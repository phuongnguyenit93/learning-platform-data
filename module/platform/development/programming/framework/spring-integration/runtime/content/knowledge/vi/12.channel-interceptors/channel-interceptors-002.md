# preSend, postSend, afterSendCompletion

Trong Spring Integration, channel là ranh giới mà message đi qua trước khi tới endpoint tiếp theo. Khi cần kiểm tra, bổ sung metadata hoặc ghi nhận kết quả của thao tác gửi message mà không sửa producer và handler, ta có thể đăng ký `ChannelInterceptor`. Ba callback quan trọng ở chiều gửi là `preSend()`, `postSend()` và `afterSendCompletion()`.

Ba callback này nằm ở ba thời điểm khác nhau:

- `preSend()` chạy trước khi channel thực sự gửi message. Nó có thể trả lại message đã được biến đổi hoặc trả `null` để chặn thao tác gửi.
- `postSend()` chạy ngay sau lời gọi gửi và nhận kết quả boolean `sent` của channel.
- `afterSendCompletion()` chạy ở bước hoàn tất, kể cả khi send phát sinh exception, nên phù hợp cho cleanup và ghi nhận kết quả cuối.

Điều quan trọng là `sent=true` chỉ nói thao tác gửi của channel đã thành công theo semantics của channel đó. Nó không tự chứng minh nghiệp vụ downstream đã hoàn tất. Với `QueueChannel`, thành công thường có nghĩa message đã được enqueue; với `ExecutorChannel`, task dispatch đã được executor tiếp nhận. Handler có thể vẫn đang chờ xử lý.

## 1. ChannelInterceptor nằm ở đâu?

`ChannelInterceptor` là strategy interface của Spring Messaging, được Spring Integration sử dụng để xem hoặc thay đổi message khi message được gửi tới hoặc nhận từ `MessageChannel`.

Một channel có thể đăng ký nhiều interceptor. Khi producer gọi `send(message)`, chuỗi interceptor tham gia vào thao tác send trước khi channel thực hiện việc chuyển message.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as MessageChannel
    participant I as ChannelInterceptor chain
    participant H as Handler / Consumer

    P->>C: send(message)
    C->>I: preSend(message)
    I-->>C: message đã chấp nhận / đã biến đổi
    C->>H: doSend(message)
    H-->>C: kết quả dispatch
    C->>I: postSend(message, sent)
    C->>I: afterSendCompletion(message, sent, ex)
    C-->>P: boolean hoặc exception
~~~

Sơ đồ mô tả một channel dispatch đồng bộ. Với channel bất đồng bộ, `doSend()` có thể chỉ enqueue message hoặc submit task; handler có thể chạy sau khi producer đã nhận kết quả gửi.

Một interceptor có thể dùng cho nhiều mục đích:

- Kiểm tra message có đủ header bắt buộc trước khi gửi.
- Bổ sung correlation metadata hoặc chuẩn hóa header.
- Ghi log thời điểm send bắt đầu và kết quả.
- Đo latency của thao tác gửi trên channel.
- Gắn metric theo channel và kết quả gửi.
- Dọn tài nguyên hoặc hoàn tất observation sau khi send.

Interceptor là một phần của đường gửi message. Vì vậy, code trong interceptor cần ngắn, thread-safe và có chi phí thấp.

## 2. Ba callback ở chiều gửi khác nhau thế nào?

| Callback | Thời điểm | Có thể làm gì? | Vai trò chính |
|---|---|---|---|
| `preSend(message, channel)` | Trước khi message được gửi | Trả message mới hoặc `null` | Validate, enrich, chặn send |
| `postSend(message, channel, sent)` | Ngay sau lời gọi send trả về | Quan sát boolean `sent` | Ghi nhận kết quả gửi |
| `afterSendCompletion(message, channel, sent, ex)` | Khi thao tác send hoàn tất, kể cả có exception | Cleanup, ghi nhận exception và kết quả cuối | Hoàn tất tài nguyên/observation |

Các method có chữ ký:

~~~java
public interface ChannelInterceptor {

    Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    );

    void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent
    );

    void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex
    );
}
~~~

Interface cung cấp default implementation cho các hook. Các method trả `Message<?>` mặc định trả lại message, method `boolean` mặc định cho phép tiếp tục, còn method `void` mặc định không làm gì. Vì thế, custom interceptor chỉ cần override các callback thực sự cần.

