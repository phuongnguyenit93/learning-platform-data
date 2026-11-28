# Collision resistance — Tính kháng va chạm của hàm băm mật mã

## 1. Collision resistance là gì?

**Collision resistance** (*tính kháng va chạm*) là thuộc tính an toàn của **hàm băm mật mã** (*cryptographic hash function*): đối thủ phải rất khó tìm được **hai thông điệp khác nhau** cho ra **cùng một giá trị băm**.

Với hàm băm H, một **va chạm (collision)** là cặp thông điệp m₁ và m₂ thỏa mãn:

~~~text
m₁ ≠ m₂
H(m₁) = H(m₂)
~~~

Điều quan trọng là đối thủ **được tự chọn cả hai thông điệp**. Họ không cần khôi phục thông điệp ban đầu từ digest; chỉ cần tạo hai đầu vào khác nhau có chung digest. Một hàm băm có tính kháng va chạm tốt khiến việc cố ý tìm ra cặp như vậy vượt quá nguồn lực tính toán khả thi với công nghệ và mô hình đe dọa dự kiến.

Ví dụ, hệ thống phát hành phần mềm tạo hash của một gói cập nhật, sau đó ký số lên digest đó. Nếu đối thủ có thể tạo một bản cập nhật vô hại và một bản độc hại với cùng digest, họ có thể tìm cách làm người ký chấp thuận bản vô hại rồi thay bằng bản độc hại mà chữ ký vẫn khớp với digest. Vì thế, **collision resistance đặc biệt quan trọng trong thiết kế chữ ký số và chứng thực dữ liệu**.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, khái niệm này gắn với quản lý khóa ở hai điểm: lựa chọn thuật toán băm dùng cùng **khóa ký số** và phân biệt hàm băm công khai với **MAC/HMAC có khóa bí mật**. Hash không tự mã hóa dữ liệu; hash, chữ ký số, HMAC, KMS/HSM và envelope encryption giải quyết những thuộc tính bảo mật khác nhau.

> **Ghi nhớ:** “Không tìm được va chạm trong vài lần thử” không chứng minh hàm băm kháng va chạm. Cần dựa vào thuật toán được đánh giá, độ dài digest, mức an toàn của giao thức và kế hoạch thay thế khi thuật toán suy yếu.

### Digest giống nhau có chắc là dữ liệu giống nhau?

**Không.** Hai dữ liệu giống nhau luôn cho cùng hash nếu cùng thuật toán và biểu diễn byte. Chiều ngược lại không được bảo đảm tuyệt đối: **hash bằng nhau không phải bằng chứng toán học rằng hai đầu vào giống nhau**.

Một hàm băm nhận thông điệp độ dài tùy ý nhưng cho kết quả dài hữu hạn. Theo **nguyên lý Dirichlet (pigeonhole principle)**, khi có nhiều thông điệp hơn số digest có thể biểu diễn, **va chạm chắc chắn tồn tại**. Mục tiêu bảo mật là làm cho việc **tìm ra** va chạm trở nên không khả thi, không phải tuyên bố rằng va chạm không tồn tại.

## 2. Phân biệt collision, preimage và second-preimage resistance

Ba thuộc tính phổ biến của hàm băm mật mã có **mục tiêu tấn công khác nhau**.

| Thuộc tính | Đầu vào kẻ tấn công có sẵn | Mục tiêu | Độ khó lý tưởng của hash n bit |
| --- | --- | --- | --- |
| **Preimage resistance** (kháng tìm tiền ảnh) | Một digest y | Tìm một thông điệp m sao cho H(m) = y | Xấp xỉ 2^n phép thử |
| **Second-preimage resistance** (kháng tiền ảnh thứ hai) | Một thông điệp cụ thể m₁ | Tìm m₂ khác m₁ nhưng H(m₂) = H(m₁) | Xấp xỉ 2^n với mô hình lý tưởng và thông điệp thông thường |
| **Collision resistance** (kháng va chạm) | Không cần thông điệp cho trước | Tự tìm **bất kỳ** m₁ khác m₂ sao cho H(m₁) = H(m₂) | Xấp xỉ 2^(n/2) nhờ birthday attack |

Các con số trên là **ước lượng cho hàm băm lý tưởng**, không phải kết quả kiểm định tuyệt đối của mọi thuật toán thật. Cấu trúc của thuật toán, kích thước thông điệp, cách sử dụng và các tấn công đã công bố có thể làm độ khó thực tế khác đi.

### Ví dụ ba tình huống

1. **Preimage:** Đối thủ biết SHA-256 của một thông điệp ngẫu nhiên đủ mạnh và muốn tìm ra thông điệp tạo digest đó.
2. **Second-preimage:** Đối thủ được cho một hợp đồng cụ thể đã ký và phải tạo một hợp đồng khác có cùng hash với chính hợp đồng đã cho.
3. **Collision:** Đối thủ được tự chuẩn bị cả hai hợp đồng khác nhau có cùng hash, rồi tìm cách đưa bản vô hại cho người ký.

Tình huống thứ ba cho đối thủ **nhiều tự do hơn**, nên với hàm băm n bit lý tưởng, tấn công collision có thể nhanh hơn đáng kể so với tấn công preimage.

**Không được suy luận:** “SHA-256 có 256 bit nên phải thử 2^256 lần mới tìm được collision”. Với mô hình lý tưởng và tấn công birthday tổng quát, mức công việc để tìm một va chạm thường ở cỡ **2^128**.

## 3. Birthday attack giải thích giới hạn của collision resistance

### 3.1. Tại sao không cần thử hết mọi digest?

Giả sử hash cho đầu ra **n bit**, tức có 2^n giá trị digest có thể xuất hiện. Ta tính hash của q thông điệp khác nhau và xem có hai kết quả trùng nhau không. Với mô hình đầu ra ngẫu nhiên độc lập gần đúng, xác suất có va chạm là:

