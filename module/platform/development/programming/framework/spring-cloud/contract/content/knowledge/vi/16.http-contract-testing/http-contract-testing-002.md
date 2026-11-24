# Dùng RestAssuredMockMvc trong base test

## 1. Vấn đề: contract được sinh thành test nhưng gọi HTTP bằng cách nào?

Trong **Spring Cloud Contract**, producer và consumer cùng thống nhất các tương tác có thể kiểm chứng: phương thức HTTP, đường dẫn, query parameters, headers, request body và response kỳ vọng. Hợp đồng viết bằng **Groovy/YAML DSL** được **Contract Verifier** chuyển thành kiểm thử phía producer; từ cùng hợp đồng có thể tạo stub để consumer chạy qua **Stub Runner**. CI có thể chặn thay đổi API không tương thích khi generated producer tests thất bại.

Tuy nhiên, đoạn Groovy sau **không tự khởi tạo được** ứng dụng web:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')

    request {
        method GET()
        urlPath('/api/orders/ORD-123')
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 120000
        )
    }
}
~~~

Plugin có thể sinh test gửi một request như `GET /api/orders/ORD-123`, nhưng test vẫn cần **một môi trường để gọi controller của producer** và chuẩn bị dữ liệu sao cho kết quả dự đoán được. Một cách phổ biến khi producer dùng **Spring MVC** là cấu hình **RestAssuredMockMvc** trong **base test class**.

Câu lệnh trung tâm của bài học là:

~~~java
RestAssuredMockMvc.mockMvc(mockMvc);
~~~

Nó nói với RestAssuredMockMvc rằng các lời gọi HTTP theo phong cách RestAssured trong generated test sẽ sử dụng đối tượng `MockMvc` đã cấu hình, thay vì yêu cầu mở một HTTP server thật.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **MockMvc**, **RestAssuredMockMvc**, **generated test** và **base test class**.
2. Cấu hình base class với `@WebMvcTest` hoặc `@SpringBootTest` theo phạm vi muốn kiểm chứng.
3. Hiểu vai trò của `@BeforeEach` và `RestAssuredMockMvc.mockMvc(mockMvc)`.
4. Chuẩn bị mock/fixture phù hợp để request do generated test gửi nhận được response đã cam kết.
5. Đọc cấu hình plugin để kiểm tra generated test kế thừa đúng base class và dùng HTTP test mode tương ứng.
6. Xử lý các lỗi thường gặp: không tìm thấy test, application context lỗi, `401/403`, `404`, sai JSON và thay đổi API thật sự.
7. Đưa producer verification vào CI trước khi phát hành stub cho consumer.

> **Giới hạn quan trọng:** RestAssuredMockMvc được dùng cho **Spring MVC (Servlet stack)**. Nó không biến một ứng dụng WebFlux thuần reactive thành Spring MVC, cũng không thay thế việc kiểm thử gateway, socket HTTP, TLS hoặc môi trường triển khai thật.

## 2. Bốn thành phần hợp tác với nhau

| Thành phần | Vai trò | Ai tạo hoặc cấu hình? |
| --- | --- | --- |
| **Contract DSL** | Mô tả request và response mà consumer phụ thuộc | Nhóm phát triển producer/consumer |
| **Generated producer test** | Tạo request, gọi producer, assert status/header/body | Spring Cloud Contract Verifier |
| **Base test class** | Dựng môi trường Spring, `MockMvc`, mock/fixture và các hook test | Người phát triển producer |
| **RestAssuredMockMvc** | Cung cấp API request/response theo phong cách RestAssured nhưng chạy qua Spring `MockMvc` | Thư viện + base class cấu hình |

Luồng xử lý:

~~~mermaid
flowchart TD
    A["Contract: GET /api/orders/ORD-123"] --> B["Contract Verifier sinh producer test"]
    B --> C["Generated test extends ContractVerifierBase"]
    C --> D["@BeforeEach chuẩn bị MockMvc + fixture"]
    D --> E["RestAssuredMockMvc gửi request qua MockMvc"]
    E --> F["Spring MVC routing → controller → serialization"]
    F --> G["Generated assertions: HTTP status, header, JSON"]
    G --> H{"Khớp hợp đồng?"}
    H -- "Không" --> I["Build báo thất bại"]
    H -- "Có" --> J["Producer verification đạt"]
    A --> K["Sinh stub mappings"]
    J --> L["Phát hành stub sau kiểm chứng"]
    K --> L
    L --> M["Consumer kiểm thử qua Stub Runner"]
~~~

Điều cần ghi nhớ là generated test **kế thừa base class** để dùng môi trường đã chuẩn bị. RestAssuredMockMvc không thay thế test runner JUnit; nó là cầu nối giữa mã request/assertion và Spring MVC.

### 2.1. Vì sao không viết toàn bộ setup ngay trong contract?

Contract chỉ nên diễn đạt **hành vi quan sát được tại biên API**. Nếu đưa cách mock repository, tên class nội bộ hoặc dữ liệu database vào DSL, bạn sẽ gắn chặt hợp đồng với implementation, làm khó đổi kiến trúc mà vẫn giữ API tương thích.

Ví dụ, consumer quan tâm:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
Accept: application/json
~~~

chứ không quan tâm controller đã gọi `OrderRepository.findById` hay `OrderQueryService.findById`. Chi tiết setup thuộc base class hoặc test support của producer.

## 3. MockMvc khác RestAssuredMockMvc và RestAssured HTTP thật thế nào?

**MockMvc** thuộc Spring Test. Nó mô phỏng yêu cầu HTTP đi qua Spring MVC infrastructure: handler mapping, controller, argument resolution, validation, message converters và các filter được đưa vào test context. Không cần mở socket và bind cổng HTTP.

**RestAssuredMockMvc** cung cấp cú pháp kiểm thử giống RestAssured, nhưng sử dụng MockMvc làm cơ chế gửi request. Spring Cloud Contract có thể sinh test theo mode này.

