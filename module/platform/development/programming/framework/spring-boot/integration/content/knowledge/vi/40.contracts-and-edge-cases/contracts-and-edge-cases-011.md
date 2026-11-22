# Đối chiếu giới hạn của mock với hành vi dịch vụ thật

Một adapter Spring Boot gọi API đối tác có thể vượt qua toàn bộ unit test: request đúng URI, mock trả về JSON hợp lệ, ứng dụng ánh xạ sang đối tượng miền chính xác. Nhưng khi triển khai, phía đối tác trả `429 Too Many Requests`, đóng kết nối HTTP đang rảnh hoặc đổi một trường từ `"12.50"` sang số `12.50`. Tất cả những tình huống này đều **nằm ngoài phần hành vi đã được lập trình vào mock**. Bài test xanh chứng minh ứng dụng xử lý được *kịch bản giả định*, chứ chưa chứng minh tương thích hoàn toàn với dịch vụ thật.

Bài học thuộc chương **Hợp đồng và lỗi biên** của mô-đun **SPRING_BOOT_INTEGRATION**. Trong hệ thống tích hợp qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration, mục tiêu không dừng ở việc so request/response: cần bảo đảm **hợp đồng dữ liệu**, **giao dịch**, **lỗi**, **chống xử lý trùng**, **kiểm thử**, **quan sát** và khả năng phục hồi của cả luồng.

Bài này hướng dẫn xây chiến lược kiểm thử nhiều lớp để đối chiếu **điều mock khẳng định được**, **điều chỉ test qua giao thức thật mới phát hiện** và **điều phải xác nhận trực tiếp với provider hoặc môi trường tích hợp**.

## 1. Mock kiểm tra giả định, dịch vụ thật thực thi một hệ thống

Giả sử ứng dụng đặt hàng phải kiểm tra tồn kho từ dịch vụ Inventory:

~~~text
GET /stocks/SKU-1
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-1","available":12}
~~~

Mock có thể được lập trình để trả đúng response trên mọi lần gọi. Nhưng provider thực tế có thể:

- Yêu cầu xác thực OAuth token và kiểm tra scope theo tài nguyên.
- Trả `404` cho SKU chưa tồn tại, `429` khi vượt quota, `503` khi đang bảo trì.
- Trả `200` nhưng body có thêm field, giá trị `null`, ký tự Unicode hoặc trường hợp không có dữ liệu.
- Phân trang kết quả, dùng `ETag` hoặc có dữ liệu chỉ nhất quán sau một độ trễ.
- Đóng idle connection, trả response dạng chunked/gzip hoặc yêu cầu TLS/certificate hợp lệ.
- Giới hạn request theo tenant, thay đổi luật nghiệp vụ theo thời điểm hoặc trả kết quả phụ thuộc trạng thái đã ghi.

Không một mock tự biết các quy tắc đó. Nó chỉ biết những gì tác giả test đã khai báo. Vì vậy, câu hỏi quan trọng sau mỗi test xanh là: **test đã xác nhận một sự thật của provider, hay chỉ xác nhận giả định do chính nhóm consumer viết ra?**

### 1.1. Phân biệt các công cụ thường được gọi chung là “mock”

| Loại | Chạy ở đâu? | Kiểm tra được | Chưa chứng minh được |
| --- | --- | --- | --- |
| **Mock/spy của interface** (Mockito) | Trong JVM của test | Lời gọi method, tham số, quy tắc nhánh, số lần gọi | HTTP serialization, headers, TLS, lỗi transport, hợp đồng provider |
| **Stub/fixture** | Trong test hoặc file dữ liệu | Mapping với các response mẫu, trường hợp lỗi đã khai báo | Response thực tế có đúng mẫu đó hay không |
| **Spring `MockRestServiceServer`** | Chặn request ở lớp HTTP client Spring | URI, method, headers, body do `RestClient`/`RestTemplate` tạo; cách adapter xử lý response giả | Socket thật, DNS, TLS, connection pooling, hành vi provider |
| **HTTP mock server** (WireMock, MockWebServer) | Server riêng, thường trên loopback/containers | HTTP request thực sự qua socket, status/header/body, timeout/chậm theo kịch bản | Logic nghiệp vụ thật, production auth/quota/DB phía provider |
| **Contract test có provider verification** | Consumer + bước xác minh trên provider | Provider hiện tại đáp ứng các interaction đã thỏa thuận | Toàn bộ trạng thái, concurrency, network, hiệu năng, vận hành |
| **Dịch vụ thật ở sandbox/staging** | Provider và dependency thật trong môi trường thử | Các hành vi đã cấu hình của provider, auth, persistence, protocol, state | Mọi điều kiện production nếu data/quota/network khác |
| **Canary/quan sát production** | Đường xử lý thật, lưu lượng có kiểm soát | Hành vi trong điều kiện vận hành đang có | Mọi lỗi hiếm hoặc kịch bản chưa xảy ra |

Từ **mock** trong thực hành đôi khi chỉ tất cả test double. Khi đánh giá độ tin cậy, hãy mô tả rõ test ở **lớp nào**, có **socket/network thật không**, provider có **chạy chính code sản xuất không**, và **dữ liệu/trạng thái** được cung cấp bởi đâu.

