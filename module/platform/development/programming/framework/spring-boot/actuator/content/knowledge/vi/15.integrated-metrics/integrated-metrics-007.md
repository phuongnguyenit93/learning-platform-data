# Theo dõi connection pool của DataSource và HikariCP

## 1. Vì sao cần nhìn vào pool kết nối?

Một yêu cầu HTTP chậm không nhất thiết đang chạy một câu SQL chậm. Nó có thể chưa lấy được kết nối để gửi SQL xuống cơ sở dữ liệu. Ngược lại, ứng dụng vẫn có thể giữ một kết nối trong lúc chờ dịch vụ khác, dù cơ sở dữ liệu gần như không làm việc.

Pool kết nối (connection pool) giữ và tái sử dụng các kết nối vật lý tới cơ sở dữ liệu. Thay vì tạo kết nối mới cho từng thao tác, mã ứng dụng mượn kết nối, sử dụng rồi trả lại. Theo dõi pool giúp trả lời ba câu hỏi khác nhau:

- Hiện có bao nhiêu kết nối đang được mượn, bao nhiêu kết nối có thể dùng ngay?
- Có bao nhiêu luồng đang chờ mượn và chúng phải chờ bao lâu?
- Việc tạo, mượn hoặc giữ kết nối có đang gây lỗi hay làm chậm ứng dụng?

Trong Spring Boot, `DataSource` là giao diện cung cấp kết nối JDBC. HikariCP là một triển khai pool thường được Spring Boot lựa chọn khi có trên classpath. Hai tên này không đồng nghĩa: một `DataSource` có thể dùng HikariCP, một pool khác, một lớp bọc hoặc cơ chế định tuyến.

Bài học sử dụng Spring Boot 3.3.13, Micrometer do Spring Boot quản lý và HikariCP 5.1.0. Ví dụ chạy với Java 21, mã nguồn đặt mức Java 17. Những nhận xét về tên metric và vòng đời đăng ký được gắn với tổ hợp phiên bản này; khi dùng phiên bản khác, hãy kiểm tra danh sách metric thực tế.

## 2. Mô hình từ lúc mượn đến lúc trả

`DataSource.getConnection()` là điểm ứng dụng yêu cầu một kết nối. Nếu có kết nối rảnh, pool có thể giao nó cho luồng gọi. Nếu chưa có kết nối rảnh, pool có thể tạo thêm trong giới hạn cấu hình hoặc buộc luồng gọi chờ. Nếu không cấp được trước thời hạn chờ mượn, lần mượn thất bại.

Một vòng sử dụng thông thường:

```java
try (Connection connection = dataSource.getConnection()) {
    // Thực hiện công việc JDBC cần kết nối.
}
```

Đây là đoạn minh họa, chưa phải chương trình độc lập. Với kết nối do HikariCP giao, `close()` trên đối tượng kết nối thường trả nó về pool để tái sử dụng. Nó không có nghĩa mỗi lần đóng là hủy ngay kết nối vật lý. Pool vẫn có thể loại bỏ kết nối khi nó hỏng hoặc đến lúc cần nghỉ.

Trong ứng dụng dùng `JdbcTemplate`, JPA hoặc giao dịch do Spring quản lý, framework đảm nhận vòng đời mượn/trả theo phạm vi tương ứng. Ví dụ JDBC trực tiếp ở đây giúp nhìn cơ chế pool; khi xử lý nghiệp vụ, hãy giữ cách quản lý kết nối nhất quán với công cụ và giao dịch đang dùng.

Có thể hình dung luồng xử lý như sau:

```text
Luồng ứng dụng
    -> yêu cầu mượn kết nối
    -> chờ pool cấp kết nối, nếu cần
    -> nhận kết nối
    -> giữ kết nối để chạy SQL hoặc thực hiện công việc khác
    -> đóng kết nối được mượn
    -> pool nhận lại hoặc loại bỏ kết nối
```

Các khái niệm cần tách rõ:

| Khái niệm | Ý nghĩa | Điều không thể suy ra trực tiếp |
| --- | --- | --- |
| `active` | Kết nối đã được giao ra ngoài pool và chưa trả lại | Không phải số câu SQL đang chạy |
| `idle` | Kết nối đang rảnh trong pool | Không chứng minh mọi truy vấn tiếp theo đều thành công |
| `pending` | Luồng đang đợi pool cấp kết nối | Không phải số truy vấn đang chờ khóa trong cơ sở dữ liệu |
| `total` | Tổng kết nối hiện có trong pool | Không nhất thiết bằng mức tối đa cấu hình |
| `max` | Giới hạn kết nối của pool | Không phải sức chịu tải đã được đo của cơ sở dữ liệu |
| `min` | Mục tiêu số kết nối rảnh tối thiểu | Không phải số kết nối rảnh luôn có ở mọi thời điểm |

Ví dụ, một luồng giữ kết nối rồi gọi một API bên ngoài vẫn làm `active` tăng, dù chưa có SQL chạy. Một luồng chờ `getConnection()` làm `pending` tăng nhưng chưa thể gửi SQL. Một truy vấn đã vào cơ sở dữ liệu và đang chờ khóa thường vẫn giữ kết nối, vì vậy có thể đẩy `active` lên và gián tiếp làm các luồng đến sau phải chờ.

Ở trạng thái ổn định, tổng kết nối thường tương ứng với số đang mượn cộng số rảnh. Tuy nhiên các Gauge được đọc riêng, còn pool thay đổi đồng thời; không nên coi một bộ số lấy từ nhiều lần đọc là ảnh chụp nguyên tử hay dùng sai lệch tức thời làm bằng chứng lỗi.

## 3. Hai nhóm metric: JDBC dùng chung và HikariCP

### 3.1. Nhóm `jdbc.connections.*`

