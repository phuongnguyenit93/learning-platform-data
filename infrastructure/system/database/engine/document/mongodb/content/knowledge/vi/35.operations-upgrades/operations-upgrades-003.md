# Kiểm tra sẵn sàng, khởi động, dừng và bảo trì có kiểm soát trong MongoDB

Một MongoDB process đang chạy không đồng nghĩa cơ sở dữ liệu **sẵn sàng phục vụ ứng dụng**. Một replica set có thể có mongod đang lắng nghe cổng TCP nhưng chưa có primary; một secondary có thể đang đồng bộ chậm; một mongos có thể hoạt động nhưng không liên lạc được với config servers; ứng dụng có thể ping thành công nhưng không ghi được với write concern đã cam kết.

Vì vậy, **khởi động, dừng và bảo trì có kiểm soát** cần được xem là một quy trình vận hành có điều kiện trước, trong và sau thao tác; không chỉ là chạy lệnh restart rồi quan sát service status.

Bài học thuộc chương **Vận hành và nâng cấp**, module **Database Engine Document MongoDB**, trình bày:

1. Phân biệt liveness, readiness, application readiness và maintenance readiness.
2. Kiểm tra tiến trình, cấu hình, replication, quorum, hiệu năng và kết nối trước khi thay đổi.
3. Khởi động và dừng mongod/mongos đúng cách trên Linux, Windows, container và môi trường được quản lý.
4. Rolling maintenance trong replica set, xử lý primary stepdown và các tình huống mất quorum.
5. Điều phối bảo trì sharded cluster, config servers, shards, mongos và balancer.
6. Quy trình preflight, drain traffic, change execution, smoke tests, rollback và báo cáo bằng chứng.
7. Các kịch bản lỗi, bài tập thực hành và checklist dùng để xây runbook.

**Nguyên tắc an toàn:** Các lệnh stop, restart, stepdown và điều chỉnh hạ tầng có thể gây gián đoạn hoặc mất khả năng ghi. Chỉ thực hiện khi có quyền, xác nhận đúng cluster/host, có kế hoạch bảo trì và phương án khôi phục. Những ví dụ lệnh dưới đây dành cho hệ thống thử nghiệm hoặc một runbook đã được phê duyệt, không phải hướng dẫn chạy máy móc trên production.

## 1. Bốn lớp sẵn sàng cần phân biệt

| Lớp | Câu hỏi | Ví dụ bằng chứng |
| --- | --- | --- |
| **Liveness** | Tiến trình có tồn tại và phản hồi tối thiểu? | Service/process status, TCP, ping |
| **Database readiness** | MongoDB có thể phục vụ thao tác đúng vai trò? | Primary/secondary states, auth, quorum, read/write probe |
| **Application readiness** | API và các chức năng quan trọng có làm việc đúng? | Login, read/write, business smoke tests |
| **Maintenance readiness** | Có đủ điều kiện để tạm dừng/thay đổi một thành phần an toàn? | Healthy majority, backup, replication lag, capacity, rollback |

Không thể thay thế một lớp bằng lớp khác.

### 1.1. Process running chưa chắc database ready

Một lệnh:

~~~bash
systemctl is-active mongod
~~~

có thể trả active. Nhưng MongoDB vẫn có thể:

- Đang startup recovery hoặc initial sync.
- Chưa bầu được primary.
- Đang có replication lag lớn.
- Không còn dung lượng đĩa.
- Bị lỗi authentication/TLS của application.
- Không đạt majority write concern.
- Không có index cần thiết cho API quan trọng.

### 1.2. Ping chưa đủ

Lệnh:

~~~javascript
db.adminCommand({ ping: 1 });
~~~

chứng minh kết nối và khả năng xử lý một lệnh đơn giản, **không chứng minh** dữ liệu hoặc các giao dịch nghiệp vụ hoạt động đúng.

### 1.3. Database ready nhưng application chưa ready

Ứng dụng có thể vẫn lỗi do connection string sai, credentials hết hạn, connection pool quá nhỏ, chưa chạy migration tương thích hoặc background workers chưa khởi động đúng.

### 1.4. Maintenance readiness là điều kiện chặt hơn

Một replica set đang phục vụ bình thường nhưng đã mất một voting member có thể **không an toàn để dừng thêm thành viên**. Bảo trì phải xét failure budget còn lại, không chỉ biết hệ thống đang online.

## 2. Thuật ngữ vận hành

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **mongod** | Database server process, gồm standalone, replica set member và shards/config servers |
| **mongos** | Router cho sharded cluster |
| **Replica set** | Nhóm mongod duy trì dữ liệu sao chép, có cơ chế election |
| **Primary** | Thành viên nhận writes trong mô hình replica set thông thường |
| **Secondary** | Thành viên sao chép oplog và có thể được dùng cho reads theo cấu hình |
| **Election** | Quá trình chọn primary mới |
| **Quorum/majority** | Số voting members tối thiểu cần để bầu và duy trì cơ chế majority |
| **Replication lag** | Độ trễ giữa tiến độ ghi primary và secondary |
| **Oplog window** | Khoảng thời gian lịch sử trong oplog có thể hỗ trợ replication/resume |
| **Stepdown** | Yêu cầu primary nhường vai trò, tạo điều kiện election |
| **Graceful shutdown** | Dừng theo cơ chế có kiểm soát, cho tiến trình đóng tài nguyên hợp lệ |
| **Rolling maintenance** | Bảo trì từng thành phần theo thứ tự để hạn chế gián đoạn |
| **Drain** | Điều hướng/giảm các kết nối hoặc request mới trước khi dừng thành phần |
| **Go/No-Go** | Quyết định cho phép hoặc dừng bảo trì dựa trên điều kiện cụ thể |
| **Rollback** | Trở về trạng thái phần mềm/cấu hình trước đó khi an toàn và được hỗ trợ |

**Lưu ý:** Rollback binary hoặc cấu hình không tự giống rollback dữ liệu. Sau khi thay đổi FCV/schema hoặc có writes mới, việc quay về version cũ có thể bị giới hạn hoặc không an toàn.

## 3. Sơ đồ về trạng thái sẵn sàng

~~~text
Host/Container up
       |
       v
mongod process running
       |
       v
TCP/TLS/auth reachable
       |
       v
Replication topology healthy
       |
       +--> standalone: server ready
       |
       +--> replica set:
                 |
                 v
              Primary elected
                 |
                 v
              Majority reachable
                 |
                 v
              Reads/writes verified
       |
       v
Required indexes and dependencies ready
       |
       v
Application smoke tests pass
       |
       v
Service ready for business traffic
~~~

### 3.1. Các kết quả health cần ghi nhận

Không chỉ lưu một boolean.

~~~text
processHealthy: true
helloResponded: true
topologyRole: SECONDARY
primaryAvailable: true
replicationLagSeconds: 1.8
diskFreePercent: 27
applicationReadProbe: pass
applicationWriteProbe: pass
maintenanceEligible: true
~~~

Các giá trị là ví dụ; ngưỡng phải được tổ chức xác định theo workload/SLO.

### 3.2. Không ép mọi member phải là primary

Một secondary bình thường có thể hoàn toàn healthy khi **không writable**. Readiness probe phải hiểu vai trò thành viên và mục tiêu của endpoint.

## 4. Phân loại triển khai trước khi thao tác

MongoDB có nhiều mô hình triển khai.

### 4.1. Standalone

~~~text
Application -> mongod
~~~

Dừng một mongod đồng nghĩa database tạm thời không phục vụ. Không có election tự động.

### 4.2. Replica set

~~~text
Application -> MongoDB driver
                   |
                   +-> PRIMARY mongod
                   +-> SECONDARY mongod
                   +-> SECONDARY mongod
~~~

Có thể bảo trì lần lượt members, nhưng vẫn phải giữ voting majority và kiểm soát primary transition.

### 4.3. Sharded cluster

~~~text
Application
     |
     v
  mongos routers
     |
     v
Config Server Replica Set
     |
     +-> Shard Replica Set A
     +-> Shard Replica Set B
     +-> Shard Replica Set C
~~~

Có nhiều phạm vi failure. Một thành viên config server không giống một shard secondary, và mongos không phải primary dữ liệu.

### 4.4. MongoDB Atlas/managed service

Nhà cung cấp quản lý mongod processes, storage lifecycle và một phần maintenance. Không chạy thủ công systemctl vào cluster được quản lý. Sử dụng cơ chế bảo trì, upgrade, backup và observability được dịch vụ hỗ trợ.

### 4.5. Kubernetes/Operators

MongoDB có thể được triển khai qua StatefulSet và một Operator. Kubernetes tự động restart pods theo probes/controllers, nhưng không tự thay thế hoàn toàn hiểu biết về primary/quorum. Nếu có MongoDB Operator, ưu tiên quy trình upgrade/rollout do Operator hỗ trợ.

## 5. Các điều kiện Go/No-Go trước bảo trì

Một thay đổi nên có **maintenance gate** với các câu hỏi:

1. Đã xác nhận đúng cluster/environment/host?
2. Có người chịu trách nhiệm và thời điểm bảo trì được phê duyệt?
3. Có inventory các node, versions và roles?
4. Có healthy majority của mọi replica set bị ảnh hưởng?
5. Có secondary đủ cập nhật và electable cho primary stepdown?
6. Replication lag có dưới ngưỡng chấp nhận?
7. Oplog window có đủ nếu một node cần offline lâu?
8. Có backup hợp lệ, recovery procedure và quyền restore?
9. Dung lượng đĩa, inode, RAM và CPU đủ headroom?
10. Không có sự cố production đang cần xử lý hoặc error budget đã hết?
11. Đã xử lý jobs nhạy cảm, migrations, index builds và database connections?
12. Application retry/failover behavior đã được xác nhận?
13. Có rollback/abort condition và người ra quyết định?
14. Observability, alerts và communication channels sẵn sàng?
15. Có smoke tests sau từng bước?

