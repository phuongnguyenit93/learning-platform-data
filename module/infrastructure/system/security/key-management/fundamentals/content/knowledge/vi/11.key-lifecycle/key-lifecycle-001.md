# Pre-activation state — Trạng thái trước kích hoạt trong vòng đời khóa mật mã

## 1. Pre-activation state là gì?

**Pre-activation state** (*trạng thái trước kích hoạt*) là giai đoạn một **khóa mật mã đã được tạo hoặc thiết lập và được quản lý như một tài sản**, nhưng **chưa được cho phép dùng để thực hiện các thao tác mật mã nghiệp vụ theo mục đích dự kiến**. Khóa có thể đã tồn tại trong KMS/HSM, đã có định danh, thuật toán, owner, chính sách và bản sao lưu được phê duyệt; song việc bảo vệ dữ liệu mới hoặc tạo chữ ký sản xuất bằng khóa đó phải **chưa được mở**.

Ví dụ, doanh nghiệp chuẩn bị thay khóa ký hóa đơn `invoice-signing-v1` bằng `invoice-signing-v2`. Khóa `v2` được sinh sớm trong HSM, public key và chứng thư liên quan đã được phân phối cho bên xác minh, quyền sử dụng được rà soát, nhưng thời điểm chuyển đổi chính thức chưa tới. Trong giai đoạn đó, `v2` ở trạng thái **pre-activation** theo mô hình quản lý vòng đời, và không nên cho dịch vụ ký hóa đơn sản xuất gọi `Sign` bằng `v2`.

Lợi ích của trạng thái này là **tách biệt việc chuẩn bị khóa khỏi quyền sử dụng khóa**. Nhờ vậy, đội ngũ có thời gian kiểm tra vật liệu, phân phối metadata, cấu hình IAM, diễn tập xử lý lỗi và nhận phê duyệt trước khi khóa tạo ra bất kỳ kết quả mật mã sản xuất nào.

Trong phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, pre-activation là một điểm kiểm soát xuyên suốt các hoạt động **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy khóa**, kết nối mã hóa đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Nguyên tắc:** **Khóa đã được tạo không đồng nghĩa khóa đã được ủy quyền sử dụng.** Pre-activation chỉ an toàn khi có cơ chế ngăn *cryptographic use* chưa được phê duyệt ở nơi thực thi, chứ không chỉ ghi nhãn `PRE_ACTIVATION` trong database.

### Mục tiêu học tập

Sau bài này, người học cần có khả năng:

1. Phân biệt trạng thái **pre-activation** với key generation, provisioning, active, suspended và deactivated.
2. Xây dựng **điều kiện kích hoạt** có owner, custodian, phê duyệt và bằng chứng kiểm toán.
3. Thiết kế cơ chế **fail closed** để ứng dụng không vô tình dùng khóa mới.
4. Lập kế hoạch **rotation/cutover** an toàn cho DEK, KEK, signing key và khóa xác thực.
5. Hiểu khác biệt giữa trạng thái vòng đời **ở mức chính sách** với các trạng thái **thực tế của KMS/HSM**.

## 2. Khái niệm trạng thái khóa và sơ đồ vòng đời

Trong mô hình quản lý khóa được sử dụng phổ biến trong các tài liệu như **NIST SP 800-57**, người ta phân biệt các trạng thái logic của key theo **khả năng và thẩm quyền sử dụng**. Việc đặt tên cụ thể có thể khác nhau giữa tiêu chuẩn, thư viện và sản phẩm; sơ đồ sau là **mô hình giáo dục**, không phải API chung cho mọi KMS.

~~~mermaid
stateDiagram-v2
    [*] --> PreActivation: Sinh hoặc thiết lập khóa
    PreActivation --> Active: Đạt điều kiện và được phê duyệt
    PreActivation --> Compromised: Nghi bị lộ hoặc sai nguồn gốc
    PreActivation --> Destroyed: Hủy trước khi sử dụng
    Active --> Suspended: Tạm chặn theo chính sách
    Suspended --> Active: Khôi phục sau đánh giá
    Active --> Deactivated: Ngừng dùng cho nghiệp vụ mới
    Suspended --> Deactivated: Ngừng sử dụng chính thức
    Active --> Compromised: Phát hiện hoặc nghi lộ khóa
    Suspended --> Compromised: Phát hiện compromise
    Deactivated --> Compromised: Phát hiện compromise lịch sử
    Deactivated --> Destroyed: Hết phụ thuộc và retention
    Compromised --> Destroyed: Xử lý hậu quả, hủy vật liệu
    Destroyed --> [*]
~~~

### Ý nghĩa các trạng thái chính

| Trạng thái | Ý nghĩa quản trị | Thao tác mật mã nghiệp vụ điển hình |
| --- | --- | --- |
| **Pre-activation** | Khóa đã được sinh/thiết lập nhưng chưa được ủy quyền dùng theo mục đích đã định | **Chưa cho phép** sử dụng sản xuất; kiểm thử/quản trị chỉ theo chính sách riêng |
| **Active** | Khóa đã được phê duyệt và đang ở thời hạn sử dụng | Cho phép đúng những thao tác `Encrypt`, `Sign`, `GenerateMac`, `DeriveKey`… được quy định |
| **Suspended** | Tạm ngưng sử dụng trong khi chờ xử lý hoặc đánh giá | Theo mặc định bảo thủ, chặn các thao tác nhạy cảm; ngoại lệ tùy chính sách |
| **Deactivated** | Không còn được dùng cho bảo vệ/tạo dữ liệu mới | Có thể còn cho phép `Decrypt`, `Verify` hoặc truy xuất cũ theo chính sách |
| **Compromised** | Khóa bị lộ hoặc được xem như không còn bảo đảm an toàn | Cần cách ly, hạn chế quyền, đánh giá tác động và thay khóa |
| **Destroyed** | Vật liệu khóa đã bị tiêu hủy theo cơ chế được xác nhận | Không thể tiếp tục thực hiện phép toán dùng vật liệu đó |

**Active không có nghĩa “mọi operation đều được phép”**. Ví dụ, một khóa ký active chỉ nên được sử dụng để ký nội dung trong phạm vi nghiệp vụ của nó; nó không đương nhiên được phép giải mã, thỏa thuận khóa hoặc ký mọi yêu cầu đến API.

**Deactivated không nhất thiết đồng nghĩa `Disabled` trên KMS**. Một khóa giải mã cũ có thể không còn dùng để mã hóa dữ liệu mới nhưng vẫn được mở cho thao tác giải mã được phép. Khi đó, KMS có thể vẫn báo tài nguyên `Enabled`; chính sách nghiệp vụ mới là nơi phân biệt *protect mới* và *unprotect cũ*.

### Pre-activation không phải khóa “chưa tồn tại”

Một bản ghi **planned** chưa sinh khóa thường chỉ là kế hoạch tài nguyên; một key có trạng thái **pre-activation** đã được định danh, có key material hoặc key handle theo kiến trúc. Việc **sinh khóa**, **đưa vào kho khóa** và **cho phép dùng khóa** là ba cột mốc có thể xảy ra ở những thời điểm khác nhau.

