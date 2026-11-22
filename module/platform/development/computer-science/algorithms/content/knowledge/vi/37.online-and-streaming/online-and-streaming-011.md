# Ước lượng số phần tử phân biệt bằng HyperLogLog

**Chủ đề:** Computer Science Algorithms · Trực tuyến và luồng

## 1. Bài toán đếm phần tử phân biệt trong dòng dữ liệu

Một dịch vụ nhận hàng triệu sự kiện mỗi phút: người dùng mở ứng dụng, thiết bị gửi thông điệp, địa chỉ IP truy cập hoặc mã sản phẩm được xem. Một khóa có thể xuất hiện nhiều lần. Câu hỏi thường gặp:

> Trong một khoảng thời gian, có **bao nhiêu khóa khác nhau** đã xuất hiện?

Gọi luồng là \(x_1,x_2,\ldots,x_N\), số phần tử phân biệt thật là:

\[
D=\left|\{x_1,x_2,\ldots,x_N\}\right|.
\]

Nếu luồng là A,A,B,A,C,B thì có N=6 sự kiện nhưng **D=3** giá trị phân biệt. Đây là **COUNT DISTINCT**, không phải đếm tổng sự kiện.

Cách trực tiếp bằng HashSet:
- Với mỗi khóa, thêm vào Set.
- Sau cùng, trả Set.size().
- Đúng tuyệt đối nếu cách nhận diện khóa và phép so bằng nhau đúng.
- Bộ nhớ tăng theo số khóa phân biệt D và kích thước khóa/metadata.

Khi D đạt hàng chục hoặc hàng trăm triệu, giữ toàn bộ khóa có thể không phù hợp với RAM của tiến trình, nhất là khi cần thống kê đồng thời hàng nghìn nhóm.

**HyperLogLog (HLL)** là một cấu trúc dữ liệu xác suất kiểu **sketch**: thay vì giữ từng khóa, nó cập nhật một mảng thanh ghi nhỏ và ước lượng D từ những mẫu bit của hàm băm. HLL đặc biệt hữu ích khi:
- Dữ liệu đến **liên tục**, không muốn lưu toàn bộ lịch sử khóa.
- Có nhiều bản sao/partition cần **gộp thống kê**.
- Chấp nhận **sai số thống kê** thay vì bắt buộc đếm chính xác.
- Muốn bộ nhớ gần như cố định theo **độ chính xác đã chọn**, không tăng tuyến tính theo D.

HLL **không trả một tập khóa** và cũng không cho kết quả chính xác trên mọi luồng. Nó ước lượng số lượng phần tử khác nhau.

## 2. So sánh các hướng giải

| Phương pháp | Kết quả | Bộ nhớ điển hình | Đặc điểm |
|---|---|---|---|
| HashSet tất cả khóa | **Chính xác** | O(D) phần tử cộng chi phí lưu khóa | Có thể liệt kê, kiểm tra membership |
| Sort + loại trùng | **Chính xác** | Phụ thuộc dữ liệu/sort ngoài | Cần lưu hoặc truy cập lại luồng |
| Bitmap trực tiếp | Chính xác nếu miền khóa hữu hạn nhỏ và ánh xạ không va chạm | O(U) bit cho miền U | Tốt khi ID nằm trong miền số nhỏ đã biết |
| Bloom filter | Ước lượng membership, có false positive | Theo kích thước/thiết kế filter | Không phải bộ đếm distinct trực tiếp |
| Linear Counting | **Ước lượng** | m bit | Hữu ích khi còn nhiều bit trống; bão hòa ở tải cao |
| HyperLogLog | **Ước lượng** | m thanh ghi, m=2^p | Luồng lớn, gộp được, sai số chuẩn tương đối xấp xỉ 1,04/√m |

Một hệ thống có thể dùng Set khi D ít và chuyển sang HLL khi lưu chính xác không còn phù hợp. Tuy nhiên việc chuyển đổi, hợp nhất kết quả và công bố sai số cần định nghĩa rõ; không thể đơn giản cộng số lượng của các nhóm có khóa trùng nhau.

## 3. Ý tưởng xác suất: chuỗi bit 0 ở đầu

Giả sử một hàm hash tốt ánh xạ mỗi khóa tới một chuỗi bit đủ dài, với những bit gần phân phối đồng đều. Khi nhìn từ trái sang phải, xác suất một chuỗi bắt đầu bằng:
- Ít nhất 1 bit 0 là khoảng 1/2.
- Ít nhất 2 bit 0 là khoảng 1/4.
- Ít nhất 3 bit 0 là khoảng 1/8.
- Ít nhất k bit 0 là khoảng \(2^{-k}\).

Một chuỗi hash có nhiều bit 0 liên tiếp đầu tiên **hiếm**. Nếu quan sát được một chuỗi có 10 bit 0 đầu tiên, điều ấy gợi ý đã có nhiều phép thử hơn so với khi lớn nhất chỉ là 1–2 bit 0.

Đặt \(\rho(w)\) là **vị trí bit 1 đầu tiên** trong một chuỗi bit w, tính từ 1. Nếu w bắt đầu bằng k bit 0 rồi đến 1, thì \(\rho(w)=k+1\).

~~~text
w = 1........   => rho(w) = 1
w = 01.......   => rho(w) = 2
w = 0001.....   => rho(w) = 4
~~~

Nếu phần còn lại toàn bit 0 và có q bit, định nghĩa \(\rho(w)=q+1\).

**Lưu ý:** giá trị 2^rho chỉ là trực giác rất thô; dùng riêng maximum của một hash stream có **phương sai lớn**. HLL cải thiện độ ổn định bằng cách chia mẫu thành nhiều nhóm và kết hợp chúng qua công thức ước lượng được hiệu chỉnh.

### 3.1. Tại sao phải hash khóa?

Nếu khóa là số thứ tự tăng dần, hay string có prefix lặp, bit gốc có thể không mang phân phối ngẫu nhiên. Việc dùng trực tiếp biểu diễn khóa làm nguồn rho dễ tạo sai lệch nghiêm trọng.

Hash cần:
- **Ổn định:** cùng khóa và cùng cấu hình hash luôn cho cùng 64 bit.
- **Phân tán tốt:** các bit dùng làm chỉ số và rho gần đồng đều.
- **Thống nhất:** mọi partition sử dụng cùng cách chuẩn hóa khóa, encoding, thuật toán hash và seed.

Một hàm hash có chất lượng kém phá giả thiết thống kê, dù phần công thức HLL được cài đúng.

## 4. Kiến trúc thanh ghi của HyperLogLog

Chọn **precision** p, số thanh ghi:

\[
\boxed{m=2^p}.
\]

Với mỗi khóa:
1. Chuyển khóa thành chuỗi byte chuẩn hóa, ví dụ UTF-8.
2. Tính hash 64-bit \(h(x)\).
3. Lấy **p bit cao** của hash làm chỉ số thanh ghi \(j\in[0,m-1]\).
4. Dùng **q=64−p bit còn lại** để tính \(\rho(w)\).
5. Cập nhật:

\[
\boxed{M[j]\leftarrow\max(M[j],\rho(w))}.
\]

Khởi tạo toàn bộ M[j]=0.

**Ý nghĩa:** mỗi thanh ghi lưu vị trí bit 1 đầu tiên lớn nhất từng gặp trong các hash rơi vào bucket j. Không lưu khóa, không lưu toàn bộ hash, không lưu số lượt xuất hiện.

### 4.1. Ví dụ p=4 trên một hash 64-bit

Với p=4, ta có m=16 thanh ghi và q=60 bit còn lại.

Giả sử chuỗi bit cao của hash có dạng:

~~~text
0101 | 0001........................................................
^^^^   ^^^^
index  suffix bắt đầu bằng 0001...
~~~

- Prefix 0101₂ là chỉ số bucket **5**.
- Suffix bắt đầu bằng **ba bit 0 rồi 1**, nên rho=4.
- Cập nhật M[5]=max(M[5],4).

Nếu cùng khóa lặp lại, hash và bucket/rho giữ nguyên, do đó M[5] không đổi. Nếu khóa khác cũng rơi vào bucket 5 nhưng rho=2, M[5] vẫn là 4; nếu rho=7, M[5] tăng lên 7.

### 4.2. Giới hạn rho khi suffix toàn 0

Với hash 64-bit và p bit bucket, suffix chỉ có q=64−p bit. Khi suffix toàn 0, **rho=q+1**. Nếu không chặn giới hạn, dùng một phép đếm số bit 0 trên toàn word đã shift có thể trả giá trị quá lớn vì p bit thấp do phép shift thêm vào.

Bản Java dùng:

~~~text
shifted = hash << p
rank = min(numberOfLeadingZeros(shifted) + 1, 65 - p)
~~~

Với p=10, q=54, rank lớn nhất là **55**. Với p=14, rank lớn nhất là **51**. Giá trị rank có thể lưu trong một byte vì p được giới hạn thích hợp.

### 4.3. Ba tính chất bất biến của cập nhật

Do dùng phép max:
- **Lặp lại cùng khóa:** không làm đổi các thanh ghi — *idempotent*.
- **Đảo thứ tự sự kiện:** kết quả thanh ghi như nhau — *order independent*.
- **Thêm khóa:** mỗi thanh ghi không giảm — *register monotonicity*.

Tuy nhiên **estimate là số thực gần đúng**, được tính từ tổ hợp các thanh ghi và một quy tắc hiệu chỉnh; không nên tự suy ra đó là một bộ đếm nguyên tăng đúng một đơn vị mỗi lần gặp khóa mới.

## 5. Ước lượng số phần tử: raw estimator

Sau khi đọc một luồng, với m thanh ghi M[0..m−1], HLL tính:

\[
Z=\left(\sum_{j=0}^{m-1}2^{-M[j]}\right)^{-1}.
\]

Raw estimate là:

\[
\boxed{E_{\rm raw}=\alpha_m\,m^2\,Z
=\frac{\alpha_m\,m^2}{\sum_j 2^{-M[j]}}}.
\]

\(\alpha_m\) là hằng số hiệu chỉnh hệ số phụ thuộc số thanh ghi:

\[
\alpha_m=
\begin{cases}
0.673,&m=16,\\
0.697,&m=32,\\
0.709,&m=64,\\
0.7213/(1+1.079/m),&m\ge128.
\end{cases}
\]

Công thức này kết hợp các thanh ghi bằng dạng **trung bình điều hòa có chuẩn hóa**, giúp giảm mức dao động so với việc dựa trên đúng một giá trị rho lớn nhất.

**Giải thích trực giác:** nếu các thanh ghi có rank lớn, nhiều số hạng \(2^{-M[j]}\) nhỏ đi, tổng mẫu số giảm và estimate tăng. Việc chia luồng theo m bucket cung cấp nhiều quan sát tương đối độc lập khi hash tốt.

### 5.1. Tại sao không chỉ lấy max rank toàn cục?

Giả sử một hash vô tình có suffix dài toàn 0. Dùng một maximum duy nhất có thể làm estimate thay đổi dữ dội. HLL có nhiều thanh ghi, mỗi thanh ghi ghi lại thông tin cực trị của một luồng con, rồi kết hợp tất cả. Về thống kê, đó là kỹ thuật ổn định các extreme-value measurements.

Nhưng HLL **không phải thuật toán tất định chính xác**. Một luồng cụ thể vẫn có thể nhận estimate cao hoặc thấp hơn D thật.

## 6. Hiệu chỉnh cardinality nhỏ bằng Linear Counting

Nếu chưa có phần tử nào, mọi M[j]=0, tổng mẫu số là m. Raw estimator khi đó xấp xỉ \(0.7m\), **không phải 0**. Vì vậy không thể dùng raw estimator nguyên xi ở cardinality rất nhỏ.

Gọi:

\[
V=\#\{j:M[j]=0\},
\]

tức số thanh ghi **chưa từng được cập nhật**.

Nếu raw estimate nhỏ, cụ thể trong quy tắc truyền thống:

\[
E_{\rm raw}\le\frac52m
\quad\text{và}\quad V>0,
\]

dùng Linear Counting:

\[
\boxed{E_{\rm small}=m\ln(m/V)}.
\]

Nếu V=m (mọi bucket trống), ta có:

\[
m\ln(m/m)=m\ln1=0.
\]

Nếu V=0, không được chia cho 0 hoặc lấy log vô hạn; quay lại raw estimate.

### 6.1. Vì sao công thức có log?

Giả sử D hash của các khóa phân biệt được rải tương đối đều vào m bucket. Xác suất một bucket vẫn trống gần:

\[
(1-1/m)^D\approx e^{-D/m}.
\]

Do đó số bucket trống kỳ vọng xấp xỉ:

\[
V\approx me^{-D/m}.
\]

Giải ra:

\[
D\approx m\ln(m/V).
\]

Đây là một **ước lượng xác suất**, không phải phương trình chính xác cho một luồng cụ thể.

### 6.2. Quy tắc hiệu chỉnh có phạm vi

Ngưỡng \(5m/2\) là cách chuyển chế độ của **HLL cổ điển**, dựa trên phân tích và thực nghiệm. Những thư viện hiện đại như **HyperLogLog++** có thể dùng bias correction và sparse representation khác. Không nên khẳng định ngưỡng này là chuẩn duy nhất của mọi HLL.

Trong chương trình minh họa, khi Eraw≤2,5m và V>0 thì dùng Linear Counting, ngoài ra dùng Eraw. Mã **không** triển khai toàn bộ HLL++, không có bảng hiệu chỉnh bias riêng và không có sparse encoding.

## 7. Sai số tương đối, precision và bộ nhớ

Dưới giả thiết hash gần phân phối lý tưởng và cardinality ở vùng hoạt động phù hợp, HLL cổ điển có **relative standard error (RSE)** xấp xỉ:

\[
\boxed{\operatorname{RSE}\approx\frac{1.04}{\sqrt m}
=\frac{1.04}{\sqrt{2^p}}}.
\]

