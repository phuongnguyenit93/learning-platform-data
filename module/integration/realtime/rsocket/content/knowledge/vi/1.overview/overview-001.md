# RSocket là gì và vai trò trong tích hợp thời gian thực

Trong một hệ thống thời gian thực, nhiều thành phần cần trao đổi dữ liệu liên tục: bảng điều khiển nhận số liệu mới, ứng dụng chat nhận tin nhắn, dịch vụ giao dịch phát giá, hoặc thiết bị IoT gửi telemetry. HTTP request-response vẫn phù hợp với nhiều nghiệp vụ, nhưng khi mỗi thay đổi đều cần được đẩy đi ngay, việc liên tục tạo yêu cầu hoặc tự xây dựng quy ước trên một kết nối WebSocket có thể làm tăng độ phức tạp.

**RSocket** là một giao thức ứng dụng dành cho giao tiếp bất đồng bộ, hai chiều và theo luồng. Giao thức cung cấp sẵn các kiểu tương tác, cơ chế điều tiết luồng dữ liệu (backpressure) và metadata, đồng thời có thể chạy trên các transport như TCP hoặc WebSocket. Nhờ vậy, các dịch vụ Java có thể trao đổi dữ liệu liên tục qua một kết nối mà không phải tự định nghĩa lại toàn bộ cách gửi yêu cầu, nhận phản hồi và kiểm soát tốc độ dữ liệu.

## 1. RSocket là gì?

RSocket là giao thức nhị phân ở tầng ứng dụng, được thiết kế cho mô hình giao tiếp reactive giữa hai peer. Nó định nghĩa cách thiết lập phiên, đóng gói payload, nhận diện từng luồng tương tác và điều khiển việc truyền dữ liệu. RSocket không phải là một framework riêng của Java; các hệ sinh thái và ngôn ngữ khác nhau có thể triển khai cùng giao thức để giao tiếp với nhau.

Một kết nối RSocket thường được duy trì để phục vụ nhiều tương tác. Trên kết nối đó, hai bên có thể khởi tạo nhiều stream độc lập; các frame mang stream ID giúp phân biệt những tương tác đang diễn ra. Trong mô hình ứng dụng, ta thường gọi bên mở kết nối là client và bên nhận kết nối là server, nhưng sau khi phiên được thiết lập, cả hai peer đều có thể khởi tạo request nếu API và cấu hình của ứng dụng cho phép.

RSocket tách **giao thức tương tác** khỏi **transport**:

- **Giao thức RSocket** quy định các kiểu request, response, stream, metadata, flow control và frame.
- **Transport** vận chuyển các byte của giao thức giữa hai đầu. TCP thường phù hợp cho giao tiếp giữa các dịch vụ hoặc ứng dụng native; WebSocket hữu ích khi cần kết nối từ trình duyệt hoặc đi qua hạ tầng đã hỗ trợ WebSocket.

Vì vậy, RSocket không đồng nghĩa với WebSocket. WebSocket cung cấp một kênh truyền hai chiều; RSocket có thể chạy trên kênh đó và bổ sung ngữ nghĩa tương tác, định dạng frame cùng cơ chế backpressure.

## 2. Bốn kiểu tương tác cốt lõi

RSocket chuẩn hóa bốn kiểu tương tác. Việc chọn đúng kiểu giúp API thể hiện rõ dữ liệu đi theo một chiều hay hai chiều, có một phản hồi hay một chuỗi phản hồi.

| Kiểu tương tác | Dữ liệu trao đổi | Ví dụ phù hợp |
|---|---|---|
| Request-response | Một request, một response | Tra cứu trạng thái đơn hàng, lấy giá hiện tại |
| Fire-and-forget | Gửi một request và không chờ response | Gửi một tín hiệu hoặc ghi nhận một sự kiện không cần kết quả trả về |
| Request-stream | Một request, nhận một stream response | Theo dõi giá, nhiệt độ hoặc trạng thái theo thời gian |
| Request-channel | Hai bên trao đổi các stream dữ liệu | Phiên cộng tác trực tiếp, truyền dữ liệu hai chiều liên tục |

### 2.1. Request-response

Bên gọi gửi một payload và nhận về tối đa một payload phản hồi. Kiểu này gần với cách gọi API thông thường, nhưng được thực hiện trên phiên RSocket và có thể kết hợp với các kiểu tương tác khác trên cùng kết nối.

Ví dụ: dịch vụ đơn hàng gửi mã đơn hàng đến dịch vụ vận chuyển và nhận về trạng thái hiện tại. Nếu nghiệp vụ chỉ cần một kết quả, request-response thường là lựa chọn dễ hiểu nhất.

