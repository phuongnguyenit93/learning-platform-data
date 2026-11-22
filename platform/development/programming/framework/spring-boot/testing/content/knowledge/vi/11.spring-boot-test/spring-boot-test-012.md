# Tiêu chí dùng full context thay cho unit test hoặc test slice

Trong Spring Boot, `@SpringBootTest` yêu cầu Spring Boot tạo **ApplicationContext của ứng dụng theo cấu hình và profile được chọn**. Điều này cho phép kiểm thử nhiều bean và cơ chế framework hoạt động cùng nhau, nhưng thường tốn thời gian khởi tạo, đòi hỏi nhiều dependency/hạ tầng và khiến nguyên nhân lỗi khó định vị hơn test hẹp.

**Không phải cứ một tính năng đi qua nhiều lớp thì mọi test của nó phải dùng full context.** Câu hỏi đúng là: *“Muốn kết luận điều gì từ kết quả test xanh, và những thành phần nào bắt buộc phải chạy thật để kết luận đó có giá trị?”* Nếu chỉ kiểm tra quy tắc tính giá, JUnit thuần là đủ. Nếu kiểm tra HTTP binding, `@WebMvcTest` thường phù hợp. Nếu muốn khẳng định controller, service, transaction, repository và cấu hình datasource phối hợp thành công, `@SpringBootTest` với hạ tầng kiểm thử tương ứng có thể là lựa chọn cần thiết.

Bài học này tập trung vào **tiêu chí ra quyết định dùng full context thay cho unit test hoặc test slice**, không xem `@SpringBootTest` là công cụ mặc định cho mọi test trong Spring Boot.

## 1. Hiểu ba mức phạm vi trước khi lựa chọn

### Unit test: test logic Java mà không cần Spring

Unit test tạo đối tượng cần kiểm tra bằng `new`, cung cấp đầu vào/doubles thích hợp và assert output, exception hoặc tương tác có nghĩa. Nó không yêu cầu Spring khởi tạo ApplicationContext.

Ví dụ một quy tắc mã khuyến mãi hợp lệ:

```java
assertTrue(CouponRule.valid("WELCOME"));
assertFalse(CouponRule.valid("bad"));
```

Nếu `CouponRule` là class Java thuần, không có HTTP/DB/config, full context chỉ khiến test chậm và phụ thuộc môi trường mà không cung cấp thêm bằng chứng về chính quy tắc này.

### Test slice: chỉ tải một phần framework liên quan

Test slice của Spring Boot cố gắng tập trung vào một lớp infrastructure:

- `@WebMvcTest`: MVC controllers, binding, validation, HTTP status/JSON, một số web/security infrastructure cần thiết.
- `@DataJpaTest`: JPA mapping, repository, query và database trong phạm vi slice.
- `@JdbcTest`: JDBC/JdbcTemplate cùng phần datasource cần cho kiểm thử JDBC.
- `@JsonTest`: JSON serialization/deserialization.
- `@WebFluxTest`: HTTP layer của ứng dụng Spring WebFlux.
- Những test slice khác: chọn theo công nghệ và phiên bản Spring Boot thực sự sử dụng.

Một slice **không có nghĩa “không dùng Spring”**: nó vẫn tạo ApplicationContext, nhưng tập bean và auto-configuration được thu hẹp. Nếu dependency của controller nằm ngoài web slice, có thể dùng `@MockitoBean` phù hợp để cung cấp mock thay vì tải toàn bộ service/repository.

### Full context: chạy nhiều thành phần và wiring cùng nhau

`@SpringBootTest` tìm hoặc nhận cấu hình Spring Boot của ứng dụng, áp dụng auto-configuration và tạo context theo `classes`, `properties`, active profiles và các điều kiện thực tế của test. Nó thường tải phạm vi rộng hơn slice và cho phép các bean production tương tác thật.

**Nhưng “full” không đồng nghĩa “production y hệt”.** Test có thể dùng profile khác, H2 thay PostgreSQL, mock HTTP client, không có broker, hay chạy với servlet giả thay vì HTTP server thực. Hợp đồng test chỉ được khẳng định trong phạm vi **thành phần và hạ tầng thực sự chạy**.

| Câu hỏi | Unit test | Test slice | `@SpringBootTest` |
| --- | --- | --- | --- |
| Tải Spring ApplicationContext? | Không | Có, phạm vi hẹp | Có, theo cấu hình ứng dụng |
| Chạy logic service thật? | Có, nếu tạo service thật | Chỉ khi đưa service vào slice | Thường có, trừ khi mock/thay bean |
| Kiểm tra một quy tắc thuần? | **Rất phù hợp** | Thường quá rộng | Thường quá rộng |
| Kiểm tra HTTP binding/status? | Không, nếu gọi method trực tiếp | **Rất phù hợp với MVC/WebFlux slice** | Có thể, nếu test đi qua HTTP infrastructure thích hợp |
| Kiểm tra JPA SQL/mapping? | Không với mock repository | **Phù hợp với repository slice** | Có thể nếu DB/repository chạy thật |
| Kiểm tra liên kết controller–service–repository? | Không tự động | Thường nằm ngoài slice | **Phù hợp nếu các bean chạy thật** |
| Kiểm tra auto-config/profiles/qualifier/bean wiring? | Không | Chỉ phần slice | **Phù hợp khi cần cấu hình thực tế** |
| Thời gian và chi phí khởi tạo? | Thường thấp nhất | Trung bình | Thường cao hơn |
| Khi test fail, dễ khoanh vùng? | Cao | Khá cao | Cần phân tích nhiều lớp hơn |

