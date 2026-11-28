# Tạo quá nhiều ngoại lệ không có thời hạn

## 1. Sai lầm nằm ở đâu?

Trong bảo mật mạng, một hệ thống được thiết kế theo nguyên tắc **default deny** chỉ nên cho phép các kết nối cần thiết, từ nguồn và danh tính phù hợp đến đúng đích, trên đúng dịch vụ. Tuy nhiên, khi vận hành thực tế, nhóm kỹ thuật thường gặp yêu cầu khẩn: “mở tạm cổng này để xử lý lỗi”, “cho cả subnet truy cập để triển khai nhanh”, “bỏ qua kiểm tra IDS/IPS để ứng dụng không bị chặn”. Nếu mỗi yêu cầu đều biến thành **ngoại lệ không có hạn kết thúc hoặc không có lịch đánh giá lại**, chính sách ban đầu dần mất hiệu lực.

Sai lầm **“Tạo quá nhiều ngoại lệ không có thời hạn”** không chỉ là một rule firewall tồn tại lâu. Vấn đề lớn hơn là **tích tụ các quyền vượt baseline mà không còn biết lý do, chủ sở hữu, phạm vi, rủi ro và điều kiện thu hồi**. Nhiều ngoại lệ nhỏ cộng lại có thể tạo ra đường truy cập từ vùng kém tin cậy tới tài sản quan trọng dù sơ đồ kiến trúc vẫn thể hiện các vùng đã phân tách.

Bài học thuộc chương **Sai lầm thường gặp** của module **SECURITY_NETWORK_SECURITY**. Nội dung liên hệ phân đoạn, firewall/ACL, VPN/ZTNA, IDS/IPS, DNS, mạng không dây, kết nối cloud và quản trị thiết bị. Mục tiêu không phải **cấm mọi ngoại lệ**, mà là quản lý ngoại lệ như một **khoản rủi ro có thời hạn, người chịu trách nhiệm và bằng chứng kiểm chứng**.

### Sau bài học, người học có thể

1. Nhận diện ngoại lệ mạng thiếu thời hạn, phạm vi hoặc người sở hữu, kể cả ngoại lệ ẩn trong object group, policy template và controller.
2. Giải thích vì sao rule sprawl, access creep và các đường bypass tích tụ khiến default deny suy yếu.
3. Phân biệt **quy tắc truy cập lâu dài đã chuẩn hóa** với **ngoại lệ tạm thời** hoặc **ngoại lệ rủi ro cần tái phê duyệt**.
4. Thiết kế quy trình cấp ngoại lệ với lý do, owner, phê duyệt, scope, thời hạn, giám sát, kiểm thử và rollback.
5. Kiểm tra những luồng cần được phép và không được phép; loại bỏ ngoại lệ cũ mà không ngắt dịch vụ ngoài kế hoạch.
6. Đo mức nợ ngoại lệ và xây cơ chế giám sát, nhắc hạn, tái xác nhận, thu hồi dựa trên rủi ro.

> **Thông điệp cốt lõi:** Một ngoại lệ được tạo vì “tạm thời” phải có **điểm kết thúc rõ ràng**; một quyền truy cập cần tồn tại lâu phải được **thiết kế thành baseline được phê duyệt và đánh giá định kỳ**, chứ không được bỏ quên dưới nhãn “tạm”.

## 2. Ngoại lệ là gì, và khi nào một quyền lâu dài là hợp lệ?

### 2.1. Phân biệt các loại quyền

| Loại | Bản chất | Cách quản lý phù hợp |
| --- | --- | --- |
| **Quy tắc baseline** | Luồng hoặc kiểm soát được kiến trúc, chính sách và chủ dịch vụ phê duyệt như nhu cầu thường xuyên | Có owner, phạm vi tối thiểu, phiên bản cấu hình, kiểm thử và tái xác nhận theo kỳ |
| **Ngoại lệ truy cập tạm thời** | Quyền vượt baseline để hỗ trợ sự cố, triển khai, bảo trì, migration hoặc kiểm thử đã được duyệt | Có thời gian bắt đầu và **hết hạn**, điều kiện dừng, log, kế hoạch thu hồi |
| **Ngoại lệ rủi ro** | Sự không tuân thủ một yêu cầu bảo mật do giới hạn công nghệ/nghiệp vụ | Đánh giá rủi ro, người có thẩm quyền chấp nhận, biện pháp bù trừ và **hạn tái phê duyệt hoặc xử lý** |
| **Ngoại lệ khẩn cấp** | Quyền được cấp trong sự cố theo quy trình khẩn | Phê duyệt khẩn, scope rất hẹp, TTL ngắn, ghi audit, hậu kiểm bắt buộc |
| **Bỏ qua kiểm soát** | Tắt hoặc giảm hiệu lực một cơ chế như IDS/IPS, TLS inspection, DNS filtering, NAC posture | Chỉ khi thật sự cần, có phê duyệt rủi ro riêng, giới hạn đối tượng và ưu tiên phục hồi kiểm soát |

Không phải mọi rule có tuổi thọ dài đều là sai. Ví dụ, backend ứng dụng được truy cập cơ sở dữ liệu qua một cổng cố định nhiều năm có thể là **quyền nghiệp vụ lâu dài hợp lệ**. Nhưng rule vẫn cần chủ sở hữu, phạm vi, nhật ký, kiểm thử và kỳ rà soát vì hệ thống, địa chỉ hoặc dữ liệu có thể thay đổi.

Hai mốc thời gian quan trọng nhưng khác nhau:

- **Expires at (hết hiệu lực):** thời điểm quyền tạm thời phải được gỡ hoặc vô hiệu theo chính sách, có thể cần quy trình thay đổi được điều phối.
- **Review due at (hạn đánh giá lại):** thời điểm người có trách nhiệm phải chứng minh quyền vẫn cần thiết và còn phù hợp; không mặc nhiên đồng nghĩa tự động ngắt dịch vụ vào đúng giờ đó.

Với ngoại lệ tạm thời, thường cần **cả TTL và người chịu trách nhiệm thu hồi**. Với ngoại lệ rủi ro kéo dài do giới hạn legacy, cần ngày tái phê duyệt và kế hoạch chấm dứt hoặc thay thế. **Không có ngày hết hạn tự động** không nên được đồng nhất với “không cần giám sát”; chính sách phải nêu rõ trường hợp nào được chấp nhận hình thức review thay expiry.

### 2.2. Ngoại lệ có thể xuất hiện ở đâu?