**RestAssured** (HTTP thực) lại gửi request qua mạng tới server đang chạy, thường là một ứng dụng khởi động bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc môi trường HTTP khác.

| Tiêu chí | RestAssuredMockMvc + MockMvc | RestAssured HTTP trên server thực |
| --- | --- | --- |
| Socket/cổng HTTP | Không cần | Cần server HTTP đang chạy |
| Phạm vi | Spring MVC trong test context | HTTP stack chạy trên server |
| Hiệu năng khởi tạo | Thường nhanh, nhất là MVC slice | Có thể tốn hơn vì khởi động server |
| Kiểm tra filter/security MVC | Có thể, tùy cấu hình | Có thể qua stack thực |
| TLS/proxy/gateway ngoài ứng dụng | Không | Chỉ khi chúng thật sự nằm trên đường request |
| Ứng dụng WebFlux thuần | Không phải lựa chọn tự nhiên | Cần test mode phù hợp reactive stack |
| Base setup | `RestAssuredMockMvc.mockMvc(mockMvc)` | Host/port/base URI hoặc HTTP client config |

Một test dùng MockMvc **vẫn thực thi các lớp web thật có trong context**, không chỉ “giả lập response” theo stub. Tuy nhiên, nếu service bên dưới bị mock thì logic service không được kiểm tra; đó là lựa chọn về **phạm vi test**, không phải lỗi của MockMvc.

## 4. Ví dụ hệ thống dùng trong bài: Order Service

Giả sử producer cung cấp `GET /api/orders/{orderId}`. Consumer muốn khi đơn hàng có ID `ORD-123` tồn tại thì nhận:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 120000,
  "paid": true
}
~~~

Một controller Spring MVC minh họa:

~~~java
package com.example.orders.api;

import com.example.orders.application.OrderService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{orderId}")
    public OrderView getById(@PathVariable String orderId) {
        return orderService.findById(orderId);
    }
}
~~~

Response DTO sử dụng Java record:

~~~java
package com.example.orders.api;

public record OrderView(
        String orderId,
        String status,
        long totalAmount,
        boolean paid
) {}
~~~

Service interface minh họa:

~~~java
package com.example.orders.application;

import com.example.orders.api.OrderView;

public interface OrderService {
    OrderView findById(String orderId);
}
~~~

Khi viết `@WebMvcTest`, chúng ta có thể **mock `OrderService`** để controller trả một DTO ổn định. Nếu dự án dùng Java phiên bản không hỗ trợ record, thay bằng class DTO có getter và cách serialize tương đương.

### 4.1. Contract nguồn