~~~text
Pr[ít nhất một collision]
    ≈ 1 - exp( -q(q - 1) / (2 · 2^n) )
~~~

Khi q còn nhỏ so với căn bậc hai của không gian digest, có thể dùng gần đúng:

~~~text
Pr[collision] ≈ q(q - 1) / (2 · 2^n)
~~~

Xác suất đạt khoảng 50% khi q ở cỡ **1,18 × 2^(n/2)**. Đây là hiệu ứng **birthday paradox**: không phải tìm một kết quả trùng với một digest cố định, mà tìm **bất kỳ cặp** trùng nhau trong tập kết quả đã tính.

Ví dụ, nếu một ứng dụng lấy **32 bit đầu của SHA-256** làm “mã định danh duy nhất”, thì chỉ cần tạo khoảng **77 nghìn** giá trị ngẫu nhiên, xác suất xuất hiện ít nhất một va chạm đã gần 50%. Vì thế, digest ngắn có thể dùng cho phân nhóm hoặc mục đích tiện ích nào đó, nhưng **không nên coi là định danh bảo mật không thể trùng**.

### 3.2. Số bit digest và mức kháng va chạm

| Độ dài digest n | Số giá trị digest | Công việc collision tổng quát lý tưởng (xấp xỉ) |
| --- | --- | --- |
| **32 bit** | 2^32 | 2^16 phép thử (hàng chục nghìn) |
| **64 bit** | 2^64 | 2^32 phép thử |
| **128 bit** | 2^128 | 2^64 phép thử |
| **160 bit** | 2^160 | 2^80 phép thử **nếu chỉ xét birthday bound** |
| **256 bit** | 2^256 | 2^128 phép thử |
| **384 bit** | 2^384 | 2^192 phép thử |
| **512 bit** | 2^512 | 2^256 phép thử |

**Lưu ý quan trọng:** Hàng 160 bit không có nghĩa **SHA-1** còn đạt mức collision security 80 bit: SHA-1 đã có các tấn công va chạm thực tế **nhanh hơn birthday bound**. Bảng chỉ mô tả mức tính toán tổng quát trong mô hình hàm băm lý tưởng.

Ngoài ra, số lượt thử, bộ nhớ, phương pháp phát hiện va chạm và chi phí thực tế của tấn công phụ thuộc mô hình và tài nguyên. Dùng mức công việc **2^(n/2)** để hiểu độ mạnh tương đối của digest, không dùng công thức đó làm tiêu chí duy nhất phê duyệt một thuật toán.

### 3.3. Cắt ngắn hash làm giảm độ mạnh kháng va chạm

Giả sử hệ thống tính SHA-256 nhưng chỉ lưu 64 bit đầu:

~~~text
fullDigest = SHA-256(message)       # 256 bit
shortId    = first64(fullDigest)    # còn 64 bit
~~~

**Collision resistance của shortId bị giới hạn bởi 64 bit đầu ra**, nên birthday bound chỉ còn khoảng **2^32**. Việc hàm gốc có 256 bit không cứu được thiết kế đã cắt quá ngắn.

Nếu digest được sử dụng như **định danh tiện ích**, có thể chấp nhận một xác suất trùng được tính toán và có cơ chế xử lý trùng. Nếu digest làm thành phần bảo mật của **chữ ký, chứng thư, cam kết dữ liệu hoặc xác minh artifact**, phải lựa chọn thuật toán và độ dài đầu ra theo mức an toàn được yêu cầu.

## 4. Va chạm ngẫu nhiên và va chạm do đối thủ chủ động tạo

**Accidental collision** là va chạm xuất hiện ngoài ý muốn khi nhiều dữ liệu được băm. **Adversarial collision** là va chạm mà đối thủ cố ý thiết kế để vượt qua một cơ chế kiểm tra hoặc xác minh.

Đối với hệ thống bảo mật, trường hợp thứ hai thường nguy hiểm hơn vì đối thủ có thể chọn thông điệp có cấu trúc đặc biệt. Một số lớp tấn công cần nhận biết:

- **Generic birthday search:** Tính hash nhiều đầu vào rồi tìm bất kỳ cặp có cùng digest.
- **Identical-prefix collision:** Kẻ tấn công tìm hai thông điệp có cùng phần mở đầu nhất định nhưng phần sau khác, vẫn cùng digest; mức khả thi phụ thuộc thuật toán.
- **Chosen-prefix collision:** Kẻ tấn công chọn **hai phần mở đầu khác nhau**, sau đó tìm phần đuôi thích hợp để hai thông điệp hoàn chỉnh có cùng digest. Tấn công này có thể đặc biệt nguy hiểm với tài liệu hoặc chứng thư có cấu trúc, vì hai nội dung có thể mang ý nghĩa khác nhau.
- **Second-preimage attack:** Một thông điệp cụ thể đã tồn tại; đối thủ bị ràng buộc phải tìm thông điệp thứ hai trùng digest với thông điệp đó. Đây **không đồng nhất** với việc tự chuẩn bị cả hai đầu vào cho collision attack.

Không phải mọi cặp dữ liệu có hash giống nhau đều có thể dùng để giả mạo tài liệu: hệ thống còn kiểm tra định dạng, chữ ký, chính sách cấp phát, thời điểm và luồng nghiệp vụ. Nhưng **sự tồn tại của các lớp tấn công này là lý do không dùng hàm băm đã mất tính kháng va chạm cho chữ ký số mới**.

### Hash không phải mã hóa

Hash được tính từ dữ liệu theo một hàm công khai, không cần khóa bí mật. **Không có thao tác “giải mã SHA-256”** để lấy lại thông điệp. Cũng không có gì ngăn người khác tính SHA-256 của một nội dung mà họ biết.

Do đó:

- Hash giúp tạo fingerprint để đối chiếu, nhưng **không tự xác thực nguồn gửi**.
- Hash không che nội dung dữ liệu; một digest của dữ liệu có độ đoán được thấp có thể giúp người khác thử các giá trị ứng viên.
- Hash không tự bảo vệ khỏi sửa dữ liệu nếu đối thủ **có thể đồng thời thay cả dữ liệu và digest tham chiếu**.

## 5. Chọn thuật toán hash phù hợp

| Hàm băm | Độ dài digest | Tình trạng/khuyến nghị thực hành |
| --- | --- | --- |
| **MD5** | 128 bit | **Đã bị phá tính kháng va chạm**; không dùng cho chữ ký mới hoặc kiểm tra toàn vẹn có đối thủ |
| **SHA-1** | 160 bit | **Đã có va chạm thực tế và tấn công chosen-prefix**; không dùng cho chữ ký/chứng thư mới cần collision resistance |
| **SHA-256** | 256 bit | Lựa chọn phổ biến, chưa có tấn công va chạm thực tế làm mất mục tiêu bảo mật tổng quát đã biết |
| **SHA-384** | 384 bit | Phù hợp khi cần digest và mức an toàn lớn hơn; chú ý tương thích giao thức |
| **SHA-512** | 512 bit | Digest dài; mức collision security lý tưởng khoảng 256 bit |
| **SHA3-256** | 256 bit | Họ SHA-3 với cấu trúc khác SHA-2, có thể dùng khi nền tảng/giao thức hỗ trợ |
| **SHA3-512** | 512 bit | Lựa chọn SHA-3 với digest dài hơn; cần xem đúng đặc tả ứng dụng |

**Không coi độ dài digest là bảo đảm đủ.** SHA-1 dù có 160 bit vẫn không còn đáp ứng mức kháng va chạm theo birthday bound do các điểm yếu đã bị khai thác. Ngược lại, không cần chọn SHA-512 cho mọi ứng dụng nếu SHA-256 đáp ứng mức an toàn, giới hạn giao thức và yêu cầu hiện tại.

Khi thiết kế hệ thống mới, nên ưu tiên **SHA-256/SHA-384, SHA-512 hoặc SHA-3** tùy chính sách, môi trường và thuật toán chữ ký đi kèm. Tài liệu này không thay thế hướng dẫn mật mã, tiêu chuẩn tuân thủ hoặc đánh giá an toàn cập nhật của tổ chức.

### Nếu hệ thống cũ vẫn dùng SHA-1 hoặc MD5?

Các bước nên thực hiện là **kiểm kê mục đích sử dụng**, phân biệt nơi hash chỉ đóng vai trò checksum không đối kháng với nơi dùng để xác minh chữ ký, chứng thư, artifact hoặc cam kết dữ liệu, rồi lập kế hoạch thay thế. Với trường hợp yêu cầu kháng va chạm, **không tiếp tục dùng cho ký mới**. Việc chuyển sang hàm mới có thể đòi thay định dạng manifest, giao thức xác minh, chữ ký số hoặc chính sách chứng thư.

Không tự động coi mọi dữ liệu lịch sử đã hash bằng SHA-1 đều bị giả mạo; phải đánh giá mô hình tấn công, cách tạo chữ ký, thời điểm, bằng chứng kiểm toán và khả năng kiểm tra bằng thuật toán an toàn hơn. Nhưng cũng không nên mặc định chữ ký/hash cũ có cùng mức bảo đảm như giải pháp hiện đại.

## 6. Vì sao collision resistance quan trọng với chữ ký số và chứng thư?

Trong nhiều sơ đồ chữ ký, thông điệp được băm trước hoặc trong quy trình ký. Người kiểm tra chữ ký dùng cùng hàm băm và thuật toán ký để xác minh.

~~~mermaid
sequenceDiagram
    participant A as Người chuẩn bị dữ liệu
    participant S as Hệ thống ký có private key
    participant V as Người kiểm tra
    A->>S: Gửi thông điệp được phép ký
    Note over S: Tính digest và ký theo thuật toán chuẩn
    S-->>A: Chữ ký số
    A->>V: Thông điệp và chữ ký
    Note over V: Tính digest, kiểm tra bằng public key
    V-->>A: Chấp nhận hoặc từ chối
~~~

### Kịch bản collision nguy hiểm

Giả sử đối thủ có thể tạo:

~~~text
Document_A = "Tài liệu lành tính" + phần điều chỉnh A
Document_B = "Tài liệu độc hại"  + phần điều chỉnh B

Document_A != Document_B
H(Document_A) == H(Document_B)
~~~

Nếu hệ thống ký dùng cơ chế chịu ảnh hưởng bởi collision của H, đối thủ có thể tìm cách **đưa Document_A để được ký hợp lệ**, rồi thay bằng Document_B cùng digest. Kết quả xác minh chữ ký có thể bị đánh lừa trong những điều kiện tấn công thích hợp.

Đây là **mô hình rủi ro**, không phải khẳng định rằng có thể tạo hai tài liệu tùy ý với cùng SHA-256 hôm nay. Với thuật toán hiện đại và hệ thống ký được thiết kế đúng, việc tạo cặp như vậy phải nằm ngoài khả năng thực tế theo giả định bảo mật.

### Kiểm soát ngoài việc chọn hash

