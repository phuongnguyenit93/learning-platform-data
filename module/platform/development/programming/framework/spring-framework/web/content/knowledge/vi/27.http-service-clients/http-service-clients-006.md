# Quản lý nhiều dịch vụ, khả năng tương thích phiên bản và kiểm thử proxy HTTP Service Client

## 1. Bài toán và mục tiêu

Trong ứng dụng Spring, một tính năng như xem chi tiết đơn hàng có thể phải gọi **Inventory Service** để kiểm tra tồn kho, **Pricing Service** để đọc giá và **Shipping Service** để dự tính vận chuyển. Với HTTP Service Client, ta có thể khai báo interface bằng @HttpExchange, @GetExchange, @PostExchange rồi tạo proxy thực hiện HTTP thật qua RestClient hoặc WebClient.

Khi chỉ có một interface và một dịch vụ, việc tạo proxy khá ngắn. Khi có nhiều dịch vụ, các khó khăn mới xuất hiện: chọn đúng host, tránh rò token giữa các dịch vụ, cấu hình timeout và retry khác nhau, thay đổi phiên bản API không gây đứt gãy, và kiểm thử liệu proxy có gửi **đúng request thật** hay không.

Mục tiêu của bài:
1. Tổ chức nhiều HTTP Service Client theo từng remote service, với cấu hình base URL, xác thực, timeout và observability tách biệt.
2. Xác định ranh giới phiên bản của HTTP contract, nhận diện thay đổi tương thích và không tương thích ở cả request/response.
3. Tạo và quản lý proxy bằng HttpServiceProxyFactory trong Spring Framework 6.1+, đồng thời hiểu giới hạn phiên bản của cơ chế đăng ký theo group ở Spring Framework 7.
4. Kiểm thử request do proxy tạo ra (URI, method, header, body), mapping JSON, error status và contract evolution; phân biệt unit test với mock HTTP server và integration test.
5. Thiết kế migration có khả năng rollback khi upstream/dependent services được triển khai độc lập.

**Phạm vi:** đây là bài về **HTTP Service Client** của Spring; kiến thức về nhiều dịch vụ, versioning và testing được áp dụng trực tiếp cho proxy được sinh từ interface. Proxy là client gọi ra ngoài, **không phải server triển khai endpoint**, cũng không tự cung cấp API gateway, service discovery, circuit breaker hay registry.

## 2. Mỗi dịch vụ phải có hợp đồng và cấu hình riêng

Ví dụ một tính năng cần gọi hai API khác nhau:

| Dịch vụ | URL nền trong môi trường thử nghiệm | Contract | Dữ liệu |
| --- | --- | --- | --- |
| Inventory | https://inventory.example.test | GET /v1/stock/{sku} | StockResponse |
| Pricing | https://pricing.example.test | GET /v2/prices/{sku} | PriceResponse |

Việc dùng các host khác nhau chỉ là ví dụ; tên miền .test không có API thật. Lựa chọn phiên bản /v1 và /v2 ở đây minh họa hai dịch vụ độc lập có vòng đời contract khác nhau: **không phải mọi service đều phải lên v2 cùng lúc**.

Khai báo hai interface riêng:

~~~java
@HttpExchange(url = "/v1/stock", accept = MediaType.APPLICATION_JSON_VALUE)
public interface InventoryClient {
    @GetExchange("/{sku}")
    StockResponse findStock(@PathVariable("sku") String sku);
}

@HttpExchange(url = "/v2/prices", accept = MediaType.APPLICATION_JSON_VALUE)
public interface PricingClient {
    @GetExchange("/{sku}")
    PriceResponse findPrice(@PathVariable("sku") String sku);
}
~~~

Đây là **mã minh họa để tích hợp**; cần import annotation Spring tương ứng và định nghĩa StockResponse, PriceResponse. Nếu cả hai dùng chung factory và HTTP client với một baseUrl duy nhất, lời gọi có nguy cơ đi sai host. Cần phân biệt rõ:

- **Interface** sở hữu chữ ký request và kiểu response theo hợp đồng của một API.
- **RestClient/WebClient** sở hữu địa chỉ đích, cách kết nối, codec, header mặc định, auth/interceptor/filter và các chính sách truyền tải.
- **HttpServiceProxyFactory** ánh xạ method interface thành request gửi qua adapter.
- **Service/facade bên trong ứng dụng** điều phối kết quả từ nhiều API và chuyển sang model nghiệp vụ riêng.

Cấu trúc gợi ý:

~~~text
src/main/java/com/example/client/
├── inventory/
│   ├── InventoryClient.java
│   └── StockResponse.java
├── pricing/
│   ├── PricingClient.java
│   └── PriceResponse.java
├── configuration/
│   └── PartnerClientsConfiguration.java
└── facade/
    └── ProductAvailabilityService.java
~~~

