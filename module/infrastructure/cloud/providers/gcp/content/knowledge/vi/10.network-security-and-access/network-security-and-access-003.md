# Firewall logging và rà soát lưu lượng bị chặn

Trong một hệ thống Google Cloud, ứng dụng có thể đã triển khai thành công trên Compute Engine hoặc GKE nhưng vẫn không kết nối được tới database, API nội bộ hay dịch vụ quản trị. Khi đó, thông báo `timeout` chưa đủ để biết nguyên nhân là **firewall từ chối**, **route sai**, **dịch vụ không lắng nghe**, hay **lỗi xác thực**. Đội vận hành cần bằng chứng về kết nối nào được phép, kết nối nào bị chặn và quy tắc nào dẫn tới quyết định ấy.

**Firewall Rules Logging** của Google Cloud cung cấp nhật ký về những kết nối mạng khớp với quy tắc tường lửa được bật ghi log. Nhờ đó, người quản trị có thể điều tra sự cố, rà soát các rule mở quá rộng, xác minh việc chặn các luồng không được phép và giám sát các thay đổi sau triển khai.

Bài học thuộc chương **Bảo mật và truy cập mạng** trong module **CLOUD_PROVIDERS_GCP**, kết nối kiến thức về IAM, VPC, định tuyến và các workload Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Trọng tâm là **lưu lượng bị chặn ở lớp mạng**, cách thu thập bằng chứng và cách phản ứng có kiểm soát.

Sau bài học, bạn có thể:

1. Phân biệt Firewall Rules Logging, VPC Flow Logs, Cloud Audit Logs và log ứng dụng.
2. Giải thích tại sao một kết nối bị chặn có thể **không có** firewall log.
3. Bật logging cho những VPC firewall rules phù hợp, xác định quy tắc đang tác động và đọc trường quan trọng trong log.
4. Viết bộ lọc Cloud Logging theo `DENIED`, IP nguồn/đích, cổng, mạng, thời gian và rule.
5. Rà soát luồng bị chặn mà không mở quyền quá rộng, rồi kiểm thử lại cả luồng hợp lệ và luồng cần từ chối.
6. Thiết kế thời hạn lưu log, quyền truy cập và quy trình điều tra phù hợp với yêu cầu bảo mật, độ tin cậy và chi phí.

## 1. Firewall quyết định điều gì trước khi có log?

VPC firewall kiểm soát những loại lưu lượng được hỗ trợ đến hoặc đi từ các tài nguyên mạng theo **hướng (ingress/egress)**, **protocol và cổng**, **nguồn/đích**, **mục tiêu áp dụng**, cùng **thứ tự ưu tiên** của rule và policy. Route trả lời câu hỏi “gửi gói tin đi đâu?”, còn firewall trả lời “lưu lượng có được phép đi theo đường đó hay không?”.

Ví dụ:

~~~mermaid
flowchart LR
    WEB["VM Web<br/>10.10.1.10"] -->|"TCP 8080"| FW["Đánh giá firewall<br/>ở phía workload đích"]
    FW -->|"ALLOW"| API["VM API<br/>10.10.2.10"]
    FW -->|"DENY"| DROP["Bị từ chối"]
    FW -. "Quy tắc được bật logging" .-> LOG["Cloud Logging<br/>Firewall Rules Logging"]
~~~

Sơ đồ chỉ mô tả logic đối với kết nối khớp một quy tắc có logging; không phải mọi trường hợp từ chối đều được ghi nhật ký. Một yêu cầu có thể thất bại trước khi chạm đến rule mong muốn, hoặc bị một policy có độ ưu tiên cao hơn quyết định.

### 1.1. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Ingress** | Lưu lượng đi vào đối tượng được bảo vệ. | Client gọi TCP 8080 trên VM API. |
| **Egress** | Lưu lượng rời khỏi đối tượng được bảo vệ. | VM gọi TCP 443 đến một dịch vụ ngoài VPC. |
| **ALLOW** | Rule cho phép lưu lượng phù hợp điều kiện. | Chỉ Web subnet được gọi API cổng 8080. |
| **DENY** | Rule từ chối lưu lượng phù hợp điều kiện. | Chặn mạng thử nghiệm gọi database cổng 5432. |
| **Priority** | Tham số tham gia chọn rule có hiệu lực theo cơ chế và cấp policy. | Một rule cụ thể có thể được ưu tiên hơn rule rộng trong cùng tầng đánh giá. |
| **Target** | Nhóm tài nguyên mà rule được áp dụng. | VM có network tag hoặc service account được chọn. |
| **Firewall logging** | Ghi lại thông tin về kết nối được một rule có bật logging đánh giá. | Log chứa disposition `DENIED` và rule tham chiếu. |

Google Cloud có **VPC firewall rules**, **hierarchical firewall policies** và **network firewall policies**. Cách tạo và quản lý rule khác nhau, nhưng khi điều tra phải xem **thứ tự đánh giá policy hiệu lực**, không chỉ danh sách quy tắc trực tiếp tại project. Với mỗi loại policy, hãy kiểm tra tính năng logging và quyền IAM được hỗ trợ.

### 1.2. Quy tắc ngầm định và vì sao “không có log” chưa nói lên tất cả

Một VPC có các hành vi ngầm định, thường được tóm tắt là:

- **Implied deny ingress:** khi không có quy tắc cho phép phù hợp, kết nối inbound có thể bị chặn.
- **Implied allow egress:** nếu không bị hạn chế bằng rule/policy khác, lưu lượng outbound được cho phép theo mặc định.

Những **implied rules** này không phải rule thông thường mà bạn có thể bật Firewall Rules Logging trực tiếp. Vì vậy, **một kết nối bị implied deny ingress từ chối có thể không tạo firewall log**. Tương tự, nếu một kết nối được cho phép theo implied allow egress, bạn cũng không có bản ghi do “bật logging trên implied rule”.

Muốn ghi nhận một nhóm kết nối bị chặn phục vụ điều tra, có thể cần tạo **explicit deny rule** đúng phạm vi, bật logging và kiểm tra xem rule có thực sự là rule ra quyết định hay không. Không tạo deny rule chỉ để ghi log trên đường kết nối quan trọng mà chưa đánh giá tác động.

### 1.3. Log của “rule khớp” khác với nhật ký mọi packet

Firewall Rules Logging cung cấp thông tin về **kết nối** theo cơ chế sản phẩm, đặc biệt cho những giao thức được hỗ trợ như TCP và UDP. Không nên hiểu nó là công cụ bắt từng packet, thu payload hay bản ghi đầy đủ mọi request HTTP.

Các hệ quả thực hành:

- Log thường cung cấp **metadata** mạng và quyết định `ALLOWED` hoặc `DENIED`; không tự cung cấp nội dung body, cookie hay câu truy vấn SQL.
- Một kết nối lâu dài hoặc nhiều lần thử có thể có cách sinh bản ghi khác một request đơn lẻ; **không dùng số dòng log để đếm chính xác số HTTP request hoặc số packet**.
- Nếu lưu lượng không đi qua thành phần được logging hỗ trợ, hoặc khớp rule/policy khác không bật log, bạn có thể không thấy bản ghi mình kỳ vọng.
- Log có thể đến Cloud Logging trễ; hãy xác minh phạm vi thời gian, quyền xem log, log bucket và bộ lọc trước khi kết luận “không có traffic”.

## 2. So sánh các nguồn log khi điều tra sự cố mạng

Không có một nguồn log đơn lẻ giải thích mọi thất bại kết nối. Bảng dưới đây giúp chọn đúng nguồn bằng chứng.

| Nguồn | Nội dung phản ánh | Dùng khi | Giới hạn |
| --- | --- | --- | --- |
| **Firewall Rules Logging** | Quyết định match của firewall rule có bật logging, kèm thông tin kết nối/rule. | Muốn biết luồng đã bị **DENY** hay được **ALLOW** bởi rule nào. | Không phải packet capture; implied rules không phát log trực tiếp; cần rule được bật logging. |
| **VPC Flow Logs** | Thông tin luồng mạng do tính năng thu thập/lấy mẫu cung cấp. | Quan sát xu hướng lưu lượng, nguồn/đích và khối lượng traffic. | Có thể được lấy mẫu và tổng hợp; không tự là bằng chứng đầy đủ mọi deny. |
| **Cloud Audit Logs** | Ai/cái gì thay đổi cấu hình hoặc gọi API quản trị theo loại audit log. | Điều tra ai sửa firewall, VPC, IAM hay các tài nguyên liên quan. | Không thay thế log quyết định mạng cho từng kết nối. |
| **Cloud Armor request logs** | Quyết định chính sách bảo vệ HTTP(S) ở load balancer theo cấu hình. | Điều tra WAF, IP filter, rate limiting cho request web. | Không phải VPC firewall trên NIC của VM. |
| **Application / OS logs** | Socket errors, timeout, lỗi TLS, xác thực, lỗi ứng dụng. | Xác minh server có lắng nghe, app có trả lời hay không. | Có thể không biết VPC firewall nào đã chặn kết nối. |
| **Connectivity Tests** | Phân tích đường đi, cấu hình định tuyến và firewall theo khả năng công cụ. | Tìm điểm có thể chặn đường kết nối cụ thể. | Phân tích không thay thế quan sát request thật hoặc sức khỏe ứng dụng. |

Ví dụ một client gặp HTTP 403: nếu Cloud Armor từ chối yêu cầu tại load balancer, bạn nên tìm bằng chứng trong **load balancer/Cloud Armor logs**. `403` của ứng dụng cũng có thể do phân quyền API. Không mặc định mọi `403` đều đến từ VPC firewall; VPC firewall **DENY** thường làm kết nối thất bại ở lớp mạng và có thể biểu hiện là timeout.

### 2.1. Phạm vi áp dụng đối với Compute Engine, GKE và dịch vụ managed

- **Compute Engine:** firewall rules và policies liên quan đến NIC/đích VM là đối tượng điển hình để điều tra kết nối.
- **GKE:** lưu lượng node, Pod và chính sách mạng cần được phân tích theo **mô hình mạng của cluster**. VPC firewall không thay thế Kubernetes NetworkPolicy hay những chế độ bảo vệ pod cụ thể.
- **Cloud Run:** kết nối vào dịch vụ serverless, VPC egress và HTTPS ingress có những cơ chế riêng. Không suy rằng mọi request Cloud Run sẽ tạo log ở VPC firewall rules giống VM.
- **Cloud SQL:** đường kết nối private, connector, IAM database authentication và quyền database là các lớp riêng. Firewall Rules Logging có thể giúp phân tích phần mạng tương ứng, nhưng không cho biết câu lệnh SQL bị từ chối vì thiếu `GRANT`.
- **Load balancing và CDN:** một request có thể bị chặn ở chính sách L7 hoặc được phục vụ tại edge trước khi tới backend. Cần đối chiếu logs của thành phần đã thực sự xử lý yêu cầu.

Trong kiến trúc nhiều tầng, phải xác định **điểm ra quyết định** của lỗi trước khi chọn nơi tìm log.

## 3. Chuẩn bị trước khi bật Firewall Rules Logging

### 3.1. Chọn rule nào cần ghi log

Ghi log trên **mọi** quy tắc của một hệ thống có tải lớn có thể tạo lượng dữ liệu đáng kể. Nên ưu tiên nơi log phục vụ quyết định vận hành hoặc bảo mật rõ ràng:

1. **Explicit deny** bảo vệ database, môi trường production hoặc vùng dữ liệu nhạy cảm.
2. **Allow rule nhạy cảm** cho SSH, RDP, giao tiếp với hệ thống quản trị hoặc đường dữ liệu quan trọng, để phát hiện truy cập bất thường.
3. **Rule mới thay đổi** cần giám sát trong một khoảng đánh giá nhằm xác nhận ứng dụng hợp lệ vẫn hoạt động.
4. **Đường egress kiểm soát** khi cần kiểm tra kết nối tới những IP/cổng bị hạn chế.
5. **Rule trong đợt điều tra** khi có báo cáo `timeout` hoặc thay đổi kiến trúc mà chưa rõ kết quả thực tế.

Với rule allow có lượng traffic cao, cần cân nhắc chi phí log, thời gian giữ, bộ lọc hoặc phương án quan sát khác. Việc **bật logging không thay đổi quyết định ALLOW/DENY**, nhưng thay đổi lượng dữ liệu được gửi đến Cloud Logging.

### 3.2. Quyền IAM và phạm vi tài nguyên

Để thực hiện các thao tác, danh tính cần quyền phù hợp:

| Nhiệm vụ | Quyền/cách tiếp cận |
| --- | --- |
| Xem cấu hình VPC firewall rules | Vai trò có quyền đọc thông tin Compute Engine firewall, ví dụ role xem cấu hình mạng phù hợp. |
| Bật/tắt logging hoặc sửa rule | Principal có quyền cập nhật firewall rule, chẳng hạn trong một role quản trị bảo mật mạng được cấp đúng phạm vi. |
| Đọc log trong Cloud Logging | Vai trò đọc log như `roles/logging.viewer` trong phạm vi cho phép, cùng quyền bổ sung nếu loại log/điều kiện truy cập yêu cầu. |
| Xem thay đổi cấu hình IAM/firewall | Quyền xem các Admin Activity audit logs và thông tin tài nguyên liên quan. |
| Sửa log retention, sink, bucket | Quyền quản lý Cloud Logging riêng, theo phân công quản trị dữ liệu. |