1. **Sử dụng thuật toán chữ ký chuẩn:** Chẳng hạn RSA-PSS, ECDSA với digest thích hợp, hoặc Ed25519 theo cơ chế định nghĩa của thuật toán. Không tự xây phương án “ký hash” bằng phép toán RSA thô.
2. **Chọn digest được hỗ trợ an toàn:** Không dùng MD5/SHA-1 cho chữ ký mới có yêu cầu kháng va chạm.
3. **Ràng buộc thông điệp cần ký:** Kiểm tra nguồn, định dạng, quyền, đối tượng, loại tài liệu, phiên bản và trạng thái phê duyệt. Một HSM có private key không xuất được vẫn có thể bị lạm dụng như **signing oracle** nếu API cho ký bất kỳ dữ liệu nào.
4. **Quy định biểu diễn byte:** Ký/xác minh **cùng một dãy byte**. Cần xử lý encoding UTF-8, chuẩn hóa Unicode, kết thúc dòng, canonical JSON/XML nếu giao thức yêu cầu; không dùng các dạng serialization mơ hồ.
5. **Quản lý chứng thư và public key:** Có chuỗi tin cậy, thời gian hiệu lực, trạng thái thu hồi và chính sách lưu bằng chứng cho chữ ký lịch sử.
6. **Quản lý private key:** Phân tách owner/custodian, giới hạn quyền `Sign`, duy trì kiểm toán và quy trình rotation/thu hồi khi thuật toán hoặc key bị nghi yếu.

### Hashing cho artifact integrity: nguồn digest có đáng tin không?

Kiểm tra `SHA-256(file_downloaded) == digest_from_manifest` chỉ có giá trị xác thực nguồn nếu **manifest/digest tham chiếu được bảo vệ và xác thực** qua kênh hoặc chữ ký đáng tin. Nếu kẻ tấn công có thể thay cả file lẫn manifest, họ chỉ việc tính lại hash của file độc hại. Khi đó, collision resistance không phải điểm yếu: thiết kế **thiếu xác thực nguồn digest**.

Trong quy trình phát hành an toàn, có thể ký manifest bằng private signing key bảo vệ trong KMS/HSM. Bên nhận xác minh chữ ký và đối chiếu digest artifact; bước này cần cả **kháng va chạm của hash**, **an toàn của chữ ký** và **quản lý khóa/tin cậy chứng thư**.

## 7. Collision resistance và MAC/HMAC: giống nhau hay khác nhau?

**MAC** (*Message Authentication Code*) dùng **khóa bí mật K** để tính thẻ xác thực (tag). Người giữ khóa có thể xác minh rằng thông điệp chưa bị sửa bởi đối tượng không có khóa, trong phạm vi mô hình an toàn của MAC.

**HMAC** (*Hash-based Message Authentication Code*) là một cơ chế MAC xây dựng từ một hàm băm và khóa bí mật. Với HMAC-SHA-256:

~~~text
tag = HMAC-SHA256(K, message)
valid = Verify_HMAC(K, message, tag)
~~~

Cần phân biệt:

| Đặc tính | Hash công khai SHA-256 | HMAC-SHA-256 | Chữ ký số |
| --- | --- | --- | --- |
| Có khóa bí mật? | Không | **Có**, khóa chung K | Có, private signing key |
| Mục đích chủ yếu | Digest, fingerprint, thành phần giao thức | **Xác thực nguồn trong nhóm biết khóa** và toàn vẹn | Xác minh bằng public key; phù hợp cơ chế ký số |
| Bất kỳ ai có thể tính kết quả từ thông điệp? | Có | Chỉ bên có K | Chỉ bên có quyền ký bằng private key |
| Ai kiểm tra kết quả? | Ai cũng có thể tính hash | Bên có K | Bên có public verification key |
| Collision resistance có vai trò? | Là thuộc tính cốt lõi khi dùng cho chữ ký/cam kết | Tính an toàn MAC **không chỉ được đánh giá bằng collision resistance của hash nền** | Thuật toán ký và hash kèm theo phải đạt các yêu cầu tương ứng |
| Có bảo mật nội dung? | Không | Không | Không |

### Không đánh đồng collision của hash nền với giả mạo HMAC

HMAC có cấu trúc dùng **khóa bí mật** và hai lớp biến đổi. Việc tìm được va chạm công khai của một hàm băm **không tự động chứng minh** có thể tạo HMAC hợp lệ cho thông điệp chưa được ký khi không biết khóa. Mức an toàn của HMAC được đánh giá theo các giả định về hash/PRF, cách cấp khóa, độ dài tag và mô hình đối thủ.

Điều đó **không phải lời khuyên tiếp tục dùng HMAC-MD5/HMAC-SHA1 trong thiết kế mới**. Chọn HMAC-SHA-256 hoặc thuật toán MAC hiện đại được chính sách phê duyệt giúp đồng bộ tiêu chuẩn, giảm nợ kỹ thuật và tránh phụ thuộc thuật toán đã suy yếu ở những khía cạnh khác.

**Không tự triển khai MAC bằng cách ghép khóa rồi băm**:

~~~text
# Không dùng làm thiết kế MAC tùy tiện:
SHA256(secret || message)
SHA256(message || secret)
~~~

Các cấu trúc tự chế có thể gặp lỗi như length-extension, thiếu phân tách ngữ cảnh, lỗi mã hóa hoặc thiếu phân tích bảo mật. Dùng **HMAC chuẩn**, AES-CMAC hoặc cơ chế MAC được giao thức quy định.

### HMAC tag bị cắt ngắn có giống digest bị cắt ngắn không?

Không hoàn toàn. Với hash công khai, **collision resistance** của digest k bit bị giới hạn khoảng **2^(k/2)** theo birthday bound. Với **MAC**, bài toán trọng tâm là **giả mạo tag của thông điệp chưa được xác thực khi không biết K**; xác suất đoán tag có thể ở mức khoảng 2^(-t) cho mỗi lần thử trong mô hình lý tưởng với tag t bit, nhưng còn phụ thuộc hạn mức truy vấn, giao thức và chính sách xác minh.

Vì vậy không nên lấy `2^(tagBits/2)` làm câu trả lời mặc định cho độ khó giả mạo HMAC. Nếu rút ngắn tag, phải áp dụng **quy tắc độ dài tối thiểu, hạn mức xác minh và quy tắc riêng của thuật toán/giao thức**, không tự cắt tùy tiện.

### HMAC không thay thế mã hóa