Nếu điều kiện quan trọng không đạt, **hoãn hoặc đổi kế hoạch**, không dùng một lệnh force để vượt qua.

## 6. Xác định đúng cluster và phiên bản

Trước khi chạy bất kỳ lệnh nào, kiểm tra connection context:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Lệnh hello có thể cung cấp role/capabilities của endpoint như **isWritablePrimary**, **secondary**, **setName**, danh sách hosts hoặc dấu hiệu mongos tùy topology.

Xem phiên bản server khi có quyền:

~~~javascript
db.adminCommand({ buildInfo: 1 });
~~~

### 6.1. Không chỉ tin hostname

Tên host có thể bị reuse hoặc DNS đổi. Trong runbook nên ghi cluster ID, replica set name, environment label và đối chiếu dữ liệu từ monitoring/control plane.

### 6.2. Mongos khác mongod

Kết nối tới mongos là kết nối tới router; các lệnh **rs.status()** trên mongos không phải cách kiểm tra trực tiếp một replica set member. Hãy dùng các endpoints/monitoring tương ứng.

### 6.3. Feature Compatibility Version

Khi bảo trì kèm nâng cấp, cần kiểm tra **FCV** và compatibility của phiên bản binary:

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

Tính năng/cú pháp và quy trình downgrade phụ thuộc phiên bản. Không thay FCV như một bước khởi động lại thông thường.

## 7. Kiểm tra tình trạng replica set

Kết nối tới một member có quyền thích hợp:

~~~javascript
rs.status();
~~~

Tập trung các trường thông tin:

- Member name/address.
- State PRIMARY/SECONDARY/RECOVERING/STARTUP2, v.v.
- Member health.
- Thời điểm/tiến độ oplog.
- Election term và primary.
- Replication lag.
- Heartbeat failures.
- Sync source.
- Voting/electable configuration.

### 7.1. Trạng thái SECONDARY không đồng nghĩa đã bắt kịp

Một secondary có thể đang nhận oplog nhưng lag đáng kể. Nếu dự định stepdown primary để secondary trở thành primary, cần kiểm tra khả năng catch-up.

### 7.2. Không thực hiện chỉ dựa trên một ảnh chụp

Health và lag thay đổi theo thời gian. Nên quan sát nhiều mẫu liên tiếp với khoảng thời gian phù hợp trước bảo trì.

### 7.3. Election priorities

Không phải mọi secondary đều electable. Member có priority 0, không đủ điều kiện election hoặc có cấu hình đặc biệt không thể thay thế primary theo cách mong muốn.

### 7.4. Hidden/delayed members

Các members ẩn hoặc trì hoãn có mục đích riêng; không tự coi chúng là ứng viên primary. Trước bảo trì cần hiểu votes, priorities và tác động đến quorum.

## 8. Majority và failure budget

Với replica set có N voting members, majority để bầu primary là:

\[
M = \left\lfloor\frac{N}{2}\right\rfloor + 1
\]

Ví dụ:

| Voting members | Majority cần | Số voting members có thể mất mà vẫn còn majority |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

### 8.1. Ví dụ ba voters

~~~text
PRIMARY      healthy
SECONDARY A  healthy
SECONDARY B  healthy
~~~

Nếu dừng B, còn hai voters, majority vẫn có. Nếu dừng tiếp A khi B chưa trở lại, còn một voter, không còn majority để bầu primary.

### 8.2. Quorum không đồng nghĩa đủ dữ liệu

Một voting member có thể tham gia bầu cử nhưng không giữ bản sao dữ liệu đầy đủ theo vai trò, ví dụ arbiter. Một cấu hình còn majority votes chưa chắc có đủ data-bearing nodes để đáp ứng writes/availability như SLA dự kiến.

### 8.3. Majority writes và data durability

Nếu ứng dụng yêu cầu write concern majority, phải kiểm tra còn đủ data-bearing acknowledgements theo cấu hình, không chỉ tính số process alive.

### 8.4. Không đồng thời dừng nhiều voters nếu chưa có kế hoạch cụ thể

Một rolling maintenance chuẩn đợi từng member trở lại healthy/caught-up trước bước kế tiếp.

## 9. Kiểm tra replication lag và oplog window

Một node offline để patch OS, đổi volume hoặc restart sẽ cần bắt kịp các operations được ghi khi nó vắng mặt.

### 9.1. Replication lag

~~~text
Primary latest optime:   T_now
Secondary applied optime: T_now - delta
Replication lag:         delta
~~~

Delta lớn ảnh hưởng tới election readiness và thời gian phục hồi secondary.

### 9.2. Oplog window

Oplog lưu lịch sử operations có giới hạn. Nếu member vắng mặt lâu hơn khả năng lịch sử còn lại, có thể cần **initial sync** thay vì catch up bình thường.

### 9.3. Không dựa vào một ngưỡng cố định

Lag 5 giây có thể chấp nhận với workload này nhưng không với workload khác. Chọn ngưỡng dựa trên write rate, SLO và độ dài maintenance.

### 9.4. Monitoring theo nhiều mẫu

Trước restart, quan sát lag/optime trong một cửa sổ thời gian; khi node trở lại, xác nhận nó tiến về trạng thái SECONDARY và bắt kịp trước khi đi tiếp.

## 10. Kiểm tra tài nguyên hệ thống

Các thành phần đáng kiểm tra:

| Tài nguyên | Câu hỏi |
| --- | --- |
| Disk free | Đủ headroom cho journals, indexes, compaction/maintenance? |
| Disk latency/IOPS | Có bị bão hòa khiến shutdown/startup kéo dài? |
| CPU | Có tải cao kéo dài, election chậm? |
| RAM/WiredTiger cache | Có memory pressure/OOM? |
| Open files/limits | Giới hạn file descriptors đủ? |
| Network | Có packet loss, TLS failures, DNS sai? |
| Time sync | Host clocks đồng bộ theo policy? |
| Filesystem | Volume/persistent mount hoạt động đúng? |
| Backup storage | Có khả năng restore nếu thay đổi thất bại? |
| Host health | Node/VM không đang có disk hardware errors? |

### 10.1. Không bảo trì lớn khi cluster đang bão hòa

Nếu còn một healthy secondary nhưng nó đang chịu tải lớn, stepdown có thể làm tăng latency hoặc trigger failover kéo dài.

### 10.2. Disk gần đầy

Khởi động MongoDB khi volume đầy có thể thất bại hoặc không ổn định. Xử lý capacity trước khi chấp nhận bảo trì.

### 10.3. Metrics dưới quyền được cấp

Một số thông tin cần role như clusterMonitor; không cấp quyền admin rộng chỉ để một probe có thể đọc serverStatus.

## 11. MongoDB serverStatus và monitoring

Với quyền phù hợp:

~~~javascript
db.serverStatus();
~~~

Những nhóm số liệu thường dùng:

- Connections/current/available.
- Opcounters và throughput.
- Memory/cache của WiredTiger.
- Network bytes/requests.
- Operations/cursors.
- Lock contention.
- Replication/election events.
- Read/write concern failures.
- Disk utilization từ OS/cloud metrics.

### 11.1. serverStatus không thay application metrics

Một replica set có vẻ khỏe nhưng API p95 latency đã tăng gấp năm lần thì chưa đạt mục tiêu vận hành.

### 11.2. Baseline trước/sau

Ghi số liệu ít nhất:

~~~text
API p95 latency
MongoDB operation error rate
Replica lag
Election count
Connections current
CPU / disk IOPS / disk free
Queue/CDC lag
Storage/write throughput
~~~

### 11.3. Ghi xu hướng thay vì một điểm

Một spike đơn lẻ sau election có thể chấp nhận, nhưng lag tiếp tục tăng và lỗi writes kéo dài là tín hiệu phải dừng rollout.

## 12. Kiểm tra backup trước khi bảo trì

Trước một thao tác có rủi ro:

1. Xác minh backup gần nhất còn trong retention.
2. Biết recovery point và RPO thật.
3. Xác minh storage location và quyền truy cập.
4. Có encryption key/credentials nếu dùng.
5. Biết quy trình restore trên topology hiện tại.
6. Đối chiếu lịch sử restore drill gần nhất.
7. Xác định khả năng phục hồi cấu hình và secrets.
8. Không dùng backup mới tạo nhưng chưa hoàn thành.

### 12.1. Backup không thay rollback plan

Nếu một config change có thể rollback trong vài phút, đó là nhánh khôi phục khác so với restore toàn cluster từ backup.

### 12.2. Recovery drill là bằng chứng mạnh hơn backup status

Một backup báo thành công nhưng không giải mã hoặc restore được vẫn không bảo vệ ứng dụng.

### 12.3. Replication không phải backup

Xóa nhầm hoặc logical corruption có thể lan sang replicas. Khi bảo trì có thay schema/dữ liệu, backup/PITR là lớp bảo vệ riêng.

## 13. Sẵn sàng ứng dụng trước planned maintenance

Ứng dụng MongoDB nên có:

- Connection string đúng replica set/sharded endpoint.
- Driver phiên bản tương thích server.
- Server discovery/monitoring hoạt động.
- Network timeouts và retry policy phù hợp.
- Định nghĩa hành vi trong vài giây không có primary.
- Idempotency cho các thao tác có thể retry.
- Graceful drain của API/worker instances khi cần.
- Monitoring writes/read failures.
- Cơ chế xử lý change stream resume hoặc resync.

### 13.1. Retry không đồng nghĩa mọi thao tác an toàn

Retryable writes chỉ áp dụng các thao tác/điều kiện được hỗ trợ; multi-step workflows có external side effects vẫn cần idempotency business-level.

### 13.2. Tránh retry storm

Khi primary election xảy ra, nhiều application instances cùng retry tức thời có thể làm tình hình xấu hơn. Dùng backoff/jitter và giới hạn attempts phù hợp.

### 13.3. Đọc từ secondary

Nếu ứng dụng dùng secondary reads, cần kiểm soát consistency và replication lag. Secondary khỏe không nghĩa dữ liệu bằng primary tại mọi thời điểm.

### 13.4. Maintenance window và SLO

Thông báo trước cho các teams và xác định downtime budget. Một rolling restart có thể hạn chế downtime nhưng vẫn có short write interruptions trong primary transition.

## 14. Khởi động mongod: nguyên tắc

MongoDB nên được chạy bằng **cùng service manager/orchestrator** đã dùng để triển khai, không tạo thêm tiến trình ngoài cơ chế quản lý.

Trước khi khởi động xác minh:

- Executable và version phù hợp.
- Config file đúng.
- dbPath/volumes đã mount.
- File permissions và owner đúng.
- Replica set name và member identity.
- TLS certificates/keyfile/authorization.
- Network bindIp, port và firewall.
- Không có mongod khác đang giữ cùng dbPath.
- Disk và journal state phù hợp sau lần dừng trước.

### 14.1. Không khởi động hai mongod trên cùng data directory

Hai processes cùng truy cập dbPath có thể vi phạm locking và làm hỏng môi trường. Nếu service manager đã quản lý mongod, không chạy thêm mongod thủ công bằng config đó.

### 14.2. Mongod có thể cần recovery lúc startup

Sau shutdown bất thường, WiredTiger/storage engine có thể thực hiện recovery trước khi phục vụ requests. Không coi tiến trình chưa ready trong vài giây đầu là lỗi để restart liên tục.

### 14.3. Không xóa lock/journal files như phản xạ

Nếu khởi động lỗi, đọc log và tài liệu phiên bản trước khi xóa bất kỳ file dữ liệu nào. Xóa file tùy tiện có thể làm mất khả năng phục hồi.

## 15. Khởi động và dừng trên Linux systemd

Ví dụ khi mongod được cài và đăng ký dưới unit tên **mongod**:

~~~bash
sudo systemctl status mongod
sudo systemctl start mongod
sudo systemctl stop mongod
sudo systemctl restart mongod
sudo systemctl is-active mongod
~~~

Theo dõi logs:

~~~bash
sudo journalctl -u mongod -n 100 --no-pager
~~~

### 15.1. Tên service có thể khác

Một số deployments dùng tên unit riêng, container hoặc operator. Không tự cho rằng mongod luôn là tên unit trên mọi host.

### 15.2. systemctl restart không tự đảm bảo HA

Nếu target là primary hoặc một member quan trọng của quorum, restart có thể gây election và gián đoạn writes.

### 15.3. Lệnh stop phải có điều kiện

Trước stop:

- Đúng host/cluster?
- Đúng member role?
- Có healthy majority còn lại?
- Có node thay thế/secondary bắt kịp?
- Đã thông báo/drain khi cần?
- Có thể khởi động lại bằng đúng config và volume?

### 15.4. Quan sát startup

Sau start, kiểm tra service active, logs, hello, rs.status và application smoke. Một status active không đủ chứng minh node đã SECONDARY/PRIMARY mong muốn.

## 16. Khởi động thủ công bằng config file

Trong môi trường thử nghiệm có thể chạy:

~~~bash
mongod --config /path/to/mongod.conf
~~~

**Không** dùng lệnh này trên host đang được systemd/container/operator quản lý cùng dbPath.

### 16.1. Vì sao dùng config file?

Một config có thể chứa dbPath, net, replication.replSetName, security, logging và storage options. Bỏ sót một option khi chạy thủ công có thể khiến node khởi động sai vai trò.

### 16.2. Không sao chép config giữa mọi nodes mà không điều chỉnh

Một số fields có thể mang thông tin host/path/port riêng. Bản cấu hình từ node khác chưa chắc hợp lệ.

### 16.3. Kiểm tra file permissions

User chạy mongod phải được phép đọc config, cert/key và ghi dbPath/log. Không chuyển sang chạy root chỉ để “thử cho được” khi chưa xác định rủi ro.

### 16.4. Logs là nguồn chẩn đoán

Phân biệt lỗi config parsing, port already bound, disk full, filesystem permissions, TLS key mismatch và storage recovery.

## 17. Khởi động/dừng trên Windows

Nếu MongoDB được cài như Windows service và tên service là **MongoDB**:

~~~powershell
Get-Service -Name MongoDB
Start-Service -Name MongoDB
Stop-Service -Name MongoDB
Restart-Service -Name MongoDB
~~~

### 17.1. Kiểm tra service name

Tên có thể khác theo cách cài đặt. Dùng danh sách services hoặc trình quản lý dịch vụ để xác định trước.

### 17.2. Không kết hợp service và mongod.exe riêng

Nếu Windows service đang giữ data directory, không mở một mongod.exe thứ hai cùng dbPath.

### 17.3. Xem Windows Event Log và MongoDB log

Nếu startup lỗi, xem logs, config path, service account, file permissions và TLS.

### 17.4. Restart Windows không thay rolling maintenance

Trong replica set, restart OS của một voter cũng làm member offline. Phải tính majority, ứng dụng và trạng thái failover trước khi reboot host.

## 18. MongoDB trong Docker

Ví dụ phát hiện trạng thái container:

~~~bash
docker ps
docker logs --tail 100 mongo-demo
~~~

Dừng có thời gian chờ graceful:

~~~bash
docker stop --time 120 mongo-demo
~~~

Khởi động container đã có:

~~~bash
docker start mongo-demo
~~~

Các tên/container settings là ví dụ.

### 18.1. Persistent storage

Nếu dữ liệu nằm trong writable layer không được quản lý phù hợp, xóa/recreate container có thể làm mất dữ liệu. Cần volumes/persistent storage đúng.

### 18.2. Timeout của docker stop

Nếu MongoDB chưa dừng trước timeout, runtime có thể buộc kill. Chọn grace period theo workload, kích thước dữ liệu và khả năng shutdown; kiểm tra actual exit/health.

### 18.3. Không dùng docker rm như bước restart

docker rm xóa container definition; nếu không có volumes và deployment config đúng, thao tác có thể gây data loss.

### 18.4. Readiness trong container

Container running không bảo đảm replica member đã ready. Healthcheck nên hiểu role và không tự restart member chỉ vì chưa có primary trong một election bình thường.

## 19. MongoDB trên Kubernetes

Với StatefulSet:

~~~bash
kubectl get statefulsets
kubectl get pods -o wide
kubectl describe pod mongo-0
kubectl logs mongo-0 --tail=100
~~~

Đây chỉ là ví dụ về công cụ quan sát, tên resources phải được thay đúng theo deployment.

### 19.1. StatefulSet và persistent volume

Một pod có thể được rescheduled nhưng cần gắn lại PVC đúng identity. Không xóa PVC khi chỉ muốn restart pod.

### 19.2. Rolling update

Nếu có MongoDB Operator, dùng workflow Operator hỗ trợ. Nếu tự quản lý StatefulSet, phải bảo đảm thao tác lần lượt, giữ majority và kiểm tra readiness/replication trước bước tiếp theo.

### 19.3. Liveness và readiness probes

- **Liveness**: process có đang bị treo/không phục hồi?
- **Readiness**: pod có sẵn sàng nhận loại traffic đúng vai trò?
- **Startup probe**: cho phép thời gian khởi động/initial sync dài hơn trước khi liveness có hiệu lực.

Một liveness probe quá hung hăng có thể tạo vòng lặp restart khi mongod đang khôi phục bình thường.

### 19.4. Termination grace period

Kubernetes có thời gian chờ graceful termination. Nếu quá ngắn, runtime có thể kết thúc process trước khi shutdown hoàn tất.

### 19.5. PodDisruptionBudget không thay quorum awareness

PDB giúp giới hạn voluntary disruptions theo Kubernetes, nhưng không tự xác nhận replication lag, electability hoặc trạng thái ứng dụng. DBA/operator vẫn phải giám sát majority.

## 20. MongoDB Atlas và môi trường managed

Trong Atlas hoặc dịch vụ được quản lý, việc start/stop mongod thường là trách nhiệm của control plane.

### 20.1. Không áp dụng systemctl/mongod thủ công

Không SSH rồi tự restart nodes của managed deployment. Dùng các chức năng maintenance/upgrade, monitoring, backup và hỗ trợ chính thức.

### 20.2. Điều cần kiểm tra trước managed maintenance

- Window/timezone đã cấu hình.
- Backup/PITR status.
- Cluster health.
- Application driver compatibility.
- Upgrade target và FCV requirements.
- Tác động tới latency/elections.
- Alerting và communication.
- Search/index readiness khi liên quan.