Không cần ép tất cả HTTP interface vào một lớp giant client. Một nhóm endpoint có cùng host và policy có thể chia thành nhiều interface, nhưng phải rõ factory nào tạo proxy nào.

### 2.1. Tạo proxy một cách tường minh với Spring 6.1+

RestClient là HTTP client **đồng bộ** của Spring Framework 6.1; HttpServiceProxyFactory.builderFor(HttpExchangeAdapter) cũng có từ 6.1. Cách đăng ký bean trong ứng dụng Spring Boot:

~~~java
@Configuration
public class PartnerClientsConfiguration {

    @Bean
    InventoryClient inventoryClient(
            RestClient.Builder baseBuilder,
            PartnerAddresses addresses) {

        RestClient restClient = baseBuilder.clone()
            .baseUrl(addresses.inventory())
            .defaultHeader("X-Consumer", "order-service")
            .build();

        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(restClient))
            .build()
            .createClient(InventoryClient.class);
    }

    @Bean
    PricingClient pricingClient(
            RestClient.Builder baseBuilder,
            PartnerAddresses addresses) {

        RestClient restClient = baseBuilder.clone()
            .baseUrl(addresses.pricing())
            .defaultHeader("X-Consumer", "order-service")
            .build();

        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(restClient))
            .build()
            .createClient(PricingClient.class);
    }
}
~~~

**Đây là snippet tích hợp**, không phải chương trình độc lập. PartnerAddresses là bean cấu hình do ứng dụng định nghĩa, có các phương thức inventory() và pricing() trả URL; các interface/DTO là ví dụ ở trên. Clone builder trước mỗi nhánh vì RestClient.Builder **mutable**. Điều này tách cấu hình theo host và vẫn cho phép kế thừa customizers của RestClient.Builder do Spring Boot cấp.

**Không khai báo nhầm** hai proxy thành bean dùng chung một RestClient với baseUrl inventory. Một proxy có thể không phát lỗi cho tới khi được gọi; việc khởi tạo Spring context thành công chưa chứng minh routing đúng.

### 2.2. Tách policy theo target service

Một bộ policy tối thiểu cần xem xét cho mỗi host:

| Cấu hình | Inventory | Pricing | Lý do |
| --- | --- | --- | --- |
| Base URL | Config inventory | Config pricing | Tránh gọi sai host/env |
| Auth | Token/audience inventory | Token/audience pricing | Tránh lộ credential giữa các upstream |
| Timeout | Theo SLA tồn kho | Theo SLA báo giá | Dịch vụ có ngân sách độ trễ khác nhau |
| Retry | GET lỗi tạm thời, có giới hạn | GET lỗi tạm thời, có giới hạn | Không nhân request vô hạn |
| Rate limit/concurrency | Theo quota inventory | Theo quota pricing | Giới hạn tải độc lập |
| Error mapping | OutOfStock/Unavailable | PriceNotFound/Unavailable | Bảo vệ tầng nghiệp vụ khỏi lỗi transport |
| Logs/metrics | service=inventory | service=pricing | Định vị sự cố đúng upstream |

Ví dụ cấu hình ngoài code:

~~~yaml
partners:
  inventory:
    base-url: https://inventory.example.test
    connect-timeout: 1s
    read-timeout: 2s
  pricing:
    base-url: https://pricing.example.test
    connect-timeout: 1s
    read-timeout: 1s
~~~

Đây là **cấu hình ứng dụng tự định nghĩa**, không phải property Spring tự hiểu hoặc tự áp timeout. Cần @ConfigurationProperties/binding và truyền các giá trị vào request factory hoặc WebClient connector phù hợp. Dùng một biến cấu hình duy nhất cho cả hai host rồi tự nối path rất dễ làm sai ở lúc đổi môi trường.

Không đưa URL thật, token hay khóa bí mật vào annotation nếu chúng khác nhau theo môi trường; đường dẫn tài nguyên ổn định và contract version có thể nằm trong annotation, còn host/auth nên ở cấu hình. Nếu hai service dùng OAuth với audience khác nhau, cache token cũng phải phân biệt scope/audience.

### 2.3. Phần dùng chung nên là cơ chế tạo proxy, không là policy cứng

Khi có 10 interface, có thể tái sử dụng hàm nhỏ để tạo proxy:

~~~java
public final class HttpClientProxies {
    private HttpClientProxies() {}

    public static <T> T create(RestClient restClient, Class<T> api) {
        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(restClient))
            .build()
            .createClient(api);
    }
}
~~~

Bản thân factory có thể tạo nhiều interface cùng host/cấu hình nếu chúng cùng adapter. Nhưng **không gom các dịch vụ độc lập vào một adapter chung** chỉ để giảm số dòng Java. Mỗi remote service có thể cần auth, codec, logging, TLS, proxy HTTP, retry và kiểm thử khác nhau.

