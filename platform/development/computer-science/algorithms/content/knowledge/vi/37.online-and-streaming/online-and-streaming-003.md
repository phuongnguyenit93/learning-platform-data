# Bài toán thuê hay mua (ski rental)

**Bài toán thuê hay mua (ski rental problem)** là một ví dụ kinh điển của **thuật toán trực tuyến (online algorithms)**: người ra quyết định phải hành động khi dữ liệu tương lai chưa được biết. Mỗi ngày còn sử dụng một dịch vụ, ta có thể **thuê** trong ngày với giá R, hoặc **mua** một lần với giá B và từ đó không phải thuê nữa. Ta **không biết trước sẽ còn bao nhiêu ngày sử dụng D**. Câu hỏi không phải chỉ là chọn một đáp án rẻ nhất nếu biết D, mà là thiết kế một chính sách ra quyết định ngày qua ngày với chi phí không quá tệ so với người có quyền biết D từ đầu.

Bài **“Bài toán thuê hay mua (ski rental)”** thuộc nhóm **Trực tuyến và luồng** của Computer Science Algorithms. Đây là một trong những mô hình dễ hiểu nhất để học **competitive analysis**: so chi phí thuật toán online với **OPT offline**, phân biệt quyết định theo thông tin hiện tại với việc nhìn trước tương lai, xây một chính sách **2-competitive**, chứng minh giới hạn tỷ số và hiểu vai trò của chiến lược ngẫu nhiên.

Trong bài, thuật toán chính là **thuê cho k−1 ngày rồi mua vào ngày k**, với k=ceil(B/R). Đây là một chiến lược tất định đơn giản, có bảo đảm chi phí **nhỏ hơn 2 lần OPT** khi D≥1. Bài cũng làm rõ rằng k=ceil(B/R) là một lựa chọn có chứng minh 2-competitive, **không phải lúc nào cũng là ngưỡng tối ưu về competitive ratio trong mô hình ngày rời rạc nếu B/R không nguyên**. Phần Java 17+ có mô phỏng từng ngày và oracle offline độc lập; đã chạy thành công **11.808 bộ vét cạn**, **2.500 trường hợp có seed** và kiểm tra số nguyên rất lớn bằng BigInteger.

## 1. Phát biểu mô hình chi phí

Các đại lượng:

~~~text
R = giá thuê một ngày, R > 0.
B = giá mua một lần, B > 0.
D = tổng số ngày thực sự sử dụng, D >= 0.
~~~

Mỗi ngày được đánh số 1,2,3,... và chỉ phát sinh nếu người dùng còn cần thiết bị/dịch vụ ngày đó.

Tại **đầu một ngày sử dụng**, nếu chưa mua, thuật toán online có hai lựa chọn:

- **RENT:** trả R cho ngày hiện tại; ngày sau nếu còn dùng phải quyết định tiếp.
- **BUY:** trả B một lần **ở đầu ngày hiện tại**, dùng ngay ngày đó và các ngày về sau **không tốn tiền thuê nữa**.

Nếu đã mua, hành động những ngày tiếp theo chỉ là **OWN**, không trả thêm tiền. Không có chi phí bán lại, phí giữ thiết bị, lãi suất, khấu hao, khuyến mại hoặc hoàn tiền trong mô hình gốc.

Điểm then chốt: **D chỉ được biết sau khi quá trình kết thúc**, không được dùng trong quyết định của từng ngày. Giá R và B được biết trước và không đổi trong toàn bộ thời gian.

## 2. Online khác offline ở chỗ nào?

**Online:** buổi sáng ngày t, ta biết các ngày 1..t−1 đã trải qua và biết ngày t có nhu cầu. Nhưng chưa biết ngày t+1 có xuất hiện hay không. Quyết định mua/thuê phải được đưa ra mà **không tra D tương lai**.

**Offline:** được biết chính xác D ngay từ đầu, nên chọn phương án rẻ nhất cho toàn bộ chuỗi sử dụng.

Ví dụ R=1, B=5:

~~~text
Nếu biết D=2:
    thuê 2 ngày, tốn 2.

Nếu biết D=100:
    mua ngay ngày 1, tốn 5.
~~~

Người ra quyết định online **không thể** đồng thời biết từ ngày 1 rằng tình huống nào sắp xảy ra. Vì thế một thuật toán được đánh giá theo **mức thiệt hại tối đa tương đối với OPT**, không phải kỳ vọng là sẽ luôn làm đúng như người biết trước tương lai.

## 3. Lời giải tối ưu offline

Với D ngày, offline có hai dạng phương án hữu ích:

1. **Thuê cả D ngày:** chi phí D·R.
2. **Mua ngay ngày 1:** chi phí B.

Một phương án mua ở ngày t>1 sau khi đã thuê t−1 ngày có chi phí (t−1)R+B, không thể rẻ hơn mua ngay ngày 1 vì R>0. Do đó nếu biết chắc D, không có lý do kinh tế để **thuê trước rồi mới mua**, trừ khi đã ràng buộc thông tin/điều kiện khác ngoài mô hình.

Vì vậy công thức exact:

~~~text
OPT(D) = min(D*R, B) khi D>=1.

OPT(0) = 0.
~~~

Với D=0, chưa có ngày sử dụng nên offline và online đều không trả tiền. Trong trường hợp này không nên tính tỷ số 0/0; báo cạnh riêng là không xác định hoặc dùng bất đẳng thức chi phí.

Ví dụ R=3,B=10:

~~~text
D=1: OPT=min(3,10)=3.
D=2: OPT=min(6,10)=6.
D=3: OPT=min(9,10)=9.
D=4: OPT=min(12,10)=10.
D=5: OPT=min(15,10)=10.
~~~

Từ ngày 4 trở đi, offline chọn mua ngay từ đầu với giá 10.

## 4. Tại sao luôn thuê hoặc luôn mua đều có thể tệ?

Một chính sách **luôn thuê**, dù tiết kiệm khi D nhỏ, sẽ có:

~~~text
C_online(D)=D*R.
OPT(D)=B với D đủ lớn.
C_online/OPT = D*R/B.
~~~

Khi D tăng không giới hạn, tỷ số tăng không giới hạn. Vì vậy **thuê mãi không có competitive ratio hằng số** trong bài ski rental với B hữu hạn.

Một chính sách **mua ngay ngày 1** có chi phí B cho mọi D≥1. Nếu B rất lớn so với R nhưng việc sử dụng chấm dứt ngay sau một ngày, offline chỉ tốn R:

~~~text
C_online/OPT = B/R.
~~~

Nếu tỷ số B/R rất lớn, mua ngay là quyết định online tệ khi hành trình ngắn.

