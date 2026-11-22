# Lặp độc lập để tăng xác suất thành công

## 1. Ý tưởng: một lần chưa đủ tin cậy, nhiều lần có thể tốt hơn

Trong **thuật toán ngẫu nhiên hóa**, một lần chạy có thể thất bại dù thuật toán được cài đặt đúng. Chẳng hạn một thủ tục tìm ứng viên sử dụng lựa chọn ngẫu nhiên có xác suất **p** tìm được ứng viên hợp lệ ở mỗi lượt chạy. Nếu các lượt đủ độc lập, việc **chạy lại với lựa chọn ngẫu nhiên mới** làm tăng cơ hội thu được ít nhất một lần thành công.

Bài toán trung tâm:

> Mỗi lần thử thành công với xác suất p. Sau tối đa k lần thử độc lập, xác suất có **ít nhất một lần thành công** bằng bao nhiêu? Cần chạy bao nhiêu lần để đạt mức tin cậy mong muốn?

Với 0≤p≤1 và k nguyên không âm, câu trả lời là:

~~~text
P(at least one success in k independent trials)
    = 1 - (1-p)^k

P(all k trials fail)
    = (1-p)^k
~~~

Nếu mỗi lần thử có xác suất thành công ít nhất p, thì khi có bảo đảm xác suất thành công **có điều kiện sau mọi lịch sử thất bại trước đó** cũng ít nhất p, ta được cận trên cho xác suất k lần đều thất bại:

~~~text
P(all k trials fail) <= (1-p)^k
~~~

Dấu **bằng** trong công thức cơ bản áp dụng khi các lượt độc lập và có cùng xác suất thành công đúng bằng p. Khi xác suất chỉ có **cận dưới**, ta nên viết cận **≤/≥**, không tự thay bằng dấu bằng.

### Ví dụ trực giác

Một thủ tục tạo ra ứng viên hợp lệ với xác suất 20% trong một lần. Thử một lần có khả năng thành công 0,2, thất bại 0,8. Nếu thử độc lập năm lần:

~~~text
P(all fail) = 0.8^5 = 0.32768
P(at least one success) = 1 - 0.32768 = 0.67232
~~~

Vậy cơ hội có kết quả tăng từ **20%** lên **67,232%**. Tuy nhiên nó **không bằng 5×20%=100%**, vì các sự kiện “thành công ở lượt i” có thể cùng xảy ra; cộng xác suất đơn giản sẽ đếm trùng những kết quả đó.

### Ý nghĩa trong thực tế

Kỹ thuật này thường được gọi là **amplification by repetition**, **xác suất thành công tăng nhờ lặp** hoặc **restarting randomized algorithm**. Nó xuất hiện khi:

- Thử những cấu hình ngẫu nhiên khác nhau để tìm lời giải có thể **kiểm chứng**.
- Chạy lại một thuật toán Monte Carlo có thể thất bại với xác suất có thể chặn trên.
- Lấy nhiều mẫu độc lập để giảm khả năng bỏ lỡ một sự kiện.
- Lập ngân sách số lần thử sao cho rủi ro “không tìm được kết quả” dưới một ngưỡng δ.
- Lặp một thuật toán Las Vegas có thời gian tìm ra kết quả là biến ngẫu nhiên.
- So sánh lối kết hợp “chỉ cần một lần đúng” với biểu quyết đa số khi thuật toán có lỗi hai phía.

**Phạm vi:** tập trung vào lặp độc lập và cận xác suất, không coi lặp lại là bảo đảm chắc chắn thành công hữu hạn khi p<1.

## 2. Mô hình Bernoulli và các biến cố

Một **lượt thử Bernoulli** có hai kết quả: thành công hoặc thất bại. Ký hiệu:

~~~text
S_i = bien co thanh cong o lan i
F_i = bien co that bai o lan i
P(S_i) = p
P(F_i) = 1-p = q
~~~

Ở đây q=1−p là xác suất thất bại trong **một** lượt. Nếu mọi lượt độc lập và có cùng p, việc không thành công lần nào trong k lượt là giao của k biến cố thất bại:

~~~text
F_1 AND F_2 AND ... AND F_k
~~~

Nhờ độc lập:

~~~text
P(F_1 AND ... AND F_k)
    = P(F_1) * P(F_2) * ... * P(F_k)
    = q^k
~~~

Biến cố “ít nhất một lần thành công” chính là **biến cố đối** của “cả k lượt đều thất bại”, nên:

~~~text
P(S_1 OR ... OR S_k)
    = 1 - P(F_1 AND ... AND F_k)
    = 1 - q^k
    = 1 - (1-p)^k
~~~

### Vì sao dùng biến cố đối dễ hơn?

Nếu tính trực tiếp P(S1 OR ... OR Sk) bằng cách cộng từng biến cố, phải xử lý các giao nhiều chiều để tránh đếm trùng. Biến cố đối “tất cả đều thất bại” có thể tính nhanh bằng tích xác suất khi các lượt độc lập.

### Điều kiện độc lập là gì?

Độc lập có nghĩa là biết kết quả những lượt trước **không làm thay đổi phân phối** của lượt sau trong mô hình. Cụ thể với các lần thử giống nhau:

~~~text
P(S_i | lich su cac luot truoc) = p
~~~

khi xác suất có điều kiện được định nghĩa. Việc gọi một hàm nhiều lần **không tự động** tạo ra các phép thử độc lập: dùng lại chính một mẫu, một seed khởi tạo y hệt hoặc trạng thái cố định có thể tạo các kết quả tương quan.

### Các trường hợp biên

- **k=0:** chưa có phép thử, xác suất đã thành công là 0, xác suất không thành công là 1.
- **p=0:** không lần nào có cơ hội thành công, tăng k hữu hạn không giúp ích.
- **p=1:** chỉ cần một lượt là chắc chắn thành công; k=0 vẫn không thực hiện gì.
- **0<p<1, k hữu hạn:** xác suất thành công **nhỏ hơn 1**, dù có thể rất gần 1.

## 3. Bảng xác suất và tốc độ khuếch đại

Giả sử mỗi lượt thành công độc lập với p=0,2, tức q=0,8:

| Số lần tối đa k | P(cả k lần thất bại) = 0,8^k | P(ít nhất một lần thành công) |
| ---: | ---: | ---: |
| 0 | 1,000000 | 0,000000 |
| 1 | 0,800000 | 0,200000 |
| 2 | 0,640000 | 0,360000 |
| 3 | 0,512000 | 0,488000 |
| 4 | 0,409600 | 0,590400 |
| 5 | 0,327680 | 0,672320 |
| 10 | ≈0,107374 | ≈0,892626 |
| 14 | ≈0,043980 | ≈0,956020 |

Mỗi lần thử thêm **nhân xác suất chưa thành công với 0,8**. Vì thế rủi ro thất bại giảm theo **hàm mũ**, không giảm theo một lượng tuyệt đối cố định.

### Lợi ích cận biên

Từ k lượt lên k+1 lượt, xác suất thành công tăng:

~~~text
[1-(1-p)^(k+1)] - [1-(1-p)^k]
    = p*(1-p)^k
~~~

Giá trị này giảm dần theo k khi 0<p<1: những lượt đầu giúp cải thiện xác suất nhiều hơn các lượt sau. Vì thế cần cân bằng thời gian chạy và mức tin cậy mong muốn.

