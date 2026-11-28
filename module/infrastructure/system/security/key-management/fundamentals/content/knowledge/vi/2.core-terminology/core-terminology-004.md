# Public key: khóa công khai là gì và vì sao vẫn phải quản lý?

## 1. Public key trong bức tranh quản lý khóa mật mã

**Public key (khóa công khai)** là một thành phần của **cặp khóa bất đối xứng** (*asymmetric key pair*). Cặp khóa gồm:

- **Public key:** được thiết kế để chia sẻ cho các bên cần sử dụng; thường dùng để **xác minh chữ ký số**, **mã hóa dữ liệu cho người sở hữu private key**, hoặc tham gia một **giao thức thỏa thuận khóa**, tùy loại thuật toán.
- **Private key (khóa riêng):** phải được bảo vệ và cấp quyền sử dụng chặt chẽ; có thể dùng để **tạo chữ ký**, **giải mã**, hoặc tham gia thỏa thuận khóa, tùy thuật toán.

Hai khóa có quan hệ toán học nhưng không giống nhau. Với thuật toán và tham số hiện đại được triển khai đúng, việc có public key không cho phép suy ra private key bằng các phương pháp thực tế thông thường.

**Điểm cần nhớ:** public key không cần giữ bí mật, nhưng **phải đúng chủ thể, đúng mục đích và không bị thay thế**. Việc quản lý vòng đời của public key là một phần bắt buộc của *key management*, cùng với bảo vệ private key, kiểm soát quyền, xoay vòng, thu hồi và kiểm toán.

### Ví dụ mở đầu: giao dịch chuyển khoản bị sửa public key

Giả sử ứng dụng nhận public key của ngân hàng qua một đường dẫn không được xác thực rồi dùng khóa đó để kiểm tra chữ ký trên thông báo chuyển khoản. Kẻ tấn công kiểm soát đường truyền, thay public key thật bằng khóa do mình tạo và gửi thông báo giả kèm chữ ký tạo bằng private key của kẻ tấn công.

Phép kiểm tra chữ ký có thể vẫn trả về **true** vì chữ ký phù hợp với public key giả. Thuật toán ký số không bị phá: hệ thống đã tin **sai khóa**. Vì vậy câu hỏi bảo mật không chỉ là “Chữ ký có hợp lệ với khóa này không?” mà còn là “**Khóa này có thực sự thuộc ngân hàng được phép ký không?**”.

Sau bài này, người học có thể giải thích public key là gì, phân biệt với private key và symmetric key, lựa chọn đúng vai trò của public key trong mã hóa/chữ ký/thỏa thuận khóa, xác thực nguồn gốc khóa và thiết kế vòng đời quản lý khóa công khai cho hệ thống thật.

## 2. Phân biệt public key, private key và symmetric key

| Đặc điểm | Public key | Private key | Symmetric key |
| --- | --- | --- | --- |
| Mô hình | Một nửa của cặp khóa bất đối xứng | Một nửa còn lại của cặp khóa bất đối xứng | Một khóa bí mật dùng ở hai chiều mã hóa/giải mã |
| Bí mật? | Thông thường **không** | **Có** | **Có** |
| Thao tác điển hình | Xác minh chữ ký; mã hóa cho người nhận; hỗ trợ thỏa thuận khóa | Ký số; giải mã; tham gia thỏa thuận khóa | Mã hóa và giải mã dữ liệu, ví dụ AES-GCM |
| Điều kiện tin cậy quan trọng | Khóa phải được gắn đúng danh tính/chủ thể, thuật toán và mục đích | Không bị lộ hoặc bị sử dụng trái phép | Không bị lộ, được tạo và sử dụng đúng |
| Ví dụ lưu trữ | Chứng chỉ X.509, JWKS, kho khóa công khai tin cậy | KMS/HSM, kho khóa bảo mật | KMS, secret manager, DEK được bọc bởi KEK |

Một số nhầm lẫn cần tránh:

1. **Public key không phải mật khẩu, API key hay access token.** Không nên coi việc biết public key là bằng chứng có quyền đăng nhập hoặc gọi API.
2. **Public key không tự bảo đảm danh tính.** Khóa là dữ liệu toán học; cần cơ chế tin cậy để xác nhận khóa thuộc đúng người, dịch vụ hoặc tổ chức.
3. **Không phải mọi public key làm được mọi việc.** Khóa **Ed25519** dùng để xác minh chữ ký; khóa **X25519** dùng cho thỏa thuận khóa; khóa **RSA** có thể tham gia mã hóa hoặc ký tùy thuật toán và chính sách. Không tráo mục đích sử dụng.
4. **Mã hóa bất đối xứng không thay thế hoàn toàn mã hóa đối xứng.** Trong thực tế, dữ liệu lớn thường được mã hóa bằng **DEK đối xứng** (ví dụ AES-GCM); cơ chế bất đối xứng chỉ mã hóa hoặc đóng gói thông tin khóa nhỏ, hoặc dùng để thống nhất khóa phiên.

