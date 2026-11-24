# Phản hồi chậm, lỗi mạng giả lập và phạm vi kiểm thử consumer

## Mục tiêu học tập

Trong chương **Trạng thái và lỗi** của **Spring Cloud Contract**, bạn đã thấy rằng một API không chỉ trả về phản hồi thành công. Ngoài mã lỗi HTTP như `400`, `404` hay `503`, consumer còn có thể gặp **phản hồi quá chậm**, **mất kết nối**, **reset TCP** hoặc **không nhận được phản hồi HTTP hoàn chỉnh**.

Spring Cloud Contract dùng **Groovy/YAML DSL** để mô tả những hành vi giao tiếp đã thống nhất; từ đó sinh **producer contract test** và **stub** để consumer dùng với **Stub Runner**. Tuy nhiên, cần xác định đúng **phạm vi bảo đảm**: kiểm thử hợp đồng HTTP và kiểm thử khả năng chống chịu lỗi mạng của consumer liên quan nhau nhưng không hoàn toàn giống nhau.

Sau bài học, bạn có thể:

- Phân biệt **HTTP error response**, **client-side timeout**, **connection failure** và **network fault**.
- Thiết kế contract cho các phản hồi lỗi HTTP mà consumer thực sự phụ thuộc.
- Dùng **WireMock** giả lập phản hồi chậm hoặc kết nối hỏng trong consumer test, không nhầm đó là kiểm thử producer thật.
- Thiết lập và kiểm tra timeout, retry, fallback và circuit breaker ở phạm vi phù hợp.
- Nhận diện trường hợp Stub Runner đủ dùng và trường hợp cần kiểm thử bổ sung.
- Xây dựng ma trận kiểm thử consumer có thể chạy ổn định trên CI và phát hiện thay đổi API không tương thích.

## 1. Tình huống thực tế: Checkout gọi Inventory

Giả sử:

- **Inventory Service** là **producer**, cung cấp `GET /api/inventory/{sku}`.
- **Checkout Service** là **consumer**, gọi endpoint này khi người dùng chuẩn bị xác nhận đơn.
- Khi Inventory hoạt động bình thường, API trả dữ liệu tồn kho bằng JSON.
- Khi Inventory quá tải, kết nối giữa hai dịch vụ có thể chậm hoặc bị ngắt.

Một tương tác thành công:

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

Checkout cần biết **khi nào có thể dựa vào kết quả tồn kho** và **khi nào nên dừng thao tác, hiển thị trạng thái chưa xác định hoặc thử lại**. Không được mặc định “không gọi được Inventory” đồng nghĩa với `available=false`: không có phản hồi không chứng minh hàng đã hết.

### Bốn nhóm kết quả cần tách biệt

| Nhóm | Ví dụ | Consumer nhận được HTTP status? | Ý nghĩa |
|---|---|---|---|
| Phản hồi hợp lệ | `200 OK` + JSON tồn kho | Có | Producer trả kết quả theo hợp đồng |
| HTTP error response | `404`, `429`, `503` + body/header theo API | **Có** | Server hoặc gateway đã gửi một HTTP response |
| Phản hồi quá chậm | Server trì hoãn 2 giây, client giới hạn 300 ms | Có thể **không** nếu client timeout trước | Client tự dừng chờ; server có thể vẫn đang xử lý |
| Lỗi kết nối/truyền tải | Connection refused, reset, DNS/TLS failure | Thường **không** có response HTTP hợp lệ | Lỗi xảy ra trước hoặc trong khi trao đổi dữ liệu |

Một điểm quan trọng: **HTTP `408 Request Timeout` hoặc `504 Gateway Timeout` là các HTTP status được một thành phần trả về**. Chúng **không đồng nhất** với exception timeout do chính HTTP client tạo ra. Muốn test logic xử lý `504`, stub có thể trả `504`; muốn test client hết thời gian chờ, phải tạo độ trễ hoặc điều kiện tương ứng khiến timeout xảy ra.

## 2. Phân biệt lỗi giao thức và lỗi mạng

Hãy trả lời: *consumer đã nhận được một response HTTP hoàn chỉnh hay chưa?*

~~~mermaid
flowchart TD
    A["Consumer gọi producer"] --> B{"Đã có response HTTP hoàn chỉnh?"}
    B -->|Có| C{"Status là gì?"}
    C -->|2xx| D["Xử lý thành công theo contract"]
    C -->|4xx| E["Xử lý lỗi yêu cầu/trạng thái tài nguyên"]
    C -->|5xx| F["Xử lý lỗi phía server/gateway theo chính sách"]
    B -->|Chưa| G{"Điều gì xảy ra?"}
    G -->|Hết thời gian chờ| H["Client-side timeout"]
    G -->|Không kết nối được| I["Connect/DNS/TLS failure"]
    G -->|Kết nối bị ngắt| J["Reset / incomplete response"]
