# Kiểm thử hồi quy index, hiệu năng và tương thích phiên bản server

Một truy vấn **Spring Data MongoDB** có thể tiếp tục trả đúng dữ liệu nhưng chậm hơn nhiều sau khi thay đổi index, nâng MongoDB Server hoặc đổi Java driver. Chẳng hạn, endpoint lấy 20 sự kiện mới nhất của một khách hàng vẫn trả về đúng 20 document trong bài test, nhưng sau một lần nâng cấp lại phải quét hàng trăm nghìn document hoặc sắp xếp trong bộ nhớ. Đây là **hồi quy hiệu năng** mà unit test và kiểm thử kết quả đơn thuần thường không phát hiện.

Chương **Kiểm thử** của **SPRING_DATA_MONGODB** cần phân biệt ba loại bằng chứng:

1. **Hồi quy tính đúng:** truy vấn, mapping, sort, aggregation và update vẫn cho kết quả nghiệp vụ mong đợi.
2. **Hồi quy index và execution plan:** các index cần thiết vẫn tồn tại với định nghĩa đúng, và MongoDB có thể dùng chúng hiệu quả cho query shape quan trọng.
3. **Hồi quy hiệu năng và tương thích phiên bản:** cùng workload hoạt động ở mức chấp nhận được trên phiên bản **MongoDB Server**, topology, **featureCompatibilityVersion (FCV)** và Java driver dự kiến.

Bài này dùng **MongoTemplate**, repository, Testcontainers và công cụ **explain** để xây dựng chiến lược kiểm thử có thể áp dụng khi thay đổi truy vấn, chỉ mục hoặc nâng server. Mục tiêu là tạo bằng chứng kiểm chứng được; một bài test đơn lẻ không thể chứng minh toàn bộ hiệu năng sản xuất.

## 1. Chọn loại kiểm thử theo rủi ro

| Thay đổi hoặc rủi ro | Kiểm thử nên chạy | Bằng chứng cần có |
| --- | --- | --- |
| Đổi điều kiện lọc trong repository | Repository test trên MongoDB thật | Trả đúng document ở các trường hợp biên |
| Thêm/sửa compound, unique, TTL hoặc partial index | Kiểm thử metadata index và hành vi truy vấn | Key, thứ tự trường, direction, options và constraint đúng |
| Đổi sort, pagination, collation | Kiểm thử kết quả + giải thích execution plan | Thứ tự ổn định, không bỏ sót/trùng, không xuất hiện sort tốn kém ngoài dự kiến |
| Thay đổi số lượng document hoặc phân bố dữ liệu | Benchmark có fixture đại diện | p50/p95, throughput, số keys/docs examined, mức sử dụng tài nguyên |
| Nâng MongoDB Server hoặc FCV | Compatibility matrix + repository/integration test | CRUD, query, index, transaction, aggregation và dữ liệu cũ vẫn đúng |
| Đổi Spring Data MongoDB hoặc Java driver | Build, test mapping/query và khởi tạo kết nối thật | Không đứt API, codec/BSON, auth/TLS hay serialization |
| Nâng từ standalone lên replica set/sharded cluster | Integration test với topology phù hợp | Transaction, read/write concern, routing và các giới hạn feature được xác minh |
| Dùng tính năng mới của server | Contract test trên version đích | Lệnh/toán tử hoạt động với đúng FCV, driver và edition |

Nguyên tắc chọn phạm vi: **unit test** đủ cho logic Java thuần; **@DataMongoTest** với MongoDB thật phù hợp để xác minh mapping, truy vấn và index; **@SpringBootTest** phù hợp khi phải kiểm tra cấu hình driver, service, transaction, security hoặc endpoint. Benchmark chạy trên môi trường riêng có dữ liệu và tải đại diện.

~~~mermaid
flowchart TD
    A["Thay đổi query, index, driver hoặc server"] --> B["Kiểm thử kết quả đúng"]
    B --> C["Kiểm tra định nghĩa index"]
    C --> D["Quan sát explain của query thật"]
    D --> E{"Có rủi ro hiệu năng?"}
    E -- "Có" --> F["Benchmark dữ liệu và tải đại diện"]
    E -- "Không" --> G["Ma trận version / FCV / topology"]
    F --> G
    G --> H["Lưu bằng chứng và quyết định triển khai"]
~~~

## 2. Ví dụ: truy vấn sự kiện theo tenant

Một hệ thống đa tenant lưu sự kiện đơn hàng trong collection **order_events**. API cần lấy tối đa 20 sự kiện mới nhất của một tenant, sắp theo **createdAt** giảm dần. Để thứ tự ổn định khi hai sự kiện có cùng thời điểm, thêm **_id** giảm dần làm khóa phụ.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| tenantId | Phân vùng logic bắt buộc trong điều kiện truy vấn |
| createdAt | Thời gian sự kiện, dùng để lấy sự kiện mới nhất |
| _id | Khóa duy nhất, phá hòa khi createdAt trùng |
| type | Loại sự kiện, dùng để minh họa dữ liệu được trả về |