| Lớp kiểm soát | Ví dụ ngoại lệ thiếu kiểm soát | Hậu quả có thể xảy ra |
| --- | --- | --- |
| Firewall/ACL | Cho cả VLAN người dùng tới VLAN DATA, mở `any service` | Phá ranh giới phân đoạn, mở rộng di chuyển ngang |
| VPN/ZTNA | Nhóm người dùng thử nghiệm được quyền vào toàn subnet nội bộ sau khi dự án kết thúc | Đặc quyền tích tụ theo thời gian |
| IDS/IPS/NDR | Bypass kiểm tra một dải mạng hoặc vô hiệu signature vì false positive | Mất khả năng phát hiện/ngăn chặn trong một vùng |
| DNS/proxy | Allowlist domain/wildcard quá rộng, bỏ lọc DNS theo chính sách | Giảm kiểm soát egress hoặc truy cập tên miền |
| Wi-Fi/NAC | Cho thiết bị ngoại lệ bỏ qua posture hoặc cách ly guest | Thiết bị không đáp ứng baseline được kết nối lâu dài |
| Cloud | Security group egress `0.0.0.0/0` hoặc `::/0`, rule quá rộng trong NACL/cloud firewall | Đường kết nối ngoài dự kiến, kể cả giữa tenant/region |
| Mạng quản trị | Tạm cho IP của nhà cung cấp vào SSH/HTTPS/SNMP rồi quên thu hồi | Mở rộng bề mặt quản trị đặc quyền |
| Chính sách TLS | Bỏ kiểm tra chứng thư hoặc tạo trust exception không có kỳ rà soát | Tăng rủi ro giả mạo/giảm tính xác thực khi kết nối |

Một ngoại lệ ở **lớp định danh** có thể phối hợp với ngoại lệ ở **lớp mạng** để tạo đường bypass lớn hơn từng ngoại lệ đơn lẻ. Vì vậy kiểm kê cần nhìn theo **đường truy cập end-to-end**, không chỉ danh sách rule trong một firewall.

## 3. Vì sao ngoại lệ không có thời hạn nguy hiểm?

### 3.1. Access creep và rule sprawl

**Access creep** là quá trình quyền truy cập được bổ sung liên tục nhưng ít khi thu hẹp. **Rule sprawl** là tình trạng nhiều policy, object group và ngoại lệ chồng lấn làm cho việc hiểu hiệu lực thực tế khó khăn. Hai hiện tượng thường đi cùng nhau:

1. Một luồng hợp lệ bị chặn do thiếu policy hoặc cấu hình sai.
2. Để khôi phục nhanh, người xử lý tạo rule rộng hơn yêu cầu.
3. Không có thời điểm thu hồi; ticket được đóng khi ứng dụng chạy lại.
4. Sau một thời gian, ứng dụng đổi kiến trúc hoặc đổi chủ, rule vẫn tồn tại.
5. Người sau ngại xóa vì không biết ai phụ thuộc; rule được xem như “cấu hình mặc định”.
6. Những ngoại lệ mới lại được mở vì dựa trên trạng thái cũ không rõ ràng.

Kết quả không chỉ tăng số lượng rule mà còn giảm khả năng **dự đoán đường truy cập, xác minh default deny và giải thích nguyên nhân khi có sự cố**.

### 3.2. Các hình thức lỗi chính

| Mẫu lỗi | Tác động | Tín hiệu nhận biết |
| --- | --- | --- |
| **Mở quá rộng** | Host không được ủy quyền thừa hưởng quyền | Source/destination `any`, CIDR lớn, mọi port, nhóm động không có kiểm soát thành viên |
| **Không có owner** | Không ai có thẩm quyền khẳng định quyền còn cần | Ticket cũ, team giải thể, service đổi chủ |
| **Không có hạn** | Ngoại lệ khẩn thành chính sách lâu dài | Expiry và review date rỗng; không có nhắc hạn |
| **Không có bằng chứng** | Khó chứng minh rule hoạt động đúng hoặc được sử dụng | Thiếu flow/rule logs, không có positive/negative tests |
| **Rule bị che hoặc chồng lấn** | Khó biết rule nào cho phép traffic | Overlapping/shadowed rules, thứ tự xử lý không rõ |
| **Một chiều nhưng thiếu xét trạng thái** | Đánh giá sai khi thu hồi | Firewall stateful giữ phiên, ACL stateless cần kiểm tra chiều trả lời |
| **Khác biệt nhiều môi trường** | Rule đã gỡ ở site này vẫn còn ở site khác | HA/controller drift, cloud region, IPv6, IaC và runtime khác nhau |
| **Ngoại lệ làm tắt giám sát** | Không thấy hoạt động bất thường | IDS/IPS bypass, tắt log deny, mất nguồn telemetry |

Một rule đã được duyệt từ lâu **không chứng minh nó còn phù hợp hôm nay**. Việc một rule chưa từng tạo incident cũng không chứng minh rủi ro bằng không.

### 3.3. Ví dụ chuỗi rủi ro

~~~mermaid
flowchart LR
    A["Lỗi kết nối trong ca bảo trì"] --> B["Allow rộng cho khôi phục nhanh"]
    B --> C["Không có expiry / owner"]
    C --> D["Ứng dụng thay đổi, quyền vẫn còn"]
    D --> E["Quyền xuyên vùng rộng hơn nhu cầu"]
    E --> F["Default deny khó chứng minh"]
    F --> G["Khó phát hiện và thu hồi an toàn"]
~~~

Sơ đồ mô tả **chuỗi rủi ro**, không phải khẳng định mọi ngoại lệ đều bị khai thác. Ý nghĩa vận hành là mỗi bước thiếu kiểm soát làm tăng mức không chắc chắn và chi phí khắc phục về sau.

## 4. Tìm nguyên nhân gốc thay vì chỉ xóa rule

Nếu một tổ chức có hàng trăm ngoại lệ không thời hạn, nguyên nhân thường không chỉ là “kỹ sư quên”. Cần kiểm tra hệ thống quản trị:

- **Quy trình cấp ngoại lệ:** biểu mẫu có bắt buộc scope, lý do, owner và TTL không? Có phân biệt emergency change với change chuẩn không?
- **Nguồn sự thật:** ngoại lệ nằm trong CMDB, firewall manager, Git/IaC, ticket hay bảng tính rời? Có mã ID liên kết giữa hệ thống không?
- **Quyền phê duyệt:** có người thẩm định rủi ro độc lập với người triển khai hoặc phân tách trách nhiệm phù hợp không?
- **Thông tin phụ thuộc:** đội ứng dụng có flow matrix và bản đồ dịch vụ không, hay chỉ biết “mở tạm mọi cổng cho chắc”?
- **Công cụ:** nền tảng hỗ trợ lịch hết hạn, API thu hồi, policy review, object ownership và log hit không?
- **Động lực vận hành:** KPI chỉ đo thời gian sửa lỗi, không đo nợ ngoại lệ hay hiệu lực default deny?
- **Hậu kiểm:** sau incident/change có bước xóa điều kiện tạm, thử lại và cập nhật sơ đồ không?