## 3. Tại sao phải có giai đoạn trước kích hoạt?

### 3.1. Giảm rủi ro triển khai chưa sẵn sàng

Tạo một signing key trước ngày phát hành giúp đội vận hành có thời gian:

- Đăng ký **key ID/version** và chủ sở hữu.
- Cấp chứng thư đúng public key, thuật toán và key usage.
- Phân phối **public verification key/chứng thư** đến bên nhận.
- Kiểm thử việc người nhận hỗ trợ thuật toán và trust chain dự kiến.
- Thiết lập policy để chỉ dịch vụ ký đã được phê duyệt được gọi `Sign`.
- Thử kế hoạch chuyển đổi, sự cố và rollback mà không tạo chữ ký sản xuất bằng khóa mới quá sớm.

Nếu bật khóa ngay khi sinh mà các bên chưa nhận public key, dữ liệu mới ký có thể không được xác minh. Ngược lại, nếu public key được phân phối trước nhưng private key chưa được bảo vệ, giai đoạn chờ có thể trở thành cửa sổ tấn công.

### 3.2. Ngăn lẫn lộn môi trường và mục đích

Các khóa `dev`, `test`, `staging`, `production` phải có phạm vi riêng. Một key mới được tạo nhầm trong production không nên tự động được phép `Decrypt` hay `Sign`. Mô hình pre-activation yêu cầu **chứng minh rõ** rằng key đúng loại, môi trường, tenant, dữ liệu, thuật toán, lifecycle và bên sử dụng.

### 3.3. Tách nhiệm vụ trong vận hành khóa

**Key owner** phê duyệt mục đích và thời điểm; **key custodian** bảo đảm khóa được tạo/lưu an toàn; **security reviewer** đánh giá cấu hình và rủi ro; **application/key user** chỉ thực hiện phép toán được cấp. Không nên để một principal tự tạo khóa, tự sửa policy, tự phê duyệt và tự kích hoạt để ký dữ liệu nhạy cảm.

### 3.4. Hỗ trợ xoay khóa không gây gián đoạn

Sự khác nhau giữa **chuẩn bị** và **kích hoạt** cho phép triển khai mô hình hai phiên bản:

~~~text
T0: v1 đang active; v2 mới được tạo và ở pre-activation
T1: v2 đã có policy, metadata, tài liệu và đường xác minh sẵn sàng
T2: phê duyệt và cutover: v2 active để bảo vệ dữ liệu mới
T3: v1 dừng tạo dữ liệu/chữ ký mới, có thể còn dùng cho dữ liệu lịch sử
T4: v1 được ngừng hoặc hủy sau khi hết phụ thuộc và retention
~~~

Không được coi T2 là “chỉ thay một alias rồi xong” nếu có nhiều dịch vụ, KMS policy, kho chứng thư, bản sao lưu và khách hàng phụ thuộc.

## 4. Pre-activation cho phép làm gì?

Cần phân biệt **hoạt động quản trị/thẩm định** với **sử dụng khóa cho nhiệm vụ mật mã sản xuất**.

| Hoạt động | Có thể được phép trước kích hoạt? | Điều kiện |
| --- | --- | --- |
| Sinh khóa và tạo key handle | **Có** | CSPRNG/DRBG phù hợp, đúng thuật toán và nguồn gốc |
| Ghi key ID, owner, usage, key version | **Có** | Metadata đáng tin và không chứa key material bí mật |
| Phân phối public key/chứng thư | **Có thể** | Kiểm tra danh tính, chứng thư, kênh phân phối; chưa tuyên bố cho ký mới |
| Kiểm tra metadata, tham số, chứng thư | **Có** | Không mở quyền sử dụng sản xuất |
| Kiểm tra chứng minh sở hữu khóa hoặc phép toán thử | **Có thể** | Chỉ qua quy trình kiểm thử được phê duyệt, cô lập khỏi dữ liệu nghiệp vụ |
| Tạo backup hoặc cấu hình replication | **Có thể** | Theo key policy và cơ chế sao lưu được KMS/HSM hỗ trợ |
| Chuẩn bị IAM và policy có điều kiện | **Có** | Quyền sản xuất phải tiếp tục bị chặn đến lúc kích hoạt |
| Dùng để mã hóa dữ liệu production mới | **Không** | Chỉ khi đã active và được cấp quyền tương ứng |
| Dùng để ký tài liệu production | **Không** | Chỉ khi đã active và workflow ký đã được chấp thuận |
| Dùng như khóa thỏa thuận cho phiên production | **Không** | Chỉ sau khi giao thức/key usage cho phép |
| Xuất private key/DEK ra file để debug | **Không nên** | Thường trái chính sách bảo vệ khóa; không phải điều kiện để kích hoạt |

**Điểm tinh tế:** Một số thao tác kiểm thử mật mã hoặc **proof of possession** có thể được cho phép ở pre-activation, tùy tiêu chuẩn và quy trình. Vì thế, không phát biểu cứng rằng “trước kích hoạt mọi lệnh mật mã đều bất hợp pháp”. Điều phải được cấm là **sử dụng cho mục đích nghiệp vụ chưa được phê duyệt**; các thao tác kiểm tra đặc biệt phải được quy định và kiểm toán riêng.

### Key usage trước kích hoạt có thể bị ràng buộc theo từng operation

Ví dụ đối với khóa ký, có thể cho `GetPublicKey` và kiểm tra chứng thư, nhưng phải chặn `Sign` từ ứng dụng production. Với KEK, có thể đọc metadata `DescribeKey` nhưng không mở `WrapKey` cho các DEK mới. Với DEK đã tạo, có thể kiểm tra thuật toán và quyền lưu trữ, nhưng chưa được dùng cho dữ liệu thật.

Bất kỳ ngoại lệ kiểm thử nào cũng phải dùng **dữ liệu kiểm thử**, **danh tính kiểm thử**, phạm vi được phép và bằng chứng phê duyệt; không nên sử dụng ngoại lệ để thực hiện thao tác production trá hình.

## 5. Các điều kiện cần đạt trước khi kích hoạt

Một checklist sẵn sàng kích hoạt nên có ít nhất sáu nhóm điều kiện.

### 5.1. Tính hợp lệ của khóa và nguồn tạo

- Key material được tạo từ **CSPRNG/DRBG** hoặc mô-đun mật mã được phê duyệt, không sinh từ timestamp, seed cố định hoặc nguồn ngẫu nhiên dễ đoán.
- Thuật toán, kích thước khóa, curve, purpose và tham số khớp chính sách (ví dụ AES-256, ECDSA P-256, RSA-PSS, X25519 tùy trường hợp).
- Nếu nhập khóa vào KMS/HSM, có bằng chứng **nguồn gốc vật liệu nhập**; đưa một khóa yếu vào HSM không biến nó thành khóa mạnh.
- Không phát hiện sự cố compromise, trùng key material do clone, rò rỉ private key hoặc nguồn tạo không tin cậy.