Spring Boot Actuator có cơ chế đo pool qua `DataSourcePoolMetadataProvider`. Khi có metadata phù hợp và có giá trị để đo, các Gauge JDBC dùng chung bao gồm:

| Metric Micrometer | Ý nghĩa |
| --- | --- |
| `jdbc.connections.active` | Số kết nối đang được mượn |
| `jdbc.connections.idle` | Số kết nối đang rảnh |
| `jdbc.connections.max` | Mức tối đa pool báo cáo |
| `jdbc.connections.min` | Mức tối thiểu pool báo cáo |

Đây là lớp quan sát chung cho các `DataSource` được hỗ trợ, không chỉ dành cho HikariCP. Việc có `DataSource` bean không bảo đảm cả bốn Gauge luôn tồn tại: còn phụ thuộc khả năng lấy metadata và thời điểm đăng ký.

Tag nhận diện ở lớp này là `name`, được tính từ tên bean `DataSource`. Với bean mặc định `dataSource` trong ví dụ, tag là `name=dataSource`. Không nên suy ra tag của mọi bean bằng cách chép nguyên tên bean: cách tính tên của Spring Boot có thể loại bỏ hậu tố `DataSource` ở các tên dài hơn. Hãy xem tag thực tế.

### 3.2. Nhóm `hikaricp.*`

HikariCP có bộ đo riêng tích hợp với Micrometer. Với Spring Boot, thông thường không cần tự viết bộ đếm quanh từng lần gọi `getConnection()`.

Tag nhận diện là `pool`. Ví dụ đặt tên rõ ràng:

```properties
spring.datasource.hikari.pool-name=lessonPool
```

Khi đó các metric Hikari của pool này mang `pool=lessonPool`. Đây là tên pool, không phải tag `name` của JDBC và cũng không phải tên database.

Các Gauge trong HikariCP 5.1.0:

| Metric Micrometer | Giá trị đang quan sát |
| --- | --- |
| `hikaricp.connections` | Tổng kết nối hiện có |
| `hikaricp.connections.active` | Số kết nối đang được mượn |
| `hikaricp.connections.idle` | Số kết nối đang rảnh |
| `hikaricp.connections.pending` | Số luồng đang đợi kết nối |
| `hikaricp.connections.max` | Giới hạn tối đa |
| `hikaricp.connections.min` | Mục tiêu rảnh tối thiểu |

Trong HikariCP 5.1.0, thống kê pool dùng cho các Gauge này có bộ nhớ đệm cập nhật theo khoảng một giây. Vì vậy giữ kết nối rồi đọc Gauge ngay trong cùng một dòng thời gian rất ngắn có thể vẫn thấy giá trị cũ. Ví dụ thực hành bên dưới đợi có giới hạn để quan sát được các trạng thái, thay vì giả định mỗi lần gọi Gauge là một lần lấy số mới.

### 3.3. Ba Timer và một Counter

| Metric | Loại | Đo điều gì? |
| --- | --- | --- |
| `hikaricp.connections.acquire` | Timer | Thời gian chờ để mượn kết nối |
| `hikaricp.connections.usage` | Timer | Thời gian kết nối được giữ sau khi mượn, ghi nhận khi trả |
| `hikaricp.connections.creation` | Timer | Thời gian tạo kết nối vật lý |
| `hikaricp.connections.timeout` | Counter | Số lần mượn kết nối hết thời hạn chờ |

Một Timer có số mẫu và tổng thời gian; tùy registry còn có số lớn nhất theo cửa sổ và các thống kê được cấu hình. Timer không phải một số thời gian duy nhất. Khi xem Actuator, đọc cả `statistic` lẫn `baseUnit`; khi gọi trực tiếp Java, có thể yêu cầu đơn vị bằng `TimeUnit`.

Ba lỗi diễn giải rất phổ biến:

1. `acquire` cao không khẳng định SQL chậm. Nó nói rằng việc lấy kết nối mất thời gian; cần tìm tiếp vì sao pool không cấp kịp.
2. `usage` cao không khẳng định toàn bộ thời gian đó dùng để chạy SQL. Thời gian giữ kết nối còn có thể chứa xử lý Java, chờ khóa, gọi dịch vụ khác hoặc phạm vi giao dịch quá dài.
3. `creation` không đo mọi lần mượn. Mượn lại một kết nối rảnh không đồng nghĩa tạo thêm kết nối vật lý.

Trong HikariCP 5.1.0, đường đi hết hạn chờ mượn cũng ghi một mẫu `acquire`. Vì thế không được gọi `acquire.count()` là “số lần mượn thành công” nếu chưa kiểm tra cách triển khai. Ngược lại, một lần chưa nhận được kết nối không tạo ra một khoảng `usage` cho người mượn đó.

`usage` được ghi khi trả kết nối. Nếu một kết nối bị giữ rất lâu và chưa trả, thời gian đang tích lũy của nó chưa trở thành một mẫu hoàn tất trong Timer. Vì vậy biểu đồ thời gian sử dụng có vẻ bình thường không đủ loại trừ việc có một kết nối đang bị giữ bất thường.

## 4. Điều kiện để thấy metric

Trong một ứng dụng Spring Boot dùng JDBC, cần có pool, Actuator và `MeterRegistry` phù hợp. Spring Boot có thể tạo `SimpleMeterRegistry` khi không cấu hình hệ thống xuất metric khác; ví dụ độc lập dưới đây dùng registry trong bộ nhớ này.

Phân biệt ba việc:

- Đăng ký metric trong `MeterRegistry`.
- Cho phép truy cập endpoint HTTP để xem metric.
- Xuất metric sang một hệ thống lưu trữ chuỗi thời gian.

Một metric có thể đã tồn tại trong registry dù HTTP endpoint chưa được mở. Ngược lại, mở endpoint không tạo ra `DataSource`, không khởi động một pool chưa sử dụng và không tự cung cấp lịch sử dài hạn.

