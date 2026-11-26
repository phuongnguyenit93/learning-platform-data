# Cung cấp cấu hình kết nối động và chờ node sẵn sàng

**Chương: Kiểm thử — Spring Data Cassandra**

Khi kiểm thử tích hợp ứng dụng **Spring Data Cassandra**, bài toán đầu tiên thường không nằm ở phương thức `save()` hay `findById()` mà ở việc **kết nối đến đúng Cassandra đang chạy trong môi trường test**. Với Testcontainers, cổng CQL 9042 trong container được ánh xạ sang một cổng ngẫu nhiên trên máy chạy test. Đồng thời, Cassandra cần thời gian khởi động gossip, storage, native transport và chuẩn bị schema trước khi nhận truy vấn.

Vì thế, một bài test đáng tin cậy cần giải quyết **hai việc riêng biệt**:

1. **Cấp cấu hình kết nối động** cho Spring trước khi tạo `CqlSession`, `CassandraTemplate` và repository.
2. **Chờ Cassandra thực sự sẵn sàng** ở mức cần thiết cho test, không chỉ kiểm tra rằng tiến trình container hoặc cổng TCP đã mở.

Các kỹ thuật trong bài áp dụng cho kiểm thử entity mapping, `CassandraRepository`, `CassandraTemplate` và truy vấn CQL. Chúng cũng tạo nền tảng để kiểm thử partition key, paging và consistency mà không phụ thuộc cổng cố định của máy phát triển.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao `localhost:9042` không phải endpoint đáng tin cậy khi Testcontainers ánh xạ cổng động.
- Sử dụng `@DynamicPropertySource` và `DynamicPropertyRegistry` để truyền host, port, local datacenter, keyspace vào Spring Boot trước lúc tạo kết nối.
- Phân biệt **container đang chạy**, **TCP lắng nghe**, **Driver tạo session thành công**, và **CQL/query/schema đã sẵn sàng**.
- Dùng `CassandraContainer` cùng một phép thăm dò CQL có giới hạn thời gian để tránh race condition lúc khởi động.
- Chuẩn bị keyspace/schema, chạy bài test repository và template có thể lặp lại; chẩn đoán các lỗi thường gặp trong CI.
- Hiểu giới hạn của bài test Cassandra một node khi đánh giá consistency, replication, paging và hiệu năng.

## 2. Vì sao cấu hình Cassandra cần được xác định lúc chạy test?

Trong Docker, `9042` thường là **cổng native CQL bên trong container**. Testcontainers có thể tạo endpoint thật của JVM như:

~~~text
Container: 172.x.x.x:9042
JVM test:  127.0.0.1:32781
~~~

Con số `32781` chỉ là ví dụ; mỗi lần chạy, máy khác hoặc runner CI có thể được cấp một cổng khác. Trên Docker từ xa, `getHost()` thậm chí có thể trả địa chỉ khác `localhost`. Vì vậy cấu hình sau dễ gây test thất bại:

~~~yaml
# Ví dụ cần tránh khi Cassandra do Testcontainers tự khởi động
spring:
  cassandra:
    contact-points: localhost
    port: 9042
~~~

Thay vào đó, lấy host và **mapped port** từ chính container đang chạy, rồi đăng ký chúng vào môi trường Spring.

| Thuộc tính Spring Boot 3.x | Giá trị trong test | Vì sao quan trọng? |
|---|---|---|
| `spring.cassandra.contact-points` | `cassandra.getHost()` | Địa chỉ JVM có thể kết nối tới container |
| `spring.cassandra.port` | `cassandra.getMappedPort(9042)` | Cổng thực tế, không mặc định 9042 |
| `spring.cassandra.local-datacenter` | DC được cấu hình trong Cassandra, ví dụ `datacenter1` | Java Driver 4.x cần biết local DC khi chọn node |
| `spring.cassandra.keyspace-name` | Keyspace test đã được tạo | Repository/template cần keyspace hợp lệ |
| `spring.cassandra.schema-action` | Ví dụ `CREATE_IF_NOT_EXISTS` trong test | Cho phép Spring Data tạo bảng ánh xạ nếu chưa tồn tại |

Trong Spring Boot 2.x, các cấu hình Cassandra được đặt dưới tiền tố `spring.data.cassandra.*`. Bài này sử dụng **Spring Boot 3.x / Spring Data Cassandra với Java Driver 4.x**. Khi áp dụng cho dự án cụ thể, phải đối chiếu tiền tố cấu hình và API của phiên bản đã khai báo.

