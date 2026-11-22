# Kết thúc khi hết route

## 1. Bài toán: điều gì xảy ra sau bước cuối cùng?

Một hệ thống xử lý đơn hàng có các bước **validate → charge → audit**. Mỗi đơn có thể đi qua những bước khác nhau: đơn đã thanh toán thì bỏ qua `charge`, đơn rủi ro cao cần bổ sung `review`. Thay vì dựng nhiều Router cố định, hệ thống gắn danh sách điểm đến lên message và để các endpoint lần lượt xử lý. Đó là **Routing Slip** trong Enterprise Integration Patterns (EIP).

Đường đi mẫu:

~~~text
OrderCommand
    → validate
    → charge
    → audit
    → [hết routing slip]
    → ?
~~~

Dấu hỏi cuối cùng rất quan trọng: **hết danh sách route có phải là message bị drop, tự động hoàn tất giao dịch, hay gửi lại kết quả cho bên yêu cầu?**

Trong **Spring Integration**, Routing Slip được biểu diễn bằng header `routingSlip`. Khi một endpoint có khả năng tạo reply nhưng **không cấu hình output channel riêng**, framework có thể lấy điểm đến kế tiếp từ header này. **Khi đã dùng hết đường đi trong routing slip, cơ chế xử lý `replyChannel` thông thường tiếp tục được áp dụng**. Vì vậy *routing slip exhausted* không đồng nghĩa với *business workflow completed* và cũng không tự phát event hoàn tất. Muốn xác nhận đã xử lý thành công, phải quan sát kết quả của endpoint cuối và hợp đồng phản hồi của flow.

Bài thuộc chương **Routing slip** trong module **SPRING_INTEGRATION_PATTERN**. Chủ đề giúp thực hành Enterprise Integration Patterns với Spring Integration để dựng message flow ít phụ thuộc và dễ mở rộng, đồng thời kết hợp **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, error channel và correlation**, kiểm thử và theo dõi những nhánh xử lý.

**Kết quả mong đợi:** hiểu thuật toán đi qua các route, biết lúc nào routing slip thực sự cạn, phân biệt điểm dừng tự nhiên với lỗi hay handler không trả lời, thiết kế reply/terminal behavior có chủ đích và viết test xác nhận từng tình huống.

## 2. Routing Slip không giống một Router chọn một nhánh

**Content-Based Router** thường quyết định *một điểm đến kế tiếp* từ nội dung message. **Routing Slip** mang theo một *lộ trình* gồm nhiều bước và trạng thái đang đi tới đâu trên lộ trình đó. Mỗi bước xử lý có thể đưa message tới bước tiếp mà không cần biết toàn bộ topology.

| Tiêu chí | Content-Based Router | Routing Slip |
|---|---|---|
| Câu hỏi chính | Message nên đi tới channel nào bây giờ? | Message còn phải đi qua những channel nào? |
| Nơi lưu quyết định | Cấu hình Router hoặc method/SpEL | Header lưu đường đi và vị trí hiện tại |
| Tiến trình | Mỗi lần route tính một nhánh | Qua các bước theo đường đi được khai báo |
| Điểm kết thúc | Phụ thuộc nhánh/consumer đích | Khi không còn route và dùng cơ chế reply chuẩn |
| Tình huống phù hợp | Phân loại VN/US, loại sự kiện | Workflow thay đổi theo yêu cầu, nhiều xử lý kế tiếp |
| Rủi ro chính | Key lạ, mapping sai | Mất header, lặp route, không có reply, quá nhiều bước |

Trong cách cài đặt của Spring Integration, routing slip không phải một vòng lặp tự chạy toàn bộ hành trình. **Mỗi handler phải thực sự tạo ra reply** và để framework tìm output channel tiếp theo. Không có reply nghĩa là không có message để chuyển tiếp.

## 3. Đường đi và bộ đếm vị trí

Routing slip có thể hiểu bằng hai thành phần:

1. **Path:** danh sách các bước/chỉ dẫn định tuyến, ví dụ `[orders.charge, orders.audit]`.
2. **Index:** vị trí của phần tử đang được xét trong danh sách.

Trong Spring Integration, `RoutingSlipHeaderValueMessageProcessor` tạo giá trị routing slip với path đã được phân giải và chỉ số ban đầu bằng `0`. Khi một entry là tên channel được phân giải thành công, routing slip chuyển tiếp đến channel ấy rồi tăng index trong reply message. **Path không bị rút ngắn; index tiến lên**.

~~~mermaid
flowchart LR
    IN["orders.validate<br/>reply: OrderState"] --> P0["Index 0: orders.charge"]
    P0 --> CH["Charge handler<br/>reply: OrderState"]
    CH --> P1["Index 1: orders.audit"]
    P1 --> AU["Audit handler<br/>reply: OrderState"]
    AU --> END{"Index ≥ path.size?"}
    END -->|"Có"| RP["Fallback: replyChannel thông thường"]
