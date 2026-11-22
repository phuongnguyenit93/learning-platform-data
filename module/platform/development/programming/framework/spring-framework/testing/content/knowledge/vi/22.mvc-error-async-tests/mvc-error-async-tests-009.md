# Streaming hoặc SSE và khi cần HTTP qua máy chủ thật

## 1. Vì sao kiểm thử streaming cần chú ý đến ranh giới HTTP

Trong Spring MVC, nhiều endpoint trả về một response hoàn chỉnh: controller tạo DTO, Spring tuần tự hóa thành JSON, ghi response body rồi kết thúc request. Streaming có cách hoạt động khác. Server có thể ghi dữ liệu theo từng phần trong khi request vẫn còn mở.

Hai kiểu response phổ biến là:

- **StreamingResponseBody:** ứng dụng ghi trực tiếp các byte vào output stream của response. Phù hợp với file lớn, export, nội dung được tạo dần hoặc dữ liệu không cần đóng gói thành từng event.
- **SseEmitter:** ứng dụng gửi một chuỗi Server-Sent Events (SSE) tới client qua một kết nối HTTP kéo dài. Phù hợp với thông báo một chiều từ server tới trình duyệt hoặc client.

Cả hai đều có thể được kiểm thử bằng MockMvc ở mức Spring MVC. Tuy nhiên, MockMvc dùng mock servlet request/response và chạy trong cùng tiến trình test. Nó không mở socket HTTP thật. Vì vậy, MockMvc có thể xác nhận logic controller, async lifecycle và nội dung cuối cùng, nhưng không chứng minh dữ liệu đã được truyền thành nhiều lần ghi có thể quan sát từ client qua mạng.

Cần chọn đúng cấp độ kiểm thử theo điều muốn xác nhận:

- Nếu cần xác nhận status, header, content type, nội dung cuối cùng và cách controller khởi động async, MockMvc thường đủ.
- Nếu cần xác nhận client nhận được event khi stream vẫn đang mở, thời điểm flush, client disconnect, buffering, timeout hoặc hành vi của servlet container, cần gửi request qua HTTP tới máy chủ thật.

## 2. Phân biệt streaming body và Server-Sent Events

### StreamingResponseBody

