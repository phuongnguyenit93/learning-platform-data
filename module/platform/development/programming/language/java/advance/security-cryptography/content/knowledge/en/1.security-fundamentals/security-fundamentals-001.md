# 1.1 An toàn thông tin và mật mã giải quyết những vấn đề nào trong ứng dụng Java?

Ứng dụng Java thường lưu tài khoản, xử lý giao dịch, truyền dữ liệu qua mạng và gọi các dịch vụ khác. Một chương trình chạy đúng chức năng vẫn có thể gây thiệt hại nếu người không được phép đọc dữ liệu, sửa thông điệp, giả mạo người gửi hoặc sử dụng thông tin bị đánh cắp. **An toàn thông tin** là mục tiêu bảo vệ hệ thống và dữ liệu trước các rủi ro đó; **mật mã học** cung cấp những cơ chế kỹ thuật quan trọng để đạt một số mục tiêu bảo vệ.

Bài này trả lời ba câu hỏi: *Cần bảo vệ điều gì? Cơ chế mật mã giải quyết được vấn đề nào? Chọn và kết hợp cơ chế đó ra sao trong một ứng dụng Java?* Đây là bài nền tảng về bài toán và cách tư duy; phần cấu hình thuật toán, giao thức hoặc hệ thống quản lý khóa ở quy mô lớn cần được thiết kế riêng theo yêu cầu thực tế.

## 1. Xác định tài sản, đối thủ và ranh giới tin cậy

Giả sử một ứng dụng Java phục vụ thương mại điện tử:

1. Người dùng đăng nhập và gửi đơn hàng từ trình duyệt đến Java API.
2. Java API đọc thông tin khách hàng trong cơ sở dữ liệu.
3. API gọi cổng thanh toán, nhận webhook thông báo giao dịch.
4. Hệ thống ghi log, tạo bản sao lưu và gửi thông báo cho người dùng.

Những tài sản cần bảo vệ gồm mật khẩu hoặc bộ xác minh mật khẩu, token phiên, dữ liệu cá nhân, số tiền/đơn hàng, khóa mật mã, cấu hình bí mật, log và bản sao lưu. Các nguy cơ có thể đến từ người nghe trộm đường truyền, bên sửa gói tin, kẻ có tài khoản bị chiếm đoạt, lỗi phân quyền, nhân sự vận hành hoặc máy chủ bị xâm nhập.

**Ranh giới tin cậy** là nơi dữ liệu chuyển giữa những thành phần có mức độ kiểm soát khác nhau: trình duyệt → API, API → cơ sở dữ liệu, API → dịch vụ thanh toán, hệ thống đang chạy → kho sao lưu. Mỗi lần dữ liệu đi qua ranh giới, cần tự hỏi:

- Ai được phép đọc, tạo, sửa hoặc gửi dữ liệu này?
- Người nhận chứng minh danh tính người gửi bằng cách nào?
- Nếu thông điệp bị thay đổi trên đường đi, ai sẽ phát hiện?
- Khóa và bí mật nằm ở đâu; nếu bị lộ thì hậu quả là gì?
- Điều gì vẫn cần làm dù đã mã hóa, chẳng hạn kiểm soát quyền truy cập hoặc chống gửi lại yêu cầu?

Không có một thuật toán đơn lẻ nào trả lời được toàn bộ những câu hỏi này.

## 2. Những mục tiêu an toàn thông tin mà ứng dụng cần đạt

