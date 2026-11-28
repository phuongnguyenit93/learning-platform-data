# Rà soát rule không còn traffic trong vận hành mạng an toàn

**Chương:** Quản trị vận hành mạng an toàn  
**Chủ đề:** Rà soát rule không còn traffic  
**Phạm vi:** Chính sách firewall, ACL, security group và các kiểm soát truy cập mạng tương đương trong môi trường on-premises, VPN và cloud.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao quy tắc (rule) không ghi nhận lưu lượng **chưa chắc** đã không còn cần thiết.
2. Phân biệt rule không có hit, rule bị che khuất (shadowed), rule trùng lặp (redundant), rule hết hạn và rule quá rộng.
3. Thu thập bằng chứng từ cấu hình, bộ đếm hit, flow log, firewall log, ứng dụng, CMDB và chủ sở hữu hệ thống.
4. Đánh giá thời gian quan sát, tính đầy đủ của log và tác động của NAT, HA, IPv6, VPN, thay đổi tuyến hoặc chính sách.
5. Xây quy trình kiểm soát thay đổi để vô hiệu hóa, theo dõi và gỡ bỏ rule theo mức độ rủi ro, có khả năng rollback.
6. Lập báo cáo có thể kiểm toán gồm chứng cứ, người xác nhận, kết quả kiểm thử và trạng thái xử lý.

Trong module `SECURITY_NETWORK_SECURITY`, công việc này gắn trực tiếp với nguyên tắc **least privilege**, phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối và giám sát xâm nhập: giảm các đường truy cập không cần thiết nhưng vẫn giữ kết nối phục vụ nghiệp vụ và đường khôi phục khẩn cấp.

> **Nguyên tắc cốt lõi:** “Không thấy traffic” là một quan sát trong **một tập nguồn dữ liệu và khoảng thời gian cụ thể**, không phải bằng chứng tuyệt đối rằng rule vô dụng. Không xóa rule chỉ vì hit counter bằng 0.

## 2. Rule trong ngữ cảnh chính sách mạng

Rule diễn đạt quyết định cho phép, từ chối hoặc xử lý lưu lượng dựa trên nhiều thuộc tính. Trên một firewall có trạng thái, các thuộc tính thường gồm:

- Nguồn/đích (CIDR, IP, nhóm địa chỉ, FQDN object, dynamic group hoặc tag).
- Source zone và destination zone; interface, VRF hoặc tenant nếu có.
- Dịch vụ/giao thức: TCP/UDP, ICMP, cổng, ứng dụng hoặc điều kiện nhận diện lớp 7.
- Action: allow/deny/drop/reject, log, inspect, redirect hay xử lý đặc biệt.
- Thứ tự ưu tiên, các rule phía trước và quy tắc mặc định.
- Lịch hiệu lực, người dùng/danh tính, thiết bị, điều kiện hoặc security profile.
- NAT, VPN, route và stateful session ảnh hưởng cách một packet khớp rule.

**Rule không còn traffic** trong bài này là rule mà *trong tập quan sát được xác định rõ*, hệ thống không ghi nhận kết nối/phiên mới khớp rule. Kết luận sâu hơn — **rule có thể ngừng sử dụng** — đòi hỏi xác minh nhu cầu nghiệp vụ và tác động bảo mật.

### Các trạng thái dễ bị nhầm

| Trạng thái | Định nghĩa thực dụng | Có thể xử lý ngay? |
|---|---|---|
| **Zero-hit** | Counter của rule ở thiết bị/vDOM/context đang quan sát bằng 0 | Chưa; kiểm tra thời điểm reset và phạm vi counter |
| **No-log-match** | Không tìm thấy bản ghi phù hợp trong hệ thống log cho khoảng thời gian truy vấn | Chưa; kiểm tra logging, sampling, retention và bộ lọc |
| **Stale** | Không ghi nhận sử dụng trong cửa sổ đủ dài theo chính sách tổ chức | Đưa vào hàng đợi review, vẫn cần owner xác nhận |
| **Shadowed** | Một rule phía trước xử lý mọi lưu lượng mà rule sau có thể khớp, xét cùng ngữ cảnh | Có thể là ứng viên tinh gọn; phải phân tích thứ tự và chính sách |
| **Redundant** | Bỏ rule không làm thay đổi quyết định hiệu lực của toàn bộ chính sách trong phạm vi đã mô hình hóa | Cần kiểm tra tương đương ngữ nghĩa và tác động logging |
| **Expired** | Rule có hạn dùng/ngoại lệ đã hết theo thay đổi được duyệt | Ưu tiên đánh giá, nhưng vẫn kiểm tra hệ thống phụ thuộc |
| **Over-permissive** | Rule cho phép rộng hơn nhu cầu, có thể vẫn rất nhiều traffic | Cần thu hẹp theo mục đích, không thuộc nhóm “không có traffic” |
| **Unused security deny** | Rule deny không thấy hit trong khoảng quan sát | Không tự xóa; có thể là chốt chặn chủ động cho mối đe dọa ít xảy ra |

Một rule có vài hit mỗi năm khi diễn tập disaster recovery vẫn có thể **rất quan trọng**. Ngược lại, rule có số hit lớn do scan hoặc kết nối trái phép không mặc nhiên là rule hợp lệ về nghiệp vụ.

## 3. Vì sao phải rà soát?

Quá nhiều rule cũ khiến bề mặt tấn công khó nhìn thấy, tăng nguy cơ lỗi khi sửa thứ tự, tạo ngoại lệ vĩnh viễn và làm vận hành chậm. Một rule allow mở từ mạng người dùng sang subnet quản trị có thể chưa từng có hit hợp lệ nhưng vẫn cho phép kẻ tấn công di chuyển ngang khi có cơ hội.

Lợi ích của việc rà soát gồm:

1. **Giảm blast radius:** loại bỏ đường truy cập không còn phục vụ chức năng.
2. **Làm rõ segmentation:** quy tắc allow phản ánh luồng nghiệp vụ được phê duyệt giữa các vùng.
3. **Giảm lỗi thay đổi:** ít rule chồng chéo và ít ngoại lệ khó hiểu.
4. **Cải thiện kiểm toán:** có owner, thời điểm xét lại, bằng chứng và lý do tồn tại.
5. **Cải thiện vận hành:** log, hit counter và tài liệu mạng dễ đối chiếu hơn.

Tuy nhiên, mục tiêu không phải “xóa càng nhiều rule càng tốt”; mục tiêu là **chính sách tối thiểu, kiểm chứng được và duy trì tính liên tục của dịch vụ**.

## 4. Mô hình ra quyết định: từ bằng chứng đến hành động

~~~mermaid
flowchart TD
    A["Inventory: rule + context + owner"]
    B{"Dữ liệu quan sát đủ tin cậy?"}
    C["Bổ sung log/counter hoặc đánh dấu UNKNOWN"]
    D{"Có hit phù hợp trong cửa sổ?"}
    E["Có sử dụng: xem xét least privilege / phạm vi"]
    F["No observed traffic: xác minh phụ thuộc"]
    G{"Owner xác nhận? Kịch bản hiếm? Deny/DR rule?"}
    H["Giữ + đặt lịch đánh giá lại"]
    I["Đánh giá rủi ro và đề xuất change"]
    J["Backup cấu hình + phê duyệt + disable"]
    K{"Kiểm tra nghiệp vụ / bảo mật PASS?"}
    L["Rollback, phân tích nguyên nhân"]
    M["Theo dõi đủ thời gian rồi xóa"]
    A --> B
    B -- "Không" --> C
    C --> B
    B -- "Có" --> D
    D -- "Có" --> E
    D -- "Không" --> F
    F --> G
    G -- "Cần giữ / chưa rõ" --> H
    G -- "Không còn cần" --> I
    I --> J
    J --> K
    K -- "Không" --> L
    K -- "Có" --> M
~~~

Đường quyết định phải lưu lại mức tin cậy của từng nhận định. **UNKNOWN** là kết quả hợp lệ nếu log thiếu, counter reset hoặc chủ hệ thống chưa xác nhận. Không chuyển tự động UNKNOWN thành UNUSED.

## 5. Chuẩn bị inventory chính sách

Mỗi rule cần một bản ghi có đủ ngữ cảnh để tìm đúng rule trong policy đã cài đặt:

| Trường | Nội dung cần lưu |
|---|---|
| Device/context | Tên firewall, cluster, virtual system/VDOM, tenant hoặc cloud account |
| Policy/rule ID | Định danh ổn định của rule, policy package, phiên bản cấu hình |
| Order / position | Thứ tự so khớp, mức ưu tiên, mối quan hệ rule phía trước |
| Source / destination | CIDR, address group, dynamic object, zone/interface |
| Service / app | Protocol, port, application-ID, URL/FQDN nếu phù hợp |
| Action / logging | Allow, deny, reject; log enable và nơi gửi log |
| NAT / route | Trước/sau NAT, route table, VPN/overlay liên quan |
| Owner / purpose | Tên nhóm chịu trách nhiệm, ticket, sơ đồ luồng, ngày tạo, hạn dùng |
| Usage evidence | Hit count, thời điểm last hit, log/flow, nguồn và thời gian truy vấn |
| Decision | KEEP / RESTRICT / CANDIDATE / UNKNOWN / DISABLE / REMOVE |

**Không dựa riêng vào tên rule.** Ví dụ `allow-web-old` có thể vẫn được reference trong object group hoặc rule được tái sử dụng qua template. Đối chiếu cấu hình **đang được thiết bị thực thi** (running/installed policy), không chỉ cấu hình dự định trong hệ thống quản lý.

### Lưu snapshot và chuẩn hóa thời gian

Lấy bản cấu hình và policy hit counter ở thời điểm bắt đầu. Ghi timezone, thời điểm NTP đồng bộ, phiên bản policy, thiết bị đang active, log retention và bộ lọc truy vấn. Snapshot giúp phát hiện cấu hình thay đổi giữa hai lần lấy số liệu.

Trong môi trường nhiều firewall, cùng Rule ID hoặc cùng tên **chưa chắc** là cùng một rule; phải gắn ít nhất `device/context/policy_version/rule_id`.

## 6. Nguồn bằng chứng và giới hạn

### 6.1. Rule hit counter và last-hit

Hit counter là chỉ số dễ lấy nhưng ý nghĩa **phụ thuộc nền tảng**:

- Có sản phẩm đếm packet; có sản phẩm đếm session, connection hoặc lần policy match.
- Một số counter nằm tại dataplane, chỉ hiển thị trên active node, chỉ ghi trên từng thiết bị hoặc từng member.
- Counter có thể reset khi reboot, policy install, failover, nâng cấp firmware hoặc theo yêu cầu vận hành.
- Counter của rule deny có thể tăng do scan, retry lỗi hoặc hành vi trái phép; không phản ánh nhu cầu sử dụng được phép.
- Với rule có match count tăng mà không có log phiên, cần kiểm tra cấu hình logging và cách đếm của nền tảng.

Nếu snapshot T1 cho counter 120 và T2 là 125, có thể có **5 đơn vị hit theo định nghĩa vendor** trong cửa sổ; chưa chắc có 5 phiên ứng dụng. Nếu counter T2 nhỏ hơn T1, giả định ban đầu là **counter reset/overflow/chuyển context**, phải kiểm tra thay vì suy ra traffic âm.

### 6.2. Firewall traffic logs và session logs

Log giúp xác định source, destination, service, action, thời gian, số byte, user nếu có, zone và rule ID. Khi rà soát:

- Kiểm tra **log tại session start hay end**: kết nối dài chưa kết thúc có thể chưa ghi end log.
- Log có thể chỉ lưu allow, chỉ lưu deny, chỉ lưu một mẫu, hoặc bị bỏ khi pipeline nghẽn.
- Khi quản lý tập trung, phải xác minh dữ liệu của **tất cả thành viên HA** và cả các policy context liên quan.
- Log có thể bị loại bởi filter, mapping rule ID không chính xác, retention ngắn hơn kỳ khảo sát hoặc timestamp sai.
- Một record blocked ở firewall khác không chứng minh rule đích không còn cần; traffic có thể bị chặn trước khi đến rule đang xét.

**Session table** hỗ trợ kiểm tra các kết nối đang sống, đặc biệt khi ứng dụng giữ kết nối hàng giờ/ngày và thiết bị ghi log vào lúc session kết thúc.

### 6.3. Flow telemetry và log của ứng dụng

NetFlow/IPFIX, VPC flow logs, NSG flow logs, proxy logs, VPN logs, DNS logs, load balancer logs, EDR và application access logs bổ sung bằng chứng. Tuy nhiên, nhiều loại flow log **không có rule ID** và có thể bị aggregation/sampling. Cần join theo `5-tuple + thời gian + NAT mapping + context` hoặc tập trường tương đương; không ghép bừa theo IP đích.

| Nguồn | Có ích để trả lời | Không chứng minh được điều gì nếu đứng riêng |
|---|---|---|
| Policy hit counter | Rule có từng được so khớp theo bộ đếm được hiển thị? | Tài khoản/nghiệp vụ cụ thể cần rule; lần sử dụng cuối nếu counter không có lịch sử |
| Traffic/session log | Ai kết nối vào đâu, lúc nào, action gì theo log? | Tính đầy đủ tuyệt đối nếu sampling hoặc thiếu log |
| Flow log | Có luồng IP/port giữa các vùng? | Chính xác rule firewall nào đã cho phép nếu thiếu rule ID |
| CMDB và service map | Luồng thuộc ứng dụng/owner/đặc thù vận hành nào? | Traffic có thực sự xảy ra trong cửa sổ quan sát |
| Change ticket | Vì sao rule được tạo và hạn sử dụng? | Rule đã hết tác dụng ngay tại thời điểm ticket đóng |
| App logs/APM | Chức năng nào kết nối hay timeout? | Firewall là nguyên nhân duy nhất của lỗi |
| VPN/SD-WAN logs | Tunnel/đường dự phòng có được kích hoạt? | Rule ngoài thời gian tunnel hoạt động là không cần |
| Firewall config/policy analysis | Rule bị shadow, trùng phạm vi, phụ thuộc đối tượng? | Có an toàn để xóa khi owner/luồng hiếm chưa được xác minh |

### 6.4. Cửa sổ quan sát phù hợp

Ví dụ tổ chức có thể dùng cửa sổ ban đầu 30 ngày cho hệ thống thông thường, 90 ngày cho kết nối ít dùng và **một hoặc nhiều chu kỳ nghiệp vụ** cho tác vụ quý/năm; đây chỉ là **ngưỡng ví dụ**, không phải quy chuẩn bắt buộc. Cần bao phủ:

- Batch cuối tháng/quý/năm, báo cáo thuế hoặc quyết toán.
- Backup, restore, DR/failover, kiểm thử khẩn cấp, đường OOB quản trị.
- Maintenance window, patching, rotation chứng chỉ, kết nối nhà cung cấp.
- Dự phòng mạng hoạt động chỉ khi ISP/tunnel/region chính lỗi.
- Giai đoạn cao điểm theo mùa, khai trương dự án hoặc chiến dịch marketing.
- Thời gian log retention thực tế, nguồn nào trước đó không bật ghi nhận.

Nếu chỉ lưu log 7 ngày thì không thể tuyên bố “không có traffic trong 90 ngày” dựa vào kho log đó. Có thể dùng ảnh chụp counter theo lịch, dữ liệu lưu trữ dài hơn hoặc kết quả diễn tập, nhưng phải ghi cụ thể phương pháp.

## 7. Các yếu tố kỹ thuật làm sai lệch kết luận

### 7.1. Thứ tự rule, shadowing và rule mặc định

Một firewall first-match có thể chọn rule phía trên trước khi đến rule đang xét:

~~~text
Rule 100: allow 10.20.0.0/16 -> 10.30.5.10 TCP 443
Rule 110: allow 10.20.8.0/24 -> 10.30.5.10 TCP 443
Rule 999: deny  any -> any
~~~

Giả sử các điều kiện zone, user, schedule, application, NAT context và security profile của Rule 100 bao phủ hoàn toàn Rule 110. Trong ngữ nghĩa **first-match** này, Rule 110 có thể bị shadow. Nhưng xóa Rule 110 vẫn cần xem mục đích audit, khác biệt log/inspection, thay đổi policy dự kiến và kết quả phân tích chính sách tương đương. Trên hệ thống có cách so khớp khác, không áp dụng máy móc kết luận first-match.

Không được nhầm *không có hit* với *bị shadow*: nếu cả Rule 100 và Rule 110 đều không có hit, có thể không hề phát sinh luồng tương ứng trong cửa sổ.

### 7.2. NAT, load balancing và địa chỉ động

Rule có thể so khớp địa chỉ **pre-NAT** hoặc **post-NAT**, phụ thuộc hãng và loại policy. Khi đối chiếu flow, cần biết cả địa chỉ trước/sau chuyển đổi. Ví dụ client nhìn thấy VIP `10.40.10.20` nhưng backend là `10.40.30.25`; truy vấn log theo backend có thể bỏ sót rule áp dụng lên VIP.