Với ứng dụng WebFlux, áp dụng cùng nguyên tắc bằng WebClientAdapter.create(webClient); interface trả Mono<T>/Flux<T> khi contract hỗ trợ reactive. Không dùng Mono<T> với RestClientAdapter rồi kỳ vọng proxy tự trở thành non-blocking.

## 3. Quản lý phiên bản hợp đồng HTTP khi nhiều dịch vụ phát triển độc lập

**Version của API** khác với version của thư viện Java chứa interface và khác với version triển khai của service. Một release server có thể vẫn giữ API /v1; một ứng dụng có thể dùng đồng thời Inventory v1 và Pricing v2.

Các cách thể hiện version do **server contract quy định**, không phải annotation quyết định:
- URL path: /v1/stock/{sku}, /v2/stock/{sku}.
- Media type: Accept: application/vnd.example.inventory.v2+json.
- Header được API định nghĩa, ví dụ X-Api-Version: 2.
- Query parameter nếu đó là quy ước của dịch vụ.

Chỉ chọn **một** quy tắc tương ứng với upstream, không tự thêm nhiều cơ chế version khác nhau vì nghĩ sẽ an toàn hơn. Đổi path/Accept/header phía client **không tự nâng cấp server**.

### 3.1. Thay đổi nào có thể tương thích?

Tương thích phải xét theo hướng dữ liệu và chính sách của **consumer đang chạy**, không chỉ theo cảm nhận của provider.

| Thay đổi phía provider | Rủi ro phía consumer | Cách đánh giá |
| --- | --- | --- |
| Thêm field tùy chọn vào JSON response | Thường tương thích nếu consumer bỏ qua field lạ | Test JSON decoder/DTO hiện tại |
| Thêm endpoint mới | Thường không ảnh hưởng endpoint cũ | Regression các endpoint đang dùng |
| Thêm optional query parameter với default giữ nguyên | Thường tương thích | Test request cũ vẫn có nghĩa như trước |
| Đổi tên/xóa field response đang được dùng | Có thể mất dữ liệu hoặc parse lỗi | Breaking trừ khi có migration/tương thích tạm thời |
| Đổi kiểu amount từ number sang string | DTO mapping có thể sai hoặc parse lỗi | Phải test type và semantics |
| Đổi đơn vị amount từ cents sang dollars | Có thể sai nghiệp vụ **dù JSON parse được** | Breaking về ngữ nghĩa, cần version/field mới |
| Biến field optional thành required trên request | Consumer cũ bị 4xx | Breaking |
| Đổi 404 sang 200 với body rỗng | Error handling thay đổi | Breaking đối với logic dựa status |
| Giảm TTL hoặc đổi timezone/precision | Có thể sai cache và so sánh thời gian | Đánh giá nghĩa vụ contract |
| Thêm giá trị enum mới | Consumer switch cứng có thể lỗi | Kiểm tra khả năng xử lý unknown |
| Thay đổi yêu cầu auth/headers | Consumer cũ có thể 401/403 | Migration config và rollout |
| Bỏ API /v1 | Consumer còn dùng /v1 sẽ lỗi | Chỉ sau khi quan sát đã di chuyển hết |

**Tolerant reader** có thể bỏ qua field JSON mới, nhưng cần ràng buộc các field cốt lõi. Ví dụ response giá:

~~~json
{
  "sku": "A-7",
  "amountInCents": 129900,
  "currency": "VND"
}
~~~

Tương lai upstream thêm field "taxIncluded": true thường không làm hỏng consumer nếu DTO được thiết kế cho phép extra fields. Nhưng nếu provider đổi amountInCents thành "price" và field cũ biến mất, consumer có thể nhận null hoặc 0, thậm chí tính sai giá nếu không validation.

Thiết kế DTO để chặn lỗi âm thầm:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record PriceResponse(String sku, Long amountInCents, String currency) {
    public PriceResponse {
        Objects.requireNonNull(sku, "sku required");
        Objects.requireNonNull(amountInCents, "amountInCents required");
        Objects.requireNonNull(currency, "currency required");
        if (amountInCents < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }
    }
}
~~~

Đây là snippet độc lập về model nếu thêm các import Jackson/java.util.Objects; không tự là cả chương trình. Dùng **Long** thay vì **long** cho dữ liệu bắt buộc giúp phát hiện field vắng mặt thay vì nhận giá trị mặc định 0. Constructor kiểm tra ngữ nghĩa ngay khi deserialize. @JsonIgnoreProperties(ignoreUnknown = true) phải là **lựa chọn có chủ đích**: hợp đồng nghiêm ngặt có thể yêu cầu fail khi xuất hiện field lạ.

### 3.2. Nên tách DTO wire format khỏi model nghiệp vụ

Interface định nghĩa **dữ liệu thực tế của remote API**; facade chuyển nó thành model nội bộ:

~~~java
public record Money(long amountMinorUnits, String currency) {}

public final class PriceFacade {
    private final PricingClient pricing;

    public PriceFacade(PricingClient pricing) {
        this.pricing = pricing;
    }

    public Money priceOf(String sku) {
        PriceResponse wire = pricing.findPrice(sku);
        return new Money(wire.amountInCents(), wire.currency());
    }
}
~~~

Snippet dùng PricingClient và PriceResponse ở trên; không phải chương trình độc lập. Khi upstream đổi contract, lớp adapter/DTO/facade là điểm chuyển đổi, trong khi phần tính toán đơn hàng không cần phụ thuộc JSON bên ngoài.

Nếu đổi đơn vị tiền, đừng đổi nghĩa của amountInCents trong lớp cũ. Tạo DTO mới (chẳng hạn PriceV3Response) và mapping rõ ràng, kiểm thử mức tiền cả trước và sau migration. Rủi ro **semantic drift** thường lớn hơn lỗi deserialize.

### 3.3. Migration nhiều phiên bản

Khi upstream muốn bỏ /v1 để chuyển /v2, trình tự phổ biến:

1. Provider công bố contract /v2, chính sách tương thích, thời điểm ngừng hỗ trợ /v1, và chuẩn bị test environment.
2. Consumer thêm interface/DTO v2 bên cạnh v1 (nếu cần chạy song song), cùng mapping nội bộ đủ ổn định.
3. Chạy contract/integration tests cho v2; test cả field không biết, null, lỗi status, auth và giới hạn hiệu năng.
4. Rollout từng nhóm/feature flag; log metric theo client version và service để quan sát trước khi chuyển toàn bộ traffic.
5. Có cơ chế rollback rõ ràng (chuyển config/feature flag về v1 còn được provider phục vụ).
6. Chỉ gỡ proxy v1 sau khi không còn call thực tế và hết cửa sổ rollback; cuối cùng provider mới ngừng endpoint cũ.

Dùng một header version có thể đơn giản hơn tạo interface mới khi hợp đồng chỉ thêm field tương thích. Nếu response shape và semantics thay đổi mạnh, hai interface/DTO tách biệt thường dễ review và rollback hơn. **Không đoán version bằng tên deployment**: service version 2.5.1 hoàn toàn có thể tiếp tục phục vụ API v1.

### 3.4. Chú ý giới hạn theo phiên bản Spring

Trong **Spring Framework 6.1**, bài này dùng bean @Configuration cùng RestClientAdapter/WebClientAdapter và HttpServiceProxyFactory.builderFor(...). Đây là cách đơn giản, được hỗ trợ trên baseline Spring Boot 3.3.x.

Spring Framework **7** bổ sung HTTP Service Registry và nhóm HTTP service với @ImportHttpServices, giúp đăng ký nhiều interface/proxy bean theo group. Spring Boot **4** có khả năng cấu hình HTTP service group tương ứng. **Không sử dụng @ImportHttpServices, HttpServiceProxyRegistry hoặc property spring.http.client.service.group.* trong ứng dụng Spring 6.1/Boot 3.3 rồi cho rằng chúng tự hoạt động**. Nếu dự án nâng cấp lên Spring 7/Boot 4, có thể nghiên cứu cơ chế mới và migration độc lập; thiết kế nhóm theo host/policy vẫn giữ nguyên.

## 4. Kiểm thử đúng đối tượng: interface, proxy, HTTP và hợp đồng

Một fake như:

~~~java
InventoryClient fake = sku -> new StockResponse(sku, true);
~~~

chỉ phù hợp **nếu interface thực sự là functional interface**; đoạn này minh họa ý tưởng giả lập phụ thuộc trong unit test tầng nghiệp vụ, không kiểm tra được annotation hay HTTP. Nó cũng không chứng minh proxy gọi đúng host và header.

Có ba lớp kiểm thử khác nhau:

| Lớp test | Chứng minh được | Không chứng minh |
| --- | --- | --- |
| Unit test facade với fake/mock InventoryClient | Điều phối, tính toán nghiệp vụ, fallback | URI/method/header/codec/proxy |
| HTTP proxy test với MockRestServiceServer | @HttpExchange mapping, request headers, query, response JSON và status trên RestClient | DNS/TLS, HTTP transport/network thực |
| Integration test với mock HTTP server chạy qua socket (WireMock/OkHttp MockWebServer) | Đường truyền HTTP thật, request serialization, timeout/kết nối và chính client production | Provider thật có tuân thủ contract không |
| Consumer-driven contract/provider verification | Provider có đáp ứng kỳ vọng consumer đã công bố hay không | Tự động chứng minh mọi nghiệp vụ nếu contract chưa đủ |
| Staging/E2E với provider thật | Tương thích thực tế của các service đang triển khai | Tái tạo hoàn chỉnh mọi tình huống failure |

