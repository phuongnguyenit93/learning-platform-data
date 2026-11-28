# Kiểm kê rule theo chủ sở hữu

Trong hạ tầng bảo mật mạng, **rule** là một quy tắc quyết định lưu lượng nào được phép, bị chặn, chuyển hướng, ghi log hoặc phải đi qua lớp kiểm soát nhất định. Rule xuất hiện trên firewall, router ACL, security group, network ACL, VPN gateway, proxy, WAF, DNS filtering và các hệ thống phân đoạn mạng. Sau nhiều lần triển khai ứng dụng, mở kết nối đối tác, xử lý sự cố và nâng cấp, tập rule có thể phát triển thành hàng nghìn mục. Nếu không biết **ai chịu trách nhiệm về từng rule, vì sao rule còn cần thiết và ai có quyền xác nhận thay đổi**, hệ thống rất dễ tích lũy quyền truy cập quá rộng, ngoại lệ hết hạn và các đường mạng không còn chủ quản.

**Kiểm kê rule theo chủ sở hữu (rule ownership inventory)** là quy trình tạo và duy trì bản ghi có thể kiểm chứng nối mỗi rule kỹ thuật với **nhu cầu nghiệp vụ, chủ sở hữu dịch vụ hoặc kiểm soát, nhóm vận hành, hồ sơ phê duyệt và chu kỳ rà soát**. Mục tiêu không chỉ là điền một tên vào cột owner; mục tiêu là để một người hoặc nhóm có trách nhiệm thực sự có thể trả lời: “Rule này phục vụ luồng nào? Nếu đóng hoặc siết lại thì ảnh hưởng ai? Quyết định giữ rule được chứng minh bằng gì?”

Bài thuộc chương **Quản trị vận hành mạng an toàn** của module **SECURITY_NETWORK_SECURITY**. Kiểm kê ownership giúp duy trì phân đoạn, firewall, VPN, IDS/IPS, bảo vệ DNS, mạng không dây và hạ tầng cloud trong trạng thái có thể giải trình và được rà soát định kỳ.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt chủ sở hữu nhu cầu truy cập, chủ sở hữu kiểm soát bảo mật, người triển khai và người phê duyệt.
2. Thiết kế bộ trường kiểm kê đủ để truy vết từ rule vật lý đến luồng nghiệp vụ và hồ sơ thay đổi.
3. Thu thập rule ở chế độ chỉ đọc, chuẩn hóa đối tượng, phiên bản chính sách và trạng thái triển khai thực tế.
4. Gán chủ sở hữu bằng bằng chứng từ CMDB, application inventory, ticket, IaC và xác nhận trực tiếp; xử lý trường hợp chưa rõ chủ sở hữu.
5. Nhận diện rule quá rộng, không có lý do, không dùng, trùng lặp, bị che khuất và ngoại lệ quá hạn.
6. Tổ chức chu kỳ attestation, thay đổi/thu hồi có kiểm soát, theo dõi chỉ số và kiểm thử lại đường mạng hợp lệ lẫn đường bị cấm.

## 2. Vì sao kiểm kê rule theo owner quan trọng?

Một firewall có thể thực thi đúng 100% các rule đang cấu hình nhưng **tập rule đó vẫn sai về mặt quản trị**. Ví dụ:

- Rule mở TCP/443 từ mạng đối tác tới hệ thống nội bộ vẫn còn sau khi hợp đồng kết thúc.
- Rule quản trị SSH được mở tạm từ VLAN người dùng, nhưng ticket đã đóng và không ai xác nhận có thể xóa.
- Một nhóm ứng dụng chuyển sang cloud; rule cũ trong datacenter vẫn tồn tại do địa chỉ IP được tái sử dụng.
- Firewall dùng object group có tên “Production-Servers” nhưng nhóm này đã thêm nhiều máy không thuộc dịch vụ ban đầu.
- Rule “any to any” được tạo để xử lý sự cố và dần trở thành một ngoại lệ thường trực.
- Một security group được quản lý bằng Terraform nhưng tài nguyên thực tế có thay đổi thủ công ngoài mã nguồn.

Không có owner đã xác nhận, mọi thay đổi sẽ bị trì hoãn hoặc thực hiện dựa trên phỏng đoán. Kiểm kê tốt hỗ trợ đồng thời **least privilege, kiểm soát thay đổi, đánh giá rủi ro, điều tra sự cố, audit và khả năng thu hồi quyền đã hết nhu cầu**.

### 2.1. Rule owner khác người sửa rule gần nhất

Người tạo hoặc sửa rule trong log thường là **người vận hành triển khai**. Họ có thể không biết ứng dụng phụ thuộc vào luồng đó, giá trị nghiệp vụ của luồng hoặc hậu quả khi chặn. Vì vậy:

| Khái niệm | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| Business / application owner | Xác nhận nhu cầu kết nối, mức độ quan trọng và thời hạn sử dụng | Nhóm phụ trách hệ thống thanh toán |
| Technical service owner | Hiểu luồng kỹ thuật, phụ thuộc ứng dụng và phương án kiểm thử | Nhóm vận hành ứng dụng thanh toán |
| Policy / control owner | Chịu trách nhiệm chuẩn chính sách bảo mật và ngoại lệ | Nhóm Network Security |
| Implementer / operator | Thực hiện cấu hình, giám sát và khôi phục thay đổi | Kỹ sư firewall hoặc Cloud Platform |
| Approver / risk owner | Phê duyệt theo quyền hạn hoặc chấp nhận rủi ro còn lại | Chủ hệ thống hoặc người phụ trách an ninh |
| Reviewer / auditor | Kiểm chứng bằng chứng, hiệu lực và kết quả rà soát | Nhóm Security Governance |

Một tổ chức nhỏ có thể kết hợp một số vai trò, nhưng phải ghi rõ **vai trò của người đó trong từng quyết định**. Người triển khai không tự động trở thành người có quyền chấp nhận rủi ro của mọi rule mình từng tạo.

### 2.2. Định nghĩa “chủ sở hữu được xác minh”

Owner hợp lệ cần có:

1. **Danh tính nhóm hoặc vai trò có trách nhiệm** còn hoạt động trong tổ chức; ưu tiên nhóm/đội thay vì chỉ một cá nhân dễ thay đổi vị trí.
2. **Mối liên hệ có bằng chứng** với ứng dụng, dịch vụ, phân đoạn, baseline hoặc ngoại lệ mà rule phục vụ.
3. **Thẩm quyền trả lời** các câu hỏi về việc giữ, thu hẹp, thay thế hoặc thu hồi rule.
4. **Đầu mối thay thế/escalation** khi nhóm thay đổi hoặc chủ sở hữu không phản hồi.
5. **Lần xác nhận gần nhất**, người xác nhận và ngày dự kiến xem xét lại.

Một chuỗi tự do trong comment, chẳng hạn “Owner: Team A”, **chưa đủ** nếu Team A đã giải thể hoặc không còn quản lý dịch vụ. Owner phải được đối soát với nguồn tổ chức và có thể yêu cầu attestation định kỳ.

## 3. Xác định phạm vi rule cần kiểm kê

Phạm vi bắt đầu từ **ranh giới mạng và hệ thống kiểm soát truy cập đang vận hành**, thay vì chỉ một firewall trung tâm.

