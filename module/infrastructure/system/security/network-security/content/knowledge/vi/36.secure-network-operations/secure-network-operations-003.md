# Phê duyệt thay đổi network policy

## 1. Tại sao thay đổi chính sách mạng phải được phê duyệt?

Trong môi trường vận hành, một quy tắc firewall mới, ACL trên router, quyền truy cập qua VPN, security group trên cloud, chính sách DNS hay NetworkPolicy trong Kubernetes đều có thể thay đổi **ai được phép liên lạc với tài sản nào, bằng giao thức nào và trong điều kiện gì**. Thao tác tưởng nhỏ, chẳng hạn mở TCP/5432 để sửa lỗi kết nối database, có thể vô tình cấp quyền từ một VLAN người dùng tới hệ thống dữ liệu nhạy cảm. Ngược lại, một quy tắc chặn thiếu kiểm chứng có thể làm ngừng dịch vụ sản xuất hoặc cắt mất đường quản trị thiết bị.

**Phê duyệt thay đổi network policy** là quy trình đánh giá nhu cầu, phạm vi truy cập, rủi ro an ninh, ảnh hưởng vận hành, cách xác minh và phương án khôi phục trước khi một thay đổi trở thành cấu hình có hiệu lực. Phê duyệt cũng xác định **ai chịu trách nhiệm ra quyết định**, căn cứ quyết định và trường hợp nào phải xem xét lại.

Bài học thuộc chương **Quản trị vận hành mạng an toàn** của module **SECURITY_NETWORK_SECURITY**. Nội dung áp dụng cho các lớp phòng vệ mạng như phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, Wi-Fi và cloud. Một chính sách mạng an toàn cần được thiết kế theo mô hình đe dọa, kiểm thử trên lưu lượng thực tế, giám sát sau triển khai và quản trị liên tục.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Nhận diện thay đổi nào cần kiểm soát và mức phê duyệt tương ứng.
2. Viết một phiếu yêu cầu thay đổi (*change request*) đủ thông tin để người khác thẩm định.
3. Đánh giá tác động về quyền truy cập, dữ liệu, phân đoạn, tính sẵn sàng và khả năng khôi phục.
4. Phân biệt người đề xuất, chủ sở hữu nghiệp vụ, người thẩm định bảo mật, người chấp thuận và người triển khai.
5. Thiết kế phép thử **allow** và **deny**, kế hoạch rollback, kiểm soát cửa sổ thay đổi và xử lý ngoại lệ khẩn cấp.
6. Duy trì bằng chứng, vòng đời ngoại lệ và cơ chế phát hiện *policy drift* sau khi đóng thay đổi.

## 2. Network policy bao gồm những gì?

Ở đây, **network policy** là tập quy tắc kiểm soát đường truyền, quyền truy cập hoặc biện pháp bảo vệ trên mạng. Một chính sách có thể được thực thi tại nhiều lớp và trên nhiều thiết bị.

| Loại thay đổi | Ví dụ | Rủi ro khi phê duyệt thiếu |
|---|---|---|
| **Firewall / router ACL** | Cho phép subnet A kết nối server B qua TCP/443; chỉnh rule thứ tự | Mở đường vượt phân đoạn; shadow rule; chặn luồng thiết yếu |
| **Segmentation / microsegmentation** | Thay nhóm workload được trao đổi với database | Mở lateral movement hoặc làm đứt dependency |
| **VPN / remote access** | Bổ sung route, nhóm người dùng, split tunnel, quyền truy cập | Mở rộng phạm vi truy cập từ xa hoặc bỏ qua xác thực bắt buộc |
| **NAC / 802.1X / Wi-Fi** | Gán VLAN, ACL cho thiết bị theo vai trò hoặc nhóm người dùng | Thiết bị chưa được xác thực truy cập vùng tin cậy |
| **Security group / NSG / NACL** | Sửa inbound/outbound rule trên cloud | Công khai port quản trị; vô tình mở cả IPv4/IPv6 |
| **DNS / proxy / egress** | Cho client dùng resolver khác, cho phép truy cập domain mới | Rò rỉ truy vấn nội bộ; vượt DNS filtering; cho egress không kiểm soát |
| **IDS/IPS / WAF** | Bật/tắt rule kiểm tra, đưa một nguồn vào exception | Bỏ sót khai thác; chặn nhầm traffic hợp lệ |
| **Load balancer / ingress** | Public listener mới, thay mTLS/TLS và backend routing | Expose dịch vụ chưa được phép hoặc chuyển tới sai backend |
| **Kubernetes NetworkPolicy** | Cho phép pod nhóm A gọi service B | Policy không có hiệu lực như kỳ vọng, phụ thuộc CNI và namespace |
| **Routing / NAT / peering** | Chuyển next hop, thêm route VPC, DNAT dịch vụ | Luồng đi vòng enforcement hoặc sai đường trả về |

**Quy tắc mạng đang tồn tại** và **đề xuất thay đổi quy tắc** là hai dữ liệu khác nhau. Người phê duyệt cần thấy chính xác *trước → sau*: chính sách nào bị sửa/xóa, rule nào thêm, thứ tự ưu tiên, phạm vi ảnh hưởng và điều kiện hết hạn.

Một yêu cầu “mở port 443” là chưa đủ: TCP/443 có thể là web public, API quản trị hoặc HTTPS tới một dịch vụ nội bộ; phạm vi, danh tính và mục đích mới quyết định rủi ro.

## 3. Nguyên tắc phê duyệt

### 3.1. Quyền tối thiểu và nhu cầu có chủ sở hữu

Mỗi thay đổi phải có **mục đích hợp lệ**, **owner nghiệp vụ**, **owner kỹ thuật**, điểm thực thi cụ thể và phạm vi nhỏ nhất cần thiết. Không cấp một subnet /16 khi chỉ hai máy ứng dụng cần quyền; không cho phép mọi port khi chỉ TCP/8443 cần thiết. Quyền được cấp nên cụ thể theo:

- Nguồn: host, IP/CIDR, nhóm danh tính, service account, tag hoặc workload identity.
- Đích: tài sản/ứng dụng, địa chỉ, VLAN/zone, resource ID hoặc service.
- Chiều kết nối, protocol, port, SNI/FQDN, API/path nếu sản phẩm hỗ trợ ràng buộc.
- Môi trường: dev/staging/prod, region, VPC/VNet, namespace, đường VPN, management zone.
- Thời gian: thường xuyên hay tạm thời, ngày hết hạn, điều kiện gia hạn.
- Lớp bảo vệ bổ sung: TLS/mTLS, MFA, bastion, logging, IDS/IPS, WAF, rate limiting.

