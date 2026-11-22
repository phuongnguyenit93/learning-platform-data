# Streaming message và backpressure trong Spring gRPC

Streaming cho phép một RPC trao đổi nhiều message theo thời gian. Nhưng nếu bên gửi phát message nhanh hơn khả năng tiếp nhận hoặc xử lý của bên nhận, dữ liệu có thể tích tụ trong bộ đệm, làm tăng độ trễ và tiêu thụ bộ nhớ. **Backpressure** là cơ chế điều tiết tốc độ gửi theo khả năng tiếp nhận của phía sau, giúp luồng dữ liệu ổn định khi tải thay đổi.

Trong **Spring gRPC**, ứng dụng dùng API gRPC Java như **StreamObserver**, **isReady()**, **setOnReadyHandler()** và cơ chế điều khiển nhu cầu nhận message. Hiểu đúng các tín hiệu này giúp triển khai server streaming, client streaming và bidirectional streaming mà không tạo hàng đợi vô hạn hoặc nhầm việc gửi message với việc xử lý thành công.

## 1. Vì sao streaming cần backpressure?

Giả sử một thiết bị gửi 20.000 bản ghi đo mỗi giây, trong khi server chỉ xử lý được 5.000 bản ghi mỗi giây. Nếu client cứ gọi **onNext()** liên tục, lượng message chờ xử lý có thể tăng khoảng 15.000 bản ghi mỗi giây. Sau một thời gian, bộ nhớ bị chiếm dụng, độ trễ tăng và cuối cùng có thể gây lỗi toàn hệ thống.

~~~mermaid
flowchart LR
    A["Producer<br/>20.000 msg/s"] --> B["Queue / transport buffer"]
    B --> C["Consumer<br/>5.000 msg/s"]
    B --> D["Backlog tăng"]
    D --> E["Độ trễ và bộ nhớ tăng"]
    E --> F["Quá tải / lỗi"]
~~~

Backpressure giúp bên gửi **tạm dừng, giảm tốc hoặc chỉ phát thêm khi bên nhận sẵn sàng**. Mục tiêu không phải luôn đạt tốc độ gửi cao nhất, mà là giữ lượng dữ liệu đang chờ ở mức có giới hạn.

Backpressure đặc biệt quan trọng khi:

- Server streaming phát sự kiện tới client có mạng chậm.
- Client streaming tải một lô dữ liệu lớn lên server.
- Bidirectional streaming có hai chiều xử lý với tốc độ khác nhau.
- Server nhận nhiều stream đồng thời và phải chia sẻ CPU, bộ nhớ, connection và tài nguyên downstream.

Unary thường có một request và một response nên không có chuỗi message dài để điều tiết. Tuy vậy, unary vẫn cần giới hạn kích thước message, số request đồng thời và thời gian xử lý.

## 2. Ba lớp điều tiết cần phân biệt

Backpressure không phải một công tắc duy nhất. Trong gRPC chạy trên HTTP/2, có ba lớp liên quan:

| Lớp | Cơ chế | Điều tiết điều gì? |
| --- | --- | --- |
| **HTTP/2 transport** | Flow-control window ở cấp connection và stream | Số byte DATA có thể truyền mà chưa được xác nhận ở tầng transport |
| **gRPC Java API** | Readiness và inbound demand | Khi nào ứng dụng có thể gửi thêm hoặc yêu cầu nhận thêm message |
| **Ứng dụng** | Queue hữu hạn, giới hạn worker, quota, batch | Tốc độ xử lý nghiệp vụ và lượng công việc đang chờ |

HTTP/2 flow control hoạt động theo **byte**, không hiểu nội dung nghiệp vụ của Reading hay OrderEvent. gRPC đóng khung message Protobuf vào DATA frame; một message lớn có thể tiêu thụ nhiều byte của cửa sổ truyền tải.

Ở tầng gRPC Java, **isReady()** và **setOnReadyHandler()** giúp phía gửi biết khả năng ghi hiện tại. Với chiều nhận, có thể dùng **manual inbound flow control** để yêu cầu một số lượng message cụ thể thay vì nhận tự động.

