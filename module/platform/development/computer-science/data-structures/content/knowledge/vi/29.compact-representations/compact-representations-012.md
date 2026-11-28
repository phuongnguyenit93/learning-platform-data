# Phân biệt cấu trúc dữ liệu gọn với chỉ nén toàn bộ dữ liệu thành một khối

Khi lưu hàng triệu phần tử, ta thường muốn **nén dữ liệu để giảm dung lượng**. Tuy nhiên, có hai câu hỏi rất khác nhau: (1) làm thế nào để lưu một tập dữ liệu bằng ít byte nhất và (2) làm thế nào để **vừa tiết kiệm bộ nhớ, vừa tìm kiếm, đếm, lấy phần tử, duyệt hoặc điều hướng dữ liệu trực tiếp** mà không phải giải nén tất cả trước mỗi truy vấn?

Câu hỏi thứ hai dẫn đến **cấu trúc dữ liệu gọn** (*compact data structures*) và **cấu trúc dữ liệu súc tích** (*succinct data structures*). Trong chương **Biểu diễn gọn**, ta xem các biểu diễn này dưới góc nhìn của môn cấu trúc dữ liệu: **bất biến**, **phép toán**, **độ phức tạp thời gian**, **dung lượng bộ nhớ** và đôi khi cả **số lần đọc/ghi khối I/O**. Một tệp nén rất nhỏ chưa chắc phù hợp cho hệ thống phải trả lời hàng nghìn truy vấn ngẫu nhiên mỗi giây.

**Ý chính:** Nén tối ưu hóa cách mã hóa thông tin. Cấu trúc dữ liệu gọn tối ưu **cách lưu thông tin cùng các phép toán cần thực hiện trên nó**. Hai hướng có thể kết hợp với nhau; khác biệt nằm ở chức năng và chi phí truy vấn mà từng thiết kế thực sự bảo đảm.

## 1. Hai phương án lưu cùng một tập dữ liệu

Giả sử hệ thống có một triệu sự kiện, sắp theo thời gian. Ứng dụng cần lấy sự kiện thứ i, tìm sự kiện trong một khoảng thời gian và đếm số sự kiện thỏa điều kiện.

**Phương án A: một luồng nén tuần tự, không có chỉ mục.**

~~~text
 Bản ghi gốc
 [event0][event1][event2] ... [event999999]
                     |
                bộ nén tổng quát
                     v
           [một khối byte đã nén]
                     |
                  giải mã
                     v
          dữ liệu có thể truy cập
~~~

Nếu định dạng chỉ hỗ trợ giải mã theo thứ tự từ đầu luồng, để đọc sự kiện thứ i, hệ thống có thể phải giải mã nhiều phần tử trước đó. Phương án này hợp lý với sao lưu, truyền dữ liệu hoặc tác vụ đọc toàn bộ tệp.

**Phương án B: biểu diễn gọn có chỉ mục và giao diện truy vấn.**

~~~text
 [payload mã hóa gọn] [bitvector / index] [metadata]
             \             |            /
              \____________|___________/
                           |
             ACCESS(i), GET(k), RANK, SELECT
                           |
             truy cập / giải mã vùng cần thiết
~~~

Đổi lại một phần không gian cho **chỉ mục**, hệ thống có thể tìm vị trí hoặc giá trị cần đọc ngay trên biểu diễn. Phương án B **không nhất thiết nhỏ hơn** phương án A về byte. Nó được thiết kế để giảm tổng chi phí của những thao tác quan trọng.

Không phải định dạng nén nào cũng buộc giải nén toàn bộ: nén theo **block độc lập** kèm bảng offset, seek table hoặc chỉ mục cũng cho phép truy cập một phần. Khi bổ sung những cơ chế đó, định dạng nén có chức năng gần hơn với cấu trúc dữ liệu đã lập chỉ mục. Vì thế không thể phân loại chỉ dựa vào phần mở rộng tệp hoặc việc có sử dụng bộ mã nén hay không.

