# Kiểm thử nhiều producer và cách ly cấu hình từng client

Một consumer trong hệ microservices thường không chỉ gọi một producer. Ví dụ, **Checkout Service** cần đọc đơn hàng từ **Order Service**, sau đó kiểm tồn kho tại **Inventory Service**. Nếu hai HTTP client cùng dùng một `baseUrl`, chung cấu hình authentication hoặc bị gán nhầm cổng WireMock, consumer test có thể gọi đúng một stub nhưng sai dịch vụ, làm bài kiểm thử đạt giả hoặc báo lỗi khó hiểu khi chạy song song.

Với **Spring Cloud Contract**, mỗi producer có thể định nghĩa hợp đồng bằng **Groovy/YAML DSL**, sinh test xác minh implementation, đóng gói artifact `stubs` và cho consumer chạy **Stub Runner** để kiểm mã HTTP client thật. Khi consumer phụ thuộc **nhiều producer**, cần quản lý riêng **tọa độ artifact, version, địa chỉ stub động, cấu hình từng client, dữ liệu mẫu và request journal**.

Bài thuộc chương **Kiểm thử consumer** của mô-đun **SPRING_CLOUD_CONTRACT**. Mục tiêu là thiết kế kiểm thử tích hợp nhiều stub trong một test context nhưng **không trộn cấu hình**, hiểu giới hạn của consumer contract tests và đưa các kiểm tra tương thích vào CI khi nhiều producer phát hành độc lập.

## 1. Vì sao một consumer cần kiểm nhiều producer?

Xét luồng nghiệp vụ tạo bản tóm tắt thanh toán:

~~~mermaid
flowchart TD
    A["Checkout Service"] --> B["OrderClient"]
    A --> C["InventoryClient"]
    B --> D["Order Service: GET /api/orders/42"]
    C --> E["Inventory Service: GET /api/stock/SKU-42"]
    D --> F["Thông tin SKU, quantity, status"]
    E --> G["Số lượng còn trong kho"]
    F --> H["CheckoutSummaryService tổng hợp"]
    G --> H
~~~

**Order Service** trả:

~~~http
GET /api/orders/42
Accept: application/json
~~~

~~~json
{
  "id": 42,
  "sku": "SKU-42",
  "quantity": 2,
  "status": "PAID"
}
~~~

**Inventory Service** trả:

~~~http
GET /api/stock/SKU-42
Accept: application/json
~~~

~~~json
{
  "sku": "SKU-42",
  "available": 8
}
~~~

Checkout cần ghép kết quả để biết đơn yêu cầu `2` sản phẩm, kho hiện có `8`, nên trạng thái `enoughStock=true` trong ví dụ. Điều consumer quan tâm là **hai request đã đi tới đúng hai producer**, dữ liệu giải mã đúng và logic tổng hợp hoạt động.

| Nguy cơ | Ví dụ | Lớp kiểm thử phát hiện |
| --- | --- | --- |
| Gọi nhầm host | InventoryClient trỏ sang URL của Order Service. | Kiểm base URL từng client, journal từng stub. |
| Gọi sai đường dẫn | OrderClient gửi `/api/order/42` thay vì `/api/orders/42`. | Request matching, unmatched requests. |
| Sai schema | Inventory đổi `available` thành `stockCount`. | Producer verification và consumer deserialization. |
| Cấu hình lẫn headers | Authorization của Order Service gửi sang Inventory. | Kiểm journal/header trên từng stub. |
| Trộn version | Checkout dùng order stub v1 nhưng inventory stub không tương thích. | Ma trận artifact version, consumer integration tests. |
| Phụ thuộc thứ tự gọi | Test giả định hai request luôn diễn ra theo một thứ tự khi nghiệp vụ không cam kết. | Assert đúng tương tác thay vì ép thứ tự vô cớ. |

**Một bộ test chỉ dùng một stub** có thể chứng minh mỗi client hoạt động riêng, nhưng không nhất thiết phát hiện **lỗi wiring khi hai client cùng có mặt**. Vì vậy, cần kiểm **từng client độc lập** lẫn **một luồng phối hợp cả hai**.

## 2. Bốn lớp cần được cách ly

Để tránh cấu hình chéo, nên phân biệt:

1. **Artifact:** mỗi producer có `groupId:artifactId:version:stubs` riêng.
2. **Stub server:** mỗi HTTP producer stub có URL/port chạy riêng do Stub Runner cấp.
3. **Client:** mỗi HTTP client dùng base URL, auth, headers, timeout, retry và serializer theo yêu cầu của producer tương ứng.
4. **Test state:** request journal, scenario state, fixture và assertions phải thuộc đúng stub và đúng test.

| Thành phần | Order Service | Inventory Service |
| --- | --- | --- |
| Artifact minh họa | `com.acme:order-service:1.0.0:stubs` | `com.acme:inventory-service:2.0.0:stubs` |
| Stub HTTP URL | Tra qua `StubFinder` | Tra riêng qua `StubFinder` |
| Client code | `OrderClient` | `InventoryClient` |
| Property production | `clients.orders.base-url` | `clients.inventory.base-url` |
| Header nhận diện ví dụ | `X-Client: checkout-orders` | `X-Client: checkout-inventory` |
| Đường dẫn | `/api/orders/42` | `/api/stock/SKU-42` |
| DTO | `OrderDto` | `StockDto` |
| Retry/timeout | Theo quy tắc Order API | Theo quy tắc Inventory API |

Hai producer có thể khác cách xác thực, SLA và release version. **Không sử dụng một “global downstream URL” hoặc một HTTP client builder mutable được thiết lập lần lượt cho cả hai** mà không hiểu liệu cấu hình đã được copy/cô lập chưa.