## 3. Public key làm gì trong từng nhóm cơ chế mật mã?

### 3.1. Xác minh chữ ký số: public key giúp kiểm tra ai đã ký?

Một bên sở hữu private key có thể tạo chữ ký trên nội dung thông điệp; bên nhận dùng public key tương ứng để xác minh.

~~~text
Bên ký:    Thông điệp + Private key --Sign--> Chữ ký
Bên nhận:  Thông điệp + Chữ ký + Public key --Verify--> Hợp lệ / Không hợp lệ
~~~

Ví dụ: hệ thống phân phối phần mềm ký một manifest phát hành bằng private key. Máy khách kiểm tra chữ ký bằng public key **đã được xác thực** của nhà phát hành. Nếu manifest bị sửa mà không có chữ ký hợp lệ, kiểm tra sẽ thất bại.

Với cách triển khai đúng, chữ ký giúp kiểm tra **tính toàn vẹn** và **tính xác thực mật mã của bên kiểm soát private key**. Để kết luận đó là nhà phát hành cụ thể, bên xác minh phải tin cậy liên kết giữa public key và danh tính nhà phát hành.

Chữ ký số **không mã hóa nội dung**: ai có thông điệp vẫn có thể đọc nó nếu nội dung không được mã hóa riêng. Chữ ký hợp lệ cũng không tự chứng minh rằng một con người cụ thể đã phê duyệt giao dịch, vì private key hoặc dịch vụ ký có thể bị lạm dụng.

Ví dụ các thuật toán/chế độ liên quan:

- **Ed25519:** thuật toán chữ ký số; public key dùng xác minh, private key dùng ký.
- **ECDSA:** thuật toán chữ ký trên đường cong elliptic; việc sinh số ngẫu nhiên cho từng chữ ký cần đúng cách (hoặc dùng triển khai xác định phù hợp).
- **RSA-PSS:** lược đồ chữ ký được khuyến nghị cho những thiết kế RSA mới phù hợp hệ sinh thái; tránh tự định nghĩa cách ký dựa trên RSA thô.

### 3.2. Mã hóa cho người nhận: public key giúp ai cũng gửi được dữ liệu bí mật?

Trong mã hóa khóa công khai, người gửi mã hóa bằng **public key đúng của người nhận**, còn người nhận giải mã bằng **private key tương ứng**:

~~~text
Người gửi:    Plaintext + Public key của người nhận --Encrypt--> Ciphertext
Người nhận:   Ciphertext + Private key của mình --Decrypt--> Plaintext
~~~

Nếu public key bị thay thế bằng khóa của kẻ tấn công, người gửi có thể mã hóa dữ liệu cho **sai người nhận** dù thuật toán mã hóa hoàn toàn an toàn.

Cần phân biệt khả năng của thuật toán:

- **RSA-OAEP** có thể mã hóa lượng dữ liệu nhỏ được giới hạn bởi kích thước khóa và tham số OAEP; không dùng RSA trực tiếp để mã hóa cả tệp lớn.
- **X25519 không phải thuật toán mã hóa trực tiếp.** Nó hỗ trợ hai bên tạo bí mật chung; kết quả được đưa qua **KDF** thích hợp để tạo khóa phiên rồi dùng thuật toán mã hóa đối xứng có xác thực.
- Các thiết kế hiện đại thường sử dụng **hybrid public-key encryption** hoặc một cơ chế **KEM/DEM** được chuẩn hóa: phần bất đối xứng thiết lập/bọc khóa, phần đối xứng bảo vệ nội dung.

**Giới hạn:** chỉ mã hóa bằng public key của người nhận không tự chứng minh **người gửi là ai**. Nếu ứng dụng cần xác thực người gửi, phải bổ sung chữ ký hoặc cơ chế xác thực phù hợp.

### 3.3. Thỏa thuận khóa: public key không nhất thiết được dùng để mã hóa