### 2.1. Trình tự khởi tạo mong muốn

~~~mermaid
flowchart TD
    A["JUnit bắt đầu khởi tạo lớp test"] --> B["Testcontainers start Cassandra"]
    B --> C{"CQL đã truy vấn được?"}
    C -->|"Chưa"| D["Thăm dò lại trong thời hạn có giới hạn"]
    D --> C
    C -->|"Rồi"| E["Tạo keyspace test (nếu chưa có)"]
    E --> F["@DynamicPropertySource cung cấp host, mapped port, DC, keyspace"]
    F --> G["Spring TestContext tạo CqlSession, CassandraTemplate, repository"]
    G --> H["Spring Data tạo/kiểm tra schema test"]
    H --> I["JUnit chạy kiểm thử đọc/ghi và assertion"]
    C -->|"Quá hạn"| J["Fail rõ nguyên nhân khởi động"]
~~~

Điểm mấu chốt là **Spring phải nhận được giá trị cấu hình trước lúc tạo connection factory/session**. Việc thay `application.yml` sau khi Spring context đã chạy không làm session đang tồn tại tự động chuyển sang cổng mới.

### 2.2. `@DynamicPropertySource` hoạt động thế nào?

`@DynamicPropertySource` là tiện ích của Spring TestContext. Một phương thức `static` nhận `DynamicPropertyRegistry` và đăng ký các supplier cung cấp giá trị thuộc tính:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.cassandra.contact-points", cassandra::getHost);
    registry.add("spring.cassandra.port", () -> cassandra.getMappedPort(9042));
    registry.add("spring.cassandra.local-datacenter", () -> "datacenter1");
    registry.add("spring.cassandra.keyspace-name", () -> "integration_test");
}
~~~

Trong ví dụ này, `cassandra` là `CassandraContainer<?>` đã được khởi động. Supplier được Spring đọc khi cần giải quyết thuộc tính; **supplier không thay thế bước `container.start()`**. Nếu Spring dùng thuộc tính khi container chưa start, `getMappedPort(9042)` không có endpoint hợp lệ.

Thuộc tính được đăng ký qua `@DynamicPropertySource` có ưu tiên cao trong môi trường test, thuận lợi khi muốn ghi đè giá trị của `application.yml` hoặc cấu hình profile. Không cần ghi cổng Docker ngẫu nhiên vào file theo dõi bởi Git.

## 3. Khi nào được coi là “node đã sẵn sàng”?

Trạng thái sẵn sàng cần gắn với **việc mà test sắp làm**:

| Mốc quan sát | Điều đã biết | Điều **chưa** được bảo đảm |
|---|---|---|
| Docker báo container `running` | Tiến trình chính đã bắt đầu | Cassandra đã mở CQL |
| Cổng TCP có thể kết nối | Có listener nhận kết nối | Driver có thể bắt tay và thực thi query |
| `CqlSession` khởi tạo thành công | Driver có thể giao tiếp và khám phá node | Keyspace/bảng mà test cần đã tồn tại |
| `SELECT ... FROM system.local` trả kết quả | Native CQL xử lý được truy vấn cơ bản | Schema, RF hay dữ liệu thử đã chuẩn bị đầy đủ |
| Keyspace/bảng được tạo và query kiểm tra thành công | Test có thể bắt đầu thao tác trên schema cần thiết | Cluster nhiều node đã hoàn thành mọi đồng bộ/repair |

`CassandraContainer` cung cấp cơ chế chờ khởi động mặc định của module Testcontainers. Nên dùng cơ chế chuyên biệt này trước. Với bài test cần bảo đảm **CQL đã trả kết quả và keyspace đã có trước khi Spring khởi động**, bổ sung một phép thăm dò CQL là hợp lý.

Không dùng `Thread.sleep(30_000)` cố định rồi cho rằng đã sẵn sàng. Máy phát triển có thể khởi động sau 5 giây, runner CI chậm có thể cần hơn 30 giây. Cách tốt hơn là **thăm dò điều kiện thực tế**, có thời hạn tối đa và báo lỗi gốc khi không đạt.

## 4. Chuẩn bị dependency cho kiểm thử tích hợp

Một dự án Spring Boot dùng Spring Data Cassandra thường có dependency chính `spring-boot-starter-data-cassandra`. Khi kiểm thử, cần `spring-boot-starter-test` và module Cassandra của Testcontainers.