Một chính sách có bảo đảm tốt phải **thuê một thời gian có giới hạn để tránh mua quá sớm**, rồi **mua trước khi chi phí thuê quá lớn so với giá mua**.

## 5. Quy tắc cân bằng chi phí: chọn ngày mua k

Chính sách chuẩn dễ nhớ:

~~~text
k = ceil(B/R).

Ngày t < k: RENT.
Ngày t = k: BUY nếu ngày k thực sự xuất hiện.
Ngày t > k: OWN (đã mua ở ngày k).
~~~

Tức **thuê trong k−1 ngày đầu**, rồi mua vào đầu ngày k nếu vẫn có nhu cầu.

`ceil(B/R)` là **làm tròn lên tới số nguyên**, không làm tròn xuống theo kiểu ép số thực. Trên Java với long dương, có thể tính an toàn:

~~~java
long k = B / R + (B % R == 0 ? 0 : 1);
~~~

Không dùng công thức `(B+R−1)/R` khi B và R có thể gần Long.MAX_VALUE vì phép cộng B+R−1 có thể tràn trước khi chia.

Nếu B≤R thì k=1, nghĩa là **mua ngay ngày sử dụng đầu tiên**. Khi giá mua không cao hơn một ngày thuê, đây cũng là hành động tối ưu offline cho mọi D≥1.

## 6. Chính sách không hề nhìn trước D

Một lỗi phổ biến khi viết mã giải bài ski rental là tính:

~~~text
if (D*R < B) rent else buy
~~~

Tính toán trên **D** là lời giải offline, không phải thuật toán online. Đó là hành vi nhìn trước tương lai.

Hàm quyết định đúng trong bài:

~~~text
actionForDay(contract, currentDay):
    k = ceil(B/R).
    if currentDay < k: RENT.
    if currentDay == k: BUY.
    otherwise: OWN.
~~~

Hàm này **không nhận D**, không được biết sau ngày hiện tại sẽ còn nhu cầu hay không. Ngày thực sự cuối cùng D chỉ được truyền vào hàm **evaluate** để **đánh giá chi phí** sau khi biết kết quả thực tế, không được đưa vào logic ra quyết định.

Nếu chưa có ngày sử dụng nào (D=0), chính sách không được gọi cho ngày 1 và không tốn chi phí. Đây là khác biệt giữa việc **lên kế hoạch sẽ mua nếu còn nhu cầu tới ngày k** với việc **trả tiền mua ngay từ đầu**.

## 7. Công thức chi phí online theo D

Với k=ceil(B/R):

**Trường hợp 1: D<k.** Ngày mua không xuất hiện. Thuật toán thuê đúng D ngày:

~~~text
ONLINE(D) = D*R.
~~~

**Trường hợp 2: D≥k.** Thuật toán thuê k−1 ngày rồi mua ở đầu ngày k:

~~~text
ONLINE(D) = (k−1)*R + B.
~~~

Hai trường hợp nối nhau đúng theo quy ước mua **trước khi sử dụng ngày k**. Không được vừa tính tiền thuê ngày k lại vừa tính tiền mua ngày k nếu mô hình cho phép mua ngay đầu ngày.

Tóm tắt:

~~~text
ONLINE(D) =
    D*R                  nếu 0 <= D < k.
    (k−1)*R + B          nếu D >= k.

OPT(D) =
    0                    nếu D=0.
    min(D*R, B)          nếu D>=1.
~~~

Chi phí online sau ngày k **không tăng thêm**, vì đã mua. Với D cực lớn, số ngày sử dụng nhiều không làm phát sinh tiền thuê mới.

## 8. Chứng minh bảo đảm 2-competitive

Đặt k=ceil(B/R). Theo định nghĩa làm tròn lên:

~~~text
(k−1)*R < B <= k*R.
~~~

**Nếu D<k:** do D≤k−1, ta có D·R≤(k−1)R<B. Offline cũng chọn thuê, nên:

~~~text
ONLINE(D)=D*R=OPT(D).
~~~

Tỷ số bằng 1 với D≥1.

**Nếu D≥k:** ta có D·R≥kR≥B, nên OPT(D)=B. Chi phí online:

~~~text
ONLINE(D) = (k−1)*R + B
          < B+B
          = 2*OPT(D).
~~~

Vì vậy với mọi D≥1:

~~~text
OPT(D) <= ONLINE(D) < 2*OPT(D).
~~~

Đây là **bảo đảm tất định theo trường hợp tệ nhất**, không cần xác suất, không phụ thuộc giá trị D hay đối thủ kết thúc ngay trước/ngay sau một ngày cụ thể.

Tại D=0, cả hai chi phí bằng 0; phát biểu bằng **ONLINE(0)≤2 OPT(0)** vẫn đúng, nhưng tỷ số cạnh tranh không được lấy vì có phép chia cho 0.

## 9. Competitive ratio nghĩa là gì?

Một thuật toán online được gọi là **c-competitive** nếu trên mọi chuỗi đầu vào hợp lệ (ở đây đặc trưng bởi D) có:

~~~text
ONLINE(D) <= c*OPT(D) + alpha.
~~~

Trong đó `alpha` là một hằng số cộng độc lập với độ dài đầu vào trong định nghĩa tổng quát. Với chính sách ở đây, ta có c=2 và **alpha=0**, tức bảo đảm thuần nhân.

Với các input OPT>0, tỷ số của một trường hợp:

~~~text
ratio(D) = ONLINE(D)/OPT(D).
~~~

Competitive ratio ở worst case là **cận trên của ratio(D) khi D thay đổi**. Không phải tỷ số trung bình trên một bộ dữ liệu ngẫu nhiên và không phải mức sai lệch tuyệt đối bằng 2 đơn vị tiền.

Điểm khác với thuật toán xấp xỉ offline: online không được biết chuỗi tương lai khi ra quyết định, còn thuật toán xấp xỉ offline biết toàn bộ đầu vào nhưng có thể không tìm nghiệm tối ưu vì giới hạn tính toán.

## 10. Ví dụ R=1, B=5

Với giá thuê 1 mỗi ngày và giá mua 5:

~~~text
k = ceil(5/1) = 5.
Thuê ngày 1,2,3,4.
Nếu vẫn dùng ngày 5, mua ở đầu ngày 5.
~~~

Bảng chi phí:

| D | Quyết định thực tế | ONLINE(D) | OPT(D) | Tỷ số |
| ---: | --- | ---: | ---: | ---: |
| 0 | Không sử dụng | 0 | 0 | Không xác định |
| 1 | Thuê 1 ngày | 1 | 1 | 1 |
| 3 | Thuê 3 ngày | 3 | 3 | 1 |
| 4 | Thuê 4 ngày | 4 | 4 | 1 |
| 5 | Thuê 4 ngày rồi mua | 9 | 5 | 1,8 |
| 6 | Thuê 4 ngày rồi mua | 9 | 5 | 1,8 |
| 100 | Thuê 4 ngày rồi mua | 9 | 5 | 1,8 |

