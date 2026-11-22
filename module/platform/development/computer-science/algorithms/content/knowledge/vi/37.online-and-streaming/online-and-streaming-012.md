# Thống kê thứ tự gần đúng và đánh đổi độ chính xác–bộ nhớ

**Thống kê thứ tự (order statistics)** trả lời câu hỏi phần tử thứ k theo thứ tự tăng, median, p90, p95, p99 và các quantile khác. Trong mô hình offline, ta giữ toàn bộ dữ liệu rồi sắp xếp hoặc chạy thuật toán chọn phần tử. Nhưng với **luồng dữ liệu (data stream)** dài, liên tục, không thể đọc lại, ta thường không đủ RAM để lưu toàn bộ n quan sát.

Bài **“Thống kê thứ tự gần đúng và đánh đổi độ chính xác–bộ nhớ”** thuộc nhóm **Trực tuyến và luồng** của Computer Science Algorithms. Bài dạy cách giải **approximate quantile**: chọn cách đo sai số theo thứ hạng thay vì giá trị, quản lý hai tham số ε (độ chính xác) và δ (xác suất thất bại), dùng **Greenwald–Khanna (GK)** và **reservoir sampling**, chứng minh bất biến, phân tích bộ nhớ và CPU, so sánh với KLL/t-digest, xử lý giá trị trùng, dữ liệu đuôi hiếm và các tình huống ngoài mô hình insert-only.

Mã Java 17+ độc lập cuối bài triển khai một **GK-style summary dạng nén kề** và một **reservoir sample**, kèm oracle exact độc lập để kiểm thử sai số rank. Đã kiểm thử thành công **9.841 luồng vét cạn**, **1.000 luồng có seed** và hai trường hợp **n=10.000**.

## 1. Phát biểu order statistic và quantile

Sắp n quan sát theo thứ tự không giảm:

~~~text
x_(1) <= x_(2) <= ... <= x_(n).
~~~

Order statistic thứ r là x_(r), r từ 1 tới n. Có nhiều định nghĩa median/quantile trong thống kê; bài này chọn **nearest-rank**:

~~~text
r(q) = max(1, ceil(q*n)), 0<=q<=1.
Q(q) = x_(r(q)) khi n>=1.
~~~

Với sorted [0,1,2,3,4,5,6,7,8,9], n=10, p50 tương ứng rank 5, trả **4**. Không nhầm kết quả này với median kiểu trung bình hai điểm giữa bằng 4,5. Với n=0, quantile không xác định; API trong bài báo lỗi khi truy vấn dãy rỗng.

p99 là giá trị có ít nhất 99% quan sát không lớn hơn nó theo quy ước đã chọn. Bản chất quantile là **giá trị theo vị trí trong thứ tự**, không phải trung bình hay tổng.

## 2. Tại sao cần xấp xỉ khi xử lý streaming?

Nếu có n giá trị trong RAM, sort tốn O(n log n), sau đó trả nhiều quantile nhanh. Quickselect có thể lấy một order statistic trung bình O(n) nhưng cũng cần quyền truy cập dữ liệu.

Trong mô hình streaming, dữ liệu đi qua một lần:

~~~text
add(x1)
add(x2)
...
add(xn)
query(0.50)
query(0.95)
query(0.99)
~~~

Ta muốn **bộ nhớ ít phụ thuộc n**, cập nhật nhanh và hỗ trợ nhiều truy vấn. Đối với miền giá trị tùy ý và thứ tự đến bất kỳ, exact median trên một lượt streaming thường buộc phải giữ lượng thông tin lớn theo n trong trường hợp xấu. Một **sketch** tóm tắt dữ liệu giúp chuyển chi phí bộ nhớ sang một **sai số kiểm soát được**.

Đây là đánh đổi thuật toán, khác với việc giảm độ chính xác của kiểu dữ liệu số thực; giá trị lưu trong sketch vẫn có thể là long nguyên chính xác.

## 3. Rank error không phải value error

Với mục tiêu rank r=ceil(qn) và ε>0, một sai số rank cỡ εn cho phép trả phần tử tại vị trí trong:

~~~text
[r-ceil(epsilon*n), r+ceil(epsilon*n)]
sau khi cắt về [1,n].
~~~

Ví dụ n=1000, ε=0,01 thì ngân sách rank khoảng ±10 **vị trí**, không phải sai số giá trị 1%. Một phần tử có rank chênh chỉ 1 so với target vẫn có thể khác giá trị rất lớn nếu dữ liệu có outlier hoặc khoảng trống trong phân bố.

Ví dụ dãy gần 100 giá trị nhỏ và một giá trị cuối **10^12**: rank n−1 và n gần nhau nhưng chênh giá trị cực lớn. Không tuyên bố ε=0,01 đồng nghĩa sai số tuyệt đối hay tương đối giá trị dưới 1%.

## 4. Giá trị trùng tương ứng khoảng thứ hạng

Khi nhiều quan sát bằng nhau, một **giá trị v có thể chiếm nhiều vị trí**. Định nghĩa:

~~~text
L(v)=1+count(x_i<v).
U(v)=count(x_i<=v).
Khoảng rank có thể có của v: [L(v),U(v)].
~~~

