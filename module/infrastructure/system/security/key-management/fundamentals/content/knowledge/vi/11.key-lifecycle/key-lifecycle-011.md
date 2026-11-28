# Suspend key — Tạm đình chỉ sử dụng khóa trong vòng đời mật mã

## 1. Suspend key là gì?

**Suspend key** là hành động **tạm đình chỉ quyền sử dụng một khóa mật mã** theo chính sách, thường để điều tra sự cố, ngăn tác động của cấu hình sai, thực hiện thay đổi kiểm soát hoặc hạn chế rủi ro trong lúc chưa đủ thông tin để quyết định thu hồi hay hủy khóa.

Trong mô hình **key lifecycle (vòng đời khóa)**, khóa có thể ở trạng thái **Suspended**: vật liệu khóa vẫn được quản lý và có thể còn tồn tại trong keystore, KMS hoặc HSM, nhưng các thao tác sử dụng mật mã bị **từ chối theo chính sách đình chỉ**. Trạng thái này thường **có thể đảo ngược** sau một quy trình phê duyệt và xác minh phù hợp; trái lại, **destroy** là bước tiêu hủy vật liệu khóa và thường không thể đảo ngược.

Ví dụ: hệ thống ký hóa đơn phát hiện nhiều yêu cầu `Sign` từ một service account ngoài lịch phát hành. Đội ứng cứu tạm đình chỉ signing key và quyền của service account để ngăn chữ ký mới trong lúc phân tích log. Nếu điều tra kết luận khóa riêng chưa bị lộ và nguyên nhân đã được khắc phục, tổ chức có thể cân nhắc khôi phục theo phê duyệt. Nếu private key đã bị đánh cắp, **không được chỉ mở lại khóa cũ** rồi coi sự cố đã được giải quyết.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề này kết nối toàn bộ chu trình **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy** với mật mã đối xứng/bất đối xứng, chữ ký số, HMAC, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Nguyên tắc:** Suspend là **quyết định quản trị phải được cưỡng chế tại đường sử dụng khóa**. Chỉ ghi `status=SUSPENDED` vào database mà KMS/HSM vẫn chấp nhận `Sign`, `Decrypt` hoặc `Unwrap` thì khóa **chưa thực sự bị đình chỉ theo mục tiêu bảo mật**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Suspend**, **Disable**, **Deactivate**, **Revoke**, **Compromised** và **Destroy**.
2. Xác định thao tác nào phải chặn ngay và tác động tới dữ liệu/chữ ký/phiên đã tạo.
3. Thiết kế quy trình đình chỉ và khôi phục khóa có **IAM, phê duyệt, audit, fail closed**.
4. Hiểu hậu quả của việc disable **KEK, DEK, signing key, HMAC key, static ECDH key** trong hệ thống thật.
5. Xây dựng runbook ứng cứu, kế hoạch cutover và kiểm thử âm tính qua API KMS/HSM.

## 2. Suspend nằm ở đâu trong key lifecycle?

Một mô hình vòng đời phổ biến phân biệt các trạng thái logic như **Pre-activation, Active, Suspended, Deactivated, Compromised và Destroyed**. Tên gọi, những phép chuyển trạng thái được cho phép và khả năng phục hồi phụ thuộc chính sách quản lý khóa và hệ thống thực thi; sơ đồ dưới đây **mang tính khái niệm**, không phải giao diện chung của mọi KMS.

~~~mermaid
stateDiagram-v2
    [*] --> PreActivation: Tạo/thiết lập khóa
    PreActivation --> Active: Phê duyệt kích hoạt
    Active --> Suspended: Rủi ro/chính sách/yêu cầu khẩn
    Suspended --> Active: Đánh giá an toàn + phê duyệt
    Suspended --> Deactivated: Ngừng dùng chính thức
    Suspended --> Compromised: Xác nhận hoặc kết luận bị lộ
    Active --> Deactivated: Kết thúc dùng cho nghiệp vụ mới
    Active --> Compromised: Phát hiện compromise
    Deactivated --> Destroyed: Hết phụ thuộc và retention
    Compromised --> Destroyed: Ứng cứu + tiêu hủy theo quy trình
    PreActivation --> Destroyed: Hủy trước kích hoạt
    Destroyed --> [*]
~~~

**Không phải tất cả các chuyển trạng thái trong sơ đồ đều được phép ở mọi tiêu chuẩn hay sản phẩm.** Ví dụ một chính sách có thể không cho đưa khóa đã *compromised* về active nữa; trạng thái này không nên được khôi phục chỉ bằng một nút “Enable”.

### Bảng phân biệt trạng thái và hành động

| Khái niệm | Ý nghĩa | Tính đảo ngược | Ví dụ |
| --- | --- | --- | --- |
| **Suspend** | Tạm chặn khả năng sử dụng khóa theo mục tiêu/chính sách | Có thể, sau đánh giá | Dừng `Sign` khi nghi lạm dụng |
| **Disable** | Thao tác hoặc trạng thái sản phẩm KMS/HSM chặn những operation mà sản phẩm quy định | Tùy sản phẩm | KMS resource thành `Disabled` |
| **Deactivate** | Khóa nghỉ dùng theo vòng đời, đặc biệt không dùng tạo bảo vệ mới | Tùy chính sách; thường là giai đoạn kết thúc | Ngừng `Encrypt` bằng DEK v1, có thể cần `Decrypt` dữ liệu cũ |
| **Revoke permission/grant** | Thu hồi quyền của một principal hoặc một capability | Có thể cấp lại sau phê duyệt | Thu hồi quyền `kms:Sign` của workload bị chiếm |
| **Revoke certificate** | Thay đổi trạng thái tin cậy của chứng thư trong PKI | Thường không xem là chỉ “tạm pause” đơn giản | Thu hồi chứng thư ký đã lộ khóa |
| **Compromised** | Khóa không còn đáp ứng giả định bí mật/tính toàn vẹn hoặc được xử lý như đã lộ | **Không khôi phục niềm tin bằng bật lại** | Private key bị sao chép ra ngoài |
| **Destroy** | Tiêu hủy vật liệu khóa theo cơ chế được thẩm định | Thường không thể đảo ngược | Xóa key material sau hết retention |

Điểm mấu chốt: **trạng thái vòng đời logic** và **trạng thái kỹ thuật `Enabled/Disabled` của KMS** không nhất thiết tương đương. Một KMS có thể chặn **mọi** operation khi `Disabled`, trong khi chính sách nghiệp vụ chỉ muốn dừng ký mới, vẫn cần giữ khả năng xác minh chữ ký cũ bằng public key.

## 3. Mục đích và những lý do phải suspend

