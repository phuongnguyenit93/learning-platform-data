# Xác minh số lần gọi và request thực tế đã nhận

**WireMock** không chỉ trả phản hồi giả cho HTTP request; nó còn có thể **ghi nhận những request đã tới stub server** và cho phép kiểm chứng **số lần gọi, đường dẫn, phương thức, headers, query parameters và body**. Đây là khả năng quan trọng khi dùng **Spring Cloud Contract**: consumer test không chỉ chứng minh “đọc được phản hồi mẫu” mà còn có thể kiểm tra mã HTTP client **thực sự gửi gì và gửi bao nhiêu lần**.

Bài thuộc chương **WireMock** của mô-đun **SPRING_CLOUD_CONTRACT**. Mô-đun hướng dẫn định nghĩa hợp đồng giữa producer và consumer bằng **Groovy/YAML DSL**, sinh producer verification tests, đóng gói stub, dùng **Stub Runner** và tích hợp CI để phát hiện thay đổi API không tương thích. Ở đây, ta tập trung vào **request journal (nhật ký request)**, các API `verify(...)` và `findAll(...)`, WireMock Admin API và việc kết hợp chúng với Stub Runner. Chúng ta cũng làm rõ các giới hạn: “stub đã nhận request” **không đồng nghĩa** “producer thật đã thực thi request”, và một phản hồi 404 có thể chỉ là dấu hiệu **không có mapping phù hợp**.

## 1. Ba câu hỏi cần phân biệt

Giả sử **Billing Service** (consumer) gọi **Order Service** (producer) để đọc đơn hàng 42. Producer công bố hợp đồng:

~~~http
GET /api/orders/42
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

Trong consumer test, cần phân biệt ba tầng kiểm:

| Câu hỏi | Cách quan sát | Ý nghĩa |
| --- | --- | --- |
| **Stub trả gì?** | Assert status, headers và body nhận được từ OrderClient. | Consumer giải mã và xử lý phản hồi hợp đồng. |
| **Stub đã nhận gì?** | Xem WireMock request journal, `verify`, `findAll`. | Consumer thực sự gửi request nào, bao nhiêu lần. |
| **Producer thật có đúng hợp đồng không?** | Generated producer tests của Spring Cloud Contract trên Order Service. | Implementation producer thực đáp ứng request/response được công bố. |

Một consumer test chỉ assert `status=PAID` có thể bỏ sót việc client **gọi hai lần thay vì một lần**. Ngược lại, một test chỉ xác minh WireMock nhận đúng một `GET` chưa chứng minh client đã xử lý JSON đúng. Để bảo vệ tích hợp, thường cần **cả assertions trên phản hồi lẫn request journal**.

~~~mermaid
flowchart TD
    A["Hợp đồng Groovy/YAML"] --> B["Producer verification tests"]
    B --> C["Producer thật được xác minh"]
    A --> D["Đóng gói HTTP stub mappings"]
    D --> E["Stub Runner / WireMock"]
    F["Consumer HTTP client"] -->|Request thật của client| E
    E -->|Response mẫu| F
    E --> G["Request journal"]
    G --> H["verify count, method, URL, headers, body"]
    F --> I["Assertion response và xử lý nghiệp vụ"]
~~~

**Lưu ý phạm vi:** thông tin trong request journal là những gì **WireMock server đã nhìn thấy**, không phải log request nội bộ của producer. Nó giúp phát hiện lỗi trong mã consumer, nhưng không thay thế generated producer tests.

## 2. Request matching khác request verification

WireMock có hai công việc gần nhau nhưng không giống nhau:

1. **Stub matching:** khi HTTP request đến, WireMock tìm một mapping phù hợp để quyết định response nào cần trả.
2. **Request verification:** sau khi consumer code đã chạy, bài test truy vấn nhật ký request để xác minh **số lượng** và **nội dung** những request đã nhận.

Ví dụ một mapping có thể khớp:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/orders/42"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": 42,
      "status": "PAID"
    }
  }
}
~~~

Sau khi consumer gửi request đến stub, bài test kiểm:

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

**Mapping** và **`verify`** có thể dùng các matcher tương tự, nhưng làm việc ở **hai thời điểm** khác nhau. Mapping quyết định response; `verify` so các request **đã xảy ra**. Một mapping tồn tại không chứng minh consumer đã gọi nó, và một request đã được ghi lại không nhất thiết đã khớp mapping.

## 3. Hợp đồng Spring Cloud Contract tạo stub trước khi kiểm request

