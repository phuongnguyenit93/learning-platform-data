# 1.5. Quan hệ giữa khóa, thuật toán, tham số, giao thức và danh tính

Trong mật mã ứng dụng, nói “hệ thống dùng AES-256” hoặc “API có chứng chỉ TLS” chưa đủ để kết luận hệ thống an toàn. Một cơ chế bảo mật thực sự hình thành khi **khóa đúng** được dùng với **thuật toán phù hợp**, **tham số hợp lệ**, trong **giao thức có thứ tự và quy tắc kiểm tra rõ ràng**, đồng thời gắn kết kết quả mật mã với **danh tính đã được tin cậy**.

Sau bài này, người học cần có khả năng:
- Phân biệt vai trò và quan hệ của khóa, thuật toán, tham số, giao thức và danh tính.
- Giải thích vì sao một chữ ký hợp lệ, bản mã giải mã được hoặc kết nối TLS thành công vẫn có thể chưa đủ để tin tưởng đối tác.
- Nhận ra cách các tham số như nonce, salt, AAD, độ dài tag, phiên bản giao thức ảnh hưởng đến tính an toàn.
- Thiết kế một luồng bảo vệ dữ liệu có kiểm tra danh tính, quản lý khóa, chống sửa đổi và chống phát lại phù hợp.
- Liên hệ mô hình đó với API mật mã trong Java 17+.

## 1. Năm thành phần và câu hỏi mà mỗi thành phần trả lời

| Thành phần | Câu hỏi chính | Ví dụ | Sai lầm thường gặp |
| --- | --- | --- | --- |
| **Khóa (key)** | Ai nắm bí mật/quyền mật mã nào? | Khóa AES phiên, khóa riêng Ed25519, khóa công khai máy chủ, PSK | Cho rằng biết tên thuật toán là đủ để giải mã; để lộ khóa trong log |
| **Thuật toán (algorithm)** | Phép toán bảo vệ thông tin là gì? | AES-GCM, Ed25519, SHA-256, HMAC-SHA256, HKDF, ECDHE | Dùng hash thường để xác thực dữ liệu trước đối thủ chủ động |
| **Tham số (parameters)** | Thuật toán được vận hành ở cấu hình nào, cho thông điệp nào? | Khóa 128/256 bit, nonce 96 bit, tag 128 bit, AAD, salt, curve, hash, work factor | Tái sử dụng nonce của GCM với cùng khóa |
| **Giao thức (protocol)** | Các bên gửi gì, theo thứ tự nào, kiểm tra gì và xử lý lỗi ra sao? | TLS 1.3 handshake, AEAD record format, quy tắc trao đổi và xoay khóa | Có thuật toán mạnh nhưng không xác thực handshake hoặc không chống replay |
| **Danh tính (identity)** | Khóa hoặc kết quả mật mã gắn với thực thể nào, dựa trên niềm tin nào? | Tên DNS trong SAN của chứng chỉ, service account, người dùng, thiết bị | Chấp nhận chữ ký của bất kỳ khóa công khai nào do chính phía gửi cung cấp |

Đọc theo chuỗi:

```text
Mục tiêu an ninh + mô hình đe dọa
             ↓
Xác định danh tính và mối quan hệ tin cậy cần chứng minh
             ↓
Chọn giao thức có quy tắc thương lượng, xác thực và chống lỗi
             ↓
Giao thức chọn thuật toán, khóa và tham số thích hợp
             ↓
Phép toán mật mã tạo kết quả; bên nhận kiểm tra rồi mới sử dụng
```

Các lớp ràng buộc lẫn nhau. Một khóa không có ý nghĩa thực tế nếu chưa biết mục đích, thuật toán và quyền sử dụng. Một chữ ký chỉ xác thực **sự sở hữu khóa ký**; muốn xác thực danh tính phải biết vì sao khóa công khai đối ứng được tin là của chủ thể cần tìm. Một giao thức không thể an toàn nếu bỏ qua việc xử lý lỗi xác thực hoặc chấp nhận tham số yếu.

## 2. Khóa: tài sản mật mã và phạm vi quyền hạn

### 2.1. Khóa đối xứng, bất đối xứng và khóa phiên