Một số giao thức, như (EC)DH hoặc X25519, cho phép hai phía kết hợp **private key của mình** và **public key của phía kia** để tính ra vật liệu bí mật chung. Trong giao thức đúng, bí mật đó được xử lý qua KDF và sử dụng để thiết lập khóa phiên; không dùng trực tiếp kết quả thỏa thuận làm khóa AES mà bỏ qua các bước quy định của giao thức.

~~~mermaid
sequenceDiagram
    participant A as Client
    participant B as Server
    A->>B: Public key tạm thời của A
    B->>A: Public key tạm thời của B
    Note over A,B: Mỗi bên dùng private key của mình và public key phía kia
    A->>A: Tính shared secret, dẫn xuất session keys
    B->>B: Tính shared secret, dẫn xuất session keys
    Note over A,B: Giao thức phải xác thực peer và ràng buộc bản ghi handshake
~~~

**Chống nghe lén không đồng nghĩa chống giả mạo.** Nếu không xác thực public key/giao thức, kẻ đứng giữa có thể thương lượng hai khóa phiên riêng với hai bên (*man-in-the-middle*).

Trong **TLS 1.3**, chứng chỉ của máy chủ thường đóng vai trò giúp xác thực danh tính máy chủ và chữ ký handshake; khóa phiên được thiết lập từ quá trình thỏa thuận khóa tạm thời. Không nên mô tả TLS hiện đại là “trình duyệt lấy RSA public key trong chứng chỉ rồi mã hóa toàn bộ kết nối bằng RSA”.

## 4. Vì sao khóa công khai vẫn phải được tin cậy?

### 4.1. Xác minh chữ ký với một khóa bất kỳ là chưa đủ

Về mặt toán học, phép kiểm tra thường có dạng:

~~~text
Verify(publicKey, message, signature) -> true | false
~~~

Kết quả **true** chỉ nói rằng chữ ký tương ứng với **public key được đưa vào phép kiểm tra**. Nó không tự trả lời:

- Public key được tạo bởi ai?
- Public key có đúng thuộc về máy chủ, tổ chức hoặc nhà phát hành dự kiến không?
- Khóa có được phép dùng cho mục đích này không?
- Khóa còn được tin cậy tại thời điểm kiểm tra không?

Vì thế, hệ thống phải xây dựng **ràng buộc danh tính ↔ public key** (*identity binding*) bằng quy trình phân phối và xác thực đáng tin cậy.

### 4.2. Chứng chỉ số và PKI

**Chứng chỉ X.509** thường chứa public key của chủ thể, thông tin chủ thể, tổ chức phát hành (CA), thời hạn hiệu lực, các ràng buộc sử dụng khóa và chữ ký số của bên phát hành.

Một quá trình xác minh chứng chỉ máy chủ TLS có thể phải kiểm tra **đường dẫn chứng chỉ đến trust anchor**, chữ ký các chứng chỉ, tên máy chủ, thời hạn, mục đích sử dụng và chính sách thu hồi/trạng thái phù hợp với ngữ cảnh. Chỉ kiểm tra “chữ ký chứng chỉ đúng” là chưa đủ.

~~~mermaid
flowchart TD
    A["Trust anchor / Root CA đã tin cậy"] --> B["Intermediate CA"]
    B --> C["Chứng chỉ server chứa public key"]
    C --> D["Ứng dụng kiểm tra chain, hostname, thời hạn, key usage và chính sách"]
    D --> E{"Đủ điều kiện tin cậy?"}
    E -->|Có| F["Sử dụng public key cho đúng giao thức"]
    E -->|Không| G["Từ chối hoặc xử lý theo chính sách an toàn"]
~~~

**Phân biệt ba khái niệm:**

| Khái niệm | Là gì? | Vai trò |
| --- | --- | --- |
| **Public key** | Vật liệu khóa toán học có thể chia sẻ | Xác minh chữ ký, mã hóa cho người nhận hoặc thỏa thuận khóa |
| **Certificate** | Dữ liệu có chữ ký liên kết public key với danh tính và các thuộc tính | Trợ giúp bên kiểm tra xác thực ràng buộc khóa – danh tính |
| **Trust anchor** | Điểm tin cậy được cấu hình hoặc phân phối an toàn | Cơ sở để đánh giá chuỗi tin cậy của chứng chỉ |

Một public key có thể được chia sẻ dưới dạng **SubjectPublicKeyInfo (SPKI)**, chẳng hạn PEM với nhãn **PUBLIC KEY**, mà **không kèm chứng chỉ**. Khi ấy ứng dụng phải có một quy tắc tin cậy khác (ví dụ khóa được cấu hình qua kênh an toàn hoặc được ràng buộc vào một tài khoản đã xác thực).