Trong ứng dụng web đã có Actuator, có thể cho phép xem endpoint chẩn đoán:

```properties
management.endpoints.web.exposure.include=health,metrics
```

Cấu hình này điều khiển danh sách endpoint được phơi bày; việc xác thực và quyền truy cập vẫn theo cấu hình bảo mật của ứng dụng. Chỉ thay đổi nó trong phạm vi môi trường cần quan sát.

Không cần bật `spring.datasource.hikari.register-mbeans=true` để Micrometer đo HikariCP. MBeans là một cơ chế quản lý/quan sát khác. Cũng không nên tự gắn thêm bộ đo Hikari khi Spring Boot đã gắn: việc trộn cấu hình thủ công có thể làm mất bộ đo mong đợi hoặc tạo tình huống khó phân biệt.

Nếu tự định nghĩa nhiều `DataSource` bean, các thuộc tính `spring.datasource.*` dành cho auto-configuration mặc định không đương nhiên cấu hình mọi bean do bạn tạo. Cần kiểm tra cấu hình thực tế của từng pool, bộ đo thực tế và tag mà nó xuất ra.

## 5. Đọc metric qua Actuator trong ứng dụng web

Phần này dành cho ứng dụng đang chạy web trên `localhost:8080`, dùng đường dẫn Actuator mặc định. Ví dụ Java ở phần 6 cố ý chạy không có web server, nên không dùng các lệnh HTTP này cho tiến trình của ví dụ đó.

Trước tiên khám phá danh sách tên:

```bash
curl -s http://localhost:8080/actuator/metrics
```

Xem một metric trước khi lọc tag:

```bash
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.active
```

Đọc `availableTags`, rồi mới dùng đúng tên pool:

```bash
curl -s --get \
  --data-urlencode "tag=pool:lessonPool" \
  http://localhost:8080/actuator/metrics/hikaricp.connections.active

curl -s --get \
  --data-urlencode "tag=pool:lessonPool" \
  http://localhost:8080/actuator/metrics/hikaricp.connections.pending

curl -s --get \
  --data-urlencode "tag=pool:lessonPool" \
  http://localhost:8080/actuator/metrics/hikaricp.connections.acquire

curl -s --get \
  --data-urlencode "tag=name:dataSource" \
  http://localhost:8080/actuator/metrics/jdbc.connections.max
```

Đây là lệnh cho shell hỗ trợ xuống dòng bằng dấu `\`. Trên PowerShell có thể dùng `curl.exe` và viết mỗi lệnh trên một dòng. Nếu đã đổi management port hoặc base path, điều chỉnh URL theo ứng dụng.

Đọc kết quả theo loại metric:

- Với Gauge, tìm mẫu có `statistic=VALUE`.
- Với Timer, phân biệt `COUNT`, `TOTAL_TIME` và `MAX` nếu registry cung cấp; xem đơn vị được trả về.
- Với Counter timeout, xem số đếm và sự thay đổi qua thời gian, không diễn giải một giá trị tích lũy thành tốc độ hiện tại.

Không đưa ra một JSON mẫu cố định để khẳng định số kết nối của mọi máy. Danh sách tag và giá trị phụ thuộc pool, registry, thời điểm và tải đang chạy. Các lệnh trên là cách truy vấn, không phải kết quả đã định sẵn.

Khi có nhiều pool, endpoint không lọc tag có thể tổng hợp các meter trùng tên. Một giá trị tổng không mô tả riêng pool đọc hay pool ghi. Muốn chẩn đoán thiếu kết nối, phải giữ các chiều như instance ứng dụng, tên pool và vai trò kết nối trong hệ thống giám sát.

## 6. Thực hành: tạo một lần chờ mượn thật và quan sát phục hồi

### 6.1. Mục tiêu của thí nghiệm

Chương trình độc lập sau tạo HikariCP có tối đa một kết nối tới H2 trong bộ nhớ:

1. Mượn và trả một lần để khởi động pool.
2. Luồng chính giữ kết nối duy nhất.
3. Một luồng khác yêu cầu mượn và phải chờ.
4. Luồng đó hết thời hạn chờ sau cấu hình `connection-timeout`.
5. Luồng chính trả kết nối.
6. Mượn lại và chạy `SELECT 1` thành công.

Đây là thử nghiệm về pool, không phải thử tải cơ sở dữ liệu hay mô phỏng SQL chậm. Việc một kết nối bị giữ là chủ đích; không cần chèn câu lệnh SQL ngủ và không cần một database bên ngoài.

### 6.2. Các tệp cần tạo

Tạo một thư mục riêng với cấu trúc:

```text
pool-metrics-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/PoolMetricsApplication.java
        └── resources/application.properties
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>pool-metrics-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

Spring Boot quản lý phiên bản thư viện JDBC, HikariCP và H2; không cần chép riêng phiên bản Hikari vào POM. Với parent 3.3.13, thí nghiệm này dùng HikariCP 5.1.0.

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:pool_metrics;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.pool-name=lessonPool
spring.datasource.hikari.maximum-pool-size=1
spring.datasource.hikari.minimum-idle=1
spring.datasource.hikari.connection-timeout=5000
spring.datasource.hikari.validation-timeout=1000
spring.sql.init.mode=never
```

Giải thích cấu hình:

- `maximum-pool-size=1` tạo giới hạn rõ ràng để lần mượn thứ hai buộc phải đợi.
- `minimum-idle=1` đặt mục tiêu duy trì một kết nối rảnh khi không có người mượn. Nó không ngăn số kết nối rảnh giảm về 0 lúc đang sử dụng.
- `connection-timeout=5000` cho phép chờ mượn tối đa khoảng năm giây theo cơ chế Hikari. Không dùng nó để khẳng định thời gian đo ngoài chương trình sẽ đúng 5000 ms tuyệt đối.
- `validation-timeout=1000` là giới hạn cho kiểm tra tính hợp lệ, tách với thời hạn chờ mượn.
- `spring.sql.init.mode=never` bỏ bước chạy script khởi tạo dữ liệu của Spring Boot trong bài thử này. Chương trình sẽ tự mở kết nối khi chạy phần thực hành.
- `web-application-type=none` cho phép chạy và thoát như một ứng dụng Java thông thường. Không cần cổng HTTP và không có endpoint Actuator HTTP trong tiến trình này.

`src/main/java/demo/PoolMetricsApplication.java`:

```java
package demo;

