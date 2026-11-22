# Interceptor order

Một RPC có thể đi qua nhiều interceptor: tracing, correlation ID, metrics, authentication, logging và policy theo method. Thứ tự của chúng quyết định interceptor nào chạy trước, interceptor nào nhìn thấy call bị từ chối sớm và context nào đã sẵn sàng khi handler chạy. Một chain được sắp xếp thiếu chủ ý có thể làm mất metric của request bị chặn, ghi log thiếu trace ID hoặc để request đi sâu trước khi được xác thực.

Trong Spring gRPC, interceptor được thực thi theo cơ chế chain của gRPC Java; Spring cung cấp điểm đăng ký và quản lý cấu hình. Cần phân biệt **thứ tự gọi interceptor**, **thứ tự callback đi qua listener** và **thứ tự đóng call qua ServerCall**. Bài này tập trung vào cách thiết kế, đăng ký và kiểm thử thứ tự đó.

## 1. Mô hình outer và inner

Một chain có thể hình dung như các lớp bọc lồng nhau:

```text
Transport
  -> Interceptor A (outer)
      -> Interceptor B
          -> Interceptor C (inner)
              -> Service handler
```

Ở chiều request, call đi từ lớp ngoài vào lớp trong. Interceptor A có cơ hội kiểm tra hoặc bổ sung context trước B và C. Khi lớp trong gọi tiếp tới handler, các lớp ngoài đã được đi qua.

Với server listener, sự kiện từ transport như `onMessage`, `onHalfClose` và `onCancel` đi qua các listener wrapper về phía handler. Khi service kết thúc call bằng `ServerCall.close`, lời gọi close đi qua các lớp `ServerCall` đã được bọc. Do đó, mỗi interceptor có thể quan sát các giai đoạn khác nhau tùy nó bọc call, listener hay cả hai.

Không nên suy luận thứ tự chỉ từ tên bean hoặc thứ tự file cấu hình. Cách compose của API gRPC Java và extension point Spring gRPC có thể khác nhau; cần xác minh bằng test trên đúng phiên bản đang chạy.

## 2. Thứ tự đề xuất cho server

Một thứ tự logic thường hữu ích:

```text
Incoming RPC
  -> Trace / Context propagation
      -> Metrics
          -> Authentication
              -> Authorization theo method
                  -> Service handler
```

Mỗi lớp có một mục đích:

| Vị trí | Trách nhiệm | Lý do |
| --- | --- | --- |
| Trace/context | Extract trace context, gắn call context | Metrics, auth và handler có thể dùng trace context |
| Metrics | Bắt đầu đo và quan sát status cuối | Có thể ghi nhận cả call bị auth từ chối bên trong |
| Authentication | Xác minh credential, tạo principal | Request không hợp lệ không được đi tới handler |
| Authorization theo method | Kiểm tra caller có được gọi RPC này không | Chặn method trước khi thực thi nghiệp vụ |
| Service handler | Xử lý use case | Chỉ nhận call đã qua các policy chung |

Đây là thứ tự logic mong muốn theo hướng request. Khi đăng ký, phải cấu hình sao cho thứ tự thực thi thực tế đúng với chain này. Nếu metrics nằm bên trong authentication và authentication đóng call ngay, metrics có thể không nhìn thấy call bị từ chối. Nếu tracing/context nằm sau metrics, log hoặc span của metrics có thể thiếu trace context.

Authorization theo tài nguyên cụ thể vẫn thuộc application service vì interceptor chung thường chưa biết đối tượng mà request muốn truy cập. Interceptor có thể kiểm tra quyền gọi method; handler/application layer tiếp tục kiểm tra quyền trên product, order hoặc tenant cụ thể.

Giữ đúng ý nghĩa status khi từ chối: credential thiếu/sai thường là `UNAUTHENTICATED`; caller đã xác thực nhưng không được phép gọi method hoặc truy cập tài nguyên là `PERMISSION_DENIED`. Metrics và tracing bên ngoài nên ghi lại status thực tế này thay vì tự đổi sang một mã chung.

