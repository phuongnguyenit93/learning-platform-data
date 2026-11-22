# Graceful retry và idempotent command

**Chương:** Reliability  
**Phạm vi:** Spring gRPC (SPRING_GRPC) dùng hợp đồng Protocol Buffers, mã Java được sinh và triển khai client/server cho unary hoặc streaming RPC. Bài này trình bày cách retry có kiểm soát khi lỗi tạm thời xảy ra và cách thiết kế command idempotent để một thao tác có thể được gửi lại mà không tạo side effect trùng lặp. Hai cơ chế phải được thiết kế cùng nhau: retry cải thiện khả năng phục hồi giao tiếp, còn idempotency bảo vệ tính đúng đắn của nghiệp vụ.

## 1. Retry giải quyết lỗi tạm thời, không sửa lỗi nghiệp vụ

gRPC call có thể thất bại vì server tạm thời không sẵn sàng, kết nối bị reset, proxy đóng connection hoặc dependency quá tải. Một số lỗi chỉ tồn tại trong thời gian ngắn và lần gọi tiếp theo có thể thành công. Retry cho phép client thử lại trong một ngân sách thời gian và số lần hữu hạn.

Retry không phù hợp với mọi lỗi. Nếu request sai schema, caller không có quyền hoặc trạng thái nghiệp vụ không cho phép thao tác, gửi lại cùng request thường chỉ lặp lại thất bại. Retry quá rộng còn có thể làm hệ thống quá tải hơn: khi server đang chậm, hàng loạt client retry đồng thời tạo thêm traffic đúng lúc server cần giảm tải.

Một thiết kế đáng tin cậy phải trả lời được bốn câu hỏi:

1. Status nào có thể retry?
2. Còn bao nhiêu thời gian trong deadline để thử lại?
3. Bao nhiêu attempt được phép và backoff ra sao?
4. Nếu server đã thực hiện command nhưng response bị mất, request lặp lại có tạo side effect lần nữa không?

## 2. Retry và idempotency là hai trách nhiệm khác nhau

Retry quyết định **khi nào** client gửi lại call. Idempotency quyết định **điều gì xảy ra** nếu cùng một command được gửi nhiều lần.

Ví dụ client gửi lệnh tạo thanh toán. Server ghi khoản thanh toán vào database, nhưng connection bị đứt trước khi response tới client. Client không thể biết server đã commit hay chưa. Nếu client gửi lại với một command mới, hệ thống có thể tạo hai khoản thanh toán.

Nếu command mang cùng một idempotency key và server lưu kết quả đã xử lý, lần gửi lại có thể trả đúng response đã lưu mà không thực hiện thao tác lần nữa.

| Cơ chế | Câu hỏi được trả lời | Trách nhiệm |
| --- | --- | --- |
| Retry policy | Có nên thử lại call không? | Phân loại status, attempts, backoff, deadline |
| Idempotency key | Đây có phải cùng một command không? | Nhận diện lệnh lặp qua nhiều request |
| Deduplication store | Command này đã được xử lý chưa? | Lưu key, fingerprint và kết quả |
| Transaction/outbox | Side effect được commit an toàn thế nào? | Đồng bộ dữ liệu nghiệp vụ và ý định gọi hệ thống ngoài |

Retry mà không có idempotency có thể nhân đôi side effect. Idempotency mà không có retry vẫn hữu ích khi client chủ động gửi lại sau timeout hoặc mất kết nối.

## 3. Phân loại gRPC status trước khi retry

Status code là tín hiệu đầu tiên để quyết định có nên retry. Phân loại cần dựa trên semantics của RPC, không chỉ dựa vào tên code:

| Status | Chính sách thường dùng | Lý do |
| --- | --- | --- |
| UNAVAILABLE | Có thể retry có giới hạn | Server hoặc dependency tạm thời không sẵn sàng |
| RESOURCE_EXHAUSTED | Chỉ retry khi contract cho phép và có backoff | Có thể là quota hoặc quá tải; retry ngay có thể làm tình hình nặng hơn |
| ABORTED | Có thể retry toàn bộ transaction/command nếu nghiệp vụ cho phép | Conflict đồng thời hoặc transaction bị hủy |
| DEADLINE_EXCEEDED | Chỉ retry nếu logical call còn deadline và command idempotent; nếu deadline đã hết thì dừng | Server có thể đã xử lý nhưng response đến muộn |
| CANCELLED | Thường không tự retry | Caller đã hủy hoặc call bị hủy theo lifecycle |
| INVALID_ARGUMENT | Không retry | Request vi phạm hợp đồng |
| UNAUTHENTICATED | Không retry cùng credential | Cần xác thực lại hoặc refresh credential theo flow riêng |
| PERMISSION_DENIED | Không retry | Caller không được phép thực hiện thao tác |
| NOT_FOUND | Thường không retry | Tài nguyên không tồn tại theo semantics hiện tại |
| FAILED_PRECONDITION | Không retry mù quáng | Trạng thái nghiệp vụ cần được thay đổi trước |
| INTERNAL / UNKNOWN | Mặc định không retry tự động | Có thể là lỗi code hoặc lỗi không xác định; chỉ retry khi contract đã phân loại rõ |

UNAVAILABLE thường là status phù hợp nhất cho lỗi tạm thời có thể phục hồi. Tuy nhiên, nếu server trả UNAVAILABLE vì một điều kiện vĩnh viễn, retry vẫn không giúp ích. Server và client phải thống nhất semantics của status.

Không chuyển mọi exception thành UNAVAILABLE chỉ để bật retry. Làm vậy khiến client thử lại lỗi nghiệp vụ, lỗi dữ liệu hoặc bug lập trình.

Nếu một logical call đã kết thúc vì deadline thực sự hết, không thể tiếp tục retry bên trong call đó. Nếu workflow còn muốn thử lại sau đó, nó tạo một logical call mới với deadline mới nhưng phải giữ nguyên idempotency key và payload của cùng command.

## 4. Retry policy phải có giới hạn

Một retry policy thường gồm:

- **maxAttempts:** tổng số lần gọi tối đa, bao gồm lần đầu.
- **initialBackoff:** thời gian chờ trước lần retry đầu.
- **maxBackoff:** giới hạn trên của thời gian chờ.
- **backoffMultiplier:** hệ số tăng backoff sau mỗi lần thất bại.
- **retryableStatusCodes:** tập status được phép retry.
- **deadline:** giới hạn tổng thời gian cho toàn bộ logical call.
- **retry budget:** giới hạn tổng traffic retry để tránh khuếch đại sự cố.

Ví dụ, maxAttempts bằng 4 có nghĩa là tối đa một lần gọi ban đầu và ba lần retry. Nếu lần đầu thất bại, client chờ rồi mới thử lại; không tạo vòng lặp vô hạn.

Không đặt maxAttempts quá cao để che giấu service không ổn định. Retry là cơ chế phục hồi ngắn hạn, còn lỗi kéo dài cần được xử lý bằng capacity, circuit breaker, load shedding, health check và sửa nguyên nhân gốc.

## 5. Exponential backoff và jitter

Nếu mọi client retry sau cùng một khoảng cố định, chúng có thể đồng loạt gọi lại server và tạo retry storm. Exponential backoff tăng dần thời gian chờ; jitter ngẫu nhiên hóa thời điểm retry.

Một cách tính full jitter:

\[
cap_n = \min(maxBackoff,\ initialBackoff \times multiplier^{n-1})
\]

\[
delay_n = random(0,\ cap_n)
\]

Trong đó n là số thứ tự lần retry. Ví dụ initial backoff 100 ms, multiplier 2 và max backoff 1 s:

| Lần retry | Backoff cap | Khoảng delay với full jitter |
| --- | ---: | ---: |
| 1 | 100 ms | 0–100 ms |
| 2 | 200 ms | 0–200 ms |
| 3 | 400 ms | 0–400 ms |
| 4 | 800 ms | 0–800 ms |
| 5 trở đi | 1.000 ms | 0–1.000 ms |

