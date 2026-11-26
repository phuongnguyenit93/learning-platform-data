# Tùy chỉnh DriverConfigLoader và cấu hình Java Driver

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt cấu hình kết nối của **Spring Boot/Spring Data Cassandra** với cấu hình vận hành của **Apache Cassandra Java Driver 4.x**.
- Giải thích vai trò của `DriverConfigLoader`, `DriverConfig`, `DriverExecutionProfile` và `CqlSession`; chọn cách nạp cấu hình qua HOCON, file bên ngoài hoặc mã Java.
- Sử dụng `DriverConfigLoaderBuilderCustomizer` đúng cách khi Spring Boot đang tự quản lý `CqlSession`, thay vì vô tình tạo thêm session và bỏ qua cấu hình của ứng dụng.
- Điều chỉnh timeout, consistency level, paging, connection pool, retry/reconnection và metrics trên cơ sở tải thực tế.
- Đọc cấu hình đang có hiệu lực, dùng execution profile cho từng loại truy vấn, xác định giới hạn của hot reload và xử lý sự cố cấu hình.
- Liên hệ cấu hình driver với phân vùng, thiết kế bảng theo truy vấn và các bảo đảm nhất quán của Cassandra.

Bài thuộc **SPRING_DATA_CASSANDRA**: truy cập Apache Cassandra thông qua entity mapping, repository, `CassandraTemplate` và CQL; đồng thời học partition key, paging, consistency và kiểm soát hiệu năng trong hệ thống phân tán. Chủ đề ở đây là **tùy chỉnh Java Driver** mà các API Spring Data sử dụng ở phía dưới. Một driver được cấu hình đúng giúp truy cập Cassandra ổn định nhưng không thể thay thế việc thiết kế schema và partition key đúng với truy vấn.

> **Phạm vi phiên bản:** Ví dụ tập trung vào Cassandra Java Driver **4.x** (API dưới package `com.datastax.oss.driver.api`) và Spring Boot dùng cấu hình `spring.cassandra.*`. Tên import của một số customizer thay đổi giữa Spring Boot 3.x và 4.x; bài chỉ rõ điểm khác biệt. Hãy dùng tài liệu tương ứng với phiên bản dự án khi áp dụng.

## 1. DriverConfigLoader nằm ở đâu trong kiến trúc?

Một yêu cầu đọc từ repository đi qua nhiều lớp:

~~~mermaid
flowchart TD
    A[Controller / Service] --> B[Spring Data Cassandra Repository]
    A --> C[CassandraTemplate]
    B --> D[Spring Data mapping và Cassandra operations]
    C --> D
    D --> E[CqlSession]
    E --> F[Apache Cassandra Java Driver]
    G[DriverConfigLoader] --> F
    F --> H[Cluster Cassandra / CQL]
~~~

Vai trò cụ thể:

| Thành phần | Trách nhiệm |
| --- | --- |
| Spring Data entity mapping | Ánh xạ dòng Cassandra sang Java object qua `@Table`, `@PrimaryKey`, `@Column`... |
| Repository / `CassandraTemplate` | Tạo và thực thi thao tác dữ liệu; không trực tiếp quản lý connection pool của Java Driver |
| `CqlSession` | Đầu mối thực thi CQL, quản lý kết nối tới cluster và metadata; thường được dùng lại suốt vòng đời ứng dụng |
| `DriverConfigLoader` | Nạp, kết hợp và có thể nạp lại các tùy chọn driver |
| `DriverConfig` / `DriverExecutionProfile` | Cấu hình đã được diễn giải, gồm profile mặc định và các profile đặt tên |
| Cassandra cluster | Phân bố partition, replica, phối hợp đọc/ghi theo consistency level |

Một ứng dụng Spring Boot thông thường đã có cơ chế tự cấu hình `CqlSession` từ `spring.cassandra.*`. Khi cần điều chỉnh driver, hãy ưu tiên thay đổi cấu hình thông qua **Boot properties**, **file cấu hình do Boot nạp** hoặc **customizer bean**. Chỉ tự xây dựng `CqlSession` khi chủ động nhận trách nhiệm về toàn bộ cấu hình và vòng đời của session đó.

### 1.1. Vì sao không cấu hình giống JDBC?

Java Driver 4.x sử dụng kết nối Cassandra binary protocol bất đồng bộ, có thể xử lý nhiều request đồng thời trên một connection. Pool tồn tại theo node chứ không phải mô hình “mỗi request mượn một connection” giống nhiều ứng dụng JDBC.

Do đó:

- Mở một `CqlSession` mới cho mỗi HTTP request là rất tốn kém và gây áp lực kết nối/metadata.
- Tăng `pool.local.size` một cách tùy tiện có thể tăng tài nguyên mà không cải thiện throughput.
- Timeout hoặc retry của driver liên quan cả network, số replica phản hồi, tốc độ truy vấn và sức khỏe cluster.
- Một truy vấn dùng `ALLOW FILTERING` hoặc partition key sai vẫn có thể chậm dù timeout đã được nới rộng.

## 2. Ba lớp cấu hình thường gặp

### 2.1. Cấu hình Spring Boot: `application.yml`

Đây là nơi nên bắt đầu nếu ứng dụng dùng Spring Boot và chỉ cần các tùy chọn phổ biến.

~~~yaml
spring:
  cassandra:
    contact-points:
      - cassandra-1.internal
      - cassandra-2.internal
      - cassandra-3.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: order_service
    session-name: order-api
    request:
      timeout: 2s
      consistency: LOCAL_QUORUM
      page-size: 500
    connection:
      connect-timeout: 5s
      init-query-timeout: 5s
    schema-action: none
~~~

Giải thích:

- `contact-points` là các node **khởi đầu khám phá cluster**, không phải danh sách bắt buộc đầy đủ mọi replica. Ưu tiên contact point thuộc DC cục bộ.
- `local-datacenter` phải đúng tên data center mà cluster công bố. Nó ảnh hưởng chính sách định tuyến của driver và các mức consistency `LOCAL_*`.
- `keyspace-name` chọn keyspace để Spring Data làm việc; không tự tạo hoặc thay đổi replication factor.
- `request.timeout` là giới hạn chờ ở phía client; không phải thời gian server bảo đảm xử lý xong.
- `request.consistency` áp dụng mức consistency mặc định cho yêu cầu nếu statement không ghi đè.
- `request.page-size` điều khiển số hàng gợi ý trong **một trang dữ liệu mạng**, không phải `LIMIT` của CQL hay số trang của API người dùng.
- `schema-action: none` giúp tránh để nhiều instance dịch vụ tự ý điều chỉnh schema production khi khởi động.

Những giá trị timeout, page size và CL ở trên là **điểm bắt đầu để thử nghiệm**, không phải mặc định đúng cho mọi workload. Ví dụ, `LOCAL_QUORUM` trong cluster RF = 1 có ý nghĩa/khả năng chịu lỗi khác hoàn toàn RF = 3.

### 2.2. File cấu hình của Java Driver: HOCON

Driver 4.x dùng **Typesafe Config/HOCON**, với các option nằm dưới tiền tố `datastax-java-driver`. Driver JAR có `reference.conf` chứa mặc định; file ứng dụng chỉ cần khai báo những giá trị muốn thay đổi.

Ví dụ file `src/main/resources/cassandra-driver.conf`:

~~~hocon
datastax-java-driver {
  // Không trùng lặp các thuộc tính Boot đã kiểm soát,
  // trừ khi bạn có chủ đích xác định thứ tự ưu tiên.
  advanced {
    connection {
      pool {
        local.size = 1
      }
    }

    reconnection-policy {
      class = ExponentialReconnectionPolicy
      base-delay = 1 second
      max-delay = 30 seconds
    }

    metrics {
      session.enabled = [ connected-nodes, cql-requests ]
      node.enabled = [ pool.open-connections, pool.in-flight ]
    }
  }

  profiles {
    export {
      basic.request.timeout = 15 seconds
      basic.request.page-size = 1000
    }
  }
}
~~~

Để Spring Boot nạp file này:

~~~yaml
spring:
  cassandra:
    config: classpath:cassandra-driver.conf
~~~

**Lưu ý quan trọng:** Trong ứng dụng Spring Boot, không nên giả định Boot tự đọc `application.conf` ở classpath giống như khi dùng Java Driver trực tiếp. Hãy khai báo `spring.cassandra.config` để Boot nạp file tài nguyên driver dự định sử dụng. Với một option có mặt ở cả `spring.cassandra.*` và file driver, **Spring Boot property được ưu tiên** theo cơ chế auto-configuration của Boot. Trong ứng dụng Java thuần không dùng Boot, driver mặc định đọc `application.conf` theo cơ chế Typesafe Config.

HOCON không phải YAML. Ví dụ thời lượng trong HOCON là `2 seconds`, còn Spring Boot YAML thường dùng `2s`. Không đặt các khóa `spring.cassandra.*` trực tiếp vào file HOCON hay `datastax-java-driver.*` dưới cây `spring.cassandra` rồi mong driver hiểu.

### 2.3. Tùy chỉnh bằng Java: `DriverConfigLoader`

Khi thông số được tính toán từ cấu hình ứng dụng hoặc cần kiểm soát nguồn nạp, driver cung cấp API lập trình:

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.time.Duration;

DriverConfigLoader loader =
    DriverConfigLoader.programmaticBuilder()
        .withDuration(DefaultDriverOption.REQUEST_TIMEOUT,
                      Duration.ofSeconds(2))
        .withInt(DefaultDriverOption.REQUEST_PAGE_SIZE, 500)
        .withString(DefaultDriverOption.REQUEST_CONSISTENCY,
                    "LOCAL_QUORUM")
        .startProfile("export")
            .withDuration(DefaultDriverOption.REQUEST_TIMEOUT,
                          Duration.ofSeconds(15))
            .withInt(DefaultDriverOption.REQUEST_PAGE_SIZE, 1000)
        .endProfile()
        .build();
~~~

`DefaultDriverOption` định nghĩa tên và kiểu của option. Các hàm như `withDuration`, `withInt`, `withString` cần đúng kiểu tương ứng. Ví dụ `REQUEST_TIMEOUT` nhận `Duration`; truyền chuỗi `"2s"` vào `withString` cho option này là sai loại.

`programmaticBuilder()` vẫn dùng mặc định từ `reference.conf` và có thể kết hợp cấu hình từ classpath; các override lập trình có ưu tiên cao hơn các file ứng dụng mặc định của driver, còn JVM system properties có thể có ưu tiên cao hơn. Đừng dùng nó để sao chép thủ công hàng trăm giá trị mặc định của driver.

## 3. Sử dụng DriverConfigLoader trong Java Driver thuần

Đây là ví dụ dành cho ứng dụng **không dùng Spring Boot auto-configuration**:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.net.InetSocketAddress;
import java.time.Duration;

DriverConfigLoader loader =
    DriverConfigLoader.programmaticBuilder()
        .withDuration(DefaultDriverOption.REQUEST_TIMEOUT,
                      Duration.ofSeconds(3))
        .withInt(DefaultDriverOption.REQUEST_PAGE_SIZE, 500)
        .build();

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("datacenter1")
        .withKeyspace("order_service")
        .withConfigLoader(loader)
        .build()) {

    session.execute("SELECT * FROM orders_by_id WHERE order_id = "
        + "11111111-1111-4111-8111-111111111111");
}
~~~

