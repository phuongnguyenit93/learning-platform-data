# Khởi động server thật với RANDOM_PORT trong Spring Boot Test

## 1. Tại sao phải chạy một server HTTP thật?

Kiểm thử Java method hoặc unit test service xác nhận logic bên trong, nhưng không nhất thiết chứng minh được một request HTTP đi qua **socket**, được embedded server nhận, đến đúng controller, chuyển đổi query/body thành Java object và trả đúng status, headers hoặc JSON. **MockMvc** kiểm tra Spring MVC bằng mock servlet request, thường nhanh hơn nhưng không mở cổng mạng. Khi cần kiểm chứng một endpoint nhận HTTP qua network stack thật, hãy sử dụng:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpIntegrationTest {
    // Test dùng HTTP client gọi embedded server thật.
}
~~~

Với **RANDOM_PORT**, Spring Boot tạo WebServerApplicationContext, khởi động embedded web server và yêu cầu hệ điều hành chọn một cổng khả dụng, về cơ bản tương đương **server.port=0**. Client kết nối tới cổng được cấp sau khi server đã khởi động. Không gán một cổng như 8080 trong source test vì dễ bị chiếm khi chạy song song trên developer machine hoặc CI.

**Kết quả cần đạt:** Bạn biết lúc nào phải chọn RANDOM_PORT, cách lấy cổng bằng **@LocalServerPort**, gửi GET/POST với **TestRestTemplate** hoặc JDK **HttpClient**, assert HTTP status và JSON, phân biệt với MockMvc, cũng như hiểu các bẫy về rollback transaction, state của Spring context, security và concurrency.

**Phiên bản minh họa:** Java 17+, Spring Boot **3.3.5**, Gradle, Spring MVC/embedded Tomcat từ spring-boot-starter-web, JUnit Jupiter từ spring-boot-starter-test. Trong Spring Boot đời khác, tên client/annotation được khuyến nghị có thể thay đổi.

## 2. Bốn chế độ WebEnvironment của @SpringBootTest

| Giá trị | Server được khởi động? | Đặc điểm | Khi chọn |
|---|---|---|---|
| **MOCK** (mặc định) | Không khởi động embedded HTTP server thật | Mock web ApplicationContext nếu có web stack; có thể dùng MockMvc | Test MVC, full context, không cần socket |
| **RANDOM_PORT** | **Có** | Embedded server mở cổng do OS chọn | HTTP integration test, network boundary và servlet-container behavior |
| **DEFINED_PORT** | **Có** | Port theo server.port hoặc thường là 8080 nếu không cấu hình | Tích hợp đặc biệt cần port xác định |
| **NONE** | Không | ApplicationContext không có môi trường web | Test bean/service không cần HTTP |

Ví dụ minh họa (không phải project tự chạy đầy đủ):

~~~java
@SpringBootTest // WebEnvironment.MOCK
class WithoutRealServerTest {}

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RandomHttpServerTest {}

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT)
class FixedHttpServerTest {}

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NonWebContextTest {}
~~~

**Tại sao RANDOM_PORT phù hợp CI?** Khi nhiều suite cùng chạy, hai server cố dùng một port cố định dễ xung đột. Với port 0, hệ điều hành cấp cổng khi bind, làm giảm đáng kể nguy cơ đó. RANDOM_PORT không bảo đảm test thành công nếu sandbox cấm socket, không có dependency web hoặc resource đã cạn.

**Có webEnvironment=RANDOM_PORT không đủ để tạo HTTP server trong project không-web.** Ví dụ bên dưới dùng spring-boot-starter-web, có Spring MVC, embedded Tomcat và Jackson. Nếu dự án chỉ có starter cơ bản, đừng giả định đã có endpoint/server.

## 3. Luồng request với RANDOM_PORT

~~~text
Gradle/JUnit Jupiter
        |
        | @SpringBootTest(RANDOM_PORT)
        v
Spring TestContext / Spring Boot bootstrap
        |
        | @SpringBootApplication, beans, MVC mappings, filters
        v
WebServerApplicationContext
        |
        | embedded Tomcat bind cổng 0
        v
OS cấp cổng thật: 51xxx
        |                         |
        v                         v