### 4.3. Những cách khác để tin public key

- **Trust store / cấu hình tin cậy:** nạp public key hoặc chứng chỉ đã được xác minh qua quy trình vận hành an toàn.
- **Certificate pinning:** ràng buộc đến public key/chứng chỉ cụ thể; hữu ích trong một số môi trường kiểm soát chặt nhưng có thể gây gián đoạn nếu không chuẩn bị rotation và cơ chế dự phòng.
- **JWKS** (JSON Web Key Set): máy chủ công bố tập public key dạng JWK cho hệ thống xác minh token hoặc chữ ký. Endpoint JWKS cần được xác thực qua TLS và chỉ lấy từ nguồn được cấu hình tin cậy.
- **Fingerprint:** giá trị băm (thường SHA-256) của dạng biểu diễn khóa theo quy ước, dùng để đối chiếu khóa qua kênh xác thực độc lập. Fingerprint không phải mật khẩu và không tạo ra sự tin cậy nếu cả fingerprint lẫn khóa đều lấy từ cùng nguồn bị tấn công.
- **TOFU** (*trust on first use*): tin khóa ở lần tiếp xúc đầu và cảnh báo khi thay đổi; phù hợp một số trường hợp nhưng yếu trước tấn công ngay lần đầu.

**Key ID** (ví dụ trường **kid** trong JOSE/JWT) chủ yếu là **định danh để chọn khóa**. Giá trị kid không tự chứng minh quyền sở hữu khóa, không phải chữ ký và không nên cho phép client chọn tùy ý một public key chưa được tin cậy.

## 5. Vòng đời của public key và cặp khóa bất đối xứng

Public key dễ chia sẻ hơn private key nhưng không vì thế mà “phát tán một lần rồi quên”. Cả hai cần quản lý xuyên suốt vòng đời.

| Giai đoạn | Công việc với public key | Công việc với private key và kiểm soát |
| --- | --- | --- |
| **1. Tạo cặp khóa** | Chọn thuật toán, tham số, mục đích; gắn key ID và chủ thể | Sinh cặp khóa bằng thư viện tin cậy hoặc KMS/HSM; private key được bảo vệ ngay từ đầu |
| **2. Đăng ký/cấp phát** | Xác minh danh tính chủ thể; phát hành certificate hoặc đưa khóa vào trust store/JWKS | Chỉ cấp quyền sử dụng private key cho principal và thao tác phù hợp |
| **3. Phân phối** | Phát public key qua kênh có thể xác thực; quản lý fingerprint/chuỗi chứng chỉ | Tránh phân phối private key; hạn chế xuất khóa và bảo vệ backup nếu cần |
| **4. Sử dụng** | Kiểm tra chữ ký, mã hóa hoặc thỏa thuận khóa đúng loại/đúng key usage | Quyền Sign/Decrypt/Derive theo least privilege; nhật ký kiểm toán các thao tác nhạy cảm |
| **5. Xoay vòng** | Công bố khóa mới, quản lý phiên bản và giai đoạn chồng lấp tin cậy khi cần | Tạo private key mới, chuyển workload sang khóa mới; giảm quyền dùng khóa cũ |
| **6. Thu hồi** | Đánh dấu khóa/chứng chỉ không còn tin cậy; cập nhật trust store, CRL/OCSP hay danh sách khóa theo mô hình | Vô hiệu hóa hoặc hạn chế thao tác private key tương ứng; điều tra phạm vi bị ảnh hưởng |
| **7. Lưu giữ lịch sử** | Lưu khóa công khai/chuỗi chứng chỉ và bằng chứng cần thiết để xác minh dữ liệu đã ký theo chính sách | Không tiếp tục ký bằng private key đã hết cryptoperiod; quản lý thời hạn giữ để giải mã dữ liệu cũ nếu phụ thuộc |
| **8. Hủy** | Ngừng công bố/không còn tin khóa khi không cần; có thể lưu public key để kiểm chứng lịch sử | Hủy an toàn vật liệu private key và bản sao sau khi kiểm kê phụ thuộc |

### 5.1. Rotation không chỉ là thay file PEM

Giả sử dịch vụ **PaymentSigner** sử dụng khóa **K1** để ký webhook; dịch vụ **PaymentVerifier** giữ public key K1 để xác minh. Khi thay bằng **K2**, nếu signer bắt đầu dùng K2 trước khi verifier biết K2, mọi webhook mới có thể bị từ chối. Nếu verifier bỏ K1 quá sớm, webhook cũ hoặc thông điệp đang được xử lý có thể không xác minh được.

