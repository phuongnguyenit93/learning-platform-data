# Khôi phục kết nối, thay đổi topology và làm mới metadata trong Spring Data Cassandra

Trong ứng dụng **Spring Data Cassandra**, các thao tác `CassandraRepository`, `CassandraTemplate` và câu truy vấn CQL đều đi qua **Cassandra Java Driver**. Driver chịu trách nhiệm thiết lập kết nối, nhận diện các node trong cluster, chọn node điều phối phù hợp và duy trì metadata phục vụ định tuyến. Khi Cassandra khởi động lại một node, mở rộng cluster hoặc thay đổi schema, ứng dụng cần tiếp tục hoạt động mà không phải tự tạo lại kết nối ở mỗi request.

Bài thuộc chương **Quan sát và vận hành** của module `SPRING_DATA_CASSANDRA`. Ta sẽ học cách nhận diện trạng thái mất kết nối, hiểu cơ chế phục hồi của driver, theo dõi thay đổi topology, làm mới node/schema metadata có kiểm soát và xây dựng runbook xử lý sự cố. Các nguyên tắc đặc biệt quan trọng với Cassandra vì **partition key**, replication, local datacenter, consistency level và trạng thái các replica ảnh hưởng trực tiếp đến việc một request có được phục vụ hay không.

> **Phạm vi phiên bản:** Các mô tả API Java minh họa Java Driver 4.x với Spring Boot 3.x/Spring Data Cassandra tương ứng. Tên cấu hình, phương thức và module phụ thuộc có thể thay đổi theo phiên bản. Hãy đối chiếu API đã khóa trong dự án trước khi đưa ví dụ vào production. Những câu lệnh quản trị cluster cần quyền và quy trình vận hành phù hợp.

## 1. Một `CqlSession` quản lý nhiều kết nối và nhiều node

Một ứng dụng Spring Boot thường sử dụng **một `CqlSession` được quản lý bởi Spring** để phục vụ các repository và template. `CqlSession` là đối tượng cấp ứng dụng, còn bên trong driver có các kết nối đến các node, cơ chế khám phá topology và chính sách phân phối request.

~~~mermaid
flowchart TD
    HTTP["API / service"] --> REPO["Repository / CassandraTemplate"]
    REPO --> SESSION["Spring-managed CqlSession"]
    SESSION --> META["Topology + schema metadata"]
    SESSION --> LB["Load balancing + token-aware routing"]
    SESSION --> CONTROL["Control connection / topology events"]
    LB --> A["Node A / replica"]
    LB --> B["Node B / replica"]
    LB --> C["Node C / replica"]
    CONTROL --> META
    META --> LB
~~~

Cần phân biệt:

| Khái niệm | Ý nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| **Contact points** | Điểm khởi đầu để driver liên hệ cluster | Không phải danh sách duy nhất các node driver sẽ dùng mãi mãi |
| **Control connection** | Kênh driver dùng để nhận thông tin sự kiện và kiểm tra metadata cluster | Không đại diện cho toàn bộ kết nối phục vụ CQL |
| **Data connections / pools** | Những kết nối driver dùng để gửi truy vấn CQL tới các node | Một kết nối lỗi chưa chắc toàn bộ session lỗi |
| **Topology metadata** | Thông tin node, endpoint, datacenter, rack, trạng thái... mà driver biết | Không phải bản chụp luôn chính xác tức thời của cả cluster |
| **Schema metadata** | Thông tin keyspace, table, column, type... nếu tính năng được bật | Không thay thế quy trình migration hoặc schema agreement |
| **Node UP/DOWN theo driver** | Góc nhìn về khả năng sử dụng node của **driver này** | Không đồng nghĩa trạng thái mọi replica trên mọi máy |

Driver có thể chọn một node làm **coordinator** cho truy vấn, còn Cassandra tự giao tiếp với các replica theo token và consistency level. Vì vậy **node nhận CQL không nhất thiết là node duy nhất có dữ liệu của partition**.

## 2. Khi mất kết nối: driver phục hồi như thế nào?

Một node có thể bị restart, thay chứng chỉ, mất route hoặc từ chối kết nối. Driver thường phát hiện lỗi qua kết nối, heartbeat, request timeout hoặc sự kiện trạng thái; sau đó điều chỉnh trạng thái node, thử thiết lập lại kết nối theo chính sách reconnect và chọn node khác nếu request có thể được phục vụ.

~~~mermaid
stateDiagram-v2
    [*] --> Discovered: Phát hiện node
    Discovered --> Connecting: Thiết lập kết nối
    Connecting --> Up: Kết nối và điều kiện sử dụng hợp lệ
    Connecting --> Down: Không thể kết nối
    Up --> Down: Kết nối lỗi / node không sẵn sàng
    Down --> Reconnecting: Lịch reconnect
    Reconnecting --> Up: Kết nối lại thành công
    Reconnecting --> Down: Vẫn lỗi
    Up --> [*]: Node bị loại khỏi topology
~~~