@LocalServerPort              TestRestTemplate
        |                         |
        +-----------+-------------+
                    |
                 HTTP/TCP
                    |
                    v
           Tomcat servlet stack
                    |
             DispatcherServlet
                    |
             @RestController
                    |
          Jackson message converter
                    |
                    v
            HTTP status/body/headers
                    |
                    v
             JUnit assertions
~~~

Spring khởi động ApplicationContext **trước khi phương thức @Test chạy**. Khi context có lỗi bean, mapping, startup hoặc bind, bài test có thể thất bại trước phần assert. Khi server khởi động thành công, test client kết nối qua HTTP thật dù server và test chạy **trong cùng JVM**.

Trong test truyền thống với MockMvc, **mvc.perform(...)** tạo mock request và chuyển qua hạ tầng Spring MVC mà không gửi request qua socket. Không nhầm việc “có DispatcherServlet” với “có một cổng TCP đang lắng nghe”.

**RANDOM_PORT không có nghĩa mỗi test method tạo server mới.** Spring TestContext có thể cache ApplicationContext giữa các bài test có cấu hình tương đương; khi tái dùng context, cùng server/port có thể được tái dùng.

## 4. Cách lấy cổng thực sự: @LocalServerPort

Trong Spring Boot 3.3.x, package là **org.springframework.boot.test.web.server.LocalServerPort**:

~~~java
import org.springframework.boot.test.web.server.LocalServerPort;

@LocalServerPort
int port;
~~~

Annotation này dựa trên runtime property **local.server.port**, phản ánh cổng thực tế sau khi web server khởi tạo. **server.port=0** là cấu hình yêu cầu OS chọn cổng, không phải cổng mà client có thể dùng. Khi tự tạo URI, hãy dùng số port từ @LocalServerPort:

~~~java
URI uri = URI.create(
    "http://127.0.0.1:" + port + "/api/quotes");
~~~

Các snippet trên cần được đặt trong class test với import URI thích hợp. Có thể đọc port qua **Environment.getProperty("local.server.port", Integer.class)** ở giai đoạn test đã có context, nhưng không cần nếu dùng @LocalServerPort.

**Không dùng @LocalServerPort để inject vào constructor bean production được tạo trước khi server initialized.** Property chỉ hiện diện đúng thời điểm khi server đã bind. Test field được Spring inject sau khi startup là tình huống sử dụng tự nhiên.

Cũng không assert port luôn bằng 8080, luôn trên 50000 hoặc luôn khác nhau mỗi lần chạy. Cách đúng là chỉ kiểm tra cổng hợp lệ (1..65535) rồi **dùng chính số cổng ấy**.

## 5. Dự án thực hành Spring Boot 3.3.5: REST báo giá

Ta thiết kế một REST API stateless để tập trung vào việc gửi HTTP thật, không cần database và không phụ thuộc external service.

**Đặc tả:**
- **GET /api/quotes?product=book&quantity=2** → status **200**, response JSON gồm product=book, quantity=2, totalCents=2400.
- **POST /api/quotes** với JSON product=pen, quantity=4 → **201**, totalCents=1000.
- Giá đơn vị: book **1200 cents**, pen **250 cents**.
- Quantity hợp lệ từ **1 đến 1000**; product phải không null/blank.
- Quantity ngoài miền → **400**, product không được hỗ trợ → **404**.
- GET thiếu query parameter bắt buộc hoặc quantity không thể parse thành int → **400** ở Spring MVC binding layer.
- Không lưu resource vào DB; POST minh họa HTTP 201 và JSON handling chứ không tạo hóa đơn trong persistence.

### 5.1. Cấu trúc file

~~~text
settings.gradle
build.gradle
src/main/java/demo/randomport/QuoteApplication.java
src/main/java/demo/randomport/QuoteRequest.java
src/main/java/demo/randomport/QuoteResponse.java
src/main/java/demo/randomport/QuoteController.java
src/test/java/demo/randomport/QuoteRandomPortTest.java
src/test/java/demo/randomport/QuoteMockMvcTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'random-port-http-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Giải thích:** spring-boot-starter-web cung cấp Spring MVC, Jackson, embedded Tomcat; spring-boot-starter-test cung cấp JUnit Jupiter, Spring Boot Test, Spring Test/MockMvc và TestRestTemplate. useJUnitPlatform() để Gradle chạy JUnit Jupiter. Chưa có Spring Security hoặc DB ở bản mẫu; nếu thêm các dependency ấy, hành vi HTTP/error và setup có thể khác.