Ví dụ [1,2,2,2,2,8,10] có giá trị 2 xuất hiện từ rank 2 tới rank 5. Tại target r=4, v=2 là exact quantile dù count(x≤2)=5.

Vì vậy bài kiểm thử approximate rank phải xem khoảng [L(v),U(v)] **giao** vùng cho phép quanh r hay không. Nếu chỉ lấy U(v) làm rank duy nhất, test có thể báo FAIL cho một đáp án hoàn toàn hợp lệ.

## 5. CDF và hai kiểu truy vấn

CDF thực nghiệm:

~~~text
F_n(v)=count(x_i<=v)/n.
~~~

**Rank/CDF query** đưa v, muốn tỷ lệ hoặc số quan sát không vượt quá v. **Quantile query** đưa q, muốn một giá trị ở vị trí tương ứng q. Đây là hai chiều liên quan nhưng không đồng nhất; không phải mọi sketch đều hỗ trợ hai API với cùng bảo đảm.

Nếu ứng dụng tính p50, p90, p99 cùng lúc, một sketch được thiết kế cho mọi quantile có thể phục vụ cả ba truy vấn mà không cần lưu ba bộ dữ liệu riêng.

## 6. Hai loại bảo đảm: ε và δ

Một tóm tắt **tất định** có thể bảo đảm với mọi luồng hợp lệ rằng trả rank trong ±εn. Một tóm tắt **ngẫu nhiên** còn có xác suất thất bại δ:

~~~text
Deterministic: rank_error <= epsilon*n
               trên mọi input hợp lệ.

Randomized: P(rank_error > epsilon*n)
            <= delta.
~~~

Khi dùng randomized cần nêu rõ bảo đảm cho một q cố định hay đồng thời nhiều q, các giả thiết lấy mẫu, và xác suất được xét trên nguồn random nội bộ. Độ lệch thực tế có thể nhỏ hơn cận, nhưng không được lấy một bộ test ngẫu nhiên không lỗi để tuyên bố xác suất thất bại bằng 0.

## 7. Reservoir sampling giữ k mẫu

Reservoir sampling R giữ một mẫu nhiều nhất k quan sát từ luồng mà **không cần biết trước n**. Sau khi xem n≥k vị trí, mỗi quan sát có cùng xác suất k/n nằm trong mẫu.

~~~text
seen=0
sample=[]
for mỗi giá trị x đến:
    seen++
    if sample.size < k:
        sample.add(x)
    else:
        j = random integer uniform in [0,seen-1]
        if j<k:
            sample[j]=x
~~~

Khi n≤k, mẫu chứa toàn bộ n quan sát và quantile trên mẫu là exact. Khi n>k, bộ nhớ **O(k)**. Để truy vấn, sort **bản sao** của mẫu k giá trị và chọn nearest-rank. Đáp án mang sai số lấy mẫu ngẫu nhiên, không phải bảo đảm tất định trên mỗi lần chạy.

## 8. Chứng minh reservoir chọn đều từng quan sát

Với n>k, quan sát mới ở vị trí n được giữ nếu số j thuộc [0,k−1], xác suất k/n. Một quan sát cũ có xác suất được giữ ở bước n−1 là k/(n−1); nếu đang được giữ, nó chỉ bị thay khi j trúng đúng vị trí của nó, xác suất 1/n.

~~~text
P(điểm cũ còn được giữ)
 = (k/(n-1)) * (1-1/n)
 = k/n.
~~~

Suy ra mọi **vị trí xuất hiện** được lấy mẫu đồng đều, kể cả khi nhiều vị trí có cùng giá trị. Đây là một chứng minh, không phải mẹo ngẫu nhiên khó kiểm chứng.

Java 17 hỗ trợ `Random.nextLong(bound)` để lấy j theo seen long. Chỉ ép j về int khi j<k, vì mẫu của Java được đánh địa chỉ bằng int. Không ép n về int trước khi lấy mẫu nếu stream có thể vượt 2^31 quan sát.

## 9. Mối quan hệ giữa k và độ tin cậy

Gọi F_sample(v) là tỷ lệ mẫu có giá trị ≤v. Với một ngưỡng cố định trên một tập hữu hạn, mẫu đồng đều **không hoàn lại** có cận tập trung kiểu Hoeffding:

~~~text
P(|F_sample(v)-F_n(v)|>eta)
    <= 2*exp(-2*k*eta^2).
~~~

Có nhiều nhất n ngưỡng tại các giá trị quan sát; dùng union bound cho:

~~~text
P(sup_v |F_sample(v)-F_n(v)|>eta)
    <= 2*n*exp(-2*k*eta^2).
~~~

Một điều kiện đủ bảo thủ để xác suất trên không quá δ:

~~~text
k >= ln(2*n/delta)/(2*eta^2).
~~~

Các định lý mạnh hơn có thể cho cận tốt hơn và ít phụ thuộc n, nhưng cách suy luận trên đã thể hiện bản chất: giảm sai số η xuống một nửa đòi cỡ **bốn lần số mẫu** ở mức bảo đảm tương tự.

Quantile từ CDF mẫu còn chịu bước nhảy 1/k. Nên diễn giải rank-error gần **(eta+1/k)n** trong biến cố CDF tốt, không đánh đồng một độ lệch CDF với chênh giá trị của quantile.

## 10. Trường hợp p99 và dữ liệu đuôi hiếm

