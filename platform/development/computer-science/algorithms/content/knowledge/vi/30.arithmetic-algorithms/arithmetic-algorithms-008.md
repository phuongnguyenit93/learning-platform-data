# Sàng phân đoạn và xử lý khoảng số lớn

**Sàng phân đoạn** (*segmented sieve*) là kỹ thuật tìm các **số nguyên tố trong một khoảng số nguyên [L,R]** mà **không cần cấp phát một mảng dài tới R**. Thay vì sàng mọi số từ 0 đến R, ta chỉ tính các số nguyên tố nhỏ đến **\(\lfloor\sqrt R\rfloor\)**, sau đó dùng chúng để đánh dấu hợp số trong từng **cửa sổ nhỏ** của khoảng cần xét.

Đây là công cụ quan trọng của **thuật toán số học** khi R có giá trị lớn, chẳng hạn cỡ \(10^{12}\), nhưng khoảng [L,R] tương đối ngắn. Sàng Eratosthenes thông thường cần mảng kích thước O(R), không khả thi khi R lên tới hàng nghìn tỷ; sàng phân đoạn chỉ cần lưu các **số nguyên tố cơ sở** và một cửa sổ kích thước B.

Tuy nhiên, **không phải cứ dùng segmented sieve là xử lý được mọi R kiểu long**. Bản cổ điển vẫn cần tìm **toàn bộ số nguyên tố không vượt \(\sqrt R\)**. Nếu R lớn đến gần `Long.MAX_VALUE`, \(\sqrt R\) xấp xỉ \(3{,}037{,}000{,}499\), và việc tạo mảng sàng cơ sở hoặc danh sách số nguyên tố có thể vượt ngân sách bộ nhớ. Bài học sẽ chỉ rõ **giới hạn khả thi**, phương pháp đánh dấu an toàn số học và hướng thay thế cho khoảng rất xa.

Các nội dung chính:

- Hiểu chính xác đề “đếm/liệt kê số nguyên tố trong khoảng **[L,R] đóng**”.
- Chứng minh vì sao chỉ cần các số nguyên tố cơ sở \(\le\lfloor\sqrt R\rfloor\).
- Tính bội đầu tiên cần gạch: \(\max(p^2,\lceil blockLow/p\rceil p)\).
- Chia đoạn thành các cửa sổ B để kiểm soát bộ nhớ, **không** cấp phát `boolean[R+1]`.
- Tránh tràn số với `long` khi tính biên khối, bội đầu, bình phương và chỉ số.
- Đếm kết quả mà **không giữ tất cả số nguyên tố** trong bộ nhớ; chỉ giữ một số phần tử mẫu đầu tiên.
- Java 17+ độc lập, lệnh biên dịch/chạy, stdout xác định, kiểm thử bằng vét cạn và ví dụ lớn quanh \(10^{12}\).
- Phân tích độ phức tạp thực tế theo \(R\), độ rộng khoảng và kích thước cửa sổ.

## 1. Định nghĩa bài toán và các quy ước

Một số nguyên \(x\) được gọi là **số nguyên tố** khi \(x\ge2\) và chỉ có đúng hai ước dương: 1 và x.

Các ví dụ:

- 2, 3, 5, 7, 11, 13, 17, 19 là số nguyên tố.
- 4, 6, 8, 9, 10, 12, 15 là hợp số.
- 0, 1 và các số âm **không phải số nguyên tố**.

Cho hai số nguyên `long L` và `long R`, với `L<=R`. Bài toán:

\[
\boxed{\text{Tìm mọi }p\in\mathbb Z\text{ sao cho }L\le p\le R\text{ và }p\text{ nguyên tố}.}
\]

Có thể yêu cầu:

1. **Liệt kê** mọi số nguyên tố theo thứ tự tăng.
2. **Đếm** số nguyên tố.
3. **Lấy K số nguyên tố đầu tiên** để hiển thị/kiểm tra.
4. Trả lời **nhiều truy vấn khoảng** trên cùng một giới hạn R.

Trong bài, khoảng là **đóng [L,R]**: cả L và R đều được xét nếu chúng là số nguyên tố. Nếu một API dùng `[L,R)` nửa mở, phải đổi công thức độ dài và điều kiện vòng lặp.

### Ví dụ nhỏ

Với \([10,30]\):

\[
11,\ 13,\ 17,\ 19,\ 23,\ 29.
\]

Có **6** số nguyên tố. Dù L=10 không phải nguyên tố và R=30 không phải nguyên tố, hai đầu vẫn thuộc miền đang kiểm tra.

Với \([1,10]\), kết quả là \([2,3,5,7]\), có 4 số. Với \([-10,10]\) kết quả **vẫn** là \([2,3,5,7]\) vì mọi giá trị nhỏ hơn 2 đều bị loại.

Với \([14,16]\) không có số nguyên tố. Với \([17,17]\) có đúng một giá trị nguyên tố là 17.

**Chính sách đầu vào:** nếu `L>R`, chương trình báo lỗi thay vì tự đổi chỗ hai đầu hoặc lặng lẽ trả rỗng. Nếu `R<2`, kết quả hợp lệ là danh sách rỗng và count=0.

## 2. Vì sao sàng Eratosthenes toàn miền không phù hợp?

**Sàng Eratosthenes** cho các số từ 2 tới N dùng một mảng đánh dấu hợp số và gạch các bội của số nguyên tố nhỏ.

Cách tổng quát:

~~~text
isComposite[0..N] = false

for p = 2 .. floor(sqrt(N)):
    if not isComposite[p]:
        mark p*p, p*p+p, p*p+2p, ... <= N

all unmarked numbers >=2 are prime
~~~

Độ phức tạp quen thuộc:

\[
O(N\log\log N)\text{ thời gian},\qquad O(N)\text{ bộ nhớ}.
\]

Nếu cần mọi nguyên tố từ 1 đến \(10^6\), cách này rất phù hợp. Nhưng với truy vấn:

\[
L=10^{12},\qquad R=10^{12}+100
\]

thì **chỉ có 101 ứng viên**. Cấp phát một mảng tới \(10^{12}\) là cực kỳ lãng phí và không thực tế.

### Phép thử chia từng ứng viên cũng chưa tối ưu

Một lựa chọn khác là thử mỗi x trong [L,R] có chia hết cho các số d từ 2 tới \(\sqrt x\) hay không. Với W=R−L+1 ứng viên, chi phí trực tiếp có thể lên đến:

\[
O(W\sqrt R).
\]

Với R cỡ \(10^{12}\), \(\sqrt R=10^6\); nếu khoảng có hàng trăm nghìn ứng viên, thử chia ngây thơ sẽ tốn nhiều phép toán.

Sàng phân đoạn kết hợp ưu điểm:

- **Chỉ** sinh các nguyên tố nhỏ một lần đến \(\sqrt R\).
- Dùng các nguyên tố ấy đánh dấu **theo lô** mọi hợp số trong đúng khoảng cần truy vấn.
- Không tạo mảng theo toàn bộ giá trị R.

## 3. Định lý nền tảng: chỉ cần các ước nguyên tố đến √R

**Mệnh đề.** Nếu \(x\ge2\) là hợp số, thì x có ít nhất một ước nguyên tố p thỏa:

\[
\boxed{p\le\sqrt x}.
\]

**Chứng minh.** Vì x hợp số, tồn tại \(a,b>1\) sao cho \(x=ab\). Nếu cả a và b đều lớn hơn \(\sqrt x\), ta có \(ab>x\), mâu thuẫn. Do đó ít nhất một thừa số không vượt \(\sqrt x\). Thừa số ấy có một ước nguyên tố p không vượt chính nó, nên \(p\le\sqrt x\).

Với mọi x thuộc [L,R] và x≥2:

\[
\sqrt x\le\sqrt R.
\]

