# Thay địa chỉ producer bằng URL do Stub Runner cung cấp

## Mục tiêu học tập

Trong **Spring Cloud Contract**, producer (dịch vụ cung cấp API hoặc phát thông điệp) công bố hành vi bằng **Groovy/YAML DSL**. Công cụ sinh kiểm thử phía producer, tạo artifact **stub**, rồi consumer dùng **Stub Runner** để chạy những stub đó trong kiểm thử. Khi tích hợp CI, hai phía có thể phát hiện sớm thay đổi API hoặc thông điệp không tương thích.

Bài này thuộc chương **Kiểm thử consumer**. Chủ đề rất cụ thể nhưng thường quyết định test có đáng tin hay không: **làm thế nào để HTTP client thật của consumer gọi vào URL của stub do Stub Runner khởi chạy, thay vì gọi nhầm producer thật?**

Sau bài học, bạn sẽ:

- Giải thích quan hệ giữa **tọa độ artifact stub**, **stub server**, **cổng runtime** và **base URL của HTTP client**.
- Khởi động stub bằng `@AutoConfigureStubRunner` và lấy cổng bằng `@StubRunnerPort` hoặc dùng `StubFinder`.
- Viết test dùng **client thực của consumer**, đổi endpoint HTTP sang `localhost` của stub.
- Chọn **cổng động** khi test client độc lập và **cổng cố định** khi cần cấu hình toàn bộ Spring application context trước lúc bean được khởi tạo.
- Phân biệt chế độ lấy stub `LOCAL`, `REMOTE` và `CLASSPATH` theo nguồn artifact.
- Kiểm tra cả response, request matcher, version của stub và các nhánh lỗi.
- Tránh bẫy do cấu hình được áp dụng **quá muộn**, hardcode URL, cổng xung đột, cache artifact cũ hoặc test gọi nhầm môi trường ngoài.
- Liên kết producer contract tests, candidate stub và consumer tests thành pipeline CI có thể truy vết.

## 1. Vấn đề: test xanh nhưng HTTP client đang gọi vào đâu?

Giả sử **Checkout Service** là consumer. Nó gọi **Inventory Service** để xác nhận tồn kho trước khi cho người dùng đặt hàng:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Inventory dự kiến trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

Trong production, Checkout có thể dùng cấu hình:

~~~properties
inventory.base-url=https://inventory.internal.example
~~~

Nếu một consumer test vô tình giữ URL này, có những rủi ro:

1. Test gọi **dịch vụ thật**, khiến kết quả phụ thuộc mạng, bảo mật và dữ liệu môi trường.
2. Test thất bại trên CI do mạng không cho phép truy cập producer.
3. Test có thể làm thay đổi dữ liệu thật nếu API có tác dụng phụ.
4. Test chạy xanh nhưng **không dùng stub vừa tạo**, nên không kiểm tra hợp đồng ứng viên.
5. Người review nhìn thấy `@AutoConfigureStubRunner` trong test và tưởng ứng dụng đã tự chuyển URL.

**Annotation khởi động stub không tự động thay đổi mọi HTTP client trong ứng dụng.** Client phải dùng URL/cổng của stub thông qua **dependency injection, property hoặc một client factory được cấu hình phù hợp**.

### Luồng đúng

~~~mermaid
flowchart TD
    A["Groovy/YAML contract trong producer"] --> B["Generated producer tests"]
    B --> C{"Producer test đạt?"}
    C -->|Có| D["Stub artifact: group:artifact:version:stubs"]
    C -->|Không| X["Không công bố stub đã xác nhận"]
    D --> E["Stub Runner của consumer test"]
    E --> F["Khởi chạy HTTP stub trên localhost:port"]
    F --> G["Test lấy port/URL"]
    G --> H["Cấu hình InventoryClient thật"]
    H --> I["Client gửi HTTP tới stub"]
    I --> J["Assert dữ liệu và quyết định của Checkout"]
~~~

**Chỗ dễ sai:** bước “test lấy port/URL” và “cấu hình InventoryClient thật” không xảy ra tự động chỉ vì Stub Runner đã tải artifact.

## 2. Phân biệt bốn loại địa chỉ và định danh

| Khái niệm | Ví dụ | Dùng làm gì? |
|---|---|---|
| Producer service URL | `https://inventory.internal.example` | Endpoint thật ở môi trường triển khai |
| Stub artifact ID | `com.example:inventory-producer:1.0.0:stubs` | Xác định gói stub cần tải |
| Stub server URL | `http://localhost:18080` hoặc cổng động | Địa chỉ HTTP giả lập khi Stub Runner chạy |
| Consumer base URL property | `inventory.base-url` | Chỉ dẫn HTTP client nên gửi request đi đâu |

**Artifact ID không phải URL.** Chuỗi `com.example:inventory-producer:1.0.0:stubs` giúp Stub Runner tìm gói JAR; còn HTTP client cần một URL như `http://localhost:18080`.

**Tên artifact cũng không phải tên service discovery mặc định.** Nếu consumer dùng DNS hay Spring Cloud LoadBalancer, phải cấu hình rõ cơ chế nào ánh xạ tên service thành địa chỉ stub. Trong bài này, ta dùng HTTP client có **base URL** trực tiếp để học cách nối endpoint một cách tường minh.

### Tọa độ ID mở rộng của Stub Runner

Một chuỗi thường dùng trong `ids`:

~~~text
com.example:inventory-producer:1.0.0:stubs:0
|_________| |______________| |___| |___| |
   group       artifact      version classifier port
~~~

Trong đó:

- `com.example`: group ID producer.
- `inventory-producer`: artifact ID.
- `1.0.0`: version stub đã xây dựng/phát hành.
- `stubs`: classifier của artifact stub.
- `0`: để hệ điều hành chọn cổng trống cho stub server.

**Cổng 0 không có nghĩa HTTP client gọi `localhost:0`.** Nó là yêu cầu Stub Runner chọn cổng khả dụng, sau đó test phải lấy **cổng thực tế**.