HMAC đảm bảo **tính toàn vẹn và xác thực** trong phạm vi các bên giữ khóa, nhưng **không che giấu nội dung**. Khi cần cả bí mật và toàn vẹn dữ liệu, thường ưu tiên **AEAD** như AES-GCM hoặc ChaCha20-Poly1305 với nonce đúng quy tắc; không tự lắp ghép một sơ đồ mã hóa và MAC nếu giao thức chuẩn đã có.

## 8. Ví dụ Java: SHA-256 và HMAC-SHA-256

Ví dụ Java sau cho thấy sự khác nhau giữa một digest không có khóa và một MAC có khóa. Mã chạy với JDK có hỗ trợ `SHA-256` và `HmacSHA256` trong JCA/JCE. Khóa được sinh ngẫu nhiên **chỉ để minh họa**, không lưu ra file.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.GeneralSecurityException;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class CollisionResistanceDemo {

    static byte[] hash(byte[] message) throws GeneralSecurityException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        return digest.digest(message);
    }

    static byte[] hmac(SecretKey key, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        return mac.doFinal(message);
    }

    static boolean verify(SecretKey key, byte[] message, byte[] expectedTag)
            throws GeneralSecurityException {
        if (expectedTag == null || expectedTag.length != 32) {
            return false; // ở ví dụ này chỉ chấp nhận HMAC-SHA-256 đủ 32 byte
        }
        byte[] actualTag = hmac(key, message);
        return MessageDigest.isEqual(actualTag, expectedTag);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator keyGenerator = KeyGenerator.getInstance("HmacSHA256");
        keyGenerator.init(256);
        SecretKey macKey = keyGenerator.generateKey();

        byte[] original = "tenant=shopA;invoice=123;amount=100"
                .getBytes(StandardCharsets.UTF_8);
        byte[] changed = "tenant=shopA;invoice=123;amount=900"
                .getBytes(StandardCharsets.UTF_8);

        byte[] d1 = hash(original);
        byte[] d2 = hash(changed);
        System.out.println("SHA-256 digest length: " + d1.length);
        System.out.println("Same digest for these two inputs: "
                + MessageDigest.isEqual(d1, d2));

        byte[] tag = hmac(macKey, original);
        System.out.println("Original MAC valid: "
                + verify(macKey, original, tag));
        System.out.println("Changed message MAC valid: "
                + verify(macKey, changed, tag));

        // Không in byte[] của key hoặc lưu secret vào source code.
    }
}
~~~

Kết quả dự kiến:

~~~text
SHA-256 digest length: 32
Same digest for these two inputs: false
Original MAC valid: true
Changed message MAC valid: false
~~~

**Lưu ý:** `d1 != d2` chỉ chứng minh **hai thông điệp cụ thể** không va chạm. Nó **không chứng minh** SHA-256 không có va chạm hoặc bất kỳ cặp thông điệp nào khác đều khác hash. Chương trình cũng không phải kiểm thử tính an toàn mật mã của thuật toán.

Ở production, không tạo khóa HMAC mới mỗi khi xử lý một yêu cầu nếu các bên cần xác minh lâu dài. Khóa phải được tạo/quản lý, cấp cho bên được phép, gắn với **key ID/version** và có chính sách rotation. Dữ liệu cần xác thực phải có **biểu diễn byte nhất quán**, chẳng hạn canonical JSON hoặc serialization có length prefix; chuỗi `tenant=...;amount=...` trong ví dụ chỉ để minh họa, không phải định dạng giao thức an toàn hoàn chỉnh.

### Vì sao dùng `MessageDigest.isEqual`?

So sánh thẻ xác thực bằng phép so sánh byte thông thường có thể có hành vi dừng sớm theo vị trí byte sai, mở ra rủi ro rò rỉ thời gian trong một số mô hình tấn công. `MessageDigest.isEqual` là API phù hợp để so sánh digest/tag trong Java. **Phải kiểm tra độ dài tag theo giao thức** và tránh trả thông báo lỗi quá chi tiết cho đối thủ.

## 9. Quản lý khóa HMAC và khóa ký số trong KMS/HSM

Hàm băm SHA-256 công khai **không có key material để cấp phát, xoay vòng hoặc hủy**. Ngược lại, HMAC là MAC **có khóa bí mật**, còn chữ ký số **có private signing key**. Khi kết hợp hash và khóa, yêu cầu quản lý khóa phải áp dụng cho thành phần có khóa.

| Tài sản | Có vật liệu khóa bí mật? | Người cần quyền | Vòng đời cần quản lý |
| --- | --- | --- | --- |
| **SHA-256 digest công khai** | Không | Bất kỳ ai cần hash/kiểm tra | Quản lý thuật toán, độ dài digest, thay phiên bản định dạng |
| **HMAC key** | Có | Các dịch vụ tạo/xác minh MAC theo chính sách | Tạo, cấp quyền, bảo vệ, rotation, thu hồi, hủy |
| **Private signing key** | Có | Dịch vụ được cấp phép ký; custodian quản trị | Cặp khóa, chứng thư, key usage, rotation và lưu chứng cứ chữ ký |
| **Public verification key** | Không bí mật | Bên xác minh | Phân phối tin cậy, ràng buộc danh tính, trạng thái chứng thư |
| **DEK/KEK của envelope encryption** | Có | Dịch vụ mã hóa/giải mã, KMS theo quyền | Quản lý bản mã cũ, phiên bản khóa, backup và hủy an toàn |

### 9.1. KMS/HSM giúp gì?

- Tạo khóa HMAC/signing key bằng nguồn ngẫu nhiên phù hợp, nếu sản phẩm hỗ trợ đúng loại khóa.
- Hạn chế xuất private key hoặc HMAC key; một số dịch vụ cho phép **GenerateMac/VerifyMac**, **Sign/Verify** bằng key handle.
- Cấp quyền tối thiểu cho danh tính ứng dụng; tách **quyền tạo MAC/ký** khỏi **quyền quản trị policy/rotation/hủy**.
- Ghi sự kiện về `keyId`, người gọi, thao tác, thời gian, kết quả và thay đổi quyền; hạn chế ghi plaintext nhạy cảm, secret hoặc private key.
- Quản lý version, disable hoặc lịch hủy và phương án recovery theo cơ chế của nhà cung cấp.

