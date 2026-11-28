# Chọn số bit, số hàm băm và dung lượng dự kiến

Một **Bloom filter** có thể giúp giảm số lượt đọc đĩa, tra cơ sở dữ liệu hoặc kiểm tra một tập khóa rất lớn. Nhưng nếu cấu hình quá ít bit, gần như mọi truy vấn sẽ trả **“có thể có”**, khiến bộ lọc mất tác dụng. Nếu cấu hình quá nhiều bit hoặc quá nhiều lần băm, hệ thống lãng phí bộ nhớ và CPU. Vì vậy câu hỏi quan trọng trong thiết kế không chỉ là **“Bloom filter hoạt động thế nào?”**, mà là:

> Với số khóa dự kiến và mức dương tính giả chấp nhận được, phải cấp phát **bao nhiêu bit**, tính **bao nhiêu vị trí băm cho mỗi khóa**, và chuẩn bị cho **bao nhiêu khóa phân biệt** trong suốt vòng đời bộ lọc?

Bài này thuộc chương **Cấu trúc xác suất** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo định hướng học cấu trúc dữ liệu thông qua **bất biến, thao tác, thời gian, bộ nhớ** và lựa chọn cấu trúc phù hợp, chúng ta tập trung vào **bài toán định cỡ Bloom filter**: từ yêu cầu nghiệp vụ → giả định tải → công thức xác suất → tham số nguyên → bộ nhớ thực tế → vận hành khi quy mô thay đổi.

Bloom filter chuẩn vẫn giữ quy tắc một phía: **False = chắc chắn chưa được thêm** khi mọi khóa mục tiêu đã được mã hóa đầy đủ và trạng thái/hàm băm nhất quán; **True = có thể đã được thêm** vì có thể xuất hiện **dương tính giả**. Các tham số m, h và n chủ yếu ảnh hưởng tới **tỷ lệ dương tính giả và chi phí**, không thay đổi bản chất suy luận ấy.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Diễn giải chính xác bốn tham số **n, m, h, p**, phân biệt **số khóa phân biệt** với số lần gọi add.
2. Dẫn xuất xấp xỉ xác suất một bit còn 0, tỷ lệ bit đã bật, và xác suất dương tính giả của Bloom filter.
3. Tính **số bit tối ưu xấp xỉ** cho n và FPR mục tiêu p theo công thức \(m\approx-n\ln p/(\ln2)^2\).
4. Tính **số vị trí băm gần tối ưu** \(h\approx(m/n)\ln2\), hiểu tại sao h không thể tăng tùy ý.
5. Quy đổi **bit → byte → KiB → MiB**, phân biệt bộ nhớ mảng bit với overhead metadata, cấp phát và khả năng cache.
6. So sánh lựa chọn **p=10%, 1%, 0,1%, 0,01%** và mô tả chi phí bộ nhớ/CPU tăng khi muốn sai số thấp hơn.
7. Thiết kế khi **đã có ngân sách m cố định**, suy ra h gần tối ưu và FPR dự báo có thể đạt được.
8. Cấu hình Bloom filter với **làm tròn m, h thành số nguyên**, kiểm tra FPR ước tính sau làm tròn.
9. Xác định **dung lượng dự kiến** theo vòng đời: insert-only, khóa trùng, phân vùng, retention, tăng trưởng đột biến.
10. Phân tích khi số khóa thực tế vượt n dự kiến: tỷ lệ bit 1 tăng, FPR tăng, cần xây lại hoặc chia lớp.
11. Cài đặt **bộ tính tham số Python** và một Bloom filter mẫu dùng các tham số đã chọn.
12. Phân biệt **FPR lý thuyết theo mô hình hash lý tưởng** với số đo trên khóa âm tính có nhãn sự thật.
13. Tính **chi phí false positive đối với nguồn chính xác** và lựa chọn điểm cân bằng giữa RAM, CPU, I/O, độ trễ.
14. Nhận diện hạn chế của hash, seed, phiên bản, xóa, cache locality, snapshot và bảo đảm “không âm tính giả”.
15. Giải được bài tập định cỡ và giải thích rõ các giả định của từng kết quả.

## 2. Trước khi tính toán: Bloom filter lưu và trả lời điều gì?

Bloom filter chuẩn gồm **m bit ban đầu đều bằng 0** và **h vị trí băm** cho mỗi khóa. Với khóa x, các vị trí băm được biểu diễn:

\[
H_0(x),H_1(x),\ldots,H_{h-1}(x)\in\{0,\ldots,m-1\}.
\]

Khi **add(x)**, tất cả những bit ấy được bật thành 1. Khi **might_contain(x)**:

- Có ít nhất một bit bằng **0** → trả **False**, khóa chưa được add thành công trong bộ lọc theo đúng hợp đồng.
- Tất cả bit đều bằng **1** → trả **True**, nhưng chưa chứng minh khóa đã add; đây có thể là **false positive (FP)**.

Ví dụ:

~~~text
m = 12 bit, h = 3 vị trí băm.

Ban đầu:
index: 0 1 2 3 4 5 6 7 8 9 10 11
bits:  0 0 0 0 0 0 0 0 0 0  0  0

add(A): H(A)={1,4,10}
bits:  0 1 0 0 1 0 0 0 0 0  1  0

add(B): H(B)={4,7,10}
bits:  0 1 0 0 1 0 0 1 0 0  1  0

query(C): H(C)={1,7,10}; C chưa từng add.
Mọi bit đều 1 → True, một dương tính giả.
~~~

Bộ lọc **không lưu tên khóa**, nên không thể phân biệt các bit đã được chính C bật với các bit do A/B bật. Càng nhiều khóa phân biệt cùng sử dụng m bit, số bit 1 thường càng tăng.

### 2.1. Bốn tham số chính

| Ký hiệu | Ý nghĩa | Đơn vị / miền hợp lệ |
| --- | --- | --- |
| **n** | Số **khóa phân biệt dự kiến** được lưu trong vòng đời | Số nguyên dương trong bài toán định cỡ |
| **m** | Số **bit logic** của mảng Bloom | Số nguyên dương |
| **h** | Số vị trí băm cho mỗi khóa | Số nguyên h ≥ 1 |
| **p** | Tỷ lệ **false positive mục tiêu** trên các truy vấn thực sự âm tính | Số thực 0 < p < 1 |

Một số tài liệu dùng **k** thay cho **h** để chỉ số hàm băm. Trong bài này dùng **h** để tránh nhầm với k của bài toán top-k hoặc số phân vùng.

**Không nhầm n với số request/query.** Một filter có thể phục vụ hàng tỷ truy vấn nhưng chỉ chứa một triệu khóa phân biệt. Dung lượng n chủ yếu được xác định bởi **những khóa cần add**, không phải số lần người dùng hỏi membership.

### 2.2. Thông số phát sinh quan trọng: bit trên mỗi khóa

Định nghĩa:

\[
b=\frac{m}{n}\quad\text{bit/khóa phân biệt dự kiến}.
\]

Với n=1.000.000 và m=10.000.000 bit, ta có b=10 bit/khóa. Nếu m giữ nguyên nhưng số khóa tăng lên 2.000.000, tỷ lệ thực còn b=5 bit/khóa; **hiệu quả lọc sẽ khác** mặc dù h được lưu trong cấu hình vẫn là h cũ.

### 2.3. FPR được tính trên nhóm nào?

Theo bảng kết quả membership:

| Sự thật | Bloom trả True | Bloom trả False |
| --- | --- | --- |
| Khóa đã add | True positive (TP) | False negative (FN) — không cho phép trong mô hình chuẩn |
| Khóa chưa add | False positive (FP) | True negative (TN) |

FPR trên tập truy vấn có nhãn sự thật:

\[
\mathrm{FPR}=\frac{FP}{FP+TN}.
\]

Mẫu số **không bao gồm** những truy vấn thực sự có khóa. Một filter mục tiêu FPR=1% không có nghĩa 1% mọi request sai, cũng không có nghĩa 1% các câu trả lời True là sai. Tỷ lệ sai trong nhóm True còn phụ thuộc **tỷ lệ khóa thực sự có** trong workload.

## 3. Vì sao m, h và n quyết định độ bão hòa?

Ta bắt đầu từ mô hình lý tưởng: mỗi lần băm chọn một vị trí trong m bit **đều và đủ độc lập**. Có n khóa phân biệt, mỗi khóa đóng góp h lần chọn vị trí.

### 3.1. Xác suất một bit vẫn bằng 0

Với một bit cố định, một lần chọn vị trí **không rơi vào nó** với xác suất:

\[
1-\frac1m.
\]

Sau hn lượt chọn vị trí:

\[
P_0=\left(1-\frac1m\right)^{hn}.
\]

Khi m khá lớn:

\[
\left(1-\frac1m\right)^{hn}\approx e^{-hn/m}.
\]

Vậy:

\[
\boxed{P(\text{bit}=0)\approx e^{-hn/m}.}
\]

### 3.2. Tỷ lệ bit 1 dự kiến

Tỷ lệ bit được bật xấp xỉ:

\[
\boxed{q=P(\text{bit}=1)\approx1-e^{-hn/m}.}
\]

**Số bit 1 kỳ vọng** trong mô hình đó:

\[
E[\text{bit 1}]=m\left[1-\left(1-\frac1m\right)^{hn}\right].
\]

Công thức dùng lũy thừa là **giá trị kỳ vọng chính xác theo mô hình lựa chọn vị trí ngẫu nhiên độc lập có hoàn lại**; dạng mũ là **xấp xỉ** thường dùng cho Bloom filter lớn.

### 3.3. Từ bit 1 tới dương tính giả

Một khóa **chưa từng add** bị FP nếu **tất cả h vị trí truy vấn** đều đang bằng 1. Dưới xấp xỉ độc lập thông dụng:

\[
\boxed{p_{\mathrm{FP}}\approx\left(1-e^{-hn/m}\right)^h=q^h.}
\]

Có hai tầng giả định: phân bố của các vị trí khi insert và sự gần độc lập của các bit/vị trí khi truy vấn. Không được gọi công thức \(q^h\) là xác suất **chính xác tuyệt đối với mọi m, h, n**. Với m nhỏ, các bit phụ thuộc nhau; với hash/khóa do đối thủ kiểm soát, FPR thực tế có thể khác.

### 3.4. Ví dụ hiểu cơ chế qua độ bão hòa

Giả sử m/n=10 và chọn h≈7. Khi đã add khoảng n khóa phân biệt:

\[
q\approx1-e^{-7/10}\approx0,5034.
\]

Khoảng **một nửa mảng bit** được bật — đây không phải lỗi hay “lãng phí 50%”. Khi đó:

\[
p_{\mathrm{FP}}\approx 0,5034^7\approx0,82\%.
\]

Khi tăng số khóa mà **m và h giữ nguyên**, q tăng, nên \(q^h\) tăng nhanh. Một filter gần toàn bit 1 sẽ trả True cho gần như mọi khóa lạ.

