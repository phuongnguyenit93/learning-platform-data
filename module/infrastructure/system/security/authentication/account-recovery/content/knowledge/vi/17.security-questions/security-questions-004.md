# Question answer storage — Lưu trữ câu trả lời câu hỏi bảo mật

## 1. Mục tiêu và giới hạn sử dụng

Trong chương **Security Questions** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, bài học này giải thích cách bảo vệ câu trả lời câu hỏi bảo mật đang tồn tại trong hệ thống kế thừa. Trọng tâm là dữ liệu lưu ở đâu, được biến đổi thế nào, được xác minh ra sao và cần xử lý gì khi đổi thuật toán hoặc lộ dữ liệu.

Câu trả lời như tên trường học, nơi sinh hay tên thú cưng có thể đồng thời là dữ liệu cá nhân và giá trị được dùng lại ở nhiều dịch vụ. Thiết kế lưu trữ cần giảm thiệt hại khi cơ sở dữ liệu bị lấy cắp, nhưng không thể làm một thông tin dễ đoán trở thành bằng chứng mạnh.

OWASP định vị hướng dẫn về security questions cho mục đích kế thừa và cảnh báo về việc dùng chúng làm yếu tố xác thực. NIST SP 800-63B-4 cũng quy định không yêu cầu KBA hoặc câu hỏi bảo mật khi người dùng chọn mật khẩu. Không nên diễn giải việc lưu trữ đúng kỹ thuật thành sự chấp thuận dùng câu hỏi bảo mật để khôi phục MFA hoặc passkey. [OWASP Choosing and Using Security Questions](https://cheatsheetseries.owasp.org/cheatsheets/Choosing_and_Using_Security_Questions_Cheat_Sheet.html), [NIST SP 800-63B-4, Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#passwordver)

Sau bài học, người học có thể:

- Phân biệt băm, salt, pepper và mã hóa trong lưu trữ câu trả lời.
- Thiết kế bản ghi verifier có phiên bản, không giữ câu trả lời đọc được.
- Xử lý Unicode và tiếng Việt nhất quán giữa lúc ghi và lúc đối chiếu.
- Giới hạn dò đoán trực tuyến và giảm khả năng dò ngoại tuyến.
- Nâng cấp, xoay khóa, thu hồi và loại bỏ dữ liệu kế thừa có kiểm soát.

Các schema, luồng và mã Java dưới đây là **thiết kế tham khảo cho hệ thống kế thừa**, không phải đề xuất thêm câu hỏi bảo mật vào sản phẩm mới. Kết quả khớp câu trả lời chỉ được coi là một quan sát bị giới hạn bởi chính sách; nó không tự cấp token reset, không tắt MFA và không tạo session ứng dụng.

## 2. Dữ liệu cần bảo vệ và mô hình đe dọa

### 2.1. Câu trả lời có ít giá trị khả dĩ hơn người thiết kế nghĩ

Giả sử câu hỏi hỏi tháng sinh và chỉ chấp nhận số từ 1 đến 12. Với phân bố đồng đều giả định, không gian đáp án chỉ có 12 phần tử, tương đương khoảng log2(12) = 3,58 bit. Thực tế phân bố và thông tin phụ trợ có thể khiến việc đoán còn dễ hơn.

Salt ngẫu nhiên dài không làm đáp án có thêm entropy. Kẻ tấn công lấy được verifier có thể thử lần lượt 12 ứng viên cho từng bản ghi, nếu họ có đủ vật liệu để tính lại verifier.

Ngay cả câu trả lời dài cũng có thể dễ đoán khi xuất hiện trên mạng xã hội hoặc trong một vụ lộ dữ liệu khác. Độ dài chuỗi không đồng nghĩa với lượng bí mật thực tế.

### 2.2. Các ranh giới tin cậy

| Tình huống | Dữ liệu hoặc khả năng bị lộ | Mục tiêu của thiết kế lưu trữ |
| --- | --- | --- |
| Chỉ bị đọc trộm cơ sở dữ liệu | Verifier, salt, question ID và metadata | Tăng chi phí đoán; bảo vệ thêm bằng khóa bí mật tách biệt |
| Lộ cơ sở dữ liệu và pepper | Có thể tính thử đầy đủ ngoại tuyến | Băm chậm vẫn tạo chi phí, nhưng đáp án yếu vẫn nguy hiểm |
| Chiếm tiến trình ứng dụng | Có thể đọc đầu vào hoặc gọi dịch vụ khóa | Không hứa pepper giải quyết được toàn bộ việc chiếm ứng dụng |
| Nhân viên xem log hoặc ticket | Có thể gặp câu trả lời bị sao chép | Không đưa câu trả lời vào kênh quan sát và hỗ trợ |
| Sửa được dữ liệu lưu trữ | Có thể thay verifier, metadata hoặc trạng thái | Kiểm soát quyền ghi, phiên bản, audit và tính toàn vẹn |
| Gửi nhiều lần đoán trực tuyến | Có thể dùng hệ thống làm oracle kiểm tra | Giới hạn thử và không tiết lộ câu nào đúng |

Băm một chiều chủ yếu hỗ trợ bảo vệ khi dữ liệu bị đọc. Nếu đối tượng đã có quyền tùy ý sửa bảng tài khoản, họ có thể tấn công nhiều cơ chế khác; không nên mô tả một cột hash là bảo vệ đầy đủ trước việc chiếm cơ sở dữ liệu.

## 3. Chọn cách lưu: điều gì được và không được bảo vệ?

Đối với dữ liệu chỉ cần đối chiếu, mục tiêu là lưu **verifier**: thông tin cho phép kiểm tra một ứng viên mà không cần giữ câu trả lời gốc.

| Cách lưu | Vấn đề chính | Đánh giá cho câu trả lời kế thừa |
| --- | --- | --- |
| Plaintext | Người đọc DB biết ngay câu trả lời | Không phù hợp |
| Base64 hoặc che bằng ký tự | Có thể đảo ngược dễ dàng | Không phải biện pháp bảo vệ bí mật |
| Mã hóa có thể giải mã | Người có khóa có thể lấy toàn bộ câu trả lời | Không cần thiết nếu nghiệp vụ chỉ đối chiếu |
| MD5, SHA-1 hoặc SHA-256 trực tiếp | Cho phép thử ứng viên rất nhanh | Không đủ cho bí mật dễ đoán |
| Hash nhanh kèm salt | Hạn chế bảng tính trước dùng chung, nhưng từng lần đoán vẫn rẻ | Không thay thế hàm băm dành cho mật khẩu |
| Hàm băm chậm với salt riêng | Tăng chi phí từng lần đoán và tách các bản ghi | Nền tảng lưu verifier của thiết kế tham khảo |
| Băm chậm kết hợp pepper ngoài DB | Thêm ranh giới khóa khi chỉ DB bị lộ | Có ích khi quản trị khóa và vận hành đúng |

Mã hóa ổ đĩa hoặc transparent data encryption vẫn có vai trò bảo vệ bản sao lưu và phương tiện lưu trữ. Tuy nhiên, người truy vấn DB bằng quyền hợp lệ vẫn có thể nhận được nội dung cột; lớp đó không thay thế verifier một chiều.

Không duy trì thêm một bản plaintext “để helpdesk đọc khi cần”. Nếu người dùng không nhớ, quy trình cần phương thức recovery khác được chấp nhận.

## 4. Mô hình dữ liệu có phiên bản

### 4.1. Bản ghi cho từng câu trả lời

Ví dụ schema theo phong cách PostgreSQL, dùng để minh họa cấu trúc:

~~~sql
CREATE TABLE legacy_security_answer (
    id                    UUID PRIMARY KEY,
    tenant_id             UUID NOT NULL,
    account_id            UUID NOT NULL,
    question_id           VARCHAR(80) NOT NULL,
    question_version      INTEGER NOT NULL,
    verifier_scheme       VARCHAR(80) NOT NULL,
    encoded_verifier      TEXT NOT NULL,
    normalization_version VARCHAR(80) NOT NULL,
    pepper_key_id         VARCHAR(120) NOT NULL,
    status                VARCHAR(20) NOT NULL,
    row_version           BIGINT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL,
    updated_at            TIMESTAMPTZ NOT NULL,
    revoked_at            TIMESTAMPTZ,
    UNIQUE (tenant_id, account_id, question_id)
);
~~~

Trong triển khai thực tế, thêm ràng buộc tham chiếu tới đúng tài khoản trong tenant và giới hạn giá trị của các trường trạng thái. Schema không tự triển khai phân quyền truy cập theo tenant.

**encoded_verifier** chứa định dạng đã biết của thuật toán, salt và các tham số cần để đối chiếu. Ví dụ với định dạng PHC của Argon2, chuỗi thường mang tên thuật toán, phiên bản, tham số, salt và kết quả băm. Không cần lưu thêm một cột salt khác nếu thư viện đã mã hóa nó đầy đủ.

**pepper_key_id** chỉ là mã tham chiếu tới khóa; giá trị khóa không nằm trong bảng.

**verifier_scheme** mô tả toàn bộ pipeline, chẳng hạn HMAC-SHA-256 rồi Argon2id, không chỉ tên hàm cuối. Nhờ đó, bản ghi cũ có thể được đọc bằng đúng bộ xác minh tương ứng.

**row_version** giúp phát hiện thay đổi đồng thời. Không cho một tiến trình xác minh chạy chậm ghi đè lên câu trả lời vừa được người dùng thay hoặc thu hồi.

### 4.2. Lưu câu hỏi và lưu câu trả lời là hai việc khác nhau

Câu hỏi chọn từ danh mục có thể lưu bằng ID và phiên bản. Bản dịch giao diện không được âm thầm đổi ý nghĩa câu hỏi mà giữ nguyên version.

Nếu hệ thống cũ cho người dùng viết câu hỏi riêng, nội dung câu hỏi cũng có thể chứa dữ liệu nhạy cảm hoặc chính câu trả lời. Cần giới hạn truy cập và bảo vệ nội dung hiển thị, thay vì coi câu hỏi luôn là dữ liệu công khai.

Không lưu các dữ liệu phụ tạo đường đoán dễ hơn:

- Câu trả lời gốc hoặc bản đã chuẩn hóa.
- Bản băm nhanh không có pepper để phục vụ tìm kiếm.
- Ký tự đầu, ký tự cuối hoặc “gợi ý” trích từ câu trả lời.
- Độ dài câu trả lời chính xác nếu không có nhu cầu vận hành rõ ràng.
- Bản sao câu trả lời trong lịch sử thay đổi hoặc event payload.

Nếu muốn phát hiện đáp án giống nhau trong cùng một lần cập nhật, có thể xử lý tạm trong bộ nhớ và hủy sau thao tác. Không tạo fingerprint dùng chung toàn hệ thống chỉ để tìm người có cùng đáp án.

## 5. Chuẩn hóa câu trả lời tiếng Việt

### 5.1. Vì sao cần quy tắc ổn định?

Hai chuỗi nhìn giống nhau có thể có biểu diễn Unicode khác nhau. Chữ có dấu có thể là một code point dựng sẵn hoặc một chuỗi ký tự cơ sở kết hợp dấu. Nếu băm trực tiếp các byte khác nhau, kết quả sẽ khác.

Unicode mô tả NFC là một dạng chuẩn hóa dựa trên tương đương canonical; NFKC còn xử lý tương đương compatibility và có thể gộp thêm các dạng ký tự. Việc chọn dạng chuẩn hóa phải gắn với chính sách so sánh của ứng dụng. [Unicode Standard Annex #15, Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)

Thiết kế tham khảo chọn **NFC** và giữ nguyên dấu tiếng Việt. Không tự bỏ dấu để biến “Hòa” thành “Hoa”, vì chúng có thể là hai câu trả lời mà người dùng muốn phân biệt.

### 5.2. Một chính sách minh họa có phiên bản

Chính sách **vi-answer-v1** được định nghĩa:

1. Từ chối đầu vào null, Unicode không hợp lệ hoặc vượt giới hạn đầu vào.
2. Chuẩn hóa NFC.
3. Loại bỏ duy nhất khoảng trắng ASCII U+0020 ở hai đầu.
4. Chuyển chữ thường bằng Locale.ROOT.
5. Chuẩn hóa NFC lần nữa.
6. Kiểm tra chuỗi không rỗng và còn nằm trong giới hạn sau biến đổi.
7. Mã hóa UTF-8 theo cách không âm thầm thay thế ký tự lỗi.

Chính sách này giữ nguyên khoảng trắng bên trong, dấu câu, dấu tiếng Việt và ký tự số 0 ở đầu. Nó không phải Unicode case folding đầy đủ, không tự sửa chính tả và không gộp các chữ chỉ nhìn giống nhau.

Các giới hạn minh họa có thể là 256 code point và 1.024 byte UTF-8, được kiểm tra cả trước và sau biến đổi. Đây là quyết định sản phẩm, không phải ngưỡng entropy hoặc chuẩn bắt buộc. Đầu vào vượt giới hạn phải bị từ chối, không bị cắt ngầm.

| Cặp đầu vào | Kết quả theo vi-answer-v1 | Lý do |
| --- | --- | --- |
| “  Đà Nẵng  ” và “đà nẵng” | Khớp | Bỏ U+0020 ở rìa và chuyển chữ thường |
| “Hòa” và “Hoa” | Không khớp | Giữ dấu |
| “Hà  Nội” và “Hà Nội” | Không khớp | Không gộp khoảng trắng bên trong |
| Cùng chữ có dấu ở dạng dựng sẵn và dạng phân rã canonical | Khớp sau NFC | Quy tắc chuẩn hóa đã định nghĩa |
| “01” và “1” | Không khớp | Không phân tích câu trả lời như số |
| Khoảng trắng không ngắt dòng và U+0020 | Không tự đồng nhất | Không xóa hoặc đổi mọi loại khoảng trắng |

Giao diện cần mô tả quy tắc dễ hiểu và nhất quán. Nếu muốn bỏ thêm loại khoảng trắng hoặc đổi cách so sánh, tạo policy version mới; không thay hành vi của vi-answer-v1 sau khi đã có dữ liệu.

### 5.3. Không dùng DB collation để xác minh bí mật

Collation có thể bỏ qua hoa thường, dấu hoặc một số khác biệt ký tự theo cấu hình cơ sở dữ liệu. Việc đối chiếu bí mật phải dùng pipeline xác minh phía ứng dụng, dựa trên phiên bản chuẩn hóa của bản ghi.

Không truy vấn bằng điều kiện tương tự “answer = giá trị người dùng nhập”, dù cột đó đã được che hoặc mã hóa.

Tính tương thích còn phụ thuộc runtime và dữ liệu Unicode mà thư viện hỗ trợ. Cần lưu hợp đồng của chính sách, duy trì các ví dụ tương thích và đánh giá khi nâng runtime; chỉ đặt một nhãn version mà thay toàn bộ thuật toán bên dưới vẫn gây lỗi.

## 6. Pipeline tạo verifier

### 6.1. Tách vai trò salt và pepper

- **Salt:** giá trị ngẫu nhiên riêng cho mỗi lần tạo verifier; không cần bí mật; được lưu cùng kết quả.
- **Pepper:** khóa bí mật được giữ ngoài cơ sở dữ liệu chứa verifier; thường được dùng cho nhiều bản ghi thuộc cùng phạm vi quản trị khóa.
- **Hàm băm chậm:** tăng chi phí tính mỗi ứng viên, kể cả khi kẻ tấn công biết salt.
- **Giới hạn thử:** kiểm soát số ứng viên mà hệ thống chấp nhận kiểm tra trực tuyến.

OWASP hiện khuyến nghị Argon2id cho lưu trữ mật khẩu, với một cấu hình tối thiểu là 19 MiB, t = 2, p = 1. Bài học dùng cùng loại primitive để bảo vệ câu trả lời kế thừa; đây không phải bằng chứng security questions đạt mức đảm bảo của mật khẩu mạnh. [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

Một cấu hình minh họa của bài học là Argon2id với 64 MiB, t = 3, p = 1, salt ngẫu nhiên 16 byte và output 32 byte. Cần đo trên hạ tầng thật và chọn cấu hình được tổ chức phê chuẩn. Trong tham số Argon2, m thể hiện tổng bộ nhớ; tăng p không có nghĩa bộ nhớ được nhân thêm p lần. [RFC 9106, Argon2 Inputs and Outputs](https://www.rfc-editor.org/rfc/rfc9106.html#section-3.1)

### 6.2. Công thức tham khảo có pepper

~~~text
A = UTF8(normalize(answer, normalization_version))

C = encodeLengthPrefixed(
    domain_tag,
    tenant_id,
    account_id,
    answer_record_id,
    question_id,
    question_version,
    normalization_version,
    A
)

P = HMAC-SHA-256(K_pepper, C)

V = Argon2id(
    input = P,
    salt = fresh_random_salt,
    parameters = approved_parameters
)
~~~

Lưu encoded verifier của V, scheme, normalization version và mã tham chiếu khóa. Không lưu A, C chứa câu trả lời, P hoặc K_pepper.

**domain_tag** phân biệt mục đích sử dụng, chẳng hạn legacy-security-answer/hmac-argon2id/v1. ID tài khoản, tenant và bản ghi là các định danh ổn định, không dùng username có thể đổi.

**encodeLengthPrefixed** là mã hóa nhị phân có độ dài từng trường và quy tắc cụ thể. Không chỉ nối chuỗi, vì các cặp “ab, c” và “a, bc” có thể tạo cùng dữ liệu nối. Không dùng serialization tùy tiện có thể thay đổi sau nâng thư viện.

Ràng buộc ngữ cảnh giúp tránh việc một verifier hợp lệ bị sao chép nguyên sang tài khoản hoặc câu hỏi khác và vẫn xác minh được. Nó không thay thế bảo vệ tính toàn vẹn của cơ sở dữ liệu.

HMAC tạo ranh giới phụ thuộc khóa bí mật; Argon2id tạo chi phí tính toán. Khi cả pepper lẫn verifier đã bị lộ, đáp án ít khả năng vẫn có thể bị đoán. Không diễn giải đầu ra HMAC 256 bit thành việc câu trả lời có 256 bit entropy.

### 6.3. Vì sao không chỉ dùng HMAC hoặc chỉ dùng salt?

HMAC đơn lẻ có thể bảo vệ tốt trước một số tình huống chỉ DB bị lộ, nhưng khi khóa lộ thì mỗi lần đoán rất rẻ. Băm chậm bổ sung chi phí trong tình huống đó.

Salt riêng giúp các bản ghi không chia sẻ trực tiếp cùng kết quả và giảm lợi ích của tính toán trước. Salt không phải bí mật và không cản đối tượng tính lại một ứng viên cho một bản ghi đã chọn.

Pepper cũng không giúp nếu ứng dụng có endpoint không giới hạn cho phép thử mọi ứng viên, hoặc đối tượng đã chiếm được tiến trình có quyền gọi dịch vụ khóa. Quyền sử dụng khóa phải được giới hạn cùng với luồng xác minh.

Không lưu thêm SHA-256 của câu trả lời để “tối ưu tìm kiếm trước khi chạy Argon2”. Cột phụ đó có thể trở thành oracle ngoại tuyến rẻ hơn và làm mất tác dụng của pipeline chính.

## 7. Luồng ghi và đối chiếu

### 7.1. Khi ghi hoặc thay dữ liệu kế thừa

~~~mermaid
flowchart TD
    A[Quy trình bảo trì được cho phép] --> B[Xác thực lại hoặc recovery mạnh đã hoàn tất]
    B --> C[Kiểm tra quyền và phiên bản bản ghi]
    C --> D[Kiểm tra đầu vào và chuẩn hóa theo policy]
    D --> E[HMAC bằng pepper ngoài DB]
    E --> F[Argon2id với salt mới]
    F --> G[Cập nhật có điều kiện và ghi audit]
    G --> H[Vô hiệu hóa challenge liên quan và thông báo thay đổi]
~~~

Việc đặt lại câu trả lời là một thay đổi cấu hình nhạy cảm. Người chỉ đoán đúng một câu hỏi không được tự thay toàn bộ bộ câu hỏi hoặc phương thức recovery.

Trong giai đoạn loại bỏ security questions, tổ chức có thể chỉ cho phép xóa hoặc vô hiệu hóa, không cho đăng ký thêm. Pipeline ghi vẫn có ích để hiểu nâng cấp dữ liệu được phép tồn tại trong khoảng chuyển tiếp.

Salt mới được sinh mỗi lần tạo verifier, bao gồm khi đổi câu trả lời hoặc nâng tham số. Hai lần ghi cùng câu trả lời không nên tạo cùng encoded verifier.

### 7.2. Khi đối chiếu

1. Xác định tài khoản và tenant từ ngữ cảnh recovery được máy chủ kiểm soát.
2. Áp dụng giới hạn số lần thử trước khi gọi HMAC và Argon2.
3. Đọc đúng bản ghi active và kiểm tra schema, scheme, key ID, giới hạn tham số.
4. Chuẩn hóa đầu vào bằng phiên bản của bản ghi.
5. Tính HMAC bằng đúng phiên bản pepper.
6. Dùng hàm verify của thư viện băm đã chọn.
7. Trước khi ghi nhận kết quả, kiểm tra bản ghi chưa bị thay hoặc thu hồi.
8. Ghi một quan sát có thời hạn vào đúng recovery request; không cấp quyền reset chỉ từ kết quả này.
9. Dọn vùng nhớ tạm trong phạm vi có thể và không ghi đầu vào vào log.

Không tin account ID hoặc question ID do client gửi mà thiếu đối chiếu với challenge phía máy chủ. Một challenge nên ràng buộc tài khoản, tenant, tập câu hỏi, phiên bản bản ghi, mục đích và thời hạn.

Nếu không có bản ghi, không tiết lộ điều đó qua response chi tiết. Có thể dùng đường xử lý giả với verifier giả hợp lệ để giảm khác biệt thời gian rõ rệt, nhưng vẫn phải giới hạn tải. Không thể cam kết thời gian tổng thể tuyệt đối giống nhau trên mọi tình huống mạng.

## 8. Phác thảo Java cho lớp lưu trữ

Các đoạn sau là mã giả có kiểu Java. Interface dịch vụ khóa, băm và repository biểu diễn hợp đồng cần triển khai bằng thư viện đã được đánh giá; không tự viết lại Argon2.

### 8.1. Chuẩn hóa có phiên bản

~~~java
byte[] canonicalAnswerUtf8(SecretInput input, String version) {
    if (!version.equals("vi-answer-v1")) {
        throw new UnsupportedNormalizationVersion();
    }

    String raw = input.readForNormalization();
    inputRules.requireValidUnicodeAndBoundedSize(raw);

    String nfc = Normalizer.normalize(raw, Normalizer.Form.NFC);
    String stripped = stripAsciiSpacesAtEdges(nfc);
    String lower = stripped.toLowerCase(Locale.ROOT);
    String canonical = Normalizer.normalize(lower, Normalizer.Form.NFC);

    inputRules.requireNonEmptyAndBoundedSize(canonical);
    return strictUtf8Encode(canonical);
}

String stripAsciiSpacesAtEdges(String value) {
    int start = 0;
    int end = value.length();

    while (start < end && value.charAt(start) == ' ') {
        start++;
    }
    while (end > start && value.charAt(end - 1) == ' ') {
        end--;
    }
    return value.substring(start, end);
}
~~~

Không thay stripAsciiSpacesAtEdges bằng một hàm trim có tập ký tự khác rồi giữ nguyên nhãn policy. Hàm strictUtf8Encode phải báo lỗi với dữ liệu không thể mã hóa hợp lệ; các bước kiểm tra cũng cần xử lý surrogate không hợp lệ.

Ví dụ dùng String để dễ đọc, nhưng String bất biến không thể được xóa bộ nhớ một cách chắc chắn. Dọn byte array giúp giảm một phần thời gian lưu dữ liệu; nó không chứng minh mọi bản sao đã biến mất khỏi JVM. Cần quản lý heap dump, crash dump, profiler và thời gian sống của request.

### 8.2. Tạo bản ghi verifier

~~~java
PreparedAnswer prepareVerifier(
        AuthorizedLegacyMaintenance operation,
        AnswerContext context,
        SecretInput input) {

    operation.requireCanMaintain(context.tenantId(), context.accountId());

    String normalizationVersion = "vi-answer-v1";
    String scheme = "hmac-sha256-argon2id-v1";
    String pepperKeyId = keyPolicy.currentAnswerPepperId();

    byte[] canonical = null;
    byte[] framedInput = null;
    byte[] prehash = null;

    try {
        canonical = canonicalAnswerUtf8(input, normalizationVersion);
        framedInput = framing.encodeAnswerContext(
            scheme, context, normalizationVersion, canonical);

        prehash = pepperService.hmacSha256(pepperKeyId, framedInput);

        // Thư viện tạo salt mới bằng nguồn ngẫu nhiên mật mã.
        String encoded = argon2.hashWithFreshSalt(
            prehash, approvedArgon2Parameters());

        return new PreparedAnswer(
            context, scheme, normalizationVersion, pepperKeyId, encoded);
    } finally {
        zeroIfPresent(canonical);
        zeroIfPresent(framedInput);
        zeroIfPresent(prehash);
        input.close();
    }
}
~~~

Sau bước chuẩn bị, repository thực hiện cập nhật có điều kiện theo row_version và quyền vẫn còn hiệu lực; audit được ghi bền vững cùng thay đổi. Nếu version đã đổi, không ghi đè mà yêu cầu xử lý lại từ trạng thái mới.

**AnswerContext** bao gồm các ID và question version dùng trong công thức. Không lấy domain tag, key ID hoặc tham số băm tùy ý từ client. **PreparedAnswer** không được chứa plaintext hoặc giá trị HMAC trung gian.

### 8.3. Đối chiếu và trả kết quả bị giới hạn

~~~java
LegacyObservation checkLegacyAnswer(
        RecoveryContext recovery,
        UUID answerId,
        SecretInput input) {

    AttemptReservation attempt = null;
    byte[] canonical = null;
    byte[] framedInput = null;
    byte[] prehash = null;

    try {
        attempt = attempts.reserveBoundedAttempt(recovery);
        AnswerVerifier row = answers.requireBoundSnapshot(recovery, answerId);
        verifierPolicy.requireSupportedAndBounded(row);
        keyPolicy.requireAllowedAnswerPepper(row.pepperKeyId());

        canonical = canonicalAnswerUtf8(input, row.normalizationVersion());
        framedInput = framing.encodeAnswerContext(
            row.verifierScheme(), row.context(),
            row.normalizationVersion(), canonical);

        prehash = pepperService.hmacSha256(row.pepperKeyId(), framedInput);
        boolean matches = argon2.verify(row.encodedVerifier(), prehash);

        // Transaction ngắn: kiểm tra challenge, row version, rồi lưu quan sát.
        return observations.recordIfStillCurrent(
            recovery, row.id(), row.rowVersion(), attempt,
            matches ? LEGACY_ANSWER_MATCH : LEGACY_ANSWER_NO_MATCH);
    } finally {
        zeroIfPresent(canonical);
        zeroIfPresent(framedInput);
        zeroIfPresent(prehash);
        input.close();
        if (attempt != null) {
            attempts.finishWithoutReleasingConsumedBudget(attempt);
        }
    }
}
~~~

Ví dụ minh họa đường xử lý bản ghi hợp lệ. Lớp bao ngoài xử lý bản ghi không tồn tại mà không lộ trạng thái; các thao tác kết thúc lượt thử phải chịu được lỗi lặp và không che mất lỗi gốc. Timeout được ghi nhận theo chính sách giới hạn thử.

**reserveBoundedAttempt** là thao tác nguyên tử trên kho dùng chung, ngăn nhiều instance cùng vượt ngân sách thử. Không hoàn lại lượt chỉ vì request bị hủy hoặc timeout sau khi đã bắt đầu tính; nếu không, đối tượng có thể lợi dụng việc ngắt kết nối.

**recordIfStillCurrent** phải kiểm tra lại trạng thái challenge, thời hạn, tài khoản, tenant và version bản ghi trước khi ghi nhận quan sát. Kết quả khớp không được trả thành “đã xác minh chủ tài khoản” hoặc được dùng để vượt các điều kiện recovery còn thiếu.

Nếu dùng nhiều câu hỏi, response bên ngoài không chỉ ra câu nào đúng. Các bước xử lý cần tránh tạo khác biệt rõ rệt do dừng ngay ở câu sai đầu tiên; đồng thời giới hạn tổng tài nguyên cho cả tập câu hỏi.

Không dùng phép so sánh String tự viết để đối chiếu hash. Dùng verifier của thư viện với cơ chế so sánh phù hợp; điều đó không làm toàn bộ endpoint tự động trở thành constant-time.

## 9. Quản trị pepper và tình huống lỗi khóa

### 9.1. Khóa được giữ ở đâu?

Pepper cần được quản trị bằng secret manager, KMS hoặc HSM phù hợp. Nếu dịch vụ hỗ trợ HMAC không xuất khóa, ứng dụng chỉ được phép gọi đúng mục đích xác minh; nếu khóa phải được nạp vào tiến trình, cần chấp nhận và quản lý rủi ro của bộ nhớ tiến trình.

Không đặt pepper trong:

- Cột hoặc bảng khác cùng bộ backup với verifier.
- Source code, image container hoặc tệp cấu hình được chia sẻ rộng.
- Log khởi động, biến debug hoặc phản hồi chẩn đoán.
- Môi trường phát triển và production dùng chung một giá trị khóa.

Key ID do dữ liệu tham chiếu phải được kiểm tra theo danh sách khóa đúng mục đích. Không cho một bản ghi chỉ tới khóa ký token hoặc khóa của tenant khác tùy ý.

Nếu HMAC chạy ở một dịch vụ riêng, quyền truy cập API là một ranh giới quan trọng. Dịch vụ đó không nên trở thành oracle HMAC tổng quát mà mọi microservice đều gọi được. Theo dõi tải, phân quyền workload và giới hạn phạm vi sử dụng khóa.

### 9.2. Khi dịch vụ khóa không sẵn sàng

Không thử bỏ pepper, không chuyển sang SHA-256 và không chấp nhận câu trả lời vì “KMS đang lỗi”. Kết quả phù hợp là chưa thể thực hiện phép đối chiếu.

Người dùng có thể được hướng dẫn sang phương thức recovery khác đã được phê chuẩn. Lỗi hạ tầng không tự làm giảm yêu cầu bằng chứng.

Các chỉ số vận hành nên phân biệt trả lời không khớp với lỗi kỹ thuật ở bên trong, trong khi thông điệp bên ngoài không tiết lộ chi tiết giúp dò trạng thái. Giới hạn việc retry để một sự cố KMS không gây bão request.

### 9.3. Xoay khóa có kế hoạch và xoay khóa do lộ khóa

Trong pipeline HMAC trước Argon2id của bài học, không thể thay pepper của verifier hiện có chỉ bằng việc sửa key ID. Cần đầu vào câu trả lời để tạo lại verifier dưới khóa mới.

Một quy trình xoay có kế hoạch:

1. Tạo khóa mới cho lần ghi mới.
2. Giữ khóa cũ ở chế độ chỉ xác minh trong thời gian chuyển tiếp được duyệt.
3. Khi người dùng hoàn thành bước xác thực mạnh độc lập và cung cấp lại câu trả lời, tạo verifier mới nếu chính sách còn cho phép giữ dữ liệu này.
4. Đánh dấu những bản ghi chưa chuyển đổi để xử lý trước hạn.
5. Chỉ ngừng khóa cũ khi không còn bản ghi được phép xác minh phụ thuộc vào nó.

Khi pepper bị lộ, không chỉ thay khóa rồi tiếp tục tin mọi câu trả lời cũ. Cần đánh giá việc DB hoặc backup đã bị lộ cùng khóa chưa, vô hiệu hóa cơ chế bị ảnh hưởng và yêu cầu khôi phục qua bằng chứng độc lập phù hợp. Câu trả lời dựa trên thông tin đời tư thường không thể được làm bí mật trở lại.

Xoay khóa dùng để bọc một secret trong kho khóa có thể không cần câu trả lời người dùng; đó là thay đổi lớp bảo vệ khóa, khác với đổi giá trị pepper tham gia HMAC.

## 10. Chống dò đoán và giới hạn tài nguyên

Lưu trữ mạnh không chặn dò đoán qua API. Endpoint xác minh cần ngân sách thử gắn với tài khoản và luồng recovery, không chỉ một cookie hoặc một IP.

Các nguyên tắc triển khai tham khảo:

- Bộ đếm dùng chung giữa các instance và cập nhật nguyên tử.
- Đóng tab, tạo request mới hoặc chọn câu hỏi khác không tự xóa lịch sử thử của tài khoản.
- Có giới hạn ngắn hạn và dài hạn, kèm cơ chế xử lý khi bị tấn công.
- Không trả một response riêng cho từng câu đúng hoặc sai trong bộ câu hỏi.
- Không cho lặp vô hạn việc chọn câu dễ nhất trong các câu đã đăng ký.
- Giới hạn số tác vụ HMAC và băm chậm đang chạy đồng thời.
- Đặt hạn mức hàng đợi; quá tải trả trạng thái cần thử lại, không chuyển sang phép kiểm tra yếu hơn.

Với cấu hình 64 MiB mỗi tác vụ, 100 tác vụ chạy đồng thời cần khoảng 6.400 MiB chỉ cho vùng nhớ Argon2, chưa kể JVM và phần còn lại. Đây là phép ước lượng tài nguyên để thiết kế admission control, không phải benchmark hiệu năng.

Nếu một yêu cầu cần đối chiếu nhiều câu, chạy tất cả song song có thể nhân mức tiêu thụ tức thời. Cần giới hạn riêng số câu và cách lập lịch, thay vì chỉ cấu hình số luồng HTTP.

Bản ghi verifier cũng là dữ liệu cần kiểm tra. Không cho một chuỗi PHC bị sửa tự yêu cầu lượng RAM hoặc số vòng lặp vô hạn. Chỉ chấp nhận scheme, phiên bản và miền tham số đã được cấu hình để đọc; các bản ghi không hợp lệ chuyển xử lý an toàn.

Không áp dụng khóa toàn bộ tài khoản vô thời hạn chỉ vì người lạ gửi sai câu trả lời. Có thể hạn chế nhánh recovery bị lạm dụng mà vẫn bảo vệ khả năng đăng nhập hợp lệ.

## 11. Nâng cấp dữ liệu kế thừa

### 11.1. Các trường hợp nguồn khác nhau

| Dữ liệu đang tồn tại | Hướng xử lý tham khảo |
| --- | --- |
| Plaintext | Ưu tiên vô hiệu hóa hoặc chuyển đổi trong môi trường kiểm soát; xóa mọi bản sao phụ |
| Mã hóa có thể giải mã | Nếu được phép chuyển đổi, giải mã trong luồng hạn chế rồi tạo verifier; tránh xuất thành tệp trung gian |
| Hash nhanh | Không thể lấy lại câu trả lời từ hash bằng phép “giải mã”; cần đầu vào mới hoặc vô hiệu hóa |
| Băm chậm nhưng thiếu version | Xác định đúng định dạng từ hợp đồng cũ trước khi đọc; không thử nhiều thuật toán tùy tiện |
| Băm chậm với tham số cũ | Tạo verifier mới từ đầu vào hợp lệ khi có điều kiện bảo trì được cho phép |
| Verifier theo chuẩn hóa cũ | Xác minh bằng policy cũ; thay policy cần đầu vào mới và thao tác chuyển đổi rõ ràng |

Không xây dựng migration bằng cách in câu trả lời ra console, đưa vào CSV hoặc chuyển qua ticket. Một lần chuyển đổi kỹ thuật thành công cũng không xóa dữ liệu đã từng xuất hiện trong log và backup.

### 11.2. Tránh nhầm rehash với bọc hash cũ

Giả sử bản ghi cũ chứa SHA-256 của câu trả lời. Đưa chuỗi hash đó qua Argon2 có thể tạo một định dạng chuyển tiếp, nhưng kết quả không giống Argon2 của câu trả lời gốc. Muốn dùng cách bọc, phải ghi scheme riêng và còn phải xem xét rủi ro bản hash cũ đã lộ.

Thiết kế tham khảo ưu tiên tạo verifier trực tiếp từ đầu vào mới trong ngữ cảnh đã được cho phép. Không trình bày việc bọc hash như cách tự động sửa mọi điểm yếu của dữ liệu cũ.

Nếu chỉ đổi normalization_version trong DB mà không tạo lại verifier bằng dữ liệu tương ứng, người dùng có thể bị từ chối dù nhập đúng câu trả lời ban đầu.

### 11.3. Đồng thời và tính nguyên tử

Một yêu cầu xác minh có thể bắt đầu bằng row_version = 7 trong khi người dùng vừa xóa câu hỏi và tạo version = 8. Kết quả tính toán của version 7 không được dùng để ghi quan sát hợp lệ cho version 8.

Cập nhật có điều kiện phải bao gồm tenant, account, bản ghi, version và trạng thái. Nếu không khớp, bỏ kết quả hoặc yêu cầu làm lại từ challenge mới; không tự chọn bản ghi hiện tại rồi ghi đè.

Thay bộ câu hỏi và vô hiệu hóa challenge liên quan cần gắn với một ranh giới nhất quán. Nếu các dịch vụ riêng biệt, có thể dùng cấu hình recovery có phiên bản và outbox để truyền sự kiện; bên sử dụng vẫn phải kiểm tra phiên bản tại thời điểm quyết định.

Migration storage không phải quyền phục hồi tài khoản. Việc người nhập một chuỗi tạo được hash cũ không tự cho phép họ nhận session hoặc đổi MFA.

## 12. Log, sao lưu và quyền riêng tư

### 12.1. Ngăn dữ liệu lọt ra ngoài bảng chính

Một hệ thống có cột Argon2id vẫn có thể giữ nguyên câu trả lời ở nơi khác:

| Kênh | Dữ liệu dễ lọt | Kiểm soát cần đưa vào thiết kế |
| --- | --- | --- |
| Request log | JSON chứa answer | Loại bỏ trường trước khi ghi; không chỉ che ở giao diện xem log |
| APM và tracing | Body hoặc biến cục bộ trong span | Không capture payload bí mật và không dùng làm tag |
| Exception | Nội dung input trong message | Thông báo lỗi không chứa câu trả lời |
| DTO và debugger | toString tự sinh | Dùng kiểu bí mật có biểu diễn đã che; giới hạn công cụ debug |
| Event bus và CDC | Bản sao raw hoặc verifier phát tán | Chỉ gửi ID, version và thông tin nghiệp vụ tối thiểu |
| Ticket hỗ trợ | Ảnh chụp, bản ghi cuộc gọi | Không yêu cầu đọc hoặc gửi câu trả lời |
| Dữ liệu kiểm thử | Bản dump production | Dùng dữ liệu tổng hợp, không dùng câu trả lời người thật |

Verifier cũng là dữ liệu nhạy cảm vì có thể bị dò đoán. Không đưa hash vào API quản trị chỉ vì nó “không phải plaintext”.

Các chức năng backup, replica, analytics và export cần được xét riêng. Pepper không nên đi cùng đường sao lưu DB. Quyền đọc bản sao lưu và quyền dùng khóa phải được phân tách theo mô hình vận hành thực tế.

### 12.2. Xóa dữ liệu và phục hồi backup

Thu hồi bản ghi cần khiến nó không còn được dùng để xác minh ngay trong luồng hiện hành. Sau đó xử lý xóa dữ liệu theo chính sách giữ phù hợp, bao gồm bản sao, cache và các hệ thống nhận dữ liệu.

Backup bất biến có thể còn chứa verifier trong thời gian giữ. Cần bảo vệ truy cập, ghi nhận lịch hết hạn và có cơ chế áp lại trạng thái xóa hoặc thu hồi khi phục hồi, tránh làm sống lại câu trả lời đã bị vô hiệu hóa.

Audit thường chỉ cần lưu ID, thời điểm, actor, version và loại thay đổi. Không cần giữ câu trả lời cũ để chứng minh đã có thao tác thay đổi.

## 13. Ví dụ xuyên suốt

Một ứng dụng cũ giữ câu hỏi cho người dùng Minh. Mục tiêu chuyển tiếp là bảo vệ dữ liệu đang có, đồng thời đưa người dùng sang phương thức recovery được chấp nhận.

1. Sau bước xác thực mạnh độc lập, Minh vào luồng bảo trì được cho phép.
2. Hệ thống chuẩn hóa đầu vào theo vi-answer-v1, giữ nguyên dấu.
3. Tạo HMAC trong ngữ cảnh tenant, tài khoản, question version và bản ghi.
4. Tạo Argon2id với salt mới; chỉ lưu encoded verifier và metadata cần thiết.
5. Khi có yêu cầu recovery, máy chủ tạo challenge có thời hạn và giữ ngân sách thử dùng chung.
6. Minh nhập cùng đáp án nhưng khác kiểu Unicode canonical; NFC cho phép tạo cùng giá trị chuẩn hóa.
7. Nếu verifier khớp và bản ghi chưa đổi, máy chủ ghi một quan sát giới hạn cho challenge đó.
8. Quy trình recovery vẫn yêu cầu bằng chứng độc lập theo chính sách trước khi cấp quyền thay authenticator.
9. Sau khi phương thức thay thế được thiết lập phù hợp, hệ thống vô hiệu hóa dữ liệu câu hỏi kế thừa và các challenge liên quan.

Nếu trong bước 7 pepper service lỗi, kết quả là chưa thể đối chiếu. Nếu Minh bỏ dấu làm chuỗi khác với dữ liệu đã đăng ký, hệ thống không tự thử thêm phiên bản bỏ dấu. Nếu cơ sở dữ liệu bị lấy cắp, nhóm ứng cứu đánh giá cả verifier, khóa, log và bản sao lưu; không kết luận “đã băm nên không có ảnh hưởng”.

## 14. Các điều kiện bất biến cần giữ

Một thiết kế lưu trữ có thể được mô tả bằng các điều kiện sau:

- Không có bản câu trả lời đọc được hoặc fingerprint rẻ hơn nằm cạnh verifier.
- Mỗi lần tạo verifier có salt ngẫu nhiên mới; pepper nằm ngoài DB và được quản trị theo phiên bản.
- Đối chiếu dùng đúng scheme, normalization version, ngữ cảnh và khóa của bản ghi.
- Câu trả lời sai, lỗi kỹ thuật và bản ghi stale đều không cấp quyền recovery.
- Bản ghi đã xóa hoặc thay không được xác minh bằng challenge cũ.
- Lượt đoán không được tái tạo bằng cách thay session, request hoặc instance.
- Việc thay, nâng cấp và thu hồi không sao chép bí mật vào log hoặc audit.
- Kết quả khớp câu trả lời không thay thế bằng chứng cần để reset mật khẩu, MFA hoặc passkey.

Bảo vệ storage làm giảm một nhóm rủi ro cụ thể. Mục tiêu dài hạn của luồng khôi phục tài khoản vẫn là sử dụng bằng chứng phù hợp và kiểm soát quyền, token cùng session trong toàn bộ quá trình.
