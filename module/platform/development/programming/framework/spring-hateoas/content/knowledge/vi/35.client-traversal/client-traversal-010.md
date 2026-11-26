# Kiểm thử client traversal

Client traversal là quá trình client bắt đầu từ một URI gốc, đọc hypermedia link trong response và lần lượt theo các relation để đến resource cần thiết. Với Spring HATEOAS, `Traverson` hỗ trợ quy trình này ở phía client: nó gửi request, khám phá link theo relation, mở rộng URI template và chuyển representation cuối thành object hoặc giá trị JSONPath.

Kiểm thử client traversal cần xác nhận client thực sự đi theo các link server cung cấp. Một test tốt kiểm tra thứ tự request, relation được tìm thấy, query parameter được mở rộng, header `Accept` được gửi và dữ liệu cuối được đọc đúng. `MockRestServiceServer` có thể mô phỏng từng response HTTP để kiểm thử Traverson mà không cần khởi chạy server; test tích hợp với server thật giúp xác minh thêm đường đi qua controller, serializer và cấu hình hypermedia.

## 1. Client traversal khác gọi URL trực tiếp như thế nào?

Client gọi URL trực tiếp thường biết trước cấu trúc endpoint:

```java
String url = baseUrl + "/orders/" + orderId + "/payments";
```

Cách này khiến client phụ thuộc vào path, tên tham số và quy tắc định tuyến của server. Nếu server chuyển payments sang một service hoặc route khác, client phải được cập nhật.

Client traversal bắt đầu từ API root và sử dụng relation:

```text
GET /api
  └── rel="orders" → GET link orders
        └── embedded order self link → GET order
              └── rel="payments" → GET link payments
```

Client chỉ cần biết các relation mà nó hiểu và media type mà nó hỗ trợ. Đích cụ thể được lấy từ `href` trong từng response. Vì vậy, test nên phát hiện client nếu nó tự ghép URL hoặc bỏ qua relation do server công bố.

## 2. Các thành phần kiểm thử

Spring HATEOAS cung cấp một số API hữu ích cho client traversal:

| Thành phần | Vai trò trong client |
| --- | --- |
| `Traverson` | Bắt đầu từ URI gốc và cấu hình media type để gửi trong `Accept` |
| `follow(...)` | Chọn relation hoặc JSONPath trỏ đến link ở bước kế tiếp |
| `Hop` | Tùy chỉnh một bước traversal, ví dụ query parameter hoặc header riêng |
| `withTemplateParameters(...)` | Cung cấp giá trị để mở rộng URI template |
| `toObject(...)` | Thực hiện traversal và chuyển response cuối thành object hoặc giá trị JSONPath |
| `LinkDiscoverer` | Tìm link theo relation trong representation hypermedia |
| `MockRestServiceServer` | Giả lập HTTP response và xác nhận request do Traverson gửi |

`Traverson` nằm trong package `org.springframework.hateoas.client`. Các API client được tách khỏi API server từ Spring HATEOAS 1.0; khi viết import, dùng package `client` cho `Traverson`, `Hop` và `LinkDiscoverer`.

## 3. Cấu hình Traverson cơ bản

Tạo một `Traverson` với URI gốc và media type cần trao đổi:

```java
import java.net.URI;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

Traverson traverson = new Traverson(
        URI.create("https://api.example.test/api/"),
        MediaTypes.HAL_JSON);
```

`MediaTypes.HAL_JSON` yêu cầu client trao đổi representation HAL JSON. Traverson dùng media type này làm `Accept` khi gửi request. Nếu API dùng media type khác, hãy cấu hình media type tương ứng và bảo đảm client có message converter/link discoverer hỗ trợ nó.

Một traversal đơn giản theo relation `orders`:

```java
String label = traverson.follow("orders")
        .toObject("$.label");
```

Traverson gọi URI gốc, tìm link có relation `orders`, gửi request đến `href` của link đó rồi đánh giá JSONPath `$.label` trên representation cuối. Chuỗi `orders` là relation do API công bố, không phải tên path mà client tự suy ra.

