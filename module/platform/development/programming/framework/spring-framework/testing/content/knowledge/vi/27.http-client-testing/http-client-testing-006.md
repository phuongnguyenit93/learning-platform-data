# ExpectedCount, thứ tự yêu cầu và verify

Khi kiểm thử một HTTP client trong Spring, ta thường cần xác nhận client gửi đúng request, gửi request đúng số lần, tuân theo thứ tự cần thiết và không phát sinh lời gọi ngoài dự kiến. Với `RestTemplate` hoặc `RestClient`, Spring Test cung cấp `MockRestServiceServer` để mô phỏng server từ xa và khai báo các kỳ vọng cho từng request.

Ba khái niệm trong bài liên kết chặt chẽ với nhau:

- **ExpectedCount** quy định một request được phép hoặc bắt buộc xuất hiện bao nhiêu lần.
- **Thứ tự yêu cầu** xác định các expectation phải được khớp theo đúng trình tự khai báo hay có thể xuất hiện theo bất kỳ thứ tự nào.
- **verify()** xác nhận các expectation đã được đáp ứng sau khi client thực hiện công việc.

Hiểu đúng ba phần này giúp test HTTP client kiểm tra được cả hành vi bình thường lẫn những lỗi như gọi API lặp quá nhiều, thiếu request, gọi sai thứ tự hoặc quên xác nhận các request đã khai báo.

## 1. MockRestServiceServer dùng để làm gì?

`MockRestServiceServer` là công cụ của Spring Test để kiểm thử mã gọi HTTP ra bên ngoài mà không cần kết nối tới dịch vụ thật. Nó gắn một request factory giả lập vào HTTP client, nhận request do client tạo ra, so khớp với các expectation và trả response do test định nghĩa.

Luồng xử lý:

~~~text
Test
 |
 | khai báo request expectation và response giả lập
 v
MockRestServiceServer
 ^
 | request được gửi bởi HTTP client
 |
RestTemplate / RestClient
 |
 v
Code ứng dụng gọi API bên ngoài
~~~

Ví dụ, một service gọi API catalog để lấy thông tin sản phẩm. Test có thể:

1. Khai báo rằng request GET phải tới URI cụ thể.
2. Xác nhận HTTP method và header.
3. Trả về JSON giả lập.
4. Gọi service đang kiểm thử.
5. Xác nhận kết quả service.
6. Gọi `verify()` để chắc chắn request đã được gửi đúng như kỳ vọng.

Mock server chỉ thay thế phần giao tiếp HTTP. Nó không tự kiểm tra logic nghiệp vụ của service; test vẫn cần assertion cho giá trị mà service trả về.

## 2. Khởi tạo MockRestServiceServer

### Với RestTemplate

Tạo RestTemplate, sau đó bind mock server vào instance đó:

~~~java
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

RestTemplate restTemplate = new RestTemplate();

MockRestServiceServer mockServer =
    MockRestServiceServer.bindTo(restTemplate).build();
~~~

Sau khi bind, các request do RestTemplate gửi sẽ được xử lý bởi mock server. Không cần dựng HTTP server hoặc mở port thật.

Một test hoàn chỉnh:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

class CatalogClientTests {

    @Test
    void loadsProduct() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer mockServer =
            MockRestServiceServer.bindTo(restTemplate).build();

        mockServer.expect(requestTo("https://catalog.example.test/products/42"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                """
                {"id":42,"name":"Spring Guide"}
                """,
                MediaType.APPLICATION_JSON
            ));

        String body = restTemplate.getForObject(
            "https://catalog.example.test/products/42",
            String.class
        );

        assertThat(body).contains("Spring Guide");
        mockServer.verify();
    }
}
~~~

Trong ví dụ, `expect(...)` đăng ký một expectation. `andExpect(...)` bổ sung các điều kiện cần đúng cho request đó. `andRespond(...)` định nghĩa response giả lập mà client sẽ nhận khi request khớp.

### Với RestClient

Spring Framework 6.1 bổ sung khả năng bind `MockRestServiceServer` vào `RestClient.Builder`. Cần bind trước khi build RestClient:

~~~java
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://catalog.example.test");

MockRestServiceServer mockServer =
    MockRestServiceServer.bindTo(builder).build();

