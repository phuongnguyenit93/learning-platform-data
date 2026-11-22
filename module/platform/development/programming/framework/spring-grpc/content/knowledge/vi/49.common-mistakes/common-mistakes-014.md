# Log toàn bộ payload và credential

Một lỗi bảo mật phổ biến khi phát triển dịch vụ Spring gRPC là ghi nguyên request, response hoặc toàn bộ metadata vào log để tiện debug. Cách làm này có thể đưa access token, API key, dữ liệu cá nhân, thông tin đơn hàng và nội dung nghiệp vụ vào hệ thống lưu trữ log. Các bản ghi thường được chuyển tiếp đến nhiều nơi như máy chủ log tập trung, nền tảng tìm kiếm, cảnh báo, hệ thống APM và bản sao lưu. Vì vậy, một dòng log tưởng như chỉ phục vụ debug có thể trở thành một bản sao dữ liệu nhạy cảm tồn tại lâu hơn dữ liệu gốc.

Log cần giúp người vận hành trả lời các câu hỏi như RPC nào được gọi, kết quả thành công hay thất bại, mất bao lâu và lỗi xảy ra ở đâu. Hầu hết các câu hỏi vận hành không đòi hỏi phải lưu toàn bộ nội dung request hoặc credential. Với Spring gRPC, hãy thiết kế log theo nguyên tắc dữ liệu tối thiểu: chỉ ghi các trường đã được xác định là an toàn, có mục đích rõ ràng và có thời hạn lưu phù hợp.

## 1. Những dữ liệu có thể bị lộ qua log

Trong một RPC gRPC, dữ liệu nhạy cảm có thể xuất hiện ở nhiều lớp khác nhau:

| Vị trí | Ví dụ | Rủi ro khi ghi nguyên trạng |
|---|---|---|
| Request/response Protocol Buffers | Email, số điện thoại, địa chỉ, nội dung chat, thông tin thanh toán, hồ sơ khách hàng | Lộ dữ liệu cá nhân hoặc bí mật nghiệp vụ; bản ghi có thể chứa nhiều trường lồng nhau |
| gRPC Metadata | `authorization`, API key, cookie, session ID, tenant ID, thông tin định danh | Credential có thể bị sao chép và dùng để giả mạo client |
| Status và trailers | Error description, token làm mới, dữ liệu chẩn đoán, giá trị do downstream trả về | Lộ dữ liệu nội bộ hoặc thông tin nhạy cảm được đính kèm lỗi |
| Exception | Message, cause, stack trace có chứa URL, câu truy vấn, input hoặc response downstream | Lộ dữ liệu qua thông báo lỗi dù payload không được log trực tiếp |
| Trace và metric labels | Span attributes, event, baggage, tag theo user/email/token | Dữ liệu được nhân bản sang nền tảng observability và có thể bị lập chỉ mục |
| Log mạng hoặc debug framework | HTTP/2 frame, header, wire payload, request dump | Có thể ghi cả dữ liệu nhị phân và credential trước khi ứng dụng kịp che giấu |

Credential không chỉ là mật khẩu. Cần xem access token, refresh token, API key, session cookie, mã OTP, private key, secret ký, chuỗi kết nối và URL có chữ ký là dữ liệu bí mật. Thông tin định danh như user ID, tenant ID hoặc subject trong JWT cũng có thể là dữ liệu cá nhân hay dữ liệu nhạy cảm theo chính sách của hệ thống.

### 1.1. Payload Protocol Buffers không tự động an toàn

Các lớp Java được sinh từ `.proto` thường cung cấp `toString()` để hỗ trợ debug. Gọi `request.toString()` hoặc truyền trực tiếp object vào logger có thể in ra các trường của message, kể cả trường lồng nhau. Một thay đổi schema trong tương lai có thể thêm trường nhạy cảm và khiến log bắt đầu thu thập trường đó mà người viết logger không nhận ra.

Ví dụ không an toàn:

```java
// Không làm: message có thể chứa dữ liệu cá nhân hoặc bí mật.
log.debug("CreatePayment request: {}", request);

// Không làm: response có thể chứa token hoặc dữ liệu khách hàng.
log.info("RPC response: {}", response);
```

Đổi mức log từ `INFO` sang `DEBUG` không làm dữ liệu trở nên ít nhạy cảm hơn. Nếu logger được bật trong production để điều tra sự cố, toàn bộ payload vẫn có thể bị lưu vào sink đang hoạt động.