Producer có thể đặt contract tại `src/test/resources/contracts/orders/get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Đọc đơn hàng đã thanh toán'

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
        body(id: 42, status: 'PAID')
    }
}
~~~

Hoặc cùng hành vi bằng YAML DSL:

~~~yaml
description: Đọc đơn hàng đã thanh toán
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
    status: PAID
~~~

Hai tệp là **hai cách minh họa cùng hợp đồng**; trong build thực tế, chỉ nên đặt **một bản có hiệu lực** trong đường dẫn Contract Verifier quét. Producer chạy generated tests để xác minh mã thật, sau đó đóng gói artifact `com.acme:order-service:1.0.0:stubs` cho consumer.

Consumer dùng Stub Runner tải artifact và khởi chạy WireMock với mappings được sinh. Những phép kiểm **số lần gọi** ở bài này thuộc **consumer test**: chúng xác nhận hành vi client khi sử dụng stub đó. Contract mô tả HTTP request/response; nó **không tự định nghĩa mặc định một yêu cầu “phải gọi đúng một lần”** cho mọi consumer.

## 4. Khởi tạo WireMockServer độc lập để học request journal

Trước khi tích hợp Stub Runner, cách đơn giản nhất để hiểu request verification là dùng **WireMockServer** trực tiếp trong một test JUnit 5. Ví dụ này chạy một HTTP stub tại cổng động, giúp test độc lập với các service ngoài.

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.assertj.core.api.Assertions.assertThat;

class OrderClientWireMockTest {
    private WireMockServer wireMockServer;

    @BeforeEach
    void startWireMock() {
        wireMockServer = new WireMockServer(
            wireMockConfig().dynamicPort()
        );
        wireMockServer.start();

        wireMockServer.stubFor(
            get(urlEqualTo("/api/orders/42"))
                .withHeader("Accept", containing("application/json"))
                .willReturn(okJson(
                    "{\"id\":42,\"status\":\"PAID\"}"
                ))
        );
    }

    @AfterEach
    void stopWireMock() {
        wireMockServer.stop();
    }

    @Test
    void callsOrderEndpointExactlyOnce() {
        OrderClient client = new OrderClient(wireMockServer.baseUrl());

        OrderClient.OrderDto order = client.getOrder(42L);

        assertThat(order.status()).isEqualTo("PAID");
        wireMockServer.verify(
            1,
            getRequestedFor(urlEqualTo("/api/orders/42"))
                .withHeader("Accept", containing("application/json"))
        );
    }
}
~~~

`OrderClient` ở trên là **mã consumer thật** của Billing, được triển khai ở mục tiếp theo. Test dùng **`wireMockServer.baseUrl()`**, thay vì đoán cổng hoặc cố định `localhost:8089`. Vì server tạo mới trong `@BeforeEach`, mỗi method có một **request journal sạch** và mapping độc lập.

**Điều kiện để biên dịch:** dự án cần WireMock với API tương ứng (gói `com.github.tomakehurst.wiremock`), JUnit Jupiter, AssertJ và Spring Web/RestClient nếu dùng client mục 5. Các bản WireMock/Spring Cloud Contract khác nhau có thể sử dụng API hoặc cách cấu hình khác nhau; hãy đối chiếu dependency và phiên bản đang dùng.

## 5. Mã HTTP client thật cần được kiểm

Để test có giá trị với consumer, hãy gọi **lớp HTTP client mà ứng dụng sử dụng**, không chỉ tự tạo một HTTP call trong test rồi khẳng định business client đúng.

Ví dụ với **Spring RestClient** (Spring Framework 6.1+):

~~~java
package com.acme.billing;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient client;

    public OrderClient(String baseUrl) {
        this.client = RestClient.builder()
            .baseUrl(baseUrl)
            .build();
    }

    public OrderDto getOrder(long id) {
        return client.get()
            .uri("/api/orders/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(long id, String status) {}
}
~~~

Với client này, bài test ở mục 4 kiểm đồng thời:

- Consumer **gửi GET** tới đúng `/api/orders/42`.
- Request có `Accept` bao gồm `application/json`.
- Client **đọc được JSON** thành `OrderDto`.
- Stub **thực sự nhận đúng một lần gọi** phù hợp điều kiện.

Nếu client có retry tự động làm hai request đến WireMock, phép kiểm `verify(1, ...)` sẽ **FAIL**. Điều đó có thể là lỗi hoặc hành vi mong muốn tùy nghiệp vụ. **Không áp đặt đúng một lần cho mọi API**: phải hiểu hợp đồng nghiệp vụ và chính sách retry trước khi chọn con số kỳ vọng.

## 6. Verify số lần gọi: 0, 1, N và giới hạn của mẫu kiểm

WireMock có dạng verification phổ biến:

~~~java
wireMockServer.verify(
    expectedCount,
    getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

Ví dụ:

~~~java
// Chờ đúng một GET đơn 42:
wireMockServer.verify(
    1, getRequestedFor(urlEqualTo("/api/orders/42"))
);

// Đảm bảo client không gọi endpoint xóa:
wireMockServer.verify(
    0, deleteRequestedFor(urlMatching("/api/orders/.*"))
);

// Sau một batch có chủ đích, đòi đúng ba POST:
wireMockServer.verify(
    3, postRequestedFor(urlEqualTo("/api/orders"))
);
~~~

Khi cần điều kiện **ít nhất** hoặc **không quá** một số lần, WireMock có các khái niệm `moreThanOrExactly(...)`, `lessThanOrExactly(...)` hoặc cơ chế so số lượng qua `findAll(...).size()` tùy API phiên bản. Với bài học, lựa chọn rõ ràng, ít phụ thuộc cấu hình là:

~~~java
int count = wireMockServer.findAll(
    getRequestedFor(urlEqualTo("/api/orders/42"))
).size();

assertThat(count).isBetween(1, 3);
~~~

**Đếm những request khớp matcher**, không phải tổng số request bất kỳ. Nếu consumer gọi `GET /api/orders/42` một lần và `GET /health` hai lần, `verify(1, getRequestedFor(...))` vẫn đạt vì chỉ một request khớp. Nếu mục tiêu là “chỉ một HTTP request duy nhất đến stub”, phải kiểm thêm **toàn bộ request journal**.

### 6.1. Đúng một lần không phải bảo đảm exactly-once end-to-end

Đếm request tại WireMock có thể phát hiện một lời gọi lặp **trong bài test cụ thể**, nhưng không chứng minh một hệ thống phân tán bảo đảm exactly-once khi xảy ra mất kết nối, retry, timeout hoặc redelivery. Với API thanh toán, thay vì chỉ assert “đúng một POST”, thường cần **idempotency key**, hợp đồng xử lý retry và integration tests kiểm tác dụng nghiệp vụ không bị lặp.

Tương tự, một test chỉ gửi một request và `verify(1, ...)` có thể đạt trong khi client vẫn retry hai lần **khi gặp 503**. Muốn kiểm retry, tạo một **kịch bản lỗi có kiểm soát** và assert chính sách retry thực sự trong tình huống đó.

## 7. Verify request matcher: method, URL, query, header và body

Khi xác minh request, hãy kiểm **những yếu tố thuộc hợp đồng hoặc thực sự quan trọng cho consumer**.

### 7.1. Exact URL khác path-only

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlEqualTo("/api/orders/42?view=summary"))
);
~~~

`urlEqualTo` kiểm URL path và query như một chuỗi ở dạng tương ứng, nên có thể quá chặt với thứ tự nhiều query parameters. Nếu API không coi thứ tự query có ý nghĩa, dùng `urlPathEqualTo` cùng matcher query:

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlPathEqualTo("/api/orders/42"))
        .withQueryParam("view", equalTo("summary"))
        .withQueryParam("lang", equalTo("vi"))
);
~~~

Cách này bảo vệ **tên và giá trị tham số** nhưng không buộc consumer phải gửi `view` trước `lang` trong chuỗi URL. Nếu yêu cầu là “không có bất kỳ query param nào khác”, cần kiểm chi tiết request thực hoặc dùng điều kiện/schema phù hợp; kiểm hai tham số trên **không tự cấm tham số thừa**.

### 7.2. Xác minh header

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlPathEqualTo("/api/orders/42"))
        .withHeader("Accept", containing("application/json"))
        .withHeader("X-Correlation-Id", matching("[a-zA-Z0-9-]{8,64}"))
);
~~~

Trên HTTP, tên header không phân biệt chữ hoa/thường, còn **giá trị và định dạng** có thể ảnh hưởng đến tích hợp. Đừng verify các header thay đổi tự động (như User-Agent hoặc Connection) nếu consumer và producer không coi chúng là một phần giao tiếp ổn định.

**Với thông tin bí mật** như bearer token, có thể kiểm **sự hiện diện hoặc format tối thiểu** khi cần, nhưng không ghi token thật vào log hoặc ví dụ. Việc WireMock nhìn thấy một chuỗi token không có nghĩa nó đã **xác thực chữ ký, quyền hay thời hạn** của token đó.

### 7.3. Xác minh body JSON theo nội dung

Giả sử Billing gửi yêu cầu tạo hóa đơn:

~~~http
POST /api/invoices
Content-Type: application/json
Idempotency-Key: invoice-ORD-1042

{"orderId":"ORD-1042","amountMinor":125000}
~~~

Để xác minh các trường quan trọng:

~~~java
wireMockServer.verify(
    1,
    postRequestedFor(urlPathEqualTo("/api/invoices"))
        .withHeader("Content-Type", containing("application/json"))
        .withHeader("Idempotency-Key",
                    equalTo("invoice-ORD-1042"))
        .withRequestBody(matchingJsonPath(
            "$.orderId", equalTo("ORD-1042")))
        .withRequestBody(matchingJsonPath(
            "$.amountMinor", equalTo("125000")))
);
~~~

**Lưu ý JSONPath:** một số matcher chuyển giá trị được chọn thành string để so, nên biểu thức `equalTo("125000")` ở đây **không phải là phép kiểm tuyệt đối về kiểu JSON number**. Nếu consumer cần gửi number chứ không phải string, hãy kiểm kiểu của JSON thật bằng Jackson như mục 9, hoặc dùng matcher JSON/schema phù hợp.

Nếu body phải **đúng cấu trúc JSON**, có thể dùng `equalToJson` thay vì so nguyên văn chuỗi bytes:

~~~java
wireMockServer.verify(
    1,
    postRequestedFor(urlEqualTo("/api/invoices"))
        .withRequestBody(equalToJson(
            "{\"orderId\":\"ORD-1042\",\"amountMinor\":125000}"
        ))
);
~~~

So sánh JSON theo cấu trúc thường **không phụ thuộc thứ tự khóa object**. Các tùy chọn bỏ qua phần tử thừa hoặc thứ tự array thay đổi độ chặt; chỉ bật khi API thật sự không cam kết những điều đó.

## 8. Xem toàn bộ request đã nhận bằng findAll

`verify(...)` trả lời “có đúng số lượng request khớp không?”. Khi test thất bại hoặc muốn xem dữ liệu thực, dùng **request journal**:

~~~java
import com.github.tomakehurst.wiremock.verification.LoggedRequest;

List<LoggedRequest> requests = wireMockServer.findAll(
    getRequestedFor(urlPathEqualTo("/api/orders/42"))
);

assertThat(requests).hasSize(1);

LoggedRequest received = requests.get(0);
assertThat(received.getUrl()).isEqualTo("/api/orders/42");
assertThat(received.getHeader("Accept"))
    .contains("application/json");
~~~

Đây là **những request server đã nhận**, không phải những request được test tự dựng để làm kỳ vọng. Khi client dùng một query string khác hoặc thiếu header, journal giúp nhìn thấy sự khác biệt.

Ví dụ dùng trong chẩn đoán:

~~~java
List<LoggedRequest> allOrders = wireMockServer.findAll(
    getRequestedFor(urlPathMatching("/api/orders/.*"))
);

for (LoggedRequest request : allOrders) {
    System.out.println(
        request.getMethod().getName() + " " + request.getUrl()
    );
}
~~~

**Không đưa toàn bộ request có Authorization header, cookie hoặc dữ liệu cá nhân vào CI log**. Khi cần log phục vụ điều tra, chỉ in trường không nhạy cảm, che token và giới hạn số record. Đối với payload lớn, kiểm hoặc log JSONPath quan trọng thay vì dump toàn bộ body.

### 8.1. Đọc body thực tế, không chỉ kiểm JSONPath

~~~java
List<LoggedRequest> posts = wireMockServer.findAll(
    postRequestedFor(urlPathEqualTo("/api/invoices"))
);

assertThat(posts).hasSize(1);

String actualBody = posts.get(0).getBodyAsString();
JsonNode json = objectMapper.readTree(actualBody);

assertThat(json.get("orderId").asText()).isEqualTo("ORD-1042");
assertThat(json.get("amountMinor").isIntegralNumber()).isTrue();
assertThat(json.get("amountMinor").longValue()).isEqualTo(125000L);
~~~

Ở đây `objectMapper` là Jackson `ObjectMapper` đã được test khởi tạo hoặc inject. Đoạn code minh họa một phần method JUnit có `throws Exception`/import phù hợp. Việc kiểm `isIntegralNumber()` bảo vệ **JSON number nguyên**, thay vì vô tình chấp nhận chuỗi `"125000"` có nội dung giống số.

## 9. Phân biệt matched và unmatched requests

WireMock có thể **ghi nhận request dù không tìm thấy mapping phù hợp**. Ví dụ mapping chỉ cho phép:

~~~http
GET /api/orders/42
~~~

nhưng consumer lại gửi:

~~~http
GET /api/order/42
~~~

Server vẫn **nhận một HTTP request**; chỉ là nó **không match** mapping của hợp đồng, nên có thể trả 404 mặc định.

Các API liên quan:

~~~java
// Truy vấn những request không khớp stub mapping nào:
List<LoggedRequest> unmatched =
    wireMockServer.findUnmatchedRequests();

assertThat(unmatched).isEmpty();

// Xem các lần phục vụ request kèm thông tin matching/response:
var serveEvents = wireMockServer.getAllServeEvents();
assertThat(serveEvents).isNotEmpty();
~~~

`findUnmatchedRequests()` cho biết có request nào chưa match mapping hay không. `getAllServeEvents()` cung cấp thêm dữ liệu phục vụ chẩn đoán (request, mapping/response và trạng thái matching tùy API phiên bản). Không cần dựa vào tên method phụ của `ServeEvent` chưa kiểm chứng khi chỉ muốn assert số lần gọi.

**Điểm kiểm quan trọng:** `verify(0, getRequestedFor(urlEqualTo("/api/orders/42")))` có thể PASS khi client **chưa gọi gì cả**, và cũng có thể PASS khi client **gọi sai path**. Nếu test yêu cầu một lần gọi thành công, phải assert **positive count** và kiểm kết quả consumer; nếu cần phát hiện request sai, assert **unmatched journal rỗng** hoặc kiểm toàn bộ request đã nhận.

### 9.1. HTTP 404 không tự chứng minh lỗi nghiệp vụ

Một stub có thể trả 404 trong ít nhất hai tình huống:

1. Có **hợp đồng lỗi 404** rõ ràng, mapping được khớp rồi trả payload `ORDER_NOT_FOUND`.
2. Không có mapping khớp, WireMock trả 404 **do no-match**.

Nếu consumer test chỉ assert status 404, có thể **đạt giả** trong trường hợp thứ hai, kể cả client gửi sai URL. Để kiểm xử lý lỗi nghiệp vụ, nên có hợp đồng 404 với body:

~~~json
{"code":"ORDER_NOT_FOUND","message":"Order does not exist"}
~~~

sau đó assert `code=ORDER_NOT_FOUND` **và** xác minh request match đúng path/header. `findUnmatchedRequests()` giúp phát hiện no-match khi chạy với WireMock có request journal.

## 10. Reset request journal để test độc lập

Số lần gọi là **dữ liệu trạng thái** của stub server. Nếu test A gọi một lần rồi test B cũng kiểm `verify(1, ...)` trên cùng server mà không reset, B có thể thấy **hai lần** và thất bại. Cần quyết định lifecycle phù hợp:

| Cách reset | Điều bị xóa | Khi dùng |
| --- | --- | --- |
| `resetRequests()` | Request journal đã ghi. | Giữ stub mappings, chỉ làm sạch lịch sử trước mỗi test. |
| `resetAll()` | Request journal và các mappings/stub state liên quan. | Muốn dựng lại toàn bộ stubs từ đầu, thường với server tự quản. |
| `resetScenarios()` | Trạng thái của WireMock scenarios. | Khi sử dụng mapping stateful cho retry hoặc chuỗi request có thứ tự. |
| **Tạo server mới cho từng test** | Không chia sẻ request journal/mappings từ test trước. | Cách rõ ràng để tránh state leak khi tài nguyên cho phép. |

Ví dụ với một `WireMockServer` được dùng lại:

~~~java
@BeforeEach
void clearRequestHistory() {
    wireMockServer.resetRequests();
}
~~~

**Không tùy tiện gọi `resetAll()` trong test dùng Stub Runner** nếu mục tiêu là giữ các mappings được tạo từ artifact hợp đồng: xóa mappings có thể khiến những request hợp lệ trả 404. Khi chỉ cần đếm request mới, dùng **`resetRequests()`** hoặc tạo context/server cô lập.

### 10.1. Chạy song song cần nhiều hơn reset

Nếu test A và B **cùng ghi vào một request journal** ở cùng thời điểm, việc reset có thể xóa request mà test kia đang chuẩn bị assert. Để chạy parallel tin cậy:

- Dùng **WireMockServer riêng** cho từng test/class, mỗi instance có port động.
- Hoặc cô lập mỗi tập request bằng **correlation ID** rồi verify matcher theo ID khi thật sự không thể tách server.
- Nếu chia sẻ Stub Runner context và mappings, quản lý tài nguyên/test parallel rõ ràng, không reset journal từ nhiều test đồng thời.
- Không dùng biến global cấu hình HTTP port của một client cho nhiều instance trong khi chạy song song.

Một test đếm request phải có **phạm vi đo** xác định: từ thời điểm reset (hoặc khi instance mới được tạo) tới khi hành vi client cần kiểm đã hoàn tất.

## 11. Admin API: xác minh request trên Stub Runner HTTP server

Trong bài test dùng **Stub Runner**, bạn thường có **URL của WireMock stub** nhưng không nhất thiết có trực tiếp bean `WireMockServer`. WireMock cung cấp **Admin API** để truy vấn request journal qua HTTP trên chính stub server đó.

Các endpoint phổ biến:

| Admin endpoint | Ý nghĩa |
| --- | --- |
| `GET /__admin/requests` | Lấy danh sách request đã nhận. |
| `POST /__admin/requests/count` | Đếm các request khớp một request pattern. |
| `POST /__admin/requests/find` | Tìm các request khớp pattern và lấy bản ghi thực. |
| `GET /__admin/requests/unmatched` | Liệt kê request không khớp mapping. |
| `DELETE /__admin/requests` | Xóa lịch sử request, giữ các mappings. |

Ví dụ body gửi tới **count API**:

~~~json
{
  "method": "GET",
  "url": "/api/orders/42",
  "headers": {
    "Accept": {
      "contains": "application/json"
    }
  }
}
~~~

Response minh họa:

~~~json
{"count":1}
~~~

**Không nhầm Admin API với API của producer.** `/__admin/requests/count` là endpoint của WireMock dành cho kiểm thử/quan sát, không phải business endpoint của Order Service. Chỉ truy cập trong môi trường test đáng tin cậy; không công khai Admin API trên internet khi không có kiểm soát truy cập.

### 11.1. Đếm qua curl

Giả sử biến môi trường `STUB_URL` chứa base URL mà Stub Runner đã cấp:

~~~shell
curl -sS -X POST "$STUB_URL/__admin/requests/count" \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","url":"/api/orders/42"}'
~~~

Lệnh này **không cần biết port cố định**; `STUB_URL` có thể là `http://localhost:12543` hoặc địa chỉ khác tùy test environment. Phải lấy URL từ Stub Runner hoặc cấu hình môi trường đã xác nhận, **không tự đoán** số cổng.

