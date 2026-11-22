# JMX, cơ chế xuất metric và điều kiện bảo vệ truy cập trong Apache Cassandra

## 1. Mục tiêu: quan sát được cluster mà không mở thêm một lỗ hổng quản trị

Trong **Apache Cassandra**, hệ quản trị cơ sở dữ liệu **wide-column phân tán**, một truy vấn CQL từ ứng dụng Java có thể liên quan tới coordinator, nhiều replica, memtable, SSTable, cache, compaction và repair. Khi latency hoặc timeout tăng, kỹ sư cần quan sát được các thành phần này. Một nguồn quan sát quan trọng là **Java Management Extensions (JMX)**.

JMX cho phép đọc trạng thái/metric của tiến trình Java thông qua **MBean** (*managed bean*). Cassandra sử dụng cơ chế này để công bố nhiều metric nội bộ và phục vụ một số công cụ quản trị, trong đó có `nodetool`. Các hệ thống như Prometheus thường không đọc trực tiếp JMX theo cách nguyên bản; chúng cần **exporter** để chuyển dữ liệu thành định dạng có thể thu thập.

Tuy nhiên, **JMX không chỉ là một endpoint đọc metric**. Một số MBean còn hỗ trợ thao tác quản trị có thể ảnh hưởng hoạt động cluster. Vì thế, việc bật JMX từ xa, mở cổng exporter hay cấp quyền truy cập phải được thiết kế như một phần của **bề mặt bảo mật hệ thống**, không phải một bước phụ của việc dựng dashboard.

Sau bài này, người học có thể:

- Giải thích mối quan hệ giữa **JVM → MBean → JMX → exporter → hệ giám sát**.
- Phân biệt **metric Cassandra, metric JVM, metric hệ điều hành** và metric ở **Java Driver/ứng dụng**.
- Lựa chọn mô hình thu thập phù hợp với node, datacenter, keyspace, table và loại request.
- Hiểu phạm vi truy cập của **JMX local**, **JMX remote** và **HTTP metrics endpoint**.
- Thực hiện kiểm tra kết nối/metric có kiểm soát, biết xử lý lỗi RMI, firewall, xác thực, TLS và metric bị mất.
- Xây dựng checklist triển khai, cảnh báo và đáp án cho các tình huống vận hành.

> **Phạm vi phiên bản:** Cách bật JMX, tên MBean, tên metric, cổng và khả năng cấu hình TLS/xác thực có thể khác giữa Cassandra 3.x, 4.x, 5.x, bản phân phối và phiên bản JDK/JMX Exporter. Các cấu hình trong bài là ví dụ học tập cần đối chiếu với tài liệu **đúng deployment**, không phải mẫu cấu hình production có thể áp dụng nguyên xi.

## 2. JMX là gì? MBean khác một metric như thế nào?

**JMX** là tập API/cơ chế quản lý và giám sát ứng dụng Java. Một tiến trình JVM có thể đăng ký các **MBean** trong `MBeanServer`. Mỗi MBean có **ObjectName**; bên trong có thể có:

1. **Attribute**: giá trị có thể đọc, chẳng hạn số lần request, độ trễ, số task đang chờ.
2. **Operation**: thao tác có thể gọi, đôi khi **thay đổi trạng thái** ứng dụng.
3. **Notification**: sự kiện quản lý được phát ra, tùy MBean.

Một metric thường là **một attribute hoặc một nhóm thuộc tính có ý nghĩa đo lường**. Một MBean không nhất thiết tương ứng đúng một series trong Prometheus; exporter quyết định cách ánh xạ các attribute đó.

Ví dụ ObjectName dạng thường gặp trong Cassandra:

```text
org.apache.cassandra.metrics:
    type=ClientRequest,
    scope=Read,
    name=Latency
```

Ở đây `type` phân loại nhóm metric, `scope` nhận diện loại request, còn `name` xác định metric. Các attribute có thể chứa `Count` hoặc những thống kê latency; phải kiểm tra **đơn vị và loại metric thực tế** của phiên bản trước khi xây biểu đồ.

Với metric theo bảng, một dạng tên thường thấy là:

```text
org.apache.cassandra.metrics:
    type=Table,
    keyspace=telemetry_ks,
    scope=readings_by_device_day,
    name=LiveDiskSpaceUsed
```

Đây là ví dụ mô tả cấu trúc: **mỗi node có MBean/giá trị cục bộ**, không phải một chỉ số đã tổng hợp cho cả cluster. Một keyspace có RF = 3 không có nghĩa một JMX endpoint sẽ tự cộng tất cả replica.

## 3. Bốn nguồn telemetry không được đánh đồng

| Nguồn | Nó đo ở đâu? | Ví dụ | Giới hạn |
|---|---|---|---|
| **Cassandra JMX** | Trong JVM node Cassandra | ClientRequest, Table, Keyspace, ThreadPools, Compaction | Không trực tiếp biết latency của một API cụ thể |
| **JVM metrics** | JVM của Cassandra | Heap, GC, threads, buffer pools | Không phản ánh đầy đủ dung lượng/IO host |
| **Host/container metrics** | Hệ điều hành, VM hoặc container | CPU, disk available, I/O latency, network | Không biết query CQL nào đang gây tải |
| **Java Driver/ứng dụng** | JVM ứng dụng gọi Cassandra | Logical request latency, retries, in-flight, timeouts | Không tự giải thích replica nào nghẽn |

