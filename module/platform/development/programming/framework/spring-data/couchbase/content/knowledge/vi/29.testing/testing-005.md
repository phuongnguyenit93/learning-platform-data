# Cung cấp cấu hình kết nối động và chờ cluster sẵn sàng trong kiểm thử Spring Data Couchbase

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao endpoint, cổng, username, password và bucket của Couchbase kiểm thử nên được cấp **động**, không hardcode.
2. Kết nối Spring Data Couchbase với `CouchbaseContainer` thông qua `@DynamicPropertySource` hoặc `@ServiceConnection`.
3. Phân biệt **Docker container started**, **Couchbase cluster ready**, **bucket/KV sockets ready**, **collection usable** và **secondary index ONLINE**.
4. Dùng `Cluster.waitUntilReady`, `Bucket.waitUntilReady`, `WaitUntilReadyOptions` và `watchIndexes` với timeout hữu hạn.
5. Viết integration test thực tế với repository, `CouchbaseTemplate`, SDK, JSON body, SQL++ và CAS.
6. Phân biệt lỗi readiness với **query scan consistency**, nhất là truy vấn vừa ghi qua secondary index.
7. Xử lý Spring context cache, vòng đời container, quyền truy cập, test isolation và CI để tránh test PASS giả hoặc flaky.

Bài thuộc chương **Kiểm thử** của module **SPRING_DATA_COUCHBASE**, xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; đồng thời quan tâm bucket/scope/collection, index, TTL, CAS, transaction và API reactive. Kết nối động là điều kiện nền tảng để những bài kiểm thử ngữ nghĩa dữ liệu này thật sự chạm đúng tài nguyên.

> **Hai việc khác nhau:** `@DynamicPropertySource` đưa **connection details hiện tại** vào Spring. `waitUntilReady` chờ **SDK/service bootstrap**. Không cơ chế nào tự provision named collection, tạo index hoặc đảm bảo SQL++ read-your-own-write.

## 1. Vấn đề: container chạy ở cổng không cố định

Testcontainers khởi chạy một Couchbase Server thật trong Docker. Docker có thể ánh xạ các cổng khác nhau ở mỗi lần test:

~~~text
Lần 1: Couchbase container -> host/mapped ports nhóm A
Lần 2: Couchbase container -> host/mapped ports nhóm B
CI:     Docker-in-Docker hoặc remote engine -> host khác
~~~

Nếu test dùng cấu hình cố định:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: Administrator
    password: password
  data:
    couchbase:
      bucket-name: shop
~~~

nó có thể nối vào một Couchbase cài trên laptop thay vì container, hoặc thất bại vì host/port không phù hợp. Nguy hiểm hơn, một bài test có lệnh xóa dữ liệu có thể trỏ nhầm vào tài nguyên không dành cho kiểm thử.

**Nguyên tắc:** endpoint và credential phải đến từ **cùng instance CouchbaseContainer** mà JUnit đã khởi động; bucket phải mang tên dành riêng cho test; scope/collection/index phải được provision rõ ràng.

~~~mermaid
flowchart LR
    T["JUnit 5 / Testcontainers"] --> C["CouchbaseContainer"]
    C --> V["Connection string, username, password"]
    V --> D["@DynamicPropertySource"]
    D --> E["Spring Environment"]
    E --> S["Spring Data Couchbase / SDK"]
    S --> K["Bucket / Scope / Collection"]
    K --> R["Repository, Template, Query"]
~~~

### 1.1. Lấy kết nối từ container thay vì đoán cổng

~~~java
String connectionString = couchbase.getConnectionString();
String username = couchbase.getUsername();
String password = couchbase.getPassword();
~~~

`getConnectionString` thể hiện endpoint mà Testcontainers cho SDK sử dụng, kể cả port mapping cần thiết. Không tự ghép `localhost:8091`: cổng 8091 thường dành cho management API/UI, không thay thế connection string do module Testcontainers cung cấp.

Không in password hoặc credential ra CI logs. Khi cần debug, ghi loại server, tên bucket test và lỗi kết nối sau khi loại thông tin nhạy cảm.

## 2. Năm mức readiness cần kiểm tra

~~~mermaid
flowchart TB
    A["Docker process chạy"] --> B["Couchbase cluster initialized"]
    B --> C["SDK Cluster bootstrap ready"]
    C --> D["Bucket / KV sockets ready"]
    D --> E["Scope + Collection usable"]
    E --> F["Query Service ready"]
    F --> G["Index ONLINE"]
    G --> H["SQL++ visibility theo consistency đã chọn"]
~~~

Sơ đồ là **các điều kiện kiểm tra**, không phải một chuỗi nội bộ tuần tự tuyệt đối. Query Service có thể khởi động song song với KV, còn index có thể được build sau khi SDK đã kết nối.

| Mốc | Nó chứng minh | Nó chưa chứng minh |
| --- | --- | --- |
| `container.isRunning()` | Docker process đang chạy | Couchbase Server đã phục vụ KV/Query |
| `CouchbaseContainer.start()` hoàn thành | Module Testcontainers hoàn tất startup/wait strategy | Index custom ONLINE |
| `Cluster.connect(...)` trả về | Đã tạo đối tượng SDK Cluster | Tất cả socket bootstrap xong |
| `cluster.waitUntilReady` thành công | Các service được chọn đạt trạng thái mong đợi | Collection/index nghiệp vụ đã tạo |
| `bucket.waitUntilReady` thành công | Bucket và KV sockets đủ sẵn sàng | SQL++ có secondary index |
| `collection.exists(probeKey)` hoàn thành | Có thể liên lạc collection bằng KV | Index vừa ghi đã bắt kịp |
| `watchIndexes` thành công | Index chỉ định ONLINE | Query mặc định chắc chắn đọc ngay mutation vừa ghi |
| `REQUEST_PLUS` query trả về | Query chờ index theo mức scan consistency đã yêu cầu | Mọi query của app mặc định có mức consistency giống vậy |

