# TCT_Lecture_9_TradeExecution_AI_Text

## Page 1

(1772) TCT mentorship - lecture 9 | Trade execution - YouTube
https://www.youtube.com/watch?v=rBuGsQ4_raU
Transcript:
if you want to trade Futures go ahead and put that on isolated it says it here in isolated margin mode a
certain amount of margin will be added to the position if the margin Falls below the maintenance level
liquidation will take place meanwhile you can choose to add or reduce the margin for the position and
here it says in Cross margin margin will be shared across all
(08:03) positions in the event of liquidation trades might lose all the margin and position settled using
this asset if you want to only risk the money that you put up for the pos position go ahead and put it on
isolated and then apply margin mode to all Futures I don't trade on Cross ever so go and put that on
isolated now um right below that you see or right next to it you see the leverage leverage from 1 up to

---

## Page 2

400 we to dive into a quick explanation regarding leverage as well because there's just a big Mis
understanding about it but here you can
(08:36) change the leverage and then below it you can see uh limit market and Trigger these are a
different type of orders I never use trigger um I either use limit or Market but I use Market orders 95%
of the time because um I enter on break of structures that need candle Clos and then I need to enter in
the exact moment okay so I typically either use limit or Market I'm not here going to explain to you
what a limit and Market order is I'm just going to teach you how to use it okay trigger order for the
people that don't know is
(09:10) that you can actually place a trigger where price needs to fulfill a certain order so if you want to
place a limit order a limit buy order always needs to below needs to be below current market price so
right here the market is at 94k if I want to buy when price reaches 93.3 I put a limit I say 93.

---

## Page 3

(09:33) 3 I put the quantity and I do then do buy okay it will only place it if my it will only place it
below if actually my um my my price where I want to buy at is below the current market price if my
price is above current market price and half limit it will execute as a market because it's just going to
find the next best price which is currently right here if I want to say and if I want to tell price hey if you
reach 97k only then I want to buy so actually buy when price is going up then you can place a trigger at
97 and then tell the and tell the exchange hey if if

---

## Page 4

(10:08) if we reach 97 I want to buy with market and I want to buy x amount of money okay so that's
kind of limit market and Trigger but typically I have it on Market okay right here you can see the
quantity go ahead and put the quantity on order by quantity in in usdt if we're going to calculate
position Siz with the calculations I have given to you guys in the lecture 7 risk management you need
to have it on order by quantity usdt what this means is if you have a position and you want to enter with
20,000 you simply fill in 20,000 that's

---

## Page 5

(10:47) it it will use your leverage and it will do your position divided by The Leverage and then that's
the margin you put up it's a total position size that you want to enter with if you do order by cost you
need to multiply this number with the leverage to get to your 20K so if you want to fill if you want to
trade with 20K uh but you have 10x leverage right here you need to fill in 200 or 20 you need to fill in
20 oh no you need to fill in 200 my bad you need to fill in or 2,000 yeah okay my apologies right here
we want to enter
(11:24) with 20,000 okay if you to if you put the Futures unit settings on order by cost and you want to
enter with 20K you need to fill in 2K because it will multiply it with the leverage okay which is just

---

## Page 6

inconvenient you have an extra additional calculation so just put it on order by quantity usdt right here
MTL I never have that turn on it says it right here Market to limit the order is filled at the best market
price any unfilled parts will converted into a limit price order I have that ticked off I don't use these
(11:55) long tp/ stoploss when I'm entering a trade and then right here you have the green button open
long and the red button open a short very simple and then um that is kind of the most that you need to
know you can see your maker and your taker fee right here I'm currently on demo and then if you're
going to be entering a trade your position will appear down here and we're going to be taking some live
trades in a second um right here you also always have a Futures Trading guide where they explain the
exchange itself and all the
(12:28) functions of of it and these are the most important settings that you simply need to have right
knowing kind of where your open and close is putting this on isolated and putting quantity on order by
quantity in usdt now before I'm going to dive into explaining how to take a live trade on Mexi we need
to clear something up regarding the understanding of Leverage and position sizes and risk because
there is a massive misunderstanding around it so right here what we see is the current ETH price action
and what price has simply

---

## Page 7

(13:14) done is we have created a range and we had our initial Range High right here and price
deviated that Range High after deviation one we extend Range High to the deviation high and then we
see that deviation to indicating a TCT model one distribution and then we were trying to find that entry
on the low time frame right there in that breaker structure even entering prior to the main break okay
not important as to how that was possible but just know now that that is where the entry is now what's
important if we want to calculate our position
(13:49) size we're going to use the formula that we have explained in lecture seven of the TCT
mentorship so let's say our stop loss is 0.36 I'm going to round it up to 0.4 to make it a bit easier okay

