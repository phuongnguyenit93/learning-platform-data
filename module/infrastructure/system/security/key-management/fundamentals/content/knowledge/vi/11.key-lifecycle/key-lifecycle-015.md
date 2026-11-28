# Chuyển trạng thái có kiểm soát trong vòng đời khóa

## 1. Chuyển trạng thái có kiểm soát là gì?

**Chuyển trạng thái có kiểm soát (controlled key-state transition)** là việc thay đổi trạng thái sử dụng hoặc mức độ tin cậy của một khóa mật mã **chỉ khi đáp ứng các điều kiện bảo mật, nghiệp vụ, vận hành và kiểm toán đã được xác định trước**.

Ví dụ, một khóa AES đang được dùng để mã hóa dữ liệu mới có thể được chuyển từ **ACTIVE** sang **RETIRED** sau khi hệ thống đã tạo khóa thay thế. Khóa cũ không được tiếp tục mã hóa dữ liệu mới, nhưng có thể cần phục vụ **giải mã dữ liệu lịch sử** trong thời gian cho phép. Ngược lại, nếu khóa bị lộ, hệ thống phải ngăn sử dụng và xử lý ảnh hưởng theo một **quy trình khẩn cấp**, không đơn thuần đổi một nhãn trong cơ sở dữ liệu.

Đây là nội dung cốt lõi của chương **Key lifecycle** trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**. Nó gắn các thao tác **tạo, cấp phát, lưu, sử dụng, xoay vòng, thu hồi và hủy khóa** với mật mã đối xứng, bất đối xứng, chữ ký số, **KMS/HSM**, envelope encryption, IAM và audit.

~~~text
Sinh vật liệu khóa ----> Chỉ định mục đích + chính sách
                                 |
                                 v
                             PRE_ACTIVE
                                 |
                       Kiểm tra sẵn sàng
                                 |
                                 v
                               ACTIVE
                                 |
                       Thay đổi có kiểm soát
                                 |
                  +--------------+---------------+
                  |              |               |
                  v              v               v
              SUSPENDED        RETIRED         REVOKED
                  |              |               |
                  +--------------+---------------+
                                 |
                     Xử lý các phụ thuộc
                                 |
                                 v
                        PENDING_DELETION
                                 |
                     Xác nhận hủy thực tế
                                 |
                                 v
                             DESTROYED
~~~

**Cần phân biệt ba thứ:**

1. **Trạng thái quản trị** mà hệ thống ghi nhận (ví dụ ACTIVE, RETIRED).
2. **Trạng thái kỹ thuật** mà KMS/HSM thực thi (ví dụ enabled, disabled, pending deletion).
3. **Trạng thái tin cậy tại bên sử dụng hoặc xác minh** (ví dụ client còn chấp nhận chứng chỉ, JWKS hoặc cached public key cũ).

Ba thứ này **không tự động đồng bộ**. Một thiết kế đúng phải kiểm soát cả ba trước khi kết luận chuyển trạng thái đã hoàn tất.

> **Phạm vi bài:** Các trạng thái và quy tắc bên dưới là **mô hình tham khảo để thiết kế state machine**, không phải danh sách tên trạng thái bắt buộc của mọi chuẩn hoặc nhà cung cấp KMS. Tên trạng thái, khả năng đảo ngược và ngữ nghĩa API phải được ánh xạ theo hệ thống cụ thể.

## 2. Vì sao không thể chỉ sửa trường status?

Giả sử cơ sở dữ liệu chứa:

~~~yaml
keyId: payments-kek
version: v3
algorithm: AES-256
state: ACTIVE
~~~

Một operator cập nhật trực tiếp thành:

~~~yaml
state: DESTROYED
~~~

Nhưng vật liệu khóa vẫn nằm trong KMS và các service vẫn được quyền **Decrypt/Unwrap**. Hệ thống quản trị nói khóa đã bị hủy, trong khi khóa **vẫn có thể sử dụng**. Trường hợp ngược lại còn nghiêm trọng hơn: KMS đã xóa KEK, nhưng nhiều DEK vẫn chỉ được bảo vệ bằng khóa đó, khiến dữ liệu lịch sử không thể giải mã.

Các lỗi thường gặp nếu đổi status thiếu kiểm soát:

- **Không xác nhận quyền:** service thường có thể tự kích hoạt, thu hồi hoặc xóa khóa.
- **Không kiểm tra điều kiện:** xóa KEK khi còn encrypted DEK phụ thuộc.
- **Không phối hợp ứng dụng:** khóa ký mới ACTIVE nhưng verifier chưa nhận public key mới.
- **Không xử lý race condition:** hai request đồng thời ghi đè trạng thái của nhau.
- **Không kiểm soát cache:** khóa đã REVOKED nhưng một số ứng dụng vẫn dùng alias hoặc trust store cũ.
- **Không có bằng chứng:** không biết ai duyệt chuyển trạng thái, vì sao và khi nào.
- **Không có phương án phục hồi:** thao tác xóa không đảo ngược được thực hiện khi chưa kiểm tra backup.

Do đó, một transition cần tối thiểu **điểm xuất phát, điểm đích, điều kiện được phép, danh tính tác nhân, bằng chứng phê duyệt, thay đổi kỹ thuật, audit và cách xác nhận hậu điều kiện**.

## 3. Những trạng thái thường có trong vòng đời khóa

Có thể định nghĩa một state machine ở mức **key material/version**, ví dụ:

| Trạng thái | Ý nghĩa vận hành | Phép toán thông thường |
|---|---|---|
| **PRE_ACTIVE** | Vật liệu khóa đã được sinh/import và đăng ký nhưng chưa được phép sử dụng chính thức | Chỉ kiểm tra/provision theo quyền; chưa Encrypt hoặc Sign sản xuất |
| **ACTIVE** | Đang trong thời gian sử dụng được phê duyệt | Encrypt, Decrypt, Sign, Verify, Wrap, Unwrap theo key usage và IAM |
| **SUSPENDED** | Tạm ngừng vì nghi vấn, lỗi hoặc bảo trì | Chặn các thao tác nhạy cảm theo chính sách; chờ quyết định tiếp theo |
| **RETIRED** | Ngừng tạo dữ liệu/chữ ký mới, nhưng có thể phục vụ nhu cầu lịch sử được kiểm soát | Thường chặn Encrypt/Sign/Wrap mới; có thể cho Decrypt/Verify/Unwrap cũ |
| **REVOKED** | Quyền sử dụng hoặc niềm tin vào khóa đã bị rút lại, thường do rủi ro/sự cố | Chặn thao tác mới; xử lý lịch sử theo quy trình sự cố và trust policy |
| **PENDING_DELETION** | Khóa đã được đưa vào quy trình hủy nhưng chưa xác nhận hủy hoàn tất | Không cho phép sử dụng bình thường; theo dõi thời hạn và phụ thuộc |
| **DESTROYED** | Việc hủy vật liệu khóa đã được xác nhận theo bằng chứng của cơ chế bảo vệ | Không còn thao tác phụ thuộc private/symmetric key material đó |

### 3.1. Trạng thái là chính sách của hệ thống, không phải mọi khả năng của thiết bị

Một KMS có thể chỉ cung cấp các trạng thái như **enabled, disabled, pending deletion**. Ứng dụng có thể cần phân biệt **SUSPENDED** với **RETIRED** và **REVOKED**, dù KMS đều biểu diễn là disabled. Vì vậy:

- Lưu **business lifecycle state** trong registry được kiểm soát.
- Lưu **KMS provider state** và đối chiếu trạng thái thực tế.
- Thực thi **quyền trên KMS/HSM**, không chỉ từ chối trên giao diện UI.
- Với khóa công khai, theo dõi cả **trust distribution/certificate revocation** ở verifier.

**REVOKED không nhất thiết đồng nghĩa DESTROYED.** Khóa bị thu hồi có thể vẫn cần được giữ cô lập trong giai đoạn điều tra hoặc giải mã phục hồi có kiểm soát. Ngược lại, hủy khóa có thể không làm những bản sao đã bị đánh cắp biến mất.

### 3.2. Compromised là trạng thái hay nguyên nhân?

