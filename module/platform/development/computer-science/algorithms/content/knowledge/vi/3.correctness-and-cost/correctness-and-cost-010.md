# Trường hợp tốt nhất, xấu nhất, trung bình và kỳ vọng

**Độ phức tạp của thuật toán không nhất thiết chỉ có một giá trị.** Cùng một thuật toán với cùng kích thước đầu vào \(n\) có thể làm ít hoặc nhiều bước tùy dữ liệu cụ thể; với thuật toán dùng lựa chọn ngẫu nhiên, ngay cả trên **một đầu vào cố định** số bước cũng có thể khác nhau giữa các lần chạy. Vì vậy khi nói “thuật toán tốn \(O(n)\)” cần xác định **đang phân tích trường hợp nào, đầu vào phân bố ra sao, nguồn ngẫu nhiên nằm ở đâu và đo loại chi phí gì**.

Bài thuộc nhóm **Tính đúng và chi phí** của Computer Science Algorithms, chủ đề **“Trường hợp tốt nhất, xấu nhất, trung bình và kỳ vọng”**. Ta phân biệt **best case**, **worst case**, **average case**, **expected running time**, phân phối đầu vào và đồng xu ngẫu nhiên của thuật toán, tình huống xấu nhất theo kỳ vọng, phân tích chi phí bằng phép so sánh, chi phí bộ nhớ, cách dùng \(\Theta/O/\Omega\), các ví dụ **tìm kiếm tuyến tính**, **insertion sort**, **randomized quicksort**, và sự khác nhau với **amortized analysis**. Bài có chương trình **Java 17+**, đầu ra xác định, oracle độc lập và bài tập có lời giải.

## 1. Trước hết: xác định phép đo

Gọi \(x\) là một đầu vào có kích thước \(n\), và \(C(x)\) là **chi phí** chạy thuật toán trên x.

Có nhiều cách định nghĩa chi phí:

- **Số lần so sánh khóa:** hữu ích khi phân tích tìm kiếm và sắp xếp theo so sánh.
- **Số lần dịch chuyển phần tử:** quan trọng đối với insertion sort.
- **Số lần truy cập mảng, phép toán số học hoặc lời gọi hàm:** tùy mô hình chi phí.
- **Thời gian thực tế (wall-clock):** chịu tác động bởi CPU, cache, JVM/JIT, GC, hệ điều hành và I/O.
- **Số ô nhớ phụ hoặc độ sâu ngăn xếp:** phục vụ phân tích bộ nhớ.

Một bảng so sánh chỉ có ý nghĩa khi **các số đo cùng định nghĩa**. Ví dụ insertion sort có thể thực hiện một số so sánh khác số lần dịch chuyển: không được gọi chung cả hai là “số bước” rồi kết luận một công thức chính xác.

Trong các chứng minh dưới đây, thường giả định phép so sánh và thao tác mảng có chi phí hằng số, đầu vào nằm trong RAM, và phép tính số nguyên không vượt miền kiểu dữ liệu đã chọn. Khi sang cơ sở dữ liệu, xử lý file lớn hoặc số nguyên nhiều chữ số, mô hình cần bổ sung chi phí I/O và tính toán trên số lớn.

## 2. Trường hợp tốt nhất và xấu nhất

Cho \(I_n\) là tập tất cả **đầu vào hợp lệ có kích thước n**. Với một thuật toán **xác định**, có chi phí \(C(x)\):

\[
B(n)=\min_{x\in I_n} C(x),\qquad
W(n)=\max_{x\in I_n} C(x).
\]

Khi dùng tập vô hạn hoặc hàm chi phí không đạt cực trị, có thể viết infimum/supremum thích hợp; trong những bài toán mảng hữu hạn thông thường, dạng min/max dễ hiểu hơn.

- **Best case \(B(n)\):** đầu vào thuận lợi nhất trong tất cả input cùng kích thước.
- **Worst case \(W(n)\):** đầu vào bất lợi nhất trong tất cả input cùng kích thước.
- **Không phải “kích thước nhỏ nhất/lớn nhất”:** ta so **những input cùng n**, không lấy n=1 đối chiếu với n=1.000.000.

**Ví dụ:** tìm kiếm tuyến tính trên mảng n phần tử, cần tìm chỉ số xuất hiện **đầu tiên** của khóa. Nếu n≥1, trường hợp tốt nhất là khóa nằm ngay đầu mảng, chỉ cần một phép so sánh: \(B(n)=1\). Trường hợp xấu nhất là khóa không xuất hiện hoặc chỉ ở vị trí cuối: \(W(n)=n\).

**Quan trọng:** best case hiếm khi là một bảo đảm hữu dụng đối với mọi người dùng. Một thuật toán “tốt nhất \(O(1)\)” vẫn có thể “xấu nhất \(O(n^2)\)”. Khi yêu cầu hệ thống có giới hạn phản hồi nghiêm ngặt, worst case thường quan trọng hơn, dù best case rất đẹp.

## 3. Phân tích trường hợp trung bình phải nêu phân phối

“Trung bình” chỉ có nghĩa toán học khi biết **trung bình trên những input nào và với xác suất bao nhiêu**.

Cho \(X\) là một biến ngẫu nhiên nhận giá trị trong \(I_n\) theo một phân phối \(D_n\). Với thuật toán xác định:

\[
A_{D}(n)
=\mathbb{E}_{X\sim D_n}[C(X)]
=\sum_{x\in I_n}\Pr[X=x]C(x).
\]

**Average case** thường là kỳ vọng theo **phân phối input đã định nghĩa**. Nếu phân phối không được nêu, không có một đáp án average-case duy nhất. “Chọn ngẫu nhiên đồng đều từ tất cả đầu vào” cũng là một giả định phải viết rõ; hơn nữa nhiều bài toán có không gian đầu vào rất lớn hoặc không có phân phối đồng đều tự nhiên.

### Ví dụ khi phân phối khác nhau

Cùng một mảng có n=8 phần tử:

- Nếu mọi truy vấn đều tìm khóa ở chỉ số 0: số so sánh trung bình bằng 1.
- Nếu truy vấn luôn tìm khóa không tồn tại: trung bình bằng 8.
- Nếu khóa chắc chắn có mặt **đúng một lần** và vị trí xuất hiện phân bố đều trên 8 vị trí: trung bình bằng 4,5.
- Nếu xác suất khóa có mặt là 1/2, và **khi có mặt** vị trí phân bố đều: trung bình là 6,25.

Không thể nói “linear search trung bình đúng n/2 so sánh” nếu chưa quy định xác suất tìm thấy, khả năng có khóa lặp lại, và vị trí khóa.

### Phân phối không đồng đều

Nếu khóa có xác suất xuất hiện cao ở vị trí đầu, trung bình có thể gần hằng số. Nếu truy vấn chủ yếu thất bại, trung bình gần n. Nếu người dùng tìm những sản phẩm phổ biến trước, phân phối truy vấn thực tế có thể khác giả định uniform rất xa.

Phân tích trung bình tốt nên nói rõ **mô hình sinh dữ liệu**; kết quả benchmark trên một tập test không tự xác định phân phối của môi trường triển khai.

## 4. Kỳ vọng (expectation) là một phép toán xác suất, không phải một “ca thứ tư” hoàn toàn tách biệt

Nhiều tài liệu dùng “expected time” khi thuật toán có lựa chọn ngẫu nhiên. Nhưng về toán học, **average case cũng được tính bằng kỳ vọng**. Điều phân biệt là **đang lấy kỳ vọng trên biến ngẫu nhiên nào**.

### Hai nguồn ngẫu nhiên

1. **Ngẫu nhiên từ đầu vào \(X\):** input được lấy theo phân phối \(D_n\); thuật toán có thể hoàn toàn xác định.
2. **Ngẫu nhiên nội bộ của thuật toán \(R\):** chọn pivot, xáo chỉ số, lấy mẫu…; ta có thể giữ input x hoàn toàn cố định.

Với thuật toán ngẫu nhiên \(C(x,R)\), ta có thể hỏi:

\[
\mathbb{E}_R[C(x,R)]
\]

cho **một input x cố định**, hoặc:

\[
\mathbb{E}_{X,R}[C(X,R)]
\]

khi cả input và lựa chọn ngẫu nhiên thay đổi. Nếu cơ chế sinh X và R độc lập, có thể viết kỳ vọng lồng nhau \(\mathbb{E}_X[\mathbb{E}_R[C(X,R)]]\).

**Đừng gọi kỳ vọng theo phân phối input là tự động giống kỳ vọng theo random seed**, dù kết quả Big-O tình cờ trùng nhau.

## 5. Tìm kiếm tuyến tính: công thức chính xác

Cho một mảng n phần tử, n≥1, tìm **vị trí đầu tiên** có giá trị bằng target:

~~~text
LINEAR_SEARCH(A, target):
    for i from 0 to n-1:
        compare A[i] with target
        if equal:
            return i
    return NOT_FOUND
~~~

Quy ước **chi phí = số lần so sánh A[i]==target**.

### Best và worst

- **Best case:** target ở index 0 → 1 so sánh.
- **Worst case:** target vắng mặt hoặc chỉ xuất hiện lần đầu ở index n−1 → n so sánh.
- **Mảng rỗng:** n=0 → không so sánh, trả NOT_FOUND. Công thức \(B(n)=1\) chỉ dùng khi n≥1 và có input chứa target.

### Trung bình khi luôn có đúng một target

Nếu vị trí target phân bố đều trên n vị trí \(0,1,\ldots,n-1\), số so sánh là \(1,2,\ldots,n\) với xác suất \(1/n\):

\[
\mathbb{E}[C\mid \text{found}]
=\frac{1+2+\cdots+n}{n}
=\frac{n+1}{2}.
\]

Đây là công thức **chính xác** trong mô hình này, không phải chỉ là xấp xỉ.

Với n=8, trung bình là 4,5 phép so sánh.

### Khi truy vấn có thể thất bại

Đặt \(p=\Pr[\text{target found}]\). Giả sử khi tìm thấy, target xuất hiện đúng một lần và vị trí của nó phân bố đều. Khi không tìm thấy, phải so sánh n phần tử:

\[
\mathbb{E}[C]
=p\frac{n+1}{2}+(1-p)n.
\]

Với n=8,p=0,5:

\[
0,5\cdot4,5+0,5\cdot8=6,25.
\]

Nếu p=1, kỳ vọng 4,5; nếu p=0, kỳ vọng 8. Vì vậy **không có một average duy nhất** khi p chưa biết.

Nếu target có thể lặp lại, sự phân bố của **lần xuất hiện đầu tiên** mới quyết định chi phí. Phân bố đều giữa các vị trí của một target duy nhất không áp dụng nguyên xi cho trường hợp nhiều bản sao.

## 6. Tìm kiếm theo thứ tự ngẫu nhiên trên input cố định

Một phiên bản **randomized search** tạo hoán vị ngẫu nhiên đồng đều của các chỉ số 0..n−1, rồi lần lượt kiểm tra theo hoán vị này.

Nếu target xuất hiện **đúng một lần** tại một vị trí bất kỳ, không cần giả định vị trí ấy ngẫu nhiên trong input: trong một hoán vị đồng đều, vị trí kiểm tra của target cũng đồng đều từ 1..n. Do đó:

\[
\mathbb{E}_{R}[C(x,R)]=\frac{n+1}{2}.
\]

Đây là **kỳ vọng theo ngẫu nhiên của thuật toán trên một x cố định**. Khác với công thức linear search trước, ta **không** cần giả định input có vị trí target phân bố đều.

Nếu target vắng mặt, mọi thứ tự đều phải so đủ n phần tử. Nếu có k≥1 vị trí thỏa, kỳ vọng của **vị trí thành công đầu tiên** trong hoán vị ngẫu nhiên đồng đều là:

\[
\mathbb{E}[C]=\frac{n+1}{k+1}.
\]

Công thức này dùng mô hình chọn hoán vị đồng đều và kiểm tra từng vị trí không lặp lại; có thể chứng minh qua tính đối xứng của các vị trí thành công hoặc tổ hợp.

**Không đồng nhất chi phí tạo hoán vị với chi phí so sánh target.** Nếu phải cấp phát và xáo một mảng chỉ số dài n, tổng thời gian vẫn có phần O(n) ban đầu. Phân tích ở đây đo **số phép so sánh target**, không tuyên bố việc xáo chỉ số là miễn phí.

### Ví dụ n=4 bằng vét cạn

Giữ target tại **index 0** của input. Có \(4!=24\) hoán vị thứ tự kiểm tra. Mỗi vị trí thứ 1,2,3,4 của target xuất hiện trong đúng 6 hoán vị:

\[
\mathbb{E}_R[C]
=\frac{6(1+2+3+4)}{24}
=2,5.
\]

Ta sẽ kiểm công thức này bằng cách **liệt kê tất cả 24 hoán vị** trong chương trình Java, thay vì dựa vào vài phép thử ngẫu nhiên.

## 7. Insertion sort: ba kịch bản rất khác nhau

Giả mã insertion sort cho các số nguyên:

~~~text
INSERTION_SORT(A):
    for i = 1..n-1:
        key = A[i]
        j = i-1
        while j >= 0 AND A[j] > key:
            A[j+1] = A[j]
            j--
        A[j+1] = key
~~~

Để có công thức so sánh chính xác, ta quy định:

- **comparisons:** chỉ đếm mỗi lần thực sự đánh giá điều kiện khóa `A[j]>key`, **không** đếm phép kiểm `j>=0`.
- **shifts:** đếm mỗi lần dịch một phần tử `A[j]` sang `A[j+1]` khi nó lớn hơn key.
- Phép ghi key xuống vị trí cuối **không** được tính là shift.
- Dùng so sánh `>` để giữ thứ tự tương đối của các khóa bằng nhau khi cài một insertion sort ổn định.

### Best case — dãy đã tăng không giảm

Trong mỗi bước i, `A[i−1]≤key` nên thử điều kiện một lần và kết thúc. Không dịch phần tử nào.

Với n≥1:

\[
C_{\text{best}}(n)=n-1,\qquad
S_{\text{best}}(n)=0.
\]

Chi phí so sánh \(\Theta(n)\) khi n tăng, với n=0 hoặc 1 có 0 phép so sánh. Dù thuật toán có vòng lặp lồng nhau, best case **không phải \(\Theta(n^2)\)**.

### Worst case — dãy giảm nghiêm ngặt

Mỗi phần tử mới nhỏ hơn mọi phần tử đứng trước nên phải dịch i phần tử ở bước i; cả i phép so sánh đều thành công, không có phép so sánh thất bại khi j hết mảng:

\[
C_{\text{worst}}(n)=S_{\text{worst}}(n)
=\sum_{i=1}^{n-1}i
=\frac{n(n-1)}{2}.
\]

Vì thế cả so sánh và dịch chuyển là \(\Theta(n^2)\) trong worst case.

### Trường hợp trung bình trên hoán vị đồng đều

Giả sử n giá trị **phân biệt**, mỗi hoán vị của chúng có xác suất bằng nhau. Mỗi cặp vị trí tạo **nghịch thế (inversion)** với xác suất 1/2; có \(\binom n2\) cặp:

\[
\mathbb{E}[\text{shifts}]
=\mathbb{E}[\text{inversions}]
=\frac{n(n-1)}4.
\]

**Tính tuyến tính của kỳ vọng không đòi các sự kiện nghịch thế độc lập.** Chỉ cần viết tổng các biến chỉ báo cho mỗi cặp và lấy kỳ vọng của tổng.

Với phép đếm comparisons đã quy định, mỗi bước i có:

- Một phép so sánh thành công cho mỗi phần tử lớn hơn key đứng trước (mỗi shift).
- Thêm **một phép so sánh thất bại** nếu key không phải phần tử nhỏ nhất nghiêm ngặt của i+1 phần tử đầu tiên.

Trong một hoán vị ngẫu nhiên của các giá trị phân biệt, xác suất key **là nhỏ nhất** trong i+1 phần tử đầu bằng \(1/(i+1)\). Do đó:

\[
\mathbb{E}[\text{comparisons}]
=\frac{n(n-1)}4
+\sum_{i=1}^{n-1}\left(1-\frac1{i+1}\right)
=\frac{n(n-1)}4+n-H_n,
\]

với \(H_n=1+1/2+\cdots+1/n\).

Từ đó **average-case comparisons và shifts đều \(\Theta(n^2)\)** dưới phân phối hoán vị đồng đều, dù best case chỉ \(\Theta(n)\).

### Kiểm n=4

\(4!=24\) hoán vị. Vét cạn cho:

- Tổng số comparisons trên 24 hoán vị: **118**, trung bình \(118/24=4,916666\ldots\).
- Tổng số shifts: **72**, trung bình \(72/24=3\).
- Công thức lý thuyết cho comparisons: \(4\cdot3/4+4-H_4=3+4-25/12=59/12=4,916666\ldots\).

Đây là **trung bình theo phân phối input**, vì insertion sort trong ví dụ là thuật toán xác định, không bốc thăm khi chạy.

## 8. Quicksort: ngẫu nhiên hóa pivot thay đổi bảo đảm theo kỳ vọng

Quicksort chọn một pivot, partition các phần tử quanh pivot rồi đệ quy trên hai phía. Với các khóa **phân biệt** và partition bằng so sánh:

- **Best case:** pivot chia dãy thành hai phần gần bằng nhau ở mỗi mức, \(T(n)=2T(n/2)+\Theta(n)\) → \(\Theta(n\log n)\).
- **Worst case:** pivot luôn là nhỏ nhất hoặc lớn nhất, \(T(n)=T(n-1)+\Theta(n)\) → \(\Theta(n^2)\).
- **Randomized quicksort:** mỗi lần chọn pivot **đồng đều** trong đoạn hiện tại. Trên **một input phân biệt cố định bất kỳ**, số so sánh kỳ vọng là \(\Theta(n\log n)\).

Sự ngẫu nhiên nằm ở **lựa chọn pivot**, không cần giả định đầu vào được xáo trước.

### Công thức kỳ vọng số so sánh

Đánh số các phần tử theo thứ hạng khóa \(1,\dots,n\). Hai phần tử có thứ hạng i<j chỉ được so sánh trực tiếp nếu **pivot đầu tiên trong các phần tử hạng i..j là một trong hai đầu i hoặc j**. Với pivot đồng đều:

\[
\Pr[\text{i được so với j}]=\frac{2}{j-i+1}.
\]

Lấy tổng các biến chỉ báo so sánh trên mọi cặp và dùng tính tuyến tính của kỳ vọng:

\[
\mathbb{E}[C_n]
=\sum_{1\le i<j\le n}\frac2{j-i+1}
=2(n+1)H_n-4n.
\]

Do \(H_n=\Theta(\log n)\), số so sánh kỳ vọng là \(\Theta(n\log n)\).

Với n=8:

\[
2(9)H_8-32\approx16,9214.
\]

Tất nhiên **một lần chạy** không thể thực hiện 16,9214 phép so sánh; kỳ vọng là **trung bình lý thuyết** trên rất nhiều kết quả pivot. Một lần chạy sẽ dùng một số nguyên phép so sánh cụ thể.

### Worst case vẫn tồn tại

Ngay cả khi pivot được bốc thăm đồng đều, vẫn có chuỗi lựa chọn cực kỳ xấu: mỗi lần pivot ở một đầu thứ hạng. Quicksort khi ấy làm \(\Theta(n^2)\) comparisons và ngăn xếp đệ quy có thể sâu \(\Theta(n)\). Randomization khiến chuỗi đó ít khả năng xuất hiện, **không xóa nó khỏi không gian các lần chạy**.

### Dữ liệu có nhiều khóa bằng nhau

Công thức chính xác trên giả định **mọi key phân biệt**. Với partition hai phía dạng Lomuto và điều kiện `<=pivot`, nhiều key bằng nhau có thể tạo partition rất lệch; nếu toàn bộ key giống nhau, ngay cả random pivot cũng cho \(\Theta(n^2)\) so sánh.

Giải pháp thực tế thường dùng **three-way partition** (nhóm nhỏ hơn, bằng, lớn hơn pivot), giúp xử lý duplicates tốt hơn. Không áp dụng mù quáng công thức \(2(n+1)H_n-4n\) cho phiên bản code hai phía trên tập dữ liệu nhiều giá trị trùng.

## 9. Worst-case expected khác worst-case của từng lần chạy

Với thuật toán ngẫu nhiên, có nhiều cách đặt min/max và kỳ vọng. Phải nói chính xác đang dùng cách nào.

Đặt \(C(x,R)\) là chi phí trên input x, ngẫu nhiên nội bộ R.

**Worst-case expected time:**

\[
W_{\mathrm{exp}}(n)
=\max_{x\in I_n}\mathbb{E}_R[C(x,R)].
\]

Ta chọn input x bất lợi nhất nhưng **không** cho phép x thay đổi theo kết quả rút thăm R. Đây thường là đại lượng được nêu khi nói “randomized quicksort expected \(O(n\log n)\) on every distinct-key input”.

**Worst over both input and random coins:**

\[
W_{\mathrm{all}}(n)
=\max_{x\in I_n,r}C(x,r).
\]

Với randomized quicksort hai phía, đại lượng này vẫn có thể là \(\Theta(n^2)\).

**Worst-case per input draw:** nếu người tạo input thấy random seed/pivot trước khi chọn dữ liệu, mô hình adversary có thể khác mô hình chọn input trước, và bảo đảm phải xem lại.

**Không được đổi vị trí toán tử** max và expectation tùy ý. Nói “worst-case expected” không đồng nghĩa “mọi lần chạy nhanh nhất trong một khoảng cố định”.

## 10. Best, worst, average, expected — đặt cạnh nhau

| Thuật toán / điều kiện | Tốt nhất | Xấu nhất | Trung bình / kỳ vọng có điều kiện |
| --- | --- | --- | --- |
| Linear search, n≥1 | 1 comparison | n comparisons | Khi target duy nhất, vị trí đều: (n+1)/2 |
| Linear search, xác suất thành công p | 1 nếu có target đầu dãy | n | \(p(n+1)/2+(1-p)n\) với vị trí đều khi thành công |
| Random-order search, target duy nhất | 1 comparison | n comparisons | Kỳ vọng theo random order: (n+1)/2 |
| Insertion sort, khóa phân biệt | n−1 comparisons | n(n−1)/2 | Hoán vị đều: \(\Theta(n^2)\) |
| Quicksort, pivot cực thuận/bất lợi | \(\Theta(n\log n)\) | \(\Theta(n^2)\) | Random pivot + khóa phân biệt: kỳ vọng \(\Theta(n\log n)\) |
| Binary search trên dãy đã sắp | O(1) nếu lần thử đầu trúng | O(log n) | Phụ thuộc phân bố target; thường O(log n) |
| Tra cứu hash table | Có thể O(1) | Có thể O(n) nếu collision xấu | Expected O(1) **dưới giả định hashing/load factor thích hợp** |

Bảng không thể dùng để so sánh bằng một con số nếu mỗi hàng đo một chi phí khác nhau. Ký hiệu Big-O mô tả tốc độ tăng asymptotic; số lần so sánh chính xác tùy mã và cách đếm.

### Binary search: “best O(1)” không có nghĩa luôn O(1)

Binary search có thể trúng `a[mid]` ngay lần đầu, nhưng trên các target khác nó cần khoảng \(\log_2 n\) bước. Trường hợp tốt nhất không xóa worst-case O(log n).

### Hash table: kỳ vọng không phải phép màu

Expected O(1) cho tra cứu hash table phụ thuộc giả định về hàm băm, số phần tử, hệ số tải và cách xử lý collision. Nếu mọi khóa băm vào cùng bucket của separate chaining, một truy vấn có thể tốn O(n). Ngay cả một cài đặt phổ biến cũng không có bảo đảm expected O(1) tuyệt đối đối với mọi input/adversary nếu giả định hashing bị vi phạm.

## 11. Ký hiệu O, Ω, Θ và “trường hợp” là hai trục khác nhau

**Big-O:** cận trên asymptotic.

\[
f(n)=O(g(n))
\]