FQDN object, cloud tag, Kubernetes IP/pod và danh sách địa chỉ qua DNS có thể thay đổi trong thời gian khảo sát. Rule nhìn “không có traffic tới IP cũ” chưa chắc không có traffic tới object hiện tại.

### 7.3. HA, standby, failover và route bất đối xứng

Thiết bị standby thường không xử lý lưu lượng khi bình thường nên hit = 0 là điều mong đợi. Phải kiểm tra **counter/log của node thực sự xử lý traffic**, kể cả khi cluster đã failover.

Trong mô hình active-active, ECMP, PBR hoặc SD-WAN, traffic có thể đi tuyến khác và không bao giờ chạm thiết bị đang xem. Một đường dự phòng ít được dùng cần được phân loại theo **chức năng dự phòng**, không xóa vì thiếu hit.

### 7.4. IPv4, IPv6, ICMP, UDP và luồng điều khiển

IPv6 có thể đi qua policy riêng; nhiều hệ thống còn đường nội bộ IPv4 và đường internet IPv6 khác nhau. TCP session thường dễ thấy hơn một số luồng UDP hoặc ICMP. Lưu lượng DNS, NTP, DHCP relay, BGP/OSPF, VRRP, IPsec/IKE hoặc health check có thể có chu kỳ thấp nhưng tác động lớn.

Không nên dùng phép thử TCP đơn giản để đánh giá toàn bộ rule UDP/ICMP hoặc điều khiển mạng. Chọn công cụ theo giao thức và bảo đảm phạm vi thử được phê duyệt.

### 7.5. Rule deny và security intent

Rule deny nhằm chặn một hành vi **không mong muốn**; không có hit trong 90 ngày có thể cho thấy đối tượng bị chặn chưa thử truy cập. Nếu xóa rule và phía dưới có rule allow rộng, mức bảo vệ thay đổi. Khi đánh giá deny rule, câu hỏi phải là “quyết định bảo mật của chính sách có thay đổi nếu bỏ rule?” chứ không chỉ “deny counter có lớn không?”.

Tương tự, IDS/IPS signature hoặc WAF rule không kích hoạt chưa chắc nên xóa: chúng có thể phòng vệ trước hành vi hiếm nhưng nghiêm trọng. Quy trình quản lý signature/threat intelligence có thêm tiêu chí riêng về coverage, false positive và lifecycle.

## 8. Quy trình vận hành đề xuất

### Bước 1 — Chốt scope và thời gian

Định nghĩa rõ thiết bị/context, policy đang cài, nhóm rule được phép review, khoảng thời gian và data sources. Xác định nhóm sở hữu hệ thống, mức rủi ro chấp nhận, lịch freeze, cửa sổ triển khai, tiêu chí dừng và cơ chế khôi phục.

Nên ưu tiên **allow rule giữa các vùng nhạy cảm** (user → management, user → database, internet → nội bộ, application → data) vì việc loại bỏ quyền truy cập không cần thiết thường giảm bề mặt tấn công. Vẫn cần giữ khả năng nghiệp vụ hợp lệ và tuân thủ quản lý thay đổi.

### Bước 2 — Thu thập và chuẩn hóa dữ liệu

Xuất cấu hình rule, object groups, rule order, hit counter và thời điểm counter được reset (nếu biết). Lấy traffic/session logs trong toàn bộ thời gian còn retention; kiểm tra kho log có bị thiếu phút/giờ hoặc mất nguồn. Thu route, NAT, VPN/HA context và sơ đồ dependency của ứng dụng tương ứng.

Nếu thiết bị cho phép lấy hit snapshot nhiều lần, lưu số liệu dạng:

~~~csv
observed_at_utc,device,context,policy_version,rule_id,counter_value,counter_unit
2026-11-01T00:00:00Z,fw-east,vsys1,rev21,120,125,sessions
2026-11-15T00:00:00Z,fw-east,vsys1,rev21,120,125,sessions
2026-11-01T00:00:00Z,fw-east,vsys1,rev21,135,0,sessions
2026-11-15T00:00:00Z,fw-east,vsys1,rev21,135,0,sessions
~~~

Dữ liệu trên là **minh họa giả**. Để so sánh counter, phải kiểm tra cùng thiết bị/instance, cùng phiên bản chính sách, không reboot/reset và cùng đơn vị đếm. Không dùng phép trừ nếu có nghi vấn reset hoặc thay đổi cách tính.

### Bước 3 — Xác định ứng viên

Một **ứng viên review** thường có:

- Không thấy traffic match trong cửa sổ đủ dài theo loại nghiệp vụ **và** telemetry đã được xác minh tương đối đầy đủ.
- Không có last-hit gần đây đáng tin, hoặc có bằng chứng rule bị che khuất/trùng trong chính sách hiện hữu.
- Ticket/ngoại lệ đã hết hạn, service đã ngừng hoặc owner đề nghị đóng.
- Có sơ đồ dependency hoặc inventory xác nhận đường này không còn phục vụ hệ thống hoạt động.

Luôn ghi mức tin cậy: **HIGH** (nhiều nguồn độc lập + owner xác nhận), **MEDIUM** (log/counter đủ nhưng thiếu kiểm thử nghiệp vụ), **LOW** (chỉ counter hoặc log không đầy đủ), **UNKNOWN** (mâu thuẫn hoặc thiếu dữ liệu). Mức này là quy ước của **đội vận hành trong ví dụ**, không phải chuẩn chung.

### Bước 4 — Đánh giá tác động và owner sign-off

Liên hệ nhóm sở hữu ứng dụng, network, security và bên phụ trách DR/backup khi liên quan. Xác minh rule:

1. Bảo vệ hoặc cho phép chức năng nghiệp vụ nào?
2. Có vận hành theo lịch hiếm, theo mùa hoặc khi failover không?
3. Có đường đi thay thế, rule khác hoặc policy mặc định ảnh hưởng không?
4. Có ảnh hưởng kiểm soát pháp lý, phân vùng dữ liệu, nhà cung cấp hay trách nhiệm audit?
5. Nếu disable, có tín hiệu monitoring hoặc bài test nào phát hiện lỗi ngay?

Chủ sở hữu không xác định là **rủi ro quản trị**, không phải bằng chứng rule không còn cần. Quy trình nên có escalation và quyết định có thẩm quyền trước thay đổi.

### Bước 5 — Phân loại và phê duyệt

| Quyết định | Điều kiện điển hình | Hành động |
|---|---|---|
| `KEEP` | Có traffic hợp lệ hoặc thuộc đường DR/khẩn cấp được phê duyệt | Cập nhật owner, mục đích và lịch review |
| `RESTRICT` | Rule còn cần nhưng phạm vi source/destination/service quá rộng | Đề xuất rule hẹp hơn, kiểm thử theo thay đổi riêng |
| `CANDIDATE` | Không thấy sử dụng, telemetry đủ, owner xác nhận không còn phụ thuộc | Chuẩn bị change có disable thử và rollback |
| `UNKNOWN` | Log thiếu, rule mapping không chắc, owner chưa xác nhận | Giữ nguyên; bổ sung bằng chứng trước khi quyết định |
| `DISABLED_MONITORING` | Rule đã vô hiệu hóa trong cửa sổ được phê duyệt | Theo dõi ứng dụng/network/incident trước khi xóa |
| `REMOVED` | Theo dõi đủ chu kỳ, không lỗi, có sign-off | Xóa có lưu phiên bản cấu hình và kết quả hậu kiểm |

### Bước 6 — Thực hiện theo change control

Trình tự an toàn:

1. Chụp/export cấu hình đang chạy, lưu policy version, rule UUID, object references và backup khả dụng.
2. Thống nhất người thao tác, người phê duyệt, cửa sổ thay đổi và stakeholder theo dõi.
3. Xác định luồng ứng dụng cần kiểm thử trước/sau (connectivity, authentication, giao dịch, DR nếu liên quan).
4. Trước khi disable, rà thay đổi tương tác từ thứ tự rule, deny mặc định, NAT và chính sách ở các vùng khác.
5. **Disable** đúng rule được duyệt nếu nền tảng hỗ trợ và có cơ chế rollback nhanh; đừng tắt nhiều nhóm rule không liên quan cùng một lúc.
6. Chạy kiểm thử tích cực tại những điểm nguồn/đích được phép; giám sát deny log, timeout, retransmission, application error, VPN status và alert.
7. Chờ qua thời gian theo dõi phù hợp với chu kỳ sử dụng; một buổi tối yên ắng không đủ với job chạy cuối tháng.
8. Khi xác nhận an toàn và có phê duyệt, xóa rule; xác minh chính sách đã được **install/commit** đúng context và cập nhật inventory/ticket.

Một số hệ thống không có cơ chế disable riêng hoặc disable có semantics khác delete. Khi đó, cần dựa vào quy trình thay đổi được hỗ trợ bởi nền tảng, có snapshot và rollback; không tự đổi action thành deny hay thêm rule chặn mà chưa phân tích tác động.

### Bước 7 — Hậu kiểm và đóng thay đổi

Đọc lại policy sau commit, đảm bảo rule mong muốn đã tắt/xóa, không có rule bị đánh đổi thứ tự ngoài dự kiến, policy install thành công trên mọi node/region, và monitoring ổn định. Lưu evidence, change ID, owner, ngày kiểm tra lại và kết quả từ ứng dụng.

## 9. Ví dụ tình huống: rule mở SSH đã cũ

Giả định firewall giữa vùng vận hành và vùng máy chủ có các rule:

| Rule ID | Nguồn | Đích | Dịch vụ/action | Lịch sử quan sát | Owner |
|---|---|---|---|---|---|
| 120 | `10.40.20.0/24` (jump subnet) | `10.40.30.10` (app server) | TCP 22/allow | Có SSH hợp lệ hằng ngày | Ops |
| 135 | `10.40.10.0/24` (user subnet) | `10.40.30.10` | TCP 22/allow | Zero-hit 90 ngày theo dữ liệu đầy đủ | Chưa rõ |
| 150 | `10.40.20.0/24` | `10.40.30.20` (backup server) | TCP 22/allow | Zero-hit 90 ngày | Backup/DR |
| 190 | Any | `10.40.30.0/24` | TCP 22/deny | Zero-hit 90 ngày | Security |

**Phân tích từng rule:**

- **120:** đang sử dụng. Có thể kiểm tra quyền và giao thức quản trị nhưng không thuộc diện unused.
- **135:** ứng viên cần review. Cần kiểm tra lịch sử chuyển sang jump host, chủ sở hữu, đối chiếu NAT/vùng, rồi disable theo change được duyệt.
- **150:** lưu cho DR hoặc kỳ backup hiếm. Zero-hit không đủ; cần kiểm thử backup/restore/DR và nhận xác nhận từ nhóm backup.
- **190:** deny rule có giá trị bảo vệ hoặc thể hiện ranh giới an ninh. Không xóa chỉ vì counter = 0; phân tích policy equivalence và nhu cầu bảo mật.

Giả sử Rule 135 được tạo khi đội kỹ thuật còn SSH trực tiếp từ máy trạm; nay tất cả phiên hợp lệ đi qua jump subnet Rule 120. Khi owner xác nhận quy trình cũ đã ngừng, nhóm vận hành có thể **disable Rule 135 và giám sát qua một chu kỳ bảo trì**. Nếu không có lỗi và các kiểm thử được phê duyệt đều đạt, gỡ bỏ Rule 135 ở một change khác có đầy đủ bằng chứng. Ví dụ này không tự bảo đảm mọi môi trường dùng cùng chính sách.

