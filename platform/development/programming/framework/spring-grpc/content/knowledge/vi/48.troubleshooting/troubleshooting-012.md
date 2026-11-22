# Server shutdown làm RPC lỗi

Trong dịch vụ `SPRING_GRPC`, server nhận các lời gọi RPC theo hợp đồng Protocol Buffers đã sinh mã Java. Một lời gọi có thể là unary, server streaming, client streaming hoặc bidirectional streaming. Vì vậy, khi ứng dụng Spring dừng để triển khai phiên bản mới, scale pod hoặc tắt tiến trình, việc đóng gRPC server ảnh hưởng trực tiếp đến những RPC đang chạy và những RPC mới được gửi đến.

Lỗi xuất hiện đúng lúc shutdown không nhất thiết có nghĩa là logic nghiệp vụ sai. Thường nguyên nhân nằm ở thời điểm server ngừng nhận request, thời gian drain không đủ, stream kéo dài, thứ tự đóng các bean hoặc cách client xử lý kết nối bị ngắt. Cần phân biệt shutdown có kiểm soát với việc tiến trình bị kết thúc đột ngột, sau đó đối chiếu log hai phía để tìm đúng điểm đứt.

## 1. Điều gì xảy ra khi Spring gRPC server shutdown?

Trong ứng dụng Spring, gRPC server thường được tạo và quản lý trong vòng đời của application context hoặc bởi thành phần lifecycle do starter cung cấp. Khi Spring nhận yêu cầu đóng context, thành phần quản lý server sẽ dừng server theo chính sách của nó. Yêu cầu dừng có thể bắt nguồn từ:

- Người vận hành dừng ứng dụng hoặc container.
- Kubernetes thay pod trong rolling update, scale down hoặc reschedule.
- Tiến trình nhận tín hiệu `SIGTERM`.
- Ứng dụng đóng `ApplicationContext` trong kiểm thử hoặc khi khởi động thất bại.
- Một thành phần quản lý server được gọi dừng trực tiếp.

Một quy trình dừng an toàn thường có các bước: ngừng đưa traffic mới vào instance, bắt đầu shutdown gRPC server, chờ các RPC đang xử lý hoàn tất, đóng những tài nguyên mà handler sử dụng, rồi mới kết thúc tiến trình. Nếu bỏ qua một bước hoặc giới hạn thời gian quá ngắn, client có thể thấy lỗi dù handler và dữ liệu nghiệp vụ vốn hoạt động bình thường.

### 1.1. Graceful shutdown và forceful shutdown

API `io.grpc.Server` của grpc-java phân biệt hai cách dừng:

| API | Hành vi | Ảnh hưởng thường gặp |
|---|---|---|
| `server.shutdown()` | Bắt đầu dừng có trật tự. Server ngừng nhận RPC mới; các RPC đã được nhận có cơ hội hoàn tất. | RPC ngắn thường hoàn tất nếu còn đủ thời gian drain. RPC mới hoặc RPC đến đúng lúc chuyển trạng thái có thể không được xử lý tại instance này. |
| `server.shutdownNow()` | Yêu cầu dừng ngay và hủy các RPC đang hoạt động. | RPC đang chạy có thể bị cancel hoặc mất kết nối; client thường nhận status liên quan đến transport hoặc cancellation. |
| `server.awaitTermination(...)` | Chờ server kết thúc trong thời hạn được chỉ định. | Đây là thao tác chờ, không tự tạo ra chính sách graceful shutdown. |

`shutdown()` không có nghĩa mọi RPC đều chắc chắn thành công. Một RPC có thể đã hết deadline, bị client hủy, hoặc chưa được server nhận trước khi server ngừng nhận request mới. Nếu hết thời gian chờ mà server chưa kết thúc, tầng quản lý có thể chuyển sang `shutdownNow()` hoặc hệ điều hành/container có thể cưỡng bức kết thúc tiến trình.

### 1.2. Unary và streaming có đặc điểm drain khác nhau

- **Unary RPC** thường có thời gian xử lý ngắn và một response. Nếu server còn đủ thời gian drain, request đang xử lý có thể trả response bình thường.
- **Server streaming** có thể tiếp tục gửi nhiều message sau khi request ban đầu đã được nhận. Server cần thời gian để hoàn tất stream hoặc gửi trạng thái kết thúc.
- **Client streaming** và **bidirectional streaming** có thể mở trong thời gian dài. Chúng có thể chờ message tiếp theo từ client hoặc duy trì một phiên trao đổi liên tục.