Query shape quan trọng:

~~~javascript
db.order_events.find(
  { tenantId: "tenant-a" }
).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Một index phù hợp cần đánh giá:

~~~javascript
db.order_events.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "tenant_time_id_v1" }
);
~~~

Đặt trường so khớp bằng (**tenantId**) trước các trường phục vụ sắp xếp là một lựa chọn hợp lý cho query shape trên. Kết luận thực tế vẫn cần đo khi thêm các filter khác, collation, projection, sort direction hoặc đặc điểm phân bố dữ liệu.

Mô hình Java dùng trong bài:

~~~java
package example.events;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "order_events")
public class OrderEvent {
    @Id
    private String id;
    private String tenantId;
    private Instant createdAt;
    private String type;

    protected OrderEvent() {
        // Dành cho MongoDB mapping.
    }

    public OrderEvent(
            String id, String tenantId, Instant createdAt, String type) {
        this.id = id;
        this.tenantId = tenantId;
        this.createdAt = createdAt;
        this.type = type;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public Instant getCreatedAt() { return createdAt; }
    public String getType() { return type; }
}
~~~

Ví dụ truy vấn bằng **MongoTemplate**:

~~~java
package example.events;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderEventQuery {
    private final MongoTemplate template;

    public OrderEventQuery(MongoTemplate template) {
        this.template = template;
    }

    public List<OrderEvent> latest(String tenantId, int limit) {
        if (tenantId == null || tenantId.isBlank()
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid request");
        }

        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
        ).with(Sort.by(
            Sort.Direction.DESC, "createdAt", "_id"
        )).limit(limit);

        return template.find(query, OrderEvent.class);
    }
}
~~~

Việc sắp xếp theo **_id** là một tie-breaker nhất quán trong ví dụ dùng khóa chuỗi; nó không đồng nghĩa thời gian trong **ObjectId** luôn thay thế được **createdAt**. Với phân trang thực, phải bảo đảm filter, sort và cursor cùng dùng đúng thứ tự khóa.

## 3. Hồi quy tính đúng: kiểm tra dữ liệu trước khi đo tốc độ

Trước khi quan tâm index, phải biết truy vấn trả đúng dữ liệu. Một fixture nhỏ nên chứa:

- Hai tenant có sự kiện xen kẽ về thời gian để phát hiện lỗi thiếu filter **tenantId**.
- Hai sự kiện cùng **createdAt** để kiểm tra tie-breaker **_id**.
- Trường hợp không có sự kiện và số lượng nhỏ hơn **limit**.
- Document lịch sử có null hoặc thiếu trường cần sort nếu dữ liệu sản xuất cho phép; xác định thứ tự BSON mong đợi trước khi assert.

Kiểm thử kết quả thường không cần hàng triệu document; mục tiêu ở đây là chứng minh nghiệp vụ. Ví dụ:

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

// Chạy trong @DataMongoTest đã nối MongoDB test thật.
@DataMongoTest
class OrderEventQueryExample {
    @Autowired MongoTemplate template;

    @Test
    void returnsOnlyTenantEventsInStableOrder() {
        template.dropCollection(OrderEvent.class);
        Instant earlier = Instant.parse("2026-11-01T09:00:00Z");
        Instant later = Instant.parse("2026-11-01T10:00:00Z");

        template.insert(new OrderEvent("a1", "tenant-a", earlier, "CREATED"));
        template.insert(new OrderEvent("a2", "tenant-a", later, "PAID"));
        template.insert(new OrderEvent("a3", "tenant-a", later, "SHIPPED"));
        template.insert(new OrderEvent("b1", "tenant-b", later, "CREATED"));

        List<String> ids = new OrderEventQuery(template)
            .latest("tenant-a", 2).stream()
            .map(OrderEvent::getId).toList();

        assertEquals(List.of("a3", "a2"), ids);
    }
}
~~~

**Điều kiện chạy:** ví dụ rút gọn trên giả định bài test đã được nối tới một MongoDB instance do Testcontainers hoặc hạ tầng kiểm thử cấp. **@DataMongoTest** tự nó không cấp MongoDB Server. Phần tiếp theo cho ví dụ Testcontainers cụ thể.

Không đưa lệnh **dropCollection** vào test dùng chung database hoặc chạy song song không cô lập. Trong suite lớn, nên cấp database/collection riêng cho từng test hoặc quản lý fixture có kiểm soát.

## 4. Hồi quy index: xác minh định nghĩa thực tế

**@Indexed** hoặc **@CompoundIndex** trong Java biểu thị ý định ánh xạ, nhưng việc tạo index tự động có thể không bật ở mọi cấu hình Spring Data MongoDB. Bài kiểm thử cần xác nhận index **đã tồn tại trong MongoDB** với key và options chính xác, ưu tiên chạy đúng mã migration/index initializer của ứng dụng.

