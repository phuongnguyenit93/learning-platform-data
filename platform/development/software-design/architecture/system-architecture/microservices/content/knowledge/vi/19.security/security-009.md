# Mã hóa khi truyền, khi lưu và quản lý khóa trong Microservices

Trong kiến trúc microservices, dữ liệu nhạy cảm có thể đi qua trình duyệt, API Gateway, nhiều service, message broker, database, cache, object storage, hệ thống log và bản sao lưu. Một kết nối nội bộ hoặc một ổ đĩa được đặt trong mạng riêng **không mặc nhiên an toàn**. Thiết kế bảo mật cần bảo vệ dữ liệu khi di chuyển, khi được lưu trữ, và đặc biệt là bảo vệ những khóa có thể giải mã dữ liệu đó.

Ba thành phần cần đi cùng nhau:

1. **Encryption in transit** — mã hóa dữ liệu trên đường truyền, chủ yếu bằng TLS; dùng mTLS khi cần xác thực hai chiều giữa các thành phần.
2. **Encryption at rest** — mã hóa dữ liệu trên đĩa, trong cơ sở dữ liệu, backup hoặc trường dữ liệu nhạy cảm tùy mô hình đe dọa.
3. **Key management** — sinh, cấp quyền sử dụng, lưu giữ, luân chuyển, thu hồi, giám sát và hủy khóa đúng thời điểm. Nếu kẻ tấn công lấy được cả dữ liệu mã hóa lẫn khóa giải mã, phần lớn giá trị bảo vệ của mã hóa sẽ mất đi.

Bài học này tập trung vào cách kết hợp ba lớp trong hệ thống phân tán, đặc biệt là các ranh giới giữa service, các thành phần vận hành và vòng đời khóa.

## 1. Bắt đầu từ mô hình đe dọa và mục tiêu bảo vệ

Giả sử hệ thống thương mại điện tử có Order Service, Customer Service, Payment Service, Inventory Service và Notification Service. Dữ liệu đi qua nhiều ranh giới:

~~~text
Browser / Mobile App
        |
      HTTPS
        v
   API Gateway
        |
   TLS / mTLS
        v
   Order Service ---------TLS/mTLS--------> Payment Service
        |                                      |
      TLS                                      TLS
        v                                      v
   Order Database                         Payment Database
        |
    Encrypted backup
        |
   Backup Storage

Order Service -----TLS-----> Message Broker ----TLS-----> Notification Service
        |
  KMS / Key Service
  (cấp hoặc mở khóa DEK theo chính sách truy cập)
~~~

Các tình huống cần xem xét:

- Kẻ tấn công nghe lén hoặc thay đổi lưu lượng giữa client và gateway, giữa các service, hoặc giữa service và database.
- File backup, snapshot, volume hoặc bản xuất dữ liệu rơi vào tay người không được phép.
- Một service bị xâm nhập, cố yêu cầu giải mã dữ liệu của service khác.
- Khóa bị lộ qua mã nguồn, biến môi trường, log, image container, CI/CD hoặc máy người vận hành.
- Chứng chỉ hết hạn, KMS không khả dụng, khóa bị vô hiệu hoặc dữ liệu được mã hóa bằng phiên bản khóa cũ.

**Mã hóa bảo vệ tính bí mật**; những cơ chế như TLS và AEAD còn kiểm tra tính toàn vẹn của thông điệp trong phạm vi tương ứng. Tuy nhiên, mã hóa không thay thế xác thực người dùng, phân quyền, kiểm tra dữ liệu đầu vào, chống SQL injection hay bảo vệ máy chủ đã bị chiếm quyền. Một service có quyền giải mã hợp lệ mà bị xâm nhập vẫn có thể làm lộ plaintext.

| Tài sản hoặc luồng | Cơ chế bảo vệ thường dùng | Giới hạn cần nhớ |
| --- | --- | --- |
| Browser → API Gateway | HTTPS/TLS, chứng chỉ hợp lệ | HTTPS không chứng minh người dùng có quyền truy cập API |
| Service → Service | TLS, thường kết hợp mTLS và chính sách định danh | Có mTLS vẫn phải phân quyền từng hành động |
| Service → DB/Redis/Broker | TLS với xác thực chứng chỉ | Private network không đủ thay thế TLS |
| DB volume, block storage | Mã hóa ở tầng đĩa hoặc dịch vụ lưu trữ | Không ngăn truy vấn trái phép qua ứng dụng đã có quyền |
| Trường dữ liệu nhạy cảm | Application-level AEAD và khóa tách biệt | Ảnh hưởng truy vấn, tìm kiếm, indexing |
| Snapshot/backup/export | Mã hóa riêng và quản lý quyền truy cập | Backup có thể có chính sách khóa và vòng đời khác dữ liệu chính |
| Khóa và private key | KMS/HSM/secret manager phù hợp; IAM, audit | Khóa mất hoặc bị hủy sớm có thể làm dữ liệu không thể khôi phục |

## 2. Mã hóa khi truyền: TLS bảo vệ một kết nối

**TLS (Transport Layer Security)** thiết lập kênh truyền được mã hóa giữa hai endpoint đã xác thực theo cách cấu hình. Nó giúp ngăn nghe lén và phát hiện thay đổi dữ liệu trong quá trình truyền.

Một kết nối TLS đúng cần:

- **Phiên bản và bộ mật mã hiện đại:** ưu tiên TLS 1.3, có thể duy trì TLS 1.2 với cấu hình mạnh khi cần tương thích; loại bỏ giao thức và bộ mật mã đã lỗi thời.
- **Xác minh chuỗi chứng chỉ:** endpoint phải kiểm tra CA được tin cậy, thời hạn hiệu lực và các ràng buộc chứng chỉ phù hợp.
- **Xác minh danh tính máy chủ:** tên DNS/IP đích phải phù hợp với SAN của chứng chỉ theo chính sách xác minh danh tính.
- **Không vô hiệu hóa kiểm tra chứng chỉ:** không dùng trust-all hoặc bỏ hostname verification để “sửa” lỗi kết nối trong production.
- **Quản lý chứng chỉ:** phát hành, phân phối, giám sát hạn sử dụng, thay mới trước khi hết hạn và có cách thu hồi.
- **Bảo vệ toàn bộ các chặng:** nếu TLS kết thúc ở load balancer, chặng từ load balancer đến service cần được đánh giá riêng; không suy ra end-to-end encryption chỉ từ biểu tượng HTTPS của trình duyệt.