### 1.2. Metadata và trailers cũng là dữ liệu đầu vào

gRPC Java truyền metadata qua đối tượng `io.grpc.Metadata`. Các khóa thường gặp gồm `authorization`, `cookie`, `x-api-key` hoặc các khóa nội bộ do hệ thống định nghĩa. Metadata nhị phân có hậu tố `-bin`; giá trị của chúng có thể là dữ liệu nhị phân được mã hóa khi truyền. Việc dump toàn bộ metadata không an toàn chỉ vì giá trị không hiển thị như văn bản.

Không log `headers`, `trailers`, toàn bộ `Metadata`, hoặc giá trị `Authorization`. Không giả định rằng chỉ metadata do server tạo mới đáng tin cậy: metadata đến từ client và các hệ thống downstream đều có thể chứa dữ liệu do bên ngoài kiểm soát. `Status.getDescription()` và trailers cũng có thể chứa thông tin được thêm ở một tầng khác; khi ghi lỗi, ưu tiên status code và mã lỗi nội bộ đã được chuẩn hóa.

TLS bảo vệ dữ liệu trên đường truyền. TLS không ngăn ứng dụng, interceptor, logger hoặc APM ghi dữ liệu sau khi message đã được giải mã trong tiến trình. Do đó, bật TLS không phải là lý do để log toàn bộ request hoặc metadata.

## 2. Vì sao log toàn bộ payload và credential nguy hiểm

**Credential có thể được tái sử dụng.** Nếu access token hoặc API key xuất hiện trong log, người có quyền đọc log có thể dùng credential đó để gọi dịch vụ trong thời gian token còn hiệu lực. Refresh token, session cookie hoặc secret dài hạn có thể tạo ra rủi ro lớn hơn.

**Phạm vi người truy cập log thường rộng.** Nhóm vận hành, phát triển, hỗ trợ và nhà cung cấp nền tảng quan sát có thể có quyền truy cập khác nhau. Một người cần xem lỗi RPC không nhất thiết được phép xem hồ sơ khách hàng hoặc credential.

**Log có nhiều bản sao.** Log có thể được forward, index, export, lưu trong object storage, snapshot hoặc backup. Xóa một dòng ở giao diện tìm kiếm không đảm bảo mọi bản sao đã biến mất.

**Dữ liệu nhạy cảm dễ xuất hiện trong nhiều hệ thống.** Khi một payload được ghi vào log rồi gắn vào trace hoặc gửi đến công cụ báo lỗi, việc thu hồi dữ liệu trở nên khó hơn. Tag chứa email hoặc token còn có thể bị dùng làm nhãn phân nhóm, gây cardinality cao và lộ thông tin qua giao diện truy vấn.

**Log có thể bị giả mạo hoặc gây nhiễu.** Giá trị metadata do client gửi có thể chứa chuỗi rất dài, ký tự xuống dòng hoặc nội dung được thiết kế để làm sai lệch log. Nếu ghi trực tiếp, kẻ tấn công có thể tạo log injection, tăng chi phí lưu trữ hoặc làm khó việc điều tra.

## 3. Thiết kế log an toàn cho RPC

### 3.1. Dùng allowlist thay vì ghi tất cả rồi tìm cách che

Xác định trước những trường được phép xuất hiện trong log. Một bản ghi vận hành RPC thường chỉ cần:

- Tên method gRPC, ví dụ `package.Service/Method`.
- Kết quả chuẩn hóa, ví dụ mã `OK`, `INVALID_ARGUMENT`, `UNAUTHENTICATED` hoặc `INTERNAL`.
- Thời gian xử lý và, nếu có cơ chế đo tin cậy, kích thước hoặc số lượng ở dạng tổng hợp.
- Correlation ID hoặc trace ID đã được kiểm tra định dạng và được phép ghi theo chính sách.
- Mã lỗi nội bộ không chứa dữ liệu đầu vào hoặc thông tin bí mật.

Không ghi payload, credential, toàn bộ headers/trailers, JWT nguyên bản, private key, cookie, session ID hoặc nội dung exception chưa được kiểm soát. Nếu cần thông tin nghiệp vụ để điều tra, hãy chọn một mã tham chiếu giả danh hoặc một giá trị tổng hợp đã được phê duyệt; không tự ý dùng email, số điện thoại hay ID có thể liên kết ngược với một người.

Allowlist an toàn hơn denylist. Danh sách chặn có thể bỏ sót trường mới, khóa metadata viết khác kiểu hoặc trường nhạy cảm lồng trong message. Với allowlist, trường mới mặc định không được ghi cho đến khi có review.