**Năm câu hỏi “vì sao” minh họa:**

1. Vì sao VLAN APP vẫn được truy cập trực tiếp DATA qua SSH? → Một rule tạm thời chưa bị gỡ.
2. Vì sao rule chưa bị gỡ? → Ticket chỉ đánh dấu “ứng dụng hoạt động”.
3. Vì sao ticket không yêu cầu gỡ rule? → Biểu mẫu không có trường expiry hoặc review.
4. Vì sao thiếu trường đó? → Quy trình change chưa phân biệt quyền tạm và baseline.
5. Vì sao chưa phân biệt? → Không có owner chịu trách nhiệm vòng đời ngoại lệ.

Khắc phục bền vững phải giải quyết **quy trình và nguồn dữ liệu**, không chỉ sửa một rule đang nhìn thấy.

## 5. Thiết kế chính sách ngoại lệ tối thiểu

Một ngoại lệ chỉ nên được cấp khi có nhu cầu hợp lệ, có giới hạn đo được, và không thể giải quyết tốt hơn bằng cấu hình baseline hoặc thay đổi ứng dụng.

### 5.1. Trường dữ liệu bắt buộc

| Trường | Ý nghĩa và câu hỏi kiểm chứng |
| --- | --- |
| **Exception ID / Rule ID / Change ID** | Liên kết yêu cầu, quyết định và cấu hình đang chạy |
| **Exception type** | Tạm thời, khẩn cấp, rủi ro chưa thể xử lý hoặc baseline dài hạn |
| **Business reason** | Dịch vụ, công việc hoặc tình huống nào thực sự cần ngoại lệ? |
| **Requestor / service owner** | Ai yêu cầu và ai chịu trách nhiệm nghiệp vụ? |
| **Security approver / implementation owner** | Ai thẩm định rủi ro và ai có quyền triển khai/thu hồi? |
| **Source / destination** | Host, subnet, zone, identity hoặc nhóm workload chính xác |
| **Protocol / service / direction** | Giao thức, cổng, chiều, điểm kiểm soát và điều kiện áp dụng |
| **Effective from / expires at** | Thời gian bắt đầu và hết hiệu lực với quyền tạm thời |
| **Review due at** | Ngày bắt buộc tái xác nhận nếu quyền cần tồn tại dài hạn |
| **Risk / compensating controls** | Hệ quả của quyền mở rộng và kiểm soát giảm thiểu tạm |
| **Monitoring / evidence** | Log, rule hit, luồng hợp lệ và kiểm thử chặn ngoài phạm vi |
| **Rollback / revoke plan** | Cách thu hồi an toàn, người thực hiện, kiểm tra phiên đã mở |
| **Status / last verified** | Proposed, approved, active, expired, revoked... và ngày xác minh |

**Ngày hết hạn và ngày review không thay thế lẫn nhau.** Một ngoại lệ khẩn cần thời điểm chấm dứt; một quyền lâu dài đã chuẩn hóa cần đánh giá lại theo chu kỳ, và một waiver rủi ro cần người có thẩm quyền tái chấp nhận trước khi kỳ hiện tại kết thúc.

### 5.2. Mẫu exception record có thời hạn

Ví dụ sau dùng **địa chỉ dành cho tài liệu** và bản ghi hoàn toàn giả lập. Đây là schema mô tả, **không phải cú pháp cấu hình của firewall**.

~~~yaml
exception_id: EXC-NET-2026-012
type: temporary_access
status: approved
business_reason: "Backup migration trong cửa sổ đã phê duyệt"
requestor_team: data-platform
service_owner: database-platform
security_approver: security-architecture
implementation_owner: network-operations
change_id: CHG-NET-2026-212
scope:
  from_zone: backup
  to_zone: data
  source: "192.0.2.25/32"
  destination: "198.51.100.10/32"
  protocol: tcp
  destination_port: 5432
  direction: backup_to_database
  allowed_identity: "approved-backup-service"
effective_from: "2026-11-28T22:00:00+07:00"
expires_at: "2026-11-29T02:00:00+07:00"
review_due_at: "2026-11-29T02:00:00+07:00"
compensating_controls:
  - "application authentication required"
  - "TLS required for database connection"
  - "flow and database access logs retained"
verification:
  positive_test: "approved backup host reaches DB service"
  negative_tests:
    - "another backup host is denied"
    - "approved host cannot access database SSH"
    - "new connection is denied after revocation"
  last_verified_at: null
revocation:
  owner: network-operations
  method: "remove rule through approved change; check existing sessions"
  evidence_required: true
~~~

**Cảnh báo diễn giải:** Firewall L3/L4 thường thực thi IP/cổng/zone chứ không trực tiếp hiểu `allowed_identity` hoặc `TLS required`. Các trường đó cần được kiểm chứng ở những lớp hỗ trợ tương ứng (IAM, ứng dụng, database, ZTNA...). IP ví dụ thuộc các dải tài liệu `192.0.2.0/24` và `198.51.100.0/24`.

Không lưu mật khẩu, token còn hiệu lực hay khóa riêng trong record ngoại lệ. Nếu cần quyền quản trị để triển khai, dùng IAM và secret manager có audit phù hợp.

## 6. Quy trình duyệt ngoại lệ có kiểm soát

### 6.1. Các bước bắt buộc

~~~mermaid
flowchart TD
    A["Yêu cầu mở quyền"] --> B["Định rõ nhu cầu + scope"]
    B --> C{"Có cách sửa baseline/ứng dụng?"}
    C -->|"Có"| D["Ưu tiên sửa nguyên nhân"]
    C -->|"Chưa"| E["Đánh giá rủi ro và biện pháp bù trừ"]
    E --> F["Phê duyệt owner + Security"]
    F --> G["Đặt TTL, review, rule ID, kế hoạch rollback"]
    G --> H["Triển khai và kiểm thử dương/âm"]
    H --> I["Theo dõi hit/log và nhắc hạn"]
    I --> J{"Hết nhu cầu hoặc hết hạn?"}
    J -->|"Không"| K["Tái đánh giá theo lịch"]
    K --> I
    J -->|"Có"| L["Thu hồi an toàn + kiểm chứng"]
    L --> M["Đóng record với bằng chứng"]