~~~

**Lưu ý:** ví dụ bắt đầu với `orders.validate` bằng output channel đã cấu hình tại điểm tạo routing slip. Vì vậy đường đi trong header chỉ cần liệt kê **những bước tiếp theo**, ở đây `orders.charge` và `orders.audit`. Đừng ghi lặp `orders.validate` vào path nếu không muốn chạy lại validation.

Một lộ trình minh họa:

| Thời điểm | Endpoint vừa xử lý | Path không đổi | Index tiếp theo | Hành động |
|---|---|---|---:|---|
| T0 | Header enricher → Validate | `charge, audit` | 0 | Đi vào validation |
| T1 | Validate trả reply | `charge, audit` | 0 → 1 | Chuyển tới Charge |
| T2 | Charge trả reply | `charge, audit` | 1 → 2 | Chuyển tới Audit |
| T3 | Audit trả reply | `charge, audit` | 2 (hết path) | Xem xét `replyChannel` |
| T4 | Reply đã gửi về Gateway | Không còn bước Routing Slip | — | Caller nhận kết quả |

T3 chỉ xảy ra khi Audit **trả lại một reply hợp lệ** và luồng giữ được context reply. Nếu Audit là handler `void` hoặc trả `null`, flow có thể kết thúc ở đó **mà không hề thực hiện bước tra tiếp routing slip**.

## 4. Quy tắc kết thúc chính xác trong Spring Integration

Tài liệu chính thức mô tả Routing Slip ở bước **chọn output channel cho một `AbstractMessageProducingHandler`**. Thuật toán được tham chiếu khi endpoint tạo reply **và không chỉ định `outputChannel`**.

Các quy tắc quan trọng:

1. Lấy entry tương ứng với `routingSlipIndex` từ path.
2. Nếu entry là tên bean của `MessageChannel`, dùng channel ấy làm output và tăng index trong reply.
3. Nếu entry là `RoutingSlipRouteStrategy`, gọi strategy để quyết định tên channel.
4. Khi strategy trả về một channel hợp lệ, **index vẫn ở entry strategy đó**; strategy có thể được gọi lại ở lượt xử lý tiếp.
5. Khi strategy trả về `null` hoặc chuỗi rỗng, framework bỏ qua entry strategy bằng cách tăng index, rồi xét entry tiếp theo.
6. **Khi index vượt qua phần tử cuối, quay về hành vi `replyChannel` tiêu chuẩn.**

Do đó **“hết route” nghĩa là không còn đích phải đi theo itinerary của header**, không có nghĩa bắt buộc phải có một channel tên `finish` hay `done`. Nếu bạn muốn một bước xử lý kết quả bắt buộc trước khi trả về, hãy thêm bước đó vào path hoặc cấu hình một terminal handler rõ ràng.

Một điểm dễ bị bỏ qua: **output channel khai báo tường minh của endpoint được ưu tiên**. Nếu `orders.charge` có output channel cố định `orders.next`, routing slip không quyết định bước tiếp tại thời điểm đó. Kết quả có thể đi vòng khác dự kiến hoặc khiến routing slip không tiến lên theo thiết kế. Tránh trộn output cố định và routing slip mà không ghi rõ vì sao.

## 5. Một ví dụ request–reply hoàn chỉnh theo ba bước

Ví dụ dưới dùng Java record để dễ nhìn thấy thay đổi state qua từng bước:

~~~java
public record OrderState(
    String orderId,
    boolean validated,
    boolean charged,
    boolean audited
) {}
~~~

**Gateway** là nơi caller đặt yêu cầu và đợi kết quả; Reply được chuyển về theo cơ chế messaging của Spring Integration:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.entry")
public interface OrderProcessingGateway {
    OrderState process(OrderState order);
}
~~~

Đặt routing slip bằng một **HeaderEnricher**. Đây là kiểu cấu hình Java dựa trên thành phần `RoutingSlipHeaderValueMessageProcessor` của Spring Integration:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class OrderRoutingSlipConfiguration {

    @Bean
    @Transformer(
        inputChannel = "orders.entry",
        outputChannel = "orders.validate")
    public HeaderEnricher attachRoutingSlip() {
        return new HeaderEnricher(Collections.singletonMap(
            IntegrationMessageHeaderAccessor.ROUTING_SLIP,
            new RoutingSlipHeaderValueMessageProcessor(
                "orders.charge",
                "orders.audit")));
    }
}
~~~

Việc đặt `outputChannel = "orders.validate"` trên HeaderEnricher có chủ đích: nó đưa message **vào bước đầu**. Sau đó các Service Activator không tự chỉ định output channel, để Routing Slip điều khiển:

~~~java
@MessageEndpoint
public class OrderStepHandlers {

