# 5.4 Sinh, bảo quản và tách khóa HMAC theo mục đích sử dụng

**HMAC (Hash-based Message Authentication Code)** cho phép các bên cùng biết một **khóa bí mật** tạo và xác minh mã xác thực cho thông điệp. Với `HmacSHA256`, kết quả đầy đủ thường là **32 byte (256 bit)**, nhưng mức độ an toàn phụ thuộc rất lớn vào **cách sinh khóa**, **ai được giữ khóa**, **khóa được dùng cho việc gì**, và **cách xoay vòng, thu hồi khóa**. Tạo HMAC đúng thuật toán nhưng dùng chung một khóa cho webhook, session và API nội bộ có thể khiến một sự cố nhỏ lan rộng thành nhiều sự cố.

Mục tiêu của bài: tạo khóa có entropy đủ mạnh; lưu và cấp phát khóa đúng ranh giới tin cậy; hiểu hai cách **tách khóa độc lập** hoặc **dẫn xuất khóa theo mục đích (key derivation/domain separation)**; và quản lý vòng đời từ phát hành đến thu hồi. Ví dụ dùng Java 17+ và JCA/JCE.

## 1. Nhận diện đúng vai trò của khóa HMAC

HMAC sử dụng hàm băm mật mã cùng một khóa bí mật. Với ký hiệu:

```text
tag = HMAC(key, message)
valid = constant_time_compare(received_tag, HMAC(key, received_message))
```

- **Người tạo tag** biết khóa bí mật; **người kiểm tra tag** cũng phải biết khóa bí mật, hoặc dùng dịch vụ mật mã được ủy quyền để kiểm tra.
- Nếu thông điệp đổi mà tag giữ nguyên, phép xác minh sẽ thất bại với xác suất áp đảo khi HMAC được sử dụng đúng cách.
- **HMAC không mã hóa**: thông điệp và các header được xác thực vẫn có thể đọc được. Khi cần bí mật trên đường truyền, sử dụng TLS; khi cần bảo vệ dữ liệu lưu trữ, dùng giải pháp mã hóa phù hợp.
- **HMAC không tự chống replay**: một cặp `message + tag` hợp lệ bị gửi lại vẫn có thể hợp lệ. Giao thức cần timestamp, nonce, sequence, idempotency hoặc cơ chế từ chối phát lại nếu có yêu cầu.
- **HMAC không chứng minh duy nhất một người đã ký**: tất cả bên cùng giữ khóa đều có khả năng tạo tag. Nó là xác thực dựa vào *shared secret*, không cung cấp tính không thể chối bỏ như chữ ký số trong mô hình khóa và danh tính được quản lý đúng.
- HMAC không quyết định **phân quyền**; một webhook có tag hợp lệ vẫn cần được kiểm tra loại sự kiện, nguồn/tenant, quyền nghiệp vụ và trạng thái xử lý.

### 1.1. Key size khác MAC length

Với `HmacSHA256`, tag đầy đủ có **256 bit = 32 byte**. Độ dài khóa là đại lượng riêng. Khóa có thể dài hơn hoặc ngắn hơn 32 byte tùy giao thức và nguồn entropy. Với **khóa bí mật tạo ngẫu nhiên**, **32 byte (256 bit)** là lựa chọn thực hành rõ ràng và thường phù hợp cho HmacSHA256; đây không phải quy tắc “HMAC-SHA256 bắt buộc khóa đúng 32 byte”.

Bên trong HMAC, khóa dài hơn block size của hash được xử lý theo cấu trúc HMAC, không làm tag SHA-256 dài hơn 32 byte. Không suy ra “khóa dài 512 bit thì MAC mạnh 512 bit”; giới hạn bảo mật còn phụ thuộc hàm băm, độ dài tag, mô hình tấn công, quản lý khóa và giao thức.

| Thành phần | Ví dụ | Có bí mật không? |
| --- | --- | --- |
| **HMAC key** | 32 byte từ bộ sinh ngẫu nhiên mật mã | **Có**; ai có khóa có thể tạo tag |
| **Message** | Body, path, timestamp, nonce | Thường không; phụ thuộc dữ liệu và TLS |
| **MAC/tag** | 32 byte đầu ra HmacSHA256 | Không cần giữ bí mật, nhưng phải bảo đảm gắn đúng message/ngữ cảnh |
| **Key ID (`kid`)** | `webhook-prod-v2` | Thường công khai; chỉ là định danh để tìm khóa, không phải bằng chứng tin cậy |
| **Key version** | `v1`, `v2` | Metadata không bí mật; giúp xoay khóa |
| **Purpose/context** | `session`, `webhook-inbound` | Không cần bí mật; dùng để ràng buộc và phân tách |
| **HKDF salt** | Chuỗi byte ngẫu nhiên có thể lưu công khai | Không cần bí mật; phải khôi phục đúng khi dẫn xuất lại |

## 2. Sinh khóa HMAC an toàn

### 2.1. Sinh từ CSPRNG, không sinh từ dữ liệu dễ đoán

Khóa HMAC phải khó đoán với đối thủ, kể cả khi biết thuật toán, nhiều message và tag đã được công bố. Java có `SecureRandom` là giao diện sinh ngẫu nhiên mật mã; một khóa mới 32 byte có thể tạo như sau:

```java
byte[] key = new byte[32];
new java.security.SecureRandom().nextBytes(key);
```

Đây là *đoạn minh họa* để nói rõ kích thước, chưa phải chương trình độc lập. Trong code thật cần đưa khóa vào kho an toàn ngay sau khi tạo, quản lý người giữ và bảo đảm có thể khôi phục khi còn phải xác minh các thông điệp đã phát hành.