**RSE là độ lệch chuẩn tương đối**, không phải cam kết rằng mọi lần ước lượng đều nằm trong ±RSE. Một lần chạy có thể sai nhiều hơn; xác suất tail và bias cần được phân tích riêng.

| Precision p | Registers m | Bộ nhớ byte[] demo | RSE lý thuyết gần đúng |
|---:|---:|---:|---:|
| 4 | 16 | 16 byte | 26,00% |
| 8 | 256 | 256 byte | 6,50% |
| 10 | 1.024 | 1.024 byte | 3,25% |
| 12 | 4.096 | 4.096 byte | 1,625% |
| 14 | 16.384 | 16.384 byte | 0,8125% |
| 16 | 65.536 | 65.536 byte | 0,40625% |

Bộ nhớ nêu ở cột byte[] là **dung lượng phần tử mảng thanh ghi**, không tính header mảng, object, seed, các object tạm hoặc overhead của JVM.

Với dạng **packed 6-bit register**, m=16.384 cần 16.384×6/8=**12.288 byte ≈12 KiB**, so với **16 KiB** cho byte[] đơn giản. Cài đặt HLL++ có thể còn tiết kiệm đáng kể ở cardinality nhỏ nhờ biểu diễn sparse.

### 7.1. Đổi accuracy lấy RAM

Muốn giảm sai số chuẩn **một nửa**:

\[
\frac{1.04}{\sqrt{4m}}=\frac12\frac{1.04}{\sqrt m}.
\]

Cần tăng số registers **gấp bốn**, tức tăng p lên **2**. HLL phù hợp khi nhiều luồng cần bộ đếm riêng và ngân sách bộ nhớ cho mỗi bộ đếm phải kiểm soát được.

Ví dụ p=10 có RSE≈3,25% và m=1024. Chuyển lên p=12 tăng từ 1024 lên 4096 registers, RSE còn≈1,625%.

### 7.2. Không tự tạo khoảng tin cậy tuyệt đối

Câu “RSE 3,25%, nên kết quả chắc chắn lệch dưới 3,25%” là **sai**. RSE mô tả một đại lượng phân tán trong mô hình xác suất; không phải worst-case deterministic error bound.

Nếu hệ thống cần confidence interval chính thức, phải mô tả rõ phân phối/bias, phiên bản estimator, phạm vi cardinality, chất lượng hash và mức tin cậy. Lấy 2×RSE làm “95% confidence interval” không tự động có chứng minh đúng cho mọi tình huống.

## 8. Hợp nhất nhiều luồng: merge bằng max thanh ghi

Đây là lợi ích quan trọng của HLL trong **stream processing phân tán**.

Giả sử luồng A có sketch M_A, luồng B có sketch M_B. Để ước lượng số khóa phân biệt của **hợp A∪B**, tạo:

\[
\boxed{M_{A\cup B}[j]=\max(M_A[j],M_B[j])}.
\]

Vì cập nhật từng khóa cũng chính là max, sketch sau merge có thanh ghi **đúng bằng** sketch thu được nếu đưa toàn bộ khóa của A và B vào một sketch duy nhất với **cùng hash**.

### 8.1. Tính chất đại số

Merge từng thanh ghi bằng max nên:

- **Giao hoán:** merge(A,B) và merge(B,A) cho cùng thanh ghi.
- **Kết hợp:** merge(merge(A,B),C) bằng merge(A,merge(B,C)).
- **Lũy đẳng:** merge(A,A)=A.
- **Bỏ qua lặp:** khóa xuất hiện ở cả A và B không bị “đếm hai lần” ở cấp sketch.

Các tính chất này làm HLL phù hợp để:
- Gộp từng partition Kafka theo thời gian.
- Tổng hợp từ worker sang aggregator.
- Hợp nhất số người dùng phân biệt ở nhiều server.
- Retry/at-least-once delivery mà không phá các thanh ghi đã có.

**Quan trọng:** những tính chất trên đúng khi các sketch **tương thích**: cùng p, cùng width và thuật toán hash, cùng seed/salt, cùng biểu diễn và chuẩn hóa khóa.

### 8.2. Vì sao không cộng estimate A và B?

Nếu A có 1000 người dùng, B có 1000 người dùng và 500 người dùng trùng nhau, union thật có:

\[
|A\cup B|=1000+1000-500=1500.
\]

Cộng ước lượng cardinality của A và B sẽ gần 2000, bị đếm trùng. Cách đúng để ước lượng union bằng HLL là **merge registers trước, estimate một lần**.

Sau merge, estimate vẫn có sai số thống kê, vì thế không nhất thiết trả chính xác 1500.

### 8.3. Khả năng merge không có nghĩa có thể trừ sketch

Không tồn tại phép “lấy max ngược” đơn giản để loại chính xác các khóa của một partition ra khỏi sketch đã merge. Mỗi thanh ghi chỉ lưu max rho; không biết nguồn nào đã tạo max và bao nhiêu khóa khác cũng cho rank ấy.

Vì vậy:
- HLL thông thường **không hỗ trợ delete chính xác** một khóa đã thêm.
- Không thể lấy HLL(A∪B)−HLL(B) bằng trừ thanh ghi để được HLL(A\B).
- Ước lượng giao qua inclusion–exclusion:

\[
|A\cap B|\approx\hat D_A+\hat D_B-\hat D_{A\cup B}
\]

có thể **rất nhiễu**, đặc biệt khi intersection nhỏ so với union; estimate thậm chí có thể âm do sai số.

Với yêu cầu intersection/Jaccard chính xác hơn, nên xét các sketch được thiết kế cho bài toán tập hợp đó, như MinHash/KMV tùy yêu cầu.

## 9. Bài toán cửa sổ thời gian (sliding window)

Một bộ HLL tích lũy từ lúc bắt đầu **không biết tự quên** khóa cũ. Nếu cần số người dùng phân biệt trong 1 giờ gần nhất:
- Một HLL liên tục từ đầu ngày sẽ không tự loại khóa trước cửa sổ.
- Không thể xóa từng hash khỏi HLL đơn giản.
- Có thể chia dữ liệu thành **bucket thời gian**, mỗi bucket có một sketch riêng.
- Khi truy vấn, merge sketches thuộc cửa sổ.
- Khi bucket hết hạn, bỏ **cả bucket**, không trừ từng khóa.

Cách này có độ phân giải theo bucket: một cửa sổ không trùng ranh giới bucket có thể bao gồm thêm phần dữ liệu ngoài khoảng cần thiết, hoặc bỏ mất dữ liệu trong bucket biên. Muốn đúng theo time window cần xử lý bucket biên, chọn granularity hoặc cấu trúc cửa sổ chuyên dụng.

Số sketch lưu trữ tăng theo số bucket thời gian và số nhóm cần thống kê. HLL có bộ nhớ nhỏ cho một sketch nhưng **không miễn phí** khi nhân với hàng triệu nhóm.

### 9.1. Event-time khác processing-time