---

## Page 8

so our stop loss is 0.4% in size I want to make it 40 there we go let's say I want to risk a 100 bucks on
this setup with the formula I have given to you guys that means you have a $100 risk you divide that by
the stop loss size which is 0.
(14:40) 4% and then you multiply that with 100 if you calculate this and you do 100 divided by 0.4
time 100 you will get a position size of 25,000 okay meaning if I enter this trade with 25,000 so theant
quantity is 25,000 usdt and price goes against me and hits my stop loss I will lose 100 bucks which was
my risk on the trade and how you can validate this as an extra confirmation is okay if I enter with 25k
and price goes against me and hits my stop loss it goes against me 0.
(15:25) 4% and if you calculate what is 0.4% what is 0.0 what is 0.4% of 25,000 well fill in this
calculation and you're going to get a 100 bucks which was your initial risk okay what you're basically
doing in that calculation for the people that don't understand the calculation you're like if price goes
against me 0.4% I want to lose a 100 bucks so 0.
(15:55) 4% equals 100 bucks well my position size is 100% so what then is 100% so that's Z .4 equals
100 what you can then do is have 100 divide it by 0.4 and then multiply it by 100 to get the total
position size now here comes the crucial part your total position size is 25,000 but how you get to the
position size is up to the leverage that you use what do I mean with that let's say in this trade I have
have 25x leverage selected okay what that means this 25x Leverage is my total position size is 25,000
I'm using 25x leverage to get to the 25,000 meaning my own money that I have

---

## Page 9

(16:51) to put up for the trade is 1,000 okay so if I put up 1,000 of my own money my margin that's
called margin if I put up ,000 in margin and I use 25x leverage now I have $25,000 to trade with and
using 25x leverage will give you a certain liquidation price now let's say in this example that
liquidation price is 2,890 okay 2890 which is a pretty realistic number let's put that at 2890 boom so
entering this trade with A1 th000 margin using 25x leverage it will give me a liquidation price
presented to you in this red horizontal line of
(17:52) 2890 but what you can see is that it truly doesn't matter that I use 25 5x leverage because my
stop loss is way closer to the current market price than my liquidation price so I get stopped out of the
trade way before I can even get close to being liquidated which should always be the case now what I
can do I can also decide that I want to use 50x leverage so if the total position size is 25,000 and I use
50x leverage which money do I have to put up for the trade 25,000 divided 50x Leverage is 500 if I use
50x leverage my liquidation

---

## Page 10

(18:49) price will be closer to current market price because I'm using higher leverage okay let's say
using 50x you will be at 2860 with your liquidation price just like that okay as you can see when I use
50x leverage and this is for 50x leverage liquidation liquidation price and mind you guys this is all
going to become very clear when we take actual live trades but this needs to be cleared up right 20 25x
leverage liquidation price when you realize that if I use 25x leverage my my liquidation price at 2890 if
I use if I use 50x leverage my
(19:45) liquidation price is at 2860 guys in both situations my liquidation price is outside of my stop-
loss Lo ation meaning it's further away from current market price than my stop loss I can therefore
never get liquidated because prior to reaching my liquidation level I'll get stopped out and if I get
stopped out I lose 100 bucks I think we're currently dumping because all my alerts are going off but
okay okay back to focus guys what leverage does is leverage simply changes the ratio between the total
position size and your

---

## Page 11

(20:41) margin that is what it does either I am taking the trade with the 25,000 and I'm putting up a
th000 using 25x leverage to get to the total of 25k or I'm putting up 500 and I'm using 50x leverage to
get to the 25,000 but I'm again despite the change in leverage using the same position size and therefore
the same risk of $100 and because my stop loss is closer to the to the market price than the liquidation
price I can never lose more than my 100 bucks because I'll get stopped out before price reaches my li
liquidation
(21:29) changes until I use 200 x leverage if I use 200 x leverage my liquidation price could be here
right let's put down on the chart let's put that at uh five right there and then call this 200x liquidation
price what happens now if I use 200 x leverage right and I want to get to 25,000 2 25,000 divided by
200 is I'll put up 125 on 200x Leverage is I have to put up 125 as my margin so I can also get to the
$25,000 position size using 200 x lever average and therefore only needing to put up
(22:31) $125 of my own money but now there is an issue because my liquidation price is closer to the
market price let's say we're there than my stop- loss so I'll get if price goes against me I'll get liquidated
prior to getting stopped out and as you can see my margin is 125 bucks so I'll lose 125 bucks because I
get liquidated and the entire margin is gone than just the $100 that I was initially planning on risking on
the setup but if your liquidation price is outside of your stoploss area okay it does not matter which
amount of Leverage you use
(23:19) because the leverage just changes how much money you are using as margin while keeping the
total position size the same and there for the total risk the same it's crucial to understand this people
sometimes judge you for using a 100x leverage not realizing that it doesn't matter because it's just the
way you get to your total position size that is pre-calculated with a fixed risk you can have a $100 risk