### 5.2. Định danh và metadata

- Key ID/version không mơ hồ, gắn đúng môi trường, tenant, owner và ứng dụng.
- Có metadata về key usage, cryptoperiod, thuật toán, mức bảo vệ và phương án khôi phục.
- Các giá trị alias, chứng thư và public key trỏ đúng **phiên bản khóa dự kiến**, không nhầm với phiên bản đang active.

### 5.3. Quyền truy cập và phân tách nhiệm vụ

- IAM/key policy hạn chế `Encrypt`, `Decrypt`, `Sign`, `GenerateMac`, `DeriveKey`, `Wrap`, `Unwrap` theo nhu cầu thực tế.
- Chỉ người/phần mềm được ủy quyền có thể đổi trạng thái, sửa policy hoặc thay alias.
- Có người chịu trách nhiệm phê duyệt độc lập; những thao tác đặc biệt có thể cần **dual control**.
- Audit về tạo khóa, cấu hình và phê duyệt đã hoạt động; log không chứa private key, DEK, KEK hoặc session secret.

### 5.4. Khả năng vận hành và tương thích

- Đã thử các luồng cần thiết ở môi trường **tách biệt hoặc cơ chế thử nghiệm được cho phép**, không nhầm với việc dùng khóa pre-activation để phục vụ production.
- Khách hàng/bên nhận đã biết public key/chứng thư mới nếu cần xác minh chữ ký.
- Bộ phận vận hành đã có runbook cho kích hoạt thất bại, rollback, sự cố key version và liên hệ người chịu trách nhiệm.

### 5.5. Sao lưu và phục hồi

- Đã xác định việc mất khóa có làm mất khả năng giải mã dữ liệu hay không.
- Với private key/KEK không xuất được, cơ chế replication, backup/DR thực tế của KMS/HSM đã được đánh giá.
- Không tạo bản sao plaintext của key material chỉ để “dễ khôi phục”; nếu cần recovery, dùng cơ chế được phê duyệt và kiểm soát chặt.

### 5.6. Phê duyệt và thời điểm

- Có **ngày/giờ kích hoạt** và múi giờ được chuẩn hóa, thường lưu thời gian UTC theo kiểu `Instant`.
- Quy trình xác định rõ điều kiện **đạt/không đạt**. Thiếu bất kỳ điều kiện bắt buộc nào phải **fail closed**.
- Đã quyết định ai có quyền trì hoãn, hủy kế hoạch, thực hiện rollback và cách thông báo cho các dịch vụ phụ thuộc.

## 6. Pre-activation và cryptoperiod

**Cryptoperiod** là khoảng thời gian một khóa được cho phép sử dụng cho mục đích cụ thể theo chính sách mật mã. **Activation date** thường là một mốc quan trọng trong cryptoperiod nhưng không thay thế hoàn toàn khái niệm thời hạn sử dụng.

Một khóa có thể có nhiều giới hạn:

~~~text
key_created_at:       2030-01-02T08:00:00Z
activation_not_before:2030-01-10T00:00:00Z
new_protection_until: 2030-04-10T00:00:00Z
legacy_processing:    theo chính sách sau thời hạn bảo vệ mới
destroy_after:        chỉ sau khi hết phụ thuộc và retention
~~~

Đây là **ví dụ lịch thời gian**, không phải chính sách thực tế. Key `v2` có thể đã được tạo từ ngày 2/1 nhưng **chưa được phép ký/mã hóa production** trước ngày 10/1.

### 6.1. “Kích hoạt theo lịch” phải có kiểm soát trạng thái

Không nên chỉ kiểm tra `now >= activationNotBefore` và tự mở quyền. Cần cả:

~~~text
AllowedNewUse =
    (lifecycleState == ACTIVE)
    AND approvalIsEffective
    AND (now >= activationNotBefore)
    AND (now < newUseNotAfter)
    AND principalHasRequiredPermission
    AND operationMatchesKeyUsage
    AND keyIsNotCompromised
~~~

Phép kiểm tra ở ứng dụng chỉ là **một lớp**. Quyền thực tế tại KMS/HSM, key policy và thành phần cung cấp khóa phải đồng bộ với trạng thái. Nếu metadata nói `PRE_ACTIVATION` nhưng một principal có thể gọi `Sign` trực tiếp qua KMS, mô hình kiểm soát **đã thất bại**.

### 6.2. Đồng hồ và múi giờ

- Lưu mốc thời gian theo UTC và dùng `Instant`/timestamp có timezone rõ ràng; không dựa vào chuỗi giờ địa phương mơ hồ.
- Có chính sách cho **độ lệch đồng hồ**, trạng thái nguồn thời gian và xử lý khi đồng hồ hệ thống sai. Tránh mỗi node tự quyết định activation theo đồng hồ khác nhau mà không phối hợp.
- Thời điểm có hiệu lực nên được xác lập bởi **control plane đáng tin**, thay vì chỉ bởi đồng hồ của từng process ứng dụng.
- Nếu thay đổi thời gian kích hoạt hoặc tạm dừng khẩn cấp, phải bảo đảm thay đổi **được áp dụng trước khi có thao tác mới**, không lệ thuộc cache chưa được vô hiệu hóa.

**Không nhầm activation timestamp với timestamp của chữ ký số.** Thời điểm key được **ủy quyền ký** là chính sách quản trị. Một **trusted timestamp của TSA** cho chữ ký là bằng chứng mật mã về sự tồn tại của một hash/chữ ký trước hoặc tại mốc thời gian được chứng thực. Hai thông tin không thay thế nhau.

## 7. Pre-activation theo từng loại khóa

### 7.1. Khóa đối xứng DEK: chuẩn bị trước khi mã hóa dữ liệu mới

DEK dùng cho AES-GCM phải có key material đủ entropy, key ID/version, quyền mã hóa và quy tắc nonce. Trong pre-activation, hệ thống có thể tạo DEK mới, kiểm tra metadata và đường bảo vệ DEK. Nhưng **không nên bắt đầu dùng DEK mới để mã hóa record production** trước khi cutover chính thức.

Khi kích hoạt, mọi instance cùng ghi dữ liệu mới cần xác định đúng phiên bản DEK. Dùng cùng một DEK trên nhiều node còn đòi quản lý **nonce AES-GCM không lặp dưới cùng khóa**. Kích hoạt đúng key nhưng cấp nonce sai vẫn có thể phá vỡ an toàn.

**Không mặc nhiên cần sinh sẵn mọi DEK.** Nhiều hệ thống tạo DEK theo yêu cầu và kích hoạt gần như đồng thời trong workflow; pre-activation có thể rất ngắn và nằm trong một giao dịch kiểm soát. Khái niệm trạng thái vẫn hữu ích để xác định điều kiện cho phép sử dụng.

### 7.2. KEK và envelope encryption

