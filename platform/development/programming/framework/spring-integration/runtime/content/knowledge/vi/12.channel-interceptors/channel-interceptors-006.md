# Interceptor order và nhiều interceptor

Trong Spring Integration, **MessageChannel** là điểm đi qua của message giữa các endpoint. Một channel có thể gắn nhiều **ChannelInterceptor** để chuẩn hóa header, kiểm tra message, ghi audit, đo thời gian hoặc quan sát luồng xử lý. Khi có nhiều interceptor, thứ tự gọi quyết định interceptor nào nhìn thấy message trước, interceptor nào có thể thay đổi dữ liệu mà interceptor sau nhận được và lúc nào phần dọn dẹp được chạy.

Chủ đề này thuộc nhóm **Channel interceptor** trong Spring Integration Runtime. Nắm được thứ tự interceptor giúp đọc đúng vòng đời gửi và nhận message, đồng thời chẩn đoán khác biệt giữa xử lý đồng bộ, dispatch qua executor và channel có hàng đợi.

## 1. Thứ tự trong một lần gửi message

Các interceptor được gắn với channel theo một danh sách. Với một lần gửi, Spring gọi **preSend** theo thứ tự từ đầu danh sách đến cuối danh sách. Message trả về từ interceptor trước sẽ trở thành đầu vào của interceptor tiếp theo. Vì vậy, nếu interceptor đầu tiên tạo hoặc sửa header rồi trả về message mới, interceptor sau sẽ nhìn thấy header đó.

Sau khi channel thực hiện thao tác gửi, **postSend** được gọi theo thứ tự danh sách. Tham số **sent** cho biết thao tác gửi của channel thành công hay không. Sau cùng, **afterSendCompletion** được gọi theo thứ tự ngược lại đối với các interceptor đã tham gia thành công vào giai đoạn **preSend**. Hook này nhận thêm **Exception** để xử lý phần hoàn tất hoặc dọn dẹp khi thao tác gửi gặp lỗi.

Ví dụ danh sách có ba interceptor A, B và C:

~~~text
preSend:             A -> B -> C
channel.doSend(...)
postSend:            A -> B -> C
afterSendCompletion: C -> B -> A
~~~

**postSend** và **afterSendCompletion** có vai trò khác nhau. **postSend** quan sát kết quả gửi mà channel trả về. **afterSendCompletion** phù hợp với việc đóng tài nguyên hoặc khôi phục trạng thái đã thiết lập trong **preSend**, vì nó được gọi khi lời gọi gửi kết thúc, kể cả khi có exception. Thứ tự hoàn tất ngược giúp interceptor được gọi sau cùng ở giai đoạn chuẩn bị có cơ hội dọn dẹp trước.

### Dừng gửi bằng preSend

**preSend** trả về một **Message** để tiếp tục gửi. Nếu trả về **null**, interceptor từ chối message và chuỗi gửi dừng tại đó: channel không thực hiện thao tác gửi và **postSend** không được gọi cho lần gửi bị chặn. Các interceptor đã đi qua giai đoạn **preSend** vẫn nhận callback **afterSendCompletion** theo thứ tự ngược để có thể dọn dẹp.

Không nên trả về **null** do một điều kiện ngoài dự kiến mà không ghi nhận lý do. Khi dùng interceptor để lọc hoặc chặn message, hãy log channel, message ID hoặc correlation ID cùng nguyên nhân từ chối. Nếu điều kiện đó là quy tắc nghiệp vụ chính, cân nhắc đặt nó trong filter endpoint để luồng dễ đọc và dễ kiểm thử hơn.

## 2. Thứ tự trong một lần nhận message

Các hook nhận message được sử dụng với channel hỗ trợ thao tác **receive**, thường là các channel kiểu **PollableChannel** như **QueueChannel**. **preReceive** được gọi theo thứ tự danh sách trước khi channel lấy message. Nếu một interceptor trả về **false**, thao tác nhận bị ngăn lại. Khi nhận được message, **postReceive** được gọi theo thứ tự danh sách; mỗi interceptor có thể trả về message đã biến đổi để interceptor kế tiếp sử dụng.

**afterReceiveCompletion** được gọi theo thứ tự ngược đối với các interceptor đã tham gia giai đoạn **preReceive**. Hook này nhận message (nếu có) và exception (nếu có), nên phù hợp để khôi phục trạng thái hoặc giải phóng tài nguyên sau thao tác nhận.