Trong microservices, cần kiểm kê **north–south traffic** (người dùng/đối tác vào hệ thống) và **east–west traffic** (service gọi service). Ngoài HTTP, kết nối gRPC, JDBC, Redis, Kafka, message broker, object storage và dịch vụ quản trị cũng cần chính sách mã hóa phù hợp.

### TLS không phải là phân quyền

TLS có thể cho biết client đã kết nối đến endpoint đúng; mTLS còn có thể xác minh danh tính workload phía gọi. Nhưng sau bước xác thực, service vẫn phải kiểm tra: “Danh tính này có được xem hồ sơ khách hàng X hay gọi lệnh thanh toán Y không?”.

Ví dụ: Order Service có chứng chỉ hợp lệ để gọi Customer Service không đồng nghĩa nó được đọc tất cả hồ sơ hoặc xuất mọi dữ liệu cá nhân. Quyền phải giới hạn theo API, dữ liệu, phạm vi nghiệp vụ và nguyên tắc **least privilege**.

## 3. mTLS giữa các microservice

**Mutual TLS (mTLS)** yêu cầu cả hai phía cung cấp và xác minh chứng chỉ phù hợp. Đây là cơ chế phổ biến để xác thực định danh service/workload, nhất là trong môi trường nhiều service thay đổi địa chỉ theo thời gian.

~~~text
Order Service                         Payment Service
    |                                       |
    |----- ClientHello / bắt tay TLS ------>|
    |<---- Chứng chỉ của server ------------|
    |----- Chứng chỉ của client ----------->|
    |<---- Xác minh danh tính hai chiều ---->|
    |======= Kênh TLS được bảo vệ =========>|
    |      Gửi yêu cầu được phân quyền      |
~~~

Trình tự thực tế của handshake phụ thuộc phiên bản TLS và thư viện; sơ đồ chỉ thể hiện các trách nhiệm chính.

Có hai mô hình triển khai phổ biến:

**Trong ứng dụng:** mỗi service tự cấu hình TLS trust store, key store, kiểm tra peer và chứng chỉ. Cách này cho phép ứng dụng kiểm soát trực tiếp nhưng đòi hỏi đồng bộ cấu hình cho nhiều ngôn ngữ/thư viện.

**Qua service mesh hoặc proxy:** sidecar/proxy xử lý mTLS và luân chuyển workload certificate. Ứng dụng vẫn cần chính sách xác thực/phân quyền đúng và phải xác định rõ vị trí kết thúc TLS. Không coi cấu hình mesh là bằng chứng mọi cổng hoặc kết nối ngoài mesh đều đã được bảo vệ.

Thiết kế vận hành mTLS cần trả lời:

1. Ai phát hành chứng chỉ và CA nào được tin cậy?
2. Danh tính workload gắn với service account, namespace hoặc service identity ra sao?
3. Ai được gọi ai, trên endpoint nào? Có chính sách ủy quyền tương ứng không?
4. Chứng chỉ được thay mới tự động ra sao; nếu bị lộ hoặc hết hạn sẽ xử lý thế nào?
5. Với chuyển đổi dần sang mTLS bắt buộc, làm sao phát hiện kết nối vẫn còn plaintext mà không gây sự cố hàng loạt?

Không đưa private key vào Docker image, repository hoặc hệ thống log. Khóa riêng và chứng chỉ cần được cấp phát cho đúng workload, đúng phạm vi và có thể xoay vòng.

## 4. Mã hóa khi lưu: chọn đúng lớp bảo vệ

**Encryption at rest** áp dụng cho dữ liệu nằm trên phương tiện lưu trữ. Có nhiều lớp, giải quyết các rủi ro khác nhau.

### 4.1. Mã hóa ổ đĩa, volume và lưu trữ được quản lý

Các dịch vụ block/object storage và managed database thường hỗ trợ mã hóa storage. Đây là nền tảng quan trọng để giảm thiệt hại khi thất lạc ổ đĩa, snapshot hoặc bản sao vật lý. Cần xác nhận mặc định thực tế, phạm vi áp dụng và khóa được quản lý bởi ai.

Giới hạn: khi database đang hoạt động và ứng dụng có quyền đọc, engine có thể giải mã trong suốt cho truy vấn hợp lệ. Kẻ tấn công dùng thông tin đăng nhập DB hoặc khai thác ứng dụng vẫn có thể đọc dữ liệu. Mã hóa đĩa cũng không tự bảo đảm tất cả **database dump, export, log, temporary file, backup và replica** được bảo vệ.

### 4.2. Mã hóa ở tầng cơ sở dữ liệu

Transparent Data Encryption (TDE) mã hóa dữ liệu lưu trên đĩa theo cơ chế của database, thường ít ảnh hưởng đến ứng dụng. TDE hữu ích cho file dữ liệu và một số dạng log/backup theo khả năng của hệ quản trị.

TDE vẫn có giới hạn tương tự ở tầng truy vấn: người dùng hoặc ứng dụng có quyền SELECT sẽ có thể nhận plaintext. Nếu cần ngăn quản trị viên hạ tầng hoặc người truy cập database thô đọc một trường nhạy cảm, phải xem xét mã hóa ở tầng ứng dụng.

### 4.3. Mã hóa ở tầng ứng dụng hoặc từng trường

Ứng dụng mã hóa số định danh nhạy cảm, thông tin liên hệ hoặc trường bí mật **trước khi ghi vào database**, và chỉ giải mã khi một use case được phép yêu cầu.

Ưu điểm:

- Dữ liệu được mã hóa trước khi đi vào database; bản sao DB, dump và nhiều bản backup chỉ chứa ciphertext của trường đó.
- Có thể phân tách quyền dùng khóa giữa service và người quản trị database.
- Có thể áp dụng khóa theo tenant, loại dữ liệu hoặc miền nghiệp vụ.

