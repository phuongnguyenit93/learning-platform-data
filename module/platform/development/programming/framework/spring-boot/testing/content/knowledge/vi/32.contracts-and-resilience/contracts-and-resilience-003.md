# Consumer-driven contract khi nhiều dịch vụ phát triển độc lập

## 1. Tại sao cần consumer-driven contract testing?

Giả sử ba nhóm phát triển độc lập:

- **CheckoutWeb** gọi HTTP tới **InventoryService** để hiển thị chi tiết sản phẩm.
- **BillingService** cũng gọi InventoryService nhưng chỉ quan tâm giá và SKU.
- **InventoryService** muốn thay đổi model, thêm field, đổi database, tách service, triển khai nhanh mà không cần deploy đồng thời hai consumers.

Các unit tests của từng repo đều có thể PASS trong khi production vẫn hỏng: một consumer cần trường `title` nhưng provider đổi tên thành `name`; provider đổi status 404 sang 200 với body error; consumer gửi header/JSON sai định dạng; provider đã xóa endpoint còn consumer cũ đang chạy.

**Consumer-driven contract (CDC)** giải quyết phần giao tiếp: mỗi consumer mô tả những request nó **thực sự gửi** và response nó **cần để hoạt động đúng**. Provider liên tục xác minh nó đáp ứng các kỳ vọng đó. Contract được version hóa theo consumer/provider builds để xác định **phiên bản nào có thể triển khai cùng phiên bản nào** mà không buộc tất cả nhóm phải release cùng lúc.

Ý tưởng cốt lõi:

~~~text
CheckoutWeb consumer                         InventoryService provider
         |                                             |
         |  Consumer Pact test                         |  Provider verification
         |  chạy HTTP client thật                     |  chạy ứng dụng thật
         v                                             v
  Pact MockServer                              Real HTTP endpoint
         |                                             ^
         | ghi interactions thành Pact JSON            |
         +---- publish artifact / Pact Broker ---------+
                           |
                           +--- verification matrix
                           +--- can-i-deploy release gate
~~~

Không phải consumer viết “mọi API provider phải có”. Consumer chỉ công bố **những gì nó dùng**. Còn provider có thể thêm fields/endpoints ngoài các yêu cầu đó.

### Kết quả học tập

Sau bài bạn có thể:

1. Phân biệt **consumer**, **provider**, **interaction**, **provider state**, **Pact file** và **Pact Broker**.
2. So sánh CDC với unit, integration, end-to-end, OpenAPI/schema validation và Spring Cloud Contract.
3. Viết consumer test dùng Pact JVM/JUnit 5, gọi **HTTP client production** vào mock server và sinh Pact artifact.
4. Viết provider test dùng Spring Boot và `@PactFolder`/`@Provider`/`@State`, xác minh Pact trên real endpoint.
5. Hiểu tại sao provider verification là bước bắt buộc: consumer mock PASS **chưa chứng minh provider thật tương thích**.
6. Thiết kế Pact matchers đủ linh hoạt, không over-specify fields không sử dụng.
7. Kiểm cả status 200, 404, request headers, body, error contract và provider state.
8. Sử dụng Pact Broker, branch/version/deployment metadata, `can-i-deploy` và `record-deployment`.
9. Phân biệt `pending pacts` với `WIP pacts` để không làm tắc provider pipeline hoặc bỏ qua lỗi tương thích.
10. Lập kế hoạch expand–migrate–contract khi có nhiều consumers/versions triển khai độc lập.
11. Biết giới hạn của contract test với timeout, retry, idempotency, bảo mật, hiệu năng và messaging.
12. Xây pipeline CDC có khả năng xác định chính xác bản consumer/provider nào an toàn để lên môi trường.

## 2. Contract là gì, khác API schema ra sao?

Một *HTTP interaction* gồm một request cụ thể và response mà consumer trông đợi:

~~~http
GET /api/books/42 HTTP/1.1
Accept: application/json
~~~

Consumer kỳ vọng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Clean Code"}
~~~

Một tương tác khác khi sách không tồn tại:

~~~http
GET /api/books/404 HTTP/1.1
Accept: application/json
~~~

Kỳ vọng là status `404 Not Found`; nếu client không dùng body của lỗi thì contract **không cần** đóng băng toàn bộ nội dung error body.

**OpenAPI** có thể mô tả tất cả endpoint và nhiều schema có thể được gọi. **Consumer contract** thể hiện đúng tập request/response mà **một phiên bản consumer cụ thể đang phụ thuộc**. Hai thứ bổ sung nhau, không thay thế nhau.

| Khía cạnh | OpenAPI/schema validation | Consumer-driven Pact |
| --- | --- | --- |
| Ai nêu kỳ vọng? | Thường do provider/API governance quản lý | Consumer viết test cho nhu cầu thực |
| Phạm vi | API surface rộng hơn | Chỉ những interactions consumer dùng |
| Provider có thay đổi được không? | Kiểm soát theo schema và chính sách version | Cần pass Pact của consumer versions liên quan |
| Có mock service không? | Có thể generate mock/stub từ schema | Pact consumer test chạy mock theo interactions |
| Có kiểm provider thật không? | Cần provider implementation tests | Provider verifier replay Pact lên service thật |
| Có ma trận deploy không? | Không tự có nếu chỉ giữ YAML/JSON | Pact Broker Matrix + can-i-deploy |
| Tính đủ end-to-end? | Không | Cũng không |

**Không được hiểu contract test là “bắt hai dịch vụ phải deploy cùng lúc”**. Mục tiêu của Pact Broker và deployment checks chính là cho phép **triển khai độc lập có bằng chứng tương thích**.

## 3. Bối cảnh nhiều teams và những ranh giới ownership

Giả sử checkout cần đúng hai điều:

- `GET /api/books/{id}` với `id=42` trả status 200 và trường JSON số `id`, chuỗi `title`.
- `GET /api/books/404` trả status 404 để CheckoutWeb xử lý như “không tìm thấy”.

Provider có thể thêm `stock`, `author` hoặc `updatedAt` trong response 200 mà CheckoutWeb không đọc. Consumer **không nên khóa giá trị mặc định của các fields nó không cần**; Pact mặc định hỗ trợ matcher cho kiểu/chính sách tương ứng.

Bản consumer v1 có thể chỉ đọc `title`. Bản consumer v2 đọc thêm `availability`; provider cần cung cấp field mới trước khi v2 được triển khai. Trong lúc đó, provider vẫn phải phục vụ v1 đang hoạt động.

### 3.1 Quyền sở hữu

| Thành phần | Owner điển hình | Quyền/trách nhiệm |
| --- | --- | --- |
| Consumer application code | Nhóm CheckoutWeb | Quy định request gửi, parse response, fallback |
| Consumer Pact | Nhóm CheckoutWeb | Chọn interactions và matchers có giá trị |
| Provider implementation | Nhóm InventoryService | Đảm bảo mọi Pact tương ứng được verify |
| Provider state fixture | Nhóm InventoryService | Chuẩn bị dữ liệu cho từng interaction |
| Broker | Platform/nhóm sở hữu chung | Lưu Pact versions, kết quả verification và deployments |
| Release gate | CI/CD từng dịch vụ | Chạy can-i-deploy với đúng version và environment |
| Governance/API docs | API owner hoặc platform | Quản lý API public contract, deprecation, security |

Provider **không** nên tự viết một mock consumer không dùng client code thật rồi tuyên bố đã kiểm consumer behavior. CDC có ý nghĩa khi consumer test thật chạy **client/adapter** mà ứng dụng dùng trong production.

## 4. Consumer test và provider test kiểm hai mệnh đề khác nhau

Consumer test chứng minh:

> Với một response theo hợp đồng, code CheckoutWeb tạo đúng request và đọc đúng thông tin cần thiết.

Provider verification chứng minh:

> Với những provider states cụ thể, phiên bản InventoryService thật trả response phù hợp với hợp đồng đã được công bố.

Khi chỉ chạy consumer test:

~~~text
Consumer test PASS:
    client gửi GET /api/books/42
    mock server trả JSON giả
    client parse được BookDto

KHÔNG suy ra:
    InventoryService thật đang hỗ trợ /api/books/42
    response provider thực có title
    authentication production hoạt động
    có thể deploy consumer v2 với provider v1
~~~

Khi chỉ chạy provider verification mà không dùng consumer test mới nhất, cũng có thể kiểm một Pact quá cũ và bỏ sót nhu cầu mới. Bởi vậy cần **cùng Pact artifact** được sinh từ consumer và được provider xác minh.

## 5. Pact interactions và provider states

Một Pact file có thể chứa nhiều interactions cho một cặp consumer/provider:

~~~text
CheckoutWeb -> InventoryService
    1. given "book 42 exists"
       request GET /api/books/42
       response 200, JSON id=number,title=string

    2. given "book 404 is absent"
       request GET /api/books/404
       response 404
~~~

`given(...)` mô tả **provider state**: tình huống dữ liệu/điều kiện cần tồn tại trước khi request. Pact mock server phía consumer **không cần tự tạo database thật**. Trong provider verification, provider team viết `@State` callback để seed trạng thái đó trong ứng dụng test.

