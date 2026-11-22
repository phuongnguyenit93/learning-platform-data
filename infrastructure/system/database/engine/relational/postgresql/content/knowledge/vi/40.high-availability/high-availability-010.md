# Diễn tập lỗi mạng, mất máy chủ và mất vùng trong PostgreSQL HA

## 1. Vì sao phải diễn tập lỗi?

Một hệ thống PostgreSQL có standby, load balancer và backup chưa chắc đã có khả năng khôi phục dịch vụ khi production gặp sự cố. Các thành phần chỉ tạo nên khả năng sẵn sàng cao khi chúng phối hợp đúng lúc một failure xảy ra: phát hiện lỗi, xác định primary còn hợp lệ, ngăn hai node cùng ghi, promote standby phù hợp, chuyển traffic, khôi phục kết nối ứng dụng và xác minh dữ liệu.

Diễn tập lỗi (failover drill hoặc game day) là hoạt động chủ động tạo một failure có phạm vi kiểm soát để đo phản ứng thực tế của hệ thống. Mục tiêu là chứng minh runbook, automation, monitoring và con người có thể đưa dịch vụ trở lại trạng thái phục vụ được trong các giới hạn đã cam kết.

Ba nhóm tình huống trọng tâm:

- **Lỗi mạng:** primary và standby không liên lạc được; client không đến được primary; đường truyền giữa các vùng bị gián đoạn; packet loss hoặc latency khiến health checks không ổn định.
- **Mất máy chủ:** PostgreSQL process crash, host mất điện, VM/node bị terminate, storage không truy cập được hoặc server bị cô lập.
- **Mất vùng:** một Availability Zone hoặc region không còn phục vụ được, bao gồm database, network, control plane hoặc các dependencies cần để chạy ứng dụng.

Một drill tốt không chỉ đo thời gian PostgreSQL promote. Nó đo thời gian từ khi lỗi bắt đầu đến khi người dùng có thể thực hiện giao dịch hợp lệ trên endpoint mới, đồng thời xác định dữ liệu nào có thể bị mất và chứng minh không xảy ra split brain.

```text
                 FAILURE INJECTION
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
       Network       Server         Region
       partition     unavailable    unavailable
          |             |             |
          +-------------+-------------+
                        |
                        v
                Detect and classify
                        |
                        v
                 Fence old primary
                        |
                        v
                Select safe standby
                        |
                        v
                    Promote
                        |
                        v
             Route clients and reconnect
                        |
                        v
               Validate data/service
                        |
                        v
             Measure RPO, RTO, evidence
```

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt high availability (HA), disaster recovery (DR), failover và switchover.
2. Xác định failure domains và các đường phụ thuộc của PostgreSQL service.
3. Thiết lập RPO và RTO cho từng failure scenario.
4. Giải thích sự khác nhau giữa synchronous và asynchronous replication khi failover.
5. Hiểu các mức synchronous commit và tác động đến latency/durability.
6. Phân biệt network partition với server crash.
7. Nhận diện split brain và vai trò của fencing.
8. Hiểu quorum, leader lease và distributed configuration store trong HA automation.
9. Diễn tập mất kết nối client, replication link và control plane.
10. Diễn tập PostgreSQL process crash và host failure.
11. Thiết kế drill mất Availability Zone hoặc region.
12. Theo dõi replication state, WAL positions và replay lag.
13. Đo detection time, fencing time, promotion time và application recovery time.
14. Kiểm tra DNS, load balancer, connection pools và retry behavior.
15. Xác minh dữ liệu sau promotion bằng transaction markers.
16. Phân biệt planned switchover với unplanned failover.
17. Thực hiện failback và đưa old primary trở lại thành standby an toàn.
18. Bảo vệ backup, WAL archive, secrets và dependencies ở region dự phòng.
19. Thiết kế failure matrix, rollback criteria và evidence collection.
20. Xây lịch game day và cải thiện runbook dựa trên kết quả.

## 3. HA, DR, failover và switchover

### 3.1. High availability

HA giảm thời gian gián đoạn khi một thành phần lỗi. Với PostgreSQL, kiến trúc thường có một primary nhận writes, một hoặc nhiều standby nhận WAL, cơ chế phát hiện lỗi, cơ chế chọn leader và đường chuyển traffic.

HA chủ yếu xử lý các failure thường gặp trong cùng một hệ thống vận hành: process crash, node failure, storage/network interruption hoặc bảo trì có kế hoạch.

### 3.2. Disaster recovery

DR chuẩn bị khôi phục dịch vụ sau một sự cố lớn vượt quá phạm vi HA thông thường, chẳng hạn mất toàn bộ region, tài khoản cloud bị ảnh hưởng, lỗi cấu hình diện rộng hoặc hỏng dữ liệu được replicate sang standby.

DR thường cần thêm:

- Bản sao dữ liệu ở failure domain khác.
- Base backups và WAL archives độc lập.
- Hạ tầng có thể dựng lại ở region dự phòng.
- DNS/network/security rules và credentials.
- Runbook quyết định kích hoạt DR.
- Quy trình xác minh dữ liệu và chuyển traffic.

Một standby ở cùng region không phải DR cho tình huống mất region.

### 3.3. Failover

Failover là chuyển dịch vụ từ primary lỗi hoặc không còn được xem là an toàn sang một standby được chọn để trở thành primary mới. Failover thường xảy ra ngoài kế hoạch và có thể cần chấp nhận một mức mất dữ liệu tùy replication mode.

### 3.4. Switchover

Switchover là chuyển vai trò có kế hoạch. Operator có thể dừng writes, chờ standby bắt kịp, kiểm tra LSN và chuyển primary theo thứ tự có kiểm soát. Switchover giúp kiểm thử đường chuyển vai trò với ít rủi ro mất dữ liệu hơn.

### 3.5. Không dùng switchover thành bằng chứng failover đã sẵn sàng

Switchover có thể thành công trong khi failover tự động vẫn lỗi vì DCS mất quorum, fencing không hoạt động, DNS cache cũ hoặc standby không đủ WAL. Cần diễn tập cả planned switchover và failure thật trong môi trường test.

## 4. Xác định failure domains

### 4.1. Failure domain là gì?

Failure domain là phạm vi các thành phần có thể cùng bị ảnh hưởng bởi một sự cố. Ví dụ:

- Process: PostgreSQL service hoặc một worker.
- Host: VM, bare-metal node hoặc Kubernetes worker.
- Rack/zone: power, network, storage hoặc availability zone.
- Region: network, control plane, database nodes và các dịch vụ phụ thuộc.
- Account/project: IAM, quota, billing, credentials hoặc thao tác quản trị.
- Organization: lỗi cấu hình, deploy hoặc credential có quyền trên nhiều vùng.

### 4.2. Không chỉ đặt database ở nhiều máy

Nếu primary và standby ở hai VM khác nhau nhưng cùng một storage system, subnet, power domain hoặc region, một sự cố chung vẫn có thể làm cả hai mất khả năng phục vụ.

### 4.3. Vẽ cả đường dữ liệu và đường điều khiển

Một sơ đồ HA cần thể hiện:

- Primary và standby PostgreSQL.
- Replication network.
- DCS/quorum/witness nếu dùng HA manager.
- Load balancer hoặc proxy.
- DNS và service discovery.
- Application instances và connection pools.
- Backup/WAL archive storage.
- Monitoring/alerting.
- Secrets, KMS và control plane.
- Các external dependencies mà ứng dụng cần.

### 4.4. Failure domain phải phản ánh kiến trúc thực tế

Nếu ứng dụng chạy ở region A nhưng database DR ở region B, việc mất A có thể khiến database còn sống nhưng ứng dụng, DNS, credentials hoặc network không thể chạy ở B. Diễn tập phải bao gồm cả dependencies.

## 5. RPO và RTO trong một failure drill

### 5.1. RPO (Recovery Point Objective)

RPO là lượng dữ liệu tối đa tổ chức chấp nhận mất, thường đo bằng khoảng thời gian giữa giao dịch được xác nhận gần nhất trước sự cố và trạng thái dữ liệu được phục hồi sau failover.

Ví dụ:

- RPO 0 theo mục tiêu: không chấp nhận mất transaction đã được xác nhận.
- RPO 30 giây: có thể chấp nhận mất tối đa khoảng 30 giây writes trong kịch bản được xác định.
- RPO 5 phút: có thể chấp nhận khoảng dữ liệu chưa replicate trong cửa sổ đó.

RPO cần đo bằng transaction thực tế và commit acknowledgements, không chỉ bằng một metric lag trung bình.

### 5.2. RTO (Recovery Time Objective)

RTO là thời gian tối đa chấp nhận từ khi dịch vụ gián đoạn đến khi dịch vụ hoạt động trở lại theo tiêu chí business.

Không chỉ tính thời gian PostgreSQL promote. RTO nên bao gồm:

1. Detection.
2. Quyết định failover.
3. Fencing primary cũ.
4. Promotion.
5. Cập nhật routing.
6. Application reconnect.
7. Smoke tests và data validation.
8. Mở traffic đầy đủ.

### 5.3. Ví dụ phân rã RTO

| Giai đoạn | Thời gian mục tiêu minh họa |
| --- | ---: |
| Phát hiện và phân loại | 20 giây |
| Fence primary cũ | 15 giây |
| Promote standby | 20 giây |
| Chuyển endpoint/route | 30 giây |
| Ứng dụng reconnect | 20 giây |
| Smoke test và mở traffic | 25 giây |
| Tổng | 130 giây |

Đây chỉ là ví dụ lập kế hoạch. Đo số liệu thực tế trong drill và tính cả thời gian chờ timeout, DNS cache, connection pool và human approval.

### 5.4. RPO và RTO khác nhau

Một hệ thống có thể phục hồi rất nhanh nhưng mất một số transaction chưa replicate. Ngược lại, hệ thống có thể giữ đủ dữ liệu nhưng mất nhiều thời gian để dựng endpoint mới. Đo riêng cả hai.

### 5.5. Đặt mục tiêu theo từng scenario

Mất một process trong cùng zone có thể có RTO/RPO khác với mất region. Không áp một con số duy nhất cho tất cả failure domains.

## 6. Synchronous và asynchronous replication ảnh hưởng RPO

### 6.1. Asynchronous replication

Với asynchronous replication, primary có thể xác nhận commit trước khi standby nhận hoặc flush WAL tương ứng. Khi primary mất đột ngột, standby có thể thiếu một số transactions đã được primary xác nhận.

Ưu điểm:

- Độ trễ commit thấp hơn.
- Không phụ thuộc standby phải phản hồi cho mỗi commit.
- Thích hợp cho replica ở xa hoặc cross-region khi latency cao.

Đánh đổi:

- Có thể mất dữ liệu đã acknowledge nếu promote standby chưa nhận đủ WAL.
- RPO phụ thuộc replication lag tại thời điểm failure và standby được chọn.

### 6.2. Synchronous replication

Với synchronous replication, commit trên primary chờ acknowledgement từ standby được chọn theo cấu hình. Điều này giảm nguy cơ mất các transactions đã được xác nhận, nhưng tăng commit latency và có thể làm writes chờ khi standby/network không sẵn sàng.

### 6.3. synchronous_commit

Một số mức thường gặp:

| Giá trị | Hành vi khái quát |
| --- | --- |
| `off` | Không chờ local WAL flush trước khi báo commit thành công; có thể mất transaction gần đây khi crash |
| `local` | Chờ local WAL flush, không chờ synchronous standby |
| `remote_write` | Chờ synchronous standby ghi WAL tới hệ điều hành, chưa nhất thiết durable trên storage |
| `on` | Chờ synchronous standby flush WAL bền vững theo cơ chế PostgreSQL |
| `remote_apply` | Chờ synchronous standby replay transaction để transaction có thể nhìn thấy ở đó |

Ý nghĩa chính xác phụ thuộc cấu hình synchronous standbys và version. `remote_apply` thường tăng latency hơn vì chờ replay, còn `on` tập trung vào remote WAL flush.

### 6.4. synchronous_standby_names

Setting này xác định standby nào được xem là synchronous và có thể dùng `FIRST` hoặc `ANY` với số lượng standby tương ứng. Ví dụ minh họa:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

Với `FIRST`, PostgreSQL chọn standby theo thứ tự ưu tiên. Với `ANY`, có thể yêu cầu acknowledgement từ một số lượng bất kỳ trong danh sách phù hợp. Kiểm tra syntax và semantics của PostgreSQL major version triển khai.

### 6.5. Synchronous replication không tự tạo HA manager

Synchronous replication quy định commit acknowledgement. Nó không tự phát hiện node chết, không fence primary cũ, không chọn node mới, không cập nhật DNS và không bảo đảm control plane có quorum.

### 6.6. RPO 0 có điều kiện

Mục tiêu zero data loss cho acknowledged commits chỉ đạt được khi:

- Transactions thực sự dùng synchronous commit phù hợp.
- Standby được xác nhận là synchronous theo cấu hình tại thời điểm commit.
- Promotion chọn đúng standby đã nhận/flush WAL cần thiết.
- Không có writes được xác nhận qua chế độ async override.
- Fencing ngăn primary cũ tiếp tục nhận writes.
- Storage và failure assumptions của hệ thống đúng.

Một cấu hình ghi `synchronous_commit = on` ở file không đủ để tuyên bố RPO 0 cho mọi giao dịch và mọi failure scenario.

### 6.7. Cross-region synchronous replication

Đặt synchronous standby ở region xa có thể làm commit latency tăng theo round-trip time và ảnh hưởng availability khi đường liên vùng mất. Nhiều kiến trúc chọn synchronous trong một region/zone gần và asynchronous DR ở region khác. Lựa chọn phải dựa trên RPO, latency budget và failure model.

## 7. Network failure: phải phân biệt đường nào bị đứt

“Network down” có nhiều nghĩa. Các kết quả khác nhau tùy kết nối nào mất.

### 7.1. Client không đến được primary

Primary và standby vẫn khỏe, replication vẫn chạy, nhưng application không kết nối được primary. Nếu health check chỉ dựa vào lỗi từ client, hệ thống có thể failover không cần thiết.

Kiểm tra:

- Load balancer health checks.
- Routing/security groups/firewall.
- DNS resolution.
- Client subnet và application egress.
- TLS/proxy path.
- Kết nối trực tiếp từ một probe độc lập.

### 7.2. Primary không đến được standby

Primary có thể tiếp tục nhận writes trong khi standby không nhận WAL. Với async replication, lag tăng và RPO xấu dần. Với synchronous replication, commits cần synchronous acknowledgement có thể bị chặn hoặc chờ timeout/đổi trạng thái theo cấu hình.

Không tự động promote standby chỉ vì replication link mất: primary có thể vẫn đang hoạt động và nhận writes. Promotion khi primary cũ chưa được fence có thể tạo split brain.

### 7.3. Standby không đến được primary

Standby có thể ngừng nhận WAL và replay lag tăng. Một hệ thống HA manager cần xác định standby có thực sự đủ điều kiện promotion hay không, dựa trên topology, leader lease, quorum và data freshness.

### 7.4. Node không đến được DCS/quorum

Nếu HA manager dùng etcd, Consul hoặc một distributed configuration store, mất kết nối tới DCS có thể khiến node không biết mình còn giữ quyền leader hay không.

DCS quorum và PostgreSQL replication là hai lớp khác nhau. Một node có thể còn PostgreSQL process nhưng mất quyền điều phối leader. Cần chính sách fail-closed và fencing phù hợp.

### 7.5. Network partition bất đối xứng

Primary có thể liên lạc được với một số nodes nhưng không với các nodes khác. Health check từ một vị trí duy nhất có thể đưa ra kết luận sai. Diễn tập từ nhiều vantage points và kiểm tra hai chiều.

### 7.6. Latency và packet loss

Network không cần mất hoàn toàn mới gây lỗi. Latency cao, jitter và packet loss có thể khiến replication timeout, health check flapping, connection pool retries và synchronous commits chậm. Drill cần có cả fault nhẹ và fault nặng.

## 8. Split brain và fencing

### 8.1. Split brain là gì?