Một hệ thống có thể thêm trạng thái **COMPROMISED**. Trong mô hình bài này, **compromise được lưu thành lý do/sự kiện bảo mật** và khóa được chuyển sang **REVOKED** để thể hiện hành vi thực thi.

Ví dụ:

~~~yaml
keyId: signing-invoices
materialVersion: v4
state: REVOKED
reasonCode: SUSPECTED_COMPROMISE
incidentId: SEC-241
~~~

Cách này giúp tránh nhầm “đang điều tra khóa bị lộ” với “đã khóa mọi quyền”. Nếu hệ thống chọn trạng thái COMPROMISED riêng, phải quy định **phép toán nào bị chặn ngay** và cách nó liên hệ với REVOKED.

## 4. Sơ đồ chuyển trạng thái đề xuất

~~~mermaid
stateDiagram-v2
    [*] --> PRE_ACTIVE: Generate / Import
    PRE_ACTIVE --> ACTIVE: Activate có phê duyệt
    PRE_ACTIVE --> PENDING_DELETION: Hủy trước kích hoạt

    ACTIVE --> SUSPENDED: Suspend khẩn/tạm thời
    SUSPENDED --> ACTIVE: Resume sau tái đánh giá

    ACTIVE --> RETIRED: Chuyển sang phiên bản thay thế
    SUSPENDED --> RETIRED: Ngừng dùng vĩnh viễn
    ACTIVE --> REVOKED: Thu hồi / compromise
    SUSPENDED --> REVOKED: Rủi ro được xác nhận
    RETIRED --> REVOKED: Phát hiện khóa cũ bị lộ

    RETIRED --> PENDING_DELETION: Hết retention và dependency
    REVOKED --> PENDING_DELETION: Xử lý sự cố / phụ thuộc
    PENDING_DELETION --> DESTROYED: KMS xác nhận hủy
    DESTROYED --> [*]
~~~

Các chuyển đổi chính:

| Từ | Đến | Trường hợp sử dụng |
|---|---|---|
| PRE_ACTIVE | ACTIVE | Kích hoạt khóa đã sẵn sàng |
| PRE_ACTIVE | PENDING_DELETION | Hủy khóa được tạo nhầm/chưa bao giờ kích hoạt |
| ACTIVE | SUSPENDED | Tạm ngừng khi có nghi vấn hoặc sự cố vận hành |
| SUSPENDED | ACTIVE | Khôi phục sau khi rủi ro đã được xử lý và phê duyệt |
| ACTIVE/SUSPENDED | RETIRED | Dừng sử dụng cho thao tác tạo mới, chuyển sang khóa thay thế |
| ACTIVE/SUSPENDED/RETIRED | REVOKED | Thu hồi do compromise, vi phạm chính sách hoặc quyết định tin cậy |
| RETIRED/REVOKED | PENDING_DELETION | Kiểm kê xong dữ liệu/chứng cứ và đủ điều kiện hủy |
| PENDING_DELETION | DESTROYED | Có bằng chứng hủy vật liệu khóa từ cơ chế quản lý |

**Không có chuyển đổi từ DESTROYED về ACTIVE.** Nếu vật liệu đã được hủy thực sự, hệ thống muốn dùng khóa mới phải **Generate** một phiên bản/vật liệu mới.

**Không có REVOKED → ACTIVE** trong state machine tham khảo này, nhằm tránh vô tình tái tin cậy một khóa đã được đánh dấu rủi ro. Nếu nghiệp vụ yêu cầu xem xét lại, hãy dùng quy trình khôi phục đặc biệt với bằng chứng, thay khóa hoặc một mô hình khác được phê duyệt; không cập nhật status trực tiếp.

Một số KMS hỗ trợ **cancel scheduled deletion** trong cửa sổ cho phép. Mô hình tham khảo cố ý **không cho cancel tự động**, vì khả năng đảo ngược phụ thuộc provider, trạng thái trước khi hủy và quy trình phê duyệt. Nếu hỗ trợ, phải mô hình hóa transition và bảo toàn lịch sử rõ ràng, không coi cancel là ACTIVATE.

## 5. Các điều kiện kiểm soát (transition guards)

**Guard** là điều kiện bắt buộc trước khi cho phép một transition xảy ra. Guard không chỉ là biểu thức từ trạng thái A tới B mà là **tập bằng chứng và quyết định quyền**.

| Transition | Guard điển hình |
|---|---|
| **PRE_ACTIVE → ACTIVE** | Key material hợp lệ; algorithm/usage được phép; IAM sẵn sàng; public key/chứng chỉ đã phân phối nếu cần; kiểm tra kỹ thuật đạt; owner duyệt |
| **ACTIVE → SUSPENDED** | Danh tính có quyền suspend; lý do/sự cố; chặn thao tác nhạy cảm; ghi nhận thời điểm có hiệu lực |
| **SUSPENDED → ACTIVE** | Rủi ro đã được giải quyết; kiểm tra lại key material, policy và audit; phê duyệt có thẩm quyền; không có compromise chưa xử lý |
| **ACTIVE → RETIRED** | Khóa thay thế hoạt động; writer/signer đã chuyển; readers/verifiers có thể xử lý phiên bản lịch sử; không còn tác vụ tạo mới dùng khóa cũ |
| **ACTIVE/RETIRED → REVOKED** | Có quyết định thu hồi hoặc sự cố; khóa/nhóm principal bị cô lập; kế hoạch lan truyền tới verifier; bằng chứng incident/audit |
| **RETIRED/REVOKED → PENDING_DELETION** | Đã kiểm kê dependent DEK/ciphertext, backup, token và chữ ký; hết thời hạn lưu giữ; phê duyệt hủy; hủy không phá dữ liệu hợp lệ |
| **PENDING_DELETION → DESTROYED** | Provider/HSM xác nhận hoàn tất; backup và bản sao trong phạm vi quản lý được xử lý; audit ghi nhận; không còn quyền dùng key material |

### 5.1. Emergency revoke có cần đợi đủ người phê duyệt?

**Không nhất thiết.** Trong sự cố khóa bị lộ, chờ quy trình phê duyệt thông thường có thể khiến rủi ro tăng. Một thiết kế có thể cho phép **break-glass** để chặn thao tác nguy hiểm ngay, đi kèm:

- Danh tính và lý do khẩn cấp được ghi nhận.
- Quyền break-glass được giới hạn chặt, xác thực mạnh.
- Phê duyệt hậu kiểm và điều tra bắt buộc.
- Thao tác rút niềm tin/đồng bộ client được theo dõi tới khi hoàn tất.

Ngược lại, **hủy khóa không thể khôi phục** nên thường cần guard khắt khe hơn, chẳng hạn nhiều cấp phê duyệt và kiểm tra phụ thuộc.

### 5.2. Guard phải dựa trên bằng chứng từ hệ thống đáng tin

Không chấp nhận một request như:

~~~json
{
  "targetState": "DESTROYED",
  "dependenciesCleared": true,
  "approved": true
}
~~~

rồi tin luôn hai boolean do caller truyền. Điều kiện **dependenciesCleared** phải được **tính hoặc xác nhận từ inventory**, các bước phê duyệt phải đến từ hệ thống IAM/workflow tin cậy, và việc hủy thực tế phải được KMS/HSM xác nhận.

## 6. Ma trận quyền sử dụng theo trạng thái

Bảng minh họa **policy mặc định bảo thủ**; mỗi hệ thống phải xác định lại theo key usage, loại khóa và quy tắc pháp lý.

| Trạng thái | Encrypt / Wrap mới | Sign mới | Decrypt / Unwrap lịch sử | Verify chữ ký lịch sử |
|---|---|---|---|---|
| PRE_ACTIVE | Không | Không | Không | Chỉ thử nghiệm được kiểm soát |
| ACTIVE | Có, nếu IAM cho phép | Có, nếu IAM cho phép | Có, theo quyền | Có, sau kiểm tra trust |
| SUSPENDED | Không | Không | Mặc định chặn; ngoại lệ phục hồi nếu được duyệt | Phụ thuộc trust policy |
| RETIRED | Không | Không | Có thể cho phép để đọc dữ liệu cũ | Có thể cho phép theo thời điểm và chứng cứ |
| REVOKED | Không | Không | Chỉ quy trình cứu hộ/điều tra có kiểm soát nếu cho phép | Không chấp nhận tùy tiện; cần đánh giá thời điểm và trust |
| PENDING_DELETION | Không | Không | Mặc định không; xử lý phụ thuộc trước khi lập lịch hủy | Chỉ public key/chứng cứ còn được chính sách cho phép |
| DESTROYED | Không | Không | Không, nếu private/symmetric material đã hủy | Public key/chứng cứ lịch sử có thể vẫn được lưu |