Nếu chỉ 1% của n=10.000 quan sát thuộc vùng đuôi cao nhất, lấy reservoir k=4 có xác suất bỏ sót cả vùng đuôi là:

~~~text
C(9900,4)/C(10000,4)
    ≈ (0.99)^4
    ≈ 0.9606.
~~~

Gần 96% mẫu bốn phần tử bỏ qua 1% đuôi cao nhất. Vì vậy một reservoir rất nhỏ không đáng tin để ước lượng p99, dù median có vẻ tốt. Nếu cần p99.9, yêu cầu về độ chính xác rank còn nghiêm ngặt hơn.

Một sketch có sai số rank ±1% n cũng có thể sai lệch từ p98 tới p100 khi đo p99; giá trị p100 có thể rất lớn so với p99. Do đó cần chọn ε dựa trên **số hạng sai lệch được phép**, không chỉ độ hấp dẫn của một con số 1%.

## 11. Greenwald–Khanna và các entry (v,g,delta)

Tóm tắt kiểu **Greenwald–Khanna (GK)** giữ các entry theo giá trị không giảm:

~~~text
(v_i, g_i, delta_i)
~~~

Trong đó v_i là một giá trị từng xuất hiện; g_i là mức tăng tối thiểu của lower-rank so với mốc trước; delta_i là độ bất định thêm ở upper-rank.

Từ các entry:

~~~text
r_min(v_i)=sum_(j<=i) g_j.
r_max(v_i)=r_min(v_i)+delta_i.
~~~

Nhờ giữ **khoảng rank** thay vì mọi quan sát, sketch có thể xóa các mốc trung gian mà không đánh mất toàn bộ thông tin thứ tự.

Trong mã có một lớp `GK` với nguyên lý entry, chèn theo thứ tự, nén kề và truy vấn rank. Đây là **bản demo GK-style**, không phải bản GK production triển khai đầy đủ chính sách nén theo band.

## 12. Chèn và nén các entry

Khi một x đến, tăng n, tìm vị trí `upper_bound` trong danh sách entry, chèn (x,1,delta). Nếu x mới nằm ở đầu/cuối thì delta=0. Nếu x ở giữa, bản code dùng:

~~~text
delta=max(0,floor(2*epsilon*n)-1).
~~~

Để nén hai entry kề nhau A=(v_i,g_i,delta_i) và B=(v_next,g_next,delta_next), bản Java chỉ bỏ A nếu:

~~~text
g_i+g_next+delta_next
    <= floor(2*epsilon*n).
~~~

Sau đó dồn g_i vào g_next, giữ delta_next; **sum(g_i) vẫn bằng n**. Để giữ đúng minimum và maximum, code không xóa entry đầu hay entry cuối.

Cơ chế này cho thấy vì sao ta giảm bộ nhớ bằng cách chấp nhận **độ bất định hạng**. Không được bỏ một entry tùy ý hoặc sửa delta mà không giữ bất biến; một phép nén sai có thể cho kết quả sai dù tất cả value đều nằm trong dữ liệu gốc.

## 13. Truy vấn GK với cận rank

Với q∈[0,1], target rank là max(1,ceil(qn)), và tolerance=εn. Khi quét entry, cộng g để tính r_min, rồi r_max=r_min+delta.

Bản code giữ entry trước đó. Khi entry hiện tại thỏa:

~~~text
r_max(current) > target+epsilon*n
~~~

trả về `previous.value`. Nếu không entry nào vượt ngưỡng, trả entry cuối. Với q=0 hoặc q=1, trả trực tiếp minimum/maximum.

Trực giác: upper-rank của entry trước không vượt ngưỡng trên, và chênh giữa upper-rank entry hiện tại với lower-rank entry trước được kiểm soát bởi ngân sách khoảng 2εn, nên entry trước vẫn nằm gần target. Trường hợp n rất nhỏ, chưa có nén và summary còn exact.

Oracle kiểm tra rank ở **vùng ±ceil(εn)** và xét cả khoảng khi giá trị trùng. Không buộc GK trả đúng một giá trị exact nếu một giá trị khác vẫn đáp ứng hợp đồng rank.

## 14. Cận bộ nhớ GK chuẩn và giới hạn của code

Với chính sách nén đầy đủ, lý thuyết GK chuẩn có thể đạt số entry cỡ:

~~~text
O((1/epsilon)*log(epsilon*n+1)).
~~~

Đây là cận **cho thuật toán GK có chính sách nén được chứng minh**, không phải cận đã được chứng minh cho bất kỳ biến thể nén ArrayList nào.

Bản demo dùng ArrayList, chèn giữa và nén mỗi lần add; nó ưu tiên **dễ đọc và dễ kiểm tra**. Trong lần chạy Java với n=10.000, ε=0,01, kết quả là:

~~~text
Dãy tăng 0..9999: 69 entry.
Dãy hằng 7 lặp 10000 lần: 69 entry.
~~~

Con số 69 là **thực nghiệm** trên hai luồng cụ thể; không coi đó là memory bound tổng quát cho mọi luồng n=10.000. Nếu cần bảo đảm heap cứng, hãy dùng phiên bản GK/KLL được kiểm định và đo trên dữ liệu thực.

## 15. Chi phí cập nhật và truy vấn