## 4. Kiểm thử LinkDiscoverer độc lập

Trước khi kiểm thử cả chuỗi HTTP, có thể kiểm tra client có đọc được relation từ HAL representation hay không. `HalLinkDiscoverer` tìm link theo cấu trúc `_links`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.client.LinkDiscoverer;
import org.springframework.hateoas.mediatype.hal.HalLinkDiscoverer;

import static org.assertj.core.api.Assertions.assertThat;

class HalLinkDiscovererTest {

    private final LinkDiscoverer discoverer = new HalLinkDiscoverer();

    @Test
    void discoversTemplatedOrdersLink() {
        String representation = """
                {
                  "_links": {
                    "orders": {
                      "href": "https://api.example.test/orders{?status}",
                      "templated": true
                    }
                  }
                }
                """;

        Link link = discoverer.findLinkWithRel("orders", representation).orElseThrow();

        assertThat(link.isTemplated()).isTrue();
        assertThat(link.getVariableNames()).containsExactly("status");
        assertThat(link.getHref()).contains("/orders");
    }
}
```

Test này chỉ kiểm tra việc tìm link trong một representation có sẵn. Nó không gửi request HTTP và không xác minh rằng Traverson mở rộng template hoặc theo link đúng. Hãy dùng nó cho lỗi parsing/contract đơn giản, sau đó kiểm thử traversal ở mức HTTP.

Nếu relation có thể không tồn tại, dùng `findLinkWithRel(...)` để nhận `Optional<Link>` và kiểm tra trường hợp vắng mặt. `findRequiredLinkWithRel(...)` phù hợp khi relation là bắt buộc trong contract của representation đang kiểm thử.

## 5. Kiểm thử traversal bằng MockRestServiceServer

`MockRestServiceServer` gắn vào một `RestTemplate`, cho phép khai báo request mong đợi và response tương ứng. Có thể truyền `RestTemplate` đó cho Traverson qua `setRestOperations(...)`.

Ví dụ kiểm thử một luồng nhiều bước:

1. Gọi API root.
2. Theo relation `orders` và mở rộng biến `status=PAID`.
3. Từ collection, theo self link của phần tử đầu tiên.
4. Từ order, theo relation `payments`.
5. Đọc `currency` từ response payments cuối cùng.

```java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class OrderTraversalClientTest {

    private static final URI API_ROOT =
            URI.create("https://api.example.test/api/");

    @Test
    void followsRelationsFromRootToPayments() {
        RestTemplate restTemplate = new RestTemplate(
                Traverson.getDefaultMessageConverters(MediaTypes.HAL_JSON));

        MockRestServiceServer server = MockRestServiceServer
                .bindTo(restTemplate)
                .build();

        server.expect(requestTo(API_ROOT.toString()))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header("Accept", MediaTypes.HAL_JSON_VALUE))
                .andRespond(withSuccess("""
                        {
                          "_links": {
                            "orders": {
                              "href": "https://api.example.test/orders{?status}",
                              "templated": true
                            }
                          }
                        }
                        """, MediaTypes.HAL_JSON));

        server.expect(requestTo(
                        "https://api.example.test/orders?status=PAID"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess("""
                        {
                          "_embedded": {
                            "orders": [
                              {
                                "id": "ORD-42",
                                "_links": {
                                  "self": {
                                    "href": "https://api.example.test/orders/ORD-42"
                                  }
                                }
                              }
                            ]
                          }
                        }
                        """, MediaTypes.HAL_JSON));

        server.expect(requestTo("https://api.example.test/orders/ORD-42"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess("""
                        {
                          "id": "ORD-42",
                          "_links": {
                            "payments": {
                              "href": "https://api.example.test/orders/ORD-42/payments"
                            }
                          }
                        }
                        """, MediaTypes.HAL_JSON));

        server.expect(requestTo(
                        "https://api.example.test/orders/ORD-42/payments"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess("""
                        {
                          "currency": "VND",
                          "amount": 250000
                        }
                        """, MediaTypes.HAL_JSON));

        Traverson traverson = new Traverson(API_ROOT, MediaTypes.HAL_JSON)
                .setRestOperations(restTemplate);

        String currency = traverson.follow("orders")
                .withTemplateParameters(Map.of("status", "PAID"))
                .follow("$._embedded.orders[0]._links.self.href")
                .follow("payments")
                .toObject("$.currency");

        assertThat(currency).isEqualTo("VND");
        server.verify();
    }
}
```

`Traverson.getDefaultMessageConverters(MediaTypes.HAL_JSON)` cung cấp các converter mặc định cho media type HAL JSON. `setRestOperations(...)` cho phép dùng `RestTemplate` đã được gắn mock server. Các response được khai báo theo đúng thứ tự traversal, vì vậy `server.verify()` cũng xác nhận client đã gửi đủ request mong đợi.

`MockRestServiceServer` thay request factory của `RestTemplate` để kiểm tra request và trả response giả ngay trong test. Nó không mô phỏng socket, TLS, DNS hoặc các lỗi mạng ở transport layer. Nếu cần kiểm thử các tình huống mạng thực tế hơn, cân nhắc mock web server như MockWebServer hoặc WireMock.

Ví dụ dùng Java text block và `Map.of(...)`, phù hợp với Java 15 trở lên. Nếu dự án dùng Java cũ hơn, thay text block bằng chuỗi thông thường và `Map.of` bằng map mutable.

## 6. Kiểm thử query parameter của URI template

API root thường công bố link template thay vì một URL hoàn chỉnh:

```json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/orders{?status,page,size}",
      "templated": true
    }
  }
}
```

Client cung cấp giá trị khi traversal:

```java
String result = traverson.follow("search")
        .withTemplateParameters(Map.of(
                "status", "PAID",
                "page", 0,
                "size", 20))
        .toObject("$.label");