**MockRestServiceServer** thay thế ClientHttpRequestFactory của RestClient, nên rất phù hợp kiểm thử nhanh proxy đồng bộ. Với WebClient/reactive, nên dùng mock HTTP server tương thích WebClient để kiểm tra request thật hoặc kiểm thử adapter tương ứng. Khi cần mô phỏng TLS, socket reset, timeout thật hoặc proxy HTTP, dùng test qua network/transport, không dựa vào MockRestServiceServer.

Mỗi proxy nên có test khẳng định:
- Đúng host và prefix URL, method, path variable, query encoding.
- Đúng header của service này; không lộ header/credential riêng của service khác.
- Đúng Content-Type/Accept và JSON serialization/deserialization.
- Thành công 2xx, không nội dung 204, 4xx/5xx, timeout/lỗi transport, request bị từ chối.
- DTO đọc được field bổ sung nếu contract cho phép, nhưng thiếu/đổi nghĩa field bắt buộc phải bị phát hiện.
- Bản v1/v2 có bộ dữ liệu hợp đồng riêng; test migration và đường rollback khi dùng song song.

## 5. Ví dụ Java 17 chạy được: hai service và test proxy thật

Ví dụ dưới đây **không gọi một API công khai**. Nó tạo hai RestClient/HTTP Service Client với hai base URL riêng; dùng MockRestServiceServer kiểm tra request thực tế mà proxy định gửi, trả JSON giả lập và xác minh response.

Yêu cầu: **Java 17+**, **Maven**, Spring Boot 3.3.13 (Spring Framework 6.1.x). Phiên bản được ghim để giữ API trong ví dụ nhất quán, không có nghĩa đây là phiên bản production mới nhất hoặc đang được hỗ trợ lâu dài.

### 5.1. Cấu trúc project

~~~text
multi-http-client-demo/
├── pom.xml
├── src/main/java/demo/
│   ├── InventoryClient.java
│   ├── PricingClient.java
│   ├── StockResponse.java
│   ├── PriceResponse.java
│   └── ClientProxies.java
└── src/test/java/demo/
    └── ProxyContractTest.java
~~~

### 5.2. Maven dependencies

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>multi-http-client-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

starter-web cung cấp RestClient/Jackson cho demo; starter-test cấp JUnit 5, spring-test và MockRestServiceServer. Dự án không cần ứng dụng web server chạy hay cấu hình Spring ApplicationContext để kiểm thử proxy.

### 5.3. Năm file mã nguồn

**src/main/java/demo/InventoryClient.java**:

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(url = "/v1/stock", accept = MediaType.APPLICATION_JSON_VALUE)
public interface InventoryClient {
    @GetExchange("/{sku}")
    StockResponse findStock(@PathVariable("sku") String sku);
}
~~~

**src/main/java/demo/PricingClient.java**:

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(url = "/v2/prices", accept = MediaType.APPLICATION_JSON_VALUE)
public interface PricingClient {
    @GetExchange("/{sku}")
    PriceResponse findPrice(@PathVariable("sku") String sku);
}
~~~

**src/main/java/demo/StockResponse.java**:

~~~java
package demo;

public record StockResponse(String sku, boolean available) {}
~~~

**src/main/java/demo/PriceResponse.java**:

~~~java
package demo;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.Objects;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PriceResponse(String sku, Long amountInCents, String currency) {
    public PriceResponse {
        Objects.requireNonNull(sku, "sku required");
        Objects.requireNonNull(amountInCents, "amountInCents required");
        Objects.requireNonNull(currency, "currency required");
        if (amountInCents < 0) {
            throw new IllegalArgumentException("amountInCents must be >= 0");
        }
    }
}
~~~

PriceResponse chấp nhận thuộc tính mới không được biết đến (theo contract minh họa), nhưng từ chối thiếu amountInCents. Kiểm tra trong constructor biến lỗi dữ liệu thành lỗi rõ ràng trước khi dùng vào tính giá.

**src/main/java/demo/ClientProxies.java**:

~~~java
package demo;

import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

public final class ClientProxies {
    private ClientProxies() {}

    public static <T> T create(RestClient restClient, Class<T> api) {
        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(restClient))
            .build()
            .createClient(api);
    }
}
~~~

### 5.4. Kiểm thử bằng MockRestServiceServer

**src/test/java/demo/ProxyContractTest.java**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.HttpClientErrorException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import org.springframework.http.HttpStatus;

public class ProxyContractTest {

