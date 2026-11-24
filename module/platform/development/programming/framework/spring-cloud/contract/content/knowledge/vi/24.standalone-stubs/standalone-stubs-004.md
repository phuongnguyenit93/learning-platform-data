# Công bố cổng và URL cho ứng dụng gọi thử

## Mục tiêu bài học

Trong **Spring Cloud Contract**, producer định nghĩa hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Contract Verifier sinh kiểm thử phía producer, còn các stub được đóng gói để consumer chạy thử bằng **Stub Runner**. Khi chạy **stub độc lập**, một bước thường bị bỏ sót là **công bố địa chỉ thật của stub server cho ứng dụng gọi thử**.

Một stub server có thể hoạt động nhưng consumer vẫn gặp `Connection refused`, `UnknownHostException` hoặc HTTP 404 vì ứng dụng đang gọi sai **host, port, scheme hoặc URL path**. Trong CI hoặc Docker, lỗi càng dễ xảy ra nếu nhầm cổng quản lý của Stub Runner với cổng HTTP của một stub, hoặc dùng `localhost` không đúng ngữ cảnh.

Sau bài học, bạn có thể:

- Phân biệt tọa độ stub artifact với **HTTP base URL** của stub đang chạy.
- Phân biệt **cổng quản lý của standalone runner** và **cổng phục vụ request** của mỗi HTTP stub.
- Thiết kế cách chọn cổng cố định hoặc động và chuyển URL sang consumer.
- Cấu hình Spring Boot client, WireMockServer độc lập hoặc standalone Stub Runner Boot theo phạm vi thích hợp.
- Hiểu khác biệt giữa **host port**, **container port**, Kubernetes Service và service discovery.
- Tạo readiness check bằng request thật, phát hiện việc gọi nhầm dịch vụ ngoài môi trường test.
- Dùng CI kiểm tra cả producer contract tests, stub readiness và consumer assertions.

## 1. Các loại định danh không được đánh đồng

Giả sử Order Service phát hành stub JAR có tọa độ:

~~~text
com.example.orders:order-service:1.4.2:stubs
~~~

Một standalone runner tải artifact và chạy Order stub trên cổng `8090`. Nếu Checkout đang chạy trên cùng máy, URL để gọi thử có thể là:

~~~text
http://localhost:8090/api/orders/ORD-1001
~~~

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **group ID** | `com.example.orders` | Namespace của artifact trong repository |
| **artifact ID** | `order-service` | Module đã phát hành stub |
| **version** | `1.4.2` | Phiên bản artifact |
| **classifier** | `stubs` | Chọn stub JAR, không phải JAR ứng dụng |
| **stub host** | `localhost` | Hostname có thể truy cập từ nơi consumer chạy |
| **stub HTTP port** | `8090` | Cổng HTTP listener phục vụ mappings |
| **base URL** | `http://localhost:8090` | Tiền tố URL cấu hình cho HTTP client |
| **contract path** | `/api/orders/ORD-1001` | Đường dẫn HTTP được mô tả trong hợp đồng |
| **management port** | `8750` | Cổng ứng dụng điều khiển standalone runner nếu có |

**Tọa độ artifact không phải URL.** Tọa độ giúp Stub Runner tải đúng bộ mappings; runtime và network quyết định URL mà ứng dụng gọi được.

Một nhầm lẫn phổ biến khác: `8090` ở cuối một Stub Runner ID có thể là **cổng HTTP stub**, chứ không phải classifier hay phần của phiên bản Maven.

## 2. Standalone runner điều khiển nhiều stub servers

Một **Stub Runner Boot** độc lập có thể tải nhiều stub artifacts và khởi động các HTTP stub servers. Ví dụ:

~~~mermaid
flowchart LR
    R["Artifact repository"] --> S["Stub Runner Boot<br/>management: 8750"]
    S --> O["Order HTTP stub<br/>port 8090"]
    S --> P["Payment HTTP stub<br/>port 8091"]
    C["Checkout consumer test"] -->|"GET /api/orders/..."| O
    C -->|"GET /api/payments/..."| P
~~~