### 3.1. Đình chỉ khẩn cấp do tín hiệu an ninh

Những tình huống thường gặp:

- IAM credential của dịch vụ có quyền `Sign`, `Decrypt`, `GenerateMac` hoặc `Unwrap` bị nghi lộ.
- Audit phát hiện phép toán mật mã bất thường: gọi từ principal, địa chỉ hoặc môi trường chưa được phê duyệt.
- Private key có thể bị xuất ra file, đưa vào log, bản sao lưu sai nơi hoặc nhúng vào artifact.
- Nguồn RNG/DRBG dùng tạo khóa có dấu hiệu lỗi, làm giảm độ mạnh khóa đã sinh.
- Chứng thư gắn với signing key cần điều tra sai lệch danh tính hoặc khả năng bị thu hồi.

**Không chờ điều tra xong mới cô lập nếu rủi ro tiếp tục lớn.** Tuy nhiên biện pháp đình chỉ cần tính đến ảnh hưởng availability; ví dụ disable một KEK đang được hàng nghìn bản ghi sử dụng có thể làm hệ thống không giải mã được dữ liệu.

### 3.2. Đình chỉ theo vận hành hoặc thay đổi chính sách

- Có thay đổi quan trọng về người sở hữu khóa, quyền truy cập hoặc điều khoản sử dụng.
- Khóa dùng sai môi trường, sai tenant hoặc ngoài cryptoperiod.
- Chuẩn bị chuyển đổi thuật toán, key version hoặc nơi lưu trữ khóa.
- Cần kiểm tra chất lượng backup/restore hay xử lý bất thường ở HSM.
- Điều tra lỗi ứng dụng khiến khóa được sử dụng sai nghiệp vụ.

Với các trường hợp không phải sự cố khẩn cấp, nên có **change window** và đánh giá tác động. Không dùng “Suspend” để thay mọi thao tác deactivation/rotation thông thường nếu cần thời gian tương thích cho dữ liệu cũ.

### 3.3. Suspend không chứng minh khóa đã bị lộ

Tạm đình chỉ có thể là **biện pháp phòng ngừa** khi chưa đủ bằng chứng. Sau điều tra, kết quả có thể là không có compromise, lạm dụng IAM mà chưa lộ vật liệu, lỗi cấu hình, hoặc private key thực sự đã bị lấy. Các kết quả dẫn tới **quyết định khác nhau** về resume, rotate, revoke hay destroy.

## 4. Suspended key còn có thể làm gì?

Một sai lầm là gộp tất cả phép toán vào một câu “khóa không hoạt động”, không xét sự khác biệt giữa **tạo bảo vệ mới** và **xử lý dữ liệu/chữ ký cũ**.

| Operation | Rủi ro khi khóa Suspended | Mặc định bảo thủ |
| --- | --- | --- |
| **Encrypt** dữ liệu mới | Tiếp tục tạo ciphertext phụ thuộc khóa đang nghi vấn | Chặn |
| **Decrypt** dữ liệu cũ | Có thể tạo thêm plaintext cho principal bị chiếm | Chặn nếu đình chỉ vì an ninh; ngoại lệ phải được phê duyệt |
| **WrapKey** bọc DEK mới | Tạo thêm phụ thuộc vào KEK đang tạm ngưng | Chặn |
| **UnwrapKey** giải bọc DEK cũ | Nếu chặn có thể ngừng đọc dữ liệu; nếu mở có thể lộ DEK | Chặn mặc định; quyết định break-glass riêng nếu được phép |
| **Sign** nội dung mới | Tạo thêm chữ ký có thể gây tác động pháp lý/nghiệp vụ | Chặn |
| **Verify** chữ ký cũ bằng **public key đã tin cậy** | Thường không cần private signing key | Có thể tiếp tục ở hệ xác minh độc lập, tùy trust/revocation |
| **GenerateMac** | Tạo MAC cho thông điệp mới khi secret nghi lộ | Chặn |
| **VerifyMac** bằng secret HMAC | Có thể cần secret/KMS operation, liên quan cùng key | Chặn ở KMS nếu disable toàn key; ngoại lệ yêu cầu phân tích |
| **DeriveKey/ECDH** | Tạo thêm shared secret/phiên từ private agreement key nghi lộ | Chặn |
| **DescribeKey/GetPublicKey** | Metadata/public information | Có thể cho phép theo IAM; không thay thế quyền sử dụng |
| **Admin: rotate/disable/audit** | Quản lý sự cố | Chỉ role được ủy quyền, có log và phê duyệt |

**Chính sách mặc định ở tình huống nghi compromise là chặn thao tác dùng secret**, ngoại trừ hành động được phép rõ ràng cho ứng cứu/phục hồi. Nhưng *đình chỉ một operation cụ thể* có thể thực hiện bằng cách thu hồi grant/IAM thay vì disable toàn bộ key, nếu sản phẩm hỗ trợ và mô hình rủi ro cho phép.

### Cần phân biệt Verify chữ ký với Verify MAC

- **Chữ ký số bất đối xứng:** Người nhận thường kiểm tra bằng **public key**, không cần private signing key. Vì vậy ký mới có thể dừng nhưng xác minh chữ ký cũ vẫn tiếp tục bằng hệ thống tin cậy phù hợp.
- **HMAC:** Tạo và xác minh tag đều liên quan **cùng khóa bí mật**. Nếu KMS chặn khóa HMAC toàn phần, API xác minh MAC có thể cũng bị chặn; không được mặc định giống chữ ký số.

Ngay cả khi chữ ký cũ vẫn xác minh được về **toán học**, hệ thống còn phải xét **chứng thư, trạng thái thu hồi, timestamp của chữ ký, chính sách tin cậy** và sự cố khóa. Suspend private key **không tự thu hồi chứng thư**.

## 5. Cơ chế suspend trong KMS/HSM và ứng dụng

### 5.1. Trạng thái `Disabled` thường là biện pháp kỹ thuật thô

Một số dịch vụ KMS cung cấp thao tác **disable key** và **enable key**. Khi key bị disable, các API mật mã có thể thất bại theo semantics của dịch vụ. Nhưng không nên giả định:

- Nhà cung cấp có API tên `SuspendKey`.
- Mọi operation đều bị chặn giống nhau.
- `GetPublicKey`, `Verify`, quản trị và restore chịu cùng quy tắc.
- Việc disable có tác dụng tức thời đồng nhất trên mọi vùng/cache/replica.
- Khóa disable đã bị xóa khỏi thiết bị/bản backup.

