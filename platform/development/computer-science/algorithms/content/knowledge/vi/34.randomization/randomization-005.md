# Lấy mẫu có hoàn lại và không hoàn lại

**Lấy mẫu ngẫu nhiên** (*random sampling*) là việc chọn một số phần tử từ một **quần thể** (*population*) theo một quy luật xác suất xác định. Trong thuật toán ngẫu nhiên hóa, hai mô hình cơ bản là **lấy mẫu có hoàn lại** (*sampling with replacement*) và **lấy mẫu không hoàn lại** (*sampling without replacement*). Chỉ thay đổi một quy tắc nhỏ — một phần tử có được đưa trở lại tập có thể chọn hay không — nhưng phân phối kết quả, tính độc lập, số lượng phần tử có thể lấy và thuật toán triển khai đều thay đổi đáng kể.

Bài học tập trung vào **lấy mẫu đồng đều** (*uniform sampling*): mỗi vị trí hợp lệ của nguồn có cùng cơ hội được chọn. Để phân biệt thật rõ các đối tượng, ta dùng hai khái niệm:

- **Quần thể** là n vị trí/chỉ số phân biệt \(0,1,\ldots,n-1\). Hai vị trí có thể chứa **cùng giá trị** nhưng vẫn là hai phần tử nguồn khác nhau.
- **Cỡ mẫu** k là số lần chọn hoặc số vị trí cần lấy. Trong mô hình **có hoàn lại**, k có thể lớn hơn n. Trong mô hình **không hoàn lại**, phải có \(0\le k\le n\).

Sau khi hiểu phân phối xác suất, ta sẽ cài đặt **lấy mẫu có hoàn lại**, **partial Fisher–Yates shuffle**, **reservoir sampling cho dữ liệu luồng** và **thuật toán Floyd chọn k chỉ số phân biệt**, phân tích tính đồng đều của từng phương pháp, tính toán xác suất và phương sai, lưu ý các trường hợp không đồng đều (*weighted sampling*), mã **Java 17+ độc lập** có hạt giống ngẫu nhiên cố định, kết quả chạy xác định và các kiểm thử liệt kê toàn bộ trường hợp nhỏ.

## 1. Mô hình bài toán và thuật ngữ

Giả sử ta có một danh sách nguồn:

~~~text
index:    0  1  2  3  4
value:    A  B  C  D  E
~~~

Quần thể có **n=5 vị trí phân biệt**. Ta muốn lấy k phần tử.

**Có hoàn lại:** sau khi chọn một vị trí, vị trí đó tiếp tục được phép xuất hiện ở lần chọn sau. Ví dụ lấy k=4:

~~~text
[A, C, A, E]
~~~

Giá trị A được chọn hai lần, hoàn toàn hợp lệ.

**Không hoàn lại:** sau khi chọn một vị trí, vị trí đó bị loại khỏi những vị trí còn có thể chọn trong cùng lượt lấy mẫu. Ví dụ:

~~~text
[D, A, C]
~~~

Ba vị trí khác nhau. Nếu nguồn chỉ có 5 vị trí, không thể lấy 6 vị trí khác nhau.

### “Hoàn lại” không có nghĩa phải sửa danh sách gốc

Hai mô hình là **quy luật chọn**, không phải yêu cầu thực sự xóa/chèn phần tử của danh sách.

- Lấy mẫu có hoàn lại có thể chỉ gọi `rng.nextInt(n)` nhiều lần.
- Lấy mẫu không hoàn lại có thể hoán vị một **bản sao** của danh sách hoặc giữ một `Set<Integer>` chứa chỉ số đã chọn.
- Cả hai đều có thể **không làm thay đổi nguồn**, như mã Java trong bài.

### Mẫu có thứ tự và mẫu không có thứ tự

Nếu kết quả là dãy theo thứ tự rút, `[A,B]` và `[B,A]` là **hai kết quả khác nhau**.

Nếu chỉ quan tâm đến **tập vị trí được chọn**, `{A,B}` và `{B,A}` là **một kết quả**. Cần thống nhất điều này trước khi đếm số kết quả hoặc kiểm phân phối.

Trong bài, `withReplacement` và `withoutReplacement` trả **dãy theo thứ tự chọn**; `floydIndices` trả **tập chỉ số được sắp tăng** (không cam kết thứ tự rút). `reservoirSample` trả một danh sách chứa tập mẫu đồng đều, nhưng **thứ tự trong reservoir không phải thứ tự xuất hiện ban đầu và không được coi là một hoán vị ngẫu nhiên đồng đều**.

## 2. Lấy mẫu có hoàn lại: độc lập giữa các lượt

Với quần thể n vị trí, mỗi lượt lấy một chỉ số:

\[
I_t\sim\mathrm{Uniform}\{0,\ldots,n-1\}.
\]

Vì sau khi chọn tập có thể chọn **không đổi**, nên khi sử dụng các phép rút ngẫu nhiên độc lập:

\[
\boxed{P(I_t=i)=1/n\quad\text{ở mọi lượt }t.}
\]

Và:

\[
\boxed{P(I_1=i_1,\ldots,I_k=i_k)=\left(\frac1n\right)^k.}
\]

Một dãy độ dài k có **n^k khả năng có thứ tự**, mỗi dãy xác suất bằng \(1/n^k\).

### Ví dụ n=3, k=2

Với quần thể [A,B,C], có đúng **9 dãy kết quả**:

~~~text
(A,A) (A,B) (A,C)
(B,A) (B,B) (B,C)
(C,A) (C,B) (C,C)
~~~

Mỗi dãy xác suất **1/9**.

Ba kết quả (A,A), (B,B), (C,C) có lặp; vì vậy xác suất hai lượt lấy trùng nhau là:

\[
\boxed{P(I_1=I_2)=3/9=1/3.}
\]

Đó là tính chất đúng của mẫu có hoàn lại, **không phải lỗi của bộ sinh ngẫu nhiên**.

### Khi k lớn hơn n

Với n=5 và k=9, mô hình có hoàn lại vẫn hợp lệ. Theo nguyên lý Dirichlet, trong 9 lượt phải có ít nhất một vị trí được chọn nhiều lần.

Lấy mẫu có hoàn lại thường phù hợp khi:

- Mô phỏng các phép thử độc lập từ cùng một phân phối.
- Thực hiện **bootstrap** trên một tập dữ liệu.
- Chọn phần tử thử nghiệm nhiều lần mà không muốn loại trừ lựa chọn đã dùng.
- Ước lượng Monte Carlo dựa trên các quan sát độc lập có cùng phân phối.

## 3. Lấy mẫu không hoàn lại: phụ thuộc giữa các lượt

Với mẫu **không hoàn lại đồng đều**, ta chọn đều trong những vị trí **còn lại**:

- Lượt đầu: n lựa chọn, mỗi lựa chọn xác suất 1/n.
- Lượt hai: n−1 lựa chọn còn lại, xác suất có điều kiện 1/(n−1).
- Lượt ba: n−2 lựa chọn còn lại.
- Cứ thế tới lượt k, với k≤n.

Đối với một dãy **k chỉ số phân biệt** có thứ tự, xác suất:

\[
\boxed{
P(I_1=i_1,\ldots,I_k=i_k)
=\frac1{n(n-1)\cdots(n-k+1)}.
}
\]

Số dãy có thứ tự là:

\[
\boxed{P(n,k)=\frac{n!}{(n-k)!}.}
\]

Mỗi dãy hợp lệ có xác suất \(1/P(n,k)\).

Nếu không quan tâm thứ tự chọn, số tập con k phần tử là:

\[
\boxed{\binom nk=\frac{n!}{k!(n-k)!}.}
\]

Mỗi tập con được chọn với xác suất:

\[
\boxed{1/\binom nk}.
\]

Vì một tập con k phần tử có đúng k! thứ tự rút và mọi thứ tự hợp lệ có xác suất như nhau, nên phương pháp rút đều liên tiếp **tạo tập con đồng đều**.

### Ví dụ n=3, k=2

Các dãy có thứ tự:

~~~text
(A,B) (A,C)
(B,A) (B,C)
(C,A) (C,B)
~~~

Có **3×2=6** dãy, mỗi dãy xác suất 1/6.

Các tập không thứ tự:

~~~text
{A,B} {A,C} {B,C}
~~~

Có 3 tập, mỗi tập xác suất **1/3**.

**Điểm quan trọng:** hai lần rút không còn **độc lập**. Nếu lượt đầu là A, xác suất lượt hai cũng là A bằng 0, không còn là 1/3.

## 4. Bảng so sánh hai quy luật

| Tiêu chí | Có hoàn lại | Không hoàn lại |
|---|---|---|
| Một vị trí có thể xuất hiện nhiều lần? | Có | Không |
| Giới hạn cỡ mẫu | k≥0, nguồn phải không rỗng nếu k>0 | 0≤k≤n |
| Phân phối ở mỗi lần rút | 1/n trên toàn bộ n vị trí | 1/(số vị trí chưa chọn) |
| Các lượt độc lập? | Có trong mô hình rút độc lập | Không |
| Số dãy có thứ tự | \(n^k\) | \(n!/(n-k)!\) |
| Số tập con k phần tử | Không phải cách đếm đúng cho dãy cho phép lặp | \(\binom nk\) |
| Có thể chọn mọi vị trí đúng một lần nếu k=n? | Không bảo đảm | Có, chắc chắn |
| Thuật toán thường dùng | k lần chọn chỉ số ngẫu nhiên | Partial Fisher–Yates, reservoir, Floyd |
| Dữ liệu luồng không biết trước n | Có thể cần bộ lưu/định nghĩa truy cập khác | Reservoir dùng O(k) nhớ |
| Ví dụ ứng dụng | Bootstrap, rút độc lập, mô phỏng | Chia tập dữ liệu, chọn người không lặp, mẫu khảo sát |