import com.zaxxer.hikari.HikariDataSource;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLTransientConnectionException;
import java.sql.Statement;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;

@SpringBootApplication
public class PoolMetricsApplication {
    private static final String POOL = "lessonPool";
    private static final String DATA_SOURCE = "dataSource";

    public static void main(String[] args) throws Exception {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(PoolMetricsApplication.class, args)) {
            HikariDataSource source = context.getBean(HikariDataSource.class);
            MeterRegistry registry = context.getBean(MeterRegistry.class);
            demonstrate(source, registry);
        }
    }

    private static void demonstrate(
            HikariDataSource source, MeterRegistry registry) throws Exception {
        try (Connection warm = source.getConnection()) {
            if (!selectOne(warm)) {
                throw new IllegalStateException("Warm-up query failed");
            }
        }

        Timer acquire = registry.get("hikaricp.connections.acquire")
                .tag("pool", POOL).timer();
        Timer usage = registry.get("hikaricp.connections.usage")
                .tag("pool", POOL).timer();
        Counter timeouts = registry.get("hikaricp.connections.timeout")
                .tag("pool", POOL).counter();
        long acquireBefore = acquire.count();
        long usageBefore = usage.count();
        double timeoutsBefore = timeouts.count();

        System.out.println("CHECK jdbc.name=" + registry.get("jdbc.connections.max")
                .tag("name", DATA_SOURCE).gauge().getId().getTag("name"));
        System.out.println("CHECK hikari.pool=" + acquire.getId().getTag("pool"));
        System.out.println("CHECK jdbc.active.present=" + (registry.find("jdbc.connections.active")
                .tag("name", DATA_SOURCE).gauge() != null));
        await(() -> hasState(registry, 0, 1, 0), "ready");
        snapshot("ready", registry);

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            try (Connection held = source.getConnection()) {
                await(() -> hasState(registry, 1, 0, 0), "held");
                snapshot("held", registry);

                Future<String> waiting = executor.submit(() -> {
                    try (Connection unexpected = source.getConnection()) {
                        return "unexpected-success";
                    } catch (SQLTransientConnectionException expected) {
                        return expected.getClass().getSimpleName();
                    }
                });

                await(() -> hasState(registry, 1, 0, 1), "waiting");
                snapshot("waiting", registry);
                String result = waiting.get(8, TimeUnit.SECONDS);
                if (!result.equals("SQLTransientConnectionException")) {
                    throw new IllegalStateException("Expected pool acquisition timeout");
                }
                System.out.println("CHECK wait.result=" + result);
                System.out.printf(Locale.ROOT, "CHECK timeout.delta=%.0f%n",
                        timeouts.count() - timeoutsBefore);
                System.out.println("CHECK usage.closed.whileHeld="
                        + (usage.count() - usageBefore));
            }

            await(() -> hasState(registry, 0, 1, 0), "returned");
            snapshot("returned", registry);
            try (Connection recovered = source.getConnection()) {
                System.out.println("CHECK reborrow.query.ok=" + selectOne(recovered));
            }
            System.out.println("CHECK acquire.count.delta="
                    + (acquire.count() - acquireBefore));
            System.out.println("CHECK usage.count.delta="
                    + (usage.count() - usageBefore));
        } finally {
            executor.shutdownNow();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not terminate");
            }
        }
    }

    private static boolean selectOne(Connection connection) throws Exception {
        try (Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT 1")) {
            return result.next() && result.getInt(1) == 1;
        }
    }

    private static boolean hasState(
            MeterRegistry registry, int active, int idle, int pending) {
        return hikari(registry, "active") == active
                && hikari(registry, "idle") == idle
                && hikari(registry, "pending") == pending
                && hikari(registry, "") == 1;
    }

    private static void snapshot(String phase, MeterRegistry registry) {
        Gauge jdbcMax = registry.get("jdbc.connections.max")
                .tag("name", DATA_SOURCE).gauge();
        System.out.printf(Locale.ROOT,
                "CHECK %s jdbcMax=%.0f hikariActive=%.0f idle=%.0f pending=%.0f total=%.0f%n",
                phase, jdbcMax.value(), hikari(registry, "active"),
                hikari(registry, "idle"), hikari(registry, "pending"),
                hikari(registry, ""));
    }

    private static double hikari(MeterRegistry registry, String suffix) {
        String name = "hikaricp.connections" + (suffix.isEmpty() ? "" : "." + suffix);
        return registry.get(name).tag("pool", POOL).gauge().value();
    }

    private static void await(BooleanSupplier condition, String phase)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (System.nanoTime() < deadline) {
            if (condition.getAsBoolean()) {
                return;
            }
            Thread.sleep(20);
        }
        throw new IllegalStateException("Pool state not observed: " + phase);
    }
}
```

### 6.3. Chạy chương trình

Cần JDK 17 trở lên và Maven. Lần dựng đầu cần tải các dependency từ Maven repository. Tại thư mục có `pom.xml`, chạy:

```bash
mvn -q -DskipTests package
java -jar target/pool-metrics-lab-1.0.0.jar
```

Đây là ứng dụng có Spring Boot và các dependency nên không chỉ chạy một lệnh `javac PoolMetricsApplication.java` trên tệp Java rời. Maven sẽ biên dịch và đóng gói đầy đủ classpath cần thiết.

Bên cạnh log khởi động và tắt ứng dụng, các dòng do chương trình in ra trong lần chạy đã kiểm chứng với Java 21 là:

```text
CHECK jdbc.name=dataSource
CHECK hikari.pool=lessonPool
CHECK jdbc.active.present=false
CHECK ready jdbcMax=1 hikariActive=0 idle=1 pending=0 total=1
CHECK held jdbcMax=1 hikariActive=1 idle=0 pending=0 total=1
CHECK waiting jdbcMax=1 hikariActive=1 idle=0 pending=1 total=1
CHECK wait.result=SQLTransientConnectionException
CHECK timeout.delta=1
CHECK usage.closed.whileHeld=0
CHECK returned jdbcMax=1 hikariActive=0 idle=1 pending=0 total=1
CHECK reborrow.query.ok=true
CHECK acquire.count.delta=3
CHECK usage.count.delta=2
```

Không đưa thời gian thực thi chính xác hoặc log có PID vào kết quả cố định vì các giá trị đó thay đổi giữa các máy.

### 6.4. Giải thích từng trạng thái

`ready`: pool có một kết nối rảnh. `active=0`, `idle=1`, `pending=0`. Gauge JDBC `max` báo giới hạn 1, không phải số kết nối đang dùng.

`held`: luồng chính đã mượn kết nối. `active=1`, `idle=0`. Tại thời điểm này không có câu SQL chậm nào được chạy. Thí nghiệm chứng minh trực tiếp rằng “active” có nghĩa đang được mượn.

`waiting`: luồng thứ hai đã gọi `getConnection()` trong khi kết nối duy nhất chưa trả. `pending=1`. Nó chưa thể chạy truy vấn.

`wait.result=SQLTransientConnectionException`: Hikari không cấp được kết nối trong thời hạn. `timeout.delta=1` xác nhận một lần hết hạn chờ mượn đã được ghi nhận.

`usage.closed.whileHeld=0`: Timer sử dụng chưa có mẫu hoàn tất mới, dù kết nối chính đang bị giữ. Dòng này minh họa vì sao cần xem cả Gauge đang dùng và thời gian sử dụng đã hoàn tất.

`returned`: kết nối chính đã trả về pool. Một kết nối lại rảnh, không còn luồng chờ. `reborrow.query.ok=true` xác minh đường mượn tiếp theo và truy vấn đơn giản vẫn hoạt động.

Trong tổ hợp HikariCP 5.1.0 của thí nghiệm, số mẫu `acquire` tăng 3: mượn để giữ, lần chờ thất bại và mượn phục hồi. Số mẫu `usage` tăng 2: trả kết nối đã giữ và trả kết nối phục hồi. Lần khởi động pool đã hoàn thành trước khi lấy mốc so sánh nên không tính vào các chênh lệch này.

Chương trình dùng `try-with-resources` để trả các kết nối, đóng context để tắt pool và dừng executor. Các khoảng đợi quan sát đều có thời hạn. Nếu không thấy trạng thái mong muốn, chương trình báo lỗi thay vì in một kết quả giả.

### 6.5. Tại sao `jdbc.active.present=false`?

Đây là hành vi đã quan sát của đúng cấu hình và phiên bản ở trên, không phải quy tắc nói rằng Hikari luôn thiếu Gauge JDBC.

Trong thí nghiệm, `HikariDataSource` khởi động pool khi gọi `getConnection()` lần đầu, sau khi context đã khởi động xong. Khi bộ đo JDBC dùng chung được gắn trước đó, có thể đọc được cấu hình `min/max` nhưng chưa có thống kê `active/idle` của pool đang chạy.

Trong Spring Boot 3.3.13, `DataSourcePoolMetrics` chỉ đăng ký một Gauge khi hàm lấy giá trị của Gauge đó trả về khác `null` tại lúc gắn. `HikariDataSourcePoolMetadata` có thể trả `null` cho active/idle khi chưa lấy được pool. Việc sau đó mở kết nối không tự bảo đảm các Gauge bị bỏ qua này sẽ được đăng ký lại.

Hikari đã được Spring Boot gắn `MicrometerMetricsTrackerFactory` nên các metric `hikaricp.*` xuất hiện khi pool được khởi động. Vì thế ví dụ dùng `jdbc.connections.max` để minh họa tag `name` và dùng các Gauge Hikari để quan sát trạng thái. Không thay một metric bị thiếu bằng số 0.

Khi gặp tình huống tương tự:

- Xem danh sách meter thực sự đã đăng ký, không chỉ gọi endpoint theo một tên dự đoán.
- Kiểm tra pool đã khởi động chưa, bean có bị bọc/định tuyến không và cơ chế lấy metadata có hỗ trợ nó không.
- Kiểm tra đúng tổ hợp phiên bản và thời điểm gắn bộ đo.
- Chỉ dùng khởi tạo sớm hoặc gắn bộ đo tường minh khi đã thiết kế rõ vòng đời, tránh gắn trùng với auto-configuration.

Nếu một ứng dụng khác khởi động pool sớm hơn, nó có thể có đủ `jdbc.connections.active` và `jdbc.connections.idle`. Không sửa kỳ vọng của toàn bộ hệ thống chỉ để mọi ứng dụng phải giống một thí nghiệm nhỏ.

## 7. Phân biệt những thời hạn liên quan

Các tên đều có chữ “timeout” nhưng bảo vệ những giai đoạn khác nhau:

| Cấu hình hoặc cơ chế | Giai đoạn chính | Cách hiểu sai cần tránh |
| --- | --- | --- |
| Hikari `connectionTimeout` | Đợi pool giao kết nối cho người mượn | Không phải thời hạn chạy SQL |
| Hikari `validationTimeout` | Kiểm tra kết nối còn hợp lệ | Không thay thế giới hạn truy vấn |
| Thời hạn truy vấn JDBC/driver | Thực thi câu lệnh theo khả năng driver | Không tự bảo đảm toàn bộ giao dịch kết thúc sạch |
| Thời hạn giao dịch | Phạm vi giao dịch, phụ thuộc bộ quản lý và tài nguyên | Không đồng nhất với một lần chờ pool |
| Hikari `idleTimeout` | Loại bớt kết nối rảnh theo điều kiện của pool | Không thu hồi ngay kết nối đang được mượn |
| Hikari `maxLifetime` | Vòng đời kết nối vật lý | Không cưỡng bức ngắt kết nối đang được mượn đúng lúc chạm mốc |

Trong thuộc tính Spring Boot, các cấu hình Hikari được viết dạng kebab-case, chẳng hạn `spring.datasource.hikari.connection-timeout`. Với các giá trị kiểu `long` mà Hikari nhận ở đây, đơn vị là mili giây; cấu hình 5000 nghĩa là 5000 ms.

Với cấu hình hữu hạn thông thường, Hikari 5.1.0 yêu cầu `connectionTimeout` tối thiểu 250 ms; `validationTimeout` cần nhỏ hơn `connectionTimeout`. Đây là ràng buộc cấu hình, không phải khuyến nghị mọi hệ thống nên đặt các giá trị thấp nhất.

`idleTimeout` có ý nghĩa thu nhỏ phần kết nối rảnh khi `minimumIdle` nhỏ hơn `maximumPoolSize`. Nếu đặt min bằng max như ví dụ, đừng kỳ vọng pool chủ động co về ít kết nối hơn chỉ vì hết thời gian rảnh.

`maxLifetime` giúp nghỉ các kết nối vật lý theo vòng đời, nhưng kết nối đang được mượn không bị thu hồi giữa chừng chỉ vì chạm mốc này. Đặt một giá trị ngắn không sửa được đoạn mã quên trả kết nối.

`leakDetectionThreshold` có thể giúp ghi log khi kết nối bị giữ quá ngưỡng. Đó là cảnh báo nghi ngờ giữ kết nối lâu, không phải bằng chứng tự động rằng mã đã làm rò rỉ, cũng không phải cơ chế tự đóng kết nối bị nghi ngờ. Một giao dịch hợp lệ nhưng rất dài vẫn có thể tạo cảnh báo.

Tách các thời hạn giúp chọn đúng biện pháp: tăng thời gian chờ mượn có thể làm người dùng chờ lâu hơn mà không tạo thêm năng lực xử lý; giới hạn truy vấn không sửa được một lời gọi dịch vụ ngoài đang giữ kết nối.

## 8. Đọc các tín hiệu cùng nhau để tìm nguyên nhân

### 8.1. `active` gần `max`, `pending` tăng

Đây là dấu hiệu pool đang khó cấp kết nối kịp cho nhu cầu. Hãy kiểm tra xem tình trạng kéo dài bao lâu và thời gian chờ mượn có tăng cùng không.

Các hướng điều tra có thể gồm:

- Truy vấn chậm hoặc đang chờ khóa trong database.
- Giao dịch bao trùm quá nhiều công việc.
- Mã giữ kết nối trong khi gọi dịch vụ ngoài hoặc xử lý dữ liệu lớn.
- Kết nối không được trả khi có ngoại lệ.
- Lưu lượng tăng vượt năng lực phục vụ hoặc giới hạn pool quá nhỏ cho tải đã đo.

Những số đo này xác định vị trí đang bị nghẽn; chúng chưa chọn sẵn một nguyên nhân. Đối chiếu log lỗi, thời gian yêu cầu, dấu vết thực thi và số liệu database trước khi sửa cấu hình.

### 8.2. `active` cao nhưng `pending` bằng 0

Pool có thể đang phục vụ tốt tải hiện tại. Một tỉ lệ sử dụng cao không tự động là sự cố nếu thời gian chờ mượn thấp và không có lỗi.

Ngược lại, một Gauge được lấy theo chu kỳ có thể bỏ qua đợt chờ rất ngắn. Vì vậy không dùng một lần đọc `pending=0` để phủ nhận mọi lần hết hạn hoặc mọi đợt chờ đã xảy ra giữa hai lần thu thập.

### 8.3. `timeout` tăng nhưng `total` còn dưới `max`

Không nhất thiết chỉ cần tăng `max`. Pool có thể không tạo được kết nối mới do lỗi xác thực, giới hạn kết nối ở database, lỗi mạng hoặc quá trình thiết lập kết nối quá lâu.

Xem log Hikari/driver, thử đường kết nối phù hợp và đối chiếu trạng thái database. Timer `creation` hỗ trợ quan sát quá trình tạo được ghi nhận nhưng không thay thế toàn bộ thông tin lỗi kết nối. Đừng suy từ một giá trị thời gian tạo bình thường rằng mọi lần tạo đều đã thành công.

### 8.4. `usage` tăng nhưng `acquire` vẫn thấp

Ứng dụng có thể đang giữ kết nối lâu hơn nhưng chưa tới mức làm người đến sau phải chờ. Đây là tín hiệu cần tìm phạm vi giữ kết nối và giao dịch, không phải lý do đổi mọi câu SQL ngay lập tức.

Lưu ý thêm sự trễ của Timer sử dụng: lần giữ lâu chỉ hoàn tất khi trả. Kết hợp số kết nối đang mượn, log giao dịch và dấu vết thực thi để hiểu việc đang xảy ra.

### 8.5. Có kết nối rảnh nhưng ứng dụng vẫn lỗi

Kết nối rảnh không chứng minh thông tin đăng nhập của mọi nguồn dữ liệu đều đúng, mọi bảng đều tồn tại hoặc mọi truy vấn đều nhanh. Metric pool phản ánh việc quản lý kết nối, trong khi tính đúng của SQL và nghiệp vụ là lớp khác.

Endpoint health và pool metric cũng trả lời những câu hỏi khác nhau. Một lần kiểm tra kết nối thành công không chứng minh pool chịu được tải đồng thời; một snapshot pool ít sử dụng không bảo đảm yêu cầu tiếp theo thành công.

## 9. Nhiều pool, nhiều instance và cách đặt giới hạn

Một ứng dụng có thể dùng pool đọc, pool ghi, pool cho tác vụ nền hoặc nhiều tenant. Mỗi bản sao ứng dụng còn có các pool riêng.

Khi nhìn biểu đồ:

- Giữ tag nhận diện pool và instance để không trộn các giới hạn khác nhau.
- Phân biệt Gauge JDBC có tag `name` với metric Hikari có tag `pool`.
- Không cộng hai nhóm JDBC và Hikari như hai bộ kết nối độc lập nếu chúng cùng quan sát một pool.
- Chỉ tổng hợp khi đã xác định rõ muốn trả lời câu hỏi của một pool, một instance hay toàn hệ thống.

Với nhiều pool, một `active` tổng thấp vẫn có thể che một pool nhỏ đang đầy. Ví dụ một pool ghi có giới hạn 5 và đang dùng cả 5 kết nối, trong khi pool đọc có giới hạn 50 nhưng không có tải. Tổng 5/55 không thể hiện việc các luồng cần pool ghi đang phải chờ.

Khi cân nhắc `maximumPoolSize`, cần tính tổng ngân sách kết nối tới cùng một database:

```text
Ngân sách kết nối có thể cần
    = tổng giới hạn của các pool trỏ tới database trên các instance
      + kết nối từ ứng dụng/công cụ khác
      + phần dành cho vận hành và dự phòng