KEK trong KMS/HSM có thể được tạo trước để chuẩn bị chuyển đổi bọc DEK. Trạng thái pre-activation cho phép kiểm tra quyền **Wrap/Unwrap** và khả năng truy cập theo chính sách, nhưng chưa nên dùng KEK đó làm **lớp bảo vệ chính thức của DEK mới** trước thời điểm được phê duyệt.

Ví dụ, `kek-v2` được tạo và cấu hình trong KMS, nhưng hệ thống tiếp tục bọc DEK mới dưới `kek-v1` cho đến cutover. Sau khi `kek-v2` active, luồng mã hóa mới dùng `kek-v2` theo chính sách. Việc **rewrap các DEK cũ** là một quy trình riêng, thường cần giữ `kek-v1` cho `Unwrap` đến khi xác nhận không còn bản bọc phụ thuộc.

**Chuyển KEK không giống chuyển DEK.** Chỉ đổi KEK có thể cho phép giữ nguyên ciphertext dữ liệu; đổi DEK thường kéo theo đánh giá mã hóa lại dữ liệu.

### 7.3. Khóa ký số

Signing key thường cần nhiều chuẩn bị nhất: sinh private key, bảo vệ không xuất được khi thích hợp, cấp chứng thư, phân phối public key, kiểm tra trust chain và key usage, cấu hình service identity, chính sách `Sign` và kế hoạch duy trì xác minh chữ ký cũ.

Ở pre-activation, cần đặc biệt chặn **ký production** bằng khóa mới trước khi public key/chứng thư của nó đã được bên xác minh chấp nhận. Nếu có thao tác proof of possession hoặc xác minh kỹ thuật trước kích hoạt, chúng phải được kiểm soát và không được phép tạo chữ ký nghiệp vụ ngoài dự kiến.

**Thời điểm bắt đầu hiệu lực chứng thư (`NotBefore`)** và thời điểm được phép sử dụng private signing key theo quy trình **không phải một khái niệm**. Một chứng thư có thể đã hợp lệ về PKI nhưng tổ chức vẫn chưa phê duyệt key để ký sản xuất. Ngược lại, chính sách nội bộ không thể làm chứng thư đã hết hạn hoặc chưa hợp lệ trở thành chứng thư được bên nhận chấp nhận.

### 7.4. Khóa thỏa thuận ECDH/X25519

Với **static agreement key**, pre-activation có thể là giai đoạn phân phối public key và kiểm tra peer trust trước khi cho phép `DeriveKey` cho phiên mới. Khi chuyển khóa, hai bên cần thống nhất group, định dạng, KDF, key version và chính sách chống MITM.

Với **ephemeral ECDHE**, giai đoạn tiền kích hoạt có thể rất ngắn hoặc được quản lý **ngầm trong state machine của handshake**: private/public key tạm được sinh, peer key được xác thực theo giao thức rồi mới đưa shared secret vào lịch dẫn xuất traffic key cho phiên. Không nên buộc mỗi private ECDHE key ngắn hạn phải có một quy trình phê duyệt thủ công, nhưng vẫn phải bảo đảm **không sử dụng bí mật trước khi các kiểm tra giao thức cần thiết hoàn thành**.

### 7.5. HMAC key và password-derived KEK

HMAC key mới chỉ nên bắt đầu tạo MAC production sau khi các bên xác minh đã nhận đúng key version và quyền tương ứng. Với password-derived KEK, việc “sinh trước” có thể không phù hợp vì KEK chỉ được dẫn xuất sau khi có mật khẩu/nguồn bí mật hợp lệ; pre-activation lúc này chủ yếu là **chuẩn bị thuật toán, salt/KDF parameters, định dạng wrapped DEK và đường recovery**.

Không coi pre-activation là lý do để **lưu password, raw KEK hoặc private key ở dạng rõ** trong hệ thống cấu hình.

## 8. Key inventory: những gì cần ghi trước khi kích hoạt

Khóa chưa active vẫn là **tài sản nhạy cảm**, cần có bản ghi quản lý riêng. Một schema khái niệm:

~~~yaml
keyId: "billing-signing-v2"
version: "v2"
lifecycleState: "PRE_ACTIVATION"
purpose: "SIGN"
algorithm: "ECDSA_P256_SHA256"
environment: "production"
owner: "billing-security-owner"
custodian: "platform-key-management"
keyMaterialLocation: "HSM key handle (không chứa secret)"
createdAtUtc: "2030-01-02T08:00:00Z"
activationNotBeforeUtc: "2030-01-10T00:00:00Z"
newUseNotAfterUtc: "2030-04-10T00:00:00Z"
allowedProductionOpsBeforeActivation: []
approvedSignService: "billing-signing-service"
approvalRef: "approval-record-id"
testEvidenceRef: "reviewed-test-report-id"
certificateRef: "certificate-identifier"
recoveryPolicyRef: "policy-version"
auditCorrelationId: "request-id"
~~~

Đây là **minh họa metadata**, **không phải file YAML cần ghi vào repo hoặc cấu hình được KMS nhận trực tiếp**. Các trường như `owner`, `approvalRef`, `policyRef` cần được đối chiếu với hệ thống cấp quyền thật. Không lưu raw private key, DEK, KEK, seed, password hoặc HMAC key trong inventory.

### Quy tắc đối với metadata

- `keyId` + `version` phải phân biệt rõ các bản khóa, không chỉ dựa vào alias có thể thay đổi.
- `algorithm`, `purpose`, `environment` phải được kiểm tra với **key type** và định dạng vật liệu thực tế, không chỉ tin chuỗi metadata.
- `lifecycleState` và `approvalRef` phải do **control plane đáng tin** cập nhật; một ứng dụng bất kỳ không được tự viết `ACTIVE`.
- `activationNotBeforeUtc` là **điều kiện cần**, không phải điều kiện đủ.
- Khi có thay đổi ngoài kế hoạch, cần lịch sử phiên bản, người phê duyệt, lý do, thời điểm và trạng thái cuối cùng.

## 9. KMS/HSM: trạng thái khái niệm và trạng thái sản phẩm không trùng nhau

Một vấn đề triển khai lớn là **NIST-style lifecycle state** và **resource state của nhà cung cấp KMS** không dùng cùng tập tên hoặc cùng ý nghĩa.

| Khái niệm | Mô hình vòng đời | Trong một KMS/HSM cụ thể có thể biểu diễn bằng |
| --- | --- | --- |
| Khóa được tạo nhưng chưa dùng | **Pre-activation** | Tài nguyên đã tạo + policy chặn cryptographic operations; hoặc trạng thái pending/import theo sản phẩm |
| Khóa được cho phép dùng | **Active** | Key enabled + IAM/key policy phù hợp + thời gian cutover + app routing |
| Tạm dừng quyền | **Suspended** | Disable hoặc chặn principal/operation theo chính sách |
| Ngừng bảo vệ dữ liệu mới | **Deactivated** | Ứng dụng ngừng chọn key version cũ; có thể còn quyền giải mã/xác minh |
| Nghi bị lộ | **Compromised** | Incident state ngoài KMS + disable/revoke/grant cleanup/rotate |
| Tiêu hủy | **Destroyed** | Deletion/destroy material, có thể trải qua giai đoạn pending deletion và quy tắc backup |