**Không giả định mọi KMS đều hỗ trợ HMAC** hoặc cho phép cùng một API `GenerateMac`/`VerifyMac`. Một số KMS chỉ quản lý khóa AES hoặc khóa bất đối xứng với tập thuật toán riêng. Phải kiểm tra danh mục hỗ trợ, giới hạn API và semantics của key state trong sản phẩm được chọn.

### 9.2. Phân công owner, custodian và key user

| Vai trò | Quyết định hoặc thao tác | Cần tránh |
| --- | --- | --- |
| **Key owner** | Phê duyệt mục đích, phạm vi dữ liệu, ứng dụng được dùng, thời hạn lưu và rotation | Tự cấp phép dùng khóa mà không có kiểm soát độc lập |
| **Key custodian** | Tạo/cấu hình khóa, quản lý KMS/HSM, thực thi quyền và vòng đời theo phê duyệt | Tự có quyền tạo MAC/ký số trái nhu cầu |
| **Key user / dịch vụ** | Gọi `GenerateMac`, `VerifyMac`, `Sign` hoặc `Verify` được cấp trên đúng key | Sửa key policy, xuất key material, xóa khóa |
| **Auditor** | Xem bằng chứng phê duyệt, log sử dụng/quản trị và kết quả rà soát | Thay quyền hoặc thực hiện phép toán nhạy cảm |

Trong HMAC, **các bên cùng giữ khóa có thể tạo tag**; do đó một tag hợp lệ **không chứng minh chỉ riêng người gửi cụ thể** đã tạo nó nếu nhiều bên chia sẻ khóa. Khi cần bên thứ ba công khai xác minh và gắn trách nhiệm ký với một chủ thể, cân nhắc **chữ ký số** cùng cơ chế quản lý chứng thư và private key thích hợp.

### 9.3. Rotation không được làm mất khả năng xác minh dữ liệu cũ

Giả sử webhook sử dụng `HMAC-SHA-256` với khóa `v1`; sau đó hệ thống chuyển sang `v2`:

1. **Tạo và cấp phát `v2`** bằng cơ chế an toàn. Hai bên có thể cần cửa sổ chuyển đổi có kiểm soát.
2. **Thông điệp mới dùng `v2`**; gắn key ID/version vào envelope hoặc metadata theo giao thức, và ràng buộc metadata vào dữ liệu được xác thực nếu cần.
3. **Thông điệp cũ** có thể còn cần xác minh với `v1` trong thời gian chờ giao hàng, retry hoặc lưu trữ. Chỉ giữ quyền xác minh cũ trong phạm vi và thời gian đã duyệt.
4. **Thu hồi/hủy `v1`** sau khi không còn phụ thuộc và đã xử lý bản sao lưu/retention; nếu khóa bị lộ, cần quy trình ứng cứu khẩn cấp thay vì chờ lịch rotation thông thường.

Không nên tự động chuyển mọi tag cũ sang khóa mới bằng cách “tính lại HMAC” khi chưa có quyền và bằng chứng dữ liệu gốc là đáng tin. Một tag chỉ xác thực **với khóa/phiên bản đã tạo ra nó**.

## 10. Collision resistance trong hệ thống mã hóa, AEAD và envelope encryption

Hệ thống bảo mật hiện đại thường kết hợp các kỹ thuật với vai trò khác nhau:

~~~mermaid
flowchart TD
    D[Dữ liệu cần bảo vệ] --> E[AEAD với DEK: AES-GCM]
    E --> C[Ciphertext + nonce + tag]
    K[KEK trong KMS/HSM] --> W[Bọc hoặc giải bọc DEK]
    W --> C
    D --> H[SHA-256 nếu cần fingerprint/manifest]
    H --> M[Digest]
    M --> S[Chữ ký số bằng private signing key]
    S --> V[Bên nhận xác minh bằng public key]
    A[Định danh, key policy, audit] --> K
    A --> S
~~~

- **Collision resistance** của SHA-256 quan trọng khi digest đóng vai trò thành phần cần tin cậy của chữ ký/manifest/cam kết dữ liệu.
- **AEAD** như AES-GCM bảo vệ **bí mật và tính toàn vẹn của ciphertext/AAD** theo khóa đối xứng và nonce đúng quy tắc. Tag GCM **không phải SHA-256 digest**; độ an toàn của GCM không thể được kết luận chỉ từ collision resistance của SHA-256.
- **DEK (Data Encryption Key)** mã hóa dữ liệu. **KEK (Key Encryption Key)** trong KMS/HSM bọc DEK, tạo nên **envelope encryption**. Quản lý DEK/KEK đòi vòng đời, phân quyền và khả năng giải mã dữ liệu cũ.
- **Chữ ký số** dùng private key để cho bên khác xác minh nguồn và tính toàn vẹn thông điệp. Hash trong sơ đồ ký cần được chọn phù hợp; không phải thuật toán ký nào cũng bộc lộ cùng một API “ký digest”.
- **HMAC** phù hợp xác thực giữa các bên có khóa chung; nếu cần công khai xác minh bởi bên không biết secret, chữ ký số là công cụ khác.

### Phân biệt ba kiểu “toàn vẹn”

| Bài toán | Phương pháp có thể phù hợp | Điều kiện then chốt |
| --- | --- | --- |
| Phát hiện lỗi truyền tải tình cờ | Checksum hoặc hash thông thường | Biết giới hạn xác suất trùng và dữ liệu tham chiếu |
| Phát hiện chỉnh sửa có đối thủ giữa các bên biết secret | HMAC hoặc AEAD phù hợp | Khóa bí mật an toàn; xác thực tag; nonce nếu có |
| Xác minh artifact/phát hành từ một chủ thể | Chữ ký số trên manifest/digest theo giao thức chuẩn | Private key được bảo vệ, public key/chứng thư được tin cậy, hash kháng va chạm |