Một dashboard tốt thường ghép các nguồn nhưng giữ **phạm vi, đơn vị và nhãn nguồn đo**.

Ví dụ: API chậm nhưng `ClientRequest.Read.Latency` ở các coordinator vẫn bình thường có thể do **driver connection pool**, JVM ứng dụng hoặc network. Ngược lại, coordinator latency cao có thể do một replica chậm, dù CPU của coordinator thấp.

**Không khẳng định CPU thấp = Cassandra khỏe; cũng không khẳng định JMX có dữ liệu = người dùng không gặp lỗi.** Cần nhìn đồng thời request rate, errors, p95/p99 latency và saturation.

## 4. Luồng xuất metric từ node Cassandra ra hệ giám sát

```text
            +----------------------+
            |   Cassandra JVM      |
            |                      |
            |   MBeanServer        |
            |   + Cassandra MBeans |
            |   + JVM MBeans       |
            +----------+-----------+
                       |
                   JMX attributes
                       |
          +------------+----------------+
          |                             |
          v                             v
   Local JMX access              JMX exporter/agent
   nodetool / JConsole           ánh xạ MBean -> metric
   (quản trị được phép)                   |
                                         v
                                 HTTP /metrics endpoint
                                         |
                               Prometheus hoặc collector
                                         |
                                Dashboard / alert / SLO
```

Tách thành **hai mặt phẳng**:

- **Mặt phẳng quản trị**: JMX có khả năng đọc thuộc tính và có thể gọi operation. Quyền phải rất hạn chế.
- **Mặt phẳng giám sát**: exporter chuyển các attribute đã chọn thành số đo và công bố qua HTTP(S) hoặc hệ thống collector. Mục tiêu là **chỉ đọc metric**, không cấp khả năng điều hành MBean cho người chỉ xem dashboard.

Một Prometheus scrape thành công **không chứng minh** người thu thập có quyền dùng JMX, cũng không nên yêu cầu mở JMX remote cho cả mạng giám sát nếu dùng agent nằm trong chính JVM.

## 5. Các cách truy cập JMX: local, remote và Java agent

| Mô hình | Đường truy cập | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|---|
| **Local JMX** | Công cụ trên chính node tới JMX loopback/connector cục bộ | Không cần mở JMX ra mạng ngoài | Vẫn cần quyền truy cập host và bảo vệ tài khoản |
| **Remote JMX qua RMI** | Client từ máy khác kết nối JMX connector được phép | Dùng công cụ quản trị/collector từ xa | Mở bề mặt quản trị; RMI, firewall, TLS, auth phức tạp |
| **Exporter dạng Java agent** | Exporter chạy trong JVM Cassandra, đọc MBean cục bộ | Không cần cấp remote JMX chỉ để lấy metric | Agent và cổng HTTP metrics cần được bảo vệ; có overhead |
| **Exporter dạng standalone** | Một tiến trình riêng kết nối JMX từ xa | Tách tiến trình thu thập khỏi Cassandra | Cần cấu hình JMX remote an toàn; có thêm network hop |
| **Agent/sidecar nội bộ** | Collector đọc endpoint nội bộ và chuyển metric | Phù hợp mô hình container, hạn chế phơi bày cổng | Cần bảo vệ network namespace, service account và telemetry pipeline |

**Lựa chọn thường hợp lý:** nếu mục tiêu chỉ là Prometheus metrics, cân nhắc exporter **đọc MBean tại node** và công bố metric ra mạng giám sát riêng, thay vì bật một cổng remote JMX có quyền quản trị cho nhiều hệ thống.

Việc triển khai agent/sidecar phải xét phiên bản Cassandra, JDK, container, bộ thu thập và chi phí vận hành. Không có một mô hình duy nhất đúng cho mọi deployment.

## 6. Những cổng thường gặp và ý nghĩa bảo mật

| Cổng ví dụ | Chức năng thường gặp | Có thay thế nhau không? |
|---|---|---|
| `9042` | Native transport của CQL/client driver trong nhiều cấu hình Cassandra | **Không** phải JMX |
| `7199` | JMX được `nodetool` sử dụng trong nhiều cấu hình mặc định | **Không** phải CQL hoặc HTTP metrics |
| `9404` | Cổng ví dụ thường chọn cho endpoint `/metrics` của JMX exporter | **Không** phải cổng chuẩn bắt buộc |
| Các cổng internode tùy cấu hình | Giao tiếp giữa Cassandra nodes | Không nên cấp cho dashboard chỉ để scrape |

Cổng có thể thay đổi theo môi trường. Hãy kiểm tra cấu hình service/JDK và cấu hình collector thay vì giả định tên cổng đủ để nhận diện giao thức.

### JMX RMI có thể không chỉ dùng một cổng

Với **remote JMX qua RMI**, kết nối có thể đi qua **RMI registry** rồi tới một đối tượng remote được quảng bá ở địa chỉ/cổng khác. Nếu JDK/connector không được cố định theo cấu hình thích hợp, một firewall chỉ mở cổng registry có thể chưa đủ.

Các thuộc tính JVM thường được nhắc tới trong tài liệu JMX/RMI gồm:

```text
com.sun.management.jmxremote.port
com.sun.management.jmxremote.rmi.port
java.rmi.server.hostname
```

