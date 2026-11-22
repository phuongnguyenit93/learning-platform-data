# Stub immutable và cấu hình deadline

Generated stub trong gRPC Java là đối tượng client đại diện cho một service và giữ tham chiếu tới Channel cùng CallOptions. Stub được thiết kế **immutable**: các phương thức cấu hình như withDeadlineAfter, withDeadline, withWaitForReady hoặc withCompression trả về một stub mới thay vì thay đổi đối tượng hiện tại.

Đặc tính này giúp ứng dụng Spring chia sẻ stub nền giữa nhiều request mà không làm cấu hình của request này ảnh hưởng request khác. Khi gọi RPC, hãy tạo một stub dẫn xuất với deadline phù hợp cho lần gọi đó. Đặc biệt, withDeadlineAfter() tính deadline tại thời điểm tạo stub dẫn xuất; nếu lưu stub đó lâu dài rồi dùng lại, deadline tuyệt đối bên trong sẽ tiếp tục trôi và cuối cùng hết hạn.

## 1. Generated stub chứa những gì?

Sau khi biên dịch file .proto, plugin sinh các lớp client theo service. Ví dụ với PaymentService, gRPC Java thường sinh:

- PaymentServiceBlockingStub: gọi đồng bộ, kết quả trả về trực tiếp hoặc ném StatusRuntimeException.
- PaymentServiceStub: gọi bất đồng bộ qua StreamObserver.
- PaymentServiceFutureStub: dùng ListenableFuture cho các method unary được hỗ trợ.

Khởi tạo stub từ channel:

~~~java
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("payment.internal", 9090)
    .useTransportSecurity()
    .build();

PaymentServiceGrpc.PaymentServiceBlockingStub paymentStub =
    PaymentServiceGrpc.newBlockingStub(channel);
~~~

Channel quản lý kết nối và transport. Stub là wrapper nhẹ cho service, channel và các tùy chọn gọi. Không tạo channel mới cho mỗi RPC; channel thường được tái sử dụng trong suốt vòng đời ứng dụng và được đóng khi Spring application context dừng.

## 2. Immutable nghĩa là cấu hình tạo ra stub mới

Mỗi lời gọi cấu hình trả về một đối tượng mới:

~~~java
var baseStub = PaymentServiceGrpc.newBlockingStub(channel);

var shortBudgetStub =
    baseStub.withDeadlineAfter(300, TimeUnit.MILLISECONDS);

var longerBudgetStub =
    baseStub.withDeadlineAfter(1500, TimeUnit.MILLISECONDS);
~~~

baseStub không bị thay đổi sau hai lệnh trên. shortBudgetStub và longerBudgetStub có CallOptions riêng nhưng vẫn sử dụng cùng channel.

Một lỗi phổ biến là gọi phương thức cấu hình nhưng bỏ qua giá trị trả về:

~~~java
baseStub.withDeadlineAfter(300, TimeUnit.MILLISECONDS);
PaymentResponse response = baseStub.getPayment(request);
~~~

Lệnh đầu chỉ tạo stub dẫn xuất rồi bỏ đi. RPC thực tế vẫn được gọi bằng baseStub, do đó deadline 300 ms không được áp dụng. Phải gọi RPC trên đối tượng được trả về:

~~~java
PaymentResponse response = baseStub
    .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
    .getPayment(request);
~~~

## 3. Chia sẻ stub nền trong ứng dụng Spring

Vì stub immutable, có thể tạo stub nền một lần và inject vào service client. Ví dụ khi ứng dụng tự quản lý channel:

~~~java
@Configuration
public class PaymentGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel paymentChannel() {
        return ManagedChannelBuilder
            .forAddress("payment.internal", 9090)
            .useTransportSecurity()
            .build();
    }

    @Bean
    PaymentServiceGrpc.PaymentServiceBlockingStub paymentStub(
            ManagedChannel paymentChannel) {
        return PaymentServiceGrpc.newBlockingStub(paymentChannel);
    }
}
~~~