## 2. Compact, compression và succinct không đồng nghĩa

| Khái niệm | Mục tiêu | Đặc trưng | Hạn chế cần xét |
|---|---|---|---|
| **Compression – nén** | Giảm số bit cần lưu hoặc truyền để khôi phục nội dung. | Áp dụng bộ mã như từ điển, mã biến độ dài, mã theo entropy. | Truy cập ngẫu nhiên có thể tốn giải mã nếu thiếu cấu trúc hỗ trợ. |
| **Compact data structure – cấu trúc gọn** | Sử dụng ít bộ nhớ nhưng vẫn phục vụ các thao tác định nghĩa trước. | Đóng gói bit, thay con trỏ bằng chỉ số, lưu chỉ mục truy cập. | Không nhất thiết đạt cận dung lượng tối ưu theo lý thuyết. |
| **Succinct data structure – cấu trúc súc tích** | Tiệm cận **cận dưới thông tin** của đối tượng với cận thời gian truy vấn xác định. | Có thể dùng dạng \(L(n)+o(L(n))\) bit cùng chỉ mục để hỗ trợ phép toán. | Phát biểu phải ghi rõ đối tượng, mô hình máy và tập phép toán. |

**Cận dưới thông tin** là số bit cần để phân biệt các trạng thái hợp lệ. Với một bitvector dài n, có \(2^n\) trạng thái, nên cần ít nhất **n bit** trong trường hợp xấu nếu không có giả thiết bổ sung. Nếu biết chính xác có m bit 1, chỉ còn \(\binom{n}{m}\) trạng thái, nên cận dưới trở thành:

\[
L(n,m)=\left\lceil\log_2\binom{n}{m}\right\rceil\ \text{bit}.
\]

Khi m rất nhỏ so với n, con số này có thể nhỏ hơn n nhiều. Một bitvector mã hóa gọn cho tập thưa có thể tận dụng đặc điểm đó.

Ký hiệu **\(o(n)\)** trong \(n+o(n)\) bit chỉ phần phụ trội có tỷ lệ so với n tiến dần về 0 khi n tăng. Nó **không** có nghĩa cấu trúc không cần chỉ mục hoặc metadata. Một index thực dụng dùng thêm 5% dung lượng vẫn có thể rất tốt, dù chưa đạt điều kiện phụ trội \(o(n)\) theo định nghĩa tiệm cận.

## 3. Giao diện thao tác quan trọng hơn tên bộ mã

Trước khi thiết kế, cần biết người dùng sẽ hỏi gì:

| Phép toán | Ý nghĩa | Với một luồng nén tuần tự không chỉ mục | Với cấu trúc gọn được thiết kế phù hợp |
|---|---|---|---|
| **ACCESS(i)** | Lấy phần tử tại vị trí i. | Có thể giải mã từ đầu tới i. | Xác định vị trí hoặc giải mã một block nhỏ. |
| **GET(k)** | Tìm giá trị theo khóa. | Có thể phải quét nhiều bản ghi đã giải mã. | Dùng chỉ mục hoặc thứ tự của dữ liệu để thu hẹp tìm kiếm. |
| **RANK1(i)** | Đếm bit 1 trong i vị trí đầu. | Thường phải giải mã và đếm phần đầu. | Bitvector có index rank hỗ trợ nhanh. |
| **SELECT1(k)** | Tìm vị trí bit 1 thứ k. | Thường phải dò và đếm tới bit thứ k. | Dùng index select để xác định vị trí. |
| **RANGE(lo, hi)** | Duyệt các phần tử trong khoảng. | Có thể phải giải mã cả dữ liệu ngoài khoảng. | Có thể tìm điểm bắt đầu và duyệt vùng cần thiết. |
| **INSERT/DELETE** | Chèn, xóa, cập nhật. | Có thể phải tạo lại phần lớn khối nén. | Tùy cấu trúc: nhiều cấu trúc tĩnh cập nhật đắt; có các biến thể động. |

