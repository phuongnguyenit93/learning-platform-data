# Không giới hạn stream hoặc buffer

Trong dịch vụ Spring gRPC, một RPC streaming có thể sống lâu và chuyển rất nhiều message trong cùng một lời gọi. Nếu ứng dụng nhận dữ liệu nhanh hơn khả năng xử lý, hoặc gửi dữ liệu nhanh hơn khả năng tiêu thụ của client, dữ liệu sẽ tích tụ trong bộ nhớ. Một hàng đợi không giới hạn, một danh sách giữ toàn bộ stream hoặc một luồng công việc không có backpressure có thể khiến heap tăng liên tục, tăng độ trễ, gây `OutOfMemoryError` và làm ảnh hưởng các RPC khác.

Đây là lỗi thiết kế thường gặp khi dùng `StreamObserver`: API cho phép gọi `onNext` nhiều lần, nhưng việc gọi được phương thức đó không có nghĩa receiver đã xử lý xong message trước. Cần giới hạn lượng công việc đang chờ, điều tiết tốc độ gửi/nhận và giải phóng tài nguyên khi stream kết thúc.

## Stream và buffer tích tụ ở đâu?

Một luồng dữ liệu gRPC có thể đi qua nhiều tầng: ứng dụng tạo message, hàng đợi trong service, bộ đệm của grpc-java, HTTP/2 flow control, socket và proxy; phía nhận lại có hàng đợi, bộ giải mã protobuf và công việc xử lý riêng. Flow control của HTTP/2 giúp điều tiết dữ liệu trên kết nối, nhưng không tự giới hạn các collection hoặc queue do ứng dụng tạo ra.

Các mẫu code sau dễ gây vấn đề:

```java
// Rủi ro: giữ toàn bộ dữ liệu của stream trong heap.
List<Record> allRecords = new ArrayList<>();

repository.streamAll().forEach(allRecords::add);
allRecords.forEach(record -> responseObserver.onNext(toProto(record)));
responseObserver.onCompleted();
```

```java
// Rủi ro: queue không có giới hạn khi producer nhanh hơn consumer.
BlockingQueue<Event> pending = new LinkedBlockingQueue<>();
```

Ở ví dụ đầu, bộ nhớ tăng theo tổng số record. Ở ví dụ sau, `LinkedBlockingQueue` mặc định có sức chứa rất lớn; nếu producer tiếp tục thêm trong khi consumer bị chậm, queue có thể chiếm hết heap. Một queue giới hạn theo số phần tử vẫn có thể tốn quá nhiều bộ nhớ nếu mỗi message có kích thước lớn hoặc thay đổi mạnh.

## Giới hạn cả số lượng lẫn dung lượng

Một thiết kế an toàn cần đặt giới hạn ở các cấp phù hợp với nghiệp vụ:

| Tài nguyên | Giới hạn cần cân nhắc | Mục đích |
|---|---|---|
| Một message protobuf | Kích thước tối đa theo byte | Ngăn một message đơn lẻ chiếm quá nhiều bộ nhớ |
| Queue của một stream | Số message và tổng byte đang chờ | Ngăn producer lấn át consumer |
| Một stream | Tổng byte, số message hoặc thời lượng | Ngăn stream kéo dài tích lũy tài nguyên vô hạn |
| Các stream của một client/tenant | Số stream đồng thời và quota | Ngăn một danh tính chiếm hết năng lực dịch vụ |
| Toàn service | Số RPC đồng thời, worker và queue toàn cục | Bảo vệ heap, thread và dependency dùng chung |

Đừng chỉ đặt `queueCapacity = 1000` rồi coi như đã an toàn. Nếu mỗi message có thể lớn vài megabyte, 1000 phần tử vẫn là một lượng bộ nhớ rất lớn. Khi có thể, hãy theo dõi cả số phần tử và tổng kích thước ước lượng theo byte. Ngân sách bộ nhớ cần tính đến protobuf object sau giải mã, bản sao dữ liệu trong quá trình xử lý, queue và số stream hoạt động cùng lúc.