**Không coi đây là cấu hình hoàn chỉnh.** Phải kiểm tra JDK, cấu hình Cassandra, TLS và chính sách mạng. Đặc biệt, không sửa thành **tắt xác thực hoặc tắt mã hóa** chỉ để “sửa lỗi exporter không kết nối được”.

## 7. `nodetool` sử dụng JMX: bằng chứng và quyền quản trị

Trong nhiều bản Cassandra, `nodetool` là client dùng JMX để đọc thông tin và gọi các thao tác quản trị. Các lệnh **đọc để chẩn đoán** thường gặp:

```bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool tablestats telemetry_ks.readings_by_device_day
```

| Lệnh | Mục đích quan sát | Cần lưu ý |
|---|---|---|
| `status` | Trạng thái node và token/định tuyến cluster | Chỉ một snapshot, không phải alert liên tục |
| `info` | Thông tin node, một số trạng thái JVM/storage | Format khác nhau giữa phiên bản |
| `tpstats` | Thread pools, pending và dropped tasks/messages | Cần đối chiếu workload cùng thời điểm |
| `compactionstats` | Công việc compaction hiện tại/đang chờ | Không khẳng định tombstone sẽ dọn xong ngay |
| `tablestats` | Metric/thống kê theo table trên node | Không phải tổng logical reads của toàn cluster |

Các lệnh trên chủ yếu dùng để quan sát, nhưng `nodetool` còn có các thao tác **thay đổi hệ thống**, ví dụ repair, flush, compact, decommission hoặc thay cấu hình runtime tùy phiên bản. Vì thế **quyền JMX có thể là quyền vận hành cluster**, không chỉ quyền xem số liệu.

**Không cho một tài khoản dashboard quyền JMX quản trị đầy đủ** chỉ để scraper đọc metric. Nên phân tách quyền vận hành Cassandra với quyền đọc/thu thập telemetry.

## 8. Tên MBean, nhóm metric và các giới hạn khi export

Cassandra thường tổ chức MBean theo những nhóm có tên tương tự:

| Nhóm thường gặp | Điều muốn đo | Lưu ý |
|---|---|---|
| `ClientRequest` | Read/write request count, latency, timeout | Coordinator-level, không nhất thiết có label keyspace |
| `Table` | SSTable, memtable, disk, row/cell scan, latency | Một table tại **một node** |
| `Keyspace` | Workload/metric liên quan keyspace | Các thuộc tính hỗ trợ khác nhau theo version |
| `ThreadPools` | Active/pending/completed tasks | Mục tiêu là phát hiện saturation |
| `Compaction` | Pending/completed compaction | Không đồng nghĩa byte reclaim ngay |
| `Cache` | Hits, misses, size/capacity | Phân biệt loại cache và workload |
| `DroppedMessage` | Thông điệp xử lý bị bỏ | Có thể liên quan queue/saturation |
| JVM `java.lang` | Heap, GC, threads | Không biết partition nào đang gây tải |

Ví dụ một ObjectName dạng `ClientRequest.Read.Latency` có thể chứa `Count`, `Mean`, `50thPercentile`, `99thPercentile` hoặc các thống kê khác. **Đơn vị latency có thể khác** giữa cách xuất JMX, quy ước Cassandra và exporter: phải kiểm tra trước khi biểu diễn ra milliseconds/seconds.

Exporter có thể:

- **Giữ nguyên** tên/nhóm metric (dẫn tới tên dài, khó thống nhất).
- **Đặt tên mới** theo mapping, ví dụ chuyển thuộc tính đếm thành counter `..._total`.
- **Bỏ bớt** MBean không cần thiết để giảm số series.
- **Gắn label** `cluster`, `datacenter`, `node`, `keyspace`, `table`, `request_type` theo định nghĩa.

Nhưng không thể tự suy rằng mỗi percentile gauge trong JMX là một Prometheus histogram. Nếu không có `*_bucket` với bucket hợp lệ, **không dùng `histogram_quantile()`** trên dữ liệu đó.

## 9. Exporter dạng Java agent: ví dụ triển khai trong môi trường thử nghiệm

Một hướng thường gặp là dùng **JMX Exporter Java agent** đọc MBean ngay trong tiến trình Cassandra và công bố endpoint metric.

Ví dụ JVM argument **minh họa**:

```text
-javaagent:/opt/monitoring/jmx_prometheus_javaagent.jar=127.0.0.1:9404:/etc/cassandra/jmx-exporter.yaml
```

Ý định của ví dụ là **chỉ bind loopback** để thử cục bộ, nếu phiên bản exporter hỗ trợ cú pháp host:port này. Tên JAR, cách nạp vào JVM và vị trí cấu hình phải được kiểm tra theo bản exporter và cách Cassandra được cài đặt. Đừng thêm argument vào một tiến trình đã chạy rồi tưởng có tác dụng: **Java agent nạp khi JVM khởi động**, nên thường cần cơ chế rollout/restart được kiểm soát.

### Cấu hình mapping minh họa

```yaml
# Chỉ là ví dụ về quy tắc mapping; kiểm tra ObjectName
# thực tế với phiên bản Cassandra/JMX Exporter đang dùng.
lowercaseOutputName: true
lowercaseOutputLabelNames: true
rules:
  - pattern: 'org.apache.cassandra.metrics<type=ClientRequest, scope=(.*), name=Latency><>Count'
    name: cassandra_client_request_latency_count
    type: COUNTER
    labels:
      operation: "$1"
```