## 3. Thứ tự ở client

Client cũng có thể dùng nhiều interceptor. Một chain logic ví dụ:

```text
Application stub
  -> Trace propagation
      -> Credential attachment
          -> Client metrics
              -> Transport
```

| Vị trí | Trách nhiệm | Lưu ý |
| --- | --- | --- |
| Trace propagation | Inject trace context vào metadata | Phải dùng propagator, không tự ghép traceparent |
| Credential attachment | Gắn credential phù hợp cho call | Không log token; lấy token theo từng call |
| Client metrics | Đo thời gian client chờ và status cuối | Đo tới callback onClose, không kết thúc khi start trả về |

Thứ tự này giúp metric client quan sát call sau khi metadata đã được chuẩn bị. Tuy nhiên, nếu metrics cần đo cả thời gian lấy token hoặc tạo span, vị trí có thể thay đổi. Hãy xác định rõ metric bắt đầu ở đâu rồi mới chọn thứ tự.

Không gắn credential toàn cục vào channel nếu channel được dùng cho nhiều identity hoặc nhiều audience. Credential interceptor phải áp dụng đúng channel/call và không chuyển tiếp token sang backend không được phép nhận token đó.

## 4. Short-circuit ảnh hưởng các interceptor khác

Interceptor có thể kết thúc call mà không gọi interceptor kế tiếp, ví dụ authentication từ chối credential:

```java
if (!credentialVerifier.isValid(token)) {
    call.close(
            Status.UNAUTHENTICATED.withDescription("credentials required"),
            new Metadata());
    return new ServerCall.Listener<>() {};
}
return next.startCall(call, headers);
```

Khi short-circuit:

- Các interceptor ở ngoài đã được thực thi và có thể quan sát call.
- Các interceptor ở trong chưa được gọi.
- Service handler không chạy.
- Interceptor ngoài chỉ ghi nhận kết quả nếu nó đã bọc đúng ServerCall hoặc listener và xử lý đường đóng call.

Đây là lý do metrics hoặc tracing thường được đặt bên ngoài các policy có thể từ chối call. Nếu một interceptor short-circuit nhưng không gọi tiếp, đừng kỳ vọng interceptor bên trong tự ghi log hoặc metrics.

## 5. Exception và status phải đi qua chain

Service có thể kết thúc call bằng status như NOT_FOUND, INVALID_ARGUMENT hoặc INTERNAL. Interceptor quan sát status ở ServerCall.close; client interceptor thường quan sát status ở callback onClose.

Nếu interceptor chỉ ghi log/metrics, nó nên giữ nguyên status và trailers:

```java
ServerCall<ReqT, RespT> monitored =
        new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
            @Override
            public void close(Status status, Metadata trailers) {
                metrics.record(status.getCode());
                super.close(status, trailers);
            }
        };
```

Không đổi mọi exception thành INTERNAL trong nhiều interceptor khác nhau. Chọn một nơi rõ ràng để ánh xạ exception nghiệp vụ sang gRPC status; các interceptor quan sát nên giữ nguyên status đã được xác định. Nếu một interceptor bắt exception rồi ném lại, phải bảo đảm không gọi close hai lần hoặc làm mất cause gốc.

## 6. Thứ tự và Context propagation

Các interceptor như tracing hoặc correlation thường tạo context dùng cho phần còn lại của call. Vì vậy chúng cần chạy trước interceptor nào cần đọc context đó.

Ví dụ:

1. Trace interceptor extract W3C trace context và gắn vào callback.
2. Correlation interceptor đọc hoặc tạo correlation ID rồi gắn vào gRPC Context.
3. Metrics/logging interceptor lấy trace/correlation context để gắn vào log hoặc span attributes.
4. Authentication xác minh token và gắn principal.
5. Handler đọc principal và context để thực hiện use case.