### Với hoàn lại, “không quan tâm thứ tự” là **đa tập**

Nếu chỉ quan tâm những giá trị đã lấy, mẫu có hoàn lại là **multiset** (đa tập), không phải một tập con thông thường. Các đa tập không có xác suất bằng nhau.

Với k=2, n=3:

- Đa tập {A,A} chỉ ứng với **một** dãy (A,A), xác suất 1/9.
- Đa tập {A,B} ứng với **hai** dãy (A,B) và (B,A), xác suất 2/9.

Với số lần xuất hiện \(c_1,\ldots,c_n\), tổng \(c_i=k\), xác suất của đa tập tương ứng là:

\[
\boxed{\frac{k!}{c_1!\cdots c_n!}\frac1{n^k}.}
\]

Không được tuyên bố “mọi đa tập k phần tử đều đồng xác suất” chỉ vì mỗi lượt có hoàn lại chọn đều.

## 5. Xác suất một phần tử xuất hiện trong mẫu

Xét một **vị trí nguồn cụ thể** i.

### Có hoàn lại

Xác suất **không** chọn i trong một lượt là \(1-1/n\). Do các lượt độc lập:

\[
P(\text{i không bao giờ xuất hiện})
=\left(1-\frac1n\right)^k.
\]

Vì vậy:

\[
\boxed{
P(\text{i xuất hiện ít nhất một lần})
=1-\left(1-\frac1n\right)^k.
}
\]

Số lần i xuất hiện trong k lượt có phân phối nhị thức:

\[
C_i\sim\operatorname{Binomial}(k,1/n),
\]

với:

\[
E[C_i]=\frac kn,\quad
\operatorname{Var}(C_i)=k\frac1n\left(1-\frac1n\right).
\]

### Không hoàn lại

Vì mọi tập con k vị trí đều đồng xác suất, xác suất i được chọn là:

\[
P(i\in S)
=\frac{\binom{n-1}{k-1}}{\binom nk}
=\boxed{\frac kn}.
\]

Biến chỉ báo \(Z_i=1\) nếu i được chọn, bằng 0 nếu không, có:

\[
E[Z_i]=k/n.
\]

Vì vị trí không thể chọn hai lần, **không có biến “số lần xuất hiện” lớn hơn 1** cho một vị trí cụ thể.

### Ví dụ n=5, k=2

Có hoàn lại:

\[
P(i\text{ xuất hiện})=1-(4/5)^2=9/25=0.36.
\]

Không hoàn lại:

\[
P(i\text{ xuất hiện})=2/5=0.4.
\]

Sự khác biệt có nghĩa: với cùng hai lần rút, mô hình có hoàn lại đôi khi “phí” một lượt để chọn lại chính phần tử cũ.

## 6. Số phần tử phân biệt và bài toán trùng mẫu

Với mẫu có hoàn lại từ n vị trí, đặt \(D\) là **số vị trí nguồn khác nhau** đã xuất hiện sau k lượt.

Đặt \(Z_i=1\) nếu vị trí i từng được chọn. Khi đó:

\[
D=\sum_{i=0}^{n-1}Z_i.
\]

Theo tính tuyến tính của kỳ vọng:

\[
\boxed{
E[D]=n\left[1-\left(1-\frac1n\right)^k\right].
}
\]

Công thức này **không đòi hỏi các Z_i độc lập**, vì kỳ vọng của tổng luôn bằng tổng kỳ vọng khi các kỳ vọng tồn tại.

Với mẫu không hoàn lại và k≤n:

\[
\boxed{D=k}
\]

nếu đếm **vị trí nguồn** phân biệt.

### Xác suất hoàn toàn không có lặp khi có hoàn lại

Nếu k≤n:

\[
\boxed{
P(\text{k lượt đều khác nhau})
=\frac{n(n-1)\cdots(n-k+1)}{n^k}
=\prod_{j=0}^{k-1}\left(1-\frac jn\right).
}
\]

Nếu k>n thì xác suất này bằng 0. Xác suất có ít nhất một lần lặp là 1 trừ xác suất không lặp.

### Liên hệ với nghịch lý ngày sinh

Ngay cả khi k nhỏ hơn n khá nhiều, xác suất trùng có thể không nhỏ. Cùng một cấu trúc xác suất xuất hiện trong **nghịch lý ngày sinh**: chọn k “ngày sinh” độc lập trong n khả năng và hỏi có cặp trùng hay không.

Trong thực hành, muốn chắc chắn **không chọn trùng vị trí**, không nên dựa vào việc “k còn nhỏ so với n” nếu đề yêu cầu tính không lặp tuyệt đối. Hãy dùng đúng thuật toán **không hoàn lại**.

## 7. Lấy mẫu có hoàn lại: thuật toán O(k)

Với mảng/list truy cập ngẫu nhiên `population` dài n, mỗi lượt:

1. Rút chỉ số j đồng đều trong \([0,n)\).
2. Thêm `population[j]` vào kết quả.
3. **Không xóa, không đánh dấu** vị trí vừa chọn.
4. Lặp k lần.

Mã giả:

~~~text
sampleWithReplacement(population, k, rng):
    require k >= 0
    if k > 0: require population.length > 0

    result = []
    repeat k times:
        j = rng.uniformInt(0, population.length - 1)
        result.add(population[j])

    return result
~~~

**Tính đúng:** ở mỗi lượt, j lấy đều từ n chỉ số, nguồn không bị thay đổi, nên mỗi chỉ số có xác suất 1/n. Nếu bộ sinh tạo các lượt ngẫu nhiên độc lập lý tưởng, dãy kết quả có đúng phân phối tích \(1/n^k\).

**Độ phức tạp:** O(k) thời gian và O(k) bộ nhớ cho kết quả; không cần sao chép toàn bộ quần thể.

### Rút chỉ số không thiên lệch

Trong Java:

~~~java
int j = random.nextInt(population.size());
~~~

trả j trong `0..n-1` với phân phối đồng đều theo API. Không nên viết:

~~~java
int j = Math.abs(random.nextInt()) % n;
~~~

vì:

- `Math.abs(Integer.MIN_VALUE)` vẫn là số âm do tràn int.
- Phép chia lấy dư trực tiếp có thể gây **modulo bias** khi phạm vi nguồn không chia hết cho n.
- Bạn đang tự tạo lỗi khó thấy thay vì dùng `nextInt(bound)`.

Để có thể tái lập bài kiểm, hãy truyền một `Random` có **seed cố định** vào hàm. Trong tình huống cần chống dự đoán hoặc có tác động bảo mật, dùng **SecureRandom** thay cho Random; xem phần sau.

## 8. Không hoàn lại bằng partial Fisher–Yates

Nếu dữ liệu nằm sẵn trong một `List<T>` dài n và muốn k≤n phần tử **không trùng chỉ số**, một giải pháp dễ kiểm là **partial Fisher–Yates shuffle**.

Thuật toán trên **bản sao** của danh sách:

~~~text
sampleWithoutReplacement(population, k, rng):
    require 0 <= k <= n
    a = copy(population)

    for i = 0 .. k-1:
        j = uniformly random integer in [i, n-1]
        swap(a[i], a[j])

    return copy(a[0 .. k-1])
~~~

Sau bước i, phần tử ở vị trí i đã được chọn và không bị động vào trong các bước tiếp theo. Vị trí j được lấy từ các vị trí **chưa chốt** \([i,n-1]\).

### Chứng minh tính đồng đều

- Bước 0: phần tử bất kỳ có xác suất 1/n được đặt vào a[0].
- Bước 1: sau khi a[0] đã cố định, phần tử bất kỳ còn lại có xác suất 1/(n−1) vào a[1].
- ...
- Bước k−1: mỗi phần tử còn lại có xác suất 1/(n−k+1).

Do đó mọi **dãy k chỉ số nguồn phân biệt** đều có xác suất:

\[
\boxed{\frac1{n(n-1)\cdots(n-k+1)}}.
\]

Vì vậy mọi **tập con k vị trí** cũng đồng xác suất sau khi bỏ thứ tự.

### Chạy tay với [A,B,C,D,E]

Giả sử k=3:

~~~text
Ban đầu: [A,B,C,D,E]
i=0, j=4: [E,B,C,D,A]  -> chốt E
i=1, j=3: [E,D,C,B,A]  -> chốt D
i=2, j=2: [E,D,C,B,A]  -> chốt C

Kết quả theo thứ tự rút: [E,D,C]
~~~

Đây chỉ là **một đường đi minh họa**. Với seed được dùng trong chương trình Java, kết quả cụ thể có thể khác vì trình tự chỉ số j phụ thuộc PRNG.

### Chi phí