**Phải kiểm tra tài liệu API, trạng thái, thời gian hiệu lực và đặc tính nhất quán của sản phẩm thực tế.** Không tự suy ra mapping đầy đủ từ một giá trị trạng thái.

### 5.2. Policy gate của ứng dụng cần đi cùng chặn ở provider

~~~mermaid
flowchart TD
    R[Yêu cầu Sign/Decrypt/Unwrap] --> A[Identity + authorization]
    A --> P[Key lifecycle policy gate]
    P -->|Suspended: deny| D[Từ chối và ghi audit]
    P -->|Active + đúng operation| K[KMS/HSM kiểm tra IAM + key state]
    K -->|Bị chặn ở provider| D
    K -->|Cho phép| C[Cryptographic operation]
    C --> L[Audit, key ID/version, principal, result]
    D --> L
~~~

Nếu **chỉ** gắn `SUSPENDED` trong database mà service account vẫn có quyền gọi trực tiếp KMS, attacker có thể **bỏ qua policy gate**. Nếu **chỉ** disable KMS nhưng ứng dụng có plaintext DEK trong cache, một số operation vẫn diễn ra **không đi qua KMS**.

Vì vậy nên có ít nhất các lớp:

1. **Control plane** phát quyết định suspend có chữ ký/quyền đáng tin, key ID/version, lý do và thời gian.
2. **KMS/HSM policy/state** chặn những operation tương ứng trên khóa được chỉ định, trong phạm vi sản phẩm cho phép.
3. **Application/data-plane gate** kiểm tra trạng thái hiện hành, đúng operation, tenant và mục đích.
4. **Cache/session containment** để vô hiệu hoặc giảm quyền các bản key material, grant, session và token đã cấp theo phạm vi sự cố.
5. **Audit và negative test** chứng minh yêu cầu bị chặn thật, kể cả qua đường gọi trực tiếp provider.

### 5.3. Suspend key không đồng nghĩa suspend principal

Đối thủ có thể đã đánh cắp **IAM credential** để gọi nhiều key, hoặc đã lấy **raw key material**. Nếu chỉ disable một key nhưng credential còn dùng được với các key khác, sự cố vẫn tiếp tục. Ngược lại, nếu chỉ khóa service account mà key đã bị xuất thành file, bản sao khóa ngoài hệ thống không bị vô hiệu.

Với incident response phải xác định **đối tượng cần cô lập**: key, version, principal, grant, certificate, application session, wrapped DEK, plaintext cache hoặc một tập hợp các thành phần đó.

## 6. Tác động với DEK, KEK và envelope encryption

### 6.1. Đình chỉ DEK: bảo vệ dữ liệu ở mức bản ghi

**DEK (Data Encryption Key)** thường là khóa đối xứng AES-GCM dùng trực tiếp mã hóa bản ghi. Nếu một DEK bị nghi lộ:

- Ngừng dùng DEK đó để mã hóa dữ liệu mới.
- Xác định ciphertext đã được bảo vệ bởi DEK, IV/nonce và AAD tương ứng.
- Đánh giá xem đối thủ có **bản sao DEK** hoặc ciphertext lịch sử hay không.
- Nếu DEK thật sự lộ, cần cân nhắc **rotate DEK và re-encrypt dữ liệu**; chỉ ngừng dùng DEK mới không đảo ngược việc ciphertext cũ có thể bị giải mã.

Nếu DEK đang được giữ **plaintext trong cache của ứng dụng**, disable KEK trong KMS không ngay lập tức ngăn ứng dụng sử dụng DEK. Cần thiết kế quy trình cache invalidation, cô lập workload hoặc thay quyền sử dụng ở data plane.

### 6.2. Đình chỉ KEK: rủi ro mất khả năng giải bọc dữ liệu

**KEK (Key Encryption Key)** bảo vệ DEK qua cơ chế wrap/envelope encryption. Disable KEK có thể làm **Unwrap/Decrypt DEK** qua KMS thất bại. Kết quả là service không đọc được những record mà DEK được bọc bằng KEK này, dù ciphertext và wrapped DEK vẫn nguyên vẹn.

~~~mermaid
flowchart LR
    DB[(Ciphertext + wrapped DEK)] --> U[Ứng dụng cần unwrap DEK]
    U --> K{KEK đang suspended?}
    K -->|Có, API bị chặn| X[Không unwrap được, đọc dữ liệu có thể thất bại]
    K -->|Không và đủ quyền| D[DEK được giải bọc có kiểm soát]
    D --> G[AEAD decrypt dữ liệu]
    C[DEK plaintext còn trong cache] --> G
~~~

Điểm nguy hiểm: nhánh **cache** có thể khiến một service vẫn giải mã được dữ liệu một thời gian ngay sau khi KEK bị đình chỉ, trong khi service vừa restart lại lỗi. Điều này tạo hành vi **không nhất quán giữa instance**, đồng thời khiến người vận hành đánh giá sai hiệu quả cô lập.

### 6.3. Break-glass cho dữ liệu cũ có phù hợp không?

Đôi khi tổ chức cần **tạm mở có kiểm soát** khả năng `Unwrap`/`Decrypt` để phục hồi dữ liệu, xuất bằng chứng hoặc di chuyển sang khóa mới. Đây **không phải ngoại lệ mặc định** khi key bị nghi compromise.

Một quy trình break-glass nếu được chính sách cho phép nên có:

- Phê duyệt độc lập, lý do, phạm vi dữ liệu và thời hạn cụ thể.
- Danh tính riêng, quyền tối thiểu, giới hạn môi trường và audit đầy đủ.
- Chặn mở lại `Encrypt/Wrap` cho dữ liệu mới nếu mục tiêu chỉ là xử lý dữ liệu cũ.
- Giám sát các lượt sử dụng; khóa lại ngay sau khi hoàn thành.
- Đánh giá nguy cơ lộ dữ liệu trước khi dùng lại một key đang nghi vấn.

**Nếu KEK/DEK đã bị compromise, việc dùng lại có thể không được phép**; cần áp dụng quy trình sự cố và phương án thay khóa, không dùng break-glass để né quyết định bảo mật.

## 7. Tác động với signing key, chứng thư và chữ ký số

Một private signing key có thể dùng ký hóa đơn, JWT, artifact build hoặc chứng thư máy chủ. Tạm đình chỉ khóa ký cần xét cả **quyền tạo chữ ký mới** lẫn **niềm tin đối với chữ ký đã tồn tại**.

### 7.1. Chặn việc ký mới