### 20.3. Dịch vụ không đảm bảo mọi thay đổi zero-downtime

Ngay cả managed rolling maintenance có thể gây transient connection errors, election hoặc latency. Ứng dụng cần retry, idempotency và monitoring.

### 20.4. Cách tạm dừng cluster

Một số managed products có pause/resume hoặc scale-to-zero theo điều kiện riêng. Không mặc định tính năng có ở mọi tier, và không xem pause là tương đương graceful restart một member.

## 21. Dừng mongod theo hướng graceful

Đích đến của graceful shutdown là để MongoDB dừng qua code path được hỗ trợ, đóng connections/tài nguyên và xử lý storage state phù hợp.

Một số cách phụ thuộc môi trường:

- systemctl stop mongod.
- Windows Stop-Service cho MongoDB service.
- Container orchestrator gửi tín hiệu termination theo chính sách.
- Lệnh shutdown server trong mongosh với quyền phù hợp.

Ví dụ khi kết nối trực tiếp tới mongod được phép dừng:

~~~javascript
db.getSiblingDB("admin").shutdownServer();
~~~

### 21.1. Connection bị đóng không nhất thiết là shutdown thất bại

Khi mongod thật sự shutdown, client connection có thể bị ngắt nên shell báo lỗi kết nối. Cần xác minh ở service/process/logs.

### 21.2. Không dùng shutdownServer trên router theo suy đoán

mongos và mongod có yêu cầu quản trị khác nhau. Dùng service manager/orchestrator và tài liệu triển khai chính thức cho router.

### 21.3. Tránh SIGKILL/kill -9

Một stop cưỡng bức bỏ qua quy trình graceful, làm tăng nguy cơ recovery dài và failure khi storage đang hoạt động. Chỉ dùng trong tình huống sự cố chuyên biệt có phê duyệt và runbook.

### 21.4. Không dùng fsyncLock như một nút tạm dừng chung

Các lệnh khóa filesystem backup có semantics riêng; không dùng để “đóng băng database cho dễ restart” nếu không có kế hoạch được hỗ trợ.

## 22. Thứ tự điều phối trước khi dừng

Một sequence gợi ý:

~~~text
Approved maintenance window
         |
         v
Validate cluster + backup
         |
         v
Check majority/replication lag
         |
         v
Notify / drain affected workload
         |
         v
Stop or step down selected member
         |
         v
Perform change
         |
         v
Start member
         |
         v
Wait for topology recovery
         |
         v
Database/app smoke tests
         |
         v
Only then advance to next member
~~~

### 22.1. Drain có nhiều nghĩa

- Với mongos router: ngừng điều phối requests mới tới router sắp dừng.
- Với application: tạm giảm job/requests không phù hợp election.
- Với replica member: bảo đảm member không giữ vai trò primary nếu cần bảo trì.
- Với host: dừng task platform không liên quan có thể tranh tài nguyên.

### 22.2. Không rút toàn bộ traffic thiếu kiểm soát

Draining mọi routers cùng lúc sẽ biến maintenance thành downtime. Giữ đủ endpoints theo SLA.

## 23. Rolling restart trong replica set ba data-bearing members

Giả sử:

~~~text
Node A: PRIMARY
Node B: SECONDARY
Node C: SECONDARY
~~~

Một kế hoạch an toàn hơn restart đồng thời:

1. Kiểm tra A/B/C healthy và lag nhỏ.
2. Chọn C để bảo trì trước.
3. Dừng C gracefully.
4. Thực hiện patch/config change của C.
5. Khởi động C.
6. Chờ C trở lại SECONDARY và bắt kịp.
7. Kiểm tra majority, reads/writes, metrics.
8. Lặp lại với B.
9. Khi A còn là primary, chuẩn bị chuyển primary có kiểm soát.
10. Stepdown A khi có secondary electable/caught-up và thời điểm phù hợp.
11. Xác nhận primary mới và ứng dụng hồi phục.
12. Bảo trì A như một member không còn là primary.
13. Chờ A trở lại healthy/caught-up.
14. Chạy smoke tests toàn diện và đóng maintenance.

### 23.1. Không được suy “Node A sẽ luôn là primary”

Sau elections, roles có thể thay đổi. Mỗi bước phải **đọc lại topology** trước khi chọn target tiếp theo.

### 23.2. Không bảo trì node B khi C còn RECOVERING

Nếu C chưa healthy/caught-up và B bị dừng, failure budget bị thu hẹp hoặc mất.

### 23.3. Election vẫn có thể gây gián đoạn

Một primary transition có thể làm writes lỗi tạm thời, transactions bị retry/abort hoặc connections được driver điều hướng lại. Điều này cần nằm trong kế hoạch truyền thông và app retry.

### 23.4. Secondary priorities và voters ảnh hưởng thứ tự

Không áp dụng nguyên sơ đồ ba data-bearing nodes cho replica set có arbiter, hidden/delayed members, priority 0 hoặc nhiều zones mà không tính quorum/electability.

## 24. Primary stepdown có kiểm soát

Trước khi dừng primary, có thể yêu cầu primary nhường vai trò nếu topology cho phép.

Trên primary với quyền và change approval phù hợp:

~~~javascript
rs.stepDown(60);
~~~

Tham số ví dụ là thời gian stepdown; semantics chi tiết và các tùy chọn catch-up phụ thuộc phiên bản.

### 24.1. Điều kiện trước stepdown

- Có electable secondary đủ cập nhật.
- Majority khỏe.
- Application đã sẵn sàng cho transient errors.
- Không có critical transaction/job không thể retry.
- Có monitoring election và rollback strategy.
- Đã xác nhận đúng primary và window.

### 24.2. Không dùng force stepdown theo mặc định

Nếu không có secondary phù hợp, stepdown thông thường có thể không hoàn thành như mong muốn. Dùng force có thể làm mất khả năng ghi; không ép khi chưa đánh giá và phê duyệt riêng.

### 24.3. Kiểm tra sau stepdown

- Primary mới đã được election.
- Driver đã tìm primary mới.
- Majority writes hoạt động.
- API error rate trở lại bình thường.
- Node cũ đã chuyển vai trò phù hợp.

### 24.4. Không tin response của lệnh một mình

Một primary stepdown có thể làm mất kết nối tới shell. Đọc topology từ một kết nối mới hoặc monitoring thay vì chỉ nhìn return code.

## 25. Những gián đoạn hợp lệ và bất thường trong election

### 25.1. Có thể dự kiến

- Một khoảng ngắn không có primary.
- Một số operations bị retry hoặc trả lỗi có thể retry.
- Latency tăng trong lúc driver server discovery.
- Cursors/transactions dài cần xử lý lại theo semantics.

### 25.2. Không thể mặc định chấp nhận

- Không có primary kéo dài vượt SLO.
- Majority votes mất.
- Secondary replication lag tăng không hồi phục.
- Dữ liệu ghi mất ngoài RPO.
- Application retry storm.
- Access control bị tắt để “cho qua lỗi”.
- Forced reconfig thiếu kiểm soát.

### 25.3. Khi nào dừng rollout?

Nếu election time, error rate, p95 latency hoặc replication lag vượt ngưỡng đã định, không tiến tới member tiếp theo. Xác định nguyên nhân trước.

## 26. Khi replica set chỉ có hai voters

Với hai voting members, majority là hai.

~~~text
PRIMARY   voter
SECONDARY voter
~~~

Dừng một voter khiến không còn majority cho election/majority availability trong các tình huống tương ứng.

### 26.1. Rolling restart không tự an toàn

Đừng lấy quy trình ba voters áp dụng y nguyên. Cần thiết kế topology với failure budget phù hợp hoặc có maintenance window chấp nhận downtime.

### 26.2. Arbiter là giải pháp có trade-off

Một cấu hình primary/secondary/arbiter có quorum election khác, nhưng arbiter không giữ dữ liệu và có hạn chế với durability/majority writes. Cần đánh giá kỹ, không thêm arbiter chỉ để “cho phép restart” thiếu tính toán.

### 26.3. Một voter không thể tự tạo HA

Standalone hoặc một voter không có dư địa failover tự động trước khi lên kế hoạch bổ sung replication/topology.

## 27. Sharded cluster: nhìn đủ các tầng

Sharded cluster có:

- Config Server Replica Set (CSRS).
- Một hoặc nhiều shard replica sets.
- Một hoặc nhiều mongos routers.
- Balancer và chunk migration mechanisms.

### 27.1. Không bảo trì toàn cluster bằng một lệnh restart chung

Nếu cùng dừng nhiều shard members hoặc config voters, cluster có thể mất routing hoặc quorum.

### 27.2. Bảo trì từng replica set

Trong mỗi shard và CSRS, áp dụng nguyên tắc giữ majority và chờ member trở lại healthy trước khi dừng member tiếp theo.

### 27.3. Mongos router là lớp khác

Nếu có nhiều mongos sau load balancer, có thể drain và restart tuần tự để giảm tác động. Nếu chỉ một mongos, dừng nó gây gián đoạn ứng dụng dù shards vẫn khỏe.

### 27.4. Config servers là thành phần trọng yếu

Lỗi config server majority có thể ảnh hưởng cluster metadata và operations. Không coi việc dừng config server chỉ giống dừng một router.

### 27.5. Thứ tự nâng cấp/bảo trì theo version