## 10. Phân tích bằng truy vấn log: từ no-hit tới candidate

### 10.1. Giả định schema

Giả sử SIEM có bảng `FirewallTraffic` sau khi chuẩn hóa:

| Field | Ý nghĩa |
|---|---|
| `TimeGenerated` | Thời gian sự kiện UTC |
| `DeviceId` | Firewall sinh log |
| `ContextId` | Context/vsys/tenant |
| `PolicyVersion` | Phiên bản policy nếu có |
| `RuleId` | Định danh rule đã match |
| `Action` | Allow / Deny |
| `SourceIp`, `DestinationIp` | IP hiển thị theo schema đã thống nhất về NAT |
| `DestinationPort`, `Protocol` | Dịch vụ đã quan sát |
| `LogType` | Session start/end, policy match hoặc loại khác |

Đây là **bảng ví dụ**, không phải schema mặc định của Azure, Splunk, Elastic, Palo Alto, Fortinet hoặc hãng khác. Trước khi dùng trên SIEM thật, phải ánh xạ tên field, action và semantics tương ứng.

### 10.2. Liệt kê số log được quan sát theo rule

Ví dụ cú pháp KQL trên dữ liệu đã chuẩn hóa:

~~~kusto
let startTime = datetime(2026-08-01T00:00:00Z);
let endTime   = datetime(2026-11-01T00:00:00Z);
FirewallTraffic
| where TimeGenerated >= startTime and TimeGenerated < endTime
| where DeviceId == "fw-east" and ContextId == "vsys1"
| where Action == "Allow"
| summarize ObservedLogRecords = count(),
            LastObservedUtc = max(TimeGenerated),
            DistinctSources = dcount(SourceIp),
            DistinctDestinations = dcount(DestinationIp)
    by DeviceId, ContextId, PolicyVersion, RuleId
| order by ObservedLogRecords asc
~~~

Kết quả chỉ hiển thị các rule **có ít nhất một bản ghi phù hợp** trong khoảng thời gian truy vấn. Để tìm rule **0 bản ghi**, phải join kết quả với inventory đầy đủ của các rule hiện hành; không diễn giải việc rule vắng mặt trong kết quả là đã không còn được sử dụng.

Lưu ý thêm: nếu truy vấn đặt filter `Action == "Allow"`, các rule deny sẽ bị loại khỏi kết quả dù vẫn có deny hit. Phạm vi và semantics log phải khớp câu hỏi phân tích.

### 10.3. Ghép inventory để tạo danh sách xem xét

~~~kusto
// RuleInventory: bảng snapshot quy tắc đang cài cùng mốc PolicyVersion
let startTime = datetime(2026-08-01T00:00:00Z);
let endTime   = datetime(2026-11-01T00:00:00Z);
let matches =
    FirewallTraffic
    | where TimeGenerated >= startTime and TimeGenerated < endTime
    | where DeviceId == "fw-east" and ContextId == "vsys1"
    | summarize ObservedLogRecords = count(),
                LastObservedUtc = max(TimeGenerated)
        by DeviceId, ContextId, PolicyVersion, RuleId;
RuleInventory
| where DeviceId == "fw-east" and ContextId == "vsys1"
| where Action == "Allow"
| join kind=leftouter matches on DeviceId, ContextId, PolicyVersion, RuleId
| extend ObservedLogRecords = coalesce(ObservedLogRecords, tolong(0))
| where ObservedLogRecords == 0
| project DeviceId, ContextId, PolicyVersion, RuleId,
          Source, Destination, Service, Owner, ObservedLogRecords
~~~

**Điều kiện tiên quyết:** `RuleInventory` chứa các rule đúng policy/context đã cài, `PolicyVersion` được chuẩn hóa và log không bị mất. Nếu policy đã đổi trong cửa sổ, cần chia khoảng quan sát theo phiên bản, hoặc dùng định danh rule ổn định cùng phương pháp mapping được kiểm chứng. Query chỉ sinh danh sách **no-log candidate**; bước xác nhận nghiệp vụ và chính sách bảo mật vẫn bắt buộc.

### 10.4. Trường hợp log không đủ

Hãy lưu kết quả như:

~~~yaml
rule_id: "135"
device: fw-east
context: vsys1
observation:
  start_utc: "2026-08-01T00:00:00Z"
  end_utc: "2026-11-01T00:00:00Z"
  traffic_logs: 0
  hit_counter_delta: unknown
  logging_coverage: partial
  reason: "Thiếu log 4 ngày, một HA member chưa kiểm chứng"
classification: UNKNOWN
next_action: "Bổ sung log và xác nhận với owner"
~~~

Điều này tốt hơn là ghi “unused = true” khi chứng cứ không đầy đủ.

## 11. Phân loại rủi ro và ưu tiên xử lý

Có thể xây ma trận ưu tiên **để review**, không tự động xóa:

| Tác động nếu rule bị lạm dụng | Tính chắc chắn không còn dùng | Ưu tiên | Cách tiếp cận |
|---|---|---|---|
| Rất cao: Internet/user → mạng quản trị, database, domain service | Cao | Review/change sớm có kiểm soát | Owner sign-off + kiểm thử đường truy cập + quan sát |
| Rất cao | Thấp | Thu thập thêm bằng chứng sớm | Không tự disable do rủi ro dịch vụ |
| Thấp: luồng nội bộ đọc public service | Cao | Gom nhóm thay đổi định kỳ | Tối ưu theo quy trình chuẩn |
| Thấp | Thấp | Bổ sung ownership/logging | Tránh change thiếu căn cứ |
| Deny/DR/backup/security rule | Dù không có hit | Đánh giá theo chức năng chuyên biệt | Không đưa vào danh sách xóa tự động |