Sơ đồ mang tính khái niệm: trạng thái nội bộ và tên callback cụ thể thay đổi theo phiên bản driver. **Tự động reconnect** không đảm bảo request đang chạy sẽ được thực thi lại thành công. Một request có thể lỗi trong lúc node đang được đánh dấu DOWN, hoặc không đủ replica theo consistency level dù cluster vẫn còn node khác.

Ví dụ: keyspace có replication factor 3 trong một datacenter, request dùng `LOCAL_QUORUM`. Với RF=3, quorum cần **2 replica phù hợp**. Nếu chỉ một replica khả dụng, việc driver kết nối được tới một coordinator khác cũng không đủ để thực hiện truy vấn ở mức consistency đó.

### Phân biệt reconnect với retry

- **Reconnect:** driver cố phục hồi kênh kết nối tới một node bị mất hoặc lỗi.
- **Retry:** một request CQL thất bại được thử lại theo chính sách retry, có thể trên coordinator khác hoặc cùng node tùy tình huống.
- **Speculative execution:** gửi thêm bản thực thi request khi có dấu hiệu chậm, theo chính sách và điều kiện đã cấu hình.
- **Recovery ở mức nghiệp vụ:** quyết định có tiếp tục, bù trừ hoặc từ chối thao tác sau lỗi.

Bốn khái niệm này độc lập ở mục đích. Không nên sửa một lỗi DNS/TLS kéo dài bằng cách tăng số lần retry CQL. Cũng không được giả định read/write timeout có nghĩa Cassandra chắc chắn **chưa** thực hiện lệnh ghi.

Với tác vụ ghi có thể gây tác dụng phụ, cần đánh giá **idempotency** trước khi cho phép retry hoặc speculative execution. Ví dụ thao tác gán cùng giá trị theo primary key thường dễ thiết kế idempotent hơn bộ đếm `COUNTER` hoặc nghiệp vụ phát sinh tác dụng phụ ngoài Cassandra.

### Có nên tự tạo lại CqlSession sau mọi lỗi?

Thông thường **không**. Java Driver được thiết kế để giữ session dài hạn, tái sử dụng connection pools, theo dõi node và reconnect. Mở `CqlSession` mới sau mỗi query hoặc restart toàn ứng dụng ngay khi một node lỗi sẽ:

1. Tăng tải handshake, authentication, topology discovery và chuẩn bị statement.
2. Tạo áp lực CPU, socket và bộ nhớ lên ứng dụng lẫn Cassandra.
3. Làm mất các lợi ích của pooling và theo dõi metadata.
4. Có thể tạo vòng lặp restart khi dependency chỉ tạm thời không sẵn sàng.

Nếu không có node nào đủ điều kiện, request có thể thất bại cho đến khi connectivity hoặc replica được phục hồi. Bổ sung bounded retry/backoff ở **đúng tầng**, kết hợp timeout và circuit breaker ở nơi phù hợp với ứng dụng; không cấu hình nhiều lớp retry vô hạn chồng lên nhau.

## 3. Vì sao khôi phục kết nối thất bại?

| Triệu chứng | Tầng ưu tiên kiểm tra | Ví dụ nguyên nhân |
| --- | --- | --- |
| `UnknownHostException` | DNS và địa chỉ node | Contact point sai; node mới quảng bá hostname không phân giải được từ pod |
| Connection refused / connect timeout | TCP và route | Node chưa bật native transport; sai cổng; firewall/network policy |
| `SSLHandshakeException` | TLS | Chứng chỉ hết hạn, CA chưa được tin cậy, SAN không khớp địa chỉ node |
| Authentication failed | Đăng nhập Cassandra | Secret đã đổi nhưng ứng dụng chưa nhận; role mất quyền `LOGIN` |
| Unauthorized khi query | Phân quyền | Role đăng nhập được nhưng thiếu quyền trên bảng/keyspace |
| `AllNodesFailedException` | Nhiều node | Tổng hợp lỗi theo từng node; đọc nguyên nhân con, không suy ra cluster đã chết |
| Read/write timeout hoặc unavailable | Replica/consistency và tải | Không đủ replica, coordinator quá tải, partition nóng, mạng chậm |
| `InvalidQueryException` sau đổi schema | Schema hoặc CQL | Cột/bảng bị đổi; câu CQL, entity mapping, migration không còn tương thích |

Để xác định nguyên nhân, luôn ghi nhận **thời điểm**, **endpoint**, **datacenter**, **exception cause chain** và **truy vấn/operation logic**. Không log password, token, nội dung TLS key, CQL bind values nhạy cảm hoặc thông tin cá nhân.

Một chẩn đoán đúng thường đi theo thứ tự:

1. JVM và container ứng dụng còn hoạt động không?
2. Ứng dụng phân giải và đến được endpoint Cassandra nào?
3. TCP/TLS và authentication còn thành công không?
4. Driver nhìn thấy những node nào, node nào đang DOWN?
5. Có đủ replica theo consistency level cho partition cần đọc/ghi không?
6. Topology/schema metadata và truy vấn CQL còn phù hợp không?

## 4. Topology thay đổi: thêm, xóa hoặc thay node

