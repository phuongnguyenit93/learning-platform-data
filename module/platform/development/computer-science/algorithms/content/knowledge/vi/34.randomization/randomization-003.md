# Phân biệt kỳ vọng thời gian với xác suất sai

Trong **thuật toán ngẫu nhiên hóa** (*randomized algorithms*), hai nhận định sau không hề đồng nghĩa:

- “Thuật toán chạy nhanh **theo kỳ vọng**.”
- “Thuật toán có **xác suất trả đáp án sai** nhỏ.”

Nhận định thứ nhất mô tả **chi phí thực thi**, còn nhận định thứ hai mô tả **độ tin cậy của kết quả**. Một thuật toán có thể chạy với thời gian thay đổi theo lựa chọn ngẫu nhiên nhưng **không bao giờ trả lời sai**; ngược lại, một thuật toán có thể luôn chạy trong thời gian cố định nhưng đôi khi **trả sai kết quả**. Có thuật toán vừa có thời gian ngẫu nhiên vừa có xác suất sai. Để thiết kế và đọc chứng minh đúng, phải định nghĩa và phân tích từng đại lượng độc lập.

Bài thuộc chủ đề **Ngẫu nhiên hóa (Randomization)**, lấy ba ví dụ xuyên suốt:

1. **Randomized quicksort**: chọn pivot ngẫu nhiên, luôn sắp xếp đúng; **kỳ vọng thời gian** tốt nhưng vẫn có các đường chạy chậm.
2. **So sánh hai dãy bằng dấu vân tay đa thức** (*polynomial fingerprinting*): có thể chạy với số vòng được ấn định, nhưng hai dãy khác nhau đôi khi cho cùng fingerprint; đây là **xác suất sai một phía**.
3. **Mô hình thử lại đến khi thành công có thể kiểm chứng**: không trả kết quả sai, số lượt thử ngẫu nhiên có **phân phối hình học**, minh họa Las Vegas.

Bài có chương trình Java 17+ đầy đủ, chứng minh hai xác suất hoàn toàn khác nhau, ví dụ tính tay, cách giảm xác suất sai bằng các phép thử độc lập, các công thức xác suất và những lỗi lập luận phổ biến.

## 1. Hai câu hỏi khác nhau với cùng một thuật toán

Gọi:

- `x` là **đầu vào đã cố định** của bài toán;
- `R` là những lựa chọn ngẫu nhiên mà thuật toán sử dụng;
- `T(x,R)` là **thời gian/chi phí thực hiện**, có thể đếm số bước hoặc số phép so sánh;
- `A(x,R)` là kết quả thuật toán trả về;
- `f(x)` là kết quả toán học đúng.

Khi đó **thời gian kỳ vọng** là:

```text
E_R[T(x,R)].
```

**Xác suất sai** là:

```text
Pr_R[A(x,R) != f(x)].
```

Cả hai đều đo xác suất **theo lựa chọn ngẫu nhiên R của thuật toán khi input x đã cố định**, nhưng là hai biến/biến cố khác nhau:

| Đại lượng | Đang đo | Ví dụ khẳng định |
| --- | --- | --- |
| `E[T(x,R)]` | Trung bình chi phí qua các lựa chọn R | `E[T(x,R)] = O(n log n)` |
| `Pr[A(x,R) != f(x)]` | Tỷ lệ các lựa chọn R dẫn tới **đáp án sai** | `Pr[error] <= 0.01` |
| `Pr[T(x,R)>t]` | Xác suất vượt **ngân sách thời gian t** | `Pr[T>100n] <= 0.001` |
| `max_R T(x,R)` | Thời gian xấu nhất trên mọi kết quả ngẫu nhiên | Có thể là `Theta(n^2)` |

**Không được suy từ một hàng sang hàng khác** nếu không có lập luận bổ sung. Chẳng hạn `E[T]=100` không có nghĩa xác suất sai là 1/100. Tương tự, xác suất sai 1/100 không chứng minh thời gian kỳ vọng bằng 100.

### 1.1. Kỳ vọng là trung bình có trọng số

Nếu `T` nhận các giá trị `t1,t2,...` với xác suất `p1,p2,...`, thì:

```text
E[T] = SUM_i (pi * ti)
```

Ví dụ một thuật toán **luôn trả đúng**, nhưng:

```text
T = 1 bước   với xác suất 99/100
T = 1000 bước với xác suất 1/100

E[T] = 0.99*1 + 0.01*1000
     = 10.99 bước.

Pr[trả sai] = 0.
```

Một số lần chạy rất chậm vẫn có thể xuất hiện dù kỳ vọng thấp. Đây là câu chuyện về **đuôi phân phối thời gian**, không phải về đáp án sai.

### 1.2. Xác suất sai là xác suất một biến cố

Ví dụ khác, thuật toán luôn dùng đúng `n` bước, nhưng khi trả lời thì chọn đáp án sai với xác suất 0.1:

```text
T = n luôn luôn
E[T] = n

Pr[error] = 0.1
```

Thời gian không ngẫu nhiên nhưng đáp án có thể sai. Đây là phản ví dụ trực tiếp cho suy luận “thời gian chạy ổn định thì thuật toán chính xác”.

### 1.3. Đầu vào ngẫu nhiên không giống thuật toán ngẫu nhiên

**Phân tích average-case** có thể lấy kỳ vọng theo phân phối đầu vào `X`:

```text
E_X[T(X)].
```

**Thuật toán ngẫu nhiên hóa** thường lấy kỳ vọng theo random coins `R` **cho từng input x cố định**:

```text
E_R[T(x,R)].
```

Nếu cả input lẫn thuật toán đều ngẫu nhiên, ta phải nói rõ mình xét `E_X E_R[T(X,R)]` với giả thiết phù hợp. Không được tự động thay phát biểu “nhanh trên đầu vào trung bình” thành “nhanh theo kỳ vọng trên mọi đầu vào” — đầu vào cố định do đối thủ chọn có thể làm thay đổi bảo đảm.

## 2. Hai họ thuật toán: Las Vegas và Monte Carlo

### 2.1. Las Vegas: kết quả đúng, thời gian có thể ngẫu nhiên

**Las Vegas algorithm**: khi trả một kết quả, thuật toán **bảo đảm kết quả đúng** theo đặc tả; số phép thử/thời gian có thể ngẫu nhiên.

