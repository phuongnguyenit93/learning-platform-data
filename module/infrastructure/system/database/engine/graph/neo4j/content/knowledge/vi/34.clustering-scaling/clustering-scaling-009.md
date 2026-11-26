# Giám sát, sao lưu và diễn tập sự cố trong cụm

## 1. Một cụm Neo4j có nhiều bản sao vẫn có thể gặp sự cố

Neo4j cho phép triển khai cơ sở dữ liệu đồ thị theo mô hình **cluster** để cải thiện khả năng sẵn sàng và mở rộng năng lực đọc trong những cấu hình được hỗ trợ. Trong đó, dữ liệu vẫn được mô hình hóa bằng **node, relationship, property**, truy vấn bằng **Cypher** và được ứng dụng Java truy cập qua **Neo4j Java Driver** hoặc Spring Data Neo4j.

Tuy nhiên, sự tồn tại của nhiều server không đồng nghĩa mọi loại sự cố đều được giải quyết:

- Một thành viên không phản hồi có thể khiến kết nối trên server đó thất bại.
- Cụm mất đủ thành viên tham gia đồng thuận có thể **không tiếp tục commit ghi** dù một số server vẫn đang chạy.
- Ứng dụng có thể tìm được bootstrap endpoint nhưng nhận routing table chứa hostname không thể truy cập.
- Một truy vấn đọc trên bản sao đang chậm cập nhật có thể chưa thấy thay đổi vừa commit ở nơi khác nếu không dùng cơ chế nhất quán phù hợp.
- Thao tác `DELETE` nhầm hoặc dữ liệu nghiệp vụ sai có thể được sao chép sang các thành viên còn lại.
- Sự cố ảnh hưởng cả vùng lưu trữ, tài khoản quản trị hay cấu hình chung có thể tác động toàn bộ cluster.
- Có bản sao lưu nhưng chưa từng thử restore vẫn có thể không phục hồi được đúng thời hạn.

Vì vậy, cần ba lớp kiểm soát phối hợp:

1. **Giám sát (monitoring):** phát hiện lệch chuẩn của cluster, database, giao dịch và ứng dụng.
2. **Sao lưu/khôi phục (backup and restore):** có dữ liệu độc lập và quy trình tái dựng được hệ thống sau mất mát hoặc sai lệch.
3. **Diễn tập sự cố (failure drill):** chủ động xác minh giả định về failover, routing, thời gian khôi phục, dữ liệu và người phụ trách.

> **Nguyên tắc trọng tâm:** Replication giúp nâng cao tính sẵn sàng trước một số lỗi hạ tầng; **backup bảo vệ khả năng phục hồi dữ liệu**; diễn tập xác nhận hai cơ chế thực sự hoạt động. Không dùng bất kỳ cơ chế nào để thay thế hoàn toàn hai cơ chế còn lại.

Các ví dụ trong bài tập trung vào kiến trúc Neo4j Enterprise 5.x trở lên theo hướng khái niệm. **Tên lệnh, quyền, cấu hình backup, giới hạn cluster và vai trò máy chủ phụ thuộc phiên bản/edition**. Trước khi triển khai, cần đối chiếu tài liệu đúng phiên bản đang chạy; không áp dụng lệnh vận hành vào production chỉ vì nó xuất hiện trong bài.

## 2. Hiểu topology và phạm vi lỗi của cluster

Trong nhiều mô hình Neo4j cluster hiện đại, cần phân biệt:

| Thành phần | Vai trò khái quát | Điểm cần quan sát |
|---|---|---|
| **Server/member** | Tiến trình Neo4j tham gia triển khai | Liveness, CPU, heap, page cache, disk, mạng |
| **Primary** | Thành viên giữ bản sao dữ liệu tham gia cơ chế duy trì dữ liệu/ghi phù hợp topology | Khả dụng, khả năng đồng thuận, thời gian commit |
| **Secondary** | Thành viên duy trì bản sao phục vụ một số mục tiêu mở rộng đọc/khả dụng | Độ trễ theo kịp dữ liệu, truy vấn đọc, tài nguyên |
| **Database** | Một graph database logic được phân bố theo topology | Trạng thái, khả năng đọc/ghi, replication |
| **Writer/leader** | Điểm đảm nhiệm điều phối ghi của database theo topology tại thời điểm đó | Chuyển vai trò, độ trễ, failover |
| **System database/control plane** | Quản lý metadata/topology và các chức năng quản trị tùy phiên bản | Trạng thái hệ thống, thay đổi cấu hình, quyền |
| **Client routing** | Cơ chế Java Driver khám phá và lựa chọn endpoint | Routing table, DNS, TLS, read/write connectivity |

Các bản Neo4j khác nhau có thể sử dụng thuật ngữ, số lượng role và chính sách cấp phát database khác nhau. **Không đồng nhất role “PRIMARY” trong một lệnh hiển thị với giả định server đó luôn là writer hiện tại cho mọi database.** Vai trò writer có thể thay đổi theo database và theo thời điểm.

### 2.1. Quorum và khả năng ghi

Với cơ chế đồng thuận đa số, một nhóm ba thành viên có quyền tham gia bỏ phiếu thường có thể chịu mất một thành viên mà vẫn còn đa số **nếu những điều kiện khác của topology vẫn thỏa mãn**. Khi chỉ còn một thành viên trong nhóm ba và không liên lạc được với hai thành viên kia, việc cho phép commit ghi an toàn thường không thể tiếp tục.

~~~text
Trạng thái bình thường:
    Primary A ----- Primary B ----- Primary C
         \              |              /
               đủ thành viên đồng thuận

Một member mất:
    Primary A ----- Primary B       Primary C (offline)
         |
      vẫn có thể còn đa số, tùy topology

Mất phần lớn:
    Primary A          Primary B (offline)  Primary C (offline)
         |
      không còn đa số để tiếp tục commit ghi an toàn
~~~

Đây là mô hình giải thích nguyên tắc, không phải cam kết mọi cấu hình ba server sẽ tự failover thành công với cùng độ trễ. Khả năng ghi còn phụ thuộc trạng thái database, network, bầu chọn, topology và phiên bản.

**Secondary không phải bản thay thế tự động cho quorum ghi.** Dù có nhiều bản sao chỉ phục vụ đọc, cluster vẫn cần những điều kiện đồng thuận cụ thể để cho phép ghi.

### 2.2. Phạm vi sự cố phải được phân tầng

- **Một process Neo4j:** crash, out-of-memory, hết file descriptor.
- **Một host/VM/Pod:** restart, CPU starvation, disk bị đầy.
- **Một availability zone:** mạng hoặc lưu trữ trong zone không hoạt động.
- **Một subnet/VPC:** DNS, route, firewall hoặc network partition.
- **Một database:** stopped, failed, thiếu replica hoặc gặp lỗi dữ liệu.
- **Toàn cluster:** lỗi cấu hình chung, certificate hết hạn đồng loạt, sai thao tác quản trị.
- **Hệ thống tích hợp:** broker/Java service vẫn gửi request dù database mất khả năng ghi.

Thiết kế giám sát và diễn tập nên có kịch bản cho từng mức, không gộp tất cả thành “Neo4j down”.

## 3. Xác định điều gì được coi là hệ thống khỏe

Một endpoint trả `200 OK` hoặc một lệnh `RETURN 1` thành công **chưa chứng minh** mọi database và mọi đường ứng dụng đang hoạt động tốt.

Có thể đánh giá qua bốn lớp:

| Lớp | Câu hỏi | Ví dụ phép đo |
|---|---|---|
| **Hạ tầng** | Server và mạng còn đủ tài nguyên không? | CPU, memory, disk free, I/O, TCP, DNS |
| **Neo4j/database** | Database còn online, có đủ topology và xử lý transaction không? | Trạng thái DB, transaction errors, replication |
| **Driver và ứng dụng** | Java service có kết nối, định tuyến và retry đúng không? | Routing errors, pool wait, executeRead/executeWrite |
| **Nghiệp vụ** | Các thao tác quan trọng còn hoàn thành đúng kết quả không? | Tạo đơn, đọc quan hệ, đối chiếu dữ liệu |

Một cluster có thể báo process “up” ở mọi member nhưng người dùng vẫn thất bại khi ghi do mất quorum hoặc sai DNS được công bố. Vì vậy, **health của process, health của database và health của nghiệp vụ không giống nhau**.