**Nguyên tắc tách nhiệm vụ:** người xem và phân tích log thường không cần quyền thay đổi firewall. Người được phép sửa firewall không tự động phải có quyền xóa sink, thay retention hoặc làm mất bằng chứng audit. IAM trong project, folder hoặc organization có thể được kế thừa; cần kiểm tra **quyền hữu hiệu**.

### 3.3. Ghi nhận trạng thái ban đầu

Trước khi thay đổi rule, lưu những thông tin phục vụ so sánh:

- Project ID, VPC, region/subnet và VM/đối tượng đích.
- Tên rule và loại rule/policy, hướng ingress/egress, priority, ALLOW/DENY.
- Source/destination ranges, target tags/service accounts, giao thức/cổng và các điều kiện liên quan.
- Cờ logging hiện tại, log bucket dự kiến và khoảng thời gian cần quan sát.
- Chủ ứng dụng, luồng nghiệp vụ hợp lệ và cách rollback khi rule được thay đổi.

Không nên đổi hành vi của firewall và bật logging trong cùng một bước nếu mục tiêu đầu tiên là đo hệ thống hiện tại. Nếu bắt buộc thay đổi, ghi rõ cả hai thay đổi và thử nghiệm độc lập.

## 4. Bật logging cho VPC firewall rule

Phần này sử dụng **VPC firewall rule** thông thường và lệnh gcloud minh họa. Đối với hierarchical firewall policies hoặc network firewall policies, cú pháp quản lý rule khác; kiểm tra tài liệu tương ứng thay vì dùng lệnh firewall-rules của VPC.

### 4.1. Kiểm tra rule hiện có

Trong Cloud Shell hoặc Bash đã cấu hình gcloud:

~~~bash
export PROJECT_ID="YOUR_PROJECT_ID"
export RULE_NAME="deny-app-to-db"

# Chỉ đọc: chọn đúng project và xem rule
gcloud config set project "$PROJECT_ID"
gcloud compute firewall-rules describe "$RULE_NAME" \
  --format="yaml(name,network,direction,priority,disabled,denied,allowed,sourceRanges,targetTags,logConfig)"
~~~

`YOUR_PROJECT_ID` và `deny-app-to-db` chỉ là giá trị mẫu. Xác nhận rule thuộc **đúng VPC** và áp dụng cho **đúng nhóm đích** trước khi thực hiện ghi. Nếu rule chưa tồn tại, không tự tạo rule mang tên đó trong production.

### 4.2. Bật logging trên rule đã được phê duyệt

~~~bash
# Thao tác ghi: chỉ thực hiện trên firewall rule do bạn sở hữu
gcloud compute firewall-rules update "$RULE_NAME" \
  --enable-logging

# Đọc lại sau thay đổi
gcloud compute firewall-rules describe "$RULE_NAME" \
  --format="yaml(name,network,direction,priority,logConfig)"
~~~

Trong Console, có thể vào khu vực quản lý **VPC firewall rules**, chọn rule phù hợp, chỉnh **Logs/Logging** và lưu. Vị trí menu có thể thay đổi theo giao diện và loại policy.

Cấu hình `logConfig` xác nhận logging có được bật hay không. Một số hình thức logging còn cho phép lựa chọn **metadata được ghi kèm**, tùy loại rule/policy; cần kiểm tra khả năng hỗ trợ và tác động tới mức dữ liệu nhạy cảm được lưu.

Nếu chỉ muốn **tắt logging** sau khi hoàn thành một đợt điều tra, có thể dùng:

~~~bash
# Thao tác ghi; không thay đổi ALLOW/DENY của rule
gcloud compute firewall-rules update "$RULE_NAME" \
  --no-enable-logging
~~~

Khi tắt logging, các log đã thu thập trước đó vẫn tuân theo retention và quyền truy cập của Cloud Logging; tắt logging không tự xóa những bản ghi lịch sử.

### 4.3. Tạo explicit deny có logging trong môi trường lab

Để thấy log `DENIED`, người học có thể dùng VPC và VM thử nghiệm **đã được cấp quyền sử dụng**, không ảnh hưởng production. Ví dụ minh họa sau giả định:

- VPC tên `lab-sec-vpc`.
- VM nguồn có IP trong dải `10.90.10.0/24`.
- VM đích gắn network tag `lab-sec-db` và lắng nghe TCP 8080.
- Không có policy hoặc rule ưu tiên cao hơn quyết định khác trên luồng này.

~~~bash
# Chỉ chạy trong PROJECT LAB được phép, sau khi xác minh VPC/tag/IP
gcloud compute firewall-rules create lab-deny-db-8080 \
  --network=lab-sec-vpc \
  --direction=INGRESS \
  --priority=900 \
  --deny=tcp:8080 \
  --source-ranges=10.90.10.0/24 \
  --target-tags=lab-sec-db \
  --enable-logging
~~~

Rule này không chỉ ghi log mà còn **chặn** lưu lượng khớp điều kiện. Nếu tạo nhầm trên hệ thống đang chạy, tác động tới người dùng là thật. Vì vậy cần có VPC lab riêng, xác minh source/target và dự kiến cách xóa rule sau bài tập.

Một thao tác từ VM nguồn như:

~~~bash
# Chạy BÊN TRONG VM nguồn của lab; thay IP đích thực tế
curl -v --connect-timeout 3 --max-time 5 \
  http://10.90.20.10:8080/
~~~

được kỳ vọng thất bại do firewall **nếu** luồng đi đúng qua rule vừa tạo. Timeout **chưa phải bằng chứng duy nhất**: cần có log `DENIED` hoặc phân tích policy/effective rules để xác nhận nguyên nhân.

Sau thực hành, chỉ xóa rule do bài lab tạo:

~~~bash
gcloud compute firewall-rules delete lab-deny-db-8080 --quiet
~~~

Việc xóa phải được thực hiện trong đúng project lab; nếu không chắc rule thuộc bài tập, kiểm tra trước rồi mới dọn. Xóa rule không đồng nghĩa mọi luồng tới VM đích được mở; implied deny ingress và những rule/policy khác vẫn tồn tại.

## 5. Đọc và giải thích một bản ghi Firewall Rules Logging

Tùy loại kết nối và bản ghi, một log có thể chứa những trường như:

| Trường thường gặp | Cách đọc | Lỗi phân tích cần tránh |
| --- | --- | --- |
| `timestamp` | Thời điểm sự kiện được ghi nhận. | Không xem `receiveTimestamp` là thời điểm packet chắc chắn được phát. |
| `logName` | Nguồn log trong Cloud Logging. | Không nhầm với audit log hoặc log ứng dụng. |
| `resource.type`, `resource.labels` | Đối tượng được gắn log, ví dụ subnetwork/project. | Không mặc định là tên VM đích; cần xem thêm thông tin instance. |
| `jsonPayload.disposition` | Kết quả quyết định, thường `ALLOWED` hoặc `DENIED`. | `DENIED` là kết luận về traffic khớp rule, không phải lỗi đăng nhập ứng dụng. |
| `jsonPayload.connection.src_ip` | IP nguồn của kết nối được ghi. | Có thể là IP sau NAT/proxy; xem đúng điểm quan sát. |
| `jsonPayload.connection.dest_ip` | IP đích của kết nối. | Có thể là IP nội bộ, không phải hostname người dùng nhập. |
| `jsonPayload.connection.src_port` | Cổng nguồn. | Cổng tạm thời phía client có thể thay đổi theo kết nối. |
| `jsonPayload.connection.dest_port` | Cổng đích. | Quan trọng để phân biệt SSH 22, HTTPS 443, database 5432... |
| `jsonPayload.connection.protocol` | Protocol IP theo số định danh được ghi, ví dụ TCP 6, UDP 17. | Đừng giả định chuỗi hiển thị luôn là `TCP`/`UDP`. |
| `jsonPayload.rule_details` | Chi tiết rule đã dẫn đến quyết định, có thể gồm reference, direction, priority, action. | Không kết luận toàn bộ thứ tự policy chỉ từ một trường nếu có nhiều lớp. |
| `jsonPayload.instance`, `jsonPayload.vpc` | Metadata bổ sung về VM/VPC khi hiện diện. | Mức metadata có thể thay đổi theo cấu hình và tình huống. |

Một bản ghi **minh họa**, đã rút gọn và thay định danh:

~~~json
{
  "timestamp": "2026-11-19T01:15:00Z",
  "logName": "projects/lab-project/logs/compute.googleapis.com%2Ffirewall",
  "resource": {
    "type": "gce_subnetwork"
  },
  "jsonPayload": {
    "disposition": "DENIED",
    "connection": {
      "src_ip": "10.90.10.10",
      "dest_ip": "10.90.20.10",
      "src_port": 51642,
      "dest_port": 8080,
      "protocol": 6
    },
    "rule_details": {
      "reference": "network:lab-sec-vpc/firewall:lab-deny-db-8080",
      "direction": "INGRESS",
      "priority": 900,
      "action": "DENY"
    }
  }
}
~~~

Đây là ví dụ để tập cách đọc trường, **không phải bản ghi đã thu từ Google Cloud**. Schema và những metadata thực tế có thể khác theo loại rule, môi trường và cấu hình logging.

**Diễn giải:** một kết nối TCP (protocol 6) từ `10.90.10.10` đến `10.90.20.10:8080` bị từ chối ở hướng ingress bởi rule được tham chiếu. Cần đối chiếu IP với subnet, NIC, tên VM, tài nguyên đích và thời điểm thực tế để kết luận đây là kết nối hợp lệ bị chặn nhầm hay một hành vi cần giữ chặn.

### 5.1. Ý nghĩa của source và destination khi có NAT hoặc load balancer

IP xuất hiện trong log là thông tin kết nối tại **điểm mà sản phẩm ghi nhận**. Nếu có load balancer, proxy, Cloud NAT, kết nối private hoặc nhiều NIC, IP nguồn/đích quan sát có thể khác IP ban đầu của trình duyệt.

Ví dụ một người dùng Internet gọi load balancer HTTPS: log của VPC firewall phía backend có thể mô tả kết nối từ hệ thống cân bằng tải/đường proxy tới VM, không nhất thiết dùng IP của người dùng cuối như nguồn trên lớp mạng. Muốn điều tra người dùng nào gửi request, phải đối chiếu thêm **load balancer request log**, header được hệ thống tin cậy xử lý và log ứng dụng.

### 5.2. Quyết định DENIED có thể là hành vi mong muốn

Không phải mọi `DENIED` đều là sự cố. Một firewall tốt **cố ý từ chối** những luồng ngoài chính sách:

- Máy Web không được truy cập thẳng database.
- VM ở mạng thử nghiệm không được gọi môi trường production.
- Internet không được mở phiên SSH trực tiếp vào backend riêng.
- Một workload chỉ cần gọi API qua TCP 443 thì những cổng egress không cần thiết có thể bị chặn.

Khi rà soát, cần phân loại `DENIED` thành **chặn đúng chính sách**, **chặn nhầm luồng hợp lệ**, và **hoạt động bất thường cần điều tra**. Chỉ giảm số dòng log DENIED không phải mục tiêu bảo mật.

## 6. Tìm lưu lượng bị chặn trong Cloud Logging

Có hai cách thuận tiện: dùng **Logs Explorer** trên Cloud Console để lọc trực quan hoặc dùng **gcloud logging read** khi cần lặp lại truy vấn trong quá trình xử lý sự cố. Ví dụ bên dưới giả định bạn có quyền xem log, đã bật Firewall Rules Logging trên rule có hiệu lực và các bản ghi đã được chuyển đến nơi bạn có quyền truy cập.

### 6.1. Truy vấn cơ bản trong Logs Explorer

Mở **Logging → Logs Explorer**, chọn đúng project và phạm vi thời gian phù hợp. Nhập bộ lọc:

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
~~~

Kết quả phù hợp sẽ là những bản ghi Firewall Rules Logging trên nguồn log tương ứng có quyết định từ chối. `log_id()` giúp lọc theo log ID mà không phải viết toàn bộ tên log theo project, nhưng vẫn phải chọn phạm vi project/log scope đúng.

**Các bộ lọc thường dùng:**

**Chặn một IP nguồn cụ thể:**

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
jsonPayload.connection.src_ip="10.90.10.10"
~~~

**Chặn kết nối tới một IP/cổng đích:**

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
jsonPayload.connection.dest_ip="10.90.20.10"
jsonPayload.connection.dest_port=8080
~~~

**Tìm rule cụ thể qua phần tham chiếu:**

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.rule_details.reference:"lab-deny-db-8080"
~~~