Trong cách mô hình hóa tiêu chuẩn, thuật toán kết thúc với xác suất 1 (*almost surely*) và có thời gian kỳ vọng hữu hạn nếu đã chứng minh được. Không nên hiểu câu “xác suất 1” thành “mỗi đường chạy đều có thời gian giới hạn chung”. Một chuỗi lựa chọn cực kỳ không may có thể dẫn đến quá nhiều bước; với vòng thử lại không giới hạn, không tồn tại ngân sách thời gian hữu hạn bảo đảm kết thúc với mọi chuỗi kết quả ngẫu nhiên.

Ví dụ điển hình là **randomized quicksort** với pivot chọn ngẫu nhiên: nếu thực thi hoàn tất, mảng sắp xếp luôn đúng. Chọn pivot kém có thể khiến chi phí tăng, nhưng không biến mảng đã sort thành đáp án sai.

**Đặc tính cần chứng minh:**

```text
For every valid fixed input x:
  Pr_R[algorithm returns an incorrect result] = 0.

Then analyze separately:
  E_R[T(x,R)] <= g(n).
```

Lưu ý một triển khai cụ thể vẫn có thể mắc lỗi lập trình như tràn số, lỗi bộ nhớ hoặc stack overflow; tuyên bố Las Vegas nói về **thuật toán toán học được cài đặt đúng**, không phủ nhận lỗi phần mềm.

### 2.2. Monte Carlo: chi phí bị chặn, có thể trả sai

**Monte Carlo algorithm**: thường dành ngân sách thời gian hoặc số vòng hữu hạn đã xác định, trả kết quả nhanh nhưng cho phép một xác suất sai được kiểm soát.

```text
For every valid fixed input x:
  T(x,R) <= g(n,k)  (nếu thiết kế số vòng bị chặn)

And:
  Pr_R[incorrect result] <= epsilon(n,k).
```

Ở đây `k` là số lần lặp độc lập, `epsilon` là cận lỗi. Kết quả có thể sai dù chương trình kết thúc trong ngân sách.

Có hai kiểu sai phổ biến:

- **Sai một phía (one-sided error):** Một loại câu trả lời là chắc chắn đúng; loại còn lại có thể sai với xác suất bị chặn. Ví dụ fingerprint khác nhau chắc chắn suy ra hai dãy khác nhau; fingerprint bằng nhau **có thể là va chạm**.
- **Sai hai phía (two-sided error):** Cả hai loại câu trả lời đều có khả năng sai, nhưng tổng xác suất lỗi bị chặn cho mỗi đầu vào.

**Tên Las Vegas hay Monte Carlo không nói lên độ lớn O(n)**: cần phân tích số phép tính và xác suất sai riêng cho từng thuật toán.

### 2.3. Bảng so sánh cốt lõi

| Câu hỏi | Las Vegas | Monte Carlo |
| --- | --- | --- |
| Có thể trả kết quả sai không? | Không, nếu trả kết quả | Có thể, theo cận xác suất |
| Thời gian có ngẫu nhiên không? | Thường có | Có thể có hoặc cố định |
| Có bảo đảm số vòng hữu hạn cố định không? | Không nhất thiết | Thường được thiết kế để có |
| Bảo đảm chính | **Correctness** + `E[T]` | Cận **error** + cận work |
| Ví dụ | Quicksort pivot ngẫu nhiên, phép thử lại có kiểm chứng | Fingerprint đa thức, kiểm thử tính bằng nhau xác suất |

Một bài toán có thể có cả hai loại lời giải; bản chất phụ thuộc **điều kiện trả lời** và **cách kiểm chứng đáp án**, không phụ thuộc chỉ tên “ngẫu nhiên hóa”.

## 3. Randomized quicksort: kỳ vọng thời gian không phải xác suất sai

Quicksort phân hoạch mảng theo pivot, rồi xử lý đệ quy các phần nhỏ hơn/lớn hơn. Trong biến thể **3-way partition** của mã Java, mỗi phần tử được xếp vào một trong ba nhóm:

```text
< pivot
= pivot
> pivot
```

Pivot được lấy ngẫu nhiên, nhưng **bất biến phân hoạch** vẫn đúng bất kể pivot nào được chọn. Từ đó quy nạp trên độ dài mảng chứng minh hai nhánh đệ quy đã sắp xếp và toàn mảng cuối cùng được sort chính xác. Mảng có nhiều phần tử bằng nhau còn được xử lý tốt nhờ nhóm `= pivot`.

### 3.1. Phân tích thời gian

Với các khóa phân biệt và pivot chọn đồng đều trong đoạn hiện tại, số phép so sánh **kỳ vọng** của quicksort cổ điển là `O(n log n)` trên từng đầu vào có n phần tử, không cần giả thiết input được xáo ngẫu nhiên.

Đối với n khóa phân biệt trong phân tích quicksort tiêu chuẩn, nếu xếp các khóa theo thứ hạng từ 1 đến n, một cặp hạng i<j được so sánh với xác suất:

```text
Pr[key i and key j compared] = 2/(j-i+1).
```

Vì mỗi cặp có thể so tối đa một lần:

```text
E[#comparisons]
  = SUM_{1<=i<j<=n} 2/(j-i+1)
  = O(n log n).
```

Đây là một chứng minh kỳ vọng bằng **biến chỉ báo + tính tuyến tính kỳ vọng**. Mã Java sử dụng quicksort **3-way**, có cùng bậc kỳ vọng `O(n log n)` và xử lý khóa trùng tốt; công thức cặp so sánh ở trên là cho phiên bản phân tích quicksort chuẩn, không phải công thức chính xác cho bộ đếm của mọi triển khai 3-way.

**Worst-case** vẫn có thể là `Theta(n^2)` nếu liên tục chọn các pivot cực lệch trên dữ liệu có khóa phân biệt. Điều này không mâu thuẫn với `E[T]=O(n log n)`: xác suất chuỗi pivot rất xấu có thể nhỏ, song nó không bằng 0 với n hữu hạn.

### 3.2. Sai số xác suất

```text
Pr_R[sorted output is incorrect] = 0.
```

Chọn pivot “xấu” làm việc tốn kém, **không** làm kết quả sai. Không được viết “quicksort ngẫu nhiên có xác suất sai thấp” khi ý muốn nói “có xác suất gặp pivot xấu”. Đó là **xác suất sự kiện chi phí**, không phải lỗi đáp án.

### 3.3. Thời gian kỳ vọng không là deadline

Một lần chạy không có nghĩa phải kết thúc trong `c*n*log(n)` thao tác. Để có bảo đảm thực tế về deadline, cần phân tích **đuôi phân phối** hoặc dùng fallback (ví dụ introsort giới hạn độ sâu rồi chuyển heapsort) nhằm chặn worst-case. Bảo đảm kỳ vọng không thay thế bảo đảm thời gian xấu nhất.