Giới hạn message nhận vào, ví dụ `maxInboundMessageSize`, chỉ kiểm soát kích thước từng message ở receiver. Nó không thay thế giới hạn tổng dữ liệu của stream, giới hạn queue hoặc giới hạn số RPC đồng thời.

## Áp dụng backpressure cho dữ liệu gửi đi

Với server streaming hoặc bidirectional streaming, service không nên gọi `onNext` liên tục trong khi client chưa sẵn sàng nhận thêm dữ liệu. grpc-java cung cấp `ServerCallStreamObserver.isReady()` và `setOnReadyHandler()` để service điều tiết việc gửi. Khi `isReady()` là `false`, hãy dừng phát message và tiếp tục khi callback báo stream đã sẵn sàng.

Ví dụ sau minh họa cách phát một nguồn dữ liệu hữu hạn theo trạng thái sẵn sàng. `serialExecutor` là executor tuần tự của ứng dụng; iterator cần đọc dữ liệu theo từng phần, không nạp toàn bộ kết quả vào một list trước đó.

```java
ServerCallStreamObserver<RecordReply> out =
    (ServerCallStreamObserver<RecordReply>) responseObserver;

Iterator<Record> records = repository.streamFor(request).iterator();
AtomicBoolean terminated = new AtomicBoolean();

Runnable pump = () -> {
    if (terminated.get() || out.isCancelled()) {
        return;
    }

    while (out.isReady() && !out.isCancelled() && records.hasNext()) {
        out.onNext(toReply(records.next()));
    }

    if (!out.isCancelled() && !records.hasNext()
            && terminated.compareAndSet(false, true)) {
        closeUnderlyingResource(); // Đóng cursor khi đọc hết dữ liệu.
        out.onCompleted();
    }
};

out.setOnReadyHandler(() -> serialExecutor.execute(pump));
out.setOnCancelHandler(() -> {
    if (terminated.compareAndSet(false, true)) {
        closeUnderlyingResource(); // Đóng cursor hoặc hủy truy vấn đang chạy.
    }
});

// Chạy lần đầu vì stream có thể đã sẵn sàng trước khi đăng ký callback.
serialExecutor.execute(pump);
```

Đây là khung minh họa; trong code thực tế cần bảo đảm `pump` và mọi thao tác trên observer được tuần tự hóa, đóng iterator/cursor trong mọi nhánh kết thúc, và không gọi `onCompleted` sau khi stream đã bị hủy. Nếu nguồn dữ liệu là bất đồng bộ, cần phân biệt queue tạm thời rỗng với nguồn đã hoàn tất. Khi queue rỗng nhưng producer chưa xong, không được tự kết thúc RPC.

`isReady()` phản ánh khả năng gửi thêm dữ liệu ở thời điểm kiểm tra; nó không phải giấy phép để tạo trước một lượng message không giới hạn. Producer cũng cần bị chặn hoặc tạm dừng khi buffer đạt ngưỡng. Callback on-ready nên làm công việc ngắn và chuyển phần xử lý phù hợp sang executor tuần tự có giới hạn.

## Kiểm soát dữ liệu nhận vào

Với client-streaming hoặc bidirectional streaming, service cũng cần điều tiết tốc độ đọc và xử lý message. grpc-java hỗ trợ manual inbound flow control thông qua `disableAutoRequest()` và `request(n)` trên `ServerCallStreamObserver`. Ở phía client, `ClientResponseObserver.beforeStart` có thể cấu hình `ClientCallStreamObserver` để chỉ yêu cầu thêm response sau khi ứng dụng đã xử lý message trước đó.

Mẫu xử lý là chỉ cho phép một số lượng message đang được xử lý, sau đó yêu cầu thêm message khi có chỗ trống. Ví dụ, nếu ứng dụng chỉ có thể xử lý tuần tự, có thể bắt đầu với một message đang được yêu cầu và gọi `request(1)` sau khi xử lý xong message hiện tại. Với xử lý song song, số lượng demand phải tương ứng với số slot xử lý có giới hạn.