Split brain xảy ra khi hai node cùng tin rằng mình là primary và cùng nhận writes. Điều này có thể tạo hai lịch sử WAL/data độc lập, gây divergence và làm việc hợp nhất dữ liệu rất khó hoặc không thể tự động.

### 8.2. Vì sao network partition nguy hiểm?

Primary cũ có thể chỉ bị cô lập khỏi HA manager hoặc standby, nhưng vẫn được ứng dụng truy cập từ một mạng khác. Nếu standby được promote đồng thời, hai primary có thể cùng phục vụ writes.

### 8.3. Fencing là gì?

Fencing là hành động bảo đảm node cũ không thể tiếp tục ghi hoặc phục vụ với vai trò primary trước khi node mới được promote.

Các cách fencing tùy môi trường:

- Power fencing/STONITH: tắt node cũ qua out-of-band management hoặc cloud API.
- Network fencing: chặn traffic client và replication tới node cũ.
- Storage fencing: thu hồi quyền truy cập storage dùng chung nếu kiến trúc có shared storage.
- Orchestrator fencing: dùng lease/leader state cùng cơ chế ngăn node mất quyền tiếp tục phục vụ.

Fencing phải được chứng minh có hiệu lực. Chỉ đổi DNS không phải fencing vì client có thể còn kết nối cũ hoặc truy cập trực tiếp IP.

### 8.4. Promotion chỉ sau khi xác định primary cũ

Runbook cần có điều kiện rõ: node cũ đã tắt, đã bị cô lập khỏi mọi write path, hoặc HA manager có cơ chế fencing đáng tin cậy. Nếu không thể chứng minh, không promote tự động trong một topology có nguy cơ split brain.

### 8.5. Không dùng ping làm bằng chứng node đã chết

Ping thất bại có thể do ICMP bị chặn, route hỏng hoặc partition. PostgreSQL process vẫn có thể hoạt động. Cần nhiều health signals và fencing.

### 8.6. Kiểm tra sau fencing

Thử từ các mạng/application paths xem primary cũ còn nhận kết nối không. Kiểm tra cloud instance state, service state, routing và DCS lease. Ghi lại evidence trước khi promotion.

## 9. Quorum và HA orchestration

### 9.1. Quorum

Quorum là số lượng thành viên tối thiểu cần thiết để một distributed system ra quyết định nhất quán. Với DCS ba nodes, nhiều triển khai cần đa số nodes để tiếp tục ghi state. Nếu mất quorum, hệ thống có thể từ chối thay đổi leader để tránh hai phía cùng điều khiển.

### 9.2. Witness

Một witness có thể giúp phân xử trong một số kiến trúc, nhưng phải là thành viên có semantics quorum thực sự. Một VM nhỏ chỉ chạy health check không tự động là witness an toàn.

### 9.3. PostgreSQL không tự cung cấp toàn bộ failover orchestration

PostgreSQL có streaming replication, synchronous replication và các hàm promotion. Tự động phát hiện primary failure, leader election, fencing, routing và lifecycle thường do công cụ bên ngoài quản lý, ví dụ Patroni với DCS, repmgr hoặc nền tảng managed database.

Không trộn lẫn API/command của các công cụ. Thực hiện drill theo đúng tool và version đang triển khai.

### 9.4. Leader lease

Một số HA managers dùng lease/lock có thời hạn để xác định leader. Node mất kết nối DCS có thể mất quyền leader khi lease hết hạn. Cần kiểm tra timing, clock assumptions, renewal và fencing behavior.

### 9.5. Quorum không bảo đảm standby mới nhất

Quorum trả lời ai được quyền điều phối, không tự đảm bảo node được chọn có đủ WAL mới nhất. Cần có policy chọn candidate và kiểm tra data loss risk.

## 10. Mất PostgreSQL process và mất máy chủ

### 10.1. Process crash

PostgreSQL process có thể crash do bug, OOM kill, invalid extension, resource exhaustion hoặc lỗi hệ điều hành. Host vẫn hoạt động và có thể truy cập qua SSH/management plane.

Drill cần kiểm tra:

- Process supervisor có restart process không.
- HA manager phân biệt restart với node failure thế nào.
- WAL crash recovery có hoàn tất không.
- Health check chỉ báo healthy sau khi database nhận được kết nối/queries cần thiết.
- Failover có bị kích hoạt quá sớm khi process chỉ restart ngắn không.

### 10.2. Host/VM mất hoàn toàn

Node có thể mất nguồn, hypervisor lỗi, VM bị terminate hoặc host không thể truy cập. Standby cần được đánh giá để promotion. Primary cũ phải được fence trước khi node khác nhận writes.

### 10.3. Storage failure

Host có thể sống nhưng volume chứa PGDATA hoặc WAL bị detach, read-only, latency cao hoặc lỗi I/O. Một health check chỉ kiểm tra TCP port có thể bỏ sót storage failure.

Không cố restart liên tục trên volume đang lỗi. Theo runbook storage, xác định khả năng phục hồi, fencing và backup/replica source.

### 10.4. Disk full

WAL, logs hoặc data volume đầy có thể khiến writes thất bại hoặc server không hoạt động bình thường. Diễn tập alert sớm và response capacity. Không xóa thủ công files trong PGDATA hoặc pg_wal.

### 10.5. Restart không đồng nghĩa failover

Nếu process restart nhanh và crash recovery hoàn tất, có thể không cần promote standby. Nhưng nếu restart loop kéo dài hoặc host không an toàn, HA policy có thể cần failover. Ngưỡng quyết định phải rõ và được test.

## 11. Mất Availability Zone hoặc region

### 11.1. Mất zone

Một zone failure có thể làm mất primary, một số standbys, network path hoặc DCS members. Thiết kế nên có database candidate và quorum còn lại ở các zones độc lập theo failure model.

### 11.2. Mất region

Region outage có thể đồng thời ảnh hưởng:

- Primary và các standby cùng region.
- Load balancers và private DNS.
- DCS/control plane.
- Application services.
- Backup credentials hoặc KMS access.
- Monitoring/alerting endpoints.
- NAT, routing và service dependencies.

### 11.3. Cross-region standby

Một standby ở region khác có thể trở thành DR candidate. Nếu asynchronous, có thể mất WAL chưa được nhận. Đo RPO theo replay position và transactions đã commit trên primary.

### 11.4. Cross-region WAL archive

WAL archive off-region giúp dựng lại cluster khi standby không còn khả dụng. PITR cần base backup và WAL liên tục; chỉ có một snapshot cũ sẽ tạo recovery point cũ hơn.

### 11.5. Region mới cần đủ hạ tầng

Trước khi tuyên bố DR sẵn sàng, xác minh:

- Compute capacity và PostgreSQL version.
- Storage throughput/capacity.
- Network, subnet, firewall và private endpoints.
- Secrets, certificates và KMS keys.
- DNS/traffic routing.
- Application images/configuration.
- Observability và alert delivery.
- External integrations và data dependencies.
- Quyền truy cập operator trong tình huống region chính mất.

### 11.6. DR activation là quyết định business

Runbook cần xác định ai được quyền tuyên bố region chính không thể phục hồi, khi nào kích hoạt DR, cách xử lý dữ liệu chưa replicate và điều kiện quay lại region cũ.

### 11.7. Không để hai region cùng nhận writes

Sau khi DR region được promote và phục vụ writes, region cũ khi trở lại phải được fence và xử lý như một node có lịch sử cũ. Không mở traffic đồng thời vào cả hai primary nếu không có kiến trúc multi-writer được thiết kế riêng.

## 12. Thiết kế failure matrix

Trước game day, lập ma trận scenario, tín hiệu phát hiện, hành vi kỳ vọng và tiêu chí thành công.