Các MongoDB major-version upgrade procedures có thứ tự riêng cho CSRS, shard replica sets, mongos và FCV. Phải tuân theo **official upgrade procedure của source/target versions**, không dùng một thứ tự cố định cho mọi releases.

## 28. Balancer và chunk migrations khi bảo trì sharded cluster

Các hoạt động balancing/chunk migration có thể làm tăng I/O/network hoặc ảnh hưởng tính nhất quán vận hành trong một số thay đổi.

### 28.1. Có phải lần nào cũng tắt balancer?

**Không.** Phụ thuộc loại thay đổi và tài liệu của phiên bản MongoDB. Một số quy trình yêu cầu dừng balancing hoặc đợi migrations hoàn tất; một số quy trình không cần.

### 28.2. Ghi trạng thái ban đầu

Nếu một runbook yêu cầu thay đổi balancer state, ghi trạng thái trước để cuối cùng chỉ khôi phục khi vốn đã bật.

### 28.3. Ví dụ lệnh mang tính môi trường

Trên mongos, với quyền phù hợp, các helper quản trị như:

~~~javascript
sh.status();
~~~

và khi runbook đã yêu cầu:

~~~javascript
sh.stopBalancer();
~~~

sau đó khôi phục theo trạng thái đã ghi:

~~~javascript
sh.startBalancer();
~~~

Các helpers/semantics có thể khác theo phiên bản; cần xác minh migration activity đã kết thúc theo tài liệu trước khi bảo trì. **Không tự dừng balancer trên production chỉ vì thấy một ví dụ.**

### 28.4. Không quên bật lại chức năng đã tạm dừng

Một môi trường có balancer bị tắt lâu sau bảo trì có thể tích lũy phân bố dữ liệu không cân bằng.

## 29. Bảo trì mongos router

Một kế hoạch khi có nhiều routers:

1. Kiểm tra các mongos endpoints còn khỏe.
2. Xác định router cụ thể cần bảo trì.
3. Drain nó khỏi load balancer hoặc service discovery.
4. Chờ in-flight requests theo policy.
5. Stop router bằng service manager.
6. Patch/config/start router.
7. Verify routing/auth/TLS và các API mẫu.
8. Đưa router trở lại pool.
9. Theo dõi error rate.
10. Chỉ sau đó chuyển sang router khác.

### 29.1. Không restart tất cả mongos cùng lúc

Ứng dụng có thể mất đường routing dù shards còn khỏe.

### 29.2. Router stateless không có nghĩa không cần drain

Đang có connections/cursors/transactions đi qua mongos có thể bị gián đoạn. Driver/application cần retry đúng và load balancer drain theo kế hoạch.

### 29.3. Connection strings

Clients kết nối sharded cluster nên theo endpoints chính thức của deployment. Không tự chuyển application trỏ trực tiếp tới một shard để “bypass mongos”.

## 30. Bảo trì đi kèm nâng cấp MongoDB

Bảo trì nâng cấp có nhiều lớp thay đổi:

- MongoDB binary version.
- Database Tools/drivers.
- OS packages/kernel.
- TLS certificates và crypto config.
- Storage volumes.
- Replica set configuration.
- FCV.
- Schema/index/data migrations.

### 30.1. Không gộp quá nhiều thay đổi không liên quan

Nếu cùng lúc đổi OS, MongoDB major version, driver, auth và index schema, việc rollback/chẩn đoán trở nên rất khó. Nên tách các bước trừ khi compatibility yêu cầu phối hợp.

### 30.2. Kiểm tra compatibility matrix

Trước khi lên version:

- Supported upgrade path.
- FCV requirements.
- Driver/driver feature compatibility.
- Sharded/replica set topology support.
- Operating system compatibility.
- Deprecated commands/settings.
- Authentication/TLS support.
- Backup/restore tooling compatibility.

### 30.3. Binaries và FCV là hai bước khác

Một rolling binary upgrade có thể giữ FCV cũ trong giai đoạn chuyển tiếp theo tài liệu. Đổi FCV sớm có thể bật features khiến downgrade khó hoặc không còn được hỗ trợ.

### 30.4. Plan rollback trước khi đổi FCV

Không coi downgrade là thao tác restart với binary cũ. Có release-specific constraints, dữ liệu có thể chứa features mới hoặc schema mới.

## 31. Graceful shutdown không xóa được mọi rủi ro

Graceful shutdown giúp database dừng hợp lệ, nhưng:

- Client connections vẫn bị đóng.
- Long-running operations có thể bị gián đoạn.
- Primary transition có thể tạo khoảng không có writes.
- Jobs/transactions cần xử lý retry.
- CDC consumers có thể cần resume.
- Backups/index builds có thể bị ảnh hưởng.

### 31.1. Shutdown duration không cố định

Thời gian phụ thuộc tải, storage engine, I/O và môi trường. Service manager có timeout cần đủ cho shutdown bình thường.

### 31.2. Đừng đặt kill timeout quá ngắn

Nếu runtime gửi forced termination trước khi server xong graceful shutdown, startup recovery sau đó có thể lâu hơn.

### 31.3. Không tin log một dòng duy nhất

Theo dõi service exit, process status, logs và readiness khi trở lại.

## 32. Khởi động lại: kiểm tra recovery và role

Sau một restart:

1. Process chạy bằng binary/config dự kiến.
2. Không có startup fatal errors.
3. Disk mount và permissions đúng.
4. TLS/auth hoạt động.
5. hello phản hồi.
6. Member vào đúng replica set.
7. Replica state trở về SECONDARY/PRIMARY phù hợp.
8. Replication lag trở về ngưỡng.
9. Majority và writable primary ổn định.
10. Required application reads/writes pass.

### 32.1. Một SECONDARY đang STARTUP2 không ready như SECONDARY ổn định

Initial sync hoặc recovery có thể còn diễn ra. Không tính member đó như một secondary đã bắt kịp chỉ vì process live.

### 32.2. Node mới khởi động có thể chịu tải sync

Theo dõi disk/network và ảnh hưởng lên primary/secondary sync source.

### 32.3. Chờ trước bước tiếp theo

Maintenance tool/orchestrator cần một gate đo thực tế, không chỉ sleep cố định 30 giây.

## 33. Database smoke tests sau từng node

Một bộ kiểm tra nhẹ từ ứng dụng hoặc mongosh:

~~~javascript
db.adminCommand({ ping: 1 });
~~~

Trên database test phù hợp:

~~~javascript
db.getSiblingDB("ops_smoke")
  .validation
  .findOne({ _id: "known-test-record" });
~~~

### 33.1. Read probe dùng dữ liệu test

Nên có record test/tenant xác định. Không query dữ liệu nhạy cảm rồi đưa kết quả vào logs.

### 33.2. Write probe

Nếu cần chứng minh writes, dùng collection/record test trên target được phép và dọn cleanup:

~~~javascript
const coll = db.getSiblingDB("ops_smoke").validation;

coll.updateOne(
  { _id: "maintenance-probe-001" },
  {
    $set: {
      checkedAt: new Date(),
      purpose: "maintenance-smoke"
    }
  },
  { upsert: true }
);

coll.findOne({ _id: "maintenance-probe-001" });

coll.deleteOne({ _id: "maintenance-probe-001" });
~~~

### 33.3. Không dùng test writes vào production không được duyệt

Chạy probe writes có thể tạo audit events, triggers, change streams và side effects. Chỉ dùng khi có scope và policy rõ.

### 33.4. App-level smoke quan trọng hơn mongosh admin test

Ứng dụng với least-privilege credentials có thể fail dù admin ping và insert được.

## 34. Kiểm tra readConcern/writeConcern theo ứng dụng

MongoDB operations có read/write concern khác nhau.

### 34.1. Majority write readiness

Một ứng dụng yêu cầu majority writes cần đảm bảo topology còn đáp ứng write concern đó sau khi member bị dừng.

### 34.2. Secondary read readiness

Read preference secondary có thể khiến ứng dụng đọc dữ liệu lag hoặc mất read endpoint trong rolling maintenance. Không chỉ kiểm tra primary.

### 34.3. Causal consistency

Những workflows phụ thuộc read-your-writes hoặc causal consistency cần kiểm tra theo driver/session configuration.

### 34.4. Transactions

Primary stepdown có thể ngắt in-flight transactions. Ứng dụng cần xử lý lỗi transient transaction theo hướng dẫn driver, không retry toàn bộ business side effects thiếu idempotency.

## 35. Change Streams, job queues và scheduled tasks

Maintenance có thể làm mongod connections/streams gián đoạn.

### 35.1. Change Streams

Consumers cần xử lý reconnect/resume tokens. Nếu maintenance kéo dài vượt oplog window hoặc topology có thay đổi đặc biệt, có thể cần resync.

### 35.2. Scheduled jobs

Một worker xử lý 1.000 records dở dang cần có checkpoint/idempotency thay vì bắt đầu lại thiếu kiểm soát.

### 35.3. Outbox pattern

Nếu một event được commit nhưng email/payment chưa xử lý, restart workers có thể replay. Nên dùng idempotency keys.

### 35.4. Tạm dừng jobs theo plan

Một số maintenance cần pause batch jobs có tải nặng hoặc nhạy cảm, nhưng không mặc định cần stop mọi consumers. Xem tác động queue lag và SLA.

### 35.5. Resume sau khi database ready

Không mở lại jobs gây tác dụng phụ trước khi hệ thống chính có consistency/readiness phù hợp.

## 36. Kiểm soát backup và snapshots đang chạy

Nếu một snapshot/backup đang hoạt động:

- Xác định có được phép restart node theo tài liệu dịch vụ không.
- Đánh giá snapshot consistency khi có writes.
- Kiểm tra nguồn backup và retention.
- Không dừng/gián đoạn backup chỉ để rút ngắn maintenance mà không có chủ sở hữu quyết định.
- Ghi những backup windows bị ảnh hưởng.

### 36.1. Backup can overlap maintenance?

Tùy công nghệ. Một số hoạt động có thể cùng tồn tại, một số phải tránh để giảm tải hoặc bảo đảm tính nhất quán.

### 36.2. Không suy snapshot success bằng dữ liệu chưa kiểm tra

Trong một thay đổi có nguy cơ cao, evidence từ restore drill/backup validation mang nhiều giá trị hơn một cờ success mới xuất hiện.

## 37. Các bước của một planned maintenance runbook

### Giai đoạn A — PREPARE

1. Thông báo change ID, mục tiêu, thời gian.
2. Xác định owner, incident commander, rollback approver.
3. Chốt phạm vi, node order và dependencies.
4. Chốt baseline metrics và expected error budget.
5. Kiểm tra backup/restore readiness.
6. Đánh giá compatibility/config diff.
7. Kiểm tra primary/quorum/lag.
8. Chuẩn bị smoke tests và alert dashboards.
9. Xác nhận stop/go criteria.

### Giai đoạn B — EXECUTE

1. Revalidate topology trước mỗi node.
2. Drain traffic hoặc giảm workload có kiểm soát.
3. Stepdown primary khi cần và đủ điều kiện.
4. Graceful stop đúng target.
5. Thực hiện thay đổi theo change script.
6. Start bằng cùng manager/orchestrator.
7. Chờ role/replication/index readiness.
8. Smoke test database/application.
9. So error rates/metrics với baseline.
10. Chỉ tiếp tục nếu pass.

### Giai đoạn C — VERIFY

1. Tất cả members healthy.
2. Primary/majority ổn định.
3. Replication lag trong ngưỡng.
4. Required reads/writes hoạt động.
5. API error rate và p95 trở lại SLO.
6. Change streams/jobs hồi phục.
7. Backups, search và file references không bị ảnh hưởng.
8. Trạng thái balancer/routers đúng ban đầu khi liên quan.

### Giai đoạn D — CLOSE

1. Ghi start/end/election/cutover timestamps.
2. Cập nhật change record.
3. Lưu logs/evidence đã loại secrets/PII.
4. Ghi deviations và incidents.
5. Mở follow-up actions.
6. Kết thúc maintenance mode và thông báo.

## 38. Bảng gate theo từng bước

| Gate | Trước stop | Sau start |
| --- | --- | --- |
| Đúng cluster/host | Bắt buộc | Đối chiếu lại |
| Quorum còn đủ | Bắt buộc | Bắt buộc |
| Secondary caught up | Với election plan | Bắt buộc trước node kế |
| Disk free và mounts | Bắt buộc | Bắt buộc |
| TLS/auth | Có baseline | Test lại |
| Service running | Đang healthy | Running |
| MongoDB role | Được ghi lại | Ổn định |
| Application error rate | Trong giới hạn | Trở về baseline |
| Writes/read probes | Baseline pass | Pass |
| Backup restore path | Available | Vẫn available |
| Rollback | Ready | Chỉ dùng nếu đúng điều kiện |

### 38.1. Một gate fail thì sao?

Không tự động tiếp tục. Dừng rollout, đánh giá impact, phục hồi member hoặc rollback theo runbook.

### 38.2. Timeout

Đặt timeout hợp lý cho start, replication catch-up và elections theo topology. Timeout không phải lý do để force thành công bằng cách bỏ check.

## 39. Abort criteria và rollback

Một kế hoạch phải nêu trước những tín hiệu dừng:

- Một member không start được.
- Quorum có nguy cơ mất.
- Primary election vượt thời gian cho phép.
- Replication lag tiếp tục tăng.
- API error rate vượt threshold.
- p95 latency vượt SLO kéo dài.
- Backup/restore safety condition bị mất.
- Có data inconsistencies.
- Storage corruption hoặc auth/TLS error nghiêm trọng.
- Unexpected schema/FCV change.

### 39.1. Rollback config

Nếu thay một config option và node không start, có thể đưa config về bản đã xác minh, nhưng phải chắc rằng thay đổi không tạo ra trạng thái dữ liệu mới không tương thích.

### 39.2. Rollback binaries

Chỉ downgrade nếu **được MongoDB version documentation hỗ trợ** và các điều kiện FCV/data features cho phép. Không tự cài binary cũ rồi restart.

### 39.3. Không force reconfig để “cứu quorum” thiếu đánh giá

Force reconfig có thể tăng rủi ro mất dữ liệu hoặc tách não. Đây là thao tác xử lý sự cố chuyên biệt cần người chịu trách nhiệm và runbook riêng.

### 39.4. Backup restore khác rollback nhanh

Một restore toàn dữ liệu mất thời gian và có thể mất writes sau recovery point. Chọn nhánh phục hồi phải xét RPO/RTO và hậu quả nghiệp vụ.

## 40. Maintenance khi ứng dụng có tải cao

### 40.1. Chọn maintenance window

Dựa trên:

- Traffic theo giờ.
- Batch jobs, billing cycles.
- Backup windows.
- Customer SLA.
- Các chiến dịch/peak events.
- Cross-region timezone.
- Workload thay đổi đột biến.

### 40.2. Rate limit và drain

Có thể giảm workload batch, pause migrations ứng dụng hoặc điều chỉnh load balancer, nhưng tránh thay đổi nhiều knobs ngoài kế hoạch.

### 40.3. Bảo trì không đồng nghĩa luôn phải downtime

Replica set/sharded cluster có thể được bảo trì theo rolling strategy, nhưng transient errors vẫn có thể xuất hiện. Đừng hứa “zero downtime” nếu chưa kiểm chứng driver và topology.

### 40.4. Planned maintenance vs emergency maintenance

Sự cố khẩn cấp có thể yêu cầu rút ngắn approvals nhưng vẫn nên có minimum safety gates: đúng target, quorum, khả năng backup/recovery, người điều phối và logs.

## 41. Cách xử lý khi mongod không khởi động

Một runbook chẩn đoán:

1. Kiểm tra process/service exit code.
2. Đọc logs gần nhất.
3. Xác nhận config path và syntax.
4. Kiểm tra dbPath/volume mounts/permissions.
5. Kiểm tra port và bind address.
6. Kiểm tra TLS/keyfile và certificates.
7. Kiểm tra disk free/inodes.
8. Kiểm tra MongoDB binary/FCV compatibility.
9. Kiểm tra storage recovery errors.
10. Xác định có member khác đang dùng cùng dữ liệu không.
11. Dừng rollout nếu quorum bị ảnh hưởng.
12. Escalate trước các thao tác sửa file dữ liệu hoặc reconfig.

### 41.1. Không xóa WiredTiger/journal files thiếu hướng dẫn

Việc xóa file storage tùy tiện có thể phá hủy khả năng recovery.

### 41.2. Không tự chạy mongod --repair trên production

Repair có mục đích và rủi ro riêng, không phải thao tác restart thông thường. Phải có backup và quy trình cụ thể khi được hỗ trợ.

### 41.3. Startup recovery có thể mất thời gian

Khởi động sau abrupt shutdown có thể cần recovery; logs là nguồn thông tin để phân biệt đang tiến triển với bị treo.

### 41.4. Kubernetes CrashLoopBackOff

Đừng chỉ tăng liveness timeout để che lỗi disk/auth/config. Kiểm tra actual process logs và volume state.

## 42. Khi không còn primary

Điều tra theo thứ tự:

- Có healthy voting majority không?
- Network partition hay DNS/TLS lỗi?
- Members đang trạng thái nào?
- Secondary nào electable?
- Lag và sync state ra sao?
- Có ongoing upgrade/reconfig không?
- Application đang kết nối đúng replica set endpoints không?

### 42.1. Không chỉ restart tất cả nodes

Restart đồng thời có thể làm tình hình khó đoán, kéo dài recovery và phá evidence.

### 42.2. Không force election/reconfig mặc định

Nếu majority mất, cần khôi phục members/network hoặc thực hiện disaster-recovery procedure được phê duyệt, không ép data loss khi chưa đánh giá.

### 42.3. Ghi election logs

Các dấu hiệu heartbeat timeout, auth mismatch, quorum loss và replication lag giúp xác định nguyên nhân.

## 43. Sau maintenance: ứng dụng trả lỗi kết nối

Một số nguyên nhân:

- Primary vừa đổi nhưng driver chưa phát hiện.
- Connection URI thiếu replica set hosts.
- Service account bị đổi credentials.
- TLS CA/cert mismatch.
- DNS/hostnames sai.
- Network allowlist khác.
- Connection pool cũ.
- Driver không tương thích.
- Router mongos bị drain chưa mở lại.

### 43.1. Không sửa bằng cách tắt authorization/TLS

Lỗi auth/TLS cần sửa credentials/cert/config đúng, không hạ bảo mật để “khởi động cho nhanh”.

### 43.2. Kiểm tra driver logs và SDAM events

Driver server discovery/monitoring có thể cho biết primary transition, network failures và server selection timeouts.

### 43.3. Client retry behavior

Cần phân biệt retryable failures, non-retryable failures và operations có thể gây side effects ngoài MongoDB.