### 2.2. Fire-and-forget

Bên gọi gửi một payload mà không đăng ký nhận response. Kiểu này hữu ích khi bên gửi chỉ cần phát một tín hiệu hoặc thông báo cho bên nhận xử lý.

Không nên hiểu fire-and-forget là bảo đảm dữ liệu đã được xử lý hoặc lưu bền vững. Vì không có response ở cấp tương tác, bên gửi không nhận được xác nhận nghiệp vụ rằng thao tác đã hoàn tất. Nếu cần xác nhận, retry có kiểm soát hoặc bảo đảm lưu trữ, ứng dụng phải thiết kế thêm cơ chế phù hợp.

### 2.3. Request-stream

Bên gọi gửi một request ban đầu và nhận về nhiều response theo thời gian. Stream có thể tiếp tục cho đến khi hoàn tất, bị hủy hoặc gặp lỗi.

Ví dụ: ứng dụng yêu cầu theo dõi mã cổ phiếu ACME; dịch vụ giá phát ra các mức giá mới khi thị trường thay đổi. Người tiêu thụ không cần polling liên tục để hỏi lại cùng một dữ liệu.

### 2.4. Request-channel

Bên gọi gửi một stream request và đồng thời nhận một stream response. Đây là kiểu tương tác phù hợp khi cả hai phía đều cần phát dữ liệu trong cùng một phiên.

Ví dụ: trong một phiên chỉnh sửa cộng tác, client liên tục gửi thao tác của người dùng trong khi server gửi các thay đổi đã được đồng bộ từ những người tham gia khác. Ứng dụng vẫn cần quy định cách xử lý xung đột và thứ tự nghiệp vụ; RSocket cung cấp kênh trao đổi hai chiều chứ không tự giải quyết các quy tắc cộng tác đó.

## 3. RSocket hỗ trợ tích hợp thời gian thực như thế nào?

### Duy trì kết nối cho nhiều tương tác

Khi kết nối được thiết lập, ứng dụng có thể sử dụng lại phiên để thực hiện nhiều request và stream. Điều này giảm nhu cầu mở một kết nối mới cho mỗi lần cập nhật và giúp hai dịch vụ duy trì một kênh trao đổi liên tục. Nhiều stream có thể cùng tồn tại trên một kết nối, nhờ đó các luồng dữ liệu độc lập không cần được ghép thủ công vào một chuỗi thông điệp duy nhất.

### Giao tiếp hai chiều

Một bên có thể gửi dữ liệu trong khi vẫn nhận dữ liệu từ bên kia. Khả năng này hữu ích cho chat, cộng tác trực tiếp, điều khiển thiết bị và các phiên tương tác cần phản hồi liên tục. Request-channel biểu đạt rõ trường hợp cả hai phía đều phát stream.

### Điều tiết luồng bằng backpressure

Trong hệ thống realtime, tốc độ phát dữ liệu có thể cao hơn tốc độ xử lý của bên nhận. Nếu cứ gửi dữ liệu liên tục, bộ nhớ đệm có thể tăng không giới hạn, độ trễ tăng hoặc ứng dụng bị quá tải.

Với các tương tác dạng stream, RSocket hỗ trợ flow control dựa trên nhu cầu. Bên nhận cho biết số phần tử mà nó sẵn sàng nhận; bên gửi chỉ phát dữ liệu trong giới hạn nhu cầu đó. Khi cần thêm dữ liệu, bên nhận có thể yêu cầu thêm. Cơ chế này giúp pipeline reactive điều chỉnh tốc độ giữa producer và consumer.

Backpressure không thay thế việc thiết kế giới hạn tài nguyên. Ứng dụng vẫn cần chọn kích thước buffer hợp lý, xử lý consumer chậm, hủy stream không còn cần thiết và theo dõi độ trễ.

### Mang metadata cùng payload

Một payload RSocket có thể chứa phần **data** và phần **metadata**. Data thường mang nội dung nghiệp vụ như đối tượng JSON hoặc dữ liệu nhị phân. Metadata có thể mang thông tin định tuyến, kiểu nội dung, thông tin xác thực hoặc dữ liệu phục vụ tracing tùy theo định dạng và thỏa thuận giữa hai bên.

Cách tách này giúp ứng dụng giữ phần nội dung nghiệp vụ rõ ràng, đồng thời chuyển các thông tin điều khiển cần thiết cho việc định tuyến và xử lý. Hai phía cần thống nhất định dạng metadata và kiểm tra dữ liệu đầu vào; không nên mặc định mọi metadata đều đáng tin cậy.

## 4. Một tương tác RSocket diễn ra ra sao?

