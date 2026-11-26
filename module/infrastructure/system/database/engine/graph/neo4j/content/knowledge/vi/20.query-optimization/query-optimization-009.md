# Đo độ trễ, thông lượng và mức dùng tài nguyên theo tải thực tế trong Neo4j

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Thiết kế phép đo hiệu năng **đại diện cho tải thực tế** của ứng dụng dùng Neo4j, thay vì chỉ đo một câu Cypher trên database trống.
- Phân biệt **độ trễ (latency)**, **thông lượng (throughput)**, **độ đồng thời (concurrency)**, tỷ lệ lỗi và các chỉ số tài nguyên; đọc đúng p50, p95, p99.
- Đo ở cả **đầu ứng dụng/Java Driver** và **phía Neo4j**, xác định thời gian chờ connection, thời gian thực thi truy vấn và thời gian nhận kết quả.
- Kết hợp `EXPLAIN`/`PROFILE` với CPU, heap, page cache, I/O, transaction và connection pool để tìm nút thắt.
- Thực hiện phép thử có thể lặp lại, đánh giá ngưỡng bão hòa và kết luận một thay đổi tối ưu có thật sự cải thiện trải nghiệm người dùng hay không.

Đây là bài thuộc chương **Tối ưu truy vấn** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Một ứng dụng property graph thường đọc node theo khóa, mở rộng nhiều relationship, truy vấn đường đi bằng Cypher, ghi giao dịch qua **Neo4j Java Driver** hoặc **Spring Data Neo4j**, và có thể nhập dữ liệu theo lô. Các loại công việc đó tạo tải khác nhau. Đánh giá đúng hiệu năng cần đo **hành vi hệ thống dưới hỗn hợp truy vấn và lượng truy cập thực tế**, chứ không chỉ xem một truy vấn có dùng index hay không.

> Các ngưỡng, số liệu mẫu và quy mô tải trong bài chỉ để minh họa phương pháp đo. Không coi chúng là benchmark của Neo4j hoặc cam kết tốc độ cho môi trường cụ thể. Tên metrics và tính năng quan sát có thể thay đổi tùy phiên bản Neo4j, edition, môi trường tự quản hoặc dịch vụ được quản lý.

## 1. Xác định chính xác điều cần đo

Giả sử API `GET /customers/{id}/orders` tìm một `Customer` theo `customerId`, duyệt quan hệ `PLACED`, lọc `Order` theo thời gian và trả tối đa 20 đơn gần nhất. Câu Cypher có thể như sau:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.createdAt >= datetime($fromTime)
RETURN o.orderId AS orderId, o.createdAt AS createdAt
ORDER BY createdAt DESC
LIMIT 20;
~~~

Một yêu cầu nghiệp vụ từ trình duyệt tới API và Neo4j đi qua nhiều công đoạn:

~~~mermaid
flowchart LR
    A["Client gửi request"] --> B["API và hàng đợi"]
    B --> C["Driver lấy connection"]
    C --> D["Neo4j thực thi Cypher"]
    D --> E["Truyền và đọc hết kết quả"]
    E --> F["API xử lý và trả response"]
~~~

Cần phân biệt các điểm đo:

| Phạm vi | Bắt đầu – kết thúc | Phản ánh |
| --- | --- | --- |
| **Độ trễ API đầu cuối** | Nhận HTTP request đến khi gửi xong response | Điều người dùng thấy; gồm cả logic ứng dụng, hàng đợi, network |
| **Độ trễ thao tác với Neo4j tại ứng dụng** | Ngay trước khi mở session/chạy giao dịch đến khi đã consume kết quả và đóng session | Gồm pool/driver, network, retry, thực thi và đọc dữ liệu |
| **Thời gian truy vấn phía database** | Theo công cụ quan sát/log của Neo4j | Phần xử lý thuộc database; không thay thế đo từ ứng dụng |
| **`PROFILE` của Cypher** | Chạy câu truy vấn và thu số liệu toán tử | `Rows`, `DB Hits`, các bước scan/seek/expand để chẩn đoán nguyên nhân |

**Điểm quan trọng:** Một `PROFILE` có `DB Hits` thấp không đảm bảo HTTP p99 thấp. Có thể người dùng vẫn chờ vì connection pool hết chỗ, server đầy tải, trả nhiều dữ liệu qua mạng hoặc ứng dụng serialize chậm. Ngược lại, không thể quy mọi độ trễ API cho Neo4j.

## 2. Các chỉ số cốt lõi: latency, throughput, concurrency và lỗi

### 2.1. Latency: không chỉ đo trung bình

**Latency** là thời gian hoàn tất **một** thao tác. Đơn vị thường dùng: milli giây (ms). Một hệ thống có nhiều request nhanh và vài request rất chậm có thể có **trung bình đẹp nhưng trải nghiệm kém**. Vì vậy cần báo cáo phân vị:

| Chỉ số | Diễn giải | Khi hữu ích |
| --- | --- | --- |
| `p50` (median) | 50% phép đo có thời gian nhỏ hơn hoặc bằng mức này | Trường hợp điển hình |
| `p95` | 95% phép đo có thời gian nhỏ hơn hoặc bằng mức này | Phần đuôi mà nhiều người dùng có thể gặp |
| `p99` | 99% phép đo có thời gian nhỏ hơn hoặc bằng mức này | Độ trễ đuôi trong tải cao |
| `max` | Phép đo lớn nhất trong tập quan sát | Xem bất thường, nhưng rất nhạy với nhiễu |
| `average` | Trung bình cộng | Hữu ích bổ sung, không thay thế percentile |

Ví dụ giả định: p50 = 18 ms, p95 = 85 ms và p99 = 270 ms. Điều này cho thấy nhiều request nhanh nhưng khoảng đuôi có thời gian dài hơn đáng kể. Phân vị cần đi kèm **số mẫu**, khoảng thời gian đo và loại request.

**Không bỏ request lỗi hoặc timeout khỏi báo cáo.** Nếu chỉ tính p99 trên request thành công rồi bỏ qua 5% request timeout, bảng độ trễ có thể che giấu một sự cố nghiêm trọng. Nên phân nhóm latency của request thành công, số lỗi, số timeout và tỷ lệ hoàn tất trong thời hạn.

### 2.2. Throughput: hoàn tất bao nhiêu công việc mỗi giây?

Thông lượng đo số thao tác **hoàn thành** trong một khoảng thời gian:

\[
\text{Throughput (ops/s)}
=\frac{\text{Số thao tác hoàn tất}}{\text{Thời gian đo (giây)}}
\]

Ví dụ hoàn tất 12.000 request trong 120 giây thì throughput là **100 request/s**. Với công việc khác nhau, xác định rõ đơn vị: **HTTP requests/s**, **Cypher queries/s**, **transactions/s**, **rows/s** hoặc **events/s**. Một HTTP request có thể thực hiện nhiều câu Cypher, nên các con số đó không hoán đổi trực tiếp.

Đặc biệt cần phân biệt:

- **Offered load (tải yêu cầu):** tốc độ gửi request dự kiến của máy tạo tải.
- **Achieved throughput (tải hoàn tất):** số request thực sự được xử lý xong mỗi giây.
- **Timeout/error/retry:** lượng việc thất bại hoặc được làm lại; không tính tất cả retry như giao dịch nghiệp vụ thành công.

Nếu máy tạo tải gửi 300 request/s nhưng hệ thống chỉ hoàn tất 190 request/s, không thể nói throughput của hệ thống là 300 request/s.

### 2.3. Concurrency: bao nhiêu thao tác đang diễn ra?

**Concurrency** là số request/transaction đang xử lý đồng thời. Nó khác throughput: tăng số worker hoặc connection chưa chắc tăng số request hoàn tất.

Khi hệ thống ổn định, không mất request và mọi chỉ số cùng phạm vi, **định luật Little** cho mối liên hệ gần đúng:

\[
L \approx \lambda W
\]

Trong đó `L` là số công việc trung bình đang có trong hệ thống, `\lambda` là tốc độ hoàn tất (công việc/giây) và `W` là thời gian trung bình một công việc ở trong hệ thống (giây). Ví dụ với 100 req/s và thời gian trung bình 0,05 giây, có khoảng 5 request đồng thời **trong phạm vi được đo**. Đây không phải công thức đảm bảo một server sẽ đạt tốc độ cụ thể, nhất là khi tải không ổn định, có queue hoặc hệ thống đang bão hòa.

### 2.4. Ghi rõ định nghĩa của một lần đo

Trước khi benchmark, cần thống nhất:

1. **Một thao tác** nghĩa là gì: một HTTP request, một managed transaction hay một query?
2. Thời gian bắt đầu ở đâu: trước khi đợi connection hay sau khi đã lấy được connection?
3. Khi nào thao tác kết thúc: sau `run`, sau `consume`/đọc hết records hay sau khi gửi hết HTTP response?
4. Retry/timeout có được tính vào độ trễ không?
5. Đọc ở leader, follower hay từ các instance khác nhau trong cluster? Dùng bookmark khi cần đảm bảo đọc sau ghi?

Không thống nhất định nghĩa thì hai lần thử rất dễ cho số liệu “cải thiện” chỉ vì thay đổi điểm bấm đồng hồ.

## 3. Xây dựng workload đại diện cho nghiệp vụ

Không nên chạy một truy vấn `MATCH (n) RETURN count(n)` hàng nghìn lần rồi coi kết quả là hiệu năng của ứng dụng đồ thị. Cần chọn **hỗn hợp truy vấn** theo log và dữ liệu nghiệp vụ, ví dụ:

| Nhóm công việc | Tỷ lệ giả định | Ví dụ | Đặc điểm áp lực |
| --- | ---: | --- | --- |
| **Tra cứu theo khóa** | 50% | Tìm `Customer` theo `customerId` | Index seek, connection, cache |
| **Duyệt quan hệ ngắn** | 25% | Khách hàng → đơn hàng qua `PLACED` | Độ phân nhánh, đọc nhiều node/relationship |
| **Đường đi nhiều bước** | 10% | `KNOWS*1..3` từ một `Person` | Bùng nổ số hàng trung gian |
| **Ghi giao dịch** | 10% | Tạo/cập nhật `Order` và quan hệ | Khóa ghi, transaction log, constraint |
| **Nhập/đồng bộ theo lô** | 5% | `UNWIND` các sự kiện có ID ổn định | I/O, bộ nhớ, transaction size |