~~~

### HTTP error response

Producer có thể chủ động công bố:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 2

{
  "code": "INVENTORY_TEMPORARILY_UNAVAILABLE",
  "message": "Inventory is temporarily unavailable"
}
~~~

Consumer nhận được **status, header, body**. Đây là hành vi có thể viết rõ trong Spring Cloud Contract để generated producer test kiểm chứng và Stub Runner mô phỏng.

`Retry-After: 2` trong ví dụ gợi ý chờ 2 giây trước khi gửi lại. Header này có thể dùng số giây hoặc ngày HTTP theo giao thức; việc có retry hay không, số lần tối đa và tổng ngân sách thời gian vẫn do consumer và chính sách ứng dụng quyết định.

### Client-side timeout

Producer phản hồi thành công sau 1.500 ms, nhưng consumer chỉ cho phép một request kéo dài 250 ms. Trong trường hợp đó, **consumer có thể ném timeout exception trước khi response đến**. Test không nên đòi có status `200` hay `503` vì chưa chắc client đã nhận được response HTTP.

### Lỗi kết nối

**Connection refused** thường xảy ra khi chưa có tiến trình lắng nghe tại địa chỉ/cổng. **Connection reset** thường xảy ra sau khi kết nối được thiết lập nhưng bị đóng đột ngột; lỗi có thể xuất hiện giữa lúc gửi request hoặc đọc response. DNS/TLS failure lại là các giai đoạn khác.

Không nên bắt mọi exception thành “dịch vụ trả 503”. Cách chuẩn hóa lỗi ở tầng ứng dụng có thể gom chúng vào một loại lỗi ngoại vi, nhưng log/telemetry và chính sách retry cần giữ thông tin nguyên nhân.

## 3. Phân biệt các loại timeout trong consumer

| Loại timeout | Giới hạn điều gì? | Cách kiểm thử phù hợp |
|---|---|---|
| **Connection timeout** | Thời gian thiết lập kết nối TCP (và cấu hình tương ứng của client) | Điều kiện mạng/đích không thể kết nối; không dùng chỉ một server `fixedDelay` để suy ra connect timeout |
| **Response/read timeout** | Thời gian chờ dữ liệu hoặc đọc giữa các lần nhận dữ liệu, tùy thư viện HTTP | WireMock trì hoãn phản hồi, hoặc tình huống đọc dữ liệu chậm |
| **Request/overall timeout** | Tổng ngân sách cho một request hoặc một chuỗi thao tác theo client | Cấu hình timeout tổng và giả lập thao tác kéo dài |
| **Circuit-breaker time limiter** | Giới hạn thời gian của lời gọi được bảo vệ ở tầng ứng dụng | Test cấu hình giới hạn và trạng thái cancellation/fallback |

Các thư viện Java khác nhau có cách tính read timeout và tổng thời gian khác nhau. Ví dụ `HttpClient`, `RestClient`, `WebClient`, Feign và các HTTP client bên dưới có API cấu hình riêng. **Không gọi mọi timeout là “read timeout”** khi chưa kiểm tra timeout nào thực sự được cấu hình.

Giả sử Checkout có ngân sách tổng 800 ms để phản hồi người dùng. Nếu mỗi attempt có timeout 700 ms và chính sách retry thêm ba lần với backoff, tổng thời gian có thể vượt xa 800 ms. Vì vậy cần thiết kế **ngân sách đầu-cuối**, không chỉ cấu hình từng timeout độc lập.

> Cần phân biệt “người gọi ngừng chờ” với “producer đã hủy xử lý”. Client timeout **không chứng minh** server đã dừng công việc. Với thao tác có tác dụng phụ, retry thiếu idempotency có thể tạo giao dịch trùng.

## 4. Hợp đồng Spring Cloud Contract cho HTTP 503

Giả sử Inventory có hành vi được **hai nhóm thực sự thống nhất**: khi không thể phục vụ tạm thời, API trả `503`, mã lỗi ổn định và một header `Retry-After`.