    @Test
    void proxiesRouteToSeparateHostsAndKeepHeadersSeparate() {
        RestClient.Builder inventoryBuilder = RestClient.builder()
            .baseUrl("https://inventory.example.test")
            .defaultHeader("X-Target-Service", "inventory");
        RestClient.Builder pricingBuilder = RestClient.builder()
            .baseUrl("https://pricing.example.test")
            .defaultHeader("X-Target-Service", "pricing");

        // Bind mock servers BEFORE building RestClient instances.
        MockRestServiceServer inventoryServer =
            MockRestServiceServer.bindTo(inventoryBuilder).build();
        MockRestServiceServer pricingServer =
            MockRestServiceServer.bindTo(pricingBuilder).build();

        InventoryClient inventory = ClientProxies.create(
            inventoryBuilder.build(), InventoryClient.class);
        PricingClient pricing = ClientProxies.create(
            pricingBuilder.build(), PricingClient.class);

        inventoryServer.expect(
                requestTo("https://inventory.example.test/v1/stock/A-7"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-Target-Service", "inventory"))
            .andRespond(withSuccess(
                "{\"sku\":\"A-7\",\"available\":true}",
                MediaType.APPLICATION_JSON));

        pricingServer.expect(
                requestTo("https://pricing.example.test/v2/prices/A-7"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-Target-Service", "pricing"))
            .andRespond(withSuccess(
                "{\"sku\":\"A-7\",\"amountInCents\":129900,\"currency\":\"VND\"}",
                MediaType.APPLICATION_JSON));

        assertEquals(new StockResponse("A-7", true),
            inventory.findStock("A-7"));
        assertEquals(new PriceResponse("A-7", 129900L, "VND"),
            pricing.findPrice("A-7"));

        inventoryServer.verify();
        pricingServer.verify();
    }

    @Test
    void newlyAddedResponseFieldIsAccepted() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://pricing.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        PricingClient pricing = ClientProxies.create(
            builder.build(), PricingClient.class);

        server.expect(requestTo(
                "https://pricing.example.test/v2/prices/A-7"))
            .andRespond(withSuccess(
                "{\"sku\":\"A-7\",\"amountInCents\":129900," +
                "\"currency\":\"VND\",\"taxIncluded\":true}",
                MediaType.APPLICATION_JSON));

        assertEquals(129900L,
            pricing.findPrice("A-7").amountInCents());
        server.verify();
    }

    @Test
    void missingRequiredPriceFieldFailsContractValidation() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://pricing.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        PricingClient pricing = ClientProxies.create(
            builder.build(), PricingClient.class);

        server.expect(requestTo(
                "https://pricing.example.test/v2/prices/A-7"))
            .andRespond(withSuccess(
                "{\"sku\":\"A-7\",\"currency\":\"VND\"}",
                MediaType.APPLICATION_JSON));

        assertThrows(RestClientException.class,
            () -> pricing.findPrice("A-7"));
        server.verify();
    }

    @Test
    void missingItemReturnsHttp404ErrorByDefault() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://inventory.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        InventoryClient inventory = ClientProxies.create(
            builder.build(), InventoryClient.class);

        server.expect(requestTo(
                "https://inventory.example.test/v1/stock/UNKNOWN"))
            .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(HttpClientErrorException.NotFound.class,
            () -> inventory.findStock("UNKNOWN"));
        server.verify();
    }
}
~~~

Giải thích bằng chứng từng bài test:
1. **proxiesRoute...:** tạo hai builder và hai mock server độc lập; từng proxy phải đi đúng URL, method và header, sau đó JSON được map thành record tương ứng. Test có một kỳ vọng ở mỗi mock server, vì vậy gọi chéo host hoặc bỏ sót request sẽ thất bại.
2. **newlyAdded...:** JSON response thêm field taxIncluded; @JsonIgnoreProperties(ignoreUnknown = true) cho phép reader cũ tiếp tục đọc field đang dùng. Đây là **một dạng tương thích**, không chứng minh mọi thay đổi đều an toàn.
3. **missingRequired...:** response bỏ amountInCents; constructor yêu cầu non-null nên deserialization phải thất bại và được báo qua exception trên RestClient. Điều này tránh dùng âm thầm giá bằng 0.
4. **missingItem...:** 404 theo chính sách status mặc định của RestClient được phát ra thành HttpClientErrorException.NotFound, không biến thành StockResponse rỗng.

Chạy:

~~~bash
mvn -q test
~~~

JUnit/Surefire chạy **bốn test**. Nếu tất cả thành công, Maven trả **exit code 0**; tuỳ Maven/IDE, chế độ -q có thể không in bảng tóm tắt. Xem báo cáo trong target/surefire-reports/ để xác minh số bài test và trạng thái thực tế. Nếu có lỗi compile, assertion hoặc mapping, Maven trả exit code khác 0; không coi đoạn output dự kiến là bằng chứng đã chạy tại môi trường của người đọc.