**Không phải KMS nào cũng có API `SetKeyState(PRE_ACTIVATION)`**. Hơn nữa, một số dịch vụ KMS tạo khóa mới ở trạng thái **có thể sử dụng ngay** nếu principal được cấp quyền. Nếu thiết kế yêu cầu pre-activation, đội ngũ cần tạo **lớp chặn thực tế** thông qua IAM/key policy, cơ chế disable, routing/alias và control plane theo điều kiện mà sản phẩm hỗ trợ.

### Tránh “chỉ gắn cờ ở ứng dụng”

Mô hình lỗi:

~~~text
App database: lifecycleState = PRE_ACTIVATION
KMS API: service-role vẫn được kms:Sign trên key vừa tạo
=> service-role hoặc attacker gọi KMS trực tiếp vẫn ký được.
~~~

Cách khắc phục là **defense in depth**:

1. Chặn trước khi sử dụng trong **control plane/routing** của ứng dụng.
2. Giới hạn quyền thực hiện phép toán **ở phía KMS/HSM hoặc provider** đến thời điểm được phép.
3. Yêu cầu kiểm tra quyền/thời gian/trạng thái trong đường xử lý yêu cầu.
4. Audit cả **đổi trạng thái**, **thay policy**, **đổi alias** lẫn **các phép toán mật mã thực tế**.
5. Kiểm thử rằng principal ứng dụng **không thể** gọi `Sign`/`Encrypt`/`DeriveKey` trên khóa chưa active, kể cả khi bỏ qua lớp ứng dụng thông thường.

### Khi nào được dùng KMS `Disabled` để mô phỏng pre-activation?

Đây **có thể** là một biện pháp nếu dịch vụ hỗ trợ việc enable/disable phù hợp và không cản trở các bước chuẩn bị hợp lệ. Tuy nhiên, `Disabled` có thể chặn **mọi** phép toán, kể cả một số bài kiểm thử hoặc giải mã hợp lệ. Thay đổi trạng thái phải được đánh giá tác động lên các quyền khác, không dùng như ánh xạ 1–1 tuyệt đối với pre-activation.

**Pending import, pending replication hay pending deletion** cũng có ngữ nghĩa riêng của từng nền tảng, không mặc định tương đương pre-activation.

## 10. Ví dụ Java 11+: kiểm tra chính sách trước khi sử dụng khóa mới

Đoạn mã sau minh họa **policy gate ở tầng ứng dụng**: một khóa chỉ được phép dùng cho mục đích bảo vệ dữ liệu mới khi trạng thái logic là `ACTIVE`, thời gian nằm trong cửa sổ đã phê duyệt và operation đúng purpose. **Không có key material** trong ví dụ; tất cả là metadata. Do đó mã **không tạo hay thực thi khóa thật** và **không thể thay thế IAM của KMS/HSM**.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.EnumSet;

public final class PreActivationGateDemo {

    enum LifecycleState {
        PRE_ACTIVATION, ACTIVE, SUSPENDED,
        DEACTIVATED, COMPROMISED, DESTROYED
    }

    enum Operation {
        ENCRYPT, SIGN, GENERATE_MAC, DERIVE_SESSION_KEY
    }

    static final class KeyMetadata {
        final String keyId;
        final LifecycleState state;
        final Instant activationNotBefore;
        final Instant newUseNotAfter;
        final EnumSet<Operation> permittedOperations;

        KeyMetadata(
                String keyId,
                LifecycleState state,
                Instant activationNotBefore,
                Instant newUseNotAfter,
                EnumSet<Operation> permittedOperations) {

            if (keyId == null || keyId.isEmpty()
                    || state == null
                    || activationNotBefore == null
                    || newUseNotAfter == null
                    || !activationNotBefore.isBefore(newUseNotAfter)
                    || permittedOperations == null) {
                throw new IllegalArgumentException("Invalid metadata");
            }

            this.keyId = keyId;
            this.state = state;
            this.activationNotBefore = activationNotBefore;
            this.newUseNotAfter = newUseNotAfter;
            this.permittedOperations = permittedOperations.clone();
        }
    }

    static void requireAuthorizedForNewUse(
            KeyMetadata key, Operation requested, Clock clock) {

        Instant now = Instant.now(clock);

        if (key.state != LifecycleState.ACTIVE) {
            throw new SecurityException(
                    "Key is not active: " + key.keyId);
        }
        if (now.isBefore(key.activationNotBefore)
                || !now.isBefore(key.newUseNotAfter)) {
            throw new SecurityException("Outside activation window");
        }
        if (requested == null
                || !key.permittedOperations.contains(requested)) {
            throw new SecurityException("Operation not permitted");
        }
    }

    public static void main(String[] args) {
        Instant from = Instant.parse("2030-01-10T00:00:00Z");
        Instant until = Instant.parse("2030-04-10T00:00:00Z");
        Clock demoClock = Clock.fixed(
                Instant.parse("2030-01-11T12:00:00Z"),
                java.time.ZoneOffset.UTC);

        KeyMetadata pending = new KeyMetadata(
                "billing-signing-v2",
                LifecycleState.PRE_ACTIVATION,
                from, until, EnumSet.of(Operation.SIGN));

        try {
            requireAuthorizedForNewUse(
                    pending, Operation.SIGN, demoClock);
            throw new AssertionError("Must not authorize pending key");
        } catch (SecurityException expected) {
            System.out.println("PRE_ACTIVATION: rejected");
        }

        // Metadata ACTIVE chỉ được phát hành bởi control plane
        // sau khi kiểm tra phê duyệt và áp dụng policy tại HSM/KMS.
        KeyMetadata activated = new KeyMetadata(
                "billing-signing-v2",
                LifecycleState.ACTIVE,
                from, until, EnumSet.of(Operation.SIGN));

        requireAuthorizedForNewUse(
                activated, Operation.SIGN, demoClock);
        System.out.println("ACTIVE: allowed for SIGN");

        try {
            requireAuthorizedForNewUse(
                    activated, Operation.ENCRYPT, demoClock);
            throw new AssertionError("Wrong operation must fail");
        } catch (SecurityException expected) {
            System.out.println("ENCRYPT: rejected for signing key");
        }
    }
}
~~~

### Kết quả dự kiến

~~~text
PRE_ACTIVATION: rejected
ACTIVE: allowed for SIGN
ENCRYPT: rejected for signing key
~~~

### Những gì ví dụ làm đúng

- Trạng thái và các thời điểm **đều được kiểm tra**, không chỉ nhìn alias.
- Dùng `Instant` và `Clock` giúp kiểm thử mốc UTC một cách xác định.
- Một signing key chỉ cho phép `SIGN`, không mở rộng mặc định cho `ENCRYPT`.
- Khi pre-activation, yêu cầu sử dụng bị chặn theo **fail closed**.