~~~text
preReceive:             A -> B -> C
channel.receive(...)
postReceive:            A -> B -> C
afterReceiveCompletion: C -> B -> A
~~~

Từ Spring Integration 5.1, **postReceive** không còn được gọi khi không nhận được message. Nếu cần xử lý phần hoàn tất kể cả khi hàng đợi rỗng hoặc thao tác nhận phát sinh exception, hãy dùng **afterReceiveCompletion**.

## 3. Cấu hình nhiều interceptor trên cùng channel

Với interceptor cục bộ, **addInterceptor** thêm interceptor vào cuối danh sách. Do đó, thứ tự gọi có thể được kiểm soát trực tiếp tại nơi tạo channel. **addInterceptor(index, interceptor)** cho phép chèn tại một vị trí cụ thể; chỉ nên dùng chỉ số khi thứ tự đó có ý nghĩa rõ ràng và được duy trì nhất quán.

~~~java
@Bean
MessageChannel ordersChannel() {
    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(new HeaderNormalizationInterceptor());
    channel.addInterceptor(new OrderAuditInterceptor());
    channel.addInterceptor(new DispatchMetricsInterceptor());
    return channel;
}
~~~

Trong ví dụ này, **HeaderNormalizationInterceptor** chạy trước, **OrderAuditInterceptor** nhận message sau khi header đã được chuẩn hóa, rồi **DispatchMetricsInterceptor** quan sát kết quả của các bước trước. Các interceptor cục bộ được gọi theo đúng thứ tự đã thêm vào danh sách.

Nếu cấu hình bằng Java DSL, có thể gắn interceptor vào channel hiện tại bằng **intercept(...)**. Các interceptor truyền vào được thêm theo thứ tự khai báo, sau những interceptor đã có trên channel:

~~~java
IntegrationFlow flow = IntegrationFlow
    .from("orders.input")
    .intercept(normalizeHeaders, auditOrder, measureDispatch)
    .handle(orderHandler)
    .get();
~~~

Hãy xác định rõ channel nào đang được cấu hình. Interceptor gắn vào một channel chỉ quan sát các thao tác đi qua channel đó; nó không tự động bao quanh toàn bộ endpoint hoặc mọi bước trong **IntegrationFlow**.

## 4. Global interceptor và thuộc tính order

Khi cùng một hành vi cần áp dụng cho nhiều channel, Spring Integration cung cấp global channel interceptor. Trong Java configuration, đánh dấu bean bằng **@GlobalChannelInterceptor**; thuộc tính **patterns** giới hạn tên channel được áp dụng. Nếu bỏ **patterns**, interceptor sẽ áp dụng cho mọi channel.

~~~java
@Configuration
class OrderInterceptorConfiguration {

    @Bean
    @GlobalChannelInterceptor(patterns = "orders*", order = -20)
    ChannelInterceptor normalizeOrderHeaders() {
        return new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message, MessageChannel channel) {
                return MessageBuilder.fromMessage(message)
                    .setHeader("flow", "orders")
                    .build();
            }
        };
    }

    @Bean
    @GlobalChannelInterceptor(patterns = "orders*", order = -10)
    ChannelInterceptor auditOrders() {
        return new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message, MessageChannel channel) {
                // Ghi audit bằng channel và message ID.
                return message;
            }
        };
    }

    @Bean
    @GlobalChannelInterceptor(patterns = "orders*", order = 20)
    ChannelInterceptor observeDispatch() {
        return new ChannelInterceptor() {
            @Override
            public void postSend(
                    Message<?> message, MessageChannel channel, boolean sent) {
                // Ghi nhận kết quả gửi của channel.
            }
        };
    }
}
~~~

**order** của **@GlobalChannelInterceptor** điều khiển vị trí chèn global interceptor trên channel:

| Giá trị order | Vị trí |
|---|---|
| Số âm | Trước các interceptor đã cấu hình trực tiếp trên channel |
| Số dương | Sau các interceptor đã cấu hình trực tiếp trên channel |
| Các global interceptor cùng khớp một channel | Được sắp xếp theo giá trị order |
| Không khai báo | Mặc định là 0 |

