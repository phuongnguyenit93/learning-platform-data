# Đặc điểm bộ thực thi tái sử dụng luồng theo nhu cầu

## 1. Mô hình cần nắm: giữ lại luồng rảnh để phục vụ đợt việc tiếp theo

Bộ thực thi tái sử dụng luồng theo nhu cầu thường được tạo bằng `Executors.newCachedThreadPool()`. Nó quản lý một nhóm luồng có thể tăng khi công việc đến và giảm khi luồng không còn được dùng.

Hãy hình dung một bộ phận xử lý yêu cầu:

- Có người đang rảnh và sẵn sàng nhận việc thì giao việc cho người đó.
- Không có người nhận sẵn thì bổ sung người xử lý mới.
- Người đã rảnh quá thời gian cho phép được cho nghỉ.

Trong chương trình, “người xử lý” là **luồng thực thi**; “công việc” là **tác vụ** `Runnable` hoặc `Callable`. Tên “cached” nói đến việc giữ lại và tái sử dụng luồng, không phải lưu kết quả tính toán hay ghi nhớ các tác vụ đã chạy.

Mục đích là giảm việc tạo/hủy luồng lặp lại khi có nhiều công việc bất đồng bộ ngắn đến thành từng đợt. Khả năng mở rộng nhanh cũng là điểm phải kiểm soát: mặc định không có một trần số luồng nhỏ phù hợp với tài nguyên ứng dụng. API này vẫn còn áp dụng hiện nay. [Hợp đồng newCachedThreadPool](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html#newCachedThreadPool()).

## 2. Các đặc điểm mặc định

Cách tạo thông thường:

```java
ExecutorService executor = Executors.newCachedThreadPool();
```

Đây là đoạn minh họa cần các import trong `java.util.concurrent`; thành phần sở hữu executor phải quản lý việc dừng nó.

Trong triển khai OpenJDK được đối chiếu, factory sử dụng cấu hình `ThreadPoolExecutor` sau:

| Thành phần | Giá trị | Ý nghĩa |
|---|---|---|
| `corePoolSize` | `0` | Không giữ một số luồng nền tối thiểu chỉ vì executor còn sống |
| `maximumPoolSize` | `Integer.MAX_VALUE` | Trần cấu hình rất lớn, thường xem như không giới hạn thực tế |
| `keepAliveTime` | `60` giây | Luồng không có việc trong thời gian này có thể được thu hồi |
| Hàng đợi | `SynchronousQueue<Runnable>` | Chuyển giao trực tiếp, không chứa kho tác vụ đang chờ |
| Chính sách từ chối mặc định | `AbortPolicy` | Ném `RejectedExecutionException` khi việc không được chấp nhận theo cơ chế từ chối |

Các giá trị cấu hình trên có thể kiểm tra ở [mã nguồn OpenJDK của Executors](https://raw.githubusercontent.com/openjdk/jdk/jdk-25-ga/src/java.base/share/classes/java/util/concurrent/Executors.java). Đừng hiểu `Integer.MAX_VALUE` là máy thực sự có thể tạo hơn hai tỉ luồng. Giới hạn bộ nhớ, luồng hệ điều hành và tài nguyên tiến trình thường xuất hiện từ rất lâu trước con số đó.

Nhóm luồng không tạo trước hàng loạt luồng khi gọi factory. Khi chưa có tác vụ, số luồng có thể bằng 0; khi mọi luồng đã rảnh đủ lâu, số luồng cũng có thể về 0 dù chưa gọi `shutdown()`.

## 3. Một tác vụ mới đi qua hệ thống như thế nào?

Luồng xử lý khái niệm trong trạng thái executor còn nhận việc:

```text
Tác vụ mới đến
    ↓
Có luồng đang sẵn sàng nhận qua SynchronousQueue?
    ├─ Có → chuyển giao → tái sử dụng luồng đó
    └─ Không → cố tạo thêm luồng trong giới hạn cấu hình
                   ├─ tạo được → chạy tác vụ
                   └─ không nhận được → xử lý từ chối/lỗi tài nguyên tương ứng
```

Sau khi hoàn thành, luồng tiếp tục chờ tác vụ mới trong thời gian giữ luồng rảnh. Nếu nhận việc trong khoảng này, nó được tái sử dụng; nếu tiếp tục không có việc, nó có thể kết thúc. Đây là một vòng đời luồng, không phải vòng đời tác vụ.

**Một tác vụ đang chạy lâu hơn 60 giây không bị dừng vì `keepAliveTime = 60 giây`.** Thời gian đó dành cho lúc luồng rảnh chờ công việc. Muốn giới hạn thời gian xử lý phải thiết kế thời hạn riêng cho yêu cầu, lời gọi I/O và cơ chế hủy hợp tác.

Cũng không có cam kết rằng tác vụ B chắc chắn dùng đúng luồng đã chạy tác vụ A chỉ vì A vừa trả kết quả. Tại thời điểm gửi B, luồng đó có thể chưa quay lại trạng thái nhận việc. “Có thể tái sử dụng” không phải cam kết danh tính luồng cho mỗi tác vụ.

## 4. Vì sao SynchronousQueue làm nhóm luồng tăng nhanh?

`SynchronousQueue` không có dung lượng lưu phần tử, kể cả dung lượng 1. Nó là điểm gặp giữa bên giao và bên nhận. Với cách dùng trong `ThreadPoolExecutor`, thao tác thử chuyển giao không thành công khi không có luồng nhận phù hợp; executor có thể bổ sung luồng.

Không nên nhầm chữ “synchronous” với việc lời gọi `submit()` phải chờ tác vụ chạy xong. Tác vụ vẫn có thể được chạy trên luồng khác; tên hàng đợi nói về cơ chế chuyển giao.

Một hệ quả khi quan sát hệ thống: `executor.getQueue().size()` có thể bằng 0 trong lúc hàng trăm luồng đang xử lý hoặc đang chờ I/O. Không có tác vụ tích trong hàng đợi này không có nghĩa hệ thống còn nhẹ tải. [SynchronousQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/SynchronousQueue.html).

Ví dụ: ba tác vụ đến trong lúc cả ba đều bị chặn ở lời gọi mạng. Không có luồng nào quay lại nhận việc; tác vụ thứ tư có thể làm nhóm luồng tạo luồng thứ tư. Nó không mặc nhiên chờ một trong ba tác vụ trước xong như nhóm ba luồng cố định.

## 5. Thí nghiệm chạy được: tăng theo tải rồi thu hồi khi rảnh

Chương trình sau dùng `ThreadPoolExecutor` với cùng mô hình `core = 0`, trần rất lớn và `SynchronousQueue`. **Riêng thời gian giữ luồng rảnh được rút từ 60 giây xuống 200 mili giây để thí nghiệm không phải chờ một phút.** Đây là cấu hình thí nghiệm, không phải giá trị mặc định của `newCachedThreadPool()`.

Ba tác vụ cùng chờ một latch, do đó không luồng nào có thể nhận thêm tác vụ trước khi luồng `main` cho phép chúng hoàn thành. Sau đó chương trình chờ số luồng về 0 trước khi giao việc tiếp. Nó kiểm tra điều kiện với một thời hạn tối đa, không đoán rằng cứ ngủ đúng 200 mili giây là mọi luồng đã được thu hồi.

Lưu vào `CachedPoolDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CachedPoolDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger created = new AtomicInteger();
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                0,
                Integer.MAX_VALUE,
                200,
                TimeUnit.MILLISECONDS,
                new SynchronousQueue<Runnable>(),
                task -> new Thread(task,
                        "cached-demo-" + created.incrementAndGet()));

        CountDownLatch allStarted = new CountDownLatch(3);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<Integer>> results = new ArrayList<>();

        try {
            System.out.println("initial pool size: " + pool.getPoolSize());

            for (int i = 1; i <= 3; i++) {
                final int value = i;
                results.add(pool.submit(() -> {
                    allStarted.countDown();
                    release.await();
                    return value;
                }));
            }

            if (!allStarted.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Three tasks did not start");
            }
            System.out.println("threads created for burst: " + created.get());
            System.out.println("buffered tasks: " + pool.getQueue().size());

            release.countDown();
            int sum = 0;
            for (Future<Integer> result : results) {
                sum += result.get(10, TimeUnit.SECONDS);
            }
            System.out.println("sum: " + sum);

            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
            while (pool.getPoolSize() != 0) {
                if (System.nanoTime() - deadline >= 0) {
                    throw new AssertionError("Idle threads did not retire");
                }
                Thread.sleep(10);
            }
            System.out.println("pool size after idle: " + pool.getPoolSize());

            Future<String> next = pool.submit(
                    () -> Thread.currentThread().getName());
            System.out.println("next worker: "
                    + next.get(10, TimeUnit.SECONDS));
            System.out.println("total threads created: " + created.get());
        } finally {
            release.countDown();
            shutdown(pool);
        }
    }

    private static void shutdown(ThreadPoolExecutor pool) {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Executor did not terminate");
                }
            }
        } catch (InterruptedException ex) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 CachedPoolDemo.java
java CachedPoolDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
initial pool size: 0
threads created for burst: 3
buffered tasks: 0
sum: 6
pool size after idle: 0
next worker: cached-demo-4
total threads created: 4
```

Giải thích bằng chứng:

1. `initial pool size: 0`: chưa có tác vụ thì chưa cần luồng.
2. Ba tác vụ bị giữ cùng lúc làm nhóm tạo ba luồng; không có bộ đệm tác vụ trong `SynchronousQueue`.
3. Kết quả `sum: 6` xác nhận cả ba tác vụ đã hoàn thành bình thường.
4. Sau khoảng rảnh đủ dài, mọi luồng có thể được thu hồi vì `corePoolSize = 0`.
5. Tác vụ mới vẫn được chấp nhận sau khi số luồng về 0; nó dùng luồng mới có tên thứ tư. Executor chưa bị shutdown.

Thí nghiệm này kiểm chứng tăng/thu hồi/tạo lại. Nó không tuyên bố mỗi tác vụ liên tiếp luôn dùng cùng một luồng. Muốn quan sát sự tái sử dụng, có thể ghi tên luồng qua nhiều đợt công việc với khoảng nghỉ ngắn hơn thời gian giữ luồng; tên lặp lại là quan sát của lần chạy, không phải đầu ra cố định được bảo đảm cho mọi lịch chạy.

## 6. Khi nào đặc điểm này có ích?

Nhóm luồng kiểu này có thể phù hợp khi lượng việc đã được giới hạn ở bên ngoài, tác vụ tương đối ngắn, độc lập và tải đến theo đợt. Ví dụ một công cụ nội bộ chỉ có tối đa vài chục tác vụ đồng thời, giữa các đợt có thời gian nghỉ. Việc tái sử dụng luồng giảm chi phí tạo luồng cho các đợt gần nhau; thu hồi luồng rảnh giúp không giữ nguyên số luồng sau đỉnh tải.

Tuy nhiên, “tác vụ ngắn” phải được đánh giá trong điều kiện thực tế. Một tác vụ chỉ có vài dòng gọi HTTP vẫn có thể giữ luồng rất lâu khi dịch vụ phía sau chậm. Mỗi luồng bị giữ làm tăng nhu cầu bổ sung luồng cho yêu cầu mới.

Với tác vụ chủ yếu tính toán CPU, tạo thêm nhiều luồng nền không tạo thêm lõi xử lý. Cần chọn mức song song theo tài nguyên CPU và đo hiệu năng. Với công việc chờ I/O, số luồng cho phép cũng phải xét đến kết nối, hạn mức dịch vụ và bộ nhớ, không chỉ CPU.

## 7. Rủi ro quan trọng: tải chậm được biến thành tăng số luồng

Một chuỗi quá tải thường gặp:

```text
Dịch vụ phía sau chậm
    → tác vụ giữ luồng lâu hơn
    → ít luồng rảnh nhận công việc mới
    → executor tạo thêm luồng
    → nhiều kết nối/yêu cầu cạnh tranh hơn
    → tài nguyên cạn hoặc độ trễ tiếp tục tăng
```

Hậu quả có thể gồm bộ nhớ stack luồng tăng, chi phí chuyển ngữ cảnh tăng, số kết nối vượt khả năng phục vụ, hoặc không thể tạo thêm luồng hệ điều hành. Không nên chờ đến `Integer.MAX_VALUE` hay trông đợi mọi lỗi tài nguyên đều đi qua `RejectedExecutionException`.

Một ước lượng giúp đặt câu hỏi đúng: nếu trung bình có 100 tác vụ/giây và mỗi tác vụ chiếm luồng 2 giây, số tác vụ đang chiếm luồng có thể vào khoảng 200 trong trạng thái ổn định. Đây chỉ là ước lượng theo tốc độ đến và thời gian chiếm luồng; đỉnh tải và phân bố độ trễ vẫn cần đo riêng.

`keepAliveTime` không xử lý quá tải khi mọi luồng đều bận. Giảm từ 60 xuống 10 giây chỉ làm luồng rảnh nghỉ sớm hơn; nó không đặt giới hạn cho tác vụ đang chạy.

## 8. Đặt giới hạn có chủ đích

Nếu cần trần số luồng hữu ích, có thể tự cấu hình `ThreadPoolExecutor`. Đoạn sau là ví dụ khởi tạo, cần import và quản lý vòng đời; các con số chỉ minh họa:

```java
ThreadPoolExecutor bounded = new ThreadPoolExecutor(
        0,
        16,
        30,
        TimeUnit.SECONDS,
        new SynchronousQueue<Runnable>(),
        new ThreadPoolExecutor.AbortPolicy());
```

Cấu hình này vẫn tái sử dụng/thu hồi luồng theo nhu cầu nhưng tối đa 16 luồng. Khi cả 16 luồng đều không thể nhận việc, tác vụ mới có thể bị từ chối ngay; không có chỗ đệm để chờ. Nơi giao việc phải xử lý `RejectedExecutionException` và đưa ra chính sách như báo bận, giảm tải hoặc thử lại có giới hạn. Trần 16 không phải khuyến nghị chung.

Nếu muốn cho phép một số tác vụ chờ, chọn hàng đợi có dung lượng hữu hạn. Khi đổi hàng đợi, phải hiểu lại thứ tự tăng luồng: `ThreadPoolExecutor` thường thử đưa vào hàng đợi sau khi đạt mức lõi rồi mới tăng đến mức tối đa nếu hàng đợi không nhận được. Chỉ thay `SynchronousQueue` bằng một hàng đợi không giới hạn có thể làm cấu hình `core = 0` chạy khác hẳn ý định co giãn ban đầu. [Cơ chế kích thước nhóm và hàng đợi của ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

Các giới hạn tài nguyên phía sau, chẳng hạn tối đa số lời gọi cơ sở dữ liệu đồng thời, cần được bảo vệ theo đúng tài nguyên đó. Có thể kết hợp cơ chế cho phép nhận việc với số lượt hữu hạn, nhưng phải giới hạn trước khi tạo ra vô số tác vụ chỉ để chờ một giấy phép.

## 9. Vòng đời và trạng thái đi theo luồng

Tái sử dụng luồng kéo theo trách nhiệm dọn trạng thái. Dữ liệu để trong `ThreadLocal` có thể còn trên luồng khi tác vụ tiếp theo đến. Với dữ liệu theo yêu cầu như mã theo dõi hoặc người dùng, cần gán/thu dọn có chủ đích, thường bằng `try/finally` và `remove()`. Không dùng việc “luồng chắc sớm nghỉ” làm cơ chế cách ly yêu cầu.

Luồng do factory mặc định tạo là luồng nền tảng (platform thread), không phải tự động là virtual thread. Java 21 trở lên có `newVirtualThreadPerTaskExecutor()` cho mô hình một virtual thread cho mỗi tác vụ; đó là một lựa chọn có cơ chế khác, không biến cached pool thành nhóm luồng ảo. Dù dùng mô hình nào vẫn phải kiểm soát tài nguyên phía sau. [Các factory và defaultThreadFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html).

Thu hồi luồng rảnh cũng không thay cho đóng executor. Khi chủ sở hữu không còn dùng nữa, gọi `shutdown()` và chờ kết thúc theo nhu cầu; nếu cần dừng gấp, `shutdownNow()` chỉ cố gắng ngắt tác vụ đang chạy. Tác vụ phải hợp tác với tín hiệu ngắt. Không shutdown executor dùng chung sau từng công việc.

Việc chọn nhóm cached không đổi hợp đồng kết quả của tác vụ: `submit` trả Future để theo dõi; nên thu nhận kết quả/lỗi có chủ đích. Không bỏ Future rồi kết luận công việc thành công vì không thấy lỗi trên màn hình.

## 10. Các ngộ nhận cần tự sửa

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Cached” nghĩa là lưu kết quả | Thứ được giữ để tái sử dụng là luồng |
| Luồng luôn được tạo mới cho từng tác vụ | Luồng sẵn sàng có thể nhận lại công việc |
| Số luồng tăng theo CPU | Cơ chế này tăng theo nhu cầu nhận việc và cấu hình, không tự tính giới hạn CPU |
| Tác vụ quá 60 giây sẽ bị hủy | 60 giây mặc định áp dụng cho luồng rảnh |
| Hàng đợi bằng 0 nghĩa là không tải | Tác vụ có thể đang chiếm rất nhiều luồng |
| Có `maximumPoolSize` rất lớn nên cứ gửi thoải mái | Tài nguyên máy thường cạn trước khi chạm trần đó |
| Số luồng về 0 nghĩa executor đã đóng | Executor còn hoạt động vẫn có thể tạo luồng cho tác vụ mới |
| Tái sử dụng bảo đảm cùng luồng cho cùng người dùng | Không có sự gắn cố định tác vụ/người dùng với luồng |

## 11. Tự kiểm tra và thực hành

1. Vì sao ba tác vụ bị chặn có thể làm xuất hiện ba luồng? **Vì mỗi tác vụ chiếm một luồng và không có luồng nhận rảnh để chuyển giao tác vụ tiếp theo.**
2. Có nên dùng cached pool không giới hạn để xử lý lượng yêu cầu công khai chưa kiểm soát? **Chỉ khi đã có giới hạn tiếp nhận/tài nguyên phù hợp; bản thân factory không cung cấp trần thực tế an toàn.**
3. Sau khi mọi luồng rảnh bị thu hồi, có thể gửi việc tiếp không? **Có**, nếu executor chưa shutdown và còn chấp nhận được tác vụ.
4. Hạ thời gian giữ luồng rảnh có làm ít tác vụ chạy đồng thời hơn trong đợt tải dài? **Không.** Muốn giới hạn đồng thời cần giới hạn số luồng hoặc cơ chế nhận việc.

Thực hành với chương trình trên: đổi `maximumPoolSize` từ `Integer.MAX_VALUE` thành `2`. Tác vụ thứ ba sẽ không có luồng nhận và không thể tạo luồng thứ ba khi hai tác vụ trước còn bị giữ; với chính sách mặc định, lời gọi giao việc có thể báo `RejectedExecutionException`. Thêm xử lý từ chối có chủ đích và giữ phần `finally` để giải phóng hai tác vụ đã chạy. Đừng bỏ qua ngoại lệ rồi chờ đủ ba tác vụ bắt đầu, vì tác vụ thứ ba chưa được nhận.