| Scenario | Failure được tạo | Hành vi mong đợi | Rủi ro cần kiểm tra |
| --- | --- | --- | --- |
| Client path down | App không tới primary | Phân biệt routing issue với DB failure | Failover không cần thiết |
| Replication link down | Primary không gửi WAL tới standby | Alert lag, giữ primary hoặc failover theo policy | Data loss nếu promote standby cũ |
| Primary isolated from DCS | Node mất quorum/lease | Fencing và leader decision an toàn | Split brain |
| Standby lost | Replica process/host dừng | Primary tiếp tục theo policy, alert redundancy loss | Không còn candidate |
| Primary process crash | PostgreSQL dừng | Restart hoặc failover theo threshold | Flapping |
| Primary host lost | Node không truy cập được | Fence và promote candidate | RPO |
| Storage failure | Data/WAL volume lỗi | Isolate, restore/replica recovery | Corruption hoặc repeated restart |
| Zone outage | Nhiều nodes/path cùng mất | Chọn candidate ở zone còn sống | Quorum placement |
| Region outage | Toàn bộ region không khả dụng | Kích hoạt DR region | WAL lag, DNS, dependencies |
| DNS stale | Client dùng endpoint cũ | Route update và reconnect đúng | Cache/pool stale |
| DCS quorum loss | Không ra được leader decision | Fail closed theo policy | Unsafe promotion |
| Slow network | Latency/loss tăng | Alert và behavior theo timeout | False failure detection |

## 13. Chuẩn bị một game day an toàn

### 13.1. Xác định mục tiêu cụ thể

Ví dụ: chứng minh primary host failure có thể chuyển writes sang standby trong 120 giây và không mất các transactions đã được xác nhận theo RPO cam kết.

Không bắt đầu bằng mục tiêu mơ hồ như “thử xem HA có chạy không”.

### 13.2. Chọn môi trường

Ưu tiên staging có topology gần production: cùng PostgreSQL major version, HA manager, DCS, routing, connection pools và replication settings. Nếu thử ở production, cần change window, owner, rollback conditions và blast radius được phê duyệt theo quy trình tổ chức.

### 13.3. Ghi baseline

Trước drill, lưu:

- Primary identity và standby list.
- Timeline và LSN positions.
- Replication state/lag.
- Synchronous standby state.
- DCS quorum/leader.
- Disk/WAL/storage health.
- Current application endpoint.
- Active connection count.
- Error rate và transaction throughput.
- Transaction marker IDs đã commit.

### 13.4. Xác định stop conditions

Dừng drill nếu:

- Có dấu hiệu hai primary cùng nhận writes.
- Fencing không chứng minh được.
- Quorum không rõ hoặc DCS state bất thường.
- RPO vượt ngưỡng chấp nhận.
- Storage/backup bị ảnh hưởng ngoài phạm vi.
- Không thể xác định node nào là primary.
- Application error rate hoặc business impact vượt giới hạn.
- Rollback procedure không còn khả dụng.

### 13.5. Có người giữ vai trò độc lập

Một người thực hiện injection, một người quan sát database/HA manager, một người theo dõi application và một người có quyền dừng drill. Với nhóm nhỏ có thể kiêm nhiệm, nhưng người ra quyết định stop phải được xác định trước.

### 13.6. Ghi lại timestamp thống nhất

Đồng bộ clocks bằng NTP/chrony hoặc nguồn thời gian được quản lý. Ghi mốc UTC cho injection, detection, fencing, promotion, routing, first successful write và validation.

## 14. Diễn tập lỗi mạng trong môi trường lab

### 14.1. Tách các đường mạng

Liệt kê ports và paths thực tế:

- Client/app tới PostgreSQL endpoint.
- Primary tới standby replication.
- Node tới DCS.
- Node tới DNS/load balancer.
- Backup/WAL archive tới object storage.
- Operator tới management plane.

Port 5432 là ví dụ phổ biến cho PostgreSQL, nhưng triển khai có thể dùng port khác. DCS ports cũng tùy công cụ.

### 14.2. Network latency và packet loss

Trong Linux lab, `tc netem` có thể mô phỏng delay/loss trên interface được chọn:

```bash
# Lab only: add delay and packet loss to the selected test interface.
sudo tc qdisc add dev eth0 root netem delay 200ms 50ms loss 2%

# Remove the injected rule after the drill.
sudo tc qdisc del dev eth0 root
```

Thay `eth0` bằng interface test đã xác minh. Quy tắc này tác động traffic trên interface đó; không chạy trên production hoặc interface quản trị nếu chưa hiểu blast radius.

### 14.3. Chặn replication path

Có thể dùng security group/firewall riêng của lab để chặn kết nối primary-standby trong một khoảng thời gian có giới hạn. Ghi chính xác rule được thêm để có thể gỡ đúng rule đó.

Không chặn tất cả traffic trên host khi mục tiêu chỉ là kiểm tra replication link. Cần giữ management access để quan sát và khôi phục.

### 14.4. Chặn client path

Chặn riêng application subnet tới database endpoint hoặc route test. Xác minh primary vẫn khỏe và standby vẫn nhận WAL. Mục tiêu là chứng minh hệ thống phân biệt lỗi đường client với lỗi database.

### 14.5. Chặn DCS path

Trong lab HA manager, chặn node thử nghiệm truy cập DCS hoặc làm mất một số DCS members để quan sát quorum/lease behavior. Không tạo partition tùy tiện trên production control plane.

### 14.6. Khôi phục network

Sau khi gỡ fault, kiểm tra:

- TCP connections có được thiết lập lại không.
- WAL receiver có reconnect không.
- Replay lag có giảm không.
- DCS members có đủ quorum không.
- Node cũ có còn bị fence không.
- Không có hai primary cùng nhận writes.

### 14.7. Không coi network partition là node failure

Đây là nguyên tắc quan trọng nhất của network drill. Một node không liên lạc được với observer vẫn có thể sống và nhận writes từ một đường khác.

## 15. Diễn tập process crash và host loss

### 15.1. PostgreSQL process restart

Trong lab, dừng service có kế hoạch để quan sát supervisor/HA manager:

```bash
sudo systemctl stop postgresql
sudo systemctl status postgresql
```

Đây là controlled stop, không phải power loss. Nó giúp xác nhận health detection và service management.

### 15.2. Process crash bất ngờ

Có thể dùng một VM/container test để mô phỏng abrupt process termination. Ghi rõ cách thực hiện và bảo đảm không ảnh hưởng shared storage hoặc host khác.

Không dùng kill -9 trên production để thay cho drill có kiểm soát.

### 15.3. Host failure

Tắt VM test bằng hypervisor/cloud test controls hoặc mô phỏng network isolation của host. Xác minh standby promotion và fencing của node cũ.

### 15.4. Storage detach/error

Nếu cần kiểm tra storage failure, dùng volume test. Xác nhận monitoring nhận ra I/O errors, mount loss hoặc latency cao. Không detach volume đang chứa production PGDATA để thử.

### 15.5. Sau khi host cũ trở lại

Không khởi động node cũ như primary. Trước tiên xác định role hiện tại, fence/disable write path và chuẩn bị rebuild thành standby từ primary mới.

## 16. Diễn tập mất zone hoặc region

### 16.1. Mất một Availability Zone

Kịch bản:

1. Xác định primary, standbys và DCS members theo zone.
2. Ghi baseline LSN và transaction markers.
3. Cô lập network hoặc dừng các test nodes trong zone được chọn.
4. Quan sát quorum và leader election.
5. Xác minh primary cũ bị fence.
6. Promote standby ở zone còn sống.
7. Chuyển endpoint và reconnect application.
8. Chạy transaction validation.
9. Khôi phục zone test và đưa node cũ về standby.

### 16.2. Mất region

Kịch bản DR nên kiểm tra toàn bộ dependency:

1. Ghi baseline ở region chính.
2. Mô phỏng region chính không thể truy cập từ DR control plane.
3. Xác minh quyết định DR activation theo runbook.
4. Xác định latest recoverable WAL/base backup ở region DR.
5. Promote DR standby hoặc restore từ backup/WAL archive.
6. Dựng/kiểm tra app dependencies ở DR.
7. Chuyển DNS/traffic.
8. Thực hiện smoke tests và data reconciliation.
9. Ghi nhận RPO/RTO.
10. Lập kế hoạch failback riêng.

### 16.3. Không phá hủy region để thử

Có thể dùng network policy, test account, test VPC, test cluster hoặc game day có blast radius được giới hạn. Mục tiêu là mô phỏng khả năng region chính không thể phục vụ từ góc nhìn DR, không cần xóa tài nguyên thật.

### 16.4. Kiểm tra control plane độc lập

