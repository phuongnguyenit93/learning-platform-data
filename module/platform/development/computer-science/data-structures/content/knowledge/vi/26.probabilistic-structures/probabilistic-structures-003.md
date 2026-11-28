# Dương tính giả và điều kiện bảo đảm không có âm tính giả của Bloom filter

Một **Bloom filter** có thể giúp loại nhanh những khóa chắc chắn chưa được đưa vào một tập, chỉ bằng một mảng bit nhỏ. Nhưng nó có một đặc điểm khác với set hoặc dictionary thông thường: **kết quả dương tính và âm tính không có cùng mức độ chắc chắn**.

Trong mô hình Bloom filter chuẩn, **chỉ thêm khóa** (*insert-only*):

- **True** nghĩa là **“có thể đã được thêm”**; một khóa chưa thêm vẫn có thể trả True. Đó là **dương tính giả** (*false positive*, FP).
- **False** nghĩa là **“chắc chắn chưa được thêm”** đối với tập mà bộ lọc thực sự biểu diễn; một khóa đã add thành công không thể trả False nếu các bất biến và điều kiện vận hành được giữ đúng. Đó là bảo đảm **không có âm tính giả** (*no false negatives*, no FN).

Từ “chắc chắn” cần được đọc chính xác. Bloom filter chỉ biết tập khóa đã được **thực sự mã hóa vào mảng bit**; nó không biết một bản ghi vừa được thêm vào database nhưng chưa được chuyển đến bộ lọc, hay một thao tác add đang cập nhật dở. Vì vậy phải phân biệt **bảo đảm toán học của cấu trúc** với **bảo đảm nhất quán của hệ thống sử dụng nó**.

Bài thuộc chương **Cấu trúc xác suất** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo định hướng học cấu trúc dữ liệu qua bất biến, thao tác và độ phức tạp thời gian/bộ nhớ để lựa chọn cấu trúc phù hợp, bài tập trung vào **sai số một phía, cách chứng minh và giới hạn của lời hứa “không âm tính giả”**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định **đối tượng được hỏi membership** là tập đã add vào Bloom hay tập của một nguồn dữ liệu khác.
2. Phân biệt **true positive, false positive, true negative, false negative** và nêu đúng mẫu số khi đo tỷ lệ FP.
3. Truy vết bit của Bloom filter bằng các vị trí băm cho sẵn, tìm ví dụ dương tính giả và ví dụ âm tính thật.
4. Chứng minh **không âm tính giả** bằng bất biến bit chỉ chuyển **0→1** và suy luận phản đảo hợp lệ.
5. Hiểu tại sao dương tính giả vẫn xảy ra dù thuật toán đúng và hàm băm không hỏng.
6. Phân tích công thức xấp xỉ FPR theo **n khóa phân biệt, m bit và h vị trí băm**, biết điều kiện xác suất của mô hình.
7. Phân biệt FPR với tỷ lệ câu trả lời True thực sự sai, và dùng **base rate** để tính một ví dụ.
8. Nhận diện những tình huống có thể gây **âm tính sai ở cấp hệ thống**: thiếu add, mất cập nhật, xóa bit, đổi hash/seed, khôi phục snapshot cũ, race và đọc database khác phiên bản.
9. Viết một Bloom filter Python **chỉ thêm, băm xác định, không xóa bit**, cùng ví dụ tra cứu nguồn chính xác.
10. Phân tích chi phí **O(h)** phép băm/bit và **O(m)** bit, cùng tác động của kích thước khóa/hashing.
11. Đề xuất cách đo FPR, kiểm tra không FN và quản lý snapshot, cập nhật đồng thời, xóa/hết hạn hoặc mở rộng dung lượng.
12. Giải thích vì sao Bloom True không thể làm bằng chứng độc lập cho nghiệp vụ đòi tính đúng tuyệt đối.

## 2. Định nghĩa chính xác: đang so với tập nào?

Đặt:

- **U**: Không gian các khóa có thể xuất hiện.
- **S**: Tập những khóa đã được add **hoàn tất và được ghi nhận thành công** trong bộ lọc.
- **B**: Mảng bit hiện tại của Bloom filter.
- **M(x,B)**: Kết quả truy vấn membership của khóa x trên trạng thái B.

Một bộ lọc chỉ-thêm chuẩn bảo đảm:

\[
\boxed{x\in S\Longrightarrow M(x,B)=\mathrm{True}.}
\]

Điều này nói rằng **không có false negative đối với S**, không phải “mọi khóa có mặt ở bất kỳ hệ thống bên ngoài nào đều được nhận diện”.

Giả sử database đã có khóa X nhưng X **chưa được add vào Bloom**. Theo định nghĩa, X có thể thuộc tập của database nhưng **chưa thuộc S**. Nếu Bloom trả False, cấu trúc không vi phạm định lý phía trên. Tuy nhiên, ứng dụng mà dùng False để kết luận X không có trong database **đã sai về tính nhất quán**.

### 2.1. Bảng bốn khả năng

| Sự thật so với S | Bloom trả True (“có thể có”) | Bloom trả False (“không có”) |
| --- | --- | --- |
| x ∈ S | **True positive (TP)** | **False negative (FN)** |
| x ∉ S | **False positive (FP)** | **True negative (TN)** |

Với filter insert-only đúng hợp đồng:

- **TP**: Khóa đã thêm, trả True.
- **TN**: Khóa chưa thêm, trả False.
- **FP**: Khóa chưa thêm, nhưng trả True vì các bit đã được khóa khác bật.
- **FN**: Khóa đã thêm, nhưng trả False — **không thể xảy ra** nếu các tiền điều kiện được giữ.

**Chú ý:** “Chưa thêm vào filter” khác “chưa thấy trong database”, và “False” không có nghĩa “khóa sẽ không bao giờ xuất hiện trong tương lai”.

### 2.2. Bảo đảm xác định và tỷ lệ lỗi xác suất

Không FN là một **bất biến xác định** của thuật toán bit khi các phép băm nhất quán và cập nhật hoàn tất. Nó **không phải** phát biểu “xác suất FN bằng 0,01%”.

Ngược lại, FP là kết quả có thể xảy ra tùy **các bit được khóa khác bật như thế nào**. Tỷ lệ FP thường được ước tính xác suất dựa trên mô hình phân bố/họ hàm băm. Nó không đồng nghĩa thuật toán tung đồng xu mới sau mỗi lần query.

## 3. Cách Bloom filter lưu dấu vết khóa

Một Bloom filter chuẩn có:

- **m** bit, lúc tạo đều bằng 0.
- **h** phép chọn vị trí băm cho mỗi khóa, với h ≥ 1.
- Những hàm/vị trí **H₀(x), H₁(x), …, H_(h−1)(x)** thuộc khoảng 0 đến m−1.

~~~text
Mảng bit ban đầu, m = 8:

chỉ số  0 1 2 3 4 5 6 7
bit     0 0 0 0 0 0 0 0
~~~

Các vị trí cho một khóa được xác định **tái lập**: add và query cùng khóa với cùng tham số phải luôn tính ra cùng các vị trí.

### 3.1. Thao tác add

~~~text
ADD(x):
    với mỗi i = 0..h-1:
        j = H_i(x)
        bit[j] = 1
~~~

Thao tác chỉ **bật** bit. Không đọc, cập nhật hoặc giữ riêng bộ đếm số khóa dùng chung một bit.

### 3.2. Thao tác query

~~~text
MIGHT_CONTAIN(x):
    với mỗi i = 0..h-1:
        j = H_i(x)
        nếu bit[j] = 0:
            return False
    return True
~~~

**Định nghĩa kết quả:** Nếu **một vị trí là 0**, khóa không thể đã được add thành công (theo bất biến). Nếu **tất cả vị trí là 1**, khóa **có thể** đã được add, nhưng các vị trí 1 không chứa thông tin nguồn gốc.

### 3.3. Không có yêu cầu các vị trí băm phải khác nhau

Cùng một khóa có thể sinh hai chỉ số trùng nhau; add và query vẫn kiểm tra các chỉ số tương ứng, nên điều này **không tạo âm tính giả**. Nhưng nó có thể làm hiệu quả phân bố và FPR thực tế khác mô hình lý tưởng.

## 4. Truy vết: dương tính giả xuất hiện dù không có lỗi

Giả sử **m=8, h=2**, các vị trí được cho sẵn:

| Khóa | Vị trí băm | Đã add? |
| --- | --- | --- |
| A | {1, 4} | Có |
| B | {4, 6} | Có |
| C | {1, 6} | **Không** |
| D | {2, 4} | **Không** |

Ban đầu:

~~~text
        0 1 2 3 4 5 6 7
bits:   0 0 0 0 0 0 0 0
~~~

Sau **add(A)**:

~~~text
        0 1 2 3 4 5 6 7
bits:   0 1 0 0 1 0 0 0
~~~

Sau **add(B)**:

~~~text
        0 1 2 3 4 5 6 7
bits:   0 1 0 0 1 0 1 0
~~~

