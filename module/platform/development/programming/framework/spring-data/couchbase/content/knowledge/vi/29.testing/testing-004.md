# Khởi tạo CouchbaseContainer bằng Testcontainers trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `CouchbaseContainer`, `BucketDefinition`, `CouchbaseService` và JUnit 5 extension trong **Testcontainers for Java**.
2. Chọn đúng các dependency và import theo **Testcontainers 1.x/2.x** và **Spring Boot 3.x/4.x**, tránh lắp ghép API khác phiên bản.
3. Khởi tạo Couchbase Server kiểm thử, tạo bucket, chọn **KV / Query / Index Services** và kết nối qua Couchbase Java SDK.
4. Tích hợp container với Spring Data Couchbase qua `@ServiceConnection` hoặc `@DynamicPropertySource`, đồng thời cấu hình bucket cho `@DataCouchbaseTest`.
5. Provision **scope/collection/index** riêng, đợi tài nguyên sẵn sàng, không dùng `sleep` cố định để che lỗi.
6. Viết test thực cho `@Id`, `@Field`, repository, `CouchbaseTemplate`, JSON body, SQL++, CAS và TTL.
7. Tổ chức container lifecycle, isolation, cleanup và CI sao cho không kết nối nhầm production hoặc dùng lại một Spring context đã gắn container bị dừng.

Bài thuộc chương **Kiểm thử** của module **SPRING_DATA_COUCHBASE**, là module xây dựng tầng truy cập Couchbase bằng Spring Data document mapping, repository, `CouchbaseTemplate` và SQL++, đồng thời xử lý bucket/scope/collection, index, TTL, CAS, giao dịch và API reactive. Trọng tâm ở đây là **khởi tạo và quản lý tài nguyên kiểm thử Couchbase một cách xác định**, trước khi đi sâu các loại assertion ở những bài kiểm thử khác.

## 1. Vì sao cần CouchbaseContainer thay vì mock repository?

Mock repository có thể giúp kiểm tra service đã gọi `findById` và `save`, nhưng nó không khởi tạo Couchbase Server, không serialize JSON, không thực thi SQL++ hay kiểm tra CAS.

`CouchbaseContainer` của Testcontainers cung cấp một **Couchbase Server thực chạy trong container**, được cấp phát và dọn dẹp trong vòng đời test. Nhờ đó test có thể kiểm tra:

- `@Id` ánh xạ thành **document key** và `@Field` ghi đúng JSON field.
- Repository truy cập đúng **bucket/scope/collection**.
- Key-Value operations như `insert`, `get`, `replace` trả lỗi đúng với tình huống.
- SQL++ query hoạt động khi có Query/Index Services và secondary index phù hợp.
- `@Version` dùng CAS và phát hiện update từ snapshot cũ.
- TTL/expiry được thực thi bằng đồng hồ của Couchbase Server.
- Reactive repository thực sự phát sinh I/O khi được subscribe.

~~~mermaid
flowchart LR
    J["JUnit 5"] --> T["CouchbaseContainer"]
    T --> S["Couchbase Server test"]
    S --> K["KV"]
    S --> Q["Query"]
    S --> I["Index"]
    B["Spring @DataCouchbaseTest"] --> C["Repository / CouchbaseTemplate"]
    C --> D["Couchbase Java SDK"]
    D --> S
    B -.->|"@ServiceConnection / properties"| T
~~~

**Giới hạn:** một container Couchbase đơn node không tự mô phỏng cluster production nhiều node, replica failover, network partition hoặc mọi mức durability quorum. Nó rất hữu ích cho integration test KV/SQL++/mapping/CAS cơ bản, không phải bằng chứng đầy đủ cho resilience.

## 2. Chọn bộ phiên bản trước khi sao chép ví dụ

Tại thời điểm tài liệu được soạn, tài liệu Testcontainers chính thức có ví dụ artifact `org.testcontainers:testcontainers-couchbase:2.0.5`; Spring Boot 4.x có module test slice riêng `spring-boot-data-couchbase-test`. Không có một đoạn import duy nhất đúng cho mọi thế hệ thư viện.

| Trường hợp | Dependency Couchbase Testcontainers | Import `CouchbaseContainer` |
| --- | --- | --- |
| Testcontainers **1.x** | `org.testcontainers:couchbase` | `org.testcontainers.couchbase.CouchbaseContainer` |
| Testcontainers **2.x** | `org.testcontainers:testcontainers-couchbase` | `org.testcontainers.couchbase.CouchbaseContainer` |

| Spring Boot | Test slice | Import `@DataCouchbaseTest` |
| --- | --- | --- |
| **3.x** | Tích hợp trong boot test auto-config | `org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest` |
| **4.x** | `spring-boot-data-couchbase-test` (hoặc starter test tương ứng) | `org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest` |

**Hai điều phải tách biệt:** Testcontainers version quyết định tọa độ dependency của `CouchbaseContainer`; Spring Boot version quyết định test module/package của `@DataCouchbaseTest`. Couchbase Java SDK version lại quyết định những API quản lý bucket/collection/index mà bạn có thể gọi.

### 2.1. Dependency Gradle cho Spring Boot 4.x + Testcontainers 2.x

Giả sử dự án đã dùng Spring Boot plugin/BOM tương thích với các dependency dưới đây:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'

    testImplementation 'org.springframework.boot:spring-boot-starter-data-couchbase-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'

    // Phiên bản Testcontainers 2.x cần được quản lý thống nhất bằng BOM.
    testImplementation 'org.testcontainers:testcontainers-couchbase'
    testImplementation 'org.testcontainers:testcontainers-junit-jupiter'

    // Khi có kiểm thử publisher Reactor.
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Nếu Testcontainers BOM không được BOM hiện tại quản lý như mong muốn, import BOM `org.testcontainers:testcontainers-bom` hoặc pin **cùng một phiên bản được dự án kiểm chứng** cho hai module Testcontainers. Không chọn ngẫu nhiên hai minor version khác nhau.

### 2.2. Dependency thay thế cho Spring Boot 3.x + Testcontainers 1.x

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'

    testImplementation 'org.testcontainers:couchbase'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Với Boot 3.x, đổi import `@DataCouchbaseTest` theo bảng trên. **Không trộn artifact `couchbase` của Testcontainers 1.x với `testcontainers-junit-jupiter` của 2.x** rồi coi thiếu class là lỗi Couchbase Server.