| Mục tiêu | Câu hỏi cần giải quyết | Ví dụ trong ứng dụng Java |
| --- | --- | --- |
| **Tính bí mật (confidentiality)** | Người không có quyền có đọc được nội dung không? | Che dữ liệu khách hàng khi truyền hoặc lưu; dùng TLS và mã hóa dữ liệu nhạy cảm ở nơi cần thiết. |
| **Tính toàn vẹn (integrity)** | Nội dung có bị sửa trái phép mà không bị phát hiện không? | Phát hiện số tiền trong thông điệp đã bị đổi; dùng mã xác thực thông điệp, chữ ký số hoặc chế độ mã hóa có xác thực. |
| **Tính xác thực (authenticity)** | Thông điệp hoặc bên giao tiếp có thật sự đến từ chủ thể được tin cậy không? | Xác thực máy chủ HTTPS, kiểm tra chữ ký webhook và gắn khóa xác minh với danh tính đúng. |
| **Xác thực người dùng (authentication)** | Ai đang yêu cầu hành động này? | Đăng nhập bằng phương thức phù hợp, kiểm tra phiên/token và xác thực thêm khi rủi ro cao. |
| **Phân quyền (authorization)** | Chủ thể đã xác thực được phép làm gì? | Người dùng A không được đọc đơn hàng của B; kiểm tra quyền tại server, theo từng tài nguyên và thao tác. |
| **Khả dụng (availability)** | Dịch vụ có tiếp tục phục vụ hợp lệ khi gặp lỗi hay tấn công không? | Giới hạn tốc độ, dự phòng, khôi phục sao lưu, theo dõi và ứng phó sự cố. |
| **Khả năng quy trách nhiệm / chống chối bỏ có điều kiện** | Có bằng chứng đáng tin về một hành động hoặc chữ ký không? | Chữ ký số cùng quy trình bảo vệ khóa, gắn danh tính và lưu bằng chứng phù hợp; chỉ có chữ ký chưa tự bảo đảm tính pháp lý. |

Ba mục tiêu kinh điển là **CIA: Confidentiality – Integrity – Availability**. Trong hệ thống thực tế còn cần xác thực, phân quyền, truy vết và kiểm soát vận hành.

Phân biệt đặc biệt quan trọng: **xác thực** trả lời “bạn là ai?”, còn **phân quyền** trả lời “bạn được làm gì?”. Một token hợp lệ không có nghĩa người sở hữu token được truy cập mọi bản ghi. Mật mã có thể hỗ trợ xác thực nhưng không thay thế kiểm tra quyền theo nghiệp vụ.

## 3. Các cơ chế mật mã giải những bài toán khác nhau

### 3.1. Mã hóa đối xứng: giữ bí mật nội dung

Một **khóa bí mật chung** được dùng để mã hóa và giải mã. Trong Java, một lựa chọn phổ biến cho dữ liệu ứng dụng là **AES-GCM**, vì nó vừa bảo mật nội dung vừa kiểm tra tính toàn vẹn của bản mã và dữ liệu bổ sung được xác thực (AAD).

Dùng khi cần bảo vệ một trường dữ liệu nhạy cảm lưu trữ, file sao lưu, hoặc thông điệp mà hai phía đã chia sẻ khóa an toàn. Bản mã vẫn cần khóa mới đọc được. Các yếu tố cần quản lý: sinh khóa đủ mạnh, lưu khóa tách biệt khỏi dữ liệu, nonce/IV **không trùng với cùng một khóa**, lưu IV kèm bản mã, kiểm tra thẻ xác thực trước khi sử dụng kết quả giải mã.

**Giới hạn:** mã hóa không quyết định người dùng nào được đọc bản ghi sau khi server giải mã. Lộ khóa có thể khiến dữ liệu tương ứng bị lộ; mã hóa không sửa được lỗi phân quyền.

### 3.2. Mật mã bất đối xứng: khóa công khai và khóa riêng

Một cặp khóa gồm **public key** có thể chia sẻ và **private key** phải bảo mật. Các thuật toán khác nhau phục vụ mục tiêu khác nhau: RSA-OAEP có thể mã hóa lượng dữ liệu phù hợp; Ed25519 được dùng cho **chữ ký số**, không dùng để mã hóa; ECDH/X25519 phục vụ thỏa thuận khóa, không tự xác thực danh tính đối tác.