Một số cloud operations cần control plane của region/account. Nếu chính control plane bị ảnh hưởng, operator có thể không tạo được VM, đổi firewall hoặc update DNS. Kiểm tra quyền và automation từ một failure domain khác.

### 16.5. Backup và WAL archive phải ngoài region

Nếu base backup/WAL archive chỉ nằm ở region chính, mất region có thể làm DR không thể dựng cluster. Kiểm tra cả object metadata, KMS keys, credentials và khả năng download.

## 17. Quan sát replication trước và trong drill

### 17.1. Primary replication state

Trên primary:

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

`sync_state` giúp nhận biết standby đang được xem là synchronous hay async theo cấu hình. Đọc cùng `synchronous_standby_names` và transaction settings.

### 17.2. Standby receiver state

Trên standby:

```sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_catalog.pg_stat_wal_receiver;
```

Nếu view không có row, standby có thể không có WAL receiver connection đang hoạt động. Kết hợp logs và `pg_is_in_recovery()`.

### 17.3. Receive và replay positions

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

Receive LSN và replay LSN có thể khác nhau. Standby có thể đã nhận WAL nhưng chưa replay hết.

### 17.4. Tính khoảng cách WAL

Trên standby, nếu có cả hai LSN:

```sql
SELECT pg_wal_lsn_diff(
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn()
) AS received_not_replayed_bytes;
```

Đây là khoảng WAL address space chưa replay, không phải thời gian lag chính xác. Dùng thêm timestamps và workload context.

### 17.5. Kiểm tra primary identity

Ghi nhận system identifier và timeline/cluster identity bằng các công cụ phù hợp với version. Không chỉ dựa vào hostname hoặc database name khi nhiều clusters có tên giống nhau.

## 18. Đo RPO bằng transaction markers

### 18.1. Tạo marker workload

Trong lab, tạo một bảng marker đơn giản trên primary:

```sql
CREATE TABLE IF NOT EXISTS ha_drill_markers (
    marker_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    drill_id text NOT NULL,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    note text
);
```

Một client test ghi marker theo chu kỳ, ghi lại marker ID và thời điểm client nhận commit success.

### 18.2. Ghi acknowledged transactions

Log mỗi marker vào một hệ thống quan sát ngoài database hoặc file test có timestamp đồng bộ. Mục tiêu là biết transaction nào đã được client xác nhận trước khi injection bắt đầu.

### 18.3. Sau promotion

Trên primary mới, đọc marker IDs. So sánh tập marker đã được acknowledge trước failure với tập marker tồn tại sau recovery.

### 18.4. Tính data loss window

Xác định marker cuối cùng được acknowledge trước sự cố nhưng không có ở primary mới. Chênh lệch timestamp giữa marker đó và failure/last commit giúp ước lượng RPO thực tế.

Nếu không mất marker đã acknowledge, ghi nhận kết quả đó trong đúng điều kiện test; không suy rộng thành cam kết zero data loss cho mọi transaction/mọi failure mode.

### 18.5. Idempotency

Client có thể không biết commit đã thành công hay response bị mất khi connection đứt. Dùng idempotency key hoặc transaction ID trong lab để phân biệt retry tạo duplicate với transaction thực sự mất.

## 19. Ứng dụng, DNS và connection pools

### 19.1. Database promote chưa đủ để ứng dụng phục hồi

Application có thể vẫn giữ connection tới primary cũ. Connection TCP cũ không tự chuyển sang primary mới. Pool cần phát hiện connection lỗi, loại bỏ connection stale và tạo connection mới tới endpoint hiện hành.

### 19.2. DNS TTL không phải thời gian chuyển đổi chắc chắn

Resolver, JVM, OS, container runtime và connection pool có thể cache DNS lâu hơn TTL dự kiến. Load balancer/proxy có health checks và routing behavior riêng. Đo thực tế từ application process.

### 19.3. Stable endpoint

Dùng một endpoint ổn định qua load balancer/proxy hoặc DNS failover theo kiến trúc. Endpoint cần route tới đúng primary mới và từ chối writes tới standby read-only.

### 19.4. Retry policy

Retry khi gặp lỗi kết nối/primary shutdown cần có:

- Backoff có jitter.
- Giới hạn retry duration.
- Phân biệt lỗi transient với constraint/business errors.
- Idempotency cho các thao tác có thể đã commit nhưng response bị mất.
- Timeout tổng thể để không retry vô hạn.
- Circuit breaker nếu downstream chưa sẵn sàng.

### 19.5. SQLSTATE và reconnect

Ứng dụng có thể nhận connection exception hoặc server shutdown errors trong lúc failover. Hãy phân loại SQLSTATE theo driver/version, không dựa vào một error message cố định. Khi connection đã mất, transaction đang mở có thể có kết quả không rõ với client; cần kiểm tra idempotency/reconciliation.

### 19.6. Read/write routing

Nếu có read replicas, application cần biết endpoint nào read-only và endpoint nào primary. Sau promotion, routing metadata phải cập nhật để không tiếp tục gửi writes tới node cũ hoặc đọc stale data ngoài SLA.

### 19.7. Connection storm

Khi hàng nghìn clients cùng reconnect, primary mới có thể bị quá tải. Dùng pool limits, staggered reconnect, backoff và connection proxy phù hợp. Drill phải đo connection establishment rate và CPU/memory.

## 20. Kiểm tra consistency sau failover

### 20.1. Server state

Xác nhận:

- Chỉ một primary được phép nhận writes.
- Standby còn lại đang follow đúng timeline.
- WAL receiver/sender state phù hợp.
- Không có stale leader lease.
- Node cũ bị fence.
- Replication slots/standby connections được xử lý theo topology.

### 20.2. Data checks

Chạy các truy vấn kiểm tra:

- Marker cuối cùng đã commit.
- Row counts ở các bảng critical.
- Business aggregates.
- Unique keys và foreign keys.
- Transaction records gần thời điểm failure.
- Sequence values nếu có cutover.
- Dữ liệu được replicate theo publication nếu là logical replication.

### 20.3. Sequence state

Với physical replication, sequence state nằm trong physical data stream. Với logical replication native, sequence state không được replicate như row changes thông thường. Nếu ứng dụng dùng logical migration/cutover, đồng bộ sequence values theo runbook để tránh duplicate IDs.

### 20.4. Không chỉ kiểm tra SELECT 1

SELECT 1 chứng minh server nhận kết nối và thực thi một câu query đơn giản. Nó không chứng minh ứng dụng có thể ghi, commit, đọc lại dữ liệu hoặc gọi các dependencies.

### 20.5. Smoke test theo business path

Thực hiện một giao dịch test được kiểm soát: tạo record, commit, đọc lại, kiểm tra side effects ở môi trường test và xác minh không phát sinh duplicate. Có thể dùng synthetic account/order để không tạo giao dịch thật.

## 21. Failback: đưa node cũ trở lại

### 21.1. Old primary không tự trở lại primary

Sau failover, node cũ có thể chứa WAL history phân kỳ. Không khởi động lại nó như primary độc lập và không cho application route vào.

### 21.2. Rebuild thành standby

Cách an toàn thường là đưa old primary về vai trò standby của primary hiện tại. Tùy tình trạng divergence, có thể dùng pg_rewind nếu đáp ứng prerequisites hoặc tạo fresh base backup.

### 21.3. pg_rewind

pg_rewind có thể đồng bộ một data directory đã phân kỳ trở lại với một source cluster chung lịch sử, trong điều kiện phù hợp. Thường cần data checksums được bật hoặc wal_log_hints đã bật trước đó, WAL cần thiết còn đủ và hai clusters cùng major version. Kiểm tra tài liệu của đúng version và thực hiện theo runbook.

Nếu không đáp ứng prerequisites, dùng base backup mới. Không giả định pg_rewind luôn có thể sửa bất kỳ old primary nào.

### 21.4. Fencing vẫn cần thiết

Giữ old primary không nhận writes trong toàn bộ quá trình rebuild. Chỉ đưa nó vào replication topology sau khi xác minh data directory và role.

### 21.5. Không failback chỉ để quay lại hostname cũ

Failback là một thay đổi vận hành có rủi ro. Chỉ thực hiện khi có lý do về capacity, latency, topology hoặc maintenance; planned switchover cần kiểm tra standby đã catch up và có rollback plan.

