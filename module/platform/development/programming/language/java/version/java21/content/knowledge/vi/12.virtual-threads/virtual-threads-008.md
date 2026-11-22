# Chi phí stack, đối tượng thread và số lượng tác vụ còn sống

Virtual thread nhẹ hơn platform thread vì nó không giữ riêng một OS thread cùng một native stack cố định trong suốt vòng đời. Tuy vậy, virtual thread không miễn phí: mỗi tác vụ vẫn có một đối tượng **Thread**, trạng thái scheduler/continuation, stack đang sử dụng và các object mà tác vụ còn tham chiếu.

Khi đánh giá khả năng phục vụ nhiều request đồng thời, cần tính theo số tác vụ còn sống và dữ liệu mà mỗi tác vụ giữ lại, không chỉ đếm số carrier thread. Một triệu virtual thread có thể khả thi với tác vụ I/O đang chờ và giữ ít dữ liệu; cùng số lượng đó có thể vượt heap nếu mỗi request giữ payload lớn, cache riêng hoặc nhiều buffer.

## 1. Virtual thread và platform thread tiêu tốn tài nguyên khác nhau

Cả platform thread và virtual thread đều là instance của **java.lang.Thread**, nhưng cách chúng gắn với OS thread khác nhau.

| Đặc điểm | Platform thread | Virtual thread |
|---|---|---|
| Đơn vị được OS lập lịch trực tiếp | OS thread tương ứng | Carrier là platform thread |
| Liên kết với OS thread | Giữ OS thread trong suốt vòng đời | Có thể mount/unmount trên các carrier |
| Stack | Native stack do runtime/OS quản lý, thường có dung lượng lớn và được cấp theo cấu hình thread | Stack frame được lưu thành các heap stack chunk khi virtual thread unmount; dung lượng tăng/giảm theo nhu cầu |
| Đối tượng Java Thread | Có | Có |
| Số lượng đồng thời | Thường bị giới hạn bởi chi phí OS thread và native stack | Có thể rất lớn, kể cả hàng trăm nghìn hoặc hàng triệu trong workload phù hợp |
| Tác vụ phù hợp | CPU-bound hoặc tác vụ cần kiểm soát số worker | Nhiều tác vụ độc lập, phần lớn thời gian chờ I/O |

Virtual thread vẫn chạy Java code trên một platform thread gọi là *carrier*. Khi virtual thread thực hiện một thao tác blocking được JDK hỗ trợ unmount, runtime có thể tạm dừng nó và giải phóng carrier để chạy virtual thread khác. Virtual thread đang chờ vẫn là một thread và tác vụ của nó vẫn còn sống.

Điều này giúp tăng số tác vụ có thể chờ đồng thời mà không cần tạo một OS thread cho mỗi tác vụ.

## 2. Chi phí stack: heap stack chunk thay cho native stack cố định

### Stack của platform thread

Platform thread chạy trực tiếp trên OS thread của nó. Native stack được dành cho thread đó và thường có kích thước tương đối lớn theo cấu hình runtime hoặc hệ điều hành. Vì vậy, số platform thread đồng thời bị giới hạn bởi tổng tài nguyên native memory và giới hạn của hệ điều hành.

### Stack của virtual thread

Trong triển khai Java 21, stack của virtual thread được biểu diễn bằng các đối tượng stack chunk trên Java heap khi thread unmount khỏi carrier. Các chunk có thể tăng hoặc giảm theo độ sâu lời gọi thực tế, thay vì mỗi virtual thread phải giữ một native stack lớn cố định như platform thread.

Khi virtual thread được mount để chạy, runtime sử dụng carrier để thực thi. Khi nó unmount, các stack frame cần giữ lại được lưu trong heap stack chunks để có thể tiếp tục sau đó. Vì vậy:

- Một tác vụ có call stack nông thường chỉ cần ít stack storage.
- Một tác vụ gọi nhiều tầng phương thức hoặc giữ call stack sâu sẽ cần nhiều stack storage hơn.
- Nhiều virtual thread đang chờ I/O vẫn giữ phần stack cần thiết để tiếp tục tác vụ.
- Stack chunk nằm trong heap nên vẫn góp phần vào heap occupancy và hoạt động của garbage collector.

Không có một con số byte cố định áp dụng cho mọi virtual thread. Chi phí phụ thuộc vào call stack tại thời điểm đo, dữ liệu được giữ trong các frame, cách runtime cấp phát chunk và workload thực tế.

Không nên ước tính bộ nhớ bằng phép nhân số virtual thread với Xss như thể mỗi virtual thread giữ một native stack có kích thước cố định. Thread.Builder.OfVirtual trong Java 21 cũng không cung cấp phương thức stackSize(); lựa chọn stackSize() thuộc builder dành cho platform thread.

## 3. Mỗi virtual thread vẫn là một đối tượng Thread