**Không cấu trúc gọn nào mặc nhiên hỗ trợ toàn bộ các phép toán.** Cấu trúc tối ưu cho ACCESS có thể chưa hỗ trợ SELECT; chỉ mục dành cho GET cũng không tự động tối ưu quét khoảng. Phải so sánh các phương án dưới cùng một **hợp đồng thao tác** và cùng yêu cầu độ trễ.

## 4. Bitvector: lưu một bit khác với truy vấn trên bit

Cho bitvector:

~~~text
Vị trí (đếm từ 1):  1  2  3  4  5  6  7  8  9 10
Bit:                1  0  1  1  0  0  1  0  1  1
~~~

Định nghĩa:

- **rank1(i)** là số bit 1 trong **i vị trí đầu tiên**; rank1(0) = 0.
- **select1(k)** là vị trí (đếm từ 1) của **bit 1 thứ k** khi đi từ trái sang phải; chỉ xác định với \(1\le k\le \operatorname{rank}_1(n)\).

Với ví dụ:

\[
\operatorname{rank}_1(7)=4,\quad
\operatorname{select}_1(4)=7,\quad
\operatorname{select}_1(6)=10.
\]

Các phép toán này có thể ghép lại để trả lời câu hỏi trên tập vị trí S = {1, 3, 4, 7, 9, 10}:

| Câu hỏi | Biểu thức | Kết quả |
|---|---|---|
| Vị trí 6 có thuộc S không? | ACCESS(6) | Không |
| Có bao nhiêu phần tử S không vượt quá 7? | rank1(7) | 4 |
| Phần tử nhỏ thứ 4 của S? | select1(4) | 7 |
| Có bao nhiêu phần tử S thuộc [4,9]? | rank1(9) − rank1(3) | 3 |
| Phần tử tiếp theo của S sau 6? | select1(rank1(6) + 1) | 7 |

Trong phép tìm phần tử tiếp theo, phải kiểm tra rank1(6) + 1 không vượt tổng số bit 1. Các công thức đơn giản này cho thấy **một biểu diễn bit có thể phục vụ nhiều thao tác trực tiếp**.

### 4.1. Đóng gói bit mới giải quyết dung lượng

Nếu lưu **1.000.000** giá trị Boolean bằng một byte mỗi giá trị, payload chiếm **1.000.000 byte**. Đóng gói 8 giá trị mỗi byte cần:

\[
\left\lceil \frac{1\,000\,000}{8}\right\rceil
=125\,000\text{ byte}.
\]

Giảm được **8 lần**, nhưng rank1(i) tính ngây thơ vẫn phải đếm i bit; select1(k) vẫn có thể dò từ đầu. **Đóng gói** và **lập chỉ mục để truy vấn** là hai bước khác nhau.

### 4.2. Thêm chỉ mục rank

Một triển khai thực dụng ghi tổng số bit 1 sau mỗi **512 bit**. Với khoảng 1 triệu bit, có gần **1.954** mốc block; nếu mỗi bộ đếm chiếm 4 byte thì metadata khoảng **7,8 KB**.

~~~text
function RANK1(i):              # số bit 1 trong i bit đầu
    block = floor(i / 512)
    answer = prefix_ones[block] # số 1 trong block*512 bit đầu
    answer += POPCOUNT(bits[block*512 : i])
    return answer
~~~

POPCOUNT đếm các bit 1 theo từ máy; phần phải xử lý sau mốc block dài tối đa **511 bit**. Với từ máy 64 bit, đoạn cuối gồm không quá tám từ. Tổng payload và metadata trong ví dụ xấp xỉ **132,8 KB**, vẫn nhỏ hơn đáng kể so với 1.000.000 byte Boolean.