**Điểm đặc biệt:** Verify chữ ký số có thể thực hiện bằng **public key**, nên việc private signing key đã bị disable/hủy **không làm phương trình chữ ký cũ mất đúng**. Quyết định tin chữ ký cần thêm chứng chỉ, trạng thái thu hồi, timestamp tin cậy, mục đích và quy định lưu giữ.

Với **DEK/KEK**, giải mã dữ liệu quá khứ lại cần vật liệu khóa hoặc khả năng unwrap. Hủy DEK/KEK khi còn bản mã phụ thuộc có thể khiến dữ liệu không thể phục hồi.

### 6.1. Originator-use và recipient-use period

Có thể phân biệt hai khoảng sử dụng:

- **Originator-use period:** thời gian được phép tạo bảo vệ mật mã mới, ví dụ **Encrypt, Sign hoặc Wrap**.
- **Recipient-use period:** thời gian được phép xử lý dữ liệu đã được bảo vệ trước đó, ví dụ **Decrypt, Unwrap hoặc Verify** theo chính sách.

Trong mô hình trên, **ACTIVE** thường bao gồm originator-use. **RETIRED** có thể tiếp tục recipient-use, nhưng điều này phải được áp dụng riêng cho mỗi thuật toán, đối tượng và rủi ro. Không suy rằng trạng thái RETIRED có nghĩa mọi thao tác đều hợp lệ.

## 7. Quản lý trạng thái theo từng phiên bản vật liệu khóa

Giả sử alias **payments-kek** từng tham chiếu KEK v2, sau đó được chuyển sang KEK v3.

~~~text
Alias: payments-kek
  |
  +--> v2: RETIRED (chỉ unwrap encrypted DEK lịch sử có quyền)
  |
  +--> v3: ACTIVE  (wrap DEK mới)
~~~

**Alias là tham chiếu logic, không phải bằng chứng đã thay key material.** Nếu chỉ trỏ alias sang một ID mới nhưng cả hai đối tượng vẫn chứa cùng vật liệu khóa, tổ chức chưa thực sự giảm rủi ro khi khóa cũ bị lộ.

Để tránh sai lệch:

1. Quản lý **materialVersion** độc lập với alias.
2. Ghi key reference và version phù hợp cạnh ciphertext, encrypted DEK hoặc chữ ký.
3. Dùng **version cụ thể** khi kiểm tra phụ thuộc và khi điều tra sự cố.
4. Tách trạng thái **version cũ** khỏi trạng thái **version mới**.
5. Kiểm tra chính sách cả ở **alias resolution** lẫn quyền thực thi thực tế trong KMS.

### 7.1. Trạng thái logic khác trạng thái của một phiên bản

Một alias có thể “ACTIVE” vì đã có v3 sẵn sàng, trong khi v2 đang RETIRED hoặc REVOKED. Không nên lưu một trường duy nhất trên alias rồi cho rằng nó mô tả tất cả material versions.

Một bản ghi minh họa:

~~~yaml
# Dữ liệu minh họa; không phải schema của nhà cung cấp KMS
keyId: payments-kek
materialVersion: v3
algorithm: AES-256-KEY-WRAP
owner: payment-platform
tenantScope: production
purpose: wrap-data-keys
lifecycleState: ACTIVE
kmsKeyRef: provider/key/material-v3
stateRevision: 17
policyVersion: 4
createdAt: "2026-11-20T09:00:00Z"
activatedAt: "2026-11-22T10:00:00Z"
~~~

**stateRevision** hỗ trợ kiểm soát cạnh tranh; **policyVersion** cho biết chính sách nào đã được áp dụng khi trạng thái thay đổi.

## 8. Kích hoạt khóa (PRE_ACTIVE → ACTIVE)

**Kích hoạt** là quyết định cho phép khóa thực hiện các thao tác sản xuất được phê duyệt. Không nên để GenerateKey mặc nhiên kích hoạt và cấp quyền rộng cho mọi workload nếu kiến trúc yêu cầu xét duyệt riêng.

Luồng tham khảo:

~~~mermaid
sequenceDiagram
    participant O as Operator / Workflow
    participant R as Key Registry
    participant K as KMS/HSM
    participant C as Consumer / Verifier
    O->>R: Request activate(key v3, expectedRevision)
    R->>R: Kiểm tra IAM, policy, owner, readiness
    R->>K: Kiểm tra key material/usage/trạng thái
    K-->>R: Key ready
    R->>C: Kiểm tra phân phối reference/public key
    C-->>R: Consumer ready
    R->>R: Commit transition theo revision
    R-->>O: ACTIVE + audit event
~~~

Trước khi chuyển ACTIVE, kiểm tra:

- Key đúng thuật toán, độ dài/curve, origin và **key usage**.
- Secret không bị lộ qua quy trình sinh/import.
- Quyền **Encrypt, Sign, Wrap...** đã được giới hạn theo workload/môi trường.
- Nếu là signing key, public key/chứng chỉ có nguồn tin cậy và verifier đã sẵn sàng.
- Nếu là KEK, các ứng dụng và context cần wrap/unwrap đã được kiểm thử.
- Audit và giám sát ở mức hệ thống đã hoạt động.

**Không phải mọi key mới đều cần được công bố cho verifier.** Public-key provisioning là guard của khóa ký/asymmetric tương ứng; DEK đối xứng không có public verification key.

## 9. Rotation có kiểm soát: ACTIVE → RETIRED

**Rotation không chỉ là thay giá trị status mà là quá trình chuyển traffic hoặc nhiệm vụ sang vật liệu khóa mới.**

~~~mermaid
flowchart TD
    A["Khóa v1 ACTIVE"] --> B["Generate v2 PRE_ACTIVE"]
    B --> C["Cấp quyền + kiểm tra provider và consumer"]
    C --> D["Activate v2"]
    D --> E["Chuyển writer/signer sang v2"]
    E --> F{"Không còn thao tác tạo mới bằng v1?"}
    F -->|Chưa| G["Theo dõi và xử lý workload cũ"]
    G --> F
    F -->|Rồi| H["Retire v1"]
    H --> I["Đọc/verify dữ liệu lịch sử theo policy"]
    I --> J["Kiểm kê để hủy khi đủ điều kiện"]
~~~

Các bước quan trọng:

1. **Sinh vật liệu mới thật sự** và gắn version mới.
2. Chuẩn bị ứng dụng nhận version mới, bao gồm hệ thống xác minh chữ ký và reader dữ liệu cũ.
3. Chuyển **new Encrypt/Sign/Wrap** sang key mới qua cấu hình có kiểm soát.
4. Kiểm tra không còn producer dùng key cũ, bao gồm worker chưa cập nhật, batch job, queue retry và các vùng triển khai.
5. Chuyển khóa cũ sang **RETIRED** để chặn thao tác tạo mới.
6. Giữ khả năng xử lý dữ liệu/chữ ký cũ theo cryptoperiod và retention policy.
7. Kiểm tra điều kiện hủy sau này.

### 9.1. Rotation KEK khác rotation DEK

- Với **KEK**, có thể **rewrap encrypted DEK** dưới KEK mới mà không cần mã hóa lại plaintext dữ liệu nếu DEK chưa bị lộ và thiết kế hỗ trợ.
- Với **DEK**, việc thay key material thường đòi hỏi **mã hóa lại dữ liệu** bằng DEK mới.
- Với **signing key**, cần phân phối public key/chứng chỉ mới; chữ ký lịch sử có thể tiếp tục được kiểm tra qua bằng chứng cũ theo chính sách.

Nếu DEK đã bị lộ, chỉ rewrap không khắc phục sự cố: đối thủ có thể giữ bản sao plaintext DEK cũ.