Trong ứng dụng thực tế, dữ liệu lớn thường được mã hóa bằng khóa đối xứng; cơ chế bất đối xứng có thể hỗ trợ trao đổi hoặc bao bọc khóa, xác minh chữ ký hay thiết lập phiên giao tiếp an toàn. Không nên tự ghép các phép toán thành một giao thức truyền tin riêng khi đã có TLS và thư viện đã được kiểm chứng.

### 3.3. Hàm băm mật mã: tạo dấu vân tay của dữ liệu

Hàm như **SHA-256** biến dữ liệu bất kỳ thành một giá trị có độ dài cố định. Dữ liệu thay đổi thường làm giá trị băm thay đổi; đây là công cụ cho fingerprint, kiểm tra tính toàn vẹn khi **giá trị băm kỳ vọng đến từ nguồn đáng tin**, và làm thành phần của những cơ chế khác.

**SHA-256 không phải mã hóa:** không có thao tác “giải mã hash”. Tuy nhiên, băm trần của thông điệp **không chứng minh ai đã gửi**: người sửa dữ liệu cũng có thể tính lại hash. CRC32 hay checksum thông thường còn không phải công cụ bảo vệ chống sửa đổi có chủ đích.

### 3.4. MAC/HMAC: phát hiện sửa đổi và xác thực bên biết khóa

**HMAC-SHA256** dùng khóa bí mật chung để tạo mã xác thực thông điệp. Người nhận có khóa kiểm tra được nội dung và MAC có khớp hay không. Phù hợp khi hai hệ thống tin cậy cùng giữ bí mật, ví dụ một kiểu webhook được nhà cung cấp quy định dùng HMAC.

HMAC **không mã hóa nội dung**. Vì cả hai bên cùng biết khóa, HMAC không chứng minh riêng một bên đã ký trước bên thứ ba. Bản thân HMAC cũng không ngăn việc gửi lại một thông điệp cũ hợp lệ; cần thêm thời gian, nonce, ID giao dịch, hạn hiệu lực hoặc tính idempotent theo giao thức.

### 3.5. Chữ ký số: xác minh nguồn và nội dung

Người ký sử dụng private key để tạo chữ ký trên **đúng chuỗi byte**; người kiểm tra sử dụng public key tương ứng để xác minh. Nếu nội dung bị thay đổi, chữ ký cũ sẽ không còn hợp lệ. Ví dụ: xác minh gói phát hành, tài liệu hoặc webhook được ký.

**Điều kiện bắt buộc:** public key phải được gắn với đúng danh tính qua kênh tin cậy, chứng chỉ hoặc cấu hình đã xác minh. Chữ ký không làm dữ liệu bí mật, không tự chứng minh thời điểm ký và không tự tạo giá trị pháp lý nếu khóa riêng bị chia sẻ, đánh cắp hoặc quy trình quản trị thiếu tin cậy.

### 3.6. Băm mật khẩu chuyên dụng: lưu bộ xác minh, không lưu mật khẩu

Mật khẩu người dùng không nên lưu dưới dạng plaintext, mã hóa có thể giải mã, hoặc SHA-256 một lần. Khi đăng ký, hệ thống tạo **salt ngẫu nhiên riêng cho mỗi mật khẩu** và tính hàm dẫn xuất/băm mật khẩu có chi phí phù hợp như **Argon2id** (thường qua thư viện được duy trì) hoặc **PBKDF2WithHmacSHA256** trong JDK nếu cần phương án phù hợp hạ tầng. Lưu salt, tham số thuật toán và kết quả; khi đăng nhập tính và đối chiếu theo cơ chế của thư viện.

Salt không cần giữ bí mật; vai trò là tránh các mật khẩu giống nhau có cùng kết quả và gây khó cho tấn công tính trước. **Pepper** nếu sử dụng là bí mật bổ sung cần quản lý tách khỏi cơ sở dữ liệu. Tham số chi phí cần điều chỉnh, kiểm thử và cập nhật theo thời gian; không tự thiết kế thuật toán băm mật khẩu.

