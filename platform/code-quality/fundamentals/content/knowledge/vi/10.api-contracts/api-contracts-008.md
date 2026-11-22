# Làm rõ thao tác chặn, bất đồng bộ và hủy

Một API có thể trả kết quả đúng trong điều kiện bình thường nhưng vẫn gây lỗi nghiêm trọng khi người dùng không hiểu **lời gọi có chặn hay không**, **tác vụ thực sự hoàn thành lúc nào** hoặc **việc hủy có dừng tác dụng phụ đang diễn ra hay không**. Chẳng hạn, một hàm trả về ngay một **Future** không đồng nghĩa dữ liệu đã được lưu; một lần **get()** hết thời gian chờ không đồng nghĩa công việc phía sau đã dừng; một yêu cầu hủy thanh toán không có nghĩa khoản tiền chắc chắn chưa bị thu.

Trong chương **Hợp đồng API** của module **CODE_QUALITY_FUNDAMENTALS**, việc mô tả rõ các tính chất này giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Người gọi cần biết mình được bảo đảm điều gì để không vô tình chặn luồng quan trọng, giải phóng tài nguyên quá sớm, retry gây tác dụng phụ trùng hoặc báo kết quả thành công trước thời điểm thực sự hoàn tất.

## 1. Hợp đồng API không chỉ là kiểu tham số và kiểu trả về

Khi đọc một chữ ký như sau:

~~~java
Future<StockSnapshot> loadAsync(String sku);
~~~

Ta có thể biết phương thức trả một **Future** chứa kết quả **StockSnapshot**. Nhưng chỉ từ chữ ký này chưa thể khẳng định:

- Lời gọi **loadAsync** có thực sự trả về nhanh hay có thể chặn để chờ hàng đợi?
- Bước kiểm tra **sku** diễn ra ngay trong luồng gọi hay trong tác vụ phía sau?
- Công việc chạy trên executor nào và ai chịu trách nhiệm dừng executor?
- Khi không lấy được tồn kho, lỗi được ném lúc gọi hay xuất hiện trong Future?
- Khi gọi **cancel(true)**, công việc có ngừng và tài nguyên có được giải phóng không?
- Nếu bên gọi chờ quá hạn, công việc vẫn tiếp tục hay tự dừng?
- Có thể có tác dụng phụ hoặc ghi log ngay cả khi kết quả bị hủy không?

Đó là những thành phần của **hợp đồng hành vi** (*behavioral contract*). Hợp đồng đầy đủ làm rõ cả hành vi thành công, lỗi, thời gian chờ, khả năng hủy, tác động lên trạng thái và quyền sở hữu tài nguyên.

| Nội dung hợp đồng | Câu hỏi cần trả lời |
| --- | --- |
| Tiền điều kiện | Đầu vào null, rỗng, thời hạn âm hoặc dữ liệu không hợp lệ được xử lý ra sao? |
| Mô hình thực thi | Lời gọi chặn hay trả về một handle? Công việc chạy trên luồng nào? |
| Điểm hoàn thành | Trả về có nghĩa đã hoàn tất tính toán, đã commit dữ liệu hay chỉ đã nhận yêu cầu? |
| Lỗi | Lỗi ném đồng bộ, lưu trong Future hay truyền tới callback? Có thể thấy lỗi gốc không? |
| Timeout | Timeout giới hạn thời gian chờ của bên gọi hay thực sự giới hạn công việc phía sau? |
| Hủy | Hủy là yêu cầu dừng, đánh dấu kết quả hủy hay bảo đảm không có tác dụng phụ? |
| Thứ tự và đồng thời | Các lời gọi/callback có được thực hiện tuần tự hoặc đúng thứ tự nhận không? |
| Tài nguyên | Ai sở hữu executor, kết nối, stream, callback subscription và phải dọn dẹp? |
| Retry | Nếu kết quả chưa rõ, có được gọi lại không? Có khóa chống trùng hoặc idempotency key không? |

Một API tốt không nhất thiết bảo đảm mọi điều. Quan trọng là **không để người gọi suy đoán một bảo đảm mà API không cung cấp**.

## 2. Phân biệt đồng bộ, chặn, bất đồng bộ và không chặn

Các từ này có liên quan nhưng không đồng nghĩa.

### 2.1. Đồng bộ (*synchronous*)

Với API đồng bộ thông thường, bên gọi nhận kết quả hoặc lỗi trực tiếp trong cùng chuỗi lời gọi:

~~~java
StockSnapshot stock = inventory.loadBlocking("SKU-42");
display(stock);
~~~

Lời gọi thứ hai chỉ chạy sau khi lời gọi đầu kết thúc bình thường. Nếu tác vụ mất thời gian, luồng gọi thường phải chờ. Nhưng **đồng bộ** nói chủ yếu về cách phối hợp trả kết quả, không có nghĩa bắt buộc phải chờ I/O: một hàm tính toán thuần chạy ngay rồi trả về cũng là đồng bộ.

### 2.2. Chặn (*blocking*)

Một thao tác **chặn** làm luồng gọi không thể tiếp tục công việc phía sau cho đến khi thao tác trả về, bị ngắt hoặc thất bại. Khi chờ I/O, khóa hay kết quả một Future, luồng đó có thể phải đợi mà không làm công việc hữu ích.

Ví dụ:

~~~java
Future<StockSnapshot> future = inventory.loadAsync("SKU-42");
StockSnapshot stock = future.get(); // Luồng gọi có thể bị chặn.
display(stock);
~~~

Phương thức **loadAsync** có thể tạo công việc bất đồng bộ, nhưng gọi **future.get()** ngay sau đó có thể khiến **đường xử lý của bên gọi vẫn chặn**. Việc trả về Future không tự khiến toàn bộ chương trình vận hành theo cách không chặn.

### 2.3. Bất đồng bộ (*asynchronous*)

Một API **bất đồng bộ** tách thời điểm **khởi tạo** công việc khỏi thời điểm **nhận kết quả cuối**. Lời gọi ban đầu thường trả về một handle, Future, callback registration hoặc đối tượng mô tả một tiến trình đang diễn ra.

~~~java
CompletableFuture<StockSnapshot> future =
        inventory.loadAsync("SKU-42");

future.thenAccept(this::display);
// Luồng gọi có thể tiếp tục xử lý việc khác.
~~~

Đoạn mã này chỉ mang tính minh họa với một API trả **CompletableFuture**. Kết quả chưa chắc đã sẵn sàng ngay khi đăng ký callback, và việc đăng ký callback cũng không chứng minh tác vụ đã bắt đầu trên luồng riêng.

### 2.4. Không chặn (*non-blocking*)

**Không chặn** mô tả cơ chế thực thi không phải giữ một luồng chờ cho một thao tác chưa sẵn sàng, thường dựa trên cơ chế thông báo khi I/O có thể tiếp tục hoặc khi dữ liệu đến.

Lưu ý sự khác biệt:

- **Bất đồng bộ nhưng dùng I/O chặn:** đưa một lời gọi JDBC chặn vào thread pool rồi trả **Future**. Luồng gọi trả về sớm, nhưng một worker vẫn bị chặn để chờ cơ sở dữ liệu.
- **Bất đồng bộ và I/O không chặn:** một client mạng hỗ trợ cơ chế xử lý khi dữ liệu sẵn sàng mà không cần giữ riêng một worker đợi mỗi lời gọi.
- **Đồng bộ và không cần I/O:** một phép cộng trả kết quả trực tiếp; việc gọi là đồng bộ nhưng không đồng nghĩa có chờ tài nguyên ngoài.

Không nên quảng bá một API là **non-blocking** chỉ vì chữ ký có **CompletableFuture**. Cần kiểm tra điều gì xảy ra trong phần triển khai và những cơ chế chờ mà nó sử dụng.

## 3. Điểm hoàn thành: “đã nhận” khác “đã làm xong”

Giả sử một API nhận yêu cầu tạo báo cáo và trả HTTP **202 Accepted**. Trong nhiều thiết kế, mã này thể hiện **yêu cầu đã được chấp nhận để xử lý**, không phải báo cáo đã được tạo thành công.

~~~text
T0: Client gọi createReport
T1: Server xác thực và nhận yêu cầu
T2: Server trả trạng thái ACCEPTED + jobId
T3: Worker bắt đầu tạo báo cáo
T4: Worker ghi tệp và metadata
T5: Công việc chuyển sang SUCCEEDED hoặc FAILED
~~~

Nếu client xem T2 là T5, nó có thể chuyển người dùng đến một tệp chưa tồn tại. API cần phân biệt:

| Mốc | Ý nghĩa |
| --- | --- |
| Đã nhận | Server đã tiếp nhận thông điệp hoặc yêu cầu |
| Đã xếp hàng | Công việc đã được lưu hoặc đưa vào hàng đợi theo bảo đảm cụ thể |
| Đang thực thi | Worker bắt đầu xử lý, chưa có kết quả cuối |
| Đã hoàn tất thành công | Kết quả và tác dụng phụ thuộc hợp đồng đã đạt điều kiện thành công |
| Đã thất bại | Công việc không đạt mục tiêu; có thể còn kết quả trung gian |
| Có yêu cầu hủy | Hệ thống đã nhận yêu cầu dừng, chưa chắc đã dừng thực tế |
| Đã hủy theo hợp đồng | Công việc không còn tiếp tục theo trạng thái hệ thống; tác dụng phụ trước đó có thể vẫn tồn tại |

Để làm rõ hơn, một API tác vụ dài có thể cung cấp **jobId** và trạng thái **PENDING**, **RUNNING**, **SUCCEEDED**, **FAILED**, **CANCEL_REQUESTED**, **CANCELLED**. Đây chỉ là mô hình ví dụ; các hệ thống khác có thể gộp bớt trạng thái hoặc cần thêm **UNKNOWN** khi kết quả của dịch vụ bên ngoài chưa được đối soát.

Phải định nghĩa **SUCCEEDED** theo nghiệp vụ. Với ghi dữ liệu, điều đó có thể là đã commit thành công; với gửi email, có thể chỉ là nhà cung cấp đã chấp nhận thông điệp, **không** có nghĩa người nhận đã đọc email.

## 4. Ví dụ Java: định nghĩa hai API đồng bộ và bất đồng bộ

Giả sử có một cổng đọc tồn kho. Để tập trung vào hợp đồng, phần truy cập thực tế đến kho dữ liệu được đại diện bằng một interface.

### 4.1. Gateway và kết quả có hợp đồng rõ

~~~java
import java.io.IOException;

public interface StockGateway {
    StockSnapshot fetch(String sku)
            throws IOException, InterruptedException;
}
~~~