Một quy trình có kế hoạch:

1. Sinh **K2** và xác thực ràng buộc khóa với danh tính PaymentSigner.
2. Công bố public key K2 qua kênh tin cậy; các bên xác minh chấp nhận K1/K2 trong **cửa sổ chuyển đổi có giới hạn**, theo phiên bản và chính sách.
3. Chuyển dịch vụ ký sang private key K2; gắn key ID rõ ràng với mỗi chữ ký để phía nhận tìm khóa phù hợp.
4. Theo dõi sự kiện xác minh lỗi và xác nhận các bên đã cập nhật; sau thời gian cho phép, dừng ký và loại K1 khỏi các khóa được phép xác minh **thông điệp mới**.
5. Quy định riêng việc xác minh chữ ký trong hồ sơ lịch sử, yêu cầu thời gian ký đáng tin cậy nếu nghiệp vụ cần chứng minh chữ ký hợp lệ tại một thời điểm trước đó.

Khóa cũ bị **lộ private key** cần quy trình xử lý sự cố khẩn cấp thay vì cứ duy trì cửa sổ chồng lấp thông thường. Những thông điệp đã được kẻ tấn công ký sau khi chiếm khóa có thể vượt qua phép xác minh bằng public key cũ.

### 5.2. Thu hồi khóa, hết hạn chứng chỉ và tính hợp lệ lịch sử

Đây là ba khái niệm khác nhau:

- **Hết hạn chứng chỉ:** thời gian hiệu lực ghi trong chứng chỉ đã kết thúc. Điều này không tự chứng minh private key đã lộ và cũng không có nghĩa mọi chữ ký lịch sử từng hợp lệ đều trở nên giả.
- **Thu hồi chứng chỉ/khóa:** có thông tin cho rằng không còn nên tin chứng chỉ/khóa trước thời hạn dự kiến. Bên xác minh cần chính sách và kênh kiểm tra trạng thái có hiệu lực; cache hoặc xác minh offline có thể gây trễ.
- **Không thể tin chữ ký trong quá khứ:** cần đánh giá riêng khi private key có khả năng bị lộ, dựa trên thời gian bị ảnh hưởng, timestamp đáng tin cậy và quy định lưu trữ chứng cứ. Không thể chỉ nhìn chữ ký toán học mà kết luận mọi thông điệp cũ còn đáng tin.

Đối với chứng chỉ X.509, **CRL** và **OCSP** là hai cơ chế phổ biến để cung cấp thông tin thu hồi, nhưng hành vi kiểm tra và xử lý khi dịch vụ trạng thái không truy cập được phụ thuộc chính sách và loại ứng dụng. Với **JWKS**, việc gỡ một khóa khỏi danh sách tin cậy có thể khiến trình xác minh từ chối chữ ký dùng khóa đó sau khi cache được cập nhật.

## 6. Rủi ro thường gặp nếu quản lý public key sai

| Sai lầm | Hậu quả có thể xảy ra | Biện pháp |
| --- | --- | --- |
| Tải public key từ URL không xác thực rồi tin ngay | Kẻ đứng giữa thay khóa; xác minh chữ ký giả hoặc mã hóa cho sai người | TLS đúng chuẩn, chứng chỉ/trust anchor phù hợp, kiểm tra fingerprint qua kênh tin cậy |
| Tin vào public key bất kỳ đính kèm yêu cầu | Người gửi tự tạo cặp khóa rồi tự ký và tuyên bố mình là người có quyền | Ràng buộc khóa với issuer, tài khoản hoặc danh tính đã xác thực |
| Chỉ dựa vào trường kid | Attacker chọn khóa khác hoặc khai thác nhầm lẫn ở bộ chọn khóa | Chỉ tra khóa trong tập được tin cậy; cố định thuật toán cho từng khóa/mục đích |
| Dùng public key ký số như khóa mã hóa | Lỗi thuật toán hoặc hiểu sai bảo đảm bảo mật | Phân loại khóa theo Sign, Verify, Encrypt, Decrypt, Derive; tách mục đích |
| Không triển khai kế hoạch rotation | Thay khóa gây ngừng dịch vụ, token/chữ ký hợp lệ bị từ chối | Quản lý phiên bản, giai đoạn công bố trước, cache TTL và giám sát |
| Không có đường thu hồi | Khóa của chủ thể bị vô hiệu hóa vẫn được chấp nhận | Chính sách revoke, danh sách tin cậy cập nhật và cơ chế thông báo sự cố |
| Không kiểm soát việc gọi Sign trong KMS/HSM | Private key không xuất được vẫn bị dùng để ký nội dung trái phép | IAM least privilege, kiểm tra nghiệp vụ trước khi ký, audit và cảnh báo |
| Tự tin vào chữ ký nhưng bỏ qua nghiệp vụ | Chữ ký hợp lệ của issuer không đồng nghĩa request hợp lệ | Kiểm tra quyền, ngữ cảnh, thời hạn, audience, nonce/replay theo giao thức |