### Tăng gấp đôi số lượt

Nếu sau k lượt xác suất thất bại là δₖ=(1−p)^k, thì sau 2k lượt độc lập:

~~~text
delta_2k = (1-p)^(2k) = delta_k^2
~~~

Ví dụ nếu k lượt còn rủi ro thất bại 10%, thì 2k lượt theo cùng mô hình còn 1%. Đây là một cách nhìn trực giác về **amplification**: lặp lại một ngân sách thử độc lập sẽ nhân rủi ro thất bại của các khối với nhau.

## 4. Chọn số lượt k từ mức thất bại cho phép δ

Giả sử người thiết kế muốn:

~~~text
P(all k trials fail) <= delta
~~~

với 0<δ<1. Nếu biết xác suất thành công mỗi lượt ít nhất p>0 và các điều kiện độc lập/cận có điều kiện phù hợp, cần:

~~~text
(1-p)^k <= delta
~~~

Khi 0<p<1, lấy logarit hai vế:

~~~text
k * ln(1-p) <= ln(delta)
~~~

Do `ln(1-p)<0`, khi chia hai vế thì chiều bất đẳng thức đảo:

~~~text
k >= ln(delta) / ln(1-p)
~~~

Số lượt nguyên nhỏ nhất là:

~~~text
k_min = ceil(ln(delta) / ln(1-p))
~~~

Nếu chỉ biết mỗi lượt có xác suất thành công **ít nhất p**, công thức trên vẫn cho **ngân sách bảo đảm cận thất bại δ** khi đủ điều kiện nêu ở phần 2, nhưng xác suất thành công thực tế có thể cao hơn cận.

### Ví dụ 1: p=0,2; muốn thành công ít nhất 95%

Ngưỡng thất bại δ=0,05:

~~~text
k >= ln(0.05) / ln(0.8)
  ≈ 13.425...

k_min = 14
~~~

Kiểm tra:

~~~text
k=13: P(fail)=0.8^13 ≈ 0.054976 > 0.05
k=14: P(fail)=0.8^14 ≈ 0.043980 <= 0.05
~~~

Vậy **14 lượt** là ngân sách nhỏ nhất trong mô hình này để cơ hội thành công đạt ít nhất 95%.

### Ví dụ 2: p=0,1; muốn thành công ít nhất 99%

~~~text
delta = 0.01
k >= ln(0.01)/ln(0.9)
  ≈ 43.7087...

k_min = 44
~~~

Kiểm tra: `0,9^44≈0,0096977`, nhỏ hơn 1%; còn `0,9^43≈0,010775`, lớn hơn 1%.

### Các biên đặc biệt

- Nếu p=1, k_min=1 cho mọi 0<δ<1.
- Nếu p=0, **không tồn tại k hữu hạn** đạt δ<1.
- Nếu δ=0 và 0<p<1, **không có số lượt hữu hạn** bảo đảm xác suất thất bại bằng 0.
- Nếu chấp nhận δ≥1, ngân sách k=0 thỏa bất đẳng thức nhưng không đạt ích lợi tìm kiếm; bài tập trung vào 0<δ<1.
- Phải làm tròn **lên** (`ceil`), không làm tròn gần nhất.

### Cẩn thận phép so sánh số thực

Khi p rất nhỏ hoặc k rất lớn, tính trực tiếp `(1-p)^k` bằng `double` có thể mất độ chính xác. Trong Java, `Math.log1p(-p)` và `Math.expm1(...)` giúp tính ổn định hơn khi p gần 0. Bản demo dùng **tìm kiếm nhị phân trên số lượt** và so logarit để tránh một số lỗi làm tròn ở ranh giới.

## 5. Độc lập thực sự, phụ thuộc và phản ví dụ

Công thức `1-(1-p)^k` **không đúng cho mọi chuỗi thử có cùng xác suất biên p**.

### Phản ví dụ: dùng một kết quả duy nhất cho mọi lượt

Giả sử rút một đồng xu ngẫu nhiên một lần; nếu mặt được chọn là “thành công” thì tất cả k lượt đều báo thành công, nếu không thì tất cả đều thất bại.

Mỗi lượt xét riêng có xác suất thành công p, nhưng các lượt **phụ thuộc hoàn toàn**. Khi đó:

~~~text
P(at least one success) = p
P(all fail) = 1-p
~~~

với mọi k≥1. Lặp 100 lần cũng không thay đổi xác suất thành công, vì không có lựa chọn ngẫu nhiên mới.

Nếu nhầm áp công thức độc lập, ta sẽ tính `1-(1-p)^100`, có thể rất gần 1 và đưa ra cam kết sai.

### Cùng nguồn RNG có đồng nghĩa phụ thuộc?

Một **pseudorandom generator (PRNG)** có trạng thái, ví dụ `java.util.Random`, phát ra một chuỗi giá trị khi gọi liên tiếp. Trong mô hình thuật toán, ta thường giả sử các lựa chọn giả ngẫu nhiên có chất lượng phù hợp để **xấp xỉ** các lần thử độc lập. Tuy nhiên tính độc lập toán học **không được chứng minh chỉ bằng việc gọi `nextDouble()` nhiều lần**; PRNG là thuật toán xác định nếu biết seed.

Cần phân biệt:

- **Mô hình xác suất:** các lần thử được giả định độc lập và phân phối đúng.
- **Cài đặt thực tế:** một PRNG cố định, được đánh giá theo đặc tính thống kê và mục tiêu ứng dụng.
- **Bảo mật:** kẻ tấn công biết seed hoặc dự đoán được RNG có thể dự đoán chuỗi kết quả, kể cả khi thuật toán amplification được lập luận đúng trong mô hình xác suất.

### Lỗi tái khởi tạo cùng seed

~~~java
for (int attempt = 0; attempt < k; attempt++) {
    Random rng = new Random(12345L);
    // consume exactly the same random sequence each time
}
~~~

Nếu thủ tục bên trong dùng cùng input và cùng số lượng lệnh gọi RNG, mỗi lần có thể đi vào **cùng đường đi**; lặp k lần không phải k cơ hội mới.

Thay vào đó, tạo một nguồn RNG phù hợp một lần và dùng liên tục hoặc quản lý các luồng RNG độc lập theo yêu cầu. **Đừng dùng thời gian hiện tại để tạo seed liên tiếp rồi mặc nhiên cho rằng độc lập tốt**; thời gian có độ phân giải hữu hạn và có thể tạo seed tương quan.

## 6. Điều kiện mạnh hơn: xác suất thành công có điều kiện tối thiểu

Công thức dấu bằng đòi mô hình Bernoulli độc lập đồng xác suất. Nhưng có một kết quả **mạnh hơn** rất hữu ích:

Nếu với mỗi lượt i, **dù các lượt trước đã thất bại**, xác suất thành công của lượt i (có điều kiện trên toàn bộ lịch sử thất bại liên quan) vẫn **ít nhất p**, thì:

~~~text
P(F_i | F_1 AND ... AND F_(i-1)) <= 1-p
~~~

Áp dụng quy tắc nhân xác suất:

~~~text
P(F_1 AND ... AND F_k)
 = P(F_1)
 * P(F_2 | F_1)
 * ...
 * P(F_k | F_1,...,F_(k-1))
 <= (1-p)^k