Controller trả về một callback ghi dữ liệu vào OutputStream:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class ReportController {

    @GetMapping(
            value = "/reports/export",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public StreamingResponseBody export() {
        return outputStream -> {
            outputStream.write("report header\n"
                    .getBytes(StandardCharsets.UTF_8));
            outputStream.flush();

            outputStream.write("row 1\n"
                    .getBytes(StandardCharsets.UTF_8));
            outputStream.flush();

            outputStream.write("row 2\n"
                    .getBytes(StandardCharsets.UTF_8));
        };
    }
}
~~~

Spring MVC chạy phần ghi stream theo cơ chế async. Controller trả về trước khi callback hoàn tất; callback ghi dữ liệu trong giai đoạn xử lý async. Có thể gọi **flush()** để yêu cầu đẩy dữ liệu đã ghi xuống response stream. Việc client thực sự nhận được từng phần vào thời điểm nào còn phụ thuộc servlet container, mạng và các tầng proxy hoặc gateway.

**StreamingResponseBody** phù hợp khi ứng dụng muốn kiểm soát cách ghi byte. Nếu nội dung có thể lớn, nên ghi theo từng phần và tránh dựng toàn bộ nội dung trong một **byte[]** hoặc **String** trước khi trả về.

### SseEmitter

SSE là một định dạng sự kiện văn bản chạy trên HTTP. Response thường có media type **text/event-stream**. Mỗi event gồm các dòng tùy chọn như **id**, **event**, **retry**, một hoặc nhiều dòng **data**, rồi một dòng trống để kết thúc event.

Ví dụ một event trên đường truyền:

~~~text
id:42
event:notification
data:An order has been paid

~~~

Trình duyệt có thể đọc event bằng API **EventSource**. Kết nối thường được giữ mở để server tiếp tục gửi event mới.

Controller có thể trả về **SseEmitter**:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
public class NotificationController {

    private final NotificationService notificationService;

    public NotificationController(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @GetMapping(
            value = "/notifications",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public SseEmitter notifications() {
        return notificationService.subscribe();
    }
}
~~~

Một nơi phát event có thể gửi dữ liệu như sau:

~~~java
emitter.send(SseEmitter.event()
        .id("42")
        .name("notification")
        .data("An order has been paid"));
~~~

Khi không còn event và muốn kết thúc stream, gọi **complete()**. Nếu quá trình phát sinh lỗi, có thể gọi **completeWithError(exception)**. **SseEmitter** cũng hỗ trợ callback **onCompletion**, **onTimeout** và **onError**; ứng dụng thường dùng chúng để hủy subscription, giải phóng tài nguyên hoặc ghi nhận vòng đời kết nối.

Không nên nhầm SSE với WebSocket. SSE là luồng một chiều từ server tới client trên HTTP; client gửi dữ liệu ngược lại bằng một request HTTP khác. WebSocket cung cấp kết nối hai chiều với giao thức riêng sau quá trình upgrade.

## 3. MockMvc có thể kiểm tra những gì?

MockMvc gọi Spring MVC thông qua các thành phần như handler mapping, controller, argument resolver, return value handler, message converter và exception resolver. Nó hỗ trợ async request, vì vậy có thể kiểm tra các điểm sau:

- Request có khởi động xử lý async hay không.
- Async result có được hoàn tất hay không.
- Kết quả sau async dispatch có status và header đúng không.
- Body cuối cùng có đúng dữ liệu và định dạng không.
- Exception được xử lý thế nào khi MVC còn có thể tạo response lỗi.
- Với SSE được kết thúc trong test, các dòng event cuối cùng có đúng nội dung hay không.

Điểm giới hạn là MockMvc không tạo kết nối TCP thực, không mô phỏng client đọc từng byte trong lúc server tiếp tục ghi, và không xác nhận servlet container hay proxy có đẩy dữ liệu ra ngoài ngay sau mỗi lần flush hay không.

### Luồng kiểm thử async của MockMvc

Với một async endpoint, request đầu tiên có thể trả về trước khi kết quả cuối cùng sẵn sàng. Test cần kiểm tra async đã bắt đầu, lấy **MvcResult**, sau đó gọi **asyncDispatch** để kiểm tra response sau khi xử lý async hoàn tất.

~~~text
mockMvc.perform(request)
        |
        v
request().asyncStarted()
        |
        v
MvcResult (request đang chờ)
        |
        | callback / async task hoàn tất
        v
mockMvc.perform(asyncDispatch(result))
        |
        v
Kiểm tra status, header và body cuối cùng
~~~

Nếu bỏ qua **asyncDispatch**, test có thể chỉ nhìn thấy trạng thái ban đầu của request và chưa kiểm tra response sau khi async hoàn tất.

## 4. Kiểm thử StreamingResponseBody bằng MockMvc

Ví dụ test kiểm tra nội dung cuối cùng của một response streaming:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReportController.class)
class ReportControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldReturnTheCompletedStreamingBody() throws Exception {
        MvcResult pending = mockMvc.perform(get("/reports/export"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(content().string(containsString("report header")))
                .andExpect(content().string(containsString("row 1")))
                .andExpect(content().string(containsString("row 2")));
    }
}
~~~

Test này xác nhận controller đã khởi động async và response cuối cùng chứa các phần dữ liệu mong đợi. Nó không chứng minh client đã nhận được **report header** trước **row 1**, cũng không chứng minh mỗi lần gọi **flush()** tạo ra một lần truyền dữ liệu riêng trên mạng.

Nếu async task phụ thuộc vào service, có thể mock service hoặc dùng dữ liệu cố định để test có kết quả xác định. Nếu task có thể chạy lâu, hãy cấu hình timeout phù hợp cho async request trong test để test thất bại có thông tin rõ ràng thay vì chờ vô hạn.

Không nên dùng một assertion trên toàn bộ response body để suy ra hành vi streaming. Mock response có thể lưu lại toàn bộ byte đã ghi rồi mới cho test đọc. Việc body cuối cùng đúng không có nghĩa luồng byte được phân phối đúng thời gian.

## 5. Kiểm thử SSE bằng MockMvc

Một bài kiểm thử MockMvc có thể xác nhận controller trả về async response, content type SSE và event đã gửi trước khi emitter hoàn tất.

Ví dụ service trả về emitter:

~~~java
public interface NotificationService {
    SseEmitter subscribe();
}
~~~

Test tạo emitter có thể điều khiển, cho controller trả về emitter đó, rồi gửi event và kết thúc stream:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(NotificationController.class)
class NotificationControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private NotificationService notificationService;

    @Test
    void shouldSerializeAnSseEvent() throws Exception {
        SseEmitter emitter = new SseEmitter(10_000L);
        when(notificationService.subscribe()).thenReturn(emitter);

        MvcResult pending = mockMvc.perform(get("/notifications")
                        .accept(MediaType.TEXT_EVENT_STREAM))
                .andExpect(request().asyncStarted())
                .andReturn();

        emitter.send(SseEmitter.event()
                .id("42")
                .name("notification")
                .data("ready"));

        emitter.complete();

        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM))
                .andExpect(content().string(containsString("id:42")))
                .andExpect(content().string(containsString("event:notification")))
                .andExpect(content().string(containsString("data:ready")));
    }
}
~~~