    @ServiceActivator(inputChannel = "orders.validate")
    public OrderState validate(OrderState input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new IllegalArgumentException("Missing orderId");
        }
        return new OrderState(
            input.orderId(), true, input.charged(), input.audited());
    }

    @ServiceActivator(inputChannel = "orders.charge")
    public OrderState charge(OrderState input) {
        if (!input.validated()) {
            throw new IllegalStateException("Order not validated");
        }
        return new OrderState(
            input.orderId(), true, true, input.audited());
    }

    @ServiceActivator(inputChannel = "orders.audit")
    public OrderState audit(OrderState input) {
        if (!input.charged()) {
            throw new IllegalStateException("Order not charged");
        }
        return new OrderState(
            input.orderId(), true, true, true);
    }
}
~~~

**Đường đi dự kiến:** `orders.entry → orders.validate → orders.charge → orders.audit → replyChannel của Gateway`. Kết quả cuối có ba cờ `true`. Ví dụ giả định các handler trả object bình thường, channel dispatch đồng bộ và context reply do Gateway thiết lập còn được giữ qua message flow.

Đây là minh họa học thuật: thao tác thanh toán và audit thực tế là side effect cần port riêng, transaction/idempotency và quan sát lỗi. Đoạn code cố tình chỉ biến đổi immutable state để làm rõ điều kiện **handler phải trả reply**.

### Vì sao đoạn này thật sự hết route?

Header enricher tạo path gồm **hai** entry. Khi Validate tạo reply, entry thứ nhất đưa message tới Charge. Khi Charge tạo reply, entry thứ hai đưa message tới Audit. Khi Audit tạo reply, không còn entry thứ ba; framework quay lại xét `replyChannel` chuẩn của message. Nếu Gateway còn chờ và reply được gửi thành công, caller sẽ thấy `OrderState` cuối cùng.

**Không nên** thêm `orders.entry` vào cuối path để “gửi kết quả về nơi bắt đầu”; điều đó có thể tạo vòng xử lý lặp lại. Đường trả lời của Gateway được quản lý bằng `replyChannel`, không phải bằng cách tự route ngược vào request channel.

## 6. Hết routing slip khác gì kết thúc toàn bộ workflow?

Phân biệt bốn mốc:

| Mốc | Điều đã xảy ra | Điều **chưa** được bảo đảm |
|---|---|---|
| **Routing slip exhausted** | Không còn entry điều phối trong header | Không chứng minh tác dụng phụ đã commit |
| **Handler cuối trả reply** | Có message kết quả để phân phối | Không chứng minh caller đã nhận được |
| **Gateway nhận reply** | Lời gọi đồng bộ có kết quả | Không chứng minh notification/broker downstream đã xác nhận |
| **Business workflow completed** | Đã thỏa tiêu chí hoàn tất nghiệp vụ đã định nghĩa | Không suy ra chỉ từ index hoặc một Boolean `send()` |

Ví dụ, Audit trả về `OrderState(audited=true)` nhưng tác vụ gửi email hoặc ghi sổ kế toán vẫn đang chạy bất đồng bộ. Gateway nhận reply không chứng minh những tác vụ khác đã xong. Nếu nghiệp vụ yêu cầu tất cả bước bắt buộc phải thành công, hãy thể hiện chúng trong flow bằng result/status, transaction boundary và cơ chế tổng hợp có chủ đích.

Với các message fire-and-forget, có thể không có caller nào chờ `replyChannel`. Khi đó kết thúc theo Routing Slip cần được biểu diễn bằng một **terminal consumer** có ý nghĩa hoặc một event hoàn tất; không giả định cứ hết path là tự phát tín hiệu cho hệ thống ngoài.

## 7. Vì sao handler cuối trả `void` hoặc `null` dễ gây nhầm lẫn?

Xét hai dạng handler:

~~~java
@ServiceActivator(inputChannel = "orders.audit")
public OrderState auditWithReply(OrderState order) {
    return auditService.markAudited(order);
}

@ServiceActivator(inputChannel = "orders.audit")
public void auditWithoutReply(OrderState order) {
    auditService.writeOnly(order);
}
~~~

**Hai ví dụ trên là hai lựa chọn thay thế**, không khai báo đồng thời trên cùng channel trong ứng dụng mẫu.

`auditWithReply` tạo ra reply để framework tiếp tục xác định điểm đến. Khi path cạn, reply có thể về Gateway. `auditWithoutReply` chỉ làm side effect và kết thúc handler; không có reply message để cơ chế routing slip gửi tiếp. Nếu Gateway mong đợi kết quả, nó có thể phải chờ đến timeout.

Do đó cần xác định rõ **hợp đồng của endpoint cuối**:

- **Request–reply:** handler cuối trả `OrderResult`/`OrderState` để caller nhận kết quả.
- **One-way:** handler cuối cố ý không reply, nhưng caller không được chờ một response đồng bộ; nên có cơ chế ack/status khác nếu bắt buộc.
- **Kết thúc có xác nhận:** handler cuối tạo một completion event hoặc ghi trạng thái bền vững và có chính sách retry/idempotency.
- **Kết thúc lỗi:** handler ném exception; đây là đường lỗi, không phải hành vi “hết route bình thường”.