### 2.3. Chọn Docker image có phiên bản

~~~java
DockerImageName image = DockerImageName.parse(
    "couchbase/server:community-7.2.5");
~~~

Image trên là **phiên bản minh họa được pin**, không phải đề xuất rằng mọi dự án năm 2026 phải chạy Couchbase 7.2.5. Nên chọn tag Server nằm trong **ma trận tương thích Java SDK/Spring Data** và sát phiên bản production mà ứng dụng hỗ trợ. Với bài kiểm thử nâng cấp, có thể chạy suite trên nhiều tag đã chọn.

Không dùng `couchbase/server:latest` làm cơ sở kiểm thử hồi quy quan trọng: hôm nay và ngày mai có thể kéo về phiên bản khác nhau.

## 3. Khởi tạo tối thiểu: không cần Spring để hiểu lifecycle

Điểm khởi đầu nhỏ nhất là tạo một `BucketDefinition`, gắn nó vào `CouchbaseContainer`, gọi `start()` rồi kết nối bằng Java SDK.

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;

import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.utility.DockerImageName;

public class CouchbaseContainerSmokeExample {

    public static void main(String[] args) {
        CouchbaseContainer container = new CouchbaseContainer(
            DockerImageName.parse("couchbase/server:community-7.2.5"))
            .withEnabledServices(
                CouchbaseService.KV,
                CouchbaseService.QUERY,
                CouchbaseService.INDEX)
            .withBucket(new BucketDefinition("shop_it"));

        container.start();

        try (Cluster cluster = Cluster.connect(
                container.getConnectionString(),
                container.getUsername(),
                container.getPassword())) {
            var collection = cluster.bucket("shop_it").defaultCollection();
            String key = "smoke::product::1";

            collection.upsert(key,
                JsonObject.create().put("name", "Cà phê test"));

            String value = collection.get(key)
                .contentAsObject().getString("name");

            if (!"Cà phê test".equals(value)) {
                throw new AssertionError("Smoke test thất bại");
            }
        } finally {
            container.stop();
        }
    }
}
~~~

Đây là **mẫu minh họa vòng đời thủ công**. Trong test JUnit, nên để JUnit extension hoặc một test fixture quản lý `start/stop`; không sao chép `main()` vào test rồi khởi tạo một cluster mới cho mỗi assertion.

### 3.1. Các bước container.start() quản lý

`CouchbaseContainer` sử dụng Docker runtime để:

1. Tạo container từ image chỉ định, với các cổng/service cần thiết.
2. Khởi tạo một cluster Couchbase dành cho test theo cấu hình module.
3. Bật các service đã yêu cầu.
4. Thiết lập thông tin xác thực kiểm thử.
5. Tạo bucket được định nghĩa bằng `withBucket(...)`.
6. Trả endpoint/credential để Java SDK kết nối.

Không nên tự giả định thao tác `start()` cũng tạo scope `sales`, collection `orders`, index theo `customer_id` hay dữ liệu fixture. **`withBucket` chỉ khai báo bucket**, những tài nguyên còn lại phải provision theo yêu cầu test.

### 3.2. Vì sao dùng getConnectionString thay vì IP/port tự đoán?

~~~java
String url = container.getConnectionString();
String username = container.getUsername();
String password = container.getPassword();
~~~

Couchbase SDK dùng các service/ports cho KV, Query, Index và có cơ chế cluster discovery. Testcontainers ánh xạ port của container sang host. **Không thay `getConnectionString()` bằng `localhost:8091` hoặc `container.getHost() + ":8091"`**, vì cổng UI/management không phải cấu hình kết nối SDK đầy đủ.

Không ghi username/password và connection string ra log CI không cần thiết. Nếu cần hỗ trợ debug, log loại server/port sau khi loại thông tin nhạy cảm.

## 4. Chọn đúng service: KV không đồng nghĩa Query và Index

`CouchbaseService` cung cấp các giá trị như `KV`, `QUERY`, `INDEX`, `SEARCH`, `ANALYTICS`, `EVENTING`. Không cần bật tất cả cho một suite nhỏ.

| Phạm vi kiểm thử | Services tối thiểu nên xem xét | Vì sao |
| --- | --- | --- |
| SDK `get/insert/upsert/replace` | `KV` | Đọc/ghi theo document key |
| Spring Data `findById` / `save` | `KV` (cùng mapping) | Repository thao tác theo key |
| Derived query `findByCustomerId` | `KV` + `QUERY` + `INDEX` | SQL++ cần Query/Index |
| SQL++ `CREATE INDEX`, `EXPLAIN` | `QUERY` + `INDEX` | DDL/query và Index Service |
| Full Text Search | `SEARCH` và các service liên quan | Không phải SQL++ index thông thường |
| Analytics/Eventing | `ANALYTICS` / `EVENTING` khi test có dùng | Tốn thêm tài nguyên, cần setup riêng |

~~~java
CouchbaseContainer couchbase = new CouchbaseContainer(image)
    .withEnabledServices(
        CouchbaseService.KV,
        CouchbaseService.QUERY,
        CouchbaseService.INDEX)
    .withBucket(new BucketDefinition("shop_it"));
~~~

**Query Service và Index Service là hai service khác nhau.** Bật Query nhưng thiếu Index có thể khiến các SQL++ queries cần index không chạy; bật đủ services nhưng không tạo secondary index cũng chưa đủ.

### 4.1. Memory quota và tài nguyên Docker

Testcontainers `CouchbaseContainer` có API `withServiceQuota(CouchbaseService, int)` để chỉnh quota của service. Nhưng không nên đặt mọi quota thật thấp chỉ để CI chạy: Couchbase có **mức tối thiểu và yêu cầu tổng bộ nhớ** theo phiên bản Server.

Ví dụ tùy chỉnh quota (các số phải được kiểm tra với image đang dùng):

~~~java
CouchbaseContainer couchbase = new CouchbaseContainer(image)
    .withEnabledServices(
        CouchbaseService.KV,
        CouchbaseService.QUERY,
        CouchbaseService.INDEX)
    .withServiceQuota(CouchbaseService.KV, 256)
    .withServiceQuota(CouchbaseService.INDEX, 256)
    .withBucket(new BucketDefinition("shop_it"));
~~~

Giá trị `256` MB là **mẫu cấu hình để minh họa API**, không được coi là bảo đảm đủ cho mọi bản Couchbase. CI cần được cấp CPU/RAM và disk thực tế; việc container bootstrap thất bại vì quota không hợp lệ không phải lỗi repository.

