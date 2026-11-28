# Derived key: khóa dẫn xuất là gì, được tạo ra và quản lý như thế nào?

## 1. Derived key trong phân loại khóa mật mã

**Derived key (khóa dẫn xuất)** là khóa mật mã được tạo ra từ một hoặc nhiều đầu vào bằng một **hàm dẫn xuất khóa (Key Derivation Function, KDF)**. Đầu vào có thể là vật liệu khóa bí mật có độ ngẫu nhiên cao, bí mật chung từ giao thức thỏa thuận khóa hoặc mật khẩu do con người tạo, nhưng **mỗi loại đầu vào cần cơ chế KDF thích hợp**.

Ví dụ, một ứng dụng truyền dữ liệu an toàn đã có bí mật chung từ thỏa thuận khóa X25519. Nó cần hai khóa khác nhau: một khóa dùng để mã hóa dữ liệu theo chiều client → server và một khóa cho chiều server → client. Sử dụng trực tiếp cùng một chuỗi byte làm cả hai khóa sẽ gây khó khăn cho việc phân tách mục đích và giới hạn rủi ro. KDF cho phép dẫn xuất hai khóa với **nhãn ngữ cảnh riêng biệt**, bảo đảm các bên tham gia cùng tính ra kết quả dự kiến khi có cùng đầu vào và quy tắc.

~~~text
Bí mật đầu vào (IKM)
        |
        v
KDF + salt + ngữ cảnh / nhãn mục đích
        |
        +--> Derived key A: mã hóa client → server
        |
        +--> Derived key B: mã hóa server → client
        |
        +--> Derived key C: xác thực thông điệp
~~~

Một derived key **vẫn là khóa bí mật nếu mục đích sử dụng đòi hỏi bí mật**. Việc nó được tính ra thay vì được sinh ngẫu nhiên trực tiếp không khiến nó an toàn hơn trước việc lộ khóa, truy cập trái phép hoặc dùng sai thuật toán. Vì vậy derived key nằm trong chủ đề **phân loại key** nhưng phải được quản lý trong toàn bộ vòng đời khóa: tạo, cấp phát, lưu, sử dụng, rotation, thu hồi, hủy và kiểm toán.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **derived key**, **DEK**, **KEK**, khóa gốc và khóa phiên.
2. Giải thích vai trò của **IKM, salt, context/info, output length, key ID và phiên bản KDF**.
3. Lựa chọn đúng giữa **HKDF**, KDF từ mật khẩu như **Argon2id, scrypt hoặc PBKDF2**, và KDF theo giao thức.
4. Phân tích **domain separation** (tách miền mục đích), entropy và các rủi ro khi cùng một đầu vào sinh nhiều khóa.
5. Thiết kế vòng đời khóa dẫn xuất gắn với **KMS/HSM, envelope encryption, IAM và audit**.
6. Hiểu ví dụ Java triển khai HKDF-SHA256 để tạo các khóa độc lập theo mục đích.

## 2. Derived key khác DEK, KEK và khóa gốc ở điểm nào?

Một khóa có thể được phân loại **theo nguồn gốc** và **theo vai trò**. Hai chiều phân loại này không loại trừ nhau.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Derived key** | Khóa được **hình thành bằng cách nào**? | Khóa 256 bit được dẫn xuất bằng HKDF từ bí mật chung của phiên |
| **Randomly generated key** | Khóa có được sinh ngẫu nhiên trực tiếp không? | DEK AES-256 từ CSPRNG của KMS |
| **DEK (Data Encryption Key)** | Khóa được **dùng để làm gì**? | Khóa AES-GCM mã hóa nội dung hóa đơn |
| **KEK (Key Encryption Key)** | Khóa được **dùng để làm gì**? | Khóa bọc DEK trong envelope encryption |
| **Session/traffic key** | Khóa bảo vệ phiên hoặc lưu lượng nào? | Khóa mã hóa một chiều truyền trong TLS |
| **Root/master key** | Khóa giữ vai trò gì trong phân cấp? | Bí mật có kiểm soát dùng để dẫn xuất các khóa con |

**Một derived key hoàn toàn có thể đóng vai trò DEK, KEK hoặc session key.** Từ “derived” không chỉ ra quyền sử dụng hay thuật toán mã hóa; vai trò phải được định nghĩa rõ trong metadata và chính sách.

Ví dụ: một root secret có entropy cao được dùng với KDF để sinh khóa con của dịch vụ báo cáo. Khóa con có thể dùng làm KEK để bọc các DEK. Tuy nhiên, không phải mọi hệ thống nên xuất root secret cho ứng dụng: kiến trúc an toàn thường giữ khóa nhạy cảm trong **KMS/HSM** và sử dụng API dẫn xuất (nếu có) hoặc **GenerateDataKey / Wrap / Unwrap** thay thế.

### Hai thiết kế cùng sử dụng các khóa khác nhau

~~~mermaid
flowchart TB
    subgraph D["Dẫn xuất khóa"]
        R["Root secret entropy cao"] --> F["KDF + salt + info"]
        F --> A["Derived DEK cho phạm vi A"]
        F --> B["Derived key cho xác thực B"]
    end
    subgraph E["Envelope encryption"]
        K["KEK giữ trong KMS/HSM"] --> W["Wrap/Unwrap"]
        G["DEK ngẫu nhiên"] --> W
        W --> WD["Wrapped DEK lưu cùng bản mã"]
        G --> C["Mã hóa dữ liệu"]
    end
~~~

Hai cách có thể được kết hợp nhưng không đồng nghĩa. **Key derivation** tính khóa mới từ vật liệu bí mật đầu vào; **key wrapping** mã hóa một khóa đã có bằng khóa bảo vệ khóa. Việc dẫn xuất một KEK và việc dùng KEK ấy để wrap DEK là **hai thao tác riêng**.

## 3. Cơ chế dẫn xuất khóa: đầu vào và tính chất bảo mật

Một KDF chung có thể biểu diễn ở mức khái niệm như sau:

~~~text
derivedKey = KDF(secretInput, salt, context/info, outputLength, parameters)
~~~

Tùy họ KDF, không phải tất cả tham số trên đều hiện diện hoặc có cùng ý nghĩa.

| Thành phần | Ý nghĩa | Yêu cầu thực hành |
| --- | --- | --- |
| **IKM / secret input** | Vật liệu khóa đầu vào, có thể là bí mật ngẫu nhiên hoặc bí mật chung | Cần đủ entropy, không lộ và phù hợp với loại KDF |
| **Salt** | Giá trị bổ sung nhằm tách các lần dẫn xuất, chống việc dùng lại cùng điều kiện và hỗ trợ mục tiêu của KDF | Thường **không bí mật**; tạo và lưu theo chuẩn từng KDF; không nhầm với key |
| **Info / context / label** | Chỉ rõ mục đích, giao thức, môi trường, vai trò, tenant hoặc phiên bản | Có cấu trúc rõ, không nhập nhằng; nên ràng buộc vào danh tính/nghiệp vụ tin cậy |
| **Output length** | Số byte khóa cần xuất | Phù hợp thuật toán dùng khóa, ví dụ 32 byte cho AES-256 |
| **Parameters / version** | Họ KDF, hàm băm, số vòng, chi phí bộ nhớ, tham số thuật toán | Lưu phiên bản để có thể tái tạo khóa và di chuyển an toàn |

**Salt không thay thế entropy của secret input.** Nếu người dùng chọn mật khẩu “123456”, thêm một salt ngẫu nhiên không biến mật khẩu đó thành bí mật 256 bit. Ngược lại, với input mật mã mạnh, một KDF được thiết kế đúng có thể tạo đầu ra phù hợp để làm khóa cho một hay nhiều mục đích, trong giới hạn bảo mật của nó.

Một KDF có tính **xác định (deterministic)** với cùng đầu vào, salt và info: cùng tham số tạo cùng khóa. Tính này giúp hai phía của một giao thức tạo cùng khóa phiên và giúp hệ thống tái tạo khóa khi cần. Hậu quả là **đầu vào, salt/info và phiên bản phải được quản lý nhất quán**; thay một byte bất kỳ có thể tạo ra khóa khác, khiến bản mã cũ không giải được.

### 3.1. Không “tăng entropy” bằng cách chỉ băm nhiều lần

Giả sử root secret chỉ có 20 bit entropy thực tế. Việc băm nó bằng SHA-256 rồi lấy 32 byte đầu ra không tạo được bí mật 256 bit: kẻ tấn công vẫn có thể thử khoảng số trường hợp tương ứng với không gian đầu vào yếu. KDF có thể **trích xuất và phân phối độ ngẫu nhiên sẵn có** một cách phù hợp; nó không thể biến một mật khẩu dễ đoán thành bí mật mạnh tương đương khóa ngẫu nhiên.

Khi nguồn bí mật là mật khẩu, phải dùng loại **password-based KDF** chống thử đoán bằng chi phí tính toán/bộ nhớ và kết hợp các kiểm soát tài khoản. Khi nguồn đã là **key material ngẫu nhiên mạnh**, HKDF thường phù hợp hơn một KDF mật khẩu tốn chi phí.

### 3.2. Domain separation: cùng nguồn bí mật, các mục đích riêng biệt

Nếu dùng một khóa AES cho cả mã hóa dữ liệu và cho MAC, hoặc dùng cùng traffic key cho hai chiều mạng, mô hình bảo mật có thể bị phá bởi sự tương tác giữa các giao thức. **Domain separation** tạo miền đầu vào khác nhau để khóa con dùng cho mục đích A không trùng khóa con dùng cho B (ngoại trừ xác suất va chạm không đáng kể theo bảo đảm của KDF).

~~~text
HKDF-Expand(PRK, info="myapp/v1|invoice|encrypt", 32) --> key A
HKDF-Expand(PRK, info="myapp/v1|invoice|mac",     32) --> key B
HKDF-Expand(PRK, info="myapp/v1|audit|mac",       32) --> key C
~~~

Nhãn cần chỉ rõ **giao thức/ứng dụng, mục đích, vai trò, phiên bản và ngữ cảnh** khi phù hợp. Không ghép chuỗi bằng phép nối dễ nhập nhằng. Ví dụ “ab|c” và “a|bc” không nên vô tình biến thành cùng dãy byte; có thể dùng **length-prefix**, TLV hoặc một cấu trúc byte có quy ước chuẩn.

Tách mục đích không tự thay thế quyền truy cập. Nếu kẻ tấn công lấy được **root secret**, họ thường có thể dẫn xuất mọi khóa con mà họ biết salt và info; các giá trị đó thường không phải bí mật.

## 4. Những họ KDF quan trọng và thời điểm dùng

| Họ/cơ chế | Nguồn đầu vào điển hình | Đặc điểm và trường hợp sử dụng |
| --- | --- | --- |
| **HKDF (RFC 5869)** | Vật liệu mật mã có entropy đủ tốt: shared secret từ (EC)DH, root key ngẫu nhiên | Extract rồi Expand; hỗ trợ tách miền bằng info; dùng nhiều trong giao thức và dẫn xuất khóa con |
| **PBKDF2 (RFC 8018)** | Mật khẩu hoặc passphrase do người dùng nhập | Dùng PRF với iteration count và salt; tương thích rộng, có thể dùng khi phù hợp chính sách |
| **Argon2id (RFC 9106)** | Mật khẩu, bí mật có entropy thấp | KDF phụ thuộc bộ nhớ, có tham số thời gian/bộ nhớ/mức song song; thường được ưu tiên cho xử lý mật khẩu mới khi nền tảng hỗ trợ |
| **scrypt (RFC 7914)** | Mật khẩu | Có chi phí bộ nhớ và CPU điều chỉnh được; có ích ở nơi có hỗ trợ phù hợp |
| **KDF theo NIST SP 800-108** | Khóa bí mật cho mục đích dẫn xuất | Các chế độ KDF dựa trên PRF như HMAC hoặc CMAC, với nhãn và context |
| **KDF tích hợp trong giao thức** | Key schedule của TLS hoặc giao thức khác | Phải tuân thủ **toàn bộ đặc tả**, gồm nhãn, transcript, secret và chiều truyền |