---

## Page 12

and therefore you need to open up a 25k position and how you get to that 25k doesn't matter as long as
the liquidation price is outside
(23:57) of the stop loss area okay you need to understand this because it's crucial and the reason why
this is crucial is because let's say you have a account balance that is lower okay let's say you have
$1,000 in your account balance and you see this position and you need to open up 25,000 if you use
25x leverage and therefore it's required that you use ,000 as a margin meaning you use your total
account to get into that trade then you don't have any more money left to decide to open up other
positions on other pairs if
(24:41) opportunities present themselves whereas if you understand it you could also use 50x leverage
and nothing would change literally nothing but your liquidation price which is irrelevant because it's
outside of your stoploss home then you can only use 500 of your own margin and still have 500
leftover margin to trade with if opportunities on other pairs present themselves that's why it's crucial to
understand this okay so bringing it back to one and only Mexi you can see the chart you know the
layout let's open a position we're going
(25:21) to go on a lower time frame here on the five minute and we just saw all the alerts go off and
we're like oh yeah we're we're dumping here now let's let's say I want to go long okay I want to go long
on bitcoin right here what you can simply do is you can say 10x right I want to go long and where is
going to be the invalidation the invalidation is going to be at uh 92 820 let's say 92 820 doesn't really
matter okay we're not going to particularly pre-calculate everything but on open up a position of 20,000
because I have a setup right here you
(26:00) know if you have a setup go ahead open up a position 25,000 I want to enter the position right
now I want to go long and then right here 20 20,000 I'm using 10x leverage I'm going to click on open
long and it's going to give me a popup and then I need to claim my demo crypto okay we have 50k
Wallet balance total Equity available margin now we're ready to go okay matter of fact let's say we
want to go short we're going to go short because markets are going down when you click on open short
you get a popup okay it's a
(26:41) market order this is going to be your quantity 199 19,99 always some spread and fees involved
this is going to be your liquidation price pay attention to this estimated liquidation price 102.7 one8 on
the 10x leverage okay and then I want to open my short boom I click on open short and now we can see
the position down below so we can see Bitcoin us Perpetual a 10x short the position size is 19,90 my
average entry price is 93 4886 this is the current market price and right here you can see my liquidation
price and to get to this

---

## Page 13

(27:25) position size right here of 20,000 I used 2,000 margin okay so I put up oh man we're coming
down guys I put up 2,000 of my own money to open a position that's worth 20,000 okay cuz I'm using a
10x leverage 10 * 2 gets you to the 20K position now right here you can see my unrealized p&l which
is currently 75 usdt and you can see my realized p&l which is a um negative because you have to open
a fee when you enter a position there you can see auto marching addition you take that off you don't
want that on this is
(28:17) Market close all flash closing position you don't need to use that right now this is if you want to
place a TP and stop loss and is if you want to close the position at a certain price for a certain quantity I
don't use these buttons I always always use the close function up here but we have our trade we went
short where is our invalidation okay what we can do is we can go with our Mouse to the position on the
chart have our Mouse on it and see we have the TP and the stop loss function and it says drag or click
to set the position
(28:49) stop loss so you can click this hold it drag it and let's say we want to put our stop loss Above
That Swing point because that was our calculation it will give you a popup showcasing your position
and then it says when the last price reaches this level which is your invalidation level it will trigger the
stop- loss at the market price to close close to the position your estimated p&l is minus 360 and the p&l
rate is minus8 that doesn't really matter this this is what matters if my stop loss gets hit I'm losing
(29:24) $360 okay so I'm going to go ahead and confirm that now bringing it back comparing it to the
example here on eth but now on a live situation on bitcoin usdt you can see that my liquidation price is
102.6 n6 which if you look at it on the chart is you can't even see it on the chart it's all the way up here
so my stop loss is going to get hit way before I will get liquidated meaning I can use way higher
leverage as long as my liquidation price is outside of the stop-loss location now how do you change
your leverage on