Trong sơ đồ này:

- `8750` là cổng **ứng dụng điều khiển** runner.
- `8090` là cổng HTTP phục vụ các request của Order stub.
- `8091` là cổng HTTP phục vụ Payment stub.
- Checkout gọi `http://localhost:8090/api/orders/ORD-1001`, **không mặc định gọi** `http://localhost:8750/api/orders/ORD-1001`.
- API quản lý runner (nếu có) khác với API nghiệp vụ được WireMock mô phỏng.

Khi tự chạy một `WireMockServer` thay vì Stub Runner Boot, có thể **chỉ có một HTTP listener** và không tồn tại management port riêng. Không cố áp dụng mô hình hai cổng cho mọi kiểu chạy WireMock.

## 3. HTTP contract quy định path, không quy định stub host

Ví dụ hợp đồng YAML:

~~~yaml
description: "Lấy đơn hàng đã thanh toán"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Hợp đồng mô tả **HTTP method, URL path, request headers, response status và body**. Nó không yêu cầu runner phải được cài trên `localhost` hoặc cổng `8090`.

| Nguồn thông tin | Điều được quyết định |
| --- | --- |
| Contract DSL | Method/path/header/body matcher và response |
| Contract Verifier | Generated producer tests và stub mapping |
| Stub artifact | Đóng gói đúng bộ mappings theo group/artifact/version |
| Standalone runner | Artifact nào được tải, những stub server nào được khởi động |
| Network/orchestration | Hostname, port công bố và routing |
| Consumer test config | Base URL hoặc service ID được HTTP client sử dụng |
| CI | Kiểm tra toàn bộ chuỗi và ghi lại bản build thực sự đã thử |

Đổi cổng của stub là **thay đổi cách chạy test**, thường không phải breaking change của HTTP API. Đổi `/api/orders/ORD-1001` hoặc trường `status` lại có thể phá vỡ consumer và cần kiểm chứng qua hợp đồng.

## 4. Ví dụ cấu hình Standalone Stub Runner Boot

Tùy phiên bản, Stub Runner Boot nhận danh sách ID và các thuộc tính runtime qua application properties/CLI. Ví dụ dưới đây minh họa hai cổng khác nhau; **tên property chính xác và cách chạy JAR phải được đối chiếu với phiên bản Stub Runner Boot đang dùng**:

~~~bash
java -jar stub-runner-boot.jar \
  --server.port=8750 \
  --stubrunner.ids=com.example.orders:order-service:1.4.2:stubs:8090 \
  --stubrunner.stubsMode=LOCAL
~~~

Ý nghĩa dự kiến:

- `server.port=8750`: cổng của ứng dụng Boot điều khiển stub.
- `stubrunner.ids=...:8090`: chọn artifact và gán cổng HTTP cho Order stub.
- `stubrunner.stubsMode=LOCAL`: sử dụng nguồn artifact local theo cơ chế Stub Runner hỗ trợ.

Trong những test Spring Boot sử dụng `@AutoConfigureStubRunner`, bạn có thể gặp namespace `spring.cloud.contract.stubrunner.*`. Trong standalone Boot, một số phiên bản dùng `stubrunner.*`. **Không thay namespace theo suy đoán**: phải xác minh trong log cấu hình runtime và tài liệu đúng release.

Nếu chọn `LOCAL`, môi trường chạy cần có stub JAR tương ứng trong repository local. Nếu artifact nằm ở Maven repository từ xa, phải cấu hình nguồn tải và quyền truy cập phù hợp. **Process runner khởi động thành công chưa chứng minh stub JAR đã được tải.**

### Khi có hai stub artifacts

Ví dụ khai báo về mặt ý tưởng:

~~~text
com.example.orders:order-service:1.4.2:stubs:8090
com.example.billing:payment-service:2.3.0:stubs:8091
~~~

Cách phân cách nhiều IDs trên CLI hoặc YAML có thể khác nhau theo property binder/version; hãy kiểm tra giá trị runner thực sự nhận. Không đoán một chuỗi được parse thành hai artifact chỉ vì nó trông hợp lý.