## 3. Hợp đồng của mỗi producer phải độc lập

Mỗi producer chịu trách nhiệm **kiểm implementation của chính mình** trước khi phát hành stub. Ví dụ viết bằng **Groovy DSL**.

### 3.1. Hợp đồng Order Service

Trong repository **Order Service**, tệp `src/test/resources/contracts/orders/get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            sku: 'SKU-42',
            quantity: 2,
            status: 'PAID'
        )
    }
}
~~~

### 3.2. Hợp đồng Inventory Service

Trong repository **Inventory Service**, tệp `src/test/resources/contracts/stock/get_stock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnAvailableStock'

    request {
        method 'GET'
        url '/api/stock/SKU-42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-42',
            available: 8
        )
    }
}
~~~

Hai contract mô tả hai API riêng. Các giá trị mẫu `42`, `SKU-42` và `available=8` chỉ phục vụ tình huống kiểm thử xác định. Chúng **không bảo đảm** Order Service và Inventory Service ngoài production có dữ liệu nhất quán tức thời hoặc rằng tồn kho không thay đổi giữa hai lời gọi.

### 3.3. Cùng hành vi dưới dạng YAML DSL

Order Service có thể chọn YAML thay Groovy:

~~~yaml
description: Order Service trả đơn hàng đã thanh toán
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    sku: SKU-42
    quantity: 2
    status: PAID
~~~

Inventory Service có hợp đồng YAML riêng:

~~~yaml
description: Inventory Service trả số lượng tồn kho
request:
  method: GET
  url: /api/stock/SKU-42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-42
    available: 8
~~~

Trong một producer, chọn **một cách biểu diễn có hiệu lực** cho cùng tình huống; đừng nạp đồng thời cả Groovy và YAML tương đương rồi tạo stub mapping trùng. Hai producer có thể dùng **hai DSL khác nhau** mà consumer vẫn dùng Stub Runner với hai artifact độc lập.

## 4. Chuẩn bị hai artifact stub

Mỗi producer chạy **Contract Verifier** với base test và môi trường riêng. Khi producer test đạt, build có thể đóng gói artifact:

~~~text
com.acme:order-service:1.0.0:stubs
com.acme:inventory-service:2.0.0:stubs
~~~

Trong bài thực hành chạy `LOCAL`, mỗi producer có thể dùng quy trình Maven đã cấu hình:

~~~shell
mvn clean verify
mvn install
~~~

Đó là **các lệnh minh họa chạy ở từng producer repository**, không yêu cầu ghép lệnh hoặc chạy hai lần cùng lúc. Tùy Maven lifecycle, `install` có thể thực thi lại test. Trong CI, nên tổ chức các bước để producer verification là **điều kiện bắt buộc trước publish**. Nếu consumer chạy trên máy/runner khác, hãy publish hai artifact vào Maven repository và dùng Stub Runner `REMOTE`.

**Lưu ý về phiên bản:** Order Service `1.0.0` và Inventory Service `2.0.0` không bắt buộc có cùng số version. Hai dịch vụ có vòng phát hành độc lập; consumer cần kiểm **một tổ hợp version cụ thể**, không tự động nâng tất cả phụ thuộc lên “latest”.

## 5. Cho Stub Runner tải và khởi động cả hai HTTP stubs

Ở consumer, Spring Cloud Contract Stub Runner có thể nạp nhiều artifact trong một test:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = {
        "com.acme:order-service:1.0.0:stubs",
        "com.acme:inventory-service:2.0.0:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutConsumerContractTest {
    // Kiểm thử nhiều producer sẽ được viết bên dưới.
}
~~~

**Không gắn cổng cố định** vào `ids` nếu muốn Stub Runner tự cấp port, tránh các job CI tranh `8089` hoặc `8090`. Sau khi stubs khởi động, dùng **`StubFinder`** tra URL cho từng producer:

~~~java
import java.net.URL;
import java.util.Objects;

@Autowired
private StubFinder stubFinder;

private URL orderStubUrl() {
    return Objects.requireNonNull(
        stubFinder.findStubUrl("com.acme", "order-service"),
        "Order Service stub was not started"
    );
}

private URL inventoryStubUrl() {
    return Objects.requireNonNull(
        stubFinder.findStubUrl("com.acme", "inventory-service"),
        "Inventory Service stub was not started"
    );
}
~~~

Các đoạn này minh họa phần của một test class; cần imports Spring StubFinder/JUnit tương ứng. Một cặp `groupId + artifactId` phù hợp hơn việc tìm chỉ bằng tên `order-service`, nhất là khi hệ thống có nhiều nhóm cùng tên artifact.

**Không tự ghép một URL chung** từ một số cổng. Ví dụ, lỗi:

~~~java
String url = orderStubUrl().toExternalForm();
OrderClient orders = new OrderClient(url);
InventoryClient inventory = new InventoryClient(url); // Sai.
~~~

Lỗi này rất dễ xảy ra nếu test chỉ có một biến `stubBaseUrl`. Hãy tạo **hai biến rõ nghĩa** và dùng đúng mỗi client:

~~~java
OrderClient orders = new OrderClient(
    orderStubUrl().toExternalForm()
);
InventoryClient inventory = new InventoryClient(
    inventoryStubUrl().toExternalForm()
);
~~~

`StubFinder` trả URL của **stub server đã khởi động**, không phải URL Maven repository. Chế độ `REMOTE` cũng có thể tải artifact từ repository rồi khởi động WireMock local ở port động; `REMOTE` **không có nghĩa** HTTP client phải gọi chính Maven repository.

## 6. Viết hai HTTP client với cấu hình cách ly