~~~java
public record StockSnapshot(String sku, int available) {
    public StockSnapshot {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is blank");
        }
        if (available < 0) {
            throw new IllegalArgumentException("Negative stock");
        }
    }
}
~~~

**StockGateway.fetch** là một API trừu tượng: triển khai cụ thể có thể chờ mạng hoặc cơ sở dữ liệu, có thể ném **IOException**, và được thiết kế để có khả năng phản hồi **InterruptedException** khi việc chờ hỗ trợ ngắt. Chữ ký **không tự bảo đảm** rằng mọi thư viện I/O bên dưới đều ngắt được ngay.

### 4.2. Lớp công khai cả hai cách sử dụng

~~~java
import java.io.IOException;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;

public final class StockQueries {
    private final StockGateway gateway;
    private final ExecutorService executor;

    public StockQueries(
            StockGateway gateway, ExecutorService executor) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.executor = Objects.requireNonNull(executor, "executor");
    }

    public StockSnapshot loadBlocking(String sku)
            throws IOException, InterruptedException {
        return gateway.fetch(validateSku(sku));
    }

    public Future<StockSnapshot> loadAsync(String sku) {
        String validSku = validateSku(sku);
        return executor.submit(() -> gateway.fetch(validSku));
    }

    private static String validateSku(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is blank");
        }
        return sku;
    }
}
~~~

Hai phương thức cùng lấy một dữ kiện nhưng có **hợp đồng thực thi khác nhau**:

| Thuộc tính | loadBlocking | loadAsync |
| --- | --- | --- |
| Thời điểm thực hiện gateway.fetch | Trong luồng gọi | Trong một tác vụ gửi vào executor |
| Kết quả trả về trực tiếp | StockSnapshot | Future chứa kết quả có thể đến sau |
| Kiểm tra sku | Trước khi gọi gateway | Ngay trong lời gọi loadAsync, trước submit |
| Lỗi từ gateway | IOException/InterruptedException ném khi gọi | Được lưu trong Future và xuất hiện qua ExecutionException khi get |
| Executor từ bên ngoài | Không sử dụng | Do bên khởi tạo StockQueries cung cấp |
| Hủy công việc | Bên gọi có thể ngắt thread đang chờ theo hợp đồng gateway | Bên gọi có thể yêu cầu Future.cancel |

### 4.3. Những chi tiết thường bị hiểu sai

**Kiểm tra đầu vào có thể thất bại đồng bộ.** Mặc dù **loadAsync** trả Future, lời gọi **validateSku** chạy trước **executor.submit**, nên có thể ném **IllegalArgumentException** ngay. Nếu executor từ chối nhận việc, **submit** có thể ném **RejectedExecutionException** ngay trong lời gọi.

**Lỗi thực thi đến ở thời điểm khác.** Khi **gateway.fetch** ném IOException trong worker, **Future.get()** thường ném **ExecutionException** mà **getCause()** chứa ngoại lệ gốc. **get()** cũng có thể ném **InterruptedException** khi chính luồng đang chờ bị ngắt; đó không nhất thiết là lỗi của công việc bên trong.

**Executor có chủ sở hữu riêng.** Trong ví dụ, **StockQueries** chỉ mượn executor được truyền vào, không tự shutdown nó khi một yêu cầu kết thúc. Thành phần tạo và quản lý executor chịu trách nhiệm vòng đời theo kiến trúc ứng dụng.

**Bất đồng bộ không đồng nghĩa tự có timeout.** Nếu **gateway.fetch** chờ vô hạn và không có timeout bên dưới, worker có thể bị giữ lâu dù bên gọi đã ngừng đợi.

**Chạy trên executor không đồng nghĩa chạy ngay.** Công việc có thể phải xếp hàng; nếu hàng đợi đã đầy hoặc executor đóng, hành vi từ chối cần được mô tả rõ.

## 5. Timeout: chờ quá hạn không phải hủy công việc

Một trong những lỗi hợp đồng phổ biến nhất là hiểu **TimeoutException** theo nghĩa công việc chắc chắn đã dừng.

### 5.1. Timeout của Future.get

~~~java
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

Future<StockSnapshot> pending = queries.loadAsync("SKU-42");

try {
    StockSnapshot result = pending.get(300, TimeUnit.MILLISECONDS);
    use(result);
} catch (TimeoutException timeout) {
    reportSlowOperation();
    // Tác vụ có thể vẫn đang chạy trong executor.
}
~~~

**pending.get(300, MILLISECONDS)** giới hạn **khoảng thời gian luồng gọi chờ kết quả**. Nếu quá hạn:

- **get** ném TimeoutException.
- **Future** không tự bị hủy chỉ vì lần **get** này hết hạn.
- Worker có thể tiếp tục làm việc, sau đó hoàn thành bình thường hoặc thất bại.
- Bên gọi có thể thử **get** lại hoặc đưa ra quyết định hủy rõ ràng.

Trong ví dụ, **queries**, **use** và **reportSlowOperation** là những thành phần minh họa của ứng dụng, không phải một chương trình hoàn chỉnh.

### 5.2. Timeout của I/O hoặc công việc

Để giới hạn thời gian chờ mạng, truy vấn hoặc khóa, có thể cần **timeout ở client I/O**, **statement timeout**, timeout khi lấy connection từ pool hoặc cơ chế deadline được triển khai bởi thành phần thực thi.