### 3.1. Chọn SLI/SLO trước khi đặt alert

**SLI** là đại lượng đo, chẳng hạn tỷ lệ transaction ghi thành công hoặc p99 độ trễ đọc. **SLO** là mục tiêu do đội sản phẩm/vận hành lựa chọn.

Ví dụ minh họa:

~~~text
Service: Graph Order API
SLI-1: tỷ lệ yêu cầu ghi được xác nhận thành công
SLI-2: p95/p99 latency của thao tác tạo Order
SLI-3: tỷ lệ truy vấn đọc thành công sau khi ghi
SLI-4: độ trễ nhận được trạng thái cập nhật ở projection
SLO: lựa chọn theo yêu cầu sản phẩm, không lấy ngưỡng tùy ý
~~~

**Không tự chọn một ngưỡng chung cho mọi Neo4j cluster.** SLO của dịch vụ realtime, kho phân tích và pipeline nhập dữ liệu có thể khác nhau.

## 4. Kiểm tra trạng thái cluster bằng công cụ Neo4j

Trong những phiên bản Neo4j hỗ trợ các lệnh quản trị tương ứng, có thể bắt đầu bằng:

~~~cypher
SHOW DATABASES;
~~~

Lệnh này giúp quan sát danh sách database và những thông tin trạng thái/role mà phiên bản và quyền hiện tại cho phép hiển thị.

Đối với môi trường hỗ trợ quản lý server qua Cypher:

~~~cypher
SHOW SERVERS;
~~~

Cần quyền phù hợp và phiên bản/edition hỗ trợ. Nội dung cột có thể khác nhau giữa các bản Neo4j; khi xây script thu thập metric, **không hard-code tên cột từ một phiên bản khác**.

Kiểm tra các transaction đang chạy (với quyền cho phép):

~~~cypher
SHOW TRANSACTIONS;
~~~

Lệnh này hỗ trợ điều tra giao dịch kéo dài, trạng thái chờ hoặc truy vấn đang hoạt động. **Không đưa bản dump kết quả thô lên ticket công khai** nếu nó chứa query text, thông tin người dùng hay tham số nhạy cảm.

### 4.1. Những trạng thái nên phân biệt

- Member/DB đang online và nhận kết nối.
- Database được yêu cầu online nhưng trạng thái thực tế chưa online.
- Một server đang offline, nhưng database vẫn đọc/ghi được qua server khác.
- Ứng dụng không lấy được routing table hoặc routing table chứa địa chỉ không reachable.
- Read còn thành công nhưng write thất bại.
- Ghi vẫn commit nhưng độ trễ tăng do contention hoặc thay đổi writer.
- Backup service online nhưng thao tác backup thất bại do disk/permission/network.

Đừng dùng **chỉ một** health check trên một IP làm tiêu chí cho cả cluster.

### 4.2. Trạng thái tức thời không thay thế lịch sử

`SHOW DATABASES` tại thời điểm T có thể cho thấy database đang hoạt động. Nó không nói database đã mất writer ba phút trước, đã bầu chọn lại bao nhiêu lần, hoặc những request nào gặp timeout.

Giữ chuỗi thời gian và dấu mốc sự kiện:

~~~text
09:10:00  Member B không phản hồi
09:10:05  Driver bắt đầu báo routing/write failures
09:10:18  Writer mới hoạt động và commit được
09:10:22  API write success rate trở lại mục tiêu
09:11:00  Đối chiếu lệnh nghiệp vụ đã nhận và commit
~~~

Các mốc là **ví dụ**, không phải thời gian failover chuẩn của Neo4j. Thời gian thực phải được đo trong diễn tập.

## 5. Giám sát tài nguyên trên từng server

Theo dõi **từng member**, không chỉ tổng cluster:

| Nhóm | Chỉ số cần quan sát | Vì sao quan trọng? |
|---|---|---|
| CPU | Mức sử dụng, saturation, steal time nếu là VM | Truy vấn/GC có thể chậm khi CPU tranh chấp |
| Heap/JVM | Used heap, GC pause, GC frequency | Memory pressure có thể gây timeout/OOM |
| Page cache | Kích thước, hit ratio, evictions | Tác động tới I/O khi duyệt node/relationship |
| OS memory | Available RAM, swap/pressure | Thiếu RAM có thể làm toàn server chậm |
| Disk | Free bytes, inode, IOPS, latency, queue | Ghi transaction và backup nhạy với I/O |
| Network | Throughput, errors, packet loss, RTT | Ảnh hưởng routing và nhân bản dữ liệu |
| Process | Restart, open files, thread pool, liveness | Phát hiện crash hoặc giới hạn tài nguyên |
| Backup destination | Dung lượng, lỗi ghi, thời gian upload | Backup thành công phụ thuộc đích lưu |
| Container | CPU throttling, memory limit, OOMKilled | Cấu hình cgroup có thể khác tài nguyên host |

### 5.1. Heap và page cache không phải cùng một thứ

Neo4j dùng heap cho nhiều cấu trúc Java và **page cache** cho việc truy cập dữ liệu graph trên đĩa. Nếu mọi latency tăng do page cache không đủ, chỉ tăng heap có thể không giải quyết vấn đề. Ngược lại, tăng page cache quá mức có thể làm OS thiếu RAM cho heap và thành phần khác.

Khi điều chỉnh tài nguyên, xem:

- Số node, relationship, index và kích thước store.
- Truy vấn thường duyệt bao nhiêu phần graph.
- Mức độ cache warming sau restart.
- GC pause và pressure.
- Tài nguyên dành cho backup, GDS projection và job nhập dữ liệu.

Không lấy một công thức RAM cố định áp dụng cho mọi workload.

### 5.2. Disk đầy là tình huống phải ưu tiên cảnh báo

Database và transaction log cần dung lượng ghi. Nếu một thành viên bị đầy disk, nó có thể gặp lỗi ghi, lỗi backup, lỗi phục hồi hoặc không theo kịp cluster.

Nên cảnh báo trước khi disk chạm mức nguy hiểm, dựa trên **tốc độ tăng dung lượng**, dung lượng còn trống và thời gian cần để vận hành khắc phục.

**Không xóa transaction log, data store hoặc file nội bộ Neo4j thủ công chỉ để giải phóng dung lượng.** Những thao tác này có thể làm hỏng khả năng recovery hoặc độ nhất quán. Phải dùng quy trình được phiên bản Neo4j hỗ trợ.

## 6. Giám sát cơ chế nhân bản và tính sẵn sàng ghi

Ở cluster, chỉ số replication/synchronization cần được diễn giải theo vai trò và topology của từng database:

- Có đủ thành viên phục vụ điều kiện ghi không?
- Writer có thay đổi thường xuyên không?
- Các bản sao có **đang theo kịp** trạng thái commit không?
- Một member có bị đứng sau lâu do network, CPU hoặc disk không?
- Có node liên tục bị evict/rejoin hoặc database liên tục chuyển trạng thái không?
- Có sự khác biệt giữa database nghiệp vụ và các thành phần system/control plane không?

**Metric name và cơ chế replication phụ thuộc phiên bản Neo4j.** Không tự giả định có một counter hoặc một đơn vị “replication lag = X milliseconds” giống nhau ở mọi phiên bản. Khi tích hợp exporter, phải xác nhận metric mang ý nghĩa gì, scope là server/database nào và có thể dùng để alert hay chỉ làm chỉ báo bổ sung.

### 6.1. Đọc chậm cập nhật khác với đọc thất bại

Ví dụ:

~~~text
T1: write "Order O1 = PAID" commit thành công
T2: một session đọc khác đến server chưa theo kịp
T3: session đó có thể chưa quan sát dữ liệu mới nếu không có cơ chế nhất quán phù hợp
~~~

Nếu nghiệp vụ yêu cầu **read-your-writes** qua nhiều session, Java Driver có cơ chế **bookmarks/causal consistency** tùy API và phiên bản; ứng dụng cần chia sẻ bookmark đúng phạm vi thay vì giả định mọi lệnh đọc sau đó luôn đến server đã commit.

Cũng cần phân biệt yêu cầu “thấy ghi trước của chính mình” với yêu cầu “mọi client thấy cùng trạng thái tức thời”. Causal consistency không tự biến toàn bộ cluster thành một giao dịch phân tán đồng bộ cho mọi tác vụ ứng dụng.