### 3.7. Ngẫu nhiên an toàn, chứng chỉ và TLS

- **SecureRandom** tạo khóa, nonce, token ngẫu nhiên hoặc salt cần độ khó dự đoán. **Random**, thời gian hệ thống và số thứ tự tăng dần không phù hợp để sinh bí mật bảo mật.
- **Chứng chỉ X.509/PKI** giúp gắn public key với một danh tính khi chuỗi tin cậy và tên máy chủ được kiểm tra đúng.
- **TLS/HTTPS** bảo vệ kết nối giữa các điểm cuối cụ thể: xác thực máy chủ và cung cấp bảo mật, toàn vẹn đường truyền. Trong Java, thường sử dụng stack HTTP/TLS chuẩn (JSSE, HttpClient, framework) thay vì tự tạo giao thức mật mã.

TLS chỉ bảo vệ **từng kết nối**. Dữ liệu đã giải mã trong ứng dụng, ghi vào log hoặc chuyển tiếp qua kết nối khác vẫn cần bảo vệ tương ứng. Không vô hiệu hóa kiểm tra chứng chỉ hoặc hostname chỉ để hết lỗi kết nối.

## 4. Bản đồ “bài toán → cơ chế → trách nhiệm còn lại”

| Tình huống | Cơ chế phù hợp | Việc vẫn phải kiểm tra |
| --- | --- | --- |
| Trình duyệt gọi Java API qua Internet | HTTPS/TLS đúng chứng chỉ và hostname | Xác thực phiên, phân quyền, kiểm tra dữ liệu đầu vào, CSRF khi phù hợp, xử lý lỗi an toàn |
| Lưu mật khẩu tài khoản | Argon2id/PBKDF2 với salt riêng và tham số chi phí | Chống dò mật khẩu, MFA khi cần, chính sách đặt lại và bảo vệ phiên |
| Lưu số định danh hoặc file nhạy cảm | AES-GCM hoặc cơ chế mã hóa được quản lý | Quản lý khóa, quyền truy cập sau giải mã, lưu bản sao lưu, hạn chế log lộ dữ liệu |
| Nhận webhook thanh toán | Kiểm tra chữ ký số hoặc HMAC **theo đặc tả nhà cung cấp** | Xác thực đúng raw payload/canonical form, thời hạn, replay, idempotency, trạng thái giao dịch |
| Kiểm tra gói phần mềm tải xuống | Hash đối chiếu từ nguồn xác thực hoặc chữ ký phát hành | Tin cậy nguồn cấp hash/public key, quy trình phát hành, chống rollback |
| Phát hành và kiểm tra access token | Token opaque hoặc token có chữ ký phù hợp kiến trúc | Kiểm tra issuer/audience/expiry/thuật toán/khóa, thu hồi khi cần, quyền ở endpoint |
| Ghi log sự kiện nhạy cảm | Log tối thiểu, phân quyền, bảo toàn log; có thể dùng chữ ký/chuỗi băm khi có yêu cầu | Bảo vệ nơi lưu, đồng bộ thời gian, chống xóa/sửa, chính sách giữ dữ liệu |
| Chống nghẽn dịch vụ, DDoS hoặc lỗi logic | Rate limit, quota, timeout, cache, dự phòng, giám sát | Mã hóa và chữ ký **không giải quyết** tính khả dụng một cách trực tiếp |

Một yêu cầu có thể cần nhiều cơ chế cùng lúc. Ví dụ webhook có HMAC hợp lệ vẫn có thể là thông điệp cũ bị phát lại, hoặc yêu cầu xử lý nghiệp vụ đã hoàn tất. HMAC kiểm tra thông điệp, còn cơ chế nghiệp vụ phải kiểm tra trạng thái và xử lý lặp.