Một test KV `findById` PASS không tự chứng minh Query/Index Service sẵn sàng. Ngược lại, `cluster.waitUntilReady` PASS không tự bảo đảm repository đang dùng đúng bucket/scope/collection.

## 3. Chọn đúng phiên bản thư viện

Ví dụ chính dùng **Java 17+, Spring Boot 3.5.x và Testcontainers 1.x**; với Spring Boot 4.x/Testcontainers 2.x, xem bảng chuyển đổi.

| Thành phần | Boot 3.x / Testcontainers 1.x | Boot 4.x / Testcontainers 2.x |
| --- | --- | --- |
| Data starter | `spring-boot-starter-data-couchbase` | Cùng nhóm starter |
| Boot test dependency | `spring-boot-starter-test` | `spring-boot-starter-data-couchbase-test` hoặc module tương ứng |
| Boot Testcontainers | `spring-boot-testcontainers` | `spring-boot-testcontainers` |
| Testcontainers Couchbase | `org.testcontainers:couchbase` | `org.testcontainers:testcontainers-couchbase` |
| Testcontainers JUnit | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| `@DataCouchbaseTest` import | `org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest` | `org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest` |
| `@DynamicPropertySource` | `org.springframework.test.context.DynamicPropertySource` | Tương tự |

### 3.1. Gradle dependencies mẫu cho Boot 3.5 / Testcontainers 1.x

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:couchbase'
    testImplementation 'org.testcontainers:junit-jupiter'

    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Với Testcontainers 2.x, thay hai artifact theo bảng. Dùng BOM phù hợp và **đồng nhất phiên bản các module Testcontainers**, không trộn 1.x với 2.x. Chọn Couchbase Server image đã pin phiên bản tương thích dự án:

~~~java
DockerImageName image =
    DockerImageName.parse("couchbase/server:community-7.2.5");
~~~

`community-7.2.5` chỉ là **tag minh họa cố định**, không phải khuyến nghị mọi hệ thống nên dùng phiên bản đó. Test nâng cấp phải chọn các tag trong compatibility matrix SDK/Server thực tế.

## 4. Khởi tạo CouchbaseContainer với bucket và dịch vụ đúng

~~~java
import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.utility.DockerImageName;

CouchbaseContainer couchbase = new CouchbaseContainer(
    DockerImageName.parse("couchbase/server:community-7.2.5"))
    .withEnabledServices(
        CouchbaseService.KV,
        CouchbaseService.QUERY,
        CouchbaseService.INDEX)
    .withBucket(new BucketDefinition("shop_it"));
~~~

`BucketDefinition("shop_it")` tạo bucket test. Nó **không tạo scope `sales`, collection `orders` hoặc index `ix_orders_customer`**.

| Test cần làm | KV | QUERY | INDEX |
| --- | :---: | :---: | :---: |
| `get/insert/upsert` theo key | Có | Không nhất thiết | Không nhất thiết |
| Repository `save/findById` | Có | Không nhất thiết | Không nhất thiết |
| SQL++ lọc theo thuộc tính | Có | Có | Có |
| `CREATE INDEX` / `EXPLAIN` | Tùy thao tác | Có | Có |
| CAS write conflict | Có | Không nhất thiết | Không nhất thiết |
| TTL/expiry | Có | Không nhất thiết | Không nhất thiết |

Chỉ bật những dịch vụ test dùng, nhưng đừng vô tình bỏ Query hoặc Index khi bài test có repository derived query. Couchbase cần CPU/RAM và thời gian khởi động đủ cho services đã chọn; startup timeout không phải lúc nào cũng do code Spring Data.

### 4.1. JUnit 5 quản lý container lifecycle

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class CouchbaseSmokeIT {
    @Container
    static final CouchbaseContainer COUCHBASE =
        new CouchbaseContainer(
            DockerImageName.parse("couchbase/server:community-7.2.5"))
            .withBucket(new BucketDefinition("shop_it"));

    @Test
    void example() {
        org.junit.jupiter.api.Assertions.assertTrue(COUCHBASE.isRunning());
    }
}
~~~

`static @Container` thường được JUnit Jupiter Testcontainers extension khởi động một lần cho class và dừng khi class kết thúc. Instance `@Container` có vòng đời theo test method, tốn chi phí Couchbase bootstrap lớn hơn.

`assertTrue(isRunning())` chỉ là smoke check ở Docker layer; **chưa phải integration test persistence**. Phải làm thêm KV/query assertion nếu muốn khẳng định Spring Data/Couchbase thực sự hoạt động.

## 5. DynamicPropertySource cung cấp các giá trị nào?

Spring Boot 3.x sử dụng các properties:

| Property | Supplier |
| --- | --- |
| `spring.couchbase.connection-string` | `COUCHBASE::getConnectionString` |
| `spring.couchbase.username` | `COUCHBASE::getUsername` |
| `spring.couchbase.password` | `COUCHBASE::getPassword` |
| `spring.data.couchbase.bucket-name` | `() -> "shop_it"` |

Đây là **tên Spring Boot properties**, không phải tên biến môi trường Docker. App có custom `AbstractCouchbaseConfiguration` hoặc nhiều `Cluster` beans cần được kiểm tra riêng vì không chắc sẽ dùng đúng auto-configuration này.

### 5.1. Phương thức static và lazy Supplier

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void couchbaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.couchbase.connection-string",
        COUCHBASE::getConnectionString);
    registry.add("spring.couchbase.username",
        COUCHBASE::getUsername);
    registry.add("spring.couchbase.password",
        COUCHBASE::getPassword);
    registry.add("spring.data.couchbase.bucket-name",
        () -> "shop_it");
}
~~~