Trong dự án producer đã cấu hình Spring Cloud Contract, có thể viết `src/test/resources/contracts/inventory/serviceUnavailable.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Inventory tam thoi khong the phuc vu'

    request {
        method 'GET'
        url '/api/inventory/SKU-UNAVAILABLE'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 503
        headers {
            contentType(applicationJson())
            header('Retry-After', '2')
        }
        body(
            code: 'INVENTORY_TEMPORARILY_UNAVAILABLE',
            message: 'Inventory is temporarily unavailable'
        )
    }
}
~~~

Ý nghĩa:

- `request` mô tả tình huống cần nhận diện.
- `response.status 503` là **HTTP error status**, không phải một network exception.
- `Retry-After` là header mà producer cam kết ở tình huống này.
- `code` là mã máy đọc được để consumer phân nhánh; `message` chỉ nên được ràng buộc nguyên văn nếu API có cam kết như vậy.

**Lưu ý khi chạy producer test:** `SKU-UNAVAILABLE` chỉ là khóa tình huống minh họa. Producer test phải **sắp đặt trạng thái lỗi** cho nhánh này, bằng fake dependency, trạng thái test hoặc cơ chế mô phỏng được kiểm soát. Không nên đưa “nếu SKU có tên UNAVAILABLE thì trả 503” vào nghiệp vụ production chỉ để test dễ dàng.

### YAML DSL tương đương

Có thể chọn YAML thay cho Groovy, ví dụ `serviceUnavailable.yml`:

~~~yaml
description: 'Inventory tam thoi khong the phuc vu'
request:
  method: GET
  url: '/api/inventory/SKU-UNAVAILABLE'
  headers:
    Accept: 'application/json'
response:
  status: 503
  headers:
    Content-Type: 'application/json'
    Retry-After: '2'
  body:
    code: 'INVENTORY_TEMPORARILY_UNAVAILABLE'
    message: 'Inventory is temporarily unavailable'
~~~

Ở YAML, quote `'2'` để thể hiện giá trị **header dạng văn bản**. Đây là **một cách viết thay thế**, không cần đặt cả hai file trong cùng build cho cùng tình huống nếu chúng sẽ tạo mapping trùng nhau.

Contract này phù hợp để kiểm chứng **producer có trả đúng 503/header/body khi tình huống lỗi được tạo ra hay không**, và để consumer thử logic xử lý **503**. Nó **chưa kiểm chứng** kết nối bị reset, server im lặng hoặc consumer timeout.

## 5. Stub Runner: kiểm tra consumer xử lý HTTP error response

Trong pipeline thông thường của Spring Cloud Contract:

1. Producer giữ Groovy/YAML DSL và chạy các **generated contract tests**.
2. Khi producer test thành công, build tạo/phát hành **stub artifact**.
3. Consumer dùng **Spring Cloud Contract Stub Runner** chạy stub đúng version.
4. Consumer test gọi **HTTP client thật của ứng dụng** đang trỏ tới cổng stub và kiểm tra hành vi.

Ví dụ skeleton cho consumer dùng Spring Boot và JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(properties = {
    "inventory.base-url=http://localhost:10000"
})
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:10000",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryUnavailableConsumerTest {

    @Test
    void handlesHttp503WithoutTreatingItAsOutOfStock() {
        // Gọi InventoryClient/Gateway thật của Checkout.
        // Yêu cầu tới /api/inventory/SKU-UNAVAILABLE.
        // Assert ứng dụng báo "chưa thể xác minh tồn kho",
        // không tự gán available=false như thể đã hết hàng.
        // Nếu client đọc Retry-After, assert chính sách liên quan.
    }
}
~~~

Đây là **skeleton minh họa**: lớp client, cơ chế inject, assertion và thuộc tính `inventory.base-url` phải được điều chỉnh theo mã ứng dụng thực. Ví dụ dùng chế độ `LOCAL` nên artifact `com.example:inventory-producer:1.0.0:stubs` cần có trong Maven local repository của môi trường test. Trong CI có thể dùng repository được cấu hình phù hợp, thay vì giả định cache local luôn sẵn.

Khi chạy consumer test với stub `503`, cần xác nhận:

- Client **không** coi HTTP response là thành công chỉ vì server có trả body JSON.
- Chính sách phân loại `503` khác `404` và `400`.
- UI hoặc workflow không đưa ra kết luận sai như “hết hàng” khi dữ liệu tồn kho chưa được xác nhận.
- Nếu có retry, hành vi tuân theo chính sách đã thiết kế (giới hạn lần, backoff, tổng ngân sách thời gian).
- Các header hoặc mã lỗi mà consumer thực sự dựa vào được giữ đúng.

**Không dùng consumer test với Stub Runner để thay thế generated producer tests.** Stub có thể trả response theo DSL ngay cả khi code producer thật chưa triển khai đúng.

## 6. Vì sao lỗi mạng không chỉ là một HTTP contract?

Spring Cloud Contract mạnh ở **giao diện có thể mô tả bằng request và response**, gồm status, header, body và matcher. Lỗi ở tầng TCP, DNS, TLS hoặc việc client tự kết thúc do timeout có thể **không tạo thành một HTTP response hoàn chỉnh**.

Ví dụ:

| Tình huống | Có thể biểu diễn như phản hồi HTTP thông thường? | Gợi ý kiểm thử |
|---|---|---|
| Producer trả `503` kèm JSON | Có | Spring Cloud Contract DSL + Stub Runner |
| Gateway trả `504` | Có nếu đó là phản hồi đã công bố tại ranh giới consumer | Stub HTTP trả `504`, kiểm tra logic consumer |
| Server chờ rất lâu rồi trả `200` | Có response, nhưng **độ trễ** là hành vi bổ sung | WireMock fixed delay và timeout client |
| Kết nối TCP bị reset trước response | Không có HTTP response hợp lệ để viết như status/body bình thường | WireMock fault injection hoặc test transport |
| DNS không phân giải được | Không | Môi trường test mạng/fake transport phù hợp |
| TLS handshake lỗi | Không | Test tích hợp với cấu hình TLS cụ thể |
| Client từ chối gọi vì circuit breaker mở | Không có lời gọi HTTP tới producer | Test resilience ở tầng ứng dụng |

**Nguyên tắc thực hành:** dùng contract để bảo vệ hành vi HTTP được cam kết; dùng **fault-injection tests** để bảo vệ cách consumer đối mặt với lỗi vận hành. Hai nhóm test có mục đích khác nhau nhưng cần bổ sung cho nhau.

Không nên tự cho rằng một file Groovy/YAML contract chứa `status: 503` sẽ tạo ra network timeout. Cũng không nên giả định mọi tùy chọn **WireMock** đều được Spring Cloud Contract DSL chuyển nguyên vẹn sang stub mapping; cần kiểm tra hỗ trợ của phiên bản và **mapping thực tế được sinh**.

## 7. Dùng WireMock giả lập phản hồi chậm

**WireMock** là công cụ HTTP stubbing được sử dụng trong hệ sinh thái Spring Cloud Contract. Ngoài response status/body, WireMock có thể giả lập **độ trễ** để kiểm tra timeout của consumer.

### Mapping JSON: fixed delay

Ví dụ ánh xạ minh họa cho request `GET /api/inventory/SKU-SLOW`:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-SLOW"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "sku": "SKU-SLOW",
      "available": true,
      "quantity": 8
    },
    "fixedDelayMilliseconds": 1500
  }
}
~~~

`fixedDelayMilliseconds: 1500` yêu cầu WireMock **trì hoãn trả response khoảng 1.500 ms**. Nếu consumer có tổng thời gian chờ request 200 ms, test có thể kiểm tra nhánh timeout.

Đây là **WireMock mapping tự viết để minh họa fault/latency testing**, không phải khẳng định Spring Cloud Contract tự sinh trường delay đó từ Groovy/YAML DSL chuẩn. Bạn có thể dùng một WireMock server test riêng, hoặc một cơ chế đưa mapping bổ sung vào stub test **nếu** dự án hỗ trợ và không làm mapping xung đột.

### Ví dụ Java với WireMockServer

Giả sử consumer test đã có dependency WireMock tương thích với Spring Boot và Java đang dùng. Ví dụ này dùng JUnit 5 và JDK `HttpClient` để chứng minh một HTTP request có thể hết thời gian chờ trước response:

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InventoryTimeoutTransportTest {

    private WireMockServer wireMock;

    @BeforeEach
    void startServer() {
        wireMock = new WireMockServer(options().dynamicPort());
        wireMock.start();
    }

    @AfterEach
    void stopServer() {
        if (wireMock != null) {
            wireMock.stop();
        }
    }

    @Test
    void clientTimesOutBeforeSlowResponse() {
        wireMock.stubFor(get(urlEqualTo("/api/inventory/SKU-SLOW"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("{\"sku\":\"SKU-SLOW\",\"available\":true,\"quantity\":8}")
                .withFixedDelay(1500)));

        HttpClient httpClient = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(wireMock.baseUrl() + "/api/inventory/SKU-SLOW"))
            .timeout(Duration.ofMillis(200))
            .GET()
            .build();

        assertThrows(HttpTimeoutException.class, () ->
            httpClient.send(request, HttpResponse.BodyHandlers.ofString()));
    }
}
~~~

**Đây là test minh họa transport timeout của JDK HttpClient**, không phải kiểm thử đầy đủ logic Checkout. Trong dự án, hãy cấu hình **InventoryClient thực** trỏ đến `wireMock.baseUrl()` rồi assert kết quả từ lớp ứng dụng: trả trạng thái không xác định, hiển thị thông báo phù hợp, ngừng quy trình hoặc kích hoạt fallback đúng chính sách.

Khi một test kiểm tra thời gian thực, hệ điều hành/CI có thể có độ trễ lập lịch. Chọn khoảng cách đủ lớn giữa timeout và fake delay, không viết assertion đo chính xác số millisecond; các phép thử rất nhạy thời gian nên được thiết kế để giảm flaky test. Với retry/backoff, ưu tiên virtual clock hoặc scheduler điều khiển được khi công nghệ cho phép.

### Delay không mô phỏng được mọi lỗi

WireMock `fixedDelayMilliseconds` phù hợp để thử **client chờ response quá lâu**. Nó **không tự mô phỏng connection timeout**, vì server WireMock vẫn đang lắng nghe và có thể thiết lập kết nối ngay. Muốn thử connect timeout, cần điều kiện mạng/transport tương ứng (ví dụ proxy, mạng giả lập hoặc fake connector), không dùng kết quả của fixed delay để kết luận chính sách connect timeout đã được kiểm thử.

## 8. Dùng WireMock giả lập reset kết nối

WireMock có cơ chế **fault injection** để tạo những sự cố không phải HTTP response bình thường. Ví dụ mapping minh họa:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-RESET"
  },
  "response": {
    "fault": "CONNECTION_RESET_BY_PEER"
  }
}
~~~

Khi consumer gọi endpoint tương ứng, WireMock cố mô phỏng tình huống **peer reset connection**. Tùy HTTP client, hệ điều hành và giao thức, test có thể quan sát lỗi `IOException`, lỗi I/O cụ thể hoặc exception được client library bọc lại. **Không giả định mọi client luôn ném cùng một class exception hay message.**

Nếu dùng WireMock Java DSL, có thể cấu hình:

~~~java
wireMock.stubFor(get(urlEqualTo("/api/inventory/SKU-RESET"))
    .willReturn(aResponse()
        .withFault(Fault.CONNECTION_RESET_BY_PEER)));
~~~

`Fault` trong ví dụ thuộc `com.github.tomakehurst.wiremock.http.Fault`. Test thực tế nên assert **hành vi ứng dụng** (ví dụ trạng thái “không thể xác minh tồn kho”) thay vì so khớp nguyên văn thông điệp lỗi I/O của JDK.

### Những lỗi WireMock khác

Các chế độ lỗi thường được dùng trong WireMock gồm:

| Fault | Ý nghĩa mô phỏng | Lưu ý |
|---|---|---|
| `CONNECTION_RESET_BY_PEER` | Kết nối bị reset | Exception cụ thể tùy client/OS |
| `EMPTY_RESPONSE` | Peer đóng kết nối mà không trả HTTP response bình thường | Không đồng nghĩa với HTTP `204 No Content` |
| `MALFORMED_RESPONSE_CHUNK` | Dữ liệu phản hồi bị hỏng ở dạng chunked | Có thể ảnh hưởng cách parser HTTP xử lý |
| `RANDOM_DATA_THEN_CLOSE` | Gửi dữ liệu không phải response HTTP hợp lệ rồi đóng kết nối | Kiểm tra lỗi protocol/transport |

Không cần đưa cả bốn fault vào mọi test suite. Chọn lỗi có khả năng xảy ra ở kiến trúc của mình và có **hành vi consumer khác nhau cần bảo vệ**.

Phản hồi `EMPTY_RESPONSE` hoặc reset kết nối **không giống** `HTTP 200` với body rỗng `""`, `HTTP 204`, hay `HTTP 503`. Nếu consumer code gộp tất cả vào một nhánh, cần đảm bảo đó là quyết định nghiệp vụ có chủ đích.

## 9. Phạm vi của consumer test: nên kiểm tra gì?

Kiểm thử consumer cần xác nhận **client và logic ứng dụng của chính consumer** khi phụ thuộc bên ngoài hoạt động bình thường hoặc thất bại.

| Hành vi cần kiểm tra | Loại phép thử phù hợp | Assertion trọng tâm |
|---|---|---|
| Deserialize response `200` theo contract | Stub Runner với stub được sinh | Đọc `sku`, `available`, `quantity` đúng kiểu và ngữ nghĩa |
| Xử lý `400`/`404`/`503` cùng error body | Stub Runner với các contract lỗi | Phân nhánh đúng status, error code, header |
| Timeout khi server phản hồi chậm | WireMock delay hoặc fake transport | Consumer dừng chờ đúng chính sách, không hiểu nhầm là `available=false` |
| Connection reset/empty response | WireMock fault | Consumer phục hồi/hiển thị lỗi đúng; không giả nhận có response |
| Retry/backoff | Fault stub có kịch bản theo số lần gọi, fake clock nếu được | Số lần thử có giới hạn, không nhân đôi tác dụng phụ |
| Circuit breaker mở sau một số lỗi | Test resilience với dependency giả và clock có thể kiểm soát | Sau ngưỡng, lời gọi tiếp theo không đi qua network |
| Tác động người dùng | Service/controller/UI test | Thông báo rõ “chưa thể kiểm tra tồn kho”, không đưa ra kết luận sai |
| Producer thật trả đúng `503` | Generated producer contract test | Status/header/body ở producer phù hợp contract |
| DNS/TLS, proxy, service mesh | Integration/network test | Hành vi với hạ tầng mạng thật hoặc mô phỏng phù hợp |

**Phạm vi không gồm** việc chứng minh producer triển khai đúng từ đầu đến cuối chỉ bằng consumer test: khi consumer test dùng stub, nó chưa hề gọi producer thật. Tương tự, test với WireMock không thể chứng minh mạng production không gặp lỗi.

### Ví dụ hành vi Checkout khi mất Inventory

Giả sử Checkout có ba trạng thái:

- `IN_STOCK`: API trả `200` và `available=true`.
- `OUT_OF_STOCK`: API trả `200` và `available=false`.
- `UNKNOWN`: timeout, reset hoặc lỗi hạ tầng khiến không xác minh được tồn kho.

Một fallback an toàn đối với UI có thể hiển thị “Chưa thể kiểm tra tồn kho, vui lòng thử lại” cho `UNKNOWN`, thay vì tự suy thành `OUT_OF_STOCK`. Tùy nghiệp vụ, bước thanh toán có thể bị chặn cho đến khi xác nhận lại. Đây là **quyết định nghiệp vụ minh họa**, cần được thống nhất với chủ sở hữu sản phẩm.

## 10. Retry, backoff, idempotency và circuit breaker

### Retry phải có giới hạn

Không phải lỗi nào cũng nên tự động retry:

| Trường hợp | Gợi ý quyết định |
|---|---|
| `400 Bad Request` do dữ liệu sai | Thường không retry nguyên request chưa sửa |
| `404 Not Found` cho tài nguyên không tồn tại | Thường không retry vô hạn; xem chính sách eventual consistency nếu có |
| `429 Too Many Requests` | Có thể thử lại theo `Retry-After` và chính sách giới hạn |
| `503 Service Unavailable` | Có thể retry có kiểm soát, ưu tiên backoff/jitter |
| Client timeout khi `GET` | Có thể retry nếu còn ngân sách và request idempotent |
| Timeout khi `POST` tạo giao dịch | **Nguy cơ nhân đôi tác dụng phụ**; cần idempotency key/cơ chế chống trùng hoặc quy trình xác minh kết quả |
| Connection reset | Kết quả thao tác trước khi reset có thể chưa rõ | Không tự coi thao tác chắc chắn chưa thực hiện |

### Idempotency quan trọng hơn số lần retry

Giả sử Checkout gọi `POST /api/reservations` để giữ hàng, server **đã ghi thành công** nhưng kết nối bị reset trước khi consumer nhận response. Nếu consumer retry không có cơ chế nhận diện yêu cầu trùng, hệ thống có thể giữ hàng hai lần.

Với thao tác có tác dụng phụ, cân nhắc **idempotency key** được producer công bố và xử lý, hoặc một cơ chế truy vấn lại trạng thái. Hợp đồng có thể mô tả header/body và response cho key trùng; nhưng kiểm thử tính idempotent đầy đủ thường cần test trạng thái nghiệp vụ nhiều lần gọi, không chỉ một contract request/response đơn lẻ.

### Circuit breaker

Circuit breaker có thể mở sau một số lần thất bại và tạm thời ngừng gọi dependency. Consumer test nên phân biệt:

1. Khi breaker **closed**, request đi ra ngoài.
2. Sau lỗi đạt điều kiện, breaker chuyển **open**.
3. Khi **open**, gọi tiếp có thể bị từ chối ngay, **không có HTTP request tới stub**.
4. Khi đi vào pha phục hồi theo cấu hình, các lời gọi thử được kiểm soát.

Kiểm thử state machine của circuit breaker phụ thuộc thư viện resilience (chẳng hạn Resilience4j) và cấu hình thực tế. Không nên suy rằng Spring Cloud Contract hoặc Stub Runner tự cung cấp toàn bộ logic breaker; chúng chủ yếu là công cụ kiểm chứng giao tiếp.

## 11. Thiết kế test ổn định, tránh “flaky” trên CI

### Ma trận tình huống khuyến nghị

| ID | Cách tạo tình huống | Kỳ vọng consumer | Công cụ |
|---|---|---|---|
| `OK` | `200` + JSON hợp lệ | Xử lý tồn kho đúng | Spring Cloud Contract stub |
| `NOT_FOUND` | `404` + mã lỗi | Phân biệt SKU không tồn tại | Spring Cloud Contract stub |
| `UNAVAILABLE` | `503` + mã lỗi, `Retry-After` nếu cam kết | Báo tạm unavailable, retry theo chính sách | Spring Cloud Contract stub |
| `SLOW` | `200` được trì hoãn hơn timeout client | Chuyển nhánh timeout, không kết luận hết hàng | WireMock delay |
| `RESET` | TCP reset | Nhánh lỗi kết nối/fallback | WireMock fault |
| `EMPTY_RESPONSE` | Đóng kết nối không có response HTTP | Không hiểu nhầm thành HTTP 204 | WireMock fault |
| `RETRY_BOUND` | Trả lỗi rồi thành công theo kịch bản có giới hạn | Đúng số lần thử và thời gian chờ | Stub có trạng thái/fake dependency |
| `BREAKER_OPEN` | Kích hoạt circuit breaker | Không gửi request khi breaker mở | Test resilience ở tầng ứng dụng |

Đây là **ma trận gợi ý**, không phải yêu cầu mọi dự án phải triển khai nguyên bộ. Chọn tập có giá trị theo luồng nghiệp vụ và rủi ro thực tế.

### Những nguyên tắc giảm flaky

1. Dùng **cổng động** cho WireMock nếu nhiều test chạy song song; không tranh chấp cổng cố định.
2. Dùng request path/header/body **phân biệt rõ** giữa các mapping; tránh hai mapping cùng match một request nhưng trả kết quả khác.
3. Với bài test timeout, đặt **delay lớn hơn timeout đủ rõ rệt**, nhưng giữ tổng thời lượng CI hợp lý.
4. Với retry/backoff, dùng **fake clock**, virtual scheduler hoặc công cụ kiểm soát thời gian khi thư viện cho phép, thay vì `Thread.sleep` quá nhiều.
5. Reset mapping và request journal/stub state giữa các test nếu chúng có thể ảnh hưởng nhau.
6. Dùng **phiên bản stub được ghim**, không vô tình lấy artifact cũ từ local Maven cache hoặc nhãn `latest`.
7. Test hành vi ứng dụng và loại lỗi ổn định, không so khớp nguyên văn exception message của từng hệ điều hành.
8. Không khẳng định ngưỡng timeout đúng đến từng millisecond trên môi trường CI chia sẻ tài nguyên.

### Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Test chờ chậm nhưng vẫn nhận `200` | Timeout client chưa được cấu hình hoặc đang quá dài | Xem timeout thực của HTTP client, không chỉ config ứng dụng |
| Test “connection timeout” lại chỉ chờ server phản hồi | Dùng `fixedDelay` sau khi kết nối đã thành công | Tạo tình huống connect failure phù hợp |
| Consumer nhận `404` từ WireMock dù dự kiến `503` | Request không match mapping hoặc sai stub version | Xem log unmatched request và mapping được tải |
| Test reset thỉnh thoảng ra exception khác | OS/client/JDK xử lý TCP khác nhau | Assert hành vi application, không khóa message |
| Retry tạo nhiều reservation | POST không có idempotency | Bổ sung bảo vệ request trùng và test trạng thái |
| CI xanh dù producer đã đổi body lỗi | Consumer đang chạy stub cũ | Ghi rõ version/commit của artifact stub |
| Test 503 xanh nhưng khi mất mạng consumer vẫn lỗi | HTTP error khác network exception | Bổ sung fault test riêng |

## 12. Bài thực hành: chọn phép thử đúng cho yêu cầu

### Đề bài

Checkout có cấu hình tổng thời gian chờ cho việc gọi Inventory là **400 ms**. Nhóm sản phẩm đưa ra ba yêu cầu:

1. Nếu Inventory trả `503` kèm `code=INVENTORY_TEMPORARILY_UNAVAILABLE` thì Checkout hiển thị “Kho tạm bận”.
2. Nếu Inventory phản hồi `200` sau **1.200 ms**, Checkout phải bỏ chờ và hiển thị “Chưa thể xác minh”.
3. Nếu TCP bị reset, Checkout không được hiểu như hàng đã hết và không được lặp vô hạn.

Một đồng nghiệp chỉ viết contract:

~~~yaml
description: 'Inventory unavailable'
request:
  method: GET
  url: '/api/inventory/SKU-UNAVAILABLE'
response:
  status: 503
  headers:
    Content-Type: 'application/json'
  body:
    code: 'INVENTORY_TEMPORARILY_UNAVAILABLE'
~~~

Hãy trả lời:

**Câu 1. Contract trên bảo vệ yêu cầu nào?**

Nó mô tả **HTTP `503`** và mã lỗi, nên là nền tảng cho yêu cầu (1) khi generated producer test và consumer test tương ứng được chạy. Nó **không** tự tạo server chậm hoặc reset TCP.

**Câu 2. Dùng công cụ nào cho yêu cầu (2)?**

Dùng WireMock với `fixedDelayMilliseconds` đủ lớn so với 400 ms, hoặc fake transport phù hợp. Client thực của Checkout phải được cấu hình timeout; assert nhánh `UNKNOWN`/“Chưa thể xác minh”, không đo thời lượng tuyệt đối cứng nhắc trên CI.

**Câu 3. Dùng công cụ nào cho yêu cầu (3)?**

Dùng WireMock `CONNECTION_RESET_BY_PEER` hoặc công cụ mô phỏng transport tương đương. Assert fallback đúng và số lần retry có giới hạn; không phụ thuộc vào tên exception cụ thể của một phiên bản HTTP client.

**Câu 4. Nếu endpoint chuyển thành `POST /api/reservations` có tác dụng phụ, điều gì thay đổi?**

Phải cân nhắc idempotency, nguy cơ server đã xử lý dù client không nhận response, và quy tắc chống thao tác trùng. Không áp dụng máy móc retry của `GET` cho `POST`.

**Câu 5. Vì sao test với Stub Runner cho `503` vẫn cần producer test?**

Vì Stub Runner dùng **stub mô phỏng** theo contract; nó không xác nhận code producer thật có trả đúng `503`, header và body trong điều kiện lỗi đã thiết kế. Generated producer tests kiểm chứng phần đó.

### Câu hỏi tự kiểm tra

- Sự khác biệt giữa HTTP `504` và timeout do client tự kích hoạt là gì?
- Vì sao `fixedDelayMilliseconds` không kiểm tra connect timeout?
- `EMPTY_RESPONSE` khác `204 No Content` thế nào?
- Khi mất kết nối trong lúc `POST`, vì sao không thể luôn biết giao dịch đã thành công hay chưa?
- Một consumer test dùng Stub Runner có kiểm chứng được logic retry/circuit breaker không? Cần bố trí stub và thời gian ra sao?
- Vì sao build producer và consumer đều xanh vẫn chưa đủ nếu chúng dùng hai revision contract/stub khác nhau?

## 13. Ghi nhớ

**Đừng gộp phản hồi lỗi HTTP với lỗi mạng.** Với Spring Cloud Contract, hãy dùng Groovy/YAML DSL để định nghĩa status/header/body mà producer cam kết, sinh generated producer tests và phát hành stub cho consumer thử với Stub Runner. Khi cần kiểm tra consumer trong điều kiện **phản hồi chậm, kết nối reset, timeout, retry hoặc circuit breaker**, bổ sung WireMock fault/delay tests hoặc công cụ resilience phù hợp.

Một bộ kiểm thử đáng tin cậy cần xác nhận **hành vi của consumer khi không có thông tin chắc chắn**, không tự biến timeout thành “hết hàng”, đồng thời quản lý version stub và kiểm tra hai phía trên CI. Contract test bảo vệ giao diện đã mô tả; fault-injection và integration tests bảo vệ những giới hạn vận hành mà contract đơn lẻ chưa bao phủ.