Lợi ích:

- Dữ liệu không phụ thuộc record production.
- Không giả định provider có sẵn book ID 42 trong mọi môi trường.
- Một test 404 không bị flake vì test khác tạo book 404.
- Mỗi interaction có fixture riêng, không phụ thuộc thứ tự test.
- Provider có thể thay đổi persistence implementation miễn external contract còn đúng.

### 5.1 Tên provider state là một phần hợp đồng phối hợp

Nếu Pact khai báo `given("book 42 exists")` nhưng provider chỉ có callback `@State("a book exists")`, verification thất bại vì **state name không khớp**. Không sửa bằng cách bỏ `given` hoặc dùng dữ liệu ngẫu nhiên trên production DB; hãy đồng bộ tên/các tham số state có ý nghĩa.

Đối với generated IDs, Pact V3/V4 có **provider state generators** để provider callback trả dynamic ID. Bài dùng ID cố định để dễ hiểu; production có thể dùng generators khi ID chỉ biết sau khi insert fixture.

## 6. Dự án thực hành: hai Gradle modules, hai services độc lập

Mini-project sử dụng **Java 17+, Spring Boot 3.5.0, Pact JVM 4.6.17 và JUnit 5**.

- `consumer`: module CheckoutWeb; Java HTTP client + Jackson + Pact consumer tests.
- `provider`: module InventoryService; Spring Boot REST controller + in-memory catalog + Pact provider verification trên RANDOM_PORT.
- Consumer test tạo artifact ở `consumer/build/pacts`.
- Provider test được Gradle cấu hình chạy **sau** consumer test và đọc Pact file cùng nội dung, không tạo hợp đồng lần hai.

~~~text
independent-service-contracts/
  settings.gradle
  consumer/
    build.gradle
    src/main/java/example/consumer/
      BookDto.java
      InventoryClient.java
    src/test/java/example/consumer/
      InventoryConsumerPactTest.java
  provider/
    build.gradle
    src/main/java/example/provider/
      InventoryApplication.java
      BookDto.java
      BookCatalog.java
      BookController.java
    src/test/java/example/provider/
      InventoryProviderPactTest.java
~~~

Bộ ví dụ có **hai JUnit @Test ở consumer** và một **@TestTemplate của provider sinh một lần kiểm cho mỗi interaction trong Pact** (dự kiến hai provider verification invocations). Không dùng database, Docker hay Broker trong lượt kiểm local, chỉ dùng Pact mock HTTP trên localhost và Spring Boot embedded HTTP server trên random port.

### 6.1 Giới hạn của mini-project

Ví dụ tập trung HTTP GET/200/404 và provider states, không giả lập đầy đủ service discovery, OAuth, database transaction, Redis hoặc message broker. Các cơ chế đó được mô tả ở phần mở rộng. Version pins dùng để hướng dẫn tái lập, **không khẳng định là phiên bản mới nhất** và **chưa phải kết quả build chạy thực tế**.

## 7. settings.gradle

File `settings.gradle` tại root:

~~~groovy
rootProject.name = 'independent-service-contracts'
include 'consumer', 'provider'
~~~

Mỗi module có source/test classpath riêng, nên consumer có thể thay đổi client và provider có thể thay đổi implementation độc lập. Trong production, hai module có thể nằm ở hai repos riêng, artifact đi qua Pact Broker thay vì thư mục build dùng chung.

## 8. consumer/build.gradle

~~~groovy
plugins {
    id 'java'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.0'
    }
}

dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'au.com.dius.pact.consumer:junit5:4.6.17'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()

    // Consumer Pact files ghi vào thư mục build của consumer.
    systemProperty 'pact.rootDir',
            file("$buildDir/pacts").absolutePath
}
~~~

Consumer **không cần** Spring Boot runtime để sử dụng Pact. BOM Boot chỉ giữ Jackson và JUnit versions ở một tập thống nhất với phần provider. Dùng Pact consumer artifact `au.com.dius.pact.consumer:junit5` là tọa độ của Pact JVM 4.6.x, không dùng tên artifact đời cũ của Pact 4.0.

### 8.1 Vì sao version Pact được pin?

Nếu consumer dùng Pact JVM 4.6.x còn provider dùng một dòng tương thích V3/V4, generated Pact format dễ được xử lý nhất. Trong production nâng version có plan, test lại JDK/Java dependencies và Pact specification compatibility. Không tự nâng mỗi module riêng rồi coi Pact JSON không thay đổi.

## 9. provider/build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'au.com.dius.pact.provider:junit5:4.6.17'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()

    // Bắt buộc consumer tạo artifact trước khi provider verify.
    dependsOn ':consumer:test'

    // @PactFolder relative path được resolve từ projectDir.
    workingDir projectDir
}
~~~

`test.dependsOn(':consumer:test')` chỉ là orchestration **local demo**; trong hệ thống độc lập thực sự, provider CI tải published pacts từ Broker chứ không phụ thuộc consumer source repo. Bài không dùng provider-specific Spring6 extension vì Pact `junit5` cơ bản có thể verify HTTP target của một Spring Boot app đang chạy.

### 9.1 Gradle wrapper và test ordering

Từ root workspace có Gradle wrapper:

~~~bash
./gradlew :provider:test
~~~

Task graph sẽ có `:consumer:test` trước `:provider:test`. Nếu consumer test fail, Pact chưa hợp lệ và provider verification không nên được xem là hoàn tất. Nếu consumer test bị UP-TO-DATE, Gradle dùng build outputs trước đó; trong clean run sẽ tái tạo artifact.

Từ root để thử sạch:

~~~bash
./gradlew :consumer:clean :provider:clean :provider:test
~~~

**Không xóa Pact files trước provider verification**. Trong CI phân tán, việc truyền artifact phải có checksum/version; không đọc một file `latest` không xác định.

## 10. Consumer domain model: BookDto.java

File `consumer/src/main/java/example/consumer/BookDto.java`:

~~~java
package example.consumer;

public record BookDto(long id, String title) {
}
~~~

Java record giữ model đủ nhỏ. Consumer chỉ quan tâm `id` và `title`. Provider có thể bổ sung field `stock` trong JSON mà consumer không sử dụng. Jackson 2.18+ hỗ trợ deserialization record trong Java 17.

**Một lỗi backward compatibility phổ biến:** đổi `title` thành `name` sẽ khiến field title của consumer không còn được điền đúng. Nếu consumer kiểm title là bắt buộc, provider Pact verification phải fail trước khi provider được deploy thay đổi không tương thích.

## 11. Consumer HTTP client: InventoryClient.java

File `consumer/src/main/java/example/consumer/InventoryClient.java`:

~~~java
package example.consumer;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Optional;

import com.fasterxml.jackson.databind.ObjectMapper;

public final class InventoryClient {

    private final URI baseUrl;
    private final HttpClient http;
    private final ObjectMapper json;

    public InventoryClient(URI baseUrl, ObjectMapper json) {
        this.baseUrl = baseUrl;
        this.json = json;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
    }

    public Optional<BookDto> find(long id)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(
                baseUrl.resolve("/api/books/" + id))
                .timeout(Duration.ofSeconds(3))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = http.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() == 404) {
            return Optional.empty();
        }

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Inventory returned HTTP "
                    + response.statusCode());
        }

        return Optional.of(
                json.readValue(response.body(), BookDto.class));
    }
}
~~~

Test consumer sẽ gọi **đúng method `find`** mà code CheckoutWeb dùng, không dựng request bằng `HttpClient.newHttpClient().send` trực tiếp trong test ngoài client. Nhờ vậy Pact test bắt lỗi request path, Accept header, status handling và mapping.

### 11.1 Chính sách lỗi trong client

- `200`: parse JSON và trả `Optional.of(BookDto)`.
- `404`: coi là không tìm thấy, trả `Optional.empty()`.
- Các status khác: ném exception để caller có thể phân biệt 401/403/5xx với missing book.
- `IOException`/`InterruptedException` được propagate, không được âm thầm đổi thành empty.

Trong production cần đo latency, retry **có chọn lọc**, circuit breaker, correlation IDs và cancellation. Contract này **không** tự kiểm timeout/retry của mạng thật; đó là bài resilience test khác.

### 11.2 Vì sao dùng baseUrl configurable?

Client nhận URI trong constructor, nên Pact test chuyển baseUrl sang Pact mock server, còn production lấy từ configuration/service discovery. **Không hardcode localhost:8080** trong client; CI có thể chạy parallel, Pact chọn random port.

## 12. Consumer Pact test: InventoryConsumerPactTest.java

File `consumer/src/test/java/example/consumer/InventoryConsumerPactTest.java`:

~~~java
package example.consumer;

import java.net.URI;
import java.util.Map;
import java.util.Optional;

import com.fasterxml.jackson.databind.ObjectMapper;