### 6.2. Quan sát ứng dụng theo cả read và write

Nên theo dõi riêng:

- `executeRead` success/latency.
- `executeWrite` success/latency.
- Retry/transaction attempt count.
- Lỗi không lấy được writer/routing endpoint.
- Lỗi không có đủ server hoặc database không available.
- Số request nghiệp vụ nhận, xử lý thành công, đã xác nhận trùng.

Trong sự cố, **read vẫn thành công** có thể khiến dashboard tổng thể đẹp, trong khi **write đã mất khả dụng**. Tách SLI read/write giúp phát hiện nhanh hơn.

## 7. Thu thập metrics, logs và tracing có kiểm soát

Với Neo4j Enterprise ở những phiên bản hỗ trợ, có thể xuất metric sang Prometheus hoặc một nền tảng giám sát tương ứng. Tên setting và mức độ hỗ trợ có thể thay đổi.

Ví dụ **minh họa cho nhóm setting của Neo4j 5.x**, cần xác minh với phiên bản thực tế:

~~~properties
# neo4j.conf — minh họa, không phải cấu hình production hoàn chỉnh.
server.metrics.enabled=true
server.metrics.prometheus.enabled=true
server.metrics.prometheus.endpoint=127.0.0.1:2004
~~~

Địa chỉ `127.0.0.1:2004` mang ý nghĩa endpoint metric chỉ lắng nghe loopback của network namespace. Nếu agent giám sát ở container/Pod khác, phải thiết kế đường truy cập nội bộ được bảo vệ; **không đổi thành 0.0.0.0 public tùy tiện**.

Trước khi deploy, kiểm tra:

1. Neo4j đang chạy phiên bản/edition nào.
2. Setting metric tương ứng có được hỗ trợ không.
3. Endpoint metric có yêu cầu thêm chính sách network/auth không.
4. Collector có quyền và route phù hợp không.
5. Metric label có chứa database/member và có cardinality chấp nhận được không.
6. Metric đang thu có đủ cơ sở để đo SLI đã định nghĩa không.

### 7.1. Không thu thông tin nhạy cảm chỉ vì cần debug

Giữ metrics ở dạng tổng hợp, có nhãn hữu hạn như `database`, `operation` và `outcome` theo chính sách. Không đặt email, customer ID, Cypher parameter map hay request body vào metric label, trace span hoặc alert.

Với log query/transaction, kiểm tra chính sách redaction/parameter logging theo phiên bản; dashboard cho nhiều người không được làm lộ dữ liệu mà người xem không có quyền đọc trực tiếp trong graph.

### 7.2. Quan sát theo lớp

~~~mermaid
flowchart TD
  A["Neo4j members"] --> B["Metrics/Logs Collector"]
  C["Java Driver / Spring Service"] --> B
  D["Proxy / DNS / LB"] --> B
  E["Backup / Restore Jobs"] --> B
  B --> F["Dashboard read-write + RPO/RTO evidence"]
  B --> G["Alerts / Incident process"]
~~~

Một lỗi route proxy có thể khiến ứng dụng không kết nối được dù cả Neo4j server lẫn query metrics đều bình thường. Vì vậy, collector cần dấu hiệu từ **cả infrastructure và client**.

## 8. Xây dashboard vận hành tối thiểu

Một dashboard dùng để trực ca nên trả lời nhanh:

| Nhóm | Widget nên có | Cảnh báo cần phân biệt |
|---|---|---|
| Topology | Số member up, database online và trạng thái vai trò | Member down, database không đạt yêu cầu |
| Write availability | Thành công/thất bại của ghi theo database | Không có writer hoặc mất quorum |
| Read availability | Thành công/thất bại của đọc | Replica/endpoint không reachable |
| Latency | p50/p95/p99 theo read/write và endpoint nghiệp vụ | Tail latency tăng |
| Routing/client | Lỗi DNS/TLS/routing, pool wait, retry | Bootstrap hoạt động nhưng member endpoint hỏng |
| Replication | Chỉ báo bắt kịp dữ liệu theo phiên bản hỗ trợ | Member lag/stall kéo dài |
| Storage | Disk free, I/O, transaction log growth | Nguy cơ hết dung lượng |
| Backup | Lần backup thành công gần nhất, tuổi backup, kiểm tra tính toàn vẹn | Không có bản mới trong khoảng RPO |
| Restore drills | Lần restore test gần nhất, thời gian, kết quả kiểm tra | Backup chưa được thử khôi phục |
| Business invariant | Đối soát số request đã xử lý, đơn hàng thiếu quan hệ | Ghi bị lặp hoặc dữ liệu lệch sau retry |

### 8.1. Alert phải có hành động tiếp theo

Không chỉ cấu hình “CPU vượt ngưỡng” mà không nói ai và bằng cách nào xử lý. Một alert tốt có:

- Database/server bị ảnh hưởng.
- Thời điểm và thời lượng vi phạm.
- SLI/SLO liên quan.
- Mức ưu tiên và phạm vi tác động.
- Link runbook xử lý.
- Người chịu trách nhiệm hoặc nhóm trực.
- Chỉ số xác nhận đã phục hồi.

Nếu chỉ số CPU cao mà tỷ lệ request thành công và latency vẫn trong mục tiêu, mức độ ưu tiên có thể khác với tình huống **100% write thất bại**.

### 8.2. Cảnh báo backup không chỉ dựa vào exit code

Backup process có thể trả thành công nhưng:

- Bản backup không được copy sang vùng lưu độc lập như kế hoạch.
- Đích lưu bị đầy và bản mới nhất bị giữ tại một host tạm.
- Secret/certificate dùng để giải mã backup bị thất lạc.
- File có mặt nhưng restore đã từng thất bại vì thiếu metadata/quyền.
- Kho backup bị hỏng hoặc bị xóa bởi cùng một tài khoản quản trị production.

Vì vậy dashboard nên phân biệt **backup job completed**, **artifact verified**, **offsite copy verified** và **restore drill passed**.

## 9. Replication không phải backup

Một cluster có ba bản sao của cùng database có thể chống mất một server trong một số điều kiện. Nhưng replication cũng có thể **sao chép lỗi**:

~~~text
Ứng dụng chạy DELETE sai
       |
       v
Writer commit DELETE
       |
       v
Thay đổi hợp lệ về mặt transaction được nhân bản
       |
       v
Các replica đều thiếu dữ liệu đã xóa
~~~

Các bản sao nhất quán không có nghĩa dữ liệu đúng về mặt nghiệp vụ. Muốn quay về một thời điểm trước khi xóa sai, cần **backup hoặc một cơ chế phục hồi lịch sử được thiết kế trước**.

| Cơ chế | Bảo vệ chủ yếu | Không tự giải quyết |
|---|---|---|
| Cluster replication | Một số lỗi member/host và khả năng đọc/ghi liên tục | Xóa nhầm, ransomware, lỗi logic được commit |
| Backup độc lập | Khôi phục dữ liệu từ điểm đã lưu | Tự động failover tức thời |
| Snapshot storage | Tạo ảnh chụp theo khả năng nền tảng | Không tự bảo đảm nhất quán ứng dụng/database nếu chụp sai quy trình |
| Transaction log/recovery theo tính năng hỗ trợ | Khôi phục đến một thời điểm/ranh giới có thể hỗ trợ | Không thể giả định bảo vệ mọi thay đổi nếu retention/chain thiếu |
| Restore drill | Chứng minh một đường phục hồi khả thi | Không ngăn sự cố xảy ra |
| Outbox/idempotency | Giảm sai lệch do retry/duplicate và tích hợp | Không khôi phục toàn bộ database bị mất |

**Không xem snapshot VM, copy thư mục data đang chạy, hoặc PVC clone thủ công là backup Neo4j nhất quán** nếu không tuân theo quy trình sản phẩm và storage được hỗ trợ.

## 10. Đặt mục tiêu RPO, RTO và mức khôi phục

Hai mục tiêu cần thống nhất với nghiệp vụ trước khi chọn chiến lược backup:

- **RPO (Recovery Point Objective):** mức mất dữ liệu có thể chấp nhận sau sự cố, thường biểu đạt bằng khoảng thời gian.
- **RTO (Recovery Time Objective):** thời gian cho phép từ lúc sự cố gây gián đoạn tới khi dịch vụ được khôi phục đủ điều kiện chấp nhận.