Ở mức khái quát, một phiên làm việc có các bước sau:

1. Hai phía thiết lập transport, chẳng hạn TCP hoặc WebSocket.
2. Peer khởi tạo gửi thông tin SETUP, bao gồm các tham số phiên và kiểu MIME được sử dụng cho data, metadata.
3. Sau khi phiên sẵn sàng, một phía gửi frame khởi tạo tương tác, chẳng hạn REQUEST_RESPONSE, REQUEST_STREAM hoặc REQUEST_CHANNEL.
4. Các frame tiếp theo mang payload, response, yêu cầu thêm dữ liệu hoặc tín hiệu kết thúc/hủy stream.
5. Khi không còn sử dụng, ứng dụng đóng tương tác và giải phóng kết nối theo vòng đời của phiên.

Sơ đồ dưới đây minh họa một request-stream. Đây là luồng logic rút gọn; giao thức thực tế có thêm các frame điều khiển và stream ID.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant R as RSocket session
    participant P as Producer
    C->>R: SETUP / thiết lập phiên
    R-->>C: Phiên sẵn sàng
    C->>P: REQUEST_STREAM (request ban đầu)
    P-->>C: Payload 1
    P-->>C: Payload 2
    C->>P: REQUEST_N (cần thêm dữ liệu)
    P-->>C: Payload tiếp theo
    C->>P: CANCEL (khi không còn theo dõi)
~~~

Trong giao thức, mỗi tương tác được gắn với một stream ID. Các frame như REQUEST_N, CANCEL, ERROR và KEEPALIVE hỗ trợ điều khiển nhu cầu, vòng đời tương tác, lỗi và trạng thái kết nối. Ứng dụng không cần tự xây dựng một giao thức text riêng để biểu diễn những thao tác cơ bản này.

## 5. RSocket trong ứng dụng Java và Spring Boot

Trong Java, RSocket thường được sử dụng cùng Reactor để biểu diễn kết quả bất đồng bộ bằng Mono và Flux. Spring Boot cung cấp tích hợp RSocket, cho phép khai báo route ở phía nhận bằng @MessageMapping và gọi route từ client bằng RSocketRequester.

Ví dụ sau minh họa một route trả về luồng giá:

~~~java
@Controller
public class QuoteRSocketController {

    private final QuoteService quoteService;

    public QuoteRSocketController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("quotes.stream")
    public Flux<Quote> stream(String symbol) {
        return quoteService.stream(symbol);
    }
}
~~~

Client gọi route và nhận một Flux:

~~~java
Flux<Quote> quotes = requester
    .route("quotes.stream")
    .data("ACME")
    .retrieveFlux(Quote.class);
~~~

Do handler trả về Flux<Quote>, tương tác này biểu diễn request-stream. Khi consumer hủy subscription, việc hủy stream có thể được truyền xuống pipeline để giải phóng tài nguyên nếu các thành phần xử lý hỗ trợ cancellation đúng cách.

Đoạn mã chỉ minh họa cách khai báo và gọi route; ứng dụng thực tế còn cần cấu hình transport, RSocketRequester, codec, xác thực, xử lý lỗi và quản lý vòng đời kết nối. Việc dùng Spring không làm thay đổi bản chất giao thức: một client RSocket khác triển khai đúng protocol vẫn có thể giao tiếp với endpoint này.

## 6. So sánh RSocket với các lựa chọn phổ biến

| Công nghệ | Mô hình chính | Điểm phù hợp | Điều cần lưu ý |
|---|---|---|---|
| HTTP/REST | Request-response | CRUD, truy vấn tài nguyên, API phổ thông | Muốn cập nhật liên tục thường cần polling hoặc cơ chế push bổ sung |
| WebSocket | Kênh hai chiều | Trao đổi message realtime giữa client và server | Ứng dụng thường phải tự quy định kiểu message, flow control và vòng đời tương tác |
| Server-Sent Events (SSE) | Server đẩy dữ liệu một chiều đến client | Feed hoặc thông báo từ server đến trình duyệt | Không cung cấp kênh gửi dữ liệu hai chiều trong cùng kết nối |
| RSocket | Request-response, fire-and-forget, request-stream, request-channel | Giao tiếp reactive, stream và hai chiều giữa các peer | Cần client/server hỗ trợ RSocket và cần thiết kế vận hành cho kết nối dài hạn |
| Apache Kafka | Log sự kiện phân tán và pub/sub | Phân phối sự kiện giữa nhiều consumer, lưu giữ và đọc lại theo chính sách | Có mô hình broker và lưu trữ sự kiện khác với tương tác trực tiếp qua phiên RSocket |