Jitter giảm khả năng nhiều client đồng bộ retry. Với hệ thống có yêu cầu tải cao, kết hợp retry budget và circuit breaker để giới hạn tổng số lần gọi lại.

## 6. Deadline là ngân sách chung của toàn bộ attempts

gRPC deadline giới hạn thời gian caller chờ một logical RPC. Mỗi retry dùng một phần ngân sách đó; không được cấp lại deadline đầy đủ cho từng attempt.

Ví dụ caller đặt deadline 2 giây. Lần đầu mất 900 ms, backoff 200 ms, lần thứ hai chỉ còn khoảng 900 ms cho xử lý và network. Nếu không đủ thời gian cho một attempt có ý nghĩa, client nên dừng và trả lỗi thay vì gửi request chắc chắn hết hạn.

Khi gọi downstream service, server nên truyền deadline còn lại theo gRPC Context. Không tạo deadline mới dài hơn deadline của request gốc; nếu không, một dependency chậm có thể tiếp tục chạy sau khi caller đã bỏ cuộc.

Trong Java:

~~~java
OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);

GetOrderResponse response = stub.getOrder(request);
~~~

Nếu channel có retry policy, deadline này bao phủ logical call và các attempt do gRPC quản lý. Với application-level retry tự viết, cần tính thời gian còn lại trước mỗi attempt và backoff; không tạo stub với deadline mới vô hạn cho từng vòng.

## 7. Cấu hình retry bằng gRPC service config

gRPC Java hỗ trợ retry policy qua service config. Ví dụ cấu hình cho unary method payments.v1.PaymentService/CreatePayment:

~~~json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "payments.v1.PaymentService",
          "method": "CreatePayment"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.1s",
        "maxBackoff": "1s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": [
          "UNAVAILABLE"
        ]
      }
    }
  ]
}
~~~

Service config gắn policy với đúng service/method. Không áp dụng retry cho toàn bộ RPC nếu có method đọc, method ghi và method không idempotent với semantics khác nhau.

gRPC retry engine chỉ retry khi call chưa bị commit theo quy tắc của runtime. Khi client đã nhận response headers, call được commit và retry tự động dừng; một số giới hạn buffering cũng ảnh hưởng khả năng replay request. Vì vậy, retry policy không thể thay thế idempotency ở application layer.

Với gRPC Java, channel builder có thể nhận service config và bật retry:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress(host, port)
        .defaultServiceConfig(serviceConfig)
        .enableRetry()
        .build();
~~~

serviceConfig là map tương ứng với cấu trúc JSON ở trên. Trong Spring gRPC, channel thường được starter tạo và quản lý. Hãy cấu hình service config qua channel builder customizer hoặc extension point mà phiên bản starter đang dùng hỗ trợ, trước khi channel được build. Không tạo channel thứ hai chỉ để lách cấu hình của starter, vì điều đó làm lifecycle và observability khó kiểm soát.

Kiểm tra gRPC Java version và retry feature đang bật trong runtime. Các phiên bản, channel provider hoặc service discovery resolver có thể ảnh hưởng cách service config được cung cấp. Test cấu hình bằng in-process/transport test và quan sát số attempt thực tế.

## 8. Không chồng nhiều tầng retry

Một call có thể bị retry ở nhiều tầng: gRPC channel, application service, Spring Retry, HTTP client bên dưới hoặc service downstream. Nếu mỗi tầng cho phép 3 attempts, một logical request có thể tạo số lần gọi lớn hơn dự kiến.

Ví dụ ba tầng retry độc lập, mỗi tầng tối đa 3 attempts, có thể khuếch đại tới 27 lần gọi ở tầng sâu nhất trong trường hợp xấu.

Chọn một tầng chịu trách nhiệm retry cho mỗi dependency boundary. Nếu cần retry ở nhiều tầng, tính tổng số attempts và deadline budget một cách tường minh. Không bọc một gRPC stub đã có retry policy bằng vòng lặp retry vô hạn khác.

