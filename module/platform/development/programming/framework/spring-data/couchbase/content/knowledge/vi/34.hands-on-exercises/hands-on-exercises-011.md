# Kiểm thử bằng Testcontainers và đo tải theo một mẫu truy cập cụ thể trong Spring Data Couchbase

> **Chương:** Bài thực hành  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase qua document mapping, `CouchbaseRepository`, `CouchbaseTemplate` và SQL++; vận dụng keyspace, index, TTL, CAS, giao dịch và reactive access để đảm bảo tính đúng đắn, hiệu năng và khả năng vận hành.  
> **Đích thực hành:** dùng **Testcontainers** để chạy Couchbase thật trong kiểm thử tích hợp, sau đó đo một **workload đã được định nghĩa chính xác**, không suy diễn kết quả container thành throughput production.

## 1. Mục tiêu và sản phẩm đầu ra

Sau bài này, bạn có thể:

1. Phân biệt unit test, integration test, workload experiment và capacity benchmark.
2. Khởi chạy **Couchbase Server bằng Testcontainers** trong JUnit 5, sử dụng kết nối động của Spring Boot thay vì hardcode port.
3. Viết entity `@Document`/`@Id`/`@Version` và `CouchbaseRepository` để kiểm thử KV theo ID cùng CAS.
4. Chuẩn bị dữ liệu seed **ngoài khoảng đo**, chờ Couchbase KV sẵn sàng trước khi chạy.
5. Mô tả **mẫu truy cập cố định**: 90% logical operations là KV GET, 10% là đọc–sửa–ghi có CAS.
6. Tạo **hot-set distribution** có thể tái lập: 70% requests tới 1% document IDs, còn lại tới tập khóa lạnh.
7. Chạy load nhỏ có số worker, seed random, số requests, kích thước document và cách xử lý CAS conflict xác định.
8. Đo throughput, latency p50/p95/p99, số success, optimistic-lock conflicts và other errors tách biệt.
9. Hiểu khác biệt giữa **closed-loop** (các worker chạy liên tục) và **open-loop** (tốc độ arrival đặt trước).
10. Đánh giá tính hợp lệ của số đo: startup/warm-up/GC, seed overhead, Docker CPU/memory, single-node, Index Service, retry budget.
11. Viết acceptance criteria và báo cáo có thể chạy lại, tránh kết luận quá mức từ số đo lab.
12. Mở rộng thử SQL++/GSI, `CouchbaseTemplate`, durability và reactive API mà không làm lẫn biến thí nghiệm.

### 1.1. Kết quả bàn giao mong muốn

- Một project Spring Boot có `BenchOrder`, `BenchOrderRepository`.
- Một bài `CouchbaseRepositoryIT` chạy Couchbase thật qua Testcontainers.
- Một harness đo mẫu 90/10 theo key distribution được định nghĩa.
- Bảng báo cáo các lần chạy concurrency 1/4/8/16 (hoặc cấu hình theo giới hạn máy).
- Phân tích vì sao latency tăng, CAS conflicts xuất hiện và đâu là giới hạn suy luận của lab.

**Không có số đo “được điền sẵn” trong bài.** Những số liệu hoặc cấu hình làm ví dụ không phải kết quả benchmark đã chạy.

## 2. Tình huống thực tế: trang xem chi tiết đơn hàng

Một API có hai luồng:

- `GET /orders/{id}`: trả về đơn hàng theo document ID, **đọc KV**.
- `POST /orders/{id}/view` hoặc một thao tác nội bộ: đọc document rồi tăng bộ đếm `viewCount` và ghi lại **với CAS**.

Trong thực tế, một vài đơn hàng được xem nhiều hơn hẳn các đơn còn lại. Nếu chỉ chọn IDs **đồng đều**, tải có thể trông rất nhẹ dù production có hot keys.

Bài chọn một mô hình cụ thể:

~~~text
Dataset:          1.000 documents seed
Document keys:    bench::order::0000 ... bench::order::0999
Hot set:          10 documents đầu (1% keys)
Cold set:         990 documents còn lại
Request mix:      90% GET by ID, 10% read+CAS replace
Key distribution: 70% operations vào hot set
                  30% operations vào cold set
Workers:          1, 4, 8, 16 (chạy lần lượt)
Per worker:       400 logical operations
Random seed:      cố định theo worker và run
Write retry:      0 lần trong baseline (conflict được đo)
Warm-up:          chạy riêng trước cửa sổ đo
~~~

Các thông số là **một profile giáo dục**, không phải tỷ lệ chuẩn của mọi hệ thống. Chỉ thay một yếu tố giữa hai runs nếu muốn so nguyên nhân.

### 2.1. Tại sao “đọc–sửa–ghi” là một logical write?

Một cập nhật:

~~~text
GET document + CAS
          ↓
Increment viewCount
          ↓
REPLACE document with CAS
~~~

Tức 10% **logical operations** là writes, nhưng có thể tương ứng **hai KV calls** khi không conflict. Vì vậy đừng diễn giải “90/10” là đúng 90% KV packets đọc và 10% KV packets ghi. Muốn tỷ lệ **KV commands**, phải đo từng command hoặc dùng workload khác.

### 2.2. Tại sao chọn CAS?

Khi hai request cùng đọc `viewCount=5`, cả hai muốn ghi 6. Nếu dùng `upsert` không điều kiện, một increment có thể bị mất. Với `@Version`, chỉ một replace với CAS cũ thành công; request kia nhận conflict và được đếm riêng. Bài đo **conflict có chủ đích** để hiểu contention, không che nó bằng retry vô hạn.

### 2.3. Những thứ không nằm trong profile baseline

- Không có HTTP serialization/gateway/authentication overhead.
- Không có SQL++ query hoặc GSI trong pha KV chính.
- Không đặt TTL để tránh document tự expire trong lúc đo.
- Không bật durability `MAJORITY` trên cluster đơn nút chỉ để mô phỏng HA.
- Không có multi-document transaction, failover, rebalance hoặc load production thật.
- Không nạp test data trong khoảng đo.

Một benchmark hữu ích phải khai báo cả **những gì nó không đo**.

## 3. Thế nào là integration test và benchmark hợp lệ?

| Kiểu | Hệ thống dưới kiểm thử | Câu hỏi | Có thể kết luận gì? |
|---|---|---|---|
| **Unit test** | Mock repository/clock | Service map dữ liệu đúng không? | Logic thuần và behavior của mock |
| **Integration test Testcontainers** | Couchbase Server thật trong container | Mapping, KV insert/get, CAS chạy đúng không? | Hợp đồng kỹ thuật với image/version đã chọn |
| **Micro-load lab** | Cùng container + JVM với tải kiểm soát | p99 và conflict thay đổi thế nào khi tăng workers? | Xu hướng trong điều kiện lab, không phải capacity |
| **Performance test staging** | Kiến trúc gần production, hạ tầng riêng | Có đạt SLO dưới tải giống thật? | Bằng chứng hiệu năng trong staging |
| **Production observability** | Traffic thật, chính sách giám sát | p99/error theo giờ cao điểm? | SLI thực tế; không chủ động tạo fault nguy hiểm |

**Testcontainers chạy Couchbase thật, nhưng không tạo production topology.** Một container Data node không có replicas là môi trường tuyệt vời để kiểm tra API, không đủ để cam kết RPO/RTO, throughput đa node hoặc durability khi failover.

### 3.1. “Tự động khởi chạy” không đồng nghĩa “luôn ổn định”

Couchbase startup kéo dài hơn nhiều mock DB: bootstrap cluster, tạo bucket, mở Data Service, chuẩn bị ports và SDK cluster config. Nếu chạy test trước khi Data Service sẵn sàng, timeout đầu tiên không phản ánh hiệu năng steady-state.

### 3.2. Đo load trên cùng Docker host có nguồn nhiễu

CPU scheduler, memory pressure, page cache, Docker Desktop/WSL2, disk filesystem, JVM warm-up/GC và việc kéo image có thể thay đổi latency. Một con số p99 chỉ có nghĩa khi gắn với **host, image, JVM, heap, số workers, số samples, time window**.

## 4. Thiết kế kiến trúc bài lab

~~~mermaid
flowchart LR
    JUnit["JUnit 5<br/>Testcontainers"]
    Container["CouchbaseContainer<br/>ephemeral DB instance"]
    Boot["Spring Boot Test Context"]
    Repo["BenchOrderRepository<br/>Spring Data"]
    Driver["Load Driver<br/>90% GET / 10% CAS"]
    KV["Couchbase Data Service<br/>bench_lab._default._default"]
    Metric["Per-op samples<br/>latency / outcomes"]
    JUnit --> Container
    Container -->|"Dynamic service connection"| Boot
    Boot --> Repo
    Driver --> Repo --> KV
    Driver --> Metric
~~~

Ở đường chính, dữ liệu sống trong **default scope/default collection của bucket `bench_lab`**. Cách này giảm biến cấu hình để tập trung vào performance experiment. Cuối bài có bước mở rộng tạo scope/collection riêng khi cần kiểm tra mapping tương đương production.

### 4.1. Vì sao chọn `_default._default` lúc đầu?

Với Couchbase, `Bucket` chứa scopes và collections. Testcontainers `withBucket(...)` tạo bucket; nó **không mặc định tạo mọi scope/collection custom** mà bạn tưởng tượng. Nếu đặt `@Scope("sales")` và `@Collection("orders")` ngay trong entity, phải provision hai objects đó và đợi manifest propagation; nếu không, test sẽ lỗi `CollectionNotFound`.

Sử dụng default collection cho baseline, rồi chỉ đổi keyspace ở bài mở rộng riêng sau khi chứng minh CRUD đã đúng.

### 4.2. Dùng một client/connection pool, không kết nối lại theo operation

Một lỗi benchmark thường gặp:

~~~java
// SAI: không tạo Cluster mới cho mỗi GET.
for (int i = 0; i < n; i++) {
    Cluster cluster = Cluster.connect(...);
    // ...
}
~~~

Việc bootstrap SDK tạo nhiều IO threads/network connections và bóp méo latency. Spring Boot auto-configured `Cluster`/Repository nên được tái sử dụng suốt test.

## 5. Công cụ và điều kiện chuẩn bị

- JDK tương thích với Spring Boot version, ví dụ Java 21.
- Maven/Gradle và Docker-API-compatible runtime đang chạy.
- Docker đủ RAM/CPU/disk; Couchbase image khá lớn.
- Spring Boot với `spring-boot-starter-data-couchbase` và `spring-boot-starter-test`.
- Testcontainers Couchbase module và JUnit 5 integration.
- Nếu dùng `@ServiceConnection`: cần `spring-boot-testcontainers` phù hợp Spring Boot version.
- Không cần Couchbase cài sẵn ở host; Testcontainers tạo container tạm.

**Địa chỉ kết nối sẽ có mapped ports ngẫu nhiên**; không điền `localhost:8091` hoặc `127.0.0.1:11210` cố định khi Testcontainers đã tự cấp ports.

### 5.1. Chốt phiên bản để kết quả tái lập

Ví dụ tại thời điểm viết, Testcontainers Java 2.x có artifact:

~~~text
org.testcontainers:testcontainers-couchbase
org.testcontainers:testcontainers-junit-jupiter
~~~

**Lưu ý:** Ở Testcontainers 1.x, module có artifact `org.testcontainers:couchbase` và `org.testcontainers:junit-jupiter`. Không trộn tọa độ 1.x với BOM 2.x; ví dụ bài dùng cách đặt tên 2.x. Hãy khóa **một BOM Testcontainers** cùng một Spring Boot BOM tương thích.

### 5.2. Maven: Spring Initializr + test dependencies