**Topology** mô tả tập hợp các node, datacenter, rack, token/partition ownership và endpoint mà driver cần biết để định tuyến. Trong quá trình vận hành, cluster có thể:

- **Scale out:** bootstrap thêm node để nhận một phần token range và lưu dữ liệu.
- **Replace node:** thay node hỏng bằng node mới theo quy trình Cassandra.
- **Decommission:** loại node đúng cách, chuyển ownership và dữ liệu liên quan.
- **Rolling restart / upgrade:** node lần lượt xuống rồi lên, có thể ngắt các connection pools tạm thời.
- **Thay endpoint hoặc DNS:** ví dụ thay IP, chuyển mạng hoặc sửa hostname node quảng bá.

Java Driver sử dụng thông tin từ cluster và thông báo topology/status để cập nhật danh sách node. Bên cạnh sự kiện, driver có thể thực hiện refresh và tái khám phá tùy cấu hình/phiên bản. **Thông báo sự kiện có thể bị trễ hoặc bị mất** trong đứt kết nối; do đó sự tồn tại của chức năng event handling không bảo đảm góc nhìn của mọi client được cập nhật ngay lập tức.

### Contact point không bằng topology hoàn chỉnh

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  cassandra:
    contact-points:
      - cassandra-seed-a.internal.example:9042
      - cassandra-seed-b.internal.example:9042
    local-datacenter: dc1
    keyspace-name: app_data
~~~

Hai contact point chỉ phục vụ **bootstrap session**. Sau đó driver có thể biết thêm nhiều node qua metadata. Nếu node mới quảng bá địa chỉ không thể truy cập từ runtime ứng dụng, việc đổi danh sách contact point đơn thuần có thể không khắc phục được lỗi.

Các điểm cần nhất quán:

- Endpoint native transport CQL mà node quảng bá phải phân giải/truy cập được từ client.
- Datacenter name trong `spring.cassandra.local-datacenter` phải đúng như tên DC được Cassandra nhận diện.
- DNS, network policy, firewall và security group phải cho phép kết nối tới **các node driver có thể dùng**, không chỉ seed.
- Khi Cassandra chạy trong Kubernetes hoặc nhiều mạng private/public, cần giải quyết địa chỉ quảng bá và routing giữa network namespaces; DNS của developer laptop không chứng minh DNS từ container ứng dụng.
- Khi thay node hoặc thay địa chỉ, phải xác nhận trạng thái cluster và quá trình chuyển dữ liệu/ownership qua công cụ vận hành Cassandra, không chỉ nhìn log một Java client.

Cấu hình `broadcast_rpc_address` và các thiết lập liên quan đến địa chỉ CQL quảng bá phụ thuộc kiểu triển khai Cassandra. Không nên đổi chúng tùy tiện chỉ để làm một client kết nối được, vì những client khác hoặc cluster topology có thể bị ảnh hưởng.

### Quan hệ với token-aware routing

Cassandra phân vùng dữ liệu theo **partition key**. Một chính sách load balancing hiểu token/topology có thể ưu tiên coordinator gần replica phù hợp, tùy driver, cấu hình và khả năng lấy token metadata. Khi cluster thêm node hoặc di chuyển token, metadata cũ có thể khiến lựa chọn coordinator chưa tối ưu.

Tuy nhiên, **metadata refresh không làm ứng dụng thay đổi partition key hay giải quyết hot partition**. Nếu query thiếu partition key hoặc dữ liệu dồn vào một partition rất lớn, nguyên nhân hiệu năng vẫn nằm ở thiết kế bảng theo truy vấn. Tối ưu định tuyến và tối ưu access pattern là hai việc cần phối hợp.

## 5. Phân biệt node metadata và schema metadata

Trong Java Driver, "metadata" thường gồm nhiều loại thông tin. Tách chúng ra giúp biết cần làm mới phần nào.

| Loại | Chứa thông tin gì? | Khi nào đáng kiểm tra? |
| --- | --- | --- |
| **Node/topology metadata** | UUID node, endpoint, DC/rack, trạng thái, thông tin token... | Scale out, replace node, rolling restart, mất kết nối |
| **Schema metadata** | Keyspace, bảng, cột, UDT, index và các cấu trúc CQL được hỗ trợ | Migration DDL, repository báo cột/bảng không tồn tại |
| **Prepared statement metadata** | Kiểu bind variables, các cột kết quả và prepared query từ server | Query bị thay đổi không tương thích, `UNPREPARED` sau restart |
| **Metrics/tracing** | Thời gian request, connection lỗi, retry, coordinator, cảnh báo server... | Chẩn đoán và vận hành lâu dài |

Java Driver có thể quản lý **topology metadata** và **schema metadata** với cơ chế/tùy chọn khác nhau. Nếu schema metadata bị vô hiệu hóa để giảm overhead, việc không thấy một bảng trong `session.getMetadata()` không chứng minh bảng đó không tồn tại ở Cassandra. Ngược lại, schema metadata có trong client cũng không đồng nghĩa mọi node đã đạt **schema agreement**.

Một thay đổi DDL có thể mất thời gian lan tới các node. Trong khoảng chuyển tiếp:

- Client A có thể đã nhìn thấy table/column mới, client B chưa cập nhật metadata.
- Prepared query hoặc mapping cũ có thể không còn tương thích với schema mới.
- Một query chạy qua coordinator này thành công nhưng coordinator khác báo lỗi cho đến khi schema hội tụ, tùy kiểu thay đổi.

Vì vậy **làm mới metadata không thay thế cho schema migration có thứ tự, kiểm tra schema agreement và triển khai ứng dụng tương thích**.

## 6. Quan sát node metadata từ một Spring Boot service

Ví dụ sau đọc **snapshot mà Java Driver hiện đang biết**. Nó phù hợp cho endpoint chẩn đoán nội bộ có kiểm soát hoặc hỗ trợ incident, không nên công khai danh sách endpoint cluster cho người dùng bên ngoài.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class CassandraTopologyInspector {

    private final CqlSession session;

    public CassandraTopologyInspector(CqlSession session) {
        this.session = session;
    }

    public List<NodeView> snapshot() {
        return session.getMetadata().getNodes().values().stream()
            .map(this::toView)
            .sorted(Comparator.comparing(NodeView::endpoint))
            .toList();
    }

    private NodeView toView(Node node) {
        return new NodeView(
            node.getEndPoint().toString(),
            node.getDatacenter(),
            node.getState().name());
    }

    public record NodeView(String endpoint, String datacenter,
                           String state) {
    }
}
~~~

Ý nghĩa của snapshot:

- `getMetadata().getNodes()` trả về tập node **theo góc nhìn hiện tại của session**.
- `node.getState()` phản ánh việc driver đánh giá node có thể sử dụng hay không, không phải kết quả cuối cùng của `nodetool status`.
- Metadata có thể thay đổi sau đó; một lần chụp không đảm bảo trạng thái ổn định khi request tiếp theo thực hiện.
- Một node đang `UP` vẫn có thể bị timeout bởi tải, lỗi CQL, thiếu quyền hoặc không đủ replica theo consistency level.
- Nếu các node trong snapshot đều UP nhưng ứng dụng vẫn bị `UnavailableException`, hãy kiểm tra **replication**, số replica sống của partition, local datacenter và consistency level.

Nên giới hạn tần suất tạo snapshot/log và tránh gán các giá trị có cardinality quá cao làm tag metric. Số lượng node UP/DOWN theo datacenter, trạng thái kết nối, tỷ lệ lỗi và p95 latency thường hữu ích hơn việc ghi toàn bộ topology vào log mỗi giây.

## 7. Làm mới topology và schema metadata khi nào?

Trong trạng thái vận hành bình thường, **để driver nhận sự kiện và đồng bộ metadata tự động**. Thao tác refresh thủ công nên là công cụ có kiểm soát sau một thay đổi topology/schema hoặc khi có bằng chứng metadata đã lệch.

Hai hành động phục vụ mục đích khác nhau:

- **Refresh node list/topology:** yêu cầu driver cập nhật danh sách node nó biết, hữu ích khi vừa bootstrap/replace node hoặc nghi bỏ lỡ topology event.
- **Refresh schema:** yêu cầu driver cập nhật thông tin keyspace/bảng/type, hữu ích sau migration khi ứng dụng cần xác minh schema đã được nhận diện.

Với Java Driver 4.x, thao tác bất đồng bộ có thể được yêu cầu theo dạng:

~~~java
// Thao tác phục vụ vận hành, không đặt trên đường đi mỗi request.
// Xác nhận API cụ thể theo phiên bản Java Driver đã khóa.
session.refreshNodeListAsync()
    .toCompletableFuture()
    .join();

session.refreshSchemaAsync()
    .toCompletableFuture()
    .join();
~~~

Phương thức có thể hoàn tất bất thường; khi dùng thực tế cần bắt lỗi, đặt giới hạn thời gian qua cơ chế vận hành phù hợp và quan sát trạng thái sau refresh. `join()` chặn thread gọi, nên ví dụ này chỉ minh họa thao tác thủ công trong tác vụ quản trị/diagnostic, **không chạy trực tiếp trong HTTP request phổ biến**.

Điểm giới hạn:

1. Refresh metadata **không tự sửa** DNS, network policy, TLS, credential hoặc local datacenter sai.
2. Refresh metadata **không buộc** một node DOWN thành UP nếu kết nối mới vẫn thất bại.
3. Refresh schema **không thực thi DDL**, không tạo quyền CQL và không sửa entity mapping.
4. Nếu query đã chuẩn bị trước không còn tương thích với schema mới, cần giải quyết lifecycle của prepared statements/query và kế hoạch deploy.
5. Làm mới quá thường xuyên trên nhiều instance có thể tạo tải metadata không cần thiết cho cluster; không chạy vòng lặp refresh vô hạn.

Nếu lỗi vẫn còn sau refresh, đừng gọi lại liên tục. Lúc đó cần tìm nguyên nhân ở topology thực, khả năng kết nối và schema agreement.

### Làm mới metadata khác restart ứng dụng

