# PAM configuration backup

## 1. Mục tiêu của sao lưu cấu hình PAM

Sao lưu cấu hình PAM là tạo và bảo vệ một tập thông tin đủ để tái lập các thiết lập của hệ thống quản lý truy cập đặc quyền tại một thời điểm xác định. Mục tiêu không chỉ là đưa giao diện quản trị hoạt động trở lại. Sau khôi phục, hệ thống phải tiếp tục thực thi đúng quyền truy cập, quy trình phê duyệt, giới hạn phiên, chính sách luân chuyển credential và yêu cầu lưu bằng chứng.

Một hệ thống PAM có thể vẫn chạy nhưng không còn an toàn nếu khôi phục thiếu một thành phần cấu hình. Ví dụ, chính sách yêu cầu hai người phê duyệt đã được phục hồi, nhưng ánh xạ nhóm từ IdP lại trỏ tới một nhóm rộng hơn. Người dùng khi đó có thể nhận quyền không đúng thiết kế dù việc import không báo lỗi.

Trong chương Backup và khôi phục, bài này tập trung vào **bản sao cấu hình**: xác định phạm vi, tạo tập sao lưu có thể sử dụng, bảo vệ nó và xác minh khả năng phục hồi cấu hình. Sao lưu toàn bộ kho bí mật, bản ghi phiên và khôi phục thảm họa là những phạm vi liên quan nhưng phải được quản lý như các hạng mục riêng.

Sau bài học, người học cần làm được các việc sau:

- Lập danh mục cấu hình PAM cần sao lưu và các phụ thuộc cần để khôi phục.
- Phân biệt export cấu hình, snapshot dữ liệu, cấu hình dưới dạng mã và bản sao máy chủ.
- Thiết kế lịch sao lưu đáp ứng mục tiêu phục hồi cùng với thay đổi quyền đặc quyền.
- Mô tả một quy trình sao lưu có kiểm tra tính toàn vẹn và quản lý khóa.
- Xác định các điều kiện để chấp nhận hoặc từ chối một bản sao cấu hình khi diễn tập khôi phục.

## 2. Cấu hình PAM thực sự bao gồm những gì?

Cấu hình là thông tin quyết định hệ thống PAM hoạt động và thực thi kiểm soát như thế nào. Một phần nằm trong tệp trên máy chủ; phần khác nằm trong cơ sở dữ liệu, kho cấu hình nội bộ, API quản trị hoặc hệ thống triển khai.

Không nên dùng câu hỏi “đã chép thư mục cấu hình chưa?” làm tiêu chí đầy đủ. Câu hỏi cần trả lời là: “Từ tập sao lưu này, một nhóm phục hồi được ủy quyền có thể dựng lại đúng các kiểm soát cần thiết hay chưa?”

| Nhóm thông tin | Ví dụ cần kiểm kê | Điều cần xác minh khi phục hồi |
|---|---|---|
| Chính sách truy cập | Role, quyền thao tác, scope tài nguyên, điều kiện truy cập | Quyền được cấp đúng đối tượng và đúng phạm vi |
| Ánh xạ danh tính | Nhóm IdP/LDAP, định danh nhóm, ánh xạ role | Định danh vẫn khớp, không chỉ trùng tên hiển thị |
| JIT và JEA | Thời hạn cấp quyền, approval, command profile, task profile | Không biến quyền tạm thời thành quyền thường trực |
| Quản trị vault | Cấu trúc vùng lưu trữ, owner, ACL, metadata đối tượng | Ranh giới giữa các nhóm quản trị được giữ nguyên |
| Luân chuyển credential | Policy, lịch, tham số connector, quy trình reconcile | Không chạy nhầm vào tài khoản thật trong lúc kiểm thử |
| Quản lý phiên | Proxy, gateway, profile kết nối, timeout, recording policy | Phiên được định tuyến và kiểm soát đúng |
| Tích hợp | IdP, MFA, SIEM, ITSM, email, secrets consumer | Endpoint, trust và thông tin xác thực đáp ứng môi trường đích |
| Cấu hình nền tảng | Listener, TLS, DNS liên quan, dịch vụ, tham số triển khai | Dịch vụ khởi động đúng và chỉ mở các kết nối cần thiết |
| Plugin và automation | Phiên bản plugin, script, cấu hình thực thi, dependency | Artifact tương thích và có nguồn gốc được kiểm chứng |
| Cơ chế phục hồi | Tham chiếu khóa, quy trình tiếp cận KMS/HSM, người giữ quyền | Có thể mở và sử dụng bản sao theo đúng cơ chế của sản phẩm |

Danh mục này cần được điều chỉnh theo sản phẩm và cách triển khai. Một giải pháp SaaS có thể chỉ cho phép export một phần cấu hình; khả năng phục hồi phía nhà cung cấp và khả năng phục hồi cấu hình tenant của khách hàng phải được phân định rõ. Không suy ra quyền truy cập bản sao nội bộ của nhà cung cấp từ việc có tài khoản quản trị tenant.

### 2.1. Phân biệt cấu hình với các lớp dữ liệu khác