Tỷ lệ trên chỉ là **ví dụ**. Với hệ thống thực tế, lấy phân phối từ telemetry hoặc logs; tách bài test online latency khỏi job import dài nếu chúng có lịch chạy khác nhau, đồng thời bổ sung kịch bản chạy **cùng lúc** khi đó là tình huống vận hành thật.

### Phân phối tham số phải giống thực tế

Hai truy vấn dùng cùng Cypher nhưng ID khác nhau có thể tốn chi phí rất khác:

- Một khách hàng có 2 đơn và một khách hàng có 500.000 đơn đều đi từ `Customer` qua `PLACED`, nhưng lượng quan hệ mở rộng khác rất xa.
- Một `Person` có 5 cạnh `KNOWS` và một `Person` nổi tiếng có hàng chục nghìn cạnh sẽ tạo tải khác.
- Truy vấn mới nhất trong 24 giờ có thể chọn lọc hơn hẳn truy vấn quét cả năm.

Tập tham số test nên có **các khóa thường gặp, khóa hiếm, node có độ phân nhánh cao, truy vấn không có kết quả và dữ liệu theo thời gian**. Không dùng một ID cố định để đo mọi request: hệ thống có thể hưởng lợi cache bất thường.

### Quy mô và hình dạng đồ thị

Cần tương đồng không chỉ tổng số node mà cả:

- Số relationship và độ phân bố bậc node (*degree distribution*).
- Tỷ lệ node theo label, relationship theo type, độ chọn lọc của thuộc tính.
- Kích thước thuộc tính, các index/constraint, phần trăm dữ liệu vừa ghi.
- Tỷ lệ nóng/lạnh theo cache và dữ liệu tăng trưởng theo thời gian.

Một đồ thị thử nghiệm có 10.000 node phân bố đều thường không mô phỏng được hệ thống sản xuất chứa vài node **siêu kết nối**. Nếu bắt buộc dùng dữ liệu mẫu, cần ghi rõ hạn chế này khi kết luận.

## 4. Thiết kế một phép thử tải có thể lặp lại

### 4.1. Thiết lập điều kiện trước khi đo

Ghi lại **Neo4j version/edition**, cấu hình database, kích thước heap và page cache, topology cluster, phần cứng, loại ổ đĩa, network, Java Driver version, giới hạn connection pool, số instance ứng dụng, schema index/constraint và kích thước dữ liệu. Cần có một **baseline** trước khi sửa Cypher hoặc cấu hình.

Đảm bảo index ở trạng thái sẵn sàng:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;
~~~

`ONLINE` cho biết index đã sẵn sàng, nhưng không chứng minh query planner đang sử dụng index đó. Việc dùng index phải được kiểm tra riêng qua `EXPLAIN`/`PROFILE`.

### 4.2. Warm-up và thời gian đo ổn định

Một kịch bản thử nghiệm thông dụng gồm:

1. **Chuẩn bị:** nạp dữ liệu, kiểm tra kết quả nghiệp vụ và sẵn sàng connection.
2. **Warm-up:** chạy hỗn hợp workload để JVM, driver, plan cache, page cache và các thành phần khác đạt trạng thái đại diện.
3. **Steady state:** đo trong một cửa sổ đủ dài để quan sát p95/p99, throughput, CPU và GC. Chọn thời lượng theo yêu cầu độ chính xác, không lấy một lần chạy ngắn làm kết luận.
4. **Thử tăng tải:** nâng offered load qua nhiều mức cho đến gần vùng bão hòa; phải giới hạn để không gây tác động ngoài dự kiến.
5. **Kết thúc:** ghi lại version, tham số, lỗi, biểu đồ và đối chiếu dữ liệu còn đúng sau các thao tác ghi.

**Cold cache** và **warm cache** là hai kịch bản khác nhau. Nếu người dùng thường truy vấn dữ liệu vừa được truy cập gần đây, warm cache có ý nghĩa. Nếu hệ thống định kỳ quét phần lớn kho dữ liệu sau restart, cold cache cũng cần được đo. Đừng âm thầm so sánh trước/sau trong hai trạng thái cache khác nhau.

### 4.3. Mô hình tạo tải: closed-loop và open-loop

- **Closed-loop:** một worker chờ request hoàn tất rồi gửi request tiếp theo. Khi server chậm, tốc độ gửi tự giảm; phép thử có thể che một phần tình trạng backlog của hệ thống thực.
- **Open-loop:** gửi request theo tốc độ mục tiêu độc lập với thời gian phản hồi, giúp nhìn rõ queue, timeout và khi không đáp ứng nổi offered load. Máy tạo tải cần đủ năng lực và phải ghi lại tốc độ phát thực tế.