Đổi lại:

- Không thể tìm kiếm, sắp xếp hoặc lập chỉ mục tùy ý trên ciphertext ngẫu nhiên như với plaintext.
- Phải quản lý metadata, khóa, phiên bản định dạng, quyền giải mã và quá trình migrate dữ liệu.
- Nếu service có quyền giải mã bị xâm nhập, dữ liệu mà service đó có quyền truy xuất vẫn có nguy cơ lộ.
- Bản plaintext vẫn có thể xuất hiện ở memory, logs, trace, response hoặc hệ thống downstream nếu không kiểm soát.

**Không tự xây cơ chế mã hóa xác định/deterministic encryption để “search cho tiện”**. Nó có thể làm lộ mẫu lặp, tần suất và các quan hệ giữa giá trị. Nếu cần tra cứu, phải thiết kế tokenization, chỉ mục riêng, blind index hoặc công nghệ tìm kiếm trên dữ liệu mã hóa với đánh giá an ninh cụ thể. Không dùng hash đơn giản của dữ liệu đoán được như email/CMND để coi như ẩn danh.

### 4.4. Kiểm kê dữ liệu bị bỏ quên

Bảng chính được mã hóa chưa đủ. Cần xem cả:

- Backup/snapshot, replica, file tạm, export CSV/Excel/PDF, tệp đính kèm và object storage.
- Queue, dead-letter queue (DLQ), event payload, outbox, cache và search index.
- Application log, audit log, distributed trace, APM, crash dump và debug endpoint.
- Pipeline dữ liệu, môi trường staging/test, dữ liệu sao chép phục vụ phân tích.
- Ổ đĩa laptop nhân viên, file tải xuống và đường truyền khi chuyển dữ liệu giữa vùng hoặc tài khoản.

Với mỗi bản sao, xác định chủ sở hữu, thời gian lưu, quyền truy cập, nhu cầu khôi phục, mã hóa và kế hoạch xóa.

## 5. Chọn nguyên thủy mật mã phù hợp

Không cần tự phát minh thuật toán. Hãy dùng thư viện được duy trì, API chuẩn, cấu hình đã được kiểm chứng và cơ chế quản lý khóa được hỗ trợ.

### Mã hóa dữ liệu: ưu tiên AEAD

**Authenticated Encryption with Associated Data (AEAD)** cung cấp tính bí mật và kiểm tra tính toàn vẹn cho ciphertext. Các lựa chọn phổ biến gồm **AES-GCM** hoặc **ChaCha20-Poly1305** khi hệ thống/thư viện hỗ trợ và chính sách cho phép.

Với AES-GCM:

- Khóa AES phải được sinh ngẫu nhiên bằng nguồn ngẫu nhiên mật mã và có độ dài hợp lệ (thường 128 hoặc 256 bit).
- **Nonce/IV cần duy nhất cho mỗi lần mã hóa dưới cùng một khóa**. Cách thông dụng là nonce 96 bit được sinh bằng CSPRNG, nhưng phải đánh giá nguy cơ trùng với lưu lượng và vòng đời khóa thực tế.
- GCM dùng authentication tag, thông dụng 128 bit. Khi tag không hợp lệ, phải coi là **giải mã thất bại**; không lấy plaintext “một phần” làm kết quả.
- **AAD** là thông tin không mã hóa nhưng được xác thực, chẳng hạn tenant ID, loại bản ghi, record ID hoặc phiên bản schema. AAD phải được tái tạo theo định dạng ổn định và lấy từ ngữ cảnh đáng tin cậy.
- Không tái sử dụng cùng cặp **(key, nonce)**; nguy cơ này đặc biệt nghiêm trọng với GCM.
- Cần lưu nonce, tag/ciphertext, phiên bản thuật toán, key ID và thông tin cần thiết để giải mã. Nonce không phải bí mật, nhưng không được thay đổi tùy ý.

Với hệ thống dữ liệu cực lớn hoặc mô hình sinh nonce khó bảo đảm, việc chọn sơ đồ mã hóa phải được chuyên gia mật mã đánh giá; không “sửa” GCM bằng cách dùng timestamp hoặc ID đoán được làm nonce.

### Hash, chữ ký và mã hóa là ba việc khác nhau

| Nhu cầu | Cơ chế |
| --- | --- |
| Giữ bí mật dữ liệu và giải mã khi có quyền | Encryption như AEAD |
| Lưu mật khẩu người dùng | **Password hashing** có salt và chi phí tính toán thích hợp (ví dụ Argon2id; thuật toán thay thế tùy hệ thống) |
| Kiểm tra thông điệp do chủ thể được phép ký | Digital signature/MAC theo mô hình tin cậy |
| Đối chiếu toàn vẹn file công khai | Hash mật mã, thường đi với chữ ký nếu cần xác thực nguồn |

Mật khẩu không nên được “mã hóa rồi giải mã lại” để xác thực. Dùng password hashing phù hợp; mỗi mật khẩu có salt ngẫu nhiên riêng và chính sách tăng chi phí theo thời gian.

Một JWT được **ký (JWS)** không có nghĩa payload đã được mã hóa. Không đưa dữ liệu bí mật vào payload chỉ vì token có chữ ký hoặc đang chạy trong mạng riêng; khi truyền vẫn cần TLS.

## 6. Tại sao quản lý khóa quyết định hiệu quả mã hóa?

Khóa mã hóa là tài sản có mức nhạy cảm cao. Những sai lầm thường khiến mã hóa trở nên vô nghĩa gồm:

- Lưu khóa trong cùng bảng chứa ciphertext hoặc trong repository.
- Dùng một khóa chung cho tất cả service, tenant, môi trường và loại dữ liệu.
- Cấp quyền giải mã rộng hơn nhu cầu nghiệp vụ.
- Không lưu phiên bản khóa, không biết bản ghi nào dùng khóa nào.
- Không có quy trình xoay khóa, xử lý lộ khóa hoặc phục hồi dữ liệu từ backup.
- Ghi khóa, token, plaintext hoặc payload nhạy cảm vào log khi có lỗi.