## 2. Tiêu chí dùng full context: “bằng chứng nào cần thiết?”

Một test nên được nâng từ unit/slice sang full context khi **có ít nhất một rủi ro không thể kiểm chứng đáng tin ở ranh giới hẹp**, và rủi ro đó đủ quan trọng để chấp nhận chi phí tăng.

### Tiêu chí 1 — Phải chứng minh wiring giữa nhiều lớp

Ví dụ: “`POST /coupons` đi qua controller, gọi service, thực hiện JDBC insert và trả response thể hiện dữ liệu đã ghi”. Test controller mock service có thể chứng minh routing/JSON; test service mock repository có thể chứng minh lệnh insert được yêu cầu; nhưng **cả hai chưa chứng minh các bean thật được nối đúng nhau trong cấu hình ứng dụng**.

Full-context test phù hợp nếu muốn bảo vệ đường đi tích hợp đó, bao gồm bean scanning, constructor injection, transaction manager và datasource.

### Tiêu chí 2 — Hành vi phụ thuộc vào Spring proxy/interceptor

Ví dụ `@Transactional`, `@Cacheable`, `@PreAuthorize` và các advisor/proxy khác. Nếu test dùng `new Service(...)`, annotation không tự khởi tạo transaction, cache hay method-security interceptor. Nếu một slice không tải proxy infrastructure tương ứng, test slice cũng chưa đủ bằng chứng.

Dùng context có bean thật và advice thật. **Không nhất thiết phải là toàn bộ `@SpringBootTest`**: với một proxy được cấu hình tối thiểu, `@SpringJUnitConfig` có thể đủ. Chọn full context khi còn cần chứng minh **cấu hình production và nhiều advisor/manager cùng hoạt động**.

### Tiêu chí 3 — Auto-configuration và điều kiện bean là phần hợp đồng

Ví dụ một `DataSource`/`TransactionManager` chỉ tạo dưới một profile, bean tồn tại khi có một property, hay một implementation được chọn thông qua `@Primary`/`@Qualifier`. Unit test không đọc cấu hình Spring; slice test có thể chủ ý bỏ qua những bean ấy.

Full-context test có giá trị khi muốn phát hiện bean biến mất, cấu hình profile sai, conditional auto-configuration không được kích hoạt hoặc chọn nhầm implementation. Nhưng hãy cẩn thận: **test tự khai báo một mock để thay bean thiếu có thể che chính lỗi wiring**. Khi cần chứng minh bean phải tồn tại, dùng chiến lược override nghiêm ngặt hoặc assertion cấu hình phù hợp, không tạo mock mới một cách vô thức.

### Tiêu chí 4 — Dữ liệu/thao tác phải đi qua nhiều adapter thật

Ví dụ “request tạo đơn, transaction commit và bản ghi được truy vấn lại”; “outbox event ghi DB và được relay qua broker”; “HTTP client serialization kết hợp timeout/retry của adapter”.

Nếu rủi ro nằm ở định dạng SQL, migration, transaction hoặc protocol, **mock các adapter ấy sẽ không cho bằng chứng tương đương**. Full context với DB/broker/HTTP test server thích hợp giúp kiểm chứng luồng. Tuy nhiên, khi chỉ cần kiểm tra riêng một repository query hoặc HTTP client adapter, **test slice/adapter** vẫn có thể hẹp và hiệu quả hơn.

### Tiêu chí 5 — Lỗi chỉ lộ khi các thành phần tương tác

Một lỗi có thể đến từ sự phối hợp: controller truyền nhầm field vào service; service chọn transaction manager sai; Bean Validation được đặt ở tầng không chạy; security filter cấu hình khác method security; Jackson đổi format làm client không parse được.

Full-context test là **lưới an toàn cho vài hành trình quan trọng**, không phải lý do viết mọi edge case tại tầng full. Một test happy path và một số failure path có rủi ro cao có thể bổ sung các unit/slice tests bao phủ nhiều biến thể.

### Tiêu chí 6 — Cần chạy cùng cấu hình tương tự môi trường triển khai

Nếu yêu cầu là “với profile `test`/`staging`, bean A kết nối DB B, migrate schema và xử lý request”, hãy dùng context với config/profiles gần mục tiêu. Cấu hình khác nhau có thể dẫn đến kết luận khác nhau.

**Không nên nói một test H2 là bằng chứng PostgreSQL-specific constraints/dialect/locking đều đúng.** Khi hệ thống phụ thuộc PostgreSQL, SQL đặc thù, Redis TTL, Kafka consumer offset hoặc network security, chạy hạ tầng tương ứng (ví dụ Testcontainers cho DB/broker khi thích hợp) nếu đó chính là điều cần chứng minh.

## 3. Cây quyết định thực hành