Trong `pom.xml` do Spring Initializr sinh, thêm dependencies (fragment):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-couchbase</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-couchbase</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Version Testcontainers được chọn qua compatible BOM (ví dụ 2.0.x), không thêm version 1.x vào từng dependency. Nếu Spring Boot BOM chọn một Testcontainers major khác, import BOM phù hợp có chủ đích và xác minh dependency tree. Tài liệu này **không phải một pom.xml đầy đủ**; parent, compiler, surefire/failsafe do project đang dùng cung cấp.

Ví dụ `dependencyManagement` cho **Testcontainers 2.0.5** (khi parent Spring Boot chưa quản lý đúng major/artifact names của Testcontainers 2.x):

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>2.0.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Chọn cùng một Testcontainers 2.x cho Couchbase và JUnit, kiểm tra `mvn dependency:tree` khi thực hành. Nếu một Spring Boot parent khác quản lý `org.testcontainers` 1.x, phải kiểm tra thứ tự BOM/overrides và version thực resolve; không để module 2.x kéo lẫn core 1.x. `2.0.5` là phiên bản minh họa đã công bố, không có nghĩa đây luôn là phiên bản mới nhất khi người học chạy.

### 5.3. Kiểm tra runtime trước khi chạy

- Docker daemon khởi động, người chạy tests có quyền sử dụng.
- Image Couchbase được phép tải và license/edition phù hợp lab.
- RAM/disk đủ cho container và JVM.
- Không đặt `TESTCONTAINERS_RYUK_DISABLED=true` hay bật container reuse chỉ để né lỗi cleanup.
- CI worker cho phép Docker socket/container lifecycle; nếu không, dùng một staging cluster được cấp phép theo quy trình khác, không giả Testcontainers đã chạy.
- Không chạy micro-load cùng builds nặng khác trên một host nếu muốn so p99.

## 6. Cấu trúc project và dữ liệu

~~~text
src/main/java/com/example/cbbench/
  CouchbaseBenchApplication.java
  BenchOrder.java
  BenchOrderRepository.java
src/test/java/com/example/cbbench/
  BenchSeed.java
  AccessProfile.java
  ReportPrinter.java
  CouchbaseRepositoryIT.java
  AccessPatternLoadIT.java
  AccessPatternRunner.java
src/test/resources/
  application-test.yml
~~~

Đặt `package com.example.cbbench;` cho Java files. `BenchSeed`, `AccessProfile`, `ReportPrinter` và `AccessPatternRunner` thuộc **test sources**, không đóng gói vào runtime service. Test classes được tách để có **smoke tests** chạy mặc định khi Docker khả dụng, còn **load test** cần cờ opt-in.

### 6.1. Entity với key và CAS

~~~java
package com.example.cbbench;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class BenchOrder {
    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String state;
    private long viewCount;
    private String padding;

    public BenchOrder() {}

    public BenchOrder(
            String id, String tenantId,
            String state, long viewCount, String padding) {
        this.id = id;
        this.tenantId = tenantId;
        this.state = state;
        this.viewCount = viewCount;
        this.padding = padding;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) {
        this.version = version;
    }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    public String getState() { return state; }
    public void setState(String state) { this.state = state; }

    public long getViewCount() { return viewCount; }
    public void setViewCount(long viewCount) {
        this.viewCount = viewCount;
    }

    public String getPadding() { return padding; }
    public void setPadding(String padding) {
        this.padding = padding;
    }
}
~~~

### 6.2. Repository

~~~java
package com.example.cbbench;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface BenchOrderRepository
        extends CouchbaseRepository<BenchOrder, String> {
}
~~~

`findById(id)` là KV lookup, không cần SQL++/GSI. `save` với entity mới có `@Version=null` được Spring Data Couchbase xác định là new state để insert; entity đã được đọc có CAS thì dùng replace với optimistic locking. Bài sẽ xác minh semantics này qua integration test.

### 6.3. Application

~~~java
package com.example.cbbench;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CouchbaseBenchApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            CouchbaseBenchApplication.class, args);
    }
}
~~~

### 6.4. Config test

~~~yaml
# src/test/resources/application-test.yml
spring:
  data:
    couchbase:
      bucket-name: bench_lab
  couchbase:
    env:
      timeouts:
        connect: 60s
        key-value: 10s
~~~

Không đặt `spring.couchbase.connection-string` hoặc username/password tĩnh trong test profile nếu `@ServiceConnection` quản lý các connection details. Tên bucket vẫn phải được cung cấp cho Spring Data. Các timeout ở đây là **test setup** để giảm lỗi bootstrap trên máy yếu; không thay đổi bừa timeout nhằm che lỗi performance.

## 7. Khởi động CouchbaseContainer theo JUnit 5

~~~java
package com.example.cbbench;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.ActiveProfiles;
import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Bucket;

@SpringBootTest(properties = {
    "spring.data.couchbase.bucket-name=bench_lab"
})
@ActiveProfiles("test")
@Testcontainers(disabledWithoutDocker = true)
class CouchbaseRepositoryIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer couchbase =
        new CouchbaseContainer(DockerImageName.parse(
            "couchbase/server:7.6.6"))
            .withBucket(new BucketDefinition("bench_lab"));

    @Autowired BenchOrderRepository repository;
    @Autowired Cluster cluster;

    @Test
    void repositoryWorksAgainstRealCouchbase() {
        Bucket bucket = cluster.bucket("bench_lab");
        bucket.waitUntilReady(Duration.ofSeconds(90));

        String id = "it::" + UUID.randomUUID();
        BenchOrder doc = new BenchOrder(
            id, "LAB", "CREATED", 0, "payload"
        );

        try {
            repository.save(doc);

            BenchOrder loaded =
                repository.findById(id).orElseThrow();

            assertEquals("CREATED", loaded.getState());
            assertNotNull(loaded.getVersion());

            Long versionBeforeUpdate = loaded.getVersion();
            loaded.setViewCount(1);
            repository.save(loaded);

            BenchOrder next =
                repository.findById(id).orElseThrow();

            assertEquals(1, next.getViewCount());
            assertNotEquals(
                versionBeforeUpdate, next.getVersion());
        } finally {
            repository.findById(id).ifPresent(
                repository::delete
            );
        }
    }
}
~~~

### 7.1. `@ServiceConnection` làm gì?

Spring Boot nhận `CouchbaseContainer` và tạo connection details cho auto-configured Couchbase beans. Nhờ vậy test không cần hardcode mapped port, username hay password. `@ServiceConnection` cần `spring-boot-testcontainers`; Spring Boot version quá cũ không có tính năng này thì dùng `@DynamicPropertySource` thay thế theo tài liệu phù hợp.

### 7.2. Container life cycle

- Trường `static @Container` được khởi động **một lần trong test class**, không phải mỗi test method.
- Không dùng `static` nếu muốn mỗi method có container riêng; cái giá là startup rất chậm.
- `@Testcontainers(disabledWithoutDocker=true)` có thể skip khi không tìm thấy Docker, nhưng không thay báo cáo rằng một môi trường CI đã kiểm thử thực tế.
- Không bật test method chạy song song trên cùng container khi state/cleanup chưa cô lập: Testcontainers Jupiter extension được tài liệu kiểm chứng chủ yếu với execution tuần tự.
- Không bật container reuse mặc định trên CI: nguy cơ rò state giữa test runs.

### 7.3. Một điều cần kiểm tra với API cụ thể của dự án

Trong một số Spring Data versions, entity truyền vào `save` có thể được cập nhật CAS tại chỗ hoặc method trả entity với CAS mới. Nếu dựa vào bản trả, hãy dùng:

~~~java
BenchOrder saved = repository.save(loaded);
BenchOrder reloaded = repository.findById(id).orElseThrow();
assertEquals(saved.getViewCount(), reloaded.getViewCount());
~~~

**Không tự giả định** `loaded.version` luôn giữ nguyên sau `save`, vì mutation may cập nhật instance. Khi cần test CAS stale, lưu bản token cũ **trước** mutation và tạo một writer khác dựa trên token đó, không dựa vào object có thể bị update bởi framework.

## 8. Test optimistic locking thật, không chỉ gọi `save` hai lần

Đặt method `@Test` sau **bên trong class `CouchbaseRepositoryIT` ở mục 7**, không tạo một phương thức top-level độc lập.

~~~java
@Test
void staleWriterMustNotOverwriteLatest() {
    String id = "it::cas::" + UUID.randomUUID();
    repository.save(new BenchOrder(
        id, "LAB", "CREATED", 0, "padding"
    ));

    try {
        BenchOrder writerA =
            repository.findById(id).orElseThrow();
        BenchOrder writerB =
            repository.findById(id).orElseThrow();

        // Hai entity khác nhau có cùng CAS cũ.
        writerA.setViewCount(1);
        repository.save(writerA);

        writerB.setViewCount(1);
        assertThrows(
            org.springframework.dao.OptimisticLockingFailureException.class,
            () -> repository.save(writerB)
        );

        assertEquals(
            1,
            repository.findById(id)
                .orElseThrow().getViewCount()
        );
    } finally {
        repository.findById(id).ifPresent(repository::delete);
    }
}
~~~

Nếu Spring Data/SDK version dịch CAS exception thành lớp khác, cần đối chiếu `cause chain` trong integration test và sửa assertion đúng bản phát hành. **Đừng** thay lỗi CAS bằng `upsert` để làm test xanh; điều đó xóa yêu cầu tránh lost update.

### 8.1. Tại sao vẫn chưa đo tải?

Hai tests trên kiểm tra mapping, KV operation, CAS và container bootstrap. Chúng chưa có warm-up, distribution, concurrency levels và số mẫu đủ để đo p95/p99. Dùng tên `IT` thay vì “PerformanceBenchmark” cho các tests chức năng.

## 9. Provision scope/collection riêng: bài mở rộng cấu hình

Sau khi baseline default collection hoạt động, có thể mở rộng:

~~~java
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.manager.collection.CollectionManager;

Bucket bucket = cluster.bucket("bench_lab");
bucket.waitUntilReady(Duration.ofSeconds(90));

CollectionManager manager = bucket.collections();
manager.createScope("sales");
manager.createCollection("sales", "orders");
~~~

Đoạn trên **chỉ chạy một lần** trong setup khi keyspace chưa có. Nếu chạy lại có thể gặp `ScopeExistsException`/`CollectionExistsException`, nên quản lý idempotent setup theo API/version thực tế. Đợi collection manifest được SDK cập nhật trước khi seed; một `CollectionNotFound` tức thì sau DDL không luôn là bug của Repository.

Mapping cho một **entity thay thế**:

~~~java
@Document
@Scope("sales")
@Collection("orders")
class BenchOrder {
    // Fields như mục 6; chỉ dùng khi custom keyspace đã sẵn sàng.
}
~~~

**Không tạo hai classes cùng tên trong project.** Nếu dùng custom keyspace, mọi SDK direct calls phải trỏ tới `bucket.scope("sales").collection("orders")`, và test phải kiểm tra cấu hình thật. Đừng suy từ bucket name rằng index Query Service tự xuất hiện.

## 10. Cố định profile truy cập trước khi lấy kết quả