- Sao chép nguồn dài n: **O(n)** thời gian và bộ nhớ.
- Hoán vị k vị trí đầu: O(k) thời gian.
- Sao chép k kết quả: O(k) bộ nhớ đầu ra.

Tổng cho bản không sửa nguồn:

\[
\boxed{\text{O(n+k) thời gian, O(n+k) bộ nhớ kể cả đầu ra}.}
\]

Vì k≤n, thường viết gọn thành O(n) thời gian/bộ nhớ; nhưng nêu O(n+k) giúp thấy rõ phần sao chép. Nếu **được phép thay đổi nguồn**, có thể chạy partial Fisher–Yates tại chỗ với O(k) lần swap và O(k) bộ nhớ cho kết quả. Bài dùng bản sao để **không gây tác dụng phụ** cho caller.

## 9. Không hoàn lại không đồng nghĩa với giá trị khác nhau

Đây là lỗi ngữ nghĩa rất hay gặp.

Nguồn:

~~~text
index:  0  1  2  3
value:  A  A  B  C
~~~

Hai vị trí **0 và 1** chứa cùng giá trị A nhưng là **hai đối tượng nguồn khác nhau**.

Nếu mẫu không hoàn lại chọn các **chỉ số [0,1]**, kết quả theo giá trị là:

~~~text
[A, A]
~~~

Kết quả này **hoàn toàn hợp lệ** đối với lấy mẫu không hoàn lại theo **vị trí**: không có vị trí nào được chọn hai lần.

Nếu yêu cầu nghiệp vụ là **các giá trị khác nhau theo `equals`**, cần định nghĩa một bài toán khác, chẳng hạn:

1. Loại trùng các giá trị trước, tạo quần thể **giá trị phân biệt** rồi lấy mẫu.
2. Hoặc gom theo mã định danh (*id*) nếu các phần tử có thuộc tính trùng nhưng đại diện cho các đối tượng thật khác nhau.
3. Xác định lại phân phối mong muốn: lấy đều trên **vị trí** không giống lấy đều trên **giá trị phân biệt** khi có tần suất lặp.

Không được kiểm “thuật toán lấy mẫu không hoàn lại sai” chỉ vì `new HashSet<>(selectedValues).size()<k` nếu nguồn có các giá trị trùng. Khi kiểm tính không hoàn lại, cần kiểm **chỉ số nguồn** hoặc định danh duy nhất, không chỉ `equals` của giá trị.

## 10. Fisher–Yates và những cách làm sai

### A. Sắp xếp bằng comparator ngẫu nhiên

Một cách viết hấp dẫn nhưng **sai**:

~~~java
list.sort((a, b) -> random.nextBoolean() ? -1 : 1);
~~~

Comparator của sort phải có những tính chất thứ tự nhất quán như **phản đối xứng** và **bắc cầu**. Một comparator trả ngẫu nhiên có thể vi phạm chúng, khiến thuật toán sắp xếp không bảo đảm kết quả hoặc thậm chí báo lỗi.

Muốn hoán vị đồng đều, dùng **Fisher–Yates**, không “sort theo random”.

### B. Mỗi lần swap với một vị trí bất kỳ của cả mảng

Nếu ở mỗi i đều rút j từ \([0,n)\) thay vì \([i,n)\), phương pháp “đổi n lần với chỉ số bất kỳ” **không** tạo mọi hoán vị với xác suất bằng nhau nói chung.

Partial Fisher–Yates phải chọn **trong phần chưa chốt** và loại những vị trí đã chọn khỏi các bước tương lai.

### C. Rút không hoàn lại bằng rejection

Có thể lặp rút ngẫu nhiên từ [0,n) rồi chỉ chấp nhận j chưa xuất hiện. Khi k còn nhỏ so với n, cách này thường chạy nhanh và cho mẫu đồng đều nếu rút hoàn toàn đồng đều, nhưng khi k gần n số lần **rút trùng bị bỏ** tăng mạnh.

Số lần thử kỳ vọng để thu đủ k chỉ số là:

\[
\boxed{
E[\text{draws}]=
\sum_{t=0}^{k-1}\frac{n}{n-t}.
}
\]

Với k=n, đó là \(n H_n=\Theta(n\log n)\), không phải O(n) như Fisher–Yates. Bởi vậy không nên chọn rejection sampling làm giải pháp mặc định khi k lớn.

## 11. Reservoir sampling: lấy mẫu không hoàn lại từ luồng

Khi dữ liệu là một **luồng** hoặc `Iterable<T>` không biết trước tổng số phần tử n, ta không thể dễ dàng chọn một chỉ số ngẫu nhiên trong [0,n) trước khi đọc hết luồng.

**Reservoir sampling** cho phép chọn **k vị trí đồng đều không hoàn lại** chỉ bằng **O(k) bộ nhớ** và duyệt nguồn **một lần**.

Quy tắc chuẩn:

1. Đưa **k phần tử đầu tiên** vào reservoir.
2. Khi gặp phần tử thứ t, đếm từ t=1, với t>k:
   - Rút `j` đồng đều trong \([0,t-1]\).
   - Nếu `j<k`, **thay** phần tử ở `reservoir[j]` bằng phần tử thứ t.
   - Nếu `j>=k`, bỏ qua phần tử mới.
3. Sau khi duyệt hết n phần tử, reservoir chứa một **tập con k vị trí đồng đều**.

Mã giả:

~~~text
reservoirSample(stream, k):
    require k >= 0
    reservoir = []
    seen = 0

    for item in stream:
        seen += 1

        if seen <= k:
            reservoir.add(item)
        else:
            j = random integer in [0, seen-1]
            if j < k:
                reservoir[j] = item

    if seen < k:
        reject "stream shorter than sample size"

    return reservoir
~~~

### Ví dụ k=2

Luồng [A,B,C,D,E]:

- Sau A,B: reservoir=[A,B].
- Gặp C là phần tử thứ 3: chọn j∈[0,2]; với xác suất 2/3, C thay một phần tử trong reservoir.
- Gặp D là phần tử thứ 4: chọn j∈[0,3]; với xác suất 2/4, D được đưa vào reservoir.
- Gặp E là phần tử thứ 5: chọn j∈[0,4]; với xác suất 2/5, E được đưa vào reservoir.

Không phần tử nào được lựa chọn **hai lần**, vì luồng chỉ đi qua mỗi vị trí nguồn một lần và reservoir chỉ chứa phần tử ở vị trí nguồn đang xét hoặc đã xét.

### Chứng minh xác suất bao hàm k/n

Xét phần tử ở vị trí thứ t.

Nếu t≤k, ban đầu nó có mặt chắc chắn trong reservoir; khi xử lý phần tử thứ r>k, xác suất nó **không bị thay** là \(1-1/r=(r-1)/r\). Xác suất nó sống tới cuối n:

\[
\prod_{r=k+1}^{n}\frac{r-1}{r}=\frac kn.
\]

Nếu t>k, khi xuất hiện, nó được giữ với xác suất k/t. Sau đó sống tới n với xác suất:

\[
\prod_{r=t+1}^{n}\frac{r-1}{r}=\frac tn.
\]

Xác suất cuối:

\[
\frac kt\cdot\frac tn=\boxed{\frac kn}.
\]

Vậy mọi vị trí có xác suất xuất hiện bằng k/n.

### Chứng minh mạnh hơn: mọi tập con đều đồng xác suất

Chỉ có **xác suất bao hàm bằng nhau** chưa đủ chứng minh các tập con cùng xác suất. Reservoir còn có một chứng minh quy nạp mạnh hơn:

Giả sử sau t phần tử, mỗi tập con k vị trí có xác suất \(1/\binom tk\).

- Với một tập S **không chứa phần tử mới**, S tồn tại khi trước đó reservoir chính là S và phần tử mới không thay ai. Xác suất:
  \[
  \frac1{\binom tk}\frac{t+1-k}{t+1}
  =\frac1{\binom{t+1}k}.
  \]
- Với một tập S **có chứa phần tử mới**, viết S=T∪{new}, \(|T|=k-1\). Có t−k+1 lựa chọn phần tử cũ x không thuộc T để reservoir trước đó là T∪{x}. Mỗi trạng thái trước có xác suất \(1/\binom tk\), và xác suất x bị thay bởi new là \(1/(t+1)\). Tổng:
  \[
  \frac{t-k+1}{\binom tk(t+1)}
  =\frac1{\binom{t+1}k}.
  \]

Do đó ở mọi thời điểm t≥k, reservoir là **tập con k vị trí đồng đều** của t phần tử đầu.

### Giới hạn cần nêu rõ

- Cần đọc **hết luồng** để có mẫu đồng đều của toàn bộ luồng.
- Thời gian **O(n)**, bộ nhớ **O(k)**; phù hợp khi n lớn và k nhỏ.
- Nếu luồng ngắn hơn k, không thể trả đúng k vị trí phân biệt; phải báo lỗi hoặc có chính sách trả thiếu được ghi rõ.
- Danh sách reservoir **không nhất thiết theo thứ tự nguồn**.
- Bản Java minh họa dùng biến đếm `int`; nếu luồng vượt `Integer.MAX_VALUE` phần tử, phải đổi bộ đếm sang long và dùng phép rút chỉ số long có giới hạn đúng, không được để tràn số.