`afterSendCompletion()` có từ Spring Framework 4.1 và Spring Integration 4.1. Khi triển khai ứng dụng cũ, hãy kiểm tra đúng phiên bản API đang dùng.

## 3. preSend: kiểm tra và biến đổi trước khi gửi

`preSend()` được gọi trước khi channel thực hiện thao tác gửi. Đây là nơi phù hợp để kiểm tra điều kiện đầu vào hoặc bổ sung metadata cần thiết cho các endpoint phía sau.

### Giữ nguyên message

Nếu không cần thay đổi, trả lại message đầu vào:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel
) {
    return message;
}
~~~

Không trả `null` một cách vô tình. `null` có ý nghĩa đặc biệt: channel sẽ không thực hiện thao tác gửi message đó.

### Bổ sung header

Message và `MessageHeaders` có cấu trúc bất biến. Nếu cần thêm header, hãy tạo message mới bằng `MessageBuilder`:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel
) {
    return MessageBuilder.fromMessage(message)
            .setHeader("observedBy", "integration-runtime")
            .build();
}
~~~

Các endpoint phía sau nhận message được trả về từ `preSend()`. Vì payload có thể là object mutable, việc tạo message mới không đồng nghĩa deep copy payload. Nếu cần thay đổi dữ liệu nghiệp vụ, hãy tạo DTO hoặc object mới có chủ đích.

Không nên ghi đè các header chuẩn như `id` hoặc `timestamp` nếu không có lý do rõ ràng. Với custom header, nên dùng namespace riêng để tránh xung đột, ví dụ `app.traceId` hoặc `app.tenantId`.

### Chặn send bằng cách trả null

Có thể dùng `preSend()` để từ chối message không hợp lệ:

~~~java
@Component
class RequiredTenantInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        Object tenantId = message.getHeaders().get("tenantId");

        if (tenantId == null || tenantId.toString().isBlank()) {
            return null;
        }

        return message;
    }
}
~~~

Khi callback trả `null`:

1. Channel không gọi thao tác gửi thực tế cho message đó.
2. `send()` trả `false` theo contract của `MessageChannel`.
3. `postSend()` không được gọi cho lần gửi bị chặn ở `preSend()`.
4. `afterSendCompletion()` không được gọi cho interceptor đã trả `null`; những interceptor trước đó đã cho phép tiếp tục vẫn có thể nhận completion callback.

Chặn send trong interceptor có thể khiến producer chỉ nhìn thấy kết quả `false`. Nếu nghiệp vụ cần giải thích lý do từ chối, hãy ghi log/metric hoặc định tuyến validation error rõ ràng. Không nên âm thầm loại message mà không có cách quan sát.

### Tránh đặt nghiệp vụ nặng trong preSend

`preSend()` nằm trên đường gửi. Truy vấn database, gọi HTTP hoặc thực hiện tác vụ block trong callback sẽ làm tăng latency của producer và có thể làm nghẽn channel.

Interceptor phù hợp với kiểm tra nhẹ, chuẩn hóa metadata và quan sát. Validation nghiệp vụ phức tạp nên nằm trong endpoint/handler chuyên trách để có error handling và transaction boundary rõ ràng.

## 4. postSend: quan sát kết quả boolean

`postSend()` được gọi ngay sau thao tác gửi của channel trả về. Tham số `sent` chính là giá trị boolean mà thao tác gửi trả về.

- `sent=true`: channel báo đã chấp nhận hoặc dispatch message theo semantics của implementation.
- `sent=false`: channel báo không gửi được message, ví dụ queue không nhận thêm phần tử hoặc send bị từ chối.

Ví dụ:

~~~java
@Override
public void postSend(
        Message<?> message,
        MessageChannel channel,
        boolean sent
) {
    if (sent) {
        logger.debug(
                "Channel accepted message: channel={}, messageId={}",
                channel.getClass().getSimpleName(),
                message.getHeaders().getId()
        );
    }
    else {
        logger.warn(
                "Channel did not accept message: channel={}, messageId={}",
                channel.getClass().getSimpleName(),
                message.getHeaders().getId()
        );
    }
}
~~~

### sent=true không có cùng ý nghĩa trên mọi channel