Ví dụ minh họa:

~~~text
Mất dịch vụ lúc:        10:00
Điểm dữ liệu mới nhất
khôi phục được:          09:55
Dịch vụ trở lại:        10:17

Mất dữ liệu theo mốc:   khoảng 5 phút
Thời gian gián đoạn:    khoảng 17 phút
~~~

Đây là minh họa cách đo, **không phải năng lực mặc định của Neo4j**. Nếu transaction được phục hồi thêm từ log sau mốc backup hoặc luồng ứng dụng có replay, điểm khôi phục thực tế có thể khác. Cần đo bằng **dữ liệu commit được xác minh**, không chỉ bằng timestamp của file backup.

### 10.1. RPO và RTO phải bao gồm những gì?

RTO không nên chỉ đo thời gian chạy lệnh restore. Khôi phục phục vụ ứng dụng có thể còn cần:

1. Chuẩn bị compute, network, volume và secret.
2. Có quyền truy cập artifact backup.
3. Restore database và kiểm tra nhất quán.
4. Cấu hình topology/cluster theo quy trình được hỗ trợ.
5. Khôi phục DNS/proxy/TLS và quyền ứng dụng.
6. Kiểm tra read/write, index và các truy vấn quan trọng.
7. Đối chiếu transaction đã xác nhận/đang chờ.
8. Mở traffic lại theo các điều kiện nghiệm thu.

Một câu “restore mất 4 phút” có thể che khuất 40 phút sửa cấu hình network hoặc xác thực sau đó.

### 10.2. Hợp đồng nghiệp vụ quyết định mục tiêu

Một graph dùng tìm tài liệu nội bộ có thể chấp nhận dựng lại từ nguồn, trong khi graph đơn hàng/điểm thưởng cần bảo vệ cao hơn đối với các transaction đã xác nhận thành công. Mức độ chấp nhận mất dữ liệu và thời gian dừng phải được **chủ sở hữu nghiệp vụ phê duyệt**.

Không cố đạt RPO bằng 0 nếu không có kiến trúc, ngân sách, nguồn dữ liệu và quy trình cụ thể để chứng minh nó.

## 11. Lập chính sách backup cho một database và nhiều database

Trước khi viết lệnh backup, lập danh sách:

- Những database đang hoạt động và database nào là nguồn dữ liệu chính.
- Database nào chứa dữ liệu có thể tạo lại, database nào không.
- Phiên bản Neo4j/edition và cơ chế backup hỗ trợ.
- Địa chỉ backup service và quyền network.
- Dung lượng data/index/log và tốc độ tăng trưởng.
- Kho lưu độc lập, mã hóa và vòng đời secret.
- Lịch full/incremental nếu tính năng và phiên bản cho phép.
- Retention và số phiên bản lưu.
- Chính sách lưu trữ bất biến/offsite theo yêu cầu chống xóa nhầm/ransomware.
- Cách kiểm chứng backup artifact và diễn tập restore.
- Metadata cấu hình/role/secret cần bảo vệ riêng.

### 11.1. Nhiều database không tự có một thời điểm nhất quán toàn cụm

Một hệ thống có database `customers` và `orders` có thể backup hai database tại hai thời điểm khác nhau. Nếu dữ liệu giữa chúng có ràng buộc nghiệp vụ, việc restore từng bản có thể tạo một trạng thái liên hệ **không khớp thời gian**.

Neo4j transaction thông thường có phạm vi một database; không tự giả định một lệnh backup nhiều database là **distributed snapshot đồng nhất về nghiệp vụ** giữa nhiều nguồn hoặc giữa Neo4j và SQL/Kafka.

Giải pháp có thể gồm:

- Thiết kế ứng dụng lưu thông tin version/offset để đối chiếu sau restore.
- Dừng hoặc điều phối một số nguồn ghi trong cửa sổ backup khi nghiệp vụ cho phép.
- Chấp nhận eventual reconciliation và có playbook khôi phục sự kiện thiếu.
- Định nghĩa rõ dữ liệu nào là authoritative source và dữ liệu nào có thể rebuild.

### 11.2. Có cần backup system database?

Trong Neo4j, **system database** và metadata quản trị có vai trò quan trọng đối với quản lý database và quyền. Nhưng phạm vi được backup/restore, phương thức thao tác và cách dựng lại cluster tùy phiên bản.

Một kế hoạch phục hồi đầy đủ phải bao gồm khả năng khôi phục hoặc tái tạo **database metadata, users/roles, schema, secret/certificate, topology và cấu hình deployment**, theo cách được phiên bản hỗ trợ. Không chỉ lưu backup database nghiệp vụ rồi giả định mọi thứ khác tự xuất hiện sau sự cố toàn cụm.

## 12. Backup online: công cụ và điều kiện an toàn

Neo4j Enterprise cung cấp công cụ backup phù hợp những phiên bản/edition tương ứng. Một ví dụ định hướng trong dòng Neo4j 5.x có dạng:

~~~bash
# Minh họa cho môi trường thử nghiệm được ủy quyền.
# Cú pháp/flag và cơ chế backup phải kiểm tra theo phiên bản đang chạy.
neo4j-admin database backup \
  --from=10.20.1.11:6362 \
  --to-path=/secure/neo4j-backups \
  neo4j
~~~

Ví dụ giả định backup service ở địa chỉ `10.20.1.11:6362` đã được bật, reachable từ nơi chạy CLI và tài khoản có quyền. **Không suy ra port 6362 luôn được mở** hoặc backup online sẵn sàng trong mọi image, edition và cấu hình.

Một số phiên bản dùng nhóm setting cho backup service, ví dụ:

~~~properties
# Setting minh họa, phải xác minh theo bản Neo4j triển khai.
server.backup.enabled=true
server.backup.listen_address=10.20.1.11:6362
~~~

Không mở backup port cho Internet. Đây là kênh vận hành có thể truy cập dữ liệu rất nhạy cảm; cần network ACL, quyền truy cập, mã hóa và kiểm soát artifact.

### 12.1. Chạy backup từ thành viên nào?

Về nguyên tắc, có thể chọn một thành viên **có khả năng phục vụ backup và đủ dữ liệu** theo điều kiện của phiên bản/topology nhằm hạn chế tác động đến tải ghi. Nhưng không được tuyên bố “backup secondary luôn an toàn/đủ mới” trong mọi trường hợp.

Cần đo:

- Mức cập nhật dữ liệu của thành viên được chọn.
- Tác động I/O/CPU/network đến traffic đọc/ghi.
- Cách backup tool xử lý transaction log và consistency.
- Chênh lệch giữa điểm dữ liệu được khôi phục và thời điểm backup hoàn tất.
- Khả năng hoàn thành trong cửa sổ cho phép.

Backup thành công từ một thành viên đang theo sau dữ liệu có thể không đáp ứng RPO nếu không kiểm tra **recovery point thực tế**.

### 12.2. Full và incremental

Một chiến lược có thể dùng **full backup định kỳ** và **incremental backup** giữa các lần full nếu bản Neo4j/đích lưu hỗ trợ. Incremental thường có phụ thuộc vào chuỗi backup/lịch sử transaction; không được xóa một phần chain rồi nghĩ vẫn restore được điểm gần nhất.

Thiết kế retention phải lưu đủ thành phần cần để tái dựng bản backup hợp lệ. Khi chuyển server/version hoặc đổi vị trí lưu, kiểm tra khả năng tiếp tục chuỗi incremental thay vì tự suy đoán.

### 12.3. Artifact backup cần được bảo vệ thế nào?

- Đặt tên/metadata gồm database, thời điểm, phiên bản, loại backup và ID run.
- Mã hóa khi truyền/lưu theo chính sách.
- Hạn chế tài khoản có quyền xóa hoặc thay thế backup.
- Có bản sao ở failure domain khác với cluster.
- Ghi manifest/checksum nếu quy trình hỗ trợ.
- Xác minh khả năng liệt kê và đọc artifact.
- Ghi thời gian/phiên bản Neo4j cần để restore tương thích.
- Thử restore định kỳ và theo dõi kết quả.

**Checksum chứng minh file không bị thay đổi ngoài mong muốn theo phép kiểm đó, nhưng không chứng minh data store bên trong khôi phục được.** Phải có bước restore test.

## 13. Quản lý lịch backup và độ tuổi bản khôi phục

Một lịch có thể gồm:

~~~text
00:00  Full backup (tùy chính sách)
01:00  Incremental hoặc cơ chế bổ sung được hỗ trợ
02:00  Incremental / verify
...
Mỗi ngày: kiểm tra tuổi recovery point và kết quả artifact
Mỗi tuần/tháng: restore drill trong môi trường cô lập
~~~

Đây chỉ là cấu trúc lịch minh họa; tần suất cần dựa trên RPO, lưu lượng ghi, khả năng lưu transaction log và chi phí thực tế.

### 13.1. Nếu backup job thất bại

Đừng coi thất bại một lần là “chỉ retry thêm” mà bỏ qua nguyên nhân. Cần biết:

- Destination có còn đủ dung lượng không?
- Network tới member backup có lỗi không?
- Backup service có bật đúng địa chỉ/port không?
- Cluster có đang failover hoặc database chưa online không?
- Secret/certificate/permission có thay đổi không?
- Có quá nhiều backup job đồng thời làm nghẽn I/O không?
- File/chuỗi incremental còn hợp lệ không?

Với mục tiêu RPO ngắn, backup fail liên tiếp phải cảnh báo theo **độ tuổi bản khôi phục hợp lệ gần nhất**, chứ không chỉ theo số job lỗi.

### 13.2. Retention và recovery window

Giả sử tổ chức giữ một bản mỗi giờ trong một ngày và một bản mỗi ngày trong bốn tuần. Đây là chính sách theo tầng, không có nghĩa có thể phục hồi tới **mọi giây** trong khoảng bốn tuần.

Khả năng phục hồi đến một mốc cụ thể phụ thuộc backup format, transaction log/incremental chain và tính năng được bản Neo4j hỗ trợ. **Không quảng cáo point-in-time recovery theo phút/giây chỉ vì file backup có timestamp.**

## 14. Diễn tập restore phải diễn ra ngoài cụm đang chạy

Một bài restore drill an toàn nên được thực hiện trên **môi trường cô lập**, không ghi đè dữ liệu production.

~~~mermaid
flowchart TD
  A["Backup artifact đã được bảo vệ"] --> B["Môi trường restore cô lập"]
  B --> C["Restore bằng công cụ đúng phiên bản"]
  C --> D["Khởi động database/cluster thử nghiệm"]
  D --> E["Kiểm tra trạng thái và truy vấn Cypher"]
  E --> F["Đối chiếu bất biến dữ liệu"]
  F --> G["Đo RTO/RPO và lập biên bản"]
~~~

### 14.1. Chuẩn bị restore

- Xác nhận **database target** và version tương thích.
- Có volume/disk đủ dung lượng cho restore, log và index.
- Chuẩn bị secret/certificate/role cần thiết.
- Bảo đảm môi trường target không dùng DNS/service name trùng production theo cách khiến client ghi nhầm.
- Chặn outbound integration không cần thiết (email, thanh toán, broker production).
- Ghi rõ snapshot/artifact được chọn và recovery point kỳ vọng.
- Kiểm tra công cụ restore, quyền và phương án xử lý khi fail.

**Không dùng thao tác overwrite-destination trên database production đang phục vụ** trong một buổi diễn tập. Đối với disaster recovery thật, chỉ thực hiện theo change/incident procedure và hướng dẫn restore chính thức của đúng phiên bản.

### 14.2. Restore không chỉ là một lệnh CLI

Công cụ restore của Neo4j có thể có lệnh trong nhóm:

~~~text
neo4j-admin database restore ...
~~~

Nhưng đường dẫn, định dạng artifact, cờ ghi đè, yêu cầu database offline và thứ tự khởi động phải lấy từ **trợ giúp của phiên bản cụ thể**. Không cố cung cấp một lệnh phá dữ liệu có placeholder rồi khuyến khích chạy trực tiếp.

Sau restore, cần xác minh server có thể khởi động và database có trạng thái phù hợp, **không chỉ kiểm tra exit code của câu lệnh**.

### 14.3. Kiểm tra graph bằng Cypher

Trên database restore thử nghiệm, có thể đếm một số thực thể đại diện:

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS customers;
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orders;
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationships;
~~~

Các con số trên **không nên lấy từ giả định**; so với manifest/điểm khôi phục/nguồn đối soát đã chuẩn bị trước. Với graph lớn, scan toàn bộ cũng có chi phí; chọn kiểm tra theo quy mô và trong môi trường test cho phép.

### 14.4. Kiểm tra bất biến, không chỉ số lượng

Giả sử mỗi Order phải có ít nhất một OrderLine:

~~~cypher
MATCH (o:Order)
WHERE NOT EXISTS {
  MATCH (o)-[:HAS_LINE]->(:OrderLine)
}
RETURN o.orderId AS orderId
LIMIT 20;
~~~

Kiểm tra OrderLine không có Product:

~~~cypher
MATCH (l:OrderLine)
WHERE NOT EXISTS {
  MATCH (l)-[:FOR_PRODUCT]->(:Product)
}
RETURN l.lineId AS lineId
LIMIT 20;
~~~

Những truy vấn này chỉ đúng khi mô hình nghiệp vụ quy định bất biến tương ứng. Nếu ứng dụng có trạng thái `DRAFT` hoặc cho phép Order chưa hoàn tất, cần lọc trạng thái trước khi coi dữ liệu là lỗi.

### 14.5. Kiểm tra schema và quyền

Sau restore, đừng chỉ xem có node/relationship:

~~~cypher
SHOW CONSTRAINTS;
~~~

~~~cypher
SHOW INDEXES;
~~~

Cần xác minh schema phục vụ API, quyền ứng dụng, tài khoản kết nối, database name, routing và các thành phần metadata cần thiết được khôi phục hoặc tái tạo đúng cách.

## 15. Đối chiếu giao dịch ứng dụng sau recovery

Đây là phần dễ bị bỏ sót khi hệ thống có retry và nhiều service.

Ví dụ:

~~~text
Client gửi lệnh C-101
    |
    +-- Neo4j commit thành công
    |
    X-- response bị mất vì sự cố
    |
Client không biết C-101 đã commit chưa
~~~

Sau cluster failover hoặc restore, client có thể gửi lại cùng thao tác. Nếu lệnh tạo Order có `orderId` ổn định, uniqueness constraint có thể giúp ngăn tạo hai Order. Nhưng với lệnh **cộng dồn điểm**:

~~~cypher
MATCH (a:Account {accountId: $accountId})
SET a.points = coalesce(a.points, 0) + $delta;
~~~

chạy lại thành công sẽ cộng thêm lần nữa. Vì vậy cần thiết kế **idempotency key/receipt**.

### 15.1. Ghi receipt cùng thay đổi nghiệp vụ

Mô hình minh họa:

~~~text
(:AppliedCommand {commandId, payloadHash, appliedAt})
           |
       [:APPLIED_TO]
           |
           v
(:Account {accountId, points})
~~~

Constraint:

~~~cypher
CREATE CONSTRAINT applied_command_unique IF NOT EXISTS
FOR (cmd:AppliedCommand)
REQUIRE cmd.commandId IS UNIQUE;
~~~

Ghi receipt và cập nhật Account **cùng Neo4j transaction**. Khi request trùng, kiểm tra receipt theo commandId và so payload trước khi quyết định đã xử lý. **MERGE Account đơn thuần không chống một delta bị cộng hai lần**.

### 15.2. Restore có thể làm mất receipt sau recovery point

Nếu restore tới bản sao lưu trước khi command C-101 được commit, receipt C-101 có thể không còn. Nhưng hệ thống bên ngoài có thể đã nhận xác nhận/thông báo về C-101. Khi replay:

- Nguồn sự kiện phải biết điểm replay phù hợp.
- Bản tin mang ID ổn định.
- Có quy trình đối chiếu thay đổi đã xác nhận với điểm khôi phục.
- Tác dụng phụ ngoài DB được bù/điều phối theo quy tắc nghiệp vụ.

**Một database restore thành công không tự khôi phục tính nhất quán giữa Neo4j và hệ thống thanh toán/Kafka/SQL** tại cùng thời điểm. RPO và cơ chế reconciliation phải xét toàn bộ quy trình nghiệp vụ.

### 15.3. Transactional outbox giúp phối hợp hệ thống ngoài