Vì thế **mọi hợp số trong khoảng** đều có một ước nguyên tố thuộc tập:

\[
P=\{p:\ p\text{ nguyên tố},\ p\le\lfloor\sqrt R\rfloor\}.
\]

Nếu đánh dấu tất cả bội phù hợp của mọi p trong P, những ứng viên x≥2 còn lại chính là các số nguyên tố.

### Vì sao phải dùng floor√R, không phải floor√L?

Một hợp số gần R có thể chứa thừa số nguyên tố lớn hơn \(\sqrt L\), đặc biệt khi khoảng rộng. Dùng \(\lfloor\sqrt L\rfloor\) làm giới hạn số nguyên tố cơ sở là **không đủ** nói chung.

Ví dụ nếu chỉ chuẩn bị các prime tới \(\sqrt{10}=3\) rồi sàng khoảng [10,49], số 49=7×7 có thể không bị gạch, mặc dù không nguyên tố. Giới hạn đúng cho toàn khoảng là \(\lfloor\sqrt{49}\rfloor=7\).

### Có cần đánh dấu theo mọi số từ 2 đến √R?

Không. Chỉ dùng **số nguyên tố** cơ sở là đủ. Nếu một ứng viên chia hết cho một hợp số d, nó cũng chia hết cho ít nhất một ước nguyên tố của d; việc đánh dấu theo d là thừa.

Vì thế bước đầu tiên là sàng thông thường trên **miền nhỏ [2, floor√R]**.

## 4. Hai giai đoạn của sàng phân đoạn

Giả sử:

\[
L=10^{12},\quad R=10^{12}+100.
\]

Suy ra \(\lfloor\sqrt R\rfloor=10^6\) với giá trị R này. Ta làm:

**Giai đoạn A — Prime cơ sở**

Sàng Eratosthenes thông thường từ 2 đến 1.000.000. Số lượng số nguyên tố cơ sở vào khoảng 78 nghìn (chính xác có 78.498 số nguyên tố không vượt 1.000.000), chi phí nhớ và tính toán vẫn khá nhỏ so với sàng đến \(10^{12}\).

**Giai đoạn B — Đánh dấu đúng khoảng cần xét**

Tạo mảng boolean chỉ cho 101 giá trị:

~~~text
index trong mảng:  0       1      ... 100
giá trị thực:     10^12  10^12+1  ... 10^12+100
~~~

Duyệt các prime cơ sở và gạch bội nằm trong khoảng. Những vị trí chưa gạch đại diện cho số nguyên tố.

Mảng kết quả không cần có chỉ số là giá trị số nguyên cực lớn. Ta dùng **ánh xạ chỉ số cục bộ**:

\[
\boxed{index(x)=x-blockLow}.
\]

Ví dụ trong một khối bắt đầu tại `blockLow=1_000_000_000_000`, số `blockLow+17` nằm ở vị trí mảng **17**, không phải vị trí một nghìn tỷ.

## 5. Bội đầu tiên phải đánh dấu: công thức quan trọng nhất

Cho một cửa sổ \([A,B]\) đóng, với \(A\ge2\), và một số nguyên tố cơ sở p.

Ta cần tìm bội nhỏ nhất của p nằm **không trước A**:

\[
firstMultiple=\left\lceil\frac Ap\right\rceil p.
\]

Nhưng **không** được bắt đầu ở p khi cửa sổ chứa p, vì **p chính là số nguyên tố**, không phải hợp số. Sàng Eratosthenes đánh dấu hợp số bắt đầu từ \(p^2\). Do đó:

\[
\boxed{start=\max\left(p^2,\ \left\lceil\frac Ap\right\rceil p\right)}.
\]

Nếu `start>B`, p không tạo dấu mới trong cửa sổ. Ngược lại đánh dấu các số:

\[
start,\ start+p,\ start+2p,\ldots\le B.
\]

### Tại sao phải lấy max với p²?

Xét \([2,10]\), p=2:

- Bội đầu tiên của 2 trong cửa sổ là 2.
- Nếu gạch từ 2, ta đánh dấu sai **số nguyên tố 2**.
- Dùng \(\max(2^2,2)=4\), đánh dấu 4,6,8,10; số 2 vẫn để trống, đúng.

Với \([2,10]\), p=3:

- \(\lceil2/3\rceil\cdot3=3\).
- \(p^2=9\).
- Bắt đầu gạch tại 9, không gạch 3.

Lý do tổng quát: nếu một hợp số x là bội của p mà x<p², thừa số x/p nhỏ hơn p. Nó đã có ước nguyên tố nhỏ hơn p và sẽ được gạch ở lượt trước. Do đó không bỏ sót hợp số khi bắt đầu từ p².

### Vì sao không chỉ bắt đầu tại p²?

Nếu cửa sổ \([A,B]\) nằm rất xa, chẳng hạn A=\(10^{12}\), p² có thể nhỏ hơn A rất nhiều. Bắt đầu vòng từ p² và tăng p cho tới A là **cực kỳ chậm**, gần như mất lợi thế của sàng phân đoạn.

Phải nhảy thẳng tới **bội đầu tiên trong cửa sổ**, rồi so với p².

### Ví dụ [10,30]

Các prime cơ sở đến \(\lfloor\sqrt{30}\rfloor=5\) là 2,3,5:

| Prime p | p² | Bội đầu tiên ≥10 | start | Đánh dấu |
|---|---:|---:|---:|---|
| 2 | 4 | 10 | 10 | 10,12,14,16,18,20,22,24,26,28,30 |
| 3 | 9 | 12 | 12 | 12,15,18,21,24,27,30 |
| 5 | 25 | 10 | 25 | 25,30 |

Các số ≥2 chưa bị gạch là:

\[
\boxed{11,\ 13,\ 17,\ 19,\ 23,\ 29.}
\]

Đây là danh sách nguyên tố cần tìm.

## 6. Tránh tràn số khi tính bội đầu tiên

Công thức toán học \(\lceil A/p\rceil p\) rất rõ, nhưng cài đặt với kiểu `long` phải tránh những biểu thức có thể vượt miền giá trị.

Một cách quen thuộc với A≥0 là:

~~~java
long first = ((A + p - 1) / p) * p;
~~~

Nhưng **`A+p-1` có thể tràn long** khi A gần `Long.MAX_VALUE`; phép nhân ở cuối cũng có nguy cơ tràn nếu bội kế tiếp nằm ngoài miền long.

### Cách dùng phần dư an toàn hơn

Vì trong bài ta chỉ sàng các cửa sổ có `blockLow>=2`, nên p>0 và số dư `blockLow%p` không âm:

~~~java
long remainder = blockLow % p;
long delta = remainder == 0 ? 0 : p - remainder;
~~~

`delta` là khoảng cách tới bội tiếp theo của p, nằm trong [0,p−1].

Nếu `delta > blockHigh-blockLow`, **không có bội p nào trong cửa sổ**, có thể bỏ qua p mà **không thực hiện phép cộng có nguy cơ tràn**.

Ngược lại:

~~~java
long firstMultiple = blockLow + delta;
long start = Math.max((long) p * p, firstMultiple);
~~~

Phép cộng `blockLow+delta` an toàn vì `delta<=blockHigh-blockLow` ⇒ `blockLow+delta<=blockHigh`.

Khi đang gạch x và muốn chuyển sang x+p, cũng có thể kiểm:

~~~java
if (x > blockHigh - p) {
    break;
}
x += p;
~~~

Thao tác này tránh tăng vượt blockHigh rồi mới so sánh, đặc biệt hữu ích khi giới hạn tiến gần miền số nguyên tối đa.

### Nhân p*p bằng long, không dùng int

Nếu p là `int`, biểu thức `p*p` mặc định nhân bằng int **trước** khi chuyển sang long. Khi p lớn hơn khoảng 46.340, bình phương vượt `Integer.MAX_VALUE`, có thể tràn.