Các trách nhiệm điển hình của **KMS** (Key Management Service) và **HSM** (Hardware Security Module) gồm bảo vệ key material, kiểm soát truy cập, hỗ trợ thao tác mật mã hoặc bọc/mở khóa, lưu audit và chính sách vòng đời. HSM cung cấp ranh giới bảo vệ khóa bằng phần cứng với những thuộc tính phụ thuộc thiết bị/dịch vụ. Không phải mọi KMS đều có cùng API, giới hạn, SLA hoặc chế độ export khóa.

**Secret manager** phù hợp lưu trữ/phân phối nhiều loại bí mật vận hành như DB credential, API key và private key theo cơ chế có kiểm soát. Không đánh đồng nó với khóa mã hóa dữ liệu: khóa mã hóa cần thêm phiên bản, chính sách cryptographic usage, rotation, recovery và định dạng ciphertext.

### Phân quyền theo trách nhiệm

Ví dụ:

- Order Service có quyền **mã hóa và giải mã** một tập trường đơn hàng mà nó sở hữu.
- Notification Service chỉ nhận thông tin cần gửi thông báo, không có quyền giải mã toàn bộ hồ sơ thanh toán.
- Nhân viên vận hành có thể theo dõi tình trạng KMS nhưng không có quyền xuất hoặc sử dụng khóa để đọc plaintext.
- Quyền sửa chính sách khóa, quyền dùng khóa và quyền xóa khóa được tách biệt; thao tác nhạy cảm cần audit.

Quyền truy cập KMS chỉ là một lớp. Ứng dụng vẫn phải xác thực người dùng và kiểm tra quyền ở mức record/use case **trước khi yêu cầu giải mã**.

## 7. Envelope encryption: phân tách khóa dữ liệu và khóa bảo vệ khóa

**Envelope encryption** là mẫu rất hữu ích trong microservices.

- **DEK (Data Encryption Key)**: khóa dùng để mã hóa dữ liệu thực tế, ví dụ AES-256-GCM.
- **KEK (Key Encryption Key)**: khóa bảo vệ/bọc DEK, thường được giữ và kiểm soát bởi KMS.
- **Wrapped DEK**: bản DEK đã được bọc bằng KEK, có thể lưu cùng ciphertext nếu chính sách cho phép.

~~~text
                  KMS / KEK
                     |
               Generate data key
                     |
       +-------------+-------------+
       |                           |
   Plaintext DEK                Wrapped DEK
       |                           |
  AES-GCM encrypt                  |
       |                           |
   Ciphertext + Nonce + Tag + Wrapped DEK + Key ID
                     |
                   Storage

Giải mã:
Đọc envelope -> KMS unwrap DEK theo quyền -> AES-GCM decrypt
             -> Kiểm tra authentication tag/AAD -> Plaintext
~~~

Một luồng ghi điển hình:

1. Service đã xác thực và được phân quyền cho thao tác ghi.
2. Service yêu cầu một DEK hoặc nhận DEK qua cơ chế KMS hỗ trợ.
3. Service mã hóa plaintext bằng AEAD với nonce duy nhất, AAD ổn định.
4. Service ghi ciphertext, nonce, key ID, wrapped DEK, phiên bản định dạng và metadata bắt buộc vào storage.
5. Service hạn chế thời gian plaintext/DEK tồn tại trong bộ nhớ và không đưa chúng vào log.

Một luồng đọc:

1. Kiểm tra người gọi có quyền đọc đúng dữ liệu và có nhu cầu giải mã.
2. Đọc envelope; xác thực version/algorithm/metadata theo chính sách.
3. Gọi KMS unwrap DEK với định danh workload có thẩm quyền.
4. Giải mã bằng AEAD và AAD đúng ngữ cảnh; tag sai phải thất bại.
5. Chỉ sử dụng plaintext trong phạm vi cần thiết, không đẩy sang log/trace hoặc service không có quyền.

Envelope encryption giảm nhu cầu đưa KEK ra khỏi miền quản lý khóa; cũng cho phép thay KEK và **rewrap DEK** trong những điều kiện phù hợp mà không nhất thiết phải giải mã toàn bộ dữ liệu bằng khóa dữ liệu mới. Tuy nhiên, **đổi KEK không đồng nghĩa đổi DEK**. Nếu DEK đã lộ thì chỉ rewrap chưa xử lý rủi ro: phải tạo DEK mới và mã hóa lại dữ liệu chịu ảnh hưởng.

Một cấu trúc lưu trữ minh họa:

~~~json
{
  "formatVersion": 1,
  "algorithm": "AES-256-GCM",
  "keyId": "orders-prod-key-v3",
  "wrappedDek": "<base64-wrapped-key>",
  "nonce": "<base64-random-nonce>",
  "ciphertext": "<base64-ciphertext-with-tag>",
  "aadSchema": "orders-field-v1"
}
~~~

Chuỗi trong dấu ngoặc nhọn chỉ là placeholder, không phải khóa thật. Trong hệ thống thực tế có thể dùng khóa chung một cấp, DEK theo bản ghi hoặc DEK theo nhóm dữ liệu; lựa chọn phụ thuộc độ nhạy, giới hạn gọi KMS, quy mô, yêu cầu tách tenant, chi phí và chính sách xoay khóa.

## 8. Ví dụ Java: mã hóa trường dữ liệu bằng AES-GCM

Ví dụ sau minh họa primitive mã hóa/giải mã. **SecretKey phải đến từ dịch vụ quản lý khóa hoặc lớp cung cấp DEK được tin cậy**; mã không sinh một khóa cố định, không nhúng khóa vào source và không tự triển khai KMS.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

record EncryptedField(
    String algorithm,
    String keyVersion,
    String nonceB64,
    String ciphertextB64
) {}

public final class FieldEncryption {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";

    private FieldEncryption() {}

    public static EncryptedField encrypt(
        String plaintext,
        SecretKey dek,
        String keyVersion,
        byte[] aad
    ) throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(
            Cipher.ENCRYPT_MODE,
            dek,
            new GCMParameterSpec(TAG_BITS, nonce)
        );
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(
            plaintext.getBytes(StandardCharsets.UTF_8)
        );