Đây là thiết kế **thực dụng**, chưa phải chứng minh \(n+o(n)\) bit cho mọi n: bảng với khoảng cách block và tỷ lệ phụ trội cố định có thể dùng \(\Theta(n)\) bit metadata về mặt tiệm cận. Các cấu trúc bitvector súc tích tinh vi hơn dùng chỉ mục nhiều tầng và kỹ thuật ở mức từ máy để hỗ trợ **ACCESS, RANK, SELECT trong \(O(1)\)** trên mô hình word RAM thích hợp, với không gian **\(n+o(n)\)** bit. Không thể suy SELECT có cùng cận chỉ từ bảng rank đơn giản; SELECT cần thêm cơ chế riêng.

## 5. Cấu trúc cây gọn: mã LOUDS

**LOUDS** (*Level-Order Unary Degree Sequence*) mã hóa hình dạng của **cây có gốc và có thứ tự các con** bằng bitvector. Thay vì lưu từng nút heap và nhiều con trỏ, ta duyệt nút theo thứ tự mức (**BFS**) và với mỗi nút có d con, ghi **d bit 1 rồi một bit 0**.

~~~text
       A
      / \
     B   C
    /
   D
~~~

Thứ tự BFS là A, B, C, D; bậc lần lượt 2, 1, 0, 0:

~~~text
Nút:       A       B     C     D
Bậc:       2       1     0     0
Mã:        110     10    0     0
Chuỗi LOUDS: 1101000
~~~

Với n nút của một cây có gốc, có đúng \(n-1\) cạnh. Theo quy ước này, chuỗi LOUDS có **n−1 bit 1** (mỗi cạnh đóng góp một bit) và **n bit 0** (mỗi nút đóng góp một bit), tổng **\(2n-1\)** bit cho **hình dạng cây**.

Kết hợp rank/select trên bitvector, hệ thống có thể điều hướng quan hệ cha/con và bậc nút mà không phải lưu con trỏ cho mỗi cạnh. Phần nhãn **A/B/C/D**, giá trị ứng dụng và các chỉ mục hỗ trợ điều hướng **vẫn tốn bộ nhớ**. Đặc biệt, cây động có INSERT/DELETE liên tục khó hơn cây tĩnh được xây theo lô.

Một tệp nén toàn bộ hình dạng cây có thể nhỏ hơn LOUDS với một số phân phối lặp, nhưng nếu muốn tìm con của nút bất kỳ mà phải giải nén toàn bộ cây thì chi phí truy vấn không tương đương. **LOUDS là biểu diễn dữ liệu được tổ chức để điều hướng**, chứ không chỉ là một dãy bit ngắn.

## 6. Dãy số nguyên tăng: Elias–Fano

Với một dãy số nguyên **không giảm** \(x_0\le x_1\le\cdots\le x_{n-1}\) trong miền \([0,U)\), **Elias–Fano** tận dụng tính đơn điệu để lưu dãy gọn trong khi vẫn truy cập được phần tử theo chỉ số qua bitvector và phép select.

Chọn:

\[
\ell=\left\lfloor\log_2\frac{U}{n}\right\rfloor
\quad(1\le n\le U).
\]

Tách mỗi số thành hai phần:

\[
\operatorname{low}(x)=x\bmod 2^\ell,\qquad
\operatorname{high}(x)=\left\lfloor\frac{x}{2^\ell}\right\rfloor.
\]

Các phần **low** lưu trực tiếp bằng \(\ell\) bit mỗi số. Phần **high** không giảm nên có thể mã hóa bằng bitvector unary, trong đó vị trí các bit 1 cho phép khôi phục high qua select.

Ví dụ \(U=16\), \(n=4\), \(X=[2,3,9,14]\), \(\ell=2\):

| x | high = floor(x/4) | low (2 bit) |
|---:|---:|---|
| 2 | 0 | 10 |
| 3 | 0 | 11 |
| 9 | 2 | 01 |
| 14 | 3 | 10 |

Nếu dùng vị trí bit 1 (đếm từ 0) bằng **high(x_i)+i**, bitvector high dài khoảng \(n+\lceil U/2^\ell\rceil\) bit. Phép select tìm vị trí bit 1 tương ứng để khôi phục high rồi ghép thành \(x_i=2^\ell\operatorname{high}(x_i)+\operatorname{low}(x_i)\).