Đây là ví dụ quản lý channel trực tiếp; nếu Spring gRPC starter đã tạo channel, hãy dùng channel do starter quản lý thay vì tạo channel trùng. Cấu hình endpoint, TLS, interceptor và lifecycle phải theo integration point của starter đang dùng.

Service sử dụng stub nền:

~~~java
@Service
public class PaymentGateway {

    private final PaymentServiceGrpc.PaymentServiceBlockingStub baseStub;

    public PaymentGateway(
            PaymentServiceGrpc.PaymentServiceBlockingStub baseStub) {
        this.baseStub = baseStub;
    }

    public PaymentResponse getPayment(PaymentRequest request) {
        return baseStub
            .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
            .getPayment(request);
    }
}
~~~

Mỗi lần gọi getPayment tạo một stub dẫn xuất mới với ngân sách 500 ms. Nhiều thread có thể đồng thời sử dụng baseStub; không cần lưu stub dẫn xuất vào field mutable dùng chung.

## 4. Deadline tương đối và vòng đời stub dẫn xuất

withDeadlineAfter(duration, unit) chuyển thời lượng tương đối thành một Deadline tại thời điểm phương thức được gọi. Deadline biểu diễn một mốc hết hạn theo clock đơn điệu của tiến trình, không phải bộ đếm bắt đầu lại mỗi khi RPC được gửi.

Không nên tạo stub có deadline tương đối trong constructor rồi dùng mãi:

~~~java
// Không nên: deadline bắt đầu trôi từ lúc bean được tạo.
private final PaymentServiceBlockingStub timedStub =
    baseStub.withDeadlineAfter(500, TimeUnit.MILLISECONDS);
~~~

Sau khi ứng dụng chạy hơn 500 ms, các RPC dùng timedStub có thể hết hạn ngay lập tức. Cách đúng là tạo stub dẫn xuất gần thời điểm bắt đầu từng logical RPC:

~~~java
public PaymentResponse getPayment(PaymentRequest request) {
    var callStub = baseStub.withDeadlineAfter(
        500, TimeUnit.MILLISECONDS);
    return callStub.getPayment(request);
}
~~~

Nếu cần chia sẻ cùng một mốc deadline cho nhiều lời gọi downstream thuộc một request cha, hãy dùng withDeadline(Deadline) với deadline đã capture từ context cha. Đây là trường hợp có chủ đích vì các lời gọi con phải cùng kết thúc theo ngân sách của request cha.

## 5. Bảo toàn deadline của request cha

Khi một service Spring gRPC gọi tiếp service khác, deadline của call con không được vượt deadline còn lại của call cha. Có thể lấy deadline từ Context.current() và chọn mốc sớm hơn giữa deadline cha và ngân sách riêng của downstream:

~~~java
private PaymentServiceBlockingStub stubForCurrentCall(
        Duration childBudget) {

    Deadline childDeadline = Deadline.after(
        childBudget.toNanos(), TimeUnit.NANOSECONDS);

    Deadline parentDeadline = Context.current().getDeadline();
    if (parentDeadline != null
            && parentDeadline.isBefore(childDeadline)) {
        childDeadline = parentDeadline;
    }

    return baseStub.withDeadline(childDeadline);
}
~~~

Ví dụ helper giả định childBudget đã được validate là dương. Nếu parent deadline đã hết, call con sẽ hết hạn ngay; không tạo ngân sách mới để kéo dài request cha. Nếu cần chừa thời gian cho service cha xử lý response, hãy trừ phần dự phòng khỏi child budget trước khi tạo deadline.

gRPC Java cũng dùng context hiện hành khi tạo client call. Tuy nhiên, khi offload công việc sang executor khác, cần truyền context bằng Context.wrap(...) hoặc executor gắn context; nếu không, task có thể không còn thấy deadline/cancellation của request cha.

