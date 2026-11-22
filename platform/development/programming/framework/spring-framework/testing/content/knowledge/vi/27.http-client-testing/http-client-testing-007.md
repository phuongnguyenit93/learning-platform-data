# Reset kỳ vọng giữa các bài kiểm thử

## Vì sao cần reset MockRestServiceServer?

Khi kiểm thử HTTP client trong Spring, MockRestServiceServer cho phép khai báo những request mà client được phép gửi và response giả lập tương ứng. Mỗi kỳ vọng thường mô tả URL, HTTP method, header hoặc body của request, sau đó chỉ định response sẽ trả về.

Một RestTemplate hoặc RestClient.Builder có thể được tạo một lần rồi dùng chung trong nhiều test method. Nếu MockRestServiceServer cũng được tạo một lần và gắn với client đó, trạng thái của mock server có thể tồn tại qua nhiều test:

- Những kỳ vọng của test trước có thể còn chưa được thực hiện.
- Các request đã ghi nhận từ test trước có thể ảnh hưởng đến việc kiểm tra số lượng hoặc thứ tự request.
- Test sau có thể nhận lỗi do trạng thái expectation manager còn lại, dù logic của test sau không sai.

MockRestServiceServer.reset() đặt lại trạng thái của mock server: xóa các kỳ vọng đã đăng ký và các request đã ghi nhận. Nhờ đó, mỗi test có thể bắt đầu với một tập kỳ vọng mới khi cùng sử dụng client và mock server.

Reset là thao tác quản lý trạng thái kiểm thử. Nó không tự xác nhận test trước đã thực hiện đủ request. Muốn xác nhận kỳ vọng của test hiện tại đã được đáp ứng, vẫn cần gọi verify().

## Vòng đời của expectation

Một expectation thường được khai báo trước khi gọi client:

~~~java
mockServer.expect(requestTo("https://orders.example.test/api/orders/42"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"id": 42, "status": "PAID"}
                """,
                MediaType.APPLICATION_JSON
        ));
~~~

Khi client gửi request phù hợp, mock server đối chiếu request với expectation và trả về response đã khai báo. Sau khi request được xử lý, expectation tương ứng được đánh dấu đã sử dụng. verify() kiểm tra các expectation đã khai báo có được thực hiện đầy đủ hay không.

Có thể hình dung vòng đời trong một test như sau:

~~~text
reset() trước test
      |
      v
Đăng ký expectations của test hiện tại
      |
      v
HTTP client gửi request
      |
      v
MockRestServiceServer đối chiếu và trả response giả
      |
      v
Assert kết quả từ client
      |
      v
verify() xác nhận các expectations đã được đáp ứng
      |
      v
Test kết thúc
~~~

Ở đầu test tiếp theo, reset() xóa expectations và request history của lượt trước. Test mới phải đăng ký các expectation mà chính nó cần. Không nên phụ thuộc vào expectation do test khác tạo ra.

## Dùng reset khi client và mock server được chia sẻ

Ví dụ dưới đây cố ý dùng một RestTemplate, một OrderClient và một MockRestServiceServer cho nhiều test method. TestInstance(PER_CLASS) giúp các field tồn tại qua các method; BeforeEach reset trạng thái mock server trước khi test mới bắt đầu.

~~~java
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class OrderClientTests {

    private final RestTemplate restTemplate = new RestTemplate();

    private MockRestServiceServer mockServer;
    private OrderClient orderClient;

    @BeforeAll
    void createSharedClientAndServer() {
        mockServer = MockRestServiceServer
                .bindTo(restTemplate)
                .build();
        orderClient = new OrderClient(restTemplate);
    }

    @BeforeEach
    void resetExpectationsBeforeEachTest() {
        mockServer.reset();
    }

    @Test
    void findsPaidOrder() {
        mockServer.expect(requestTo(
                        "https://orders.example.test/api/orders/42"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        """
                        {"id": 42, "status": "PAID"}
                        """,
                        MediaType.APPLICATION_JSON
                ));

        OrderResponse order = orderClient.findById(42);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
        mockServer.verify();
    }

    @Test
    void findsNewOrder() {
        mockServer.expect(requestTo(
                        "https://orders.example.test/api/orders/7"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        """
                        {"id": 7, "status": "NEW"}
                        """,
                        MediaType.APPLICATION_JSON
                ));

        OrderResponse order = orderClient.findById(7);

        assertThat(order.id()).isEqualTo(7L);
        assertThat(order.status()).isEqualTo("NEW");
        mockServer.verify();
    }
}
~~~

Trong ví dụ, reset() chạy trước mỗi test method, còn expectation được đăng ký bên trong test cần sử dụng nó. Hai test không chia sẻ expectation của nhau dù dùng cùng RestTemplate và mock server.

Các kiểu OrderClient và OrderResponse là lớp minh họa của ứng dụng. Điều quan trọng ở đây là vòng đời của fixture: client và mock server được tạo một lần, trạng thái expectation được reset trước từng test.

## Vì sao reset ở BeforeEach?

Đặt reset ở BeforeEach tạo ra một ranh giới rõ ràng: test bắt đầu với mock server không còn expectation và request history từ test trước. Sau đó, test đăng ký đúng các response giả mà nó cần.

Trình tự này quan trọng:

~~~java
@BeforeEach
void prepareMockServer() {
    mockServer.reset();
    // Có thể khai báo expectations chung cho mọi test sau lệnh reset,
    // nếu các expectations đó thực sự thuộc fixture của từng test.
}
~~~

Nếu test cần expectation riêng, hãy khai báo trong thân test sau khi BeforeEach đã chạy. Nếu expectation chung được tạo trước reset, ví dụ trong BeforeAll, reset ở BeforeEach sẽ xóa chúng. Khi đó test sẽ không còn response giả mà nó mong đợi.

Có thể gọi reset() ở cuối test, nhưng cách này dễ bỏ sót khi test ném exception hoặc assertion thất bại trước khi chạy tới lệnh reset. Reset trước test tiếp theo là cơ chế phòng vệ tốt hơn cho fixture dùng chung. Dù vậy, mỗi test vẫn nên tự xác nhận kỳ vọng của mình bằng verify().

## Reset không thay thế verify

Hai phương thức phục vụ hai mục đích khác nhau:

| Phương thức | Tác dụng |
| --- | --- |
| reset() | Xóa expectations và các request đã ghi nhận để bắt đầu một lượt mới |
| verify() | Kiểm tra tất cả expectations đã đăng ký có được thực hiện hay chưa |

Ví dụ test đăng ký một expectation nhưng client không gửi request:

~~~java
mockServer.expect(requestTo(
        "https://orders.example.test/api/orders/42"));

// Không gọi orderClient.findById(42).

mockServer.verify(); // Thất bại vì expectation chưa được thực hiện.
~~~

Nếu gọi reset() ngay thay cho verify(), expectation chưa thực hiện sẽ bị xóa. Test mất cơ hội phát hiện rằng client không gửi request như yêu cầu. Vì vậy, reset không phải là cách “dọn lỗi” hoặc bỏ qua expectation còn thiếu.

Trong từng test, nên:

1. Đăng ký tất cả expectation cần thiết.
2. Gọi hành vi của HTTP client.
3. Assert kết quả trả về hoặc exception mong đợi.
4. Gọi mockServer.verify() để xác nhận các request đã được gửi đúng như khai báo.

Nếu dự án có cơ chế kiểm tra expectation chung ở AfterEach, hãy bảo đảm cơ chế đó chỉ verify mock server hiện tại và không che khuất exception gốc của test. Với ví dụ đơn giản, gọi verify() ngay trong test giúp nhìn rõ điểm kiểm tra.

## Reset với RestClient.Builder

Từ Spring Framework 6.1, MockRestServiceServer cũng hỗ trợ gắn với RestClient.Builder. Điều này hữu ích khi ứng dụng dùng API HTTP client đồng bộ mới thay cho RestTemplate.

~~~java
RestClient.Builder builder = RestClient.builder();

MockRestServiceServer mockServer = MockRestServiceServer
        .bindTo(builder)
        .build();

RestClient restClient = builder.build();
~~~

Client được build từ builder đã được gắn mock server. Khi fixture này được chia sẻ qua nhiều test, có thể reset mock server trước mỗi test theo cùng nguyên tắc:

~~~java
@BeforeEach
void resetServer() {
    mockServer.reset();
}
~~~

Mỗi test đăng ký expectation bằng mockServer.expect(...), gọi restClient, assert kết quả và verify. Việc dùng RestClient thay RestTemplate không thay đổi ý nghĩa của reset: trạng thái expectation và request history của mock server cần được cách ly giữa các lượt test.

## Khi dùng Spring TestContext hoặc test slice

Trong test tích hợp, RestTemplate hoặc RestClient có thể được khai báo như bean singleton trong ApplicationContext. Spring TestContext Framework có thể tái sử dụng context giữa nhiều test class để tiết kiệm thời gian. Nếu MockRestServiceServer được tạo và gắn với client singleton trong context đó, trạng thái của mock server cũng có thể được chia sẻ.

Điều cần làm rõ là fixture nào đang được chia sẻ:

- Nếu mỗi test method tự tạo client và mock server mới, trạng thái không cần reset giữa các method vì mỗi test có instance riêng.
- Nếu test dùng chung một mock server được tạo trong fixture hoặc context, hãy reset trước khi đăng ký expectations của test hiện tại.
- Nếu test class khác cũng nhận đúng singleton mock server đó, nó cần tuân theo cùng quy tắc vòng đời. Không để test này reset trong khi test khác đang dùng server.

Trong Spring Boot, các test slice cho HTTP client có thể tự cấu hình client và mock server. Hãy xem cách test slice đang cung cấp fixture và phiên bản Spring Boot cụ thể trước khi thêm một mock server thứ hai. Tạo hai mock server cùng gắn vào một client hoặc thay thế customizer đã được cấu hình có thể làm test gửi request qua một fixture khác với fixture mà test đang reset.

Reset trạng thái mock server thường đủ để cách ly expectations; không cần đánh dấu DirtiesContext chỉ để xóa expectation hoặc request history. DirtiesContext yêu cầu Spring loại context khỏi cache và tạo lại, tốn kém hơn và tác động tới toàn bộ bean trong context. Chỉ dùng nó khi trạng thái của chính ApplicationContext đã bị thay đổi đến mức không thể tái sử dụng theo mục tiêu của test.

## Expectations có thứ tự và không có thứ tự

MockRestServiceServer mặc định sử dụng cơ chế quản lý expectation có thứ tự. Khi một test đăng ký nhiều request, thứ tự request được gửi phải phù hợp với thứ tự kỳ vọng. Có thể cấu hình expectation manager không yêu cầu thứ tự khi thứ tự request không thuộc hợp đồng cần kiểm tra.

Ví dụ:

~~~java
MockRestServiceServer mockServer = MockRestServiceServer
        .bindTo(restTemplate)
        .ignoreExpectOrder(true)
        .build();
~~~

Hoặc sử dụng builder có expectation manager cụ thể khi cần cấu hình rõ ràng. Dù chọn cách nào, reset() vẫn dùng để xóa tập expectations và request đã ghi nhận giữa các test.

Không nên dùng chế độ không thứ tự chỉ để làm test bớt thất bại. Nếu client phải gọi token endpoint trước rồi mới gọi API nghiệp vụ, thứ tự đó có thể là một phần của hành vi cần kiểm tra. Ngược lại, nếu hai request độc lập và hệ thống không cam kết thứ tự, expectation không thứ tự có thể tránh phụ thuộc vào lịch thực thi.

## Không chia sẻ mock server giữa các test chạy song song

reset() thay đổi trạng thái dùng chung của mock server. Nếu hai test cùng lúc sử dụng một instance:

- Test A có thể đăng ký expectation.
- Test B gọi reset() và xóa expectation của A.
- Test A gửi request nhưng không còn expectation phù hợp.
- Test B có thể ghi nhận request hoặc response làm thay đổi kết quả mà A đang kiểm tra.

Vì vậy, không chạy song song các test cùng chia sẻ một MockRestServiceServer mutable. Có ba hướng xử lý:

1. Tạo RestTemplate/RestClient và mock server riêng cho từng test method.
2. Cô lập test class hoặc nhóm test dùng chung fixture, không cho chúng thực thi đồng thời.
3. Dùng một fixture riêng theo test thread hoặc test instance nếu framework và cách cấu hình cho phép.

Chỉ sử dụng collection hoặc expectation manager an toàn đa luồng không giải quyết được vấn đề logic này. reset() vẫn có thể xóa expectations mà test khác vừa đăng ký.

Nếu không có nhu cầu giữ client singleton, cách đơn giản nhất là tạo client và mock server trong BeforeEach. Mỗi test sở hữu trạng thái của riêng mình nên không cần gọi reset để làm sạch trạng thái từ một test khác:

~~~java
class IsolatedOrderClientTests {

    private RestTemplate restTemplate;
    private MockRestServiceServer mockServer;
    private OrderClient orderClient;

    @BeforeEach
    void setUp() {
        restTemplate = new RestTemplate();
        mockServer = MockRestServiceServer
                .bindTo(restTemplate)
                .build();
        orderClient = new OrderClient(restTemplate);
    }

    @Test
    void findsAnOrder() {
        mockServer.expect(requestTo(
                        "https://orders.example.test/api/orders/42"))
                .andRespond(withSuccess(
                        """
                        {"id": 42, "status": "PAID"}
                        """,
                        MediaType.APPLICATION_JSON
                ));

        OrderResponse result = orderClient.findById(42);

        assertThat(result.status()).isEqualTo("PAID");
        mockServer.verify();
    }
}
~~~

Trong ví dụ này, mỗi lần chạy test có mock server mới, nên reset không cần thiết. Đây thường là cách dễ hiểu nhất nếu việc tạo client không tốn kém và không phụ thuộc vào context dùng chung.

## Những lỗi thường gặp

### Đăng ký expectations trước khi reset

Nếu BeforeEach gọi reset sau khi fixture đã khai báo expectations, những expectations đó bị xóa. Hãy reset trước rồi mới khai báo expectation cho test.

### Gọi reset thay cho verify

Reset xóa kỳ vọng chưa thực hiện, nên có thể che giấu việc client không gửi request. Gọi verify để xác nhận hành vi của test hiện tại trước khi lượt test kết thúc.

### Tưởng reset sẽ tạo lại RestTemplate hoặc RestClient

Reset chỉ làm sạch trạng thái của MockRestServiceServer. Nó không tạo client mới và không xóa interceptor, converter, cấu hình timeout hoặc trạng thái ứng dụng khác đã gắn vào client.

### Dùng chung server nhưng quên reset

Expectation chưa sử dụng hoặc request history có thể tồn tại qua test method. Khi client và mock server được chia sẻ, reset ở đầu mỗi test là cách tạo ranh giới rõ ràng.

### Chạy song song trên cùng một mock server

Một test reset có thể xóa expectations của test khác. Hãy tạo fixture riêng hoặc cô lập lịch chạy nếu test cần chạy đồng thời.

### Dùng DirtiesContext chỉ để xóa expectations

Việc tạo lại toàn bộ context không cần thiết nếu vấn đề chỉ nằm ở trạng thái của mock server. Dùng reset hoặc tạo fixture mới phù hợp hơn.

## Quy trình quản lý kỳ vọng giữa các test

1. Xác định RestTemplate/RestClient và MockRestServiceServer có được chia sẻ qua nhiều test hay không.
2. Nếu fixture được chia sẻ, gọi mockServer.reset() trong BeforeEach.
3. Đăng ký expectations riêng của test sau khi reset hoàn tất.
4. Thực hiện hành vi của HTTP client.
5. Assert response, dữ liệu decode hoặc exception mong đợi.
6. Gọi mockServer.verify() để bảo đảm tất cả expectations đã được đáp ứng.
7. Không chạy song song các test dùng chung mock server mutable; nếu cần song song, tạo fixture riêng cho từng test.

Reset expectations là cách làm sạch trạng thái của mock HTTP server, còn verify là bằng chứng rằng client đã thực hiện đúng các request được mong đợi. Khi hai bước này được đặt đúng vị trí trong vòng đời test, nhiều bài kiểm thử có thể dùng chung fixture mà không để expectation hoặc request history của lượt trước làm sai kết quả lượt sau.