| Loại giới hạn | Thường tác động lên | Điều không tự bảo đảm |
| --- | --- | --- |
| get(timeout) | Thời gian bên gọi chờ Future | Tác vụ phía sau đã bị dừng |
| Timeout của kết nối hoặc đọc mạng | Thời gian chờ một giai đoạn I/O | Mọi giai đoạn của nghiệp vụ đều hoàn thành trước hạn |
| Timeout truy vấn DB | Thời gian cơ sở dữ liệu cho phép truy vấn theo cấu hình | Giao dịch hoặc các dịch vụ khác đã được xử lý nhất quán |
| Deadline toàn quy trình | Ngân sách thời gian cho chuỗi bước theo thiết kế | Tác dụng phụ đã gửi ra ngoài chắc chắn được hoàn tác |

Giới hạn 500 ms cho **mỗi** lời gọi của bốn dịch vụ liên tiếp vẫn có thể tạo thời gian chờ lớn hơn 500 ms cho toàn bộ yêu cầu. Khi có mục tiêu **thời gian toàn quy trình**, cần xét ngân sách thời gian còn lại cho các bước kế tiếp và các chi phí ngoài từng lời gọi.

### 5.3. CompletableFuture.orTimeout

~~~java
CompletableFuture<StockSnapshot> future =
        CompletableFuture.supplyAsync(
                () -> blockingLoad("SKU-42"), executor);

future.orTimeout(300, TimeUnit.MILLISECONDS);
~~~

**blockingLoad** và **executor** là các thành phần minh họa. **orTimeout** làm CompletableFuture hoàn tất đặc biệt với **TimeoutException** nếu chưa hoàn thành khi hết hạn, nhưng **không bảo đảm tác vụ blockingLoad phía sau bị ngắt hoặc dừng**. Cũng cần lưu ý phương thức **orTimeout** tác động lên chính CompletableFuture được gọi, không tạo một tác vụ mạng có timeout thực thi tự động.

Với các thao tác có tác dụng phụ, sự khác nhau giữa **“bên gọi không nhận được kết quả đúng hạn”** và **“tác vụ chưa từng thực hiện”** đặc biệt quan trọng.

## 6. Hủy: kết quả bị hủy khác với tác vụ thực sự đã dừng

Hủy (*cancellation*) là một yêu cầu hoặc sự kiện cần được diễn giải theo hợp đồng. Có thể phân biệt:

1. **Yêu cầu hủy đã được gửi.**
2. **Bên thực thi đã nhận hoặc đánh dấu hủy.**
3. **Công việc đã ngừng chạy và giải phóng tài nguyên.**
4. **Tác dụng phụ nghiệp vụ đã được kiểm tra, bù trừ hoặc xác nhận trạng thái cuối.**

Không được coi bốn mốc đó là một.

### 6.1. Future.cancel(boolean)

Với **Future** từ **ExecutorService.submit**, bên gọi có thể yêu cầu hủy:

~~~java
Future<StockSnapshot> future = queries.loadAsync("SKU-42");
boolean cancellationAccepted = future.cancel(true);
~~~

Ý nghĩa quan trọng:

- **cancel(true)** cố gắng hủy tác vụ; nếu tác vụ đang chạy, cơ chế thực thi có thể yêu cầu ngắt thread.
- **cancel(false)** không yêu cầu ngắt công việc đang chạy theo hợp đồng của Future; công việc chưa bắt đầu có thể được ngăn khởi chạy.
- Giá trị trả về **true** thể hiện yêu cầu hủy Future thành công theo ngữ nghĩa của triển khai; không chứng minh mọi tác dụng phụ bên ngoài đã bị hoàn tác.
- Nếu Future được đánh dấu đã hủy, các lần **get()** sau đó ném **CancellationException**.
- Nếu tác vụ đã hoàn tất trước khi hủy, yêu cầu hủy có thể không còn hiệu lực.

Điểm mấu chốt: **cancellationAccepted** không phải cờ **“đã hoàn tác công việc”**.

### 6.2. Ngắt thread là hợp tác, không phải cưỡng bức an toàn

Java sử dụng cơ chế **interruption** để yêu cầu một thread lưu ý việc ngắt. Một số thao tác chờ như **Thread.sleep**, **Object.wait** và **CountDownLatch.await** phản hồi bằng **InterruptedException**. Các đoạn tính toán CPU cần chủ động kiểm tra trạng thái ngắt hoặc dùng cơ chế hủy phù hợp.

~~~java
public long sumUntilCancelled(long[] values)
        throws InterruptedException {
    long sum = 0;
    for (int index = 0; index < values.length; index++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Calculation interrupted");
        }
        sum = Math.addExact(sum, values[index]);
    }
    return sum;
}
~~~

Ví dụ này kiểm tra trạng thái ngắt định kỳ trong vòng lặp. Nó có thể dừng trước khi hoàn thành tính toán nếu phát hiện yêu cầu ngắt. **Không nên tự ý dừng một tác vụ giữa các thay đổi không thể hoàn tác** mà không có thiết kế xử lý trạng thái trung gian.

### 6.3. Không nuốt InterruptedException

~~~java
try {
    blockingOperation();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Operation interrupted", interrupted);
}
~~~