| Đặc tính | Baseline của bài | Vì sao khóa giá trị? |
|---|---|---|
| Operation mix | 90% GET, 10% CAS update | Tránh so profile khác nhau |
| Seed records | 1.000 | Kích thước keyspace |
| Key prefix | `bench::order::` | Không đụng test khác |
| Hot records | 10 | Tranh chấp tập trung |
| Hot traffic share | 70% | Không phải uniform |
| Cold records | 990 | Tạo phân phối lệch |
| Concurrency | 1/4/8/16 workers | Đường cong throughput–latency |
| Operations/worker | 400 | Tổng op tăng theo concurrency |
| Payload body | `padding` dài 256 ký tự | Giữ serialization tương tự |
| CAS retry | Không trong baseline | Đo conflict thay vì che nó |
| Warm-up | Ngoài cửa sổ measured | Tránh JIT/bootstrap |
| Time source | `System.nanoTime()` | Đo elapsed trong cùng JVM |
| Dataset reuse | Reset trạng thái trước từng run | Giữ state tương đương |
| Docker image | Pin tag/digest | Giảm khác biệt server version |
| Environment | JVM/CPU/RAM/disk ổn định | Giảm nhiễu đo |

### 10.1. Các giả định cần viết thành lời

- Bản ghi được seed trước mọi lần đo.
- GET theo ID là `repository.findById(id)`, không phải SQL++.
- Một write gồm `findById` + sửa counter + `repository.save` có CAS.
- Tỷ lệ GET/UPDATE tính trên **logical operations được gửi**, không bảo đảm đúng bằng packet mix server quan sát.
- Hot traffic lấy ngẫu nhiên theo xác suất; mỗi run hữu hạn có thể lệch vài phần trăm so với 70%.
- Mỗi worker có seed xác định, nhưng **interleaving của threads không deterministic**, nên tỷ lệ CAS conflict vẫn biến thiên.
- Load generator và Couchbase container có thể chung một host; CPU contention ảnh hưởng phép đo.

## 11. Seed dữ liệu tách khỏi cửa sổ benchmark

Một helper điền 1.000 documents:

~~~java
package com.example.cbbench;

import java.util.Locale;
import org.springframework.stereotype.Component;

@Component
public class BenchSeed {
    public static final int RECORDS = 1_000;
    public static final int HOT_KEYS = 10;

    private final BenchOrderRepository repository;

    public BenchSeed(BenchOrderRepository repository) {
        this.repository = repository;
    }

    public static String key(int index) {
        if (index < 0 || index >= RECORDS) {
            throw new IllegalArgumentException("Bad index: " + index);
        }
        return "bench::order::" +
            String.format(Locale.ROOT, "%04d", index);
    }

    public void resetAndSeed() {
        String padding = "X".repeat(256);

        // Bài học dùng dữ liệu giả; không seed PII thật.
        for (int i = 0; i < RECORDS; i++) {
            String id = key(i);
            // Reset state cho lần chạy tiếp theo.
            // Lab dùng upsert/replace trong giai đoạn SETUP;
            // KHÔNG tính thao tác này vào latency benchmark.
            var value = new BenchOrder(
                id, "LAB", "CREATED", 0, padding
            );
            // Để reset đúng với @Version, xóa key
            // test đã có rồi tạo lại ở giai đoạn SETUP.
            repository.findById(id).ifPresent(repository::delete);
            repository.save(value);
        }
    }
}
~~~

### 11.1. Vì sao seed không được tính vào throughput GET?

Giai đoạn seed có đặc tính hoàn toàn khác: inserts/deletes, cache cold, bucket memory allocation, index updates (nếu có). Nếu đưa vào khoảng đo rồi tuyên bố throughput của GET, số đo bị pha trộn và không còn đại diện cho profile đã định.

### 11.2. Không dùng cleanup toàn bucket bừa bãi

`repository.deleteAll()` có thể dùng query SQL++ hoặc đòi index, và nếu trỏ nhầm bucket sẽ nguy hiểm. Helper chỉ xóa **1.000 keys theo prefix test đã biết** trong **container do Testcontainers sở hữu**. Không đưa helper này sang production service hoặc chạy trên shared bucket.

### 11.3. `@Version` trong seed và conflict

Helper tạo entity mới sau delete để `version=null`. Trong quá trình đo, update được thực hiện trên entity vừa đọc có `@Version` hợp lệ. Nếu `save` xảy ra với bản stale thì cần ghi nhận conflict, không dùng một `upsert` không kiểm soát để né nó.

## 12. Định nghĩa load driver: đo đúng logical operation

Ta viết một driver nhỏ chạy trong `src/test/java`, không thêm một thư viện benchmark nặng cho bài học. Driver sẽ:

1. Tạo một nhóm worker threads cố định.
2. Chờ mọi worker sẵn sàng rồi mở cùng một `CountDownLatch`.
3. Mỗi worker chạy số logical operations xác định.
4. Chọn GET hay UPDATE theo xác suất 90/10 với `SplittableRandom`.
5. Chọn hot/cold key theo xác suất 70/30 với **seed cố định**.
6. Gọi đúng Repository đang được Spring inject.
7. Đo elapsed time bằng `System.nanoTime()`.
8. Phân loại `SUCCESS`, `CAS_CONFLICT` và `ERROR`.
9. Thu latency samples vào danh sách **riêng của worker** để tránh lock chung trong đường đo.
10. Dừng đồng hồ tổng sau khi tất cả futures hoàn thành và in kết quả **sau cửa sổ đo**.

### 12.1. Profile và sample record

~~~java
package com.example.cbbench;

import java.util.List;

public record AccessProfile(
        int workers,
        int operationsPerWorker,
        int readPercent,
        int hotPercent,
        long seed
) {
    public AccessProfile {
        if (workers <= 0 || operationsPerWorker <= 0) {
            throw new IllegalArgumentException(
                "Workers/operations must be positive");
        }
        if (readPercent < 0 || readPercent > 100
                || hotPercent < 0 || hotPercent > 100) {
            throw new IllegalArgumentException(
                "Percent must be between 0 and 100");
        }
    }

    public enum Kind { GET, CAS_UPDATE }
    public enum Outcome { SUCCESS, CAS_CONFLICT, ERROR }

    public record Sample(
        Kind kind,
        Outcome outcome,
        long latencyNanos
    ) {}

    public record Report(
        AccessProfile profile,
        long wallNanos,
        List<Sample> samples
    ) {}
}
~~~

`readPercent=90` và `hotPercent=70` là **xác suất chọn**. Số GET và hot keys thực tế của 400 operations/worker có thể lệch một chút; luôn báo cáo số lượng **đã quan sát**, không tuyên bố 90.000% tuyệt đối.

### 12.2. Chọn hot key đúng cách

~~~java
private static String sampleKey(
        java.util.SplittableRandom random,
        int hotPercent) {

    // 70% operations tới 10 / 1000 keys.
    boolean hot = random.nextInt(100) < hotPercent;

    int index = hot
        ? random.nextInt(BenchSeed.HOT_KEYS)
        : BenchSeed.HOT_KEYS +
            random.nextInt(
                BenchSeed.RECORDS - BenchSeed.HOT_KEYS);

    return BenchSeed.key(index);
}
~~~

Không dùng `new Random()` cho mỗi request vì seed mặc định không ổn định và có thể làm nhiễu phép đo. `SplittableRandom` theo từng worker cho chuỗi chọn IDs lặp lại giữa runs cùng config (nhưng thứ tự các thread thực thi vẫn phụ thuộc scheduler).

## 13. AccessPatternRunner: chạy profile closed-loop

Đây là implementation chính của bộ đo:

~~~java
package com.example.cbbench;

import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.couchbase.client.core.error.CasMismatchException;
import org.springframework.dao.OptimisticLockingFailureException;

import static com.example.cbbench.AccessProfile.Kind;
import static com.example.cbbench.AccessProfile.Outcome;
import static com.example.cbbench.AccessProfile.Report;
import static com.example.cbbench.AccessProfile.Sample;

public final class AccessPatternRunner {
    private final BenchOrderRepository repository;

    public AccessPatternRunner(BenchOrderRepository repository) {
        this.repository = repository;
    }

    public Report run(AccessProfile profile) throws Exception {
        ExecutorService pool =
            Executors.newFixedThreadPool(profile.workers());

        CountDownLatch ready =
            new CountDownLatch(profile.workers());
        CountDownLatch start = new CountDownLatch(1);
        List<Future<List<Sample>>> futures =
            new ArrayList<>();

        try {
            for (int worker = 0; worker < profile.workers();
                    worker++) {
                final int workerIndex = worker;

                Callable<List<Sample>> task = () -> {
                    SplittableRandom random =
                        new SplittableRandom(
                            profile.seed() +
                            0x9E3779B97F4A7C15L * workerIndex);

                    List<Sample> samples =
                        new ArrayList<>(
                            profile.operationsPerWorker());

                    ready.countDown();
                    start.await();

                    for (int i = 0;
                            i < profile.operationsPerWorker();
                            i++) {
                        Kind kind =
                            random.nextInt(100) < profile.readPercent()
                                ? Kind.GET : Kind.CAS_UPDATE;

                        String id = sampleKey(
                            random, profile.hotPercent());

                        long begin = System.nanoTime();
                        Outcome outcome = Outcome.ERROR;

                        try {
                            if (kind == Kind.GET) {
                                repository.findById(id)
                                    .orElseThrow();
                            } else {
                                BenchOrder doc =
                                    repository.findById(id)
                                        .orElseThrow();

                                doc.setViewCount(
                                    doc.getViewCount() + 1);

                                // @Version CAS: một writer
                                // stale sẽ bị từ chối.
                                repository.save(doc);
                            }
                            outcome = Outcome.SUCCESS;
                        } catch (
                            OptimisticLockingFailureException
                            | CasMismatchException conflict
                        ) {
                            outcome = Outcome.CAS_CONFLICT;
                        } catch (RuntimeException failure) {
                            // Bản demo gộp các lỗi khác.
                            // Test thực phải giữ exception type/count
                            // trong một collector có giới hạn.
                            outcome = Outcome.ERROR;
                        } finally {
                            samples.add(new Sample(
                                kind,
                                outcome,
                                System.nanoTime() - begin));
                        }
                    }
                    return samples;
                };
                futures.add(pool.submit(task));
            }

            ready.await();
            long wallStart = System.nanoTime();
            start.countDown();

            List<Sample> merged = new ArrayList<>();
            for (Future<List<Sample>> future : futures) {
                merged.addAll(future.get());
            }

            long elapsed = System.nanoTime() - wallStart;

            return new Report(profile, elapsed, merged);
        } finally {
            pool.shutdownNow();
            // Tránh rò threads khi test fail.
            pool.awaitTermination(15, TimeUnit.SECONDS);
        }
    }

    private static String sampleKey(
            SplittableRandom random, int hotPercent) {
        boolean hot = random.nextInt(100) < hotPercent;

        int index = hot
            ? random.nextInt(BenchSeed.HOT_KEYS)
            : BenchSeed.HOT_KEYS
                + random.nextInt(
                    BenchSeed.RECORDS - BenchSeed.HOT_KEYS);

        return BenchSeed.key(index);
    }
}
~~~

### 13.1. Điều gì được đo và không được đo?

Đo bằng `nanoTime()` từ ngay trước Repository operation đến khi có success/error. Nó gồm Spring Data conversion, SDK network, Data Service và các bước read/replace cho update. Nó **không** gồm HTTP/gateway, serialization của REST Controller hoặc thời gian request chờ trong queue ngoài executor.

Một `CAS_UPDATE` thực chất có **hai KV round trips**; vì vậy p99 UPDATE không thể so trực tiếp với p99 GET như hai commands tương đương. Mỗi latency là **logical operation end-to-end**, không phải per-request KV socket latency.

### 13.2. Vì sao driver là closed-loop?

Mỗi thread **đợi kết quả op hiện tại rồi gửi op kế tiếp**, nên số request outstanding không vượt số workers. Khi cluster chậm, arrival rate tự giảm theo latency. Kiểu này phù hợp khám phá quan hệ concurrency–throughput nhỏ trong lab nhưng có nguy cơ **coordinated omission** khi bạn dùng nó để hứa SLO theo tốc độ người dùng đến cố định.