### 5.2. Các lớp production

**src/main/java/demo/randomport/QuoteApplication.java**

~~~java
package demo.randomport;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }
}
~~~

**src/main/java/demo/randomport/QuoteRequest.java**

~~~java
package demo.randomport;

public record QuoteRequest(String product, int quantity) {
}
~~~

**src/main/java/demo/randomport/QuoteResponse.java**

~~~java
package demo.randomport;

public record QuoteResponse(
        String product, int quantity, long totalCents) {
}
~~~

Java 17 record phù hợp với DTO ngắn. Jackson của Spring Boot 3.3 hỗ trợ các record ở ví dụ này. Mỗi public type đặt trong file Java đúng tên, và QuoteResponse có equals/hashCode dựa trên các thành phần nên assertion so object rất rõ.

**src/main/java/demo/randomport/QuoteController.java**

~~~java
package demo.randomport;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    @GetMapping
    public QuoteResponse getQuote(
            @RequestParam("product") String product,
            @RequestParam("quantity") int quantity) {
        return calculate(product, quantity);
    }

    @PostMapping
    public ResponseEntity<QuoteResponse> postQuote(
            @RequestBody QuoteRequest request) {
        QuoteResponse quote =
                calculate(request.product(), request.quantity());
        return ResponseEntity.status(HttpStatus.CREATED).body(quote);
    }

    private static QuoteResponse calculate(
            String product, int quantity) {
        if (product == null || product.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "product must not be blank");
        }
        if (quantity < 1 || quantity > 1000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "quantity must be in 1..1000");
        }

        long priceCents = switch (product) {
            case "book" -> 1200L;
            case "pen" -> 250L;
            default -> throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "Unknown product");
        };

        return new QuoteResponse(
                product, quantity, priceCents * quantity);
    }
}
~~~

Ở đây **@GetMapping** nhận query params do MVC chuyển kiểu; **@PostMapping** dùng Jackson chuyển JSON request body vào QuoteRequest, trả ResponseEntity/201. Lỗi thiếu/sai kiểu tham số có thể được framework xử lý trước calculate; lỗi về miền quantity/unknown product xảy ra trong business logic đơn giản ở calculate.

**ResponseStatusException** trả HTTP status tương ứng nhưng body lỗi không được đặc tả cứng trong ví dụ. Không assert raw error JSON có một shape cụ thể nếu chưa cấu hình error contract riêng, vì framework/custom ControllerAdvice có thể thay đổi nó.

## 6. Integration test thực sự gọi HTTP với TestRestTemplate và Java HttpClient

**src/test/java/demo/randomport/QuoteRandomPortTest.java**

~~~java
package demo.randomport;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class QuoteRandomPortTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate restTemplate;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void embeddedServerHasARealPort() {
        assertTrue(port > 0 && port <= 65535);
    }

    @Test
    void getWithRealHttpReturnsJson() {
        ResponseEntity<QuoteResponse> response =
                restTemplate.getForEntity(
                    "/api/quotes?product=book&quantity=2",
                    QuoteResponse.class);

        assertEquals(200, response.getStatusCode().value());
        assertEquals(
                new QuoteResponse("book", 2, 2400L),
                response.getBody());
        assertNotNull(response.getHeaders().getContentType());
        assertTrue(response.getHeaders().getContentType()
                .isCompatibleWith(MediaType.APPLICATION_JSON));
    }

    @Test
    void postJsonReturnsCreated() {
        ResponseEntity<QuoteResponse> response =
                restTemplate.postForEntity(
                    "/api/quotes",
                    new QuoteRequest("pen", 4),
                    QuoteResponse.class);

        assertEquals(201, response.getStatusCode().value());
        assertEquals(
                new QuoteResponse("pen", 4, 1000L),
                response.getBody());
    }

    @Test
    void quantityZeroReturns400() {
        ResponseEntity<String> response =
                restTemplate.getForEntity(
                    "/api/quotes?product=book&quantity=0",
                    String.class);
        assertEquals(400, response.getStatusCode().value());
    }

    @Test
    void unknownProductReturns404() {
        ResponseEntity<String> response =
                restTemplate.getForEntity(
                    "/api/quotes?product=unknown&quantity=1",
                    String.class);
        assertEquals(404, response.getStatusCode().value());
    }

    @Test
    void missingQuantityReturns400() {
        ResponseEntity<String> response =
                restTemplate.getForEntity(
                    "/api/quotes?product=book",
                    String.class);
        assertEquals(400, response.getStatusCode().value());
    }

    @Test
    void invalidQuantityBindingReturns400() {
        ResponseEntity<String> response =
                restTemplate.getForEntity(
                    "/api/quotes?product=book&quantity=abc",
                    String.class);
        assertEquals(400, response.getStatusCode().value());
    }

    @Test
    void plainJdkClientCanConnectToEmbeddedServer() throws Exception {
        URI uri = URI.create(
                "http://127.0.0.1:" + port
                    + "/api/quotes?product=book&quantity=1");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        JsonNode json = objectMapper.readTree(response.body());
        assertEquals("book", json.path("product").asText());
        assertEquals(1, json.path("quantity").asInt());
        assertEquals(1200L, json.path("totalCents").asLong());
    }
}
~~~