### 3.2. Ghi metadata có chọn lọc

Nếu cần correlation ID, hãy đọc đúng một khóa metadata đã định nghĩa thay vì serialize cả `Metadata`. Kiểm tra độ dài và tập ký tự trước khi ghi, vì client có thể tự gửi giá trị này. Tốt hơn nữa, server có thể tạo correlation ID nội bộ và trả lại cho client qua response metadata theo quy ước của hệ thống.

Ví dụ, chỉ lấy `x-request-id` dạng ASCII:

```java
private static final Metadata.Key<String> REQUEST_ID_KEY =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

private static String safeRequestId(String candidate) {
    if (candidate == null || !candidate.matches("[A-Za-z0-9._-]{1,64}")) {
        return "-";
    }
    return candidate;
}
```

Không thêm `authorization`, `cookie`, `x-api-key` hoặc khóa `*-bin` vào danh sách log. Nếu một khóa tùy chỉnh có vẻ vô hại, hãy xác nhận chủ sở hữu, ý nghĩa và phân loại dữ liệu trước khi cho phép ghi.

### 3.3. Ghi status code thay vì toàn bộ lỗi

Với gRPC, `Status.Code` thường đủ để phân loại kết quả vận hành. Có thể ghi method, code, thời gian và mã sự kiện nội bộ. Tránh ghi nguyên `Status.getDescription()`, nội dung trailers hoặc `StatusRuntimeException` nếu message/cause có thể chứa payload, địa chỉ nội bộ hay phản hồi từ hệ thống khác.

Stack trace hữu ích khi điều tra lỗi lập trình, nhưng cần kiểm tra các exception được phép đi vào log. Không đưa request object, token hoặc dữ liệu người dùng vào message của exception. Nếu không thể bảo đảm exception message an toàn, hãy log mã sự kiện và loại exception; lưu chi tiết chẩn đoán đã được làm sạch trong hệ thống có quyền truy cập hạn chế.

## 4. Ví dụ ServerInterceptor chỉ ghi trường an toàn

`ServerInterceptor` là vị trí thuận tiện để ghi nhận kết quả và thời gian của một RPC. Interceptor dưới đây chỉ ghi tên method, status code, thời gian xử lý và request ID đã kiểm tra. Nó không đọc payload, không dump metadata và không ghi status description hoặc trailers.

```java
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;

public final class SafeRpcLoggingInterceptor implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SafeRpcLoggingInterceptor.class);

    private static final Metadata.Key<String> REQUEST_ID_KEY =
            Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        String requestId = safeRequestId(headers.get(REQUEST_ID_KEY));
        long startedAt = System.nanoTime();

        ServerCall<ReqT, RespT> loggingCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startedAt);

                        log.info(
                                "grpc_server_call method={} status={} elapsed_ms={} request_id={}",
                                method,
                                status.getCode(),
                                elapsedMs,
                                requestId);

                        super.close(status, trailers);
                    }
                };

        return next.startCall(loggingCall, headers);
    }

    private static String safeRequestId(String candidate) {
        if (candidate == null || !candidate.matches("[A-Za-z0-9._-]{1,64}")) {
            return "-";
        }
        return candidate;
    }
}
```

Đăng ký interceptor theo cơ chế extension mà Spring gRPC starter của dự án hỗ trợ. Cách đăng ký global interceptor khác nhau giữa các starter; không nên sao chép annotation hoặc cấu hình của một starter khác nếu dự án không sử dụng nó.

Mẫu này minh họa log kết quả khi server đóng call. Với streaming RPC, thời gian được đo từ lúc interceptor nhận call đến lúc call đóng; cần thống nhất cách diễn giải metric này với nhóm vận hành. Nếu cần đo thời gian từng message hoặc số byte, dùng cơ chế instrumentation phù hợp và chỉ xuất số liệu tổng hợp đã được phê duyệt. Không thêm listener để in từng request/response message.

Ở client, áp dụng cùng nguyên tắc trong `ClientInterceptor`: ghi method, status code và duration; không ghi `CallOptions`, toàn bộ `Metadata`, request, response hoặc trailers. Với lỗi, chỉ log status code và mã sự kiện an toàn. Correlation ID cần được truyền theo quy ước đã kiểm soát, không lấy tùy tiện một giá trị bất kỳ từ context rồi ghi ra log.

## 5. Khi cần debug payload, tạo bản ghi chẩn đoán riêng