| Hệ thống | Đối tượng rule cần lấy | Lưu ý khi xác định owner |
| --- | --- | --- |
| Network firewall / NGFW | Security policy, zone rules, NAT liên quan, schedule, application/service object | Phân biệt luồng nghiệp vụ và baseline chặn theo chính sách |
| Router / switch ACL | ACL vào/ra interface, control-plane access, management ACL | Có thể phục vụ cả kết nối ứng dụng và bảo vệ thiết bị |
| Cloud security group | Inbound/outbound permissions trên VM, workload hoặc ENI | Rule có thể chia sẻ cho nhiều tài nguyên và nhiều chủ dịch vụ |
| Cloud network ACL | Quy tắc subnet ở ingress/egress | NACL thường xét theo thứ tự và không duy trì state như security group |
| VPN / remote access | Policy nguồn/đích, nhóm người dùng, split/full tunnel, site-to-site selectors | Owner của đối tác và chủ dịch vụ được kết nối có thể khác nhau |
| WAF / proxy / SWG | Allow/deny, bypass, exception, URL/category, application policy | Cần gắn owner cho ứng dụng hoặc lý do ngoại lệ |
| DNS firewall/filtering | Domain/category allow/deny, exception, DNS policy | Gắn owner cho nhu cầu phân giải hoặc baseline bảo vệ |
| IDS/IPS | Rule/exclusion/bypass, policy inspection | Nhiều rule do security team quản lý; exception cần người yêu cầu và hạn |
| SDN / microsegmentation | Workload label policy, segment, namespace policy | Gắn với service identity và policy-as-code, tránh chỉ dựa vào IP |
| Wi-Fi / NAC | VLAN/role ACL, posture-based access, guest policy | Liên hệ nhóm sở hữu dịch vụ và nhóm kiểm soát truy cập |

**Không đồng nhất tất cả loại rule.** Firewall policy có thể là tập quy tắc xét theo thứ tự ưu tiên; một cloud security group thường hợp nhất các quyền allow theo mô hình riêng, không xử lý giống firewall first-match. Phải lưu **semantics của nền tảng** để các công cụ kiểm kê không suy ra sai một rule bị che hoặc không hiệu lực.

### 3.1. Rule nghiệp vụ, rule nền tảng và rule bảo vệ

Chia loại theo **mục đích**, không phải theo cổng:

- **Business access:** cho phép ứng dụng giao tiếp theo nhu cầu đã phê duyệt; owner thuộc nhóm dịch vụ nghiệp vụ.
- **Platform dependency:** DNS, NTP, monitoring, backup, identity, certificate service; owner là nhóm vận hành nền tảng hoặc nhóm phụ trách dịch vụ dùng chung.
- **Security baseline:** deny Internet to management, chặn giao thức không an toàn, chặn lateral movement theo policy; **security policy owner** xác nhận chứ không cần bịa ra một ứng dụng để gán.
- **Temporary exception:** rule có phạm vi, thời hạn và risk approval; cần cả người yêu cầu, owner chịu trách nhiệm và ngày hết hạn.
- **Emergency change:** mở khẩn trong sự cố; bắt buộc hậu kiểm và chuyển về luồng phê duyệt đầy đủ.
- **Generated/managed rule:** controller hoặc IaC tự sinh; cần owner của **nguồn sinh** và chủ ứng dụng/kiểm soát liên quan.

## 4. Thiết kế mô hình định danh rule

Một rule phải có **ID ổn định đủ để theo dõi giữa các lần xuất cấu hình**, kể cả khi tên, vị trí hoặc thứ tự thay đổi. Tuy nhiên, không có ID phổ quát cho mọi nhà cung cấp.

### 4.1. Hai lớp định danh

- **Rule instance ID:** bản ghi rule cụ thể trên một thiết bị/chính sách, ví dụ ID gốc do firewall cung cấp kèm tenant, domain, policy package hoặc context.
- **Logical flow / control ID:** nhu cầu truy cập hoặc mục tiêu kiểm soát chung có thể hiện thực bằng nhiều rule vật lý, ví dụ một luồng ứng dụng được áp ở firewall on-prem, cloud SG và VPN.

Một logical flow có thể ánh xạ tới nhiều instance. Ngược lại, một rule gộp nhiều subnet/service có thể phục vụ nhiều ứng dụng. Khi đó, cần **bảng quan hệ nhiều-nhiều** hoặc kế hoạch tách rule, thay vì chọn bừa một owner và mất thông tin về các chủ liên quan.

### 4.2. Không lấy số thứ tự làm ID duy nhất

Trong firewall có policy theo thứ tự, rule số 17 có thể thành số 18 sau khi chèn rule mới. Với rule tự sinh, thay đổi resource ID hoặc deployment có thể tạo instance mới. Định danh nên ghi:

~~~text
inventory_id           : ID của bản ghi kiểm kê nội bộ, ổn định
platform               : firewall / cloud security group / proxy / ...
management_domain      : tenant, organization, VDOM, device-group, subscription...
policy_package_id      : gói chính sách hoặc policy set
native_rule_id         : ID được nền tảng cung cấp nếu có
rule_fingerprint       : hash chuẩn hóa của nội dung chính sách (phụ trợ)
logical_flow_id        : ID nhu cầu dịch vụ hoặc kiểm soát
configuration_version  : commit/revision đang được kiểm kê
snapshot_time          : thời điểm nhìn thấy rule thực tế
~~~

**Fingerprint không tự thay thế ID.** Sửa source object có thể làm nội dung rule thay đổi và hash khác, trong khi nhu cầu truy cập vẫn là một. Tương tự, hai rule có nội dung giống nhau ở hai vùng khác nhau không nhất thiết là cùng một instance.

## 5. Bộ trường kiểm kê tối thiểu

Một mẫu chuẩn hóa có thể nhóm thành sáu khối:

| Nhóm dữ liệu | Trường gợi ý | Mục đích |
| --- | --- | --- |
| Định danh | inventory_id, native_rule_id, platform, device, policy/package, tenant | Tìm được đúng rule gốc khi cần thay đổi |
| Điều kiện kỹ thuật | direction, source zone/address, destination zone/address, service/port, application, action, enabled, order | Mô tả traffic được điều khiển |
| Ngữ cảnh đường truyền | NAT, VPN, IPv4/IPv6, object references, schedule, logging, failover path | Hiểu đầy đủ quyền mạng thực sự |
| Ownership | application/service, business_owner, technical_owner, policy_owner, approver, escalation_contact | Xác định ai quyết định giữ hoặc thay đổi |
| Căn cứ nghiệp vụ | business_justification, ticket/change_id, approval_id, created_at, expires_at, exception_reason | Giải thích vì sao rule tồn tại |
| Chứng cứ/rà soát | last_hit, hit_count_window, last_reviewed_at, next_review_due, owner_confirmation, review_status, evidence_links | Hỗ trợ attestation và quyết định lifecycle |

Ngoài ra nên có các trường kiểm soát chất lượng dữ liệu:

- **Observed_at / last_seen_at:** thời điểm bản ghi còn tồn tại trong cấu hình đang hoạt động.
- **Source_of_truth:** hệ thống kiểm kê/chính sách/IaC gốc; phân biệt declared state và applied state.
- **Data_confidence:** mức tin cậy về owner và purpose, có lý do khi chưa chắc.
- **Ownership_status:** VERIFIED, PENDING_CONFIRMATION, UNKNOWN, DISPUTED hoặc ORPHANED.
- **Review_decision:** KEEP, NARROW, REPLACE, RETIRE, INVESTIGATE, kèm bằng chứng.
- **Rule_scope:** phạm vi production, staging, DR, partner, management hoặc guest.
- **Change_link:** tham chiếu tới thay đổi đã thực hiện và kết quả kiểm thử lại.

Trường nào bắt buộc phụ thuộc hệ thống, nhưng một rule **ALLOW có rủi ro** không nên được coi là đủ dữ liệu nếu thiếu purpose, owner được xác minh và căn cứ phê duyệt.

## 6. Ví dụ một bản ghi rule có ownership

Ví dụ JSON bên dưới chỉ minh họa định dạng trao đổi; địa chỉ IP thuộc khối tư liệu RFC 5737, tên nhóm và mã ticket đều là dữ liệu giả.