- **Đối xứng:** hai phía cùng biết một khóa bí mật `K`. AES-GCM dùng `K` để mã hóa và tạo authentication tag; bên giải mã cũng cần `K`. HMAC dùng khóa đối xứng để xác thực thông điệp, nhưng không mã hóa nội dung. Vì nhiều bên có thể cùng giữ `K`, một tag hợp lệ **không chứng minh duy nhất người gửi là ai**.
- **Bất đối xứng:** một cặp gồm khóa riêng `sk` và khóa công khai `pk`, có quan hệ theo thuật toán. Với chữ ký số, `sk` ký và `pk` xác minh; người xác minh không cần biết `sk`. Khóa công khai không phải “bí mật được mã hóa”.
- **Khóa dài hạn:** chẳng hạn khóa riêng TLS máy chủ hoặc khóa gốc được quản lý trong KMS. Chúng có nhiệm vụ và vòng đời riêng.
- **Khóa tạm/khóa phiên:** được thiết lập hoặc dẫn xuất cho một kết nối, phiên, mục đích hay chiều truyền. TLS 1.3 thông thường dùng bí mật trao đổi tạm thời và HKDF để dẫn xuất khóa lưu lượng; khóa dùng mã hóa bản ghi khác khóa riêng xác thực máy chủ.

**Không đồng nhất password với cryptographic key.** Mật khẩu thường có entropy thấp, cần hàm dẫn xuất/hashing chuyên cho mật khẩu với salt và chi phí tính toán phù hợp (ví dụ Argon2id qua thư viện được đánh giá; PBKDF2 trong môi trường cần tương thích). HKDF phù hợp để dẫn xuất từ vật liệu khóa đã có entropy đủ cao, không tự làm cho mật khẩu yếu trở thành mạnh.

### 2.2. Khóa phải gắn với mục đích và vòng đời

Thông tin quản trị tối thiểu cho một khóa gồm: `keyId`, loại/thuật toán được phép, mục đích (`encrypt`, `sign`, `derive`…), chủ sở hữu/miền tin cậy, phiên bản, trạng thái (active/retired/revoked), thời gian hiệu lực, vị trí lưu giữ và quy tắc xoay khóa.

`keyId` chỉ là **nhãn tra cứu**, không phải bằng chứng danh tính hay bí mật. Nếu gói dữ liệu nói `keyId=server-prod`, bên nhận vẫn phải lấy khóa từ kho tin cậy và kiểm tra khóa đó có quyền dùng cho nghiệp vụ đang xét. Không cho phép phía không tin cậy tự chọn bất cứ khóa nào để qua kiểm tra.

Các nguyên tắc thực hành:
1. Sinh khóa bí mật bằng nguồn ngẫu nhiên mật mã phù hợp; `java.util.Random` không dành cho sinh khóa.
2. Giới hạn phân phối và quyền dùng khóa; ưu tiên keystore/KMS/HSM theo mức rủi ro, tránh đặt khóa trong source, URL hay log.
3. Tách khóa theo môi trường, tenant, mục đích và chiều truyền khi giao thức yêu cầu; dẫn xuất bằng KDF có nhãn/ngữ cảnh thích hợp.
4. Xoay và thu hồi khóa bằng quy trình đã định; dữ liệu cũ có thể cần khóa giải mã cũ trong thời gian giữ liệu. Thu hồi chứng chỉ/khóa ký ảnh hưởng đến việc tin cậy chữ ký và phiên phát sinh sau đó.
5. Xác định rõ hậu quả khi khóa bị lộ: khóa đối xứng lộ có thể ảnh hưởng bí mật và tính toàn vẹn của dữ liệu dùng nó; khóa ký lộ cho phép giả mạo chữ ký trong phạm vi tin cậy liên quan.

## 3. Thuật toán: mỗi loại giải quyết một bài toán khác nhau

| Nhóm | Tính chất chính | Điển hình | Điều không tự bảo đảm |
| --- | --- | --- | --- |
| Mã hóa xác thực (AEAD) | Bí mật dữ liệu + phát hiện sửa đổi ciphertext/AAD khi kiểm tra tag thành công | AES-GCM, ChaCha20-Poly1305 | Không tự nhận diện một con người nếu nhiều bên chia sẻ khóa; không tự chống phát lại |
| Chữ ký số | Kiểm tra dữ liệu gắn với khóa công khai tương ứng và không bị sửa sau khi ký | Ed25519, ECDSA, RSA-PSS | Không giữ bí mật nội dung; không tự chứng minh `pk` thuộc người có thẩm quyền |
| MAC | Toàn vẹn và xác thực giữa những bên chia sẻ bí mật | HMAC-SHA256 | Không công khai xác minh; khó quy trách nhiệm một bên khi nhiều người cùng biết khóa |
| Hash mật mã | Tạo digest có tính kháng va chạm/kháng tiền ảnh theo thiết kế | SHA-256, SHA-384 | Không xác thực trước đối thủ có thể sửa cả nội dung lẫn digest |
| KDF | Dẫn xuất khóa có ngữ cảnh và độ dài phù hợp | HKDF, PBKDF2 (trường hợp mật khẩu) | Không thay được entropy tốt của đầu vào |
| Trao đổi/thỏa thuận khóa | Tạo bí mật chung mà không gửi khóa phiên trực tiếp | (EC)DHE, cơ chế KEM phù hợp | Chưa xác thực đối tác nếu thiếu ràng buộc danh tính với transcript |