Việc chọn KDF phải dựa vào **mô hình đe dọa, entropy đầu vào, mục đích, tiêu chuẩn và thư viện tin cậy**. Không tự thiết kế một “KDF” bằng cách nối password với timestamp rồi gọi SHA-256 một lần.

Cũng không nên lấy **cùng đầu vào và cùng context** cho nhiều giao thức mà không có phân tách miền. Ngay cả khi dùng cùng HMAC-SHA256 bên dưới, quy tắc tạo khóa của TLS hoặc một API KMS cụ thể có thể khác HKDF tự triển khai cho ứng dụng.

## 5. HKDF: Extract rồi Expand

HKDF được mô tả trong **RFC 5869** và có hai bước:

1. **Extract:** trích xuất một khóa giả ngẫu nhiên (PRK, *pseudorandom key*) từ IKM và salt.
2. **Expand:** mở rộng PRK thành vật liệu khóa đầu ra (OKM, *output keying material*) với info và độ dài đầu ra.

Với HKDF-SHA256:

~~~text
PRK = HMAC-SHA256(salt, IKM)                # Extract

T(0) = empty
T(1) = HMAC-SHA256(PRK, T(0) || info || 0x01)
T(2) = HMAC-SHA256(PRK, T(1) || info || 0x02)
...
OKM  = first L bytes of T(1) || T(2) || ...
~~~

Trong đó dấu **||** là phép nối byte, còn chỉ số block là byte đếm từ **1**. Với SHA-256, một PRK dài 32 byte, độ dài OKM theo RFC 5869 tối đa **255 × 32 = 8160 byte**. Khóa AES-256 cần **32 byte** nên chỉ cần một block đầu ra.

### 5.1. Ý nghĩa của salt

HKDF cho phép không cung cấp salt; khi đó RFC quy định giá trị mặc định gồm các byte 0 có độ dài bằng HashLen. Tuy nhiên, **nên dùng salt phù hợp nếu giao thức cho phép**, vì salt độc lập với IKM có thể nâng cao một số thuộc tính bảo mật của extract. Salt thường có thể lưu công khai cạnh metadata.

Khác với salt của password-based KDF, salt trong HKDF không được dùng để bù đắp việc secret input dễ đoán. Nên ưu tiên IKM có entropy cao đã được tạo hoặc thỏa thuận đúng chuẩn.

**Không coi salt là nonce của AES-GCM.** Salt tham gia quá trình tạo khóa; nonce tham gia một lần mã hóa cụ thể. Hai trường có quy tắc và nguy cơ dùng lại khác nhau. Dù mỗi bản ghi dùng derived key riêng, vẫn cần tuân thủ giới hạn nonce/IV của thuật toán mã hóa.

### 5.2. Ý nghĩa của info và độ dài đầu ra

**Info** chứa thông tin theo ngữ cảnh mà bên dẫn xuất muốn ràng buộc vào khóa. Nó có thể gồm:

- phiên bản giao thức/ứng dụng;
- mục đích như **encrypt**, **authentication**, **KEK**;
- chiều truyền **client-to-server** hoặc **server-to-client**;
- định danh tenant hoặc đối tượng đã được xác thực;
- key version hoặc một ID theo chính sách.

Info thông thường **không bí mật**, vì vậy không nên đặt mật khẩu, private key hoặc dữ liệu nhạy cảm vào nhãn/metadata. Nếu context được xây dựng từ input không đáng tin, bên dẫn xuất phải xác minh thông tin nghiệp vụ trước.

**Không dẫn xuất 32 byte rồi cắt tùy tiện làm nhiều khóa cùng mục đích** nếu không có kế hoạch phân chia theo chuẩn. Nếu một output dài được chia thành các khóa con, phải đảm bảo quy tắc phân đoạn và độ dài được thiết kế rõ; cách dễ kiểm soát hơn là **dùng info riêng** cho từng khóa.

## 6. Derived key từ mật khẩu: khác HKDF cho key material mạnh

Một password hoặc passphrase thường có entropy thấp và có thể bị thử đoán ngoại tuyến khi kẻ tấn công lấy được salt, bản mã hoặc giá trị xác minh. Vì vậy, với mật khẩu nên dùng **KDF được thiết kế để làm quá trình thử đoán tốn kém**, chẳng hạn **Argon2id**, **scrypt**, hoặc **PBKDF2** theo yêu cầu tương thích/chính sách.

~~~text
password + salt ngẫu nhiên + cost parameters
          |
          v
Password-based KDF
          |
          +--> Derived key (ví dụ cho cơ chế mã hóa phù hợp)
~~~

### 6.1. Salt và tham số có thể lưu công khai

Salt phải được tạo đúng quy chuẩn KDF, với giá trị riêng phù hợp để tránh những người dùng có cùng mật khẩu nhận cùng kết quả mà không cần thử lại. Cần lưu **tên thuật toán, phiên bản, salt, chi phí CPU/bộ nhớ, độ dài đầu ra** để có thể dẫn xuất lại hoặc xác minh.

Chi phí phải phù hợp ngân sách tài nguyên và khả năng chống brute force; kiểm thử trên hạ tầng thật và điều chỉnh khi chính sách an ninh thay đổi. Với thuật toán có chi phí bộ nhớ như Argon2id/scrypt, phải tính tới rủi ro **DoS** nếu cho phép tạo quá nhiều yêu cầu đồng thời.

### 6.2. Mã hóa từ mật khẩu và lưu mật khẩu đăng nhập là hai bài toán khác nhau