**Giải thích test:**

1. @SpringBootTest(RANDOM_PORT) làm server thật khởi động trước @Test.
2. @LocalServerPort lấy cổng runtime. Kiểm tra chỉ cần cổng hợp lệ; không được assert một số cố định.
3. @Autowired TestRestTemplate là tiện ích Spring Boot 3.3 cho các real HTTP integration tests. Dùng **relative URL** nên không cần gắn localhost:port vào mỗi lệnh get/post.
4. Khi response 400/404, TestRestTemplate được thiết kế thích hợp cho testing, thường **trả status** để assertion thay vì ném exception ngay khi gặp HTTP error như RestTemplate cấu hình error handler thông thường.
5. POST đưa QuoteRequest record qua Jackson thành JSON, server bind lại từ @RequestBody và trả JSON QuoteResponse.
6. GET trả QuoteResponse; assertEquals trên record kiểm tra đầy đủ product, quantity, totalCents. Assert Content-Type tương thích application/json, không so raw JSON với thứ tự property cụ thể.
7. Test cuối sử dụng **Java 17 HttpClient**, kết nối **127.0.0.1:port** qua socket; parse JSON bằng ObjectMapper để assert các field. Với Java 17, HttpClient không cần try-with-resources ở đây.
8. Các test không ghi dữ liệu vào DB, nên **không có test nào cần dữ liệu do test khác tạo ra**.

Các trường hợp theo đặc tả:

| Case | URL/Body | Status đúng | Điều cần kiểm |
|---|---|---|---|
| GET thành công | product=book, quantity=2 | 200 | totalCents=2400 |
| POST thành công | JSON pen, quantity=4 | 201 | totalCents=1000 |
| Quantity ngoài miền | quantity=0 | 400 | Business validation |
| Product unknown | product=unknown | 404 | Resource/business lookup |
| Thiếu tham số | thiếu quantity | 400 | MVC required parameter |
| Tham số sai kiểu | quantity=abc | 400 | MVC type conversion |
| Cổng runtime | @LocalServerPort | hợp lệ | Embedded server đã bind |
| JDK client | GET 127.0.0.1:port | 200 | HTTP thực và parse JSON |

**Lưu ý:** @WithMockUser không tự làm một request real HTTP trở thành authenticated, vì server xử lý request ở thread riêng. Nếu app dùng security, client phải gửi header/token/cookie phù hợp.

## 7. Ví dụ đối chiếu: @WebMvcTest với MockMvc không mở socket

**src/test/java/demo/randomport/QuoteMockMvcTest.java**

~~~java
package demo.randomport;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(QuoteController.class)
class QuoteMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void mapsAndSerializesWithoutOpeningPort() throws Exception {
        mvc.perform(get("/api/quotes")
                        .param("product", "book")
                        .param("quantity", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.product").value("book"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.totalCents").value(2400));
    }

    @Test
    void missingQuantityIsBadRequest() throws Exception {
        mvc.perform(get("/api/quotes")
                        .param("product", "book"))
                .andExpect(status().isBadRequest());
    }
}
~~~