### Những gì ví dụ chưa giải quyết

**Đây chỉ là ví dụ policy logic.** Trong production cần thêm:

1. **Xác thực danh tính** principal và kiểm tra quyền ở control plane/KMS/HSM.
2. **Nguồn metadata đáng tin**, chống người gọi tự đưa `state=ACTIVE`.
3. **Kích hoạt nguyên tử** có version/compare-and-swap, ngăn hai người hoặc hai job ghi trạng thái mâu thuẫn.
4. **Đảm bảo thứ tự thao tác:** quyền KMS, routing alias và bản ghi active phải được chuyển bằng một quy trình chuyển trạng thái có kiểm soát; cập nhật thất bại phải được xử lý.
5. **Khả năng thu hồi tức thời:** nếu phát hiện compromise, cache metadata của application không được tiếp tục cho phép sử dụng khóa cũ.
6. **Kiểm soát TOCTOU:** giữa bước `requireAuthorizedForNewUse` và phép gọi `KMS Sign`, key có thể đã bị suspend. Phép toán tại KMS cũng phải bị ràng buộc bởi quyền/trạng thái hiện hành.
7. **Audit và giám sát:** kiểm tra quyết định phê duyệt, kết quả kiểm tra, thao tác sử dụng thực tế và cảnh báo.

Không lấy `KeyMetadata activated` do caller khởi tạo như một bằng chứng đã phê duyệt trong production. Trong ví dụ, việc tạo object `ACTIVE` chỉ giúp minh họa logic kiểm tra hai trạng thái; quyền thay đổi trạng thái thật phải được giới hạn chặt.

## 11. Kích hoạt và chuyển đổi phiên bản khóa: case study signing key

Giả sử hệ thống **billing-service** cần xoay từ `signing-v1` sang `signing-v2` mà vẫn cho khách hàng xác minh hóa đơn cũ.

### Các bước an toàn

1. **Key owner** phê duyệt thuật toán, mục đích, cryptoperiod và mốc dự kiến chuyển đổi.
2. **Key custodian** tạo `signing-v2` trong HSM, ưu tiên private key không xuất được theo chính sách. Key `v2` ở pre-activation, `Sign` production bị chặn.
3. Nhận chứng thư/phân phối public key `v2` và kiểm tra khả năng xác minh của các client. Kiểm thử kỹ thuật được cô lập khỏi luồng hóa đơn production.
4. Kiểm tra trust store, key usage, thuật toán, thời gian chứng thư, IAM, log và việc không có bên nào vô tình sử dụng `v2`.
5. **Security reviewer** xác nhận preflight; quy trình phê duyệt độc lập cho phép thay trạng thái.
6. Control plane đưa `v2` vào phạm vi được phép, chuyển luồng **ký mới** sang `v2` theo cơ chế có kiểm soát; mọi thay đổi có audit.
7. Sau khi xác nhận phần lớn/tất cả luồng ký mới đã chuyển, ngừng cho `v1` ký mới và đưa `v1` về trạng thái nghỉ sử dụng thích hợp.
8. Giữ public verification key, chứng thư và bằng chứng cần thiết của `v1` để xác minh **chữ ký lịch sử**. Chỉ hủy private key `v1` khi không còn phụ thuộc và đáp ứng yêu cầu lưu giữ.

~~~mermaid
sequenceDiagram
    participant Owner as Key owner
    participant Custodian as Key custodian
    participant Control as Control plane
    participant HSM as HSM/KMS
    participant App as Billing service
    participant Verifier as Verifier
    Owner->>Custodian: Phê duyệt tạo signing-v2
    Custodian->>HSM: Tạo key v2, chặn Sign production
    HSM-->>Control: Key ID v2, metadata, public key
    Control->>Verifier: Phân phối public key/chứng thư v2
    Verifier-->>Control: Xác nhận sẵn sàng xác minh
    Owner->>Control: Phê duyệt activation theo chính sách
    Control->>HSM: Áp dụng quyền/trạng thái kích hoạt v2
    Control->>App: Cutover routing ký mới sang v2
    App->>HSM: Sign với key v2 được cấp phép
    HSM-->>App: Signature v2
    Control->>HSM: Ngừng Sign mới bằng v1 theo chính sách
    Note over Verifier: Vẫn xác minh được chữ ký v1 lịch sử
~~~

Sơ đồ là kiến trúc minh họa; **thứ tự triển khai chính xác** phải phù hợp khả năng KMS, quyền, idempotency và phương án chuyển đổi nhiều dịch vụ. Đặc biệt, trong khoảng thời gian chuyển đổi, cần kiểm soát hành vi của các node còn dùng cache/alias cũ.

### Kế hoạch rollback phải được chuẩn bị khi key còn pre-activation

Nếu `v2` chưa được sử dụng cho production, hủy kế hoạch tương đối đơn giản: giữ `v1` active, thu hồi các quyền chuẩn bị và lưu lý do. Nhưng nếu `v2` **đã phát hành chữ ký hoặc mã hóa dữ liệu thật**, rollback **không thể giả định dữ liệu mới chưa tồn tại**:

- Các hóa đơn đã ký bằng `v2` vẫn cần public key/chứng thư và bằng chứng xác minh hợp lệ.
- Các bản mã dùng DEK/KEK `v2` phải tiếp tục giải mã được hoặc được di chuyển có kiểm chứng.
- Không hủy `v2` chỉ vì ứng dụng đã chuyển lại routing sang `v1`.

**Rollback routing** khác với **tiêu hủy key material**.

## 12. Case study: chuẩn bị KEK cho envelope encryption

Một dịch vụ lưu hồ sơ người dùng đang dùng `KEK-v1` trong KMS để bọc DEK. Tổ chức cần tạo `KEK-v2` phục vụ kế hoạch xoay vòng.

### Trong pre-activation

- Tạo `KEK-v2` bằng cơ chế KMS có hỗ trợ và bảo đảm nguồn ngẫu nhiên.
- Lưu `keyId/version`, owner, mục đích **WRAP/UNWRAP**, thuật toán, policy và cryptoperiod.
- Chuẩn bị quyền theo nhóm dịch vụ, nhưng **không cấp quyền production Wrap** cho `v2` trước khi approved.
- Bảo đảm service/metadata store có thể ghi nhận **wrapped DEK kèm đúng key version**, tránh nhầm `v1`/`v2`.
- Chuẩn bị kế hoạch **rewrap** DEK cũ và kiểm tra khả năng restore trước khi dừng hoặc xóa `v1`.

### Khi active

