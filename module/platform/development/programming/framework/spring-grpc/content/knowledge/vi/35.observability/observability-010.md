# Che payload trong log

Log giúp điều tra lỗi và hiểu hành vi của dịch vụ, nhưng payload gRPC thường chứa dữ liệu cá nhân, thông tin tài khoản, bí mật xác thực hoặc nội dung nghiệp vụ. Ghi nguyên request/response vào log có thể biến hệ thống observability thành một bản sao dữ liệu nhạy cảm, được lưu lâu hơn và có nhiều người truy cập hơn hệ thống nghiệp vụ. Vì vậy, dịch vụ cần quyết định rõ trường nào được log, trường nào phải che hoặc loại bỏ, và việc redaction diễn ra ở ranh giới nào.

**Che payload trong log** là giảm thiểu dữ liệu được ghi, loại bỏ hoặc biến đổi các trường nhạy cảm trước khi chúng tới logging backend. Bài thuộc chương **Observability** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là không ghi raw Protobuf message, phân loại trường theo schema, dùng allowlist cho log projection, xử lý metadata/trailers và kiểm thử để chứng minh dữ liệu nhạy cảm không rò rỉ.

## 1. Nguyên tắc: không ghi raw payload theo mặc định

Một Protobuf request có thể chứa nhiều loại dữ liệu:

- Thông tin nhận dạng: tên, email, số điện thoại, địa chỉ, ngày sinh.
- Thông tin tài chính: số tài khoản, số thẻ, số tiền, dữ liệu thanh toán.
- Bí mật xác thực: access token, refresh token, API key, mật khẩu, cookie.
- Nội dung riêng tư: ghi chú, nội dung chat, tệp đính kèm, dữ liệu y tế hoặc hồ sơ khách hàng.
- Định danh nghiệp vụ có thể liên kết tới cá nhân: customer ID, order ID, tenant ID.

Không nên gọi request.toString(), nối request vào log message hoặc serialize toàn bộ message bằng JsonFormat.printer() để ghi log. Protobuf toString() và JSON printer có thể xuất các field hiện diện, kể cả field nhạy cảm. Việc payload hiện ở dạng text hay binary không làm thay đổi mức độ nhạy cảm.

Mặc định an toàn là log metadata vận hành: method, request ID, status, duration, số lượng phần tử, kích thước đã được đo tại ranh giới xác định và kết quả xử lý. Chỉ bổ sung nội dung payload khi có mục đích cụ thể, được phê duyệt theo chính sách dữ liệu và đã qua sanitizer.

## 2. Phân loại field trước khi viết logger

Phải biết schema chứa gì trước khi quyết định log. Có thể phân loại field theo bốn nhóm:

| Nhóm | Ví dụ | Cách xử lý trong log vận hành |
| --- | --- | --- |
| Public/operational | RPC method, enum loại thao tác, số lượng item | Có thể log nếu cần cho vận hành. |
| Internal identifier | customer ID, order ID, tenant ID | Mặc định loại bỏ hoặc thay bằng token giả danh có kiểm soát. |
| Personal/confidential | email, phone, address, free-text note | Che một phần nếu thật sự cần; ưu tiên loại bỏ. |
| Secret/authentication | password, token, API key, cookie, private key | Không ghi; loại bỏ hoàn toàn. |

Phân loại cần áp dụng cho cả request và response, field lồng nhau, repeated field, map, oneof, Any, bytes và metadata. Một field mới được thêm vào Protobuf schema không được tự động trở thành dữ liệu được phép log.

## 3. Allowlist tốt hơn denylist

Allowlist chỉ định những trường được phép xuất hiện trong log. Denylist cố gắng liệt kê các trường cần che. Với schema thay đổi theo thời gian, denylist dễ bỏ sót field nhạy cảm mới; allowlist mặc định loại bỏ field chưa được xem xét.

Ví dụ:

~~~text
Log projection cho CreateOrder:
  grpc_method       allow
  request_id        allow nếu đã validate
  item_count        allow
  delivery_mode     allow nếu enum không chứa dữ liệu nhạy cảm
  customer_email    exclude
  customer_phone    exclude
  payment_token     exclude
  delivery_address  exclude
  free_text_note    exclude
~~~

Nên tạo một log projection riêng từ request, chỉ giữ các thuộc tính có mục đích vận hành. Không truyền cả Protobuf message cho logger rồi hy vọng một regex chung có thể xóa mọi bí mật.

## 4. Che, loại bỏ và giả danh hóa là các cách khác nhau