Ví dụ **Maven với Testcontainers 1.x** (phiên bản nên được quản lý bởi BOM phù hợp với Spring Boot):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-cassandra</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>cassandra</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Với Gradle, các dependency tương ứng có thể là:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.testcontainers:cassandra'
~~~

Đoạn mẫu phía dưới dùng package `org.testcontainers.containers.CassandraContainer` của **Testcontainers 1.x**. Một số phiên bản Testcontainers mới có thể đổi tọa độ artifact hoặc package; cần kiểm tra tài liệu theo phiên bản thực tế nếu nâng cấp. Máy/runner chạy bài test phải có môi trường Docker tương thích để Testcontainers tạo container.

## 5. Ví dụ đầy đủ: repository, template và Cassandra khởi động động

Giả sử cần kiểm thử tính năng lưu hồ sơ theo `profile_id`. Bảng Cassandra được thiết kế theo truy vấn truy xuất bằng partition key:

~~~sql
CREATE TABLE profiles_by_id (
    profile_id uuid PRIMARY KEY,
    display_name text
);
~~~

Entity tương ứng (ví dụ trong package `example.cassandra`):

~~~java
package example.cassandra;

import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("profiles_by_id")
public class Profile {
    @PrimaryKey("profile_id")
    private UUID id;

    @Column("display_name")
    private String displayName;

    protected Profile() {
        // Spring Data dùng constructor mặc định để đọc entity.
    }