import au.com.dius.pact.consumer.MockServer;
import au.com.dius.pact.consumer.dsl.PactDslJsonBody;
import au.com.dius.pact.consumer.dsl.PactDslWithProvider;
import au.com.dius.pact.consumer.junit5.PactConsumerTest;
import au.com.dius.pact.consumer.junit5.PactTestFor;
import au.com.dius.pact.core.model.RequestResponsePact;
import au.com.dius.pact.core.model.annotations.Pact;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@PactConsumerTest
class InventoryConsumerPactTest {

    @Pact(
        consumer = "CheckoutWeb",
        provider = "InventoryService")
    public RequestResponsePact existingBook(
            PactDslWithProvider builder) {

        return builder
                .given("book 42 exists")
                .uponReceiving("get a book by ID")
                .path("/api/books/42")
                .method("GET")
                .headers(Map.of("Accept", "application/json"))
                .willRespondWith()
                .status(200)
                .headers(Map.of(
                        "Content-Type", "application/json"))
                .body(new PactDslJsonBody()
                        .integerType("id", 42L)
                        .stringType("title", "Clean Code"))
                .toPact();
    }

    @Pact(
        consumer = "CheckoutWeb",
        provider = "InventoryService")
    public RequestResponsePact missingBook(
            PactDslWithProvider builder) {

        return builder
                .given("book 404 is absent")
                .uponReceiving("get a missing book")
                .path("/api/books/404")
                .method("GET")
                .headers(Map.of("Accept", "application/json"))
                .willRespondWith()
                .status(404)
                .toPact();
    }

    @Test
    @PactTestFor(pactMethod = "existingBook")
    void clientParsesRequiredFields(MockServer mock)
            throws Exception {

        InventoryClient client = new InventoryClient(
                URI.create(mock.getUrl()), new ObjectMapper());

        Optional<BookDto> result = client.find(42L);

        assertEquals(
                new BookDto(42L, "Clean Code"),
                result.orElseThrow());
    }

    @Test
    @PactTestFor(pactMethod = "missingBook")
    void clientTreats404AsAbsent(MockServer mock)
            throws Exception {

        InventoryClient client = new InventoryClient(
                URI.create(mock.getUrl()), new ObjectMapper());

        assertTrue(client.find(404L).isEmpty());
    }
}
~~~

**Hai JUnit @Test methods** và hai `@Pact` definitions.

### 12.1 Những dòng có ý nghĩa quan trọng nhất

- `@Pact(consumer="CheckoutWeb",provider="InventoryService")` đặt **đúng tên participant**; provider test/Broker phải dùng y hệt.
- `given(...)` đặt state provider cần setup, không phải consumer tự tạo database.
- `uponReceiving(...)` là mô tả interaction để đọc debug.
- `path`/`method`/`headers` mô tả request consumer được phép/cần gửi.
- `status`/`Content-Type`/`PactDslJsonBody` mô tả response consumer cần.
- `integerType("id",42L)` và `stringType("title","Clean Code")` yêu cầu đúng JSON types, không khóa mọi trường khác.
- `@PactTestFor(pactMethod=...)` đảm bảo mỗi test dùng đúng definition, không tùy ý chọn Pact đầu tiên.
- `MockServer` injection cung cấp URL/port test, không cần mở server production.

### 12.2 Vì sao Pact phải được tạo từ consumer test?

Nếu provider team tự viết một JSON contract mà consumer không dùng client thực khi test, hai bên có thể đồng ý với một contract *không liên quan tới code triển khai*. Gọi real `InventoryClient.find` là điểm cốt lõi: Pact test kiểm request thực mà client gửi, không chỉ một HTTP request được copy vào test.

### 12.3 Mối quan hệ với JUnit assertions

Pact mock kiểm request có khớp những interactions đã định nghĩa và có được thực thi không. Assertions của JUnit kiểm consumer xử lý response đúng nghĩa vụ. Cả hai cần PASS; chỉ gọi mock server bằng HTTP nhưng không assert deserialization/fallback là thiếu kiểm consumer behavior.

## 13. Pact artifact được sinh ra như thế nào?

Sau consumer tests, Pact JVM viết file theo cặp participant names trong `consumer/build/pacts`, ví dụ:

~~~text
consumer/build/pacts/CheckoutWeb-InventoryService.json
~~~

Nội dung **khái niệm được giản lược** dưới đây thể hiện hai interactions:

~~~json
{
  "consumer": {"name": "CheckoutWeb"},
  "provider": {"name": "InventoryService"},
  "interactions": [
    {
      "description": "get a book by ID",
      "providerStates": [{"name": "book 42 exists"}],
      "request": {
        "method": "GET",
        "path": "/api/books/42",
        "headers": {"Accept": "application/json"}
      },
      "response": {
        "status": 200,
        "headers": {"Content-Type": "application/json"},
        "body": {"id": 42, "title": "Clean Code"}
      }
    },
    {
      "description": "get a missing book",
      "providerStates": [{"name": "book 404 is absent"}],
      "request": {"method": "GET", "path": "/api/books/404"},
      "response": {"status": 404}
    }
  ]
}
~~~

**Đây không phải pact file byte-for-byte thực tế.** Pact JVM còn ghi matching rules, metadata/spec version và có thể format/headers khác. **Không chép JSON rút gọn này làm input provider test**; hãy dùng file generated bởi consumer suite.

### 13.1 Generated contract là artifact của một version consumer

Trong CI consumer, gắn Pact file với commit SHA/build version không thay đổi. File này là **output của consumer test version**, không phải một API contract global cố định tồn tại ngoài lịch sử phiên bản.

Khi consumer thay đổi request/response expectation, Pact content version thay đổi; Broker cần biết consumer version/branch nào đã publish Pact đó.

### 13.2 Đừng merge stale Pact files bừa bãi

Pact JVM có thể merge interactions vào Pact file đã tồn tại tùy writer settings. Với CI, nên chạy trong clean workspace hoặc cấu hình overwrite phù hợp để không giữ interaction đã xóa khỏi consumer code. Không tự xóa các contract của consumer versions **đã deploy** khỏi Broker; chúng cần được provider hỗ trợ đến khi những versions đó hết hoạt động.

## 14. Provider Spring Boot application: InventoryApplication.java

File `provider/src/main/java/example/provider/InventoryApplication.java`:

~~~java
package example.provider;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

Root package `example.provider` scan controller và catalog ở cùng package. Pact test sẽ khởi động embedded HTTP server trên random port để verify **real Spring MVC response**.

## 15. Provider model: BookDto.java

File `provider/src/main/java/example/provider/BookDto.java`:

~~~java
package example.provider;

public record BookDto(long id, String title) {
}
~~~

Đây là model provider độc lập với BookDto phía consumer. **Không chia sẻ cùng một Java DTO jar giữa hai services chỉ để test**, vì việc dùng chung model có thể che incompatibility khi thay đổi schema: một thay đổi sẽ compile đồng thời cả hai dù production versions đang chạy khác nhau.

Hai DTOs trông giống nhau trong ví dụ vì chúng cần mô tả cùng HTTP payload, nhưng source code/ownership tách biệt.

## 16. Provider in-memory state: BookCatalog.java

File `provider/src/main/java/example/provider/BookCatalog.java`:

~~~java
package example.provider;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Repository;

@Repository
public class BookCatalog {

    private final ConcurrentMap<Long, BookDto> books =
            new ConcurrentHashMap<>();

    public Optional<BookDto> find(long id) {
        return Optional.ofNullable(books.get(id));
    }

    public void clear() {
        books.clear();
    }

    public void put(BookDto book) {
        books.put(book.id(), book);
    }
}
~~~

Catalog chỉ phục vụ mini-project. Trong production có thể thay bằng JPA repository, query theo tenant, cache hoặc remote service. Provider state handlers có trách nhiệm reset/seed vào **đúng source of truth** mà HTTP controller thực dùng.

### 16.1 Vì sao dùng state setup thay hardcoded data trong controller?

Nếu controller code cứng luôn trả Book("Clean Code") chỉ để Pact PASS, provider verification sẽ không kiểm actual service/repository wiring. State setup ở test hỗ trợ cả integration slice và cho phép provider implementation phát triển độc lập.

## 17. Provider HTTP controller: BookController.java

File `provider/src/main/java/example/provider/BookController.java`:

~~~java
package example.provider;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookCatalog catalog;

    public BookController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> find(@PathVariable long id) {

        BookDto book = catalog.find(id).orElse(null);

        if (book != null) {
            return ResponseEntity.ok(book);
        }

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "BOOK_NOT_FOUND"));
    }
}
~~~

Endpoint trả:

- Book 42 tồn tại: `200`, JSON chứa `id` và `title`.
- Book 404 không tồn tại: `404`, JSON error body tùy provider.

Consumer Pact kiểm 404 status, **không** khóa chính xác error body vì client trả Optional.empty mà không parse field `code`. Nếu CheckoutWeb trong tương lai đọc `code` để hiển thị thông báo khác nhau, consumer phải thêm matcher/expectation phù hợp vào Pact.

## 18. Provider verification: InventoryProviderPactTest.java

File `provider/src/test/java/example/provider/InventoryProviderPactTest.java`:

~~~java
package example.provider;