Thứ tự thao tác có ý nghĩa:

1. MockMvc thực hiện request và Spring đăng ký emitter với request async.
2. Test gửi event sau khi request đã bắt đầu.
3. Test gọi **complete()** để kết thúc stream.
4. Test dùng **asyncDispatch** để kiểm tra response đã hoàn tất.

Nếu emitter không được hoàn tất hoặc timeout, async dispatch có thể phải chờ cho tới khi timeout. Với một kết nối SSE chạy lâu dài trong production, việc giữ kết nối mở là hành vi đúng; trong test MockMvc kiểm tra body cuối cùng, nên cần điều khiển rõ thời điểm gửi event và kết thúc emitter.

Test trên kiểm tra định dạng event đã được ghi vào mock response. Nó chưa xác nhận trình duyệt nhận được event khi kết nối vẫn đang mở, cũng chưa xác nhận event đến theo nhịp thời gian mong muốn.

## 6. Khi nào MockMvc là đủ?

Dùng MockMvc khi mục tiêu nằm ở logic Spring MVC và nội dung response cuối cùng:

| Mục tiêu | MockMvc có phù hợp? |
|---|---|
| Kiểm tra endpoint trả về **StreamingResponseBody** | Có |
| Kiểm tra request khởi động async | Có |
| Kiểm tra nội dung sau khi async hoàn tất | Có |
| Kiểm tra SSE có đúng **id**, **event**, **data** sau khi hoàn tất | Có |
| Kiểm tra status, header và content type | Có |
| Kiểm tra exception xảy ra trước khi response được commit | Có |
| Chứng minh event đầu tiên đến client trước khi stream kết thúc | Không |
| Đo độ trễ giữa các event hoặc heartbeat | Không |
| Chứng minh **flush()** được chuyển thành dữ liệu có thể đọc ngay qua socket | Không |
| Kiểm tra client disconnect và server phát hiện disconnect | Không |
| Kiểm tra buffering của servlet container, reverse proxy hoặc gateway | Không |
| Kiểm tra hành vi thực tế dưới tải và nhiều kết nối đồng thời | Không |

MockMvc vẫn là lựa chọn tốt cho phần lớn kiểm thử controller và MVC. Khi một yêu cầu phụ thuộc vào thời gian, kết nối hoặc transport, cần bổ sung một integration test qua HTTP.

## 7. Kiểm thử qua HTTP với máy chủ thật

Với Spring Boot, **@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)** khởi chạy application context cùng embedded servlet container. Test gửi request tới cổng thật được cấp ngẫu nhiên.

Đối với SSE, có thể dùng Java **HttpClient** để đọc response body theo dòng. Ví dụ dưới đây giả định endpoint gửi một event **ready** ngay sau khi client kết nối; test fixture hoặc publisher cần bảo đảm event đó được phát ra.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class NotificationHttpIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void shouldDeliverAnSseEventOverRealHttp() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + "/notifications"))
                .header("Accept", "text/event-stream")
                .GET()
                .build();

        HttpResponse<Stream<String>> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofLines());

        assertEquals(200, response.statusCode());

        String contentType = response.headers()
                .firstValue("Content-Type")
                .orElse("");

        assertTrue(contentType.startsWith("text/event-stream"));

        try (Stream<String> lines = response.body()) {
            String dataLine = lines
                    .filter(line -> line.startsWith("data:"))
                    .findFirst()
                    .orElseThrow();

            assertEquals("data:ready", dataLine);
        }
    }
}
~~~