Dấu `:` trong bộ lọc Logging thường được dùng để tìm phần chuỗi phù hợp; dấu `=` để so khớp giá trị theo cách Logging query language hỗ trợ. Khi trường không tồn tại trong loại log đang xem, bộ lọc bằng trường đó sẽ không trả kết quả, dù các entry khác vẫn có. Có thể bắt đầu bằng ba dòng cơ bản rồi bổ sung điều kiện từng bước.

### 6.2. Thu hẹp theo thời gian và đúng điểm quan sát

Khi xử lý sự cố, người dùng thường báo: “10:15 sáng hôm nay không kết nối được”. Đừng tìm cả ngày rồi quy kết mọi DENIED cho lỗi đó. Hãy quy đổi sang **khoảng UTC hoặc múi giờ hiển thị nhất quán**, sau đó lấy cửa sổ vài phút quanh sự kiện:

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
timestamp>="2026-11-19T03:10:00Z"
timestamp<="2026-11-19T03:20:00Z"
~~~

Khoảng thời gian trong ví dụ chỉ để minh họa cú pháp. Trước khi truy vấn, thay bằng thời điểm đã xác minh từ incident. So sánh `timestamp` và `receiveTimestamp` nếu nghi ngờ bản ghi được chuyển tới Cloud Logging trễ.

Khi ứng dụng nằm trong **Shared VPC**, project chạy workload và host project quản lý mạng có thể không phải một. Phải kiểm tra nơi nhật ký thực sự được ghi, quyền xem log, log scope, log sink và hệ thống tập trung log, thay vì chỉ chọn project có tên gần với ứng dụng.

### 6.3. Đọc log bằng gcloud

Ví dụ Bash/Cloud Shell:

~~~bash
export PROJECT_ID="YOUR_PROJECT_ID"

# Chỉ đọc: lấy tối đa 30 bản ghi bị firewall từ chối
gcloud logging read \
  'resource.type="gce_subnetwork" AND log_id("compute.googleapis.com/firewall") AND jsonPayload.disposition="DENIED"' \
  --project="$PROJECT_ID" \
  --limit=30 \
  --format=json
~~~

Để chỉ xem những trường quan trọng, có thể định dạng đầu ra:

~~~bash
gcloud logging read \
  'resource.type="gce_subnetwork" AND log_id("compute.googleapis.com/firewall") AND jsonPayload.disposition="DENIED"' \
  --project="$PROJECT_ID" \
  --limit=30 \
  --format="table(timestamp,jsonPayload.connection.src_ip,jsonPayload.connection.dest_ip,jsonPayload.connection.dest_port,jsonPayload.rule_details.reference)"
~~~

Đây là những lệnh **chỉ đọc**; không đổi firewall. Nếu không thấy kết quả, nguyên nhân có thể là bộ lọc quá hẹp, quyền/log scope chưa đúng, hoặc thật sự chưa có bản ghi phù hợp. Không tự động cấp quyền Administrator hoặc thay policy chỉ vì truy vấn trả về danh sách trống.

### 6.4. Từ một log DENIED tới quy tắc đã tác động

Giả sử bạn tìm được một bản ghi:

~~~text
10.90.10.10:51642 -> 10.90.20.10:8080 TCP
disposition: DENIED
rule: lab-deny-db-8080
direction: INGRESS
priority: 900
~~~

Hãy trả lời theo thứ tự:

1. **Nguồn là gì?** `10.90.10.10` thuộc subnet/VM/Pod hoặc một đường NAT nào? Đây có phải workload được phép gọi đích không?
2. **Đích là gì?** `10.90.20.10` có đúng VM và NIC của dịch vụ đang lỗi không? Nó có thực sự lắng nghe TCP 8080 không?
3. **Rule có chủ đích gì?** Lý do tạo `lab-deny-db-8080` là bảo vệ tầng Data hay chặn tạm trong thời gian sự cố?
4. **Luồng có hợp lệ theo thiết kế không?** Nếu Web được phép gọi App nhưng không được gọi Data, kết nối Web → Data bị chặn là kết quả đúng.
5. **Có thay đổi gần thời điểm lỗi không?** Đối chiếu thay đổi firewall, deployment, IP, DNS, route, service account, network tag và cấu hình ứng dụng qua audit/config history.
6. **Hành động phù hợp là gì?** Giữ deny, chỉnh cấu hình client để gọi đúng điểm đích, hoặc đề nghị thay đổi rule có phạm vi và người phê duyệt.

Nếu sửa firewall thực sự cần thiết, hãy ưu tiên **cho phép đúng nguồn, đúng đích, đúng protocol/cổng** và đúng đối tượng mục tiêu. Không giải quyết mọi timeout bằng rule `ALLOW all` từ `0.0.0.0/0`.

## 7. Quy trình rà soát sự cố kết nối có lưu lượng bị chặn

Một quy trình có thể tái sử dụng cho môi trường dev, staging hoặc production:

~~~mermaid
flowchart TD
    START["Báo lỗi kết nối<br/>nguồn, đích, cổng, thời gian"] --> OBS{"Có Firewall Rules Log<br/>phù hợp không?"}
    OBS -->|Có DENIED| RULE["Xác định rule/policy<br/>và đối tượng mục tiêu"]
    OBS -->|Không| OTHER["Kiểm tra implied deny,<br/>priority, log scope, routing,<br/>dịch vụ và những lớp khác"]
    RULE --> EXPECT{"Kết nối được phép<br/>theo thiết kế?"}
    EXPECT -->|Không| KEEP["Giữ chặn; phân loại sự kiện<br/>và tăng giám sát nếu cần"]
    EXPECT -->|Có| FIX["Đề nghị thay đổi tối thiểu<br/>có phê duyệt"]
    FIX --> TEST["Thử lại positive<br/>và negative cases"]
    OTHER --> TEST
    TEST --> END["Ghi bằng chứng,<br/>theo dõi và đóng incident"]
    KEEP --> END
~~~

### 7.1. Bước 1 — Thu thập dữ kiện của kết nối

Một yêu cầu điều tra tốt nên ghi:

| Thuộc tính | Ví dụ |
| --- | --- |
| Thời gian lỗi (có múi giờ) | 10:15 ICT, 19/11/2026 |
| Client/source | VM `web-01`, IP `10.10.1.10` |
| Destination | VM `app-01`, IP `10.10.2.10` |
| Protocol/port | TCP 8080 |
| Project/VPC/subnet | `shop-prod` / `prod-vpc` / `app-subnet` |
| Kỳ vọng nghiệp vụ | Web được gọi API nội bộ |
| Kết quả quan sát | `curl` timeout sau 5 giây |
| Lần chạy thử và trace ID | Nếu có, giúp liên kết với log ứng dụng |