Khi cần tìm request thực:

~~~shell
curl -sS -X POST "$STUB_URL/__admin/requests/find" \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","urlPath":"/api/orders/42"}'
~~~

Các lệnh ở đây chỉ minh họa giao diện Admin API; không cần chạy shell trong mỗi consumer test. Tốt hơn nên dùng assertions Java để thất bại với thông báo rõ ràng trong CI.

## 12. Stub Runner + StubFinder + Admin API: ví dụ consumer test

Một consumer JUnit 5 có thể dùng **`StubFinder`** tra URL động của Order Service stub, gọi mã client thật, rồi truy vấn Admin count API để biết **số lần stub nhận request**.

~~~java
import java.net.URL;
import java.util.Map;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired
    private StubFinder stubFinder;

    @Test
    void callsCorrectOrderEndpointOnce() {
        URL url = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub was not started"
        );

        String baseUrl = url.toExternalForm();
        RestClient admin = RestClient.create(baseUrl);

        // 1. Làm sạch journal của test này; không xóa stub mappings.
        admin.delete().uri("/__admin/requests")
            .retrieve().toBodilessEntity();

        // 2. Gọi mã consumer thật.
        OrderClient client = new OrderClient(baseUrl);
        OrderClient.OrderDto result = client.getOrder(42L);

        assertThat(result.id()).isEqualTo(42L);
        assertThat(result.status()).isEqualTo("PAID");

        // 3. Kiểm server đã nhận đúng request dự kiến một lần.
        RequestCount count = admin.post()
            .uri("/__admin/requests/count")
            .contentType(MediaType.APPLICATION_JSON)
            .body(Map.of(
                "method", "GET",
                "url", "/api/orders/42"
            ))
            .retrieve()
            .body(RequestCount.class);

        assertThat(count).isNotNull();
        assertThat(count.count()).isEqualTo(1);
    }

    record RequestCount(int count) {}
}
~~~