Ở tầng ứng dụng, ngay cả khi transport cho phép gửi, một hàng đợi nội bộ không giới hạn vẫn có thể làm cạn bộ nhớ. Vì vậy cần phối hợp cả ba lớp; không thể chỉ dựa vào HTTP/2 flow control để bảo vệ toàn bộ hệ thống.

## 3. isReady() và setOnReadyHandler() khi gửi message

Trong gRPC Java, các observer hỗ trợ gửi dữ liệu cung cấp:

- **isReady()**: cho biết hiện tại có thể gửi thêm mà không làm bộ đệm outbound tăng quá mức theo cơ chế gRPC.
- **setOnReadyHandler(Runnable)**: đăng ký callback được gọi khi observer chuyển sang trạng thái sẵn sàng gửi.

Mẫu điều khiển là **chỉ phát message khi isReady() trả về true**, và tạm dừng khi trả về false. Khi có callback on-ready, tiếp tục phát từ vị trí đã dừng.

~~~java
// Mẫu minh họa cho một response stream phía server.
ServerCallStreamObserver<Reading> output =
    (ServerCallStreamObserver<Reading>) responseObserver;

Iterator<Reading> pending = readings.iterator();
AtomicBoolean completed = new AtomicBoolean(false);

Runnable sendAvailable = () -> {
    while (output.isReady() && pending.hasNext()
            && !output.isCancelled()) {
        output.onNext(pending.next());
    }

    if (!pending.hasNext() && !output.isCancelled()
            && completed.compareAndSet(false, true)) {
        output.onCompleted();
    }
};

output.setOnReadyHandler(sendAvailable);
sendAvailable.run(); // Xử lý cả trường hợp stream đã sẵn sàng từ đầu.
~~~

Đây là mẫu cho một danh sách hữu hạn; trong ứng dụng thật, nguồn dữ liệu hoặc hàng đợi phải có giới hạn. Nếu dữ liệu được tạo bất đồng bộ, cần điều phối việc thêm phần tử và gọi tiếp sender theo một executor phù hợp. Không gọi sender đồng thời từ nhiều thread nếu chưa có cơ chế tuần tự hóa.

**Không hiểu isReady() là xác nhận đã xử lý.** Giá trị true chỉ là tín hiệu readiness của gRPC outbound flow; nó không chứng minh peer đã đọc, xử lý hoặc lưu message. **onNext()** trả về cũng không phải acknowledgement nghiệp vụ.

### Readiness có thể thay đổi

Không nên kiểm tra isReady() một lần khi bắt đầu rồi phát toàn bộ stream. Khi bộ đệm đầy, readiness có thể chuyển thành false. Producer cần dừng phát và chờ callback thay vì tiếp tục đẩy message vào observer.

Với nhiều producer cùng gửi vào một observer, phải **tuần tự hóa** thao tác onNext, onCompleted và onError. **StreamObserver không mặc định thread-safe**; nhiều thread gọi đồng thời có thể gây race, sai thứ tự hoặc kết thúc stream không đúng lúc.

## 4. Điều khiển số message được nhận: manual inbound flow control

Readiness điều tiết **chiều gửi của observer hiện tại**. Một yêu cầu khác là giới hạn số message mà ứng dụng nhận trước khi xử lý xong. gRPC Java hỗ trợ manual inbound flow control thông qua:

- **disableAutoInboundFlowControl()**: tắt cơ chế tự động yêu cầu thêm message.
- **request(n)**: yêu cầu gRPC chuyển thêm tối đa n message inbound cho ứng dụng.

Ví dụ, server có thể chỉ yêu cầu một Reading tiếp theo sau khi đã xử lý xong bản ghi hiện tại. Với **ServerCallStreamObserver**, các API điều khiển inbound được gọi trên observer phía server, thường được truyền vào method dưới vai trò response observer:

~~~java
ServerCallStreamObserver<UploadSummary> call =
    (ServerCallStreamObserver<UploadSummary>) responseObserver;

call.disableAutoInboundFlowControl();
call.request(1);

return new StreamObserver<Reading>() {
    @Override
    public void onNext(Reading reading) {
        processAsync(reading, result -> {
            // Chỉ yêu cầu message kế tiếp sau khi xử lý xong.
            if (!call.isCancelled()) {
                call.request(1);
            }
        });
    }

    @Override
    public void onError(Throwable error) {
        // Dừng xử lý và giải phóng tài nguyên.
    }

    @Override
    public void onCompleted() {
        // Hoàn tất tổng hợp và gửi UploadSummary.
    }
};
~~~