Vì thế, một thời hạn drain phù hợp với unary RPC chưa chắc phù hợp với streaming RPC. Với stream dài hạn, cần định nghĩa thời lượng phiên tối đa, cơ chế báo ngừng nhận phiên mới và cách client kết nối lại.

## 2. Vì sao RPC lỗi trong lúc shutdown?

### 2.1. Tiến trình bị kết thúc trước khi RPC hoàn tất

Container hoặc hệ điều hành gửi `SIGTERM`, ứng dụng bắt đầu đóng context nhưng thời gian chờ kết thúc quá sớm. Khi hết grace period, runtime có thể gửi tín hiệu kết thúc cưỡng bức. RPC đang chạy mất tiến trình phục vụ trước khi gửi response.

Trường hợp này thường xuất hiện trong lúc deploy hoặc scale pod. Nếu log cho thấy shutdown bắt đầu ngay trước khi transport đóng, hãy kiểm tra thời gian drain thực tế và thời gian grace period của môi trường chạy.

### 2.2. Server bị dừng cưỡng bức

Ứng dụng gọi `shutdownNow()` ngay khi nhận tín hiệu dừng, hoặc một đoạn mã cleanup tự hủy server trước khi các RPC đang chạy hoàn tất. Việc này phù hợp khi cần dừng khẩn cấp, nhưng không phải lựa chọn mặc định cho rolling deployment.

### 2.3. Traffic vẫn được gửi đến instance đang rời khỏi cụm

Load balancer, service discovery hoặc Kubernetes endpoint chưa kịp cập nhật trạng thái của instance. Trong khoảng chuyển tiếp, client vẫn chọn instance sắp shutdown. RPC mới có thể gặp lỗi kết nối hoặc `UNAVAILABLE`.

Việc đánh dấu readiness không sẵn sàng cần diễn ra đủ sớm để trạng thái được truyền đến nơi phân phối traffic. Chỉ thay đổi readiness tại đúng thời điểm tiến trình đã đóng listener có thể không tạo đủ khoảng đệm.

### 2.4. Streaming RPC không kết thúc trong thời gian drain

Một stream có thể chờ vô hạn nếu giao thức ứng dụng không quy định thời lượng phiên hoặc client không đóng luồng gửi. Khi server shutdown, stream vẫn còn hoạt động đến hết grace period; sau đó nó bị hủy hoặc mất transport.

Với stream dài hạn, cần có quy ước ở tầng ứng dụng, chẳng hạn thông báo server đang bảo trì, ngừng tạo stream mới, cho client một khoảng thời gian chuyển sang kết nối mới và đóng stream cũ có kiểm soát.

### 2.5. Các bean phụ thuộc bị đóng quá sớm

Handler có thể sử dụng database, executor, cache, tracing exporter hoặc client gọi sang dịch vụ khác. Nếu các tài nguyên này bị đóng trước khi gRPC server drain xong, RPC vẫn còn chạy nhưng không còn dependency để hoàn thành. Kết quả có thể là exception trong handler, response `INTERNAL` hoặc lỗi khác tùy cách exception được ánh xạ sang gRPC status.

Trong Spring, hãy kiểm tra thứ tự dừng của các thành phần lifecycle. Server cần ngừng nhận RPC và drain trước khi những tài nguyên mà handler cần bị hủy. Nếu starter đang quản lý gRPC server, nên sử dụng cơ chế lifecycle và cấu hình shutdown được hỗ trợ bởi đúng phiên bản starter.

### 2.6. Client đóng channel hoặc xử lý retry không phù hợp

Lỗi có thể bắt nguồn từ phía client: ứng dụng client đóng `ManagedChannel` trong khi request còn chạy, tái sử dụng channel đã shutdown, hoặc retry một RPC không an toàn. Một channel nên được tái sử dụng trong vòng đời ứng dụng và được đóng sau khi client đã ngừng phát request mới, chờ các call cần thiết hoàn tất.

Retry cũng không bảo đảm thành công. Nếu server đã thực hiện nghiệp vụ nhưng response bị mất khi shutdown, client không thể chỉ dựa vào lỗi transport để biết thao tác đã được commit hay chưa. Với thao tác ghi dữ liệu, cần thiết kế tính idempotent hoặc dùng khóa idempotency để tránh thực hiện nghiệp vụ hai lần.