- Từ chối `Sign` ở service và HSM/KMS, thu hồi grant hoặc danh tính bị nghi chiếm.
- Dừng hàng đợi ký đang chờ; xác định các request đã gửi **trước khi suspend** nhưng hoàn tất sau đó.
- Ghi nhận key ID/version, thời điểm yêu cầu, kết quả API và định danh artifact/tài liệu.
- Không tự động trả về một chữ ký giả, hoặc fallback sang khóa cũ **chưa được phê duyệt**.

**Chặn ký mới không có nghĩa hủy hoặc xóa chữ ký đã tạo.** Chữ ký hợp lệ theo thuật toán có thể vẫn kiểm tra được với public key tương ứng.

### 7.2. Verify và trạng thái chứng thư

Nếu sử dụng public key độc lập, hệ thống có thể tiếp tục xác minh về mặt toán học những chữ ký cũ mà không cần private key đã suspended. Tuy nhiên:

- Nếu có nghi vấn private key đã bị lộ, **tính đáng tin** của chữ ký mới/cũ cần đánh giá theo thời gian, chứng thư và bằng chứng.
- Thu hồi chứng thư qua PKI, cập nhật allowlist/JWKS/trust store và thông báo đối tác là các thao tác **riêng**; suspend key trong HSM không tự cập nhật chúng.
- Các token/JWT **đã ký** vẫn có thể được bên nhận chấp nhận cho đến khi chúng hết hạn hoặc chính sách xác minh được cập nhật. Đình chỉ quyền ký không tự thu hồi token đã phát.
- Với tài liệu dài hạn, **trusted timestamp và CRL/OCSP** có thể hỗ trợ phân tích chữ ký lịch sử; timestamp không tự chứng minh khóa không bị lộ tại thời điểm ký.

### 7.3. Mặc định không thay signing key bằng mọi khóa khác

Khi key ký bị suspended, giải pháp tạm thời phải có signing key dự phòng **đã được phê duyệt**, có public key/chứng thư được bên nhận tin cậy. Không tự chuyển sang khóa test, khóa cùng alias nhưng sai thuật toán hoặc một cặp khóa mới chưa phân phối.

## 8. Tác động với HMAC, ECDH và phiên đã thiết lập

### 8.1. HMAC key

HMAC là MAC đối xứng, nghĩa là bên tạo và bên kiểm tra cùng phụ thuộc khóa bí mật.

- Disable HMAC key có thể chặn cả `GenerateMac` và `VerifyMac` nếu provider chặn toàn khóa.
- Các webhook/tag MAC đã phát trước đó có thể cần key cũ để xác minh trong cửa sổ retry.
- Nếu nghi key HMAC đã lộ, **không tiếp tục tin vô điều kiện vào MAC** được tạo từ key đó; phải đánh giá việc giả mạo và chuyển đổi key version.
- Trong giai đoạn chuyển key, cần xác định rõ khoảng thời gian chấp nhận `v1`/`v2`, điều kiện phân phối secret và cách chống replay.

### 8.2. Static ECDH agreement key

Đình chỉ **private static ECDH key** thường nhằm ngăn tạo shared secret cho những phiên mới. Nó **không tự hủy** các shared secret hoặc traffic key đã dẫn xuất cho phiên đang chạy.

Nếu private agreement key đã bị lấy, khả năng ảnh hưởng phiên cũ phụ thuộc giao thức (static/static, static/ephemeral, ECDHE) và dữ liệu đối thủ đã thu thập. Không phát biểu chung rằng suspend một ECDH key sẽ khiến toàn bộ ciphertext cũ an toàn trở lại.

### 8.3. Ephemeral key và TLS

Trong các giao thức như TLS 1.3, private ECDHE key tạm thường chỉ tồn tại trong thời gian bắt tay/phiên. Khi phát hiện compromise dài hạn, việc **chặn các handshake mới**, thay chứng thư/khóa xác thực và kết thúc session phù hợp có thể quan trọng hơn việc tạo một resource key `SUSPENDED` cho từng ephemeral key.

**Session đang hoạt động có thể tiếp tục dùng traffic keys đã dẫn xuất**, ngay cả khi khóa xác thực dùng trong bắt tay trước đó đã bị disable. Đánh giá phạm vi cần gồm session lifetime, connection pool, resumption ticket và cơ chế thu hồi session của sản phẩm.

## 9. Runbook suspend key: từ tín hiệu đến cô lập

Đình chỉ cần được vận hành như **một quy trình có thể lặp lại và kiểm chứng**, không phải thao tác thủ công tùy hứng.

### Bước 1 — Nhận sự kiện và định danh đúng khóa

Xác định:

- `keyId` **và** `keyVersion` thực tế (không chỉ alias có thể trỏ lại).
- `environment`, `region`, `tenant`, `purpose` và `algorithm`.
- Key là **DEK, KEK, HMAC, private signing key hay ECDH key**.
- Owner, custodian, ứng dụng và người phụ thuộc.
- Mức độ rủi ro/incident ID cùng nguyên nhân: nghi compromise, lỗi policy, khôi phục có kế hoạch.

### Bước 2 — Đánh giá đường sử dụng đang tồn tại

Vẽ danh sách nơi có thể gọi phép toán bằng khóa: microservice, batch job, CI/CD, HSM partition, KMS grant, serverless, thư viện native, cache, secret manager và backup. Kiểm tra các operation thực sự đang dùng và khả năng mất availability khi chặn.

### Bước 3 — Quyết định biện pháp cô lập ban đầu

Lựa chọn theo mục tiêu và khả năng của sản phẩm:

- **Chặn principal/grant** khi nguồn rủi ro là danh tính bị xâm nhập nhưng không cần chặn mọi ứng dụng.
- **Disable key resource** nếu cần chặn toàn bộ operation được provider quy định.
- **Policy deny theo operation** nếu chỉ muốn chặn `Sign/Encrypt/Wrap` nhưng vẫn còn một lối xử lý legacy được chính sách cho phép.
- **Application kill switch / routing block** để chặn thêm ở lớp nghiệp vụ.
- **Revoke session/token và vô hiệu cache** khi có nguy cơ bỏ qua provider do bí mật đã được phân phối.

Trong sự cố khẩn cấp, hành động có thể bắt đầu bằng quyền ứng cứu được định trước và phê duyệt hậu kiểm theo chính sách; **không tự tạo ngoại lệ vô hạn** cho người vận hành.

### Bước 4 — Thực thi và xác minh

- Áp dụng trạng thái và IAM/key policy trên KMS/HSM/control plane.
- **Thử từ chối** từ danh tính ứng dụng thật với operation cần chặn, trên đúng key/version.
- Kiểm tra các instance, vùng và bản sao theo mức nhất quán của nhà cung cấp.
- Theo dõi API lỗi/không lỗi, độ trễ, luồng backup/restore và hàng đợi ký/mã hóa.
- Ghi audit trước/sau: ai, khi nào, lý do, thay đổi gì và kết quả kiểm thử.