Virtual thread là một instance của Thread, có danh tính, trạng thái, tên (nếu được đặt), stack trace và các thông tin quản lý vòng đời. Runtime còn cần trạng thái continuation/scheduler để có thể tạm dừng và tiếp tục tác vụ.

Do đó, tạo nhiều virtual thread vẫn tạo ra nhiều object. Ví dụ, một triệu tác vụ đồng thời sẽ cần một triệu virtual thread object, ngoài các object của chính tác vụ.

Một tác vụ thường còn có những object khác:

- Runnable hoặc Callable và các object bao quanh task.
- Future nếu tác vụ được submit và cần lấy kết quả.
- Request, response, DTO, buffer, chuỗi và dữ liệu đã parse.
- Context của giao dịch, thông tin người dùng và tracing.
- Các object mà biến local hoặc ThreadLocal còn tham chiếu.

Vì vậy, chi phí một tác vụ không chỉ là Thread object. Dữ liệu ứng dụng được giữ trong suốt thời gian chờ thường có thể chiếm nhiều bộ nhớ hơn metadata của thread.

## 4. Số lượng tác vụ còn sống khác số carrier đang chạy

Giả sử server có 8 carrier thread và đang nhận 50.000 request. Mỗi request được xử lý bằng một virtual thread:

- Một số virtual thread đang chạy trên carrier.
- Nhiều virtual thread khác đang chờ socket, database, semaphore hoặc một thao tác blocking khác.
- Các virtual thread đang chờ vẫn còn sống, vẫn giữ trạng thái và dữ liệu cần cho request.

Số carrier cho biết khả năng thực thi Java code tại một thời điểm. Số virtual thread còn sống phản ánh số tác vụ đang được quản lý đồng thời. Hai con số này không bằng nhau.

~~~text
50.000 request đang còn xử lý
              |
              v
      50.000 virtual threads
              |
       +------+------+
       |             |
       v             v
  Đang runnable   Đang chờ I/O,
  hoặc chạy trên  semaphore, DB...
  carrier         (đã unmount nếu có thể)
       |             |
       +------+------+
              |
              v
       Một nhóm carrier
       platform threads
       thực thi Java code
~~~

Khi request chờ database trong vài trăm mili giây, carrier có thể chạy request khác. Tuy nhiên, virtual thread của request đang chờ không tự biến mất: nó vẫn phải giữ trạng thái để tiếp tục khi database trả kết quả.

Vì vậy, khả năng tạo hàng triệu virtual thread không có nghĩa ứng dụng có thể giữ hàng triệu request với payload tùy ý trong heap.

## 5. Những yếu tố làm tăng bộ nhớ của mỗi tác vụ

### Call stack sâu và biến local còn được sử dụng

Stack frame có thể giữ reference đến request object, dữ liệu đã parse hoặc buffer. Khi tác vụ đang chờ, các reference còn cần thiết có thể làm object đó tiếp tục được giữ trong bộ nhớ.

Ví dụ, nếu một request đọc toàn bộ nội dung file vào byte[], sau đó chờ một dịch vụ mạng, mảng byte vẫn có thể được giữ bởi biến local cho tới khi tác vụ hoàn tất hoặc không còn cần biến đó nữa.

Hãy tránh giữ dữ liệu lớn xuyên suốt một khoảng chờ nếu có thể xử lý hoặc giải phóng nó trước khi chờ. Chỉ giữ trạng thái thực sự cần để tiếp tục tác vụ.

### ThreadLocal và InheritableThreadLocal

Virtual thread hỗ trợ ThreadLocal và InheritableThreadLocal, nhưng mỗi virtual thread là một thread riêng. Nếu dùng ThreadLocal để cache một object đắt tiền, mỗi tác vụ có thể tạo một bản cache riêng thay vì tái sử dụng cache trên một nhóm worker được dùng lại.

Ví dụ, cách cache formatter có trạng thái bằng ThreadLocal từng phù hợp với một số thread pool:

~~~java
static final ThreadLocal<SimpleDateFormat> FORMATTER =
    ThreadLocal.withInitial(
        () -> new SimpleDateFormat("yyyy-MM-dd")
    );
~~~

Nếu mỗi request chạy trên một virtual thread mới, nhiều request có thể tạo ra rất nhiều formatter riêng. Điều này làm tăng số object và bộ nhớ giữ lại, trong khi mục tiêu cache ban đầu là tái sử dụng một số ít formatter trên worker thread.

Với formatter ngày giờ, dùng DateTimeFormatter immutable để chia sẻ một instance:

~~~java
static final DateTimeFormatter FORMATTER =
    DateTimeFormatter.ISO_LOCAL_DATE;
~~~