## 3. Đọc gRPC status để khoanh vùng nguyên nhân

Các status sau thường xuất hiện khi kết nối bị ảnh hưởng bởi shutdown:

| Status | Ý nghĩa có thể gặp trong tình huống shutdown | Hướng kiểm tra |
|---|---|---|
| `UNAVAILABLE` | Không thể sử dụng server hoặc transport tại thời điểm gọi; instance có thể đang dừng hoặc kết nối bị đóng. | Kiểm tra log server, sự kiện deploy, load balancer, endpoint và chính sách retry. |
| `CANCELLED` | RPC bị hủy bởi client, server hoặc tầng transport. | Xác định bên nào yêu cầu cancel và thời điểm cancel so với shutdown. |
| `DEADLINE_EXCEEDED` | Deadline của RPC hết trước khi có kết quả. | So sánh thời gian xử lý, thời gian drain và deadline client. |
| `INTERNAL` | Handler hoặc tầng xử lý gặp lỗi nội bộ; có thể do dependency bị đóng trong lúc RPC còn chạy. | Đọc exception phía server và thứ tự đóng tài nguyên. |
| `UNKNOWN` | Lỗi không được ánh xạ thành status cụ thể hoặc transport cung cấp thông tin không đầy đủ. | Ghép log client/server theo thời gian, method và request ID. |

Không thể kết luận nguyên nhân chỉ từ một status. Cùng một lần shutdown, client khác nhau hoặc thời điểm gọi khác nhau có thể quan sát status khác nhau. Hãy dùng status làm tín hiệu để bắt đầu điều tra, sau đó xác nhận bằng log và sự kiện vòng đời.

Ví dụ ghi nhận status ở client:

```java
try {
    GetOrderResponse response = blockingStub
            .withDeadlineAfter(3, TimeUnit.SECONDS)
            .getOrder(request);
    return response;
} catch (StatusRuntimeException ex) {
    Status status = ex.getStatus();
    log.warn("gRPC call failed: method={}, code={}, description={}",
            "GetOrder", status.getCode(), status.getDescription());
    throw ex;
}
```

Deadline trong ví dụ là giá trị minh họa. Chọn deadline dựa trên SLA và thời gian xử lý thực tế của method. Không ghi dữ liệu nhạy cảm trong request hoặc metadata vào log chỉ để phục vụ điều tra.

## 4. Quy trình chẩn đoán

### Bước 1: Xác định lỗi chỉ xảy ra khi instance dừng hay xảy ra cả lúc bình thường

Đối chiếu thời điểm lỗi với các sự kiện như rolling update, scale down, restart, đóng Spring context hoặc thao tác shutdown thủ công. Nếu lỗi tập trung quanh thời điểm một pod rời cụm, ưu tiên kiểm tra lifecycle và routing. Nếu lỗi xuất hiện liên tục khi instance vẫn khỏe, mở rộng điều tra sang network, TLS, cấu hình channel và handler.

### Bước 2: Ghép timeline giữa client và server

Thu thập tối thiểu các mốc sau:

1. Client bắt đầu RPC, kèm method, deadline và request/correlation ID.
2. Server nhận RPC và bắt đầu xử lý.
3. Tiến trình nhận tín hiệu dừng hoặc Spring bắt đầu đóng context.
4. gRPC server bắt đầu shutdown.
5. Handler hoàn tất, bị cancel hoặc ném exception.
6. Transport đóng và tiến trình kết thúc.

Nếu server không ghi nhận RPC nhưng client có log gửi request, kiểm tra routing và kết nối. Nếu server đã nhận request nhưng không ghi nhận handler hoàn tất trước khi tiến trình kết thúc, kiểm tra thời gian drain và dependency.

### Bước 3: Kiểm tra số RPC đang hoạt động và các stream dài

Theo dõi số RPC đang xử lý, thời lượng theo method, số stream mở, số lần cancel và số lỗi theo gRPC status. Dùng interceptor hoặc instrumentation hiện có để ghi method, thời điểm bắt đầu/kết thúc và trạng thái cuối. Tránh ghi toàn bộ payload vì có thể chứa dữ liệu nhạy cảm và làm tăng chi phí logging.