Có thể dùng `KeyGenerator` của provider nếu hỗ trợ thuật toán khóa HMAC phù hợp; khi đó chú ý tham số kích thước khóa tính bằng **bit**, không phải byte. `SecretKeySpec(key, "HmacSHA256")` chỉ **đóng gói mảng byte có sẵn**, không tự tạo entropy hay biến password yếu thành khóa mạnh.

**Tránh các nguồn khóa sau:**

- `new Random()`, `Math.random()`, thời gian hệ thống, số thứ tự, tên người dùng hoặc định danh đoán được.
- Một chuỗi người dùng tự nhập rồi gọi `getBytes(UTF_8)`. Số byte dài không bảo đảm entropy tương ứng.
- Khóa hardcode trong Java, YAML, Docker image, biến CI được in ra log hoặc nằm trong lịch sử Git.
- Khóa dùng chung được sao chép từ môi trường development sang staging/production.
- Dùng kết quả `SHA-256(password)` trực tiếp làm khóa HMAC như thể password đã có entropy 256 bit.

Nếu buộc phải lấy bí mật từ mật khẩu con người, hãy xét thiết kế **password KDF** có salt và chi phí phù hợp (ví dụ Argon2id/scrypt/PBKDF2, tùy hệ sinh thái và chính sách), thay vì tạo khóa dài bằng cách thêm ký tự, hash nhanh hoặc dùng Base64. Trong hệ thống service-to-service, ưu tiên tạo và quản lý khóa **ngẫu nhiên thật**, không cần đi qua mật khẩu.

### 2.2. Không nhầm entropy, encoding và chiều dài

- 32 byte từ `SecureRandom` dùng đúng cách mang xấp xỉ **256 bit entropy**; 32 byte của chuỗi `"aaaaaaaa..."` có entropy rất thấp.
- `Base64`, hex hoặc PEM chỉ **đổi biểu diễn byte**, không làm khóa an toàn hơn. 32 byte nhị phân có thể hiện thành 44 ký tự Base64 chuẩn, nhưng vẫn là một khóa 32 byte cần giữ bí mật.
- Không in raw key hoặc chuỗi Base64 của key để kiểm thử. Chỉ cần log **key ID, thuật toán, version, trạng thái**, và các thông tin vận hành không chứa khóa.
- Một khóa HMAC **khác** một nonce/IV hoặc salt; việc nonce/salt có thể công khai không cho phép công khai HMAC key.

### 2.3. Ai được tạo và cấp phát khóa?

Chọn rõ **chủ sở hữu khóa** và đường cấp phát:

1. Tốt nhất, hệ thống quản lý khóa/secret tạo hoặc nhập khóa bằng kênh có kiểm soát, cấp quyền theo service/tenant/purpose và audit sử dụng.
2. Nếu chương trình phải tạo khóa, dùng CSPRNG, đưa khóa ngay vào cơ chế lưu an toàn, gắn metadata; không tự in ra terminal, gửi qua chat/email hay commit vào repo.
3. Khi hai hệ thống cần **cùng** khóa để xác minh HMAC (ví dụ sender và webhook receiver), chia sẻ qua quy trình provision/secret manager có quyền truy cập tối thiểu. Coi **cả hai đầu** là bên có thể tạo MAC, nên không thể dùng HMAC để phân biệt ai đã tạo nếu không có ràng buộc bổ sung.
4. Có thể dùng HSM/KMS có tính năng tạo/xác minh MAC để tránh đưa raw key vào tiến trình ứng dụng; cần kiểm tra API và thuật toán cụ thể của nhà cung cấp. **Không giả định mọi KMS đều hỗ trợ HMAC hoặc cùng một dạng `SecretKey`**.

## 3. Bảo quản khóa: bảo vệ bí mật và phạm vi truy cập

Khóa HMAC là tài sản nhạy cảm. Người biết khóa có thể giả mạo thông điệp trong mọi ngữ cảnh dùng chung khóa đó.

| Nơi/cách giữ | Đánh giá và lưu ý |
| --- | --- |
| **Secret manager/KMS/HSM** | Ưu tiên theo yêu cầu hệ thống; IAM tách quyền đọc/ghi/ký/xác minh, audit, rotation và bảo vệ khóa. Nếu có MAC API không xuất khóa, ứng dụng có thể không cần thấy raw key. |
| **Secret được ứng dụng nạp khi khởi động** | Chỉ cho workload identity cần thiết đọc; giới hạn file permissions/mount, tránh log, crash dump, thông báo lỗi và endpoint debug tiết lộ key. |
| **Biến môi trường** | Có thể dùng trong môi trường hạn chế nhưng biến môi trường không phải kho bí mật mặc định; hãy xét khả năng bị lộ qua tiến trình con, công cụ debug, log hoặc cấu hình triển khai. |
| **Cơ sở dữ liệu/bản sao lưu** | Nếu cần giữ key, mã hóa bằng khóa quản lý **riêng**, giới hạn truy cập và quản lý backup/restore; không lưu plaintext trong bản ghi dễ đọc. |
| **Mã nguồn, Dockerfile, `application.yml` được commit, tài liệu, ticket, chat** | **Không lưu khóa thực**. Lịch sử commit và bản sao có thể tồn tại cả sau khi xóa dòng. |

Các nguyên tắc chính:

- **Least privilege:** service chỉ cần xác minh MAC thì nên có quyền **verify** trên KMS nếu hạ tầng hỗ trợ tách quyền, thay vì mặc định được đọc raw key hoặc ký mọi message.
- **Tách môi trường:** development, test, staging, production có khóa độc lập. Cần chia tách theo tenant, đối tác, protocol hoặc service khi ranh giới tin cậy yêu cầu.
- **Kiểm soát vòng đời:** mỗi key có owner, purpose, algorithm, key ID, version, ngày kích hoạt/ngừng ký/ngừng xác minh, chính sách rotation/retention và quy trình thu hồi.
- **Không log hoặc phản hồi lỗi chứa khóa:** tránh `Arrays.toString(key)`, `HexFormat.of().formatHex(key)`, `Base64.getEncoder().encodeToString(key)` trong log. Tag cũng có thể cần quản lý dữ liệu/ẩn thông tin tùy nghiệp vụ, nhưng tag **không phải khóa**.
- **Chú ý bộ nhớ:** `Arrays.fill(key, (byte) 0)` có thể xóa một mảng byte tạm đang sở hữu, nhưng không bảo đảm xóa mọi bản sao trong `SecretKeySpec`, provider, heap dump, swap hoặc HSM. Không xem việc overwrite một mảng là cơ chế bảo vệ hoàn chỉnh.
- **Không có key hợp lệ thì từ chối xác minh (fail closed)**; không dùng khóa mặc định `"secret"`, không vô hiệu kiểm tra MAC, không fallback sang thuật toán yếu.

### 3.1. Khóa không xuất được và Java JCA/JCE

Trong Java, `SecretKey` là trừu tượng. Với khóa phần mềm, `getEncoded()` có thể trả byte; với khóa trong HSM/provider không xuất được, phương thức này có thể trả `null`. Một số provider yêu cầu chạy `Mac` qua provider tương ứng hoặc gọi MAC API riêng.

Do vậy kiến trúc **không nên phụ thuộc vào việc dump khóa ra byte** để xác minh “đúng 32 byte” trong sản phẩm. Cấu hình key size và chính sách quản lý ở điểm tạo khóa; code gọi HMAC qua một interface có thể triển khai bằng JCA hoặc KMS tùy hệ thống.

## 4. Tách khóa theo mục đích sử dụng (key separation)

### 4.1. Vì sao một “super HMAC secret” là nguy hiểm?

Giả sử một ứng dụng dùng một khóa cho:

- Ký session cookie (xác thực phiên);
- Xác minh webhook từ đối tác;
- Ký URL tải file;
- Xác minh tác vụ quản trị nội bộ.

Nếu khóa webhook bị lộ từ bên tích hợp, kẻ tấn công có thể tính HMAC cho các loại message khác. **Biết khóa = có khả năng tạo MAC ở mọi giao thức dùng khóa đó.** Một parser coi thông điệp có tag hợp lệ là “được tin” mà không kiểm tra scope sẽ mở đường cho tấn công chuyển ngữ cảnh (*cross-protocol confusion*).

Thiết kế tốt phải tách bí mật **và** tách cách diễn giải message. Ví dụ ranh giới:

| Mục đích | Định danh logic | Bên được phép sử dụng |
| --- | --- | --- |
| Session/cookie | `shop/prod/session/v3` | Service quản lý phiên |
| Inbound partner webhook | `shop/prod/webhook/partner-A/v2` | Gateway nhận webhook và bên đối tác tương ứng |
| URL có hạn | `shop/prod/download-link/v1` | Service phát và xác minh URL |
| Yêu cầu nội bộ | `shop/prod/internal-job/v4` | Service phụ trách tác vụ |

Không chỉ đổi **tên biến**; cần dùng **khóa khác** hoặc **khóa con được dẫn xuất độc lập**, chính sách cấp quyền theo mục đích và ràng buộc mục đích trong dữ liệu được MAC.

### 4.2. Cách A: sinh khóa ngẫu nhiên độc lập cho từng mục đích

Đơn giản nhất là sinh riêng:

```text
K_session     <- SecureRandom(32 bytes)
K_webhook     <- SecureRandom(32 bytes)
K_download    <- SecureRandom(32 bytes)
K_internal    <- SecureRandom(32 bytes)
```

Mỗi khóa được lưu, đánh nhãn, cấp phát và rotate riêng. Nếu lộ khóa của đối tác webhook, khóa session vẫn không tự bị suy ra. **Đây thường là cách dễ kiểm toán, cô lập sự cố và xoay khóa độc lập nhất** khi có cơ sở hạ tầng quản lý secret.

Nhược điểm là số khóa, bản sao và quyền cấp phát tăng theo số mục đích/tenant. Cần có registry/secret manager rõ ràng; tránh chuyển sang một khóa chung chỉ vì thấy nhiều entry.

### 4.3. Cách B: dẫn xuất khóa con từ một root secret bằng HKDF

Khi phải quản lý nhiều khóa có quan hệ từ một **root key entropy cao**, có thể dùng **HKDF-SHA256** (RFC 5869) để dẫn xuất các khóa con theo từng mục đích:

```text
root_secret  --HKDF-Extract(salt)--> PRK
PRK + info("shop|prod|session|v1") --> K_session (32 bytes)
PRK + info("shop|prod|webhook|v1") --> K_webhook (32 bytes)
PRK + info("shop|prod|download|v1")-> K_download (32 bytes)
```

Trong HKDF chuẩn:

- **IKM (input keying material):** secret đầu vào có entropy phù hợp. Ở đây là root ngẫu nhiên mạnh, **không** phải password người dùng chưa qua password KDF.
- **Salt:** giá trị thường ngẫu nhiên, có thể công khai, dùng trong pha `Extract` để tạo **PRK (pseudorandom key)**. Nếu muốn dẫn xuất lại cùng key sau restart, **giữ đúng salt** cùng metadata; đổi salt sẽ đổi khóa con. HKDF định nghĩa giá trị mặc định khi salt bị bỏ trống, nhưng nên thiết kế và ghi rõ lựa chọn.
- **Info:** chuỗi byte mô tả ngữ cảnh, mục đích và version, dùng trong pha `Expand`. Khác `info` dẫn tới các khóa con khác nhau dưới giả định an toàn của HKDF.
- **Length:** số **byte** đầu ra muốn tạo. Với HmacSHA256, một khóa con 32 byte tương ứng **256 bit**; HKDF Expand có giới hạn tổng độ dài không vượt **255 × HashLen** byte.
- **Root key có quyền lực bao trùm:** kẻ lộ root có thể dẫn xuất **mọi khóa con**. Tách bằng HKDF làm giảm việc tái dùng cùng khóa, nhưng **không đạt mức cô lập rủi ro root giống nhiều khóa ngẫu nhiên hoàn toàn độc lập**.

Thiết kế `info` nên ghi rõ **ứng dụng, môi trường, protocol, purpose, đối tác hoặc tenant nếu cần, thuật toán và version**. Các trường có thể do người dùng cung cấp phải được canonicalize và mã hóa không nhập nhằng, ví dụ TLV hoặc length-prefix; không ghép ngây thơ những chuỗi chứa delimiter để hai bộ tham số tạo cùng một `info`.

**Đừng tự “dẫn xuất khóa” bằng `SHA256(root || purpose)` hoặc bằng Base64 của root.** Hãy dùng một KDF đã được định nghĩa và kiểm chứng như HKDF theo đúng các bước và tham số của nó.

### 4.4. Tách khóa khác với thêm nhãn vào message

Có hai lớp phòng vệ khác nhau:

1. **Key separation:** `K_session != K_webhook`. Kẻ có khóa webhook không tự tính được MAC dùng khóa session.
2. **Domain separation của message:** ngay cả trong một phạm vi khóa, thêm dữ liệu có cấu trúc, không nhập nhằng như `protocol_version`, `purpose`, `tenant`, `operation` vào những byte được MAC, giúp ngăn tag của một loại thông điệp bị hiểu là loại khác.

Chỉ thêm `"session:"` vào trước message nhưng vẫn giữ **một shared secret chung có mặt ở mọi service** không cô lập được sự cố khi secret đó lộ. Ngược lại, dù dùng khóa độc lập, vẫn cần xác thực đầy đủ các trường có ý nghĩa nghiệp vụ.

Ví dụ metadata `purpose`, `tenant`, `environment` và `key_id` chỉ là **thông tin tham chiếu**, không phải bằng chứng tự xác minh; **server phải áp chính sách ràng buộc chúng với khóa và request**.

## 5. Thiết kế giao thức MAC và xác minh phù hợp

Một giao thức có thể dùng cấu trúc:

```text
version: 2
key_id: webhook-partner-A-v2
timestamp: 2026-10-31T12:00:00Z
nonce: 4f8b...     (giá trị ví dụ)
body: {"event":"payment.paid","id":"evt123"}
mac: <HMAC-SHA256 của biểu diễn canonical đã xác định>
```

Các giá trị trên chỉ là mô hình minh họa, **không phải một request có MAC tính sẵn**. Để dùng thật phải định nghĩa chính xác byte được ký (phương thức, path/query, timestamp, nonce, body, context) và quy tắc canonicalization. Nếu các byte có ý nghĩa bảo mật không được MAC thì kẻ tấn công có thể thay chúng mà tag không đổi.

Quy trình server hợp lý:

1. **Xác định giao thức và purpose tin cậy từ route/cấu hình**, không cho client tự khai purpose để được chọn một key scope có quyền rộng hơn.
2. Giới hạn định dạng/độ dài của `key_id`; tra key trong registry **đúng tenant + purpose + environment + trạng thái**. `key_id` là selector do client gửi nên phải coi là dữ liệu không tin cậy, không phải đường dẫn file, URL hay chỉ thị tải secret tùy ý.
3. Chỉ dùng **thuật toán do server quy định** (ví dụ HmacSHA256); không chấp nhận `alg=none` hay thuật toán khác dựa vào header không tin cậy.
4. Kiểm tra timestamp trong cửa sổ hợp lệ, nonce/idempotency chưa dùng và những giới hạn phù hợp **nếu giao thức yêu cầu chống replay**.
5. Tạo lại **chính xác các byte** đã ký, tính HMAC bằng khóa tương ứng, kiểm tra tag độ dài chuẩn và so sánh bằng phương pháp tránh tiết lộ thời gian phụ thuộc nội dung, ví dụ `MessageDigest.isEqual(byte[], byte[])` trong Java khi đã biết tag đúng độ dài.
6. Chỉ sau khi MAC hợp lệ mới xử lý nghiệp vụ, nhưng còn phải kiểm tra authorization, tenant, loại sự kiện và điều kiện trạng thái. Cơ chế replay phải được cập nhật theo cách nguyên tử nếu cần chống nhận hai request đồng thời.

**Lưu ý canonicalization:** chữ hoa/thường trong header, thứ tự query parameter, encoding UTF-8, ký tự xuống dòng, khoảng trắng JSON, chuẩn hóa Unicode và raw body có thể dẫn đến hai byte stream khác nhau. Trong webhook, nếu đối tác ký **raw HTTP body**, receiver phải dùng đúng byte raw đã nhận theo đặc tả, **không parse rồi serialize JSON lại** trước khi tính HMAC.

**So sánh tag:** tag đầy đủ HmacSHA256 dài 32 byte. Nếu giao thức cho phép truncate tag, phải có thông số độ dài rõ ràng, giới hạn phù hợp, kiểm tra độ dài và tính đúng chuỗi byte. Không tự cắt tag tùy tiện để “tiết kiệm băng thông”.

## 6. Vòng đời khóa: tạo, dùng, rotate, thu hồi, hủy