### 21.6. Xác minh sau failback

Kiểm tra replication state, timeline, LSN positions, synchronous standby configuration, routing, backup jobs và monitoring. Đảm bảo topology HA đã được phục hồi đầy đủ sau incident.

## 22. Backup và DR khác với standby

### 22.1. Standby có thể replicate lỗi logic

Nếu người dùng chạy nhầm DELETE hoặc ứng dụng ghi dữ liệu sai, physical standby cũng replay thay đổi đó. Standby không phải bản sao lịch sử bất biến.

### 22.2. Backup giữ recovery points cũ

Base backup và WAL archive cho phép PITR về trước thời điểm lỗi nếu retention còn đủ. Backup phải nằm trong failure domain độc lập.

### 22.3. Snapshot và archive

Storage snapshots có thể giúp dựng volume nhanh, nhưng cần consistency procedure và WAL cần thiết. WAL archive phải có chuỗi liên tục và được kiểm tra.

### 22.4. DR test cần thử restore từ backup

Một region DR không chỉ nên có standby. Thử dựng cluster từ base backup và WAL archive trong môi trường tách biệt để chứng minh đường khôi phục độc lập.

### 22.5. Backup restore và failover là hai bài diễn tập

Failover kiểm tra continuity từ standby. Restore drill kiểm tra khả năng phục hồi khi replica/primary bị hỏng logic hoặc storage. Cần cả hai.

## 23. Runbook cho từng scenario

### 23.1. Network partition

1. Xác định path bị đứt: client, replication, DCS hay management.
2. Thu thập health signals từ nhiều vantage points.
3. Kiểm tra primary còn nhận writes từ client nào không.
4. Kiểm tra DCS quorum/leader lease.
5. Xác minh fencing trước promotion.
6. Đánh giá standby freshness và RPO.
7. Promote theo HA manager/runbook nếu đủ điều kiện.
8. Chuyển endpoint, reconnect clients.
9. Xác minh old primary không nhận writes.
10. Khôi phục network và rejoin old node như standby.

### 23.2. Primary process/host loss

1. Xác nhận process/host state và failure scope.
2. Kiểm tra DCS/HA manager.
3. Xác định standby candidate và replay position.
4. Fence old primary hoặc xác minh host đã tắt.
5. Promote candidate theo công cụ triển khai.
6. Chuyển endpoint và reconnect application.
7. Kiểm tra transaction markers và business data.
8. Khôi phục redundancy bằng standby mới.
9. Lập kế hoạch rebuild node cũ.
10. Đo RPO/RTO và lưu logs.

### 23.3. Region loss

1. Xác định region chính có thực sự không thể phục vụ.
2. Kiểm tra DR authority và điều kiện activation.
3. Chọn standby hoặc base backup/WAL archive phù hợp.
4. Ước lượng data loss theo latest recoverable LSN.
5. Fence region cũ nếu có thể và ngăn split brain khi nó trở lại.
6. Promote/restore database ở region DR.
7. Dựng app, secrets, network và dependencies.
8. Chuyển DNS/traffic.
9. Chạy data/application validation.
10. Ghi nhận RPO/RTO và lên kế hoạch failback riêng.

## 24. Đo lường kết quả drill

### 24.1. Các timestamp cần ghi

| Timestamp | Ý nghĩa |
| --- | --- |
| T0 | Fault injection bắt đầu |
| T1 | Monitoring phát hiện |
| T2 | Incident/failover decision |
| T3 | Fencing hoàn tất |
| T4 | Promotion hoàn tất |
| T5 | Endpoint/routing cập nhật |
| T6 | Application reconnect thành công |
| T7 | First successful write |
| T8 | Data validation hoàn tất |
| T9 | Full service restored |

### 24.2. Các metric tính được

- Detection time = T1 - T0.
- Decision time = T2 - T1.
- Fencing time = T3 - T2.
- Promotion time = T4 - T3.
- Routing time = T5 - T4.
- Application recovery time = T7 - T5.
- End-to-end RTO = T9 - T0 theo tiêu chí service restored đã định nghĩa.
- RPO = khoảng dữ liệu đã acknowledge nhưng không tồn tại trong recovered state.

### 24.3. Ghi nhận lỗi phụ

Theo dõi error rate, failed transactions, retry count, duplicate requests, connection storm, CPU/memory, WAL lag và disk usage.

### 24.4. Kết quả không chỉ là pass/fail

Một drill có thể đạt RTO nhưng phát hiện RPO cao hơn cam kết; hoặc dữ liệu an toàn nhưng client reconnect quá lâu. Ghi từng dimension riêng.

### 24.5. Evidence

Lưu timeline, HA manager logs, PostgreSQL logs, DCS state, LSN snapshots, transaction markers, DNS/LB changes, application traces và người phê duyệt quyết định.

## 25. Tần suất và cấp độ diễn tập

### 25.1. Tabletop exercise

Nhóm đọc runbook và diễn giải ai làm gì khi failure xảy ra. Không injection. Dùng để phát hiện thiếu owner, quyết định mơ hồ và thông tin liên hệ cũ.

### 25.2. Component drill

Thử một process/connection hoặc network path trong lab. Mục tiêu là hiểu hành vi của từng thành phần.

### 25.3. Staging failover drill

Thực hiện failover end-to-end với application, routing và monitoring giống production.

### 25.4. Zone/region DR drill

Diễn tập định kỳ trong môi trường có blast radius được giới hạn. Thử cả database và application dependencies.

### 25.5. Sau thay đổi kiến trúc

Chạy lại drill khi thay PostgreSQL major version, HA manager, DCS topology, network, DNS, storage, synchronous replication hoặc connection pool.

### 25.6. Tần suất theo criticality

Dịch vụ quan trọng có thể cần tabletop hàng quý, staging failover thường xuyên hơn và DR test định kỳ theo yêu cầu compliance/business. Chọn lịch theo rủi ro và khả năng thực hiện, không dùng lịch máy móc.

## 26. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Có standby là đã có HA | Cần detection, fencing, promotion, routing và validation |
| Failover luôn không mất dữ liệu | Async replication có thể mất acknowledged commits |
| synchronous_commit = on bảo đảm mọi scenario RPO 0 | Cần synchronous standby thực sự, đúng candidate và fencing |
| Ping không được nghĩa primary đã chết | Có thể chỉ là network partition |
| Chặn client path thì phải promote standby | Database có thể vẫn khỏe và replication bình thường |
| Standby không nhận WAL nghĩa primary chết | Replication path có thể lỗi trong khi primary còn writes |
| DCS quorum và PostgreSQL replication là một | Chúng là hai lớp khác nhau |
| Quorum bảo đảm chọn replica mới nhất | Quorum chọn quyền điều phối, không thay data freshness check |
| Đổi DNS là fencing | Node cũ vẫn có thể nhận writes qua connection/IP cũ |
| Promote trước rồi mới fence | Có nguy cơ split brain |
| Switchover thành công chứng minh failover | Failure path có thể có quorum/fencing/network khác |
| Promote là dịch vụ đã phục hồi | App reconnect và data validation còn cần |
| DNS TTL là thời gian reconnect | Cache/pool có thể giữ trạng thái cũ lâu hơn |
| Retry mọi transaction là an toàn | Commit outcome có thể không rõ; cần idempotency |
| Replay lag bằng 0 chứng minh mọi data business đã xử lý | Cần xác minh transaction/app/downstream state |
| Mất region chỉ cần promote database | App, secrets, network, DNS và dependencies cũng cần |
| Backup trong cùng region đủ cho region DR | Region outage có thể làm mất cả backup |
| Standby thay backup | Logical corruption có thể replicate |
| Old primary có thể start lại bình thường | Cần fence và rebuild/rejoin thành standby |
| pg_rewind luôn sửa được old primary | Có prerequisites và WAL/common-history requirements |
| Failback phải diễn ra ngay | Chỉ làm khi có lý do và runbook an toàn |
| Một lần drill thành công là đủ | Cấu hình và dependencies thay đổi; cần diễn tập định kỳ |
| RTO chỉ là promotion time | RTO end-to-end gồm detection, routing, reconnect và validation |
| RPO có thể suy ra từ lag trung bình | Đo bằng acknowledged transactions thực tế |
| Region DR không cần test vì standby đang streaming | Cần test cả control plane và application dependencies |