Không chuyển message nhận được sang một executor có queue không giới hạn rồi lập tức yêu cầu thêm message. Cách đó chỉ chuyển điểm tích tụ từ gRPC sang executor. Nếu cần offload xử lý, dùng worker pool có hàng đợi hữu hạn; khi hết chỗ, tạm dừng demand hoặc từ chối stream theo hợp đồng API.

## Dùng queue có giới hạn và chính sách quá tải rõ ràng

Khi cần tách producer và consumer, hãy chọn queue có dung lượng hữu hạn. Ví dụ:

```java
BlockingQueue<Event> pending = new ArrayBlockingQueue<>(128);

boolean accepted = pending.offer(event);
if (!accepted) {
    // Không tiếp tục nhận vô hạn khi consumer đã tụt lại.
    // Áp dụng chính sách quá tải đã định nghĩa cho RPC này.
}
```

`offer` cho phép ứng dụng phát hiện queue đã đầy mà không chờ vô hạn. Tùy nghiệp vụ, chính sách khi đầy có thể là:

- Tạm dừng yêu cầu message tiếp theo bằng inbound flow control để consumer có thời gian xử lý.
- Từ chối RPC mới khi đạt giới hạn concurrency hoặc quota.
- Hủy stream hiện tại với trạng thái và thông báo phù hợp nếu không thể tiếp tục an toàn.
- Ghi dữ liệu vào kho bền vững có quota và chính sách dọn dẹp khi nghiệp vụ yêu cầu xử lý lâu dài.

Không âm thầm bỏ message nếu giao thức yêu cầu xử lý đầy đủ. Nếu nghiệp vụ cho phép mất dữ liệu, hãy định nghĩa rõ message nào có thể bị loại, cách client biết điều đó và cách khôi phục. Tránh dùng `CallerRunsPolicy` một cách máy móc trên callback gRPC: chạy công việc nặng ngay trên thread gọi callback có thể làm nghẽn luồng xử lý RPC khác.

## Giới hạn vòng đời và mức đồng thời của stream

Stream mở lâu vẫn chiếm tài nguyên dù tại một thời điểm không có message nào được truyền. Hãy cân nhắc deadline hoặc thời lượng tối đa, giới hạn số stream đồng thời theo tenant và toàn service, cùng chính sách idle timeout phù hợp. Deadline của RPC cần được truyền và tôn trọng ở các lời gọi downstream; nếu không, một stream đã hết hạn ở phía client vẫn có thể để lại công việc nền tiếp tục chạy.

Khi client hủy RPC hoặc deadline hết hạn, service cần dừng producer, hủy truy vấn/công việc downstream và đóng tài nguyên như cursor, file handle hoặc subscription. Với `ServerCallStreamObserver`, có thể đăng ký `setOnCancelHandler` để phản ứng khi client hủy. Đảm bảo callback hủy không giải phóng một tài nguyên trong khi worker khác vẫn đang sử dụng nó; việc dừng và đóng cần được đồng bộ đúng cách.

Đặt giới hạn riêng cho:

- Số stream đang mở trên mỗi người dùng hoặc tenant.
- Tổng stream đang hoạt động trên một instance.
- Số worker xử lý stream và độ dài queue chờ worker.
- Tổng byte hoặc số message được phép trong một stream.
- Thời gian không có hoạt động và thời lượng tối đa của stream.

Các giới hạn cần phối hợp với giới hạn kết nối và cấu hình proxy/load balancer. Nếu chỉ giới hạn tại một instance nhưng có nhiều instance, quota toàn tenant có thể cần bộ đếm dùng chung hoặc cơ chế phân bổ năng lực rõ ràng.

## Ví dụ một thiết kế streaming có kiểm soát

Giả sử client tải một tệp lớn lên dịch vụ Spring gRPC bằng client-streaming RPC. Thiết kế an toàn có thể chia tệp thành các chunk nhỏ, giới hạn kích thước từng chunk, chỉ cho phép một số chunk đang được xử lý, và ghi từng chunk vào nơi lưu trữ theo luồng. Server xác thực quyền truy cập trước khi cấp tài nguyên, kiểm tra tổng byte và số chunk, rồi xác nhận hoàn tất sau khi kiểm tra checksum.