Với Spring Framework 6.1+/Spring Boot tương thích, có thể dùng **`RestClient`**. Ta tạo **mỗi client một RestClient instance**, thay vì sử dụng chung một builder mutable rồi thay base URL/header liên tục.

### 6.1. OrderClient

~~~java
package com.acme.checkout.clients;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient http;

    public OrderClient(String baseUrl) {
        this.http = RestClient.builder()
            .baseUrl(baseUrl)
            .defaultHeader("X-Client", "checkout-orders")
            .build();
    }

    public OrderDto getOrder(long id) {
        return http.get()
            .uri("/api/orders/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(
        long id, String sku, int quantity, String status
    ) {}
}
~~~

### 6.2. InventoryClient

~~~java
package com.acme.checkout.clients;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class InventoryClient {
    private final RestClient http;

    public InventoryClient(String baseUrl) {
        this.http = RestClient.builder()
            .baseUrl(baseUrl)
            .defaultHeader("X-Client", "checkout-inventory")
            .build();
    }

    public StockDto getStock(String sku) {
        return http.get()
            .uri("/api/stock/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(StockDto.class);
    }

    public record StockDto(String sku, int available) {}
}
~~~

Hai client có **URL và header riêng**. Trong ví dụ, `X-Client` chỉ dùng để minh họa khả năng xác minh cấu hình; nó không phải yêu cầu bắt buộc của Spring Cloud Contract. Nếu producer thật yêu cầu các header khác, hãy đưa chúng vào **hợp đồng được producer xác minh** và cấu hình client tương ứng.

**Tại sao không dùng chung mutable builder?** Một `RestClient.Builder` có thể giữ các tùy chỉnh sau khi gọi `baseUrl(...)` hoặc `defaultHeader(...)`. Nếu cùng một builder bị sửa lần lượt cho Order và Inventory, header/token/interceptor của client trước có thể bị áp dụng ngoài ý muốn cho client sau. Tạo builder mới cho từng client hoặc **clone có kiểm soát** theo API phiên bản framework sẽ giúp giới hạn phạm vi cấu hình.

Với `WebClient` hoặc `RestTemplate`, nguyên tắc tương tự: **mỗi producer có cấu hình endpoint, auth, codec, timeout và retry riêng**, dù các client có thể dùng chung tài nguyên hạ tầng thread-safe như connection pool khi được thiết kế đúng.

## 7. Cấu hình production phải dùng hai property riêng

Để chuyển từ test sang ứng dụng thật, không hardcode URL trong client. Một cấu hình Spring Boot có thể nhận hai property:

~~~yaml
clients:
  orders:
    base-url: ${ORDERS_API_URL}
  inventory:
    base-url: ${INVENTORY_API_URL}
~~~

Đây là đoạn trong `application.yml` minh họa: các biến môi trường `ORDERS_API_URL` và `INVENTORY_API_URL` được triển khai cung cấp. Không ghi token/secret production vào tệp hợp đồng hoặc mã test.

Một lớp factory Spring:

~~~java
package com.acme.checkout.config;

import com.acme.checkout.clients.InventoryClient;
import com.acme.checkout.clients.OrderClient;
import com.acme.checkout.service.CheckoutSummaryService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OutboundClientsConfig {

    @Bean
    OrderClient orderClient(
            @Value("${clients.orders.base-url}") String baseUrl) {
        return new OrderClient(baseUrl);
    }

    @Bean
    InventoryClient inventoryClient(
            @Value("${clients.inventory.base-url}") String baseUrl) {
        return new InventoryClient(baseUrl);
    }

    @Bean
    CheckoutSummaryService checkoutSummaryService(
            OrderClient orders, InventoryClient inventory) {
        return new CheckoutSummaryService(orders, inventory);
    }
}
~~~

Lớp này cung cấp hai bean **khác kiểu và khác property**. Nếu có nhiều client cùng kiểu `RestClient`, nên đặt tên bean hoặc dùng qualifier rõ ràng để tránh injection nhầm.

Một quy tắc cấu hình nên áp dụng cho dự án thật:

| Cấu hình | Cô lập theo producer? | Vì sao |
| --- | --- | --- |
| Base URL / service discovery name | **Có** | Order và Inventory là hai đích khác nhau. |
| Authorization/token audience | **Có** | Không làm lộ token Order sang Inventory hoặc ngược lại. |
| Default headers | **Có** | Tránh gửi metadata sai producer. |
| Timeout/retry/circuit breaker | **Có** | Từng API có SLA và tính idempotency khác nhau. |
| DTO/serializer/schema | **Có** | Hai producer có thể dùng enum/date/field khác nhau. |
| Metrics/logging tag | **Có** | Phân biệt lỗi Order và Inventory khi giám sát. |
| Connection pool | **Có thể chia sẻ có kiểm soát** | Chỉ nếu thread-safe và chính sách isolation/tài nguyên rõ ràng. |

**Không dùng cùng token cho tất cả downstream service nếu mô hình quyền không cho phép.** Token trong consumer test phải là dữ liệu giả. Khi test một client, chỉ assert những header thực sự thuộc hợp đồng, không chèn credential thật vào WireMock request journal hoặc CI logs.

## 8. Lớp orchestration sử dụng cả hai client

Một consumer thường có logic ghép dữ liệu. Để kiểm thực chất, hãy dùng **chính service orchestration** đó thay vì chỉ tạo hai HTTP request trực tiếp trong test.

~~~java
package com.acme.checkout.service;

import com.acme.checkout.clients.InventoryClient;
import com.acme.checkout.clients.OrderClient;

public final class CheckoutSummaryService {
    private final OrderClient orders;
    private final InventoryClient inventory;

    public CheckoutSummaryService(
            OrderClient orders, InventoryClient inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    public CheckoutSummary summaryFor(long orderId) {
        OrderClient.OrderDto order = orders.getOrder(orderId);
        InventoryClient.StockDto stock =
            inventory.getStock(order.sku());

        if (!order.sku().equals(stock.sku())) {
            throw new IllegalStateException(
                "Inventory SKU does not match order SKU");
        }

        return new CheckoutSummary(
            order.id(),
            order.sku(),
            order.quantity(),
            stock.available(),
            stock.available() >= order.quantity()
        );
    }

    public record CheckoutSummary(
        long orderId,
        String sku,
        int requestedQuantity,
        int availableQuantity,
        boolean enoughStock
    ) {}
}
~~~

Đây là luồng **đọc dữ liệu rồi tổng hợp**, không phải một giao dịch phân tán. Dữ liệu tồn kho có thể thay đổi sau khi đọc; nếu nghiệp vụ cần giữ chỗ hàng hoặc thanh toán atomically, phải có API/quy trình bảo đảm riêng. Consumer contract test với hai stubs **không tự chứng minh tính nhất quán hoặc atomicity** của một nghiệp vụ nhiều dịch vụ.

## 9. Consumer test đầy đủ: hai URL động và logic thật

Trong Checkout Service, ta tạo test Boot context tối thiểu để Stub Runner khởi động hai stubs. Những client thật được tạo **sau khi** `StubFinder` tìm được URL, tránh phải đoán cổng từ trước khi Spring context hoàn tất.

~~~java
package com.acme.checkout;

import com.acme.checkout.clients.InventoryClient;
import com.acme.checkout.clients.OrderClient;
import com.acme.checkout.service.CheckoutSummaryService;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = MultiProducerContractTest.TestApp.class)
@AutoConfigureStubRunner(
    ids = {
        "com.acme:order-service:1.0.0:stubs",
        "com.acme:inventory-service:2.0.0:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class MultiProducerContractTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {}

    @Autowired
    private StubFinder stubFinder;

    @Test
    void combinesOrderAndInventoryResponses() {
        URL ordersUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub missing"
        );
        URL inventoryUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "inventory-service"),
            "Inventory Service stub missing"
        );

        assertThat(ordersUrl.toExternalForm())
            .isNotEqualTo(inventoryUrl.toExternalForm());

        // Sử dụng các class HTTP client thật của ứng dụng.
        OrderClient orders = new OrderClient(
            ordersUrl.toExternalForm()
        );
        InventoryClient inventory = new InventoryClient(
            inventoryUrl.toExternalForm()
        );

        CheckoutSummaryService service =
            new CheckoutSummaryService(orders, inventory);

        var summary = service.summaryFor(42L);

        assertThat(summary.orderId()).isEqualTo(42L);
        assertThat(summary.sku()).isEqualTo("SKU-42");
        assertThat(summary.requestedQuantity()).isEqualTo(2);
        assertThat(summary.availableQuantity()).isEqualTo(8);
        assertThat(summary.enoughStock()).isTrue();
    }
}
~~~