Giá trị `1.0.0` ở đây chỉ để minh họa. Khi kiểm tra một PR có candidate stub mới, phải thay bằng **đúng version/candidate artifact** đã được producer xác minh, không mặc nhiên dùng bản ổn định cũ.

## 3. Bước chuẩn bị: stub của producer phải tồn tại

Trước khi consumer khởi động Stub Runner, producer cần tạo artifact stub từ hợp đồng. Ví dụ hợp đồng HTTP Groovy có thể là:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Ton kho SKU-101 con hang'

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

Có thể viết YAML DSL thay thế:

~~~yaml
description: 'Ton kho SKU-101 con hang'
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

Một build thực tế chỉ cần **một contract cho tình huống này**; không nhân đôi Groovy và YAML như hai contract độc lập nếu điều đó tạo mapping chồng lấn.

Khi producer chạy đầy đủ lifecycle kiểm chứng, plugin thường tạo **generated producer tests** và đóng gói `*-stubs.jar`. Ví dụ Maven:

~~~bash
# Trong module producer đã cấu hình Spring Cloud Contract Verifier:
./mvnw clean verify

# Nếu muốn dùng Stub Runner với stubsMode=LOCAL,
# phải cài artifact stub vào Maven local repository:
./mvnw install
~~~

`install` chỉ có ý nghĩa khi build đã được cấu hình tạo/attach stub artifact phù hợp. Kiểm tra kết quả plugin và test reports, không suy rằng một lệnh Maven bất kỳ tự sinh stub.

Quan trọng hơn: việc `stubs.jar` tồn tại **không đủ chứng minh producer đã đạt contract test**. Theo quy trình release đáng tin cậy, chỉ phát hành stub như một cam kết đã kiểm chứng khi generated producer tests **thực sự chạy và PASS**.

### Nội dung một artifact stub

Một layout thường gặp:

~~~text
inventory-producer-1.0.0-stubs.jar
└── META-INF/
    └── com.example/
        └── inventory-producer/
            └── 1.0.0/
                ├── contracts/
                │   └── inventory/stockAvailable.groovy
                └── mappings/
                    └── inventory_stockAvailable.json
~~~

Đường dẫn/tên cụ thể phụ thuộc version Spring Cloud Contract và cách đóng gói. Với HTTP, Stub Runner chạy WireMock dựa trên mappings/contract trong artifact. Với messaging, nó còn dùng nhãn/định nghĩa message; **không phải mọi stub đều là HTTP mapping**.

## 4. Dependency cần thiết ở phía consumer

Với Spring Boot consumer dùng Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Với Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
}
~~~

Các ví dụ giả định dự án đã cấu hình Spring Boot/Spring Cloud BOM và repositories phù hợp. Với release train khác nhau, cần chọn phiên bản dependency tương thích; không chép version của một dự án khác mà chưa xem BOM đang sử dụng.

Có hai thành phần quan trọng:

~~~java
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
~~~

và để **lấy cổng stub đang chạy**:

~~~java
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
~~~

`@AutoConfigureStubRunner` chọn và khởi động stub; `@StubRunnerPort` giúp inject **cổng runtime** của một stub cụ thể vào test. Nếu nhiều producer cùng được khởi động, cần dùng định danh stub rõ ràng để không lấy nhầm cổng.

## 5. Cách 1 — Cổng động, tạo HTTP client từ URL của Stub Runner

Đây là cách dễ quan sát nhất khi muốn kiểm tra **HTTP adapter/client thật** mà không cần cố định cổng.

### HTTP client của consumer

Giả sử Checkout dùng Spring `RestClient`, có một class triển khai HTTP request thực:

~~~java
package com.example.checkout.inventory;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public class InventoryClient {

    private final RestClient http;

    public InventoryClient(RestClient.Builder builder, String baseUrl) {
        this.http = builder.baseUrl(baseUrl).build();
    }

    public StockResponse findBySku(String sku) {
        return http.get()
            .uri("/api/inventory/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(StockResponse.class);
    }
}
~~~

Response model:

~~~java
package com.example.checkout.inventory;

public record StockResponse(
    String sku,
    boolean available,
    int quantity
) {}
~~~

`RestClient` có trong các phiên bản Spring Framework hiện đại, ví dụ Spring Framework 6.1+ (Spring Boot 3.2+). Nếu dự án sử dụng `RestTemplate`, OpenFeign hoặc `WebClient`, **nguyên tắc đổi base URL vẫn như nhau**, chỉ khác API cấu hình.

Class `InventoryClient` trên được dùng cả trong ứng dụng thật và trong test; test không mock `findBySku(...)` mà chỉ thay **địa chỉ đích**. Trong production, có thể tạo bean qua một `@Configuration` lấy `inventory.base-url` từ cấu hình môi trường.

### Consumer test với cổng động

~~~java
package com.example.checkout.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryClientContractTest {

    @StubRunnerPort("inventory-producer")
    int inventoryStubPort;

    @Autowired
    RestClient.Builder restClientBuilder;

    @Test
    void readsStockFromProducerStub() {
        String stubBaseUrl = "http://localhost:" + inventoryStubPort;

        // Dùng chính class HTTP client của Checkout, chỉ thay URL.
        InventoryClient client =
            new InventoryClient(restClientBuilder, stubBaseUrl);

        StockResponse response = client.findBySku("SKU-101");

        assertThat(response.sku()).isEqualTo("SKU-101");
        assertThat(response.available()).isTrue();
        assertThat(response.quantity()).isEqualTo(8);
    }
}
~~~

### Vì sao ví dụ này đáng tin?

1. Stub Runner tìm stub artifact `com.example:inventory-producer:1.0.0:stubs` trong Maven local repository.
2. `:0` yêu cầu khởi động stub HTTP ở **cổng động**.
3. `@StubRunnerPort("inventory-producer")` lấy cổng thực tế của stub đó.
4. Test tạo **InventoryClient thật** dùng `http://localhost:<port>`, không dùng URL của Inventory production.
5. Client gửi HTTP request thực. Stub chỉ trả response nếu request phù hợp mapping.
6. Assertion kiểm tra consumer đọc đúng JSON và kiểu dữ liệu.

**Phạm vi chính xác:** ví dụ kiểm chứng **class InventoryClient thật**, nhưng **không tự kiểm tra Spring production bean wiring** vì test tạo client với URL bằng constructor. Đây là lựa chọn có chủ đích cho bài test HTTP adapter độc lập. Ở mục sau sẽ xem cách kiểm tra cả phần wiring.

### Lưu ý về @StubRunnerPort

Trong ví dụ chỉ có một artifact `inventory-producer`, dùng artifact ID là cách dễ đọc. Với nhiều artifact có tên giống nhau ở các group khác nhau, cần sử dụng định danh đầy đủ theo khả năng của phiên bản Stub Runner để tránh mơ hồ; không dựa vào thứ tự server được khởi động.

Nếu field `inventoryStubPort` bằng 0 hoặc không được inject như mong đợi, **đừng thử gọi localhost:0**. Hãy kiểm tra artifact được tải, annotation đang chạy, tên stub trong `ids`, version và test context.

## 6. Lấy URL bằng StubFinder

Ngoài việc inject cổng, Spring Cloud Contract còn cung cấp API `StubFinder` để tra cứu stub đang chạy theo định danh producer.

Ví dụ trong consumer test:

~~~java
import java.net.URL;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.contract.stubrunner.StubFinder;

class StubUrlLookupExample {

    @Autowired
    StubFinder stubFinder;

    void inspectUrl() {
        URL inventoryUrl =
            stubFinder.findStubUrl("com.example", "inventory-producer");

        // inventoryUrl có dạng http://localhost:<runtime-port>
        // Truyền inventoryUrl.toString() vào InventoryClient.
    }
}
~~~

`StubFinder` có ích khi:

- Test quản lý **nhiều stub** và muốn tra cứu theo group/artifact.
- Cần **URL đầy đủ**, không chỉ số cổng.
- Muốn phân biệt URL của producer A và producer B mà không dùng hằng số cổng.
- Client factory có thể nhận trực tiếp `String`/`URL`/`URI`.

**Đây là đoạn minh họa bên trong Spring test context đã cấu hình Stub Runner**, không phải một class tự chạy độc lập. API overload/định danh có thể khác đôi chút theo version; nếu version dự án khác, xác nhận bằng kiểu trả về và API `StubFinder` có sẵn trong dependency thực tế.

Tránh lấy URL bằng cách tự quét các cổng địa phương đang mở. Stub Runner đã biết chính xác server nào ứng với artifact nào; hãy dùng API/property do nó cung cấp.

## 7. Cách 2 — Cổng cố định để kiểm tra cả application wiring

Với ví dụ cổng động, test tạo client sau khi stub khởi động. Nhưng đôi khi ta muốn test **CheckoutService đã được Spring inject InventoryClient** và gọi đúng dependency qua cấu hình bean hiện hành.

Khi Spring tạo `InventoryClient`, nó có thể đọc `inventory.base-url` ngay trong constructor. Vì thế URL phải được thiết lập **trước thời điểm bean khởi tạo**.

Một phương án đơn giản, dễ kiểm chứng là **yêu cầu Stub Runner dùng cổng cố định trong test**, rồi cấu hình ứng dụng consumer trỏ tới cổng đó.

### Cấu hình bean trong ứng dụng

~~~java
package com.example.checkout.inventory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class InventoryClientConfiguration {

    @Bean
    InventoryClient inventoryClient(
            RestClient.Builder builder,
            @Value("${inventory.base-url}") String baseUrl) {
        return new InventoryClient(builder, baseUrl);
    }
}
~~~

Ứng dụng production có thể giữ property:

~~~properties
inventory.base-url=https://inventory.internal.example
~~~

Nhưng test override bằng URL nội bộ.

### Test cả Spring wiring

~~~java
package com.example.checkout.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "inventory.base-url=http://localhost:18080"
})
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:18080",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutWiringWithStubTest {

    @Autowired
    InventoryClient inventoryClient;

    @Test
    void injectedClientUsesProducerStub() {
        StockResponse response = inventoryClient.findBySku("SKU-101");

        assertThat(response.available()).isTrue();
        assertThat(response.quantity()).isEqualTo(8);
    }
}
~~~

Ở đây:

- `:18080` trong `ids` chỉ đạo Stub Runner khởi động stub trên cổng `18080`.
- `inventory.base-url=http://localhost:18080` khiến **bean InventoryClient do Spring khởi tạo** trỏ đúng Stub Runner.
- Test dùng `@Autowired InventoryClient` nên bảo vệ thêm phần **wiring qua Spring configuration**, không chỉ implementation của class client.

**Đánh đổi:** cổng cố định có nguy cơ bị chiếm hoặc xung đột khi chạy test song song. Chỉ sử dụng khi có cơ chế bảo đảm cổng trống hoặc test isolation phù hợp. Nếu môi trường CI chạy nhiều job trên cùng host, nên ưu tiên cách cổng động hoặc giải pháp cấu hình động đúng lifecycle.

### Phân biệt hai kiểu test

| Tiêu chí | Cổng động + khởi tạo client trong test | Cổng cố định + inject bean ứng dụng |
|---|---|---|
| Stub URL | Lấy từ `@StubRunnerPort` | Cố định theo `ids ... :18080` |
| Kiểm tra HTTP client thật | Có | Có |
| Kiểm tra Spring bean wiring | Không đầy đủ | Có |
| Tránh va chạm cổng | Tốt hơn | Phải quản lý cổng |
| Test chạy song song | Dễ cô lập cổng hơn | Cần điều phối |
| Phù hợp | Adapter/client test nhanh và rõ | Application/configuration integration test |

**Đừng tuyên bố cách nào luôn tốt hơn.** Chọn theo ranh giới muốn kiểm chứng và đặc điểm CI.

## 8. Tại sao đổi property trong @BeforeEach thường đã quá muộn?