## 5. Hai câu hỏi bảo mật trên cùng một đơn hàng

Giả sử ứng dụng Java nhận lệnh thanh toán `order=42;amount=250000` và lưu thông tin giao dịch cho dịch vụ khác đọc. **Cùng một dữ liệu** nhưng có những câu hỏi khác nhau:

- **Người đọc trộm backup có biết số tiền không?** Đây là mục tiêu bí mật ở nơi lưu trữ. Có thể dùng mã hóa xác thực như AES-GCM với khóa tách khỏi backup; không lưu khóa cạnh bản mã dưới cùng quyền đọc.
- **Người nhận webhook có biết thông điệp bị sửa hoặc bên gửi có quyền xác thực không?** Đây là mục tiêu toàn vẹn và xác thực thông điệp. Nếu giao thức quy định một secret chung, HMAC-SHA256 phù hợp; nếu cần bên thứ ba độc lập xác minh, dùng chữ ký số với public key đã được ràng buộc vào người ký.
- **Một webhook có tag hoặc chữ ký đúng có được ghi nhận nhiều lần không?** Không. Giao thức/nghiệp vụ vẫn phải kiểm tra sự kiện đã xử lý, thời hạn/nonce và tính idempotent.
- **Người dùng đã đăng nhập có thể đọc đơn hàng bất kỳ không?** Không. Đây là bài toán phân quyền đối tượng; AES-GCM, HMAC, chữ ký và TLS không thể quyết định một mình.

Phải nêu được **đối thủ nào bị chặn**, **khóa nào do ai giữ** và **kiểm tra diễn ra ở đâu**. Một giải pháp bảo vệ tốt backup vẫn có thể thất bại nếu API giải mã rồi trả bản rõ cho người dùng khác; một webhook HMAC hợp lệ vẫn có thể là sự kiện cũ bị phát lại.

## 6. Phép thử chứng minh cơ chế đã giải đúng vấn đề

| Mục tiêu | Phép thử phù hợp | Điều không thể suy ra chỉ từ kết quả đó |
| --- | --- | --- |
| Bí mật dữ liệu lưu trữ | Đọc backup bằng tài khoản không có khóa giải mã phải không lấy được bản rõ | Người chạy API hợp lệ không thể lộ plaintext trong log/response |
| Phát hiện sửa đổi | Sửa ciphertext/tag/AAD thì giải mã AEAD phải từ chối | Client đã được phân quyền trên đúng bản ghi |
| Xác thực webhook | Sửa bytes payload nhưng giữ MAC/chữ ký cũ thì verification phải thất bại | Thông điệp chưa từng được xử lý trước đó |
| Phân quyền dữ liệu | User A đổi ID sang record của B phải bị từ chối ở backend | Các byte lưu trong DB đã được mã hóa |

Ở đây chỉ cần **định hướng lựa chọn và đánh giá**. Ví dụ Java triển khai từng primitive, cách so sánh hash/MAC/chữ ký và định dạng byte được trình bày riêng ở bài phân biệt các cơ chế; còn bài này giữ trọng tâm là **vấn đề an toàn nào buộc ứng dụng phải kết hợp cơ chế và quyền truy cập**.

## 7. Chọn đúng primitive trong Java và đặt vào đúng lớp bảo vệ