Ở đây **blockingOperation** là phương thức minh họa có thể ném InterruptedException. Nếu không thể truyền **InterruptedException** lên trên vì hợp đồng phương thức, việc **khôi phục cờ ngắt** giúp tầng cao hơn có cơ hội nhận biết yêu cầu ngắt. Nếu phương thức có thể khai báo **throws InterruptedException**, thường nên truyền ngoại lệ để bên gọi quyết định cách xử lý.

Việc bắt InterruptedException rồi bỏ qua, tiếp tục chạy như không có gì xảy ra có thể khiến **cancel(true)** không đạt mục tiêu và tài nguyên tiếp tục bị giữ.

### 6.4. Hủy CompletableFuture không đồng nghĩa ngắt worker

~~~java
CompletableFuture<StockSnapshot> future =
        CompletableFuture.supplyAsync(
                () -> blockingLoad("SKU-42"), executor);

future.cancel(true);
~~~

Đối với **CompletableFuture**, tham số **mayInterruptIfRunning** của **cancel** không điều khiển ngắt tác vụ nền theo cách của một số Future do ExecutorService quản lý. **cancel(true)** hoàn tất Future ở trạng thái hủy, nhưng không bảo đảm tác vụ đang chạy bên trong **supplyAsync** bị ngắt.

Nếu cần hủy hoạt động nền thực sự, thiết kế có thể phải quản lý một **Future** của tác vụ bên dưới, một **cancellation token** được kiểm tra hợp tác, hoặc sử dụng API I/O có hỗ trợ hủy riêng. Cần tài liệu hóa rõ **hủy phần kết quả** và **hủy phần thực thi**.

## 7. Định nghĩa trạng thái và kết quả khi hủy

Với công việc chỉ tính toán trong bộ nhớ và chưa tạo tác dụng phụ, hủy thường khá đơn giản: ngừng tính, không xuất bản kết quả.

Với công việc đã gọi hệ thống bên ngoài, hủy có thể đến quá muộn. Ví dụ:

~~~text
T0: Tạo yêu cầu thanh toán
T1: Gửi lệnh thu tiền tới cổng thanh toán
T2: Client hết thời gian chờ hoặc bấm "Hủy"
T3: Cổng thanh toán trả kết quả thành công
T4: Server ghi nhận và đối soát khoản thu
~~~

Nếu client hủy ở T2, không thể suy ra khoản thu chưa xảy ra. API nên có trạng thái hoặc cơ chế đối soát phù hợp, thay vì trả một kết luận sai như **“đã hủy nên không bị trừ tiền”**.

| Loại tác vụ | Hủy có thể có nghĩa gì? | Điều cần làm rõ |
| --- | --- | --- |
| Tính báo giá thuần | Ngừng tính và bỏ kết quả | Không có tác dụng phụ trước đó |
| Đọc dữ liệu mạng | Không chờ kết quả nữa; có thể yêu cầu đóng kết nối | Kết nối có dừng được không, có giải phóng pool không? |
| Tạo báo cáo | Dừng ghi và dọn tệp tạm | Có giữ báo cáo một phần để tiếp tục không? |
| Gửi email | Dừng trước khi gửi nếu còn kịp | Nếu nhà cung cấp đã nhận, không thể “thu hồi” theo giả định |
| Thanh toán | Yêu cầu hủy hoặc hoàn tiền theo quy trình riêng | Kết quả chưa rõ cần đối soát, không suy đoán |
| Công việc theo lô | Dừng nhận thêm phần tử mới tại điểm an toàn | Các phần tử đã commit vẫn tồn tại theo hợp đồng |

Một hợp đồng hủy có thể nói rõ: **“Hệ thống ngừng nhận công việc mới sau khi thấy yêu cầu hủy; các phần đã commit sẽ không tự rollback; phần chưa bắt đầu sẽ không được chạy.”** Đây là bảo đảm thực tế hơn một tuyên bố chung chung như **“hủy sẽ dừng ngay mọi việc”**.

## 8. Tác dụng phụ, retry và tính lặp an toàn

**Retry** thường xuất hiện sau timeout hoặc lỗi mạng. Nhưng cùng một yêu cầu có thể đã thành công ở hệ thống đích, chỉ có phản hồi bị mất.

~~~text
Client              Server              Cổng thanh toán
  | -- pay(key=A) --> | -- charge(A) ----> |
  |                   | <--- success ----- |
  |       (mất kết nối trước phản hồi)      |
  | -- pay(key=A) --> |                     |
~~~

Nếu server coi lần gọi thứ hai là lệnh thu tiền mới, có nguy cơ tính tiền trùng. API cần quy định **ngữ nghĩa retry** và, khi phù hợp, dùng **idempotency key** ổn định cho một ý định nghiệp vụ.

Ví dụ hợp đồng:

- Cùng **idempotency key** và cùng nội dung yêu cầu chỉ tương ứng một giao dịch thanh toán trong phạm vi bảo đảm của hệ thống.
- Yêu cầu trùng key có thể nhận lại kết quả đã lưu hoặc trạng thái đang xử lý.
- Dùng lại cùng key cho một yêu cầu khác phải bị từ chối hoặc giải quyết theo quy tắc rõ ràng.
- Việc kiểm tra và ghi nhận key phải chống được yêu cầu đồng thời, chẳng hạn bằng unique constraint, giao dịch hoặc cập nhật nguyên tử.
- Phải nêu rõ phạm vi tồn tại và thời hạn lưu của key; không ngầm hứa bảo vệ vĩnh viễn.