Muốn mô phỏng 500 requests/s độc lập latency, cần **open-loop/rate-controlled generator** với queueing, max in-flight và cách ghi nhận cả dropped/timeouts; không nên thay một biến rồi cho rằng kết quả ngang nhau.

### 13.3. Exception không được rơi khỏi mẫu đo

`Sample` được ghi trong `finally` ngay cả khi operation lỗi. Nếu bỏ tất cả timeout/CAS conflicts ra khỏi histogram, p99 thành công có thể đẹp lên đúng lúc hệ thống suy giảm. Báo cáo cần cả percentile của **tất cả attempts** và tỷ lệ outcome.

Trong bài demo, mọi `RuntimeException` không thuộc CAS được gộp `ERROR` để giữ code gọn. Khi thực hành thật, mở rộng thành thống kê theo exception class (`DocumentNotFound`, `UnambiguousTimeout`, `AmbiguousTimeout`, durability errors, connection error) bằng counters giới hạn; tránh log full stacktrace cho hàng nghìn requests.

### 13.4. Vì sao `Future.get()` không có timeout trong bản rút gọn?

Driver dựa vào SDK-level timeouts. Nếu một worker bị block vì lỗi harness hoặc dependency ngoài SDK, `Future.get()` có thể chờ lâu. Trong suite nghiêm túc, thêm **deadline tổng** hoặc `Future.get(timeout, unit)`, cancel và xuất partial report. Không dùng kết quả partial rồi giả có đủ samples của profile.

## 14. Tính throughput và percentiles có ý nghĩa

Percentiles cần được tính từ **mẫu latency của chính nhóm được đo**, không phải trung bình p99 của từng thread. Một cách đơn giản trong lab là gom vào `long[]` rồi sort.

~~~java
package com.example.cbbench;

import java.util.Locale;

import static com.example.cbbench.AccessProfile.Kind;
import static com.example.cbbench.AccessProfile.Outcome;
import static com.example.cbbench.AccessProfile.Report;

public final class ReportPrinter {
    private ReportPrinter() {}

    public static void print(Report report) {
        var samples = report.samples();
        long get = samples.stream()
            .filter(s -> s.kind() == Kind.GET).count();
        long writes = samples.size() - get;
        long successes = samples.stream()
            .filter(s -> s.outcome() == Outcome.SUCCESS).count();
        long conflicts = samples.stream()
            .filter(s -> s.outcome() == Outcome.CAS_CONFLICT).count();
        long errors = samples.stream()
            .filter(s -> s.outcome() == Outcome.ERROR).count();

        double seconds =
            report.wallNanos() / 1_000_000_000.0;

        System.out.printf(Locale.ROOT,
            "threads=%d ops=%d seconds=%.3f "
              + "throughput=%.1fops/s GET=%d UPDATE=%d "
              + "success=%d casConflict=%d error=%d%n",
            report.profile().workers(),
            samples.size(),
            seconds,
            seconds == 0 ? 0 : samples.size() / seconds,
            get, writes, successes, conflicts, errors
        );

        printLatencies("GET", report, Kind.GET);
        printLatencies("CAS_UPDATE", report, Kind.CAS_UPDATE);
    }

    private static void printLatencies(
            String name, Report report, Kind kind) {
        long[] all = report.samples().stream()
            .filter(s -> s.kind() == kind)
            .mapToLong(s -> s.latencyNanos())
            .sorted().toArray();

        long[] successOnly = report.samples().stream()
            .filter(s -> s.kind() == kind)
            .filter(s -> s.outcome() == Outcome.SUCCESS)
            .mapToLong(s -> s.latencyNanos())
            .sorted().toArray();

        printRow(name + "-all-attempts", all);
        printRow(name + "-success-only", successOnly);
    }

    private static void printRow(String label, long[] ns) {
        if (ns.length == 0) {
            System.out.println(label + " n=0");
            return;
        }
        System.out.printf(Locale.ROOT,
            "%s n=%d p50=%.2fms p95=%.2fms "
              + "p99=%.2fms max=%.2fms%n",
            label, ns.length,
            millis(nearestRank(ns, 0.50)),
            millis(nearestRank(ns, 0.95)),
            millis(nearestRank(ns, 0.99)),
            millis(ns[ns.length - 1])
        );
    }

    // Nhận sorted array, nearest-rank percentile.
    private static long nearestRank(long[] sorted, double p) {
        int index = Math.max(0,
            (int) Math.ceil(p * sorted.length) - 1);
        return sorted[index];
    }

    private static double millis(long nanoseconds) {
        return nanoseconds / 1_000_000.0;
    }
}
~~~

### 14.1. Nearest-rank là một quy ước, không phải “p99 duy nhất”

Các công cụ khác có interpolation, HDR histogram, t-digest hoặc cách tính quantile khác. Khi so bảng số liệu, **đặt cùng phép ước lượng**; đối với mẫu nhỏ, p99 có biến động cao. Histogram production thường dùng HdrHistogram hoặc Micrometer+tracing/metrics phù hợp để giảm overhead và ghi nhận phân phối tốt hơn.

### 14.2. Tại sao in cả "all attempts" và "success only"?

- **All attempts:** phản ánh latency caller phải chịu, kể cả các lần xung đột hoặc lỗi.
- **Success only:** cho biết thời gian của các tác vụ hoàn tất thành công.
- **Conflict/error counts:** cho biết bao nhiêu công việc đã không hoàn tất theo yêu cầu nghiệp vụ.

Nếu tăng số workers làm 30% updates bị CAS conflict, không thể khoe throughput tổng tăng mà bỏ qua số thao tác nghiệp vụ bị từ chối.

### 14.3. Throughput tổng không phải throughput thành công

`samples.size()/seconds` đo **attempt throughput**. Một chỉ số thứ hai cần tính là:

~~~text
successful logical ops per second = successes / elapsedSeconds

conflict rate = conflicts / attempted CAS updates
error rate = errors / all logical attempts
~~~

Một profile có 10.000 attempts/s nhưng 5.000 errors/s không thể tự gọi là 10.000 successful operations/s.

## 15. Runbook chạy micro-load opt-in trên Testcontainers

Tạo một test class **khác** với smoke test, chỉ chạy khi đã bật cờ `RUN_CB_BENCH=true`. Cần đủ CPU/RAM và không chạy song song test khác trên cùng container.

~~~java
package com.example.cbbench;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.ActiveProfiles;
import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest(properties = {
    "spring.data.couchbase.bucket-name=bench_lab"
})
@ActiveProfiles("test")
@Testcontainers(disabledWithoutDocker = true)
@EnabledIfEnvironmentVariable(
    named = "RUN_CB_BENCH",
    matches = "true"
)
class AccessPatternLoadIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer couchbase =
        new CouchbaseContainer(DockerImageName.parse(
            "couchbase/server:7.6.6"))
            .withBucket(new BucketDefinition("bench_lab"));

    @Autowired BenchOrderRepository repository;
    @Autowired BenchSeed seed;

    @Test
    void readHeavyHotKeyProfile() throws Exception {
        var runner = new AccessPatternRunner(repository);

        for (int threads : new int[] {1, 4, 8, 16}) {
            // Cửa sổ PREPARE, ngoài latency measurement.
            seed.resetAndSeed();

            // Warm-up nhỏ, không lấy sample làm kết quả.
            runner.run(new AccessProfile(
                threads, 100, 90, 70, 20261125L));

            // Xóa hậu quả writes warm-up; reset ngoài đo.
            seed.resetAndSeed();

            AccessProfile profile = new AccessProfile(
                threads, 400, 90, 70, 20261125L
            );

            var report = runner.run(profile);
            ReportPrinter.print(report);

            assertEquals(
                threads * 400, report.samples().size());

            // Kiểm tra dữ liệu vẫn có cấu trúc hợp lệ.
            // Việc này thực hiện SAU cửa sổ đo.
            assertEquals(
                "CREATED",
                repository.findById(BenchSeed.key(0))
                    .orElseThrow().getState()
            );
        }
    }
}
~~~

### 15.1. Vì sao `RUN_CB_BENCH` phải là opt-in?

Một micro-load test không nên tự chạy mỗi lần developer gõ `mvn test` trong CI chung; nó tốn tài nguyên và kết quả không ổn định khi host bận. Dùng profile/tag Maven/Failsafe hoặc cờ môi trường để tách khỏi functional suite. Tùy hệ thống build, class `*IT` có thể được Maven Failsafe xử lý thay vì Surefire; cần cấu hình cách chạy rõ.

### 15.2. Vì sao phải seed trước mỗi concurrency level?

Nếu C1 đã làm `viewCount` tăng ở các hot keys, rồi C4 chạy tiếp mà không reset, conflict/serialization load có thể bị khác về data state. Reset giúp giữ `viewCount=0` và tập keys giống nhau trước mỗi run. Nhưng reset cũng làm cache trở nên nóng; ghi rõ và dùng warm-up nhất quán.

### 15.3. Concurrency cao hơn đồng nghĩa tổng operations nhiều hơn

Vì `operationsPerWorker=400`, C1 chạy 400 operations, C16 chạy 6.400. Thời gian đo/độ ổn định p99 khác nhau. Bài phù hợp demo thao tác và xu hướng ban đầu; để báo cáo performance nghiêm túc, nên chuyển sang **fixed-duration measurement**, warm-up theo thời gian, đạt số samples tối thiểu mỗi nhóm và chạy nhiều repetitions.

### 15.4. Công cụ không bảo đảm benchmark tự chạy

Đoạn `AccessPatternLoadIT` là tài liệu hướng dẫn; STEP 4 không được chạy Docker, Maven, Testcontainers hoặc benchmark thật. Người học chỉ có kết quả sau khi tự chạy trên môi trường được cấp phép, lưu logs và xác nhận setup đúng.

## 16. Kiểm tra tính đúng của counter sau khi đo

Dù benchmark hướng tới latency, **tính đúng của dữ liệu** vẫn cần kiểm tra. Trong baseline không retry CAS conflict, mỗi successful update làm `viewCount` tăng đúng một lần. Với dataset riêng và không có writer khác, bất biến mong đợi:

~~~text
Sum(viewCount of 1.000 documents)
    == number of SUCCESS CAS_UPDATE operations
~~~

Một helper kiểm tra ngoài khoảng đo:

~~~java
long storedViews = 0;
for (int i = 0; i < BenchSeed.RECORDS; i++) {
    BenchOrder doc = repository
        .findById(BenchSeed.key(i)).orElseThrow();
    assertEquals("CREATED", doc.getState());
    storedViews += doc.getViewCount();
}

long successfulWrites = report.samples().stream()
    .filter(s -> s.kind()
        == AccessProfile.Kind.CAS_UPDATE)
    .filter(s -> s.outcome()
        == AccessProfile.Outcome.SUCCESS)
    .count();

assertEquals(successfulWrites, storedViews);
~~~

### 16.1. Khi bất biến không đúng

- Có update khác ngoài driver vào collection hay không?
- Seed có hoàn tất trước khi mở gate đo không?
- Một lỗi ambiguous được đếm `ERROR` nhưng server đã commit hay chưa?
- SDK timeout/pending mutation có thể làm kết quả chưa xác định; cần reconciliation trước khi assert tuyệt đối.
- `viewCount` có bị overwrite bằng upsert không CAS không?
- Có cleanup/TTL/expiry chạm vào data khi đo không?

Trong lab healthy đơn nút và không có timeout, invariant thường nên đạt. Nếu xuất hiện ambiguous outcomes, không tự kết luận lost update chỉ từ một con số lệch.