Đây là **mẫu ý tưởng**, trong ứng dụng thật cần bảo đảm callback xử lý bất đồng bộ không gọi request(1) sau khi RPC đã bị hủy hoặc kết thúc, và mọi state được điều phối an toàn giữa các thread. Cần xử lý ngoại lệ trong processAsync, đặt giới hạn thời gian và không để công việc đã nhận bị treo vô hạn.

Ở client, **ClientResponseObserver.beforeStart(ClientCallStreamObserver<ReqT>)** cung cấp call observer để cấu hình điều khiển trước khi stream bắt đầu. Cơ chế **request(n)** trên call observer kiểm soát số response message inbound mà client yêu cầu nhận. Cách dùng cụ thể cần khớp với chiều inbound/outbound của API và phiên bản gRPC Java đang sử dụng.

Manual inbound flow control phù hợp khi xử lý message có chi phí cao hoặc cần phối hợp với worker pool. Nếu chỉ xử lý message nhanh, tuần tự và lượng dữ liệu có giới hạn, auto flow control thường đơn giản hơn.

## 5. Áp dụng theo từng loại streaming RPC

| Loại RPC | Chiều cần điều tiết | Cách thường dùng |
| --- | --- | --- |
| **Server streaming** | Server → client | Server kiểm tra readiness trước khi phát response; client có thể giới hạn demand inbound |
| **Client streaming** | Client → server | Client chỉ gửi khi request observer sẵn sàng; server có thể yêu cầu từng request sau khi xử lý |
| **Bidirectional streaming** | Cả hai chiều độc lập | Mỗi phía điều tiết outbound của mình và inbound demand của mình |

### Server streaming

Server có thể phát dữ liệu từ nguồn lớn hoặc sự kiện liên tục. Nếu client chậm, server phải tạm dừng producer khi response observer không ready. Với nguồn dữ liệu có thể truy vấn theo trang, chỉ tải phần tiếp theo khi phía gửi có khả năng phát; tránh nạp toàn bộ dữ liệu vào List.

### Client streaming

Client tải nhiều message lên. Producer nên giữ một lượng nhỏ message đang chờ, gửi khi observer sẵn sàng và dừng khi readiness chuyển false. Server xử lý message theo quota hoặc worker pool có giới hạn; không tạo một task không giới hạn cho mỗi onNext.

### Bidirectional streaming

Hai chiều có readiness và tốc độ xử lý riêng. Client có thể đang chậm nhận event trong khi vẫn gửi request nhanh; hoặc server gửi response nhanh trong khi client đang bận. Mỗi phía phải có chính sách queue, giới hạn và hủy riêng, không giả định điều tiết một chiều sẽ tự động kiểm soát chiều còn lại.

## 6. Queue hữu hạn và chính sách khi quá tải

isReady() kiểm soát khả năng ghi của gRPC, nhưng producer ứng dụng vẫn cần một hàng đợi có giới hạn. Một thiết kế phổ biến:

1. Producer tạo message và đưa vào queue có capacity xác định.
2. Một sender tuần tự lấy message khỏi queue khi observer ready.
3. Khi queue đầy, áp dụng chính sách nghiệp vụ: chặn producer trong giới hạn, từ chối message, giảm tần suất, gộp các bản cập nhật hoặc hủy stream.
4. Khi stream bị hủy/lỗi, dừng producer và giải phóng queue.

Không có chính sách drop nào phù hợp cho mọi dữ liệu:

| Loại dữ liệu | Khi quá tải có thể cân nhắc | Điều cần tránh |
| --- | --- | --- |
| Telemetry chỉ cần giá trị mới nhất | Gộp nhiều cập nhật thành giá trị mới nhất theo thiết bị | Gộp nếu cần lưu đầy đủ lịch sử |
| Log/audit | Backpressure hoặc ghi bền vào hàng đợi ngoài | Âm thầm bỏ sự kiện |
| Lệnh điều khiển | Từ chối có status hoặc áp dụng quota | Gộp lệnh nếu thứ tự/thao tác không tương đương |
| Sự kiện giao diện tạm thời | Coalesce hoặc drop theo chính sách đã định | Giữ queue vô hạn cho client mất kết nối |