**BodyHandlers.ofLines()** cho phép test đọc dữ liệu theo từng dòng từ response body. **findFirst()** sẽ chờ cho tới khi có dòng phù hợp hoặc stream kết thúc. Vì vậy, endpoint cần phát event trong thời gian test cho phép. Khi đóng stream body, client đóng phần đọc response và có thể làm kết nối bị ngắt.

Nếu muốn xác nhận dữ liệu đến trước khi server kết thúc stream, hãy thiết kế test có điều khiển: server gửi event đầu tiên và giữ kết nối mở; client đọc event đó rồi mới phát tín hiệu để server gửi event tiếp theo hoặc hoàn tất. Một **CountDownLatch**, test publisher hoặc cổng điều khiển chỉ dùng trong test có thể đồng bộ hai phía. Không dùng **Thread.sleep()** để đoán thời điểm event sẽ đến vì test dễ chập chờn trên CI.

Đối với **StreamingResponseBody**, cũng có thể dùng **HttpClient** với **BodyHandlers.ofInputStream()** hoặc **BodyHandlers.ofLines()** để đọc phần đầu trong lúc server còn đang ghi phần sau. Điều này kiểm tra được hành vi mà MockMvc không thể xác nhận: client thực sự quan sát được dữ liệu trên một kết nối HTTP đang hoạt động.

## 8. Những hành vi chỉ có thể xác nhận đáng tin cậy qua máy chủ thật

### Thời điểm flush và buffering

Lệnh **flush()** yêu cầu đẩy dữ liệu đã ghi xuống output stream. Tuy nhiên, dữ liệu có thể còn bị giữ ở servlet container, TLS layer, proxy, load balancer hoặc client buffer. Một test MockMvc chỉ đọc được mock response cuối cùng nên không xác nhận được tầng nào đang buffer dữ liệu.

Nếu sản phẩm yêu cầu dashboard cập nhật gần như tức thời hoặc SSE phải gửi heartbeat định kỳ, cần kiểm tra qua đường HTTP thực tế. Nếu production đi qua reverse proxy, hãy kiểm tra cả đường đi qua proxy vì test vào embedded server trực tiếp không thể phát hiện proxy đang buffer response.

### Client disconnect và cleanup

Trong production, trình duyệt có thể đóng tab, mất mạng hoặc chủ động hủy request. Với **SseEmitter**, ứng dụng nên xử lý **onCompletion**, **onTimeout** và **onError** để hủy subscription hoặc giải phóng tài nguyên.

MockMvc có thể gọi các nhánh callback hoặc kiểm tra logic cleanup ở mức unit test nếu test điều khiển được emitter. Nhưng nó không mô phỏng chính xác việc socket bị đóng giữa lúc server đang ghi. Muốn xác nhận server phát hiện disconnect và ngừng công việc nền, cần một HTTP client thật mở rồi đóng response stream, đồng thời quan sát trạng thái cleanup ở phía server.

Việc phát hiện disconnect có thể xảy ra ở lần ghi hoặc flush tiếp theo. Không nên giả định server luôn biết ngay lập tức khi client đóng kết nối.

### Timeout và kết nối kéo dài

Một SSE connection có thể tồn tại nhiều phút. Cần kiểm tra timeout của emitter, async request timeout, proxy idle timeout và cơ chế heartbeat. MockMvc hữu ích để kiểm tra nhánh timeout do ứng dụng điều khiển, nhưng không đại diện cho chính sách timeout của toàn bộ hạ tầng.

### Nhiều client và tài nguyên

Mỗi kết nối streaming có thể giữ một phần tài nguyên của ứng dụng. Cần kiểm tra số kết nối đồng thời, thread/task executor, hàng đợi event, giới hạn bộ nhớ và cách ứng dụng xử lý client đọc chậm. Các bài kiểm thử tải hoặc kiểm thử nhiều client qua HTTP thật phù hợp hơn MockMvc.

### Giao thức và hạ tầng triển khai

Nếu cần kiểm tra TLS, cookie, authentication filter, compression, HTTP/1.1, HTTP/2 hoặc reverse proxy, hãy dùng một máy chủ và đường mạng tương ứng với cấu hình cần xác nhận. Embedded server trên localhost không tự động kiểm tra được mọi khác biệt của môi trường triển khai.