### 9.2. Không dùng retire để xử lý một compromise đang hoạt động

**RETIRED** là trạng thái phù hợp với chuyển đổi có kế hoạch khi vật liệu còn được tin trong phạm vi lịch sử. Khi khóa bị đánh cắp hoặc nghi lộ, cần **SUSPENDED/REVOKED** và quy trình sự cố, không đơn giản RETIRED nhưng vẫn để mọi ứng dụng decrypt/unwrap thoải mái.

## 10. SUSPENDED: ngừng tạm thời và khôi phục an toàn

Trạng thái **SUSPENDED** giúp chặn nguy cơ ngay khi chưa đủ dữ kiện kết luận khóa đã bị lộ.

Ví dụ:

- Giám sát phát hiện lượng **Decrypt/Unwrap** bất thường từ workload.
- HSM báo lỗi cấu hình hoặc nguy cơ thao tác khóa không đúng.
- Một principal có quyền Sign bị nghi chiếm quyền.
- Có sự cố vận hành cần tạm dừng trong khi đánh giá.

**Luồng SUSPEND:**

1. Ghi nhận incident/operational reason.
2. Chặn các thao tác nhạy cảm ở **KMS/HSM/policy**, không chỉ ẩn nút trên UI.
3. Đánh dấu trạng thái registry và phiên bản, ghi audit.
4. Thông báo đến producer/consumer theo cách không rò bí mật.
5. Theo dõi tình trạng propagating của policy, cache và các phiên đang hoạt động.

**Luồng RESUME:**

1. Chứng minh nguyên nhân đã được xử lý, không có compromise chưa giải quyết.
2. Kiểm tra key material, provider, IAM và hoạt động bất thường.
3. Có phê duyệt theo quy trình; yêu cầu người phê duyệt độc lập nếu mức rủi ro cần.
4. Khôi phục quyền tối thiểu và xác minh ở cả registry lẫn KMS.
5. Audit việc khôi phục, bằng chứng và thay đổi policy.

**Không cho phép RESUME nếu khóa đã REVOKED vì bị lộ** trong state machine tham khảo. Sinh khóa mới là cách an toàn hơn cho những trường hợp không thể tin vật liệu cũ.

## 11. REVOKED: thu hồi quyền sử dụng và niềm tin

**Revocation** là quyết định **rút quyền sử dụng hoặc rút niềm tin** đối với khóa. Nó có thể xảy ra khi private signing key bị lộ, KEK bị đánh cắp, IAM bị lạm dụng hoặc thuật toán/cấu hình bị cấm.

### 11.1. Cần phân biệt revoke, disable và delete

| Hành động | Đối tượng chịu tác động | Có đủ để ngăn đối thủ không? |
|---|---|---|
| **Disable key trong KMS** | Những lời gọi qua API KMS đó | Không nếu đối thủ đã có bản sao plaintext key |
| **Revoke certificate/trust** | Những verifier thực sự cập nhật và thực thi thông tin thu hồi | Không ngay lập tức nếu cache/client ngoại tuyến chưa cập nhật |
| **Revoke IAM principal** | Quyền gọi của danh tính trong miền IAM có hiệu lực | Không xóa key material hoặc dữ liệu đã bị lấy |
| **Destroy key material** | Bản sao nằm trong phạm vi hủy của KMS/HSM | Không chắc xóa được bản sao đã xuất/lộ từ trước |
| **Invalidate token/session** | Phiên và credential trong hệ thống hỗ trợ revoke | Phụ thuộc cơ chế kiểm tra tại từng dịch vụ |

Vì vậy, một trạng thái **REVOKED trong registry** chưa đồng nghĩa sự cố đã được khống chế hoàn toàn. Phải kiểm tra **hiệu lực thực tế** của việc chặn API và cập nhật niềm tin.

### 11.2. Quy trình thu hồi khẩn cấp

~~~mermaid
flowchart TD
    I["Phát hiện sự cố hoặc compromise"] --> S["Block Sign/Encrypt/Decrypt theo phạm vi"]
    S --> R["Đánh dấu REVOKED + incident ID"]
    R --> N["Sinh khóa thay thế từ nguồn tin cậy"]
    N --> T["Cập nhật public trust/KEK/DEK và client"]
    T --> V["Kiểm tra mọi consumer, cache, khu vực"]
    V --> D["Điều tra dữ liệu/chữ ký/phiên bị ảnh hưởng"]
    D --> E["Quyết định retention, recovery và destruction"]
~~~

**Chữ ký cũ** có thể vẫn verify đúng về mặt toán học. Việc tiếp tục chấp nhận chúng cần kiểm tra **trusted timestamp, trạng thái chứng chỉ tại thời điểm ký, bằng chứng phát hành và yêu cầu pháp lý/nghiệp vụ**. Không được tự động tuyên bố mọi chữ ký lịch sử đều giả hoặc mặc nhiên đáng tin.

**Dữ liệu mã hóa bằng DEK bị lộ** có thể đã bị sao chép và giải mã. Sinh DEK mới giúp bảo vệ dữ liệu về sau, nhưng **không lấy lại bí mật đã mất**.

## 12. PENDING_DELETION và DESTROYED: hủy có điều kiện

Hủy key material có thể **không thể đảo ngược** và làm mất dữ liệu hợp lệ. Do đó chuyển sang **PENDING_DELETION** phải dựa trên kiểm tra phụ thuộc, retention và quyền phê duyệt.

### 12.1. Trước khi lên lịch hủy

Với **KEK**:

- Đã tìm được những encrypted DEK nào còn phụ thuộc?
- Đã rewrap hoặc giải quyết đường phục hồi của chúng chưa?
- Có dữ liệu backup/archival ở vùng khác còn cần KEK không?
- Có kế hoạch khôi phục disaster recovery không?

Với **DEK**:

- Dữ liệu dưới DEK đã được xóa hợp lệ, mã hóa lại hoặc đến hạn crypto-shredding chưa?
- Có nghĩa vụ lưu giữ dữ liệu/điều tra/backup chưa hết không?

Với **private signing key**:

- Đã dừng việc ký mới, thu hồi quyền Sign và chuyển sang khóa mới chưa?
- Có cần giữ public key, chứng chỉ, CRL/OCSP/timestamp hoặc chứng cứ khác để xác minh tài liệu cũ không?
- Backup của private key có cần được xử lý theo chính sách không?

**Crypto-shredding** là cơ chế làm dữ liệu mã hóa không thể giải mã bằng việc hủy key material duy nhất còn cho phép decrypt, nhưng chỉ hiệu quả nếu **không có bản sao khóa/bản rõ hoặc recovery path** ngoài phạm vi hủy.

### 12.2. Khi nào được đánh dấu DESTROYED?

Chỉ sau khi có bằng chứng thích hợp:

1. KMS/HSM hoặc cơ chế bảo vệ xác nhận **hủy key material** ở những nơi thuộc phạm vi quản lý.
2. Quá trình xử lý backup/copy được ghi nhận và đáp ứng chính sách.
3. Registry ghi thời gian, đối tượng, version, quyết định và bằng chứng hủy.
4. Không còn ứng dụng có thể thực hiện phép toán cần vật liệu bị hủy qua những đường thông thường.
5. Hệ thống điều tra/phục hồi biết những hạn chế không thể xác minh, ví dụ **bản sao từng bị đánh cắp không thể được “hủy từ xa”**.

Không được gọi thao tác ScheduleDelete rồi **đánh dấu DESTROYED ngay lập tức**. Trong nhiều dịch vụ, **lên lịch xóa** và **xóa thực tế** là hai thời điểm khác nhau. Một số nền tảng còn hỗ trợ hủy lịch, nhưng chỉ được làm theo policy và mô hình trạng thái đã kiểm chứng.

## 13. Đồng bộ state machine với KMS/HSM

Hệ thống thực tế thường có hai lớp kiểm soát:

- **Control plane:** registry trạng thái, workflow phê duyệt, IAM, incident management, audit.
- **Data plane:** KMS/HSM hoặc crypto provider thực sự cho phép hay từ chối Encrypt, Decrypt, Sign, Unwrap.