import au.com.dius.pact.provider.junitsupport.Provider;
import au.com.dius.pact.provider.junitsupport.State;
import au.com.dius.pact.provider.junitsupport.loader.PactFolder;
import au.com.dius.pact.provider.junit5.PactVerificationContext;
import au.com.dius.pact.provider.junit5.PactVerificationInvocationContextProvider;
import au.com.dius.pact.provider.junit5.HttpTestTarget;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestTemplate;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@Provider("InventoryService")
@PactFolder("../consumer/build/pacts")
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InventoryProviderPactTest {

    @LocalServerPort int port;

    @Autowired BookCatalog catalog;

    @BeforeEach
    void beforeEachInteraction(PactVerificationContext context) {
        context.setTarget(new HttpTestTarget("localhost", port));
    }

    @State("book 42 exists")
    void bookExists() {
        catalog.clear();
        catalog.put(new BookDto(42L, "Clean Code"));
    }

    @State("book 404 is absent")
    void missingBook() {
        catalog.clear();
    }

    @TestTemplate
    @ExtendWith(PactVerificationInvocationContextProvider.class)
    void verifyEachConsumerInteraction(
            PactVerificationContext context) {
        context.verifyInteraction();
    }
}
~~~

Đây là **một JUnit @TestTemplate**, Pact extension tạo **một verification invocation cho mỗi interaction** có trong Pact file (dự kiến hai invocations từ consumer demo).

### 18.1 Vai trò các annotations

- `@Provider("InventoryService")`: tên provider phải khớp Pact.
- `@PactFolder("../consumer/build/pacts")`: dùng Pact artifact consumer sinh ra. Trong Gradle demo, path resolve từ `provider` project working directory.
- `@SpringBootTest(RANDOM_PORT)`: chạy Spring Boot HTTP server thật, không mock response bằng tay.
- `@LocalServerPort`: truyền dynamic port cho verifier qua `HttpTestTarget`.
- `@BeforeEach`: cài target trước mỗi interaction verification, đúng Pact JUnit5 lifecycle.
- `@State("book 42 exists")`: tạo dữ liệu cho success interaction.
- `@State("book 404 is absent")`: xóa dữ liệu cho not-found interaction.
- `@TestTemplate` và `PactVerificationInvocationContextProvider`: Pact phát request lên provider, so sánh status/headers/body với consumer Pact.
- `context.verifyInteraction()`: thực sự chạy verifier, không chỉ dựng test context.

### 18.2 Bài test phải thất bại khi thiếu Pact

Pact provider JUnit5 thường báo lỗi khi không tìm thấy Pact để verify. **Đừng** dùng `@IgnoreNoPactsToVerify` chỉ để pipeline xanh nếu không có Pact; nó che lỗi artifact delivery/Broker selector. Giữ failure để CI phát hiện thư mục trống, sai provider name, sai path hoặc consumer test chưa chạy.

### 18.3 Vì sao provider state phải độc lập và reset?

Interaction 404 không được phụ thuộc test success đã chạy trước hay sau. `catalog.clear()` trong mỗi `@State` giúp deterministic. Nếu provider dùng DB, chuẩn bị fixtures có cleanup và transaction visibility đúng; Pact verification gửi HTTP tới server thread khác với test thread.

**Không dựa vào `@Transactional` rollback trên test thread** để dọn writes trong HTTP server thread: transaction boundary khác. Dùng DB test độc lập, setup/teardown rõ hoặc Testcontainers.

## 19. Chạy local và đọc đúng kết quả

Từ root của multi-project với Gradle wrapper:

~~~bash
./gradlew :consumer:clean :provider:clean :provider:test
~~~

Vì provider task phụ thuộc consumer task:

~~~text
:consumer:compileJava
:consumer:compileTestJava
:consumer:test              -> 2 consumer @Test methods
                             -> generated Pact JSON
:provider:compileJava
:provider:compileTestJava
:provider:test              -> Pact @TestTemplate
                             -> expected 2 interaction invocations
~~~

Sơ đồ thứ tự ở trên là **diễn giải task dependency**, không phải stdout Gradle được chụp lại. Gradle có thể interleave compile tasks; điều bảo đảm là `:consumer:test` hoàn tất trước `:provider:test` chạy.

Expected behavior:

| Tương tác | Consumer test | Provider verification |
| --- | --- | --- |
| Book 42 exists | Mock GET 200; client parse BookDto(42,"Clean Code") | @State seed book 42, HTTP 200 với id/title phù hợp |
| Book 404 absent | Mock GET 404; client trả Optional.empty | @State clear catalog, HTTP 404 |
| Provider đổi `title` thành `name` | Consumer mock vẫn PASS theo Pact cũ | Provider verification **FAIL** vì thiếu field title |
| Provider bỏ endpoint | Consumer mock vẫn PASS | Provider verification **FAIL** do status/path |
| Provider thêm field `stock` | Consumer vẫn PASS | Provider thường PASS nếu Pact không ràng buộc field dư |

Chưa có build/test execution thực tế trong văn bản này; những PASS/FAIL trên là **kết quả mong đợi theo contract definition**. Khi chạy thật, xem:

~~~text
consumer/build/reports/tests/test/index.html
provider/build/reports/tests/test/index.html
consumer/build/pacts/
~~~

### 19.1 Nếu provider verifier fail

Đọc từng nhóm sai lệch:

1. Pact path hoặc provider name không khớp.
2. Provider state callback không tồn tại hoặc seed sai.
3. Request method/path/header không khớp controller mapping.
4. Status 200 vs 404/401/500 khác contract.
5. Response Content-Type khác format được consumer kỳ vọng.
6. Body thiếu field `title`, `id` sai kiểu hoặc serialization khác.
7. Test target trỏ sai localhost port; server chưa ready.
8. Pact version/spec/tooling không tương thích.
9. Test state bị rò giữa interactions.
10. Request bị security filter chặn hoặc authorization chưa setup.

**Không** sửa Pact file generated bằng tay để làm provider test PASS; nó thuộc consumer. Provider có thể sửa code/state nếu tương thích, hoặc thương lượng thay đổi yêu cầu với consumer team.

## 20. Consumer contracts phải nhỏ, cụ thể và có ý nghĩa

Một anti-pattern là đưa **toàn bộ response JSON** của provider vào Pact với mọi field, value và array order chính xác dù consumer chỉ đọc `title`.

Ví dụ một provider response có:

~~~json
{
  "id": 42,
  "title": "Clean Code",
  "description": "...",
  "stock": 6,
  "warehouse": "HCM-01",
  "debugVersion": "abcdef",
  "timestamp": "2026-11-08T00:00:00Z"
}
~~~

Nếu CheckoutWeb chỉ dùng `id` và `title`, Pact chỉ nên yêu cầu các fields này và type/pattern phù hợp; việc đóng băng `stock=6`, debugVersion hoặc timestamp làm provider build fail không có lý do nghiệp vụ.

### 20.1 Exact values và matchers

| Expectation | Matcher phù hợp | Lý do |
| --- | --- | --- |
| URL cụ thể cần gọi | Exact method/path hoặc regex có chủ ý | Bảo đảm consumer gọi đúng resource |
| ID JSON | `integerType("id",42L)` | Contract cần number, không buộc ID luôn 42 |
| Title JSON | `stringType("title","Clean Code")` | Consumer cần chuỗi |
| Enum/status | Exact allowed value hoặc regex khi hợp lệ | Phù hợp business branching |
| Timestamp | Datetime matcher nếu consumer parse format | Không khóa giá trị timestamp từ fixture |
| Array products | Type matcher + minimum size khi consumer cần | Không khóa order/size nếu không cần |
| Optional field | Không yêu cầu nếu consumer không cần; có test fallback nếu dùng | Tránh over-specification |

**Dùng matcher rộng quá cũng nguy hiểm.** Nếu client cần mã đơn hàng dạng UUID nhưng contract chỉ yêu cầu “chuỗi bất kỳ”, provider có thể trả `"abc"` làm client downstream lỗi. Kỳ vọng phải đúng invariant mà consumer thực sự phụ thuộc.

### 20.2 Không biến mock thành giả sự thật

Mock server có thể đáp ứng contract rất hoàn hảo dù provider hiện chưa code endpoint. Consumer test PASS cho phép consumer team xây tính năng **trước**, nhưng việc deploy an toàn phải đợi provider verification success và `can-i-deploy` đúng environment. Nếu bỏ gate, CDC sẽ chỉ còn “mock tests màu xanh”.

## 21. Cơ chế phát triển độc lập: expand, migrate, contract

Giả sử provider muốn đổi `title` thành `displayName`.

**Cách phá vỡ tương thích:**

~~~text
InventoryService v1 -> {"title":"Clean Code"}
InventoryService v2 -> {"displayName":"Clean Code"}
CheckoutWeb v1 vẫn đọc title -> bị hỏng
~~~

Cách làm an toàn:

1. **Expand:** Provider v2 trả cả `title` lẫn `displayName`. Consumer Pact cũ vẫn PASS.
2. **Migrate:** CheckoutWeb v2 cập nhật code đọc `displayName`, viết Pact mới, provider verify PASS. Deploy CheckoutWeb v2, ghi deployment lên Broker.
3. **Observe:** Xác nhận không còn consumer versions đang hoạt động phụ thuộc `title` (gồm mobile/partners/old branches nếu cần).
4. **Contract:** Provider v3 mới xóa `title`; chỉ triển khai nếu `can-i-deploy` với versions deployed còn lại an toàn.

~~~text
time --->
Provider v1: title
Provider v2: title + displayName   (both consumers work)
Consumer v2: uses displayName
Provider v3: displayName only      (remove after old consumers retire)
~~~

**Không đồng nhất semver MAJOR bump với bảo đảm an toàn.** Một API v2 có breaking change vẫn có thể làm các consumers đang triển khai hỏng nếu route cùng endpoint và không duy trì v1 semantics; Broker verification/can-i-deploy mới cung cấp bằng chứng với từng version.

### 21.1 Những thay đổi thường compatible và incompatible

| Provider change | Khả năng tương thích | Lưu ý |
| --- | --- | --- |
| Thêm JSON field không được consumer dùng | Thường compatible | Với consumers strict deserializers có thể khác; phải test thật |
| Giữ field nhưng thay giá trị fixture | Thường compatible khi matchers cho phép | Không phá enum/business rules |
| Xóa field đang được dùng | Breaking | Pact sẽ fail nếu field required |
| Rename path hoặc HTTP method | Breaking | Consumer requests cũ sai |
| Đổi status 404 sang 200 | Có thể breaking | Consumer branch theo status |
| Đổi string sang number | Breaking với consumer typed JSON | Matcher phát hiện |
| Siết auth yêu cầu header mới | Có thể breaking | Consumer contract cũ không gửi header |
| Thêm required request field | Breaking với old consumers | Expand API để accept cả old/new |
| Thay ý nghĩa field mà giữ type | Breaking về mặt ngữ nghĩa | Pact type matcher **không tự phát hiện** |
| Đổi sort/order/page defaults | Có thể breaking | Contract nếu consumer phụ thuộc order/pagination |

CDC là contract về **interactions**, không tự bảo đảm các ý nghĩa sâu hơn như số dư tiền, VAT, pricing rules nếu consumer tests không viết assertions phù hợp.

## 22. Pact Broker: source of truth của versions và verification

Local demo chỉ truyền Pact qua một thư mục build. Trong doanh nghiệp, các repos/teams độc lập không nên copy thủ công JSON qua Slack/commit vào provider repo. Dùng Pact Broker hoặc dịch vụ tương đương để giữ:

- Consumer participant/version/branch và pact contents.
- Provider participant/version/branch và kết quả verify.
- Chuyển trạng thái deploy/release theo environment.
- Matrix biểu diễn consumer version nào tương thích provider version nào.
- API/CLI `can-i-deploy` quyết định deploy với các versions **đang ở** môi trường đích.
- Webhooks kích hoạt provider verification khi contract mới được publish.

Sơ đồ:

~~~text
CheckoutWeb CI              Pact Broker                InventoryService CI
  |                             |                              |
  |--- publish pact (cSHA) ---->|                              |
  |                             |---- webhook new pact ------->|
  |                             |                              |
  |                             |<--- provider verification ---|
  |                             |     (pSHA, PASS/FAIL)         |
  |                             |                              |
  |--- can-i-deploy cSHA ------>|                              |
  |<-- YES / NO --------------- |                              |
  |--- deployment --------------|                              |
  |--- record-deployment ------>|                              |
  |                             |                              |
  |                             |<--- can-i-deploy pSHA --------|
  |                             |---- YES / NO ---------------->|
  |                             |<--- record provider deploy ---|
~~~

**Phải publish verification results với đúng provider version**. Nếu provider test local dùng `@PactFolder` mà không có Broker source/link, Broker không tự có kết quả dù JUnit PASS. Trong CI chuyển test source sang `@PactBroker`/selectors và cấu hình publish results.

## 23. Can I Deploy và deployment matrix

Pact Broker cung cấp ma trận tương thích theo versions.

Giả sử đang ở production:

| Participant | Đã deploy | Pact/verification liên quan |
| --- | --- | --- |
| CheckoutWeb | `checkout-a1` | Cần `title` |
| BillingService | `billing-b7` | Cần `price` |
| InventoryService | `inventory-p9` | Đã verify cả hai contracts |

Team InventoryService chuẩn bị `inventory-p10`. Pipeline provider cần xác minh **các Pact của consumers deployed**; nếu p10 làm hỏng CheckoutWeb a1, `can-i-deploy` phải trả NO, dù provider unit tests xanh.

Đây là ví dụ ma trận **minh họa**, không phải trạng thái Broker thật của hệ thống nào.

### 23.1 Lệnh can-i-deploy

Ví dụ từ CI đã có Pact Broker CLI và credentials dưới dạng environment:

~~~bash
pact-broker can-i-deploy \
  --pacticipant InventoryService \
  --version "$CI_COMMIT_SHA" \
  --to-environment production
~~~

Sau khi triển khai thành công:

~~~bash
pact-broker record-deployment \
  --pacticipant InventoryService \
  --version "$CI_COMMIT_SHA" \
  --environment production
~~~

Đối với CheckoutWeb, thay participant tương ứng. Tùy môi trường sử dụng PactFlow/OSS Broker và authentication setup, CLI còn cần `--broker-base-url`/`--broker-token` hoặc environment variables. **Không** hardcode token trong source/README hay in nó ra CI logs.

### 23.2 Thứ tự hành động là một contract release

1. Build/test version v.
2. Publish Pact hoặc provider verification results gắn v.
3. Chờ những verifications cần thiết được công bố.
4. Chạy `can-i-deploy` cho **đúng v** và **đúng environment**.
5. Chỉ deploy khi trả YES.
6. Sau deploy thành công, gọi `record-deployment` để Matrix có versions đang chạy mới nhất.

Nếu bỏ bước 6, lần deploy sau có thể so với **versions cũ** và đưa ra quyết định sai. Nếu can-i-deploy chạy cho `latest` thay vì immutable SHA, một build mới xuất hiện có thể khiến gate kiểm **sai artifact**.

### 23.3 Không “chữa” NO bằng cách đổi môi trường

Một provider candidate không tương thích production consumer sẽ không trở thành compatible chỉ vì chạy can-i-deploy với environment khác. Khi NO, kiểm pact verification cụ thể, giữ backward compatibility hoặc phối hợp migration. Đừng đổi selector sang `main branch only` và bỏ các phiên bản consumer đang chạy để làm pipeline xanh.

## 24. Pending Pacts và WIP Pacts

Hai khái niệm dễ nhầm:

**Pending Pact** là một thuộc tính động của pact verification trong provider pipeline. Khi consumer mới publish một expectation mà provider chưa hỗ trợ, verification có thể **FAIL** nhưng không làm hỏng main provider build, nhằm tránh để consumer branch chưa deploy chặn đội provider triển khai những thay đổi không liên quan.

**Work-in-progress (WIP) Pact** là một pact mới chưa được provider branch chấp nhận, được Broker tự đưa vào danh sách verify nếu cấu hình thời điểm WIP/selector phù hợp; nó giúp provider sớm nhìn thấy kỳ vọng mới mà không phải mỗi lần cập nhật selector thủ công.

| Thuộc tính | Pending | WIP |
| --- | --- | --- |
| Là gì? | Trạng thái của một Pact khi được verify | Cách chọn thêm Pact đang phát triển |
| Mục đích | Không block provider main vì kỳ vọng mới chưa được chấp nhận | Tự verify hợp đồng mới |
| Provider verification có được ghi FAIL không? | **Có**, vẫn ghi kết quả thật | **Có**, nếu thực sự không tương thích |
| Consumer mới có deploy được nếu verify FAIL? | **Không**, can-i-deploy vẫn cần compatibility | Không |
| Có thay thế can-i-deploy không? | Không | Không |

### 24.1 Pending không biến FAIL thành PASS

Nếu consumer v2 yêu cầu `availability` mà provider v1 chưa trả:

~~~text
Provider verifies new Pact:
    interaction FAIL
    Pact Broker records FAILED verification
    provider main build MAY remain green (pending policy)

CheckoutWeb v2:
    can-i-deploy -> NO until provider supports contract
~~~

Đó là behavior **có chủ đích**, không phải bug của pending pacts. Provider vẫn cần bổ sung field; consumer v2 vẫn bị chặn deploy nếu chưa tương thích môi trường đích.

### 24.2 Cấu hình phải có branch/version metadata

Để pending/WIP hoạt động đúng:

- Consumer publish Pact với **consumer version** và **branch**.
- Provider publish verification với **provider version** và **branch**.
- Định nghĩa main branch cho participants.
- Chọn pacts đang deployed/released và pacts thuộc main branch cần thiết.
- Bật pending và WIP theo Pact Broker feature/version phù hợp.
- Không nhầm provider-triggered verification webhook với main provider pipeline: pending có vai trò khác nhau giữa hai workflows.
- Chạy can-i-deploy ở release gate bất kể main provider build có xanh do pending.