Cấu hình `datacenter1` và `order_service` chỉ là ví dụ; DC và keyspace phải tồn tại trong cluster thật. `try-with-resources` bảo đảm đóng session khi chương trình độc lập kết thúc. Đối với server Spring Boot, session thường được dùng lại và do container Spring quản lý vòng đời.

Ngoài `programmaticBuilder()` còn các cách nạp:

| API | Khi nào dùng | Chú ý |
| --- | --- | --- |
| `DriverConfigLoader.fromClasspath("cassandra-driver")` | Cấu hình driver được đóng gói với ứng dụng Java thuần | Tham số là tên gốc, driver tìm `cassandra-driver.conf` / `.json` / `.properties` trong classpath |
| `DriverConfigLoader.fromFile(file)` / `fromPath(path)` | File cấu hình được mount vào container hoặc nằm ngoài JAR | Cần quyền đọc, kế hoạch cập nhật/restart |
| `DriverConfigLoader.fromUrl(url)` | Tài nguyên cấu hình qua URL có thể truy cập | Cần bảo vệ đường truyền, tính sẵn sàng và nguồn cấu hình |
| `DriverConfigLoader.fromString(hocon)` | Cấu hình HOCON tạo động trong bộ nhớ | Không hỗ trợ nạp lại động kiểu loader file |
| `DriverConfigLoader.programmaticBuilder()` | Ghi đè một số option có kiểu xác định bằng Java | Vẫn kế thừa cấu hình mặc định; rõ ràng khi review |
| `DriverConfigLoader.fromMap(optionsMap)` | Muốn quản lý toàn bộ option trong bộ nhớ | Phải cung cấp đủ option bắt buộc; có thể khởi đầu với `OptionsMap.driverDefaults()` |

Không đưa password hoặc private key trực tiếp vào nội dung ví dụ và commit cùng mã nguồn. Nếu dùng file mount, cần quản lý quyền và cơ chế thay đổi cấu hình nhất quán giữa các instance.

## 4. Tùy chỉnh đúng cách trong Spring Boot

### 4.1. Ưu tiên DriverConfigLoaderBuilderCustomizer

Spring Boot có bean interface `DriverConfigLoaderBuilderCustomizer` để can thiệp vào builder driver **trước khi Boot tạo `DriverConfigLoader`**. Cách này phù hợp khi bạn chỉ cần thêm tùy chọn nâng cao mà Boot properties chưa biểu diễn, trong khi vẫn giữ nguyên session do Boot quản lý.

Ví dụ với **Spring Boot 3.x**:

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import java.time.Duration;
import org.springframework.boot.autoconfigure.cassandra.DriverConfigLoaderBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CassandraDriverConfiguration {

    @Bean
    DriverConfigLoaderBuilderCustomizer driverTuning() {
        return builder -> {
            builder.withInt(
                DefaultDriverOption.CONNECTION_POOL_LOCAL_SIZE, 1);
            builder.withDuration(
                DefaultDriverOption.RECONNECTION_BASE_DELAY,
                Duration.ofSeconds(1));
            builder.withDuration(
                DefaultDriverOption.RECONNECTION_MAX_DELAY,
                Duration.ofSeconds(30));
        };
    }
}
~~~

Ví dụ này minh họa API; `local.size = 1` thường đã là giá trị mặc định của Driver 4.x và không có nghĩa tăng throughput. Thực tế chỉ thêm customizer khi cần thay đổi có đo đạc, hoặc khi muốn cố định rõ chính sách theo môi trường.

Với **Spring Boot 4.x**, import interface tương ứng chuyển sang:

~~~java
import org.springframework.boot.cassandra.autoconfigure.DriverConfigLoaderBuilderCustomizer;
~~~

Package API của Java Driver (`com.datastax.oss.driver.api.core.config.*`) vẫn giữ cách gọi trong các ví dụ trên. Khi dùng một bản Spring Boot cụ thể, hãy kiểm tra dependency và package tương ứng, không trộn import Boot 3 với Boot 4.

### 4.2. CqlSessionBuilderCustomizer khác gì?

`CqlSessionBuilderCustomizer` cho phép can thiệp vào **`CqlSessionBuilder`** trước khi Boot xây dựng session, ví dụ thiết lập đặc điểm tạo session mà builder hỗ trợ. Nó không phải lớp ưu tiên cho việc thay đổi `REQUEST_TIMEOUT` hoặc `REQUEST_PAGE_SIZE`, vì đó là option của driver config.

So sánh:

| Nhu cầu | Điểm mở rộng nên xem xét |
| --- | --- |
| Contact points, keyspace, local DC, CL, page size, request timeout phổ biến | `spring.cassandra.*` |
| Option driver chưa có Boot property, chẳng hạn một số reconnection/pool tuning | `DriverConfigLoaderBuilderCustomizer` |
| Cấu hình nhiều profile, nhiều option nâng cao dễ review | File HOCON + `spring.cassandra.config` |
| Tùy biến thao tác xây dựng `CqlSession` | `CqlSessionBuilderCustomizer` |
| Tự quản lý ứng dụng Java thuần | `DriverConfigLoader` + `CqlSession.builder()` |

**Không tự đăng ký thêm `@Bean CqlSession` chỉ để thay đổi một timeout.** Điều đó có thể làm Boot auto-configuration ngừng cung cấp bean mặc định và buộc ứng dụng tự xử lý contact points, authentication, SSL, keyspace, lifecycle cùng các tích hợp với Spring Data.

### 4.3. Thứ tự ưu tiên cần hiểu rõ

Có hai tình huống riêng:

**Java Driver thuần:** mặc định Typesafe Config ưu tiên system properties, rồi các file `application.conf`/`application.json`/`application.properties` trên classpath và `reference.conf`. Nếu dùng `programmaticBuilder()`, override lập trình được đặt trên các file ứng dụng mặc định. Một loader đọc file riêng cũng dùng fallback về cấu hình reference của driver.