```text
Bắt đầu từ hành vi/bug cần bảo vệ
              |
              v
Có cần Spring xử lý để hành vi xảy ra đúng không?
       /                         \
     Không                       Có
      |                           |
   JUnit thuần                    v
                           Chỉ một layer?
                            /         \
                          Có           Không
                          |              |
                  Web/JPA/JDBC/JSON       v
                     test slice      Nhiều bean,
                          |           proxy/config
                          |              |
                          v              v
                  Test slice đủ?     Dùng context
                     /    \         phù hợp, cân nhắc
                   Có      Không    @SpringBootTest
                   |         |
                Dừng       Nâng phạm vi
              tại slice    theo rủi ro
```

Một cách hỏi nhanh trước khi thêm `@SpringBootTest`:

1. **Nếu không khởi động Spring, điều gì sẽ không được thực thi?** Nếu không trả lời được, hãy thử unit test trước.
2. **Nếu chỉ dùng test slice, bằng chứng nào sẽ còn thiếu?** Nếu không có, giữ slice.
3. **Trong full-context test, adapter nào vẫn bị mock/fake?** Lời khẳng định về adapter mock phải bị giới hạn tương ứng.
4. **Nếu test fail, có thể chỉ ra khu vực nào làm sai không?** Bổ sung unit/slice tests để khoanh vùng lỗi.
5. **Có cần test bằng server/DB/broker thật hay chỉ một ApplicationContext?** Chọn `webEnvironment` và fixture/hạ tầng theo đúng mục tiêu.

Nếu mục tiêu chỉ là “context có thể khởi động”, một smoke test full context có giá trị. Nếu mục tiêu là transaction commit hay HTTP serialization, **assert chỉ việc context start là chưa đủ**.

## 4. Các chế độ webEnvironment của @SpringBootTest

`@SpringBootTest` không mặc định mở một cổng HTTP thật. Những giá trị thường dùng của `SpringBootTest.WebEnvironment`:

| Giá trị | Hành vi chính | Phù hợp khi |
| --- | --- | --- |
| `MOCK` (mặc định) | Tạo web application context khi ứng dụng là web app, **không khởi động embedded server thực** | Test integration sử dụng `MockMvc` hoặc không cần socket |
| `RANDOM_PORT` | Khởi động web server trên cổng ngẫu nhiên | Test HTTP qua network stack thật, cookies/redirect/servlet container behavior |
| `DEFINED_PORT` | Khởi động server trên cổng cấu hình | Bắt buộc dùng cổng cụ thể, thường ít phù hợp CI song song |
| `NONE` | Không tạo web environment | Cần full application beans nhưng không cần web infrastructure |

### MOCK không tự cấp MockMvc trong mọi cấu hình

Với Spring Boot MVC test phổ biến, `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` giúp inject `MockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CouponFullContextTest {
    @Autowired MockMvc mvc;
}
```

Đây là đoạn class structure, không phải file test độc lập. Annotation `@AutoConfigureMockMvc` thuộc Spring Boot test auto-configuration; vị trí package/dependency có thể khác giữa các thế hệ Boot. Các ví dụ chạy ở mục 6 lấy **Spring Boot 3.4/3.5** làm mốc cú pháp import. MockMvc chạy MVC request/response bằng servlet test infrastructure, **không sử dụng cổng socket thực**.

### RANDOM_PORT là một bằng chứng rộng hơn ở lớp HTTP

`@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` khởi động server thật với cổng động. Client test có thể gọi HTTP tới cổng ấy bằng một HTTP client phù hợp phiên bản Boot; nếu cần thử TLS, proxy, wire behavior, cấu hình thêm theo yêu cầu.

**Bẫy transaction:** khi HTTP client của test và request handler của server chạy ở **hai thread**, transaction do `@Transactional` trên method test điều khiển không tự bao trùm transaction phía server. Nếu server ghi DB và commit, việc rollback test transaction không xóa dữ liệu ấy. Chuẩn bị và cleanup phải phản ánh đường đi thật. Chỉ dùng `@Transactional` trên test để “dọn DB tự động” cho một test RANDOM_PORT có thể gây dữ liệu rò rỉ giữa các case.

## 5. So sánh bằng một tính năng: lưu mã coupon

Ta xét hành vi “người dùng gửi mã coupon hợp lệ; ứng dụng lưu mã vào database và trả HTTP 201 cùng số bản ghi hiện có”.

- **Unit test** chứng minh quy tắc mã hợp lệ.
- **Web slice** chứng minh request mapping và JSON response khi service được mock.
- **Full context** chứng minh controller, service thật, `JdbcTemplate`, transaction manager, schema và H2 cùng hoạt động.

Khi lựa chọn mức test, hãy nêu rõ phần nào là mock trong từng ví dụ.

**Các quy tắc của ví dụ:**

1. Coupon code chỉ gồm chữ in hoa ASCII `A–Z`, từ 4 đến 12 ký tự.
2. Mã không hợp lệ bị từ chối bằng `IllegalArgumentException` trước khi insert.
3. Mã hợp lệ được lưu vào bảng `coupons`, cột `code` có ràng buộc unique.
4. Controller trả HTTP 201 với JSON có `code` và `total` nếu lưu thành công.
5. Nếu input sai, controller map sang HTTP 400 có trường `error`.