## 27. Bài tập thực hành có đáp án

Các bài tập giả định bạn có một lab PostgreSQL HA riêng. Không tạo network partition, stop host hoặc promote node trong production chỉ để làm bài.

### Bài 1. HA khác DR thế nào?

**Đáp án:** HA giảm gián đoạn do failures thường gặp; DR khôi phục dịch vụ sau sự cố lớn như mất region hoặc failure domain chính.

### Bài 2. Failover là gì?

**Đáp án:** Chuyển dịch vụ từ primary lỗi sang standby được promote thành primary mới.

### Bài 3. Switchover là gì?

**Đáp án:** Chuyển vai trò primary/standby có kế hoạch và có kiểm soát.

### Bài 4. RPO là gì?

**Đáp án:** Lượng dữ liệu tối đa tổ chức chấp nhận mất theo một failure scenario.

### Bài 5. RTO là gì?

**Đáp án:** Thời gian tối đa chấp nhận để khôi phục dịch vụ theo tiêu chí đã định nghĩa.

### Bài 6. Vì sao RTO không chỉ là promotion time?

**Đáp án:** Còn detection, fencing, routing, reconnect, smoke tests và data validation.

### Bài 7. Asynchronous replication có thể mất dữ liệu khi nào?

**Đáp án:** Khi primary mất trước khi WAL mới nhất được standby nhận/flush và standby đó được promote.

### Bài 8. Synchronous replication giúp gì?

**Đáp án:** Commit chờ acknowledgement từ synchronous standby theo cấu hình, giảm nguy cơ mất acknowledged transactions.

### Bài 9. synchronous_commit = remote_write chờ điều gì?

**Đáp án:** Synchronous standby ghi WAL tới hệ điều hành, chưa nhất thiết durable như remote flush.

### Bài 10. synchronous_commit = on chờ điều gì?

**Đáp án:** Local WAL flush và remote synchronous standby flush theo cấu hình.

### Bài 11. remote_apply khác on thế nào?

**Đáp án:** remote_apply chờ standby replay transaction để có thể nhìn thấy transaction đó.

### Bài 12. synchronous_standby_names có nhiệm vụ gì?

**Đáp án:** Chọn synchronous standby và số lượng acknowledgement cần thiết theo FIRST/ANY.

### Bài 13. Synchronous replication có tự fence primary cũ không?

**Đáp án:** Không. Cần fencing/HA orchestration riêng.

### Bài 14. Split brain là gì?

**Đáp án:** Hai node cùng nhận writes trong khi mỗi node tin mình là primary.

### Bài 15. Fencing là gì?

**Đáp án:** Ngăn node cũ tiếp tục nhận writes trước khi promote node mới.

### Bài 16. Đổi DNS có phải fencing không?

**Đáp án:** Không. Client cũ hoặc đường IP trực tiếp vẫn có thể truy cập node cũ.

### Bài 17. Network partition khác server crash thế nào?

**Đáp án:** Partition làm mất một đường liên lạc; server có thể vẫn sống và nhận writes từ đường khác.

### Bài 18. Chặn client path có nhất thiết cần failover?

**Đáp án:** Không. Primary có thể vẫn khỏe và standby vẫn đồng bộ.

### Bài 19. Chặn replication path có nghĩa primary đã chết?

**Đáp án:** Không. Primary có thể tiếp tục writes trong khi standby lag.

### Bài 20. DCS quorum dùng để làm gì?

**Đáp án:** Hỗ trợ quyết định nhất quán về leader/coordination trong distributed HA manager.

### Bài 21. PostgreSQL native replication có tự cung cấp toàn bộ leader election không?

**Đáp án:** Không. Thường cần HA manager/orchestrator bên ngoài.

### Bài 22. Witness có ý nghĩa gì?

**Đáp án:** Thành viên hỗ trợ quorum/arbitration theo semantics của hệ thống, không chỉ là health-check VM.

### Bài 23. Vì sao không dùng ping làm bằng chứng node chết?

**Đáp án:** ICMP có thể bị chặn hoặc route lỗi trong khi PostgreSQL vẫn hoạt động.

### Bài 24. Process crash khác host loss thế nào?

**Đáp án:** Process crash chỉ làm PostgreSQL/service dừng; host loss khiến cả node không truy cập được.

### Bài 25. Disk full có thể ảnh hưởng gì?

**Đáp án:** WAL/data writes có thể thất bại và server có thể không hoạt động bình thường.

### Bài 26. Vì sao không xóa thủ công file trong pg_wal?

**Đáp án:** PostgreSQL quản lý WAL lifecycle; xóa thủ công có thể phá recovery và replication.

### Bài 27. Region outage ảnh hưởng những gì ngoài database?

**Đáp án:** App, network, DNS, control plane, secrets, KMS, monitoring và external dependencies.

### Bài 28. Vì sao cần off-region base backup và WAL archive?

**Đáp án:** Để khôi phục cluster khi region chính và storage trong region đó không còn truy cập được.

### Bài 29. Cross-region async replica có trade-off gì?

**Đáp án:** Giảm commit latency nhưng có thể có data loss window khi region chính mất.

### Bài 30. Tại sao cần đo LSN trước drill?

**Đáp án:** Làm baseline để so sánh WAL received/replayed và ước lượng data freshness.

### Bài 31. View nào trên primary hiển thị replication state?

**Đáp án:** pg_stat_replication.

### Bài 32. View nào trên standby hiển thị WAL receiver?

**Đáp án:** pg_stat_wal_receiver.

### Bài 33. Hàm nào kiểm tra standby đang ở recovery?

**Đáp án:** pg_is_in_recovery().

### Bài 34. Receive LSN và replay LSN khác nhau thế nào?

**Đáp án:** Receive là WAL đã nhận; replay là WAL đã áp dụng vào data state.

### Bài 35. pg_wal_lsn_diff dùng để làm gì?

**Đáp án:** Tính khoảng cách byte giữa hai WAL positions, không trực tiếp tính thời gian lag.

### Bài 36. Transaction marker giúp đo gì?

**Đáp án:** Transaction đã được acknowledge trước failure có còn tồn tại sau promotion hay không.

### Bài 37. Vì sao cần idempotency trong failover drill?

**Đáp án:** Client có thể mất response sau khi commit đã thành công và retry có thể tạo duplicate.

### Bài 38. DNS TTL có bảo đảm application reconnect đúng thời điểm không?

**Đáp án:** Không. Resolver, OS và connection pool có thể cache hoặc giữ connection lâu hơn.

### Bài 39. Connection pool cần làm gì sau failover?

**Đáp án:** Loại connection stale và tạo connection mới tới endpoint primary hiện hành.

### Bài 40. Vì sao retry transaction cần thận trọng?

**Đáp án:** Client có thể không biết transaction trước đã commit hay chưa; cần idempotency/reconciliation.

### Bài 41. Một SELECT 1 có chứng minh service phục hồi hoàn toàn?

**Đáp án:** Không. Cần thử write/commit/read và business dependencies.

### Bài 42. Tại sao cần kiểm tra chỉ một primary nhận writes?

**Đáp án:** Để phát hiện và ngăn split brain.

### Bài 43. Sau failover, old primary nên làm gì?

**Đáp án:** Bị fence rồi rebuild/rejoin thành standby của primary mới.

### Bài 44. pg_rewind dùng trong tình huống nào?

**Đáp án:** Đồng bộ data directory đã phân kỳ về source cluster chung lịch sử khi đáp ứng prerequisites.

### Bài 45. Khi nào cần fresh base backup thay pg_rewind?

**Đáp án:** Khi không đủ prerequisites, WAL/common history không còn hoặc rewind không phù hợp.

### Bài 46. Vì sao failback cần kế hoạch riêng?

**Đáp án:** Old primary có thể có lịch sử phân kỳ; chuyển vai trò cần catch-up, fencing, routing và validation.

### Bài 47. Game day là gì?