~~~

Các điểm cần kiểm soát:

1. **Yêu cầu:** chủ dịch vụ nêu luồng cụ thể, thời gian, nhu cầu và lý do giải pháp chuẩn chưa đáp ứng.
2. **Thẩm định:** nhóm bảo mật xem trust boundary, phân đoạn, dữ liệu, identity, đường quản trị và mức phơi lộ.
3. **Phê duyệt:** theo ma trận rủi ro. Người thực hiện thay đổi không tự đóng vai người duyệt rủi ro cao, trừ trường hợp quy trình tổ chức đã có kiểm soát tương đương.
4. **Triển khai:** rule hẹp nhất có thể, có ID, thứ tự, zone/interface, object, IPv4/IPv6, NAT và đường HA.
5. **Kiểm chứng:** test luồng được phép **và** luồng ngoài phạm vi, thu chứng cứ từ endpoint lẫn điểm thực thi.
6. **Theo dõi:** log, hit, tác động nghiệp vụ, thay đổi membership của group, giờ hết hạn và trạng thái telemetry.
7. **Thu hồi hoặc gia hạn:** trước khi hết hạn phải có quyết định mới; không để “quá hạn nhưng vẫn active” thành trạng thái bình thường.
8. **Hậu kiểm:** lưu bằng chứng phiên mới bị chặn sau thu hồi, xóa credentials và object tạm nếu thích hợp, cập nhật inventory và runbook.

### 6.2. Ngoại lệ khẩn cấp không đồng nghĩa miễn quy trình

Khi cần khôi phục dịch vụ, quy trình **emergency change** có thể rút gọn bước xét duyệt ban đầu theo cơ chế đã xác lập, nhưng vẫn cần:

- Phạm vi hẹp, thời điểm hết hạn/ngưỡng dừng và người thực hiện cụ thể.
- Kênh liên lạc tới incident commander/owner có thẩm quyền.
- Ghi audit về người, thời gian, policy trước/sau và nguyên nhân.
- Kiểm thử tối thiểu để bảo đảm không mở đường trái yêu cầu.
- **Post-implementation review** và quyết định gỡ/giữ có phê duyệt trong khoảng thời gian đã định.

Không dùng tính khẩn cấp để mở cổng quản trị hoặc tắt IDS/IPS trên phạm vi lớn mà không xem xét tác động. Nếu phải chấp nhận giảm kiểm soát, cần ghi risk acceptance và giám sát bù trừ.

## 7. Kiểm tra ngoại lệ có thực sự đủ hẹp không?

### 7.1. Kiểm thử dương và âm

**Positive test** trả lời: luồng nghiệp vụ được phép có hoạt động đúng không? **Negative test** trả lời: những luồng tương tự nhưng **không nằm trong quyền** có bị chặn không?

Giả sử chính sách giả lập: chỉ host backup `192.0.2.25` được kết nối DB `198.51.100.10` qua TCP/5432 trong thời gian bảo trì. Ma trận:

| Test ID | Nguồn | Đích | Giao thức/cổng | Kỳ vọng |
| --- | --- | --- | --- | --- |
| P1 | 192.0.2.25 | 198.51.100.10 | TCP/5432 | **Allow trong thời hạn** và xác thực DB thành công |
| N1 | 192.0.2.26 | 198.51.100.10 | TCP/5432 | **Deny**: host cùng subnet không thừa hưởng quyền |
| N2 | 192.0.2.25 | 198.51.100.10 | TCP/22 | **Deny**: không mở SSH |
| N3 | 192.0.2.25 | 198.51.100.11 | TCP/5432 | **Deny**: không mở DB khác |
| N4 | Vùng USER không được phê duyệt | 198.51.100.10 | TCP/5432 | **Deny**: không bypass phân đoạn |
| N5 | 192.0.2.25 | 198.51.100.10 | TCP/5432, **phiên mới sau expiry** | **Deny**: thu hồi thực sự có hiệu lực |

Kết quả **“timeout” không tự chứng minh default deny**: đích có thể không chạy dịch vụ, host firewall chặn hoặc routing lỗi. Cần xác định đúng nơi chặn bằng log/rule hit, flow telemetry, packet capture được phê duyệt và kết quả tại host.

### 7.2. Những biến thể hay bị bỏ sót

| Biến thể | Vì sao cần kiểm tra |
| --- | --- |
| **IPv4 và IPv6** | Rule v4 hẹp nhưng đường v6 vẫn mở hoặc còn bypass |
| **NAT trước/sau policy** | IP log có thể khác IP gốc; sai nhận diện nguồn/đích |
| **Stateful session** | Phiên đã được phép trước khi thu hồi có thể tiếp tục tồn tại tùy nền tảng |
| **HA và failover** | Node dự phòng có thể nhận policy chậm hoặc khác cấu hình |
| **Object groups** | Thêm một host vào group có thể vô tình mở quyền tới nhiều nơi |
| **VPN/ZTNA identity** | Đúng subnet nhưng sai user/device posture vẫn phải bị từ chối nếu policy yêu cầu |
| **Cloud IAM / security groups** | Quyền thay đổi ở account/region khác; selector hoặc tag không còn đúng |
| **DNS/proxy** | FQDN có thể phân giải tới đích khác; wildcard có thể cho phép phạm vi rộng |
| **Logging** | Policy có hiệu lực nhưng thiếu log khiến audit và phát hiện khó khăn |

**Một rule “allow đúng cổng” chưa đủ nếu nguồn là cả subnet**. Người kiểm thử phải thay đổi từng thuộc tính (nguồn, đích, port, identity, time) để chứng minh quyền **không lan sang những trường hợp ngoài nhu cầu**.

## 8. Thu hồi ngoại lệ mà không làm gián đoạn ngoài kế hoạch

### 8.1. Tại sao không nên chỉ xóa rule ngay?

Một ngoại lệ cũ có thể vẫn đang phục vụ backup hằng tháng, hệ thống thanh toán theo kỳ hoặc một ứng dụng không được kiểm kê. Đánh dấu “expired” là **tín hiệu cần xử lý** nhưng thu hồi phải có **kế hoạch và bằng chứng**. Nếu tự động gỡ rule khi hết giờ mà không có cơ chế phối hợp, hệ thống có thể gián đoạn; nếu vì sợ gián đoạn mà không bao giờ gỡ, ngoại lệ trở thành lỗ hổng lâu dài.