Trường hợp D=5 làm ta thấy rủi ro của online: vừa trả bốn ngày thuê rồi phải trả đủ giá mua. Tuy nhiên tỷ số chỉ 9/5=1,8, nằm dưới 2.

Hàm `actionForDay` trong Java in cụ thể:

~~~text
Day 4 -> RENT.
Day 5 -> BUY.
Day 6 -> OWN.
~~~

Nếu hành trình dừng ở ngày 4, lệnh BUY ở ngày 5 **không được thực thi**. Tỷ số ở D=4 vẫn là 1.

## 11. Ví dụ R=3, B=10: B/R không nguyên

Giá thuê R=3, giá mua B=10:

~~~text
B/R = 10/3 ≈ 3.333...
k = ceil(10/3) = 4.
~~~

Chính sách cơ sở thuê ngày 1,2,3; nếu ngày 4 xuất hiện thì mua.

~~~text
D=3:
    ONLINE = 3*3 = 9.
    OPT = min(9,10) = 9.
    ratio = 1.

D=4:
    ONLINE = 3*3+10 = 19.
    OPT = min(12,10) = 10.
    ratio = 1.9.
~~~

Tỷ số 1,9 vẫn dưới 2 nhưng khá sát cận trên. Đây là ví dụ cho thấy nên làm tròn ngày mua **một cách có chủ đích**, không áp máy móc các công thức tối ưu dành riêng cho trường hợp B chia hết cho R.

Quan trọng: chính sách k=ceil(B/R) **đủ** để chứng minh 2-competitive, nhưng không luôn là chính sách **tối ưu hóa worst-case ratio** trong mô hình ngày nguyên; vấn đề này được tách riêng ở phần tiếp theo.

## 12. Ngưỡng tối ưu trong mô hình ngày rời rạc

Xét cả họ chính sách tất định **thuê tới trước ngày t, mua ở ngày t nếu còn dùng**, với t là một số nguyên dương.

Nếu D<t, chi phí bằng D·R. Nếu D≥t, chi phí bằng (t−1)R+B. Với B>R, tỷ số tệ nhất của chính sách t đạt tại D=t và bằng:

~~~text
W(t) = [B+(t−1)R] / min(tR, B).
~~~

Lý do: trước t, tỷ số thuê/OPT không giảm khi D tăng; từ t trở đi, chi phí online đã cố định còn OPT không giảm, nên tỷ số lớn nhất xuất hiện ngay tại thời điểm mua.

Gọi q=floor(B/R), k=ceil(B/R). Khi B/R không nguyên và B>R:

- Với t≤q, mẫu số tR; công thức W(t)=1+(B−R)/(tR), **giảm khi t tăng**.
- Với t≥k, mẫu số B; công thức W(t)=1+(t−1)R/B, **tăng khi t tăng**.

Do đó nếu muốn tìm ngưỡng **tối ưu trong họ chính sách mua vào một ngày cố định**, chỉ cần so **t=q hoặc t=k** (khi q≥1). Khi B/R nguyên, q=k là ứng viên tự nhiên; khi B≤R, mua ngày 1 là tối ưu.

Ví dụ R=3,B=10:

~~~text
q=3, k=4.

Mua ngày 3:
    D=3: ONLINE=2*3+10=16, OPT=9.
    W(3)=16/9≈1.7778.

Mua ngày 4:
    D=4: ONLINE=3*3+10=19, OPT=10.
    W(4)=19/10=1.9.
~~~

Ở đây **ngày 3 tốt hơn về worst-case ratio**, dù chiến lược cơ sở của bài chọn ngày 4 để có một chứng minh 2-competitive trực tiếp rất đơn giản. Đừng nói mọi lựa chọn k=ceil(B/R) đều là chiến lược tất định tối ưu cho tất cả R,B.

## 13. Khi B≤R: mua ngay là tối ưu

Nếu giá mua B nhỏ hơn hoặc bằng **một ngày thuê R**, việc thuê ngày đầu đã không có lợi so với mua:

~~~text
B <= R.
k=ceil(B/R)=1.
~~~

Nếu D≥1, online mua ngay ngày 1 với giá B; offline cũng trả min(DR,B)=B. Do đó tỷ số bằng 1 cho mọi D≥1.

Ví dụ:

~~~text
R=4, B=3, D=7.

ONLINE=3.
OPT=min(7*4,3)=3.
ratio=1.
~~~

Nếu D=0, không có ngày 1 nên **không mua** và chi phí bằng 0. Mua trước khi biết có sử dụng ít nhất một ngày là một mô hình khác, cần phát biểu lại.

## 14. Chặn 2 có sát không?

Với R=1 và B nguyên k≥1, chính sách mua vào đầu ngày k sau k−1 ngày thuê. Nếu horizon D=k, ta có:

~~~text
ONLINE(k) = (k−1)+k = 2k−1.
OPT(k)=k.

ratio(k)=(2k−1)/k=2−1/k.
~~~

Khi k tăng, tỷ số tiến dần tới 2 từ phía dưới. Vì vậy **không thể chứng minh một cận đồng đều nhỏ hơn 2** cho **chính chiến lược k=ceil(B/R)** trên mọi B/R.

Lưu ý đây là **mệnh đề về chiến lược cụ thể**, không phải tự động chứng minh cận dưới 2 cho mọi chính sách randomized trong mọi mô hình. Các thuật toán ngẫu nhiên và mức thông tin của đối thủ có thể đạt bảo đảm khác.

## 15. Đối thủ kết thúc bất ngờ ngay trước/sau ngày mua

Ta có thể hình dung một **adversary** chọn horizon D để làm online mất lợi thế. Với một ngưỡng ngày mua k, hai trường hợp đối lập:

~~~text
D=k−1:
    Online chỉ thuê (k−1) ngày.
    Nếu k=ceil(B/R), chi phí bằng OPT.

D=k:
    Online đã thuê k−1 ngày và mua.
    Offline biết D nên có thể mua từ ngày 1.
~~~

Nếu thuật toán mua quá sớm, đối thủ dừng ngay sau ngày mua để làm phí mua lãng phí. Nếu thuật toán mua quá muộn, đối thủ kéo dài hành trình để làm phí thuê tích lũy lớn.

**Competitive analysis** không yêu cầu biết D trước; nó xem **mọi D có thể xảy ra** và chứng minh rằng dù adversary chọn trường hợp nào, chi phí online vẫn nằm trong cận đã phát biểu.

Nếu thêm khuyến mại thay đổi theo ngày, hoặc đối thủ được thay giá mỗi ngày, cách chứng minh dựa trên R,B cố định không còn áp dụng trực tiếp.