**Đáp án:** Diễn tập tạo failure có kiểm soát để đo khả năng phát hiện, phục hồi và cải thiện runbook.

### Bài 48. Tabletop exercise khác fault injection thế nào?

**Đáp án:** Tabletop diễn giải runbook không tạo lỗi thật; fault injection tạo failure có kiểm soát trong môi trường được chọn.

### Bài 49. Vì sao cần stop conditions?

**Đáp án:** Để dừng drill khi có split brain risk, RPO vượt ngưỡng hoặc blast radius vượt phạm vi.

### Bài 50. Ai nên có quyền dừng drill?

**Đáp án:** Một người được chỉ định trước, độc lập với người thực hiện fault injection nếu có thể.

### Bài 51. Cần ghi những timestamp nào?

**Đáp án:** Injection, detection, decision, fencing, promotion, routing, first successful write và validation complete.

### Bài 52. Detection time tính thế nào?

**Đáp án:** T1 - T0, với T0 là lúc inject fault và T1 là lúc monitoring phát hiện.

### Bài 53. End-to-end RTO tính thế nào?

**Đáp án:** Từ fault start đến khi service đạt tiêu chí restored đã định nghĩa, bao gồm validation nếu nằm trong tiêu chí.

### Bài 54. RPO nên đo bằng gì?

**Đáp án:** Acknowledged transaction markers và recovered data, không chỉ một lag metric trung bình.

### Bài 55. Vì sao cần kiểm tra control plane ở region DR?

**Đáp án:** Nếu không thể tạo compute, network, update DNS hoặc lấy secrets, DR region có thể không khởi động được service.

### Bài 56. Mất region có thể ảnh hưởng KMS/secrets thế nào?

**Đáp án:** Key/secret access có thể phụ thuộc region hoặc control plane chính; cần thử quyền giải mã và credential ở DR.

### Bài 57. Synchronous standby ở xa có chi phí gì?

**Đáp án:** Commit latency tăng theo network RTT và availability có thể giảm khi inter-region link lỗi.

### Bài 58. Vì sao một drill thành công không đủ?

**Đáp án:** Topology, software, network và dependencies thay đổi; cần diễn tập định kỳ và sau thay đổi lớn.

### Bài 59. Khi nào có thể tuyên bố drill pass?

**Đáp án:** Khi RPO/RTO, fencing, single-primary, application validation và evidence đều đáp ứng tiêu chí đã đặt.

### Bài 60. Lập checklist diễn tập mất region

**Đáp án gợi ý:**

1. Xác định RPO/RTO và người có quyền DR activation.
2. Ghi baseline primary/standby LSN, timeline và acknowledged markers.
3. Xác minh off-region base backup/WAL archive và KMS access.
4. Mô phỏng region chính không thể phục vụ từ góc nhìn DR.
5. Kiểm tra quorum, leader decision và fencing.
6. Chọn standby/backup có WAL freshness phù hợp.
7. Promote hoặc restore database tại region DR.
8. Dựng application, network, secrets, DNS và dependencies.
9. Chạy write/read smoke tests và kiểm tra marker/business data.
10. Ghi RPO/RTO, giữ evidence và lập kế hoạch failback riêng.

## 28. Checklist production

| Kiểm tra | Điều cần bảo đảm |
| --- | --- |
| Failure domains | Primary, standby, quorum và app không cùng một failure domain không cần thiết |
| RPO/RTO | Có mục tiêu riêng theo scenario |
| Replication mode | Sync/async trade-off được ghi rõ |
| synchronous_commit | Phù hợp durability requirement |
| synchronous_standby_names | Candidate/acknowledgement policy rõ |
| HA manager | Version, leader election và failover policy được kiểm thử |
| DCS quorum | Có đủ members và placement phù hợp |
| Fencing | Có thể chứng minh primary cũ không nhận writes |
| Split brain | Có kiểm tra single-primary sau promotion |
| Network paths | Client, replication, DCS và management được tách khi drill |
| Health checks | Nhiều vantage points, tránh false failover |
| Replication lag | Có baseline và alert |
| LSN markers | Có thể đo acknowledged transactions |
| Host failure | Có drill process và VM/host loss |
| Zone failure | Có candidate và quorum ở zone còn lại |
| Region DR | Có database và application dependencies |
| Backups | Base backup/WAL archive off-region |
| KMS/secrets | Có thể truy cập ở DR |
| DNS/LB | Có routing update và health checks |
| Connection pools | Reconnect, stale connection cleanup và retry |
| Idempotency | Có xử lý unknown commit outcome |
| Data validation | Có business smoke tests và reconciliation |
| Failback | Old primary được fence/rebuild thành standby |
| Observability | PostgreSQL, HA manager, DCS, network, app logs |
| Stop conditions | Được thống nhất trước drill |
| Drill owner | Có người inject, observe và stop |
| Evidence | Timeline, logs, LSNs, markers và routing changes |
| RPO/RTO report | Có số đo thực tế |
| Restore drill | Có test backup độc lập với standby |
| Review actions | Có owner và due date cho từng gap |

## 29. Tổng kết

Diễn tập lỗi mạng, mất máy chủ và mất vùng giúp chứng minh PostgreSQL HA/DR hoạt động trong failure conditions thực tế. Một quy trình phục hồi hoàn chỉnh phải xử lý detection, leader decision, fencing, promotion, routing, application reconnect và data validation. Thành công không chỉ là standby trở thành primary; hệ thống phải tránh split brain, giữ dữ liệu trong RPO và phục vụ lại ứng dụng trong RTO.

Những nguyên tắc quan trọng:

1. **Phân biệt HA và DR.** Standby cùng region không bảo vệ được mọi region failure.
2. **Đặt RPO/RTO theo từng scenario.** Đo acknowledged transactions và thời gian service restored.
3. **Hiểu sync/async trade-off.** Synchronous replication có thể giảm data loss nhưng tăng latency và phụ thuộc standby.
4. **Network partition không phải server crash.** Node bị cô lập vẫn có thể sống và nhận writes.
5. **Fencing trước promotion.** Không để hai primary cùng phục vụ writes.
6. **Quorum và replication là hai lớp khác nhau.** DCS quyết định leader coordination; WAL state quyết định data freshness.
7. **Không dùng ping làm bằng chứng node đã chết.** Dùng nhiều health signals và fencing.
8. **Kiểm tra client path, replication path và DCS path riêng.** Mỗi loại lỗi cần response khác nhau.
9. **Mất region ảnh hưởng cả dependencies.** Database, app, network, DNS, secrets, KMS và control plane phải được thử.
10. **Đo RPO bằng transaction markers.** Lag metric không chứng minh mọi acknowledged commit đã tồn tại.
11. **Ứng dụng cần reconnect và idempotency.** Failover có thể làm commit outcome không rõ với client.
12. **Old primary phải được rebuild an toàn.** Không cho node cũ start lại như primary sau promotion.
13. **Backup không thay standby và standby không thay backup.** Cần diễn tập cả failover lẫn restore.
14. **Game day cần stop conditions và evidence.** Kiểm soát blast radius và đo từng giai đoạn.
15. **Lặp lại sau thay đổi lớn.** Một lần pass không bảo đảm topology tương lai vẫn an toàn.

Mô hình đánh giá:

```text
Failure được phát hiện?
        |
        v
Đã xác định đúng failure domain?
        |
        v
Old primary đã được fence?
        |
        v
Candidate có WAL phù hợp RPO?
        |
        v
Promote đúng một primary?
        |
        v
Endpoint và clients đã reconnect?
        |
        v
Write/read business tests thành công?
        |
        v
RPO/RTO đạt mục tiêu?
        |
        v
Evidence, review và action owners
```

**Câu hỏi review cuối cùng:** “Nếu primary chỉ mất kết nối tới DCS nhưng vẫn nhận writes từ ứng dụng, hệ thống có fence nó trước khi promote standby không? Nếu region chính biến mất, region DR có đủ WAL, compute, secrets, DNS và application dependencies để phục vụ không? Và chúng ta đã đo bằng transaction markers rằng RPO/RTO thực tế đạt mục tiêu chưa?” Một HA/DR design chỉ đáng tin khi các câu hỏi đó đã được trả lời bằng diễn tập và evidence thực tế.
