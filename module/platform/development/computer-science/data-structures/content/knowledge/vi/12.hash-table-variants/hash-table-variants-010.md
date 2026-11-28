# Phân biệt băm phục vụ tra cứu với băm mật mã

**Hash** (băm) là tên gọi của nhiều kỹ thuật cùng chuyển dữ liệu đầu vào thành một giá trị đại diện, nhưng **mục tiêu thiết kế có thể rất khác nhau**. Một bảng băm (*hash table*) cần biết **nên bắt đầu tìm khóa ở đâu**; một hàm băm mật mã (*cryptographic hash function*) cần tạo ra **bản tóm lược khó bị thao túng có chủ đích** theo những mô hình an toàn xác định. Chọn nhầm công cụ có thể gây chậm chương trình, truy vấn sai hoặc tạo lỗ hổng bảo mật.

Trong chương **Biến thể bảng băm** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài học này tập trung phân biệt mục đích, bất biến, thao tác, độ phức tạp thời gian–bộ nhớ và trường hợp sử dụng để lựa chọn đúng cơ chế băm cho các cấu trúc dữ liệu như tập hợp, từ điển và chỉ mục. Các ví dụ cũng làm rõ khi nào cần **SHA-256**, **HMAC**, băm có khóa chống tấn công va chạm bảng, và cơ chế lưu mật khẩu chuyên dụng.

## 1. Hai câu hỏi khác nhau phía sau từ “hash”

Trong cấu trúc dữ liệu, ta thường hỏi:

> Với khóa \(k\) và bảng gồm \(m\) ô hoặc bucket, **khóa này được tìm ở vị trí nào**?

Một cách tổ chức đơn giản là tính giá trị băm tổng quát \(H_{\text{lookup}}(k)\), rồi lấy địa chỉ:

\[
\boxed{\operatorname{index}(k)=H_{\text{lookup}}(k)\bmod m.}
\]

Nếu bảng chứa các cặp khóa–giá trị, chỉ số giúp chọn một **bucket ứng viên**. Bảng vẫn cần xử lý va chạm bằng **separate chaining**, **open addressing** hoặc biến thể khác, và phải so sánh **khóa thật** để kết luận có tìm thấy bản ghi hay không.

Trong mật mã học, ta lại hỏi:

> Có thể tạo một **bản tóm lược có độ dài cố định** của thông điệp sao cho kẻ tấn công rất khó tìm ra một đầu vào khác gây ra kết quả mong muốn hay không?

Ví dụ với SHA-256:

\[
H_{\text{crypto}}:\{0,1\}^{*}\longrightarrow\{0,1\}^{256}.
\]

Đầu vào có thể dài tùy ý trong phạm vi mà thuật toán hỗ trợ; đầu ra là **256 bit**. Bản tóm lược được dùng trong kiểm tra toàn vẹn, chữ ký số, cơ chế xác thực dựa trên khóa bí mật và nhiều giao thức khác.

Hai chức năng có thể dùng chung thao tác “băm” nhưng tối ưu cho **hai tiêu chí thành công**:

| Tiêu chí | Băm phục vụ tra cứu | Băm mật mã |
| --- | --- | --- |
| Câu hỏi chính | Khóa nên nằm trong bucket/ô nào? | Có khó tạo đầu vào gây ra quan hệ băm nguy hiểm không? |
| Kết quả thường dùng | Chỉ số, vị trí thăm dò hoặc giá trị băm để định tuyến | Digest (bản tóm lược) có độ dài bit cố định |
| Ưu tiên | Phân bố tốt, xử lý nhanh, ít va chạm gây hại cho hiệu năng | Chống tìm tiền ảnh, tiền ảnh thứ hai và va chạm theo mô hình bảo mật |
| Khi có va chạm | Bảng phải xử lý đúng và vẫn phân biệt các khóa | Va chạm có chủ đích có thể phá vỡ giả thiết an toàn của ứng dụng |
| Tính bảo mật | Không mặc nhiên có | Có các tính chất bảo mật cụ thể, **không tự có mọi tính chất** |
| Ví dụ | Hash của khóa trong dictionary, bảng băm trong bộ nhớ | SHA-256, SHA-3, BLAKE2 trong các ngữ cảnh phù hợp |

**Không thể kết luận chỉ từ từ “hash” rằng dữ liệu đã được mã hóa, được xác thực hoặc đã được bảo vệ khỏi kẻ tấn công.**

## 2. Va chạm của chỉ số bảng và va chạm của digest

Đây là sự nhầm lẫn quan trọng nhất cần loại bỏ.

### Va chạm tại bucket của bảng băm

Giả sử một bảng có \(m=8\) bucket và dùng hàm minh họa \(H_{\text{lookup}}(k)=k\) cho khóa nguyên không âm. Khi đó:

\[
\operatorname{index}(21)=21\bmod8=5,
\qquad
\operatorname{index}(29)=29\bmod8=5.
\]

Hai khóa **21 và 29 khác nhau**, giá trị băm đầy đủ là 21 và 29 cũng khác nhau, nhưng **chỉ số bucket trùng nhau** do phép chia dư.

~~~text
                   H_lookup(k)      modulo 8
Khóa 21  -------->      21  ------------> bucket 5
                                               |
                                               v
                                        [(21, "A"), (29, "B")]
                                               ^
                                               |
Khóa 29  -------->      29  ------------> bucket 5
~~~

Nếu bảng dùng chaining, cả hai bản ghi có thể nằm trong cùng một bucket. Khi tìm **29**, chương trình quét bucket và so sánh khóa với **29**, không được trả luôn giá trị của 21 chỉ vì gặp bucket 5.

**Bất biến của bảng băm** là: mọi khóa lưu đúng chỗ theo hàm băm/cách thăm dò hiện tại, và phép tìm kiếm có khả năng phân biệt khóa không bằng nhau. Va chạm không làm hỏng bảng nếu **cơ chế xử lý va chạm được viết đúng**.

