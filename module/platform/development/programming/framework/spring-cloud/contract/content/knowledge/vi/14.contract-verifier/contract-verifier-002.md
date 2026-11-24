# Chọn framework, ngôn ngữ và chế độ kiểm thử trong Contract Verifier

Trong **Spring Cloud Contract**, viết hợp đồng Groovy/YAML DSL mới là bước đầu. Để bảo đảm **producer** thực thi đúng hành vi HTTP hoặc thông điệp mà **consumer** đang sử dụng, **Spring Cloud Contract Verifier** phải chuyển hợp đồng thành các bài kiểm thử và thực thi chúng trong một môi trường phù hợp. Việc lựa chọn **test framework**, **ngôn ngữ của kiểm thử được sinh** và **test mode** ảnh hưởng trực tiếp đến mã test được tạo, lớp cơ sở phải chuẩn bị, thư viện cần khai báo và mức độ mô phỏng môi trường HTTP.

Bài thuộc chương **Contract Verifier** của mô-đun **SPRING_CLOUD_CONTRACT**. Mục tiêu là đưa ra cách lựa chọn có căn cứ cho dự án **Spring MVC**, **Spring WebFlux** hoặc ứng dụng cần kiểm thử qua HTTP thực, thay vì chọn theo thói quen. Cùng với generated producer tests, quy trình Spring Cloud Contract còn có thể tạo và phát hành **stub**, cho consumer chạy **Stub Runner** trong CI để sớm phát hiện thay đổi API không tương thích. Hai luồng này dùng cùng nguồn hợp đồng nhưng có trách nhiệm khác nhau.

## 1. Ba quyết định độc lập cần phân biệt

Khi cấu hình Contract Verifier, nhóm thường nhầm ba loại lựa chọn sau thành một:

| Lựa chọn | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **DSL dùng để viết hợp đồng** | Đội ngũ sẽ mô tả request/response hoặc thông điệp bằng định dạng gì? | Tệp `.groovy`, `.yml`/YAML được phiên bản công cụ hỗ trợ. |
| **Test framework và ngôn ngữ test được sinh** | Các generated tests chạy với engine/assertion và cú pháp test nào? | JUnit 5/Java, JUnit 4/Java trong dự án cũ, Spock/Groovy. |
| **Test mode / HTTP test client** | Generated tests sẽ gửi request tới producer bằng cơ chế nào? | `MOCKMVC`, `WEBTESTCLIENT`, `EXPLICIT`; một số tích hợp có thêm `JAXRSCLIENT`. |

**Điểm mấu chốt:** sử dụng **Groovy DSL không bắt buộc generated tests phải là Groovy/Spock**. Ví dụ, một tệp `get_paid_order.groovy` có thể sinh bài kiểm thử **JUnit 5 bằng Java** chạy trong chế độ **MockMvc**. Tương tự, một hợp đồng YAML vẫn có thể được sử dụng trong dự án chọn JUnit 5 hoặc Spock nếu toolchain hỗ trợ tổ hợp đó.

Việc chọn DSL liên quan **cách viết hợp đồng**; `testFramework` liên quan **cách sinh và chạy mã kiểm thử**; `testMode` liên quan **cách generated test tương tác với producer**. Không nên đổi ba thứ cùng lúc chỉ vì một test thất bại, vì khi đó khó biết lỗi đến từ cú pháp DSL, engine kiểm thử hay cách thiết lập HTTP.

## 2. Generated producer tests đứng ở đâu trong toàn bộ quy trình?

Xét **Order Service** là producer, **Billing Service** là consumer. Billing gọi:

~~~http
GET /api/orders/42
Accept: application/json
~~~

và mong đợi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

Spring Cloud Contract có thể dùng một hợp đồng làm đầu vào cho hai nhánh:

~~~mermaid
flowchart TD
    C["Hợp đồng Groovy hoặc YAML"] --> G["Contract Verifier sinh producer test"]
    C --> S["Sinh stub HTTP/messaging"]
    G --> M["JUnit hoặc Spock chạy theo testMode"]
    M --> P{"Producer thực khớp hợp đồng?"}
    P -->|Không| F["Build/CI thất bại"]
    P -->|Có| A["Cho phép đóng gói và phát hành stubs"]
    S --> A
    A --> R["Stub Runner tải và chạy stub"]
    R --> T["Consumer viết và chạy test cho mã client thật"]
~~~

**Generated producer test** kiểm tra **mã Order Service**, không kiểm tra một stub. **Consumer test** kiểm tra **mã Billing Service** qua stub, thông thường do đội consumer tự viết. **Stub Runner** tìm và khởi chạy stub; nó không tự sinh mọi assertion nghiệp vụ cho Billing. Việc chỉ cho publish stub sau khi producer test đạt là **quy tắc CI phải thiết lập**, vì artifact stub có thể được tạo trong quá trình build trước khi toàn bộ test hoàn tất.