```

Khi kiểm thử, khai báo request mong đợi là URI đã mở rộng, ví dụ `/orders?status=PAID&page=0&size=20`. Không kiểm tra thứ tự query parameter nếu contract không yêu cầu thứ tự đó; URI có thể biểu diễn cùng tập tham số với thứ tự khác nhau. Nếu dùng `requestTo(...)` với chuỗi chính xác, hãy chọn cách mở rộng và encoding ổn định hoặc dùng request matcher tùy chỉnh để kiểm tra path và tập query parameter.

Đảm bảo tên biến trong map khớp với biến URI template server công bố. Nếu client gửi sai tên hoặc thiếu giá trị bắt buộc, request có thể không được mở rộng như mong đợi hoặc server trả lỗi. Test nên bao gồm trường hợp tham số hợp lệ, thiếu tham số và giá trị có ký tự cần URL encode.

## 7. Tùy chỉnh từng Hop bằng Hop

`withTemplateParameters(...)` áp dụng map tham số cho traversal. Khi mỗi bước cần tham số hoặc header khác nhau, dùng `Hop` để tùy chỉnh riêng một relation:

```java
import static org.springframework.hateoas.client.Hop.rel;

String label = traverson
        .follow(rel("orders").withParameter("projection", "summary"))
        .toObject("$.label");
```

Có thể gắn nhiều tham số vào cùng một hop:

```java
String result = traverson.follow(rel("orders")
        .withParameter("status", "PAID")
        .withParameter("projection", "summary"))
        .toObject("$.label");
```

`Hop` giúp tránh áp dụng cùng một map tham số cho mọi URI template trong toàn bộ traversal. Dùng nó khi từng relation có biến khác nhau hoặc khi cần kiểm soát request header theo bước.

## 8. Kiểm thử header và xác thực theo từng bước

Traverson cho phép gắn header vào traversal bằng `withHeaders(...)`. `Hop` cũng hỗ trợ header riêng cho một bước thông qua `header(...)` hoặc `withHeaders(...)`:

```java
import org.springframework.http.HttpHeaders;

HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);

String label = traverson.follow("orders")
        .withHeaders(headers)
        .toObject("$.label");
```

Nếu API yêu cầu header riêng cho một hop:

```java
String label = traverson.follow(rel("orders")
        .header("X-Tenant", "tenant-42"))
        .toObject("$.label");
