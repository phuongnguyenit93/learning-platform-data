# Recovery trace correlation — Liên kết trace trong luồng khôi phục tài khoản

## 1. Bài toán: một lần recovery đi qua nhiều lần thực thi

Một yêu cầu khôi phục tài khoản thường không hoàn tất trong một HTTP request. Người dùng có thể gửi yêu cầu, đợi email, mở liên kết trên thiết bị khác, bổ sung bằng chứng, chờ xét duyệt rồi mới thay mật khẩu hoặc đăng ký yếu tố xác thực mới. Sau đó, tác vụ thu hồi session và gửi thông báo còn có thể chạy ở các dịch vụ khác.

Trong SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, observability phải hỗ trợ cả mất mật khẩu, MFA, passkey và thiết bị xác thực. Người vận hành cần tìm được đường đi của một workflow, xác định bước đang chậm hoặc lỗi, đồng thời không đưa token hay bằng chứng danh tính vào hệ thống telemetry.

**Recovery trace correlation** là cách nối các lần thực thi đó bằng trace context, định danh nghiệp vụ và quan hệ nhân quả phù hợp. Mục tiêu là trả lời: “Thao tác nào thuộc cùng yêu cầu recovery, thành phần nào đã xử lý và vì sao quy trình chưa đạt kết quả mong muốn?”

Một thiết kế quan trọng là **một workflow recovery có thể liên quan tới nhiều trace**. Không ép mọi bước cách nhau hàng giờ vào một trace đang mở, cũng không dùng trace_id làm quyền truy cập hoặc định danh tài khoản.

Các thuộc tính app.recovery.* trong bài là quy ước riêng của ứng dụng để minh họa; chúng không được trình bày như semantic conventions chuẩn của OpenTelemetry.

## 2. Phân biệt các loại định danh

| Định danh | Phạm vi | Quy tắc sử dụng |
| --- | --- | --- |
| trace_id | Một trace của một lần thực thi phân tán | Do hệ thống tracing quản lý; không là định danh recovery |
| span_id | Một thao tác trong trace | Thay đổi theo từng span |
| request_id | Một request đi qua điểm vào đã định nghĩa | Có thể hỗ trợ tra cứu HTTP; không thay trace_id |
| attempt_id | Một lần người dùng hoặc worker thử thực hiện hành động | Lần thử mới có định danh riêng |
| recovery_id | Một workflow recovery | Được tạo và ràng buộc bởi máy chủ; nối nhiều trace |
| operation_id | Một thao tác nghiệp vụ cần theo dõi hoặc đối soát | Giữ ổn định qua retry của cùng thao tác nếu hợp đồng yêu cầu |
| event_id | Một sự kiện nghiệp vụ hoặc audit | Giữ nguyên khi phát lại cùng sự kiện |
| token_ref | Tham chiếu nội bộ tới token | Không có giá trị sử dụng như bearer token |

Ví dụ, người dùng mở cùng liên kết hai lần sẽ tạo hai request và có thể có hai trace. Nếu cả hai ánh xạ hợp lệ tới cùng recovery record, chúng cùng recovery_id. Lần thứ hai vẫn là một attempt riêng; nó có thể bị từ chối vì quyền đã được sử dụng.

Không tạo trace_id bằng cách cắt một đoạn token, hash email hoặc tái sử dụng account ID. Không dùng recovery_id làm token truy cập. Dù không trực tiếp cấp quyền, các định danh liên kết vẫn có thể tiết lộ quan hệ hoạt động nên cần được giới hạn truy cập.

Trước khi workflow tồn tại hoặc trước khi xác định được recovery record đáng tin cậy, một request có thể chỉ có trace_id và attempt_id. Không bịa recovery_id để mọi bản ghi có đủ trường.

Khi người gọi tự gửi một recovery_id, giá trị đó chưa chứng minh liên kết nghiệp vụ. Dịch vụ phải xác định và kiểm tra quan hệ từ dữ liệu có thẩm quyền trước khi ghi nó như định danh đã được xác nhận.

## 3. Trace, span và span link có vai trò khác nhau

Một span mô tả một đơn vị công việc có điểm bắt đầu và kết thúc. Parent-child thể hiện thao tác con trong quan hệ thực thi đã định nghĩa. Span link có thể nối các span liên quan nhân quả, kể cả khi chúng thuộc các trace khác nhau. [Nguồn: OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/).