Spring TestContext yêu cầu method `static` với **một tham số `DynamicPropertyRegistry`**. `registry.add` nhận `Supplier`; supplier được đánh giá khi property cần được resolve. Nhờ đó Spring không cần đoán địa chỉ container từ trước khi Docker cấp mapped ports.

`@DynamicPropertySource` chỉ đăng ký properties. Nó **không tự khởi động container**. Cần `@Testcontainers`/`@Container` hoặc một fixture quản lý `start()` trước thời điểm Spring dùng các properties.

### 5.2. Tại sao không chỉ khai báo @TestPropertySource?

`@TestPropertySource` hữu ích với một giá trị cố định như bật/tắt feature hoặc tên profile, nhưng không biết mapped port sẽ được Docker cấp. `@DynamicPropertySource` có **độ ưu tiên cao hơn các property sources thông thường**, gồm `@TestPropertySource`, environment và Java system properties.

Do đó, property dynamic **sai key** có thể khiến Spring dùng endpoint mặc định, còn property dynamic **đúng key** thường thắng config tĩnh. Phải kiểm tra chắc test kết nối đúng container thay vì chỉ dựa vào việc Spring context đã start.

## 6. Entity mẫu để xác minh kết nối thực

Ứng dụng bán hàng dùng Order trong bucket test `shop_it`, mặc định `_default._default` ở ví dụ đầu.

~~~java
package com.example.shop.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Order {
    @Id private String id;
    @Version private Long cas;

    @Field("customer_id")
    private String customerId;

    @Field("total_amount_vnd")
    private long totalAmountVnd;

    @Field
    private String status;

    protected Order() {}

    public Order(String id, String customerId, long amount) {
        if (id == null || id.isBlank()
                || customerId == null || customerId.isBlank()
                || amount < 0) {
            throw new IllegalArgumentException("Order không hợp lệ");
        }
        this.id = id;
        this.customerId = customerId;
        this.totalAmountVnd = amount;
        this.status = "DRAFT";
    }

    public String getId() { return id; }
    public Long getCas() { return cas; }
    public String getCustomerId() { return customerId; }
    public long getTotalAmountVnd() { return totalAmountVnd; }

    public void addAmount(long amount) {
        if (!"DRAFT".equals(status) || amount <= 0) {
            throw new IllegalStateException("Không thể sửa Order");
        }
        totalAmountVnd = Math.addExact(totalAmountVnd, amount);
    }
}
~~~

~~~java
package com.example.shop.sales;

import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<Order, String> {

    // Derived query này sử dụng SQL++ theo field customer_id.
    List<Order> findByCustomerId(String customerId);
}
~~~

`@Id` là document key, `@Version` là CAS metadata, `@Field` định nghĩa JSON field names. Không suy rằng JSON body phải chứa `"id"` hay `"cas"`.

## 7. Integration test hoàn chỉnh: dynamic endpoint → ready bucket → JSON

Mã dưới đây áp dụng cho **Spring Boot 3.5.x/Testcontainers 1.x**. Với Boot 4.x thay import test slice và dependency theo bảng.

~~~java
package com.example.shop.sales;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.UUID;

import com.couchbase.client.java.Cluster;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataCouchbaseTest
@Testcontainers
class OrderConnectionIT {

    @Container
    static final CouchbaseContainer COUCHBASE =
        new CouchbaseContainer(DockerImageName.parse(
            "couchbase/server:community-7.2.5"))
            .withEnabledServices(
                CouchbaseService.KV,
                CouchbaseService.QUERY,
                CouchbaseService.INDEX)
            .withBucket(new BucketDefinition("shop_it"));

    @DynamicPropertySource
    static void register(DynamicPropertyRegistry registry) {
        registry.add("spring.couchbase.connection-string",
            COUCHBASE::getConnectionString);
        registry.add("spring.couchbase.username",
            COUCHBASE::getUsername);
        registry.add("spring.couchbase.password",
            COUCHBASE::getPassword);
        registry.add("spring.data.couchbase.bucket-name",
            () -> "shop_it");
    }

    @Autowired private Cluster cluster;
    @Autowired private OrderRepository orders;

    @Test
    void waitsThenReadsActualJson() {
        cluster.waitUntilReady(Duration.ofSeconds(60));
        cluster.bucket("shop_it")
            .waitUntilReady(Duration.ofSeconds(60));

        String key = "it::order::" + UUID.randomUUID();

        try {
            orders.save(new Order(key, "customer::u100", 350000));

            Order mapped = orders.findById(key).orElseThrow();
            assertEquals("customer::u100", mapped.getCustomerId());
            assertEquals(350000L, mapped.getTotalAmountVnd());

            var result = cluster.bucket("shop_it")
                .defaultCollection().get(key);
            var body = result.contentAsObject();

            assertEquals("customer::u100",
                body.getString("customer_id"));
            assertEquals(350000L,
                body.getLong("total_amount_vnd"));
            assertFalse(body.containsKey("id"));
            assertNotEquals(0L, result.cas());
        } finally {
            orders.deleteById(key);
        }
    }
}
~~~

Test này chứng minh **một đường KV thực**: Spring đã nhận connection details, entity được ghi/đọc và SDK thấy đúng raw JSON cùng CAS. Đây không phải unit test/mock.

Nó **chưa chứng minh** named collection `sales.orders`, secondary index, transaction hay TTL; những trường hợp ấy cần test bổ sung.

### 7.1. Vì sao dùng Cluster bean của Spring?

`@Autowired Cluster cluster` lấy bean Spring Boot đã cấu hình từ dynamic properties. Nếu bạn tự `Cluster.connect` với một URL khác, test có thể vô tình dùng **hai cluster khác nhau** mà không phát hiện.