Đặc biệt, nếu dùng public key để xác minh **JWT**, ngoài xác minh chữ ký, hệ thống còn phải kiểm tra các claim liên quan như **issuer**, **audience**, **expiration**, **not before** (khi áp dụng) và phân quyền nghiệp vụ. Không được để token tự chỉ định URL tùy ý để tải khóa xác minh, hoặc tự tin vào thuật toán do input không đáng tin yêu cầu.

## 7. Ví dụ Java: public key dùng để xác minh chữ ký Ed25519

Ví dụ sau dùng API chuẩn của Java (JDK 15 trở lên có hỗ trợ Ed25519). Nó sinh cặp khóa để minh họa, ký thông điệp bằng private key và xác minh bằng public key.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class PublicKeyDemo {
    public static void main(String[] args) throws Exception {
        // Demo: sinh cặp khóa trong bộ nhớ.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair pair = generator.generateKeyPair();

        byte[] message = "transfer:order-1001:amount-250".getBytes(
                StandardCharsets.UTF_8);

        // Bên ký: chỉ thành phần có quyền mới được dùng private key.
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        // Bên xác minh: cần public key đã được xác thực của bên ký.
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        boolean valid = verifier.verify(signature);

        System.out.println("Signature valid: " + valid); // true

        // Đổi thông điệp thì chữ ký cũ không còn xác minh thành công.
        byte[] changedMessage = "transfer:order-1001:amount-999".getBytes(
                StandardCharsets.UTF_8);
        verifier.initVerify(pair.getPublic());
        verifier.update(changedMessage);
        System.out.println("Modified message valid: "
                + verifier.verify(signature)); // false
    }
}
~~~

Ví dụ này chứng minh **tính đúng đắn của phép ký/xác minh**, không chứng minh danh tính người ký: chương trình tự sinh cả cặp khóa nên đương nhiên biết public key tương ứng. Trong hệ thống thật, verifier phải nhận public key từ **nguồn được xác thực** (trust store, chứng chỉ được xác minh hoặc cấu hình khóa đã tin cậy).

Khi triển khai production:

- Cân nhắc tạo, lưu và ký bằng **KMS/HSM** có chính sách chặt; private key không nhất thiết cần xuất ra JVM.
- Gắn khóa với **key ID**, chủ thể, mục đích, trạng thái và thời hạn; giải quyết rotation/thu hồi trước khi phát hành.
- Kiểm soát quyền gọi API ký: giữ private key an toàn nhưng cho mọi request được ký là một lỗi thiết kế.
- Không log/private key export, không nhúng khóa trong mã nguồn hoặc tạo lại cặp khóa mỗi lần service khởi động nếu khóa phải ổn định qua các lần triển khai.
- Nếu muốn dùng public key để **mã hóa**, phải triển khai một cơ chế mã hóa được thiết kế cho mục đích đó; **không dùng Ed25519 như thuật toán mã hóa**.

## 8. Public key, KMS/HSM và envelope encryption liên hệ thế nào?

Trong mô hình **envelope encryption**, dữ liệu thường được mã hóa bằng **DEK (Data Encryption Key)** đối xứng, còn **KEK (Key Encryption Key)** bảo vệ DEK. Có thể dùng KEK đối xứng trong KMS, hoặc một cơ chế **bọc/đóng gói DEK bằng public key** của người nhận tùy kiến trúc.

~~~mermaid
flowchart LR
    M["Dữ liệu cần mã hóa"] --> A["AES-GCM với DEK ngẫu nhiên"]
    A --> C["Ciphertext + nonce + tag"]
    K["Public key đúng của người nhận"] --> W["Cơ chế bọc/đóng gói DEK được hỗ trợ"]
    D["DEK"] --> A
    D --> W
    W --> E["Wrapped DEK"]
    C --> S["Kho lưu trữ"]
    E --> S
    P["Private key được bảo vệ trong KMS/HSM"] -. "Chỉ bên được cấp quyền mở DEK" .-> E
~~~