- Cho phép bọc **DEK mới** dưới `KEK-v2` theo phạm vi đã phê duyệt.
- Các bản bọc `v1` tiếp tục được giải bọc bằng `KEK-v1` nếu còn dữ liệu phụ thuộc.
- Khi thực hiện rewrap, kiểm tra tính toàn vẹn và chỉ thay wrapped DEK/metadata sau khi có xác nhận thành công. Không nhầm rewrap với mã hóa lại dữ liệu.
- Ghi audit về identity, key version, thao tác wrap/unwrap, thay trạng thái và sự cố, **không ghi raw DEK/KEK**.

### Rủi ro nếu bỏ pre-activation gate

Nếu `KEK-v2` vừa tạo đã có quyền sử dụng, một instance mới có thể bắt đầu bọc DEK bằng `v2` trước khi các instance cũ hỗ trợ giải bọc. Kết quả là **một phần dữ liệu ghi thành công nhưng không đọc được ở những service còn dùng cấu hình cũ**. Sự cố là kết quả của quản trị vòng đời và rollout, không nhất thiết do thuật toán AES hay KMS bị lỗi.

## 13. Phân công trách nhiệm và kiểm toán

### Vai trò

| Vai trò | Trách nhiệm trước kích hoạt | Không nên được phép mặc định |
| --- | --- | --- |
| **Key owner** | Phê duyệt mục đích, cryptoperiod, bên sử dụng, mốc kích hoạt và rủi ro | Tự sửa IAM để dùng khóa không qua quy trình |
| **Key custodian** | Sinh/lưu khóa, cấu hình KMS/HSM, backup, policy và ghi bằng chứng | Sử dụng private key/DEK trái nhiệm vụ |
| **Application owner** | Kiểm thử tương thích, chuẩn bị rollout, routing/key version | Tự đổi trạng thái logic thành ACTIVE |
| **Security reviewer** | Rà soát thuật toán, key usage, phân quyền, thiết kế fail closed và DR | Tự tạo chứng cứ phê duyệt cho thay đổi của mình |
| **Auditor** | Đối chiếu phê duyệt, thay đổi, kết quả kiểm tra và lịch sử trạng thái | Sửa audit hoặc truy cập key material |
| **Incident responder** | Có quyền cách ly, suspend hoặc thu hồi theo quy trình khẩn cấp | Xóa vĩnh viễn key trước khi kiểm kê phụ thuộc |

### Nhật ký tối thiểu

Một hệ thống giám sát nên ghi:

~~~text
eventType: KEY_ACTIVATION_APPROVED
keyId: billing-signing-v2
fromState: PRE_ACTIVATION
toState: ACTIVE
requestedBy: identity-A
approvedBy: identity-B
effectiveAtUtc: 2030-01-10T00:00:00Z
appliedPolicyVersion: policy-07
controlPlaneRevision: revision-38
result: SUCCESS
correlationId: request-xxx
~~~

Bản ghi ví dụ **không chứa bí mật**; ở hệ thống thật cần bảo vệ tính toàn vẹn log, nguồn identity và mốc thời gian. Tài liệu `approvedBy` không tự chứng minh có dual control nếu cả hai danh tính do cùng một người kiểm soát.

Cần audit thêm **CREATE, IMPORT, GRANT, POLICY_CHANGE, ALIAS_CHANGE, ACTIVATE, SUSPEND, DEACTIVATE, DESTROY_SCHEDULED, DESTROY_COMPLETED** và các lần gọi phép toán mật mã thực tế trong mức chi tiết dịch vụ hỗ trợ.

### Chỉ số giám sát hữu ích

- Số khóa pre-activation **quá ngày dự kiến** nhưng chưa có quyết định tiếp theo.
- Số yêu cầu sử dụng production bị chặn trên khóa chưa active.
- Số key được active **thiếu approval evidence** hoặc sai giờ hiệu lực.
- Số key còn active nhưng không có owner/custodian hiện hành.
- Số lần sửa policy/alias gần mốc cutover và số phiên bản bị sử dụng ngoài dự kiến.
- Số sự cố rollback hoặc bản mã/chữ ký được tạo bằng key version sai.

**Không coi metric “0 lần chặn” là bằng chứng chắc chắn rằng policy đúng**: cũng có thể chưa ai thực hiện kiểm thử chặn. Cần có **negative test** trực tiếp với principal và đường API cần bảo vệ.

## 14. Xử lý trường hợp pre-activation thất bại

Có những lý do một khóa chưa dùng vẫn phải bị loại bỏ hoặc điều tra.

| Tình huống | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Sai thuật toán/độ dài/curve so với chính sách | Kết quả không tương thích hoặc không đạt mức an toàn | Không kích hoạt; tạo khóa mới đúng thông số |
| Sinh khóa từ entropy/RNG không đáng tin | Vật liệu khóa có thể đoán được | Không dùng, đánh giá nguồn và tạo lại từ nguồn tin cậy |
| Private key bị xuất ra ngoài quy trình | Khóa có thể đã lộ dù chưa ký production | Cô lập, điều tra, tạo thay thế; không chỉ đổi nhãn |
| Public key/chứng thư phân phối nhầm | Bên nhận có thể tin nhầm key hoặc không xác minh được | Dừng cutover, điều chỉnh trust distribution và đối soát |
| IAM vô tình cho phép `Sign` trước activation | Key có thể đã tạo chữ ký thật | Chặn quyền, điều tra log, xác định chữ ký/bản mã đã tạo |
| Approval bị thiếu hoặc danh tính phê duyệt không phù hợp | Thay đổi không được ủy quyền | Fail closed, yêu cầu phê duyệt độc lập |
| Không đồng bộ giữa node/region | Một số instance dùng v1, số khác dùng v2 không đúng kế hoạch | Tạm dừng rollout, khôi phục routing, giữ đủ key version để đọc dữ liệu |
| Thời gian hệ thống bị sai | Kích hoạt quá sớm/muộn hoặc gây ngắt dịch vụ | Dùng control plane đáng tin, đánh giá UTC/clock skew |
| Test dùng production key không đúng quy trình | Vật liệu/đầu ra test có thể lẫn vào dữ liệu thật | Phân tách môi trường/identity, điều tra và thay khóa nếu cần |
| Khóa bị đặt vào lịch xóa | Có nguy cơ mất khả năng sử dụng/khôi phục | Tạm dừng cutover, đánh giá trạng thái dịch vụ, phục hồi theo cơ chế cho phép |

### Khi khóa chưa active nhưng bị nghi compromise

**Không thể khẳng định “chưa active nên chắc chắn vô hại”.** Dù chưa sử dụng cho production, public key có thể đã được đăng ký với đối tác, vật liệu đã được backup, quyền API đã được cấp sai hoặc một số thao tác test đã tạo dữ liệu nhạy cảm. Phải kiểm kê các bản sao và những nơi đã tin cậy key đó.

Hành động thường gồm **chặn dùng**, bảo toàn bằng chứng, xác định nguồn lộ, **tạo key material mới**, cập nhật public key/chứng thư/metadata, thông báo bên phụ thuộc và chỉ tiếp tục activation sau một vòng preflight mới.

### Có được kích hoạt lại chính khóa đã bị đánh dấu Compromised?