## 9. Thiết kế idempotent command trong Protocol Buffers

Với command có side effect như tạo payment, chuyển tiền, tạo order hoặc đặt chỗ, đưa idempotency key vào request contract:

~~~proto
syntax = "proto3";

package payments.v1;
option java_package = "com.example.payments.grpc";
option java_multiple_files = true;

service PaymentService {
  rpc CreatePayment(CreatePaymentRequest)
      returns (CreatePaymentResponse);
}

message CreatePaymentRequest {
  string idempotency_key = 1;
  string source_account_id = 2;
  string destination_account_id = 3;
  int64 amount_minor_units = 4;
  string currency = 5;
}

message CreatePaymentResponse {
  string payment_id = 1;
  string state = 2;
}
~~~

Client tạo key một lần cho một ý định nghiệp vụ và giữ nguyên key đó qua mọi retry. Không tạo UUID mới ở mỗi attempt, vì server sẽ coi mỗi UUID là một command khác nhau.

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;

String idempotencyKey = UUID.randomUUID().toString();

CreatePaymentRequest request = CreatePaymentRequest.newBuilder()
        .setIdempotencyKey(idempotencyKey)
        .setSourceAccountId("account-A")
        .setDestinationAccountId("account-B")
        .setAmountMinorUnits(25_000)
        .setCurrency("USD")
        .build();

CreatePaymentResponse response = paymentStub
        .withDeadlineAfter(3, TimeUnit.SECONDS)
        .createPayment(request);
~~~

Nếu client timeout và người dùng hoặc workflow quyết định gửi lại cùng thao tác, phải dùng lại key và cùng nội dung command. Nếu người dùng tạo một thao tác mới, phải tạo key mới.

## 10. Quy tắc của idempotency key

Một idempotency key hữu ích cần có phạm vi và vòng đời rõ ràng:

1. **Unique trong scope:** key thường duy nhất theo tenant/caller, operation và key value.
2. **Ổn định qua retry:** mọi attempt của cùng command dùng một key.
3. **Ràng buộc với payload:** server lưu fingerprint của các field nghiệp vụ.
4. **Không dùng làm credential:** biết key không đồng nghĩa có quyền xem kết quả.
5. **Retention đủ dài:** giữ record ít nhất bằng thời gian client/workflow có thể retry hoặc replay.
6. **Kiểm tra authorization trước khi replay:** caller hiện tại vẫn phải có quyền truy cập kết quả.

Fingerprint nên được tạo từ biểu diễn canonical của các field nghiệp vụ: source account, destination account, amount, currency và operation version. Không đưa trace ID, request timestamp, deadline hoặc metadata quan sát vào fingerprint vì các giá trị đó có thể thay đổi giữa các attempt.

Không mặc định hash của request.toByteArray() là fingerprint nghiệp vụ phù hợp. Unknown fields, schema evolution hoặc thay đổi cách serialize có thể làm fingerprint đổi dù ý nghĩa command không đổi. Hãy chuẩn hóa field nghiệp vụ theo một quy tắc versioned rồi hash biểu diễn đó.

## 11. Hành vi khi key được gửi lại

Server cần phân biệt ba trường hợp:

| Trường hợp | Hành vi |
| --- | --- |
| Key chưa từng tồn tại | Thực hiện command và lưu kết quả |
| Cùng key, cùng fingerprint, đã hoàn tất | Trả lại kết quả đã lưu, không thực hiện side effect lần nữa |
| Cùng key, fingerprint khác | Từ chối vì key đang bị dùng cho command khác |

Nếu hai request cùng key đến đồng thời, unique constraint trong database phải bảo vệ khỏi hai transaction cùng thực hiện side effect. Kiểm tra key bằng một câu SELECT rồi mới INSERT là không đủ: hai request có thể cùng thấy “chưa tồn tại” trước khi một trong hai ghi dữ liệu.