Giải pháp là kết hợp **cơ chế hết hạn mặc định**, nhắc trước hạn và **quy trình escalation cho những trường hợp cần gia hạn**. Mức tự động hóa tùy độ quan trọng của dịch vụ và tính năng platform.

### 8.2. Quy trình thu hồi có kiểm soát

1. **Xác định đúng đối tượng:** exception ID, rule ID, vị trí, thứ tự, zone, object/group và các policy phụ thuộc.
2. **Xác minh nhu cầu:** liên hệ owner, kiểm tra lịch nghiệp vụ, traffic/flow logs, hit counter và ticket; không kết luận từ “0 hit” duy nhất.
3. **Phân tích đường đi:** firewall, NAT, IPv6, VPN, cloud, host policy, HA, các đường dự phòng.
4. **Lập thay đổi:** kiểm tra tác động, chọn cửa sổ và phương án quay về **cấu hình an toàn đã biết**.
5. **Thu hồi có giám sát:** xóa/disable quyền chính xác qua quy trình, bảo đảm cấu hình đã commit và triển khai ở mọi node liên quan.
6. **Kiểm chứng:** positive tests cho luồng baseline và **negative tests cho kết nối mới** vốn được ngoại lệ cho phép.
7. **Xử lý phiên hiện có:** đánh giá session table của firewall stateful. Có thể cần thu hồi session theo tài liệu hãng và quy trình thay đổi, tránh làm gián đoạn ngoài ý muốn.
8. **Đóng hồ sơ:** lưu log, người xác nhận, thời gian, kết quả kiểm thử, quyết định về object/credential phụ và trách nhiệm theo dõi.

**Hết hạn rule và chấm dứt mọi kết nối không phải cùng một sự kiện.** Với firewall stateful, gỡ rule có thể chỉ chặn **phiên mới**, trong khi phiên cũ tiếp tục đến khi timeout hoặc bị thu hồi theo cơ chế nền tảng. Cần mô tả yêu cầu cụ thể: “không cho bắt đầu phiên mới” hay “chấm dứt mọi quyền truy cập”, rồi thử đúng điều kiện.

### 8.3. Điều kiện dừng/rollback

- Ứng dụng hợp lệ ngoài phạm vi thay đổi bắt đầu lỗi.
- Cơ chế cứu hộ/bastion hoặc quản trị từ xa không còn hoạt động.
- Flow giám sát quan trọng bị mất và không đủ bằng chứng để biết chính sách đang chạy.
- Phát hiện rule chồng lấn hoặc NAT làm kết quả khác kế hoạch.
- Phiên lâu dài có dữ liệu nghiệp vụ quan trọng có nguy cơ bị ngắt không được phê duyệt.

Rollback phải khôi phục **trạng thái an toàn đã kiểm chứng** hoặc đưa ra biện pháp thay thế có phê duyệt; không dùng `allow any any` như cách khôi phục mặc định.

## 9. Kiểm toán kho ngoại lệ tồn đọng

Khi đã tồn tại nhiều ngoại lệ thiếu hạn, nên xử lý như **một chương trình giảm nợ quyền truy cập**, thay vì giao kỹ thuật viên xóa ngẫu nhiên.

### 9.1. Bước kiểm toán

1. **Hợp nhất nguồn dữ liệu:** firewall manager, cloud security groups, SD-WAN/controller, VPN/ZTNA policies, DNS/proxy allowlist, bypass IDS/IPS, NAC và tickets.
2. **Chuẩn hóa định danh:** mỗi ngoại lệ có một ID ổn định; liên kết asset, app, owner và các rule thực thi, kể cả node HA/site/region.
3. **Phân loại:** baseline đã phê duyệt, ngoại lệ tạm, ngoại lệ rủi ro/legacy, ngoại lệ khẩn, rule không xác định.
4. **Đánh dấu nguy cơ:** thiếu owner, thiếu expiry/review, phạm vi quá rộng, đích nhạy cảm, đường quản trị, mạng khách/Internet, không có logging, trùng/chồng lấn.
5. **Xác minh sử dụng:** đối chiếu flow logs, change records và người dùng, kể cả chu kỳ nghiệp vụ hiếm; lưu độ tin cậy kết luận.
6. **Ưu tiên xử lý:** bắt đầu từ các ngoại lệ có mức phơi lộ cao và dễ thu hẹp, không chỉ các rule có tuổi lớn.
7. **Giảm phạm vi hoặc thu hồi:** theo change management, có test trước/sau và owner xác nhận.
8. **Chặn tái phát:** sửa request form, policy-as-code, approval gates, nhắc hạn, audit và dashboard.

### 9.2. Ma trận ưu tiên

| Tình huống | Mức ưu tiên định hướng | Quyết định ban đầu |
| --- | --- | --- |
| Internet/VPN user được truy cập management plane quá rộng | **Rất cao** | Hạn chế nguồn, xác thực, điều tra và có phương án thu hồi |
| Guest Wi-Fi có đường tới vùng nội bộ | **Rất cao** | Xác minh trust boundary, isolate và test đường cấm |
| Bypass IDS/IPS của vùng nhạy cảm không có owner | **Cao** | Khôi phục quan sát/giảm bypass, đánh giá false positive và rủi ro |
| Rule từ subnet APP tới DATA trên mọi cổng | **Cao** | Xác minh luồng cần, thu về host/service tối thiểu |
| Ngoại lệ backup có hạn đã qua nhưng vẫn có owner và job theo lịch | **Cần xử lý sớm** | Liên hệ owner và lịch job, quyết định gia hạn hoặc thu hồi có kiểm soát |
| Rule nội bộ hẹp, có owner, review định kỳ, phụ thuộc ổn định | **Theo chu kỳ** | Tái xác nhận và cân nhắc chuyển thành baseline |
| Rule 0 hits nhưng chỉ chạy backup hằng quý | **Chưa đủ bằng chứng** | Xem log dài hơn và xác nhận chu kỳ trước khi xóa |

Ưu tiên cần tính **mức phơi lộ, độ nhạy tài sản, phạm vi quyền, điểm thiếu kiểm soát, khả năng khai thác, tác động nghiệp vụ và độ chắc chắn của dữ liệu**. Tuổi đời rule là một tín hiệu, nhưng không nên là yếu tố quyết định duy nhất.

## 10. Tự động phát hiện nợ ngoại lệ bằng báo cáo chỉ đọc