## 4. Fingerprint đa thức: thời gian có thể cố định nhưng trả sai

Xét hai dãy chữ số `a` và `b` cùng độ dài `n`, mỗi phần tử thuộc `{0,...,9}`. Chọn số nguyên tố `p=101` và một phần tử ngẫu nhiên `r` **đồng đều** trong trường hữu hạn `F_101={0,1,...,100}`.

Ta định nghĩa dấu vân tay:

```text
H_r(a) =
  (a0*r^(n-1) + a1*r^(n-2) + ... + a(n-1)) mod 101.
```

Tính bằng quy tắc Horner trong `O(n)`:

```text
hash=0
for each digit from left to right:
    hash=(hash*r+digit) mod 101
```

### 4.1. Khi hai dãy bằng nhau

Nếu `a=b`, mọi hệ số bằng nhau, nên:

```text
H_r(a) = H_r(b) for EVERY r.
```

Vì vậy nếu fingerprint khác nhau, hai dãy **chắc chắn khác nhau**. Ở bài kiểm tra bằng nhau này, kết luận `DIFFERENT` là **đúng tuyệt đối**, không có false negative cho input bằng nhau.

### 4.2. Khi hai dãy khác nhau

Xét đa thức sai khác:

```text
D(X) = H_X(a) - H_X(b)  over F_101.
```

Nếu dãy có cùng độ dài và chữ số trong 0..9, khi `a!=b` có ít nhất một hệ số sai khác khác 0 theo modulo 101 (do chênh lệch từng chữ số nằm trong -9..9). Do đó `D(X)` là một **đa thức khác đa thức 0**, bậc tối đa `n-1`.

Một đa thức khác 0 bậc `d` trên trường chỉ có **tối đa d nghiệm**. Vì chọn `r` đồng đều trong 101 phần tử:

```text
Pr_R[H_r(a) == H_r(b) | a!=b] <= min(1,(n-1)/101).
```

Để cận này mạnh, cần **chọn trường đủ lớn so với độ dài dãy**. Khi `n-1 >= 101`, cận trên trở nên vô ích (>=1); với n lớn phải đổi modulus/kiểu số/thiết kế thay vì tuyên bố đảm bảo nhỏ. Ví dụ này cố ý dùng `n=3`, nên bảo đảm rõ ràng.

### 4.3. Ví dụ chính xác có hai nghiệm

```text
a = [1,0,1] -> P(X)=X^2+1
b = [0,0,2] -> Q(X)=2

D(X)=X^2-1 = (X-1)(X+1).
```

Trong `F_101`, nghiệm là:

```text
r=1
r=100  (tức -1 mod 101).
```

Vậy với một `r` ngẫu nhiên đồng đều:

```text
Pr[false EQUAL for this unequal pair] = 2/101.
```

Ở đây xác suất lỗi **đúng bằng** cận bậc đa thức `2/101`, không phải tỷ lệ đoán. Chương trình kiểm tra kiệt kê đủ **101 giá trị r**, tìm chính xác hai nghiệm `[1,100]`.

### 4.4. Vì sao đây là Monte Carlo?

Thuật toán một vòng đánh giá hai đa thức trong `O(n)` và trả ngay sau kiểm tra. Thời gian **được chặn** bất kể r, nhưng nếu hai dãy khác nhau và r trúng nghiệm D thì nó trả `EQUAL` **sai**. Đây là **sai một phía**: dãy bằng nhau không bao giờ bị kết luận `DIFFERENT`.

**Không được nói “xác suất sai bằng 1/(số bước)”**. Xác suất lỗi đến từ **số nghiệm đa thức chia cho số lựa chọn r**, còn thời gian đến từ **số phần tử dãy** và số vòng kiểm tra — hai phép phân tích độc lập.

## 5. Giảm xác suất sai bằng lặp ngẫu nhiên độc lập

Với `a!=b` như ví dụ, một vòng có xác suất va chạm:

```text
epsilon = 2/101.
```

Lấy `k` giá trị `r1,...,rk` **độc lập và đồng đều**, chỉ trả `EQUAL` nếu **cả k vòng** đều có fingerprint bằng nhau. Dãy bằng nhau vẫn luôn cho `EQUAL`. Dãy khác nhau chỉ bị trả `EQUAL` sai khi **cả k phép thử đều va chạm**:

```text
Pr[false EQUAL after k independent rounds]
   = (2/101)^k        (với ví dụ a,b cụ thể)

For any unequal length-3 decimal arrays:
   Pr[false EQUAL] <= (2/101)^k.
```

Ví dụ:

| k | Cận xác suất sai |
| ---: | --- |
| 1 | `2/101`, khoảng 1.98% |
| 2 | `4/10201`, khoảng 0.0392% |
| 3 | `8/1030301`, khoảng 0.000776% |
| 5 | `(2/101)^5` |

Tổng thời gian trong trường hợp xấu nhất trở thành **`O(k*n)`**, không còn chỉ `O(n)` khi coi k là tham số. Tăng k là một **đánh đổi chi phí để giảm sai**, không biến “kỳ vọng thời gian” thành “xác suất đúng” bằng cách đổi tên.

### 5.1. Điều kiện độc lập quan trọng ra sao?

Nếu cả k vòng dùng **cùng một r**, biến cố va chạm lặp lại y nguyên:

```text
Pr[all k repeats collide] = 2/101,
NOT (2/101)^k.
```

Cần những phép chọn r mới độc lập (hoặc một mô hình cho cận xác suất có điều kiện đủ mạnh). Chạy lại với **cùng seed** PRNG và cùng trình tự r cũng không phải các thử nghiệm độc lập.

### 5.2. Sai một phía và sai hai phía khuếch đại khác nhau

Fingerprint ở ví dụ có tính chất mạnh:

```text
a=b => mỗi vòng EQUAL chắc chắn.
```

Nên có thể dùng quy tắc “**bất kỳ vòng nào khác fingerprint thì DIFFERENT**”, làm lỗi chỉ khi **tất cả** vòng va chạm.

Với một thuật toán **sai hai phía**, không thể tùy ý kết hợp bằng “AND” hay “OR” mà luôn giảm cả hai loại lỗi. Một cách thông dụng là chạy k lần **độc lập**, k lẻ, rồi lấy **đa số** nếu xác suất từng vòng trả sai không quá `1/3` cho mỗi input. Bất đẳng thức tập trung, chẳng hạn Hoeffding, cho:

```text
Pr[majority wrong] <= exp(-k/18)
```