| Channel | `sent=true` thường có nghĩa gì? | Không chứng minh điều gì? |
|---|---|---|
| `DirectChannel` | Dispatch đồng bộ tới subscriber đã thành công | Không chứng minh mọi nghiệp vụ bên ngoài đã commit nếu handler chỉ khởi chạy tác vụ khác |
| `QueueChannel` | Message đã được đưa vào queue | Không chứng minh polling consumer đã nhận hoặc xử lý |
| `ExecutorChannel` | Dispatcher/executor đã tiếp nhận tác vụ dispatch | Không chứng minh handler trên worker đã hoàn tất |
| Broker-backed channel | Adapter/broker đã chấp nhận thao tác theo contract cụ thể | Không tự chứng minh consumer đích đã xử lý và commit |

Do đó, không nên đặt tên metric của `postSend()` là `business.completed`. Tên phù hợp hơn là `channel.send.accepted` hoặc `channel.send.result`.

### postSend không phải finally

`postSend()` là hook sau khi thao tác send trả về. Nếu thao tác send ném exception thay vì trả boolean, không có giá trị `sent` bình thường để báo cho `postSend()`. Dùng `afterSendCompletion()` cho logic cần chạy cả khi send thất bại bằng exception.

## 5. afterSendCompletion: hoàn tất và cleanup

`afterSendCompletion()` là callback ở bước hoàn tất thao tác send. Nó được gọi sau khi send hoàn tất, bất kể thao tác có phát sinh exception hay không, miễn là `preSend()` của interceptor tương ứng đã chạy thành công và trả về một message khác null.

Tham số:

| Tham số | Ý nghĩa |
|---|---|
| `message` | Message được đưa qua interceptor chain |
| `channel` | Channel đang thực hiện send |
| `sent` | Kết quả boolean của send nếu có |
| `ex` | Exception phát sinh trong quá trình send; null nếu không có |

Ví dụ:

~~~java
@Override
public void afterSendCompletion(
        Message<?> message,
        MessageChannel channel,
        boolean sent,
        Exception ex
) {
    if (ex != null) {
        logger.error(
                "Send failed: channel={}, messageId={}",
                channel.getClass().getSimpleName(),
                message.getHeaders().getId(),
                ex
        );
        return;
    }

    logger.debug(
            "Send completed: channel={}, messageId={}, sent={}",
            channel.getClass().getSimpleName(),
            message.getHeaders().getId(),
            sent
    );
}
~~~

Đây là nơi phù hợp để:

- Kết thúc timer hoặc observation đã bắt đầu ở `preSend()`.
- Giải phóng resource tạm.
- Ghi nhận exception của send.
- Dọn context cục bộ gắn với thread hiện tại.
- Cập nhật counter kết quả cuối.

Không nên ném thêm exception từ cleanup nếu có thể tránh. Callback này chạy trong quá trình hoàn tất send; một exception mới có thể che khuất nguyên nhân ban đầu hoặc làm việc xử lý lỗi khó hiểu hơn. Nếu cleanup có thể thất bại, hãy log và ghi metric riêng.

### Callback được gọi theo thứ tự ngược

Nếu nhiều interceptor đã tham gia `preSend()`, `afterSendCompletion()` được gọi theo thứ tự ngược với thứ tự `preSend()`.

Ví dụ, với interceptor A rồi B:

~~~text
preSend(A)
  preSend(B)
    channel send
  afterSendCompletion(B)
afterSendCompletion(A)
~~~

Cách gọi ngược này giống cấu trúc mở/đóng tài nguyên lồng nhau: interceptor vào trước hoàn tất sau cùng. Nó hữu ích khi interceptor ngoài cùng mở context và interceptor bên trong dùng context đó.

## 6. Trình tự callback trong các tình huống khác nhau

Không phải lần gửi nào cũng đi qua đủ ba callback.

| Tình huống | preSend | postSend | afterSendCompletion |
|---|---|---|---|
| Send thành công | Có | Có, `sent=true` | Có, `ex=null` |
| Channel trả `false` | Có | Có, `sent=false` | Có, `ex=null` |
| Channel ném exception trong send | Có | Không có kết quả trả về bình thường | Có, nhận exception |
| Interceptor trả `null` ở preSend | Có tới interceptor đó | Không có cho lần gửi bị chặn | Không gọi cho interceptor trả null; interceptor trước đã chấp nhận có thể được hoàn tất |
| Interceptor ném exception trong preSend | Có tới interceptor gây lỗi | Không | Các interceptor trước đã chấp nhận được hoàn tất theo chain |