Hủy ở tầng Future không thay thế cơ chế idempotency ở tầng nghiệp vụ. Một Future đã bị đánh dấu hủy vẫn có thể đại diện cho thao tác bên ngoài đã thực hiện.

## 9. Dọn dẹp tài nguyên và vòng đời tác vụ

Khi một lời gọi bị ngắt hoặc được yêu cầu hủy, việc **giải phóng tài nguyên** có thể quan trọng như việc trả kết quả.

### 9.1. Tài nguyên do tác vụ sở hữu

~~~java
public byte[] readFile(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input.readAllBytes();
    }
}
~~~

Ví dụ này sử dụng các kiểu **Path**, **Files**, **InputStream** và **IOException** trong Java; giả định tệp đủ nhỏ để đọc vào bộ nhớ. **Try-with-resources** bảo đảm cố gắng đóng stream khi phương thức thoát bình thường hoặc bằng ngoại lệ.

Nếu một tác vụ bất đồng bộ mở stream, thường nên để **tác vụ đó sở hữu và đóng stream**. Không nên mở stream trong lời gọi ban đầu rồi đóng ngay sau khi submit nếu worker vẫn cần đọc.

### 9.2. Một tác vụ hủy không được làm rò rỉ giấy phép hoặc khóa

~~~java
Semaphore permits = new Semaphore(4);

public void processOne() throws InterruptedException {
    permits.acquire();
    try {
        performInterruptibleWork();
    } finally {
        permits.release();
    }
}
~~~

Ví dụ dùng **Semaphore**, với **performInterruptibleWork** là phương thức minh họa. Nếu bị ngắt **trước khi acquire thành công**, khối try chưa bắt đầu và không được release. Nếu đã lấy giấy phép, **finally** trả lại giấy phép kể cả khi tác vụ bị ngắt trong khi xử lý.

Với **Lock**, quy tắc tương tự là chỉ **unlock** khi thực sự nắm giữ khóa. Với cơ sở dữ liệu, cần phân biệt **rollback giao dịch** và **đóng/trả kết nối**; một yêu cầu hủy không tự cung cấp rollback cho các tác dụng phụ ngoài giao dịch.

### 9.3. Quyền sở hữu executor

API nhận một **ExecutorService** từ bên ngoài thường **không được tự đóng executor đó** khi một lời gọi hoặc một Future kết thúc. Executor có thể phục vụ nhiều thành phần. Ngược lại, thành phần **tự tạo** executor riêng phải quy định shutdown, chờ dừng và xử lý công việc chưa hoàn tất khi đóng vòng đời.

Timeout, hủy và shutdown có thể xảy ra đồng thời. Hợp đồng cần nói rõ điều gì xảy ra với tác vụ đang xếp hàng, tác vụ đang chạy và tác vụ đã kết thúc.

## 10. Trạng thái và ngoại lệ trong Future

Với một **Future** thông thường, có thể hình dung các tình huống:

~~~text
SUBMITTED ----> RUNNING ----> COMPLETED
    |              |               |
    |              |               +-- get() trả kết quả
    |              |
    |              +-----------> FAILED
    |                                |
    |                                +-- get() ném ExecutionException
    |
    +--------------------------> CANCELLED
                  (cũng có thể yêu cầu hủy khi RUNNING)
                                     |
                                     +-- get() ném CancellationException
~~~

Sơ đồ mô tả **trạng thái quan sát được của Future**, không phải một máy trạng thái đầy đủ của tất cả công việc bên dưới. Khi Future đã **CANCELLED**, tác vụ nền có thể vẫn phải dọn dẹp hoặc vẫn tiếp tục chạy nếu không phản hồi được yêu cầu hủy.

Đối với **CompletableFuture**:

- **get()** thường bọc lỗi hoàn thành vào **ExecutionException**; **get()** có thể bị ngắt.
- **join()** không yêu cầu khai báo checked exception, thường truyền lỗi dưới dạng **CompletionException** hoặc **CancellationException**.
- Callback có thể thực thi trên thread hoàn thành Future hoặc thread đăng ký callback trong một số tình huống; không nên tự đoán thread thực thi callback dạng không có hậu tố **Async**.
- Các phương thức **thenApplyAsync**, **thenAcceptAsync** có thể nhận executor rõ ràng; việc chọn executor và phạm vi truy cập trạng thái chung là một phần của thiết kế.

Khi callback thay đổi UI, dữ liệu dùng chung hoặc gọi API khác, nên xác định rõ nơi callback chạy, thứ tự tương tác và cách xử lý lỗi. Không nên chỉ dựa vào hậu tố **Async** để kết luận rằng mã không thể gặp race condition.

## 11. Kiểm thử hợp đồng chặn, timeout và hủy

Kiểm thử chỉ xác nhận đường thành công không cho biết API xử lý những tình huống khó. Cần có các ca chủ động điều phối thời điểm.

### 11.1. Timeout của get không tự hủy Future

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;