Hàng đợi cần giới hạn cả **số message** và **tổng byte**. Một queue 100 phần tử vẫn có thể chiếm nhiều GB nếu mỗi message rất lớn. Đặt thêm giới hạn kích thước message và thời gian tồn tại.

## 7. Khi nào nên yêu cầu thêm message, khi nào nên gửi tiếp?

Hai thao tác thường bị nhầm:

- **Outbound readiness:** bên gửi kiểm tra isReady() để biết có nên gọi onNext() thêm hay chưa.
- **Inbound demand:** bên nhận dùng request(n) để yêu cầu gRPC chuyển thêm n message đến ứng dụng khi manual inbound flow control được bật.

Một bên điều tiết số message **đang gửi ra**, bên kia điều tiết số message **được giao vào callback nhận**. Chúng phối hợp nhưng không thay thế nhau.

Ví dụ một server nhận upload có thể:

- Dùng inbound demand để chỉ nhận một chunk mới sau khi chunk trước đã được xử lý.
- Dùng outbound readiness để chỉ gửi acknowledgement hoặc summary khi response stream sẵn sàng.
- Dùng queue hữu hạn cho công việc DB đang chờ, thay vì tạo task không giới hạn.

Nếu nghiệp vụ cần xác nhận rằng dữ liệu đã được ghi bền, hãy gửi **acknowledgement message** chứa sequence hoặc upload ID sau khi commit. Tín hiệu isReady(), request(n) và việc gọi onNext() không mang ngữ nghĩa xác nhận lưu trữ.

## 8. Hủy stream, deadline và lỗi quá tải

Backpressure không thể giải quyết một consumer đã ngừng hoạt động mãi mãi. Mỗi stream cần chính sách deadline, idle timeout hoặc cancel phù hợp.

Các trạng thái thường gặp:

| Status | Khi nào có thể dùng |
| --- | --- |
| **RESOURCE_EXHAUSTED** | Vượt quota, giới hạn queue hoặc dung lượng được phép |
| **CANCELLED** | Client hoặc server chủ động hủy stream |
| **DEADLINE_EXCEEDED** | RPC vượt quá ngân sách thời gian |
| **UNAVAILABLE** | Dịch vụ hoặc kết nối tạm thời không sẵn sàng |
| **INVALID_ARGUMENT** | Kích thước hoặc nội dung message vi phạm hợp đồng |

Khi hủy, dừng producer, ngừng tạo message, giải phóng queue và hủy các tác vụ downstream nếu có thể. Không tiếp tục gọi onNext() sau khi observer đã kết thúc.

Với streaming RPC, deadline thường áp dụng cho **toàn bộ lời gọi**, không tự khởi động lại sau mỗi message. Một stream dài cần cách quản lý vòng đời rõ ràng; có thể dùng phiên có thời hạn và kết nối lại bằng cursor/sequence thay vì giữ một RPC vô hạn.

## 9. Ví dụ thiết kế upload có giới hạn

Giả sử client gửi Reading theo client streaming. Một thiết kế ổn định cần các thành phần:

- Client có nguồn dữ liệu đọc tuần tự, không tải toàn bộ file vào RAM.
- Client giữ queue nhỏ và chỉ gửi khi request observer ready.
- Server kiểm tra sequence, giới hạn số lượng và kích thước, xử lý từng message.
- Server chỉ gửi UploadSummary sau khi hoàn tất và xác định rõ dữ liệu đã được commit hay chưa.
- Khi lỗi giữa chừng, client dùng upload ID và sequence để hỏi trạng thái hoặc tiếp tục mà không ghi trùng.

Pseudocode sender:

~~~java
void sendWhileReady(
        ClientCallStreamObserver<Reading> requestStream,
        Iterator<Reading> source) {
    while (requestStream.isReady() && source.hasNext()) {
        requestStream.onNext(source.next());
    }

    if (!source.hasNext()) {
        requestStream.onCompleted();
    }
    // Nếu chưa ready, chờ setOnReadyHandler gọi lại hàm này.
}
~~~

Trong triển khai thực tế, cần cờ completed để bảo đảm onCompleted() chỉ được gọi một lần, và đồng bộ hóa nếu sendWhileReady có thể được kích hoạt từ nhiều thread. Cũng cần phân biệt nguồn đã hết với stream đã kết thúc do lỗi/hủy.