### 16.2. CAS conflict không phải “thao tác thành công bị bỏ mất”

Một update dùng CAS stale bị từ chối một cách có chủ đích để bảo vệ dữ liệu mới. Nếu nghiệp vụ yêu cầu *mọi lượt xem phải tăng counter*, ứng dụng phải retry có giới hạn hoặc dùng sub-document counter/atomic increment thích hợp. Đây là **workload khác**, có latency và contention khác.

## 17. Mẫu bảng báo cáo kết quả

Đừng tự điền số liệu giả như thể đã benchmark. Khi chạy thực, ghi một bảng:

| Run | Concurrency | Attempts | GET / UPDATE thực tế | Success | CAS conflict | Other error | Attempt throughput | p50 GET | p95 GET | p99 GET | p99 UPDATE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| R1 | 1 | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| R2 | 4 | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| R3 | 8 | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| R4 | 16 | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

**Kèm metadata môi trường:** image digest/tag, Testcontainers + Spring Boot/Java SDK version, JDK/JVM flags, host CPU/RAM/Docker quota, số lần lặp, thời lượng warm-up, seed, kích thước document, timestamp test, current system load và error classification.

### 17.1. Chọn giá trị để đánh giá

- `p99 GET` nếu API có SLO đọc.
- `p99 UPDATE` nếu cần theo dõi chi phí optimistic update.
- `successful operations/s` để biết năng lực hoàn thành công việc thật.
- `CAS conflict rate` để đánh giá hot-key contention.
- `timeout/errors` để biết tính ổn định.
- `CPU/GC/network/disk utilization` để giải thích bottleneck.

Một dòng “throughput = 4.000 ops/s” không nói đủ nếu thiếu error rate, workload và cấu hình.

## 18. Warm-up, cold cache và thứ tự thí nghiệm

~~~mermaid
flowchart LR
    Init["START CONTAINER"]
    Ready["WAIT KV READY"]
    Seed["SEED 1000 DOCS"]
    Warm["WARM-UP (excluded)"]
    Reset["RESET VIEW COUNTS"]
    Measure["MEASURED RUN"]
    Validate["VALIDATE DATA"]
    Export["EXPORT REPORT"]
    Init --> Ready --> Seed --> Warm --> Reset --> Measure --> Validate --> Export
~~~

### 18.1. Warm-up làm gì?

- JVM JIT có cơ hội biên dịch các code paths nóng.
- SDK kết nối, router và serializer đã từng được sử dụng.
- Server có thể có cache/page warming.
- Test driver khởi tạo threads và data structures.

Warm-up ngắn 100 operations/worker chỉ là **minh họa**, không thể cam kết JIT/GC ổn định. Performance suite nghiêm túc cần warm-up theo thời gian, theo dõi steady-state và nhiều repetitions.

### 18.2. So sánh cold-start và steady-state là hai bài khác nhau

Nếu muốn biết latency của **request đầu tiên sau deploy**, đo cold-start riêng với startup included, và đừng gắn con số đó vào p99 steady-state. Với bài này, **startup bị loại khỏi cửa sổ đo** để đo hoạt động sau khi cluster và SDK sẵn sàng.

### 18.3. Thứ tự chạy có thể gây bias

C1 luôn chạy trước C16; máy, JIT, disk cache và heap có thể nóng lên theo thời gian. Khi so sánh nghiêm túc:

1. Chạy vài repetitions theo thứ tự luân phiên/randomized.
2. Cố định hoặc ghi nhận nhiệt độ/tải host.
3. Báo median/variance của các runs, không chỉ một p99.
4. Tách outliers có lý do và báo cả mẫu không đạt, không xóa tùy ý.
5. Tối thiểu giữ cùng data size, mix, seed và deadline.

## 19. Closed-loop và open-loop: đọc biểu đồ cho đúng

~~~mermaid
flowchart TD
    Goal{"Câu hỏi hiệu năng?"}
    Closed["Concurrency fixed<br/>Workers đợi response rồi gửi tiếp"]
    Open["Arrival-rate fixed<br/>Requests đến độc lập response"]
    A["Khám phá throughput-latency<br/>khi tăng concurrency"]
    B["Kiểm tra latency SLO<br/>ở offered load X req/s"]
    Goal -->|"Concurrency scaling"| Closed --> A
    Goal -->|"Tải đến theo thời gian"| Open --> B
~~~

Closed-loop giúp phát hiện khi tăng worker từ C1 → C16 thì latency, throughput và conflicts biến động. Nhưng khi DB chậm, các threads gửi **ít requests hơn**, làm nguồn tải tự giảm. Điều đó có thể che overload so với arrival-rate thực tế.

Open-loop cần:

- Lịch phát request cố định hoặc phân phối arrival xác định.
- Giới hạn outstanding requests/queue để không làm nổ bộ nhớ.
- Ghi nhận requests bị bỏ, timeouts và queue delay, không chỉ completed requests.
- Báo offered vs achieved throughput.
- Tách HTTP end-to-end và backend timings.

Có thể dùng Gatling/k6/JMeter cho HTTP tải thực tế hoặc một driver có pacing đúng; **không** tuyên bố rằng mỗi vòng `for` bắn thật chính xác `X req/s`.

## 20. Ba lượt đối chiếu để hiểu hot-key contention

Đừng thay tất cả biến cùng lúc. Dùng cùng entity, container, document size, workers, operations và phần lớn code; thay **một chiều của profile**:

| Scenario | GET / UPDATE | Hot traffic | Điều cần học |
|---|---|---|---|
| **A — Read-only uniform** | 100 / 0 | 1% hoặc phân bố đều | Latency KV GET và throughput baseline |
| **B — Mixed uniform** | 90 / 10 | 1% vào 1% keys, hoặc mọi key uniform | Chi phí CAS update khi ít contention |
| **C — Mixed hot** | 90 / 10 | **70% vào 1% keys** | Hot-key conflicts và tail latency |

Trong code đã viết, `hotPercent=70` nghĩa là 70% requests chọn ngẫu nhiên trong 10 hot keys, **không phải 70% traffic trên một key duy nhất**. Để tạo phân bố đều thực sự trên 1.000 keys, cần một sampler uniform riêng; đặt `hotPercent=1` không hoàn toàn tương đương uniform vì nó thêm 1% xác suất ngoài baseline vào 1% hot keys.

### 20.1. Một sampler uniform rõ nghĩa

~~~java
// Chỉ dùng cho scenario A/B thay thế.
private static String uniformKey(
        java.util.SplittableRandom rng) {
    return BenchSeed.key(
        rng.nextInt(BenchSeed.RECORDS));
}
~~~

**So sánh A với B** cho thấy thêm writes làm thay đổi latency/throughput thế nào nhưng cũng đổi packet mix. **So sánh B với C** phù hợp hơn để cô lập tác động của skewed distribution, miễn hai workload có cùng ratio và môi trường.

### 20.2. Có nên giữ seed random giống nhau?

Giữ cùng seed cố định giúp giảm một nguồn dao động. Tuy nhiên, khi sampler khác, chuỗi keys không tự giống nhau và thread interleaving vẫn không deterministic. Muốn kiểm soát tuyệt đối trace, có thể **pre-generate danh sách logical operations cùng key** trước measured window rồi replay. Đó là mức kế tiếp của bài học.

### 20.3. Tại sao CAS conflict cao có thể đúng?

Nếu 10% operations là read+replace và nhiều writes tới cùng 10 hot keys, hai workers có thể đọc cùng CAS, rồi một writer thua. Đây là outcome kỳ vọng của optimistic locking, **không nhất thiết Data node đã quá tải**. Theo dõi conflict rate cùng timeout/error rate thay vì gọi mọi exception là database outage.

## 21. Spring Data Repository, Template và SDK: đo một thứ ở mỗi lần

Mẫu chính dùng `CouchbaseRepository`. Trong module Spring Data Couchbase, bạn có thể tạo hai bài đối chứng với cùng keyspace và ratio:

### 21.1. Spring Data Template — thao tác GET theo ID

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

// Template đã được Spring Boot autoconfigure.
BenchOrder order = template
    .findById(BenchOrder.class)
    .one(BenchSeed.key(42));
~~~

Update có CAS qua metadata entity:

~~~java
BenchOrder order = template
    .findById(BenchOrder.class)
    .one(BenchSeed.key(42));

order.setViewCount(order.getViewCount() + 1);

BenchOrder saved = template
    .replaceById(BenchOrder.class)
    .one(order);
~~~

Với `@Version`, verify CAS translation của Template theo version, và không dùng `upsertById` để “giảm conflicts”. Template có thể cung cấp tùy chọn expiry/durability riêng theo operation; phải giữ options tương đương Repository nếu muốn so cùng workload.

### 21.2. Java SDK trực tiếp — KV operation thuần

~~~java
import com.couchbase.client.java.Collection;

Collection collection = cluster.bucket("bench_lab")
    .defaultCollection();

var content = collection.get(BenchSeed.key(42))
    .contentAsObject();
~~~

Đường này đo SDK KV + JSON decoder, **không** đo Spring Data mapping/entity conversion. Không dùng khác biệt p95 một mình để kết luận Repository “kém” hoặc Template “tốt” vì đường benchmark có thể trả kiểu dữ liệu khác nhau.

### 21.3. So sánh công bằng cần giữ điều kiện

| Thuộc tính | Repository | Template | SDK direct |
|---|---|---|---|
| Keyspace | Cùng `bench_lab` | Cùng | Cùng |
| KV GET ID | `findById` | `findById(...).one` | `get(id)` |
| Decode | Entity converter | Entity converter | JSON hoặc POJO serializer |
| Update | `save` có `@Version` | `replaceById` có CAS | `replaceOptions().cas(...)` |
| Durability | Default / entity policy | Có thể override | Per operation |
| TTL | Entity metadata | Fluent overrides | `expiry/preserveExpiry` |
| Error mapping | Spring Data exceptions | Spring Data exceptions | SDK exceptions |

Không nên gộp latency của JSON-only SDK GET và entity-mapping Repository trong cùng p99 nếu mục tiêu là đo cùng semantic operation.

## 22. SQL++/GSI là một profile khác, không phải KV GET

Nếu sản phẩm cần màn hình “đơn CREATED của tenant LAB”, bạn có thể thêm truy vấn:

~~~sql
CREATE INDEX ix_bench_tenant_state
ON `bench_lab`.`_default`.`_default`(tenantId, state);
~~~

Ví dụ Spring Data Repository khác:

~~~java
import java.util.List;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.repository.ScanConsistency;

// Thêm vào BenchOrderRepository nếu cần lab SQL++.
@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
List<BenchOrder> findByTenantIdAndState(
    String tenantId, String state);
~~~

### 22.1. Vì sao không thêm query vào profile 90/10 ban đầu?

Query Service, Index Service, GSI update lag, scan consistency và result-size là những biến hoàn toàn khác KV GET by ID. Nếu bạn đổi 50% GET thành SQL++ nhưng vẫn gọi đó là “90/10 KV profile”, báo cáo đã sai định nghĩa.

Khi cần query profile, mô tả:

~~~text
Scenario Q:
  80% KV get by ID
  10% SQL++ findByTenantIdAndState
  10% CAS update
  Query consistency: REQUEST_PLUS
  Result size: bounded / pagination
  GSI: ix_bench_tenant_state online
~~~

**Chỉ khi Index/Query services được bật trong CouchbaseContainer** mới chạy scenario Q; `withBucket` và `KV ready` chưa đủ chứng minh Query/Index đã sẵn sàng. Testcontainers có tùy chọn bật services theo edition/image và tài liệu version, nhưng cần provision/bật đúng trong fixture riêng, đợi index online.