Không nhất thiết tất cả log đều có đầy đủ thuộc tính trên. Một số thông tin phải lấy từ người báo lỗi, cấu hình triển khai và công cụ quản trị mạng.

### 7.2. Bước 2 — Tìm DENIED, rồi kiểm tra effective policy

Lọc theo khoảng thời gian, IP, cổng và `DENIED`. Nếu có log, đọc `rule_details` và kiểm tra rule tại nơi quản lý nó. Sau đó đối chiếu:

- Phạm vi VPC, ingress/egress, target của rule.
- Priority và các lớp policy phía trên, kể cả deny/allow liên quan.
- Đối tượng mạng có đổi network tag hoặc service account sau lần deploy mới không.
- Dải nguồn có thay đổi vì autoscaling, proxy, NAT, node GKE hoặc cấu hình subnet không.
- Rule thực sự là nguyên nhân của sự cố hay lưu lượng DENIED chỉ là traffic thăm dò không liên quan.

Nếu source/destination đi qua load balancer hoặc endpoint managed, cần đọc thêm log của thành phần trung gian. Đừng kết luận từ một IP mà chưa biết nó thuộc client, proxy hay backend.

### 7.3. Bước 3 — Không thấy DENIED thì kiểm tra gì?

**Không tìm thấy log không phải bằng chứng firewall đã cho phép.** Kiểm tra lần lượt:

1. Rule nghi ngờ có **bật logging** và có hiệu lực trong thời điểm lỗi không?
2. Lưu lượng có bị **implied deny ingress** mà không có explicit deny bật log không?
3. Có rule hoặc hierarchical/network firewall policy **được đánh giá trước** nên rule đang xem không hề match không?
4. Query có chọn sai **project, log scope, log bucket, resource type, thời gian** hoặc loại log không?
5. Log có bị **router/sink/exclusion** xử lý, retention hết hạn hoặc quyền xem log không đủ không?
6. Kết nối thực tế có đi qua **VPC/NIC** đang xem không, hay dừng ở Cloud Armor, load balancer, Cloud Run ingress, GKE NetworkPolicy hoặc ứng dụng?
7. Route, DNS, NAT, máy đích, local firewall và port đang lắng nghe có đúng không?
8. Có lỗi TLS, database authentication, IAM hoặc response từ ứng dụng được người dùng gọi chung là “lỗi mạng” không?

Ví dụ, khi không có route tới IP đích, traffic có thể không đến được nơi bạn kỳ vọng nhìn thấy ingress firewall log. Khi ứng dụng trả HTTP 401 hoặc 403, cần điều tra xác thực/phân quyền ở tầng ứng dụng trước khi thay đổi firewall.

### 7.4. Bước 4 — Phân loại và quyết định

| Phân loại | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| **Chặn đúng chính sách** | Web gọi thẳng Data dù kiến trúc chỉ cho Web → App → Data. | Giữ rule; sửa client nếu gọi sai; lưu bằng chứng đúng thiết kế. |
| **Chặn nhầm traffic hợp lệ** | Rule mới chặn App → database trên cổng được phê duyệt. | Điều chỉnh phạm vi nhỏ nhất, review, thử nghiệm trước và sau. |
| **Thử truy cập bất thường** | IP ngoài danh sách, lặp lại nhiều đích hoặc nhiều cổng, không có nhu cầu nghiệp vụ. | Giữ chặn, điều tra nguồn, đánh giá cảnh báo và kiểm tra cấu hình/danh tính liên quan. |
| **Chưa đủ bằng chứng** | Không có log phù hợp, kết nối vẫn timeout hoặc lỗi ở nhiều lớp. | Bổ sung đo kiểm, cấu hình, log từ thành phần khác; chưa vội sửa rule. |

### 7.5. Bước 5 — Kiểm thử trước và sau khi sửa

Một thay đổi firewall chỉ hoàn tất khi hai nhóm thử nghiệm đều đạt:

**Positive test:** workload được phê duyệt có thể gọi đúng đích, cổng, protocol, và ứng dụng phản hồi hợp lệ.

**Negative test:** workload không được phê duyệt **vẫn bị chặn**. Đặc biệt kiểm tra từ nguồn ở subnet khác, VM không thuộc service account được cho phép, hoặc luồng trực tiếp mà kiến trúc yêu cầu đi qua gateway.

Sau thay đổi, lưu ID thay đổi, rule cũ/mới, ảnh hưởng, thời điểm, kết quả kiểm thử và người phê duyệt. Quan sát log trong khoảng thời gian đủ đại diện cho ứng dụng, vì một kết nối đã mở từ trước có thể biểu hiện khác với kết nối **mới** khi chính sách thay đổi.

## 8. Tình huống thực tế: Web không kết nối được App

Một nhóm triển khai hệ thống quản lý khóa học:

- **Web tier:** VM tại subnet `10.20.10.0/24`.
- **Application tier:** VM tại subnet `10.20.20.0/24`, lắng nghe TCP 8080.
- **Data tier:** cơ sở dữ liệu chỉ cho phép kết nối từ App tier qua đường mạng được thiết kế.
- **VPC:** `learning-prod-vpc` với rule hạn chế kết nối giữa các tầng.

Sau một lần cập nhật firewall, người dùng gặp HTTP 502 từ Web. Người trực kiểm tra trên Web VM:

~~~bash
# Chạy trên VM Web theo đúng chính sách truy cập của tổ chức
curl --verbose --connect-timeout 3 --max-time 5 \
  http://10.20.20.10:8080/health
~~~

Giả sử lệnh trả về timeout. Một log minh họa cho thấy:

~~~text
timestamp: 2026-11-19T04:15:03Z
connection: 10.20.10.12:54230 -> 10.20.20.10:8080 TCP
disposition: DENIED
direction: INGRESS
rule: deny-web-to-app-temporary
~~~

### 8.1. Đọc bằng chứng

Đội kỹ thuật xác nhận ba điều trước khi sửa:

1. IP `10.20.10.12` thực sự là NIC của Web VM, còn `10.20.20.10` là App VM đang lắng nghe cổng 8080.
2. Tài liệu kiến trúc cho phép Web gọi App cổng 8080; Web không được kết nối thẳng Data.
3. Rule `deny-web-to-app-temporary` mới được thêm trong lần thay đổi gần thời điểm lỗi, có hiệu lực trên App VM và được ghi log `DENIED`.