## 2. Xác định nguồn hợp đồng trước khi viết mock

Nếu test fixture được tạo bằng cách nhìn vào code client hiện tại, rồi mock server trả đúng trường mà client đang chờ, test có thể củng cố một hiểu nhầm. Nguồn chuẩn nên có chủ sở hữu và cách quản lý phiên bản rõ ràng.

Các loại hợp đồng thường gặp trong `SPRING_BOOT_INTEGRATION`:

| Ranh giới | Hợp đồng chính | Ví dụ điểm dễ lệch |
| --- | --- | --- |
| **REST/HTTP** | OpenAPI, JSON Schema, status codes, headers, quy tắc lỗi/throttling | `null` và absent, enum, `Retry-After`, body rỗng, idempotency key |
| **SOAP/XML** | WSDL, XSD, binding, SOAPAction, SOAP Fault | Namespace, QName, thứ tự phần tử, SOAP 1.1 và 1.2 |
| **Kafka/AMQP** | Schema Avro/Protobuf/JSON, routing, keys, ack/retry/DLT policy | Schema evolution, key distribution, ordering, redelivery |
| **Database** | Schema migrations, constraints, transaction isolation, SQL semantics | Unique key, khóa, precision decimal, rollback, timezone |
| **Redis/cache** | Key pattern, TTL, serialization, consistency và fallback policy | Key expiry, eviction, thundering herd, stale value |
| **Spring Integration** | Payload/header/channel/error-channel và ack/commit boundary | Error channel không được nối, async handoff không bền vững |

**Hợp đồng chính thức không chỉ gồm schema.** Với API ghi dữ liệu, còn cần quy định: một idempotency key được giữ trong bao lâu, response nào nghĩa là đã nhận xử lý, thứ tự trạng thái, timeout nào có kết quả không chắc chắn, và lỗi nào được retry. Những quy tắc này có thể nằm trong tài liệu nghiệp vụ hoặc thoả thuận tích hợp thay vì OpenAPI thuần.

Nên tạo một tập mẫu có nguồn gốc:

~~~text
src/test/resources/contracts/inventory/
  openapi.yaml
  response-stock-available.json
  response-stock-not-found.json
  response-stock-throttled.json
  response-stock-null-field.json
  request-reserve-stock.json
  response-reservation-accepted.json
~~~

Với mỗi fixture, ghi nguồn và phiên bản của hợp đồng, ví dụ ngày provider phát hành schema hoặc snapshot đã được hai bên phê duyệt. Dữ liệu capture từ dịch vụ thật phải **loại bỏ token, thông tin cá nhân, mật khẩu và dữ liệu thanh toán** trước khi đưa vào repository.

## 3. Một ma trận giới hạn của mock

Để lựa chọn test, đối chiếu **hành vi muốn bảo đảm** với **lớp test nhỏ nhất có thể chứng minh**:

| Tình huống | Mock cùng tiến trình | HTTP mock server | Provider/sandbox hoặc test hạ tầng |
| --- | --- | --- | --- |
| Mapping JSON hợp lệ thành DTO | Tốt | Tốt | Có thể đối chiếu thêm |
| Client phát đúng method/URI/header | Có thể kiểm tra | Tốt qua socket | Xác nhận provider chấp nhận |
| Provider trả đủ trường/đúng kiểu | Chỉ giả định qua fixture | Chỉ giả định qua fixture | Cần schema/provider verification |
| HTTP `429` rồi `200` | Mô phỏng chính sách retry | Tốt với request thật | Kiểm tra quota/`Retry-After` thực tế |
| DNS/TLS/certificate | Không | Loopback hạn chế; có thể dựng TLS riêng | Cần test mạng/TLS phù hợp |
| Idle connection bị server đóng | Không | Có thể tiêm lỗi ở transport | Cần pool, proxy, endpoint thực tế |
| Race condition giữa hai request | Thường không | Dựng concurrency cục bộ | Cần provider/state store thực, tải phù hợp |
| Giao dịch DB rollback/lock/unique | Mock repository không chứng minh | Không | Testcontainers/RDBMS thật |
| Broker redelivery/rebalance/ack | Mock publisher không chứng minh | Không | Kafka/RabbitMQ test thật |
| Cache TTL/eviction/failover | Mock map không chứng minh | Không | Redis thật với TTL/fault |
| Thông điệp phát ra trùng khi retry | Có thể assert lời gọi | Đếm HTTP request | Kiểm tra idempotency và side effect phía đích |
| Hiệu năng, quota, backpressure | Hầu như không | Giúp mô phỏng vài tình huống | Load/staging/production telemetry |

Bảng cho thấy mock **không vô ích**: đây vẫn là lớp nhanh nhất để khóa hành vi mapper, nhánh lỗi và chính sách retry. Vấn đề nảy sinh khi dùng kết quả của một lớp để kết luận về lớp khác.

## 4. Ví dụ Spring Boot: cùng một adapter qua mock và socket thật

Giả sử hợp đồng của API Inventory công bố:

- `GET /stocks/{sku}` trả `200 application/json` với `sku` (string), `available` (integer không âm).
- `404` nghĩa là SKU không tồn tại.
- `429` có thể mang `Retry-After`, phản ánh giới hạn tốc độ.
- Trường bổ sung có thể xuất hiện nhưng các trường bắt buộc không được tự biến mất.