dưới giả thiết các biến lỗi vòng độc lập và `Pr[round wrong] <= 1/3`. Đây là cận trên; hệ số có thể cải thiện bằng phân tích sắc hơn. Điểm cốt lõi là xác suất sai giảm **theo hàm mũ của k**, trong khi công việc tăng tuyến tính theo k.

### 5.3. Chọn k từ ngưỡng lỗi mục tiêu

Nếu mỗi vòng độc lập có lỗi tối đa `epsilon<1`, muốn lỗi không quá `delta` thì cần:

```text
epsilon^k <= delta

k >= ln(delta)/ln(epsilon).
```

Vì `ln(epsilon)<0`, khi chia bất đẳng thức phải giữ đúng hướng suy ra như trên. Chọn:

```text
k = ceil(ln(delta)/ln(epsilon)).
```

Nếu k không đủ lớn hoặc `epsilon>=1`, biểu thức không cho bảo đảm hữu ích. Trong ứng dụng thật cần tính toán phù hợp với số học và mức độ an toàn, không đơn thuần xem `Math.random()` là nguồn ngẫu nhiên an toàn mật mã.

## 6. Mô hình Las Vegas thử đến khi tìm được thành công có kiểm chứng

Giả sử mỗi lần thử độc lập có xác suất `q=1/4` tìm được một phương án **có thể kiểm chứng hoàn toàn đúng**. Nếu chưa qua kiểm chứng thì thử lại; chỉ trả kết quả khi kiểm chứng thành công.

Gọi `N` là số lượt thử, tính cả lượt thành công. Đây là **phân phối hình học**:

```text
Pr[N=k] = (3/4)^(k-1)*(1/4), k=1,2,...

E[N] = 1/q = 4.
```

Bảo đảm về **độ đúng**:

```text
Pr[returned answer is incorrect] = 0
```

nếu bước kiểm chứng đúng tuyệt đối và thuật toán chỉ trả phương án đã kiểm chứng. Với các lượt thử độc lập và q>0, thuật toán kết thúc với xác suất 1, mặc dù **không có số lượt thử hữu hạn cố định** bảo đảm thành công đối với mọi chuỗi kết quả.

### 6.1. Đuôi thời gian khác xác suất sai

Xác suất **chưa thành công sau t lượt**:

```text
Pr[N>t]=(3/4)^t.
```

Ví dụ t=8:

```text
Pr[N>8]=(3/4)^8=6561/65536 ≈ 10.01%.
```

Đây là xác suất **chạy lâu**, không phải xác suất **trả đáp án sai**. Không được lấy `(3/4)^8` làm “xác suất sai” nếu thuật toán không hề trả đáp án trước khi xác minh. Nếu hệ thống buộc phải dừng sau t lượt và trả `UNKNOWN`, đó là **không đưa ra đáp án**, khác với **đưa ra đáp án sai**. Nếu hệ thống đoán một đáp án khi hết hạn, nó đã thay đổi hợp đồng và cần phân tích lỗi mới.

### 6.2. Mô hình minh họa khác thuật toán giải bài thực tế

Trong mã Java, hàm `verifiedGeometricTrials` mô phỏng mỗi lần thử có kết quả thành công khi một phép bốc số trúng 0 trong bốn giá trị. Nó **chỉ là mô hình thời gian** chứ không tự giải một bài toán dữ liệu thực. Ví dụ Las Vegas thực sự trong cùng mã là **quicksort pivot ngẫu nhiên**, với bất biến sắp xếp luôn đúng. Không nên coi số lượt quay trúng 0 là chứng minh độ đúng cho một thuật toán thực tế chưa có bước kiểm chứng ứng viên.

## 7. Kỳ vọng, cận đuôi và worst-case

Ba phát biểu thường gặp:

```text
E[T] <= m
Pr[T > t] <= delta
T <= w for all random choices
```

có mức mạnh khác nhau.

### 7.1. Bất đẳng thức Markov

Với biến thời gian `T>=0` và `a>0`:

```text
Pr[T >= a] <= E[T]/a.
```

Đặt `a=lambda*E[T]` khi `E[T]>0`:

```text
Pr[T >= lambda*E[T]] <= 1/lambda.
```

Ví dụ `E[T]=100` thì:

```text
Pr[T >= 1000] <= 0.1.
```

Đây chỉ là **cận trên yếu nhưng hợp lệ** từ thông tin kỳ vọng. Không thể suy ra xác suất trễ chính xác chỉ từ E[T]. Nếu có cấu trúc phân phối hoặc tính độc lập, có thể chứng minh cận đuôi mạnh hơn.

### 7.2. Kỳ vọng tốt không triệt tiêu worst-case chậm

Với randomized quicksort, vẫn có thể liên tục chọn pivot kém dẫn tới `Theta(n^2)` trên input phân biệt. Sự kiện ấy hiếm dưới phân phối pivot đồng đều, nhưng **kịch bản xấu nhất** vẫn tồn tại. Muốn thời gian xấu nhất `O(n log n)`, có thể dùng thuật toán khác hoặc cơ chế fallback có chứng minh, không chỉ dựa vào “expected O(n log n)”.

### 7.3. Cận thời gian không bảo đảm xác suất đúng

Một thuật toán có thể luôn kết thúc trước deadline và vẫn có xác suất sai dương. Ví dụ fingerprint k vòng có worst-case work `O(k*n)` nhưng có lỗi tối đa `(2/101)^k` cho dãy 3 chữ số khác nhau. Ngược lại, quicksort có xác suất sai 0 nhưng không có thời gian xấu nhất `O(n log n)` chỉ từ việc chọn pivot ngẫu nhiên.

## 8. Nhiều truy vấn, độc lập và xác suất lỗi tổng

Giả sử hệ thống thực hiện m truy vấn, mỗi truy vấn có xác suất trả sai tối đa `delta`, **cho input cố định của truy vấn đó**. Xác suất có **ít nhất một** truy vấn sai thỏa cận hợp:

```text
Pr[at least one error] <= m*delta.
```

Chính xác hơn là `min(1,m*delta)`. Đây là **union bound**, không yêu cầu các truy vấn độc lập. Ví dụ có 1.000 truy vấn, muốn xác suất ít nhất một lỗi ≤0.01, đủ để chọn cận **mỗi truy vấn ≤0.00001**.

**Đừng trộn lẫn:**

- Lặp k lần để **giảm lỗi của một câu trả lời**: thường dùng tích xác suất khi các lần thử độc lập.
- Chạy m bài toán và hỏi **có bất kỳ câu nào sai không**: dùng union bound; xác suất lỗi tổng có thể **tăng** theo m.