Nếu số RPC đang hoạt động không giảm trong thời gian shutdown, tìm method hoặc stream giữ tài nguyên lâu. Kiểm tra xem handler có chờ message tiếp theo, chờ I/O không giới hạn, giữ lock hoặc chặn executor hay không.

### Bước 4: Kiểm tra deadline và cancellation

Mỗi RPC cần deadline phù hợp. Khi deadline hết, client có thể hủy RPC và server nhận tín hiệu cancellation. Handler nên dừng công việc nền khi RPC đã bị hủy, đặc biệt với streaming RPC hoặc tác vụ có chi phí cao.

Deadline quá ngắn khiến request hợp lệ bị lỗi trong lúc hệ thống đang bận drain. Deadline quá dài có thể giữ tài nguyên đến sau thời gian shutdown. Hãy đặt deadline theo SLA, giới hạn thời gian xử lý ở server và khả năng retry của nghiệp vụ.

### Bước 5: Kiểm tra thứ tự đóng tài nguyên

Đọc log lifecycle để xác định thời điểm gRPC server dừng so với database pool, executor, cache, tracing và các client phụ thuộc. Nếu dependency đóng trước khi handler hoàn tất, điều chỉnh lifecycle phase hoặc cơ chế phối hợp shutdown để server drain trước.

### Bước 6: Kiểm tra môi trường triển khai

Với container orchestrator, đối chiếu thời gian readiness propagation, thời gian `preStop` nếu có, `terminationGracePeriodSeconds` và thời gian ứng dụng thực sự cần để drain. Tổng thời gian cho drain và cleanup phải nằm trong grace period của môi trường. Nếu grace period kết thúc trước, runtime vẫn có thể kết thúc tiến trình đang xử lý RPC.

## 5. Triển khai graceful shutdown

### 5.1. Để một thành phần sở hữu vòng đời gRPC server

Trong ứng dụng Spring dùng starter quản lý gRPC server, hãy để thành phần lifecycle của starter chịu trách nhiệm start/stop server. Kiểm tra tài liệu của đúng phiên bản dependency để biết cách cấu hình thời gian chờ và hành vi khi hết thời gian. Không tạo thêm một shutdown hook độc lập cùng dừng server nếu starter đã sở hữu lifecycle; hai cơ chế dừng cạnh tranh có thể khiến thứ tự cleanup khó dự đoán.

Cấu hình graceful shutdown của embedded HTTP server trong Spring Boot không tự động chứng minh rằng gRPC server cũng được drain. Cần xác nhận gRPC server có tích hợp với lifecycle đó trong phiên bản đang dùng và kiểm tra hành vi thực tế bằng integration test.

Nếu ứng dụng tự tạo và sở hữu `io.grpc.Server`, có thể triển khai trình tự dừng cơ bản như sau:

```java
import io.grpc.Server;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class GrpcShutdown {

    private GrpcShutdown() {
    }

    public static void stop(Server server, Duration gracePeriod) {
        server.shutdown();

        try {
            boolean terminated = server.awaitTermination(
                    gracePeriod.toMillis(), TimeUnit.MILLISECONDS);

            if (!terminated) {
                server.shutdownNow();
                if (!server.awaitTermination(5, TimeUnit.SECONDS)) {
                    // Ghi log: server chưa kết thúc sau cả giai đoạn cưỡng bức.
                }
            }
        } catch (InterruptedException ex) {
            server.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Đoạn mã này minh họa thứ tự API của grpc-java, không phải bean cấu hình dùng chung cho mọi Spring gRPC starter. Trong ứng dụng thực tế, gọi nó từ đúng điểm lifecycle của thành phần sở hữu server. Không gọi đồng thời từ nhiều hook. Khi thread bị interrupt, đoạn mã yêu cầu dừng ngay và khôi phục interrupt flag để tầng gọi có thể xử lý trạng thái interrupt.

Thời hạn chờ cần được chọn theo SLA của RPC, thời lượng stream tối đa và grace period của nền tảng. Nếu server chưa kết thúc sau `shutdownNow()`, cần ghi nhận sự kiện để điều tra handler hoặc transport còn giữ tài nguyên.

### 5.2. Phối hợp với readiness và load balancer

Khi bắt đầu drain, instance cần được đánh dấu không còn nhận traffic mới. Sau đó chừa đủ thời gian để trạng thái readiness lan tới service discovery hoặc load balancer trước khi đóng server. Cách thực hiện phụ thuộc nền tảng triển khai và cơ chế health check của hệ thống.

Với Kubernetes, `terminationGracePeriodSeconds` đặt giới hạn thời gian tổng thể trước khi container bị kết thúc cưỡng bức. Giá trị cần bao gồm thời gian chạy `preStop` nếu có, thời gian cập nhật routing, thời gian drain RPC và cleanup cuối cùng. Ví dụ dưới đây chỉ minh họa việc dành một khoảng grace period; ứng dụng vẫn phải tự phối hợp readiness và gRPC lifecycle:

```yaml
spec:
  terminationGracePeriodSeconds: 60