### 3.5. Chỉ cần tăng h để giảm sai số?

**Không.** Tăng h có hai hiệu ứng:

1. Một khóa lạ cần khớp **nhiều bit 1 hơn** mới nhận True.
2. Nhưng mỗi khóa thêm cũng bật **nhiều bit hơn**, khiến mảng bão hòa nhanh.

Vì hai hiệu ứng ngược nhau, tồn tại một h gần tối ưu với m và n đã chọn.

## 4. Số vị trí băm gần tối ưu

Với m và n cố định, xét xấp xỉ:

\[
p(h)=\left(1-e^{-hn/m}\right)^h.
\]

Đặt \(b=m/n\). Lựa chọn tối ưu theo h thực dương của mô hình này là:

\[
\boxed{h^*=\frac mn\ln2=b\ln2.}
\]

Tại điểm tối ưu:

\[
e^{-h^*n/m}=e^{-\ln2}=\frac12,
\]

nên **xấp xỉ một nửa số bit bằng 1** và:

\[
p^*\approx\left(\frac12\right)^{h^*}.
\]

### 4.1. Làm tròn h thành số nguyên

h phải là **số nguyên**. Với b=10:

\[
h^*=10\ln2\approx6,93.
\]

Chọn **h=7** thay vì 6 hoặc 8 thường cho FPR gần tối ưu nhất trong trường hợp này.

Nếu b=4:

\[
h^*\approx2,77\Rightarrow h\approx3.
\]

Không nên cố “dùng 10 hash cho chắc” khi chỉ có 4 bit/khóa. Nhiều hash có thể làm bit gần bão hòa và **FPR tệ hơn**.

### 4.2. So sánh ứng viên nguyên gần điểm tối ưu

Khi m, n đã biết, cách làm thực tế:

1. Tính \(h^*=(m/n)\ln2\).
2. Lấy ít nhất hai ứng viên nguyên \(\lfloor h^*\rfloor\) và \(\lceil h^*\rceil\), chặn dưới bằng 1.
3. Tính lại **p dự báo** bằng công thức xấp xỉ cho từng ứng viên.
4. Chọn h cho FPR thấp nhất; nếu kết quả gần bằng nhau, cân nhắc **ít hash hơn để giảm CPU**.

**Lưu ý:** Điểm tối ưu theo p không tự tối ưu theo độ trễ hoặc chi phí điện toán. Có hệ thống cố ý dùng h ít hơn để đổi một chút FPR lấy ít lần đọc bit/hash hơn.

### 4.3. Khi p đã biết, h còn có một công thức ngắn

Kết hợp công thức h tối ưu với m tối ưu sẽ cho:

\[
\boxed{h^*\approx\log_2\frac1p=-\frac{\ln p}{\ln2}.}
\]

Ví dụ p=1%:

\[
\log_2 100\approx6,64\Rightarrow h\approx7.
\]

Đây là **h gần tối ưu cho m đã được định cỡ theo p**, không phải “luôn 7 hash” bất kể n và m.

## 5. Số bit cần cho FPR mục tiêu

Tại \(h^*=(m/n)\ln2\), ta có:

\[
p^*\approx\left(\frac12\right)^{(m/n)\ln2}
=e^{-(m/n)(\ln2)^2}.
\]

Lấy logarit:

\[
\ln p\approx-\frac mn(\ln2)^2.
\]

Suy ra công thức thiết kế kinh điển:

\[
\boxed{m^*\approx-\frac{n\ln p}{(\ln2)^2}.}
\]

Và:

\[
\boxed{\frac mn\approx-\frac{\ln p}{(\ln2)^2}
\quad \text{bit/khóa}.}
\]

**Điều kiện:** n>0 và 0<p<1. Công thức xuất phát từ mô hình hash lý tưởng và tối ưu liên tục, sau đó phải **làm tròn các tham số** thành số nguyên.

### 5.1. Thí dụ hoàn chỉnh: một triệu khóa, FPR 1%

Đầu vào:

~~~text
n = 1 000 000 khóa phân biệt
p = 0,01 (1%)
~~~

Tính:

\[
m^*\approx\frac{-1.000.000\ln(0,01)}{(\ln2)^2}
\approx9.585.059\ \text{bit}.
\]

Làm tròn/cấp phát:

~~~text
m xấp xỉ       9 585 059 bit
bit/khóa       9,585 bit/khóa
byte tối thiểu  ceil(m/8) ≈ 1 198 133 byte
KiB            ≈ 1 170 KiB
MiB            ≈ 1,14 MiB
h tối ưu        ≈ (m/n) ln2 ≈ 6,64
h nguyên        7
~~~

Con số khoảng 1,14 MiB là **vùng bit tối thiểu**, chưa bao gồm đối tượng chứa bytearray, hash seeds, counter, serialization header, bộ nhớ cấp phát/căn chỉnh hoặc nguồn dữ liệu chính xác.

### 5.2. Bảng các mức FPR

Với **n=1.000.000 khóa phân biệt**:

| FPR mục tiêu | Bit/khóa xấp xỉ | Bit mảng xấp xỉ | Dung lượng bitarray | h gần tối ưu |
| --- | ---: | ---: | ---: | ---: |
| 10% | 4,79 | 4,79 triệu bit | 0,57 MiB | 3 |
| 1% | 9,59 | 9,59 triệu bit | 1,14 MiB | 7 |
| 0,1% | 14,38 | 14,38 triệu bit | 1,71 MiB | 10 |
| 0,01% | 19,17 | 19,17 triệu bit | 2,29 MiB | 13 |

Mỗi lần giảm p đi **một bậc thập phân**, số bit/khóa tăng khoảng:

\[
\frac{\ln10}{(\ln2)^2}\approx4,79\ \text{bit/khóa}.
\]

Đồng thời h tối ưu tăng khoảng:

\[
\log_2 10\approx3,32\ \text{vị trí/khóa}.
\]

Vì vậy **FPR nhỏ hơn không miễn phí**: thêm RAM và thông thường thêm CPU đọc/băm.

### 5.3. Dung lượng tăng gần tuyến tính theo n

Giữ p mục tiêu và tỉ lệ bit/khóa b cố định, số bit cần là \(m=bn\), tức **gần tuyến tính theo số khóa phân biệt**.

~~~text
Mục tiêu p = 1%:

n =    100 000 → m ≈   0,959 triệu bit → 0,114 MiB.
n =  1 000 000 → m ≈   9,585 triệu bit → 1,14 MiB.
n = 10 000 000 → m ≈  95,851 triệu bit → 11,43 MiB.
~~~

Đây là **kế hoạch cấp phát trước**, không phải bộ lọc 1 triệu khóa tự tăng mười lần khi cần chứa 10 triệu khóa. Với Bloom chuẩn, m thường cố định sau khi tạo.


## 6. Dự báo n: dung lượng phải tính theo vòng đời dữ liệu

**n là một quyết định thiết kế**, không chỉ là một tham số trong công thức. Nếu dự báo n quá thấp, mảng bit có thể bão hòa trước khi hết vòng đời. Nếu dự báo quá cao, RAM bị dành sẵn nhưng không sử dụng hiệu quả.

### 6.1. “Một triệu request” không tương đương “một triệu khóa”

Ví dụ luồng sự kiện một ngày:

~~~text
Tổng số lượt gọi add:    20 000 000
Mã sự kiện phân biệt:     1 000 000

Cùng một mã có thể xuất hiện nhiều lần.
~~~

Với Bloom bit chuẩn, **add lặp một khóa luôn bật cùng các vị trí băm**. Vì vậy định cỡ theo 20 triệu **lượt add** sẽ quá lớn so với mô hình một triệu **khóa phân biệt** nếu hai con số đó có thể được ước lượng tin cậy.

**Ngược lại:** Nếu nhiều khóa được phát sinh mới liên tục, số khóa phân biệt có thể gần bằng số lượt add. Khi thiếu thống kê chính xác, nên chọn **cận trên bảo thủ** phù hợp ngân sách hoặc dự trù tái xây.

### 6.2. Vòng đời filter quyết định phạm vi n

Cần xác định bộ lọc phục vụ:

- **Một SSTable bất biến:** n là số khóa phân biệt trong SSTable đó, không phải toàn bộ database.
- **Một tập cache hiện hành:** n là số khóa sẽ có mặt/được biểu diễn trong vòng đời filter; nếu không hỗ trợ xóa, n có thể là **tổng số khóa từng add**, kể cả khóa không còn trong cache.
- **Một phân vùng theo ngày:** n là số khóa phân biệt trong ngày/phân vùng ấy.
- **Bộ lọc tồn tại nhiều năm:** n là số khóa phân biệt tích lũy từ khi tạo, nếu không có tái xây/xóa.
- **Bộ lọc cho một snapshot:** n là số khóa phân biệt của snapshot; filter không tự cập nhật khi snapshot thay đổi.

Câu hỏi “giữ lại dữ liệu 7 ngày” không tự nói một Bloom bit chỉ-thêm có thể **quên khóa sau 7 ngày**. Nếu không tái xây hay dùng biến thể phù hợp, các khóa cũ vẫn làm bit 1 và tiếp tục góp phần bão hòa.

### 6.3. Dự báo từ tốc độ xuất hiện khóa mới

Giả sử hệ thống đã có U khóa trong phạm vi một filter, và dự báo tối đa r **khóa mới phân biệt mỗi ngày** trong T ngày:

\[
n_{\mathrm{forecast}}\le U+rT
\]

nếu r là cận trên thích hợp và các khóa mới không bị trừ khỏi phạm vi filter trong khoảng ấy.

Ví dụ:

~~~text
U ban đầu:         400 000 khóa phân biệt
r dự kiến:          30 000 khóa mới/ngày
T vận hành:             20 ngày

n tối đa theo dự báo: 400 000 + 30 000*20
                     = 1 000 000 khóa.
~~~

Nếu thêm **20% headroom** để chịu biến động:

\[
n_{\mathrm{plan}}=\lceil1,2\,n_{\mathrm{forecast}}\rceil
=1.200.000.
\]

Headroom là **quyết định nghiệp vụ/vận hành**, không phải một hằng số toán học bắt buộc. Nếu n dự kiến đã là cận trên đủ chặt, không cần tăng thêm tùy tiện; nếu phân phối tăng trưởng có đuôi dài, 20% có thể chưa đủ.

### 6.4. Các phân vùng khác nhau cần phân bổ khác nhau

Một hệ thống có nhiều phân vùng không nhất thiết nên cấp cùng m cho tất cả. Phân vùng chứa 10.000 khóa và phân vùng chứa 10 triệu khóa có thể cần số bit khác nhau nếu cùng FPR mục tiêu.

Với các phân vùng độc lập và truy vấn chỉ tới **một phân vùng liên quan**, có thể định cỡ từng filter theo n_i. Nếu một truy vấn phải hỏi **tất cả phân vùng**, tổng xác suất false positive có thể khác p_i của từng phân vùng; phải phân tích ngữ nghĩa kết hợp kết quả.

