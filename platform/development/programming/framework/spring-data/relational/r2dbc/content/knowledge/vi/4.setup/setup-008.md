# Kiểm tra kết nối bằng một truy vấn phản ứng đơn giản

Khi khởi tạo ứng dụng Spring Data R2DBC, cần xác nhận rằng ứng dụng có thể mở kết nối đến cơ sở dữ liệu và thực thi được một câu SQL. Cách kiểm tra trực tiếp, dễ hiểu là chạy truy vấn `SELECT 1` thông qua `DatabaseClient`. Truy vấn này không phụ thuộc vào bảng nghiệp vụ, nên giúp kiểm tra đường kết nối và khả năng thực thi SQL trước khi điều tra entity hoặc repository.

Trong ứng dụng reactive, kết quả truy vấn được biểu diễn bằng `Mono` hoặc `Flux`. Tạo publisher chưa có nghĩa là truy vấn đã chạy; truy vấn được thực thi khi publisher được subscribe. Spring WebFlux có thể tiêu thụ publisher khi xử lý request, còn bài kiểm thử có thể dùng `StepVerifier` để subscribe và xác nhận kết quả.

## 1. Mục tiêu và phạm vi của phép kiểm tra

Một phép kiểm tra kết nối đơn giản thường cần trả lời ba câu hỏi:

1. Ứng dụng có tìm được R2DBC driver và tạo được `ConnectionFactory` không?
2. Driver có mở được kết nối đến database với URL và thông tin xác thực đã cấu hình không?
3. Kết nối có thực thi được một câu SQL đơn giản và trả kết quả về ứng dụng không?

Truy vấn `SELECT 1` phù hợp cho bước khởi tạo vì nó không cần bảng, entity hay dữ liệu mẫu:

```sql
SELECT 1 AS probe_value;
```

Nếu truy vấn trả về giá trị `1`, ứng dụng đã đi qua được các bước tạo kết nối, gửi câu lệnh và đọc kết quả. Phép thử này chưa chứng minh rằng mọi bảng nghiệp vụ đều tồn tại, người dùng database có đủ quyền trên từng bảng, mapping entity chính xác, giao dịch hoạt động đúng hoặc hệ thống chịu được tải thực tế. Những nội dung đó cần được kiểm tra riêng.

## 2. Chuẩn bị dependency và database driver

Ứng dụng cần Spring Data R2DBC và driver tương ứng với hệ quản trị cơ sở dữ liệu. Ví dụ dưới đây sử dụng PostgreSQL và Spring Boot với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    runtimeOnly 'org.postgresql:r2dbc-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Các phiên bản dependency thường được quản lý bởi Spring Boot dependency management hoặc plugin tương ứng trong dự án. Không cần tự đặt phiên bản cho từng dependency nếu dự án đã sử dụng Spring Boot dependency management.

Vai trò của từng dependency:

- `spring-boot-starter-data-r2dbc` cung cấp hạ tầng Spring Data R2DBC, bao gồm `DatabaseClient` và khả năng cấu hình repository reactive.
- `r2dbc-postgresql` cung cấp driver triển khai R2DBC SPI cho PostgreSQL.
- `spring-boot-starter-webflux` cho phép xây dựng endpoint trả về `Mono` hoặc `Flux`.
- `reactor-test` cung cấp `StepVerifier` để kiểm thử publisher.

Nếu sử dụng H2, MariaDB, Microsoft SQL Server hoặc database khác, hãy thay driver PostgreSQL bằng driver R2DBC tương ứng. Một JDBC driver không thể thay thế R2DBC driver chỉ bằng cách đổi URL.

## 3. Cấu hình kết nối trong application.yml

Spring Boot có thể tự cấu hình `ConnectionFactory` khi dependency driver và cấu hình R2DBC hợp lệ có mặt trên classpath.

Ví dụ với PostgreSQL:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/customer_db
    username: ${DB_USERNAME:app_user}
    password: ${DB_PASSWORD}