        return new EncryptedField(
            "AES-256-GCM",
            keyVersion,
            Base64.getEncoder().encodeToString(nonce),
            Base64.getEncoder().encodeToString(ciphertextAndTag)
        );
    }

    public static String decrypt(
        EncryptedField value,
        SecretKey dek,
        byte[] aad
    ) throws GeneralSecurityException {
        if (!"AES-256-GCM".equals(value.algorithm())) {
            throw new GeneralSecurityException("Unsupported algorithm");
        }

        byte[] nonce = Base64.getDecoder().decode(
            value.nonceB64()
        );
        if (nonce.length != NONCE_BYTES) {
            throw new GeneralSecurityException("Invalid nonce");
        }

        byte[] ciphertextAndTag = Base64.getDecoder().decode(
            value.ciphertextB64()
        );

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(
            Cipher.DECRYPT_MODE,
            dek,
            new GCMParameterSpec(TAG_BITS, nonce)
        );
        cipher.updateAAD(aad);

        byte[] plaintext = cipher.doFinal(ciphertextAndTag);
        return new String(plaintext, StandardCharsets.UTF_8);
    }
}
~~~

Ví dụ giả định DEK là **khóa AES 256 bit** được KMS cấp và ánh xạ đúng với keyVersion. Java thường gắn authentication tag vào phần cuối ciphertext trả bởi doFinal đối với GCM.

Khi tích hợp thật:

- **Không truyền keyVersion do client tùy ý chọn** để có thể ép hệ thống dùng khóa yếu hoặc khóa khác miền. Service phải chọn khóa theo chính sách và ghi phiên bản đã dùng.
- Cấu trúc EncryptedField chỉ minh họa; envelope hoàn chỉnh còn cần wrapped DEK hoặc cơ chế tra cứu khóa an toàn, version định dạng và các trường metadata.
- AAD nên gắn với ngữ cảnh bản ghi được xác thực, ví dụ tenant ID + loại trường + record ID. Định dạng byte phải có quy ước rõ ràng để tránh nhập nhằng.
- Khi chuyển bản ghi sang tenant/record khác, AAD cũ sẽ không còn khớp: đây là bảo vệ có chủ đích. Việc migrate dữ liệu cần giải mã và mã hóa lại theo chính sách.
- Ciphertext bị sửa, AAD sai hoặc DEK không đúng sẽ khiến xác thực GCM thất bại. **Không thử giải mã bằng chế độ bỏ qua authentication tag và không trả plaintext mặc định.**
- Validate Base64, kích thước payload, metadata và format version ở biên API; bắt và ánh xạ ngoại lệ phù hợp nhưng không tiết lộ plaintext hoặc thông tin khóa trong response.
- Trong hệ thống lớn, sử dụng SDK/thư viện envelope encryption có hỗ trợ KMS, version, rotation và memory handling; đoạn code trên là minh họa về API AEAD, chưa phải một dịch vụ mã hóa production hoàn chỉnh.

### Ràng buộc AAD với đúng tenant và bản ghi

Ví dụ Order Service tạo AAD từ các giá trị **đã được xác thực ở backend**:

~~~java
byte[] aad = (
    "tenant=" + authenticatedTenantId + "\n" +
    "type=order.privateNote\n" +
    "order=" + persistedOrderId
).getBytes(StandardCharsets.UTF_8);
~~~

Không tạo AAD từ tenant ID do client gửi mà chưa xác thực; nếu không, kẻ tấn công có thể thử tráo dữ liệu giữa các phạm vi truy cập. AAD không được mã hóa, nên chỉ đặt metadata phù hợp và không coi AAD là nơi giấu bí mật.

## 9. Vòng đời khóa: tạo, dùng, luân chuyển, thu hồi, hủy

Một khóa không chỉ có trạng thái “có/không”. Nên quản lý vòng đời rõ ràng:

| Giai đoạn | Quyết định cần có |
| --- | --- |
| Tạo khóa | Ai được tạo? Thuật toán, độ dài và nguồn ngẫu nhiên nào? Dùng cho tenant/miền dữ liệu nào? |
| Kích hoạt | Workload nào được encrypt/decrypt? Có tách production khỏi test không? |
| Sử dụng | Có audit, hạn mức, kiểm soát truy cập và version trong ciphertext không? |
| Luân chuyển | Khi nào ngừng mã hóa dữ liệu mới bằng khóa cũ? Dữ liệu cũ được rewrap hay re-encrypt? |
| Ngừng dùng để ghi | Khóa cũ có còn được decrypt trong thời gian chuyển tiếp/khôi phục backup không? |
| Thu hồi do sự cố | Phạm vi dữ liệu ảnh hưởng, chính sách ngắt truy cập, thay khóa, kiểm toán và thông báo ra sao? |
| Hủy cuối cùng | Đã hết retention và không còn bản backup/dữ liệu phụ thuộc khóa chưa? Ai phê duyệt? |

### Rotation khác với re-encryption

**Rotate KEK:** chuyển sang key version mới cho việc bọc DEK; các wrapped DEK cũ có thể cần rewrap theo khả năng KMS, mô hình khóa và chính sách của hệ thống. Cơ chế tự động luân chuyển của nhà cung cấp không mặc nhiên cập nhật metadata hoặc mọi ciphertext ứng dụng đã lưu.

**Rotate DEK:** tạo khóa dữ liệu mới và mã hóa lại các bản ghi hoặc nhóm bản ghi theo phạm vi tương ứng. Đây là hoạt động có thể nặng về I/O và cần migration theo lô, retry an toàn, giới hạn tải, khả năng tiếp tục sau gián đoạn và quan sát tiến độ.

**Rotate TLS certificate/private key:** phát hành cặp khóa/chứng chỉ mới, phân phối trust chain hợp lệ, cho phép giai đoạn chuyển tiếp và loại bỏ chứng chỉ cũ khi client đã cập nhật. Không để certificate expiry biến thành outage toàn hệ thống.