Khi các stub khởi động đúng:

~~~text
Order base URL:   http://localhost:8090
Payment base URL: http://localhost:8091
~~~

Cổng `8750` chỉ phục vụ các thao tác của **runner management API** nếu phiên bản đó cung cấp; không được suy rằng nó cũng là cổng HTTP stub.

## 5. Cổng cố định hay cổng động?

| Cách chọn | Ưu điểm | Rủi ro và cách xử lý |
| --- | --- | --- |
| **Cố định**, ví dụ 8090 | Dễ cấu hình client ngoài tiến trình | Có thể bị process khác chiếm; CI cần cách ly job |
| **Động** | Tránh va chạm, phù hợp test song song | Phải lấy port sau khi server start và truyền cho consumer |
| **Dải cổng** | Hữu ích khi có firewall hoặc nhiều stubs | Cần bộ điều phối và tránh gán trùng |
| **Container internal port cố định** | Dễ gọi giữa container cùng network | Published host port có thể khác internal port |

Một lỗi hay gặp: WireMock chọn port động, còn client vẫn gọi `http://localhost:8090`. Khi đó client không thể biết cổng mới, thậm chí có thể gọi nhầm một process khác.

### Ví dụ WireMockServer với port động

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

WireMockServer stub = new WireMockServer(
    wireMockConfig().dynamicPort()
);
stub.start();

try {
    int port = stub.port();
    String baseUrl = "http://localhost:" + port;
    // Đưa baseUrl vào HTTP client rồi thực hiện assertions.
} finally {
    stub.stop();
}
~~~

Đây là **WireMock Java API**, không phải API lấy port của một runner chạy từ xa. Với standalone process, có thể lấy port từ cấu hình cố định, API của runner được version hỗ trợ hoặc metadata orchestration công bố.

Nếu runner chọn cổng động, consumer chỉ nên bắt đầu test **sau khi** địa chỉ và port cuối cùng đã được xác định.

## 6. Base URL phải là cấu hình của ứng dụng consumer

Không nên hardcode stub URL trong logic nghiệp vụ:

~~~java
// Phản ví dụ: URL môi trường test nằm trong business code.
String url = "http://localhost:8090/api/orders/" + orderId;
~~~

Với consumer Spring Boot, có thể cấu hình:

~~~yaml
# application-contract.yml
orders:
  api:
    base-url: "http://localhost:8090"
~~~

Ví dụ một client dùng Spring `RestClient`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class OrderApiClient {
    private final RestClient restClient;

    public OrderApiClient(
        RestClient.Builder builder,
        @Value("${orders.api.base-url}") String baseUrl
    ) {
        restClient = builder.baseUrl(baseUrl).build();
    }

    public OrderResponse getById(String id) {
        return restClient.get()
            .uri("/api/orders/{id}", id)
            .retrieve()
            .body(OrderResponse.class);
    }
}
~~~

`OrderResponse` là DTO ứng dụng minh họa. Test cần inject một URL thực của stub; runtime khác có thể trỏ đến dịch vụ tương ứng. Không để giá trị `localhost:8090` mặc định đi vào cấu hình production.

### Biến môi trường cho CI

~~~yaml
orders:
  api:
    base-url: "${ORDER_API_BASE_URL:http://localhost:8090}"
~~~

Cơ chế environment/property placeholder cho phép truyền `ORDER_API_BASE_URL` từ test runner. Trong pipeline nghiêm ngặt, có thể **không cung cấp default** để build fail nếu chưa công bố URL, thay vì âm thầm dùng cổng sai.

Cấu hình phải truyền **toàn bộ scheme://host:port**; chỉ truyền số port không đủ khi client và stub ở những môi trường mạng khác nhau.

## 7. Truyền URL động bằng DynamicPropertySource

Một test Spring Boot tự quản lý WireMock có thể dùng `@DynamicPropertySource` để cung cấp URL:

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

@SpringBootTest
class OrderConsumerContractTest {

    static final WireMockServer STUB =
        new WireMockServer(wireMockConfig().dynamicPort());