Áp dụng cho recovery:

- Một HTTP request gọi đồng bộ sang policy service có thể tiếp tục cùng trace.
- Một job xử lý ngay sau khi phát message có thể dùng quan hệ producer-consumer theo instrumentation và quy ước messaging đã chọn.
- Một job chạy sau thời gian chờ dài có thể tạo trace mới và gắn link tới context của thao tác đã lên lịch.
- Một lần người dùng quay lại từ email thường là request mới, có trace riêng; recovery_id nối nó với workflow trước đó.
- Một bước xét duyệt thủ công là lần thực thi riêng, không phải span giữ mở suốt thời gian chờ nhân viên.

~~~mermaid
flowchart TD
    A[Trace A: nhận yêu cầu] --> A1[Lưu recovery R và outbox]
    A1 -. span link .-> B[Trace B: worker gửi email]
    C[Trace C: người dùng mở liên kết] --> C1[Xác minh và hoàn tất quyền recovery]
    C1 -. span link .-> D[Trace D: xử lý session]
    A1 -. recovery_id R .-> C1
    B -. recovery_id R .-> C1
~~~

Mũi tên đứt biểu thị liên hệ, không phải mọi liên hệ đều là parent-child. Trong hệ thống thực tế, một backend có thể không hỗ trợ điều hướng span link thuận tiện; trường recovery_id trong log hoặc chỉ mục được bảo vệ vẫn giúp tra cứu các trace liên quan.

Một link là quan hệ quan sát, không tự chứng minh hành động được cho phép. Hai trace có cùng recovery_id cũng không có nghĩa chúng đều thành công hay thuộc cùng người dùng đã được xác thực.

## 4. Truyền trace context qua ranh giới dịch vụ

### Dùng propagator thay vì tự nối header