**Rủi ro của việc giữ rule** là nguy cơ khai thác truy cập rộng không cần thiết. **Rủi ro của việc xóa rule** là gián đoạn nghiệp vụ, khôi phục hoặc suy giảm bảo vệ. Hai loại rủi ro phải được ghi riêng trong change.

Có thể dùng một bảng chấm điểm nội bộ cho `Exposure`, `Criticality`, `EvidenceQuality` và `ChangeRisk`. Không nên nhân ra một “risk score” duy nhất rồi để script tự xóa tất cả mục có score cao.

## 12. Kế hoạch thay đổi và rollback

### 12.1. Thông tin tối thiểu trong change request

~~~text
Change: NET-FW-2026-041
Environment: lab / staging / production (nêu chính xác)
Device/context: fw-east / vsys1
Policy revision: rev21
Rule ID/UUID: 135 / [ID thực tế]
Action: Disable thử -> theo dõi -> xem xét remove

Reason: Không thấy phiên phù hợp trong cửa sổ đủ dài, owner xác nhận
Evidence: Counter snapshots, query ID, log coverage, service map, ticket
Owner approval: [nhóm / người / thời gian]
Security review: [người / thời gian]
Scheduled window: [UTC]

Pre-check: Export cấu hình, record order/NAT/object reference, test app
Expected impact: Không có luồng hợp lệ dùng rule này
Post-check: Test app, firewall deny, VPN, monitoring, ticket/incident
Abort thresholds: Lỗi dịch vụ, backup/DR fail, bất thường chưa lý giải
Rollback: Re-enable đúng UUID/rule + đúng thứ tự/policy + verify install
Success criteria: Dịch vụ và kiểm soát bảo mật ổn định qua cửa sổ đã duyệt
Evidence location: [kho được cấp quyền, link/ID không chứa secret]
~~~

### 12.2. Kiểm chứng rollback có hiệu lực

Rollback không chỉ là hoàn tác câu lệnh. Trên hệ thống quản lý tập trung, thay đổi có thể cần commit/push đến nhiều thiết bị; trên firewall HA, cần kiểm tra đồng bộ cấu hình; trong cloud, cần xác nhận policy đã apply ở mọi vùng liên quan. Kiểm tra lại đường kết nối, log và hành vi ứng dụng sau rollback.

Nếu đã xóa rule thay vì disable, phải phục hồi **đúng thứ tự và quan hệ object/NAT**. Một rule có action giống cũ nhưng đứng ở vị trí khác có thể tạo tác dụng mới nguy hiểm.

## 13. Các KPI hữu ích trong vận hành

Các chỉ số nên đo theo **quy trình review**, đồng thời báo rõ mẫu số:

| KPI | Công thức / cách diễn giải | Điều cần lưu ý |
|---|---|---|
| `Inventory coverage` | Rule có owner, purpose, review date / tổng rule trong scope | Đo chất lượng metadata, không đo traffic |
| `Evidence coverage` | Rule có dữ liệu tin cậy trong cửa sổ / tổng rule cần xét | Đánh dấu riêng UNKNOWN |
| `Candidate rate` | Số rule được đề cử review / tổng rule đã xét | Không gọi là tỷ lệ rule chắc chắn vô dụng |
| `Validated removal rate` | Rule được remove sau sign-off & monitoring / tổng rule candidate đủ điều kiện | Tách lý do bị hoãn |
| `Rollback rate` | Số change phải rollback / số change đã thực hiện | Phân tích nguyên nhân, không cố giảm số này bằng cách giấu lỗi |
| `Post-change incidents` | Sự cố liên quan thay đổi rule trong cửa sổ theo dõi | Cần mốc thay đổi và điều tra nguyên nhân |
| `Exception expiry compliance` | Rule có expiration được review đúng hạn / rule có expiration | Hữu ích cho quyền truy cập tạm |

Ví dụ: review 500 rule, 80 được đánh dấu no-log; xác minh 60/80 có dữ liệu và owner đủ, 30 ứng viên disable, 18 loại bỏ sau theo dõi, 12 giữ do DR/chu kỳ hiếm. Báo cáo phải phân biệt **80 no-log**, **30 được duyệt thử vô hiệu hóa** và **18 đã gỡ thành công**, không ghi “đã tối ưu 80 rule”.

## 14. Phối hợp với SOC, ứng dụng và đội mạng

Một change firewall có thể ảnh hưởng tới hoạt động IDS/IPS, VPN, DNS và các điểm giám sát:

- **Network operations:** xác nhận rule order, NAT, routing, HA và trạng thái cài đặt policy.
- **Security/SOC:** đánh giá nguy cơ mở/đóng truy cập, kiểm tra log và phát hiện bất thường, không vô hiệu hóa chốt chặn phòng thủ.
- **Application owner:** chứng minh luồng nghiệp vụ còn cần hay đã ngừng; thực hiện smoke test.
- **Platform/cloud team:** xác minh các security group/NSG/NACL, peering, transit gateway, service endpoints và policy cloud.
- **Backup/DR owner:** kiểm tra đường restore/failover vốn ít dùng, đặc biệt sau thay đổi segmentation.
- **Change manager/on-call:** phê duyệt, phối hợp cửa sổ thay đổi, ghi incident và rollback.

Nếu nhiều lớp cùng xử lý một luồng (cloud SG → firewall nội bộ → host firewall), việc một lớp không có hit không đồng nghĩa có thể gỡ vì luồng có thể bị chặn ở lớp khác hoặc trạng thái tuyến tạm thời làm mất quan sát. Hãy vẽ đường đi end-to-end trước khi thay đổi.