### 4.2. BucketDefinition không phải schema migration

~~~java
BucketDefinition bucket = new BucketDefinition("shop_it");

CouchbaseContainer container = new CouchbaseContainer(image)
    .withBucket(bucket);
~~~

Bucket là cấp tài nguyên chứa document; scope/collection nằm bên trong bucket. `BucketDefinition` có thể hỗ trợ tùy chọn bucket theo phiên bản Testcontainers, nhưng vẫn không thay thế migration SQL++/SDK tạo collection và index.

**Một bucket thật tồn tại không chứng minh Spring Data entity đang dùng đúng bucket đó**. Khi tích hợp Spring Boot, phải đặt `spring.data.couchbase.bucket-name` cùng tên.

## 5. JUnit 5: @Testcontainers và @Container quản lý vòng đời

Trong JUnit Jupiter, `@Testcontainers` kích hoạt extension; `@Container` đánh dấu field container để extension quản lý.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class CouchbaseKvIT {

    @Container
    static final CouchbaseContainer COUCHBASE =
        new CouchbaseContainer(
            DockerImageName.parse("couchbase/server:community-7.2.5"))
            .withBucket(new BucketDefinition("shop_it"));

    @Test
    void containerHasAnAccessibleBucket() {
        Cluster cluster = Cluster.connect(
            COUCHBASE.getConnectionString(),
            COUCHBASE.getUsername(),
            COUCHBASE.getPassword());

        try {
            var collection = cluster.bucket("shop_it").defaultCollection();
            var result = collection.upsert(
                "it::smoke::" + java.util.UUID.randomUUID(),
                JsonObject.create().put("ok", true));
            // Đây là thao tác KV thực: có CAS do Couchbase cấp.
            org.junit.jupiter.api.Assertions.assertNotEquals(0L, result.cas());
        } finally {
            cluster.disconnect();
        }
    }
}
~~~

Các import `Cluster` và `JsonObject` theo SDK trong mục 3.

### 5.1. Static và instance container

| Kiểu field | Vòng đời thường dùng | Đánh đổi |
| --- | --- | --- |
| `static @Container` | Một container cho **test class** | Ít lần bootstrap; test methods cần isolation |
| Instance `@Container` | Container riêng cho từng **test method** | Cô lập tốt hơn nhưng Couchbase startup đắt |
| Một container thủ công cho nhiều classes | Dùng chung có chủ đích | Phải quản lý Spring context cache, setup, cleanup |
| `withReuse(true)` (experimental) | Có thể giữ container giữa các lần chạy khi cấu hình cho phép | Rủi ro dữ liệu/tài nguyên cũ; không phù hợp mặc định CI |

**Không sử dụng việc chạy song song trên cùng một static container mà thiếu chiến lược keyspace/fixture.** Testcontainers JUnit extension có các giới hạn liên quan parallel execution; nếu bật JUnit parallel, phải kiểm chứng lifecycle và tránh xung đột dữ liệu.

### 5.2. Khi nào phải tự start/stop?

Nếu một chương trình không dùng JUnit extension, bạn có thể điều khiển:

~~~java
CouchbaseContainer couchbase = new CouchbaseContainer(image)
    .withBucket(new BucketDefinition("shop_it"));

try {
    couchbase.start();
    // Tạo Cluster, chạy test...
} finally {
    couchbase.stop();
}
~~~

Không gọi `start()` lần nữa trong mỗi `@BeforeEach` nếu container đã do `@Testcontainers`/`@Container` quản lý. Khi Spring giữ `ApplicationContext` cache giữa nhiều test class, nếu container dừng sau class đầu mà context còn giữ connection details cũ thì class sau có thể kết nối vào port không còn hoạt động.

## 6. Tích hợp Spring Boot 4.x qua @ServiceConnection

Đây là cấu hình thuận tiện khi ứng dụng dùng Spring Boot hỗ trợ **Service Connections**.

### 6.1. Entity ví dụ: Inventory

~~~java
package com.example.shop.inventory;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Inventory {

    @Id
    private String id;

    @Version
    private Long cas;

    @Field("available_units")
    private int availableUnits;

    protected Inventory() {}

    public Inventory(String id, int availableUnits) {
        if (id == null || id.isBlank() || availableUnits < 0) {
            throw new IllegalArgumentException("Inventory không hợp lệ");
        }
        this.id = id;
        this.availableUnits = availableUnits;
    }

    public String getId() { return id; }
    public Long getCas() { return cas; }
    public int getAvailableUnits() { return availableUnits; }

    public void reserve(int count) {
        if (count <= 0 || count > availableUnits) {
            throw new IllegalArgumentException("Không đủ tồn kho");
        }
        availableUnits -= count;
    }
}
~~~

Repository:

~~~java
package com.example.shop.inventory;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface InventoryRepository
        extends CouchbaseRepository<Inventory, String> {
}
~~~

### 6.2. Test slice hoàn chỉnh cho KV + raw JSON

Ví dụ sau sử dụng **Spring Boot 4.x + Testcontainers 2.x**. Các imports được viết theo cặp phiên bản này; nếu đang dùng Boot 3.x, đổi `@DataCouchbaseTest` theo mục 2.

~~~java
package com.example.shop.inventory;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import com.couchbase.client.java.Cluster;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=shop_it")
@Testcontainers
class InventoryRepositoryIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer COUCHBASE =
        new CouchbaseContainer(
            DockerImageName.parse("couchbase/server:community-7.2.5"))
            .withEnabledServices(
                CouchbaseService.KV,
                CouchbaseService.QUERY,
                CouchbaseService.INDEX)
            .withBucket(new BucketDefinition("shop_it"));

    @Autowired InventoryRepository repository;
    @Autowired Cluster cluster;

    @Test
    void savesAndReadsRealDocument() {
        String key = "it::inventory::" + UUID.randomUUID();

        try {
            repository.save(new Inventory(key, 15));
            Inventory loaded = repository.findById(key).orElseThrow();

            assertEquals(15, loaded.getAvailableUnits());

            var result = cluster.bucket("shop_it")
                .defaultCollection().get(key);

            assertEquals(15,
                result.contentAsObject().getInt("available_units"));
            assertFalse(result.contentAsObject().containsKey("id"));
            assertNotEquals(0L, result.cas());
        } finally {
            repository.deleteById(key);
        }
    }
}
~~~