Trong thiết kế này, server không ghép toàn bộ tệp thành một `byte[]` trong heap. Khi storage chậm, server giảm demand để client không thể tiếp tục đẩy chunk vào một queue vô hạn. Nếu vượt quota tổng, server kết thúc RPC bằng lỗi đã thỏa thuận và ghi nhận nguyên nhân. Khi client ngắt kết nối, server hủy thao tác ghi dở dang hoặc lưu trạng thái có thể tiếp tục theo chính sách của nghiệp vụ.

Với server-streaming RPC trả về dữ liệu lớn, áp dụng cách tương tự theo chiều ngược lại: đọc theo từng trang hoặc cursor, chỉ gửi khi `isReady()` cho phép, và đóng nguồn dữ liệu khi stream hoàn tất hoặc bị hủy.

## Quan sát và kiểm thử

Theo dõi các chỉ số giúp phát hiện buffer đang tích tụ trước khi heap cạn:

| Chỉ số | Điều cần quan sát |
|---|---|
| Số stream đang hoạt động và thời lượng stream | Stream tăng liên tục hoặc có stream sống lâu bất thường |
| Số phần tử và tổng byte trong queue | Queue tăng kéo dài, thường xuyên chạm giới hạn |
| Thời gian chờ trong queue và thời gian xử lý message | Consumer đang chậm hơn producer |
| Số lần queue đầy hoặc RPC bị từ chối | Hệ thống thường xuyên chạm ngưỡng bảo vệ |
| Heap, GC pause và số thread đang hoạt động | Áp lực bộ nhớ hoặc thread tăng theo tải |
| Tỷ lệ stream bị hủy, timeout và lỗi | Client hoặc downstream không theo kịp |

Nên kiểm thử ít nhất các trường hợp sau:

1. Producer gửi nhanh hơn consumer trong thời gian dài; xác minh queue không vượt giới hạn và heap ổn định.
2. Client đọc response chậm; xác minh server tôn trọng `isReady()` và không tạo trước toàn bộ response.
3. Gửi message lớn và nhiều message liên tục; xác minh giới hạn theo byte và theo số lượng đều hoạt động.
4. Mở nhiều stream đồng thời từ một tenant và từ nhiều tenant; xác minh quota và giới hạn toàn service.
5. Hủy client giữa stream hoặc để deadline hết hạn; xác minh producer, cursor, subscription và worker được dừng/giải phóng.
6. Làm chậm dependency như database hoặc object storage; xác minh backpressure truyền ngược tới nguồn tạo dữ liệu.
7. Làm đầy queue; xác minh hệ thống áp dụng đúng chính sách từ chối, tạm dừng hoặc hủy stream và phát ra metric/log tương ứng.

## Những cách làm cần tránh

- Thu thập toàn bộ stream vào `List`, `byte[]` hoặc `String` khi kích thước đầu vào không có giới hạn rõ ràng.
- Dùng queue không giới hạn hoặc queue có dung lượng quá lớn so với ngân sách bộ nhớ.
- Gọi `onNext` trong vòng lặp mà không kiểm tra readiness và không giới hạn tốc độ producer.
- Nhận message rồi đẩy sang executor có queue vô hạn.
- Cho phép stream tồn tại vô thời hạn mà không có quota, idle timeout hoặc cơ chế hủy.
- Chỉ giới hạn kích thước từng message mà bỏ qua tổng byte, số message và số stream đồng thời.
- Bỏ qua cancellation khiến truy vấn, cursor hoặc công việc nền tiếp tục chạy sau khi client đã rời đi.

Trong Spring gRPC, service thường được đăng ký như một Spring bean và sử dụng API streaming của grpc-java. Việc Spring quản lý bean không tự tạo backpressure cho `StreamObserver`; ứng dụng vẫn phải thiết kế giới hạn queue, flow control, quota và vòng đời RPC. Khi các giới hạn này được đặt rõ ràng và đo lường được, tải tăng sẽ dẫn đến điều tiết hoặc từ chối có kiểm soát thay vì làm bộ nhớ tăng không ngừng.