## 10. Kiểm thử backpressure

Một bài test chỉ xác minh server nhận đủ message khi client gửi nhanh chưa đủ để chứng minh backpressure. Cần tạo consumer chậm và quan sát sender có thực sự dừng/giảm tốc hay queue vẫn tăng không giới hạn.

Các tình huống nên kiểm thử:

1. **Consumer chậm:** xử lý mỗi message có độ trễ nhân tạo; xác minh sender tuân thủ readiness hoặc inbound demand.
2. **Queue đầy:** kiểm tra chính sách từ chối, gộp hoặc dừng producer đúng như thiết kế.
3. **Message lớn:** giới hạn byte hoạt động, không chỉ giới hạn số phần tử.
4. **Cancel giữa stream:** producer và worker dừng, queue được giải phóng.
5. **Deadline:** stream hết hạn không để lại task hoặc tài nguyên đang chạy vô hạn.
6. **Nhiều stream đồng thời:** một client chậm không làm cạn tài nguyên của các client khác.
7. **Thứ tự và tính toàn vẹn:** không mất hoặc đảo thứ tự message khi sender tạm dừng rồi tiếp tục.

Trong test tích hợp Spring gRPC, dùng client thực hiện stream qua stub và một service có tốc độ xử lý được điều khiển. Đo số message đang chờ, thời gian chờ readiness, throughput, memory và status cuối. Không chỉ dựa vào thời gian chạy tổng thể để kết luận backpressure hoạt động.

## 11. Chỉ số quan sát khi vận hành

Để phát hiện stream đang gây quá tải, theo dõi:

- **Số stream đang mở** theo method và client/tenant.
- **Message/byte gửi và nhận** trên mỗi RPC.
- **Queue depth**, tuổi message lâu nhất và số lần queue đạt ngưỡng.
- **Thời gian chờ readiness** và số lần sender bị tạm dừng.
- **Tốc độ producer/consumer**, throughput và độ trễ xử lý.
- **Số RPC bị cancel, deadline hoặc RESOURCE_EXHAUSTED**.
- **Bộ nhớ, CPU và số worker đang bận**.

Khi queue tăng liên tục, cần tìm nơi tiêu thụ chậm hoặc producer không tôn trọng readiness. Khi isReady() thường xuyên false, có thể client/server downstream đang chậm hoặc kích thước/tần suất message vượt khả năng hiện tại. Khi nhiều stream bị RESOURCE_EXHAUSTED, cần xem quota và giới hạn có phù hợp với tải hợp lệ hay không.

## 12. Ghi nhớ và tự kiểm tra

**Backpressure** giữ cho tốc độ gửi phù hợp khả năng nhận/xử lý. Trong gRPC Java:

- **isReady()** và **setOnReadyHandler()** điều tiết **chiều outbound**.
- **disableAutoInboundFlowControl()** và **request(n)** điều tiết **số message inbound được giao** khi dùng manual flow control.
- Queue hữu hạn, quota, giới hạn byte và cancel bảo vệ **tầng ứng dụng**.

Không tín hiệu nào trong số đó chứng minh message đã được xử lý nghiệp vụ hoặc ghi bền. Nếu cần acknowledgement, phải định nghĩa response/message xác nhận riêng.

Tự kiểm tra:

1. Vì sao HTTP/2 flow control chưa đủ để ngăn queue ứng dụng tăng vô hạn?
2. isReady() và request(1) điều khiển hai việc khác nhau như thế nào?
3. Khi consumer chậm, vì sao sender cần dừng phát thay vì tiếp tục gọi onNext()?
4. Vì sao queue cần giới hạn theo byte ngoài số lượng message?
5. Nếu upload bị hủy sau khi server đã lưu một phần dữ liệu, cần những thông tin nào để retry an toàn?

Thiết kế streaming tốt không chỉ chọn đúng loại RPC mà còn kiểm soát **tốc độ, bộ nhớ, vòng đời và ngữ nghĩa xác nhận** của từng message. Đó là nền tảng để dịch vụ Spring gRPC hoạt động ổn định khi tải tăng hoặc các client có tốc độ mạng và xử lý khác nhau.