Lớp adapter tối giản:

~~~java
import org.springframework.web.client.RestClient;

// Spring Framework 6.1+; minh họa dùng trong Spring Boot hỗ trợ RestClient.
record Stock(String sku, int available) {}

public final class InventoryGateway {
    private final RestClient client;

    public InventoryGateway(RestClient client) {
        this.client = client;
    }

    public Stock getStock(String sku) {
        return client.get()
                .uri("/stocks/{sku}", sku)
                .retrieve()
                .body(Stock.class);
    }
}
~~~

Adapter minh họa giả định hệ thống đã khai báo chính sách xử lý `404/429` ở lớp gọi phía trên; khi triển khai thật, cần ánh xạ lỗi thành kiểu nghiệp vụ, validate trường quan trọng, timeout và retry phù hợp. Trường `available` kiểu `int` trong DTO có nguy cơ che sự khác nhau giữa `null` và `0` tùy cách deserialization. Với hợp đồng bắt buộc, ưu tiên kiểu `Integer`, validation rõ ràng hoặc custom mapper, rồi test dữ liệu thiếu/`null`.

### 4.1. Unit/integration hẹp với MockRestServiceServer

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class InventoryGatewayMockTest {

    @Test
    void mapsStockFromExpectedJson() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl("http://inventory.invalid");
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        InventoryGateway gateway = new InventoryGateway(builder.build());

        server.expect(requestTo(
                "http://inventory.invalid/stocks/SKU-1"))
              .andExpect(method(HttpMethod.GET))
              .andRespond(withSuccess(
                  "{\"sku\":\"SKU-1\",\"available\":12}",
                  MediaType.APPLICATION_JSON));

        Stock stock = gateway.getStock("SKU-1");

        assertThat(stock).isEqualTo(new Stock("SKU-1", 12));
        server.verify();
    }
}
~~~

Test này đảm bảo request mà `RestClient` tạo ra được matcher chấp nhận và response giả được Jackson chuyển thành `Stock`. Nó **không mở socket tới inventory.invalid** và không chứng minh provider thực tế hỗ trợ đúng URL hay response đó.

Để tránh test chỉ kiểm tra những gì chính mock vừa dựng, thêm trường hợp âm: body thiếu `available`, `available=null`, kiểu dữ liệu sai, enum mới, `Content-Type` khác dự kiến và status lỗi. Khi cần kiểm tra dữ liệu đúng hợp đồng, dùng JSON Schema/OpenAPI validation hoặc logic kiểm tra bắt buộc ở boundary.

### 4.2. HTTP mock server để kiểm tra transport

Cũng dùng `InventoryGateway`, nhưng lần này gọi tới **MockWebServer** trên loopback. Thông điệp đi qua HTTP client và socket thật:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}
~~~

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

class InventoryGatewayWireTest {

    @Test
    void sendsRequestAcrossActualHttpSocket() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "application/json")
                    .setBody("{\"sku\":\"SKU-1\",\"available\":12}"));
            server.start();

            HttpClient httpClient = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(1))
                    .build();
            JdkClientHttpRequestFactory factory =
                    new JdkClientHttpRequestFactory(httpClient);
            factory.setReadTimeout(Duration.ofSeconds(2));

            InventoryGateway gateway = new InventoryGateway(
                    RestClient.builder()
                              .baseUrl(server.url("/").toString())
                              .requestFactory(factory)
                              .build());

            Stock actual = gateway.getStock("SKU-1");

            assertThat(actual).isEqualTo(new Stock("SKU-1", 12));
            RecordedRequest request =
                    server.takeRequest(1, TimeUnit.SECONDS);
            assertNotNull(request);
            assertEquals("GET", request.getMethod());
            assertEquals("/stocks/SKU-1", request.getPath());
        }
    }
}
~~~

HTTP mock server cho phép kiểm tra request thực sự qua TCP, cách HTTP client nhận header/body, timeout, connection reuse và nhiều dạng response mà `MockRestServiceServer` không đi qua. Nhưng **server vẫn trả dữ liệu mà test tự định nghĩa**; đây chưa phải một bài xác nhận hợp đồng với provider thật.

Có thể bổ sung các ca dùng MockWebServer/WireMock để trả `429` có `Retry-After`, `503` rồi `200`, body lỗi, response chậm, kết nối bị đóng giữa chừng. Nếu phải kiểm tra DNS, TLS, proxy, firewall hoặc stale pooled connection, dựng đúng môi trường transport bằng HTTP test server có TLS hoặc Toxiproxy/Testcontainers, rồi xác minh toàn bộ request/response và metric.

## 5. Đưa provider thật vào vòng xác minh hợp đồng

Một bộ **consumer-driven contract test** cho phép consumer công bố interaction mình phụ thuộc vào: request, status, header, cấu trúc body và các ví dụ dữ liệu. Với công cụ như **Pact**, consumer sinh pact file, còn phía provider chạy verification trên code của chính provider.

~~~mermaid
flowchart LR
    U["Consumer test"] --> P["Pact / Contract artifact"]
    P --> V["Provider verification"]
    V --> S["Provider code + test state"]
    V --> R["Kết quả tương thích"]
    R --> C["CI / deploy gate"]
    C --> I["Sandbox integration test"]