**Không thử bằng thao tác tạo dữ liệu nhạy cảm hoặc xuất private key trong production** chỉ để “xem có bị chặn không”. Dùng kiểm tra đã được phê duyệt và dữ liệu test an toàn; khi cần negative test trực tiếp, bảo đảm request thử không thể tạo hậu quả nghiệp vụ.

### Bước 5 — Điều tra và quản lý ảnh hưởng

Đánh giá vật liệu khóa có thật sự lộ hay chỉ là lạm dụng quyền, các bản mã/chữ ký/tag/phiên có thể bị ảnh hưởng, hành vi trước thời điểm suspend và dữ liệu nằm ngoài kiểm soát KMS.

### Bước 6 — Ra quyết định tiếp theo

Có ba nhánh cơ bản:

1. **Resume:** Sự cố được giải thích/khắc phục, key material còn đáng tin, có phê duyệt và bài kiểm tra bảo mật/khả dụng.
2. **Rotate/Deactivate:** Key không còn phù hợp, đã kết thúc cryptoperiod hoặc cần thay thế có kiểm soát; tránh tạo dữ liệu mới bằng key cũ.
3. **Compromised/Destroy theo quy trình:** Key được kết luận bị lộ/không còn đáp ứng mục tiêu; thay vật liệu khóa, thu hồi trust/quyền và xử lý dữ liệu lịch sử, rồi tiêu hủy khi không còn phụ thuộc.

~~~mermaid
flowchart TD
    Alert[Cảnh báo hoặc yêu cầu suspend] --> Id[Định danh keyId + version + principal]
    Id --> Impact[Đánh giá tác động bảo mật/khả dụng]
    Impact --> Block[Chặn operation tại IAM/KMS/HSM và app]
    Block --> Test[Negative test + audit]
    Test --> Investigate[Điều tra key material, quyền, phiên, cache]
    Investigate --> Q{Key còn đáng tin?}
    Q -->|Có; lỗi đã sửa; đủ phê duyệt| Resume[Resume có kiểm soát]
    Q -->|Cần nghỉ dùng/thay phiên bản| Rotate[Rotate / Deactivate]
    Q -->|Bị lộ hoặc không đủ an toàn| Comp[Compromised: thay key + xử lý hệ phụ thuộc]
    Comp --> Destroy[Hủy sau đánh giá dữ liệu và retention]
~~~

## 10. Resume key: điều kiện khôi phục sau khi đình chỉ

**Resume** không nên là thao tác “bấm Enable vì hết giờ bảo trì”. Nó phải là quyết định **có bằng chứng rằng điều kiện đình chỉ đã được giải quyết** và việc mở lại khóa không tái tạo rủi ro.

### Các điều kiện tối thiểu

1. **Nguyên nhân đã xác định:** Báo động giả, IAM lỗi, thiết bị bị lỗi hay vật liệu đã bị lộ? Kết luận phải dựa trên bằng chứng phù hợp.
2. **Key material còn đáng tin:** Không có bằng chứng compromise chưa được xử lý; nếu đã lộ thì **tạo key mới** thay vì resume key cũ.
3. **Phê duyệt độc lập:** Key owner và người có thẩm quyền an ninh cho phép resume; key custodian thực hiện theo quy trình.
4. **Quyền đã sửa:** IAM/grant, network guardrails, service identity, rate limit và policy đúng mục đích.
5. **Khả năng vận hành đã chuẩn bị:** Ứng dụng có thể xử lý key version, dữ liệu đã tạo, queue backlog và traffic tăng khi mở lại.
6. **Khóa trong cryptoperiod:** Không resume key đã hết thời hạn sử dụng mới hoặc đã đi vào giai đoạn deactivated/compromised.
7. **Kiểm tra trạng thái thực tế:** Key enabled nếu cần, nhưng chỉ những operation được phép mới hoạt động; người không đủ quyền phải tiếp tục bị chặn.
8. **Audit và giám sát:** Có record về lý do, phiên bản chính sách, approver, thời điểm, kiểm thử và cảnh báo sau resume.

### Lỗi TOCTOU và cache trạng thái

Giữa lúc ứng dụng đọc `ACTIVE` từ DB và gọi API KMS, khóa có thể đã bị đình chỉ. Nếu chỉ kiểm tra **trước** một bước rồi dùng cached DEK/handle vô thời hạn, quyết định suspend có thể không hiệu quả như mong muốn.

Vì vậy cần thiết kế **nguồn trạng thái có hiệu lực**, thời gian cache phù hợp với rủi ro, cơ chế invalidation và **cưỡng chế tại điểm thực hiện phép toán**. Những mục tiêu “chặn trong vòng X giây” chỉ được cam kết khi có đo kiểm trên cấu hình thực tế; không nên tự suy ra từ việc gọi API một lần.

## 11. Ví dụ Java 11+: policy gate từ chối khóa Suspended

Ví dụ Java sau minh họa cách **từ chối thao tác với khóa ở trạng thái `SUSPENDED`** và kiểm tra mục đích/cryptoperiod. Mã chỉ xử lý metadata giả lập — **không tạo khóa thật, không gọi KMS/HSM**. Nó là lớp kiểm soát bổ sung, **không thể thay quyền và trạng thái được thực thi tại provider**.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.EnumSet;

public final class SuspendKeyPolicyDemo {
    enum KeyState {
        PRE_ACTIVATION,
        ACTIVE,
        SUSPENDED,
        DEACTIVATED,
        COMPROMISED,
        DESTROYED
    }

    enum Operation {
        ENCRYPT, DECRYPT, SIGN, GENERATE_MAC, VERIFY_MAC, DERIVE_KEY, WRAP, UNWRAP
    }

    static final class KeyRecord {
        final String keyId;
        final long revision;
        final KeyState state;
        final EnumSet<Operation> allowedOperations;
        final Instant validFrom;
        final Instant newUseUntil;

        KeyRecord(String keyId, long revision, KeyState state,
                  EnumSet<Operation> allowedOperations,
                  Instant validFrom, Instant newUseUntil) {
            if (keyId == null || keyId.isEmpty()
                    || revision < 0 || state == null
                    || allowedOperations == null
                    || validFrom == null || newUseUntil == null
                    || !validFrom.isBefore(newUseUntil)) {
                throw new IllegalArgumentException("Invalid key metadata");
            }
            this.keyId = keyId;
            this.revision = revision;
            this.state = state;
            this.allowedOperations = allowedOperations.clone();
            this.validFrom = validFrom;
            this.newUseUntil = newUseUntil;
        }
    }