**Phạm vi công nghệ để chạy ví dụ:** Java 17+, Spring Boot **3.4/3.5**, Spring MVC, Spring JDBC, H2, JUnit Jupiter và Mockito trong test. Với Spring Boot 4+, kiểm tra artifact/package cụ thể của các module test trước khi copy imports; tư duy lựa chọn full context vẫn tương tự.

Cấu trúc project:

```text
src/
├── main/java/example/fullcontext/
│   ├── CouponApplication.java
│   ├── CouponRule.java
│   ├── CouponRuleDemo.java
│   ├── CouponService.java
│   └── CouponController.java
├── main/resources/schema.sql
└── test/java/example/fullcontext/
    ├── CouponRuleTest.java
    ├── CouponControllerSliceTest.java
    └── CouponFullContextTest.java
```

### 5.1. Cấu hình Gradle cần thiết

Trong project Spring Boot 3.4/3.5 đã cấu hình `org.springframework.boot` Gradle plugin, Java toolchain và dependency management tương thích, phần liên quan ở `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đoạn này **không phải toàn bộ build.gradle độc lập**, vì plugin, repositories và các phiên bản đã được project Spring Boot quản lý. Với Boot 3.4/3.5, test starter thông dụng cung cấp JUnit Jupiter, Mockito và Spring Boot test infrastructure. `@MockitoBean` thuộc Spring Framework TestContext 6.2+ nằm trong test dependency phù hợp.

H2 được dùng **chỉ để minh họa kết nối controller–service–database**, không phải để chứng minh đặc tính SQL của PostgreSQL/MySQL production.

### 5.2. Ứng dụng Spring Boot

Tạo `src/main/java/example/fullcontext/CouponApplication.java`:

```java
package example.fullcontext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CouponApplication {
    public static void main(String[] args) {
        SpringApplication.run(CouponApplication.class, args);
    }
}
```

Đặt application class ở package gốc `example.fullcontext` để mặc định Spring component scanning phát hiện controller và service ở cùng package.

### 5.3. Quy tắc thuần Java: CouponRule

Tạo `src/main/java/example/fullcontext/CouponRule.java`:

```java
package example.fullcontext;

public final class CouponRule {
    private CouponRule() {
    }

    public static boolean valid(String code) {
        return code != null && code.matches("[A-Z]{4,12}");
    }
}
```

Class này không cần Spring. `matches("[A-Z]{4,12}")` bắt đầu/kết thúc theo toàn bộ chuỗi, nên `"WELCOME"` hợp lệ, `"bad"` sai do chữ thường, `"ABC"` sai do độ dài.

### 5.4. Service chạy JDBC và transaction

Tạo `src/main/java/example/fullcontext/CouponService.java`:

```java
package example.fullcontext;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CouponService {
    private final JdbcTemplate jdbc;

    public CouponService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public int register(String code) {
        if (!CouponRule.valid(code)) {
            throw new IllegalArgumentException("invalid code");
        }

        jdbc.update(
                "INSERT INTO coupons(code) VALUES (?)",
                code);

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM coupons",
                Integer.class);
        return count;
    }
}
```

Ý nghĩa:

- Spring tạo `CouponService` bean nhờ `@Service` và inject `JdbcTemplate` từ JDBC auto-configuration.
- `@Transactional` áp dụng khi method được gọi qua bean proxy được Spring quản lý; unit test bằng `new` không chứng minh transaction interception.
- Validation chạy trước insert; dữ liệu không hợp lệ không chạm DB.
- Sau khi insert, service query count để trả kết quả.
- Unique constraint trên `code` trong schema sẽ ngăn tạo hai coupon trùng; test riêng có thể kiểm tra lỗi constraint nếu nghiệp vụ yêu cầu.

### 5.5. Controller và JSON response

Tạo `src/main/java/example/fullcontext/CouponController.java`:

```java
package example.fullcontext;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/coupons")
public class CouponController {
    private final CouponService service;