Đối với cả hai, không tăng concurrency mà bỏ qua **timeout, backlog hoặc tốc độ hoàn tất**. Nếu hệ thống không ổn định hoặc quá tải, phần trăm latency từ các request được hoàn tất có thể không còn phản ánh toàn bộ trải nghiệm.

## 5. Đo độ trễ ở tầng Java Driver và Spring

### 5.1. Đặt đồng hồ ở ranh giới thao tác nghiệp vụ

Ví dụ Java Driver sau đo một lượt lấy 20 đơn gần nhất; thời gian bao gồm mở session, managed read transaction và đọc hết kết quả. `System.nanoTime()` thích hợp để đo **khoảng thời gian**, không dùng để tạo timestamp tuyệt đối.

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public class OrderReadLatency {
    private static final String QUERY = """
        MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
        RETURN o.orderId AS orderId
        ORDER BY o.createdAt DESC
        LIMIT 20
        """;

    static long measureOnce(Driver driver, String customerId) {
        long started = System.nanoTime();
        try (Session session =
                     driver.session(SessionConfig.forDatabase("neo4j"))) {
            List<String> ids = session.executeRead(tx ->
                    tx.run(QUERY, Map.of("customerId", customerId))
                      .list(record -> record.get("orderId").asString()));

            // Kết quả đã được đọc đầy đủ trước khi kết thúc đo.
            if (ids.size() > 20) {
                throw new IllegalStateException("Sai giới hạn kết quả");
            }
        }
        return TimeUnit.NANOSECONDS.toMicros(
                System.nanoTime() - started);
    }

    public static void main(String[] args) {
        // Chỉ là ví dụ cấu hình: lấy thông tin đăng nhập từ nơi lưu an toàn.
        try (Driver driver = GraphDatabase.driver(
                "bolt://localhost:7687",
                AuthTokens.basic("neo4j", "password-from-config"))) {
            driver.verifyConnectivity();
            // Với benchmark thật: warm-up, chạy nhiều ID đại diện,
            // đo song song bằng session riêng cho từng công việc.
            long micros = measureOnce(driver, "C-101");
            System.out.println("Elapsed (microseconds): " + micros);
        }
    }
}
~~~

Ví dụ này đo **một lượt minh họa**, không phải công cụ benchmark có ý nghĩa thống kê. Để đo tải thực tế, cần nhiều mẫu, request song song có kiểm soát, tính percentile sau khoảng đo và ghi rõ số lỗi. Không in console từng request bên trong phần đo vì I/O của logging có thể làm méo số liệu.

**Lưu ý về giao dịch:** callback `executeRead` có thể được chạy lại khi driver gặp lỗi transient phù hợp. Thời gian ngoài callback phản ánh cả phần retry đó; thời gian đặt **bên trong** callback chỉ phản ánh từng attempt. Hai cách đo đều hữu ích nhưng trả lời hai câu hỏi khác nhau.

Khi chạy song song, chia sẻ **Driver** (được thiết kế để dùng chung) nhưng tạo **Session riêng cho từng luồng/request**; không chia sẻ một Session giữa các tác vụ đồng thời. Kích thước pool và số kết nối tới cluster cần phù hợp với workload, nhưng tăng pool quá lớn có thể khiến Neo4j tranh chấp tài nguyên nặng hơn.

### 5.2. Instrument trong Spring Data Neo4j

Ở ứng dụng Spring Boot dùng Spring Data Neo4j, nên theo dõi đồng thời:

- **HTTP server latency** và tỷ lệ response lỗi ở API.
- **Service method duration** cho các ca sử dụng: tra cứu theo khóa, tìm đường đi, ghi đơn hàng.
- **Thời gian thao tác với Neo4j** (qua instrumentation/metrics được phiên bản framework và driver hỗ trợ).
- **Connection pool pending/acquired**, retry, timeout nếu thư viện và cấu hình quan sát hiện có cung cấp.

Micrometer/Actuator là những công cụ thường được dùng để xuất metric, song **tên metric, tag và khả năng tự động instrument Neo4j tùy phiên bản**; kiểm tra danh sách metric thực tế trước khi dựng dashboard. Tránh đặt `customerId`, `orderId` hoặc Cypher chứa dữ liệu cá nhân thành **nhãn metric** vì độ phân mảnh nhãn có thể làm tăng bộ nhớ và rủi ro lộ thông tin. Dùng nhãn ổn định như `operation=read_customer_orders`, `result=success|error` hoặc `workload=graph_traversal`.

## 6. Quan sát tài nguyên phía Neo4j

Truy vấn càng chậm dưới tải không nhất thiết do planner lựa chọn kém. Đôi khi planner đã dùng index đúng nhưng database bão hòa CPU, cache hoặc I/O. Khi đo, thu thập các nhóm chỉ số **cùng mốc thời gian** với biểu đồ latency/throughput:

| Nhóm | Quan sát | Dấu hiệu chẩn đoán |
| --- | --- | --- |
| **CPU** | CPU tiến trình Neo4j, CPU toàn host, tải các lõi | CPU cao kéo dài đi cùng p95 tăng, throughput không tăng thêm |
| **Heap và GC** | Heap đang dùng, tần suất/thời gian GC, vùng nhớ của JVM | Nhiều GC pause có thể làm latency đuôi tăng |
| **Page cache** | Dung lượng, hit/miss, page faults hoặc I/O liên quan | Miss hoặc page faults tăng khi working set không còn vừa cache |
| **Disk/transaction log** | Thông lượng, độ trễ I/O, ghi log, checkpoint | Transaction ghi/import nặng khiến I/O thành nút thắt |
| **Query/transaction** | Số giao dịch đang hoạt động, thời gian chờ, truy vấn chậm, lỗi | Lock contention, hàng đợi và truy vấn lâu bất thường |
| **Network/Bolt/driver pool** | Connection đang dùng/đang chờ, throughput network, timeout | Client đợi lấy connection hoặc trả payload lớn |
| **Cluster** | Tải từng thành viên, read routing, trạng thái đồng bộ/replication theo tính năng sẵn có | Tải lệch, độ trễ đọc sau ghi hoặc chờ đồng bộ |

Tùy cách triển khai, dùng metrics được Neo4j hỗ trợ, dashboard quản trị, hệ thống giám sát host/container, query log và telemetry từ ứng dụng. Không giả định mọi bản Neo4j hay Aura đều cung cấp cùng một bộ metric, cấu hình log hoặc khả năng xuất Prometheus/JMX. Trên production, bật ghi log truy vấn hay thu thập chi tiết phải cân nhắc **chi phí overhead**, sampling và bảo vệ tham số nhạy cảm.

### Page cache và heap không phải một

**Heap** là vùng nhớ phục vụ đối tượng Java và hoạt động JVM; **page cache** hỗ trợ truy cập dữ liệu lưu trữ của Neo4j. Tăng heap không mặc định sửa được tình trạng page cache quá nhỏ. Đồng thời, cấp phát RAM quá mức cho heap + page cache + hệ điều hành và các thành phần khác có thể khiến máy bị thiếu bộ nhớ.

Khi đánh giá page cache, xem hit/miss và I/O **theo workload**. Tỷ lệ hit cao chưa chắc truy vấn tốt nếu một truy vấn vẫn đọc hàng triệu phần tử không cần thiết; thiếu index và mở rộng quan hệ quá mức vẫn gây nhiều công việc.

### Độ trễ tăng không đồng nghĩa CPU thiếu

Ví dụ: CPU server chỉ 40% nhưng p99 tăng mạnh. Các nguyên nhân có thể gồm:

- Connection pool của ứng dụng nhỏ và nhiều request **đợi được cấp connection**.
- Transaction ghi giữ khóa khiến truy vấn khác bị chặn.
- Ổ đĩa có độ trễ cao hoặc có I/O contention trong khi CPU chưa bão hòa.
- Hệ thống gửi kết quả lớn qua đường mạng chậm.
- Workload mở rộng từ vài node bậc cực cao, khiến một phần request chậm hơn hẳn.

Phải đối chiếu dữ liệu **tại cùng thời điểm** trước khi tăng kích thước máy hoặc thay đổi cấu hình database.

## 7. Sử dụng EXPLAIN và PROFILE để giải thích số liệu

Sau khi đo ở tải thực tế và phát hiện một **operation** bị chậm, lấy truy vấn/đầu vào đại diện để xem kế hoạch:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = $status
RETURN o.orderId
LIMIT 20;
~~~

`EXPLAIN` lập kế hoạch mà **không thực thi** câu truy vấn. Nó giúp xác định database dự định:

- `NodeUniqueIndexSeek` hoặc `NodeIndexSeek` từ `Customer.customerId` nếu schema phù hợp;
- `NodeByLabelScan` / `AllNodesScan` nếu phải đọc tập dữ liệu rộng;
- `Expand(All)` để duyệt các quan hệ `PLACED`;
- `Filter`, `Sort`, `Distinct` hoặc toán tử khác sau bước truy cập.

Khi an toàn, chạy `PROFILE` để đo công việc thực tế:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = $status
RETURN o.orderId
LIMIT 20;
~~~

`PROFILE` **thực sự chạy truy vấn**, kể cả với lệnh ghi/xóa; hãy tránh dùng `PROFILE` tùy tiện trên production. Nó có thể tạo thêm overhead nên **không dùng thời gian PROFILE làm số latency chính của benchmark**. Vai trò của nó là cho biết **Rows, Estimated Rows, DB Hits và toán tử** để giải thích tại sao workload chậm.