    static {
        STUB.start();
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "orders.api.base-url",
            () -> "http://localhost:" + STUB.port()
        );
    }

    @AfterAll
    static void close() {
        STUB.stop();
    }
}
~~~

Đây là **khung lifecycle và cấu hình**, chưa có mappings hoặc assertions. Việc start trong static initializer được dùng để minh họa rằng stub phải hoạt động trước khi Spring đọc dynamic properties. Trong dự án thật có thể dùng WireMock JUnit extension hoặc một cơ chế lifecycle phù hợp hơn.

Một test ngoài tiến trình dùng **standalone Stub Runner Boot** không thể đơn giản gọi `STUB.port()` như trên. Nó phải nhận URL qua orchestrator, cấu hình runner hoặc API truy vấn được hỗ trợ.

### Khi Stub Runner chạy trong cùng Spring test context

Một số phiên bản tích hợp `@AutoConfigureStubRunner` cung cấp các tiện ích như `StubFinder` hoặc `@StubRunnerPort` để lấy stub URI/port:

~~~java
// Phác thảo, cần dùng API đúng version và thời điểm khởi tạo:
// URI stubUrl = stubFinder.findStubUrl("com.example.orders", "order-service");
// Tạo HTTP client với stubUrl và kiểm chứng consumer.
~~~

Không tự đoán chữ ký API hay dùng `@DynamicPropertySource` bất kể lifecycle; có trường hợp Stub Runner được khởi động **sau lúc** dynamic properties được đăng ký. Khi đó cần phương án wiring khác hoặc port cố định đã được kiểm soát.

## 8. Từ máy host vào Docker: published port

Giả sử container stub nghe HTTP tại port `8090` nhưng Docker publish host port `18090`:

~~~text
Host port 18090 -> Container port 8090
~~~

Một cấu hình Compose **minh họa cấu trúc mạng**:

~~~yaml
services:
  order-stub:
    image: example/stub-runner-test:1.4.2
    ports:
      - "18090:8090"
      - "18750:8750"

  checkout-test:
    image: example/checkout-test:2.8.0
    environment:
      ORDER_API_BASE_URL: "http://order-stub:8090"
    depends_on:
      - order-stub
~~~

**Không có bảo đảm image `example/...` tồn tại.** Đây là ví dụ mạng; cần xây dựng/chọn image thật, khởi động Stub Runner trên đúng port, mount/cấp stub artifact và cấu hình repository theo công cụ đã chọn.

Ba góc nhìn:

| Consumer nằm ở đâu? | URL dự kiến |
| --- | --- |
| Process hoặc curl trên **máy host** | `http://localhost:18090/api/orders/ORD-1001` |
| Checkout container trong **cùng Compose network** | `http://order-stub:8090/api/orders/ORD-1001` |
| Process **bên trong order-stub container** | `http://localhost:8090/api/orders/ORD-1001` |

`localhost` trong container Checkout chính là **container Checkout**, không phải container WireMock. Cổng 18090 được công bố cho phía host, trong khi container cùng network thường gọi bằng service name và **internal port 8090**.

### Bind interface khác với destination host

Trong container, stub process cần lắng nghe interface có thể truy cập qua mạng container; thường điều này có nghĩa bind tới `0.0.0.0` khi cấu hình cho phép. Nhưng **`0.0.0.0` là địa chỉ bind**, không phải hostname nên đưa vào URL của consumer.

Cấu hình Docker `ports` cũng **không tự làm một process đang bind chỉ vào loopback trong container thành có thể truy cập bên ngoài**; phải kiểm tra listener và routing thật.

### depends_on không phải readiness

Compose có thể start `order-stub` trước `checkout-test` nhưng Stub Runner còn đang phân giải artifact. `depends_on` đơn thuần không chứng minh mapping đã sẵn sàng. Cần có readiness check và đợi theo điều kiện, với timeout hữu hạn, trước khi consumer gọi.

## 9. Công bố management port và stub port trong container

Với standalone Stub Runner Boot ví dụ:

~~~text
Host 18750 --> Container 8750 : Runner management
Host 18090 --> Container 8090 : Order HTTP stub
~~~