nghĩa là tồn tại c,n₀ sao cho \(0\le f(n)\le c g(n)\) khi n≥n₀ (với các hàm chi phí không âm).

**Big-Ω:** cận dưới asymptotic.

**Big-Θ:** cả cận trên và cận dưới cùng cấp.

Ta có thể nói:

- Best-case time của insertion sort là \(\Theta(n)\).
- Worst-case time của insertion sort là \(\Theta(n^2)\).
- Average-case time của insertion sort dưới uniform permutations là \(\Theta(n^2)\).
- Expected time của randomized quicksort trên mọi input phân biệt cố định là \(\Theta(n\log n)\).

**Không** nói “best case là Ω, worst case là O” như thể đó là cùng một khái niệm. Cả ba ký hiệu O/Ω/Θ đều có thể được áp dụng **cho bất kỳ hàm best/worst/average/expected nào**, khi ta có chứng minh thích hợp.

Ví dụ worst-case insertion sort là \(O(n^2)\) và cũng là \(\Omega(n^2)\), nên là \(\Theta(n^2)\).

## 12. Vì sao kỳ vọng không bảo đảm mỗi lần chạy nhanh?

Kỳ vọng là một con số trung bình, không giới hạn tối đa của từng quan sát.

Ví dụ một thuật toán có:

- Xác suất 99% dùng 1 bước.
- Xác suất 1% dùng 10.000 bước.

Kỳ vọng:

\[
0,99\cdot1+0,01\cdot10000=100,99.
\]

Kỳ vọng khoảng 101 bước, nhưng vẫn có lần chạy tới 10.000 bước.

Với biến ngẫu nhiên chi phí không âm T, **bất đẳng thức Markov** cho:

\[
\Pr[T\ge a]\le\frac{\mathbb{E}[T]}{a}\quad (a>0).
\]

Cận này đôi khi rất lỏng. Muốn nói “chạy trong O(n log n) với xác suất ít nhất 1−1/n²” phải có phân tích **high-probability** thích hợp, không suy diễn chỉ từ \(E[T]=O(n\log n)\).

**Trong hệ thống realtime hoặc an toàn cao**, một vài lần chạy rất chậm có thể không chấp nhận được. Khi ấy cần nhìn worst-case latency, phân phối đuôi, giới hạn deadline hoặc chọn thuật toán có bảo đảm chặt hơn.

## 13. Phân tích trung bình không phải đo benchmark tùy ý

Giả sử benchmark cho insertion sort trên 100 mảng và thấy trung bình 10.000 phép so sánh. Điều này là **trung bình thực nghiệm trên tập mẫu**. Nó không tự chứng minh average-case của mọi đầu vào kích thước n.

Để kết nối lý thuyết và thực nghiệm:

1. **Nêu cách tạo input:** đã sort, giảm, hoán vị đều, nhiều duplicates, phân phối Gaussian, dữ liệu nghiệp vụ hay đầu vào đối kháng?
2. **Định nghĩa phép đo:** so sánh khóa, dịch chuyển, cấp phát, thời gian CPU, thời gian tường?
3. **Giữ n cố định** khi so các kịch bản; thay n để quan sát tăng trưởng.
4. **Ghi seed** cho bộ sinh ngẫu nhiên để tái lập lỗi.
5. **Lặp lại nhiều lần**, tách các hiệu ứng JIT warmup, GC, tải CPU, cache.
6. **Không dùng một đồ thị thực nghiệm** để tuyên bố một cận worst-case toán học.
7. **Nêu phạm vi suy rộng** từ phân phối test sang phân phối production.

Với Java, benchmark nghiêm túc có thể dùng JMH để tránh các lỗi đo nóng/lạnh, dead-code elimination và thiếu warmup. Chương trình trong bài nhằm **minh họa cách đếm chi phí và kiểm tính đúng**, không phải benchmark JVM chuẩn.

## 14. So sánh average-case với amortized analysis

Đây là hai khái niệm rất dễ nhầm.

**Average-case:** trung bình chi phí của một thao tác/thuật toán **qua phân phối input hoặc nguồn ngẫu nhiên**.

**Amortized:** tính **tổng chi phí của một dãy thao tác bất kỳ** rồi chia cho số thao tác; không bắt buộc dùng xác suất.

### Ví dụ mở rộng mảng động

Một dynamic array có thể tăng gấp đôi sức chứa khi đầy. Một lần `append` gây cấp phát và copy n phần tử nên **worst-case append** là O(n). Nhưng trong một chuỗi m lần append, tổng số phần tử phải sao chép qua các lần mở rộng hình học là O(m). Do đó:

\[
\text{amortized cost per append}=O(1).
\]

Đây là bảo đảm trên **chuỗi thao tác**, kể cả khi các input không ngẫu nhiên. Không có giả định “mỗi lần append được chọn đồng đều”.

**Randomized expected O(1)**, **average-case O(1)** và **amortized O(1)** là ba phát biểu có thể cùng xuất hiện trong một cấu trúc dữ liệu, nhưng dựa trên những chứng minh khác nhau.

## 15. Chi phí thời gian và bộ nhớ là hai hàm riêng

Cần phân tích **time complexity** và **space complexity** độc lập. Một thuật toán có thời gian xấu nhất O(n²) không nhất thiết dùng O(n²) RAM.

Ví dụ:

- Linear search: thời gian 1..n comparisons, bộ nhớ phụ O(1).
- Insertion sort tại chỗ: thời gian 1..n² theo input, bộ nhớ phụ O(1).
- Randomized quicksort đệ quy in-place: kỳ vọng số comparisons O(n log n) trên distinct keys; ngăn xếp **kỳ vọng** O(log n) trong mô hình pivot ngẫu nhiên, **xấu nhất** O(n).
- **Bản demo** randomized quicksort sao chép toàn bộ mảng để không sửa caller, nên **tổng bộ nhớ bổ sung** O(n) cho copy dù stack mong đợi nhỏ.
- Random-order search demo cấp phát chỉ số hoán vị dài n → O(n) bộ nhớ phụ. Nếu cần O(1) bộ nhớ, phải dùng thiết kế khác hoặc chấp nhận thay đổi input.

Không suy ra space complexity chỉ từ recurrence thời gian. Và không coi bản copy hoặc overhead của API là “miễn phí” nếu chương trình thực sự cấp phát nó.

## 16. Một vài bẫy khi tính kỳ vọng

### Tính tuyến tính của kỳ vọng

Với các biến ngẫu nhiên \(X_i\):

\[
\mathbb E\left[\sum_i X_i\right]
=\sum_i\mathbb E[X_i].
\]

**Không cần các \(X_i\) độc lập.** Đây là lý do ta có thể đếm nghịch thế của hoán vị và so sánh từng cặp của randomized quicksort bằng biến chỉ báo.

### Kỳ vọng của tích không tự bằng tích kỳ vọng

Nói chung:

\[
\mathbb E[XY]\ne\mathbb E[X]\mathbb E[Y]
\]

nếu X,Y phụ thuộc nhau. Không được tự nhân các xác suất của những sự kiện ngẫu nhiên không độc lập.

### Không đổi max và expectation

Thông thường:

\[
\max_x\mathbb E_R[C(x,R)]
\ne \mathbb E_R[\max_x C(x,R)].
\]

Một phía có thể được dùng để phân tích adversary chọn input **trước khi thấy** random coins; phía còn lại cho phép chọn input **sau khi biết** kết quả ngẫu nhiên. Hai mô hình khác nhau.

### Đừng biến kỳ vọng thành cam kết “luôn”

Khi tài liệu nói expected O(n log n), nên ghi rõ: **đối với input nào, trên nguồn ngẫu nhiên nào, loại chi phí gì và có giả định gì về phân phối/hàm băm/độ phân biệt của khóa**.

## 17. Java 17+ — chương trình đo chi phí và kiểm oracle

Lưu file dưới tên **`ComplexityCasesDemo.java`**. Chương trình có các thành phần:

- `SearchResult(index,comparisons)` cho linear search và random-order search.
- `InsertionStats(sorted,comparisons,shifts)`: sort **bản sao**, đếm đúng phép so sánh khóa và dịch chuyển.
- `QuickStats(sorted,comparisons)`: randomized quicksort chọn pivot ngẫu nhiên cho từng đoạn, sort bản sao, đếm comparisons của partition.
- Vét cạn **24 hoán vị** n=4 để kiểm trung bình insertion sort và kỳ vọng random-order search.
- Kiểm công thức kỳ vọng quicksort trên **8 khóa phân biệt** từ tổng điều hòa \(H_8\).
- **600 bộ random search**, **600 bộ insertion sort** và **500 bộ quicksort**, đối chiếu với các oracle độc lập.
- Không sửa các mảng input; có kiểm null input và dữ liệu rỗng.

### Mã Java đầy đủ

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.Random;

public class ComplexityCasesDemo {
    record SearchResult(int index, int comparisons) {}
    record InsertionStats(int[] sorted,
            long comparisons, long shifts) {}
    record QuickStats(int[] sorted, long comparisons) {}

    // Count ONLY equality comparisons to the target.
    static SearchResult linearSearch(int[] values, int key) {
        Objects.requireNonNull(values, "values");
        int comparisons = 0;
        for (int i = 0; i < values.length; i++) {
            comparisons++;
            if (values[i] == key)
                return new SearchResult(i, comparisons);
        }
        return new SearchResult(-1, comparisons);
    }

    // Fresh uniformly shuffled index order. A matching index
    // need not be the FIRST matching index if duplicates exist.
    static SearchResult randomizedSearch(
            int[] values, int key, Random random) {
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(random, "random");
        int n = values.length;
        int[] order = new int[n];
        for (int i = 0; i < n; i++) order[i] = i;

        // Fisher-Yates shuffle.
        for (int i = n - 1; i > 0; i--) {
            int j = random.nextInt(i + 1);
            int temp = order[i];
            order[i] = order[j];
            order[j] = temp;
        }
        int comparisons = 0;
        for (int position : order) {
            comparisons++;
            if (values[position] == key)
                return new SearchResult(position, comparisons);
        }
        return new SearchResult(-1, comparisons);
    }

    // Count evaluations of data[j] > key, NOT j >= 0.
    static InsertionStats insertionSortCopy(int[] input) {
        Objects.requireNonNull(input, "input");
        int[] a = input.clone();
        long comparisons = 0, shifts = 0;

        for (int i = 1; i < a.length; i++) {
            int key = a[i], j = i - 1;
            while (j >= 0) {
                comparisons++;
                if (a[j] > key) {
                    a[j + 1] = a[j];
                    shifts++;
                    j--;
                } else {
                    break;
                }
            }
            a[j + 1] = key;
        }
        return new InsertionStats(a, comparisons, shifts);
    }

    static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    // Lomuto partition with randomized pivot. The exact
    // harmonic expectation formula assumes DISTINCT keys.
    static QuickStats randomizedQuickSortCopy(
            int[] input, Random random) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(random, "random");
        int[] a = input.clone();
        long[] comparisons = {0L};
        quickSort(a, 0, a.length - 1, random, comparisons);
        return new QuickStats(a, comparisons[0]);
    }

    static void quickSort(int[] a, int lo, int hi,
            Random random, long[] comparisons) {
        if (lo >= hi) return;

        int chosen = lo + random.nextInt(hi - lo + 1);
        swap(a, chosen, hi);
        int pivot = a[hi], store = lo;

        for (int j = lo; j < hi; j++) {
            comparisons[0]++;
            if (a[j] <= pivot) {
                swap(a, store, j);
                store++;
            }
        }
        swap(a, store, hi);
        quickSort(a, lo, store - 1, random, comparisons);
        quickSort(a, store + 1, hi, random, comparisons);
    }

    // Exhaustively enumerate all 4! permutations.
    // totals: [number of permutations, insertion comparisons,
    // insertion shifts, random-search rank for fixed target 0].
    static void enumerateFour(int[] permutation,
            int offset, long[] totals) {
        if (offset == permutation.length) {
            InsertionStats stats =
                    insertionSortCopy(permutation);
            totals[0]++;
            totals[1] += stats.comparisons();
            totals[2] += stats.shifts();
            for (int i = 0; i < permutation.length; i++) {
                if (permutation[i] == 0) {
                    totals[3] += i + 1;
                    break;
                }
            }
            return;
        }

        for (int i = offset; i < permutation.length; i++) {
            swap(permutation, offset, i);
            enumerateFour(permutation, offset + 1, totals);
            swap(permutation, offset, i);
        }
    }

    static double expectedQuickSortComparisons(int n) {
        if (n < 0)
            throw new IllegalArgumentException("Negative n");
        double harmonic = 0.0;
        for (int i = 1; i <= n; i++)
            harmonic += 1.0 / i;
        return n <= 1 ? 0.0
                : 2.0 * (n + 1) * harmonic - 4.0 * n;
    }

    static void require(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static int oracleFirstIndex(int[] a, int key) {
        for (int i = 0; i < a.length; i++)
            if (a[i] == key) return i;
        return -1;
    }

    static void randomSearchTests() {
        Random random = new Random(520262L);
        for (int trial = 0; trial < 600; trial++) {
            int n = random.nextInt(81);
            int[] a = new int[n];
            for (int i = 0; i < n; i++) {
                int choice = random.nextInt(20);
                a[i] = choice == 0 ? Integer.MAX_VALUE
                        : choice == 1 ? Integer.MIN_VALUE
                        : random.nextInt(91) - 45;
            }
            int key = random.nextInt(91) - 45;
            int expected = oracleFirstIndex(a, key);
            SearchResult sequential = linearSearch(a, key);
            require(sequential.index() == expected,
                    "linear search result");
            require(sequential.comparisons() ==
                    (expected < 0 ? n : expected + 1),
                    "linear search comparison count");

            SearchResult shuffled =
                    randomizedSearch(a, key, random);
            if (expected < 0) {
                require(shuffled.index() == -1
                        && shuffled.comparisons() == n,
                        "random search absent");
            } else {
                require(shuffled.index() >= 0
                        && shuffled.index() < n
                        && a[shuffled.index()] == key,
                        "random search found");
                require(shuffled.comparisons() >= 1
                        && shuffled.comparisons() <= n,
                        "random search comparison bound");
            }
        }
        System.out.println("searchRandom=PASS (600 cases)");
    }

    // Independent O(n^2) inversion and stop-test oracles.
    static void randomInsertionTests() {
        Random random = new Random(520263L);
        for (int trial = 0; trial < 600; trial++) {
            int n = random.nextInt(76);
            int[] a = new int[n];
            for (int i = 0; i < n; i++) {
                int choice = random.nextInt(20);
                a[i] = choice == 0 ? Integer.MAX_VALUE
                        : choice == 1 ? Integer.MIN_VALUE
                        : random.nextInt(101) - 50;
            }
            int[] original = a.clone();
            int[] expected = a.clone();
            Arrays.sort(expected);
            InsertionStats got = insertionSortCopy(a);
            require(Arrays.equals(got.sorted(), expected),
                    "insertion sort output");
            require(Arrays.equals(a, original),
                    "insertion sort mutated input");

            long inversions = 0, failedComparisons = 0;
            for (int i = 1; i < n; i++) {
                boolean hasPreviousLessOrEqual = false;
                for (int j = 0; j < i; j++) {
                    if (a[j] > a[i]) inversions++;
                    else hasPreviousLessOrEqual = true;
                }
                if (hasPreviousLessOrEqual)
                    failedComparisons++;
            }
            require(got.shifts() == inversions,
                    "inversion count");
            require(got.comparisons() ==
                    inversions + failedComparisons,
                    "insertion comparison count");
        }
        System.out.println("insertionRandom=PASS (600 cases)");
    }

    static void randomQuickSortTests() {
        Random random = new Random(520264L);
        for (int trial = 0; trial < 500; trial++) {
            int n = random.nextInt(61);
            int[] a = new int[n];
            for (int i = 0; i < n; i++) {
                int choice = random.nextInt(20);
                a[i] = choice == 0 ? Integer.MIN_VALUE
                        : choice == 1 ? Integer.MAX_VALUE
                        : random.nextInt(101) - 50;
            }
            int[] original = a.clone();
            int[] expected = a.clone();
            Arrays.sort(expected);
            QuickStats got =
                    randomizedQuickSortCopy(a, random);
            require(Arrays.equals(got.sorted(), expected),
                    "quicksort wrong output");
            require(Arrays.equals(a, original),
                    "quicksort mutated input");
            require(got.comparisons() >=
                    Math.max(0, n - 1),
                    "quicksort too few comparisons");
            require(got.comparisons() <=
                    (long) n * (n - 1) / 2,
                    "quicksort too many comparisons");
        }
        System.out.println("quickSortRandom=PASS (500 cases)");
    }

    public static void main(String[] args) {
        int[] values = {4, 1, 7, 2, 8, 3, 6, 5};
        SearchResult first = linearSearch(values, 4);
        SearchResult last = linearSearch(values, 5);
        SearchResult absent = linearSearch(values, 99);
        System.out.println("linear best index="
                + first.index() + " comparisons="
                + first.comparisons());
        System.out.println("linear worstPresent index="
                + last.index() + " comparisons="
                + last.comparisons());
        System.out.println("linear absent index="
                + absent.index() + " comparisons="
                + absent.comparisons());
        System.out.printf(Locale.ROOT,
                "linear uniformPresent expected=%.2f%n",
                (values.length + 1) / 2.0);
        double p = 0.5;
        double expected = p * (values.length + 1) / 2.0
                + (1.0 - p) * values.length;
        System.out.printf(Locale.ROOT,
                "linear presentP50 expected=%.2f%n", expected);

        SearchResult randomPresent = randomizedSearch(
                values, 4, new Random(2026L));
        SearchResult randomAbsent = randomizedSearch(
                values, 99, new Random(2026L));
        System.out.println("randomSearch present index="
                + randomPresent.index());
        System.out.println("randomSearch absent index="
                + randomAbsent.index() + " comparisons="
                + randomAbsent.comparisons());

        InsertionStats sorted = insertionSortCopy(
                new int[]{1,2,3,4,5,6,7,8});
        InsertionStats reversed = insertionSortCopy(
                new int[]{8,7,6,5,4,3,2,1});
        InsertionStats sample = insertionSortCopy(
                new int[]{4,1,3,2});
        System.out.println("insertion sorted comparisons="
                + sorted.comparisons() + " shifts="
                + sorted.shifts());
        System.out.println("insertion reversed comparisons="
                + reversed.comparisons() + " shifts="
                + reversed.shifts());
        System.out.println("insertion sample sorted="
                + Arrays.toString(sample.sorted())
                + " comparisons=" + sample.comparisons()
                + " shifts=" + sample.shifts());

        long[] exhaustive = new long[4];
        enumerateFour(new int[]{0,1,2,3}, 0, exhaustive);
        System.out.printf(Locale.ROOT,
                "insertion exhaustive n=4 permutations=%d"
                + " averageComparisons=%.4f"
                + " averageShifts=%.4f%n",
                exhaustive[0],
                exhaustive[1] / (double) exhaustive[0],
                exhaustive[2] / (double) exhaustive[0]);
        System.out.printf(Locale.ROOT,
                "randomSearch exhaustive n=4 permutations=%d"
                + " averageComparisons=%.4f%n",
                exhaustive[0],
                exhaustive[3] / (double) exhaustive[0]);

        QuickStats quick = randomizedQuickSortCopy(
                new int[]{8,7,6,5,4,3,2,1},
                new Random(2026L));
        int[] expectedSorted = {1,2,3,4,5,6,7,8};
        System.out.println("quicksort randomized sorted="
                + Arrays.toString(quick.sorted())
                + " verified="
                + Arrays.equals(quick.sorted(), expectedSorted));
        System.out.printf(Locale.ROOT,
                "quicksort theoretical n=8"
                + " expectedComparisons=%.4f%n",
                expectedQuickSortComparisons(8));

        randomSearchTests();
        randomInsertionTests();
        randomQuickSortTests();

        try {
            linearSearch(null, 42);
            throw new AssertionError("Expected null rejection");
        } catch (NullPointerException expectedNull) {
            System.out.println("invalidInput=rejected");
        }
    }
}
~~~