```

Ý nghĩa các thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `spring.r2dbc.url` | URL R2DBC xác định driver, máy chủ, cổng và database |
| `spring.r2dbc.username` | Tên người dùng database |
| `spring.r2dbc.password` | Mật khẩu database |

URL có dạng `r2dbc:postgresql://host:port/database`. Trong ví dụ, ứng dụng kết nối đến PostgreSQL trên máy cục bộ, cổng `5432`, database `customer_db`.

`DB_USERNAME` và `DB_PASSWORD` là biến môi trường. Có thể đặt giá trị phù hợp trong môi trường chạy ứng dụng hoặc trong cấu hình phát triển cục bộ. Không nên commit mật khẩu thật vào Git. Với môi trường triển khai, hãy dùng secret manager hoặc cơ chế quản lý cấu hình bảo mật của nền tảng.

Một số lỗi cấu hình thường gặp:

- Dùng URL JDBC như `jdbc:postgresql://...` thay vì URL R2DBC.
- Chưa thêm driver R2DBC tương ứng vào runtime classpath.
- Sai hostname, cổng, tên database hoặc thông tin xác thực.
- Database chưa khởi động hoặc không cho phép kết nối từ máy chạy ứng dụng.
- Dùng tên biến môi trường không tồn tại khiến giá trị cấu hình rỗng hoặc không như dự kiến.

## 4. Tạo thành phần kiểm tra bằng DatabaseClient

`DatabaseClient` là abstraction của Spring để thực thi SQL theo mô hình reactive. Nó nhận `ConnectionFactory` do Spring cấu hình và quản lý các bước thực thi ở tầng R2DBC SPI.

Tạo một service nhỏ:

```java
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DatabaseConnectionProbe {

    private final DatabaseClient databaseClient;

    public DatabaseConnectionProbe(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<Integer> ping() {
        return databaseClient.sql("SELECT 1 AS probe_value")
                .map((row, metadata) ->
                        row.get("probe_value", Integer.class)
                )
                .one();
    }
}
```

Phương thức `ping()` trả về `Mono<Integer>` vì truy vấn dự kiến trả về một giá trị:

1. `databaseClient.sql(...)` khai báo câu SQL cần thực thi.
2. `map((row, metadata) -> ...)` đọc cột `probe_value` từ hàng kết quả và chuyển thành `Integer`.
3. `one()` yêu cầu kết quả có tối đa một hàng và trả về `Mono`.

Với câu `SELECT 1`, database thông thường trả đúng một hàng chứa số nguyên `1`. Nếu không có hàng, publisher có thể hoàn tất rỗng; nếu kết nối hoặc thực thi SQL thất bại, publisher phát tín hiệu lỗi.

Tên alias `probe_value` làm cho việc đọc cột rõ ràng. Có thể dùng chỉ số cột, ví dụ `row.get(0, Integer.class)`, nhưng đọc theo tên giúp đoạn mã dễ hiểu hơn khi câu SQL được mở rộng.

## 5. Cung cấp endpoint kiểm tra reactive

Để kiểm tra thủ công sau khi ứng dụng khởi động, có thể tạo endpoint nội bộ trả về kết quả truy vấn. Controller trả trực tiếp một publisher cho Spring WebFlux:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/diagnostics")
public class DatabaseProbeController {

    private static final Logger log =
            LoggerFactory.getLogger(DatabaseProbeController.class);

    private final DatabaseConnectionProbe probe;

    public DatabaseProbeController(DatabaseConnectionProbe probe) {
        this.probe = probe;
    }

    @GetMapping("/database")
    public Mono<ResponseEntity<DatabaseProbeResponse>> checkDatabase() {
        return probe.ping()
                .map(value -> ResponseEntity.ok(
                        new DatabaseProbeResponse("UP", value)
                ))
                .onErrorResume(error -> {
                    log.warn("Reactive database connection check failed", error);
                    return Mono.just(
                            ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                                    .body(new DatabaseProbeResponse("DOWN", null))
                    );
                });
    }
}