~~~

### Một chu kỳ hợp đồng đúng nghĩa

1. **Consumer định nghĩa nhu cầu thật**: chỉ trường nó sử dụng, status/error bắt buộc, headers, cách xác thực và các tình huống nghiệp vụ.
2. **Provider chạy verification**: kiểm tra các interaction với code hiện tại, setup trạng thái phù hợp cho từng ca (SKU tồn tại, SKU hết hàng, SKU không tồn tại, bị quota).
3. **Công bố kết quả và phiên bản**: gắn kết quả với consumer/provider version hoặc commit để CI quyết định tính tương thích.
4. **Kiểm thử sandbox**: kiểm tra môi trường gồm auth, routing, network, DB, rate limit và cấu hình thực tế.
5. **Quan sát khi phát hành**: theo dõi lỗi hợp đồng, deserialization, status không lường trước và tỷ lệ request thất bại.

**Consumer contract không thay cho toàn bộ hợp đồng provider.** Nếu consumer chưa biết về `429` thì pact có thể không có interaction đó. Nếu provider verification dùng repository giả và trạng thái hoàn toàn nhân tạo, nó cũng chưa chứng minh giao dịch/concurrency của provider chạy đúng trên database thật.

### Phân loại thay đổi tương thích

| Thay đổi phía provider | Rủi ro và cách kiểm chứng |
| --- | --- |
| Thêm trường JSON tùy chọn | Thường tương thích nếu consumer bỏ qua trường không dùng; vẫn kiểm tra strict deserializer |
| Xóa hoặc đổi kiểu trường bắt buộc | Thường phá vỡ consumer đang dùng; contract test phải fail |
| `null` thay cho giá trị bắt buộc | Có thể qua deserializer nếu dùng primitive default; cần validate miền |
| Đổi tên endpoint, path parameter, enum hoặc status | Cần đối chiếu contract và policy phân loại lỗi |
| Đổi `200` trả dữ liệu thành `202` xử lý bất đồng bộ | Thay đổi semantic: client phải poll/callback/reconcile |
| Đổi điều kiện trả `409` cho request lặp | Tác động idempotency; test với key đã dùng |
| Thêm API quota/rate limit | Có thể không đổi schema nhưng phá hành vi retry/throughput |
| Đổi dữ liệu phân trang, sort mặc định | Có thể gây thiếu/trùng khi consumer dùng cursor/offset |
| Đổi event schema hoặc key distribution trên broker | Ảnh hưởng consumer compatibility, ordering và partition assignment |

Một thay đổi “không phá schema” chưa chắc giữ nguyên ý nghĩa nghiệp vụ. Ví dụ provider chuyển việc cập nhật tồn kho từ đồng bộ sang eventual consistency: response vẫn là `200`, nhưng consumer đọc ngay sau khi ghi có thể thấy trạng thái cũ.

## 6. Các lỗi biên mock thường che mất

### 6.1. Dữ liệu và serialization

- **Vắng mặt khác `null`, khác chuỗi rỗng, khác số 0.** Nếu trường bắt buộc biến mất mà DTO Java dùng primitive `int`, ứng dụng có thể nhận giá trị mặc định; validation cần rõ ràng.
- **Số thập phân**: dùng `BigDecimal` cho tiền/tỉ giá quan trọng, kiểm thử scale/rounding; mock có `12.50` chưa phát hiện provider gửi `"12.50"`.
- **Ngày giờ**: lệch timezone, DST, date-only vs timestamp, precision micro/nanosecond; dữ liệu sandbox có thể chỉ ở một múi giờ.
- **Unicode/encoding**: tên có dấu, emoji, ký tự escape, `Content-Type` với charset, newline trong chuỗi.
- **Danh sách rỗng và pagination**: không có dữ liệu, trang cuối, cursor hết hạn, kết quả đổi giữa hai trang.
- **Enum/field bổ sung**: policy với giá trị tương lai; không mặc định map unknown enum sang thành công.
- **Body bất thường**: HTTP 204 không có body, `200` với body rỗng, JSON malformed, payload lớn hoặc compression.
- **XML/SOAP**: namespace URI, QName, thứ tự theo XSD, SOAP Fault, cách server xử lý SOAPAction hoặc SOAP 1.2.

### 6.2. Semantics HTTP không được phản ánh bởi matcher đơn giản

| Chi tiết | Mock dễ bỏ qua | Hệ quả khi gọi thật |
| --- | --- | --- |
| `Content-Type` và `Accept` | Chỉ so JSON body | Provider trả 415/406 hoặc parser dùng sai codec |
| `Authorization`, scope, mTLS | Stub chấp nhận mọi request | Production trả 401/403 hoặc TLS handshake fail |
| Redirect 301/302/307/308 | Trả thẳng 200 | Client đổi method, mất header hoặc không theo redirect như mong đợi |
| `Retry-After`, quota per tenant | Mock chỉ trả một 503 | Retry storm, account bị throttle |
| `ETag`, `If-Match`, `If-None-Match` | Bỏ qua optimistic concurrency | Ghi đè dữ liệu cũ hoặc bỏ lỡ cập nhật |
| Idempotency key và thời gian giữ key | Mock trả 200 cho mọi lần POST | Tạo bản ghi trùng sau timeout |
| Timeout khi đã xử lý xong | Mock luôn trả response hoàn chỉnh | Client không biết server đã commit chưa |
| Connection reuse và keep-alive | Không có socket thật | Stale connection, pool exhaustion, đóng kết nối giữa request |
| Chunked, gzip, body bị ngắt | Body luôn nằm trong một chuỗi | Parse lỗi, treo chờ response, timeout |
| DNS, proxy, certificate | Không cấu hình trong test | Kết nối thất bại dù mapping đúng |