### Lệnh chạy

~~~bash
javac -encoding UTF-8 ComplexityCasesDemo.java
java ComplexityCasesDemo
~~~

### Đầu ra dự kiến chính xác

~~~text
linear best index=0 comparisons=1
linear worstPresent index=7 comparisons=8
linear absent index=-1 comparisons=8
linear uniformPresent expected=4.50
linear presentP50 expected=6.25
randomSearch present index=0
randomSearch absent index=-1 comparisons=8
insertion sorted comparisons=7 shifts=0
insertion reversed comparisons=28 shifts=28
insertion sample sorted=[1, 2, 3, 4] comparisons=6 shifts=4
insertion exhaustive n=4 permutations=24 averageComparisons=4.9167 averageShifts=3.0000
randomSearch exhaustive n=4 permutations=24 averageComparisons=2.5000
quicksort randomized sorted=[1, 2, 3, 4, 5, 6, 7, 8] verified=true
quicksort theoretical n=8 expectedComparisons=16.9214
searchRandom=PASS (600 cases)
insertionRandom=PASS (600 cases)
quickSortRandom=PASS (500 cases)
invalidInput=rejected
~~~

### Giải thích các dòng output

**Linear:** input dài 8. Target=4 ở đầu nên chỉ 1 so sánh; target=5 ở cuối và target=99 không có đều cần 8 so sánh. Giả định vị trí thành công đều cho 4,50; thêm xác suất thành công p=0,5 cho 6,25. Hai giá trị này không đo được chỉ từ một lần chạy thực tế.

**Random search:** xáo thứ tự chỉ số; target=4 duy nhất tại index0 nên bất kể thứ tự kiểm tra thế nào, kết quả index vẫn là 0, nhưng số comparisons có thể thay đổi và không được in như một hằng số. Target=99 vắng mặt nên lần nào cũng phải kiểm hết 8 phần tử.

**Insertion:** mảng đã sort dài 8 cần 7 comparisons, không shifts; mảng đảo ngược cần 28 comparisons và 28 shifts. Mảng [4,1,3,2] được sắp thành [1,2,3,4], cần 6 comparisons và 4 shifts theo đúng cách đếm đã định nghĩa.

**Exhaustive:** liệt kê **mọi** hoán vị n=4 cho 24 trường hợp; trung bình comparisons của insertion sort là 118/24≈4,9167, shifts=72/24=3. Vị trí của một target cố định trong thứ tự quét random có trung bình 60/24=2,5.

**Quicksort:** pivot ngẫu nhiên chọn bằng `Random.nextInt`, nhưng kết quả sắp phải đúng và giống `Arrays.sort`. Dòng lý thuyết 16,9214 đến từ công thức điều hòa, **không phải** số phép so sánh của một lượt chạy. Công thức này giả định các khóa phân biệt.

**Các dòng PASS:** đối chiếu input ngẫu nhiên với oracle độc lập: kiểm kết quả search, phép so sánh và vắng mặt; insertion sort đối chiếu `Arrays.sort` và đếm nghịch thế trực tiếp O(n²); quicksort đối chiếu `Arrays.sort` và giới hạn số comparisons. Dữ liệu test gồm mảng rỗng, duplicate keys, số âm và cực trị int.

**invalidInput:** một mảng null vi phạm hợp đồng; hàm ném `NullPointerException` thay vì âm thầm coi như empty.

## 18. Kiểm thử độc lập cho bốn cách phân tích

### 18.1. Xác nhận best và worst bằng input xây dựng

Với linear search, đặt target ở index0 cho best; ở index n−1 hoặc vắng mặt cho worst.

Với insertion sort, đặt dãy tăng không giảm cho best; giảm nghiêm ngặt cho worst. Đừng chỉ thử một dãy ngẫu nhiên rồi đoán worst case.

### 18.2. Kiểm average bằng vét cạn input nhỏ

Với n=4, liệt kê mọi hoán vị của bốn giá trị phân biệt. Đếm comparisons và shifts chính xác, chia cho 24. Đây là một cách kiểm công thức lý thuyết dưới **phân phối hoán vị đều**.

