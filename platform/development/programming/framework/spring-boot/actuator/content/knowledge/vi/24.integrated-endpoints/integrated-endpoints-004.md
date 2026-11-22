# Kiểm tra lịch sử migration bằng endpoint `flyway`

## 1. Endpoint này giúp trả lời câu hỏi gì?

Một thay đổi mã Java có thể cần thêm bảng, cột hoặc dữ liệu khởi tạo tương ứng trong cơ sở dữ liệu. Migration là một thay đổi cơ sở dữ liệu được mô tả và quản lý theo trình tự. Flyway chạy các migration và ghi nhận lịch sử để những lần triển khai sau biết thay đổi nào đã được áp dụng.

Khi một chức năng báo thiếu cột, câu hỏi vận hành không chỉ là “bản Java nào đang chạy?”, mà còn là “cơ sở dữ liệu mà ứng dụng này sử dụng đã nhận migration cần thiết chưa?”.

Endpoint tích hợp `flyway` của Spring Boot Actuator đưa thông tin migration của các Flyway bean ra giao diện quản trị:

~~~text
Tệp migration đi cùng ứng dụng
              +
Lịch sử Flyway trong cơ sở dữ liệu
              ↓
       Flyway.info().all()
              ↓
ApplicationContext → Flyway bean → danh sách migration
              ↓
     GET /actuator/flyway
~~~

Cần giữ riêng ba việc:

| Việc | Công cụ/cơ chế |
| --- | --- |
| Quan sát thông tin migration | Endpoint `flyway`, hoặc Flyway `info` |
| Áp dụng thay đổi cơ sở dữ liệu | Flyway `migrate` |
| Kiểm tra migration hiện có có khớp lịch sử không | Flyway `validate` |

GET endpoint không phải nút triển khai migration, không thực hiện `repair`, và không cung cấp kết quả kiểm tra toàn bộ cấu trúc cơ sở dữ liệu. Hợp đồng Java của endpoint chỉ khai báo thao tác đọc `flywayBeans()`. Nguồn: [API FlywayEndpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/flyway/FlywayEndpoint.html).

Bài dùng Spring Boot **3.3.x**. Ví dụ thực thi cố định Boot **3.3.0**, Flyway **10.10.0**, H2 **2.2.224**, với Java **17 trở lên**. Đây là các phiên bản dùng cho thí nghiệm; khi làm việc với hệ thống khác, cần đối chiếu đúng phiên bản mà hệ thống đó sử dụng.

## 2. Lịch sử được lưu ở đâu, và trạng thái được hiểu như thế nào?

Flyway lưu dấu vết áp dụng migration trong bảng lịch sử lược đồ (schema history table), mặc định tên là `flyway_schema_history`. Tên bảng và schema chứa bảng có thể được cấu hình. Lịch sử này ghi thông tin như phiên bản, script, checksum, thời điểm và kết quả thực thi.

Tuy nhiên, **trạng thái trong API không chỉ là sao chép một cột `state` từ bảng lịch sử**. Flyway đối chiếu lịch sử trong cơ sở dữ liệu với migration mà phiên bản ứng dụng hiện tại tìm được và cấu hình đang dùng, rồi xác định trạng thái.

Ví dụ:

- Tệp V2 có trong ứng dụng, cơ sở dữ liệu mới áp dụng V1: V2 có thể là `PENDING`.
- Cơ sở dữ liệu đã áp dụng V2 nhưng ứng dụng không còn tìm thấy tệp tương ứng: trạng thái phải được đọc trong quan hệ giữa lịch sử và các tệp hiện tại.
- Có cấu hình `target` giới hạn phiên bản: một migration chưa chạy có thể là `ABOVE_TARGET`, không phải `PENDING`.

Vì vậy, khi điều tra cần xác định cùng lúc **bản ứng dụng, cấu hình Flyway và cơ sở dữ liệu đích**. Xem [bảng lịch sử và các trạng thái của Flyway](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/flyway-schema-history-table).