## 16. Randomized ski rental: ý tưởng giảm tỷ số kỳ vọng

Một chính sách tất định có thời điểm mua dự kiến rõ ràng nên đối thủ có thể chọn horizon tệ nhất ngay quanh thời điểm ấy. **Ngẫu nhiên hóa thời điểm mua** giúp đối thủ không biết trước chính xác lúc mua, nếu horizon được chọn **không dựa trên kết quả random của thuật toán**.

Trong mô hình **thời gian liên tục**, với đơn vị chi phí thuê R mỗi đơn vị thời gian, giá mua B, có một chiến lược cổ điển đạt competitive ratio **kỳ vọng e/(e−1)≈1,582** đối với đối thủ oblivious (chọn horizon mà không quan sát random nội bộ).

Đặt x=R·t/B, tức thời gian thuê được chuẩn hóa sao cho mua ở t=B/R tương ứng x=1. Chọn thời điểm mua ngẫu nhiên X trong [0,B/R] với hàm phân phối:

~~~text
F_X(t) = (exp(R*t/B)−1)/(e−1),
         0 <= t <= B/R.
~~~

Mật độ:

~~~text
f_X(t) = (R/B)*exp(R*t/B)/(e−1).
~~~

Hành động là thuê tới thời điểm X và mua tại X nếu nhu cầu vẫn còn. Nếu horizon ngắn hơn X thì không mua. Đây là chính sách **của mô hình liên tục**, không phải code Java chính của bài.

Không tự tuyên bố rằng làm tròn X sang ngày nguyên sẽ giữ nguyên cận e/(e−1). Phân phối tối ưu cho mô hình ngày rời rạc với R,B tùy ý phải được phân tích riêng.

## 17. Phác thảo chứng minh tỷ số ngẫu nhiên liên tục

Gọi D là thời lượng sử dụng thực, với chi phí thuê R mỗi đơn vị thời gian và B là giá mua.

Nếu D≤B/R:

~~~text
E[ONLINE(D)] =
    integral_0^D (R*t+B)*f_X(t) dt
    + (R*D)*(1−F_X(D)).
~~~

Thay mật độ và hàm phân phối ở trên, ta có:

~~~text
integral_0^D (R*t+B)*f_X(t) dt
    = R*D*exp(R*D/B)/(e−1).

(R*D)*(1−F_X(D))
    = R*D*(e−exp(R*D/B))/(e−1).
~~~

Hai vế cộng lại:

~~~text
E[ONLINE(D)] = (e/(e−1))*R*D.
OPT(D) = R*D nếu D<=B/R.
~~~

Nếu D≥B/R thì luôn mua trước hoặc đúng thời điểm B/R:

~~~text
E[ONLINE(D)] = E[R*X+B]
             = (e/(e−1))*B.

OPT(D)=B.
~~~

Do đó với mọi D>0, tỷ số kỳ vọng là e/(e−1) trong mô hình liên tục đã nêu. **Giả thiết quan trọng:** adversary không được nhìn thấy thời điểm mua ngẫu nhiên rồi chọn D phụ thuộc trực tiếp vào lần tung random ấy; nếu đối thủ có quyền thích nghi như vậy, cách đánh giá cần thay đổi.

## 18. Khác biệt giữa chiến lược xác suất và chiến lược trong Java

Bài Java cố ý cài một **thuật toán tất định dễ kiểm chứng**:

~~~text
k = ceil(B/R).
actionForDay(day) ∈ {RENT, BUY, OWN}.
~~~

Nó có bảo đảm **ONLINE(D)<2 OPT(D)** cho D>0 và bằng nhau bằng 0 khi D=0, không cần seed.

Phần ngẫu nhiên ở mục trước là **kiến thức mở rộng**: chọn thời điểm mua ngẫu nhiên trong mô hình liên tục và chứng minh theo kỳ vọng. Không được nhầm:

- Cận tất định của policy Java với cận kỳ vọng của policy random.
- Thời gian liên tục với ngày nguyên.
- Expected competitive ratio với việc mỗi lần chạy chắc chắn có tỷ số không quá e/(e−1).
- Adversary oblivious với đối thủ nhìn được random của thuật toán.
- Random sinh dữ liệu **kiểm thử** với random để chọn **hành động của thuật toán**; code Java ở đây chỉ dùng random cho test cases.

## 19. Bài toán mở rộng: thuê/mua trong đời thực

Ski rental là một mô hình trừu tượng cho nhiều tình huống:

- Thuê máy chủ theo giờ hay mua một máy vật lý.
- Thuê thiết bị theo ngày hay mua thiết bị để sử dụng dài hạn.
- Trả phí theo lần truy cập hay mua giấy phép trọn đời.
- Dùng gói dịch vụ theo ngày hay mua vé tháng.
- Trả phí vận hành linh hoạt hay đầu tư cố định.

Những tình huống thực có thể có các biến thể vượt mô hình:

1. **Giá thuê biến đổi theo ngày:** R không còn hằng số, ngưỡng B/R cần được thay bằng chính sách khác dựa trên tổng chi phí đã phát sinh và mức độ thông tin.
2. **Giá mua tăng/giảm theo thời gian:** mua ở ngày k tốn B_k, nên chứng minh trên B cố định không còn đúng.
3. **Chi phí bảo trì sau khi mua:** offline tối ưu không còn đơn giản là min(DR,B).
4. **Có giá trị bán lại:** chi phí sở hữu ròng khác B.
5. **Giảm giá, coupon, hoàn tiền:** thời điểm chiết khấu và điều kiện áp dụng ảnh hưởng quyết định.
6. **Không biết liệu ngày hiện tại có nhu cầu:** nếu mua trước khi có một ngày sử dụng chắc chắn, D=0 cũng có thể chịu phí; mô hình phải phát biểu lại.

Trước khi áp dụng chiến lược, hãy xác định đúng **mô hình chi phí và thông tin**. Sự đơn giản của ski rental nằm ở việc **có hai hành động, giá cố định, không biết horizon**.

## 20. Overflow và tính toán tỷ số chính xác

Nếu R, B và D là các số nguyên long lớn, phép nhân D·R có thể vượt **Long.MAX_VALUE**, ngay cả khi từng toán hạng nằm trong long.

Ví dụ:

~~~text
R=1.
B=Long.MAX_VALUE.
D=Long.MAX_VALUE.

k=B.
ONLINE=(B−1)*1+B
      =2*Long.MAX_VALUE−1.
~~~

Giá trị ONLINE này **không thể lưu trong long**, dù k và D có thể. Code Java dùng:

~~~java
BigInteger online = BigInteger.valueOf(rentedDays)
        .multiply(BigInteger.valueOf(rentPerDay));