**Thu hồi do lộ khóa:** đánh giá xem plaintext có khả năng bị truy xuất hay không; khóa đã lộ vẫn có thể giải mã dữ liệu lịch sử nếu ciphertext cũ còn tồn tại. Chỉ đổi key ID hoặc thay KEK trong khi DEK cũ bị lộ sẽ không đủ.

**Hủy khóa / crypto-shredding:** có thể làm dữ liệu không thể giải mã, nhưng đây là hành động khó đảo ngược. Phải tính cả backup, retention, pháp lý và khả năng phục hồi. Không xóa khóa trước khi chắc chắn dữ liệu cần lưu đã được chuyển và kiểm chứng.

### Chiến lược đổi khóa không gián đoạn

Một mẫu rollout thường dùng:

1. Tạo và phê duyệt phiên bản khóa mới.
2. Bắt đầu **ghi mới bằng khóa mới**, vẫn có quyền đọc dữ liệu bằng khóa cũ.
3. Migrate/rewrap/re-encrypt dữ liệu cũ theo lô có checkpoint.
4. Đo số bản ghi còn tham chiếu khóa cũ, kiểm tra khôi phục từ backup.
5. Chuyển khóa cũ sang chỉ-đọc/không dùng cho encrypt mới.
6. Chỉ hủy khi hết mọi phụ thuộc và đáp ứng chính sách retention.

Cần lưu key ID/version và định dạng envelope trên từng bản ghi hoặc một catalog đáng tin cậy. Không dựa vào giả định “mọi bản ghi đều dùng khóa mới nhất”.

## 10. Phân tách khóa và ranh giới tin cậy trong microservices

Nếu mọi service đều nhận cùng một khóa, xâm nhập một service có thể mở rộng thành sự cố toàn bộ dữ liệu. Thiết kế nên chia khóa theo **miền dữ liệu, môi trường, mức nhạy cảm và ranh giới quản trị**.

Một phương án minh họa:

| Thành phần | Dữ liệu cần giữ bí mật | Quyền khóa phù hợp |
| --- | --- | --- |
| Customer Service | Hồ sơ và thông tin liên hệ khách hàng | Chỉ khóa/dữ liệu thuộc miền Customer |
| Payment Service | Token/cấu phần thanh toán được phép lưu | Chỉ khóa/dữ liệu thuộc miền Payment; tuân thủ tiêu chuẩn thanh toán áp dụng |
| Order Service | Ghi chú hoặc nội dung đơn hàng nhạy cảm | Chỉ khóa/dữ liệu thuộc miền Order |
| Notification Service | Nội dung tối thiểu để gửi thông báo | Không có quyền mở khóa hồ sơ thanh toán |
| Analytics Service | Dữ liệu đã giảm thiểu danh tính/tổng hợp | Quyền theo tập dữ liệu được phê duyệt, tránh mặc định toàn quyền giải mã |

Khi service cần chia sẻ dữ liệu với service khác, ưu tiên API đã phân quyền, tokenization hoặc sự kiện đã giảm thiểu thông tin nhạy cảm. Tránh chia sẻ DEK cho nhiều service chỉ để giảm số lời gọi API.

Các yếu tố cần bảo vệ bên cạnh KMS policy:

- Identity của workload và cơ chế cấp credential ngắn hạn.
- IAM/role trên service, KMS, database, object storage và backup.
- Network policy hạn chế endpoint có thể gọi.
- Không dùng tài khoản quản trị chung cho mọi môi trường.
- Audit tất cả thao tác nhạy cảm như đổi policy, vô hiệu khóa, decrypt bất thường.
- Quy trình break-glass có phê duyệt, thời hạn, ghi nhận lý do và hậu kiểm.

## 11. Tích hợp với Spring Boot và vận hành service

Với ứng dụng Java/Spring Boot, có thể tách các trách nhiệm:

~~~text
Controller / API Handler
          |
   Application Service
          |
     Data Protection
     (encrypt/decrypt)
          |
     Key Provider -----> KMS / HSM
          |
     Repository --------> Encrypted DB field

HTTP/gRPC client ------> TLS/mTLS config and peer validation
Secrets/certificates --> Runtime secret delivery / rotation
Logs/Metrics/Tracing --> Sanitized telemetry
~~~

**Data Protection component** nhận yêu cầu mã hóa/giải mã ở ranh giới nghiệp vụ, biết schema và AAD; **Key Provider** quản lý việc lấy DEK/unwrap theo key ID và môi trường; **Repository** lưu ciphertext/envelope. Cách phân tách này giảm việc mỗi controller tự thao tác với Cipher hoặc tự đọc bí mật từ file.

Ứng dụng cần cấu hình và kiểm thử:

- HTTPS/TLS inbound và TLS outbound đến từng phụ thuộc; trust store không chứa CA không cần thiết.
- Hostname verification luôn bật; certificate validation phải thất bại khi gặp peer sai.
- Chứng chỉ/client private key được cấp phát an toàn ở runtime; password của key store không được nằm trong mã nguồn.
- Tự động làm mới chứng chỉ và kiểm thử handshake sau thay khóa/chứng chỉ.
- Timeout, connection pool, retry có giới hạn và chính sách fail-safe khi KMS không khả dụng.
- Thông báo lỗi rõ cho client khi chức năng cốt lõi không thể thực hiện; không ghi stack trace chứa bí mật.

Bí mật trong environment variable có thể là phương thức cấp tạm, nhưng vẫn có nguy cơ lộ qua dump, công cụ vận hành hoặc log. Với production, ưu tiên cơ chế cấp bí mật ở runtime có kiểm soát quyền và luân chuyển; tuyệt đối không đưa giá trị bí mật vào application.yml đã commit.

## 12. Khi TLS, KMS hoặc quá trình giải mã gặp lỗi

Cơ chế bảo mật phải có hành vi lỗi rõ ràng. “Cho phép plaintext để hệ thống tiếp tục chạy” thường là lỗi thiết kế nghiêm trọng.

