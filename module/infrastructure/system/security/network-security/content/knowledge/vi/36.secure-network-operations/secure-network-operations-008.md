# Quản lý cấu hình bằng version control

## 1. Vì sao cấu hình mạng cần được quản lý như mã nguồn?

Trong một hệ thống mạng, một thay đổi nhỏ về **firewall rule, VLAN, VRF, BGP route policy, VPN peer, DNS resolver, Wi-Fi access policy hoặc cloud security group** có thể làm gián đoạn dịch vụ, mở đường truy cập trái phép hoặc khiến hệ thống giám sát không còn nhìn thấy sự kiện. Quản trị cấu hình bằng **version control** giúp mọi thay đổi có lịch sử, có người chịu trách nhiệm, có thể so sánh, kiểm thử và quay lại phiên bản phù hợp khi cần.

Trong chương **Quản trị vận hành mạng an toàn** thuộc mô-đun **SECURITY_NETWORK_SECURITY**, kỹ thuật này kết nối nhiều lớp phòng vệ: phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, mạng không dây và hạ tầng cloud. Mục tiêu không chỉ là lưu các file cấu hình vào Git, mà là tạo một **quy trình kiểm soát thay đổi cấu hình** xuyên suốt từ đề xuất chính sách đến xác minh trạng thái đang hoạt động.

Ví dụ, một kỹ sư muốn mở TCP/443 từ mạng ứng dụng tới API thanh toán. Nếu chỉnh rule trực tiếp trên firewall rồi thông báo trong chat, nhóm vận hành khó trả lời ai đã cho phép, vì sao, từ lúc nào và có mở cả subnet không cần thiết hay không. Nếu sử dụng Git, pull request, policy review, kiểm thử và deployment có giám sát, thay đổi được đối chiếu với yêu cầu nghiệp vụ và điều kiện bảo mật cụ thể.

**Kết quả mong đợi của bài học:**

- Phân biệt **desired configuration**, **effective/running configuration**, **startup/saved configuration** và bản sao lưu.
- Tổ chức repository, nhánh, phiên bản, môi trường và metadata quản trị phù hợp.
- Thiết kế workflow có phê duyệt, kiểm thử, phát hành, đối chiếu drift và rollback.
- Bảo vệ bí mật trong cấu hình, khóa truy cập, runner CI/CD và kho Git.
- Áp dụng version control vào router, switch, firewall, VPN, DNS, IDS/IPS, cloud và Kubernetes.
- Xác định bằng chứng audit, thước đo vận hành và điểm dừng để triển khai an toàn.

**Nguyên tắc:** Git hỗ trợ lịch sử và review, **không tự bảo đảm cấu hình an toàn, thiết bị đã áp dụng đúng, hoặc có bản backup có thể phục hồi**.

## 2. Các loại trạng thái phải phân biệt

| Trạng thái | Ý nghĩa | Câu hỏi quan trọng |
| --- | --- | --- |
| **Desired state** | Cấu hình mong muốn đã được duyệt trong Git/IaC | Phiên bản nào là nguồn sự thật, ai phê duyệt? |
| **Rendered state** | Cấu hình tạo từ template, inventory và biến môi trường | Cấu hình cuối cùng có đúng đối tượng và giá trị? |
| **Candidate state** | Thay đổi chuẩn bị áp dụng trên thiết bị hỗ trợ transaction/commit | Có khác gì trạng thái đang chạy? |
| **Running/effective state** | Cấu hình đang có hiệu lực trên thiết bị hoặc dịch vụ | Thiết bị thực sự đang áp chính sách gì? |
| **Startup/saved state** | Cấu hình sẽ được nạp khi khởi động lại, tùy nền tảng | Có khác running state và gây lỗi sau reboot không? |
| **Observed state** | Hành vi được chứng minh bằng log, metric, flow và kiểm thử | Allow/deny trên traffic thật có đúng kỳ vọng? |
| **Backup/snapshot** | Bản sao phục vụ khôi phục hoặc pháp chứng ở một mốc thời gian | Có đủ bí mật/phụ thuộc, toàn vẹn và restore được không? |

Một commit có thể là nguồn sự thật cho **ý định cấu hình**, nhưng không phản ánh những thay đổi ngoài luồng được thực hiện trên thiết bị trong tình huống khẩn cấp. Ngược lại, cấu hình lấy từ router không nhất thiết là chuẩn phải triển khai cho các router khác vì có thể chứa **IP, interface, serial, secret hoặc session-specific parameters**.

### 2.1. Version control khác backup

| Khía cạnh | Git/version control | Backup cấu hình |
| --- | --- | --- |
| Chức năng chính | Quản lý thay đổi, review, provenance, so sánh phiên bản | Khôi phục trạng thái thiết bị/dịch vụ sau sự cố |
| Đối tượng tối ưu | Policy, template, cấu hình được phép lưu và tài liệu quyết định | Cấu hình export đủ thông tin và dependency cần thiết |
| Lịch sử | Commit, diff, tag, pull request | Recovery points, snapshots, retention |
| Bảo mật secret | Nên dùng references và kho secret riêng | Có thể phải lưu bí mật dưới mã hóa/kho kiểm soát |
| Chứng minh trạng thái thực | Không tự chứng minh đã deploy thành công | Cũng không tự chứng minh thiết bị đang chạy bản đó |
| Phục hồi thiết bị | Cần pipeline, đúng platform, secrets, firmware | Cần restore test, khóa giải mã và tương thích |

Không khuyến nghị đưa **raw running-config có credential** vào một repository rồi coi đó là cả backup lẫn version control. Có thể duy trì **repository chính sách đã làm sạch**, đồng thời có **kho backup riêng được mã hóa và bảo vệ** để phục hồi đầy đủ.

## 3. Xác định phạm vi cấu hình cần quản lý

Mỗi loại tài sản có mô hình cấu hình và phụ thuộc khác nhau.