RestClient restClient = builder.build();
~~~

Test có thể khai báo expectation và gọi RestClient:

~~~java
mockServer.expect(requestTo("https://catalog.example.test/products/42"))
    .andRespond(withSuccess(
        """
        {"id":42,"name":"Spring Guide"}
        """,
        MediaType.APPLICATION_JSON
    ));

String body = restClient.get()
    .uri("/products/42")
    .retrieve()
    .body(String.class);

assertThat(body).contains("Spring Guide");
mockServer.verify();
~~~

Với RestClient có base URL, request matcher có thể dùng URI tương đối theo cách builder đã cấu hình. Nếu cần xác nhận URI tuyệt đối, hãy dùng URI matcher phù hợp với dạng URI mà request thực tế tạo ra.

## 3. ExpectedCount là gì?

`ExpectedCount` nằm trong package:

~~~java
import org.springframework.test.web.client.ExpectedCount;
~~~

Nó mô tả số lần một expectation có thể được khớp. Có thể truyền ExpectedCount vào overload của `expect(...)`:

~~~java
mockServer.expect(ExpectedCount.times(2), requestTo("/inventory/42"))
    .andRespond(withSuccess("available", MediaType.TEXT_PLAIN));
~~~

Các factory method thường dùng:

| Factory method | Số lần request được chấp nhận | Khi sử dụng |
|---|---:|---|
| `ExpectedCount.once()` | Chính xác 1 lần | Request phải xuất hiện đúng một lần. |
| `ExpectedCount.times(n)` | Chính xác n lần | Một request phải được gửi đúng số lần xác định. |
| `ExpectedCount.manyTimes()` | Ít nhất 1 lần, không giới hạn trên | Request có thể lặp nhiều lần và ít nhất phải xuất hiện một lần. |
| `ExpectedCount.min(n)` | Ít nhất n lần | Xác nhận số lần gọi đạt ngưỡng tối thiểu. |
| `ExpectedCount.max(n)` | Tối đa n lần, có thể là 0 | Giới hạn số lần gọi được phép. |

Ví dụ:

~~~java
ExpectedCount.once();       // 1 lần
ExpectedCount.times(3);     // đúng 3 lần
ExpectedCount.manyTimes();  // ít nhất 1 lần
ExpectedCount.min(2);       // từ 2 lần trở lên
ExpectedCount.max(4);       // không quá 4 lần
~~~

Với `times(n)`, số lần thực tế phải bằng n. Nếu request chỉ xuất hiện một lần trong khi kỳ vọng hai lần, `verify()` sẽ thất bại. Nếu request xuất hiện nhiều hơn số lần cho phép, mock server sẽ báo lỗi ngay khi request vượt quá expectation.

## 4. Dùng ExpectedCount để kiểm tra request lặp

Một service có thể cần gọi cùng endpoint nhiều lần, chẳng hạn đọc từng trang dữ liệu hoặc thử lại một request theo chính sách retry.

Ví dụ client gọi endpoint inventory hai lần:

~~~java
mockServer.expect(
        ExpectedCount.times(2),
        requestTo("https://inventory.example.test/items/42")
    )
    .andExpect(method(HttpMethod.GET))
    .andRespond(withSuccess(
        """
        {"itemId":42,"available":true}
        """,
        MediaType.APPLICATION_JSON
    ));

inventoryClient.loadItem(42);
inventoryClient.loadItem(42);

mockServer.verify();
~~~

Một expectation có ExpectedCount bằng hai sẽ tiếp nhận hai request khớp với matcher đã khai báo. Không cần viết hai expectation giống hệt nhau chỉ để mô tả cùng một request lặp đúng hai lần.

Nếu muốn request xuất hiện ít nhất hai lần:

~~~java
mockServer.expect(
        ExpectedCount.min(2),
        requestTo("https://inventory.example.test/items/42")
    )
    .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
~~~

Nếu chỉ muốn cho phép tối đa hai lần:

~~~java
mockServer.expect(
        ExpectedCount.max(2),
        requestTo("https://inventory.example.test/items/42")
    )
    .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
~~~

Lưu ý: `max(2)` không yêu cầu request phải xuất hiện. Nó chỉ đặt giới hạn trên. Nếu cần bảo đảm có ít nhất một lần gọi, dùng `once()`, `times(n)` với n lớn hơn 0, `manyTimes()` hoặc `min(n)` tùy hợp đồng.