**Ước lượng dung lượng:** Với \(n=2^{20}\) số nguyên tăng trong miền \(U=2^{30}\), ta có \(\ell=10\). Phần low dùng \(10n\) bit, phần high khoảng \(2n\) bit, tổng **\(12n\) bit = 1,5 MiB**, chưa kể chỉ mục/metadata. Lưu cùng n số bằng 32 bit mỗi số cần **4 MiB**.

Elias–Fano tận dụng **bất biến thứ tự tăng**, giúp khôi phục trực tiếp phần tử thứ i trong các biến thể có hỗ trợ select hiệu quả. Nhưng không được mặc định mọi phép toán như **predecessor** hay INSERT/DELETE đều \(O(1)\): điều đó phụ thuộc chỉ mục và biến thể; cập nhật ngẫu nhiên một biểu diễn tĩnh có thể tốn chi phí xây lại.

## 7. Block compression: khoảng giữa hai thái cực

Giả sử bộ nén tổng quát biến 200 MB sự kiện thành 20 MB, nhưng dữ liệu được lưu như **một luồng nén tuần tự**, không có điểm nhảy. Một yêu cầu lấy sự kiện thứ 900.000 có thể phải giải mã rất nhiều dữ liệu trước nó.

Ta có thể chia dữ liệu thành các block độc lập, mỗi block gồm b phần tử, nén từng block và lưu **bảng offset**:

~~~text
index: [offset block 0][offset block 1][offset block 2]...
data : [compressed B0][compressed B1][compressed B2]...
~~~

Khi nhận ACCESS(i):

1. Xác định block chứa i bằng phép chia nguyên \(\lfloor i/b\rfloor\).
2. Lấy offset của block trong index.
3. Đọc và giải mã duy nhất block đó.
4. Chọn phần tử i trong kết quả giải mã.

Nếu giải mã cả block tốn \(O(b)\) thao tác theo số phần tử, giảm b có thể giảm độ trễ đọc ngẫu nhiên nhưng tăng header và kích thước bảng offset. Tăng b thường tạo cơ hội nén tốt hơn nhưng có thể bắt đọc/giải mã nhiều dữ liệu thừa hơn.

Như vậy, **nén có chỉ mục** có thể đáp ứng một phần nhu cầu truy vấn nhanh. Với một cấu trúc súc tích chuyên dụng, cách mã hóa có thể hỗ trợ trực tiếp những thao tác mạnh hơn, ví dụ rank/select hay điều hướng cây, thay vì chỉ giải mã từng block rồi quét.

## 8. Hai thước đo độc lập: dung lượng và chi phí truy vấn

Xét một ví dụ **giả định**, không phải benchmark sản phẩm:

| Tiêu chí | Luồng nén không chỉ mục | Biểu diễn gọn có chỉ mục |
|---|---|---|
| Dung lượng từ 200 MB dữ liệu gốc | 20 MB | 27 MB |
| ACCESS(i) bất kỳ | Có thể giải mã tiền tố dài. | Xác định vùng cần đọc và giải mã cục bộ. |
| RANGE(lo, hi) | Có thể giải mã các bản ghi ngoài khoảng. | Có thể tận dụng thứ tự/chỉ mục để bỏ qua vùng không liên quan. |
| INSERT/DELETE | Có thể phải tạo lại khối nén. | Phụ thuộc cấu trúc; nhiều cấu trúc tĩnh cũng cần tái dựng. |
| Phù hợp | Sao lưu lạnh, truyền và giải mã toàn bộ. | Truy vấn tương tác, đọc ngẫu nhiên thường xuyên. |

Nếu chỉ cần giải nén toàn bộ mỗi đêm, 20 MB có thể là lựa chọn hợp lý. Nếu cần hàng nghìn GET ngẫu nhiên mỗi giây, 27 MB vẫn có thể đáng chọn vì giảm thời gian đọc và bộ nhớ tạm dùng để giải nén.