| Sự cố | Hành vi an toàn nên chọn |
| --- | --- |
| TLS certificate hết hạn hoặc sai tên | Từ chối kết nối; phát cảnh báo và khôi phục chứng chỉ |
| Peer certificate không thuộc trust domain | Không bỏ qua kiểm tra; điều tra cấu hình hoặc danh tính |
| KMS tạm không khả dụng khi cần encrypt/decrypt | Dừng thao tác cần dữ liệu nhạy cảm, trả lỗi có kiểm soát hoặc giữ tác vụ chờ nếu đã nhận bền vững |
| KMS từ chối vì thiếu quyền | Không dùng khóa dự phòng rộng quyền; ghi audit và sửa policy qua quy trình chuẩn |
| Ciphertext bị sửa, tag GCM sai hoặc AAD không khớp | Coi dữ liệu không xác thực; từ chối giải mã, điều tra nguồn |
| Khóa cũ không tìm thấy khi đọc backup | Kích hoạt quy trình phục hồi khóa/backup theo chính sách; không đoán khóa khác |
| Xác nhận khóa đã lộ | Khoanh vùng, thu hồi quyền, đổi khóa liên quan, đánh giá dữ liệu lịch sử |
| Chuyển khóa mới nhưng còn service cũ | Duy trì cơ chế đọc tương thích có giới hạn; rollout và migrate theo phiên bản |

Có thể dùng cache DEK ngắn hạn trong bộ nhớ ở một số mô hình để giảm độ trễ và số lượt gọi KMS, nhưng cần đánh giá **quyền truy cập, phạm vi cache, thời gian tồn tại, phương án thu hồi và rủi ro khi service bị xâm nhập**. Không cache khóa plaintext ra disk hoặc chia sẻ một key cache toàn cluster tùy tiện.

Với tác vụ thanh toán hoặc thay đổi dữ liệu quan trọng, nếu không thể thực hiện mã hóa/giải mã cần thiết, chọn **fail closed** hoặc trạng thái chờ đã được ghi bền vững. Không âm thầm lưu plaintext, không dùng khóa tạm cố định, không tự động chuyển sang cấu hình “insecure”.

## 13. Quan sát, cảnh báo và khả năng kiểm toán

Mã hóa đúng về thuật toán nhưng quản lý kém vẫn dễ gây sự cố. Các tín hiệu cần theo dõi gồm:

- **TLS:** số handshake failures, lỗi xác minh chứng chỉ, chứng chỉ sắp hết hạn, tỉ lệ kết nối dùng phiên bản/giao thức không đáp ứng chính sách.
- **mTLS:** tỷ lệ lưu lượng giữa service được bảo vệ, kết nối không có workload identity hợp lệ, sự kiện cấp/luân chuyển chứng chỉ.
- **KMS:** độ trễ encrypt/decrypt/unwrap, lỗi từ chối quyền, giới hạn tốc độ, unavailable, số lượng yêu cầu bất thường theo service hoặc loại thao tác.
- **Encryption at rest:** tỷ lệ dữ liệu/backup được mã hóa, số bản ghi còn dùng key version cũ, lỗi migrate/rewrap.
- **Data protection:** thất bại kiểm tra AEAD tag, lỗi AAD/schema, truy cập trái phép vào trường nhạy cảm, sự kiện lộ bí mật cần xử lý.

Tín hiệu phải đủ để vận hành mà **không ghi plaintext, mật khẩu, token, DEK, private key hoặc payload nhạy cảm**. Key ID có thể dùng cho audit theo chính sách; không đưa giá trị có cardinality rất cao hoặc thông tin định danh không cần thiết vào metric labels.

Cảnh báo nên phân biệt hai nhóm: sự cố có thể ngăn kết nối/giải mã hợp lệ và sự kiện có khả năng xâm phạm bảo mật. Thiết lập runbook cho các tình huống chứng chỉ hết hạn, KMS không khả dụng, quyền key bị đổi sai, phát hiện decrypt bất thường, xóa khóa nhầm và khôi phục dữ liệu mã hóa từ backup.

## 14. Kiểm thử bảo mật và khả năng phục hồi

Kiểm thử không chỉ có trường hợp encrypt rồi decrypt trả lại dữ liệu ban đầu. Các kịch bản quan trọng:

1. **TLS server sai SAN hoặc CA không tin cậy:** client từ chối kết nối.
2. **mTLS không có client certificate hoặc dùng identity sai:** chỉ endpoint theo chính sách mới cho phép.
3. **TLS kết thúc ở gateway:** xác nhận các chặng còn lại được bảo vệ theo thiết kế.
4. **Thay nonce, ciphertext, tag hoặc AAD:** giải mã thất bại; không trả plaintext phần còn lại.
5. **Chép ciphertext sang tenant khác:** ứng dụng từ chối theo phân quyền và kiểm tra AAD.
6. **KMS chặn quyền decrypt:** service không dùng credential quyền cao hơn để vượt qua.
7. **KMS timeout/quota:** không tự ghi plaintext; deadline và retry không làm cạn tài nguyên.
8. **Rotation:** dữ liệu mới dùng key version mới, dữ liệu lịch sử vẫn đọc được trong thời gian chuyển tiếp.
9. **Khôi phục từ backup cũ:** key version tương ứng vẫn còn theo retention và quyền truy cập hợp lệ.
10. **Rò rỉ log:** trace, exception, debug và audit không lộ dữ liệu nhạy cảm.
11. **Lưu dữ liệu vào cache/queue/export:** các bản sao tuân thủ chính sách mã hóa và vòng đời.
12. **Tải lớn:** giới hạn yêu cầu KMS, pool kết nối và thiết kế cache không gây thắt cổ chai.

Với crypto primitives, ưu tiên test vector từ nguồn đáng tin cậy và thư viện được kiểm chứng; với hệ thống, dùng integration test và fault injection có kiểm soát để xác nhận chính sách quyền, lỗi và khôi phục.

## 15. Những ngộ nhận thường gặp

**“Có HTTPS ở Gateway nghĩa là toàn bộ hệ thống được mã hóa.”** TLS bảo vệ từng chặng. Nếu gateway gửi HTTP đến service phía sau, chặng sau không được hưởng bảo vệ của kết nối HTTPS ban đầu.

**“Nội bộ Kubernetes/VPC thì không cần TLS.”** Mạng riêng là một lớp giảm rủi ro, không bảo đảm không có workload bị xâm nhập, sai cấu hình hay lưu lượng bị quan sát.