Sơ đồ nhánh:

~~~mermaid
flowchart TD
    A["send(message)"] --> B["preSend chain"]
    B --> C{"Có interceptor trả null?"}
    C -->|"Có"| F["Dừng send, trả false"]
    C -->|"Không"| D["Channel thực hiện doSend"]
    D --> E{"doSend trả về hay ném exception?"}
    E -->|"Trả boolean"| G["postSend(message, sent)"]
    E -->|"Ném exception"| H["Bỏ qua postSend"]
    G --> I["afterSendCompletion"]
    H --> I
    I --> J["send kết thúc"]
    F --> K["Không gọi completion cho interceptor trả null"]
~~~

Nếu một interceptor ở đầu chain đã trả message hợp lệ, nhưng interceptor sau đó trả null, interceptor đầu có thể vẫn nhận `afterSendCompletion()` để hoàn tất phần việc mà nó đã bắt đầu. Interceptor trả null không nhận callback completion cho chính lần gửi bị chặn đó.

## 7. Ví dụ một interceptor triển khai đủ ba callback

Ví dụ dưới đây ghi nhận message ID, channel type, kết quả send và exception:

~~~java
@Component
class SendLifecycleInterceptor implements ChannelInterceptor {

    private static final Logger logger =
            LoggerFactory.getLogger(SendLifecycleInterceptor.class);

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        logger.debug(
                "preSend channel={}, messageId={}",
                channel.getClass().getSimpleName(),
                message.getHeaders().getId()
        );

        return message;
    }

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent
    ) {
        logger.debug(
                "postSend channel={}, messageId={}, sent={}",
                channel.getClass().getSimpleName(),
                message.getHeaders().getId(),
                sent
        );
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex
    ) {
        if (ex != null) {
            logger.warn(
                    "afterSendCompletion channel={}, messageId={}, sent={}",
                    channel.getClass().getSimpleName(),
                    message.getHeaders().getId(),
                    sent,
                    ex
            );
        }
        else {
            logger.trace(
                    "afterSendCompletion channel={}, messageId={}, sent={}",
                    channel.getClass().getSimpleName(),
                    message.getHeaders().getId(),
                    sent
            );
        }
    }
}
~~~

Interceptor này không giữ trạng thái mutable theo từng message trong field của singleton bean. Điều đó quan trọng vì cùng một interceptor có thể được gọi đồng thời từ nhiều producer thread.

Nếu muốn đo thời gian, không nên lưu timestamp vào một field instance đơn như `long startedAt`; hai message đồng thời sẽ ghi đè thời điểm của nhau. Có thể dùng Micrometer Observation/Timer phù hợp với instrumentation của ứng dụng, hoặc dùng context per invocation có cleanup chắc chắn. Tránh thêm header nội bộ chỉ để đo thời gian nếu header đó sẽ bị lộ sang handler hoặc transport bên ngoài.

## 8. Đăng ký interceptor vào channel

Có thể đăng ký interceptor cục bộ cho một channel bằng Java:

~~~java
@Configuration
class ChannelConfiguration {

    @Bean
    DirectChannel ordersChannel(
            SendLifecycleInterceptor interceptor
    ) {
        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(interceptor);
        return channel;
    }
}
~~~

Với cách này, interceptor chỉ áp dụng cho channel `ordersChannel`. Cách cục bộ phù hợp khi cần quan sát một ranh giới cụ thể và muốn tránh tác động tới channel khác.

### Global interceptor theo pattern

Nếu cần áp dụng cùng interceptor cho một nhóm channel, có thể đăng ký global channel interceptor:

~~~java
@Configuration
@EnableIntegration
class GlobalChannelInterceptorConfiguration {

    @Bean
    @GlobalChannelInterceptor(
            patterns = {"orders*", "payments*"},
            order = 10
    )
    ChannelInterceptor sendLifecycleInterceptor() {
        return new SendLifecycleInterceptor();
    }
}
~~~

Pattern giúp giới hạn channel được intercept. Thuộc tính `order` xác định thứ tự tương đối giữa các interceptor. Không nên gắn interceptor toàn cục cho mọi channel nếu nó thực hiện log chi tiết hoặc xử lý tốn thời gian.