Bốn lớp sau thường bị gộp vào một tên gọi “backup PAM”, làm che khuất phần còn thiếu:

1. **Cấu hình và chính sách:** ai được làm gì, với điều kiện nào, qua thành phần nào.
2. **Dữ liệu bí mật và trạng thái credential:** password, private key, secret version, trạng thái checkout hoặc thông tin quản lý tài khoản.
3. **Bằng chứng và lịch sử:** audit event, bản ghi phiên, lịch sử phê duyệt, dữ liệu phục vụ điều tra.
4. **Khóa và nền tảng tin cậy:** khóa giải mã, khóa ký, chứng thư, khả năng truy cập KMS/HSM hoặc cơ chế mở kho.

Một export cấu hình không mặc nhiên chứa dữ liệu bí mật hay audit log. Ngược lại, một snapshot cơ sở dữ liệu có thể chứa cả cấu hình lẫn dữ liệu nhạy cảm. Phải ghi rõ nội dung thực tế của từng loại bản sao thay vì suy đoán theo phần mở rộng tệp.

Tài liệu chính thức của HashiCorp Vault cũng phân biệt sao lưu dữ liệu lưu trữ với việc giữ tệp cấu hình máy chủ, script vận hành và khả năng cài lại plugin. Tài liệu lưu ý cấu hình có thể chứa thông tin nhạy cảm dù dữ liệu ở storage backend đã được mã hóa. Đây là ví dụ cho việc phải kiểm kê nhiều lớp, không phải khẳng định mọi sản phẩm PAM dùng cùng cấu trúc. [Nguồn: HashiCorp Vault — Storage](https://developer.hashicorp.com/vault/docs/concepts/storage)

### 2.2. Tham chiếu không phải dữ liệu đã được sao lưu

Giả sử cấu hình chứa:

~~~yaml
identity_provider: idp-corporate
backup_encryption_key_ref: kms://recovery-domain/pam-config
rotation_connector_credential_ref: secret://pam-connectors/rotation
~~~

Các giá trị này chỉ minh họa tham chiếu, không phải cú pháp của một sản phẩm cụ thể.

Bản sao có đủ ba dòng trên chưa chứng minh rằng nhóm phục hồi truy cập được IdP, khóa mã hóa hay credential của connector. Ngược lại, thay chúng bằng password hoặc private key dạng rõ sẽ làm tăng mức độ nhạy cảm của bản sao.

Cần quản lý riêng:

- Cấu hình và định danh phụ thuộc.
- Phương thức có thẩm quyền để phục hồi hoặc tiếp cận phụ thuộc.
- Điều kiện truy cập và kiểm thử phương thức đó.
- Người chịu trách nhiệm khi phụ thuộc không sẵn sàng.

Một tệp export có giá trị bị che thành `********` cũng không chứng minh secret đã được bảo toàn. Phải xác định đó là giá trị đã bị loại bỏ hay là tham chiếu có thể tiếp tục sử dụng theo cơ chế của sản phẩm.

## 3. Một bản sao cấu hình tốt phải đáp ứng điều kiện nào?

Có thể đánh giá một tập sao lưu theo năm thuộc tính:

**Đủ phạm vi:** Bao gồm các đối tượng đã được đưa vào kế hoạch phục hồi. Thành phần bị loại trừ phải có lý do và cách cung cấp thay thế.

**Nhất quán:** Các thành phần liên quan biểu diễn một trạng thái có thể phục hồi được. ACL của vault, role và mapping danh tính không được lấy từ ba thời điểm tùy ý rồi xem là một bộ hoàn chỉnh.

**Được bảo vệ:** Người không có quyền không thể đọc, sửa hoặc hủy bản sao; người có nhiệm vụ phục hồi vẫn có thể tiếp cận khi hệ thống chính gặp sự cố.

**Có nguồn gốc và phiên bản rõ ràng:** Xác định được hệ thống nguồn, thời điểm, phiên bản sản phẩm, phương thức export, thay đổi liên quan và người hoặc workload tạo bản sao.

**Có bằng chứng sử dụng được:** Đã có kiểm thử phục hồi phù hợp. Tệp tồn tại hoặc job báo thành công chỉ là một phần của bằng chứng.

Các nguyên tắc trên tương ứng với cách tiếp cận của NIST SP 800-53, kiểm soát CP-9: xác định sao lưu thông tin hệ thống, bảo vệ bản sao và kiểm tra độ tin cậy, tính toàn vẹn theo yêu cầu của tổ chức. NIST không cung cấp một lịch sao lưu PAM duy nhất cho mọi doanh nghiệp. [Nguồn: NIST SP 800-53 Rev. 5, CP-9](https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-53r5.pdf)

## 4. Chọn phương thức sao lưu theo mục đích phục hồi

Các phương thức dưới đây có thể bổ sung cho nhau. Không nên lựa chọn chỉ vì một phương thức tạo ra tệp nhỏ hơn hoặc triển khai nhanh hơn.

| Phương thức | Giá trị chính | Giới hạn cần xử lý |
|---|---|---|
| Export qua chức năng hoặc API được hỗ trợ | Lấy các đối tượng cấu hình theo mô hình của sản phẩm | Có thể thiếu secret, trạng thái nội bộ, plugin hoặc đối tượng không được export |
| Backup cơ sở dữ liệu hoặc snapshot ứng dụng được hỗ trợ | Bảo toàn trạng thái persisted theo cơ chế lưu trữ | Có thể chứa nhiều dữ liệu hơn cấu hình và kéo theo yêu cầu nhất quán, tương thích |
| Cấu hình dưới dạng mã | Có diff, review, version và khả năng tái triển khai | Không tự bao phủ thay đổi thủ công, dữ liệu runtime hay dependency bên ngoài |
| Backup tệp triển khai và artifact | Phục hồi listener, service, plugin, script và cấu hình node | Không thay thế bản sao cấu hình lưu trong cơ sở dữ liệu |
| Bản sao máy ảo hoặc máy chủ | Hỗ trợ tái dựng một môi trường nền tảng | Không tự chứng minh tính nhất quán ứng dụng hoặc khả năng dùng khóa sau phục hồi |

Với mỗi thành phần, chọn cơ chế đã được sản phẩm và backend lưu trữ hỗ trợ. Không tự chép các tệp cơ sở dữ liệu đang được ghi rồi coi đó là một snapshot nhất quán.

Nếu giải pháp yêu cầu tạm dừng thay đổi hoặc dừng dịch vụ để backup, phải đưa thời gian đó vào kế hoạch vận hành. Nếu hỗ trợ snapshot trực tuyến, vẫn cần theo dõi trạng thái hoàn thành và điều kiện nhất quán của snapshot.

### 4.1. HA và replication không thay thế bản sao theo thời điểm

HA giúp duy trì dịch vụ khi một thành phần lỗi. Replication có thể chuyển thay đổi tới một hệ thống khác. Nếu một policy bị xóa hoặc một quyền quá rộng được tạo và nhân bản, hệ thống dự phòng có thể nhận cùng thay đổi.

Bản sao theo thời điểm cung cấp khả năng quay lại trạng thái trước thay đổi. Tuy nhiên, quay lại trạng thái cũ cũng có thể khôi phục một quyền đã bị thu hồi. Vì vậy, khả năng quay lui phải đi cùng bước đối soát các thay đổi an ninh phát sinh sau thời điểm sao lưu.

### 4.2. Git chỉ nên chứa phần cấu hình phù hợp

Cấu hình dưới dạng mã có ích cho role, policy, tham số triển khai và lịch sử thay đổi đã được rà soát. Tuy nhiên, một repository riêng tư không mặc nhiên là nơi được phép lưu mọi export.

Trước khi đưa dữ liệu vào Git, cần xét:

- Có password, token, private key hoặc dữ liệu nhúng trong URL hay không?
- Danh sách tài khoản đặc quyền và topology có bị lộ không?
- Có thể khôi phục đầy đủ từ mã hay còn thay đổi thủ công chưa được ghi nhận?
- Dependency và artifact đúng phiên bản có còn lấy được không?
- Repository có nằm trong cùng miền quản trị có thể bị sự cố với PAM không?

Secret đã commit có thể còn trong lịch sử ngay cả khi bị xóa ở commit sau. Quy trình sao lưu không nên tạo thêm một đường lưu trữ secret ngoài thiết kế.

## 5. Xác định RPO, RTO và lịch sao lưu cấu hình

**RPO — Recovery Point Objective** là mục tiêu về mức mất dữ liệu chấp nhận được theo thời gian. Với cấu hình PAM, cần xét lượng thay đổi cấu hình có thể phải tái lập sau khi phục hồi.

**RTO — Recovery Time Objective** là mục tiêu về thời gian khôi phục khả năng phục vụ đã được xác định. Với PAM, “phục vụ” cần bao gồm các kiểm soát tối thiểu, không chỉ trạng thái tiến trình đang chạy.

Các con số phải xuất phát từ nhu cầu của tổ chức. Ví dụ minh họa:

~~~text
Mục tiêu nội bộ:
- RPO cấu hình: 15 phút.
- RTO cho truy cập quản trị có kiểm soát: 120 phút.
- Bắt buộc có bản sao hợp lệ trước thay đổi lớn.
- Thay đổi quyền khẩn cấp được ghi vào nhật ký phục hồi độc lập.
~~~

Đây là giả định bài tập, không phải tiêu chuẩn bắt buộc cho PAM.

### 5.1. Đo trên bản sao hợp lệ có thể tiếp cận

Giả sử:

~~~text
02:00  Bản sao gần nhất hoàn tất và đã kiểm tra.
02:15  Thay đổi policy JIT.
02:25  Thu hồi quyền của một tài khoản quản trị.
02:30  Sự cố làm mất khả năng sử dụng cấu hình hiện tại.
~~~

Nếu chỉ còn bản sao hợp lệ lúc 02:00, khoảng dữ liệu chưa được bảo toàn đến thời điểm sự cố là 30 phút. Một lịch “chạy mỗi 15 phút” không chứng minh đáp ứng RPO nếu các job sau đó lỗi hoặc bản sao không thể giải mã.

Sau khi khôi phục bản sao 02:00, nhóm phục hồi còn phải xem xét thay đổi 02:15 và đặc biệt việc thu hồi quyền 02:25. Bản sao nguyên vẹn nhưng quá cũ so với quyết định thu hồi vẫn có thể tạo ra quyền truy cập sai.

Trong tình huống mất cả site, chỉ tính các bản sao còn truy cập được ở miền phục hồi. Một bản sao mới hơn nằm duy nhất trong vùng đã mất không giúp đáp ứng mục tiêu của kịch bản đó.

### 5.2. Kết hợp lịch định kỳ và sự kiện thay đổi

Lịch sao lưu có thể gồm:

- Định kỳ để giới hạn khoảng mất cấu hình.
- Trước thay đổi lớn để có điểm phục hồi.
- Sau khi thay đổi đã được nghiệm thu để có baseline mới.
- Sau các thay đổi nhạy cảm theo quy trình nội bộ.
- Sau nâng cấp để ghi nhận tập cấu hình tương thích với phiên bản mới.

Cần giữ được các điểm trước và sau thay đổi trong thời gian cần thiết. Nếu bản sao mới ghi đè bản sao tốt cuối cùng ngay sau một cấu hình sai, khả năng phục hồi sẽ giảm.

Không nhất thiết chạy export toàn bộ sau mỗi thao tác nhỏ. Có thể kết hợp snapshot, nhật ký thay đổi và cấu hình dưới dạng mã, nhưng phải chứng minh rằng chuỗi phục hồi thực sự tái lập được trạng thái mong muốn.

## 6. Thiết kế một tập sao lưu có thể kiểm chứng

Một **tập sao lưu** gồm các artifact và thông tin cần để sử dụng chúng như một đơn vị phục hồi. Nếu backup có nhiều phần, chỉ đánh dấu tập hoàn chỉnh khi mọi phần bắt buộc đã hoàn tất và vượt qua kiểm tra.

Ví dụ bố cục logic:

~~~text
backup-set/
  inventory.yml
  platform-configuration.enc
  policy-export.enc
  deployment-configuration.enc
  artifact-catalog.enc
  verification-report.enc

Kho bằng chứng tách quyền sửa:
  manifest đã xác thực
  checksum của các artifact đã mã hóa
  kết quả kiểm thử
  lịch sử phê duyệt và thao tác

Cơ chế quản lý khóa riêng:
  tham chiếu khóa
  quyền sử dụng khóa
  quy trình tiếp cận khi có sự cố
~~~

Bố cục này là mô hình minh họa. Không phải tên tệp hay định dạng import của một sản phẩm cụ thể.

Phần inventory cũng có thể chứa dữ liệu nhạy cảm. Chỉ để công khai những trường thực sự cần cho việc tra cứu và xác minh ban đầu. Quyền đọc manifest không nên vô tình tiết lộ tên tài khoản đặc quyền, hostname nội bộ hoặc cấu trúc nhóm quản trị.

### 6.1. Những trường nên ghi trong inventory

~~~yaml
backup_set:
  id: pam-config-example-20261126-020000
  source_environment: production-example
  scope: configuration
  captured_at_utc: "2026-11-26T02:00:00Z"
  completed_at_utc: "2026-11-26T02:04:00Z"
  application_version: "example-version"
  configuration_revision: "approved-revision-example"
  export_method: "vendor-supported-method"
  consistency_basis: "documented-consistency-procedure"
  change_record: "CHANGE-EXAMPLE"
  required_components:
    - platform_configuration
    - access_policy
    - identity_mapping
    - connector_configuration
    - deployment_configuration
  artifact_catalog_ref: "protected-artifact-catalog"
  encryption_key_ref: "approved-recovery-key-reference"
  integrity_record_ref: "protected-integrity-record"
  restore_procedure_ref: "approved-runbook-revision"
  exclusions:
    - "session-recordings: managed by a separate backup plan"
    - "secret-values: managed by a separate recovery plan"
  state: complete
~~~

Đây là một mẫu thiết kế. Các giá trị có chữ `example` phải được thay bằng giá trị thật trong hệ thống triển khai; không dùng mẫu làm bằng chứng rằng đã có backup thành công.

Việc ghi `scope: configuration` cũng không làm một snapshot toàn cơ sở dữ liệu trở thành “chỉ chứa cấu hình”. Inventory phải phản ánh nội dung thực tế, kể cả khi cơ chế backup mang theo dữ liệu ngoài phạm vi tối thiểu.

### 6.2. Checksum, tính xác thực và khả năng giải mã là ba kiểm tra khác nhau

- **Checksum** giúp phát hiện nội dung khác với giá trị đối chiếu.
- **Chữ ký hoặc manifest được bảo vệ bằng một cơ chế xác thực phù hợp** giúp xác định nguồn và bảo vệ giá trị đối chiếu.
- **Kiểm thử giải mã và phục hồi** cho biết dữ liệu có thể được sử dụng trong điều kiện đã kiểm thử.

Nếu kẻ tấn công sửa được cả artifact lẫn tệp checksum, việc hai giá trị khớp nhau không chứng minh tính xác thực. Giá trị đối chiếu phải nằm trong một cơ chế bảo vệ mà người sửa artifact không thể tùy ý thay đổi.

Nếu checksum được tính trên ciphertext, kết quả khớp chỉ chứng minh ciphertext không thay đổi so với bản đối chiếu. Nó chưa chứng minh khóa còn sử dụng được, dữ liệu bên trong hợp lệ hay cấu hình phù hợp để đưa vào vận hành.

### 6.3. Khóa phải được quản lý theo vòng đời của bản sao

Một bản sao còn thời hạn lưu nhưng khóa giải mã đã bị hủy có thể không còn dùng được. Ngược lại, khóa bị lộ có thể làm nhiều thế hệ bản sao mất tính bảo mật.

Cần xác định rõ ai quản lý khóa, ai được sử dụng khóa và cách phục hồi quyền tiếp cận khóa. Với khóa không xuất được khỏi HSM hoặc KMS, không tự tạo yêu cầu “chép khóa ra tệp”; phải dùng cơ chế dự phòng, duy trì hoặc phục hồi được hỗ trợ.

Quy trình cần kiểm tra cả tình huống người vận hành không đăng nhập được PAM chính. Tránh vòng phụ thuộc: cần PAM để lấy credential của kho backup, nhưng cần bản sao trong kho backup để phục hồi PAM.

Giải pháp có thể gồm danh tính phục hồi độc lập, cơ chế break-glass được quản trị riêng và tài liệu nằm ngoài vùng sự cố. Những quyền này vẫn phải có owner, kiểm soát sử dụng và nhật ký; việc khẩn cấp không biến thành quyền quản trị thường trực không được theo dõi.

## 7. Quy trình tạo bản sao cấu hình

Quy trình dưới đây là khung vận hành, không phải lệnh chạy cho mọi sản phẩm.

### Bước 1 — Kiểm tra điều kiện đầu vào

Xác nhận hệ thống nguồn, phiên bản, phạm vi export, thời điểm thay đổi và kho đích. Kiểm tra khả năng sử dụng khóa, dung lượng, kết nối và danh tính của workload sao lưu.

Nếu có thành phần chưa được hỗ trợ export hoặc chưa rõ ảnh hưởng của export tới hệ thống, ghi nhận thiếu sót trước khi chạy. Không đánh dấu “đủ cấu hình” chỉ vì các thành phần dễ lấy đã thành công.

### Bước 2 — Xác lập trạng thái nhất quán

Áp dụng cơ chế của sản phẩm: một snapshot nhất quán, export trong một transaction được hỗ trợ, hoặc một cửa sổ kiểm soát thay đổi phù hợp.

Nếu phải xuất lần lượt nhiều tập đối tượng, ghi revision và kiểm tra thay đổi xen giữa. Khi không chứng minh được quan hệ giữa các phần, coi tập sao lưu là chưa hoàn chỉnh.

Không tự tắt audit hoặc nới quyền toàn hệ thống để làm job chạy được. Quyền của tài khoản sao lưu phải được thiết kế theo cơ chế thực tế; trong một số giải pháp, quyền export snapshot có thể cho phép lấy nhiều dữ liệu nhạy cảm, nên không được đánh giá thấp chỉ vì tên quyền là “backup”.

### Bước 3 — Xuất dữ liệu và ghi nhận kết quả từng phần

Với mỗi thành phần, ghi thời điểm, trạng thái hoàn thành, định danh artifact, kích thước và revision nếu có. Chỉ lưu các thông tin cần thiết; không ghi secret hoặc nội dung export vào log job.

Một API trả về mã tiếp nhận công việc chưa phải bằng chứng export đã hoàn tất. Phải theo dõi trạng thái cuối cùng và xác nhận artifact có thể truy xuất.

### Bước 4 — Bảo vệ artifact và chuyển tới kho đích

Mã hóa bằng cơ chế đã được phê duyệt, bảo vệ đường truyền và hạn chế thời gian tồn tại của bản rõ trong vùng làm việc. Nếu công cụ bắt buộc tạo tệp tạm, vùng đó cần quyền truy cập chặt chẽ và cơ chế dọn dẹp phù hợp.

Kiểm tra bản lưu tại đích, không chỉ bản trong vùng staging. Việc tải lên thành công một tệp rỗng hoặc nhầm artifact vẫn phải bị phát hiện.

### Bước 5 — Kiểm tra tính toàn vẹn và độ đầy đủ

Đối chiếu danh mục thành phần, checksum, revision và điều kiện nhất quán. Lưu manifest cùng bằng chứng theo cơ chế xác thực đã chọn.

Có thể biểu diễn điều kiện hoàn thành:

~~~text
backup_set_complete =
    all_required_components_finished
    AND consistency_checks_passed
    AND destination_copy_verified
    AND integrity_evidence_recorded
    AND recovery_key_dependency_identified
~~~

Điều kiện này xác nhận tập sao lưu được tạo đúng quy trình. Kết quả kiểm thử phục hồi phải được quản lý như bằng chứng bổ sung, có thời điểm và phạm vi riêng.

### Bước 6 — Công bố trạng thái và xử lý lỗi

Cập nhật bản sao hợp lệ gần nhất chỉ sau khi các điều kiện bắt buộc đạt. Một tập mới bị thiếu thành phần không được đẩy bản tốt trước đó ra khỏi danh mục phục hồi.

Cảnh báo cần nêu rõ phần lỗi, bản hợp lệ gần nhất còn lại và ảnh hưởng tới RPO. Không dùng một thông báo “backup failed” chung chung nếu người trực không biết hiện còn bản nào sử dụng được.

## 8. Bảo vệ bản sao khỏi lạm dụng đặc quyền

Cấu hình PAM có thể tiết lộ ranh giới quản trị, nhóm có quyền cao, topology kết nối và quy tắc bảo vệ tài khoản. Một số export còn chứa credential hoặc khóa. Vì vậy, phân loại bản sao theo dữ liệu thật bên trong, không theo nhãn “configuration”.

Nên phân tách các quyền sau khi công nghệ và quy trình cho phép:

| Vai trò | Trách nhiệm | Quyền cần tránh gộp không cần thiết |
|---|---|---|
| Workload sao lưu | Tạo và ghi artifact theo lịch | Xóa toàn bộ lịch sử, tự giảm retention, cấp quyền phục hồi cho chính nó |
| Quản trị kho backup | Duy trì lưu trữ, retention và tính sẵn sàng | Tự giải mã mọi bản sao |
| Người quản lý khóa | Duy trì quyền và vòng đời khóa | Tự thay đổi artifact để che dấu can thiệp |
| Người phục hồi | Thực hiện runbook được phê duyệt | Tự thay đổi chính sách rồi tự nghiệm thu |
| Người nghiệm thu | Kiểm tra bằng chứng và kết quả kiểm soát | Dùng quyền phục hồi cho công việc vận hành thường ngày |

Đây là mô hình phân trách nhiệm, không bắt buộc phải tạo năm tài khoản cho mọi hệ thống. Điểm cần giữ là một credential bị chiếm không dễ dàng vừa sửa PAM, vừa xóa các điểm phục hồi và vừa sửa bằng chứng.

Các lớp bảo vệ thường cần xem xét gồm:

- Bản sao ở miền quản trị hoặc vùng lỗi độc lập với hệ thống nguồn.
- Cơ chế bất biến hoặc chống xóa trong thời gian đã chọn.
- Quyền đọc, tải xuống, giải mã và xóa được giới hạn riêng khi có thể.
- Nhật ký truy cập và thay đổi retention được lưu ngoài vùng mà workload backup có thể sửa.
- Kiểm soát việc thay đổi lịch, khóa và đích sao lưu.
- Phê duyệt phù hợp cho thao tác phục hồi hoặc hủy các thế hệ bản sao quan trọng.

Bất biến không làm bản sao tự nhiên đúng hoặc sạch. Nó có thể giữ nguyên một cấu hình đã bị xâm phạm. Vẫn cần nhiều điểm theo thời gian và bằng chứng để chọn trạng thái đáng tin.

Thời hạn lưu phải cân bằng nhu cầu phục hồi, điều tra, chi phí và yêu cầu quản lý dữ liệu của tổ chức. Không tự giữ vô hạn mọi credential lịch sử chỉ vì dung lượng còn đủ.

## 9. Kiểm thử phục hồi cấu hình trong môi trường cô lập

Kiểm thử cần trả lời hai câu hỏi: có nhập lại được cấu hình không, và cấu hình sau nhập có thực thi đúng các kiểm soát cần thiết không?

Một môi trường kiểm thử vô tình kết nối production có thể gây tác động thật. Ví dụ, connector luân chuyển credential được phục hồi có thể đổi password tài khoản sản xuất nếu lịch chạy và đường mạng vẫn hoạt động.

Trước khi khởi động các thành phần có khả năng tạo tác động:

1. Dựng môi trường theo phiên bản và cơ chế khôi phục được hỗ trợ.
2. Chặn kết nối tới tài nguyên thật theo chính sách mạng đã chuẩn bị.
3. Vô hiệu hóa các tác vụ có tác động ngoài môi trường kiểm thử bằng phương thức được hỗ trợ.
4. Dùng IdP, tài khoản đích, endpoint SIEM/ITSM và connector thử nghiệm khi phù hợp.
5. Xác nhận thay đổi để cô lập đã được ghi nhận và không bị nhầm thành cấu hình chuẩn cho production.

Các tác vụ cần chú ý gồm rotation, reconciliation, cấp hoặc thu hồi quyền, đồng bộ danh tính, gửi thông báo, gọi API cloud và replication.

### 9.1. Ma trận xác minh sau import

| Nhóm kiểm tra | Thử nghiệm đại diện | Điều kiện đạt |
|---|---|---|
| Nhận dạng cấu hình | Đối chiếu revision, thành phần và số lượng đối tượng dự kiến | Đúng tập đã chọn; chênh lệch có giải thích |
| Định danh và mapping | Đăng nhập bằng danh tính thử nghiệm được phép | Nhận đúng role và scope |
| Từ chối truy cập | Dùng danh tính ngoài nhóm hoặc ngoài scope | Bị từ chối theo chính sách |
| JIT/JEA | Yêu cầu một quyền tạm thời và thao tác vượt profile | Quy trình cấp quyền, hết hạn và giới hạn thao tác đúng |
| Phê duyệt | Kiểm tra yêu cầu thiếu phê duyệt bắt buộc | Không được thực thi trái policy |
| Phiên đặc quyền | Mở phiên thử nghiệm qua gateway | Áp dụng timeout, điều kiện và ghi nhận theo thiết kế |
| Tích hợp nhật ký | Phát sinh sự kiện thử nghiệm | Có bằng chứng tại đích kiểm thử |
| Plugin/connector | Nạp artifact đúng phiên bản, thử với tài nguyên giả lập | Không thiếu artifact và không tác động production |
| Credential tham chiếu | Xác minh phương thức cung cấp dependency | Không phải chèn credential rõ vào cấu hình để vượt lỗi |
| Đường phục hồi | Thử tiếp cận artifact và khóa bằng danh tính phục hồi | Không phụ thuộc hoàn toàn vào PAM đã mất |

Không lấy việc tài khoản quản trị toàn quyền đăng nhập được làm bằng chứng duy nhất. Các thử nghiệm từ chối và hết hạn quyền thường phát hiện lỗi mapping hoặc policy mà phép thử đăng nhập thành công không phát hiện.

Nếu SIEM hoặc một tích hợp bắt buộc chưa sẵn sàng, xử lý theo chế độ suy giảm đã được phê duyệt. Không tự bỏ yêu cầu ghi nhận hoặc chuyển mọi truy cập sang tài khoản break-glass chỉ để đạt RTO.

### 9.2. Đối soát thay đổi sau thời điểm sao lưu

Trước khi dùng một cấu hình cũ cho production, kiểm tra ít nhất:

- Quyền và tài khoản đã bị thu hồi.
- Thay đổi nhóm quản trị, mapping và người phê duyệt.
- Chứng thư, trust hoặc credential đã thay đổi.
- Connector, endpoint hoặc tài nguyên đã bị loại bỏ.
- Các quyết định cô lập tài khoản hay hệ thống trong quá trình ứng phó sự cố.

Nguồn đối soát phải đáng tin và còn tiếp cận được, chẳng hạn nhật ký thay đổi được bảo vệ độc lập. Nếu chỉ lấy dữ liệu từ chính hệ thống đang nghi bị xâm phạm thì chưa đủ để khẳng định cấu hình là sạch.

Cần phân biệt “tái lập trạng thái lịch sử” với “cho phép sử dụng trạng thái đó hiện tại”. Có thể phải chặn các quyền nhạy cảm cho tới khi đối soát hoàn tất.

### 9.3. Bằng chứng cần giữ sau diễn tập

Biên bản nên ghi tập sao lưu, phiên bản môi trường phục hồi, người thực hiện, thời gian từng giai đoạn, kiểm tra đạt hoặc lỗi và những phần chưa được kiểm thử.

Nếu chỉ import cấu hình mà không thử kết nối tới tài nguyên sản xuất, phải ghi đúng giới hạn đó. Không suy diễn kết quả thử nghiệm cô lập thành bằng chứng đã kiểm tra toàn bộ quy trình vận hành thật.

Sau diễn tập, thu hồi quyền tạm, xử lý dữ liệu thử nghiệm, dọn artifact theo quy định và xác nhận không để lại các tác vụ nền có thể tác động tới hệ thống thật.

## 10. Tình huống: bản sao đầy đủ nhưng quyền đã lỗi thời

Một tổ chức có bản sao cấu hình hợp lệ lúc 01:00. Lúc 08:10, nhóm an ninh thu hồi quyền của một nhà thầu và thay nhóm phê duyệt JIT. Lúc 09:00, một thay đổi cấu hình làm hệ thống PAM không phục vụ được.

Nhóm vận hành có thể phục hồi bản 01:00 trong 40 phút, nhưng nếu đưa ngay vào sử dụng thì quyền của nhà thầu có thể xuất hiện trở lại.

Cách xử lý hợp lý:

1. Xác minh bản 01:00 là tập phù hợp, toàn vẹn và tương thích.
2. Phục hồi trong điều kiện mạng và tác vụ nền đã được kiểm soát.
3. Lấy thay đổi 08:10 từ nguồn được bảo vệ.
4. Áp dụng lại việc thu hồi và thay đổi nhóm phê duyệt theo quy trình.
5. Kiểm tra danh tính nhà thầu bị từ chối và yêu cầu JIT đi đúng nhóm mới.
6. Ghi nhận thời gian và phần kiểm soát đã xác minh trước khi mở lại dịch vụ.

Nếu không chứng minh được quyền thu hồi đã được giữ, nhóm phục hồi cần tiếp tục hạn chế phạm vi truy cập theo kế hoạch sự cố. “Import thành công” không đủ để nghiệm thu.

Tình huống này chỉ ra ba yêu cầu thiết kế: lịch sao lưu gắn với thay đổi quan trọng, nhật ký quyết định an ninh còn truy cập được và kiểm thử tập trung vào quyền thực tế sau khôi phục.

## 11. Các lỗi thường gặp và cách nhận biết

| Lỗi | Biểu hiện | Cách cải thiện |
|---|---|---|
| Chỉ sao chép một thư mục | Dịch vụ chạy nhưng thiếu policy hoặc mapping | Lập danh mục theo đối tượng và nơi lưu trữ |
| Xem API tiếp nhận là backup xong | Có job ID nhưng thiếu artifact hoàn chỉnh | Theo dõi trạng thái cuối cùng và kiểm tra bản tại đích |
| Chỉ giữ bản mới nhất | Cấu hình sai thay thế điểm phục hồi tốt | Giữ các thế hệ theo chính sách và theo mốc thay đổi |
| Backup và khóa cùng mất | Artifact còn nhưng không thể giải mã | Thiết kế phụ thuộc khóa theo kịch bản mất site |
| Dùng chung một quyền quản trị | Một tài khoản xóa được cả nguồn lẫn lịch sử | Phân tách quyền và miền quản trị phù hợp |
| Không ghi phiên bản plugin | Import được nhưng connector không chạy | Giữ catalog và khả năng cung cấp artifact đúng phiên bản |
| Export có giá trị bị che | Khôi phục thiếu credential cần thiết | Xác định cơ chế cung cấp hoặc phục hồi secret riêng |
| Chỉ thử tài khoản toàn quyền | Không phát hiện quyền rộng hoặc mapping sai | Thêm phép thử từ chối, scope và hết hạn |
| Không cô lập tác vụ nền | Diễn tập đổi password hoặc gọi API production | Kiểm soát egress và tác vụ trước khi khởi động |
| Bỏ qua quyền đã thu hồi | Tài khoản cũ truy cập lại sau restore | Đối soát thay đổi sau thời điểm sao lưu |
| Bỏ qua lỗi nhiều ngày | Lịch chạy dày nhưng bản hợp lệ quá cũ | Theo dõi tuổi bản hợp lệ và ảnh hưởng RPO |

## 12. Bài tập thực hành thiết kế

Giả sử một hệ thống PAM gồm một cổng quản trị, hai gateway phiên, một kho credential, một tích hợp IdP, một connector rotation và một pipeline audit. Tổ chức yêu cầu truy cập đặc quyền sau phục hồi vẫn phải qua phê duyệt và có bằng chứng theo policy.

Hãy thiết kế kế hoạch sao lưu cấu hình mà không dùng dữ liệu thật:

1. Lập danh mục cấu hình của từng thành phần; đánh dấu nơi có khả năng chứa secret.
2. Chọn cơ chế sao lưu được hỗ trợ và ghi các phần không nằm trong export.
3. Đề xuất RPO, RTO cùng lý do; phân biệt thời gian import và thời gian nghiệm thu kiểm soát.
4. Mô tả cách tiếp cận kho backup và khóa khi PAM chính không hoạt động.
5. Đưa ra một tập sao lưu minh họa với inventory, artifact và bằng chứng.
6. Viết ít nhất một phép thử truy cập được phép, một phép thử bị từ chối và một phép thử quyền hết hạn.
7. Mô tả cách ngăn connector rotation tác động production trong diễn tập.
8. Giải thích cách đối soát một quyền vừa bị thu hồi sau thời điểm backup.

Kết quả đạt khi kế hoạch chỉ rõ ai làm gì, dữ liệu ở đâu, phụ thuộc nào cần phục hồi và bằng chứng nào được dùng để kết luận. Một danh sách công cụ hoặc một lịch cron chưa đủ.

## 13. Tiêu chí hoàn thành một kế hoạch backup cấu hình PAM

Một kế hoạch có thể đưa vào triển khai khi đã xác định được phạm vi sao lưu, cơ chế nhất quán, danh tính thực hiện, kho lưu, quản lý khóa, lịch và retention, cùng runbook phục hồi được phân công rõ.

Khi vận hành, cần theo dõi tuổi của bản sao hợp lệ có thể tiếp cận, mức đầy đủ của thành phần, kết quả kiểm tra integrity, tình trạng phụ thuộc khóa và tuổi của lần kiểm thử phục hồi gần nhất. Mỗi chỉ số phải gắn với người xử lý khi vượt ngưỡng.

Giá trị của PAM configuration backup nằm ở khả năng tái lập các kiểm soát đặc quyền đã được xác minh. Tập sao lưu chỉ nên được nghiệm thu cho một phạm vi phục hồi cụ thể khi nhóm vận hành chứng minh được rằng cấu hình đầy đủ, có thể tiếp cận an toàn và không vô tình khôi phục những quyền đã phải thu hồi.