### 6.5. Cận trên không chắc chắn và việc làm lại dự báo

Khi dữ liệu tăng theo mùa, sản phẩm ra mắt, tấn công spam hoặc đột biến ID, giả định r có thể lỗi thời. Quy trình vận hành nên theo dõi **số khóa phân biệt ước lượng/nguồn chính xác**, **tỷ lệ bit 1**, FPR thực đo và điều kiện tái xây filter.

**Bloom cố định không thất bại ngay khi vượt n thiết kế**: nó vẫn add và có thể không FN, nhưng FPR tăng, khiến chi phí tra nguồn chính xác tăng. Đây là sự suy giảm chất lượng dần dần.

## 7. Khi ngân sách RAM đã cố định: ta có thể chứa bao nhiêu khóa?

Giả sử hệ thống chỉ cấp **R byte** cho **mảng bit**.

Đổi sang bit:

\[
m=8R.
\]

Nếu còn phải dành metadata trong ngân sách, hãy **trừ phần metadata trước** rồi mới đổi phần còn lại sang m bit. Ví dụ 2 MiB bộ nhớ toàn bộ **không có nghĩa** mảng bit được phép chiếm trọn 2 MiB khi runtime và nguồn dữ liệu còn cần bộ nhớ riêng.

### 7.1. FPR tốt nhất theo m và n

Nếu chọn h gần tối ưu:

\[
p_{\min}\approx e^{-(m/n)(\ln2)^2}.
\]

Đặt \(b=m/n\), công thức trở thành:

\[
\boxed{p_{\min}\approx (0,6185)^b}.
\]

**Đây là mức xấp xỉ tối ưu của Bloom tiêu chuẩn**, không phải bảo đảm chính xác cho mọi dữ liệu/hàm hash.

Với m/n=8:

\[
p_{\min}\approx e^{-8(\ln2)^2}\approx2,14\%.
\]

Với m/n=12:

\[
p_{\min}\approx e^{-12(\ln2)^2}\approx0,314\%.
\]

Thêm bit trên mỗi khóa giúp giảm FPR theo hàm mũ, nhưng phải trả thêm bộ nhớ.

### 7.2. Dung lượng khóa tối đa gần đúng cho p mục tiêu

Đảo công thức chọn m:

\[
\boxed{
n_{\max}\approx\frac{m(\ln2)^2}{-\ln p}.
}
\]

Đây là **số khóa phân biệt gần đúng theo mô hình tối ưu h liên tục** có thể chứa ở FPR mục tiêu p. Thực tế phải làm tròn h, căn chỉnh m, cân nhắc headroom và đo trên workload.

**Ví dụ:** Dành đúng **1 MiB** mảng bit:

~~~text
R = 1 048 576 byte
m = 8 388 608 bit

Mục tiêu p = 1%
bit/khóa cần ≈ 9,585

n_max xấp xỉ:
8 388 608 / 9,585 ≈ 875 000 khóa phân biệt.
~~~

Nếu cần chứa một triệu khóa ở p≈1%, **1 MiB cho mảng bit là không đủ** theo thiết kế gần tối ưu của Bloom tiêu chuẩn. Có thể tăng RAM, chấp nhận FPR cao hơn, chia dữ liệu theo vòng đời, hoặc chọn một cấu trúc khác.

### 7.3. Với h cố định, giải ngược theo n

Từ:

\[
p\approx(1-e^{-hn/m})^h
\]

suy ra:

\[
\boxed{
n\approx-\frac mh\ln\left(1-p^{1/h}\right).
}
\]

Công thức có ích nếu **m và h đã được khóa trong một hệ thống triển khai**: nó cho ngưỡng số khóa gần đúng tương ứng với FPR p.

Không được dùng công thức này như bằng chứng một filter có thể vượt n đó mà vẫn giữ FPR trong mọi trường hợp; chất lượng hash và phân bố truy vấn vẫn quyết định số đo thật.

### 7.4. Nếu yêu cầu p thấp hơn mức bộ nhớ cho phép

Khi m và n đã cố định, **không thể giảm FPR tùy ý bằng tăng h**. p đạt cực tiểu gần \(h^*=(m/n)\ln2\). Nếu mức p yêu cầu nhỏ hơn p tối ưu ấy, giải pháp phải đổi **m, n, loại cấu trúc hoặc đặc tả**.

Một phương án thiết kế đúng cần nói rõ **không khả thi dưới ngân sách hiện tại**, thay vì báo một giá trị h tùy ý để ngụ ý đạt mục tiêu.

## 8. Làm tròn và cấp phát: từ công thức thực đến cấu hình chạy được

Công thức dùng số thực, nhưng bộ nhớ và số hàm băm phải dùng **số nguyên**.

### 8.1. Một quy trình định cỡ an toàn theo mô hình

1. **Xác định n_plan ≥ 1**: số khóa phân biệt tối đa dự kiến trong vòng đời.
2. **Chọn p_target ∈ (0,1)**: xác suất dương tính giả mục tiêu.
3. Tính **m_ideal = −n_plan ln(p_target)/(ln2)²**.
4. **Làm tròn m lên** thành số bit nguyên; nếu cần byte/word alignment, làm tròn thêm lên bội 8, 64 hoặc kích thước phù hợp.
5. Tính **h_ideal = (m/n_plan)ln2**.
6. Thử **h=floor(h_ideal)** và **h=ceil(h_ideal)**, chặn h≥1.
7. Tính lại \(p_{\mathrm{est}}=(1-e^{-hn/m})^h\) cho **m, h nguyên đã chọn**.
8. Nếu **p_est > p_target**, tăng m và chọn lại h; không được báo “đạt p” chỉ từ công thức số thực.
9. Ghi cấu hình **m, h, hash version/seed/encoding, n_plan, p_target, thời điểm hoặc version snapshot** để có thể khôi phục nhất quán.
10. Sau khi dùng thực tế, đo FPR và độ bão hòa; **không tự đổi m hoặc h trên mảng bit cũ**.

### 8.2. Vì sao làm tròn h cần kiểm tra lại?

Công thức m_ideal giả định h có thể nhận số thực \(h^*\). Thực tế **h=6 hoặc h=7**, không phải 6,64. Khi chọn h nguyên, FPR dự báo có thể nhỉnh hơn mức tối ưu số thực.

Chỉ làm tròn m_ideal lên **không luôn đủ** để đảm bảo công thức p_est với h nguyên **≤ p_target**. Nếu yêu cầu thiết kế nghiêm theo **xấp xỉ đã chọn**, hãy kiểm tra p_est và tăng m nếu cần.

**Lưu ý:** Đạt p_est≤p_target vẫn **không phải bảo đảm xác suất tuyệt đối** với hash/dữ liệu tùy ý; đây là một mục tiêu lý thuyết trong mô hình giả định.

### 8.3. Làm tròn byte so với số bit logic

Nếu m=1001 bit:

~~~text
Số byte lưu: ceil(1001/8) = 126 byte.
Dung lượng vật lý: 126*8 = 1008 bit.
Số bit dư ở byte cuối: 7 bit.
~~~

Có hai cách thiết kế hợp lệ, phải chọn nhất quán:

- **Giữ m_logic=1001**, cấp phát 126 byte, chỉ tính hash modulo 1001; 7 bit còn lại không dùng.
- **Đặt m_logic=1008**, dùng tất cả 1008 bit, tính lại h/p theo m=1008; không được áp dụng nếu filter cũ đã có dữ liệu với m=1001.

Không được khi insert lấy modulo 1001 nhưng khi query lấy modulo 1008; cùng khóa có thể dẫn tới **âm tính giả do đổi cấu hình**.

### 8.4. Căn chỉnh theo cache/word

Một số thư viện cấp phát theo các khối 64 bit, trang hoặc cache line để đọc/ghi hiệu quả. Khi đó:

\[
m_{\mathrm{aligned}}=
a\left\lceil\frac{m_{\mathrm{required}}}{a}\right\rceil
\]

với a là số bit của một khối căn chỉnh.

Căn chỉnh làm **m thực dùng** lớn hơn một chút, nhưng không tự bảo đảm truy vấn nhanh hơn trên mọi workload. Tính cục bộ cache còn phụ thuộc vị trí băm, cấu trúc block và cách đọc của CPU.

### 8.5. Trường hợp biên phải xử lý tường minh

- **n=0**: Bộ lọc rỗng có thể trả False cho mọi khóa mà chưa cần định cỡ qua công thức có chia cho n. Nếu chuẩn bị cho khóa tương lai, chọn n_plan dương.
- **p=0**: Với tập khóa bất kỳ và dung lượng hữu hạn theo mô hình Bloom chung, không thể yêu cầu **không false positive tuyệt đối**; cần cấu trúc chính xác hoặc thay đổi hợp đồng.
- **p=1**: Mục tiêu cho phép mọi khóa lạ nhận True, nên một bộ lọc có thể không có ích; không dùng công thức tối ưu ở ranh giới này như một thiết kế bình thường.
- **p rất gần 0**: m/h có thể lớn, chi phí băm/memory tăng; kiểm tra giới hạn số nguyên, thời gian và khả năng triển khai.
- **m quá nhỏ so với n**: h tối ưu thực có thể nhỏ hơn 1; chọn h≥1 nhưng FPR có thể rất cao.
- **Khóa trùng lặp**: n phải theo số khóa phân biệt, không tăng chỉ vì một khóa được add lại.
- **Hash/encoding không nhất quán**: lỗi membership có thể xảy ra dù các công thức sizing hoàn toàn đúng.


## 9. Python: tính m, h và FPR sau làm tròn

Đoạn mã sau chỉ **lập kế hoạch dung lượng**, chưa cấp phát m bit. Nó nhận số khóa phân biệt dự kiến n và FPR mục tiêu p, tính số bit lý tưởng, thử hai số vị trí băm nguyên gần tối ưu, rồi điều chỉnh số bit được căn chỉnh cho tới khi **FPR theo công thức xấp xỉ** không vượt p.

Dùng hàm **expm1** để đánh giá biểu thức \(1-e^{-x}\) ổn định hơn khi x nhỏ. Bộ tính tham số **không biến xác suất thực tế thành một bảo đảm tuyệt đối** nếu các giả định hash hoặc workload bị vi phạm.

~~~python
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class BloomPlan:
    expected_distinct: int
    target_fp: float
    bit_count: int
    hash_count: int
    estimated_fp: float
    byte_count: int
    bits_per_key: float


def approx_false_positive(n: int, m: int, h: int) -> float:
    """FPR xấp xỉ trong mô hình hash phân bố lý tưởng."""
    if n <= 0 or m <= 0 or h <= 0:
        raise ValueError("n, m, h phải dương")

    fraction_set = -math.expm1(-h * n / m)
    return fraction_set ** h