Khi n tăng, n! quá lớn; chuyển sang mô phỏng random và/hoặc chứng minh bằng biến chỉ báo. Không thể vét cạn n=100 hoán vị trong thực tế.

### 18.3. Kiểm thuật toán ngẫu nhiên bằng oracle kết quả

Randomized quicksort phải sắp đúng **bất kể pivot được bốc thế nào**. Oracle `Arrays.sort` kiểm output theo giá trị, không lấy “kỳ vọng lý thuyết” làm đáp án sắp xếp.

Số comparisons thay đổi theo random seed; không ép nó bằng 16,9214 khi n=8. Ta có thể kiểm cận tất định đơn giản:

\[
\max(0,n-1)\le C\le n(n-1)/2
\]

cho Lomuto partition trên n phần tử với mỗi lần partition k phần tử dùng k−1 comparisons.

### 18.4. Kiểm cả tính đúng và độ phức tạp

Một thuật toán có thể **trả đúng** nhưng làm quá nhiều phép toán; ngược lại có thể **rất nhanh** nhưng trả sai. Test nên tách:

- **Correctness:** kết quả có thỏa đặc tả?
- **Cost contract:** số comparisons/operations có nằm trong cận hoặc công thức quy định?
- **Performance benchmark:** trên máy thực tế với data lớn, latency/throughput có đáp ứng SLA?

Một test có 500 seed PASS không chứng minh upper bound cho **mọi seed**. Muốn chứng minh worst case cần lập luận cấu trúc thuật toán, không chỉ dựa trên random testing.

## 19. Vấn đề độ chính xác của số đo

### Đếm comparisons với insertion sort

Nếu code viết:

~~~java
while (j >= 0 && a[j] > key) {
    a[j + 1] = a[j];
    j--;
}
~~~

không thể đếm số comparisons bằng số vòng lặp thành công, vì còn lần cuối `a[j]>key` thất bại khi j≥0. Cần đặt bộ đếm **bên trong vòng lặp có kiểm soát**, như mã đầy đủ đã làm.

Nếu thay cách viết hoặc dùng sentinel, công thức chính xác của comparisons có thể đổi dù thứ tự asymptotic không đổi. **Trước khi chứng minh công thức chính xác, phải nêu cách đếm chính xác.**

### Big-O bỏ hằng số nhưng không bỏ ngữ nghĩa

Hai thuật toán đều O(n log n) có thể có số phép ghi khác nhau, cache behavior khác nhau và hệ số rất khác. Big-O không dùng để dự đoán thời gian tuyệt đối cho input nhỏ.

### Kết quả ngẫu nhiên tái lập

Nếu muốn debug một lần chạy random tệ, lưu seed, input, phiên bản thuật toán và tham số. Java `Random(seed)` cho chuỗi có thể tái lập theo triển khai đã công bố; nhưng một pipeline đa luồng với thứ tự tiêu thụ RNG khác nhau có thể vẫn không tái lập chỉ bằng một seed.

### Đánh giá trung bình của latency

Latency thường có phân phối lệch và đuôi dài. Chỉ báo trung bình 20 ms không nói rằng 99% request dưới 100 ms. Với sản phẩm thực tế, nên xem thêm median, p95, p99, max, deadline misses và sự thay đổi theo tải.

## 20. Các hiểu lầm thường gặp

1. Gọi best case là bảo đảm thời gian chạy tối đa.
2. So best case của thuật toán A với worst case của thuật toán B rồi kết luận A luôn tốt hơn.
3. Nói “average O(n)” mà không xác định phân phối input.
4. Coi average là trung bình cộng **một vài test tự chọn** nhưng không công bố cách lấy mẫu.
5. Gọi expected time chỉ dành cho thuật toán random; average cũng dùng toán tử expectation.
6. Không phân biệt random input với random pivot.
7. Cho rằng randomized quicksort có worst-case O(n log n) vì kỳ vọng O(n log n).
8. Cho rằng số comparisons của một lượt chạy phải bằng kỳ vọng thập phân.
9. Áp công thức quicksort khóa phân biệt cho mảng toàn giá trị trùng.
10. Đếm comparisons của insertion sort chỉ bằng số shifts.
11. Áp công thức average của insertion sort uniform permutations cho input phần lớn đã sort.
12. Nói linear search “trung bình n/2” khi target thường vắng mặt.
13. Bỏ qua xác suất thành công p.
14. Quên mảng rỗng có 0 phép so sánh.
15. Dùng Big-O như một dấu bằng thời gian tuyệt đối.
16. Nghĩ Big-Ω chỉ dành cho best case, Big-O chỉ dành cho worst case.
17. Lẫn lộn chi phí một thao tác với chi phí cả chuỗi thao tác.
18. Gọi amortized O(1) là average-case O(1) do input ngẫu nhiên.
19. Từ average O(1) suy ra không có input O(n).
20. Từ \(E[T]=100\) suy ra mọi lần chạy dưới 100.
21. Dùng tính tuyến tính của expectation nhưng tự yêu cầu độc lập không cần thiết.
22. Nhân kỳ vọng của hai biến phụ thuộc nhau như thể chúng độc lập.
23. Đổi max và expectation mà không đổi mô hình adversary.
24. Không ghi rõ đối tượng được đếm: comparisons, shifts, allocations, I/O hay CPU time.
25. Bỏ chi phí copy, tạo permutation hoặc chuẩn bị dữ liệu khi so runtime.
26. Dùng số int cho tổng phép đếm có thể vượt int trong input lớn.
27. Không thử input đã sort, reverse, duplicate, absent và empty.
28. Không đối chiếu output random quicksort với oracle sắp xếp độc lập.
29. Không kiểm cận comparisons trong bộ test.
30. Chỉ tin các con số benchmark mà không xét JVM warmup, JIT, GC và OS noise.
31. Dùng uniform permutation mặc định cho mọi dataset nghiệp vụ.
32. Không tách lý thuyết expected value và high-probability guarantee.
33. Kết luận thuật toán O(n²) “luôn chạy chậm hơn” O(n log n) ở mọi n nhỏ.
34. Không xét space complexity theo best/worst/expected riêng với time.
35. Không nêu hiệu ứng collision khi nói hash lookup expected O(1).
36. Dựa vào 500 lượt chạy thành công để tuyên bố chứng minh một cận toán học.

## 21. Bài tập có lời giải

**Bài 1.** Best case là gì? **Đáp án:** chi phí nhỏ nhất trên các input hợp lệ cùng kích thước n.

**Bài 2.** Worst case là gì? **Đáp án:** chi phí lớn nhất trên các input hợp lệ cùng kích thước n.

**Bài 3.** Có thể so best ở n=10 với worst ở n=1.000 rồi gọi cùng hàm B(n),W(n) không? **Đáp án:** không; định nghĩa phải cố định cùng n.

**Bài 4.** Average case thiếu thông tin gì nếu chỉ biết n? **Đáp án:** phân phối input và phép đo chi phí.

**Bài 5.** Ký hiệu \(\mathbb E_X[C(X)]\) chỉ kỳ vọng trên gì? **Đáp án:** phân phối input X.

**Bài 6.** \(\mathbb E_R[C(x,R)]\) chỉ kỳ vọng trên gì? **Đáp án:** nguồn random R của thuật toán với input x cố định.

**Bài 7.** Linear search n=8, target đầu tiên, số comparisons? **Đáp án:** 1.

**Bài 8.** Linear search n=8, target vắng mặt, số comparisons? **Đáp án:** 8.

**Bài 9.** Linear search n=8, target duy nhất ở vị trí cuối, số comparisons? **Đáp án:** 8.

**Bài 10.** Target duy nhất đều giữa 8 vị trí, average comparisons? **Đáp án:** (8+1)/2=4,5.

**Bài 11.** Target có mặt xác suất 1/2 và vị trí đều khi có, kỳ vọng n=8? **Đáp án:** 6,25.

**Bài 12.** Nếu target luôn absent thì kỳ vọng n=8? **Đáp án:** 8.

**Bài 13.** Nếu p=1 và vị trí đều thì kỳ vọng n=8? **Đáp án:** 4,5.