    public CouponController(CouponService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CouponReceipt> create(
            @RequestParam String code) {
        int total = service.register(code);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new CouponReceipt(code, total));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalidCode(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", ex.getMessage()));
    }

    public record CouponReceipt(String code, int total) {
    }
}
```

Controller không biết SQL; nó dùng service. `@ExceptionHandler` ở đây chỉ ánh xạ `IllegalArgumentException` từ controller/service trong scope xử lý của MVC sang HTTP 400. Đây là hợp đồng của ví dụ, không có nghĩa mọi ứng dụng phải dùng cùng kiểu exception mapping.

### 5.6. Schema cho datasource H2

Tạo `src/main/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS coupons (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(32) NOT NULL UNIQUE
);
```

Trong project Spring Boot với datasource H2 nhúng và SQL initialization thông dụng, `schema.sql` được chạy khi khởi tạo datasource. Nếu dự án đã dùng Flyway/Liquibase, có thể phải điều chỉnh initialization/migration cho test; **không nên chạy hai hệ migration chồng lên nhau mà không có kế hoạch**.

## 6. Ba test cùng tính năng, ba lời khẳng định khác nhau

### 6.1. Unit test: quy tắc coupon

Tạo `src/test/java/example/fullcontext/CouponRuleTest.java`:

```java
package example.fullcontext;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CouponRuleTest {
    @ParameterizedTest
    @ValueSource(strings = {"WELCOME", "SAVE", "ABCDEFGHIJKL"})
    void acceptsUppercaseCodesWithinLength(String code) {
        assertTrue(CouponRule.valid(code));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {"bad", "ABC", "ABC123", "ABCDEFGHIJKLM"})
    void rejectsInvalidCodes(String code) {
        assertFalse(CouponRule.valid(code));
    }
}
```

Đây là **9 lượt thực thi** (3 hợp lệ + 2 null/empty + 4 chuỗi sai = 9 lượt). Để tránh nhầm đếm: nhóm hợp lệ có **3**, nhóm không hợp lệ có **6** nên tổng chính xác là **9 invocations**, trải trên **2 parameterized test methods**. Không có Spring context, database hay MockMvc. Test này bảo vệ rule với ranh giới rất hẹp, không cần `@SpringBootTest`.

Nhận xét về kỹ thuật: case 12 chữ cái `ABCDEFGHIJKL` là ranh giới hợp lệ, 13 chữ cái `ABCDEFGHIJKLM` không hợp lệ. Dữ liệu biên có giá trị hơn việc chỉ thử các chuỗi bất kỳ.

### 6.2. MVC slice: hợp đồng HTTP khi service được mock

Tạo `src/test/java/example/fullcontext/CouponControllerSliceTest.java`:

```java
package example.fullcontext;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CouponController.class)
class CouponControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CouponService service;

    @Test
    void returnsCreatedResponseFromServiceResult() throws Exception {
        when(service.register("WELCOME")).thenReturn(1);

        mvc.perform(post("/coupons")
                        .param("code", "WELCOME"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code").value("WELCOME"))
                .andExpect(jsonPath("$.total").value(1));

        verify(service).register("WELCOME");
    }
}
```

Test này có Spring MVC context **nhưng không tải service thật hoặc database**. `@MockitoBean` tạo/thay bean service để controller có dependency. Nếu test xanh, có thể kết luận routing `POST /coupons`, request parameter và response JSON **ở web slice** phù hợp với dữ liệu mock.

**Không được kết luận** JDBC insert thành công hay transaction hoạt động: service là mock, `register` không chạy logic thật. Nếu ứng dụng có Spring Security trên classpath, MVC test có thể chạy security filters; cần cấu hình authentication/test filter theo hợp đồng thay vì tắt bảo mật chỉ để test xanh. Ví dụ tối thiểu này **không khai báo Security starter**.

### 6.3. Full context: controller → service thật → JDBC → DB

Tạo `src/test/java/example/fullcontext/CouponFullContextTest.java`:

```java
package example.fullcontext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CouponFullContextTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void clearRows() {
        jdbc.update("DELETE FROM coupons");
    }

    @Test
    void postRequestPersistsCouponAndReturnsResponse()
            throws Exception {

        mvc.perform(post("/coupons")
                        .param("code", "WELCOME"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code").value("WELCOME"))
                .andExpect(jsonPath("$.total").value(1));

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM coupons",
                Integer.class);
        assertEquals(1, count);
    }

    @Test
    void invalidCodeReturnsBadRequestWithoutInsert()
            throws Exception {

        mvc.perform(post("/coupons")
                        .param("code", "bad"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("invalid code"));

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM coupons",
                Integer.class);
        assertEquals(0, count);
    }
}
```

**Đây là điểm full context có giá trị bổ sung:**

1. Spring Boot tìm `CouponApplication` và tải controller, service, datasource, JDBC, transaction manager cùng auto-configuration phù hợp.
2. `MockMvc` mô phỏng HTTP request đi qua MVC infrastructure; **không dùng network port thật**.
3. Spring inject **service thật** vào controller; `CouponService.register` thực hiện validation, JDBC insert và query.
4. H2 chạy SQL schema. Assertion đếm dữ liệu thực, chứ không chỉ `verify(mockRepository).save(...)`.
5. Case input sai được chuyển thành HTTP 400 và **không có dòng mới** trong DB.

Bộ test intentionally **không mock CouponService hoặc JdbcTemplate**, vì mục tiêu là chứng minh đường đi tích hợp. `@BeforeEach` xóa dữ liệu để các case độc lập trong chế độ chạy test thông thường. Nếu bật chạy test song song trên cùng H2 datasource, cần isolate database/schema/test fixtures sâu hơn; `DELETE` trước test không bảo vệ được khỏi race giữa nhiều method.

**Giới hạn:** test này chứng minh Spring MVC → service → Spring JDBC → H2 trong ApplicationContext. Nó **chưa** chứng minh request qua TCP/embedded server, behavior PostgreSQL hoặc email/payment/broker bên ngoài.

### 6.4. Chạy từng mức bằng Gradle

Từ thư mục gốc project đã có Gradle wrapper:

```bash
./gradlew test --tests example.fullcontext.CouponRuleTest
./gradlew test --tests example.fullcontext.CouponControllerSliceTest
./gradlew test --tests example.fullcontext.CouponFullContextTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.fullcontext.CouponRuleTest"
.\gradlew.bat test --tests "example.fullcontext.CouponControllerSliceTest"
.\gradlew.bat test --tests "example.fullcontext.CouponFullContextTest"
```

**Kỳ vọng khi cấu hình đúng:** unit có 9 invocations, MVC slice có 1 test method, full context có 2 test methods; tất cả pass. Báo cáo và stdout Gradle thay đổi theo phiên bản/cấu hình runner, nên không gán một chuỗi stdout cố định cho lệnh test. Có thể dùng test reports để xem tên và thời gian mỗi nhóm.

### 6.5. Chạy riêng Java thuần bằng javac/java

Để kiểm chứng quy tắc mà **không cần Gradle/Spring/JUnit**, tạo `src/main/java/example/fullcontext/CouponRuleDemo.java`:

```java
package example.fullcontext;

public class CouponRuleDemo {
    public static void main(String[] args) {
        System.out.println(CouponRule.valid("WELCOME"));
        System.out.println(CouponRule.valid("bad"));
        System.out.println(CouponRule.valid("ABC"));
    }
}
```

Chạy trong thư mục project có JDK 17+:

```bash
javac -d out src/main/java/example/fullcontext/CouponRule.java src/main/java/example/fullcontext/CouponRuleDemo.java
java -cp out example.fullcontext.CouponRuleDemo
```

**Stdout chính xác:**

```text
true
false
false
```

Đây chỉ là demo Java thuần. Nó **không kiểm chứng** Spring context, controller, database hoặc annotation transaction; những điều ấy cần chạy JUnit/Spring test ở phần trên.

## 7. Vì sao không dùng full context để thay mọi unit/slice test?

Một test full context có thể đi qua nhiều lớp, nhưng **một lỗi có thể xuất phát từ rất nhiều nơi**: bean không tìm thấy, datasource không boot, schema thiếu, security filter ngăn request, serialization sai, transaction chưa commit hoặc business rule sai.

Nếu mọi trường hợp biên đều chạy qua `@SpringBootTest`:

- Chi phí bootstrap và DB fixture tăng; vòng sửa code ngắn bị chậm.
- Lỗi môi trường có thể khiến rất nhiều test đỏ cùng lúc dù logic nghiệp vụ đúng.
- Tên test không còn chỉ rõ lớp lỗi, làm debugging tốn thời gian.
- Các test dễ phụ thuộc dữ liệu và context chung, nhất là khi chạy song song.
- Mock đặt quá nhiều trong full context có thể khiến test vẫn không kiểm tra tích hợp thực sự.

**Một cách phân bổ hợp lý:**

- Unit test dày cho rule, state transitions, exception và phép tính.
- Slice tests đủ chi tiết cho HTTP binding, validation, JSON, JPA queries hoặc JDBC adapter.
- Full-context tests chọn lọc cho một số **critical paths**: boot/wiring, happy path xuyên nhiều lớp, rollback/authorization/caching ở ranh giới thực và lỗi tương tác đã từng xảy ra.

Không có quy tắc cứng rằng phải có 70% unit, 20% slice, 10% full. Lựa chọn dựa vào rủi ro, chi phí test và mức bằng chứng cần bảo vệ. **Càng rộng không tự động càng tốt** nếu test không quan sát đúng hành vi cần thiết.

## 8. Chọn full context hay focused Spring TestContext?

Ngoài unit và các slice của Boot, còn một lựa chọn trung gian: dùng `@SpringJUnitConfig` để tạo **một Spring context tối thiểu có chủ đích**.

Ví dụ cần kiểm tra `@Cacheable` trên một service và một `CacheManager`: có thể tạo config chỉ với service, cache manager và `@EnableCaching`. Test đó vẫn đi qua Spring AOP proxy mà **không cần** toàn bộ application autoconfiguration, DB và web server.

Tương tự, với method security `@PreAuthorize` có thể dùng context nhỏ với `@EnableMethodSecurity` và SecurityContext kiểm thử. Khi mục tiêu là kiểm tra Spring transaction proxy, cần transaction manager/datasource phù hợp; không nhất thiết phải khởi động toàn bộ REST API.

**Dùng full `@SpringBootTest` khi điều cần chứng minh là chính cấu hình/wiring của ứng dụng rộng hơn**: nhiều bean, điều kiện auto-configuration, security chain, nhiều transaction managers, cache manager production hoặc tương tác nhiều adapter. Context tối thiểu đủ cho **framework behavior**, nhưng chưa chắc đủ cho **production wiring behavior**.

## 9. Những bẫy của full-context tests

### 9.1. @Transactional trên test có thể che kết quả commit

Spring Test hỗ trợ `@Transactional` trên test method để tự rollback sau khi test kết thúc. Tính năng này hữu ích để cô lập dữ liệu, nhưng nếu mục tiêu là **xác nhận service commit** thì assertion đọc DB trong cùng transaction test có thể thấy dữ liệu chưa commit.

Với một test commit/rollback của service, hãy đảm bảo transaction boundary đúng: gọi bean proxy từ ngoài test-managed transaction và kiểm tra dữ liệu **sau khi service hoàn tất**. Với test `RANDOM_PORT`, transaction của test thread lại không kiểm soát server thread. Không tuyên bố commit/rollback đúng chỉ vì một test được tự rollback khi kết thúc.

### 9.2. Một số dependency còn bị mock

`@SpringBootTest` vẫn có thể sử dụng `@MockitoBean` để thay client bên ngoài, nhưng **không được nói rằng adapter mock đã được kiểm tra thật**. Nếu mock HTTP client, test có thể bảo vệ orchestration của service và wiring các bean khác, nhưng serialization/timeout của client chưa được chứng minh.

Nếu mock chính service có `@Transactional`/`@Cacheable`/method security, test có thể đánh mất đường đi qua advice của target. Hãy giữ target thật khi muốn chứng minh proxy.

### 9.3. Profile test không giống production

Test chạy với `@ActiveProfiles("test")` hoặc property override có thể chọn bean/datasource khác production. Điều này hữu ích để tránh hệ thống ngoài, nhưng phải giới hạn kết luận. Một test context `test` không đảm bảo profile `prod` có cùng bean nếu có `@Profile`, `@ConditionalOnProperty` hoặc cấu hình theo environment.

Nếu rủi ro nằm ở cấu hình production, cần một smoke/integration test nạp config đủ sát mục tiêu. Không vô tình tự thêm test bean để bù một bean production bị thiếu rồi kết luận mọi thứ đúng.

### 9.4. H2 và database production có thể hành xử khác

H2 hữu ích để test luồng SQL phổ biến, nhưng không chứng minh SQL dialect, kiểu JSON/array, index, transaction isolation, locking hoặc migration riêng của PostgreSQL/MySQL. Khi bug thực tế phụ thuộc DB engine, dùng **Testcontainers** hoặc môi trường DB tương ứng với production và dọn dữ liệu test rõ ràng.

### 9.5. Shared ApplicationContext, DB và cache

Spring TestContext có thể cache và tái sử dụng ApplicationContext giữa những test có cấu hình tương đương. Đó là tối ưu hợp lý, nhưng **không tự reset** singleton mutable state, DB, cache, broker hoặc file.

- Tạo test data độc lập và có cleanup.
- Tránh phụ thuộc thứ tự chạy test.
- Nếu chạy song song, cách ly transaction, schema, database/container hoặc key namespace theo nhu cầu.
- Chỉ dùng `@DirtiesContext` khi thật sự cần phá context; nó làm thời gian chạy tăng đáng kể.
- Không lạm dụng một `@BeforeEach` gọi HTTP/DB dài cho từng test nếu fixture có thể chuẩn bị hiệu quả hơn mà vẫn độc lập.

### 9.6. Context startup test chưa chắc kiểm tra mọi route

Một bài `@SpringBootTest` chỉ có method `contextLoads()` hữu ích như **smoke test wiring**, nhưng nó không tự gửi request, không gọi method proxy và không chứng minh DB commit. Muốn kiểm chứng luồng nghiệp vụ, phải thực thi luồng đó và assert kết quả quan sát được.

### 9.7. Security filter và method security

Trong một ứng dụng có Spring Security, `MockMvc` có thể chạy security filter chain khiến request bị 401/403/CSRF. Điều đó có thể là một phần **đúng** của hợp đồng. Khi test HTTP security, cung cấp authentication/token phù hợp; không dùng `addFilters=false` hoặc tắt security chỉ để cho assertion status khác pass rồi tuyên bố đã kiểm tra security.

Method security `@PreAuthorize` là một lớp khác; test trực tiếp service qua proxy có thể chứng minh rule method nhưng không chứng minh HTTP filter/JWT decoder. Chọn ranh giới mà user đang phụ thuộc.

## 10. Chi phí thực tế của full context: ra quyết định bằng tín hiệu

Chi phí không chỉ là vài giây bootstrap:

| Chi phí hoặc rủi ro | Dấu hiệu | Biện pháp |
| --- | --- | --- |
| Khởi tạo nhiều auto-configuration/bean | Test đầu chậm, log nhiều bean | Ưu tiên unit/slice cho case hẹp |
| DB/container/migration startup | CI chậm, test flaky vì resource | Dùng container/fixture chung có kiểm soát, chọn ít critical paths |
| Dữ liệu dùng chung | Test pass đơn lẻ nhưng fail khi chạy cả suite | Dọn/isolated data, không phụ thuộc thứ tự |
| Lỗi nhiều lớp | Failure stacktrace dài, khó biết SQL hay MVC | Giữ test unit/slice để định vị |
| Mock che mất wiring | Full context xanh dù production thiếu adapter | Kiểm tra override strategy và config thật |
| Test chạy song song | Race ở bảng DB hoặc cache key | Isolate state theo test, điều chỉnh parallelization |
| Khác môi trường production | H2 pass, PostgreSQL fail | Dùng đúng engine khi rủi ro yêu cầu |
| Test suite quá rộng | Mọi edge case chạy @SpringBootTest | Chuyển case logic sang unit, contract đơn lớp sang slice |

Chỉ dùng một số **full-context tests có câu hỏi rõ** thường cho tỷ lệ bằng chứng/chi phí tốt hơn việc biến toàn bộ suite thành một loạt integration tests. Nếu pipeline cần xác nhận deployment hoặc network thật, xây các test riêng với môi trường/hạ tầng được cấu hình tương ứng.

## 11. Các lỗi phổ biến khi chọn mức test

**1. Cho rằng @SpringBootTest luôn bắt đầu HTTP server.** Mặc định `MOCK` không mở cổng thực. Muốn gọi qua socket hãy dùng `RANDOM_PORT` hoặc cấu hình tương ứng.

**2. Dùng @SpringBootTest cho một phép if hoặc regex.** Unit test thuần đủ chứng minh quy tắc và chạy nhanh hơn.

**3. Dùng @WebMvcTest rồi kết luận database đã lưu.** Nếu service là mock, test chỉ chứng minh web contract với output đã stub.

**4. Dùng mock repository rồi kết luận transaction rollback.** Verification lời gọi không có nghĩa DB transaction đã xảy ra. Kiểm tra dữ liệu bằng integration test thích hợp.

**5. Dùng full context nhưng mock hết target liên quan.** Test có thể “đầy context” mà không đi qua behavior thực sự muốn bảo vệ.

**6. Bỏ qua profile/conditional beans.** Test xanh chỉ xác nhận context của config/profiles đang nạp, không đại diện mọi môi trường.

**7. Dùng H2 để chứng minh SQL production-specific.** Đổi sang DB engine phù hợp khi hợp đồng cần kiểu dữ liệu/transaction behavior đặc thù.

**8. Quên kiểm tra side effect.** HTTP 201 không tự chứng minh DB commit. Kết hợp assertion sau request qua repository/JDBC hoặc client quan sát hạ tầng thật.

**9. Đặt @Transactional trên test rồi kết luận service commit.** Đọc dữ liệu trong cùng test transaction không phải bằng chứng commit sau service call.

**10. Test RANDOM_PORT nhưng trông chờ rollback của test thread.** Request chạy ở server thread; cần cleanup dữ liệu được server ghi.

**11. Tắt security filter để ép status code.** Nếu security là phần hợp đồng, phải test với filter/role/token đúng.

**12. Chỉ có một test contextLoads() cho tính năng phức tạp.** Nó phát hiện lỗi khởi tạo bean, nhưng không kiểm tra route, transaction hay nghiệp vụ nếu không gọi chúng.

**13. Dùng @DirtiesContext ở mọi nơi để xử lý dữ liệu bẩn.** Việc rebuild context liên tục tốn chi phí và không thay thế cleanup đúng.

**14. Đưa cả những ca boundary vào full context.** Logic regex/validation nhiều nhánh nên được kiểm tra ở test hẹp, chỉ chọn ít case đại diện cho đường tích hợp.

## 12. Checklist chọn @SpringBootTest

Trước khi viết:

- Hợp đồng cần chứng minh là **quy tắc thuần, một infrastructure layer hay liên kết nhiều layer**?
- Tôi có thể mô tả **lỗ hổng bằng chứng** của unit/slice test không?
- Bean nào bắt buộc phải chạy thật? Có bean nào đang bị mock khiến bài test chưa chứng minh điều mình muốn?
- Cần framework proxy, auto-configuration, profile, transaction manager hay security chain thật không?
- Với DB/broker/HTTP, đang dùng implementation nào; nó có đủ giống production cho rủi ro đang kiểm tra không?
- `@SpringBootTest` nên dùng `MOCK`, `RANDOM_PORT` hay `NONE`?
- Test có cần thêm `@AutoConfigureMockMvc` hoặc công cụ HTTP client phù hợp không?
- Fixture và test data có độc lập/cleanup được khi context cache hoặc suite chạy song song không?

Sau khi chạy:

- Test có assert **output + side effect** đúng boundary, không chỉ việc khởi tạo context?
- Lỗi có được khoanh vùng bởi unit/slice tests tương ứng không?
- Test có thật sự đi qua bean/proxy/config production cần chứng minh không?
- Những kết luận nào vẫn chưa được chứng minh do dùng H2/mock/test profile/MockMvc không có socket?
- Full-context test có thể thay bằng slice nhỏ hơn mà vẫn giữ đầy đủ bằng chứng không?
- Nếu test chậm/flaky, tôi nên **thu hẹp ranh giới**, cải thiện fixture hay tách rủi ro thành test riêng?

**Kết luận:** `@SpringBootTest` phù hợp khi **bằng chứng yêu cầu nhiều bean và hạ tầng Spring Boot phải phối hợp thật**, đặc biệt wiring/auto-configuration, proxy transaction/security/cache và các hành trình liên lớp quan trọng. Unit test vẫn nên bảo vệ logic chi tiết, còn test slice nên bảo vệ hợp đồng của từng lớp. Chọn **mức hẹp nhất đủ chứng minh yêu cầu**, sau đó thêm một số full-context tests có chủ đích để bảo vệ những rủi ro tích hợp mà test hẹp không nhìn thấy.