Từ Spring Integration 5.1, global channel interceptor cũng áp dụng cho channel được đăng ký động thông qua `IntegrationFlowContext` hoặc `BeanFactory.initializeBean()`. Với phiên bản cũ hơn, cần kiểm tra behavior tương ứng.

## 9. Nhiều interceptor và thứ tự thực thi

Khi channel có nhiều interceptor, thứ tự có thể ảnh hưởng tới dữ liệu mà callback tiếp theo nhìn thấy.

Ví dụ:

- A thêm header `app.traceId`.
- B kiểm tra header đó.
- C ghi metric dựa trên kết quả.
- Khi send hoàn tất, completion callback chạy ngược để đóng context theo thứ tự lồng nhau.

~~~mermaid
flowchart TD
    A["preSend A: thêm trace metadata"] --> B["preSend B: validate metadata"]
    B --> C["preSend C: capture observation"]
    C --> D["Channel send"]
    D --> E["afterSendCompletion C"]
    E --> F["afterSendCompletion B"]
    F --> G["afterSendCompletion A"]
~~~

`preSend()` được áp dụng theo thứ tự interceptor trong chain. Completion callback chạy ngược thứ tự các interceptor đã chấp nhận message. Không nên phụ thuộc vào thứ tự không được cấu hình rõ; nếu một interceptor cần header do interceptor khác tạo, hãy đặt thứ tự bằng cấu hình và kiểm thử.

Nếu một interceptor trả null, chain bị dừng trước khi channel send. Các interceptor sau nó không chạy. Interceptor trước đó đã trả message vẫn cần hoàn tất phần việc đã bắt đầu.

## 10. Exception và khác biệt giữa false với lỗi

Ba tình huống sau không giống nhau:

| Kết quả | Ý nghĩa | Nơi cần xử lý |
|---|---|---|
| `preSend()` trả null | Interceptor chủ động chặn send | Validation/rejection policy |
| `send()` trả false | Channel không nhận message theo implementation | Producer hoặc cơ chế retry phù hợp |
| `send()` ném exception | Có lỗi trong interceptor hoặc channel/handler | Exception handling và error flow |

`postSend()` giúp quan sát trường hợp channel trả boolean. `afterSendCompletion()` nhận exception nếu thao tác send ném lỗi. Không nên bắt mọi exception rồi chỉ ghi log và tiếp tục như thể send đã thành công; producer cần biết message có được nhận hay không.

### Không dùng interceptor để che giấu lỗi

Ví dụ không nên:

~~~java
@Override
public void postSend(
        Message<?> message,
        MessageChannel channel,
        boolean sent
) {
    try {
        auditRepository.save(message);
    }
    catch (Exception ex) {
        // Nuốt lỗi và không ghi nhận
    }
}
~~~

Cách này che giấu lỗi audit và có thể tạo cảm giác rằng dữ liệu đã được ghi. Nếu audit là bắt buộc, hãy thiết kế nó như một bước nghiệp vụ có transaction và error handling rõ. Nếu audit chỉ best-effort, ít nhất phải ghi metric/log cho lỗi để vận hành biết có dữ liệu quan sát bị bỏ lỡ.

## 11. Channel semantics quyết định ý nghĩa của callback

Interceptor bao quanh lời gọi `send()`, chứ không tự đo toàn bộ vòng đời message sau khi rời channel.

### DirectChannel

Với `DirectChannel`, dispatch thường đồng bộ trên thread gửi. `postSend()` được gọi sau khi dispatch trả về. Nếu handler ném exception đồng bộ, `afterSendCompletion()` nhận exception.

### QueueChannel

Với `QueueChannel`, send thường kết thúc khi message được enqueue. `postSend(sent=true)` không có nghĩa polling consumer đã nhận message. Consumer có thể xử lý sau đó hoặc không bao giờ xử lý nếu endpoint không chạy.

### ExecutorChannel

Với `ExecutorChannel`, thao tác send có thể kết thúc sau khi executor nhận task. Handler thực thi trên worker thread. `afterSendCompletion()` của sender không phải callback hoàn tất handler.

Nếu cần đo thời gian handler, hãy instrument handler hoặc endpoint ở worker side. Nếu cần biết nghiệp vụ hoàn tất, dùng completion event, reply hoặc trạng thái nghiệp vụ thay vì suy ra từ channel send callback.