### Kiểm tra không được gọi một endpoint

Nếu test không khai báo expectation cho một endpoint, request bất ngờ tới mock server sẽ không khớp với expectation nào và bị báo lỗi. Vì vậy, với trường hợp không được gọi API, thường chỉ cần không khai báo expectation cho request đó và thực thi hành vi cần kiểm tra.

Ví dụ, nhánh cache hit không nên gọi remote service:

~~~java
mockServer.expect(requestTo("/health"))
    .andRespond(withSuccess("ok", MediaType.TEXT_PLAIN));

catalogService.getCachedProduct(42);

// Nếu code bất ngờ gọi catalog API, mock server sẽ báo request không được mong đợi.
mockServer.verify();
~~~

Ở ví dụ này, expectation duy nhất là request health nếu test có chủ ý gọi nó. Nếu nhánh cache không cần bất kỳ request nào, không đăng ký expectation; một lời gọi bất ngờ tới mock server sẽ thất bại ngay.

## 5. Một expectation gồm matcher và response

Một expectation thường có ba phần:

~~~java
mockServer.expect(ExpectedCount.once(), requestTo("/products/42"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("X-Client", "catalog"))
    .andRespond(withSuccess(
        """
        {"id":42,"name":"Spring Guide"}
        """,
        MediaType.APPLICATION_JSON
    ));
~~~

| Phần | Vai trò |
|---|---|
| `expect(count, matcher)` | Khai báo số lần và điều kiện nhận diện request. |
| `andExpect(matcher)` | Thêm điều kiện về method, header, query, body hoặc thuộc tính request. |
| `andRespond(creator)` | Định nghĩa response trả về cho client. |

Các request matcher thường dùng:

~~~java
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
~~~

| Matcher | Kiểm tra |
|---|---|
| `requestTo(uri)` | URI của request. |
| `method(HttpMethod.GET)` | HTTP method. |
| `header(name, value)` | Giá trị header. |
| `headerDoesNotExist(name)` | Header không được gửi. |
| `queryParam(name, values...)` | Query parameter. |
| `content().string(value)` | Request body dạng text. |
| `content().json(json)` | Request body JSON. |
| `content().formData(...)` | Form data. |

Response creator thường dùng:

~~~java
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;
~~~

| Response creator | Response giả lập |
|---|---|
| `withSuccess(body, mediaType)` | 200 OK với body. |
| `withStatus(status)` | Status tùy chọn. |
| `withBadRequest()` | 400 Bad Request. |
| `withSuccess()` | 200 OK không có body. |
| `withNoContent()` | 204 No Content. |
| `withServerError()` | 500 Internal Server Error. |
| `withException(exception)` | Lỗi I/O ở tầng request execution. |

## 6. Thứ tự request mặc định

Theo mặc định, `MockRestServiceServer` yêu cầu các expectation được đáp ứng theo thứ tự khai báo. Request đầu tiên phải khớp expectation đầu tiên, request tiếp theo phải khớp expectation tiếp theo, và cứ như vậy.

Ví dụ một client cần lấy access token trước rồi mới gọi API đơn hàng:

~~~java
mockServer.expect(requestTo("/oauth/token"))
    .andExpect(method(HttpMethod.POST))
    .andRespond(withSuccess(
        """
        {"access_token":"test-token"}
        """,
        MediaType.APPLICATION_JSON
    ));

mockServer.expect(requestTo("/orders"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("Authorization", "Bearer test-token"))
    .andRespond(withSuccess(
        """
        [{"id":101,"status":"PAID"}]
        """,
        MediaType.APPLICATION_JSON
    ));

orderClient.loadOrders();
mockServer.verify();
~~~

Test này kiểm tra thứ tự ở mức HTTP:

1. Client gọi token endpoint.
2. Mock server trả token.
3. Client dùng token trong Authorization header để gọi orders endpoint.
4. Mock server trả danh sách đơn hàng.

Nếu code gọi `/orders` trước `/oauth/token`, request không khớp expectation đang chờ và test thất bại. Đây là cách hữu ích để kiểm tra một quy trình mà thứ tự gọi remote API có ý nghĩa.

### Một expectation có thể được khớp nhiều lần

ExpectedCount cũng tham gia vào thứ tự. Nếu expectation đầu tiên yêu cầu hai lần, hai request phù hợp phải được xử lý trước khi expectation kế tiếp được xem là đến lượt:

~~~java
mockServer.expect(
        ExpectedCount.times(2),
        requestTo("/inventory/42")
    )
    .andRespond(withSuccess("available", MediaType.TEXT_PLAIN));

mockServer.expect(requestTo("/orders/101"))
    .andRespond(withSuccess("created", MediaType.TEXT_PLAIN));

orderClient.checkInventoryTwiceThenCreateOrder();
mockServer.verify();
~~~

Thứ tự khai báo ở đây mô tả một chuỗi: hai lần kiểm tra inventory, sau đó mới tạo order. Nếu thứ tự không phải yêu cầu nghiệp vụ, không nên vô tình phụ thuộc vào nó.

## 7. Bỏ qua thứ tự với ignoreExpectOrder(true)

Trong một số trường hợp, các request có thể được gửi theo thứ tự khác nhau nhưng tất cả đều phải xuất hiện. Ví dụ, service gọi hai API độc lập hoặc thực hiện các lời gọi song song. Khi đó, có thể yêu cầu mock server bỏ qua thứ tự expectation:

~~~java
MockRestServiceServer mockServer = MockRestServiceServer
    .bindTo(restTemplate)
    .ignoreExpectOrder(true)
    .build();
~~~

Sau đó khai báo các expectation:

~~~java
mockServer.expect(requestTo("/profile/42"))
    .andRespond(withSuccess(
        """
        {"id":42,"name":"An"}
        """,
        MediaType.APPLICATION_JSON
    ));

mockServer.expect(requestTo("/permissions/42"))
    .andRespond(withSuccess(
        """
        {"canEdit":true}
        """,
        MediaType.APPLICATION_JSON
    ));
~~~

Code có thể gọi profile trước permissions hoặc ngược lại. Mỗi request vẫn phải khớp với một expectation và mỗi expectation vẫn phải thỏa ExpectedCount khi gọi verify.

`ignoreExpectOrder(true)` thay đổi quy tắc khớp expectation, không tắt kiểm tra request. URI, method, header, body và số lần gọi vẫn được kiểm tra như đã khai báo.

API cấu hình bỏ qua thứ tự có từ Spring Framework 6.1. Với phiên bản cũ hơn, builder có thể không cung cấp phương thức này; hãy giữ expectation theo thứ tự hoặc nâng phiên bản framework theo dependency management của dự án.

### Khi nào không nên bỏ qua thứ tự?

Giữ thứ tự mặc định nếu:

- Request thứ hai cần dữ liệu từ response của request thứ nhất, như access token.
- Request sau chỉ hợp lệ khi request trước đã hoàn tất.
- Thứ tự gọi là một phần của hợp đồng cần kiểm tra.
- Muốn test phát hiện lỗi khi code đảo trình tự.

Chỉ bỏ qua thứ tự khi các request thực sự độc lập hoặc lịch thực thi không được đảm bảo. Nếu hai expectation có matcher quá giống nhau, việc bỏ qua thứ tự có thể làm test khó hiểu; nên dùng matcher phân biệt rõ bằng URI, method, query hoặc header.

## 8. verify() xác nhận điều gì?

`verify()` kiểm tra các expectation đã đăng ký có được đáp ứng đủ số lần hay không. Gọi nó sau khi code client đã thực hiện những hành động cần kiểm thử:

~~~java
catalogService.loadProduct(42);

mockServer.verify();
~~~

Nếu một expectation yêu cầu đúng một request nhưng client không gọi, verify thất bại. Nếu expectation yêu cầu hai lần nhưng chỉ có một lần, verify cũng thất bại.

Điều quan trọng:

- `expect(...)` chỉ đăng ký kỳ vọng, chưa gửi request.
- `andRespond(...)` chỉ cấu hình response giả lập, chưa thực thi client.
- `verify()` không tự gọi client và cũng không tạo request.
- Request không được mong đợi thường khiến mock server báo lỗi ngay khi client gửi request đó.
- `verify()` kiểm tra các kỳ vọng về số lần, giúp phát hiện những request còn thiếu.

Không nên bỏ qua verify chỉ vì test đã nhận được response mong muốn. Một client có thể trả đúng dữ liệu nhưng gọi một endpoint phụ quá ít hoặc quá nhiều lần. Verify giúp xác nhận giao tiếp HTTP đã diễn ra đúng như hợp đồng test.

## 9. verify(Duration) cho request bất đồng bộ

Nếu code gửi request từ một thread khác hoặc một tác vụ bất đồng bộ, gọi `verify()` ngay sau khi khởi động tác vụ có thể quá sớm. Request có thể chưa được gửi tại thời điểm verify chạy.

Ở các phiên bản Spring Framework có hỗ trợ, `verify(Duration timeout)` chờ tối đa khoảng thời gian đã cho để các expectation được đáp ứng:

~~~java
mockServer.verify(Duration.ofSeconds(2));
~~~

Ví dụ:

~~~java
import java.time.Duration;

CompletableFuture<Void> operation = orderClient.loadOrderAsync(42);

operation.join();
mockServer.verify(Duration.ofSeconds(2));
~~~

Nếu Future đã hoàn tất sau khi request HTTP hoàn tất, verify thông thường thường đã đủ. Nếu tác vụ nền được khởi chạy độc lập và test chưa có tín hiệu hoàn tất trực tiếp, verify với timeout có thể giúp chờ request đến mock server.

Không dùng timeout lớn để che giấu đồng bộ hóa sai. Nếu test có thể chờ Future, latch hoặc completion signal của tác vụ, hãy đồng bộ theo tín hiệu đó trước rồi verify. Timeout chỉ đặt giới hạn chờ; nó không làm cho tác vụ bất đồng bộ tự hoàn tất.

## 10. Ví dụ kiểm tra ExpectedCount và verify

Giả sử service đọc cấu hình remote một lần rồi đọc trạng thái health hai lần:

~~~java
class RemoteStatusService {

    private final RestTemplate restTemplate;

    RemoteStatusService(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    String loadConfiguration() {
        return restTemplate.getForObject(
            "/configuration",
            String.class
        );
    }

    void checkHealthTwice() {
        restTemplate.getForObject("/health", String.class);
        restTemplate.getForObject("/health", String.class);
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.DefaultUriBuilderFactory;

class RemoteStatusServiceTests {

    @Test
    void sendsExpectedRequests() {
        RestTemplate restTemplate = new RestTemplate();
        restTemplate.setUriTemplateHandler(
            new DefaultUriBuilderFactory("https://status.example.test")
        );
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(restTemplate).build();
        RemoteStatusService service = new RemoteStatusService(restTemplate);

        server.expect(once(), requestTo("https://status.example.test/configuration"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess("mode=test", MediaType.TEXT_PLAIN));

        server.expect(times(2), requestTo("https://status.example.test/health"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess("UP", MediaType.TEXT_PLAIN));

        assertThat(service.loadConfiguration()).isEqualTo("mode=test");
        service.checkHealthTwice();

        server.verify();
    }
}
~~~

Test khai báo rõ số lần cho từng endpoint. Nếu health chỉ được gọi một lần, verify báo thiếu một request. Nếu health được gọi ba lần, request vượt quá ExpectedCount sẽ làm test thất bại.

## 11. Kiểm tra thứ tự và số lần trong một kịch bản

Giả sử một client phải:

1. Lấy token một lần.
2. Đọc profile hai lần.
3. Gửi một request audit sau cùng.

Expectation:

~~~java
server.expect(ExpectedCount.once(), requestTo("/token"))
    .andRespond(withSuccess("{\"token\":\"t1\"}", MediaType.APPLICATION_JSON));

server.expect(ExpectedCount.times(2), requestTo("/profile"))
    .andRespond(withSuccess("{\"name\":\"An\"}", MediaType.APPLICATION_JSON));

server.expect(ExpectedCount.once(), requestTo("/audit"))
    .andRespond(withSuccess());

client.executeWorkflow();
server.verify();
~~~

Kịch bản trên kết hợp cả cardinality và thứ tự:

| Vị trí | Request | Số lần bắt buộc |
|---:|---|---:|
| 1 | `/token` | 1 |
| 2 | `/profile` | 2 |
| 3 | `/audit` | 1 |

Nếu profile chỉ được gọi một lần, verify phát hiện expectation chưa đủ. Nếu audit được gọi trước profile hoàn tất, thứ tự mặc định khiến request không khớp expectation hiện tại.

Nếu profile và audit độc lập, hãy dùng `ignoreExpectOrder(true)` thay vì dựa vào thứ tự tình cờ của thread.

## 12. Reset mock server giữa các giai đoạn

`reset()` xóa các expectation đã đăng ký và trạng thái request đã ghi nhận để mock server có thể được dùng cho một giai đoạn test tiếp theo:

~~~java
server.reset();

server.expect(requestTo("/next-step"))
    .andRespond(withSuccess("done", MediaType.TEXT_PLAIN));
~~~

Thông thường, nên tạo mock server mới cho mỗi test method để test độc lập và dễ đọc. `reset()` hữu ích khi một test có chủ đích kiểm tra nhiều giai đoạn khác nhau trên cùng client, hoặc khi fixture dùng chung cần xóa trạng thái giữa các giai đoạn.

Không gọi reset trước verify nếu vẫn cần xác nhận các expectation trước đó. Reset xóa thông tin mà verify cần kiểm tra; hãy verify xong giai đoạn hiện tại rồi mới reset.

## 13. Tổ chức verify trong JUnit

Có thể gọi `verify()` trực tiếp trong test:

~~~java
@Test
void loadsProduct() {
    // Khai báo expectation
    // Gọi service
    // Assertion kết quả
    mockServer.verify();
}
~~~

Hoặc đặt verify trong `@AfterEach` để mọi test trong lớp đều được kiểm tra:

~~~java
@AfterEach
void verifyMockServer() {
    mockServer.verify();
}
~~~

Cách dùng `@AfterEach` cần bảo đảm mỗi test đều khai báo đúng expectation và mock server được khởi tạo lại cho từng test. Nếu test thất bại giữa chừng, lỗi verify trong teardown có thể xuất hiện cùng lỗi ban đầu và làm log khó đọc hơn. Với test có nhiều nhánh hoặc nhiều giai đoạn, gọi verify tường minh ở cuối test thường giúp xác định chính xác giai đoạn nào chưa đáp ứng kỳ vọng.

Ví dụ dùng JUnit lifecycle:

~~~java
class CatalogClientTests {

    private RestTemplate restTemplate;
    private MockRestServiceServer server;

    @BeforeEach
    void setUp() {
        restTemplate = new RestTemplate();
        server = MockRestServiceServer.bindTo(restTemplate).build();
    }

    @AfterEach
    void verifyRequests() {
        server.verify();
    }
}
~~~

Không dùng cùng một mock server mutable giữa nhiều test chạy song song nếu các test có thể đăng ký hoặc tiêu thụ expectation của nhau. Mỗi test nên có client và mock server riêng.

## 14. ExpectedCount và retry

Một ứng dụng có thể retry khi dịch vụ từ xa trả lỗi tạm thời. ExpectedCount giúp xác nhận số lần gọi đúng theo chính sách retry.

Ví dụ service thực hiện tối đa ba lần gọi:

~~~java
// retryTemplate được cấu hình tối đa ba lần thử.
String body = retryTemplate.execute(context ->
    restTemplate.getForObject(
        "https://inventory.example.test/inventory/42",
        String.class
    )
);
~~~

Với chính sách tối đa ba lần thử, một lần gọi ban đầu cộng tối đa hai lần retry. Nếu mỗi lần thử thực hiện một HTTP request bằng RestTemplate hoặc RestClient, test có thể dùng `ExpectedCount.max(3)` để giới hạn số request. Nếu kịch bản bắt buộc phải retry đúng hai lần trước khi thành công, dùng `times(3)` và cấu hình response giả lập theo từng lần. Ví dụ trên minh họa một cơ chế retry bao quanh RestTemplate; MockRestServiceServer không thay thế transport của WebClient.

Ví dụ RestTemplate retry ở tầng service:

~~~java
server.expect(ExpectedCount.times(3), requestTo("https://inventory.example.test/inventory/42"))
    .andRespond(withServerError());
~~~

Nếu cần trả hai lỗi rồi mới thành công, có thể khai báo ba expectation cùng matcher, theo thứ tự:

~~~java
server.expect(requestTo("https://inventory.example.test/inventory/42"))
    .andRespond(withServerError());

server.expect(requestTo("https://inventory.example.test/inventory/42"))
    .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

server.expect(requestTo("https://inventory.example.test/inventory/42"))
    .andRespond(withSuccess(
        "{\"available\":true}",
        MediaType.APPLICATION_JSON
    ));
~~~

Test phải gọi code có chính sách retry rồi xác nhận kết quả cuối. Chỉ khai báo ba expectation không làm client tự retry; hành vi retry phải tồn tại trong code đang kiểm thử.

## 15. Lỗi thường gặp

### Quên gọi verify()

Test có thể chạy hết và assertion kết quả vẫn pass dù một expectation chưa được đáp ứng. Gọi `verify()` để xác nhận số lần request bắt buộc.

### Nhầm ExpectedCount với số response

ExpectedCount mô tả số lần request được khớp với expectation. Nó không phải số phần tử trong response body hoặc số lần một method Java được gọi độc lập với HTTP.

### Dùng once() cho request có thể retry

Nếu code được thiết kế retry, expectation once có thể làm test thất bại khi lần gọi thứ hai xuất hiện. Hãy khai báo số lần đúng theo chính sách retry cần kiểm tra.

### Dùng manyTimes() khi cần giới hạn số lần

manyTimes cho phép không giới hạn số lần sau khi đã có ít nhất một request. Nếu cần giới hạn trên, dùng max(n); nếu cần đúng số lần, dùng times(n).

### Cho rằng bỏ qua thứ tự sẽ bỏ qua mọi kiểm tra

ignoreExpectOrder(true) chỉ bỏ ràng buộc thứ tự. Request vẫn phải khớp URI, method, header, body và ExpectedCount.

### Đảo thứ tự expectation trong một workflow phụ thuộc

Nếu request B cần token hoặc ID từ response của request A, thứ tự là một phần của hành vi. Đừng bật ignoreExpectOrder chỉ để test dễ pass.

### Gọi verify quá sớm với request bất đồng bộ

Nếu request được gửi ở thread nền, verify ngay sau khi khởi chạy task có thể chạy trước request. Hãy chờ completion signal hoặc dùng verify với timeout phù hợp.

### Dùng chung mock server cho các test song song

Expectation và request history là trạng thái của mock server. Dùng chung instance có thể khiến test tiêu thụ expectation của nhau. Khởi tạo riêng theo test.

### Chỉ xác nhận request mà quên kết quả nghiệp vụ

MockRestServiceServer xác nhận giao tiếp HTTP. Test vẫn nên kiểm tra service đã parse response, xử lý lỗi và trả kết quả đúng.

## 16. Cách chọn ExpectedCount, thứ tự và verify

Khi viết test cho HTTP client:

1. Xác định mỗi endpoint phải được gọi bao nhiêu lần.
2. Dùng `once()`, `times(n)`, `manyTimes()`, `min(n)` hoặc `max(n)` đúng với hợp đồng.
3. Giữ thứ tự mặc định nếu request sau phụ thuộc request trước hoặc thứ tự là hành vi cần kiểm tra.
4. Dùng `ignoreExpectOrder(true)` khi các request độc lập và thứ tự không phải hợp đồng.
5. Khai báo matcher đủ rõ để phân biệt các request, nhất là khi bỏ qua thứ tự.
6. Dùng `andRespond(...)` để mô phỏng response thành công, lỗi HTTP hoặc lỗi I/O.
7. Gọi `verify()` sau khi client hoàn tất; với tác vụ bất đồng bộ, chờ tác vụ hoặc dùng `verify(Duration)` nếu phiên bản Spring hỗ trợ.
8. Kiểm tra riêng kết quả nghiệp vụ mà code client trả về.

`ExpectedCount` trả lời câu hỏi “request này được gọi bao nhiêu lần?”, thứ tự expectation trả lời “request nào phải xảy ra trước?”, còn `verify()` xác nhận các yêu cầu đã khai báo thực sự được đáp ứng. Kết hợp đúng ba cơ chế này giúp test HTTP client kiểm tra được số lần gọi, trình tự giao tiếp và việc hoàn tất toàn bộ workflow.