Ví dụ: hàm `SHA-256(message)` có thể phát hiện sự thay đổi khi digest được lấy từ **kênh tin cậy**. Nếu đối thủ thay được cả `message` và digest, hash thuần không chống được giả mạo. Muốn bảo vệ dữ liệu trước đối thủ chủ động phải chọn MAC/chữ ký hoặc AEAD tương ứng với mô hình khóa.

**Tên thuật toán phải đủ cụ thể.** “AES” chỉ xác định block cipher, chưa chỉ ra mode và quy tắc bảo vệ toàn vẹn. Trong Java, `Cipher.getInstance("AES/GCM/NoPadding")` thể hiện transformation cụ thể; `NoPadding` ở đây không có nghĩa là bỏ authentication tag. Cũng vậy, “RSA” chưa nói là ký RSA-PSS hay mã hóa RSA-OAEP; không sử dụng “mã hóa bằng private key” như một cách thay cho chữ ký số.

## 4. Tham số: những giá trị nhỏ có thể quyết định an toàn

Mỗi thuật toán có tập tham số được định nghĩa riêng. Không có một cấu hình “an toàn cho mọi thứ”.

| Trường hợp | Tham số cần hiểu | Ý nghĩa |
| --- | --- | --- |
| AES-GCM | Độ dài khóa 128/256 bit; nonce/IV, thường 96 bit; tag thường 128 bit; AAD | Giữ bí mật và kiểm tra tag. **Không lặp cặp (khóa, nonce) cho hai lần mã hóa** |
| HKDF | Hash, `salt`, `info`, độ dài đầu ra | Dẫn xuất khóa cho từng ngữ cảnh; `info` có thể tách ứng dụng, phiên, chiều truyền |
| Dẫn xuất từ mật khẩu | `salt` riêng, work factor/chi phí tính toán, hàm KDF | Làm tăng chi phí thử đoán và tránh cùng mật khẩu tạo cùng kết quả khi salt khác |
| Ed25519 | Thuật toán và định dạng khóa/chữ ký; chính sách xác thực khóa công khai | Họ thuật toán đã xác định đường cong/chế độ; không trộn nhầm với ECDSA |
| ECDSA / ECDH | Đường cong/nhóm được chấp nhận, ví dụ P-256 | Hai phía phải thống nhất nhóm hợp lệ; xác thực vẫn là bước riêng |
| RSA-PSS | Hàm hash, MGF, độ dài salt, tham số kiểm tra | Bên ký và xác minh phải thống nhất cấu hình |
| TLS 1.3 | Phiên bản, AEAD/HKDF hash suite, nhóm key exchange, thuật toán chữ ký, chính sách certificate | Thương lượng có kiểm tra, không để đối thủ ép chọn cấu hình không được phép |

Ba khái niệm dễ nhầm:

- **Nonce/IV:** giá trị dùng cho một lần mã hóa theo quy tắc của mode; thông thường không phải bí mật. Trong AES-GCM, bảo đảm tính duy nhất cho mỗi khóa là yêu cầu sống còn. Một nonce ngẫu nhiên 96 bit dùng được trong ví dụ nhỏ, nhưng hệ thống lưu lượng lớn/phân tán cần quản lý xác suất va chạm, giới hạn số lần dùng khóa và chiến lược cấp nonce thống nhất; có thể dùng bộ đếm được phân vùng đúng cách.
- **Salt:** thường là giá trị công khai làm đầu vào dẫn xuất/hashing, ví dụ tránh việc hai mật khẩu giống nhau tạo cùng hash khi dùng salt khác. Salt **không** thay thế khóa hoặc entropy đầu vào.
- **Tag:** kết quả xác thực (ví dụ GCM authentication tag); bên giải mã phải kiểm tra thành công trước khi tin và sử dụng plaintext. Không bỏ qua ngoại lệ xác thực.

**AAD (Additional Authenticated Data)** là dữ liệu không cần mã hóa nhưng cần bảo vệ tính toàn vẹn, chẳng hạn phiên bản envelope, loại thông điệp, tenantId hoặc resourceId. Bên mã hóa và giải mã phải dùng đúng cùng AAD. AAD không bảo mật giá trị trước người quan sát và không tự quyết định ai được phép truy cập.