## 12. Threading và transaction boundary

Các callback `preSend()`, `postSend()` và `afterSendCompletion()` thuộc cùng một thao tác `send()`. Thông thường chúng chạy trên thread đang gọi send.

Điều đó có nghĩa:

- Với DirectChannel, handler cũng thường chạy trên thread gửi; transaction thread-bound có thể tiếp tục qua lời gọi handler đồng bộ.
- Với QueueChannel, send và receive có thể diễn ra trên các thread khác nhau; interceptor send không quan sát transaction của consumer.
- Với ExecutorChannel, handler chạy trên worker; transaction context gắn với sender thread không tự động truyền sang worker.

Không dùng một `ThreadLocal` ở `preSend()` rồi kỳ vọng đọc nó trong handler bất đồng bộ. Nếu cần truyền correlation hoặc tracing context qua thread boundary, hãy dùng message headers hoặc cơ chế context propagation tương ứng.

## 13. Đo latency và tạo metric an toàn

Một interceptor có thể đo thời gian của thao tác send, nhưng phải xác định rõ đang đo ranh giới nào.

- Với DirectChannel, thời gian send có thể bao gồm dispatch đồng bộ và thời gian handler.
- Với QueueChannel, thời gian send chủ yếu bao gồm việc đưa message vào queue.
- Với ExecutorChannel, thời gian send thường bao gồm submit/dispatch task, không bao gồm toàn bộ thời gian worker xử lý.

Nên dùng tên metric phản ánh đúng boundary, ví dụ:

| Metric | Ý nghĩa |
|---|---|
| `integration.channel.send.duration` | Thời gian thao tác send trên channel |
| `integration.channel.send.accepted` | Số lần send trả true |
| `integration.channel.send.rejected` | Số lần send trả false hoặc bị từ chối theo phân loại |
| `integration.channel.send.exception` | Số lần send ném exception |

Khi tạo tag:

- Dùng tên channel ổn định và số lượng giá trị hữu hạn.
- Không dùng message ID, correlation ID, customer ID hoặc payload làm metric tag.
- Không ghi full payload hoặc header nhạy cảm vào log.
- Tách lỗi do interceptor chặn, channel trả false và exception.
- Không gọi metric backend hoặc hệ thống ngoài theo cách block trong callback.

Nếu cần quan sát toàn bộ thời gian xử lý message, kết hợp channel metrics với handler metrics và tracing. Một timer send đơn lẻ không thể mô tả đầy đủ thời gian từ producer tới khi nghiệp vụ hoàn tất.

## 14. Kiểm thử callback

Một test đơn giản có thể xác nhận thứ tự cơ bản khi gửi qua DirectChannel:

~~~java
class RecordingInterceptor implements ChannelInterceptor {

    final List<String> events = new ArrayList<>();

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        events.add("preSend");
        return message;
    }

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent
    ) {
        events.add("postSend:" + sent);
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex
    ) {
        events.add("afterSendCompletion:" + (ex == null));
    }
}
~~~

Test thành công:

~~~java
@Test
void invokesSendCallbacksInOrder() {
    DirectChannel channel = new DirectChannel();
    RecordingInterceptor interceptor = new RecordingInterceptor();

    channel.addInterceptor(interceptor);
    channel.subscribe(message -> { });

    boolean sent = channel.send(
            MessageBuilder.withPayload("hello").build()
    );

    assertThat(sent).isTrue();
    assertThat(interceptor.events)
            .containsExactly(
                    "preSend",
                    "postSend:true",
                    "afterSendCompletion:true"
            );
}
~~~

Nên bổ sung các tình huống:

1. `preSend()` trả null: channel không dispatch message và producer nhận false.
2. `doSend()` trả false: `postSend()` nhận false và completion vẫn được gọi.
3. Handler ném exception trên DirectChannel: completion callback nhận exception.
4. Có nhiều interceptor: completion chạy theo thứ tự ngược.
5. ExecutorChannel: completion send xảy ra trước hoặc độc lập với việc handler hoàn tất; không dùng nó làm bằng chứng handler đã xong.
6. Interceptor được gọi đồng thời: không có race condition do shared mutable state.

Trong ví dụ test, `events` là state quan sát của test. Nếu dùng trong test đa thread, hãy thay bằng collection thread-safe và chờ điều kiện hoàn tất bằng timeout hữu hạn.