## 12. Thuật toán Floyd: chọn k chỉ số trong miền lớn

Nếu mục tiêu là chọn k chỉ số phân biệt trong \([0,n)\), n đã biết nhưng n có thể rất lớn so với k, việc sao chép cả quần thể rồi partial Fisher–Yates tốn O(n) bộ nhớ.

**Thuật toán Floyd** (*Floyd’s algorithm for random sampling*) có thể tạo **một tập con k chỉ số đồng đều** với **O(k)** bộ nhớ kỳ vọng bằng một `HashSet`.

Cách làm, với n và k nguyên, 0≤k≤n:

~~~text
selected = empty set

for j = n-k .. n-1:
    t = uniform random integer in [0,j]

    if t not in selected:
        selected.add(t)
    else:
        selected.add(j)

return selected
~~~

Sau vòng cuối, có đúng k chỉ số phân biệt.

### Ví dụ n=5, k=2

Vòng chạy j=3 rồi j=4:

- Ở j=3, chọn t∈[0,3], thêm t.
- Ở j=4, chọn t∈[0,4]. Nếu t chưa được chọn, thêm t; nếu t đã chọn, thêm j=4.

Tổng số cặp lựa chọn cơ bản của t là **4×5=20**, đều có xác suất 1/20. Có \(\binom52=10\) tập con hai phần tử, và thuật toán ánh xạ đúng **2 đường đi** vào mỗi tập con, nên mỗi tập xuất hiện xác suất 2/20=1/10.

### Thứ tự kết quả không phải thứ tự rút

Bản Java trả các chỉ số **đã sort tăng** cho dễ đọc:

~~~text
[0, 1, 8, 9]
~~~

Đây là một **tập chỉ số** được biểu diễn có thứ tự tăng. Không được suy ra “phần tử 0 được rút trước phần tử 1”. Nếu ứng dụng cần **thứ tự rút đồng đều**, hãy trộn ngẫu nhiên k chỉ số đã chọn bằng Fisher–Yates sau đó.

### Độ phức tạp

Nếu thao tác `HashSet` có thời gian kỳ vọng O(1):

- Chọn k chỉ số: O(k) kỳ vọng.
- Bộ nhớ: O(k).
- Nếu cần trả danh sách **sắp tăng**: thêm O(k log k) để sort.

Vì thế mã demo dùng Floyd cho trường hợp k nhỏ, n lớn, **không cần giữ cả n phần tử**. Nhưng nếu nguồn là những đối tượng không có truy cập theo chỉ số, Floyd chỉ tạo các **chỉ số**; muốn lấy giá trị tại các chỉ số ấy từ một stream vẫn cần duyệt dữ liệu/thiết kế lưu trữ thích hợp.

## 13. Chọn thuật toán theo đầu vào

| Yêu cầu | Phương pháp gợi ý | Thời gian | Bộ nhớ phụ, không tính đầu ra |
|---|---|---|---|
| k lượt độc lập, có hoàn lại, truy cập List | `nextInt(n)` k lần | O(k) | O(1) |
| k≤n, không hoàn lại, List có thể copy | Partial Fisher–Yates | O(n+k) | O(n) |
| k≤n, không hoàn lại, được sửa nguồn | Partial Fisher–Yates tại chỗ | O(k) thao tác swap | O(1) |
| n chưa biết, dữ liệu một chiều dạng stream | Reservoir sampling | O(n) | O(k) |
| Chỉ cần k chỉ số từ [0,n), k≪n | Floyd + HashSet | O(k) kỳ vọng; sort O(k log k) | O(k) |
| Chọn tất cả n vị trí một lần theo thứ tự ngẫu nhiên | Fisher–Yates đầy đủ | O(n) | O(1) nếu tại chỗ |
| Chỉ cần mẫu **theo xác suất trọng số** | Thuật toán weighted phù hợp | Phụ thuộc phương pháp | Phụ thuộc phương pháp |
| Đầu vào vô hạn không thể đọc hết | Cần định nghĩa lại “mẫu của toàn bộ luồng” | Không có mẫu đều trên toàn bộ vô hạn dạng đếm được | Tùy định nghĩa |

**Không có một phương pháp duy nhất luôn tối ưu**: cách chọn phụ thuộc dữ liệu có truy cập ngẫu nhiên không, n đã biết chưa, k/n nhỏ hay lớn, có được sửa nguồn không, cần thứ tự hay chỉ tập, và yêu cầu tính bảo mật của ngẫu nhiên.

## 14. Độc lập, phụ thuộc và phương sai ước lượng

Một lý do quan trọng để phân biệt hai mô hình không chỉ là “có lặp hay không”, mà còn là **sai số thống kê của ước lượng**.

Giả sử quần thể hữu hạn có n giá trị thực:

\[
z_1,z_2,\ldots,z_n.
\]

Trung bình quần thể:

\[
\mu=\frac1n\sum_{i=1}^n z_i.
\]

Định nghĩa phương sai quần thể theo **mẫu số n**:

\[
\sigma^2=\frac1n\sum_{i=1}^n(z_i-\mu)^2.
\]

Lấy k giá trị rồi tính trung bình mẫu \(\bar z\).

### Có hoàn lại

Các lượt rút độc lập cùng phân phối đều, nên:

\[
E[\bar z]=\mu,\qquad
\boxed{\operatorname{Var}(\bar z)=\frac{\sigma^2}{k}}
\]

cho k≥1.

### Không hoàn lại

Các lượt **không độc lập**: chọn một giá trị làm giảm số lần giá trị ấy có thể xuất hiện trong mẫu. Với lấy mẫu đồng đều không hoàn lại và n>1:

\[
E[\bar z]=\mu,
\]

\[
\boxed{
\operatorname{Var}(\bar z)
=\frac{\sigma^2}{k}\frac{n-k}{n-1}.
}
\]

Hệ số:

\[
\boxed{\frac{n-k}{n-1}}
\]

được gọi là một dạng của **hiệu chỉnh quần thể hữu hạn** (*finite population correction*) khi \(\sigma^2\) được định nghĩa với mẫu số n. Với quy ước phương sai \(S^2=\sum(z_i-\mu)^2/(n-1)\), công thức tương đương là:

\[
\boxed{\operatorname{Var}(\bar z)=\frac{S^2}{k}\left(1-\frac kn\right)}.
\]

Đừng trộn hai quy ước mẫu số n và n−1 rồi áp sai hệ số điều chỉnh.

### Ví dụ số n=4, k=2

Quần thể [2,4,6,8]:

\[
\mu=5,\qquad
\sigma^2=((2-5)^2+(4-5)^2+(6-5)^2+(8-5)^2)/4=5.
\]

Có hoàn lại:

\[
\operatorname{Var}(\bar z)=5/2=2.5.
\]

Không hoàn lại:

\[
\operatorname{Var}(\bar z)=\frac52\frac{4-2}{4-1}
=\frac53\approx1.6667.
\]

Khi k=n trong mô hình không hoàn lại, mỗi phần tử nguồn được lấy đúng một lần, nên \(\bar z=\mu\) chắc chắn, **phương sai bằng 0**. Trong mô hình có hoàn lại, k=n không bảo đảm thấy đủ mọi vị trí, nên vẫn có sai số mẫu (trừ khi các giá trị quần thể đều giống nhau).

**Trường hợp n=1:** phương sai quần thể bằng 0; công thức có mẫu số n−1 không áp dụng trực tiếp. Với không hoàn lại, k chỉ có thể bằng 0 hoặc 1; khi k=1, trung bình mẫu bằng chính phần tử duy nhất.

## 15. Mẫu đồng đều và mẫu có trọng số khác nhau

Các thuật toán vừa nêu mặc định **mỗi vị trí nguồn có trọng số như nhau**.

Nếu vị trí i có trọng số \(w_i>0\), bài toán **weighted sampling** phải định nghĩa rõ:

- Có hoàn lại: mỗi lượt chọn i với xác suất \(w_i/\sum_jw_j\), các lượt độc lập khi trọng số cố định.
- Không hoàn lại: sau khi chọn một vị trí, vị trí ấy bị loại; nếu rút liên tiếp theo trọng số còn lại, xác suất chọn i ở bước tiếp theo là \(w_i/\sum_{\text{còn lại}}w_j\).
- Có nhiều định nghĩa “mẫu có trọng số không hoàn lại” khác nhau; **xác suất được đưa vào mẫu cuối** nói chung không đơn giản bằng \(k w_i/\sum_jw_j\).

### Ví dụ trọng số 1,2,3

Nếu ba vị trí A,B,C có trọng số [1,2,3], lượt đầu khi có hoàn lại chọn A,B,C với xác suất tương ứng 1/6,2/6,3/6.

Nếu rút **không hoàn lại có trọng số** và lượt đầu chọn C, lượt hai chỉ còn A,B với xác suất 1/3 và 2/3. **Không** tiếp tục chọn C ở lượt hai.

### Thuật toán thích hợp

- Có hoàn lại: dùng phân phối tích lũy + tìm nhị phân, hoặc **alias method** nếu rút rất nhiều lần từ cùng phân phối.
- Không hoàn lại theo mô hình rút từng bước tỉ lệ trọng số: có thể dùng các **khóa ưu tiên ngẫu nhiên** phù hợp (ví dụ exponential race với khóa \(-\ln(U_i)/w_i\), \(U_i\in(0,1]\), chọn k khóa nhỏ nhất) hoặc cấu trúc duy trì tổng trọng số.
- Không được áp dụng Fisher–Yates **đồng đều** rồi kỳ vọng nó tự phản ánh trọng số.