---

## Page 14

(30:13) the position and change the margin Etc what you can simply do is go top right go to leverage
swipe it to let's say 50x Leverage okay and click confirm you will see when I change it to 50ix
Leverage The liquidation price stays the same how is that possible Right how is that possible I'm
changing the leverage to 50 my liquidation price is still the same I'm going to press confirm okay I'm
going to press confirm and you can see I'm on 50x Leverage right now 50x Leverage my liquidation
price is still the same how is that possible well as you can see
(31:04) I'm using 50ix leverage but I'm still using 2K of my own money meaning I am not using the
50x leverage because if I'm using all the 50x leverage 50 time 2K should be 100K position I have now
changed the leverage but I'm not using it yet what I can do now because I changed the Leverage is click
on this pen next to margin and click on reduce and take the money that's unnecessary in the position out
and if I want to take that money out you can see right here Max reduction 7% if I take out 111 bucks
because I don't need

---

## Page 15

(31:46) the entire 2K to keep the 20K position open now my liquidation price after adjustment starts to
change and you can see the more I want to take out the Tighter and Tighter the liquidation level will be
to the current market price do you see that when I'm when I'm taking all the money out my liquidation
price goes from 99 to 98 97 and my stop loss as you can see top right here is 95.
(32:12) 1 72 so what I could do right here I can take out and you always got to give it some room to
wiggle let's do 80% I can take out 80% of the money I currently put up for this position and my
liquidation price will be 96.7 my stop loss is 95.1 so I'm all good I'm not risking of getting liquidated I
click confirm now the margin changes to $723 and the liquidation price changed to 96.

---

## Page 16

(32:52) 7 if I go to stop loss I'm still risking the same amount as before I'm still risking 360 bucks my
position size is still the same what changed the way I got to my position size initially it was a 10x short
using 2K margin to get to 20K now it's a 50x short using $700 in margin okay and I'm not even
completely using it because I didn't reduce everything as you just saw I can still reduce more but this is
how you can change your leverage while also being in a trade already and what's so beautiful about this
is that let's say price action dumps down from here okay and you can
(33:44) put your stop loss to entry meaning you can put your stop all the way to your entry meaning
you're risking zero bucks you go to your stop loss right now and it says if you get stopped out you
make $1.9 so your stop loss is in slight profit well if my stop loss is in profit I can never get liquidated
because my liquidation can never be in profit your liquidation is always in the invalidation area
meaning if my stop loss is to break even I can put this leverage to 400 if I want to again when I click on
confirm the liquidation price stays the same
(34:25) until I use the leverage I click on confirm and I have 400x leverage oh look at this look at my
p&l card oh my God look at the p&l Shell I have 165% in profits it doesn't matter this percentages
because it's simply a calculation of the leverage times the percental move in the market which tells you
nothing about risk to reward or anything now we're on 400x Leverage okay my stop loss is to break
even we're in profit if I go to margin and if I click on reduce and if I swipe it all the way to the right
you will see if I want to
(35:02) take out almost all the money and obviously you always have a minimum amount my
liquidation price after adjustment is 93.5 A2 my stop loss is 93.4 79 I can take it all out because it's

---

## Page 17

outside of my stop loss I first get stopped out before I get liquidated but let's give it some room
adjusted and now you see I go here it will say stop loss is close to the is too close to the estimated
liquidation price of 93.
(35:36) 8 N5 um so stop loss order May fell to trigger doesn't really matter it will give this anytime you
try to do it close it's going to trigger your stop loss it's not going to trigger your liquidation price but do
always give it some room to wiggle um but as you can see I'm still in the same position of 20,000 I'm
losing nothing right now because my stop loss is to break even so it's either win or or break even
position but now I'm on 400x Leverage and this is when you will see the typical scammer promoting
his 200 to 400x leverage position which absolutely
(36:10) says nothing about his RR and his profit on the trade it says absolutely nothing but now you
have to realize when I am in a high time frame swing position and I am posting my p&l card that's
200x Leverage I probably did not enter on 200x leverage I may have entered on 50x Leverage or 40x
leverage or just a leverage that allow me to have a liquidation price outside of my stop loss Zone but
because I'm in profit and because the trade is Dr risk and my because my stop loss is to break even I
can now increase the leverage pull out
(36:50) all my margin and have available margin bottom right here to trade with that's the key guys The
Leverage to Showcase is how you got to the total position size but the total position size and therefore
the risk is still the exact same because I can draw right here I can draw this back obviously it will tell
me hey I'm going to get liquidated before I'm um before I'm going to reach my stop loss so I'm not
risking the 360 anymore but guess what even if I get liquidated I get liquidated of the the money I put
up for
(37:29) the trade I'm only putting up 120 bucks so I can only lose 120 bucks now the same way you
reduce the margin you can also add margin to it and then your liquidation price will change again so if I
add 2% my liquidation price shoots back up to 98.55% because I'm not using the 400xs leverage right
there so here you can see how you can apply that concept of Leverage and margin in a live trading
environment now let's say we want to set our take profit what you can do is you can identify where you
want to set your take profit you can go here go to TP
(38:13) click hold drag and place it and then boom it will says when the prize reaches your take profit
your estimated p&l is 345 usdt so 345 bucks click on confirm and voila there's your TP now I don't use
this TP button that often and the reason for that is because I like to set partial take profits so right now
our position is 20,000 let what if I want to cash out 50% at this price price point and 50% at the other