```

Trong test với `MockRestServiceServer`, dùng `.andExpect(header(...))` để xác nhận header được gửi ở đúng request. Không ghi token thật vào fixture hoặc log; dùng token giả dành riêng cho test.

Nếu token chỉ được cấp cho một host, kiểm tra mọi `href` mà server công bố trước khi gửi credential. Client không nên chuyển bearer token đến một host không được tin cậy chỉ vì representation chứa link trỏ đến đó.

## 9. Dùng JSONPath để chọn link trong embedded resource

Không phải mọi bước traversal đều có relation trực tiếp ở cấp root. Với collection HAL, mỗi item thường nằm trong `_embedded`; client có thể dùng JSONPath để chọn self link của phần tử:

```java
record OrderView(String id, String status) {
}

EntityModel<OrderView> order = traverson
        .follow("orders")
        .follow("$._embedded.orders[0]._links.self.href")
        .toObject(new ParameterizedTypeReference<EntityModel<OrderView>>() {});
```

Ví dụ này yêu cầu các import:

```java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;
```

`follow("orders")` tìm relation `orders`; bước tiếp theo dùng JSONPath để lấy URL self của item đầu tiên; `toObject(...)` chuyển representation cuối thành `EntityModel<OrderView>`. Dùng `ParameterizedTypeReference` khi cần giữ thông tin generic mà `Class<T>` không thể biểu diễn.

Nếu collection rỗng, JSONPath trỏ đến phần tử `[0]` không tìm được link. Test cần chuẩn bị dữ liệu phù hợp hoặc kiểm tra nhánh collection rỗng riêng. Không nên coi vị trí phần tử đầu tiên là một định danh nghiệp vụ ổn định; nếu cần chọn item cụ thể, hãy lọc theo dữ liệu hoặc relation có ngữ nghĩa rõ ràng.

## 10. Kiểm thử relation không tồn tại và collection rỗng

Một traversal có thể thất bại nếu response không chứa relation mà client yêu cầu. Có thể kiểm tra representation trước bằng `LinkDiscoverer`:

```java
import org.springframework.hateoas.client.LinkDiscoverer;
import org.springframework.hateoas.mediatype.hal.HalLinkDiscoverer;

LinkDiscoverer discoverer = new HalLinkDiscoverer();

assertThat(discoverer.findLinkWithRel("payments", representation))
        .isEmpty();