- **Loại bỏ (redact/remove):** field không xuất hiện trong log. Đây là lựa chọn ưu tiên với secret và dữ liệu không cần thiết.
- **Che một phần (mask):** chỉ giữ một phần giá trị, ví dụ hiển thị hai ký tự cuối của số điện thoại khi use case thực sự cần nhận diện tương đối.
- **Giả danh hóa (pseudonymize):** thay identifier bằng token ổn định để liên kết sự kiện mà không ghi identifier gốc.
- **Tổng hợp (aggregate):** ghi count, category hoặc range thay vì giá trị cụ thể.

Masking không biến dữ liệu thành vô hại; phần còn lại vẫn có thể nhận dạng người dùng khi kết hợp với dữ liệu khác. Hash thông thường cũng không bảo đảm ẩn danh: ID có miền giá trị nhỏ có thể bị dò bằng dictionary. Nếu cần token ổn định để liên kết log, dùng HMAC với secret key được quản lý riêng, giới hạn quyền truy cập và rotation; không dùng HMAC output làm metric label nếu cardinality không được kiểm soát.

## 5. Tạo log projection thay vì log Protobuf message

Ví dụ sau minh họa một log projection chỉ giữ số lượng item và enum vận chuyển đã được đánh giá là an toàn. Tên getter là minh họa theo một generated request cụ thể; thay bằng field thực tế trong schema của ứng dụng:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderRequestLogger {

    private static final Logger log =
            LoggerFactory.getLogger(OrderRequestLogger.class);

    public void logAccepted(
            String requestId,
            CreateOrderRequest request) {

        String deliveryMode =
                request.getDeliveryMode().name();
        int itemCount = request.getItemsCount();

        // Chỉ log các field đã được duyệt trong log projection.
        log.info(
                "order.request.accepted request_id={} grpc_method={} delivery_mode={} item_count={}",
                requestId,
                "orders.OrderService/CreateOrder",
                deliveryMode,
                itemCount);
    }
}
~~~

Ví dụ không đưa request trực tiếp vào logger và không serialize toàn bộ message. deliveryMode chỉ được log nếu enum không chứa giá trị tự do hoặc thông tin nhạy cảm. Nếu enum phản ánh loại khách hàng hoặc phân khúc bí mật, hãy bỏ field đó hoặc ánh xạ sang nhóm rộng hơn.

Log projection nên là kiểu dữ liệu nhỏ, có tên field rõ ràng và được review cùng schema. Khi Protobuf thêm field, projection không tự động thêm field đó vào log.

## 6. Redaction theo Protobuf schema

Khi cần sanitizer dùng chung cho nhiều message, hãy xây dựng policy theo descriptor thay vì dựa vào toString() hoặc tìm chuỗi bằng regex. Protobuf descriptor cung cấp tên field, kiểu, field number, nested message và options; ứng dụng có thể ánh xạ field path vào chính sách dữ liệu.

Ví dụ policy:

~~~text
CreateOrderRequest.customer.email       -> REMOVE
CreateOrderRequest.customer.phone       -> MASK
CreateOrderRequest.payment.token         -> REMOVE
CreateOrderRequest.items[*].sku          -> ALLOW nếu SKU không nhạy cảm
CreateOrderRequest.items[*].quantity     -> ALLOW
CreateOrderRequest.delivery.address      -> REMOVE
CreateOrderRequest.note                  -> REMOVE
~~~

Một sanitizer schema-aware cần xử lý:

- Nested message: áp dụng policy đệ quy theo full field path.
- Repeated/map: áp dụng policy cho từng phần tử và giới hạn số phần tử được duyệt.
- oneof: chỉ field đang được set mới có giá trị; vẫn phải áp dụng policy tương ứng.
- Any: chỉ unpack type nằm trong allowlist đã biết; nếu không biết type thì loại bỏ payload.
- bytes: không log raw bytes hoặc base64 payload nếu chưa phân loại.
- Unknown/new fields: mặc định bỏ qua trong log projection.

Không nên tạo một sanitizer tổng quát phức tạp nếu ứng dụng chỉ có vài method cần log. Log projection tường minh theo method thường dễ review và ít rủi ro hơn. Với schema lớn, dùng descriptor-driven policy và test coverage cho từng field path.

## 7. Không log payload ở interceptor tổng quát

ServerInterceptor và ClientInterceptor là vị trí thuận tiện để log method, status, request ID và duration. Tuy nhiên, interceptor tổng quát không nên log toàn bộ message trong onMessage hoặc sendMessage: nó có thể chạy cho mọi service, mọi schema và mọi loại dữ liệu.

Một server interceptor chỉ log thông tin vận hành:

~~~java
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class SafeGrpcAccessLogInterceptor
        implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SafeGrpcAccessLogInterceptor.class);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        long started = System.nanoTime();
        AtomicBoolean terminalLogged = new AtomicBoolean();

        ServerCall<ReqT, RespT> monitored =
                new ForwardingServerCall
                        .SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        if (terminalLogged.compareAndSet(false, true)) {
                            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                                    System.nanoTime() - started);
                            log.info(
                                    "grpc.server.completed grpc_method={} grpc_status={} duration_ms={}",
                                    method,
                                    status.getCode().name(),
                                    durationMs);
                        }
                        super.close(status, trailers);
                    }
                };

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitored, headers);

        return new io.grpc.ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                if (terminalLogged.compareAndSet(false, true)) {
                    log.info(
                            "grpc.server.cancelled grpc_method={}",
                            method);
                }
                super.onCancel();
            }
        };
    }
}
~~~

Interceptor này không đọc request message và không ghi metadata tùy ý. Nếu ứng dụng đã có access-log interceptor, hãy thêm các field an toàn vào cơ chế đó thay vì tạo nhiều logger ghi trùng một RPC. Khi đăng ký với Spring gRPC starter, dùng đúng server lifecycle mà starter quản lý.

## 8. Metadata và trailers cũng có thể chứa bí mật

Không chỉ Protobuf payload mới cần redaction. Request metadata có thể chứa:

- authorization, bearer token hoặc API key.
- Cookie/session identifier.
- Credential do service mesh hoặc proxy thêm.
- Custom header có dữ liệu cá nhân hoặc tenant identifier.

Response trailers có thể chứa error description, debug details hoặc dữ liệu do application thêm. Không log toàn bộ Metadata.keys() cùng giá trị; chỉ log allowlist các header vận hành đã được duyệt. Với secret, loại bỏ hoàn toàn thay vì mask vài ký tự.

Ví dụ quy tắc:

~~~text
Allow:
  x-request-id       nếu đã validate
  grpc-timeout       nếu cần cho điều tra và đã chuẩn hóa

Never log:
  authorization
  cookie
  x-api-key
  session-token
  arbitrary custom metadata
~~~

Không tự ghi grpc-timeout thô nếu giá trị có thể gây nhầm lẫn giữa deadline còn lại và timeout ban đầu; nếu cần, ghi một duration đã parse/chuẩn hóa. Tránh log raw error description hoặc exception message vì chúng có thể chứa input của caller.

## 9. Che payload trong streaming RPC

Với client-streaming, server-streaming và bidirectional streaming, mỗi stream có thể chứa nhiều message. Log từng message làm tăng chi phí, tạo lượng dữ liệu nhạy cảm lớn và có thể làm nghẽn logging pipeline.

Nên ưu tiên:

- Log một event khi stream bắt đầu và một event khi kết thúc.
- Ghi method, status, duration và message count bằng metrics.
- Nếu cần debug nội dung, dùng sampling có giới hạn và log projection đã redaction.
- Giới hạn số message được lấy mẫu trên mỗi stream và tổng số byte log.
- Không log message chưa được phân loại, kể cả chỉ một message đầu tiên.
- Xử lý cancellation/exception để không bỏ sót cleanup hoặc ghi payload trong error path.

Với stream mang dữ liệu nhạy cảm, không bật payload logging bằng feature flag toàn cục. Nếu cần một phiên debug đặc biệt, phải giới hạn method, thời gian, caller, quyền truy cập và retention; mặc định tắt và có audit cho thao tác bật.

## 10. Exception, debug details và audit log

Exception message không tự động an toàn. Một exception có thể chứa SQL fragment, request value, file path, token hoặc dữ liệu từ downstream. Không log Throwable.getMessage() một cách không kiểm soát và không trả stack trace qua gRPC status description.

Log vận hành nên ưu tiên:

- Error category hoặc exception class đã được chuẩn hóa.
- gRPC status code.
- Method, request ID và trace ID nếu có.
- Dependency name và operation name đã được duyệt.
- Một mã lỗi nội bộ không chứa payload.

Audit log là mục đích khác với application log. Nếu nghiệp vụ yêu cầu lưu ai đã thực hiện hành động nào, ghi audit event với schema, access control, integrity, retention và redaction riêng. Không dùng raw gRPC payload log làm audit trail.

## 11. Retention, quyền truy cập và nơi lưu log

Redaction tại application là lớp bảo vệ quan trọng, nhưng không thay thế kiểm soát ở logging pipeline:

- Giới hạn quyền đọc log theo vai trò và môi trường.
- Tách log production khỏi môi trường dev/test.
- Đặt retention theo mục đích và chính sách dữ liệu.
- Mã hóa log khi truyền và khi lưu.
- Hạn chế export log sang bên thứ ba; đánh giá data residency và hợp đồng xử lý dữ liệu.
- Có audit cho truy cập hoặc export log nhạy cảm.
- Không đưa payload raw vào dead-letter log, retry diagnostic hoặc crash dump một cách vô tình.

Nếu redaction xảy ra quá muộn ở dashboard, raw payload vẫn có thể tồn tại trong agent buffer, collector, archive hoặc bản export. Thực hiện data minimization trước khi log event rời khỏi process.

## 12. Kiểm thử redaction

Kiểm thử phải chứng minh giá trị nhạy cảm không xuất hiện ở bất kỳ log event nào trong các đường thành công và lỗi:

1. Tạo request chứa email, phone, access token, địa chỉ và free-text note có marker dễ tìm.
2. Gọi RPC thành công; kiểm tra log projection chỉ chứa field allowlist.
3. Làm validation hoặc downstream call thất bại; kiểm tra exception/status description không làm lộ marker.
4. Gửi metadata authorization, cookie và x-api-key; xác minh logger không ghi giá trị.
5. Gửi nested/repeated/map/oneof fields có dữ liệu nhạy cảm; xác minh sanitizer áp dụng policy đệ quy.
6. Gửi Any với type không nằm trong allowlist; xác minh payload bị loại bỏ.
7. Gửi streaming RPC nhiều message; xác minh log không chứa raw message và event count bị giới hạn.
8. Kiểm tra log encoder thực tế, không chỉ kiểm tra object MDC hoặc log argument trước khi serialize.
9. Thay đổi Protobuf schema bằng field mới; xác minh field mới không tự xuất hiện trong log projection.
10. Kiểm tra cả appender, async logging queue, collector test sink và error path nếu các thành phần này nằm trong phạm vi triển khai.

Ví dụ test có thể dùng appender in-memory để thu log event, sau đó assert marker bí mật không có trong formatted message hoặc structured fields. Dùng marker duy nhất cho từng loại dữ liệu để xác định chính xác field nào bị rò.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Token xuất hiện trong log debug | Log trực tiếp request hoặc metadata. | Không log raw message/header; dùng allowlist projection. |
| Field mới xuất hiện trong log sau khi đổi proto | Serialize toàn bộ Protobuf message. | Dùng projection tường minh hoặc schema policy mặc định deny. |
| Regex che email nhưng bỏ sót dữ liệu khác | Redaction dựa trên chuỗi thay vì field semantics. | Phân loại theo schema và nested field path. |
| Secret xuất hiện trong exception | Log nguyên exception message/description. | Chuẩn hóa error category; redact exception data. |
| Streaming tạo quá nhiều log | Log từng message ở mức INFO. | Dùng message metrics và log lifecycle; sampling có giới hạn. |
| Dữ liệu vẫn lộ trong collector | Redaction chỉ thực hiện ở dashboard/collector cuối. | Redact trước khi event rời process và kiểm soát pipeline. |
| Masked identifier vẫn có thể nhận diện | Giữ quá nhiều ký tự hoặc dùng hash dễ dò. | Loại bỏ hoặc dùng HMAC/tokenization có quản lý khóa. |
| Test redaction vẫn pass dù JSON log lộ field | Chỉ kiểm tra log template/MDC, không kiểm tra encoder output. | Test formatted event và structured JSON thực tế. |

## 14. Bài tập thực hành

1. Lập bảng phân loại field cho một Protobuf request có nested message, repeated field và Any.
2. Tạo log projection allowlist cho unary RPC; không truyền raw request vào logger.
3. Viết ServerInterceptor chỉ log full method, status, duration và request ID đã validate.
4. Thiết lập allowlist metadata; chứng minh authorization/cookie/API key không xuất hiện trong log.
5. Viết sanitizer theo descriptor hoặc projection tường minh cho nested/repeated fields.
6. Kiểm thử streaming RPC để bảo đảm không log từng payload và không lộ marker nhạy cảm.
7. Kiểm tra exception, trailers, async appender và collector sink để tìm đường rò dữ liệu.
8. Định nghĩa retention/access policy cho application log và audit log riêng biệt.

Sau bài này, bạn cần biết cách giảm dữ liệu log bằng allowlist, che hoặc loại bỏ field nhạy cảm theo schema, giữ interceptor ở ranh giới vận hành an toàn và kiểm thử log output thực tế. Khi payload, metadata và exception đều được xử lý theo cùng chính sách dữ liệu, hệ thống Spring gRPC vẫn có đủ method/status/correlation fields để điều tra mà không biến log thành nơi lưu trữ bản sao dữ liệu nghiệp vụ.