**Spring Boot:** Boot tự xây dựng loader và chuyển các `spring.cassandra.*` tương ứng sang cấu hình driver; khi một option trùng giữa Spring properties và file được chỉ định bằng `spring.cassandra.config`, giá trị từ Spring properties chiếm ưu tiên. Nếu có nhiều customizer cùng sửa một option, thứ tự áp dụng phải được quản lý tường minh và xác minh ở runtime; đừng dựa vào thứ tự đăng ký bean ngẫu nhiên.

Nguyên tắc vận hành dễ kiểm soát: chỉ định **một nơi sở hữu cho mỗi option** (ví dụ timeout/CL ở Boot YAML, connection pool và execution profiles ở HOCON) rồi kiểm tra giá trị hiệu lực.

## 5. Execution profile cho nhiều loại request

Một dịch vụ đơn hàng thường có hai nhóm truy vấn:

1. **Tra cứu online:** trả chi tiết đơn theo `order_id` hoặc danh sách ngắn theo `customer_id`, cần phản hồi nhanh.
2. **Xuất dữ liệu:** đọc tuần tự nhiều trang thuộc các partition đã biết, cho phép xử lý lâu hơn nhưng phải giới hạn tài nguyên.

Không nên nâng timeout cho mọi request lên 30 giây chỉ vì một luồng export cần nhiều thời gian hơn. Dùng **execution profile** để tách chính sách:

~~~hocon
datastax-java-driver {
  basic {
    request {
      timeout = 2 seconds
      page-size = 200
      consistency = LOCAL_QUORUM
    }
  }

  profiles {
    export {
      basic.request.timeout = 15 seconds
      basic.request.page-size = 1000
    }

    fast-read {
      basic.request.timeout = 1 second
      basic.request.page-size = 100
    }
  }
}
~~~

Profile có tên kế thừa các tùy chọn từ default profile, trừ các option ghi đè. Do đó `export` vẫn dùng `LOCAL_QUORUM` trong ví dụ này.

Cách chọn profile tại API Java Driver:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement statement = SimpleStatement.builder(
        "SELECT order_id, created_at, status "
      + "FROM orders_by_customer_month "
      + "WHERE customer_id = ? AND month_bucket = ?")
    .addPositionalValue(customerId)
    .addPositionalValue(monthBucket)
    .setExecutionProfileName("export")
    .build();

session.execute(statement);
~~~

Truy vấn trên giả định bảng có partition key ghép `(customer_id, month_bucket)` và schema CQL phù hợp. Với truy vấn lặp lại, prepared statement/bound statement thường thích hợp hơn về hiệu năng và an toàn parameter binding.

**Lưu ý về Spring Data:** Gắn profile lên một `SimpleStatement` của Java Driver không có nghĩa mọi phương thức repository tự sử dụng profile đó. Khi dùng repository hoặc `CassandraTemplate`, phải kiểm tra điểm mở rộng cụ thể mà phiên bản Spring Data cung cấp để tùy chỉnh statement/query. Với một luồng cần profile riêng rõ ràng, có thể đi qua `CqlSession` trong lớp adapter chuyên biệt; vẫn dùng chung session được Spring quản lý.

## 6. Timeout: chọn đúng loại thay vì tăng tất cả

Các timeout khác nhau giải quyết những công đoạn khác nhau:

| Cấu hình | Ý nghĩa | Gợi ý sử dụng |
| --- | --- | --- |
| `spring.cassandra.connection.connect-timeout` / `CONNECTION_CONNECT_TIMEOUT` | Giới hạn khi tạo TCP connection đến node | Kiểm tra DNS, firewall, network và mất node |
| `spring.cassandra.connection.init-query-timeout` / `CONNECTION_INIT_QUERY_TIMEOUT` | Giới hạn cho truy vấn nội bộ lúc khởi tạo connection | Quan sát lỗi thiết lập kết nối/handshake |
| `spring.cassandra.request.timeout` / `REQUEST_TIMEOUT` | Thời gian driver chờ request hoàn tất phía client | Phù hợp SLA của API và số lần thử của driver |
| `spring.cassandra.controlconnection.timeout` | Timeout cho các truy vấn control/metadata | Phân biệt lỗi metadata với truy vấn nghiệp vụ |
| Timeout phía Cassandra server | Giới hạn riêng cho thực thi/phối hợp request ở server | Phải quan sát và điều chỉnh độc lập |

Một lệnh ghi có thể được server áp dụng nhưng phản hồi bị mất và client nhận timeout. Vì vậy **timeout không đồng nghĩa chắc chắn chưa ghi**. Điều này đặc biệt quan trọng với retry ở thao tác ghi có tác dụng phụ hoặc cập nhật nhiều bảng.

Ví dụ API yêu cầu phản hồi trong hai giây:

- Đặt driver request timeout quá ngắn (ví dụ 100 ms) có thể tạo nhiều false timeout khi latency p99 tăng.
- Đặt timeout 30 giây có thể khiến thread/resource giữ request quá lâu, trái SLA HTTP.
- Cần đo latency p50/p95/p99, lượng request đang chờ, timeout phía server và giới hạn của upstream/downstream.
- Nếu cần retry, dành ngân sách thời gian hợp lý cho tổng request và bảo đảm thao tác được retry an toàn.

Timeout chỉ là một **hàng rào tài nguyên**, không phải phương pháp cải thiện CQL dùng partition key sai, truy vấn có `ALLOW FILTERING` hoặc partition quá lớn.

## 7. Consistency level, paging và giới hạn của cấu hình driver

### 7.1. Consistency là thỏa thuận đọc/ghi với replica