Nên kiểm thử **hợp đồng lỗi** riêng: cấu trúc lỗi, mã ứng dụng, body có thể thiếu, header tương quan, và cách client phân biệt lỗi vĩnh viễn với lỗi tạm thời. Đừng viết `catch (Exception)` rồi retry mọi lỗi: với hợp đồng dữ liệu sai, retry chỉ làm tăng tải và che nguyên nhân.

### 6.3. Timeout và thành công không rõ ràng

Giả sử consumer gọi:

~~~text
POST /reservations
Idempotency-Key: order-1024-reserve
Content-Type: application/json

{"orderId":"ORD-1024","sku":"SKU-1","quantity":1}
~~~

Provider đã commit reservation, nhưng kết nối mất trước khi response về. Từ góc nhìn client, chỉ có timeout. Nếu mock mô phỏng bằng `throw new SocketTimeoutException()` **trước khi** ghi trạng thái giả, bài test có thể chứng minh retry không lỗi, nhưng chưa kiểm tra trường hợp nguy hiểm nhất là **side effect đã xảy ra**.

Một test có giá trị cần:

1. Đặt provider giả lập có **state store**: request đầu tiên ghi reservation và chủ động cắt response.
2. Client retry với **cùng idempotency key**, hoặc tra cứu trạng thái theo ID giao dịch.
3. Provider trả cùng kết quả/nhận diện request lặp theo hợp đồng.
4. Assert chỉ **một reservation** tồn tại, dù số HTTP request lớn hơn một.
5. Chạy lại kịch bản ở provider sandbox để xác nhận chính sách giữ key và hành vi response của nhà cung cấp.

Nếu provider không cung cấp idempotency/reconciliation, phải làm rõ giới hạn bảo đảm. `@Transactional` ở ứng dụng consumer không thể rollback một tác động đã commit trong hệ thống HTTP khác.

## 7. Mock repository khác cơ sở dữ liệu thật

Một `Map<String, Order>` được dùng trong unit test không thể mô phỏng chính xác isolation level, ràng buộc unique, transaction rollback, deadlock, lock timeout, kiểu dữ liệu hoặc cách driver khôi phục connection.

Ví dụ test giả:

~~~java
// Mock repository: lần gọi save() được xác nhận.
verify(orderRepository).save(any(Order.class));
~~~

Test này không chứng minh đơn hàng được commit hoặc tính đúng khi hai request chạy đồng thời. Các ca nên có với PostgreSQL/MySQL/SQL Server thực (Testcontainers hoặc môi trường DB tương ứng):

- Hai request cùng business key tranh insert; chỉ một bản ghi hợp lệ được commit theo unique constraint.
- Transaction thất bại giữa chừng và rollback đúng cả business state + outbox trên **cùng DB transaction**.
- Ghi DB thành công rồi broker/API gửi thất bại; outbox còn `PENDING` và được retry.
- Pool mất kết nối hoặc DB failover; transaction cũ không bị coi là thành công giả, transaction mới có thể khởi động.
- SQL khác biệt giữa H2 và RDBMS thực: collation, lock, JSON types, date/time, upsert và isolation.

**H2 in-memory database là RDBMS hữu ích cho nhiều test**, nhưng không thay thế hoàn toàn chính loại database production nếu bài test dựa vào locking/transaction/SQL dialect. Với ranh giới quan trọng, ưu tiên engine và version tương thích qua container test.

## 8. Broker mock không chứng minh được giao hàng và commit

Một test:

~~~java
verify(kafkaTemplate).send(eq("orders.events"), any());
~~~

chỉ cho thấy code **đã gọi** phương thức gửi, chưa chứng minh broker xác nhận ghi log hoặc consumer đích xử lý thành công. Tương tự, mock `RabbitTemplate` không chứng minh publisher confirm, ack, redelivery và dead-lettering.

| Ranh giới | Điều test double giúp ích | Điều cần broker thật |
| --- | --- | --- |
| Producer Kafka | Mapping message/key, topic, lựa chọn header | Serialization, broker ack, timeout, idempotent producer, lỗi mạng |
| Consumer Kafka | Handler/mapper nghiệp vụ với event mẫu | Partition assignment, committed offset, rebalance, redelivery |
| RabbitMQ publisher | Mapping exchange/routing key | Publish confirm/return, unroutable message, exchange/binding |
| RabbitMQ consumer | Handler branch, business error policy | `ack/nack/requeue`, prefetch, dead-letter, consumer restart |
| Spring Integration adapter | Biến đổi payload/header, routing theo rule | Executor queue, errorChannel, ack/transaction boundary, scheduler concurrency |