Nếu người học gửi GET `/api/orders/ORD-1001` tới `localhost:18750`, server có thể trả 404 vì đó là cổng quản lý, không phải WireMock mapping.

**Giải pháp:** gọi `http://localhost:18090/api/orders/ORD-1001` từ host, hoặc `http://order-stub:8090/api/orders/ORD-1001` từ container Checkout.

Nếu runner chọn **port động** nhưng Docker chỉ publish `8090`, consumer ngoài container có thể không đến được port thật. Cần gán cổng ổn định đã publish hoặc để orchestrator công bố/forward đúng cổng được cấp phát.

Không nên publish management API hoặc một bộ stub nhạy cảm trực tiếp ra Internet. Đặt chúng trong mạng test nội bộ và giới hạn truy cập.

## 10. Kubernetes Service và môi trường remote

Nếu consumer chạy trong cluster, địa chỉ ổn định thường là **Kubernetes Service DNS**, không phải IP của một Pod:

~~~text
http://order-stub.contract-test.svc.cluster.local:8090
~~~

Đây là URL minh họa. Service có thể expose một `port` khác `targetPort` của container; cần xác minh mapping trong manifest thực tế.

~~~mermaid
flowchart LR
    C["Checkout test Pod"] --> K["Kubernetes Service<br/>order-stub:8090"]
    K --> P["Stub Pod<br/>listener/targetPort"]
    P --> W["WireMock mappings"]
~~~

Những tình huống cần phân biệt:

- Consumer ở cùng namespace: có thể dùng hostname Service ngắn.
- Consumer khác namespace: cần hostname đầy đủ hoặc DNS phù hợp.
- Consumer chạy ngoài cluster: ClusterIP/Service DNS có thể không truy cập được; cần port-forward hoặc ingress/gateway có kiểm soát.
- Test qua HTTPS ingress: cần cấu hình scheme, certificate và URL tương ứng.

**Không hardcode Pod IP**, vì Pod có thể được tạo lại và địa chỉ thay đổi.

## 11. Reverse proxy và URL path prefix

Stub mapping của producer:

~~~text
GET /api/orders/ORD-1001
~~~

Một proxy của môi trường test lại công bố:

~~~text
https://stubs.test.internal/order-stub/api/orders/ORD-1001
~~~

Hai trường hợp:

1. Proxy **loại bỏ prefix `/order-stub`** khi forward; WireMock nhận `/api/orders/ORD-1001` và mapping có thể match.
2. Proxy giữ prefix; WireMock nhận `/order-stub/api/orders/ORD-1001`, dẫn tới unmatched request nếu không có mapping phù hợp.

Vì vậy, một URL có host/port đúng nhưng HTTP 404 chưa chắc là do contract. Cần kiểm tra **request thực đến WireMock** và cấu hình path rewriting của proxy.

Nếu prefix chỉ là cơ chế công bố stub cho CI, không nhất thiết nên thêm prefix đó vào HTTP contract của producer thật.

## 12. Readiness check cần gửi đúng request

Sau khi biết base URL, có thể kiểm tra bằng curl:

~~~bash
curl -i \
  -H "Accept: application/json" \
  "http://localhost:8090/api/orders/ORD-1001"
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"ORD-1001","status":"PAID"}
~~~

Một request khác:

~~~bash
curl -i "http://localhost:8090/api/orders/ORD-NOT-FOUND"
~~~

có thể nhận 404 nếu không có mapping. Tuy nhiên, đừng nhầm **WireMock unmatched 404** với **hợp đồng lỗi 404** có body/schema chính thức. Nếu cần response lỗi cụ thể, phải có scenario riêng.

### Chỉ thấy process sống chưa đủ

~~~mermaid
flowchart TD
    A["Start standalone runner"] --> B{"Process sống?"}
    B -->|Không| X["Kiểm tra log startup"]
    B -->|Có| C{"Stub artifact/version được tải?"}
    C -->|Không| Y["Kiểm tra Maven repository và classifier"]
    C -->|Có| D{"Stub listener đã mở?"}
    D -->|Không| Z["Kiểm tra port/binding"]
    D -->|Có| E{"Request hợp đồng trả đúng status/body?"}
    E -->|Không| U["Kiểm tra mapping, URL, headers"]
    E -->|Có| F["Chạy consumer integration tests"]