## 6. Chọn deadline theo loại method

Không nên gắn một timeout dài cho toàn bộ service chỉ vì một method chậm. Có thể tạo helper hoặc wrapper theo ngân sách nghiệp vụ:

| Method | Ví dụ ngân sách | Lý do |
| --- | ---: | --- |
| GetPayment | 300–500 ms | Truy vấn đọc nhanh |
| CreatePayment | 1–2 s | Cần validate, ghi transaction và trả kết quả |
| GenerateStatement | 5–15 s | Xử lý báo cáo có giới hạn |
| WatchPaymentEvents | Theo session policy | Stream dài cần session lifetime, idle timeout và reconnect |

Các con số chỉ minh họa. Chọn theo SLA, latency p95/p99, kích thước dữ liệu và ngân sách caller. Với stream dài hạn, không giữ một stub dẫn xuất có deadline vô hạn; dùng policy phiên rõ ràng và tạo call theo thời gian sống đã xác định.

## 7. Áp dụng deadline cho blocking, async và future stub

Các loại generated stub đều có API cấu hình CallOptions. Blocking stub:

~~~java
PaymentResponse response = blockingStub
    .withDeadlineAfter(400, TimeUnit.MILLISECONDS)
    .getPayment(request);
~~~

Async stub:

~~~java
asyncStub.withDeadlineAfter(400, TimeUnit.MILLISECONDS)
    .getPayment(request, new StreamObserver<PaymentResponse>() {
        @Override
        public void onNext(PaymentResponse response) {
            handleResponse(response);
        }

        @Override
        public void onError(Throwable error) {
            Status status = Status.fromThrowable(error);
            handleFailure(status);
        }

        @Override
        public void onCompleted() {
            finishCall();
        }
    });
~~~

Future stub cho unary method:

~~~java
ListenableFuture<PaymentResponse> result =
    futureStub.withDeadlineAfter(400, TimeUnit.MILLISECONDS)
        .getPayment(request);
~~~

Với blocking stub, timeout thường được quan sát qua StatusRuntimeException. Với async stub, lỗi được chuyển qua onError; với future stub, future hoàn tất exceptional. Cần xử lý DEADLINE_EXCEEDED theo đúng kiểu API và tránh chặn thread callback để chờ kết quả.

## 8. Immutable stub và thread safety

Generated stub của gRPC Java kế thừa mô hình immutable của AbstractStub. Có thể chia sẻ stub nền giữa nhiều request và tạo các bản dẫn xuất độc lập trên từng thread. CallOptions cũng immutable; thao tác cấu hình trả về bản CallOptions mới.

Tuy nhiên:

- Không đặt thông tin request hoặc mutable state vào field dùng chung của wrapper quanh stub.
- Không lưu deadline tương đối đã tạo từ lúc startup để dùng cho các request sau.
- Không đóng channel khi một request kết thúc; channel có thể đang phục vụ nhiều call.
- Không tạo channel mới cho mỗi stub dẫn xuất; withDeadlineAfter chỉ tạo wrapper mới, không cần tạo transport mới.
- Đóng channel theo lifecycle của ứng dụng sau khi ngừng nhận call mới.

## 9. Deadline và retry dùng cùng một mốc hết hạn

Khi gRPC retry policy tạo nhiều attempt cho một logical call, các attempt vẫn chịu deadline của call đó. Nếu tự retry ở tầng ứng dụng, giữ cùng một Deadline cho mọi attempt và backoff:

~~~java
Deadline overall = Deadline.after(1200, TimeUnit.MILLISECONDS);