~~~json
{
  "inventory_id": "NET-RULE-0142",
  "logical_flow_id": "FLOW-PAYMENTS-API-01",
  "platform": "network-firewall",
  "device": "FW-DC-A",
  "policy_package": "PROD-SEGMENTATION",
  "native_rule_id": "142",
  "source_zone": "APP",
  "source": ["192.0.2.0/27"],
  "destination_zone": "PAYMENT",
  "destination": ["198.51.100.10/32"],
  "service": ["tcp/443"],
  "action": "ALLOW",
  "enabled": true,
  "application": "Payment API",
  "business_owner": "Nhóm Sản phẩm Thanh toán",
  "technical_owner": "Nhóm Vận hành Ứng dụng",
  "policy_owner": "Network Security",
  "approval_id": "CHG-DEMO-0142",
  "business_justification": "Ứng dụng truy cập API thanh toán nội bộ",
  "created_at": "2026-10-01",
  "expires_at": null,
  "last_reviewed_at": "2026-11-15",
  "next_review_due": "2027-02-15",
  "ownership_status": "VERIFIED",
  "review_decision": "KEEP",
  "observed_at": "2026-11-28T07:00:00Z"
}
~~~

Để dùng trong hệ thống thực, cần có thêm định danh tenant/context của rule, nguồn dữ liệu, version/chữ ký snapshot, object group đã tham chiếu và log/hit evidence khi thích hợp. Các thông tin nhạy cảm trong cấu hình phải được bảo vệ theo quyền truy cập.

**Không dựa vào bản ghi JSON do một người nhập để suy ra rule đã tồn tại thực tế.** Bản kiểm kê phải liên kết được với snapshot cấu hình và đối soát trạng thái deployed.

## 7. Thu thập dữ liệu rule một cách có kiểm soát

### 7.1. Xác định nguồn dữ liệu

Ưu tiên truy xuất bằng API/export **read-only được hỗ trợ chính thức** từ firewall manager, cloud control plane, controller, IaC repository hoặc hệ thống quản lý tập trung. Mục tiêu là biết **cấu hình đang được thực thi**, không chỉ cấu hình ai đó dự kiến triển khai.

Quy trình gợi ý:

1. Liệt kê thiết bị/tenant/policy package và tài khoản dịch vụ có quyền xem cần thiết.
2. Ghi lại thời điểm, phiên bản hệ thống, policy revision và cấu hình đang active.
3. Xuất rule, object group, schedule, zone, NAT và metadata liên quan, theo đúng phạm vi ủy quyền.
4. Thu bản ghi change ticket, application inventory, CMDB/asset owner và IaC state/commit nếu có.
5. Bảo vệ file xuất vì có thể tiết lộ sơ đồ mạng, đối tác, endpoint và kiểm soát bảo mật.
6. Kiểm tra dữ liệu đầy đủ: số rule, số policy package, pagination, API throttling, failed requests và thiết bị không kết nối.
7. Ghi dấu snapshot và lưu bản gốc bất biến trong kho kiểm soát; các phép chuẩn hóa thao tác trên bản sao logic.

**Phân biệt ba trạng thái:**

| Trạng thái | Ý nghĩa | Rủi ro nếu nhầm |
| --- | --- | --- |
| Intended | Rule yêu cầu trong ticket/thiết kế | Có thể chưa được phê duyệt hoặc triển khai |
| Declared | Rule định nghĩa trong IaC/manager | Có thể chưa được push hoặc phát sinh drift |
| Enforced | Rule thực tế được thiết bị/cloud control plane áp dụng | Có thể khác declared sau lỗi triển khai hoặc hotfix |

Một bản kiểm kê cần nêu rõ đang phản ánh trạng thái nào. Muốn kết luận bảo mật thực tế, phải có bằng chứng **enforced state** hoặc mô tả rõ giới hạn quan sát.

### 7.2. Ghi nguồn và chất lượng

Các kiểm tra dữ liệu trước khi đối soát owner:

- Có bao nhiêu thiết bị đã xuất thành công trên tổng số dự kiến?
- Có pagination và rule ẩn trong nhiều policy layer không?
- Rule bị disable có được xuất không?
- Có thấy implicit/default rules và global rule không?
- Đối tượng động (FQDN, tag, workload group) có được giữ nguyên cùng snapshot membership không?
- Tình trạng NAT, IPv6, VPN và multi-tenant đã đầy đủ chưa?
- API có làm mất comment chứa ticket/owner hoặc rule ID?
- Thời gian snapshot giữa nhiều firewall có đủ gần để phân tích không?

Nếu một nguồn thất bại, đánh dấu **INCOMPLETE** với lý do và owner của nguồn dữ liệu; không lặng lẽ coi phần thiếu là “không tồn tại rule”.

## 8. Chuẩn hóa rule mà không đánh mất ý nghĩa

Một số nền tảng đặt tên field khác nhau: source có thể là địa chỉ, object ID, prefix list, workload identity hoặc nhãn. Chuẩn hóa chỉ nên tạo **mô hình so sánh**, vẫn giữ bản gốc và semantics.

### 8.1. Object group và thành viên động

Rule sử dụng group “APP-SERVERS” có thể bỗng mở rộng phạm vi khi thành viên được thêm vào. Vì vậy nên lưu **cả tên group và thành viên đã phân giải tại snapshot**, có dấu thời gian và nguồn xác định membership.

Không xóa liên kết object gốc khi xuất báo cáo dạng “expanded rule”. Nếu group được sử dụng ở nhiều rule, thay đổi một group có thể ảnh hưởng nhiều owner. Cần lập danh sách các rule cùng tham chiếu trước khi sửa.

### 8.2. NAT và đường đi

Traffic có thể được đối chiếu ở địa chỉ trước NAT, sau NAT hoặc theo zone; thứ tự xử lý tùy nền tảng. Một rule đích public IP có thể phục vụ backend nội bộ. Phải lưu quan hệ **flow logic → NAT mapping → policy rule → endpoint thực** để owner của ứng dụng có thể xác nhận đúng luồng.

Đối với VPN/SD-WAN, kiểm tra tunnel selector, route, DNS và policy gắn với danh tính người dùng. Rule có thể chỉ phát sinh hiệu lực khi một VPN hoặc tunnel cụ thể hoạt động.

### 8.3. Semantics cloud và firewall

- Firewall ordered policy có thể sử dụng first-match; rule ưu tiên cao che khuất rule ở dưới.
- Security group kiểu allow aggregation có thể không có thứ tự rule; không áp dụng phân tích shadow theo thứ tự một cách máy móc.
- Network ACL cloud có thể là stateless, đánh giá ingress và egress riêng với rule priority.
- Kubernetes NetworkPolicy có semantics riêng theo selector, ingress/egress và plugin; không giả định mọi policy engine hỗ trợ deny tường minh.
- Rule WAF có priority, override, exception và hành động monitor/block theo dịch vụ; phải đọc đúng logic thực thi.

**Phân tích trùng lặp hoặc rule bị che chỉ đúng khi công cụ hiểu mô hình thực thi của nền tảng.** Một công thức so sánh chuỗi source/destination đơn giản không đủ cho quyết định thu hồi.

## 9. Gán chủ sở hữu dựa trên bằng chứng

Đây thường là khâu khó hơn xuất cấu hình. Cần tránh gán owner theo suy đoán từ tên máy hoặc người commit gần nhất.

### 9.1. Thứ tự nguồn xác minh

Ưu tiên kết hợp các bằng chứng:

1. **Service catalog / application inventory:** dịch vụ nào nhận hoặc phát sinh luồng, ai chịu trách nhiệm chức năng?
2. **CMDB / asset inventory:** tài sản nguồn/đích, role, nhóm vận hành, lịch sử sở hữu.
3. **Change request và phê duyệt:** rule được yêu cầu bởi ai, để làm gì, có hiệu lực bao lâu?
4. **IaC và deployment pipeline:** module/project tạo rule, repository maintainer và team chịu trách nhiệm chính sách.
5. **Sơ đồ luồng và kiến trúc phân đoạn:** quan hệ hệ thống và các phụ thuộc đã duyệt.
6. **Log và phân tích traffic:** bằng chứng rule được sử dụng từ nguồn nào tới đích nào trong khoảng thời gian có giới hạn.
7. **Xác nhận từ người có thẩm quyền:** owner dịch vụ hoặc security policy owner xác nhận mục đích và quyền giữ rule.

**Bằng chứng sử dụng (hit count) không chứng minh ownership.** Một rule được hit bởi máy thuộc nhóm B không có nghĩa nhóm B đã yêu cầu hoặc được phép sở hữu rule, nhất là khi rule quá rộng hoặc chứa traffic không mong muốn.

### 9.2. Quy trình liên hệ và xác nhận

- Tạo danh sách rule ứng viên của từng service dựa trên mapping và bằng chứng.
- Gửi bản tóm tắt chỉ gồm thông tin cần thiết: source/destination/service, mục đích, ticket, lần hit, rủi ro và ngày hết hạn.
- Yêu cầu owner chọn **KEEP / NARROW / RETIRE / INVESTIGATE**, nêu căn cứ và trường hợp cần thử.
- Ghi người xác nhận, vai trò, thời điểm, comment, phạm vi xác nhận và link evidence.
- Với nhiều owner, ghi các bên chịu tác động và **một người/nhóm accountable cho quyết định**, hoặc tách rule thành các quyền truy cập dễ quản trị hơn.

Không xem việc “đã gửi email” hoặc “không ai phản hồi” là một xác nhận mặc định. Nếu quá thời hạn, chuyển escalation đến hệ thống quản lý dịch vụ hoặc chủ hạ tầng theo chính sách.

### 9.3. Khi owner chưa rõ

Trạng thái nên phân biệt:

| Trạng thái | Ý nghĩa | Xử lý |
| --- | --- | --- |
| VERIFIED | Chủ sở hữu đã xác nhận, có bằng chứng gần đây | Đưa vào chu kỳ rà soát định kỳ |
| PENDING_CONFIRMATION | Có ứng viên nhưng chưa được người có trách nhiệm xác nhận | Giao nhiệm vụ và thời hạn |
| UNKNOWN | Không có căn cứ đáng tin để gán owner | Điều tra với CMDB/ticket/flow, escalate |
| DISPUTED | Nhiều nhóm không thống nhất trách nhiệm | Tổ chức buổi quyết định có người có thẩm quyền |
| ORPHANED | Owner cũ không còn tồn tại hoặc dịch vụ ngừng vận hành | Kiểm tra nhu cầu thực, đánh giá rủi ro và kế hoạch retirement |
| EXEMPT_BASELINE | Rule bảo vệ nền tảng đã có policy owner | Rà soát theo baseline, không ép gán business app owner |

**Rule UNKNOWN không đồng nghĩa được quyền xóa ngay.** Trước khi thay đổi cần xác định tác động lên ứng dụng, đường dự phòng, tác vụ định kỳ và dịch vụ ít sử dụng. Ngược lại, UNKNOWN cũng không phải lý do giữ vô hạn; phải có owner điều tra, hạn xử lý và biện pháp giảm rủi ro trong thời gian chờ.

## 10. RACI cho vòng đời rule

Mẫu RACI sau chỉ là gợi ý; R = Responsible (thực hiện), A = Accountable (chịu trách nhiệm cuối), C = Consulted, I = Informed. Mỗi hoạt động nên có **một vai trò A rõ ràng**.

| Hoạt động | Application owner | Network Security | Firewall/Cloud operator | Security governance |
| --- | --- | --- | --- | --- |
| Xác nhận nhu cầu luồng nghiệp vụ | A/R | C | C | I |
| Đánh giá tính phù hợp của rule với policy | C | A/R | C | I |
| Triển khai rule được phê duyệt | I | C | A/R | I |
| Ghi nhật ký và kiểm kê kỹ thuật | C | A | R | I |
| Attestation mục đích còn hiệu lực | A/R | C | I | C |
| Đề xuất thu hẹp/xóa rule | A/R đối với nhu cầu ứng dụng | A với policy/risk | R về triển khai | C |
| Chấp nhận ngoại lệ rủi ro | C hoặc A nếu được ủy quyền | C | I | A theo quy chế |
| Audit quy trình và chỉ số | I | R | C | A |

Ma trận trên có thể cần phân tách thêm service owner, business risk owner và approver. Quan trọng là tránh để một cá nhân tự yêu cầu, tự đánh giá, tự duyệt và tự sửa một rule đặc quyền cao khi chính sách yêu cầu phân tách nhiệm vụ.

## 11. Phân loại và ưu tiên review theo rủi ro

Không phải mọi rule đều có cùng rủi ro. Dùng các yếu tố sau để ưu tiên, không gán rủi ro chỉ bằng số cổng:

| Tín hiệu | Ví dụ | Ý nghĩa quản trị |
| --- | --- | --- |
| Source quá rộng | 0.0.0.0/0 hoặc ::/0 vào management interface | Có thể mở bề mặt quản trị ra vùng không tin cậy |
| Destination quá rộng | Một subnet lớn hoặc nhóm tăng thành viên liên tục | Quyền truy cập vượt ứng dụng ban đầu |
| Service quá rộng | ANY, nhiều port không có justification | Tăng bề mặt tấn công và lateral movement |
| Cross trust boundary | Guest → internal, partner → production, Internet → admin | Cần owner/phê duyệt và kiểm thử phân đoạn chặt hơn |
| High-privilege protocol | SSH, RDP, WinRM, BMC hoặc API quản trị | Rủi ro thay đổi hệ thống hoặc chiếm quyền |
| Thiếu owner/ticket | Không rõ ai xác nhận mục đích | Không thể ra quyết định lifecycle có trách nhiệm |
| Exception đã hết hạn | Rule tạm vẫn enabled sau mốc cam kết | Có thể là quyền tạm trở thành vĩnh viễn |
| Log thiếu hoặc không nhất quán | Rule đặc quyền cao không ghi sự kiện cần thiết | Hạn chế điều tra và phát hiện tấn công |
| Rule chưa được hit trong cửa sổ quan sát | Có thể không còn dùng | Cần điều tra, không tự động xóa |
| Shared object đổi thành viên | Nhiều rule mở rộng ngầm cùng lúc | Có thể ảnh hưởng nhiều chủ ứng dụng |
| Policy drift | Khác IaC/central manager hoặc peer HA | Trạng thái thực thi không khớp phê duyệt |

Một mô hình xếp hạng tham khảo có thể dùng ba nhóm:

- **Priority 1:** tiếp cận quản trị từ nguồn không tin cậy, rule tạm hết hạn có phạm vi rộng, không rõ owner ở biên nhạy cảm, hoặc phát hiện khả năng bypass kiểm soát.
- **Priority 2:** rule rộng nhưng có owner, thiếu một số bằng chứng, rule chưa sử dụng lâu cần xác minh hoặc thay đổi object group làm tăng phạm vi.
- **Priority 3:** rule ít rủi ro và đã được owner xác nhận, có lịch rà soát bình thường.

Mức ưu tiên thực tế cần dựa trên phân loại dữ liệu, kiến trúc, threat model và quy định tổ chức. Không biến ví dụ này thành thang điểm tuân thủ cứng hoặc suy từ trường UNKNOWN thành lỗ hổng khai thác đã được chứng minh.

## 12. Hit count, stale rule và rule bị che khuất

### 12.1. Hit count có ích nhưng có giới hạn

Hit counter hoặc log cho biết có bao nhiêu gói/session khớp một rule trong điều kiện nền tảng đo được. Nó **không chứng minh rule cần giữ**, cũng không tự chứng minh rule không cần nữa khi bằng 0.