Quy tắc này minh họa cách lấy attribute `Count` của một MBean có tên tương ứng và xuất thành counter có nhãn `operation`. **Không coi pattern là hợp đồng áp dụng nguyên xi**: thứ tự thuộc tính ObjectName, tên MBean, kiểu giá trị và cách exporter parse phải được thử nghiệm. Khi lỗi, xem metric thực ở endpoint thay vì kết luận Cassandra không có hoạt động.

### Thử đọc endpoint cục bộ

```bash
# Chạy trên node/container thử nghiệm được phép,
# với exporter được cấu hình chỉ nghe loopback.
curl --fail --silent http://127.0.0.1:9404/metrics
```

Kết quả là dữ liệu định dạng text metric; có thể thấy các dòng `# HELP`, `# TYPE` và series số nếu exporter cấu hình đúng. Cần xác minh có **metric Cassandra mong muốn**, không chỉ metric nội bộ của exporter.

**Bảo vệ truy cập:** cấu hình loopback có ích cho thử nghiệm tại node; nếu Prometheus chạy trên host khác, nó **không tự truy cập** được endpoint loopback này. Trong production, thiết kế một đường scrape qua **mạng giám sát riêng hoặc proxy có xác thực/TLS** và firewall, không chuyển ngay sang bind `0.0.0.0` rồi bỏ trống toàn bộ bảo vệ.

## 10. Exporter standalone: khi nào hợp lý và đánh đổi bảo mật

Một exporter chạy tách rời có thể kết nối đến **remote JMX** rồi xuất metric HTTP để collector lấy dữ liệu.

```text
Prometheus                   Exporter                  Cassandra node
    |  GET /metrics              |                           |
    +-------------------------->|                           |
    |                           |--- JMX/RMI + auth/TLS ---->|
    |                           |<--- MBean attributes ------|
    |<---- metrics text --------|
```

Đánh đổi:

1. **Ưu điểm:** exporter tách khỏi JVM Cassandra; có thể nâng cấp/khởi động lại độc lập trong một số mô hình.
2. **Phụ thuộc:** phải có JMX connector remote, thông suốt cả registry/RMI address, và credential/trust hợp lệ.
3. **Bảo mật:** exporter có thể giữ credential JMX; credential bị lộ có thể ảnh hưởng quyền quản trị node, tùy quyền được cấp.
4. **Độ tin cậy:** nếu exporter hoặc đường JMX hỏng, dashboard mất dữ liệu dù Cassandra vẫn phục vụ CQL bình thường.
5. **Chi phí:** thu thập quá thường xuyên hoặc truy vấn quá nhiều MBean có thể tăng tải trên JVM và collector.

Standalone exporter không “an toàn mặc định” chỉ vì tách process. Phải kiểm soát **hai đoạn**: exporter → Cassandra JMX và Prometheus → exporter metrics.

## 11. Thu thập bằng Prometheus: ví dụ và kiểm tra tính đúng đắn

Một cấu hình scrape **cục bộ trong lab** khi Prometheus chạy cùng host/network namespace với exporter:

```yaml
scrape_configs:
  - job_name: cassandra-jmx-lab
    scrape_interval: 30s
    scrape_timeout: 10s
    static_configs:
      - targets: ['127.0.0.1:9404']
        labels:
          cluster: 'cassandra-lab'
          datacenter: 'dc1'
```

Ở production, Prometheus có thể chạy trên host khác; khi đó cần target **thực sự định tuyến được qua kênh đã bảo vệ**, không sao chép `127.0.0.1` của lab. Với Kubernetes/VM, cần kiểm soát Service, NetworkPolicy/ACL, mTLS hoặc proxy tùy kiến trúc.

Một số truy vấn PromQL mẫu, giả sử exporter đã ánh xạ các series tương ứng:

```promql
# Kiểm tra collector có scrape thành công hay không.
up{job="cassandra-jmx-lab"}

# Tính tốc độ từ counter; tên bên dưới chỉ là ví dụ mapping.
sum by (instance, operation) (
  rate(cassandra_client_request_latency_count_total[5m])
)
```

**Cảnh báo về tên metric:** exporter có thể bổ sung `_total` cho counter theo quy tắc của phiên bản, hoặc đặt tên khác. Hãy xem `/metrics` để dùng **chính xác** tên xuất hiện. Không dựng alert chỉ từ tên đoán.

**Đừng so số lượng series scrape được với số request nghiệp vụ:** một client write có thể liên quan nhiều replica; exporter có thể có cả counter, rate và gauge cho cùng nhóm MBean. Luôn kiểm tra semantics trước khi tính throughput toàn cluster.

## 12. Quy tắc bảo mật tối thiểu cho remote JMX

**Remote JMX là cổng quản trị có rủi ro cao.** Chính sách an toàn thường gồm:

1. **Không bật remote JMX nếu không cần.** Ưu tiên local JMX/Java agent cho metrics khi khả thi.
2. **Giới hạn địa chỉ nghe và network ACL/firewall.** Chỉ những máy/bastion hoặc collector được phép mới có đường tới cổng JMX.
3. **Bật xác thực và phân quyền** theo cơ chế phù hợp bản JDK/Cassandra; dùng tài khoản chuyên biệt, quyền tối thiểu.
4. **Mã hóa kết nối/TLS** khi dữ liệu quản trị đi qua mạng; kiểm tra chứng chỉ, hostname, truststore và chính sách rotation.
5. **Khóa các đường quản trị ngoài ý muốn:** JMX có thể cho gọi operation, không chỉ đọc metric. Đánh giá những MBean mà tài khoản thực sự được phép thao tác.
6. **Bảo vệ bí mật:** không hard-code password trong script, args, URL, git repository, dashboard hay Prometheus labels. Dùng secrets manager hoặc cơ chế bảo vệ tương đương.
7. **Theo dõi truy cập và thay đổi cấu hình:** ai đã bật remote JMX, mở firewall, đổi quyền và từ đâu có thể kết nối.
8. **Kiểm tra sau upgrade:** JDK, Cassandra và exporter có thể thay đổi mặc định hoặc tham số xác thực.

Ở một số triển khai, file cấu hình quyền JMX hoặc cơ chế auth của Cassandra/JDK được dùng cho phân quyền. **Tên file, cú pháp và quyền cụ thể tùy phiên bản**. Không áp dụng một ví dụ `jmxremote.password` hoặc `jmxremote.access` mà chưa kiểm tra tích hợp hiện tại và quyền file (chỉ tài khoản service cần thiết được đọc).

> Không nên làm: bật JMX remote rồi vô hiệu hóa TLS/xác thực để `nodetool` hoặc exporter dễ kết nối. Điều đó có thể cấp cho người trong mạng quyền đọc metadata nhạy cảm hoặc tác động vào tiến trình Cassandra.

## 13. Điều kiện bảo vệ HTTP `/metrics` và hệ thống thu thập

Ngay cả khi exporter **chỉ xuất metric**, endpoint `/metrics` vẫn có thể tiết lộ:

- Tên **keyspace/table**, số node, datacenter/rack, phiên bản exporter hoặc JVM.
- Mức traffic, loại request, lượng dữ liệu, tỷ lệ lỗi và dấu hiệu tải.
- Kiến trúc nội bộ hoặc thời điểm sự cố nếu metric chứa nhãn quá chi tiết.

Vì vậy “read-only metrics” **không có nghĩa dữ liệu công khai vô hại**.

| Thành phần | Điều kiện bảo vệ |
|---|---|
| **Listener exporter** | Bind loopback/private IP hoặc socket trong phạm vi cần thiết; tránh Internet công khai |
| **Đường scrape** | Firewall, NetworkPolicy, mTLS/TLS proxy hoặc auth phù hợp topology |
| **Collector** | Service account riêng, egress giới hạn, credential/secret được quản lý |
| **Prometheus storage** | RBAC truy vấn, retention, mã hóa/backup theo chính sách |
| **Grafana/dashboard** | SSO/RBAC, giới hạn người xem thông tin hạ tầng |
| **Labels/logs** | Không chứa credential, token, raw CQL parameters, user/session IDs tùy ý |
| **Thay đổi cấu hình** | Review, audit trail, thử nghiệm trước rollout |

**Cẩn thận với network namespace:** `127.0.0.1` bên trong container của exporter có thể không phải loopback của Prometheus. Với Kubernetes sidecar cùng Pod, container thường chung network namespace; với Pod khác, loopback khác. Cần hiểu đường mạng thực tế, tránh khắc phục bằng cách phơi bày endpoint ra toàn cluster.

Nếu cần tập trung metric từ nhiều datacenter, thiết kế federation/remote-write hoặc collector cục bộ theo khả năng mạng; đừng mở JMX quản trị qua WAN chỉ để đặt một scraper ở một vị trí trung tâm.

## 14. Phân quyền theo vai trò: ai cần làm gì?

| Vai trò | Nhu cầu | Quyền tối thiểu nên cấp |
|---|---|---|
| **SRE/DBA trực vận hành** | Kiểm tra JMX/`nodetool`, điều tra sự cố | Quyền quản trị qua đường bảo vệ; có audit và quy trình |
| **Metrics collector** | Đọc chỉ số | Chỉ đọc telemetry cần thiết; không cần quyền JMX thay đổi hệ thống nếu có thể |
| **Developer ứng dụng** | Xem latency/error theo service | Dashboard/trace đã lọc, không cần remote JMX |
| **Nhóm phân tích dữ liệu** | Thống kê nghiệp vụ | Dữ liệu và metric nghiệp vụ được cấp riêng; không cần endpoint quản trị |
| **Automation repair/maintenance** | Thực hiện thao tác lên Cassandra | Tài khoản chuyên dụng, tác vụ/đích giới hạn, xác nhận và log |

**Nguyên tắc “least privilege”:** người cần xem biểu đồ không mặc nhiên cần quyền gọi một MBean operation; người được chạy `nodetool status` cũng không nên có quyền thay đổi cluster nếu cơ chế phân quyền triển khai cho phép tách bạch.

Trường hợp phiên bản/cơ chế JMX không hỗ trợ tách quyền đủ hẹp, cần **đặt một exporter/proxy chỉ đọc phía trước** và khóa hẳn remote JMX đối với người chỉ xem metric.

## 15. Quan sát có kiểm soát mà không tạo cardinality explosion

Một MBean theo table có thể sinh nhiều series vì mỗi series mang nhãn `instance`, `keyspace`, `table`, `metric`, `quantile`... Với hàng trăm bảng/nhiều node, mapping quá rộng gây tốn CPU, network và dung lượng Prometheus.