def best_hash_count(n: int, m: int) -> int:
    """Chọn ứng viên h nguyên gần h* = (m/n) ln 2."""
    if n <= 0 or m <= 0:
        raise ValueError("n và m phải dương")

    h_star = (m / n) * math.log(2.0)
    lower = max(1, math.floor(h_star))
    upper = max(1, math.ceil(h_star))

    return min(
        (lower, upper),
        key=lambda h: (approx_false_positive(n, m, h), h),
    )


def plan_bloom(
    expected_distinct: int,
    target_fp: float,
    align_bits: int = 8,
) -> BloomPlan:
    """Trả cấu hình với estimated_fp <= target_fp theo xấp xỉ."""
    if (
        isinstance(expected_distinct, bool)
        or not isinstance(expected_distinct, int)
        or expected_distinct <= 0
    ):
        raise ValueError("expected_distinct phải là int dương")

    if not math.isfinite(target_fp) or not (0.0 < target_fp < 1.0):
        raise ValueError("target_fp phải thuộc (0,1)")

    if (
        isinstance(align_bits, bool)
        or not isinstance(align_bits, int)
        or align_bits <= 0
    ):
        raise ValueError("align_bits phải là int dương")

    ln2 = math.log(2)
    ideal_bits = (
        -expected_distinct * math.log(target_fp) / (ln2 * ln2)
    )

    # Tính số khối, thay vì số bit, để căn chỉnh kích thước.
    upper_units = max(1, math.ceil(ideal_bits / align_bits))

    def evaluate(units: int):
        m = units * align_bits
        h = best_hash_count(expected_distinct, m)
        return h, approx_false_positive(expected_distinct, m, h)

    # Mở rộng ngưỡng trên nếu làm tròn h chưa đạt p mục tiêu.
    while evaluate(upper_units)[1] > target_fp:
        upper_units *= 2

    lower_units = 0

    # Nhị phân tìm số khối nhỏ nhất đạt p ước tính.
    while upper_units - lower_units > 1:
        mid = (lower_units + upper_units) // 2
        if evaluate(mid)[1] <= target_fp:
            upper_units = mid
        else:
            lower_units = mid

    m = upper_units * align_bits
    h, p_est = evaluate(upper_units)

    return BloomPlan(
        expected_distinct=expected_distinct,
        target_fp=target_fp,
        bit_count=m,
        hash_count=h,
        estimated_fp=p_est,
        byte_count=(m + 7) // 8,
        bits_per_key=m / expected_distinct,
    )


plan = plan_bloom(
    expected_distinct=1_000_000,
    target_fp=0.01,
    align_bits=64,
)

assert plan.bit_count % 64 == 0
assert plan.hash_count >= 1
assert plan.estimated_fp <= plan.target_fp
assert plan.byte_count == (plan.bit_count + 7) // 8

print("Số bit:", plan.bit_count)
print("Byte bitarray:", plan.byte_count)
print("MiB:", plan.byte_count / (1024 * 1024))
print("Số vị trí băm:", plan.hash_count)
print("FPR ước tính:", plan.estimated_fp)

looser = plan_bloom(100_000, 0.10)
stricter = plan_bloom(100_000, 0.001)
assert stricter.bit_count > looser.bit_count

smaller = plan_bloom(10_000, 0.01)
larger = plan_bloom(100_000, 0.01)
assert larger.bit_count > smaller.bit_count
~~~

### 9.1. Kết quả cần đọc theo đúng nghĩa

Bộ tính tham số báo **estimated_fp**, tức FPR dự báo theo công thức, chứ không trả bảo đảm trên mọi khóa/hàm hash.

Nó không cấp phát thực sự vùng m byte; khi triển khai còn phải kiểm tra **giới hạn bộ nhớ, seed, encoding, hash version, concurrency và thời điểm snapshot**.

### 9.2. Khi m cố định, tối ưu chỉ còn h

Nếu được cấp đúng **1 MiB mảng bit** và cần đại diện 1 triệu khóa, có thể gọi:

~~~python
n_plan = 1_000_000
m = 8 * 1024 * 1024

h = best_hash_count(n_plan, m)
p_est = approx_false_positive(n_plan, m, h)

print("h nguyên gần tối ưu:", h)
print("FPR ước tính với 1 MiB:", p_est)
~~~

Nếu p_est lớn hơn FPR yêu cầu, **bài toán không khả thi với ngân sách hiện tại trong mô hình Bloom chuẩn**. Không thể cứ tăng h tới một số thật lớn rồi hy vọng đạt p.

### 9.3. Chi phí của việc tính tham số

Lựa chọn h giữa hai ứng viên dùng số phép toán số học **hằng số**. Bộ tính plan_bloom dùng tìm kiếm nhị phân trên số khối căn chỉnh nên thực hiện khoảng **O(log(m/align_bits)) bước đánh giá** trong mô hình số máy cố định, không duyệt n khóa.

Nó là **công cụ thiết kế**, không phải phép đo hiệu quả trên dữ liệu thực. Khi n hoặc p cực đoan, giá trị float/log/exp có thể mất độ chính xác hay vượt giới hạn triển khai; phải xử lý giới hạn tài nguyên riêng trong sản phẩm.


## 10. Python: dùng kế hoạch để tạo Bloom filter

Ví dụ tiếp theo dùng lớp **BloomPlan** và hàm **plan_bloom** đã định nghĩa ở mục 9. Bộ lọc dùng SHA-256 với một tiền tố phiên bản và chỉ số vị trí để băm khóa str đã mã hóa UTF-8.

Đây là **mã minh họa giáo dục**: chưa được đánh giá cho môi trường bảo mật hoặc ghi song song, và các hash từ SHA-256 với tiền tố khác nhau không tự chứng minh tính độc lập hoàn hảo của mô hình FPR.

~~~python
import hashlib