Nếu registry ghi REVOKED nhưng workload vẫn có credential gọi KMS Decrypt trực tiếp, thu hồi chưa có hiệu lực. Ngược lại, KMS đã disable khóa nhưng registry vẫn báo ACTIVE có thể làm ứng dụng lỗi và che khuất sự cố.

~~~mermaid
flowchart TD
    U["Yêu cầu transition"] --> W["IAM, guards và approval"]
    W --> I["Transition intent / operation ID"]
    I --> P["Áp policy hoặc đổi trạng thái tại KMS/HSM"]
    P --> O["Đọc observed provider state"]
    O --> C{"Hậu điều kiện đạt?"}
    C -->|Có| R["Finalize registry + audit"]
    C -->|Chưa| E["Fail-safe, retry và reconciliation"]
    E --> O
    R --> N["Thông báo consumer / verifier"]
    N --> V["Xác nhận propagation"]
~~~

### 13.1. Desired state và observed state

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| **desiredLifecycleState** | REVOKED | Trạng thái mà policy yêu cầu |
| **observedProviderState** | DISABLED | Điều KMS/HSM thực tế báo |
| **transitionPhase** | APPLYING, VERIFYING, COMPLETED, FAILED | Tiến độ workflow |
| **transitionId** | op-20261128-001 | Định danh idempotency |
| **stateRevision** | 27 | Phiên bản dùng chống ghi đè đồng thời |
| **lastReconciledAt** | 2026-11-28T02:10:00Z | Lần cuối đọc provider |
| **trustPropagationState** | IN_PROGRESS | Tiến độ cập nhật verifier, nếu có |

Không được tự gán observedProviderState theo desiredLifecycleState. Giá trị observed phải lấy từ API/bằng chứng đáng tin, không phải giả định.

### 13.2. Provider state không ánh xạ một–một

Một ánh xạ *tham khảo*:

~~~text
Business lifecycle      KMS/provider
-----------------------------------------------------
PRE_ACTIVE              Key tồn tại, chưa cấp usage
ACTIVE                  Enabled + quyền tối thiểu
SUSPENDED               Disabled hoặc deny policy
RETIRED                 Deny Encrypt/Sign mới, có thể giữ Decrypt cũ
REVOKED                 Deny + thu hồi trust ở verifier
PENDING_DELETION        Schedule deletion và deny usage
DESTROYED               Có xác nhận hủy key material
~~~

Đây không phải cam kết mọi nhà cung cấp đều hỗ trợ các policy nói trên. Nếu KMS không thể tách quyền Encrypt khỏi Decrypt, kiến trúc cần thay cách phân chia khóa, áp lớp thực thi khác hoặc dùng provider phù hợp.

### 13.3. Fail-safe khi hai lớp chưa nhất quán

Khi có sự cố, phải ưu tiên **chặn sử dụng không an toàn**. Nếu đang chuyển ACTIVE sang REVOKED, workflow nên ngăn thao tác tại các cổng và ở IAM/KMS sớm nhất có thể, rồi xác nhận mọi đường gọi quan trọng đã bị từ chối.

Nếu PRE_ACTIVE đang kích hoạt nhưng trust store/consumer chưa sẵn sàng, **không đánh dấu ACTIVE hoàn tất** chỉ vì KMS báo enabled. Cần giữ operation đang xử lý và reconcile.

## 14. Concurrency, idempotency và cập nhật phân tán

Nhiều operator và worker có thể cùng tác động vào một phiên bản khóa:

- Operator A muốn ACTIVE → RETIRED theo kế hoạch.
- Incident responder yêu cầu ACTIVE → REVOKED.
- Worker cũ retry một lệnh ACTIVATE từ trạng thái đã lỗi thời.
- Consumer còn cache alias hoặc policy cũ.

Nếu không kiểm soát, một lệnh rotation stale có thể ghi đè REVOKED và khiến khóa nguy hiểm được dùng lại.

### 14.1. Optimistic locking với stateRevision

Mỗi transition cần khai báo **expectedRevision**. Chỉ cập nhật khi state và revision khớp:

~~~sql
-- SQL minh họa; cú pháp tùy cơ sở dữ liệu.
UPDATE key_registry
SET lifecycle_state = :target_state,
    state_revision = state_revision + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE key_id = :key_id
  AND material_version = :material_version
  AND lifecycle_state = :expected_state
  AND state_revision = :expected_revision;
~~~

Nếu số dòng cập nhật bằng **0**, request phải **đọc lại và đánh giá lại toàn bộ guard**, không bỏ điều kiện WHERE để ghi đè bằng mọi giá.

### 14.2. Idempotency

Mỗi yêu cầu nên có **operationId/idempotencyKey** ổn định. Retry cùng ID phải trả về kết quả đã ghi hoặc tiếp tục thao tác dở dang, không tự lên lịch hủy hai lần hay tạo phiên bản khóa trùng lặp.

~~~json
{
  "operationId": "op-key-20261128-001",
  "keyId": "payments-kek",
  "materialVersion": "v3",
  "fromState": "ACTIVE",
  "toState": "REVOKED",
  "expectedRevision": 27,
  "reasonCode": "SUSPECTED_COMPROMISE",
  "incidentId": "SEC-241"
}
~~~

**Idempotency không tự biến nhiều hệ thống thành một giao dịch exactly-once.** Retry một provider API phải có cơ chế đọc trạng thái, kiểm tra hậu điều kiện hoặc khóa theo operationId tùy đặc tính thực tế.

### 14.3. KMS và database thường không chung ACID transaction

Một lời gọi DisableKey tại KMS và UPDATE tại DB không tự atomic. Cách xử lý tham khảo:

1. Ghi **transition intent** có operation ID, revision và phase ở DB.
2. Chặn các usage nguy hiểm ở cổng thực thi khi transition giảm quyền.
3. Gọi KMS/HSM API theo quy tắc retry an toàn.
4. Đọc lại provider để xác nhận observed state.
5. Commit/finalize trạng thái và ghi **outbox event** trong một transaction local khi khả thi.
6. Reconciler tìm operation tồn tại quá lâu ở APPLYING/VERIFYING.
7. Khi gặp xung đột với incident REVOKED, không cho phép workflow cũ vô tình khôi phục usage.

### 14.4. Sự kiện stale và fencing

Message bus có thể gửi lại hoặc thay thứ tự event. Consumer phải so sánh **stateRevision/materialVersion** và bỏ qua event cũ.

Khi nhiều worker cùng điều phối, có thể dùng **fencing token** hoặc cơ chế lease đáng tin để ngăn một worker đã mất quyền tiếp tục áp dụng thao tác. Ví dụ worker ACTIVATE revision 10 không thể kích hoạt lại khóa sau khi incident đã REVOKED ở revision 11.

## 15. IAM, separation of duties và kiểm soát break-glass

| Hành động | Application | Key operator | Security approver | Incident responder | Auditor |
|---|---|---|---|---|---|
| Request Generate/Activate | Có thể yêu cầu | Có thể làm theo policy | Có thể duyệt | Theo quyền | Chỉ xem |
| Activate | Không tự ý | Theo phê duyệt | Duyệt khi cần | Khi có thẩm quyền | Chỉ xem |
| Suspend khẩn cấp | Báo sự cố | Theo quyền | Theo quyền | Có thể break-glass | Chỉ xem |
| Resume | Không tự ý | Sau tái đánh giá | Phê duyệt nếu cần | Đề xuất | Chỉ xem |
| Retire | Theo workflow | Thực hiện | Duyệt nếu cần | Có thể đề xuất | Chỉ xem |
| Revoke | Không tự ý | Theo policy | Duyệt/hậu kiểm | Có thể chặn khẩn cấp | Chỉ xem |
| Schedule destruction | Không tự ý | Sau kiểm kê | Phê duyệt độc lập | Có thể yêu cầu | Chỉ xem |
| Confirm destroyed | Không tự gán | Dựa vào provider | Xác nhận theo policy | Theo vai trò | Kiểm tra bằng chứng |

**Separation of duties** giúp tránh một cá nhân vừa tạo khóa, tự phê duyệt, hủy khóa và xóa audit. Với hành động **không thể khôi phục** có thể yêu cầu dual control.