| Bài toán | Điều hệ thống cần | Lưu ý |
| --- | --- | --- |
| **Mã hóa tệp bằng passphrase** | Dẫn xuất khóa đối xứng để mã hóa rồi có thể dẫn xuất lại khi người dùng nhập passphrase | Dùng password-based KDF đủ chi phí, salt, AEAD; có kế hoạch mất passphrase |
| **Xác minh mật khẩu đăng nhập** | Kiểm tra mật khẩu mà **không cần khôi phục** mật khẩu gốc | Dùng lược đồ lưu mật khẩu một chiều chuyên dụng, thường Argon2id hoặc phương án phù hợp; lưu verifier/hash có tham số |
| **Dẫn xuất khóa phiên từ ECDH** | Tạo khóa giao thức từ bí mật chung mật mã | HKDF theo key schedule giao thức, không dùng PBKDF2 như giải pháp mặc định |
| **Dẫn xuất khóa con từ root secret 256 bit** | Phân tách khóa theo ứng dụng, mục đích và phiên bản | HKDF hoặc KDF theo chuẩn; bảo vệ root secret như khóa cấp cao |

**PBKDF2, Argon2id, scrypt và HKDF không phải những tên gọi có thể thay thế tùy ý.** Một KDF nhanh như HKDF không có thuộc tính làm chậm tấn công thử từ điển trên mật khẩu yếu. Một KDF mật khẩu có chi phí cao cũng không thay thế tính xác thực của giao thức thỏa thuận khóa.

Trong thiết kế dữ liệu nhiều tenant, nếu cần mã hóa lâu dài, thường nên ưu tiên **DEK ngẫu nhiên được bọc bằng KEK quản lý qua KMS** hơn là đặt khả năng giải mã toàn hệ thống lên một mật khẩu khó kiểm soát.

## 7. Derived key trong mật mã bất đối xứng và chữ ký số

### 7.1. Thỏa thuận khóa (EC)DH

Trong thỏa thuận khóa ECDH/X25519, hai bên dùng private key của mình và public key hợp lệ của phía kia theo thuật toán để tính **shared secret**. Thông thường, shared secret được đưa vào **KDF theo giao thức**; các khóa traffic thu được mới dùng cho mã hóa xác thực.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: Public key tạm thời client
    S->>C: Public key tạm thời server + bằng chứng xác thực
    Note over C,S: Xác thực peer và ràng buộc transcript theo giao thức
    C->>C: Shared secret từ private client + public server
    S->>S: Shared secret từ private server + public client
    C->>C: KDF(shared secret, transcript, labels) → traffic keys
    S->>S: KDF(shared secret, transcript, labels) → traffic keys
    Note over C,S: Dùng AEAD với traffic keys và nonce hợp lệ
~~~

Nếu không **xác thực public key/peer**, kẻ đứng giữa có thể tạo hai shared secret khác nhau với hai phía. Một KDF tốt **không tự ngăn man-in-the-middle**. Ngoài ra, key schedule của giao thức phải xử lý đầu vào bất thường/không hợp lệ theo đặc tả; không tự triển khai X25519, TLS hoặc handshake để thay thế thư viện đã được kiểm chứng.

### 7.2. Khóa ký số không nên bị hoán đổi vai trò

Public/private key dùng cho chữ ký số (ví dụ Ed25519) không được tự động coi là đầu vào cho một cơ chế ECDH hoặc wrapping. Mỗi khóa phải gắn với **algorithm, key usage, key version** và danh tính tin cậy tương ứng.

Nếu một hệ thống sử dụng KDF để tạo **seed của nhiều khóa ký**, cơ chế đó đòi hỏi thiết kế và chuẩn mật mã riêng. Không lấy derived key AES 32 byte rồi tùy ý coi đó là private key hợp lệ của mọi thuật toán. Các dạng khóa khác nhau có cấu trúc, điều kiện hợp lệ và yêu cầu bảo mật khác nhau.

## 8. Vòng đời quản lý derived key

Nguồn bí mật có thể nằm ở tầng cao, còn các derived key được sinh cho từng phiên, dịch vụ hoặc đối tượng. Việc quản lý **root/IKM và các khóa dẫn xuất** phải đồng bộ.

| Giai đoạn | Thực hành cần có | Nếu làm sai |
| --- | --- | --- |
| **Tạo/khởi tạo** | Chọn KDF theo entropy đầu vào, thuật toán, salt, info và độ dài; tạo root/IKM an toàn | Từ mật khẩu yếu vẫn sinh được khóa dễ đoán; hai vai trò vô tình dùng cùng khóa |
| **Cấp phát quyền** | Xác thực principal/workload trước khi cấp quyền dẫn xuất hoặc sử dụng khóa | Bị lạm dụng để dẫn xuất khóa của tenant khác hoặc mọi mục đích |
| **Lưu trữ** | Bảo vệ IKM/root; quyết định có lưu derived key hay tái tạo; lưu metadata công khai cần thiết | Mất salt/info/version không thể giải dữ liệu; log khóa ở dạng rõ |
| **Sử dụng** | Chỉ dùng khóa theo key usage, domain, cryptoperiod; nonce/IV và AAD theo chế độ mã hóa | Cross-protocol key reuse, nonce reuse, giải mã sai tenant |
| **Xoay vòng** | Thay root/IKM hoặc key schedule/version có kế hoạch; giữ đường đọc dữ liệu cũ | Dữ liệu lịch sử không còn tái tạo được khóa |
| **Thu hồi** | Vô hiệu hóa quyền dẫn xuất và sử dụng nguồn bí mật; đánh giá derived key đã cấp/cached | Bên bị chiếm vẫn giữ khóa con cũ hoặc vẫn dùng được root |
| **Hủy và khôi phục** | Kiểm kê dữ liệu/phụ thuộc/backup; xóa root hoặc khóa con đúng lúc; thử restore | Hủy root làm mất toàn bộ khóa con chưa sao lưu/rewrap; giữ lâu gây lộ rộng |

### 8.1. Derived key có cần lưu không?