| Điều thấy trong PROFILE | Giả thuyết | Bước tiếp theo |
| --- | --- | --- |
| `AllNodesScan` đọc gần như toàn bộ node | Thiếu label hoặc điều kiện chọn lọc | Thêm điều kiện đúng nghiệp vụ, cân nhắc index phù hợp |
| `NodeByLabelScan` rất lớn, `Filter` chỉ giữ vài hàng | Thuộc tính lọc cần index | Kiểm tra độ chọn lọc và property index |
| `NodeIndexSeek` ra 1 node, `Expand(All)` ra hàng triệu hàng | Node bậc cao, fan-out quan hệ lớn | Đổi điểm xuất phát, mô hình hóa/lọc sớm, giới hạn phạm vi |
| `Sort` xử lý rất nhiều hàng trước `LIMIT` | Sắp xếp tập trung gian lớn | Tìm cách giới hạn/lọc sớm hoặc dùng index phù hợp |
| `CartesianProduct` trên hai tập lớn | Thiếu mối liên hệ giữa hai mẫu | Kết nối mẫu bằng relationship/điều kiện thích hợp |

Một truy vấn có index seek **vẫn có thể chậm** nếu sau seek nó mở rộng quá nhiều relationship. Ngược lại, scan trên tập nhỏ có thể là lựa chọn tốt. Không tối ưu chỉ để tên toán tử đổi từ `Scan` thành `Seek`.

## 8. Phân tích tải tăng dần và điểm bão hòa

Thay vì chạy một mức tải duy nhất, hãy cố định dữ liệu/hỗn hợp truy vấn và đo nhiều nấc offered load. Bảng dưới đây hoàn toàn **giả định**:

| Offered load (req/s) | Completed (req/s) | p95 thành công (ms) | p99 thành công (ms) | Lỗi/timeout | CPU Neo4j |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 50 | 32 | 58 | 0% | 18% |
| 100 | 100 | 46 | 93 | 0% | 35% |
| 180 | 176 | 105 | 240 | 0,4% | 71% |
| 250 | 191 | 410 | 1.250 | 7% | 94% |
| 320 | 190 | 1.100 | 3.800 | 19% | 97% |

Diễn giải: thông lượng tăng gần tuyến tính ở mức thấp, sau đó chỉ tăng rất ít từ 180 lên 250 req/s dù tốc độ gửi cao hơn nhiều. p95/p99, lỗi và CPU tăng mạnh: hệ thống có dấu hiệu **gần hoặc vượt ngưỡng bão hòa**. Việc tăng thêm số worker lúc này chủ yếu làm tăng thời gian chờ hoặc số request thất bại.

Để xác định **nút thắt thật**, cần dữ liệu bổ sung: pool đang chờ, queue, CPU chi tiết, GC, disk và các truy vấn chậm. Bảng minh họa **không đủ để kết luận** phải tăng CPU hay sửa index.

### Chọn ngưỡng theo SLO

Ví dụ một SLO nội bộ yêu cầu:

- Hoàn tất **ít nhất 99,9%** request hợp lệ trong khoảng đo;
- p95 của thao tác đọc đơn hàng **dưới 150 ms**;
- Đạt **150 request/s** trong hỗn hợp nghiệp vụ mục tiêu;
- Không làm các giao dịch ghi quan trọng giảm throughput hoặc tăng lock wait vượt ngưỡng chấp nhận.

Các số này phải được thỏa thuận theo sản phẩm và khách hàng, không được xem là “SLO mặc định của Neo4j”. Tải chấp nhận được là mức đạt cả **độ trễ + thông lượng + lỗi + giới hạn tài nguyên**, không chỉ mức tối đa requests/s.

## 9. Những bẫy làm sai lệch benchmark

### Bẫy 1: Chỉ dùng một khách hàng hoặc một tham số

Lặp lại cùng `customerId` sẽ tận dụng working set rất nhỏ trong cache và bỏ sót node có độ phân nhánh cao. Dùng tập ID đủ rộng, phân bố nóng/lạnh đại diện, có cả request không khớp.

### Bẫy 2: Chỉ đo thời gian trả về từ `run()`

API driver có thể trả về đối tượng kết quả trước khi toàn bộ records được đọc/consume. Thời gian quá ngắn sẽ bỏ qua phần truyền dữ liệu và xử lý kết quả. Đo đến khi đã **tiêu thụ kết quả cần thiết**.

### Bẫy 3: Thay workload giữa hai lần đo

Một run có 90% tra cứu đơn giản, run khác có 30% truy vấn đường đi nhiều bước thì kết quả không so sánh trực tiếp. Giữ tỷ lệ, dữ liệu, tham số, thời lượng và điều kiện môi trường tương đương.

### Bẫy 4: Load generator tự bị bão hòa

CPU, network hoặc pool của máy tạo tải có thể là nút thắt. Ghi lại offered load thực, client queue và chi phí tạo tải. Nếu không đạt tốc độ phát mong muốn, không quy tất cả giới hạn cho Neo4j.

### Bẫy 5: Chỉ xem request thành công

Khi request timeout, phần request thành công còn lại thường là những request nhanh hơn; p95 trông đẹp hơn thực tế. Báo cáo **thời gian, tỷ lệ lỗi, timeout, retry và số request chưa hoàn tất** song song.

### Bẫy 6: Tính trung bình từ p95 của nhiều cửa sổ

Không thể lấy trung bình các p95 của từng phút rồi coi đó là p95 chung. Percentile phải được tính từ **phân phối mẫu phù hợp** hoặc hệ thống histogram có thể tổng hợp đúng, với các bộ lọc thống nhất.