Một sai lầm phổ biến:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class IncorrectSetup {

    @StubRunnerPort("inventory-producer")
    int port;

    @BeforeEach
    void changeUrlTooLate() {
        System.setProperty(
            "inventory.base-url",
            "http://localhost:" + port
        );
    }

    @Autowired
    InventoryClient inventoryClient;
}
~~~

**Vấn đề:** `@SpringBootTest` tạo Spring application context và các singleton beans **trước khi** gọi `@BeforeEach` của test method. Nếu `InventoryClient` đọc property khi constructor chạy, nó đã giữ base URL cũ.

Hơn nữa, `System.setProperty` là một trạng thái **toàn JVM**, có thể ảnh hưởng các test khác và làm test song song không ổn định.

**Cách sửa:**

- Nếu chỉ kiểm tra client: inject cổng rồi **khởi tạo client sau khi Stub Runner có URL** (mục 5).
- Nếu kiểm tra wiring: dùng cổng đã định trước và set `@SpringBootTest(properties=...)` từ đầu (mục 7).
- Nếu phải dùng cổng động **và** wiring toàn bộ ứng dụng: chọn một cơ chế bootstrap/configuration phù hợp với lifecycle của Stub Runner và Spring Boot mà version dự án hỗ trợ; xác nhận thời điểm property được đăng ký so với lúc bean khởi tạo. Không đọc field `@StubRunnerPort` trong một static initializer và giả định nó đã có giá trị.

Có những setup sử dụng **runtime properties do Stub Runner đăng ký** cho port của các server đang chạy. Tên property/định danh và thứ tự đăng ký phụ thuộc cách tích hợp/version; nếu sử dụng cách này, cần xác nhận trên test context thật và kiểm tra bean đã nhận URL nào. Một cách cấu hình nghe hợp lý nhưng được áp dụng **sau khi bean đã xây dựng** sẽ không bảo vệ ứng dụng.

## 9. Cấu hình client cho nhiều producer

Checkout có thể gọi **Inventory Service**, **Pricing Service** và **Payment Service**. Mỗi producer có stub riêng:

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-producer:1.0.0:stubs:0",
        "com.example:pricing-producer:2.1.0:stubs:0",
        "com.example:payment-producer:3.0.0:stubs:0"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

Mỗi client cần URL **của chính producer đó**:

~~~java
@StubRunnerPort("inventory-producer")
int inventoryPort;

@StubRunnerPort("pricing-producer")
int pricingPort;

@StubRunnerPort("payment-producer")
int paymentPort;
~~~

Sau đó:

~~~java
InventoryClient inventory =
    new InventoryClient(builder, "http://localhost:" + inventoryPort);

// Tương tự: pricingClient và paymentClient thực của Checkout,
// mỗi client nhận base URL riêng.
~~~

Không nên:

- Dùng nhầm cổng Inventory cho Pricing chỉ vì cả hai đều có `GET`.
- Phụ thuộc vào **thứ tự** stub server khởi động.
- Bỏ group/artifact/version khi có nhiều stub dễ trùng tên.
- Dùng một biến cấu hình chung kiểu `external.base-url` cho mọi dependency mà không có cơ chế routing rõ ràng.
- Dùng stub `latest` cho từng producer rồi khó tái lập test.

### Service discovery và load-balancing

Nếu ứng dụng dùng `http://inventory-service` qua service discovery thay vì một URL trực tiếp, phải quyết định **lớp nào trong test thay tên service bằng đích stub**. Có thể ghi đè cấu hình target URL, đăng ký fake service instance, hoặc dùng tính năng Stub Runner tích hợp với load-balancing/discovery theo version.

Bài này ưu tiên cơ chế **base URL được cấu hình tường minh**. Không giả định Stub Runner tự thay DNS của mọi tên service trong ứng dụng.

## 10. Kiểm tra điều consumer thật sự cần, không chỉ status 200

Một consumer contract test có ý nghĩa nên kiểm tra **cách consumer xử lý response**:

~~~java
StockResponse response = client.findBySku("SKU-101");

assertThat(response.sku()).isEqualTo("SKU-101");
assertThat(response.available()).isTrue();
assertThat(response.quantity()).isEqualTo(8);
~~~

Nếu Checkout có business rule “không cho đặt quá số tồn”, nên test trực tiếp **business flow** khi có đủ setup, thay vì chỉ kiểm tra JSON deserialization.

Ví dụ pseudocode:

~~~text
given stub: SKU-101 available=true, quantity=8
when Checkout asks to order 9 units
then Checkout rejects quantity > 8

given stub: SKU-101 available=true, quantity=8
when Checkout asks to order 2 units
then Checkout allows next checkout step
~~~

**Đừng hardcode `available=true` trong CheckoutService chỉ để test xanh.** Test phải gọi qua client và thực sự sử dụng response stub.

### So sánh các lớp kiểm thử

| Test | Bảo vệ tốt | Chưa bảo vệ |
|---|---|---|
| Unit test với mock `InventoryClient` | Checkout phân nhánh trên response giả | URL, HTTP header, serialization |
| Consumer test với Stub Runner + client thật | Request HTTP và cách consumer đọc stub theo contract | Producer implementation thật (nếu chưa chạy producer test) |
| Generated producer contract test | Producer thật đáp ứng những contract đã mô tả | Logic ứng dụng của mọi consumer |
| End-to-end test với các dịch vụ thật | Một số luồng tích hợp thực | Mọi tình huống lỗi/ngoại lệ nếu không được mô phỏng |

Bài này đặt trọng tâm ở **consumer test qua Stub Runner**; nó phải được kết hợp với **producer contract verification** để hai phía có cùng bằng chứng.

## 11. Test lỗi HTTP: không được hiểu nhầm 404 do không match mapping

Giả sử contract producer có tình huống:

~~~http
GET /api/inventory/SKU-404 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"SKU_NOT_FOUND","message":"SKU does not exist"}
~~~

Khi Stub Runner đã tải artifact chứa contract lỗi này, consumer có thể kiểm tra nhánh xử lý.

Ví dụ với `RestClient.retrieve()` không tùy chỉnh `onStatus`:

~~~java
import org.springframework.web.client.HttpClientErrorException;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