Nếu ứng dụng cần phát event sau khi ghi graph, có thể ghi `OutboxEvent` cùng transaction Neo4j, rồi dispatcher gửi ra broker sau commit. Dispatcher có thể gửi trùng do crash, nên consumer vẫn cần idempotency.

Khi restore, cần xác định những outbox nào đã phát trước sự cố, những outbox nào đang pending và cách replay để không nhân đôi tác dụng kinh doanh.

## 16. Diễn tập lỗi một member và failover

Một bài diễn tập thường bắt đầu bằng tình huống **một thành viên bị dừng có chủ đích** trong môi trường test/staging.

### 16.1. Kịch bản

- Cluster được dựng theo topology thử nghiệm phù hợp.
- Java application dùng URI routing `neo4j+s://...` hoặc cấu hình tương ứng với mạng đã thiết kế.
- Có workload read/write nhẹ, có tham số và ID nghiệp vụ ổn định.
- Dữ liệu test có những node/relationship được dùng để đối chiếu.
- Người trực có dashboard và khả năng rollback.

### 16.2. Trình tự kiểm tra

1. Đo baseline 10–30 phút hoặc khoảng phù hợp với môi trường.
2. Xác định writer/role của database mục tiêu bằng công cụ phiên bản hỗ trợ.
3. Dừng **một member đã chọn trong môi trường được phép**, không chọn ngẫu nhiên server production.
4. Quan sát alert về server/database/driver.
5. Theo dõi thời gian read/write bị ảnh hưởng và thời điểm phục hồi.
6. Kiểm tra số request đã commit, thất bại, retry và chưa rõ kết quả.
7. Khôi phục member, quan sát khả năng bắt kịp và trạng thái cluster.
8. Đối chiếu business invariant và ghi biên bản.

Không khẳng định một failover thành công chỉ vì server còn lại trả `RETURN 1`. Cần xác nhận **transaction ghi nghiệp vụ** và thông tin routing từ phía Java.

### 16.3. Chỉ tiêu phải ghi lại

| Chỉ tiêu | Vì sao quan trọng? |
|---|---|
| Thời gian phát hiện lỗi | Chất lượng monitoring/alert |
| Thời gian từ lỗi tới writer mới usable | Khả năng failover của database |
| Số request timeout/failed | Tác động người dùng |
| Số lần retry Driver | Mức độ tải và tính ổn định |
| Số lệnh chưa rõ commit | Nhu cầu đối soát/idempotency |
| Thời gian member hồi phục/bắt kịp | Khả năng khôi phục topology |
| p95/p99 latency trong và sau sự cố | Sự ổn định dưới failover |
| Sai lệch dữ liệu/duplicate | Độ đúng nghiệp vụ |

## 17. Diễn tập network partition và tình huống mất quorum

Đây là kịch bản quan trọng nhưng **có rủi ro cao hơn** việc tắt một process: một thay đổi firewall/network policy sai có thể cô lập cả môi trường.

### 17.1. Mục tiêu diễn tập

- Khi các nhóm member không liên lạc được, cụm có **ngăn ghi không an toàn** ở phía không đủ quorum không?
- Những request Java nào thành công, timeout hoặc bị từ chối?
- DNS và proxy có còn gửi traffic tới member không thể phục vụ ghi không?
- Khi mạng trở lại, cluster có hồi phục không?
- Sau hồi phục có sai lệch graph hoặc ghi lặp do ứng dụng retry không?

### 17.2. Mô hình logic

~~~text
Trước lỗi:
  [A] --- [B] --- [C]

Phân vùng mạng:
  [A]       [B] --- [C]

Nhóm B,C có thể giữ đa số theo điều kiện cấu hình.
A không được tự commit ghi độc lập chỉ vì process vẫn chạy.
~~~

Trong ví dụ nhóm ba member có voting tương ứng, nhóm hai có thể giữ đa số; đây không phải quy tắc cho mọi cluster/database có bất kỳ số member nào. Cần căn cứ topology thực tế.

### 17.3. Không gây network partition tùy tiện trên production

Bài diễn tập nên diễn ra ở staging hoặc môi trường test mô phỏng topology. Muốn làm trên production phải có kế hoạch change được phê duyệt, blast radius, người trực, rollback mạng, tiêu chí dừng và cửa sổ thực hiện.

**Không được dùng “xóa data directory để ép resync” như một bước thử nghiệm phổ thông.** Recovery, server replacement và topology change phải theo quy trình chính thức tương ứng.

## 18. Diễn tập các dạng lỗi khác

Một kế hoạch tốt không dừng ở “tắt một node”.

| Sự cố mô phỏng | Mục tiêu | Chỉ tiêu chính |
|---|---|---|
| Một primary/member dừng | Failover, routing, write availability | Thời gian writer usable, lỗi ứng dụng |
| Một secondary dừng | Khả năng đọc và tải phân bố | Read latency, replica catch-up |
| Mạng chập chờn/packet loss | Retry, timeout, election stability | Transaction errors, latency |
| DNS trả IP cũ | Client reconnect/cutover | Routing errors, pool reconnect |
| TLS certificate gần hết hạn | Alert và quy trình gia hạn | Không gián đoạn kết nối |
| Một disk đầy trong test | Phát hiện và xử lý lưu trữ | Alert trước nguy hiểm, recovery |
| Quá tải ghi tại node nóng | Deadlock/lock contention | Retry, p99, error rate |
| Backup job thất bại | Cảnh báo RPO | Tuổi backup hợp lệ |
| Restore từ bản gần nhất | Đo RPO/RTO | Phục hồi và đối soát dữ liệu |
| Mất cả failure domain | Khả năng DR độc lập | Thời gian dựng môi trường khác |
| Outbox dispatcher crash | Redelivery | Không nhân đôi tác dụng kinh doanh |
| Java app crash sau commit | Ambiguous commit | Receipt/idempotency phát huy tác dụng |

Các bài thử có chủ đích cần thực hiện trong phạm vi được phép; không đưa các lệnh phá hủy/partition cụ thể vào tài liệu để tránh chạy nhầm môi trường.

### 18.1. Diễn tập mất cả vùng chứa cluster

Nếu tất cả member nằm trong **một failure domain**, cluster replication không bảo vệ trước sự cố mất vùng đó. Một bài DR nâng cao có thể mô phỏng việc vùng chính không khả dụng rồi dựng lại dịch vụ từ **backup nằm ngoài vùng ảnh hưởng**.

Bài tập này cần đảm bảo:

- Có compute và network thay thế.
- Có quyền truy cập backup artifact và secret.
- Có file cấu hình/manifest hạ tầng.
- Có quy trình DNS/certificate/proxy cutover.
- Có bước xác minh database và source dữ liệu bên ngoài.
- Có người xác nhận nghiệp vụ trước khi mở lại ghi.

## 19. Java Driver: smoke test read/write và routing

Java Driver giúp ứng dụng sử dụng `executeRead` và `executeWrite` cho các transaction được driver quản lý, cùng khả năng routing/retry phù hợp theo phiên bản.

Ví dụ **smoke test đọc**:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class ClusterReadSmokeTest {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");
        String database = System.getenv("NEO4J_DATABASE");

        if (uri == null || user == null ||
                password == null || database == null) {
            throw new IllegalArgumentException(
                "Neo4j configuration is incomplete"
            );
        }

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            try (Session session = driver.session(
                    SessionConfig.forDatabase(database))) {
                long value = session.executeRead(tx ->
                    tx.run("RETURN 1 AS value")
                      .single()
                      .get("value")
                      .asLong()
                );
                if (value != 1L) {
                    throw new IllegalStateException(
                        "Unexpected Cypher result"
                    );
                }
                System.out.println("Cluster read smoke test PASS");
            }
        }
    }
}
~~~

Code này chỉ xác nhận kết nối và truy vấn đơn giản tại thời điểm chạy. Nó **không chứng minh failover, khả năng ghi hay dữ liệu nghiệp vụ đã nhất quán**.

### 19.1. Smoke test ghi không được làm bẩn production

Thay vì `CREATE` một node bất kỳ trong production, hãy:

1. Chọn database **test/canary** được phê duyệt.
2. Tạo một định danh cố định cho mỗi lệnh thử.
3. Ghi trong transaction có uniqueness/idempotency phù hợp.
4. Đọc lại để xác nhận.
5. Dọn dữ liệu canary theo quy trình an toàn.

Ví dụ câu Cypher cho một database canary:

~~~cypher
MERGE (c:ClusterCanary {checkId: $checkId})
ON CREATE SET c.createdAt = datetime()
SET c.lastCheckedAt = datetime()
RETURN c.checkId AS checkId;
~~~

Thiết lập uniqueness constraint trên `ClusterCanary.checkId` trước khi cho nhiều worker cùng dùng canary. Không chạy query ghi này trên database thật nếu chưa được cho phép; nếu dùng live readiness, tránh tạo write load hoặc spam event.

### 19.2. Callback có thể retry

Không đưa email, thanh toán hoặc publish broker vào callback `executeWrite` chỉ vì muốn smoke test nghiệp vụ. Callback managed transaction có thể chạy lại khi gặp lỗi phù hợp. Nếu cần phát event, dùng outbox và cơ chế idempotency, không trộn side effect vào transaction.

### 19.3. Routing và bookmark

Với URI `neo4j+s://...`, driver có thể khám phá endpoint từ routing table. Nếu cluster sau proxy/NAT công bố hostname private không reachable từ Java Pod/client, bootstrap có thể hoạt động nhưng query vẫn lỗi.

Sau failover, nếu nghiệp vụ cần read-your-writes giữa các session, hãy dùng bookmark manager/causal consistency theo API phiên bản Driver. Không dùng sleep cố định rồi coi như mọi replica đã theo kịp.

## 20. Runbook phản ứng sự cố cluster

Một runbook cụ thể giúp giảm thời gian ra quyết định dưới áp lực.

### 20.1. Giai đoạn nhận diện

1. Xác định **database và endpoint nghiệp vụ** bị ảnh hưởng.
2. Phân biệt lỗi read, write, routing, TLS, authentication hay query latency.
3. Xem dashboard member/DB/driver và mốc thay đổi gần nhất.
4. Ghi nhận thời điểm bắt đầu sự cố để đo RTO.
5. Kích hoạt mức ưu tiên và liên hệ người trực theo chính sách.

### 20.2. Giai đoạn khoanh vùng

- Nếu một server crash: kiểm tra tài nguyên, logs và trạng thái các server khác.
- Nếu mất quorum: xác định failure domain và tình trạng connectivity; không cưỡng ép ghi trên phần minority.
- Nếu routing lỗi: kiểm tra DNS/advertised endpoint, proxy, certificate, firewall từ môi trường Java.
- Nếu disk đầy: dùng quy trình giải phóng/tăng dung lượng được hỗ trợ; không xóa file DB tùy tiện.
- Nếu dữ liệu sai do lệnh nghiệp vụ: khoanh vùng tác động, dừng nguồn ghi lỗi và đánh giá restore/reconciliation trước khi tiếp tục.

### 20.3. Giai đoạn khôi phục

Thứ tự ưu tiên theo trường hợp:

1. Bảo vệ dữ liệu khỏi thao tác tiếp diễn gây hỏng.
2. Khôi phục connectivity hoặc member theo hướng dẫn phiên bản.
3. Đảm bảo database có thể nhận read/write phù hợp.
4. Xác nhận những lệnh có kết quả commit không rõ bằng receipt/log nghiệp vụ.
5. Kiểm tra graph invariants và độ trễ.
6. Mở traffic dần nếu cơ chế deployment cho phép.

**Không dùng restore như phản xạ đầu tiên cho mọi lỗi server.** Một member down có thể được thay thế/phục hồi mà không cần rollback toàn bộ dữ liệu về backup cũ. Phương án restore chỉ được chọn khi mục tiêu và phạm vi mất dữ liệu đã được đánh giá.

### 20.4. Giai đoạn đóng sự cố

- Ghi rõ timeline.
- Ghi RTO thực tế và điểm dữ liệu mới nhất đã phục hồi.
- Phân tích retry, duplicate, pending outbox và các event cần replay.
- Lập danh sách điều chỉnh monitor, backup, runbook và topology.
- Lên lịch kiểm tra lại biện pháp khắc phục.

## 21. Mẫu kế hoạch diễn tập có thể dùng ngay

| Trường | Nội dung cần điền |
|---|---|
| Mã diễn tập | `neo4j-drill-staging-001` |
| Môi trường | Staging/DR cô lập |
| Database | Tên database test |
| Neo4j version/edition | Ghi rõ |
| Topology | Số primary, secondary, failure domain |
| Mục tiêu | Ví dụ xác nhận failover khi một member dừng |
| Dữ liệu | Canary và tập business invariant |
| Tải thử | Read/write RPS nhỏ theo giới hạn an toàn |
| Trigger | Sự kiện giả lập đã được phê duyệt |
| Người thực hiện | Operator và người giám sát |
| Tiêu chí dừng | Mức lỗi, mất quorum, ảnh hưởng ngoài phạm vi |
| Rollback | Cách phục hồi member/network |
| SLI/SLO | Số liệu theo hợp đồng |
| RPO/RTO dự kiến | Giá trị do nghiệp vụ phê duyệt |
| Bằng chứng | Dashboard, logs, timeline, kết quả Cypher |
| Kết quả | PASS/FAIL/PARTIAL và phát hiện |
| Hành động sau thử | Chủ sở hữu, deadline và phương án |

### 21.1. Điều kiện dừng an toàn

Trước mỗi diễn tập, xác định:

- Không có production traffic bị đưa nhầm vào môi trường test.
- Không sử dụng dữ liệu hoặc secret production ngoài phạm vi được phép.
- Có cách dừng thao tác gây lỗi và phục hồi network.
- Có backup/restore point cần thiết.
- Có người chịu trách nhiệm ra quyết định.
- Có ngưỡng lỗi hoặc tác động vượt mức phải dừng bài thử.
- Không gây xóa/ghi đè database không thuộc bài thử.

Một bài diễn tập có kết quả **FAIL có bằng chứng** vẫn có giá trị nếu phát hiện sớm điểm yếu và không gây tổn hại môi trường ngoài phạm vi.

## 22. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Có ba bản sao nên không cần backup | Xóa nhầm được nhân bản tới mọi member | Backup độc lập, retention và restore drill |
| Đếm process up = cluster healthy | Mất writer/quorum vẫn không được phát hiện | SLI read/write và trạng thái database |
| Chỉ monitor leader hiện tại | Role thay đổi sau failover | Quan sát tất cả member/database, routing |
| Backup job exit 0 là đủ | Artifact có thể không restore được | Khôi phục thử và kiểm tra dữ liệu |
| Backup nằm cùng một volume/zone với cluster | Một sự cố có thể làm mất cả hai | Copy sang failure domain khác, kiểm tra truy cập |
| Không biết RPO/RTO | Không có cơ sở chọn lịch backup và drill | Được nghiệp vụ phê duyệt trước |
| Restore thẳng vào production để thử | Có thể mất dữ liệu đang chạy | Restore cô lập, không overwrite production |
| Chỉ đo thời gian lệnh restore | Bỏ qua DNS, secret, routing và validation | Đo RTO đầu-cuối |
| Chỉ kiểm tra số node | Có thể mất relationship hoặc sai bất biến | Kiểm tra invariants/schema/đối soát |
| Bỏ qua system metadata/role | Database phục hồi nhưng ứng dụng không truy cập | Kế hoạch phục hồi metadata và cấu hình |
| Đọc được `RETURN 1` coi như ghi được | Mất quorum ghi không lộ qua read test | Smoke test write an toàn và SLI write |
| Dùng IP private trong routing cho client public | Bootstrap chạy, query thất bại | Advertised endpoints reachable |
| Retry cùng lệnh cộng điểm không có ID | Áp dụng delta lặp | Receipt/idempotency key |
| Gửi email trong callback có retry | Tác dụng phụ lặp | Outbox/dispatcher |
| Xóa transaction log thủ công khi đầy disk | Có thể làm hỏng recovery | Dùng quy trình Neo4j được hỗ trợ |
| Chỉ diễn tập tắt một server | Không biết hệ thống xử lý partition/region loss ra sao | Bộ kịch bản đa mức |
| Không có rollback cho network test | Thử nghiệm có thể thành sự cố thật | Tiêu chí dừng và rollback phê duyệt |
| Chụp query/parameter nhạy cảm lên dashboard | Lộ dữ liệu khách hàng | Redaction/allowlist và RBAC |

## 23. Bài tập vận dụng

### Bài 1 — Replication và xóa nhầm