W3C Trace Context định nghĩa traceparent và tracestate. Với định dạng phiên bản 00, traceparent chứa trace ID gồm 32 ký tự hex thường, parent ID gồm 16 ký tự hex thường và trace flags; trace ID hoặc parent ID toàn số 0 không hợp lệ. sampled flag là tín hiệu tracing, không phải cam kết rằng mọi span chắc chắn đã được lưu. [Nguồn: W3C Trace Context](https://www.w3.org/TR/trace-context/).

Ví dụ định dạng:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Giá trị này minh họa trace context, không phải token recovery. Nên dùng propagator của SDK để inject và extract, thay vì tự cắt chuỗi, tự tạo parent ID hoặc tự sao chép nguyên header sang mọi nơi.

tracestate dành cho ngữ cảnh tracing theo nhà cung cấp; không dùng nó làm nơi chứa email, account ID, trạng thái xác minh hoặc credential. Quyền xử lý recovery phải dựa trên dữ liệu nghiệp vụ và chính sách, không dựa trên header quan sát.

### Ranh giới tin cậy của context

Client có thể tự gửi traceparent hoặc baggage. Một header đúng cú pháp vẫn có thể do kẻ tấn công tạo. Nó không xác thực người gửi, tenant hay quan hệ với một recovery request.

Ở điểm vào công khai, cần có chính sách rõ ràng: chỉ chấp nhận context phù hợp từ nguồn được tin cậy hoặc tạo root trace nội bộ mới. Nếu giữ liên hệ với context bên ngoài, phải phân biệt nguồn và áp dụng giới hạn; không coi context đó là định danh nghiệp vụ đáng tin cậy.

Không cho bên ngoài buộc hệ thống lưu mọi trace chỉ bằng cách bật sampled flag. Quyết định thu thập phải nằm trong chính sách và ngân sách telemetry của dịch vụ.

OpenTelemetry lưu ý rủi ro của context giả từ bên ngoài, việc truyền context sang dịch vụ không tin cậy và dữ liệu nhạy cảm trong baggage. Vì vậy, outbound propagation cần được kiểm soát theo đích đến. [Nguồn: OpenTelemetry — Context propagation, Security best practices](https://opentelemetry.io/docs/concepts/context-propagation/#security-best-practices).

Ví dụ, hệ thống có thể cho phép propagation giữa các dịch vụ nội bộ nhưng không gửi baggage hoặc định danh nội bộ sang nhà cung cấp email. Trace client nội bộ vẫn đo được lần gọi nhà cung cấp mà không cần chia sẻ toàn bộ context với họ.

## 5. Correlation trong một request xử lý recovery

Một cây span minh họa cho bước hoàn tất đặt lại mật khẩu:

~~~text
HTTP server span: POST /recovery/complete
  recovery.token.validate
    database lookup
  recovery.policy.evaluate
  recovery.credential.replace
    database transaction
      lock account and recovery grant
      consume grant
      update credential and security epoch
      persist audit/outbox records
  recovery.response.prepare
~~~

Tên span cần ổn định, không chứa token, email hoặc recovery_id. Định danh được phép liên kết nằm trong thuộc tính riêng có kiểm soát truy cập.

Một tập thuộc tính riêng của ứng dụng có thể gồm:

~~~text
app.recovery.id       = recovery-ref-42
app.recovery.purpose  = PASSWORD_RESET
app.recovery.step     = token_validation
app.recovery.outcome  = DENIED
app.recovery.reason   = TOKEN_EXPIRED
~~~

Chỉ thêm app.recovery.id sau khi máy chủ xác định được quan hệ đáng tin cậy. Một token không hợp lệ hoặc không ánh xạ được tới bản ghi không cần có trường này.

outcome nghiệp vụ và trạng thái kỹ thuật của span là hai chiều khác nhau. Bộ xác minh hoạt động bình thường nhưng từ chối token hết hạn không giống với lỗi kết nối cơ sở dữ liệu. Cần giữ mã lý do có giới hạn và quy ước trạng thái phù hợp cho thao tác, tránh biến mọi từ chối dự kiến thành lỗi hệ thống.

OpenTelemetry có các trạng thái span Unset, Error và Ok. Những trạng thái đó mô tả kết quả thao tác được theo dõi; chúng không thay quyết định cấp quyền recovery hay sự kiện audit xác nhận thay credential. [Nguồn: OpenTelemetry — Span Status](https://opentelemetry.io/docs/concepts/signals/traces/#span-status).

Nếu agent hoặc framework đã tạo server span, không tự tạo thêm một server span cùng nghĩa chỉ để có trace. Manual instrumentation nên bổ sung các bước nghiệp vụ mà instrumentation hiện có chưa thể hiện.

Kết thúc span đúng ranh giới công việc. Không để span của request tiếp tục mở đến khi email được đọc hoặc session ở một hệ thống ngoài được thu hồi.

## 6. Outbox, hàng đợi và job chạy trễ

Recovery thường dùng outbox để phát email, thông báo hoặc lệnh xử lý session sau khi thay đổi nghiệp vụ đã commit. Có thể lưu context quan sát tối thiểu cùng bản ghi công việc để nối bước trước với bước sau.

Metadata minh họa:

~~~json
{
  "event_id": "evt-delivery-42",
  "operation_id": "op-delivery-42",
  "recovery_id": "recovery-ref-42",
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
}
~~~

Đây chỉ là metadata correlation, không phải toàn bộ nội dung job. Nếu job cần gửi một bí mật, bí mật đó phải được xử lý trong kênh nghiệp vụ riêng có bảo vệ; không đưa nó vào metadata tracing hoặc log message.

Các nguyên tắc thiết kế:

1. Ghi metadata công việc cùng transaction nghiệp vụ khi cần bảo toàn quan hệ với sự kiện đã commit.
2. Chỉ lưu các trường context được phép; không dump toàn bộ HTTP header hoặc baggage vào outbox.
3. Worker xác minh envelope và tải dữ liệu công việc theo quyền của mình; metadata tracing không thay việc kiểm tra tenant hoặc resource.
4. Chọn một quy tắc rõ ràng về tiếp tục trace hay tạo root mới có span link.
5. Từng lần thực thi worker có span riêng và delivery_attempt riêng nếu cần theo dõi retry.
6. event_id hoặc operation_id vẫn ổn định cho cùng sự kiện hoặc thao tác theo hợp đồng; không dùng span_id để chống xử lý trùng.

Với job chạy sau nhiều giờ hoặc sau một khoảng cooldown, tạo trace mới có link thường giúp thể hiện đúng một lần thực thi mới. Đây là lựa chọn thiết kế cho workflow dài; không có quy tắc bắt buộc rằng mọi message luôn phải bắt đầu một trace mới.

Khi relay gửi lại cùng sự kiện, trace của lần gửi hoặc xử lý lại có thể khác. Quyền dùng token một lần và idempotency vẫn được đảm bảo trong nghiệp vụ; correlation chỉ giúp quan sát những lần thử đó.

Nếu một consumer xử lý batch từ nhiều nguồn, một span chỉ có một parent. Có thể dùng nhiều link có giới hạn để biểu diễn nguồn, hoặc tách các span xử lý từng message theo quy ước instrumentation. Không gắn tùy tiện toàn bộ batch vào recovery_id của message đầu tiên.

Thời gian chờ do chính sách, thời gian nằm trong hàng đợi và thời gian worker xử lý là ba đại lượng khác nhau. Không biểu diễn chúng thành một span xử lý liên tục rồi kết luận worker chậm.

## 7. Ví dụ Java: trace mới cho worker và link về bước phát công việc

Đoạn mã dưới minh họa việc bọc một bước giao việc bằng OpenTelemetry API. tracer đã được cấu hình từ bên ngoài; origin đã được extract qua propagator và xử lý theo chính sách tin cậy; recoveryRef đã được xác định từ job hợp lệ.

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanBuilder;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;

final class RecoveryDeliveryTracing {
    static void run(
            Tracer tracer,
            SpanContext origin,
            String recoveryRef,
            Runnable deliveryWork) {

        SpanBuilder builder = tracer
                .spanBuilder("recovery.delivery.process")
                .setSpanKind(SpanKind.CONSUMER)
                .setNoParent()
                .setAttribute("app.recovery.id", recoveryRef)
                .setAttribute("app.recovery.step", "delivery");

        if (origin != null && origin.isValid()) {
            builder.addLink(origin);
        }

        Span span = builder.startSpan();
        try (Scope ignored = Context.root().with(span).makeCurrent()) {
            deliveryWork.run();
            span.setAttribute(
                    "app.recovery.outcome", "PROCESSING_COMPLETED");
        } catch (RuntimeException failure) {
            span.setAttribute(
                    "app.recovery.outcome", "PROCESSING_FAILED");
            span.setStatus(StatusCode.ERROR, "delivery processing failed");
            throw failure;
        } finally {
            span.end();
        }
    }
}
~~~

setNoParent tạo root cho lần thực thi này; addLink giữ quan hệ với nguồn. Scope đóng khi thoát khối và span luôn được kết thúc. Context.root().with(span) giúp không mang theo baggage của một ngữ cảnh khác đang còn trên thread. Cách quản lý context và span này sử dụng API được mô tả trong tài liệu Java của OpenTelemetry. [Nguồn: OpenTelemetry Java — Record Telemetry with API](https://opentelemetry.io/docs/languages/java/api/).

PROCESSING_COMPLETED ở đây chỉ nói Runnable đã hoàn tất theo hợp đồng của nó. Nếu bước đó mới đưa thông báo vào hàng đợi nhà cung cấp, không được diễn giải là người dùng đã nhận email. Mã này cũng không thay thế giao dịch, chống xử lý trùng hay kiểm tra quyền của deliveryWork.

Không gọi recordException với thông điệp tùy ý khi exception có thể chứa URL reset, response body hoặc dữ liệu cá nhân. Ví dụ chỉ ghi mã lỗi an toàn; nơi xử lý exception ở tầng ngoài cũng phải tuân thủ cùng quy tắc dữ liệu.

Với thread pool hoặc CompletableFuture, không giả định context tự đi theo mọi lần chuyển thread. Cần cơ chế propagation phù hợp với executor hoặc framework đang dùng. Không dùng một biến global để giữ “recovery hiện tại”.

Nếu bổ sung MDC cho logger, phải đặt và khôi phục hoặc xóa các trường trong phạm vi tương ứng. Đóng OpenTelemetry Scope không tự đảm bảo mọi MDC tùy chỉnh đều được dọn. Một thread được tái sử dụng không được mang recovery_id của người dùng trước sang job sau.

## 8. Liên kết log và audit với trace

Trace giúp tìm thao tác và thời gian xử lý; log có cấu trúc giúp hiểu kết quả từng bước. Audit giữ những sự kiện bảo mật theo hợp đồng riêng, chẳng hạn quyền token đã được tiêu thụ hoặc credential đã thay đổi.

Mô hình log OpenTelemetry có các trường TraceId và SpanId để gắn log với context xử lý; chúng là trường tùy chọn. Nếu có SpanId thì nên có TraceId tương ứng. [Nguồn: OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/#trace-context-fields).

Ví dụ một biểu diễn JSON của log ứng dụng, không phải payload OTLP nguyên bản:

~~~json
{
  "timestamp": "2026-11-24T04:22:10.315Z",
  "service": "account-recovery",
  "event": "recovery.token.rejected",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "b9c7c989f97918e1",
  "attempt_id": "attempt-ref-7",
  "recovery_id": "recovery-ref-42",
  "purpose": "PASSWORD_RESET",
  "outcome": "DENIED",
  "reason_code": "TOKEN_EXPIRED"
}
~~~

trace_id và span_id lấy từ context thực sự đang hoạt động, không sao chép trực tiếp từ header đầu vào vào log để giả định đó là span hiện tại. recovery_id lấy từ liên kết nghiệp vụ đã xác định.

Khi ghi audit outbox trong transaction, có thể gắn trace context của thao tác gây ra sự kiện. Lúc relay phát lại audit event, giữ nguyên context nguyên nhân đã ghi; nếu cần đo lần phát của relay, thêm context riêng với vai trò rõ ràng. Không thay trace gốc của sự kiện bằng trace của lần relay cuối cùng.

Một audit event không có trace_id vẫn có thể là sự kiện hợp lệ, ví dụ tác vụ cũ hoặc quá trình phục hồi trạng thái không có span hoạt động. Không tạo một trace ID giả chỉ để điền đủ schema. event_id, recovery_id và dấu vết nghiệp vụ vẫn phải giữ đúng ý nghĩa.

Nếu trace không được lấy mẫu hoặc đã hết thời hạn lưu, log và audit vẫn có thể còn định danh của trace đó. Giao diện điều tra nên thể hiện “không có dữ liệu trace khả dụng” thay vì kết luận thao tác chưa từng xảy ra.

Không dùng log kỹ thuật hoặc span event thay cho audit bền vững về thay đổi credential. Một span có thể bị lấy mẫu bỏ, exporter có thể lỗi và thời hạn giữ trace thường khác thời hạn giữ audit.

## 9. Không biến correlation thành một kênh rò bí mật

### Những dữ liệu phải tách khỏi telemetry

| Dữ liệu | Cách xử lý trong thiết kế minh họa |
| --- | --- |
| Raw token, OTP, recovery code | Không ghi; dùng token_ref độc lập khi cần |
| Reset URL có query hoặc fragment bí mật | Không ghi URL đầy đủ; dùng route hoặc operation chuẩn hóa |
| Password, password hash, seed MFA, private key | Không đưa vào span, log, link hoặc baggage |
| Session cookie, access token, refresh token | Không dùng làm correlation ID |
| Hồ sơ identity proofing | Giữ ở kho bằng chứng riêng; telemetry chỉ có evidence_ref được phép |
| Email, số điện thoại, tên thật | Loại khỏi context tracing; chỉ dùng dữ liệu tối thiểu được phê duyệt |
| Request/response body của nhà cung cấp | Không tự động dump; ghi mã kết quả đã chuẩn hóa |
| Header do client tự tạo | Parse, giới hạn và áp dụng chính sách propagation |

Chỉ xóa token trong log ứng dụng là chưa đủ nếu HTTP instrumentation vẫn thu URL đầy đủ, proxy ghi query string hoặc exception chứa request của nhà cung cấp. Cần áp dụng giới hạn tại các nơi thu nhận, không chỉ ở dashboard cuối cùng.

Tương tự, ghi câu SQL có tham số bind hoặc chụp request body trong công cụ chẩn đoán có thể đưa token và bằng chứng vào telemetry. Tracing nên thể hiện loại thao tác, thời gian và kết quả được chuẩn hóa; không cần bản sao bí mật để liên kết request.

Baggage không phải nơi chứa recovery_id theo mặc định, càng không phải nơi chứa trạng thái “đã xác minh”. Trong thiết kế của bài, các định danh nghiệp vụ chỉ được truyền trong kênh nội bộ đã chọn và gắn vào những span cần thiết. Việc thêm vào baggage có thể khiến dữ liệu lan sang nhiều dịch vụ ngoài dự kiến.

### Liên kết từ email hoặc trình duyệt quay lại

Không nhét traceparent, baggage hoặc trace_id nội bộ vào reset URL để nối trace trước và sau khi người dùng mở email. URL có thể đi qua hệ thống quét liên kết, lịch sử trình duyệt, analytics và các log trung gian.

Sau khi nhận token qua giao thức recovery, máy chủ kiểm tra theo quy trình an toàn và dùng bản ghi có thẩm quyền để tìm recovery_id. Request mới có trace mới; quan hệ nghiệp vụ đủ để tìm lại những lần thực thi trước mà không lộ context tracing trong URL.

Không coi việc trình quét email mở URL là bằng chứng người dùng đã đọc email hoặc cho phép thay credential. Một trace ghi nhận truy cập chỉ chứng minh endpoint đã được gọi trong phạm vi quan sát.

### Quyền tra cứu cũng cần được kiểm soát

Biết trace_id hoặc recovery_id không được đủ để xem dữ liệu tài khoản. Backend tra cứu phải kiểm tra quyền của người điều tra và phạm vi tenant. Các bộ lọc bảo mật không được lấy từ baggage hoặc một tenant_ref chưa được xác thực.

Correlation tăng khả năng liên kết hành vi. Ngay cả các ID ngẫu nhiên vẫn cần thời hạn lưu, kiểm soát truy cập và quy tắc xuất dữ liệu phù hợp. Không xem việc bỏ email là đã làm telemetry hoàn toàn vô danh.

## 10. Sampling, metric và giới hạn số lượng giá trị

### Trace có thể không đầy đủ

Head sampling quyết định sớm; tail sampling dùng dữ liệu đã nhận từ trace để chọn giữ theo tiêu chí như lỗi hoặc độ trễ. Head sampling đơn thuần không thể bảo đảm giữ mọi trace có lỗi về sau. [Nguồn: OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/).

Trong recovery, có thể thiết kế ưu tiên giữ các trace liên quan đến lỗi phụ thuộc, độ trễ bất thường, phê duyệt thủ công hoặc sai lệch xử lý session. Tuy nhiên, chính sách này cần giới hạn tải vì kẻ tấn công có thể cố tạo khối lượng lớn đầu vào lỗi.

Tail sampler không khôi phục được span đã bị loại bỏ trước khi đến nó. Khi một workflow chia thành nhiều trace có span link, quyết định giữ một trace cũng không tự giữ mọi trace liên kết. Cần có khả năng điều tra bằng business correlation ngay cả khi một phần trace bị thiếu.

Các sự kiện audit quan trọng không nên phụ thuộc vào quyết định lấy mẫu của trace. Việc lưu đầy đủ sự kiện tiêu thụ quyền, thay credential hoặc phê duyệt là một hợp đồng dữ liệu khác.

### Không đưa định danh từng workflow vào metric label

recovery_id có thể hữu ích trong log hoặc span được bảo vệ, nhưng không phù hợp làm label cho một time series trên mỗi workflow. Tương tự, trace_id, token_ref và email tạo số lượng giá trị rất lớn nếu dùng làm label metric.

Một metric tổng hợp minh họa có thể phân chiều:

~~~text
recovery_step_duration_seconds{
    step="token_validation",
    purpose="PASSWORD_RESET",
    outcome="DENIED"
}
~~~

Tên và label này là ví dụ riêng của ứng dụng, không phải tên metric chuẩn được yêu cầu. step, purpose và outcome dùng danh mục giới hạn. Không thêm recovery_id hoặc raw reason message vào label.

Nếu backend hỗ trợ exemplar, có thể dùng tham chiếu từ một điểm metric sang trace theo cơ chế phù hợp, thay vì tạo label trace_id cho mọi time series. Việc xem trace liên kết vẫn cần quyền truy cập.

Ở phía trace, cũng cần giới hạn số attributes, số links, độ dài giá trị và mức index. Việc một ID không nằm trong metric không có nghĩa có thể index vô hạn ở mọi hệ thống quan sát.

## 11. Đọc timeline mà không suy luận sai về thời gian

Một timeline có thể gồm:

~~~text
09:00:00  Trace A nhận yêu cầu và tạo recovery-ref-42.
09:00:01  Outbox đã có công việc gửi email.
09:00:04  Trace B xử lý công việc; có link tới context nguồn.
09:08:00  Trace C nhận một lần mở liên kết từ trình duyệt khác.
09:08:01  Trace C từ chối vì token đã bị thu hồi.
~~~

Tám phút giữa Trace A và Trace C không phải thời gian CPU của recovery service. Nó có thể bao gồm thời gian giao email, thời gian người dùng chờ và thao tác của trình quét liên kết.

Để hiểu độ trễ, cần tách:

- Thời gian xử lý một request hoặc một job.
- Thời gian công việc chờ trong queue.
- Thời gian trì hoãn theo lịch hoặc cooldown bắt buộc.
- Thời gian chờ người dùng hoặc người phê duyệt.
- Thời gian từ thay credential đến khi chính sách session có hiệu lực.

Đo duration cục bộ bằng cơ chế thời gian của SDK hoặc đồng hồ đơn điệu thích hợp. Không mặc định hiệu của hai timestamp từ hai máy là độ trễ chính xác nếu đồng hồ chưa được đồng bộ hoặc sai số chưa được biết.

Timestamp vẫn hữu ích cho tìm kiếm theo cửa sổ thời gian. Quan hệ parent/link, operation_id và version nghiệp vụ giúp xác định nhân quả; chúng không được thay bằng việc chỉ sắp log theo thời gian collector nhận.

Một span ghi “token validation completed” không tự chứng minh token đã được dùng. Muốn kết luận thay đổi credential đã commit, phải đối chiếu sự kiện và trạng thái có thẩm quyền. Muốn kết luận session đã mất hiệu lực, phải hiểu phạm vi và cơ chế thực thi được xác nhận.

## 12. Những lỗi correlation thường gặp

| Hiện tượng | Nguyên nhân có thể có | Hướng xử lý trong thiết kế |
| --- | --- | --- |
| Mỗi dịch vụ thành một trace rời | Không inject/extract hoặc proxy loại header | Xác định hợp đồng propagation qua từng ranh giới |
| Job gắn với request không liên quan | Context cũ còn trên thread hoặc MDC | Quản lý scope và dọn context theo từng công việc |
| Một workflow có trace kéo dài nhiều giờ | Giữ span mở qua thời gian chờ người dùng | Tách lần thực thi và nối bằng recovery_id hoặc link |
| Các job trong batch cùng một recovery_id | Gắn ID từ message đầu tiên cho cả batch | Gắn context theo từng message hoặc đơn vị công việc |
| Dùng lại token bị đếm là nhiều lần đổi mật khẩu | Nhầm retry kỹ thuật với thao tác nghiệp vụ mới | Phân biệt event_id, operation_id và attempt_id |
| Không tìm thấy trace từ một audit event | Không lấy mẫu, quá hạn lưu hoặc mất dữ liệu | Tra cứu bằng recovery_id và kiểm tra pipeline |
| Trace của hai tenant bị xem chung | Tin metadata từ client hoặc bộ lọc tra cứu sai | Xác định tenant phía máy chủ và phân quyền backend |
| Telemetry có reset URL | Instrumentation, proxy hoặc exception thu quá nhiều | Loại dữ liệu nhạy cảm tại các điểm thu nhận |
| Thu hồi session đã “thành công” nhưng còn truy cập | Nhầm yêu cầu xử lý với hiệu lực thực tế | Đối soát operation và cơ chế vô hiệu hóa có thẩm quyền |

Khi điều tra, một trình tự hữu ích là lấy recovery_id từ hồ sơ được phép truy cập, tìm các attempt và trace liên quan, đi theo parent/link, rồi đối chiếu audit và trạng thái hiện tại. Nếu thiếu trace, xem tình trạng thu thập và lấy mẫu trước khi kết luận chưa có hành động.

Không tìm kiếm bằng cách sao chép raw token vào ô truy vấn của hệ thống quan sát. Dùng tham chiếu nội bộ không cấp quyền và công cụ tra cứu được kiểm soát.

Thiết kế correlation đạt mục đích khi người vận hành nối được các lần thực thi, hiểu chính xác bước nào đã được xác nhận và giải thích được phần dữ liệu còn thiếu, trong khi quyền recovery vẫn do nghiệp vụ quyết định và bí mật không bị lan truyền theo telemetry.