Không nên assert kích thước từng HTTP chunk như thể đó là ranh giới của SSE event. Chunked transfer encoding là framing của HTTP/1.1; HTTP/2 dùng framing khác. Một event có thể bị chia thành nhiều lần đọc ở client, hoặc nhiều event có thể xuất hiện trong cùng một lần đọc. Hãy kiểm tra ranh giới event theo định dạng SSE, không phụ thuộc ranh giới chunk của transport.

## 9. Xử lý lỗi trong response streaming

Lỗi MVC xảy ra trước khi response được commit thường có thể đi qua **HandlerExceptionResolver** hoặc **@ControllerAdvice**. Khi đó, MockMvc có thể xác nhận status và error body như với endpoint thông thường.

Streaming có thêm một ranh giới quan trọng: sau khi server đã gửi header hoặc một phần body, response có thể đã được commit. Lúc này, server thường không thể đổi status thành 500 rồi thay toàn bộ body bằng JSON error response như một request chưa gửi dữ liệu.

Với **StreamingResponseBody**, nếu callback lỗi sau khi đã ghi một phần nội dung, client có thể nhận một body không hoàn chỉnh hoặc kết nối bị đóng. Test MockMvc có thể kiểm tra một số trường hợp exception trong async processing, nhưng không chứng minh client đã nhận bao nhiêu byte trước khi kết nối kết thúc.

Với SSE, lỗi nghiệp vụ sau khi kết nối đã mở có thể được biểu diễn thành một event có tên như **error** nếu giao thức ứng dụng định nghĩa như vậy. **completeWithError** kết thúc emitter với lỗi; nó không đảm bảo có thể biến một stream đã bắt đầu thành response JSON lỗi mới. Client cần có quy tắc xử lý event lỗi và reconnect rõ ràng.

Nên kiểm tra riêng các tình huống:

- Lỗi trước khi response bắt đầu: xác nhận status và error representation.
- Lỗi trong lúc tạo stream: xác nhận callback lỗi, cleanup và cách client nhận biết stream bị gián đoạn.
- Client disconnect: xác nhận tác vụ nền hoặc subscription được hủy.
- Timeout: xác nhận kết nối được đóng và tài nguyên được giải phóng.

MockMvc phù hợp với các nhánh logic có thể điều khiển trong test. Các tình huống phụ thuộc vào kết nối đã commit và client thực tế cần HTTP integration test.

## 10. Cách tổ chức bộ kiểm thử

Một bộ kiểm thử streaming/SSE thường có nhiều cấp:

| Cấp kiểm thử | Công cụ | Mục tiêu |
|---|---|---|
| Unit test | JUnit và Mockito | Kiểm tra logic tạo chunk, event, xử lý lỗi và cleanup |
| MVC test | MockMvc | Kiểm tra mapping, async start, status, header và body cuối cùng |
| HTTP integration test | **@SpringBootTest(RANDOM_PORT)** + **HttpClient** | Kiểm tra byte/event được gửi qua embedded server thật |
| Deployment test | HTTP client qua proxy hoặc môi trường staging | Kiểm tra TLS, proxy buffering, timeout và cấu hình triển khai |
| Load test | Công cụ tạo nhiều HTTP client | Kiểm tra concurrency, throughput và tài nguyên |

Không cần biến mọi test controller thành HTTP integration test. Hãy đặt phần lớn assertion logic và response contract ở MockMvc để test chạy nhanh, dễ xác định lỗi. Thêm test qua máy chủ thật khi có yêu cầu cụ thể về kết nối, thời gian hoặc hành vi của container.

Khi kiểm thử SSE, hãy xác định rõ điều gì là hợp đồng: tên event, event id, data schema, heartbeat, reconnect policy và hành vi khi client ngắt kết nối. Khi kiểm thử streaming body, hãy xác định nội dung, encoding, thứ tự dữ liệu, thời điểm dữ liệu phải sẵn sàng và cách báo lỗi nếu stream bị gián đoạn.

Một test MockMvc xác nhận được response cuối cùng đúng. Một test HTTP thật mới xác nhận được client có thể nhận dữ liệu trên kết nối đang mở theo cách hệ thống yêu cầu.