### Va chạm của giá trị băm mật mã

Với hàm băm mật mã \(H\), một **va chạm đầy đủ** là cặp thông điệp khác nhau:

\[
\boxed{x\neq y\quad\text{nhưng}\quad H(x)=H(y).}
\]

Do số thông điệp khả dĩ lớn hơn số digest hữu hạn, va chạm **chắc chắn tồn tại về mặt toán học**. Điều mật mã yêu cầu là **khó tìm ra một va chạm** trong nguồn lực tính toán thực tế, chứ không phải “không bao giờ có”.

Hai loại va chạm trên có thể khác nhau hoàn toàn:

| Tình huống | Ý nghĩa |
| --- | --- |
| \(H(x)\neq H(y)\) nhưng \(H(x)\bmod m=H(y)\bmod m\) | Va chạm **chỉ số bảng**; thường xảy ra ngay cả khi dùng SHA-256 làm hàm băm nguồn |
| \(H(x)=H(y)\) với \(x\neq y\) | Va chạm **giá trị băm đầy đủ**; liên quan trực tiếp tới tính chống va chạm của hàm |
| Hai chuỗi khác nhau sau khi chuẩn hóa lại thành cùng một khóa logic | Có thể là **cùng khóa theo quy tắc ứng dụng**, không nhất thiết là va chạm |

Ngay cả khi dùng SHA-256 để chọn bucket, một bảng chỉ có 8 bucket vẫn không tránh được va chạm chỉ số. **Hàm băm mật mã mạnh không biến một bảng có ít bucket thành bảng không va chạm.**

## 3. Điều gì làm nên một hàm băm phục vụ tra cứu tốt?

Một hàm băm cho bảng tra cứu được đánh giá theo **workload** và cách tổ chức bảng:

1. **Tính xác định trong vòng đời bảng:** cùng khóa, cùng cách mã hóa, cùng tham số và cùng kích thước bảng phải được định tuyến đến đúng vị trí. Nếu đổi seed hoặc thay kích thước bảng, cần **tái băm/phân phối lại** các khóa phù hợp.
2. **Tương thích với quan hệ bằng nhau:** nếu hai đối tượng được coi là khóa bằng nhau, chúng phải có giá trị băm bằng nhau theo hợp đồng của bảng.
3. **Phân bố đủ đều trên tập khóa thực tế:** tránh để phần lớn khóa tập trung trong vài bucket, gây chuỗi dài hoặc thăm dò dài.
4. **Chi phí tính toán nhỏ:** tính hash được gọi thường xuyên khi tìm, chèn và xóa.
5. **Phù hợp với cơ chế xử lý va chạm:** linear probing, Robin Hood, cuckoo và chaining có các đặc tính hiệu năng khác nhau.
6. **Chống đầu vào đối kháng nếu cần:** khi người dùng bên ngoài có thể gửi khóa tùy ý, cần xem xét khả năng cố tình tạo nhiều khóa cùng bucket.

Với bảng băm có \(n\) phần tử và \(m\) bucket, **hệ số tải** là:

\[
\alpha=\frac{n}{m}.
\]

Trong chaining, một phân tích đơn giản với phân bố băm đều cho độ dài chuỗi kỳ vọng khoảng \(\alpha\). Khi \(\alpha\) được khống chế và hàm băm phù hợp, phép tra cứu thường có **\(O(1)\) theo kỳ vọng** xét theo số phần tử. Nhưng nếu tất cả khóa cùng rơi vào một bucket thì tìm kiếm tuyến tính trong bucket có thể tốn **\(O(n)\)**.

Tương tự, trong open addressing, hệ số tải tăng làm tăng xác suất phải thử nhiều ô. Dùng một hàm mật mã mạnh **không thay thế được** việc kiểm soát tải, resize và tổ chức bảng.

### Quan hệ hash và phép so sánh bằng nhau

Một bảng ánh xạ cần duy trì quy tắc:

\[
k_1=k_2\ \Longrightarrow\ H_{\text{lookup}}(k_1)=H_{\text{lookup}}(k_2).
\]

Chiều ngược lại **không đúng**: hai khóa có cùng giá trị băm có thể vẫn khác nhau. Nếu khóa là đối tượng có các trường có thể thay đổi, không nên thay đổi những trường tham gia tính hash và so sánh bằng nhau khi đối tượng đang là khóa trong bảng, nếu không phép tìm có thể đi đến vị trí khác.

Ví dụ, hai chuỗi Unicode nhìn giống nhau nhưng có cách biểu diễn byte khác nhau có thể băm ra các kết quả khác nhau. Nếu ứng dụng quy định các chuỗi đó là cùng một khóa, cần thống nhất **quy tắc chuẩn hóa trước khi băm**.

## 4. Ba yêu cầu an toàn mật mã cần phân biệt

Đối với hàm băm mật mã \(H\), các tính chất được mô tả bằng mức độ khó của **bài toán tấn công**.

### 4.1. Chống tìm tiền ảnh (*preimage resistance*)

Cho sẵn một digest \(y\), kẻ tấn công khó tìm một thông điệp \(x\) sao cho:

\[
H(x)=y.
\]

Với một hàm băm lý tưởng có \(b\) bit đầu ra, công sức thử vét cạn mục tiêu cụ thể thường ở mức **\(2^b\)** phép thử, trong mô hình đầu vào và mục tiêu thích hợp.

Đây **không** có nghĩa ai đó không thể đoán đầu vào có ít khả năng, ví dụ chuỗi mật khẩu phổ biến. Nếu người dùng chọn mật khẩu từ một tập nhỏ, kẻ tấn công có thể thử từng mật khẩu trong tập đó, không cần vét cạn \(2^{256}\) giá trị digest.

### 4.2. Chống tìm tiền ảnh thứ hai (*second-preimage resistance*)