    public Profile(UUID id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public UUID getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Repository:

~~~java
package example.cassandra;

import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface ProfileRepository extends CassandraRepository<Profile, UUID> {
}
~~~

### 5.1. Test class tự khởi động container và đăng ký cấu hình động

Ví dụ sau sử dụng `@DataCassandraTest` để tải phần cấu hình Cassandra, repository và template; test cần nằm trong cấu trúc package mà Spring Boot nhận diện được cấu hình ứng dụng và repository.

~~~java
package example.cassandra;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.datastax.oss.driver.api.core.CqlSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.cassandra.DataCassandraTest;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.utility.DockerImageName;

@DataCassandraTest
class ProfileRepositoryIntegrationTest {

    private static final String LOCAL_DC = "datacenter1";
    private static final String KEYSPACE = "integration_test";

    private static final CassandraContainer<?> CASSANDRA =
            new CassandraContainer<>(DockerImageName.parse("cassandra:4.1"))
                    .withStartupTimeout(Duration.ofMinutes(5));

    static {
        // 1. Khởi động trước khi Spring đọc supplier của @DynamicPropertySource.
        CASSANDRA.start();

        // 2. Chờ CQL đáp ứng rồi chuẩn bị keyspace cho Spring Data.
        awaitCqlReadyAndCreateKeyspace();
    }

    @DynamicPropertySource
    static void cassandraProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cassandra.contact-points", CASSANDRA::getHost);
        registry.add("spring.cassandra.port", () -> CASSANDRA.getMappedPort(9042));
        registry.add("spring.cassandra.local-datacenter", () -> LOCAL_DC);
        registry.add("spring.cassandra.keyspace-name", () -> KEYSPACE);

        // Chỉ dành cho test: để Spring Data tạo bảng mapped nếu chưa có.
        registry.add("spring.cassandra.schema-action", () -> "CREATE_IF_NOT_EXISTS");
    }

    @Autowired
    private ProfileRepository repository;

    @Autowired
    private CassandraTemplate template;

    @Test
    void savesThroughRepositoryAndReadsThroughTemplate() {
        UUID id = UUID.randomUUID();
        repository.save(new Profile(id, "Lan"));

        Profile fromRepository = repository.findById(id).orElseThrow();
        assertThat(fromRepository.getDisplayName()).isEqualTo("Lan");

        Profile fromTemplate = template.selectOneById(id, Profile.class);
        assertThat(fromTemplate).isNotNull();
        assertThat(fromTemplate.getDisplayName()).isEqualTo("Lan");
    }

    private static void awaitCqlReadyAndCreateKeyspace() {
        long deadline = System.nanoTime() + Duration.ofMinutes(2).toNanos();
        RuntimeException lastFailure = null;

        while (System.nanoTime() < deadline) {
            try (CqlSession probe = CqlSession.builder()
                    .addContactPoint(CASSANDRA.getContactPoint())
                    .withLocalDatacenter(LOCAL_DC)
                    .build()) {

                // Kiểm tra bằng CQL thật, không chỉ bằng trạng thái cổng TCP.
                if (probe.execute("SELECT release_version FROM system.local").one() == null) {
                    throw new IllegalStateException("system.local returned no row");
                }

                // Keyspace đơn node cho kiểm thử; không dùng RF=1 làm mẫu production.
                probe.execute(
                        "CREATE KEYSPACE IF NOT EXISTS integration_test "
                                + "WITH replication = {"
                                + "'class': 'SimpleStrategy', "
                                + "'replication_factor': 1}");
                return;
            } catch (RuntimeException ex) {
                lastFailure = ex;
                try {
                    // Khoảng nghỉ giữa hai phép thăm dò, không phải lời đoán
                    // rằng Cassandra chắc chắn đã sẵn sàng sau hai giây.
                    TimeUnit.SECONDS.sleep(2);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Interrupted while waiting for Cassandra", interrupted);
                }
            }
        }

        throw new IllegalStateException(
                "Cassandra CQL not ready / keyspace not created in time", lastFailure);
    }
}
~~~

**Diễn giải những điểm đáng chú ý:**

1. `CASSANDRA.start()` được gọi trong static initializer, nên trước lúc Spring resolve các supplier và tạo `CqlSession` đã có container để lấy host/mapped port.
2. `getHost()` cùng `getMappedPort(9042)` tạo endpoint ở **góc nhìn JVM test**. Không dùng IP nội bộ Docker hoặc giả định cổng host là 9042.
3. `getContactPoint()` cung cấp endpoint cho phiên `CqlSession` thăm dò; `withLocalDatacenter(LOCAL_DC)` phải khớp với DC thực tế. Ví dụ mặc định Cassandra trong container dùng `datacenter1`; nếu cấu hình image khác, hãy đổi cả hai nơi.
4. Chỉ khi truy vấn `system.local` chạy được, đoạn mã mới tạo keyspace `integration_test`. Điều này tránh trường hợp Spring tạo session với keyspace chưa tồn tại.
5. `CREATE_IF_NOT_EXISTS` để Spring Data chuẩn bị bảng từ entity mapping. Schema hành vi này dành riêng cho môi trường test; hệ thống production thường quản lý schema bằng migration/quy trình triển khai riêng.
6. Bài test khẳng định dữ liệu đã ghi bằng repository có thể đọc lại qua `CassandraTemplate` — tức là cả hai abstraction cùng dùng đúng cấu hình Cassandra.

### 5.2. Vì sao phải tạo keyspace trước Spring context?

Nếu cấu hình `spring.cassandra.keyspace-name=integration_test` nhưng keyspace chưa tồn tại, Driver hoặc quá trình khởi tạo thành phần Spring có thể gặp lỗi như `Keyspace integration_test does not exist`. Lúc này, `schema-action` tạo bảng **không cứu được** một connection đang cần keyspace chưa có.

Trong ví dụ chính, test tạo keyspace **qua session không chọn keyspace trước**, rồi mới để Spring tạo session sử dụng keyspace đó. Một số cách thay thế hợp lệ:

- Chạy script CQL khởi tạo keyspace bằng cơ chế init script của Cassandra Testcontainers.
- Chuẩn bị keyspace từ fixture/migration có thứ tự khởi chạy xác định trước khi Spring tạo session.
- Với test sử dụng Cassandra có sẵn trên CI, chạy bước provisioning idempotent và chờ xác nhận keyspace/schema trước khi dựng ApplicationContext.

Tránh phụ thuộc việc hai component khởi tạo song song rồi “may mắn” một bên tạo keyspace xong trước bên còn lại.

## 6. Cách thay thế: lifecycle của JUnit và init script

Nếu muốn Testcontainers quản lý việc start/stop cho từng lớp test, có thể dùng `@Testcontainers` và `@Container` (cần thêm dependency `org.testcontainers:junit-jupiter` với Testcontainers 1.x). Với cách này, **chuẩn bị keyspace bằng init script của container** để không phải tự mở phiên CQL trong static initializer.

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.data.cassandra.DataCassandraTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@DataCassandraTest
class CassandraWithInitScriptTest {