**Phải xử lý trọng số âm, NaN, vô cực và tổng trọng số bằng 0** trước khi gọi thuật toán weighted. Chọn nhầm mô hình trọng số có thể dẫn đến thiên lệch nghiêm trọng dù mã random hoàn toàn đúng.

## 16. Tính tái lập, nguồn ngẫu nhiên và bảo mật

### Seed cố định để kiểm thử

Trong Java:

~~~java
Random random = new Random(2026L);
~~~

Tạo một chuỗi số giả ngẫu nhiên **có thể tái lập** theo thuật toán `java.util.Random`. Điều này hữu ích cho:

- Ví dụ trong tài liệu có đầu ra xác định.
- Kiểm thử tự động và tái hiện lỗi.
- So sánh hai cách cài dưới cùng một giả định kiểm thử.

Tuy nhiên **không sử dụng cùng một đối tượng Random rồi mong các thuật toán trả cùng mẫu**: mỗi thuật toán tiêu thụ số lời gọi PRNG khác nhau. Ví dụ dùng **Random mới với cùng seed** cho mỗi chiến lược để có kết quả riêng ổn định.

### Seed cố định không bảo đảm chất lượng thống kê hay an toàn

`java.util.Random` là bộ sinh **giả ngẫu nhiên**; phù hợp để học, mô phỏng và nhiều công việc thông thường nhưng không được thiết kế cho trường hợp đối thủ cố dự đoán kết quả.

Nếu chọn mã xác thực, rút phần thưởng có giá trị, sinh token, hoặc các tình huống cần tính khó dự đoán, nên dùng **`java.security.SecureRandom`** và thiết kế toàn bộ quy trình an toàn tương ứng.

**Độc lập toán học** trong mô hình có hoàn lại là một giả định về phân phối lý tưởng. PRNG máy tính với seed hữu hạn là **xác định**; nói “các lượt độc lập” trong chứng minh là nói về mô hình xác suất mà bộ sinh được dùng để mô phỏng, không phải tuyên bố các bit thực sự độc lập theo nghĩa toán học vô hạn.

### Tránh modulo bias

Nếu cần chỉ số đều trong \([0,n)\), ưu tiên API `rng.nextInt(n)` thay vì tự lấy `randomNumber % n`. Một API lấy số có giới hạn đúng phải xử lý trường hợp miền PRNG không chia hết cho n, thường bằng một kỹ thuật rejection phù hợp.

## 17. Java 17+: bốn cách lấy mẫu và kiểm thử độc lập

Chương trình **SamplingReplacementDemo.java** dưới đây triển khai:

1. **`withReplacement`**: rút k lần độc lập từ n vị trí, cho phép trùng và k>n.
2. **`withoutReplacement`**: partial Fisher–Yates trên bản sao danh sách, trả k vị trí không lặp theo thứ tự chọn.
3. **`reservoirSample`**: lấy mẫu không hoàn lại của một `Iterable` theo một lượt duyệt, chỉ giữ O(k) phần tử.
4. **`floydIndices`**: chọn k chỉ số phân biệt từ [0,n) mà không cần tạo cả n phần tử, trả kết quả được sắp tăng.
5. Các kiểm thử **liệt kê đúng toàn bộ khả năng** của một số bài toán nhỏ: n=4,k=2 với partial Fisher–Yates, n=5,k=2 với reservoir và Floyd.
6. **600 bộ test ngẫu nhiên** về độ dài, thành viên hợp lệ, tính duy nhất của chỉ số, và việc không sửa nguồn đầu vào.

Mã được thiết kế để học **lấy mẫu đồng đều trên vị trí nguồn**; nó không xử lý weighted sampling hay yêu cầu an toàn mật mã.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.Set;

public class SamplingReplacementDemo {

    // Uniform draws WITH replacement. Repeated positions are allowed.
    static <T> List<T> withReplacement(
            List<T> population, int k, Random rng) {
        Objects.requireNonNull(population, "population");
        Objects.requireNonNull(rng, "rng");

        if (k < 0) {
            throw new IllegalArgumentException(
                "sample size must be nonnegative"
            );
        }
        if (k > 0 && population.isEmpty()) {
            throw new IllegalArgumentException(
                "cannot draw from an empty population"
            );
        }

        List<T> result = new ArrayList<>(k);
        for (int i = 0; i < k; i++) {
            int index = rng.nextInt(population.size());
            result.add(population.get(index));
        }
        return result;
    }

    // Uniform ordered k-tuple WITHOUT replacement.
    // Copy the source so the caller's List is not rearranged.
    static <T> List<T> withoutReplacement(
            List<T> population, int k, Random rng) {
        Objects.requireNonNull(population, "population");
        Objects.requireNonNull(rng, "rng");

        int n = population.size();
        if (k < 0 || k > n) {
            throw new IllegalArgumentException(
                "sample size must be between 0 and population size"
            );
        }

        List<T> copy = new ArrayList<>(population);
        for (int i = 0; i < k; i++) {
            int j = i + rng.nextInt(n - i);
            Collections.swap(copy, i, j);
        }
        return new ArrayList<>(copy.subList(0, k));
    }

    // Uniform k-subset from an Iterable in one pass and O(k) memory.
    // The returned List is not guaranteed to preserve source order.
    static <T> List<T> reservoirSample(
            Iterable<T> source, int k, Random rng) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(rng, "rng");

        if (k < 0) {
            throw new IllegalArgumentException(
                "sample size must be nonnegative"
            );
        }
        if (k == 0) {
            return new ArrayList<>();
        }

        List<T> sample = new ArrayList<>(k);
        int seen = 0;
        for (T item : source) {
            if (seen == Integer.MAX_VALUE) {
                throw new IllegalArgumentException(
                    "stream too long for int-index demonstration"
                );
            }
            seen++;

            if (seen <= k) {
                sample.add(item);
            } else {
                int j = rng.nextInt(seen); // [0, seen)
                if (j < k) {
                    sample.set(j, item);
                }
            }
        }