Một rule có zero hits vì:

- Mới triển khai hoặc chỉ kích hoạt trong ca dự phòng.
- Chỉ phục vụ job cuối tháng, cuối quý hoặc batch theo mùa.
- Thiết bị đã reboot hoặc counter bị reset.
- Traffic đi qua node HA/đường khác; snapshot chưa tổng hợp toàn cluster.
- Fast-path/offload/telemetry sampling khiến số đo không tương ứng số session.
- Rule bị che bởi rule khác hoặc chưa được phân bố tới thiết bị đang chạy.
- Phạm vi đo không bao phủ giao thức/địa chỉ IPv6 hoặc interface phụ.

Vì vậy, mỗi hit metric cần ghi **window_start, window_end, data_source, node_scope, counter_reset và mức độ đầy đủ**. Không chỉ lưu một số nguyên “last_used = 0”.

### 12.2. Stale rule, shadowed rule và duplicate

- **Stale:** lý do kinh doanh không còn hoặc đã được xác nhận ngừng sử dụng, không đơn thuần là zero hits.
- **Shadowed:** trong policy theo thứ tự, rule ưu tiên trước đã xử lý toàn bộ hoặc phần tương ứng khiến rule sau không được áp dụng như dự kiến.
- **Duplicate:** nhiều rule có điều kiện tương đương hoặc chồng lấn đáng kể; không mặc nhiên được xóa vì có thể khác zone, log, schedule, rule order hoặc policy package.
- **Overly permissive:** rule cho phép phạm vi vượt nhu cầu, dù được dùng hằng ngày.
- **Expired exception:** quyền truy cập ngoại lệ quá hạn nhưng vẫn enabled hoặc không có phê duyệt gia hạn.

Khi công cụ phát hiện các trường hợp trên, chuyển chúng thành **ứng viên review có bằng chứng**; quyết định xóa hoặc thu hẹp phải xét hành vi thực thi, ứng dụng phụ thuộc và kế hoạch kiểm thử.

## 13. Chu kỳ kiểm kê và attestation

Một chu kỳ hoàn chỉnh có thể đi theo luồng:

~~~mermaid
flowchart TD
    A["Thu snapshot enforced rules"] --> B["Chuẩn hóa và đối chiếu source of truth"]
    B --> C["Ánh xạ rule với flow, dịch vụ, owner"]
    C --> D{"Owner và purpose đã xác minh?"}
    D -->|"Chưa"| E["Điều tra / escalation có thời hạn"]
    E --> C
    D -->|"Rồi"| F["Review rủi ro, log, hit, expiry"]
    F --> G{"Quyết định"}
    G -->|"KEEP"| H["Xác nhận owner và ngày review tiếp"]
    G -->|"NARROW / REPLACE"| I["Tạo change có phê duyệt"]
    G -->|"RETIRE"| I
    G -->|"INVESTIGATE"| E
    I --> J["Đánh giá phụ thuộc, staging và rollback"]
    J --> K["Triển khai và kiểm thử lại"]
    K --> L["Cập nhật inventory + evidence"]
    H --> L
    L --> M["Theo dõi drift / đến hạn review"]
    M --> A
~~~

Quy trình nên chạy theo **hai nhịp**:

1. **Continuous/event-driven:** rule mới, rule sửa, rule bị xóa, tag owner thay đổi, CMDB đổi nhóm sở hữu hoặc ticket hết hạn đều tạo sự kiện cập nhật.
2. **Periodic attestation:** chủ dịch vụ và policy owner rà soát theo lịch dựa trên mức rủi ro.

Ví dụ cadence có thể là 30–90 ngày cho quyền quản trị/ngoại lệ nhạy cảm và 180 ngày cho rule nghiệp vụ ổn định. Đây là **ví dụ thiết kế lịch**, không có một chu kỳ chung áp cho mọi tổ chức; điều chỉnh theo tiêu chuẩn nội bộ, biến động hệ thống và mức độ phơi lộ.

### 13.1. Bốn quyết định cần chuẩn hóa

| Quyết định | Điều kiện | Bước tiếp theo |
| --- | --- | --- |
| KEEP | Rule vẫn cần, phạm vi chính xác, owner và phê duyệt còn hiệu lực | Ghi attestation, ngày review mới |
| NARROW | Nhu cầu còn nhưng source/destination/service quá rộng | Thiết kế rule cụ thể hơn, kiểm thử ứng dụng |
| REPLACE | Có luồng mới hoặc cơ chế bảo vệ tốt hơn thay thế rule cũ | Triển khai quyền mới, kiểm chứng rồi retire cũ |
| RETIRE | Owner xác nhận không còn nhu cầu và đánh giá tác động đạt | Change control, disable/remove theo kế hoạch và retest |
| INVESTIGATE | Thiếu dữ liệu hoặc có mâu thuẫn | Giao owner điều tra, hạn và escalation |

Không dùng trạng thái KEEP để che việc owner chưa trả lời. Đối với rule không rõ owner, nên dùng UNKNOWN/PENDING và lịch escalation riêng.

## 14. Quản lý ngoại lệ và rule có thời hạn

Các rule mở khẩn để khắc phục sự cố, hỗ trợ đối tác, migration hoặc pentest cần **time-bound exception**.

Một hồ sơ đầy đủ nên có:

- Người yêu cầu, nhóm owner của dịch vụ và người chấp nhận rủi ro.
- Rule ID và phạm vi nguồn/đích/protocol tối thiểu.
- Lý do, hệ thống bị ảnh hưởng, ticket incident/change.
- Ngày bắt đầu, **ngày hết hạn**, thời gian đánh giá lại và điều kiện thu hồi.
- Biện pháp bù trừ: MFA/VPN, logging, giám sát, giới hạn IP/port hoặc thời gian.
- Kế hoạch tháo bỏ, người triển khai, cách kiểm thử và rollback.

Nếu hệ thống hỗ trợ tự động hết hạn, cấu hình cần có cơ chế thông báo và kiểm thử tương thích, tránh hết hạn giữa một giao dịch quan trọng mà không có kế hoạch. Khi đến hạn, hệ thống nên tạo việc cần làm và thông báo owner; **không gia hạn tự động vô thời hạn** chỉ vì từng được phê duyệt.

Rule hết hạn nhưng vẫn có traffic là một tín hiệu cần xử lý sớm: hoặc nhu cầu chưa được chuyển sang rule chính thức, hoặc vẫn có luồng không còn được phê duyệt. Cả hai đều cần đánh giá, không nên im lặng xóa trong sản xuất.

## 15. Mẫu bảng kiểm kê và buổi rà soát

Giả sử một tổ chức có các rule minh họa sau. Các tên và IP đều là giả lập, không phản ánh hệ thống thực.

| Rule ID | Luồng / hành động | Owner | Lý do | Tình trạng | Hướng xử lý |
| --- | --- | --- | --- | --- | --- |
| NET-101 | APP → PAYMENT TCP/443 ALLOW | Nhóm Thanh toán | API nghiệp vụ đã duyệt | VERIFIED, hoạt động | KEEP |
| NET-102 | BASTION → SWITCH TCP/22 ALLOW | Nhóm Network Operations | Quản trị thiết bị | VERIFIED | KEEP, review theo rủi ro |
| NET-103 | GUEST → MGMT ANY DENY | Network Security | Baseline phân đoạn | EXEMPT_BASELINE | Giữ và kiểm thử chính sách |
| NET-104 | PARTNER → DB TCP/5432 ALLOW | Chưa xác nhận | Comment cũ: migration | UNKNOWN, ticket hết hạn | INVESTIGATE khẩn |
| NET-105 | USER → APP ANY ALLOW | Nhóm Ứng dụng A | Kết nối phục vụ ứng dụng | VERIFIED nhưng quá rộng | NARROW theo port cụ thể |
| NET-106 | BATCH → REPORT TCP/443 ALLOW | Nhóm Dữ liệu | Tác vụ quý | Zero hits trong 60 ngày | INVESTIGATE, chưa kết luận stale |