ThreadLocal vẫn có thể hữu ích cho context gắn với một request hoặc giao dịch. Cần đánh giá kích thước object, vòng đời và việc kế thừa giá trị từ thread tạo virtual thread; tránh dùng nó làm kho cache các object lớn cần tái sử dụng giữa nhiều tác vụ.

### Buffer và tài nguyên I/O

Một virtual thread có thể giữ socket, stream, JDBC connection, buffer hoặc handle tới tài nguyên khác trong khi chờ. Những tài nguyên này có giới hạn riêng và có thể tiêu tốn heap, native memory hoặc file descriptor.

Ví dụ, 100.000 virtual thread không có nghĩa database có thể phục vụ 100.000 connection đồng thời. Connection pool, giới hạn file descriptor và năng lực dịch vụ downstream vẫn là các giới hạn thực tế.

## 6. Biểu diễn mỗi tác vụ bằng một virtual thread

Virtual thread được thiết kế để đại diện cho một tác vụ, không phải một worker dùng chung cho nhiều tác vụ như platform thread pool.

Java 21 cung cấp Executors.newVirtualThreadPerTaskExecutor(). Executor này tạo một virtual thread mới cho mỗi task được submit; nó không phải thread pool có số worker cố định.

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> profile = executor.submit(
        () -> loadProfile(userId)
    );

    Future<List<Order>> orders = executor.submit(
        () -> loadOrders(userId)
    );

    String userProfile = profile.get();
    List<Order> userOrders = orders.get();

    render(userProfile, userOrders);
}
~~~

ExecutorService.close() được gọi tự động khi thoát try và chờ các task đã submit hoàn tất. Vì vậy, cần bảo đảm các task có timeout và khả năng kết thúc phù hợp; nếu một task bị mắc kẹt vô thời hạn, việc đóng executor cũng có thể phải chờ lâu.

Không nên tạo pool để tái sử dụng virtual thread. Pool làm mất mô hình một task/một thread và không cần thiết để giảm chi phí OS thread, vì virtual thread vốn được runtime quản lý nhẹ hơn platform thread.

## 7. Giới hạn tài nguyên bằng backpressure và Semaphore

Virtual thread giúp biểu diễn nhiều tác vụ đồng thời, nhưng không làm tăng dung lượng của database, API bên ngoài hoặc một dịch vụ có giới hạn kết nối.

Nếu dịch vụ downstream chỉ cho phép tối đa 20 request đồng thời, hãy giới hạn riêng tài nguyên đó bằng Semaphore:

~~~java
private static final Semaphore API_PERMITS = new Semaphore(20);

static Result callExternalApi(Request request)
        throws InterruptedException {
    API_PERMITS.acquire();
    try {
        return invokeApi(request);
    } finally {
        API_PERMITS.release();
    }
}
~~~

Các virtual thread vượt quá 20 permit có thể chờ trên semaphore. Nếu thao tác chờ hỗ trợ unmount, carrier được giải phóng cho tác vụ khác. Tuy nhiên, những virtual thread đang đợi vẫn còn sống và vẫn giữ dữ liệu của request.

Vì vậy cần phân biệt hai giới hạn:

- **Giới hạn tài nguyên downstream:** dùng semaphore, connection pool hoặc rate limiter phù hợp.
- **Giới hạn số tác vụ được nhận vào hệ thống:** dùng admission control, hàng đợi có giới hạn, từ chối request hoặc backpressure ở tầng tiếp nhận.

Chỉ đặt semaphore bên trong task không giới hạn số virtual thread đã được tạo. Nếu hệ thống tiếp tục nhận request vô hạn rồi tạo virtual thread cho tất cả, hàng đợi các thread đang chờ vẫn có thể làm đầy heap.

Nếu đã có JDBC connection pool giới hạn số connection, pool đó thường đã đóng vai trò điều tiết việc truy cập database; không thêm semaphore trùng lặp nếu không có một giới hạn khác cần bảo vệ.

## 8. Tách tác vụ I/O-bound và CPU-bound

Virtual thread phù hợp với nhiều tác vụ chờ I/O như gọi HTTP, đọc socket hoặc truy vấn database. Chúng không làm CPU chạy nhanh hơn và không tạo thêm lõi xử lý.

Với công việc CPU-bound kéo dài như nén dữ liệu, mã hóa hoặc tính toán lớn:

- Số tác vụ thực thi đồng thời vẫn bị giới hạn bởi số CPU khả dụng.
- Tạo quá nhiều tác vụ CPU-bound có thể làm tăng tranh chấp CPU, bộ nhớ và chi phí lập lịch.
- Dùng executor có parallelism được giới hạn theo tài nguyên CPU nếu cần kiểm soát số phép tính đang chạy.

Có thể dùng virtual thread để điều phối một request gồm nhiều bước I/O và một bước tính toán, nhưng nên kiểm soát riêng phần tính toán nặng. Đừng kỳ vọng tăng số virtual thread sẽ làm throughput CPU-bound tăng tuyến tính.