Nhưng không thể suy ra mọi cấu trúc 27 MB chắc chắn nhanh hơn mọi codec 20 MB: một codec hỗ trợ seek theo frame độc lập, cache và bảng offset cũng có thể phục vụ đọc ngẫu nhiên hiệu quả. **Muốn so công bằng phải đo trên cùng truy vấn và cùng dữ liệu**.

## 9. Tính đủ chi phí bộ nhớ

Kích thước một biểu diễn thực tế không chỉ có payload:

\[
S_{\text{resident}}
=S_{\text{payload}}
+S_{\text{index}}
+S_{\text{metadata}}
+S_{\text{alignment}}.
\]

Trong quá trình xây dựng hoặc cập nhật còn có **bộ nhớ tạm** và đôi khi các bản sao dữ liệu cũ/mới cùng tồn tại. Với cấu trúc lưu trên đĩa, phải phân biệt dung lượng tệp với lượng RAM được nạp thường trú.

- **Payload:** dữ liệu được mã hóa, bitvector, dãy số hoặc nhãn.
- **Index:** bảng rank/select, bảng offset, mốc tìm kiếm, cấu trúc điều hướng.
- **Metadata:** số phần tử, phiên bản định dạng, từ điển, cấu hình mã hóa.
- **Alignment:** padding theo từ máy, cache line hoặc block đĩa.
- **Temporary/peak:** vùng giải mã, xây chỉ mục hoặc tái dựng khi cập nhật, nên đo **riêng** nếu so bộ nhớ thường trú.

Một ví dụ tiết kiệm không cần codec: một triệu nút danh sách liên kết, mỗi nút có một giá trị 32 bit nhưng còn con trỏ 64 bit và overhead cấp phát. Cùng dữ liệu trong một mảng 32 bit liên tiếp chỉ cần khoảng **4 MB payload**. Thay con trỏ bằng chỉ số và đặt dữ liệu liên tục cũng là kỹ thuật **biểu diễn gọn**, dù không dùng thuật toán nén entropy.

## 10. Độ phức tạp và chi phí I/O

Gọi N là số phần tử, B là số phần tử truyền trong mỗi khối I/O, b là số phần tử của một block nén và w là số bit trong từ máy.

| Biểu diễn | ACCESS(i) | RANK1(i) | Quét tuần tự | Ghi chú |
|---|---|---|---|---|
| Mảng nguyên bản | \(O(1)\) trên RAM khi đã có trong bộ nhớ. | \(O(i)\) nếu không có chỉ mục đếm. | \(O(N)\) CPU, khoảng \(O(1+N/B)\) I/O khi liên tục. | Nhanh, nhưng tốn bộ nhớ. |
| Luồng nén tuần tự không chỉ mục | Có thể giải mã tiền tố tới i. | Có thể giải mã và đếm tiền tố. | Chi phí giải mã theo codec. | Phù hợp khi đọc toàn bộ. |
| Nén block + bảng offset | Định vị block và giải mã tối đa b phần tử. | Cần chỉ mục tổng đếm riêng để nhanh. | Giải mã lần lượt các block. | Đánh đổi kích thước block/index. |
| Bitvector đóng gói + rank directory | \(O(1)\) thao tác từ máy để lấy bit. | \(O(1+L/w)\) với block L bit và popcount. | Đọc tuần tự các từ máy. | SELECT cần chỉ mục riêng. |
| Bitvector súc tích với rank/select | Có thể \(O(1)\) theo mô hình word RAM phù hợp. | Có thể \(O(1)\). | Tuyến tính theo lượng dữ liệu phải duyệt. | Có thể dùng \(n+o(n)\) bit cho bitvector bất kỳ. |