Tệp minh họa `src/test/resources/contracts/orders/get_confirmed_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')
    description('Consumer đọc đơn hàng đã được xác nhận')

    request {
        method GET()
        urlPath('/api/orders/ORD-123')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 120000,
            paid: true
        )
    }
}
~~~

Contract này yêu cầu producer đáp ứng đủ method, path, status, media type và các giá trị JSON có ý nghĩa. Generated test sẽ thay bạn gửi request tương ứng, nhưng **nó chưa biết cách chuẩn bị đơn hàng `ORD-123`**; đó là nhiệm vụ của base class.

## 5. Cách 1: base test dùng `@WebMvcTest` và RestAssuredMockMvc

Với một endpoint Spring MVC mà bạn muốn kiểm chứng ở **web slice** (controller, request mapping, HTTP status, JSON serialization), `@WebMvcTest` thường phù hợp.

Một base class có thể viết như sau:

~~~java
package com.example.orders.contract;

import com.example.orders.api.OrderController;
import com.example.orders.api.OrderView;
import com.example.orders.application.OrderService;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;

@WebMvcTest(OrderController.class)
public abstract class ContractVerifierBase {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @BeforeEach
    protected void configureContractTest() {
        given(orderService.findById("ORD-123"))
                .willReturn(new OrderView(
                        "ORD-123", "CONFIRMED", 120000L, true
                ));

        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Đây là **ví dụ cho Spring Boot dùng Spring Framework 6.2+**, nơi `@MockitoBean` thuộc package `org.springframework.test.context.bean.override.mockito`. Ở các phiên bản Spring Boot cũ, dự án có thể cần `@MockBean` thay thế và chỉnh import. Đừng sao chép annotation mà không đối chiếu bộ phiên bản Spring Boot/Spring Cloud Contract đang được dự án quản lý.

### 5.1. Đọc từng phần trong base class

**`@WebMvcTest(OrderController.class)`:** Nạp web slice chứa controller và những thành phần MVC được hỗ trợ; không tự nạp toàn bộ application bean graph. Nó giúp test tập trung vào ranh giới HTTP.

**`@Autowired MockMvc mockMvc`:** Nhận đối tượng MockMvc được Spring Test cung cấp cho context này.

**`@MockitoBean OrderService orderService`:** Tạo/thay thế dependency của controller bằng Mockito mock trong context. Nhờ đó test không cần database thật để tạo một đơn hàng `ORD-123`.

**`given(...).willReturn(...)`:** Chuẩn bị kết quả ổn định từ dependency khi controller tìm `ORD-123`. Dữ liệu này phải **khớp contract**.

**`@BeforeEach`:** Chạy trước mỗi phương thức test theo JUnit Jupiter, kể cả những test được sinh trong subclass kế thừa base class.

**`RestAssuredMockMvc.mockMvc(mockMvc)`:** Cấu hình RestAssuredMockMvc để lời gọi do generated test tạo **đi qua MockMvc đã chuẩn bị**.

### 5.2. Vì sao đặt setup trong `@BeforeEach`?

Các generated tests có thể kiểm tra nhiều contract: đơn hàng tồn tại, không tồn tại, response khác header hoặc query. Setup trong `@BeforeEach` giúp **mỗi test có trạng thái khởi đầu dự đoán được**.

Đặc biệt, RestAssuredMockMvc có các điểm cấu hình toàn cục trong test runtime. Nếu test suite dùng nhiều context/controller, nên cấu hình đúng MockMvc cho từng test, tránh phụ thuộc thứ tự chạy và tránh tình huống test sau sử dụng cấu hình còn sót từ test trước.

Không dùng `@BeforeAll` rồi giả định một mock context luôn đủ cho mọi test nếu có nhiều môi trường hoặc trạng thái riêng biệt. Khi ứng dụng cần reset/thay đổi mock giữa các kịch bản, hãy tổ chức setup theo từng test hoặc theo nhóm hợp đồng thích hợp.

### 5.3. Lưu ý về class và package

`ContractVerifierBase` phải được sinh test **nhìn thấy tại compile time** và được plugin cấu hình đúng tên package/class. Base class thường là `public abstract class`. Generated test sẽ kế thừa nó, không cần gọi thủ công từng hook nếu JUnit được cấu hình tương thích.

Nếu plugin sinh class khác package, vẫn có thể kế thừa base công khai qua import hoặc fully-qualified name; nhưng các thành phần có mức truy cập package-private trong base có thể tạo khó khăn. Dùng visibility phù hợp và tránh logic khởi tạo phụ thuộc tên package của generated test.

## 6. Cách 2: dùng `@SpringBootTest` kết hợp `@AutoConfigureMockMvc`

`@WebMvcTest` tập trung vào một phần MVC. Khi muốn chạy **nhiều bean ứng dụng thật hơn** (service, mapping, cấu hình) nhưng vẫn gửi request qua MockMvc, có thể dùng:

~~~java
package com.example.orders.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
public abstract class ContractVerifierBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    protected void configureContractTest() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Trong cách này, producer test dùng **nhiều cấu hình Spring thực** hơn. Dữ liệu `ORD-123` phải được chuẩn bị theo cơ chế thực tế: test database, SQL fixtures, test transaction, stub một hệ thống bên ngoài hoặc dependency override có chủ đích.

### 6.1. Phân biệt hai mức kiểm thử

| Nội dung | `@WebMvcTest` | `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` |
| --- | --- | --- |
| Controller và MVC serialization | Có | Có |
| Service/repository thật | Thường không; cần mock/import | Có thể có nếu được context nạp |
| Thời gian khởi tạo | Thường thấp hơn | Có thể cao hơn |
| Gỡ lỗi wiring nghiệp vụ | Phạm vi hạn chế | Rộng hơn |
| Phụ thuộc database/message broker | Có thể tránh bằng mock | Có thể cần cấu hình hoặc thay thế |
| Phù hợp với | Kiểm tra web contract tập trung | Kiểm tra hợp đồng đi qua nhiều lớp ứng dụng |

**Không có cách nào tốt tuyệt đối.** Một web-slice contract test có thể bắt lỗi routing, HTTP status, headers và DTO serialization nhưng không bảo đảm service thật tính tiền đúng. Một full-context test có phạm vi rộng hơn nhưng chậm và dễ phụ thuộc hạ tầng. Chọn theo rủi ro API và khả năng cô lập môi trường.

### 6.2. Vì sao không dùng server cổng ngẫu nhiên để gọi RestAssuredMockMvc?

`@SpringBootTest(webEnvironment = RANDOM_PORT)` mở server HTTP, trong khi RestAssuredMockMvc vẫn dùng **MockMvc**, không tự chuyển sang gọi cổng đã mở. Nếu mục tiêu là HTTP socket thực, hãy cấu hình generated test mode/client phù hợp (ví dụ RestAssured HTTP). Nếu mục tiêu là web test trong JVM, dùng `MOCK` + `MockMvc` là rõ ràng hơn.

## 7. Những cách khởi tạo RestAssuredMockMvc thường gặp

Tùy mức độ kiểm soát context, RestAssuredMockMvc có một số cách thiết lập.

### 7.1. Truyền một MockMvc đã có

~~~java
@Autowired
MockMvc mockMvc;

@BeforeEach
protected void setup() {
    RestAssuredMockMvc.mockMvc(mockMvc);
}
~~~

Đây là **cách trọng tâm của bài**: bạn đã cấu hình Spring Test và chỉ cần đưa MockMvc vào RestAssuredMockMvc.

### 7.2. Dùng web application context

Trong những dự án sử dụng `WebApplicationContext` và muốn RestAssuredMockMvc dựng cấu hình theo context:

~~~java
@Autowired
WebApplicationContext context;

@BeforeEach
protected void setup() {
    RestAssuredMockMvc.webAppContextSetup(context);
}
~~~

Tùy phiên bản, cú pháp và thiết lập filter có thể cần điều chỉnh. Cách này hữu ích nếu bạn muốn dựa trên web context sẵn có thay vì truyền trực tiếp một `MockMvc` do Spring Test cung cấp.

### 7.3. Standalone setup

Với test cô lập controller và tự cung cấp dependency:

~~~java
OrderService orderService = mock(OrderService.class);
OrderController controller = new OrderController(orderService);

RestAssuredMockMvc.standaloneSetup(controller);
~~~

Đây là **minh họa cấu hình standalone**, không phải base class hoàn chỉnh: cần thêm stub cho `orderService` và, nếu API sử dụng exception handler, converter, filter hoặc validation riêng, phải thiết lập chúng phù hợp. Standalone dễ chạy nhanh nhưng có thể bỏ qua các thành phần MVC mà production đang dùng.

**Không kết hợp nhiều cách thiết lập trong cùng một test một cách tùy tiện.** Chọn cách phù hợp với context và hợp đồng, rồi kiểm tra generated test thực sự sử dụng cấu hình mong đợi.

## 8. Đảm bảo plugin sinh test đúng HTTP test mode và base class

Tạo `ContractVerifierBase` là chưa đủ. Plugin cần biết generated tests phải kế thừa class nào, và mã được sinh phải phù hợp cách gửi request mong muốn.

Ví dụ cấu hình Maven (minh họa; dùng version phù hợp với Spring Boot/Spring Cloud của dự án):

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
      <extensions>true</extensions>
      <configuration>
        <baseClassForTests>
          com.example.orders.contract.ContractVerifierBase
        </baseClassForTests>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Trong ví dụ này:

- `baseClassForTests` chỉ ra base class của generated tests.
- `testFramework` xác định kiểu test framework mà plugin cần sinh; `JUNIT5` dành cho JUnit Jupiter.
- `testMode` là `MOCKMVC` để sinh lời gọi theo RestAssuredMockMvc.
- `extensions` kích hoạt tích hợp lifecycle Maven của plugin theo cách cấu hình phổ biến.
- Placeholder version **phải được thay bằng phiên bản tương thích** trong dự án; không thể sao chép nguyên rồi kỳ vọng Maven resolve được.

Dependency kiểm thử thường gồm Spring Cloud Contract Verifier starter và Spring Boot test:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Phiên bản dependencies nên được quản lý nhất quán qua Spring Cloud/Spring Boot dependency management. Trong dự án dùng plugin hoặc starter khác, cần điều chỉnh đúng với tài liệu phiên bản tương ứng.

### 8.1. Gradle cũng cần đồng bộ chế độ kiểm thử

Với Gradle, mục tiêu vẫn là:

1. Áp dụng plugin Spring Cloud Contract phù hợp.
2. Khai báo source directory chứa contract.
3. Chọn base class cho generated tests.
4. Chọn JUnit/test mode tương thích với RestAssuredMockMvc.
5. Chạy task sinh generated tests và task test liên quan.

Cấu hình DSL của Gradle thay đổi theo plugin và phiên bản, vì vậy không sao chép cấu hình Maven `<testMode>MOCKMVC</testMode>` vào file `build.gradle`. Hãy dùng cú pháp Gradle mà dự án hỗ trợ và xác nhận trực tiếp bằng generated Java test.

### 8.2. Nguồn contract và base class có thể nằm khác thư mục

Ví dụ cây file:

~~~text
order-service/
├── src/test/resources/contracts/orders/
│   ├── get_confirmed_order.groovy
│   └── get_order_not_found.groovy
├── src/test/java/com/example/orders/contract/
│   └── ContractVerifierBase.java
└── target/generated-test-sources/contracts/
    └── ... generated Java tests ...
~~~

Đường dẫn đầu ra chỉ minh họa một bố cục Maven thường gặp. Plugin và dự án có thể chọn vị trí khác.

**Nguyên tắc:** Không đặt generated tests vào source control chỉ để chúng “luôn tồn tại”. DSL và base class là source chủ động; generated tests là đầu ra build cần được sinh và chạy trong CI.

## 9. Đọc generated test để xác nhận đã kết nối đúng MockMvc

Khi plugin được cấu hình phù hợp, generated code có thể dùng các API tương tự:

~~~java
// MÃ MINH HỌA RÚT GỌN: không phải file plugin sinh nguyên văn
class GetConfirmedOrderTest extends ContractVerifierBase {

    @Test
    void validateGetConfirmedOrder() {
        MockMvcRequestSpecification request = given()
            .header("Accept", "application/json");

        ResponseOptions response = given()
            .spec(request)
            .get("/api/orders/ORD-123");

        assertThat(response.statusCode()).isEqualTo(200);
        // Kiểm tra Content-Type và JSON body theo contract
    }
}
~~~

Tên `GetConfirmedOrderTest` và các API assertion thực tế có thể khác tùy version plugin; ví dụ nhằm chỉ ra **dấu hiệu cần nhận diện**:

- Generated test **extends** đúng `ContractVerifierBase`.
- Test tạo request với `GET`, path `/api/orders/ORD-123`, header `Accept`.
- Lời gọi được thực thi bởi API MockMvc-style được sinh cho mode đã chọn.
- Response status và JSON fields có assertions tương ứng.

Không lấy ví dụ rút gọn này làm source Java compile sẵn. Trong dự án thật, mở file generated Java đầy đủ để xem import, lời gọi `given()`, kiểu response và assertions cụ thể.

### 9.1. Cơ chế kết nối qua base class

Khi JUnit chạy test trong subclass:

~~~text
JUnit tạo generated test
    ↓
Spring Test tạo MVC context
    ↓
JUnit gọi @BeforeEach kế thừa từ base class
    ↓
Base class chuẩn bị OrderService mock và RestAssuredMockMvc.mockMvc(mockMvc)
    ↓
Generated test gửi GET /api/orders/ORD-123
    ↓
MockMvc chọn OrderController.getById(...)
    ↓
Controller gọi OrderService mock, nhận OrderView
    ↓
Spring JSON converter tạo HTTP 200 + JSON
    ↓
Generated assertions kiểm tra hợp đồng
~~~

Nếu bỏ `RestAssuredMockMvc.mockMvc(mockMvc)` và không có cách thiết lập tương đương, generated test có thể không tìm thấy môi trường MockMvc cần thiết để gửi request. Nếu thiếu mock `OrderService` trong `@WebMvcTest`, application context có thể không tạo được controller.

## 10. Mở rộng: hợp đồng 404 và base class có nhiều fixture

Consumer có thể phụ thuộc cả nhánh thành công lẫn lỗi không tồn tại:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_not_found')

    request {
        method GET()
        urlPath('/api/orders/ORD-404')
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND'
        )
    }
}
~~~

Producer cần trả mã lỗi `ORDER_NOT_FOUND` nếu `ORD-404` không tồn tại. Với `@WebMvcTest`, có thể stub dependency:

~~~java
@BeforeEach
protected void configureContractTest() {
    given(orderService.findById("ORD-123"))
        .willReturn(new OrderView(
            "ORD-123", "CONFIRMED", 120000L, true
        ));

    given(orderService.findById("ORD-404"))
        .willThrow(new OrderNotFoundException("ORD-404"));

    RestAssuredMockMvc.mockMvc(mockMvc);
}
~~~

Ví dụ này giả định `OrderNotFoundException` và exception handler đã tồn tại trong ứng dụng. Nếu `@WebMvcTest` không tự đưa handler cần thiết vào context, hãy cấu hình `@Import(OrderErrorHandler.class)` hoặc cách đăng ký tương ứng để phản hồi có cấu trúc đúng với API.

### 10.1. Ví dụ handler cho 404

~~~java
@RestControllerAdvice
public class OrderErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<Map<String, String>> handle(
            OrderNotFoundException ex) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "ORDER_NOT_FOUND"));
    }
}
~~~

Đây là snippet minh họa; để compile cần import các class Spring và Java cùng định nghĩa `OrderNotFoundException`. Ý nghĩa chính: **exception từ service không tự biến thành JSON lỗi theo contract** nếu ứng dụng không có cơ chế xử lý tương ứng.

Một contract chỉ kiểm tra status `404` có thể pass vì router không tìm thấy endpoint, trong khi lỗi “đơn hàng không tồn tại” chưa được triển khai. Hãy kiểm tra **error body** và path hợp lệ để tránh kết luận sai.

## 11. Kiểm tra request có body: POST và validation

RestAssuredMockMvc cũng dùng cho contract `POST`, `PUT` hoặc `PATCH` có JSON body. Ví dụ:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_order_valid')

    request {
        method POST()
        urlPath('/api/orders')
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: 'CUS-7',
            items: [[sku: 'BK-1', quantity: 2]]
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-200',
            status: 'CREATED'
        )
    }
}
~~~

Để generated test này đạt, web slice phải có:

- Controller đăng ký `POST /api/orders`.
- JSON message converter deserialize được body.
- Bean Validation chạy nếu controller có `@Valid` hoặc constraint tương ứng.
- Service dependency hoặc mock được cấu hình trả response tương ứng.
- HTTP status `201` và body JSON đúng schema.

**Cảnh báo:** Nếu bạn mock trực tiếp controller hoặc bỏ qua validation/filter chỉ để có response mong muốn, generated test có thể xanh mà không bảo vệ đúng hành vi HTTP cần thiết.

### 11.1. Cách kiểm tra nhánh input không hợp lệ

Một contract lỗi có thể yêu cầu:

~~~groovy
request {
    method POST()
    urlPath('/api/orders')
    headers {
        contentType(applicationJson())
    }
    body(customerId: '')
}

response {
    status BAD_REQUEST()
    headers {
        contentType(applicationJson())
    }
    body(code: 'VALIDATION_FAILED')
}
~~~

Khi chạy với `@WebMvcTest`, request phải đi qua MVC validation và exception mapping phù hợp; base class không nên đưa một service mock giả lập `400` nếu mục tiêu là kiểm tra validator ở web layer. Nếu API muốn error code `VALIDATION_FAILED`, producer phải có handler/mapper tạo field này, không mặc định Spring Boot sẽ tự sinh đúng body đó.

## 12. Matcher và giá trị hai phía trong generated test

Một số trường như ID hoặc timestamp có thể biến đổi. Spring Cloud Contract có thể dùng matcher thay cho literal cứng:

~~~groovy
response {
    status CREATED()
    headers {
        contentType(applicationJson())
    }
    body(
        orderId: 'ORD-200',
        status: 'CREATED'
    )
    bodyMatchers {
        jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
    }
}
~~~

Với matcher này:

- Stub cho consumer có thể dùng giá trị mẫu `ORD-200`.
- Generated producer test có thể chấp nhận ID như `ORD-345` nếu nó khớp `ORD-[0-9]+`.
- `status: CREATED` vẫn là một giá trị nghiệp vụ cần kiểm tra chính xác nếu không bị thay bằng matcher.

Điều quan trọng: **RestAssuredMockMvc chỉ là cơ chế gọi HTTP trong test**, không quyết định matcher nào nên dùng. Các assertion đến từ DSL và các quy tắc được plugin sinh ra. Nếu generated test chấp nhận một response sai kiểu do matcher quá rộng, sửa contract/matcher, không sửa cách khởi tạo MockMvc.

### 12.1. Matcher ở request

~~~groovy
body(
    customerId: $(consumer(regex('CUS-[0-9]+')),
                  producer('CUS-7'))
)
~~~

Generated producer test dùng **giá trị `CUS-7` cụ thể** để gửi vào controller. Phía consumer stub có thể chấp nhận các mã phù hợp pattern. Base class nên chuẩn bị fixture cho `CUS-7` và các tình huống producer-side thực sự được sinh test.

Đừng nghĩ rằng một generated test dùng `CUS-7` chứng minh producer hoạt động đúng với toàn bộ dải mã khách hàng. Với hành vi tổng quát, bổ sung tests khác theo rủi ro.

## 13. Cấu hình security: không tắt filter khi hợp đồng cần kiểm tra chúng

Với Spring Security, test web slice có thể trả `401 Unauthorized` hoặc `403 Forbidden` dù controller và fixture đúng. Đó chưa chắc là lỗi contract; cần xem API đã công bố yêu cầu xác thực nào.

Một số dự án dùng:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

để bỏ filter trong test. Điều này có thể giúp kịch bản đơn giản chạy, nhưng **đồng thời loại khỏi kiểm chứng những quy tắc lọc request**, bao gồm security filter. Không coi đây là cách chữa mặc định cho mọi lỗi `403`.

Các lựa chọn hợp lý hơn, tùy hợp đồng:

1. Cấp principal/quyền phù hợp trong Spring Security test context cho request hợp lệ.
2. Khai báo header/token mẫu đúng chính sách và cấu hình test authentication tương ứng.
3. Viết contract riêng cho `401`/`403` nếu consumer thực sự phụ thuộc hai phản hồi này.
4. Chỉ bỏ filter khi phạm vi kiểm thử **được xác định rõ là controller contract không bao gồm security**, và có security tests riêng.

### 13.1. CSRF với POST, PUT, PATCH, DELETE

Nếu ứng dụng dùng bảo vệ CSRF và contract gửi request thay đổi trạng thái, generated test có thể gặp `403` do thiếu CSRF token. Giải pháp phải thống nhất với **cơ chế xác thực công khai** của API. Không vô hiệu hóa CSRF trong production chỉ để test đạt; cũng không thêm token vào contract nếu consumer thực tế không sử dụng mô hình cookie/CSRF đó.

## 14. Các vấn đề thường gặp với `@WebMvcTest`

`@WebMvcTest` giúp giảm chi phí khởi tạo nhưng không nạp mọi bean ứng dụng. Một số lỗi dễ gặp:

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `UnsatisfiedDependencyException` | Controller cần service chưa có trong web slice | Thêm mock bean hoặc import dependency có chủ đích |
| `NoSuchBeanDefinitionException` | Web configuration/custom converter/handler chưa có | Import cấu hình cần cho API contract |
| `404` dù URL đúng | Controller không có trong slice hoặc mapping khác | Đối chiếu `@WebMvcTest` và `@RequestMapping` |
| `401`/`403` | Security filters hoạt động, test thiếu auth/CSRF | Thiết lập security test theo giao diện API |
| `500` | Mock trả null hoặc controller ném exception chưa xử lý | Sửa fixture/mock/exception handler |
| Response JSON field thiếu | DTO serialization/naming khác contract | Kiểm tra getter/record/Jackson annotations |
| `Content-Type` khác | Controller produces/converters/header setup | Kiểm tra media type được công bố |
| Trả `404` ở hợp đồng not found nhưng body khác | Route/exception handler không đúng | Kiểm tra đúng path và mapping lỗi |
| Generated test không nhận base class | Plugin chưa trỏ đúng `baseClassForTests` | Kiểm tra tên đầy đủ và generated source |
| RestAssuredMockMvc chưa được thiết lập | Không có `mockMvc(...)` hoặc hook không chạy | Kiểm tra `@BeforeEach`, JUnit và inheritance |

### 14.1. Khi controller gọi nhiều dependency

Giả sử `OrderController` dùng `OrderService` và `CustomerPermissionService`. Nếu `@WebMvcTest` chỉ mock một dependency, context có thể không khởi tạo được hoặc request đi vào nhánh không mong muốn. Hãy khai báo các mock thật sự cần để controller xử lý request, nhưng tránh biến base class thành một “bộ mô phỏng toàn bộ hệ thống” khó bảo trì.

### 14.2. Không trộn nhầm Spring MVC và WebFlux

Một application thuần WebFlux với `@RestController` và reactive routing có thể cần WebTestClient hoặc HTTP test mode thích hợp. `MockMvc` kiểm tra Spring MVC Servlet stack; việc chọn sai mode có thể làm test không chạy được dù contract DSL hoàn toàn hợp lệ.

## 15. Cách đọc generated test để xác định lỗi setup hay breaking change

Giả sử CI báo:

~~~text
Expected HTTP status: 200
Actual HTTP status: 404
Request: GET /api/orders/ORD-123
~~~

Đừng sửa DSL thành `404` ngay. Thực hiện:

1. **Kiểm tra request:** Generated test đã gọi đúng method và path trong contract chưa?
2. **Kiểm tra route:** `OrderController` thực sự được nạp trong Spring MVC context chưa?
3. **Kiểm tra fixture:** `OrderService.findById("ORD-123")` có trả `OrderView` như base class setup không?
4. **Kiểm tra filters:** Có redirect, auth hay context-path ảnh hưởng request không?
5. **Kiểm tra response thực:** Nếu endpoint thật đã đổi không tương thích, trao đổi với consumer trước khi thay contract.

Ví dụ lỗi khác:

~~~text
Expected JSON field: $.totalAmount = 120000
Actual JSON field: $.totalAmount = "120000"
~~~

Nếu consumer cam kết nhận Number, đây là sai lệch **kiểu JSON**. MockMvc và RestAssuredMockMvc đang làm việc đúng: chúng chuyển request và trả response để assertion phát hiện lỗi. Sửa producer DTO/serializer hoặc thương lượng thay đổi API, **không đổi matcher thành một regex bất kỳ để che lỗi**.

### 15.1. Phân biệt ba lớp nguyên nhân

| Nhóm lỗi | Ví dụ | Nơi cần sửa |
| --- | --- | --- |
| **Build / generation** | Không sinh test, không compile, thiếu dependency | Plugin, dependency, source path, JUnit |
| **Test infrastructure / setup** | Context lỗi, mock sai, thiếu dữ liệu, port/client mode không đúng | Base class, fixture, Spring test configuration |
| **Contract mismatch thực sự** | Method/path/status/JSON thay đổi so với cam kết | Producer hoặc contract đã được các bên đồng thuận cập nhật |

**Đừng sửa file Java generated test trực tiếp.** Chúng được sinh lại khi build; nguồn thay đổi bền vững là contract DSL, cấu hình plugin, base class, fixture hoặc code producer.

## 16. Khi có nhiều nhóm contract: base class chung hay tách riêng?

Không phải mọi endpoint đều cần cùng một test context. Ví dụ một producer có:

- `/api/orders/**` dùng controller Spring MVC và mocked `OrderService`.
- `/api/payments/**` cần một test setup khác.
- Hợp đồng messaging dùng trigger/destination, không phải MockMvc.

Nếu tất cả generated tests kế thừa một base class quá lớn, setup có thể nạp những bean không liên quan và tăng chi phí bảo trì.

Các chiến lược:

1. **Một base class chung** khi tất cả HTTP contracts thật sự chia sẻ cấu hình MVC/test data.
2. **Base class theo package hoặc thư mục hợp đồng** khi cần môi trường/controller khác nhau.
3. **Base class cho HTTP và messaging riêng** khi công cụ, trigger và verifier khác nhau.
4. **Mở rộng một lớp hỗ trợ chung** cho setup dùng lại, nhưng đừng để lớp chung giữ trạng thái mutable giữa tests.

Spring Cloud Contract hỗ trợ cấu hình base class/mapping trong plugin; tên option và cơ chế ánh xạ phụ thuộc Maven/Gradle plugin và version. Khi thay đổi mapping, **kiểm tra generated `extends`** của từng nhóm, không chỉ nhìn nội dung cấu hình.

## 17. Lỗi vì dữ liệu bị chia sẻ giữa các test

Một test có thể mutate trạng thái của mock, singleton hoặc database fixture khiến test sau trả kết quả khác. Với bộ contract lớn:

- Thiết kế từng test **độc lập và có dữ liệu đầu vào rõ ràng**.
- Stub Mockito cho đúng điều kiện sử dụng của từng contract.
- Tránh phụ thuộc thứ tự chạy test.
- Không để các giá trị thời gian, ID hoặc random dữ liệu vào fixture trừ khi có matcher phù hợp.
- Nếu dùng database, chọn rollback/cleanup/fixture strategy tương ứng.
- Nếu RestAssuredMockMvc giữ cấu hình toàn cục, đảm bảo mỗi test nạp cấu hình cần thiết trước khi gọi.

### 17.1. Mock quá rộng cũng có thể che lỗi

Ví dụ:

~~~java
given(orderService.findById(anyString()))
    .willReturn(new OrderView(
        "ORD-123", "CONFIRMED", 120000L, true
    ));
~~~

Mock này trả cùng một đơn hàng cho **mọi** ID. Nó có thể làm test GET đơn hàng thành công đạt, nhưng không kiểm chứng được logic not-found cho ID khác. Với contract `ORD-404`, cần stub hoặc fixture đúng nhánh; khi cần kiểm tra service thật, không nên mock mất toàn bộ logic lookup.

## 18. RestAssuredMockMvc không thay thế consumer Stub Runner

Sau khi generated producer tests đạt, Spring Cloud Contract có thể sinh và đóng gói **stubs** để consumer dùng qua **Stub Runner**. Hai quy trình có cùng nguồn contract nhưng khác vai trò:

| Câu hỏi | Producer + RestAssuredMockMvc | Consumer + Stub Runner |
| --- | --- | --- |
| Đang thử code của ai? | Producer | Consumer |
| Có gọi controller thật không? | Có, trong Spring MVC test context | Không; gọi stub mô phỏng producer |
| Response đến từ đâu? | Controller/serializer/handler của producer | Mapping/template được sinh từ DSL |
| Ai quyết định request? | Generated producer test | Consumer test code |
| Sai lệch được phát hiện | Producer không đáp ứng contract | Consumer gọi sai hoặc xử lý response sai |
| Cần `ContractVerifierBase` không? | Có nếu generated producer tests yêu cầu | Không theo cách của producer base; consumer có setup riêng |

Một consumer test chạy xanh với stub **không chứng minh producer thật tương thích** nếu producer verification không được thực thi. Ngược lại, producer test xanh với MockMvc không chứng minh consumer đã gửi đúng headers hoặc xử lý mọi nhánh lỗi. Vì vậy CI nên dùng cả hai phía đúng phạm vi.

## 19. Đưa generated tests dùng MockMvc vào CI

Với Maven đã cấu hình plugin và base class, producer có thể chạy:

~~~bash
./mvnw -B clean verify
~~~

Với Gradle đã cấu hình plugin Spring Cloud Contract và test tasks tương ứng:

~~~bash
./gradlew clean build
~~~

Đây là **ví dụ lệnh**, không phải bằng chứng rằng pipeline đã thực sự chạy Contract Verifier. CI cần xác nhận:

1. Các file contract trong nguồn được plugin phát hiện.
2. Generated Java tests được sinh và biên dịch.
3. Generated tests kế thừa base class đúng và dùng HTTP test mode `MOCKMVC` như dự định.
4. JUnit/Surefire/Gradle test runner thực sự chạy các tests; không skip hoặc báo `0 tests`.
5. MockMvc context và fixture được dựng ổn định.
6. Các request/assertions quan trọng được kiểm chứng.
7. Chỉ đóng gói, phát hành stub từ producer đã vượt qua verification.
8. Consumer CI kiểm thử với stub artifact/version tương ứng.

### 19.1. Cần chú ý gì khi nâng cấp phiên bản?

Việc nâng Spring Boot/Spring Framework/Spring Cloud Contract có thể ảnh hưởng:

- Tên hoặc package annotation Mockito test (`@MockBean` so với `@MockitoBean`).
- Phiên bản JUnit và cách runner chạy generated tests.
- Kiểu generated Java source và assertions.
- Cách xử lý filter/security trong MockMvc.
- Cấu hình plugin và vị trí generated test sources.
- Khả năng tương thích RestAssuredMockMvc với version thư viện liên quan.

Sau nâng cấp, **đọc lại generated tests và chạy cả producer/consumer tests** trước khi coi việc thay dependency là an toàn.

## 20. Bài thực hành: xây base test cho Catalog Service

Giả sử `Catalog Service` công bố:

~~~http
GET /api/products/P-100 HTTP/1.1
Accept: application/json
~~~

Response:

~~~json
{
  "productId": "P-100",
  "name": "Wireless Mouse",
  "price": 350000,
  "available": true
}
~~~

### 20.1. Nhiệm vụ A — Tạo contract

Viết file `src/test/resources/contracts/products/get_product.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_product')

    request {
        method GET()
        urlPath('/api/products/P-100')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            productId: 'P-100',
            name: 'Wireless Mouse',
            price: 350000,
            available: true
        )
    }
}
~~~

### 20.2. Nhiệm vụ B — Tạo base class

Giả sử dự án có `ProductController` và `ProductService`. Tạo `ContractVerifierBase`:

~~~java
package com.example.catalog.contract;

import com.example.catalog.api.ProductController;
import com.example.catalog.api.ProductView;
import com.example.catalog.application.ProductService;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;

@WebMvcTest(ProductController.class)
public abstract class ContractVerifierBase {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ProductService productService;

    @BeforeEach
    protected void setup() {
        given(productService.findById("P-100"))
            .willReturn(new ProductView(
                "P-100", "Wireless Mouse", 350000L, true
            ));

        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Đây là ví dụ cho Spring Framework 6.2+ với `@MockitoBean`. Bạn cần có `ProductService.findById` và constructor của `ProductView` tương ứng, đồng thời cấu hình plugin để generated tests kế thừa `com.example.catalog.contract.ContractVerifierBase`.

### 20.3. Nhiệm vụ C — Xác minh generated test

Sau khi cấu hình Spring Cloud Contract Verifier trong dự án thực hành:

1. Sinh và chạy generated tests.
2. Mở generated source tương ứng với `get_product`.
3. Xác định HTTP method, path, request header và assertion `200`.
4. Xác định assertions cho `productId`, `name`, `price`, `available`.
5. Xác nhận test gọi qua `RestAssuredMockMvc` và được base class cung cấp `MockMvc`.

### 20.4. Nhiệm vụ D — Cố ý làm test thất bại

Thực hiện lần lượt:

| Thay đổi | Dự đoán |
| --- | --- |
| Bỏ `RestAssuredMockMvc.mockMvc(mockMvc)` nhưng không cấu hình thay thế | Generated test có thể không có MockMvc để thực thi |
| Bỏ mock `ProductService` khỏi `@WebMvcTest` | Context có thể không khởi tạo do thiếu dependency |
| Mock trả `price` là String `"350000"` thay vì Number | Có thể phát hiện sai kiểu nếu JSON contract ràng buộc đúng |
| Đổi controller path thành `/api/items/{id}` và bỏ path cũ | Generated request có thể nhận `404` |
| Đổi response `available` từ boolean sang String | JSON assertion/type có thể thất bại |
| Thêm filter auth mà test không thiết lập principal | Có thể nhận `401`/`403` tùy policy |
| Chỉ sửa `get_product.groovy` thành response mới để test xanh | Có nguy cơ che breaking change đối với consumer cũ |

### 20.5. Câu hỏi tự đánh giá

1. Vì sao `MockMvc` không cần một TCP port thật?
2. Tại sao generated test cần kế thừa một base class?
3. Khi nào chọn `@WebMvcTest` thay cho `@SpringBootTest` và ngược lại?
4. Nếu test trả `404` vì fixture không tồn tại, đó có phải breaking change không?
5. Vì sao bỏ security filters bằng `addFilters = false` không phải cách sửa mặc định?
6. Khi nâng cấp sang Spring Framework 6.2+, annotation mock bean cần kiểm tra điều gì?
7. Producer test xanh có đủ để kết luận consumer code đang xử lý stub đúng không?
8. Nếu CI báo `BUILD SUCCESS` nhưng generated tests không được chạy, cần kiểm tra phần nào?

**Định hướng:** MockMvc chạy pipeline MVC trong JVM; base class cung cấp context và dữ liệu; chọn scope test theo rủi ro; kiểm tra fixture trước khi kết luận breaking change; giữ security tests; tương thích version annotation; producer và consumer tests bổ trợ nhau; `0 tests` không phải bằng chứng hợp đồng được xác minh.

## 21. Checklist trước khi dùng RestAssuredMockMvc trong base test

- [ ] Producer thực sự dùng Spring MVC hoặc môi trường tương thích với MockMvc.
- [ ] Contract DSL mô tả đúng request và response mà consumer dùng.
- [ ] Plugin cấu hình generated test mode MockMvc và base class tương ứng.
- [ ] Base class kế thừa/visibility phù hợp để generated tests sử dụng.
- [ ] `@WebMvcTest` hoặc `@SpringBootTest` được chọn có chủ đích theo test scope.
- [ ] Có `MockMvc` hợp lệ và được truyền vào `RestAssuredMockMvc.mockMvc(mockMvc)` trong hook test.
- [ ] Controller và các web configuration/exception handlers quan trọng được nạp.
- [ ] Service/repository dependency được mock hoặc cung cấp fixture tái lập theo phạm vi kiểm thử.
- [ ] Không vô hiệu hóa security/validation vô ý để làm test xanh.
- [ ] Status, headers và JSON fields được kiểm tra theo đúng matcher trong contract.
- [ ] Mỗi test độc lập, không phụ thuộc mock hoặc database state từ test trước.
- [ ] Đã phân biệt failure do build/setup với contract mismatch thật.
- [ ] Generated Java tests được sinh, biên dịch và thực thi trong CI, không bị skip.
- [ ] Stub chỉ được phát hành sau khi producer verification đạt.
- [ ] Consumer tiếp tục kiểm thử qua Stub Runner với artifact đúng phiên bản.

## 22. Tài liệu tham khảo

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, HTTP test modes, Maven/Gradle plugin và stubs.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): cách khai báo HTTP request/response.
- [Spring Cloud Contract — Developing Your First Application](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): quy trình producer verification, base test và generated tests.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): vai trò MockMvc trong kiểm thử Spring MVC.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@WebMvcTest` và các test slice.

**Ghi nhớ:** **RestAssuredMockMvc là cầu nối giữa generated producer tests và Spring MVC test context**. Base class cung cấp `MockMvc`, chuẩn bị dữ liệu/bean phù hợp rồi gọi `RestAssuredMockMvc.mockMvc(mockMvc)` trước khi test thực thi. Hãy phân biệt **web-slice setup**, **full-context setup** và **HTTP server thật**; đọc generated assertions thay vì chỉ nhìn build xanh. Khi producer verification và consumer Stub Runner đều chạy đúng trong CI, các thay đổi HTTP không tương thích được phát hiện sớm hơn.