Như vậy, chọn đúng framework và test mode giúp nhánh producer thực sự có giá trị. Nếu test được sinh nhưng không chạy, hoặc chỉ gọi một môi trường giả không chứa controller/service cần kiểm tra, pipeline xanh không chứng minh lời cam kết đã được xác minh.

## 3. Chọn test framework: JUnit 5, JUnit 4 hay Spock?

Các lựa chọn thường gặp trong hệ Spring Cloud Contract Verifier:

| Test framework | Ngôn ngữ generated test thường dùng | Khi nào phù hợp | Điều kiện cần kiểm |
| --- | --- | --- | --- |
| **JUnit 5 / Jupiter** (`JUNIT5`) | Java | Dự án Spring Boot hiện đại, đội phát triển dùng Java và Jupiter. | Test engine, Maven Surefire/Gradle test discovery, các annotation Jupiter, Spring Test tương thích. |
| **JUnit 4** (`JUNIT`, trong những phiên bản hỗ trợ) | Java | Bảo trì hệ thống cũ đang có nhiều test JUnit 4. | Tương thích với phiên bản Contract Verifier và hệ Spring đang dùng; chiến lược chuyển lên Jupiter. |
| **Spock** (`SPOCK`, nếu tổ hợp phiên bản hỗ trợ) | Groovy | Nhóm quen phong cách `given/when/then` và đã dùng Spock/Groovy cho test. | Bộ phiên bản Groovy, Spock, Spring Boot, plugin và cơ chế chạy test tương thích. |

**Khuyến nghị cho dự án mới dùng Java và Spring Boot hiện đại:** bắt đầu từ **JUnit 5** nếu release train đang dùng hỗ trợ; nó nhất quán với phần lớn bộ test Spring Boot ngày nay. Không nên chọn JUnit 4 chỉ để giữ cú pháp quen thuộc trong một dự án mới.

**Spock** hữu ích khi đội ngũ đã có nền tảng Groovy, nhưng lựa chọn này không phải chỉ đổi một dòng `testFramework`. Bạn cần có dependencies Spock phù hợp, khả năng biên dịch Groovy test source và cơ chế thực thi tương ứng. Nếu plugin sinh test Spock nhưng build chỉ cấu hình chạy Java/JUnit, test có thể bị bỏ sót.

**Ngôn ngữ nguồn của ứng dụng và ngôn ngữ test là hai chuyện khác nhau.** Producer có thể viết bằng Java hoặc Kotlin nhưng vẫn dùng hợp đồng Groovy/YAML. Khi đó nhóm cần xác nhận test framework được chọn tạo mã mà pipeline đang biên dịch và chạy được. Không suy ra rằng ứng dụng Kotlin bắt buộc phải sinh test Kotlin; lựa chọn cụ thể phụ thuộc khả năng plugin và cấu hình dự án.

### 3.1. Không trộn JUnit 4 và JUnit 5 một cách ngẫu nhiên

Với JUnit 5, lớp cơ sở thường sử dụng:

~~~java
import org.junit.jupiter.api.BeforeEach;

@BeforeEach
void setUp() {
    // Chuẩn bị MockMvc, RestAssured hoặc fixture.
}
~~~

Trong JUnit 4, cơ chế setup tương ứng thường dùng `org.junit.Before` và các annotation runner khác. Nếu generated tests được sinh theo **JUnit 5** nhưng lớp cơ sở dùng thiết lập/engine không phù hợp, bước khởi tạo có thể không chạy như dự kiến. Hãy thống nhất framework cho phần contract tests hoặc cấu hình rõ ràng đường tương thích legacy, thay vì dựa vào khả năng tự nhận diện.

## 4. Chọn test mode theo kiểu ứng dụng và mức cần kiểm tra

**Test mode** trả lời: generated producer test tương tác với giao diện HTTP của producer bằng cách nào? Ba lựa chọn có ý nghĩa nhất trong nhiều dự án Spring:

| Chế độ | Cách tương tác | Phù hợp nhất khi | Giới hạn cần biết |
| --- | --- | --- | --- |
| **`MOCKMVC`** | Dùng **Spring MockMvc** để gọi lớp xử lý Spring MVC trong test context, không cần socket HTTP thực. | Producer là ứng dụng **Spring MVC** hoặc controller Servlet cần test nhanh, ổn định. | Không xác minh toàn bộ HTTP server, connector, proxy và hành vi mạng khi triển khai. |
| **`WEBTESTCLIENT`** | Dùng **Spring WebTestClient** phù hợp với stack WebFlux/reactive và cấu hình test của ứng dụng. | Producer xây trên **Spring WebFlux**. | Cần thiết lập binding/client và test context đúng kiểu reactive; không mặc nhiên kiểm mọi hạ tầng ngoài. |
| **`EXPLICIT`** | Gửi HTTP request tới **server chạy thật** ở URL/port được cấu hình cho generated test. | Muốn kiểm HTTP stack thực của ứng dụng, custom filters/network adapter, hoặc trường hợp không dùng MockMvc. | Tốn thời gian khởi động, phụ thuộc port/server; có thể gặp lỗi môi trường mà MockMvc không gặp. |

Trong một số phiên bản/tích hợp của Spring Cloud Contract còn có **`JAXRSCLIENT`** cho ứng dụng JAX-RS. Chỉ chọn khi **phiên bản plugin và stack producer thực sự hỗ trợ**, có cấu hình client và base test tương ứng; không chọn nó cho một controller `@RestController` thông thường chỉ vì tên nghe giống HTTP client.