Restart service buộc tạo session/connection và khám phá lại cluster, nhưng mất thời gian khởi động, làm gián đoạn traffic và có thể khiến lỗi lan rộng nếu mọi replica ứng dụng restart đồng thời. Restart chỉ phù hợp khi cần nạp thay đổi cấu hình/secret không hỗ trợ reload hoặc sau khi có chẩn đoán rõ ràng.

Ví dụ một cert mới chưa được ứng dụng nạp vào SSL context có thể cần tái tạo session hoặc rollout service theo cách thiết kế; chỉ refresh schema sẽ không thay đổi truststore đang dùng.

## 8. Schema migration và schema agreement

Một ví dụ thay đổi schema:

~~~sql
ALTER TABLE app_data.orders_by_customer
ADD fulfillment_status text;
~~~

Sau DDL, các node Cassandra cần hội tụ về định nghĩa schema nhất quán. Trước khi ứng dụng chạy query dựa trên `fulfillment_status`, quy trình triển khai nên:

1. Chạy DDL qua migration/provisioning có kiểm soát.
2. Xác minh không có node lỗi hoặc đang tách mạng làm schema agreement bị trì hoãn.
3. Kiểm tra schema agreement theo công cụ/driver hỗ trợ và xác nhận cấu trúc mong muốn.
4. Đảm bảo ứng dụng cũ và mới tương thích trong thời gian rollout.
5. Quan sát lỗi `InvalidQueryException`, prepared statement mismatch và lỗi mapping.
6. Sau cùng, kiểm tra câu CQL của repository/template trên cluster thực.

Nếu migration thay đổi hoặc xóa cột, hãy dùng chiến lược **expand → migrate → contract** khi có thể:

~~~mermaid
flowchart LR
    A["Thêm cấu trúc mới tương thích"] --> B["Triển khai code đọc/ghi tương thích"]
    B --> C["Backfill/di chuyển dữ liệu nếu cần"]
    C --> D["Xác minh mọi phiên bản ứng dụng"]
    D --> E["Loại cấu trúc cũ sau khi an toàn"]
~~~

Một phép kiểm tra schema agreement có thể trả **chưa đồng thuận**, dù query trên một node tình cờ vẫn chạy. Ngược lại, schema agreement đạt được không đảm bảo entity mapping hay CQL của ứng dụng đúng, vì mọi node có thể cùng đồng thuận trên một schema **khác với schema code mong đợi**.

Một số thay đổi định nghĩa bảng/primary key không thể thực hiện bằng `ALTER TABLE` đơn giản. Cassandra đặc biệt ràng buộc partition key và clustering key; khi access pattern thay đổi, thường phải tạo bảng mới, ghi/di chuyển dữ liệu phù hợp và chuyển ứng dụng sang query mới. Làm mới metadata không giải quyết thiết kế bảng sai.

## 9. Health, readiness và liveness khi Cassandra gặp sự cố

Spring Boot Actuator có thể cung cấp health indicator cho Cassandra khi dependency/auto-configuration tương thích. Tuy nhiên, **một health check thành công tại một thời điểm không chứng minh mọi node, mọi partition và mọi consistency level đều phục vụ được**.

Ba trạng thái cần phân biệt:

- **Liveness:** tiến trình JVM còn chạy và có khả năng hoạt động hay không. Một node Cassandra DOWN tạm thời thường không nên khiến liveness của mọi instance ứng dụng thất bại, gây restart storm.
- **Readiness:** instance có nên nhận traffic nghiệp vụ phụ thuộc Cassandra ở thời điểm hiện tại hay không? Nếu truy cập Cassandra là bắt buộc, readiness nên phản ánh khả năng xử lý một thao tác đại diện.
- **Health nghiệp vụ/chẩn đoán:** có thể kiểm tra một query nhẹ với role của ứng dụng, các operation đọc/ghi hoặc consistency level phù hợp; chi phí check phải được kiểm soát.

Ví dụ cấu hình theo quy ước Spring Boot 3.x (xác nhận nhóm indicator có sẵn trong phiên bản/dự án):

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include:
            - readinessState
            - cassandra
~~~

Đây là ví dụ **chọn đưa Cassandra health indicator vào readiness group**. Không nên mặc định rằng mọi phiên bản Spring Boot tự đưa Cassandra vào nhóm readiness. Nếu indicator không tồn tại hoặc context đã tự thay health contributors, cần cấu hình lại dựa trên ứng dụng thực. Đồng thời cân nhắc tác động khi Cassandra lỗi: readiness false có thể ngắt traffic khỏi tất cả replica ứng dụng; khi không có đường phục vụ thay thế, cần đánh giá fallback/queue/brownout thay vì chỉ dựa vào restart.

Một query lên `system.local` có thể chứng minh kết nối CQL cơ bản tới một coordinator nhưng **không chứng minh** quyền truy cập bảng nghiệp vụ. Nếu health check yêu cầu bảng thật, ưu tiên query bounded theo partition key và tránh đọc lượng dữ liệu lớn. Không dùng `SELECT COUNT(*)` trên bảng lớn làm health check định kỳ.

