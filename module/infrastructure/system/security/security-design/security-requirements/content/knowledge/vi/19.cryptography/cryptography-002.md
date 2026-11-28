# Chọn thuật toán được phê duyệt

## 1. “Được phê duyệt” phải trả lời được bởi ai và cho việc gì

Một yêu cầu như “dùng thuật toán mã hóa mạnh” chưa đủ để triển khai hoặc nghiệm thu. Nó không nói dữ liệu cần bảo vệ khỏi ai, cần bí mật hay xác thực, thuật toán được dùng với mode nào, khóa được tạo ở đâu và ai có thẩm quyền chấp nhận lựa chọn đó.

**Chọn thuật toán được phê duyệt** là chọn một cơ chế mật mã nằm trong chính sách áp dụng cho hệ thống, đúng mục đích, đúng bộ tham số và được thực hiện bởi implementation đáp ứng yêu cầu. Phê duyệt không chỉ là thấy tên thuật toán xuất hiện trong một tài liệu hoặc thư viện.

Cần phân biệt ít nhất bốn lớp:

| Lớp | Câu hỏi cần trả lời |
| --- | --- |
| Cơ sở tiêu chuẩn và chính sách | Nguồn nào cho phép cách dùng này, theo phiên bản nào? |
| Thuật toán và profile | Thuật toán, mode, tham số, định dạng và giới hạn cụ thể là gì? |
| Implementation | Thư viện, provider hoặc module nào thực hiện, trong cấu hình nào? |
| Quyết định của hệ thống | Ai phê duyệt cho dữ liệu, môi trường và vòng đời đang xét? |