Vì vậy, trong ví dụ, hai interceptor có **order** âm chạy trước các interceptor cục bộ; **normalizeOrderHeaders** đứng trước **auditOrders** do có giá trị nhỏ hơn. **observeDispatch** có **order** dương nên được chèn sau các interceptor đã cấu hình trực tiếp trên channel. Khi thứ tự có ảnh hưởng đến dữ liệu hoặc side effect, hãy đặt các giá trị **order** khác nhau thay vì dựa vào thứ tự phát hiện bean.

**patterns** dùng để chọn channel theo tên. Có thể giới hạn interceptor cho nhóm channel như **orders***, thay vì áp dụng logging hoặc audit lên toàn bộ channel trong ứng dụng. Từ Spring Integration 5.1, global interceptor cũng được áp dụng cho channel đăng ký động, chẳng hạn channel được tạo qua **IntegrationFlowContext**.

## 5. Không nhầm thứ tự interceptor với thứ tự xử lý giữa các thread

Thứ tự các interceptor trong cùng một lần gọi gửi hoặc nhận được xác định bởi danh sách interceptor. Tuy nhiên, không thể suy ra một thứ tự cố định giữa sự kiện gửi và sự kiện nhận khi channel cho phép hai phía chạy độc lập. Loại channel và thời điểm consumer chờ nhận message đều ảnh hưởng đến trình tự quan sát được.

| Loại channel | Điều xảy ra khi gửi | Ý nghĩa của callback |
|---|---|---|
| **DirectChannel** | Dispatch tới subscriber đồng bộ trong thread gửi | **postSend** chạy sau khi lời gọi dispatch của channel hoàn tất |
| **ExecutorChannel** | Giao việc dispatch cho executor | **postSend** phản ánh việc channel dispatch/gửi tác vụ; không chứng minh handler đã xử lý xong |
| **QueueChannel** | Đưa message vào hàng đợi | Gửi và nhận là hai thao tác riêng; consumer có thể nhận trước hoặc sau khi sender chạy **postSend** |

Với **QueueChannel**, nếu receiver đang chờ sẵn, **preReceive** và **postReceive** có thể xuất hiện trước **postSend** của sender. Nếu sender đưa message vào hàng đợi và hoàn tất trước khi receiver poll, **postSend** sẽ xuất hiện trước các callback nhận. Đây là khác biệt về thời gian giữa hai thread, không phải lỗi thứ tự của interceptor.