Cluster có ba thành viên khỏe mạnh. Một lệnh Cypher xóa nhầm 2.000 node được commit và nhân bản.

**Câu hỏi:** Vì sao không thể “lấy bản còn lại trong cluster” theo cách mặc định để có dữ liệu cũ?

**Đáp án:** Replication áp dụng các thay đổi đã commit; những bản sao theo kịp cũng có thể đã mất 2.000 node. Cần đánh giá backup/khả năng phục hồi lịch sử hoặc rebuild từ nguồn có thẩm quyền.

### Bài 2 — Mất quorum

Một database dùng nhóm ba thành viên bỏ phiếu. Hai thành viên không thể liên lạc, chỉ còn một thành viên hoạt động.

**Câu hỏi:** Có nên ép thành viên còn lại tiếp tục nhận ghi để tránh downtime không?

**Đáp án:** Không. Nó không còn đa số theo mô hình đồng thuận của ví dụ. Cho ghi độc lập có thể phá bất biến. Cần phục hồi connectivity/quorum hoặc dùng quy trình DR được hỗ trợ.

### Bài 3 — Backup có file nhưng chưa restore

Job backup chạy hằng đêm, dashboard báo thành công. Tổ chức chưa từng restore thử.

**Câu hỏi:** Có thể nói RTO được bảo đảm không?

**Đáp án:** Không. Chưa biết tốc độ tải backup, restore, khởi động database, DNS/TLS/role, kiểm chứng dữ liệu và mở lại ứng dụng. Phải diễn tập đầu-cuối.

### Bài 4 — Chênh lệch giữa backup và nguồn sự kiện

Backup được tạo khi dữ liệu ở mốc 09:55. Đến 10:00 xảy ra sự cố; hệ thống bên ngoài vẫn lưu một số đơn đã được xác nhận trong năm phút cuối.

**Câu hỏi:** Sau restore chỉ cần kiểm tra database online là đủ chưa?

**Đáp án:** Chưa. Cần đối chiếu/replay những command/event đã xác nhận nhưng không nằm trong điểm khôi phục, giữ ID ổn định để tránh xử lý trùng.

### Bài 5 — Read thành công, write thất bại

Sau lỗi mạng, một API đọc vẫn trả kết quả, nhưng tạo Order liên tục timeout.

**Câu hỏi:** Cần ưu tiên dashboard nào?

**Đáp án:** Trạng thái database writer/quorum, write SLI, routing/write errors và topology. Process health hoặc read SLI đơn lẻ không đủ.

### Bài 6 — Client bootstrap nhưng không chạy được query

Java Driver qua proxy kết nối bootstrap thành công, routing table trả địa chỉ `neo4j-1.internal:7687` không resolve được từ client.

**Câu hỏi:** Có nên tăng pool size để xử lý không?

**Đáp án:** Không. Cần thiết kế DNS/advertised endpoint/routing reachability, không phải tăng số connection.

### Bài 7 — Sao lưu nhiều database

Ứng dụng có database `orders` và `customers`, được backup tại hai thời điểm khác nhau.

**Câu hỏi:** Có thể khẳng định chúng tạo thành cùng một snapshot nghiệp vụ không?

**Đáp án:** Không. Cần quy tắc nhất quán/reconciliation, version hoặc các biện pháp điều phối phù hợp; backup độc lập từng database không tự tạo distributed transaction.

### Bài 8 — Diễn tập một member

Trong staging, một primary bị dừng, read phục hồi nhanh, nhưng write retry gây 40 lệnh có kết quả không rõ.

**Câu hỏi:** Ngoài việc khởi động lại member, phải làm gì?

**Đáp án:** Kiểm tra receipt/commandId, đối chiếu lệnh đã commit, xử lý retry/duplicate và đo thời gian writer usable; không cho chạy lại 40 lệnh với ID mới.

### Bài 9 — Backup port

Người vận hành mở port backup cho Internet để một máy backup ở ngoài VPC truy cập.

**Câu hỏi:** Tại sao cần thay thiết kế?

**Đáp án:** Backup có thể tiếp cận dữ liệu rất nhạy cảm. Nên dùng kênh private/VPN/đường vận hành bảo vệ phù hợp, giới hạn nguồn và quyền, thay vì mở public rộng.

### Bài 10 — Diễn tập kết thúc lúc nào?

Một restore test chạy lệnh xong lúc 10:10, database online 10:12, Java API truy cập được lúc 10:17 và nghiệp vụ xác nhận dữ liệu đúng lúc 10:20.

**Câu hỏi:** Mốc nào phản ánh RTO phục vụ nghiệp vụ tốt hơn?

**Đáp án:** Nếu định nghĩa RTO là lúc dịch vụ trở lại đầy đủ chức năng và dữ liệu hợp lệ, mốc 10:20 phù hợp hơn mốc “lệnh restore kết thúc”. Định nghĩa phải được thống nhất trước khi test.

## 24. Checklist nghiệm thu giám sát và khôi phục

### 24.1. Cluster và ứng dụng

- [ ] Biết rõ topology, edition, phiên bản và failure domain của từng database.
- [ ] Có giám sát member/database/writer và điều kiện mất khả năng ghi.
- [ ] Phân biệt SLI read, write, routing, latency và lỗi nghiệp vụ.
- [ ] Java Driver dùng URI routing/endpoint đúng với mạng client.
- [ ] Các advertised endpoint reachable từ ứng dụng.
- [ ] Có timeout/retry có giới hạn, idempotency và kiểm soát tác dụng phụ ngoài DB.
- [ ] Có chính sách bookmark/causal consistency khi nghiệp vụ yêu cầu.

### 24.2. Backup và artifact

- [ ] RPO/RTO được xác định và phê duyệt.
- [ ] Biết database nào phải backup và metadata nào cần bảo vệ.
- [ ] Dùng công cụ/format backup được phiên bản Neo4j hỗ trợ.
- [ ] Backup endpoint và kho lưu được bảo vệ quyền/network/encryption.
- [ ] Có retention, bản sao offsite và bảo vệ xóa nhầm.
- [ ] Dashboard theo dõi tuổi recovery point hợp lệ, không chỉ job status.
- [ ] Có manifest/artifact/version để tái lập restore.
- [ ] Đã phục hồi thử ít nhất một bản theo lịch và lưu bằng chứng.

### 24.3. DR và diễn tập

- [ ] Có môi trường DR/restore cô lập, không ghi đè production.
- [ ] Có runbook mất member, mất quorum, network partition và vùng dữ liệu.
- [ ] Có điều kiện dừng, người trực, quyền phê duyệt và kế hoạch rollback.
- [ ] Đo detection time, write recovery, RTO và recovery point thực tế.
- [ ] Sau restore đã kiểm tra node, relationship, schema, quyền và bất biến nghiệp vụ.
- [ ] Có quy trình đối chiếu những transaction có kết quả không rõ.
- [ ] Có kế hoạch replay/outbox/broker cho dữ liệu phát sinh sau recovery point.
- [ ] Đã kiểm tra Java application thực sự đọc/ghi được sau phục hồi.
- [ ] Mỗi bài diễn tập có báo cáo PASS/FAIL/PARTIAL và hành động cải tiến.

## 25. Ghi nhớ

**Giám sát cluster Neo4j** không thể chỉ dựa vào số server đang chạy. Cần quan sát **khả năng ghi, trạng thái từng database, điều kiện đồng thuận, routing của Java Driver, độ theo kịp dữ liệu, độ trễ truy vấn, tài nguyên và các thao tác nghiệp vụ**. Một server còn online hoặc một lệnh `RETURN 1` thành công chưa chứng minh toàn cụm đang đáp ứng yêu cầu ứng dụng.

**Replication không thay thế backup**: dữ liệu bị xóa hoặc sửa sai có thể được sao chép tới mọi thành viên. Backup phải nằm trong chính sách **RPO/RTO, retention, bảo mật, lưu độc lập và restore test**; khả năng khôi phục được chứng minh bằng **database hoạt động, graph đúng bất biến và Java service sử dụng được**, chứ không chỉ một file backup xuất hiện. Cuối cùng, diễn tập lỗi member, mất quorum, network partition và khôi phục từ backup trong môi trường an toàn giúp phát hiện sớm những điểm yếu về topology, dữ liệu, DNS, quyền, retry và quy trình phản ứng sự cố.