Phê duyệt một **luồng cần thiết** không đồng nghĩa cho phép hạ mức xác thực hoặc tắt lớp giám sát để luồng đó hoạt động.

### 3.2. Mặc định từ chối và ngoại lệ có giới hạn

**Default deny** thường là điểm xuất phát phù hợp ở biên nhạy cảm: chỉ mở các luồng đã được phê duyệt. Với hệ thống cũ có chính sách mặc định khác, phải lập kế hoạch chuyển đổi theo giai đoạn để không cắt phụ thuộc ngoài dự kiến.

Ngoại lệ tạm thời phải có mục đích, owner, phạm vi, ngày hết hạn, biện pháp bù đắp và mốc đánh giá lại. Một exception không có thời hạn thường biến thành quyền tồn tại vô thời hạn dù nhu cầu ban đầu đã kết thúc.

### 3.3. Tách trách nhiệm và quản trị theo rủi ro

Người yêu cầu thay đổi không nên là người duy nhất phê duyệt chính yêu cầu đó. Với thay đổi rủi ro cao, cần ít nhất đánh giá độc lập của bên chịu trách nhiệm bảo mật và chủ sở hữu dịch vụ. Ở nhóm nhỏ có thể không đủ vai trò tách biệt hoàn toàn; khi đó cần **người kiểm tra độc lập**, log không thể sửa tùy ý và xét duyệt sau triển khai.

Việc phê duyệt **chấp nhận rủi ro** khác với **xác nhận kỹ thuật có thể triển khai**. Ví dụ security reviewer xác minh phạm vi được giới hạn; owner nghiệp vụ chấp nhận thời gian gián đoạn; network engineer xác minh routing/NAT; người có thẩm quyền mới cho phép triển khai vào sản xuất.

### 3.4. Phê duyệt phải gắn với đúng phiên bản cấu hình

Một yêu cầu được chấp thuận cho rule A không tự động có hiệu lực nếu người triển khai thay thành A + một rule khác. Với IaC hoặc thiết bị có candidate config, lưu commit/revision/hash và diff đã phê duyệt. Nếu diff sau phê duyệt thay đổi về nguồn, đích, hành động hoặc tác động, phải **đánh giá/phê duyệt lại** theo ngưỡng của tổ chức.

## 4. Phân loại thay đổi để chọn luồng phê duyệt

Tên và ngưỡng thay đổi do tổ chức quy định; mô hình dưới đây là ví dụ thực hành.

| Loại thay đổi | Điều kiện điển hình | Cách phê duyệt |
|---|---|---|
| **Standard (đã chuẩn hóa)** | Lặp lại, ít rủi ro, mẫu được kiểm chứng, điều kiện và rollback cố định | Phê duyệt trước cho **đúng mẫu**; mỗi lần thực thi vẫn ghi ticket và bằng chứng |
| **Normal – thấp/trung bình** | Quyền mới có phạm vi nhỏ, hệ thống không nhạy cảm, tác động đã hiểu | Owner ứng dụng + người thẩm định kỹ thuật/bảo mật theo policy |
| **Normal – cao** | Internet-facing, quản trị, sản xuất quan trọng, thay đổi phân đoạn, ảnh hưởng nhiều hệ thống | Security owner, chủ dịch vụ và change authority/CAB theo quy chế |
| **Emergency** | Khai thác đang diễn ra hoặc sự cố cần chặn/khôi phục khẩn | Thẩm quyền khẩn cấp được ủy quyền; giới hạn phạm vi, ghi nhận ngay và rà soát sau |
| **Exception / risk acceptance** | Yêu cầu vượt chuẩn như mở quyền rộng hơn baseline | Thẩm định rủi ro, thời hạn, kiểm soát bù đắp và chấp thuận của người có thẩm quyền chịu rủi ro |

Một thay đổi có thể **rủi ro bảo mật thấp** nhưng **rủi ro vận hành cao**. Chặn subnet bị tấn công có thể giảm nguy cơ xâm nhập, nhưng ảnh hưởng tới hệ thống thanh toán nếu cùng dải IP. Hai khía cạnh phải được đánh giá riêng.

Không tự động coi thay đổi rollback là vô hại: khôi phục cấu hình cũ có thể mở lại lỗ hổng đã được bịt hoặc phá lệch trạng thái giữa các node HA.

## 5. Thông tin tối thiểu trong phiếu yêu cầu

### 5.1. Thông tin nghiệp vụ và hệ thống

Phiếu nên trả lời: **Tại sao cần thay đổi? Ai cần quyền nào? Khi nào? Trong bao lâu?** Đồng thời ghi:

1. ID ticket, người đề xuất, owner dịch vụ, môi trường và khung triển khai.
2. Mục tiêu nghiệp vụ, lý do không dùng phương án ít quyền hơn.
3. Tài sản nguồn/đích và định danh ổn định: IP/CIDR, hostname, CMDB ID, cloud resource ID, tag, namespace, nhóm quyền.
4. Giao thức, port, chiều kết nối, vùng mạng, address family IPv4/IPv6.
5. Policy/rule hiện tại, diff đề xuất, vị trí chèn và thiết bị/zone thực thi.
6. Ảnh hưởng dự kiến tới ứng dụng, backup, giám sát, DNS, VPN, người dùng và đối tác.
7. Đánh giá rủi ro, biện pháp giảm thiểu, thẩm định bảo mật, chủ sở hữu chấp nhận rủi ro còn lại.
8. Kế hoạch triển khai, phép thử chức năng và bảo mật, điều kiện dừng, rollback.
9. Danh sách phê duyệt, trạng thái, ngày hết hạn, bằng chứng thực thi và review sau triển khai.

### 5.2. Bảng luồng dạng có cấu trúc

| Trường | Ví dụ | Cần lưu ý |
|---|---|---|
| Source | `app-prod-01`, `10.20.10.21/32` | IP động, NAT, tag và identity có thể làm nguồn thay đổi |
| Destination | `db-prod-01`, `10.30.40.15/32` | Tài sản thực tế đằng sau VIP, LB hoặc DNAT |
| Protocol / port | TCP/5432 | TCP/UDP khác nhau; port nguồn tạm thời không phải port đích |
| Direction | App → DB | Xét cả luồng trả lời và firewall statefulness |
| Environment / zone | Production App → Production DB | Đảm bảo không vô ý mở dev/guest/Internet |
| Action | ALLOW | Rule trước đó có DENY/ALLOW khác hay bị shadow không? |
| Scope / identity | Hai instance app đã đăng ký | Nhóm lớn có thể tự thêm thành viên ngoài ý muốn |
| Validity | 30 ngày hoặc lâu dài có review | Tạm thời nên có auto-expiry khả thi |
| Evidence | Ticket, sơ đồ, traffic log, dependency | Log có thể chứa thông tin nhạy cảm; lưu theo quyền |
| Rollback | Xóa đúng rule hoặc revert commit | Không phá các thay đổi độc lập đến sau |