Nhưng **ngừng sử dụng một khóa đang bị lộ** không nên bị trì hoãn bởi thủ tục hủy thông thường. **Break-glass** có thể chặn tức thì theo quyền giới hạn, với danh tính mạnh, ghi audit và bắt buộc hậu kiểm.

Kiểm tra quyền cần có ở các tầng:

- **IAM/KMS policy** kiểm soát caller có thể thực hiện thao tác mật mã nào.
- **Workflow service** kiểm tra người yêu cầu, người duyệt và guard.
- **Business authorization** kiểm tra tenant, dữ liệu và nhiệm vụ được phép.
- **Verifier policy** kiểm tra trust của public key, chứng chỉ và thời điểm chữ ký.

KMS có thể cho một workload quyền Sign, nhưng không tự biết chứng từ chưa qua phê duyệt nghiệp vụ. Quyết định ký phải được kiểm soát ở tầng ứng dụng.

## 16. Audit event và bằng chứng chuyển trạng thái

Một transition cần tạo được lịch sử truy vết rõ ràng:

~~~json
{
  "eventType": "KEY_LIFECYCLE_TRANSITION",
  "operationId": "op-key-20261128-001",
  "keyId": "payments-kek",
  "materialVersion": "v3",
  "fromState": "ACTIVE",
  "toState": "REVOKED",
  "actor": "security-incident-workflow",
  "approverRefs": ["approval-789"],
  "reasonCode": "SUSPECTED_COMPROMISE",
  "incidentId": "SEC-241",
  "policyVersion": 4,
  "expectedRevision": 27,
  "resultRevision": 28,
  "requestedAt": "2026-11-28T02:01:00Z",
  "effectiveAt": "2026-11-28T02:01:20Z",
  "providerConfirmationRef": "kms-event-ref-123",
  "result": "COMPLETED"
}
~~~

Đây là **format minh họa**, không phải schema của mọi KMS.

Cần trả lời được: **ai** yêu cầu và duyệt, **khóa/phiên bản nào**, **vì sao**, **guard nào**, **provider làm gì**, **thời điểm thực sự có hiệu lực**, **consumer nào đã nhận thông tin**, **retry hoặc lỗi nào đã xảy ra**.

Phải phân biệt thời điểm **REQUESTED, registry commit, provider confirmed, verifier propagated**. Một API trả thành công cho việc đặt lịch không chứng minh trạng thái đã có hiệu lực ở mọi nơi.

**Không ghi private key, plaintext DEK, HMAC secret, ECDSA nonce k, seed, token còn hiệu lực hoặc dữ liệu nhạy cảm vào log.** Audit chỉ cần metadata, correlation IDs, actor, policy, kết quả và references. Dữ liệu audit phải được bảo vệ chống thay đổi hoặc xóa trái quyền.

## 17. Java 17: kiểm tra state machine và transition guards

Đoạn mã Java 17 dưới đây chỉ triển khai **logic quyết định**. Nó chưa gọi KMS, chưa truy cập DB và chưa tự xác thực bằng chứng phê duyệt; đây là phần lõi minh họa cho workflow chứ **không phải hệ thống quản lý khóa production**.

~~~java
import java.util.Set;

public final class KeyLifecycleStateMachine {
    public enum State {
        PRE_ACTIVE, ACTIVE, SUSPENDED, RETIRED,
        REVOKED, PENDING_DELETION, DESTROYED
    }

    public record KeyRecord(
            String keyId, String materialVersion,
            State state, long revision) {}

    public record Command(
            State target, long expectedRevision,
            String reason, String operationId) {}

    // Evidence phải được lấy từ IAM/workflow/inventory/provider
    // đã xác thực, KHÔNG tin boolean do client tự gửi.
    public record Evidence(
            boolean authorized,
            boolean readyForActivation,
            boolean incidentResolved,
            boolean replacementReady,
            boolean dependenciesCleared,
            boolean retentionSatisfied,
            boolean destructiveApprovalGranted,
            boolean kmsDestructionConfirmed) {}

    private static boolean allowedEdge(State from, State to) {
        return switch (from) {
            case PRE_ACTIVE -> Set.of(
                State.ACTIVE, State.PENDING_DELETION).contains(to);
            case ACTIVE -> Set.of(
                State.SUSPENDED, State.RETIRED, State.REVOKED).contains(to);
            case SUSPENDED -> Set.of(
                State.ACTIVE, State.RETIRED, State.REVOKED).contains(to);
            case RETIRED -> Set.of(
                State.REVOKED, State.PENDING_DELETION).contains(to);
            case REVOKED -> to == State.PENDING_DELETION;
            case PENDING_DELETION -> to == State.DESTROYED;
            case DESTROYED -> false;
        };
    }

    public static KeyRecord decide(
            KeyRecord current, Command command, Evidence evidence) {
        if (!evidence.authorized()) {
            throw new SecurityException("Unauthorized");
        }
        if (command.reason() == null || command.reason().isBlank()
                || command.operationId() == null
                || command.operationId().isBlank()) {
            throw new IllegalArgumentException(
                "Reason and operationId required");
        }
        if (current.revision() != command.expectedRevision()) {
            throw new IllegalStateException("Stale revision");
        }
        if (!allowedEdge(current.state(), command.target())) {
            throw new IllegalStateException(
                "Illegal transition: " + current.state()
                    + " -> " + command.target());
        }

        switch (command.target()) {
            case ACTIVE -> {
                if (!evidence.readyForActivation()
                        || (current.state() == State.SUSPENDED
                        && !evidence.incidentResolved())) {
                    throw new IllegalStateException(
                        "Readiness/risk assessment incomplete");
                }
            }
            case RETIRED -> {
                if (!evidence.replacementReady()) {
                    throw new IllegalStateException(
                        "Replacement not ready");
                }
            }
            case PENDING_DELETION -> {
                if (!evidence.dependenciesCleared()
                        || !evidence.retentionSatisfied()
                        || !evidence.destructiveApprovalGranted()) {
                    throw new IllegalStateException(
                        "Destruction prerequisites missing");
                }
            }
            case DESTROYED -> {
                if (!evidence.kmsDestructionConfirmed()) {
                    throw new IllegalStateException(
                        "Provider destruction not confirmed");
                }
            }
            case SUSPENDED, REVOKED -> {
                // Incident/authorization policy ở lớp workflow.
            }
            case PRE_ACTIVE -> throw new IllegalStateException(
                "Cannot return to PRE_ACTIVE");
        }

        // Trả quyết định dự kiến; chưa cập nhật DB/KMS.
        return new KeyRecord(
            current.keyId(), current.materialVersion(),
            command.target(), current.revision() + 1);
    }

    public static void main(String[] args) {
        KeyRecord key = new KeyRecord(
            "payments-kek", "v3", State.ACTIVE, 7);
        Command retire = new Command(
            State.RETIRED, 7, "Planned rotation", "op-001");
        Evidence verified = new Evidence(
            true,   // authorized
            false,  // activation readiness: not applicable
            false,  // incident resolved: not applicable
            true,   // replacement ready
            false, false, false, false);

        KeyRecord result = decide(key, retire, verified);
        if (result.state() != State.RETIRED
                || result.revision() != 8) {
            throw new IllegalStateException("Transition failed");
        }
        System.out.println("Transition policy OK");
    }
}
~~~

**Điểm cần rút ra:** enum giới hạn trạng thái; allowedEdge hạn chế những đường chuyển cho phép; revision phát hiện request stale; guards hạn chế kích hoạt và hủy; DESTROYED không có cạnh đi ra; REVOKED không trở lại ACTIVE trong mô hình này.

**Để đưa vào sản xuất**, service phải tự kiểm tra evidence đáng tin, commit CAS trong DB, thực hiện KMS API với readback, điều phối outbox/idempotency/reconciliation, áp IAM tại đường thực thi và ghi audit. Nếu có chuyển sang REVOKED khẩn cấp, phải chặn quyền nhạy cảm **thực sự**, không chờ một boolean trạng thái.

## 18. Thiết kế API chuyển trạng thái và transition workflow

Một API tham khảo cho phép yêu cầu chuyển trạng thái theo **key version** và revision:

~~~http
POST /key-versions/payments-kek/v3/transitions
Idempotency-Key: op-20261128-001
Authorization: Bearer <access-token>

{
  "targetState": "REVOKED",
  "expectedRevision": 27,
  "reasonCode": "SUSPECTED_COMPROMISE",
  "incidentId": "SEC-241"
}
~~~

Đây là **hợp đồng minh họa**, không phải API chuẩn chung. Client không được tự đặt một flag approved=true để bỏ qua IAM/approval workflow.

Với thao tác bất đồng bộ, server có thể trả:

~~~json
{
  "operationId": "op-20261128-001",
  "keyId": "payments-kek",
  "materialVersion": "v3",
  "desiredState": "REVOKED",
  "transitionPhase": "APPLYING",
  "statusUrl": "/key-transition-operations/op-20261128-001"
}
~~~

Phản hồi nhận request **không có nghĩa provider đã hoàn thành**. Client và hệ thống giám sát phải theo dõi operation tới hậu điều kiện có thể kiểm chứng.

### 18.1. Các phase của thao tác

- **REQUESTED:** client gửi yêu cầu, chưa có quyết định.
- **VALIDATED:** hệ thống xác minh quyền, guard và phê duyệt.
- **APPLYING:** áp thay đổi ở KMS/HSM/IAM/trust.
- **VERIFYING:** đọc observed state và kiểm tra consumer cần thiết.
- **COMPLETED:** đạt hậu điều kiện đã quy định.
- **FAILED / REQUIRES_ATTENTION:** chưa đạt; bảo toàn kiểm soát fail-safe, cảnh báo, xử lý bằng workflow.

Đây là **operation phases**, không phải những trạng thái key material mới. Trộn APPLYING vào trường lifecycleState có thể khiến ứng dụng hiểu nhầm khóa đang có quyền dùng.

### 18.2. Outbox event cho consumer

~~~json
{
  "eventType": "KEY_VERSION_REVOKED",
  "keyId": "payments-kek",
  "materialVersion": "v3",
  "stateRevision": 28,
  "operationId": "op-20261128-001",
  "effectiveAt": "2026-11-28T02:01:20Z"
}
~~~

Consumer xử lý event **idempotent**, bỏ qua revision cũ, kiểm tra version phù hợp và áp chính sách tại nơi thực thi. Với compromise, event bus không thay thế thao tác chặn IAM/KMS ngay lập tức.

## 19. Case study: nền tảng thanh toán đa tenant

Hệ thống Java quản lý ba nhóm khóa:

- **AES-GCM DEK** mã hóa từng hồ sơ, được bọc dưới KEK.
- **KEK theo tenant** nằm trong KMS, bảo vệ encrypted DEK.
- **Signing key cho chứng từ** nằm trong HSM; các đối tác xác minh bằng public key/chứng chỉ được tin.

### 19.1. Tình huống A — Rotation KEK theo kế hoạch

KEK của tenant-A v2 đang ACTIVE, cần chuyển sang v3.

1. Generate v3, gắn PRE_ACTIVE, kiểm tra thuật toán, tenant scope và key usage.
2. Thiết lập IAM/audit cho v3, kiểm tra KMS readiness.
3. Kích hoạt v3; chuyển toàn bộ **new Wrap** của ứng dụng sang v3.
4. Kiểm kê encrypted DEK cũ còn phụ thuộc v2, lên kế hoạch **rewrap** thích hợp.
5. Chặn mọi thao tác **Wrap mới** bằng v2, kể cả job offline và retry.
6. Chuyển v2 sang RETIRED; nếu cần, chỉ Unwrap lịch sử theo quyền và thời hạn.
7. Sau khi xác nhận dữ liệu, backup và restore không còn phụ thuộc, mới xem xét PENDING_DELETION và hủy.

**Nguy cơ:** registry ghi RETIRED nhưng một batch job cũ vẫn Wrap dưới v2. Phải kiểm tra policy thực tế ở provider và theo dõi stale producers.

### 19.2. Tình huống B — Signing key bị nghi lộ

Một workload có quyền Sign bị chiếm quyền.

1. Cô lập principal, **SUSPEND** lời gọi Sign ở KMS/HSM và ghi incident.
2. Phân biệt **lạm dụng API Sign** với **private key bị export** để xác định phạm vi.
3. Nếu cần, REVOKE phiên bản cũ, sinh key version mới và kiểm tra quyền.
4. Phát hành public key/chứng chỉ mới, cập nhật mọi verifier, JWKS/trust store/cache.
5. Điều tra chứng từ/token có chữ ký trong khoảng nghi ngờ dựa trên audit và bằng chứng thời gian.
6. Retain public key/chứng cứ cần thiết; quyết định lúc hủy private key theo yêu cầu pháp lý/vận hành.

**Nguy cơ:** HSM có thể đã disable key nhưng một client chưa cập nhật vẫn chấp nhận chữ ký do bản sao private key bị lộ tạo bên ngoài. Phải phối hợp **technical revocation và trust revocation**.

### 19.3. Tình huống C — Hủy khóa để xóa dữ liệu

Tenant-B yêu cầu xóa dữ liệu, hệ thống dự định hủy KEK tenant-B để thực hiện crypto-shredding.

Trước khi lên lịch hủy, cần chứng minh KEK đó **không còn bảo vệ dữ liệu của tenant khác**, không còn dữ liệu có nghĩa vụ lưu giữ và không còn recovery key hoặc bản sao DEK nằm ngoài phạm vi. Nếu KEK được dùng chung, hủy nó có thể làm mất dữ liệu hợp lệ của bên khác. Có thể phải hủy từng DEK hoặc chuyển phụ thuộc trước.

**Bài học:** điều kiện dependenciesCleared là một bằng chứng cần thu thập từ hệ thống thực, không phải checkbox tự khai báo.

## 20. Ma trận kiểm thử chuyển trạng thái

| Tình huống kiểm thử | Kết quả kỳ vọng |
|---|---|
| PRE_ACTIVE → ACTIVE đủ điều kiện | Thành công, revision tăng và có audit |
| PRE_ACTIVE → ACTIVE thiếu readiness/trust | Từ chối hoặc chưa finalize |
| ACTIVE → RETIRED khi vẫn còn producer dùng khóa cũ | Chưa hoàn tất hoặc báo vi phạm guard |
| ACTIVE → SUSPENDED do incident | Chặn usage nhạy cảm theo policy |
| SUSPENDED → ACTIVE khi chưa xử lý nguyên nhân | Từ chối |
| REVOKED → ACTIVE | Từ chối theo state machine tham khảo |
| DESTROYED → bất kỳ trạng thái nào | Từ chối |
| PENDING_DELETION → DESTROYED trước khi KMS xác nhận | Từ chối |
| Schedule deletion khi còn DEK phụ thuộc | Từ chối hoặc yêu cầu migration được duyệt |
| Hai request dùng chung expectedRevision | Chỉ một commit, request khác phải đánh giá lại |
| Retry một operationId sau timeout | Không lặp thao tác không an toàn |
| Event revision cũ đến sau event mới | Consumer bỏ qua sự kiện cũ |
| KMS disable thành công nhưng DB update lỗi | Reconciliation phát hiện và bảo đảm fail-safe |
| DB ghi REVOKED nhưng IAM còn cho Decrypt | Test phát hiện lỗ hổng ở đường thực thi |
| Rotate KEK và rewrap DEK | Dữ liệu cũ vẫn giải mã được theo policy |
| Rotate signing key | Verifier chấp nhận khóa mới, xử lý lịch sử đúng |
| Certificate đã thu hồi nhưng cache chưa cập nhật | Phát hiện propagation chưa hoàn tất |
| KMS timeout khi kích hoạt | Không tự bypass provider; operation không COMPLETED |
| Break-glass revoke | Chặn kịp thời, có audit và hậu kiểm |
| Hủy khóa có backup/retention phụ thuộc | Chặn hoặc yêu cầu kiểm kê và phê duyệt |
| Event audit chuyển trạng thái | Đủ actor, key/version, revision, reason, kết quả; không có secret |

Kiểm thử phải bao gồm **multi-region, nhiều instance, restart/failover, queue retry, TTL cache, bản sao lưu và các sự kiện đến sai thứ tự**. Kiểm thử enum và guard đơn lẻ không chứng minh được toàn bộ workflow đã an toàn.