---

## Page 18

price point what you can do is you can go top right and simply go to the close section click on close
(38:58) you want to close using a limit order because you you just said if it reaches 92 I want to take
out 50 if it reaches 91 I want to take out 50 what you do is you click here on limit and then you go to
92,000 and you say if price reaches 92,000 I want to take out 50% and you can swipe this to 50% and it
will also showcase you the amount of uh dollars or usdt that will be taken out of the position and then
we're in short so uh we're going to say close short and then we'll give you a popup right here at 92,000
um 50% of the position equal to
(39:37) 9.8 usdt 9.8000 is going to get taken out and your estimated p&l is 15 157 click on close short
and boom you can see your partial take profit now what you can do for the other is do the exact same
so if it reaches 91,000 I can I want to close the of the position which is 50% and then it will give you
the same popup it's going to close this amount and it's going to close 264 bucks in profit and boom
there are your partial take profits through limit okay if you want to close out of the position partially
but at the
(40:18) current market price you can simply go to market and swipe that you want to take out 30%
click on close short and then boom your es made appear pnl will be around 30 close short and you will
close 30% of the position you can see we bought there sold there made a slight profit we can see the
increase in realized p&l and we can see the decrease in position size because we initially had close to
20,000 and now we have 13,092 because we closed 30% now um if your trading exchange doesn't have
a close function and most
(40:58) of them have you can always close the position bottom right at the position um level right here
where you can see you have your TP you have your stop loss but you can close right here using Market
or the uh last Price Right Here fill in the price click on the quantity swipe it the same way we just did
and click on close short so you can also close the um position using uh the buttons down here I just use
the buttons top right always because that's what I've been doing always okay now another great thing is
like we just explained with the
(41:39) leverage and if your liquidation price is outside of your stop loss and it doesn't really matter
especially when your stop loss is to break even it also is the situation and the case when you Trill your
stop loss right so let's say price goes down and my invalidation goes from that high to this high right
my risk diminishes diminishes so initially if I put it back at that high which was the initial Target my
risk is 252 okay initially the risk was 360 but we closed out um 30% so now the risk is 252 now let's
say I can now based on
(42:18) confirmations Trill my stop loss to the most local lower high okay well now my risk diminishes
to one 26 126 bucks if you want to still risk 1% what you can simply do is open up a new position with
$130 risk right because now we're risking 126 I want to risk 250 in total and if I can now open up
another position of around $24 risk and I click on open short again I can have my 1% risk back using
that new invalidation point so you can go to open and then you can simply click on go short now right

---

## Page 19