assertThatThrownBy(() -> client.findBySku("SKU-404"))
    .isInstanceOf(HttpClientErrorException.NotFound.class);
~~~

Nếu ứng dụng chuyển `404` thành kết quả nghiệp vụ có mã `SKU_NOT_FOUND`, test nên assert đúng kiểu kết quả đó; không buộc mọi consumer phải lộ trực tiếp exception từ thư viện HTTP.

**Cực kỳ quan trọng:** khi WireMock không tìm thấy mapping phù hợp, nó cũng có thể trả `404` mặc định. Do đó, một test chỉ assert “đã nhận 404” **chưa chắc** chứng minh case `SKU_NOT_FOUND` trong contract đã được dùng.

Cách tăng độ tin cậy:

1. Kiểm tra artifact stub có contract tương ứng.
2. Xem method, path, query và headers mà client thực sự gửi.
3. Assert **error body/code** theo giao diện, không chỉ status.
4. Khi cần, xem log unmatched requests hoặc request journal của WireMock/Stub Runner.
5. Xác nhận đang gọi đúng Stub Runner server, không phải một WireMock server khác.

### Không tự dùng response 503 để chứng minh timeout

`HTTP 503` là một response có status/header/body. **Client timeout** xảy ra khi client không nhận kết quả trong thời gian cho phép. Một contract `503` không tự giả lập kết nối chậm hoặc TCP reset.

Để test retry, timeout hoặc các lỗi mạng đặc biệt, có thể bổ sung test consumer với WireMock fault/delay riêng. Nhưng đừng sửa ngẫu nhiên contract chính thức để khiến mọi test resilience nhận status như ý muốn.

## 12. Stub Runner LOCAL, REMOTE và CLASSPATH

Nguồn lấy stub ảnh hưởng trực tiếp đến tính tái lập của consumer test.

| Chế độ | Nguồn stub | Khi nên dùng | Điều cần lưu ý |
|---|---|---|---|
| `LOCAL` | Maven local repository của môi trường chạy test | Máy dev hoặc pipeline đã cài candidate stub vào local repo | Stub phải được install đúng version; có nguy cơ dùng cache cũ |
| `REMOTE` | Artifact repository được cấu hình | CI hoặc các consumer khác tải stub có version từ Nexus/Artifactory/Maven repository | Cần repository URL, credentials/quyền đọc và version rõ |
| `CLASSPATH` | Stubs được đóng gói/có sẵn trên test classpath | Test tích hợp với bộ stub kèm dependency | Cần đúng cấu trúc/resource, không tự đọc Maven local |

### LOCAL

Ví dụ:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

Nếu producer chưa install `inventory-producer-1.0.0-stubs.jar` vào local repository, Stub Runner có thể không tìm thấy artifact. Tên file nằm trong workspace producer chưa đồng nghĩa nó đã nằm trong Maven local repo mà consumer test đọc được.

### REMOTE

Khi dùng repository từ xa, có thể cấu hình thông số nguồn trong annotation/properties tương ứng của phiên bản:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    repositoryRoot = "https://artifacts.example.test/repository/stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE
)
~~~

Địa chỉ ở trên là URL minh họa, không phải repository có thể truy cập thật. Trong CI thực, cấu hình repository nội bộ và cơ chế authentication được dự án cho phép; **không ghi token/password trực tiếp vào source hoặc URL**.

### CLASSPATH

Với `CLASSPATH`, stub được cung cấp từ nguồn tài nguyên/dependency đã đưa vào test classpath. Cách thiết lập phụ thuộc cách đóng gói và cơ chế nạp stubs của phiên bản. Đừng hiểu `CLASSPATH` có nghĩa Stub Runner sẽ tự tìm trong Maven local repository.

**Nguyên tắc chung:** dù nguồn nào, test phải biết **stub artifact/revision chính xác** đang được chạy. Nếu producer thay contract mà consumer vẫn dùng bản cũ, test có thể xanh nhưng không còn kiểm tra thay đổi của PR.

## 13. Stub Runner khởi chạy, client chưa chắc đã được cấu hình đúng

Khi debug, cần phân biệt ba việc khác nhau:

~~~text
A. Stub Runner RESOLVED artifact
   ↓
B. Stub Runner STARTED HTTP server at runtime port
   ↓
C. Consumer HTTP client USED that server URL
~~~

Có thể A và B đúng nhưng C sai.

### Dấu hiệu và chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| `@StubRunnerPort` không inject đúng | Tên stub sai, artifact không load, annotation/test context sai | Xem log Stub Runner, ID và version |
| `Connection refused` | Client trỏ port cũ, stub chưa chạy hoặc server khác | In URL thực của client trong test log an toàn |
| Client gọi production URL | `inventory.base-url` không được override hoặc bean đã khởi tạo trước khi đổi | Xem cấu hình bean/client và lúc property được đọc |
| HTTP 404 dù contract có case 200 | URL/header/body không match mapping | Xem WireMock unmatched request và mapping thật |
| Client nhận sai dữ liệu nhưng test vẫn xanh | Test không assert field quan trọng hoặc dùng mock client | Assert sau deserialize và luồng nghiệp vụ |
| Test chạy cục bộ xanh, CI không tìm stub | LOCAL cache có artifact, runner CI không có | Install candidate trong CI hoặc dùng REMOTE |
| CI dùng stub cũ | Version mutable, cache, tọa độ `+`/latest | Ghim version/commit/digest, xem resolved artifact |
| Khi chạy song song bị xung đột port | Dùng fixed port chung | Chuyển sang `:0` hoặc cô lập runner |
| Producer test xanh, consumer lỗi | Contract thay đổi phá vỡ client hoặc stub matcher chưa đúng | Đối chiếu candidate artifact, generated tests và consumer logic |
| Consumer test xanh, production lỗi | Stub chưa được producer xác nhận hoặc trường hợp chưa được bao phủ | Kiểm tra producer verification và test matrix |

Không nên chữa mọi lỗi bằng việc thay `:0` thành một cổng cố định. Trước tiên phải biết **client đang trỏ URL nào**, **stub đang nghe ở đâu** và **request có match contract không**.