Ví dụ: hệ thống gửi tệp cho đối tác, tạo một DEK mới để mã hóa tệp, sau đó mã hóa/đóng gói DEK bằng public key **đã được xác minh** của đối tác. Đối tác sử dụng private key tương ứng theo giao thức để phục hồi DEK rồi giải mã tệp. Không bao giờ nhúng private key của đối tác vào ứng dụng gửi.

Với kiến trúc này, vẫn phải bảo đảm:

1. Public key của đối tác là **đúng khóa**, còn hiệu lực và cho phép đúng mục đích.
2. Thuật toán bọc khóa hoặc KEM được chọn là cơ chế **chuẩn hóa, có xác thực phù hợp**; không tự xây giao thức mật mã.
3. DEK được sinh an toàn; nonce/IV và authenticated encryption được quản lý đúng.
4. Việc cho phép sử dụng private key tại KMS/HSM được kiểm soát bằng IAM, chính sách nghiệp vụ và audit.
5. Có thiết kế rotation, thu hồi và giải mã dữ liệu cũ tương ứng với thời hạn lưu trữ.

**Không nhầm KMS/HSM với bằng chứng danh tính:** việc một public key được tải từ API KMS không tự chứng minh nó thuộc về đối tác mong muốn; bên sử dụng vẫn phải xác thực tài khoản, chính sách sở hữu hoặc quy trình trao đổi khóa giữa hai tổ chức.

## 9. Kiểm toán và giám sát vòng đời public key

Dù vật liệu public key có thể công khai, việc **tạo, thêm, thay, cấp quyền hoặc thu hồi một khóa được tin cậy** là thao tác nhạy cảm. Nên có nhật ký và cảnh báo về:

- Ai đăng ký hoặc thay public key của tài khoản, dịch vụ, đối tác; nguồn xác minh danh tính/ủy quyền là gì.
- Thời điểm chứng chỉ/JWKS thay đổi; khóa nào được thêm, bị loại, và phạm vi ứng dụng nào bị tác động.
- Các sự kiện phát hành, gia hạn, hết hạn, thu hồi chứng chỉ; cache và trạng thái cập nhật ở các verifier.
- Ai yêu cầu **Sign/Decrypt/Derive** bằng private key trong KMS/HSM, từ workload nào, thao tác thành công hay bị từ chối.
- Tỷ lệ chữ ký không hợp lệ tăng đột biến, khóa lạ xuất hiện hoặc yêu cầu xác minh dùng key ID không tồn tại.

Nhật ký có thể chứa key ID, fingerprint, sự kiện, danh tính workload, thời gian, request ID và kết quả, nhưng **không ghi private key, DEK dạng rõ hoặc bản rõ dữ liệu nhạy cảm**. Nếu đưa public key vào log để hỗ trợ điều tra, cần kiểm soát kích thước, tính toàn vẹn và độ nhạy của metadata đi kèm.

## 10. Tình huống thực hành: dịch vụ xác minh webhook

Một hệ thống Java nhận webhook từ nhà cung cấp thanh toán. Nhà cung cấp gửi nội dung, chữ ký và key ID, đồng thời công bố tập public key trên endpoint JWKS.

Quy trình an toàn về nguyên tắc:

1. Đăng ký **issuer và địa chỉ JWKS tin cậy** của nhà cung cấp từ cấu hình đã kiểm duyệt; không lấy endpoint từ header tùy ý của webhook.
2. Tải JWKS qua HTTPS với kiểm tra chứng chỉ đúng; quản lý cache và làm mới khóa theo chính sách.
3. Đọc key ID từ webhook để **chọn** khóa trong tập đã tin cậy; khóa được chọn phải có loại và thuật toán cho phép, phù hợp mục đích xác minh.
4. Xác minh chữ ký trên **đúng dãy byte mà bên gửi ký** (bao gồm quy tắc canonicalization nếu giao thức có), không tự sửa body trước khi kiểm tra.
5. Kiểm tra timestamp, ID sự kiện, issuer, tài khoản đích và giới hạn chấp nhận để chống phát lại theo đặc tả của nhà cung cấp.
6. Chỉ khi **đã xác thực webhook**, mới áp dụng xử lý nghiệp vụ và kiểm tra khả năng phát lại/đã xử lý.
7. Ghi log các lần dùng khóa không tồn tại, lỗi chữ ký, cập nhật keyset và thay đổi trust configuration; thiết lập quy trình emergency revoke.