## 10. Metrics, log và cảnh báo cần theo dõi

Hệ quan sát hữu ích kết hợp góc nhìn **ứng dụng/driver** và **Cassandra cluster**. Một chỉ số đơn lẻ khó cho biết reconnect, topology hay schema là nguyên nhân.

| Nguồn | Chỉ số/tín hiệu | Cách đọc |
| --- | --- | --- |
| Java Driver | Request success/error, timeout, retry, in-flight requests | Phân biệt lỗi request với lỗi kết nối node |
| Driver connections | Mở/đóng kết nối, kết nối lỗi, node UP/DOWN theo DC | Nhận diện reconnect storm hoặc node bị cô lập |
| Driver latency | Latency p50/p95/p99 theo operation/statement class | Phát hiện tail latency khi đổi topology |
| Spring Boot | HTTP/gRPC error rate, latency, readiness, GC, thread/connection pool pressure | Hiểu mức ảnh hưởng lên trải nghiệm API |
| Cassandra cluster | Node state, native transport, dropped messages, tombstone warnings, compaction/CPU/disk | Xác định lỗi storage/replica so với lỗi client |
| Schema/migration | Phiên bản migration, thời điểm DDL, schema agreement | Liên hệ lỗi query với rollout |

**Tên metric và cách bật metric khác nhau theo Java Driver, Micrometer và Spring Boot version.** Không giả định mọi metric trên đều có sẵn mặc định. Nếu instrument có tag `node_id`, `endpoint` hoặc `query_name`, phải kiểm soát cardinality; không gắn UUID user, partition key hoặc toàn bộ raw CQL có giá trị nhạy cảm làm tag.

Các cảnh báo hữu dụng gắn với triệu chứng dịch vụ:

- Tỷ lệ request Cassandra thất bại tăng đồng thời với một nhóm node DOWN.
- p95/p99 latency tăng sau khi thêm node, thay routing hoặc chuyển token ownership.
- Reconnect failures xảy ra liên tiếp trên một datacenter.
- Schema migration được ghi nhận nhưng query bắt đầu báo bảng/cột không tồn tại.
- Retry hoặc speculative execution tăng dù tỷ lệ lỗi HTTP tạm thời chưa tăng.
- Health/readiness chập chờn do dependency check quá nhạy với một node.

Nếu chỉ có log `AllNodesFailedException`, cần mở rộng **các lỗi theo từng node** và cause chain. Đây là container exception của driver; nó không phân biệt sẵn DNS, TLS, authentication hay topology.

### Mẫu sự kiện log phục vụ điều tra

~~~text
time=2026-11-25T08:12:10Z
service=order-api
environment=staging
operation=orders_by_customer.read
local_dc=dc1
cassandra_error=AllNodesFailedException
affected_nodes=2
request_id=trace-...
cause_family=CONNECTIVITY
~~~

Dữ liệu trên chỉ là ví dụ minh họa. Không đưa nguyên bind values, password hay thông tin cá nhân vào log. Với truy vấn theo partition key của khách hàng, ưu tiên mã correlation đã được kiểm soát hơn việc ghi UUID khách hàng vào mọi log line.

## 11. Quy trình vận hành khi node xuống và quay lại

Giả sử cluster Cassandra 3 node ở cùng datacenter, một node được rolling restart trong bảo trì. Ứng dụng Spring Data Cassandra báo vài connection errors nhưng vẫn phục vụ đa số request.

**Bước 1 — Xác nhận sự cố và mức ảnh hưởng.** Kiểm tra thời điểm bắt đầu, operation lỗi, local DC, consistency level, request error/latency và tỷ lệ readiness. Không coi mọi timeout là do node đang restart nếu cluster còn dấu hiệu quá tải, disk hoặc compaction.

**Bước 2 — So sánh hai góc nhìn.** Từ ứng dụng, lấy snapshot node metadata của driver. Từ phía Cassandra, dùng công cụ quản trị:

~~~bash
nodetool status
nodetool describecluster
~~~

Lệnh này cần môi trường có `nodetool`, quyền phù hợp và cấu hình kết nối JMX/management tương ứng. `nodetool status` cho biết trạng thái cluster theo góc nhìn node Cassandra mà ta hỏi; nó không tự chứng minh ứng dụng bên ngoài truy cập được native transport CQL. So sánh hai nguồn để tìm khác biệt.

**Bước 3 — Kiểm tra endpoint mà driver thực sự dùng.** Kiểm tra DNS, route, cổng CQL, TLS và credentials từ **runtime ứng dụng**. Nếu ứng dụng chạy trong Kubernetes, không sử dụng kết quả ping/DNS từ laptop làm kết luận cuối cùng.

**Bước 4 — Để driver reconnect.** Quan sát node có chuyển lại trạng thái UP và tỷ lệ lỗi giảm. Nếu node còn đang bootstrap hoặc chưa nhận traffic CQL ổn định, không ép client liên tục tạo session mới.

