# Phân lớp kiểm thử nghiệp vụ, ánh xạ và tích hợp dữ liệu trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **unit test nghiệp vụ**, **test ánh xạ entity–JSON**, **test repository/template** và **test tích hợp dữ liệu/luồng nghiệp vụ** trong một ứng dụng Spring Data Couchbase.
2. Chọn đúng **test double** (stub/mock/fake) hoặc **Couchbase thật trong môi trường cô lập** tùy lỗi cần phát hiện.
3. Viết JUnit 5 test cho business rules mà **không khởi động Spring hay database**.
4. Thiết lập bài test với `@DataCouchbaseTest`, Testcontainers, `@ServiceConnection` hoặc cấu hình kết nối tường minh theo phiên bản Spring Boot.
5. Kiểm chứng `@Document`, `@Id`, `@Field`, `@Version`, nested object, constructor và nội dung JSON thật, không chỉ kiểm tra Java object trả về.
6. Test riêng **KV theo key**, **SQL++ theo thuộc tính**, **index và scan consistency**, **CAS**, **TTL**, **transaction** và **reactive publisher**.
7. Thiết kế fixture, cleanup, isolation, CI và ma trận lỗi để bộ test ổn định, tái hiện được, không đụng dữ liệu production.

Chủ đề thuộc chương **Kiểm thử** của module **SPRING_DATA_COUCHBASE**. Module này xây dựng tầng truy cập Couchbase bằng Spring Data document mapping, repository, `CouchbaseTemplate` và SQL++, đồng thời phải quản lý bucket/scope/collection, index, TTL, CAS, giao dịch và reactive API. Vì những phần đó có **hành vi do server thực thi**, kiểm thử chỉ dùng mock sẽ không đủ để chứng minh chúng vận hành đúng.

## 1. Đừng gọi tất cả là “unit test repository”

Một service bán hàng có thể chứa ba nhóm quy tắc:

- **Nghiệp vụ:** đơn phải có ít nhất một dòng hàng; số lượng phải dương; tổng tiền không được tràn số; không cho xác nhận đơn đã hủy.
- **Ánh xạ:** `@Id` trở thành Couchbase document key, `@Field("total_amount_vnd")` lưu đúng tên JSON, `@Version` phản ánh CAS và nested value object đọc lại được.
- **Tích hợp dữ liệu:** repository dùng keyspace đúng, index phục vụ SQL++, ghi đồng thời phát hiện conflict, TTL làm document hết hạn, transaction không để trạng thái nửa vời.

Không thể thay thế ba nhóm này bằng một test duy nhất. **Unit test nghiệp vụ** có thể chạy trong vài mili-giây và chỉ kiểm tra Java; **test ánh xạ** cần cơ chế converter thật; **test tích hợp dữ liệu** cần các khả năng server/query/index thật.

~~~mermaid
flowchart TB
    U["Unit test nghiệp vụ\nKhông Spring, không DB"]
    M["Mapping / persistence test\nSpring Data + Couchbase thật"]
    I["Integration test\nRepository, Query, index, CAS, TTL"]
    E["Workflow / E2E test\nAPI, nhiều service, transaction"]
    E --> I
    I --> M
    M --> U
~~~

Hình minh họa **phạm vi xác minh**, không khẳng định bốn tầng luôn phải dùng đúng bốn bộ framework khác nhau. Trong thực tế một integration test có thể bao phủ cả mapping, nhưng không nên thay thế test nghiệp vụ nhỏ, nhanh và cô lập.

### 1.1. Ma trận lớp kiểm thử

| Lớp | Thành phần thực sự chạy | Mock/fake có phù hợp? | Lỗi cần bắt |
| --- | --- | --- | --- |
| **Unit nghiệp vụ** | Domain object, chính sách, calculator | Có; đặc biệt với clock/ID generator hoặc port lưu trữ | Sai invariant, rounding, trạng thái, giới hạn |
| **Service unit** | Service + fake/mock repository port | Có, nếu đang kiểm tra orchestration | Lời gọi đúng, retry decision, mapping exception sang HTTP |
| **Mapping test** | Spring Data converter + SDK/Couchbase test | Mock không đủ để chứng minh JSON thật | Sai `@Field`, key/CAS, constructor, type hint, null/missing |
| **Repository/Template integration** | Spring context tối thiểu + Couchbase | Nên dùng database thật | Sai collection, query/index, scan consistency |
| **Concurrency/expiry/transaction** | Nhiều thao tác server có điều kiện | Không thay bằng mock để kết luận đúng | CAS lost update, TTL, transaction commit/rollback |
| **API/workflow integration** | HTTP controller, service, persistence, có thể thêm message broker | Fake cho hệ thống ngoài nếu không phải trọng tâm | Luồng end-to-end, authorization, lỗi kết nối, idempotency |
| **Load/resilience test** | Hạ tầng gần production | Mock không phản ánh server performance | p95/p99, index lag, throughput, failover, resource limits |

Một mock repository trả `Product` từ một `Map` chỉ chứng minh service dùng port ấy theo cách mong đợi; nó **không chứng minh** `ProductRepository.findById` sẽ đọc đúng `@Collection` hoặc SQL++ query sẽ thấy document mới ghi.

## 2. Một miền ví dụ xuyên suốt: Order nháp và giỏ hàng

Để tránh mỗi test dùng một loại document không liên quan, ta sử dụng **Order** trong bucket `shop`, scope `sales`, collection `orders`:

- Key: `order::125`.
- Có `customer_id`, `status`, danh sách `lines`, `total_amount_vnd`.
- `@Version` để kiểm tra CAS khi hai request sửa một Order.
- Line chứa `sku`, `unit_price_vnd`, `quantity`.
- Trạng thái `DRAFT`, `CONFIRMED`, `CANCELLED`.

Ví dụ JSON body được kỳ vọng sau lưu:

~~~json
{
  "_class": "com.example.shop.sales.Order",
  "customer_id": "customer::u100",
  "status": "DRAFT",
  "lines": [
    {
      "sku": "coffee250",
      "unit_price_vnd": 150000,
      "quantity": 2
    }
  ],
  "total_amount_vnd": 300000
}
~~~

`_class` có thể xuất hiện tùy type mapper, `order::125` là **document key nằm ngoài body**, còn CAS là **metadata server**. Không đưa ra giả định rằng body bắt buộc có `"id":"order::125"` hoặc `"version":42`.

### 2.1. Tách quy tắc miền khỏi persistence

Một `OrderLine` là value object có thể kiểm tra hoàn toàn bằng Java:

~~~java
package com.example.shop.sales;