Tự động hóa nên tập trung phát hiện **ngoại lệ bất thường và đã quá hạn**, tạo ticket và yêu cầu người có thẩm quyền xử lý. Không nên bắt đầu bằng một chương trình tự xóa mọi rule sau một số ngày cố định vì việc đó có thể làm gián đoạn dịch vụ và bỏ qua các điểm thực thi phụ thuộc.

### 10.1. Schema CSV mẫu

File mẫu hoàn toàn giả lập:

~~~csv
exception_id,type,status,owner,source,destination,protocol,port,created_at,expires_at,review_due_at
EXC-001,temporary,active,NetOps,192.0.2.25/32,198.51.100.10/32,tcp,5432,2026-11-27T09:00:00+07:00,2026-11-28T08:00:00+07:00,2026-11-28T08:00:00+07:00
EXC-002,temporary,active,NetOps,any,198.51.100.10/32,tcp,any,2026-11-20T09:00:00+07:00,,
EXC-003,standing,active,SecOps,192.0.2.30/32,198.51.100.20/32,tcp,443,2026-01-01T09:00:00+07:00,,2026-12-31T17:00:00+07:00
EXC-004,standing,active,,192.0.2.40/32,198.51.100.30/32,tcp,22,2025-12-01T09:00:00+07:00,,
~~~

**Nguyên tắc phân loại:** `temporary` phải có `expires_at`; `standing` phải có `review_due_at`; mọi record đang active cần owner và scope. Một quyền đứng lâu nhưng không có owner/review phải được điều tra, không ngầm coi là baseline hợp lệ.

### 10.2. Python chuẩn thư viện để rà soát CSV

Đoạn code chỉ **đọc dữ liệu và in ra cảnh báo**; không kết nối thiết bị, không cập nhật firewall hoặc tự thu hồi rule. Kỳ đánh giá cố định là **28/11/2026 theo UTC** để ví dụ có thể tái lập.

~~~python
import csv
from datetime import datetime, timezone

AS_OF = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
REQUIRED = {
    "exception_id", "type", "status", "owner",
    "source", "destination", "protocol", "port",
    "created_at", "expires_at", "review_due_at"
}
BROAD = {"any", "*", "0.0.0.0/0", "::/0", "0-65535"}