Nếu truy vấn mới được **chọn thích nghi dựa trên các hash công khai đã thấy**, phải chứng minh lại bảo đảm xác suất có điều kiện; không tự áp mô hình “mỗi input cố định trước khi r được chọn” trong bối cảnh đối thủ biết trước random coins.

## 9. Khi nào có thể chuyển Monte Carlo thành Las Vegas?

Chỉ khi có **cách kiểm chứng ứng viên trả về chắc chắn đúng** đủ rẻ và có xác suất tìm được ứng viên hợp lệ dương:

```text
loop:
    candidate = randomizedCandidate()
    if verify(candidate) is CERTAIN:
        return candidate
```

Khi `verify` hoàn toàn đáng tin, thuật toán **không trả lời sai**; nhưng thời gian thử lại có thể ngẫu nhiên, cần chứng minh `E[T]` và điều kiện kết thúc.

**Không phải mọi Monte Carlo đều chuyển được dễ dàng.** Với fingerprint, khi hai đa thức có cùng giá trị tại r, chỉ kiểm tra thêm **một fingerprint khác** vẫn không phải chứng minh tuyệt đối hai dãy bằng nhau. Nếu thay bằng phép so sánh đầy đủ từng phần tử, ta có kiểm chứng chính xác nhưng cũng phải tính chi phí so sánh `O(n)`; tính chất/độ phức tạp của thuật toán mới cần phân tích riêng.

Nếu hết thời gian và trả `UNKNOWN`, đó là **không giải quyết được truy vấn** trong ngân sách chứ không nhất thiết là “sai”. Cần định nghĩa rõ hệ thống tính việc từ chối trả lời là lỗi loại nào.

## 10. Chương trình Java 17+ chạy được

Tệp **RandomnessExpectationVsErrorDemo.java** minh họa đồng thời:

- **Las Vegas randomized quicksort 3-way:** chọn pivot bằng `SplittableRandom`, sort đúng với mọi pivot, đo số so sánh.
- **Monte Carlo fingerprint:** các dãy chữ số 0..9, trường nguyên tố 101, đánh giá bằng Horner và lặp k lần với các `r` mới.
- **Kiểm chứng đủ 101 giá trị r** để tìm đúng nghiệm va chạm `[1,100]` cho dãy `[1,0,1]` và `[0,0,2]`.
- **Mô hình thời gian hình học:** thử đến khi bốc số trúng 0, với mỗi lần có xác suất thành công 1/4.
- **Tự kiểm thử:** 3.000 mảng ngẫu nhiên đối chiếu với `Arrays.sort`; 101 giá trị trường kiểm tra số nghiệm fingerprint; kiểm tra dãy bằng nhau không bị báo khác và dãy khác độ dài được nhận diện chính xác.

Trong ví dụ, `SplittableRandom` với seed cố định được dùng để tái lập **stdout**, không nhằm bảo đảm tính ngẫu nhiên mật mã. Các công thức xác suất giả định lựa chọn lý tưởng **đồng đều và độc lập**. Để đối phó input do đối thủ kiểm soát, phải cân nhắc nguồn ngẫu nhiên và việc lộ seed/giá trị r.

```java
import java.util.*;

public class RandomnessExpectationVsErrorDemo {
    static final int PRIME = 101;
    static class Counter {
        long comparisons;
    }

    static void swap(int[] a, int i, int j) {
        int tmp = a[i];
        a[i] = a[j];
        a[j] = tmp;
    }

    static void quicksort3(
            int[] a, int left, int right,
            SplittableRandom rng, Counter counter) {
        if (left >= right) return;
        int pivot = a[left + rng.nextInt(right - left + 1)];
        int lt = left, i = left, gt = right;
        while (i <= gt) {
            counter.comparisons++;
            if (a[i] < pivot) {
                swap(a, lt++, i++);
            } else if (a[i] > pivot) {
                swap(a, i, gt--);
            } else {
                i++;
            }
        }
        quicksort3(a, left, lt - 1, rng, counter);
        quicksort3(a, gt + 1, right, rng, counter);
    }

    // Las Vegas: randomness changes execution cost, not correctness.
    static long randomizedSort(
            int[] a, SplittableRandom rng) {
        Objects.requireNonNull(a, "array");
        Objects.requireNonNull(rng, "random");
        Counter counter = new Counter();
        quicksort3(a, 0, a.length - 1, rng, counter);
        return counter.comparisons;
    }

    static void validateDigits(int[] a) {
        Objects.requireNonNull(a, "array");
        for (int d : a) {
            if (d < 0 || d > 9) {
                throw new IllegalArgumentException(
                        "digits must be in [0,9]");
            }
        }
    }

    // Horner evaluation of polynomial coefficients modulo PRIME.
    static int fingerprint(int[] a, int r) {
        int hash = 0;
        for (int digit : a) {
            hash = (hash * r + digit) % PRIME;
        }
        return hash;
    }

    // Monte Carlo, one-sided error: equal arrays always return true;
    // different arrays may collide at all sampled field elements.
    static boolean probablyEqual(
            int[] a, int[] b, int rounds,
            SplittableRandom rng) {
        validateDigits(a);
        validateDigits(b);
        Objects.requireNonNull(rng, "random");
        if (rounds < 1) {
            throw new IllegalArgumentException(
                    "rounds must be positive");
        }
        if (a.length != b.length) return false;
        for (int i = 0; i < rounds; i++) {
            int r = rng.nextInt(PRIME); // uniform 0,...,100
            if (fingerprint(a, r) != fingerprint(b, r)) {
                return false; // definitely different
            }
        }
        return true; // possible false equality
    }

    // Stylized Las Vegas waiting time:
    // each independent trial has verifiable success probability 1/4.
    static int verifiedGeometricTrials(SplittableRandom rng) {
        int count = 0;
        do {
            count++;
        } while (rng.nextInt(4) != 0);
        return count;
    }

    static void selfTest() {
        SplittableRandom inputRng = new SplittableRandom(77231);
        SplittableRandom pivotRng = new SplittableRandom(41123);
        for (int t = 0; t < 3000; t++) {
            int n = inputRng.nextInt(50);
            int[] a = new int[n];
            for (int i = 0; i < n; i++) {
                a[i] = inputRng.nextInt(-12, 13);
            }
            int[] expected = a.clone();
            Arrays.sort(expected);
            randomizedSort(a, pivotRng);
            if (!Arrays.equals(a, expected)) {
                throw new AssertionError("randomized sort mismatch");
            }
        }

        int[] a = {1, 0, 1};
        int[] b = {0, 0, 2};
        int matches = 0;
        for (int r = 0; r < PRIME; r++) {
            boolean equal = fingerprint(a, r)
                    == fingerprint(b, r);
            boolean expected = (r == 1 || r == 100);
            if (equal != expected) {
                throw new AssertionError(
                        "fingerprint root mismatch at r=" + r);
            }
            if (equal) matches++;
        }
        if (matches != 2) {
            throw new AssertionError("expected 2 roots");
        }
        if (!probablyEqual(a, a, 20,
                new SplittableRandom(24))) {
            throw new AssertionError("false different result");
        }
        if (probablyEqual(a, new int[] {1, 0}, 20,
                new SplittableRandom(24))) {
            throw new AssertionError("length mismatch");
        }
        System.out.println(
                "Self-test: PASS (3000 quicksort arrays, 101 field values)");
    }

    public static void main(String[] args) {
        int[] numbers = {5, 1, 5, 3, 2, 1, 4};
        long comparisons = randomizedSort(
                numbers, new SplittableRandom(20261110L));
        System.out.println(
                "Las Vegas sorted: " + Arrays.toString(numbers)
                + ", comparisons=" + comparisons);

        int[] a = {1, 0, 1};
        int[] b = {0, 0, 2};
        List<Integer> roots = new ArrayList<>();
        for (int r = 0; r < PRIME; r++) {
            if (fingerprint(a, r) == fingerprint(b, r)) {
                roots.add(r);
            }
        }
        System.out.println(
                "Monte Carlo collision roots: " + roots);
        System.out.println("One-round error: 2/101");
        System.out.println("Three-round error: 8/1030301");
        System.out.println(
                "Equal arrays: "
                + probablyEqual(a, a, 3,
                        new SplittableRandom(20261110L)));
        System.out.println(
                "Unequal arrays, three rounds: "
                + probablyEqual(a, b, 3,
                        new SplittableRandom(20261110L)));
        System.out.println(
                "Different lengths: "
                + probablyEqual(a, new int[] {1, 0}, 3,
                        new SplittableRandom(20261110L)));

        SplittableRandom rng = new SplittableRandom(789123L);
        long total = 0;
        for (int i = 0; i < 10000; i++) {
            total += verifiedGeometricTrials(rng);
        }
        System.out.printf(Locale.ROOT,
                "Geometric theoretical E[trials]=4, sample mean=%.3f%n",
                total / 10000.0);
        selfTest();
    }
}
```