Có hai mô hình phổ biến:

- **Tái dẫn xuất khi cần:** giữ IKM/root an toàn và lưu **salt, info, thuật toán, phiên bản**. Ưu điểm là không phải lưu mọi khóa con ở dạng rõ. Nhược điểm là lộ root có thể gây ảnh hưởng rộng và mất root có thể khiến không tạo lại được bất kỳ khóa nào.
- **Lưu derived key dưới dạng wrapped key:** dẫn xuất một lần trong ranh giới tin cậy, sau đó bọc bằng KEK để có thể truy cập độc lập với secret gốc. Khi đó phải quản lý cả key wrapping và bản sao của derived key.

Không mặc định cách thứ nhất luôn an toàn hơn. Ví dụ, việc yêu cầu ứng dụng Java cầm một **root secret dùng cho toàn bộ tenant** chỉ để tái dẫn xuất DEK có thể tạo điểm thất bại rất lớn. KMS/HSM, phân tách quyền và envelope encryption thường cho kiến trúc dễ kiểm soát hơn.

### 8.2. Rotation khi root hoặc KDF version thay đổi

Giả sử bản ghi A được mã hóa với:

~~~text
DEK-A = HKDF(root-v1, salt-A, info=("invoice", "tenant-42", "v1"), 32)
~~~

Sau rotation, bản ghi mới dùng **root-v2**. Bản ghi A **không tự đổi** sang root-v2. Để đọc lại A, hệ thống vẫn cần dữ liệu đầu vào của root-v1 hoặc phải **giải mã rồi mã hóa lại** dữ liệu bằng khóa mới. Nếu bản ghi chỉ lưu ciphertext mà quên salt, info hoặc version, khả năng khôi phục sẽ bị phá vỡ.

Các khái niệm khác nhau:

| Thao tác | Kết quả | Hạn chế |
| --- | --- | --- |
| **Đổi root/IKM** | Derived key mới sẽ khác khi dẫn xuất bằng root mới | Bản mã dùng derived key cũ vẫn cần đường giải mã cũ |
| **Đổi salt/info/KDF version** | Khóa được dẫn xuất khác dù root không đổi | Phải biết metadata cũ để giải mã dữ liệu lịch sử |
| **Rewrap derived key/DEK đã lưu** | Thay lớp bọc KEK, giữ nguyên key value | Không xóa nguy cơ nếu chính derived key đã bị lộ |
| **Re-encrypt dữ liệu với DEK mới** | Thay khóa bảo vệ nội dung và ciphertext | Cần triển khai an toàn, kiểm tra toàn vẹn và kế hoạch rollback/restore |
| **Hủy root** | Không thể dẫn xuất lại các khóa con chưa được giữ độc lập | Có thể gây mất dữ liệu hàng loạt |

**Lưu ý khi lộ root:** nếu kẻ tấn công đã sao chép root-v1 và salt/info công khai, họ có thể tự dẫn xuất các khóa con v1. Chuyển mọi yêu cầu mới sang root-v2 **không xóa được** bản sao cũ; cần đánh giá phạm vi và thường phải tái mã hóa dữ liệu nhạy cảm bị ảnh hưởng.

### 8.3. Không coi derived key là khóa có tính forward secrecy mặc định

Nếu tất cả khóa phiên đều được dẫn xuất từ **một root dài hạn** cùng các tham số công khai, việc root bị lộ về sau có thể cho phép tái tạo khóa của các phiên trước và giải dữ liệu đã lưu. **Forward secrecy** phụ thuộc vào thiết kế giao thức, nguồn bí mật tạm thời, việc hủy bí mật đó và các giả định bảo mật khác, không xuất hiện chỉ vì dùng HKDF.

## 9. Ví dụ Java 17+: dẫn xuất hai khóa khác mục đích bằng HKDF-SHA256

Ví dụ dưới đây tự minh họa công thức HKDF của **RFC 5869** bằng **JCA/JCE** có sẵn trong Java. Nó tạo một IKM ngẫu nhiên 32 byte, salt ngẫu nhiên 32 byte, sau đó dẫn xuất **AES-256 key** cho mã hóa hóa đơn và **HMAC key** cho xác thực sự kiện với hai nhãn riêng biệt.