Các cận **\(O(1)\)** nói về **thao tác CPU trên mô hình RAM**. Nếu payload/index ở SSD, thiếu cache hoặc phát sinh page fault, số lần đọc block vẫn quan trọng. Một cấu trúc rất nhỏ có thể giảm cache miss nhưng cũng có thể tăng phép dịch bit, giải mã hay nhảy chỉ mục. Chi phí cuối cùng phụ thuộc cả bộ nhớ và CPU.

## 11. Chọn phương án theo loại công việc

**Sao lưu và truyền dữ liệu:** Nếu luồng nghiệp vụ chỉ ENCODE/DECODE toàn bộ, nén tổng quát có thể tối ưu hơn vì không phải trả chi phí chỉ mục không cần thiết.

**Tập bit lớn với nhiều câu hỏi đếm/chọn:** Bitvector có rank/select phù hợp hơn một luồng nén không có chỉ mục, do giao diện yêu cầu đếm và xác định vị trí trực tiếp.

**Trie/cây từ điển ít cập nhật:** LOUDS giảm con trỏ của topology, hỗ trợ điều hướng khi có rank/select. Với cây cần chèn/xóa liên tục, có thể phải chọn cấu trúc động hoặc chấp nhận xây lại.

**Posting list hoặc dãy ID tăng:** Elias–Fano có thể tiết kiệm không gian nhờ tính đơn điệu, trong khi vẫn đọc phần tử theo chỉ số với index phù hợp. Nếu cần cập nhật bất kỳ, phải tính chi phí sửa và rebuild.

**Kho dữ liệu truy vấn liên tục và nhiều cập nhật:** Có thể kết hợp phần dữ liệu tĩnh được mã hóa gọn với **bộ đệm cập nhật**, sau đó hợp nhất/tái dựng theo lô. Cần đo độ trễ cập nhật và dung lượng đỉnh, không chỉ tốc độ đọc.

### Quy trình đánh giá thực tế

1. Xác định **loại dữ liệu và bất biến**: bitvector, cây, chuỗi, dãy tăng, tập thưa hay bảng khóa–giá trị.
2. Liệt kê **phép toán phải hỗ trợ** và tỷ lệ gọi: ACCESS, GET, RANK, SELECT, RANGE, INSERT, DELETE.
3. Phân biệt dữ liệu **tĩnh, append-only hay động**; nhiều cấu trúc súc tích tối ưu nhờ giả thiết tĩnh.
4. So **tổng dung lượng** payload + chỉ mục + metadata, bộ nhớ dựng và đỉnh, không chỉ byte nén.
5. Benchmark **thời gian xây dựng**, truy vấn nóng/lạnh, quét tuần tự, đọc ngẫu nhiên, p95/p99 và I/O trên dữ liệu thực.

## 12. Những ngộ nhận cần tránh

**“Nén càng nhỏ thì cấu trúc càng tốt.”** Sai: tỷ lệ nén chỉ đo không gian, trong khi GET/RANGE có thể phải giải mã lượng lớn dữ liệu.

**“Cấu trúc gọn luôn nhỏ hơn mọi tệp nén.”** Sai: nó có thể dành thêm bit chỉ mục để truy cập nhanh; tệp nén phục vụ sao lưu có thể nhỏ hơn.

**“Đóng gói 1 bit/Boolean thì rank/select đã O(1).”** Sai: phải tổ chức bảng phụ hoặc dùng cấu trúc súc tích chuyên biệt để có cận thời gian đó.

**“Nén là phải giải nén toàn bộ.”** Sai: một số định dạng hỗ trợ block độc lập, seek table hoặc chỉ mục để giải mã cục bộ.

**“Cấu trúc succinct luôn cập nhật nhanh.”** Sai: bố trí bit chặt thường thuận lợi khi đọc tĩnh; chèn/xóa có thể làm dịch nhiều bit và phải cập nhật chỉ mục.

**“Tiết kiệm RAM chắc chắn tiết kiệm CPU.”** Sai: các phép giải mã, rank/select và nhảy bảng có thể tốn CPU; phải đo kết quả tổng thể.