**Bước 5 — Xác minh CQL đại diện.** Dùng chính role, keyspace, local DC và consistency level của ứng dụng để kiểm tra query theo partition key. Thử cả một truy vấn của repository và một truy vấn `CassandraTemplate` nếu hai đường này có mapping/query khác nhau.

**Bước 6 — Nếu topology cũ, cân nhắc metadata refresh có kiểm soát.** Chỉ làm sau khi endpoint và trạng thái cluster đã đúng. Nếu sau refresh node vẫn DOWN, quay lại kiểm tra kết nối, không lặp lại refresh vô hạn.

**Bước 7 — Kiểm tra hậu sự cố.** Đọc p95/p99 latency, retry rate, failover behavior, remaining replica count và log schema trong giai đoạn recovery. Một instance báo “connected” không đủ chứng minh khả năng phục vụ workload đã phục hồi hoàn toàn.

## 12. Runbook riêng cho từng thay đổi

### A. Thêm node mới

1. Chuẩn bị node mới theo quy trình bootstrap Cassandra, xác minh datacenter/rack, token ownership và quá trình đồng bộ dữ liệu.
2. Xác nhận cluster nhận biết node và trạng thái phù hợp từ công cụ Cassandra.
3. Từ pod ứng dụng, xác nhận endpoint CQL node mới có DNS/route/TLS hợp lệ.
4. Quan sát driver discovery, node metadata, connection và độ trễ sau bootstrap.
5. Đo lại latency, coordinator distribution và error rate của các truy vấn theo partition key.

Nếu driver vẫn chỉ biết tập node cũ, kiểm tra thông báo topology/control connection và khả năng truy vấn metadata trước khi thử refresh node list. **Không dùng lệnh thêm contact point để thay thế công đoạn bootstrap trong cluster.**

### B. Thay node hỏng hoặc thay IP

1. Thực hiện replace/decommission theo đúng quy trình Cassandra; tránh tạo hai node cùng claim ownership không mong muốn.
2. Xác nhận DNS và node-advertised address phù hợp với client.
3. Nếu dùng TLS, chứng chỉ của endpoint mới phải có SAN phù hợp với địa chỉ được driver sử dụng.
4. Theo dõi node cũ biến mất và node mới xuất hiện trong metadata.
5. Quan sát reconnect, failed requests, tính đủ replica cho consistency level.

**Đổi IP** không chỉ là thay DNS record nếu driver vẫn nhận endpoint cũ qua gossip/topology metadata hoặc connection pools chưa được cập nhật.

### C. Rolling restart / rolling upgrade

1. Kiểm tra health, trạng thái replica và khả năng đáp ứng consistency level **trước** khi hạ node.
2. Restart có trình tự; đợi node trước phục hồi và cluster ổn định rồi mới chuyển node tiếp theo.
3. Theo dõi connection/reconnect và request error rate ở ứng dụng.
4. Kiểm tra phiên bản Cassandra/driver/protocol tương thích, chứng chỉ và authentication.
5. Kiểm tra lại schema, migration state và các truy vấn nghiệp vụ sau mỗi đợt.

Không hạ nhiều node cùng lúc chỉ vì driver đang tự reconnect. Driver không thể bù đắp việc cluster còn quá ít replica để đạt consistency level.

### D. Đổi schema

1. Phát hành migration tương thích và có rollback/forward plan thực tế.
2. Xác minh schema agreement và cấu trúc keyspace/table mới.
3. Triển khai code đọc/ghi tương thích, theo dõi mapping errors.
4. Chỉ refresh schema metadata thủ công nếu có bằng chứng client chưa cập nhật và cơ chế tự động không xử lý được.
5. Loại bỏ cột hoặc hành vi cũ sau khi các instance đã sử dụng schema mới an toàn.

## 13. Các lỗi thiết kế vận hành nên tránh

| Cách làm | Rủi ro | Thay bằng |
| --- | --- | --- |
| Mở `CqlSession` trên mỗi HTTP request | Nhiều kết nối/handshake, tải lớn, mất lợi ích pooling | Một session được Spring quản lý và tái sử dụng |
| Restart mọi pod vì một node Cassandra DOWN | Restart storm, giảm khả năng phục vụ | Readiness/liveness phù hợp; để driver reconnect và xử lý cluster |
| Retry vô hạn sau lỗi auth/TLS | Không sửa được cấu hình, gây log/tải | Sửa credential, CA/SAN và rotate đúng quy trình |
| Gọi refresh metadata mỗi query | Tải metadata không cần thiết, che vấn đề | Dựa vào driver; chỉ refresh khi có nguyên nhân |
| Coi contact point là danh sách node cố định | Bỏ qua node được discovery; lỗi khi scale/replace | Kiểm tra toàn bộ endpoint được quảng bá |
| Dựa chỉ vào `nodetool status` | Không thấy lỗi DNS/TLS từ JVM client | Đối chiếu cluster với snapshot từ driver và query thật |
| Coi schema refresh là migration | App/schema có thể vẫn không tương thích | Migration, schema agreement, rollout tương thích |
| Tăng consistency level trong lúc mất replica | Dễ tăng unavailable/timeouts | Chọn CL theo yêu cầu dữ liệu và RF; phục hồi replica |
| Cho retry ghi không idempotent | Ghi lặp hoặc tác dụng phụ không mong muốn | Đánh giá idempotency/semantics trước khi retry |
| Ghi endpoint/partition key người dùng vào metric tag | Cardinality cao, nguy cơ rò dữ liệu | Label hữu hạn theo DC, operation và trạng thái |