Nếu chuyển công việc sang executor tùy chỉnh, phải propagate context qua executor/task. Thứ tự interceptor đúng không tự bảo đảm context được truyền sang thread mới. Không lưu principal, trace ID hay request ID vào field mutable của singleton interceptor/service vì nhiều RPC chạy đồng thời sẽ ghi đè dữ liệu.

## 7. Đăng ký thứ tự trong gRPC Java và Spring gRPC

Ở gRPC Java, builder và helper API có cách nhận interceptor riêng. Khi dùng helper như `ServerInterceptors.intercept` hoặc `ServerInterceptors.interceptForward`, đọc đúng contract của API đang gọi; tên helper phản ánh cách compose danh sách và không nên thay thế bằng giả định từ một API khác. Với client cũng cần xem tài liệu của cách tạo channel/intercept đang dùng.

Ví dụ đăng ký ở core server builder:

```java
Server server = ServerBuilder.forPort(9090)
        .intercept(traceInterceptor)
        .intercept(metricsInterceptor)
        .intercept(authenticationInterceptor)
        .addService(catalogService)
        .build();
```

Đoạn này cho thấy các interceptor được đăng ký tại server builder; thứ tự thực thi cuối cùng phải được xác nhận theo API builder và phiên bản gRPC Java cụ thể. Không sao chép thứ tự trên sang `ServerInterceptors.intercept(...)` hoặc Spring configuration mà không kiểm tra semantics của extension point.

Trong Spring gRPC, server thường được auto-configure và interceptor được gắn qua extension point của framework. Hãy dùng cơ chế ordering mà đúng phiên bản Spring gRPC hỗ trợ. Không mặc định rằng `@Order`, thứ tự khai báo `@Bean` hoặc thứ tự component scan sẽ quyết định chain nếu tài liệu phiên bản không cam kết điều đó.

Nếu cần thứ tự bắt buộc và framework không cung cấp guarantee rõ, tạo một cấu hình đăng ký tập trung hoặc adapter rõ ràng cho danh sách interceptor. Mục tiêu là một nơi duy nhất có thể review thứ tự, thay vì để nhiều module tự thêm interceptor toàn cục.

## 8. Kiểm thử thứ tự thực tế

Viết test dùng interceptor ghi lại sự kiện vào danh sách thread-safe. Gọi một RPC thành công và một RPC bị từ chối để xác minh cả đường đi bình thường lẫn short-circuit:

```text
Successful call:
trace.enter
metrics.enter
auth.enter
service.invoke
auth.return
metrics.close(OK)
trace.exit

Rejected call:
trace.enter
metrics.enter
auth.enter
metrics.close(UNAUTHENTICATED)
trace.exit
```

Đây là thứ tự mong muốn của ví dụ chain; callback thực tế có thể xen kẽ tùy asynchronous execution. Test nên assert các quan hệ cần thiết, ví dụ trace.enter xảy ra trước metrics.enter, auth chạy trước service và metrics quan sát được status từ auth rejection.

Các ca cần kiểm tra:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| RPC thành công | Mọi interceptor cần thiết chạy đúng thứ tự |
| Credential thiếu/sai | Authentication chặn handler; metrics/tracing bên ngoài vẫn quan sát call |
| Context propagation | Handler và downstream client call đọc được context đã thiết lập |
| Exception trong handler | Status cuối được giữ nguyên và metric ghi đúng một lần |
| Client cancellation | Listener callback và call close không tạo log/metric trùng |
| Hai RPC đồng thời | Không chia sẻ state hoặc thứ tự sự kiện giữa call |
| Nhiều channel/server | Mỗi endpoint nhận đúng interceptor set |

Ưu tiên in-process server/channel cho test chain gRPC thuần. Với Spring integration test, khởi động application context và thực hiện RPC qua bean/channel thật để xác minh framework đã đăng ký đúng danh sách interceptor.