```

Đây là cách lập kế hoạch giới hạn, không phải dự đoán mọi pool luôn mở đủ số kết nối tối đa. Khi tăng số instance, ngân sách tiềm năng cũng tăng dù cấu hình mỗi pool không đổi.

Tăng số kết nối không tự làm database xử lý nhanh hơn. Quá nhiều công việc đồng thời có thể tăng tranh chấp CPU, I/O hoặc khóa và làm thời gian giữ kết nối kéo dài. Dùng thử tải có kiểm soát và số liệu database để tìm điểm làm việc phù hợp.

Có thể ước lượng sơ bộ số kết nối đang được giữ bằng tốc độ công việc thực sự mượn kết nối nhân với thời gian giữ trung bình, nếu hệ thống ở trạng thái tương đối ổn định. Không nhân thẳng toàn bộ HTTP RPS khi nhiều yêu cầu không dùng database, và không coi một giá trị trung bình là đủ cho tải đột biến hay các giao dịch dài.

## 10. Từ xem tức thời tới theo dõi liên tục

`/actuator/metrics` tiện cho kiểm tra tên, tag và trạng thái hiện tại. Để thấy xu hướng, cần một registry xuất metric và hệ thống thu thập/lưu trữ phù hợp. Tên ở backend có thể được đổi theo quy tắc của backend; đừng chép tên có dấu chấm từ endpoint sang một câu truy vấn khác mà chưa kiểm tra tên đã xuất.

Một bộ biểu đồ hữu ích thường đặt cạnh nhau:

- Kết nối đang mượn, rảnh, tổng và giới hạn theo từng pool.
- Số luồng chờ và thời gian chờ mượn.
- Số lần hết hạn chờ mượn theo khoảng thời gian.
- Thời gian giữ kết nối đã hoàn tất.
- Độ trễ/lỗi yêu cầu của ứng dụng và tín hiệu tương ứng từ database.

Với Timer, trung bình của các mẫu trong một khoảng phải được tính từ chênh lệch tổng thời gian chia chênh lệch số mẫu trong cùng khoảng và cùng tập tag, khi số mẫu lớn hơn 0. Không lấy tổng thời gian tích lũy chia cho RPS của toàn ứng dụng. Phân vị hoặc histogram chỉ có khi được cấu hình và hỗ trợ; không suy ra p95 từ giá trị trung bình.

Counter timeout tích lũy có thể đặt lại khi tiến trình khởi động lại; registry xuất theo từng bước còn có cách tổng hợp riêng. Dùng cơ chế tốc độ/chênh lệch của backend, giữ ranh giới instance và xử lý reset phù hợp. Một số đếm “10” không nói riêng rằng trong phút vừa qua có 10 lỗi.

Cảnh báo nên gắn với thời gian kéo dài và tác động: chẳng hạn số lần hết hạn mới xuất hiện, hoặc chờ mượn tăng cùng số luồng chờ và độ trễ yêu cầu. Không có một ngưỡng phần trăm active áp dụng đúng cho mọi pool. Pool có một kết nối trong thí nghiệm chạm 100% ngay khi có người mượn; riêng điều đó chưa đủ kết luận sự cố.

## 11. Lỗi thường gặp và cách kiểm tra

| Hiện tượng hoặc cách làm | Điểm cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không có `jdbc.connections.active` | Pool đã khởi động chưa, metadata có giá trị lúc gắn chưa? | Khám phá meter thật và vòng đời đăng ký; không đổi thiếu dữ liệu thành 0 |
| Không có `hikaricp.*` | Có đúng Hikari đang chạy và đã gắn Micrometer không? | Kiểm tra bean thực tế, phiên bản, cấu hình bộ đo và registry |
| Có metric nhưng truy vấn HTTP không thấy | Endpoint có được phơi bày, URL/tag có đúng và có quyền không? | Tách lỗi truy cập HTTP khỏi lỗi đăng ký meter |
| Gọi `active` là số SQL đang chạy | Có luồng giữ kết nối mà chưa chạy SQL không? | Diễn giải là kết nối đang được mượn |
| Dùng `acquire` làm thời gian chạy SQL | Timer có bao gồm thời gian chờ pool không? | Đo và đối chiếu SQL/giao dịch bằng cơ chế phù hợp |
| Chỉ nhìn `usage` để tìm kết nối bị giữ | Kết nối nghi ngờ đã trả chưa? | Xem thêm active, phạm vi giao dịch và thông tin giữ kết nối |
| Tăng pool khi có timeout | Database còn năng lực và ngân sách kết nối không? | Tìm nguyên nhân, đo lại sau từng thay đổi |
| Đặt thời hạn mượn thật dài để hết lỗi | Yêu cầu đang đợi lâu hơn hay thực sự xử lý tốt hơn? | Đối chiếu độ trễ, số luồng chờ và năng lực phục vụ |
| Bật leak detection rồi coi mọi log là rò rỉ | Có giao dịch hợp lệ nhưng dài không? | Điều tra stack/log và đường trả kết nối |
| Cộng số liệu JDBC với Hikari | Có đang đo trùng một pool không? | Chọn một lớp cho phép tổng hợp nhất quán |

Không cần tự tạo Counter mới mang tên “active” quanh mỗi truy vấn: số đang sử dụng là trạng thái có tăng có giảm và pool đã cung cấp Gauge phù hợp. Bộ đếm tự viết ở lớp repository còn có thể không thấy các lần mượn ngoài lớp đó hoặc các kết nối được giữ bởi giao dịch.

## 12. Bài tập tự kiểm chứng

1. Trong ví dụ độc lập, thay `maximum-pool-size` thành 2 và suy luận điều gì thay đổi. Luồng thứ hai có thể mượn ngay nên không còn đợi đến timeout. Chương trình hiện có các điều kiện kiểm tra dành cho pool một kết nối; cần sửa kịch bản và kỳ vọng tương ứng, không coi lỗi kiểm tra là Hikari hỏng.
2. Giữ pool một kết nối nhưng đóng kết nối chính trước khi lần chờ hết hạn. Luồng chờ có thể thành công và phải trả kết nối của nó. Khi đó không được tiếp tục kỳ vọng `timeout.delta=1`.
3. Trong ứng dụng web có sẵn, khám phá tag thật của từng pool rồi truy vấn riêng `active`, `pending`, `acquire` và `timeout`. Ghi rõ đâu là số tức thời, đâu là mẫu thời gian, đâu là số đếm.
4. Chọn một thao tác dùng giao dịch và xác định phần nào cần giữ kết nối. Nếu có lời gọi mạng không liên quan tới tính nhất quán dữ liệu, phân tích khả năng rút ngắn phạm vi giao dịch trước khi đổi giới hạn pool.

Câu hỏi kiểm tra hiểu bài:

- Vì sao một kết nối active có thể chưa chạy SQL? Vì nó đã được mượn, còn việc dùng thời gian giữ để làm gì phụ thuộc mã ứng dụng.
- Vì sao thiếu metric khác với metric bằng 0? Thiếu nghĩa là chưa có phép đo phù hợp; 0 là giá trị của một phép đo đã tồn tại.
- Vì sao timeout khi mượn khác SQL timeout? Lần đầu có thể chưa nhận được kết nối, còn lần sau xảy ra trong giai đoạn thực thi câu lệnh.
- Vì sao số mẫu acquire tăng 3 nhưng số mẫu usage chỉ tăng 2 trong thí nghiệm? Lần chờ thất bại được ghi thời gian acquire nhưng không có kết nối đã mượn để trả.
- Vì sao nhiều instance làm thay đổi quyết định tăng pool? Mỗi instance có giới hạn riêng, trong khi chúng có thể cùng tiêu thụ ngân sách kết nối của một database.

## 13. Tài liệu đối chiếu

- [Spring Boot 3.3 — DataSource metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.jdbc): nhóm JDBC dùng chung và HikariCP.
- [Spring Boot 3.3.13 — DataSourcePoolMetricsAutoConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/jdbc/DataSourcePoolMetricsAutoConfiguration.java): cách gắn bộ đo và đặt tag.
- [HikariCP 5.1.0 — MicrometerMetricsTracker](https://github.com/brettwooldridge/HikariCP/blob/HikariCP-5.1.0/src/main/java/com/zaxxer/hikari/metrics/micrometer/MicrometerMetricsTracker.java): tên metric và các loại phép đo.
- [HikariCP 5.1.0 — HikariPool](https://github.com/brettwooldridge/HikariCP/blob/HikariCP-5.1.0/src/main/java/com/zaxxer/hikari/pool/HikariPool.java): thống kê pool và đường đi khi hết hạn chờ.
- [HikariCP 5.1.0 — PoolBase](https://github.com/brettwooldridge/HikariCP/blob/HikariCP-5.1.0/src/main/java/com/zaxxer/hikari/pool/PoolBase.java): cách ghi thời gian mượn và sử dụng.
- [HikariCP 5.1.0 — HikariConfig](https://github.com/brettwooldridge/HikariCP/blob/HikariCP-5.1.0/src/main/java/com/zaxxer/hikari/HikariConfig.java): ràng buộc các giá trị cấu hình.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): số mẫu, tổng thời gian và cách dùng đơn vị.
- [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html): giá trị tại thời điểm quan sát và giới hạn của phép lấy mẫu.
- [HikariCP — cấu hình](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): ý nghĩa các thuộc tính pool; cần đối chiếu phiên bản đang chạy.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): mối liên hệ giữa số kết nối, mức đồng thời và năng lực database.