| Loại hệ thống | Nội dung thích hợp quản lý bằng version control | Điểm cần lưu ý |
| --- | --- | --- |
| **Router, switch** | VLAN, VRF, interface template, routing policy, ACL, QoS, NTP/syslog | Dynamic routes và neighbor state không phải desired config |
| **Firewall/NGFW** | Security zones, objects, rules, NAT, logging policy, IDS profile references | Thứ tự rule, rule ID và implicit/default deny có ý nghĩa |
| **VPN** | Tunnel parameters, peer references, route/policy, authentication method | PSK, private key, certificate material cần bảo vệ riêng |
| **DNS/DHCP** | Zone definition, forwarding, resolver ACL, DHCP ranges, policy | Serial/TTL, split-horizon, secret TSIG nếu có |
| **Wi-Fi/NAC** | SSID policy, VLAN mappings, 802.1X/RADIUS integration | Thiết bị, chứng chỉ và controller database có thể lưu riêng |
| **WAF/LB/API gateway** | Listener, backend/service mapping, route, WAF rules, TLS profile references | TLS private key và secret không nên commit |
| **IDS/IPS/NDR** | Bật/tắt rule, threshold, exception có lý do, sensor routing | Rule signatures/tuning và false positives cần review |
| **Cloud network** | VPC/VNet, subnets, route tables, security group/NSG, gateway, IAM boundaries | Cloud API state và resource IDs có thể thay đổi tự động |
| **Kubernetes/CNI/mesh** | NetworkPolicy, Gateway/Ingress, mesh auth policy, namespace labels | Cần kiểm tra CNI hỗ trợ; policy có thể phụ thuộc selectors |
| **Automation/collector** | Inventory schemas, templates, validation rules, deploy workflows | CI token và runtime credentials phải ở kho riêng |

**Đừng cố đưa tất cả vào Git chỉ vì dữ liệu có thể xuất thành text.** Routing table động, ARP/NAT session, transient pod IP, private keys, token, password và customer payload có vòng đời, độ nhạy hoặc ngữ nghĩa khác nhau. Các dữ liệu này có thể phục vụ telemetry/backup nhưng không phải đối tượng commit plaintext vào Git.

### 3.1. Chọn đơn vị thay đổi

Một thay đổi có thể là một rule của firewall, một cấu hình toàn thiết bị, một DNS record hoặc một policy cho nhiều cloud account. Chọn đơn vị cho phép:

1. Owner rõ ràng.
2. Review đủ ngữ cảnh nghiệp vụ.
3. Kiểm thử có thể tái hiện.
4. Rollback không ghi đè những thay đổi độc lập.
5. Ít xung đột trong môi trường nhiều nhóm.

Ví dụ, phân tách policy theo **zone, service và environment** hữu ích hơn một file chứa mọi cấu hình của toàn tập đoàn nếu công cụ hỗ trợ tổng hợp an toàn. Nhưng phải bảo đảm bước render kiểm tra **tổng thể policy cuối** để phát hiện xung đột, trùng rule và ảnh hưởng thứ tự.

## 4. Kiến trúc GitOps/Configuration-as-Code căn bản

~~~mermaid
flowchart TD
    R[Business/network owner yêu cầu thay đổi] --> PR[Git branch + pull request]
    PR --> V[Lint, schema, security policy và diff]
    V --> A{Review + phê duyệt hợp lệ?}
    A -->|Không| X[Sửa yêu cầu hoặc từ chối]
    A -->|Có| M[Merge vào protected branch]
    M --> B[Render cấu hình với inventory được tin cậy]
    B --> S[Staging / canary / policy simulation]
    S --> D{Đạt test và change gate?}
    D -->|Không| X
    D -->|Có| P[Deploy bằng danh tính ít quyền]
    P --> O[Readback effective config + traffic test]
    O --> C{Đúng trạng thái và không tác động?}
    C -->|Có| E[Lưu deployment evidence + monitor drift]
    C -->|Không| RB[Dừng / rollback có kiểm soát]
    RB --> E
~~~

Đây là workflow tham khảo; **GitOps** nhấn mạnh quản lý trạng thái mong muốn bằng Git và quá trình reconcile của hệ thống. Không phải mọi thiết bị mạng hỗ trợ transaction hoặc reconciliation an toàn như Kubernetes. Với CLI network appliances, một số thao tác chỉ có thể thực hiện **theo lệnh và trình tự phụ thuộc**, nên phải lập kế hoạch thay đổi, kiểm thử và rollback riêng.

### 4.1. Những thành phần và trách nhiệm

| Thành phần | Vai trò | Quyền phải giới hạn |
| --- | --- | --- |
| Git repository | Source of truth cho nội dung đã phê duyệt | Merge/delete/tag và visibility có kiểm soát |
| Inventory/IPAM/CMDB | Asset ID, site, zone, role, version, owner | Chỉ nguồn dữ liệu được xác minh mới được render |
| Secret manager/PKI | Credential và certificate material | Không đưa khóa vào repository/log |
| CI validation | Kiểm tra syntax, schema, policy, diff, threat checks | Không cần quyền sửa production |
| CD/reconciler | Áp policy đã phê duyệt tới đúng tài sản | Scope theo environment/asset, có audit |
| Device/network API | Nơi áp và kiểm chứng cấu hình | Read/commit/rollback tùy chức năng và phê duyệt |
| Telemetry/monitoring | Đo allow/deny, lỗi kết nối, drift, health | Quyền chỉ đọc và bảo vệ log |
| Backup repository | Lưu recovery point, dữ liệu thiết bị thực | Tách khỏi Git và tài khoản có quyền xóa production |

**Một pipeline đủ quyền sửa mọi firewall, VPN, DNS và cloud IAM** trở thành mục tiêu tấn công cực kỳ nhạy cảm. Thiết kế hệ thống automation phải có blast radius thấp hơn hoặc ít nhất được kiểm soát chặt chẽ bằng ranh giới trust, danh tính và audit.

## 5. Tổ chức repository và phân tách môi trường

Ví dụ cây thư mục mang tính kiến trúc, không phải chuẩn bắt buộc:

~~~text
network-config/
  README.md
  schemas/
    firewall-policy.schema.json
  inventories/
    sites.yml
    devices.yml
  policies/
    common/
      dns-egress.yml
      log-forwarding.yml
    staging/
      segmentation.yml
    production/
      segmentation.yml
  templates/
    firewall-policy.j2
    router-interface.j2
  checks/
    required-controls.yml
  docs/
    change-guidelines.md
    rollback-runbook.md
  .gitignore
~~~

**Không lưu private key, PSK, secret plaintext, cloud access token hoặc raw backup có mật khẩu trong cây này.** Những giá trị cần thiết khi render/deploy được tham chiếu bằng ID tới kho secrets có phân quyền. Các tên và cấu trúc thư mục có thể khác tùy team, vendor và hệ thống quản lý thay đổi.

### 5.1. Mô hình repository

- **Monorepo:** thuận tiện kiểm soát shared policy, cross-service changes và test tổng thể; cần bảo vệ phạm vi CODEOWNERS và quyền truy cập.
- **Repo theo domain/site/đội:** giới hạn blast radius và phân quyền; cần cơ chế xử lý phụ thuộc liên repo.
- **Repo chính sách và repo triển khai riêng:** giảm quyền của nhóm review policy và runner triển khai; cần ánh xạ chính xác artifact được duyệt.