if (purchased) {
    online = online.add(BigInteger.valueOf(buyPrice));
}
~~~

Tương tự, OPT được tính bằng BigInteger để không tràn trước khi lấy min. Ngày mua k được tính bằng **chia nguyên và phần dư** chứ không lấy Math.ceil trên double, vì double có thể không biểu diễn chính xác những số nguyên 64-bit lớn.

Để kiểm tra bảo đảm 2-competitive, code so hai số nguyên:

~~~text
ONLINE < 2*OPT khi D>0.
~~~

Không cần chia floating-point. Chỉ khi **hiển thị tỷ số** mới dùng BigDecimal với 4 chữ số thập phân; nếu OPT=0 in **n/a** để tránh chia cho 0.

## 21. Tại sao chọn BigInteger trong ví dụ Java?

Bài thực hành Java hướng tới cả **đúng toán học** lẫn **an toàn số học**:

- Ngày sử dụng là long không âm.
- R, B là long dương.
- k=ceil(B/R) tính bằng phép chia và phần dư trên long.
- Số ngày đã thuê khi mua là k−1, không bao giờ âm.
- Chi phí online và offline là **BigInteger**, vì tổng chi phí có thể lớn hơn long.
- Không khởi tạo một vòng mô phỏng từng ngày cho D cực lớn; thay bằng công thức chi phí đóng.
- Khi D nhỏ, một **mô phỏng ngày-by-ngày độc lập** được dùng làm phép kiểm thử so với công thức đóng.
- Kiểm tra kết quả bằng bất đẳng thức nguyên thay vì ratio double làm tròn.

Nếu bài thi chỉ có R,B,D≤10^6, kiểu long thường đã đủ cho tất cả phép cộng/nhân trong mô hình này. BigInteger trong demo là lựa chọn phòng thủ cho **toàn miền long dương** và giúp tránh phụ thuộc vào giới hạn input chưa được cung cấp.

## 22. Java 17+: chương trình chạy độc lập

Lưu mã dưới đây thành **SkiRentalOnlineLesson.java**. Chương trình gồm:

- `Contract(rentPerDay,buyPrice)` kiểm tra giá dương.
- `Action` với ba trạng thái RENT, BUY, OWN.
- `purchaseDay(c)` tính k=ceil(B/R) không tràn ở bước cộng.
- `actionForDay(c,day)` quyết định **không nhận D tương lai**.
- `evaluate(c,days)` tổng kết sau khi biết horizon bằng công thức đóng, trả Outcome gồm ngày mua, số ngày thuê, trạng thái mua, online và offline.
- `exhaustiveOffline`: oracle liệt kê mọi thời điểm mua khả dĩ **và phương án không mua** cho horizon nhỏ.
- `simulateOnline`: mô phỏng từng ngày bằng hành động của policy, độc lập với công thức đóng.
- `check`: so cả hai oracle, xác nhận bất đẳng thức 2-competitive theo **BigInteger**.
- `verify`: vét cạn giá/horizon nhỏ, kiểm thử random seed, input cực trị và input sai.
- `description`: in tỷ số ở dạng thập phân với RoundingMode.HALF_UP và không chia cho 0.

Code hiện thực **chính sách cơ sở k=ceil(B/R)**, không cài phân phối randomized liên tục ở các phần lý thuyết trước. Mỗi quyết định online phụ thuộc vào giá hợp đồng và số thứ tự ngày sử dụng, **không phụ thuộc D**.

~~~java
import java.math.*;
import java.util.*;

public final class SkiRentalOnlineLesson {
    private SkiRentalOnlineLesson() {}

    public record Contract(long rentPerDay, long buyPrice) {
        public Contract {
            if (rentPerDay <= 0 || buyPrice <= 0) {
                throw new IllegalArgumentException(
                        "rent and purchase price must be positive");
            }
        }
    }

    public enum Action { RENT, BUY, OWN }

    public record Outcome(long days, long buyOnDay, long rentedDays,
                          boolean purchased, BigInteger onlineCost,
                          BigInteger offlineOptimal) {}

    public static long purchaseDay(Contract c) {
        if (c == null) throw new IllegalArgumentException("null contract");
        long quotient = c.buyPrice() / c.rentPerDay();
        long remainder = c.buyPrice() % c.rentPerDay();
        return quotient + (remainder == 0 ? 0 : 1);
    }

    public static Action actionForDay(Contract c, long day) {
        if (c == null || day <= 0) {
            throw new IllegalArgumentException("invalid contract or day");
        }
        long k = purchaseDay(c);
        if (day < k) return Action.RENT;
        if (day == k) return Action.BUY;
        return Action.OWN;
    }

    private static BigInteger big(long x) {
        return BigInteger.valueOf(x);
    }

    public static Outcome evaluate(Contract c, long days) {
        if (c == null || days < 0) {
            throw new IllegalArgumentException("invalid contract or horizon");
        }
        long k = purchaseDay(c);
        boolean bought = days >= k;
        long rentedDays = bought ? k - 1 : days;
        BigInteger online = big(rentedDays).multiply(big(c.rentPerDay()));
        if (bought) online = online.add(big(c.buyPrice()));
        BigInteger offline = big(days)
                .multiply(big(c.rentPerDay()))
                .min(big(c.buyPrice()));
        return new Outcome(days, k, rentedDays, bought, online, offline);
    }

    private static BigInteger exhaustiveOffline(Contract c, int days) {
        BigInteger best = big(days).multiply(big(c.rentPerDay()));
        for (int buyDay = 1; buyDay <= days; buyDay++) {
            BigInteger candidate = big(buyDay - 1L)
                    .multiply(big(c.rentPerDay()))
                    .add(big(c.buyPrice()));
            best = best.min(candidate);
        }
        return best;
    }

    private static BigInteger simulateOnline(Contract c, int days) {
        BigInteger cost = BigInteger.ZERO;
        boolean owns = false;
        for (int day = 1; day <= days; day++) {
            Action action = actionForDay(c, day);
            if (action == Action.RENT) {
                if (owns) throw new AssertionError("rent after purchase");
                cost = cost.add(big(c.rentPerDay()));
            } else if (action == Action.BUY) {
                if (owns) throw new AssertionError("duplicate purchase");
                cost = cost.add(big(c.buyPrice()));
                owns = true;
            } else if (!owns) {
                throw new AssertionError("own before purchase");
            }
        }
        return cost;
    }