Ví dụ hai nhóm nhãn:

```text
Nhãn được quản lý:
  cluster="prod-a"
  datacenter="dc1"
  instance="cassandra-03"
  keyspace="telemetry_ks"
  table="readings_by_device_day"
  operation="read"

Nhãn không nên thêm vào metric:
  partition_key="thiết bị cụ thể"
  user_id="người dùng cụ thể"
  request_id="mỗi request một giá trị"
  token="bí mật"
  raw_cql="câu truy vấn chứa tham số"
```

Cần chọn metric theo **mục tiêu vận hành**, không bật toàn bộ MBean rồi quyết định dashboard sau. Với một bảng mới, có thể bắt đầu từ read/write latency, tombstone scans, SSTable/memtable, disk, compaction; sau đó mới mở rộng khi cần.

Một exporter nhiều rule cũng có rủi ro mapping **trùng tên hoặc trùng label** khiến kết quả không phản ánh đúng dữ liệu. Hãy kiểm thử metric family, kiểu counter/gauge, unit, nhãn và số series sau mỗi lần nâng cấp config.

## 16. Metric không phải lệnh: phân biệt counter, gauge, timer và histogram

| Loại | Ví dụ khái niệm | Cách sử dụng |
|---|---|---|
| **Counter** | Số read requests đã xử lý | Tính `rate()/increase()` trên cửa sổ |
| **Gauge** | Pending compactions tại thời điểm đọc | Quan sát giá trị và xu hướng |
| **Timer** | Read latency | Đọc count và phân phối độ trễ theo đơn vị đúng |
| **Histogram** | Số quan sát theo bucket | Tính quantile từ bucket nếu exporter thực sự xuất histogram |
| **Snapshot percentile** | `99thPercentile` của MBean | Là gauge/snapshot theo node; không lấy trung bình để ra p99 toàn cluster |

Ví dụ, một bộ exporter có thể xuất các thuộc tính `Latency.Count`, `Latency.99thPercentile` và `Latency.MeanRate` thành ba series khác nhau. **Chúng không có cùng đơn vị** và không nhất thiết cùng tính chất tăng đơn điệu.

Khi tổng hợp:

- Counter phải xử lý **reset sau restart** bằng hàm phù hợp.
- Gauge số pending tasks có thể giảm; đừng biểu diễn raw counter thành queue length.
- Percentile theo node không thể cộng hoặc trung bình thành percentile của cluster.
- Latency phía ứng dụng bao gồm driver/network; latency coordinator đo một phạm vi khác.
- Một logical write từ Java có thể sinh nhiều hoạt động replica, đặc biệt khi RF, CL và retries thay đổi.

**Thành công của endpoint `/metrics` không đủ**: phải xác nhận đúng semantics của ít nhất các metric trọng yếu trong dashboard.

## 17. Chẩn đoán lỗi kết nối JMX và exporter

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý an toàn |
|---|---|---|
| `nodetool` kết nối local thất bại | JMX service chưa chạy, sai port, sai host, auth | Kiểm tra log/cấu hình local trên node; không mở remote vội |
| Remote JMX registry tới được nhưng session không tạo | RMI quảng bá địa chỉ/cổng khác, firewall hoặc NAT | Kiểm tra địa chỉ RMI và cổng với nhóm network |
| `Authentication failed` | Sai credential/role hoặc chính sách JMX thay đổi | Xác minh secret và quyền theo bản JDK/Cassandra; không tắt auth |
| Lỗi TLS handshake | Sai certificate, hostname, truststore, protocol | Kiểm tra chain/trust/hostname; không tắt TLS |
| `/metrics` không nghe cổng | Agent không nạp, sai JVM option, lỗi rule/exporter | Kiểm tra startup log, agent JAR và listener |
| Endpoint trả HTTP 200 nhưng thiếu metric Cassandra | Pattern MBean không match, MBean thay tên, rule bị lọc | Đối chiếu ObjectName thực và rule trong lab |
| Metric bị lệch đơn vị rất lớn | Micro giây bị đọc như milli giây, counter/gauge nhầm loại | Kiểm tra MBean attribute và exporter mapping |
| Prometheus `up=0` | Scrape HTTP thất bại/network/target | Kiểm tra target health, DNS, TLS/auth và ACL |
| Không thấy target nào | Discovery/config collector sai hoặc metric đổi tên | Kiểm tra service discovery, exporter và rule |
| Node khỏe nhưng dashboard trống | Collector/exporter lỗi hoặc missing series | Phân biệt mất telemetry với giá trị đo bằng 0 |
| JVM Cassandra tăng tải sau khi bật metric | Scrape quá dày hoặc mapping quá rộng | Giảm quy mô scrape/rules, đo overhead rồi rollout lại |

### Quy trình điều tra ba tầng

1. **Tầng Cassandra/JMX:** MBean có tồn tại, JMX local hoạt động, người vận hành được ủy quyền có thể đọc được attribute hay không?
2. **Tầng exporter:** agent/standalone có kết nối, trả `/metrics`, có đúng tên và unit không?
3. **Tầng collector/dashboard:** target có `up=1`, Prometheus nhận sample, labels/recording rules và quyền dashboard đúng không?

Không tăng timeout Prometheus vô hạn nếu scraper tốn nhiều thời gian; cần xác định MBean/rule nào gây tải, cardinality và chi phí xuất metric.