Không chọn theo sở thích Git đơn thuần. Chọn theo **ranh giới ownership, sự phụ thuộc và yêu cầu audit**, rồi kiểm chứng mô hình quyền trên server Git và CI/CD.

### 5.2. Định danh môi trường

Tách staging và production bằng **cả cấu trúc repository lẫn danh tính/credential của pipeline**. Một đường dẫn tên staging không ngăn script có quyền production áp nhầm tài nguyên. Mỗi environment nên có:

- Account/tenant/project được phép.
- Asset IDs rõ ràng.
- Protected branch/environment approval.
- Credential giới hạn đúng tài sản/operation.
- Khác biệt về change window, test gates và rollback.

## 6. Bảo vệ secrets, thông tin nhạy cảm và lịch sử Git

Một file cấu hình thiết bị có thể chứa hostname, subnet nội bộ, access rule, SNMP community, password hash, private key, pre-shared key VPN, API token hoặc certificate material. **Private Git repository vẫn có thể bị lộ** qua clone, backup của developer, CI artifacts, fork, package cache hoặc token bị chiếm.

### 6.1. Quy tắc dữ liệu

| Loại dữ liệu | Khuyến nghị | Vì sao |
| --- | --- | --- |
| Policy/rule không có secret | Có thể version control sau phân loại quyền đọc | Giúp review và diff |
| Template và tham chiếu secret | Commit ID/URI tham chiếu, không commit giá trị bí mật | Tách quyền đọc policy và quyền decrypt |
| Private key, VPN PSK, service token | Dùng secret manager, PKI hoặc kho mã hóa chuyên biệt | Rotation, audit, truy cập hạn chế |
| Raw running config có secret | Backup mã hóa riêng, kiểm soát truy cập | Dùng để restore, không phát tán qua Git |
| Config diff có secret | Redact bản báo cáo, giữ bản gốc ở kho hạn chế | Tránh lộ qua PR, review bot, log |
| IaC plan/state | Hạn chế quyền và mã hóa; state có thể chứa secret | Không coi plan/state là file vô hại |

Các giải pháp như **SOPS với KMS**, sealed secrets hoặc encryption-at-rest có thể phù hợp trong bối cảnh riêng nhưng **không tự thay thế quản trị khóa, IAM, audit và rotation**. Phải hiểu ai có quyền decrypt, việc thu hồi quyền ảnh hưởng các bản cũ ra sao và liệu secret có bị lộ ở bước render/log hay không.

### 6.2. Git ignore không xóa lịch sử

**.gitignore chỉ ngăn file chưa được track được thêm theo cách thông thường**, không xóa dữ liệu đã commit. Nếu secret vô tình được commit:

1. Ngừng chia sẻ/triển khai artifact chứa secret theo quy trình ứng phó.
2. **Rotate hoặc revoke secret**; không chỉ xóa một commit rồi coi là an toàn.
3. Đánh giá các bản clone, CI logs/artifacts, fork và những nơi có thể đã nhân bản secret.
4. Xử lý lịch sử Git theo quy trình và quyền hạn của tổ chức, phối hợp với những người đang dùng repository.
5. Ghi nhận sự cố và thêm secret scanning, review để tránh tái diễn.

Không đưa secret thật vào ví dụ bài học hoặc commit “tạm rồi xóa”. **Git history, caches và mirrors có thể còn bản cũ**.

### 6.3. Bảo vệ máy và danh tính làm việc

Bật MFA/SSO và branch protection cho kho; review quyền repository định kỳ; không cho phép force-push vào nhánh triển khai trừ quy trình được kiểm soát. Git commit ký số hoặc artifact được ký giúp xác minh nguồn/byte khi hệ thống khóa đáng tin, **không chứng minh cấu hình đã an toàn hoặc review đầy đủ**.

CI runner nên có quyền mạng tối thiểu, tách build/test khỏi deploy, cấp token ngắn hạn khi có thể và không lộ credential vào output. Tránh chạy mã từ pull request không tin cậy trên runner có production secrets.

## 7. Workflow pull request và kiểm soát thay đổi

Một thay đổi production nên có mô tả:

1. **Vì sao?** Ticket, incident hoặc yêu cầu nghiệp vụ.
2. **Cái gì?** Policy, asset, zone, port, protocol và environment.
3. **Ai?** Người đề xuất, owner, người phê duyệt, người triển khai.
4. **Tác động?** Traffic hiện hữu, nhóm người dùng, hệ thống phụ thuộc, đường đi về.
5. **Kiểm thử?** Positive, negative, failure path và kiểm tra cấu hình.
6. **Khôi phục?** Pre-change backup, version trước, thời gian rollback và quyền truy cập recovery.
7. **Quan sát?** Những log/metric chứng minh thay đổi không phá vỡ dịch vụ.

### 7.1. Ma trận trách nhiệm

| Vai trò | Quyền và nhiệm vụ |
| --- | --- |
| Requester / service owner | Xác nhận nhu cầu và phạm vi luồng nghiệp vụ |
| Network engineer | Soạn cấu hình, đánh giá topology/NAT/routing |
| Security reviewer | Kiểm tra least privilege, boundary, audit và rủi ro |
| Change approver | Quyết định được triển khai trong cửa sổ nào |
| Pipeline identity | Render/apply đúng artifact tới đúng tài sản |
| NOC/SRE/on-call | Theo dõi tác động, quyết định dừng/rollback |
| Auditor | Truy xuất version, approval, deployment và readback |

Áp dụng **separation of duties** khi mức rủi ro yêu cầu: người tạo thay đổi không nên tự bypass mọi review, tự cấp quyền và xóa audit. Không nhất thiết mọi thay đổi lab phải qua cùng quy trình production; lựa chọn dựa trên mức độ nhạy cảm.

### 7.2. Pull request cần hiển thị semantic diff

Text diff thông thường hữu ích nhưng chưa đủ cho thiết bị có rule order, object references hoặc implicit defaults. Một PR tốt nên cho biết:

- Rule nào được thêm, sửa, xóa; vị trí và độ ưu tiên.
- Source/destination zones, subnet/CIDR, protocol/port và action.
- Có mở rộng từ một host sang cả subnet hoặc **any-to-any** không.
- Có thay NAT, route, DNS, VPN, logging, IDS/IPS hay management access không.
- Rendered config có khác dự kiến; có tác động lên IPv6/UDP/QUIC không.
- Số lượng flow được thêm quyền, danh tính và thời gian exception.