### 24.3 Không dùng “pending everything” để che breaking change

Sau khi provider đã verify thành công một Pact của deployed consumer, việc provider về sau làm hỏng Pact này **không còn là thay đổi mới chưa chấp nhận**. Provider pipeline phải phát hiện và chặn breaking change. Pending được thiết kế để bảo vệ đường nâng cấp độc lập, **không hợp thức hóa regression**.

## 25. Provider verification từ Broker trong CI

Local demo dùng:

~~~java
@Provider("InventoryService")
@PactFolder("../consumer/build/pacts")
~~~

Trong provider CI khi repos độc lập, thay `@PactFolder` bằng một nguồn Pact Broker, ví dụ khai báo `@PactBroker` và selectors phù hợp theo Pact JVM version:

~~~java
@Provider("InventoryService")
@PactBroker
class InventoryBrokerVerificationTest {
    // @TestTemplate, @State, HttpTestTarget
    // Tương tự InventoryProviderPactTest.
}
~~~

**Đây là snippet định hướng, không phải file đầy đủ trong mini-project.** Cấu hình Broker host/scheme/auth/selectors cần áp dụng theo Pact JVM 4.6.x docs và pipeline thật. Không đăng ký cùng một provider test vừa dùng `@PactFolder` vừa dùng Broker source tùy tiện; chọn đúng source theo môi trường.

Pact JVM provider JUnit5 hỗ trợ publish verification results khi các system properties được đặt trên **test JVM**. Ví dụ Gradle provider:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()

    systemProperty 'pact.provider.version',
            System.getenv('CI_COMMIT_SHA') ?: 'local'

    systemProperty 'pact.provider.branch',
            System.getenv('CI_COMMIT_BRANCH') ?: 'local'

    systemProperty 'pact.verifier.publishResults',
            System.getenv('CI') == 'true'
                    ? 'true' : 'false'
}
~~~

Đây là **mẫu CI cho mode Broker**, không phải thay thế trực tiếp build.gradle local demo khi test đang dùng PactFolder. Nhiều build tools chạy tests trong JVM riêng; đặt `-Dpact.provider.version` trên Gradle CLI **không luôn tự được forward vào test JVM**, nên cấu hình trong `Test` task như trên.

Nếu cần pending, WIP, provider version selectors, Broker token, dùng cơ chế config chính thức của Pact/CI. Không publish kết quả `local` lên Broker production như thể đó là một deployable artifact bất biến.

## 26. Pipeline độc lập điển hình

### 26.1 Consumer CI

~~~text
checkout feature branch
      |
      +-- compile + unit tests
      |
      +-- Pact consumer tests using MockServer
      |
      +-- publish immutable Pact (consumer SHA + branch)
      |
      +-- trigger provider verification via Broker webhook
      |
      +-- await required verification results / can-i-deploy
      |
      +-- deploy CheckoutWeb SHA
      |
      +-- record-deployment
~~~

Consumer không cần chờ provider deploy để **viết code và chạy unit/Pact mock tests**. Nhưng bản consumer mới **không** nên vào môi trường đang chạy provider không đáp ứng Pact.

### 26.2 Provider CI

~~~text
inventory feature branch
      |
      +-- unit/integration tests
      |
      +-- fetch relevant deployed/main/WIP pacts
      |
      +-- setup provider states and verify real HTTP endpoints
      |
      +-- publish verification result (provider SHA + branch)
      |
      +-- protect main with pending-pacts semantics
      |
      +-- can-i-deploy against target environment
      |
      +-- deploy InventoryService SHA
      |
      +-- record-deployment
~~~

Provider phải verify **Pacts của mọi consumer versions cần được hỗ trợ**, không chỉ Pact mới nhất của một consumer.

### 26.3 Khi một team có nhiều CI workflows

Có thể có provider-changed workflow, consumer-pact-published webhook workflow và deployment workflow. Cần đúng trách nhiệm:

- Webhook verifica­tion có thể FAIL vì hợp đồng mới, cho team consumer biết provider chưa hỗ trợ.
- Provider main branch build được pending tránh bị một Pact mới chưa deploy làm đỏ.
- Deployment gate vẫn kiểm ma trận thật với môi trường đích.
- Báo cáo verification phải gửi đúng provider version/branch.
- Không coi việc chưa có kết quả verify là PASS hoặc giả định pacts không tồn tại.

## 27. Khi có nhiều consumer khác nhau

CheckoutWeb đọc `title`, BillingService đọc `price`, MobileApp đọc `stock`. Provider muốn thay đổi response. Pact Broker lưu nhiều Pact contents và versions.

Ví dụ:

| Consumer đang deploy | Contract đang cần | Provider cần giữ |
| --- | --- | --- |
| CheckoutWeb a1 | GET /books/42 → id,title | id,title |
| BillingService b7 | GET /pricing/42 → currency,amount | currency,amount |
| MobileApp m3 | GET /books/42 → stock | stock |
| CheckoutWeb a2 chưa deploy | GET /books/42 → displayName | displayName trước khi a2 deploy |

Nếu InventoryService v2 thêm displayName nhưng vẫn giữ title/stock/price, nó có thể compatible với tất cả. Khi v3 xóa title, cần biết a1 còn trong production không.

**Không xóa hỗ trợ cho mobile clients đã cài trên thiết bị chỉ vì app-store version mới nhất đã phát hành.** Với client ngoài tổ chức, active versions có thể khó đo; kết hợp telemetry, deprecation window, API versioning và consumer registration thay vì chỉ nhìn branch HEAD.

## 28. Negative contracts: lỗi cũng là API

Một CDC suite chỉ có HTTP 200 sẽ bỏ qua nhiều breakages:

- Provider đổi 404 thành 200 trả body `{"error":"not found"}`.
- Unauthorized request trả 500 thay vì 401/403.
- Validation error đổi JSON schema khiến consumer parse fail.
- Rate-limit 429 không còn `Retry-After` mà consumer dựa vào.
- Provider đổi lỗi timeout thành response 200 với data không đầy đủ.
- Header `Content-Type` đổi thành XML khi client chỉ biết JSON.

### 28.1 Khi nào kiểm error body?

Nếu consumer hiển thị message dựa vào field `code`, đó là contract requirement:

~~~json
{
  "code": "BOOK_NOT_FOUND",
  "message": "Book does not exist"
}
~~~

Nếu consumer chỉ dùng status 404 để trả Optional.empty, ép mọi chữ trong `message` phải chính xác sẽ over-specify. Hãy viết những assertions đúng **cách consumer hành xử**.

### 28.2 401/403/429 cũng cần provider states

Ví dụ `given("token missing")`, `given("user lacks permission")`, `given("rate limit exceeded")` có thể cần provider state handler/token fixture. Nhưng **đừng** hardcode token production, user passwords hoặc secrets trong Pact files; dùng dummy/test credentials, token injector hoặc request modification hook phù hợp với provider verifier.

## 29. Security boundary: contract test không chứng minh auth an toàn

Nếu consumer test gửi dummy header:

~~~http
Authorization: Bearer test-token
~~~

và Pact mock chấp nhận, điều đó **không** chứng minh production JWT được xác minh chữ ký, issuer, audience hoặc expiration. Provider verification có thể cấu hình test authentication để qua filters, nhưng để kiểm **security** phải có tests riêng cho:

- Authorized vs unauthorized status.
- Role/scope/tenant authorization.
- Token parsing/verification trên real security filter chain.
- CSRF khi dùng browser/session cookies.
- Secrets rotation và mTLS nếu service-to-service yêu cầu.
- Retry/circuit breaker không leak token vào logs.

**Không lưu token thật vào Pact JSON/Broker**. Nếu authentication header có thời hạn ngắn, dùng verifier hook thay đổi request cho test runtime theo docs, ghi rõ phần nào là contract và phần nào là credential injection.

## 30. Contract testing là một phần của resilience, không thay nó

CDC xác minh request/response **shape và một số semantics**, không tự chứng minh hệ thống vẫn hoạt động khi:

- Network timeout hoặc DNS lỗi.
- Provider 500/503 khi quá tải.
- Retry tạo side effects trùng lặp.
- Circuit breaker OPEN/HALF_OPEN.
- Event đến sai thứ tự hoặc bị lặp.
- Partial outage/zone failover.
- Serialization thành công nhưng dữ liệu stale.
- Database transaction rollback sau khi response đã được publish.

| Vấn đề | Test/điều khiển bổ sung |
| --- | --- |
| HTTP connect/read timeout | Client integration test với faulting server/network proxy |
| Retry/backoff | Test chính xác request count và retry conditions |
| Idempotency | Duplicate request/payment/event tests |
| Circuit breaker | State transition + fallback tests |
| Authentication | Security integration tests |
| DB transaction | Repository/transaction integration |
| 99p latency/SLO | Load/performance tests |
| Provider availability | Probes/monitoring/failover |
| Async event delivery | Messaging integration + CDC message tests |

**Contract PASS là điều kiện tương thích, không phải cam kết uptime.** Trong production, kết hợp CDC với chaos, observability, retries có kiểm soát và data consistency tests.

### 30.1 Đặc biệt với POST/commands