Khi key đã tồn tại nhưng trạng thái đang xử lý, API cần một policy rõ ràng. Với thiết kế lưu trạng thái IN_PROGRESS đã commit riêng, request trùng có thể chờ trong giới hạn hoặc trả status retryable có backoff. Với thiết kế lưu record, mutation và response trong cùng một transaction, request trùng sẽ chờ unique conflict được giải quyết; sau khi transaction đầu commit, request sau đọc được kết quả hoàn tất. Chọn một mô hình và test concurrency.

## 12. Lưu deduplication record bền vững

Một bảng idempotency có thể lưu:

| Cột | Mục đích |
| --- | --- |
| tenant_id | Scope của caller/tenant |
| operation | Tên/version của command |
| idempotency_key | Key do client tạo |
| request_hash | Fingerprint của payload nghiệp vụ |
| state | IN_PROGRESS hoặc COMPLETED nếu dùng state machine |
| response_payload | Response đã serialize để replay |
| created_at, expires_at | Retention và cleanup |

Tạo unique constraint trên (tenant_id, operation, idempotency_key). Có thể thêm principal/client scope nếu contract yêu cầu phân biệt caller trong cùng tenant. Khi replay, vẫn phải kiểm tra quyền hiện tại trước khi trả response đã lưu.

Ví dụ DDL rút gọn cho PostgreSQL:

~~~sql
CREATE TABLE rpc_idempotency (
    tenant_id         text        NOT NULL,
    operation         text        NOT NULL,
    idempotency_key   text        NOT NULL,
    request_hash      bytea       NOT NULL,
    state             text        NOT NULL,
    response_payload  bytea,
    created_at        timestamptz NOT NULL DEFAULT now(),
    expires_at        timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, operation, idempotency_key)
);
~~~

Thao tác claim có thể dùng INSERT ... ON CONFLICT DO NOTHING RETURNING idempotency_key. Nếu trả về một dòng, transaction đã claim key. Nếu không có dòng, đọc record hiện có và so sánh fingerprint. Đây là cú pháp PostgreSQL; database khác cần cơ chế upsert/unique conflict tương đương.

Với command có thể xử lý nhanh trong một database transaction, một pattern là:

1. INSERT ... ON CONFLICT DO NOTHING cho key/scope và fingerprint.
2. Nếu insert thành công, transaction này sở hữu command; thực hiện domain mutation.
3. Lưu outbox record nếu cần gọi hệ thống ngoài.
4. Serialize response và cập nhật idempotency record thành COMPLETED.
5. Commit mutation, outbox và response record trong cùng transaction.
6. Nếu insert không thành công, đọc record hiện có; fingerprint khác thì trả conflict, fingerprint giống thì replay response đã lưu.

Unique constraint khiến transaction cạnh tranh cùng key phải chờ kết quả ghi của transaction đầu. Nếu transaction đầu rollback, request sau có thể giành quyền insert; nếu transaction đầu commit, request sau đọc được kết quả đã hoàn tất. Với PostgreSQL ở mức READ COMMITTED, câu SELECT tiếp theo sau khi INSERT conflict kết thúc sẽ thấy record đã commit. Ở isolation level khác hoặc database khác, snapshot/locking có thể khác; xử lý serialization failure và retry transaction theo đúng semantics database. Vì vậy cần integration test trên database thực tế của module.

## 13. Ví dụ xử lý command trong Spring transaction

Đoạn code sau minh họa orchestration; các repository method là abstraction cần triển khai bằng SQL phù hợp database:

~~~java
@Service
public class CreatePaymentService implements CreatePaymentUseCase {

    private final IdempotencyRepository idempotencyRepository;
    private final PaymentRepository paymentRepository;
    private final OutboxRepository outboxRepository;
    private final PaymentResponseCodec responseCodec;