### 10.1. Biên dịch và chạy

Sử dụng JDK 17 trở lên:

```bash
javac RandomnessExpectationVsErrorDemo.java
java RandomnessExpectationVsErrorDemo
```

**Stdout chính xác:**

```text
Las Vegas sorted: [1, 1, 2, 3, 4, 5, 5], comparisons=15
Monte Carlo collision roots: [1, 100]
One-round error: 2/101
Three-round error: 8/1030301
Equal arrays: true
Unequal arrays, three rounds: false
Different lengths: false
Geometric theoretical E[trials]=4, sample mean=3.964
Self-test: PASS (3000 quicksort arrays, 101 field values)
```

### 10.2. Giải thích kết quả

**Las Vegas sorted:** Sau các lựa chọn pivot theo seed, mảng được sắp đúng thành `[1,1,2,3,4,5,5]`, trong lần chạy đó bộ đếm ghi **15 lần so sánh với pivot**. Con số 15 là **chi phí của một lần chạy**, không phải giá trị kỳ vọng tổng quát và càng không phải xác suất sai.

**Monte Carlo collision roots:** Liệt kê đủ 101 phần tử trường cho thấy chính xác hai r bằng 1 và 100 gây va chạm cho cặp dãy khác nhau. Vậy một lần rút đồng đều có lỗi **2/101**.

**One-round/Three-round error:** Với **ba vòng độc lập**, xác suất cả ba cùng va chạm là `(2/101)^3=8/1030301`. Đây là phân tích của cặp dãy cụ thể, **không phải** một kết quả thống kê ước lượng từ một lần chạy.

**Equal arrays=true:** Dãy bằng nhau luôn có fingerprint bằng nhau; không có r nào tạo false `DIFFERENT`.

**Unequal arrays, three rounds=false:** Với seed thử nghiệm được hiển thị, chương trình chọn các r dẫn đến ít nhất một vòng fingerprint khác nhau, nên trả `false` (khác nhau). Chỉ một lần chạy trả đúng **không phải bằng chứng** rằng xác suất sai bằng 0.

**Different lengths=false:** Hai dãy khác độ dài bị xác định khác nhau theo so độ dài, không cần đưa ra phỏng đoán xác suất.

**Geometric sample mean=3.964:** Trung bình quan sát được trên 10.000 chuỗi thử là 3.964 lượt, gần kỳ vọng lý thuyết **4 lượt**. Nó chỉ minh họa định luật số lớn và một phân phối thời gian; **không phải xác suất sai 3.964%**.

**Self-test=PASS:** 3.000 mảng kiểm tra sort với `Arrays.sort` và tất cả 101 giá trị trường đối chiếu đúng các nghiệm va chạm. Test hỗ trợ phát hiện lỗi triển khai; chứng minh xác suất ở phần lý thuyết dựa trên **đa thức bậc 2** và tính độc lập của lựa chọn ngẫu nhiên, không dựa trên việc test ít hay nhiều.

## 11. Bảng phân tích độ phức tạp và độ tin cậy

| Thuật toán | Thời gian hoặc chi phí | Xác suất trả sai |
| --- | --- | --- |
| Quicksort 3-way pivot ngẫu nhiên | Kỳ vọng `O(n log n)`; worst-case có thể `O(n²)` | **0**, nếu chạy đúng tới kết thúc |
| Fingerprint một vòng | `O(n)` | Một phía, với dãy dài n: `<=min(1,(n−1)/101)` khi miền chữ số phù hợp |
| Fingerprint k vòng | Worst-case `O(k*n)`; có thể dừng sớm khi thấy khác | `<=((n−1)/101)^k` nếu `(n−1)/101<1`, chọn r độc lập |
| Ví dụ fingerprint n=3, k=3 | Worst-case `O(3n)` | Đúng `8/1030301` cho cặp `[1,0,1]`, `[0,0,2]` |
| Mô hình thử lại q=1/4 | Kỳ vọng 4 lượt; không có giới hạn số lượt cố định trên mọi đường chạy | **0** nếu chỉ trả ứng viên được kiểm chứng chắc chắn |

**Phải ghi rõ phân phối xác suất**: nếu `r` không đồng đều, bị lộ trước khi đối thủ chọn input, hay dùng lại cùng r trong mọi vòng, cận `epsilon^k` nói trên không còn tự động áp dụng.

## 12. Những lỗi thường gặp