    private static void check(Contract c, long days) {
        Outcome outcome = evaluate(c, days);
        BigInteger expectedOffline = big(days)
                .multiply(big(c.rentPerDay()))
                .min(big(c.buyPrice()));
        if (!outcome.offlineOptimal().equals(expectedOffline)) {
            throw new AssertionError("offline formula mismatch");
        }
        if (days <= 40) {
            BigInteger brute = exhaustiveOffline(c, (int) days);
            BigInteger simulated = simulateOnline(c, (int) days);
            if (!brute.equals(outcome.offlineOptimal())
                    || !simulated.equals(outcome.onlineCost())) {
                throw new AssertionError("oracle/simulator mismatch: "
                        + c + " days=" + days);
            }
        }

        long k = purchaseDay(c);
        if (k < 1 || outcome.buyOnDay() != k
                || outcome.purchased() != (days >= k)
                || outcome.rentedDays() != (days >= k ? k - 1 : days)) {
            throw new AssertionError("policy or state mismatch");
        }

        if (outcome.onlineCost().compareTo(outcome.offlineOptimal()) < 0) {
            throw new AssertionError("online cost below offline optimum");
        }
        if (days > 0 && outcome.onlineCost().compareTo(
                outcome.offlineOptimal().multiply(BigInteger.TWO)) >= 0) {
            throw new AssertionError("strict 2-competitive bound failed");
        }
        if (days == 0 && (!outcome.onlineCost().equals(BigInteger.ZERO)
                || !outcome.offlineOptimal().equals(BigInteger.ZERO))) {
            throw new AssertionError("zero horizon must cost zero");
        }
    }

    private static void expectInvalid(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    private static void verify() {
        int exhaustive = 0;
        for (int rent = 1; rent <= 12; rent++) {
            for (int buy = 1; buy <= 24; buy++) {
                Contract c = new Contract(rent, buy);
                for (int days = 0; days <= 40; days++) {
                    check(c, days);
                    exhaustive++;
                }
            }
        }

        Random rng = new Random(4852026L);
        int seeded = 0;
        for (int trial = 0; trial < 2500; trial++) {
            Contract c = new Contract(1L + rng.nextInt(1_000_000),
                                      1L + rng.nextInt(1_000_000));
            long days = rng.nextInt(1_000_001);
            check(c, days);
            seeded++;
        }

        long max = Long.MAX_VALUE;
        check(new Contract(1, max), max);
        check(new Contract(1, max), max - 1);
        check(new Contract(max, max), max);
        check(new Contract(max, 1), max);
        check(new Contract(2, max), max);
        check(new Contract(max, 2), 0);
        BigInteger gigantic = evaluate(new Contract(1, max), max)
                .onlineCost();
        if (gigantic.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) <= 0) {
            throw new AssertionError("BigInteger overflow defense not exercised");
        }

        expectInvalid(() -> new Contract(0, 10));
        expectInvalid(() -> new Contract(2, 0));
        expectInvalid(() -> new Contract(-3, 5));
        expectInvalid(() -> purchaseDay(null));
        expectInvalid(() -> evaluate(null, 3));
        expectInvalid(() -> evaluate(new Contract(1, 5), -1));
        expectInvalid(() -> actionForDay(new Contract(1, 5), 0));
        expectInvalid(() -> actionForDay(null, 1));

        System.out.println("Exhaustive rent/buy/horizon cases: "
                + exhaustive + " PASS");
        System.out.println("Seeded large-horizon cases: "
                + seeded + " PASS");
        System.out.println("BigInteger extremes and invalid inputs: PASS");
    }

    private static String description(Contract c, long days) {
        Outcome o = evaluate(c, days);
        String ratio = o.offlineOptimal().signum() == 0
                ? "n/a"
                : new BigDecimal(o.onlineCost()).divide(
                        new BigDecimal(o.offlineOptimal()), 4,
                        RoundingMode.HALF_UP).toPlainString();
        return "R=" + c.rentPerDay() + " B=" + c.buyPrice()
                + " D=" + days + " -> buyDay=" + o.buyOnDay()
                + ", rentals=" + o.rentedDays()
                + ", purchased=" + o.purchased()
                + ", online=" + o.onlineCost()
                + ", offline=" + o.offlineOptimal()
                + ", ratio=" + ratio;
    }

    public static void main(String[] args) {
        Contract example = new Contract(1, 5);
        System.out.println(description(example, 4));
        System.out.println(description(example, 5));
        Contract fractional = new Contract(3, 10);
        System.out.println(description(fractional, 3));
        System.out.println(description(fractional, 4));
        System.out.println(description(new Contract(4, 3), 7));
        System.out.println(description(example, 0));
        System.out.println("Day 4 action for R=1 B=5: "
                + actionForDay(example, 4));
        System.out.println("Day 5 action for R=1 B=5: "
                + actionForDay(example, 5));
        System.out.println("Day 6 action for R=1 B=5: "
                + actionForDay(example, 6));
        verify();
    }
}
~~~

Biên dịch/chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac SkiRentalOnlineLesson.java
java SkiRentalOnlineLesson
~~~

**Stdout chính xác từ lần chạy kiểm thử:**

~~~text
R=1 B=5 D=4 -> buyDay=5, rentals=4, purchased=false, online=4, offline=4, ratio=1.0000
R=1 B=5 D=5 -> buyDay=5, rentals=4, purchased=true, online=9, offline=5, ratio=1.8000
R=3 B=10 D=3 -> buyDay=4, rentals=3, purchased=false, online=9, offline=9, ratio=1.0000
R=3 B=10 D=4 -> buyDay=4, rentals=3, purchased=true, online=19, offline=10, ratio=1.9000
R=4 B=3 D=7 -> buyDay=1, rentals=0, purchased=true, online=3, offline=3, ratio=1.0000
R=1 B=5 D=0 -> buyDay=5, rentals=0, purchased=false, online=0, offline=0, ratio=n/a
Day 4 action for R=1 B=5: RENT
Day 5 action for R=1 B=5: BUY
Day 6 action for R=1 B=5: OWN
Exhaustive rent/buy/horizon cases: 11808 PASS
Seeded large-horizon cases: 2500 PASS
BigInteger extremes and invalid inputs: PASS
~~~

Các dòng `PASS` được in sau khi nhóm phép kiểm tra tương ứng đã hoàn tất; nếu vi phạm quy tắc chọn ngày, sai oracle hoặc sai hệ số cạnh tranh, chương trình ném AssertionError.

## 23. Kiểm thử vét cạn 11.808 trường hợp

Code duyệt các bộ số nguyên dương:

~~~text
R thuộc {1,2,...,12}.
B thuộc {1,2,...,24}.
D thuộc {0,1,...,40}.
~~~

Tổng số trường hợp:

~~~text
12 * 24 * 41 = 11808.
~~~

Với từng bộ (R,B,D), chạy:

1. `evaluate` dùng công thức đóng cho online và offline.
2. `simulateOnline` mô phỏng **từng ngày 1..D**, gọi đúng `actionForDay` mà không dùng horizon tương lai khi quyết định.
3. `exhaustiveOffline` thử **thuê tất cả D ngày** và thử **mua ở mọi ngày t=1..D** để tìm chi phí nhỏ nhất.
4. So kết quả từng byte số nguyên BigInteger của hai cách tính online và offline.
5. Kiểm tra số ngày thuê trước khi mua, số lần mua và hành động sau mua.
6. Kiểm tra `ONLINE>=OPT`, `ONLINE<2 OPT` cho D>0 và cả hai bằng 0 khi D=0.

Do brute offline không dùng công thức `min(DR,B)` làm cách tìm chính mà liệt kê các lịch mua, nó là một **oracle độc lập** phù hợp cho miền D nhỏ. Kết quả đã chạy thực tế: **11.808 trường hợp PASS**.

## 24. Kiểm thử 2.500 bộ chi phí và horizon có seed

Ngoài miền vét cạn nhỏ, chương trình dùng:

~~~text
Random seed: 4852026.

Số bộ: 2500.
R được chọn trong [1,1_000_000].
B được chọn trong [1,1_000_000].
D được chọn trong [0,1_000_000].
~~~

Với D lớn, code không mô phỏng từng ngày vì điều này không cần thiết; nó kiểm tra `evaluate` bằng công thức chuẩn của mô hình và các bất biến của chính sách. Với D≤40, còn chạy oracle liệt kê và mô phỏng như bộ thử vét cạn.

Kiểm thử random giúp bao phủ nhiều cấu hình B<R, B=R, B>R, tỷ số B/R nguyên và không nguyên, hành trình dừng trước/sau ngày k. Kết quả **2.500 bộ PASS**.

**Lưu ý:** Random ở đây chỉ để **tạo test case**. Policy ski rental vẫn **tất định**, nên kết quả quyết định trên cùng R,B và ngày t không thay đổi theo seed.

## 25. Kiểm thử số nguyên rất lớn và input lỗi

Các ca riêng gồm:

~~~text
R=1, B=Long.MAX_VALUE, D=Long.MAX_VALUE.
R=1, B=Long.MAX_VALUE, D=Long.MAX_VALUE−1.
R=Long.MAX_VALUE, B=Long.MAX_VALUE,
    D=Long.MAX_VALUE.
R=Long.MAX_VALUE, B=1, D=Long.MAX_VALUE.
R=2, B=Long.MAX_VALUE, D=Long.MAX_VALUE.
R=Long.MAX_VALUE, B=2, D=0.
~~~

Đặc biệt trường hợp R=1, B=D=Long.MAX_VALUE có ONLINE=2B−1 lớn hơn `Long.MAX_VALUE`, nên nó xác nhận phép tính BigInteger thật sự cần thiết. Bảo đảm online<2 OPT vẫn được xác nhận bằng phép nhân BigInteger, không dùng double.

Mã cũng từ chối `R<=0`, `B<=0`, hợp đồng null, horizon âm, ngày hành động bằng 0 và lời gọi policy với hợp đồng null bằng **IllegalArgumentException**.

Đầu vào hợp lệ D=0 không tạo ra chi phí. Không nên thử lấy tỷ số ONLINE/OPT trong trường hợp này.

## 26. Độ phức tạp của các phương pháp trong code

| Phương pháp | Thời gian | Bộ nhớ phụ | Ghi chú |
| --- | --- | --- | --- |
| `purchaseDay` | O(1) thao tác số học | O(1) | Tính ceil(B/R) bằng chia/phần dư |
| `actionForDay` | O(1) | O(1) | Không cần horizon |
| `evaluate` | O(1) thao tác số học | O(1) đối tượng kích thước giới hạn | Không lặp D ngày |
| `simulateOnline` | O(D) | O(1) ngoài kết quả | Oracle mô phỏng cho test D nhỏ |
| `exhaustiveOffline` | O(D) | O(1) ngoài kết quả | Duyệt mọi ngày mua để kiểm tra |
| `verify` | Phụ thuộc số bộ test | Phụ thuộc dữ liệu test | Không thuộc chi phí chính sách online |

Khi phân tích ở mô hình RAM, mỗi thao tác trên những số nguyên có độ rộng cố định được coi O(1). BigInteger/BigDecimal có chi phí phụ thuộc số bit và số chữ số, nhưng trong code đầu vào đều là **long** nên kết quả của một lần evaluate chỉ cần nhiều nhất cỡ **128 bit**; kích thước biểu diễn được chặn và tính toán vẫn là hằng số theo D.

Chi phí đời thực là số tiền thuê/mua, **không phải độ phức tạp thời gian chạy Java**. Hai khái niệm này hoàn toàn khác nhau: thuật toán đánh giá O(1) có thể tạo chi phí mua rất lớn, nhưng vẫn cạnh tranh tốt so với OPT offline.

## 27. Sai lầm thường gặp

1. **Dùng D trong hàm ra quyết định**, vô tình giải bài offline.
2. **Mua ngay dù D=0**, sai mô hình chỉ hành động khi có nhu cầu.
3. **Tính thêm tiền thuê ở ngày mua**, trong khi đã mua ở đầu ngày đó.
4. **Dùng floor(B/R) nhưng vẫn áp trực tiếp chứng minh dành cho ceil**, không kiểm tra ngưỡng.
5. **Kết luận ceil(B/R) tối ưu mọi trường hợp R,B**, sai khi B/R không nguyên trong mô hình ngày rời rạc.
6. **Quên B≤R**, dù mua ngày 1 mới là tối ưu.
7. **Coi thuật toán luôn thuê là c-competitive với c cố định**, sai khi D tăng tùy ý.
8. **Tính OPT bằng lịch thuê rồi mua với thông tin online**, làm lẫn nghĩa offline.
9. **Quên phương án mua ở ngày 1 trong offline**, khiến OPT bị đánh giá lớn hơn thực tế.
10. **Dùng tỷ số với OPT=0**, gặp 0/0 ở D=0.
11. **Nhầm competitive ratio là sai số cộng 2 đơn vị**, thay vì nhân với OPT.
12. **Phân tích tỷ số trung bình trên dữ liệu test rồi kết luận worst-case**, không đúng loại bảo đảm.
13. **Suy luận từ chiến lược randomized liên tục sang ngày rời rạc bằng làm tròn mà không chứng minh**.
14. **Không phân biệt đối thủ oblivious và adaptive** khi nói cận kỳ vọng.
15. **Cho rằng randomized luôn đạt e/(e−1) ở mỗi lần chạy**, dù đó là cận kỳ vọng.
16. **Dùng Math.ceil((double)B/R) cho long cực lớn**, nguy cơ mất chính xác vì double.
17. **Tính (B+R−1)/R trong long cực lớn**, có thể tràn ở phép cộng.
18. **Tính D*R trong long rồi mới đổi sang BigInteger**, tràn đã xảy ra trước khi đổi.
19. **Dùng một vòng lặp D ngày chỉ để tính tổng tiền**, gây thời gian vô ích khi D cực lớn.
20. **Dùng một ngày mua đã quyết định nhưng không kiểm tra hôm đó có còn sử dụng hay không**, làm phát sinh mua không cần thiết.
21. **Mua nhiều lần** do không theo dõi trạng thái đã mua.
22. **Trả thuê sau khi đã mua**, làm chi phí tăng sai.
23. **Không kiểm tra R,B dương**, dẫn tới chia 0 hoặc mô hình có tiền âm.
24. **Tính tỷ số bằng chia nguyên**, ví dụ 9/5 thành 1 thay vì 1,8.
25. **Dùng chiến lược này khi có giá bán lại hay chi phí bảo trì**, dù công thức OPT đã thay đổi.
26. **Nhầm hành trình D với số ngày đã thuê**, vì khi mua số ngày thuê chỉ là k−1.
27. **Gọi bảo đảm c<2 cho mọi B,R với một c cố định độc lập tham số**, dù khi B/R lớn tỷ số có thể tiến sát 2.
28. **Không mô tả thời điểm thanh toán**, khiến công thức ONLINE lệch đúng một ngày thuê.
29. **Cho rằng policy dùng random vì test dùng Random**, nhầm thuật toán với bộ sinh dữ liệu kiểm thử.
30. **Không đối chiếu với oracle liệt kê lịch mua** trên D nhỏ, dễ bỏ lỗi off-by-one.