Với NAT, proxy, load balancer, IPv6, cloud tag hoặc Kubernetes, một địa chỉ IP không đủ để xác định định danh và vị trí thực thi. Phải mô tả **trước/sau NAT** và nơi rule được áp dụng. FQDN rule nếu có thể không đồng nhất với URL path hoặc mTLS identity.

## 6. Thẩm định rủi ro trước phê duyệt

### 6.1. Các chiều đánh giá

| Chiều rủi ro | Câu hỏi | Tín hiệu nâng mức |
|---|---|---|
| **Độ nhạy tài sản** | Đích là database, IAM/AD, backup, control plane, production không? | Tài khoản đặc quyền, dữ liệu nhạy cảm, dịch vụ lõi |
| **Mức mở rộng truy cập** | Quyền tăng từ một máy tới /24, /16 hoặc Internet? | `0.0.0.0/0`, `::/0`, `any`, broad port range |
| **Biên tin cậy** | Có vượt Internet ↔ internal, user ↔ server, dev ↔ prod, guest ↔ management không? | Bỏ qua firewall/segmentation, expose management plane |
| **Biện pháp kiểm soát** | Có TLS, MFA, bastion, authorization, WAF/IPS, logging không? | Đề nghị tắt kiểm soát hoặc giảm audit |
| **Phụ thuộc vận hành** | Chặn/mở có thể làm gián đoạn những dịch vụ nào? | Shared infrastructure, HA, failover, DR, routing lõi |
| **Khả năng kiểm chứng** | Có lab, traffic baseline, cả positive và negative test? | Thiếu telemetry, không biết nguồn, không có rollback |
| **Thời gian và ngoại lệ** | Quyền tạm thời hay lâu dài; ai sẽ đóng? | Không có hạn, không có owner |
| **Tác động khi bị lạm dụng** | Nếu tài khoản/host nguồn bị chiếm, kẻ tấn công tới được đâu? | Lateral movement vào vùng dữ liệu/identity nhạy cảm |

Có thể lập hai mức riêng: **rủi ro bảo mật** (ví dụ thấp/trung bình/cao) và **rủi ro gián đoạn** (thấp/trung bình/cao). Sau đó áp dụng ma trận phê duyệt của tổ chức, không dùng một điểm số giả chính xác để thay cho suy xét kỹ thuật.

### 6.2. Bộ câu hỏi của security reviewer

- Có thể thực hiện bằng **service identity, private endpoint, bastion hoặc proxy** thay vì mở IP/port rộng không?
- Nguồn/đích đã được định danh đúng vai trò, cùng môi trường và chủ sở hữu chưa?
- Quy tắc mới có phá **deny boundary** đang bảo vệ database, management plane hoặc guest không?
- Đường đi qua HA/failover, VPN, NAT, IPv6, cloud peering có còn cùng policy không?
- Có rule cũ bị shadow, duplicate, object group quá rộng hoặc quyền kế thừa ngoài dự kiến không?
- Cơ chế ghi log, phát hiện và kiểm soát truy cập ở lớp ứng dụng có đủ không?
- Có phương án hết hạn và rà soát định kỳ cho quyền cấp lâu dài không?

### 6.3. Minh họa đánh giá một đề xuất

Yêu cầu ban đầu: “Mở TCP/5432 từ toàn bộ `10.20.0.0/16` vào DB sản xuất cho dễ kết nối”.

Thẩm định cho thấy chỉ `10.20.10.21` và `10.20.10.22` thuộc nhóm ứng dụng hợp lệ cần kết nối. Đề xuất được chỉnh thành hai nguồn `/32`, một đích DB và một port TCP/5432, kèm tài khoản database có quyền tối thiểu và logging.

**Thay đổi phạm vi cấp quyền** là nội dung quyết định quan trọng của phê duyệt. Sự đồng ý với bản yêu cầu rộng **không** được tự động chuyển thành quyền triển khai mọi rule tương tự về sau.

## 7. Vai trò và quyền hạn: ai phê duyệt điều gì?

| Vai trò | Trách nhiệm chính | Ranh giới thẩm quyền |
|---|---|---|
| **Requester** | Mô tả nhu cầu, cung cấp thông tin và kết quả kiểm thử nghiệp vụ | Không tự phê duyệt rủi ro của chính mình khi chính sách yêu cầu kiểm tra độc lập |
| **Application / Business Owner** | Xác thực nhu cầu, lịch tác động, chấp nhận hậu quả kinh doanh | Không thay thế đánh giá điều kiện bảo mật |
| **Network / Platform Engineer** | Phân tích route, NAT, ACL, phụ thuộc, tính khả thi và rollback | Triển khai theo cấu hình đã được chấp thuận |
| **Security Reviewer / Security Owner** | Kiểm tra least privilege, segmentation, threat model, control bù đắp và log | Phê duyệt kỹ thuật bảo mật hoặc đề xuất từ chối/escalate |
| **Change Manager / CAB** | Điều phối thời điểm, xung đột thay đổi, thẩm quyền production theo cấp | Không mặc định là người duy nhất chấp thuận rủi ro an ninh |
| **Implementer** | Áp cấu hình đã phê duyệt, ghi log và kết quả, rollback khi cần | Không mở rộng scope ngoài change record |
| **Independent Validator** | Xác minh positive/negative tests và policy thực tế sau triển khai | Cung cấp bằng chứng, báo lỗi và không phê duyệt nếu điều kiện sai |
| **Incident Commander / Emergency Authority** | Ra quyết định giới hạn thời gian khi cần xử lý sự cố khẩn | Ghi nhận lý do khẩn, kiểm soát bù đắp và hậu kiểm |
| **Auditor / Governance** | Kiểm tra lịch sử, phân quyền, ngoại lệ, bằng chứng và chỉ số tuân thủ | Theo dõi độc lập; không nhất thiết trực tiếp triển khai |

**RACI** có thể định nghĩa theo môi trường; một người có thể giữ nhiều vai trò trong nhóm nhỏ nếu có kiểm soát bù đắp. Trước khi tạo rule trên production, cần xác định ai có quyền **phê duyệt nghiệp vụ**, **phê duyệt bảo mật**, **cho phép thực thi** và **xác nhận hậu kiểm**.