**Câu hỏi kiểm tra:** sau khi message đi hết path, đối tượng nào sở hữu trách nhiệm xác nhận hoàn tất: Gateway, một terminal handler, state store hay upstream broker? Nếu không chỉ ra được, thiết kế có thể chỉ “hết đường” chứ chưa “xong việc”.

## 8. Khi không có `replyChannel` thì sao?

Quy tắc framework là **quay về xử lý reply tiêu chuẩn**, không hứa hẹn sẽ có một reply channel hợp lệ. Hành vi thực tế phụ thuộc loại endpoint, kiểu giao tiếp và cấu hình message:

1. **Có Gateway/request–reply:** Gateway thường tạo hoặc quản lý reply channel; handler cuối trả reply và caller nhận kết quả khi mọi thứ hoạt động đúng.
2. **Không có caller chờ reply:** chưa chắc có channel nào nhận kết quả cuối; cần thiết kế một terminal sink hoặc output channel phù hợp.
3. **Reply channel sai hoặc không có subscriber:** message có thể gặp lỗi delivery, hoặc luồng xử lý không đạt trạng thái mong muốn theo cấu hình.
4. **Reply channel đã bị thay đổi/mất ở adapter:** Gateway có thể timeout dù một số bước đã chạy.

**Đừng thêm “chế độ kết thúc mặc định” bằng cách xóa routing slip header ở giữa flow**. Điều đó thay đổi semantics: khi các bước sau chưa hoàn tất, flow có thể gửi reply sớm. Nếu cần cắt ngắn quy trình, hãy quyết định thông qua route strategy hoặc một điểm điều phối có hợp đồng kết thúc rõ ràng.

## 9. RoutingSlipRouteStrategy có thể quyết định lúc nào chuyển bước

Path không nhất thiết chỉ chứa tên channel tĩnh. Một entry có thể là `RoutingSlipRouteStrategy`; strategy nhìn vào **request message** và **reply hiện tại** để trả về tên channel tiếp theo.

Điểm khác biệt quan trọng:

- Strategy trả về **tên channel khác rỗng**: chuyển message tới channel đó, nhưng **không tăng index**. Lần sau strategy còn có thể được gọi lại.
- Strategy trả về **`null` hoặc chuỗi rỗng**: entry strategy được coi là đã kết thúc; framework tăng index để xét entry kế tiếp.
- Khi đã duyệt hết path: quay về hành vi `replyChannel` bình thường.

~~~mermaid
flowchart TD
    Q["Endpoint tạo reply, không có outputChannel"] --> I["Đọc routingSlipIndex"]
    I --> D{"Entry hiện tại?"}
    D -->|"MessageChannel"| C["Gửi tới channel, tăng index"]
    D -->|"RoutingSlipRouteStrategy"| ST["Gọi getNextPath(request, reply)"]
    ST -->|"Tên channel"| SAME["Gửi channel, giữ index"]
    ST -->|"null / rỗng"| NEXT["Tăng index"]
    NEXT --> I
    D -->|"Hết path"| RP["Dùng replyChannel chuẩn"]
~~~

Ví dụ logic định tuyến có thể yêu cầu kiểm tra trạng thái nhiều lượt:

~~~text
Path = [reviewStrategy, auditChannel]

Lượt 1: reviewStrategy trả "reviewChannel" → xử lý review
Lượt 2: reviewStrategy trả "reviewChannel" → kiểm tra lại
Lượt 3: reviewStrategy trả null           → bỏ qua strategy, sang auditChannel
Lượt 4: Audit trả reply, path cạn         → replyChannel
~~~

**Nguy cơ vòng lặp:** nếu strategy luôn trả cùng một channel và không có điều kiện thoát, index không tăng; message có thể đi vòng vô hạn. Cần giới hạn số lượt, timeout, trạng thái tiến độ và tiêu chí dừng kiểm thử được.

**Nguy cơ sai kiểu reply:** reply của một POJO service có thể là object domain thuần, không phải `Message<?>`. Nếu SpEL của strategy tham chiếu `reply.headers` nhưng reply thực tế chỉ là `OrderState`, biểu thức có thể thất bại. Hãy kiểm soát kiểu được chấp nhận và chỉ đọc thuộc tính có thực.

## 10. Để lộ trạng thái kết thúc có chủ đích

Trong thực tế, các bên liên quan thường cần biết **đơn hàng thành công hay thất bại**. Có ba cách thể hiện hợp đồng kết thúc:

| Cách | Khi dùng | Hợp đồng |
|---|---|---|
| **Gateway reply** | Tác vụ ngắn, đồng bộ, caller chờ | Trả result sau khi bước cuối sinh reply và routing slip cạn |
| **Terminal handler + completion event** | Nhiều hệ thống bất đồng bộ | Ghi trạng thái và phát `OrderCompleted` khi đạt điều kiện |
| **Stateful process manager** | Quy trình dài, nhiều retry/nhánh | Lưu tiến độ, timeout, compensation, checkpoint |