**“Có mTLS nghĩa là service gọi được mọi API.”** mTLS xác thực workload, không thay thế chính sách ủy quyền theo hành động hoặc dữ liệu.

**“Bật TDE thì DBA hoặc ứng dụng có quyền truy vấn không thể đọc dữ liệu.”** TDE chủ yếu bảo vệ tầng lưu trữ; ứng dụng được quyền đọc vẫn nhận plaintext.

**“Mã hóa mật khẩu rồi lưu khóa riêng là đủ.”** Xác thực mật khẩu cần password hashing với salt và tham số phù hợp, không cần khả năng giải mã mật khẩu gốc.

**“Chỉ cần đổi key ID là đã rotate khóa.”** Rotation phải thay vật liệu khóa hoặc cơ chế bảo vệ đúng, quản lý dữ liệu cũ và kiểm soát thời gian lưu.

**“Ciphertext luôn có thể giải mã với khóa mới nhất.”** Dữ liệu lịch sử thường gắn với key version cụ thể; cần metadata và khả năng truy xuất phiên bản tương ứng.

**“Mất KMS thì tạm tắt mã hóa.”** Đây là fail-open làm hỏng cam kết bảo mật; khi không thể bảo vệ dữ liệu, không được lưu hoặc truyền plaintext như một phương án dự phòng mặc định.

**“AES-GCM chỉ cần nonce ngẫu nhiên, có trùng cũng không sao.”** Trùng nonce dưới cùng khóa có thể phá vỡ an toàn của GCM; phải quản lý nonce, phạm vi và vòng đời khóa nghiêm túc.

## 16. Quy trình triển khai vào một microservice mới

Một trình tự thực tế:

1. **Phân loại dữ liệu.** Xác định bí mật, dữ liệu cá nhân, token, metadata, thời hạn lưu và quy định áp dụng.
2. **Vẽ data flow.** Liệt kê mọi chặng truyền, chỗ lưu, bản sao, backup và bên nhận dữ liệu.
3. **Định nghĩa threat model.** Ai có thể lấy lưu lượng, storage, credential hoặc xâm nhập service? Mức bảo vệ kỳ vọng là gì?
4. **Bật TLS tại mọi điểm cần thiết.** Kiểm chứng peer identity, CA, SAN và cipher policy; áp dụng mTLS cho workload khi thiết kế cần.
5. **Chọn lớp at-rest.** Mã hóa storage/DB làm nền; dùng application-level encryption với dữ liệu cần ranh giới bảo vệ sâu hơn.
6. **Chọn AEAD và schema envelope.** Định nghĩa algorithm, version, nonce, tag, AAD, key version và cách lưu.
7. **Thiết kế chính sách khóa.** KMS/HSM, DEK/KEK, tách tenant/service/environment, quyền, audit, backup và quy trình break-glass.
8. **Thiết kế rotation và recovery.** Quy định thời hạn, khả năng rewrap/re-encrypt, thao tác với dữ liệu lịch sử và điều kiện hủy khóa.
9. **Thiết kế fail-safe.** KMS lỗi, chứng chỉ sai, ciphertext bị sửa, khóa không tồn tại đều có phản hồi rõ và không làm lộ dữ liệu.
10. **Kiểm thử và quan sát.** Chạy thử việc từ chối kết nối, cấm quyền, đổi khóa, khôi phục backup và cảnh báo chứng chỉ.
11. **Đánh giá trước khi vận hành.** Kiểm tra cả logs, queues, exports, cache và dữ liệu test; cập nhật runbook và trách nhiệm từng nhóm.

## 17. Tình huống thực hành

Hệ thống có ba service: Customer, Order và Notification. Customer lưu số điện thoại; Order cần hiển thị một phần số điện thoại cho nhân viên được phân quyền; Notification gửi SMS qua nhà cung cấp bên ngoài. Tất cả chạy trong một cụm Kubernetes, dùng chung database và có backup hằng ngày.

Hãy đề xuất:

- Những kết nối nào cần TLS/mTLS? Nếu API Gateway terminate TLS, cần kiểm tra điều gì ở chặng phía sau?
- Nên mã hóa số điện thoại tại storage, tại application hay cả hai? Phần nào vẫn có khả năng nhìn thấy plaintext?
- Service nào nên có quyền gọi KMS decrypt? Có cần chia sẻ cùng một DEK giữa ba service không?
- Cách giới hạn dữ liệu gửi cho Notification và nhà cung cấp SMS như thế nào?
- Khi Customer rotate key, làm sao Order vẫn đọc được dữ liệu cũ trong thời gian chuyển đổi?
- Nếu KMS ngừng hoạt động, hành vi nào là an toàn cho thao tác xem và gửi thông báo?

**Hướng giải minh họa:** TLS bảo vệ mọi chặng bên ngoài và giữa các service theo chính sách; mTLS xác thực workload nếu được áp dụng. Storage encryption bảo vệ volume/backup, còn application-level AEAD giúp giảm quyền đọc số điện thoại từ database thô. Customer sở hữu quyền giải mã và có thể cung cấp API trả số điện thoại đã che bớt cho Order; Notification chỉ nhận thông tin tối thiểu được phép để gửi SMS, với kênh truyền bảo vệ và hợp đồng dữ liệu rõ. Rotation lưu key ID/version, thực hiện ghi khóa mới và đọc khóa cũ tạm thời; khi KMS không khả dụng, không tự bỏ mã hóa hoặc trả dữ liệu không được xác thực, mà từ chối an toàn hoặc xử lý chờ theo một luồng đã được thiết kế.

---

**Điểm cần nhớ:** Bảo mật dữ liệu trong microservices là một hệ thống các ranh giới tin cậy. **TLS bảo vệ đường truyền; mã hóa at rest bảo vệ các bản sao được lưu; quản lý khóa kiểm soát ai có thể biến ciphertext thành plaintext.** Chỉ khi cả ba lớp được thiết kế cùng định danh, phân quyền, khả năng vận hành và vòng đời dữ liệu thì mã hóa mới mang lại hiệu quả bảo vệ thực tế.