### Bẫy 7: Tối ưu truy vấn đọc nhưng quên ảnh hưởng ghi

Thêm index có thể làm tra cứu nhanh hơn nhưng tạo thêm công việc khi `CREATE`/`SET`/`DELETE`. Hãy đo lại throughput ghi, chi phí nhập lô, không gian lưu trữ và tail latency khi workload vừa đọc vừa ghi.

### Bẫy 8: Dùng kết quả PROFILE làm chuẩn hiệu năng cuối

`PROFILE` giúp phân tích plan, nhưng có overhead và không mô phỏng giao dịch đa luồng, pool, mạng, API hoặc tỉ lệ truy vấn thực tế. Chọn **benchmark tại ứng dụng** làm số đo chính và dùng `PROFILE` để giải thích.

## 10. Quy trình tối ưu và tái đo theo bằng chứng

Một vòng làm việc nên đi theo thứ tự:

~~~mermaid
flowchart TD
    A["Chọn operation và SLO"] --> B["Đo baseline theo workload thực tế"]
    B --> C["Khoanh vùng p95/p99, lỗi và tài nguyên"]
    C --> D["EXPLAIN/PROFILE truy vấn nghi vấn"]
    D --> E["Chỉ thay đổi một nhóm yếu tố"]
    E --> F["Chạy lại cùng workload và dữ liệu"]
    F --> G{"SLO và tài nguyên tốt hơn?"}
    G -->|Có| H["Ghi nhận kết quả và triển khai có kiểm soát"]
    G -->|Chưa| C
~~~

Các thay đổi có thể là:

- **Cypher:** thêm label/type, lọc theo khóa sớm, giảm số đường đi duyệt, chỉ trả trường cần thiết, tránh `CartesianProduct` vô ý.
- **Schema:** dùng range index hoặc uniqueness constraint theo điều kiện truy vấn thật sự; không tạo index vô hạn.
- **Mô hình dữ liệu:** điều chỉnh truy vấn từ node bậc cao, giảm fan-out không cần thiết, bổ sung quan hệ/thuộc tính phục vụ truy vấn trọng yếu nếu có cơ sở.
- **Ứng dụng:** dùng chung Driver, đóng Session đúng cách, tiêu thụ kết quả có kiểm soát, cấu hình pool/timeout theo tải, batch các thao tác có lợi mà vẫn bảo đảm transaction semantics.
- **Vận hành:** kiểm tra CPU, page cache, heap, GC, ổ đĩa, mạng và phân bổ workload trước khi nâng cấp phần cứng.

Nên thử **một nhóm thay đổi mỗi lần** hoặc có cách tách riêng tác động. Mỗi lần đo báo cả **chi phí**: index mới dùng thêm storage, truy vấn mới có thể trả kết quả khác, batch lớn gây transaction lâu, pool lớn có thể tăng tranh chấp.

### Mẫu bảng so sánh trước/sau

| Chỉ số | Trước tối ưu | Sau tối ưu | Quy tắc diễn giải |
| --- | --- | --- | --- |
| p50/p95/p99 của **cùng operation** | Ghi số đo | Ghi số đo | Đuôi latency có cải thiện không? |
| Throughput hoàn tất tại cùng offered load | Ghi số đo | Ghi số đo | Có thực hiện được nhiều thao tác hơn không? |
| Lỗi/timeout/retry | Ghi số đo | Ghi số đo | Có đang đổi tốc độ lấy độ tin cậy? |
| CPU, GC, page cache, disk, network | Ghi số đo | Ghi số đo | Tài nguyên có bị chuyển nút thắt sang nơi khác? |
| `Rows` và `DB Hits` ở plan nghi vấn | Ghi số đo | Ghi số đo | Truy vấn có đọc ít dữ liệu vô ích hơn không? |
| Đúng dữ liệu nghiệp vụ | Kiểm thử | Kiểm thử | Kết quả phải giữ đúng ngữ nghĩa |

Không tự động coi p95 thấp hơn trong run **ít tải hơn** là tối ưu. Để so sánh công bằng, cần cố định mức offered load và hỗn hợp công việc, sau đó mới so sánh ngưỡng bão hòa tối đa.

## 11. Bài thực hành: đánh giá truy vấn đơn hàng

**Bối cảnh:** Đồ thị có `Customer`, `Order`, relationship `PLACED` và API liệt kê 20 đơn gần nhất của khách hàng. Mục tiêu là đạt SLO do nhóm tự đặt trong khi 20% khách hàng có nhiều đơn hơn mức điển hình.

**Bước 1 — Kiểm tra truy vấn và schema.** Chuẩn bị một tập tham số có khách hàng ít đơn, khách hàng nhiều đơn và ID không tồn tại. Xem index:

~~~cypher
SHOW INDEXES
YIELD name, entityType, labelsOrTypes, properties, state
RETURN name, entityType, labelsOrTypes, properties, state;
~~~

Sau đó thử:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