```

Không chọn một con số chỉ dựa trên thời gian trung bình của unary RPC. Hãy đo thời gian RPC dài, đặc biệt là streaming, rồi xác định giới hạn hợp lý. Nếu stream có thể sống lâu hơn grace period, cần thiết kế giao thức reconnect hoặc giới hạn tuổi stream.

### 5.3. Giữ dependency sống đến khi server drain xong

Trong thời gian RPC đang chạy, handler có thể vẫn cần truy cập database, executor, cache hoặc dịch vụ khác. Thứ tự shutdown nên bảo đảm:

1. Ngừng nhận request mới và bắt đầu drain gRPC server.
2. Chờ các handler và stream đang hoạt động hoàn tất trong thời hạn cho phép.
3. Đóng executor và các dependency mà handler sử dụng.
4. Hoàn tất cleanup của ứng dụng và kết thúc tiến trình.

Nếu dùng Spring lifecycle, xem xét phase và quan hệ phụ thuộc của bean. Server cần được dừng trước các tài nguyên mà handler phụ thuộc. Không để một handler bị mắc kẹt vô hạn trong lúc cleanup; mọi thao tác I/O và lời gọi downstream cũng cần timeout.

## 6. Thiết kế client và RPC để chịu được shutdown

### 6.1. Đặt deadline cho từng RPC

Client nên đặt deadline theo đặc tính của từng method. Deadline giúp request không chờ vô hạn khi server rời cụm hoặc network mất kết nối. Với chuỗi lời gọi nhiều dịch vụ, cần truyền ngân sách thời gian còn lại thay vì cấp một deadline mới quá dài ở mỗi hop.

### 6.2. Retry có điều kiện

Chỉ retry các lỗi có khả năng phục hồi, thường gồm một số trường hợp `UNAVAILABLE`, và chỉ khi chính sách retry của client cho phép. Dùng exponential backoff có giới hạn và jitter để tránh nhiều client đồng loạt dồn request vào instance còn lại.

Trước khi retry, đánh giá tính idempotent của method:

- RPC đọc dữ liệu thường dễ retry hơn, nhưng vẫn cần cân nhắc tính nhất quán và deadline.
- RPC ghi hoặc tạo giao dịch có thể đã được server thực hiện trước khi response bị mất. Retry mù có thể tạo dữ liệu trùng hoặc thực hiện nghiệp vụ hai lần.
- Với thao tác ghi, dùng idempotency key hoặc mã yêu cầu duy nhất được server lưu và kiểm tra trong cùng ranh giới transaction.

Không retry vô hạn, không retry mọi status và không vượt quá deadline tổng thể của request. Một retry thành công về transport không đồng nghĩa nghiệp vụ đã được thực hiện đúng một lần.

### 6.3. Quản lý vòng đời ManagedChannel ở client

Client nên dùng channel có vòng đời dài, chia sẻ cho các stub tương ứng, thay vì tạo channel cho mỗi RPC. Khi client shutdown, trước tiên ngừng nhận công việc mới, chờ các call quan trọng hoàn tất, sau đó mới gọi `ManagedChannel.shutdown()` và chờ channel kết thúc. Chỉ dùng `shutdownNow()` khi cần hủy các call còn lại sau thời hạn đã định.

### 6.4. Thiết kế streaming RPC có khả năng reconnect

Với stream dài hạn:

- Định nghĩa message hoặc status ở tầng ứng dụng để client biết server đang drain.
- Dùng sequence number, cursor hoặc offset để client tiếp tục từ vị trí đã xử lý khi kết nối lại.
- Đặt giới hạn tuổi stream và có cơ chế client mở stream mới trước khi stream cũ kết thúc.
- Xử lý cancellation để giải phóng subscription, queue, executor task và tài nguyên liên quan.
- Không giả định một stream sẽ sống xuyên qua lần deploy hoặc shutdown của server.

Nếu dùng `ServerCallStreamObserver`, handler có thể đăng ký callback cancellation để dừng công việc nền khi RPC bị hủy. Callback cần an toàn khi chạy đồng thời với logic gửi message và không được gửi thêm response sau khi stream đã kết thúc.

## 7. Kiểm thử shutdown và drain

Một integration test nên dùng server thật trên cổng động và client thật, thay vì chỉ mock stub. Thiết kế kiểm thử bằng latch hoặc barrier để kiểm soát thời điểm handler đang chạy; tránh dựa vào `Thread.sleep()` vì timing của máy kiểm thử không ổn định.

Các tình huống nên bao phủ:

| Tình huống | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Unary RPC đang xử lý khi gọi `shutdown()` | Giữ handler bằng latch, bắt đầu shutdown, sau đó cho handler hoàn tất. | RPC đã được nhận hoàn tất nếu nằm trong grace period. |
| RPC mới gửi sau khi shutdown bắt đầu | Bắt đầu shutdown rồi thử gửi một RPC mới tới server đó. | Server không nhận RPC mới; client xử lý lỗi hoặc chuyển sang instance khác theo cấu hình. |
| RPC đang chạy khi gọi `shutdownNow()` | Giữ handler đang chạy rồi yêu cầu shutdown cưỡng bức. | Call bị hủy hoặc transport bị đóng; tài nguyên handler được giải phóng. |
| Streaming RPC đang mở khi deploy | Duy trì stream, phát tín hiệu drain và quan sát client reconnect. | Client nhận biết phiên cũ kết thúc và tiếp tục từ checkpoint theo giao thức. |
| Spring `ApplicationContext` đóng | Khởi tạo context và gRPC server, gọi đóng context trong lúc có RPC. | Lifecycle dừng server theo chính sách đã cấu hình; dependency còn sống đến khi drain xong. |
| Grace period không đủ | Cố ý giữ handler lâu hơn thời gian drain. | Hệ thống chuyển sang nhánh timeout/forceful shutdown có log rõ ràng và không treo vô hạn. |

Ở môi trường triển khai, bổ sung kiểm thử rolling update hoặc scale down với traffic liên tục. Theo dõi tỷ lệ `UNAVAILABLE`, `CANCELLED`, `DEADLINE_EXCEEDED`, số RPC đang hoạt động và thời gian drain. Một lần deploy thành công không đủ chứng minh mọi loại RPC đều được bảo vệ; cần có cả unary và streaming trong bộ kiểm thử.

## 8. Checklist xử lý sự cố

Khi RPC lỗi đúng lúc server shutdown, kiểm tra theo thứ tự sau:

- [ ] Lỗi có trùng với `SIGTERM`, deploy, scale down hoặc đóng Spring context không?
- [ ] Log cho biết server bắt đầu graceful shutdown hay bị dừng cưỡng bức?
- [ ] Có bao nhiêu RPC và stream còn hoạt động khi shutdown bắt đầu?
- [ ] Thời gian drain thực tế có nằm trong grace period của container hoặc nền tảng không?
- [ ] Readiness và routing có ngừng gửi request mới đủ sớm không?
- [ ] Database, executor, cache và client downstream có bị đóng trước handler không?
- [ ] Client có deadline, retry có giới hạn và channel lifecycle đúng không?
- [ ] Các RPC ghi có idempotency để tránh xử lý lặp khi response bị mất không?
- [ ] Integration test đã bao phủ unary, streaming, graceful shutdown và forceful shutdown chưa?

Khi đã xác định nguyên nhân, hãy sửa tại đúng tầng: lifecycle nếu server dừng sai thứ tự, readiness/routing nếu traffic đến pod đang rời cụm, grace period nếu drain không đủ thời gian, hoặc hợp đồng RPC/client nếu stream và retry chưa có quy tắc phục hồi. Sau thay đổi, xác nhận bằng log hai phía và kiểm thử shutdown có kiểm soát để bảo đảm RPC được xử lý đúng trong suốt vòng đời của dịch vụ Spring gRPC.