**Điều test này chứng minh:** cùng một luồng nghiệp vụ consumer có thể dùng **hai bản stub khác nhau**, gửi request qua hai client riêng, giải mã hai kiểu DTO và tổng hợp giá trị đúng theo fixtures đã công bố.

**Điều test này chưa chứng minh:** Spring production configuration `OutboundClientsConfig` đã được inject đúng trong mọi profile. Ví dụ test cố ý tạo client sau khi biết URL động. Cần một **test wiring riêng** cho các property `clients.orders.base-url` và `clients.inventory.base-url` hoặc dùng test configuration gắn URL động với bean lifecycle một cách có kiểm soát, nếu muốn bảo vệ chính xác hệ thống DI của ứng dụng.

Với test class ở trên, `@SpringBootConfiguration + @EnableAutoConfiguration` chỉ tạo test context nhỏ; đây không phải Spring Boot application production đầy đủ. Cần phiên bản Spring Boot/Stub Runner tương thích và hai artifact đã cài trong Maven local. Nếu bạn muốn test **toàn bộ cấu hình ứng dụng**, hãy khởi tạo app context thực và bố trí thời điểm cung cấp URL stub đúng vòng đời. Không dùng một phương thức static `@DynamicPropertySource` để truy cập tùy tiện một `@Autowired StubFinder` instance chưa được tạo.

## 10. Xác minh request đi đến đúng stub bằng journal

Một phản hồi đúng chưa chắc chứng minh **mọi client được cấu hình đúng**. Có thể hai stubs cùng có một mapping chung hoặc test đã sửa mappings quá rộng. **WireMock request journal** cho phép kiểm request **đến đúng server** và có header của client tương ứng.

Với HTTP stubs được khởi động bởi Stub Runner, có thể sử dụng **WireMock Admin API** trên từng base URL. Ví dụ phương thức đếm request:

~~~java
import java.util.Map;
import java.util.Objects;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

record RequestCount(int count) {}

static int countRequests(
        String stubBaseUrl,
        String path,
        String expectedClientHeader) {
    RequestCount result = RestClient.create(stubBaseUrl)
        .post()
        .uri("/__admin/requests/count")
        .contentType(MediaType.APPLICATION_JSON)
        .body(Map.of(
            "method", "GET",
            "url", path,
            "headers", Map.of(
                "X-Client", Map.of("equalTo", expectedClientHeader)
            )
        ))
        .retrieve()
        .body(RequestCount.class);

    return Objects.requireNonNull(result).count();
}
~~~

Sau khi chạy `service.summaryFor(42L)`, test có thể assert:

~~~java
assertThat(countRequests(
    ordersUrl.toExternalForm(),
    "/api/orders/42",
    "checkout-orders"
)).isEqualTo(1);

assertThat(countRequests(
    inventoryUrl.toExternalForm(),
    "/api/stock/SKU-42",
    "checkout-inventory"
)).isEqualTo(1);
~~~

Để kiểm **không gửi nhầm request sang server khác**, tra thêm count theo path không thuộc producer:

~~~java
static int countByPath(String baseUrl, String path) {
    RequestCount result = RestClient.create(baseUrl)
        .post()
        .uri("/__admin/requests/count")
        .contentType(MediaType.APPLICATION_JSON)
        .body(Map.of("method", "GET", "url", path))
        .retrieve()
        .body(RequestCount.class);
    return Objects.requireNonNull(result).count();
}

assertThat(countByPath(
    ordersUrl.toExternalForm(),
    "/api/stock/SKU-42"
)).isZero();
assertThat(countByPath(
    inventoryUrl.toExternalForm(),
    "/api/orders/42"
)).isZero();
~~~

**Quan trọng về cô lập journal:** `/__admin/requests/count` đếm các request **đã ghi từ khi server bắt đầu hoặc từ lần reset gần nhất**. Nếu nhiều test dùng chung stubs, phải reset request journal đúng thời điểm hoặc cấp server riêng, nếu không count sẽ bị cộng dồn. Endpoint `DELETE /__admin/requests` chỉ xóa journal, còn `resetAll()` có thể xóa mappings nên không nên tùy tiện dùng với Stub Runner.

Nếu test có thể chạy song song trên cùng instance, **đừng reset journal của test khác**. Hãy cô lập từng test context/server hoặc dùng correlation ID riêng trong request matcher và count. Chỉ xem count theo path cũng không tự chứng minh mọi request đều đúng; khi cần, kiểm thêm `GET /__admin/requests/unmatched` hoặc tìm journal thực theo header/body.

## 11. Kiểm leakage của authentication, headers và default settings

Trong hệ thống thật, Order Service có thể dùng OAuth2 bearer token còn Inventory Service dùng API key. Nếu một HTTP client builder chung giữ `Authorization`, token có thể bị gửi tới sai host; đây vừa là lỗi tích hợp vừa là rủi ro bảo mật.

Hướng thiết kế:

~~~text
OrderClient:
  baseUrl: orders API URL
  auth: token dành cho orders audience/scope
  headers: X-Client=checkout-orders
  timeout: chính sách Order API

InventoryClient:
  baseUrl: inventory API URL
  auth: API key riêng cho inventory
  headers: X-Client=checkout-inventory
  timeout: chính sách Inventory API
~~~

Trong consumer tests, dùng **token/key giả** để kiểm sự hiện diện, định dạng và **không bị gửi nhầm**; không ghi bí mật thật vào hợp đồng, WireMock mapping hoặc CI logs.

| Sai lệch | Cách phát hiện trong test |
| --- | --- |
| Header Inventory xuất hiện trên Order request. | Truy vấn Order stub journal, assert header không tồn tại. |
| Bearer token Order bị gửi đến Inventory. | Kiểm Inventory stub journal không có header Authorization của Order. |
| Cả hai client dùng cùng timeout/retry vô ý. | Gây lỗi/delay có kiểm soát ở từng stub, kiểm số lần gọi và lỗi tương ứng. |
| Một interceptor thay đổi query/body cho cả hai. | Verify path/header/body theo từng artifact, chạy test phối hợp. |
| Cùng DTO dùng cho cả hai producer. | Kiểm field, kiểu và schema riêng cho `OrderDto` và `StockDto`. |

**Không dùng request journal như nơi lưu token thô**. Trong test có thể assert header vắng mặt bằng matcher, nhưng khi in journal phục vụ debug phải lọc Authorization, cookie và dữ liệu nhạy cảm. WireMock ghi nhận request chưa có nghĩa nó đã **xác thực** những token đó.

## 12. Timeouts, retries và circuit breakers cũng phải cách ly

Hai producer có hành vi lỗi và độ trễ khác nhau. Một request `GET` có thể được retry khi gặp lỗi tạm thời; một request `POST` có tác dụng phụ có thể yêu cầu idempotency key và chính sách khác.

Ví dụ chính sách **minh họa**, không phải giá trị mặc định của Spring Cloud Contract:

| Chính sách | OrderClient | InventoryClient |
| --- | --- | --- |
| Connection/read timeout | Ngắn để phản hồi đơn kịp thời. | Có thể khác tùy SLA tồn kho. |
| Retry khi 503 | Tối đa số lần do đội Order cam kết. | Tối đa số lần do đội Inventory cam kết. |
| Retry khi 404 | Thường không, nếu là 404 nghiệp vụ. | Tùy API tồn kho và ý nghĩa 404. |
| Circuit breaker ID | `orderService` | `inventoryService` |
| Metrics tag | `producer=orders` | `producer=inventory` |

Nếu dùng Resilience4j hoặc framework tương tự, hãy tạo **instance/name theo producer**, không dùng một circuit breaker chung khiến lỗi Inventory làm Order bị mở circuit. Nếu một luồng orchestration có chính sách timeout tổng thể, vẫn cần xác định timeout **từng request** để chẩn đoán lỗi đúng nguồn.

Trong consumer test, có thể thêm hợp đồng lỗi hoặc WireMock scenarios với 503/delay để kiểm retry theo từng client. Nhưng **không tự sửa artifact stub đã publish để thêm mapping ngẫu nhiên** rồi coi đó là nguồn hợp đồng; dùng test-specific mappings được tạo có chủ đích hoặc các error contracts đã được producer xác minh. Khi chạy đồng thời nhiều test, scenarios và journal cũng cần isolation.