~~~

Vì thế:

~~~text
P(at least one success) >= 1-(1-p)^k
~~~

Định lý cận này **không đòi mọi lượt độc lập hoàn toàn**, mà đòi **cận xác suất thành công có điều kiện sau các lịch sử thất bại**. Cận phải được chứng minh cho quy trình cụ thể.

### Phân biệt ba mức bảo đảm

1. **Độc lập, mỗi lượt có xác suất đúng p:** xác suất thành công sau k lượt **bằng** `1-(1-p)^k`.
2. **Cận dưới có điều kiện p:** xác suất thành công sau k lượt **ít nhất** `1-(1-p)^k`.
3. **Chỉ biết P(S_i)≥p theo từng lượt, không biết phụ thuộc:** không thể tự suy ra cận mũ này.

Phản ví dụ ở phần 5 thuộc mức thứ ba: mỗi lượt có xác suất biên p nhưng sau khi đã thất bại lần đầu, các lượt sau có xác suất thành công bằng 0.

### Khi thuật toán thay đổi theo lịch sử

Một heuristic có thể học từ thất bại trước đó và đổi chiến lược. Điều này **không nhất thiết làm mất khả năng phân tích xác suất**, nhưng phải kiểm tra cận `P(S_i | history)` theo chính cơ chế thích nghi mới. Không dùng công thức độc lập một cách máy móc.

## 7. Dừng sớm sau lần thành công đầu tiên

Nếu mục tiêu chỉ cần **một kết quả đúng**, cách cài hiệu quả là:

~~~text
repeatUpTo(k):
    for attempt = 1..k:
        result = randomizedAttempt()
        if isVerifiedSuccess(result):
            return SUCCESS, result, attemptsUsed=attempt

    return NOT_FOUND_AFTER_BUDGET, attemptsUsed=k
~~~

Thuật toán **không cần chạy hết k lượt** nếu một lượt đã thành công. Điều này giữ nguyên biến cố “có ít nhất một lần thành công trong k lượt”, vì dừng sớm chỉ bỏ qua những lượt **không còn cần thiết** sau thành công.

Nếu hết k lần không tìm được kết quả, trạng thái phải có nghĩa **“chưa tìm được trong ngân sách đã cấp”**. Không được đánh đồng với **“bài toán chắc chắn vô nghiệm”**, trừ khi có một chứng minh độc lập rằng không tồn tại nghiệm.

### Xác minh kết quả là yếu tố then chốt

Mô hình “lấy bất kỳ kết quả thành công nào” an toàn khi thuật toán trả một **ứng viên** và có thể kiểm tra bằng một **verifier đáng tin cậy**. Nếu verifier chấp nhận cả ứng viên sai (false positive), việc lặp rồi nhận lần “đúng” đầu có thể **khuếch đại rủi ro nhận kết quả sai**.

Vì vậy nên tách:

~~~text
candidate = randomizedAttempt()
if candidate is present
    AND deterministicVerifier(candidate, originalInput):
        accept(candidate)
~~~

Với các bài không có verifier rẻ và có thể sai cả hai phía, cần một cơ chế kết hợp kết quả khác, chẳng hạn **biểu quyết đa số**, thay vì lấy OR của những thông báo “đúng”.

## 8. Số lần thử cho tới thành công: phân phối hình học

Nếu các lượt độc lập và xác suất thành công mỗi lượt đúng p, với 0<p≤1, gọi T là **chỉ số lần thành công đầu tiên** (T∈{1,2,...}). Khi đó:

~~~text
P(T=t) = (1-p)^(t-1)*p

P(T>k) = (1-p)^k

E[T] = 1/p
~~~

Đây là **phân phối hình học**. Ví dụ p=0,25 thì số lượt trung bình cho tới khi thành công là:

~~~text
E[T] = 1/0.25 = 4
~~~

Nhưng “trung bình 4 lượt” **không có nghĩa** mọi lần chạy đều kết thúc trong 4 lượt hoặc xác suất thất bại ở 4 lượt bằng 0. Thực tế:

~~~text
P(T>4) = 0.75^4 = 81/256
       = 0.31640625
~~~

Sau bốn lượt, xác suất chưa thành công vẫn hơn 31%.

### Khi giới hạn ngân sách k

Nếu luôn dừng ở lần thành công đầu hoặc sau tối đa k lượt, số lượt thực tế là:

~~~text
N = min(T,k)
~~~

Với p>0:

~~~text
E[N] = sum_{j=0..k-1} (1-p)^j
     = [1-(1-p)^k] / p
~~~

Với p=0, không có lần thành công nào và E[N]=k. Với k=0, E[N]=0.

Ví dụ p=1/4, k=4:

~~~text
E[N] = (1-0.75^4)/0.25
     = 0.68359375/0.25
     = 2.734375
~~~

Vậy ngân sách tối đa là bốn lượt nhưng **số lượt kỳ vọng** chỉ khoảng 2,734 vì thường dừng sớm.

### Cẩn thận với kỳ vọng

Kỳ vọng thời gian **không phải** cận thời gian chạy chắc chắn. Một thuật toán có E[T]=4 vẫn có thể, với xác suất nhỏ, cần rất nhiều lượt. Lập ngân sách δ giúp kiểm soát **đuôi phân phối** thay vì chỉ nhìn trung bình.

## 9. Thời gian chạy, chi phí và ngân sách

Nếu một lượt thử tốn O(C) thời gian và mỗi lần thử có chi phí tương đương:

- **Tệ nhất** khi có ngân sách k: O(k·C).
- **Kỳ vọng** khi dừng sớm, với p>0 độc lập đồng xác suất: O(C·E[min(T,k)]) = O(C·[1−(1−p)^k]/p).
- Khi chạy cho tới thành công mà không giới hạn ngân sách và p>0: thời gian kỳ vọng O(C/p), nhưng thời gian thực tế **không có cận hữu hạn chắc chắn**.
- Nếu cần lưu một kết quả xác minh, bộ nhớ phụ thêm tùy cách lưu ứng viên và verifier; chỉ bộ điều khiển lặp là O(1).

### Thời gian mỗi lượt có thể thay đổi

Nếu một lượt là thuật toán ngẫu nhiên có chi phí C_i thay đổi theo dữ liệu và randomness, không nên tự viết O(k·C) với C là một hằng không được bảo đảm. Có thể dùng ngân sách thời gian, chi phí tệ nhất mỗi lượt, hoặc phân tích kỳ vọng có điều kiện. Trong môi trường thực tế, việc khởi tạo lại trạng thái cũng có chi phí đáng kể.

### Dừng sớm làm tiết kiệm nhưng không tăng xác suất hơn ngân sách k

Khi bạn luôn dừng sau thành công đầu tiên, xác suất “có kết quả sau tối đa k lượt” vẫn là `1−(1−p)^k`. Dừng sớm không tạo thêm xác suất; nó chỉ **không tiêu CPU cho những lượt không còn mục đích**.

### Chọn k khi p nhỏ

Với p đủ nhỏ và k không quá nhỏ, ta có gần đúng:

~~~text
ln(1-p) ≈ -p

k ≈ ln(1/delta)/p
~~~

Cận đơn giản thường dùng là `1−p≤e^(−p)` nên:

~~~text
P(all fail)=(1-p)^k <= exp(-p*k)
~~~

