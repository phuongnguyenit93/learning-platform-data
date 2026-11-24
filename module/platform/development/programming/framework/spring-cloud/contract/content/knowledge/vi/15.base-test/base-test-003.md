# Khởi tạo controller hoặc ứng dụng cần kiểm chứng

## Mục tiêu học tập

Trong **Spring Cloud Contract**, hợp đồng mô tả hành vi mà **producer** (dịch vụ cung cấp API hoặc phát thông điệp) cam kết với **consumer** (dịch vụ gọi API hoặc nhận thông điệp). Hợp đồng viết bằng **Groovy/YAML DSL** có thể được dùng để sinh **test phía producer** và **stub** cho consumer kiểm thử qua **Stub Runner**. Khi tích hợp CI, hai loại test giúp phát hiện những thay đổi giao diện không tương thích.

Nhưng generated producer test không thể tự kiểm chứng một controller chưa được khởi tạo. Một trong những nhiệm vụ quan trọng nhất của **base test class** là dựng đúng **đối tượng hoặc ứng dụng cần kiểm chứng**, với trạng thái đủ xác định để request được sinh từ hợp đồng nhận về response mong đợi.

Sau bài học này, bạn có thể:

- Giải thích vai trò của `baseClassForTests` trong quá trình sinh test HTTP.
- Khởi tạo một **controller độc lập** bằng `RestAssuredMockMvc.standaloneSetup(...)`.
- Khởi tạo **Spring WebApplicationContext** rồi dùng `RestAssuredMockMvc.webAppContextSetup(...)`.
- Phân biệt `MOCKMVC`, `WEBTESTCLIENT` và `EXPLICIT`, đặc biệt là khác biệt giữa gọi in-process và gửi HTTP qua socket thật.
- Chuẩn bị fixture, fake/mock dependency và cấu hình test để generated test chạy ổn định.
- Đọc generated test và lỗi chạy test để xác nhận mình đang kiểm chứng **producer thực sự**, không phải một stub tự trả dữ liệu.
- Biết phạm vi nào nên được bảo vệ bằng producer contract test và phạm vi nào cần integration test, consumer test với Stub Runner hoặc CI bổ sung.

## 1. Base test class nằm ở đâu trong chuỗi kiểm chứng?

Giả sử **Inventory Service** là producer của API tồn kho:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

**Checkout Service** là consumer: nó cần đọc `available` và `quantity` để quyết định cho phép đặt hàng. Nhóm producer viết hợp đồng kiểm tra phản hồi này; công cụ tạo một test gửi `GET /api/inventory/SKU-101` và kiểm tra status, header, body.

Tuy nhiên, một câu hỏi vẫn còn: **test gửi request vào đâu?**

- Vào một `InventoryController` do test khởi tạo trực tiếp?
- Vào toàn bộ web context của ứng dụng Spring Boot?
- Hay vào ứng dụng đang lắng nghe trên một cổng TCP thật?

Base class cung cấp phần **setup chung** để generated tests hoạt động đúng với lựa chọn đó.