Khi dùng completion event, nên có một điểm phát duy nhất có thể kiểm soát idempotency. Đừng để mỗi handler thấy “không còn route” rồi tự phát event giống nhau, vì retry có thể phát trùng.

Một result nghiệp vụ:

~~~java
public record ProcessResult(
    String orderId,
    String outcome,       // COMPLETED / REJECTED / FAILED
    String lastStep,
    String correlationId
) {}
~~~

Thông tin `lastStep` là metadata để hỗ trợ truy vết, không thay thế bằng chứng các tác dụng phụ đã commit. Nếu có billing, inventory hoặc payment, chỉ dùng outcome `COMPLETED` khi đã đạt tiêu chí nghiệp vụ đã công bố.

## 11. Trường hợp route trống ngay từ đầu

Một message có thể nhận routing slip không có entry hợp lệ, hoặc một route strategy chỉ trả giá trị null/rỗng ngay từ đầu. Cần phân biệt:

| Tình huống | Nghĩa vụ thiết kế |
|---|---|
| **Empty itinerary hợp lệ** | Xác định liệu có được trả reply ngay hay không |
| **Không khai báo itinerary nhưng nghiệp vụ yêu cầu bước bắt buộc** | Reject/validation error; không đánh dấu hoàn thành |
| **Strategy trả null có chủ đích** | Tiếp tục xét entry sau hoặc reply theo quy tắc |
| **Tên channel trong path không tồn tại** | Đây là lỗi cấu hình/resolution, không phải hoàn thành thành công |
| **Message mất routingSlip khi đi qua broker** | Thiếu thông tin điều phối; khôi phục từ state store hoặc reject theo hợp đồng |

Nếu dùng request–reply cho một trường hợp không cần xử lý gì, tốt hơn nên trả kết quả tại một endpoint terminal minh bạch, thay vì dựa vào hành vi ngầm của path rỗng ở một topology chưa có reply producer.

**Không gán route trực tiếp từ dữ liệu user chưa kiểm tra.** Danh sách tên channel chỉ nên được chọn từ tập được ứng dụng cho phép; sai giá trị không được biến thành quyền điều hướng tới một bean bất kỳ.

## 12. Hết route ≠ exception, Filter discard hay timeout

Các hiện tượng sau rất dễ bị nhầm trong log:

| Dấu hiệu | Nguyên nhân có thể | Phân loại |
|---|---|---|
| Index đã tới cuối path và caller nhận reply | Routing slip cạn bình thường | **Hoàn tất điều phối theo path** |
| Một handler trả `null` | Không tạo reply để đi tiếp | **Flow dừng sớm**, không phải hết path |
| Filter bỏ message | Predicate không đạt, có thể có discard channel | **Message bị lọc** |
| Handler ném exception | Lỗi nghiệp vụ/kỹ thuật | **Error path**, không tự xử lý như completion |
| Tên channel không được phân giải | Lỗi route config/bean | **Routing error** |
| Caller timeout | Không nhận reply trong hạn | **Không đủ thông tin** để kết luận handler chưa chạy |
| Broker gửi lại message | Chưa ack hoặc policy redelivery | **Delivery retry**, có thể có side effect trước đó |

**Thực hành quan trọng:** dashboard nên có metric riêng cho *routing-slip-exhausted*, *terminal-success*, *terminal-error*, *timeout* và *early-stop*. Không gom tất cả thành “done”; sẽ không truy vết được mất message và các ca retry.

## 13. Retry và idempotency khi đã qua vài bước

Giả sử đường đi là `validate → charge → audit`. Charge đã thu tiền thành công nhưng Audit lỗi mạng. Nếu retry **toàn bộ** Gateway call từ đầu:

~~~text
Lượt 1:
validate: OK
charge: ĐÃ THU TIỀN
audit: TIMEOUT
caller: exception/timeout

Lượt 2:
validate: OK
charge: NGUY CƠ THU LẠI TIỀN
audit: ...
~~~

Routing slip không ghi nhận bền vững “Charge đã commit” và cũng không tự bảo đảm exactly-once. Khi có side effect, mỗi bước cần:

1. **Idempotency key ổn định**: ví dụ `orderId + actionType` hoặc event ID; ràng buộc unique ở nơi thực hiện side effect.
2. **Checkpoint/progress store** nếu muốn tiếp tục từ bước đã hoàn tất sau restart.
3. **Retry giới hạn** theo loại lỗi; lỗi validation không nên retry vô hạn.
4. **Transaction/outbox** nếu cần liên kết thay đổi database và phát event.
5. **Compensation** cho nghiệp vụ dài khi không thể rollback phân tán.

Không lấy `routingSlipIndex` làm bằng chứng thanh toán thành công; index phản ánh việc điều phối route đã xét, không thay thế transaction log. Message có thể được chuyển tiếp nhưng handler phía sau vẫn thất bại.