now with we're at
(43:08) 14k on the top of my head let's say you open a 12,000 position if you are already short and you
click on open short again it will add to the position size okay so I open short you get the popup of the
confirmation look at that it's the same trade it's not too two individual shorts that can't happen okay
right now the position size is 26,000 th000 I go to TP stop loss I go back and I see I'm risking $235
now my Max was $ 250 I am all good okay and that way if you control your stop loss but you want to
keep the same risk you
(43:49) can now add back to the position and therefore increase the total position size again and then
boom have it take profit that's like at around 92 but then double the double the profit because you're in
double the position size okay so it's very simple guys if you want to close the position you can also go
go close short here close short and then boom you exited and you're done but you can also go to close
top right click on Market swipe it to 100 and close the entire trade but as you can see it's very very
simple you have a
(44:25) open function you have a closed function you put it on isolated The Leverage doesn't really
matter as long as the liquidation price is outside of your stop loss Zone and um you have limit Market
trigger that I barely use right here you can open up however much you want and it will give you the
max that you can open down there as as well as just a nice little extra function because right now I have
a 50k demo account for this video and it's 400x leverage and um if I open up a 100 I can uh I can open
up almost a seven mil position which is
(45:02) pretty crazy right pretty crazy it does have a maximum I wouldn't open seven Mill in one
market order the spread's not not going to be that nice okay but yeah you simply open up your trades
you close your trades and once they're there you can manage them in this uh area right here and right
there after placing a trade you can go to position history and you can find your trade back where you
had the open open time yet the closing time the margin mode your average entry your average close
and also the real life p&l this is where you
(45:34) can get your screenshot boom you can share it with your community with your with your
brothers and um showcase how good you are trading after watching this mentorship and uh you can
also go to order and trade history where you can see all the orders of the positions this is simply the
position and these are all the orders where you know we uh we went short initially we went short right
there or we closed a short let me see sell short close it for some profits and you can see all the details
here it's all completed if you want to have
(46:12) the data to look back on you can use it right there and then this is simply your uh your wallet
which is currently My Demo account okay but it's every single trading exchange is going to be looking
very similar okay you're all going to have a chart they're all going to have the order book right there
which you don't need to use and then you're going to get your function here where you placing the
trades using open and close if you don't have the close function it's it's bottom right there if you have to
trade open that is simply it I'm
(46:42) thinking if I'm forgetting something it's just extremely important that you understand that the
leverage the only thing the leverage does is change the ratio between your margin and the total position
size that's what the leverage represents you can have a 20 5K position on this eth example and oh man
we indeed uh completed the entire model one distribution in a live uh mentorship environment right
here but um you can complete this distribution right and you can short there with 25,000 having your
stop loss above that

---

## Page 20

(47:17) High having a bless me having a $100 risk The Leverage simply showcase is how you get to
the total position size so it's either you put up a th000 to get or you put up a th000 use 25x leverage and
get 25k or you put up 500 use 50x leverage get 25k or you put up 125 use 200 200 High index leverage
get 25k but you're still using 25k and your stop loss is still the same inv validation from a percental
standpoint so you're still risking the same amount so despite the leverage you're still risk risking the
same amount you just
(47:58) got to make sure that the leverage liquidation price is not closer to your current stop loss price
okay that's all and that's the biggest misconception that currently is around trading so the moment you
are in this position and price coming down right here and you can move your stop loss to break even
what can you do you can put the leverage to a maximum and take out and reduce all your margin and
now you have money in your account to take other trades with because either way if you guys are
going to start trading don't put the all the money that
(48:34) you want to trade with on your trading exchange let's say you have 10,000 you want to start
trading with don't put 10K on your leverage trading exchange okay put up 5,000 why one you never
want to have all your money on the trading exchange because not your keys not your wallet the
exchange can have a bank run your money could be frozen your money could be gone there's always
risk involved if you want to with if you 10K put 5K on the exchange right I typically sometimes put 30
as low as 30% so if I want to trade with 100K I'll put 30k on the
(49:13) exchange second when you're starting out and you still don't have your trading psychology
fully under control you want to avoid being in this impulsive state where you have access to leverage
trade with your 10K and then blow it all if you're very impulsive but you don't have all the money on
on the exchange you cannot blow all the money because you still have money left over on a different
exchange and you're not going to be that impulsive for so long you're going to send that money and
then still make an impulsive decision by that
(49:46) time your impulsive State of Mind is cooled down so two reasons protect your money spread it
across different wallets different exchanges different banks plus avoid you falling into an impulsive
trap to then liquidate your entire account and the entire 10K rather than just the 5K if you're if you're
[ __ ] up okay I think I had it all I think I I managed it all if you guys have any questions let me know
in the comments and I'll get back to every single one of you and um if you want me to make a video
regarding entering trades and
(50:25) managing trades on a on a tradition broker with metatrader and just the Forex Market Etc also
let me know in the comments and I'll do that and um again my recommendation Mexi bit Unix and

---

## Page 21

bybit you can find the links in the description and um I appreciate all you guys for tuning in hopefully
you learned something and then now you can start taking trades effectively okay all these trailing stops
trigger orders you don't need to use them just use what I showed you with open close Market limit
isolated leverage open long open short
(51:01) drag for the Stop and take profit and then that is it appreciate all of you guys for tuning in and
I'll see you all inside the Discord chcha