    @Container
    static final CassandraContainer<?> CASSANDRA =
            new CassandraContainer<>(DockerImageName.parse("cassandra:4.1"))
                    .withStartupTimeout(Duration.ofMinutes(5))
                    .withInitScript("cassandra/init-test.cql");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.cassandra.contact-points", CASSANDRA::getHost);
        registry.add("spring.cassandra.port", () -> CASSANDRA.getMappedPort(9042));
        registry.add("spring.cassandra.local-datacenter", () -> "datacenter1");
        registry.add("spring.cassandra.keyspace-name", () -> "integration_test");
        registry.add("spring.cassandra.schema-action", () -> "CREATE_IF_NOT_EXISTS");
    }

    @Test
    void contextCanConnect() {
        // Các assertion repository/template được viết như ví dụ trước.
    }
}
~~~

Nội dung file `src/test/resources/cassandra/init-test.cql`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS integration_test
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
~~~

Hai ví dụ mô tả **hai lựa chọn độc lập**, không kết hợp cả hai cơ chế khởi tạo keyspace vào cùng một test. Mẫu đầu minh họa kiểm tra readiness trực tiếp bằng CQL; mẫu này tiện hơn khi có script schema đã kiểm soát trong test resources. Dù dùng cách nào, một phép query smoke test vẫn hữu ích nếu yêu cầu của test cao hơn mức readiness mặc định của Testcontainers.

**Vòng đời cần chú ý:** Với `@Container` static, JUnit extension start/stop container theo lớp test. Spring có cơ chế **cache ApplicationContext** giữa các lớp. Nếu hai lớp có chung cấu hình nhưng dùng container khác cổng, context tái sử dụng có thể trỏ về endpoint đã bị stop. Hãy dùng một container chia sẻ ổn định cho các test dùng chung context, hoặc làm mới context có chủ đích, ví dụ `@DirtiesContext` ở lớp phù hợp. Không bật reuse container toàn cục mà không hiểu yêu cầu cô lập dữ liệu giữa các test.

## 7. Kiểm tra readiness chính xác: từ TCP đến CQL

### 7.1. Tại sao wait-for-port có thể báo “xong” quá sớm?

Một health check chỉ mở socket đến 9042 chứng minh rằng có process đang nhận kết nối TCP. Cassandra vẫn có thể đang khởi tạo các thành phần nội bộ, chưa ổn định schema hoặc chưa sẵn sàng trả truy vấn. Một lệnh `SELECT release_version FROM system.local` qua Java Driver kiểm tra được nhiều lớp hơn: connect, protocol handshake, session và thực thi CQL.

Khi có **cluster nhiều node**, khả năng query một coordinator trả lời được chưa có nghĩa tất cả replica đã vào trạng thái phục vụ, schema đã thống nhất, hay dữ liệu mới được replicate đủ. Với bài test consistency hoặc failover, phải thăm dò đúng điều kiện mà test cần, thay vì lấy kết quả `system.local` của một node làm tiêu chuẩn cho toàn cluster.

### 7.2. Thời hạn chờ và cách xử lý lỗi

Mẫu thăm dò đúng hướng có các đặc điểm:

| Thành phần | Khuyến nghị | Ý nghĩa |
|---|---|---|
| Điều kiện | Truy vấn CQL thật trả kết quả; nếu cần thì xác nhận keyspace/bảng | Kiểm tra khả năng dùng được |
| Deadline | Ví dụ 2 phút sau khi container start | Không để CI treo vô hạn |
| Poll interval | Ví dụ 2 giây | Tránh bắn yêu cầu dồn dập khi node khởi động |
| Error handling | Lưu exception cuối làm `cause` khi quá hạn | Giúp phân biệt kết nối, auth, local DC, schema |
| Interrupt | Khôi phục cờ interrupt và fail | Cho phép test runner dừng công việc đúng cách |
| Failure | Fail test setup rõ ràng | Không biến lỗi hạ tầng thành kết quả kiểm thử nghiệp vụ |

Đừng bọc toàn bộ test trong `catch (Exception e)` rồi bỏ qua hoặc cho test pass. Một môi trường Cassandra không hoạt động phải được báo là **setup/infrastructure failure**, không được trình bày thành “repository hoạt động”.

### 7.3. Điều chỉnh deadline theo CI

`withStartupTimeout(Duration.ofMinutes(5))` trong ví dụ đặt hạn chờ khởi động container; vòng thăm dò CQL đặt thêm hạn chờ hữu hạn cho giai đoạn sau đó. Hai ngưỡng là **giới hạn**, không phải mỗi test bắt buộc phải đợi đủ số phút. Test sẽ tiếp tục ngay khi điều kiện thành công.