**Một test thành công với hai response 200 không chứng minh chính sách retry và timeout**. Cần bài kiểm riêng cho những hành vi này và kiểm số lần request thực tế.

## 13. Điều phối lỗi: một producer hỏng thì consumer phải xử lý ra sao?

Một consumer gọi nhiều producer phải xác định hành vi khi **một phần dữ liệu thành công, một phần thất bại**. Ví dụ:

| Order Service | Inventory Service | Hành vi Checkout có thể cần |
| --- | --- | --- |
| `200 PAID` | `200 available=8` | Tạo summary `enoughStock=true`. |
| `404 ORDER_NOT_FOUND` | Không cần gọi | Trả lỗi đơn hàng không tồn tại; **không gọi Inventory** nếu nghiệp vụ không yêu cầu. |
| `200 PAID` | `404 SKU_NOT_FOUND` | Báo không có thông tin tồn kho, không đồng nhất với số tồn 0. |
| `200 PAID` | `503` | Thử retry có giới hạn hoặc báo tạm thời không thể xác nhận tồn kho. |
| `503` | Không cần gọi | Trả lỗi/gián đoạn đọc đơn; kiểm không gọi Inventory vô ích. |
| `200 PAID` | `200 available=1` | `enoughStock=false`, không coi là lỗi HTTP. |

Các dòng trên là **ví dụ về thiết kế consumer**, không phải luật chung của Spring Cloud Contract. Nhóm phải thỏa thuận rõ hành vi nghiệp vụ.

Đặc biệt, WireMock có thể trả HTTP 404 khi **không có request mapping phù hợp**. Một consumer test chỉ assert 404 có thể **đạt giả**, trong khi client đã gọi sai URL. Khi kiểm 404 nghiệp vụ, phải có **contract lỗi riêng** với error body/code (`ORDER_NOT_FOUND`, `SKU_NOT_FOUND`) và assert nội dung đó cùng request journal.

### 13.1. Kiểm "không gọi producer còn lại"

Giả sử Checkout phát hiện đơn hàng không tồn tại thì không nên gọi tồn kho. Test có thể dùng `countByPath(inventoryUrl, "/api/stock/SKU-42") == 0` để bảo vệ **không có lời gọi không cần thiết**. Tuy nhiên, count bằng 0 cũng có thể do client gọi **sai path**; nếu thật sự phải bảo đảm Inventory **không nhận bất kỳ request nào**, hãy kiểm toàn bộ journal hoặc quy ước path/matcher bao quát, sau khi cô lập lịch sử test.

Với các luồng bất đồng bộ, đợi thao tác consumer hoàn tất rồi mới verify journal; không dùng `Thread.sleep` tùy ý. Nếu cùng context có health checks tự động, phân biệt traffic nghiệp vụ bằng matcher phù hợp thay vì kết luận mọi request đều là lỗi.

## 14. Cấu hình bean trong Spring Boot: tránh lỗi tạo quá sớm

Một vấn đề dễ mắc khi thay property production bằng URL stub động: **bean HTTP client được tạo khi Spring application context khởi tạo**, trong khi URL Stub Runner chỉ biết chắc **sau khi stub đã khởi chạy**.

Ví dụ không nên làm:

~~~java
// Sai ý tưởng: dùng một static @DynamicPropertySource để
// truy cập một instance @Autowired StubFinder chưa sẵn sàng.
// Không có bảo đảm vòng đời thích hợp cho cách này.
~~~

Có vài hướng an toàn:

1. **Tạo client thật sau khi tra StubFinder** như mục 9. Phù hợp với test tập trung vào logic HTTP/orchestration và tách khỏi DI của ứng dụng.
2. **Tạo một test configuration có factory phụ thuộc StubFinder**, nhưng phải kiểm thứ tự khởi tạo và cơ chế tích hợp Stub Runner trong phiên bản Spring Cloud Contract đang dùng.
3. **Dùng property integration chính thức** mà phiên bản Stub Runner hỗ trợ, sau khi xác minh tên property và lúc nó có giá trị. Không tự bịa tên khóa `stubrunner.port.*`.
4. **Test wiring production riêng** bằng properties ổn định trỏ tới hai test HTTP servers đã khởi động theo một lifecycle biết trước. Test này bảo vệ `OutboundClientsConfig` và các `@Value`, thay vì chỉ kiểm constructor client.

Một test có thể chia thành **hai lớp**:

| Loại test | Mục đích | Ví dụ |
| --- | --- | --- |
| **Contract consumer test** | Gọi mã client và orchestration qua stubs thực được tìm động. | `MultiProducerContractTest` ở mục 9. |
| **Spring configuration/wiring test** | Chứng minh hai property và bean injection không bị tráo. | Boot context có hai mock HTTP servers/known URLs, kiểm request tới đúng endpoint. |

Đừng cho rằng test contract với client khởi tạo thủ công chứng minh tất cả `@Bean` và profile config production đều đúng. Việc chia hai lớp kiểm giúp mỗi lỗi có nguồn xác định.

## 15. Nhiều artifact và phiên bản: quản lý ma trận tương thích

Khi Order và Inventory phát hành độc lập, Checkout cần biết tổ hợp nào đang hỗ trợ:

| Checkout version | Order stub | Inventory stub | Kết quả kiểm thử |
| --- | --- | --- | --- |
| `checkout-1.0` | `order:1.0.0` | `inventory:2.0.0` | **Baseline**: chạy đủ client + orchestration tests. |
| `checkout-1.0` | `order:1.1.0` | `inventory:2.0.0` | Kiểm Order nâng version có phá Checkout cũ không. |
| `checkout-1.0` | `order:1.0.0` | `inventory:2.1.0` | Kiểm Inventory nâng version có phá Checkout cũ không. |
| `checkout-1.1` | `order:1.1.0` | `inventory:2.1.0` | Kiểm tổ hợp dự kiến triển khai tiếp theo. |

Các version ở bảng là **giả định minh họa**, không phải kết quả pipeline thật. Không nhất thiết phải chạy **mọi tích Descartes của mọi version**: chọn các tổ hợp đang được hỗ trợ, đang triển khai và có rủi ro nâng cấp, rồi ghi rõ chiến lược tương thích.

Khi dùng `LOCAL`, cả hai artifact cần nằm trong Maven local repository của CI runner/test machine. Khi dùng `REMOTE`, cả hai artifact phải được publish và consumer có cấu hình `repositoryRoot`/credentials phù hợp. **Dùng cùng một chế độ tải artifact không đồng nghĩa hai producer có cùng vòng release**.

**Không dùng version mutable một cách vô thức** (ví dụ lúc thì tải snapshot cũ, lúc snapshot mới). Consumer test cần ghi được **tọa độ chính xác** của từng artifact và liên hệ với producer commit hoặc release tương ứng.

## 16. CI: bảo vệ nhiều producer mà không trộn nguồn sự thật

Một pipeline gợi ý:

~~~mermaid
flowchart TD
    OA["Order Service contracts"] --> OV["Order producer verification"]
    IA["Inventory Service contracts"] --> IV["Inventory producer verification"]
    OV --> OS{"Order tests đạt?"}
    IV --> IS{"Inventory tests đạt?"}
    OS -->|Không| F["Chặn publish artifact tương ứng"]
    IS -->|Không| F
    OS -->|Có| OP["Publish order:version:stubs"]
    IS -->|Có| IP["Publish inventory:version:stubs"]
    OP --> CS["Checkout CI tải hai artifact đã chọn"]
    IP --> CS
    CS --> RUN["Stub Runner cấp URL riêng"]
    RUN --> TEST["Chạy OrderClient, InventoryClient, orchestration"]
    TEST --> JOURNAL["Verify request journal từng stub"]
    JOURNAL --> COMPAT["Đánh giá compatibility/matrix"]
~~~

Các yêu cầu nên có trong CI:

1. **Mỗi producer tự chịu trách nhiệm generated producer tests**. Stub của một producer không được coi là đã được xác minh chỉ vì consumer test với stub đó xanh.
2. **Mỗi artifact có version rõ ràng**. Consumer CI pin hai phiên bản đang được kiểm.
3. **Stub Runner khởi động hai stubs độc lập**; dùng `StubFinder` tra từng base URL, không dùng cổng cố định khi chạy song song.
4. **Cấu hình riêng từng client**: URLs, credentials giả, headers, timeouts/retries và DTOs.
5. **Chạy test đơn lẻ và test phối hợp** để phát hiện client wiring, parse schema và logic tổng hợp.
6. **Kiểm request journal đúng server**, bảo đảm không có cross-talk và không có request no-match ngoài ý muốn.
7. **Cô lập state** khi chạy song song: đừng dùng một journal/scenario của Stub Runner rồi reset từ nhiều test cùng lúc.
8. **Thử lỗi từng producer**: 404/503/timeout có kiểm soát, assert fallback/retry/no-call theo quy tắc nghiệp vụ.
9. **Đánh giá phiên bản cũ còn hỗ trợ** trước khi nâng Order hoặc Inventory. Việc một producer thêm/bỏ trường có thể ảnh hưởng Checkout mà producer kia không liên quan.

Nếu CI bị chậm, không nên xóa kiểm thử phối hợp ngay: có thể giữ bộ hợp đồng từng client chạy thường xuyên và bộ orchestration đa producer cho các pull requests có thay đổi wiring/version, miễn chiến lược phù hợp mức rủi ro thực tế.

## 17. Những sai lầm thường gặp

| Sai lầm | Dấu hiệu | Cách sửa |
| --- | --- | --- |
| Dùng chung base URL cho hai client. | Inventory request đến Order WireMock, trả 404 no-match. | Tra URL hai artifact riêng và truyền đúng client. |
| Gắn cố định hai cổng trong CI song song. | `Address already in use` hoặc kết nối nhầm stub. | Bỏ port cố định, dùng `StubFinder`/URL động. |
| Dùng một builder mutable cho cả hai client. | Header/token/baseUrl của Order xuất hiện ở Inventory. | Tạo builder/client riêng hoặc clone có kiểm soát. |
| Chỉ assert response mà không xem journal. | Có thể client gọi sai endpoint trong mapping rộng. | Verify request method/path/header tại đúng stub server. |
| Dùng 404 no-match làm test lỗi nghiệp vụ. | Test 404 xanh dù path sai. | Contract error body riêng, assert mã lỗi và matching. |
| Tin rằng tạo client thủ công kiểm cả Spring DI. | Test xanh nhưng `@Value` production bị tráo. | Thêm test cấu hình bean/properties riêng. |
| Cùng reset journal trong nhiều test parallel. | Count khi 0 khi 2, test chập chờn. | Cô lập stub instance hoặc correlation ID, hạn chế shared reset. |
| Dùng một DTO “chung cho mọi producer”. | Schema thay đổi làm parse sai ngầm. | DTO/serializer riêng theo API và version. |
| Dùng chung retry/circuit breaker. | Inventory lỗi kéo theo Order bị chặn. | Tách client policies và instance IDs. |
| Chỉ kiểm happy path 200/200. | Không phát hiện hỏng fallback/timeout/404. | Thêm negative cases theo ma trận nghiệp vụ. |
| Luôn tải stub version mới nhất. | Cùng commit consumer nhưng test cho kết quả khác nhau. | Pin version, lưu artifact coordinates trong báo cáo. |
| Consumer test xanh nên bỏ qua producer verifier. | Stubs vẫn đúng trong khi producer thật đã đổi API. | Chặn publish khi producer verification chưa đạt. |