Khóa HMAC thường tồn tại lâu hơn một instance Java. Muốn thay khóa không làm hỏng request còn hiệu lực, cần **key ring có version** và trạng thái riêng cho ký mới/xác minh cũ.

| Giai đoạn | Đối tượng thực hiện | Quy tắc |
| --- | --- | --- |
| **Generate** | Quản lý khóa | Sinh khóa ngẫu nhiên mới, định danh, owner, purpose, thuật toán, thời gian; không tái sử dụng secret cũ |
| **Store/provision** | Secret manager/KMS | Mã hóa/giữ trong HSM khi phù hợp; cấp quyền tối thiểu cho workload và đối tác |
| **Active signing** | Bên tạo MAC | Chỉ **một version hiện hành cho việc ký mới** tại mỗi phạm vi cần thống nhất |
| **Verify overlap** | Bên xác minh | Có thể nhận **key mới và key cũ** trong cửa sổ chuyển tiếp giới hạn, mỗi key chỉ dùng đúng purpose/scope |
| **Retire** | Quản lý khóa | Ngừng ký bằng key cũ; ngừng verify khi message hợp lệ cũ đã hết hạn/được xử lý |
| **Revoke/compromise** | Incident response | Nếu lộ khóa, thu hồi nhanh, đánh giá dữ liệu đã được ký giả, không chờ hết thời hạn rotation định kỳ |
| **Destroy** | Quản lý khóa/backup | Xóa/crypto-shred theo chính sách, xét cả phiên bản trong backup và cache; ghi lại việc hủy mà không log secret |

### 6.1. Ví dụ rotation có `kid`

Giả sử service đang dùng `key_id=webhook-v1` rồi phát hành `webhook-v2`:

- **Chuẩn bị:** tạo secret v2 độc lập, cập nhật receiver để biết v2 trước khi sender chuyển sang ký v2.
- **Chuyển đổi:** sender bắt đầu phát `kid=v2` và HMAC bằng key v2. Receiver kiểm tra v2; tạm tiếp tục kiểm tra v1 cho thông điệp phát hành trước hạn chót.
- **Kết thúc:** sau cửa sổ hợp lệ và độ trễ phân phối, tắt verify v1, thu hồi quyền truy cập, dọn các cache/backup theo chính sách.
- **Nếu bị lộ v1:** thay khóa và **thu hồi ngay theo quy trình xử lý sự cố**, không mặc định giữ “overlap” chỉ để tránh lỗi khách hàng. Có thể cần hủy các session/token đã ký bằng v1 và thông báo bên liên quan.

**Không thử tất cả khóa, tất cả purpose và mọi tenant để “tìm MAC đúng”** khi request đã khai báo key ID rõ ràng. Điều đó làm rộng khả năng chấp nhận ngoài policy và khó kiểm soát thời hạn. Lookup đúng scope, kiểm tra trạng thái, rồi verify.

### 6.2. Vòng đời root key khi dùng HKDF

Rotation root tạo một tập khóa con mới (kể cả khi `info` giữ nguyên), do đó:

- Lưu **root key version + salt + cấu trúc info + thuật toán KDF + output length** như một phần thông tin không thể thiếu cho việc dẫn xuất lại.
- Thay root theo kế hoạch ở tầng quản lý khóa, phân phối dần khóa con mới; key ID phải cho phép xác định version thích hợp.
- Một root bị lộ đồng nghĩa các khóa con dẫn xuất từ nó có thể bị lộ; cần lập kế hoạch thay **toàn bộ miền khóa con** bị ảnh hưởng.
- Không chia sẻ raw root cho mọi microservice chỉ để chúng tự sinh subkey. Nếu có thể, chỉ phát subkey đúng scope hoặc cho gọi API derivation/MAC được giới hạn quyền.
- Không dùng lại raw root để trực tiếp HMAC message nghiệp vụ: root chỉ dành cho KDF theo thiết kế đó.

## 7. Java 17+: tạo khóa HMAC độc lập và ràng buộc purpose

Chương trình độc lập dưới đây tạo **hai khóa 32 byte ngẫu nhiên độc lập** cho `session` và `webhook`. Phần prefix `demo:v1|purpose|` bổ sung domain separation trong bytes được MAC; demo chỉ dùng hai purpose cố định do code tin cậy chọn. Trong hệ thống thật cần encoding không nhập nhằng và chính sách xác định scope tại server.