## 8. Quy trình phê duyệt tiêu chuẩn

~~~mermaid
flowchart TD
  A["Tạo change request và mô tả luồng cần mở/chặn"] --> B["Xác minh owner, asset, policy hiện tại và diff đề xuất"]
  B --> C{"Thông tin đủ và nhu cầu hợp lệ?"}
  C -->|Không| D["Trả lại yêu cầu để bổ sung hoặc hủy"]
  C -->|Có| E["Đánh giá bảo mật, tác động vận hành, các phương án ít quyền"]
  E --> F{"Có ngoại lệ hoặc rủi ro cao?"}
  F -->|Có| G["Security owner, business risk owner, change authority theo policy"]
  F -->|Không| H["Phê duyệt theo cấp standard/normal"]
  G --> I{"Được chấp thuận đúng scope?"}
  H --> I
  I -->|Không| J["Từ chối hoặc chỉnh lại diff và đánh giá lại"]
  J --> B
  I -->|Có| K["Chốt phiên bản config, change window, rollback và test plan"]
  K --> L["Triển khai canary hoặc maintenance window có giám sát"]
  L --> M["Kiểm thử allow + deny, identity, logging, failover"]
  M --> N{"Đạt tiêu chí và đúng approved diff?"}
  N -->|Không| O["Dừng, rollback hoặc xử lý theo runbook"]
  N -->|Có| P["Lưu bằng chứng, cập nhật inventory, đóng change"]
  O --> Q["Ghi sự cố và đánh giá lại trước triển khai tiếp"]
~~~

Các bước chi tiết:

1. **Tiếp nhận:** requester điền mục đích, owner, flow, timeframe và yêu cầu cụ thể. Tạo ID duy nhất, gắn tài sản, môi trường và ticket liên quan.
2. **Xác minh thực trạng:** network engineer kiểm tra rulebase hiện hành, route/NAT, security group, policy kế thừa, dependency và traffic baseline.
3. **Đánh giá:** security reviewer và application owner đánh giá độ cần thiết, phương án thay thế ít quyền, tác động khi lạm dụng và tác động gián đoạn.
4. **Phê duyệt:** cá nhân/nhóm đúng thẩm quyền chấp thuận **phiên bản diff** và điều kiện như expiration, logging, test cases, rollback. Trường hợp từ chối phải ghi lý do.
5. **Lập lịch và khóa scope:** xác định phiên bản cấu hình, target devices, trình tự, backup, thông báo và điều kiện dừng.
6. **Triển khai:** áp dụng theo runbook, canary/staging nếu phù hợp. Mọi sửa ngoài scope cần đánh giá lại theo quy trình.
7. **Kiểm chứng:** đối chiếu policy thực tế với diff đã duyệt; kiểm tra luồng hợp lệ, bị cấm, giám sát, ảnh hưởng dịch vụ và đường dự phòng.
8. **Đóng thay đổi:** lưu bản ghi phê duyệt, log người thực hiện, thời điểm, kết quả test, rollback nếu có, owner và ngày review/hết hạn.

Mỗi bước có thể tự động hóa một phần, nhưng **bằng chứng quyết định** và **thẩm quyền cấp quyền** vẫn phải được bảo đảm.

## 9. Kiểm tra kỹ thuật theo lớp thực thi

### 9.1. Firewall, ACL, NAT và định tuyến

Thẩm định cần xem **effective policy**, không chỉ một rule mới. Một số câu hỏi quan trọng:

- Rule có được đánh giá theo thứ tự first-match, last-match hay nguyên tắc khác của sản phẩm không?
- Rule mới có bị rule trước đó che khuất (*shadowing*) hoặc làm thay đổi kết quả của luồng khác không?
- Object group có đang tham chiếu nhiều host, zone hoặc port hơn dự kiến?
- Sau DNAT/SNAT, thiết bị thực sự thấy source/destination nào? ACL áp dụng trước hay sau NAT?
- Phân luồng qua nhiều firewall, route bất đối xứng, HA và đường failover có giữ rule tương đương?
- Cần stateful return traffic hay có ACL stateless cần rule chiều ngược?
- Có rule IPv6 tương đương hoặc rò đường IPv6 ngoài dự kiến không?
- Log các quyết định mới có được gửi đúng nơi, với độ nhạy dữ liệu phù hợp không?

**“Rule Allow tồn tại” không chứng minh kết nối thực sự được phép**, và **“Rule Deny tồn tại” không chứng minh mọi đường đều bị chặn**. Cần nhìn cấu hình hiệu lực, thứ tự đánh giá và đường đi.

### 9.2. VPN, IAM và chính sách quản trị

Mở network path tới hệ thống nhạy cảm phải đi kèm xác thực/ủy quyền ở nơi phù hợp:

- Nhóm người dùng VPN nào được route tới subnet nào? Split tunnel, source NAT, DNS và MFA có thay đổi không?
- API/SSH quản trị có yêu cầu jump host/bastion, xác thực mạnh và audit không?
- Có ảnh hưởng tới phiên đã xác thực trước đó và chính sách thu hồi phiên không?
- Với hệ thống identity-aware, có thể dùng danh tính dịch vụ thay cho IP động không?
- Khi IdP/RADIUS lỗi, chính sách fail-closed/restricted mode còn nguyên không?

### 9.3. DNS, proxy, WAF và IDS/IPS

- **DNS:** mở resolver hoặc thay egress DNS có cho phép client bỏ DNS filtering hoặc rò internal domain không? TCP và UDP 53, DoT/DoH quản lý theo chính sách.
- **Proxy/egress:** FQDN allowlist có dựa vào certificate/SNI, DNS, path hay chỉ IP? CDN/shared IP có làm phạm vi rộng hơn dự kiến?
- **WAF/IDS/IPS:** ngoại lệ để tránh false positive có chỉ áp dụng đúng path, signature, host, source và thời gian không? Có làm mất giám sát trên toàn bộ ứng dụng không?
- **Load balancer:** listener, backend group, mTLS/TLS, health check và quyền backend có được quản lý cùng change không?

### 9.4. Cloud security groups và Kubernetes