Nếu Cassandra khởi động rất chậm trên runner dùng chung, hãy đo thời gian bootstrap thực tế, CPU/memory pressure và log container trước khi tăng timeout. Không nên chỉnh deadline để che việc image, Docker daemon hoặc cấu hình tài nguyên đang có vấn đề.

## 8. Kiểm thử với nhiều đối tượng Spring Data Cassandra

Kết nối động cần đi xuyên suốt các thành phần Spring Data. Khi Spring tạo chúng từ cùng cấu hình, chúng sẽ cùng trỏ đến Cassandra test:

~~~mermaid
flowchart LR
    P["@DynamicPropertySource"] --> S["CqlSession / SessionFactory"]
    S --> R["CassandraRepository"]
    S --> T["CassandraTemplate"]
    S --> Q["CQL operations"]
    R --> K["Keyspace test"]
    T --> K
    Q --> K
~~~

### 8.1. Entity mapping và khóa phân vùng

Trường `@PrimaryKey("profile_id")` trong ví dụ tương ứng partition key đơn của bảng. Test nên xác nhận được round-trip: ghi qua repository, đọc lại qua repository hoặc template và so sánh giá trị. Nếu entity đổi `@Column` hoặc cách đặt tên cột, một test chạy trên Cassandra thật sẽ phát hiện sai khác giữa mapping và schema rõ hơn so với mock repository.

Đối với bảng có partition key tổng hợp hoặc clustering key, hãy tạo fixture thể hiện đúng khóa và truy vấn mà ứng dụng thực hiện. Đừng dùng dữ liệu test tình cờ nằm ở một partition quá nhỏ để kết luận mô hình sẽ chịu tải tốt trong production.

### 8.2. Paging

Ví dụ khi test luồng phân trang, hãy tạo đủ số row để buộc Driver đọc nhiều page. Cấu hình `fetchSize`/page size phải nhất quán với test, rồi kiểm tra không mất hoặc lặp row khi lấy các trang. Cần phân biệt **Driver paging state** với số trang tự đặt ở tầng API; một truy vấn có nhiều page không nhất thiết tương đương với phân trang `LIMIT/OFFSET` như database quan hệ.

Sự kiện node sẵn sàng ở đầu test chỉ bảo đảm điều kiện kết nối ban đầu. Khi đo độ trễ truy vấn phân trang, còn phải kiểm soát số partition, clustering order, tombstone, kích thước dữ liệu và số round-trip. Testcontainers một node không phải phép đo p95/p99 đại diện cho production.

### 8.3. Consistency và replication

Keyspace demo dùng `SimpleStrategy` với replication factor 1 để thiết lập nhanh một node. Đây là **điều kiện test chức năng**, không phải bài test đầy đủ về nhất quán phân tán. Với RF=1, các kịch bản như `LOCAL_QUORUM` của nhiều replica, node failure, replica lag hoặc read repair cần cluster nhiều node và keyspace/CL thiết kế tương ứng.

Không dựa vào việc repository `save()` thành công trong cluster đơn để kết luận rằng cùng thao tác sẽ thành công khi production yêu cầu mức consistency cao hơn hoặc replica phân bố qua nhiều DC.

### 8.4. Reactive và template tùy biến

Nếu ứng dụng dùng `ReactiveCassandraRepository` hoặc `ReactiveCassandraTemplate`, các thành phần đó cũng cần cùng endpoint động. Khác biệt chủ yếu nằm ở thời điểm truy vấn được kích hoạt và cách quan sát lỗi trong `Mono`/`Flux`. Khi kiểm thử reactive, phải subscribe/assert đầy đủ bằng công cụ test phù hợp, tránh gọi phương thức tạo publisher mà không kích hoạt luồng.

Nếu ứng dụng tự khởi tạo `CqlSession` bằng bean cấu hình riêng, hãy kiểm tra rằng bean ấy thực sự đọc các thuộc tính động. Một bean hard-code `localhost:9042` có thể bỏ qua hoàn toàn `@DynamicPropertySource` mặc dù annotation đã đăng ký đúng.