Lưu đúng tên **HmacPurposeDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class HmacPurposeDemo {
    static byte[] generateKey() {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        return key;
    }

    static byte[] tag(byte[] key, String purpose, String payload) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        mac.update(("demo:v1|" + purpose + "|").getBytes(StandardCharsets.UTF_8));
        return mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
    }

    static boolean verify(byte[] key, String purpose, String payload,
                          byte[] expected) throws Exception {
        return expected != null && expected.length == 32
                && MessageDigest.isEqual(expected, tag(key, purpose, payload));
    }

    public static void main(String[] args) throws Exception {
        byte[] sessionKey = generateKey();
        byte[] webhookKey = generateKey();
        String payload = "user=alice";
        byte[] sessionTag = tag(sessionKey, "session", payload);

        System.out.println("session key bytes: " + sessionKey.length);
        System.out.println("session tag bytes: " + sessionTag.length);
        System.out.println("correct purpose: "
                + verify(sessionKey, "session", payload, sessionTag));
        System.out.println("wrong purpose: "
                + verify(sessionKey, "webhook", payload, sessionTag));
        System.out.println("wrong key: "
                + verify(webhookKey, "session", payload, sessionTag));
        System.out.println("tampered payload: "
                + verify(sessionKey, "session", "user=bob", sessionTag));

        Arrays.fill(sessionKey, (byte) 0);
        Arrays.fill(webhookKey, (byte) 0);
    }
}
```

Biên dịch, chạy:

```bash
javac -encoding UTF-8 HmacPurposeDemo.java
java HmacPurposeDemo
```

Stdout kỳ vọng (khóa ngẫu nhiên mỗi lần khác nhau nhưng các kết luận giữ nguyên trong thực hành):

```text
session key bytes: 32
session tag bytes: 32
correct purpose: true
wrong purpose: false
wrong key: false
tampered payload: false
```

**Giải thích:**

- `new SecureRandom().nextBytes(key)` tạo một mảng 32 byte khóa mới; chương trình không in raw key.
- `tag()` dùng `Mac.getInstance("HmacSHA256")` và `SecretKeySpec`. Tạo instance `Mac` riêng cho phép tính; `Mac` có trạng thái và **không nên chia một instance mutable cho nhiều thread mà không có cơ chế điều phối**.
- Kiểm tra `wrong purpose` dùng **cùng** session key nhưng dữ liệu purpose khác trong input của HMAC; `wrong key` dùng **khóa khác**; cả hai cho thấy hai lớp bảo vệ không nên lẫn lộn.
- `MessageDigest.isEqual` so sánh hai byte array của tag sau khi đã xác minh độ dài dự kiến. Đừng dùng `new String(tag)` hoặc phép so sánh có hành vi phụ thuộc nội dung để xác minh tag.
- `Arrays.fill` chỉ là dọn mảng tạm ở mức tốt nhất, **không bảo đảm xóa toàn bộ bản sao** mà provider/JVM có thể giữ. Code demo **không cất giữ key qua restart**, không quản lý rotation/key ID và không thực hiện xác thực session thực tế.

Đối với ứng dụng lớn, `generateKey()` thường là trách nhiệm của hệ thống quản lý khóa, còn logic nghiệp vụ chỉ nhận quyền thao tác HMAC phù hợp.

## 8. Java 17+: dẫn xuất khóa theo purpose bằng HKDF-SHA256

Ví dụ sau triển khai đầy đủ **HKDF-Extract + HKDF-Expand** với HmacSHA256 theo RFC 5869 để minh họa. Đầu tiên kiểm tra **RFC 5869 test vector case 1** bằng giá trị công khai; sau đó tạo root và salt ngẫu nhiên, dẫn xuất hai khóa 32 byte từ hai `info` khác nhau. Ví dụ không in root, PRK hay subkey.

Lưu **HkdfPurposeDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class HkdfPurposeDemo {
    static final int HASH_LEN = 32;

    static byte[] hmac(byte[] key, byte[]... inputs)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        for (byte[] input : inputs) mac.update(input);
        return mac.doFinal();
    }

    static byte[] extract(byte[] salt, byte[] ikm)
            throws GeneralSecurityException {
        return hmac(salt == null || salt.length == 0
                ? new byte[HASH_LEN] : salt, ikm);
    }

    static byte[] expand(byte[] prk, byte[] info, int length)
            throws GeneralSecurityException {
        if (length < 1 || length > 255 * HASH_LEN)
            throw new IllegalArgumentException("invalid length");

        byte[] output = new byte[length];
        byte[] previous = new byte[0];
        int offset = 0;
        for (int counter = 1; offset < length; counter++) {
            previous = hmac(prk, previous, info, new byte[]{(byte) counter});
            int count = Math.min(HASH_LEN, length - offset);
            System.arraycopy(previous, 0, output, offset, count);
            offset += count;
        }
        Arrays.fill(previous, (byte) 0);
        return output;
    }

    static byte[] context(String purpose) {
        return ("app=shop|env=prod|alg=HmacSHA256|purpose="
                + purpose + "|version=1").getBytes(StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        byte[] ikm = new byte[22];
        Arrays.fill(ikm, (byte) 0x0b);
        byte[] salt = HexFormat.of().parseHex("000102030405060708090a0b0c");
        byte[] info = HexFormat.of().parseHex("f0f1f2f3f4f5f6f7f8f9");
        byte[] okm = expand(extract(salt, ikm), info, 42);

        String expected =
                "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c"
              + "5db02d56ecc4c5bf34007208d5b887185865";
        System.out.println("RFC 5869 case 1 valid: "
                + expected.equals(HexFormat.of().formatHex(okm)));

        byte[] root = new byte[32];
        byte[] appSalt = new byte[32];
        new SecureRandom().nextBytes(root);
        new SecureRandom().nextBytes(appSalt);
        byte[] prk = extract(appSalt, root);
        byte[] sessionKey = expand(prk, context("session"), 32);
        byte[] webhookKey = expand(prk, context("webhook"), 32);

        System.out.println("derived key bytes: " + sessionKey.length);
        System.out.println("same purpose stable: "
                + MessageDigest.isEqual(sessionKey,
                        expand(prk, context("session"), 32)));
        System.out.println("other purpose differs: "
                + !MessageDigest.isEqual(sessionKey, webhookKey));

        Arrays.fill(root, (byte) 0);
        Arrays.fill(prk, (byte) 0);
        Arrays.fill(sessionKey, (byte) 0);
        Arrays.fill(webhookKey, (byte) 0);
    }
}
```

Biên dịch, chạy:

```bash
javac -encoding UTF-8 HkdfPurposeDemo.java
java HkdfPurposeDemo
```

Stdout:

```text
RFC 5869 case 1 valid: true
derived key bytes: 32
same purpose stable: true
other purpose differs: true
```

**Phân tích kết quả:**