**Vì sao cần đọc body qua SDK?** Nếu annotation bị gõ nhầm thành `@Field("availble_units")`, `repository.save` và `repository.findById` có thể **cùng** dùng sai tên và round-trip vẫn PASS. SDK assertion kiểm tra trực tiếp hợp đồng JSON được các service khác kỳ vọng.

### 6.3. @ServiceConnection cung cấp gì?

Spring Boot nhận diện `CouchbaseContainer` và cung cấp `CouchbaseConnectionDetails` cho Couchbase auto-configuration, bao gồm endpoint và credential thích hợp.

Nó **không tự**:

- Đặt `spring.data.couchbase.bucket-name` bằng tên bucket nếu ứng dụng chưa khai báo.
- Tạo scope/collection/index nghiệp vụ.
- Seed dữ liệu hoặc chạy migration.
- Bật các business service ngoài `@DataCouchbaseTest`.
- Bảo đảm readiness của index vừa tạo.

Nếu vừa dùng `@ServiceConnection` vừa đặt properties trỏ một cluster khác, hãy hiểu **thứ tự ưu tiên của Spring Boot connection details**; tránh để test pass trên tài nguyên không mong muốn. Khi muốn tự truyền properties, xem mục 7.

## 7. Cách thay thế: @DynamicPropertySource

Với Spring Boot version hoặc cấu hình không dùng `@ServiceConnection`, đăng ký properties từ container thông qua `@DynamicPropertySource`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class InventoryExplicitConnectionIT {

    @Container
    static final CouchbaseContainer COUCHBASE =
        new CouchbaseContainer(
            DockerImageName.parse("couchbase/server:community-7.2.5"))
            .withBucket(new BucketDefinition("shop_it"));

    @DynamicPropertySource
    static void couchbaseProperties(DynamicPropertyRegistry properties) {
        properties.add("spring.couchbase.connection-string",
            COUCHBASE::getConnectionString);
        properties.add("spring.couchbase.username",
            COUCHBASE::getUsername);
        properties.add("spring.couchbase.password",
            COUCHBASE::getPassword);
        properties.add("spring.data.couchbase.bucket-name",
            () -> "shop_it");
    }

    @Test
    void contextUsesExplicitCouchbaseDetails() {
        // Bổ sung KV/Repository assertion thực như mục 6.
    }
}
~~~

**Lưu ý:** ở đây dùng `@SpringBootTest` để minh họa registration độc lập với test slice. Nếu chỉ cần tầng dữ liệu, có thể đổi sang `@DataCouchbaseTest` với import theo Boot version, giữ nguyên phần `@DynamicPropertySource`. Cả hai **không cần dùng đồng thời** trong cùng test class.

Các tên property bên trên là của Spring Boot 3.x/4.x tương ứng; nếu ứng dụng có cấu hình tùy biến hoặc nhiều Cluster bean, test cần chỉ rõ bean đang dùng những properties nào.

### 7.1. @ServiceConnection hay @DynamicPropertySource?

| Tiêu chí | `@ServiceConnection` | `@DynamicPropertySource` |
| --- | --- | --- |
| Kết nối | Spring Boot suy ra từ container type | Test đăng ký từng property |
| Độ ngắn gọn | Ít code | Nhiều code hơn |
| Cần Boot testcontainers support | Có | Không bắt buộc |
| Tùy biến config nhiều cluster | Có thể cần bean/config thêm | Tường minh hơn |
| Bucket/schema resources | Vẫn phải khai báo/provision | Vẫn phải khai báo/provision |
| Debug | Xem connection details tạo bởi Boot | Kiểm tra registry/property names |
| Nguy cơ thường gặp | Tin rằng annotation tự tạo bucket/index | Quên một property, dùng nhầm profile |

**Một nguồn connection details rõ ràng tốt hơn hai nguồn mâu thuẫn.** Nếu test có cả annotation và registry, phải xác minh nguồn nào đang thắng, không suy từ việc container đã khởi động.

## 8. Named scopes/collections: phải tạo trước khi gọi repository

Trong production, Inventory có thể nằm ở:

~~~text
Bucket:     shop
Scope:      warehouse
Collection: inventories
Key:        inventory::coffee250
~~~

Test có thể chọn tên bucket riêng:

~~~text
Bucket:     shop_it
Scope:      warehouse
Collection: inventories
Key:        it::inventory::<UUID>
~~~

Entity:

~~~java
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("warehouse")
@Collection("inventories")
public class Inventory {
    // Các property từ ví dụ mục 6.
}
~~~

**Chỉ khi scope và collection thật đã tồn tại, annotation mới có tài nguyên để thao tác.** `withBucket(new BucketDefinition("shop_it"))` không tạo `warehouse.inventories`.

### 8.1. Provision bằng Couchbase Java SDK

Một fixture setup có quyền quản trị:

~~~java
import com.couchbase.client.core.error.ScopeExistsException;
import com.couchbase.client.core.error.CollectionExistsException;
import com.couchbase.client.java.Bucket;

Bucket bucket = cluster.bucket("shop_it");
var manager = bucket.collections();

try {
    manager.createScope("warehouse");
} catch (ScopeExistsException alreadyExists) {
    // Cho phép fixture setup được gọi nhiều lần.
}

try {
    manager.createCollection("warehouse", "inventories");
} catch (CollectionExistsException alreadyExists) {
    // Collection đã có: không tạo lại.
}
~~~

Trong SDK cũ, một số phiên bản còn dùng `CollectionSpec.create(...)`; với SDK 3.x hiện đại, có overload `createCollection(String scopeName, String collectionName)`. Chọn **API thuộc đúng SDK dự án**.

Trên Couchbase Server, việc tạo collection có thể cần thời gian để manifest đến những thành phần đang kết nối. **Một lời gọi create thành công không có nghĩa mọi SDK operation ngay lập tức đã thấy collection ở mọi node**.

### 8.2. Test không vô tình dùng default collection

Đường SDK phải trùng entity:

~~~java
var inventoryCollection = cluster.bucket("shop_it")
    .scope("warehouse")
    .collection("inventories");

var body = inventoryCollection.get(key).contentAsObject();
~~~

Nếu test vẫn dùng `bucket.defaultCollection().get(key)`, nó đang kiểm tra **một keyspace khác**. Cùng một chuỗi key có thể tồn tại ở hai collection mà không xung đột.

### 8.3. Khi nào provision tài nguyên?