## 14. Phân biệt Stub Runner với @AutoConfigureWireMock

Hai cách đều có thể tạo một HTTP server giả để test consumer, nhưng nguồn sự thật khác nhau.

~~~java
// A: Stub Runner dùng contract artifact từ producer.
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

~~~java
// B: Embedded WireMock dùng stubs do test tự đăng ký.
@AutoConfigureWireMock(port = 0)
~~~

| Tiêu chí | Stub Runner | @AutoConfigureWireMock |
|---|---|---|
| Nguồn mapping | Stub được sinh từ Groovy/YAML contract | Java DSL hoặc WireMock JSON mapping viết tay |
| Tọa độ version producer | Có ý nghĩa cốt lõi | Không bắt buộc |
| Producer contract test liên quan | Có qua quy trình sinh/kiểm chứng stub | Không tự có |
| Lấy runtime URL | `@StubRunnerPort`, `StubFinder` hoặc cơ chế tích hợp | `wiremock.server.port` |
| Phù hợp | Kiểm tra consumer với API mà producer đã cam kết | HTTP client test độc lập, fault/latency test |
| Nguy cơ thường gặp | Nhầm artifact/version hoặc quên đổi client URL | Stub viết tay lệch với producer thật |

`@AutoConfigureWireMock` cũng có thể dùng cổng động, nhưng property **`wiremock.server.port` không phải là cách mặc định lấy cổng của một stub do Stub Runner quản lý**. Hãy dùng đúng API cho đúng công cụ.

Trong một test, nếu đồng thời khởi động Stub Runner và WireMock khác mà cấu hình client không rõ ràng, rất dễ gọi nhầm server. Chỉ kết hợp khi có lý do cụ thể và ghi rõ server nào được gọi trong từng test.

## 15. Bảo đảm không gọi nhầm dịch vụ thật

Đối với test tự động, đặc biệt là test có HTTP request ghi dữ liệu, cần hạn chế nguy cơ gọi production.

Các phương án:

- URL sản xuất chỉ đến từ cấu hình triển khai, không hardcode trong code test.
- Test thay URL bằng `localhost` stub **trước khi client được sử dụng**.
- Khi test tích hợp nhiều bean, kiểm tra bean/HTTP client nhận đúng base URL.
- Dùng một **endpoint giả không thể truy cập** làm default trong test profile khi cần phát hiện việc quên override.
- Không cho test runner truy cập các mạng production nhạy cảm nếu không có nhu cầu rõ ràng.
- Với `POST`/`PUT`/`DELETE`, chú ý side effect; không “thử xem test có tự gọi được không” lên môi trường thật.
- Nếu dùng HTTP proxy hay service discovery, phải chắc chắn route stub không bị bypass.

**Đừng trông chờ rằng test fail nếu gọi nhầm production.** Dịch vụ thật đôi khi trả đúng fixture tình cờ; test vẫn có thể xanh. Cấu hình test cần khiến việc gọi nhầm trở nên khó xảy ra và dễ phát hiện.

### Ví dụ kiểm tra target URL

Trong test dùng cổng động:

~~~java
assertThat(inventoryStubPort).isGreaterThan(0);

String stubBaseUrl = "http://localhost:" + inventoryStubPort;

InventoryClient client =
    new InventoryClient(restClientBuilder, stubBaseUrl);
~~~

Điều này xác nhận cổng được cấp, nhưng để chứng minh request đi tới stub cụ thể, cần **gọi client và assert response của một mapping phân biệt**. Khi nghi ngờ, kiểm tra request journal hoặc WireMock log của stub đang chạy.

## 16. Khi có nhiều contract cho một endpoint

Một artifact có thể chứa nhiều mapping cho `GET /api/inventory/{sku}`:

| Tình huống | Request matcher | Response |
|---|---|---|
| `stockAvailable` | `GET /api/inventory/SKU-101` | `200`, `available=true`, `quantity=8` |
| `stockEmpty` | `GET /api/inventory/SKU-EMPTY` | `200`, `available=false`, `quantity=0` |
| `stockNotFound` | `GET /api/inventory/SKU-404` | `404`, `code=SKU_NOT_FOUND` |
| `stockUnavailable` | `GET /api/inventory/SKU-UNAVAILABLE` | `503`, `code=INVENTORY_UNAVAILABLE` |

Khi consumer test gọi từng SKU, sẽ nhận những nhánh hành vi cụ thể. Nếu hai mapping cùng match một request nhưng trả response khác, kết quả có thể phụ thuộc ưu tiên mapping hoặc cấu hình WireMock. Contract cần thiết kế matcher **không mơ hồ**, không mặc nhiên kỳ vọng stub “nhớ” trạng thái stock thay đổi theo thời gian.

Dùng đúng request case để test đúng nhánh; không cố khiến một mapping trả response khác nhau chỉ bằng việc thay expected value của consumer test.

### Ma trận nhỏ cho Checkout

~~~text
GET SKU-101
  -> Checkout can proceed with quantity <= 8

GET SKU-EMPTY
  -> Checkout shows out-of-stock

GET SKU-404
  -> Checkout reports SKU not found

GET SKU-UNAVAILABLE
  -> Checkout reports unable to verify inventory
     (and follows retry policy if applicable)
~~~

Các trường hợp là ví dụ dựa trên hợp đồng giả định. Không tự tạo contract `503` hay quy tắc retry nếu producer và consumer chưa thống nhất.

## 17. Tổ chức CI để dùng đúng candidate stub

Một pipeline có thể được mô tả như sau:

~~~mermaid
sequenceDiagram
    participant Dev as Pull request
    participant Prod as Producer contract tests
    participant Art as Candidate stub artifact
    participant Runner as Consumer Stub Runner
    participant Checkout as Consumer test
    Dev->>Prod: Thay đổi Groovy/YAML DSL và producer code
    Prod->>Prod: Generated tests được chạy
    alt Producer tests đạt
        Prod->>Art: Đóng gói stub đúng revision
        Art->>Runner: Tải candidate stub theo version/ID
        Runner-->>Checkout: Cung cấp localhost:runtime-port
        Checkout->>Runner: HTTP client thật gọi request
        Checkout->>Checkout: Assert kết quả nghiệp vụ
    else Producer tests lỗi
        Prod-->>Dev: Không công bố stub đã xác nhận
    end