## 14. Routing Slip trong môi trường phân tán: khả năng serialize

Spring Integration cho phép path chứa tên channel, tên `RoutingSlipRouteStrategy` hoặc một biểu thức SpEL. Trong môi trường chỉ ở một JVM, biểu thức động có thể tiện; **qua broker, persistent MessageStore hoặc ranh giới JVM, cần cân nhắc tính serializable**.

Các biểu thức nội tuyến có thể được framework chuyển thành đối tượng `ExpressionEvaluatingRoutingSlipRouteStrategy` phụ thuộc `BeanFactory` và không serializable. Đưa một message chứa đối tượng đó qua cơ chế serialize có thể gây `NotSerializableException`.

**Khuyến nghị thực hành:**

- Khi đi qua ranh giới phân tán, hạn chế đưa object/strategy phụ thuộc JVM vào wire headers.
- Nếu cần strategy dùng SpEL, đăng ký strategy làm bean với tên định danh theo tài liệu và cấu hình các entry tương thích.
- Định nghĩa lộ trình ở dạng DTO/step IDs thuần dữ liệu khi cần truyền qua broker; tại mỗi service biên, khôi phục routing context theo contract của service.
- Kiểm thử serialize → deserialize → tiếp tục từ checkpoint, không chỉ test trong JVM.
- Tách routing metadata điều phối nội bộ khỏi business event công khai, tránh để bên ngoài tùy ý sửa path.

Đặc biệt, **không tự ý đưa toàn bộ Spring MessageHeaders qua JSON**: có header chứa object nội bộ như reply channel, error channel hoặc route strategy; một số object không thể serialize hoặc không an toàn để trao đổi với hệ thống ngoài.

## 15. Routing Slip, Gateway và timeout

Trong luồng đồng bộ, Gateway thường chờ reply đến từ handler cuối sau khi path cạn. Nhưng thời gian chờ phụ thuộc **tất cả các bước**, không chỉ bước cuối:

\[
T_{\text{gateway}} \approx T_{\text{validate}} + T_{\text{charge}} + T_{\text{audit}} + T_{\text{overhead}}
\]

Nếu `charge` đợi dịch vụ thanh toán lâu, Gateway có thể timeout trước khi message đi tới Audit; nếu `audit` trả `null`, Gateway cũng có thể chờ dù các side effect trước đó đã được thực hiện.

Khi thêm `ExecutorChannel`, `QueueChannel` hoặc broker, có thể xuất hiện ranh giới thực thi bất đồng bộ và cơ chế reply/error khác. Cần thiết kế **replyChannel propagation, timeout, correlation, error channel, delivery acknowledgment** tại từng ranh giới; routing slip không giải quyết tự động.

**Không đánh dấu thất bại giao dịch chỉ vì Gateway timeout.** Trước khi retry, cần xác minh trạng thái bằng idempotency key/checkpoint hoặc mô hình truy vấn trạng thái nghiệp vụ.

## 16. Kết hợp với Filter, Router, Splitter và Aggregator

Routing Slip không thay thế các pattern khác:

- **Filter** loại message sai hợp đồng trước khi bắt đầu lộ trình, hoặc chuyển sang reject channel. Drop message cần được báo cho bên chờ reply nếu có.
- **Content-Based Router** có thể chọn giữa nhiều tuyến trước khi gắn path, ví dụ đơn quốc tế cần thêm review.
- **Transformer** chuẩn hóa payload và giữ metadata cần thiết để đi tiếp.
- **Gateway** cung cấp hợp đồng request–reply/timeout tại ranh giới ứng dụng.
- **Splitter/Aggregator** xử lý việc một message tách thành nhiều phần và gộp kết quả theo correlation; Routing Slip một mình không thực hiện việc gộp nhóm.

~~~mermaid
flowchart LR
    G["Gateway"] --> F{"Filter hợp đồng"}
    F -->|"Hợp lệ"| T["Transformer + tạo Routing Slip"]
    F -->|"Không hợp lệ"| ERR["Reject / error reply"]
    T --> V["Validate"]
    V --> C["Charge"]
    C --> A["Audit"]
    A --> E{"Hết routing slip"}
    E --> R["replyChannel → Gateway"]
~~~

Khi một bước trong lộ trình tự dùng Splitter phát ra nhiều message con, phải xác định **mỗi message con có giữ cùng routing slip hay không**, ai chịu trách nhiệm gộp và thời điểm nào được coi là trả reply cho itinerary gốc. Nếu muốn một request nhận **một** kết quả cuối, thường cần Aggregator hoặc một coordinator phát đúng một reply.

## 17. Unit test và integration test: chứng minh hết route đúng nghĩa

Trước khi test end-to-end, nên có test cho handler riêng để xác minh chúng trả reply và không tự tạo side effect ngoài dự kiến. Với ví dụ `OrderStepHandlers`, unit test xác minh:

~~~java
@Test
void stepsReturnNewStates() {
    OrderStepHandlers handlers = new OrderStepHandlers();
    OrderState initial =
        new OrderState("O-101", false, false, false);

    OrderState valid = handlers.validate(initial);
    OrderState charged = handlers.charge(valid);
    OrderState audited = handlers.audit(charged);

    assertTrue(audited.validated());
    assertTrue(audited.charged());
    assertTrue(audited.audited());
    assertFalse(initial.validated());
}
~~~

Unit test này **chưa** chứng minh routing slip tự hoạt động; nó chỉ kiểm tra contract “mỗi bước trả object kết quả”. Phải có integration test với Spring Integration context thực:

~~~java
@SpringJUnitConfig(classes = {
    OrderRoutingSlipConfiguration.class,
    OrderStepHandlers.class
})
class RoutingSlipCompletionTest {

    @Autowired
    OrderProcessingGateway gateway;

    @Test
    void returnsResultAfterFinalStep() {
        OrderState result = gateway.process(
            new OrderState("O-101", false, false, false));

        assertTrue(result.validated());
        assertTrue(result.charged());
        assertTrue(result.audited());
    }
}
~~~

Đây là ví dụ định hướng test; khi sử dụng thực tế, cần cấu hình quét Gateway interface và Spring test integration phù hợp (có thể dùng `@IntegrationComponentScan` như ở configuration). Không cần HTTP server, broker hoặc database khi tất cả handler ở trong JVM.

### Ma trận kiểm thử tối thiểu

| Case | Thiết lập | Điều cần chứng minh |
|---|---|---|
| Đi hết path | Validate → Charge → Audit, cả ba trả reply | Gateway nhận kết quả có đủ ba cờ |
| Path rỗng hợp lệ | Có endpoint trả reply cuối theo contract | Không bỏ sót bước bắt buộc; reply được xử lý rõ ràng |
| Handler giữa trả `null` | Charge không reply | Audit không được gọi; Gateway có đường timeout/error rõ |
| Handler cuối `void` | Audit chỉ side effect | Không tự suy ra Gateway nhận reply |
| Lỗi ở Validate | `orderId` trống | Exception/error path; không thu tiền |
| Lỗi ở Charge | Dịch vụ thanh toán timeout | Audit không bị báo thành công; retry có giới hạn |
| Channel không tồn tại | Path chứa tên bean sai | Routing error được quan sát; không coi là hết path |
| Handler có output riêng | Charge override outputChannel | Kiểm tra routing slip không được dùng tại bước đó |
| Strategy trả channel | Dynamic strategy còn đang chọn nhánh | Index không tăng cho strategy ở lượt này |
| Strategy trả null/rỗng | Chuyển sang entry sau | Index tăng; nếu hết thì fallback replyChannel |
| Strategy luôn trả channel | Không có điều kiện thoát | Giới hạn vòng lặp/timeout và cảnh báo |
| Caller timeout | Audit chạy chậm | Không kết luận side effect chưa xảy ra |
| Redelivery cùng order | Retry sau khi Charge commit | Không thu tiền lần thứ hai |
| Cross-JVM | Serialize message có routing slip | Không chứa object/inline strategy không serializable |
| Splitter/Aggregator | Nhiều message con với correlation | Không phát nhiều reply ngoài ý muốn |

Thay các handler production bằng test doubles khi cần đếm số lần gọi. Tránh kiểm thử “hết route” chỉ bằng việc log cuối xuất hiện; log không chứng minh reply được phát đúng và caller nhận được.

## 18. Observability: đo tiến độ lộ trình và điểm kết thúc

Một sự kiện có thể đi qua nhiều endpoint và biến đổi payload. Cần dữ liệu để trả lời ba câu hỏi:

1. **Message đang ở bước nào?**
2. **Nó hết routing slip bình thường, dừng sớm hay bị lỗi?**
3. **Kết quả cuối đã tới nơi cần nhận chưa?**

Đề xuất các tín hiệu:

| Tín hiệu | Mục đích |
|---|---|
| `route.path.size` và `route.step.index` | Theo dõi tổng bước và bước hiện tại |
| `route.step.name` | Xác định channel/handler đang xử lý |
| `route.step.duration` | Phát hiện handler chậm |
| `route.exhausted.count` | Đếm tình huống dùng hết itinerary |
| `route.early_stop.count` | Handler trả `null` hoặc bị Filter drop trước khi hết path |
| `route.error.count` theo reason code | Phân loại lỗi runtime/mapping |
| `gateway.reply.duration` và timeout | Theo dõi hợp đồng kết quả |
| `workflow.completed.count` | Đếm theo tiêu chí nghiệp vụ, **không dùng chỉ số index thay thế** |

Tùy Spring Integration/Micrometer version và cấu hình, một số số liệu cần tự instrument tại interceptor/handler. **Tên metric ở bảng là tên đề xuất**, không khẳng định là các tên metric mặc định của framework.