- Security group thường có cách kết hợp rule và statefulness riêng; NACL/NSG hoặc firewall khác có thể có semantics, thứ tự và default khác. Đọc **chính sách áp dụng thực tế của nền tảng** trước khi phê duyệt.
- `0.0.0.0/0` và `::/0` là hai phạm vi mở riêng; không bỏ qua IPv6.
- Cloud tag/resource group có thể mở rộng tập workload khi tài nguyên mới được gắn tag; cần owner quản lý lifecycle.
- Route table, NAT gateway, load balancer, private endpoint và peering có thể đổi đường đi thực tế mà một security group đơn lẻ không thể mô tả.
- Kubernetes `NetworkPolicy` là tập policy cho pods/namespace và phụ thuộc CNI hỗ trợ enforcement. Một policy allow mới có thể cộng gộp với các policy allow khác. Xóa một allow rule không nhất thiết tạo deny nếu còn rule khác.
- Khi sửa Ingress/Service, phải xem port publication, TLS, authentication và quyền liên vùng; metadata `containerPort` không tự là firewall rule.

## 10. Phê duyệt bằng Policy as Code và quy trình Git

Với hệ thống có Infrastructure as Code (IaC), firewall automation hoặc cloud API, nên quản lý chính sách dưới dạng **cấu hình có phiên bản**, gắn mã ticket và pull request.

### 10.1. Luồng làm việc tham khảo

1. Requester tạo ticket và mô tả nhu cầu.
2. Engineer thay policy trên branch riêng, tạo diff và tham chiếu ticket.
3. Hệ thống CI kiểm tra syntax/schema, format, forbidden broad ranges, expiry, environment guardrails và rule duplication nếu hỗ trợ.
4. Người thẩm định xem diff thực tế, test plan, ảnh hưởng và phê duyệt đúng commit.
5. Pipeline áp candidate config vào staging, chạy kiểm thử truy cập/phân đoạn hoặc policy simulation.
6. Sau phê duyệt production, deploy có khóa phiên bản và kiểm soát concurrency; ghi người/automation, thời gian, revision.
7. Post-deploy kiểm tra effective policy; nếu drift hoặc test fail thì dừng/rollback theo runbook.

**Kiểm thử tĩnh không thay thế hoàn toàn thử nghiệm mạng:** thứ tự rule, routing, identity, DNS, NAT và kiểm soát ở nhiều nơi có thể thay đổi kết quả thực.

### 10.2. Pseudopolicy có giới hạn

Ví dụ dưới đây là **định dạng minh họa để review**, không phải cấu hình áp trực tiếp lên vendor:

~~~yaml
change:
  id: "NET-CHG-2026-014"
  owner: "payments-application-team"
  environment: "production"
  rationale: "Two application nodes require PostgreSQL access"
  expires_at: null              # permanent with scheduled review
  review_due: "2027-02-28"
policy:
  action: "allow"
  direction: "app_to_database"
  sources:
    - "10.20.10.21/32"
    - "10.20.10.22/32"
  destinations:
    - "10.30.40.15/32"
  protocol: "tcp"
  destination_ports: [5432]
  logging: "enabled"
  enforcement_zone: "prod-app-to-db"
testing:
  positive:
    - "Authorized app nodes can reach PostgreSQL with approved credentials"
  negative:
    - "User VLAN cannot reach database TCP/5432"
    - "Guest network cannot reach production DB"
approval:
  business_owner: "pending"
  network_reviewer: "pending"
  security_reviewer: "pending"
  change_authority: "pending"
~~~

Trước triển khai, tất cả trạng thái `pending` liên quan phải chuyển thành quyết định hợp lệ có người chịu trách nhiệm, timestamp và version. `expires_at: null` không đồng nghĩa miễn review; chỉ thể hiện quyền lâu dài có chu kỳ xét lại.

### 10.3. Guardrail tự động nên có

| Guardrail | Phát hiện | Ngoại lệ hợp lệ |
|---|---|---|
| Từ chối inbound quản trị từ Internet | Source `0.0.0.0/0` hoặc `::/0` tới SSH/RDP/API admin | Nếu thực sự cần thiết, chỉ theo quy trình chấp nhận rủi ro rất nghiêm ngặt |
| Cảnh báo quyền any-any | Nguồn/đích/cổng quá rộng | Kịch bản đặc biệt phải có thời hạn, phân tích và thẩm quyền |
| Yêu cầu owner/expiry | Rule không có chủ sở hữu hoặc ngoại lệ không có hạn | Rule lâu dài có review_due và owner rõ |
| Kiểm tra source/target environment | Dev được phép tới prod trái thiết kế | Có dependency hợp lệ đã xem xét độc lập |
| Kiểm tra trùng lặp và shadow | Quy tắc mới không tác động hoặc làm mở rộng ngoài ý muốn | Chỉ chấp nhận nếu có phân tích và chứng cứ |
| Policy drift | Cấu hình thực tế khác revision được duyệt | Emergency change phải tạo hậu kiểm và cập nhật source of truth |

Tự động từ chối trong pipeline cần tránh chặn các kịch bản hợp lệ vì cú pháp nhiều sản phẩm có khác biệt. Những trường hợp không thể xác định nên chuyển sang **review thủ công**, không tự động phê duyệt.

## 11. Kế hoạch triển khai an toàn và rollback

### 11.1. Điều kiện tiên quyết

- Phê duyệt đầy đủ trên **đúng diff**, không còn sửa nội dung ngoài phạm vi.
- Sao lưu cấu hình/rule/đối tượng liên quan và biết cách phục hồi.
- Có bản đồ dependency, baseline traffic, owner ứng dụng xác nhận khung bảo trì.
- Có quyền OOB/console hoặc đường quản trị thay thế khi thay đổi có thể ảnh hưởng management plane.
- Có phép kiểm thử allow/deny từ những nguồn mạng thực tế, bao gồm IPv6 nếu áp dụng.
- Có người chịu trách nhiệm thực thi, người xác minh độc lập và người điều phối rollback.
- Với HA, đảm bảo node dự phòng có policy tương đương và failover không thay đổi kết quả phân đoạn.

### 11.2. Mẫu trình tự thực hiện

1. Ghi snapshot hiện tại, phiên bản cấu hình, tình trạng thiết bị và health ứng dụng.
2. Xác minh phê duyệt còn hiệu lực và đúng ticket, mục tiêu, nguồn/đích/port.
3. Triển khai từng vùng/đối tượng nhỏ hoặc trên staging/canary khi có thể.
4. Theo dõi log và truy cập, kiểm tra từng thay đổi theo bước.
5. Chạy positive test, negative test và kiểm chứng log đến hệ thống giám sát.
6. So sánh effective config với diff đã duyệt; ghi sai khác hoặc phát hiện quyền quá rộng.
7. Chờ thời gian quan sát tối thiểu, xác minh dịch vụ liên quan ổn định.
8. Đóng change kèm bằng chứng, hoặc rollback nếu có điều kiện dừng.