**Bước 2 — Dự đoán chi phí.** Nếu một khách hàng có 500.000 đơn hàng, hỏi liệu `LIMIT 20` có tự ngăn `Expand(All)` xem nhiều cạnh hoặc `Sort` xử lý nhiều kết quả hay không. Câu trả lời: **không được đảm bảo**; phụ thuộc kế hoạch và thứ tự truy cập. Hãy kiểm tra kết quả đo.

**Bước 3 — Tạo workload.** Chạy ở ba mức offered load, ví dụ 30/80/150 req/s. Warm-up trước, sau đó đo nhiều phút, lấy đủ mẫu để đọc p95/p99; báo số lỗi và mọi request chưa hoàn tất.

**Bước 4 — Đồng thời quan sát Neo4j.** Thu thập CPU, GC, page cache, disk, transaction và metrics connection pool (nếu có) theo cùng trục thời gian. Ghi lại khi p99 tăng.

**Bước 5 — Chẩn đoán.** Dùng `PROFILE` trên truy vấn **chỉ đọc**, với một vài customer đại diện. Xác định số hàng `Expand(All)`, số hàng trước `Sort` và DB Hits. Không lấy thời gian `PROFILE` thay cho latency benchmark.

**Bước 6 — Thử một cải tiến.** Ví dụ thêm predicate thời gian phù hợp nghiệp vụ, giới hạn khoảng cần duyệt, hoặc cân nhắc lối truy cập từ `Order` nếu có index và ràng buộc tìm đúng khách hàng. Bất kỳ thay đổi nào cũng phải trả về **đúng danh sách đơn** theo yêu cầu.

**Bước 7 — Đo lại đúng cùng workload.** So sánh p50/p95/p99, throughput, lỗi và mức dùng tài nguyên; giải thích vì sao một thay đổi có hiệu quả ở khách hàng ít đơn nhưng có thể khác ở khách hàng có bậc cao.

### Câu hỏi tự kiểm tra

1. **p95 tốt hơn nhưng tỷ lệ timeout tăng từ 0% lên 8% là cải thiện không?** Chưa thể coi là cải thiện; phải đánh giá độ tin cậy và cả những request thất bại.
2. **Thêm 50 connection làm throughput không tăng nhưng p99 tăng. Vì sao?** Server có thể đã bão hòa, tranh chấp nhiều hơn hoặc queue thay đổi; kiểm tra pool và tài nguyên trước khi tăng tiếp.
3. **`NodeIndexSeek` xuất hiện, liệu truy vấn chắc chắn nhanh?** Không. `Expand(All)`, `Sort` hoặc trả payload lớn có thể mới là chi phí chính.
4. **Có thể so p99 giữa hai run có thời lượng và số mẫu rất khác nhau không?** Cần thận trọng; phải kiểm tra độ ổn định và cỡ mẫu, đồng thời giữ workload giống nhau.
5. **Vì sao cần quan sát cả application và database?** Để tách chậm do Java Driver/pool/network/API khỏi chậm do thực thi Cypher, cache hay tài nguyên Neo4j.

## 12. Checklist triển khai đo hiệu năng

- [ ] Định nghĩa rõ **operation**, ranh giới bấm đồng hồ, SLO, timeout và cách ghi nhận retry.
- [ ] Chọn dữ liệu đại diện về label, type, thuộc tính, độ phân nhánh quan hệ và tập tham số nóng/lạnh.
- [ ] Tạo hỗn hợp đọc/ghi/duyệt/import và tốc độ gửi gần thực tế; có phương án thử đồng thời nếu hệ thống chạy nhiều workload.
- [ ] Warm-up có kiểm soát, đo steady state, giữ cùng môi trường giữa baseline và lần tối ưu.
- [ ] Thu **p50/p95/p99, throughput hoàn tất, offered load, concurrency, lỗi, timeout**.
- [ ] Đối chiếu CPU, heap/GC, page cache, disk, network, transaction và connection pool ở cùng thời điểm.
- [ ] Dùng `EXPLAIN` để đọc kế hoạch và `PROFILE` đúng phạm vi để xem `Rows`, `DB Hits`, scan/index/expand.
- [ ] Ghi rõ phiên bản, schema, cấu hình, máy tạo tải và giới hạn môi trường.
- [ ] Đảm bảo các phép thay đổi Cypher/index không làm sai kết quả nghiệp vụ và không tạo tác dụng phụ khi benchmark ghi.
- [ ] So sánh kết quả trên **cùng tải**, sau đó mới xác định vùng bão hòa và dung lượng đáp ứng SLO.

**Kết luận:** Đo tối ưu truy vấn Neo4j đúng cách cần kết hợp **độ trễ đầu cuối**, **thông lượng hoàn tất**, **tỷ lệ lỗi**, **mức dùng tài nguyên** và **kế hoạch thực thi** dưới workload đại diện. Một truy vấn nhanh khi chạy riêng lẻ chưa chứng minh toàn hệ thống nhanh khi nhiều request, transaction và đường đi đồ thị cạnh tranh tài nguyên. Dùng số đo nhất quán trước/sau để xác định nút thắt, chứng minh hiệu quả tối ưu và lựa chọn cấu hình vận hành có cơ sở.