Với bằng chứng đó, đây là **chặn nhầm lưu lượng hợp lệ**. Chủ hệ thống và người quản trị mạng có thể đề nghị loại bỏ hoặc thu hẹp rule gây lỗi, đồng thời giữ nguyên các deny bảo vệ Data. Cách sửa phụ thuộc thứ tự policy thực tế: tạo một allow rule thấp hơn trong thứ tự đánh giá có thể **không có tác dụng** nếu deny có ưu tiên cao hơn đang quyết định kết nối.

### 8.2. Bảng kiểm thử sau khi khắc phục

| Trường hợp | Kỳ vọng |
| --- | --- |
| Web VM → App VM TCP 8080 | Thành công, `/health` phản hồi. |
| Web VM → Data TCP 5432 | Tiếp tục bị chặn theo thiết kế. |
| App VM → Data TCP 5432 | Hoạt động nếu đó là luồng nghiệp vụ được phê duyệt và database đã sẵn sàng. |
| VM thử nghiệm ngoài Web subnet → App TCP 8080 | Tiếp tục bị chặn. |
| Internet → App IP nội bộ | Không có endpoint công khai trực tiếp; kiểm tra thêm mạng hybrid/peering nếu tồn tại. |

Sau thử nghiệm, nhóm xác nhận lỗi 502 đã hết, log `DENIED` của rule gây lỗi không còn xuất hiện cho **kết nối hợp lệ mới**, còn lưu lượng trái phép vẫn bị từ chối. Kết quả được lưu trong incident cùng nguyên nhân gốc và cách ngăn thay đổi lặp lại.

**Bài học thiết kế:** Firewall Rules Logging giúp xác nhận *rule nào* đã chặn một đường TCP, nhưng quyết định có nên cho phép hay không vẫn phải dựa trên kiến trúc, phân loại dữ liệu, IAM và người chịu trách nhiệm hệ thống.

## 9. Giám sát dài hạn, log-based metrics và cảnh báo

Trong hệ thống lớn, đọc thủ công từng log sẽ không đủ. Có thể tạo **logs-based metrics** từ các bản ghi phù hợp, sau đó dùng Cloud Monitoring để trực quan hóa và cảnh báo theo điều kiện.

### 9.1. Chọn tín hiệu có ý nghĩa

| Tín hiệu | Lý do theo dõi | Rủi ro diễn giải |
| --- | --- | --- |
| DENIED vào cổng quản trị từ nguồn ngoài danh sách | Có thể phát hiện quét cổng hoặc cố truy cập trái phép. | Đếm nhiều không đồng nghĩa bị xâm nhập thành công. |
| DENIED từ App tier tới một dependency thiết yếu | Có thể cho biết deploy hoặc thay đổi IP/firewall gây gián đoạn. | Cần đối chiếu SLO, trace và log ứng dụng. |
| DENIED tăng đột ngột sau thay đổi policy | Gợi ý rủi ro chặn nhầm traffic hợp lệ. | Lượng yêu cầu tăng thật cũng có thể làm tăng log. |
| ALLOWED vào cổng nhạy cảm từ nguồn bất thường | Phát hiện các luồng đang **được cho phép** nhưng cần review. | Rule cho phép không có nghĩa truy cập ứng dụng thành công. |
| Số lượng rule có logging bị tắt | Phát hiện mất khả năng quan sát trên những đường được chỉ định giám sát. | Đây là dữ liệu **cấu hình**, cần kết hợp audit/inventory, không phải chỉ log traffic. |

Một logs-based counter metric có thể dùng bộ lọc:

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
jsonPayload.connection.dest_port=22
~~~

Metric này đo **số bản ghi khớp bộ lọc** mà pipeline Logging xử lý theo chính sách và thời điểm, không phải số packet chính xác hay số người dùng duy nhất. Cảnh báo cần có ngưỡng phù hợp với baseline, khoảng thời gian và quy trình phản ứng khi false positive.

### 9.2. Thiết kế một cảnh báo có thể hành động

Một cảnh báo hữu ích cần nêu:

1. **Điều kiện:** ví dụ số DENIED vào cổng quản trị tăng vượt ngưỡng được xác định từ tải nền.
2. **Phạm vi:** project, VPC, subnet, ứng dụng hoặc nhóm đích.
3. **Nguồn bằng chứng:** link tới Logs Explorer với bộ lọc thích hợp và hướng dẫn xem log chi tiết.
4. **Người nhận:** đội mạng, bảo mật hoặc on-call chịu trách nhiệm luồng kết nối.
5. **Hành động đầu tiên:** xác nhận nguồn/đích và xem đây là quét trái phép hay lưu lượng hợp lệ bị chặn.
6. **Điều kiện đóng:** xử lý nguyên nhân và xác minh lại positive/negative tests, không chỉ tắt alert.

Nếu một lượng truy cập bị chặn liên tục nhưng đã được xác định là noise được quản lý, có thể điều chỉnh chính sách quan sát để giảm mệt mỏi cảnh báo. **Không xóa rule chặn hoặc ngừng toàn bộ logging chỉ để số cảnh báo nhỏ đi.**

### 9.3. Log retention, log buckets và phân quyền

Firewall log có thể chứa địa chỉ IP, tên VM, subnet và những thông tin vận hành có thể được xem là dữ liệu nhạy cảm trong bối cảnh cụ thể. Khi thiết kế log:

- **Chỉ cấp quyền đọc cho người cần thiết**, tách nhóm vận hành mạng, nhóm giám sát bảo mật và tài khoản quản trị Logging.
- **Chọn retention theo nhu cầu:** xử lý sự cố, điều tra bảo mật, yêu cầu lưu trữ và chính sách dữ liệu. Không mặc định giữ log vô hạn.
- **Xem xét vị trí lưu dữ liệu log:** nhất là khi tổ chức có ràng buộc residency hoặc dùng log bucket tập trung.
- **Giảm dữ liệu không cần thiết:** cân nhắc logging metadata được hỗ trợ, log routing hoặc exclusion phù hợp. Không lọc bỏ bằng chứng DENIED quan trọng một cách vô tình.
- **Theo dõi chi phí:** chi phí ingestion, lưu trữ, truy vấn/định tuyến/đích xuất tùy sản phẩm và cấu hình; xác minh bảng giá hiện hành.
- **Giữ bằng chứng thay đổi:** audit logs của hoạt động sửa firewall, thay log routing, chỉnh retention và cấp quyền đọc log.

Trong một tổ chức nhiều project, có thể định tuyến log về nơi tập trung hoặc SIEM theo cơ chế được hỗ trợ. Cần bảo đảm **log sink, IAM của đích, quota, retention, đường truyền và phạm vi tổ chức** được cấu hình đúng. Khi log bị loại qua exclusion, việc điều tra lại quá khứ có thể không còn đủ dữ liệu.