Vì vậy, chỉ nên dựa vào quan hệ nằm trong cùng một thao tác: **preSend** xảy ra trước **postSend**, và **preReceive** xảy ra trước **postReceive**. Không dùng thứ tự log giữa sender và receiver để kết luận interceptor đã chạy sai thứ tự. Với **DirectChannel**, luồng nhận không đi qua **preReceive**/**postReceive**; các hook này dành cho thao tác nhận trên pollable channel.

Một điểm cần nhớ khi đo hiệu năng: **afterSendCompletion** hoàn tất lời gọi gửi của channel. Trên **ExecutorChannel**, nó không phải tín hiệu cho biết phần xử lý nghiệp vụ trong consumer đã kết thúc. Muốn đo thời gian xử lý handler, hãy đặt observation hoặc advice ở vị trí bao quanh handler/endpoint, hoặc phát sự kiện đo lường từ chính consumer.

## 6. Thiết kế chuỗi interceptor dễ bảo trì

Một chuỗi interceptor tốt có thứ tự dễ giải thích. Ví dụ với luồng đơn hàng:

1. Chuẩn hóa header và bổ sung metadata dùng chung.
2. Kiểm tra điều kiện kỹ thuật của message trước khi đưa vào channel.
3. Ghi nhận audit hoặc trace ID để các bước sau có thể đối chiếu.
4. Gửi message và ghi nhận kết quả channel trả về.
5. Dọn dẹp trạng thái trong **afterSendCompletion** hoặc **afterReceiveCompletion**.

Không phải interceptor nào cũng cần triển khai mọi callback. Các phương thức mặc định của **ChannelInterceptor** không làm gì hoặc trả lại message/giá trị cho phép tiếp tục, vì vậy mỗi interceptor chỉ nên override những hook thực sự cần thiết.

Một số nguyên tắc thực tế:

- **Giữ interceptor nhẹ.** Tránh gọi dịch vụ từ xa, truy vấn cơ sở dữ liệu hoặc chờ I/O lâu trong **preSend** và **postSend**. Những thao tác đó nằm trên đường gửi và có thể làm tăng độ trễ hoặc giảm thông lượng.
- **Trả lại message đã sửa.** **Message** là bất biến; khi tạo message mới bằng **MessageBuilder**, phải return message đó để interceptor kế tiếp và channel sử dụng.
- **Phân biệt từ chối với lỗi.** Trả **null** từ **preSend** hoặc **false** từ **preReceive** là cách chủ động dừng thao tác. Ném exception biểu thị lỗi và có thể kích hoạt cơ chế xử lý lỗi ở tầng gọi.
- **Không xem completion là transaction commit.** **afterSendCompletion** và **afterReceiveCompletion** kết thúc một lời gọi channel. Chúng không đại diện cho việc toàn bộ flow hoặc transaction của endpoint đã commit.
- **Tránh phụ thuộc vào ThreadLocal qua executor.** Khi message chuyển sang thread khác, trạng thái gắn với thread gửi không tự động xuất hiện ở thread consumer. Nếu cần truyền trace hoặc context, ưu tiên message header hoặc cơ chế propagation phù hợp.
- **Không ghi payload nhạy cảm vào log.** Dùng channel name, message ID, correlation ID, header đã chọn và thời gian xử lý để chẩn đoán.

## 7. Kiểm tra thứ tự khi chạy ứng dụng

Khi một message đi qua nhiều interceptor, hãy xác minh danh sách thực tế trên đúng channel thay vì chỉ suy luận từ tên bean. Với channel triển khai **InterceptableChannel**, **getInterceptors()** trả về danh sách interceptor đã cấu hình ở dạng chỉ đọc. Có thể kiểm tra danh sách này trong lúc khởi động hoặc trong integration test.

Một bài kiểm tra thứ tự có thể dùng danh sách ghi nhận sự kiện:

~~~java
List<String> events = new CopyOnWriteArrayList<>();

// Mỗi interceptor thêm tên của nó vào events trong preSend,
// postSend và afterSendCompletion.
// Gửi một message qua DirectChannel rồi so sánh events
// với thứ tự mong đợi của từng callback.
~~~

Nên kiểm tra riêng các tình huống sau:

- Gửi thành công qua **DirectChannel**.
- Một interceptor trả **null** trong **preSend**.
- **doSend** hoặc một callback phát sinh exception.
- Nhận message từ **QueueChannel** khi có message và khi hàng đợi rỗng.
- Gửi qua **ExecutorChannel**, xác nhận **postSend** không bị hiểu nhầm là consumer đã hoàn tất.
- Channel có cả interceptor cục bộ và global interceptor với **order** âm, dương.

Khi chẩn đoán runtime, đối chiếu channel name, message ID/correlation ID, thread name và timestamp. Nếu log giữa hai phía không theo thứ tự bạn dự đoán, trước tiên hãy xác định channel là đồng bộ, executor hay pollable; sau đó mới kiểm tra thứ tự danh sách interceptor.

## 8. Ghi nhớ

- Interceptor cục bộ được thêm vào danh sách theo thứ tự đăng ký; **addInterceptor** thêm vào cuối danh sách.
- **preSend** và **postSend** chạy theo thứ tự danh sách; **afterSendCompletion** chạy theo thứ tự ngược đối với các interceptor đã tham gia giai đoạn chuẩn bị.
- Với thao tác nhận, **preReceive** và **postReceive** chạy theo thứ tự danh sách; **afterReceiveCompletion** chạy theo thứ tự ngược.
- **@GlobalChannelInterceptor.order** đặt global interceptor trước hoặc sau interceptor cục bộ; các global interceptor được so sánh theo giá trị **order**.
- Thứ tự callback giữa send và receive không cố định trên channel có sender/receiver độc lập.
- **postSend** và **afterSendCompletion** phản ánh vòng đời gửi của channel, không nhất thiết là vòng đời xử lý nghiệp vụ của consumer bất đồng bộ.

## Tài liệu tham khảo

- [Spring Integration Reference — Channel Interceptors](https://docs.spring.io/spring-integration/docs/latest-ga/reference/html/channel.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [GlobalChannelInterceptor API](https://docs.spring.io/spring-integration/docs/latest-ga/api/org/springframework/integration/config/GlobalChannelInterceptor.html)