**Giả định cần tránh:** “Chữ ký hợp lệ thì chắc chắn chuyển tiền”. Chữ ký cho biết dữ liệu đã được ký bởi bên nắm private key được tin cậy; hệ thống vẫn phải kiểm tra sự kiện đó có hợp lệ với **đơn hàng, số tiền, người nhận và trạng thái giao dịch** của mình hay không.

## 11. Checklist dùng public key đúng cách

1. Public key này thuộc **ai**, được xác nhận bằng cách nào?
2. Khóa hỗ trợ thao tác **Verify / Encrypt / Derive** nào; thuật toán nào được cho phép?
3. Có tách public key theo **môi trường, chủ thể, tenant và mục đích** khi cần không?
4. Nếu có certificate, hệ thống kiểm tra **chuỗi tin cậy, tên, thời hạn, mục đích, chính sách thu hồi** phù hợp chưa?
5. Nếu dùng JWKS, endpoint được **cố định từ nguồn tin cậy** chưa; cách kiểm soát kid và cache có chặn thay khóa trái phép không?
6. Có quy trình **công bố khóa mới trước khi chuyển đổi**, xử lý khóa cũ và thu hồi khẩn cấp không?
7. Có kế hoạch xác minh **chữ ký/dữ liệu lịch sử** sau khi khóa hoặc chứng chỉ hết hạn không?
8. Private key được lưu ở đâu, ai có quyền **Sign / Decrypt / Derive**, sự kiện nào được kiểm toán?
9. Bên nhận kiểm tra **quyền nghiệp vụ, thời hạn, chống replay và ngữ cảnh** sau khi xác minh mật mã chưa?
10. Khi phát hiện key substitution hoặc private key compromise, có thể **xác định phạm vi, vô hiệu hóa và khôi phục** trong thời gian chấp nhận được không?

### Tự kiểm tra kiến thức

**Câu 1.** Nếu public key không phải bí mật, vì sao kẻ tấn công thay public key trên website vẫn nguy hiểm?

**Trả lời:** Vì bên dùng có thể mã hóa dữ liệu cho kẻ tấn công hoặc tin vào chữ ký được tạo bằng private key tương ứng với public key giả. Cần bảo vệ tính xác thực và toàn vẹn của đường phân phối khóa.

**Câu 2.** Máy chủ nhận chữ ký hợp lệ bằng public key do chính request đính kèm. Đã xác thực người gửi chưa?

**Trả lời:** Chưa. Phép Verify chỉ xác nhận chữ ký khớp với khóa được đưa vào. Phải xác minh rằng khóa đó thuộc đúng danh tính hoặc issuer được quyền gửi request.

**Câu 3.** Có dùng public key Ed25519 để mã hóa tài liệu bằng AES-GCM trực tiếp được không?

**Trả lời:** Không. Ed25519 dùng cho chữ ký; AES-GCM dùng khóa đối xứng. Để trao đổi hoặc bọc DEK bằng cơ chế bất đối xứng, cần thuật toán/giao thức phù hợp như RSA-OAEP hoặc thiết kế KEM/DEM đã được chuẩn hóa.

**Câu 4.** Khi thay public key K1 bằng K2, vì sao cả bên ký và bên xác minh phải phối hợp?

**Trả lời:** Nếu bên ký dùng K2 trước khi bên xác minh tin K2, các chữ ký mới bị từ chối. Nếu bỏ K1 quá sớm, thông điệp cũ hoặc còn trong hàng đợi không thể xác minh theo chính sách thông thường.

**Câu 5.** Private key không thể xuất khỏi HSM. Có thể coi là không còn rủi ro lạm dụng chữ ký không?

**Trả lời:** Không. Workload có quyền Sign quá rộng vẫn có thể yêu cầu HSM ký nội dung không được phép. Phải kiểm soát IAM, xác thực yêu cầu nghiệp vụ và kiểm toán.

## Tổng kết

**Public key là khóa có thể phân phối rộng, nhưng không thể được tin cậy một cách tùy tiện.** Sự an toàn phụ thuộc vào việc public key đúng chủ thể, đúng thuật toán, đúng mục đích và còn được phép sử dụng; private key tương ứng phải được bảo vệ khỏi rò rỉ và lạm dụng.

Trong quản lý khóa thực tế, public key liên kết **mật mã bất đối xứng**, **chữ ký số**, **PKI/chứng chỉ**, **KMS/HSM**, **envelope encryption**, **IAM**, **rotation/thu hồi** và **audit**. Thuật toán có thể rất mạnh, nhưng chỉ một public key bị tráo hoặc một private key bị dùng sai quyền cũng đủ khiến toàn bộ quy trình bảo mật thất bại.