**Giới hạn:** mã minh họa thuật toán và cách tách miền, không phải triển khai KMS/HSM. Trong production, nên dùng thư viện HKDF đáng tin cậy hoặc API dẫn xuất của hệ thống quản lý khóa khi được hỗ trợ; tránh mang root secret độ nhạy cao từ KMS/HSM ra JVM chỉ để gọi ví dụ này.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class DerivedKeyHkdfDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String HMAC = "HmacSHA256";
    private static final int HASH_LEN = 32; // SHA-256 output = 32 bytes

    public static void main(String[] args) throws Exception {
        // Chỉ cho demo: sinh ngẫu nhiên IKM tại chỗ.
        // Production có thể yêu cầu KMS/HSM quản lý root/IKM.
        byte[] ikm = new byte[32];
        byte[] salt = new byte[32];
        RANDOM.nextBytes(ikm);
        RANDOM.nextBytes(salt);

        byte[] prk = null;
        byte[] aesKey = null;
        byte[] authKey = null;
        try {
            // Bước 1: Extract.
            prk = extract(salt, ikm);

            // Bước 2: Expand với info có nhãn mục đích riêng.
            byte[] encryptInfo =
                encodeInfo("billing-v1", "invoice-aes-256-gcm", "tenant-42");
            byte[] authInfo =
                encodeInfo("billing-v1", "event-hmac-sha256", "tenant-42");

            aesKey = expand(prk, encryptInfo, 32);
            authKey = expand(prk, authInfo, 32);

            System.out.println("AES key length: " + aesKey.length);
            System.out.println("Auth key length: " + authKey.length);
            System.out.println("Different derived keys: "
                + !Arrays.equals(aesKey, authKey));

            // Không in nội dung key. Ở hệ thống thật, dùng aesKey
            // đúng thuật toán/chính sách và nonce AES-GCM hợp lệ.
        } finally {
            Arrays.fill(ikm, (byte) 0);
            if (prk != null) Arrays.fill(prk, (byte) 0);
            if (aesKey != null) Arrays.fill(aesKey, (byte) 0);
            if (authKey != null) Arrays.fill(authKey, (byte) 0);
        }

        // Salt là metadata công khai: nếu cần tái dẫn xuất,
        // phải lưu salt cùng KDF version và info.
    }

    // RFC 5869 HKDF-Extract(salt, IKM).
    // Ở ví dụ này salt luôn là 32 byte ngẫu nhiên.
    private static byte[] extract(byte[] salt, byte[] ikm)
            throws Exception {
        Mac mac = Mac.getInstance(HMAC);
        mac.init(new SecretKeySpec(salt, HMAC));
        return mac.doFinal(ikm);
    }

    // RFC 5869 HKDF-Expand(PRK, info, L).
    private static byte[] expand(byte[] prk, byte[] info, int length)
            throws Exception {
        if (length < 0 || length > 255 * HASH_LEN) {
            throw new IllegalArgumentException("Invalid HKDF length");
        }

        Mac mac = Mac.getInstance(HMAC);
        mac.init(new SecretKeySpec(prk, HMAC));

        byte[] output = new byte[length];
        byte[] previous = new byte[0]; // T(0) là chuỗi rỗng.
        int written = 0;
        int counter = 1;

        try {
            while (written < length) {
                mac.reset();
                mac.update(previous);
                mac.update(info);
                mac.update((byte) counter);
                byte[] next = mac.doFinal();

                Arrays.fill(previous, (byte) 0);
                previous = next;

                int n = Math.min(next.length, length - written);
                System.arraycopy(next, 0, output, written, n);
                written += n;
                counter++;
            }
            return output;
        } finally {
            Arrays.fill(previous, (byte) 0);
        }
    }

    // Length-prefix từng thành phần để tránh nhãn/context nhập nhằng.
    private static byte[] encodeInfo(
            String appVersion, String purpose, String tenant) {
        byte[] a = appVersion.getBytes(StandardCharsets.UTF_8);
        byte[] b = purpose.getBytes(StandardCharsets.UTF_8);
        byte[] c = tenant.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(12 + a.length + b.length + c.length)
            .putInt(a.length).put(a)
            .putInt(b.length).put(b)
            .putInt(c.length).put(c)
            .array();
    }
}
~~~

### 9.1. Giải thích vì sao mã hoạt động

1. **IKM là 32 byte ngẫu nhiên**, phù hợp với ví dụ HKDF trên vật liệu mật mã mạnh. Không thay IKM bằng chuỗi mật khẩu yếu.
2. **Extract** dùng HMAC-SHA256 với salt làm HMAC key để tạo PRK.
3. **Expand** tính liên tiếp T(1), T(2), ... với thông tin info và bộ đếm một byte; trả đúng số byte yêu cầu, tuân thủ giới hạn 255 block.
4. Hai giá trị **info** khác nhau tạo hai khóa riêng cho hai mục đích. Thuật toán mã hóa cụ thể và key usage vẫn phải được kiểm soát ở tầng ứng dụng.
5. **Length-prefix** giúp nhãn rõ ràng, không bị nhập nhằng khi nối giá trị.
6. Các mảng chứa vật liệu khóa được xóa khi có thể để giảm thời gian tồn tại. Trong JVM, đối tượng như **SecretKeySpec**, Mac provider và bản sao nội bộ có thể giữ dữ liệu; xóa mảng **không bảo đảm xóa sạch mọi bản sao**.

**Cảnh báo thực hành:** một lần chạy mới của ví dụ tạo IKM và salt mới nên không cho ra lại các khóa cũ. Trong hệ thống cần giải mã dữ liệu lâu dài, không được tạo IKM mới ở mỗi lần khởi động nếu chưa có chiến lược di chuyển dữ liệu/khóa. Ngoài ra, việc lấy **tenant-42** làm context trong ví dụ không phải kiểm tra quyền; tenant thật phải đến từ danh tính đã xác thực.

### 9.2. Nếu dùng derived key để mã hóa AES-GCM

Nếu dẫn xuất được khóa AES-256, ứng dụng có thể dùng API Cipher của Java với AES/GCM/NoPadding, nonce theo giới hạn của GCM, tag xác thực và AAD phù hợp. **Mỗi lần mã hóa dưới cùng một AES key phải dùng nonce không trùng**; thông thường nonce 96 bit được quản lý theo chiến lược bảo đảm duy nhất. Lưu nonce và tag cùng ciphertext, kiểm tra tag trước khi chấp nhận plaintext.

Không đặt nguồn secret hoặc derived key trong log, URL, metrics label hoặc cơ sở dữ liệu bản rõ. Không dùng cùng một derived key cho nhiều thuật toán chỉ vì nó có 32 byte.

## 10. Kết hợp derived key với KMS, HSM và envelope encryption

Trong hạ tầng doanh nghiệp, root secret và các khóa cấp cao thường cần kiểm soát chặt hơn khóa con. Một thiết kế an toàn có thể dựa vào:

- **HSM:** quản lý vật liệu root/private key và thực hiện thao tác mật mã bên trong ranh giới phần cứng, nếu có hỗ trợ API dẫn xuất phù hợp.
- **KMS:** kiểm soát danh tính, quyền theo key ID, key policy, version, rotation, audit và có thể cung cấp API dẫn xuất hoặc **GenerateDataKey/Wrap/Unwrap** tùy dịch vụ.
- **Envelope encryption:** dùng DEK ngẫu nhiên để mã hóa dữ liệu; DEK được bọc dưới KEK trong KMS. Đây là cách phổ biến tránh phải xuất root key tới ứng dụng.
- **IAM và tầng nghiệp vụ:** bảo đảm workload chỉ được tạo/dùng khóa đúng tenant, dữ liệu và mục đích. KMS không thể tự suy luận quyền đọc hóa đơn của người dùng cuối nếu ứng dụng không áp dụng quy tắc đó.
- **Audit:** theo dõi thao tác tạo/quản trị root, derive key, unwrap, change policy, rotation và revoke, đồng thời tránh lưu vật liệu khóa hoặc ngữ cảnh bí mật.