1. Coi “expected `O(n log n)`” là “mỗi lần đều chạy `O(n log n)`”.
2. Coi xác suất chạy chậm là xác suất trả sai.
3. Coi xác suất trả sai là kỳ vọng số bước.
4. Không xác định xác suất tính trên lựa chọn R hay phân phối input X.
5. Dùng kết quả trung bình trên input random để khẳng định từng input cố định đều có bảo đảm.
6. Tuyên bố randomized quicksort có thể trả mảng sai chỉ vì chọn pivot không may.
7. Quên quicksort ngẫu nhiên vẫn có các chuỗi pivot tạo worst-case chậm.
8. Coi một lần benchmark đủ để ước lượng kỳ vọng lý thuyết.
9. Chỉ đo E[T] rồi suy cận xác suất trễ chặt mà không có phân phối.
10. Sử dụng Markov như đẳng thức xác suất trễ thay vì **cận trên**.
11. Gộp mọi thuật toán dùng random thành Monte Carlo.
12. Gộp mọi thuật toán dùng random thành Las Vegas.
13. Không phân biệt một kết quả sai với việc trả `UNKNOWN` hoặc timeout.
14. Coi Las Vegas luôn có một số bước tối đa chung cho mọi chuỗi random.
15. Coi dãy fingerprint bằng nhau là chứng minh hai dãy chắc chắn bằng nhau.
16. Coi dãy fingerprint khác nhau là có thể sai trong ví dụ chỉ sai một phía.
17. Quên chứng minh đa thức sai khác không phải đa thức 0 modulo p.
18. Không giới hạn miền chữ số khi dùng prime nhỏ, khiến hai hệ số khác nhau ngoài modulo có thể bằng nhau trong trường.
19. Áp cận `(n−1)/p` như một xác suất nhỏ ngay cả khi nó >=1.
20. Lặp k lần với cùng r rồi nhân xác suất lỗi thành `epsilon^k`.
21. Lặp với cùng seed và cùng chuỗi random rồi gọi là độc lập.
22. Đánh đồng lặp giảm lỗi với việc rút ngắn thời gian; thực tế k vòng thường tăng chi phí.
23. Kết hợp các thuật toán sai hai phía bằng AND mà không phân tích hai kiểu lỗi.
24. Dùng majority vote nhưng quên giả thiết độc lập.
25. Nhầm cận xác suất một truy vấn với cận hệ thống có m truy vấn.
26. Dùng union bound cho một truy vấn lặp k vòng rồi suy nó làm lỗi giảm.
27. Dùng lỗi thực nghiệm 0 trên một số test để tuyên bố xác suất sai bằng 0.
28. Cho rằng nguồn giả ngẫu nhiên seeded trong demo là bảo mật mật mã.
29. Cho phép đối thủ nhìn r rồi chọn input và vẫn dùng bảo đảm theo input cố định.
30. Chỉ kiểm thử dãy bằng nhau mà không thử các cặp khác nhau có va chạm.
31. Chỉ kiểm thử input thường mà không xác nhận định dạng và điều kiện giới hạn dữ liệu.
32. Quên tính chi phí kiểm chứng ứng viên trong thuật toán thử đến khi đúng.
33. Tuyên bố một thuật toán có thể sửa lỗi bằng retry nhưng không có cách kiểm chứng tuyệt đối ứng viên.
34. Dùng một cận trung bình mà không xác định biến chi phí đo là bước, so sánh, I/O hay thời gian thực.
35. Không nói rõ kỳ vọng và xác suất được lấy với **đầu vào cố định** hay một phân phối đầu vào.

## 13. Bài tập tự luyện có lời giải

**Bài 1.** Cho T=1 với xác suất 0.99, T=1000 với xác suất 0.01. Tính E[T].

**Lời giải:** `0.99*1+0.01*1000=10.99`. Không suy ra xác suất sai.

**Bài 2.** Thuật toán luôn đúng, nhưng thời gian ngẫu nhiên. Có thể là Las Vegas không?

**Lời giải:** Có, nếu khi trả kết quả nó luôn đúng; còn phải phân tích khả năng kết thúc và kỳ vọng riêng.

**Bài 3.** Thuật toán luôn dùng n bước nhưng sai với xác suất 0.1, đó thuộc kiểu nào?

**Lời giải:** Monte Carlo với xác suất sai 0.1; E[T]=n.

**Bài 4.** Randomized quicksort chọn pivot không may có làm mảng sort sai không?

**Lời giải:** Không nếu cài đặt đúng; chỉ làm tăng số phép so sánh.

**Bài 5.** Quicksort có E[T]=O(nlogn) thì có bảo đảm worst-case O(nlogn) không?

**Lời giải:** Không; pivot lệch liên tiếp có thể tạo Theta(n²).

**Bài 6.** Fingerprint hai dãy bằng nhau có thể khác nhau khi r thay đổi không?

**Lời giải:** Không, đa thức hệ số giống nhau cho cùng giá trị tại mọi r.

**Bài 7.** Khi hai fingerprint khác nhau, dãy có chắc chắn khác nhau không?

**Lời giải:** Có, trong đúng hệ mã hóa đã định nghĩa.

**Bài 8.** Với a=[1,0,1], b=[0,0,2], đa thức sai khác là gì?

**Lời giải:** `D(r)=r²−1`.

**Bài 9.** Trên F101, hai nghiệm của D(r) là gì?

**Lời giải:** `r=1` và `r=100`.

**Bài 10.** Một vòng random r đồng đều từ F101 có xác suất false equality bao nhiêu?

**Lời giải:** Chính xác `2/101`.

**Bài 11.** Ba vòng độc lập có xác suất lỗi bao nhiêu?

**Lời giải:** `(2/101)^3=8/1030301`.

**Bài 12.** Ba vòng dùng cùng r có giảm lỗi xuống lập phương không?

**Lời giải:** Không, vẫn `2/101` trong ví dụ vì sự kiện va chạm lặp lại.

**Bài 13.** Một thuật toán có lỗi <=0.01/vòng và lặp 4 lần độc lập với quy tắc “mọi vòng phải cùng sai” thì cận là gì?

**Lời giải:** `0.01^4=10^-8`, với giả thiết sự kiện sai tương ứng độc lập và quy tắc tổng hợp đúng.

**Bài 14.** Tại sao fingerprint dùng p=101 không cho cận lỗi hữu ích với dãy rất dài n=1000?

**Lời giải:** Cận bậc `(n−1)/101=999/101 >1` là vô ích; cần trường lớn hơn hoặc thiết kế khác.

**Bài 15.** Trong mô hình geometric, xác suất thành công mỗi lượt là 1/4. E[N]?