Cho sẵn thông điệp \(x\) cụ thể, kẻ tấn công khó tìm thông điệp khác \(x'\neq x\) sao cho:

\[
H(x')=H(x).
\]

Trong mô hình hash lý tưởng với thông điệp có độ dài thông thường và đủ entropy, công sức kỳ vọng tìm tiền ảnh thứ hai có thể gần **\(2^b\)**. Một số cấu trúc hash và thông điệp rất dài có những kết quả chuyên biệt, nên không nên coi con số này là định lý đúng cho mọi thuật toán, mọi độ dài.

### 4.3. Chống va chạm (*collision resistance*)

Kẻ tấn công được **tự chọn cả hai thông điệp** và phải tìm:

\[
x\neq x',\qquad H(x)=H(x').
\]

Đối với hàm băm lý tưởng \(b\) bit, **hiệu ứng ngày sinh** (*birthday bound*) cho công sức tìm va chạm ở mức khoảng **\(2^{b/2}\)** phép thử, nhỏ hơn đáng kể mức tìm tiền ảnh của một digest cụ thể.

Ví dụ về quy mô lý tưởng:

| Độ dài digest \(b\) | Tìm va chạm kiểu ngày sinh | Tìm tiền ảnh mục tiêu cụ thể |
| ---: | --- | --- |
| 32 bit | Cỡ \(2^{16}\) thử | Cỡ \(2^{32}\) thử |
| 64 bit | Cỡ \(2^{32}\) thử | Cỡ \(2^{64}\) thử |
| 128 bit | Cỡ \(2^{64}\) thử | Cỡ \(2^{128}\) thử |
| 256 bit | Cỡ \(2^{128}\) thử | Cỡ \(2^{256}\) thử |

Các con số là **ước lượng của mô hình lý tưởng**, không phải tuyên bố rằng mọi hàm có cùng số bit đều bảo mật như nhau. Các thuật toán cũ như **MD5** và **SHA-1** có điểm yếu va chạm đã biết, nên không được chọn để bảo vệ các ứng dụng cần chống va chạm hiện đại.

### Phân biệt ba bài toán bằng một bảng

| Bài toán | Đầu vào kẻ tấn công được biết/chọn | Mục tiêu |
| --- | --- | --- |
| Preimage | Digest đích \(y\) | Tìm \(x\) để \(H(x)=y\) |
| Second preimage | Một thông điệp \(x\) cho trước | Tìm \(x'\neq x\) cùng digest |
| Collision | Tự chọn cả \(x,x'\) | Tìm hai thông điệp khác nhau cùng digest |

**Tính khuếch tán mạnh** (*avalanche effect*: đổi một bit đầu vào thường làm thay đổi nhiều bit đầu ra) là đặc điểm mong muốn, nhưng **không đủ để chứng minh tính an toàn mật mã**. Một hàm băm không mật mã vẫn có thể có avalanche rất tốt.

## 5. SHA-256, HMAC và hàm băm mật khẩu không cùng vai trò

Nói “dùng hash để bảo mật” là chưa xác định đủ yêu cầu. Cần hỏi hệ thống muốn **kiểm tra toàn vẹn, xác thực nguồn gửi hay lưu mật khẩu**.

### 5.1. Digest không khóa để kiểm tra toàn vẹn

**SHA-256** tạo bản tóm lược 256 bit:

\[
d=\operatorname{SHA256}(\text{message}).
\]

Nếu có một digest kỳ vọng **nhận từ nguồn đáng tin cậy**, chương trình có thể tính lại SHA-256 của tệp nhận được và so sánh để phát hiện tệp bị thay đổi. Phép so sánh này **không tự xác thực người gửi**: nếu kẻ tấn công được phép sửa cả tệp lẫn chuỗi digest công bố kèm, họ chỉ cần tính digest mới.

SHA-256 cũng không phải **mã hóa**. Nó không tạo ra bản mã có thể giải mã bằng khóa; đầu vào bí mật có tập khả năng nhỏ vẫn có thể bị đoán bằng cách băm từng ứng viên.

### 5.2. HMAC để xác thực bằng khóa bí mật chung

**HMAC** là cơ chế tạo **mã xác thực thông điệp** (*message authentication code*, MAC) dựa trên một hàm băm và **khóa bí mật**. Với HMAC-SHA-256:

\[
\operatorname{tag}=\operatorname{HMAC}_{K}(\text{message}).
\]

Người nhận có khóa \(K\) có thể tính lại tag và kiểm tra thông điệp chưa bị sửa bởi người không biết khóa. **HMAC khác với việc chỉ viết \(\operatorname{SHA256}(K\parallel\text{message})\)**: các cách ghép trực tiếp như vậy có thể mắc lỗi thiết kế, trong đó có vấn đề *length extension* đối với một số hàm hash kiểu Merkle–Damgård khi dùng làm MAC không đúng cách.

HMAC phù hợp khi hai bên chia sẻ bí mật. Nó **không cung cấp chữ ký số công khai** hoặc khả năng chống chối bỏ của chữ ký bất đối xứng.

### 5.3. Mật khẩu phải dùng cơ chế băm chuyên dụng

Lưu đơn thuần **SHA-256(mật khẩu)** thường **không phù hợp** để bảo vệ cơ sở dữ liệu mật khẩu, vì hàm quá nhanh và giúp kẻ tấn công thử nhiều mật khẩu trong một giây nếu cơ sở dữ liệu bị lộ.

Với mật khẩu, nên dùng **hàm dẫn xuất khóa dành cho mật khẩu** (*password hashing/KDF*) như **Argon2id**, **scrypt** hoặc **PBKDF2** khi bối cảnh triển khai yêu cầu. Các cơ chế này sử dụng **salt riêng ngẫu nhiên** cho từng mật khẩu và tham số chi phí tính toán; Argon2id/scrypt còn chú trọng chi phí bộ nhớ.

**Salt không phải khóa bí mật**: salt giúp các mật khẩu giống nhau không nhất thiết tạo cùng kết quả và hạn chế khả năng tái sử dụng bảng tính trước, nhưng không thay thế độ mạnh mật khẩu và chính sách chống đoán mật khẩu.

| Nhiệm vụ | Công cụ phù hợp | Không nên dùng thay thế |
| --- | --- | --- |
| Chọn bucket cho khóa trong hash table | Hàm băm tra cứu và cơ chế xử lý va chạm | Dùng SHA-256 với kỳ vọng hết va chạm bucket |
| Kiểm tra tệp có trùng digest đáng tin cậy | SHA-256 hoặc digest mật mã mạnh phù hợp | CRC32 nếu cần chống chỉnh sửa có chủ đích |
| Xác thực thông điệp khi hai bên có khóa bí mật | HMAC-SHA-256 hoặc MAC được thiết kế cho mục đích đó | SHA-256 thuần không khóa |
| Lưu/xác minh mật khẩu | Argon2id, scrypt, PBKDF2 cấu hình phù hợp | SHA-256(mật khẩu) không salt hoặc một lần băm quá nhanh |
| Chữ ký số có thể xác minh bằng khóa công khai | Lược đồ chữ ký số chuẩn sử dụng digest thích hợp | HMAC khi người xác minh không được biết khóa bí mật |

## 6. Vì sao “hàm băm nhanh” không luôn là một lời khen?

Trong **tra cứu**, tốc độ thường là ưu điểm: mỗi phép tìm/chèn/xóa có thể cần tính hash của khóa, nên hàm băm hiệu quả giảm CPU và độ trễ.

Trong **kiểm tra toàn vẹn tệp**, tốc độ cũng hữu ích: một hàm như SHA-256 có thể băm lượng dữ liệu lớn với chi phí chấp nhận được trên nhiều phần cứng.

Nhưng trong **lưu mật khẩu**, băm quá nhanh có thể giúp kẻ tấn công thử mật khẩu hàng loạt. Vì thế, hàm băm mật khẩu được cố ý thiết kế để **tốn thời gian hoặc bộ nhớ có thể điều chỉnh**, khiến thử đoán mật khẩu trở nên đắt hơn.

Không có mâu thuẫn: **tiêu chí tốc độ phụ thuộc vào mô hình đe dọa và mục đích sử dụng**. Một cơ chế tốt cho bảng băm không nhất thiết tốt cho lưu mật khẩu, và ngược lại.

## 7. Tấn công hash flooding: khi băm tra cứu trở thành vấn đề bảo mật

Bảng băm chaining với \(n\) phần tử được phân bố đều có thể tra cứu **\(O(1)\) theo kỳ vọng**, nhưng nếu kẻ tấn công tạo nhiều khóa cùng một bucket, việc tìm/chèn có thể giảm xuống **\(O(n)\)** cho mỗi thao tác trong cài đặt duyệt chuỗi. Gửi nhiều khóa như vậy có thể làm dịch vụ tốn quá nhiều CPU (*algorithmic complexity denial of service*, thường được gọi là **hash-flooding attack**).

~~~text
Phân bố bình thường:       Phân bố bị tấn công:

bucket 0: [a]              bucket 0: []
bucket 1: [b, c]           bucket 1: []
bucket 2: [d]              bucket 2: [x1, x2, x3, ..., xN]
bucket 3: [e]              bucket 3: []

Tra cứu trung bình ngắn.   Chuỗi dài khiến tra cứu/chèn tốn CPU.
~~~

Một biện pháp quan trọng là **hàm băm tra cứu có khóa bí mật** (*keyed hash*) với seed/khóa không lộ cho bên gửi dữ liệu. Ví dụ, **SipHash** được thiết kế để dùng trong các tình huống cần hàm băm ngắn, có khóa, tốc độ phù hợp và chống việc kẻ tấn công dễ tiên đoán các giá trị băm phục vụ bảng.

**Cần phân biệt ba khái niệm:**

- **Băm không mật mã nhanh** như một số họ hash dữ liệu có thể phân bố tốt cho workload thông thường, nhưng không nên mặc định có khả năng chống đầu vào đối kháng.
- **Băm có khóa để chống hash flooding** giấu ánh xạ băm khỏi kẻ tấn công khi khóa thực sự bí mật và cơ chế sử dụng đúng; nó không khiến va chạm **chỉ số bucket** biến mất.
- **Hàm băm mật mã cho digest** như SHA-256 có các mục tiêu chống tiền ảnh/va chạm ở **đầu ra đầy đủ**; dùng SHA-256 rồi lấy vài bit hoặc modulo cho địa chỉ bảng vẫn cho phép rất nhiều khóa chung bucket.

Chỉ **thay một hàm băm yếu bằng SHA-256 không khóa** cũng chưa giải quyết mọi nguy cơ hash flooding nếu kẻ tấn công biết thuật toán, kích thước bảng, cách lấy chỉ số và có đủ nguồn lực để tìm khóa trùng bucket. Khác biệt then chốt trong mô hình bảo vệ này thường là **hàm băm có khóa không thể đoán**, bên cạnh giới hạn yêu cầu, resize và cấu trúc xử lý va chạm phù hợp.

Ở một số môi trường, thuật toán băm của **chuỗi** được ngẫu nhiên hóa theo tiến trình để giảm khả năng tấn công. Tuy nhiên, chi tiết băm phụ thuộc ngôn ngữ và phiên bản runtime; không thể mặc định mọi kiểu khóa trong mọi bảng đều được bảo vệ giống nhau.

## 8. Python: cùng một dữ liệu, ba cách dùng băm

Các ví dụ dưới đây đặt cạnh nhau để thấy **chỉ số bucket**, **digest SHA-256** và **HMAC** là ba kết quả phục vụ ba yêu cầu khác nhau. Chúng dùng thư viện chuẩn Python; mã chỉ minh họa nguyên lý, không phải một thư viện bảng băm hoặc giao thức xác thực hoàn chỉnh.

### 8.1. Băm để chọn bucket và tìm đúng khóa

~~~python
BUCKET_COUNT = 8
buckets = [[] for _ in range(BUCKET_COUNT)]


def bucket_index(key):
    if type(key) is not int or key < 0:
        raise ValueError("Ví dụ yêu cầu khóa nguyên không âm")
    return key % BUCKET_COUNT


def put(key, value):
    bucket = buckets[bucket_index(key)]
    for i, (existing_key, _) in enumerate(bucket):
        if existing_key == key:
            bucket[i] = (key, value)
            return
    bucket.append((key, value))


def get(key, default=None):
    bucket = buckets[bucket_index(key)]
    for existing_key, value in bucket:
        if existing_key == key:
            return value
    return default


put(21, "Alice")
put(29, "Bob")

print(bucket_index(21))  # 5
print(bucket_index(29))  # 5: va chạm chỉ số
print(buckets[5])        # [(21, 'Alice'), (29, 'Bob')]
print(get(21))           # Alice
print(get(29))           # Bob
print(get(37))           # None: cùng bucket nhưng không có khóa này
~~~

**Bài học:** Điều kiện đúng của chương trình là **tra cứu trả chính xác giá trị gắn với khóa**, kể cả khi nhiều khóa cùng bucket. Không có bất kỳ yêu cầu tiền ảnh hay chống va chạm mật mã nào trong ví dụ này.

Nếu dùng Python **dict** thực tế, nên sử dụng API có sẵn thay vì viết lại một bảng băm chaining như trên. Việc gọi **hash(obj)** trong Python gắn với hợp đồng của kiểu đối tượng và môi trường thực thi; giá trị của hash với một số kiểu như chuỗi **không nên dùng làm mã định danh bền vững lưu trên đĩa hay trao đổi qua mạng**.

### 8.2. SHA-256 để tạo digest ổn định của thông điệp

~~~python
import hashlib

message = b"abc"
digest_bytes = hashlib.sha256(message).digest()
digest_hex = hashlib.sha256(message).hexdigest()

print(len(digest_bytes))  # 32 byte = 256 bit
print(digest_hex)
# ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad

assert digest_hex == (
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
)

changed = b"abd"
print(hashlib.sha256(changed).hexdigest() == digest_hex)  # False
~~~

SHA-256 xử lý **chuỗi byte**: hai hệ thống muốn có cùng digest phải thống nhất **cách mã hóa**, **chuẩn hóa**, thứ tự trường và mọi dấu phân tách trước khi băm. Digest có thể so sánh qua nhiều lần chạy, miễn dữ liệu byte và thuật toán giống nhau.

Không được suy ra rằng cứ thấy digest khác nhau thì dữ liệu có ý nghĩa khác nhau theo nghiệp vụ: chẳng hạn hai cách biểu diễn Unicode có thể mang cùng ý nghĩa nhưng là hai chuỗi byte khác nhau. Ngược lại, digest trùng nhau không chứng minh tính bằng nhau **tuyệt đối về mặt toán học**; tính an toàn dựa trên việc tạo va chạm có chủ đích là cực khó với thuật toán phù hợp.

### 8.3. HMAC-SHA-256 để xác thực thông điệp

~~~python
import hashlib
import hmac
import secrets

# Ví dụ: hai phía phải có cùng secret qua kênh quản lý khóa an toàn.
# Tạo khóa ngẫu nhiên chỉ để minh họa trong một phiên làm việc.
secret = secrets.token_bytes(32)
message = b"user=42&role=member"

tag = hmac.new(secret, message, hashlib.sha256).digest()


def verify(received_message, received_tag):
    expected = hmac.new(secret, received_message, hashlib.sha256).digest()
    return hmac.compare_digest(expected, received_tag)


print(verify(message, tag))                        # True
print(verify(b"user=42&role=admin", tag))           # False
~~~

**Đọc đúng ví dụ:** Người gửi và người kiểm tra phải **giữ bí mật** khóa HMAC. Nếu người khác biết khóa, họ cũng tạo được tag. HMAC không mã hóa nội dung và không tự chống gửi lại thông điệp cũ (*replay attack*); muốn chống replay cần thêm timestamp, nonce hoặc số thứ tự có kiểm tra.

Hàm **hmac.compare_digest** được thiết kế nhằm tránh việc so sánh dừng ở ký tự đầu tiên khác nhau, qua đó hạn chế rò rỉ thời gian trong phép đối chiếu tag. Nó không khắc phục lỗi thiết kế giao thức hoặc cách lưu trữ khóa.

## 9. Chi phí thời gian: không chỉ có một chữ \(O(1)\)

Cho \(L\) là độ dài khóa/thông điệp tính theo byte, \(n\) là số bản ghi của bảng và \(m\) là số bucket.

| Thao tác | Chi phí khái quát | Cần hiểu thêm |
| --- | --- | --- |
| Tính hàm băm trên toàn bộ khóa dài \(L\) | Thường \(O(L)\) | Muốn đọc hết đầu vào phải xử lý số byte tương ứng; một số runtime có thể cache hash khóa bất biến |
| Tính chỉ số sau khi đã có hash | Thường \(O(1)\) | Ví dụ phép modulo hoặc lấy bit |
| Tìm trong hash table chaining phân bố tốt | \(O(1)\) kỳ vọng theo \(n\) với tải được khống chế | Chưa tính chi phí băm/so sánh khóa dài; phụ thuộc giả thiết phân bố |
| Tìm trong chaining khi mọi khóa cùng bucket | \(O(n)\) lần so sánh khóa | Nếu mỗi phép so sánh tốn \(O(L)\), chi phí có thể lớn hơn |
| Tính digest SHA-256 của thông điệp \(L\) byte | \(O(L)\) theo độ dài đầu vào | Hằng số phụ thuộc triển khai/phần cứng; đầu ra cố định 32 byte |
| Tính HMAC-SHA-256 của thông điệp \(L\) byte | \(O(L)\) đối với đầu vào dài, cộng xử lý khóa | Dùng một MAC được thiết kế chuẩn, không tự ghép chuỗi |
| Xác minh mật khẩu bằng Argon2id/scrypt/PBKDF2 | Chi phí cố ý cao theo tham số cấu hình | Không thể mô tả đầy đủ chỉ bằng \(O(L)\); thời gian/bộ nhớ chủ động điều chỉnh |

**Giải thích \(O(1)\) cho bảng băm:** Khi giáo trình ghi “tìm kiếm trong bảng băm trung bình \(O(1)\)”, thường đang xem thao tác băm và so sánh khóa là **đơn vị chi phí hằng số**. Với khóa là chuỗi rất dài, phần tính hash hoặc so sánh khóa vẫn có thể phải đọc nhiều byte.

**Dùng digest mật mã để làm chỉ số bảng có hợp lệ không?** Về mặt chức năng, có: tính digest rồi chuyển thành số nguyên và lấy modulo \(m\). Nhưng thường **không cần thiết** nếu chỉ quan tâm hiệu năng tra cứu và các khóa không thuộc mô hình tấn công đối kháng. Hơn nữa, phương pháp này vẫn cần xử lý va chạm như mọi bảng khác. Ngược lại, trong ứng dụng an toàn cần chống đầu vào có chủ đích, hãy lựa chọn **hàm băm có khóa được thiết kế phù hợp**, không suy đoán chỉ từ tên SHA-256.

## 10. Xác suất va chạm: cùng công thức, ý nghĩa khác

Giả sử \(n\) khóa phân biệt được phân bố độc lập và đều trên \(m\) bucket. Với một cặp khóa bất kỳ, xác suất chúng rơi vào cùng bucket là \(1/m\). Số cặp khóa có thể tạo là \(\binom{n}{2}\), nên **số cặp va chạm bucket kỳ vọng**:

\[
\boxed{\mathbb{E}[\text{số cặp trùng bucket}]
=\binom{n}{2}\frac1m
=\frac{n(n-1)}{2m}.}
\]

Ví dụ với \(n=1000\) khóa và \(m=1000\) bucket:

\[
\mathbb{E}[\text{số cặp trùng bucket}]
=\frac{1000\cdot999}{2\cdot1000}=499{,}5.
\]

Số cặp trùng bucket có thể **rất nhiều** dù bảng băm vẫn hoạt động đúng và tra cứu trung bình nhanh nhờ mỗi bucket chỉ có ít khóa. Con số **499,5** là **kỳ vọng số cặp**, không phải số bucket bị va chạm hay số khóa phải di chuyển.

Với digest băm mật mã lý tưởng \(b\) bit và \(q\) thông điệp ngẫu nhiên độc lập, xác suất có **ít nhất một cặp digest trùng nhau** xấp xỉ:

\[
\boxed{P(\text{có va chạm})\approx
1-\exp\left(-\frac{q(q-1)}{2\cdot2^b}\right).}
\]

Vì \(2^b\) cực lớn khi \(b=256\), xác suất va chạm digest đầy đủ với số lượng thông điệp vừa phải rất nhỏ theo mô hình lý tưởng. Nhưng nếu chỉ lấy digest SHA-256 modulo \(1000\) để chọn bucket, ta lại quay về một **không gian chỉ số chỉ có 1000 giá trị**, nên va chạm bucket là điều bình thường.

**Kết luận:** Đừng nhầm **độ dài digest \(b\) bit** với **số bucket \(m\)**. Tính chống va chạm mật mã không đảm bảo không có va chạm tại chỉ số đã bị rút gọn của bảng.

## 11. Một luồng dữ liệu có thể cần nhiều loại băm

Giả sử dịch vụ lưu tài liệu có:

- **Khóa tra cứu** là định danh tài liệu.
- **Tệp dữ liệu** là nội dung do người dùng tải lên.
- **API** tiếp nhận yêu cầu từ máy khách.

Một thiết kế có thể dùng ba cơ chế khác nhau mà không mâu thuẫn:

~~~mermaid
flowchart TD
    A["Yêu cầu lưu tài liệu"] --> B["Định danh tài liệu"]
    B --> C["Hàm băm tra cứu"]
    C --> D["Chọn bucket trong từ điển chỉ mục"]
    A --> E["Nội dung tệp"]
    E --> F["SHA-256 của nội dung"]
    F --> G["Đối chiếu digest hoặc định danh nội dung"]
    A --> H["Thông điệp API + khóa bí mật"]
    H --> I["HMAC-SHA-256"]
    I --> J["Xác thực thông điệp"]
~~~

Đối với **chỉ mục từ điển**, kết quả băm giúp **định tuyến** và tra cứu; vẫn phải so sánh khóa để xác nhận đúng tài liệu.

Đối với **nội dung tệp**, digest mật mã giúp kiểm tra toàn vẹn so với digest đáng tin cậy hoặc làm **định danh dựa trên nội dung** (*content-addressed identifier*) với chính sách xử lý va chạm phù hợp. Tính chống va chạm mạnh khiến việc tìm hai nội dung khác nhau cùng digest trở nên rất khó, nhưng không cho phép bỏ qua hoàn toàn kiểm tra tính xác thực của nguồn và quy tắc xử lý sai lệch dữ liệu.

Đối với **API có khóa bí mật chung**, HMAC giúp kiểm tra thông điệp được tạo bởi bên có khóa hợp lệ. Quyền truy cập tài liệu và xác thực người dùng vẫn là các vấn đề thiết kế riêng.

### Khi muốn khử trùng lặp nội dung

Hệ thống có thể lưu **digest của tệp** để nhanh chóng phát hiện **ứng viên trùng nội dung**. Nếu yêu cầu chính xác tuyệt đối, cần kiểm tra thêm kích thước hoặc so sánh nội dung trong những tình huống cần thiết, vì không có hàm từ tập chuỗi byte vô hạn sang digest hữu hạn nào loại bỏ va chạm hoàn toàn.

Một bảng băm dùng cho tra cứu digest đó vẫn có thể xảy ra **va chạm bucket** giữa các digest khác nhau. Phải xử lý va chạm ở cả hai tầng theo chính sách dữ liệu của ứng dụng.

## 12. Hướng dẫn lựa chọn theo yêu cầu

Trước khi chọn thuật toán, hãy xác định **tài sản cần bảo vệ hoặc thao tác cần tối ưu**:

| Yêu cầu thực tế | Giải pháp thường phù hợp | Điều phải kiểm tra thêm |
| --- | --- | --- |
| Tìm nhanh giá trị theo khóa nội bộ | Bảng băm với hàm phân bố tốt; sử dụng collection chuẩn | Hash/equality nhất quán, hệ số tải, resize, va chạm |
| Nhận nhiều khóa từ khách không tin cậy | Bảng băm có bảo vệ hash flooding, chẳng hạn keyed hashing do runtime/thư viện cung cấp | Giữ bí mật seed, giới hạn tài nguyên, worst-case của cấu trúc |
| Lưu kết quả băm ổn định qua lần khởi động hoặc giữa hệ thống | Thuật toán xác định và định dạng dữ liệu được quy định rõ | Không dùng giá trị hash runtime ngẫu nhiên làm định danh bền vững |
| Kiểm tra tệp có bị sửa so với giá trị chuẩn không | SHA-256/digest mật mã mạnh và một digest tham chiếu đáng tin cậy | Xác thực nguồn digest, tránh kẻ tấn công thay cả hai |
| Chứng minh thông điệp được bên có khóa bí mật tạo ra | HMAC hoặc MAC được chuẩn hóa | Quản lý khóa, replay, định dạng thông điệp, so sánh tag |
| Lưu và xác minh mật khẩu | Argon2id/scrypt/PBKDF2 với salt và tham số phù hợp | Chính sách cập nhật chi phí, giới hạn đăng nhập, bảo vệ DB |
| Kiểm tra lỗi truyền dẫn ngẫu nhiên, không cần chống sửa có chủ đích | Checksum/CRC phù hợp | Không nhầm CRC với hash mật mã có tính chống tấn công |
| Phân chia khóa giữa các nút có thể gia nhập/rời cụm | Consistent hashing/rendezvous hashing hoặc cơ chế sharding thích hợp | Phiên bản thành viên, chuyển dữ liệu, replica, hotspot |

Một quyết định đúng đôi khi dùng **nhiều thuật toán băm cho các lớp chức năng khác nhau** thay vì yêu cầu một hàm làm tốt tất cả.

## 13. Những hiểu lầm và lỗi triển khai thường gặp

1. **“Hash giống mã hóa.”** Sai. Digest thông thường không có thao tác giải mã để khôi phục đầu vào; bảo mật nội dung cần mã hóa/giao thức phù hợp.
2. **“Dùng SHA-256 thì bảng băm không bao giờ va chạm.”** Sai. Khi lấy modulo \(m\), nhiều digest khác nhau vẫn vào cùng bucket; bản thân digest hữu hạn cũng có thể va chạm về mặt toán học.
3. **“Hai khóa có cùng hash chắc chắn bằng nhau.”** Sai. Chỉ có chiều **khóa bằng nhau ⇒ hash bằng nhau** là yêu cầu của hợp đồng bảng.
4. **“Một hàm có avalanche mạnh chắc chắn an toàn mật mã.”** Sai. Cần các mục tiêu chống tấn công cụ thể, phân tích mật mã và thuật toán đáng tin cậy.
5. **“SHA-256(mật khẩu) là đủ vì có 256 bit.”** Sai. Mật khẩu có entropy thấp và SHA-256 chạy nhanh; nên dùng password hashing/KDF chuyên dụng với salt.
6. **“SHA-256(message) xác thực người gửi.”** Sai. Người không có khóa bí mật cũng tính được digest; xác thực cần MAC hoặc chữ ký số phù hợp.
7. **“HMAC cũng là chữ ký số công khai.”** Sai. Các bên cùng biết khóa đều có thể tạo tag, nên không có tính chất như chữ ký có khóa công khai.
8. **“Băm tra cứu nhanh luôn an toàn trước người dùng độc hại.”** Sai. Hash flooding có thể làm hiệu năng xấu đi; cân nhắc keyed hashing, giới hạn tài nguyên và xử lý va chạm.
9. **“Giá trị hash() của đối tượng Python luôn giống nhau giữa các lần chạy.”** Sai đối với một số kiểu khóa như chuỗi trong các runtime thường dùng; không sử dụng nó làm định danh bền vững nếu không có hợp đồng bảo đảm.
10. **“Đổi seed của bảng khi đang dùng không ảnh hưởng dữ liệu.”** Sai. Nếu seed thay đổi, vị trí khóa có thể thay đổi và bảng cần được tái phân phối.
11. **“Một hash mật mã mạnh cho phép bỏ so sánh khóa khi tìm trong bảng.”** Sai. Bảng vẫn phải xử lý collision của địa chỉ và tuân thủ hợp đồng về tính chính xác.
12. **“Một checksum như CRC32 là giải pháp chống giả mạo.”** Sai. CRC chủ yếu phát hiện lỗi ngẫu nhiên theo mô hình truyền dẫn; không bảo đảm chống sửa có chủ đích.
13. **“Tốc độ cao luôn tốt cho mọi ứng dụng hash.”** Sai. Với password hashing, chi phí cao có kiểm soát là một phần của cơ chế bảo vệ.
14. **“Tính hash là toàn bộ chi phí thao tác phân tán.”** Sai. Định tuyến, I/O, mạng, sao chép, thành viên cụm và tính nhất quán dữ liệu có chi phí riêng.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Bảng có 8 bucket. Khóa 21 và 29 cùng vào bucket 5. Đây có phải bằng chứng hàm SHA-256 không chống va chạm không?

**Đáp án:** Không. Đó là va chạm **chỉ số bucket** khi dùng phép modulo 8. Hai giá trị băm nguồn có thể khác nhau, và bảng vẫn phải xử lý đúng hai khóa bằng cơ chế collision resolution.

**Câu 2.** Trong bảng chaining, khóa 37 cùng bucket với 21 và 29 nhưng không được lưu. Phép tìm khóa 37 có được trả về giá trị của 21 không?

**Đáp án:** Không. Phải **so sánh khóa thật**, kiểm tra hết ứng viên trong bucket rồi trả về không tìm thấy.

**Câu 3.** Mô tả khác biệt giữa preimage và collision resistance.

**Đáp án:** Preimage cho sẵn digest rồi yêu cầu tìm một đầu vào khớp. Collision cho phép kẻ tấn công tự chọn hai đầu vào khác nhau rồi tìm cặp có cùng digest. Với hash lý tưởng \(b\) bit, công sức tìm collision thường ở mức \(2^{b/2}\), nhỏ hơn công sức tìm preimage của một digest cụ thể, khoảng \(2^b\).

**Câu 4.** Vì sao SHA-256(tệp) và SHA-256(tệp đã sửa) khác nhau chưa đủ để chứng minh tệp nhận được có nguồn gốc đáng tin cậy?

**Đáp án:** SHA-256 không chứa khóa và bất kỳ ai cũng tính được digest của tệp mới. Phải so với **digest tham chiếu được xác thực** hoặc dùng chữ ký số/MAC để ràng buộc thông điệp với bên hợp lệ.

**Câu 5.** Hai hệ thống dùng cùng khóa HMAC nhưng khác cách nối các trường trước khi băm. Điều gì có thể xảy ra?

**Đáp án:** Chúng có thể tính tag khác nhau cho cùng dữ liệu nghiệp vụ; hoặc cách nối mơ hồ có thể khiến hai bộ trường khác nhau có cùng chuỗi byte, dẫn tới lỗi logic. Cần quy định **định dạng tuần tự hóa và miền thông điệp** nhất quán, có dấu phân tách/độ dài trường không mơ hồ.

**Câu 6.** Người dùng đặt mật khẩu rất phổ biến; ứng dụng lưu SHA-256 của mật khẩu. Tính chống preimage của SHA-256 có giải quyết được việc đoán mật khẩu không?

**Đáp án:** Không. Kẻ tấn công có thể thử tập mật khẩu thường gặp và so sánh digest. Cần hàm lưu mật khẩu chuyên dụng có salt, chi phí tính toán phù hợp và các biện pháp phòng thủ bổ sung.

**Câu 7.** Khi hệ thống hứng đầu vào khóa do người dùng tự chọn, vì sao hàm băm có khóa bí mật có thể hữu ích hơn một hàm băm không khóa dễ đoán?

**Đáp án:** Khóa bí mật khiến người gửi khó dự đoán bucket hoặc tự xây dựng một tập khóa có va chạm theo cùng ánh xạ, giảm khả năng hash flooding nếu thiết kế đúng. Nó **không làm biến mất** sự tồn tại toán học của các va chạm.

**Câu 8.** Với \(n=m=1000\) và giả thiết các khóa rơi độc lập, đều lên bucket, số cặp va chạm bucket kỳ vọng là bao nhiêu?

**Đáp án:** \(n(n-1)/(2m)=499{,}5\) cặp. Đây không phải số thao tác tra cứu thất bại; bảng vẫn hoạt động đúng nếu xử lý collision và so sánh khóa đầy đủ.

**Câu 9.** Một ứng dụng cần cả tìm kiếm nhanh theo ID và kiểm tra ảnh tải lên có cùng nội dung không. Có nên chỉ dùng một hàm băm duy nhất cho cả hai?

**Đáp án:** Không bắt buộc. Có thể dùng **hash của cấu trúc dữ liệu** để tìm ID trong dictionary, và dùng **digest mật mã** của byte ảnh để làm ứng viên khử trùng lặp/kiểm tra toàn vẹn. Cả hai tầng vẫn cần quy tắc xử lý collision thích hợp.

## 15. Tổng kết

**Băm phục vụ tra cứu** trả lời câu hỏi **“khóa nằm ở đâu?”**. Nó ưu tiên phân bố tốt, chi phí thấp, tương thích với so sánh khóa và xử lý va chạm để đạt hiệu năng mong muốn, thường là \(O(1)\) theo kỳ vọng với những giả thiết thích hợp.

**Băm mật mã** trả lời những câu hỏi về **độ khó tạo đầu vào giả mạo hoặc digest trùng theo chủ đích**. Những tính chất như **preimage resistance, second-preimage resistance, collision resistance** liên quan đến việc bảo vệ dữ liệu trong các giao thức; bản thân hàm băm không khóa **không xác thực nguồn gửi, không mã hóa nội dung và không phải cơ chế lưu mật khẩu hoàn chỉnh**.

Khi thiết kế giải pháp, hãy bắt đầu từ **mục tiêu và mô hình đe dọa**: bảng tra cứu cần thuật toán băm và cấu trúc xử lý va chạm; hash flooding có thể cần **keyed hashing**; kiểm tra toàn vẹn cần **digest mật mã và nguồn tham chiếu tin cậy**; xác thực thông điệp có thể cần **HMAC**; mật khẩu cần **password hashing/KDF chuyên dụng**. Không chọn một công cụ chỉ vì nó cũng được gọi là “hash”.