Hãy suy nghĩ về một sự cố: hai request của hai tenant được mã hóa bằng cùng khóa; nếu định dạng chỉ chứa ciphertext và nonce, một ciphertext hợp lệ có thể bị chuyển sang ngữ cảnh tenant khác khi ứng dụng không gắn/kiểm tra tenant ở tầng giao thức. Đặt định danh ngữ cảnh vào AAD **và** kiểm tra quyền nghiệp vụ giúp ngăn sự nhầm lẫn này. Không coi một trường client tự khai là danh tính đáng tin.

## 5. Giao thức: kết hợp phép toán thành lời bảo đảm có thể kiểm chứng

Một giao thức định nghĩa **vai trò, trình tự, định dạng, trạng thái, kiểm tra và xử lý lỗi**. Cùng AES-GCM và Ed25519 nhưng hai giao thức khác nhau có thể cho bảo đảm an ninh khác nhau.

Giao thức tối thiểu phải trả lời:
1. Ai khởi tạo? Ai là người gửi/người nhận? Danh tính mong đợi lấy từ cấu hình hoặc ngữ cảnh tin cậy nào?
2. Hai bên chọn thuật toán/phiên bản/tham số bằng quy tắc nào? Có danh sách cho phép và quy tắc từ chối thuật toán yếu/không rõ không?
3. Khóa đến từ đâu: khóa cấu hình, khóa tạm, KDF, trao đổi khóa hay KMS? Có gắn khóa với phiên, vai trò và đối tác không?
4. Những byte nào được mã hóa, ký hoặc đưa vào AAD? Dữ liệu có được mã hóa tuần tự (canonical encoding), phân định loại thông điệp và phiên bản rõ ràng không?
5. Đối tác kiểm tra tag/chữ ký/chứng chỉ/tên máy chủ và quyền sử dụng khi nào? Có từ chối mọi lỗi trước khi xử lý business logic không?
6. Có chống **replay**, **downgrade**, nhầm khóa/nhầm đối tác, thông điệp sai thứ tự và xử lý retry/idempotency không?

### 5.1. Ví dụ TLS 1.3: ràng buộc khóa, thuật toán, tham số và danh tính

Một kết nối TLS 1.3 dùng xác thực máy chủ bằng chứng chỉ thông thường có thể hình dung như sau:

```text
Client                                              Server
  |-- ClientHello: TLS version, suites, key_share --->|
  |<-- ServerHello: lựa chọn hợp lệ, key_share -------|
  |             thiết lập bí mật handshake           |
  |<-- Certificate, CertificateVerify, Finished ------|
  |  kiểm tra chain, SAN/hostname, chữ ký transcript   |
  |-- Finished --------------------------------------->|
  |<========== dữ liệu ứng dụng AEAD hai chiều ======>|
```

Đây là **sơ đồ đơn giản hóa** của đường xác thực bằng chứng chỉ, không phải toàn bộ các kiểu handshake TLS 1.3. TLS 1.3 còn hỗ trợ PSK và resumption; phía client có thể được xác thực bằng certificate khi cấu hình mTLS.

Vai trò của từng lớp:
- **Thuật toán/tham số:** các bên thương lượng AEAD, HKDF hash, key-share group và thuật toán chữ ký theo quy tắc TLS 1.3. Cipher suite như `TLS_AES_128_GCM_SHA256` biểu thị AEAD và hash liên quan, **không tự quyết định** nhóm trao đổi khóa hay thuật toán chữ ký.
- **Khóa:** bí mật thu được từ key establishment/PSK được đưa qua key schedule, dẫn xuất các khóa handshake và application traffic có mục đích khác nhau. Khóa riêng dài hạn của server được dùng để chứng minh danh tính qua chữ ký khi dùng certificate; nó không được gửi qua mạng.
- **Giao thức:** transcript handshake và các thông điệp xác nhận liên kết việc chọn tham số, khóa và quá trình xác thực; một đối thủ không thể tùy ý thay đổi chúng mà vẫn qua các kiểm tra mật mã.
- **Danh tính:** client xác minh đường tin cậy của chứng chỉ **và** tên server mong đợi với SAN DNS/IP, cùng các quy tắc hiệu lực/chính sách áp dụng. Chỉ nhìn thấy ổ khóa hay nhận được một certificate bất kỳ không đủ để kết luận đã kết nối đúng server.

Kết nối HTTPS bảo vệ một **kênh vận chuyển** tới endpoint đã xác thực theo chính sách; không tự bảo đảm người dùng được quyền thao tác, bảo vệ dữ liệu sau khi TLS termination, hay ngăn ứng dụng phía server xử lý sai quyền.

### 5.2. AEAD không tự ngăn phát lại