## 9. Chẩn đoán lỗi kết nối và khởi động

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh và xử lý |
|---|---|---|
| `IllegalStateException` khi gọi `getMappedPort` | Container chưa start | Kiểm tra thứ tự lifecycle; khởi động trước khi supplier được đánh giá |
| Driver không tìm thấy node / `AllNodesFailedException` | Sai host/port, Docker networking, node chưa sẵn sàng | Log `getHost()` và mapped port, kiểm tra lỗi theo node và log Cassandra |
| `NoNodeAvailableException` | Driver không có node phù hợp/sẵn sàng | Kiểm tra endpoint, local DC, kết nối và node state |
| “Local datacenter ...” không hợp lệ | Giá trị DC không khớp node thực | Kiểm tra `system.local`/image config, truyền `spring.cassandra.local-datacenter` chính xác |
| “Keyspace does not exist” | Spring session khởi tạo trước khi tạo keyspace | Khởi tạo keyspace trước Spring context; không chỉ bật tạo bảng |
| “Unconfigured table” | SchemaAction không chạy, entity không được scan hoặc migration chưa chạy | Kiểm tra keyspace, entity mapping, schema-action, thứ tự setup |
| Test pass local nhưng fail CI | Thiếu Docker, tài nguyên yếu, endpoint khác localhost | Kiểm tra runner, image pull, container log, mapped host/port, timeout |
| Test đầu pass, test sau lỗi kết nối | Context cache trỏ tới container đã stop | Đồng bộ vòng đời context/container hoặc dùng `@DirtiesContext` |
| Test chậm bất thường | Boot Cassandra tốn tài nguyên hoặc tạo mới container cho từng method | Chia sẻ container theo phạm vi phù hợp, giảm fixture, đo boot time |
| Bị lỗi đăng nhập/TLS | Test cluster và cấu hình client không cùng chế độ security | Đăng ký credentials/SSL tương ứng; không lưu secret trong log |

### 9.1. Đừng chẩn đoán chỉ dựa trên exception bề ngoài

Khi Driver báo `AllNodesFailedException`, các lỗi cụ thể theo từng node có thể nằm trong `getAllErrors()` (tùy phiên bản Java Driver). Một node từ chối kết nối, một node hết timeout, hoặc Driver chọn sai datacenter sẽ có cách xử lý khác nhau. Có thể ghi loại lỗi, node identifier, test class và trace ID; tránh log mật khẩu hoặc dữ liệu cá nhân trong fixture.

### 9.2. Lỗi readiness khác lỗi assertion nghiệp vụ

Phân loại nhanh:

- **Container không start / không đạt CQL probe:** môi trường test chưa sẵn sàng. Cần xem Docker, startup logs, host/port, datacenter, tài nguyên.
- **CQL probe thành công nhưng Spring context lỗi:** xem keyspace, mapping, bean config, schema-action hoặc cấu hình Spring Boot.
- **Spring context thành công nhưng assertion sai:** xem repository query, entity mapping, dữ liệu fixture, consistency và logic nghiệp vụ.

Phân chia này giúp tránh sửa logic repository khi thực tế nguyên nhân là một port Docker đã đổi.

## 10. Thực hành tốt cho bộ test ổn định

### 10.1. Cô lập và dọn dữ liệu

Tạo ID ngẫu nhiên cho dữ liệu thử; xóa bản ghi do chính test tạo khi dùng chung keyspace hoặc thiết kế fixture không phụ thuộc thứ tự thực thi. Tránh dựa vào trạng thái từ bài test trước. Nếu test chạy song song, cần thiết kế keyspace/partition test để các luồng không ghi đè lẫn nhau.

Đối với test yêu cầu khởi tạo schema giống production, nên áp dụng **cùng migration/schema contract**. `CREATE_IF_NOT_EXISTS` thuận tiện cho ví dụ đơn giản nhưng không kiểm tra rằng migration sản xuất có đầy đủ index, UDT, cột và bảng mà ứng dụng cần.

### 10.2. Chọn phạm vi test phù hợp

| Loại test | Hạ tầng | Nên kiểm tra |
|---|---|---|
| Unit test | Mock repository, không cần Cassandra | Quy tắc nghiệp vụ, mapping lỗi sang kết quả API |
| Slice test `@DataCassandraTest` | Cassandra Testcontainers | Entity/repository/template, CQL đơn giản, mapping |
| Integration test `@SpringBootTest` | Cassandra và các thành phần thực sự cần thiết | Toàn luồng service/config/event, kết nối Spring |
| Cluster/failure test | Cassandra nhiều node/DC, kiểm soát lỗi mạng/node | Consistency, retry, failover, replication |
| Performance test | Dataset và topology đại diện | Partition hotspot, paging latency, throughput, p95/p99 |