### 22.2. SQL++ consistency thay đổi latency

`QueryScanConsistency.NOT_BOUNDED` dùng trạng thái index hiện có; có thể không thấy writes rất mới. `REQUEST_PLUS` chờ index bắt kịp đến mốc query và có thể tăng latency khi DCP backlog.

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

var result = cluster.query(
    "SELECT META(o).id AS id, o.tenantId, o.state "
  + "FROM `bench_lab`.`_default`.`_default` AS o "
  + "WHERE o.tenantId = $tenant AND o.state = $state "
  + "LIMIT 20",
    queryOptions()
      .parameters(
          com.couchbase.client.java.json.JsonObject.create()
              .put("tenant", "LAB")
              .put("state", "CREATED"))
      .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);
~~~

SQL++ statement trong Java cần backticks thật quanh keyspace, không phải dấu định dạng Markdown. Xem code block khi chép vào IDE. Không tự kết luận một SQL++ query chưa thấy order là KV write đã mất.

### 22.3. Chỉ mục phải được provision ngoài khoảng đo

DDL `CREATE INDEX` và index build có thể mất thời gian/CPU/disk đáng kể. Tạo index trong setup, đợi ONLINE, warm-up query và chỉ sau đó mới bắt đầu measurement. Index build lẫn trong cửa sổ đo sẽ khiến p99 không phản ánh query steady-state.

## 23. Durability: không dùng single container để thử HA

Một `CouchbaseContainer` thường là **một Data node**, và bucket test có thể không có replica. Điều này phù hợp kiểm tra CRUD, CAS, TTL và bộ đo nhẹ; nó không kiểm chứng HA.

| Muốn thử | Điều kiện tối thiểu | Không được suy ra từ một container |
|---|---|---|
| `DurabilityLevel.NONE` | Default/bucket policy được ghi rõ | Dữ liệu chắc chắn sống sau mất node |
| `DurabilityLevel.MAJORITY` | Topology đủ điều kiện, majority được định nghĩa | Một node còn sống khi cả host mất |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Couchbase bucket có disk persistence | Sẵn replica đa node |
| `PERSIST_TO_MAJORITY` | Majority bản copy có persistence | DR của cả region |
| Failover/rebalance | Multi-node cluster lab được quản lý đúng | Testcontainers single-node tự tạo replica |

Trong Couchbase, majority khi 0 replica là 1/1; đáp ứng majority 1/1 **không bảo vệ mất node duy nhất**. Đừng dùng `DurabilityLevel.MAJORITY` trong code rồi báo “đã kiểm thử mất một Data node”.

### 23.1. Bài mở rộng durability cần profile độc lập

Nếu dùng Template:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;

// Chỉ triển khai trên cluster lab hỗ trợ level này.
BenchOrder saved = template
    .replaceById(BenchOrder.class)
    .withDurability(DurabilityLevel.MAJORITY)
    .one(order);
~~~

So sánh với default chỉ có ý nghĩa khi ghi rõ **effective bucket minimum durability**, replica count, disk health, failover policy và operation size. Một write mạnh hơn có thể làm p99 tăng; đó không phải bằng chứng nên hạ policy nếu business RPO không cho phép.

### 23.2. Tham số không nên âm thầm đổi

- Write durability level.
- Timeout/retry config.
- Bucket replica count.
- Storage quota/disk type.
- GSI Query/Index services.
- Payload size.
- Read preferences/consistency.
- Cache/Spring converter.
- JVM heap/GC.
- Access key distribution.

Nếu một biến thay đổi, đánh dấu run thành thí nghiệm mới; không đưa vào cùng nhóm như đã “đo lại cùng điều kiện”.

## 24. Reactive access và backpressure là một thí nghiệm riêng

Spring Data Couchbase có `ReactiveCouchbaseRepository` và `ReactiveCouchbaseTemplate`; Java SDK cũng có reactive `Mono` APIs. Một prototype reactive read:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Mono;

interface ReactiveBenchOrderRepository
        extends ReactiveCouchbaseRepository<BenchOrder, String> {}

Mono<BenchOrder> read =
    reactiveRepository.findById(BenchSeed.key(42));
~~~

### 24.1. Không trộn `block()` trên event loop

Nếu driver đã chạy trên WebFlux/Netty event-loop, gọi blocking Repository hoặc `Mono.block()` có thể làm nghẽn event-loop. Nếu muốn benchmark reactive, dùng `flatMap` với **concurrency giới hạn**, tách throughput/latency theo logical operation và xử lý onError.

### 24.2. Reactive không tự làm KV server nhanh hơn

Reactive giúp quản lý tài nguyên client và nhiều requests đang chờ I/O mà không cần mỗi request một platform thread. Server-side KV, CAS conflicts, durability và network vẫn tồn tại. So sánh reactive với blocking phải giữ cùng semantics, batch size, concurrency, error handling, JSON converter và memory budget.

### 24.3. Backpressure không thay retry/idempotency

Nếu write timeout ambiguous, không gọi `retryWhen(Retry.max(100))` cho mọi lỗi. Cần phân biệt operation idempotent, CAS conflicts, duplicate, ambiguous outcome và total retry budget. Một reactive load driver có thể gửi nhiều inflight requests rất nhanh nếu `flatMap` không giới hạn concurrency.

## 25. Đọc biểu đồ: throughput tăng nhưng p99 xấu đi

Dự kiến (không phải số đo thật):

~~~text
C1  -> throughput tăng theo số workers
C4  -> nhiều KV requests đang chờ cùng lúc
C8  -> hot-key CAS conflicts có thể tăng
C16 -> p99 có thể tăng và throughput có thể bão hòa
~~~

Không có quy tắc chắc chắn rằng C16 luôn nhanh hơn C8. Khi p99 xấu, xem đồng thời:

- Số worker requests đang in flight.
- Thời gian round-trip từ client đến Data Service.
- CPU/GC của JVM app và của Couchbase container.
- Disk/IO/network và Docker resource caps.
- CAS contention trên 10 hot keys.
- SDK timeouts/retries.
- Query/index workload khác có đang chạy trên cùng host không.

### 25.1. Xác định “điểm gãy” theo SLO

Nếu đội sản phẩm đưa SLO GET p99 thấp hơn một ngưỡng trong điều kiện tải cụ thể, thì điểm gãy là mức offered/concurrency nơi p99 hoặc error rate vượt tiêu chí. Bài không tự đặt `100ms` hay `10.000 ops/s` làm chuẩn vì mỗi hệ thống khác nhau.

### 25.2. Nhìn sang Little's Law nhưng không dùng sai

Trong trạng thái ổn định:

~~~text
L ≈ λ × W
  L: số requests trung bình trong hệ thống
  λ: throughput trung bình (ops/s)
  W: thời gian trung bình trong hệ thống (s)
~~~

Đây là quan hệ trung bình, không phải công thức suy p99 hay dự đoán số requests thành công khi lỗi. Với closed-loop threads, số in-flight bị giới hạn bởi số workers; nếu λ thấp vì W quá cao, tăng worker có thể làm queueing tệ hơn.

## 26. Sai số thống kê và quy mô mẫu

Ở concurrency 1 với `operationsPerWorker=400` và mix 90/10, chỉ có khoảng 40 logical updates. Giá trị p99 UPDATE khi đó gần **max sample**, rất nhạy cảm một lần GC/IO chậm. Không dùng con số đó để ký SLO.

### 26.1. Khi nào cần tăng mẫu?

- Muốn p99 có ý nghĩa hơn, cần đủ nhiều samples **trong từng operation category**, không chỉ tổng 100.000 GET rồi 30 UPDATE.
- Đo thời gian dài đủ có vài chu kỳ GC, tải ổn định, tránh khởi động hoặc seed.
- Lặp nhiều runs trên cùng cấu hình, báo median/variance/confidence bands nếu có.
- Nếu đo high-percentile production SLO, dùng công cụ chuyên dụng và tổ chức kiểm soát noise.

### 26.2. Tránh averaged percentiles sai

Không tính:

~~~text
p99_total = (p99_worker1 + p99_worker2 + ...)/workerCount
~~~

Cách này không cho ra p99 của **toàn bộ** samples. Hãy gộp phân phối/histograms tương thích, rồi tính percentile toàn cục. Bài dùng `long[]` sorted từ mọi worker đã được merge.

### 26.3. Không chọc JVM hoặc container khi đo

- Tránh chạy profiler rất nặng trong benchmark baseline.
- Không in log mỗi operation.
- Không xuất `System.out.println` trong vòng lặp workers.
- Không liên tục tạo client/Cluster mới.
- Không sửa cấu hình host giữa hai runs.
- Nếu cần JFR/async-profiler, đánh dấu đó là một run phân tích có overhead riêng.

## 27. Các lỗi môi trường Testcontainers thường gặp

| Triệu chứng | Khả năng | Hành động phù hợp |
|---|---|---|
| `Could not find a valid Docker environment` | Docker daemon không chạy/không có quyền | Kiểm tra Docker runtime/CI policy |
| Image pull rất lâu | Image lớn, proxy, registry | Pre-pull được cấp phép, cache image, không tính vào latency |
| Container start timeout | Thiếu RAM/CPU, bootstrap chậm | Kiểm tra resource limits và logs, tăng startup budget hợp lý |
| Boot app không kết nối | Thiếu `@ServiceConnection` hoặc trộn credentials | Kiểm tra `spring-boot-testcontainers` và dependency alignment |
| `BucketNotFoundException` | Tên `bench_lab` sai/chưa provision | Kiểm tra `withBucket` và `spring.data.couchbase.bucket-name` |
| `CollectionNotFoundException` | Entity dùng custom scope chưa tạo | Provision scope/collection và đợi manifest |
| `No index available` | Chạy SQL++ không có GSI | Tạo index đúng keyspace, đợi online |
| `AuthenticationFailureException` | App dùng secret tĩnh sai | Để container cung cấp connection details |
| `CasMismatchException` | Hot key update tranh chấp | Đo conflict; không upsert để che |
| p99 cao bất thường ở lần đầu | SDK bootstrap/JIT/cache | Warm-up và tách cold-start |
| Benchmark chạy nhưng không có samples | Test skipped/empty profile | Kiểm tra cờ opt-in và số operations |
| Parallel JUnit methods can thiệp data | Shared container + shared key prefix | Chạy tuần tự, test namespace riêng |
| Port collision | Host port hardcode | Dùng mapped port ngẫu nhiên của Testcontainers |
| Test treo quá lâu | SDK/driver deadline thiếu | Thêm total deadline, cancel, giữ partial diagnostics |

### 27.1. Không tắt resource cleanup để “giải quyết” lỗi CI

Testcontainers dùng cơ chế cleanup containers/networks. Vô hiệu hóa Ryuk/cleanup hoặc bật reuse không có policy có thể để lại containers và credentials, làm test sau nhiễm state. Giải quyết bằng quyền Docker, cấu hình runner và cleanup policies được nhóm CI chấp thuận.

### 27.2. Windows/Docker Desktop

Nếu Docker Desktop/WSL2 chạy trên laptop, hiệu năng disk/network/VM khác server thật. Testcontainers integration thường hợp lý; performance measurements chỉ nên coi là **local comparative evidence**. Tránh copy p99 laptop vào capacity planning của cluster cloud.

## 28. CI pipeline: chạy đúng bài ở đúng giai đoạn

Một cách chia pipeline:

~~~mermaid
flowchart LR
    Unit["Unit tests<br/>always"]
    Integration["Testcontainers integration<br/>Docker-enabled CI"]
    Load["Opt-in micro-load<br/>dedicated runner"]
    Staging["Staging performance test<br/>topology near production"]
    Review["Report + SLO review"]
    Unit --> Integration --> Load --> Staging --> Review