## 15. Sai lầm thường gặp và cách xử lý

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| “0 hit là vô dụng” | Xóa đường DR, backup, failover ít chạy | Bao phủ chu kỳ nghiệp vụ, xác minh owner và kịch bản hiếm |
| Chỉ đọc log của một HA node | Bỏ sót traffic đi qua node còn lại | Đối chiếu active/standby, cluster members, thời điểm failover |
| Truy vấn log một tuần rồi kết luận ba tháng | Khẳng định vượt quá chứng cứ | Ghi rõ độ dài retention và missing intervals |
| Quên NAT/FQDN hoặc IPv6 | Sai mapping rule với luồng | Kiểm tra ngữ nghĩa policy, object expansion và cả hai stack |
| Dùng một truy vấn chỉ có log allow để xét deny | Deny rule trông “không dùng” | Phân tích theo action và tính tương đương chính sách |
| Xóa một nhóm rule trong cùng change | Không biết rule nào gây lỗi | Chia nhóm nhỏ, chứng cứ và rollback riêng |
| Giữ rule cũ nhưng không có owner | Tích lũy quyền truy cập quá rộng | Escalation, gắn trách nhiệm và hạn review |
| Xóa rule nhưng để object/group hỏng tham chiếu | Drift hoặc lỗi deployment | Kiểm tra object references trước/sau |
| Coi mọi hit là lưu lượng nghiệp vụ | Giữ mãi quyền truy cập do scan | Đối chiếu ứng dụng, user, thời gian và hành vi |
| Disable xong chỉ ping một lần | Bỏ sót tác vụ dài kỳ và phụ thuộc | Smoke test, monitoring, chu kỳ quan sát phù hợp |

## 16. Bài tập áp dụng

**Bối cảnh:** một firewall phân đoạn mạng doanh nghiệp có các rule:

- `A10`: User VLAN → App server TCP/443; 150.000 log session hợp lệ/30 ngày.
- `A20`: User VLAN → App server TCP/22; 0 log/90 ngày, logging được xác minh đầy đủ, nhưng chưa tìm được owner.
- `A30`: Management VLAN → backup server TCP/22; 0 log/90 ngày, chỉ chạy khi diễn tập DR vào tháng 12.
- `D40`: Guest VLAN → internal database TCP/1433 deny; 0 hit/90 ngày.
- `A50`: App server → DNS resolvers UDP/53; counter tăng nhưng không có traffic log vì log đang tắt.

**Câu hỏi:**

1. Những rule nào thực sự là ứng viên rà soát no-traffic? Những rule nào cần giữ theo chức năng?
2. Nếu muốn disable `A20`, còn thiếu bằng chứng và phê duyệt nào?
3. Vì sao không được xóa `D40` chỉ vì không có hit?
4. Với `A50`, kết luận “không còn traffic” có đúng không? Cần thu thập thêm gì?
5. Thiết kế một change gồm pre-check, smoke test, thời gian theo dõi và rollback cho `A20`.

**Gợi ý trả lời:**

- `A10` đang được dùng; `A20` là ứng viên *review* nhưng owner chưa rõ; `A30` là đường DR ít dùng; `D40` là deny mang ý định bảo vệ; `A50` có dấu hiệu được dùng nên cần hiểu semantics counter và bổ sung DNS/flow telemetry.
- `A20` còn thiếu xác nhận chủ hệ thống, đánh giá liệu quá trình quản trị đã chuyển sang jump host chưa, kiểm tra rule order/NAT và biên bản change có quyền phê duyệt.
- Nếu xóa `D40`, có thể làm mất rào chắn chống Guest truy cập database nếu tồn tại allow rộng phía sau hoặc chính sách khác có thay đổi.
- `A50` counter tăng nên không thể suy ra không có traffic từ việc không có log; cần xem chính sách ghi log, DNS request log, flow và nguồn ứng dụng.
- Kế hoạch cho `A20`: chốt baseline/backup, xác nhận người duyệt, disable trong khung cho phép, kiểm thử SSH từ đường quản trị hợp lệ và đảm bảo user subnet không còn cần SSH trực tiếp, theo dõi lỗi/deny log qua chu kỳ hợp lý, rollback khi có ảnh hưởng chưa giải thích được.

## 17. Checklist sử dụng thực tế

Trước khi đưa một rule vào diện gỡ bỏ, xác nhận:

- [ ] Xác định đúng `device/context/policy_version/rule_id` và action.
- [ ] Có snapshot policy đang chạy và bộ đếm với thời điểm quan sát.
- [ ] Hiểu log retention, sampling, độ đầy đủ nguồn và thời điểm reset counter.
- [ ] Đã đối chiếu NAT, rule order, object groups, HA, IPv4/IPv6 và hướng luồng.
- [ ] Đã rà ứng dụng, batch theo mùa, VPN, backup, DR và đường quản trị khẩn cấp.
- [ ] Có owner/nhóm thẩm quyền xác nhận mục đích và không còn phụ thuộc.
- [ ] Đã phân tích tác động bảo mật khi bỏ allow/deny và rule mặc định.
- [ ] Có change ticket, kế hoạch disable, monitoring, tiêu chí dừng và rollback.
- [ ] Đã chạy post-check, theo dõi đủ chu kỳ và lưu bằng chứng.
- [ ] Sau remove, policy install/commit và inventory được xác minh, cập nhật.

## 18. Ghi nhớ

Rà soát rule không còn traffic là hoạt động **quản trị vòng đời quyền truy cập mạng dựa trên bằng chứng**. Cần kết hợp hit counter, log, topology, NAT/HA, lịch nghiệp vụ và xác nhận của owner để phân biệt rule ít dùng với rule đã hết nhu cầu. Thực hiện theo chu trình **observe → validate → approve → disable → monitor → remove**, có kiểm soát tác động và rollback. Kết quả tốt là policy ít quyền hơn, dễ kiểm toán hơn và vẫn bảo vệ được cả hoạt động thường ngày lẫn khả năng phục hồi khi có sự cố.