Đặc biệt, trong Boot 3.3, endpoint gọi **`Flyway.info().all()`**. Danh sách có thể chứa cả migration đã áp dụng và migration chưa áp dụng mà Flyway phân giải được. Không được coi mọi phần tử trong mảng `migrations` là một thay đổi đã chạy thành công.

## 3. Điều kiện để endpoint xuất hiện qua HTTP

Một ứng dụng web cần có Actuator và ít nhất một Flyway bean được cấu hình phù hợp. Nếu dùng cơ chế tự cấu hình của Boot, dependency Flyway, JDBC DataSource và các thiết lập liên quan quyết định việc tạo bean và khởi tạo migration.

Ví dụ dependency cho lab H2, ghép vào dự án Gradle đã quản lý phiên bản bằng Spring Boot 3.3:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.flywaydb:flyway-core'
    runtimeOnly 'com.h2database:h2'
}
~~~

Đây là đoạn cấu hình của một dự án Spring Boot hiện có, không phải toàn bộ dự án Gradle độc lập.

Cấu hình minh họa trong `application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: flyway-lab
  datasource:
    url: jdbc:h2:mem:flyway_web_lab;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  sql:
    init:
      mode: never
  flyway:
    enabled: true
    locations: classpath:db/migration

management:
  endpoint:
    flyway:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,flyway
~~~

Ba thiết lập khác vai trò:

| Thiết lập | Vai trò |
| --- | --- |
| `spring.flyway.enabled` | Điều khiển cơ chế tự cấu hình Flyway của Boot |
| `management.endpoint.flyway.enabled` | Bật/tắt endpoint quản trị trong Boot 3.3 |
| `management.endpoints.web.exposure.include` | Chọn endpoint được công bố qua HTTP |

Bật endpoint không tự tạo Flyway bean; công bố qua HTTP cũng không tự cấp quyền truy cập. Nếu có `exposure.exclude`, phải kiểm tra vì nó được ưu tiên hơn `include`. Nguồn: [cấu hình endpoint Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Với Boot 3.3, H2 được hỗ trợ qua `flyway-core`; một số hệ quản trị khác cần thêm module Flyway tương ứng, chẳng hạn `flyway-database-postgresql` cho PostgreSQL. Không suy từ việc đã có JDBC driver rằng đã có đầy đủ hỗ trợ Flyway cho mọi hệ quản trị.

Theo cấu hình thông thường, Boot gọi `Flyway.migrate()` khi khởi động. Điều này xảy ra ở vòng đời khởi tạo, **không phải do người vận hành gọi GET endpoint**. Mặc định script nằm dưới `classpath:db/migration`, với dạng tên như `V1__create_product.sql` — có **hai dấu gạch dưới** giữa phiên bản và mô tả. Nguồn: [khởi tạo cơ sở dữ liệu bằng Flyway trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html#howto.data-initialization.migration-tool.flyway).

Nếu đang dùng JPA, tránh để nhiều cơ chế cùng tự ý tạo/sửa schema mà không có phân công rõ ràng. Trong lab trên, cơ chế SQL init cơ bản được tắt để việc tạo bảng thuộc về migration.

## 4. Gọi endpoint và đọc đúng cấu trúc phản hồi

Với cổng và đường dẫn quản trị mặc định của lab:

~~~shell
curl -i "http://localhost:8080/actuator/flyway"
~~~

Trên Windows PowerShell có alias `curl`, dùng `curl.exe` nếu muốn gọi đúng công cụ curl. Ví dụ giả định yêu cầu đã được cấp quyền truy cập.

Một phần thân JSON **minh họa** cho migration SQL đã chạy thành công:

~~~json
{
  "contexts": {
    "application": {
      "flywayBeans": {
        "flyway": {
          "migrations": [
            {
              "type": "SQL",
              "checksum": -120035678,
              "version": "1",
              "description": "create product",
              "script": "V1__create_product.sql",
              "state": "SUCCESS",
              "installedBy": "SA",
              "installedOn": "2026-11-06T03:00:00Z",
              "installedRank": 1,
              "executionTime": 7
            }
          ]
        }
      }
    }
  }
}
~~~

Checksum, thời gian và thời điểm trong JSON trên là dữ liệu minh họa, không phải giá trị cố định của script trong bài. Khi thực hành, lấy giá trị từ phản hồi thực tế.

Đường đi đến mảng cần đọc là:

~~~text
contexts
  → ID ApplicationContext
    → flywayBeans
      → tên Flyway bean
        → migrations
~~~

`application` và `flyway` là các khóa ví dụ. Không hard-code rằng mọi hệ thống luôn có đúng hai tên này. Có thể có nhiều context, context cha và nhiều Flyway bean. Trong hệ thống nhiều cơ sở dữ liệu, phải đối chiếu bean với cấu hình DataSource/schema của nó trước khi kết luận một migration đã có mặt ở đúng nơi.

Các trường cần đọc:

| Trường | Ý nghĩa |
| --- | --- |
| `version` | Phiên bản migration, nếu có |
| `description` | Mô tả |
| `script` | Tên script |
| `type` | Loại migration |
| `state` | Trạng thái Flyway xác định |
| `checksum` | Giá trị kiểm tra nội dung, nếu có |
| `installedBy` | Tài khoản cơ sở dữ liệu thực thi |
| `installedOn` | Thời điểm áp dụng |
| `installedRank` | Thứ tự trong lịch sử áp dụng |
| `executionTime` | Thời gian thực thi, đơn vị mili giây |

Hợp đồng cấu trúc và đơn vị được mô tả tại [Actuator Flyway HTTP API của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/flyway.html).

Những cách đọc dễ sai:

- `installedBy` thường là tài khoản kết nối cơ sở dữ liệu, không chứng minh một cá nhân cụ thể đã bấm triển khai.
- `installedRank` là thứ tự áp dụng, không đồng nhất với số phiên bản. Khi áp dụng ngoài thứ tự, hai thông tin càng cần được đọc riêng.
- Không so sánh phiên bản theo thứ tự chuỗi thông thường: chuỗi `"10"` và `"2"` không có thứ tự phiên bản chỉ nhờ phép so sánh ký tự.
- Checksum âm không tự mang nghĩa lỗi; cần đối chiếu bằng cơ chế Flyway, không dựa vào dấu của số.
- Migration chưa chạy chưa có thời điểm, người chạy, thứ tự hay thời lượng áp dụng. Các trường tương ứng có thể chưa có giá trị.
- Migration lặp lại (repeatable migration) có thể không có `version`. Không ép mọi migration phải là `V1`, `V2` hoặc có cùng bộ giá trị không null.

## 5. Đọc trạng thái để chọn bước điều tra tiếp theo

Các tên trạng thái trong JSON là tên enum viết hoa. Một số trạng thái thường cần phân biệt:

| Trạng thái | Cách hiểu trong phạm vi quan sát |
| --- | --- |
| `SUCCESS` | Migration đã áp dụng thành công |
| `PENDING` | Migration được tìm thấy, đang chờ áp dụng |
| `ABOVE_TARGET` | Migration nằm trên giới hạn target đang cấu hình |
| `FAILED` | Có migration thất bại được lịch sử/trạng thái phản ánh |
| `MISSING_SUCCESS` | Migration đã thành công nhưng không còn được phân giải từ nguồn hiện tại |
| `FUTURE_SUCCESS` | Migration đã thành công có phiên bản cao hơn mức cao nhất nguồn hiện tại phân giải được |
| `OUT_OF_ORDER` | Migration được áp dụng ngoài thứ tự phiên bản |
| `OUTDATED` / `SUPERSEDED` | Các trạng thái liên quan đến vòng đời migration lặp lại |

Danh sách này không thay thế đầy đủ quy tắc trạng thái của phiên bản Flyway cụ thể. Ví dụ, trạng thái phụ thuộc nguồn migration, `target`, baseline và lịch sử thực tế; không thể chẩn đoán mọi nguyên nhân chỉ từ một tên enum. Đối chiếu [mô hình trạng thái của Flyway](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/flyway-schema-history-table).

Nếu thấy V2 là `PENDING`, câu hỏi tiếp theo là: có đúng bản ứng dụng và đúng cơ sở dữ liệu cần triển khai không; pipeline có chủ ý chưa áp dụng V2 không? Không chuyển thẳng từ “đang chờ” sang “phải chạy ngay trên môi trường này”.

Nếu thấy `MISSING_SUCCESS` hoặc `FUTURE_SUCCESS`, cần kiểm tra gói ứng dụng và `locations`: một bản ứng dụng cũ có thể nhìn vào cơ sở dữ liệu đã được bản mới nâng cấp. Endpoint phản ánh quan hệ đó; nó không tự chứng minh cơ sở dữ liệu bị hỏng.

## 6. Thí nghiệm Java: quan sát V2 đang chờ, rồi áp dụng riêng

Thí nghiệm sau sử dụng H2 trong bộ nhớ và gọi trực tiếp **chính `FlywayEndpoint` của Actuator**. Nó không khởi động HTTP server và không dùng cơ sở dữ liệu thật.

Ý tưởng:

1. Tạo V1 thêm bảng `product`, V2 thêm cột `price`.
2. Chạy Flyway lần đầu với `target=1` để chỉ áp dụng V1.
3. Tạo Flyway bean khác trên cùng cơ sở dữ liệu và cùng script, nhưng không giới hạn target.
4. Đọc endpoint: V1 đã thành công, V2 đang chờ.
5. Đọc lại và kiểm tra V2 vẫn chờ.
6. Gọi `migrate()` riêng, rồi đọc lại.

Việc bỏ giới hạn target ở bước 3 là có chủ ý. Nếu tiếp tục dùng Flyway với `target=1`, trạng thái V2 có thể là `ABOVE_TARGET`, nên đó sẽ là một thí nghiệm khác.

### 6.1. Dependency

Trong thư mục lab riêng, tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>flyway-history-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.flywaydb</groupId>
            <artifactId>flyway-core</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Parent Boot 3.3.0 quản lý các phiên bản thư viện dùng cho lab. Maven ở đây chỉ tạo classpath dependency; ta dùng `javac` và `java` trực tiếp.

### 6.2. Chương trình đầy đủ

Đặt `FlywayHistoryDemo.java` cùng cấp với `pom.xml`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.flywaydb.core.Flyway;
import org.springframework.boot.actuate.flyway.FlywayEndpoint;
import org.springframework.context.support.GenericApplicationContext;

public class FlywayHistoryDemo {
    public static void main(String[] args) throws Exception {
        Logger.getLogger("org.flywaydb").setLevel(Level.OFF);
        Path directory = Files.createTempDirectory("flyway-history-demo-");
        Path v1 = directory.resolve("V1__create_product.sql");
        Path v2 = directory.resolve("V2__add_price.sql");
        try {
            Files.writeString(v1,
                    "CREATE TABLE product (id BIGINT PRIMARY KEY, name VARCHAR(100));");
            Files.writeString(v2,
                    "ALTER TABLE product ADD COLUMN price DECIMAL(12,2);");
            String url = "jdbc:h2:mem:flyway_history_demo;DB_CLOSE_DELAY=-1";
            String location = "filesystem:" + directory.toAbsolutePath();

            Flyway.configure().dataSource(url, "sa", "")
                    .locations(location).target("1").load().migrate();

            Flyway flyway = Flyway.configure().dataSource(url, "sa", "")
                    .locations(location).load();
            try (GenericApplicationContext context = new GenericApplicationContext()) {
                context.setId("lab");
                context.getBeanFactory().registerSingleton("flyway", flyway);
                context.refresh();
                FlywayEndpoint endpoint = new FlywayEndpoint(context);

                print("before read", endpoint);
                endpoint.flywayBeans();
                System.out.println("pending after read="
                        + flyway.info().pending().length);

                flyway.migrate();
                print("after migrate", endpoint);
                System.out.println("pending after migrate="
                        + flyway.info().pending().length);
            }
        } finally {
            Files.deleteIfExists(v2);
            Files.deleteIfExists(v1);
            Files.deleteIfExists(directory);
        }
    }

    private static void print(String label, FlywayEndpoint endpoint) {
        System.out.println(label);
        var migrations = endpoint.flywayBeans().getContexts()
                .get("lab").getFlywayBeans().get("flyway").getMigrations();
        for (var migration : migrations) {
            System.out.println("version=" + migration.getVersion()
                    + " state=" + migration.getState().name()
                    + " rank=" + migration.getInstalledRank());
        }
    }
}
~~~

Chương trình tạo đúng hai script trong một thư mục tạm riêng rồi xóa chúng khi kết thúc. H2 nằm trong bộ nhớ của tiến trình. `DB_CLOSE_DELAY=-1` giữ cơ sở dữ liệu này giữa các lần Flyway mở/đóng kết nối trong cùng lần chạy; nó không biến dữ liệu thành lưu trữ bền vững qua các tiến trình.

Context được đặt ID `lab` và đăng ký bean `flyway` tường minh, vì vậy chương trình biết chính xác đường đi để lấy danh sách. Khi đọc JSON của ứng dụng thật, phải dùng các khóa thực tế.

### 6.3. Biên dịch và chạy

Yêu cầu JDK 17+, Maven; lần đầu lấy dependency cần truy cập kho Maven.

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$flywayClasspath = (Get-Content -LiteralPath .\classpath.txt -Raw).Trim()
javac --release 17 -cp "$flywayClasspath" FlywayHistoryDemo.java
java -cp ".;$flywayClasspath" FlywayHistoryDemo
~~~

Linux/macOS:

~~~shell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
flyway_classpath="$(cat classpath.txt)"
javac --release 17 -cp "$flyway_classpath" FlywayHistoryDemo.java
java -cp ".:$flyway_classpath" FlywayHistoryDemo
~~~

Stdout của chương trình:

~~~text
before read
version=1 state=SUCCESS rank=1
version=2 state=PENDING rank=null
pending after read=1
after migrate
version=1 state=SUCCESS rank=1
version=2 state=SUCCESS rank=2
pending after migrate=0
~~~

Chương trình giảm log JUL của Flyway để tập trung vào các dòng trên; cấu hình logging khác có thể còn ghi log bổ sung.

Điểm cần giải thích được:

- `rank=null` của V2 trước khi migrate phù hợp với việc chưa có lần áp dụng.
- `pending after read=1` chứng minh thao tác đọc không áp dụng V2.
- Sau lệnh `migrate()` riêng, V2 có `SUCCESS` và thứ tự áp dụng là 2.
- `pending after migrate=0` xác nhận không còn migration chờ chạy trong đúng bộ script và cơ sở dữ liệu của lab.

Đây là bằng chứng trên cấu hình đã nêu, không phải giả định mọi môi trường đều chỉ có hai migration hoặc mọi ID context đều là `lab`.

## 7. Áp dụng cách quan sát vào ứng dụng web

Trong ứng dụng web đã có cấu hình ở phần 3, đặt hai script SQL dưới:

~~~text
src/main/resources/db/migration/
├── V1__create_product.sql
└── V2__add_price.sql
~~~

Nội dung V1:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100)
);
~~~

Nội dung V2:

~~~sql
ALTER TABLE product ADD COLUMN price DECIMAL(12,2);
~~~

Với cơ sở dữ liệu lab mới và cấu hình khởi tạo mặc định, Boot chạy migration khi khởi động; lúc ứng dụng sẵn sàng, GET thường cho thấy cả V1 và V2 là `SUCCESS`. Điều này không mâu thuẫn với thí nghiệm ở phần 6, vì thí nghiệm chủ động dừng lần chạy đầu tại V1.

Có thể đọc mọi context và bean trong PowerShell mà không giả định tên khóa:

~~~powershell
$response = Invoke-RestMethod -Uri "http://localhost:8080/actuator/flyway"
$rows = foreach ($context in $response.contexts.PSObject.Properties) {
    foreach ($bean in $context.Value.flywayBeans.PSObject.Properties) {
        foreach ($migration in $bean.Value.migrations) {
            [pscustomobject]@{
                Context = $context.Name
                Bean = $bean.Name
                Version = $migration.version
                State = $migration.state
                Rank = $migration.installedRank
                Script = $migration.script
            }
        }
    }
}
$rows | Format-Table -AutoSize
~~~

Đây là phép chiếu thông tin để đọc; nó không thay đổi trạng thái migration. Nếu hệ thống yêu cầu xác thực, bổ sung phương thức xác thực đã được cấu hình cho môi trường đó.

Khi theo dõi một bản phát hành cần V2, hãy tìm đúng migration trong đúng bean rồi kiểm tra `state`. Việc tên V2 xuất hiện trong mảng chưa đủ: `PENDING` và `SUCCESS` dẫn tới hai kết luận triển khai khác nhau.

## 8. Những kết luận endpoint không bảo đảm

### 8.1. HTTP 200 không đồng nghĩa mọi migration thành công

`200` cho biết thao tác đọc endpoint thành công ở tầng HTTP. Mảng trả về vẫn có thể chứa migration chưa áp dụng hoặc trạng thái cần điều tra. Công cụ giám sát phải đọc nội dung, không chỉ kiểm tra mã HTTP.

Endpoint `flyway` cũng không tự biến các trạng thái đó thành một kết quả `health` theo quy tắc nghiệp vụ của hệ thống. Nếu cần chặn triển khai theo trạng thái migration, quy tắc phải được đặt rõ trong kiểm tra triển khai.

### 8.2. SUCCESS trong lịch sử không thay thế validate

Giả sử V1 đã được áp dụng, sau đó ai đó sửa nội dung tệp V1 trong gói ứng dụng. Việc nhìn thấy một dòng lịch sử thành công không phải kết quả xác minh checksum giữa hai bên.

`validate` dùng để đối chiếu migration đã áp dụng với các migration hiện có, bao gồm tên, loại và checksum theo cấu hình Flyway. Nguồn: [lệnh Validate của Flyway](https://documentation.red-gate.com/flyway/reference/commands/validate).

Không yêu cầu người đọc tự tính lại checksum bằng một hàm băm tùy ý rồi so với số trong JSON. Hãy dùng cơ chế kiểm tra của Flyway và đúng tập nguồn migration.

### 8.3. Lịch sử không chứng minh schema hiện tại chưa từng bị sửa ngoài Flyway

Nếu một cột bị xóa thủ công sau lúc V2 đã chạy, bản ghi V2 thành công vẫn có thể còn. Lịch sử ghi nhận lần áp dụng, không tự trở thành phép kiểm tra toàn bộ bảng, cột, ràng buộc và dữ liệu hiện tại.

Khi lỗi ứng dụng mâu thuẫn với lịch sử, phải kiểm tra cấu trúc thật và cơ sở dữ liệu mà yêu cầu đang sử dụng, thay vì chỉ đọc lại cùng một dòng `SUCCESS`.

### 8.4. Không phải mọi migration lỗi đều quan sát được qua ứng dụng đang chạy

Nếu migration thất bại trong quá trình khởi tạo, ứng dụng có thể không khởi động tới lúc phục vụ HTTP. Khi đó endpoint không sẵn sàng; nguồn điều tra là log khởi động và trạng thái cơ sở dữ liệu.

Khả năng một lần chạy thất bại để lại dấu vết hay thay đổi từng phần còn phụ thuộc cơ sở dữ liệu và giao dịch. Không được suy “không thấy FAILED trong endpoint” thành “chưa từng có lỗi”.

## 9. Xử lý các tình huống thường gặp

| Hiện tượng | Điều cần xác minh |
| --- | --- |
| Endpoint trả `404` | Đúng cổng/base path chưa; endpoint có được bật/công bố không; có Flyway bean không |
| Trả `401` hoặc `403` | Cấu hình xác thực và phân quyền của đường quản trị |
| Không thấy migration mong đợi | Đúng bean, datasource, schema, bản ứng dụng và `locations` chưa; tên tệp có hợp lệ không |
| Thấy V2 nhưng chức năng vẫn thiếu cột | Đọc `state`; đối chiếu cơ sở dữ liệu thực tế và cấu trúc hiện tại |
| Một môi trường có `PENDING`, môi trường khác có `SUCCESS` | Có cùng bản ứng dụng, cấu hình target và cùng kế hoạch triển khai không |
| Trạng thái thiếu hoặc thuộc tương lai | Gói ứng dụng có cũ hoặc thiếu migration so với cơ sở dữ liệu không |
| Ứng dụng không lên sau khi thêm migration | Đọc log khởi động; không chờ một endpoint mà tiến trình chưa phục vụ |
| Gặp lỗi truy cập cơ sở dữ liệu khi đọc | Kiểm tra kết nối, quyền đọc metadata/lịch sử và cấu hình Flyway đang dùng |

Không có hợp đồng tích hợp `POST /actuator/flyway/migrate` hay `POST /actuator/flyway/repair` trong endpoint này. Không thử biến yêu cầu quan sát thành thao tác ghi bằng cách thay HTTP method.

`repair` thay đổi bảng lịch sử và không tự hoàn tác mọi đối tượng cơ sở dữ liệu còn lại sau lỗi. Nếu cần xử lý sai lệch lịch sử, phải điều tra nguyên nhân và thực hiện theo quy trình thay đổi cơ sở dữ liệu đã được phê duyệt; không coi nó là bước mặc định sau khi đọc thấy trạng thái lạ. Nguồn: [phạm vi của lệnh Repair](https://documentation.red-gate.com/flyway/reference/commands/repair).

Thông tin endpoint có thể tiết lộ tên script, cấu trúc phiên bản và tài khoản thực thi. Cấp quyền xem theo nhu cầu vận hành; việc thêm `flyway` vào danh sách công bố HTTP không thay thế bảo mật của ứng dụng.

## 10. Thực hành đọc bằng chứng theo một bản phát hành

Giả sử bản phát hành mới cần cột `product.price` do V2 thêm vào.

1. Xác định đúng môi trường, bản ứng dụng và Flyway bean gắn với cơ sở dữ liệu chứa bảng `product`.
2. GET endpoint, tìm script V2 và đọc `state`, thay vì chỉ tìm tên.
3. Nếu V2 là `PENDING`, kiểm tra trạng thái triển khai migration; GET thêm lần nữa không tự áp dụng nó.
4. Nếu V2 là `SUCCESS` nhưng chức năng vẫn lỗi, kiểm tra datasource thực tế và cấu trúc hiện tại.
5. Nếu nghi ngờ script từng bị sửa, dùng bước kiểm tra `validate` của quy trình triển khai; không kết luận chỉ từ checksum đang hiển thị.

**Bài tập tự kiểm tra:**

- Trong thí nghiệm, giữ `target=1` cho Flyway bean quan sát rồi dự đoán trạng thái V2. Vì sao nó khác `PENDING`?
- Đọc endpoint hai lần trước `migrate()`. Những giá trị nào cho biết V2 chưa được áp dụng?
- Giải thích vì sao `installedRank=2` không có nghĩa mọi migration trên hệ thống đều phải mang phiên bản `"2"`.
- Một bản ứng dụng cũ nhìn vào cơ sở dữ liệu đã được bản mới nâng cấp: cần kiểm tra những nguồn nào trước khi sửa lịch sử?
- HTTP `200` và một dòng `SUCCESS` riêng lẻ cung cấp bằng chứng gì, và còn thiếu bằng chứng nào để xác nhận chức năng dùng đúng schema?

Mỗi nhận định nên gắn với **context, Flyway bean, cơ sở dữ liệu đích và trạng thái migration cụ thể** để người khác có thể kiểm tra lại.