class FutureTimeoutTest {
    @Test
    void waitingTimeoutDoesNotCancelTheTask() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch allowFinish = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                allowFinish.await();
                return "done";
            });

            assertThrows(TimeoutException.class,
                    () -> future.get(30, TimeUnit.MILLISECONDS));
            assertFalse(future.isCancelled());

            allowFinish.countDown();
            assertEquals("done", future.get(2, TimeUnit.SECONDS));
        } finally {
            allowFinish.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

Ví dụ dùng **CountDownLatch** thay vì trông chờ Thread.sleep để kiểm soát khi nào tác vụ được phép hoàn thành. Bài kiểm thử chỉ chứng minh đặc tính của **Future.get(timeout)**, chưa kiểm chứng timeout của một thư viện HTTP hoặc cơ sở dữ liệu.

### 11.2. Cancel có thể ngắt một tác vụ hợp tác

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class FutureCancellationTest {
    @Test
    void cancellationInterruptsAnInterruptibleWait() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                try {
                    new CountDownLatch(1).await();
                    return "unexpected";
                } finally {
                    finished.countDown();
                }
            });

            assertTrue(started.await(2, TimeUnit.SECONDS));
            assertTrue(future.cancel(true));
            assertThrows(CancellationException.class, future::get);
            assertTrue(finished.await(2, TimeUnit.SECONDS));
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Ở ví dụ này, tác vụ chờ tại **CountDownLatch.await()**, là thao tác có khả năng phản hồi interruption. Vì thế **cancel(true)** có cơ hội ngắt và đưa tác vụ vào **finally**. Kết quả kiểm thử **không thể suy rộng** thành bảo đảm rằng mọi network client, JDBC driver hoặc đoạn mã tính toán không kiểm tra ngắt sẽ luôn dừng kịp thời.

### 11.3. Ma trận kiểm thử cần có

| Tình huống | Điều nên kiểm chứng |
| --- | --- |
| Đầu vào không hợp lệ | Lỗi đồng bộ hay lỗi trong Future theo hợp đồng? |
| Executor từ chối công việc | API ném lỗi ngay, trả Future thất bại hay thực hiện chính sách khác? |
| Tác vụ thành công | Kết quả đúng và điều kiện thành công đã thật sự đạt? |
| Tác vụ lỗi | Người gọi nhận được nguyên nhân; tài nguyên được dọn đúng? |
| get(timeout) hết hạn | Bên gọi dừng chờ; trạng thái công việc bên dưới được hiểu đúng? |
| Hủy trước khi bắt đầu | Tác dụng phụ chưa xảy ra theo bảo đảm cụ thể? |
| Hủy khi đang chạy | Tác vụ hợp tác dừng tại điểm an toàn; tài nguyên được giải phóng? |
| Hủy và hoàn thành tranh chấp | Kết quả quan sát phù hợp với quy tắc đã công bố? |
| Hủy sau tác dụng phụ | Không báo sai rằng tác dụng phụ chưa từng diễn ra? |
| Client retry sau timeout | Không tạo tác dụng phụ trùng nếu hợp đồng yêu cầu idempotency? |
| Shutdown executor | Công việc đang xếp hàng và đang chạy được xử lý theo chính sách? |

Kiểm thử có thể chứng minh một số lịch chạy cụ thể. Với vấn đề đồng thời, cần kết hợp kiểm thử điều phối, phân tích các điểm tranh chấp, giới hạn tài nguyên và quan sát vận hành thay vì tin rằng một lần chạy xanh loại bỏ toàn bộ race condition.

## 12. Mẫu tài liệu hóa hợp đồng API

Với một API bất đồng bộ thực tế, có thể mô tả hợp đồng bằng một bảng ngắn ngay cạnh chữ ký:

| Mục | Hợp đồng minh họa của loadAsync |
| --- | --- |
| Đầu vào | sku phải khác null và không rỗng; kiểm tra ngay khi gọi |
| Khởi tạo | Tạo tác vụ trên executor được truyền vào; có thể bị từ chối ngay |
| Hoàn thành thành công | Future có StockSnapshot hợp lệ khi gateway.fetch trả kết quả |
| Lỗi | Lỗi khi chạy tác vụ được quan sát khi get; nguyên nhân có thể truy cập qua getCause |
| Chờ | get() có thể chặn; get(timeout) chỉ giới hạn thời gian chờ của bên gọi |
| Hủy | cancel(true) gửi yêu cầu hủy/ngắt theo khả năng executor và gateway; không bảo đảm dừng I/O ngay |
| Tác dụng phụ | API thiết kế để đọc tồn kho; không hứa rằng hệ thống ngoài không có log hoặc hoạt động quan sát |
| Tài nguyên | Executor do bên tạo/sở hữu quản lý; gateway đóng tài nguyên của riêng mỗi lượt đọc |
| Thứ tự | Không bảo đảm hai lời gọi loadAsync hoàn thành theo thứ tự gửi |

Một lời mô tả ngắn nhưng chính xác thường hữu ích hơn các từ mơ hồ như **“async hoàn toàn”**, **“cancel ngay lập tức”** hoặc **“timeout sẽ rollback”**.

Khi dùng Javadoc, hãy nói trực tiếp phần liên quan tới người gọi. Ví dụ:

~~~java
/**
 * Submits a stock read to the injected executor.
 *
 * <p>Validates sku before submission and may throw
 * IllegalArgumentException or RejectedExecutionException immediately.
 *
 * <p>The returned Future completes with the stock snapshot or a failure.
 * Calling get(timeout, unit) limits caller waiting only.
 * Cancellation is best-effort and depends on the gateway's
 * interruption support; it does not guarantee network work has stopped.
 *
 * <p>This class does not own or shut down the injected executor.
 */
public Future<StockSnapshot> loadAsync(String sku);
~~~