record DatabaseProbeResponse(String status, Integer value) {}
```

Khi truy vấn thành công, endpoint trả HTTP 200 với nội dung tương tự:

```json
{
  "status": "UP",
  "value": 1
}
```

Khi truy vấn thất bại, endpoint trả HTTP 503 và trạng thái `DOWN`. Chi tiết lỗi được ghi vào log phía máy chủ để điều tra; response không gửi nguyên thông báo exception ra bên ngoài.

Trong ví dụ trên, record được đặt cùng file với controller để minh họa ngắn gọn. Trong dự án thực tế, có thể chuyển response record thành file riêng theo quy ước package và tổ chức mã nguồn của dự án.

Endpoint chẩn đoán có thể tiết lộ trạng thái hạ tầng. Chỉ nên mở nó trong mạng nội bộ hoặc bảo vệ bằng cơ chế xác thực và phân quyền phù hợp. Nếu mục tiêu là health check vận hành, hãy cân nhắc tích hợp Spring Boot Actuator và health endpoint được cấu hình cho môi trường triển khai.

## 6. Chạy ứng dụng và gọi truy vấn kiểm tra

Khởi động PostgreSQL trước, bảo đảm database và người dùng trong cấu hình đã tồn tại, sau đó chạy ứng dụng Spring Boot:

```bash
./gradlew bootRun
```

Khi ứng dụng đã lắng nghe HTTP, gọi endpoint:

```bash
curl -i http://localhost:8080/diagnostics/database
```

Nếu kết nối và câu SQL thành công, kết quả dự kiến là HTTP 200:

```text
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP","value":1}
```

Nếu database không thể truy cập hoặc xác thực thất bại, endpoint trả HTTP 503:

```text
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"status":"DOWN","value":null}
```

Mã HTTP và body giúp người gọi phân biệt trạng thái thành công với thất bại. Khi thất bại, xem log của ứng dụng để tìm nguyên nhân gốc; không nên kết luận chỉ từ chuỗi `DOWN`.

## 7. Kiểm thử truy vấn bằng StepVerifier

Không nhất thiết phải gọi endpoint bằng trình duyệt để kiểm tra. Có thể viết integration test để xác nhận publisher phát đúng giá trị:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class DatabaseConnectionProbeTest {

    @Autowired
    private DatabaseConnectionProbe probe;

    @Test
    void shouldExecuteSimpleReactiveQuery() {
        StepVerifier.create(probe.ping())
                .expectNext(1)
                .verifyComplete();
    }
}
```

`StepVerifier.create(probe.ping())` đăng ký tiêu thụ publisher. `expectNext(1)` xác nhận giá trị được phát ra là `1`, còn `verifyComplete()` xác nhận publisher kết thúc bình thường.

Đây là integration test vì Spring cần tạo context và kết nối đến database đã cấu hình. Khi chạy trong CI, cần cung cấp database test có thể truy cập, chẳng hạn một PostgreSQL service hoặc container dành cho test. Nếu database không sẵn sàng, kiểm thử có thể thất bại trước khi đến bước xác nhận giá trị.

Không nên dùng mock `DatabaseClient` làm bằng chứng rằng driver và database thật có thể kết nối. Mock phù hợp để kiểm thử logic phối hợp ở mức đơn vị; muốn xác minh URL, xác thực, driver, SQL và mapping thì cần integration test với database thật hoặc database test tương thích.

## 8. Hiểu thời điểm truy vấn được thực thi

Một đặc điểm quan trọng của reactive programming là publisher thường mô tả công việc sẽ được thực hiện khi có subscription.

Ví dụ:

```java
Mono<Integer> result = probe.ping();
// Publisher đã được tạo, nhưng chưa có subscriber tiêu thụ.
```

Đoạn mã trên chưa đủ để kết luận kết nối đã được kiểm tra. Publisher cần được subscribe. Trong endpoint WebFlux, framework đăng ký tiêu thụ publisher khi xử lý request và chuyển kết quả thành HTTP response. Trong integration test, `StepVerifier` đăng ký tiêu thụ publisher.