Có tình huống cần biết một request có hình dạng bất thường hoặc một trường có giá trị không hợp lệ. Khi đó, không bật chế độ dump toàn bộ protobuf. Hãy xây dựng một projection dành riêng cho chẩn đoán, chỉ chứa những trường đã được phân loại là an toàn.

Ví dụ, với RPC tạo đơn hàng, có thể ghi số lượng dòng hàng và kết quả kiểm tra schema nếu các số liệu này được chính sách dữ liệu cho phép:

```java
log.debug(
        "create_order_validation item_count={} has_note={} schema_valid={}",
        request.getItemsCount(),
        request.hasCustomerNote(),
        validationResult.isValid());
```

Không ghi nội dung `customerNote`, thông tin thanh toán, địa chỉ hoặc toàn bộ `request`. Ngay cả số lượng hoặc cờ boolean cũng cần được đánh giá theo ngữ cảnh; một giá trị tổng hợp có thể tiết lộ thông tin khi kết hợp với dữ liệu khác.

Nếu cần kiểm tra một giá trị cụ thể, hãy dùng dữ liệu tổng hợp trong môi trường thử nghiệm hoặc tạo fixture đã loại bỏ dữ liệu nhận dạng. Không sao chép payload production vào ticket, chat, file đính kèm hay môi trường dev chỉ để tái hiện lỗi nếu chưa có quy trình phê duyệt và khử định danh.

Tránh viết hàm redaction chung bằng cách duyệt mọi field của protobuf rồi thay một số tên field quen thuộc. Cách làm này dễ bỏ sót field mới, map, repeated field, message lồng nhau và dữ liệu nhạy cảm được nhúng trong chuỗi tự do. Một projection có allowlist theo từng use case dễ review và kiểm thử hơn.

## 6. Kiểm soát log, trace và công cụ quan sát

### 6.1. Áp dụng cùng chính sách cho mọi sink

Chính sách dữ liệu phải áp dụng đồng nhất cho:

- Log ứng dụng từ SLF4J/Logback hoặc logging framework tương đương.
- Log do interceptor, exception handler và thư viện gRPC tạo ra.
- Distributed trace, span attributes, span events và baggage.
- Error tracking, APM, profiler và công cụ thu thập request.
- Log proxy, gateway, service mesh, ingress và load balancer.
- Log CI, artifact debug, file dump và bản sao lưu.

Không gắn access token, email, số điện thoại hoặc payload vào span attribute để tiện tìm kiếm. Không đưa credential vào baggage vì baggage có thể được truyền qua nhiều service và ra ngoài ranh giới tin cậy. Dùng trace ID để liên kết sự kiện; chỉ thêm thuộc tính có phân loại an toàn và cardinality phù hợp.

### 6.2. Cẩn thận với chế độ debug và wire logging

Trước khi bật log mức `DEBUG` hoặc wire logging của HTTP/2/Netty trong production, cần biết chính xác logger nào sẽ ghi gì, dữ liệu đi đến sink nào, ai có thể đọc và thời hạn lưu là bao lâu. Một cấu hình debug ở tầng transport có thể ghi header hoặc frame chứa dữ liệu đã mã hóa ở tầng ứng dụng nhưng đã giải mã ở tiến trình. Chỉ bật tạm thời theo quy trình sự cố, trên phạm vi nhỏ, có người phê duyệt và có thời điểm tắt rõ ràng.

Không để cờ debug nhạy cảm được bật lâu dài qua biến môi trường, config server hoặc cấu hình triển khai. Nếu cần tái hiện lỗi, ưu tiên môi trường kiểm thử với dữ liệu tổng hợp.

### 6.3. Bảo vệ hệ thống lưu trữ log

Giảm dữ liệu được ghi vẫn là biện pháp quan trọng nhất. Bên cạnh đó, hệ thống log cần có phân quyền theo vai trò, xác thực mạnh, mã hóa khi truyền và khi lưu, audit truy cập, thời hạn lưu và quy trình xóa theo chính sách. Hạn chế export và chia sẻ bản ghi. Không coi việc chỉ che token trên giao diện là đã xóa token khỏi index, bản lưu hoặc bản sao lưu.

Redaction ở pipeline thu thập có thể là lớp phòng vệ bổ sung, nhưng không thay thế việc ngăn ứng dụng phát ra dữ liệu nhạy cảm. Bộ lọc regex có thể bỏ sót token được encode, tên field khác, dữ liệu nhị phân hoặc chuỗi nằm trong exception. Kiểm soát ở nguồn giúp tránh dữ liệu bị nhân bản trước khi đến bộ lọc.