~~~

| Giai đoạn | Điều kiện | Tiêu chí chính |
|---|---|---|
| Unit | Không Docker | Logic đúng, nhanh |
| Testcontainers IT | Docker available | Mapping/CAS/Repository correctness |
| Opt-in micro-load | `RUN_CB_BENCH=true` + host được kiểm soát | Samples đầy đủ, report không crash |
| Staging perf | Load driver và cluster phù hợp | SLO latency, throughput, error budget |
| Production | Không inject fault/benchmark tùy tiện | Metrics và cảnh báo theo traffic thật |

### 28.1. Không biến performance micro-load thành cổng CI tuyệt đối

Nếu test chạy trên runner shared có CPU dao động, assertion `p99 < 20ms` có thể flaky vô ích. CI nên assert **functional invariants, không có lỗi ngoài dự kiến, đủ samples**. Performance threshold chỉ nên gate trên **dedicated runner đã kiểm soát** và có statistical policy/tolerance.

### 28.2. Version drift làm mất khả năng so sánh

Nếu Docker tag trỏ image khác, Spring Boot/SDK converter đổi, Testcontainers major đổi hoặc JVM khác, hãy xem đó là một **run metadata mới**, không ghi đè baseline cũ. Tốt nhất pin tag/digest và lưu `dependency:tree` ở ngoài bài (người chạy thực hành thực hiện), đồng thời cập nhật security patches có kế hoạch.

## 29. Logging và observability: không làm sai đường đo

Trong benchmark driver, việc log mỗi operation sẽ:

- Tạo IO và lock contention ở app.
- Thay thread scheduling.
- Tăng allocation/GC và latency.
- Khiến p99 phản ánh log sink nhiều hơn Couchbase.

Thay vào đó, chỉ tăng counters trong worker-local structures rồi in aggregate sau run. Ở production, dùng metrics/tracing sampling theo policy; gắn correlation IDs khi cần điều tra cụ thể.

### 29.1. Bảng metric tối thiểu

| Metric | Đơn vị | Ý nghĩa |
|---|---|---|
| Attempt throughput | logical ops/s | Các attempts hoàn tất mỗi giây |
| Success throughput | successful ops/s | Công việc thật đã thành công |
| GET p50/p95/p99 | ms | Độ trễ logical KV read |
| UPDATE p50/p95/p99 | ms | Read–CAS replace, có thể gồm 2 calls |
| CAS conflict rate | % writes | Mức tranh chấp optimistic locking |
| Other error rate | % all attempts | Hạ tầng/code errors |
| Sample count | count | Độ tin cậy của percentile |
| Application CPU/GC | %/pause ms | Client overhead |
| Container CPU/memory/disk | %/bytes/IOPS | Nút cổ chai Couchbase lab |
| Hot-set actual share | % all attempts | Kiểm tra sampler |
| SDK timeout/retry count | count | Tác động latency/resilience |

**Mọi số liệu phải gắn với cùng khoảng thời gian và cùng run ID.** Không ghép p99 GET run R1 với conflict rate run R3 rồi gọi là một kết quả.

## 30. Case study A — Testcontainers chạy xanh nhưng Spring Data lưu nhầm collection

**Tình huống:** team thêm `@Scope("sales")` và `@Collection("orders")` vào entity để giống production, nhưng container chỉ được cấu hình `withBucket(new BucketDefinition("bench_lab"))`.

**Triệu chứng:** smoke test trước kia chạy được, sau đổi annotation thì `repository.save` báo collection not found. Một developer bỏ annotation đi hoặc đổi tên bucket ngẫu nhiên để test xanh.

**Phân tích:** Testcontainers Couchbase container cung cấp **Couchbase Server**, không tự suy toàn bộ keyspace từ code Spring Data. Bucket, scope, collection là tài nguyên khác nhau. `@Scope`/`@Collection` cần collection manifest đã provision đúng.

**Cách sửa:**

1. Chọn mặc định `_default._default` cho baseline hoặc tạo `sales.orders` trong setup.
2. Dùng `bucket.collections().createScope("sales")` và `createCollection("sales","orders")` theo server version được hỗ trợ.
3. Chờ manifest/SDK routing cập nhật trước seed.
4. Có một assertion đọc lại bằng SDK đúng collection.
5. Không tạo scope/collection trong mỗi logical operation hoặc trong khoảng đo.

**Bài học:** lỗi keyspace là lỗi setup/integration, **không** phải latency benchmark.

## 31. Case study B — p99 tăng nhưng throughput vẫn được ca ngợi

**Tình huống:** sau khi tăng concurrency từ 4 lên 16, attempt throughput tăng; đồng thời hot-key CAS conflict tăng mạnh.

**Sai lầm:** báo cáo “backend xử lý nhanh hơn vì nhiều attempts/s hơn”. Những attempts bị `CAS_CONFLICT` **không tạo ra increment nghiệp vụ**, nên successful throughput có thể thấp hơn dự kiến.

**Cách phân tích:**

- Đếm `CAS_UPDATE` thành công riêng với conflicts.
- Tính `successful ops/s` thay vì chỉ `attempts/s`.
- Tính p99 GET và p99 UPDATE riêng.
- Xác minh `sum(viewCount) == successful CAS updates` trong trạng thái healthy không ambiguous.
- So scenario mixed uniform và mixed hot để cô lập contention.
- Nếu nghiệp vụ yêu cầu mọi increment, thử phương án atomic counter hoặc retry có giới hạn như **một profile mới**.

**Bài học:** throughput “cao” mà bỏ qua correctness và failure rate là một kết luận thiếu nền tảng.

## 32. Case study C — Benchmark trên laptop lại được dùng để sizing production

**Tình huống:** một container Couchbase và JVM cùng chạy trên Docker Desktop laptop, không replica, dataset nhỏ, payload 256 ký tự, 400 ops/worker. Nhóm lấy p99 từ một lần chạy rồi quyết định một production node có thể xử lý hàng triệu requests/ngày.

**Vấn đề:**

- Topology 1 node ≠ production nhiều Data/Index/Query nodes.
- Docker Desktop/WSL2 disk, network, VM CPU khác cloud.
- 1.000 documents gần như toàn bộ ở cache, không mô phỏng working set thật.
- Không có TLS/auth/API gateway/telemetry overhead như production.
- Workload có hot keys, nhưng tỷ lệ/payload theo lựa chọn giáo dục.
- C1 chỉ vài trăm samples, p99 cập nhật không đáng tin cậy.
- Không đo failure, rebalance, backups hoặc recovery.

**Cách sửa:** dùng lab làm baseline functional và khám phá code path. Muốn capacity planning cần staging topology gần production, realistic dataset, workload trace, open-loop offered rate, repetitions và SLO được nghiệp vụ duyệt.

**Bài học:** Testcontainers đảm bảo **reproducible integration setup**, không tự tạo **reproducible production performance**.

## 33. Case study D — Load driver là nguyên nhân của p99

**Tình huống:** benchmark in một dòng log chứa JSON document/stack trace cho mỗi operation. CPU JVM cao, GC thường xuyên, p99 tăng, trong khi Couchbase Data node CPU còn thấp.

**Phân tích:** phép đo không chỉ đo Couchbase; nó đo **driver + Spring Data + SDK + server**. Logging synchronous trong hot loop có thể là bottleneck chính.

**Cách sửa:**

1. Gỡ per-operation logs trong measured interval.
2. Thu samples trong worker-local array/list và aggregate sau run.
3. So client CPU/GC với container CPU/disk/network.
4. Không tạo Cluster/Connection mỗi request.
5. Nếu cần JFR/async-profiler, chạy profile riêng có gắn nhãn overhead.
6. Kiểm tra sample distribution trước khi suy ra bottleneck database.

**Bài học:** đúng phương pháp đo quan trọng không kém chọn công cụ đo.

## 34. Case study E — Có Index nhưng `findById` vẫn chậm

**Tình huống:** một developer tạo GSI trên `state`, nghĩ nó sẽ làm `repository.findById` nhanh hơn. Kết quả p99 GET gần như không đổi.

**Giải thích:** `findById` theo document ID là **KV operation**, dùng vBucket key routing, không tra GSI. Secondary index giúp SQL++ query theo field như `state` hoặc `tenantId`. Tạo index không giải quyết KV GET latency do SDK queueing, network, Data node CPU hoặc hot-key contention.

**Cách sửa:** phân loại đường truy vấn thật; kiểm tra operation type qua metrics/tracing/SDK logs. Nếu dùng `findByTenantIdAndState`, benchmark SQL++ riêng với index/query consistency đúng; không trộn với KV GET.

## 35. Ma trận kiểm thử và thực nghiệm được đề xuất

| Mã | Kịch bản | Điều kiện | Assertion/báo cáo |
|---|---|---|---|
| T01 | Docker/Testcontainers bootstrap | Docker available | Container ready, Spring context có Cluster |
| T02 | Bucket mapping | `bench_lab` | Repository lưu/đọc đúng bucket |
| T03 | Create/read one document | Test ID duy nhất | Body và CAS metadata đúng |
| T04 | Update với CAS | Writer A đã đọc | Save thành công, viewCount tăng |
| T05 | Stale CAS | Writer A/B cùng CAS cũ | Chỉ một update thành công; state đúng |
| T06 | Dataset seed | 1.000 documents | Không thiếu ID, payload thống nhất |
| T07 | No index KV path | Default collection | `findById` chạy không cần GSI |
| T08 | Load C1 | 90/10, hot70 | Samples đúng số, không crash |
| T09 | Load C4 | Profile không đổi | Báo cáo latency/outcome |
| T10 | Load C8 | Profile không đổi | Báo cáo latency/outcome |
| T11 | Load C16 | Profile không đổi | Báo cáo latency/outcome |
| T12 | All attempts percentile | Cùng data samples | p50/p95/p99 từ global distribution |
| T13 | Success-only percentile | Lọc outcome | p99 success không bị đánh tráo |
| T14 | Counter invariant | Không ambiguous writers khác | Tổng views = successful updates |
| T15 | Uniform vs hot | Chỉ đổi key distribution | So contention và latency |
| T16 | 100% GET baseline | Chỉ GET | Tách latency read-only |
| T17 | SQL++ query | Query/Index enabled + GSI ONLINE | Query trả data, p99 đo riêng |
| T18 | Query freshness | `NOT_BOUNDED`/`REQUEST_PLUS` | Không nhầm index lag với KV missing |
| T19 | Container resource cap | Resource limit thay có kiểm soát | Đánh dấu scenario khác |
| T20 | Retry policy | Bounded retries sau CAS | Thành công vs latency và retries |
| T21 | Reactive path | Reactive backend, bounded flatMap | Không block event loop |
| T22 | CI opt-in | `RUN_CB_BENCH` absent | Micro-load không chạy ngoài ý muốn |
| T23 | Docker unavailable | Không có daemon | Skip/fail rõ ràng, không báo PASS thật |
| T24 | Cleanup | Test hoàn tất | Không còn containers ngoài policy |
| T25 | Production comparability | Chỉ một container | Báo cáo rõ không phải sizing/HA |

### 35.1. Điểm phân biệt PASS trong functional tests

T01–T07 phải đạt **correctness**; nếu fail, không chạy benchmark rồi cố diễn giải p99. Đặc biệt, thiếu bucket hoặc CAS mismatch bất ngờ là tín hiệu hỏng test setup/semantics.

### 35.2. Điểm phân biệt PASS trong micro-load