Với s entry đang giữ:

| Thao tác | Thời gian trong bản demo | Bộ nhớ |
| --- | --- | --- |
| GK tìm chỗ chèn | O(log s) so sánh | O(1) |
| GK ArrayList insert | O(s) trường hợp xấu | O(s) lưu entry |
| GK compress | Có thể tới O(s²) do nhiều lần ArrayList.remove | O(s) |
| GK quantile | O(s) quét entry | O(1) phụ |
| Reservoir add | O(1) kỳ vọng | O(k) |
| Reservoir sampleQuantile | O(k log k) để copy/sort | O(k) phụ |
| Exact sort | O(n log n) | O(n) |

Không nói mọi `GK.add` của **bản code này** là O(log s) chỉ vì dùng binary search. `ArrayList.add/remove` phải dịch nhiều phần tử. Các cài đặt tối ưu có cấu trúc/nén khác để cải thiện throughput.

Reservoir tốn k giá trị cố định, còn GK có s entry tùy n, ε và phân bố luồng. Tỷ lệ bộ nhớ thực tế phải đo bằng **byte heap**, không phải chỉ số tuple: object Entry, reference trong ArrayList và Long boxing có overhead.

## 16. Các sketch khác: KLL và t-digest

KLL là họ quantile sketch dùng compactors với lựa chọn ngẫu nhiên và có bảo đảm thống kê phù hợp khi triển khai đúng; được dùng cho nhiều truy vấn phân vị và một số thiết kế mergeable.

t-digest gom những centroid đại diện các nhóm giá trị, thường có hiệu quả thực nghiệm tốt cho tails nhưng chất lượng và bảo đảm worst-case phụ thuộc bản triển khai/giả thiết. Không tự gán một cận tất định kiểu GK cho t-digest.

Khi chọn cấu trúc phải nhìn toàn bộ yêu cầu: rank-error hay value-error, muốn deterministic hay probabilistic, bao nhiêu query, thời gian ingest, memory, có merge nhiều shard, timestamp hay delete không. **Tên thuật toán** không thay thế thông số sai số và chứng minh.

## 17. Ví dụ 10 quan sát đã chạy Java

Luồng đầu vào:

~~~text
7,1,9,3,5,2,8,4,6,0.
~~~

Sort làm oracle:

~~~text
0,1,2,3,4,5,6,7,8,9.
~~~

Chọn ε=0,10, reservoir capacity=4, seed=494. Chương trình đo GK giữ 6 entry, reservoir giữ 4 mẫu.

| q | Target rank | Exact | GK-style | Reservoir |
| ---: | ---: | ---: | ---: | ---: |
| 0,25 | 3 | 2 | 3 | 5 |
| 0,50 | 5 | 4 | 5 | 6 |
| 0,75 | 8 | 7 | 7 | 7 |

Vì εn=1, GK trả 3 ở q25 (rank4 so với target3) và trả 5 ở q50 (rank6 so với target5) đều **đạt sai số rank**. Không gọi đó là lỗi chỉ vì giá trị không bằng exact.

Reservoir q25 trả 5 (rank6) lệch ba vị trí; k=4 không có bảo đảm tất định ±1 rank. Đây là một ví dụ tốt về khác biệt giữa hai loại hợp đồng.

## 18. Cài oracle đúng cho giá trị trùng

Bộ test của bài giữ một List<Long> đầy đủ **chỉ trong kiểm thử**, không phải trong sketch chính. Với câu trả `answer`, oracle tính:

~~~text
less=count(x<answer).
leq=count(x<=answer).
actual rank interval=[less+1,leq].

target=max(1,ceil(q*n)).
budget=ceil(epsilon*n).

PASS nếu hai khoảng:
[less+1,leq] và
[target-budget,target+budget]
có giao nhau.
~~~

Đồng thời kiểm tra answer là một giá trị có thật trong input và các entry GK có `g>0`, `delta>=0`, thứ tự v không giảm và sum(g)=n.

Nếu test chỉ so `answer==exactQuantile`, nó đã vô tình biến bài approximate thành exact. Nếu chỉ so count(x≤answer), nó không xử lý trường hợp nhiều giá trị trùng.

## 19. Kiểm thử vét cạn 9.841 luồng

Chương trình sinh mọi dãy từ bảng giá trị {-1,0,1}, độ dài L từ 0 tới 8. Tổng:

~~~text
sum_(L=0)^8 3^L
    = (3^9-1)/2
    = 9841.
~~~

Mỗi luồng được thử với **bốn mức ε**: 0,05; 0,10; 0,20; 0,35. Với luồng không rỗng, test hỏi từng rank trong 1..n cùng q=0,0,01,0,25,0,5,0,75,0,99,1. Mọi lần add đều kiểm tra bất biến entry.

Dữ liệu bao phủ các trường hợp lặp giá trị, tăng/giảm, đảo thứ tự, all-equal, gần minimum/maximum, và luồng rỗng. Kết quả đã quan sát trong Java: **9.841 luồng PASS** ở các mức ε được kiểm tra.

## 20. Kiểm thử ngẫu nhiên và stress 10.000 quan sát

Bộ thứ hai dùng `Random(4942026L)` để sinh **1.000 luồng** dài 0..160, luân phiên các mẫu giá trị:

- Tăng dần.
- Giảm dần.
- Nhiều phần tử trùng trong miền rất nhỏ.
- Số nguyên long ngẫu nhiên.
- Số nguyên rải trong miền vừa.

Mỗi luồng được so với oracle rank-window. Kết quả: **1.000 PASS**.

Hai luồng 10.000 quan sát gồm 0..9999 tăng dần và một giá trị 7 lặp 10.000 lần. Với ε=0,01, mỗi summary giữ **69 entry** trong lần chạy. Trên luồng tăng, test hỏi 101 giá trị q=0,0,01,...,1 và xác minh rank window; trên luồng hằng, q50 phải trả 7.

Các kết quả PASS là **thực nghiệm đã chạy**, không thay thế chứng minh bộ nhớ/khả năng merge worst-case.

## 21. Sai số, bytes và chọn epsilon thực tế

Nếu có 5.000.000 quan sát và chấp nhận rank-error tối đa 5.000, cần ε≤0,001. Nếu chấp nhận tối đa 500, cần ε≤0,0001.

~~~text
epsilon = rank_budget / expected_N.
5000 / 5000000 = 0.001.
500 / 5000000 = 0.0001.
~~~

Cần chọn thêm δ khi phương pháp random. Sau đó đo memory trong **bytes thực**, CPU cho mỗi add và thời gian query. Một summary giữ 100 entry Java không chỉ dùng 100×8 bytes vì còn metadata và overhead cấp phát.

Nếu dùng p99 cho SLA, cần xem **chênh lệch giá trị** khi dịch 500 hoặc 5.000 rank trong vùng đuôi, không chỉ nhìn con số ε.

## 22. Cửa sổ trượt, dữ liệu có trọng số và gộp sketch

Các lớp trong demo là **insert-only**. Chúng không có `delete`, `update`, timestamps, sliding-window query hay `merge`.

Đối với p99 trong 10 phút gần nhất, reservoir toàn bộ lịch sử là sai mô hình vì mẫu không ưu tiên dữ liệu mới. Với GK, không thể ghép hai danh sách entry đã nén bằng concat/sort và cho rằng invariant còn giữ; cần thuật toán merge đã được chứng minh.

Với weighted quantile, mỗi quan sát có trọng số w, rank phải tính theo **tổng trọng số** thay vì số phần tử. Mã nhận `long value` với mỗi quan sát trọng số 1 nên không giải quyết bài weighted.

Công nghệ nên chọn theo luồng thật: chỉ thêm, cửa sổ trượt, xóa/sửa, hay dữ liệu đến phân tán nhiều máy.

## 23. Trường hợp biên và số học

GK và Reservoir yêu cầu epsilon/capacity hợp lệ. GK từ chối epsilon≤0, epsilon≥0,5 hoặc NaN/Infinity; reservoir từ chối k≤0. Query q phải hữu hạn và thuộc [0,1]. Input rỗng không thể trả quantile.

Giá trị long âm/dương và cực trị 64-bit đều được so trực tiếp, không dùng cách so kiểu `a-b` có thể overflow. Bộ đếm n là long; code từ chối tăng khi đã đạt Long.MAX_VALUE.

Khi n lớn vượt vùng 2^53, việc nhân q*n trong double có thể mất hạng đơn vị; nếu cần production cho stream cực lớn, cần kiểm soát chính xác hơn phép tính rank, không mặc định demo Java đủ an toàn cho mọi n long. Khi dữ liệu double có NaN, cũng cần quy ước so sánh rõ ràng; demo dùng long để tránh tình huống này.

## 24. Java 17+ hoàn chỉnh

Lưu mã sau thành **StreamingOrderStatistics.java**. `GK.add` chèn và nén entry; `GK.quantile` trả phân vị gần đúng; `Reservoir.add` lấy mẫu một lượt; `Reservoir.sampleQuantile` copy-sort mẫu. `exactQuantile` và `assertRankWindow` là oracle kiểm thử độc lập, **không nằm trong hoạt động chính của sketch**.

~~~java
import java.util.*;

public final class StreamingOrderStatistics {
    private StreamingOrderStatistics() {}

    public static final class GK {
        private static final class Entry {
            final long value;
            long g;
            final long delta;
            Entry(long value, long g, long delta) {
                this.value = value; this.g = g; this.delta = delta;
            }
        }

        private final double epsilon;
        private final ArrayList<Entry> entries = new ArrayList<>();
        private long count;

        public GK(double epsilon) {
            if (!(epsilon > 0 && epsilon < 0.5)
                    || !Double.isFinite(epsilon)) {
                throw new IllegalArgumentException("epsilon must be in (0,0.5)");
            }
            this.epsilon = epsilon;
        }

        private long threshold() {
            return (long) Math.floor(2.0 * epsilon * count);
        }

        public void add(long value) {
            if (count == Long.MAX_VALUE) {
                throw new IllegalStateException("count overflow");
            }
            count++;
            int left = 0, right = entries.size();
            while (left < right) {
                int middle = (left + right) >>> 1;
                if (entries.get(middle).value <= value) {
                    left = middle + 1;
                } else {
                    right = middle;
                }
            }
            int index = left;
            long delta = (index == 0 || index == entries.size())
                    ? 0 : Math.max(0, threshold() - 1);
            entries.add(index, new Entry(value, 1, delta));
            compress();
        }