## 7. Kiểm thử để ngăn log rò rỉ dữ liệu

Thêm kiểm thử cho các đường ghi log quan trọng, đặc biệt là interceptor và exception handler. Dùng giá trị giả lập dễ nhận diện như `TEST_SECRET_DO_NOT_LOG` trong metadata và payload, thực hiện RPC, sau đó kiểm tra nội dung log được thu lại không chứa chuỗi đó.

Ví dụ tiêu chí kiểm thử:

1. Gửi request có trường nhạy cảm chứa chuỗi canary.
2. Gửi metadata `authorization` và `x-api-key` với giá trị canary.
3. Cho RPC trả về lỗi có description giả lập chứa canary để xác minh logger không ghi description.
4. Thu log từ appender thử nghiệm hoặc test sink.
5. Xác nhận log vẫn có method, status code và duration cần thiết, đồng thời không có bất kỳ canary nào.

Ngoài kiểm thử tự động, review thay đổi schema `.proto`, interceptor, exception handler và logging configuration để tìm các mẫu nguy hiểm như:

```java
log.debug("request={}", request);
log.info("headers={}", headers);
log.error("RPC failed: {}", exception.getMessage());
log.debug("trailers={}", trailers);
```

Các mẫu trên cần được xem xét theo dữ liệu thực tế và thay bằng log có allowlist. Quét mã nguồn chỉ là hỗ trợ; kiểm thử bằng canary chứng minh hành vi của đường chạy cụ thể và nên được duy trì khi thêm RPC mới.

## 8. Xử lý khi credential đã xuất hiện trong log

Nếu phát hiện token, API key hoặc secret đã bị ghi vào log, hãy xem đó là sự cố lộ credential:

1. Xác định loại credential, phạm vi thời gian, service và các sink đã nhận bản ghi.
2. Thu hồi hoặc rotate credential; vô hiệu hóa session/token nếu cơ chế xác thực hỗ trợ.
3. Kiểm tra audit truy cập log và hoạt động dùng credential trong khoảng thời gian có rủi ro.
4. Hạn chế truy cập, xử lý bản ghi và bản sao theo quy trình ứng phó sự cố, chính sách lưu trữ và yêu cầu pháp lý.
5. Sửa logger ở nguồn, bổ sung kiểm thử canary và xác minh các pipeline liên quan không tiếp tục phát dữ liệu.
6. Ghi lại phạm vi ảnh hưởng và bằng chứng xử lý theo quy trình nội bộ.

Chỉ xóa giá trị ở một màn hình tìm kiếm không đủ để kết luận sự cố đã được xử lý. Cần kiểm tra index, archive, export, bản sao lưu và các nền tảng observability nhận dữ liệu chuyển tiếp. Việc xóa phải tuân theo quy trình lưu giữ bằng chứng và chính sách của tổ chức.

## 9. Checklist review trước khi phát hành

- [ ] Không có logger nào gọi `toString()` trên request/response protobuf hoặc serialize toàn bộ payload.
- [ ] Không ghi toàn bộ gRPC Metadata, headers, trailers hoặc giá trị `*-bin`.
- [ ] Access token, refresh token, API key, cookie, OTP và private key không xuất hiện trong log.
- [ ] Log RPC chỉ chứa method, status code, duration và correlation ID đã được kiểm tra hoặc trường allowlist khác.
- [ ] Status description, exception message và stack trace đã được đánh giá để tránh chứa payload hoặc credential.
- [ ] Trace attributes, events, baggage và metric labels tuân theo cùng chính sách dữ liệu.
- [ ] Debug/wire logging production có quy trình bật tạm thời, giới hạn phạm vi và tắt sau điều tra.
- [ ] Hệ thống log có phân quyền, audit truy cập, mã hóa và thời hạn lưu.
- [ ] Kiểm thử canary chứng minh secret giả lập không xuất hiện trong log sau các luồng thành công và thất bại.
- [ ] Có quy trình thu hồi credential và xử lý các bản sao nếu phát hiện rò rỉ.

Một bản log tốt cho Spring gRPC cho phép liên kết một RPC với trace và xác định method, kết quả, thời gian xử lý. Payload và credential chỉ được xử lý trong luồng nghiệp vụ có kiểm soát; chúng không trở thành dữ liệu mặc định của hệ thống log.