Để truy vết, giữ event ID, business ID và trace/correlation context theo hợp đồng. Không đưa `orderId` hay `eventId` làm metric tag nếu cardinality lớn; dùng log/tracing có kiểm soát. Không log toàn bộ payload hoặc headers nhạy cảm.

## 19. Sai lầm thường gặp

**“Hết route là tự động hoàn thành nghiệp vụ.”** Sai. Framework chỉ xử lý việc chọn channel tiếp theo và fallback `replyChannel`; transaction, side effect, ack và process status cần thiết kế riêng.

**“Handler `void` sẽ tự đi tiếp sang route sau.”** Sai trong flow request–reply thông thường: không có reply thì không có message để dispatch tiếp.

**“Thêm channel tên `finish` vào path là bắt buộc.”** Không bắt buộc. Có thể dùng replyChannel chuẩn; nếu cần terminal sink, hãy định nghĩa rõ hành vi kết thúc.

**“Strategy trả được tên channel là index tăng.”** Sai. Với `RoutingSlipRouteStrategy` trả channel, index không tăng; strategy có thể tiếp tục được gọi. Nó chỉ bị bỏ qua khi trả null/rỗng.

**“outputChannel tường minh và routing slip cùng điều khiển một bước như nhau.”** Sai. Output được cấu hình cho handler có ảnh hưởng ưu tiên và có thể làm routing slip không được tham chiếu tại bước đó.

**“Gateway timeout nghĩa là Charge chưa chạy.”** Sai. Caller có thể không nhận reply nhưng một số side effect đã commit. Retry cần idempotency và truy vấn trạng thái.

**“Dùng biểu thức SpEL inline trong routing slip qua broker luôn an toàn.”** Sai. Object strategy được sinh có thể không serializable; dùng hợp đồng/strategy bean phù hợp và kiểm thử biên JVM.

**“Header routing slip có thể lấy nguyên từ client.”** Không nên: giá trị có thể điều khiển flow vào channel không được phép, tạo vòng lặp hoặc vượt validation. Lộ trình phải được dựng/kiểm tra ở application boundary.

**“Một message vào Splitter sẽ trả đúng một reply khi routing slip cạn.”** Không tự động: số lượng message con và release strategy của Aggregator quyết định cách phát kết quả.

## 20. Bài thực hành: xác nhận đường đi thật sự kết thúc

Xây dựng tính năng **OrderRoutingSlip** với ba bước và một Gateway:

1. **Xác định hợp đồng:** `OrderState` và `OrderProcessingGateway.process()` trả result đồng bộ.
2. **Gắn Routing Slip:** HeaderEnricher thêm path `orders.charge → orders.audit` trước khi gửi vào `orders.validate`.
3. **Viết các Service Activator:** mỗi bước trả một state mới; không khai báo outputChannel cho các handler muốn routing slip điều phối.
4. **Happy path:** xác minh caller nhận đủ trạng thái đã validate, charge và audit, không route ngược vào input.
5. **Early-stop:** đổi Audit thành `void` để thấy khác biệt giữa “không còn reply” và “routing slip đã được dùng hết rồi reply”.
6. **Failure path:** cho Charge ném lỗi, thử retry và bảo vệ side effect bằng idempotency key.
7. **Dynamic strategy:** thêm một entry cho review có điều kiện; test trả channel, trả null và trường hợp có nguy cơ lặp.
8. **Observability:** đo `route.step.index`, thời gian handler, số completion và timeout theo correlation ID.
9. **Cross-JVM:** nếu có broker/persistent store, kiểm thử serialization và cách khôi phục lộ trình sau restart.

**Tiêu chí hoàn thành:** có sơ đồ sequence, giải thích được vị trí index trước/sau mỗi bước, chứng minh kết quả quay về `replyChannel` sau khi path cạn, có test phân biệt hết path với handler `null`/error/timeout và nêu rõ giới hạn durability/idempotency.

## 21. Ghi nhớ

Trong Spring Integration, **kết thúc khi hết route** nghĩa là **không còn điểm đến tiếp theo trong header `routingSlip`**. Khi một handler có reply và không định nghĩa `outputChannel` riêng, Routing Slip được dùng để chọn channel tiếp theo; **sau khi path cạn, việc phân phối reply trở lại quy tắc `replyChannel` thông thường**.

Đừng đồng nhất việc cạn đường đi với thành công nghiệp vụ, đừng mặc định handler `void` sẽ tiếp tục, và đừng để strategy chạy lặp vô hạn. Hãy xác định terminal behavior, retry, idempotency, error path và correlation rõ ràng, đồng thời kiểm thử kết quả ở cả Gateway lẫn các bước xử lý.

### Tài liệu tham khảo

- Spring Integration Reference, **Routing Slip**: https://docs.spring.io/spring-integration/reference/router/routing-slip.html
- Enterprise Integration Patterns, **Routing Slip**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/RoutingTable.html