**Lời giải:** `E[N]=1/(1/4)=4`.

**Bài 16.** Xác suất chưa thành công sau 8 lượt là bao nhiêu?

**Lời giải:** `(3/4)^8=6561/65536 ≈ 10.01%`. Đây là thời gian đuôi, không phải lỗi trả đáp án.

**Bài 17.** Thuật toán chỉ trả khi kiểm chứng chắc chắn đúng; chạy quá hạn rồi báo UNKNOWN. Có là trả sai không?

**Lời giải:** Không, nếu UNKNOWN được định nghĩa là từ chối trả kết luận, không phải một trong các đáp án đúng/sai.

**Bài 18.** Markov cho E[T]=100, P[T>=1000] tối đa bao nhiêu?

**Lời giải:** `<=100/1000=0.1`.

**Bài 19.** Có thể suy chính xác P[T>=1000] từ E[T]=100 không?

**Lời giải:** Không, nhiều phân phối có cùng kỳ vọng nhưng đuôi khác nhau.

**Bài 20.** Có 1.000 truy vấn, mỗi truy vấn lỗi <=10^-5. Cận xác suất có ít nhất một lỗi?

**Lời giải:** Union bound `<=1000*10^-5=0.01`.

**Bài 21.** Union bound cần truy vấn độc lập không?

**Lời giải:** Không; chỉ cần cận trên xác suất của từng biến cố lỗi trong mô hình phù hợp.

**Bài 22.** Muốn giảm lỗi hai phía từ <=1/3 bằng cách lặp độc lập, chiến lược phổ biến?

**Lời giải:** Dùng số vòng lẻ và lấy đa số, phân tích bằng cận tập trung như Hoeffding.

**Bài 23.** Nếu mỗi vòng lỗi 1/3, sau k vòng lẻ độc lập, một cận Hoeffding đơn giản?

**Lời giải:** `Pr[majority wrong] <= exp(-k/18)`.

**Bài 24.** Một báo cáo “expected runtime <=n²” có chứa thông tin lỗi đáp án không?

**Lời giải:** Không, vì nó chỉ mô tả chi phí T; cần chứng minh correctness/error riêng.

**Bài 25.** Khi nào có thể chuyển cách sinh ứng viên Monte Carlo thành thuật toán thử lại Las Vegas?

**Lời giải:** Khi có phép kiểm chứng ứng viên chắc chắn đúng, chỉ trả ứng viên đã qua kiểm chứng và có xác suất tìm được ứng viên hợp lệ dương để kỳ vọng hữu hạn.

**Bài 26.** Nếu r bí mật nhưng sau đó bị công khai trước khi đối thủ chọn dãy, bảo đảm collision còn theo cặp input cố định không?

**Lời giải:** Không tự động; đối thủ có thể chọn cặp phụ thuộc r. Cần mô hình và chứng minh lại.

**Bài 27.** Trong mã quicksort, `comparisons=15` là gì?

**Lời giải:** Bộ đếm của **một lần chạy** với mảng/seed cụ thể, không phải E[T] và không phải lỗi xác suất.

**Bài 28.** Trung bình số lượt thử đo được 3.964 có chứng minh E[N]=3.964 không?

**Lời giải:** Không; lý thuyết cho E[N]=4, 3.964 chỉ là trung bình mẫu của 10.000 lần mô phỏng.

**Bài 29.** Vì sao đầu vào đã cố định quan trọng trong phát biểu xác suất sai Monte Carlo?

**Lời giải:** Vì ngẫu nhiên R của thuật toán được chọn cho từng x, và cận phải áp dụng với mỗi x; nếu x phụ thuộc R thì điều kiện chứng minh có thể mất.

**Bài 30.** Nêu hai phát biểu độc lập cần trình bày cho một randomized algorithm.

**Lời giải:** `E_R[T(x,R)] <= g(n)` (chi phí) và `Pr_R[A(x,R) != f(x)] <= epsilon` (độ đúng), cùng phạm vi input và phân phối R rõ ràng.

## 14. Checklist khi đọc một chứng minh thuật toán ngẫu nhiên

- [ ] Input x cố định hay lấy từ một phân phối ngẫu nhiên?
- [ ] Random coins R được chọn đồng đều, độc lập không?
- [ ] Biến thời gian T đo đơn vị nào?
- [ ] Nói về `E[T]`, cận đuôi `Pr[T>t]` hay worst-case?
- [ ] Cụ thể biến cố sai là gì, khác timeout/UNKNOWN thế nào?
- [ ] Thuật toán Las Vegas hay Monte Carlo theo hợp đồng đầu ra?
- [ ] Nếu Monte Carlo, lỗi một phía hay hai phía?
- [ ] Nếu lặp k vòng, công thức giảm lỗi có đủ giả thiết độc lập không?
- [ ] Chi phí thời gian/bộ nhớ sau khi lặp đã tính lại chưa?
- [ ] Nếu dùng hash hoặc fingerprint, đã chứng minh miền đầu vào tạo đa thức sai khác không zero?
- [ ] Nếu áp dụng trên nhiều truy vấn, đã tính xác suất **ít nhất một lỗi** chưa?
- [ ] Nếu có đối thủ biết seed, mô hình xác suất có còn hợp lệ không?
- [ ] Kết quả chạy test chỉ là bằng chứng thực nghiệm, không thay chứng minh xác suất?
- [ ] Đã tách rõ correctness với phân phối thời gian trong lời giải cuối?

## Kết luận

**Kỳ vọng thời gian** và **xác suất sai** là hai thuộc tính độc lập:

```text
E_R[T(x,R)]               = chi phí trung bình theo random coins
Pr_R[A(x,R) != f(x)]      = xác suất trả đáp án sai
Pr_R[T(x,R)>t]            = xác suất chạy quá ngưỡng t
```

**Randomized quicksort** minh họa thời gian kỳ vọng tốt, có thể chạy chậm ở một số pivot nhưng **không sai đáp án**. **Fingerprint đa thức** minh họa thuật toán kết thúc trong ngân sách và có lỗi một phía được tính từ **số nghiệm đa thức**, có thể giảm theo lũy thừa bằng các vòng độc lập. **Vòng thử lại Las Vegas** minh họa kỳ vọng số thử hữu hạn nhưng không phải một deadline chắc chắn.

Khi thiết kế thuật toán ngẫu nhiên, hãy luôn viết **hai chứng minh riêng**: một chứng minh cho *thời gian/chi phí*, một chứng minh cho *xác suất kết quả sai*, rồi mới đánh đổi số lần thử, độ tin cậy và ngân sách hệ thống.