@WebMvcTest chỉ tải những thành phần liên quan MVC theo slice và không mở embedded server thật. Trong ví dụ, QuoteController không inject service bên ngoài nên slice có thể chạy trực tiếp. Nếu controller inject QuoteService hoặc repository, slice thường cần một bean test hoặc mock phù hợp.

| Tiêu chí | @WebMvcTest + MockMvc | @SpringBootTest(RANDOM_PORT) |
|---|---|---|
| Cổng TCP | Không | **Có** |
| Servlet container thật nhận request | Không | Có, với starter-web/Tomcat |
| Kiểm tra MVC routing và JSON | Có | Có |
| Full application context | Không mặc định, là slice | Thường có |
| Tốc độ | Thường nhanh hơn | Thường tốn chi phí startup hơn |
| Network boundary | Không | Có |
| Error page/connector behavior thật | Hạn chế | Phù hợp hơn |
| Dữ liệu DB bên ngoài | Phụ thuộc cấu hình test | Phụ thuộc cấu hình test |

**@SpringBootTest(webEnvironment=MOCK) + @AutoConfigureMockMvc** cho phép test nhiều bean hơn một web slice nhưng vẫn dùng mock requests. Nếu cần kiểm tra socket hoặc embedded server configuration, chỉ dùng mvc.perform không đủ.

## 8. Chạy ví dụ, kết quả và báo cáo JUnit

Với project đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Các file liệt kê trong bài cung cấp **mã nguồn và build configuration**; nếu tạo project thủ công chưa có wrapper, ./gradlew chưa tồn tại. Dùng Gradle tương thích để tạo wrapper hoặc chạy gradle test.

Ở source này, **QuoteRandomPortTest có 8 phương thức @Test**, **QuoteMockMvcTest có 2 phương thức @Test**, tổng **10 test methods**. Nếu không thêm test khác và mọi điều kiện môi trường đáp ứng, tất cả được thiết kế để PASS. Xem báo cáo:

~~~text
build/reports/tests/test/index.html
~~~

Có thể chạy một lớp:

~~~bash
./gradlew test --tests demo.randomport.QuoteRandomPortTest
./gradlew test --tests demo.randomport.QuoteMockMvcTest
~~~

Đừng assert số port cứng hoặc toàn bộ startup log: cổng thay đổi theo OS, còn log Tomcat/Gradle thay đổi theo cấu hình. Các assertion ổn định là HTTP status, JSON và những header được đặc tả.

## 9. Tại sao @Transactional trên test không rollback dữ liệu phía server?

Đây là bẫy quan trọng nhất khi chuyển từ MockMvc/unit test sang real HTTP integration.

Với Spring TestContext, @Transactional trên test method thường mở **test-managed transaction** và rollback cuối test. Nhưng khi dùng RANDOM_PORT hoặc DEFINED_PORT:
- HTTP client thực thi trong **thread của test**.
- Server nhận HTTP trong **thread của embedded server**.
- Transaction context theo thread **không tự truyền qua TCP**.
- Nếu service phía server dùng một transaction khác và commit thay đổi database, **rollback transaction của test không rollback được các thay đổi đã commit ở server**.

Đoạn minh họa về giả định sai:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpTest {
    // Gửi POST /orders bằng HTTP client thật.
    // KHÔNG thể mặc nhiên tin DB write phía server
    // sẽ rollback khi test method kết thúc.
}
~~~

Snippet này không phải file chạy độc lập; nó diễn tả một tình huống transaction cần đặc biệt chú ý. Trong ứng dụng có endpoint POST tạo entity, dữ liệu server commit có thể tồn tại sang test tiếp theo.

**Cách cô lập dữ liệu cho real HTTP tests:**
1. Dùng **test database/schema riêng** hoặc Testcontainers có vòng đời phù hợp.
2. Tạo ID/namespace riêng cho từng test.
3. Cleanup bằng repository, @Sql/script, API fixture hoặc reset schema **ở đúng transaction và đúng nguồn dữ liệu**.
4. Tránh giả định @DirtiesContext xóa database; nó loại ApplicationContext khỏi cache, còn dữ liệu DB bên ngoài có thể giữ nguyên.
5. Xử lý trường hợp test chết giữa chừng: với DB tạm, dữ liệu tồn đọng không ảnh hưởng môi trường/lần chạy sau.
6. Nếu test chạy song song, không cleanup dữ liệu của test khác; dùng prefix/key riêng hoặc tài nguyên cô lập.