        private void compress() {
            long limit = threshold();
            for (int i = entries.size() - 2; i >= 1; i--) {
                Entry a = entries.get(i);
                Entry b = entries.get(i + 1);
                if (a.g + b.g + b.delta <= limit) {
                    b.g += a.g;
                    entries.remove(i);
                }
            }
        }

        public long count() { return count; }
        public int retainedTuples() { return entries.size(); }

        public long quantile(double phi) {
            if (!Double.isFinite(phi) || phi < 0 || phi > 1) {
                throw new IllegalArgumentException("phi must be in [0,1]");
            }
            if (count == 0) throw new IllegalStateException("empty summary");
            if (phi == 0) return entries.get(0).value;
            if (phi == 1) return entries.get(entries.size()-1).value;
            long target = Math.max(1, Math.min(count,
                    (long)Math.ceil(phi*count)));
            double tolerance = epsilon * count;
            long rankMin = 0;
            Entry previous = entries.get(0);
            for (Entry entry : entries) {
                rankMin += entry.g;
                long rankMax = rankMin + entry.delta;
                if (rankMax > target + tolerance) return previous.value;
                previous = entry;
            }
            return entries.get(entries.size()-1).value;
        }

        public void assertInvariants() {
            long total = 0, last = Long.MIN_VALUE;
            for (int i = 0; i < entries.size(); i++) {
                Entry e = entries.get(i);
                if (e.value < last || e.g <= 0 || e.delta < 0) {
                    throw new AssertionError("entry order/count invalid");
                }
                last = e.value;
                total += e.g;
            }
            if (total != count ||
                ((count == 0) != entries.isEmpty())) {
                throw new AssertionError("missing samples");
            }
        }
    }

    public static final class Reservoir {
        private final int capacity;
        private final Random random;
        private final ArrayList<Long> samples = new ArrayList<>();
        private long count;

        public Reservoir(int capacity, long seed) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
            this.random = new Random(seed);
        }

        public void add(long value) {
            if (count == Long.MAX_VALUE) {
                throw new IllegalStateException("count overflow");
            }
            count++;
            if (samples.size() < capacity) {
                samples.add(value);
            } else {
                long j = random.nextLong(count);
                if (j < capacity) samples.set((int)j, value);
            }
        }

        public long count() { return count; }
        public int retainedSamples() { return samples.size(); }
        public List<Long> snapshot() { return List.copyOf(samples); }