Giờ query từng khóa:

| Query | Kiểm tra | Kết quả | Phân loại |
| --- | --- | --- | --- |
| A | bit 1 = 1, bit 4 = 1 | True | TP |
| B | bit 4 = 1, bit 6 = 1 | True | TP |
| C | bit 1 = 1, bit 6 = 1 | **True** | **FP** |
| D | bit 2 = 0, bit 4 = 1 | False | TN |

**C chưa từng được add**, nhưng A bật bit 1 và B bật bit 6, khiến C có đủ hai bit 1. Đó là ví dụ FP hoàn toàn hợp lệ.

**D chưa được add** và còn bit 2 bằng 0, nên trả False. Đây là **âm tính thật** (*true negative*), không phải false negative.

### 4.1. Tại sao khóa khác có thể cùng tạo dấu vết?

Bloom filter chỉ lưu điều kiện “ít nhất một khóa nào đó bật bit j”, không lưu **khóa nào** bật bit. Hai tập khóa hoàn toàn khác nhau có thể cho cùng mảng bit. Vì vậy, không thể đảo ngược một kết quả True thành kết luận chính xác về danh tính khóa.

### 4.2. Dữ liệu đầy đủ khác dữ liệu gốc

Ngay cả khi mọi vị trí bit của A đều bằng 1, bộ lọc không thể khôi phục payload hoặc số lần A xuất hiện. Nó cũng **không thể liệt kê** tất cả khóa đã add. Bloom filter là một **summary membership** chứ không phải nguồn sự thật.

## 5. Chứng minh không âm tính giả bằng bất biến

Đặt \(B_t[j]\) là bit tại vị trí j sau t thao tác add hợp lệ.

**Bất biến đơn điệu:**

\[
B_{t+1}[j]\ge B_t[j],\qquad B_t[j]\in\{0,1\}.
\]

Điều này đúng vì phép gán bit[j] = 1 không thể làm bit 1 trở về 0.

Giả sử khóa x được add ở thời điểm t. Theo định nghĩa add:

\[
B_t[H_i(x)]=1
\quad\text{với mọi }i=0,\ldots,h-1.
\]