WebSocket là một transport có thể dùng cho RSocket; hai khái niệm này không loại trừ nhau. Kafka và RSocket cũng có thể bổ sung cho nhau: Kafka đảm nhiệm lưu trữ/phân phối sự kiện bền vững, còn RSocket phục vụ tương tác realtime giữa các thành phần đang kết nối.

## 7. Khi nào nên dùng RSocket?

RSocket phù hợp khi ứng dụng có một hoặc nhiều đặc điểm sau:

- Cần phát dữ liệu liên tục thay vì yêu cầu lặp lại theo chu kỳ.
- Cả client và server đều cần gửi dữ liệu trong cùng một phiên.
- Producer và consumer có tốc độ xử lý khác nhau, cần backpressure cho stream.
- Nhiều tương tác độc lập cần dùng chung một kết nối dài hạn.
- Các dịch vụ Java hoặc các hệ thống hỗ trợ RSocket cần trao đổi dữ liệu reactive qua TCP hoặc WebSocket.

Một số ví dụ thực tế:

- **Dashboard vận hành:** backend gửi số liệu và trạng thái mới khi chúng thay đổi.
- **Chat và cộng tác:** client gửi thao tác, server phát cập nhật tới phiên đang hoạt động.
- **IoT:** thiết bị gửi telemetry và nhận lệnh điều khiển qua kênh hai chiều.
- **Dịch vụ giá hoặc theo dõi trạng thái:** một request mở stream để nhận nhiều bản cập nhật.
- **Tích hợp giữa microservice:** một dịch vụ yêu cầu luồng dữ liệu từ dịch vụ khác và xử lý theo pipeline reactive.

RSocket có thể không cần thiết với API CRUD ít thay đổi, lưu lượng thấp và chỉ cần request-response đơn giản. Nếu yêu cầu chính là lưu sự kiện để consumer có thể đọc lại sau khi mất kết nối, cần một hệ thống broker hoặc storage phù hợp; một phiên RSocket đang mở tự nó không đóng vai trò như một event log bền vững.

## 8. Những giới hạn và điểm cần thiết kế

RSocket cung cấp cơ chế giao tiếp, nhưng không tự giải quyết mọi vấn đề của hệ thống phân tán.

- **Mất kết nối và phục hồi:** ứng dụng cần định nghĩa cách phát hiện disconnect, reconnect và khôi phục trạng thái nghiệp vụ. Protocol có cơ chế resumability tùy chọn, nhưng khả năng resume phải được hỗ trợ và cấu hình ở cả hai phía; không nên giả định mọi kết nối đều tự phục hồi trong suốt.
- **Độ tin cậy của nghiệp vụ:** retry có thể khiến một thao tác được gửi lại. Các lệnh làm thay đổi trạng thái nên có thiết kế idempotency hoặc mã định danh để tránh xử lý trùng.
- **Bảo mật:** dùng TLS khi truyền qua mạng không tin cậy, xác thực peer, phân quyền theo route và kiểm tra metadata/payload. Metadata là dữ liệu đầu vào, không phải bằng chứng xác thực nếu chưa được kiểm tra.
- **Quản lý tài nguyên:** theo dõi số kết nối, stream đang hoạt động, buffer, consumer chậm, timeout và cancellation. Kết nối dài hạn cần giới hạn và dọn dẹp đúng vòng đời.
- **Quan sát hệ thống:** ghi nhận latency, tỷ lệ lỗi, số stream, reconnect và trạng thái backpressure. Correlation ID hoặc trace metadata giúp nối các log giữa nhiều dịch vụ.
- **Khả năng tương thích:** thống nhất route, schema payload, MIME type và quy ước metadata giữa các phiên bản client/server.

## 9. Kết luận

RSocket là giao thức cho giao tiếp ứng dụng bất đồng bộ và reactive qua các transport như TCP hoặc WebSocket. Vai trò nổi bật của nó trong tích hợp thời gian thực là cung cấp bốn kiểu tương tác chuẩn, hỗ trợ trao đổi hai chiều và điều tiết luồng dữ liệu trên các kết nối có thể được tái sử dụng.

Khi thiết kế hệ thống Java, hãy bắt đầu từ hình dạng của nghiệp vụ: cần một kết quả thì dùng request-response; gửi tín hiệu không cần phản hồi thì cân nhắc fire-and-forget; cần nhận cập nhật liên tục thì dùng request-stream; cần hai bên cùng phát dữ liệu thì dùng request-channel. Sau đó, thiết kế thêm bảo mật, xử lý lỗi, reconnect, idempotency và quan sát hệ thống để phiên realtime hoạt động ổn định trong môi trường thực tế.

