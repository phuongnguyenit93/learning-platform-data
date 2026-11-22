# Kiểm chứng giả định đồng thời thay cho dựa vào độ trễ hoặc thứ tự log

## 1. Chuyển một niềm tin thành một điều kiện kiểm tra được

Các nhận xét như “luồng ghi thường xong trước”, “ngủ 100 ms là đủ” hay “log đã in ready rồi” không phải hợp đồng đồng bộ.

Trước khi viết kiểm thử, hãy phát biểu giả định chính xác:

| Nhận xét mơ hồ | Điều kiện cần kiểm chứng |
| --- | --- |
| Hai lần tăng phải được tính | Sau hai thao tác hoàn tất, bộ đếm bằng 2 |
| Dữ liệu đã sẵn sàng | Sau khi nhận tín hiệu đúng giao thức, đọc được payload đã công bố |
| Chỉ xử lý một lần | Trong các lời gọi cạnh tranh, đúng một lời gọi giành được quyền xử lý |
| Không kẹt | Tác vụ hoàn tất hoặc bị báo lỗi trong giới hạn kiểm thử đã chọn |

Sau đó xác định cơ chế nào bảo đảm điều kiện: cùng khóa, thao tác atomic, latch, Future, queue hoặc giao thức khác. Kết quả chạy thử là bằng chứng quan sát; lập luận dựa trên mô hình bộ nhớ là cơ sở để nói chương trình được bảo đảm đúng.

## 2. Vì sao sleep không phải lời giải?

Đoạn sau là ví dụ cách chờ không đáng tin:

```java
startWorker();
Thread.sleep(100);
checkResult();
```

Đây là mã minh họa, không phải một chương trình đầy đủ. Không có bảo đảm worker đã hoàn tất trong 100 ms. Máy bận, bộ lập lịch, I/O hoặc tối ưu JVM đều có thể làm thời gian thực tế khác dự đoán.

`Thread.sleep` và `yield` không có ngữ nghĩa đồng bộ bộ nhớ. Việc thời gian trôi qua không tự tạo quan hệ happens-before cho dữ liệu dùng chung. [JLS §17.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.3)

Cần chờ **đúng sự kiện**: tác vụ hoàn tất, cổng đã được mở hay một phần tử đã được chuyển giao. Thời hạn chờ chỉ giúp kiểm thử không treo mãi, không thay thế sự kiện đó.

## 3. Vì sao thứ tự log không đủ?

Log hữu ích để chẩn đoán nhưng không nên là cơ chế quyết định tính đúng của chương trình:

- Một giá trị có thể được đọc khi chuẩn bị đối số log, trước khi dòng log thực sự được xuất.
- Logger bất đồng bộ có thể chuyển dòng log qua một luồng khác.
- I/O, cấp phát và khóa trong đường ghi log có thể thay đổi lịch chạy.
- Nếu việc log tạo thêm đồng bộ, lỗi ban đầu có thể tạm biến mất.
- Thứ tự trên màn hình không mô tả đầy đủ mọi truy cập tới trạng thái cần bảo vệ.

Vì vậy, “writer logged first” không tự chứng minh lần đọc dữ liệu của reader đã có quan hệ happens-before cần thiết. Cũng không suy ra rằng thêm log là cách sửa lỗi, dù sau khi thêm log không còn tái hiện được.

Hãy ghi kết quả quan sát vào cấu trúc dữ liệu thích hợp và kiểm tra sau khi các tác vụ hoàn tất. Có thể in báo cáo cuối, tránh I/O trong đoạn đang cần quan sát nếu không thuộc mục tiêu kiểm thử.

## 4. Dùng cổng đồng bộ để tạo thứ tự cần thử

Với lỗi thao tác ghép, có thể chủ động đưa hai luồng tới cùng một điểm:

```text
Luồng A đọc giá trị cũ ─┐
                       ├── xác nhận cả hai đã đọc
Luồng B đọc giá trị cũ ─┘
                              ↓
                       mở cổng cập nhật
                              ↓
                    cả hai ghi kết quả từ giá trị cũ
```