### 15.1. Lập quyết định có chứng cứ

**NET-104:** Không thể khẳng định xóa an toàn vì chưa biết có job nào còn dùng. Tìm change gốc, tra owner của DB, flow log theo cửa sổ đủ dài, hỏi nhóm đối tác và nghiệp vụ. Nếu chứng minh không còn hợp đồng/luồng và có phê duyệt, tạo change để disable rồi theo dõi trước khi remove.

**NET-105:** Owner xác nhận chỉ cần TCP/443 từ hai workload cụ thể. Thiết kế rule mới giới hạn source/port, kiểm tra traffic hợp lệ, sau đó loại bỏ rule ANY cũ theo change có rollback. Tránh sửa object group dùng chung mà chưa xem tác động các rule khác.

**NET-106:** Chưa có hits không đồng nghĩa không cần rule vì job chạy cuối quý. Cần xem lịch tác vụ, log các quý trước và owner xác nhận; điều chỉnh cửa sổ đánh giá cho đúng chu kỳ.

**NET-103:** Rule DENY phục vụ chính sách an ninh chung có policy owner, không cần ép nhóm ứng dụng bất kỳ chịu trách nhiệm. Kiểm thử negative access từ guest VLAN để chứng minh rule còn có tác dụng theo thiết kế.

## 16. Thực hành offline: đối soát một file inventory mẫu

Để người học kiểm tra logic dữ liệu, ví dụ CSV dưới đây có thể được tạo **thủ công trong lab**. Nó không phải cấu hình firewall có thể áp dụng. Dùng các mã nhóm thay tên cá nhân.

~~~csv
inventory_id,action,source_zone,destination_zone,service,owner,status,expires_at
NET-101,ALLOW,APP,PAYMENT,tcp/443,Payment,VERIFIED,
NET-102,ALLOW,BASTION,MGMT,tcp/22,NetworkOps,VERIFIED,
NET-103,DENY,GUEST,MGMT,any,NetworkSecurity,EXEMPT_BASELINE,
NET-104,ALLOW,PARTNER,DATA,tcp/5432,,UNKNOWN,2026-10-31
NET-105,ALLOW,USER,APP,any,AppA,VERIFIED,
NET-106,ALLOW,BATCH,REPORT,tcp/443,DataTeam,PENDING_CONFIRMATION,
~~~

Có thể kiểm tra theo tư duy điều kiện:

~~~text
FOR each inventory record:
    VERIFY inventory_id is unique in the snapshot
    VERIFY technical rule fields are present

    IF status is UNKNOWN or PENDING_CONFIRMATION:
        OPEN ownership-review task with deadline and escalation

    IF action is ALLOW and source/destination/service is broad:
        REQUEST least-privilege review with documented owner

    IF expires_at exists and expires_at < review_date:
        FLAG expired-exception review

    IF baseline DENY:
        VERIFY policy owner and negative-access test evidence

    NEVER auto-delete rule based solely on these flags
~~~

Đây là **mã giả** nhằm minh họa nguyên tắc rà soát. Để đưa vào công cụ tự động thật cần xử lý schema, ngày tháng, nguồn dữ liệu, phân quyền, transaction và chính sách phê duyệt.

Một báo cáo sơ bộ cho CSV trên có thể ghi:

| Phát hiện | Rule minh họa | Ý nghĩa |
| --- | --- | --- |
| Chưa xác nhận owner | NET-104, NET-106 | Hai bản ghi cần điều tra/attestation |
| Ngoại lệ quá hạn tại ngày 28/11/2026 | NET-104 | Cần đánh giá ưu tiên trước |
| Rule ALLOW quá rộng | NET-105 | Cần chứng minh phạm vi service tối thiểu |
| Baseline DENY | NET-103 | Owner kiểm soát là Security, cần test deny |
| Rule đã xác nhận và có mục đích rõ | NET-101, NET-102 | Tiếp tục review định kỳ |

Không kết luận NET-104 có thể bị xóa chỉ vì owner rỗng hoặc ngày quá hạn. Tương tự, không kết luận NET-105 tồn tại lỗ hổng exploitable chỉ vì service ANY; cần đánh giá vùng tin cậy, ACL bổ sung và dịch vụ liên quan.

## 17. Tự động hóa đồng bộ kiểm kê và phát hiện drift

Mục tiêu tự động hóa là **tăng độ chính xác và thời gian phát hiện thay đổi**, trong khi việc quyết định quyền truy cập vẫn có người hoặc quy trình có thẩm quyền kiểm soát.

Một pipeline tham khảo:

~~~text
Firewall / cloud API / IaC repository
                |
          Read-only collector
                |
       Snapshot + schema validation
                |
       Vendor-specific normalization
                |
       Inventory rule instances
                |
       Join logical flow + CMDB + tickets
                |
       Owner attestation / risk review
                |
       Exceptions, drift alerts, dashboards
                |
       Approved change workflow
                |
       Recheck enforced state
~~~

### 17.1. Các kiểm tra tự động nên làm

- Phát hiện rule mới có action ALLOW nhưng thiếu owner hoặc ticket.
- Phát hiện rule được sửa source/destination/service mà không có change record tương ứng.
- Phát hiện owner không còn tồn tại trong tổ chức, team bị đổi tên hoặc ứng dụng bị decommission.
- Phát hiện rule tạm đã quá hạn, rule được enable lại và ngoại lệ liên tục gia hạn.
- So sánh policy giữa HA peers, region, environment production/DR khi cần giữ parity.
- Đánh dấu object group tăng thành viên, quyền quản trị bị mở rộng hoặc thêm source ::/0.
- Đối chiếu declared IaC với enforced state sau triển khai và thay đổi thủ công.
- Theo dõi số bản ghi thiếu nguồn, pagination lỗi, snapshot quá cũ hoặc không liên hệ được manager.

### 17.2. Cách tránh tự động hóa gây sự cố

- Collector dùng **read-only service account**; lưu secret ở secret manager và luân chuyển theo chính sách.
- Không để dashboard hay script kiểm kê có quyền tự sửa firewall trong bước quan sát.
- Cảnh báo thay đổi owner/status được lưu audit trail; không để người dùng tự gán owner của nhóm khác mà thiếu xác nhận.
- Phân biệt các trạng thái **RECOMMENDED**, **APPROVED**, **DEPLOYED**, **VERIFIED** trong workflow.
- Tránh suy danh tính dựa trên một IP động, tên object hoặc git committer.
- Trước mọi hành động thu hồi, áp dụng impact analysis, approval, maintenance window và rollback được chuẩn bị.
- Giới hạn dữ liệu xuất và quyền truy cập vì rule inventory có thể tiết lộ sơ đồ phân đoạn, hệ thống nhạy cảm và đối tác.

## 18. Change control khi thu hẹp hoặc xóa rule

Một quyết định RETIRE được xác nhận về mặt nghiệp vụ vẫn cần quy trình kỹ thuật để không làm đứt dịch vụ.

### 18.1. Trước khi thay đổi

1. Xác nhận đúng rule instance, policy package, môi trường và phiên bản đã triển khai.
2. Đọc lại ticket/phê duyệt cùng xác nhận của các owner chịu ảnh hưởng.
3. Xem object group dùng chung, NAT, route, VPN, upstream/downstream firewall và các đường HA.
4. Kiểm tra log/flow theo cửa sổ phù hợp (bao gồm batch định kỳ hoặc DR failover nếu có).
5. Lập **ma trận luồng dương/âm**: ứng dụng nào phải tiếp tục được ALLOW, luồng không đúng chính sách phải DENY.
6. Chuẩn bị backup/rollback phù hợp nền tảng, người trực xử lý và cửa sổ bảo trì nếu cần.
7. Với rule nhạy cảm, cân nhắc staging hoặc canary để giảm rủi ro.