1. Test vector xác nhận rằng ví dụ dùng đúng thứ tự `HKDF-Extract(salt, IKM)` và `HKDF-Expand(PRK, info, L)`, trong đó mỗi khối Expand phụ thuộc khối trước, `info` và counter 1 byte. Giá trị kỳ vọng công khai từ RFC 5869 không phải khóa sản xuất.
2. Khóa con cho `session` và `webhook` đều 32 byte nhưng khác nhau do `info` khác nhau. Nếu cùng root, salt, info và length, HKDF tất định: dẫn xuất lại cho cùng kết quả.
3. Root và salt được tạo ngẫu nhiên khi chương trình chạy; một ứng dụng thật cần lưu/khôi phục **root và salt cùng version** theo thiết kế, nếu không các key sinh ra lần sau sẽ khác.
4. Ví dụ chỉ cho purpose cố định do code chọn. Với hệ thống đa tenant/đối tác, phải chuẩn hóa và mã hóa `info` không nhập nhằng, kiểm tra nguồn tin cậy của từng thuộc tính và quyền truy cập. **Không dùng `purpose` hay `tenant` tự khai để mở quyền ký/xác minh.**
5. Để dùng trong sản phẩm, ưu tiên thư viện hoặc dịch vụ mật mã đã kiểm định triển khai HKDF; ví dụ này nhằm giúp hiểu cấu trúc RFC và đo đúng kết quả. Việc xóa mảng tạm trong demo chỉ là best effort, không biến Java heap thành vùng bí mật được bảo đảm.

## 9. Tình huống thiết kế thực tế

### 9.1. Webhook từ hai đối tác khác nhau

Nếu Partner A và Partner B đều gửi `payment.paid`, tạo khóa `partner-A/prod/webhook/v1` và `partner-B/prod/webhook/v1` riêng biệt. Khi request đến, map đối tác qua endpoint/cấu hình và chọn key đúng scope. Một tag hợp lệ từ A **không** được dùng để xác thực message có tư cách B.

Nếu đối tác kiểm tra HMAC chung với server, cả hai nắm secret. Khi cần xác nhận nguồn theo danh tính không chia sẻ, cân nhắc chữ ký số hoặc cơ chế xác thực dịch vụ phù hợp thay vì cho rằng HMAC tự cung cấp non-repudiation.

### 9.2. Session và signed download URL

Một service ký cookie phiên, một service khác ký URL tải tài liệu. Hai purpose có chính sách khác nhau: cookie thuộc phiên đăng nhập; URL phải chứa hạn dùng, tài nguyên, hành động và có thể giới hạn người nhận. Dùng **khóa riêng** để không biến việc lộ khóa signed URL thành khả năng giả mạo session. Không cấp `K_session` cho service chỉ cần kiểm tra URL.

### 9.3. Nhiều tenant và microservice

Nếu mỗi tenant cần biên giới tin cậy riêng, cân nhắc **per-tenant keys** do secret manager giữ hoặc HKDF với context chuẩn hóa có tenant ID và purpose. Phải xét rõ ai có quyền root: tách theo HKDF **không** giảm ảnh hưởng của việc root bị chiếm toàn bộ. Khi yêu cầu cô lập chặt, dùng khóa độc lập và giới hạn IAM theo tenant.

### 9.4. Thay key v1 giữa lúc message còn hợp lệ

Cho phép receiver giữ v1 ở chế độ **verify-only** trong thời hạn tối đa đã thiết kế; sender chỉ phát v2. Gắn `kid` vào envelope và xác minh nó trong scope. Sau hạn, xóa v1 khỏi danh sách cho phép. Nếu v1 đã bị lộ, phải đánh giá **thu hồi ngay** và vô hiệu hóa message còn hiệu lực thay vì ưu tiên tương thích.

### 9.5. Phát hiện khóa nằm trong Git hoặc log

Không chỉ “xóa dòng” là đủ. Coi secret đã bị lộ: phát khóa mới, cập nhật bên sử dụng, thu hồi key cũ, điều tra phạm vi ký giả và lưu dấu audit. Dọn log/backup/history theo khả năng và chính sách, kiểm tra secret scanning/CI để ngăn tái diễn.

## 10. Lỗi thường gặp và cách sửa

| Lỗi | Rủi ro | Cách đúng |
| --- | --- | --- |
| Hardcode `"changeit"` làm HMAC key | Người có mã nguồn có thể giả MAC | Sinh khóa ngẫu nhiên đủ mạnh và giữ trong hệ thống secret |
| Dùng `Random`/timestamp/password làm khóa | Dễ đoán, entropy thấp | `SecureRandom`/KMS; nếu buộc dùng password, xử lý bằng password KDF phù hợp |
| Dùng một key cho session, webhook, URL | Lộ một hệ thống ảnh hưởng nhiều mục đích | Khóa độc lập hoặc HKDF theo purpose, ranh giới IAM rõ |
| Chỉ đổi tên biến `SESSION_KEY`/`WEBHOOK_KEY` nhưng bytes giống nhau | Chưa tách bí mật | Thực sự phát khóa khác hoặc dẫn xuất subkey với info khác |
| Dùng hex/Base64 để “giấu” secret | Encoding có thể giải mã tức thì | Quản lý access, encryption at rest/secret manager, tránh log |
| Đặt root HKDF trong tất cả microservice | Mỗi service có quyền suy ra mọi subkey | Chỉ phát key đúng scope, giữ root trong khu vực tin cậy |
| `SHA256(root \|\| purpose)` tự chế | KDF không có thiết kế và kiểm định rõ | Dùng HKDF theo RFC, context không nhập nhằng |
| Cho client chọn `alg`/`kid`/purpose tùy ý | Confusion/downgrade/secret lookup sai | Server cố định thuật toán, tra kid trong scope đáng tin và kiểm tra trạng thái |
| Ký JSON đã serialize nhưng verify JSON serialize lại khác | HMAC không khớp dù cùng ý nghĩa | Đặc tả byte canonical; webhook raw body thì xác minh raw body |
| Verify mọi version key vô thời hạn | Key cũ tiếp tục là điểm yếu | Cửa sổ overlap giới hạn, retire/revoke theo sự kiện |
| Cho rằng HMAC chặn replay | Request cũ vẫn có tag hợp lệ | Timestamp, nonce/sequence, TTL và replay cache/logic nguyên tử |
| `Arrays.fill` là đảm bảo không còn key ở RAM | JVM/provider có thể giữ bản sao | Giảm thời gian/phạm vi giữ key, hạn chế dump, ưu tiên non-exportable key |
| In key để debug lỗi xác minh | Tiết lộ khóa thực | Log `kid`/version/correlation ID, không log secret |
| Dùng cùng key giữa test và production | Rò môi trường thấp ảnh hưởng production | Mỗi môi trường có secret riêng, chính sách IAM riêng |