**Lưu ý:** ví dụ minh họa API Java 17/Spring 6.1 bằng file và test code đầy đủ; các URL .test không cần DNS thật bởi MockRestServiceServer intercept request. Không nên thay mock bằng RestClient thật trỏ vào URL đó khi chưa có server. Để kiểm thử transport thực, chạy WireMock/MockWebServer ở localhost và cập nhật baseUrl tương ứng.

### 5.5. Từ proxy test đến contract test liên dịch vụ

Proxy test chỉ mô phỏng hợp đồng **consumer nghĩ rằng provider có**. Nếu mock trả trường amountInCents nhưng provider deploy thật trả priceInDollars, test consumer vẫn xanh vì mock sai thực tế. Cần gắn contract vào một nguồn chung hoặc kiểm tra provider thực thi các expectation đó.

Một quy trình consumer-driven contract (dùng Pact hoặc công cụ tương tự nếu tổ chức cần) thường là:
1. Consumer ghi các request thật mình dùng và các response tối thiểu mình yêu cầu.
2. Consumer test dựa trên contract; tạo/công bố artifact contract có version.
3. Provider chạy verification với artifact của consumer để chứng minh endpoint phù hợp.
4. Pipeline deployment đối chiếu provider version và nhóm consumer còn tồn tại; phát hành khi các cặp tương thích.
5. Thêm test tích hợp bằng mock HTTP server hoặc môi trường thực để bắt sai khác transport, auth, TLS, redirect và cấu hình vận hành.

Cẩn thận với “hợp đồng quá chặt”: nếu consumer không dùng field taxIncluded, không cần khóa toàn bộ response JSON chỉ để so khớp byte. Nhưng phải kiểm tra **đúng field và semantics thực sự cần cho nghiệp vụ**.

## 6. Unit test và integration test cho cấu hình nhiều proxy

Một lỗi phổ biến là chỉ test các interface riêng lẻ với builder tự tạo trong test, trong khi cấu hình production lại sử dụng sai baseUrl hoặc chung interceptor cho hai host. Do đó, ngoài test ở phần 5, cần test **wiring thực tế**:

- Tạo Spring context tối thiểu có PartnerClientsConfiguration với property inventory.base-url và pricing.base-url khác nhau.
- Gắn server stub độc lập vào từng cấu hình client, hoặc dùng WireMock trên hai cổng localhost.
- Lấy InventoryClient và PricingClient từ ApplicationContext; xác nhận bean nào gọi host nào.
- Gửi một request có credentials dành cho inventory; xác nhận header đó **không xuất hiện** trên request sang pricing.
- Kiểm tra policy 404/429/503 và timeout qua chính bean đã đăng ký, chứ không thông qua RestClient test tự tạo khác cấu hình.
- Khi bật đổi version hoặc feature flag, test branch cũ/v1 và mới/v2; xóa branch cũ khi hết thời hạn rollback.

Cần phân biệt **assertion của mock** với **thực thi network thật**. Test mock tương đối nhanh, ổn định và xác minh mapping; test socket thực xác minh timeout, DNS/proxy, TLS và wire encoding. Đối với nhiều remote dependencies, kết hợp cả hai ở mức hợp lý thay vì biến mọi unit test thành E2E chậm.

### Khi dùng WebClient/reactive

WebClientAdapter proxy thường trả Mono<T>/Flux<T>. Cần test reactive chain có subscriber, timeout, backpressure/streaming khi áp dụng và retryWhen scope. Với một mock HTTP server qua localhost:

~~~java
WebClient webClient = WebClient.builder()
    .baseUrl("http://localhost:8089")
    .build();

PricingReactiveClient client = HttpServiceProxyFactory
    .builderFor(WebClientAdapter.create(webClient))
    .build()
    .createClient(PricingReactiveClient.class);

StepVerifier.create(client.findPrice("A-7"))
    .assertNext(price -> assertEquals("A-7", price.sku()))
    .verifyComplete();
~~~

Đây là **snippet tích hợp**, không tự chạy nếu thiếu PricingReactiveClient, server test được khởi tạo sẵn và dependency reactor-test. Đừng dùng .block() trong handler WebFlux chỉ để “test nhanh”; dùng StepVerifier trong test, hoặc subscribe/return publisher đúng cách. Thực thi subscriber nhiều lần có thể phát request nhiều lần; kiểm thử retry phải tính cả số request thực tế.

## 7. Lỗi thường gặp khi quản lý nhiều service