**Điều kiện để chạy:** mã `OrderClient` dùng thực sự trong consumer như ở mục 5; artifact `com.acme:order-service:1.0.0:stubs` đã được producer cài vào Maven local; test có Spring Boot Test, Stub Runner, RestClient, Jackson và AssertJ tương thích. Đoạn ví dụ dùng một context/test độc lập; **không reset journal giữa chừng nếu các test khác đang dùng chung stub instance**.

Với `StubsMode.REMOTE`, Stub Runner tải artifact từ Maven repository đã cấu hình nhưng vẫn có thể khởi động WireMock ở một port động trên máy test. `StubFinder` trả **URL của HTTP stub đang chạy**, **không phải** URL repository; Admin API được gọi trên chính URL stub đó.

### 12.1. Kiểm thêm request thực tế đã nhận

Count API cho biết **số lượng**, nhưng không hiển thị đầy đủ từng request. Để kiểm sâu hơn có thể gọi:

~~~java
String journal = admin.get()
    .uri("/__admin/requests")
    .retrieve()
    .body(String.class);

// Phân tích journal bằng Jackson JsonNode, chỉ lấy các trường cần assert.
// Tránh in toàn bộ journal có chứa tokens/PII vào CI log.
~~~

Hoặc POST `/__admin/requests/find` với pattern JSON rồi đọc danh sách request nhận được. Trong các phiên bản WireMock khác nhau, một số trường trong Admin response có thể thay đổi; cần đối chiếu API của phiên bản đang chạy trước khi hardcode đường JSONPath sâu của cấu trúc journal.