| Nhu cầu | API/cơ chế thường gặp | Điều cần nhớ |
| --- | --- | --- |
| Sinh giá trị khó đoán | **java.security.SecureRandom** | Dùng cho bí mật, IV/nonce/salt theo yêu cầu từng thuật toán. |
| Băm nội dung | **MessageDigest** với SHA-256 | Hash trần không chứng minh người gửi và không dùng làm password hash. |
| Xác thực thông điệp bằng khóa chung | **javax.crypto.Mac** với HmacSHA256 | So khớp MAC theo cách an toàn; gắn timestamp/nonce nếu cần chống replay. |
| Mã hóa dữ liệu | **javax.crypto.Cipher**, **KeyGenerator**, **GCMParameterSpec** | Dùng AEAD và quản lý khóa/IV/tag đúng cách. |
| Ký/xác minh | **java.security.Signature**, **KeyPairGenerator** | Kiểm tra nguồn public key; private key chỉ nằm ở bên ký. |
| Dẫn xuất khóa từ mật khẩu | **SecretKeyFactory** với PBKDF2WithHmacSHA256 hoặc thư viện Argon2id | Phân biệt password verifier với khóa mã hóa; chọn tham số theo threat model. |
| Lưu/đọc khóa theo thiết kế | **KeyStore** hoặc KMS/HSM của nền tảng | KeyStore là giao diện lưu khóa; chính sách truy cập, backup và rotation vẫn phải thiết kế. |
| Kết nối có TLS | **java.net.http.HttpClient**, JSSE, HTTPS của framework | Dùng kiểm tra chứng chỉ/hostname mặc định; bảo vệ từng chặng kết nối. |

Bảng trên là **bản đồ trách nhiệm**, không có nghĩa chỉ cần gọi một API là hệ thống an toàn. Kết quả bảo vệ còn phụ thuộc nguồn khóa, dữ liệu đầu vào, cách kiểm tra lỗi và ranh giới tin cậy của toàn hệ thống.

## 8. Ví dụ thiết kế ứng dụng: luồng đăng nhập và thanh toán

### Đăng ký và đăng nhập

1. Trình duyệt gửi thông tin qua HTTPS đến Java API.
2. Khi đăng ký, server sử dụng hàm băm mật khẩu chuyên dụng với salt riêng và tham số chi phí đã chọn; không lưu mật khẩu plaintext.
3. Khi đăng nhập, server xác minh mật khẩu dựa trên bản ghi đã lưu, áp dụng giới hạn thử sai và biện pháp chống chiếm đoạt tài khoản theo mức độ rủi ro.
4. Nếu hợp lệ, server cấp phiên/token với thời hạn, phạm vi, cách lưu và cơ chế thu hồi rõ ràng. Không log token hoặc password.
5. Mọi API đọc/sửa đơn hàng vẫn kiểm tra quyền sở hữu tài nguyên; không tin mỗi việc “đã đăng nhập”.

### Tạo đơn và nhận thông báo thanh toán

1. API xác thực người yêu cầu, kiểm tra số tiền và quyền thao tác theo nghiệp vụ.
2. API gọi đối tác thanh toán qua TLS, xử lý thông tin bí mật bằng kho bí mật hoặc KMS nếu có.
3. Khi webhook đến, hệ thống kiểm tra chữ ký/HMAC **trên đúng dữ liệu mà nhà cung cấp quy định**, xác minh nguồn khóa, thời hạn và dấu hiệu gửi lại.
4. Server dùng ID giao dịch duy nhất và kiểm tra trạng thái hiện tại để xử lý **idempotent**: nhận hai lần cùng một webhook không được ghi nhận thanh toán hai lần.
5. Log chứa thông tin đủ để tra soát nhưng không lộ số thẻ, token bí mật, khóa hoặc dữ liệu nhạy cảm không cần thiết.

Trong cả hai luồng, mật mã bảo vệ đường truyền, dữ liệu và thông điệp; **quy tắc nghiệp vụ và kiểm soát truy cập** vẫn là phần riêng không thể bỏ qua.

## 9. Quản lý khóa: nơi nhiều thiết kế “đúng thuật toán” vẫn thất bại

Một ứng dụng có AES-GCM chuẩn nhưng đặt khóa trong mã nguồn, ảnh container, log hoặc cùng cơ sở dữ liệu bị lộ có thể mất toàn bộ lợi ích bảo mật. Cần xác định vòng đời khóa trước khi triển khai:

- **Tạo khóa:** dùng nguồn ngẫu nhiên mật mã và kích thước/loại khóa tương thích thuật toán, không tự dựng từ thời gian hay chuỗi cố định.
- **Cấp phát quyền:** chỉ dịch vụ cần thiết được truy cập, tuân thủ nguyên tắc quyền tối thiểu; khóa ký riêng không cấp cho bên chỉ xác minh.
- **Lưu khóa:** chọn keystore được bảo vệ, secret manager, KMS hoặc HSM theo môi trường; phân biệt bí mật dùng khi phát triển và production.
- **Định danh và xoay vòng:** dữ liệu mã hóa dài hạn cần biết dùng phiên bản khóa nào; có kế hoạch mã hóa lại/khôi phục khi đổi khóa.
- **Rò rỉ và thu hồi:** có quy trình thay khóa, vô hiệu phiên/token, đánh giá dữ liệu bị ảnh hưởng và theo dõi sự cố.
- **Sao lưu và khôi phục:** mất khóa có thể làm mất dữ liệu vĩnh viễn; bản sao lưu khóa phải bảo vệ và kiểm thử tương ứng.
- **Vận hành:** hạn chế để khóa hoặc nội dung bí mật trong stack trace, metrics, crash dump, log và câu lệnh debug.

Không phải mọi dữ liệu đều cần mã hóa riêng từng trường: TLS, mã hóa đĩa, mã hóa cột và các biện pháp khác bảo vệ ở **những ranh giới khác nhau**. Chọn theo mô hình đe dọa và yêu cầu tuân thủ thực tế, tránh thêm mật mã mà không thể vận hành khóa an toàn.

## 10. Những nhầm lẫn dễ dẫn đến lỗ hổng

1. **“Base64 là mã hóa.”** Sai. Base64 chỉ đổi cách biểu diễn byte và có thể giải mã trực tiếp mà không cần bí mật.
2. **“SHA-256 mật khẩu là đủ.”** Sai. Hash nhanh cho phép thử đoán với tốc độ cao; cần hàm dành cho mật khẩu, salt riêng và chi phí phù hợp.
3. **“Đã dùng HTTPS nên dữ liệu ở database và log an toàn.”** Sai. TLS bảo vệ đường truyền giữa các điểm cuối; các bản sao dữ liệu khác có ranh giới riêng.
4. **“Có chữ ký số thì nội dung bí mật.”** Sai. Chữ ký hỗ trợ tính toàn vẹn/xác thực nguồn; muốn giữ bí mật phải dùng mã hóa phù hợp.
5. **“Kiểm tra HMAC một lần là webhook không thể bị phát lại.”** Sai. Thông điệp cũ vẫn có MAC hợp lệ; cần freshness, deduplication và idempotency.
6. **“Mã hóa dữ liệu là đủ để chặn đọc trái phép.”** Sai. Server có thể giải mã cho người dùng không được phép nếu thiếu kiểm tra quyền theo tài nguyên.
7. **“Mật mã sửa được SQL injection, XSS hoặc lỗi xử lý nghiệp vụ.”** Sai. Phải kiểm soát đầu vào/đầu ra, truy vấn có tham số, phân quyền và kiểm thử riêng.
8. **“Dùng AES-GCM với một IV cố định tiện hơn.”** Nguy hiểm. Tái sử dụng cặp khóa/IV phá vỡ các bảo đảm an toàn quan trọng của GCM.
9. **“Bỏ qua lỗi chứng chỉ TLS chỉ ảnh hưởng môi trường test.”** Nguy hiểm nếu cấu hình lọt sang môi trường khác; cần sửa trust chain hoặc chứng chỉ đúng cách.
10. **“Có thuật toán mạnh là có hệ thống an toàn.”** Sai. Cách cài đặt, quản lý khóa, xác thực danh tính, phân quyền, giám sát và quy trình xử lý sự cố đều quyết định kết quả.

## 11. Quy trình chọn giải pháp cho một yêu cầu bảo mật