Ví dụ, AES là một họ thuật toán được chuẩn hóa trong [FIPS 197](https://csrc.nist.gov/pubs/fips/197/final). Điều đó không tự làm mọi cách gọi `AES` trong Java trở thành thiết kế lưu trữ an toàn, cũng không chứng minh ứng dụng đáp ứng một yêu cầu xác nhận module mật mã.

Trong module thiết kế yêu cầu bảo mật, đầu ra cần là một quyết định có thể truy vết: tài sản và đe dọa dẫn tới profile nào, các ràng buộc sử dụng là gì và bằng chứng nghiệm thu được tạo ở đâu.

## 2. Bắt đầu từ mục tiêu, không từ tên thuật toán

### 2.1. Mỗi mục đích cần một loại cơ chế phù hợp

| Nhu cầu | Loại cơ chế phù hợp để đánh giá | Điều không nên suy diễn |
| --- | --- | --- |
| Giữ bí mật nội dung và phát hiện sửa đổi | Mã hóa có xác thực, thường dưới dạng AEAD | Có mã hóa là đã có toàn vẹn |
| Xác thực thông điệp giữa bên cùng giữ bí mật | MAC theo profile được duyệt | Hash không khóa luôn thay được MAC |
| Xác minh chữ ký bằng khóa công khai | Chữ ký số và mô hình tin cậy khóa | Mọi hàm có tên RSA đều là cơ chế ký hoàn chỉnh |
| Kiểm tra một digest đã có nguồn tin cậy | Hàm hash phù hợp mục đích | Attacker không thể thay cả dữ liệu và digest |
| Lưu thông tin kiểm chứng mật khẩu | Password hashing hoặc password-based KDF phù hợp | SHA-256 một vòng là đủ vì có tên SHA |
| Thiết lập hoặc dẫn xuất khóa | Giao thức key establishment và KDF được duyệt | Một KDF bất kỳ biến mọi mật khẩu yếu thành khóa mạnh |
| Bảo vệ kết nối | Giao thức và cấu hình mật mã được phê duyệt | Tự ghép mã hóa, MAC và handshake đơn giản hơn dùng giao thức |

Base64, nén hoặc đổi định dạng không phải mã hóa bảo mật. Một lớp obfuscation có thể làm dữ liệu khó đọc bằng mắt nhưng không cung cấp tính chất bí mật được kỳ vọng từ mật mã.

Hash không khóa cũng không tự xác thực nguồn gửi khi attacker có thể thay cả dữ liệu lẫn giá trị hash đi kèm. Nếu yêu cầu là phát hiện sửa đổi bởi bên không có khóa, phải chọn cơ chế xác thực và mô hình tin cậy phù hợp.

### 2.2. Xác định thời gian và phạm vi bảo vệ

Trước khi chọn profile, cần trả lời:

- Dữ liệu phải giữ bí mật trong bao lâu?
- Attacker có thể lấy bản sao cơ sở dữ liệu, sửa ciphertext hay kiểm soát một thành phần ứng dụng không?
- Nội dung cần được đọc lại, chỉ kiểm chứng hay chia sẻ cho nhiều bên?
- Dữ liệu nằm trong một tenant hay nhiều tenant dùng chung hạ tầng?
- Có yêu cầu tương thích, phần cứng, xác nhận module hoặc đối tác nào không?
- Khối lượng dữ liệu, số thao tác và khả năng phục hồi ảnh hưởng thế nào đến khóa và nonce?

Mã hóa ổ đĩa, mã hóa tại cơ sở dữ liệu và mã hóa trường ở ứng dụng có ranh giới bảo vệ khác nhau. Chọn cùng một tên thuật toán không làm chúng bảo vệ khỏi cùng một loại xâm nhập. Cần xác định nơi plaintext xuất hiện và thành phần nào có quyền dùng khóa.

## 3. Xác định cơ sở phê duyệt và cách cập nhật

### 3.1. Tiêu chuẩn là đầu vào cho quyết định

Một chính sách mật mã có thể dựa trên tiêu chuẩn của cơ quan chuyên môn, yêu cầu hợp đồng, khả năng nền tảng và đánh giá rủi ro nội bộ. Hồ sơ phải ghi rõ nguồn, phiên bản, ngày xem xét và phạm vi áp dụng.

Hướng dẫn chuyển đổi thuật toán và độ dài khóa là một loại tài liệu quan trọng vì trạng thái sử dụng có thể thay đổi theo mục đích và thời gian. Ví dụ, [NIST SP 800-131A Rev. 2](https://csrc.nist.gov/pubs/sp/800/131/a/r2/final) trình bày hướng dẫn chuyển sang thuật toán và khóa mạnh hơn. Khi phê duyệt thật, phải kiểm tra trạng thái tài liệu, bản sửa đổi và thông báo cập nhật áp dụng tại thời điểm quyết định; không mặc định một bản được trích dẫn trong bài học luôn là bản mới nhất.

Một draft, một đặc tả final và một thông báo kế hoạch sửa đổi không có cùng vai trò. Không ghi “đã được chuẩn hóa” chỉ vì một đề xuất đã được công bố để lấy ý kiến. Ngược lại, việc có kế hoạch sửa đổi không tự có nghĩa mọi triển khai theo bản final hiện tại phải lập tức bị coi là không dùng được.

### 3.2. Phê duyệt phải theo mục đích cụ thể

Một thuật toán có thể được phép cho xác minh dữ liệu cũ nhưng không được phép tạo mới. Cũng có thể một hàm hash được sử dụng trong một cơ chế khác với các giả định khác; không gộp mọi cách dùng chỉ vì cùng chứa một tên hash.

Ví dụ một chính sách nội bộ cho hệ thống mới có thể từ chối MD5 hoặc SHA-1 cho chữ ký và các mục đích dựa vào tính chống va chạm, đồng thời có quy trình riêng để xử lý bản ghi lịch sử. Đó phải là quyết định có mục đích và trạng thái rõ ràng, không phải một tìm kiếm chuỗi rồi tự xóa mọi tham chiếu cũ.

Không đưa thuật toán tự sáng tác, biến thể sửa đổi hoặc cách ghép primitive chưa được thẩm định vào profile chỉ vì bộ test đơn giản chạy được. Tính chất mật mã không được chứng minh bởi việc mã hóa rồi giải mã lại đúng.

### 3.3. Có người chịu trách nhiệm duy trì danh mục

Danh mục thuật toán cần owner và cơ chế rà soát khi có thay đổi tiêu chuẩn, lỗ hổng thư viện, yêu cầu đối tác hoặc thay đổi vòng đời dữ liệu. Phê duyệt một lần rồi không có người tiếp nhận thông báo mới sẽ làm danh mục nhanh chóng lỗi thời.

Một nhóm chuyên trách có thể ban hành profile dùng chung; nhóm sản phẩm vẫn chịu trách nhiệm áp dụng đúng profile cho dữ liệu và đường xử lý của mình. Việc có một danh sách ở cấp tổ chức chưa chứng minh mọi dịch vụ đang dùng đúng.

## 4. Phê duyệt một profile hoàn chỉnh

### 4.1. Tên thuật toán chỉ là điểm bắt đầu

Một profile nên xác định:

| Thành phần | Ví dụ nội dung cần chốt |
| --- | --- |
| Mục đích | Mã hóa bản ghi lưu trữ; xác thực callback; ký artifact |
| Primitive và construction | AEAD, MAC, signature hoặc KDF cụ thể |
| Thuật toán và mode | Không chỉ ghi AES hoặc RSA chung chung |
| Khóa | Loại khóa, độ dài, nguồn tạo, mục đích được phép |
| Tham số | Nonce/IV, tag, padding, curve, hash hoặc work factor phù hợp |
| Giới hạn sử dụng | Dung lượng mỗi thông điệp, số thao tác, cryptoperiod và ngân sách lỗi |
| Định dạng | Envelope version, key ID, ciphertext, tag và metadata |
| Ngữ cảnh được xác thực | Cách ràng buộc tenant, record, phiên bản hoặc mục đích |
| Implementation | Provider/module, phiên bản, môi trường và cấu hình được chấp nhận |
| Hành vi lỗi | Không fallback yếu hơn; không phát plaintext khi xác thực thất bại |
| Chuyển đổi | Cách đọc dữ liệu cũ, tạo dữ liệu mới và retirement |

Không có một tập tham số duy nhất phù hợp mọi loại mật mã. Các trường bắt buộc phải theo construction; chẳng hạn nonce của AEAD không đóng vai trò như salt của password hashing.

### 4.2. Ví dụ profile mã hóa lưu trữ

Giả sử nền tảng lưu ghi chú báo cáo nhạy cảm. Sau đánh giá, tổ chức lựa chọn một profile minh họa:

```yaml
profileId: report-storage-aead-v1
purpose: authenticated_encryption_for_report_notes
status: encrypt_and_decrypt
algorithm: AES
mode: GCM
keyBits: 256
nonceBits: 96
tagBits: 128
maxPlaintextBytes: 1048576
keyPolicyRef: report-data-key-policy-v1
noncePolicyRef: gcm-nonce-allocation-policy-v1
usageLimitsRef: gcm-key-usage-budget-v1
contextEncodingRef: report-envelope-context-v1
providerPolicyRef: production-crypto-provider-policy-v1
onAuthenticationFailure: reject_without_plaintext
fallbackProfile: none
```

Các giá trị là lựa chọn của ví dụ, không phải bộ mặc định bắt buộc cho mọi ứng dụng. AES-128, AES-192 và AES-256 đều thuộc tiêu chuẩn AES; việc chọn 256 bit ở đây không có nghĩa mọi dùng AES-128 đều yếu hoặc không được phép.

Các tham chiếu `noncePolicyRef`, `usageLimitsRef` và `providerPolicyRef` phải được giải quyết thành chính sách có giá trị cụ thể trước triển khai. Không thể nghiệm thu một profile còn trống các phụ thuộc quan trọng chỉ vì phần YAML trên parse được.

### 4.3. Mode và authentication phải phù hợp mục tiêu

AES-GCM là một cơ chế mã hóa có xác thực với associated data; mode GCM và GMAC được mô tả trong [NIST SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final). Chọn mode là một quyết định khác với chọn primitive AES.

Không thay GCM bằng ECB hoặc CBC chỉ vì provider không hỗ trợ cấu hình đã chọn. ECB không đáp ứng profile bảo vệ bản ghi này; CBC tự nó không cung cấp cùng tính chất xác thực. Nếu cần một construction khác, phải có profile riêng đã được xem xét, không tự nối thêm một MAC theo cách tùy ý.

Việc ưu tiên authenticated encryption và tránh tự thiết kế cơ chế mật mã được thảo luận trong [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html).

## 5. Khóa, nonce và associated data là điều kiện của profile

### 5.1. Độ dài khóa không bù cho quản lý khóa sai

Một khóa 256 bit được hard-code trong repository hoặc lưu cùng dữ liệu với quyền truy cập như nhau không tạo ra ranh giới bảo vệ mong muốn. Tương tự, chuỗi 32 ký tự dễ đoán không tự có 256 bit entropy.

Yêu cầu cần liên kết profile với chính sách tạo, lưu, sử dụng, xoay và thu hồi khóa. Với KMS/HSM hoặc key store được quản lý, phải kiểm soát quyền dùng khóa theo service và mục đích, không chỉ quyền đọc cấu hình ứng dụng.

Không dùng chung một khóa cho mọi vai trò như mã hóa dữ liệu, MAC và bảo vệ token nếu profile không cho phép. Tách mục đích và ngữ cảnh giúp tránh việc một khả năng mật mã ở nơi này bị dùng để tác động tới một giao thức khác.

### 5.2. GCM cần nonce không lặp dưới cùng khóa

Nonce không phải secret, nhưng tính duy nhất theo khóa là điều kiện quan trọng. Sinh một mảng 12 byte có vẻ ngẫu nhiên chưa tự chứng minh điều kiện này ở quy mô nhiều instance, restart và khôi phục backup.

Chính sách nonce phải trả lời:

- Ai tạo hoặc cấp phát nonce, ứng dụng hay dịch vụ mật mã được quản lý?
- Dùng construction nonce nào và giới hạn sử dụng tương ứng?
- Nhiều instance chia sẻ cùng key có phối hợp như thế nào?
- Retry có tiêu thụ nonce mới hay dùng lại một thao tác đã hoàn tất?
- Rollback, clone môi trường và restore có thể lặp trạng thái sinh nonce không?
- Khi chạm ngân sách hoặc không thể bảo đảm tính duy nhất, hệ thống dừng hoặc đổi khóa ra sao?

Không dùng timestamp đơn thuần, một ID được tái sử dụng hoặc counter khởi tạo lại tùy ý làm bằng chứng. Với nonce ngẫu nhiên, cần đánh giá xác suất va chạm và giới hạn tổng theo khóa; với nonce có cấu trúc, cần chứng minh cách cấp phát và trạng thái bền vững.

Một ca test tạo vài nghìn nonce không trùng chỉ kiểm tra một số lỗi implementation. Nó không chứng minh không bao giờ trùng hoặc thay thế phân tích ngân sách sử dụng.

### 5.3. AAD ràng buộc ngữ cảnh, không thay phân quyền

Associated data có thể ràng buộc ciphertext với tenant, record, mục đích hoặc phiên bản envelope. Điều này giúp phát hiện việc đưa ciphertext hợp lệ từ ngữ cảnh này sang ngữ cảnh khác nếu thiết kế thực thi đúng.

AAD được xác thực nhưng không được mã hóa bởi AEAD. Không đặt secret vào đó rồi cho rằng nó được giữ bí mật. Cách mã hóa AAD phải xác định rõ byte, thứ tự và độ dài; nối chuỗi bằng một dấu phân cách mơ hồ có thể tạo cách diễn giải không nhất quán.

Khi giải mã, tenant và record mong đợi phải xuất phát từ ngữ cảnh đã được kiểm tra quyền. Nếu lấy mọi thông tin AAD từ chính envelope mà không đối chiếu ngữ cảnh cần đọc, ứng dụng có thể vẫn chấp nhận một ciphertext bị chuyển chỗ hợp lệ.

AAD cũng không chống replay một cách tự động. Nếu nghiệp vụ yêu cầu phát hiện bản ghi cũ bị đưa trở lại, cần ràng buộc version hoặc cơ chế trạng thái phù hợp và đặc tả cách kiểm tra.

## 6. Phân biệt thuật toán, thư viện và module được xác nhận

### 6.1. Có implementation không đồng nghĩa có phê duyệt

Một JDK có thể cung cấp nhiều thuật toán và mode, gồm cả những cơ chế không nằm trong policy của sản phẩm. Việc `getInstance()` thành công chỉ chứng minh tìm được implementation tương ứng trong môi trường đó.

Cần xác định provider nào thực sự được chọn, phiên bản nào, cấu hình nào và có thay đổi khi dependency hoặc runtime được nâng cấp không. Không để thứ tự provider vô tình làm production dùng một implementation khác với môi trường đã kiểm chứng nếu yêu cầu bắt buộc một provider cụ thể.

Thư viện được duy trì, primitive chuẩn và API mức cao giúp giảm lỗi, nhưng không tự chứng minh cách tích hợp đã bảo vệ key, nonce, metadata và đường lỗi đúng.

### 6.2. FIPS validation là một yêu cầu có phạm vi riêng

Nếu hệ thống có yêu cầu dùng cryptographic module được xác nhận, hồ sơ phải đối chiếu module cụ thể, phiên bản, operating environment, security policy, chế độ vận hành và trạng thái chứng nhận phù hợp.

Không suy từ “thuật toán này là AES”, “thư viện hỗ trợ FIPS” hoặc “có chứng nhận thuật toán” sang “toàn ứng dụng đã đáp ứng yêu cầu FIPS”. Chương trình [NIST Cryptographic Module Validation Program](https://csrc.nist.gov/projects/cryptographic-module-validation-program) đánh giá module; [CMVP FAQ](https://csrc.nist.gov/projects/cryptographic-module-validation-program/faqs) cũng phân biệt bước xác nhận thuật toán trong quy trình xác nhận module.

Tuyên bố phù hợp phải dựa trên phạm vi bằng chứng thật. Một lần tự chạy known-answer test của ứng dụng không tạo ra chứng nhận module. Một module được xác nhận cũng không tự chứng minh toàn bộ thiết kế phân quyền và quản lý dữ liệu của sản phẩm đã đúng.

Trạng thái và điều kiện chấp nhận có thể thay đổi theo thời gian. Hồ sơ cần có lần kiểm tra cập nhật thay vì giữ nguyên một số certificate từ nhiều năm trước mà không xem xét các điều kiện áp dụng.

## 7. Ánh xạ các mục đích khác sang profile riêng

### 7.1. MAC và hash

Một profile MAC có thể chọn HMAC-SHA-256 cùng chính sách về key, độ dài tag, định dạng thông điệp và chống replay. Nó không dùng cùng key với profile mã hóa chỉ vì hai chức năng cùng thuộc một service.

Nếu cần xác thực một callback, chỉ chọn HMAC chưa đủ. Cần xác định các byte nào được MAC, timestamp hoặc nonce nghiệp vụ, cửa sổ chấp nhận và cách đối chiếu chữ ký. Hai phía có thể tính đúng HMAC trên hai biểu diễn khác nhau mà vẫn không tích hợp được; một biểu diễn mơ hồ còn có thể gây sai ngữ nghĩa.

Với digest cho artifact, cần xác định nguồn tin cậy của digest hoặc chữ ký bao phủ nó. Hash mạnh không bảo vệ một file nếu attacker được thay cả file và giá trị hash công khai đi kèm mà không có ràng buộc khác.

### 7.2. Chữ ký số

Một profile chữ ký phải xác định họ thuật toán, tham số, hash khi áp dụng, kiểu encoding chữ ký, nguồn khóa và mô hình tin cậy khóa xác minh. ECDSA trên một curve cụ thể hoặc RSA-PSS với bộ tham số cụ thể là các quyết định đầy đủ hơn hai chữ “ECC” và “RSA”.

Ví dụ ứng viên để tổ chức đánh giá có thể là ECDSA P-256 với SHA-256 hoặc RSA-PSS với key và tham số được chốt. Chúng không tự được phê duyệt chỉ vì xuất hiện trong ví dụ. Cần đối chiếu tiêu chuẩn, mức an toàn, khả năng bên nhận và implementation. [FIPS 186-5, Digital Signature Standard](https://csrc.nist.gov/pubs/fips/186-5/final) là một nguồn tiêu chuẩn về chữ ký số.

Không so trực tiếp số bit của RSA với số bit khóa AES để kết luận cơ chế nào mạnh hơn. Các họ thuật toán có mô hình tấn công và cách đánh giá security strength khác nhau.

Chữ ký hợp lệ chỉ có ý nghĩa khi khóa xác minh đúng danh tính hoặc vai trò cần tin cậy, thông điệp đúng ngữ cảnh và các điều kiện như thời hạn, version hoặc chống replay được xử lý. Nếu attacker tự gửi cả public key lẫn chữ ký, việc xác minh bằng chính key đó không tự xác thực họ là chủ thể được phép.

### 7.3. Mật khẩu không dùng profile mã hóa bản ghi

Thông tin kiểm chứng mật khẩu cần password hashing với salt và chi phí phù hợp. Một hàm hash nhanh như SHA-256 không trở thành lựa chọn phù hợp chỉ bằng cách lặp một số lần tùy ý hoặc ghép một secret theo cách tự thiết kế.

Argon2id hoặc một profile PBKDF2 phù hợp có thể được xem xét theo chính sách và các ràng buộc áp dụng. Bộ tham số phải được đánh giá trên tải xác thực dự kiến, có giới hạn chống DoS và cơ chế nâng cấp khi người dùng đăng nhập hoặc đổi mật khẩu. Xem [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Một lựa chọn phù hợp cho password hashing nói chung không tự đáp ứng mọi yêu cầu xác nhận module của một môi trường cụ thể. Cần đối chiếu cả cơ chế và implementation, không gắn nhãn phê duyệt chung cho mọi sản phẩm dùng cùng tên thuật toán.

## 8. Quản lý trạng thái cho tạo mới và dữ liệu lịch sử

Một danh mục chỉ có cột “allowed” dễ tạo nhầm lẫn. Nên tách mục đích thao tác và vòng đời:

| Trạng thái minh họa | Tạo ciphertext/chữ ký mới | Đọc hoặc xác minh dữ liệu cũ |
| --- | --- | --- |
| Được phép tạo mới và sử dụng | Cho phép trong scope | Cho phép theo profile |
| Chỉ đọc/giải mã/xác minh lịch sử | Không cho tạo mới | Chỉ theo phạm vi và thời hạn đã phê duyệt |
| Cần chuyển đổi | Chỉ profile thay thế tạo mới | Luồng cũ được kiểm soát để migrate |
| Đã ngừng | Không cho phép | Xử lý theo kế hoạch lưu giữ hoặc phục hồi đã chốt |
| Không nhận diện hoặc chưa phê duyệt | Không cho phép | Không tự thử một thuật toán mặc định |

Tên trạng thái có thể khác, nhưng hành vi phải rõ. “Deprecated” không được hiểu thành “vẫn dùng mới nếu tiện”. Cũng không tự hủy mọi khóa cũ khi chính sách yêu cầu còn đọc dữ liệu lịch sử trong một thời hạn hợp lệ.

Một yêu cầu có thể ghi:

> Sau thời điểm chuyển profile, mọi ghi mới dùng profile B. Profile A chỉ được giải mã bản ghi lịch sử đã nhận diện trong phạm vi được phép. Dịch vụ không được fallback từ B sang A khi mã hóa thất bại. Việc ngừng khả năng đọc A chỉ diễn ra sau khi điều kiện chuyển đổi và phục hồi được nghiệm thu.

Mốc thời gian, phạm vi dữ liệu và người phê duyệt phải cụ thể trong hồ sơ thật. Không để một danh mục vận hành chỉ dựa trên ký ức rằng “thuật toán này trước đây từng được dùng”.

## 9. Định dạng envelope và chống chọn thuật toán ngoài policy

### 9.1. Version hóa định dạng để có thể chuyển đổi

Một envelope minh họa có thể gồm:

```text
formatVersion
profileId
keyId
nonce
ciphertextAndTag
```

`profileId` tham chiếu cấu hình do server kiểm soát. Nó không phải tên JCA tùy ý được truyền thẳng vào `Cipher.getInstance()`. `keyId` cũng cần được giới hạn trong miền key được phép và đối chiếu quyền, không trở thành một địa chỉ KMS hoặc nguồn khóa tùy ý.

Metadata cần có giới hạn kích thước, định dạng và chính sách xác thực phù hợp. Khi profile hoặc version không được nhận diện, từ chối theo đường lỗi đã thiết kế thay vì thử lần lượt mọi thuật toán cho tới khi một cái “giải được”.

### 9.2. Không để dữ liệu không tin cậy tự chọn độ mạnh

Nếu client có thể yêu cầu `algorithm=AES/ECB/PKCS5Padding` hoặc `tagBits=32`, một allowlist chỉ kiểm tra tên AES là không đủ. Policy phải áp dụng cho profile và tham số có hiệu lực.

Ngay cả envelope đã lưu trong cơ sở dữ liệu cũng có thể là dữ liệu bị sửa trong mô hình đe dọa. Cần parse chặt, giới hạn lựa chọn và ràng buộc metadata với xác thực theo construction. Không mặc định mọi trường đã lưu đều đáng tin hơn request từ mạng.

Ngược lại, không cần giấu tên profile như một secret. Bí mật chủ yếu nằm ở khóa và các yếu tố được thiết kế là bí mật. Công khai thuật toán chuẩn không được làm mất tính chất bảo mật mong đợi.

## 10. Ví dụ Java: transformation rõ ràng và tham số cố định

### 10.1. Tránh phụ thuộc mode mặc định

Đoạn sau không biểu đạt đủ profile của ví dụ:

```java
Cipher cipher = Cipher.getInstance("AES");
```

Theo API Java, khi chỉ chỉ định tên thuật toán, mode và padding có thể dùng mặc định của provider. Không dựa vào một mặc định chưa được kiểm tra để kết luận ứng dụng đang dùng GCM.

Một trích đoạn thể hiện rõ lựa chọn đã được phê duyệt:

```java
// Các tiền điều kiện được hạ tầng mật mã đã phê duyệt bảo đảm:
// - approvedProvider đáp ứng policy của môi trường.
// - dataKey là key AES đúng độ dài, purpose và trạng thái được phép.
// - reservedNonce có 12 byte và chưa từng dùng với dataKey để mã hóa.
// - contextBytes theo encoding AAD đã công bố.
// - plaintext đã nằm trong ngân sách dung lượng của profile.

Cipher cipher = Cipher.getInstance(
        "AES/GCM/NoPadding", approvedProvider);

GCMParameterSpec parameters = new GCMParameterSpec(
        128, reservedNonce);

cipher.init(Cipher.ENCRYPT_MODE, dataKey, parameters);
cipher.updateAAD(contextBytes);
byte[] ciphertextAndTag = cipher.doFinal(plaintext);
```

Các số 128 và 12 byte thể hiện tag và nonce của profile minh họa, không phải cùng một đơn vị. Code này không cấp phát nonce, không tạo key và không kiểm chứng provider; các tiền điều kiện không được coi là đã hoàn thành chỉ vì chúng được viết trong comment.

Không gọi `getEncoded()` chỉ để ép xuất một khóa được quản lý trong phần cứng nếu thiết kế yêu cầu khóa không xuất được. Metadata về loại và độ dài key cần đến từ nguồn tin cậy của key manager hoặc cơ chế phù hợp môi trường.

### 10.2. Chỉ phát plaintext sau khi xác thực thành công

Khi giải mã AEAD, tag phải được kiểm chứng và lỗi phải được chuyển thành thất bại, không phải dữ liệu rỗng hoặc đường fallback. Với Java, `doFinal` thực hiện bước xác thực tag và có thể báo `AEADBadTagException` khi không khớp. Tài liệu [Java SE 21 Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html) cũng nêu yêu cầu IV duy nhất của GCM và thứ tự cung cấp AAD.

Yêu cầu triển khai nên nói:

> Plaintext chưa được xác thực không được chuyển tới parser nghiệp vụ, trả response, lưu chính thức hoặc dùng để tạo tác dụng phụ. Khi xác thực thất bại, dịch vụ không thử mode yếu hơn và không trả kết quả giải mã một phần.

Với dữ liệu lớn và streaming, cần dùng construction hoặc thư viện hỗ trợ semantics xác thực phù hợp. Không nối thêm một vòng lặp `Cipher.update()` rồi mặc định mọi byte nhận được trước tag đã được tin cậy.

### 10.3. Lỗi provider không phải lý do hạ cấp

Nếu production thiếu transformation hoặc key manager không sẵn sàng, hệ thống phải đi theo đường lỗi hoặc phục hồi đã thiết kế. Không đổi sang provider bất kỳ, CBC, plaintext hoặc một key dự phòng hard-code để thao tác tiếp tục thành công.

Nếu cho phép nhiều provider, danh sách và điều kiện chuyển phải được phê duyệt, kiểm thử tương thích và giữ cùng profile. “Có fallback” không được đồng nghĩa “bất kỳ thứ gì thư viện hỗ trợ”.

## 11. Crypto agility là khả năng chuyển đổi có kiểm soát

Crypto agility không phải một trường cấu hình cho người gọi chọn thuật toán tùy ý. Nó là khả năng thay profile, key hoặc implementation qua một quy trình có version, bằng chứng và điều kiện chuyển đổi rõ.

Một kế hoạch chuyển đổi cần trả lời:

- Profile mới dùng cho ghi mới từ thời điểm nào?
- Dữ liệu cũ được migrate chủ động hay khi đọc?
- Làm sao không mã hóa lại một phần rồi ghi nhầm metadata?
- Khóa cũ còn giữ vì backup hoặc bản ghi lịch sử nào?
- Rollback code có thể đọc dữ liệu mới hay phải bị chặn?
- Khi profile cũ bị coi là không còn chấp nhận được, có thể vô hiệu hóa trong thời hạn nào?

Không làm mất dữ liệu chỉ để loại một tên thuật toán khỏi source. Cần kiểm chứng khả năng đọc, tính toàn vẹn, bản sao dự phòng và trạng thái migrate trước khi thu hồi hoặc hủy key theo policy.

### Cân nhắc chuyển đổi hậu lượng tử

Dữ liệu có thời hạn bí mật dài cần được xem xét trong lộ trình thuật toán, kể cả khi chưa có thay đổi ngay tại ứng dụng. Cần phân biệt vai trò: [FIPS 203](https://csrc.nist.gov/pubs/fips/203/final) chuẩn hóa ML-KEM cho thiết lập bí mật chung; [FIPS 204](https://csrc.nist.gov/pubs/fips/204/final) chuẩn hóa ML-DSA và [FIPS 205](https://csrc.nist.gov/pubs/fips/205/final) chuẩn hóa SLH-DSA cho chữ ký số.

Một KEM không phải hàm thay trực tiếp AES để mã hóa toàn bộ báo cáo. Việc chọn tham số, tích hợp giao thức, mô hình hybrid khi áp dụng và implementation cần profile được duyệt cùng bằng chứng tương thích. Không tự ghép các thuật toán mới chỉ vì chúng có tiêu chuẩn riêng.

Mục tiêu ở cấp yêu cầu là biết hệ thống dùng mật mã ở đâu, thời hạn bảo vệ nào quan trọng và có thể chuyển đổi ra sao. Tuyên bố “đã có thư viện PQC” chưa chứng minh một giao thức đang triển khai có tính chất mong muốn.

## 12. Bộ yêu cầu có thể giao cho nhóm triển khai

| Mã | Yêu cầu minh họa | Bằng chứng nghiệm thu dự kiến |
| --- | --- | --- |
| CRYPTO-ALG-01 | Mọi thao tác mật mã phải ánh xạ tới profile được duyệt theo purpose và môi trường | Inventory crypto, cấu hình hiệu lực và đường gọi |
| CRYPTO-ALG-02 | Profile chưa nhận diện hoặc không cho thao tác hiện tại phải bị từ chối | Ca profile lạ, deprecated và tạo mới bằng profile chỉ đọc |
| CRYPTO-ALG-03 | Thuật toán, mode và tham số có hiệu lực phải nằm trong profile | Đối chiếu provider, key metadata, nonce, tag hoặc tham số tương ứng |
| CRYPTO-ALG-04 | Lỗi implementation hoặc cấu hình không được gây hạ cấp ngoài policy | Làm thiếu provider hoặc profile và quan sát đường lỗi |
| CRYPTO-ALG-05 | Key và nonce phải đáp ứng chính sách đã liên kết, gồm nhiều instance và phục hồi | Kiểm chứng thiết kế cấp phát, usage budget, restart và restore |
| CRYPTO-ALG-06 | Xác thực ciphertext thất bại không được phát plaintext hoặc commit nghiệp vụ | Sửa ciphertext, tag, AAD và kiểm tra tác dụng phụ |
| CRYPTO-ALG-07 | Metadata lựa chọn profile/key không được mở rộng quyền hoặc thuật toán | Ca key ID ngoài scope, profile sai purpose và envelope bị sửa |
| CRYPTO-ALG-08 | Có đường chuyển đổi profile và kiểm chứng dữ liệu lịch sử | Migrate, rollback theo policy và restore backup |
| CRYPTO-ALG-09 | Yêu cầu xác nhận module, nếu có, phải được chứng minh trên cấu hình triển khai | Đối chiếu certificate, security policy, environment và mode |
| CRYPTO-ALG-10 | Danh mục phải có owner, nguồn phê duyệt và cơ chế cập nhật | Hồ sơ quyết định, phiên bản policy và lịch sử thay đổi |

Yêu cầu về thuật toán cần đi cùng yêu cầu khóa và kiến trúc. Không đánh dấu hoàn tất toàn bộ bảo vệ dữ liệu chỉ vì CRYPTO-ALG-03 có một transformation đúng trong code.

## 13. Kế hoạch nghiệm thu: chứng minh dùng đúng, từ chối đúng và phục hồi được

Các ca dưới đây là kế hoạch kiểm chứng cho profile lưu ghi chú minh họa, không phải kết quả đã chạy trên một hệ thống cụ thể.

| Ca | Điều kiện | Kết quả cần quan sát |
| --- | --- | --- |
| Profile hợp lệ | Key, nonce, AAD và dữ liệu đúng policy | Mã hóa/giải mã đúng và metadata nhất quán |
| Profile không biết | Thay `profileId` ngoài danh mục | Từ chối, không thử thuật toán mặc định |
| Sai purpose | Dùng key/profile của chức năng khác | Không dùng được ngoài scope đã cấp |
| Sai tham số | Nonce, tag hoặc tham số không đúng profile | Từ chối trước khi phát kết quả được tin cậy |
| Dữ liệu bị sửa | Thay một byte ciphertext hoặc tag | Lỗi xác thực; không phát plaintext |
| Ngữ cảnh bị đổi | Đổi tenant, record hoặc version mong đợi | Không chấp nhận ciphertext cho ngữ cảnh sai |
| Key ID ngoài scope | Envelope chọn key của tenant hoặc mục đích khác | Không mở quyền dùng key từ metadata |
| Thiếu provider | Môi trường không có implementation được phép | Không fallback yếu hơn hoặc plaintext |
| Profile chỉ đọc | Yêu cầu tạo mới bằng profile legacy | Bị chặn trong khi đường đọc lịch sử đúng scope vẫn theo policy |
| Nhiều instance | Các node cùng dùng một key | Cơ chế nonce và ngân sách tổng theo thiết kế |
| Restart/restore | Khôi phục trạng thái sinh nonce hoặc deployment | Không tái sử dụng nonce dưới cùng key ngoài construction được duyệt |
| Hết ngân sách | Chạm giới hạn dùng key hoặc kích thước | Dừng/đổi key theo policy, không tiếp tục không giới hạn |
| Migration | Đọc cũ, ghi mới, ngắt giữa lần chuyển | Không mất dữ liệu hoặc ghi sai version |
| Backup | Phục hồi dữ liệu thuộc các thời kỳ key khác nhau | Đọc được phần cần giữ, theo quyền và vòng đời đã chốt |

### 13.1. Round-trip chưa đủ

`decrypt(encrypt(data)) == data` chỉ chứng minh một tính chất chức năng trong điều kiện thử. Một cơ chế dùng IV cố định hoặc mode không phù hợp cũng có thể vượt ca này.

Cần kiểm thử âm, kiểm tra cấu hình hiệu lực, test vector khi phù hợp và đánh giá các điều kiện ngoài hàm như nonce uniqueness, key purpose, quyền KMS và đường lỗi. Test vector của implementation không thay thế kiểm chứng tích hợp hoặc xác nhận module nếu đó là yêu cầu riêng.

### 13.2. Không dùng quét chuỗi như bằng chứng duy nhất

Tìm `MD5`, `SHA1` hoặc `ECB` trong source có thể hỗ trợ review, nhưng không phản ánh đầy đủ cấu hình động, thư viện bắc cầu, KMS hoặc dữ liệu lịch sử. Một chuỗi xuất hiện trong test từ chối khác với nó được dùng để tạo dữ liệu thật.

Ngược lại, không tìm thấy chuỗi nguy hiểm không chứng minh profile đúng. Thuật toán có thể được lựa chọn qua tên alias, cấu hình bên ngoài hoặc mặc định provider. Bằng chứng cần liên kết với đường chạy và môi trường thực tế.

### 13.3. Bằng chứng phải đủ phạm vi, không chứa secret

Hồ sơ có thể lưu profile ID, key version không bí mật theo chính sách, provider/version, release, cấu hình được phê duyệt và kết quả ca kiểm thử. Không lưu plaintext nhạy cảm, raw key hoặc credential KMS chỉ để chứng minh code đã gọi mã hóa.

Thông điệp lỗi công khai nên theo hợp đồng hạn chế tiết lộ không cần thiết; nguyên nhân chi tiết được ghi ở nơi có quyền truy cập phù hợp. Không tuyên bố toàn bộ đường lỗi hằng thời gian chỉ vì các lỗi có cùng một message; nếu cần tính chất đó, phải có thiết kế và kiểm chứng riêng.

## 14. Phê duyệt ngoại lệ và xử lý sự cố thuật toán

Một hệ thống cũ có thể chưa chuyển ngay được vì đối tác hoặc định dạng dữ liệu. Ngoại lệ cần ghi mục đích, dữ liệu, phạm vi, thời hạn, người chấp nhận rủi ro, biện pháp bù và kế hoạch thoát. Không thêm một thuật toán vào allowlist toàn cục chỉ để giải quyết một tích hợp cá biệt.

Khi có thông báo lỗ hổng hoặc thay đổi chính sách, inventory mật mã phải hỗ trợ tìm service, purpose, provider, key và tập dữ liệu chịu ảnh hưởng. Cần biết khả năng tắt ghi mới, chuyển profile, xoay khóa và giữ đường đọc phục hồi theo mức rủi ro.

Không mặc định đổi thuật toán luôn giải quyết việc lộ khóa. Nếu khóa đã bị lấy, dữ liệu trước đó có thể đã mất bí mật; kế hoạch ứng phó phải đánh giá tài sản và phạm vi ảnh hưởng, không chỉ thay một hằng số transformation.

Ngược lại, xoay key không sửa một construction dùng sai nonce hoặc thiếu xác thực nếu lỗi vẫn lặp lại với key mới. Phải xử lý nguyên nhân thiết kế hoặc implementation trước khi coi thay đổi là hoàn tất.

## 15. Một hồ sơ quyết định gọn cho kiến trúc

```text
Tài sản: ghi chú báo cáo cần bí mật và phát hiện sửa đổi.
Đe dọa: lộ bản sao lưu trữ, sửa ciphertext, chuyển dữ liệu sai tenant.

Profile được chọn:
  - AEAD theo danh mục được phê duyệt cho purpose lưu trữ.
  - Primitive, mode, key, nonce, tag và giới hạn được xác định rõ.
  - Provider/module và môi trường có bằng chứng phù hợp.

Ràng buộc:
  - Key được quản lý và cấp quyền theo purpose.
  - Nonce không lặp theo construction và ngân sách của profile.
  - Ngữ cảnh được mã hóa nhất quán và xác thực bằng AAD khi áp dụng.
  - Không dùng plaintext trước khi xác thực thành công.
  - Không hạ cấp ngoài policy khi lỗi.

Vòng đời:
  - Ghi mới, đọc lịch sử và retirement có trạng thái riêng.
  - Có version envelope, migration, restore và owner duy trì policy.

Kiểm chứng:
  - Ca dương, sửa ciphertext/tag/context, sai key/purpose/profile.
  - Restart, nhiều instance, giới hạn sử dụng và phục hồi.
  - Bằng chứng cấu hình thực tế, không chỉ tên thuật toán trong code.
```

Chọn thuật toán được phê duyệt là chọn đúng cơ chế cho mục tiêu, đúng profile cho cách sử dụng và đúng implementation cho môi trường. Khi quyết định được liên kết với khóa, tham số, vòng đời và bằng chứng, yêu cầu mật mã mới có thể triển khai và kiểm chứng thay vì chỉ dừng ở một tên thuật toán được cho là mạnh.