Trong hệ thống luồng phân tán:
- **Event time:** thời điểm sự kiện thực sự xảy ra.
- **Processing time:** thời điểm hệ thống xử lý nó.

Sự kiện trễ có thể thuộc một bucket đã “đóng”. Phải định nghĩa watermark, độ trễ chấp nhận, chính sách cập nhật và thời điểm phát hành kết quả. HLL giải bài distinct sketch, không tự giải bài toán phân nhóm thời gian.

## 10. Lựa chọn hash, identity và khả năng tương thích

### 10.1. Cùng “người dùng” nghĩa là cùng khóa gì?

HLL đếm **giá trị hash của khóa đầu vào**. Nếu hệ thống có:
- userId dạng số và dạng chuỗi,
- Unicode có dạng composed/decomposed,
- chữ hoa/chữ thường,
- tiền tố tenant,
- email đã hoặc chưa chuẩn hóa,

thì cần quyết định rõ liệu chúng có cùng một identity hay không. Nếu hai phần mềm chuẩn hóa khác nhau, merge sketches sẽ cho kết quả khó diễn giải.

Ví dụ cùng một tài khoản có ID "User-17" ở bên A và "user-17" ở bên B. Nếu quy tắc nghiệp vụ xem hai chuỗi tương đương nhưng hệ thống hash chúng khác nhau, HLL **ước lượng hai khóa riêng** thay vì một người dùng.

### 10.2. Hash collision và độ bão hòa

Hash 64-bit có miền hữu hạn. Hai khóa khác nhau **có thể cùng hash**. HLL không phân biệt được những khóa ấy; số học xác suất giả định hash phân tán tốt và số lượng khóa chưa tiến gần giới hạn miền hash.

Ở cardinality rất lớn so với không gian 2^64, collision và **saturation** làm sai lệch ước lượng. Ví dụ cổ điển HLL 32-bit dùng hiệu chỉnh large-range khi tiến gần kích thước miền hash. Bản demo dùng hash 64-bit và **không triển khai large-range correction**, nên không được hứa chính xác ở quy mô cực hạn.

### 10.3. Hash demo và hash production

Code Java dùng **FNV-1a 64-bit** trên UTF-8, sau đó trộn thêm bằng bước avalanche kiểu MurmurHash3 fmix64, có một seed dài 64-bit:
- Ưu điểm: ngắn, không cần thư viện ngoài, tái lập trên JVM.
- Hạn chế: **không chứng minh** đầu ra là các bit độc lập đều, không chống đối thủ biết seed, không phải bộ hash mật mã.
- Phù hợp **minh họa và bài tập**, không tự động là khuyến nghị triển khai HLL ở môi trường đối kháng.

Trong production nên cân nhắc thư viện sketch đã kiểm định, hash 64/128-bit có kiểm thử phân phối, versioning và merge protocol rõ ràng. Đổi hash/seed giữa chừng làm các sketch **không thể merge an toàn**.

## 11. Độ phức tạp thời gian và không gian

Với m=2^p registers và khóa có k byte UTF-8:

| Thao tác | Chi phí | Ghi chú |
|---|---|---|
| Tính hash khóa | O(k) | Phụ thuộc độ dài khóa |
| Add một hash đã có | O(1) | Một bucket, một phép max |
| Add một String | O(k) | Hash + một cập nhật thanh ghi |
| Estimate toàn sketch | O(m) | Quét tất cả m registers |
| Merge hai sketches | O(m) | Max theo từng vị trí |
| Copy một sketch | O(m) | Sao chép thanh ghi |
| Bộ nhớ register | O(m) | Độc lập với số sự kiện và D |
| Truy vết mọi khóa | Không hỗ trợ | HLL không lưu khóa gốc |

Đếm distinct chính xác bằng HashSet cần O(D) entry và chi phí lưu khóa. HLL đổi tính chính xác tuyệt đối lấy O(m) thanh ghi.

**Chú ý:** nếu hệ thống gọi estimate **sau mỗi event**, mỗi query estimate O(m), nên tổng thời gian có thể trở thành O(Nm) dù add chỉ O(1) sau hash. Thường nên cache kết quả và chỉ ước lượng định kỳ/khởi tạo khi cần.

### 11.1. Chọn p theo SLA

Nếu ngân sách sai số chuẩn tương đối mong muốn khoảng r, có thể ước lượng:

\[
m\approx(1.04/r)^2.
\]

Sau đó chọn p sao cho \(m=2^p\) đủ lớn, đồng thời xem xét RAM của mọi sketch, độ chính xác tại cardinality nhỏ và các hiệu chỉnh bias.

Ví dụ mong muốn RSE khoảng 1%, cần m vào cỡ 10.816 thanh ghi; chọn m=16.384 (p=14) cho lý thuyết RSE≈0,8125%.

Công thức này là **quy hoạch độ chính xác thống kê**, không phải bảo đảm sai lệch tuyệt đối cho mọi lần chạy.

## 12. Java 17 hoàn chỉnh: HLL cơ bản có merge

Lưu file **HyperLogLogDemo.java**. Chương trình này là **bản HLL giáo dục**, không phải thư viện HLL++ tối ưu production.