Việc **dùng hash công khai** nhưng bỏ qua xác thực nguồn manifest không được xem là một MAC, dù dùng SHA-512.

## 11. Rủi ro về encoding, canonicalization và domain separation

Ngay cả khi hàm băm có tính kháng va chạm tốt, chương trình vẫn có thể cho ra hai digest giống nhau đối với hai đối tượng **được ứng dụng hiểu khác nhau**, vì việc chuyển từ đối tượng sang byte bị thiết kế sai.

### 11.1. Nối chuỗi mơ hồ không phải là hash collision

Ví dụ ứng dụng tính:

~~~text
H( userId || amount )
~~~

Nếu không có **length prefix, delimiter được escape** hoặc một serialization xác định, các cặp giá trị khác nhau có thể tạo **cùng một chuỗi byte trước khi hash**, như:

~~~text
userId="12", amount="34" => bytes "1234"
userId="1",  amount="234" => bytes "1234"
~~~

Hai đầu vào **ở mức đối tượng nghiệp vụ** khác nhau, nhưng thông điệp đưa cho hàm băm lại **giống hệt nhau**. Đây **không phải cryptographic hash collision** vì các byte đầu vào của H không khác nhau. Chọn SHA-512 thay SHA-256 không sửa được lỗi này.

Cách xử lý: dùng canonical serialization, định dạng có length prefix, kiểu trường và thứ tự cố định, encoding nhất quán. Với JSON/XML, quy tắc canonicalization cần được quy định ở cả bên ký và bên kiểm tra. Nếu có nhiều kiểu thông điệp, gắn **domain separation** và phiên bản giao thức để ngăn sử dụng nhầm digest/tag giữa các mục đích.

### 11.2. Domain separation

Cần tách rõ ngữ cảnh, ví dụ:

~~~text
hashForInvoice = SHA256(encode("invoice-signature/v1", invoiceBytes))
hashForToken   = SHA256(encode("token-binding/v1", tokenBytes))
~~~

`encode` ở đây phải là một **phép mã hóa các trường không mơ hồ**. Domain separation giúp tránh dùng cùng digest trong những ngữ cảnh có thể tương tác nguy hiểm; nó **không tự biến một hàm băm đã bị phá collision resistance thành an toàn**.

## 12. Tình huống thực tế: ký manifest bản phát hành

Giả sử đội nền tảng xây hệ thống phát hành một gói `billing-service.jar`. Mục tiêu là người triển khai có thể kiểm tra gói nhận được đúng là bản đã được duyệt, dù nguồn tải về hoặc đường truyền có thể bị can thiệp.

**Luồng đề xuất:**

1. Hệ thống build tạo artifact và kiểm tra quy trình phê duyệt phát hành.
2. Tính **SHA-256** trên **chính bytes artifact** đã đóng gói. Manifest lưu digest, version, định danh artifact, thuật toán và thông tin cần xác minh.
3. Chuẩn hóa biểu diễn manifest theo định dạng thống nhất, rồi dùng **private signing key** đã cấp quyền trong KMS/HSM để ký bằng thuật toán chữ ký được phê duyệt.
4. Bên triển khai xác minh **chữ ký manifest** với public key/chứng thư đáng tin; đối chiếu digest artifact tải về với digest trong manifest đã xác thực.
5. Ghi audit về artifact ID, key ID/version, thời điểm, danh tính hệ thống, phê duyệt và kết quả kiểm tra; không lưu private key trong build artifact.

~~~mermaid
sequenceDiagram
    participant CI as Pipeline
    participant HSM as KMS/HSM
    participant Repo as Artifact Repository
    participant Deploy as Deployment Agent
    CI->>CI: Build và phê duyệt artifact
    CI->>CI: SHA-256 trên bytes artifact
    CI->>HSM: Sign(manifest chuẩn hóa, key ID)
    HSM-->>CI: Chữ ký
    CI->>Repo: Artifact + manifest + chữ ký
    Deploy->>Repo: Tải các thành phần
    Repo-->>Deploy: Artifact + manifest + chữ ký
    Deploy->>Deploy: Verify manifest bằng public key tin cậy
    Deploy->>Deploy: So sánh SHA-256 artifact với manifest
    Deploy->>Deploy: Chấp nhận hoặc từ chối phát hành
~~~

**Phân tích an ninh:**

- Nếu manifest không được ký/xác thực, kẻ tấn công có thể thay cả artifact và digest: **không cần tìm hash collision**.
- Nếu dùng một hàm băm đã bị phá collision resistance trong quy trình ký, có nguy cơ đối thủ chuẩn bị cặp nội dung khác nhau cùng digest để đánh lừa bước ký/đối chiếu.
- Nếu private signing key bị đánh cắp hoặc API `Sign` bị lạm dụng, SHA-256 có mạnh đến đâu cũng không ngăn đối thủ tạo chữ ký hợp lệ trên dữ liệu độc hại.
- Nếu artifact được đóng gói lại sau lúc tính digest (ví dụ đổi timestamp trong ZIP/JAR), hash sẽ khác; phải ký/xác minh đúng **bytes cuối cùng** và thống nhất quy trình reproducible/canonicalization khi cần.
- Khi xoay vòng private signing key, phải phân phối public key/chứng thư mới và giữ bằng chứng đủ để xác minh artifact lịch sử theo chính sách.

## 13. Sai lầm phổ biến và cách xử lý