~~~

### Các cổng CI cần có

1. **Producer contract discovery:** generator tìm đúng các contract.
2. **Producer test execution:** generated tests thực sự chạy và PASS, không bị skip.
3. **Stub packaging:** candidate artifact chứa mappings/contracts/fixtures cần thiết.
4. **Revision consistency:** artifact có version/commit khớp producer vừa kiểm chứng.
5. **Consumer retrieval:** Stub Runner thực sự tải **đúng candidate**, không dựa vào cache mơ hồ.
6. **URL replacement:** consumer test gọi localhost/cổng được Stub Runner cấp.
7. **Consumer assertions:** không chỉ gọi stub; phải xác nhận hành vi ứng dụng.
8. **Compatibility review:** thay đổi field, header, status hoặc URL có thể phá consumer cũ dù producer test với contract mới xanh.
9. **Release policy:** không công bố stub chưa được producer xác nhận chỉ vì consumer test với stub đã xanh.

### LOCAL trong CI có thể hoạt động thế nào?

Nếu pipeline có thể chuyển source/binary giữa jobs, một luồng đơn giản:

~~~text
Producer job:
  checkout commit A
  run generated producer tests
  package candidate stubs.jar
  publish artifact tạm trong CI (không phải release)

Consumer job:
  get candidate from producer job
  install artifact into isolated Maven local repository
  run @AutoConfigureStubRunner(stubsMode=LOCAL)
  use @StubRunnerPort to configure HTTP client
  run consumer tests and save reports
~~~

Phần “install artifact vào isolated Maven local repository” cần được triển khai bằng công cụ build/repository của tổ chức; không chỉ copy JAR vào một folder tùy ý. Job phải có đầy đủ metadata Maven để Stub Runner resolve chính xác.

Nếu dùng `REMOTE` với repository staging, cần quản lý quyền, version và TTL tương ứng. Đừng upload một candidate chưa đạt producer gate vào repository release chính thức để consumer test “dễ lấy”.

## 18. Tình huống sai phổ biến và cách sửa

### Tình huống A: đã có Stub Runner nhưng client vẫn gọi host cũ

~~~java
@SpringBootTest(properties = {
    "inventory.base-url=https://inventory.internal.example"
})
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class IncorrectConsumerTest {
    @Autowired InventoryClient inventoryClient;
}
~~~

**Lỗi:** test đã khởi động stub, nhưng bean InventoryClient dùng URL của dịch vụ thật. Stub Runner không tự thay property của ứng dụng.

**Sửa:** tạo client bằng URL lấy từ `@StubRunnerPort` trong một client-level test, hoặc cấu hình base URL ở thời điểm tạo bean và trỏ vào cổng Stub Runner được biết trước.

### Tình huống B: ghép cổng 0 thành URL

~~~java
String baseUrl = "http://localhost:0";
~~~

**Lỗi:** port 0 là tín hiệu **yêu cầu cấp cổng động**, không phải cổng thực để gọi HTTP. **Sửa:** lấy cổng đã được Stub Runner cấp, ví dụ từ `@StubRunnerPort`.

### Tình huống C: test đặt System.setProperty quá muộn

~~~java
@BeforeEach
void setup() {
    System.setProperty("inventory.base-url",
        "http://localhost:" + inventoryStubPort);
}
~~~

**Lỗi:** client bean có thể đã khởi tạo. **Sửa:** dùng cấu hình trước context creation hoặc tạo lại client từ URL runtime một cách có chủ đích.

### Tình huống D: Stub Runner tải sai artifact

~~~text
Producer PR: 1.1.0-rc.2
Consumer test: 1.0.0
Result: PASS
~~~

**Lỗi:** kết quả chỉ chứng minh consumer tương thích với stub `1.0.0`, không chứng minh nó hiểu các thay đổi của `1.1.0-rc.2`. **Sửa:** đưa candidate version từ job producer vào test consumer; lưu version/digest trong CI log.

### Tình huống E: stub có 404 mặc định

Consumer test muốn kiểm tra `SKU_NOT_FOUND` nhưng gửi nhầm `/api/inventory/SKU404`. WireMock không match mapping, trả 404. Test chỉ assert status nên xanh.

**Sửa:** assert error code/body và kiểm tra request path, mapping/near misses. Chỉ coi test thành công khi response của **tình huống hợp đồng** được sử dụng.

## 19. Bài thực hành: nối đúng cổng và kiểm tra cả hai phía

### Đề bài

Consumer có ứng dụng:

~~~java
public class InventoryClient {
    public InventoryClient(RestClient.Builder builder, String baseUrl) {
        // ...
    }
    public StockResponse findBySku(String sku) {
        // ...
    }
}
~~~

Producer đã cung cấp stub:

~~~text
group    = com.example
artifact = inventory-producer
version  = 1.0.0
classif. = stubs

GET /api/inventory/SKU-101
-> 200 application/json
-> {"sku":"SKU-101","available":true,"quantity":8}
~~~

Một test ban đầu:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class WrongTest {

    @Test
    void stock() {
        InventoryClient client = new InventoryClient(
            RestClient.builder(),
            "http://localhost:0"
        );

        // ...
    }
}
~~~

**Câu hỏi 1:** Vì sao `localhost:0` sai?

Cổng 0 trong `ids` không phải cổng server thực. Nó chỉ yêu cầu Stub Runner chọn cổng trống. Test phải lấy **runtime port**.

**Câu hỏi 2:** Sửa ra sao?

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CorrectTest {

    @StubRunnerPort("inventory-producer")
    int stubPort;

    @Autowired
    RestClient.Builder builder;

    @Test
    void readsStock() {
        InventoryClient client = new InventoryClient(
            builder,
            "http://localhost:" + stubPort
        );

        StockResponse response = client.findBySku("SKU-101");

        assertThat(response.sku()).isEqualTo("SKU-101");
        assertThat(response.available()).isTrue();
        assertThat(response.quantity()).isEqualTo(8);
    }
}
~~~