Chức năng:
- Chọn precision p từ 4 đến 16, m=2^p registers.
- Băm String theo UTF-8 thành long 64-bit ổn định và có seed.
- Lấy p bit cao làm bucket, rank từ 64−p bit còn lại, chặn q+1.
- Cập nhật thanh ghi bằng max.
- Tính raw estimate, alpha_m, dùng Linear Counting khi Eraw≤2,5m và còn thanh ghi 0.
- Gộp hai sketches cùng p và seed, sao chép sketch, kiểm tra register equality.
- Minh họa empty/duplicates/order, hai luồng có khóa trùng, union, rejection khi merge sketch không tương thích.
- Dùng HashSet để tính **oracle chính xác trên dữ liệu nhỏ**; production không cần giữ HashSet.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public final class HyperLogLogDemo {
    private HyperLogLogDemo() {
    }

    private static final long SEED = 0x1234ABCD5678EF90L;

    public static final class HyperLogLog {
        private static final long FNV_OFFSET =
                0xcbf29ce484222325L;
        private static final long FNV_PRIME =
                0x100000001b3L;
        private static final long MIX1 =
                0xff51afd7ed558ccdL;
        private static final long MIX2 =
                0xc4ceb9fe1a85ec53L;

        private final int precision;
        private final int m;
        private final long seed;
        private final byte[] registers;

        public HyperLogLog(int precision, long seed) {
            if (precision < 4 || precision > 16) {
                throw new IllegalArgumentException(
                        "precision must be in [4, 16]");
            }
            this.precision = precision;
            this.m = 1 << precision;
            this.seed = seed;
            this.registers = new byte[m];
        }

        public int registerCount() {
            return m;
        }

        public int registerBytes() {
            return registers.length;
        }

        public double relativeStandardError() {
            return 1.04 / Math.sqrt(m);
        }

        private static long mix64(long x) {
            x ^= x >>> 33;
            x *= MIX1;
            x ^= x >>> 33;
            x *= MIX2;
            x ^= x >>> 33;
            return x;
        }

        // FNV-1a trên UTF-8 rồi avalanche; minh họa,
        // KHÔNG phải một bảo đảm hash lý tưởng/mật mã.
        private long hash(String value) {
            Objects.requireNonNull(value, "value");
            long h = FNV_OFFSET ^ seed;

            for (byte b : value.getBytes(
                    StandardCharsets.UTF_8)) {
                h ^= (b & 0xffL);
                h *= FNV_PRIME;
            }
            return mix64(h);
        }

        public void add(String value) {
            long h = hash(value);
            int index = (int) (h >>> (64 - precision));

            // Bỏ p bit prefix; suffix 64-p bit
            // được đẩy sang đầu word.
            long shifted = h << precision;
            int rank = Math.min(
                    Long.numberOfLeadingZeros(shifted) + 1,
                    65 - precision);

            if (rank > (registers[index] & 0xff)) {
                registers[index] = (byte) rank;
            }
        }

        public int zeroRegisters() {
            int zeros = 0;
            for (byte register : registers) {
                if (register == 0) {
                    zeros++;
                }
            }
            return zeros;
        }

        private double alpha() {
            return switch (m) {
                case 16 -> 0.673;
                case 32 -> 0.697;
                case 64 -> 0.709;
                default -> 0.7213 / (1.0 + 1.079 / m);
            };
        }

        public double estimate() {
            double inverseSum = 0.0;
            int zeros = 0;

            for (byte register : registers) {
                int rank = register & 0xff;
                inverseSum += Math.scalb(1.0, -rank);
                if (rank == 0) {
                    zeros++;
                }
            }

            double raw = alpha() * m * (double) m
                    / inverseSum;

            if (raw <= 2.5 * m && zeros > 0) {
                return m * Math.log(
                        (double) m / zeros);
            }
            return raw;
        }

        public HyperLogLog copy() {
            HyperLogLog result =
                    new HyperLogLog(precision, seed);
            System.arraycopy(registers, 0,
                    result.registers, 0, m);
            return result;
        }

        public void mergeFrom(HyperLogLog other) {
            Objects.requireNonNull(other, "other");

            if (precision != other.precision
                    || seed != other.seed) {
                throw new IllegalArgumentException(
                        "Incompatible HLL precision or seed");
            }

            for (int i = 0; i < m; i++) {
                if ((registers[i] & 0xff)
                        < (other.registers[i] & 0xff)) {
                    registers[i] = other.registers[i];
                }
            }
        }

        public boolean sameRegisters(HyperLogLog other) {
            return other != null
                    && precision == other.precision
                    && seed == other.seed
                    && Arrays.equals(
                        registers, other.registers);
        }
    }

    private static String twoDecimals(double value) {
        return String.format(
                Locale.ROOT, "%.2f", value);
    }

    private static void require(boolean condition, String msg) {
        if (!condition) {
            throw new AssertionError(msg);
        }
    }

    public static void main(String[] args) {
        HyperLogLog empty = new HyperLogLog(10, SEED);
        System.out.println("Empty estimate: "
                + twoDecimals(empty.estimate()));
        System.out.println("Register count: "
                + empty.registerCount());
        System.out.println("Raw register bytes: "
                + empty.registerBytes());
        System.out.println("Theoretical RSE: "
                + twoDecimals(
                    100.0 * empty.relativeStandardError())
                + "%");

        String[] sample = {
            "alpha", "beta", "alpha",
            "gamma", "delta", "gamma"
        };
        HyperLogLog small = new HyperLogLog(10, SEED);
        for (String value : sample) {
            small.add(value);
        }

        Set<String> smallExact =
                new HashSet<>(Arrays.asList(sample));
        System.out.println("Small exact distinct: "
                + smallExact.size());
        System.out.println("Small estimate: "
                + twoDecimals(small.estimate()));
        System.out.println("Small zero registers: "
                + small.zeroRegisters());

        HyperLogLog beforeDuplicates = small.copy();
        small.add("alpha");
        small.add("gamma");
        small.add("alpha");
        System.out.println("Duplicates unchanged: "
                + small.sameRegisters(beforeDuplicates));

        HyperLogLog backwards =
                new HyperLogLog(10, SEED);
        for (int i = sample.length - 1; i >= 0; i--) {
            backwards.add(sample[i]);
        }
        System.out.println("Order independent: "
                + small.sameRegisters(backwards));

        HyperLogLog left = new HyperLogLog(10, SEED);
        HyperLogLog right = new HyperLogLog(10, SEED);
        Set<String> exactA = new HashSet<>();
        Set<String> exactB = new HashSet<>();
        Set<String> exactUnion = new HashSet<>();

        for (int i = 0; i < 1000; i++) {
            String id = "user-" + i;
            left.add(id);
            exactA.add(id);
            exactUnion.add(id);
        }

        for (int i = 500; i < 1500; i++) {
            String id = "user-" + i;
            right.add(id);
            exactB.add(id);
            exactUnion.add(id);
        }

        HyperLogLog union = left.copy();
        union.mergeFrom(right);

        HyperLogLog direct =
                new HyperLogLog(10, SEED);
        for (int i = 0; i < 1500; i++) {
            direct.add("user-" + i);
        }

        HyperLogLog reverseMerge = right.copy();
        reverseMerge.mergeFrom(left);
        HyperLogLog repeatedMerge = union.copy();
        repeatedMerge.mergeFrom(right);

        require(union.sameRegisters(direct),
                "Merge must equal direct union");
        require(reverseMerge.sameRegisters(union),
                "Merge must be commutative");
        require(repeatedMerge.sameRegisters(union),
                "Merge must be idempotent");

        System.out.println("A exact: " + exactA.size());
        System.out.println("B exact: " + exactB.size());
        System.out.println("Union exact: "
                + exactUnion.size());
        System.out.println("A HLL estimate: "
                + twoDecimals(left.estimate()));
        System.out.println("B HLL estimate: "
                + twoDecimals(right.estimate()));
        System.out.println("Union HLL estimate: "
                + twoDecimals(union.estimate()));
        System.out.println("Merged equals direct: "
                + union.sameRegisters(direct));
        System.out.println("Merge commutative: "
                + union.sameRegisters(reverseMerge));
        System.out.println("Merge idempotent: "
                + union.sameRegisters(repeatedMerge));

        try {
            union.mergeFrom(new HyperLogLog(11, SEED));
            System.out.println(
                    "Incompatible precision rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "Incompatible precision rejected: true");
        }

        try {
            union.mergeFrom(new HyperLogLog(10, SEED + 1));
            System.out.println(
                    "Incompatible seed rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "Incompatible seed rejected: true");
        }

        try {
            new HyperLogLog(3, SEED);
            System.out.println("Invalid p rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid p rejected: true");
        }

        try {
            small.add(null);
            System.out.println("Null key rejected: false");
        } catch (NullPointerException expected) {
            System.out.println("Null key rejected: true");
        }
    }
}
~~~

### 12.1. Biên dịch và chạy

Dùng **JDK 17 hoặc mới hơn**, lưu đúng tệp HyperLogLogDemo.java:

~~~bash
javac -encoding UTF-8 HyperLogLogDemo.java
java HyperLogLogDemo
~~~

**Stdout dự kiến với hàm hash và seed như trong mã:**

~~~text
Empty estimate: 0.00
Register count: 1024
Raw register bytes: 1024
Theoretical RSE: 3.25%
Small exact distinct: 4
Small estimate: 4.01
Small zero registers: 1020
Duplicates unchanged: true
Order independent: true
A exact: 1000
B exact: 1000
Union exact: 1500
A HLL estimate: 1017.79
B HLL estimate: 988.49
Union HLL estimate: 1481.40
Merged equals direct: true
Merge commutative: true
Merge idempotent: true
Incompatible precision rejected: true
Incompatible seed rejected: true
Invalid p rejected: true
Null key rejected: true
~~~

### 12.2. Cách đọc output đúng

**Small exact distinct: 4:** luồng sáu event alpha,beta,alpha,gamma,delta,gamma chỉ có bốn khóa khác nhau. HashSet cho đáp án chính xác 4.

**Small estimate: 4.01:** HLL cho kết quả **số thực** gần 4, không phải 4 đúng tuyệt đối. Vì p=10, có m=1024 registers và chỉ bốn bucket khác 0, nên Linear Counting với V=1020 cho:

\[
1024\ln(1024/1020)\approx4.0078.
\]

In hai chữ số thập phân là 4.01.

**A exact/B exact/Union exact:** A chứa user-0 đến user-999 (1000 khóa), B chứa user-500 đến user-1499 (1000 khóa), 500 khóa giao nhau, union có 1500 khóa.

**A/B/Union HLL estimates:** tương ứng xấp xỉ 1017.79, 988.49 và 1481.40 với hàm hash cụ thể trong bản demo. Cả ba **không cần trùng số chính xác**; kết quả gần nhau là đặc điểm của dữ liệu và seed minh họa, không phải định lý rằng mọi lần HLL sai dưới 2%.

**Merge equals direct:** bộ thanh ghi của union sau max-register trùng **từng byte** với sketch nạp trực tiếp user-0 đến user-1499. Đây là tính chất **chính xác ở cấp sketch**, khác với việc cardinality estimate bằng true D.

**Merge commutative/idempotent:** hai nhánh gộp có cùng thanh ghi dù đổi thứ tự hoặc lặp lại merge.

**Reject incompatible:** precision khác làm số lượng/ý nghĩa thanh ghi khác, seed khác làm hash mapping khác. Code từ chối để không tạo một estimate nhìn có vẻ hợp lệ nhưng đã hỏng ngữ nghĩa.

**Empty estimate:** Linear Counting trả 0 cho m bucket đều trống. HLL không tự suy diễn luồng rỗng có vài trăm khóa chỉ từ raw formula.

### 12.3. Giải thích Java từng phần

**Hash:** dùng FNV-1a 64-bit với seed để hash byte UTF-8, sau đó bước avalanche. Java long overflow theo quy tắc modulo 2^64 cho các phép nhân/hay trộn bit trên long; đây là hành vi dự kiến của hash, **không phải lỗi arithmetic overflow cần tránh** như khi tính tiền hoặc tổng số vật.

**index:** h >>> (64-p) dịch phải không dấu, lấy đúng p bit cao. Không dùng toán tử >> có dấu để suy ra chỉ số bucket, vì bit dấu 1 có thể làm chỉ số âm hoặc sai.

**rank:** h << p đẩy suffix lên đầu; Long.numberOfLeadingZeros đo số bit 0 đầu tiên; min(...,65-p) tránh tính các bit 0 nhân tạo do shift. Trong ví dụ p=10, rho tối đa 55.

**register:** byte[] lưu rank không âm nhỏ; update chỉ khi rank mới lớn hơn. Không có phép cộng số lần vào register — HLL không phải m counters đếm tần suất.

**estimate:** quét toàn bộ registers, cộng 2^(−rank) bằng Math.scalb, tính alpha_m và raw estimator; khi raw nhỏ và còn bucket trống thì dùng Linear Counting.

**mergeFrom:** kiểm p và seed trước khi max từng thanh ghi. Việc tương thích **hash algorithm, encoding và chuẩn hóa** được đảm bảo bởi cùng class/phiên bản demo; production phải kiểm thêm version/protocol nếu có nhiều dịch vụ.

**sameRegisters:** so mảng byte, dùng để xác nhận các tính chất đại số; nó không so estimate làm tròn, vì hai sketch khác register vẫn có thể tình cờ có cùng estimate.

**Seed:** dùng cố định để output tái lập. Không được diễn giải seed cố định làm các bit có phân phối lý tưởng trước một đối thủ biết thuật toán.

### 12.4. Mã không triển khai những gì?

Đây không phải HLL++ đầy đủ:
- Không có sparse representation/bias table của HLL++.
- Không có large-range correction khi cardinality tiệm cận không gian 64-bit.
- Không có serialize/deserialize và versioned merge protocol.
- Không có thread-safety cho cập nhật đồng thời.
- Không có TTL/delete chính xác hoặc sliding-window event-time.
- Không có chứng minh phân phối lý tưởng của FNV+fmix.

Các giới hạn này cần ghi nhận khi tái sử dụng bài code trong một hệ thống lớn, nhất là dữ liệu đối kháng hoặc số lượng sketch khổng lồ.

## 13. Kiểm thử HLL như thế nào?

Vì HLL là thuật toán xác suất, một test đơn lẻ kiểu **assert estimate == exact** là không phù hợp, trừ những trường hợp đặc biệt như luồng rỗng.

Cần tách hai loại kiểm thử:

### 13.1. Tính chất xác định phải đúng tuyệt đối

Đây là các bất biến **không được phép sai**:
1. Cùng khóa nạp nhiều lần không đổi registers.
2. Đảo thứ tự nạp không đổi registers.
3. Merge(A,B) có registers bằng một sketch nạp toàn bộ A và B theo cùng hash/seed/p.
4. Merge(A,B)=Merge(B,A) ở mức registers.
5. Merge(A,A)=A.
6. Merge kết hợp ba sketches có cùng registers.
7. Không register nào giảm sau add/merge.
8. Mọi rank đều nằm trong [0,65-p].
9. Dữ liệu rỗng trả estimate0 sau small-range correction.
10. Merge precision/seed không tương thích phải bị từ chối.
11. Estimate là số hữu hạn và không âm trong miền đầu vào demo.
12. Cùng String hợp lệ, cùng seed cho cùng hash và cùng trạng thái sketch.

Các bất biến này nên được kiểm tra bằng property-based tests với seed tái lập và nhiều luồng có khóa trùng. Một lỗi ở bất kỳ bất biến nào thường là lỗi implementation, **không thể biện hộ bằng “sai số xác suất”**.

### 13.2. Sai số estimator phải kiểm tra thống kê

Với nhiều tập khóa phân biệt đã biết chính xác D:
- Sinh dữ liệu với các seed/hàm hash phù hợp.
- Tính \(\hat D\) từ sketch.
- Đo \((\hat D-D)/D\) khi D>0.
- Tổng hợp **bias**, sample standard deviation và quantiles.
- So với kỳ vọng RSE ở cardinality tương ứng, tránh đòi một lần đo nằm trong ±RSE.

Mức sai số gần 1.04/√m là một tính chất **thống kê trong mô hình hash**, không phải kiểm thử từng instance đều phải đạt. Các dataset rất nhỏ, hash kém và chế độ gần bão hòa có thể có bias khác.

### 13.3. Những bộ dữ liệu cần có

- Empty stream và một khóa lặp hàng trăm lần.
- 2, 4, 10, 100, 1000, 10000 khóa phân biệt.
- Khóa chung giữa nhiều partition; gộp theo các thứ tự khác nhau.
- Chuỗi rỗng "" và khóa UTF-8 nhiều byte.
- Khóa được viết hoa/thường hoặc khác Unicode normalization.
- Các chuỗi dài, nhiều prefix giống nhau hoặc các số tăng liên tiếp.
- precision p=4, p=10, p=16 và giá trị p ngoài giới hạn.
- Seed giống và seed khác khi merge.
- Rank cực đại khi suffix toàn 0 (có thể kiểm bằng một hàm cập nhật nhận hash thủ công trong test).
- Đọc/ghi qua serialization nếu hệ thống thực tế triển khai.

Một test quan trọng: nếu hai streams đều có đúng 1000 khóa và 500 khóa trùng, union thật là 1500. HLL sau merge phải có **registers đúng như nạp union trực tiếp**, nhưng estimate có thể là 1481.40 theo ví dụ, không bắt buộc đúng 1500.

## 14. Lỗi thường gặp

1. **Đếm số sự kiện N thay vì số phần tử phân biệt D.**
2. **Dùng HashSet rồi gọi là HyperLogLog**, dù bộ nhớ vẫn tăng theo số khóa.
3. **Giữ toàn bộ hash 64-bit** và gọi đó là HLL; HLL chỉ cần registers.
4. **Không thống nhất định nghĩa identity** giữa các partition.
5. **Hash bằng String.hashCode() 32-bit** nhưng dùng công thức và dải mong muốn của 64-bit mà không xem xét va chạm và phân phối.
6. **Lấy p bit thấp cho bucket nhưng lại shift như thể lấy bit cao**, làm rho/index không nhất quán.
7. **Dùng dịch phải có dấu >> thay vì >>>** khi lấy bucket cao.
8. **Quên giới hạn rho=q+1** với suffix toàn 0.
9. **Dùng phép cộng thay cho max** khi cập nhật thanh ghi, khiến duplicate bị đếm nhiều lần.
10. **Dùng số lần xuất hiện của khóa làm register**, sai bản chất thuật toán.
11. **Tính raw estimate cho luồng rỗng** rồi nhận kết quả xấp xỉ 0.7m.
12. **Không áp dụng small-range correction** khi D rất nhỏ so với m.
13. **Lấy log khi V=0**, dẫn tới vô hạn hoặc lỗi số học.
14. **Tính 2^rank thay vì 2^(−rank)** trong mẫu số estimator.
15. **Không dùng đúng alpha_m theo m**, tạo bias.
16. **Khẳng định mọi bản HLL đều dùng đúng ngưỡng 5m/2**, bỏ khác biệt HLL++.
17. **Lấy RSE làm sai số tối đa mỗi lần chạy**.
18. **Tuyên bố estimate ±RSE là confidence interval chắc chắn 95%** mà không chứng minh phân phối.
19. **Không xét lỗi hash/collision**, dù các register updates đúng.
20. **Đổi seed/hash/encoding rồi merge sketches cũ**, làm hỏng union semantics.
21. **Cộng estimate hai nhóm để ra distinct union**, đếm trùng khóa.
22. **Trừ trực tiếp hai sketches để xử lý deletion/window**, không có phép trừ hợp lệ cho max-register sketch.
23. **Ước lượng intersection bằng inclusion–exclusion rồi coi số âm là số phần tử thật**, bỏ qua nhiễu thống kê.
24. **Quên nhiều nhóm tương đương nhiều bộ registers**, tiêu tốn RAM khi cardinality theo nhóm cao.
25. **Gọi estimate O(1)** dù phải quét m thanh ghi.
26. **Bỏ chi phí hash O(k) theo độ dài khóa**, chỉ đếm phần update bucket.
27. **Thay HashSet oracle bằng HLL khác rồi kiểm tra cùng sai số**, không còn nguồn kiểm chứng chính xác.
28. **Bắt estimate bằng exact D ở mọi test**, biến hành vi xác suất hợp lệ thành lỗi giả.
29. **Chỉ test một seed hoặc một loại khóa**, không đo bias trên nhiều mẫu.
30. **Không khóa phiên bản của sketch khi phân tán**, làm kết quả merge không thể tái tạo.
31. **Không đồng bộ cập nhật nhiều thread**, làm rơi register max nếu race.
32. **Không có chính sách late event/window** cho thống kê theo event time.
33. **Dùng cùng một sketch mãi mãi cho sliding window**, giữ những khóa đã hết hạn.
34. **Báo sai đơn vị 1KiB/12KiB**, bỏ overhead hoặc nhầm byte và bit.
35. **Gọi HLL là bộ đếm chính xác**, dù thực chất là sketch xác suất.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** HyperLogLog dùng để làm gì?

**Đáp án:** Ước lượng số khóa phân biệt D trong một luồng bằng bộ nhớ nhỏ cố định theo precision, không lưu mọi khóa.

**Câu 2.** HLL khác HashSet thế nào?

**Đáp án:** HashSet đếm chính xác nhưng nhớ các khóa; HLL giữ một mảng thanh ghi nhỏ và trả estimate có sai số thống kê.

**Câu 3.** p=10 có bao nhiêu thanh ghi?

**Đáp án:** \(m=2^{10}=1024\).

**Câu 4.** Để chọn bucket dùng bit nào của hash trong demo?

**Đáp án:** p bit cao của hash 64-bit.

**Câu 5.** Rho là gì?

**Đáp án:** Vị trí bit 1 đầu tiên của phần suffix hash, tính từ 1; suffix toàn 0 có rho=q+1.

**Câu 6.** Rank lớn nhất khi p=10 và hash 64-bit?

**Đáp án:** 64−10+1=55.

**Câu 7.** Mỗi lần add cập nhật thanh ghi thế nào?

**Đáp án:** M[j]=max(M[j],rho).

**Câu 8.** Vì sao khóa lặp không làm thay đổi sketch?

**Đáp án:** Hash, bucket và rho giống nhau; phép max với giá trị cũ là lũy đẳng.

**Câu 9.** Công thức raw estimate?

**Đáp án:** \(\alpha_m m^2/\sum_j 2^{-M[j]}\).

**Câu 10.** Vì sao luồng rỗng cần hiệu chỉnh?

**Đáp án:** Raw estimator khi mọi thanh ghi bằng 0 vẫn gần 0.7m, không phải 0.

**Câu 11.** Small-range correction dùng công thức nào?

**Đáp án:** \(m\ln(m/V)\), với V số registers bằng 0, khi raw nhỏ và V>0.

**Câu 12.** RSE xấp xỉ của HLL?

**Đáp án:** \(1.04/\sqrt m\) với các giả thiết thống kê phù hợp.

**Câu 13.** p=10 có RSE khoảng bao nhiêu?

**Đáp án:** 3,25% (độ lệch chuẩn tương đối, không phải sai số tối đa).

**Câu 14.** Muốn chia đôi RSE cần tăng m thế nào?

**Đáp án:** Tăng số registers lên khoảng gấp bốn, tức p tăng 2.

**Câu 15.** Merge hai HLL cho union bằng công thức nào?

**Đáp án:** Max từng register tương ứng, với cùng precision và hash configuration.

**Câu 16.** Vì sao không cộng estimate A+B?

**Đáp án:** Hai nhóm có thể có khóa trùng, nên cộng estimate gần như đếm trùng; cần merge sketches.

**Câu 17.** Hai sketches khác seed có nên merge không?

**Đáp án:** Không, vì cùng khóa có thể đến bucket/rho khác nhau; phải dùng cùng hash family/seed/canonicalization.

**Câu 18.** Có thể xóa một khóa khỏi HLL gốc không?

**Đáp án:** Không bằng phép toán đơn giản; register chỉ giữ maximum, mất thông tin khóa/nguồn.

**Câu 19.** HLL có hỗ trợ cửa sổ trượt tự động không?

**Đáp án:** Không; thường cần sketches theo bucket thời gian và cơ chế bỏ bucket hết hạn hoặc một cấu trúc phù hợp hơn.

**Câu 20.** Vì sao output union=1481.40 khi union thật 1500 không phải bug?

**Đáp án:** HLL trả estimate xác suất; sai số có thể khác 0. Tính chất bắt buộc là merge registers giống insert union trực tiếp, không phải estimate bằng D thật.

**Câu 21.** Có thể dùng HLL để liệt kê mọi userId đã thấy không?

**Đáp án:** Không; sketches không lưu danh sách khóa.

**Câu 22.** Trong Java, phép >>> dùng để làm gì?

**Đáp án:** Lấy p bit cao của long hash bằng dịch phải không dấu, tránh sign extension.

**Câu 23.** Test nào phải luôn PASS bất kể sai số thống kê?

**Đáp án:** Duplicate idempotence, order independence, merge associative/commutative/idempotent và register equality với union trực tiếp.

**Câu 24.** RSE 3,25% có nghĩa mọi estimate sai dưới 3,25% không?

**Đáp án:** Không; đó là đại lượng độ lệch chuẩn tương đối, không phải deterministic worst-case guarantee.

**Câu 25.** Bản Java đã là HLL++ production-ready chưa?

**Đáp án:** Chưa. Nó thiếu sparse/bias correction nâng cao, serialization, đồng bộ, window management và một hash production đã kiểm định.

## 16. Bài tập thực hành

**Bài 1 — Thay precision:** chạy p=8,10,12,14 với cùng tập user-0..user-1499, giữ hash/seed như nhau. Ghi m, estimate, relative error so với HashSet và RSE lý thuyết. Không kết luận “p lớn luôn gần hơn” từ một lần chạy; đo qua nhiều seed.

**Bài 2 — Kiểm thử merge ba nhóm:** tạo A chứa user-0..user-999, B chứa user-500..user-1499, C chứa user-1200..user-1999. Kiểm tra hai cách (A merge B) merge C và A merge (B merge C) cho **cùng thanh ghi**, rồi đối chiếu với sketch nạp trực tiếp 2000 khóa.

**Bài 3 — Hash consistency:** đổi seed của sketch B và thử merge; mã phải bác bỏ. Giải thích tại sao việc bỏ kiểm tra seed có thể gây estimate sai dù hai arrays cùng kích thước.

**Bài 4 — Dữ liệu Unicode:** thử các khóa Unicode, chuỗi rỗng, chữ hoa/thường và các dạng normalize khác nhau. Chốt định nghĩa identity theo yêu cầu nghiệp vụ trước khi so với HashSet.

**Bài 5 — Sliding window:** tạo 6 sketches, mỗi sketch lưu distinct keys trong một bucket 10 phút. Để hỏi distinct của 1 giờ gần nhất, merge 6 bucket thích hợp. Mô tả sai số ở ranh giới nếu cửa sổ bắt đầu giữa một bucket.

**Bài 6 — Đo hiệu năng:** so HashSet và HLL với 10^3,10^4,10^5 khóa; đo thời gian add, query, peak memory. Phân biệt thời gian hash O(k), add O(1) sau hash, estimate O(m). Không dùng một lần chạy để đưa ra kết luận thống kê.

**Bài 7 — Trường hợp lệch:** tự tạo một hàm hash tệ luôn trả cùng 64-bit. Thấy rằng cả triệu khóa chỉ cập nhật tối đa một register; giải thích vì sao sai lệch không nằm ở công thức alpha mà ở giả thiết hash.

## 17. Tài liệu tham khảo và phạm vi áp dụng

- Philippe Flajolet, Éric Fusy, Olivier Gandouet, Frédéric Meunier (2007), *HyperLogLog: the analysis of a near-optimal cardinality estimation algorithm*. DOI: https://doi.org/10.46298/dmtcs.3545.
- Stefan Heule, Marc Nunkesser, Alexander Hall (2013), *HyperLogLog in Practice: Algorithmic Engineering of a State of the Art Cardinality Estimation Algorithm*. DOI: https://doi.org/10.1145/2452376.2452456.

Bản demo theo **cơ chế HLL cơ bản**, có alpha_m và linear counting khi ít phần tử, để người học có thể đọc và chạy trọn vẹn một class Java 17. Những triển khai HLL++ hiện đại có thêm hiệu chỉnh bias, biểu diễn sparse và các tối ưu lớn; không nên so sánh chính xác từng chữ số giữa hai implementation mà không biết phiên bản estimator/hash của chúng.

**Ghi nhớ:** HyperLogLog đếm gần đúng **số khóa phân biệt**, không đếm số sự kiện. Mỗi khóa được hash 64-bit, p bit đầu chọn bucket, suffix quyết định rho; register cập nhật bằng **max**, rồi ước lượng bằng \(\alpha_m m^2/\sum2^{-M[j]}\) và hiệu chỉnh linear counting khi nhỏ. Với m=2^p, RSE gần **1,04/√m**, không phải cận sai số chắc chắn. Merge union bằng **max từng register** là chính xác ở cấp sketch nếu cùng hash/seed/precision; cardinality estimate sau merge vẫn có sai số. Để dùng trong hệ thống thật, phải kiểm soát **hash quality, identity, phiên bản sketch, chi phí lưu nhiều nhóm và window semantics**.