## 28. Bài tập tự luyện

**Bài 1 — Offline:** với R=2,B=7, tính OPT(D) cho D=0..7. Tại D nào offline chuyển từ thuê sang mua?

**Bài 2 — Online cơ sở:** với R=2,B=7, tính k=ceil(B/R), lập lịch RENT/BUY/OWN cho D=3,4,8.

**Bài 3 — Ví dụ chuẩn:** với R=1,B=5, tính ONLINE và OPT cho D=4 và D=5; giải thích vì sao tỷ số nhảy từ 1 lên 9/5.

**Bài 4 — Chứng minh:** đặt k=ceil(B/R); chứng minh (k−1)R<B≤kR rồi dùng hai trường hợp D<k, D≥k suy ra ONLINE<2OPT khi D>0.

**Bài 5 — Ngưỡng rời rạc:** với R=3,B=10, tính W(3) và W(4); vì sao mua ngày 3 tốt hơn về tỷ số tệ nhất dù k cơ sở là 4?

**Bài 6 — B≤R:** đặt R=8,B=5; chứng minh mua ngày 1 tối ưu cho mọi D≥1 và D=0 vẫn không trả phí.

**Bài 7 — Ngưỡng cố định:** với B>R, suy ra công thức W(t)=[B+(t−1)R]/min(tR,B) của chính sách mua ngày t và chứng minh tối ưu trong họ threshold chỉ cần xét floor hoặc ceil của B/R.

**Bài 8 — Adversary:** mô tả horizon làm chính sách thuê mãi và mua ngay tệ; so với chính sách cân bằng chi phí.

**Bài 9 — Competitive vs approximation:** phát biểu vì sao ski rental không thể giải bằng việc đưa toàn bộ D vào quyết định online.

**Bài 10 — Kiểm thử:** viết brute-force offline liệt kê ngày mua 1..D và phương án không mua, so với min(DR,B).

**Bài 11 — Mô phỏng:** chạy actionForDay từng ngày và so tổng với công thức ONLINE(D) cho D≤50 và nhiều R,B.

**Bài 12 — Overflow:** với R=1,B=D=Long.MAX_VALUE, tính ONLINE=2B−1 bằng BigInteger và kiểm tra bất đẳng thức với OPT.

**Bài 13 — Randomized liên tục:** thay mật độ vào công thức kỳ vọng và kiểm chứng e/(e−1), giải thích vai trò của đối thủ oblivious.

**Bài 14 — Discount:** giả sử giá mua B giảm ở ngày 10. Xác định bước nào của chứng minh k=ceil(B/R) không còn áp dụng nguyên dạng.

**Bài 15 — Chi phí thuê thay đổi:** nếu R_t khác nhau theo ngày, đề xuất một quy tắc dựa trên tổng chi phí thuê đã trả và chỉ ra những yếu tố cần chứng minh lại.

**Bài 16 — Thực tế:** chọn một dịch vụ thuê hay mua và liệt kê giả thiết của ski rental không còn đúng (bảo trì, lãi suất, bán lại, nhu cầu không theo ngày). Đừng áp cận 2 nếu chưa điều chỉnh mô hình.

## 29. Checklist triển khai và tổng kết

Một lời giải ski rental trực tuyến cần đáp ứng:

- Giá **R,B>0**, D≥0 và D không biết khi ra quyết định.
- Quy ước **BUY ở đầu ngày mua**, nên không thuê trong chính ngày ấy.
- Policy chỉ dùng `currentDay` cùng R,B, **không dùng D**.
- Dùng k=ceil(B/R), tính bằng **chia nguyên và phần dư** tránh overflow.
- Nếu D<k, chỉ thuê D ngày và trùng OPT.
- Nếu D≥k, thuê k−1 ngày rồi mua; OPT=B.
- Suy ra với D≥1, **OPT≤ONLINE<2OPT**.
- Với D=0, cả hai bằng 0 và tỷ số không xác định.
- Khi B/R không nguyên, có thể **so ngưỡng floor và ceil** nếu tối ưu worst-case ratio trong họ threshold, không khẳng định ceil luôn tối ưu.
- Randomized continuous ratio e/(e−1) là phần mở rộng có **giả thiết mô hình riêng**.
- Khi chi phí lớn, dùng BigInteger cho tổng tiền và kiểm tra cận bằng phép so số nguyên.
- Kiểm thử có oracle độc lập thử **mọi ngày mua** cho horizon nhỏ, bên cạnh mô phỏng online từng ngày.

**Kết luận:** Ski rental dạy cách ra quyết định **mà không biết tương lai** và cách đánh giá bằng **competitive ratio**, thay vì so nghiệm trên một đầu vào đã biết đầy đủ. Chính sách thuê trước tới sát mức giá mua rồi mua nếu vẫn cần sử dụng có bảo đảm mạnh, rất dễ triển khai và chứng minh bằng hai trường hợp D<k và D≥k. Điểm quan trọng nhất không phải nhớ một công thức rời rạc cụ thể, mà là **giữ đúng thông tin online, thời điểm trả tiền và cận so với OPT offline**. Những kiến thức này là nền tảng cho các thuật toán trực tuyến về mua tài nguyên, cấp phát năng lực và quản lý quyết định dưới tương lai chưa biết.