Ví dụ: một thiết kế nhiều tenant muốn dẫn xuất **tenant-specific KEK** từ root secret. Trước khi chọn cách này, cần trả lời: nền tảng KMS/HSM có hỗ trợ dẫn xuất KEK **mà không xuất root** không? Làm sao ràng buộc tenant ID với danh tính được xác thực? Khi root bị lộ hoặc phải rotation, sẽ di chuyển KEK và wrapped DEK của tất cả tenant thế nào? Có phương án phân tách root theo môi trường/miền dữ liệu để hạn chế blast radius không?

Nếu không có cơ chế dẫn xuất tin cậy, **tạo các KEK độc lập bằng KMS** và bọc DEK có thể dễ phân quyền, xoay vòng và thu hồi hơn so với đưa một root chung vào nhiều ứng dụng.

### 10.1. Metadata của bản ghi dùng derived key

Giả sử một ứng dụng cố ý mã hóa một bản ghi bằng derived key được tạo từ root do KMS/HSM quản lý. Nó cần đủ metadata **không bí mật** để tái tạo đúng khóa hoặc di chuyển dữ liệu:

~~~json
{
  "ciphertext": "<base64 ciphertext and authentication tag>",
  "nonce": "<base64 nonce for AES-GCM>",
  "rootKeyRef": "billing-root-v3",
  "kdf": "HKDF-SHA256",
  "kdfVersion": 1,
  "salt": "<base64 salt>",
  "infoFormat": "length-prefixed-utf8-v1",
  "purpose": "invoice-aes-256-gcm",
  "tenantId": "tenant-42",
  "invoiceId": "inv-0088",
  "cipher": "AES-256-GCM"
}
~~~

Bản ghi minh họa không chứa ciphertext thực. **Root secret và derived key rõ không được lưu trong đó**. Metadata như tenant, invoice và key reference cần được xác thực/bảo vệ khỏi tráo đổi theo thiết kế (ví dụ gắn ngữ cảnh vào AEAD AAD và chính sách truy cập). Không coi tất cả metadata trên đều tự động an toàn khi cho phép client chỉnh sửa.

Nếu thiết kế thực tế dùng **wrapped DEK**, bản ghi nên lưu **wrapped DEK và KEK ID/version**, khi đó không nhất thiết cần lưu salt/info của một HKDF tự thiết kế.

## 11. Các sai lầm và tình huống sự cố

| Sai lầm | Vì sao nguy hiểm? | Cách xử lý |
| --- | --- | --- |
| **Dùng SHA-256(password) làm AES key** | Mật khẩu yếu vẫn dễ bị thử từ điển ngoại tuyến | Dùng password-based KDF thích hợp, salt và cost được benchmark; ưu tiên khóa ngẫu nhiên/KMS khi có thể |
| **Dùng HKDF trực tiếp cho mật khẩu yếu** | HKDF nhanh, không được thiết kế để chống thử đoán mật khẩu | Dùng Argon2id/scrypt/PBKDF2 theo chính sách và yêu cầu |
| **Dùng cùng info cho mọi mục đích** | Nguy cơ chia sẻ khóa giữa các miền sử dụng | Dùng nhãn domain separation có phiên bản/mục đích rõ ràng |
| **Dùng info từ tenant do client tự khai** | Kẻ tấn công có thể chọn miền derivation trái phép | Xác thực identity, kiểm tra quyền tenant và khóa nguồn |
| **Không lưu salt/context/version** | Không thể tái tạo derived key để giải bản mã cũ | Thiết kế metadata và migration trước khi phát hành |
| **Đưa root dài hạn vào mọi container** | Chiếm một tiến trình có thể làm lộ toàn bộ khóa con | Dùng KMS/HSM, phân tách nguồn bí mật, hạn chế xuất root |
| **Tưởng đổi root là dữ liệu cũ an toàn** | Kẻ đã lấy root cũ và ciphertext vẫn có thể dẫn xuất khóa cũ | Đánh giá phạm vi, phát hành DEK mới và re-encrypt nếu cần |
| **Tin rằng derived key tự có forward secrecy** | Lộ root dài hạn có thể khôi phục khóa phiên quá khứ | Dùng giao thức có ephemeral secrets và quy trình hủy an toàn |
| **Dùng derived key sai thuật toán** | Key 32 byte không chứng minh đủ điều kiện làm mọi loại khóa | Ràng buộc thuật toán, key usage và kiểm tra tham số |
| **Tái sử dụng nonce AES-GCM với cùng derived key** | Có thể mất bí mật và tính toàn vẹn nghiêm trọng | Thiết kế nonce duy nhất, giới hạn số lần mã hóa trên khóa |

### Tình huống A: lộ khóa con của một tenant

Giả sử hệ thống dẫn xuất khóa AES khác nhau cho tenant A và B bằng HKDF từ cùng root với info có nhãn tenant rõ ràng. Nếu kẻ tấn công chỉ lấy được **derived key của A**, các bảo đảm của KDF tốt và phân tách miền có thể khiến việc suy ngược root hoặc tính khóa của B không khả thi trong thực tế. Tuy nhiên, dữ liệu **tenant A dùng khóa bị lộ** vẫn cần được coi là có nguy cơ. Phải thu hồi quyền sử dụng khóa bị lộ, đánh giá bản mã đã sao chép và tái mã hóa khi cần.

### Tình huống B: lộ root secret chung