```

Trong test độc lập, `representation` là chuỗi HAL JSON của response đang kiểm tra và cần import `assertThat` từ AssertJ.

Test nên phân biệt hai trường hợp:

- Relation không xuất hiện vì hành động không khả dụng hoặc resource không có quan hệ đó.
- Relation bắt buộc theo contract nhưng server vô tình bỏ sót.

Trường hợp đầu có thể là hành vi hợp lệ của domain. Trường hợp thứ hai là lỗi contract cần phát hiện. Đừng biến mọi relation thành bắt buộc nếu chúng chỉ xuất hiện trong một số trạng thái.

Với `Traverson`, test missing relation nên xác nhận client không gửi request đến một URL tự suy đoán. Thay vì dựa vào một exception cụ thể có thể khác theo phiên bản, kiểm tra rõ relation trước khi traversal hoặc xác nhận request không mong đợi không được phát ra.

## 11. Kiểm thử traversal với server thật

`MockRestServiceServer` kiểm thử client độc lập với server. Để kiểm tra cả controller, hypermedia converter và client trong một ứng dụng Spring Boot, có thể chạy ứng dụng trên cổng ngẫu nhiên:

```java
import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderTraversalIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void traversesApplicationLinks() {
        URI root = URI.create("http://localhost:" + port + "/api/");

        Traverson traverson = new Traverson(root, MediaTypes.HAL_JSON);

        String name = traverson.follow("orders")
                .follow("$._embedded.orders[0]._links.self.href")
                .toObject("$.customerName");

        assertThat(name).isNotBlank();
    }
}
```

Test này gửi request HTTP thật đến ứng dụng, nên kiểm tra được link mà controller thực tế tạo ra và khả năng client theo link đó. Dữ liệu test phải được khởi tạo trước để API root, collection và item có các relation tương ứng. Nếu ứng dụng yêu cầu authentication, cấu hình security test và truyền header qua `withHeaders(...)`.

`RANDOM_PORT` tránh xung đột cổng khi chạy song song. Không hard-code `localhost:8080` vì cổng thực tế do test server cấp qua `@LocalServerPort`.

## 12. Phân biệt kiểm thử client và kiểm thử server

Hai nhóm test có mục tiêu khác nhau:

| Kiểu test | Thành phần được kiểm tra | Ví dụ |
| --- | --- | --- |
| `LinkDiscoverer` unit test | Cách client đọc relation từ payload | Có tìm thấy `orders` trong `_links` không? |
| Traverson + `MockRestServiceServer` | Logic traversal và request client gửi | Có theo đúng link, mở rộng template và gửi header không? |
| `MockMvc` | Controller và response server trong Spring MVC | Server có tạo `_links` và `_embedded` đúng không? |
| Traverson + `RANDOM_PORT` | Client đi qua API đang chạy | Client có thể đi từ root đến resource cuối qua HTTP thật không? |

Không dùng `MockMvc` như thể nó là HTTP transport cho `Traverson`: Traverson dùng `RestOperations` để gửi request HTTP. Nếu muốn kiểm thử Traverson, dùng mock `RestOperations`/`MockRestServiceServer` hoặc một server HTTP đang chạy. Dùng MockMvc riêng để kiểm tra phía server.

## 13. Kiểm tra pagination traversal

Client thường duyệt collection phân trang bằng link `next`, không tự tăng `page`:

```java
String nextPageLabel = traverson.follow("orders")
        .follow("next")
        .toObject("$.label");
```

Test nên cung cấp response đầu có link `next`, response tiếp theo có dữ liệu trang sau và xác nhận client gửi request đến đúng `href`. Khi trang cuối không có `next`, client phải dừng thay vì tự tạo URL trang tiếp theo.

Nếu cần thu thập mọi trang, viết vòng lặp dựa trên sự hiện diện của relation `next`. Mỗi bước đọc response mới và khám phá link tiếp theo từ response đó. Tránh tính `page + 1` trong client vì cách phân trang có thể thay đổi sang cursor hoặc token.

## 14. Kiểm tra error response và giới hạn retry

Traversal có thể gặp lỗi HTTP ở bất kỳ hop nào: `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `429 Too Many Requests` hoặc lỗi máy chủ. Kiểm thử client nên xác định hành vi mong muốn cho từng loại lỗi.

- Với `401`, client có thể cần làm mới credential theo cơ chế xác thực đã cấu hình.
- Với `403`, client không nên tiếp tục gọi lại cùng hành động bằng credential không đủ quyền.
- Với `404`, resource hoặc link có thể đã hết hiệu lực; client nên quay lại resource cha hoặc khám phá lại trạng thái.
- Với `429` hoặc lỗi tạm thời, tôn trọng `Retry-After` nếu có và dùng backoff có giới hạn.
- Với lỗi `5xx`, chỉ retry thao tác phù hợp; không tự động lặp command có side effect nếu chưa có idempotency.

Trong `MockRestServiceServer`, có thể cấu hình response lỗi bằng `withStatus(...)` để kiểm tra exception/error handling của client. Không viết test chỉ xác nhận exception bị ném; hãy xác nhận client không tiếp tục traversal sai hoặc lặp request không an toàn.

## 15. Kiểm tra URL và bảo mật khi theo link

Hypermedia giúp client không phụ thuộc route, nhưng không có nghĩa client phải tin mọi URI trong response. Nếu API có thể trả link đến host khác, client cần chính sách cho phép host/scheme trước khi gửi credential hoặc dữ liệu nhạy cảm.

Các điểm nên kiểm tra:

- Chỉ dùng scheme được phép, thường là HTTPS trong production.
- Xác minh host đích theo allow-list khi credential được gửi tự động.
- Không chuyển bearer token hoặc cookie sang origin không đáng tin.
- Giới hạn số hop và thời gian request để tránh vòng lặp hoặc traversal kéo dài.
- Không ghi access token, dữ liệu cá nhân hoặc query nhạy cảm vào log.
- Xử lý redirect theo chính sách bảo mật của HTTP client.

Client traversal vẫn cần timeout, connection pool và giới hạn retry như mọi HTTP client khác. Không để một link vòng lặp hoặc một server phản hồi chậm làm treo toàn bộ tiến trình xử lý.

## 16. Lỗi thường gặp

**Hard-code path thay vì follow relation:** test vẫn chạy dù hypermedia contract bị hỏng. Dùng relation trong response làm điểm bắt đầu cho từng bước.

**Quên cấu hình media type:** client gửi `Accept` không đúng hoặc không có converter HAL. Khởi tạo Traverson với media type và converter phù hợp.

**Dùng MockMvc để thay thế HTTP transport của Traverson:** hai công cụ hoạt động ở hai tầng khác nhau. Dùng `MockRestServiceServer` hoặc server thật cho Traverson.

**Không khai báo mọi request mong đợi:** test có thể bỏ sót request thừa hoặc sai thứ tự. Dùng `MockRestServiceServer` và gọi `verify()`.

**Giả định query parameter luôn có thứ tự cố định:** cùng một tập tham số có thể được serialize theo thứ tự khác. Kiểm tra giá trị query thay vì chuỗi URI quá chặt.

**Dùng JSONPath đến item `[0]` mà không có fixture:** collection rỗng làm traversal thất bại. Chuẩn bị dữ liệu hoặc test riêng nhánh rỗng.

**Không phân biệt relation tùy chọn và relation bắt buộc:** link vắng mặt có thể là trạng thái hợp lệ. Ghi rõ semantics của relation trong contract.

**Theo link khác host rồi gửi credential:** có thể làm lộ token. Xác minh origin trước khi gắn header xác thực.

**Tự tạo link `next`:** client bị gắn với cơ chế pagination. Theo relation `next` do server trả về và dừng khi relation không còn.

## 17. Checklist kiểm thử client traversal

- Khởi tạo `Traverson` bằng API root và media type đúng.
- Xác nhận `Accept` header được gửi trong từng request.
- Dùng relation để khám phá link, không ghép URL từ path nội bộ.
- Kiểm thử URI template với giá trị và encoding thực tế.
- Dùng `Hop` khi từng bước cần parameter hoặc header riêng.
- Kiểm thử nhiều hop, bao gồm link trong `_embedded`.
- Dùng `LinkDiscoverer` để kiểm tra relation bắt buộc/tùy chọn.
- Gắn `MockRestServiceServer` vào `RestTemplate` và cấu hình HAL converters.
- Khai báo request theo đúng thứ tự và gọi `server.verify()`.
- Kiểm tra pagination qua `next` và trường hợp trang cuối.
- Kiểm tra lỗi xác thực, quyền, resource mất và lỗi tạm thời.
- Kiểm tra origin trước khi chuyển credential sang link khác host.
- Có ít nhất một integration test với server thật khi cần xác nhận toàn bộ luồng HTTP.

Kiểm thử client traversal xác nhận client sử dụng hypermedia contract như một bản đồ điều hướng do server cung cấp. Khi kết hợp `LinkDiscoverer`, `Traverson`, `MockRestServiceServer` và test tích hợp trên cổng ngẫu nhiên, nhóm phát triển có thể phát hiện lỗi relation, URI template, thứ tự hop, media type và bảo mật trước khi client phụ thuộc vào các endpoint cụ thể.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Client-side support / Traverson](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client.traverson)
- [Spring HATEOAS API – Traverson](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html)
- [Spring HATEOAS API – Traverson.TraversalBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.TraversalBuilder.html)
- [Spring HATEOAS API – LinkDiscoverer](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/LinkDiscoverer.html)
- [Spring HATEOAS API – Hop](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Hop.html)
- [Spring Framework Reference – MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html)