## 18. Bài thực hành: Checkout gọi Order và Inventory

Trên một consumer Spring Boot dùng Spring Cloud Contract Stub Runner:

1. **Chuẩn bị hai producer contracts** như mục 3, trong hai producer repositories riêng; mỗi producer có generated test và artifact `stubs` riêng.
2. **Chạy producer verification** cho Order và Inventory, xác nhận test thực sự chạy và PASS; cài hai artifact vào Maven local hoặc publish lên repository.
3. **Viết hai client** `OrderClient` và `InventoryClient` với constructors nhận base URL; cho mỗi client một header `X-Client` khác nhau.
4. **Viết `CheckoutSummaryService`** gọi Order trước rồi Inventory, kiểm SKU khớp và tính `enoughStock`.
5. **Dùng `@AutoConfigureStubRunner` với hai IDs** không gắn port cố định và `StubFinder` tra hai URL riêng.
6. **Chạy test phối hợp**: gọi `summaryFor(42)`, assert `requested=2`, `available=8` và `enoughStock=true`.
7. **Kiểm Admin request journal** ở từng stub: đúng một GET Order có `X-Client=checkout-orders`, đúng một GET Inventory có `X-Client=checkout-inventory`, không gọi chéo path.
8. **Gây lỗi cấu hình có chủ đích**: tráo hai URL khi tạo client. Quan sát consumer test FAIL hoặc unmatched requests; hoàn nguyên.
9. **Gây lỗi schema**: đổi `available` thành một trường khác trong fixture test không nhất quán với contract; xác nhận test phát hiện và phân biệt với producer verification.
10. **Thử negative path**: Order 404 → không gọi Inventory; Inventory 503 → xử lý retry/fallback theo chính sách đã quyết định. Tạo test-specific mapping hoặc hợp đồng lỗi được producer xác minh, không nhầm no-match với lỗi nghiệp vụ.
11. **Thử chạy song song** với port động và journal isolation để bảo đảm hai client không phụ thuộc một cổng cố định.
12. **Thử nâng từng stub version độc lập**, ghi lại tổ hợp version Checkout đang hỗ trợ, rồi đưa cả producer/consumer checks vào CI.

**Tiêu chí hoàn thành:** consumer gọi đúng **hai HTTP clients thật**, mỗi client chỉ sử dụng **base URL và cấu hình của producer tương ứng**; test chứng minh request xuất hiện ở **đúng hai WireMock servers**, dữ liệu được ghép chính xác, và pipeline phát hiện lỗi do tráo URL, nhầm header, đổi schema hoặc nâng version không tương thích.

## 19. Câu hỏi tự kiểm tra

1. Khi consumer gọi hai producer, vì sao chỉ một `stubBaseUrl` là thiết kế dễ gây lỗi?
2. Hai artifact `order-service:1.0.0:stubs` và `inventory-service:2.0.0:stubs` có bắt buộc dùng cùng version không?
3. `StubFinder.findStubUrl("com.acme", "order-service")` trả URL Maven repository hay URL stub HTTP đang chạy?
4. Vì sao `StubsMode.REMOTE` không có nghĩa client phải gọi Maven repository?
5. Trong ví dụ, điều gì bảo đảm `InventoryClient` không vô tình gửi request tới Order Service?
6. Vì sao dùng một `RestClient.Builder` mutable cho nhiều client có thể làm lẫn headers?
7. Nếu test tạo client trực tiếp từ URL động, nó đã kiểm được cấu hình `@Value` của Spring Boot production chưa?
8. Với request journal, làm sao chứng minh một request được gửi đúng tới từng stub và không có cross-talk?
9. Vì sao response 404 của WireMock chưa đủ để kết luận API producer trả lỗi tài nguyên không tồn tại?
10. Khi Order Service lỗi trước, có nhất thiết gọi Inventory Service nữa không? Ai quyết định quy tắc này?
11. Timeout, retry và circuit breaker có nên dùng chung cho mọi producer không? Vì sao?
12. Vì sao hai producer contract tests đạt riêng không tự động chứng minh nghiệp vụ Checkout phối hợp cả hai dịch vụ đúng?
13. Khi hai producer phát hành độc lập, cần quản lý ma trận version theo chiến lược nào để tránh breaking change?
14. Nếu consumer test đa producer xanh nhưng một producer đã không chạy generated verification, đã đủ điều kiện coi các stubs đáng tin chưa?

**Ghi nhớ:** **Kiểm thử consumer với nhiều producer phải tách biệt artifact, URL của stub server, cấu hình client và trạng thái kiểm thử**. Mỗi producer tự xác minh hợp đồng bằng Contract Verifier và phát hành `stubs` theo version; consumer dùng Stub Runner nạp các artifact, `StubFinder` lấy **địa chỉ động riêng**, rồi chạy **mã client và orchestration thật**. Kiểm cả response lẫn request journal trên từng stub, bảo vệ authentication/headers/retry riêng và đưa ma trận tương thích vào CI. Như vậy, một consumer tích hợp nhiều dịch vụ vẫn có thể được kiểm thử độc lập mà không đánh đổi tính chính xác hoặc vô tình gọi nhầm producer.