~~~

Readiness nên xác minh ít nhất một request có nghĩa; khi có nhiều dependency quan trọng, phải chờ readiness riêng của từng stub.

Tránh chỉ dùng `Thread.sleep(5000)` rồi coi mọi stub đã sẵn sàng. Thời gian tải artifact khác nhau giữa laptop và CI; hãy dùng polling theo điều kiện với timeout hữu hạn.

## 13. Không nhầm service discovery với base URL cố định

Một consumer có thể gọi bằng Feign:

~~~java
@FeignClient(name = "orders-api")
interface OrderClient {
    @GetMapping("/api/orders/{id}")
    OrderResponse getById(@PathVariable("id") String id);
}
~~~

Feign có thể hỏi Spring Cloud LoadBalancer/DiscoveryClient để tìm `orders-api` thay vì dùng URL trực tiếp. Khi Stub Runner Spring Cloud được tích hợp trong test context, có thể có cấu hình ánh xạ:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        ids-to-service-ids:
          order-service: orders-api
~~~

`order-service` ở đây là **artifact ID**, còn `orders-api` là **service ID**. Mapping giúp consumer discovery tìm đúng HTTP stub instance nếu các thành phần tích hợp hỗ trợ và đang hoạt động.

Điểm phân biệt:

- **Base URL trực tiếp**: HTTP client gọi `http://localhost:8090` hoặc URL được inject.
- **Service discovery**: client dùng service ID; load balancer cần một instance có host/port trỏ tới stub.
- **Standalone process từ xa**: không tự động đưa discovery registration vào một Spring test context chỉ bằng cách khởi động JAR.

Không áp dụng property `ids-to-service-ids` cho một standalone process rồi mặc định mọi Feign/WebClient bên ngoài sẽ tự tìm được stub. Đường đi tới discovery phải tồn tại thật.

## 14. HTTPS và mTLS khi công bố URL

Khi stub phục vụ HTTPS, URL đổi thành:

~~~text
https://localhost:<httpsPort>/api/orders/ORD-1001
~~~

Nhưng **đổi `http` thành `https` không tạo TLS listener**. Cần bảo đảm:

- WireMock hoặc proxy thật sự phục vụ HTTPS.
- Client dùng đúng HTTPS port.
- Certificate có SAN khớp hostname đang gọi.
- Client tin certificate/CA test qua truststore phù hợp.
- Hostname verification được bật.
- Với mTLS, server và client còn xác minh certificate của nhau.

Nếu WireMock chỉ mở HTTP `8090`, còn proxy mở HTTPS `8443`, bài test TLS xác minh đường **consumer → proxy**, không chứng minh bản thân WireMock đang sử dụng HTTPS.

Trong Docker, certificate cho `localhost` không tự hợp lệ với `order-stub`; SAN cần phản ánh hostname thực.

## 15. Chẩn đoán lỗi theo đúng lớp

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
| --- | --- | --- |
| `Connection refused` | Sai port, process chưa chạy hoặc listener không truy cập được | Xem bind address, Docker port mapping, log |
| Timeout | Mạng, firewall, service chưa sẵn sàng | Kiểm tra route, readiness, timeout |
| `UnknownHostException` | Hostname không phân giải được từ consumer | Kiểm tra DNS/network namespace |
| `SSLHandshakeException` | Sai HTTPS port, trust hoặc certificate | Kiểm tra TLS listener, SAN và truststore |
| HTTP 404 ở management port | Gọi nhầm runner control API | Gọi đúng stub server port |
| HTTP 404 ở stub port | Request không match mapping hoặc proxy rewrite sai | Kiểm tra method, path, headers và request journal |
| HTTP 200 nhưng sai payload | Artifact/scenario sai hoặc nhầm stub server | Kiểm tra GAV/classifier, mapping, base URL |
| Local PASS, Docker FAIL | `localhost` hoặc published/internal port bị nhầm | Kiểm tra client nằm ở host hay container |
| Consumer gọi staging | Property fallback/service discovery không được cách ly | Assert URI instance và cấu hình |
| Consumer CI PASS dù producer đổi API | Đang dùng stub artifact version cũ | Khóa artifact mới và chạy lại consumer tests |