| Cấp setup | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Một lần trong test class `@BeforeAll` | Dễ hiểu và ít bootstrap | Cần bảo đảm index/resource readiness |
| Một fixture chung cho test suite | Tái sử dụng, giảm thời gian chạy | Phải quản lý dữ liệu/test parallel |
| Migration script riêng của CI | Gần quy trình production | CI phức tạp hơn |
| Mỗi test tự tạo scope/collection | Cô lập tốt | Chậm, tốn quota, dễ rò rỉ resources |

Nên tách **provisioning quyền admin** khỏi **runtime principal** khi bài test cần kiểm tra RBAC. Việc test luôn dùng account admin của container không chứng minh ứng dụng production có quyền least privilege.

## 9. Index và readiness: container “running” chưa đủ

Một test dùng `findById` theo key có thể PASS dù Query Service/Index Service chưa sẵn sàng. Nhưng derived query:

~~~java
java.util.List<Inventory> findByAvailableUnits(int availableUnits);
~~~

thường cần SQL++ và index tương ứng.

### 9.1. Index minh họa

~~~sql
CREATE INDEX ix_inventory_available
ON `shop_it`.`warehouse`.`inventories`(available_units);
~~~

Đừng chạy câu query dựa vào `available_units` khi chưa provision index. Với Spring Data generated SQL++, type predicate có thể làm planner chọn index khác; kiểm tra `EXPLAIN` cho query thực tế.

### 9.2. Chờ cluster/bucket và collection

~~~java
import java.time.Duration;

cluster.waitUntilReady(Duration.ofSeconds(90));

var bucket = cluster.bucket("shop_it");
bucket.waitUntilReady(Duration.ofSeconds(90));
~~~

Chờ cluster/bucket chỉ đảm bảo mức readiness được SDK kiểm tra, không có nghĩa **secondary index mới tạo đã ONLINE**. Với collection vừa tạo, có thể poll một thao tác KV an toàn (ví dụ `exists` một key probe không tồn tại) tới khi resource usable, có timeout và phân biệt lỗi “scope/collection not found” với lỗi quyền.

Không thay bằng `Thread.sleep(2000)`: thời gian build index và propagation khác nhau giữa laptop/CI, phụ thuộc CPU/RAM và image.

### 9.3. Chờ index ONLINE

Couchbase Java SDK có `QueryIndexManager.watchIndexes`:

~~~java
import java.time.Duration;
import java.util.List;

import static com.couchbase.client.java.manager.query.WatchQueryIndexesOptions.watchQueryIndexesOptions;

cluster.queryIndexes().watchIndexes(
    "shop_it",
    List.of("ix_inventory_available"),
    Duration.ofSeconds(120),
    watchQueryIndexesOptions()
        .scopeName("warehouse")
        .collectionName("inventories")
);
~~~

Nếu SDK version đang dùng thay đổi overload/options, tham khảo Java SDK Javadoc tương ứng. **Khi watchIndexes timeout, nên fail test/setup**, không âm thầm bỏ qua và cho query chạy với kết quả khó đoán.

### 9.4. Sau save, SQL++ chưa thấy ngay: index consistency

KV có thể thấy mutation mới trước khi secondary index cập nhật. SDK có `QueryScanConsistency.REQUEST_PLUS`:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryScanConsistency;

var result = cluster.query(
    """
    SELECT META(i).id AS docKey,
           i.available_units AS availableUnits
    FROM `shop_it`.`warehouse`.`inventories` AS i
    WHERE i.available_units = $available
    """,
    queryOptions()
        .parameters(JsonObject.create().put("available", 15))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);
~~~

`REQUEST_PLUS` giúp yêu cầu index bắt kịp tại thời điểm query, nhưng có thể tăng latency. **Không phải mọi production query đều cần REQUEST_PLUS.** Bài test phải chọn mức nhất quán theo hợp đồng đang xác minh; nếu mục tiêu là đặc điểm eventual index consistency thì test cả chế độ mặc định.

## 10. Bài kiểm thử tích hợp CRUD + raw JSON + CAS

Sau khi container, Spring context và keyspace đã được chuẩn bị, một test nên kiểm tra **dữ liệu thật**, không chỉ việc repository trả một object:

~~~java
@Test
void roundTripAndCas() {
    String key = "it::inventory::" + UUID.randomUUID();

    try {
        repository.save(new Inventory(key, 15));

        Inventory a = repository.findById(key).orElseThrow();
        Inventory b = repository.findById(key).orElseThrow();

        assertNotNull(a.getCas());
        assertEquals(a.getCas(), b.getCas());

        a.reserve(3);
        repository.save(a);

        b.reserve(2);

        assertThrows(
            org.springframework.dao.OptimisticLockingFailureException.class,
            () -> repository.save(b)
        );

        Inventory stored = repository.findById(key).orElseThrow();
        assertEquals(12, stored.getAvailableUnits());
    } finally {
        repository.deleteById(key);
    }
}
~~~

Tính đúng đắn ở đây dựa vào `@Version` và **hai snapshot độc lập**. Nếu test dùng một reference Java hai lần, sẽ không tái hiện được stale CAS. Không kiểm tra CAS bằng phép cộng 1: CAS là token opaque do Couchbase cấp.

### 10.1. Test đọc JSON do SDK ghi

Để kiểm chứng **chiều đọc của Spring Data**:

~~~java
var collection = cluster.bucket("shop_it")
    .scope("warehouse")
    .collection("inventories");

String key = "it::import::" + UUID.randomUUID();

try {
    collection.insert(key,
        com.couchbase.client.java.json.JsonObject.create()
            .put("available_units", 17));

    Inventory loaded = repository.findById(key).orElseThrow();
    assertEquals(17, loaded.getAvailableUnits());
} finally {
    repository.deleteById(key);
}
~~~

Ví dụ này cần chạy trong cấu hình entity **có `@Scope/@Collection`** và môi trường đã provision tương ứng. Nếu mapper dùng type hint `_class` hoặc subclass, JSON từ SDK phải cung cấp type metadata phù hợp hoặc test phải xác nhận lỗi theo hợp đồng.

### 10.2. CouchbaseTemplate: kiểm tra đúng đường code sản phẩm

Khi production dùng `CouchbaseTemplate`, test bằng repository không thay được:

~~~java
@Autowired
CouchbaseTemplate template;