        if (seen < k) {
            throw new IllegalArgumentException(
                "stream shorter than requested sample size"
            );
        }
        return sample;
    }

    // Floyd: uniformly sample an UNORDERED k-subset of [0, n).
    // Sorting is for stable presentation, not selection order.
    static List<Integer> floydIndices(
            int n, int k, Random rng) {
        Objects.requireNonNull(rng, "rng");
        if (n < 0 || k < 0 || k > n) {
            throw new IllegalArgumentException(
                "sample size must be between 0 and population size"
            );
        }

        Set<Integer> selected = new HashSet<>();
        for (int j = n - k; j < n; j++) {
            int candidate = rng.nextInt(j + 1);
            if (!selected.add(candidate)) {
                selected.add(j);
            }
        }

        List<Integer> result = new ArrayList<>(selected);
        Collections.sort(result);
        return result;
    }

    static void ensure(boolean ok, String detail) {
        if (!ok) {
            throw new AssertionError(detail);
        }
    }

    // Verify the 4*3 equally likely random-index paths
    // map to all 4P2 ordered distinct outputs exactly once.
    static void verifyPartialShuffleExhaustively() {
        boolean[][] visited = new boolean[4][4];
        int paths = 0;

        for (int j0 = 0; j0 < 4; j0++) {
            for (int j1 = 1; j1 < 4; j1++) {
                int[] items = {0, 1, 2, 3};
                int t = items[0];
                items[0] = items[j0];
                items[j0] = t;
                t = items[1];
                items[1] = items[j1];
                items[j1] = t;

                int a = items[0];
                int b = items[1];
                ensure(a != b, "duplicate in partial shuffle");
                ensure(!visited[a][b],
                    "ordered result reached more than once");
                visited[a][b] = true;
                paths++;
            }
        }

        ensure(paths == 12, "wrong number of shuffle paths");
        for (int a = 0; a < 4; a++) {
            for (int b = 0; b < 4; b++) {
                ensure(visited[a][b] == (a != b),
                    "missing or invalid ordered output");
            }
        }
        System.out.println(
            "Partial shuffle enumeration: PASS (12 ordered outcomes)"
        );
    }

    // For n=5,k=2, exactly 3*4*5=60 equiprobable
    // random-index sequences. Each of 10 subsets must
    // arise from exactly 6 sequences.
    static void verifyReservoirExhaustively() {
        int[][] frequency = new int[5][5];

        for (int j3 = 0; j3 < 3; j3++) {
            for (int j4 = 0; j4 < 4; j4++) {
                for (int j5 = 0; j5 < 5; j5++) {
                    int[] reservoir = {0, 1};
                    if (j3 < 2) reservoir[j3] = 2;
                    if (j4 < 2) reservoir[j4] = 3;
                    if (j5 < 2) reservoir[j5] = 4;

                    int a = Math.min(reservoir[0], reservoir[1]);
                    int b = Math.max(reservoir[0], reservoir[1]);
                    ensure(a != b, "duplicate reservoir index");
                    frequency[a][b]++;
                }
            }
        }

        int subsets = 0;
        for (int a = 0; a < 5; a++) {
            for (int b = a + 1; b < 5; b++) {
                ensure(frequency[a][b] == 6,
                    "reservoir subset not uniformly represented");
                subsets++;
            }
        }
        ensure(subsets == 10, "wrong subset count");
        System.out.println(
            "Reservoir enumeration: PASS (10 subsets, 6 paths each)"
        );
    }

    // For n=5,k=2, Floyd uses 4*5=20 equiprobable
    // random-index paths; each of 10 subsets has 2 paths.
    static void verifyFloydExhaustively() {
        int[][] frequency = new int[5][5];

        for (int j3 = 0; j3 < 4; j3++) {
            for (int j4 = 0; j4 < 5; j4++) {
                Set<Integer> selected = new HashSet<>();
                selected.add(j3);
                if (!selected.add(j4)) {
                    selected.add(4);
                }

                List<Integer> sorted = new ArrayList<>(selected);
                Collections.sort(sorted);
                ensure(sorted.size() == 2,
                    "Floyd did not choose two distinct indices");
                frequency[sorted.get(0)][sorted.get(1)]++;
            }
        }

        int subsets = 0;
        for (int a = 0; a < 5; a++) {
            for (int b = a + 1; b < 5; b++) {
                ensure(frequency[a][b] == 2,
                    "Floyd subset not uniformly represented");
                subsets++;
            }
        }
        ensure(subsets == 10, "wrong subset count");
        System.out.println(
            "Floyd enumeration: PASS (10 subsets, 2 paths each)"
        );
    }

    static void verifyRandomizedInvariants() {
        Random test = new Random(42L);
        int cases = 600;

        for (int t = 0; t < cases; t++) {
            int n = test.nextInt(13);
            int k = test.nextInt(n + 1);
            int draws = n == 0 ? 0 : test.nextInt(19);

            List<Integer> source = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                source.add(i);
            }
            List<Integer> before = new ArrayList<>(source);

            List<Integer> without = withoutReplacement(
                source, k, new Random(test.nextLong())
            );
            List<Integer> streaming = reservoirSample(
                source, k, new Random(test.nextLong())
            );
            List<Integer> floyd = floydIndices(
                n, k, new Random(test.nextLong())
            );
            List<Integer> with = withReplacement(
                source, draws, new Random(test.nextLong())
            );

            ensure(without.size() == k
                    && streaming.size() == k
                    && floyd.size() == k
                    && with.size() == draws,
                "wrong sample size");
            ensure(new HashSet<>(without).size() == k,
                "partial shuffle repeated a source index");
            ensure(new HashSet<>(streaming).size() == k,
                "reservoir repeated a source index");
            ensure(new HashSet<>(floyd).size() == k,
                "Floyd repeated a source index");

            for (int value : without) {
                ensure(source.contains(value), "invalid shuffle value");
            }
            for (int value : streaming) {
                ensure(source.contains(value), "invalid reservoir value");
            }
            for (int value : floyd) {
                ensure(source.contains(value), "invalid Floyd value");
            }
            for (int value : with) {
                ensure(source.contains(value), "invalid with-replacement value");
            }
            ensure(source.equals(before), "source was changed");

            for (int i = 1; i < floyd.size(); i++) {
                ensure(floyd.get(i - 1) < floyd.get(i),
                    "Floyd output is not sorted distinct");
            }
        }

        System.out.println(
            "Randomized sample invariants: PASS (" + cases + " cases)"
        );
    }

    public static void main(String[] args) {
        List<String> population =
            List.of("A", "B", "C", "D", "E");

        List<String> with =
            withReplacement(population, 9, new Random(2026L));
        List<String> without =
            withoutReplacement(population, 3, new Random(2026L));
        List<String> streaming =
            reservoirSample(population, 3, new Random(2026L));
        List<Integer> indices =
            floydIndices(10, 4, new Random(2026L));

        System.out.println("Population: " + population);
        System.out.println("With replacement (9): " + with);
        System.out.println("Without replacement (3): " + without);
        System.out.println("Reservoir streaming (3): " + streaming);
        System.out.println(
            "Floyd indices (10 choose 4, sorted): " + indices
        );
        System.out.println(
            "With replacement allows k>n: "
                + (with.size() > population.size())
        );
        System.out.println(
            "Without replacement unique source positions: "
                + (new HashSet<>(without).size() == without.size())
        );
        System.out.println(
            "Empty population, zero draws: "
                + withReplacement(List.of(), 0, new Random(1L))
        );

        verifyPartialShuffleExhaustively();
        verifyReservoirExhaustively();
        verifyFloydExhaustively();
        verifyRandomizedInvariants();

        try {
            withReplacement(List.of(), 1, new Random(1L));
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Empty population rejected: " + e.getMessage()
            );
        }
        try {
            withoutReplacement(population, 6, new Random(1L));
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Oversized no-replacement sample rejected: "
                    + e.getMessage()
            );
        }
        try {
            reservoirSample(List.of("A", "B"), 3, new Random(1L));
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Short stream rejected: " + e.getMessage()
            );
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 SamplingReplacementDemo.java
java SamplingReplacementDemo
~~~

**Stdout xác định với các seed trong chương trình:**

~~~text
Population: [A, B, C, D, E]
With replacement (9): [E, A, C, A, E, D, D, B, E]
Without replacement (3): [E, B, D]
Reservoir streaming (3): [E, B, D]
Floyd indices (10 choose 4, sorted): [0, 1, 8, 9]
With replacement allows k>n: true
Without replacement unique source positions: true
Empty population, zero draws: []
Partial shuffle enumeration: PASS (12 ordered outcomes)
Reservoir enumeration: PASS (10 subsets, 6 paths each)
Floyd enumeration: PASS (10 subsets, 2 paths each)
Randomized sample invariants: PASS (600 cases)
Empty population rejected: cannot draw from an empty population
Oversized no-replacement sample rejected: sample size must be between 0 and population size
Short stream rejected: stream shorter than requested sample size
~~~

**Lưu ý về ví dụ:** hai thuật toán `withoutReplacement` và `reservoirSample` tình cờ trả cùng `[E,B,D]` với cùng seed 2026 trong ví dụ. Điều đó **không** có nghĩa thuật toán cho kết quả giống nhau với mọi seed, cũng không có nghĩa thứ tự reservoir là một hoán vị ngẫu nhiên đồng đều. Điều phải khớp là **phân phối trên tập chỉ số được chọn**, không phải từng kết quả của cùng hạt giống.

## 18. Giải thích từng phần quan trọng của mã Java

### A. With replacement

Hàm rút k chỉ số trong `[0,n)`, không thay đổi nguồn và không ghi nhận những vị trí đã chọn. Đây là lý do phần tử có thể xuất hiện nhiều lần.

Với k=0, hàm trả danh sách rỗng **kể cả khi quần thể rỗng**. Với k>0 và n=0, hàm báo lỗi thay vì gọi `rng.nextInt(0)`.

### B. Partial Fisher–Yates

Hàm tạo `new ArrayList<>(population)` để tránh sửa input. Khi đã chốt a[i] ở vòng i, các vòng sau chỉ rút vị trí từ i+1 trở đi, nên vị trí đã được chọn không thể quay lại.

Mã trả một **bản sao của subList**, không trả một view phụ thuộc vào danh sách nội bộ sẽ bị thay đổi về sau. Không có `HashSet` trong thuật toán partial shuffle; tính không trùng chỉ số đến từ **cấu trúc hoán vị**.

### C. Reservoir

Hàm chỉ giữ k phần tử, không biết n trước khi duyệt. Khi đã gặp `seen` phần tử, phần tử mới được giữ với xác suất k/seen nếu seen>k.

Nếu k=0, mã trả rỗng ngay mà không đọc luồng; đây là một **chính sách API** hợp lệ vì mẫu kích thước 0 không yêu cầu biết n. Nếu k>độ dài luồng, mã ném lỗi **sau khi đọc hết luồng**. Với một nguồn không thể lặp lại, caller cần biết rằng phép thử thất bại đã tiêu thụ luồng.

### D. Floyd

Hàm chỉ trả chỉ số, không chứa giá trị nguồn. Vì dùng `HashSet`, tính đồng đều là trên **các tập** chỉ số, không phải thứ tự duyệt HashSet. Kết quả được `Collections.sort` để có cách biểu diễn xác định.

Với n là `int` không âm và 0≤k≤n, vòng j chạy từ n−k đến n−1; `j+1` luôn nằm trong `[1,n]` và là một bound hợp lệ cho `Random.nextInt`. Không xây một mảng dài n; đó là lý do phù hợp khi n lớn và k nhỏ.

### E. Các kiểm thử có cấu trúc

`verifyPartialShuffleExhaustively` không dựa vào việc “chạy Random rất nhiều lần”. Nó **liệt kê 12 đường đi chỉ số** của partial shuffle với n=4,k=2 và chứng minh mỗi dãy chỉ số khác nhau xuất hiện đúng một lần.

`verifyReservoirExhaustively` liệt kê **3×4×5=60** chuỗi quyết định ngẫu nhiên khi n=5,k=2; kiểm mỗi trong \(\binom52=10\) tập con có **đúng 6 đường đi**.