## 15. Chẩn đoán khi callback không chạy như mong đợi

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| `preSend()` không chạy | Interceptor chưa đăng ký vào channel producer đang dùng |
| `postSend()` không chạy | `preSend()` chặn message hoặc send ném exception trước khi trả về |
| `sent` là false | Channel từ chối send hoặc interceptor trả null |
| `afterSendCompletion()` không chạy | `preSend()` của interceptor đó không trả message; hoặc interceptor chưa nằm trong chain |
| Handler chạy nhưng producer thấy send thành công sớm | Channel bất đồng bộ; send chỉ xác nhận enqueue/submit |
| Completion nhận exception | Kiểm tra lỗi gốc trong channel, handler đồng bộ hoặc interceptor khác |
| Metric duration quá thấp | Đang đo thời gian enqueue/submit thay vì xử lý downstream |
| Metric duration tăng mạnh | Handler đồng bộ, queue block, interceptor chậm hoặc channel contention |
| Header bổ sung không xuất hiện ở handler | Message mới không được trả về hoặc interceptor khác thay message sau đó |

Quy trình kiểm tra:

1. Xác định bean channel chính xác mà producer gửi tới.
2. Xác nhận channel hỗ trợ interceptor và interceptor đã được đăng ký.
3. Kiểm tra thứ tự interceptor và kết quả `preSend()`.
4. Kiểm tra `send()` trả false hay ném exception.
5. Xem `postSend()` nhận giá trị sent nào.
6. Kiểm tra `afterSendCompletion()` có nhận exception không.
7. Xác định channel là đồng bộ hay bất đồng bộ trước khi diễn giải thời gian.
8. Nếu handler chạy trên executor, quan sát worker thread và error channel riêng.
9. Kiểm tra interceptor có state mutable dùng chung giữa nhiều thread không.

## 16. Checklist trước khi đưa ChannelInterceptor vào production

- [ ] `preSend()` chỉ thực hiện validation/enrichment nhẹ và có timeout phù hợp?
- [ ] Nếu trả null, producer có cách nhận biết message bị chặn?
- [ ] Message mới từ `preSend()` có được trả lại đầy đủ?
- [ ] `postSend()` chỉ được dùng để quan sát kết quả channel send?
- [ ] Không diễn giải `sent=true` thành business completion?
- [ ] `afterSendCompletion()` cleanup được cả trường hợp exception?
- [ ] Cleanup callback không che khuất exception ban đầu?
- [ ] Thứ tự nhiều interceptor được cấu hình rõ?
- [ ] Interceptor thread-safe và không lưu trạng thái từng message trong field dùng chung?
- [ ] Metric tag có cardinality thấp và không chứa dữ liệu nhạy cảm?
- [ ] Channel sync/async đã được tính tới khi diễn giải latency?
- [ ] Transaction và context propagation qua executor được hiểu đúng?
- [ ] Có test cho send thành công, false, null rejection và exception?
- [ ] Có log/metric để phân biệt interceptor rejection, channel false và exception?

`preSend()`, `postSend()` và `afterSendCompletion()` tạo thành vòng đời quan sát một thao tác send. Dùng `preSend()` để kiểm tra hoặc chuẩn hóa message, `postSend()` để ghi nhận boolean mà channel trả về, và `afterSendCompletion()` để hoàn tất cleanup kể cả khi có exception. Khi phân biệt rõ kết quả send với kết quả xử lý downstream, interceptor có thể hỗ trợ observability và policy mà không làm sai semantics của message flow.

## Tài liệu tham khảo

- [Spring Integration — Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html) — các callback send/receive, thứ tự completion và cách đăng ký interceptor.
- [Spring Framework — ChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html) — hợp đồng `preSend`, `postSend` và `afterSendCompletion`.
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html) — semantics của DirectChannel, QueueChannel và ExecutorChannel.
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html) — đăng ký interceptor cục bộ và global.

Các chi tiết callback và channel behavior cần đối chiếu với phiên bản Spring Framework/Spring Integration mà ứng dụng đang dùng. Tài liệu hiện hành xác nhận `afterSendCompletion()` chỉ được gọi cho interceptor có `preSend()` đã trả về message khác null; completion callback chạy theo thứ tự ngược với các lần gọi pre-hook.