Nếu consumer contract mô tả `POST /orders` trả 201, nó chưa chứng minh hai retries không tạo hai orders. Với commands có side effects, contract nên bao gồm idempotency key/header/status khi consumer thực sự phụ thuộc, và có test implementation xử lý duplicate cùng key đúng nghĩa vụ.

## 31. API changes và schema evolution trong message/event-based systems

CDC không chỉ cho HTTP. Với Kafka/RabbitMQ/event-driven integrations:

- **Producer** phát event/message.
- **Consumer** nhận và parse message.
- Contract mô tả message metadata, headers và body/fields consumer cần.
- Provider verification kiểm producer có khả năng tạo message phù hợp từ một provider state.
- Schema Registry (Avro/Protobuf/JSON Schema) còn kiểm schema compatibility theo version; CDC kiểm nhu cầu cụ thể của consumer.

Ví dụ event:

~~~json
{
  "eventType": "BookStockChanged",
  "version": 2,
  "bookId": 42,
  "available": true
}
~~~

Nếu consumer chỉ cần `bookId` và `available`, Pact matcher có thể yêu cầu đúng fields/types. Nhưng **cần test thêm**:

- Event có được publish trong transaction/outbox phù hợp không?
- Duplicate/out-of-order events có được handler chấp nhận không?
- Partition key có giữ ordering khi cần?
- Retry/DLQ/poison-message policy có đúng không?
- Consumer có idempotent khi replay không?

Pact JVM hỗ trợ **asynchronous message interactions**; API V4/messages khác HTTP RequestResponsePact. **Không copy nguyên `@PactTestFor` HTTP sample cho Kafka rồi mong chạy**, mà chọn correct message DSL/target/plugin, test handler/producer ở tầng phù hợp và thêm broker integration tests.

## 32. Spring Cloud Contract: lựa chọn khác trong Spring ecosystem

Spring Cloud Contract (SCC) là một lựa chọn phổ biến khi cả provider/consumer đều trong Spring stack.

So sánh:

| Nhu cầu | Pact JVM + Broker | Spring Cloud Contract |
| --- | --- | --- |
| Consumer mô tả interaction từ code đang dùng | Rất phù hợp | Có CDC workflow với contracts/stubs |
| Provider tự động verify contracts | JUnit Pact verifier | Generated tests từ contract DSL |
| Consumer dùng stub không cần provider chạy | Pact MockServer | Stub Runner/WireMock-generated stubs |
| Quản lý versions và deploy compatibility matrix | Pact Broker built-in | Cần quản trị metadata/release gate theo workflow |
| Multi-language consumers | Pact ecosystem nhiều SDKs | Tập trung Spring/JVM, cũng có hỗ trợ khác |
| Async messages | Pact message interactions/plugins | SCC hỗ trợ messaging contracts theo integration |
| Kiểm toàn bộ service topology | Không | Không |

Ví dụ Spring Cloud Contract DSL:

~~~groovy
org.springframework.cloud.contract.spec.Contract.make {
    description("Read an existing book")
    request {
        method GET()
        url("/api/books/42")
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            title: "Clean Code"
        )
    }
}
~~~

Đây là **minh họa SCC DSL**, không phải file chạy trong Pact mini-project. SCC version phải tương thích với Spring Boot/Spring Cloud BOM mà repo sử dụng. Không trộn Pact/SCC schemas mà không có chiến lược source-of-truth rõ: nếu mỗi tool duy trì một hợp đồng khác nhau, có thể tạo drift.

### 32.1 Chọn gì cho team?

Nếu cần **cross-team, multi-repo, multi-language và independent deployment gates** theo từng consumer/provider version, Pact Broker matrix là lợi thế rõ. Nếu provider là Spring app và muốn contract DSL + auto-generated provider tests + publish stubs cho consumer, Spring Cloud Contract có thể phù hợp.

Không cần chọn cả hai cho cùng một integration chỉ vì có thể; một hệ thống rõ ownership/version/CI feedback có giá trị hơn hai bộ contract mâu thuẫn.

## 33. Test pyramid: không dùng contract test cho mọi thứ

~~~text
                Few E2E tests
             /------------------\
            /   End-to-end       \
           /----------------------\
          / Contract verification  \
         /--------------------------\
        / Component/integration      \
       /------------------------------\
      /  Many unit/service tests       \
     /----------------------------------\
~~~

Phân công hợp lý:

- Unit: business rules, DTO parsing, fallback, mapping.
- Consumer Pact: real client request + expected response behavior.
- Provider Pact verification: real provider endpoint/state đáp ứng Pact.
- Integration: database, transaction, authentication, Redis, message broker và network-specific failures.
- End-to-end: một vài customer journeys với real infrastructure, không chạy mọi combination mỗi commit.
- Production monitoring: business metrics, traces và canary/rollback khi assumptions thay đổi.

Pact giúp giảm nhu cầu E2E giữa mọi cặp service, **không loại bỏ E2E hoàn toàn**. Một hợp đồng hợp lệ vẫn có thể đi qua service discovery/routing hoặc environment configuration sai ở staging.

## 34. Tình huống team độc lập và quyết định release

### 34.1 Consumer muốn dùng field mới trước provider

CheckoutWeb v2 viết Pact cần `displayName`, consumer test PASS trên mock; provider v1 verify FAIL. Broker ghi failure, consumer `can-i-deploy` NO. Team provider có thể ship bản v2 thêm field. Sau khi provider verification thành công và v2 được deploy (theo trình tự an toàn), consumer v2 có thể ship.

### 34.2 Provider cần đổi database

InventoryService đổi từ Postgres sang DynamoDB nhưng external response vẫn giữ `id`/`title`/404. Provider Pact verification PASS; consumer không cần đổi hoặc deploy đồng thời. Cần integration/data migration tests riêng, nhưng CDC cho biết API contract không đổi.

### 34.3 Provider bỏ field cũ

Provider không được xóa `title` chỉ vì code của CheckoutWeb main branch đã dùng `displayName`. Phải biết **CheckoutWeb versions đang deploy** và mọi consumers khác có đang dùng field cũ không. Pact Broker deployment records và can-i-deploy hỗ trợ đánh giá này.

### 34.4 Hai consumers cần error schema khác nhau

CheckoutWeb chỉ quan tâm status 404; MobileApp cần `code`. Provider có thể giữ status và thêm field `code`, tương thích với cả hai. Đừng ép CheckoutWeb kiểm chính xác error body nếu nó không dùng.

### 34.5 Contract đổi nhưng test provider không được kích hoạt

Consumer publish Pact mới nhưng webhook bị tắt hoặc provider selector sai; không có verification result. `can-i-deploy` phải xử lý trạng thái missing/unknown như **không đủ bằng chứng**, không lấy “consumer unit tests PASS” thay thế.

## 35. Quan sát contract failures trong CI và production

Các tín hiệu hữu ích:

| Tín hiệu | Vì sao cần |
| --- | --- |
| Consumer Pact version/branch | Biết kỳ vọng đến từ build nào |
| Provider version/branch verified | Biết implementation nào đã chạy verifier |
| Pact verification PASS/FAIL | Chặn regressions đúng tương tác |
| Pending/WIP label | Phân biệt yêu cầu mới với breakage đã chấp nhận |
| Broker matrix/can-i-deploy result | Quyết định deploy theo environment |
| Deployment/release records | Không so sánh với versions lỗi thời |
| Interaction mismatch | Path/method/header/status/body nào sai |
| Provider state failure | Fixture nào không setup được |
| CI webhook lag | Provider chưa verify vì job bị delay |
| Contract coverage | Những consumers/endpoints nào có/thiếu Pact |
| Runtime error rate by integration | Bắt lỗi về ngữ nghĩa/timing ngoài Pact |
| Correlation ID/traces | Theo dõi call thực giữa services |

Không publish secrets hoặc customer PII vào Pact examples. Dùng synthetic values và cleanup/test data. Với ephemeral test environments, có thể namespace provider state fixtures theo build ID để tránh race.

### 35.1 Khi provider verification fail: triage nhanh

1. Xác nhận consumer/provider participant names exact.
2. Xác nhận Pact content version và consumer branch/deployment selector.
3. Đọc interaction description và provider state.
4. Kiểm provider state callback setup dữ liệu đúng, không phụ thuộc thứ tự.
5. Kiểm status code, Accept/Content-Type headers.
6. Kiểm JSON fields/types/regex/array cardinality.
7. Kiểm provider service chạy đúng port và HTTP layer.
8. Kiểm security filters nếu 401/403 không nằm trong Pact.
9. Kiểm matcher over-specification vs real client requirement.
10. Chỉ sửa contract theo nhu cầu consumer code thật, không sửa để “green” bằng mọi giá.

## 36. Những sai lầm phổ biến

**1. Consumer test mock PASS được xem như provider compatible.**  
Sai: phải có provider verification trên real implementation.

**2. Provider tự viết Pact thay consumer.**  
Mất consumer-driven feedback. Contract nên xuất phát từ consumer code/test.