    static void requireActiveNewUse(
            KeyRecord key, Operation operation, Clock clock) {
        if (key == null || operation == null || clock == null) {
            throw new SecurityException("Missing authorization context");
        }

        // Fail closed: Suspended và mọi state không phải ACTIVE đều bị chặn.
        if (key.state != KeyState.ACTIVE) {
            throw new SecurityException(
                    "Key is not active: " + key.keyId);
        }
        Instant now = clock.instant();
        if (now.isBefore(key.validFrom) || !now.isBefore(key.newUseUntil)) {
            throw new SecurityException("Outside cryptoperiod");
        }
        if (!key.allowedOperations.contains(operation)) {
            throw new SecurityException("Operation denied for this key");
        }
    }

    public static void main(String[] args) {
        Clock demoClock = Clock.fixed(
                Instant.parse("2030-05-02T12:00:00Z"), ZoneOffset.UTC);
        Instant from = Instant.parse("2030-05-01T00:00:00Z");
        Instant until = Instant.parse("2030-08-01T00:00:00Z");

        KeyRecord active = new KeyRecord(
                "invoice-signing-v3", 17L, KeyState.ACTIVE,
                EnumSet.of(Operation.SIGN), from, until);
        requireActiveNewUse(active, Operation.SIGN, demoClock);
        System.out.println("ACTIVE/SIGN: allowed");

        // Bản ghi revision mới được tạo bởi control plane đáng tin.
        KeyRecord suspended = new KeyRecord(
                "invoice-signing-v3", 18L, KeyState.SUSPENDED,
                EnumSet.of(Operation.SIGN), from, until);

        try {
            requireActiveNewUse(suspended, Operation.SIGN, demoClock);
            throw new AssertionError("Suspended key must be rejected");
        } catch (SecurityException expected) {
            System.out.println("SUSPENDED/SIGN: denied");
        }

        try {
            requireActiveNewUse(active, Operation.DECRYPT, demoClock);
            throw new AssertionError("Unapproved operation must be rejected");
        } catch (SecurityException expected) {
            System.out.println("ACTIVE/DECRYPT: denied");
        }
    }
}
~~~

**Kết quả dự kiến:**

~~~text
ACTIVE/SIGN: allowed
SUSPENDED/SIGN: denied
ACTIVE/DECRYPT: denied
~~~

### Vì sao ví dụ chưa đủ cho production?

- Bản ghi `active` đã nằm trong bộ nhớ vẫn cho phép `SIGN` vì không tự biết revision 18 vừa được phát hành. Đây **chính là rủi ro stale state/cache**.
- Không có **principal identity**, IAM, approval record, tenant scope, audit hoặc khả năng khóa principal bị chiếm.
- Không gọi API **KMS/HSM thực**; một attacker bỏ qua ứng dụng vẫn có thể dùng key nếu provider cho phép.
- Không giải quyết giao dịch cập nhật trạng thái, nhất quán đa vùng, event ordering, session đã thiết lập và dữ liệu đã ở trong cache.
- Hàm chỉ minh họa **new use** khi key `ACTIVE`; các trường hợp cần historical `Decrypt` hoặc `VerifyMac` khi deactivated/suspended phải có **policy riêng**, không tự thêm ngoại lệ vào đường này.
- Không nên hiển thị thông tin nội bộ key ID và chi tiết policy cho khách hàng cuối nếu có nguy cơ rò rỉ metadata; các thông báo trong demo chỉ dùng học tập.

Trong triển khai thật, **control plane ký/ủy quyền quyết định đình chỉ**, áp dụng tại provider và đẩy tín hiệu đến các service. Bất kỳ chính sách resume nào cũng phải kiểm tra `revision`, key version, trạng thái và nguồn dữ liệu tin cậy; **không dựa vào caller tự truyền `ACTIVE`**.

## 12. Phân quyền và separation of duties khi suspend/resume

Các hành động khẩn cấp và phục hồi có mức rủi ro khác nhau:

| Vai trò | Quyền/trách nhiệm hợp lý | Điều không nên mặc định |
| --- | --- | --- |
| **Key owner** | Xác định mức chấp nhận rủi ro, phê duyệt phạm vi suspend và quyết định resume/rotate | Tự có raw key hoặc quyền `Decrypt/Sign` |
| **Key custodian** | Thực thi disable/enable, IAM, key policy và rotation theo phê duyệt | Tự ký dữ liệu sản xuất hoặc quyết định resume khi đang bị điều tra |
| **Security/incident responder** | Có quyền cô lập khẩn cấp theo runbook, bảo toàn chứng cứ, rà soát principal | Hủy vĩnh viễn key khi chưa đánh giá dữ liệu phụ thuộc |
| **Application owner** | Giảm lưu lượng, cập nhật routing, hỗ trợ kiểm thử và khôi phục | Tự thay key state để bỏ qua quyết định an ninh |
| **Auditor** | Đối chiếu thời điểm, lý do, người yêu cầu/phê duyệt, sự kiện và negative test | Sửa audit log hoặc dùng private key |
| **Recovery operator** | Thực hiện thao tác `Unwrap/Decrypt` được cấp quyền trong cửa sổ đặc biệt nếu có | Mở rộng quyền vô thời hạn cho mọi dữ liệu |

### Suspend khẩn cấp có thể cần nhanh hơn quy trình chuẩn

Một số tổ chức cấp quyền **emergency suspend** cho nhóm ứng cứu để ngăn thiệt hại đang diễn ra, nhưng yêu cầu **phê duyệt hậu kiểm, thời hạn và audit**. Quyền **resume** nên chặt hơn, vì việc mở lại khả năng sử dụng khóa có thể tái diễn compromise.

**Không dùng cùng một danh tính quyền cao** cho: tạo key, sử dụng key, sửa key policy, đình chỉ, khôi phục và xóa audit. Nên đánh giá khả năng leo thang gián tiếp: ai có thể cấp grant cho chính mình hoặc đổi service account?

## 13. Nhật ký, cảnh báo và bằng chứng kiểm toán

Một event suspend mẫu ở mức **metadata không bí mật**:

~~~yaml
eventType: KEY_SUSPENDED
keyId: "billing-kek-v3"
keyVersion: "v3"
previousState: "ACTIVE"
newState: "SUSPENDED"
reasonCategory: "SECURITY_INVESTIGATION"
incidentRef: "INC-2030-041"
requestedBy: "security-responder"
approvedBy: "incident-commander"
effectiveAtUtc: "2030-05-02T10:15:00Z"
controlPlaneRevision: 118
providerAction: "DisableKey"
providerResult: "SUCCESS"
negativeTestResult: "DENIED"
correlationId: "request-abc"
~~~