### 18.2. Trong khi thay đổi

Ưu tiên thực hiện thay đổi nhỏ, có thể đảo ngược và dễ theo dõi. Ví dụ một quy trình có thể:

1. Thêm rule hẹp đã được phê duyệt.
2. Kiểm thử các luồng hợp lệ qua rule mới.
3. Disable rule cũ trong cửa sổ thay đổi nếu nền tảng và chính sách cho phép.
4. Quan sát log/tác động, đánh giá kết quả theo tiêu chí chấp nhận.
5. Remove rule cũ sau thời gian theo dõi và có xác nhận; lưu bằng chứng version.

Không có một trình tự duy nhất cho mọi firewall: một số nền tảng áp dụng ordered first-match, một số cấu hình dùng shared object hoặc transaction; phải tuân thủ hành vi thật của sản phẩm. **Không tự xóa rule dựa trên hit count hoặc ngày hết hạn** khi chưa qua change và đánh giá tác động.

### 18.3. Sau khi thay đổi

- Kiểm tra actual deployed policy và hash/revision, không chỉ thông báo thành công của công cụ quản lý.
- Xác minh ứng dụng và những luồng ALLOW thiết yếu vẫn hoạt động.
- Thử luồng DENY để bảo đảm đường đã thu hẹp thực sự chặn quyền không cần thiết.
- Kiểm tra cả IPv4/IPv6, đường HA, VPN và môi trường DR liên quan.
- Ghi rule ID trước/sau, người triển khai, ticket, kết quả và thời gian.
- Cập nhật inventory, quan hệ flow/owner và lịch review; đóng ticket khi đủ bằng chứng.

## 19. Khi rule liên quan nhiều lớp kiểm soát

Một luồng ứng dụng xuyên nhiều miền tin cậy có thể cần thay đổi ở firewall nội bộ, cloud SG, WAF, DNS policy và site-to-site VPN.

Ví dụ luồng đối tác → API nội bộ:

~~~mermaid
flowchart LR
    P["Partner network"]
    V["Site-to-site VPN"]
    F["Edge firewall"]
    S["Cloud security group"]
    A["Internal API"]
    D["DNS / identity"]
    P --> V --> F --> S --> A
    A -.-> D
~~~

Owner cần xác nhận **nhu cầu end-to-end**, còn mỗi control owner chịu trách nhiệm rule thực thi trong lớp của mình. Khi đối tác ngừng sử dụng API, không đủ nếu chỉ xóa rule ở một firewall; phải tìm các rule liên quan trên toàn đường, security group, DNS exception và cấu hình VPN để tránh quyền thừa.

Cũng không nên xóa đồng loạt không kiểm chứng. Một rule logic có thể phục vụ nhiều workload hoặc nhiều đối tác; cần tách quan hệ trước khi thu hồi để không ảnh hưởng bên vẫn có quyền sử dụng.

### 19.1. Liên hệ với threat modeling và giám sát

- Các luồng có ranh giới tin cậy cao (Internet, guest, partner, production data) cần lý do và owner rõ ràng.
- Đối với luồng qua IDS/IPS hoặc WAF, cần quản lý **exception/bypass owner** riêng với owner của luồng network allow.
- Rule DNS filtering ngoại lệ có thể ảnh hưởng nhiều ứng dụng; không gán mọi domain exception cho DNS administrator mà thiếu requester/risk approval.
- Khi điều tra sự cố, mapping rule → owner → service giúp SOC liên hệ đúng nhóm và biết rule có thuộc luồng được phê duyệt hay không.
- Trong HA/failover, kiểm tra quyền trên đường dự phòng để chắc chắn policy owner không chỉ xác nhận đường chính.

## 20. Báo cáo và chỉ số vận hành

Chỉ số cần phục vụ quyết định và có **mẫu số rõ ràng**, tránh tạo tỷ lệ đẹp nhưng không phản ánh chất lượng kiểm kê.

| Chỉ số | Công thức/định nghĩa | Cách sử dụng |
| --- | --- | --- |
| Coverage kiểm kê | Số rule instance được thu / tổng số rule instance dự kiến trong scope | Đánh giá độ đầy đủ của snapshot |
| Ownership verified rate | Số rule thuộc scope có owner VERIFIED / tổng rule thuộc scope | Phát hiện khoảng trống trách nhiệm |
| Purpose/approval coverage | Số ALLOW rule có lý do và bằng chứng phê duyệt hợp lệ / tổng ALLOW rule | Đo khả năng giải trình quyền |
| Attestation on-time | Số rule đến hạn đã review đúng hạn / tổng số rule đến hạn | Đo tiến độ rà soát |
| Temporary exception overdue | Số ngoại lệ đã hết hạn nhưng còn active | Đặt ưu tiên remediation |
| Orphan rule backlog | Số rule UNKNOWN/ORPHANED quá hạn điều tra | Đo tồn đọng cần escalation |
| High-risk broad rule count | Số rule có scope rộng trong vùng nhạy cảm, kèm tiêu chí | Theo dõi giảm bề mặt truy cập |
| Change drift rate | Số rule lệch source of truth sau deploy / tổng rule đã đối soát | Đánh giá kiểm soát thay đổi |
| Retest completion | Số change đã có positive/negative test / tổng change yêu cầu | Chứng minh sửa đúng kỹ thuật |

Nếu phạm vi chưa đầy đủ hoặc snapshot cũ, ghi rõ **data freshness và coverage** cạnh các KPI. Không công bố 100% owner verified khi chỉ kiểm kê được một phần nhỏ thiết bị.

### 20.1. Dashboard và lịch làm việc

Một dashboard hữu ích có thể gồm: tổng rule theo platform/zone, ownership status, risk tier, deadline review, rule tạm quá hạn, bản ghi chưa có evidence, thay đổi gần đây và nhóm chịu trách nhiệm xử lý. Dashboard cần cho phép truy ngược đến **rule ID gốc**, owner và ticket, không chỉ biểu đồ tổng hợp.

Thiết lập lịch review theo mức rủi ro, có nhắc hạn và escalation; với tổ chức lớn, ưu tiên giao đầu việc theo **team/service** để người chịu trách nhiệm có đủ ngữ cảnh thay vì gửi hàng nghìn bản ghi rời rạc.

## 21. Sự cố thường gặp khi kiểm kê và cách xử lý

| Tình huống | Rủi ro sai kết luận | Cách xử lý |
| --- | --- | --- |
| Tên rule là tên người đã nghỉ | Gán nhầm owner hoặc không ai nhận | Tra service catalog và ticket, chuyển ORPHANED để điều tra |
| Nhiều app dùng một rule rộng | Một owner xác nhận thay cho tất cả | Ánh xạ nhiều flow và owner, xem xét tách rule |
| Rule zero hits 90 ngày | Xóa nhầm job theo quý hoặc DR | Mở rộng cửa sổ, hỏi owner, xem log các đường HA |
| Rule trong IaC không tồn tại khi triển khai | Báo sai rằng hệ thống có quyền đó | Phân biệt declared/enforced, kiểm tra pipeline |
| Rule thực tế không có trong IaC | Bỏ sót cấu hình thủ công ngoài quy trình | Gắn drift finding và tra change log |
| Object group vừa thay thành viên | Quyền thay đổi mà rule ID không đổi | Lưu object membership diff và tìm tất cả rule tham chiếu |
| Firewall failover sang peer khác | Số hit và thứ tự policy khác kỳ trước | Thu cả node, so sánh config và counter reset |
| NAT che địa chỉ dịch vụ | Không map được app owner | Truy ngược NAT mapping và đúng luồng thực tế |
| NACL cloud và SG được phân tích như ordered firewall | Gán nhầm shadowed hoặc duplicate | Dùng parser/engine theo semantics từng loại |
| Review trong spreadsheet nhưng không cập nhật nguồn chính | Dashboard lệch trạng thái thực | Gắn attestation với inventory ID và đồng bộ có audit |
| Owner xác nhận bằng im lặng | Nhu cầu chưa được chứng minh | Ghi PENDING, đặt hạn và escalation |
| Automation tự xóa rule expired | Gây outage cho dịch vụ phụ thuộc | Bắt buộc approval, test, rollback và xác minh sau thay đổi |