`LOCAL_ONE` có thể giúp giảm số replica cần phản hồi ở DC cục bộ nhưng có khả năng đọc bản sao chưa cập nhật. `LOCAL_QUORUM` yêu cầu đa số replica của DC cục bộ, đánh đổi số phản hồi và độ trễ/khả năng sẵn sàng.

Với RF = 3 trong một DC, `LOCAL_QUORUM` thường yêu cầu hai replica phản hồi. Với RF = 1, quorum chỉ là một; không thể có khả năng chịu lỗi một replica chỉ vì chọn `LOCAL_QUORUM`.

Java Driver có các tùy chọn:

- `REQUEST_CONSISTENCY`: consistency level thông thường.
- `REQUEST_SERIAL_CONSISTENCY`: serial consistency được dùng trong phần điều phối của lightweight transaction (LWT), như `IF NOT EXISTS` hoặc `IF value = ...`.
- Execution profile/statement có thể ghi đè CL mặc định cho một request cụ thể.

Không chọn `SERIAL` hoặc `LOCAL_SERIAL` làm giải pháp chung cho mọi SELECT/INSERT. LWT có chi phí và ngữ nghĩa riêng, chỉ nên dùng khi có yêu cầu cập nhật có điều kiện thực sự.

### 7.2. Page size khác LIMIT và khác paging state

Giả sử truy vấn:

~~~sql
SELECT order_id, created_at, status
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?;
~~~

Nếu driver dùng `page-size = 100`, Cassandra trả kết quả theo từng khối xấp xỉ 100 hàng, tùy kích thước dữ liệu và điều kiện thực thi. Điều này **không giới hạn tổng số hàng** mà ứng dụng có thể duyệt. Nếu tiếp tục duyệt result set đồng bộ, driver có thể tự tải trang tiếp theo.

Ngược lại, `LIMIT 100` trong CQL giới hạn số hàng của kết quả truy vấn (theo ngữ nghĩa CQL) và không thay thế phân trang nhiều trang. Paging state là token tiếp tục truy vấn, không tương đương offset số học và phải được liên kết với cùng truy vấn/binding phù hợp; không sửa hoặc coi token là dữ liệu đáng tin cậy do client tự tạo.

Ví dụ dùng profile `export` với `page-size = 1000` **không** đồng nghĩa đọc tất cả khách hàng bằng một query. Cassandra tối ưu truy vấn theo partition key; nhiều partition hoặc bảng chưa có access pattern phù hợp vẫn cần thiết kế xử lý riêng.

### 7.3. Driver có giúp query-driven design không?

Driver quyết định cách gửi, điều phối và nhận request. **Schema** mới quyết định truy vấn có thể lấy dữ liệu hiệu quả hay không. Nếu cần “20 đơn mới nhất của khách hàng”, bảng nên có partition key theo khách/bucket và clustering key theo thời gian. Thay `page-size` từ 5000 sang 200 không giải quyết được thiếu khóa phân vùng.

## 8. Retry, reconnection và speculative execution

Ba cơ chế dễ bị nhầm:

| Cơ chế | Khi nào kích hoạt | Rủi ro nếu lạm dụng |
| --- | --- | --- |
| **Retry policy** | Một attempt thất bại hoặc gặp tình trạng mà policy có thể xử lý | Nhân đôi tải, che giấu lỗi, lặp lại mutation nguy hiểm |
| **Reconnection policy** | Connection/node bị mất, driver cố mở lại kết nối | Bão reconnect khi cluster/network không ổn định |
| **Speculative execution** | Driver thử thêm attempt để giảm tail latency theo policy | Tăng request song song, có thể nhân đôi tác dụng phụ nếu đánh dấu idempotent sai |

Ví dụ cấu hình reconnection với exponential backoff:

~~~hocon
datastax-java-driver {
  advanced.reconnection-policy {
    class = ExponentialReconnectionPolicy
    base-delay = 1 second
    max-delay = 30 seconds
  }
}
~~~

Reconnection **không** có nghĩa tự động retry lại mọi lệnh nghiệp vụ đang thất bại. Khi cluster tạm mất kết nối, một số thao tác vẫn cần retry ở ứng dụng, nhưng chỉ sau khi đã định nghĩa idempotency và cách phân biệt kết quả không rõ.

Ví dụ ở Java Driver:

~~~java
SimpleStatement statement = SimpleStatement.builder(
        "SELECT order_id, status FROM orders_by_id WHERE order_id = ?")
    .addPositionalValue(orderId)
    .setIdempotent(true)
    .build();
~~~

Truy vấn đọc đơn theo ID thường là idempotent. **Không gắn `setIdempotent(true)` hàng loạt cho mọi ghi.** Counter update, LWT và các mutation có timestamp/TTL, trigger hoặc hiệu ứng nghiệp vụ cần đánh giá chính xác trước khi cho driver retry/speculate. Idempotency của statement không đồng nghĩa toàn bộ luồng nghiệp vụ chỉ thực hiện một lần.

## 9. Connection pool và throttling: đo trước khi chỉnh

Java Driver 4.x thường dùng một connection trên mỗi node ở pool cục bộ theo cấu hình mặc định, nhờ binary protocol multiplexing. Những option liên quan:

~~~hocon
datastax-java-driver {
  advanced.connection {
    max-requests-per-connection = 1024
    pool.local.size = 1
  }
}
~~~

Đây là **minh họa giá trị thường gặp**, không phải đề xuất cố định cho mọi cụm. Đừng sao chép thói quen tăng pool lên 20–50 như JDBC.

Khi throughput bị nghẽn:

1. Kiểm tra CPU/GC/network của ứng dụng và node Cassandra, latency theo partition, lỗi timeout và request đang chờ.
2. Quan sát `pool.in-flight`, `pool.available-streams`, `pool.open-connections` và mức bão hòa I/O thread.
3. Xem một partition/key có nóng hơn các partition khác không.
4. Nếu có bằng chứng một connection trên một node là nút thắt, thử điều chỉnh `pool.local.size` có kiểm soát và so sánh tải.
5. Nếu cần bảo vệ cluster trước tải bùng nổ, cân nhắc driver throttler hoặc giới hạn đồng thời ở tầng ứng dụng, thay vì chỉ tăng pool.