Một bản tin có `ciphertext + tag` hợp lệ vẫn có thể là bản tin **cũ** được gửi lại. Tag xác minh tính toàn vẹn và bên sở hữu khóa, không mặc định xác minh tính mới của sự kiện. Giao thức ứng dụng cần `messageId`/sequence number/counter/timestamp+window hoặc token dùng một lần, kết hợp trạng thái kiểm tra, phù hợp với retry và idempotency. Bản thân các byte được kiểm tra toàn vẹn phải bao gồm ngữ cảnh dùng để chống replay.

## 6. Danh tính: từ “đúng khóa” đến “đúng thực thể được phép”

Xét hai câu hỏi khác nhau:

- **Cryptographic authentication:** bản tin/handshake có do bên giữ khóa phù hợp tạo ra không?
- **Identity binding:** khóa được tin là thuộc về dịch vụ/người dùng/thiết bị nào, và điều đó được xác minh dựa trên nguồn tin cậy nào?

Sau đó còn câu hỏi **authorization**: thực thể đã xác thực có quyền thực hiện thao tác cụ thể trên tài nguyên này không? Xác thực thành công không thay cho phân quyền.

### 6.1. Chứng chỉ số và bản đồ danh tính–khóa

Chứng chỉ X.509 chứa khóa công khai, các thuộc tính nhận dạng (ví dụ `subjectAltName`), thời hạn và ràng buộc sử dụng; chữ ký của CA hỗ trợ kiểm tra ràng buộc ấy theo chuỗi tin cậy. Khi xác thực HTTPS, thông thường phải kiểm tra chain đến trust anchor phù hợp, hostname/SAN, validity và các chính sách sử dụng khóa/chứng chỉ có liên quan; kiểm tra thu hồi tùy chính sách và cấu hình của hệ thống. Một chứng chỉ tự ký không mặc nhiên được tin; nó chỉ phù hợp nếu được tin cậy/ghim bằng quy trình riêng đã thiết lập.

Một certificate hợp lệ cho `api.example.com` không đồng nghĩa mọi lời gọi từ server đó đều có quyền quản trị cơ sở dữ liệu. Certificate và danh tính kết nối là **đầu vào** cho chính sách phân quyền, không phải chính sách phân quyền.

Ví dụ ràng buộc:
- `service-account/orders-prod` → một hoặc nhiều khóa/certificate được registry đáng tin cấp/quản lý.
- `api.example.com` → certificate có SAN phù hợp và chain đến CA được tin; client đã có **tên mong đợi** từ URL/cấu hình.
- `user:alice` → được ứng dụng xác thực qua cơ chế danh tính (session/OIDC, v.v.) và ánh xạ vào quyền; không tự gán user chỉ từ keyId do client gửi.

Trong thực tế, một danh tính có thể thay khóa khi rotation; một khóa có thể phục vụ một scope hạn chế; khóa đã thu hồi hoặc hết hạn phải được xử lý theo chính sách của thời điểm xác minh.

### 6.2. Vì sao “verify(signature) = true” vẫn có thể bị lừa?

Đối thủ tạo cặp khóa riêng của họ, ký lệnh `transfer 100` và gửi cả chữ ký lẫn khóa công khai do họ tạo. Hàm verify đương nhiên trả `true`. Nếu server dùng khóa công khai vừa nhận làm nguồn duy nhất để quyết định người ký là giám đốc tài chính, hệ thống đã mắc **identity/key substitution**.

Cách đúng: lấy khóa/certificate từ registry, trust store hoặc quy trình xác thực đã được kiểm tra; xác định chủ thể được phép ký loại lệnh đó; bảo đảm chữ ký bao phủ chính xác nội dung và ngữ cảnh (phiên bản, loại lệnh, tài khoản, tenant, nonce/requestId) trước khi thực thi.

**Chữ ký không mã hóa thông điệp.** Chữ ký hợp lệ còn không mặc nhiên tạo ra “chối bỏ không thể” trong mọi bối cảnh pháp lý/vận hành: điều đó phụ thuộc việc bảo vệ khóa, chính sách định danh và chứng cứ hệ thống.

## 7. Bài toán xuyên suốt: gửi lệnh thanh toán giữa hai dịch vụ

Giả sử `orders-service` gửi `payment-service` yêu cầu thanh toán. Mục tiêu là: không lộ số liệu trên đường truyền, không bị sửa người nhận/số tiền, không chấp nhận request lặp và chỉ cho đúng dịch vụ/tenant gọi API.

Một thiết kế có thể gồm các lớp sau:

1. **Danh tính kết nối:** client đặt URL máy chủ mong đợi; dùng TLS 1.3/HTTPS với certificate verification. Nếu áp dụng mTLS, payment-service còn xác thực danh tính client dựa trên certificate và ánh xạ sang service principal.
2. **Quyền ứng dụng:** xác thực access token hoặc cơ chế service authorization theo chính sách; kiểm tra issuer, audience, thời gian hiệu lực, quyền và tenant; không coi mTLS hoặc token hợp lệ là quyền tuyệt đối trên mọi khoản thanh toán.
3. **Giao thức nghiệp vụ:** định nghĩa body và định dạng chính xác, `requestId` duy nhất, version và TTL. Server lưu/truy vấn idempotency key để xử lý retry an toàn và từ chối lệnh phát lại trái chính sách.
4. **Mã hóa bổ sung nếu cần:** nếu dữ liệu phải được bảo vệ vượt qua TLS termination, mã hóa AEAD ở tầng thông điệp; khóa chỉ tới được endpoint ứng dụng mong muốn, bao gồm `version|tenantId|requestId|messageType` trong AAD được kiểm tra.
5. **Xác nhận provenance nếu cần:** ký canonical representation của lệnh bằng khóa ký đã gắn với orders-service. Payment-service kiểm tra chữ ký bằng khóa đã đăng ký đáng tin, rồi kiểm tra quyền của principal trước khi xử lý.
6. **Vòng đời:** rotate key và certificate, giám sát lỗi xác thực, quản lý thời gian và lưu log audit phù hợp; không log bí mật, plaintext nhạy cảm hoặc private key.

Ví dụ envelope cho dữ liệu mã hóa ứng dụng (chỉ minh họa format, không phải tiêu chuẩn giao thức):

```json
{
  "version": 1,
  "algorithm": "AES-128-GCM",
  "keyId": "orders-data-v3",
  "nonce": "<base64-12-byte-nonce>",
  "aad": {
    "tenantId": "t-17",
    "messageType": "payment-request",
    "requestId": "r-204"
  },
  "ciphertextAndTag": "<base64-data>"
}
```

Trong thiết kế thực tế, cần quy định **serialization chuẩn** của AAD (thứ tự trường, encoding UTF-8, độ dài/phân cách, version), thuật toán cho phép cố định ở cấu hình đáng tin, nguồn dữ liệu mà server dùng xác định tenant/request, cách từ chối giá trị không hợp lệ và quản lý keyId. Không tin `algorithm` hoặc `keyId` chỉ vì client khai báo trong JSON. Việc chứa AAD rõ ràng trong envelope hỗ trợ kiểm tra tính toàn vẹn, nhưng không làm AAD trở thành bí mật.

## 8. Java 17+: chữ ký hợp lệ vẫn có thể đến từ khóa không đáng tin

Ví dụ chạy độc lập này mô phỏng hai cặp khóa Ed25519: một public key đã được bên nhận **tin cậy cấu hình trước**, và một cặp khóa **do người gửi không đáng tin tự sinh**. Kẻ tấn công ký chính nội dung bằng khóa của họ; bên nhận phải xác minh bằng **khóa của danh tính mong đợi**, không bằng public key tùy ý gửi kèm request.

Lưu thành `IdentityBindingDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class IdentityBindingDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair trusted = generator.generateKeyPair();
        KeyPair attacker = generator.generateKeyPair();
        byte[] request =
                "pay:100".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(attacker.getPrivate());
        signer.update(request);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(attacker.getPublic());
        verifier.update(request);
        System.out.println("Untrusted key verifies own signature: "
                + verifier.verify(signature));

        verifier.initVerify(trusted.getPublic());
        verifier.update(request);
        System.out.println("Trusted key verifies attacker signature: "
                + verifier.verify(signature));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac --release 17 IdentityBindingDemo.java
java IdentityBindingDemo
```

Kết quả khi chạy với provider Ed25519 chuẩn:

```text
Untrusted key verifies own signature: true
Trusted key verifies attacker signature: false
```

**Vì sao hai dòng khác nhau?** Phép toán chữ ký đúng với khóa của attacker, nhưng **khóa đó không thuộc danh tính mà ứng dụng dự định tin cậy**. Đây là lỗi nhầm khóa/danh tính (`key substitution`), không phải lỗi toán học Ed25519. Trong sản phẩm thực, bên nhận lấy public key từ registry/chứng chỉ được tin cậy, gắn với sender, tenant, purpose và trạng thái thu hồi. Còn phải kiểm tra rằng signer được **phân quyền** ký đúng loại lệnh và bytes của lệnh bao gồm thông tin ngữ cảnh cần xác thực.