Ví dụ cần các import JUnit, Spring và AssertJ tương ứng, cùng producer stub đã có trong local repository. Nó kiểm chứng class HTTP client thật nhưng không kiểm chứng Spring application wiring khi class được khởi tạo thủ công.

**Câu hỏi 3:** Nếu muốn kiểm tra cả bean wiring thì sao?

Chọn một cổng đã được Stub Runner cấu hình trong `ids` và override `inventory.base-url` ngay khi tạo `@SpringBootTest` context, như ví dụ `:18080`. Hoặc áp dụng cơ chế runtime property/bootstrap tương thích với phiên bản dự án. Đừng đổi property trong `@BeforeEach` rồi giả định bean đã dựng lại.

**Câu hỏi 4:** Nếu consumer test xanh nhưng producer code trả `quantity` dạng string?

Test với stub chỉ chứng minh client xử lý **stub**. Phải chạy generated producer contract tests để phát hiện producer thật không tuân thủ schema, và bảo đảm consumer test dùng đúng stub của revision đã được kiểm chứng.

**Câu hỏi 5:** Nếu CI không tìm thấy artifact trong chế độ LOCAL?

Cần tạo, kiểm chứng và **install candidate stub artifact** vào đúng local Maven repository của runner hoặc chọn repository/mode phân phối khác. Không tự chuyển sang version cũ chỉ để test xanh.

### Bài mở rộng

Hãy thiết kế thêm các test consumer cho:

1. `SKU-EMPTY` trả `available=false`, `quantity=0`: Checkout phải thông báo hết hàng.
2. `SKU-404` trả `404` cùng mã `SKU_NOT_FOUND`: Checkout xử lý tài nguyên không tồn tại, không nhầm với lỗi mạng.
3. `SKU-UNAVAILABLE` trả `503`: Checkout báo trạng thái tạm thời chưa xác minh được và tuân theo chính sách retry nếu có.
4. Producer thứ hai `pricing-producer`: client giá phải dùng **cổng riêng**, không nhầm cổng của Inventory.

Mỗi case cần ghi rõ mapping contract nào đang được dùng, consumer gửi request thực nào, kết quả cuối cùng của Checkout ra sao và revision artifact stub của test.

## 20. Checklist trước khi chấp nhận consumer test với Stub Runner

- [ ] Producer và consumer đã thống nhất Groovy/YAML contract cho các tương tác quan trọng.
- [ ] Generated producer tests **được chạy và PASS** trước khi coi stub là đã xác nhận.
- [ ] `@AutoConfigureStubRunner` dùng đúng group/artifact/version/classifier.
- [ ] Chế độ `LOCAL`/`REMOTE`/`CLASSPATH` phù hợp nơi artifact được lưu.
- [ ] Khi dùng cổng động `:0`, test **lấy runtime port** qua `@StubRunnerPort` hoặc `StubFinder`.
- [ ] Consumer HTTP client thật được tạo/cấu hình với URL stub, không còn gọi production URL.
- [ ] Nếu kiểm tra Spring wiring, URL phải được cấu hình **trước khi bean khởi tạo**.
- [ ] Không dùng `System.setProperty` ở `@BeforeEach` như giải pháp mặc định cho bean singleton đã tạo.
- [ ] Mỗi producer có cổng/URL riêng; không dựa vào thứ tự server khởi động.
- [ ] Test assert response JSON/type hoặc business outcome mà consumer phụ thuộc.
- [ ] Test phân biệt 404 do contract với 404 do request không match mapping.
- [ ] Test không dùng stub artifact stale hoặc version `latest` thiếu truy vết.
- [ ] Test song song không xung đột cổng cố định và state/mapping dùng chung.
- [ ] Nếu có retry/timeout, có test bổ sung đúng phạm vi; không đánh đồng HTTP status với network fault.
- [ ] CI ghi version/commit của producer, candidate artifact và consumer test đã chạy.
- [ ] Thay đổi phá vỡ API được đánh giá với những consumer hiện đang triển khai.

## 21. Ghi nhớ và tài liệu tham khảo

**Stub Runner khởi động HTTP server cho artifact stub; nhưng consumer chỉ thực sự kiểm thử với stub khi HTTP client của nó đã được trỏ sang đúng URL runtime.** `@StubRunnerPort` giúp lấy cổng động, `StubFinder` giúp tra cứu URL theo định danh stub, còn cấu hình base URL của ứng dụng quyết định client sẽ gửi request đến đâu.

Khi test client độc lập, hãy nhận cổng động rồi tạo **client thật** với `http://localhost:<port>`. Khi kiểm tra cả Spring application wiring, phải bảo đảm URL đã được cấu hình **trước khi bean được khởi tạo**; dùng cổng cố định được quản lý hoặc cơ chế bootstrap động tương thích với version thay vì ghi đè property quá muộn.

Để kiểm chứng tương thích thực sự, cần nối ba bằng chứng: **producer generated tests PASS**, **stub artifact đúng revision**, **consumer tests dùng client thật và đúng Stub Runner URL**. Không có bằng chứng nào trong ba phần này tự thay thế hai phần còn lại.

### Tài liệu tham khảo

- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): `@AutoConfigureStubRunner`, `@StubRunnerPort` và cách dùng Stub Runner trong Spring Boot test.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): cơ chế resolve và chạy stubs, `StubFinder` và URL runtime.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): hợp đồng Groovy/YAML, producer verification và stub generation.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): API `RestClient` và cấu hình client.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): lifecycle sinh/kiểm chứng contract tests và đóng gói stub.

**Tóm lại:** đừng chỉ hỏi “Stub Runner đã chạy chưa?”. Hãy hỏi **“client nào đã gọi vào URL nào, lấy từ artifact version nào, và producer đã được kiểm chứng chưa?”**. Đó là cách một consumer test thực sự góp phần phát hiện thay đổi HTTP API không tương thích trên CI.