Throttling có thể dùng `advanced.throttler` và các thuộc tính tương ứng như `spring.cassandra.request.throttler.*` trong Spring Boot. Cần định rõ kích thước queue, số request đồng thời và cách trả lỗi khi queue đầy. Queue quá lớn có thể làm timeout tăng dù database không chậm hơn.

## 10. Metrics và logging: kiểm tra tác động thực tế

Cấu hình driver không thể đánh giá chỉ bằng việc ứng dụng khởi động thành công. Driver cung cấp metric cấp session và cấp node; cần kích hoạt metric phù hợp và tích hợp backend/registry đo đạc, ví dụ Micrometer, theo dependency của phiên bản driver.

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [ connected-nodes, cql-requests ]
    node.enabled = [
      pool.open-connections,
      pool.in-flight,
      pool.available-streams
    ]
  }
}
~~~

Nếu thiếu module metrics thích hợp hoặc backend chưa được cấu hình, chỉ thêm danh sách metric chưa chắc khiến metric xuất hiện trong hệ thống quan sát. Kiểm tra module tích hợp (ví dụ Micrometer) và cách xuất dữ liệu theo phiên bản driver.

| Tín hiệu | Câu hỏi trả lời |
| --- | --- |
| `connected-nodes` | Session đang nhìn thấy bao nhiêu node được kết nối? |
| `cql-requests` và phân phối latency | Request chậm do tail latency hay chậm đều? |
| `pool.in-flight` | Node nào đang nhận nhiều request trong pool? |
| `pool.available-streams` | Connection còn khả năng xử lý thêm request không? |
| Timeout, unavailable, retry/reconnect | Lỗi từ mạng, replica, consistency hay quá tải? |
| Page count/rows, payload size | Paging đang tạo quá nhiều round-trip hoặc trang quá lớn? |
| Tombstone, partition size, server-side metrics | Vấn đề xuất phát từ schema/CQL hay client? |

Logging request cần tách dữ liệu vận hành khỏi thông tin nhạy cảm. Không bật ghi toàn bộ CQL và bound values ở production vô thời hạn: truy vấn có thể chứa PII hoặc thông tin nghiệp vụ. Chỉ bật logging chi tiết khi điều tra có kiểm soát, có giới hạn độ dài và chính sách che dữ liệu.

## 11. Kiểm tra cấu hình có hiệu lực bằng API

Khi nhiều nguồn cấu hình cùng tồn tại, đừng chỉ kiểm tra file. Có thể đọc giá trị đã nạp từ session:

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfig;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;
import java.time.Duration;

DriverConfig config = session.getContext().getConfig();

DriverExecutionProfile defaults = config.getDefaultProfile();
Duration timeout =
    defaults.getDuration(DefaultDriverOption.REQUEST_TIMEOUT);
int pageSize =
    defaults.getInt(DefaultDriverOption.REQUEST_PAGE_SIZE);

DriverExecutionProfile exportProfile = config.getProfile("export");
Duration exportTimeout =
    exportProfile.getDuration(DefaultDriverOption.REQUEST_TIMEOUT);

// Đưa giá trị không nhạy cảm vào kiểm tra startup/metrics có kiểm soát.
System.out.printf(
    "requestTimeout=%s, pageSize=%d, exportTimeout=%s%n",
    timeout, pageSize, exportTimeout);
~~~

Đây là cách xác minh option hiệu lực của driver, bao gồm cả trường hợp Boot properties ghi đè HOCON. Không log password, token, đường dẫn private key hoặc thông tin cấu hình nhạy cảm.

Trong Spring Boot, có thể inject `CqlSession` do Boot quản lý vào một component kiểm tra lúc khởi động. Đừng tạo thêm session chỉ để đọc cấu hình.

### 11.1. Hot reload có giới hạn

Loader dựa trên file của Driver 4.x có thể hỗ trợ nạp lại cấu hình theo chu kỳ `basic.config-reload-interval`. Tùy chọn này có thể được đặt trong cấu hình HOCON:

~~~hocon
datastax-java-driver {
  basic.config-reload-interval = 5 minutes
}
~~~

Có thể gọi API thủ công khi loader hỗ trợ:

~~~java
DriverConfigLoader currentLoader =
    session.getContext().getConfigLoader();

if (currentLoader.supportsReloading()) {
    currentLoader.reload().whenComplete((changed, error) -> {
        if (error != null) {
            // Ghi nhận lỗi reload ở hệ thống giám sát.
        } else if (Boolean.TRUE.equals(changed)) {
            // Kiểm tra lại các option quan trọng.
        }
    });
}
~~~

**Không phải option nào cũng có thể thay đổi nóng.** Những thiết lập ảnh hưởng khởi tạo session, protocol, load-balancing policy hoặc cấu trúc thành phần có thể không được áp dụng khi session đã chạy. Dùng hot reload cho thông số được tài liệu driver xác nhận hỗ trợ; với thay đổi ảnh hưởng kiến trúc kết nối nên triển khai có kiểm soát và khởi động lại ứng dụng.

`DriverConfigLoader.fromString()` không cung cấp hot reload kiểu loader file. Với custom loader, phải kiểm tra `supportsReloading()` và cách các option được áp dụng. Việc nạp file thành công không bảo đảm mọi giá trị mới đang được driver sử dụng.

## 12. Cấu hình môi trường và bảo mật

Tách rõ địa chỉ cluster, keyspace, DC và yêu cầu bảo mật theo môi trường:

| Môi trường | Đặc điểm cấu hình nên có |
| --- | --- |
| Local | Contact point localhost, DC thật của node local, RF phù hợp cluster một node, timeout dễ debug |
| Integration test | Cluster thử nghiệm cô lập, schema test độc lập, cấu hình có thể tái lập |
| Staging | Gần topology/CL production nếu mục tiêu là đo chịu lỗi và tail latency |
| Production | Nhiều contact point cục bộ, keyspace đúng, TLS/auth, timeout và CL theo SLA, metrics và runbook |

Ví dụ Spring Boot cấu hình TLS qua SSL bundle đã được quản lý:

~~~yaml
spring:
  cassandra:
    contact-points: cassandra-1.internal,cassandra-2.internal
    local-datacenter: dc1
    keyspace-name: order_service
    ssl:
      bundle: cassandra-client
~~~

Ví dụ giả định SSL bundle `cassandra-client` đã được định nghĩa đúng ở cấu hình Spring Boot và hạ tầng Cassandra đã bật TLS. SSL bundle chỉ là cơ chế cung cấp vật liệu TLS; cần tiếp tục xác minh certificate chain, hostname verification và khả năng giao tiếp với đúng endpoint.

Tên đăng nhập/mật khẩu, token hoặc secret để xác thực phải được cấp qua nguồn bảo mật của môi trường, không hardcode vào Java/HOCON commit lên repository. Không tắt xác minh hostname chỉ để vượt qua lỗi chứng chỉ ở production.

Một vấn đề khác: **sự nhất quán của cấu hình giữa replica ứng dụng**. Nếu một instance đang dùng `LOCAL_ONE` và một instance khác dùng `LOCAL_QUORUM`, kết quả quan sát có thể khác nhau. Cần kiểm soát version cấu hình và rollout, có telemetry để phát hiện instance lệch cấu hình.

## 13. Tình huống thực hành: API và luồng export dùng chung cluster

Ứng dụng có hai chức năng:

- `GET /orders/{id}`: truy vấn bảng `orders_by_id` theo đúng `order_id`; SLA mong muốn dưới một vài giây.
- Xuất lịch sử đơn theo `customer_id` và `month_bucket`: đọc từng partition/bucket với paging, cho phép timeout lâu hơn nhưng phải giới hạn lượng đọc.

Cụm Cassandra có RF = 3 trong DC `dc1`. Spring Boot quản lý `CqlSession`, repository dùng cho API thông thường. Người vận hành muốn thêm profile `export` mà không thay CL của toàn dịch vụ.

**Bước 1 — Khai báo kết nối và chính sách mặc định trong Spring Boot:**

~~~yaml
spring:
  cassandra:
    contact-points: cassandra-1.internal,cassandra-2.internal
    local-datacenter: dc1
    keyspace-name: order_service
    request:
      timeout: 2s
      consistency: LOCAL_QUORUM
      page-size: 200
    config: classpath:cassandra-driver.conf
~~~

**Bước 2 — Khai báo profile trong `cassandra-driver.conf`:**

~~~hocon
datastax-java-driver {
  profiles {
    export {
      basic.request.timeout = 15 seconds
      basic.request.page-size = 1000
    }
  }

  advanced.metrics {
    session.enabled = [ connected-nodes, cql-requests ]
    node.enabled = [ pool.in-flight, pool.available-streams ]
  }
}
~~~

**Bước 3 — Giữ nguyên đường API mặc định; dùng profile `export` cho những statement xuất dữ liệu:** Chỉ những statement được đánh dấu `setExecutionProfileName("export")` (hoặc điểm mở rộng tương đương) mới nhận timeout/page size của export. Không mặc định rằng repository tự gán profile.

**Bước 4 — Đo và kiểm chứng:** Kiểm tra giá trị hiệu lực từ `session.getContext().getConfig()`. Chạy tải có kiểm soát cho cả API và export, theo dõi p95/p99, timeout, số page, lưu lượng mạng, pool in-flight và CPU. Giới hạn số export đồng thời để không lấn át request tương tác.

**Bước 5 — Xử lý đúng truy vấn:** Lịch sử của một khách hàng rất lớn cần chia bucket theo thời gian hoặc shard hợp lý, thay vì một partition vô hạn. Nếu export cần nhiều bucket, ứng dụng nên điều phối lần lượt hoặc có mức song song giới hạn; page size chỉ tối ưu trao đổi dữ liệu bên trong từng truy vấn.

### Các ca kiểm tra nên thực hiện

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Startup thiếu `local-datacenter` hoặc sai DC | Nhận diện lỗi cấu hình/kết nối; sửa DC theo topology thật |
| `request.timeout = 2s` trong Boot nhưng HOCON đặt 5 giây | Xác minh driver sử dụng giá trị Boot trong phạm vi option trùng |
| Có profile `export`, statement không chọn profile | Statement vẫn dùng profile mặc định |
| Statement chọn `export` | Timeout/page size của `export` được áp dụng |
| Tăng page size lên rất lớn | Quan sát memory, payload, latency; không coi tăng page size là luôn nhanh hơn |
| Driver báo timeout sau INSERT | Không kết luận dữ liệu chưa ghi; kiểm tra idempotency và trạng thái thực |
| Tắt một replica trong staging RF = 3 với `LOCAL_QUORUM` | Đánh giá khả năng tiếp tục đọc/ghi khi còn đủ replica và tác động latency |
| Thay đổi option không hỗ trợ hot reload | Có kế hoạch restart/rollout và xác minh sau khởi động |
| Bật metric driver mà dashboard vẫn trống | Kiểm tra dependency metrics, backend và cấu hình export |