### 11.3. Kế hoạch rollback không được chỉ ghi “revert”

Rollback nên xác định:

- **Điểm phục hồi:** revision/rule ID cụ thể, backup, đối tượng và chính sách liên quan.
- **Điều kiện kích hoạt:** đứt giao dịch quan trọng, mở truy cập trái phép, mất logging hoặc quản trị, độ trễ vượt ngưỡng.
- **Trình tự:** rollback một rule hay nhiều tài nguyên, thứ tự cho HA/NAT/route, giới hạn blast radius.
- **Bảo toàn thay đổi khác:** không ghi đè các change độc lập được phê duyệt sau thời điểm snapshot.
- **Xác minh sau rollback:** kiểm tra lại positive/negative tests, logging, HA và các nguồn/đích liên quan.
- **Người ra quyết định và timestamp:** ai đã dừng/khôi phục, lý do và thời gian thực hiện.

Trên thiết bị hỗ trợ **commit confirmed / auto-rollback**, có thể dùng cơ chế xác nhận trong cửa sổ ngắn để giảm rủi ro mất quản trị. Tính năng và cú pháp tùy sản phẩm; cần thử tại lab trước.

## 12. Kiểm chứng sau thay đổi: cả allow và deny

### 12.1. Ma trận kiểm thử

Giả sử ứng dụng `app-prod-01` và `app-prod-02` được quyền kết nối database `db-prod-01` qua TCP/5432.

| Mã | Phép thử | Kỳ vọng | Nguồn chứng cứ |
|---|---|---|---|
| P1 | `app-prod-01` → DB TCP/5432 | Kết nối hợp lệ và truy vấn kiểm tra không phá dữ liệu thành công | Client log + firewall + DB audit |
| P2 | `app-prod-02` → DB TCP/5432 | Thành công với danh tính được ủy quyền | Client log + DB audit |
| N1 | Máy ở User VLAN → DB TCP/5432 | Bị chặn | Kết quả thử + log enforcement |
| N2 | Guest VLAN → DB TCP/5432 | Bị chặn | Kết quả thử + policy/log |
| N3 | App node → DB port quản trị ngoài nhu cầu | Bị chặn nếu không thuộc luồng đã duyệt | Firewall + kiểm tra dịch vụ |
| N4 | Nguồn IPv6 không được duyệt → DB | Bị chặn nếu đích có IPv6 | IPv6 policy/flow log |
| O1 | Kiểm tra các dependency liên quan | Không phát sinh lỗi bất thường | Health check, app logs, metrics |
| H1 | Kiểm thử trên HA/đường dự phòng khi thuộc phạm vi | Policy không nới rộng | Standby config + path probe |

**Kết nối TCP thành công không đồng nghĩa tài khoản ứng dụng đã được ủy quyền.** Cần kiểm thử đúng ở database/application layer. Tương tự, timeout ở N1 chưa chắc do firewall chặn; hãy đối chiếu rule hit counter hoặc log ở nơi thực thi.

### 12.2. Quy trình xác minh một rule mới

~~~text
1. Xác minh nguồn client và danh tính theo thời gian (NAT, DHCP, VPN, workload ID).
2. Xác minh đích được định tuyến tới đúng tài sản/port.
3. Phát sinh request kiểm thử hợp lệ ở phạm vi được phê duyệt.
4. Ghi kết quả mạng và ứng dụng, thời gian, source/destination quan sát thực tế.
5. Kiểm tra rule hit/log trên enforcement point.
6. Chạy negative tests từ các vùng không được phép.
7. So sánh với baseline trước thay đổi, gồm IPv4 và IPv6 nếu có.
8. Kiểm tra failover/standby, giám sát và drift.
9. Đối chiếu config hiệu lực với diff đã được phê duyệt.
~~~

Có thể dùng phép đo connection hoặc functional test trên máy được phép, nhưng **không tự phát sinh traffic trên mạng ngoài phạm vi kiểm thử**. Trên môi trường production, phép thử phải được thiết kế giảm ảnh hưởng đến dữ liệu và dịch vụ.

## 13. Emergency change và quyền truy cập khẩn cấp

Khi có exploit đang diễn ra, tài khoản VPN bị chiếm hoặc DDoS làm dịch vụ gián đoạn, chờ đầy đủ CAB thông thường có thể không phù hợp. Tuy nhiên, **emergency không đồng nghĩa bỏ quy trình**.

Một luồng khẩn cấp cần:

1. Xác định incident ID, tình huống nguy hiểm, mục tiêu giảm thiểu và người chỉ huy được ủy quyền.
2. Chọn biện pháp **ít phạm vi nhất**: chặn IP/identity cụ thể, rate-limit hoặc cô lập vùng thay vì mở rộng hàng loạt quyền.
3. Xin phê duyệt khẩn qua kênh đã định; nếu có quyền khẩn theo runbook, ghi rõ căn cứ và người chịu trách nhiệm.
4. Lưu cấu hình trước, triển khai có khả năng rollback và giám sát liên tục.
5. Xác minh bảo mật và ảnh hưởng dịch vụ ngay sau thay đổi.
6. Đặt thời hạn tự hết hoặc ngày rà soát rất gần; thực hiện **post-implementation review** khi tình huống ổn định.

**Ví dụ:** cần chặn kết nối từ một subnet bị lạm dụng tới quản trị cloud. Owner an ninh phê duyệt rule deny khẩn; đội mạng triển khai và kiểm tra các tác vụ thiết yếu từ subnet đó có bị ảnh hưởng. Sau sự cố, đối chiếu IOC, đánh giá có tiếp tục chặn hay loại bỏ rule và cập nhật kiến trúc phân đoạn.

Tài khoản **break-glass** phải có quyền hạn được kiểm soát, giám sát, ghi log, lưu bí mật an toàn và quy trình hậu kiểm. Không dùng quyền khẩn cấp để cấp truy cập “any-any” không có owner/expiry.

## 14. Quản lý ngoại lệ, ngày hết hạn và rà soát định kỳ

Một change được phê duyệt hôm nay có thể không còn phù hợp sau khi dịch vụ được chuyển sang cloud, host bị xóa, subnet đổi vai trò hoặc tài khoản bị thu hồi.

### Vòng đời của rule