1. **Hai proxy chia sẻ sai baseUrl:** method annotation đúng nhưng request đi nhầm upstream. Kiểm thử URL trọn vẹn, clone builder và cấu hình theo host.
2. **Header hoặc token của service A rò sang B:** dùng chung interceptor/defaultHeader không phân biệt target. Tách cấu hình và kiểm thử header âm tính (credential A không có trong request B).
3. **Nhầm code version với API version:** release ứng dụng v3 không có nghĩa endpoint HTTP /v3 đã tồn tại. Version phải từ contract provider.
4. **Đọc JSON quá dễ dãi:** bỏ qua missing required fields, dùng primitive mặc định 0 hoặc null rồi tính toán sai. Validate DTO tại boundary.
5. **Đọc JSON quá nghiêm ngặt:** từ chối field bổ sung vô hại gây lỗi trong rollout provider trước consumer. Quyết định tolerance theo schema contract.
6. **Thêm version vào interface mà không kiểm thử server:** code compile nhưng server có thể không hỗ trợ URL/Accept mới.
7. **Chỉ mock interface ở unit test:** không bắt annotation sai path/query/header, không thấy serialization lỗi. Thêm proxy test với HTTP expectation.
8. **Chỉ test proxy với builder nhân tạo:** production bean có thể cấu hình sai. Thêm integration test cho Spring configuration.
9. **Assume 2xx luôn mang DTO:** 204 No Content có thể tạo body rỗng; contract phải nêu rõ.
10. **Retry toàn bộ POST:** request bị timeout không chứng minh server chưa ghi. Cần idempotency server và retry có giới hạn.
11. **Lặp retry ở nhiều tầng:** client, gateway và service cùng retry làm tăng attempt theo cấp số nhân; chỉ định ownership của retry.
12. **Dùng API Spring 7 trên Spring 6.1:** @ImportHttpServices/group registry không tồn tại trên classpath cũ; version gate và nâng cấp có kế hoạch.
13. **Quên thời hạn ngừng v1:** còn consumer ít traffic tới v1 bị lỗi khi provider xóa API; cần metrics theo caller/version.
14. **Chỉ kiểm kiểu dữ liệu, bỏ semantics:** field tiền tệ đổi đơn vị, timezone thay đổi, default logic khác có thể đúng JSON nhưng sai nghiệp vụ.

## 8. Checklist trước khi phát hành

### Trước khi merge client mới

- Interface @HttpExchange trỏ đúng method, path và API version; DTO, nullability, status semantics được tài liệu hóa.
- Mỗi remote host có cấu hình riêng; secret lấy từ hệ thống quản lý cấu hình/secret, không hardcode.
- Timeout, retry budget và circuit/rate control phù hợp SLA và khả năng chịu tải của từng provider.
- Unit test facade, proxy test URI/header/body/codec/status và integration test wiring đều phù hợp phạm vi thay đổi.
- Có thể xác minh provider contract bằng verification hoặc môi trường tích hợp thật.

### Trước khi migration sang API version mới

- Liệt kê consumer/deployments đang sử dụng version cũ và thời gian provider còn hỗ trợ.
- Viết kiểm thử dữ liệu mẫu cũ/mới, bao gồm thay đổi field/kiểu/semantics và mã lỗi.
- Có cách rollout và rollback trong khi cả hai version còn hoạt động.
- Đo metrics theo service, version, status, latency, số retry; cảnh báo nếu xuất hiện tăng đột biến lỗi mapping/4xx/5xx.
- Gỡ version cũ **sau** khi không còn traffic hoặc consumer phụ thuộc, không chỉ sau khi phát hành version mới.

## 9. Tổng kết

Để quản lý nhiều HTTP Service Client trong Spring, hãy tách **hợp đồng interface**, **client configuration theo dịch vụ**, **factory/proxy** và **facade nghiệp vụ**. Versioning là trách nhiệm phối hợp consumer–provider; tương thích phải xét cả JSON shape, mã lỗi và **ngữ nghĩa dữ liệu**. Kiểm thử proxy phải chạy qua adapter thật để xác minh request HTTP nó tạo ra, sau đó bổ sung provider contract verification và integration test cho transport/wiring.

Trên **Spring Framework 6.1 / Boot 3.3**, tạo RestClient/WebClient và HttpServiceProxyFactory theo từng nhóm cấu hình là cơ chế phù hợp. Khi dùng **Spring Framework 7 / Boot 4**, có thể đánh giá HTTP Service Registry theo group để giảm cấu hình lặp, nhưng vẫn phải giữ ranh giới auth, versioning, rollback và test theo dịch vụ.

## 10. Tài liệu chính thức và đọc thêm

- Spring Framework 6.1 API — HttpServiceProxyFactory, builderFor và createClient: https://docs.spring.io/spring-framework/docs/6.1.7/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html
- Spring Framework 6.1 API — RestClient.Builder (clone/baseUrl/defaultHeader): https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/web/client/RestClient.Builder.html
- Spring Framework 6.1 API — MockRestServiceServer.bindTo(RestClient.Builder): https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html
- Spring Framework Reference — Testing Client Applications: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html
- Spring Framework Reference — HTTP Service Client: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Engineering Blog — HTTP Service Client Enhancements (Spring Framework 7): https://spring.io/blog/2025/09/23/http-service-client-enhancements/