## 18. Ví dụ Java đọc một thuộc tính JMX trong lab

Đối với ứng dụng **Java**, API chuẩn `javax.management` có thể truy vấn một MBean từ JVM khác nếu connector được cấu hình và cho phép. Đây là công cụ **chẩn đoán được ủy quyền**, không phải mẫu khuyến nghị cho mọi service ứng dụng kết nối JMX production.

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class LocalCassandraJmxProbe {
    public static void main(String[] args) throws Exception {
        // Chỉ chạy trên máy lab có JMX loopback được cho phép.
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"
        );

        // Nếu môi trường yêu cầu TLS/auth, cấu hình connector qua
        // môi trường và secrets an toàn theo đúng phiên bản.
        try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
            MBeanServerConnection server =
                connector.getMBeanServerConnection();

            ObjectName latencyBean = new ObjectName(
                "org.apache.cassandra.metrics:" +
                "type=ClientRequest,scope=Read,name=Latency"
            );

            if (!server.isRegistered(latencyBean)) {
                System.out.println("MBean not available in this version");
                return;
            }

            Object count = server.getAttribute(latencyBean, "Count");
            System.out.println("Read latency observation count = " + count);
        }
    }
}
```

Đây là truy vấn thuộc tính **đọc**, không gọi operation thay đổi hệ thống. `Count` ở ví dụ là số quan sát trong timer MBean nếu thuộc tính đó được phiên bản Cassandra cung cấp. Không mặc định các ObjectName/attribute tồn tại giống nhau ở mọi phiên bản.

**Bảo mật:** ví dụ kết nối `127.0.0.1`, không đưa tài khoản/mật khẩu vào source. Với kết nối remote, cấu hình xác thực, TLS và quyền tối thiểu bằng cơ chế chính thức. Không xây một dịch vụ API công khai cho phép người dùng gửi tùy ý ObjectName hay tên JMX operation để gọi vào Cassandra.

Với metric ứng dụng Java Driver, nên dùng instrument ở phía service (ví dụ Micrometer/OpenTelemetry) thay vì buộc mỗi request API phải mở kết nối JMX tới cluster.

## 19. Chọn dashboard và alert từ mục tiêu vận hành

Một dashboard JMX hữu ích cần phục vụ **hành động cụ thể**, không chỉ chứa hàng trăm đường biểu diễn.

| Câu hỏi vận hành | Nguồn quan sát | Alert/điều tra gợi ý |
|---|---|---|
| Node nào không phản hồi? | Node reachability, `nodetool`, exporter health | Kiểm tra topology, RF/CL và node health |
| Read p99 tăng do đâu? | App/driver latency, ClientRequest, table/JVM metrics | Drill-down coordinator → replica → table/disk/GC |
| Table nào bị tombstone pressure? | Table MBeans, tracing mẫu | Kiểm tra TTL, DELETE, partition và compaction |
| Compaction tụt sau write load? | Compaction pending/throughput, disk I/O | Đánh giá workload, disk saturation, strategy |
| Metric collector có lỗi không? | `up`/scrape duration/errors | Khôi phục exporter/collector trước khi kết luận |
| Có node thiếu disk headroom? | OS exporter, Cassandra disk usage | Kiểm tra volume, snapshot, SSTables, backlog |
| Các lần repair có ảnh hưởng request không? | Repair/streaming, node metrics, app SLO | Gắn annotation đợt repair với p99/errors |

**Không nên alert chỉ vì một metric thấp/cao tạm thời.** Ví dụ CPU cao vài giây không nhất thiết là sự cố nếu request latency ổn định; dashboard trống không phải cluster hết tải. Ưu tiên SLO có ảnh hưởng người dùng, ngưỡng theo baseline, thời gian kéo dài và runbook.

### Bảo đảm có thể điều tra sau sự cố

Lưu đủ thời gian metric để đối chiếu với deploy, schema change, repair, compaction và thay đổi topology. Tuy nhiên retention metric ở Prometheus **khác** với TTL của dữ liệu Cassandra; không giả định hai vòng đời dữ liệu dùng một cấu hình.

## 20. Quy trình triển khai exporter an toàn theo giai đoạn

Một quy trình tốt có thể đi theo thứ tự:

1. **Kiểm kê phiên bản** Cassandra/JDK, JMX mode, các cổng thật, tên MBean và chính sách quản trị.
2. **Chọn kiến trúc**: Java agent tại node hay standalone exporter; tránh remote JMX nếu không cần.
3. **Xác định ranh giới mạng**: node, exporter, collector, datacenter và các ingress/egress được phép.
4. **Thiết lập quyền tối thiểu** cho JMX và metrics, dùng TLS/auth khi qua mạng, secret rotation và RBAC cho dashboard.
5. **Tạo rule mapping tối thiểu**: request rate/error, latency, compaction, thread pools, table SSTable/tombstone, JVM/GC.
6. **Thử trên một node canary**: xác nhận `/metrics`, labels, counter/gauge, đơn vị và overhead scrape.
7. **Kiểm tra trường hợp thất bại**: exporter chết nhưng Cassandra vẫn chạy, collector mất scrape, credential sai, tên MBean đổi khi upgrade.
8. **Rollout có kiểm soát** theo rack/datacenter; nếu cần restart JVM thì tuân thủ yêu cầu RF/CL và kế hoạch bảo trì.
9. **Giám sát liên tục**: scrape failures, JMX auth failures, cardinality, CPU/heap overhead, Prometheus storage và alert noise.
10. **Lưu runbook**: ai được truy cập, cách kiểm tra local JMX, vị trí secret, cách rollback agent và quy trình thu hồi quyền.

Ở cluster production, một thay đổi nhỏ đối với cấu hình giám sát vẫn có thể cần restart node hoặc thay security policy. **Không restart đồng loạt tất cả replica trong một datacenter** chỉ để bật exporter; phải tuân thủ kế hoạch rolling maintenance tương thích RF/CL.

## 21. Bài tập tình huống và đáp án

**Câu 1.** JMX có phải giao thức chỉ đọc metric, an toàn để mở công khai ra Internet không?

**Đáp án:** **Không.** JMX có thể cho phép gọi MBean operations mang tính quản trị. Cần giới hạn mạng, auth/TLS và quyền; ưu tiên không bật remote JMX nếu không cần.

**Câu 2.** Vì sao `nodetool status` chạy được trên node không chứng minh remote JMX đang được bảo vệ đúng?

**Đáp án:** `nodetool` có thể truy cập JMX cục bộ qua loopback hoặc cấu hình riêng. Tính an toàn của remote listener, firewall, credentials và TLS là các câu hỏi khác.

**Câu 3.** Prometheus ở máy A cấu hình target `127.0.0.1:9404` nhưng exporter nghe ở máy B. Vì sao không scrape được?

**Đáp án:** `127.0.0.1` trên A trỏ về A, không phải B. Cần đường scrape được định tuyến qua mạng giám sát an toàn, hoặc collector chạy cùng network namespace phù hợp.

**Câu 4.** Một client kết nối tới cổng JMX registry, nhưng phiên RMI vẫn lỗi. Nguyên nhân phổ biến là gì?

**Đáp án:** RMI có thể quảng bá hostname/cổng khác; firewall/NAT, địa chỉ máy, TLS hoặc cấu hình connector chưa phù hợp.

**Câu 5.** `/metrics` trả HTTP 200 nhưng không có `ClientRequest` mong đợi. Có thể kết luận Cassandra không xử lý request không?

**Đáp án:** **Không.** Cần kiểm tra tên MBean, rule exporter, thuộc tính `Count`, collector mapping và version trước khi kết luận.

**Câu 6.** Có thể gắn từng `session_id` làm label Prometheus để theo dõi truy vấn chậm của một người dùng không?

**Đáp án:** Không nên. Điều đó tạo cardinality rất lớn và có thể lộ thông tin nhạy cảm; dùng tên operation hữu hạn, log/trace có kiểm soát cho ID cụ thể.

**Câu 7.** Vì sao không thể lấy trung bình p99 latency MBean từ ba node thành p99 của cluster?

**Đáp án:** Percentile không tuyến tính. Cần phân phối/histogram có thể gộp hợp lệ, hoặc quan sát p99 theo từng node.

**Câu 8.** Khi dùng Java agent nằm trong JVM Cassandra, có còn cần mở remote JMX để Prometheus đọc metric không?

**Đáp án:** **Không nhất thiết.** Agent đọc MBean nội bộ rồi xuất HTTP metrics riêng. Nhưng endpoint HTTP đó vẫn phải được bảo vệ và đường scrape phải hoạt động.

**Câu 9.** JMX exporter gặp lỗi TLS, có nên tắt TLS/xác thực để tiếp tục giám sát không?

**Đáp án:** **Không.** Cần kiểm tra chứng chỉ, hostname, truststore, secret và tương thích giao thức; không hạ bảo mật để sửa lỗi kết nối.

**Câu 10.** `up=0` ở Prometheus có đồng nghĩa node Cassandra không còn phục vụ CQL không?

**Đáp án:** **Không.** Có thể chỉ exporter, proxy hoặc collector bị lỗi. Cần kiểm tra health của node và đường client độc lập.

**Câu 11.** Khi bật thêm mọi JMX MBean trong exporter, vì sao Prometheus có thể chậm hơn?

**Đáp án:** Mapping quá rộng tạo nhiều series/labels và tăng chi phí scrape, network, CPU, lưu trữ; cần chọn metric theo mục tiêu.

**Câu 12.** Vì sao một tài khoản dashboard không nên dùng chung credential remote JMX quản trị với SRE?

**Đáp án:** Người xem dashboard chỉ cần quyền xem metric. Quyền JMX quản trị có thể thực hiện các operation thay đổi cluster; dùng chung trái nguyên tắc quyền tối thiểu và gây khó audit.

---

**Ghi nhớ:** JMX cung cấp **MBean và thuộc tính/operation** trong JVM Cassandra; exporter biến các thuộc tính cần thiết thành **metric** cho collector và dashboard. **JMX remote là bề mặt quản trị**, không được đánh đồng với HTTP `/metrics` chỉ đọc. Ưu tiên local JMX hoặc agent khi phù hợp, giới hạn mạng, xác thực/TLS, phân quyền và bảo vệ bí mật cho mọi đường truy cập. Khi xây hệ quan sát, phải xác minh **ObjectName, metric type, đơn vị, nhãn, cardinality và sức khỏe collector** trước khi dùng chúng để kết luận tình trạng node, keyspace, table và yêu cầu ứng dụng.