Mô phỏng tạo cả hai key trong RAM, không có certificate/PKI và không chứng minh danh tính ngoài đời. Nó **chỉ chứng minh** vì sao `Signature.verify` không đủ để cấp quyền giao dịch.

## 9. Thêm tham số và giao thức để buộc quyền vào bản tin

Với lệnh thanh toán `tenant=t-17, requestId=r-204, pay=100`, đừng chỉ ký chuỗi `pay=100` rồi xem kết quả là chấp nhận toàn bộ thao tác. Một hợp đồng thông điệp có thể yêu cầu:

1. **Khóa và identity:** lookup `keyId` trong registry đáng tin, xác minh khóa thuộc `orders-service`, còn hiệu lực và được phép ký lệnh của tenant này.
2. **Thuật toán và tham số:** khóa ký/verify dùng cùng thuật toán và cấu hình được allowlist; với dữ liệu mã hóa AEAD, thống nhất khóa, nonce duy nhất, tag và AAD version/tenant/requestId.
3. **Giao thức:** quy định chính xác bytes được ký, dạng canonical encoding, message type, hạn hiệu lực, requestId và kiểm tra chống replay.
4. **Thực thi:** chỉ sau verification và authorization mới chạy nghiệp vụ; sử dụng idempotency key để không cộng tiền hai lần khi có retry.

Tách **xác minh phép toán** (`verify == true`, tag hợp lệ) khỏi **đánh giá ngữ cảnh** (đúng khóa, đúng người, đúng tenant, đúng thời điểm và quyền). Đó là đóng góp chính của quan hệ khóa–thuật toán–tham số–giao thức–danh tính.

## 10. Những lỗi thiết kế phổ biến nhìn qua năm thành phần

| Hiện tượng | Thành phần bị thiếu hoặc gắn sai | Hậu quả và hướng xử lý |
| --- | --- | --- |
| Dùng AES-ECB vì “AES mạnh” | Thuật toán/mode | Lộ mẫu dữ liệu, thiếu xác thực; dùng AEAD theo nhu cầu bảo mật |
| Dùng lại nonce GCM với cùng khóa | Tham số + quản lý khóa | Có thể phá bảo mật nghiêm trọng; quản lý nonce unique, giới hạn dùng khóa |
| Dùng SHA-256 thuần để “ký” dữ liệu | Thuật toán | Đối thủ sửa cả dữ liệu và hash; dùng MAC/chữ ký theo mô hình tin cậy |
| Verify chữ ký với public key do request tự gửi | Danh tính + trust | Xác minh chữ ký của kẻ tấn công; tra khóa từ nguồn tin cậy và kiểm tra quyền |
| Tắt hostname verification/TrustManager luôn tin | Danh tính + giao thức | TLS mã hóa tới sai đối tác; bật xác minh chain và endpoint identity |
| Chỉ kiểm tra tag AEAD, không kiểm tra messageId | Giao thức/trạng thái | Replay hợp lệ; thêm freshness, sequence và idempotency |
| Tin `keyId` hoặc `alg` do client cung cấp không hạn chế | Giao thức + cấu hình | Chọn nhầm khóa/thuật toán hoặc algorithm confusion; áp allowlist và binding |
| Dùng chung một khóa cho nhiều mục đích không cách ly | Khóa + KDF | Tăng phạm vi sự cố và nhầm ngữ cảnh; tách khóa/ngữ cảnh, kiểm soát usage |
| Xác thực user thành công nhưng không kiểm tra quyền tài nguyên | Danh tính + phân quyền | Truy cập chéo tenant/IDOR; kiểm tra authorization từng yêu cầu |
| Chấp nhận plaintext dù xác thực thất bại | Giao thức + xử lý lỗi | Đưa dữ liệu chưa đáng tin vào nghiệp vụ; fail closed trước khi xử lý |
| Ký JSON nhưng mỗi bên serialize khác nhau | Giao thức + encoding | Verify thất bại hoặc tạo ambiguity; chuẩn hóa byte representation, version |

Các lỗi này lý giải vì sao **chỉ thay AES-128 bằng AES-256** không thể tự sửa thiết kế thiếu xác thực, sai nonce hay sai danh tính.

## 11. Quy trình thiết kế và tự kiểm tra

Khi đọc hoặc xây một tính năng bảo mật, lần lượt trả lời:

1. **Mục tiêu:** cần confidentiality, integrity, peer authentication, freshness, authorization và audit đến mức nào? Đối thủ có thể đọc/chặn/sửa/phát lại thông điệp hoặc kiểm soát client không?
2. **Định danh:** ai được phép là sender/receiver? Expected identity lấy từ cấu hình đáng tin hay dữ liệu client tự khai? Cơ chế trust anchor/key registry là gì?
3. **Khóa:** sinh/trao đổi/dẫn xuất tại đâu, ai có quyền dùng, scope nào, cách lưu và rotate/revoke? Có tách khóa theo mục đích và session không?
4. **Thuật toán và tham số:** chọn primitive cho đúng mục tiêu; mode, hash, nonce, tag, salt, curve, KDF context và size được ràng buộc/kiểm tra ra sao?
5. **Giao thức:** định nghĩa version, role, canonical encoding, trình tự handshake/bản tin, AAD, signature scope, timeout, failure handling, chống downgrade và replay.
6. **Ủy quyền:** sau khi chứng minh danh tính, có kiểm tra tenant/resource/operation được phép tại đúng thời điểm không?
7. **Vận hành:** có theo dõi lỗi xác thực, vòng đời khóa, số lần dùng nonce, thu hồi danh tính, tương thích phiên bản và migration mà không làm giảm kiểm tra an ninh không?
8. **Kiểm thử:** thử sai khóa, sai nonce, sai tag, sai AAD, sai public key, certificate sai hostname/CA, message sửa đổi, replay, downgrade, chéo tenant và người dùng thiếu quyền. Các trường hợp phải bị từ chối theo chính sách.

### Câu hỏi kiểm tra nhanh

**Câu 1.** Alice và Bob chia sẻ cùng khóa AES-GCM. Bob giải mã thành công và kiểm tra tag đúng. Bob có bằng chứng mật mã rằng *chính Alice*, chứ không phải người khác cũng nắm khóa, đã gửi không?

**Trả lời:** Không. Tag cho biết bản tin phù hợp với khóa đối xứng và tham số đã kiểm tra. Nếu nhiều bên giữ khóa, không phân biệt duy nhất ai đã tạo bản tin; cần cơ chế nhận dạng và ràng buộc bổ sung.

**Câu 2.** Chữ ký Ed25519 `verify=true` với public key do request cung cấp có đủ để xác nhận “request của quản trị viên” không?

**Trả lời:** Không. Phải biết public key đó được gắn với quản trị viên bởi nguồn tin cậy nào và còn hiệu lực/quyền ký hay không; nếu không, đối thủ có thể tự tạo khóa và chữ ký.

**Câu 3.** Nonce và AAD đều có thể gửi công khai. Vì sao cần chúng?

**Trả lời:** Nonce cho phép tạo lần mã hóa khác nhau và, với GCM, không được lặp cặp khóa–nonce; AAD ràng buộc dữ liệu ngữ cảnh vào phép kiểm tra tag mà không mã hóa chúng. Cả hai là tham số an ninh, không cần giữ bí mật.

**Câu 4.** Kênh TLS đã bảo vệ request; có còn cần phân quyền và idempotency không?

**Trả lời:** Có. TLS bảo vệ kênh và xác thực endpoint theo chính sách TLS; quyền trên đơn hàng và xử lý request lặp thuộc giao thức/nghiệp vụ ứng dụng.

**Câu 5.** Khi rotate certificate TLS, khóa AES mã hóa dữ liệu lịch sử có bắt buộc thay theo không?

**Trả lời:** Không nhất thiết. Khóa xác thực TLS, traffic keys và khóa dữ liệu lưu trữ có mục đích/vòng đời khác nhau. Việc rotate được quyết định theo chính sách, mức độ sự cố và phạm vi sử dụng của từng khóa.

## 12. Tóm tắt mối quan hệ

**Thuật toán** xác định phép toán mật mã; **khóa** cấp năng lực mật mã cho bên nắm giữ; **tham số** xác định cách phép toán được dùng cho từng thông điệp; **giao thức** định nghĩa các bước tạo, thương lượng, kiểm tra và xử lý kết quả; **danh tính** gắn kết khóa và phiên với thực thể được tin cậy, còn **authorization** quyết định thực thể ấy được làm gì.

Một kết quả mật mã chỉ có ý nghĩa bảo mật trong **ngữ cảnh đã được kiểm tra**. Câu hỏi quan trọng nhất không phải “chúng ta đang dùng thuật toán nào?” mà là: **“Đúng khóa của ai, với tham số nào, trong giao thức nào, để chứng minh điều gì cho đúng đối tác và đúng hành động?”**

### Tham khảo chính thức

- RFC 8446 — TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446
- RFC 5869 — HKDF: https://www.rfc-editor.org/rfc/rfc5869
- NIST SP 800-38D — GCM/GMAC và yêu cầu IV: https://csrc.nist.gov/pubs/sp/800/38/d/final
- Java Cryptography Architecture (JCA), Java SE 17: https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html