Trước khi chọn API Java, hãy trả lời tuần tự:

1. **Tài sản gì?** Dữ liệu cá nhân, mật khẩu, thông điệp, tài liệu, token hay khóa?
2. **Đối thủ và quyền của họ?** Nghe trộm mạng, sửa message, đọc database backup, chiếm một tài khoản hay chiếm server?
3. **Mục tiêu nào?** Bí mật, toàn vẹn, xác thực nguồn, phân quyền, khả dụng hay bằng chứng truy vết?
4. **Ranh giới nào?** Trên đường truyền, trong bộ nhớ, nơi lưu trữ, giữa các dịch vụ hoặc với bên thứ ba?
5. **Ai giữ khóa và ai tin ai?** Khóa chung, cặp khóa, nguồn public key, phiên bản/rotation và đường xử lý khi lộ khóa?
6. **Giao thức đã có chưa?** Ưu tiên TLS và các cơ chế tiêu chuẩn đã được duy trì, kiểm thử; không tự sáng tác thuật toán hoặc tự dựng giao thức.
7. **Kiểm chứng thế nào?** Có test cho dữ liệu bị sửa, khóa sai, bản tin hết hạn, replay, từ chối quyền, lỗi TLS, khôi phục và rotation không?

Một yêu cầu cụ thể nên dẫn đến **mục tiêu kiểm chứng cụ thể**. Ví dụ: “người đọc được bản sao lưu database không xem được trường X” có thể dẫn đến mã hóa riêng trường X và tách quyền truy cập khóa khỏi database. Ngược lại, “người dùng A không xem đơn của B” đòi hỏi kiểm tra phân quyền trên server dù dữ liệu có được mã hóa hay không.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Một client gửi số tiền và kèm SHA-256 của số tiền. Server nhận cả hai qua một kênh bị tấn công. Server có xác minh được người gửi không?  
**Trả lời:** Không. Đối thủ có thể thay số tiền và tính lại SHA-256. Cần cơ chế xác thực nguồn/thông điệp phù hợp như HMAC/chữ ký cùng kênh hoặc giao thức xác thực tin cậy.

**Câu 2.** HTTPS có ngăn user đã đăng nhập xem dữ liệu của user khác không?  
**Trả lời:** Không. HTTPS bảo vệ kết nối; server phải kiểm tra quyền trên từng bản ghi/hành động.

**Câu 3.** Nếu cần lưu mật khẩu để xác minh sau này, chọn AES hay SHA-256 một lần?  
**Trả lời:** Không chọn cả hai làm cơ chế chính. Dùng hàm băm mật khẩu chuyên dụng với salt và tham số chi phí phù hợp (ví dụ Argon2id hoặc PBKDF2 theo yêu cầu triển khai).

**Câu 4.** Chữ ký webhook hợp lệ có đủ để cộng tiền vào tài khoản ngay không?  
**Trả lời:** Chưa đủ. Phải xác minh khóa đúng đối tác, payload đúng, độ mới và trạng thái giao dịch; xử lý idempotent để tránh thao tác lặp.

**Câu 5.** Tại sao ví dụ AES-GCM vừa giải mã được bản gốc vừa từ chối bản mã đã bị sửa?  
**Trả lời:** AES-GCM là chế độ mã hóa có xác thực (AEAD). Tag ràng buộc nội dung và AAD với khóa/IV; việc xác minh tag thất bại khiến API từ chối dữ liệu không còn khớp.

**Điểm cần nhớ:** An toàn thông tin xác định những điều cần bảo vệ. Mật mã cung cấp những công cụ như mã hóa, MAC, hash, chữ ký, password hashing và TLS để bảo vệ những mục tiêu cụ thể. Một ứng dụng Java an toàn chỉ hình thành khi chọn đúng công cụ, quản lý khóa đúng và kết hợp với xác thực, phân quyền, kiểm tra đầu vào, vận hành và khả năng khôi phục.