import org.springframework.data.couchbase.core.mapping.Field;

public record OrderLine(
        String sku,
        @Field("unit_price_vnd") long unitPriceVnd,
        int quantity) {

    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU bắt buộc");
        }
        if (unitPriceVnd < 0 || quantity <= 0) {
            throw new IllegalArgumentException("Giá/số lượng không hợp lệ");
        }
    }

    public long amountVnd() {
        return Math.multiplyExact(unitPriceVnd, quantity);
    }
}
~~~

Một hàm nghiệp vụ độc lập với Couchbase:

~~~java
package com.example.shop.sales;

import java.util.List;

public final class OrderPolicy {
    private OrderPolicy() {}

    public static long totalVnd(List<OrderLine> lines) {
        if (lines == null || lines.isEmpty() || lines.size() > 50) {
            throw new IllegalArgumentException("Đơn cần từ 1 đến 50 dòng");
        }

        long total = 0;
        for (OrderLine line : lines) {
            if (line == null) {
                throw new IllegalArgumentException("Dòng hàng null");
            }
            total = Math.addExact(total, line.amountVnd());
        }
        return total;
    }
}
~~~

`Math.multiplyExact` và `Math.addExact` phát hiện tràn `long`. Trong hệ thống thanh toán thật, còn cần currency, rounding, thuế và chính sách giảm giá; ví dụ này tập trung vào test phân tầng.

`@Field("unit_price_vnd")` trên record component là chi tiết mapping cần được kiểm chứng ở tầng persistence: tên Java là `unitPriceVnd`, nhưng JSON minh họa sử dụng `unit_price_vnd`. Unit test tính tiền không phát hiện lỗi đặt tên field này.

## 3. Tầng 1 — Unit test nghiệp vụ: không Spring, không Couchbase

Ví dụ JUnit 5:

~~~java
package com.example.shop.sales;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class OrderPolicyTest {

    @Test
    void totalsTwoLines() {
        long total = OrderPolicy.totalVnd(List.of(
            new OrderLine("coffee250", 150000, 2),
            new OrderLine("cup01", 50000, 1)
        ));

        assertEquals(350000L, total);
    }

    @Test
    void refusesEmptyOrder() {
        assertThrows(IllegalArgumentException.class,
            () -> OrderPolicy.totalVnd(List.of()));
    }

    @Test
    void refusesInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
            () -> new OrderLine("coffee250", 150000, 0));
    }

    @Test
    void detectsArithmeticOverflow() {
        assertThrows(ArithmeticException.class,
            () -> OrderPolicy.totalVnd(List.of(
                new OrderLine("huge", Long.MAX_VALUE, 2)
            )));
    }
}
~~~

Unit test này không dùng `@SpringBootTest`, `@DataCouchbaseTest` hay Testcontainers. Lợi ích:

- Chạy rất nhanh và có lỗi gần vị trí logic sai.
- Không phụ thuộc port, index build, network hay container startup.
- Có thể chạy với hàng trăm/hàng nghìn tham số đầu vào.
- Có thể dùng **property-based test** để kiểm tra invariant “tổng luôn bằng tổng các dòng nếu không tràn” hoặc “không tồn tại line có quantity không dương”.

**Đây không phải bằng chứng ánh xạ Couchbase đúng.** Unit test trên không thể phát hiện `@Field("total_amout_vnd")` bị gõ sai hoặc repository trỏ nhầm scope.

### 3.1. Unit test service với fake repository

Nếu service phụ thuộc một cổng nghiệp vụ `OrderStore`, dùng fake để xác minh điều phối:

~~~java
public interface OrderStore {
    java.util.Optional<OrderDraft> findByKey(String key);
    OrderDraft save(OrderDraft order);
}

public record OrderDraft(
        String key, String customerId, List<OrderLine> lines) {

    public OrderDraft {
        lines = List.copyOf(lines);
    }

    public OrderDraft add(OrderLine line) {
        var next = new java.util.ArrayList<>(lines);
        next.add(line);
        return new OrderDraft(key, customerId, next);
    }
}
~~~

Fake in-memory:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

final class InMemoryOrderStore implements OrderStore {
    final Map<String, OrderDraft> values = new HashMap<>();

    @Override
    public Optional<OrderDraft> findByKey(String key) {
        return Optional.ofNullable(values.get(key));
    }

    @Override
    public OrderDraft save(OrderDraft order) {
        values.put(order.key(), order);
        return order;
    }
}
~~~

Có thể dùng fake để test service **có gọi save sau khi tạo bản sao**, nhưng không được tuyên bố fake này mô phỏng CAS, TTL, index hay transaction. Nếu cần chứng minh concurrency thật, chuyển xuống tầng integration.

### 3.2. Các phụ thuộc thời gian và ID phải điều khiển được

Thay vì gọi `Instant.now()` hoặc `UUID.randomUUID()` sâu trong policy, inject `Clock` hoặc `IdGenerator` khi muốn test các quy tắc thời gian/idempotency:

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-25T08:00:00Z"),
    ZoneOffset.UTC
);
Instant createdAt = fixed.instant();
~~~

Không dùng thời gian hệ thống để kiểm tra `createdAt` bằng so sánh `==` hoặc kỳ vọng chính xác đến mili-giây. Với TTL, thời gian thật và scheduler của server cần một kiểu integration test riêng.

## 4. Tầng 2 — Test ánh xạ entity/JSON: chạm converter và metadata thật

Test mapping cần bắt các lỗi unit thuần không thấy:

- `@Id` là **document key**, không tự trở thành field `id` trong JSON body.
- `@Field("customer_id")` ánh xạ tên Java `customerId`.
- Value object lồng nhau được serialize thành object/array đúng.
- `@Version` nhận CAS metadata và save với CAS cũ bị từ chối.
- Constructor/`@PersistenceCreator` hoặc record canonical constructor có thể dựng entity.
- Field MISSING, NULL, zero/false, enum, timestamp và dữ liệu lịch sử được giải mã đúng.
- `@TypeAlias` và type discriminator hoạt động nếu root/nested polymorphism cần thông tin loại.

Chỉ gọi:

~~~java
assertEquals(order.getCustomerId(), order.getCustomerId());
~~~

là vô nghĩa đối với mapping: không có serialization/deserialization diễn ra.

### 4.1. Entity mẫu cho bài kiểm thử