## 22. Quy trình vận hành mẫu trong một tháng

Một lịch giả định cho nhóm Network Security quản lý nhiều thiết bị:

- **Tuần 1 – Thu thập:** lấy snapshot từ firewall/cloud và đối soát với IaC, CMDB, ticket; xác minh tỷ lệ coverage trước khi sử dụng số liệu.
- **Tuần 2 – Phân loại:** kiểm tra owner, purpose, expiry và object changes; xếp ưu tiên các rule rộng, ngoại lệ quá hạn và đường quản trị.
- **Tuần 3 – Attestation:** gửi danh sách theo service/team, nhận quyết định có bằng chứng; escalation trường hợp không phản hồi.
- **Tuần 4 – Remediation và retest:** tạo change cho NARROW/RETIRE/REPLACE, thực hiện các phép thử có phạm vi và cập nhật inventory.
- **Xuyên suốt tháng:** quy tắc mới hoặc sửa phải có owner tại thời điểm yêu cầu; cảnh báo drift và hết hạn được xử lý theo SLA riêng.

Đây là gợi ý tổ chức công việc. Với hệ thống thay đổi nhiều hoặc có luồng nhạy cảm, cần giám sát liên tục hoặc review nhanh hơn. Việc đặt lịch không thay thế kiểm tra ngay khi có yêu cầu khẩn cấp hay phát hiện truy cập trái phép.

## 23. Checklist rà soát theo một rule

Với mỗi rule được đưa ra quyết định KEEP, NARROW hoặc RETIRE, người review nên xác nhận:

- [ ] Có định danh chính xác rule instance, thiết bị/tenant, policy và snapshot đang active.
- [ ] Đã hiểu source/destination, zone, service, action, NAT, IPv4/IPv6 và object group.
- [ ] Có logical flow hoặc baseline control được mô tả rõ.
- [ ] Có chủ dịch vụ/nhóm kiểm soát được xác minh và liên hệ được.
- [ ] Có căn cứ nghiệp vụ, ticket/phê duyệt phù hợp và ngoại lệ còn hiệu lực nếu có.
- [ ] Có log/hit evidence với phạm vi và cửa sổ thời gian được nêu.
- [ ] Đã kiểm tra quyền quá rộng, rule chồng lấn, shared object và đường dự phòng.
- [ ] Đã ghi quyết định, người xác nhận, ngày review và ngày review tiếp theo.
- [ ] Nếu cần sửa, đã có change plan, impact analysis, rollback và kiểm thử.
- [ ] Sau thay đổi đã xác minh enforced state, positive/negative flows và cập nhật inventory.

## 24. Tình huống thực hành

### Tình huống 1 – Firewall policy có 700 rule, 15% thiếu owner

Nhóm hạ tầng muốn gán toàn bộ các rule không rõ owner cho người đã sửa cuối cùng để đạt KPI.

**Phân tích:** người sửa cuối không chắc là chủ nhu cầu. Làm vậy tạo số liệu “đủ” nhưng không tạo trách nhiệm thực. Cần phân loại theo ứng dụng, asset, change và lý do; để trạng thái PENDING/UNKNOWN khi chưa xác minh, giao người điều tra có hạn xử lý.

### Tình huống 2 – Rule đối tác còn dùng nhưng hợp đồng đã chấm dứt

Rule cho phép từ mạng đối tác tới API còn hit hàng ngày. Owner nghiệp vụ xác nhận hợp đồng đã kết thúc từ hai tháng trước.

**Phân tích:** hit count chứng minh traffic đi qua, **không chứng minh traffic được phép**. Cần điều tra nguồn và người sử dụng, đánh giá rủi ro, cân nhắc tạm cô lập theo quy trình ứng cứu nếu có dấu hiệu bất thường, thu hồi quyền theo change có giám sát và ghi bằng chứng.

### Tình huống 3 – Security group có ba ứng dụng dùng chung

Một security group cloud chứa rule allow phục vụ ba ứng dụng. Khi một ứng dụng nghỉ hoạt động, team muốn xóa toàn bộ group.

**Phân tích:** group là đối tượng chia sẻ, nên xóa có thể cắt traffic của hai ứng dụng còn lại. Cần tách quan hệ logical flow, owner và thành viên; chỉ thu hồi quyền của ứng dụng đã dừng sau khi đo ảnh hưởng.

### Tình huống 4 – Rule ẩn trong DR site

Firewall tại DR có policy ít được dùng, nhiều rule zero hits. Sau sự cố datacenter, hệ thống chuyển sang DR và cần kết nối qua những rule đó.

**Phân tích:** zero hits từ vận hành bình thường không chứng minh rule thừa. Cần xác nhận disaster-recovery use case, tập luồng có quyền, chạy bài test failover được phê duyệt và review theo lịch DR.

### Tình huống 5 – Rule còn owner nhưng không còn phê duyệt

Owner kỹ thuật xác nhận rule vẫn giúp ứng dụng chạy, nhưng rule mở từ Internet vào API quản trị và không có phê duyệt rủi ro hiện hành.

**Phân tích:** owner xác nhận nhu cầu **không thay thế** chấp nhận rủi ro hoặc tiêu chuẩn bảo mật. Cần thẩm định kiến trúc, thay đường vào bằng VPN/bastion/identity-aware proxy khi phù hợp và có phê duyệt theo quy chế.

## 25. Câu hỏi tự kiểm tra

1. Vì sao người commit hoặc cấu hình rule cuối cùng không mặc nhiên là business owner?
2. Một rule DENY bảo vệ management subnet nên gắn owner thuộc nhóm nào và được xác nhận theo bằng chứng gì?
3. Vì sao zero hit trong 90 ngày không đủ để kết luận rule không cần thiết?
4. Những trường metadata nào giúp tìm đúng rule khi thứ tự bị thay đổi sau cập nhật?
5. Khi object group đổi thành viên mà rule ID vẫn giữ nguyên, cơ chế kiểm kê nào phát hiện quyền đã mở rộng?
6. Một logical flow đi qua cả firewall, VPN và cloud SG nên biểu diễn quan hệ ownership như thế nào?
7. Rule tạm hết hạn nhưng có traffic phải được xử lý ra sao?
8. Tại sao không thể dùng cùng thuật toán shadowed rule cho firewall ordered policy và cloud security group?
9. Những phép kiểm thử nào cần thực hiện sau khi tách một rule ANY thành các quyền tối thiểu?
10. Dashboard báo 100% rule đã có owner nhưng chỉ thu được 60% thiết bị: có thể kết luận chương trình kiểm kê đã hoàn thành không?

**Ghi nhớ:** kiểm kê rule theo chủ sở hữu là một **quy trình kiểm soát quyền truy cập liên tục**. Mỗi quyền nên nối được tới nhu cầu hoặc baseline, owner có thẩm quyền, bằng chứng phê duyệt, trạng thái triển khai và lịch rà soát. Chỉ khi kiểm kê đủ phạm vi, gán owner bằng chứng cứ và kiểm thử thay đổi có kiểm soát, tổ chức mới có thể thu hồi quyền dư thừa mà vẫn bảo vệ khả năng vận hành mạng an toàn.