Cách này kiểm tra một thứ tự xen kẽ cụ thể thay vì chèn sleep rồi hy vọng nó xuất hiện. Nhưng công cụ đồng bộ của kiểm thử cũng có hiệu ứng bộ nhớ; cần nói rõ đang kiểm tra điều gì.

Ví dụ dưới dùng AtomicInteger để tái hiện mất cập nhật do tách get và set. Nó cố ý kiểm tra **tính nguyên tử của thao tác ghép**, không phải thử hành vi data race trên một trường int thường.

## 5. Chương trình kiểm chứng hoàn chỉnh

Lưu toàn bộ thành **ConcurrencyAssumptionDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrencyAssumptionDemo {
    private static final long TIMEOUT_SECONDS = 10;

    static final class Data {
        int payload;
    }

    public static void main(String[] args) throws Exception {
        int split = runCounterCase(false);
        require(split == 1,
                "The forced split schedule should lose one update");

        int atomic = runCounterCase(true);
        require(atomic == 2,
                "Atomic increments should preserve both updates");

        int payload = runPublicationCase();
        require(payload == 42,
                "The publication protocol should expose payload");

        System.out.println("splitResult=" + split);
        System.out.println("atomicResult=" + atomic);
        System.out.println("publishedPayload=" + payload);
        System.out.println("checks=PASS");
    }

    private static int runCounterCase(boolean atomic)
            throws Exception {
        AtomicInteger counter = new AtomicInteger();
        CountDownLatch atGate = new CountDownLatch(2);
        CountDownLatch updateAllowed = new CountDownLatch(1);
        ExecutorService executor =
                Executors.newFixedThreadPool(2);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < 2; i++) {
                tasks.add(executor.submit(() -> {
                    if (atomic) {
                        atGate.countDown();
                        updateAllowed.await();
                        counter.incrementAndGet();
                    } else {
                        int old = counter.get();
                        atGate.countDown();
                        updateAllowed.await();
                        counter.set(old + 1);
                    }
                    return null;
                }));
            }

            boolean bothArrived = atGate.await(
                    TIMEOUT_SECONDS, TimeUnit.SECONDS);
            require(bothArrived,
                    "Workers did not reach the update gate");

            updateAllowed.countDown();

            for (Future<?> task : tasks) {
                task.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            }

            return counter.get();
        } finally {
            updateAllowed.countDown();
            for (Future<?> task : tasks) {
                task.cancel(true);
            }
            executor.shutdownNow();
        }
    }

    private static int runPublicationCase()
            throws Exception {
        Data data = new Data();
        CountDownLatch ready = new CountDownLatch(1);
        ExecutorService executor =
                Executors.newFixedThreadPool(2);

        try {
            Future<Integer> reader = executor.submit(() -> {
                boolean signalled = ready.await(
                        TIMEOUT_SECONDS, TimeUnit.SECONDS);
                require(signalled,
                        "Publication signal did not arrive");
                return data.payload;
            });

            Future<?> writer = executor.submit(() -> {
                data.payload = 42;
                ready.countDown();
            });

            writer.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            return reader.get(
                    TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } finally {
            executor.shutdownNow();
        }
    }

    private static void require(
            boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 ConcurrencyAssumptionDemo.java
java ConcurrencyAssumptionDemo
```

Kết quả khi hoàn tất bình thường:

```text
splitResult=1
atomicResult=2
publishedPayload=42
checks=PASS
```

Các điều kiện dùng hàm require ném AssertionError, nên vẫn được kiểm tra khi không bật tùy chọn `-ea`. Không có lời gọi sleep và không dựa vào thứ tự log giữa các worker.

## 6. Vì sao từng kết quả được kiểm chứng?

### Trường hợp get rồi set

Cả hai luồng đọc 0 trước khi báo đã tới atGate. Chưa luồng nào được ghi counter trước khi main mở updateAllowed. Vì vậy cả hai đều set 1; kết quả cuối là 1 dù có hai tác vụ.

Kiểm thử này không xem 1 là hành vi đúng của bộ đếm nghiệp vụ. Nó xác nhận **lỗi đã được tái hiện theo lịch cưỡng bức**. Một kiểm thử cho implementation bộ đếm đúng phải yêu cầu 2.

### Trường hợp tăng atomic

Hai luồng vẫn được đưa tới cổng cập nhật, nhưng mỗi luồng gọi incrementAndGet để thực hiện phép tăng nguyên tử. Hai cập nhật được giữ lại, kết quả là 2. Từng lời gọi get/set có tính chất atomic riêng không làm chuỗi get–tính–set tương đương incrementAndGet. [API AtomicInteger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)

### Trường hợp công bố dữ liệu

Writer ghi payload trước ready.countDown; reader chỉ đọc sau await thành công. Đó là giao thức công bố mà kiểm thử đang xác nhận. Latch có hợp đồng bộ nhớ làm các hành động trước countDown được nhìn thấy sau await tương ứng. [API CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

### Vì sao lấy Future thay vì chỉ đếm tác vụ xong?

Future.get chờ hoàn tất và truyền lỗi của tác vụ về bên kiểm thử qua ExecutionException; nó còn có hợp đồng happens-before cho việc quan sát kết quả. Nếu worker ném AssertionError hoặc ngoại lệ, main không nên vẫn in PASS chỉ vì worker đã kết thúc. [API Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html)

Phần finally mở cổng và yêu cầu hủy/ngắt các tác vụ còn lại khi có lỗi. Tác vụ trong ví dụ dùng await có thể bị ngắt; không giữ các vòng lặp vô hạn bỏ qua tín hiệu hủy.

## 7. Thời hạn chờ để chẩn đoán, không để chứng minh đồng bộ

Mốc 10 giây trong ví dụ không có nghĩa thuật toán cần đúng 10 giây để nhìn thấy dữ liệu. Đây là giới hạn thực dụng để kiểm thử báo lỗi thay vì chờ vô hạn.

Nếu await trả false hoặc Future.get ném TimeoutException, không được tiếp tục như thể tác vụ đã hoàn tất. Cần phân biệt:

- Chưa tới điểm cần quan sát.
- Có tác vụ thất bại.
- Bị kẹt do thiếu tín hiệu.
- Môi trường quá tải nên không hoàn thành trong giới hạn đã chọn.

Có thể điều chỉnh giới hạn theo môi trường, nhưng tăng timeout không sửa được một giao thức thiếu đồng bộ. Tương tự, giảm timeout không biến một phép thử thành bằng chứng mạnh hơn về mô hình bộ nhớ.

Nếu cần đo khoảng thời gian trôi qua trong một lần chạy, dùng nanoTime theo hợp đồng của nó và so hiệu giữa các lần đọc; số đo thời gian vẫn không tạo quan hệ happens-before. [API System.nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime())

### Đủ luồng để các cổng có thể mở

Một bẫy phổ biến là executor chỉ có một worker nhưng hai tác vụ đều phải tới barrier/latch trước khi được đi tiếp. Tác vụ đầu chiếm worker để chờ, tác vụ thứ hai chưa được chạy, khiến kiểm thử tự tạo bế tắc.

Chương trình dùng hai worker cho hai tác vụ cần cùng tới cổng. Khi thay kích thước pool hoặc thêm bước chờ, phải kiểm tra khả năng tiến triển của chính bộ kiểm thử.

## 8. Đừng vô tình kiểm tra một chương trình khác

Thêm latch giữa phép ghi và phép đọc có thể tạo happens-before mà mã gốc không có. Khi đó kết quả chỉ chứng minh phiên bản **đã thêm đồng bộ**, không chứng minh bản gốc chia sẻ dữ liệu không đồng bộ là đúng.

Cần chọn cách kiểm tra theo mục tiêu:

| Mục tiêu | Cách tiếp cận |
| --- | --- |
| Tái hiện check-then-act hoặc mất cập nhật | Dùng cổng ở những điểm thao tác để dựng thứ tự cụ thể |
| Kiểm tra giao thức công bố có latch/queue thật | Dùng chính hợp đồng dự kiến của hệ thống |
| Tìm kết quả yếu do mô hình bộ nhớ | Tránh chèn đồng bộ che mất tình huống; cân nhắc công cụ stress chuyên dụng |
| Kiểm tra hiệu năng | Đo bằng thiết kế benchmark riêng; không đồng nhất nhanh/chậm với đúng/sai |

Không đặt log, synchronized hoặc atomic vào một đường đang cần quan sát rồi quên rằng chính chúng đã thay đổi các quan hệ bộ nhớ.

Một biến lưu kết quả của mỗi actor cũng cần thiết kế đúng. Không dùng một collection thường bị nhiều luồng cùng sửa để thu thập bằng chứng, vì bộ thu kết quả có thể tạo lỗi riêng và làm kết luận nhiễu.

## 9. Kết hợp lập luận và stress test

Kiểm thử có kiểm soát cho một lịch chạy dễ tái hiện, nhưng không bao quát mọi lịch, mọi tối ưu JIT và mọi kiến trúc xử lý. Chạy thử hàng triệu lần mà không thấy lỗi vẫn không chứng minh mọi hành vi được mô hình bộ nhớ cho phép đều đã được quan sát.

jcstress là công cụ của OpenJDK dành cho stress test đồng thời và những kết quả liên quan đến JVM/hardware. Khi dùng nó, cần mô hình hóa các actor, trạng thái riêng cho từng lần thử và phân loại kết quả theo hợp đồng mong muốn. [Dự án OpenJDK jcstress](https://github.com/openjdk/jcstress)

Ví dụ lập luận một phép thử công bố đơn giản:

```text
Trạng thái ban đầu: payload = 0, ready = false
Actor ghi:         payload = 42; ready = true
Actor đọc:         nếu thấy ready thì lấy payload, nếu chưa thì ghi "chưa thấy"
```

Nếu ready là volatile và giao thức chỉ công bố một lần, kết quả “đã thấy ready nhưng payload = 0” không được chấp nhận theo đường happens-before dự kiến. “Chưa thấy ready” có thể hợp lệ vì actor đọc được chạy sớm. Với cờ thường không đồng bộ, không được áp kết luận của volatile sang nó.

Phân loại kết quả phải xuất phát từ mô hình bộ nhớ và hợp đồng mã, không từ việc “trên laptop tôi chỉ thấy 42”. Công cụ stress giúp tìm bằng chứng phản ví dụ và kiểm tra nhiều thực thi; nó không thay thế việc phát biểu đúng điều kiện ban đầu.

## 10. Một quy trình kiểm chứng thực dụng

1. Ghi rõ bất biến hoặc kết quả cần giữ.
2. Chỉ ra các trường chia sẻ và đường đọc/ghi.
3. Vẽ đường happens-before hoặc xác định đơn vị atomic cần có.
4. Thiết kế lịch thử có mục tiêu nếu lỗi là thao tác ghép.
5. Lấy kết quả và lỗi từ mọi tác vụ, đặt giới hạn chờ và dọn tài nguyên.
6. Hạn chế tác dụng phụ không thuộc mục tiêu ở đoạn cần quan sát.
7. Dùng stress test phù hợp cho những trường hợp không thể ép lịch một cách trung thực.
8. Kết luận đúng phạm vi bằng chứng, không biến số lần chạy thành một chứng minh tổng quát.

### Tự thực hành

1. Đổi executor của runCounterCase thành chỉ một worker. Vì sao kiểm thử có thể hết hạn mà không chứng minh thuật toán bộ đếm sai theo lịch dự kiến?
2. Bỏ việc kiểm tra boolean trả từ await. Điều gì có thể làm kiểm thử đọc dữ liệu trước khi có tín hiệu?
3. Cho một worker ném ngoại lệ trước khi tăng. Nếu chỉ chờ bằng sleep rồi in kết quả, lỗi đó dễ bị bỏ sót thế nào?
4. Di chuyển ready.countDown xuống trước phép ghi payload. Kiểm thử còn có cùng đường happens-before không?
5. Bỏ log giữa worker nhưng giữ báo cáo sau khi mọi Future hoàn tất. Vì sao cách này giảm can thiệp vào đoạn đang quan sát?
6. Viết phân loại kết quả cho một cờ công bố volatile, rồi giải thích vì sao phải dùng trạng thái mới cho từng lần thử.