Đây **không phải schema API KMS cụ thể**; các trường phải gắn với hệ thống IAM/incident response và nhật ký có bảo vệ toàn vẹn thực tế.

### Audit nên trả lời được những câu hỏi nào?

1. Ai phát hiện, ai yêu cầu và ai phê duyệt suspend?
2. Key ID/version, thuật toán, mục đích và môi trường là gì?
3. Đã thay IAM/key policy, disable provider hay chặn riêng operation nào?
4. Có những lượt gọi `Sign/Decrypt/Unwrap` nào **đang chạy** hoặc hoàn tất sau quyết định?
5. Những instance hoặc vùng nào vẫn sử dụng key material từ cache?
6. Có phát sinh bản mã, chữ ký, MAC, session hoặc wrapped DEK trong cửa sổ sự cố?
7. Kết quả **negative test** từ danh tính thực và thời điểm provider có hiệu lực?
8. Khi resume/rotate, bằng chứng điều tra, phê duyệt và chính sách nào được dùng?

### Giám sát

Nên đặt cảnh báo cho:

- Sử dụng `Sign`, `Decrypt`, `Unwrap` bất thường trước khi đình chỉ.
- Lượt dùng khóa được báo suspended nhưng data plane vẫn thành công.
- Thay policy/grant hoặc enable key **không có approval phù hợp**.
- Khóa suspended quá lâu nhưng không có quyết định xử lý tiếp theo.
- Tỉ lệ lỗi giải mã sau disable KEK, số lượng job ký bị treo, cache invalidation không hoàn tất.
- Mở quyền `Decrypt/Unwrap` trong chế độ break-glass vượt thời hạn được phê duyệt.

**Không log** private key, DEK, KEK, HMAC key, ECDH shared secret, raw reset token, plaintext nhạy cảm hoặc seed RNG.

## 14. Case study: nghi lộ khóa ký gói phần mềm

Giả sử pipeline phát hành sử dụng **private signing key** `release-signing-v4` trong HSM. Một job không được phê duyệt gọi API `Sign` 50 lần vào ban đêm. Hệ thống không biết job chỉ lạm dụng quyền hay private key đã bị lộ ngoài HSM.

### Phương án đình chỉ

1. Nhóm ứng cứu ghi incident ID và key ID/version thực; tạm dừng pipeline phát hành.
2. Thu hồi credential/grant của job nghi vấn; chặn `Sign` với `release-signing-v4` ở HSM/KMS theo khả năng nền tảng.
3. Chứng minh việc chặn bằng negative test an toàn từ service principal liên quan.
4. Truy vết 50 kết quả ký với artifact ID/digest, thời điểm, principal và approval workflow; xác định artifact nào đã phát hành.
5. Tạm dừng phát hành mới; đánh giá các client còn tin public key/chứng thư của `v4`.
6. Nếu key material còn bảo đảm nhưng quyền bị lạm dụng, quyết định **có resume hay chuyển sang key mới** theo mức tác động và chính sách.
7. Nếu private key đã lộ hoặc không còn đáng tin, sinh `v5` trong vùng bảo vệ an toàn, cấp/phân phối thông tin xác minh, cập nhật trust và xử lý chứng thư `v4` theo PKI; không resume `v4`.
8. Báo cáo và sửa nguyên nhân gốc: IAM, CI role, approval của nội dung được ký, policy HSM và kiểm toán.

### Những giới hạn của suspend

- **HSM từ chối ký mới** không xóa được chữ ký đã phát.
- **Chữ ký trên artifact độc hại** có thể tiếp tục được người nhận chấp nhận nếu họ còn tin public key cũ. Cần xử lý kênh phân phối, metadata phát hành, trust/revocation và thông báo.
- Nếu signing key chỉ có thể sử dụng trong HSM và chưa bị xuất, việc lạm dụng API vẫn có thể gây thiệt hại đáng kể; **non-exportable không thay thế kiểm soát nội dung trước khi ký**.
- Đổi alias sang `v5` nhưng không cập nhật bên xác minh sẽ khiến artifact mới không được tin hoặc bị từ chối.

## 15. Case study: disable KEK gây gián đoạn dữ liệu

Hệ thống lưu hóa đơn dùng **envelope encryption**: mỗi nhóm bản ghi được mã hóa bằng **DEK**, còn DEK được bọc bởi **KEK `billing-kek-v3`** trong KMS. Đội an ninh phát hiện grant của KEK bị cấp quá rộng và chọn disable ngay.

### Điều gì có thể xảy ra?

| Thời điểm | Tình trạng | Hệ quả |
| --- | --- | --- |
| Trước khi suspend | Ứng dụng giải bọc DEK bình thường | Đọc/ghi thành công |
| Vừa disable KEK | KMS từ chối thao tác liên quan theo API | Các instance cần unwrap mới có thể lỗi |
| Một số instance còn DEK trong cache | Có thể vẫn giải mã/mã hóa bằng DEK cache | Chặn KEK **không bảo đảm dừng toàn bộ truy cập dữ liệu** |
| Restart service sau disable | Cache mất, phải gọi KMS | Đột ngột không đọc được bản ghi phụ thuộc |
| Quyết định rotate thay KEK | Cần đường giải bọc hợp lệ và thủ tục rewrap | Không được xóa `v3` trước khi dữ liệu được di chuyển/giải quyết |

### Thiết kế ứng phó

- Phân biệt **rủi ro từ principal/grant** với **rủi ro từ bản thân KEK**. Nếu chỉ một role bị chiếm, có thể ưu tiên thu hồi role/grant và giám sát, thay vì chặn mọi tác vụ cần dữ liệu; lựa chọn phụ thuộc mức độ khẩn cấp.
- Tạo bản đồ **wrapped DEK → key version** để xác định phạm vi tác động.
- Giảm nguy cơ cache không còn kiểm soát: cô lập workload bị chiếm, quản lý TTL/invalidation phù hợp và kiểm tra các instance còn key material.
- Nếu cần chuyển sang KEK khác, thực hiện **rewrap DEK** theo quy trình được phép; đảm bảo ciphertext còn truy cập được trước khi ngừng khóa cũ.
- Nếu **DEK đã bị lấy**, chỉ rewrap dưới KEK mới không ngăn đối thủ dùng bản sao DEK; cần đánh giá **thay DEK và mã hóa lại dữ liệu**, cùng sự cố lịch sử.
- Không dùng delete/hủy vĩnh viễn để mô phỏng suspend. Xóa KEK khi vẫn còn wrapped DEK phụ thuộc có thể gây mất khả năng giải mã.