Một thay đổi YAML chỉ một dòng vẫn có thể thay đổi hàng nghìn rule được render. Review phải bao gồm cả **đầu ra cuối** và những người chịu trách nhiệm ở tài sản bị ảnh hưởng.

## 8. Thực hành Git cơ bản cho một thay đổi cấu hình

Ví dụ sau **chỉ làm trên repository thử nghiệm đã được cấp quyền**, không tự áp cấu hình vào thiết bị. Giả sử thư mục đang là một Git repository có branch chính là **main** và file policy đã có:

~~~bash
# Kiểm tra nhánh hiện tại và file bị thay đổi.
git status
git branch --show-current

# Đồng bộ nhánh làm việc theo quy trình của đội.
git switch main
git pull --ff-only

# Tạo nhánh cho một thay đổi đã được duyệt.
git switch -c change/segmentation-payment-042

# Chỉ xem phần khác biệt và kiểm tra format trước khi commit.
git diff -- policies/production/segmentation.yml
git diff --check

# Chỉ stage file policy đã kiểm tra không chứa secret.
git add -- policies/production/segmentation.yml
git diff --cached

# Ghi lại lý do với mã change ticket.
git commit -m "CHG-042: limit payment ingress to approved source"

# Publish nhánh vào remote theo quyền được cấp;
# mở pull request và review, KHÔNG push thẳng production.
git push -u origin change/segmentation-payment-042
~~~

Trong ví dụ, kỹ sư phải **chỉnh file policy có chủ đích trước khi chạy git add**; lệnh trên không tự tạo hay sửa rule nào. Các hệ thống Git có thể dùng tên nhánh khác hoặc quy trình GitOps khác.

Lệnh **git diff --check** chủ yếu phát hiện lỗi whitespace, không xác nhận semantics của firewall rule. **Git commit** tạo một lịch sử thay đổi, chưa chạy kiểm thử kết nối, chưa deploy và chưa khôi phục thứ gì.

### 8.1. Đọc lịch sử và xác định phiên bản

~~~bash
# Xem lịch sử đã có của đúng file.
git log --oneline -- policies/production/segmentation.yml

# So phần thay đổi giữa hai revision đã chọn.
git diff <revision-truoc> <revision-sau> -- policies/production/segmentation.yml

# Xem nội dung chính xác tại một revision (không triển khai).
git show <revision>:policies/production/segmentation.yml
~~~

Các chuỗi **revision-truoc, revision-sau, revision** là ký hiệu placeholder; thay bằng commit/tag được xác minh trước khi chạy. Khi xử lý phiên bản chứa thông tin nhạy cảm, hạn chế nơi xuất nội dung và quyền truy cập.

## 9. Ví dụ policy theo luồng: giảm quyền thay vì mở cổng hàng loạt

Giả sử vùng **APP** chỉ được gọi **Payment API** qua TCP/8443; **GUEST** không được gọi trực tiếp; Payment service là thành phần duy nhất được truy cập Payment DB. Ví dụ dưới đây là **schema chính sách minh họa do tổ chức định nghĩa, không phải YAML được một firewall bất kỳ chấp nhận**:

~~~yaml
policy_id: payment-segmentation
version: 2
owner: network-security
environment: production
default_action: deny
rules:
  - id: allow-order-to-payment-api
    source:
      service: order-service
      zone: APP
    destination:
      service: payment-service
      zone: PAYMENT
    protocol: tcp
    port: 8443
    action: allow
    log: true
  - id: allow-payment-to-db
    source:
      service: payment-service
      zone: PAYMENT
    destination:
      service: payment-db
      zone: DATA
    protocol: tcp
    port: 5432
    action: allow
    log: true
~~~

**Cần làm rõ khi triển khai thật:**

- Các giá trị **service** phải ánh xạ tới tài sản/workload identity hoặc địa chỉ đáng tin, không tự lấy từ input người dùng.
- Kiểm tra **default deny** được engine hỗ trợ như mong đợi; thứ tự rule, statefulness, NAT và chiều reply có ý nghĩa.
- Đánh giá dependencies như DNS, NTP, identity, health check, telemetry và management plane.
- Nếu môi trường có IPv6 hoặc UDP/QUIC, phải có policy phù hợp, không mặc định rằng TCP/IPv4 bao phủ toàn bộ.
- Cổng chỉ là ví dụ; yêu cầu thực tế có thể sử dụng các cổng khác.

**Đặt policy cạnh test cases** giúp reviewer biết cấu hình kỳ vọng ngăn điều gì, thay vì chỉ nhìn một dòng **action: deny**.

### 9.1. Ma trận kiểm thử policy

| Mã test | Nguồn → đích | Kỳ vọng | Bằng chứng |
| --- | --- | --- | --- |
| T01 | Order service → Payment API TCP/8443 | Allow | Access log + firewall/CNI flow |
| T02 | Guest → Payment API TCP/8443 | Deny | Firewall deny + kiểm thử từ guest zone |
| T03 | Order service → Payment DB TCP/5432 | Deny | Firewall/NetworkPolicy và database audit |
| T04 | Payment service → Payment DB TCP/5432 | Allow | DB connection + principal audit |
| T05 | Workload ngoài allowlist → Payment service | Deny | Policy/flow log |
| T06 | Admin đã xác thực → management plane | Chỉ quyền được phê duyệt | PAM/AAA audit |
| T07 | DNS/telemetry dependencies | Đúng như kiến trúc | Resolver/syslog metrics |
| T08 | Failover hoặc route bất đối xứng (lab) | Không tạo bypass | Route/session logs |

**Chỉ thử nghiệm trên hệ thống có quyền kiểm tra.** Một phép thử kết nối thành công tới TCP/8443 chưa chứng minh ứng dụng đã xử lý request đúng hoặc người gọi có quyền nghiệp vụ; authn/authz còn phải được kiểm tra ở lớp phù hợp.

## 10. Tự động hóa CI: kiểm tra cấu hình trước khi merge

Một pipeline kiểm tra nên chạy từ rẻ và ít tác động đến đắt và phụ thuộc môi trường:

| Cổng kiểm soát | Ví dụ kiểm tra | Nếu thất bại |
| --- | --- | --- |
| Syntax/format | YAML/JSON parse, schema, naming, whitespace | Chặn merge, trả lỗi rõ |
| Inventory references | Asset/zone/service có tồn tại, owner hợp lệ | Chặn rule mồ côi hoặc sai môi trường |
| Secret scanning | Tìm token/private key/PSK/credential mẫu | Chặn và kích hoạt xử lý secret nếu có thật |
| Least privilege | Không có any-to-any, cổng quản trị mở sai zone, exception hết hạn | Chặn hoặc yêu cầu phê duyệt có căn cứ |
| Semantic diff | Rule order, NAT, route, DNS, security group, identity | Người review nhận được tác động |
| Render/compile | Template có tạo cấu hình đúng vendor/version không | Không deploy |
| Policy test | Positive, negative, conflict, default deny | Chặn merge hoặc deploy |
| Simulation/lab | Test traffic và protocol behavior tại staging | Không triển khai production |
| Drift/preflight | Thiết bị hiện tại có khác baseline hoặc policy đang thay đổi không | Dừng để điều tra và reconcile |
| Approval | Owner/security/change gate đã duyệt | Không cho production job chạy |

**Không chạy code từ pull request không tin cậy với credential production.** Một workflow CI thực thi script trong repo có thể bị sửa để in token, gửi dữ liệu ra ngoài hoặc thay artifact build. Tách **untrusted validation** khỏi **trusted deployment**, cố định dependency version, giới hạn network egress và yêu cầu artifact provenance.

### 10.1. Ví dụ logic kiểm tra rule (pseudocode)

~~~text
input: approved_policy, inventory, expected_matrix

assert approved_policy.schema_is_valid
assert policy.owner in trusted_owners
for each rule in approved_policy.rules:
    assert rule.source and rule.destination are resolvable
    assert rule.action in {allow, deny}
    assert rule.priority/order is deterministic
    reject broad admin access from untrusted zones
    reject unknown or expired exceptions

render policy for target vendor/version/environment
assert compiled policy has no unexpected broad allow
assert tests for allowed flows pass
assert tests for forbidden flows pass
produce sanitized diff + test report for human review
~~~

Đây là **pseudocode mô tả quy trình**, không phải trình thông dịch để copy và chạy. Các rule mang tính nghiệp vụ như “không mở SSH từ GUEST” phải được định nghĩa thành điều kiện kiểm thử cụ thể và được kiểm tra trên **effective policy**, không chỉ source YAML.

## 11. Triển khai cấu hình an toàn: chỉ merge chưa đủ

Một deployment cần liên kết chính xác **Git commit → rendered artifact → thiết bị/đích → trạng thái thực tế**.

### 11.1. Trước khi áp

1. Chốt artifact hash, commit ID, change ticket, target asset IDs và environment.
2. Đọc lại active/saved configuration, kiểm tra không có drift chưa được xử lý.
3. Lưu recovery point hợp lệ và bảo đảm có kênh quản trị dự phòng.
4. Kiểm tra nguồn điện, HA/failover, route, security policy, khả năng truy cập NTP/DNS/AAA.
5. Thông báo NOC/SOC và owner; thiết lập metrics và **stop conditions**.
6. Nếu thiết bị hỗ trợ candidate/transaction, dùng cơ chế validate/commit-confirmed hoặc rollback native **đúng theo vendor**.

Không giả định mọi appliance hỗ trợ atomic commit hoặc commit-confirmed. Một lệnh thay management ACL có thể khiến mất kết nối trước khi kịp apply lệnh sửa tiếp theo.

### 11.2. Khi áp

**Ưu tiên canary, từng site hoặc từng nhóm tài sản nhỏ**, không đẩy đồng thời toàn bộ cấu hình nhạy cảm. Nếu hệ thống cần nhiều bước, xác định thứ tự không làm mất DNS, identity, route, management hoặc quan hệ HA. Bảo đảm pipeline biết mình đang áp **đúng revision** đã được phê duyệt; không dựng lại cấu hình bằng dependency chưa khóa sau khi approval.

### 11.3. Sau khi áp

Read back **running/effective state** bằng cách phù hợp nhà cung cấp; so với cấu hình được render và ghi lý do nếu có chênh lệch hợp lệ. Kiểm tra các luồng:

- **Positive tests:** traffic được phép vẫn hoạt động.
- **Negative tests:** traffic phải chặn vẫn bị chặn.
- **Operational tests:** DNS, VPN, syslog, NTP, quản trị và HA còn khỏe.
- **Failure-path tests:** failover, return path và tunnel khi thuộc phạm vi kiểm thử.

Lưu deployment ID, policy version, timestamp UTC, người phê duyệt, status, log ref và kết quả kiểm chứng. **Pipeline trả success không chứng minh end-to-end behavior**.

## 12. Drift detection: phát hiện cấu hình ngoài luồng

**Configuration drift** là sai khác giữa trạng thái mong muốn được quản trị và trạng thái thực đang áp dụng. Drift có thể do thao tác thủ công, automation khác, firmware update, controller tự sửa, thay đổi hạ tầng cloud hoặc ứng cứu khẩn cấp.

### 12.1. Cách phát hiện

~~~mermaid
flowchart LR
    G[Git desired config] --> R[Render theo inventory và secrets refs]
    R --> N[Normalize config để so sánh]
    D[Device effective config readback] --> N2[Normalize theo vendor]
    N --> CMP[Semantic comparison]
    N2 --> CMP
    CMP --> Q{Có khác biệt đáng kể?}
    Q -->|Không| OK[Đã đồng bộ theo phạm vi kiểm tra]
    Q -->|Có| C[Alert, owner review và change lookup]
    C --> E{Thay đổi hợp lệ?}
    E -->|Có| A[Cập nhật Git qua review]
    E -->|Không rõ / nguy hiểm| I[Điều tra, bảo toàn chứng cứ]
~~~

**Không tự động ghi đè mọi drift ngay lập tức.** Một emergency fix có thể đang giữ production hoạt động; reconcile mù quáng có thể làm tái phát sự cố. Trước khi sửa cần xác định thay đổi có owner, ticket, nguyên nhân và mức ảnh hưởng.

### 12.2. Phân biệt drift thật với nhiễu

Một số thiết bị tự thêm timestamp, counters, dynamic routes, line order, default values hoặc session IDs. So sánh text thô dễ báo sai. Nên dùng parser/vendor API hoặc **semantic diff** hiểu cú pháp, thứ tự và reference.

Các trường thay đổi động có thể được chuẩn hóa **trong bản sao phục vụ so sánh**, nhưng không nên sửa raw backup hoặc dữ liệu gốc. Đặc biệt **thứ tự firewall rule** không thể sắp xếp tùy ý, vì đổi thứ tự có thể đổi kết quả allow/deny.

### 12.3. Khi nào auto-remediate?

Chỉ cân nhắc tự động khôi phục drift khi:

- Chính sách và giới hạn tác động rõ ràng.
- Có xác nhận không phải thay đổi khẩn cấp hợp lệ.
- Đã kiểm tra phạm vi tài sản và bảo đảm không tạo outage.
- Có canary, rollback và log chứng minh hành động.
- Tổ chức chấp nhận rủi ro auto-remediation cho lớp cấu hình đó.

Với cấu hình có thể khóa management plane hoặc thay route diện rộng, mặc định nên **cảnh báo và yêu cầu review** thay vì auto-force.

## 13. Rollback, restore và tình huống emergency

**Git revert** tạo một commit đảo thay đổi ở source; nó không tự khôi phục mọi packet path hoặc trạng thái thiết bị. **Device rollback** áp một phiên bản cấu hình cũ bằng cơ chế của platform. **Restore** là tái dựng thiết bị/dịch vụ từ bản backup, có thể cần firmware, license, certificate và secrets.

| Cơ chế | Phù hợp khi | Điều cần kiểm chứng |
| --- | --- | --- |
| Git revert | Muốn thay lại desired config và đưa qua review/deploy | Có thay đổi mới khác phụ thuộc không? |
| Native rollback/commit confirmed | Device hỗ trợ quay lại config trước theo transaction | Có giữ management và state phù hợp không? |
| Redeploy last-known-good artifact | Cấu hình trước đã kiểm thử và phù hợp hạ tầng hiện tại | Secrets, policy, dependencies có còn hợp lệ? |
| Backup restore | Thiết bị mất cấu hình/hỏng hoặc phải dựng lại | Model, firmware, license, PKI và restore test |
| Manual emergency correction | Cần duy trì dịch vụ trong sự cố và automation không khả dụng | Có incident commander, audit, cập nhật Git sau |

**Lỗi thường gặp:** muốn khôi phục connectivity nên quay lại một commit cũ nhưng commit ấy cũng xóa các rule đã được phê duyệt sau đó. Cần xem semantic diff, trạng thái live và ảnh hưởng chung, không dùng Git history như nút "Undo production" không có kiểm tra.

### 13.1. Break-glass và đồng bộ sau sự cố

Khi pipeline/IdP/Git không khả dụng, tổ chức cần phương án quản trị khẩn cấp có MFA hoặc cơ chế break-glass được bảo vệ, giới hạn quyền, audit và phê duyệt phù hợp. Sau khi khôi phục:

1. Bảo toàn trạng thái và log sự cố.
2. Xác nhận cấu hình khẩn cấp đang hiệu lực.
3. So sánh với Git desired state và điều tra chênh lệch.
4. Đưa thay đổi hợp lệ trở lại Git qua quy trình review.
5. Thu hồi quyền khẩn cấp và kiểm tra lần deploy kế tiếp không đảo nhầm sửa lỗi.

Không nên che giấu emergency changes bằng cách sửa lịch sử Git hoặc xóa audit.

## 14. Tính toàn vẹn, provenance và audit trail

Để truy vết một rule production từ ý định đến thực thi, nên liên kết:

~~~text
Requirement / Incident / Change ticket
       ↓
Pull request, reviewers và decision
       ↓
Git commit + build/render artifact hash
       ↓
CI policy/syntax/negative tests
       ↓
Deployment ID, identity, asset IDs, timestamp UTC
       ↓
Device effective config readback / backup ID
       ↓
Network telemetry và post-change validation
~~~

### 14.1. Những metadata tối thiểu

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| change_id | CHG-EXAMPLE-042 | Liên kết mục đích và approval |
| git_revision | Commit hash từ repository | Xác định source chính xác |
| artifact_hash | SHA-256 bản render đã duyệt | Chống build khác nội dung review |
| asset_id | fw-app-01 | Xác định thiết bị theo inventory |
| platform/version | Vendor OS/firmware revision | Kiểm tra tương thích |
| deployment_time_utc | Thời gian có offset UTC | Correlate log |
| deploy_identity | Service identity có quyền giới hạn | Truy cứu thao tác |
| pre_change_backup_id | Recovery point đã kiểm tra | Rollback/restore |
| policy_test_result | Matrix ID và kết quả | Bằng chứng compliance |
| readback_reference | Tệp/log cấu hình thực tế sau deploy | Xác minh apply |
| incident/rollback reference | Mã sự cố hoặc biên bản rollback | Đóng vòng vận hành |

Git commit ID và hash file chỉ hỗ trợ đối chiếu byte/phiên bản trong điều kiện hệ thống nguồn tin cậy. **Hash khớp không chứng minh chính sách được phê duyệt, an toàn hoặc đã triển khai đúng**. Audit phải được bảo vệ khỏi sửa/xóa bởi cùng tài khoản đang deploy.

### 14.2. Backup Git và backup thiết bị đều cần

Bảo vệ repository Git (remote redundancy, access controls, backups, disaster recovery), nhưng đồng thời lưu **device configuration backup đã mã hóa và test restore**. Nếu mất Git, không được mất toàn bộ policy history; nếu thiết bị hỏng, không được chỉ còn YAML thiếu PKI/firmware dependencies. Ít nhất một bản cần nằm ngoài miền lỗi bị ảnh hưởng; có thể dùng immutable/offline theo rủi ro và chính sách tổ chức.

## 15. Các đặc thù theo công nghệ mạng

### 15.1. Firewall, ACL và NAT

Rule order, object/group expansion, source/destination zone, NAT precedence và implicit defaults có ý nghĩa bảo mật. Một review chỉ xem line diff có thể bỏ qua tác động lớn của một address group được mở rộng. Kiểm thử cả traffic hợp lệ và không được phép ở **đúng nguồn và đường đi**.

### 15.2. Router, BGP, VLAN và VRF

Policy routing, route redistribution, BGP filters, VRF leak và interface templates cần được kiểm tra với topology thực. **Config chuẩn không bảo đảm forwarding table đang có đường như dự kiến**, vì route động và neighbor state thay đổi theo thời gian. Có thể dùng simulation/lab hoặc kiểm tra show-state theo nhà cung cấp sau deploy.

### 15.3. VPN và PKI

Tunnel configuration có thể version control nhưng private key, PSK và certificate material phải được quản trị riêng. Kiểm tra chính sách route, peer, cipher/proposal compatibility, certificate lifecycle và split tunneling; backup/restore phải tính đến việc **cấp lại hoặc khôi phục danh tính**. Không ghi secret vào diff hoặc pipeline logs.

### 15.4. DNS