Không tự gọi `disconnect()` trên Cluster do Spring sở hữu; Spring context sẽ quản lý vòng đời bean. Chỉ disconnect Cluster mà fixture tự tạo và sở hữu.

## 8. @ServiceConnection: lựa chọn thay thế gọn hơn

Nếu dự án dùng `spring-boot-testcontainers` và Spring Boot có `CouchbaseConnectionDetails`, có thể bỏ method `@DynamicPropertySource` cho endpoint/credential:

~~~java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=shop_it")
@Testcontainers
class OrderServiceConnectionIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer COUCHBASE =
        new CouchbaseContainer(DockerImageName.parse(
            "couchbase/server:community-7.2.5"))
            .withBucket(new BucketDefinition("shop_it"));

    // @Autowired Cluster / OrderRepository / các @Test thực.
}
~~~

Spring Boot nhận diện container type và tạo **connection details** cho Couchbase auto-configuration. Các details này có ưu tiên so với cấu hình kết nối thông thường.

| Điểm so sánh | `@DynamicPropertySource` | `@ServiceConnection` |
| --- | --- | --- |
| Cơ chế | TestContext nhận `Supplier` | Boot tạo `ConnectionDetails` |
| Endpoint và credential | Đăng ký từng property | Nhận diện `CouchbaseContainer` |
| Bucket name | Cấu hình riêng | Vẫn phải cấu hình riêng |
| Named scope/collection | Phải provision | Phải provision |
| Secondary index | Phải tạo/chờ | Phải tạo/chờ |
| Tùy biến nhiều Cluster beans | Tường minh hơn | Có thể cần custom bean |
| Phù hợp | Muốn kiểm soát property values | Boot auto-configuration chuẩn |

**Không cần bật cả hai** cho cùng connection string/credentials. Khi có hai nguồn, test khó giải thích vì sao auto-configuration dùng địa chỉ này thay vì địa chỉ kia.

### 8.1. Spring Boot 4.x

Đối với Boot 4.x, import test slice thay đổi:

~~~java
import org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest;
~~~

Testcontainers 2.x dùng artifact `testcontainers-couchbase` và `testcontainers-junit-jupiter`. Ý nghĩa `@ServiceConnection` vẫn là cấp endpoint/credential, **không bao gồm provisioning business schema**.

## 9. Cluster.waitUntilReady và Bucket.waitUntilReady

Couchbase Java SDK bootstrap **lazily**. `Cluster.connect` tạo object nhưng một số kết nối đang được mở trong nền. API readiness giúp chủ động đợi trước khi thao tác đầu tiên.

~~~java
import java.time.Duration;

cluster.waitUntilReady(Duration.ofSeconds(60));

var bucket = cluster.bucket("shop_it");
bucket.waitUntilReady(Duration.ofSeconds(60));
~~~

Theo tài liệu Couchbase Java SDK, **Bucket-level wait bổ sung việc đợi KV data sockets**, ngoài các kiểm tra readiness tương ứng ở Cluster-level. Cả hai đều có timeout.

### 9.1. Khi nào cần WaitUntilReadyOptions?

~~~java
import java.time.Duration;
import com.couchbase.client.core.service.ServiceType;
import static com.couchbase.client.java.diagnostics.WaitUntilReadyOptions.waitUntilReadyOptions;

cluster.waitUntilReady(
    Duration.ofSeconds(60),
    waitUntilReadyOptions().serviceTypes(ServiceType.QUERY)
);
~~~

`serviceTypes(...)` cho phép chọn những service cần đợi. Nếu suite chỉ dùng KV, `bucket.waitUntilReady` là trọng tâm; nếu cần SQL++, phải bảo đảm Query Service đã bật và có thể phục vụ request.

**Không yêu cầu `ServiceType.QUERY` khi container chỉ bật KV rồi cho rằng đó là lỗi Spring Data.** Test phải provision đúng service trước.

Khi không truyền `serviceTypes`, SDK có quy tắc mặc định riêng về các service khả dụng; chi tiết cần kiểm tra theo SDK version. Hãy chỉ định tường minh khi độ sẵn sàng của một service là yêu cầu test.

### 9.2. waitUntilReady không thay thế ping hoặc test KV

~~~java
var ping = cluster.ping();
System.out.println(ping);
~~~

`ping` chủ động thử kết nối với service ở tầng ứng dụng; `diagnostics` chủ yếu lấy thông tin trạng thái từ SDK. `waitUntilReady` phục vụ bootstrap với timeout. **Không dùng một kết quả ping duy nhất để kết luận JSON mapping, collection hay index đúng.**

| API | Mục đích |
| --- | --- |
| `Cluster.connect` | Tạo object SDK và bắt đầu bootstrap |
| `cluster.waitUntilReady` | Đợi service cluster đạt desired state |
| `bucket.waitUntilReady` | Đợi bucket/KV readiness |
| `cluster.ping` | Kiểm tra active service reachability |
| `cluster.diagnostics` | Quan sát trạng thái SDK |
| `collection.get/exists` | Kiểm chứng đường KV tới keyspace |
| `queryIndexes().watchIndexes` | Chờ secondary index ONLINE |

Không nên xem `ClusterState`/CAS/token là các số đơn giản có thể tự suy ra từ Java object.

## 10. Named scope/collection: tài nguyên nghiệp vụ cần provision riêng

Giả sử Order production ở `shop.sales.orders`, còn test dùng `shop_it.sales.orders`.

Entity phải bổ sung:

~~~java
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("sales")
@Collection("orders")
public class Order {
    // Các property như mục 6.
}
~~~

`withBucket(new BucketDefinition("shop_it"))` không tự tạo `sales` và `orders`. Có thể tạo bằng SDK management:

~~~java
import com.couchbase.client.java.manager.collection.CollectionSpec;
import com.couchbase.client.core.error.ScopeExistsException;
import com.couchbase.client.core.error.CollectionExistsException;

var manager = cluster.bucket("shop_it").collections();

try {
    manager.createScope("sales");
} catch (ScopeExistsException alreadyExists) {
    // Có thể setup lại mà không làm mất dữ liệu.
}

try {
    manager.createCollection(
        CollectionSpec.create("orders", "sales"));
} catch (CollectionExistsException alreadyExists) {
    // Collection đã tồn tại.
}
~~~

Các overload quản lý collection khác nhau tùy Java SDK version; `CollectionSpec` là một cách thể hiện phù hợp tài liệu SDK. **Không nuốt mọi exception**, nhất là lỗi quyền, sai bucket hoặc network.

### 10.1. Chờ collection có thể nhận KV

Tạo collection thành công vẫn có thể cần thời gian để manifest được các phần của hệ thống cập nhật. Hãy **poll một thao tác an toàn** tới khi thành công hoặc timeout:

~~~java
import java.time.Duration;
import java.time.Instant;

var coll = cluster.bucket("shop_it")
    .scope("sales").collection("orders");

Instant deadline = Instant.now().plus(Duration.ofSeconds(30));

while (true) {
    try {
        coll.exists("it::readiness::probe"); // Key có thể không tồn tại.
        break; // Request tới collection đã thành công.
    } catch (com.couchbase.client.core.error.CollectionNotFoundException ex) {
        if (Instant.now().isAfter(deadline)) {
            throw new IllegalStateException(
                "Collection chưa sẵn sàng", ex);
        }

        try {
            Thread.sleep(200); // Khoảng cách giữa các lần probe.
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Đã bị ngắt khi chờ collection", interrupted);
        }
    }
}
~~~

Điểm mấu chốt là **mỗi lần đều kiểm tra điều kiện thật và có deadline**. Nó không giống `Thread.sleep(5000)` xong coi như resource sẵn sàng.

Trong code dự án, có thể dùng Awaitility/retry helper, đồng thời chỉ retry đúng lỗi được xác nhận là tạm thời. Nếu nhận Authentication Failure hoặc không có quyền tạo collection, phải **fail fast**.

### 10.2. Thời điểm provisioning so với khởi tạo Spring context

`@DataCouchbaseTest` thường load Spring context trước khi chạy test method. Nếu bean khởi tạo có truy cập collection ngay ở startup, provisioning tại `@BeforeAll` **có thể quá muộn**.

Các lựa chọn:

- Provision resource trong một fixture chạy trước khi bean cần nó.
- Dùng `@BeforeAll` nếu các bean chỉ truy cập collection sau startup.
- Tách container bootstrap/setup schema và application context một cách có chủ đích.
- Dùng test initializer/configuration đúng lifecycle khi project phức tạp.

**Không mặc định mọi `@BeforeAll` luôn chạy trước giai đoạn Spring bean initialization**. Hãy kiểm tra đường code thật của dự án.

## 11. Index ONLINE là mốc khác với Query Service ready

Một derived query:

~~~java
List<Order> findByCustomerId(String customerId);
~~~

thường dùng SQL++ theo field `customer_id`. Nó có thể cần index phù hợp:

~~~sql
CREATE INDEX ix_orders_customer
ON `shop_it`.`sales`.`orders`(customer_id);
~~~

`cluster.waitUntilReady` thành công không nói rằng `ix_orders_customer` đã tồn tại hay đã ONLINE. Đợi index bằng QueryIndexManager:

~~~java
import java.time.Duration;
import java.util.List;
import static com.couchbase.client.java.manager.query.WatchQueryIndexesOptions.watchQueryIndexesOptions;

cluster.queryIndexes().watchIndexes(
    "shop_it",
    List.of("ix_orders_customer"),
    Duration.ofSeconds(90),
    watchQueryIndexesOptions()
        .scopeName("sales")
        .collectionName("orders")
);
~~~

`watchIndexes` **chỉ theo dõi index đã được tạo**; nó không tự chạy `CREATE INDEX`. Nếu index build thất bại, timeout phải làm setup/test FAIL kèm nguyên nhân.

Một primary index tạm để “cho query chạy” có thể che việc thiếu secondary index mà production thật sự cần. Nên dùng `EXPLAIN` để xác minh optimizer có thể tận dụng index ứng viên với query của Spring Data (có thể kèm type predicate).

### 11.1. Đừng nhầm Query readiness với index consistency

Couchbase KV có thể đọc document mới ngay sau khi save, trong khi SQL++ dùng secondary index có thể chưa thấy mutation đó ở chế độ scan consistency mặc định.

Ví dụ SDK kiểm chứng read-after-write:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryScanConsistency;

var rows = cluster.query(
    """
    SELECT META(o).id AS docKey
    FROM `shop_it`.`sales`.`orders` AS o
    WHERE o.customer_id = $customerId
    """,
    queryOptions()
        .parameters(JsonObject.create()
            .put("customerId", "customer::u100"))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
).rowsAsObject();
~~~

`REQUEST_PLUS` đợi index bắt kịp theo yêu cầu query, nhưng đổi lại có thể tăng latency. Nó **không tạo index** và không thể biến một Query Service đang tắt thành sẵn sàng.

Nếu test muốn chứng minh repository derived method chạy, phải gọi **chính method đó** với configuration/consistency phù hợp, không chỉ chạy query SDK rồi suy rằng mọi đường khác cũng đúng.

## 12. Spring TestContext cache và container lifecycle

Spring TestContext cache `ApplicationContext` giữa những test có cấu hình tương đương. JUnit Testcontainers extension lại có thể stop container `static @Container` sau mỗi test class.