## 44. Java application: kiểm tra readiness cơ bản

Ví dụ ứng dụng Java Sync Driver đọc ping qua MongoClient.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

public class MongoReadinessProbe {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGODB_URI"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            Document reply = client
                    .getDatabase("admin")
                    .runCommand(new Document("ping", 1));

            System.out.println(reply.toJson());
        }
    }
}
~~~

### 44.1. Đây chỉ là connectivity probe

Ping không xác nhận writable primary, majority, indexes hoặc các business rules.

### 44.2. Không khởi tạo MongoClient mới cho mỗi HTTP request

MongoClient thường được giữ và tái sử dụng theo vòng đời ứng dụng để tận dụng connection pooling và server discovery.

### 44.3. Phân quyền ít nhất

Health probe không cần admin quyền ghi dữ liệu; sử dụng access thích hợp cho ping và readiness checks theo thiết kế.

### 44.4. Không log MONGODB_URI

Connection string có thể chứa credentials, không in nguyên vào logs.

## 45. Java application: business-level smoke test

Sau restart, ứng dụng có thể dùng một test collection/tenant được phép để kiểm tra round trip:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import org.bson.Document;

import java.util.Date;

public class MongoSmokeTest {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGODB_URI"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> coll =
                    client.getDatabase("ops_smoke")
                          .getCollection("validation");

            String id = "maintenance-smoke-001";

            coll.replaceOne(
                    Filters.eq("_id", id),
                    new Document("_id", id)
                            .append("checkedAt", new Date())
                            .append("purpose", "maintenance"),
                    new ReplaceOptions().upsert(true)
            );

            Document readback = coll.find(
                    Filters.eq("_id", id)
            ).first();

            if (readback == null) {
                throw new IllegalStateException(
                        "Write/read smoke test failed"
                );
            }

            coll.deleteOne(Filters.eq("_id", id));

            System.out.println("PASS");
        }
    }
}
~~~

### 45.1. Chỉ chạy với quyền/scope hợp lệ

Đây là test ghi và xóa. Chỉ dùng trên môi trường được phép và không gây side effects không mong muốn từ change streams/triggers.

### 45.2. Không chỉ chạy test bằng admin credentials

Dùng application account và write/read concerns phù hợp để phát hiện lỗi phân quyền/thực thi nghiệp vụ.

### 45.3. Khả năng chạy sau failover

Ứng dụng có thể cần retry kết nối/operations theo driver semantics. Không thêm retry không giới hạn mà không có timeout và idempotency.

## 46. Kiểm tra index và query performance sau maintenance

Một restart bình thường không nhằm thay đổi index definitions, nhưng nâng cấp/config/index maintenance có thể ảnh hưởng query behavior.

Ví dụ:

~~~javascript
db.orders.getIndexes();
~~~

Query mẫu:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "confirmed"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

### 46.1. Quan sát executionStats

- Có dùng index dự kiến?
- Có COLLSCAN ngoài kế hoạch?
- Có blocking SORT?
- totalDocsExamined và totalKeysExamined?
- Execution time biến động như thế nào?

### 46.2. Cold cache

Lần truy vấn đầu sau restart có thể chậm do WiredTiger cache chưa warm. So sánh dưới điều kiện tương đương.

### 46.3. Search/Vector Search

Nếu ứng dụng phụ thuộc index ngoài BSON như Atlas Search, kiểm tra readiness và queries mẫu riêng. Không coi CRUD sẵn sàng là Search sẵn sàng.

## 47. Diễn tập planned maintenance trên môi trường thử

Một bài thực hành có thể thiết kế replica set ba data-bearing nodes:

~~~text
A: PRIMARY
B: SECONDARY
C: SECONDARY
~~~

Thực hiện trên lab được phép:

1. Ghi primary hiện tại, member states, baseline lag.
2. Tạo một test record.
3. Dừng C gracefully qua service manager.
4. Quan sát majority/ứng dụng.
5. Start C.
6. Chờ C trở lại SECONDARY/caught-up.
7. Kiểm tra test record tồn tại.
8. Lặp lại cho B.
9. Chuẩn bị primary stepdown theo plan.
10. Kiểm tra primary mới và application writes.
11. Restart old primary nếu đủ điều kiện.
12. Kết thúc với tất cả members healthy.
13. Ghi election duration, API errors và observed lag.
14. Đối chiếu với SLO.

### 47.1. Không coi lab và production giống nhau

Production có mạng, workload, index/data size, backups và dependencies khác. Ghi giới hạn mô phỏng.

### 47.2. Quan sát thay vì chỉ chạy lệnh

Kết quả bài thực hành là evidence của health transitions và các điều kiện pass/fail, không chỉ danh sách commands.

## 48. Báo cáo maintenance tối thiểu

Một mẫu giả định:

~~~yaml
maintenanceId: "MONGO-MAINT-2026-11-14-01"
environment: "staging"
cluster: "mongodb-rs-example"
changeType: "rolling-service-restart"
windowUtc:
  start: "2026-11-14T02:00:00Z"
  end: "2026-11-14T03:00:00Z"
preflight:
  majorityHealthy: true
  secondariesCaughtUp: true
  backupAvailable: true
  applicationSmokeBaseline: "PASS"
steps:
  - member: "mongo-c"
    beforeRole: "SECONDARY"
    afterRole: "SECONDARY"
    result: "PASS"
  - member: "mongo-b"
    result: "PASS"
  - member: "mongo-a"
    result: "PASS"
postflight:
  primaryElected: true
  replicationLagWithinLimit: true
  applicationReadWriteSmoke: "PASS"
  p95LatencyWithinSlo: true
decision: "COMPLETED"
issues: []
~~~

Các giá trị đều minh họa.

### 48.1. Bằng chứng cần lưu

- Change/ticket ID và owner.
- Before/after topology snapshots.
- Backup/recovery evidence.
- Logs khi start/stop/election.
- Node versions/config changes.
- Replication lag/metrics timeline.
- Application smoke outputs.
- Abort/rollback decisions nếu có.

### 48.2. Loại bỏ secrets/PII

Không đính kèm mật khẩu, private keys, raw connection URIs hoặc dữ liệu người dùng không cần thiết.

### 48.3. Follow-up actions

Một sự kiện recovery chậm hoặc tăng latency cần có owner, deadline và hành động cụ thể.

## 49. Các lỗi vận hành thường gặp

| Sai lầm | Hậu quả |
| --- | --- |
| Service active được xem là ready | Bỏ sót election/auth/data errors |
| Chỉ ping trước bảo trì | Không biết quorum/lag |
| Restart mọi members cùng lúc | Mất majority/downtime |
| Bảo trì secondary tiếp khi node trước chưa caught-up | Thu hẹp failure budget |
| Dừng primary không xét electable secondary | Election thất bại |
| Force stepdown/reconfig thiếu đánh giá | Mất availability hoặc data |
| Không kiểm tra backup | Không có recovery path đáng tin |
| Replication được xem là backup | Không cứu xóa nhầm |
| Không tính oplog window | Secondary cần initial sync |
| Không xác nhận cluster target | Thao tác nhầm production |
| Chạy mongod hai lần cùng dbPath | File locking/data risk |
| Xóa journal/storage files khi startup lỗi | Mất khả năng recovery |
| Kill -9 dùng thay graceful stop | Recovery dài, tăng rủi ro |
| systemctl restart trên primary thiếu plan | Write interruption |
| Docker stop timeout quá ngắn | Forced termination |
| Xóa PVC khi restart pod | Mất persistent data |
| Liveness probe quá hung hăng | CrashLoop |
| Nghĩ PDB đảm bảo Mongo quorum | Không kiểm tra votes/data health |
| Dừng mọi mongos cùng lúc | Ứng dụng mất router |
| Bỏ quên config server majority | Sharded cluster operations lỗi |
| Tắt balancer rồi không bật lại | Shard imbalance |
| Đổi FCV chung với restart | Downgrade không còn đơn giản |
| Không kiểm tra driver retry | Transient errors thành outage |
| Retry side effects không idempotent | Trùng payment/email |
| Không theo dõi change streams | Event loss/duplicate |
| Không warm/check indexes | API p95 tăng kéo dài |
| Smoke test chỉ bằng admin user | Bỏ lỗi app permissions |
| Bỏ lỗi vì service có vẻ online | Không đủ business readiness |
| Rollback binary tùy ý | Incompatibility/corruption risk |
| Không có stop/go criteria | Rollout tiếp dù cluster bất ổn |
| Không ghi timeline/evidence | Khó audit và cải tiến |

## 50. Bài tập về readiness

### Bài 1 — Process và database readiness

Một service mongod active, nhưng rs.status không có PRIMARY. Có thể đánh dấu application writable không? Cần kiểm tra gì?

### Bài 2 — Ping success

mongosh ping trả ok:1 nhưng API tạo booking timeout. Liệt kê ít nhất sáu nguyên nhân không được phát hiện chỉ bằng ping.

### Bài 3 — Four-layer readiness

Thiết kế bốn tín hiệu liveness, database readiness, application readiness và maintenance readiness cho replica set có ba voters.

### Bài 4 — Secondary lag

Secondary B đang lag 10 phút. Có nên stepdown primary A để bảo trì ngay không? Vì sao?

### Bài 5 — Oplog

Node C offline lâu hơn oplog window. Khi quay lại, điều gì có thể xảy ra? Tác động tới maintenance duration?

### Bài 6 — Health threshold