**3. Consumer test không gọi production client.**  
Dựng HTTP request thủ công có thể không khớp những gì app thực gửi.

**4. Pact test chỉ kiểm 200.**  
404/401/403/429 và validation/error paths có thể breaking.

**5. Khóa mọi field/giá trị trong response JSON.**  
Over-specification làm provider không thể evolve độc lập.

**6. Dùng matcher rộng đến mức bỏ qua business invariant.**  
`stringType` không kiểm UUID/enum/currency format; chọn matching rule đúng.

**7. Dùng shared DTO jar cho provider và consumer.**  
Compile đồng thời có thể che compatibility của các deploy versions khác nhau.

**8. Provider state callback không reset fixture.**  
Verification phụ thuộc thứ tự, flaky.

**9. Provider test trỏ sai port.**  
RANDOM_PORT phải đưa vào HttpTestTarget, không hardcode 8080.

**10. Không tìm thấy Pact nhưng test vẫn PASS.**  
Không suppress no-Pact verification failure khi bắt buộc có contract.

**11. Provider test chỉ dùng MockMvc fake toàn bộ business logic.**  
Có thể thiếu wiring/security/integration thực; chọn tầng verification phù hợp và bổ sung integration tests.

**12. Không publish provider verification results.**  
Broker không biết compatible dù JUnit local PASS.

**13. Không gửi provider version/branch.**  
Broker khó tính pending/matrix đúng, can-i-deploy thiếu bằng chứng.

**14. Không record-deployment sau deploy.**  
Broker so với versions cũ, release gates mất ý nghĩa.

**15. Dùng latest Pact không có version pin.**  
CI có thể verify sai content so với artifact đang deploy.

**16. Chỉ verify Pact consumer main branch.**  
Bỏ sót consumer versions đang chạy trong production.

**17. Thấy pending Pact mà tưởng verification thành công.**  
FAILED vẫn là FAILED; consumer vẫn bị can-i-deploy chặn.

**18. Cho WIP pacts block provider main do không bật pending.**  
Một contract mới chưa sẵn sàng có thể làm chậm provider release không liên quan.

**19. Xóa compatibility ngay khi consumer main đã đổi.**  
Phiên bản cũ đang deploy vẫn cần API cũ.

**20. Nhầm Pact Broker với source code registry.**  
Broker lưu Pact versions/verification/deployment matrix, không thay Git/CI artifacts.

**21. Bỏ authentication/security tests vì Pact chạy mock server.**  
Mock không kiểm signature/authorization thực.

**22. Cho rằng Pact bảo đảm retry/idempotency.**  
Contract shape không thay network/resilience tests.

**23. Chia sẻ database production để tạo provider states.**  
Nguy hiểm và không deterministic; dùng isolated test data.

**24. Không kiểm extra fields/strict clients.**  
Một consumer configured reject unknown properties có thể fail khi provider thêm field; consumer test/client phải kiểm behavior thật.

**25. Thay error semantics mà vẫn giữ schema.**  
Status 404 vs 200-with-error có thể breaking dù JSON “hợp lệ”.

**26. Không kiểm message ordering/duplication.**  
Message contracts không thay queue integration/idempotency tests.

**27. Team dọn Pact files của deployed versions.**  
Provider mất khả năng biết tương thích với old clients.

**28. Merge contract và code vào một release train vô điều kiện.**  
Mất lợi thế independent deployment; dùng publish/verify/gate phối hợp.

## 37. Quy trình triển khai CDC theo từng bước

1. Chọn integration quan trọng có hai teams/repos: ví dụ CheckoutWeb → InventoryService.
2. Xác định consumer thực sự dùng endpoint/status/headers/fields nào.
3. Viết consumer unit tests cho mapping/fallback riêng.
4. Viết Pact consumer test gọi real HTTP client vào Pact MockServer.
5. Sinh Pact artifact, inspect interaction và loại bỏ over-specification.
6. Publish Pact với immutable consumer version SHA và branch.
7. Provider đăng ký Pact source và `@State` fixture handlers đúng.
8. Provider verification chạy trên real endpoint hoặc layer phù hợp; publish results với provider version/branch.
9. Bật Broker matrix và can-i-deploy trước mỗi deployment.
10. Record-deployment sau khi deployment thành công.
11. Bật webhooks để pact changes kích hoạt provider verify.
12. Dùng pending/WIP đúng semantics để không chặn provider vì feature chưa được hỗ trợ.
13. Giữ selectors bao phủ deployed/released consumer versions, không chỉ latest.
14. Thay đổi breaking API bằng expand–migrate–contract, không deploy đồng thời bắt buộc.
15. Đối với schema provider, duy trì OpenAPI và documentation bên cạnh CDC.
16. Bổ sung security, DB, messaging, retry và fault-injection tests cho những điều Pact không kiểm.
17. Phân tích production logs/metrics và deprecation windows trước khi xóa old fields.
18. Theo dõi Pact Broker gate failures, missing results, webhook reliability, build promotion.
19. Giữ examples synthetic, không lộ token/secrets/PII trong Pact artifacts.
20. Kiểm các trường hợp negative (404/401/403/429) theo consumer behavior.
21. Xác định rõ ownership/versioning và review các contract changes như code changes.
22. Test provider tương thích với tất cả active consumer versions ở target environment.

### Checklist trước khi bật deploy gate

- [ ] Consumer test gọi client thật, không chỉ request thủ công.
- [ ] Pact file được sinh từ tests và versioned theo SHA/branch.
- [ ] Provider name/consumer name khớp chính xác giữa hai bên.
- [ ] Provider states deterministic, dữ liệu test không chia sẻ production.
- [ ] Provider verification thực sự replay interactions lên implementation.
- [ ] Không suppress “no pacts to verify”.
- [ ] Matcher không quá rộng hoặc quá chặt.
- [ ] Có both success và error semantics quan trọng.
- [ ] Broker nhận Pact và verification results với đúng versions.
- [ ] Pending/WIP được cấu hình và hiểu chính xác.
- [ ] can-i-deploy chạy cho đúng artifact và environment trước deploy.
- [ ] record-deployment được gọi sau deploy thành công.
- [ ] Provider selectors bao phủ deployed consumers.
- [ ] Compatibility/rollout theo expand–migrate–contract.
- [ ] Security, timeout, retry, idempotency vẫn có tests độc lập.
- [ ] Không lưu secrets hoặc dữ liệu khách thật trong Pact.
- [ ] CI failure là hành động rõ ràng, không override gate tùy tiện.

## 38. Kết luận

**Consumer-driven contract cho phép các nhóm phát triển độc lập nhưng vẫn cam kết không phá giao tiếp giữa những phiên bản đang triển khai.**

Với HTTP:

- Consumer viết Pact từ chính client/adapter thật và kiểm behavior trên mock server.
- Provider replay Pact trên service thật, tạo provider states để mỗi interaction deterministic.
- Pact Broker giữ versions/branches/verification matrix và deployments.
- `can-i-deploy` quyết định có đủ bằng chứng tương thích với môi trường mục tiêu hay chưa.
- Pending/WIP giúp các team tiến nhanh mà không che kết quả FAILED.
- Expand–migrate–contract giúp đổi API mà không buộc đồng loạt deploy.

**Không coi contract test là toàn bộ kiểm thử.** Nó kiểm giao tiếp, không tự kiểm database correctness, runtime availability, load, network resilience, auth hay mọi business invariants. Kết hợp Pact/Spring Cloud Contract với integration/security/fault tests và observability để vừa duy trì tốc độ release, vừa tránh breaking changes khi nhiều dịch vụ cùng tiến hóa.

### Tài liệu tham khảo chính thức

- [Pact JVM — Consumer JUnit 5](https://docs.pact.io/implementation_guides/jvm/consumer/junit5): @PactConsumerTest, @PactTestFor, MockServer, Pact DSL.
- [Pact JVM — Provider JUnit 5](https://docs.pact.io/implementation_guides/jvm/provider/junit5): @Provider, @TestTemplate, HttpTestTarget, result publishing.
- [Pact JVM — Spring6/Spring Boot3](https://docs.pact.io/implementation_guides/jvm/provider/spring6): Pact verification với Spring 6/Boot 3.
- [Pact JVM — Provider State Setup](https://docs.pact.io/implementation_guides/jvm/provider/junit): @State handlers và Pact sources.
- [Pact Broker — Can I Deploy](https://docs.pact.io/pact_broker/can_i_deploy): Matrix, can-i-deploy và record-deployment.
- [Pact Broker — Pending Pacts](https://docs.pact.io/pact_broker/advanced_topics/pending_pacts): pending verification semantics.
- [Pact Broker — Work In Progress Pacts](https://docs.pact.io/pact_broker/advanced_topics/wip_pacts): WIP inclusion và pending relationship.
- [Pact JVM — JDK/Specification Support](https://docs.pact.io/implementation_guides/jvm/readme): compatibility và artifact coordinates.
- [Spring Boot 3.5 — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): SpringBootTest, RANDOM_PORT.
- [Spring Cloud Contract — Reference](https://docs.spring.io/spring-cloud-contract/reference/): contracts DSL, verifier, stub runner.