**Đừng đồng nhất `EXPLICIT` với “phải có môi trường chung từ xa”.** Trong bài kiểm thử Spring Boot, test có thể tự khởi động chính producer bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)` rồi gửi HTTP tới cổng local đó. Như vậy ta dùng HTTP server thực nhưng vẫn kiểm độc lập trên máy/CI của producer.

### 4.1. Sơ đồ chọn nhanh

~~~mermaid
flowchart TD
    A{"Producer phục vụ HTTP theo stack nào?"}
    A -->|Spring MVC| B{"Có cần kiểm server/network adapter thật?"}
    B -->|Không| C["MOCKMVC"]
    B -->|Có| D["EXPLICIT"]
    A -->|Spring WebFlux| E{"Muốn kiểm qua WebTestClient?"}
    E -->|Có| F["WEBTESTCLIENT"]
    E -->|Muốn HTTP server thực| D
    A -->|JAX-RS hoặc stack khác| G["Kiểm tổ hợp được plugin hỗ trợ"]
    G --> H["JAXRSCLIENT nếu phù hợp hoặc EXPLICIT"]
    C --> I["Chọn JUnit 5/Spock theo toolchain"]
    F --> I
    D --> I
    H --> I
~~~

Nếu vừa muốn tốc độ cao vừa muốn bảo vệ các đặc tính HTTP triển khai thật, có thể dùng **MockMvc** cho phần lớn generated tests và bổ sung một nhóm **integration tests qua HTTP thực**. Không cần ép mọi bài kiểm thử dùng `EXPLICIT` nếu rủi ro cần bảo vệ đã được kiểm ở tầng phù hợp.

## 5. Hợp đồng mẫu dùng chung cho ba chế độ

Để thấy **test mode không đổi ý nghĩa hợp đồng**, ta dùng một hợp đồng HTTP Groovy trong producer tại:

`src/test/resources/contracts/orders/get_paid_order.groovy`

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Trả trạng thái đơn 42 đã thanh toán'

    request {
        method 'GET'
        url '/api/orders/42'
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID'
        )
    }
}
~~~

Về bản chất, generated test phải tạo request tương đương **GET /api/orders/42**, rồi kiểm **HTTP 200**, **Content-Type JSON**, `id=42` và `status=PAID`. Điều khác nhau giữa MockMvc, WebTestClient và HTTP explicit là **công cụ thực hiện request và cách khởi tạo môi trường**, không phải producer được phép thay đổi mã trạng thái hoặc schema.

Hợp đồng có thể viết bằng **YAML DSL** thay vì Groovy; lựa chọn đó không tự đổi test mode. Ví dụ tương đương:

~~~yaml
description: Trả trạng thái đơn 42 đã thanh toán
request:
  method: GET
  url: /api/orders/42
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

Hai đoạn là **hai cách biểu diễn một hành vi**. Trong một lượt build, không nên cùng đặt cả tệp Groovy lẫn YAML tương đương vào nơi plugin quét để tránh tạo test/stub trùng hoặc mâu thuẫn.

## 6. Ví dụ producer Spring MVC để thử các lựa chọn

Tạo một ứng dụng Spring Boot đơn giản với endpoint có cùng hành vi:

~~~java
package com.acme.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Và controller:

~~~java
package com.acme.orders;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public OrderView getOrder(@PathVariable long id) {
        if (id != 42L) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.NOT_FOUND);
        }
        return new OrderView(42L, "PAID");
    }

    public record OrderView(long id, String status) {}
}
~~~

Đây là **fixture học tập**, cố định đơn hàng 42 để phép kiểm không phụ thuộc cơ sở dữ liệu. Trong dự án thật, base test cần thiết lập service, mock dependency hoặc dữ liệu xác định trước; đừng đưa mã hardcode ID như ví dụ vào luồng nghiệp vụ sản xuất.

## 7. Cấu hình Contract Verifier cho JUnit 5 và MockMvc

Với producer Spring MVC dùng Maven, cấu hình các dependencies kiểm thử cần thiết, ví dụ:

~~~xml
<dependencies>
    <!-- Cùng với spring-boot-starter-web ở ứng dụng producer. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-verifier</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Tại phần `<build><plugins>` trong `pom.xml`, cấu hình plugin:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>com.acme.orders.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

**Lưu ý:** các đoạn XML trên là **phần của POM**, không phải toàn bộ POM có thể chạy độc lập. Dự án cần Spring Boot parent hoặc BOM, Spring Cloud BOM tương thích và thuộc tính `spring-cloud-contract.version` được khai báo đúng; version của plugin phải tương thích với phiên bản các dependency Spring Cloud Contract đang dùng. Không chọn phiên bản plugin một cách tách rời khỏi release train.

Từ cấu hình này:

- `testFramework=JUNIT5`: sinh bài test theo **JUnit Jupiter**.
- `testMode=MOCKMVC`: dùng cơ chế **MockMvc** để gọi Spring MVC.
- `baseClassForTests`: generated tests kế thừa lớp cơ sở `ContractTestBase`, nơi chuẩn bị Spring context và công cụ gửi request.

### 7.1. Viết base test đúng với MockMvc

Tạo `src/test/java/com/acme/orders/ContractTestBase.java`:

~~~java
package com.acme.orders;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = OrderApplication.class)
@AutoConfigureMockMvc
public abstract class ContractTestBase {

    @Autowired
    private MockMvc mockMvc;

    @BeforeEach
    void configureMockMvc() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

**Vì sao đây là lớp cơ sở?** Spring khởi tạo context của Order Service, cấu hình `MockMvc`; phần setup nối Rest Assured MockMvc vào ngữ cảnh đó. Các generated tests kế thừa lớp này để request đi tới **controller của producer thực trong test context**, không phải một WireMock stub.

Với cấu hình của những phiên bản khác nhau, cách test được sinh gọi Rest Assured MockMvc có thể thay đổi; hãy xem mã Java trong thư mục generated test sources để kiểm nó thực sự dùng đối tượng/cấu hình mà base test cung cấp. Không sửa trực tiếp test được sinh; lần generate sau có thể ghi đè.

## 8. Chuyển sang EXPLICIT khi cần kiểm HTTP server thực

Vẫn dùng **hợp đồng Groovy ở mục 5** và **JUnit 5**, nhưng đổi plugin sang:

~~~xml
<configuration>
    <testFramework>JUNIT5</testFramework>
    <testMode>EXPLICIT</testMode>
    <baseClassForTests>com.acme.orders.HttpContractTestBase</baseClassForTests>
</configuration>
~~~

Ở chế độ này, generated tests sử dụng HTTP client để gọi producer qua một cổng đang lắng nghe. Với Spring Boot, có thể tự khởi động ứng dụng trong test bằng `RANDOM_PORT`:

~~~java
package com.acme.orders;

import io.restassured.RestAssured;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(
    classes = OrderApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
public abstract class HttpContractTestBase {

    @LocalServerPort
    private int port;

    @BeforeEach
    void configureHttpClient() {
        RestAssured.baseURI = "http://localhost";
        RestAssured.port = port;
        RestAssured.basePath = "";
    }
}
~~~

Ví dụ này giả định generated tests dùng **Rest Assured HTTP** ở chế độ explicit như toolchain tương ứng. Test Boot tự khởi động HTTP server ở một cổng rảnh, inject cổng vào `@LocalServerPort` rồi cấu hình request đi tới đó. Cách khởi tạo cụ thể phải khớp thư viện HTTP và **mã kiểm thử thực sự được plugin sinh**; nếu custom base test không được kế thừa hoặc port không được thiết lập, các request sẽ gửi sai địa chỉ.

**So sánh có ý nghĩa:**

| Trường hợp | MockMvc | EXPLICIT |
| --- | --- | --- |
| Gọi được `@RestController` qua Spring test context. | Có. | Có, thông qua HTTP server. |
| Cần socket HTTP thực và port. | Không. | Có. |
| Kiểm thêm hành vi ở HTTP server/connector thực. | Giới hạn. | Có cơ hội kiểm nhiều hơn, phụ thuộc cách khởi động ứng dụng. |
| Tốc độ, độ ổn định môi trường. | Thường nhanh và ít phụ thuộc port hơn. | Thường nặng hơn, có thể gặp lỗi port/startup. |
| Bảo vệ toàn bộ proxy, DNS, TLS và mạng production. | Không. | **Không tự động**; cần môi trường kiểm thử tương ứng nếu muốn kiểm các phần đó. |

Lưu ý **Rest Assured dùng cấu hình static** trong ví dụ trên: khi chạy generated tests song song với nhiều server/cổng, các test có thể ảnh hưởng nhau nếu cùng thay đổi cấu hình global. Với CI parallel, cần thiết kế cách cô lập cấu hình, test class hoặc tắt song song cho phần liên quan; không gán nhiều port vào cùng global configuration rồi mong kết quả luôn ổn định.

## 9. Khi producer dùng Spring WebFlux: WEBTESTCLIENT

Với một ứng dụng **Spring WebFlux**, cân nhắc `WEBTESTCLIENT` thay cho `MOCKMVC`. Ví dụ phần cấu hình plugin:

~~~xml
<configuration>
    <testFramework>JUNIT5</testFramework>
    <testMode>WEBTESTCLIENT</testMode>
    <baseClassForTests>com.acme.orders.WebFluxContractTestBase</baseClassForTests>
</configuration>
~~~

Một lớp cơ sở thử nghiệm có thể khởi động WebFlux application context:

~~~java
package com.acme.orders;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;

@SpringBootTest(
    classes = OrderApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
public abstract class WebFluxContractTestBase {
    // Bổ sung WebTestClient/binding theo mã generated test và
    // khả năng của phiên bản Spring Cloud Contract đang dùng.
}
~~~

Đây là **khung setup**, không phải lời cam kết có thể copy là generated tests của mọi phiên bản sẽ chạy ngay. Tùy phiên bản Spring Cloud Contract, cấu hình `WEBTESTCLIENT` cần client/binding hoặc đối tượng static cụ thể; cần **đọc lớp test được sinh** để biết phải cung cấp gì trong base test. Dùng đúng starter WebFlux, Spring Boot Test và Contract Verifier tương thích.

**Reactive không có nghĩa test tự kiểm mọi yếu tố bất đồng bộ.** Hãy thiết kế response, timeout và fixture đủ xác định; với streaming hoặc tình huống không thể biểu diễn bằng một response HTTP hữu hạn, cần lựa chọn hợp đồng và phương pháp test phù hợp. Nếu bạn muốn kiểm HTTP server thực của WebFlux thay vì WebTestClient ở binding mô phỏng, có thể cân nhắc `EXPLICIT` với server thực, theo hỗ trợ của phiên bản plugin.

## 10. Khi nào nên giữ JUnit 4 hoặc chọn Spock?

### 10.1. Dự án legacy dùng JUnit 4

Trong một hệ thống đang dùng JUnit 4 và một phiên bản Spring Cloud Contract hỗ trợ framework đó, cấu hình có thể chọn:

~~~xml
<configuration>
    <testFramework>JUNIT</testFramework>
    <testMode>MOCKMVC</testMode>
    <baseClassForTests>com.acme.orders.LegacyContractBase</baseClassForTests>
</configuration>
~~~

Lớp cơ sở khi đó cần thiết lập theo **JUnit 4/Spring Test** tương ứng. Đừng dùng đoạn base test JUnit 5 ở mục 7 rồi chỉ đổi `testFramework` mà không kiểm runner, annotation setup và test discovery. Với dự án Spring Boot mới, nên đánh giá hướng chuyển sang JUnit 5 thay vì kéo dài một tổ hợp legacy chỉ phục vụ generated tests.

### 10.2. Nhóm đã sử dụng Spock/Groovy

Nếu dự án có sẵn bộ kiểm thử Spock và toolchain Groovy tương thích, có thể xem xét:

~~~xml
<configuration>
    <testFramework>SPOCK</testFramework>
    <testMode>MOCKMVC</testMode>
    <baseClassForTests>com.acme.orders.SpockContractBase</baseClassForTests>
</configuration>
~~~

Cần có các thư viện **Spock và tích hợp Spring** thích hợp, cấu hình biên dịch Groovy và nhận diện specs khi chạy test. Lớp cơ sở Spock thường dùng lifecycle/setup theo Spock thay vì `@BeforeEach` của JUnit Jupiter. Hãy xác nhận plugin tạo ra đúng mã Groovy/Spock, các specs được thực thi và dữ liệu fixture có sẵn.

**Quy tắc chọn thực tế:** một nhóm Java/JUnit Jupiter không cần đưa Groovy/Spock vào chỉ vì hợp đồng viết bằng Groovy DSL; ngược lại, nhóm đã đầu tư vào Spock không cần bỏ nó nếu phiên bản Spring Cloud Contract đang dùng hỗ trợ tốt và CI chạy specs ổn định.

## 11. Nhận biết generated test có thực sự chạy

Sau khi cấu hình producer, chạy từ thư mục dự án:

~~~shell
mvn clean verify
~~~

Với Maven, plugin được cấu hình vào lifecycle phù hợp sẽ đọc hợp đồng, tạo mã test và để test runner thực thi các test đó. **Đừng chỉ nhìn dòng `BUILD SUCCESS`**. Kiểm tra:

1. **Contract được nạp:** file `get_paid_order.groovy` được plugin xử lý.
2. **Test được sinh:** có Java/JUnit 5 hoặc Groovy/Spock phù hợp với `testFramework` trong generated test sources.
3. **Mã HTTP tương ứng `testMode`:** MockMvc dùng cách gọi vào Spring MVC; EXPLICIT gọi HTTP server; WebTestClient dùng client reactive được thiết lập đúng.
4. **Test thực thi:** báo cáo Surefire/Gradle hiển thị ít nhất một test cho hợp đồng mẫu thực sự chạy; không bị skip hoặc lọc nhầm.
5. **Assertion đúng nội dung:** request `GET /api/orders/42` được gửi và response có mã `200`, `id=42`, `status=PAID`.
6. **Có khả năng phát hiện lỗi:** thay `status` thành `state` trong controller, giữ nguyên hợp đồng và chạy lại; generated test phải thất bại.

Mã kiểm thử được sinh có thể có ý nghĩa tương đương đoạn minh họa sau:

~~~java
// Minh họa assertion, không phải mã Java nguyên văn do plugin sinh.
given()
    .get("/api/orders/42")
.then()
    .statusCode(200)
    .body("id", equalTo(42))
    .body("status", equalTo("PAID"));
~~~

Thư viện gọi request, static imports, cách cấu hình base test và tên file được sinh phụ thuộc phiên bản, chế độ và framework. **Không chỉnh tay generated tests** để sửa lỗi; hãy sửa hợp đồng, base test hoặc implementation.

## 12. Chọn test mode nào nếu producer có nhiều loại giao diện?

Một producer có thể có cả HTTP controller và nghiệp vụ phát thông điệp. Đừng coi một cấu hình HTTP `testMode` tự động bao phủ mọi giao diện.

| Loại giao diện cần xác minh | Hướng kiểm tra |
| --- | --- |
| Spring MVC REST API | Chọn `MOCKMVC` khi test nội bộ controller là đủ; dùng `EXPLICIT` nếu cần server HTTP thực. |
| Spring WebFlux REST API | Chọn `WEBTESTCLIENT` khi được plugin và ứng dụng hỗ trợ; cân nhắc `EXPLICIT` cho HTTP server thực. |
| JAX-RS endpoint | Kiểm hỗ trợ `JAXRSCLIENT` trong phiên bản sử dụng hoặc dùng HTTP `EXPLICIT` với setup phù hợp. |
| Producer **phát message** | Cấu hình kiểm thử messaging, điểm kích hoạt sự kiện và cơ chế bắt thông điệp; không thay bằng một request WireMock thông thường. |
| HTTP giao tiếp qua gateway, proxy, TLS | Generated producer test có thể kiểm endpoint; cần **integration/E2E test bổ sung** nếu chính hành vi gateway/proxy/TLS là cam kết. |

Với messaging, Spring Cloud Contract có thể mô tả message trigger, destination, headers và payload. Generated test cần có **cấu hình để kích hoạt và quan sát producer phát thông điệp thật**. HTTP modes trong bảng trước không phải sự thay thế cho việc kiểm broker, transaction, retry hay thứ tự event trên hạ tầng thật.

## 13. Kết nối lựa chọn producer test với việc phát hành stub

Giả sử Order Service dùng **JUnit 5 + MockMvc** và producer test đã đạt. Build có thể đóng gói stub thành artifact Maven theo classifier `stubs`, ví dụ:

~~~text
com.acme:order-service:1.0.0:stubs
order-service-1.0.0-stubs.jar
~~~

Consumer có thể dùng Stub Runner tải và chạy artifact đó:

~~~java
@SpringBootTest(properties = "orders.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientStubTest {

    @Autowired OrderClient orderClient;

    @Test
    void readsPaidOrder() {
        OrderDto dto = orderClient.getOrder(42L);
        assertThat(dto.status()).isEqualTo("PAID");
    }
}
~~~

Đây là **đoạn test consumer minh họa**, giả định đã có imports, dependencies, `OrderClient`, `OrderDto` và artifact được cài vào Maven local. Nếu consumer CI tải stub đã **phát hành lên repository**, chuyển sang `REMOTE` cùng `repositoryRoot` và cơ chế xác thực phù hợp.

Điều quan trọng là **producer đã dùng JUnit 5/MockMvc, Spock hay HTTP explicit không làm thay đổi bản chất của stub**: stub sinh từ **hợp đồng**, còn generated tests dùng test mode đã chọn để kiểm producer thực thi hợp đồng. Consumer không cần biết producer đã chạy MockMvc hay Rest Assured, nhưng cần biết **tọa độ phiên bản stub và giao diện được mô phỏng**.

Một pipeline CI tin cậy nên thực hiện:

1. **Build và generated producer tests** trên đúng framework/mode đã cấu hình.
2. **Chặn publish khi producer verification thất bại.**
3. **Đóng gói và phát hành stub theo version xác định**, gắn được với source và hợp đồng đã xác minh.
4. **Chạy consumer tests qua Stub Runner**, kiểm mã HTTP/messaging client của consumer theo các tình huống được bảo vệ.
5. **Kiểm tra tương thích ngược** trước khi xóa/sửa những hợp đồng mà consumer phiên bản cũ vẫn sử dụng.

## 14. Lỗi cấu hình thường gặp

| Dấu hiệu | Khả năng cần kiểm | Cách xử lý |
| --- | --- | --- |
| Plugin sinh Java test nhưng Maven báo 0 tests. | Surefire/Test engine không nhận JUnit 5; thư mục generated sources chưa được đưa vào compile/test lifecycle; test bị lọc. | Xem báo cáo runner, tên test, plugin lifecycle và test engine. |
| `NullPointerException` hoặc request không chạy trong chế độ MockMvc. | Base test chưa tạo/gắn `MockMvc` hoặc generated class không kế thừa đúng base class. | So tên `baseClassForTests`, `@AutoConfigureMockMvc` và setup `RestAssuredMockMvc`. |
| Generated test dùng WebTestClient nhưng producer là Spring MVC thuần. | Chọn `WEBTESTCLIENT` không khớp cách thiết lập ứng dụng/test client. | Cân nhắc `MOCKMVC` hoặc kiểm cấu hình WebTestClient được hỗ trợ. |
| Test `EXPLICIT` báo `Connection refused`. | Không có server chạy, sai base URI hoặc port chưa được inject. | Dùng `RANDOM_PORT` và cấu hình Rest Assured theo port thực; kiểm startup logs. |
| Test chạy qua HTTP nhưng gọi sai path. | Base path/servlet context path hoặc URL trong hợp đồng không khớp. | Đối chiếu route thật, `RestAssured.basePath` và endpoint contract. |
| Đổi `testFramework` sang Spock rồi test không được thực thi. | Thiếu Groovy/Spock dependencies, compile plugin hoặc spec discovery. | Hoàn thiện toolchain và kiểm có Spock specs thực sự chạy. |
| Build thành công nhưng controller đổi field `status` thành `state` vẫn không bị phát hiện. | Generated test bị skip, hợp đồng không được nạp hoặc assertion quá lỏng. | Kiểm số test, source được sinh, matcher và thử phá hợp đồng có chủ đích. |
| Test MockMvc đạt nhưng production lỗi với reverse proxy hoặc TLS. | MockMvc không kiểm hạ tầng HTTP triển khai. | Thêm integration/E2E test qua đường mạng thực và cấu hình tương ứng. |
| Stub được publish dù producer tests đỏ. | CI không chặn phát hành ở bước test. | Đặt điều kiện bắt buộc producer verification đạt trước publish. |
| JUnit 4 base test không hoạt động sau khi đổi sang JUnit 5. | Annotation setup/runner hoặc test discovery không thống nhất. | Dùng base test đúng Jupiter và cập nhật test engine, hoặc giữ tổ hợp legacy được hỗ trợ. |

Khi chẩn đoán, hãy đi theo chuỗi **hợp đồng được nạp → test được sinh đúng framework → base test khởi tạo đúng mode → test thực sự chạy → assertion so đúng triển khai → artifact stub được publish sau khi đạt**. Chuỗi này giúp tách lỗi công cụ khỏi lỗi producer vi phạm hợp đồng.

## 15. Bài thực hành: so sánh MOCKMVC và EXPLICIT trên cùng một hợp đồng

Để thấy tác động của lựa chọn test mode, thực hành trên dự án Order Service thử nghiệm:

1. **Chuẩn bị** ứng dụng Spring MVC có endpoint `GET /api/orders/42` trả `{"id":42,"status":"PAID"}` và đặt một file Groovy/YAML contract tương ứng.
2. **Chọn JUnit 5 + MOCKMVC**, cấu hình `ContractTestBase`, chạy `mvn clean verify` và xác nhận generated producer test **thực sự chạy và PASS**.
3. **Phá hợp đồng có kiểm soát:** đổi JSON field từ `status` thành `state` nhưng giữ contract. Chạy lại test, xác nhận **FAIL**.
4. **Hoàn nguyên** controller rồi chuyển `testMode` sang `EXPLICIT`, đổi sang `HttpContractTestBase` có `RANDOM_PORT`. Chạy lại cùng hợp đồng và xác nhận PASS.
5. **Kiểm sự khác biệt:** so generated test và log setup. Với MockMvc không cần socket HTTP; với EXPLICIT test phải đợi server khởi động và dùng đúng port.
6. **Gây lỗi cổng có kiểm soát:** bỏ cấu hình port trong base test EXPLICIT; quan sát lỗi kết nối rồi khôi phục. Giải thích vì sao lỗi này là **lỗi môi trường test**, không phải bằng chứng endpoint vi phạm JSON schema.
7. **Đóng gói stub** sau khi producer test đạt, cài vào repository local hoặc phát hành bản thử nghiệm theo version. Cho Billing chạy consumer test qua Stub Runner và xác nhận đọc `PAID`.
8. **Tổng kết lựa chọn:** nếu nhóm xây Spring MVC REST API với pipeline cần nhanh, vì sao MockMvc là mặc định hợp lý? Trường hợp cụ thể nào của dự án cần EXPLICIT để tăng phạm vi kiểm chứng?

Nếu nhóm đang dùng WebFlux, có thể thay bài so sánh MockMvc bằng **WEBTESTCLIENT so với EXPLICIT**, nhưng phải dùng WebFlux producer và base test phù hợp, không chỉ đổi một giá trị trong POM.

## 16. Checklist quyết định và câu hỏi tự kiểm tra

Một quyết định cấu hình tốt có thể viết ngắn gọn:

| Câu hỏi cần chốt | Câu trả lời mẫu cho Order Service |
| --- | --- |
| DSL nào dùng để viết hợp đồng? | Groovy cho HTTP request/response đơn giản, do nhóm đang duy trì. |
| Test framework/ngôn ngữ nào được sinh? | `JUNIT5`, test Java chạy Jupiter. |
| Producer sử dụng stack HTTP nào? | Spring MVC với `@RestController`. |
| Test mode nào phù hợp? | `MOCKMVC` cho generated producer tests; bổ sung HTTP integration tests khi cần. |
| Base test nào được chọn? | `com.acme.orders.ContractTestBase` khởi tạo Spring context và MockMvc. |
| Dấu hiệu kiểm chứng thành công? | Generated test chạy PASS và FAIL khi cố tình phá trường `status`. |
| Stub được đưa đến consumer bằng cách nào? | Artifact `stubs` theo version, consumer dùng Stub Runner trong CI. |

Tự trả lời các câu hỏi sau:

- Nếu hợp đồng viết bằng Groovy DSL, generated test có bắt buộc dùng Spock không? Vì sao?
- `testFramework` khác `testMode` như thế nào? Ví dụ `JUNIT5` và `MOCKMVC` có đang quyết định cùng một việc không?
- Khi nào `MOCKMVC` phù hợp hơn `EXPLICIT` và ngược lại?
- Vì sao `EXPLICIT` dùng cổng HTTP local vẫn không thay thế mọi phép kiểm tra mạng/gateway production?
- Vì sao WebFlux producer nên cân nhắc `WEBTESTCLIENT` thay vì mặc định sao chép cấu hình MockMvc?
- Nếu generated Java test tồn tại nhưng báo cáo Maven cho biết không test nào chạy, có thể kết luận producer đã được xác minh không?
- Việc đổi sang Spock có yêu cầu thêm điều gì ngoài `<testFramework>SPOCK</testFramework>`?
- Tại sao consumer test xanh với stub không chứng minh producer thực đã tuân thủ hợp đồng nếu producer verification bị bỏ qua?

**Ghi nhớ:** hãy chọn **DSL**, **test framework/ngôn ngữ** và **test mode** như ba quyết định khác nhau. Với Spring MVC, thường bắt đầu từ **JUnit 5 + MockMvc**; với WebFlux, xem xét **WebTestClient**; khi phải kiểm HTTP server thực, dùng **EXPLICIT** cùng base test và port đúng. Sau khi cấu hình, phải **xem generated test, xác nhận test thực sự chạy, thử gây lỗi để chứng minh khả năng phát hiện sai lệch**, rồi mới phát hành stub cho consumer dùng qua Stub Runner. Giá trị của Spring Cloud Contract nằm ở việc hai phía cùng kiểm một hợp đồng đã được xác minh, không nằm ở việc pipeline chỉ hiển thị một kết quả build xanh.