## 16. Những sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Biện pháp |
| --- | --- | --- |
| Chỉ đổi status ở DB thành `SUSPENDED` | KMS/HSM vẫn có thể chấp nhận operation | Cưỡng chế quyền/trạng thái ở provider và app |
| Coi `Disable` ở KMS tương đương mọi chính sách suspend | Có thể chặn cả legacy decrypt/verify cần thiết | Đánh giá semantics và operation cụ thể |
| Nghĩ disable KEK chặn mọi dữ liệu | Plaintext DEK có thể còn trong cache | Cache/session containment, cô lập workload, kiểm chứng |
| Nghĩ suspend private key đã bị lộ sẽ làm nó bí mật trở lại | Đối thủ vẫn giữ bản sao | Tạo key mới, revoke trust/rights và đánh giá dữ liệu cũ |
| Suspend signing key rồi bỏ qua JWT/chữ ký cũ | Bên xác minh vẫn có thể chấp nhận kết quả đã phát | Xử lý revocation, trust, expiry và kênh phân phối |
| Cho phép tự động fallback sang key cũ/test | Dùng khóa chưa được phê duyệt | Routing theo key version và policy fail closed |
| Hủy KEK để “đảm bảo không dùng được” | Có thể mất dữ liệu không thể phục hồi | Suspend reversible, kiểm kê wrapped DEK và retention |
| Không kiểm tra các principal/grant khác | Credential còn sử dụng được khóa khác | Điều tra identity, IAM, privilege escalation |
| Không ghi nhận operation in-flight | Chữ ký/bản mã có thể được tạo quanh thời điểm chặn | Đối chiếu request time, completion time, audit |
| Không xét hệ thống phân tán và cache | Một vùng/node vẫn dùng key cũ | Quy tắc consistency, invalidation và negative test |
| Resume ngay sau khi lỗi hạ tầng hết | Có thể mở lại key compromised | Bằng chứng điều tra + phê duyệt độc lập |
| Không phân biệt HMAC với chữ ký số | Verify HMAC cần secret, Verify chữ ký dùng public key | Thiết kế policy riêng từng loại khóa |
| Mở `Decrypt/Unwrap` break-glass vô thời hạn | Đường ngoại lệ trở thành quyền thường trực | Scope/TTL/phê duyệt/audit và thu hồi |
| Không có diễn tập suspend/resume | Chỉ khi sự cố xảy ra mới phát hiện downtime | Test trên staging/an toàn theo policy, runbook và DR |

## 17. Checklist triển khai Suspend key trong production

1. **Xác định tài sản:** Đã biết đúng key ID/version, owner/custodian, algorithm, purpose, môi trường và hệ phụ thuộc chưa?
2. **Lý do:** Đình chỉ để điều tra compromise, sửa IAM, ngừng nghiệp vụ tạm thời hay chuẩn bị rotation? Quyết định có lưu bằng chứng không?
3. **Phạm vi operation:** Cần chặn `Sign`, `Encrypt`, `GenerateMac`, `DeriveKey`, `Wrap`, `Decrypt`, `Unwrap`, `VerifyMac` hay toàn bộ? Ngoại lệ nào được phê duyệt?
4. **KMS/HSM thực tế:** Nhà cung cấp hỗ trợ `Disable`, policy deny hoặc thay grant ra sao? Trạng thái có hiệu lực và mức nhất quán thế nào?
5. **Fail closed:** Có chặn từ service lẫn provider, thử từ chối với principal thực, không có fallback trái phép?
6. **Principal bị chiếm:** Có thu hồi session/token/grant và xem xét các khóa khác mà danh tính đó có thể dùng?
7. **Cache và key material:** DEK/shared secret/traffic key hoặc private key có nằm trong process memory, snapshot hay backup không? Đã cô lập đường sử dụng còn tồn tại?
8. **Ảnh hưởng dữ liệu:** Với KEK/DEK, có biết những bản ghi nào không đọc/ghi được sau đình chỉ và có phương án bảo toàn?
9. **Chữ ký số:** Với signing key, các chữ ký cũ, artifact, JWT, chứng thư, public key và timestamp được xử lý thế nào?
10. **Thỏa thuận khóa:** Với ECDH/TLS, có chặn phiên mới và đánh giá session key đã cấp không?
11. **Vòng đời:** Có trạng thái `SUSPENDED` được quản trị, lịch rà soát và tiêu chí chuyển sang `ACTIVE`, `DEACTIVATED` hoặc `COMPROMISED`?
12. **Quyền vận hành:** Ai được suspend khẩn cấp, ai được resume và ai được duyệt break-glass? Có separation of duties không?
13. **Audit:** Có log reason, incident ID, principal, key ID, trạng thái trước/sau, policy revision, kết quả API và negative test không?
14. **Rollback/resume:** Điều kiện mở lại có yêu cầu key material còn đáng tin, đã sửa nguyên nhân và kiểm thử an toàn/khả dụng?
15. **Xoay và hủy:** Nếu key compromised, đã thay vật liệu, xử lý data/trust và kiểm tra retention trước khi hủy?
16. **Kiểm thử:** Đã diễn tập khi disable KEK, khi có cache, khi nhiều region và khi một request đang gọi KMS chưa?
17. **Tuân thủ:** Trạng thái logic có được ánh xạ đúng vào semantics sản phẩm/tiêu chuẩn áp dụng, không đánh đồng `Disabled` với `Destroyed`?

### Ghi nhớ

**Suspend key** là biện pháp **tạm dừng sử dụng một khóa có kiểm soát**, không phải xóa khóa, cũng không bảo đảm xóa được các bản sao bí mật đã lộ. Để đình chỉ có hiệu lực cần chặn tại **IAM/KMS/HSM và data plane**, đồng thời xử lý principal, cache, phiên và thao tác đang chạy. Với **DEK/KEK**, suspend có thể làm gián đoạn giải mã nhưng cached DEK vẫn hoạt động; với **private signing key**, ký mới bị chặn nhưng chữ ký cũ có thể tiếp tục được xác minh bằng public key; với **HMAC/ECDH**, phải đánh giá khóa bí mật và các phiên/tag đã tồn tại. Resume chỉ được phép khi nguyên nhân đã được khắc phục và key material vẫn đáng tin; **khóa thực sự compromised cần được thay thế**, không chỉ bật lại. Phân tách trách nhiệm, kiểm toán, rotation, kế hoạch khôi phục và xử lý dữ liệu lịch sử giúp trạng thái Suspended trở thành một cơ chế quản trị vòng đời khóa hữu ích, thay vì một nút bật/tắt gây rủi ro mới.