Trong project demo, GET và POST đều tính toán **stateless**, do đó không phải xử lý DB cleanup. Đây là lựa chọn có chủ đích để tập trung vào RANDOM_PORT.

## 10. ApplicationContext caching và việc chạy song song

Spring TestContext cache ApplicationContext theo cấu hình test thực tế nhằm giảm startup. Với RANDOM_PORT:
- Các method trong một class test thường dùng cùng context/server/cổng.
- Các class tương đương về configuration có thể dùng cached context; class có profile, property, mock bean khác có thể có context mới.
- @DirtiesContext có thể khiến server đóng và một context mới được tạo, lúc đó OS có thể cấp cổng khác.
- Một singleton service, fake Map hoặc Spring cache có thể giữ state giữa các test trong cùng context.
- Port động chỉ giảm xung đột **cổng**; nó không tự cô lập database, Redis, Kafka topic, file hay tài khoản external.
- Test chạy song song dùng chung mutable bean hoặc mock có thể can thiệp nhau ngay cả khi port là số hợp lệ.

**Không dựa vào test order** hoặc giả định test B chạy sau test A. Khi cần chạy server thật, giữ mỗi scenario độc lập với fixture/setup/teardown của nó. Cần kiểm tra concurrency ở cả CI và IDE vì cấu hình chạy có thể khác nhau.

**Đừng lạm dụng @DirtiesContext** để chữa test rò state. Nó buộc khởi động lại Spring và embedded server, rất tốn thời gian; tìm đúng nơi state tồn tại rồi cleanup trước. Dùng @DirtiesContext khi test thật sự làm thay đổi cấu hình/context không khôi phục được.

## 11. Security, headers và HTTP thực

Khi ứng dụng thêm Spring Security, server thật xử lý authentication/authorization theo filter chain. Khi test:
- Gửi **Authorization** header, token, session cookie hoặc basic auth phù hợp.
- Assert 401 khi thiếu/không hợp lệ credentials, 403 khi authenticated nhưng không được phép, 200/201 khi có quyền.
- Với POST/PUT/DELETE ở browser session, hiểu yêu cầu CSRF.
- Không giả định @WithMockUser gắn trên test method tự lan sang server thread của real HTTP request.

HTTP test cũng có thể kiểm tra Content-Type, Accept, CORS headers, redirect, cookie, cache headers và ETag; nhưng **chỉ assert những gì thuộc contract**. Ví dụ không có security nên chỉ assert JSON content type ở GET và status/body ở các case còn lại.

**Server thật không tự tái tạo browser hoặc reverse proxy.** CORS enforcement là logic browser; TLS termination, DNS, ingress, load balancer và nhiều instance thường cần môi trường staging/E2E tương ứng. RANDOM_PORT ở localhost không thay thế được những kiểm thử đó.

## 12. Chọn HTTP client phù hợp

**TestRestTemplate:** Tiện cho Spring Boot 3.3; có thể gọi relative paths, serialize request/deserialize response bằng converters và kiểm tra lỗi HTTP 4xx/5xx bằng ResponseEntity.

~~~java
ResponseEntity<String> result = restTemplate.getForEntity(
        "/api/quotes?product=book&quantity=0",
        String.class);
assertEquals(400, result.getStatusCode().value());
~~~

**Java 17 HttpClient:** Client JDK độc lập với Spring, dùng @LocalServerPort để tự xây dựng URI, kiểm tra response status, headers và body:

~~~java
URI uri = URI.create("http://127.0.0.1:" + port
        + "/api/quotes?product=pen&quantity=1");
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
HttpResponse<String> response = HttpClient.newHttpClient().send(
        request, HttpResponse.BodyHandlers.ofString());
assertEquals(200, response.statusCode());
~~~

Hai snippet trên là mã **bên trong @Test đã khai báo biến và imports**, không phải tệp Java độc lập. JDK 17 HttpClient không implement AutoCloseable; không dùng try-with-resources cho HttpClient trong bản JDK này.

**WebTestClient:** Spring Boot cũng hỗ trợ WebTestClient cho real server tests nếu dependency/client auto-configuration thích hợp. Trong dự án MVC, cần bảo đảm thư viện WebFlux client/test có mặt trên test classpath khi dùng WebTestClient. Chú ý WebTestClient có chế độ bindToController/bindToApplicationContext **không dùng network**; để kiểm tra server thật phải dùng base URL đang chạy.