Đúng:

~~~java
long square = 1L * p * p;
~~~

Sai trong trường hợp p lớn:

~~~java
long square = p * p; // Integer multiplication may overflow first.
~~~

Bản demo giới hạn căn R theo **ngân sách bộ nhớ có cấu hình**, và nhân p*p trong long.

## 7. Chia khoảng thành cửa sổ nhỏ: segmented sieve dạng block

Nếu \([L,R]\) có độ rộng W tương đối nhỏ, ta có thể tạo mảng cho toàn khoảng W và đánh dấu một lần. Nhưng nếu W rất lớn, ngay cả mảng W cũng có thể gây hết bộ nhớ.

Giải pháp là chia:

~~~text
[L, R] gồm các block dài tối đa B:

block 1: [L, min(L+B-1,R)]
block 2: [high1+1, min(high1+B,R)]
block 3: ...
~~~

Trong chương trình, ta chỉ xử lý từ \(\max(2,L)\), vì số nhỏ hơn 2 chắc chắn không nguyên tố.

Với B=16 và khoảng \([1,40]\), các block thực sự xử lý là:

~~~text
[2,17]     tối đa 16 số
[18,33]    tối đa 16 số
[34,40]    7 số
~~~

Mỗi block dùng một mảng `boolean[] composite` mới, kích thước đúng số giá trị của block, tối đa B. Sau khi xử lý xong block, có thể tăng count và xuất các nguyên tố rồi **giải phóng mảng** trước block tiếp theo.

### Có được dùng lại các prime cơ sở giữa các block?

**Có, và nên dùng.** Tập prime cơ sở được tạo một lần tới \(\sqrt R\), là đủ để đánh dấu hợp số trong **mọi block** của truy vấn [L,R]. Không nên sàng lại từ 2 mỗi lần tạo block.

### Cách tính blockHigh không tràn

Biểu thức:

~~~java
long blockHigh = Math.min(blockLow + blockSize - 1, right);
~~~

về ý tưởng đúng, nhưng phép cộng `blockLow+blockSize-1` có thể tràn long **trước khi Math.min chạy**.

An toàn hơn:

~~~java
long blockHigh = blockLow
    + Math.min((long) blockSize - 1, right - blockLow);
~~~

Trong vòng lặp ta luôn biết `blockLow<=right` và `blockSize>=1`. Vì thế `right-blockLow>=0`, cộng thêm tối đa đúng khoảng cách tới right, không vượt giới hạn.

**Sau block cuối**, không được mù quáng đặt `blockLow=blockHigh+1` nếu right ở ranh giới lớn nhất của long. Cách an toàn:

~~~java
if (blockHigh == right) {
    break;
}
blockLow = blockHigh + 1;
~~~

Bản demo vẫn đặt giới hạn khả thi cho căn R, nhưng công thức biên khối này là thói quen lập trình tốt.

### Không giữ toàn bộ đáp án

Nếu cần **đếm** và in **K số đầu tiên**, không cần lưu hàng triệu kết quả. Ta duyệt các giá trị chưa đánh dấu theo thứ tự tăng:

~~~text
if not composite[offset]:
    prime = blockLow + offset
    count++
    if sample.size < K:
        sample.add(prime)
~~~

Như vậy memory đầu ra chỉ còn O(K). Nếu bài yêu cầu in **mọi** số nguyên tố, có thể xử lý bằng streaming hoặc callback ra file/đầu ra ngay khi tìm được, không cần gom toàn bộ thành `List<Long>` khổng lồ.

## 8. Chạy tay nhiều block trên một khoảng nhỏ

Xét \([2,30]\), kích thước cửa sổ B=10:

~~~text
block 1: [2,11]
block 2: [12,21]
block 3: [22,30]
~~~

Prime cơ sở tới \(\lfloor\sqrt{30}\rfloor=5\): [2,3,5].

**Block [2,11]:**

- p=2: bắt đầu từ max(4,2)=4, gạch 4,6,8,10.
- p=3: bắt đầu từ max(9,3)=9, gạch 9.
- p=5: vì 25>11, không cần đánh dấu ở block này.
- Số nguyên tố: 2,3,5,7,11.

**Block [12,21]:**

- p=2: gạch 12,14,16,18,20.
- p=3: gạch 12,15,18,21.
- p=5: 25>21, không cần.
- Số nguyên tố: 13,17,19.

**Block [22,30]:**

- p=2: gạch 22,24,26,28,30.
- p=3: gạch 24,27,30.
- p=5: gạch 25,30.
- Số nguyên tố: 23,29.

Gộp các block theo thứ tự:

\[
[2,3,5,7,11,\ 13,17,19,\ 23,29].
\]

Có đúng 10 số nguyên tố trong [2,30].

### Khi nào có thể dừng duyệt prime cơ sở trong một block?

Nếu `p*p>blockHigh`, mọi prime lớn hơn p cũng có bình phương vượt blockHigh. Các hợp số trong block đã có một prime factor nhỏ hơn các p ấy. Vì danh sách prime cơ sở tăng dần, ta có thể **break** vòng lặp đánh dấu các prime cho block đó.

Điều kiện `p*p>blockHigh` không thay thế bước **lọc các số dưới 2**. Nếu block chứa số 0 hoặc 1, chúng vẫn có thể không bị gạch; vì vậy khối đầu tiên phải bắt đầu từ ít nhất 2 hoặc phải đánh dấu 0,1 riêng.

## 9. Ví dụ khoảng lớn quanh 10¹²

Xét khoảng đóng:

\[
L=1\,000\,000\,000\,000,\quad
R=1\,000\,000\,000\,100.
\]

Mặc dù R rất lớn, độ rộng chỉ **101**. Căn nguyên chính là:

\[
\lfloor\sqrt R\rfloor=1\,000\,000.
\]

Sàng prime cơ sở đến một triệu và đánh dấu trong các block 32 giá trị. Kết quả có **4 số nguyên tố**:

~~~text
1000000000039
1000000000061
1000000000063
1000000000091
~~~

Chúng đều nằm trong khoảng [L,R], có thể được xác minh độc lập bằng phép thử nguyên tố phù hợp. Các giá trị khác trong khoảng là hợp số hoặc không phải nguyên tố.

Đây là một ví dụ cho thấy **giá trị đầu mút lớn không đồng nghĩa phải cấp phát bộ nhớ theo đầu mút**. Bộ nhớ cửa sổ chỉ là 32 phần tử, còn bộ nhớ chi phối là prime cơ sở tới 1 triệu.

### Không nên diễn giải quá mức kết quả này

Từ việc xử lý tốt \([10^{12},10^{12}+100]\) **không** suy ra xử lý tốt \([10^{18},10^{18}+100]\) bằng cùng một bản sàng. Với \(R\approx10^{18}\), căn R khoảng một tỷ, tạo toàn bộ base primes đã là một công việc nặng về bộ nhớ và thời gian.

Sàng phân đoạn **tối ưu hóa bộ nhớ theo độ rộng khoảng**, nhưng không xóa bỏ chi phí tạo prime cơ sở theo \(\sqrt R\).

## 10. Tính floor√R chính xác trên kiểu long

Nhiều chương trình viết:

~~~java
int root = (int) Math.sqrt((double) right);
~~~

Điều này có hai rủi ro:

1. `Math.sqrt` dùng `double`, có sai số làm tròn khi right là long rất lớn, nên kết quả cast xuống số nguyên có thể lệch gần điểm chính phương.
2. Căn của một giá trị long có thể **lớn hơn int tối đa**, làm phép cast int không còn phù hợp với ngân sách sàng.

Trong chương trình, ta dùng `Math.sqrt` để lấy **ước lượng ban đầu dạng long**, sau đó điều chỉnh bằng phép **chia nguyên**:

~~~java
static long floorSqrt(long value) {
    if (value < 0) {
        throw new IllegalArgumentException("negative square-root input");
    }
    if (value == 0) {
        return 0L;
    }

    long root = (long) Math.sqrt((double) value);
    while (root > value / root) {
        root--;
    }
    while (root + 1 <= value / (root + 1)) {
        root++;
    }
    return root;
}
~~~

Sau điều chỉnh:

\[
\boxed{root^2\le value<(root+1)^2.}
\]

Cách so `root<=value/root` tránh tính `root*root` khi bình phương có thể tràn. `root+1` an toàn vì căn của một số long không âm luôn chỉ khoảng 3,04 tỷ, nhỏ hơn `Long.MAX_VALUE` rất nhiều.

**Bản mã không cố sàng toàn bộ tới căn của mọi long**. Nó kiểm `root<=MAX_BASE_LIMIT` trước khi tạo mảng và danh sách prime; nếu vượt, báo lỗi rõ ràng.

## 11. Java 17+: sàng phân đoạn dùng long và block

Chương trình **SegmentedSieveDemo.java** dưới đây xử lý khoảng **[left,right] đóng**, lưu `long count` và một danh sách **sampleLimit số nguyên tố đầu tiên**. Nó không giữ toàn bộ số nguyên tố khi chỉ cần đếm.

Các giới hạn có chủ ý:

- `MAX_BASE_LIMIT=10_000_000` nghĩa là cần \(\lfloor\sqrt R\rfloor\le10^7\); giới hạn này đặt ra để ví dụ không tự cấp phát mảng base khổng lồ. Khi R lớn hơn khả năng đó, chương trình **từ chối có giải thích**, không trả sai.
- `1<=blockSize<=1_000_000`, giới hạn bộ nhớ mảng từng khối và tránh truyền một block quá lớn vào `new boolean[]`.
- `0<=sampleLimit<=1000`, chỉ lưu tối đa 1000 kết quả đầu tiên.
- Nếu `left>right`, báo lỗi. Nếu `right<2`, trả count=0.
- Dùng `long` cho L,R, mọi phép nhân p², chỉ số thực và bộ đếm.
- Bước sàng base chỉ chạy **một lần mỗi truy vấn**.
- Từng block đánh dấu từ \(\max(p^2,\lceil blockLow/p\rceil p)\), sử dụng phép dư để tính bội tiếp theo an toàn.
- Danh sách prime trả về chỉ là **K số đầu tiên**, không phải đầy đủ nếu có hơn K số trong khoảng.

Lưu thành tệp **SegmentedSieveDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SegmentedSieveDemo {
    static final int MAX_BASE_LIMIT = 10_000_000;
    static final int MAX_BLOCK_SIZE = 1_000_000;
    static final int MAX_SAMPLE_SIZE = 1_000;

    record Summary(long count, List<Long> firstPrimes) {}

    static long floorSqrt(long value) {
        if (value < 0) {
            throw new IllegalArgumentException(
                "negative square-root input"
            );
        }
        if (value == 0) {
            return 0L;
        }

        long root = (long) Math.sqrt((double) value);
        while (root > value / root) {
            root--;
        }
        while (root + 1 <= value / (root + 1)) {
            root++;
        }
        return root;
    }

    static List<Integer> basePrimes(int limit) {
        boolean[] composite = new boolean[limit + 1];

        for (int p = 2; (long) p * p <= limit; p++) {
            if (!composite[p]) {
                for (long multiple = (long) p * p;
                        multiple <= limit; multiple += p) {
                    composite[(int) multiple] = true;
                }
            }
        }

        List<Integer> primes = new ArrayList<>();
        for (int p = 2; p <= limit; p++) {
            if (!composite[p]) {
                primes.add(p);
            }
        }
        return primes;
    }

    static Summary segmentedSieve(
        long left, long right, int blockSize, int sampleLimit
    ) {
        if (left > right) {
            throw new IllegalArgumentException(
                "left must be <= right"
            );
        }
        if (blockSize < 1 || blockSize > MAX_BLOCK_SIZE) {
            throw new IllegalArgumentException(
                "block size out of bounds"
            );
        }
        if (sampleLimit < 0 || sampleLimit > MAX_SAMPLE_SIZE) {
            throw new IllegalArgumentException(
                "sample size out of bounds"
            );
        }
        if (right < 2) {
            return new Summary(0L, List.of());
        }

        long root = floorSqrt(right);
        if (root > MAX_BASE_LIMIT) {
            throw new IllegalArgumentException(
                "sqrt(R) exceeds configured base-sieve budget"
            );
        }
        List<Integer> primes = basePrimes((int) root);

        long count = 0L;
        List<Long> firstPrimes = new ArrayList<>();

        for (long blockLow = Math.max(2L, left);
                blockLow <= right;) {
            long blockHigh = blockLow
                + Math.min((long) blockSize - 1, right - blockLow);

            boolean[] composite =
                new boolean[(int) (blockHigh - blockLow + 1)];

            for (int p : primes) {
                long square = (long) p * p;
                if (square > blockHigh) {
                    break;
                }

                // Nearest multiple of p that is >= blockLow.
                long remainder = blockLow % p;
                long delta = remainder == 0 ? 0 : p - remainder;

                // No multiple of p inside this block.
                if (delta > blockHigh - blockLow) {
                    continue;
                }

                long firstMultiple = blockLow + delta;
                long first = Math.max(square, firstMultiple);

                // Mark composites without risking overflow on x += p.
                for (long x = first; x <= blockHigh;) {
                    composite[(int) (x - blockLow)] = true;
                    if (x > blockHigh - p) {
                        break;
                    }
                    x += p;
                }
            }

            // The surviving values >= 2 are primes.
            for (int offset = 0; offset < composite.length;
                    offset++) {
                if (!composite[offset]) {
                    long prime = blockLow + offset;
                    count++;
                    if (firstPrimes.size() < sampleLimit) {
                        firstPrimes.add(prime);
                    }
                }
            }

            if (blockHigh == right) {
                break;
            }
            blockLow = blockHigh + 1;
        }

        return new Summary(count, List.copyOf(firstPrimes));
    }

    static boolean isPrimeByTrial(long x) {
        if (x < 2) {
            return false;
        }
        for (long d = 2; d <= x / d; d++) {
            if (x % d == 0) {
                return false;
            }
        }
        return true;
    }

    // Independent small-range oracle, not using any sieve.
    static void verifySmallRanges() {
        int cases = 0;
        for (int left = -4; left <= 40; left++) {
            for (int right = left; right <= left + 8; right++) {
                List<Long> reference = new ArrayList<>();
                for (long x = left; x <= right; x++) {
                    if (isPrimeByTrial(x)) {
                        reference.add(x);
                    }
                }

                for (int block : new int[] {1, 3, 8}) {
                    Summary got =
                        segmentedSieve(left, right, block, 50);
                    if (got.count() != reference.size()
                            || !got.firstPrimes().equals(reference)) {
                        throw new AssertionError(
                            "mismatch at [" + left + "," + right
                            + "], block=" + block
                        );
                    }
                    cases++;
                }
            }
        }
        System.out.println(
            "Small-range brute checks: PASS (" + cases + " cases)"
        );
    }

    static void show(
        long left, long right, int blockSize, int sampleLimit
    ) {
        Summary result =
            segmentedSieve(left, right, blockSize, sampleLimit);
        System.out.println(
            "[" + left + "," + right + "] block=" + blockSize
            + " -> count=" + result.count()
            + ", first=" + result.firstPrimes()
        );
    }

    public static void main(String[] args) {
        show(1, 30, 16, 10);
        show(-10, 10, 4, 10);
        show(14, 16, 16, 10);
        show(17, 17, 8, 10);
        show(100, 150, 16, 5);

        // Huge endpoints, but a short interval and feasible sqrt(R).
        show(1_000_000_000_000L, 1_000_000_000_100L, 32, 10);

        show(0, 1, 8, 10);
        show(2, 2, 8, 10);
        show(2, 100, 8, 10);

        verifySmallRanges();

        try {
            segmentedSieve(20, 10, 8, 5);
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Invalid range rejected: " + e.getMessage()
            );
        }

        try {
            segmentedSieve(2, Long.MAX_VALUE, 16, 5);
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Root budget enforced: " + e.getMessage()
            );
        }

        try {
            segmentedSieve(2, 100, 0, 5);
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Invalid window rejected: " + e.getMessage()
            );
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 SegmentedSieveDemo.java
java SegmentedSieveDemo
~~~