        public long sampleQuantile(double phi) {
            if (!Double.isFinite(phi) || phi < 0 || phi > 1) {
                throw new IllegalArgumentException("phi must be in [0,1]");
            }
            if (samples.isEmpty()) {
                throw new IllegalStateException("no samples");
            }
            ArrayList<Long> sorted = new ArrayList<>(samples);
            sorted.sort(Comparator.naturalOrder());
            int rank = Math.max(1,
                    (int)Math.ceil(phi*sorted.size()));
            return sorted.get(rank-1);
        }
    }

    public static long exactQuantile(List<Long> input, double phi) {
        if (input == null || input.isEmpty()
                || !Double.isFinite(phi) || phi < 0 || phi > 1) {
            throw new IllegalArgumentException("invalid query");
        }
        ArrayList<Long> sorted = new ArrayList<>(input);
        sorted.sort(Comparator.naturalOrder());
        int rank = Math.max(1, (int)Math.ceil(phi*sorted.size()));
        return sorted.get(rank-1);
    }

    private static void assertRankWindow(List<Long> input, double phi,
                                         double epsilon, long answer) {
        if (input.isEmpty()) throw new AssertionError("empty input in oracle");
        int n = input.size();
        int target = Math.max(1, (int)Math.ceil(phi*n));
        int less = 0, lessOrEqual = 0;
        for (long x : input) {
            if (x < answer) less++;
            if (x <= answer) lessOrEqual++;
        }
        if (lessOrEqual == 0 || less == n) {
            throw new AssertionError("answer not in data");
        }
        double budget = Math.ceil(epsilon*n);
        if (less + 1 > target+budget || lessOrEqual < target-budget) {
            throw new AssertionError("rank window violation"
                    + " n="+n+" phi="+phi+" target="+target
                    + " answer="+answer+" interval=["
                    + (less+1)+","+lessOrEqual+"] epsilon="+epsilon);
        }
    }

    private static void checkStream(List<Long> input, double eps) {
        GK gk = new GK(eps);
        Reservoir reservoir = new Reservoir(7, 42L);
        for (long x : input) {
            gk.add(x);
            reservoir.add(x);
            gk.assertInvariants();
        }
        if (gk.count() != input.size()
                || reservoir.count() != input.size()
                || reservoir.retainedSamples() != Math.min(7,input.size())) {
            throw new AssertionError("counts disagree");
        }
        if (input.isEmpty()) return;
        for (int rank=1; rank<=input.size(); rank++) {
            double q = rank/(double)input.size();
            assertRankWindow(input, q, eps, gk.quantile(q));
        }
        for (double q : new double[]{0, 0.01, 0.25, 0.5, 0.75, 0.99, 1}) {
            assertRankWindow(input, q, eps, gk.quantile(q));
            long sampled = reservoir.sampleQuantile(q);
            if (!input.contains(sampled)) {
                throw new AssertionError("reservoir returned unseen value");
            }
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

    public static void verify() {
        int exhaustive = 0;
        double[] epsilons = {0.05, 0.10, 0.20, 0.35};
        for (int length=0; length<=8; length++) {
            int cases=1;
            for (int k=0;k<length;k++)cases*=3;
            for (int mask=0;mask<cases;mask++) {
                int x=mask;
                List<Long> data=new ArrayList<>();
                for (int i=0;i<length;i++) {
                    data.add((long)(x%3-1));
                    x/=3;
                }
                for (double eps:epsilons) checkStream(data,eps);
                exhaustive++;
            }
        }

        Random rng = new Random(4942026L);
        int seeded = 0;
        for (int trial=0;trial<1000;trial++) {
            int len=rng.nextInt(161);
            ArrayList<Long> input=new ArrayList<>();
            for(int i=0;i<len;i++) {
                long value;
                switch(trial%5){
                    case 0 -> value=(long)i*1000-trial;
                    case 1 -> value=(long)(len-i)*1000+trial;
                    case 2 -> value=(long)rng.nextInt(9)-4;
                    case 3 -> value=rng.nextLong();
                    default -> value=(long)rng.nextInt(100000)-50000;
                }
                input.add(value);
            }
            checkStream(input,epsilons[trial%epsilons.length]);
            seeded++;
        }

        GK asc = new GK(0.01);
        GK repeated = new GK(0.01);
        for(int i=0;i<10000;i++) {
            asc.add(i);
            repeated.add(7);
        }
        if(asc.count()!=10000 || repeated.count()!=10000
                || asc.retainedTuples()>=10000
                || repeated.retainedTuples()>=10000
                || asc.quantile(0)!=0 || asc.quantile(1)!=9999
                || repeated.quantile(0.5)!=7) {
            throw new AssertionError("summary size or endpoints wrong");
        }
        ArrayList<Long> exactAsc = new ArrayList<>();
        for(int i=0;i<10000;i++) exactAsc.add((long)i);
        for(int i=0;i<=100;i++) {
            double q=i/100.0;
            assertRankWindow(exactAsc,q,0.01,asc.quantile(q));
        }

        Reservoir res = new Reservoir(3,11);
        for (int i=0;i<10;i++)res.add(i);
        if (res.count()!=10 || res.retainedSamples()!=3 ||
                new HashSet<>(res.snapshot()).size()!=3) {
            throw new AssertionError("reservoir uniqueness/size invalid");
        }

        expectInvalid(() -> new GK(0));
        expectInvalid(() -> new GK(0.5));
        expectInvalid(() -> new GK(Double.NaN));
        expectInvalid(() -> new Reservoir(0, 10));
        expectInvalid(() -> new GK(0.1).quantile(-0.1));
        expectInvalid(() -> new Reservoir(3,5).sampleQuantile(1.5));
        expectInvalid(() -> exactQuantile(List.of(),0.5));
        expectInvalid(() -> exactQuantile(List.of(1L),Double.NaN));

        System.out.println("Exhaustive streams (alphabet -1,0,1): "
                + exhaustive + " PASS");
        System.out.println("Seeded varied streams: " + seeded + " PASS");
        System.out.println("Ascending n=10000 GK tuples: "
                + asc.retainedTuples());
        System.out.println("Constant n=10000 GK tuples: "
                + repeated.retainedTuples());
        System.out.println("Rank windows, reservoir and bad inputs: PASS");
    }

    public static void main(String[] args) {
        long[] values={7,1,9,3,5,2,8,4,6,0};
        GK gk=new GK(0.10);
        Reservoir reservoir=new Reservoir(4,494L);
        ArrayList<Long> full=new ArrayList<>();
        for(long v:values){
            gk.add(v);
            reservoir.add(v);
            full.add(v);
        }
        System.out.println("n="+gk.count()+", GK tuples="+gk.retainedTuples()
                + ", reservoir samples="+reservoir.retainedSamples());
        for(double q:new double[]{0.25,0.5,0.75}){
            System.out.println("q="+q
                    +" exact="+exactQuantile(full,q)
                    +" GK="+gk.quantile(q)
                    +" reservoir="+reservoir.sampleQuantile(q));
        }
        verify();
    }
~~~

Biên dịch và chạy:

~~~bash
javac StreamingOrderStatistics.java
java StreamingOrderStatistics
~~~

**Stdout đã được quan sát trong lần chạy thực tế:**

~~~text
n=10, GK tuples=6, reservoir samples=4
q=0.25 exact=2 GK=3 reservoir=5
q=0.5 exact=4 GK=5 reservoir=6
q=0.75 exact=7 GK=7 reservoir=7
Exhaustive streams (alphabet -1,0,1): 9841 PASS
Seeded varied streams: 1000 PASS
Ascending n=10000 GK tuples: 69
Constant n=10000 GK tuples: 69
Rank windows, reservoir and bad inputs: PASS
~~~

Các dòng PASS được in khi các kiểm thử tương ứng hoàn thành. `Random` với seed cố định giúp tái lập dữ liệu test và reservoir sample; thay seed có thể làm output reservoir đổi nhưng không thay đổi lý thuyết lấy mẫu.

## 25. Lỗi thường gặp

1. Đánh đồng rank-error với value-error.
2. Không nêu quy ước quantile nearest-rank hoặc nội suy median.
3. Dùng exact equality để kiểm thử một thuật toán approximate.
4. Không xét khoảng rank [L,U] khi dữ liệu có trùng.
5. Tuyên bố một reservoir có sai số rank **tất định**.
6. Không xác định δ khi nói bảo đảm xác suất.
7. Cho rằng seed cố định chứng minh tính đúng của randomized sketch.
8. Dùng k rất nhỏ để ước lượng p99 mà không xét xác suất bỏ sót đuôi.
9. Sort mẫu ở mỗi cập nhật thay vì khi query.
10. Dùng `nextInt((int)n)` trên luồng n lớn.
11. Dùng reservoir toàn lịch sử thay cho sketch sliding window.
12. Gán cận bộ nhớ GK chuẩn cho code demo không có đầy đủ compression policy.
13. Bỏ entry trong GK mà không cộng g sang entry kế.
14. Quên giữ đầu/cuối rồi vẫn tuyên bố min/max exact.
15. Nhầm binary search O(log s) thành toàn bộ insert O(log s).
16. Bỏ chi phí object overhead khi báo memory bytes.
17. Quên kiểm tra q=0/q=1 và dữ liệu rỗng.
18. Chỉ test random không trùng, bỏ all-equal và thứ tự tăng/giảm.
19. Gộp hai summary GK bằng nối entry mà chưa có chứng minh.
20. Áp insert-only sketch vào luồng có delete/update.
21. Bỏ dữ liệu cực trị Long.MIN_VALUE/Long.MAX_VALUE trong test.
22. Dùng phép trừ a-b để so long, có thể overflow.
23. Không nói rõ rank target và ngân sách epsilon*n khi báo lỗi.
24. Quên chọn epsilon theo số hạng sai lệch ứng dụng chấp nhận.
25. Đồng nhất tuple count với số byte RAM thật.
26. Gán bảo đảm tail-value cho một sketch chỉ có rank guarantee.
27. Dùng weighted data với API chỉ hỗ trợ các điểm trọng số 1.
28. Cho rằng t-digest luôn có bảo đảm tất định kiểu GK.
29. Trộn bản kiểm thử exact giữ tất cả dữ liệu với sketch production ít bộ nhớ.
30. Không đo throughput ingest và latency query khi tăng số entry.

## 26. Bài tập tự luyện

**Bài 1:** Với dãy 0..9, tính p25/p50/p75 exact theo nearest-rank, đối chiếu GK và reservoir trong stdout.

**Bài 2:** Cho [1,2,2,2,2,8,10], tính L(2), U(2), giải thích vì sao 2 exact tại target rank4.

**Bài 3:** Tạo một dãy có outlier 10^12, chứng minh một rank sai lệch có thể gây sai số giá trị rất lớn.

**Bài 4:** Chứng minh reservoir có xác suất giữ mỗi vị trí k/n bằng quy nạp.

**Bài 5:** Với n=10.000, δ=0,01, η=0,1, dùng union bound ở mục 9 tìm k đủ lớn và nhận xét tính bảo thủ.

**Bài 6:** Với n=5 triệu, muốn rank-error tối đa 500, chọn epsilon.

**Bài 7:** Theo dõi (v,g,delta) của GK khi thêm 10 giá trị, chỉ thực hiện merge khi g_i+g_next+delta_next≤floor(2εn).

**Bài 8:** Giải thích vì sao query GK trả entry trước khi r_max(current)>r+εn.

**Bài 9:** So chi phí GK ArrayList và reservoir khi tăng throughput và số lượng quantile query.

**Bài 10:** Tự tạo oracle rank-window có xử lý trùng và thử mọi luồng dài tới 8 trên {-1,0,1}.

**Bài 11:** Chạy thử ε=0,10;0,05;0,01 trên luồng tăng, giảm và trùng; đo tuple count, CPU và rank error.

**Bài 12:** So phân vị p99 trên reservoir k=10,100,1000 và các seed khác nhau để thấy tail sensitivity.

**Bài 13:** Nêu kế hoạch hỗ trợ p95 của cửa sổ trượt 1 giờ mà không dùng sketch trên toàn lịch sử.

**Bài 14:** Phân biệt khi nào chọn GK, KLL, t-digest hoặc giữ toàn bộ dữ liệu.

## 27. Kết luận và checklist

Trước khi chọn tóm tắt phân vị trên luồng, hãy xác định: **quy ước quantile**, sai số theo **rank hay giá trị**, độ tin cậy **ε/δ**, bộ nhớ theo **bytes thực**, tốc độ cập nhật/truy vấn, yêu cầu **sliding window** hoặc distributed merge, và cách kiểm thử trên dữ liệu có trùng/outlier.

GK-style dùng entry `(v,g,delta)` và nén để giảm lượng dữ liệu phải nhớ, trong khi reservoir giữ k mẫu đều theo vị trí với bảo đảm xác suất; cả hai đều có thể trả giá trị **không trùng exact** mà vẫn phù hợp hợp đồng gần đúng. Muốn đưa vào production, chọn đúng sketch có chứng minh/đặc tính được yêu cầu và đo memory–accuracy–CPU trên workload thật thay vì chỉ nhìn một số tuple của demo.