// Trên entity và keyspace đã setup:
Inventory loaded = template.findById(Inventory.class).one(key);
assertEquals(15, loaded.getAvailableUnits());
~~~

Đây là minh họa phương thức fluent API của Spring Data Couchbase hiện đại; API cụ thể có thể phụ thuộc phiên bản. Nếu service production dùng template với scope/collection override, hãy kiểm tra chính thao tác override đó trên server thật.

## 11. TTL/expiry và đồng hồ của Couchbase Server

Testcontainers không làm Couchbase TTL hoạt động như đồng hồ Java giả. Nếu ứng dụng dùng `@Document(expiry = ...)` hoặc SDK `InsertOptions.expiry(...)`, phải kiểm tra server thật.

~~~java
import java.time.Duration;
import java.util.UUID;

import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

var collection = cluster.bucket("shop_it").defaultCollection();
String key = "it::ttl::" + UUID.randomUUID();

collection.insert(
    key,
    com.couchbase.client.java.json.JsonObject.create()
        .put("purpose", "ttl-test"),
    insertOptions().expiry(Duration.ofSeconds(4))
);

assertTrue(collection.exists(key).exists());
~~~

Sau đó poll với timeout, ví dụ Awaitility:

~~~java
await()
    .atMost(Duration.ofSeconds(40))
    .pollInterval(Duration.ofMillis(300))
    .until(() -> !collection.exists(key).exists());
~~~

Không khẳng định document biến mất đúng mili-giây thứ 4. Test nên kiểm tra:

- Document tồn tại sau insert.
- Hết hạn trong khoảng thời gian chấp nhận được.
- `maxTTL` ở bucket/collection có ảnh hưởng không.
- `touchOnRead` hoặc một mutation khác có làm mới/giữ expiry không.
- Kịch bản update có `preserveExpiry` cần được xác minh riêng.

### 11.1. Không dùng một TTL dài của production cho test ngắn

Giả sử Cart thật có TTL 1 giờ. Test đơn vị policy có thể xác nhận cấu hình/constructor mong muốn, còn test expiry server tạo **document hoặc entity kiểm thử** với thời hạn vài giây, không chờ nguyên 1 giờ. Đừng sửa cấu hình TTL production chỉ để test chạy nhanh nếu điều đó khiến suite không còn kiểm tra đúng policy hoặc gây tác dụng phụ ngoài môi trường test.

## 12. ReactiveCouchbaseRepository với cùng container

Container vẫn là **Couchbase Server**; reactive chỉ thay cách Java client điều phối I/O.

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactiveInventoryRepository
        extends ReactiveCouchbaseRepository<Inventory, String> {
}
~~~

Test với Reactor:

~~~java
import reactor.test.StepVerifier;

String key = "it::rx::" + UUID.randomUUID();

StepVerifier.create(
    reactiveRepository
        .save(new Inventory(key, 10))
        .flatMap(saved -> reactiveRepository.findById(saved.getId()))
)
    .assertNext(item -> assertEquals(10, item.getAvailableUnits()))
    .verifyComplete();

StepVerifier.create(reactiveRepository.deleteById(key))
    .verifyComplete();
~~~

Các lưu ý:

- `Mono` thường **chưa chạy I/O trước khi subscribe**. Chỉ tạo publisher rồi kết thúc test không xác minh gì.
- Cleanup reactive cũng phải subscribe/verify.
- `StepVerifier.withVirtualTime` không tua nhanh TTL Couchbase hoặc index build.
- Cần dependency reactive starter/test và bean reactive repository/template phù hợp với version; không giả định mọi `@DataCouchbaseTest` đều tự có cả blocking và reactive.

Nếu test CAS reactive, dùng hai publisher/read độc lập và kiểm tra error signal đúng, không nuốt exception bằng `onErrorResume` tùy tiện.

## 13. Container lifecycle trong Spring context: lỗi khó phát hiện

Một lỗi điển hình là:

1. Class A tạo static `CouchbaseContainer` và Spring context C.
2. JUnit kết thúc class A, extension stop container.
3. Spring cache giữ context C.
4. Class B có cấu hình tương tự dùng lại C, nhưng connection details trỏ đến port đã ngừng.

Giải pháp có thể là:

- Giữ container thật sống trong toàn bộ vòng đời context chia sẻ.
- Dùng mỗi test class một context/lifecycle nhất quán khi isolation quan trọng.
- Không dùng Spring context caching mâu thuẫn với container lifecycle.
- Chỉ dùng `@DirtiesContext` có chủ đích khi bắt buộc đóng context; không thêm đại trà làm mọi test chậm.
- Nếu chia sẻ container toàn suite, setup và teardown phải do một fixture có owner rõ, không để từng class cùng gọi stop.

**Không bật `withReuse(true)` chỉ để giảm startup trong CI**. Container tái sử dụng là tính năng có ràng buộc/mức hỗ trợ riêng và có thể giữ trạng thái cũ. Ưu tiên khả năng tái hiện và isolation trước.

### 13.1. Container start timeout và chẩn đoán

Couchbase bootstrap tốn tài nguyên hơn các dịch vụ rất nhỏ; khi startup chậm, trước tiên kiểm tra:

- Docker daemon có chạy và được quyền truy cập không.
- Image đã được pull đúng kiến trúc CPU chưa.
- RAM/CPU/disk của Docker VM đủ cho services/index không.
- Bucket quota và service quota có hợp lệ không.
- Log container có báo bootstrap failure hay resource limit không.
- Port mapping/network và DNS có được hệ thống hỗ trợ không.
- CI có đang chạy quá nhiều Couchbase containers song song không.

Tăng timeout **chỉ sau khi** xác nhận nguyên nhân là bootstrap chậm hợp lý. Một lỗi credential, invalid bucket definition hoặc quota không đủ không nên bị “chữa” bằng cách chờ lâu hơn.

## 14. CI: cấu hình tài nguyên và fail-fast

Một bộ test Couchbase có nhiều tài nguyên hơn một unit test JUnit thông thường.

| Tài nguyên CI | Điều cần đảm bảo |
| --- | --- |
| Docker/container runtime | Có daemon hoặc Testcontainers-compatible runtime được chấp thuận |
| CPU/RAM | Đủ cho Couchbase KV/Query/Index và JVM test |
| Disk | Đủ image layers, data files và index build |
| Network | Có thể pull image, kết nối host-mapped ports |
| Image/version | Pin tag, dùng registry/mirror phù hợp chính sách công ty |
| Test profile | Bucket chỉ dành cho test, không chứa credential production |
| Timeout | Hữu hạn và phân biệt startup, index build, query |
| Parallel jobs | Không dùng chung key/bucket khi không có isolation |
| Logs | Giữ log lỗi setup nhưng không lộ secrets/JSON cá nhân |
| Gate | Test tích hợp bị skip vì thiếu Docker **không được báo là đã PASS** |