**Stdout đúng với dữ liệu và giới hạn đã nêu:**

~~~text
[1,30] block=16 -> count=10, first=[2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
[-10,10] block=4 -> count=4, first=[2, 3, 5, 7]
[14,16] block=16 -> count=0, first=[]
[17,17] block=8 -> count=1, first=[17]
[100,150] block=16 -> count=10, first=[101, 103, 107, 109, 113]
[1000000000000,1000000000100] block=32 -> count=4, first=[1000000000039, 1000000000061, 1000000000063, 1000000000091]
[0,1] block=8 -> count=0, first=[]
[2,2] block=8 -> count=1, first=[2]
[2,100] block=8 -> count=25, first=[2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
Small-range brute checks: PASS (1215 cases)
Invalid range rejected: left must be <= right
Root budget enforced: sqrt(R) exceeds configured base-sieve budget
Invalid window rejected: block size out of bounds
~~~

### Phân tích kỹ các thành phần

**`basePrimes`:** tạo prime cơ sở từ 2 tới \(\lfloor\sqrt R\rfloor\). Mảng boolean có kích thước `limit+1`, chỉ tính theo **căn R**, không theo R. Vòng đánh dấu nội bộ bắt đầu từ `(long)p*p`.

**`floorSqrt`:** lấy ước lượng bằng `Math.sqrt`, rồi dùng phép chia nguyên để hiệu chỉnh chính xác. Hàm từ chối số âm; `segmentedSieve` chỉ gọi sau khi đã xác nhận R≥2.

**`MAX_BASE_LIMIT`:** là **giới hạn thực thi có chủ ý**. Nếu \(\sqrt R>10^7\), chương trình báo lỗi thay vì thử sàng một mảng cơ sở quá lớn. Giới hạn không phải tính chất toán học của sàng phân đoạn, và có thể điều chỉnh sau khi đánh giá tài nguyên.

**`blockLow/blockHigh`:** tạo cửa sổ đúng tối đa `blockSize` ứng viên, không vượt `right`. Kết quả `offset` được ánh xạ lại thành `blockLow+offset`.

**`remainder/delta`:** tìm bội p gần nhất không nhỏ hơn đầu block mà không dùng biểu thức `blockLow+p-1` có rủi ro tràn.

**`Math.max(square,firstMultiple)`:** bảo toàn p chính là số nguyên tố, không đánh dấu sai nó nếu p nằm trong block.

**`count`:** cộng một cho mỗi giá trị chưa bị gạch. Bộ đếm là `long`; nếu chỉ cần count mà không cần sample, truyền `sampleLimit=0` để không thêm phần tử vào danh sách.

**`verifySmallRanges`:** không dùng sàng để làm oracle; nó thử chia từng số nhỏ đến căn, đối chiếu toàn bộ danh sách với các block size 1,3,8 cho 1.215 cấu hình. Điều này đặc biệt quan trọng vì thuật toán phải không bị thay đổi kết quả khi đổi kích thước block.

## 12. Chứng minh tính đúng của segmented sieve

Chứng minh dựa trên ba bất biến.

### Bất biến A — Mọi số được đánh dấu là hợp số

Chương trình chỉ đánh dấu x khi x là bội của một prime p≥2 và:

\[
x\ge p^2.
\]

Vậy \(x=pq\) với \(q\ge p\ge2\). Suy ra x có hai thừa số dương khác 1 và chính nó; x là **hợp số**.

Ngoài ra khối chỉ bắt đầu từ \(\max(2,L)\), nên các số 0,1, số âm không được đưa vào danh sách đầu ra.

### Bất biến B — Mọi hợp số trong [L,R] đều bị đánh dấu

Lấy một hợp số x thuộc khoảng và x≥2. Theo định lý ở phần 3, x có ước nguyên tố p≤√x≤√R. Prime p này chắc chắn nằm trong danh sách prime cơ sở.

Khi xử lý block chứa x, ta duyệt p. Vì x là hợp số có ước p, x là bội của p. Đồng thời, nếu p là ước nguyên tố nhỏ nhất của x, có x≥p²; thuật toán bắt đầu đánh dấu từ:

\[
\max(p^2,\lceil blockLow/p\rceil p).
\]

Giá trị này không vượt x, nên vòng bước p sẽ đi qua x và gạch nó. Do đó **không có hợp số x nào còn lại chưa đánh dấu**.

### Bất biến C — Mỗi ứng viên được xét đúng một lần

Các block liên tiếp rời nhau và phủ hết đoạn từ max(2,L) tới R; với mỗi block, các vị trí mảng tương ứng một-một với giá trị thực `blockLow+offset`. Bởi vậy mỗi số ≥2 trong khoảng được kiểm đúng một lần ở bước thu thập kết quả.

Từ A, B và C:

- Số chưa bị gạch, nếu ≥2, chắc chắn nguyên tố.
- Mọi số nguyên tố trong khoảng không bị gạch.
- Không số nào được đếm hai lần.

Vì thế kết quả count và danh sách mẫu đầu đúng theo hợp đồng.

### Vì sao thay đổi blockSize không thay đổi đáp án?

Một số x luôn nằm trong **đúng một block**, bất kể chia block thế nào. Các prime cơ sở vẫn là tập p≤√R. Công thức xác định bội đầu tiên trong block chỉ thay điểm bắt đầu của phép đánh dấu, **không thay tập bội thuộc block**. Do đó mọi x được quyết định nguyên tố/hợp số như nhau.

Block size chỉ ảnh hưởng **chi phí và thứ tự xử lý theo cụm**, không ảnh hưởng kết quả.

## 13. Độ phức tạp thời gian và bộ nhớ

Đặt:

- \(S=\lfloor\sqrt R\rfloor\), với R≥2.
- \(U=R-\max(2,L)+1\), số ứng viên thật sự từ 2 trở lên trong khoảng (nếu R<2 thì U=0).
- B là kích thước cửa sổ.
- \(\pi(S)\) là số lượng số nguyên tố không vượt S.
- K là giới hạn số phần tử mẫu đầu giữ lại.

**Sàng prime cơ sở:**

\[
O(S\log\log S)\text{ thời gian},\qquad O(S)\text{ bộ nhớ}.
\]

**Tạo và quét các cửa sổ:** tổng số vị trí trong các block là U; khởi tạo mảng và đọc lại ứng viên dùng O(U). Với mỗi prime p, tổng số bội cần gạch trong toàn khoảng xấp xỉ U/p, nên tổng đánh dấu gần:

\[
O\!\left(U\sum_{p\le S}\frac1p\right)
=O(U\log\log S).
\]

Nhưng mã demo **lặp qua danh sách prime cơ sở cho từng block**; mỗi block có chi phí xét các prime trước khi đánh dấu bội. Số block xấp xỉ \(\lceil U/B\rceil\), nên cần kể thêm chi phí:

\[
O\!\left(\left\lceil\frac UB\right\rceil\pi(S)\right).
\]

Một cận mô tả phù hợp cho cách triển khai này là:

\[
\boxed{
O\!\left(
S\log\log S+
U\log\log S+
\left\lceil\frac UB\right\rceil\pi(S)
\right)
}
\]

khi U>0, bỏ qua các hằng số và giả định phép toán trên long là O(1).

Bộ nhớ:

\[
\boxed{O(S+B+K).}
\]

Gồm mảng sàng cơ sở và danh sách prime (đều bị chặn bởi O(S)), mảng đánh dấu một block O(B) và K số nguyên tố mẫu. Nếu cần lưu **mọi** số nguyên tố trong khoảng, thêm O(P) với P là số lượng kết quả; khi chỉ đếm thì K=0.

### Vì sao block quá nhỏ đôi khi chậm?

Mỗi block, chương trình lại phải duyệt các prime cơ sở tới căn của blockHigh, kể cả khi block chỉ có một vài số. Nếu B=1 mà U lớn, overhead số lượt duyệt prime có thể chi phối. Tăng B giúp giảm số block và tăng tính cục bộ bộ nhớ, nhưng B quá lớn làm tốn RAM/cache.

Một số cỡ thử nghiệm thường là vài chục nghìn tới vài triệu phần tử, tùy môi trường và cách dùng `boolean[]`, `byte[]`, bitset. Bài đặt ngưỡng tối đa một triệu để mã an toàn hơn; **không có một B tối ưu chung cho mọi máy**.

### Bộ nhớ prime cơ sở đôi khi là chi phí chính

Nếu R≈\(10^{12}\) và U chỉ 101, sàng prime cơ sở tới S=1.000.000 có thể tốn nhiều thời gian hơn việc đánh dấu 101 ứng viên. Khi chỉ hỏi **một vài số rời rạc**, phép thử nguyên tố tốt có thể hợp lý hơn.

Sàng phân đoạn đặc biệt có lợi khi **nhiều ứng viên liền nhau** cần phân loại hoặc khi có thể **tái sử dụng danh sách prime cơ sở** cho nhiều khoảng.

## 14. Tối ưu thực tế khi xử lý nhiều khoảng

### Nhiều truy vấn cùng giới hạn R tối đa

Nếu có Q khoảng \([L_i,R_i]\), tính:

\[
R_{\max}=\max_i R_i.
\]

Sau đó tạo **một lần** các prime cơ sở tới \(\lfloor\sqrt{R_{\max}}\rfloor\), rồi dùng lại cho mọi khoảng. Như vậy tránh lặp chi phí sàng cơ sở Q lần.

Khi một khối có blockHigh nhỏ hơn Rmax, có thể bỏ qua prime p khi `p*p>blockHigh`. Mã demo chưa thiết kế API cache vì muốn đơn giản, nhưng việc chuyển `basePrimes` thành dữ liệu dùng chung khá trực tiếp.

### Chỉ sàng số lẻ

Ngoài 2, mọi số nguyên tố đều là số lẻ. Có thể:

1. Xử lý số 2 riêng nếu nằm trong khoảng.
2. Lưu và đánh dấu chỉ các số lẻ.
3. Khi p lẻ, đánh dấu các bội lẻ bằng bước \(2p\).

Điều này gần như giảm một nửa mảng ứng viên và số lượt ghi, nhưng làm công thức ánh xạ offset phức tạp hơn. Đừng tối ưu sớm nếu phiên bản chứa cả chẵn/lẻ chưa được kiểm chính xác.

### Dùng bitset thay boolean[]

`boolean[]` dễ hiểu và có chi phí một phần tử không nhất thiết là một bit. Bitset nén các trạng thái đánh dấu xuống mật độ theo bit, có thể tiết kiệm RAM và cải thiện cache, nhưng cần thao tác bit đúng và có thể có overhead CPU. Với mục tiêu học thuật toán, mảng boolean là điểm bắt đầu tốt.

### Phân khối song song

Các block có thể được xử lý độc lập khi danh sách prime cơ sở đã tạo xong. Tuy nhiên:

- Mỗi worker phải có mảng đánh dấu riêng.
- Tổng count phải cộng bằng kiểu số đủ lớn.
- Nếu muốn danh sách prime **tăng dần**, kết quả các block phải được ghép theo thứ tự block.
- Tránh tạo quá nhiều block/task rất nhỏ vì chi phí điều phối có thể lớn hơn lợi ích.

Parallelization là một cải tiến triển khai; không thay đổi lập luận đúng đắn của phép đánh dấu.

## 15. Khi R quá lớn so với khả năng sàng prime cơ sở

Sàng phân đoạn giải quyết **vấn đề mảng theo R** nhưng vẫn còn vấn đề **mảng/danh sách theo √R**.

Nếu \(R=10^{18}\):

\[
\sqrt R=10^9.
\]

Sàng và giữ toàn bộ prime cơ sở tới một tỷ là công việc nặng, có thể không phù hợp với ngân sách bộ nhớ, dù khoảng \([R-100,R]\) chỉ có 101 số.

### Lựa chọn phù hợp hơn trong trường hợp khác

**1. Kiểm tra từng số bằng Miller–Rabin.** Với số lượng ứng viên ít và số rất lớn, một phép thử nguyên tố nhanh dùng **lũy thừa modulo** có thể phù hợp hơn. Với miền **64-bit**, có các bộ cơ sở Miller–Rabin đã được chứng minh quyết định đúng cho mọi số trong miền được nêu, nhưng phải dùng **đúng bộ cơ sở và đúng phép nhân modulo**.

Điểm khó: khi a,b gần \(10^{18}\), `a*b` có thể tràn `long` trước khi lấy modulo. Không được viết `(a*b)%mod` rồi khẳng định bản Miller–Rabin là đúng. Cần nhân modulo chống tràn (ví dụ `BigInteger`, nhân theo phép cộng/doubling có kiểm soát, hoặc kỹ thuật rộng kiểu số).

**2. Sàng prime cơ sở theo nhiều tầng hoặc lưu ngoại vi.** Nếu vẫn cần xử lý một khoảng rộng ở R lớn, có thể tối ưu cách tạo và dùng prime cơ sở, dùng biểu diễn nén hoặc xử lý theo tệp. Nhưng **chi phí theo √R vẫn tồn tại** trong mô hình sàng cổ điển.

**3. Bài toán đếm prime đến N (\(\pi(N)\)).** Nếu cần **số lượng** prime không vượt một N rất lớn, các thuật toán prime counting chuyên biệt có thể tốt hơn việc liệt kê từng prime. Đây là bài khác với xuất từng số nguyên tố trong [L,R].

**4. Nhiều phép kiểm tra nguyên tố độc lập.** Nếu chỉ kiểm vài số, không cần dựng toàn bộ danh sách prime cơ sở. Ngược lại, nếu cần phân loại hàng triệu số liên tiếp, segmented sieve thường có lợi.

### Tránh hứa hẹn “hỗ trợ mọi long”

Bản Java demo **cố ý từ chối** trường hợp \(\sqrt R>10^7\). Đây là hành vi được dự tính trước, **không phải thuật toán bí mật xử lý sai số lớn**. Nếu bỏ guard mà tăng mảng tới hàng tỷ phần tử, chương trình có thể hết bộ nhớ hoặc rất chậm.

Một thư viện thực tế nên **định rõ ngân sách thời gian/bộ nhớ**, số truy vấn, độ rộng tối đa và nhu cầu xuất kết quả trước khi chọn chiến lược.

## 16. Các trường hợp biên phải kiểm

| Trường hợp | Kết quả hoặc cách xử lý |
|---|---|
| \([0,1]\) | Không có prime ⇒ 0 |
| \([-10,10]\) | [2,3,5,7], count 4 |
| \([2,2]\) | Prime 2, count 1 |
| \([1,2]\) | Chỉ prime 2 |
| \([14,16]\) | Không có prime |
| \([17,17]\) | Một prime 17 |
| \([4,4]\) | Hợp số, count 0 |
| \([49,49]\) | Hợp số 7×7, count 0; kiểm có prime 7 trong base |
| \([10,30]\) | 11,13,17,19,23,29 ⇒ 6 |
| \([1,30]\) | 10 prime |
| \([100,150]\) | 10 prime |
| \([10^{12},10^{12}+100]\) | 4 prime, danh sách ở phần 9 |
| `L>R` | Báo lỗi, không tự hoán đổi |
| `R<2` | Trả count 0 |
| `blockSize=1` | Đúng nhưng có thể chậm |
| `blockSize<=0` | Báo lỗi |
| `sampleLimit=0` | Vẫn đếm, không lưu mẫu |
| `sampleLimit<0` | Báo lỗi |
| \(\sqrt R\) vượt ngân sách cấu hình | Báo lỗi, không cố cấp phát |
| Khoảng có R rất lớn gần Long.MAX | Cần thuật toán/nguồn lực khác trong bản demo |
| Nhiều block, prime nằm đúng ở ranh giới | Mỗi số phải được xét đúng một lần |

### Prime chính phương và nhầm giới hạn căn

Với số `49=7*7`, nếu sàng prime cơ sở chỉ tới 6 sẽ không có p=7 để gạch 49. Dùng \(\lfloor\sqrt{49}\rfloor=7\) và **so sánh p²<=blockHigh** chính xác.

Nếu do sai số `Math.sqrt` mà root bị tính thiếu 1 tại một số chính phương lớn, kết quả có thể chứa một hợp số giả. Vì thế helper `floorSqrt` cần điều chỉnh kết quả double bằng chia nguyên.

### Biên block và chỉ số

Giả sử blockLow=18, blockHigh=33. Mảng có:

\[
33-18+1=16
\]

phần tử, chỉ số từ 0 đến 15. Số 18 ở chỉ số 0, số 33 ở chỉ số 15. Nếu dùng `new boolean[high-low]` sẽ bỏ mất đầu mút phải của khoảng **đóng**.

Nếu khối sau bắt đầu ở blockHigh thay vì blockHigh+1, số ở biên bị đếm hai lần. Nếu bắt đầu ở blockHigh+2, bỏ mất một số. Hãy test với blockSize 1,2,3 để phát hiện.

## 17. Sai lầm phổ biến

1. **Sàng toàn bộ từ 0 tới R** khi R hàng nghìn tỷ, gây hết RAM.
2. **Dùng tất cả số đến R** làm base prime, trong khi chỉ cần tới \(\sqrt R\).
3. **Dùng \(\sqrt L\) thay \(\sqrt R\)** và bỏ sót một prime factor của hợp số gần R.
4. **Không lấy max với p²**, vô tình gạch chính số nguyên tố p.
5. **Bắt đầu từ p² rồi tăng dần tới L**, khiến thời gian phụ thuộc cực lớn vào giá trị L.
6. **Tính ceilDiv bằng `(L+p-1)/p` với long không kiểm tràn**.
7. **Tính `long square=p*p` khi p là int**, gây tràn trong phép nhân int.
8. **Tính blockHigh bằng phép cộng có thể tràn**, sau đó mới gọi Math.min.
9. **Tăng số bội bằng x+=p sau khi x đã gần Long.MAX_VALUE** mà không chặn.
10. **Trộn [L,R] đóng với [L,R) nửa mở**, bỏ sót R hoặc đếm thừa.
11. **Dùng `offset=x` thay vì `offset=x-blockLow`**, truy cập mảng vượt phạm vi.
12. **Không lọc 0 và 1**, trả về các giá trị không phải prime.
13. **Quên số âm không phải prime**, khởi tạo sai mảng nếu L âm.
14. **Sàng lại prime cơ sở ở mỗi block**, lãng phí lớn.
15. **Chỉ tạo prime cơ sở tới sqrt(blockLow)**, có thể thiếu ước của số ở cuối block.
16. **Reset toàn bộ count cho mỗi block**, chỉ giữ kết quả của block cuối.
17. **Không cộng count bằng kiểu đủ rộng**, có thể tràn int ở khoảng lớn.
18. **Lưu tất cả prime khi chỉ cần đếm**, gây áp lực bộ nhớ.
19. **Dùng block cực nhỏ** nhưng không tính overhead duyệt prime cơ sở cho mỗi block.
20. **Tự tin rằng segmented sieve chạy nhanh cho mọi R kiểu long**, bỏ qua bài toán sinh prime đến sqrt(R).
21. **Dùng Math.sqrt(double) rồi ép int trực tiếp**, có thể sai căn ở biên chính phương hoặc vượt miền int.
22. **Bỏ qua p²<=blockHigh** nhưng vẫn đánh dấu bằng công thức sai.
23. **Nhầm “sàng số nguyên tố trong khoảng” với “đếm số số nguyên tố ≤R”**, dẫn tới lựa chọn thuật toán không phù hợp.
24. **Không làm sạch mảng composite khi đổi block**, khiến dấu cũ làm biến mất prime ở block mới.
25. **Dùng số lượng sample thay cho tổng count**, trong khi sample có thể bị cắt ở K.
26. **Quên xử lý block cuối ngắn hơn B**, gây truy cập/đếm vượt R.
27. **Không so sánh với oracle thử chia trên khoảng nhỏ**, khó phát hiện sai lệch một đơn vị.
28. **Không kiểm các trường hợp blockSize=1 và prime ở biên**, dễ bỏ sót/đếm hai lần.
29. **Cho rằng kết quả prime trong nhiều block tự luôn tăng dần khi chạy song song**, nếu thu kết quả theo thứ tự task hoàn thành sẽ bị đảo.
30. **Triển khai Miller–Rabin 64-bit bằng nhân long thông thường rồi lấy modulo**, có thể sai vì tràn số.

## 18. Kiểm thử độc lập và chiến lược QA

Thuật toán sàng phân đoạn có nhiều phép biến đổi chỉ số và cận, nên không đủ chỉ nhìn một ví dụ [10,30]. Một chiến lược tốt là **đối chiếu với oracle thử chia trực tiếp** trên các giá trị nhỏ.

### Oracle không dùng sàng

~~~text
isPrimeByTrial(x):
    if x < 2:
        return false
    for d from 2 while d <= x/d:
        if x % d == 0:
            return false
    return true
~~~

Cách dùng `d<=x/d` tránh tính `d*d` nếu d lớn, và chỉ dành làm oracle trên số nhỏ. Với x cỡ \(10^{12}\), thử chia ngây thơ mọi d tới một triệu có thể tốn nhiều thời gian; nên dùng kiểm tra khác khi xác minh ví dụ lớn.

### Các thuộc tính cần thử

1. `sieve(L,R)` trả mọi giá trị **nằm trong [L,R]**.
2. Mọi giá trị trả ra **≥2**.
3. Danh sách kết quả phải **tăng nghiêm ngặt**, không trùng giữa hai block.
4. Với interval nhỏ, danh sách đầy đủ bằng danh sách oracle thử chia.
5. `count` bằng số phần tử oracle, **kể cả khi sampleLimit=0**.
6. Nếu `sampleLimit>=count`, sample phải chứa **đầy đủ** mọi prime trong khoảng.
7. Với sampleLimit nhỏ, sample phải bằng **K số đầu của danh sách oracle**, nhưng count vẫn là count thật.
8. Đổi `blockSize=1,2,3,7,16,...` không đổi prime/count.
9. Ghép kết quả của \([L,M]\) và \([M+1,R]\) phải cho cùng số lượng với \([L,R]\).
10. Test biên \(R=p^2\), đặc biệt 4,9,25,49,121.
11. Test L<2, R<2, L=R, L>R.
12. Test một khoảng lớn về **giá trị số** nhưng **hẹp về độ rộng**.
13. Test giới hạn căn R bị vượt: chương trình phải **từ chối rõ ràng**, không cố cấp phát.
14. Test `blockSize=0` hoặc quá ngưỡng: phải báo lỗi.
15. Test `firstMultiple` trong block nằm ngay đầu hoặc cuối block.
16. Test `p*p` trước và sau đầu block để bảo đảm không gạch chính p.
17. Test liên tục các block mà không sàng lại prime cơ sở.
18. Test khi count lớn hơn sampleLimit, tránh nhầm hai giá trị.

### Kết quả tham chiếu

| Khoảng [L,R] | Các prime hoặc số lượng |
|---|---|
| [0,1] | 0 prime |
| [-10,10] | 2,3,5,7 |
| [2,2] | 2 |
| [4,4] | 0 prime |
| [14,16] | 0 prime |
| [17,17] | 17 |
| [1,30] | 2,3,5,7,11,13,17,19,23,29 |
| [100,150] | 101,103,107,109,113,127,131,137,139,149 |
| [1000000000000,1000000000100] | 1000000000039,1000000000061,1000000000063,1000000000091 |

Trong Java demo, `verifySmallRanges` thử các khoảng nhỏ từ left=-4 đến 40, với các right từ left tới left+8 và blockSize thuộc `{1,3,8}`. Tổng:

\[
45\cdot9\cdot3=\boxed{1215\text{ cấu hình}}.
\]

Mỗi kết quả được đối chiếu với danh sách nguyên tố do phép thử chia trực tiếp, nên đây là **kiểm chứng độc lập** với thuật toán đánh dấu sàng.

## 19. Câu hỏi và bài tập tự luyện

**Bài 1 — Phân biệt miền.** Khoảng [10,30] có bao nhiêu số nguyên tố?

*Đáp án:* **6**: 11,13,17,19,23,29.

**Bài 2 — Dưới 2.** Khoảng [-10,10] có những số nguyên tố nào?

*Đáp án:* **2,3,5,7**; 0,1 và số âm không nguyên tố.

**Bài 3 — Prime cơ sở.** Với R=10.000, cần sàng prime cơ sở tới đâu?

*Đáp án:* \(\lfloor\sqrt{10000}\rfloor=100\).

**Bài 4 — Prime nhỏ nhất.** Với [L,R]=[2,10] và p=2, bội đầu tiên phải gạch là bao nhiêu?

*Đáp án:* **4**, không phải 2, vì 2 chính là số nguyên tố.

**Bài 5 — Bình phương.** Với [10,30], p=5, vì sao bắt đầu gạch từ 25?

*Đáp án:* Bội đầu của 5 ≥10 là 10 nhưng p²=25; dùng max(25,10)=25.

**Bài 6 — Bội từ block.** Với blockLow=28 và p=3, bội đầu không nhỏ hơn blockLow là bao nhiêu?

*Đáp án:* **30**, vì 28%3=1, delta=3−1=2, nên firstMultiple=28+2=30.

**Bài 7 — Block cuối.** Khoảng [2,40] dùng blockSize=16 được chia thế nào?

*Đáp án:* **[2,17], [18,33], [34,40]**.

**Bài 8 — Ánh xạ.** Nếu blockLow=1000, số 1017 nằm ở chỉ số nào của boolean[]?

*Đáp án:* **17**, bằng 1017−1000.

**Bài 9 — Số prime rỗng.** [14,16] có prime nào không?

*Đáp án:* **Không**, count=0.

**Bài 10 — Một phần tử.** [17,17] có bao nhiêu prime?

*Đáp án:* **1**.

**Bài 11 — Chính phương.** Vì sao cần prime 7 để sàng đúng [49,49]?

*Đáp án:* 49=7²; nếu thiếu 7, có thể nhầm 49 là prime.

**Bài 12 — sqrt overflow.** Vì sao tránh `long square=p*p` khi p là int?

*Đáp án:* Phép nhân diễn ra ở kiểu **int trước khi gán**, nên có thể tràn; dùng `(long)p*p`.

**Bài 13 — R rất lớn.** Có thể dùng `new boolean[(int)(R+1)]` với R=\(10^{12}\) không?

*Đáp án:* Không; mảng theo toàn bộ R quá lớn, ép int còn có thể tràn.

**Bài 14 — Count và sample.** K=5 nhưng khoảng có 100 prime. `count` trả gì?

*Đáp án:* **100**, còn danh sách `firstPrimes` chỉ chứa 5 prime đầu.

**Bài 15 — Sàng base nhiều truy vấn.** Có nên sàng prime cơ sở lại ở mỗi block không?

*Đáp án:* **Không**. Dùng lại prime cơ sở đã sàng tới \(\sqrt R\).

**Bài 16 — Cận bộ nhớ.** Với căn R là S, cửa sổ B, sample K, bộ nhớ phụ là gì?

*Đáp án:* **O(S+B+K)** cho phiên bản có lưu prime cơ sở và sample.

**Bài 17 — Khi nào Miller–Rabin thích hợp?** Nếu chỉ kiểm tra 10 số gần \(10^{18}\), nên cân nhắc gì?

*Đáp án:* Một phép thử nguyên tố 64-bit có thiết kế chắc chắn như **Miller–Rabin**, vì sàng toàn bộ prime cơ sở tới \(10^9\) thường quá tốn kém.

**Bài 18 — Long.MAX.** Vì sao `(L+p-1)/p` là công thức dễ tràn?

*Đáp án:* `L+p-1` có thể lớn hơn `Long.MAX_VALUE` trước phép chia.

**Bài 19 — Chia nhiều block.** Nếu chia một khoảng thành nhiều block, có thay đổi tập prime không?

*Đáp án:* **Không**. Mỗi số xuất hiện trong đúng một block và được đánh dấu theo cùng tập prime factor cơ sở.

**Bài 20 — Giới hạn sqrt.** Khi \(\sqrt R>MAX_BASE_LIMIT\), Java demo trả gì?

*Đáp án:* Ném `IllegalArgumentException` với thông báo giới hạn sàng base, **không** cố chạy và không trả một danh sách prime thiếu.

**Bài 21 — Tìm khác biệt.** Sàng Eratosthenes thường và segmented sieve khác nhau chính ở đâu?

*Đáp án:* Sàng thường duy trì mảng tới N, còn segmented sieve sàng prime cơ sở tới √R rồi dùng **mảng cục bộ trên các block của [L,R]**.

**Bài 22 — Đếm toàn bộ.** Nếu chỉ muốn đếm prime trong [L,R], có cần giữ toàn bộ prime trong List không?

*Đáp án:* **Không**. Chỉ tăng biến count cho mỗi vị trí chưa gạch, giảm bộ nhớ kết quả.

**Tổng kết:** **Sàng phân đoạn** tìm các số nguyên tố trong khoảng đóng **[L,R]** bằng cách sàng **prime cơ sở đến \(\lfloor\sqrt R\rfloor\)** rồi đánh dấu hợp số chỉ trong các **cửa sổ** của khoảng. Với prime p và block \([A,B]\) (A≥2), bội đầu cần gạch là **\(\max(p^2,\lceil A/p\rceil p)\)**; bắt đầu sớm hơn có thể gạch nhầm p, bắt đầu quá muộn sẽ bỏ sót hợp số. Dùng chỉ số cục bộ `x-blockLow`, cập nhật biên an toàn với `long`, loại mọi giá trị <2, sàng base chỉ một lần và đếm mà không lưu toàn bộ kết quả. Bộ nhớ của bản cửa sổ là **O(\(\sqrt R\)+B+K)** thay vì O(R), nhưng **chi phí prime cơ sở theo \(\sqrt R\) vẫn tồn tại**: đối với R cực lớn và khoảng hẹp, một phép thử nguyên tố 64-bit như Miller–Rabin có thể thích hợp hơn.