def parse_timestamp(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid ISO-8601 timestamp")
    if result.tzinfo is None:
        raise ValueError("Missing timezone")
    return result.astimezone(timezone.utc)

def audit_exceptions(csv_path):
    seen = set()
    with open(csv_path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Missing columns: " + ", ".join(sorted(missing)))

        for row in reader:
            # Ví dụ chỉ xem các ngoại lệ đang active.
            if (row["status"] or "").strip().lower() != "active":
                continue

            exception_id = (row["exception_id"] or "").strip()
            category = (row["type"] or "").strip().lower()
            findings = []

            if not exception_id:
                findings.append("missing_id")
            elif exception_id in seen:
                findings.append("duplicate_id")
            else:
                seen.add(exception_id)

            if not (row["owner"] or "").strip():
                findings.append("missing_owner")
            if category not in {"temporary", "standing"}:
                findings.append("unknown_exception_type")

            for field in ("source", "destination", "protocol", "port"):
                value = (row[field] or "").strip().lower()
                if not value:
                    findings.append("missing_" + field)
                elif value in BROAD:
                    findings.append("broad_" + field)

            dates = {}
            for field in ("created_at", "expires_at", "review_due_at"):
                try:
                    dates[field] = parse_timestamp(row[field])
                except ValueError:
                    dates[field] = None
                    findings.append("invalid_" + field)

            expiry = dates["expires_at"]
            review = dates["review_due_at"]
            if category == "temporary":
                if expiry is None and "invalid_expires_at" not in findings:
                    findings.append("missing_expiry")
                elif expiry is not None and expiry <= AS_OF:
                    findings.append("expired_still_active")
            elif category == "standing":
                if review is None and "invalid_review_due_at" not in findings:
                    findings.append("missing_review_date")
                elif review is not None and review <= AS_OF:
                    findings.append("overdue_review")

            if findings:
                print(exception_id or "<missing>", " | ".join(findings))

audit_exceptions("network_exceptions.csv")
~~~

**Kết quả dự kiến:** `EXC-001` được đánh dấu hết hạn nhưng vẫn active; `EXC-002` thiếu expiry và có scope quá rộng; `EXC-004` thiếu owner và ngày review; `EXC-003` có ngày review trong tương lai nên không phát sinh cảnh báo từ các điều kiện mẫu.

Đây chỉ là **bộ lọc ban đầu**: không thể suy luận mọi lỗ hổng chồng lấn, độ ưu tiên rule, NAT, object group, semantic của ACL, số liệu hit, phụ thuộc ứng dụng hoặc tác động của việc thu hồi. Khi xây hệ thống thực, cần dữ liệu từ **runtime policy** và hệ thống quản lý thay đổi, xử lý timestamp thiếu/sai, log nguồn, rule shadowing, quan hệ HA/cloud và cơ chế phân loại theo mức rủi ro.

## 11. Tình huống thực hành: ngoại lệ sự cố trở thành đường truy cập lâu dài

### 11.1. Bối cảnh

Một ứng dụng bán hàng chạy trong vùng APP, database ở vùng DATA. Thiết kế chuẩn chỉ cho backend gọi database qua TCP/5432. Trong một đêm bảo trì, nhóm hỗ trợ tạm mở **cả subnet APP tới DATA trên mọi cổng** để tìm nguyên nhân timeout. Sau khi sửa lỗi DNS của ứng dụng, ticket được đóng, nhưng rule vẫn active **nhiều tháng** vì không có expiry.

Trong đợt kiểm toán, nhóm an ninh tìm thấy:

| Phát hiện | Ý nghĩa |
| --- | --- |
| Rule nguồn là toàn subnet APP | Các host không phải backend cũng có thể thừa hưởng quyền |
| Destination là toàn vùng DATA | Có thể mở đường tới nhiều hệ thống nhạy cảm không liên quan |
| Service là `any` | Không giới hạn cổng database như nhu cầu ban đầu |
| Owner chỉ ghi tên nhân viên đã chuyển nhóm | Không có người tái xác nhận |
| Ticket ghi “khắc phục xong”, không có expiry | Không có bước thu hồi sau sự cố |
| Không có test âm sau thay đổi | Chưa có bằng chứng default deny giữa hai vùng hoạt động đúng |

**Vấn đề gốc:** timeout ban đầu do DNS, nhưng ngoại lệ mở rộng lại tồn tại độc lập với nguyên nhân đã sửa. Tổ chức hiện đối mặt với rủi ro đường truy cập không được thiết kế, dù hệ thống vẫn “hoạt động ổn định”.

### 11.2. Cách xử lý đúng

1. **Khóa phạm vi phân tích:** xác định chính xác rule ID, thứ tự, trạng thái runtime trên các firewall/HA node, NAT, IPv6 và cloud/host policy liên quan.
2. **Tìm chủ sở hữu hiện tại:** xác minh dịch vụ APP/DATA, người phê duyệt thay đổi và phụ thuộc qua ứng dụng; không coi nhân viên cũ là owner còn hiệu lực.
3. **Dựng ma trận luồng cần thiết:** backend được phép tới DB trên cổng xác định; những host khác và mọi cổng quản trị phải bị chặn theo baseline.
4. **Thu thập chứng cứ có kiểm soát:** xem flow logs trong chu kỳ đủ dài, đánh dấu các kết nối lạ và so với danh sách thay đổi/nghiệp vụ.
5. **Lập change thu hẹp:** tạo allow tối thiểu trước hoặc thay rule theo thứ tự chính sách đã được kiểm tra, có phương án rollback an toàn.
6. **Kiểm thử dương/âm:** backend ↔ DB đúng luồng hoạt động; host khác, cổng SSH và đường USER → DATA bị từ chối tại đúng điểm thực thi.
7. **Xóa ngoại lệ cũ:** commit/đồng bộ, đánh giá phiên đang tồn tại, quan sát lỗi ứng dụng và lưu chứng cứ.
8. **Ngăn tái diễn:** thêm TTL vào biểu mẫu emergency change, owner service, thông báo sắp hết hạn và kiểm tra sau khắc phục.

### 11.3. Trạng thái trước và sau

~~~text
TRƯỚC
Source: APP subnet
Destination: DATA subnet
Service: any
Owner: unknown
Expiry: none
Validation: unknown

SAU
Source: approved backend host/group
Destination: approved database host/service
Service: TCP/5432 only
Owner: application + network security
Review: scheduled and documented
Validation: positive test PASS + negative tests PASS
Temporary emergency rule: REVOKED, evidence linked
~~~

**Kết luận:** Đích đến không phải “xóa sạch mọi ngoại lệ”, mà là **chứng minh những quyền còn tồn tại đều cần thiết, đủ hẹp và còn người chịu trách nhiệm**.

## 12. Đo nợ ngoại lệ và hiệu quả khắc phục

### 12.1. Các chỉ số hữu ích

| Chỉ số | Cách xác định | Cách hiểu |
| --- | --- | --- |
| **Active exceptions** | Số ngoại lệ thực sự đang có hiệu lực theo runtime | Theo dõi quy mô, không dùng độc lập để kết luận an toàn |
| **Missing expiry rate** | Ngoại lệ tạm thời đang active thiếu `expires_at` / toàn bộ ngoại lệ tạm thời active | Đo kỷ luật thiết kế quyền tạm |
| **Expired active count** | Ngoại lệ đã quá hạn nhưng rule còn hiệu lực | Chỉ báo ưu tiên cần xử lý |
| **Missing owner rate** | Ngoại lệ đang active không có owner hiện tại / tổng ngoại lệ active | Đo rủi ro không người chịu trách nhiệm |
| **Overdue review rate** | Ngoại lệ standing/waiver quá hạn tái xác nhận / tập cần review | Đo kỷ luật xem lại quyền lâu dài |
| **Overly broad exception count** | Rule có source/destination/service vượt phạm vi được chấp thuận | Cần xem cả ngữ cảnh và kết quả kiểm thử |
| **Revocation verification rate** | Ngoại lệ đã thu hồi có test và chứng cứ / số ngoại lệ đã thu hồi cần test | Chứng minh thay đổi có hiệu lực |
| **Policy drift incidents** | Sự khác nhau giữa policy được duyệt và runtime chưa có ngoại lệ hợp lệ | Đo mức mất kiểm soát thay đổi |
| **Exception exposure by criticality** | Ngoại lệ mở tới tài sản nhạy cảm, vùng quản trị, Internet | Giúp sắp thứ tự xử lý theo rủi ro |

Ví dụ, chỉ số:

\[
MissingExpiryRate =
\frac{\text{Active temporary exceptions without expiry}}
{\text{All active temporary exceptions}}\times100\%.
\]

Nếu có **40** ngoại lệ tạm thời đang active, trong đó **12** thiếu thời hạn, tỷ lệ là **30%**. Đây là tín hiệu quy trình cấp quyền thiếu kỷ luật, nhưng chưa đủ để nói 30% lưu lượng đang không an toàn: còn phải xem scope, mức phơi lộ, tài sản bị ảnh hưởng và bằng chứng runtime.

### 12.2. Tránh “đạt KPI” nhưng không giảm rủi ro

- Số ngoại lệ giảm vì đổi nhãn thành “baseline” mà không review → **không phải cải thiện**.
- Hết hạn tự động nhưng sau đó được gia hạn liên tiếp không giải trình → **TTL chỉ là hình thức**.
- Rule đã disable trên firewall chính nhưng vẫn còn trên node dự phòng → **chưa thu hồi đầy đủ**.
- Xóa rule không có hit trong một tuần khi backup chỉ chạy mỗi quý → **gây rủi ro vận hành**.
- Chỉ đo số ticket đóng, không xác nhận negative test sau thu hồi → **chưa chứng minh default deny**.

Dashboard nên thể hiện **số lượng, mức độ rủi ro, tuổi ngoại lệ, owner, chất lượng bằng chứng và tiến độ xử lý**; có drill-down tới exception ID, rule ID, asset, change và ngày review.

## 13. Những hiểu nhầm thường gặp

1. **“Mọi ngoại lệ đều phải xóa ngay khi đến hạn.”** Ngoại lệ tạm phải có quy trình hết hạn, nhưng thu hồi sản xuất cần xét tác động, phiên đang mở và kênh rollback. Trường hợp cần tiếp tục phải được tái phê duyệt minh bạch, không gia hạn ngầm.
2. **“Rule không hết hạn thì chắc chắn là lỗ hổng.”** Quyền nghiệp vụ lâu dài có thể chính đáng; vấn đề là thiếu baseline, owner, review, scope và kiểm chứng.
3. **“Có change ticket là được.”** Ticket không chứng minh policy đang thực thi đúng hoặc vẫn cần sau vài tháng. Cần evidence runtime và vòng đời.
4. **“Có log hit nên không thể xóa.”** Hit có thể đến từ nguồn ngoài mong đợi; phải xác minh người dùng, dịch vụ, chu kỳ và rule path.
5. **“Không có hit nghĩa là không ai cần.”** Log có thể thiếu, counter reset hoặc lưu lượng chỉ phát sinh theo kỳ.
6. **“Hạ tầng nội bộ đủ tin cậy.”** Máy trong mạng nội bộ, VPN hoặc Wi-Fi nhân viên có thể bị chiếm quyền; phải kiểm soát trust boundary.
7. **“Tắt IPS signature để tránh false positive là xong.”** Bypass kéo dài làm giảm quan sát; cần điều chỉnh chính xác, kiểm thử và có hạn xem lại.
8. **“Chỉ cần thu hồi trong Git.”** IaC thay đổi chưa bảo đảm runtime đã apply hoặc các node/region đã đồng bộ.
9. **“Rule hẹp theo IP là hẹp toàn bộ.”** Object group, NAT, FQDN, IPv6, user group hoặc cloud tag có thể thay đổi phạm vi thực.
10. **“Tăng thời hạn lên vô hạn để đỡ phiền.”** Giảm tải hành chính trước mắt nhưng đẩy nợ kiểm soát sang tương lai; cần tối ưu quy trình và phân loại đúng baseline.

## 14. Checklist cho người thiết kế và người kiểm toán

| Câu hỏi kiểm chứng | Đạt / Chưa / Không áp dụng |
| --- | --- |
| Đã phân loại baseline, temporary, emergency và risk waiver rõ ràng? | |
| Ngoại lệ tạm có effective-from, expiry và owner thu hồi? | |
| Quyền lâu dài hoặc waiver có review-by, người có thẩm quyền và tiêu chí gia hạn? | |
| Có exception ID liên kết rule runtime, change ticket, dịch vụ và chủ sở hữu? | |
| Source/destination/protocol/port/zone/identity được giới hạn tối thiểu? | |
| Có rà soát IPv4/IPv6, NAT, HA, cloud, nhóm động và mọi đường phụ liên quan? | |
| Có biện pháp bù trừ cho rủi ro khi tạm giảm IDS/IPS, DNS, NAC hoặc management ACL? | |
| Có kiểm thử dương/âm với bằng chứng tại đúng điểm thực thi? | |
| Có log, owner và giám sát điều kiện còn cần ngoại lệ? | |
| Có nhắc hạn, escalation khi quá hạn và hành vi tự động được phê duyệt? | |
| Khi thu hồi đã xét stateful session, rollback và chức năng nghiệp vụ? | |
| Đã kiểm tra hiệu lực sau thu hồi và cập nhật inventory/runbook? | |
| Dashboard có chỉ số thiếu hạn, quá hạn, không owner, scope rộng và drift? | |
| Có hành động điều tra nguyên nhân gốc để tránh ngoại lệ tương tự tái xuất hiện? | |

## 15. Câu hỏi tự kiểm tra và bài tập

### 15.1. Câu hỏi

1. Khác biệt giữa quyền baseline lâu dài và ngoại lệ tạm thời không có ngày hết hạn là gì?
2. Vì sao một rule cho phép `any source → DATA : any port` làm suy yếu default deny dù không có sự cố được ghi nhận?
3. Hai điều kiện nào cần kiểm tra trước khi kết luận một ngoại lệ “0 hits” có thể xóa?
4. Với firewall stateful, vì sao một kết nối mới bị chặn sau thu hồi chưa đủ chứng minh mọi phiên cũ đã kết thúc?
5. Khi một ngoại lệ IDS/IPS bypass có owner nhưng không có review date, cần xử lý khác gì một rule truy cập temporary?
6. Tại sao expiry của temporary và review của standing permission không nên được dùng như một trường chung?
7. Một rule đã bị xóa khỏi source control nhưng còn active trên node HA dự phòng. Chỉ số nào nên phản ánh tình trạng này?
8. Hãy đưa ra ba negative tests chứng minh ngoại lệ chỉ cho một máy backup tới một database trên một cổng.
9. Nếu 12/40 ngoại lệ tạm thời thiếu expiry, tỷ lệ là bao nhiêu và vì sao không thể suy luôn đó là tỷ lệ thiết bị có lỗ hổng?
10. Khi đội vận hành phản đối thu hồi ngoại lệ vì sợ ảnh hưởng, phải tìm loại chứng cứ nào trước khi quyết định?

### 15.2. Bài tập tình huống

Một công ty có **60 ngoại lệ active** trên firewall và cloud: 15 rule không có owner, 18 ngoại lệ tạm không có expiry, 9 rule chứa `any service`, 7 rule đang active dù đã qua hạn, và một số rule nằm trong nhiều nhóm trên nhiều hệ thống. Các nhóm trên **có thể chồng lấn**, vì vậy không được cộng thành tổng số ngoại lệ lỗi.

Hãy đề xuất:

1. **Ba truy vấn/danh sách ưu tiên** để phát hiện rule phơi lộ management plane hoặc vùng dữ liệu nhạy cảm.
2. Một **lịch làm sạch theo rủi ro** có review owner, xác minh phụ thuộc, thay đổi và kiểm thử.
3. Một **quy trình cấp ngoại lệ mới** bắt buộc owner/scope/expiry hoặc review và có phê duyệt.
4. Hai **chỉ số kết quả** giúp chứng minh việc làm sạch đã giảm rủi ro thực sự, không chỉ giảm số ticket.

**Hướng giải:** ưu tiên các rule mở nguồn không tin cậy vào hệ thống nhạy cảm, thiếu owner và không có log; thu thập evidence để thu hẹp dần; test cả kết nối được phép và bị cấm; triển khai review/nhắc hạn; kiểm tra runtime trên mọi điểm thực thi; đo số ngoại lệ quá hạn còn active và tỷ lệ thu hồi đã **xác minh default deny**, kèm số lượng đường truy cập ngoài policy được loại bỏ.

**Ghi nhớ:** Ngoại lệ là một công cụ vận hành cần thiết, nhưng **ngoại lệ không thời hạn, không người chịu trách nhiệm và không kiểm chứng** sẽ tích tụ thành nợ bảo mật. Mỗi ngoại lệ phải có **lý do, phạm vi tối thiểu, thời hạn hoặc kỳ đánh giá, phê duyệt, log và kế hoạch thu hồi**. Tổ chức chỉ thật sự giảm rủi ro khi các quyền không cần thiết được thu hẹp và **các luồng ngoài chính sách bị chặn trên thực tế**, không phải chỉ khi số rule trên bảng giảm xuống.