Do không có bước tắt bit, với mọi thời điểm \(t'\ge t\):

\[
B_{t'}[H_i(x)]=1.
\]

Khi query x, tất cả vị trí đều 1, nên:

\[
\boxed{x\in S_{\text{inserted}}\Rightarrow
\mathrm{mightContain}(x)=\mathrm{True}.}
\]

Lấy **phản đảo**:

\[
\boxed{\mathrm{mightContain}(x)=\mathrm{False}
\Rightarrow x\notin S_{\text{inserted}}.}
\]

Đó là cơ sở logic của câu **“False chắc chắn vắng mặt”**.

### 5.1. Phản đảo hợp lệ, đảo mệnh đề không hợp lệ

Từ **đã add ⇒ True**, ta được **False ⇒ chưa add** (phản đảo). Nhưng **True ⇒ đã add** là mệnh đề đảo, **không** được chứng minh. Trường hợp C trong mục 4 phản ví dụ trực tiếp cho chiều đảo.

~~~text
ĐÚNG:
đã add    => tất cả bit = 1 => query True
query False => có ít nhất một bit = 0 => chưa add

SAI:
query True => chắc chắn đã add
(ngược với phản ví dụ C bị dương tính giả)
~~~

### 5.2. Chứng minh đúng ngay cả khi bit đã gần bão hòa

Nếu gần như toàn bộ m bit bằng 1, filter có thể trả True cho rất nhiều khóa lạ; **FPR tăng**. Nhưng với mọi khóa đã add, các bit vẫn không bị tắt, nên **không FN** vẫn đúng.

Nếu **tất cả bit đều 1**, mọi query True. Bloom không còn loại được khóa vắng mặt, nhưng vẫn không tạo false negative. Vì thế **không FN** và **FPR nhỏ** là hai tính chất độc lập.

### 5.3. Không FN không đồng nghĩa an toàn cho mọi mục đích

Nếu hệ thống bỏ qua xử lý một sự kiện mới chỉ vì Bloom trả True, một FP có thể làm **mất sự kiện mới**. Bảo đảm không FN chỉ giúp loại khóa **vắng mặt** ở nhánh False, không khiến nhánh True trở thành chứng cứ đủ mạnh để loại việc quan trọng.


## 6. Điều kiện đầy đủ để bảo đảm không âm tính giả

Chứng minh trong mục 5 ngắn vì nó dựa trên một nhóm **tiền điều kiện rất cụ thể**. Khi hệ thống thực tế không thỏa những điều kiện ấy, người dùng không thể tiếp tục nói một cách vô điều kiện rằng Bloom “không bao giờ trả âm tính sai”.

### 6.1. Add phải hoàn tất thành công

Một khóa mới được **xếp vào hàng chờ add** không đồng nghĩa nó đã được biểu diễn trong mảng bit.

~~~text
T0: Ứng dụng nhận yêu cầu thêm khóa X.
T1: X đang chờ worker xử lý.
T2: Truy vấn Bloom(X) thấy một bit 0 → False.
T3: Worker cuối cùng mới add(X) thành công.
~~~

Tại T2, X **chưa nằm trong tập khóa đã add thành công S**, nên Bloom không vi phạm bảo đảm toán học. Nếu người gọi hiểu “đã nhận yêu cầu thêm” là “phải được query nhìn thấy”, thì hệ thống cần một **hợp đồng hoàn tất/nhìn thấy thao tác** khác.

### 6.2. Băm và mã hóa khóa phải bất biến

Hai thao tác **add(x)** và **query(x)** phải tính đúng **cùng tập vị trí**:

- Cùng độ dài bit **m**.
- Cùng số vị trí băm **h**.
- Cùng thuật toán hash và cách tạo các hash.
- Cùng **seed / salt / version**.
- Cùng kiểu dữ liệu đầu vào và **encoding**.
- Cùng quy tắc **chuẩn hóa khóa** (case, Unicode, ký tự phân cách...).

Nếu add x theo hash H_old nhưng query theo H_new, bit tương ứng với H_new(x) có thể là 0. Kết quả False lúc ấy không nói gì về việc x từng được add theo cấu hình cũ.

Ví dụ:

~~~text
ADD("A") với m=8, H_old(A)={1,4}
Mảng có bit 1 và 4 = 1.

Phần mềm mới dùng H_new(A)={1,5}.
Bit 5 còn 0.

QUERY("A") → False.
~~~

Đây là **lỗi không tương thích cấu hình**, không phải chứng minh Bloom sai trong mô hình cố định.

### 6.3. Không tắt bit sau khi add

Bloom bit chuẩn chỉ hỗ trợ **0→1**. Nếu xóa khóa A bằng cách tắt các bit của A, có thể tắt cả bit mà B vẫn cần.

~~~text
H(A)={1,4}
H(B)={4,6}

ADD(A), ADD(B): bit 1,4,6 = 1.

"Xóa A" bằng cách tắt bit 1 và 4:
bit 4 trở thành 0.

QUERY(B): kiểm tra bit 4 và 6 → False.
B đã add, giờ bị âm tính giả.
~~~

Do đó **delete bằng cách reset bit** không phải thao tác hợp lệ của Bloom chuẩn. Nếu bài toán bắt buộc xóa, cần một thiết kế khác như **counting Bloom** có điều kiện thao tác rõ ràng, hoặc xây lại bộ lọc từ dữ liệu có thẩm quyền.

### 6.4. Không mất cập nhật khi đồng thời

Phép OR từng bit có tính đơn điệu về toán học, nhưng **không phải mọi phép đọc–sửa–ghi byte đều nguyên tử**.

Giả sử hai luồng muốn bật các bit khác nhau trong **cùng một byte**:

~~~text
byte ban đầu = 00000000

Luồng A đọc 00000000, định ghi 00000010.
Luồng B đọc 00000000, định ghi 00001000.

A ghi 00000010.
B ghi 00001000, đè lên bản A.

Kết quả cuối 00001000, bit của A bị mất.
~~~

Với cách cập nhật không nguyên tử, một khóa A được báo add thành công có thể thiếu bit, dẫn tới False. Phải có **atomic fetch-or, khóa bảo vệ hoặc cơ chế đồng bộ tương ứng**.

### 6.5. Query không được tin một add đang dở

Ngay cả khi mỗi thao tác bật bit là nguyên tử, **cả thao tác add h vị trí** không nhất thiết nguyên tử như một giao dịch.

~~~text
ADD(X) cần bật bit 2, 5, 7.
Đã bật bit 2 và 5, chưa kịp bật 7.

QUERY(X) chạy đồng thời: thấy bit 7 = 0 → False.

Sau đó ADD(X) bật xong bit 7.
~~~

Nếu **add chưa công bố hoàn tất**, False không trái với bảo đảm “không FN cho các add hoàn tất”. Nếu ứng dụng đòi truy vấn đồng thời nhìn thấy ngay từ lúc nhận yêu cầu add, phải dùng cơ chế nhất quán có định nghĩa **thời điểm linearization / publication**.

### 6.6. Snapshot không được bị lùi hoặc hỏng

Một filter phục hồi từ snapshot cũ có thể chưa chứa khóa đã add sau snapshot ấy. Nếu chương trình gắn nhãn “đã khôi phục thành công và sẵn sàng cho mọi dữ liệu mới” mà không replay update, nó có thể trả False cho khóa thực tế đang tồn tại.

Ngoài ra, dữ liệu bị hỏng, bộ nhớ bị ghi sai hoặc mất bit khi serialization có thể phá bất biến. Cần lưu metadata/hash version, checksum và có chiến lược replay/tái xây phù hợp.

### 6.7. Bảng phân biệt lỗi mô hình và lỗi hệ thống

| Hiện tượng | Có trái với Bloom chuẩn insert-only đã thêm thành công không? | Giải thích |
| --- | --- | --- |
| Khóa chưa add, query True | **Không** | Dương tính giả được phép |
| Khóa chưa add, query False | **Không** | Âm tính thật |
| Khóa đã add thành công, hash/bit đúng, query False | **Có** | Vi phạm bất biến hoặc lỗi triển khai |
| Database có khóa nhưng chưa add vào Bloom, query False | **Không đối với S**, nhưng có thể **sai ứng dụng** | Filter không bao phủ database |
| Add đang thực hiện dở, query False | **Không với hợp đồng chỉ bảo đảm sau khi hoàn tất** | Tùy nhất quán giao dịch |
| Đổi seed sau khi add, query False | **Bên ngoài giả định** | Add/query không còn cùng vị trí |
| Tắt bit để xóa, query khóa khác False | **Bên ngoài giả định** | Bit đã không còn đơn điệu |
| Chỉ 1/2 số bit được bật do mất cập nhật, query False | **Lỗi triển khai** | Add đã báo thành công nhưng không lưu đủ trạng thái |

## 7. Công thức xác suất dương tính giả

Bảo đảm **không FN** đến từ bất biến. Muốn ước lượng **FP**, ta cần thêm một mô hình xác suất về vị trí băm.

Giả sử:

- **m**: số bit, m ≥ 1.
- **h**: số vị trí băm mỗi khóa, h ≥ 1.
- **n**: số khóa phân biệt đã thêm.
- Những vị trí băm của khóa được xem là đủ đều và gần độc lập trong phân tích kinh điển.

### 7.1. Một bit chưa được bật

Xác suất **một lần chọn vị trí** không chọn một bit cụ thể:

\[
1-\frac1m.
\]

Có hn lượt chọn vị trí khi thêm n khóa, nên xác suất bit cụ thể còn bằng 0 xấp xỉ:

\[
P(B[j]=0)=\left(1-\frac1m\right)^{hn}
\approx e^{-hn/m}.
\]

Từ đó xác suất bit đã bật:

\[
q=P(B[j]=1)\approx1-e^{-hn/m}.
\]

### 7.2. Một khóa chưa thêm bị false positive

Một khóa lạ trả True khi **tất cả h vị trí query đều là 1**. Xấp xỉ kinh điển:

\[
\boxed{p_{\mathrm{FP}}\approx\left(1-e^{-hn/m}\right)^h.}
\]

Đây không phải công thức xác định của một mảng bit cụ thể. Mảng bit thực tế, họ hash và phân bố khóa có thể tạo FPR khác giá trị ước lượng.

**Phân biệt:** Tỷ lệ FP thống kê được định nghĩa trên **những truy vấn thật sự âm tính**. Nếu những khóa âm tính được chọn khác hẳn mô hình ngẫu nhiên đã giả định, kết quả đo có thể lệch đáng kể.

### 7.3. Tác động của n, m, h

- **Tăng n**, m và h giữ nguyên: nhiều bit 1 hơn, FPR thường **tăng**.
- **Tăng m**, n giữ nguyên và chọn h phù hợp: có nhiều bit để phân tán dấu vết, FPR có thể **giảm**.
- **Tăng h** khi m và n giữ nguyên: ban đầu có thể giúp, nhưng khi h quá lớn bit bão hòa nhanh và FPR **tăng trở lại**.

Không có quy tắc “thêm hash luôn chính xác hơn”. Số hash cũng làm tăng số phép tính trong add/query.

### 7.4. Số hash và số bit gần tối ưu

Với n, m cố định, số vị trí băm gần tối ưu:

\[
\boxed{h_\mathrm{opt}\approx\frac mn\ln2.}
\]

Cần chọn **số nguyên h ≥ 1** gần giá trị ấy.

Muốn FPR mục tiêu p với n khóa phân biệt dự kiến:

\[
\boxed{m\approx-\frac{n\ln p}{(\ln2)^2}.}
\]

Đơn vị m là **bit**, không phải byte.

Ví dụ với n=100.000 và p=1%:

~~~text
m ≈ 958 506 bit ≈ 119 814 byte ≈ 117 KiB.
h ≈ (m/n)*ln(2) ≈ 6,64 → chọn 7 hash.
~~~

**Cảnh báo:** Những số này dựa trên giả định hash lý tưởng và số khóa phân biệt dự kiến. Một hệ thống thực cần theo dõi số khóa đã thêm, độ bão hòa và FPR thực đo.

### 7.5. Sai số xác suất không phải xác suất sai độc lập trên mỗi lần gọi

Với hash và bit array cố định, cùng khóa x sẽ đi đến **cùng vị trí**, nên:

~~~text
Nếu C là false positive hôm nay
và trạng thái/filter/hash không đổi,

QUERY(C) sáng: True
QUERY(C) trưa: True
QUERY(C) tối:  True
~~~

Không có ba lần tung đồng xu độc lập. Dùng câu “mỗi lần query sai với xác suất 1% độc lập” để dự báo chuỗi lặp cùng khóa là **không đúng mô hình**.

### 7.6. Thêm cùng một khóa nhiều lần không bằng thêm nhiều khóa mới

Trong Bloom bit chuẩn, add(x) lặp lại chỉ bật lại các bit cũ. n trong công thức thiết kế nên phản ánh **số khóa phân biệt**, không phải tổng số lời gọi add. Nếu 1 triệu sự kiện chỉ có 1.000 mã phân biệt, một Bloom chứa các mã ấy có tình trạng bit khác xa mô hình 1 triệu khóa phân biệt.

## 8. FPR và xác suất một câu trả lời True là sai

Giả sử:

- Tỷ lệ truy vấn **thực sự hỏi khóa có** là \(\alpha\).
- Tỷ lệ truy vấn **thực sự hỏi khóa không có** là \(1-\alpha\).
- FPR đối với truy vấn âm tính là p.
- Với khóa đã add đầy đủ, Bloom luôn trả True.

Trong mô hình này:

\[
P(\mathrm{True})=\alpha+p(1-\alpha).
\]

Xác suất câu trả lời True là false positive:

\[
\boxed{
P(\mathrm{FP}\mid\mathrm{True})
=\frac{p(1-\alpha)}{\alpha+p(1-\alpha)}.
}
\]

Đây là một cách dùng **xác suất có điều kiện**; FPR p không đồng nghĩa tỷ lệ kết quả True bị sai.

### 8.1. Ví dụ tỷ lệ khóa thật có bằng 5%

Giả sử 100.000 truy vấn, trong đó 5.000 truy vấn hỏi khóa thật có, 95.000 hỏi khóa không có, và FPR kỳ vọng p=1%.

~~~text
Truy vấn thật có:            5 000 → True positive = 5 000
Truy vấn thật không:        95 000

False positive kỳ vọng:        950
True negative kỳ vọng:      94 050

Tổng Bloom trả True:         5 950
Trong những True, sai:          950 / 5 950 ≈ 15,97%.
~~~

Như vậy **FPR 1%** vẫn có thể đi cùng gần **16% kết quả True bị sai** khi tỷ lệ khóa thực sự tồn tại thấp.

### 8.2. Khi phần lớn khóa không tồn tại

Nếu tỷ lệ thực sự có chỉ **0,1%** và FPR là 1%, số dương tính giả có thể **nhiều hơn số dương tính thật**. Trong workload ấy, nhánh True của Bloom khá nhiễu, dù nhánh False vẫn đáng tin theo các tiền điều kiện.

Điều này không làm bộ lọc vô dụng: nó vẫn có thể loại phần lớn truy vấn âm tính, nhưng phải tính **chi phí xác minh nhánh True**.

### 8.3. Khi phần lớn khóa tồn tại

Nếu gần như mọi khóa đều có, Bloom sẽ trả True cho phần lớn truy vấn và chỉ loại được rất ít trường hợp. Khi đó CPU bỏ ra để băm và duy trì filter có thể vượt lợi ích tránh các truy vấn nguồn chính xác.

**Quyết định hiệu năng:** Xác định tỷ lệ truy vấn âm tính, chi phí nguồn chính xác, kích thước khóa, h và chi phí cập nhật. Không chỉ nhìn con số FPR.

## 9. Chiều sai số giúp ta quyết định điều gì?

Bảo đảm no FN cho Bloom **chỉ hỗ trợ một hướng tối ưu an toàn** trong trường hợp filter biểu diễn đầy đủ tập:

~~~text
Bloom(x) = False
    → x chắc chắn vắng trong tập filter biểu diễn.
    → có thể bỏ qua tra cứu sâu, nếu tập mục tiêu được bao phủ.

Bloom(x) = True
    → x có thể có HOẶC không.
    → nếu cần chính xác, tiếp tục hỏi nguồn có thẩm quyền.
~~~

Đây là lý do Bloom thường đặt **trước truy vấn tốn I/O**, chứ không dùng để xác nhận danh tính.

### 9.1. Bỏ qua việc đắt tiền ở nhánh False

Trong một SSTable bất biến, nếu filter được xây đầy đủ cho những khóa có trong SSTable ấy và query cùng phiên bản cấu hình, Bloom False có thể cho phép **bỏ qua truy cập SSTable**.

Nhưng nếu cùng một khóa cũng có thể nằm trong SSTable khác hoặc memtable mới hơn, Bloom False của **một SSTable** không kết luận khóa vắng trong **toàn database**.

### 9.2. Khi nhánh True dẫn tới hành động không thể đảo ngược

Nếu một ứng dụng chống trùng lặp thấy Bloom True rồi **bỏ qua sự kiện mới**, một false positive có thể làm mất dữ liệu. Nếu thấy Bloom True rồi **truy vấn ID chính xác**, hệ thống vẫn có thể bảo toàn kết quả.

Tương tự, không được dùng Bloom True để **cấp quyền**, xác nhận đã thanh toán hoặc coi một người dùng đã được kiểm tra KYC. Những tác vụ ấy cần nguồn chứng thực/ủy quyền chính xác.

### 9.3. Tăng tốc không đồng nghĩa thay thế nguồn sự thật

Bloom filter giảm số lượng **kiểm tra cần thực hiện** chứ không mang theo bằng chứng đủ mạnh để khẳng định thành viên. Khi cần liệt kê khóa, tìm payload, đếm tần suất hay xóa chính xác, cấu trúc cần có thêm **set/dictionary/index** hoặc công cụ khác.


## 10. Python tự chứa: kiểm chứng một phía của Bloom filter

Bài dùng Python 3.10 trở lên. Hai ví dụ dưới đây có mục đích khác nhau: ví dụ đầu **cố định bảng vị trí băm** để thấy một FP cụ thể; ví dụ sau dùng một hàm băm xác định để minh họa cách cài đặt khi số khóa có thể lớn.

### 10.1. Phản ví dụ FP xác định

~~~python
positions = {
    "A": (1, 4),
    "B": (4, 6),
    "C": (1, 6),
    "D": (2, 4),
}
bits = [0] * 8

def toy_add(key: str) -> None:
    for j in positions[key]:
        bits[j] = 1

def toy_might_contain(key: str) -> bool:
    return all(bits[j] for j in positions[key])


toy_add("A")
toy_add("B")

assert bits == [0, 1, 0, 0, 1, 0, 1, 0]
assert toy_might_contain("A") is True
assert toy_might_contain("B") is True
assert toy_might_contain("C") is True   # FP: C chưa add.
assert toy_might_contain("D") is False  # TN: D chưa add.
~~~

Không phải mọi khóa chưa add đều trả False: C là ví dụ **false positive chính xác và có chủ đích**, không phải bug.

### 10.2. Bloom filter dùng bytearray và hash tái lập

Mã chỉ nhận **str** và dùng **SHA-256** với chỉ số vị trí và tiền tố version; cùng khóa/phiên bản/cấu hình tạo cùng kết quả. Đây là **cài đặt giáo dục**, không tự chứng minh giả định độc lập tuyệt đối của các hash theo mô hình FPR lý tưởng và chưa được kiểm định sản xuất.

~~~python
from __future__ import annotations
import hashlib
import math


class BloomFilter:
    def __init__(self, expected_items: int, target_fp: float):
        if (
            isinstance(expected_items, bool)
            or not isinstance(expected_items, int)
            or expected_items <= 0
        ):
            raise ValueError("expected_items phải là int dương")

        if not (0.0 < target_fp < 1.0):
            raise ValueError("target_fp phải trong khoảng (0,1)")

        self.expected_items = expected_items
        self.target_fp = target_fp
        ln2 = math.log(2.0)

        self.m = max(
            1,
            math.ceil(
                -expected_items * math.log(target_fp) / (ln2 * ln2)
            ),
        )
        self.h = max(1, round(self.m * ln2 / expected_items))
        self.bits = bytearray((self.m + 7) // 8)

    def _positions(self, key: str):
        if not isinstance(key, str):
            raise TypeError("Ví dụ chỉ nhận khóa str")

        encoded = key.encode("utf-8")
        for i in range(self.h):
            digest = hashlib.sha256(
                b"bloom-no-fn-v1|"
                + i.to_bytes(8, "big")
                + b"|"
                + encoded
            ).digest()
            yield int.from_bytes(digest, "big") % self.m

    def add(self, key: str) -> None:
        for j in self._positions(key):
            self.bits[j // 8] |= 1 << (j % 8)

    def might_contain(self, key: str) -> bool:
        for j in self._positions(key):
            if (self.bits[j // 8] & (1 << (j % 8))) == 0:
                return False
        return True

    def set_bit_count(self) -> int:
        return sum(byte.bit_count() for byte in self.bits)


bf = BloomFilter(expected_items=1000, target_fp=0.01)
known = [f"event-{i}" for i in range(1000)]

for key in known:
    bf.add(key)

# Mọi khóa đã add đều trả True: bất biến không FN.
assert all(bf.might_contain(key) for key in known)

assert bf.m >= 1
assert bf.h >= 1
assert len(bf.bits) == (bf.m + 7) // 8
assert 0 <= bf.set_bit_count() <= bf.m

# Một khóa chưa add có thể trả True hoặc False.
unknown = bf.might_contain("not-added")
assert isinstance(unknown, bool)

before = bytes(bf.bits)
bf.add("event-5")
assert bytes(bf.bits) == before   # Add trùng không đổi bit.

empty = BloomFilter(expected_items=10, target_fp=0.05)
assert empty.might_contain("anything") is False

try:
    BloomFilter(0, 0.01)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối n không dương")

try:
    BloomFilter(10, 1.0)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối p ngoài (0,1)")
~~~

### 10.3. Cách truy cập một bit trong bytearray

Với bit có chỉ số j:

~~~text
byte_index = j // 8
bit_offset = j % 8
bit_mask   = 1 << bit_offset
~~~

Bật bit bằng OR, kiểm tra bit bằng AND. Nếu m không chia hết cho 8, byte cuối có những bit dư, nhưng không vị trí hash nào trỏ ngoài khoảng **[0,m)**.

**m là số bit logic; bytearray cấp phát ceil(m/8) byte.** Hãy phân biệt vùng nhớ bit với overhead object, digest, m/h, seed và buffer.

### 10.4. Vì sao không ép mọi khóa lạ trả False?

Nếu thêm nhiều khóa và chọn một khóa chưa add, kết quả có thể là True do FP. Vì vậy assertion kiểu **might_contain(unknown) is False** không phải bất biến của Bloom; các bộ kiểm chứng đúng chỉ yêu cầu **mọi khóa đã add đều trả True** rồi đo tỷ lệ FP riêng trên một tập khóa âm tính có nhãn sự thật.

### 10.5. Hash phiên bản và restart

Không nên lưu mảng bit rồi dựa vào **hash() mặc định của Python cho str** mà không quản lý hash seed/runtime: hash của một số kiểu có thể thay đổi theo process.

Nếu hash mới tạo vị trí khác, query sau restart có thể trả False cho khóa từng add. Mã dùng tiền tố version nhằm minh họa tính tái lập; hệ thống thực phải lưu **m, h, hash version, seed, encoding và quy tắc chuẩn hóa** cùng với mảng bit.

## 11. Kết hợp Bloom và nguồn chính xác: không để FP thành kết luận sai

Bloom hữu ích làm **prefilter**:

~~~text
Client hỏi khóa X
     |
     v
Bloom.might_contain(X)?
  |                 |
False             True
  |                 |
Loại nhanh       Query DB hoặc set
nếu filter       có thẩm quyền
bao phủ dữ liệu      |
                  Trả đúng theo DB
~~~

### 11.1. Ví dụ snapshot bất biến bằng Python

Đoạn code này sử dụng **lớp BloomFilter định nghĩa ở mục 10**. Nguồn có thẩm quyền là **frozenset cố định**, được chụp trước khi tạo Bloom, nên không có cập nhật làm bộ lọc lạc hậu.

~~~python
from collections.abc import Iterable


class ExactMembershipWithBloom:
    def __init__(self, snapshot_keys: Iterable[str], fp: float):
        self.exact = frozenset(snapshot_keys)
        self.filter = BloomFilter(
            max(1, len(self.exact)), fp
        )

        for key in self.exact:
            self.filter.add(key)

        self.exact_lookups = 0

    def contains(self, key: str) -> bool:
        if not self.filter.might_contain(key):
            # Filter bao phủ đầy đủ snapshot -> đúng là không có.
            return False

        self.exact_lookups += 1
        return key in self.exact


index = ExactMembershipWithBloom(["A", "B", "C"], 0.01)

assert index.contains("A") is True
assert index.contains("D") is False

# Kết luận cuối vẫn chính xác, dù Bloom có thể trả FP.
for key in ["A", "B", "C", "D", "E", "F"]:
    assert index.contains(key) == (key in index.exact)
~~~

Một FP ở tầng Bloom khiến hệ thống phải tra set thêm một lần, nhưng **không khiến kết quả cuối sai**. Đó là ứng dụng an toàn điển hình khi tầng lọc được xây đầy đủ từ một tập bất biến.

### 11.2. Race giữa DB và Bloom

~~~text
T1: DB INSERT(X) hoàn tất.
T2: Client hỏi X; Bloom chưa add X.
T3: Worker mới add X thành công.
~~~

Tại T2, filter có thể trả False. Không thể suy ra DB không có X: **S_filter** chưa bao phủ **S_DB**. Muốn an toàn phải có hợp đồng nhất quán: Bloom của snapshot bất biến, delta index bao phủ khóa mới, xuất bản version đồng bộ hoặc **bypass filter** khi không chứng minh được độ bao phủ.

Đổi đơn giản thứ tự ghi Bloom/DB không tự xử lý hết **rollback, replica lag, crash, read visibility và các cuộc đua đồng thời**.

### 11.3. Hai mức độ đúng khác nhau

| Kết quả | Đúng so với tập trong Bloom? | Có thể đúng so với database mới nhất? |
| --- | --- | --- |
| Filter True cho khóa lạ | FP được phép | Phải tra DB |
| Filter False cho khóa chưa add | TN | Chỉ suy ra vắng trong DB nếu filter bao phủ DB |
| Filter True cho khóa đã add | TP | Có thể DB đã xóa khóa: vẫn phải xác minh |
| Filter False cho khóa có trong DB nhưng chưa add | Không vi phạm no-FN của filter | **Có thể sai nghiêm trọng nếu ứng dụng tin False** |
| Filter False sau khi mất bit của khóa đã add | **Vi phạm bất biến** | Phải sửa triển khai/khôi phục |

### 11.4. Không dùng nhánh True làm bằng chứng nghiệp vụ

Một false positive có thể xảy ra ngay cả khi FPR mục tiêu rất thấp. Vì thế Bloom True không được dùng làm bằng chứng duy nhất cho **cấp quyền, tính tiền, thanh toán, xác nhận đã xử lý sự kiện hoặc từ chối xử lý một ID chưa từng gặp**. Nếu quyết định cần chính xác, phải kiểm tra nguồn có thẩm quyền.

## 12. Thời gian và bộ nhớ

| Thao tác | Thời gian trong mô hình hash O(1) | Bộ nhớ |
| --- | --- | --- |
| Khởi tạo m bit | Θ(m) theo đơn vị bit | Θ(m) bit |
| Add một khóa | O(h) | O(1) phụ ngoài digest |
| Query | O(h) worst-case, có thể dừng sớm khi gặp bit 0 | O(1) phụ ngoài digest |
| Đọc một bit | Θ(1) | Θ(1) |
| Đếm toàn bộ bit bật | O(m) theo đơn vị bit | O(1) phụ |
| Lưu mảng | Không phụ thuộc trực tiếp số khóa phân biệt sau cấp phát | Θ(m) bit |

Nếu h là **hằng số cố định** khi triển khai, add/query có thể được gọi là **O(1) theo n**. Nhưng khi muốn tối ưu theo FPR, h thay đổi cùng m/n nên phân tích O(h) rõ ràng hơn.

Với khóa dài L byte, phiên bản SHA-256 ở trên băm toàn bộ khóa **h lần**, nên chi phí hash có thể là **O(hL)**, chưa kể encoding và memory allocation tạm.

**Một bộ lọc gần toàn bit 1 vẫn có chi phí query O(h), nhưng rất ít khóa vắng được loại nhanh.** Do đó lợi ích thật phải được đo bằng số **truy vấn nguồn chính xác tránh được**, không chỉ tốc độ riêng của hàm query Bloom.


## 13. Xóa khóa, đếm vị trí và nguy cơ phá bảo đảm no FN

### 13.1. Xóa bằng đặt bit về 0 là không hợp lệ

Với khóa A băm vào {1,4}, B băm vào {4,6}, ta đã biết bit 4 được **chia sẻ**.

~~~text
ADD(A)    → bật 1,4.
ADD(B)    → bật 4,6.

Nếu "DELETE(A)" bằng cách tắt 1,4:
    bit 4 = 0.

QUERY(B) cần cả bit 4 và 6.
    bit 4 = 0 → False.

B vẫn có trong tập: đây là false negative!
~~~

Bộ lọc không biết bit 4 có bao nhiêu **khóa khác nhau cần đến nó**. Vì vậy Bloom chuẩn **không có thao tác delete an toàn kiểu reset bit**.

**Phân biệt hai câu:** “Bloom chỉ-thêm không FN” là đúng; “Bloom có thể xóa bit tùy ý mà vẫn không FN” là sai.

### 13.2. Counting Bloom filter

Một biến thể dùng **các ô đếm** thay mảng bit:

- **add(x):** Tăng các counter tương ứng.
- **might_contain(x):** Kiểm tra mọi counter tương ứng lớn hơn 0.
- **delete(x):** Giảm counter tương ứng, **chỉ khi x thực sự đã được add** và chưa được xóa hết số lần tương ứng.

Giả sử hai khóa dùng chung một vị trí, counter của vị trí ấy bằng 2. Xóa đúng một khóa làm nó giảm xuống 1, nên khóa còn lại vẫn được phát hiện.

Tuy nhiên, kiểu dữ liệu counter có thể tràn hoặc bão hòa, và ứng dụng có thể xóa sai khóa.

### 13.3. Xóa theo kết quả “có thể có” là sai

Nếu khóa C chưa từng add nhưng bị **false positive**, một chương trình có thể nhầm:

~~~text
if bloom.might_contain("C"):
    bloom.delete("C")      # NGUY HIỂM nếu không biết C đã add.
~~~

Với counting Bloom, việc giảm counter tại các vị trí băm của C có thể giảm **đóng góp của A/B**, dẫn tới âm tính giả cho khóa thật.

Vì vậy một counting Bloom đúng cần **nguồn thẩm quyền xác nhận quyền xóa**, đếm lần add/delete thích hợp, cơ chế tránh underflow/overflow và bảo đảm đồng bộ khi nhiều luồng cập nhật.

### 13.4. Hết hạn theo thời gian

Một Bloom chỉ-thêm không tự “quên” khóa hết hạn. Nếu cần lọc sự kiện theo cửa sổ thời gian, có thể:

- Chia thành **bộ lọc theo phân vùng thời gian** và bỏ cả phân vùng khi không còn cần.
- **Tái xây** bộ lọc theo snapshot hiện hành.
- Dùng một cấu trúc cửa sổ hoặc biến thể membership hỗ trợ xóa với hợp đồng riêng.

Không nên tự xóa một số bit “cũ” rồi tiếp tục tuyên bố bảo đảm no FN của Bloom chuẩn.

## 14. Thay đổi quy mô: n tăng không làm mất no FN nhưng làm tăng FP

Bloom chuẩn có **m và h cố định sau khởi tạo**. Khi thêm nhiều khóa phân biệt hơn dự kiến, nhiều bit bị bật, tỷ lệ FP tăng.

### 14.1. Bão hòa khác mất dữ liệu

~~~text
Mới tạo:        0000000000000000
Sau ít khóa:    0101000100010000
Sau nhiều khóa: 1111011110111110
Bão hòa:        1111111111111111
~~~

Khi toàn bộ bit bằng 1:

- Mọi query trả **True**.
- Không còn khả năng loại một khóa âm tính.
- Vẫn **không false negative** đối với khóa đã add, vì mọi vị trí đều 1.

Đó là tình huống **suy giảm hiệu quả lọc**, không phải lỗi sai phía âm tính.

### 14.2. Không đổi m của một filter cũ bằng cách kéo dài mảng bit

Giả sử A từng được băm **mod m_old** và đã bật các vị trí tương ứng. Nếu tăng số bit m nhưng **không thêm lại A**, query mới dùng **mod m_new** có thể nhìn vào vị trí chưa bật.

Như vậy, **thay m có thể tạo âm tính giả**. Các cách hợp lệ:

1. Tái xây bộ lọc lớn hơn từ **danh sách khóa chính xác**.
2. Xuất bản phiên bản mới nhất quán với phiên bản dữ liệu.
3. Dùng một kiến trúc **scalable Bloom** có nhiều lớp, trong đó query kiểm tra mọi lớp liên quan.

Không đủ để chỉ copy mảng bit cũ vào phần đầu của mảng bit mới.

### 14.3. Nhiều lớp và tổng FPR

Giả sử filter gồm L lớp; query trả True nếu **bất cứ lớp nào** trả True.

Với khóa chưa có trong lớp nào, một cận trên an toàn theo union bound là:

\[
P(\mathrm{FP\ ở\ ít\ nhất\ một\ lớp})
\le\sum_{i=1}^{L}p_i.
\]

Không cần giả định các lớp độc lập để dùng cận trên này. Nếu các sự kiện độc lập thật sự, có thể dùng:

\[
P(\mathrm{FP})\approx1-\prod_{i=1}^{L}(1-p_i).
\]

**Hai lớp mỗi lớp FPR 1% không làm tổng tự động vẫn 1%.** Các lớp cần được phân bổ **ngân sách xác suất**, và các giả định tương thích với workload phải được kiểm chứng.

### 14.4. Khi nào tái xây?

Những tín hiệu đáng theo dõi gồm số khóa phân biệt được ước lượng, tỷ lệ bit 1, FPR trên khóa âm tính có nhãn sự thật, độ trễ truy vấn, số lần chạm DB sau filter và tỷ lệ khóa chưa có trong tải thật.

Một chính sách tái xây hiệu quả phải **chọn ngưỡng theo chi phí kinh doanh**, không chỉ theo “mảng đã dùng hết bộ nhớ”: mảng Bloom vốn được cấp phát trước, và vấn đề thường là **bit bão hòa**, không phải buffer thiếu dung lượng.

## 15. Hợp nhất nhiều Bloom filter và bảo toàn no FN

Giả sử hai phân vùng có các bộ lọc B_A và B_B. Nếu chúng **tương thích hoàn toàn** về:

- m, h;
- Thuật toán hash, seed, domain separation, version;
- Encoding/normalization của khóa;
- Ý nghĩa snapshot và tập đã thêm;

thì có thể hợp nhất bằng **OR theo bit**:

\[
B_{\mathrm{union}}[j]=B_A[j]\lor B_B[j].
\]

### 15.1. Vì sao OR vẫn không FN?

Với mọi x đã add vào A, mọi bit ở các vị trí của x đều bằng 1 trong B_A. Lấy OR với B_B không thể tắt chúng, nên bộ lọc hợp nhất vẫn trả True cho x.

Lập luận tương tự áp dụng cho khóa ở B. Do đó OR bảo toàn không FN cho **hợp của hai tập được biểu diễn**, theo cùng cấu hình hash.

~~~text
A:      0 1 0 1 0 1 0 0
B:      1 0 0 1 0 0 1 0
-----------------------
A OR B: 1 1 0 1 0 1 1 0
~~~

**Lưu ý:** OR có thể bật thêm bit và làm **FPR tăng**. Hợp nhất đúng về tính không FN không đồng nghĩa giữ nguyên mức FPR của từng bộ lọc.

### 15.2. Trường hợp không được OR

Hai bộ lọc cùng m nhưng khác hash hoặc seed có thể đặt **cùng khóa vào những vị trí khác nhau**. Một mảng bit OR không xác định được cách query tương thích với cả hai bộ lọc theo một hash duy nhất.

Nếu cấu hình khác nhau, cần giữ **hai filter riêng và query cả hai**, hoặc xây lại một filter chung từ nguồn khóa chính xác, theo hợp đồng mới.

### 15.3. Không suy ra chính xác số khóa từ số bit 1

Cùng một mảng bit có thể được tạo ra bởi nhiều tập khóa. Sau OR, không thể lấy **n_A + n_B** làm số khóa phân biệt của hợp nếu hai tập có giao nhau:

\[
|A\cup B|=|A|+|B|-|A\cap B|.
\]

Bloom không tự cung cấp chính xác **|A∩B|**. Vì vậy, tính FPR của bản hợp cần ước lượng số khóa phân biệt và độ bão hòa đúng, không nhầm phép OR bit với phép cộng kích thước tập.

## 16. Kiểm thử và đo đúng “dương tính giả, không âm tính giả”

### 16.1. Chuẩn bị hai tập dữ liệu có sự thật rõ ràng

Để kiểm chứng một phiên bản filter:

- **P (positive):** Các khóa đã add thành công.
- **N (negative):** Các khóa chắc chắn chưa add, được lựa chọn độc lập với P theo phạm vi bài kiểm tra.

Hãy đảm bảo **P và N không giao nhau** nếu mục tiêu là đo FP của những khóa chưa thêm.

### 16.2. Kiểm thử bất biến

Với mọi x trong P:

~~~text
assert bloom.might_contain(x) == True
~~~

Nếu có False, phải điều tra: add chưa hoàn tất, hash mismatch, seed/version khác, bit bị xóa, snapshot cũ, lỗi đồng thời hoặc lỗi serialization.

**Không có lý do chấp nhận một tỷ lệ FN nhỏ nào đó** đối với Bloom insert-only đã add đúng. Điều kiện này là bất biến, không phải ngưỡng thống kê.

### 16.3. Đo FPR

Trong tập N, tính:

\[
\widehat{\mathrm{FPR}}
=\frac{\#\{x\in N:\mathrm{mightContain}(x)=\mathrm{True}\}}{|N|}.
\]

Đây là **FPR quan sát được trên tập N**, không tự chứng minh FPR cho mọi workload. Với N nhỏ, độ bất định thống kê lớn; với N không đại diện hoặc chứa nhiều khóa lặp, kết luận có thể lệch.

Một cách kiểm định tốt cần ghi lại:

- m, h, n dự kiến và số khóa thật đã thêm;
- version hash, seed, encoding, snapshot;
- phương pháp chọn negative key;
- số lượng mẫu âm tính, số FP, FPR quan sát;
- tỷ lệ bit 1 và số lượng byte dùng thực tế;
- độ trễ/CPU của add/query;
- số lượt truy cập nguồn chính xác được tránh.

### 16.4. Mẫu đánh giá minh họa bằng Python

Ví dụ bên dưới sử dụng **lớp BloomFilter ở mục 10**. Tập negative được tạo để không trùng tập positive trong ví dụ; không có assertion cố định nào về số FP được phép.

~~~python
positives = [f"known:{i}" for i in range(1000)]
negatives = [f"absent:{i}" for i in range(10000)]

bf = BloomFilter(expected_items=len(positives), target_fp=0.01)

for key in positives:
    bf.add(key)

false_negatives = [
    key for key in positives
    if not bf.might_contain(key)
]
assert false_negatives == []

false_positives = sum(
    1 for key in negatives
    if bf.might_contain(key)
)
observed_fpr = false_positives / len(negatives)

assert 0.0 <= observed_fpr <= 1.0
print("Observed FPR on chosen negatives:", observed_fpr)
~~~

Nếu kết quả đo 1,2% với target 1%, không thể kết luận ngay bản thân Bloom “sai”: phải xem **cỡ mẫu, biến động, giả định hash, số khóa đã add và phân bố negative**. Ngược lại, nếu một khóa đã add trả False sau khi trạng thái ổn định, cần coi đó là lỗi nghiêm trọng đối với hợp đồng insert-only.

### 16.5. Kiểm thử các trường hợp ở ngoài mô hình đơn luồng

Khi hệ thống thực có concurrency/persistence:

- Hai luồng bật **cùng một byte** theo các mặt nạ khác nhau.
- Query chạy trong lúc add đang bật h vị trí.
- Restart từ snapshot rồi replay những cập nhật sau snapshot.
- Thay version hash/seed và chuyển đổi từ filter cũ sang filter mới.
- Nhiều replica DB có thời điểm nhìn thấy giao dịch khác nhau.
- Thêm nhiều khóa vượt n thiết kế để đo bão hòa.
- Cùng khóa có nhiều biểu diễn Unicode hoặc chữ hoa/thường.
- Truy vấn lặp một false positive và truy vấn thích nghi nhằm tìm FP.

Các trường hợp này kiểm tra **hợp đồng hệ thống**, không thể được loại trừ chỉ bằng chứng minh bit đơn điệu.


## 17. Các lỗi thường gặp khi suy luận và triển khai

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “Bloom True nghĩa là khóa chắc chắn tồn tại” | Có thể có FP do các khóa khác bật đủ bit | True chỉ là **có thể có** |
| “Bloom False luôn kết luận khóa vắng trong mọi database” | Filter có thể chỉ bao phủ một snapshot/SSTable | Xác định chính xác **tập mục tiêu S** |
| “Không FN nghĩa là xác suất FN rất thấp” | Với insert-only đúng, no FN là **bất biến xác định** | Chứng minh từ bit đơn điệu |
| “FP là lỗi triển khai hash” | Chia sẻ vị trí là cơ chế nén thông tin của Bloom | Chấp nhận FP với ngân sách rõ |
| “Một bit 1 là đủ để query True” | Còn những vị trí khác có thể 0 | Chỉ True khi **mọi h bit đều 1** |
| “Một bit 0 vẫn có thể đã add” | Nếu add thành công, mọi bit đã bật | Trừ khi hợp đồng bị phá |
| “Cập nhật DB đủ rồi, filter tự biết” | Filter không đọc DB tự động | Duy trì đồng bộ/snapshot/delta |
| “Add nằm trong queue tức đã hoàn tất” | Các bit có thể chưa được bật | Định nghĩa thời điểm add được công bố |
| “Cùng khóa sẽ nhận thử xác suất FP mới mỗi query” | Hash và bit array cố định thường cho cùng kết quả | Không giả định độc lập giữa truy vấn lặp |
| “FPR=1% nghĩa là 1% mọi request sai” | FPR đo trên **negative** | FPR = FP/(FP+TN) |
| “FPR=1% nghĩa là 1% câu True sai” | Còn phụ thuộc tỷ lệ khóa thật có | Tính xác suất có điều kiện |
| “Số lượt add trùng là n phân biệt” | Add trùng không bật bit mới | Dùng số khóa phân biệt dự kiến |
| “Tăng h vô hạn sẽ làm FP thấp nhất” | Bit có thể bão hòa nhanh | h gần (m/n)ln2 |
| “Bloom tự tăng m theo n” | m và h cố định sau khi xây | Tái xây hoặc dùng scalable filter |
| “Đổi m/h/seed mà giữ bit cũ vẫn đúng” | Vị trí hash cũ không khớp | Version/rebuild toàn bộ |
| “Dùng hash() của runtime để lưu filter vĩnh viễn” | Seed/hash có thể đổi giữa tiến trình | Dùng hash tái lập và lưu metadata |
| “Xóa khóa bằng reset h bit” | Bit có thể được khóa khác sử dụng | Không xóa trực tiếp trên Bloom bit chuẩn |
| “Counting Bloom True đủ để delete” | False positive có thể làm giảm nhầm bộ đếm | Xóa khi biết khóa đã thật sự add |
| “Bit OR toán học giao hoán nên mọi cập nhật byte là atomic” | Read–modify–write có thể mất update | Atomic OR/lock thích hợp |
| “Query đang đua với add dở cũng phải thấy đủ bit” | Chưa đủ h bit được công bố | Hợp đồng hoàn tất/linearization |
| “Khôi phục bit array là đủ” | Thiếu m, h, seed, hash/encoding | Lưu metadata đầy đủ |
| “Filter cũ vẫn loại an toàn khóa DB mới” | Snapshot có thể thiếu khóa mới | Kiểm tra version/delta |
| “Hai filter cùng m có thể OR dù seed khác” | Bit không biểu diễn cùng vị trí | Chỉ OR cấu hình tương thích |
| “Các lớp Bloom đều 1% thì tổng vẫn 1%” | Các lỗi FP có thể cộng xác suất | Phân bổ ngân sách các lớp |
| “Bloom an toàn cho cấp quyền hoặc thanh toán” | FP có thể tạo quyết định sai | Xác minh bằng nguồn có thẩm quyền |
| “Chỉ đo tốc độ Bloom là đủ” | Filter tăng chi phí hash, đổi số lookup DB | Đo **độ trễ đầu-cuối** |
| “Khi tất cả bit đều 1 thì Bloom có FN” | Mọi query đều True | **FP bão hòa**, không phải FN |
| “Mẫu một khóa lạ lặp 1000 lần đo FPR tốt” | Không đại diện các khóa âm tính khác | Chọn nhiều negative có nhãn sự thật |
| “Dùng kết quả True để bỏ qua event chưa xử lý” | FP có thể làm mất event | Verify True khi không được bỏ sót |
| “Bộ lọc cho SSTable A quyết định toàn DB” | DB còn memtable/SSTable khác | Chỉ loại trong đúng phạm vi bộ lọc |

### 17.1. Checklist chứng minh no FN ở một thiết kế cụ thể

Khi đọc một thiết kế Bloom trong thực tế, kiểm tra theo thứ tự:

1. Tập khóa **được filter biểu diễn** là tập nào, ở version nào?
2. Có chắc **mọi khóa thực sự nằm trong tập ấy** đã hoàn tất add không?
3. Mọi add có bật đủ h vị trí không?
4. Mỗi vị trí add/query có được tính theo cùng m/h/hash/seed/encoding không?
5. Có thao tác nào tắt bit hoặc sửa sai byte không?
6. Cập nhật đồng thời có thể **mất bit** không?
7. Một query có thể nhìn trạng thái đang add dở không; hợp đồng hoàn tất được định nghĩa ra sao?
8. Snapshot/filter có thể chậm hơn snapshot/database được hỏi không?
9. Khóa có quy tắc chuẩn hóa thống nhất không?
10. Nếu dùng filter để **bỏ qua việc tra chính xác**, có chắc nhánh False tương ứng một tập được bao phủ đầy đủ không?

Nếu bất kỳ câu nào chưa được chứng minh, **không nên đặt niềm tin tuyệt đối vào Bloom False ở cấp ứng dụng**. Có thể vẫn dùng filter như một gợi ý hiệu năng, nhưng cần tra nguồn chính xác khi không chắc điều kiện an toàn.

## 18. Bài tập tự luyện có đáp án

### Nhóm A — Phân loại đúng/sai và suy luận một phía

**Bài 1 — Hai kết quả.** Bloom filter chuẩn trả True và False có ý nghĩa gì?

*Đáp án:* **True = có thể đã thêm**; **False = chắc chắn chưa được thêm** vào tập mà filter biểu diễn, nếu no-FN tiền điều kiện đúng.

**Bài 2 — TP.** A đã add và query(A) trả True. Đây là loại kết quả nào?

*Đáp án:* **True positive (TP)**.

**Bài 3 — FP.** C chưa từng add nhưng query(C) trả True. Đây là lỗi nào?

*Đáp án:* **False positive (FP)**; nó là sai số cho phép của Bloom.

**Bài 4 — TN.** D chưa từng add, query(D) trả False. Đây là loại nào?

*Đáp án:* **True negative (TN)**.

**Bài 5 — FN.** A đã add thành công theo cùng hash, nhưng query(A) trả False. Đây là loại nào?

*Đáp án:* **False negative (FN)**, biểu hiện bất biến bị phá; Bloom insert-only đúng hợp đồng không cho phép.

**Bài 6 — Phản đảo.** Từ “đã add ⇒ query True”, mệnh đề suy ra hợp lệ là gì?

*Đáp án:* **query False ⇒ chưa add**, theo cùng tập/phiên bản và các tiền điều kiện.

**Bài 7 — Đảo không hợp lệ.** Có được kết luận “query True ⇒ đã add” không?

*Đáp án:* **Không**. False positive là phản ví dụ.

**Bài 8 — Mảng toàn 1.** Nếu mọi bit bằng 1, filter còn no FN không?

*Đáp án:* **Có**, nhưng mọi query trả True và FPR đối với khóa lạ là **100%**.

**Bài 9 — Add lặp.** Thêm cùng khóa X 100 lần có tạo 100 tập vị trí mới không?

*Đáp án:* **Không**. Cùng hash tạo cùng h vị trí, nên thêm lặp là idempotent đối với mảng bit.

### Nhóm B — Truy vết bit và va chạm

**Bài 10 — Sau một add.** m=8, add A ở {1,4}. Những bit nào bằng 1?

*Đáp án:* **Bit 1 và 4**.

**Bài 11 — Sau hai add.** Tiếp tục add B ở {4,6}. Những bit nào bằng 1?

*Đáp án:* **{1,4,6}**.

**Bài 12 — FP xác định.** C chưa add, vị trí {1,6}. Query C trả gì?

*Đáp án:* **True (FP)**, vì cả bit 1 và bit 6 đã được bật bởi A/B.

**Bài 13 — TN xác định.** D chưa add, vị trí {2,4}. Query D trả gì?

*Đáp án:* **False (TN)**, vì bit 2 vẫn bằng 0.

**Bài 14 — Tại sao FP không cần hash trùng hoàn toàn?** C có vị trí {1,6}, nhưng không có khóa đã add nào cũng có đúng hai vị trí đó. Vì sao C vẫn True?

*Đáp án:* Vì **tập bit 1 do nhiều khóa khác nhau hợp lại** đã bao phủ các vị trí của C. Không cần một khóa đơn lẻ có cùng toàn bộ vector hash.

**Bài 15 — Trùng vị trí trong một khóa.** Hai vị trí hash của X tình cờ bằng nhau. Điều đó có tự tạo FN không?

*Đáp án:* **Không**. Add và query kiểm tra cùng vị trí; chỉ có thể ảnh hưởng hiệu quả phân bố/FPR.

### Nhóm C — Công thức và xác suất

**Bài 16 — Định nghĩa FPR.** Có 20.000 truy vấn âm tính thực và 200 lần Bloom trả True sai. FPR là bao nhiêu?

*Đáp án:* **200/20.000 = 1%**.

**Bài 17 — Công thức.** Viết xấp xỉ FPR theo h, n, m.

*Đáp án:* \(p_{\rm FP}\approx(1-e^{-hn/m})^h\) theo mô hình hash lý tưởng.

**Bài 18 — Ý nghĩa n.** Trong công thức thiết kế Bloom, n thường chỉ số gì?

*Đáp án:* **Số khóa phân biệt dự kiến được add**, không đơn thuần số lượt gọi add.

**Bài 19 — h gần tối ưu.** Với m/n=10 bit trên khóa, nên chọn khoảng bao nhiêu hash?

*Đáp án:* \(h\approx10\ln2\approx6,93\), chọn **7**.

**Bài 20 — Số bit.** Với n=100.000 và p=1%, cần khoảng bao nhiêu bit?

*Đáp án:* **958.506 bit**, tức khoảng **117 KiB** mảng bit, h khoảng 7.

**Bài 21 — h rất lớn.** Tăng h lên 100 với m và n cố định có chắc làm FPR giảm không?

*Đáp án:* **Không**. Có thể khiến mảng bit bão hòa nhanh và tốn nhiều CPU.

**Bài 22 — Kỳ vọng FPR.** Một khóa lạ hỏi lặp 1000 lần với filter không đổi. Có thể coi đó là 1000 phép thử độc lập với p=1% không?

*Đáp án:* **Không**. Cùng khóa/bit/hash cố định thường cho cùng kết quả.

**Bài 23 — Xác suất có điều kiện.** Có 5% khóa thật có, 95% thật không, FPR=1%. Khoảng bao nhiêu phần trăm câu trả lời True là FP?

*Đáp án:* \(0,01\cdot0,95/(0,05+0,01\cdot0,95)\approx15,97\%\).

**Bài 24 — Tổng bit khi bão hòa.** Nếu Bloom gần toàn bit 1, câu trả lời False có ít hay nhiều hơn?

*Đáp án:* **Ít hơn**; FPR tăng, dù no-FN vẫn giữ nếu không tắt bit.

### Nhóm D — Điều kiện không FN và phản ví dụ hệ thống

**Bài 25 — Đổi hash.** Add X bằng seed S1, query bằng seed S2. Nếu query False, có vi phạm định lý no FN trên cùng cấu hình không?

*Đáp án:* **Không** — hệ thống đã phá tiền điều kiện dùng **cùng seed/hash**. Cần giữ metadata hoặc tái xây.

**Bài 26 — Xóa bit.** Vì sao tắt bit của A có thể làm B thành FN?

*Đáp án:* A và B có thể dùng chung bit; tắt bit ấy làm B thiếu một vị trí 1.

**Bài 27 — Counting Bloom.** Counting Bloom trả True cho C, nhưng C thực ra chưa add. Có được gọi delete(C) không?

*Đáp án:* **Không**. Dương tính giả có thể khiến giảm các counter của khóa khác, dẫn đến FN.

**Bài 28 — Ghi đồng thời.** Hai luồng cập nhật hai bit trên cùng một byte bằng read-modify-write không nguyên tử có rủi ro gì?

*Đáp án:* **Mất một cập nhật**, làm một khóa đã add thiếu bit; cần atomic OR hoặc đồng bộ.

**Bài 29 — Add đang dở.** Add(X) mới bật 2/3 bit; query(X) trả False. Có trái với cam kết “không FN với add đã hoàn tất” không?

*Đáp án:* **Không** nếu add chưa hoàn tất/công bố. Hợp đồng consistency phải xác định lúc nào một add có hiệu lực.

**Bài 30 — Snapshot cũ.** DB đã nhận X nhưng filter còn ở snapshot trước X. Bloom False có chứng minh DB mới không chứa X không?

*Đáp án:* **Không**. Bộ lọc chưa bao phủ dữ liệu mới; cần delta hoặc tra DB.

**Bài 31 — Khi cần xác minh.** Bloom True cho X, ứng dụng cần kết luận membership chính xác. Làm gì?

*Đáp án:* **Tra nguồn chính xác**, bởi True có thể FP.

**Bài 32 — Cấp quyền.** Có được cấp quyền chỉ vì Bloom trả True không?

*Đáp án:* **Không**. FP có thể cấp quyền sai, không thỏa hợp đồng xác thực/ủy quyền.

### Nhóm E — Thiết kế, kiểm thử và lựa chọn cấu trúc

**Bài 33 — Khả năng xóa.** Nếu cần xóa tùy ý và liệt kê khóa chính xác, Bloom bit chuẩn có phù hợp làm cấu trúc duy nhất không?

*Đáp án:* **Không**. Cần set/DB hoặc cấu trúc có hợp đồng xóa/lưu khóa thích hợp.

**Bài 34 — Tăng m.** Có thể chỉ tăng m từ 1000 lên 2000 mà giữ nguyên bit cũ không?

*Đáp án:* **Không**. Các vị trí hash modulo m thay đổi, cần tái xây hoặc thiết kế nhiều lớp.

**Bài 35 — OR.** Điều kiện để OR hai Bloom mà vẫn có ngữ nghĩa đúng là gì?

*Đáp án:* **Cùng m, h, hash/seed/version, encoding và quy tắc chuẩn hóa khóa**.

**Bài 36 — FPR hai lớp.** Hai lớp đều FPR 1%, query True nếu bất kỳ lớp nào True. Tổng FPR chắc chắn vẫn 1% không?

*Đáp án:* **Không**. Union bound cho cận **≤2%**; nếu độc lập thì khoảng **1,99%**.

**Bài 37 — Kiểm thử FP.** Muốn đo FPR, tập kiểm thử phải chứa khóa thuộc nhóm nào?

*Đáp án:* Những khóa **chắc chắn chưa add**, có nhãn sự thật và phân bố phù hợp với workload.

**Bài 38 — Kiểm thử FN.** Với tập khóa đã add thành công, điều kiện cần có là gì?

*Đáp án:* **Tất cả query đều True**. Một False là dấu hiệu vi phạm hợp đồng cần điều tra.

**Bài 39 — Bộ nhớ byte.** Nếu m=1001 bit, bytearray cần bao nhiêu byte lưu bit?

*Đáp án:* **ceil(1001/8)=126 byte**, chưa kể metadata.

**Bài 40 — Lợi ích thực.** Nếu phần lớn truy vấn hỏi khóa có thật và DB lookup rất rẻ, thêm Bloom có chắc tăng tốc không?

*Đáp án:* **Không**. Phải đo chi phí hash, cache, FPR, tỷ lệ âm tính và số lượt tra cứu nguồn tránh được.

## 19. Tổng kết và ghi nhớ

Bloom filter là một **bộ lọc membership xác suất**: m bit bắt đầu bằng 0; mỗi khóa add bật h vị trí băm; query chỉ trả True khi **mọi vị trí băm đều đang bằng 1**.

**Dương tính giả** xảy ra khi một khóa chưa add lại có toàn bộ vị trí đã được các khóa khác bật. Đó là sai số được phép, được mô tả bằng FPR dưới giả định hash/phân bố truy vấn. Một bộ lọc đầy bit có thể có FPR rất cao nhưng vẫn không tạo FN.

**Không có âm tính giả** là kết quả của bất biến **bit chỉ được bật, không bị tắt**: một khóa đã add thành công có mọi bit bằng 1 và luôn được query nhận ra, **miễn add/query sử dụng cùng cấu hình và trạng thái được lưu đúng**.

Bảo đảm ấy chỉ áp dụng cho **tập khóa thật sự được filter biểu diễn**, không tự động áp dụng cho **database mới hơn, thao tác add đang dở, một filter bị khôi phục cũ, phiên bản hash khác hoặc cập nhật đồng thời bị mất bit**.

Công thức tham khảo:

\[
p_{\rm FP}\approx(1-e^{-hn/m})^h,\quad
h_{\rm opt}\approx (m/n)\ln2,\quad
m\approx-\frac{n\ln p}{(\ln2)^2}.
\]

Bộ lọc có **Θ(m) bit** dữ liệu, và add/query tốn **O(h)** vị trí băm/bit theo mô hình hash hằng số. Các ứng dụng quan trọng thường dùng Bloom như **prefilter**: False có thể loại nhanh khi đã chứng minh độ bao phủ, còn True phải được xác minh bằng nguồn có thẩm quyền nếu quyết định cuối cùng không được sai.

**Ghi nhớ:** **“Bloom False ⇒ chưa add; Bloom True ⇒ có thể đã add” chỉ đáng tin khi biết rõ tập đã được biểu diễn, cấu hình hash nhất quán, bit không mất/tắt và quy trình cập nhật hoàn tất.** Phân biệt bảo đảm một phía của cấu trúc với tính nhất quán của cả hệ thống là chìa khóa để sử dụng Bloom filter đúng và an toàn.