Thông thường **không nên** dùng lại vật liệu khóa mà tổ chức đã kết luận bị compromise. Thay alias, đổi password keystore hoặc chuyển nó vào HSM không xóa các bản sao đã bị lấy. Phải tạo khóa mới từ nguồn tin cậy và đánh giá ảnh hưởng lịch sử.

## 15. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách phòng ngừa |
| --- | --- | --- |
| Gộp **CREATED** và **ACTIVE** thành một trạng thái | Cho phép sử dụng trước phê duyệt | Tách trạng thái logic và quyền thực thi |
| Chỉ lưu cờ `pre_activation=true` trong DB | KMS API vẫn có thể chấp nhận `Sign`/`Encrypt` | Chặn tại provider/IAM và đường sử dụng thật |
| Dùng giờ server cục bộ không có timezone | Các node kích hoạt khác thời điểm | UTC/Instant, control plane nhất quán |
| Gắn alias `current` sang v2 trước khi verifier nhận key | Chữ ký mới không xác minh được | Preflight trust distribution và cutover có kiểm soát |
| Bật KEK mới trước khi code cũ hỗ trợ version | Bản bọc mới không mở được ở một số dịch vụ | Triển khai tương thích trước rồi mới cutover |
| Dùng pre-activation để cấp quyền `Sign` rộng cho test | Có thể lạm dụng thành signing oracle | Quyền test riêng, hạn chế dữ liệu và audit |
| Coi KMS `Enabled` là được owner phê duyệt | Không xét mục đích, thời gian, policy | Lifecycle control plane độc lập |
| Coi KMS `Disabled` luôn đồng nghĩa pre-activation | Có thể chặn cả khả năng kiểm thử hoặc đọc dữ liệu cần thiết | Ánh xạ trạng thái theo semantics của sản phẩm |
| Bỏ qua backup/DR của private decrypt key | Mất khóa gây mất dữ liệu | Chính sách recovery, kiểm thử restore có kiểm soát |
| Xóa key v1 ngay sau cutover | Mất khả năng decrypt/verify dữ liệu lịch sử | Inventory phụ thuộc, retirement theo key usage |
| Chỉ kiểm tra đường thành công, không thử từ chối | Có thể vẫn dùng được pre-activation key | Negative tests với principal ứng dụng/KMS |
| Cho cùng một admin tạo, phê duyệt và active | Thiếu phân tách nhiệm vụ | Dual control/phê duyệt độc lập khi cần |
| Sửa state sau khi gọi phép toán sản xuất | Tạo bản mã/chữ ký bằng key chưa active | Fail closed trước mọi thao tác và provider gate |
| Không giữ audit của thay đổi trạng thái | Khó điều tra ai cho phép sử dụng key | Log có xác thực, retention và review |
| Xoay key nhưng không cập nhật token, chứng thư, alias | Khách hàng không giải mã/xác minh được | Kế hoạch rollout đầy đủ theo hệ phụ thuộc |

## 16. Checklist cho đội phát triển và vận hành

Trước khi chuyển một khóa từ **PRE_ACTIVATION** sang **ACTIVE**, hãy kiểm tra:

1. **Key identity:** Key ID/version, owner, custodian, môi trường và mục đích đã được xác nhận?
2. **Vật liệu khóa:** Được sinh/nhập đúng nguồn entropy, thuật toán, độ dài và curve; không có bằng chứng rò rỉ hoặc cấu hình sai?
3. **Nơi lưu trữ:** Key nằm trong KMS/HSM/keystore phù hợp, có chính sách export/backup và kiểm soát truy cập?
4. **Key usage:** Đã giới hạn rõ operation (`Encrypt`, `Sign`, `DeriveKey`, `Wrap`…) và bên được sử dụng? Có tách ký, giải mã, ECDH, HMAC theo chính sách?
5. **Chặn trước kích hoạt:** Đã thử từ chối lời gọi production qua **API KMS/HSM thực tế**, không chỉ qua database cờ trạng thái?
6. **Phê duyệt:** Có approval evidence, phân tách nhiệm vụ, người có quyền hoãn/hủy và cơ chế xử lý khẩn cấp?
7. **Thời gian:** Activation window/cryptoperiod được lưu UTC và áp dụng nhất quán ở control plane?
8. **Chứng thư/public key:** Với signing hoặc ECDH key, bên nhận đã được phân phối và xác minh đúng key/cert/curve chưa?
9. **Khả năng tương thích:** Các client và service biết cách tìm key version mới, có fallback/rollback hợp lệ mà không dùng khóa chưa active?
10. **KMS/HSM:** Semantics `Enabled`, `Disabled`, pending import/replication/deletion đã được hiểu và ánh xạ đúng?
11. **Đối xứng và nonce:** Với DEK AES-GCM, quy tắc tạo nonce không lặp và giới hạn dùng khóa có được kiểm soát?
12. **Envelope encryption:** Với KEK mới, luồng wrap/unwrap/rewrap, metadata bản bọc và bản mã cũ có được kiểm thử?
13. **Dữ liệu/chữ ký cũ:** Khi v2 active và v1 ngừng dùng cho nghiệp vụ mới, còn đủ quyền để verify/decrypt lịch sử theo policy?
14. **Kiểm toán:** Có log `CREATE`, `APPROVE`, `ACTIVATE`, `POLICY_CHANGE`, `USE`, `SUSPEND`, `DESTROY` mà không lộ secret?
15. **Sự cố:** Nếu key bị nghi compromise ngay trong pre-activation, có runbook cô lập, thay key và thông báo đối tác?
16. **Hậu kiểm:** Sau cutover, đã quan sát key version đang sử dụng, các lỗi từ chối, latency và tác động lên ứng dụng/bên nhận?

### Ghi nhớ

**Pre-activation state** là trạng thái **khóa đã được tạo hoặc thiết lập nhưng chưa được phép dùng cho mục đích mật mã nghiệp vụ**. Nó tách **việc chuẩn bị khóa** khỏi **quyết định kích hoạt** để bảo đảm thuật toán, nguồn entropy, key usage, KMS/HSM policy, phân quyền, chứng thư, khả năng phục hồi, lịch rotation và audit đều sẵn sàng. Khi triển khai, **đừng nhầm lifecycle state logic với trạng thái resource của KMS**: khóa có thể đang `Enabled` nhưng vẫn phải bị chặn dùng trong production cho đến khi được phê duyệt, và ngược lại `Disabled` không phải biểu diễn chuẩn của mọi pre-activation. Kiểm soát quan trọng nhất là **fail closed ngay tại nơi thực thi phép toán**, kết hợp phê duyệt độc lập và kiểm tra thời gian/phiên bản. Từ đây, vòng đời khóa mới có thể tiếp tục an toàn sang **Active**, rồi **Suspended/Deactivated**, ứng cứu **Compromised** và cuối cùng **Destroyed** theo chính sách, mà không làm mất khả năng bảo vệ hoặc khôi phục dữ liệu cần giữ.