~~~mermaid
flowchart LR
  A["Đề xuất"] --> B["Phê duyệt"]
  B --> C["Triển khai và xác minh"]
  C --> D["Giám sát và review"]
  D --> E{"Còn nhu cầu?"}
  E -->|Có| F["Xác nhận owner, scope, expiry/risk"]
  F --> D
  E -->|Không| G["Xóa rule qua change và kiểm chứng"]
  D --> H["Phát hiện drift hoặc exception hết hạn"]
  H --> I["Điều tra và khắc phục có kiểm soát"]
  I --> D
~~~

Review định kỳ tập trung vào:

- Rule không có hit trong khoảng thời gian đại diện (chưa đủ chứng minh có thể xóa ngay; xét DR/backup/failover).
- Quy tắc có source/target wildcard, port range rộng, ngoại lệ IDS/WAF hoặc quyền Internet-facing.
- Owner đã nghỉ/chuyển nhóm, asset bị hủy, tag cloud thay đổi, dịch vụ đã ngừng.
- Ngoại lệ đã qua hạn hoặc tạm thời bị gia hạn nhiều lần.
- Quy tắc không khớp version IaC, cấu hình thực tế và ticket.
- Chính sách mới có làm lộ management plane hoặc đường đi vòng firewall trên tuyến dự phòng.

Để xóa rule cũ, vẫn cần kiểm chứng dependency và phương án rollback như mọi thay đổi khác.

## 15. Case study: mở kết nối ứng dụng tới database sản xuất

### Tình huống

Ứng dụng thanh toán chuyển sang hai máy ứng dụng mới. Khi kiểm thử staging, ứng dụng không mở được phiên PostgreSQL tới database sản xuất. Nhóm phát triển đề nghị:

> “Mở toàn bộ TCP từ `10.20.0.0/16` sang `10.30.40.0/24` để không còn lỗi.”

Phạm vi đề xuất rộng và có nguy cơ mở truy cập từ những máy không liên quan vào nhiều hệ thống DB.

### Bước 1 — Làm rõ nhu cầu

Owner ứng dụng xác nhận chỉ hai instance mới `10.20.10.21` và `10.20.10.22` cần kết nối DB `10.30.40.15` qua TCP/5432. Cổng quản trị DB không được mở. Database dùng xác thực riêng, ứng dụng cần TLS và audit theo chính sách.

### Bước 2 — Tìm cấu hình hiện hữu

Network engineer xem route, NAT, rule firewall app-to-db, object group, HA và traffic logs. Xác minh không có proxy hoặc SNAT khiến IP nguồn quan sát trên firewall khác với IP instance. Reviewer cũng kiểm tra đường truy cập qua môi trường dev hoặc guest.

### Bước 3 — Phân loại rủi ro và phê duyệt

Đích là production database chứa dữ liệu quan trọng, nên dù phạm vi mới đã thu hẹp, thay đổi vẫn cần security reviewer và owner ứng dụng chấp thuận. Thẩm quyền triển khai production được xác định theo lịch change.

Thay đổi được phê duyệt **chỉ** cho hai nguồn /32, một đích /32, TCP/5432, logging bắt buộc, kiểm tra quyền DB và review theo lịch.

### Bước 4 — Triển khai và kiểm chứng

Sau khi lưu snapshot, engineer áp rule có ID gắn ticket. Kiểm tra kết nối ứng dụng từ hai nguồn và một truy vấn đọc thử; đồng thời thử từ User VLAN và Guest VLAN để bảo đảm vẫn bị chặn. Xem log/flow thực tế, kiểm tra standby HA có policy tương đương.

### Bước 5 — Kết thúc

Reviewer đối chiếu diff cuối, kết quả P1/P2/N1/N2, thời gian triển khai và quyền còn hiệu lực; cập nhật sơ đồ dependency và danh mục rule. Nếu có thêm nguồn thứ ba phát sinh, đó là **một yêu cầu mở rộng scope mới** cần thẩm định trước khi thêm.

### Mẫu bản ghi quyết định

~~~yaml
change_id: "NET-CHG-2026-014"
requested_at: "2026-11-28T09:00:00+07:00"
requester: "payments-app-owner"
business_reason: "New production app nodes require DB connectivity"
risk:
  security: "high"
  operational: "medium"
  rationale: "Production database boundary"
approved_scope:
  sources: ["10.20.10.21/32", "10.20.10.22/32"]
  destinations: ["10.30.40.15/32"]
  protocol: "tcp"
  ports: [5432]
  environment: "prod"
  action: "allow"
  logging: true
approval_records:
  business_owner: "approved in ticket"
  security_reviewer: "approved in ticket"
  network_reviewer: "approved in ticket"
  change_authority: "approved in ticket"
deployment:
  revision: "policy-rev-42"
  implemented_by: "network-oncall"
  rollback_revision: "policy-rev-41"
validation:
  - "Authorized app connections passed"
  - "User VLAN and guest network denied"
  - "Firewall logs and HA parity verified"
review_due: "2027-02-28"
~~~

Đây là **hồ sơ giả định** để minh họa cấu trúc; không được ghi “approved” khi chưa có quyết định thật. Tên, ID và thời gian cần được thay bằng dữ liệu thực có bằng chứng.

## 16. Theo dõi hiệu quả và bằng chứng kiểm toán

Một quy trình kiểm soát thay đổi hiệu quả cần cho phép người kiểm tra trả lời được **ai yêu cầu, ai duyệt, duyệt phạm vi nào, ai triển khai, cấu hình nào có hiệu lực và đã kiểm chứng thế nào**.

### Bằng chứng nên lưu

- Ticket, bối cảnh nghiệp vụ, tài sản và owner.
- Trạng thái cấu hình trước/sau, diff, revision/hash, rule ID và đối tượng bị tác động.
- Bản ghi phê duyệt, người có thẩm quyền, timestamp và điều kiện kèm theo.
- Kế hoạch triển khai, cửa sổ thay đổi, kết quả thực tế, cảnh báo và nhật ký người/automation thực hiện.
- Kết quả positive/negative tests, bằng chứng tại enforcement point và hệ thống đích.
- Kế hoạch và kết quả rollback nếu cần, thời điểm cập nhật CMDB/IaC, expiry/review.
- Liên kết incident ID, post-change review và quyết định chấp nhận rủi ro khi có ngoại lệ.

Không dán mật khẩu, token, private key hoặc dữ liệu cá nhân không cần thiết vào ticket chia sẻ rộng. Bằng chứng cần lưu ở kho có quyền truy cập thích hợp và chính sách lưu giữ của tổ chức.

### Chỉ số vận hành mẫu