Thứ tự điều tra hữu ích:

1. Stub artifact thực sự được tải chưa?
2. Stub HTTP listener có tồn tại và đang lắng nghe ở đâu?
3. Consumer chạy ở mạng nào và có đến được host/port đó không?
4. Scheme HTTP/HTTPS đúng không?
5. Đúng HTTP path, headers và body matcher không?
6. Consumer có assertion nghiệp vụ hay chỉ kiểm tra status 200?

## 16. An toàn khi mở stub cho ứng dụng gọi thử

Standalone stub có thể chứa dữ liệu tổng hợp, lỗi mẫu và management API. Các khuyến nghị:

- Chỉ mở port trong mạng nội bộ/CI khi có thể; không phơi management endpoint không cần thiết ra Internet.
- Không đưa email, mật khẩu, token hoặc dữ liệu production vào stub response/headers.
- Không ghi credential artifact repository vào cấu hình URL hoặc log.
- Giữ stub artifact có version cố định và metadata đủ truy vết.
- Không để các CI jobs dùng chung một runner mutable mà không có isolation.
- Dọn container/process sau test và tránh để port bị chiếm ở lần chạy tiếp theo.
- Nếu dùng TLS, cấu hình truststore/chứng chỉ test; không tắt TLS validation chỉ để có response 200.

URL nội bộ không tự động là bí mật, nhưng URL kèm token, địa chỉ quản lý, dữ liệu request hoặc metadata nhạy cảm có thể cần kiểm soát log/chia sẻ.

## 17. CI: công bố URL phải nối liền chuỗi bằng chứng

~~~mermaid
flowchart TD
    A["Review Groovy/YAML contract"] --> B["Sinh generated producer tests"]
    B --> C{"Producer tests thật sự PASS?"}
    C -->|Không| X["BLOCK"]
    C -->|Có| D["Sinh và publish stub artifact"]
    D --> E["Start standalone stub runner"]
    E --> F["Lấy host + stub HTTP port thật"]
    F --> G["Inject base URL vào consumer"]
    G --> H["Readiness check request hợp đồng"]
    H --> I{"HTTP response đúng?"}
    I -->|Không| X
    I -->|Có| J["Consumer integration tests"]
    J --> K{"Assertions PASS?"}
    K -->|Không| X
    K -->|Có| L["Lưu evidence và xét rollout"]
~~~

Biên bản CI minh họa:

~~~yaml
# Do dự án tự thiết kế, không phải output mặc định của SCC.
producer_revision: "order-service@abc123"
contracts_revision: "contracts@def456"
stub_artifact: "com.example.orders:order-service:1.4.2:stubs"
runner_mode: standalone
runner_management_port: 8750
stub_http_port: 8090
consumer_runtime: same-host
consumer_base_url: "http://localhost:8090"
stub_readiness: PASS
generated_producer_tests: PASS
consumer_stub_tests: PASS
~~~

Không chỉ ghi `stub_readiness: PASS` bằng tay. CI phải gọi request đúng method/path và kiểm tra response. Đồng thời, kết quả consumer PASS với **stub version 1.4.2** không chứng minh consumer tương thích với producer **1.5.0** nếu chưa dùng stub mới từ build đó.

## 18. Bài tập thực hành

### Bài tập A — Phân biệt management và stub port

Standalone runner mở management ở `8750`, Order stub ở `8090`. Checkout gọi `http://localhost:8750/api/orders/ORD-1001` và nhận 404.

**Yêu cầu:** xác định URL đúng và giải thích vì sao management port không phải HTTP stub port.

**Gợi ý:** nếu cùng máy, dùng `http://localhost:8090/api/orders/ORD-1001`.