Tình huống có rủi ro:

~~~text
Class A:
  Container A -> port A
  Spring context C -> connection details port A
  A PASS, JUnit stop container A

Class B:
  Container B -> port B
  Spring có thể reuse context C nếu cache key tương đương
  C vẫn giữ SDK bean trỏ port A -> B FAIL
~~~

Tình huống này phụ thuộc context configuration thực tế; không phải mọi suite đều gặp. Khi nhiều test classes có `@DynamicPropertySource` ở **base class** nhưng nguồn động thay đổi giữa subclass, Spring TestContext docs khuyến nghị xem xét `@DirtiesContext` để tránh reuse sai.

### 12.1. Phương án vòng đời phù hợp

1. Chia sẻ container **với cùng vòng đời context** cho nhiều test classes, có owner rõ.
2. Nếu mỗi class dùng container riêng, giữ context isolation tương ứng.
3. Dùng `@DirtiesContext` chọn lọc khi cần context mới; không dùng đại trà làm suite rất chậm.
4. Không stop thủ công container đã do Jupiter extension quản lý.
5. Không bật Testcontainers reuse trên CI mặc định nếu không xử lý dữ liệu/trạng thái cũ.
6. Dùng UUID/prefix riêng cho fixture thay vì `deleteAll` trên collection chung.

### 12.2. Property supplier không làm bean tự cấu hình lại

~~~java
static String currentBucket;

@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.couchbase.bucket-name",
        () -> currentBucket);
}
~~~

Thay `currentBucket` giữa các test không bảo đảm bean `CouchbaseTemplate` hoặc repository đã tạo sẽ tự động chuyển bucket. Giá trị dynamic được đọc vào quá trình cấu hình bean; nó không phải cơ chế hot-reload toàn Spring context.

Muốn test nhiều buckets/contexts, cần cấu hình test riêng hoặc API override có chủ đích, không chỉ thay static field.

## 13. Các lỗi thường gặp và cách phân loại

| Triệu chứng | Tầng hỏng có thể có | Xử lý |
| --- | --- | --- |
| Không tìm thấy Docker | Testcontainers runtime | Cấp Docker/container runtime, kiểm tra quyền |
| Container start timeout | Couchbase bootstrap | Docker RAM/CPU/disk, image, enabled services |
| `Cluster.connect` trả về nhưng KV timeout | SDK bootstrap | `Cluster/Bucket.waitUntilReady`, mapped ports |
| Bucket not found | Resource provisioning | So `BucketDefinition` với Spring bucket property |
| Scope/collection not found | Collection manifest/setup | Provision đúng tên và poll KV readiness |
| `No index available` | SQL++/index | Tạo index phù hợp, `EXPLAIN` |
| `watchIndexes` timeout | Index build | Index Service, trạng thái index và quota |
| KV thấy document, SQL++ chưa thấy | Scan consistency | `REQUEST_PLUS` hoặc cơ chế phù hợp |
| Unauthorized/Authentication failure | Credentials/RBAC | Kiểm tra principal và quyền, không retry vô hạn |
| A PASS, B FAIL sau khi container stop | Spring context cache | Đồng bộ context–container lifecycle |
| Test local PASS nhưng CI FAIL | Hạ tầng/version | Pin image, RAM/CPU, Docker runtime |
| Cùng một test lúc PASS, lúc FAIL | Fixed sleep/race | Readiness checks có deadline và isolation |
| Reactive query không chạy | Publisher chưa subscribe | `StepVerifier`/subscription |
| Context load PASS nhưng query thất bại | Thiếu index hoặc bean config | Test I/O thực và logs cụ thể |

**Không sửa mọi lỗi bằng tăng sleep.** Phải xác định Docker, SDK, bucket, collection, index hay consistency là tầng bị lỗi.

### 13.1. Readiness timeouts nên tách riêng

| Giai đoạn | Timeout ví dụ | Điều kiện dừng |
| --- | --- | --- |
| Container bootstrap | Theo image/resources | Startup strategy hoàn thành |
| Cluster wait | 60 giây | Service đạt desired state |
| Bucket wait | 60 giây | Bucket/KV sockets ready |
| Collection probe | 30 giây | KV probe không lỗi collection |
| Index watch | 90 giây | Index ONLINE |
| SQL++ query | Theo SLO test | Query với consistency phù hợp trả về |

Các số trong bảng **không phải default hoặc SLO do Couchbase quy định**. Chúng là ví dụ để test báo nguyên nhân riêng cho từng tầng và fail với timeout hữu hạn.

## 14. CAS, TTL, transaction và reactive sau khi readiness PASS

Readiness chỉ nói service có thể nhận thao tác. Nó **không chứng minh** correctness của các tính năng sau.

### 14.1. CAS @Version

~~~java
String key = "it::cas::" + UUID.randomUUID();

try {
    orders.save(new Order(key, "customer::u100", 100000));

    Order first = orders.findById(key).orElseThrow();
    Order stale = orders.findById(key).orElseThrow();

    first.addAmount(10000);
    orders.save(first);

    stale.addAmount(20000);
    assertThrows(
        org.springframework.dao.OptimisticLockingFailureException.class,
        () -> orders.save(stale));

    assertEquals(110000L,
        orders.findById(key).orElseThrow().getTotalAmountVnd());
} finally {
    orders.deleteById(key);
}
~~~

Hai snapshot phải được đọc **riêng**, CAS là token opaque, không kiểm tra bằng “tăng đúng 1”. Retry cần đọc lại rồi tính lại quyết định nghiệp vụ; không được lưu lại object stale vô hạn.

### 14.2. TTL

~~~java
var collection = cluster.bucket("shop_it").defaultCollection();
String key = "it::ttl::" + UUID.randomUUID();