DNS zone có record, TTL, serial và quyền cập nhật động. Với authoritative DNS, serial cần tuân theo cơ chế quản lý zone thực tế; không sửa tùy tiện gây sai đồng bộ. **Dynamic updates** và managed DNS API có thể tạo drift khác với file desired; cần quyết định cái nào là nguồn sự thật. Kiểm thử từ nhiều resolver/view, cả A/AAAA nếu có split horizon.

### 15.5. IDS/IPS, WAF và monitoring

Một rule IDS hay WAF mới có thể gây false positives hoặc block traffic hợp lệ. Version control cần đi cùng baseline, shadow mode khi nền tảng hỗ trợ, tuning/test traffic và theo dõi alert quality. **Không tắt toàn bộ rule** chỉ để tránh báo động, và không dùng một ngoại lệ bao trùm toàn site khi chỉ cần điều chỉnh một luồng.

### 15.6. Cloud và Kubernetes

Cloud IaC mô tả resource nhưng **state files, resource IDs, IAM permissions và API eventual consistency** ảnh hưởng tới triển khai. Một Terraform plan có thể chứa thông tin nhạy cảm; không công khai artifact. Kubernetes NetworkPolicy có thể được quản lý bằng GitOps nhưng cần xác nhận **CNI thực thi**, ingress/egress là hai chiều riêng và một số traffic node/host-network có ngoại lệ tùy nền tảng.

Service mesh chính sách mTLS và authorization giúp xác thực workload nhưng không thay thế DB/app authorization. Khi pod IP thay đổi, dùng selectors hoặc identity được xác minh; đừng phụ thuộc thủ công vào địa chỉ của một pod đã bị thay thế.

## 16. Case study: PR mở rộng firewall rule ngoài ý định

### 16.1. Bối cảnh

Một hệ thống đơn hàng có hai vùng **APP** và **PAYMENT**. Theo thiết kế, chỉ order-service được phép gọi payment-service trên TCP/8443. Nhân sự vận hành cần bổ sung một instance order-service mới; trong PR, người đề xuất vô tình đổi nguồn từ **nhóm workload order-service** thành **toàn subnet APP**.

~~~text
Trước (ý định đã duyệt):
  Source: order-service identity / approved endpoints
  Destination: payment-service TCP/8443
  Action: allow

Sau (đề xuất sai):
  Source: toàn subnet APP
  Destination: payment-service TCP/8443
  Action: allow
~~~

Với hệ thống thực, policy có thể dựa trên địa chỉ IP, security group hoặc workload identity. Ở đây nội dung là **mẫu mô tả logic**, không phải cú pháp firewall.

### 16.2. Phát hiện trước triển khai

| Cổng kiểm tra | Quan sát | Kết luận |
| --- | --- | --- |
| Text diff | Source object đổi từ nhóm service sang APP subnet | Có phạm vi quyền mở rộng |
| Semantic policy check | Số workload có thể gọi payment-service tăng đáng kể | Cần dừng review |
| Negative test | Một workload khác trong APP có thể kết nối | Vi phạm yêu cầu least privilege |
| Reviewer | Không có change ticket cho phép mở cả subnet | Từ chối PR |
| CI gate | Block merge cho đến khi sửa rule và test đạt | Ngăn thay đổi sai đi vào production |

Sau khi sửa PR để chọn đúng workload/identity, pipeline chạy lại positive và negative tests; reviewer phê duyệt theo chính sách. Cần lưu PR, commit và report của phiên bản được phê duyệt.

### 16.3. Nếu sai lệch đã xuất hiện ở production

Giả sử một kỹ sư sửa trực tiếp rule trên firewall trong sự cố, rồi quên cập nhật Git. Drift detection phát hiện effective source khác desired source. **Không nên vội auto-revert** nếu đó là emergency change hợp lệ còn cần thiết. Nhóm network xác nhận incident ticket, mức ảnh hưởng và kế hoạch đóng quyền; sau khi có quyết định, thực hiện thay đổi có kiểm soát, retest các luồng và cập nhật Git/history. Một rule mở quá rộng là rủi ro bảo mật, nhưng khôi phục mù quáng cũng có thể làm mất dịch vụ.

### 16.4. Những bằng chứng cần có

- Policy mong muốn tại commit đã duyệt.
- Rendered config và semantic diff.
- Log reviewer/approval và CI test outputs.
- Device readback, firewall session/deny logs và deployment ID.
- Bản backup trước thay đổi và kết quả kiểm thử sau thay đổi.
- Thông tin drift, người xử lý, mốc UTC và action đóng sự cố.

## 17. Chỉ số vận hành của quản lý cấu hình

| Chỉ số | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| **Asset coverage** | Tỷ lệ thiết bị quan trọng được quản trị theo version | Không đánh đồng có repo với có kiểm chứng |
| **Change approval coverage** | Tỷ lệ thay đổi có reviewer và change reference | Đánh giá cả emergency exceptions |
| **Deploy success + validation pass** | Triển khai thành công và positive/negative tests đạt | Success command chưa đủ |
| **Drift age và drift count** | Sai khác tồn tại bao lâu, phạm vi nào | Phải lọc nhiễu runtime config |
| **Time to detect unsafe change** | Mất bao lâu từ thay đổi đến cảnh báo | Cần event timestamp chính xác |
| **Time to rollback/recover** | Khả năng phục hồi cấu hình được đo | Phân biệt revert, rollback và restore |
| **Policy test coverage** | Bao nhiêu yêu cầu mạng được kiểm chứng | Không chỉ đếm số rule |
| **Failed pipeline và secret alerts** | Lỗi automation, nguy cơ leak | Đánh giá nguyên nhân, tránh chỉ đếm sự kiện |
| **Unreviewed exceptions** | Rule khẩn cấp chưa được hợp thức hóa hoặc hết hạn | Có owner và mốc đóng |
| **Device state accuracy** | Tỷ lệ desired và effective khớp theo semantic comparison | Lưu ngữ nghĩa và phạm vi so sánh |

Chỉ số cần phân theo mức độ quan trọng của thiết bị và zone. Một firewall thanh toán quan trọng hơn nhiều switch lab; báo cáo tổng hợp có thể che những tài sản rủi ro cao chưa được quản trị.

## 18. Sai lầm phổ biến