## 13. Bài tập tự kiểm tra có lời giải

### Bài 1 — Đóng gói và bảng rank

Có **800.000** giá trị Boolean, ban đầu mỗi giá trị một byte. Đóng gói 8 bit/byte cần bao nhiêu byte? Nếu có xấp xỉ một bộ đếm 4 byte sau mỗi nhóm 512 bit, dung lượng index khoảng bao nhiêu?

**Lời giải:** Payload là \(800\,000/8=100\,000\) byte. Có \(\lceil800\,000/512\rceil=1563\) nhóm, chỉ mục xấp xỉ \(1563\times4=6252\) byte, chưa tính phần đầu/cuối và căn chỉnh. Tổng khoảng **106,3 KB** theo cách tính thập phân.

### Bài 2 — Rank và select

Cho B = 1 0 1 1 0 0 1 0 1 1 với vị trí bắt đầu từ 1. Tính rank1(8), select1(5) và số bit 1 thuộc \([3,9]\).

**Lời giải:** rank1(8) = **4**; select1(5) = **9**. Trong \([3,9]\) có rank1(9) − rank1(2) = 5 − 1 = **4** bit 1.

### Bài 3 — Mã hóa LOUDS

Cây gốc R có hai con A và B; A không có con, B có một con C, C không có con. Hãy ghi LOUDS theo thứ tự BFS.

**Lời giải:** Bậc của R, A, B, C lần lượt 2, 0, 1, 0. Mã là **110 0 10 0**, ghép lại **1100100**, dài 7 bit = \(2\times4-1\). Chưa tính nhãn nút và index.

### Bài 4 — Dung lượng hay tốc độ truy cập?

Tệp nén tuần tự chiếm 8 MB nhưng giải mã thành 100 MB. Cấu trúc gọn 12 MB có chỉ mục, cho phép lấy phần tử bất kỳ bằng cách giải mã một block nhỏ. Dịch vụ cần nhiều lượt đọc ngẫu nhiên và không bị giới hạn đĩa nghiêm ngặt. Phương án nào đáng benchmark trước?

**Lời giải:** Cấu trúc **12 MB** đáng thử vì giao diện truy cập cục bộ phù hợp tải đọc ngẫu nhiên. Nhưng cần đo độ trễ, RAM, CPU và I/O thực tế; một định dạng nén có chỉ mục tốt cũng có thể cạnh tranh.

### Bài 5 — Cận thông tin và truy vấn

Một bitvector n vị trí biết trước chỉ có đúng m bit 1, với \(m\ll n\). Vì sao n bit chưa phải cận thông tin tốt nhất? Muốn tìm vị trí của bit 1 thứ k cần phép toán gì?

**Lời giải:** Chỉ có \(\binom{n}{m}\) trạng thái hợp lệ, nên cận thông tin là khoảng \(\log_2\binom{n}{m}\) bit, có thể thấp hơn nhiều so với n. Phép toán cần là **select1(k)**; nếu muốn thực hiện nhanh phải tính cả không gian và thời gian của index select.

## 14. Ghi nhớ

**Nén toàn bộ dữ liệu** tập trung vào số byte và khả năng khôi phục nội dung. **Cấu trúc dữ liệu gọn** bố trí bit và chỉ mục để vẫn **truy cập, đếm, chọn vị trí, tìm kiếm hoặc điều hướng** hiệu quả. **Cấu trúc dữ liệu súc tích** thêm mục tiêu lý thuyết rõ ràng: dung lượng gần cận dưới thông tin cùng cận thời gian truy vấn xác định.

Khi chọn cách biểu diễn dữ liệu, hãy hỏi: **Ứng dụng cần phép toán nào? Mỗi phép toán tốn bao nhiêu thời gian, I/O và dung lượng chỉ mục? Dữ liệu có bị cập nhật thường xuyên không?** Những câu hỏi này giúp chọn cấu trúc phù hợp hơn việc chỉ xếp hạng các phương án theo tỷ lệ nén.