Chọn `k >= ln(1/delta)/p` là một **ngân sách đủ** (có thể không tối thiểu). Đây là dạng dễ nhớ khi tính toán giới hạn xác suất trong phân tích thuật toán.

## 10. Ví dụ liệt kê toàn bộ các đường đi ngẫu nhiên

Để kiểm công thức một cách độc lập với một trình sinh số ngẫu nhiên, xét mỗi lượt lấy một số nguyên đều trong:

~~~text
{0,1,2,3}
~~~

Định nghĩa **thành công khi lấy được 0**, do đó p=1/4, q=3/4. Thử độc lập **k=4 lượt**.

Mỗi lượt có bốn lựa chọn, nên tổng số **chuỗi kết quả cơ sở** là:

~~~text
4^4 = 256
~~~

Mọi chuỗi có cùng xác suất 1/256 dưới mô hình bốc độc lập, đồng đều. Một chuỗi **thất bại hoàn toàn** khi cả bốn lượt đều nằm trong {1,2,3}:

~~~text
3^4 = 81 chuoi that bai
~~~

Vì thế:

~~~text
so chuoi co it nhat mot thanh cong = 256 - 81 = 175
P(success by trial 4) = 175/256 = 0.68359375
P(all fail) = 81/256 = 0.31640625
~~~

### Phân bố vị trí thành công đầu tiên

Khi xét toàn bộ 256 chuỗi có độ dài 4, số chuỗi có thành công đầu tiên ở từng lượt:

| Lần thành công đầu | Chuỗi kết quả có vị trí đó |
| ---: | ---: |
| Lượt 1 | 1×4×4×4 = 64 |
| Lượt 2 | 3×1×4×4 = 48 |
| Lượt 3 | 3×3×1×4 = 36 |
| Lượt 4 | 3×3×3×1 = 27 |
| Không có thành công | 3×3×3×3 = 81 |

Tổng 64+48+36+27+81=256. Tổng bốn hàng có thành công bằng **175**, khớp công thức `256−3^4`.

### Vì sao vẫn tính các lượt sau khi đã thành công?

Trong phép liệt kê để chứng minh phân phối, ta xét **mọi chuỗi 4 kết quả giả định**, bao gồm cả các giá trị có thể phát sinh sau thời điểm thành công đầu. Còn chương trình thật có thể **dừng sớm**. Việc này không thay đổi xác suất “có ít nhất một thành công trong tối đa bốn lượt”, nhưng làm giảm số lượt đã thực hiện.

### Kiểm thêm k=6

Nếu tăng lên sáu lượt với p=1/4:

~~~text
total paths = 4^6 = 4096
all-fail paths = 3^6 = 729
success paths = 4096 - 729 = 3367

P(at least one success) = 3367/4096
                         ≈ 0.821? (gia tri xap xi)
~~~

Để tránh lệch do làm tròn trên các số ví dụ, khi cần **giá trị chính xác** hãy giữ phân số `3367/4096` hoặc dùng phép tính số thực có kiểm tra, không thay các kết quả phân số bằng số thập phân viết tay.

## 11. Java 17: chương trình độc lập có mô hình xác suất và thử nghiệm

Chương trình `IndependentRepetitionDemo.java` có thể biên dịch trực tiếp trên JDK 17. Nó minh họa:

- `failureAfter(p,k)`: xác suất toàn bộ k lượt thất bại theo mô hình độc lập.
- `successAfter(p,k)`: xác suất có ít nhất một thành công, tính bằng `Math.expm1` ổn định hơn khi p nhỏ.
- `minTrials(p,delta)`: tìm số lượt nhỏ nhất để rủi ro thất bại ≤δ, bằng tìm kiếm nhị phân trên logarit, tránh làm tròn phép `ceil` sai ở ranh giới thông thường.
- `repeatUpTo(k,BooleanSupplier)`: chạy tối đa k lượt và dừng ngay khi thành công.
- `expectedAttemptsCapped(p,k)`: kỳ vọng số lượt thực tế nếu dừng sớm hoặc hết k.
- `enumerateFourIndependentDraws`: liệt kê đúng 256 chuỗi bốn giá trị đều 0..3 và đếm lần thành công đầu, đối chiếu công thức.
- Ví dụ `java.util.Random` tạo hai dãy test lặp với cùng seed. **Không** suy ra độc lập toán học hoặc bảo mật chỉ từ điều đó.
- Chương trình in các công thức xác định và các thuộc tính kiểm thử, **không in một mẫu ngẫu nhiên riêng lẻ làm đáp án cố định**.

**Lưu tệp với tên chính xác `IndependentRepetitionDemo.java`:**

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.Random;
import java.util.function.BooleanSupplier;

public class IndependentRepetitionDemo {

    public record RunResult(boolean success, int attempts) {}

    private static void checkP(double p) {
        if (!Double.isFinite(p) || p < 0.0 || p > 1.0) {
            throw new IllegalArgumentException(
                    "p must be finite in [0,1]");
        }
    }

    private static void checkK(int k) {
        if (k < 0) {
            throw new IllegalArgumentException(
                    "number of attempts must be nonnegative");
        }
    }

    public static double failureAfter(double p, int k) {
        checkP(p);
        checkK(k);
        if (k == 0 || p == 0.0) {
            return 1.0;
        }
        if (p == 1.0) {
            return 0.0;
        }
        // Numerically safer than first computing 1-p for tiny p.
        return Math.exp(k * Math.log1p(-p));
    }

    public static double successAfter(double p, int k) {
        checkP(p);
        checkK(k);
        if (k == 0 || p == 0.0) {
            return 0.0;
        }
        if (p == 1.0) {
            return 1.0;
        }
        // -expm1(t) computes 1-exp(t) accurately when t is near 0.
        return -Math.expm1(k * Math.log1p(-p));
    }

    public static int minTrials(double p, double delta) {
        checkP(p);
        if (!Double.isFinite(delta)
                || delta <= 0.0 || delta >= 1.0) {
            throw new IllegalArgumentException(
                    "delta must be in (0,1)");
        }
        if (p == 0.0) {
            throw new IllegalArgumentException(
                    "cannot reach target when p=0");
        }
        if (p == 1.0) {
            return 1;
        }

        double logQ = Math.log1p(-p);
        double logDelta = Math.log(delta);

        // Exponential search to bracket minimal feasible k.
        int low = 0;
        int high = 1;
        while (high * logQ > logDelta) {
            if (high > Integer.MAX_VALUE / 2) {
                high = Integer.MAX_VALUE;
                if (high * logQ > logDelta) {
                    throw new IllegalArgumentException(
                            "required budget exceeds int range");
                }
                break;
            }
            high *= 2;
        }

        // Compare in log space to avoid exp rounding at a boundary.
        while (low + 1 < high) {
            int mid = low + (high - low) / 2;
            if (mid * logQ <= logDelta) {
                high = mid;
            } else {
                low = mid;
            }
        }
        return high;
    }

    public static RunResult repeatUpTo(
            int maxAttempts, BooleanSupplier trial) {
        checkK(maxAttempts);
        Objects.requireNonNull(trial, "trial");

        for (int i = 0; i < maxAttempts; i++) {
            if (trial.getAsBoolean()) {
                return new RunResult(true, i + 1);
            }
        }
        return new RunResult(false, maxAttempts);
    }