Bài test tích hợp với Testcontainers Kafka/RabbitMQ cần chạy thử **crash sau side effect nhưng trước ack/commit**. Nếu record được giao lại, database phải chứng minh không tạo tác động nhân đôi theo khóa nghiệp vụ. Với Kafka, consumer group có thể đọc lại bản ghi chưa commit khi partition được giao lại. Với RabbitMQ, message chưa ack có thể được redeliver khi kết nối/channel đóng.

**Exactly-once semantics** trong một số luồng Kafka không tự biến SQL transaction hoặc HTTP call ngoài Kafka thành một giao dịch nguyên tử. Cần **inbox/dedup**, transactional outbox, idempotency key hoặc reconciliation.

## 9. Cache và bất đồng bộ: trạng thái thật khác bản đồ giả

Mock Redis thường được viết giống một `Map` ổn định, nhưng Redis thật có **TTL**, eviction, lỗi kết nối, serialization, memory pressure và các race quanh cache miss. Các test nên bao gồm:

- Key hết hạn đúng chính sách; application fallback sang DB hoặc giá trị stale có kiểm soát.
- Nhiều request cùng miss một key nóng; hệ thống không dồn hàng trăm query xuống DB (cache stampede).
- Cache update thất bại sau DB commit; hệ thống có invalidation/rebuild phù hợp.
- Cache không được xem là nơi lưu idempotency duy nhất nếu TTL/eviction ngắn hơn thời gian request có thể được gửi lại.

Với Spring Integration, sự khác nhau giữa **`DirectChannel`** (thường đồng bộ trong thread caller), **`ExecutorChannel`** (đẩy công việc sang executor) và **`QueueChannel`** (xếp hàng) có thể làm test unit đánh giá sai thời điểm hoàn thành. Một assertion “send() đã được gọi” không chứng minh handler phía sau đã commit DB hay ack message.

Nếu flow có async boundary, cần đo `accepted`, `in_flight`, `completed`, `failed` và `outstanding` theo **message ID**. Không đánh dấu thành công khi message mới nằm trong queue in-memory mà có thể mất khi process crash.

## 10. Kiểm thử tải, fault injection và hành vi sau phục hồi

Bên cạnh hợp đồng dữ liệu, provider thật có đặc tính tải: pool kết nối, giới hạn concurrency, rate limit, circuit breaker, retry backoff, timeout và thời gian để phục hồi sau outage.

Một test mock happy path không biết ứng dụng sẽ làm gì khi 200 thread cùng gọi một API chậm. Cần kết hợp:

- **Network fault injection** (Toxiproxy hoặc network shaping trong môi trường test) cho disconnect, packet delay, reset, bandwidth giới hạn, connection flap.
- **HTTP fault server** cho 429/503, response rỗng, malformed payload, `Retry-After`, body chậm hoặc mất response sau side effect.
- **Load test** với nhiều producer/consumer và nhiều replica, rate/concurrency được kiểm soát.
- **DB/broker integration** cho timeout, transaction rollback, redelivery, connection pool stale, rebalance và backlog.
- **Sandbox provider** để kiểm tra rate limit/quota, credential, certificate, test data và hành vi hoạt động thật.

Một vòng phục hồi điển hình:

~~~mermaid
sequenceDiagram
    participant App as Consumer Spring Boot
    participant Mock as Fault proxy / downstream
    participant Outbox as Durable outbox
    participant Target as Dịch vụ đích
    App->>Outbox: Lưu ý định gửi
    App->>Mock: Gọi outbound
    Mock--xApp: Timeout / 503
    Note over App,Outbox: Retry hữu hạn; giữ trạng thái PENDING
    Target-->>Mock: Downstream đã khỏe
    App->>Mock: Gửi lại có backoff + idempotency key
    Mock->>Target: Forward request
    Target-->>Mock: Phản hồi
    Mock-->>App: Kết quả
    App->>Outbox: Đánh dấu hoàn tất
~~~

Bài test chỉ PASS nếu số công việc đã chấp nhận có thể đối soát, backlog giảm về mức kỳ vọng, không có side effect trùng và hệ thống không rơi vào **retry storm** sau khi phục hồi. Các ngưỡng `p95/p99`, `time_to_resume`, `time_to_drain` cần lấy từ SLO thực tế.

Mock không thể xác nhận hệ thống đích có capacity dự kiến. Test load thực tế phải dùng môi trường được phép, dữ liệu kiểm soát và số lượng request hữu hạn để tránh làm gián đoạn provider.

## 11. Một chiến lược kiểm thử nhiều lớp có thể áp dụng

~~~mermaid
flowchart TB
    A["Unit test: mapping, policy, validate"] --> B["HTTP/SOAP mock: request và lỗi biên"]
    B --> C["Consumer contract + provider verification"]
    C --> D["Testcontainers: DB/cache/broker thật"]
    D --> E["Sandbox integration: provider thật"]
    E --> F["Canary + metrics ở production"]
    F --> G["Phát hiện case mới, bổ sung fixture/test"]
    G --> A
~~~

Chú ý sơ đồ mô tả **mức độ bằng chứng tăng dần**, không yêu cầu mọi bài test phải chạy tuần tự hoặc tất cả đều bắt buộc trong từng pull request.