| Sai lầm | Tác hại | Cách khắc phục |
| --- | --- | --- |
| Commit raw backup có secrets | Lộ credential, topology và key | Kho backup riêng mã hóa; secret references |
| Cho rằng private repo đủ bảo mật | Clone, CI, token hoặc artifacts vẫn có thể lộ | MFA, least privilege, secret scan, vault |
| Dùng .gitignore để “xóa” secret đã commit | Secret vẫn tồn tại trong history/mirrors | Rotate/revoke, xử lý lịch sử theo quy trình |
| Chỉ quản lý file template, không kiểm tra rendered output | Template đổi một dòng nhưng mở nhiều luồng | Diff và test policy cuối |
| Có Git commit nhưng deploy thủ công khác bản đã review | Không truy được production về source | Artifact pin, deployment ID và readback |
| So text của running config và báo drift hàng loạt | Dynamic fields tạo false positives | Vendor-aware semantic normalization |
| Auto-overwrite mọi drift | Có thể xóa emergency fix hoặc làm mất quản trị | Owner review và canary trước remediation |
| Test chỉ có allow cases | Không phát hiện mở rộng quyền ngoài ý định | Negative tests, default-deny matrix |
| Bỏ qua NAT/return path/IPv6/QUIC | False confidence về segmentation | Test từ đúng zone và nhiều protocol phù hợp |
| Cho runner CI quyền production khi xử lý PR không tin cậy | Lộ token hoặc bị lạm dụng deploy | Tách trust boundary validation/deployment |
| Merge và deploy đồng loạt mọi thiết bị | Một lỗi gây gián đoạn diện rộng | Canary, phased rollout và stop conditions |
| Chỉ rollback Git mà bỏ qua device state | Desired thay nhưng production chưa đổi | Native rollback/readback/traffic validation |
| Không có backup hoặc recovery credential | Không thể khôi phục khi mất route, IdP hoặc PKI | Backup riêng, break-glass, restore drills |
| Bỏ quên DNS/NTP/AAA/syslog dependencies | Default deny làm mất vận hành | Inventory và test dependencies |
| Không ghi owner hoặc change ticket | Dễ có rule vô chủ và exception lâu dài | CODEOWNERS, ADR, exception expiry |
| Dùng cùng credential cho mọi môi trường | Chiếm một pipeline có thể ảnh hưởng cả hệ thống | Tách token, tenant, approval và blast radius |

## 19. Mẫu Architecture Decision Record (ADR)

Mẫu dưới đây dùng để lưu lý do áp dụng version control thay vì chỉ ghi “dùng Git”.

~~~markdown
# ADR-EXAMPLE-008: Quản trị cấu hình bảo mật mạng bằng Git

Trạng thái: Proposed
Owner: Network Security + Platform Operations
Ngày: 2026-11-28

## Bối cảnh
- Nhiều firewall, VPN gateway, router và cloud network policy.
- Có thay đổi thủ công, khó review và khó xác minh drift.
- Thiết bị khác nhau về running/saved config và cơ chế rollback.

## Mục tiêu
- Desired policy có owner, change reference, review và version.
- Không lưu raw secret trong Git.
- Có CI syntax/semantic/negative test và deployment evidence.
- Có backup và runbook phục hồi độc lập với Git.

## Phương án
- A: Chỉ quản lý thủ công kèm backup thiết bị.
- B: Git cho policy và review, deploy có kiểm soát theo đợt.
- C: GitOps reconcile tự động cho mọi tài sản.

## Quyết định đề xuất
- Chọn B cho thiết bị mạng truyền thống và những vùng production nhạy cảm.
- Thí điểm C ở nền tảng hỗ trợ policy reconcile an toàn.

## Rủi ro/trade-offs
- CI/CD/collector cần phân quyền, on-call và patching.
- Drift do emergency fix phải được xử lý có review.
- Không phải vendor nào cũng hỗ trợ atomic apply hoặc rollback.

## Điều kiện chấp nhận
- PR approval + codeowner/security review theo mức rủi ro.
- CI secret scan, policy diff, positive/negative tests.
- Device readback xác nhận effective config.
- Restore drill và kiểm tra failover theo lịch.

## Rà soát lại
- Khi mở cloud account/site mới, đổi IAM/PKI hoặc vendor firmware.
- Khi deployment incident, secret exposure hoặc drift tăng.
~~~

ADR cần được chấp thuận bởi owner thực tế và cập nhật trạng thái theo vòng đời quyết định. Nó không thay thế change ticket cho một thay đổi firewall cụ thể.

## 20. Checklist áp dụng version control cho cấu hình mạng

- [ ] Đã xác định tài sản, service owner, trust boundaries và mức độ quan trọng.
- [ ] Đã phân biệt desired, rendered, candidate, running, startup và observed state.
- [ ] Đã lựa chọn chính sách/template nào thuộc Git và dữ liệu nào cần backup riêng.
- [ ] Repository có cấu trúc theo owner/environment/asset đủ rõ và quyền truy cập hạn chế.
- [ ] Secrets, PSK, private key, token và raw backup nhạy cảm không nằm ở Git plaintext.
- [ ] Branch protection, CODEOWNERS, MFA, approval và signed/provenance controls phù hợp.
- [ ] Pull request ghi change ticket, lý do, scope, risk, test và rollback plan.
- [ ] CI kiểm tra schema, reference, semantic diff, secret scan và dangerous broad allow.
- [ ] Có positive, negative, dependency và failure-path tests cho policy trọng yếu.
- [ ] Build artifact được pin với commit đã phê duyệt; CI runner chưa tin cậy không có quyền production.
- [ ] Deploy đúng environment/asset, giới hạn canary/concurrency và có stop conditions.
- [ ] Có pre-change backup, out-of-band/recovery access và thủ tục rollback phù hợp vendor.
- [ ] Sau deploy có readback effective config, traffic tests, audit và health metrics.
- [ ] Drift detection dùng semantic comparison, xử lý emergency changes bằng review.
- [ ] Firewall/NAT, DNS, VPN, Wi-Fi/NAC, IDS/IPS, cloud và Kubernetes có chính sách riêng phù hợp.
- [ ] Git repository và kho backup được bảo vệ, sao lưu ở miền lỗi độc lập và thử restore.
- [ ] Log/metrics có timestamp UTC, identity, policy version và trạng thái change.
- [ ] Đã xác định owner/on-call, policy exception expiry và chu kỳ rà soát.

**Kết luận:** quản lý cấu hình bằng version control không đơn thuần là lưu file vào Git. Đó là một cơ chế quản trị an toàn gồm **nguồn sự thật được phê duyệt, kiểm tra ý nghĩa chính sách, triển khai có kiểm soát, đối chiếu trạng thái đang chạy và khả năng khôi phục**. Khi Git, automation, phân quyền, backup và telemetry hoạt động cùng nhau, những thay đổi ở firewall, VPN, DNS, routing, IDS/IPS và cloud trở nên có thể giải thích, kiểm chứng và phục hồi mà không đánh đổi an toàn mạng lấy tốc độ thao tác.