~~~java
package com.example.shop.sales;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Order {

    @Id
    private String id;

    @Version
    private Long cas;

    @Field("customer_id")
    private String customerId;

    @Field
    private String status;

    @Field
    private List<OrderLine> lines = new ArrayList<>();

    @Field("total_amount_vnd")
    private long totalAmountVnd;

    protected Order() {}

    public Order(String id, String customerId) {
        if (id == null || id.isBlank() ||
                customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        this.id = id;
        this.customerId = customerId;
        this.status = "DRAFT";
        this.lines = new ArrayList<>();
    }

    public void addLine(OrderLine line) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("Đơn không còn nháp");
        }
        if (line == null || lines.size() >= 50) {
            throw new IllegalArgumentException("Quá số dòng");
        }
        long extra = line.amountVnd();
        this.totalAmountVnd = Math.addExact(totalAmountVnd, extra);
        this.lines.add(line);
    }

    public String getId() { return id; }
    public Long getCas() { return cas; }
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public long getTotalAmountVnd() { return totalAmountVnd; }
    public List<OrderLine> getLines() { return List.copyOf(lines); }
}
~~~

Ví dụ sử dụng default scope/collection để đoạn test đơn giản và không phụ thuộc việc tạo keyspace tùy chỉnh. Trong dự án thật, gắn `@Scope("sales")`/`@Collection("orders")` rồi tạo đúng scope/collection trong fixture; **test trên default collection không chứng minh cấu hình named collection đã đúng**.

### 4.2. Test “save rồi findById” vẫn chưa đủ nếu không xem JSON body

~~~java
Order expected = new Order("order::test-001", "customer::u100");
expected.addLine(new OrderLine("coffee250", 150000, 2));

Order saved = orderRepository.save(expected);
Order actual = orderRepository.findById(saved.getId()).orElseThrow();

assertEquals("customer::u100", actual.getCustomerId());
assertEquals(300000L, actual.getTotalAmountVnd());
assertEquals(1, actual.getLines().size());
~~~

Đây là một kiểm tra round-trip tốt, nhưng để bắt trường hợp **cả writer và reader cùng sai tên field**, hãy dùng **SDK độc lập** đọc JSON body rồi đối chiếu:

~~~java
var sdkResult = cluster.bucket("testbucket")
    .defaultCollection()
    .get(actual.getId());

var body = sdkResult.contentAsObject();

assertEquals("customer::u100", body.getString("customer_id"));
assertEquals(300000L, body.getLong("total_amount_vnd"));
assertFalse(body.containsKey("id")); // Theo mapping @Id thông thường.
assertNotEquals(0L, sdkResult.cas());
~~~

Nếu ứng dụng chủ động cấu hình lưu ID vào body, điều kiện `containsKey("id")` cần đổi theo hợp đồng đó; test phải bám **cấu hình thực**, không bám một giả định ẩn.

### 4.3. Test đọc JSON viết từ nguồn khác

Một case quan trọng khác là **chèn JSON bằng SDK**, sau đó đọc bằng repository:

~~~java
var collection = cluster.bucket("testbucket").defaultCollection();

String key = "order::external-import";
collection.insert(key, JsonObject.create()
    .put("customer_id", "customer::u100")
    .put("status", "DRAFT")
    .put("total_amount_vnd", 0L)
    .put("lines", JsonArray.create())
);

Order imported = orderRepository.findById(key).orElseThrow();
assertEquals("customer::u100", imported.getCustomerId());
~~~

Cách này kiểm tra **reader có phụ thuộc field `_class` hay không**, và phát hiện dữ liệu do SDK thuần/legacy import không qua Spring Data. Nếu mapper có cấu hình buộc type hint hoặc subtype, phải chuẩn bị JSON/type alias đúng hoặc kỳ vọng lỗi có chủ đích.

## 5. Tầng 3 — Test persistence với Couchbase thật và Testcontainers

Một **test slice Spring Boot** không có nghĩa là database được giả lập. `@DataCouchbaseTest` chủ yếu tự cấu hình `CouchbaseTemplate`/`ReactiveCouchbaseTemplate`, repository và entity mapping, hạn chế các bean ngoài tầng data. Để repository thực hiện I/O, vẫn cần **Couchbase Server truy cập được**.

Kết hợp với **Testcontainers Couchbase** giúp:

- Tạo môi trường Couchbase cô lập, gần hành vi Server.
- Tránh phụ thuộc “database đang chạy trên laptop của lập trình viên”.
- Chạy đồng nhất trong CI có Docker/container runtime được cấp phép.
- Test được SQL++ query, index, CAS, TTL và các service KV/Query/Index thực.

Tài liệu hiện hành của Spring Boot có `@ServiceConnection` cho `CouchbaseContainer`; hãy kiểm tra version Spring Boot/Testcontainers vì package import và artifact Testcontainers có thay đổi giữa các major version.

### 5.1. Phụ thuộc test tối thiểu

Một project Java Spring Boot cần các nhóm dependency sau:

| Dependency | Dùng để |
| --- | --- |
| `spring-boot-starter-data-couchbase` | Entity mapping và repository |
| `spring-boot-starter-test` | JUnit 5, assertions và Spring testing |
| Spring Boot **Testcontainers support** | `@ServiceConnection` và connection details |
| Testcontainers Couchbase module | Khởi động Couchbase Server cô lập |
| Testcontainers JUnit Jupiter integration | Quản lý vòng đời `@Container` |

**Chú ý version:** Testcontainers Java 1.x thường dùng module Maven `org.testcontainers:couchbase` và `org.testcontainers:junit-jupiter`; các phiên bản 2.x tách artifact `testcontainers-couchbase`/`testcontainers-junit-jupiter`. Để tránh lỗi build, dùng **BOM cùng version** và tra đúng tọa độ phụ thuộc cho phiên bản đã chọn. Spring Boot 3.x và 4.x cũng có thay đổi ở package của `@DataCouchbaseTest`.

### 5.2. Ví dụ @DataCouchbaseTest + @ServiceConnection

Ví dụ sau minh họa đường Boot **3.x** với các import test-slice của Boot 3.x; khi dùng Boot 4.x, kiểm tra package/đầu vào test module hiện hành trước khi sao chép. Một số version Testcontainers có thể cần image/version khác được hỗ trợ.