collection.insert(
    key,
    com.couchbase.client.java.json.JsonObject.create()
        .put("kind", "temporary"),
    com.couchbase.client.java.kv.InsertOptions.insertOptions()
        .expiry(Duration.ofSeconds(4))
);
~~~

Sau đó dùng Awaitility/polling để chờ `collection.exists(key).exists()` thành false trong timeout có căn cứ. `Clock.fixed` hoặc Reactor virtual time không tua nhanh đồng hồ server. TTL cũng có thể bị ảnh hưởng bởi maxTTL hoặc touch/replace options.

### 14.3. Transaction

Nếu nghiệp vụ cần thay đổi Order và Inventory cùng nguyên tử, phải kiểm tra **Couchbase Transactions API hoặc cơ chế Spring transaction được cấu hình thật**, không suy từ `waitUntilReady`. Tạo hai document, chủ động gây lỗi trong workflow, đối chiếu commit/abort và retry/idempotency. Một container đơn node không mô phỏng đầy đủ failover/quorum.

### 14.4. Reactive waitUntilReady phải subscribe

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(
    cluster.reactive()
        .waitUntilReady(Duration.ofSeconds(60))
).verifyComplete();

StepVerifier.create(
    cluster.bucket("shop_it")
        .reactive().waitUntilReady(Duration.ofSeconds(60))
).verifyComplete();
~~~

Nếu chỉ tạo `Mono<Void>` mà không subscribe, không nên khẳng định đã đợi readiness. Reactive repository `save()` và cleanup `deleteById()` cũng cần subscription/verification. Reactor virtual time chỉ tác động những scheduler thuộc pipeline, không thay thời gian bootstrap/expiry của Couchbase.

## 15. CI và security: test động vẫn cần guardrail

Trước khi chạy bộ integration test:

- Cấp Docker/container runtime và CPU/RAM/disk đủ cho Couchbase.
- Pin Server image, Java SDK, Spring Boot và Testcontainers theo ma trận tương thích.
- Dùng bucket tên riêng như `shop_it`, không dùng credential production.
- Không fallback sang URL production khi container chưa chạy.
- Có namespace hoặc UUID cho mọi document test.
- Cleanup theo key trong `finally`/tearDown; tránh `deleteAll` trên tài nguyên dùng chung.
- Phân biệt lỗi môi trường với assertion dữ liệu.
- Báo `SKIPPED` rõ khi thiếu Docker; CI gate bắt buộc không được coi đó là integration PASS.
- Không in password/raw JSON PII trong log.
- Với nhiều suites chạy song song, quản lý collection/index setup idempotent và vòng đời context cùng container.

### 15.1. @DataCouchbaseTest không thay thế resource readiness

`@DataCouchbaseTest` cấu hình Spring Data slice và repository, **không tự khởi động Couchbase Server**. `@ServiceConnection` hoặc `@DynamicPropertySource` cấp endpoint, nhưng không tạo index/collection. `CouchbaseContainer` tạo server/bucket theo cấu hình, nhưng không tự biết nghiệp vụ cần những index nào.

Bộ test hoàn chỉnh cần tất cả:

~~~text
Container + connection details
  -> SDK Cluster/Bucket ready
  -> Scope/collection/index provision
  -> Index ONLINE
  -> Repository/Template/SDK assertions
  -> Cleanup và CI reporting
~~~

## 16. Bài thực hành: kiểm thử shop_it.sales.orders từ môi trường động

**Bối cảnh:** ứng dụng lưu Order trong `shop_it.sales.orders`, query theo `customer_id` và có `@Version`. Test trên laptop PASS nhưng đôi khi CI báo index not found hoặc connection timeout.

### 16.1. Nhiệm vụ

1. Cấu hình `CouchbaseContainer` với KV/QUERY/INDEX và bucket `shop_it`.
2. Dùng một trong `@DynamicPropertySource` hoặc `@ServiceConnection` để cấp endpoint và credentials.
3. Gọi `Cluster.waitUntilReady` và `Bucket.waitUntilReady`.
4. Tạo scope `sales`/collection `orders` trước khi thực hiện repository operation.
5. Poll collection cho tới khi KV request chạy thành công.
6. Tạo `ix_orders_customer` và chờ index ONLINE.
7. Ghi Order với key UUID; xác minh JSON body bằng SDK.
8. Thực hiện SQL++ `REQUEST_PLUS` để đọc mutation vừa ghi.
9. Dùng hai snapshot để kiểm tra CAS conflict.
10. Cleanup theo key và giải thích cách xử lý Spring context cache nếu nhiều test classes dùng container khác nhau.

### 16.2. Luồng triển khai gợi ý

~~~mermaid
flowchart TB
    A["CouchbaseContainer"] --> B["DynamicPropertySource/ServiceConnection"]
    B --> C["Spring Cluster bean"]
    C --> D["Cluster.waitUntilReady"]
    D --> E["Bucket.waitUntilReady"]
    E --> F["createScope/createCollection"]
    F --> G["Collection KV probe"]
    G --> H["CREATE INDEX"]
    H --> I["watchIndexes ONLINE"]
    I --> J["Insert/Save Order"]
    J --> K["SDK raw JSON + Query REQUEST_PLUS"]
    K --> L["CAS assertions + cleanup"]
~~~

### 16.3. Skeleton test bổ sung named collection

~~~java
// Gắn @Scope("sales") và @Collection("orders") vào Order entity.
// Đảm bảo fixture provision resources trước khi repo thao tác.

@DataCouchbaseTest
@Testcontainers
class SalesOrderIT {