## 14. Bài tập tự kiểm tra

**Câu 1.** Spring Boot chỉ cấu hình hai contact point nhưng cluster có sáu node. Có phải driver chỉ gửi CQL đến hai node ban đầu?

**Gợi ý đáp án:** Không nhất thiết. Contact points phục vụ bootstrap; driver có thể khám phá các node còn lại qua metadata và định tuyến đến chúng. Điều kiện là topology metadata đúng và endpoint của các node truy cập được từ ứng dụng.

**Câu 2.** Một node Cassandra restart. Health check của ứng dụng báo DOWN trong một lần kiểm tra, sau đó trở lại UP. Có cần restart mọi pod Spring Boot để tạo lại session?

**Gợi ý đáp án:** Thường không. Driver duy trì session và tự khôi phục các kết nối phù hợp. Đánh giá ảnh hưởng tới readiness và request failures, kiểm tra cơ chế reconnect; restart chỉ khi có lý do cấu hình/lifecycle cụ thể.

**Câu 3.** Migration thêm cột mới đã chạy nhưng một số query báo "unknown column". Gọi `refreshSchemaAsync()` có giải quyết chắc chắn không?

**Gợi ý đáp án:** Không. Phải kiểm tra migration có đúng keyspace/bảng, schema agreement, trạng thái các node và query/entity mapping. Refresh chỉ yêu cầu cập nhật metadata phía client; không tự chạy DDL hoặc sửa schema thiếu trên cluster.

**Câu 4.** Driver ghi node UP nhưng query `LOCAL_QUORUM` vẫn trả unavailable. Điều này mâu thuẫn không?

**Gợi ý đáp án:** Không. Một coordinator có thể truy cập được nhưng partition không có đủ replica đang sẵn sàng để đạt consistency level. Kiểm tra RF, DC, trạng thái replica, node ownership và local DC.

**Câu 5.** Đổi DNS của contact point rồi khởi động lại ứng dụng, nhưng một số request vẫn cố đi tới IP private không route được. Cần xem gì?

**Gợi ý đáp án:** Kiểm tra endpoint mà từng node quảng bá trong topology, không chỉ DNS contact point. Đối chiếu snapshot node metadata, `broadcast_rpc_address` hoặc cấu hình address tương ứng, DNS và network policy trong pod.

**Câu 6.** Vì sao tăng số lần retry write timeout có thể nguy hiểm?

**Gợi ý đáp án:** Client không biết chắc thao tác ghi trước đã được áp dụng hay chưa. Retry an toàn phụ thuộc idempotency, dữ liệu được ghi, consistency và các side effect liên quan. Cần chính sách retry có giới hạn và hiểu ngữ nghĩa của thao tác.

## 15. Checklist vận hành trước và sau thay đổi topology/schema

- [ ] Ghi nhận baseline latency, error rate, timeout, retry và trạng thái node từ cả client và cluster.
- [ ] Xác nhận đúng keyspace, replication strategy/factor, local datacenter và consistency level.
- [ ] Mọi endpoint mà driver có thể khám phá đều truy cập được từ runtime ứng dụng qua DNS, TCP, TLS và authentication.
- [ ] Có một `CqlSession` ổn định do Spring quản lý; không tạo session theo request.
- [ ] Retry, reconnect, timeout và speculative execution được cấu hình theo tính chất thao tác và giới hạn tải.
- [ ] Readiness/liveness phân biệt lỗi dependency tạm thời với lỗi tiến trình.
- [ ] Có migration, schema agreement và kế hoạch rollout tương thích khi đổi bảng/CQL.
- [ ] Metadata được theo dõi và chỉ refresh thủ công khi có bằng chứng cần thiết.
- [ ] Không sử dụng một node UP hoặc một query thành công để kết luận mọi partition/replica đã phục hồi.
- [ ] Đã kiểm tra truy vấn đại diện qua `CassandraRepository` và/hoặc `CassandraTemplate` với role ứng dụng.
- [ ] Có thể đối chiếu log/metric với thời điểm bootstrap, decommission, replace, restart và DDL.
- [ ] Sau sự cố, ghi lại nguyên nhân gốc, hành động khôi phục và điều kiện cảnh báo hữu ích cho lần sau.

**Ghi nhớ:** Với Spring Data Cassandra, **phục hồi kết nối** thuộc trách nhiệm kết hợp của Java Driver và hạ tầng, **topology** quyết định những node có thể phục vụ yêu cầu, còn **metadata** là góc nhìn mà client dùng để định tuyến và hiểu schema. Khôi phục thành công đòi hỏi xác minh cả hai phía: cluster thật sự ổn định và ứng dụng thực hiện được CQL đại diện bằng đúng cấu hình, quyền và consistency level của mình.