T08–T16 trước hết cần:
- Đúng số samples, không lẫn seed/warm-up.
- Có phân loại success/CAS/other errors.
- Không có lỗi lạ bị che.
- Bất biến counter đúng khi không có unknown outcomes.
- Mọi run lưu metadata có thể tái lập.
- Không gắn một ngưỡng performance “trời cho” mà thiếu SLO.

## 36. Bài tập thực hành nâng cao

### A — định nghĩa profile

Viết lại một contract workload gồm tỷ lệ GET/UPDATE, dataset size, payload size, hot/cold distribution, concurrency, seed và retry policy. Vì sao thiếu một trong các biến này có thể làm kết quả không thể so sánh?

### B — Testcontainers artifact migration

Nêu sự khác nhau giữa `org.testcontainers:couchbase` ở Testcontainers 1.x và `org.testcontainers:testcontainers-couchbase` ở 2.x. Vì sao trộn BOM major versions có thể dẫn tới lỗi compile/runtime?

### C — Dynamic connection

Giải thích vai trò của `@Container`, `@Testcontainers` và `@ServiceConnection`. Nếu không có `@ServiceConnection`, cần cung cấp những Spring properties nào bằng `@DynamicPropertySource`?

### D — mapping custom collection

Chuyển entity từ `_default._default` sang `sales.orders`. Cần provision những tài nguyên nào, chờ manifest ra sao và test gì để tránh nhầm `CollectionNotFound` với lỗi Spring Data?

### E — CAS conflict

Cho hai workers cùng đọc counter=8 và CAS V1. Một writer lưu 9, worker kia lưu 9 dùng CAS cũ. Kết quả đúng là gì? Điều gì xảy ra nếu thay replace bằng upsert không điều kiện?

### F — percentile

Tại sao không thể lấy trung bình p99 của bốn threads làm p99 toàn hệ thống? Hãy dùng global latency samples và nearest-rank, giải thích hạn chế khi samples ít.

### G — successful throughput

Một run có 4.000 attempts, trong đó 100 CAS conflicts và 20 errors. Hãy biểu diễn công thức tính successful throughput nếu biết `elapsedSeconds`. Tại sao attempts/s không bằng successes/s?

### H — hot-key distribution

Chọn 70% operations tới 10 hot keys trên tổng 1.000 keys. Vì sao điều này khác với uniform? Kết quả CAS conflict có thể thay đổi ra sao khi tăng worker?

### I — Query lag

Một write KV đã success, nhưng SQL++ `NOT_BOUNDED` chưa thấy. Đây có phải lỗi durability không? Phân biệt KV get theo ID và `REQUEST_PLUS` index freshness.

### J — resource pressure

Khi p99 tăng trên Docker Desktop nhưng Data node CPU thấp, hãy liệt kê năm nguyên nhân ngoài database engine và cách thu thập bằng chứng.

### K — closed vs open loop

Vì sao fixed concurrency load driver có thể gửi ít requests hơn khi DB chậm? Muốn đo user arrival 200 req/s thì cần thay đổi generator và cách ghi metric thế nào?

### L — durability

Bucket có một Data node, không replica; một mutation `MAJORITY` có thể đạt majority 1/1. Có thể dùng kết quả đó để hứa sống sót khi node duy nhất mất vĩnh viễn không? Vì sao?

### M — retry CAS

Chuyển một UPDATE từ “conflict là outcome cuối” sang bounded retry tối đa hai lần. Định nghĩa lại logical operation và báo cáo retries/latency để không đánh tráo profile.

### N — reactive

Dùng `ReactiveCouchbaseRepository` hoặc `ReactiveCouchbaseTemplate` để đọc `BenchOrder` trong WebFlux. Thiết kế `flatMap` concurrency limit và không dùng `block()` trên event-loop; giữ cùng key distribution và workload ratio.

### O — test report

Viết một báo cáo có version/image digest, hardware, JVM config, dataset size, read/write ratio, hot set, concurrency, seed, p50/p95/p99, attempts/s, successes/s, conflict%, error% và giới hạn kết luận.

## 37. Hướng dẫn chấm bài và acceptance criteria

Gợi ý đánh giá theo bốn nhóm:

| Nhóm | Trọng số tham khảo | Cần chứng minh |
|---|---:|---|
| **Tính đúng tích hợp** | 30% | Bucket, CRUD KV, CAS, cleanup, error translation |
| **Tính tái lập workload** | 30% | Seed, key distribution, operation mix, warm-up, gate, dataset |
| **Chất lượng số liệu** | 25% | p50/p95/p99, samples, error/conflict, success throughput |
| **Nhận thức giới hạn** | 15% | Single-node/CI noise, closed-loop, index, durability, SLO |

Trọng số chỉ là gợi ý học tập. Không thưởng điểm cao chỉ vì con số throughput lớn; **độ tin cậy phép đo và cách hiểu kết quả** quan trọng hơn.

### 37.1. Những lỗi phải sửa trước khi thông qua

1. Benchmark bị seed/DDL/index build trộn vào measured interval.
2. Dùng một Query Service result thay cho KV GET trong cùng profile không ghi rõ.
3. Không bảo vệ update bằng CAS rồi tuyên bố không lost updates.
4. In log trong hot loop khiến driver thành bottleneck chính.
5. Không thu latency của failed attempts.
6. Gộp CAS conflicts vào successes.
7. Chạy tất cả tests song song trên shared container/dataset không cô lập.
8. Bật micro-load trên production hoặc shared CI mà không có approval.
9. Tuyên bố p99 của Testcontainers single-node là p99 của production.
10. Bỏ qua Spring Boot/Testcontainers version compatibility.

## 38. Checklist thực hiện bài lab

- [ ] Đã kiểm tra Docker daemon và quyền chạy containers.
- [ ] Dùng **image tag/digest cố định** và Testcontainers/Spring Boot BOM tương thích.
- [ ] Dependencies Testcontainers 2.x dùng artifact names đúng.
- [ ] `@ServiceConnection` hoặc `@DynamicPropertySource` cung cấp connection details động.
- [ ] `bench_lab` bucket được tạo bởi fixture Testcontainers.
- [ ] Đã đợi KV sẵn sàng thay vì gửi requests ngay sau container start.
- [ ] Entity có `@Id`/`@Version`, keyspace đúng và không có TTL vô tình.
- [ ] Smoke test save/get/update/CAS chạy độc lập micro-load.
- [ ] Không cần GSI cho `findById`.
- [ ] Nếu custom scope/collection, setup đã provision và chờ manifest.
- [ ] Dataset 1.000 documents và kích thước payload đã được cố định.
- [ ] Seed/reset nằm ngoài cửa sổ đo.
- [ ] Workload định nghĩa rõ 90% GET, 10% CAS UPDATE ở mức logical operation.
- [ ] Hot set 10 keys và hot traffic share 70% được đo/ghi lại.
- [ ] Có fixed random seed theo worker; biết scheduling không deterministic.
- [ ] Warm-up không bị đếm vào kết quả.
- [ ] Concurrency và số op/worker được ghi trong report.
- [ ] Driver không mở Cluster mới ở mỗi operation.
- [ ] Không log per-operation trong measured interval.
- [ ] Latency dùng `System.nanoTime()`, không dùng wall clock chỉnh NTP.
- [ ] Có p50/p95/p99 theo GET và UPDATE, samples count đầy đủ.
- [ ] Phân loại SUCCESS/CAS_CONFLICT/ERROR, không đánh tráo failed attempts.
- [ ] Báo attempts/s và successful ops/s riêng.
- [ ] Kiểm tra `sum(viewCount) == successful writes` khi applicable.
- [ ] Khi có ambiguous timeout, đối soát trước khi kết luận lost update.
- [ ] Run có option `RUN_CB_BENCH=true` trên dedicated environment.
- [ ] Không coi `@Testcontainers(disabledWithoutDocker=true)` skip là test thành công thật.
- [ ] Đã theo dõi Docker/JVM CPU, memory, GC, disk và network.
- [ ] SQL++/GSI chỉ đo trong scenario riêng, index online và consistency được ghi.
- [ ] Durability/replica/failover không được suy từ single-node container.
- [ ] Đã phân biệt closed-loop concurrency và open-loop offered rate.
- [ ] Báo cáo nêu rõ version, resources, date/time, seed, SLO và limits.
- [ ] Không bật container reuse/disable cleanup ngoài quy trình CI.
- [ ] Không sử dụng kết quả laptop trực tiếp cho capacity planning production.

## 39. Tổng kết

**Testcontainers giúp kiểm thử Spring Data Couchbase với một Couchbase Server thật, được khởi động trong môi trường có thể tái tạo**, thay vì tin rằng mock Repository đã đủ chứng minh mapping/CAS/SDK behavior. Với `@ServiceConnection` hoặc dynamic properties, Spring Boot nhận endpoint/credential của container được cấp phát ngẫu nhiên mà không cần hardcode port.

Phần đo tải đặt một câu hỏi **cụ thể và có thể kiểm tra**: điều gì xảy ra với throughput, latency p50/p95/p99 và CAS conflict khi số workers tăng, trong profile 90% GET by ID và 10% read–CAS replace, với 70% traffic rơi vào 1% hot keys? Để trả lời đúng, phải cố định dataset, operation mix, key distribution, warm-up, retry policy, version và host resources; đồng thời tách seed/DDL khỏi measurement, ghi cả lỗi thay vì chỉ ghi successes.

Mẫu closed-loop của bài giúp học concurrency scaling, **không** mô phỏng chính xác một arrival rate ngoài đời. Một Testcontainers single-node giúp xác minh KV, Repository/Template và CAS, **không** chứng minh HA, replica durability, backup/DR hoặc công suất của cluster production. Khi cần những cam kết đó, hãy thiết kế benchmark staging có topology, tải và SLO riêng.

## Tài liệu tham khảo chính thức

1. [Testcontainers Java — Couchbase module](https://java.testcontainers.org/modules/databases/couchbase/): `CouchbaseContainer`, `BucketDefinition` và dependency module.
2. [Testcontainers Java — JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`, container lifecycle và giới hạn chạy song song.
3. [Testcontainers Java — Version management](https://java.testcontainers.org/): artifact/BOM Testcontainers 2.x và module versions.
4. [Testcontainers Java — Supported container runtimes](https://java.testcontainers.org/supported_docker_environment/): Docker API runtime và CI.
5. [Spring Boot — Testcontainers service connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, `@DynamicPropertySource` và điều kiện test dependencies.
6. [Spring Boot — Couchbase auto-configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html): `spring.data.couchbase.bucket-name` và Spring Data integration.
7. [Spring Data Couchbase — Repository reference](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): KV by ID, query derivation và repository behavior.
8. [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Id`, `@Version` và CAS.
9. [Spring Data Couchbase — Template operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): fluent KV operations và durability options.
10. [Couchbase Java SDK — Managing connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html): bootstrap, `waitUntilReady` và connection reuse.
11. [Couchbase Java SDK — Provisioning cluster resources](https://docs.couchbase.com/java-sdk/current/howtos/provisioning-cluster-resources.html): scopes, collections và indexes.
12. [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): index consistency và `REQUEST_PLUS`.
13. [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): get/insert/replace/CAS và timeout.
14. [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): replica majority, persistence và giới hạn failure scenarios.

**Giới hạn của STEP 4:** Mã trong tài liệu là hướng dẫn để người học dựng project và tự chạy trên Docker/lab được phép; người soạn chưa chạy Maven build, JUnit/Testcontainers, benchmark, can thiệp cluster hoặc Content QA/refactor chuyên môn. Các assertion, image tags, plugin versions và thông số phải được kiểm chứng trên môi trường thực trước khi dùng làm bằng chứng SLO hay capacity.