~~~mermaid
flowchart TD
    A["Groovy/YAML contract"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer test"]
    C --> D["Base test class"]
    D --> E{"Test mode"}
    E -->|MOCKMVC standalone| F["Controller + fake/mock service"]
    E -->|MOCKMVC context| G["Spring WebApplicationContext"]
    E -->|EXPLICIT| H["Ứng dụng HTTP chạy trên cổng thực"]
    E -->|WEBTESTCLIENT| I["WebFlux handler/controller"]
    B --> J["Generated stub artifact"]
    J --> K["Stub Runner cho consumer test"]
~~~

**Lưu ý:** generated producer test chạy với code producer; stub artifact dành cho consumer. Nếu base class của producer vô tình trả response giả cố định mà không đi qua controller/logic cần bảo vệ, test có thể xanh nhưng không mang lại bằng chứng như nhóm mong muốn.

## 2. Ba thành phần cần khớp nhau

Một bài kiểm thử producer chỉ đáng tin khi có đủ ba phần:

| Thành phần | Nội dung ví dụ | Trách nhiệm |
|---|---|---|
| **Contract** | `GET /api/inventory/SKU-101` phải trả `200` với JSON đã thống nhất | Xác định hành vi cần kiểm chứng |
| **Generated test** | Gửi request, assert status/header/JSON | Kiểm tra producer theo contract |
| **Base test class** | Dựng controller hoặc ứng dụng, cung cấp service và dữ liệu nền | Làm cho generated test gọi được đối tượng cần kiểm chứng |

Nếu chỉ có contract mà chưa có controller, generated test có thể lỗi vì chưa thiết lập MockMvc, trả `404` hoặc không dựng được context.

Nếu có controller nhưng service đọc từ database thật đang trống, test có thể trả `404` thay vì `200` do **dữ liệu nền**, không phải do cú pháp DSL.

Nếu base class thay hoàn toàn controller bằng một WireMock stub tự trả đúng JSON, test không còn kiểm chứng producer implementation như dự định.

Vì vậy, **setup của base class là một quyết định về phạm vi kiểm thử**, không chỉ là cách làm cho pipeline hết báo đỏ.

## 3. Định nghĩa contract HTTP trước khi viết base class

Ví dụ Groovy DSL đặt tại `src/test/resources/contracts/inventory/stockAvailable.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Ton kho SKU-101 con 8 san pham'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8
        )
    }
}
~~~

Đây là hợp đồng **producer phải đáp ứng**; nó không chỉ định controller cần được tạo bằng `new` hay ứng dụng cần chạy ở cổng nào. Phần đó là trách nhiệm của **base class và cấu hình plugin**.

YAML DSL có thể biểu đạt cùng tình huống, chẳng hạn:

~~~yaml
description: 'Ton kho SKU-101 con 8 san pham'
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
    quantity: 8
~~~

Trong project thực, hãy **chọn một định dạng** cho tình huống này, tránh giữ cả Groovy lẫn YAML như hai hợp đồng trùng điều kiện request mà không có lý do.

## 4. Khai báo base class trong plugin

### Maven

Trong module **producer**, cấu hình Spring Cloud Contract Maven plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <!-- Điền phiên bản plugin tương thích với Spring Boot/Cloud BOM -->
            <version>REPLACE_WITH_MATCHING_CONTRACT_VERSION</version>
            <extensions>true</extensions>
            <configuration>
                <testMode>MOCKMVC</testMode>
                <testFramework>JUNIT5</testFramework>
                <baseClassForTests>
                    com.example.inventory.contract.InventoryContractBase
                </baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trong ví dụ, `InventoryContractBase` là **tên class do nhóm tự tạo**, không phải class được Spring Cloud Contract sinh sẵn. Plugin dùng tên đó để các generated tests kế thừa hoặc gắn với setup tương ứng.

`REPLACE_WITH_MATCHING_CONTRACT_VERSION` là placeholder cần thay bằng version thực tế; không phải một artifact có thể tải về. Thông thường dự án đã dùng Spring Boot parent/BOM và Spring Cloud BOM để quản lý các dependency tương thích, nhưng **phiên bản build plugin** vẫn cần được quản lý rõ.

Dependency producer thường cần:

~~~xml
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
~~~

Ứng dụng HTTP thực tế vẫn cần starter phù hợp, chẳng hạn `spring-boot-starter-web` cho Spring MVC. Các thư viện kiểm thử thường ở **scope test**; không cần đóng chúng vào runtime production chỉ để sinh contract test.

### Gradle

Với module producer đã áp dụng Spring Cloud Contract Gradle plugin phù hợp:

~~~groovy
contracts {
    testMode = 'MOCKMVC'
    testFramework = 'JUNIT5'
    baseClassForTests =
        'com.example.inventory.contract.InventoryContractBase'
}
~~~

Đây là phần cấu hình `contracts`, không phải toàn bộ `build.gradle`. Dự án cần `java`/Spring Boot plugin, repositories, BOM và dependencies phù hợp.

**Chú ý phiên bản:** cách chỉ định mode, framework kiểm thử, task và tên output có thể khác giữa các dòng plugin. Nếu dự án dùng JUnit 5, base class cần lifecycle hook mà generated test/framework thực sự hỗ trợ; không chép `@Before` của ví dụ JUnit 4 vào code JUnit 5 rồi giả định nó được gọi.

## 5. Cách 1 — Khởi tạo controller độc lập bằng MockMvc

Đây là cách nhanh và dễ kiểm soát khi muốn kiểm chứng **HTTP mapping, serialization và hành vi của controller** với service giả.

### Một controller tối giản

Giả sử code producer có kiểu response và service sau (Java 17+):

~~~java
package com.example.inventory;

public record StockResponse(
    String sku,
    boolean available,
    int quantity
) {}
~~~

~~~java
package com.example.inventory;

import java.util.Optional;

public interface InventoryService {
    Optional<StockResponse> findBySku(String sku);
}
~~~

Controller sản xuất có thể là:

~~~java
package com.example.inventory;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {
    private final InventoryService inventoryService;

    public InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @GetMapping("/{sku}")
    public ResponseEntity<StockResponse> find(@PathVariable("sku") String sku) {
        return inventoryService.findBySku(sku)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Controller không biết Spring Cloud Contract. Nó chỉ triển khai HTTP contract. Trong production, `InventoryService` có thể đọc database, tính tồn kho hoặc truy cập dịch vụ khác; trong contract test, ta có thể cung cấp **một service mock**.

### Base test class sử dụng `standaloneSetup`

Ví dụ file `src/test/java/com/example/inventory/contract/InventoryContractBase.java`:

~~~java
package com.example.inventory.contract;

import com.example.inventory.InventoryController;
import com.example.inventory.InventoryService;
import com.example.inventory.StockResponse;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;

import java.util.Optional;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public abstract class InventoryContractBase {

    @BeforeEach
    protected void setUpContractController() {
        InventoryService service = mock(InventoryService.class);

        when(service.findBySku("SKU-101"))
            .thenReturn(Optional.of(
                new StockResponse("SKU-101", true, 8)
            ));

        RestAssuredMockMvc.standaloneSetup(
            new InventoryController(service)
        );
    }
}
~~~

**Những gì ví dụ đang làm:**

1. Tạo mock `InventoryService` riêng cho test.
2. Quy định `SKU-101` trả về `StockResponse` với các giá trị mà contract cần.
3. Khởi tạo **InventoryController thật** từ mã producer, truyền mock vào constructor.
4. Gắn controller vào `RestAssuredMockMvc.standaloneSetup(...)` để generated test trong chế độ MockMvc gửi request in-process.
5. Không cần start web server trên TCP port.

**Kết quả:** nếu controller đổi mapping `/{sku}` sai, trả status khác hoặc serialize JSON khác contract, generated producer test có thể thất bại.

Tuy nhiên, mock `InventoryService` không chứng minh database/repository thật của producer hoạt động đúng. Vì vậy cần nhận biết **ranh giới kiểm thử**: đây là kiểm thử contract ở tầng controller với dependency được cô lập, không phải end-to-end test.

### Khi nào cách này phù hợp?

- Controller có constructor injection và dễ khởi tạo.
- Request mapping, serialization và xử lý của controller cần được bảo vệ.
- Service phụ thuộc database/network gây chậm hoặc khó tái lập.
- Nhóm muốn hợp đồng chạy nhanh ở mỗi PR.
- Hành vi có thể đưa về một số tình huống xác định bằng mock/fake.

### Những điểm dễ bỏ sót khi standalone

`standaloneSetup` không tự dựng **toàn bộ** cấu hình Spring Boot. Các thành phần cần cấu hình hoặc bổ sung riêng nếu contract phụ thuộc vào chúng:

- `@ControllerAdvice` / exception handler toàn cục.
- Converter tùy chỉnh, Jackson module, format ngày/giờ đặc thù.
- Filter, interceptor, Spring Security filter chain, authentication.
- Validator và cấu hình validation đặc biệt.
- Các bean do Spring quản lý thay vì được truyền thủ công.

Nếu contract có `404` hoặc error body từ exception handler toàn cục, base class chỉ tạo controller độc lập có thể bỏ qua handler và cho kết quả khác ứng dụng thật. Khi đó hãy bổ sung cấu hình MockMvc tương ứng hoặc chuyển sang test với application context.

**Không “chữa” lỗi bằng cách làm mock trả nguyên HTTP response mong đợi rồi không gọi qua controller.** Như vậy test có thể không chứng minh điều consumer cần.

## 6. Cách 2 — Dựng WebApplicationContext của ứng dụng Spring Boot

Khi giao diện HTTP phụ thuộc nhiều vào cấu hình MVC của ứng dụng, có thể khởi tạo web context và để Spring quản lý controller, serialization, bean wiring cùng các thành phần khác.

Ví dụ base class:

~~~java
package com.example.inventory.contract;

import com.example.inventory.InventoryApplication;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.context.WebApplicationContext;

@SpringBootTest(
    classes = InventoryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@ActiveProfiles("contract")
public abstract class InventoryContractBase {

    @Autowired
    WebApplicationContext webApplicationContext;

    @BeforeEach
    protected void setUpContractContext() {
        RestAssuredMockMvc.webAppContextSetup(
            webApplicationContext
        );
    }
}
~~~

Ở đây:

- `@SpringBootTest` khởi tạo **Spring application context** của Inventory Service.
- `webEnvironment = MOCK` không yêu cầu mở cổng HTTP thật.
- `RestAssuredMockMvc.webAppContextSetup(...)` gắn generated MockMvc test với web context.
- Profile `contract` chỉ là tên minh họa: dự án phải cung cấp cấu hình và fixture tương ứng; việc khai báo profile không tự tạo database/fake.
- Generated test vẫn dùng **MockMvc in-process** nếu plugin chọn `MOCKMVC`.

**So với standalone**, cách này kiểm chứng nhiều thành phần cấu hình thực của ứng dụng hơn, nhưng có thể chậm và dễ phụ thuộc vào broker, database, cấu hình môi trường hoặc các bean không liên quan.

### Chuẩn bị dữ liệu trong context test

Nếu Inventory Service dùng repository, cần bảo đảm:

- Có bản ghi `SKU-101` với số lượng `8` trước khi request chạy.
- Không có dữ liệu từ test khác làm thay đổi kết quả.
- Profile `contract` trỏ tới tài nguyên test, không phải database production.
- Kết quả không phụ thuộc ngày giờ, random, consumer bên ngoài hoặc trạng thái tồn tại trước đó.

Có thể áp dụng **database test cô lập**, bean fake, mock được đăng ký vào Spring test context hoặc seed dữ liệu trong lifecycle hook. Tên annotation và cách override bean cụ thể phụ thuộc phiên bản Spring Boot/Spring Framework; chẳng hạn một số dòng hiện đại sử dụng `@MockitoBean`, trong khi dự án cũ có thể dùng `@MockBean`. Hãy chọn cơ chế hỗ trợ bởi phiên bản dự án, thay vì sao chép mọi annotation trong tài liệu khác nhau rồi dùng đồng thời.

Nếu cần rollback/transaction, hãy kiểm tra transaction của test và request có thực sự chia sẻ cùng ranh giới hay không; với HTTP qua server thực, transaction của test method không nhất thiết bao trùm transaction do server xử lý.

### Cẩn trọng với security và filter

`webAppContextSetup` bảo đảm MockMvc có web context, nhưng mức độ áp dụng **Spring Security filter chain** và các filter đặc biệt có thể cần cấu hình test bổ sung. Không suy rằng một test `200` không có xác thực đã kiểm tra bảo mật thật. Nếu hợp đồng cam kết `401`/`403` hoặc header security, hãy xem generated test thực sự dùng filter chain nào và bổ sung kiểm thử thích hợp.

## 7. Cách 3 — Chạy ứng dụng trên cổng HTTP thật với EXPLICIT

Nếu cần kiểm chứng giao tiếp qua socket HTTP thật thay vì MockMvc, Spring Cloud Contract hỗ trợ `EXPLICIT` test mode.

Trong Maven plugin:

~~~xml
<configuration>
    <testMode>EXPLICIT</testMode>
    <baseClassForTests>
        com.example.inventory.contract.InventoryHttpContractBase
    </baseClassForTests>
</configuration>
~~~

Hoặc Gradle:

~~~groovy
contracts {
    testMode = 'EXPLICIT'
    baseClassForTests =
        'com.example.inventory.contract.InventoryHttpContractBase'
}
~~~

Base class Spring Boot:

~~~java
package com.example.inventory.contract;

import com.example.inventory.InventoryApplication;
import io.restassured.RestAssured;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
    classes = InventoryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@ActiveProfiles("contract")
public abstract class InventoryHttpContractBase {

    @LocalServerPort
    int port;

    @BeforeEach
    protected void configureHttpClient() {
        RestAssured.baseURI = "http://localhost";
        RestAssured.port = port;
    }
}
~~~

`@LocalServerPort` cung cấp cổng do Spring Boot cấp cho ứng dụng test. `RestAssured` cấu hình URL/port để generated tests của `EXPLICIT` gọi **endpoint thật qua mạng loopback**, thay vì gọi MockMvc trong bộ nhớ.

Những điều cần biết:

- `RANDOM_PORT` tránh tranh chấp cổng cố định trong môi trường CI.
- Start server thật có chi phí cao hơn standalone/controller test.
- Các filter, serialization, servlet container và ranh giới HTTP thực tế được tham gia ở mức gần production hơn.
- Nếu application có database hoặc dịch vụ bên ngoài, cần test configuration cô lập.
- `RestAssured.baseURI` và `RestAssured.port` là cấu hình dùng chung có tính mutable; khi chạy test song song trong một JVM, cần bảo đảm các test không ghi đè cấu hình của nhau.

**Đừng chỉ thêm `@SpringBootTest(RANDOM_PORT)` trong base class và giữ test mode `MOCKMVC` rồi nghĩ request tự đi qua socket.** Chế độ sinh test do plugin quyết định; base class phải **phù hợp** với chế độ ấy.

## 8. Nếu producer là WebFlux/reactive?

Với Spring WebFlux, Spring Cloud Contract có `WEBTESTCLIENT` mode để sinh test dùng WebTestClient thay vì MockMvc. Một base class tối giản có thể dùng:

~~~java
import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import org.junit.jupiter.api.BeforeEach;

public abstract class ReactiveInventoryContractBase {

    @BeforeEach
    protected void setUp() {
        RestAssuredWebTestClient.standaloneSetup(
            new ReactiveInventoryController(/* fake dependencies */)
        );
    }
}
~~~

Đoạn trên chỉ minh họa **ý tưởng**; class `ReactiveInventoryController` và phụ thuộc của nó do dự án định nghĩa. Khi dùng context WebFlux đầy đủ, cần khởi tạo và bind WebTestClient theo cấu hình phù hợp của Spring Cloud Contract và phiên bản thư viện.

| Đặc điểm | `MOCKMVC` | `WEBTESTCLIENT` | `EXPLICIT` |
|---|---|---|---|
| Stack điển hình | Servlet Spring MVC | Spring WebFlux/reactive | HTTP app chạy thật |
| Có bắt buộc TCP socket? | Không | Không nhất thiết | Có |
| Setup cơ bản | `RestAssuredMockMvc.standaloneSetup` hoặc `webAppContextSetup` | `RestAssuredWebTestClient` với controller/context phù hợp | Start server + cấu hình HTTP client |
| Mức độ cô lập | Từ một controller đến web context | Tùy standalone/context | Gần kiểm thử HTTP end-to-end hơn |
| Khi nên chọn | Producer MVC, contract HTTP nhanh | Producer WebFlux | Cần kiểm tra context path, filter/HTTP stack hoặc tích hợp thực |

Không cần dùng đồng thời tất cả mode. Chọn **một mode phù hợp producer** cho nhóm contract đang kiểm thử; có thể có integration tests riêng bằng mode khác khi cần.

## 9. Base class nên chuẩn bị gì và không nên làm gì?

### Những việc base class nên đảm nhiệm

1. **Khởi tạo đúng entry point:** controller thật, web context thật hoặc ứng dụng đang nghe trên cổng thật.
2. **Cung cấp dependency kiểm soát được:** mock/fake hoặc database test có dữ liệu được seed.
3. **Thiết lập request infrastructure:** MockMvc, WebTestClient hoặc RestAssured theo test mode.
4. **Đảm bảo dữ liệu xác định:** SKU và các trạng thái mẫu phải lặp lại giống nhau khi test chạy lại.
5. **Đảm bảo cô lập:** không để test case trước ảnh hưởng test case sau.
6. **Chọn profile và config an toàn:** không gọi production database, broker hoặc API bên ngoài khi không có chủ đích.
7. **Cung cấp helper có ý nghĩa nếu DSL yêu cầu:** ví dụ hàm custom assertion hoặc method được gọi từ contract khi cấu hình cho phép.

### Những việc không nên làm

- Không giả lập **cả response HTTP từ chính endpoint cần kiểm chứng** rồi coi producer contract test đã xác nhận controller.
- Không tạo trạng thái test bằng cách sửa cứng dữ liệu production.
- Không phụ thuộc thứ tự chạy hoặc một random ID mới cho mỗi lần test nếu contract yêu cầu giá trị cụ thể.
- Không dùng base class quá tổng quát chứa hàng chục mock không liên quan rồi để các test tương tác lẫn nhau.
- Không sửa trực tiếp generated tests, vì chúng được tạo lại khi build.
- Không bỏ qua vấn đề false positive: test xanh với mock service chỉ chứng minh **phần controller và mapping được test**; không chứng minh truy vấn DB/thao tác broker thật.

## 10. Tổ chức nhiều base class khi API có nhóm setup khác nhau

Không phải mọi hợp đồng đều phù hợp với một môi trường chung. Ví dụ:

- `inventory`: kiểm thử controller cùng fake `InventoryService`.
- `payments`: cần context có transaction, validator và exception handler.
- `notifications`: cần mode messaging khác HTTP.
- `admin`: cần security test setup khác.

Spring Cloud Contract có cấu hình **base class dùng chung** và cơ chế **gán base class theo package/thư mục contract** (như `packageWithBaseClasses` hoặc mapping base classes tùy plugin). Khi số nhóm có yêu cầu setup khác nhau tăng lên, nên tách một base class có chủ đích cho mỗi nhóm thay vì viết nhiều `if` kiểm tra tên test.

Ví dụ định hướng thư mục:

~~~text
src/test/resources/contracts/
├── inventory/
│   ├── stockAvailable.groovy
│   └── stockNotFound.groovy
└── payments/
    ├── paymentAccepted.yml
    └── paymentRejected.yml

src/test/java/com/example/contract/
├── InventoryContractBase.java
└── PaymentsContractBase.java
~~~

Đường dẫn trên là **gợi ý tổ chức**, không tự kích hoạt việc chọn base class tương ứng. Phải cấu hình mapping theo khả năng của **phiên bản Maven/Gradle plugin**; đọc generated test để xác nhận nó kế thừa đúng base class.

Một quy ước tốt: tên base class nêu rõ **đối tượng được dựng** và **tầng kiểm thử**, ví dụ `InventoryControllerContractBase` hoặc `InventoryHttpServerContractBase`. Nhờ vậy reviewer biết test đang chạy MockMvc độc lập hay ứng dụng thật.

## 11. Generated test được sinh thế nào và cách kiểm chứng setup?

Khi producer build đã có plugin đúng, có thể dùng Maven lifecycle:

~~~bash
./mvnw clean verify
~~~

Với Gradle, dùng những task contract được plugin phiên bản dự án tích hợp; để xem task:

~~~bash
./gradlew tasks --all
~~~

Tùy cấu hình, generated tests thường nằm ở những vùng output như:

~~~text
Maven:
  target/generated-test-sources/contracts/

Gradle:
  build/generated-test-sources/contracts/
~~~

Đây là **đường dẫn thường gặp**, có thể được đổi bởi cấu hình build. Hãy kiểm tra build log.

Khi đọc generated test, tìm:

- Tên base class có đúng `InventoryContractBase` không?
- Test có được biên dịch và **thực sự chạy** không?
- Nó gọi đúng `GET /api/inventory/SKU-101` không?
- Assertion có kiểm tra `200`, JSON `sku`/`available`/`quantity` đúng kiểu không?
- Nó dùng `RestAssuredMockMvc` hay `RestAssured` qua socket đúng với mode đã chọn?
- Có bean, mock, fake hoặc fixture nào chưa được setup khiến test fail ngoài ý định?

Ví dụ logic test được sinh có thể được tóm tắt như sau (**pseudocode**, không phải output nguyên văn của một generator cụ thể):

~~~text
class StockAvailableTest extends InventoryContractBase

test "validate_stockAvailable":
    given:
        GET /api/inventory/SKU-101
        Accept: application/json

    when:
        send request to controller/app prepared by base class

    then:
        status == 200
        Content-Type == application/json
        body.sku == "SKU-101"
        body.available == true
        body.quantity == 8
~~~

**Không nhầm giữa “generated test được sinh” và “generated test đã chạy”.** Có thể plugin tạo file nhưng test runner không khám phá test, test bị disable hoặc filter build bỏ qua. Vì thế phải xem báo cáo test, số test được thực thi và kết quả thực sự.

## 12. Các lỗi setup thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không sinh generated test | Plugin chưa áp dụng, đường dẫn contract sai hoặc build phase/task chưa chạy | Kiểm tra cấu hình plugin, input DSL và log generate |
| Generated test không compile | `baseClassForTests` sai tên/package, class không thuộc test source set hoặc sai framework | Xác nhận full class name, import và JUnit version |
| `RestAssuredMockMvc` chưa được khởi tạo | `@BeforeEach`/`@Before` không chạy hoặc setup chưa gọi | Xem lifecycle hook, generated class và test framework |
| Test trả `404` dù contract chờ `200` | Controller không được đăng ký, URL mapping sai hoặc dữ liệu fixture không tồn tại | Kiểm tra controller thực, base class và request path |
| Test nhận `500` / `NullPointerException` | Service mock thiếu stub hoặc bean chưa khởi tạo | Kiểm tra constructor injection, mock answer và fixture |
| App context khởi động lỗi | Thiếu bean, cấu hình test sai, kết nối DB/broker ngoài | Dùng test profile/fake hoặc context cấu hình phù hợp |
| Response sai JSON format | Standalone chưa có converter/Jackson module cấu hình như production | Dùng context phù hợp hoặc đăng ký converter cần thiết |
| `401`/`403` khác kỳ vọng | Security filter chưa khớp hoặc auth setup khác | Xem filter chain và danh tính test |
| `EXPLICIT` không kết nối được | Server không chạy, port sai, baseURI cũ | Dùng `RANDOM_PORT` và cấu hình RestAssured đúng |
| Test xanh nhưng thay service thật bị lỗi | Mock đã thay service nên không kiểm chứng DB/network | Thêm integration test cho lớp phụ thuộc quan trọng |
| Test lỗi thất thường khi chạy song song | Static RestAssured config hoặc fixture dùng chung bị ghi đè | Cô lập cấu hình/client và dữ liệu; kiểm soát parallel |
| Consumer test vẫn xanh sau thay đổi producer | Consumer dùng stub artifact cũ | Ghim version stub và kiểm chứng cùng revision trong CI |

Một lỗi đáng chú ý là **mismatch giữa JUnit 4 và JUnit 5**. Nhiều ví dụ cũ dùng `org.junit.Before`, trong khi mã JUnit 5 dùng `org.junit.jupiter.api.BeforeEach`. Lifecycle method không chạy sẽ khiến MockMvc hoặc dữ liệu nền không được dựng. Đừng chỉ sửa “test fail” bằng cách bỏ assertion; hãy xác định vì sao setup chưa thực thi.

## 13. Producer test, consumer test và integration test có trách nhiệm khác nhau

| Loại test | Gọi vào đâu? | Bảo vệ điều gì? | Giới hạn |
|---|---|---|---|
| Generated producer contract test với standalone MockMvc | Controller thật + dependency fake/mock | HTTP mapping và response của controller trong phạm vi setup | Không kiểm chứng DB/broker thật |
| Generated producer contract test với WebApplicationContext | Spring MVC context của producer | Wiring/config và hành vi HTTP trong context test | Có thể vẫn dùng fake/mock, không phải socket thật |
| Generated producer contract test `EXPLICIT` | Ứng dụng producer qua HTTP socket | Hành vi qua server/HTTP stack được dựng cho test | Không tự mô phỏng mọi môi trường production |
| Consumer test với **Stub Runner** | Stub HTTP/message từ hợp đồng | Consumer gửi request và xử lý response đã cam kết | Không gọi producer thật |
| Integration/end-to-end test | Producer + DB/broker và các dịch vụ liên quan | Kết hợp các tầng và khả năng vận hành | Tốn thời gian, dữ liệu và hạ tầng hơn |

Nếu mục tiêu là “khi đổi route Inventory thì Checkout phải phát hiện ngay”, producer contract tests và consumer Stub Runner tests là hai lớp bảo vệ quan trọng. Nếu mục tiêu là “truy vấn DB tồn kho có đúng transaction/locking không”, phải có kiểm thử ở tầng repository/service/integration tương ứng.

Không nên tăng kích thước base class đến mức mọi contract test phải khởi động toàn bộ hệ thống microservice. Mỗi test nên dựng **ranh giới nhỏ nhất vẫn đủ chứng minh điều contract cam kết**.

## 14. Đưa setup base class vào CI để phát hiện thay đổi không tương thích

Một quy trình tham khảo:

~~~mermaid
sequenceDiagram
    participant Dev as Pull request
    participant Gen as Contract generator
    participant Base as Base test + producer
    participant Stub as Stub artifact
    participant Cons as Consumer test
    Dev->>Gen: Cập nhật Groovy/YAML contract
    Gen->>Base: Sinh test và kế thừa base class
    Base->>Base: Khởi tạo controller/context + fixtures
    Base->>Base: Gọi producer, kiểm tra status/header/body
    alt Producer contract test thành công
        Gen->>Stub: Đóng gói stub cùng revision
        Stub->>Cons: Stub Runner khởi chạy candidate stub
        Cons->>Cons: Gọi bằng client thật của consumer
    else Producer test thất bại
        Base-->>Dev: Điều tra setup hoặc implementation
    end
~~~

Các điều kiện cần kiểm tra trước khi chấp nhận PR:

1. **Contract được phát hiện:** file DSL nằm đúng vùng input của plugin.
2. **Generated test được chạy:** không phải build xanh vì `0 tests`.
3. **Base class dựng đúng đối tượng:** controller, application context hoặc HTTP server tương ứng với `testMode`.
4. **Fixture ổn định:** không phụ thuộc production DB hoặc thứ tự test.
5. **Assertion đủ:** producer test kiểm tra field và trạng thái mà consumer thực sự sử dụng.
6. **Stub cùng revision:** artifact được tạo từ hợp đồng đã qua kiểm chứng.
7. **Consumer test đúng stub:** Stub Runner chạy bản candidate dự kiến phát hành, không lấy bản cũ từ cache.
8. **Thay đổi tương thích được review:** đổi field, status, MIME, schema hoặc URL có thể phá vỡ consumer dù producer test với contract mới vẫn xanh.

**Không suy rằng việc build tạo stub đủ chứng minh producer đã chạy test thành công.** Cổng CI phải ràng buộc bước phát hành stub với kết quả producer contract tests.

## 15. Bài tập thực hành: chọn đúng cách khởi tạo

### Tình huống A — Controller đơn giản

`InventoryController` chỉ phụ thuộc `InventoryService`. Nhóm muốn kiểm tra `GET /api/inventory/{sku}` với service fake để chạy nhanh.

**Đề xuất:** dùng `MOCKMVC` + `RestAssuredMockMvc.standaloneSetup(new InventoryController(fakeService))`. Setup fixture `SKU-101` trong mock và bảo đảm controller thật được gọi.

**Câu hỏi:** test này có chứng minh repository lưu tồn kho đúng không?

**Trả lời:** không. Nó bảo vệ hành vi HTTP/controller trong phạm vi mock; repository cần test riêng.

### Tình huống B — Error body từ `@ControllerAdvice`

Producer sử dụng global exception handler để chuyển `InventoryNotFoundException` thành `404` cùng JSON `{"code":"SKU_NOT_FOUND"}`. Standalone test chỉ khởi tạo controller, nên test nhận exception thay vì error body.

**Đề xuất:** đăng ký exception handler/converter trong MockMvc standalone hoặc chuyển sang `WebApplicationContext` để dùng cấu hình MVC thực. Đừng viết controller mới chỉ để làm test xanh.

**Câu hỏi:** nếu context test bỏ qua security filters, có thể xem test `403` là đã kiểm chứng bảo mật đầy đủ không?

**Trả lời:** không. Cần setup security/filter đúng theo ranh giới kiểm thử hoặc bổ sung integration/security test.

### Tình huống C — Có context path và proxy-like behavior

Ứng dụng phục vụ endpoint dưới `/inventory-service/api/inventory/SKU-101` và nhóm muốn xác nhận cả context path qua HTTP thực.

**Đề xuất:** cân nhắc `EXPLICIT` + `SpringBootTest(RANDOM_PORT)`, cấu hình RestAssured tới đúng cổng và bảo đảm contract mô tả path đầy đủ. Chỉ dùng MockMvc nếu phạm vi đã được thống nhất và không cần kiểm chứng socket/context path thực.

### Tình huống D — Generated test vẫn xanh dù producer DB hỏng

Base class đã mock `InventoryService` để luôn trả `8`. Một PR đổi repository khiến đọc dữ liệu thật thất bại, nhưng contract test vẫn xanh.

**Giải thích:** test chỉ đi qua controller và mock service, không gọi repository thật. Cần thêm repository/integration tests; có thể bổ sung một bộ contract chạy với context và database test nếu mức rủi ro yêu cầu.

### Câu hỏi tự kiểm tra

1. Vì sao `baseClassForTests` phải trỏ tới đúng class ở test source set?
2. `standaloneSetup` và `webAppContextSetup` khác nhau ở phạm vi những thành phần Spring được dựng thế nào?
3. Vì sao `@SpringBootTest(RANDOM_PORT)` không tự chuyển test mode từ `MOCKMVC` sang `EXPLICIT`?
4. Khi nào nên mock service, khi nào nên dùng database test thật?
5. Làm sao phát hiện JUnit lifecycle hook không chạy?
6. Tại sao producer contract test không thể thay thế consumer test dùng Stub Runner?
7. Nếu test xanh nhưng không có generated test nào được chạy, CI đang thiếu kiểm tra gì?
8. Vì sao không nên sửa trực tiếp generated test thay vì sửa DSL/base class?

## 16. Ghi nhớ

**Base test class là cầu nối giữa contract và producer cần kiểm chứng.** Nó phải dựng đúng controller hoặc ứng dụng, cấp dependency và dữ liệu nền có chủ đích, rồi gắn generated test với `MockMvc`, `WebTestClient` hoặc HTTP socket theo test mode đã chọn. `standaloneSetup` giúp test controller nhanh và cô lập; `webAppContextSetup` dùng Spring MVC context; `EXPLICIT` gọi ứng dụng qua cổng thật.

Một base class tốt không chỉ giúp test xanh, mà giúp **test xanh có ý nghĩa**: request đã đi qua đúng mã producer, assertion thật sự chạy, trạng thái test tái lập được, và phạm vi mock được thừa nhận. Sau đó, producer phát hành stub và consumer dùng Stub Runner trên CI để phát hiện sớm những thay đổi API hoặc thông điệp không tương thích.

### Tài liệu tham khảo

- [Spring Cloud Contract — Getting Started](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): ví dụ `baseClassForTests` và setup controller độc lập.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): cấu hình plugin, test mode và base classes.
- [Spring Cloud Contract — Project Features](https://docs.spring.io/spring-cloud-contract/reference/project-features.html): các lựa chọn WebFlux, `EXPLICIT`, context path và cơ chế producer/consumer.