Trong luồng xử lý reactive, nên trả publisher để thành phần gọi quyết định thời điểm tiêu thụ:

```java
public Mono<Integer> ping() {
    return databaseClient.sql("SELECT 1")
            .map((row, metadata) -> row.get(0, Integer.class))
            .one();
}
```

Tránh gọi `block()` trong controller hoặc service reactive:

```java
Integer value = probe.ping().block();
```

`block()` chờ kết quả và chặn thread hiện tại. Điều đó làm mất lợi ích không chặn và có thể gây nghẽn khi đặt trong đường xử lý request WebFlux. Cũng không nên tự gọi `subscribe()` trong service chỉ để khởi động truy vấn rồi bỏ publisher; caller sẽ khó phối hợp thời điểm hoàn tất và xử lý lỗi.

Nếu có một ranh giới imperative được kiểm soát, việc chờ kết quả có thể có lý do riêng, nhưng đó không phải cách triển khai endpoint reactive thông thường.

## 9. Kiểm tra thêm một truy vấn trên bảng nghiệp vụ

`SELECT 1` xác nhận kết nối và khả năng thực thi SQL cơ bản. Sau khi phép thử này thành công, nên kiểm tra riêng quyền truy cập và mapping của một bảng mà ứng dụng thực sự sử dụng.

Ví dụ repository:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findById(Long id);
}
```

Có thể gọi `findById` từ một service hoặc kiểm thử:

```java
StepVerifier.create(customerRepository.findById(100L))
        .expectNextMatches(customer -> customer.getId().equals(100L))
        .verifyComplete();