Nếu developer laptop tạm thời không có Docker, có thể đánh dấu rõ suite integration bị skip trong profile local; **merge gate** hoặc release gate vẫn phải chạy thật những test được yêu cầu.

### 14.1. Gradle test separation

Có thể dùng quy ước tên class:

~~~text
*Test.java       -> domain/service unit test
*IT.java         -> integration test cần Couchbase
*PerformanceIT  -> test tải/độ trễ ở môi trường riêng
~~~

Sau đó cấu hình Gradle test tasks/suites để chạy mỗi nhóm theo cadence phù hợp. Không dùng filter tên class để **vô tình loại toàn bộ `*IT` khỏi CI**, rồi khẳng định persistence đã được kiểm chứng.

### 14.2. Không kết nối production

Một container test không cần secret production. Nếu dùng `@DynamicPropertySource`, lấy endpoint từ container chứ không fallback sang `couchbases://production...` trong `application-test.yml`.

Tốt nhất test có guard/fail-fast với bucket prefix `_it` hoặc tên xác nhận, và CI network policy ngăn truy cập production. Một test có thao tác `deleteById`/`deleteAll` càng phải chắc chắn đang ở cluster riêng.

## 15. Những lỗi thường gặp khi khởi tạo CouchbaseContainer

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `ClassNotFound: CouchbaseContainer` | Sai module Testcontainers 1.x/2.x hoặc dependency thiếu | Dùng đúng artifact và import theo BOM |
| `ClassNotFound: DataCouchbaseTest` | Import Boot 3.x dùng trên Boot 4.x (hoặc ngược lại) | Đổi package/starter test phù hợp |
| `Could not find a valid Docker environment` | Container runtime chưa có/không được quyền | Cấp runtime cho laptop/CI, không coi test PASS |
| Container chạy nhưng SDK không kết nối | Dùng sai host/port hoặc thiếu credential | Dùng `getConnectionString/getUsername/getPassword` |
| Spring kết nối cluster ngoài ý muốn | Nhiều nguồn properties, không dùng container details | Chọn một nguồn, kiểm tra bucket/endpoint thực |
| Bucket not found | Quên `withBucket` hoặc property bucket khác | Đồng nhất bucket ở container và Spring config |
| Scope/collection not found | Chỉ tạo bucket | Provision named resources và chờ manifest |
| Query service unavailable | Chỉ bật KV | Bật QUERY/INDEX theo workload |
| `No index available` | Chưa tạo index hoặc index không phù hợp | Provision index, `EXPLAIN` và readiness |
| Index mới tạo nhưng query lỗi lúc được lúc không | Index chưa ONLINE | Dùng `watchIndexes`/poll với timeout |
| Sau save KV thấy, SQL++ không thấy | Index consistency | Dùng `REQUEST_PLUS` nếu test cần read-after-write |
| `@Service` không được inject ở slice | `@DataCouchbaseTest` giới hạn bean scan | `@Import` bean cần thiết hoặc `@SpringBootTest` |
| JSON field sai dù round-trip PASS | Writer/reader cùng ánh xạ sai | SDK đọc raw JSON independent |
| CAS test không ném lỗi | Không dùng hai snapshots hoặc thiếu `@Version` | Kiểm tra metadata và đường ghi thực |
| TTL test flaky | Dùng sleep cứng/không xét server clock và maxTTL | Poll có timeout và expiry policy |
| Test class thứ hai lỗi sau class đầu | Spring context cached nhưng container đã stop | Đồng bộ lifecycle và cache |
| Integration CI xanh dù container chưa chạy | Skip im lặng | Gate phải đánh dấu thiếu bằng chứng |
| Test chạy song song xóa dữ liệu nhau | Key trùng hoặc `deleteAll` | Dùng UUID, cleanup theo key, tách keyspace |

## 16. Bài thực hành: tạo ProductRepositoryIT đúng tài nguyên

**Bối cảnh:** dự án Spring Data Couchbase có:

~~~text
Bucket:      shop_it
Scope:       catalog
Collection:  products
Index:       ix_products_category trên category
Document key: it::product::<UUID>
~~~

Entity `Product` có:

- `@Document`, `@Scope("catalog")`, `@Collection("products")`.
- `@Id String id`, `@Version Long cas`.
- `@Field("display_name") String displayName`.
- `@Field String category` và `@Field("price_vnd") long priceVnd`.

Repository có `findById` và `findByCategory`.

### 16.1. Yêu cầu

1. Chọn đúng Gradle dependencies/imports cho Boot 4 + Testcontainers 2.
2. Tạo container có bucket `shop_it` và KV/QUERY/INDEX.
3. Dùng `@ServiceConnection` cùng `@DataCouchbaseTest`.
4. Provision `catalog.products` và secondary index `ix_products_category`.
5. Đợi index ONLINE trước khi chạy derived query.
6. Test `save`/`findById` và đối chiếu `display_name` bằng SDK raw JSON.
7. Test query theo category với mức consistency phù hợp.
8. Test hai writer dùng CAS cũ và cleanup theo key.
9. Cho biết vì sao một container đơn node chưa đủ để kiểm tra failover.

### 16.2. Lời giải gợi ý: thứ tự khởi tạo

~~~mermaid
flowchart TB
    A["JUnit @Testcontainers"] --> B["CouchbaseContainer(image)"]
    B --> C["withEnabledServices KV/QUERY/INDEX"]
    C --> D["withBucket shop_it"]
    D --> E["@ServiceConnection tới Spring Boot"]
    E --> F["createScope catalog"]
    F --> G["createCollection products"]
    G --> H["CREATE INDEX ix_products_category"]
    H --> I["watchIndexes ONLINE"]
    I --> J["Seed Product với key UUID"]
    J --> K["KV / JSON / SQL++ / CAS assertions"]
    K --> L["Cleanup đúng key"]
~~~

### 16.3. Skeleton test class

~~~java
// Import từ những ví dụ phía trên, dùng Boot 4 + Testcontainers 2.