Không cần dựng cluster nhiều node cho mọi test CRUD. Ngược lại, không dùng kết quả của một bài test một node để khẳng định về hành vi phân tán của hệ thống.

### 10.3. Cấu hình dành riêng cho kiểm thử

Một vài nguyên tắc quan trọng:

- Cấu hình động phải đến từ **đúng Cassandra instance** mà bài test đã start.
- Không ghi host/port ngẫu nhiên vào `application.yml` hay source code cố định.
- Các giá trị DC, keyspace, credentials và SSL phải nhất quán giữa node và Driver.
- Container readiness cần có **timeout hữu hạn** và giữ nguyên nguyên nhân thất bại cuối cùng.
- DDL tạo keyspace/bảng phải có thứ tự xác định trước các assertion truy vấn.
- Test context cache và container lifecycle phải tương thích; dùng lại context chỉ khi endpoint còn sống.
- Chỉ thêm retry có giới hạn cho **giai đoạn chờ hạ tầng**; không retry vô hạn các assertion thất bại hoặc lỗi CQL sai.

## 11. Tình huống tự kiểm tra

**Tình huống A.** Cassandra Testcontainers báo `getMappedPort(9042) = 32817` nhưng `application-test.yml` vẫn cấu hình `port: 9042`. Bài test báo không kết nối được. Cần sửa ở đâu?

**Gợi ý:** Đăng ký `spring.cassandra.port` qua `@DynamicPropertySource` bằng mapped port của đúng container; lấy host qua `getHost()` thay vì luôn giả định `localhost`.

**Tình huống B.** Docker báo container `running` và port 9042 mở; `@DataCassandraTest` vẫn lỗi “Keyspace integration_test does not exist”. Có phải lỗi Java Driver?

**Gợi ý:** Không nhất thiết. Native CQL có thể đã hoạt động nhưng keyspace test chưa được tạo. Chuẩn bị keyspace trước khi Spring khởi tạo session sử dụng nó.

**Tình huống C.** Một static `@Container` dừng sau lớp test thứ nhất, trong khi Spring dùng lại ApplicationContext cho lớp thứ hai. Lớp sau gặp lỗi kết nối. Phương án nào phù hợp?

**Gợi ý:** Bảo đảm container còn sống trong toàn vòng đời context được cache, hoặc tách/đánh dấu dirty để Spring tạo context mới với endpoint còn hoạt động.

**Tình huống D.** Test repository thành công với Cassandra một node, RF=1. Có thể xem đó là bằng chứng `LOCAL_QUORUM` sẽ hoạt động đúng khi một replica production bị down không?

**Gợi ý:** Không. Bài test này chỉ xác nhận chức năng truy cập cơ bản; cần kịch bản cluster nhiều replica với RF, DC và consistency được cấu hình phù hợp.

**Tình huống E.** Một pipeline lúc nhanh lúc chậm. Có nên thay vòng thăm dò CQL bằng `Thread.sleep(120000)` để “chắc chắn” Cassandra khởi động xong?

**Gợi ý:** Không. Giữ phép thăm dò theo điều kiện, có deadline và khoảng nghỉ giữa các lần thử; khi quá hạn, báo nguyên nhân kỹ thuật để điều tra.

## 12. Tổng kết

Trong **Spring Data Cassandra**, kiểm thử tích hợp đáng tin cậy bắt đầu từ việc kết nối đúng Cassandra và chờ node đủ sẵn sàng để phục vụ truy vấn. `@DynamicPropertySource` giải quyết **cấu hình kết nối động**, còn `CassandraContainer` và thăm dò CQL giải quyết **thứ tự khởi động và readiness**. Hai cơ chế bổ sung cho nhau.

Sau khi kết nối ổn định, cần chuẩn bị keyspace/schema trước lúc dùng `CassandraRepository`, `CassandraTemplate` hoặc CQL. Test phải phân biệt lỗi hạ tầng với assertion nghiệp vụ, xử lý vòng đời context/container nhất quán và nhớ rằng test một node chỉ xác nhận một phần hành vi của Cassandra phân tán.

## Tài liệu tham khảo

- [Spring Framework — Dynamic Property Sources trong TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Testcontainers Java — Cassandra module](https://java.testcontainers.org/modules/databases/cassandra/)
- [Spring Boot — Testcontainers support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html)