**Bài 14.** Với random-order search và target duy nhất tại index0, có cần input random không? **Đáp án:** không; ngẫu nhiên nằm ở thứ tự quét.

**Bài 15.** Random-order search n=4, target duy nhất, kỳ vọng comparisons? **Đáp án:** 2,5.

**Bài 16.** Random-order search n=8, target xuất hiện ở k=3 vị trí, kỳ vọng? **Đáp án:** (8+1)/(3+1)=9/4=2,25.

**Bài 17.** Chi phí tạo random permutation có thể bỏ qua khi đánh giá wall-clock không? **Đáp án:** không; chỉ tách khỏi số comparisons target trong mô hình đã công bố.

**Bài 18.** Insertion sort trên mảng tăng n=8 có bao nhiêu comparisons theo định nghĩa bài? **Đáp án:** 7.

**Bài 19.** Insertion sort trên mảng tăng n=8 có bao nhiêu shifts? **Đáp án:** 0.

**Bài 20.** Insertion sort trên mảng giảm nghiêm ngặt n=8 có bao nhiêu shifts? **Đáp án:** 8×7/2=28.

**Bài 21.** Trường hợp tốt nhất insertion sort thuộc Θ nào? **Đáp án:** Θ(n) với n lớn.

**Bài 22.** Worst case insertion sort thuộc Θ nào? **Đáp án:** Θ(n²).

**Bài 23.** Average insertion sort uniform permutations thuộc Θ nào? **Đáp án:** Θ(n²).

**Bài 24.** Số nghịch thế kỳ vọng trên n phần tử phân biệt hoán vị đều? **Đáp án:** n(n−1)/4.

**Bài 25.** Cần các biến chỉ báo nghịch thế độc lập để cộng kỳ vọng không? **Đáp án:** không.

**Bài 26.** Với n=4, average shifts insertion sort? **Đáp án:** 3.

**Bài 27.** Với n=4, average comparisons theo cách đếm trong bài? **Đáp án:** 59/12≈4,9167.

**Bài 28.** Quicksort best-case time thường là? **Đáp án:** Θ(n log n) với partition gần cân bằng.

**Bài 29.** Quicksort worst-case time? **Đáp án:** Θ(n²) khi partition luôn cực lệch.

**Bài 30.** Randomized quicksort trên các khóa phân biệt có expected comparisons cấp nào? **Đáp án:** Θ(n log n).

**Bài 31.** Randomized quicksort có loại bỏ hoàn toàn khả năng chạy Θ(n²) không? **Đáp án:** không.

**Bài 32.** Công thức expected comparisons quicksort trên n khóa phân biệt? **Đáp án:** \(2(n+1)H_n-4n\).

**Bài 33.** Tại sao \(H_n\) xuất hiện? **Đáp án:** cộng xác suất hai phần tử hạng i,j được so sánh, bằng 2/(j−i+1).

**Bài 34.** Tại n=8, kỳ vọng quicksort xấp xỉ bao nhiêu comparisons? **Đáp án:** 16,9214.

**Bài 35.** Quicksort Lomuto với toàn bộ key bằng nhau có giữ công thức distinct-keys không? **Đáp án:** không; partition có thể lệch và tốn Θ(n²).

**Bài 36.** Worst-case expected time viết thế nào? **Đáp án:** \(\max_x\mathbb E_R[C(x,R)]\).

**Bài 37.** Worst over all random outcomes viết thế nào? **Đáp án:** \(\max_{x,r}C(x,r)\).

**Bài 38.** O và Θ có phải tên khác của worst và average không? **Đáp án:** không; là ký hiệu cận của một hàm chi phí đã chọn.

**Bài 39.** Amortized O(1) cho append mảng động có cần input ngẫu nhiên không? **Đáp án:** không, chứng minh trên tổng chi phí chuỗi thao tác.

**Bài 40.** Expected O(1) hash lookup có đòi giả định không? **Đáp án:** có, về hashing, collision và hệ số tải.

**Bài 41.** Expected 101 bước có bảo đảm lần nào cũng không quá 101 bước không? **Đáp án:** không.

**Bài 42.** Markov cho biến không âm T và a>0 là gì? **Đáp án:** \(\Pr[T\ge a]\le\mathbb E[T]/a\).

**Bài 43.** Khi khảo sát latency thực tế nên nhìn gì ngoài mean? **Đáp án:** median, các percentile đuôi như p95/p99, max và deadline misses.

**Bài 44.** Tại sao quét input random rồi đo có thể không phản ánh production? **Đáp án:** phân phối production có thể khác phân phối tạo test.

**Bài 45.** Vét cạn 24 hoán vị n=4 chứng minh kết quả gì? **Đáp án:** trung bình chính xác theo **uniform permutations n=4**, không phải mọi n hay mọi phân phối.

**Bài 46.** Random quicksort sort đúng trên 500 input có chứng minh bound O(n log n) cho mọi seed không? **Đáp án:** không; bound kỳ vọng cần chứng minh theo xác suất pivot.

**Bài 47.** Với Java int, làm sao lưu tổng số phép so sánh lớn hơn 2³¹−1? **Đáp án:** dùng long cho counter và kiểm giới hạn.

**Bài 48.** Vì sao cần đếm comparisons của insertion sort ngay cả lần thoát while? **Đáp án:** vì lần kiểm điều kiện khóa thất bại vẫn là một lần so sánh thật.

## 22. Checklist phân tích bài toán

1. Đã xác định input size n, tập input hợp lệ \(I_n\) và loại chi phí?
2. Đã tách so sánh, dịch chuyển, cấp phát, I/O và thời gian thực tế?
3. Best case có một input chứng minh đạt được?
4. Worst case có một input chứng minh đạt được hoặc có cận chứng minh?
5. Average case có **phân phối input** cụ thể?
6. Có nêu target có thể absent, duplicate hay chỉ xuất hiện một lần?
7. Nếu thuật toán random, có chỉ ra nguồn random và cách chọn?
8. Đã phân biệt \(E_X\), \(E_R\) và \(E_{X,R}\)?
9. Đã phân biệt max trên input trước hay sau khi random coins được rút?
10. Có nêu worst-case expected khác worst random run?
11. Ký hiệu O/Ω/Θ có gắn với đúng hàm chi phí đang xét?
12. Nếu đếm comparisons, có quy định có tính lần kiểm thất bại không?
13. Nếu dữ liệu có duplicate, công thức phân tích có còn đúng?
14. Có tách chi phí tiền xử lý khỏi cost metric đang đếm?
15. Có cân nhắc memory copy, auxiliary array và stack?
16. Có dùng tuyến tính của expectation đúng mà không giả định độc lập thừa?
17. Có tránh thay \(\mathbb E[XY]\) bằng \(\mathbb E[X]\mathbb E[Y]\) khi chưa chứng minh độc lập?
18. Có hiểu expectation không tự cho worst-case hay high-probability bound?
19. Có tránh nhầm average với amortized?
20. Có tạo test best, worst, random và trường hợp biên?
21. Có oracle độc lập so **kết quả**, không chỉ đo số bước?
22. Có xác nhận công thức bằng vét cạn input nhỏ khi khả thi?
23. Có ghi rõ seed, kích thước và cách sinh dữ liệu benchmark?
24. Có phân biệt kết quả test thực nghiệm với chứng minh toán học?
25. Có cân nhắc phân phối dữ liệu thực của hệ thống thay vì mặc định uniform?

**Kết luận:** **best case** là chi phí nhỏ nhất, **worst case** là chi phí lớn nhất trên các input cùng kích thước. **Average case** là kỳ vọng theo một **phân phối input đã nêu**; **expected cost** là kỳ vọng theo nguồn ngẫu nhiên được xác định, có thể là input, random choices của thuật toán hoặc cả hai. Linear search cho công thức trực quan; insertion sort cho thấy best Θ(n) nhưng average/worst Θ(n²); randomized quicksort cho thấy worst Θ(n²) vẫn tồn tại trong khi expected Θ(n log n) trên các khóa phân biệt. Luôn công bố **mô hình chi phí, giả định xác suất, cận nào đang chứng minh, kiểu dữ liệu và cách kiểm chứng** trước khi dùng một nhãn độ phức tạp.