### 11.1. Phân bổ theo pipeline

| Thời điểm | Kiểm thử nên ưu tiên | Tín hiệu chặn triển khai |
| --- | --- | --- |
| **Mỗi commit/PR** | Unit/mapper, mock HTTP/SOAP, schema validation, contract consumer tests | Sai mapping, request, error policy, schema |
| **Provider CI** | Provider verification theo các consumer đã công bố | Provider thay đổi phá interaction đã xác nhận |
| **Integration CI** | Testcontainers DB/broker/cache, HTTP fault injection, crash window | Sai transaction, commit, ack, timeout, idempotency |
| **Trước release** | Sandbox provider + auth/network/config thực, so version hợp đồng | Sai credential, endpoint, quota, SSL, behavior mismatch |
| **Định kỳ/staging** | Load, concurrency, recovery và failover | Pool cạn, backlog không giảm, retry storm |
| **Sau release** | Canary/telemetry/tracing và đối soát dữ liệu | Schema drift, status mới, error rate, side effect trùng |

Các vòng contract/provider test nên dùng **phiên bản có thể truy vết**: version consumer, version provider, ID contract, kết quả verification và môi trường. “Contract test đã xanh tháng trước” không chứng minh bản provider mới được deploy hôm nay vẫn tương thích.

### 11.2. Ưu tiên theo rủi ro

Không cần biến mọi nhánh nhỏ thành một bài end-to-end nặng. Với từng integration, phân loại rủi ro:

1. **Mức tác động**: lỗi có gây mất tiền, mất đơn, rò thông tin hoặc chặn phục vụ không?
2. **Khả năng thay đổi**: provider cập nhật hợp đồng thường xuyên hay API rất ổn định?
3. **Độ khó quan sát**: có trace, correlation ID, reconciliation và số liệu theo business key không?
4. **Khả năng hoàn tác**: thao tác GET thuần đọc hay POST gây side effect không thể đảo ngược?
5. **Tính phụ thuộc hạ tầng**: nhiều instance, pool, transaction, broker, cache hay chỉ là mapping đơn giản?

Nhánh rủi ro cao cần nhiều lớp test hơn: provider verification, real database/broker, failure injection và đối soát side effect.

## 12. Biến chênh lệch thực tế thành regression test

Một quy trình có ích khi mock xanh nhưng production lỗi:

1. **Ghi nhận bằng chứng an toàn**: operation, endpoint alias, request/response status, correlation ID, thời điểm, version provider, lỗi deserialization và header quan trọng (loại bỏ token/payload nhạy cảm).
2. **Phân loại chênh lệch**: hợp đồng dữ liệu, semantic nghiệp vụ, HTTP/transport, auth, trạng thái/đồng bộ, concurrency hoặc vận hành.
3. **Xác minh với provider**: response khác schema hay consumer đã giả định quá chặt; phân biệt bug với thay đổi có chủ đích.
4. **Tạo fixture/test tái hiện**: bổ sung ca dữ liệu, mã lỗi, timeout, idempotency hoặc fault injection tương ứng.
5. **Cập nhật contract**: khi là thay đổi hợp đồng, thống nhất version và quy tắc tương thích, thêm provider verification.
6. **Chạy kiểm thử ở lớp thích hợp**: đừng chỉ thêm mock cho lỗi transport nếu cần kiểm tra socket thật; đừng chỉ chạy end-to-end để sửa mapper đơn giản.
7. **Theo dõi sau sửa**: dashboard cho cùng loại lỗi, số lượng bản ghi được đối soát và tác động nghiệp vụ thực tế.

Ví dụ lỗi production: sau deploy, consumer không đọc được `{"available":null}`, dù mọi mock trước đó trả số. Regression phù hợp gồm: fixture `null`, validation ở adapter trả lỗi hợp đồng có ngữ cảnh, contract/provider verification khẳng định liệu `null` có được phép, và test phía downstream đảm bảo đơn hàng không bị đặt khi tồn kho chưa xác định.

### Anti-pattern cần tránh

| Anti-pattern | Vì sao dễ tạo tin cậy giả | Cách sửa |
| --- | --- | --- |
| Mock mọi repository/HTTP/broker rồi gọi đó là end-to-end | Không đi qua transaction, protocol, state thực | Bổ sung Testcontainers hoặc môi trường tích hợp |
| Stub response theo DTO hiện tại của consumer | Test đồng thuận với giả định, che schema drift | Dùng hợp đồng provider được quản lý phiên bản |
| Chỉ kiểm tra HTTP 200 | Bỏ status/error body, retry, timeout và semantic | Ma trận success + lỗi + boundary + recovery |
| Assert raw JSON/XML string toàn bộ | Dễ fail vì formatting/thứ tự field vô nghĩa | So theo schema, JSON path, XML namespace/QName |
| Dùng fixture chỉ toàn dữ liệu đẹp | Không bắt `null`, Unicode, outlier, pagination, malformed | Thêm partition dữ liệu và negative cases |
| Chỉ verify `send()` được gọi | Không chứng minh broker ack hoặc side effect | Test publish/consume với broker thật và idempotency |
| Test chỉ thấy kết nối phục hồi | Có thể bỏ backlog, retry storm, duplicate | Đối soát accepted/completed/outstanding |
| Retry mọi exception | Lặp lỗi vĩnh viễn, tăng tải, trùng nghiệp vụ | Phân loại lỗi, budget/backoff và khóa idempotency |
| Chạy staging nhưng dữ liệu toàn mock | Dễ che ràng buộc/khác biệt state thật | Test bằng provider test state được kiểm soát |
| Bỏ qua kết quả contract test khi deploy | CI xanh không bảo vệ version đang phát hành | Gắn verification với artifact/deployment |