    @Container
    static final CouchbaseContainer COUCHBASE =
        new CouchbaseContainer(DockerImageName.parse(
            "couchbase/server:community-7.2.5"))
            .withEnabledServices(
                CouchbaseService.KV,
                CouchbaseService.QUERY,
                CouchbaseService.INDEX)
            .withBucket(new BucketDefinition("shop_it"));

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry registry) {
        registry.add("spring.couchbase.connection-string",
            COUCHBASE::getConnectionString);
        registry.add("spring.couchbase.username",
            COUCHBASE::getUsername);
        registry.add("spring.couchbase.password",
            COUCHBASE::getPassword);
        registry.add("spring.data.couchbase.bucket-name",
            () -> "shop_it");
    }

    @Autowired Cluster cluster;
    @Autowired OrderRepository orders;

    // Provision sales.orders và ix_orders_customer
    // tại đúng lifecycle của dự án.
    // Mỗi test dùng key riêng + raw SDK read + cleanup.
}
~~~

Đây là **skeleton có chủ ý**; chưa tạo index/collection và chưa chạy đầy đủ assertions. Khi hiện thực, dùng fixture/setup phù hợp để đảm bảo tài nguyên được provision trước hoạt động thực của repository.

### 16.4. Câu hỏi tự kiểm tra

1. **`Cluster.connect` có đợi toàn bộ SDK bootstrap xong không?** Không; bootstrap có thể lazy.
2. **`@DynamicPropertySource` có tự khởi động Docker container không?** Không.
3. **Property bucket của Spring Data Couchbase là gì?** `spring.data.couchbase.bucket-name`.
4. **Vì sao không hardcode `localhost:8091`?** Docker ports động và 8091 không phải connection string SDK thích hợp.
5. **`@ServiceConnection` có tự tạo index không?** Không.
6. **`Bucket.waitUntilReady` thêm gì so với cluster wait?** Chờ bucket/KV data sockets.
7. **`watchIndexes` có tự CREATE INDEX không?** Không, nó chờ index đã tạo ONLINE.
8. **Chờ index ONLINE có đảm bảo query mặc định thấy document vừa save ngay không?** Không, còn scan consistency.
9. **`REQUEST_PLUS` có giá gì?** Có thể tăng latency do chờ index bắt kịp.
10. **Sau createCollection có thể cần gì thêm?** Chờ collection manifest/đường KV usable với timeout.
11. **Tại sao một test class khác có thể kết nối port đã dừng?** Spring context cache không khớp container lifecycle.
12. **Test CAS cần bao nhiêu snapshot?** Hai snapshot độc lập từ cùng phiên bản.
13. **Mono readiness có tự chạy nếu không subscribe?** Không nên giả định; dùng StepVerifier/subscribe.
14. **Có nên retry lỗi authentication khi chờ collection?** Không; phải fail fast.
15. **CI skip integration do thiếu Docker có thể báo PASS không?** Không.

## 17. Checklist triển khai

- [ ] Pin các version Spring Boot/Data Couchbase/SDK/Testcontainers/Server tương thích.
- [ ] Cấp endpoint và credentials từ chính `CouchbaseContainer`.
- [ ] Dùng `@DynamicPropertySource` hoặc `@ServiceConnection`, không đặt nhiều nguồn mâu thuẫn.
- [ ] Cấu hình bucket riêng và trùng `BucketDefinition`.
- [ ] Phân biệt Docker process running với Couchbase SDK ready.
- [ ] Gọi `Cluster.waitUntilReady` có timeout; chỉ định service types nếu cần.
- [ ] Gọi `Bucket.waitUntilReady` cho bucket/KV bootstrap.
- [ ] Provision named scopes/collections và chờ manifest usable.
- [ ] Tạo secondary index phục vụ query; `watchIndexes` cho tới ONLINE.
- [ ] Xác định SQL++ scan consistency, dùng `REQUEST_PLUS` nếu cần read-after-write.
- [ ] Test raw JSON với SDK để bắt lỗi `@Field`, key/CAS.
- [ ] Chỉ retry lỗi readiness có thể phục hồi; không sleep cố định thay assertion.
- [ ] Đồng bộ Spring context cache với vòng đời container giữa các test class.
- [ ] Dùng key UUID/namespace, cleanup theo key, tránh `deleteAll`.
- [ ] Reactive test phải subscribe cả I/O và cleanup.
- [ ] CI có đủ tài nguyên, Docker runtime và báo rõ test bị skip/fail.
- [ ] Không kết nối cluster hoặc dùng credential production trong test.

## Tài liệu tham khảo chính thức

- [Spring Framework — @DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html): static method, registry, lazy Supplier và property precedence.
- [Spring Framework — Context Configuration with Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): context caching và `@DirtiesContext` khi nguồn động thay đổi.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache key và vòng đời ApplicationContext.
- [Spring Boot — Testcontainers Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection`, `CouchbaseConnectionDetails` và ưu tiên connection details.
- [Spring Boot 3.5 — Auto-configured Data Couchbase Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataCouchbaseTest` phiên bản 3.x.
- [Spring Boot 4.x — Auto-configured Data Couchbase Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): module/import phiên bản 4.x.
- [Testcontainers for Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): `CouchbaseContainer`, `BucketDefinition` và connection details.
- [Testcontainers for Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): container lifecycle.
- [Couchbase Java SDK — Managing Connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html): Cluster/Bucket bootstrap và `waitUntilReady`.
- [Couchbase Java SDK — WaitUntilReadyOptions](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/diagnostics/WaitUntilReadyOptions.html): service types và desired state.
- [Couchbase Java SDK — Provisioning Cluster Resources](https://docs.couchbase.com/java-sdk/current/howtos/provisioning-cluster-resources.html): scope/collection/index management và `watchIndexes`.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): QueryOptions và scan consistency.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Id`, `@Field`, `@Version`.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): KV và query methods.