```

Ví dụ kiểm thử này giả định bảng có một hàng với ID `100`. Nếu dữ liệu test không bảo đảm hàng đó tồn tại, hãy chuẩn bị dữ liệu trước kiểm thử hoặc kiểm tra một truy vấn phù hợp với fixture hiện có.

Nếu `SELECT 1` thành công nhưng truy vấn repository thất bại, kết nối tổng thể có thể vẫn hoạt động. Khi đó cần kiểm tra tên bảng, tên cột, schema, quyền truy cập, SQL được sinh ra, kiểu dữ liệu và mapping entity.

## 10. Đọc lỗi theo từng nhóm nguyên nhân

Khi phép kiểm tra thất bại, nên phân loại theo giai đoạn mà ứng dụng không thể hoàn thành:

| Triệu chứng | Nguyên nhân có thể | Việc nên kiểm tra |
| --- | --- | --- |
| Không tìm được driver hoặc không tạo được ConnectionFactory | Thiếu dependency, URL sai scheme hoặc driver không hỗ trợ URL | Runtime classpath, driver và tiền tố `r2dbc:` |
| Connection refused hoặc timeout | Database chưa chạy, sai host/cổng hoặc mạng chặn kết nối | Trạng thái database, hostname, port, firewall và network |
| Authentication failed | Username/password sai hoặc tài khoản bị giới hạn | Secret, biến môi trường, quyền và chính sách xác thực |
| Database does not exist | Tên database trong URL sai hoặc database chưa được tạo | Tên database và cấu hình môi trường |
| Lỗi cú pháp hoặc không hỗ trợ SQL | SQL không phù hợp dialect hoặc driver | Câu SQL và tài liệu database/driver |
| Không đọc được kiểu kết quả | Kiểu cột và kiểu Java yêu cầu không tương thích | Metadata, kiểu Java và khả năng chuyển đổi của driver |
| Publisher hoàn tất rỗng | Truy vấn không trả hàng hoặc logic ánh xạ không như dự kiến | SQL, dữ liệu và toán tử `one()`/`first()` phù hợp |
| Lấy kết nối từ pool bị timeout | Pool hết kết nối hoặc kết nối không được trả lại | Vòng đời connection, subscription và cấu hình pool |

### Phân biệt lỗi kết nối và lỗi truy vấn

Nếu `ConnectionFactory` không thể tạo kết nối, cần tập trung vào driver, URL, xác thực, mạng và database server.

Nếu kết nối đã được tạo nhưng SQL thất bại, hãy xem lỗi cú pháp, quyền thực thi, kiểu dữ liệu hoặc tính năng SQL mà database hỗ trợ.

Nếu SQL thực thi thành công nhưng ánh xạ lỗi, hãy kiểm tra tên cột, kiểu dữ liệu Java và logic trong callback `map`.

Phân loại theo tầng giúp tránh thay đổi mapping entity khi nguyên nhân thật là sai mật khẩu, hoặc thay đổi cấu hình mạng khi nguyên nhân là SQL không hợp lệ.

## 11. Một số lưu ý khi dùng phép kiểm tra trong ứng dụng thật

- **Không chạy truy vấn quá thường xuyên.** Health check có thể được gọi theo chu kỳ. Chọn khoảng thời gian hợp lý để tránh tạo tải không cần thiết lên database.
- **Giữ câu truy vấn nhỏ và ổn định.** `SELECT 1` không đọc bảng lớn và không phụ thuộc dữ liệu nghiệp vụ.
- **Đặt timeout phù hợp.** Nếu cần giới hạn thời gian health check, cấu hình timeout ở tầng publisher hoặc hạ tầng health check theo chính sách ứng dụng. Timeout quá ngắn có thể tạo cảnh báo giả khi database đang chịu tải.
- **Không trả thông tin nhạy cảm ra HTTP.** Response chỉ nên cho biết trạng thái tổng quát; chi tiết kỹ thuật ở log nội bộ.
- **Bảo vệ endpoint.** Endpoint chẩn đoán nên nằm trong mạng quản trị hoặc được xác thực và phân quyền.
- **Không coi một lần ping thành công là bảo đảm lâu dài.** Kết nối có thể bị gián đoạn ngay sau phép thử; ứng dụng vẫn cần xử lý lỗi ở mọi truy vấn nghiệp vụ.
- **Theo dõi pool nếu có sử dụng.** Một lần ping có thể thành công nhưng pool vẫn có thể cạn kết nối dưới tải cao. Cần theo dõi số kết nối đang dùng, số kết nối chờ và timeout lấy connection.

Nếu dùng Spring Boot Actuator, health endpoint và các health contributor có thể cung cấp cách tích hợp với hệ thống giám sát. Cần cấu hình quyền truy cập và mức độ chi tiết được công khai theo môi trường.

## 12. Quy trình kiểm tra nhanh khi khởi tạo dự án

Có thể thực hiện theo thứ tự sau khi đưa Spring Data R2DBC vào dự án:

1. Thêm starter R2DBC và đúng driver cho database.
2. Cấu hình `spring.r2dbc.url`, username và password bằng giá trị của môi trường chạy.
3. Khởi động database và xác nhận host, cổng, database có thể truy cập.
4. Tạo `DatabaseConnectionProbe` với truy vấn `SELECT 1`.
5. Trả `Mono` từ endpoint WebFlux hoặc tiêu thụ publisher trong integration test bằng `StepVerifier`.
6. Xác nhận kết quả là `1` và publisher hoàn tất bình thường.
7. Tiếp tục kiểm tra một truy vấn trên bảng nghiệp vụ để xác nhận schema, quyền và mapping entity.
8. Khi có lỗi, đọc nguyên nhân gốc và xác định nó thuộc cấu hình, mạng, driver, database, SQL hay mapping.

## Ghi nhớ

Một truy vấn reactive đơn giản như `SELECT 1` là cách nhanh để xác nhận ứng dụng Spring Data R2DBC có thể kết nối đến database và thực thi SQL. Dùng `DatabaseClient` để tạo truy vấn và trả `Mono<Integer>`; để WebFlux hoặc `StepVerifier` subscribe publisher và nhận kết quả. Khi truy vấn thành công, giá trị `1` xác nhận đường kết nối cơ bản đang hoạt động. Sau đó vẫn cần kiểm tra riêng bảng nghiệp vụ, quyền truy cập, mapping và hành vi dưới tải để đánh giá đầy đủ khả năng hoạt động của ứng dụng.