    public static double expectedAttemptsCapped(
            double p, int k) {
        checkP(p);
        checkK(k);
        if (k == 0) {
            return 0.0;
        }
        if (p == 0.0) {
            return k;
        }
        return successAfter(p, k) / p;
    }

    private static class Enumeration {
        int paths;
        int successful;
        int failed;
        final int[] firstSuccessAt = new int[4];
    }

    // Enumerate all 4^4 equally likely primitive outcomes.
    // A draw equal to 0 denotes success; p=1/4 each trial.
    private static void enumerateFourIndependentDraws(
            int step, int firstSuccess,
            Enumeration counts) {
        if (step == 4) {
            counts.paths++;
            if (firstSuccess < 0) {
                counts.failed++;
            } else {
                counts.successful++;
                counts.firstSuccessAt[firstSuccess]++;
            }
            return;
        }

        for (int value = 0; value < 4; value++) {
            int nextFirst = firstSuccess;
            if (nextFirst < 0 && value == 0) {
                nextFirst = step;
            }
            enumerateFourIndependentDraws(
                    step + 1, nextFirst, counts);
        }
    }

    private static void showProbability(double p, int k) {
        System.out.printf(
                Locale.ROOT,
                "p=%.2f, k=%d: success=%.6f, failure=%.6f%n",
                p, k, successAfter(p, k), failureAfter(p, k));
    }

    public static void main(String[] args) {
        showProbability(0.20, 1);
        showProbability(0.20, 5);
        showProbability(0.20, 14);
        showProbability(0.25, 4);

        System.out.println(
                "min trials p=0.20, delta=0.05: "
                + minTrials(0.20, 0.05));
        System.out.println(
                "min trials p=0.10, delta=0.01: "
                + minTrials(0.10, 0.01));
        System.out.println(
                "min trials p=0.50, delta=0.125: "
                + minTrials(0.50, 0.125));

        showProbability(0.0, 8);
        showProbability(1.0, 1);

        boolean[] script = {false, false, true, false};
        int[] cursor = {0};
        RunResult scripted = repeatUpTo(
                4, () -> script[cursor[0]++]);
        System.out.println(
                "scripted: success=" + scripted.success()
                + ", attempts=" + scripted.attempts());

        RunResult exhausted = repeatUpTo(4, () -> false);
        System.out.println(
                "exhausted: success=" + exhausted.success()
                + ", attempts=" + exhausted.attempts());

        RunResult zero = repeatUpTo(0, () -> true);
        System.out.println(
                "zero budget: success=" + zero.success()
                + ", attempts=" + zero.attempts());

        Random first = new Random(2026L);
        Random second = new Random(2026L);
        RunResult replayOne = repeatUpTo(
                12, () -> first.nextInt(4) == 0);
        RunResult replayTwo = repeatUpTo(
                12, () -> second.nextInt(4) == 0);
        System.out.println(
                "same seed replay identical="
                + replayOne.equals(replayTwo));

        Enumeration counts = new Enumeration();
        enumerateFourIndependentDraws(0, -1, counts);
        if (counts.paths != 256
                || counts.successful != 175
                || counts.failed != 81
                || !Arrays.equals(counts.firstSuccessAt,
                        new int[] {64, 48, 36, 27})) {
            throw new AssertionError(
                    "exhaustive probability mismatch");
        }

        System.out.println(
                "enumerated paths=" + counts.paths
                + ", success=" + counts.successful
                + ", failure=" + counts.failed);
        System.out.println(
                "first-success counts="
                + Arrays.toString(counts.firstSuccessAt));
        System.out.printf(
                Locale.ROOT,
                "exact-model success rate=%.6f%n",
                counts.successful / (double) counts.paths);
        System.out.printf(
                Locale.ROOT,
                "expected attempts capped=%.6f%n",
                expectedAttemptsCapped(0.25, 4));

        try {
            successAfter(Double.NaN, 4);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid p: " + error.getMessage());
        }

        try {
            minTrials(0.0, 0.05);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "impossible target: " + error.getMessage());
        }
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac IndependentRepetitionDemo.java
java IndependentRepetitionDemo
~~~

**Stdout xác định:**

~~~text
p=0.20, k=1: success=0.200000, failure=0.800000
p=0.20, k=5: success=0.672320, failure=0.327680
p=0.20, k=14: success=0.956020, failure=0.043980
p=0.25, k=4: success=0.683594, failure=0.316406
min trials p=0.20, delta=0.05: 14
min trials p=0.10, delta=0.01: 44
min trials p=0.50, delta=0.125: 3
p=0.00, k=8: success=0.000000, failure=1.000000
p=1.00, k=1: success=1.000000, failure=0.000000
scripted: success=true, attempts=3
exhausted: success=false, attempts=4
zero budget: success=false, attempts=0
same seed replay identical=true
enumerated paths=256, success=175, failure=81
first-success counts=[64, 48, 36, 27]
exact-model success rate=0.683594
expected attempts capped=2.734375
invalid p: p must be finite in [0,1]
impossible target: cannot reach target when p=0
~~~

### Tại sao chương trình không in kết quả RNG làm ví dụ cố định?

Bài cần kiểm **công thức và điều kiện lặp**, nên đầu ra sử dụng:

- Công thức `Math.log1p/Math.expm1` với số cụ thể.
- Bộ thử được chỉ định sẵn, chứng minh **dừng ở lượt ba**.
- Liệt kê toàn bộ **256 chuỗi** và so đúng 175 thành công/81 thất bại.
- Hai bộ `Random` cùng seed được dùng để kiểm **khả năng tái lập**, không khẳng định độc lập toán học.

Kết quả `exhausted: success=false` chỉ có nghĩa **không thành công trong ngân sách đã thử**. Nó không có nghĩa không tồn tại nghiệm trong một bài tìm kiếm.

### Tính đúng của các trường hợp biên

`failureAfter(p,0)=1`, `successAfter(p,0)=0`. Với p=1 và k≥1, lần đầu chắc chắn thành công. Với p=0, `minTrials` từ chối mục tiêu δ<1 vì không có k hữu hạn đáp ứng.

Chương trình cũng kiểm `NaN`, các xác suất ngoài [0,1], số lượt âm và ngưỡng δ không thuộc (0,1). Những kiểm tra này rất cần thiết vì một phép tính xác suất âm hoặc `NaN` không còn ý nghĩa toán học.

## 12. Cách dùng trong thuật toán Monte Carlo một phía

Một **thuật toán Monte Carlo một phía** có thể sai theo một hướng nhất định nhưng không sai theo hướng còn lại. Ví dụ khi tồn tại một nghiệm, một lượt thử có xác suất ít nhất p phát hiện được **ứng viên có chứng nhận đúng**; nếu không phát hiện, nó trả “chưa tìm thấy”.

Quy trình:

~~~text
for trial=1..k:
    candidate = randomizedSearch(input, freshRandomness)