## 9. Các lỗi sắp xếp thường gặp

- **Metrics nằm sau authentication:** call bị từ chối sớm không được tính vào metric chung.
- **Logging chạy trước trace extraction:** log không có trace ID dù metadata đã được gửi.
- **Authorization nằm sau service logic:** nghiệp vụ có thể đã chạy trước khi quyền được kiểm tra.
- **Nhiều interceptor cùng ánh xạ exception:** status bị đổi nhiều lần hoặc cause bị mất.
- **Hai interceptor cùng inject trace context:** metadata bị ghi đè hoặc tạo propagation không nhất quán.
- **Dựa vào thứ tự bean scan:** thứ tự không được bảo đảm giữa môi trường/build khác nhau.
- **Interceptor giữ state per-call trong field:** request đồng thời có thể làm rò context hoặc sai số liệu.

Khi debug, ghi marker ngắn ở `interceptCall`, `startCall`, `onMessage`, `onCancel` và `close` chỉ trong môi trường test. Không ghi metadata nhạy cảm hoặc payload để quan sát thứ tự.

## 10. Checklist review chain

- [ ] Đã vẽ chain theo hướng request từ ngoài vào trong.
- [ ] Đã xác định interceptor nào có thể short-circuit.
- [ ] Metrics/tracing nằm đủ ngoài để quan sát các call bị từ chối theo yêu cầu.
- [ ] Authentication và authorization theo method chạy trước service handler.
- [ ] Trace/correlation context sẵn sàng trước interceptor cần dùng chúng.
- [ ] Status và trailers được giữ nguyên qua interceptor quan sát.
- [ ] Đã đọc contract thứ tự của API gRPC Java/Spring đang dùng.
- [ ] Không dựa vào thứ tự component scan hoặc khai báo bean nếu không có guarantee.
- [ ] Có integration test cho success, rejection, error, cancellation và concurrency.
- [ ] Interceptor không giữ mutable state của từng call trong field dùng chung.

**Tự kiểm tra**

**Câu 1.** Vì sao metrics interceptor thường cần nằm ngoài authentication interceptor?

*Đáp án:* Để metrics có thể quan sát cả call bị authentication từ chối sớm. Nếu metrics nằm bên trong, short-circuit có thể khiến nó không được gọi.

**Câu 2.** Khi request đi qua chain, interceptor ngoài hay trong chạy trước?

*Đáp án:* Theo mô hình chain, call đi từ outer vào inner. Callback/listener và các wrapper phản hồi đi qua các lớp bọc theo chiều tương ứng; phải kiểm thử cách compose cụ thể.

**Câu 3.** Vì sao không thể mặc định thứ tự @Bean là thứ tự interceptor?

*Đáp án:* Thứ tự chain do extension point/framework và API gRPC Java quyết định. Nếu framework không cam kết bean order, thứ tự tạo bean không đủ để chứng minh thứ tự thực thi.

**Câu 4.** Interceptor authentication từ chối call mà không gọi next thì interceptor bên trong có chạy không?

*Đáp án:* Không. Các interceptor bên trong và service handler bị bỏ qua; interceptor ngoài chỉ quan sát được kết quả nếu đã bọc call/listener đúng cách.

**Câu 5.** Cách xác minh chain có đúng trong Spring gRPC là gì?

*Đáp án:* Viết integration test khởi động cấu hình Spring thực tế, gọi RPC thành công và bị từ chối, rồi assert thứ tự marker, status và việc metrics/tracing quan sát được call.

Thứ tự interceptor là một phần của hành vi bảo mật và vận hành của Spring gRPC. Hãy thiết kế chain theo trách nhiệm, đặt các lớp quan sát đủ ngoài, thực hiện authentication trước handler, giữ nguyên status và xác minh thứ tự trên cấu hình thực tế bằng integration test.