## 9. Đo bộ nhớ và số tác vụ trong môi trường thực tế

Không có công thức chung để suy ra chính xác số virtual thread tối đa chỉ từ heap size. Hãy đo với workload đại diện, gồm cả thời gian chờ, kích thước request, độ sâu call stack và số object được giữ trong lúc chờ.

Các điểm nên quan sát:

- Heap used, allocation rate, GC frequency và thời gian GC.
- Số request đang được xử lý, số request đang chờ và thời gian sống trung bình của mỗi tác vụ.
- Số kết nối database, socket, file descriptor và lượng buffer đang được giữ.
- Các ThreadLocal hoặc context object được tạo theo từng virtual thread.
- Sự kiện virtual thread start/end và lỗi khi submit/unpark.

Java Flight Recorder trong Java 21 có các sự kiện liên quan:

| Sự kiện | Ý nghĩa |
|---|---|
| jdk.VirtualThreadStart | Virtual thread bắt đầu |
| jdk.VirtualThreadEnd | Virtual thread kết thúc |
| jdk.VirtualThreadPinned | Virtual thread bị pin lâu hơn ngưỡng sự kiện |
| jdk.VirtualThreadSubmitFailed | Không thể submit hoặc unpark virtual thread, thường do thiếu tài nguyên |

jdk.VirtualThreadStart và jdk.VirtualThreadEnd bị tắt mặc định. jdk.VirtualThreadPinned được bật mặc định với ngưỡng 20 ms trong cấu hình JFR tiêu chuẩn của Java 21.

Có thể tạo thread dump chứa cả virtual thread bằng:

~~~bash
jcmd <PID> Thread.dump_to_file -format=json threads.json
~~~

Dùng thread dump để tìm tác vụ đang chờ, call stack sâu hoặc nhiều thread bị kẹt ở cùng một điểm. Kết hợp JFR và heap/GC metrics để biết bộ nhớ tăng do stack, task context, buffer hay object cache.

Khi ước lượng năng lực, nên chạy thử theo từng mức tải tăng dần và ghi nhận heap tại trạng thái ổn định. Không dùng một con số “triệu virtual thread” làm cam kết capacity cho mọi ứng dụng.

## 10. Lưu ý theo phiên bản runtime

Một số giới hạn lập lịch phụ thuộc phiên bản JDK đang chạy. Trên Java 21 đến Java 23, virtual thread thực hiện blocking operation trong synchronized block hoặc method có thể bị pin vào carrier, khiến carrier không được giải phóng trong lúc chờ. Điều này có thể làm giảm khả năng phục vụ nhiều tác vụ đồng thời nếu xảy ra thường xuyên và kéo dài.

Từ Java 24, JEP 491 thay đổi việc quản lý monitor để virtual thread có thể unmount khi blocking bên trong synchronized. Vì vậy, cảnh báo pinning do synchronized là lưu ý cụ thể cho runtime Java 21–23, không phải quy tắc chung cho các JDK mới hơn. Native method và foreign function vẫn có thể giữ virtual thread trên carrier.

Nếu ứng dụng chạy đúng Java 21, hãy đo pinning bằng JFR và đánh giá những vùng synchronized có blocking kéo dài. Nếu chạy JDK mới hơn, áp dụng hướng dẫn theo tài liệu của đúng phiên bản runtime.

## 11. Checklist thiết kế hệ thống nhiều virtual thread

- [ ] Xem mỗi virtual thread là một tác vụ riêng và tính số tác vụ còn sống, kể cả tác vụ đang chờ.
- [ ] Không nhân số virtual thread với kích thước native stack của platform thread để ước tính heap.
- [ ] Kiểm tra độ sâu call stack và dữ liệu mà biến local còn giữ khi tác vụ chờ.
- [ ] Tránh cache object lớn hoặc đắt tiền trong ThreadLocal nếu mỗi task tạo một virtual thread mới.
- [ ] Không tạo virtual thread pool; dùng executor một virtual thread cho mỗi task.
- [ ] Giới hạn tài nguyên downstream bằng semaphore, connection pool hoặc rate limiter.
- [ ] Đặt admission control/backpressure để không tạo số lượng tác vụ đang chờ vượt quá khả năng bộ nhớ.
- [ ] Dùng giới hạn parallelism phù hợp cho công việc CPU-bound.
- [ ] Đo heap, GC, task lifetime, JFR và thread dump dưới tải thực tế.
- [ ] Kiểm tra hành vi pinning theo đúng phiên bản JDK đang triển khai.

## Tài liệu tham khảo chính thức

- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [Java SE 21 API — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Java SE 21 API — Thread.Builder.OfVirtual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21 API — Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Oracle Java 21 Core Libraries — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)