### Bài tập B — Port động và cấu hình client

JUnit tạo `WireMockServer` bằng `dynamicPort()`; `application-test.yml` lại hardcode cổng `8090`.

**Yêu cầu:** đề xuất cách truyền port động trước khi client dùng URL.

**Gợi ý:** công bố URL qua `@DynamicPropertySource` hoặc lifecycle fixture phù hợp.

### Bài tập C — Docker networking

Container WireMock chạy ở 8090; Compose publish `18090:8090`. Một client chạy trên host, client khác nằm ở container Checkout.

**Yêu cầu:** đưa ra hai base URL.

**Gợi ý:** host dùng `http://localhost:18090`, Checkout container dùng `http://order-stub:8090`.

### Bài tập D — Readiness

Runner process hoạt động nhưng vẫn đang tải artifact từ Maven repository. Checkout test khởi chạy ngay và bị 404/Connection refused.

**Yêu cầu:** thiết kế readiness check trước consumer test.

**Gợi ý:** đợi stub trả đúng response cho một request hợp đồng, với timeout hữu hạn.

### Bài tập E — Reverse proxy

Proxy công bố `https://stubs.test.internal/order-stub/api/orders/ORD-1001`; WireMock chỉ biết mapping `/api/orders/ORD-1001`.

**Yêu cầu:** mô tả vì sao có thể 404 và cách xác minh path rewriting.

**Gợi ý:** proxy cần bỏ prefix `/order-stub` hoặc mapping phải được thiết kế cho path thực.

### Bài tập F — Stub cũ và breaking change

Order Service `1.5.0` đổi `status` thành `paymentStatus`, nhưng Checkout vẫn chạy qua standalone runner với artifact `1.4.2:stubs` và PASS.

**Yêu cầu:** có đủ bằng chứng tương thích ngược không?

**Gợi ý:** chưa. Cần producer tests và stub artifact `1.5.0` từ cùng contract revision, rồi chạy Checkout đang cần hỗ trợ với đúng artifact đó.

## 19. Checklist công bố cổng và URL

- [ ] Đã chọn đúng stub artifact `groupId:artifactId:version:classifier`.
- [ ] Stub JAR được tải thành công và có mappings của hợp đồng mong muốn.
- [ ] Phân biệt runner management port với stub HTTP port.
- [ ] URL dùng đúng **scheme://host:port** theo vị trí consumer.
- [ ] Cổng động được truyền vào consumer trước lúc test gọi.
- [ ] Với Docker, phân biệt internal port và published host port.
- [ ] `localhost` chỉ được dùng khi stub thực sự ở cùng network namespace với consumer.
- [ ] Với Kubernetes, dùng Service/Ingress routing thay vì hardcode Pod IP.
- [ ] Với proxy, path rewriting đã được kiểm chứng.
- [ ] Consumer client nhận base URL qua config, không bị khóa trong business code.
- [ ] Nếu dùng discovery, service ID và ServiceInstance trỏ đúng stub.
- [ ] Nếu dùng HTTPS, listener, truststore và hostname đúng; không dùng trust-all.
- [ ] Có readiness check bằng request hợp đồng, không chỉ xem PID hoặc management health.
- [ ] Có assertion cho response và logic consumer.
- [ ] Không gọi staging/production ngoài ý muốn trong consumer CI.
- [ ] CI kiểm chứng generated producer tests trước khi tin stub artifact.
- [ ] Consumer dùng stub artifact version đúng với producer build cần đánh giá.
- [ ] Port, artifact, contract revision và test reports được ghi lại để truy vết.
- [ ] Stub process/container được dọn và cô lập sau test.

**Ghi nhớ:** công bố standalone stub không đơn giản là “mở một cổng”. Phải biết **artifact nào đã được nạp**, **listener HTTP nào đang phục vụ mapping**, **host và port nào consumer thực sự truy cập được**, rồi truyền chính xác **base URL** vào client. Chỉ khi producer tests, stub readiness và consumer assertions cùng xác minh đúng revision/phiên bản, kết quả CI mới có ý nghĩa trong phát hiện API không tương thích.