@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=shop_it")
@Testcontainers
class ProductRepositoryIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer couchbase =
        new CouchbaseContainer(
            DockerImageName.parse("couchbase/server:community-7.2.5"))
            .withEnabledServices(
                CouchbaseService.KV,
                CouchbaseService.QUERY,
                CouchbaseService.INDEX)
            .withBucket(new BucketDefinition("shop_it"));

    @Autowired ProductRepository repository;
    @Autowired Cluster cluster;

    @Test
    void persistsMappingInNamedCollection() {
        // 1. @BeforeAll hoặc fixture đã tạo catalog.products.
        // 2. Lưu Product bằng key riêng.
        // 3. SDK đọc shop_it.catalog.products raw body.
        // 4. Kiểm tra display_name, price_vnd, document key và CAS.
        // 5. Cleanup key trong finally.
    }

    @Test
    void findsProductByCategoryWithReadyIndex() {
        // 1. Index ix_products_category ONLINE.
        // 2. Chèn các Product có category khác nhau.
        // 3. Query/repository thật, consistency được chọn rõ ràng.
        // 4. Đối chiếu kết quả đúng và cleanup.
    }
}
~~~

Đây là **skeleton có các bước cần hoàn thiện**, không phải integration test hoàn chỉnh. Trong dự án, hãy triển khai fixture provisioning theo `@BeforeAll`/test configuration có trách nhiệm rõ và dùng version API SDK được kiểm chứng.

### 16.4. Câu hỏi tự kiểm tra

1. **`CouchbaseContainer` có phải một mock server không?** Không; nó chạy Couchbase Server thật trong container.
2. **`withBucket` có tạo luôn `catalog.products` không?** Không; chỉ chuẩn bị bucket.
3. **`findById` có cần secondary index không?** Không; thường dùng KV theo key.
4. **`findByCategory` thường cần thêm service nào?** Query/Index Services và index phù hợp.
5. **`@ServiceConnection` có tự chọn `shop_it` làm bucket không?** Không; vẫn phải cấu hình bucket name cho Spring Data.
6. **Tại sao cần `getConnectionString()`?** Để SDK dùng endpoint/port mapping do container cấp.
7. **`@Container` static được start/stop khi nào?** Thường một lần cho test class qua JUnit extension.
8. **`@DataCouchbaseTest` có cần một Couchbase Server kết nối được không?** Có, nếu test thực hiện I/O thật.
9. **Có nên dùng `Thread.sleep` thay `watchIndexes` không?** Không; cần readiness thực và timeout rõ.
10. **Tại sao hai document có cùng key nhưng khác collection không xung đột?** Key được định danh trong từng keyspace.
11. **Vì sao không chỉ dùng round-trip Spring Data?** Writer và reader có thể cùng dùng sai JSON field.
12. **Kiểm thử CAS cần gì?** Hai snapshot độc lập, version metadata và assertion trạng thái cuối.
13. **Reactive cleanup có chạy nếu bỏ publisher không subscribe không?** Không nên giả định; phải subscribe/verify.
14. **Có thể mô phỏng failover production bằng một container đơn node không?** Không.
15. **Tại sao test cần UUID/namespace?** Tránh xung đột dữ liệu khi chạy song song hoặc retry.

## 17. Checklist trước khi đưa CouchbaseContainer vào CI

- [ ] Chọn phiên bản Boot/Data Couchbase/SDK/Testcontainers/Server theo compatibility matrix.
- [ ] Dùng đúng artifact/import Testcontainers 1.x hoặc 2.x.
- [ ] Pin image tag Server thay vì `latest`.
- [ ] Đảm bảo Docker runtime và quyền pull image trong CI.
- [ ] Khởi tạo `CouchbaseContainer` bằng image, services và `BucketDefinition` rõ ràng.
- [ ] Không dựa vào cổng 8091 để kết nối SDK, sử dụng connection details của container.
- [ ] Chọn `@ServiceConnection` hoặc `@DynamicPropertySource`; tránh cấu hình xung đột.
- [ ] Cấu hình `spring.data.couchbase.bucket-name` trùng bucket test.
- [ ] Provision named scopes/collections/index ngoài `withBucket`.
- [ ] Chờ cluster/bucket, collection manifest và index readiness với timeout.
- [ ] Test raw JSON, document key và CAS qua SDK để kiểm tra mapping Spring Data.
- [ ] Test KV và SQL++ riêng, xác định query scan consistency.
- [ ] Dùng hai snapshots thật để kiểm tra optimistic locking.
- [ ] Với TTL, dùng expiry ngắn và polling đồng hồ server.
- [ ] Kiểm thử reactive phải subscribe I/O và cleanup.
- [ ] Dùng key UUID, cleanup theo key thay vì `deleteAll()` trên tài nguyên dùng chung.
- [ ] Quản lý container lifecycle nhất quán với Spring context cache và test parallel.
- [ ] Không dùng một container đơn node để kết luận về multi-node failover/durability.
- [ ] CI phải báo FAIL hoặc SKIPPED rõ khi container không khởi động; không gọi đó là test PASS.

## Tài liệu tham khảo chính thức

- [Testcontainers for Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): `CouchbaseContainer`, `BucketDefinition`, kết nối SDK và tọa độ artifact.
- [Testcontainers 2.0.5 — CouchbaseContainer API](https://javadoc.io/static/org.testcontainers/testcontainers-couchbase/2.0.5/org/testcontainers/couchbase/CouchbaseContainer.html): `withEnabledServices`, `withServiceQuota`, `withBucket`, credentials.
- [Testcontainers — JUnit 5 Extension](https://java.testcontainers.org/test_framework_integration/junit_5/): lifecycle `@Testcontainers` và `@Container`.
- [Spring Boot 4 — Data Couchbase Test Slice](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@DataCouchbaseTest` và các bean data layer.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test slice và package Boot 3.x.
- [Spring Boot — Testcontainers Support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và `CouchbaseConnectionDetails`.
- [Couchbase Java SDK — Provisioning Cluster Resources](https://docs.couchbase.com/java-sdk/current/howtos/provisioning-cluster-resources.html): bucket/scope/collection/index và quản lý tài nguyên.
- [Couchbase Java SDK — Managing Connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html): connection, cluster/bucket readiness.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): `QueryOptions` và scan consistency.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Id`, `@Field`, `@Version` và converter.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): truy cập KV và query theo thuộc tính.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/reference/): kiểm thử publisher reactive.