**RestAssured:** Thư viện HTTP assertions tiện dụng nhưng cần dependency riêng. Nếu nhiều test chạy song song, tránh gán port vào state global không kiểm soát; cấu hình request-specific với cổng runtime.

Chọn một client đủ đáp ứng mục tiêu. Bộ ví dụ dùng TestRestTemplate làm chính, còn HttpClient để minh họa một kết nối TCP độc lập với Spring test helper.

## 13. Những điểm bổ sung dễ bỏ qua

### 13.1. Management port khác application port

Nếu dùng Actuator và cấu hình **management.server.port** khác server.port, management endpoint có thể chạy ở server/port riêng. Khi đó @LocalServerPort chỉ port ứng dụng; **@LocalManagementPort** dùng cho management server trong trường hợp hỗ trợ. Ví dụ này không thêm Actuator.

### 13.2. WebFlux và embedded server khác Tomcat

Spring Boot lựa chọn stack tùy dependencies. Trong ví dụ starter-web ⇒ MVC + Tomcat theo mặc định. Với WebFlux-only, RANDOM_PORT có thể dùng Netty/reactive server; nếu cả MVC và WebFlux cùng có, MVC thường được chọn trừ khi cấu hình spring.main.web-application-type=reactive. Vì vậy khi sao chép cách test sang dự án WebFlux phải kiểm tra server type/client dependencies.

### 13.3. External services và Testcontainers

Cổng server ứng dụng **không phải** cổng PostgreSQL container, fake HTTP server hay message broker. Khi test cần địa chỉ runtime của các dependency ngoài, dùng cấu hình riêng (ví dụ @DynamicPropertySource hoặc tích hợp Testcontainers phù hợp), không lấy nhầm local.server.port.

### 13.4. Timeout và tác vụ bất đồng bộ

Real HTTP có thể chờ DB, network hoặc background task. Hãy thiết lập timeout hợp lý ở client/test; tránh Thread.sleep với một khoảng đoán mò để “đợi cho đủ”. Với endpoint trả 202 Accepted, việc nhận 202 chỉ xác nhận request được chấp nhận, **không chứng minh async job đã hoàn thành**. Cần poll trạng thái có deadline và cleanup phù hợp.

### 13.5. HTTP error details có thể thay đổi theo cấu hình

Test mẫu chỉ kiểm tra HTTP status của lỗi 400/404 vì error body chưa được định nghĩa chi tiết. Khi ứng dụng có @ControllerAdvice/ProblemDetail/custom error code, hãy assert body theo contract thật. Không nên viết kỳ vọng raw JSON dựa vào output tình cờ của framework một phiên bản.

## 14. Lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Connection refused tại localhost:8080 | Hard-code 8080 trong RANDOM_PORT | Dùng @LocalServerPort hoặc relative path của TestRestTemplate |
| @LocalServerPort = 0/không resolve | Sai webEnvironment, import hoặc đọc trước server startup | Kiểm tra RANDOM_PORT, web dependencies và package annotation |
| @Autowired TestRestTemplate fail | Thiếu test dependency hoặc bootstrap mode sai | Xem starter-test và @SpringBootTest(RANDOM_PORT) |
| MockMvc pass nhưng HttpClient fail | Mock request không có socket | Kiểm tra server startup, port, filters, security |
| Port binding lỗi CI | Sandbox không cho bind hoặc dùng cổng cố định | Kiểm tra quyền loopback và dùng RANDOM_PORT |
| JSON/body khác expected | DTO/serializer/message converter khác | Assert fields/content type theo contract |
| 401/403 khi đang mong 200 | Spring Security chặn anonymous hoặc CSRF | Gửi credentials thật, kiểm tra filter chain |
| 400 khi quantity=abc | MVC không chuyển được String thành int | Xác nhận expected là lỗi binding |
| Test @Transactional vẫn ghi DB | Server thread transaction riêng | Dọn DB/test fixture, không dựa vào rollback test |
| Test pass một mình nhưng fail toàn suite | Shared context/state, DB/cache hoặc parallelism | Cô lập dữ liệu, cleanup đúng nguồn |
| Suite chậm khi có nhiều RANDOM_PORT tests | Khởi động full context/server nhiều lần | Chuyển logic nhỏ sang unit/MockMvc, giảm cấu hình context dư |
| Management endpoint khác port | Có management.server.port riêng | Dùng port management đúng, không dùng port ứng dụng |
| Cổng thay đổi mỗi lần chạy | OS chọn port động | Không assert số cụ thể, dùng @LocalServerPort |