## 10. Bài thực hành có kiểm soát: đánh giá một trường hợp DENIED

Giả định bạn đang phụ trách mạng cho một ứng dụng ba tầng và nhận được yêu cầu từ nhóm phát triển:

> “Từ VM Web, chúng tôi không gọi được API nội bộ TCP 8080. Hãy mở tất cả traffic trong VPC để thử xem có hết lỗi không.”

Bạn được cung cấp dữ liệu mẫu:

| Dữ kiện | Giá trị minh họa |
| --- | --- |
| VPC | `training-prod-vpc` |
| Web subnet | `10.50.10.0/24` |
| App subnet | `10.50.20.0/24` |
| Data subnet | `10.50.30.0/24` |
| IP Web VM | `10.50.10.11` |
| IP App VM | `10.50.20.11` |
| App port | TCP 8080 |
| Data port | TCP 5432 |
| Yêu cầu bảo mật | Web không được kết nối trực tiếp Data |

### 10.1. Nhiệm vụ

1. Viết bộ lọc Logs Explorer tìm `DENIED` từ `10.50.10.11` đến `10.50.20.11:8080` trong khoảng thời gian lỗi.
2. Nêu những trường bạn cần đọc để xác định rule, hướng lưu lượng, priority và IP nguồn/đích.
3. Nếu không thấy log, liệt kê ít nhất **bốn nguyên nhân** trước khi yêu cầu thay đổi policy.
4. Giả sử đã có log `DENIED` do explicit deny trên App VM: đưa ra thay đổi **nhỏ nhất** để Web gọi API hợp lệ, không mở Web → Data.
5. Viết hai ca kiểm thử **phải thành công** và **phải thất bại** sau khi sửa.
6. Giải thích vai trò của VPC Flow Logs và Cloud Audit Logs trong trường hợp này.
7. Đề xuất một log-based metric phát hiện số kết nối App → Data bị từ chối bất thường sau phát hành.

### 10.2. Gợi ý lời giải

**Bộ lọc cho nhiệm vụ 1:**

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
jsonPayload.connection.src_ip="10.50.10.11"
jsonPayload.connection.dest_ip="10.50.20.11"
jsonPayload.connection.dest_port=8080
~~~

Với nhiệm vụ 2, cần đọc `timestamp`, `disposition`, `connection` và `rule_details` (nếu có), sau đó đối chiếu policy hiệu lực. Với nhiệm vụ 3, xem implied deny, logging chưa bật, rule/policy khác quyết định trước, sai project/thời gian/log scope hoặc lỗi route/ứng dụng.

Với nhiệm vụ 4, không thể chỉ nói “thêm allow rule” mà bỏ qua **thứ tự ưu tiên**: nếu deny có mức ưu tiên cao hơn thì allow mới không được áp dụng. Cần điều chỉnh policy theo quy trình được phê duyệt để cho phép **chỉ** đúng Web → App TCP 8080, và giữ Data được bảo vệ. Với nhiệm vụ 5, xác nhận Web → App thành công và Web → Data tiếp tục thất bại, bổ sung App → Data thành công nếu đó là đường hợp lệ.

Với nhiệm vụ 6, VPC Flow Logs giúp đánh giá xu hướng lưu lượng theo khả năng thu thập, Cloud Audit Logs giúp điều tra ai đã sửa rule; Firewall Rules Logging nêu quyết định của rule đối với kết nối phù hợp. Với nhiệm vụ 7, thiết lập metric từ `DENIED` đến IP/port của Data và cảnh báo khi vượt baseline sau triển khai.

### 10.3. Câu hỏi tự kiểm tra

**1. Không tìm thấy firewall log cho một kết nối timeout có chứng minh được traffic được ALLOW không?**  
Không. Có thể bị implied deny, không bật logging, bị policy khác quyết định, lọc sai log hoặc lỗi không nằm ở firewall.

**2. Có thể lấy số bản ghi DENIED để đếm chính xác số packet hoặc số HTTP request bị chặn không?**  
Không. Firewall Rules Logging là nhật ký kết nối theo cơ chế thu thập của sản phẩm, không phải bộ đếm packet hay HTTP request.

**3. Tại sao một rule ALLOW còn bật logging cũng đáng được quan tâm?**  
Vì việc phát hiện kết nối **được phép** từ nguồn không mong đợi có thể giúp thấy rule mở rộng hơn nhu cầu, dù chưa có dấu hiệu DENIED.

**4. Thay đổi firewall có cần chạy lại ca kiểm thử bị chặn không?**  
Có. Chỉ kiểm tra ứng dụng đã hoạt động trở lại có thể bỏ sót việc vô tình mở quyền cho mạng khác.

**5. Tại sao cần kết hợp Cloud Audit Logs với firewall log khi điều tra đợt lỗi mới?**  
Audit logs có thể giúp xác định thay đổi cấu hình và người/danh tính thực hiện, trong khi firewall log giúp chỉ ra quyết định mạng được quan sát.

## Tài liệu Google Cloud tham khảo

- **Firewall Rules Logging overview:** https://cloud.google.com/firewall/docs/firewall-rules-logging — cách ghi log, loại traffic và metadata.
- **Use Firewall Rules Logging:** https://cloud.google.com/firewall/docs/using-firewall-rules-logging — bật/tắt logging và các phương pháp xem log.
- **VPC firewall rules:** https://cloud.google.com/firewall/docs/firewalls — thứ tự đánh giá, hướng ingress/egress và implied rules.
- **Cloud Logging query language:** https://cloud.google.com/logging/docs/view/logging-query-language — bộ lọc Logs Explorer.
- **VPC Flow Logs:** https://cloud.google.com/vpc/docs/flow-logs — dữ liệu luồng mạng, giới hạn thu thập và quan sát.
- **Cloud Audit Logs:** https://cloud.google.com/logging/docs/audit — điều tra những thao tác quản trị tài nguyên.
- **Connectivity Tests:** https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview — phân tích đường đi và cấu hình kết nối.
- **Cloud Logging pricing:** https://cloud.google.com/stackdriver/pricing — kiểm tra chi phí Logging, lưu trữ và các khả năng liên quan.

Tài liệu kỹ thuật, giao diện Cloud Console, loại policy được hỗ trợ và chi phí có thể thay đổi. Khi áp dụng trong một tổ chức thực tế, hãy xác minh permission, logging configuration, phạm vi dữ liệu và quy trình phê duyệt. Một đợt rà soát thành công cần giải thích được **vì sao kết nối bị chặn**, chứng minh hành động khắc phục đúng phạm vi và **không làm mất những deny bảo vệ hệ thống**.