## 21. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ đổi trạng thái trong DB | Provider vẫn cho dùng key material | KMS/IAM enforcement và reconciliation |
| Gộp state của alias và mọi material versions | Khóa cũ REVOKED có thể bị che khuất | Theo dõi state theo key ID/version |
| REVOKED → ACTIVE bằng cập nhật thủ công | Tái kích hoạt khóa bị lộ | Deny theo state machine; sinh khóa mới |
| Không dùng expectedRevision | Race condition ghi đè kết quả khẩn cấp | CAS/optimistic locking |
| Retry thao tác hủy với operation ID mới | Nhiều workflow không nhất quán | Idempotency và transition log |
| Kết luận hoàn tất khi provider mới ACK | Chưa cập nhật trust/client/cache | Verify observed state và propagation |
| Tin approved=true do client gửi | Bỏ qua kiểm soát phê duyệt | Tra IAM, workflow và bằng chứng thực |
| Retire KEK khi reader còn phụ thuộc | Không decrypt được dữ liệu cũ | Originator/recipient-use policy rõ ràng |
| Destroy KEK trước khi rewrap | Mất khả năng unwrap DEK | Dependency inventory, thử restore |
| Xóa public key lịch sử ngay | Mất bằng chứng xác minh chữ ký cũ | Retain public key/certificate/timestamp theo policy |
| Chỉ disable signing key ở KMS | Bản sao private key ngoài KMS vẫn ký được | Revoke trust và cập nhật mọi verifier |
| Break-glass không có audit | Khó truy cứu lạm dụng quyền | Giới hạn quyền, audit, hậu kiểm |
| Cấp Delete/ChangePolicy cho service dùng khóa | Có thể xóa hoặc mở quyền trái phép | Least privilege, separation of duties |
| Log secret khi điều tra | Tạo sự cố rò khóa mới | Chỉ log metadata/bằng chứng an toàn |
| Workflow stale kích hoạt lại sau compromise | Rút lại vô ý quyết định REVOKED | Revision, fencing và ưu tiên incident |
| Đồng nhất scheduled deletion với destroyed | Báo sai trạng thái hủy thực tế | Chờ xác nhận provider và backup controls |

## 22. Câu hỏi tự kiểm tra

**Câu 1. Vì sao ACTIVE → RETIRED không chỉ là sửa status?**

**Trả lời:** Vì phải ngừng thao tác tạo mới dưới khóa cũ, chuyển producer sang khóa mới, xác minh provider enforcement và duy trì khả năng xử lý dữ liệu/chữ ký lịch sử hợp lệ.

**Câu 2. SUSPENDED khác REVOKED thế nào?**

**Trả lời:** SUSPENDED là tạm ngừng có thể tái đánh giá; REVOKED là rút quyền/niềm tin, thường cần thay khóa và xử lý sự cố, không mặc nhiên được quay lại ACTIVE.

**Câu 3. Có thể gắn DESTROYED ngay khi gọi ScheduleDelete không?**

**Trả lời:** Không. Chỉ khi hủy vật liệu khóa thực tế đã được xác nhận và đã xử lý các bản sao/phụ thuộc thuộc phạm vi quản lý.

**Câu 4. Vì sao thời gian dùng khóa ký và khóa mã hóa có thể khác nhau?**

**Trả lời:** Public verification key có thể cần để xác minh chữ ký lịch sử sau khi private signing key đã hủy; dữ liệu mã hóa lại cần DEK/KEK để decrypt/unwrap theo retention.

**Câu 5. KMS disable signing key có làm Verify chữ ký cũ thất bại không?**

**Trả lời:** Không tự động. Verify bằng public key có thể vẫn đúng toán học; verifier phải áp dụng trust, trạng thái thu hồi, timestamp và chính sách nghiệp vụ.

**Câu 6. expectedRevision để làm gì?**

**Trả lời:** Phát hiện yêu cầu stale/concurrent và ngăn transition dựa trên state cũ ghi đè kết quả mới.

**Câu 7. Idempotency có bảo đảm exactly-once giữa KMS và DB không?**

**Trả lời:** Không. Cần orchestration, retry an toàn, outbox và reconciliation.

**Câu 8. Khi compromise, có phải chờ quy trình hai người duyệt mới được chặn Sign?**

**Trả lời:** Không nhất thiết. Có thể có break-glass để chặn khẩn cấp, kèm quyền giới hạn, audit và hậu kiểm.

**Câu 9. Desired state khác observed provider state ra sao?**

**Trả lời:** Desired là mục tiêu chính sách, observed là trạng thái KMS/HSM thực tế. Hai bên có thể lệch do độ trễ hoặc lỗi.

**Câu 10. Rotate KEK có nhất thiết re-encrypt dữ liệu không?**

**Trả lời:** Không. Khi DEK chưa bị lộ, có thể chỉ rewrap DEK dưới KEK mới. Thay DEK mới thường cần re-encrypt dữ liệu liên quan.

**Câu 11. Vì sao cần theo dõi cache của verifier sau REVOKED?**

**Trả lời:** Cache cũ có thể tiếp tục tin public key đã bị lộ và chấp nhận chữ ký/token giả.

**Câu 12. Vì sao hủy KEK phải kiểm tra backup?**

**Trả lời:** Backup có thể chứa encrypted DEK chỉ unwrap được bằng KEK cũ, nên hủy sớm có thể làm mất khả năng phục hồi dữ liệu.

**Câu 13. Ai có thể xác nhận trạng thái DESTROYED?**

**Trả lời:** Workflow có thẩm quyền dựa trên bằng chứng hủy thực tế từ provider, kiểm soát backup và phê duyệt theo policy, không dựa vào flag do caller tự khai.

**Câu 14. Ví dụ Java đã là workflow production chưa?**

**Trả lời:** Chưa. Nó chỉ minh họa state machine và guards; production phải có IAM, KMS/HSM, CAS, idempotency, audit, reconciliation, outbox và test phân tán.

## 23. Checklist và ghi nhớ

Trước khi cho phép chuyển trạng thái khóa:

- **Key identity:** đúng key ID, materialVersion, tenant, algorithm, key usage?
- **State:** from/to nằm trên cạnh hợp lệ, revision không stale?
- **Authorization:** actor, approver, separation of duties và break-glass có hợp lệ?
- **Reason:** có change request/incident, lý do và cryptoperiod rõ ràng?
- **Guards:** replacement readiness, trust distribution, dependency inventory, retention và backup được kiểm tra từ nguồn đáng tin?
- **Provider:** KMS/HSM thực sự chặn/mở những phép toán cần thiết, không chỉ đổi registry?
- **Data:** còn encrypted DEK/ciphertext phụ thuộc hoặc cần rewrap/re-encrypt không?
- **Signing:** public key/chứng chỉ đã cập nhật, verifier cache và chữ ký lịch sử xử lý theo policy?
- **Concurrency:** CAS, idempotency, retry, event ordering, fencing và reconciliation được thiết kế?
- **Postcondition:** observedProviderState, consumer propagation và effectiveAt được xác minh?
- **Audit:** log đủ danh tính, version, decision và result mà không làm lộ key material?
- **Incidents:** nếu transition lỗi một phần, hệ thống có giữ hành vi fail-safe và phục hồi workflow không?
- **Destruction:** đã xác minh hủy thực tế, bản sao/backup và nghĩa vụ lưu giữ trước khi gọi DESTROYED?

**Ghi nhớ:** **Chuyển trạng thái có kiểm soát là quy trình bảo mật được thực thi và xác minh, không phải phép sửa trường status.** Một transition an toàn cần **state machine, guard, IAM/phê duyệt, revision, KMS/HSM enforcement, đồng bộ verifier, xử lý phụ thuộc dữ liệu, audit và quy trình sự cố**. Những kiểm soát này giúp vòng đời **tạo–cấp phát–sử dụng–xoay vòng–thu hồi–hủy** của **DEK/KEK, envelope encryption và khóa dùng cho chữ ký số** vận hành nhất quán, giảm nguy cơ mất dữ liệu hoặc lạm dụng quyền.