## 11. Checklist review trước khi triển khai HMAC

1. **Tạo khóa:** khóa sinh bằng CSPRNG/KMS? Độ dài và entropy có phù hợp? Có dùng secret mẫu, password hoặc khóa hardcode không?
2. **Ownership:** xác định service/đối tác/tenant, người quản trị và mục đích duy nhất của từng key chưa? Cấp quyền least privilege chưa?
3. **Lưu trữ:** key được bảo quản/backup/restore an toàn, không lọt vào source control, log, heap dump hoặc diagnostic output ngoài ý muốn?
4. **Tách miền:** dùng key độc lập hoặc HKDF theo context rõ ràng? Tránh chia sẻ root và tránh scope quá rộng?
5. **Thông điệp:** quy tắc byte canonical rõ chưa? Có MAC đầy đủ các trường bảo mật và cố định thuật toán không?
6. **Xác minh:** chọn key đúng purpose + tenant + version, kiểm tra tag dài đúng, so sánh an toàn, từ chối key không hợp lệ và xác minh thất bại?
7. **Replay và quyền:** có chống replay và kiểm tra authorization nghiệp vụ độc lập với HMAC không?
8. **Rotation:** có `kid`, keyring, lộ trình active/verify-only/retired, phương án khẩn cấp khi key bị lộ và thời điểm dọn v1 không?
9. **Vận hành:** có secret scanning, log không lộ key, audit quyền và kiểm thử sai key/sai purpose/sai message/cũ hạn không?

## 12. Bài tập tự kiểm tra

**Câu 1.** Hai hệ thống dùng cùng khóa 32 byte HmacSHA256 nhưng khác tên biến. Đã tách khóa chưa?  
**Trả lời:** **Chưa.** Đổi tên không thay đổi vật liệu khóa; cần khóa bí mật độc lập hoặc derivation theo purpose khác nhau.

**Câu 2.** Key HmacSHA256 được sinh bằng `SecureRandom` dài 32 byte. Tag đầy đủ có nhất thiết dài 32 byte vì key dài 32 byte không?  
**Trả lời:** Tag đầy đủ dài **32 byte do HmacSHA256**, không phải vì key tình cờ dài 32 byte.

**Câu 3.** Client gửi `kid="admin-prod"`. Server có nên tự động đọc secret và kiểm tra bằng khóa admin?  
**Trả lời:** **Không.** `kid` là dữ liệu không tin cậy; phải giới hạn lookup vào purpose, tenant, môi trường và key trạng thái hợp lệ do server xác định.

**Câu 4.** Ứng dụng lưu riêng khóa dẫn xuất `K_webhook`, không có root. Có thể từ đó suy ra `K_session` nếu HKDF được dùng đúng không?  
**Trả lời:** Trong mô hình mật mã dự kiến, **không thể thực tế suy ra** khóa khác từ một subkey. Nhưng **lộ root** cho phép dẫn xuất tất cả subkey, nên root cần mức bảo vệ cao hơn.

**Câu 5.** Một webhook có tag đúng nhưng timestamp cũ và nonce đã được xử lý. Nhận lại hay từ chối?  
**Trả lời:** **Từ chối** theo chính sách chống replay; MAC hợp lệ không đủ để chấp nhận lại nghiệp vụ.

**Câu 6.** Khi rotate root HKDF, giữ nguyên `info` nhưng dùng root mới. Các subkey có giống bản cũ không?  
**Trả lời:** **Không**, HKDF cho kết quả phụ thuộc root/PRK, salt, info và length. Cần quản lý version và cửa sổ chuyển đổi.

**Câu 7.** Một secret 32 byte được in thành Base64 để đưa vào log. Có an toàn vì người đọc không thấy byte gốc không?  
**Trả lời:** **Không.** Base64 có thể decode trực tiếp thành đúng 32 byte khóa. Log đã làm lộ secret.

**Câu 8.** HMAC hợp lệ từ Partner A chứng minh chắc chắn cá nhân Alice ở Partner A đã ký chưa?  
**Trả lời:** **Không.** Mọi người/hệ thống biết shared key đều có thể tạo MAC; muốn gắn danh tính cụ thể cần cơ chế khóa và xác thực thích hợp.

### Ghi nhớ

**Sinh khóa bằng nguồn ngẫu nhiên mật mã, giữ khóa trong phạm vi quyền tối thiểu, tách khóa thật sự theo mục đích, ràng buộc ngữ cảnh trong những byte được MAC, quản lý key ID và phiên bản, và có quy trình rotate/thu hồi.** HMAC-SHA256 là một primitive hữu ích; toàn bộ quy trình quản lý khóa và xác minh mới quyết định liệu ứng dụng có thực sự chống giả mạo thông điệp hay không.