~~~java
package com.example.shop.sales;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import com.couchbase.client.java.Cluster;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=testbucket")
@Testcontainers
class OrderRepositoryIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer couchbase =
        new CouchbaseContainer(
            DockerImageName.parse("couchbase/server:community-7.2.5"))
            .withEnabledServices(
                CouchbaseService.KV,
                CouchbaseService.QUERY,
                CouchbaseService.INDEX)
            .withBucket(new BucketDefinition("testbucket"));

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private Cluster cluster;

    @Test
    void savesAndReadsRealDocument() {
        String id = "order::it::" + UUID.randomUUID();

        try {
            Order order = new Order(id, "customer::u100");
            order.addLine(new OrderLine("coffee250", 150000, 2));

            Order saved = orderRepository.save(order);
            Order reloaded = orderRepository.findById(id).orElseThrow();

            assertEquals("customer::u100", reloaded.getCustomerId());
            assertEquals(300000L, reloaded.getTotalAmountVnd());
            assertEquals(1, reloaded.getLines().size());

            var raw = cluster.bucket("testbucket")
                .defaultCollection().get(id);

            assertEquals(
                "customer::u100",
                raw.contentAsObject().getString("customer_id"));
            assertEquals(
                300000L,
                raw.contentAsObject().getLong("total_amount_vnd"));
            assertNotEquals(0L, raw.cas());
        } finally {
            orderRepository.deleteById(id);
        }
    }
}
~~~

Repository cùng package (hoặc được scanner của test context phát hiện):

~~~java
package com.example.shop.sales;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository extends CouchbaseRepository<Order, String> {
}
~~~

Đây là **mẫu tích hợp**, cần cấu hình dependency và image tương thích với dự án, không phải cam kết một copy–paste chạy được trong mọi phiên bản. Với Boot 4.x, tài liệu Spring Boot dùng test module/package `org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest`; với Boot 3.x thường là `org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest`.

**Những điều test trên thật sự xác nhận:** Spring Data đã kết nối container, tìm key, ghi JSON, dựng lại entity và SDK đọc body/CAS đúng. Nó **chưa xác nhận** named scope, secondary index, transaction hay TTL nếu chưa thêm các test chuyên biệt.

### 5.3. Khi không dùng @ServiceConnection

Với Spring Boot cũ hoặc không dùng Boot Testcontainers support, có thể:

1. Khởi động `CouchbaseContainer` trước khi tạo Spring context.
2. Đưa **connection string, username, password và bucket name** vào các Spring properties bằng `@DynamicPropertySource` (hoặc cấu hình tương đương).
3. Giữ container static cho cả test class và tạo keyspace đúng.
4. Đừng hardcode `localhost:8091`, username/password từ máy phát triển.

Cấu hình property và cách tạo `Cluster` phải kiểm tra theo Boot version. `@ServiceConnection` giúp đơn giản hóa bước cấp Couchbase connection details, nhưng **không tự tạo mọi scope, collection, index nghiệp vụ**.

## 6. Chọn @DataCouchbaseTest hay @SpringBootTest?

| Nhu cầu | Chọn test |
| --- | --- |
| Chỉ repository, entity, converter, template | `@DataCouchbaseTest` |
| Service domain có thể cô lập bằng port | JUnit unit test với fake/mock |
| Service + repository + config + event publisher | `@SpringBootTest` hoặc test tích hợp có chọn bean rõ |
| HTTP controller, security filter, transaction, persistence | `@SpringBootTest` và HTTP testing phù hợp |
| Reactive repository riêng | `@DataCouchbaseTest` với reactive repository/template được hỗ trợ |
| End-to-end với broker/external API | Test workflow cấp cao, fake/mô phỏng nơi cần và container thật ở các dependency quan trọng |

`@DataCouchbaseTest` **không quét mọi `@Service` hoặc `@Component` bình thường**; nếu cần service cụ thể, dùng `@Import`, filters hoặc chuyển sang `@SpringBootTest`. Không nên vô tình viết test mong service được inject rồi chuyển cả bộ sang `@SpringBootTest` chỉ vì chưa hiểu phạm vi test slice.

Không áp mô hình JPA mặc định cho Couchbase: test dùng `@Transactional` hoặc giả định Spring rollback mọi thay đổi sau mỗi test **không tự nhiên mang nghĩa “rollback database về trạng thái ban đầu”**. Với Couchbase, phải xác minh transaction integration/version thực tế và chủ động cleanup/isolation.

## 7. Test keyspace: bucket, scope, collection và document key

Trong production, entity có thể dùng:

~~~java
@Document
@Scope("sales")
@Collection("orders")
public class Order { /* ... */ }
~~~

Kiểm thử phải tạo **bucket `shop` (hoặc bucket test tương ứng), scope `sales` và collection `orders`** trước khi repository chạy. Cùng document key `order::125` ở `_default._default` không phải document trong `sales.orders`.

Ma trận cần xác minh:

| Tình huống | Kỳ vọng |
| --- | --- |
| Key tồn tại ở đúng collection | `findById` đọc được |
| Key tồn tại ở collection khác | Repo đúng loại không tự tìm sang nơi khác |
| Key bị thiếu | `findById` trả `Optional.empty()` |
| Thiếu scope/collection | Test báo lỗi cấu hình rõ, không âm thầm chuyển sang default |
| User test không có quyền collection | Lỗi quyền truy cập, không phải “document không tồn tại” |
| Key trùng giữa hai collection | Vẫn là hai document khác nhau |
| JSON body có `id` khác key | `@Id` theo document key, không lấy body `id` thay thế |

**Khi dùng named collection**, có thể tạo keyspace bằng Couchbase management API/SDK hoặc SQL++ DDL được hỗ trợ, trước test. Dùng fixture setup idempotent và đợi service/index sẵn sàng; không chỉ sleep một khoảng cố định rồi hy vọng cluster đã khởi tạo.

## 8. Test KV khác test SQL++: vấn đề index consistency

Đọc theo key:

~~~java
Order found = orderRepository.findById(id).orElseThrow();
~~~

thường dùng **Key-Value**, không cần secondary index. Nhưng query theo thuộc tính:

~~~sql
SELECT META(o).id AS orderKey, o.customer_id, o.status
FROM `testbucket`.`_default`.`_default` AS o
WHERE o.customer_id = $customerId;
~~~

cần **index phù hợp**. Tạo index riêng cho test/query:

~~~sql
CREATE INDEX ix_orders_customer_status
ON `testbucket`.`_default`.`_default`(
    customer_id,
    status
);
~~~

Câu query này phải được chạy sau khi index đã sẵn sàng để sử dụng. **Không coi `CREATE INDEX` hoàn thành đồng nghĩa index đã online ở mọi phiên bản/kiểu triển khai**; kiểm tra index state, `EXPLAIN` hoặc cơ chế wait/poll có timeout.

### 8.1. Read-after-write và REQUEST_PLUS

Sau khi `save` một document, `findById(id)` có thể thấy nó qua KV trước khi SQL++ query theo `customer_id` thấy document. Lý do thường là **secondary index chưa cập nhật**, không phải `save` thất bại.

Couchbase Java SDK cho phép yêu cầu scan consistency:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;
import com.couchbase.client.java.json.JsonObject;