Tách việc tạo index ra thành hàm có thể gọi từ quy trình triển khai và test:

~~~java
package example.events;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

public final class OrderEventIndexes {
    private OrderEventIndexes() {}

    public static void ensure(MongoTemplate template) {
        Index index = new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("createdAt", Sort.Direction.DESC)
            .on("_id", Sort.Direction.DESC)
            .named("tenant_time_id_v1");
        template.indexOps(OrderEvent.class).ensureIndex(index);
    }
}
~~~

Test dưới đây dùng **Spring Boot 3.x / Spring Data MongoDB 4.x** và **Testcontainers 1.x** làm ví dụ minh họa. Các bản major mới của Spring Boot và Testcontainers có thể đổi package hoặc cách kết nối; dùng dependency/BOM phù hợp với dự án thực tế.

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataMongoTest
@Testcontainers
class OrderEventIndexRegressionTest {

    @Container
    static final MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongoUri(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }

    @Autowired MongoTemplate template;

    @BeforeEach
    void createCleanCollectionAndIndex() {
        template.dropCollection(OrderEvent.class);
        OrderEventIndexes.ensure(template);
    }

    @Test
    void indexKeysAndDirectionsMustMatchContract() {
        List<Document> indexDocs = template
            .getCollection("order_events")
            .listIndexes(Document.class)
            .into(new ArrayList<>());

        Document index = indexDocs.stream()
            .filter(d -> "tenant_time_id_v1".equals(d.getString("name")))
            .findFirst().orElseThrow();

        Document expectedKeys = new Document("tenantId", 1)
            .append("createdAt", -1)
            .append("_id", -1);
        assertEquals(expectedKeys, index.get("key", Document.class));
    }
}
~~~

Test này xác minh **index có mặt và đúng thứ tự/direction** sau khi chạy initializer. Nếu thay đổi business rule cần unique, partial, TTL, collation, wildcard hoặc hidden index, phải kiểm tra **options** của index tương ứng; chỉ so sánh key là chưa đủ.

Ví dụ để xem định nghĩa đầy đủ bằng **mongosh**:

~~~javascript
db.order_events.getIndexes();

// Kiểm tra riêng một index theo tên.
db.order_events.getIndexes()
  .find(index => index.name === "tenant_time_id_v1");
~~~

**Các lỗi thường gặp:**

| Lỗi định nghĩa | Hậu quả có thể xảy ra |
| --- | --- |
| Đảo thứ tự **tenantId** và **createdAt** | Index không còn hiệu quả cho cùng filter và sort |
| Bỏ **_id** khỏi phần sort hoặc index | Kết quả cùng thời điểm không có thứ tự ổn định theo yêu cầu |
| Đổi direction trong compound index | Có thể không phục vụ được sort hỗn hợp mong muốn |
| Quên collation trong index hoặc query | Planner có thể không dùng index để so khớp/sắp xếp chuỗi theo locale |
| Đổi partial filter expression | Một số document không được index; query phải thỏa điều kiện tương thích |
| Thay unique/TTL mà không đối chiếu options | Có thể mất ràng buộc dữ liệu hoặc thay đổi thời gian xóa |
| Chỉ sửa annotation, không chạy index migration | Schema trên database vẫn là cấu trúc cũ |

**Cần chú ý:** không tự động drop/recreate index production chỉ để một bài test đạt. Khi index thay đổi, lập migration riêng với kế hoạch triển khai và xử lý index đang có. Test nên kiểm chứng chính đường tạo/nâng index mà hệ thống thực sự sử dụng.

## 5. Hồi quy execution plan: đọc bằng chứng từ explain

Khi một query đúng về kết quả, dùng **explain** để xác định MongoDB thực sự duyệt dữ liệu ra sao. Với query mẫu:

~~~javascript
db.order_events.find({
  tenantId: "tenant-a"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20).explain("executionStats");
~~~

Cần xem ít nhất:

| Trường/chỉ dấu | Cách diễn giải |
| --- | --- |
| **queryPlanner.winningPlan** | Đường thực thi được planner chọn, nhưng hình dạng cây thay đổi theo engine/version |
| **IXSCAN** hoặc nhánh dùng index | Query có duyệt index hay không; cần xem index cụ thể và index bounds |
| **COLLSCAN** | Quét collection; đôi khi hợp lý với collection rất nhỏ, bất lợi trên tập lớn |
| **SORT** | Có thể có bước sắp xếp chặn (blocking sort); cân nhắc index, filter, collation và memory |
| **executionStats.nReturned** | Số document được trả |
| **executionStats.totalKeysExamined** | Số index keys được duyệt; cao bất thường có thể báo query kém chọn lọc |
| **executionStats.totalDocsExamined** | Số document phải đọc; so với nReturned để đánh giá chi phí |
| **executionStats.executionTimeMillis** | Thời gian trong phép explain; chỉ mang tính quan sát cho lần chạy đó |

**Đọc đúng ngữ cảnh:** **IXSCAN** không tự chứng minh query nhanh. Một query có thể dùng index nhưng vẫn phải đi qua hàng trăm nghìn key hoặc truy cập nhiều document để lọc. **COLLSCAN** không phải lúc nào cũng là lỗi: trên collection rất nhỏ, planner có thể chọn full scan hợp lý. Các trường stage trong **classic engine** và **slot-based execution (SBE)** không có cấu trúc JSON giống hệt nhau; việc assert chuỗi của toàn bộ **winningPlan** rất dễ vỡ khi nâng server.

### 5.1. Hai phép explain cho hai câu hỏi khác nhau

Chạy query **không hint** để biết optimizer đang chọn gì:

~~~javascript
db.order_events.find({ tenantId: "tenant-a" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Chạy thêm query **có hint** để kiểm tra hiệu quả khi buộc sử dụng index mong muốn:

~~~javascript
db.order_events.find({ tenantId: "tenant-a" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .hint("tenant_time_id_v1")
  .explain("executionStats");
~~~

Nếu bản **hint** tốt nhưng bản không hint lại chọn plan khác, vấn đề nằm ở quyết định planner, thống kê hoặc query shape. Đừng chỉ chạy explain có hint rồi kết luận workload thật sẽ dùng index đó, trừ khi application query cũng chủ động hint. Và nếu ứng dụng dùng **@Field** để đổi tên thuộc tính, hãy kiểm tra tên **BSON** thực sự được gửi xuống server; lệnh mongosh ở trên sử dụng tên trường MongoDB.

### 5.2. Tự động hóa kiểm tra plan ở mức phù hợp

Trong suite repository/integration test, có thể dùng **MongoTemplate.executeCommand** với lệnh **explain**:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class ExplainInspector {
    public static Document explainLatest(MongoTemplate template) {
        Document find = new Document("find", "order_events")
            .append("filter", new Document("tenantId", "tenant-a"))
            .append("sort", new Document("createdAt", -1)
                .append("_id", -1))
            .append("limit", 20);

        return template.executeCommand(
            new Document("explain", find)
                .append("verbosity", "executionStats")
        );
    }
}
~~~

**Lưu ý:** đây là đoạn minh họa phương thức trong một class Java đầy đủ; khi tích hợp vào repository thực, tránh nhân bản query shape khác với đường ứng dụng đang chạy. Nếu service dùng **Query** có collation, projection hoặc filter bổ sung, lệnh explain phải phản ánh chính xác những phần đó. Có thể dùng command listener ở test để đối chiếu lệnh thực tế mà driver gửi xuống server.

Đối với **plan regression test** bền vững, ưu tiên các bất biến có ý nghĩa:

1. Index metadata vẫn đúng; query trả đúng kết quả, đúng sort/limit.
2. Trên fixture đủ đại diện, **totalDocsExamined**, **totalKeysExamined** không tăng vượt ngân sách đã được xác nhận với đội vận hành.
3. Nếu bắt buộc một index hoặc không được có blocking sort, kiểm tra có chủ đích trên server version cố định, kèm cơ chế nhận diện stage thích ứng với dạng plan tương ứng.
4. Không kiểm tra bằng cách so sánh nguyên văn JSON plan, plan cache key hoặc số millisecond chính xác giữa hai phiên bản khác nhau.

Ví dụ, khi có 100.000 sự kiện trải đều theo nhiều tenant và query chỉ lấy 20 document mới nhất, nếu một thay đổi khiến **totalDocsExamined** tăng từ vài chục lên gần toàn bộ collection thì đó là tín hiệu cần điều tra. Ngưỡng cụ thể phụ thuộc cardinality, độ chọn lọc, projection và dữ liệu thực; **không sao chép cứng một con số vào mọi hệ thống**.

## 6. Benchmark hiệu năng: tách nhiễu khỏi hồi quy

Một phép đo thời gian có thể tăng vì máy CI quá tải, container đang khởi động, Java JIT chưa warm-up, cache còn lạnh hoặc mạng biến động. Do đó nên tách **test chức năng chạy mỗi PR** và **benchmark hiệu năng chạy trên môi trường kiểm soát**.

| Yếu tố | Cách kiểm soát |
| --- | --- |
| Số lượng và phân phối dữ liệu | Ghi rõ số document, số tenant, phân phối thời gian, tỷ lệ null/missing và dữ liệu skew |
| Index và schema | Áp dụng cùng migrations/index options trước mỗi phép đo |
| Phiên bản | Ghi version MongoDB Server, FCV, driver, Spring Data MongoDB, JDK và kiến trúc CPU |
| Topology | So sánh trên cùng kiểu replica set/sharding, read preference và write concern |
| Cache và khởi động | Có warm-up; phân biệt phép đo cold cache và warm cache nếu cần |
| Concurrency | Mô phỏng số client, số query/giây và tỷ lệ đọc/ghi đại diện |
| Môi trường chạy | Giảm tác động của workload không liên quan; ghi CPU, RAM, I/O, network |
| Kết quả | Lưu p50, p95/p99 khi đủ mẫu, throughput, error rate, keys/docs examined |

**Không nên viết kiểm thử cứng kiểu:** “Truy vấn phải chạy dưới 10 ms trên mọi laptop và mọi CI runner”. Kết quả như vậy biến thiên mạnh và gây false positive. Có thể lập ngân sách cho **keys/docs examined** với fixture cố định trong CI, đồng thời dùng môi trường benchmark riêng để kiểm tra latency và thông lượng theo SLO.

Một quy trình benchmark cơ bản:

1. Chụp baseline của phiên bản hiện tại với đúng dữ liệu và index.
2. Chạy warm-up có kiểm soát, ghi rõ liệu phép đo là cold hay warm cache.
3. Chạy nhiều lần bằng workload thống nhất, ghi latency distribution và các metric server.
4. Lặp lại trên phiên bản đích sau khi kiểm chứng schema/index như baseline.
5. So sánh sai lệch vượt ngưỡng đã thống nhất; nếu có hồi quy, lưu query shape, explain, logs/metric và phiên bản để tái hiện.

Ví dụ mẫu báo cáo (chỉ là cấu trúc, **không phải số đo thực tế**):

| Workload | Baseline p95 | Target p95 | Docs examined/query | Kết luận |
| --- | --- | --- | --- | --- |
| Latest 20 events, tenant phổ biến | Đo thực tế | Đo thực tế | So với baseline | Đạt hoặc cần điều tra |
| Latest 20 events, tenant ít dữ liệu | Đo thực tế | Đo thực tế | So với baseline | Đạt hoặc cần điều tra |
| Aggregation theo trạng thái | Đo thực tế | Đo thực tế | So với baseline | Đạt hoặc cần điều tra |

Không dùng **explain executionTimeMillis** như một benchmark tải đầy đủ. Explain có thể khác query chạy bình thường, không đại diện network, serialization, Spring mapping, pool contention hoặc concurrency. Đo thêm từ **MongoTemplate/repository** hoặc endpoint thật bằng công cụ phù hợp, đồng thời quan sát MongoDB metrics.

## 7. Ma trận tương thích phiên bản MongoDB Server

Nâng server thành công không chỉ có nghĩa lệnh kết nối hoạt động. Một thay đổi version có thể ảnh hưởng đến **query planner**, index, các toán tử aggregation, kết quả collation, transaction, server command, BSON conversion, authentication hoặc compatibility của driver.

Cần ghi ít nhất:

- **MongoDB Server binary version** ở tất cả node liên quan.
- **featureCompatibilityVersion (FCV)** trong giai đoạn trước, trong và sau nâng cấp.
- **Topology**: standalone, replica set hay sharded cluster; version của **mongos** nếu có.
- **Edition và dịch vụ**: Community, Enterprise hoặc Atlas; các feature có ràng buộc khác nhau.
- **Java driver và Spring Data MongoDB version**, bao gồm dependency transitives và codec/converter.
- **JDK**, connection string, TLS, auth mechanism, read/write concern và read preference.

Có thể thu thập thông tin bằng **mongosh** khi tài khoản đủ quyền:

~~~javascript
db.version();
db.adminCommand({ buildInfo: 1 });
db.adminCommand({ hello: 1 });

// Có thể cần quyền quản trị và có thể bị hạn chế trên dịch vụ managed.
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

Nếu lệnh FCV hoặc buildInfo không được phép trên môi trường managed, ghi rõ **chưa xác minh** và lấy thông tin từ cấu hình vận hành được phê duyệt. Không suy đoán FCV chỉ từ chuỗi version binary. Đặc biệt với **rolling upgrade**, có thể có giai đoạn các node chạy binary version khác nhau trong khi FCV chưa tăng; mỗi giai đoạn phải tuân thủ trình tự nâng cấp chính thức.

### 7.1. Ma trận tối thiểu cần chạy

| Môi trường kiểm thử | Mục tiêu |
| --- | --- |
| **Baseline**: phiên bản server đang chạy, FCV hiện tại | Giữ kết quả, index definition và metric tham chiếu |
| **Target binary** với FCV theo giai đoạn nâng cấp | Kiểm chứng tương thích khi chuyển tiếp, trước khi bật tính năng mới |
| **Target binary + target FCV** | Kiểm chứng tính năng và workload sau khi nâng cấp hoàn tất |
| **Dữ liệu cũ đã được nâng cấp** | Bảo đảm collection, index, BSON và schema cũ vẫn đọc/ghi đúng |
| **Cluster đại diện cho topology production** | Kiểm tra transaction, sharding, read/write concern, retry và failover nếu thuộc phạm vi |

Một container MongoDB được tạo mới với version đích chỉ chứng minh một môi trường **fresh install**. Nó **không chứng minh đường nâng cấp của dữ liệu và index hiện hữu** hoặc quá trình FCV chuyển trạng thái. Với migration đáng kể, phải khôi phục bản sao dữ liệu an toàn vào staging hoặc thực hiện bài diễn tập nâng cấp theo quy trình MongoDB được hỗ trợ.

### 7.2. Những thứ cần thử lại khi đổi version

| Thành phần | Câu hỏi hồi quy |
| --- | --- |
| Derived repository methods | Tên field, query, sort, paging và null/missing còn đúng? |
| **MongoTemplate** | Query, update, findAndModify, bulk write có giữ kết quả? |
| Aggregation pipeline | Stage/operator có được version và FCV hỗ trợ, kiểu dữ liệu trả về có đúng? |
| Index | Definition, collation, partial filter, TTL/unique có còn nguyên? |
| Query planner | Thay đổi index selection, blocking sort, số key/doc phải quét? |
| Transaction | Commit/rollback, session, retry behavior có đúng trong topology? |
| Reactive access | Publisher, backpressure, timeout/retry và connection pool có ổn định? |
| Security / connection | TLS, authentication, encryption/driver compatibility có đáp ứng chính sách? |

Không mặc định các thuật toán lập kế hoạch hoặc định dạng **explain** giữ nguyên sau upgrade. Chỉ khẳng định tương thích khi đã kiểm tra **chính lệnh, index và query shape mà ứng dụng sử dụng**.

## 8. Chạy test trên nhiều version bằng Testcontainers

Với Spring Boot 3.x, Testcontainers 1.x và MongoDB driver tương thích, có thể cố định image tag qua biến môi trường của CI, rồi cho cùng test suite chạy trên các version khác nhau.

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataMongoTest
@Testcontainers
class MongoVersionMatrixSmokeTest {
    private static final String IMAGE = System.getenv()
        .getOrDefault("MONGO_TEST_IMAGE", "mongo:7.0");

    @Container
    static final MongoDBContainer MONGO = new MongoDBContainer(
        DockerImageName.parse(IMAGE)
    );

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", MONGO::getReplicaSetUrl);
    }

    @Autowired MongoTemplate template;

    @Test
    void indexAndQueryMustWorkOnSelectedServer() {
        template.dropCollection(OrderEvent.class);
        OrderEventIndexes.ensure(template);
        template.insert(new OrderEvent(
            "evt-1", "tenant-a",
            Instant.parse("2026-11-01T10:00:00Z"), "CREATED"
        ));

        assertEquals("evt-1", new OrderEventQuery(template)
            .latest("tenant-a", 20).get(0).getId());
    }
}
~~~

Đây là một **smoke test** chạy trực tiếp trên image được chọn, chỉ chứng minh thao tác tạo index, ghi và đọc cơ bản; nó chưa thay thế bộ repository/integration regression test đầy đủ. Đối với Testcontainers/JUnit và Spring Boot phiên bản khác, cần xác nhận package và API tương thích. Không tạo một container mới cho từng test method nếu không có lý do; nhiều bài kiểm thử có thể dùng cùng container với database/collection được cô lập.

Trong pipeline CI, chạy cùng bộ test với các giá trị **MONGO_TEST_IMAGE** được cố định và duy trì:

~~~text
MONGO_TEST_IMAGE=mongo:7.0   # baseline minh họa
MONGO_TEST_IMAGE=mongo:8.0   # target minh họa
~~~

Các tag trên **chỉ minh họa ma trận** và phải chọn theo cặp version nâng cấp đã được MongoDB công bố hỗ trợ. Nên pin cụ thể hơn khi cần khả năng tái hiện (tag patch hoặc digest). Testcontainers yêu cầu Docker/compatible container runtime và hạ tầng CI đủ tài nguyên.

**Giới hạn của môi trường container:** **MongoDBContainer** có thể cung cấp replica set cho một số bài test, nhưng một node replica set trong CI **không thay thế** sharded cluster, Atlas có cấu hình riêng, quá trình rolling upgrade hoặc môi trường có replication lag thật. Feature gắn với edition hoặc topology khác phải có test riêng trên môi trường tương ứng.

## 9. Ngưỡng chấp nhận: định nghĩa trước, phân biệt lỗi chức năng và nhiễu

Một bộ tiêu chí phù hợp để review cần có ba nhóm:

| Nhóm | Điều kiện pass | Điều kiện phải điều tra |
| --- | --- | --- |
| **Đúng dữ liệu** | Cùng fixture, kết quả query/sort/update/aggregation đúng | Sai document, thứ tự không ổn định, mất dữ liệu, exception |
| **Index và plan** | Index definition đúng; query không phải quét quá nhiều trong workload chuẩn | Index bị mất/đổi options, docs/keys examined tăng mạnh, blocking sort bất ngờ |
| **Hiệu năng** | p95/p99, throughput và error rate trong ngân sách đã thống nhất | Latency tăng có ý nghĩa thống kê trên nhiều lần đo, tài nguyên vượt ngưỡng |

Không dùng một giá trị **millisecond** cố định ở test đơn lẻ để chặn mọi pull request. Nếu buộc phải đặt ngưỡng, nên:

1. Chọn baseline đo từ môi trường có tải và dữ liệu đại diện.
2. Ghi điều kiện đo và độ biến thiên giữa nhiều lần chạy.
3. Tách cảnh báo mềm (cần xem xét) với điều kiện thất bại cứng (mất index, sai constraint, query không được server hỗ trợ).
4. Lưu artifact kết quả benchmark/explain để có thể truy lại nguyên nhân.

Khi so sánh **totalDocsExamined / nReturned**, chú ý query không trả kết quả, projection, covered query, skip, $lookup và cách planner thực thi; tỷ lệ đơn giản không mô tả chính xác mọi workload. Với từng query quan trọng, chọn một hoặc vài chỉ số có tương quan trực tiếp đến chi phí cần tối ưu.

## 10. Các lỗi dễ bỏ sót trong quá trình nâng cấp

### 10.1. Test tự tạo index khác production

Nếu test gọi **ensureIndex** nhưng production phụ thuộc migration riêng hoặc bật/tắt auto-index-creation khác nhau, test có thể xanh trong khi index production không tồn tại. Nên dùng chung định nghĩa migration/index initializer trong test và production, rồi xác nhận deployment script thực sự chạy.

### 10.2. Test dữ liệu quá ít khiến planner chọn COLLSCAN

Một fixture chỉ có vài document có thể khiến planner chọn COLLSCAN mà vẫn rất nhanh. Đừng coi mọi COLLSCAN là hồi quy nếu chưa xét cardinality và dữ liệu. Nếu muốn kiểm tra khả năng tận dụng index, dùng explain có hint; muốn kiểm tra lựa chọn tự nhiên của planner, dùng dữ liệu đại diện và explain không hint.

### 10.3. So sánh nguyên văn JSON explain giữa hai server

Query engine có thể đổi tên stage, lồng thêm nhánh hoặc thay hình dạng SBE; diff JSON khổng lồ cho nhiều cảnh báo giả. Hãy tách **kết quả nghiệp vụ**, **index options**, **metric chi phí** và chỉ số plan thực sự quan trọng.

### 10.4. Chỉ chạy container server mới tinh

Một collection mới không tái hiện dữ liệu BSON cũ, index đã tạo từ phiên bản trước, collection options hoặc lịch sử migration. Cần test với snapshot dữ liệu đã làm sạch và một lần nâng cấp staging theo quy trình được hỗ trợ.

### 10.5. Chỉ kiểm tra kết nối driver

MongoClient kết nối được không bảo đảm toàn bộ aggregation operator, retryable write, transaction hay mapping của ứng dụng tương thích. Phải chạy nghiệp vụ thực, cả nhánh lỗi và dữ liệu biên.

### 10.6. Đổi index nhưng không xét tác động ghi

Thêm index giúp read nhưng tăng chi phí write, lưu trữ và thời gian build. Benchmark cần có workload ghi và mixed read/write; với index mới trên collection lớn, cần thử thời gian tạo và ảnh hưởng tài nguyên trong staging.

### 10.7. Bỏ qua collation, partial index và hint

Index có tên đúng chưa chắc phục vụ query nếu collation khác, partial filter không được thỏa hoặc hint trỏ sai index. Hãy dùng query shape thực, đối chiếu **getIndexes** và kiểm tra hint khi ứng dụng có dùng.

## 11. Một kịch bản hồi quy hoàn chỉnh

Giả sử team đổi **tenant_time_id_v1** để thêm bộ lọc theo loại sự kiện và đồng thời nâng MongoDB Server. Quy trình đề xuất:

1. **Ghi baseline:** dùng dữ liệu cố định, lưu query MongoTemplate thực tế, kết quả sort/limit, định nghĩa index, explain và p95 từ môi trường kiểm soát.
2. **Kiểm thử nghiệp vụ:** chạy repository test cho tenant, sort tie-breaker, limit, kết quả rỗng và filter mới.
3. **Kiểm tra index:** chạy đúng migration mới trên database trống và database có dữ liệu cũ; xác minh key/options từ **getIndexes**.
4. **Phân tích query plan:** chạy explain với và không hint trên baseline/target, so sánh nReturned, keys/docs examined, blocking sort và khả năng dùng index.
5. **Benchmark:** đo workload đại diện nhiều tenant, tenant nóng, tenant ít dữ liệu, thêm tải ghi để đánh giá chi phí duy trì index.
6. **Compatibility matrix:** chạy cùng bộ kiểm thử trên server hiện tại và đích; xác minh FCV, driver, topology và feature được sử dụng.
7. **Diễn tập nâng cấp:** dùng môi trường staging với dữ liệu cũ và đúng trình tự nâng cấp; kiểm tra cả giai đoạn chuyển tiếp và sau nâng FCV.
8. **Lưu bằng chứng:** ghi rõ thay đổi nào được chấp nhận, hồi quy nào cần sửa, cách rollback và điều kiện quyết định go-live.

Mẫu bản ghi bằng chứng:

~~~text
Query: latest-events-by-tenant
Application: Spring Boot/Spring Data MongoDB <version>
Driver/JDK: <version>/<version>
Server/FCV: <version>/<fcv>
Topology/edition: <replica set/sharded>/<edition>
Dataset: <documents, tenants, size, distribution>
Index contract: <name, key, options>
Functional result: <PASS/FAIL>
Explain: <winning plan summary, keys/docs examined, nReturned>
Latency/throughput: <p50/p95/p99, ops/sec, error rate>
Comparison baseline: <version + artifact>
Decision: <PASS / INVESTIGATE / BLOCK>
~~~

**Điểm quan trọng:** các chỉ số trong báo cáo phải là **số liệu quan sát được**, không điền giá trị đo giả định vào biên bản triển khai. Nếu thiếu quyền lấy FCV, thiếu topology phù hợp hoặc chưa kiểm tra dữ liệu cũ, hãy ghi rõ phạm vi bằng chứng còn thiếu.

## 12. Bài thực hành

**Đề bài:** với collection **order_events**, nhóm vận hành đề xuất đổi index phục vụ danh sách sự kiện và nâng MongoDB Server. Hãy lập bộ kiểm thử hồi quy có thể chạy trên CI và staging.

**Yêu cầu:**

1. Tạo ít nhất 4 document cho hai tenant, trong đó hai document có cùng **createdAt**; khẳng định **OrderEventQuery.latest** trả đúng tenant, thứ tự và limit.
2. Dùng **MongoTemplate.indexOps** tạo index tên **tenant_time_id_v1**, sau đó đọc metadata của MongoDB và kiểm tra key direction.
3. Tạo fixture lớn hơn (ví dụ 10.000–100.000 document tùy tài nguyên) phân phối theo nhiều tenant; chạy **explain("executionStats")** với và không hint. Ghi lại **nReturned**, **totalKeysExamined**, **totalDocsExamined** và plan tóm tắt.
4. Chạy cùng suite trên server baseline và target từ hai image tag được pin. Xác minh phiên bản và FCV thực tế; ghi những điểm chưa mô phỏng được bằng container.
5. Viết tiêu chí pass/fail phân biệt sai kết quả, mất index, tăng số document phải đọc và nhiễu latency. Thiết kế thêm một lần đo tải có cả insert để quan sát chi phí index.
6. Đề xuất cách thử với dữ liệu cũ và topology production khi chỉ chạy fresh Testcontainers chưa đủ.

**Tiêu chí đạt:** bộ test phát hiện được truy vấn sai hoặc index bị thay đổi; benchmark có phương pháp đo và so sánh rõ ràng; ma trận version ghi nhận server, FCV, driver, topology và giới hạn của môi trường thử.

## 13. Checklist vận hành

- [ ] Đã xác định query shape, mục tiêu nghiệp vụ và dữ liệu biên.
- [ ] Có repository/integration test dùng MongoDB thật cho query, sort, mapping và index.
- [ ] Định nghĩa index (key, direction, unique/TTL/partial/collation khi có) được kiểm tra từ database.
- [ ] Có explain **không hint** để quan sát planner và **có hint** nếu cần kiểm tra index cụ thể.
- [ ] Đã chọn metric và ngân sách hồi quy phù hợp với fixture/workload thực.
- [ ] Benchmark tách khỏi assertion millisecond mong manh trong CI.
- [ ] Ghi rõ server version, FCV, edition, topology, Spring Data, driver và JDK.
- [ ] Đã thử ít nhất baseline và target version phù hợp; staging xử lý dữ liệu cũ nếu nâng cấp thật.
- [ ] Đã kiểm tra transaction/aggregation/reactive nếu ứng dụng phụ thuộc các tính năng đó.
- [ ] Báo cáo lưu kết quả, explain, index metadata, sai lệch hiệu năng và quyết định triển khai.

**Ghi nhớ:** hồi quy index, hiệu năng và tương thích MongoDB Server là ba chiều liên quan nhưng khác nhau. **Kết quả đúng** không chứng minh truy vấn nhanh; **có index** không chứng minh planner dùng index hợp lý; **chạy được trên server mới** không chứng minh đường nâng cấp và hiệu năng sản xuất an toàn. Chỉ nên quyết định triển khai khi có bằng chứng phù hợp cho cả ba.