| Chỉ số | Ý nghĩa |
|---|---|
| Tỷ lệ thay đổi có phê duyệt hợp lệ trước triển khai | Đo mức tuân thủ luồng cấp quyền |
| Tỷ lệ change có diff và rollback/test plan | Đo mức chuẩn bị để triển khai và khôi phục |
| Tỷ lệ thay đổi vượt scope đã duyệt | Phát hiện lệch quy trình hoặc lỗi automation |
| Tỷ lệ rule không owner/hết hạn chưa xử lý | Đo nợ quyền truy cập |
| Số lần positive/negative test thất bại | Phát hiện regression về khả dụng và bảo mật |
| Số trường hợp policy drift | Phát hiện cấu hình ngoài hệ thống phê duyệt |
| Thời gian xử lý change theo nhóm rủi ro | Đo khả năng đáp ứng, không khuyến khích duyệt vội |
| Tỷ lệ emergency change được hậu kiểm đúng hạn | Đo kỷ luật của luồng khẩn |

Tối ưu thời gian duyệt **không được đánh đổi** bằng việc bỏ qua thẩm định, xác nhận owner hoặc phép thử ranh giới bảo mật.

## 17. Các sai lầm thường gặp

| Sai lầm | Tác động | Cách phòng tránh |
|---|---|---|
| Phê duyệt “mở port” không có source/destination/owner | Không biết quyền được cấp cho ai | Bắt buộc ma trận luồng và lý do nghiệp vụ |
| Chấp thuận source `any` để xử lý sự cố tạm | Mở rộng bề mặt tấn công lâu dài | Giới hạn scope và ngày hết hạn, có review |
| Xem rule riêng lẻ nhưng bỏ qua rulebase | Duplicate/shadow, quyền effective rộng hơn dự tính | Review effective policy, NAT, route, thứ tự rule |
| Không kiểm tra tuyến dự phòng | Failover đi vòng enforcement | Xem HA/route và negative tests trên đường dự phòng |
| Chỉ test kết nối được phép | Guest/user có thể truy cập tài sản nhạy cảm | Luôn có negative tests phù hợp |
| Chỉ đánh giá security mà quên vận hành | Gây outage, mất đường OOB hoặc gián đoạn backup | Có owner dịch vụ và rollback/health plan |
| Người yêu cầu tự duyệt và triển khai không review | Không có kiểm tra độc lập | Tách thẩm quyền, hoặc kiểm soát bù đắp ở đội nhỏ |
| Sửa config sau khi được duyệt | Phê duyệt không còn gắn đúng diff | Khóa version/commit, đánh giá lại khi đổi scope |
| Không quản lý expiry và owner | Tồn tại rule lỗi thời hoặc không ai chịu trách nhiệm | Inventory, review định kỳ, dọn rule theo change |
| Chỉ quản lý IaC, bỏ cấu hình thực tế | Manual hotfix và drift không được ghi nhận | Reconcile nguồn cấu hình và thiết bị |
| Emergency change bỏ mọi audit | Quyền khẩn tồn tại mãi và khó truy vết | Ghi incident, người duyệt, expiry và hậu kiểm |
| Rollback bằng snapshot toàn bộ | Ghi đè thay đổi khác hoặc mở lại rủi ro | Rollback theo rule/commit được kiểm soát và xác minh |

## 18. Checklist phê duyệt thay đổi

- [ ] Request có mục tiêu, owner nghiệp vụ, owner kỹ thuật và hệ thống đích rõ ràng.
- [ ] Có source/destination, protocol/port, direction, zone, IPv4/IPv6, định danh và thời hạn.
- [ ] Đã xem effective policy hiện tại, thứ tự rule, object group, NAT, routing, cloud inheritance và HA.
- [ ] Phạm vi quyền cấp là nhỏ nhất phục vụ nhu cầu; có lý do nếu phải mở rộng.
- [ ] Có đánh giá rủi ro bảo mật và gián đoạn, phương án ít rủi ro hơn và kiểm soát bù đắp.
- [ ] Người có thẩm quyền nghiệp vụ, bảo mật và change authority đã phê duyệt **đúng version/diff**.
- [ ] Có backup/config revision, kênh OOB, change window, owner triển khai và rollback rõ ràng.
- [ ] Có positive tests, negative tests, kiểm tra log, IPv6 và đường HA/failover khi liên quan.
- [ ] Có điều kiện dừng và người quyết định khi triển khai không như kỳ vọng.
- [ ] Có bằng chứng kết quả, policy version thực tế, ngày hết hạn/review và hồ sơ đóng change.
- [ ] Nếu là emergency hoặc exception, đã ghi thẩm quyền khẩn và thời hạn hậu kiểm.

## 19. Câu hỏi tự kiểm tra

1. Tại sao yêu cầu “mở TCP/443 cho app” chưa đủ để phê duyệt? Bạn sẽ yêu cầu bổ sung những trường nào?
2. Phân biệt phê duyệt nhu cầu nghiệp vụ, thẩm định bảo mật và xác nhận khả năng triển khai kỹ thuật.
3. Nếu rule đề xuất cho `0.0.0.0/0` vào cổng quản trị production, những lựa chọn ít rủi ro hơn là gì?
4. Vì sao một rule có source `10.20.0.0/16` có thể có rủi ro khác đáng kể so với hai host /32?
5. Nêu một ví dụ rule có vẻ an toàn nhưng bị NAT, thứ tự ACL hoặc một rule khác làm thay đổi tác động thực tế.
6. Tại sao sau khi kiểm tra P1 “app kết nối DB thành công” vẫn cần N1/N2 “user/guest không kết nối DB được”?
7. Với một security group mới, bạn sẽ thẩm định gì về IPv6, outbound rule, route table, private endpoint và workload tag?
8. Nếu người triển khai chỉnh rule thêm một subnet sau khi PR đã được phê duyệt, quy trình đúng là gì?
9. Emergency change cần những bằng chứng tối thiểu nào để không biến thành quyền truy cập vô hạn?
10. Lập change request cho hai ứng dụng gọi API nội bộ qua TCP/8443: xác định owner, flow, phân loại rủi ro, người duyệt, phép thử allow/deny và kế hoạch rollback.

**Điểm cần nhớ:** phê duyệt thay đổi network policy phải gắn **đúng nhu cầu, đúng luồng, đúng người có thẩm quyền và đúng phiên bản cấu hình**. Mỗi quyền cấp mới đều cần căn cứ, phạm vi tối thiểu, phép thử chứng minh ranh giới bảo mật vẫn đúng, phương án khôi phục và trách nhiệm xem xét lại trong suốt vòng đời.