**Quy trình điều tra ngắn:** xác nhận annotation/import và web starter → đọc startup log và bean errors → kiểm tra cổng/URL/method/body/auth → assert status trước body → kiểm tra state/transaction/server threads → chạy riêng và toàn suite để tìm lỗi isolation.

## 15. Xây chiến lược kiểm thử theo tầng

- **Unit/JUnit Jupiter:** Nhiều ca nghiệp vụ, chạy nhanh không cần context.
- **@WebMvcTest + MockMvc:** Mapping, validation, JSON/headers ở MVC slice, không mở socket.
- **@SpringBootTest(MOCK) + @AutoConfigureMockMvc:** Cần full context nhưng chỉ cần mock HTTP request.
- **@SpringBootTest(RANDOM_PORT):** Một tập ca có giá trị cao về HTTP thật, filter/auth flow, startup, container behavior và integration qua nhiều bean.
- **Testcontainers hoặc integration với DB/broker:** Kiểm tra persistence, transactions và external protocol.
- **Staging/E2E:** Kiểm tra proxy/TLS, ingress, service discovery, production-like config và multi-instance.

Không mặc định mọi controller test phải dùng RANDOM_PORT. Một bộ test tốt có nhiều unit/MVC tests nhanh và một số real HTTP tests đúng rủi ro; không tăng startup cost khi không cần.

## 16. Tự kiểm tra

**1. Vì sao @SpringBootTest không ghi webEnvironment không đồng nghĩa server HTTP thật?**  
Vì mặc định là **MOCK**, có mock web environment nhưng không mở embedded server qua TCP.

**2. server.port được đặt 0. Lấy số cổng kết nối thật bằng cách nào?**  
Dùng @LocalServerPort, đọc local.server.port sau startup hoặc sử dụng TestRestTemplate tương thích với relative URL.

**3. Hai test RANDOM_PORT có bắt buộc hai port khác nhau?**  
Không. Spring TestContext có thể cache context/server và tái dùng cổng; chỉ lúc khởi động mới chọn port.

**4. Một test @Transactional gửi POST tạo entity thật qua HTTP; rollback của test có xóa row server commit không?**  
Không tự động, vì server và client khác thread/transaction. Cần cleanup và test DB isolation.

**5. Vì sao chỉ gắn @WithMockUser không bảo đảm TestRestTemplate nhận 200 qua server security?**  
Security context giả của test thread không tự truyền thành credentials của một HTTP request thực; phải gửi authentication phù hợp.

**6. Test gì dùng MockMvc thay vì RANDOM_PORT?**  
Mapping, validation, JSON conversion và controller logic không đòi cổng mạng hoặc servlet container network-level behavior.

**7. GET quantity=abc trả 400 ở đâu?**  
Ở binding/type conversion của Spring MVC trước khi controller dùng calculate(int quantity).

**8. RANDOM_PORT có test được reverse proxy hay TLS ingress ở production không?**  
Không mặc định; nó chỉ chạy embedded server cục bộ. Cần môi trường tích hợp/staging thích hợp để thử proxy/network deployment.

## 17. Tài liệu chính thức

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — WebEnvironment, random ports và transactional behavior.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html) — server.port=0, @LocalServerPort.
- [Spring Boot 3.3 — TestRestTemplate](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html) — HTTP test client.
- [Spring Boot 3.3 — SpringBootTest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/SpringBootTest.html) — cách chọn webEnvironment.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html) — mock MVC request.
- [JDK 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html) — HTTP client chuẩn Java.

**Kết luận:** **RANDOM_PORT khởi động server HTTP thật trên cổng do OS cấp**, khác MockMvc. Dùng @LocalServerPort hoặc TestRestTemplate để gửi request tới đúng cổng, kiểm chứng status/headers/JSON và không quên quản lý transaction, database, shared state lẫn security như những thành phần tích hợp thật.