Đoạn trên là **mẫu chữ ký và tài liệu hợp đồng**, không phải khai báo một phương thức có thân trong một lớp cụ thể. Khi đưa vào Java thật, đặt nó tại interface hoặc khai báo phù hợp với phần triển khai.

## 13. Những hiểu nhầm thường gặp

**“Có Future là không chặn.”** Future chỉ là cách biểu diễn kết quả có thể xuất hiện trong tương lai. Gọi **get()** ngay vẫn có thể chặn; tác vụ nền cũng có thể sử dụng I/O chặn.

**“Phương thức async không thể ném lỗi ngay.”** Kiểm tra đầu vào và việc gửi tác vụ có thể thất bại đồng bộ. Lỗi phát sinh trong worker thường đến muộn qua Future.

**“TimeoutException nghĩa là tác vụ đã dừng.”** Với **Future.get(timeout)**, chỉ việc chờ đã hết hạn. Tác vụ có thể vẫn chạy và tạo tác dụng phụ.

**“cancel(true) bảo đảm không có tác dụng phụ.”** Hủy không quay ngược những thao tác đã commit hoặc những yêu cầu đã được hệ thống khác tiếp nhận.

**“Hủy CompletableFuture sẽ ngắt supplyAsync.”** Hủy CompletableFuture không mặc nhiên điều khiển worker như một FutureTask được submit trực tiếp. Cần cơ chế hủy thực thi riêng nếu nghiệp vụ yêu cầu.

**“Bắt InterruptedException rồi bỏ qua là an toàn.”** Nuốt tín hiệu ngắt khiến tác vụ tiếp tục chạy ngoài ý định; thường cần truyền ngoại lệ hoặc khôi phục trạng thái ngắt theo hợp đồng.

**“Callback luôn chạy ở luồng gọi hoặc luồng nền.”** Thread chạy callback phụ thuộc cách hoàn thành Future và loại thao tác callback; cần xác định executor rõ khi quan trọng.

**“Đã hủy thanh toán nên chắc chắn chưa thu tiền.”** Trạng thái của Future phía client không xác định kết quả của cổng thanh toán. Cần idempotency và đối soát kết quả chưa rõ.

## 14. Tình huống thực hành

Một API tạo hóa đơn dùng luồng sau:

~~~text
1. Client gọi POST /invoices
2. Server submit tác vụ tạo hóa đơn và trả jobId
3. Worker ghi hóa đơn vào DB
4. Worker gửi yêu cầu phát hành tới hệ thống ngoài
5. Worker cập nhật trạng thái SUCCEEDED
~~~

Client đặt timeout 2 giây và có nút **Hủy**. Tại giây thứ 2, client chưa có kết quả nên gửi lệnh hủy và sau đó thử lại POST với dữ liệu cũ. Tuy nhiên, worker có thể đã ghi hóa đơn ở bước 3 và hệ thống bên ngoài đã nhận lệnh ở bước 4.

Hãy trả lời:

1. POST trả **jobId** nghĩa là hệ thống đã cam kết kết quả nghiệp vụ nào, và điều gì vẫn chưa được bảo đảm?
2. Nếu client hết thời gian chờ, có đủ cơ sở để kết luận hóa đơn chưa được tạo không?
3. Lệnh hủy nên được hiểu như một **yêu cầu dừng** hay như một bảo đảm **rollback hoàn toàn**?
4. Cần thiết kế **idempotency key** và trạng thái công việc thế nào để retry không tạo hóa đơn thứ hai?
5. Những điểm nào có thể bị cập nhật một phần, và cần dùng giao dịch, outbox hoặc đối soát ở đâu?
6. Khi worker bị ngắt, tài nguyên nào phải được giải phóng, và tác dụng phụ nào không thể đơn giản hoàn tác?

**Gợi ý đối chiếu:** JobId có thể chỉ xác nhận yêu cầu được tiếp nhận. Timeout phía client không chứng minh DB hay hệ thống phát hành chưa xử lý. Lệnh hủy cần có ngữ nghĩa riêng cho trạng thái trước và sau khi commit; khi kết quả chưa rõ, API nên trả trạng thái cần chờ hoặc đối soát thay vì tự kết luận thất bại. Dùng idempotency key ổn định, ràng buộc lưu trữ chống trùng, trạng thái rõ ràng và cơ chế xử lý thông điệp đáng tin cậy tùy kiến trúc. Worker cần dọn kết nối/tài nguyên ở các điểm lỗi, nhưng không thể coi việc đóng thread là hoàn tác một hóa đơn đã phát hành.

## 15. Ghi nhớ

- **Đồng bộ**, **chặn**, **bất đồng bộ** và **không chặn** mô tả những khía cạnh khác nhau; phải nêu đúng điều API thực sự bảo đảm.
- **Trả Future** có thể chỉ cho biết công việc đã được gửi; **get()** có thể chặn, còn **get(timeout)** không tự hủy công việc.
- **Hủy** có thể chỉ đánh dấu kết quả hoặc yêu cầu tác vụ dừng hợp tác; không mặc nhiên hoàn tác các tác dụng phụ đã xảy ra.
- **Interruption, quản lý tài nguyên, deadline, idempotency và đối soát** là các cơ chế bổ sung cần thiết tùy loại công việc.
- Một **hợp đồng API rõ ràng** phải nói được khi nào hoàn thành, lỗi xuất hiện ở đâu, khi nào hủy có hiệu lực và bên gọi có thể an toàn retry hay không.