`verifyFloydExhaustively` liệt kê **4×5=20** chuỗi quyết định khi n=5,k=2; kiểm mỗi tập con có đúng **2 đường đi**.

`verifyRandomizedInvariants` còn thử 600 bộ n,k và các seed khác nhau, kiểm kích thước, thành viên nguồn, không lặp **chỉ số** trong ba phương pháp không hoàn lại, Floyd sorted và nguồn không bị thay đổi.

**Các phép thử liệt kê đầy đủ chỉ chứng minh đúng cho trường hợp n,k nhỏ được liệt kê.** Tính đúng với n,k tổng quát dựa trên **chứng minh xác suất và bất biến** ở các phần trước.

## 19. Kiểm nghiệm tính đồng đều và tránh “test may rủi”

Kết quả từ PRNG có thể trông ngẫu nhiên nhưng thuật toán vẫn thiên lệch. Ví dụ sort với comparator random có thể cho một số thứ tự nhiều hơn những thứ tự khác.

Một chiến lược QA mạnh nên kết hợp:

1. **Chứng minh phân phối:** như xác suất \(1/P(n,k)\) của partial Fisher–Yates và \(\binom nk^{-1}\) của reservoir/Floyd.
2. **Liệt kê toàn bộ các lựa chọn ngẫu nhiên nhỏ:** đếm tần suất chính xác của từng kết quả.
3. **Kiểm bất biến:** đúng kích thước, các chỉ số hợp lệ, không trùng chỉ số nếu không hoàn lại, nguồn không bị thay đổi nếu API hứa điều đó.
4. **Kiểm thống kê với nhiều seed:** tần suất thực nghiệm phải gần phân phối lý thuyết trong sai số lấy mẫu hợp lý; kiểm kiểu này là **bằng chứng thực nghiệm**, không phải chứng minh.
5. **Kiểm biên:** n=0, n=1, k=0, k=1, k=n, k>n, nguồn có giá trị trùng, nguồn rất lớn, luồng ngắn và dữ liệu đầu vào bất hợp lệ.

### Ví dụ kiểm tần suất bao hàm

Với n=5, k=2, mô hình không hoàn lại đồng đều cho mỗi chỉ số xác suất được chọn bằng **2/5=0.4**. Nếu thực hiện nhiều lần lấy mẫu độc lập và đếm số lần một chỉ số xuất hiện, tỉ lệ thực nghiệm sẽ **dao động quanh 0.4**.

Không nên yêu cầu tất cả các chỉ số được chọn đúng bằng nhau trong một số thử nghiệm hữu hạn. Một kết quả thống kê là ngẫu nhiên, nên **sai khác tần suất không tự động chứng minh thuật toán sai**. Ngược lại, tỷ lệ gần 0.4 trong một vài lần chạy cũng không chứng minh phương pháp đồng đều nếu thiếu lập luận đúng đắn.

### Exhaustive test khác randomized test thế nào?

Exhaustive test của n=5,k=2 kiểm **mọi đường đi quyết định ngẫu nhiên** trong bài toán nhỏ, nên có thể xác nhận chính xác 10 tập con với cùng số đường đi; randomized test chỉ thăm một tập hữu hạn đường đi. Kết hợp cả hai thường hiệu quả hơn chỉ chạy hàng triệu lần Monte Carlo.

## 20. Sử dụng trong bootstrap, chia dữ liệu và random algorithms

### Bootstrap

**Bootstrap** thường lấy mẫu **có hoàn lại**, kích thước bằng số quan sát gốc n, để mô phỏng nhiều tập dữ liệu tái lấy mẫu. Vì có hoàn lại, một quan sát có thể xuất hiện nhiều lần và một quan sát khác có thể không xuất hiện trong một bootstrap sample.

Kỳ vọng số **vị trí quan sát phân biệt** trong một bootstrap sample k=n là:

\[
n\left[1-\left(1-\frac1n\right)^n\right]
\approx n(1-e^{-1})\approx0.632n
\]

khi n lớn. Đây là lý do xuất hiện quy tắc trực giác **63,2% quan sát khác nhau** trong bootstrap truyền thống.

### Chia train/test

Khi cần chia các hàng dữ liệu thành train/test sao cho **mỗi vị trí chỉ ở một bên**, thường dùng **shuffle không hoàn lại** hoặc chọn tập chỉ số test không hoàn lại rồi lấy phần bù cho train. Rút có hoàn lại không tạo ngay một phép phân hoạch toàn bộ dữ liệu vì có thể lặp hàng và bỏ sót hàng.

Còn phải xét thêm ràng buộc nhóm và thời gian để tránh data leakage: chọn đều từng hàng có thể không đủ nếu nhiều hàng cùng một người hoặc nhiều mốc của một chuỗi thời gian.

### Randomized algorithms

Trong các thuật toán ngẫu nhiên hóa như chọn pivot cho Quickselect/Quicksort, ta chọn **một pivot** từ miền hiện hành; nếu thuật toán đệ quy trên miền mới, vấn đề không đơn giản là “lấy mẫu k không hoàn lại trên toàn dãy”. Cần xác định tập ứng viên ở từng bước.

Nếu một bài dùng k phần tử ngẫu nhiên khác nhau để thử nghiệm, phân phối theo **tập** hay **thứ tự** có thể ảnh hưởng tính đúng/độ phức tạp kỳ vọng. Không tự thay mẫu không hoàn lại bằng có hoàn lại nếu lời giải dựa vào tính duy nhất.

### A/B testing và chọn người dùng

Nếu muốn chọn k người **khác nhau** cho một đợt khảo sát, nên lấy mẫu theo **ID người dùng** không hoàn lại, không phải theo một bảng chứa nhiều hàng giao dịch của cùng người. Nếu chọn đều theo hàng giao dịch, người có nhiều hàng sẽ có xác suất xuất hiện cao hơn.

Đây là ví dụ cho thấy việc chọn **đơn vị lấy mẫu** còn quan trọng hơn cả kỹ thuật random được cài đúng.

## 21. Biên và lỗi thường gặp

| Trường hợp | Có hoàn lại | Không hoàn lại |
|---|---|---|
| n=0, k=0 | Trả [] | Trả [] |
| n=0, k>0 | Không có vị trí để rút → lỗi | Không thể chọn → lỗi |
| n=1, k=1 | Chọn vị trí duy nhất | Chọn vị trí duy nhất |
| n=1, k=10 | Hợp lệ, lặp một vị trí 10 lần | Không hợp lệ |
| k=0, n>0 | Mẫu rỗng | Mẫu rỗng |
| k=n | Có thể lặp và bỏ sót vị trí | Phải có đủ mọi vị trí đúng một lần |
| k>n | Hợp lệ với n>0 | Lỗi |
| Dữ liệu có hai vị trí cùng giá trị | Có thể rút lại cả vị trí | Có thể hiển thị cùng giá trị dù vị trí khác |
| Nguồn là luồng n chưa biết | Cần định nghĩa truy cập/rút phù hợp | Reservoir một lượt |
| n rất lớn, k nhỏ | Rút k chỉ số | Floyd để không tạo mảng n |
| Yêu cầu thứ tự chọn đều | Các lượt với hoàn lại theo thứ tự | Partial Fisher–Yates |
| Chỉ cần tập con không thứ tự | Có hoàn lại tạo đa tập | Reservoir/Floyd/partial shuffle rồi bỏ thứ tự |

### Danh sách lỗi cần tránh

