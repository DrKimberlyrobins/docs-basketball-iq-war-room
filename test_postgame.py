import unittest
from postgame import grade
class Grades(unittest.TestCase):
 def test_markets_and_halves_are_independent(self):
  r={'projection':{'full':[73,75],'half':[36,37]},'market':{'sideIndex':0,'spread':[3.5,-3.5],'total':139.5,'totalDirection':'Over'},'halfMarket':{'quote':{'sideIndex':1,'spread':[2,-2],'total':70,'totalDirection':'Under'}}}
  g=grade(r,[80,73],[39,31])
  self.assertFalse(g['winnerCorrect']);self.assertEqual(g['spreadResult'],'Win');self.assertEqual(g['totalResult'],'Win');self.assertEqual(g['halfSpreadResult'],'Loss');self.assertEqual(g['halfTotalResult'],'Push');self.assertFalse(g['halfWinnerCorrect'])
 def test_missing_half_does_not_invent_grades(self):
  g=grade({'projection':{'full':[70,70],'half':[35,35]}},[70,71],[None,None])
  self.assertIsNone(g['winnerCorrect']);self.assertNotIn('halfWinnerCorrect',g)
if __name__=='__main__':unittest.main()