## 14. Lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| File `cassandra-driver.conf` không có tác dụng trong Boot | Chưa khai báo `spring.cassandra.config`, sai resource path, hoặc option bị Boot property ghi đè | Xác minh classpath, YAML và đọc `DriverConfig` runtime |
| `NoNodeAvailableException` / kết nối thất bại | Contact points, firewall, DNS, TLS/auth, local DC, cluster status | Kiểm tra network, log driver và `nodetool status` |
| Kết nối tới DC không mong muốn | `local-datacenter` sai hoặc cấu hình load balancing/route không khớp | So sánh topology thật, contact points và node metadata |
| Timeout dù tăng pool | CQL chậm, hot partition, server quá tải, retry/throttling hoặc CL không đáp ứng | Đối chiếu metric client và server, truy vấn và khóa |
| Export chiếm tài nguyên của API | Chưa giới hạn số export đồng thời, page quá lớn, truy vấn rộng | Thiết lập concurrency limit/throttler và đo page/payload |
| `getProfile("export")` không có profile | Sai nguồn cấu hình hoặc tên profile | Kiểm tra HOCON, loader và tên profile chính xác |
| Hot reload báo thay đổi nhưng hành vi giữ nguyên | Option không được hỗ trợ thay nóng hoặc bị nguồn khác ghi đè | Xem docs option, config runtime và kế hoạch restart |
| Retry tạo hiệu ứng ghi trùng | Đánh dấu idempotency sai hoặc thao tác nghiệp vụ không có cơ chế chống lặp | Rà soát CQL, retry policy, idempotency key, LWT khi cần |
| Cùng một config nhưng staging/production khác hiệu năng | Topology, RF, CL, latency network, kích thước partition hoặc tải khác nhau | So sánh đặc điểm cluster và thử nghiệm theo SLA |

Đừng vội “sửa” timeout bằng cách tăng tất cả lên 60 giây. Hãy xác định request chậm nằm ở kết nối, định tuyến DC, replica, CQL, phân vùng, paging hay tải cạnh tranh.

## 15. Những câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng Spring Boot đã tự tạo `CqlSession`. Bạn muốn tăng timeout của một nhóm request xuất dữ liệu mà giữ nguyên API mặc định. Nên chọn cơ chế nào?

*Gợi ý:* Tạo execution profile và áp dụng có chủ đích lên statement xuất dữ liệu, kết hợp Boot config/file HOCON phù hợp.

**Câu 2.** `DriverConfigLoader.programmaticBuilder()` khác gì việc copy toàn bộ `reference.conf` vào source code?

*Gợi ý:* Builder chỉ cần override vài option và kế thừa mặc định, giảm nguy cơ đóng băng cấu hình mặc định theo phiên bản.

**Câu 3.** Vì sao `spring.cassandra.request.page-size: 100` không bảo đảm API chỉ trả tối đa 100 bản ghi?

*Gợi ý:* Page size điều khiển từng lần fetch, không phải số hàng cuối cùng hay `LIMIT`.

**Câu 4.** Vì sao timeout sau lệnh INSERT không đồng nghĩa “chưa ghi thành công”?

*Gợi ý:* Server có thể đã áp dụng mutation nhưng client không nhận được xác nhận.

**Câu 5.** Lý do nào khiến file `application.conf` có hiệu lực với ứng dụng Java Driver thuần nhưng không hoạt động như mong đợi trong Spring Boot?

*Gợi ý:* Boot có hạ tầng tự cấu hình riêng và không mặc định tìm file HOCON đó; hãy dùng `spring.cassandra.config` hoặc customizer.

**Câu 6.** Khi nào nên dùng `DriverConfigLoaderBuilderCustomizer` thay vì `CqlSessionBuilderCustomizer`?

*Gợi ý:* Tùy chỉnh option driver so với tùy chỉnh cách dựng session.

**Câu 7.** Cụm RF = 3 có một replica đang down. Điều gì cần kiểm chứng nếu API đang dùng `LOCAL_QUORUM`?

*Gợi ý:* Số replica còn đáp ứng trong DC, request latency, lỗi timeout/unavailable và khả năng cluster phục hồi.

**Câu 8.** Vì sao không nên đánh dấu tất cả statement là idempotent để driver tự retry?

*Gợi ý:* Một số mutation/counter/LWT và luồng nghiệp vụ có thể gây tác dụng phụ hoặc tranh chấp ngoài ý muốn.

## Tài liệu tham khảo

- [Apache Cassandra Java Driver 4.19 — Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): HOCON, loader, execution profiles và reload.
- [Apache Cassandra Java Driver 4.19 — Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/): page size, paging state, duyệt kết quả.
- [Apache Cassandra Java Driver 4.19 — Connection Pooling](https://apache.github.io/cassandra-java-driver/4.19.0/core/pooling/): pool theo node và cách theo dõi.
- [Apache Cassandra Java Driver 4.19 — Metrics](https://apache.github.io/cassandra-java-driver/4.19.0/core/metrics/): session/node metrics và backend.
- [Spring Boot — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/reference/data/nosql.html): auto-configuration Cassandra, `spring.cassandra.config` và customizer.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): các khóa `spring.cassandra.*`.

## Kết luận

`DriverConfigLoader` là cổng cấu hình của Java Driver 4.x: nó kết hợp mặc định, file HOCON và các override lập trình thành cấu hình mà `CqlSession` dùng để gửi CQL. Trong **Spring Data Cassandra**, hãy bắt đầu với `spring.cassandra.*`, dùng `spring.cassandra.config` cho cấu hình driver có cấu trúc và `DriverConfigLoaderBuilderCustomizer` khi cần tinh chỉnh sâu. Dùng execution profile để phân biệt chính sách truy vấn; kiểm chứng cấu hình thật qua `DriverConfig` và các chỉ số vận hành. Quan trọng nhất, timeout, consistency, paging, retry và pool chỉ đạt hiệu quả khi **partition key, schema, replication và đường truy vấn** được thiết kế phù hợp với Cassandra.