var result = cluster.query(
    """
    SELECT META(o).id AS orderKey
    FROM `testbucket`.`_default`.`_default` AS o
    WHERE o.customer_id = $customerId
    """,
    queryOptions()
        .parameters(JsonObject.create()
            .put("customerId", "customer::u100"))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);
~~~

- `NOT_BOUNDED` (mặc định trong nhiều SQL++ query) có thể dùng trạng thái index gần nhất và **chưa thấy mutation vừa ghi**.
- `REQUEST_PLUS` đợi index bắt kịp theo yêu cầu truy vấn, tăng độ tin cậy read-after-write nhưng có thể tăng latency.
- Có thể dùng **mutation tokens/consistentWith** theo SDK khi chỉ cần nhất quán với mutation đã biết; chọn tùy workload.

Trong test, **đừng thay `Thread.sleep(2000)` bằng `Thread.sleep(3000)` cho đến khi “hết flaky”**. Hãy xác định mức consistency cần kiểm tra và đợi index readiness với timeout có giới hạn.

### 8.2. Test repository query có type filter

Spring Data Couchbase có thể đưa **type metadata** vào câu SQL++ phát sinh cho repository. Nếu query chỉ lọc `customer_id` nhưng index không phù hợp với predicate/type key, kết quả hoặc hiệu năng có thể khác query SDK viết tay.

Với derived method:

~~~java
List<Order> findByCustomerId(String customerId);
~~~

cần xác nhận tên JSON thực là `customer_id`, cấu hình `_class`/type alias và query được phát sinh. Nếu query chạy thường xuyên, hãy dùng `EXPLAIN` và index được thiết kế cho predicate thực tế (kể cả sort/status), không chỉ test `findById`.

## 9. Tầng concurrency — CAS và optimistic locking

Một test CAS đúng phải có **hai snapshot độc lập từ cùng document**, không phải hai reference cùng trỏ một Java object.

Luồng kiểm thử:

~~~text
T0: INSERT Order -> CAS A
T1: Request 1 GET Order -> snapshot A1, CAS A
T2: Request 2 GET Order -> snapshot A2, CAS A
T3: Request 1 cập nhật và SAVE -> CAS B
T4: Request 2 SAVE dùng CAS A -> kỳ vọng conflict
~~~

Ví dụ JUnit:

~~~java
@Test
void rejectsStaleWriter() {
    String id = "order::cas::" + UUID.randomUUID();

    try {
        orderRepository.save(new Order(id, "customer::u100"));

        Order first = orderRepository.findById(id).orElseThrow();
        Order second = orderRepository.findById(id).orElseThrow();

        first.addLine(new OrderLine("coffee250", 150000, 1));
        orderRepository.save(first);

        second.addLine(new OrderLine("cup01", 50000, 1));

        assertThrows(
            org.springframework.dao.OptimisticLockingFailureException.class,
            () -> orderRepository.save(second)
        );
    } finally {
        orderRepository.deleteById(id);
    }
}
~~~

Test này có ý nghĩa khi entity thực sự dùng `@Version`/CAS và repository implementation phát hiện xung đột. Khi dùng SDK thuần, test thêm thao tác `replace` với CAS cũ và xác minh lỗi CAS mismatch tương ứng.

**Đừng viết test dựa vào giá trị CAS tăng 1**. CAS là token opaque, chỉ cần biết giá trị mới khác giá trị trước sau mutation.

### 9.1. Điều gì cần test thêm?

- Hai writer sửa **hai field khác nhau cùng document** cũng chia sẻ một CAS.
- Retry phải **đọc lại → tính lại quyết định nghiệp vụ → ghi lại**, không chỉ lặp `save(staleObject)`.
- Khi có side effect như gửi email/charge/payment, retry không được phát sinh thao tác trùng nếu chưa có idempotency.
- Một document `@Version` có thể được update bên ngoài qua SQL++; CAS cũng thay đổi và entity cũ trở nên stale.

Unit test fake có thể kiểm tra **chính sách retry**, nhưng phải có test server thật để chứng minh **CAS thực sự phát hiện conflict**.

## 10. Tầng TTL/expiry — đừng test bằng đồng hồ giả

Giả sử document Cart có TTL:

~~~java
@Document(expiry = 5)
public class EphemeralCart {
    @Id private String id;
    // ...
}
~~~

`expiry = 5` minh họa số giây theo cấu hình mặc định của annotation. Trong bài test thực tế, phải kiểm tra:

1. Ghi Cart bằng repository hoặc template với cấu hình TTL đúng.
2. Đọc ngay theo key và xác minh Cart tồn tại.
3. Poll cho đến khi Cart không còn đọc được trong khoảng thời gian tối đa hợp lý.
4. Kiểm tra việc đọc có chạm TTL (`touchOnRead`) hoặc thao tác cập nhật có làm mới expiry không.
5. Xác nhận TTL áp cho **cả document**, không cho từng phần tử lồng nhau.

Một phép test polling có timeout, với Awaitility nếu dự án có dependency:

~~~java
import static org.awaitility.Awaitility.await;
import static java.util.concurrent.TimeUnit.SECONDS;

await()
    .atMost(30, SECONDS)
    .pollInterval(1, SECONDS)
    .until(() -> cartRepository.findById(key).isEmpty());
~~~

Dùng key riêng cho test, đừng truy cập lại theo cách làm mới TTL vô tình. `Clock.fixed` hữu ích cho business time nhưng **không làm đồng hồ TTL của Couchbase Server chạy nhanh hơn**.

Lưu ý: TTL/expiry phụ thuộc phiên bản Spring Data, `@Document` options, collection/bucket maxTTL và mutation options. Test phải so sánh với **policy đang vận hành**, không dựa vào một thời điểm hết hạn cứng đến mili-giây.

## 11. Tầng transaction — kiểm tra bất biến nhiều document

Một nghiệp vụ giữ chỗ tồn kho có thể cần cập nhật cả `Order` và `Inventory`:

~~~mermaid
flowchart LR
    A["Reserve order"] --> B["Đọc Inventory"]
    B --> C["Giảm available stock"]
    C --> D["Đánh dấu Order RESERVED"]
    D --> E["Commit"]
    C -.-> F["Lỗi sau thay đổi tồn kho"]
    F --> G["Rollback / compensation"]
~~~

Test transaction phải chứng minh **cả hai cùng thành công hoặc không có trạng thái nửa vời** theo cơ chế đã chọn, không chỉ rằng service có gọi `save` hai lần.

Kịch bản:

- Chuẩn bị Order DRAFT và Inventory có 3 đơn vị.
- Gây lỗi được điều khiển ở một bước trước commit (không dùng sự cố ngẫu nhiên).
- Sau lỗi, đọc lại **cả hai document** bằng một quan sát phù hợp với cơ chế giao dịch.
- Xác minh Order không được xác nhận trong khi Inventory đã trừ — hoặc nếu hệ thống chọn **saga/compensation**, xác minh trạng thái bù và idempotency.
- Test đường commit thành công và trường hợp hai request cùng đặt chỗ vượt tồn kho.

**Không mặc định `@Transactional` trong một unit test Spring sẽ rollback mọi mutation Couchbase** như một số test JPA. Khả năng Spring-managed transactions phụ thuộc framework/configuration, SDK và service được dùng. Nếu ứng dụng dùng Couchbase Transactions SDK trực tiếp, test đúng API transaction đó; nếu dùng saga, test lại quy trình bù.

Một transaction đa document không phải giải pháp cho mọi query; lựa chọn dựa trên invariant và latency/throughput thực tế.

## 12. Tầng reactive — kiểm tra publisher được subscribe và hoàn tất

Với reactive repository:

~~~java
public interface ReactiveOrderRepository
        extends org.springframework.data.couchbase.repository
            .ReactiveCouchbaseRepository<Order, String> {
}
~~~

Test dùng Reactor `StepVerifier`:

~~~java
import reactor.test.StepVerifier;

String id = "order::rx::" + UUID.randomUUID();
Order newOrder = new Order(id, "customer::u100");

StepVerifier.create(
        reactiveOrderRepository.save(newOrder)
            .flatMap(saved ->
                reactiveOrderRepository.findById(saved.getId())))
    .assertNext(saved -> {
        assertEquals(id, saved.getId());
        assertEquals("customer::u100", saved.getCustomerId());
    })
    .verifyComplete();
~~~

Điểm quan trọng:

- `Mono`/`Flux` thường chỉ thực thi khi được **subscribe**; chỉ tạo publisher rồi không kiểm tra là test chưa chạy I/O.
- `StepVerifier` xác nhận terminal signal, số kết quả, thứ tự và lỗi mong đợi.
- Cleanup cũng phải thực sự được subscribe; gọi `repository.deleteById(id);` rồi bỏ publisher có thể không xóa gì.
- Đừng gọi `.block()` trong luồng production reactive; test có thể dùng StepVerifier hoặc block có timeout khi thực sự cần setup/cleanup.
- Reactor `VirtualTimeScheduler` không tua nhanh TTL thực của Couchbase Server hoặc thời gian xây dựng index.

Với test nhiều request cạnh tranh, sử dụng các luồng độc lập và synchronization barrier nếu muốn tái hiện race, nhưng tránh viết test kỳ vọng thứ tự scheduler cố định khi không có cơ chế điều khiển.

## 13. Test dữ liệu legacy, MISSING, NULL và polymorphism

Schema Couchbase linh hoạt khiến test mapping cần có fixture do **SDK chèn trực tiếp**, không chỉ JSON do entity mới serialize ra.

Ma trận mẫu:

| Fixture | JSON body | Điều cần kiểm tra |
| --- | --- | --- |
| Thiếu field mới | Không có `discount_percent` | Converter/reader legacy có xử lý theo version không? |
| Có `null` | `"discount_percent":null` | Không bị gộp nhầm với MISSING nếu miền cần phân biệt |
| Zero hợp lệ | `"discount_percent":0` | Không bị coi là chưa có dữ liệu |
| Sai kiểu | `"total_amount_vnd":"350000"` | Không âm thầm tính sai tiền |
| Enum không biết | `"status":"UNKNOWN_V9"` | Báo lỗi/migration có chủ đích |
| Field đổi tên | `"customerId"` thay `"customer_id"` | Reader cũ/mới tương thích theo kế hoạch |
| `_class` FQCN cũ | Tên Java class trước refactor | Type mapper/alias có đọc được không? |
| Nested subtype | `choice._class` thể hiện loại | Mapper dựng đúng concrete type |
| Thiếu type hint | JSON từ SDK không có `_class` | Đọc qua entity cụ thể/abstract type ra sao |
| Key trùng body.id khác | Document key khác JSON `id` | `@Id` vẫn theo key |
| Field lồng null/empty | `lines:[]`, `lines:null`, `lines` MISSING | Constructor/validation đúng |
| Timestamp đa dạng | ISO text hoặc format cũ | Converter có kế hoạch tương thích |

Không chỉ test “đọc được” mà cần test **đọc xong rồi ghi lại** có làm mất field, đổi type hint, biến MISSING thành NULL hoặc reset TTL ngoài ý định hay không.

### 13.1. Test round-trip chéo SDK và Spring Data

Có hai chiều:

1. **Spring Data ghi → SDK đọc:** kiểm tra tên field JSON thật, ID/CAS, nested array.
2. **SDK ghi → Spring Data đọc:** kiểm tra dữ liệu nhập/legacy không mang metadata tự động của framework.

Nếu chỉ dùng Spring Data ở cả hai chiều, writer và reader có thể cùng chia sẻ một lỗi mapping mà test không nhận ra.

## 14. Test hiệu năng không nên trộn với unit test

Một bài test 2 giây có thể PASS nhưng production có `p99` đọc chậm do document lớn hoặc index thiếu. Dùng một lớp **performance/resilience test** riêng:

- p50/p95/p99 `findById`, `save`, query theo filter/sort.
- Kích thước document, mảng tăng, index entries, heap/GC và network byte.
- Tải đồng thời trên cùng một hot key để đo CAS conflict/retry.
- Index build, rebalance/failover nếu kiến trúc cần kiểm chứng.
- Query `EXPLAIN` để xác nhận optimizer chọn index mong đợi.
- Timeout, retry budget, durability và backpressure với reactive.

Không dùng **một lần chạy Testcontainers trên laptop** làm benchmark để dự báo chắc chắn production. Cần môi trường test performance riêng, cấu hình gần production, dataset đại diện và tài nguyên có kiểm soát. Đặt ngưỡng theo SLO nghiệp vụ thay vì một con số “dưới 100 ms” không có căn cứ.

## 15. Isolation và cleanup: yếu tố làm test đáng tin

### 15.1. Dùng document key riêng

Mỗi test nên dùng key có namespace cố định và phần duy nhất:

~~~java
String key = "it::orders::" + UUID.randomUUID();
~~~

Không dùng `order::125` cố định trong nhiều test chạy song song rồi đổ lỗi cho Couchbase khi dữ liệu bị ghi đè. Dùng key sinh ở test giúp tránh va chạm; với test yêu cầu tính xác định, inject ID generator và kiểm soát riêng.