| Sai lầm | Rủi ro/hệ quả | Giải pháp |
| --- | --- | --- |
| Khẳng định hash mạnh thì “không bao giờ trùng” | Thiết kế bỏ qua xác suất và phạm vi tấn công | Hiểu hash hữu hạn, birthday bound và độ mạnh thực tế |
| Cho rằng SHA-256 có collision security 256 bit | Đánh giá sai mức công việc của birthday attack | Độ mạnh lý tưởng khoảng **128 bit** đối với collision |
| Dùng MD5/SHA-1 trong chữ ký mới | Tấn công va chạm thực tế ảnh hưởng tính tin cậy | Chuyển sang SHA-256/SHA-3 hoặc thuật toán được phê duyệt |
| Cắt digest quá ngắn để làm chứng cứ bảo mật | Va chạm trở nên khả thi | Giữ độ dài phù hợp mức an toàn |
| So hash từ file và hash công bố ngay cạnh file nhưng cả hai không xác thực | Đối thủ thay cả file lẫn digest | Xác thực manifest/kênh hoặc chữ ký số |
| Tự làm MAC bằng `SHA256(secret || message)` | Sơ đồ chưa được phân tích; nguy cơ lỗi length extension/giao thức | Dùng HMAC chuẩn hoặc MAC được chứng minh |
| Tưởng hash collision tự động là HMAC forgery | Đánh giá sai thuộc tính của MAC có khóa | Tách collision resistance khỏi unforgeability, kiểm soát K và tag |
| Dùng HMAC nhưng giữ key trong source code | Bên không được phép vẫn tạo tag | Secret manager/KMS/HSM, IAM tối thiểu, rotation |
| Dùng chuỗi ghép không phân định trường để hash/ký | Hai đối tượng khác nhau thành cùng bytes | Canonical serialization, length prefix, schema và domain separation |
| So tag MAC bằng kiểm tra byte dừng sớm | Có thể rò rỉ thông tin qua timing | Dùng API so sánh digest phù hợp và quy trình xác minh đúng |
| Xoay HMAC key nhưng quên tag cũ còn chờ kiểm tra | Webhook/retry hợp lệ bị từ chối hoặc giữ key cũ quá lâu | Key version, thời gian chuyển tiếp, ngừng dùng và hủy có kiểm soát |
| Tin rằng dùng SHA-512 sẽ sửa lỗi lộ private key | Nhầm mô hình đe dọa | Phân quyền `Sign`, bảo vệ private key và audit độc lập |

## 14. Checklist thiết kế Hash/MAC và quản lý khóa

1. **Mục đích:** Hash đang dùng để phát hiện lỗi tình cờ, làm fingerprint, làm đầu vào chữ ký hay để xác thực thông điệp? Có cần HMAC/chữ ký số thay hash công khai không?
2. **Thuật toán:** Có dùng SHA-256/SHA-384/SHA-512/SHA-3 đúng mức an toàn? Có còn MD5/SHA-1 ở luồng ký hoặc chứng thực quan trọng không?
3. **Độ dài digest:** Có bị cắt ngắn? Mức kháng va chạm thực tế đáp ứng số lượng dữ liệu và đối thủ dự kiến không?
4. **Phân biệt thuộc tính:** Nhóm kỹ thuật có hiểu **collision**, **second-preimage**, **preimage** và tấn công birthday là các bài toán khác nhau không?
5. **Nguồn digest:** Digest/manifest tham chiếu có được xác thực bằng kênh hoặc chữ ký tin cậy không? Người dùng có đang so dữ liệu với một checksum không đáng tin không?
6. **Encoding:** Dữ liệu đưa vào hash/MAC có biểu diễn byte thống nhất, không mơ hồ, ràng buộc schema/version và domain separation khi cần không?
7. **HMAC:** Khóa K có được sinh và giữ bí mật, tách theo mục đích/tenant nếu cần, giới hạn quyền tạo/xác minh MAC và quản lý độ dài tag không?
8. **Chữ ký số:** Private signing key có trong KMS/HSM hoặc nơi bảo vệ phù hợp, giới hạn `Sign`, kiểm tra nội dung được ký và phân phối public key/chứng thư đáng tin không?
9. **Vòng đời:** Có owner/custodian, key inventory, rotation, revoke, disable, retention và hủy cho **HMAC/signing key**? Khi đổi key có xử lý đúng tag/chữ ký lịch sử không?
10. **Mã hóa dữ liệu:** Khi dùng envelope encryption, DEK/KEK và AEAD tag có được quản lý theo chức năng riêng; không nhầm SHA digest với cơ chế mã hóa/xác thực AEAD không?
11. **Kiểm toán:** Có ghi key ID/version, người gọi, thao tác, kết quả và sự kiện đổi quyền mà không log private key/HMAC key hay dữ liệu nhạy cảm không?
12. **Ứng cứu:** Có kế hoạch thay thuật toán hash đã suy yếu và khóa bị lộ, cập nhật bên xác minh, kiểm tra artifact cũ và đánh giá phạm vi ảnh hưởng không?

### Ghi nhớ

**Collision resistance** yêu cầu phải rất khó tìm **hai thông điệp khác nhau có cùng hash**. Với hash lý tưởng **n bit**, tấn công birthday tổng quát cần khoảng **2^(n/2)** công việc; vì vậy SHA-256 thường được xem là có mức kháng va chạm lý tưởng khoảng **128 bit**, còn **MD5 và SHA-1 đã không còn thích hợp cho ứng dụng chữ ký mới cần thuộc tính này**. Hash công khai **không tự xác thực nguồn**; **HMAC dùng khóa bí mật** để xác thực thông điệp giữa các bên biết khóa; **chữ ký số** dùng private key để bên giữ public key kiểm tra. Thiết kế an toàn phải kết hợp lựa chọn hash với **KMS/HSM, quản lý khóa HMAC/private signing key, kiểm soát truy cập, xoay vòng, thu hồi, hủy và kiểm toán**, đồng thời phân biệt rõ các vai trò của hash, MAC, AEAD và envelope encryption.