    if candidate exists
       AND exactVerifier(input,candidate):
        return FOUND(candidate)

return NOT_FOUND_WITHIN_BUDGET
~~~

Nếu mỗi lần thử, khi nghiệm thực sự tồn tại, có xác suất tìm được và được verifier chấp nhận ít nhất p với giả thiết phù hợp, xác suất k lần vẫn bỏ lỡ ≤(1−p)^k.

### Vì sao chỉ nên OR khi có chứng nhận?

Nếu một lần thử trả **kết quả sai có vẻ thành công** và không có verifier, chiến lược “nhận ngay kết quả nào báo thành công” có thể chọn nhầm. Khi thuật toán có **false positive**, lặp nhiều lần thường làm tăng khả năng gặp ít nhất một false positive:

~~~text
P(at least one false positive in k
  independent trials with per-trial rate e)
= 1-(1-e)^k
~~~

Đó là một sự kiện **xấu** cũng có thể được khuếch đại nếu thiết kế kết hợp kết quả không đúng.

### Ví dụ kiểm chứng ứng viên

Trong bài tìm một tập con thỏa điều kiện tổng và kích thước, một lần thử ngẫu nhiên có thể đề xuất tập con. Verifier kiểm trực tiếp các phần tử có hợp lệ, không trùng quy định, tổng có đúng mục tiêu và kích thước có đúng yêu cầu. Chỉ ứng viên vượt qua verifier mới được chấp nhận.

Trong bài quyết định thuần túy không thể dễ xác minh chứng nhận “đúng”, hãy dùng loại thuật toán và cách amplification được chứng minh phù hợp, thay vì tự ý áp dụng chiến lược OR.

## 13. Monte Carlo hai phía và biểu quyết đa số

Nếu mỗi lượt là một thuật toán trả lời **đúng/sai**, và cả hai loại câu trả lời đều có thể sai, thì việc nhận câu trả lời đầu tiên hoặc OR mọi câu “đúng” không bảo đảm giảm lỗi chung.

Một kỹ thuật khác là **majority vote (biểu quyết đa số)**:

1. Chạy k lượt với randomness đủ độc lập.
2. Mỗi lượt xuất câu trả lời nhị phân.
3. Chọn câu trả lời xuất hiện nhiều hơn một nửa số lượt.

Giả sử mỗi lượt trả lời **đúng với xác suất ít nhất 1/2+γ**, trong đó γ>0, và các chỉ báo đúng/sai độc lập theo giả thiết thích hợp. Với k lẻ, bất đẳng thức Hoeffding cho cận:

~~~text
P(majority answer is wrong)
    <= exp(-2*k*gamma^2)
~~~

Đây là dạng **amplification cho lỗi hai phía**, không phải cùng công thức với việc lấy OR của các lần “thành công” có thể kiểm chứng.

### Khi nào không được dùng majority?

- Nếu xác suất đúng mỗi lượt **không hơn 1/2**, majority không tự cải thiện được.
- Nếu các kết quả **phụ thuộc hoàn toàn** (tất cả trả cùng một câu sai), biểu quyết nhiều lần không giúp.
- Nếu câu trả lời không thuộc cùng không gian nhãn hoặc có nhiều nghiệm hợp lệ khác nhau, “đa số” phải được định nghĩa rõ.
- Nếu bài có verifier chính xác, chọn một ứng viên hợp lệ thường đơn giản hơn biểu quyết.

### Không đồng nhất thuật toán Las Vegas và Monte Carlo

- **Las Vegas:** khi trả lời, kết quả đúng; randomness chủ yếu ảnh hưởng thời gian chạy. Có thể thử lại cho tới khi tìm được hoặc hết ngân sách.
- **Monte Carlo:** thời gian thường bị chặn trước, nhưng có xác suất trả kết quả sai/không đầy đủ; repetition giảm xác suất lỗi nếu có chứng minh.
- **Randomized heuristic:** có thể không có cận p được chứng minh. Chạy lại nhiều lần có thể hữu ích thực nghiệm, nhưng không tự thành một bảo đảm toán học.

## 14. Nhiều bài toán con và union bound

Đôi khi thuật toán cần hoàn thành **m bài toán con**, mỗi bài có nguy cơ thất bại riêng. Muốn xác suất **có ít nhất một bài toán con thất bại** không quá δ, một kỹ thuật an toàn là phân bổ ngân sách:

~~~text
delta_per_subproblem = delta / m
~~~

Nếu từng bài toán con có xác suất thất bại sau khi lặp không quá δ/m, thì theo **union bound**:

~~~text
P(any subproblem fails)
    <= sum_{i=1..m} P(subproblem i fails)
    <= m*(delta/m)
    = delta
~~~

**Union bound không cần các bài toán con độc lập.** Độc lập chỉ liên quan đến cách bạn chứng minh xác suất thất bại của từng bài toán con bằng lặp độc lập.

### Ví dụ

Có 100 yêu cầu ngẫu nhiên cần đều thành công và muốn tổng nguy cơ bất kỳ yêu cầu nào thất bại ≤1%:

~~~text
m = 100
delta_total = 0.01
delta_each = 0.0001
~~~

Với xác suất thành công mỗi lượt của từng yêu cầu ít nhất p=0,2, ta có thể chọn cho mỗi yêu cầu:

~~~text
k_each >= ln(0.0001)/ln(0.8)
       ≈ 41.275...

k_each = 42
~~~

Sau đó union bound cho xác suất bất kỳ yêu cầu nào còn thất bại ≤1%, không cần giả định các yêu cầu độc lập với nhau.

### Lưu ý cận có thể bảo thủ

Union bound thường không tối ưu, nhưng đơn giản và an toàn. Nếu có thông tin phụ thuộc/độc lập giữa các bài toán con, có thể có cận chặt hơn; không cần sự phức tạp đó trừ khi ngân sách thời gian yêu cầu.

## 15. Biết p như thế nào và chọn ngưỡng đáng tin

Công thức `k_min=ceil(lnδ/ln(1−p))` chỉ hữu ích khi **p có ý nghĩa đáng tin cậy**.

### Trường hợp p đã được chứng minh

Một phân tích lý thuyết có thể chứng minh trên mọi input hợp lệ, mỗi lần dùng randomness mới có xác suất thành công ít nhất p₀. Khi đó dùng **p₀** để cấp ngân sách, kể cả xác suất thực tế có thể tốt hơn.

### Trường hợp p được ước lượng qua thực nghiệm

Nếu chạy 100 lượt và thấy 20 lượt thành công, ước lượng tỷ lệ mẫu là 0,2. Nhưng **không thể mặc nhiên coi p≥0,2 đã được chứng minh**. Tỷ lệ mẫu có sai số ngẫu nhiên, và dữ liệu test có thể không đại diện cho những input khó hơn.

Để làm một cam kết xác suất từ dữ liệu, cần mô hình thống kê, tập dữ liệu phù hợp và một **cận dưới độ tin cậy** cho p theo mức tự tin đã chọn. Nếu dùng một cận dưới p_lower thay vì tỷ lệ điểm, ngân sách k sẽ lớn hơn nhưng có cơ sở vững hơn.

### p thay đổi theo input

Với một số input dễ, p có thể cao; với input khó, p có thể rất thấp. Nếu bài yêu cầu cận rủi ro trên **mọi input**, phải có cận p áp dụng cho mọi input trong miền đó, không dùng p trung bình của dữ liệu dễ.

### p thay đổi qua các lượt

Nếu xác suất có điều kiện của lượt i là p_i và những lượt đủ độc lập theo mô hình:

~~~text
P(all fail) = PRODUCT_i (1-p_i)
~~~

Nếu chỉ biết các cận dưới có điều kiện p_i, ta được:

~~~text
P(all fail) <= PRODUCT_i (1-p_i)
~~~

Không tự thay mọi p_i bằng cùng một p nếu không có một cận dưới chung hợp lệ.

## 16. Những lỗi lập luận và cài đặt thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Tính xác suất thành công k lần là k·p | Có thể >1 và đếm trùng biến cố | Dùng `1−(1−p)^k` |
| Quên giả thiết độc lập | Cận mũ có thể sai | Kiểm độc lập hoặc cận có điều kiện |
| Tạo RNG mới cùng seed ở mọi lượt | Lặp lại cùng đường đi | Dùng nguồn randomness mới phù hợp |
| Chỉ đổi tên lượt thử nhưng dùng cùng mẫu | Không tăng cơ hội | Sinh ngẫu nhiên thực sự mới |
| Tưởng mỗi lượt có marginal p là đủ | Lệch với biến cố phụ thuộc | Xem xác suất sau lịch sử thất bại |
| Nhầm “ít nhất một thành công” với “tất cả đều thành công” | Sai biến cố | Dùng biến cố đối phù hợp |
| Chia log nhưng quên đổi chiều bất đẳng thức | Ngân sách k sai | Nhớ ln(1−p)<0 |
| Làm tròn k xuống | Không đạt δ | Dùng ceil/kiểm cận |
| Coi 95% nghĩa là chắc chắn | Cam kết không đúng | Báo rõ xác suất còn thất bại |
| Coi NOT_FOUND_AFTER_BUDGET là không có nghiệm | False negative | Đặt trạng thái chính xác |
| Chấp nhận bất kỳ kết quả “đúng” không verify | Khuếch đại false positive | Dùng verifier hoặc voting đúng |
| OR nhiều câu trả lời nhị phân hai phía | Có thể làm sai nhiều hơn | Dùng majority nếu đủ điều kiện |
| Majority trên các lượt hoàn toàn giống nhau | Không giảm lỗi | Bảo đảm randomness đủ độc lập |
| Tính kỳ vọng 1/p rồi coi đó là cận worst-case | Bỏ qua tail | Dùng δ để chọn k |
| Dùng p trung bình từ test làm cận trên mọi input | Không có bảo đảm tổng quát | Chứng minh p_min |
| Nhân xác suất nhiều bài toán con mà chưa chứng minh độc lập | Sai xác suất toàn hệ | Dùng union bound |
| Bỏ p=0, p=1, k=0 | Lỗi log0/NaN | Xử lý biên riêng |
| Tính `1-Math.pow(1-p,k)` khi p cực nhỏ | Cancellation | `log1p/expm1` |
| Chọn δ=0 với 0<p<1 rồi đòi k hữu hạn | Không thể đáp ứng | Chấp nhận δ>0 hoặc p=1 |
| Lặp lại không giới hạn trong hệ thống realtime | Thời gian không bị chặn | Cấp budget k/time limit |
| Đo xác suất chỉ từ ít mẫu | Tỷ lệ nhiễu lớn | Thực nghiệm đủ mạnh và CI |
| Không kiểm phần dư hoặc tính đúng ứng viên | Sai lặng lẽ | Verifier độc lập |
| Không tính chi phí khởi động từng lượt | Ước lượng runtime quá thấp | Tính toàn bộ chi phí C_i |

## 17. Kiểm thử, đối chứng và kiểm định xác suất

### Kiểm công thức với ca nhỏ

- p=0,2,k=1: success=0,2.
- p=0,2,k=5: success=0,67232.
- p=0,2,k=14: success≈0,9560195.
- p=0,25,k=4: success=175/256.
- p=0,k=10: success=0.
- p=1,k=1: success=1.
- k=0 với mọi p: success=0.
- p=0,5,k=3: failure=1/8; tìm số lượt với δ=1/8 phải trả 3.

### Kiểm tính đơn điệu

Với 0≤p≤1:

~~~text
successAfter(p,k+1) >= successAfter(p,k)
failureAfter(p,k+1) <= failureAfter(p,k)
~~~

Với p cố định và k tăng, xác suất thành công không giảm. Với k>0 cố định và p tăng, xác suất thành công cũng không giảm.

### Kiểm công thức bằng enumeration

Nếu mỗi lượt có 4 kết quả đồng xác suất, đúng một kết quả được coi là thành công, thì với k=4:

~~~text
total = 4^4 = 256
all fail = 3^4 = 81
success = 175
~~~

Việc đếm đường đi **độc lập với code tính số thực**. Đây là oracle rất tốt cho các giá trị nhỏ vì không cần lấy mẫu ngẫu nhiên và không có dao động thống kê.

### Kiểm thực nghiệm với RNG

Nếu chạy mô phỏng nhiều nhóm k lượt và đếm tỷ lệ thành công, kết quả có thể gần `1-(1-p)^k` nhưng không nhất thiết bằng đúng. Test cần một khoảng chấp nhận dựa trên phân phối binomial hoặc kiểm định có mức ý nghĩa rõ; đừng assert đúng từng chữ số trên mẫu ngẫu nhiên hữu hạn.

### Kiểm tình huống phụ thuộc

Tạo một biến cố ngẫu nhiên duy nhất rồi dùng lại cờ thành công đó cho k lượt; kết quả phải cho xác suất thành công p, không phải công thức amplification độc lập. Đây là test quan trọng để nhắc lại **điều kiện áp dụng**.

### Kiểm dừng sớm

Cho dãy thử cố định `[false,false,true,false]`. Thuật toán phải trả success=true sau **3 lượt**, không thực hiện lượt thứ tư. Cho `[false,false,false,false]`, phải trả chưa thành công sau đủ 4 lượt. Cho k=0, không được gọi callback.

### Kiểm bất biến ứng viên

Nếu thủ tục trả lời bằng ứng viên, test verifier trên cả ứng viên đúng và sai. Bộ điều khiển lặp **không được** dừng khi chỉ có thông báo thành công chưa được xác minh, nếu thuật toán có khả năng false positive.

## 18. Thiết kế API thử lại trong sản phẩm và dịch vụ

Trong hệ thống thực tế, "thử lại" còn có thể nói về lỗi mạng, thao tác I/O, timeout và tác dụng phụ. Phải phân biệt **repetition for randomized success amplification** với **retry operations** trong hệ thống phân tán.

### Khác biệt giữa hai mô hình

- Trong thuật toán ngẫu nhiên, mỗi lượt sử dụng randomness mới để có cơ hội tìm ra một kết quả hợp lệ.
- Trong hệ thống mạng, cùng một yêu cầu gửi lại có thể có trạng thái **không rõ đã thực hiện hay chưa**, có thể gây tác dụng phụ khi retry.
- Một lỗi có thể có nguyên nhân cố định (quyền truy cập, input sai) khiến xác suất thành công của mọi lượt gần 0; lặp liên tục chỉ lãng phí.
- Phụ thuộc chung như dịch vụ đang down có thể làm các lần retry **tương quan mạnh**, không thỏa giả định Bernoulli độc lập.

### Ngân sách, backoff và idempotency

Trong dịch vụ, thường cần **giới hạn số lần retry**, **backoff** (có thể kèm jitter), timeout, rate limit và **idempotency key** cho các thao tác cần tránh thực hiện trùng. Những cơ chế này giải quyết an toàn và điều phối tải; chúng **không tự chứng minh** công thức `1-(1-p)^k`.

Nếu server trả lỗi xác thực không thể tự phục hồi, retry cùng request không phải một cách làm tăng xác suất theo p độc lập. Nếu yêu cầu ghi dữ liệu có thể đã thành công dù client timeout, retry mù có thể tạo bản ghi trùng. Bài xác suất chỉ cho một mô hình tham khảo **khi giả định thực sự phù hợp**.

### Một thiết kế kết quả an toàn

API có thể trả:

~~~text
SUCCESS(validatedResult, attemptsUsed)
BUDGET_EXHAUSTED(attemptsUsed)
PERMANENT_ERROR(reason)
CANCELLED(attemptsUsed)
~~~

Điều này giúp người gọi phân biệt “đã có kết quả”, “chưa tìm được trong số lượt đã thử”, “lỗi cố định không nên retry”, và “bị hủy”. Không gắn `BUDGET_EXHAUSTED` với kết luận toán học `NO_SOLUTION`.

## 19. Bài tập thực hành

1. Nêu định nghĩa phép thử Bernoulli và xác suất p.
2. Viết biến cố “cả k lượt thất bại” bằng giao các F_i.
3. Chứng minh xác suất cả k lượt thất bại là (1−p)^k khi độc lập.
4. Chứng minh xác suất có ít nhất một thành công là 1−(1−p)^k.
5. Tính xác suất thành công với p=0,2 và k=3.
6. Tính xác suất thất bại với p=0,2 và k=5.
7. Giải thích vì sao k·p không phải công thức đúng.
8. Tính mức tăng xác suất khi tăng từ k lên k+1.
9. Chứng minh thất bại sau 2k lượt bằng bình phương thất bại sau k lượt khi độc lập.
10. Với p=0,2 và δ=0,05, tìm k nhỏ nhất và kiểm k−1.
11. Với p=0,1 và δ=0,01, tìm k nhỏ nhất.
12. Chứng minh phải đổi chiều bất đẳng thức khi chia cho ln(1−p).
13. Xử lý p=0,k>0 và p=1,k>0.
14. Chứng minh không có ngân sách hữu hạn cho δ=0 khi 0<p<1.
15. Tạo phản ví dụ các lượt có marginal p nhưng phụ thuộc hoàn toàn.
16. Viết cận thất bại dưới điều kiện `P(S_i | past failures)≥p`.
17. Nêu sự khác nhau giữa dấu bằng cho i.i.d. và dấu ≤ cho cận có điều kiện.
18. Tìm một heuristic thay đổi theo lịch sử và phân tích điều kiện xác suất cần bảo đảm.
19. Tính P(T=t) cho thời điểm thành công đầu tiên.
20. Chứng minh E[T]=1/p trong phân phối hình học.
21. Tính E[min(T,k)] và áp dụng p=1/4,k=4.
22. Phân biệt thời gian kỳ vọng với cận worst-case.
23. Tính số chuỗi độ dài 4 khi mỗi lượt có 4 kết quả đồng xác suất.
24. Đếm 81 chuỗi thất bại hoàn toàn và 175 chuỗi có thành công.
25. Đếm số chuỗi có thành công đầu ở lượt 1,2,3,4.
26. Cài một hàm Java trả `successAfter(p,k)` với `log1p/expm1`.
27. Cài hàm `minTrials` kiểm δ∈(0,1), p∈[0,1].
28. Viết `repeatUpTo(k,trial)` dừng ở lần thành công đầu tiên.
29. Test dãy `[false,false,true,false]` và xác nhận chỉ chạy 3 lượt.
30. Test không lần nào thành công và API trả BUDGET_EXHAUSTED, không trả NO_SOLUTION.
31. Thử tạo `new Random(seed)` trong mọi lượt và quan sát sự phụ thuộc.
32. Cài verifier cho một bài toán tìm ứng viên cụ thể.
33. Nêu ví dụ lấy OR của kết quả Monte Carlo hai phía là sai.
34. Dẫn xuất một cận biểu quyết đa số bằng Hoeffding khi độ chính xác >1/2.
35. Với m=100 và δ=0,01, phân bổ δ/m và chọn k khi p=0,2.
36. Chứng minh union bound không cần độc lập giữa các bài toán con.
37. Thảo luận vì sao p ước lượng từ 100 lần thử không tự là cận dưới chắc chắn.
38. So việc dùng p_mean và p_min trên một nhóm input khó.
39. Phân tích lặp k lần khi mỗi lượt có chi phí biến đổi và giới hạn thời gian.
40. Thiết kế hệ thống retry có backoff và idempotency, giải thích khác biệt với mô hình amplification.

## 20. Checklist và tổng kết

Trước khi áp dụng lặp độc lập, hãy kiểm:

- **Thành công** được định nghĩa chính xác và có thể xác minh không?
- Mỗi lượt có xác suất thành công **đúng p**, **ít nhất p**, hay chỉ được ước lượng?
- Các lượt độc lập, hoặc có cận thành công **có điều kiện sau thất bại** không?
- Nguồn RNG có thực sự cung cấp randomness mới và phù hợp mục tiêu không?
- Số lượt k và ngưỡng δ có được chọn với điều kiện 0<p≤1, 0<δ<1 không?
- Đã tính `1−(1−p)^k` thay vì k·p chưa?
- Khi lấy logarit, có nhớ `ln(1−p)<0` và làm tròn k lên chưa?
- Đã xử lý p=0,p=1,k=0 trước khi gọi log1p/expm1 chưa?
- Có dừng sớm sau khi **verifier** xác nhận kết quả không?
- Nếu hết ngân sách, có báo **chưa thành công** thay vì **không có nghiệm**?
- Bài là một phía (có thể OR) hay hai phía (cần cách tổ hợp khác)?
- Nếu nhiều bài toán con, có phân bổ δ và dùng union bound hợp lệ không?
- Có kiểm bằng bảng xác suất, enumeration nhỏ và các ca phụ thuộc?
- Có tính chi phí thử lại, khởi tạo lại, giới hạn thời gian và bộ nhớ?
- Nếu áp dụng vào API dịch vụ, có xem xét backoff, trạng thái không rõ và idempotency không?

**Tóm lại**, với các lần thử độc lập, mỗi lần thành công xác suất p:

~~~text
P(success in <= k attempts) = 1-(1-p)^k
P(no success in k attempts) = (1-p)^k
k_min for failure at most delta
    = ceil(ln(delta)/ln(1-p))       (0<p<1, 0<delta<1)
~~~

Lặp độc lập làm xác suất thất bại giảm theo hàm mũ và cho cách đổi **thời gian chạy lấy độ tin cậy**. Nhưng công thức chỉ có ý nghĩa với giả định xác suất đúng: **phụ thuộc kết quả, random seed lặp lại, false positive, sai số ước lượng p hoặc thay đổi input** đều có thể làm kết luận sai. Để triển khai vững chắc, hãy đặt ngân sách k rõ ràng, dùng nguồn ngẫu nhiên phù hợp, dừng khi đã có **kết quả hợp lệ được xác minh**, và coi “hết ngân sách” là một trạng thái thông tin riêng chứ không phải chứng minh vô nghiệm.