for (int attempt = 1; attempt <= 3; attempt++) {
    if (overall.isExpired()) {
        throw Status.DEADLINE_EXCEEDED
            .withDescription("overall budget exhausted")
            .asRuntimeException();
    }

    try {
        return baseStub.withDeadline(overall)
            .getPayment(request);
    } catch (StatusRuntimeException ex) {
        if (ex.getStatus().getCode() != Status.Code.UNAVAILABLE
                || attempt == 3) {
            throw ex;
        }
        // Backoff phải nằm trong thời gian còn lại của overall.
    }
}
throw Status.UNAVAILABLE.asRuntimeException();
~~~

Không gọi withDeadlineAfter(1200, MILLISECONDS) ở đầu mỗi attempt. Làm như vậy sẽ cấp lại toàn bộ thời gian và khiến tổng thời gian retry vượt SLA của caller. Với command có side effect, cần idempotency key vì deadline hết không chứng minh server chưa commit.

## 10. Kiểm thử tính immutable và deadline

Có thể kiểm tra các hành vi quan trọng bằng gRPC in-process server:

1. Tạo stub nền không có deadline riêng.
2. Gọi một method chậm qua stub dẫn xuất với deadline ngắn và xác minh DEADLINE_EXCEEDED.
3. Gọi method nhanh tiếp theo qua stub nền và xác minh vẫn thành công.
4. Tạo hai stub dẫn xuất với ngân sách khác nhau; xác minh một call không làm thay đổi call còn lại.
5. Tạo stub có deadline tương đối rồi chờ quá thời lượng đó trước khi gọi; xác minh deadline đã hết, qua đó tránh lưu stub timed trong field dài hạn.
6. Trong nested call, xác minh deadline con không vượt deadline cha.

Dùng latch để điều khiển server chậm thay vì Thread.sleep dài. Test nên xác minh status, thứ tự sự kiện và cleanup, không assert thời gian timeout chính xác tới từng mili giây.

## 11. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi withDeadlineAfter nhưng bỏ qua stub trả về | RPC không dùng deadline mới | Gọi method trên stub dẫn xuất |
| Cache stub dẫn xuất có deadline tương đối từ startup | Các call sau có thể hết hạn ngay | Tạo stub dẫn xuất mới cho từng logical RPC |
| Tạo lại channel mỗi lần gọi | Tốn kết nối, thread và tài nguyên transport | Reuse channel do Spring quản lý |
| Cấp deadline mới cho từng retry | Tổng thời gian vượt ngân sách caller | Giữ một Deadline chung cho logical RPC |
| Deadline con dài hơn deadline cha | Downstream có thể chạy sau khi caller đã hết hạn | Chọn deadline sớm hơn giữa parent và child budget |
| Dùng một timeout cho mọi method | Method nhanh chờ quá lâu hoặc method dài timeout giả | Đặt ngân sách theo method/SLA |

## 12. Ghi nhớ và tự kiểm tra

**Generated stub là immutable và có thể chia sẻ an toàn; cấu hình deadline tạo ra một stub dẫn xuất mới.** withDeadlineAfter() tính mốc hết hạn ngay khi được gọi, nên hãy tạo stub có deadline tương đối gần thời điểm bắt đầu RPC. Giữ channel dùng chung, bảo toàn deadline cha cho nested call và dùng cùng một deadline cho toàn bộ retry.

Tự kiểm tra:

1. Vì sao withDeadlineAfter() không thay đổi stub nền?
2. Điều gì xảy ra nếu cache stub đã gọi withDeadlineAfter() trong một Spring singleton?
3. Khi nào nên dùng withDeadline(Deadline) thay vì withDeadlineAfter(...)?
4. Vì sao có thể chia sẻ generated stub giữa nhiều thread nhưng không nên chia sẻ mutable request state?
5. Làm thế nào để deadline của downstream và các lần retry không vượt deadline caller?

Hiểu đúng tính immutable và vòng đời deadline giúp client Spring gRPC tái sử dụng channel/stub hiệu quả, áp ngân sách theo từng RPC và tránh timeout sai do dùng lại stub dẫn xuất đã hết hạn.