1. **Nhầm không hoàn lại với “các giá trị phải khác nhau”** khi hai vị trí nguồn chứa cùng giá trị.
2. **Dùng mẫu có hoàn lại khi đề đòi k phần tử phân biệt**, rồi loại trùng sau khi rút mà không điều chỉnh phân phối.
3. **Cho rằng hai lượt không hoàn lại độc lập**, sai xác suất có điều kiện.
4. **Cho rằng mọi đa tập có hoàn lại đồng xác suất**, bỏ qua số hoán vị của mỗi đa tập.
5. **Áp \(1/\binom nk\) cho mẫu có thứ tự**, sai không gian kết quả.
6. **Áp \(1/n^k\) cho mẫu không hoàn lại**, sai mẫu số sau mỗi lượt.
7. **Cho phép k>n trong không hoàn lại**, trả mẫu không đủ k hoặc vòng lặp vô hạn.
8. **Gọi `nextInt(0)`** khi nguồn rỗng và k>0.
9. **Dùng `random.nextInt() % n` và bỏ qua modulo bias** hoặc giá trị âm.
10. **Dùng `Math.abs(Integer.MIN_VALUE)`**, vẫn cho kết quả âm.
11. **Sort bằng comparator ngẫu nhiên**, vi phạm hợp đồng comparator.
12. **Swap mỗi vị trí i với toàn bộ [0,n) thay vì phần chưa chốt**, làm hoán vị bị thiên lệch.
13. **Dùng HashSet để loại trùng nhưng quên xác suất hoặc độ phức tạp rejection khi k gần n**.
14. **Sửa list nguồn mà không có quyền hoặc không thông báo**, làm các bước khác gặp lỗi.
15. **Dùng `subList` view làm kết quả lâu dài trong khi list gốc còn thay đổi**, gây tác dụng phụ bất ngờ.
16. **Reservoir thay thế bằng chỉ số sai phạm vi**: phải rút j trong [0,seen−1].
17. **Reservoir bắt đầu với ít hơn k phần tử dù luồng đủ dài**, làm sai phân phối.
18. **Reservoir luôn giữ phần tử mới**, khiến các phần tử cuối có xác suất quá cao.
19. **Reservoir ghi phần tử mới vào tất cả các slot cùng lúc**, phá tính không hoàn lại.
20. **Hiểu sai thứ tự trong reservoir như thứ tự xuất hiện hoặc một permutation đồng đều**, không được thuật toán bảo đảm.
21. **Không kiểm luồng ngắn hơn k**, trả mẫu thiếu trong khi API hứa đúng k.
22. **Để bộ đếm `seen` overflow**, gọi `nextInt` với bound sai hoặc âm.
23. **Floyd dùng `nextInt(n)` ở mọi vòng thay vì `nextInt(j+1)`**, đổi phân phối.
24. **Floyd không xử lý va chạm trong HashSet bằng cách thêm j**, dẫn tới ít hơn k chỉ số.
25. **Tưởng sorted Floyd output là thứ tự rút**, sai ý nghĩa thứ tự mẫu.
26. **Dùng Fisher–Yates đồng đều cho bài weighted**, không đáp ứng phân phối mong muốn.
27. **Cho rằng weighted without replacement có inclusion probability \(k w_i/\sum w\)** trong mọi mô hình, không đúng nói chung.
28. **Chỉ test không trùng mà không kiểm xác suất**, một thuật toán luôn chọn [0,1,...,k−1] cũng không trùng nhưng không ngẫu nhiên đồng đều.
29. **Dùng Random(seed) cho token bảo mật**, đối thủ có thể dự đoán các giá trị nếu đủ thông tin.
30. **So tần suất mô phỏng bằng giá trị lý thuyết tuyệt đối không có sai số thống kê**, báo lỗi giả.
31. **Bỏ qua ngữ nghĩa đơn vị lấy mẫu**, rút theo bản ghi thay vì theo người/đối tượng cần chọn.
32. **Trộn công thức phương sai quần thể với mẫu số n và mẫu số n−1**, áp sai finite population correction.
33. **Giữ mọi phần tử trong bộ nhớ dù nguồn là stream lớn**, bỏ phí ưu điểm reservoir.
34. **Dùng Floyd chọn chỉ số nhưng nguồn không có random access**, phải đọc stream để lấy giá trị và phân tích lại chi phí.
35. **Không xác định chính sách khi k=0**, dễ làm API xử lý bất nhất.

## 22. Bài tập và câu hỏi tự luyện

**Bài 1.** Quần thể có n=3 vị trí, rút k=2 có hoàn lại. Có bao nhiêu dãy kết quả?

*Đáp án:* \(3^2=9\).

**Bài 2.** Cùng n=3,k=2 nhưng không hoàn lại. Có bao nhiêu dãy có thứ tự?

*Đáp án:* \(3\cdot2=6\).

**Bài 3.** Cùng bài 2, có bao nhiêu tập con không xét thứ tự?

*Đáp án:* \(\binom32=3\).

**Bài 4.** Mẫu có hoàn lại [A,A] có hợp lệ không?

*Đáp án:* Có, vì vị trí đã chọn được phép xuất hiện lại.

**Bài 5.** Mẫu không hoàn lại từ nguồn [A,A,B] có thể có giá trị [A,A] không?

*Đáp án:* Có, nếu hai chữ A ở **hai vị trí nguồn khác nhau**.

**Bài 6.** Với n=5,k=2, xác suất một vị trí cố định xuất hiện ít nhất một lần khi có hoàn lại là bao nhiêu?

*Đáp án:* \(1-(4/5)^2=9/25\).

**Bài 7.** Với n=5,k=2 không hoàn lại, inclusion probability của một vị trí cố định là bao nhiêu?

*Đáp án:* **2/5**.

**Bài 8.** Nếu k>n, cách nào còn hợp lệ?

*Đáp án:* **Có hoàn lại** nếu n>0; không hoàn lại phải từ chối.

**Bài 9.** Rút k lần có hoàn lại, xác suất mọi vị trí đều khác nhau với k≤n?

*Đáp án:* \(n(n-1)\cdots(n-k+1)/n^k\).

**Bài 10.** Kỳ vọng số vị trí khác nhau trong k lượt có hoàn lại?

*Đáp án:* \(n[1-(1-1/n)^k]\).

**Bài 11.** Vì sao partial Fisher–Yates chọn j từ [i,n) thay vì [0,n)?

*Đáp án:* Phần tử ở những vị trí trước i đã được chốt; rút từ phần chưa chốt bảo đảm không lặp và đồng đều.

**Bài 12.** Vì sao sort với comparator ngẫu nhiên không phải shuffle đúng?

*Đáp án:* Comparator có thể vi phạm tính nhất quán/bắc cầu của quan hệ thứ tự, không bảo đảm mọi hoán vị đồng xác suất.

**Bài 13.** Một luồng chưa biết n, muốn lấy k phần tử không hoàn lại trong O(k) nhớ, dùng gì?

*Đáp án:* **Reservoir sampling**.

**Bài 14.** Tại phần tử thứ t>k của reservoir, xác suất phần tử mới được giữ là bao nhiêu?

*Đáp án:* **k/t**.

**Bài 15.** Mỗi vị trí của luồng n phần tử có xác suất nằm trong reservoir cuối là bao nhiêu?

*Đáp án:* **k/n**.

**Bài 16.** Thuật toán Floyd có cần tạo mảng n phần tử không?

*Đáp án:* Không; chỉ cần HashSet cỡ O(k) để lấy k chỉ số trong [0,n).

**Bài 17.** Floyd trả danh sách đã sort có biểu thị thứ tự chọn không?

*Đáp án:* Không, chỉ là thứ tự **hiển thị của tập chỉ số**.

**Bài 18.** Với quần thể [2,4,6,8] và k=2, phương sai trung bình mẫu có hoàn lại là bao nhiêu?

*Đáp án:* **2.5** với \(\sigma^2=5\).

**Bài 19.** Cùng quần thể và k nhưng không hoàn lại, phương sai trung bình mẫu?

*Đáp án:* **5/3**, theo finite population correction.

**Bài 20.** Khi k=n không hoàn lại, trung bình mẫu có sai số do chọn mẫu không?

*Đáp án:* Không; mẫu chứa tất cả vị trí đúng một lần nên trung bình đúng bằng trung bình quần thể.

**Bài 21.** Nếu cần 100 người dùng khác nhau mà một người có nhiều bản ghi giao dịch, đơn vị lấy mẫu nên là gì?

*Đáp án:* **ID người dùng duy nhất**, không phải từng hàng giao dịch.

**Bài 22.** Nếu mỗi người có trọng số lựa chọn khác nhau, partial Fisher–Yates đồng đều có đúng không?

*Đáp án:* Không; cần thuật toán **weighted sampling** với quy luật xác suất đã định nghĩa.

**Bài 23.** Để có kết quả có thể tái lập khi học/test Java, dùng gì?

*Đáp án:* `new Random(seed)` và truyền rng qua các hàm.

**Bài 24.** Để sinh giá trị không dễ dự đoán cho tình huống bảo mật, có nên dùng Random với seed cố định không?

*Đáp án:* Không; cân nhắc **SecureRandom** cùng quy trình bảo mật phù hợp.

**Bài 25.** Hai thuật toán reservoir và Floyd cùng trả mỗi subset xác suất đều, có nhất thiết trả cùng kết quả với một seed giống nhau không?

*Đáp án:* Không. Chúng dùng các lời gọi PRNG và quy luật chuyển trạng thái khác nhau; sự tương đương là về **phân phối**, không phải kết quả từng lần.

**Bài 26.** Chỉ kiểm `sample.size()==k` và `new HashSet(sample).size()==k` có đủ chứng minh không hoàn lại đồng đều không?

*Đáp án:* Không. Điều đó chỉ kiểm tính hợp lệ/tính duy nhất; cần **chứng minh hoặc kiểm phân phối** để đánh giá tính đồng đều.

**Tổng kết:** Lấy mẫu **có hoàn lại** rút k lần độc lập từ n vị trí, mỗi dãy có xác suất \(1/n^k\); k có thể lớn hơn n và vị trí có thể lặp. Lấy mẫu **không hoàn lại** tạo k vị trí phân biệt, k≤n, mọi dãy k vị trí khác nhau có xác suất \(1/P(n,k)\) và mọi tập con k vị trí có xác suất \(1/\binom nk\). Khi nguồn có thể truy cập ngẫu nhiên, dùng **partial Fisher–Yates**; khi nguồn là stream không biết n, dùng **reservoir sampling**; khi chỉ cần k chỉ số từ miền n rất lớn, dùng **Floyd**. Phải phân biệt **vị trí nguồn với giá trị**, **thứ tự rút với tập con**, **mô hình đồng đều với weighted**, xử lý biên n=0/k=0/k>n và rút chỉ số bằng API tránh modulo bias. Chứng minh đồng đều cùng các oracle liệt kê toàn bộ trường hợp nhỏ là nền tảng để tin tưởng thuật toán ngẫu nhiên hóa, hơn là chỉ quan sát vài mẫu trông có vẻ ngẫu nhiên.