Chọn ngưỡng p95 latency, error rate, replication lag và disk free cho một ứng dụng có yêu cầu cao; giải thích tại sao cần dựa trên baseline/SLO chứ không có một con số chung.

## 51. Bài tập về quorum và replica set

### Bài 7 — Majority

Tính majority cho replica sets có 1, 2, 3, 4, 5 và 7 voting members.

### Bài 8 — Ba voters

A/B/C khỏe. Dừng C, sau đó B bị lỗi trước khi C trở lại. Điều gì xảy ra với majority và writes?

### Bài 9 — Arbiter

Một replica set gồm primary, secondary và arbiter. Vì sao arbiter giúp voting nhưng không thay một data-bearing secondary về durability?

### Bài 10 — Rolling restart

Viết runbook cho A PRIMARY, B/C SECONDARY; nêu gate sau mỗi node và kế hoạch stepdown A.

### Bài 11 — Node roles thay đổi

Sau restart B, A không còn PRIMARY. Vì sao không nên tiếp tục lệnh restart dựa trên danh sách roles lúc bắt đầu?

### Bài 12 — Force stepdown

Một primary không chịu stepdown vì không có secondary phù hợp. Tại sao không chọn force theo mặc định?

## 52. Bài tập về môi trường triển khai

### Bài 13 — systemd

Trên lab, dùng systemctl status/start/stop và journalctl để quan sát mongod. Phải kiểm tra gì ngoài trạng thái active?

### Bài 14 — Windows

Một MongoDB Windows service lỗi start vì service account không đọc được keyfile. Cách xác minh/corrective action là gì?

### Bài 15 — Docker

Container bị xóa/recreate và dữ liệu biến mất. Vấn đề thiết kế volume có thể là gì?

### Bài 16 — Kubernetes

Một StatefulSet pod đang initial sync nhưng liveness probe restart liên tục. Hãy cải tiến startup/liveness/readiness và termination settings.

### Bài 17 — Atlas

Vì sao không áp dụng systemctl hoặc mongod --config trực tiếp cho Atlas managed cluster? Cần theo dõi điều gì trong maintenance window?

### Bài 18 — Một mongos duy nhất

Sharded cluster có ba shards khỏe nhưng chỉ một mongos. Nếu dừng router này, ứng dụng gặp lỗi gì?

## 53. Bài tập về bảo trì sharded cluster

### Bài 19 — Config server majority

Config Server Replica Set có ba members. Một member đang down; team muốn restart member thứ hai. Phân tích rủi ro và Go/No-Go.

### Bài 20 — Balancer

Một runbook yêu cầu tạm dừng balancer. Cần ghi những gì trước/ sau để tránh quên bật lại hoặc làm gián đoạn migrations?

### Bài 21 — Shard restart

Bảo trì secondary shard A rồi secondary shard B cùng lúc để nhanh hơn có an toàn không? Những quorum domains nào phải xem?

### Bài 22 — mongos rolling

Thiết kế router drain/restart/verify trong cluster có bốn mongos sau load balancer.

### Bài 23 — Upgrade và FCV

Vì sao binary upgrade và setFeatureCompatibilityVersion cần kế hoạch riêng? Rollback có giới hạn gì?

## 54. Bài tập về ứng dụng và khôi phục lỗi

### Bài 24 — Retry storm

Primary election khiến 200 API instances retry ngay tức khắc. Các biện pháp giới hạn retry/backoff/idempotency là gì?

### Bài 25 — Transaction abort

Một transaction booking bị ngắt khi primary stepdown. Thiết kế lỗi/retry để không tạo hai đơn hàng hoặc thanh toán trùng.

### Bài 26 — Change Stream

Consumer không resume được sau maintenance dài. Hãy đề xuất quy trình checkpoint/resync/dedup.

### Bài 27 — CrashLoop

mongod không khởi động sau restart. Viết danh sách logs/config/storage/TLS checks trước khi can thiệp dữ liệu.

### Bài 28 — No primary

Replica set mất primary sau khi restart một member. Vì sao không nên restart toàn bộ nodes? Phải điều tra những tín hiệu nào?

### Bài 29 — Smoke test

Viết Java Sync Driver ping và một read/write smoke test trên dataset staging; trình bày giới hạn của từng phép thử.

### Bài 30 — Abort

Bảo trì node đầu thành công nhưng replication lag tăng liên tục và API p95 vượt SLO. Quyết định bước tiếp theo? Vì sao?

## 55. Checklist vận hành ngắn gọn

### Trước thay đổi

1. Đúng environment/cluster/host/member identity.
2. Window và change approval rõ.
3. Topology, version, role inventory được ghi.
4. Có healthy quorum/majority.
5. Có secondary electable/caught-up nếu cần stepdown.
6. Lag, oplog window và disk headroom đạt yêu cầu.
7. Backup/PITR và restore procedure khả dụng.
8. Driver/application retry behavior được xác nhận.
9. Monitoring, alerts và smoke tests sẵn sàng.
10. Abort/rollback approver và stop conditions rõ.

### Trong thay đổi

11. Drain traffic/workload cần thiết.
12. Dừng gracefully qua manager/orchestrator phù hợp.
13. Không stop quá nhiều voters/routers cùng lúc.
14. Không sửa trực tiếp storage/journal files.
15. Không force election/reconfig thiếu phê duyệt.
16. Chờ member trở lại role healthy và bắt kịp.
17. Test majority reads/writes và ứng dụng.
18. Ghi time/events trước bước tiếp theo.

### Sau thay đổi

19. Primary/majority ổn định.
20. Replication lag trở về ngưỡng.
21. Tất cả members đúng role và version dự kiến.
22. Authentication/TLS và quyền ứng dụng hoạt động.
23. API latency, error rate, throughput đạt SLO.
24. Change streams, queues và jobs đã hồi phục.
25. mongos/balancer và search indexes ở trạng thái cần thiết.
26. Backups/alerts không bị vô hiệu hóa.
27. Bằng chứng logs, metrics, smoke tests được lưu.
28. Hành động tiếp theo có owner/deadline.

## 56. Mẫu runbook bảo trì

~~~text
CHANGE:
  Mongod controlled rolling maintenance

ENVIRONMENT:
  Approved cluster and nodes

OWNER:
  DBA/Platform lead

PRECHECK:
  Cluster identity confirmed
  Backup verified
  Voting majority healthy
  Secondary lag within threshold
  Disk/network healthy
  Application retry/drain ready

EXECUTION:
  Revalidate topology per member
  Drain affected traffic
  Graceful stop
  Apply approved change
  Start through service manager/operator
  Wait for SECONDARY/PRIMARY stable state
  Verify replication catch-up
  Run database and application smoke
  Continue only after pass

ABORT IF:
  No healthy primary beyond limit
  Quorum at risk
  Lag or API error above threshold
  Node cannot start
  Unplanned data/security change

POSTCHECK:
  All members healthy
  Required indexes/search ready
  Majority writes and critical reads pass
  API p95 and error rate back within SLO
  CDC/background jobs reconnected
  Backup, balancer, alerts restored

CLOSE:
  Record timestamps and logs
  Document changes and deviations
  Notify stakeholders
  Create corrective actions
~~~

## 57. Kết luận

Khởi động, dừng và bảo trì MongoDB **không nên được hiểu là thao tác trên process đơn lẻ**. Mục tiêu thực sự là giữ khả năng phục vụ của hệ thống trong giới hạn RPO, RTO và SLO đã định.

Các nguyên tắc quan trọng nhất:

- **Phân biệt liveness với readiness**: process active và ping thành công chưa chứng minh khả năng đọc/ghi nghiệp vụ.
- **Kiểm tra majority, replication lag và electability** trước khi dừng bất kỳ replica set member nào.
- **Ưu tiên rolling maintenance**, chờ node trở lại healthy và caught-up rồi mới tiến sang node kế tiếp.
- **Dừng gracefully** bằng service manager/orchestrator/driver-supported command; không dùng kill cưỡng bức như quy trình thường xuyên.
- **Stepdown primary có kiểm soát** và dự kiến transient errors trong election.
- **Với sharded cluster**, xét riêng config servers, shards, mongos và balancer; theo official sequence của phiên bản nâng cấp.
- **Với Atlas/Kubernetes**, sử dụng control plane hoặc Operator tương ứng thay vì thao tác thủ công trái quy trình.
- **Không thay binary, FCV, schema và network settings đồng loạt thiếu kế hoạch**.
- **Sau start luôn xác minh cả database và ứng dụng**: roles, TLS, writes, query performance, CDC và business smoke tests.
- **Có abort/rollback gates và bằng chứng vận hành**, không tiếp tục rollout chỉ vì lệnh trước trả exit code 0.

**Một lượt bảo trì hoàn tất khi hệ thống đã trở về trạng thái sẵn sàng được kiểm chứng, không phải khi lệnh restart cuối cùng chạy xong.**

## Tài liệu tham khảo

- [MongoDB Manual — Administration](https://www.mongodb.com/docs/manual/administration/)
- [MongoDB Manual — Replica Set Deployment and Maintenance](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — rs.status](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB Manual — rs.stepDown](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/)
- [MongoDB Manual — shutdown](https://www.mongodb.com/docs/manual/reference/command/shutdown/)
- [MongoDB Manual — ServerStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — Upgrade Procedures](https://www.mongodb.com/docs/manual/release-notes/)
- [MongoDB Manual — Backup and Restore](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Atlas — Cluster Maintenance](https://www.mongodb.com/docs/atlas/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