Nếu kẻ tấn công có root secret và biết salt/info vốn được lưu công khai, họ có thể tái tạo **nhiều derived key**. Đây là sự cố có phạm vi lớn: cần chặn các quyền nguồn, điều tra lịch sử, phát hành root mới, đánh giá từng tập dữ liệu/khóa con và xây dựng kế hoạch re-encrypt hoặc thay lớp bảo vệ phù hợp. Việc chỉ đổi chuỗi nhãn info không khắc phục được các khóa cũ đã lộ.

### Tình huống C: đổi KDF nhưng quên ghi phiên bản

Một bản ghi được mã hóa bằng khóa dẫn xuất HKDF-SHA256, sau đó ứng dụng chuyển sang KDF mới và dùng mặc định đó để mở mọi bản ghi. Kết quả sẽ là sai khóa và lỗi xác thực AES-GCM. Cách xử lý là **versioning** theo bản ghi, giữ triển khai giải mã cũ trong thời gian chuyển đổi có kiểm soát và thử restore backup trước khi hủy đường truy cập cũ.

## 12. Checklist khi thiết kế derived key

1. **Nguồn:** secret input có entropy thực tế bao nhiêu, là mật khẩu, key material ngẫu nhiên hay shared secret từ giao thức?
2. **Chọn KDF:** đã dùng HKDF cho key material mật mã mạnh và password-based KDF cho password chưa?
3. **Mục đích:** mỗi derived key có vai trò và thuật toán dùng rõ ràng không (DEK, KEK, MAC, session key, v.v.)?
4. **Phân tách:** info có nhãn ứng dụng/phiên bản/mục đích/chiều truyền/tenant khi cần, được mã hóa không nhập nhằng không?
5. **Metadata:** salt, info format, KDF algorithm, cost, output length và key version có được lưu an toàn để khôi phục không?
6. **Quyền:** ai có thể dùng root hoặc yêu cầu derive, principal đó có thể dẫn xuất khóa của tenant/mục đích khác không?
7. **Bảo vệ:** có tránh đưa root, derived key rõ và dữ liệu nhạy cảm vào mã nguồn/log/backup chung quyền không?
8. **Sử dụng:** có kiểm soát nonce/IV, AAD, auth tag và giới hạn thời gian sử dụng của khóa con không?
9. **Rotation:** dữ liệu cũ và backup sẽ được giải mã ra sao khi đổi root, salt/info format hoặc phiên bản KDF?
10. **Sự cố:** nếu root hoặc derived key lộ, có kiểm kê được các bản mã, dữ liệu và workload bị ảnh hưởng để re-encrypt/revoke không?
11. **Sẵn sàng:** mất root hoặc mất metadata có làm dữ liệu không thể khôi phục không; phương án restore đã được kiểm thử chưa?
12. **Audit:** thay đổi quyền derive, thay KDF, thay root, disable và destroy được ghi nhận như thế nào mà không lộ bí mật?

### Câu hỏi tự kiểm tra

**Câu 1.** Khóa dẫn xuất có phải luôn là DEK không?

**Đáp án:** Không. “Derived” mô tả cách tạo khóa; khóa dẫn xuất có thể đóng vai trò DEK, KEK, MAC key hoặc session key tùy thiết kế.

**Câu 2.** Có nên thay mật khẩu yếu bằng HKDF(password, salt, info) để được khóa AES-256 bảo mật tương đương 256 bit không?

**Đáp án:** Không. HKDF không làm mật khẩu có thêm entropy và không nhằm làm chậm tấn công thử đoán. Phải dùng password-based KDF phù hợp hoặc ưu tiên DEK ngẫu nhiên được quản lý an toàn.

**Câu 3.** Hai bên dùng cùng IKM và salt nhưng dùng info khác nhau trong HKDF. Các khóa đầu ra có giống nhau không?

**Đáp án:** Thông thường khác nhau theo thuộc tính tách miền của HKDF, với xác suất va chạm không đáng kể trong giới hạn bảo mật và cách sử dụng đúng. Info phải được quy ước rõ giữa các bên.

**Câu 4.** Khi root secret bị lộ, chỉ cần đổi root cho dữ liệu mới và giữ nguyên bản mã cũ?

**Đáp án:** Không đủ nếu cần bảo vệ bí mật dữ liệu cũ. Kẻ đã có root cũ và các tham số công khai có thể tái tạo khóa con trước đó. Phải đánh giá dữ liệu bị ảnh hưởng và thường cần mã hóa lại với khóa không bị lộ.

**Câu 5.** Derived key có tự bảo đảm forward secrecy không?

**Đáp án:** Không. Forward secrecy phải được thiết kế trong giao thức và cách quản lý bí mật tạm thời. Dẫn xuất các khóa phiên từ một root dài hạn rồi giữ root có thể khiến các phiên cũ bị lộ sau này.

**Câu 6.** Vì sao khi thiết kế key rotation cần giữ KDF version, salt và info cho dữ liệu cũ?

**Đáp án:** Vì KDF là quá trình xác định theo đầu vào. Thiếu hoặc đổi sai một tham số sẽ sinh khóa khác, làm quá trình xác thực/giải mã bản mã cũ thất bại.

## Kết luận

**Derived key là khóa được tính ra từ vật liệu bí mật đầu vào bằng KDF, với tham số và ngữ cảnh rõ ràng.** Khi dùng đúng, KDF giúp phân tách mục đích khóa, dẫn xuất khóa phiên và quản lý phân cấp; nó không tự chữa được nguồn bí mật yếu, lỗi xác thực peer, quyền sử dụng quá rộng hoặc thiết kế nonce sai.

Để sử dụng derived key an toàn trong hệ thống Java và hạ tầng doanh nghiệp, cần bảo vệ root/IKM, chọn đúng HKDF hoặc password-based KDF, áp dụng domain separation, quản lý metadata/version, thiết kế rotation và khôi phục, đồng thời kết hợp **KMS/HSM, envelope encryption, IAM và kiểm toán**. Sức mạnh thuật toán chỉ phát huy khi toàn bộ vòng đời và quyền sử dụng khóa được kiểm soát.