### 15.2. Cleanup theo key, không xóa cả collection dùng chung

~~~java
String key = "it::" + UUID.randomUUID();

try {
    // Thực hiện test với key này...
} finally {
    repository.deleteById(key);
}
~~~

Nếu môi trường có nhiều test chạy đồng thời, `deleteAll()` có thể xóa fixture của test khác. Với test TTL, có thể dùng collection/bucket riêng và để expiry dọn dữ liệu, nhưng vẫn phải có cơ chế đảm bảo môi trường test không tích lũy tài nguyên vô hạn.

Với reactive, cleanup phải là publisher được subscribe/verified:

~~~java
StepVerifier.create(reactiveOrderRepository.deleteById(key))
    .verifyComplete();
~~~

### 15.3. Những nguồn flaky phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| KV thấy document, query không thấy | Secondary index chưa bắt kịp | REQUEST_PLUS hoặc consistency phù hợp |
| Test query không chạy sau startup | Index chưa ONLINE hoặc Query Service chưa sẵn sàng | Wait/readiness có timeout |
| Test chạy riêng PASS, chạy chung FAIL | Trùng key, cleanup thiếu, shared static state | ID duy nhất, tách dataset, cleanup |
| Test TTL thỉnh thoảng FAIL | Kỳ vọng hết hạn đúng một thời điểm | Poll với timeout, kiểm tra touch/expiry |
| CAS test không fail như mong đợi | Hai reference không độc lập hoặc `@Version` sai | Đọc hai snapshot, kiểm tra CAS thật |
| Test “rollback” vẫn còn dữ liệu | Không có transaction thật hay cleanup | Test transaction đúng API; xóa fixture |
| Test reactive không chạy | Publisher chưa subscribe | StepVerifier/subscribe |
| Testcontainers khởi động chậm | Image pull, thiếu memory, thiếu service | Quản lý image/version, timeout, CI resources |
| Lỗi quyền sau khi tạo collection | RBAC/permission chưa đúng | Fixture tạo user/quyền test đúng |
| Query có kết quả khác nhau | Dataset/query consistency/ordering không xác định | ORDER BY có tie-breaker, consistency rõ |

## 16. CI pipeline: cho phản hồi nhanh nhưng vẫn có bằng chứng dữ liệu thật

Đề xuất chia jobs/stages:

~~~mermaid
flowchart LR
    C["Commit"] --> F["Format / static checks"]
    F --> U["Unit tests\nkhông database"]
    U --> M["Mapping + repository IT\nTestcontainers Couchbase"]
    M --> I["Query / CAS / TTL / transaction\nchọn lọc"]
    I --> P["Performance / resilience\nnightly hoặc pre-release"]
~~~

Phân tầng giúp:

- **PR nhỏ:** format, compile, unit và bộ mapping/repository IT thiết yếu.
- **PR có thay đổi entity/query/index:** chạy thêm migration fixtures, SQL++ `EXPLAIN`, CAS và TTL cần thiết.
- **Nightly/pre-release:** transaction fault injection, concurrency, load, upgrade compatibility, backup/restore nếu áp dụng.

Những điều CI cần đảm bảo:

1. Container runtime/Docker hoạt động và có tài nguyên cho Couchbase.
2. Image Couchbase được pin phiên bản rõ, phù hợp production và quy định license.
3. Test có timeout hữu hạn; không treo vô hạn khi thiếu Query Service.
4. Không dùng credential production; secret của CI được quản lý và không log ra stdout.
5. Test không truy cập cluster production hoặc dữ liệu khách hàng.
6. Thất bại do hạ tầng được phân loại riêng, **không âm thầm skip** test tích hợp quan trọng.
7. Báo cáo có phân tầng: unit, mapping, repository/SQL++, concurrency, contract.
8. Thử nghiệm upgrade Couchbase/Spring Data qua compatibility matrix trước khi đổi dependency.

**Không đánh dấu một PR “đã kiểm thử Couchbase” nếu job Testcontainers thực tế bị skip vì thiếu Docker.** Có thể thiết kế local profile cho phép skip, nhưng gate CI phải thể hiện rõ điều kiện hoàn thành.

## 17. Mẫu test plan cho một thay đổi entity thực tế

**Yêu cầu thay đổi:** Product trước đây có JSON `"name"`, phiên bản mới dùng `"display_name"`, bổ sung `"currency":"VND"`, và API cho phép cập nhật giá.

Viết test theo từng lớp:

| Lớp | Trường hợp |
| --- | --- |
| Domain unit | Giá không âm, currency được hỗ trợ, không chấp nhận update sai trạng thái |
| Service unit | Reader V1 fallback `name` có điều kiện, V2 thiếu currency bị từ chối |
| Mapping | `@Field("display_name")`, `@Id`, CAS, constructor/record materialize |
| SDK ↔ Spring Data | Raw V1 JSON đọc được theo reader chuyển tiếp, raw V2 đúng |
| Repository | FindById theo key, lưu và đọc lại field mới |
| SQL++ | Query theo `display_name` và index mới; không bỏ sót V1 trong giai đoạn migration |
| Concurrency | Hai người cùng đổi giá phát hiện CAS conflict |
| Migration | Batch idempotent, không sửa `currency:null`, giữ TTL |
| Rollback | Reader/writer V1 có chiến lược rõ khi gặp V2 |
| API contract | JSON response có `id` từ document key, không lộ `_class`/CAS |
| Performance | Query p95 đạt SLO sau index và migration |

### 17.1. Tại sao unit test fallback vẫn cần mapping test?

Giả sử unit test normalizer đọc raw JSON V1 và trả đúng tên. Nhưng Spring Data mapping trong repository vẫn chỉ biết `@Field("display_name")`; nếu service trong production đi thẳng qua repository thay vì normalizer, dữ liệu V1 có thể thành `null`.

**Test cần bám đúng đường code sẽ chạy**, không chỉ một helper logic “có vẻ đúng”. Mỗi lớp phải làm rõ đường đi:

~~~text
HTTP request
   -> Application service
      -> Repository/CouchbaseTemplate
         -> Mapping converter
            -> KV/SQL++/Server
~~~

Với một chức năng mới, ít nhất một test tích hợp cần chạy **toàn bộ đường quan trọng** từ service đến server trên fixture phù hợp.

## 18. Bài tập: thiết kế bộ kiểm thử cho giỏ hàng có TTL và CAS

Một hệ thống lưu `Cart` tại `shop.sales.carts`:

- `Cart` có key `cart::u100`, `@Version` và TTL 1 giờ.
- Danh sách `lines` giới hạn 30 phần tử.
- UI xem giỏ theo ID, màn hình quản trị tìm giỏ theo `customer_id`.
- Hai thiết bị có thể cùng chỉnh sửa một giỏ.
- Dữ liệu V1 có `lines` MISSING; V2 luôn lưu `lines:[]` hoặc array.
- Một số request dùng reactive repository.

**Yêu cầu:** chia các test sao cho mỗi lớp phát hiện đúng một nhóm lỗi, nêu điều kiện setup và cách tránh flaky.

### 18.1. Lời giải tham khảo

**Unit nghiệp vụ:**

- Không thêm quá 30 dòng.
- Quantity dương; không tràn tổng tiền.
- Khi thêm item đã có SKU, quy tắc gộp item rõ ràng.
- Đơn bị khóa không cho sửa.

**Mapping:**

- `@Id` lấy `cart::u100` làm document key.
- `@Version` nhận CAS.
- `lines:[]` ghi–đọc đúng; V1 MISSING được xử lý theo default nghiệp vụ đã chấp thuận.
- JSON `lines:null` và sai kiểu có kết quả **khác V1 MISSING** nếu hợp đồng yêu cầu.

**Repository/Query:**

- `findById` lấy đúng Cart theo KV.
- `findByCustomerId` chạy SQL++ trên `customer_id`, có index.
- Sau write, dùng consistency thích hợp để không đánh giá nhầm index lag.

**CAS và TTL:**

- Load hai Cart độc lập, update một Cart thành công, Cart thứ hai từ CAS cũ bị conflict.
- Test expiry bằng polling với timeout; xác nhận `touchOnRead` nếu có.
- Xác minh TTL không tự áp riêng cho từng `CartLine`.

**Reactive:**

- Test `save().flatMap(findById)` bằng StepVerifier.
- Cleanup thật sự được subscribe.
- Lỗi CAS được phát ra qua `onError`, không bị `onErrorResume` nuốt mất.

**CI/isolation:**

- Container Couchbase riêng, tạo `sales.carts` trước test.
- Key có UUID hoặc namespace test riêng; không dùng `deleteAll()` trong môi trường chạy song song.
- Phân biệt lỗi môi trường container/index chưa sẵn sàng với lỗi mapping thật.

### 18.2. Câu hỏi tự kiểm tra

1. **Unit test dùng mock repository có chứng minh SQL++ query đúng không?** Không.
2. **`@DataCouchbaseTest` có tự chạy một Couchbase Server giả không?** Không; vẫn cần kết nối tới server thật/test container.
3. **Vì sao nên đọc raw JSON bằng SDK sau khi repository save?** Để bắt lỗi ánh xạ mà writer và reader Spring Data có thể cùng che giấu.
4. **`findById` theo key có cần secondary index không?** Không.
5. **Sau save, SQL++ query không thấy record ngay có chắc là lỗi lưu không?** Không; có thể do secondary index chưa cập nhật.
6. **`REQUEST_PLUS` giúp gì và đánh đổi gì?** Chờ index bắt kịp, có thể tăng latency.
7. **CAS test cần hai snapshot riêng vì sao?** Để mô phỏng hai writer dựa trên cùng phiên bản cũ.
8. **Có thể dùng `Clock.fixed` tua nhanh TTL Couchbase không?** Không; TTL dùng thời gian của server.
9. **Reactive publisher không được subscribe có ghi dữ liệu không?** Không nên giả định; test phải subscribe/verify.
10. **Có nên mặc định mọi `@Transactional` test Couchbase được rollback như JPA?** Không; phải kiểm tra cơ chế giao dịch thực.
11. **Vì sao không gọi `deleteAll()` sau mỗi test?** Có thể xóa dữ liệu của test khác chạy song song.
12. **Tại sao chỉ test JSON V2 do chính entity mới ghi là chưa đủ?** Không kiểm tra khả năng đọc JSON lịch sử/SDK ngoài framework.

## 19. Checklist hoàn thiện chiến lược kiểm thử

- [ ] Phân loại các business invariants có thể test mà không cần Spring/database.
- [ ] Dùng fake/mock cho orchestration, nhưng không dùng làm bằng chứng SQL++/CAS/TTL.
- [ ] Có Testcontainers hoặc cluster test cô lập chạy Couchbase Server thực.
- [ ] Ghi rõ phiên bản Spring Boot/Testcontainers và gói `@DataCouchbaseTest` đang dùng.
- [ ] Test `@Id`, `@Field`, `@Version`, constructor, nested mapping và raw JSON.
- [ ] Test cả Spring Data → SDK lẫn SDK → Spring Data.
- [ ] Tạo đúng bucket/scope/collection, quyền truy cập và index trong fixture.
- [ ] Đối chiếu KV theo key với SQL++ theo thuộc tính; quản lý scan consistency.
- [ ] Có kiểm thử CAS conflict với hai snapshot độc lập.
- [ ] Test TTL bằng polling có timeout, không dựa vào thời gian giả hoặc sleep cứng.
- [ ] Kiểm tra transaction/compensation trên nhiều document bằng lỗi chủ động.
- [ ] Với reactive, xác nhận subscribe, completion, error và cleanup bằng StepVerifier.
- [ ] Có fixture legacy, MISSING, NULL, sai kiểu, alias cũ và payload lồng nhau.
- [ ] Đặt key duy nhất, cleanup theo key và giới hạn test song song.
- [ ] Không coi `@Transactional` test là cơ chế cleanup tự động khi chưa chứng minh.
- [ ] Đo `EXPLAIN`, p95/p99 và chi phí index trong pipeline chuyên biệt.
- [ ] CI báo rõ khi integration test bị skip hoặc container không khởi động.
- [ ] Không dùng cluster production, dữ liệu thật hoặc secret production trong test.

## Tài liệu tham khảo chính thức

- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@DataCouchbaseTest`, test slice và phạm vi auto-configuration.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection`, `CouchbaseConnectionDetails` và cách tích hợp container.
- [Testcontainers for Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): `CouchbaseContainer`, `BucketDefinition`, kết nối và dependency.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Id`, `@Field`, `@Version`, constructor và converter.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD theo key, query methods và repository mapping.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): đọc body JSON, key, CAS, mutation.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): `QueryOptions`, `REQUEST_PLUS` và query consistency.
- [Couchbase Java SDK — Sub-document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): mutate/lookup theo path và atomicity trong cùng document.
- [Couchbase Server — CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): secondary index và query plan.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/reference/): kiểm tra tín hiệu của reactive publisher.