    @Transactional
    @Override
    public CreatePaymentResponse create(
            CreatePaymentCommand command,
            IdempotencyScope scope) {
        String fingerprint = fingerprint(command);

        boolean claimed = idempotencyRepository.tryInsert(
                scope,
                command.idempotencyKey(),
                fingerprint);

        if (!claimed) {
            IdempotencyRecord existing = idempotencyRepository
                    .findRequired(scope, command.idempotencyKey());

            if (!existing.requestHash().equals(fingerprint)) {
                throw new IdempotencyKeyConflictException();
            }
            if (existing.isCompleted()) {
                return responseCodec.decode(existing.responsePayload());
            }

            throw new CommandStillInProgressException();
        }

        Payment payment = paymentRepository.create(command);
        outboxRepository.append(PaymentCreatedEvent.from(payment));

        CreatePaymentResponse response =
                CreatePaymentResponse.newBuilder()
                        .setPaymentId(payment.id())
                        .setState("CREATED")
                        .build();

        idempotencyRepository.complete(
                scope,
                command.idempotencyKey(),
                responseCodec.encode(response));

        return response;
    }
}
~~~

Trong ví dụ này, tryInsert phải là thao tác atomic dựa trên unique constraint, không phải SELECT rồi INSERT thông thường. complete cập nhật record trong cùng transaction với payment và outbox. Không gọi trực tiếp một hệ thống ngoài trong transaction rồi giả định database rollback sẽ hoàn tác được side effect bên ngoài.

Nếu command lỗi trước khi có side effect và transaction rollback, idempotency record cũng rollback; retry sau có thể thực hiện lại. Nếu API cần replay cả kết quả nghiệp vụ thất bại, phải định nghĩa rõ những status nào được lưu thành kết quả hoàn tất và triển khai policy tương ứng.

Idempotency ở đây bảo vệ side effect trong scope key, transaction và retention đã định nghĩa; nó không tạo ra bảo đảm exactly-once tổng quát giữa nhiều hệ thống độc lập. Transactional outbox thường giao event theo mô hình at-least-once, vì vậy consumer hoặc downstream command cũng cần deduplication/idempotency riêng.

## 14. Key conflict và status mapping

Khi cùng key được dùng với payload khác, server phải từ chối thay vì trả kết quả của command cũ cho một command mới. Có thể dùng ALREADY_EXISTS hoặc INVALID_ARGUMENT theo contract; chọn một status ổn định và mô tả rõ.

Ví dụ:

~~~java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

StatusRuntimeException toGrpcStatus(Throwable failure) {
    if (failure instanceof IdempotencyKeyConflictException) {
        return Status.ALREADY_EXISTS
                .withDescription(
                        "Idempotency key was already used for another command")
                .asRuntimeException();
    }
    if (failure instanceof CommandStillInProgressException) {
        return Status.ABORTED
                .withDescription("Command is still being processed")
                .asRuntimeException();
    }
    return Status.INTERNAL
            .withDescription("Internal server error")
            .asRuntimeException();
}
~~~

ABORTED cho trạng thái đang xử lý chỉ phù hợp với mô hình đã commit record IN_PROGRESS riêng và client có policy retry/backoff, giữ nguyên key. Trong mô hình claim + mutation + response cùng một transaction, duplicate thường chờ transaction đầu giải quyết unique conflict rồi đọc kết quả COMPLETED; nhánh IN_PROGRESS không phải trạng thái đã commit nhìn thấy được trong cùng mô hình đó. Không retry ngay liên tục; dùng delay và deadline còn lại. Nếu hệ thống có thể chờ lấy kết quả trong thời gian ngắn, server có thể chờ record hoàn tất thay vì trả lỗi ngay.

## 15. Retry an toàn với streaming RPC

Retry unary command dễ xác định hơn vì request là một message hoàn chỉnh. Streaming có thêm trạng thái đã gửi/đã nhận:

- Client-streaming có thể đã gửi nhiều message và server đã xử lý một phần.
- Server-streaming có thể đã nhận một số response trước khi connection đứt.
- Bidirectional streaming có thể đã trao đổi message hai chiều.

Sau khi stream đã commit hoặc client đã nhận response, tự động chạy lại toàn bộ stream có thể phát lại side effect hoặc tạo response trùng. Với upload lớn hoặc event stream, nên thiết kế application-level resume:

- Mỗi chunk/message có operation key và sequence number.
- Server lưu checkpoint hoặc offset đã chấp nhận.
- Client reconnect với cùng stream/session ID và tiếp tục từ sequence chưa được xác nhận.
- Server từ chối sequence trùng có payload khác và replay acknowledgement cho sequence đã xử lý.

Không coi retry policy của channel là bảo đảm replay an toàn cho mọi streaming workflow. Với stream có side effect, idempotency phải được áp dụng ở từng command/message hoặc theo session.

## 16. Kết hợp retry budget, circuit breaker và load shedding

Retry policy nên nằm trong một chiến lược reliability rộng hơn:

- **Retry budget:** giới hạn tỷ lệ hoặc số lượng retry so với request gốc.
- **Circuit breaker:** tạm ngừng gửi tới dependency đang liên tục lỗi để tránh tiêu hao tài nguyên.
- **Load shedding:** từ chối sớm khi server quá tải thay vì nhận thêm request không thể xử lý.
- **Bulkhead:** giới hạn concurrency theo dependency để một hệ thống chậm không chiếm toàn bộ thread/connection.
- **Deadline propagation:** dừng công việc khi caller không còn chờ kết quả.

Không phải mọi lỗi RESOURCE_EXHAUSTED đều nên retry. Nếu server đang chủ động load shed, client nên backoff hoặc dừng theo policy, không lập tức gửi thêm traffic.

## 17. Kiểm thử retry và idempotency

Test cần chứng minh cả hành vi retry lẫn tính duy nhất của side effect:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Lần đầu UNAVAILABLE, lần sau OK | Client retry trong giới hạn và nhận kết quả |
| INVALID_ARGUMENT | Không retry |
| Hết maxAttempts | Dừng và trả lỗi cuối |
| Deadline hết trước attempt tiếp theo | Không gửi thêm attempt |
| Cùng key, cùng payload, gửi tuần tự | Response giống nhau, mutation chỉ một lần |
| Cùng key, cùng payload, gửi đồng thời | Unique constraint chỉ cho một transaction thực hiện |
| Cùng key, payload khác | Trả conflict status |
| Server commit nhưng response bị mất | Retry trả response đã lưu, không tạo mutation mới |
| Transaction đầu rollback | Request tiếp theo có thể giành key và thực hiện |
| Outbox event được giao lại | Consumer/downstream xử lý idempotent |

Đối với backoff, dùng clock/random/sleeper có thể điều khiển hoặc kiểm tra retry policy bằng test harness phù hợp. Tránh test phụ thuộc sleep thời gian dài. Với concurrent duplicate, dùng barrier/latch để khởi chạy hai request cùng lúc và kiểm tra số row/payment/outbox cuối cùng trong database.

### Ví dụ test tuần tự cùng idempotency key

~~~java
@Test
void repeatedCommandReturnsStoredResultWithoutSecondMutation() {
    CreatePaymentCommand command = validCommand("key-123");

    CreatePaymentResponse first = service.create(command, scope);
    CreatePaymentResponse second = service.create(command, scope);

    assertEquals(first, second);
    assertEquals(1, paymentRepository.countByIdempotencyKey("key-123"));
    assertEquals(1, outboxRepository.countByCommandKey("key-123"));
}
~~~

Đây là integration test với repository/database thật hoặc test database phù hợp; mock repository không chứng minh unique constraint và transaction isolation hoạt động.

Để mô phỏng response bị mất sau commit, gọi service lần đầu và xác nhận payment, outbox cùng idempotency record đã commit; sau đó bỏ kết quả phía client như thể connection bị đứt. Gửi lại cùng request/key và xác nhận response được đọc từ record đã lưu, số payment/outbox không tăng. Test này kiểm tra tình huống quan trọng nhất của retry command ghi dữ liệu.

## 18. Quan sát retry và deduplication

Metrics và trace nên giúp phân biệt logical call với từng attempt:

- Tổng số logical RPC calls.
- Số attempts trên mỗi logical call.
- Retry count theo service/method/status.
- Retry exhausted và deadline exceeded.
- Backoff duration và số call bị bỏ vì hết deadline.
- Idempotency replay count.
- Idempotency key conflict count.
- Command in-progress duration nếu có state đã commit.
- Deduplication store latency, conflict/lock wait và retention cleanup.

Không dùng idempotency key hoặc tenant/customer ID làm metric label vì cardinality cao và có thể lộ dữ liệu. Có thể ghi một identifier đã redact trong log/trace khi policy cho phép, nhưng không đưa raw key hoặc payload nhạy cảm vào telemetry.

Khi điều tra duplicate, so sánh trace ID và idempotency key đã được bảo vệ. Một logical operation có thể tạo nhiều client attempt; server có thể chỉ commit một command và các attempt sau replay cùng response.

## 19. Những sai lầm thường gặp

- Retry mọi status code, kể cả lỗi validation và authorization.
- Không đặt maxAttempts hoặc deadline tổng.
- Retry ngay không có backoff/jitter.
- Tạo idempotency key mới cho mỗi attempt.
- Chỉ kiểm tra key bằng SELECT rồi INSERT, không có unique constraint.
- Cùng key nhưng payload khác vẫn trả kết quả cũ.
- Lưu dedup record tách transaction khỏi business mutation, tạo cửa sổ inconsistency.
- Giả định database rollback hoàn tác side effect của HTTP/payment provider bên ngoài.
- Chồng retry ở gRPC, application và downstream client mà không tính tổng attempts.
- Tự động replay toàn bộ streaming call sau khi server đã xử lý một phần.
- Xóa idempotency record quá sớm trong khi client còn có thể retry.
- Dùng idempotency key như credential hoặc metric label.

## 20. Checklist thiết kế command có retry

Trước khi bật retry cho một RPC ghi dữ liệu, xác nhận:

1. Status retryable được định nghĩa rõ và chỉ phản ánh lỗi tạm thời.
2. Max attempts, backoff, jitter, retry budget và deadline đã có giới hạn.
3. Client tạo key một lần cho một logical command và giữ nguyên key qua retry.
4. Server scope key theo caller/tenant và operation.
5. Server so sánh fingerprint để phát hiện key reuse với payload khác.
6. Database unique constraint ngăn hai request cùng key cùng thực hiện side effect.
7. Mutation, dedup result và outbox được commit nhất quán.
8. Response đã hoàn tất được replay cho duplicate request.
9. Retention đủ dài và authorization được kiểm tra trước khi replay.
10. Streaming workflow có sequence/checkpoint hoặc policy resume riêng.
11. Test bao phủ transient failure, timeout sau commit, concurrent duplicate và payload conflict.
12. Metrics phân biệt logical calls, attempts và dedup replays.

## 21. Tự luyện tập

1. Vì sao DEADLINE_EXCEEDED có thể xảy ra sau khi server đã commit command?
2. Phân biệt retry policy và idempotency key.
3. Vì sao cùng một key phải được giữ nguyên qua mọi attempt?
4. Làm thế nào unique constraint bảo vệ hai request đồng thời dùng cùng key?
5. Vì sao fingerprint chỉ nên gồm field nghiệp vụ đã canonicalize?
6. Khi nào dùng transactional outbox cho command có side effect bên ngoài?
7. Vì sao retry một streaming RPC sau khi đã nhận response có thể không an toàn?
8. Thiết kế test cho tình huống server commit nhưng response bị mất.

**Ghi nhớ:** Retry phải có status classification, max attempts, exponential backoff với jitter, retry budget và deadline chung. Với command có side effect, client tạo một idempotency key ổn định và server lưu fingerprint cùng kết quả dưới unique constraint; duplicate cùng payload được replay, còn cùng key với payload khác bị từ chối. Transaction/outbox và test concurrency bảo vệ side effect; streaming cần sequence/checkpoint hoặc resume protocol riêng.