## 13. Bài thực hành: đánh giá mức tin cậy của một tích hợp Inventory

Một luồng mẫu: Spring Boot nhận đơn hàng, gọi API giữ hàng `POST /reservations`, ghi kết quả vào PostgreSQL, phát sự kiện `StockReserved` lên Kafka và cập nhật cache Redis.

### Bước 1: Viết bản đồ hợp đồng

Xác định request/response hợp lệ, schema, mã `200/201/202/400/404/409/429/503` (chỉ dùng những mã provider thật sự công bố), idempotency key, correlation ID, timeout, quy tắc retry và eventual consistency. Ghi rõ nguồn cho từng giả định.

### Bước 2: Kiểm thử ở cấp adapter

Dùng `MockRestServiceServer` để kiểm tra URI, header, JSON serializer, mapper lỗi. Dùng MockWebServer để kiểm tra HTTP request qua socket, response chậm và status/header. Cả hai loại test phải có ca âm.

### Bước 3: Kiểm tra hợp đồng với provider

Tạo consumer contract cho `reservation accepted`, `duplicate key`, `out of stock` và `rate limited` khi nằm trong thỏa thuận. Provider chạy verification với dữ liệu/test state phù hợp. Kiểm chứng ít nhất một luồng trên sandbox có TLS/auth thật.

### Bước 4: Kiểm thử database và broker thật

Dùng Testcontainers PostgreSQL/Kafka/Redis. Kiểm tra unique key, rollback, outbox, broker ack, redelivery, cache expiration và side effect khi restart. Cố ý crash sau DB commit nhưng trước ack để chứng minh chống xử lý trùng.

### Bước 5: Tiêm lỗi và tải

Cho provider trả `503` và `429`, sau đó phục hồi. Cắt kết nối khi server đã xử lý POST nhưng chưa trả kết quả. Chạy nhiều request đồng thời với cùng key và các key khác nhau. Xác nhận backoff, queue capacity, idempotency, SLO và backlog sau hồi phục.

### Bước 6: Đối soát kết quả

Theo từng `orderId`/`eventId`: một reservation hợp lệ có đúng trạng thái, business transaction có kết quả rõ, outbox đã phát hoặc còn được retry có kiểm soát, Kafka consumer không tạo side effect trùng và cache không che dữ liệu cũ ngoài chính sách.

**Tiêu chí đạt:** nêu được lớp test nào chứng minh từng yêu cầu, không gán bằng chứng của mock cho provider thật, phát hiện ít nhất một trường hợp lỗi biên bằng test âm, và chứng minh dữ liệu cuối luồng chính xác sau retry/restart.

## 14. Checklist review trước khi công bố tích hợp

- [ ] Hợp đồng request/response, lỗi và hành vi nghiệp vụ có nguồn chuẩn và phiên bản.
- [ ] Các mock fixture được đối chiếu với OpenAPI/WSDL/schema/event contract của provider.
- [ ] Có kiểm thử thiếu trường, `null`, enum lạ, kiểu sai, Unicode, body rỗng, pagination/cursor.
- [ ] Có test status 4xx/5xx, `429`, `Retry-After`, timeout và response không chắc chắn.
- [ ] HTTP client thật đã được thử qua socket; TLS/DNS/proxy được kiểm tra ở môi trường phù hợp.
- [ ] Consumer contract được provider verify, kết quả gắn với version đang triển khai.
- [ ] Các transaction/unique key/locking quan trọng đã chạy trên database phù hợp với production.
- [ ] Broker/cache được kiểm tra với ack, redelivery, TTL, failover và schema evolution khi liên quan.
- [ ] Side effect của retry được bảo vệ bằng idempotency/reconciliation; outbox/inbox được test ở cửa sổ crash.
- [ ] Có test quá tải, phục hồi kết nối, backpressure và backlog theo SLO.
- [ ] Metrics/tracing giúp nhận diện schema drift, lỗi không biết trước và tác động nghiệp vụ lặp.
- [ ] Sự cố thực tế được chuyển thành regression test ở đúng lớp và cập nhật contract nếu cần.

**Kết luận:** Mock giúp phát hiện lỗi nhanh ở những hành vi đã mô tả; dịch vụ thật còn có **trạng thái, giao thức, tài nguyên, concurrency và quy tắc vận hành** mà mock có thể bỏ sót. Đối chiếu có hệ thống qua schema, provider verification, HTTP transport, Testcontainers, sandbox và số liệu sau triển khai là cách chuyển từ “mock xanh” sang bằng chứng đáng tin cậy rằng luồng tích hợp Spring Boot hoạt động đúng cả ở các lỗi biên.