class SimpleBloomFilter:
    def __init__(self, config: BloomPlan):
        self.config = config
        self.bits = bytearray(config.byte_count)

    def _positions(self, key: str):
        if not isinstance(key, str):
            raise TypeError("Ví dụ chỉ hỗ trợ khóa str")

        raw = key.encode("utf-8")
        m = self.config.bit_count

        for index in range(self.config.hash_count):
            digest = hashlib.sha256(
                b"bloom-sizing-v1|"
                + index.to_bytes(8, "big")
                + b"|"
                + raw
            ).digest()
            yield int.from_bytes(digest, "big") % m

    def add(self, key: str) -> None:
        for j in self._positions(key):
            self.bits[j // 8] |= 1 << (j % 8)

    def might_contain(self, key: str) -> bool:
        for j in self._positions(key):
            if (self.bits[j // 8] & (1 << (j % 8))) == 0:
                return False
        return True

    def occupancy(self) -> float:
        """Tỷ lệ bit logic được bật, không tính bit đệm cuối."""
        full_bytes, remaining_bits = divmod(
            self.config.bit_count, 8
        )

        ones = sum(
            self.bits[i].bit_count()
            for i in range(full_bytes)
        )

        if remaining_bits:
            valid_mask = (1 << remaining_bits) - 1
            ones += (
                self.bits[full_bytes] & valid_mask
            ).bit_count()

        return ones / self.config.bit_count


config = plan_bloom(
    expected_distinct=1000,
    target_fp=0.01,
)

bf = SimpleBloomFilter(config)
keys = [f"key:{i}" for i in range(1000)]

for key in keys:
    bf.add(key)

# Bất biến của Bloom chỉ-thêm: không âm tính giả cho khóa đã add.
assert all(bf.might_contain(key) for key in keys)
assert 0.0 <= bf.occupancy() <= 1.0

# Add cùng một khóa hai lần không tạo thêm bit.
snapshot = bytes(bf.bits)
bf.add("key:0")
assert bytes(bf.bits) == snapshot

# Một khóa lạ có thể là FP; không giả định nó luôn False.
unseen = bf.might_contain("not-inserted")
assert isinstance(unseen, bool)

print("Bit/khóa:", config.bits_per_key)
print("Hash/khóa:", config.hash_count)
print("Tỷ lệ bit 1 quan sát:", bf.occupancy())
~~~

### 10.1. Cách m và h được khóa vào trạng thái

Từ lúc add khóa đầu tiên, **m, h, thuật toán hash, seed/tiền tố, encoding và cách chuẩn hóa khóa phải ổn định**. Nếu đổi m, phép lấy modulo thay đổi; nếu đổi h, tập vị trí băm có thể đổi; nếu đổi seed/hash, vị trí cũ không còn trùng.

Không được lấy một mảng bit đã có dữ liệu rồi đơn giản “nâng n dự kiến” bằng cách thay m/h. Muốn đổi dung lượng phải **xây lại từ nguồn khóa chính xác**, hoặc thiết kế nhiều filter/lớp với cấu hình riêng bất biến.

### 10.2. Tỷ lệ bit 1 quan sát và chi phí đo

Hàm occupancy quét mọi byte được cấp phát, nên tốn khoảng **O(m/8)** phép đọc byte, không phải O(h). Đây là phép đo hữu ích theo chu kỳ, nhưng không nên gọi trên **mỗi request** khi bit array lớn.

Hàm này đếm đúng **m bit logic**, không đếm nhầm các bit đệm nếu m không chia hết cho 8. Nếu dùng một bộ đếm số bit 1 được cập nhật thường xuyên để tránh quét, phải đồng bộ cả bộ đếm với bit array và xử lý trường hợp hai khóa cố bật cùng một bit.

### 10.3. Độ phức tạp add/query

Mỗi lần add hoặc might_contain cần nhiều nhất **h** phép băm và cập nhật/đọc bit.

- Với phép băm khóa O(1), add và query có chi phí **O(h)**.
- Với h là hằng số cố định, có thể nói **O(1) theo số khóa n**.
- Với khóa dài L byte và mỗi hash quét toàn bộ khóa, chi phí có thể **O(hL)**.
- Bộ nhớ của mảng là **Θ(m) bit**, chưa tính metadata và vùng nhớ tạm cho băm.

Nói “Bloom là O(1)” mà bỏ qua h có thể đánh giá sai chi phí khi giảm FPR từ 10% xuống 0,01%: số vị trí băm gần tối ưu có thể tăng từ khoảng **3 lên 13**.

## 11. Dung lượng thực tế vượt dự báo: điều gì xảy ra?

Giả sử bộ lọc được thiết kế cho n_plan khóa với m và h **cố định**. Khi thực tế có n_actual khóa phân biệt, công thức FPR dự báo phải dùng **n_actual**:

\[
\boxed{
p_{\mathrm{actual,est}}\approx
(1-e^{-hn_{\mathrm{actual}}/m})^h.
}
\]

Đây vẫn là xấp xỉ theo mô hình hash lý tưởng, nhưng mô tả rõ **sự suy giảm khi mảng bit ngày càng đầy**.

### 11.1. Bảng khi tải bằng một phần hoặc nhiều lần dự báo

Giả sử m≈9,585 bit/khóa theo kế hoạch, **h=7 được giữ nguyên**, p_plan≈1%.

| n thực / n kế hoạch | Bit trên khóa thực | Tỷ lệ bit 1 dự báo | FPR dự báo |
| ---: | ---: | ---: | ---: |
| 0,5× | 19,17 | 30,6% | **0,025%** |
| 1× | 9,59 | 51,8% | **1,00%** |
| 1,5× | 6,39 | 66,6% | **5,79%** |
| 2× | 4,79 | 76,8% | **15,75%** |
| 3× | 3,20 | 88,8% | **43,60%** |

Bảng tính với **m/h giữ nguyên**; đó không phải các filter mới được cấp lại RAM và tái tối ưu h cho mỗi n_actual.

Đặc biệt, khi số khóa thực tăng **gấp đôi**, FPR có thể tăng từ khoảng **1% lên 15,75%**. Bộ lọc vẫn có thể trả False chính xác một phía, nhưng một phần lớn truy vấn âm tính sẽ đi tới nguồn xác minh.

### 11.2. Vì sao tăng nhanh trước khi bit array đầy?

Khi \(q\) là tỷ lệ bit 1, FPR gần \(q^h\).

- q≈0,50, h=7 → FP khoảng 0,8%.
- q≈0,75, h=7 → FP khoảng 13,3%.
- q≈0,90, h=7 → FP khoảng 47,8%.

Chỉ cần bit đã bật tăng từ khoảng 50% lên 75%, FPR tăng rất mạnh vì xác suất **tất cả h vị trí đều trúng bit 1** tăng theo lũy thừa.

### 11.3. Không tự giảm h khi số khóa tăng

Nếu n_actual tăng gấp đôi, công thức h_opt=(m/n_actual)ln2 có thể gợi ý dùng **ít hash hơn**. Nhưng một bộ lọc đã add với h_old không thể tự đổi sang h_new và mong cùng tập khóa vẫn tra chính xác, vì lúc add các bit chỉ được bật theo cấu hình cũ.

Muốn thay h hoặc m phải **tái xây** hay dùng một lớp mới. Không được chỉ đổi hai con số trong metadata của mảng bit cũ.

### 11.4. Nếu thực tế có ít khóa hơn dự kiến

Khi n_actual nhỏ hơn n_plan, filter thường có FPR thấp hơn, nhưng RAM đã được dành sẵn. Dự báo quá cao giúp tránh thiếu dung lượng song có thể lãng phí bộ nhớ; với nhiều phân vùng kích thước khác nhau, hãy cân nhắc **cấp phát riêng theo n của từng phân vùng**.

### 11.5. Dung lượng dự kiến không phải giới hạn cứng của add

Bloom chuẩn không có thông báo “đầy” khi đạt đúng n_plan, vì mảng bit đã được cấp phát sẵn và mỗi add chỉ bật bit. **n_plan là mức tải dùng trong dự báo xác suất**, không phải số ô phần tử có thể giữ theo nghĩa của mảng hoặc hash table.

Khi gần toàn bit 1, add vẫn hợp lệ, không FN trong mô hình chuẩn nhưng filter gần như **trả True cho mọi khóa lạ**.


## 12. Đặt ngân sách FPR theo chi phí kinh doanh và workload

Không có một mức p tốt nhất cho mọi hệ thống. Cấu hình p nên được chọn từ **chi phí một dương tính giả, số truy vấn âm tính, RAM và CPU**.

### 12.1. Tính số lượt tra nguồn chính xác còn lại

Đặt:

- **Q**: số truy vấn membership trong một khoảng thời gian.
- **α**: tỷ lệ truy vấn hỏi khóa **thực sự có** trong tập đã biểu diễn.
- **1−α**: tỷ lệ truy vấn hỏi khóa **thực sự không có**.
- **p**: FPR của Bloom trên truy vấn thực sự âm tính.

Nếu mỗi True được xác minh chính xác và mỗi False được loại an toàn nhờ tập nguồn đã được bao phủ, thì số lượt tra nguồn chính xác kỳ vọng:

\[
\boxed{
E[\text{lookup chính xác}]=Q[\alpha+(1-\alpha)p].
}
\]

Số lượt lookup được tránh:

\[
\boxed{
E[\text{lookup tiết kiệm}]=Q(1-\alpha)(1-p).
}
\]

Công thức này là **kỳ vọng theo mô hình workload**, không phải số lượt chắc chắn cho mọi chuỗi truy vấn. Nó cũng giả định các truy vấn hiện diện thật luôn trả True và không có mất cập nhật.

### 12.2. Ví dụ giảm p từ 1% xuống 0,1%

Giả sử:

~~~text
Q = 10 000 000 truy vấn/ngày
α = 0,10      (10% truy vấn khóa thực sự có)
1-α = 0,90    (90% truy vấn khóa thực sự không có)
n_plan = 1 000 000 khóa phân biệt.
~~~

| Kịch bản | Lookup của khóa thật có | Lookup FP kỳ vọng | Tổng lookup nguồn chính xác |
| --- | ---: | ---: | ---: |
| Không Bloom | — | — | 10.000.000 |
| Bloom p=1% | 1.000.000 | 90.000 | 1.090.000 |
| Bloom p=0,1% | 1.000.000 | 9.000 | 1.009.000 |

Giảm p từ 1% xuống 0,1% tiết kiệm thêm khoảng **81.000 lượt tra nguồn mỗi ngày** trong mô hình này.

Nhưng với một triệu khóa, mức 0,1% cần **khoảng 0,57 MiB mảng bit bổ sung** so với 1%, và số vị trí băm gần tối ưu tăng từ **7 lên 10**. Tức là cả **10 triệu truy vấn** phải xử lý nhiều phép băm/bit hơn, không chỉ 81.000 trường hợp tiết kiệm được.

**Không thể kết luận phương án nào nhanh hơn** nếu chưa biết độ trễ/chi phí của lookup nguồn, hash, cache, bộ nhớ và tỷ lệ truy vấn thực tế.

### 12.3. Chi phí tổng quát nên đo những gì?

Một mô hình chi phí sơ bộ:

\[
\begin{aligned}
C_{\mathrm{total}}\approx&
\ C_{\mathrm{RAM}}(m)\\
&+Q\,C_{\mathrm{Bloom}}(h,L)\\
&+Q[\alpha+(1-\alpha)p]C_{\mathrm{source}}\\
&+C_{\mathrm{build/update/rebuild}}.
\end{aligned}
\]

Trong đó:

- \(C_{\mathrm{Bloom}}\) tăng theo số vị trí băm và độ dài khóa L, nhưng còn phụ thuộc cache locality.
- \(C_{\mathrm{source}}\) có thể là truy vấn bộ nhớ, I/O đĩa hoặc RPC, khác nhau rất lớn.
- \(C_{\mathrm{RAM}}\) không chỉ là giá một byte: có giới hạn memory, cache, số phân vùng và số replica.
- **Rebuild** có thể tốn I/O, CPU và cần song song tồn tại hai phiên bản filter.

Không nên tối ưu một biến đơn lẻ mà bỏ qua chi phí đầu-cuối.

### 12.4. Tại sao tỷ lệ khóa thật có quan trọng?

Nếu α gần **1**, phần lớn query trả True đúng và vẫn phải truy vấn nguồn chính xác. Bloom có thể mang lại ít lợi ích, dù p rất thấp.

Nếu α nhỏ và nguồn chính xác đắt, Bloom giúp loại rất nhiều âm tính thật. Tuy nhiên, workload có các khóa lạ lặp lại quá nhiều có thể khiến số FP quan sát được khác kỳ vọng trên khóa âm tính ngẫu nhiên.

### 12.5. Hệ quả của false positive phải được định nghĩa trước

Trong một pipeline đúng:

~~~text
Bloom True → kiểm chứng bằng nguồn chính xác
Bloom False → loại khi đã chứng minh filter bao phủ tập nguồn
~~~

FP thường chỉ gây **chi phí lookup bổ sung**. Nếu ứng dụng **tự bỏ một sự kiện mới khi Bloom True**, FP có thể gây **mất dữ liệu**. Nếu Bloom True dùng làm bằng chứng thanh toán/cấp quyền, FP có thể tạo kết luận sai nghiêm trọng. Với các trường hợp ấy, tăng m để p rất nhỏ **không thay thế bước xác minh**.

## 13. Khi số khóa tiếp tục tăng: tái xây, phân vùng hay nhiều lớp?

### 13.1. Tái xây từ một nguồn khóa chính xác

Khi n_actual vượt n_plan và FPR tăng, cách trực tiếp là:

1. Xác định **snapshot/tập khóa có thẩm quyền**.
2. Ước lượng số khóa phân biệt mới n_new.
3. Chọn p_target và n_plan mới, tính m/h mới.
4. Xây bộ lọc mới bằng cách **add lại toàn bộ khóa** của snapshot ấy.
5. Xuất bản phiên bản mới với cùng version dữ liệu, xử lý chênh lệch/delta trong thời gian xây.
6. Chỉ bỏ filter cũ khi mọi truy vấn đã chuyển theo đúng hợp đồng snapshot.

Vì Bloom **không lưu danh sách khóa**, không thể lấy bit array của filter cũ để khôi phục chính xác tất cả khóa rồi add lại vào một filter mới. Cần **nguồn danh tính khóa** riêng.

### 13.2. Scalable Bloom filter gồm nhiều lớp

Một lựa chọn khác là tạo filter mới khi lớp cũ đạt ngưỡng dung lượng:

~~~text
Lớp 0: m0, h0, n0_plan
Lớp 1: m1, h1, n1_plan
Lớp 2: m2, h2, n2_plan
...
~~~

Mỗi lớp **giữ nguyên cấu hình đã dùng khi add**. Query trả **True nếu bất kỳ lớp nào True**, và trả **False khi mọi lớp đều False**.

Bảo đảm không FN được giữ nếu mọi khóa đã add thành công vào **ít nhất một lớp**, mọi lớp dùng đúng hash của mình và quá trình cập nhật không mất bit.

### 13.3. Phân bổ ngân sách FPR cho nhiều lớp

Giả sử có L lớp và mỗi lớp có FPR p_i đối với một khóa thật sự vắng mặt trên mọi lớp.

Theo union bound:

\[
P(\mathrm{FP\ ở\ ít\ nhất\ một\ lớp})
\le\sum_{i=1}^{L}p_i.
\]

Không cần các lớp độc lập để dùng cận trên. Nếu các sự kiện độc lập phù hợp, có thể xấp xỉ:

\[
p_{\mathrm{total}}\approx1-\prod_{i=1}^{L}(1-p_i).
\]

**Không thể tạo mười lớp, mỗi lớp p_i=1%, rồi tuyên bố cả hệ thống vẫn 1%.** Một thiết kế scalable phải **phân ngân sách sai số** cho các lớp và quản lý dung lượng n_i của từng lớp.

Ví dụ muốn tổng FP không quá gần 1% theo union bound, có thể phân cho ba lớp p_0=0,5%, p_1=0,3%, p_2=0,2% (tổng 1%). Đây chỉ là ví dụ phân bổ, không chứng minh tối ưu bộ nhớ; lựa chọn thực tế còn phụ thuộc tăng trưởng, kích cỡ và số lớp.

### 13.4. Phân vùng giúp kiểm soát vòng đời

Nếu dữ liệu được chia theo SSTable, tenant hoặc ngày, có thể dùng một Bloom theo phân vùng và **chỉ query những phân vùng liên quan**.

Một Bloom của một SSTable bất biến có thể xây đúng số khóa của SSTable, rồi bỏ cùng SSTable khi nó không còn tồn tại. Nhưng Bloom của SSTable A trả False **không kết luận khóa vắng trong toàn database**, vì khóa có thể ở SSTable B hoặc memtable.

Nếu một truy vấn phải hỏi tất cả phân vùng, phải tính cả **số lần truy vấn Bloom và tổng xác suất FP** của cách kết hợp.

### 13.5. Hợp nhất hai Bloom bằng OR: điều kiện và chi phí

Nếu hai Bloom có:

- Cùng m, h, thuật toán băm/seed và phiên bản.
- Cùng mã hóa/chuẩn hóa khóa.
- Cùng ý nghĩa tập/snapshot phù hợp.

thì có thể **OR từng bit** để biểu diễn hợp của hai tập được mã hóa. OR không tắt bit, nên không FN đối với khóa đã add trong từng filter, nhưng số bit 1 **tăng hoặc giữ nguyên**, khiến FPR có thể tăng.

Không được OR nếu các hash/seed khác nhau, dù mảng có cùng số byte. Không thể lấy **n_A+n_B** làm số khóa phân biệt của hợp nếu hai tập có khóa trùng nhau.

### 13.6. Hết hạn/xóa dữ liệu không giống tự động giảm n

Bloom chuẩn **không có delete an toàn**. Nếu set hiện hành giảm số khóa do hết hạn, Bloom cũ vẫn giữ những bit được bật bởi các khóa đã hết hạn. FPR không tự giảm theo số khóa còn sống.

Các lựa chọn gồm tái xây, bỏ nguyên phân vùng hết hạn hoặc dùng biến thể có xóa với hợp đồng phù hợp như counting Bloom. **Tắt bit tùy ý** có thể gây âm tính giả cho khóa khác vì vị trí băm được chia sẻ.

## 14. Vận hành và kiểm chứng tham số đã chọn

### 14.1. Giám sát đúng đại lượng

Một dashboard vận hành có thể theo dõi:

| Chỉ số | Ý nghĩa | Dấu hiệu đáng chú ý |
| --- | --- | --- |
| n_plan | Số khóa phân biệt đã dùng để định cỡ | Không còn phản ánh vòng đời |
| n_actual / distinct estimate | Số khóa thực hoặc ước lượng distinct | Vượt xa n_plan |
| m, h | Cấu hình được lưu và công bố | Có version khác nhau giữa máy |
| Tỷ lệ bit 1 | Độ bão hòa quan sát được | Tăng nhanh, gần 100% |
| FPR đo trên negative | Tỷ lệ dương tính giả thực tế | Cao hơn mức cho phép |
| Lookup chính xác sau Bloom | Chi phí nhánh True | Tăng theo FP hoặc số query thật có |
| Latency add/query | CPU, cache, I/O | Hash quá nhiều hoặc filter không cục bộ |
| Dung lượng thực tế | Bit array + metadata + các phiên bản song song | Vượt hạn RAM |
| Tuổi snapshot / độ trễ đồng bộ | Phạm vi tính đúng của False | Filter lạc hậu so với nguồn |

**Tỷ lệ bit 1 không phải FPR đo được**, dù có công thức xấp xỉ \(p\approx q^h\). FPR thực cần khóa âm tính có nhãn sự thật, tốt nhất phù hợp workload.

### 14.2. Đo FPR đúng tập âm tính

Để đánh giá, cần:

- Tập **positive** đã add hoàn tất (mọi query phải trả True nếu trạng thái ổn định).
- Tập **negative** được biết chắc chưa add.
- Cấu hình m/h, hash version, số khóa, snapshot và cách chọn mẫu.

Tính:

\[
\widehat{\mathrm{FPR}}=
\frac{\#\{x\in N_{\mathrm{neg}}:\mathrm{mightContain}(x)\}}{|N_{\mathrm{neg}}|}.
\]

Không được chia số FP cho tổng truy vấn bao gồm positive rồi gọi đó là FPR. Không nên lặp **cùng một khóa lạ** 10.000 lần để ước lượng FPR theo phân bố khóa khác: với filter cố định, cùng khóa thường tạo cùng kết quả.

### 14.3. Mã minh họa đo trên tập negative có nhãn

Đoạn sau sử dụng lớp **SimpleBloomFilter** đã định nghĩa ở mục 10. Các khóa negative được sinh với tiền tố khác để tách khỏi positive trong ví dụ. Đây là phép đo minh họa, **không phải chứng minh FPR cho mọi workload**.

~~~python
config = plan_bloom(1000, 0.01)
bf = SimpleBloomFilter(config)

positives = [f"positive:{i}" for i in range(1000)]
negatives = [f"negative:{i}" for i in range(10000)]

for key in positives:
    bf.add(key)

false_negatives = [
    key for key in positives
    if not bf.might_contain(key)
]
assert false_negatives == []

fp_count = sum(
    1 for key in negatives
    if bf.might_contain(key)
)
fpr_observed = fp_count / len(negatives)

assert 0.0 <= fpr_observed <= 1.0
print("FPR quan sát:", fpr_observed)
print("FPR theo mô hình:", config.estimated_fp)
print("Tỷ lệ bit 1:", bf.occupancy())
~~~

Nếu FPR quan sát là 1,1% với p_target=1%, **chưa đủ để kết luận thuật toán sai**. Cần xét kích thước mẫu, phân bố hash, số khóa đã add và độ lệch thống kê. Nhưng nếu một khóa đã add thành công trả False trên trạng thái nhất quán, đó là **lỗi vi phạm bất biến**, không phải FP thông thường.

### 14.4. Kiểm tra phiên bản và tính nhất quán

Sizing đúng không bù được việc **hash không giống nhau giữa insert/query**. Nếu thay m, h, seed, Unicode normalization hoặc version hash mà không tái xây, khóa đã add có thể trở thành **âm tính giả**.

Trong hệ thống ghi/đọc đồng thời, add chưa hoàn tất hoặc cập nhật bit không nguyên tử có thể làm query thấy thiếu vị trí. Bộ lọc dùng làm prefilter cho database cần có **giao thức snapshot/delta** để bảo đảm mọi khóa thực sự có trong phạm vi đọc đã được mã hóa đầy đủ.

### 14.5. Không dùng FPR mục tiêu như bảo đảm an ninh

Một kẻ tấn công có thể thử nhiều khóa để tìm false positive. Công thức FPR với hash phân bố lý tưởng và truy vấn đại diện không tự là bảo đảm với **truy vấn thích nghi**.

Không được dùng Bloom True làm chứng chỉ thanh toán, xác thực hoặc cấp quyền. Khi cần quyết định tuyệt đối đúng, phải xác minh bằng nguồn có thẩm quyền, bất kể p_target nhỏ thế nào.

## 15. Một bản thiết kế mẫu từ đầu đến cuối

**Bài toán:** Dịch vụ tra cứu một tập ID phân biệt lưu tại nguồn chính xác. Trong vòng đời một phiên bản filter, dự báo **1.000.000 ID**; hệ thống có khoảng **10 triệu truy vấn/ngày**, 90% truy vấn hỏi ID không tồn tại. Yêu cầu FPR mục tiêu **0,1%**, bộ nhớ RAM cho bit array được cấp đủ và nguồn chính xác có chi phí tra cứu đáng kể.

### 15.1. Tính m/h

~~~text
n_plan = 1 000 000 khóa phân biệt
p_target = 0,001

b ≈ -ln(0,001)/(ln2)^2
  ≈ 14,38 bit/khóa

m ≈ 14,38 triệu bit
  ≈ 1,71 MiB vùng bit

h ≈ b ln2 ≈ 9,97
  → thử 10 hash, kiểm tra lại p ước tính sau làm tròn.
~~~

Nếu muốn dự trữ tăng trưởng, **chọn n_plan lớn hơn trước khi tính m**. Không thể chỉ thêm 20% “dung lượng n” vào metadata sau khi đã cấp phát.

### 15.2. Tính lợi ích tra nguồn chính xác

Với α=0,10, Q=10 triệu và p=0,001:

\[
E[\text{lookup}]
=10.000.000[0,10+0,90\times0,001]
=1.009.000.
\]

So với 10 triệu lookup không dùng Bloom, mô hình dự báo có thể tránh **8.991.000 lượt/ngày**, nhưng mọi truy vấn đều phải tính khoảng h=10 vị trí băm và bộ lọc cần được cập nhật nhất quán.

### 15.3. Chọn quy trình dữ liệu

- Xây Bloom từ **snapshot khóa có thẩm quyền** và lưu m/h/hash version/encoding cùng version dữ liệu.
- Tại thời điểm công bố, chỉ dùng False để loại những khóa trong **phạm vi snapshot được filter bao phủ**.
- Nếu ID mới được thêm, phải có quy trình **delta** hoặc thay phiên bản filter trước khi tin False cho dữ liệu mới.
- Nếu Bloom True, tiếp tục tra nguồn chính xác.
- Theo dõi số ID phân biệt, tỷ lệ bit 1, FPR trên negative, latency và số lookup thực sự tiết kiệm.
- Nếu n tăng vượt dự báo đáng kể, **tái xây hoặc chuyển lớp** có ngân sách lỗi riêng.

### 15.4. Điều kiện để tuyên bố thành công

Một phương án không nên chỉ báo “m=1,71 MiB; h=10; FPR 0,1%” rồi kết thúc. Cần đối chiếu **RAM thực dùng, CPU hash, độ trễ cuối, tỉ lệ FP quan sát, bảo đảm no-FN của filter và độ bao phủ nhất quán của database**.

Nếu chi phí cập nhật/đồng bộ lớn hơn lợi ích tránh lookup, dùng set/index chính xác trực tiếp có thể đơn giản và tốt hơn.


## 16. Những lỗi thường gặp khi chọn bit, hash và dung lượng

| Sai lầm | Hậu quả hoặc lý do sai | Cách làm đúng |
| --- | --- | --- |
| Dùng số request thay cho số khóa phân biệt n | Cấp phát quá nhiều hoặc hiểu sai tỷ lệ bit/khóa | Ước lượng **distinct keys trong vòng đời** |
| Chỉ tính n của ngày đầu tiên | FPR tăng khi khóa tích lũy qua thời gian | Tính cả **vòng đời, growth và headroom** |
| Quên rằng Bloom chuẩn không xóa khóa | Khóa đã hết hạn vẫn để lại bit 1 | Tái xây/phân vùng hoặc biến thể phù hợp |
| Dùng p=0 trong công thức m | Log(0) không xác định, cần vô hạn bit theo mô hình chung | Dùng cấu trúc membership chính xác |
| Dùng p=1 như mục tiêu tối ưu hữu ích | Không cần khả năng lọc âm tính | Xem lại yêu cầu chức năng |
| Lấy log thập phân thay log tự nhiên mà không đổi công thức | Tính sai m/h | Dùng **ln** hoặc biến đổi đúng cơ số |
| Quên bình phương trong (ln2)² | Sai số bit/khóa | Dùng đúng mẫu số **(ln2)²** |
| Đổi h thành m/n mà quên nhân ln2 | Dùng quá nhiều hash | h≈(m/n)ln2 |
| Cho rằng càng nhiều hash càng tốt | Bão hòa bit và tăng CPU | Tìm h gần tối ưu và đo hiệu năng |
| Làm tròn h nhưng không tính lại p_est | FPR dự báo có thể vượt p_target | Tính lại với m/h nguyên |
| Chỉ làm tròn m xuống | Có thể thiếu bit cần thiết | Làm tròn lên và kiểm tra p_est |
| Dùng m=1.000.000 **byte** khi công thức cho m=1.000.000 **bit** | Lệch bộ nhớ gấp 8 | Ghi rõ bit/byte trong bảng kế hoạch |
| Nhầm MB với MiB | Sai số về dung lượng cấp phát | **1 MiB=1.048.576 byte** |
| Đếm bit đệm cuối byte vào m logic mà không thống nhất modulo | Kết quả toán/định dạng bị lệch | Phân biệt m logic và byte vật lý |
| Chỉ nhân m của một filter, bỏ metadata/replica | Vượt ngân sách RAM thực tế | Tính mọi phiên bản, phân vùng, object |
| Nói filter có đúng n “ô chứa khóa” | Bloom không lưu từng khóa trong ô | n là **mức tải dùng để thiết kế FPR** |
| Đổi m sau khi đã add khóa, giữ bit cũ | Hash modulo m mới có thể gây âm tính giả | Tái xây hoặc dùng lớp mới |
| Đổi h/hash/seed khi vẫn dùng mảng bit cũ | Query không khớp vị trí insert | Lưu cấu hình/version bất biến |
| Dùng hash phân bố kém rồi tin p theo công thức lý tưởng | FPR thực cao bất thường | Đánh giá họ hash và workload |
| Cho rằng hash của process luôn ổn định sau restart | Khóa có thể băm vị trí mới | Lưu hash version/seed và encoding |
| Tính n bằng số lần add cùng một khóa | Ước lượng bão hòa quá cao | Tính theo **khóa phân biệt** |
| Sau khi n tăng, giảm h ngay mà không tái xây | Khóa cũ không có đủ các bit mới | Không sửa cấu hình khi đã có dữ liệu |
| Coi bitarray gần đầy là có false negative | Bão hòa làm FP tăng, không tự sinh FN | Phân biệt sai số một phía |
| Xóa khóa bằng cách reset bit | Có thể tắt bit của khóa khác | Không xóa trực tiếp trong Bloom bit |
| OR hai filter khác seed/encoding | Bit không có cùng ngữ nghĩa | Chỉ merge cấu hình tương thích |
| Giữ p_i của nhiều lớp bằng p_total | Tổng FPR có thể tăng theo số lớp | Phân bổ ngân sách lỗi tổng |
| Chỉ tính p và RAM, bỏ CPU h lần băm | Độ trễ có thể tăng dù bớt truy vấn DB | Đo CPU/latency đầu-cuối |
| Đếm bit 1 trên mỗi request | Phải quét toàn bộ mảng, O(m/8) byte | Đo theo chu kỳ |
| Đo FPR trên mọi request gồm positive | Sai mẫu số | Chỉ dùng **negative thật** |
| Hỏi lại cùng một khóa lạ 10.000 lần để đo FPR | Không đại diện phân bố khóa âm tính | Lấy mẫu các khóa negative đa dạng |
| Đo được FPR 1,1% rồi kết luận chắc chắn lỗi | Mẫu có biến động, hash/workload khác mô hình | Xem confidence, n và phân bố mẫu |
| Bloom False của snapshot cũ được dùng trên DB mới | Có thể loại nhầm khóa chưa được mã hóa | Snapshot/delta/đồng bộ version |
| Bloom True dùng làm bằng chứng cấp quyền | FP có thể cấp quyền sai | Xác minh với nguồn có thẩm quyền |

### 16.1. Checklist trước khi đưa cấu hình vào ứng dụng

Một bản thiết kế đủ tốt nên trả lời rõ:

1. **Câu hỏi membership** là gì; tập khóa nào được biểu diễn?
2. **n_plan** được suy ra từ đâu, có gồm tăng trưởng và retention không?
3. **p_target** được chọn vì chi phí FP nào?
4. **m, h nguyên** sau làm tròn/căn chỉnh là bao nhiêu?
5. **p_est** sau làm tròn có đáp ứng mục tiêu theo mô hình không?
6. Dung lượng **bitarray thực**, metadata, số replica/filter cùng tồn tại là bao nhiêu?
7. Số hash thực hiện trên mỗi query có được ngân sách CPU cho phép không?
8. Hash/seed/encoding/version có giữ nguyên khi lưu/khôi phục không?
9. Nếu n_actual vượt n_plan, ngưỡng tái xây hoặc tạo lớp mới là gì?
10. Nhánh False có **được phép tin** theo hợp đồng nhất quán với dữ liệu nguồn không?
11. Nhánh True có cần **xác minh chính xác** hay không?
12. Những chỉ số nào sẽ được giám sát để kiểm chứng FPR/độ trễ trong thực tế?

Nếu câu trả lời chỉ có **“đặt p=1% và dùng 7 hash”**, thiết kế vẫn thiếu phần lớn bối cảnh quan trọng.


## 17. Bài tập tự luyện có đáp án

### Nhóm A — Hiểu tham số và công thức

**Bài 1 — Định nghĩa n.** Một Bloom filter nhận một triệu lượt add nhưng chỉ có 50.000 khóa phân biệt. Trong công thức tính dung lượng, n nên lấy gần với số nào?

*Đáp án:* **50.000 khóa phân biệt**, theo phạm vi tập được biểu diễn. Add trùng khóa chỉ bật lại các bit cũ.

**Bài 2 — Định nghĩa m.** m=8.000.000 nghĩa là 8 triệu bit hay 8 triệu byte?

*Đáp án:* **8 triệu bit**, tức khoảng **1 triệu byte** cho vùng bit. Không được nhầm đơn vị.

**Bài 3 — Định nghĩa h.** Nếu h=7, một thao tác add phải làm gì?

*Đáp án:* Tính **7 vị trí băm** và bật tất cả bit tương ứng (một số vị trí có thể trùng); query kiểm tra tất cả vị trí đó.

**Bài 4 — Định nghĩa p.** FPR mục tiêu p=0,01 nói về nhóm truy vấn nào?

*Đáp án:* Các truy vấn **thực sự hỏi khóa chưa add**, theo mô hình hàm băm/phân bố truy vấn. Không phải 1% mọi request.

**Bài 5 — Bất biến.** Bloom chỉ-thêm, hash không đổi và cập nhật hoàn tất có được trả False cho một khóa đã add thành công không?

*Đáp án:* **Không**; mọi bit của khóa đã add đều bằng 1 và không bị tắt.

**Bài 6 — FP.** Một khóa chưa add được Bloom trả True vì tất cả h bit đã do khóa khác bật. Đây là loại kết quả nào?

*Đáp án:* **False positive**, được phép trong Bloom chuẩn.

**Bài 7 — Xác suất bit 0.** Với m bit, n khóa và h vị trí băm mỗi khóa, công thức gần đúng cho xác suất một bit chưa bật là gì?

*Đáp án:* \(e^{-hn/m}\) trong mô hình hash lý tưởng; biểu thức dạng lũy thừa là \((1-1/m)^{hn}\).

**Bài 8 — Tỷ lệ bit 1.** Viết công thức gần đúng cho tỷ lệ bit 1 sau khi thêm n khóa.

*Đáp án:* **q≈1−e^(−hn/m)**.

**Bài 9 — FPR.** Công thức xấp xỉ FPR là gì?

*Đáp án:* \(p_{\rm FP}\approx(1-e^{-hn/m})^h\).

**Bài 10 — h tối ưu.** Nếu đã biết m và n, nên chọn h gần bao nhiêu?

*Đáp án:* **h≈(m/n)ln2**, rồi thử các số nguyên gần nhất và tính lại FPR dự báo.

### Nhóm B — Tính toán bộ nhớ, số hash và dung lượng

**Bài 11 — 100.000 khóa.** Với n=100.000 và FPR mục tiêu 1%, cần khoảng bao nhiêu bit và hash?

*Đáp án:* \(m\approx958.506\) bit, khoảng **117 KiB** mảng bit, **h≈7**.

**Bài 12 — Một triệu khóa.** Với n=1.000.000 và p=1%, dung lượng mảng bit xấp xỉ là bao nhiêu?

*Đáp án:* Khoảng **9,585 triệu bit**, tương ứng **1,14 MiB**, h gần **7**.

**Bài 13 — FPR 0,1%.** Với n=1.000.000 và p=0,001, cần khoảng bao nhiêu bit/khóa và hash?

*Đáp án:* Khoảng **14,38 bit/khóa**, tổng **14,38 triệu bit ≈1,71 MiB**, **h≈10**.

**Bài 14 — FPR 10%.** Với n=1.000.000 và p=0,10, m và h gần bao nhiêu?

*Đáp án:* Khoảng **4,79 triệu bit ≈0,57 MiB**, **h≈3**.

**Bài 15 — FPR 0,01%.** Với n=1.000.000, p=0,0001, số bit/khóa và số hash gần đúng là gì?

*Đáp án:* Khoảng **19,17 bit/khóa**, **2,29 MiB mảng bit**, **h≈13**.

**Bài 16 — Ngân sách 1 MiB.** Một filter chỉ được dùng 1 MiB vùng bit, mục tiêu FPR khoảng 1%. Theo công thức tối ưu gần đúng, n_max là bao nhiêu?

*Đáp án:* m=8.388.608 bit, chia khoảng **9,585 bit/khóa** → **khoảng 875.000 khóa phân biệt**, trước khi trừ metadata/headroom.

**Bài 17 — 1001 bit.** Nếu m_logic=1001, cần bao nhiêu byte để lưu các bit và còn bao nhiêu bit đệm?

*Đáp án:* **ceil(1001/8)=126 byte**, vật lý 1008 bit, **7 bit đệm** nếu vẫn giữ m_logic=1001.

**Bài 18 — Căn chỉnh 64 bit.** Nếu m_required=1001 và muốn cấp phát số bit logic là bội 64, chọn m_aligned bao nhiêu?

*Đáp án:* \(64\lceil1001/64\rceil=1024\) bit, tức **128 byte**; phải băm modulo m mới nếu đây là một filter mới.

**Bài 19 — 10 bit/khóa.** Với m/n=10, h gần tối ưu là bao nhiêu?

*Đáp án:* \(10\ln2\approx6,93\), chọn **h=7**.

**Bài 20 — 8 bit/khóa.** Nếu m/n=8 và được tự chọn h tối ưu, FPR tối thiểu gần đúng theo mô hình là bao nhiêu?

*Đáp án:* \(p_{\min}\approx e^{-8(\ln2)^2}\approx0,0214\), tức **2,14%**. Hash nguyên cần được kiểm tra lại.


**Bài 21 — h từ p.** Với FPR mục tiêu p=1% và m định cỡ gần tối ưu, h thực gần bao nhiêu?

*Đáp án:* \(\log_2(100)\approx6,64\). Nên thử **h=6 và h=7**, thường chọn 7 sau khi đánh giá FPR với m nguyên.

**Bài 22 — Giảm FPR mười lần.** Nếu giảm p từ 1% xuống 0,1%, mỗi khóa cần thêm khoảng bao nhiêu bit trong mô hình tối ưu?

*Đáp án:* Thêm \(\ln10/(\ln2)^2\approx4,79\) **bit/khóa**. Với một triệu khóa, tương đương khoảng **0,57 MiB vùng bit** bổ sung.

**Bài 23 — Vượt tải 1,5 lần.** Filter n_plan=1 triệu, m≈9,585 triệu bit, h=7. Nếu n_actual=1,5 triệu, FPR dự báo gần bao nhiêu?

*Đáp án:* \((1-e^{-7(1,5)/9,585})^7\approx0,0579\), tức **5,79%**. h vẫn là 7 của filter đã triển khai.

**Bài 24 — Tỷ lệ bit 1.** Nếu q=0,5 và h=7, công thức q^h cho FPR bằng bao nhiêu?

*Đáp án:* \(0,5^7=1/128=0,0078125\), tức **0,78125%**.

**Bài 25 — Đòi chính xác tuyệt đối.** Nghiệp vụ yêu cầu không false positive với mọi khóa. Có thể đặt p=0 vào công thức m không?

*Đáp án:* **Không**. Mô hình Bloom tổng quát không đạt FPR 0 với dung lượng hữu hạn tùy ý; cần cấu trúc chính xác hoặc bước xác minh chính xác.

### Nhóm C — Vòng đời, giới hạn RAM và cấu hình bất biến

**Bài 26 — Dự báo tăng trưởng.** Đã có 400.000 khóa và dự kiến 30.000 khóa mới phân biệt mỗi ngày trong 20 ngày. n_forecast là bao nhiêu? Nếu dành thêm 20% headroom thì n_plan là bao nhiêu?

*Đáp án:* **n_forecast=400.000+30.000×20=1.000.000**; có 20% headroom, **n_plan=1.200.000**.

**Bài 27 — Số khóa tăng gấp đôi.** Một filter thiết kế p≈1% cho một triệu khóa, h=7 cố định, sau đó thêm đủ hai triệu khóa. FPR xấp xỉ trở thành bao nhiêu?

*Đáp án:* Khoảng **15,75%** trong mô hình lý tưởng, do m và h không đổi.

**Bài 28 — RAM thiếu.** Có đúng 1 MiB vùng bit, n=1.000.000 và p phải khoảng 1%. Có thể chọn h=100 để bù thiếu RAM không?

*Đáp án:* **Không**. Với m/n cố định, h có mức tối ưu; phải cấp thêm RAM, giảm phạm vi n hoặc thay đổi kiến trúc/yêu cầu.

**Bài 29 — Thay m/h khi đã có bit 1.** Có được giữ bitarray và đổi m hay h theo số khóa mới không?

*Đáp án:* **Không**. Vị trí băm của khóa cũ có thể không khớp. Cần **tái xây từ nguồn khóa chính xác** hoặc mở một lớp filter mới.

**Bài 30 — 1 triệu lượt add, 20.000 khóa.** Có nên dự báo tỷ lệ bit 1 như 1 triệu khóa độc lập không?

*Đáp án:* **Không**. Add lặp một khóa không tạo vị trí mới; phải dựa trên **số khóa phân biệt thực**.


**Bài 31 — Khóa hết hạn.** Bloom bit chuẩn từng add khóa đã bị xóa khỏi database. Bộ lọc có tự giảm số bit 1 không?

*Đáp án:* **Không**. Cần tái xây, bỏ phân vùng hết hạn hoặc dùng biến thể hỗ trợ xóa đúng hợp đồng; không tự tắt bit.

**Bài 32 — SSTable.** Bloom của một SSTable trả False. Có đủ kết luận khóa vắng trong toàn database không?

*Đáp án:* **Không**. Chỉ loại được đối với **SSTable được filter bao phủ**; khóa có thể ở memtable hoặc bảng khác.

### Nhóm D — Hiệu quả hệ thống và đánh giá

**Bài 33 — Lookup sau Bloom.** Q=10 triệu truy vấn/ngày, α=10% khóa thật có, p=1%. Số lượt tra nguồn chính xác còn lại kỳ vọng là bao nhiêu?

*Đáp án:* \(10.000.000[0,10+0,90\times0,01]=\) **1.090.000 lượt/ngày**.

**Bài 34 — Lợi ích giảm FPR.** Trong tình huống bài 33, giảm p từ 1% xuống 0,1% tiết kiệm thêm bao nhiêu lượt lookup?

*Đáp án:* Tổng lookup giảm từ **1.090.000** xuống **1.009.000**, tiết kiệm thêm **81.000 lượt/ngày**. Cần cân nhắc RAM và CPU tăng thêm.

**Bài 35 — Workload khác.** Q=5 triệu, α=20%, p=1%. Bao nhiêu lookup nguồn còn lại và bao nhiêu lookup được tránh?

*Đáp án:* Lookup còn \(5.000.000[0,20+0,80\times0,01]=\) **1.040.000**; tránh khoảng **3.960.000**.

**Bài 36 — Đo FPR.** Có 10.000 khóa chắc chắn âm tính, 120 khóa bị Bloom trả True. FPR quan sát là bao nhiêu?

*Đáp án:* **120/10.000=1,2%**, không chia cho tổng request có cả positive.

**Bài 37 — Lặp một khóa.** Một khóa lạ được hỏi 10.000 lần trên một filter không đổi. Có thể coi đây là 10.000 phép thử FP độc lập không?

*Đáp án:* **Không**. Cùng khóa, trạng thái và hash thường cho cùng kết quả. Cần tập khóa âm tính đa dạng và đại diện.

**Bài 38 — Ba lớp.** Ba lớp có FPR lần lượt 0,5%, 0,3%, 0,2%. Query True nếu bất kỳ lớp nào True. Union bound cho cận tổng bằng bao nhiêu?

*Đáp án:* **Không quá 1%** theo cận trên tổng \(0,5+0,3+0,2=1\%\), với điều kiện mỗi p_i được tính cho cùng nhóm truy vấn thật sự vắng mặt trên mọi lớp.

**Bài 39 — Merge OR.** Hai Bloom cùng m nhưng khác seed có thể OR bit để query như một filter duy nhất không?

*Đáp án:* **Không**. Cần cùng h, hash/seed/version/encoding và ngữ nghĩa vị trí. Nếu khác cấu hình, giữ riêng hoặc tái xây.

**Bài 40 — Bản thiết kế hoàn chỉnh.** Một hệ thống có n_plan=1.000.000, p_target=0,1%, có nguồn khóa chính xác và nhiều truy vấn đọc. Hãy đề xuất m/h gần đúng và hai điều kiện đúng đắn ở cấp ứng dụng.

*Đáp án:* **m≈14,38 triệu bit≈1,71 MiB, h≈10**, kiểm tra p_est sau làm tròn. **(1)** Bloom phải bao phủ đầy đủ đúng tập/version trước khi tin kết quả False; **(2)** Bloom True vẫn phải được xác minh tại nguồn có thẩm quyền nếu kết luận cuối không được sai. Ngoài ra cần theo dõi n_actual, FPR/occupancy và giữ hash/encoding nhất quán.

## 18. Tổng kết

**Bài toán chọn bit/hash của Bloom filter bắt đầu từ số khóa phân biệt n và mức FPR mục tiêu p.** Trước tiên dự báo **n trong suốt vòng đời**, rồi chọn số bit m và số vị trí băm h theo mô hình:

\[
\boxed{
m\approx-\frac{n\ln p}{(\ln2)^2},
\qquad
h\approx\frac mn\ln2\approx\log_2\frac1p.
}
\]

Với m, h cố định, FPR và tỷ lệ bit 1 dự báo là:

\[
\boxed{
p_{\mathrm{FP}}\approx(1-e^{-hn/m})^h,
\qquad
q_{\mathrm{bit\ 1}}\approx1-e^{-hn/m}.
}
\]

Đây là **các công thức xấp xỉ** dựa trên mô hình phân bố hash thích hợp. Trong cài đặt thực tế, m và h phải **làm tròn thành số nguyên**, căn chỉnh bộ nhớ nếu cần, rồi **tính lại p dự báo**. Bitarray cần **ceil(m/8) byte**, chưa kể metadata, bản sao, vùng nhớ tạm và việc giữ hai phiên bản filter khi chuyển đổi.

Khi số khóa phân biệt **n_actual tăng vượt kế hoạch** nhưng m/h giữ nguyên, FPR có thể tăng rất nhanh. Với filter thiết kế khoảng 1% cho một triệu khóa và h=7, tăng n_actual lên gấp đôi có thể đưa FPR dự báo lên **15,75%**. Không được thay đổi m/h/hash của filter đã có dữ liệu mà không tái xây hoặc tạo lớp mới.

Chọn p nên dựa trên **chi phí lookup nguồn chính xác, tỷ lệ truy vấn âm tính, RAM, CPU hash, số replica và vòng đời dữ liệu**. Bảo đảm **không âm tính giả** của Bloom chỉ-thêm không thay thế tính **đồng bộ của filter với nguồn dữ liệu**; nếu cần câu trả lời cuối chính xác, nhánh True phải được xác minh.

**Ghi nhớ:** **n là số khóa phân biệt trong vòng đời; m là số bit; h là số vị trí băm; p là FPR trên khóa âm tính.** Tính m/h theo công thức, kiểm tra số nguyên và đo FPR/độ bão hòa trên workload thật. Mục tiêu không chỉ là ít bit nhất: đó là **bộ lọc đủ chính xác, vừa ngân sách RAM/CPU và đúng đắn với phiên bản dữ liệu mà nó đại diện**.