## 13. Kiểm retry: số lần gọi có thể là yêu cầu thực sự

Giả sử Billing được yêu cầu:

- Khi Order Service trả `200`: chỉ gửi **một** GET.
- Khi gặp một lỗi tạm thời `503`: thử lại **tối đa hai lần**, tức tối đa **ba request** cho một thao tác.
- Khi gặp `404` nghiệp vụ: **không retry**.

Đây là **chính sách consumer**, không tự phát sinh từ một HTTP contract thành công. WireMock có thể dùng **scenarios** để phản hồi lần đầu `503` rồi `200` sau đó:

~~~java
import static com.github.tomakehurst.wiremock.stubbing.Scenario.STARTED;

wireMockServer.stubFor(
    get(urlEqualTo("/api/orders/42"))
        .inScenario("temporary-order-outage")
        .whenScenarioStateIs(STARTED)
        .willReturn(aResponse().withStatus(503))
        .willSetStateTo("recovered")
);

wireMockServer.stubFor(
    get(urlEqualTo("/api/orders/42"))
        .inScenario("temporary-order-outage")
        .whenScenarioStateIs("recovered")
        .willReturn(okJson("{\"id\":42,\"status\":\"PAID\"}"))
);
~~~

Sau khi gọi client **đã cấu hình retry**, có thể assert:

~~~java
wireMockServer.verify(
    2,
    getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

**Chú ý:** đoạn này chỉ cấu hình stub response, **không cài đặt retry** cho OrderClient trong mục 5. Nếu client chưa có chính sách retry, nó sẽ dừng ở 503 và số lần gọi là 1. Một bài test retry hoàn chỉnh cần có **mã client retry thật**, cách bắt lỗi và một assertion response sau retry, không chỉ kỳ vọng count 2 rồi coi retry đã tồn tại.

Nếu muốn kiểm “không quá ba request”, có thể dùng `findAll(...).size()` và assert trong miền `1..3`. Khi kiểm 404 không retry, phải có **mapping trả 404 nghiệp vụ**, không dựa vào 404 do no-match, và reset scenario/journal đúng thời điểm.

### 13.1. Request idempotency và duplicate submission

Với `POST /api/payments` hoặc `POST /api/invoices`, lặp request có thể tạo tác dụng phụ. WireMock request journal giúp bạn biết consumer đã gửi **hai HTTP requests**, nhưng **không mô phỏng đầy đủ việc producer xử lý idempotency**. Nếu API có `Idempotency-Key`, test nên kiểm:

1. Mọi lần retry của cùng giao dịch dùng **cùng một key**.
2. Key khác nhau giữa những giao dịch độc lập.
3. Số lần retry nằm trong chính sách và có backoff/timeout phù hợp.
4. Producer integration tests xác minh **tác dụng nghiệp vụ** không bị nhân đôi.

Không kết luận “exactly-once” chỉ vì Stub Runner test ghi nhận đúng một request trong happy path.

## 14. Đọc request journal với bất đồng bộ

Một consumer có thể sử dụng `WebClient`, `CompletableFuture` hoặc đưa request qua queue. Nếu verify quá sớm, journal chưa có đủ request:

~~~java
client.getOrderAsync(42L); // Khởi động thao tác bất đồng bộ.
wireMockServer.verify(
    1, getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

Đoạn test trên có thể **FAIL ngẫu nhiên** vì HTTP request chưa xảy ra khi `verify` chạy. Hãy **đợi thao tác consumer hoàn tất** bằng primitive bất đồng bộ có timeout rõ, sau đó xác minh request count:

~~~java
OrderDto order = client.getOrderAsync(42L)
    .get(3, TimeUnit.SECONDS);

assertThat(order.status()).isEqualTo("PAID");
wireMockServer.verify(
    1, getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

Đây là minh họa khi client có `CompletionStage`/`Future` tương ứng; lớp `OrderDto`, import và phương thức bất đồng bộ cần được dự án cung cấp. Với Reactor/WebClient, dùng `StepVerifier` có deadline hoặc chờ publisher hoàn tất trong test.

**Không dùng `Thread.sleep` cố định để “chờ đủ lâu”**: nó không đảm bảo request đã đến và khiến CI chậm/chập chờn. Với event background không có future hoàn tất, hãy dùng cơ chế chờ điều kiện với **timeout hữu hạn** như Awaitility và matcher cụ thể.

## 15. Tránh kiểm quá chặt hoặc quá lỏng

Một phép kiểm đáng tin phản ánh **đúng điều API và hành vi consumer phải tuân thủ**.

| Cách kiểm | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| `verify(1, getRequestedFor(urlEqualTo(...)))` | Đúng một request tới một URL cố định là yêu cầu. | Có thể quá chặt khi retry được phép. |
| `urlPathEqualTo` + `withQueryParam` | Thứ tự các query params không quan trọng. | Không tự cấm query params bổ sung. |
| `withHeader("Accept", containing(...))` | Kiểm client yêu cầu JSON. | Có thể quá yếu nếu API đòi đúng media type. |
| `matchingJsonPath("$.orderId", ...)` | Kiểm field quan trọng, không phụ thuộc thứ tự khóa. | Có thể bỏ qua extra fields hoặc sai kiểu nếu không kiểm thêm. |
| `equalToJson(...)` | Kiểm body JSON theo cấu trúc. | Cần quyết định extra elements/array order. |
| `findUnmatchedRequests().isEmpty()` | Muốn phát hiện request ngoài mapping. | Một mapping rất rộng có thể vẫn chấp nhận request sai nghiệp vụ. |
| `getAllServeEvents()` | Chẩn đoán request/response đã phục vụ. | Không thay được assertions có chủ đích. |

Đặc biệt, **request matcher của stub** có thể rộng hơn matcher dùng trong `verify`. Ví dụ stub chấp nhận `GET /api/orders/.*` nhưng contract consumer chỉ cho phép ID có cấu trúc `/api/orders/[0-9]+`; stub trả response thành công cho path sai không chứng minh client đúng. Hãy chọn matcher đủ chặt và **assert request thực tế** đã gửi.

Ngược lại, đừng assert thứ tự khóa JSON hoặc các header tự sinh không thuộc hợp đồng: một nâng cấp HTTP client hợp lệ có thể khiến test đỏ giả.

## 16. CI: kết hợp producer verification, Stub Runner và request journal

Một luồng kiểm thử end-to-end ở mức hợp đồng:

~~~mermaid
flowchart TD
    A["Producer sửa API/contract"] --> B["Verifier sinh producer tests"]
    B --> C{"Producer verification đạt?"}
    C -->|Không| D["Chặn publish stub"]
    C -->|Có| E["Đóng gói artifact classifier stubs"]
    E --> F["Publish version được chọn"]
    F --> G["Consumer CI tải stub qua Stub Runner"]
    G --> H["Chạy mã client thật, nhận response mẫu"]
    H --> I["WireMock ghi request journal"]
    I --> J["Assert số lần, URL, headers, body, no-match"]
    J --> K["Đánh giá tương thích consumer"]
~~~

Checklist quan trọng:

1. **Kiểm producer tests thật sự được sinh và chạy**, không coi việc có JAR stub là chứng cứ producer đã đúng hợp đồng.
2. **Ghim stub version** trong consumer CI; đừng dùng một artifact thay đổi ngầm.
3. **Dùng URL/port thực của Stub Runner**, có thể qua `StubFinder`, tránh cố định `localhost:8089` khi chạy song song.
4. **Cô lập request journal** theo test/context, chỉ reset khi không ảnh hưởng test khác.
5. **Assert response** từ mã client thật và **assert request journal** theo mức chặt phù hợp.
6. **Kiểm unmatched requests** khi muốn phát hiện path/headers/body sai ngoài mapping.
7. **Không log dữ liệu nhạy cảm** từ journal. Nếu cần gỡ lỗi, lọc hoặc redaction các trường liên quan.
8. **Phân biệt lỗi test wiring và lỗi API**: không tìm thấy stub, connection refused, no-match 404 và response lỗi nghiệp vụ không giống nhau.

### 16.1. Một số tình huống kiểm thực tế

| Tình huống consumer | Điều cần xác minh từ journal | Điều còn phải kiểm |
| --- | --- | --- |
| Đọc một đơn thành công | Một `GET` đúng path/query/Accept. | Đọc được `PAID` và producer verification. |
| Submit hóa đơn | Một `POST` đúng body và Idempotency-Key. | Producer không tạo hóa đơn trùng trong test nghiệp vụ. |
| Retry sau 503 | Số lần gọi đúng chính sách, request nhất quán. | Retry chỉ khi lỗi phù hợp; backoff/timeout. |
| Gặp 404 nghiệp vụ | Không retry ngoài ý muốn. | Mapping 404 với error body, client xử lý đúng. |
| Có nhiều producer stubs | Request xuất hiện trong journal của **đúng** stub instance. | URL tra cứu, version và behavior từng producer. |
| Chạy song song | Journal không lẫn request giữa các test. | Isolation theo test context/port/correlation ID. |

## 17. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `verify(1, ...)` báo 0 request. | Client chưa gọi, gọi sai stub URL hoặc matcher quá chặt. | Kiểm URL thực, `getAllServeEvents()`, `findUnmatchedRequests()` và request journal. |
| `verify(1, ...)` báo 2 requests. | Client retry, gọi lặp hoặc journal chứa request test trước. | Kiểm chính sách retry, reset journal và isolation. |
| Response 200 đúng nhưng verify header FAIL. | Client thiếu header hoặc matcher header không phù hợp. | Xem request thực, điều chỉnh mã client hoặc quy tắc đã thỏa thuận. |
| WireMock trả 404. | Request không match mapping hoặc mapping lỗi nghiệp vụ. | Xem unmatched journal và mapping; assert error body nếu 404 nghiệp vụ. |
| Request body test PASS dù number biến thành string. | Matcher JSONPath chỉ so text, không bảo vệ kiểu. | Parse body `JsonNode`, kiểm `isIntegralNumber()`/schema. |
| `findAll(...)` trả lịch sử của test khác. | Dùng chung server và không reset request journal. | Tạo server mỗi test, hoặc reset đúng lifecycle khi không chạy song song. |
| `resetAll()` làm mọi request trả 404. | Đã xóa luôn mappings Contract Stub Runner. | Dùng `resetRequests()` nếu chỉ muốn xóa journal; nạp lại mappings nếu cần. |
| Không thấy request trong journal dù HTTP call thành công. | Journal bị disable, đang hỏi nhầm WireMock instance, hoặc request đi tới server khác. | Kiểm cấu hình recording/journal, URL, instance và test setup. |
| Test async chập chờn. | `verify` chạy trước khi HTTP request kết thúc. | Await future/publisher với deadline trước khi đọc journal. |
| Admin API trả lỗi hoặc không truy cập được. | Sai host/port, server proxy chặn admin, phiên bản khác hoặc bị bảo vệ. | Tra Stub Runner URL, kiểm quyền và API tương ứng; không công khai admin. |
| Producer test xanh nhưng consumer gửi sai path. | Producer verification chỉ kiểm implementation producer với input mẫu; client consumer có lỗi riêng. | Consumer test dùng mã client thật và kiểm request journal. |

Với lỗi nghiêm trọng, thực hiện theo thứ tự **đúng artifact → đúng URL stub → request có đến không → request có match không → response nào được trả → số lần và nội dung request → chính sách consumer**. Tránh sửa hợp đồng chỉ để che một lỗi cấu hình test.

## 18. Bài thực hành: từ response assertion tới request verification

Trên một producer Order Service có Spring Cloud Contract Verifier và một consumer Billing Service:

1. **Định nghĩa contract** `GET /api/orders/42` trả `200` với JSON `{"id":42,"status":"PAID"}` bằng Groovy hoặc YAML DSL.
2. **Chạy generated producer tests**, xác minh Order Service thật đáp ứng hợp đồng; đóng gói/cài hoặc publish artifact `com.acme:order-service:1.0.0:stubs`.
3. **Tạo WireMockServer độc lập** ở cổng động để luyện `verify(1, ...)`, `findAll(...)`, `findUnmatchedRequests()` và `resetRequests()`.
4. **Viết OrderClient thật** gửi GET có `Accept: application/json` và parse JSON thành DTO. Dùng client này trong test, không chỉ gọi stub bằng HTTP client của test.
5. **Assert response và count**: `id=42`, `status=PAID`, đúng một GET tại `/api/orders/42`.
6. **Cố tình sửa mã client** gọi `/api/order/42`; kiểm journal ghi nhận request không khớp và test FAIL. Khôi phục.
7. **Cố tình gọi hai lần**; kiểm `verify(1, ...)` FAIL rồi cập nhật test hoặc client theo đúng yêu cầu nghiệp vụ, không sửa con số tùy tiện.
8. **Viết thêm POST JSON** có `orderId` và `amountMinor`; dùng `matchingJsonPath`, sau đó parse `LoggedRequest.getBodyAsString()` với Jackson để xác minh JSON number thực.
9. **Chuyển sang Stub Runner** tải artifact thật, tra URL qua `StubFinder`, dùng Admin count API để kiểm đúng một request mà không cần bean `WireMockServer`.
10. **Kiểm trạng thái journal giữa các test**, thử chạy song song, chọn reset/cô lập để test không phụ thuộc thứ tự.
11. **Thử kịch bản retry 503 → 200** với WireMock scenarios, kiểm số lần gọi và thời điểm chờ theo chính sách thật của client.
12. **Đưa vào CI**: producer verification → publish stubs → consumer Stub Runner → response + request journal assertions; giữ artifact version xác định và không in token trong logs.

**Tiêu chí đạt:** người học chứng minh được **WireMock đã nhận chính xác những request nào**, **bao nhiêu lần**, **phần nào trong request được kiểm**, **request nào không khớp mapping**, đồng thời giải thích rõ **vì sao kết quả consumer test không thay thế producer verification**.

## 19. Câu hỏi tự kiểm tra

1. Sự khác nhau giữa **request matching** lúc trả response và **request verification** sau khi client đã gọi là gì?
2. Vì sao một mapping WireMock tồn tại không chứng minh consumer đã gọi endpoint?
3. `verify(1, getRequestedFor(...))` đếm mọi request đến server hay chỉ những request khớp matcher?
4. `verify(0, ...)` có thể PASS trong những tình huống nào khiến bạn kết luận nhầm?
5. Khi nào nên dùng `urlPathEqualTo` kết hợp `withQueryParam` thay vì `urlEqualTo`?
6. Vì sao `matchingJsonPath("$.amountMinor", equalTo("125000"))` chưa chắc đã bảo vệ kiểu JSON number?
7. Khác biệt giữa `findAll(...)`, `findUnmatchedRequests()` và `getAllServeEvents()`?
8. Vì sao `resetAll()` không phải lựa chọn tốt nếu muốn giữ Stub Runner mappings?
9. Tại sao một response 404 từ stub không luôn là lỗi nghiệp vụ 404 của producer?
10. Khi Stub Runner không cung cấp bean WireMockServer, bạn có thể kiểm số lần gọi bằng endpoint nào của Admin API?
11. Vì sao `StubsMode.REMOTE` không có nghĩa Admin API phải được gọi ở URL Maven repository?
12. Nếu client retry sau 503, cần kiểm những gì ngoài số lần request?
13. Với test bất đồng bộ, vì sao phải chờ thao tác hoàn tất trước khi đọc request journal?
14. Vì sao một request journal có dữ liệu của test trước có thể làm kiểm thử sai dù producer và consumer không đổi?

**Ghi nhớ:** **WireMock request journal cho biết stub đã nhận request nào và bao nhiêu lần**, còn mappings quyết định response được trả. Dùng `verify(...)` để kiểm số lần và matcher, `findAll(...)`/`getAllServeEvents()` để xem request thực, `findUnmatchedRequests()` để phát hiện no-match, và **Admin API** khi chỉ có URL của Stub Runner. Cô lập journal theo test, kiểm đúng request headers/body, phân biệt 404 nghiệp vụ với 404 no-match và phối hợp **consumer test với producer verification** trước khi phát hành stub. Như vậy, một bài contract test bảo vệ được cả **lời hứa API** và **cách consumer thực sự sử dụng lời hứa đó**, thay vì chỉ xác nhận stub trả một JSON mẫu.
