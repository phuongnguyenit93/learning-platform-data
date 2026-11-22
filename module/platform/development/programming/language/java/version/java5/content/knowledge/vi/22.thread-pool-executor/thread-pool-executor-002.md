# corePoolSize, maximumPoolSize và quy tắc nhận tác vụ

## 1. Hai ngưỡng luồng chỉ có ý nghĩa khi đọc cùng hàng đợi

`ThreadPoolExecutor` không chỉ có một con số “số luồng”. Khi nhận công việc, nó phải chọn giữa tạo luồng, xếp hàng hoặc từ chối.

Hai tham số quan trọng:

- **`corePoolSize`**: ngưỡng luồng cốt lõi được dùng trong quy tắc tiếp nhận.
- **`maximumPoolSize`**: số luồng tối đa mà nhóm được phép có.

Nhưng chỉ biết hai số ấy chưa đủ để dự đoán hành vi. Hàng đợi quyết định khi nào executor có lý do mở rộng từ core tới maximum.

Ví dụ, core bằng 2 và maximum bằng 10 không có nghĩa executor lập tức tạo 10 luồng khi có 10 tác vụ. Sau hai luồng đầu, nó thường thử xếp những việc tiếp theo vào hàng đợi.

Để hiểu cấu hình, cần nhìn đồng thời:

```text
Số luồng hiện có
    + ngưỡng core
    + khả năng nhận việc của queue
    + ngưỡng maximum
    + trạng thái vòng đời
    -> quyết định nhận hoặc từ chối tác vụ
```

Các quy tắc trong bài vẫn áp dụng trên Java hiện hành; ví dụ hoàn chỉnh dùng Java 17+.

## 2. Đọc đúng từng đại lượng

| Đại lượng | Ý nghĩa |
|---|---|
| `corePoolSize` | Ngưỡng ưu tiên tạo thêm luồng trước khi xếp hàng |
| `maximumPoolSize` | Giới hạn số luồng của nhóm |
| `getPoolSize()` | Số luồng hiện có trong nhóm tại lúc quan sát |
| `getActiveCount()` | Ước lượng số luồng đang thực hiện công việc |
| Dung lượng queue | Số tác vụ có thể chờ trong queue, không phải số luồng |

Không dùng `getActiveCount()` làm biến quyết định tương đương với số luồng hiện có. Nhóm có thể có bốn luồng nhưng chỉ một luồng đang xử lý, các luồng còn lại đang rảnh.

### Core không có nghĩa số luồng đã tạo sẵn

Mặc định, ngay sau constructor, nhóm chưa cần tạo tất cả luồng core. Luồng được tạo theo nhu cầu khi công việc tới.

Có thể yêu cầu khởi động trước bằng:

- `prestartCoreThread()`: thử khởi động một luồng core.
- `prestartAllCoreThreads()`: khởi động các luồng core chưa có và trả số vừa khởi động.

Điều này thay đổi thời điểm khởi động, không đổi quy tắc “đạt core thì ưu tiên xếp hàng”.

### Core không phải những Thread có danh tính vĩnh viễn

Không nên gắn nghiệp vụ với giả định một đối tượng Thread cụ thể luôn là “luồng core số 1”. Các ngưỡng phục vụ quản lý số lượng; luồng có thể chết, được thay thế hoặc bị thu hồi theo cấu hình.

## 3. Quy tắc cốt lõi khi execute nhận một Runnable

Trong điều kiện executor vẫn chạy và việc tạo luồng thành công, có thể đọc theo thứ tự:

1. **Chưa đủ core**: thử tạo một luồng để chạy tác vụ mới.
2. **Đã đạt core**: thử đưa tác vụ vào hàng đợi.
3. **Không xếp hàng được**: thử thêm luồng nếu chưa đạt maximum.
4. **Không thể thêm luồng để nhận việc**: chuyển tới chính sách từ chối.

Điểm thường bị nhớ ngược là bước 2: **queue được ưu tiên trước khi mở rộng vượt core**.

```text
Có tác vụ mới
    |
    v
Chưa đủ core? ------ có -----> thử thêm luồng
    |
   không
    v
Queue nhận được? --- có -----> chờ hoặc được luồng rảnh lấy
    |
   không
    v
Chưa đủ maximum? -- có -----> thử thêm luồng
    |
   không
    v
Chính sách từ chối
```

Đây là sơ đồ khái niệm, không phải bản sao thuật toán xử lý mọi cuộc đua đồng thời. Executor còn kiểm tra trạng thái đóng và các trường hợp không thể tạo luồng.

Quy tắc được mô tả trong [ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

### Chưa đủ core vẫn có thể tạo luồng dù đang có luồng rảnh

Giả sử core bằng 3, hiện mới có một luồng và luồng đó đang rảnh. Khi có tác vụ mới, executor vẫn ưu tiên thử tạo thêm luồng theo nhánh chưa đạt core.

Vì vậy, quy tắc không phải “tìm luồng rảnh trước, chỉ tạo khi tất cả đều bận”. Đây là một khác biệt quan trọng khi đọc số luồng tăng trong những lần gửi đầu tiên.

Khi đã đạt core, một tác vụ được đưa vào queue có thể được luồng đang rảnh lấy gần như ngay lập tức. Xếp hàng không đồng nghĩa chắc chắn phải chờ lâu.

## 4. Ví dụ bằng tay: core 2, max 3, queue 1

Giả sử các tác vụ đã nhận đều chưa thể hoàn tất trong lúc gửi thêm:

| Lần gửi | Trước khi gửi | Quyết định |
|---|---|---|
| T1 | Nhóm chưa có luồng | Tạo luồng thứ nhất |
| T2 | Một luồng, nhỏ hơn core 2 | Tạo luồng thứ hai |
| T3 | Đã có hai luồng, queue trống | Đưa vào queue một chỗ |
| T4 | Đã đạt core, queue đầy | Tạo luồng thứ ba, đạt maximum |
| T5 | Ba luồng đều còn công việc, queue đầy | Gọi handler từ chối |

Nếu dùng `AbortPolicy`, T5 làm nơi gửi nhận `RejectedExecutionException`.

T4 có thể bắt đầu trước T3, vì T4 được giao trực tiếp cho luồng mới trong khi T3 đang đợi một luồng cũ rảnh để lấy nó. Hàng đợi FIFO không biến toàn bộ thứ tự bắt đầu của executor thành FIFO.

Nếu T1 kịp kết thúc trước lúc gửi T3, kết quả quan sát có thể khác: luồng rảnh có thể lấy việc ra và làm queue có chỗ. Bảng chỉ đúng dưới điều kiện các việc trước vẫn được giữ chưa kết thúc.

## 5. Chương trình hoàn chỉnh: quan sát các ngưỡng

Chương trình dùng một chốt chung để không tác vụ nào kết thúc trước khi các lần gửi và kiểm tra hoàn tất.

Lưu thành **`PoolAdmissionDemo.java`**, dùng Java 17+:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PoolAdmissionDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finish = new CountDownLatch(1);
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                2,
                3,
                15, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        Runnable heldTask = () -> {
            try {
                finish.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            printState(executor, "created");

            executor.execute(heldTask);
            printState(executor, "T1");

            executor.execute(heldTask);
            printState(executor, "T2");

            executor.execute(heldTask);
            printState(executor, "T3");

            executor.execute(heldTask);
            printState(executor, "T4");

            try {
                executor.execute(heldTask);
                throw new AssertionError("T5 should be rejected");
            } catch (RejectedExecutionException e) {
                System.out.println("T5: rejected");
            }
        } finally {
            finish.countDown();
            executor.shutdown();
            try {
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                    if (!executor.awaitTermination(
                            5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Executor did not terminate");
                    }
                }
            } catch (InterruptedException e) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }

    private static void printState(
            ThreadPoolExecutor executor, String stage) {
        System.out.println(
                stage + ": workers=" + executor.getPoolSize()
                + ", queued=" + executor.getQueue().size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 PoolAdmissionDemo.java
java PoolAdmissionDemo
```

Stdout chính xác:

```text
created: workers=0, queued=0
T1: workers=1, queued=0
T2: workers=2, queued=0
T3: workers=2, queued=1
T4: workers=3, queued=1
T5: rejected
```

### Vì sao đầu ra này xác định?

Hai tác vụ đầu được giao cho hai luồng mới. Chúng không thể kết thúc vì `finish` chưa mở.

T3 vào queue. Không có luồng nào rảnh để lấy T3, nên queue vẫn đầy khi T4 tới. T4 được giao cho luồng thứ ba và cũng chờ ở chốt. T5 không còn chỗ trong queue hoặc cơ hội thêm luồng.

Không cần `sleep` để đoán tác vụ đã chạy lâu hay chưa. Điều quan trọng là các tác vụ được giao không thể hoàn tất hoặc quay lại lấy phần tử trong queue trước khi `main` mở chốt.

Các phương thức thống kê trong hệ thống chạy tự do có thể thay đổi giữa các lần đọc. Trong ví dụ, chốt tạo ra điều kiện ổn định để quan sát. `getPoolSize()` đo luồng hiện có, không phải chứng minh cả ba đã được CPU cấp thời gian chạy tại đúng khoảnh khắc in.

Sau thí nghiệm, `finally` mở chốt và đóng executor. Nhờ vậy ví dụ không để lại luồng nền tảng tiếp tục sống sau khi chương trình xong.

## 6. Queue quyết định maximum có được dùng hay không

### Hàng đợi có dung lượng lớn

Khai báo minh họa:

```java
new ThreadPoolExecutor(
        2,
        20,
        30, TimeUnit.SECONDS,
        new LinkedBlockingQueue<>());
```

Sau hai luồng đầu, các việc mới thường tiếp tục vào hàng đợi. Với queue không cấu hình capacity hữu hạn thực tế, nhánh mở rộng vượt core thường không xảy ra trong vận hành bình thường.

Do đó, đặt maximum bằng 20 không tạo ra cơ chế “queue dài một chút thì tăng dần tới 20”. ThreadPoolExecutor không tự đặt ngưỡng mở rộng dựa trên độ dài queue theo cách ấy.

Nếu đầu vào vượt tốc độ xử lý kéo dài, số việc chờ và độ trễ có thể tăng dù số luồng vẫn ở mức core.

### Queue hữu hạn

`ArrayBlockingQueue<>(capacity)` hoặc `LinkedBlockingQueue<>(capacity)` tạo một ranh giới rõ hơn. Khi queue không nhận được việc mới, executor có thể thử tăng số luồng tới maximum.

Capacity lớn làm ứng dụng có nhiều chỗ đợi hơn trước khi nhánh mở rộng được dùng. Capacity nhỏ khiến mở rộng hoặc từ chối xảy ra sớm hơn. Không có lựa chọn đúng cho mọi tải; phải xét thời gian chờ chấp nhận được và bộ nhớ.

### SynchronousQueue

Queue này không có bộ đệm giữ phần tử; công việc cần được chuyển giao cho bên nhận. Nếu không chuyển giao được cho một luồng sẵn sàng, executor có thể tạo thêm luồng tới maximum, sau đó áp dụng handler từ chối.

Vì thế, cùng core và maximum nhưng thay queue có thể làm hành vi mở rộng khác hẳn.

## 7. Các kiểm tra đồng thời đằng sau sơ đồ đơn giản

Quy tắc core → queue → maximum là điểm khởi đầu, nhưng không mô tả mọi tình huống.

Trong triển khai OpenJDK, sau khi đưa một tác vụ vào queue thành công, executor kiểm tra lại trạng thái vì một luồng khác có thể vừa gọi shutdown. Nếu đã không còn nhận việc, nó có thể lấy lại tác vụ và từ chối.

Nếu tác vụ được xếp hàng mà không có luồng xử lý nào, executor còn thử tạo một luồng để queue không bị bỏ mặc. Điều này đặc biệt giúp hiểu cấu hình core bằng 0: không có nghĩa công việc được đưa vào queue sẽ vĩnh viễn không có ai xử lý.

Việc thử thêm luồng cũng có thể thất bại vì trạng thái thay đổi hoặc factory không tạo được luồng. Sơ đồ khái niệm không được đọc như bảo đảm tuyệt đối rằng mọi lần đi vào nhánh tạo luồng đều thành công.

Có thể đối chiếu các kiểm tra này tại phương thức `execute` trong [mã nguồn OpenJDK 25 của ThreadPoolExecutor](https://raw.githubusercontent.com/openjdk/jdk/jdk-25-ga/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java).

Đây là chi tiết triển khai giúp hiểu cơ chế; khi sử dụng API, vẫn phải dựa vào hợp đồng của lớp và handler đã cấu hình, không sao chép thuật toán để tự đưa việc vào queue.

### Không kiểm tra rồi gửi bằng hai thao tác riêng

Mẫu suy nghĩ “đọc queue thấy còn một chỗ, vậy lần execute tiếp theo chắc chắn nhận được” không đúng khi có nhiều bên gửi hoặc đang dừng executor. Trạng thái có thể đổi giữa hai bước.

Hãy để executor quyết định tiếp nhận và xử lý kết quả từ chối theo chính sách. Các số đo thích hợp cho giám sát, không phải một khóa đồng bộ thay thế.

## 8. Tăng giảm core và maximum khi đang chạy

Hai tham số có setter, nhưng cập nhật phải giữ quan hệ hợp lệ:

```text
0 <= corePoolSize <= maximumPoolSize
maximumPoolSize > 0
```

Nếu đang có core bằng 4, max bằng 8 và muốn tăng cả hai lên 12, không thể đặt core lên 12 trong khi maximum vẫn là 8. Thứ tự cập nhật phải giữ cấu hình hợp lệ ở mỗi bước.

Tương tự, muốn giảm maximum xuống dưới core hiện tại thì cần giảm core trước cho phù hợp.

### Thay đổi số cấu hình không giết công việc đang chạy

Giảm core hoặc maximum không có nghĩa luồng vượt ngưỡng bị ép kết thúc ngay giữa tác vụ. Các luồng dư được thu hồi khi đi vào trạng thái rảnh theo cơ chế quản lý của executor.

Tăng core có thể khiến executor khởi động thêm luồng để xử lý việc đã có trong queue. Tăng maximum chỉ cho phép mở rộng hơn khi quy tắc tiếp nhận đi tới nhánh tương ứng; nó không biến một queue luôn nhận được thành tín hiệu mở rộng tức thì.

Cấu hình động cần đi kèm đo tải và hiểu tác động; không tự thay đổi liên tục dựa trên một số đo ngắn hạn mà chưa có chính sách ổn định.

## 9. keepAliveTime liên hệ với các ngưỡng như thế nào?

Mặc định, thời gian rảnh dùng để thu hồi những luồng vượt core. Nếu nhóm đã tăng lên maximum trong một đợt tải rồi rảnh, số luồng có thể giảm về mức core.

Nếu bật `allowCoreThreadTimeOut(true)`, chính sách timeout có thể áp dụng cả luồng core; keepAliveTime phải lớn hơn 0. Khi ấy core không còn là cam kết rằng luôn có ít nhất bấy nhiêu luồng sống.

Điều này không thay đổi ý nghĩa core trong đường tiếp nhận việc mới: khi công việc quay lại, executor có thể tạo luồng trở lại theo nhu cầu.

`keepAliveTime` không phải timeout của một tác vụ đang chạy. Một tác vụ treo một giờ không bị dừng chỉ vì keepAliveTime là 30 giây; tham số này áp dụng cho thời gian luồng rảnh chờ việc.

## 10. Nhận hoặc từ chối chưa nói công việc thành công

Khi không thể nhận thêm, `RejectedExecutionHandler` quyết định hành vi. Ví dụ dùng `AbortPolicy` để nơi gửi nhìn thấy `RejectedExecutionException`.

Với handler khác, có thể xảy ra hành vi khác:

- `CallerRunsPolicy` có thể chạy công việc trên bên gửi khi executor chưa đóng.
- Handler bỏ việc có thể làm công việc không bao giờ được thực thi.
- Handler tùy biến phải có hợp đồng rõ về thông báo, hủy và kết quả.

`maximumPoolSize` giới hạn luồng trong nhóm, không giới hạn số bên gửi có thể tự chạy việc theo CallerRunsPolicy. Nếu nhiều bên gửi cùng thực hiện công việc bị từ chối, tổng công việc đang chạy trong ứng dụng có thể vượt con số maximum.

Với `submit`, còn phải phân biệt việc được nhận thành công với việc thân tác vụ sau đó thất bại. Nhận được Future không bảo đảm phép tính nghiệp vụ thành công; cần lấy và xử lý kết quả.

## 11. Cách chọn cấu hình có lý do

Không chọn core và maximum chỉ bằng cách điền hai số “nhỏ” và “lớn”.

Cần trả lời:

1. Công việc chủ yếu dùng CPU hay chờ tài nguyên bên ngoài?
2. Có bao nhiêu tài nguyên thật sự cho phép truy cập đồng thời?
3. Độ trễ chờ tối đa còn hữu ích là bao nhiêu?
4. Mỗi tác vụ chờ giữ lượng dữ liệu nào trong bộ nhớ?
5. Khi không nhận thêm, ứng dụng sẽ phản hồi ra sao?

Với CPU, số lõi khả dụng là một thông tin khởi đầu. Với I/O, cần xét thêm kết nối và khả năng hệ thống đích. Tăng maximum không tự giải quyết khóa dùng chung hoặc dịch vụ ngoài đã bão hòa.

Nếu yêu cầu là luôn dùng tối đa một mức luồng xác định, core và maximum bằng nhau tạo cấu hình cố định về số luồng xử lý. Nhưng vẫn phải giới hạn hoặc kiểm soát đầu vào cho queue.

Nếu muốn nhóm mở rộng khi đợt tải tới, cần chọn queue có hành vi phù hợp; chỉ đặt maximum lớn hơn core là chưa đủ.

## 12. Tự kiểm tra

1. Core bằng 3 nhưng mới tạo một luồng đang rảnh: tác vụ mới có thể làm thêm luồng không?
2. Tại sao queue không giới hạn thường làm maximum không phát huy?
3. Core 2, max 3, queue 1: vì sao việc thứ tư có thể bắt đầu trước việc thứ ba?
4. Giảm maximum có tự ngắt luồng đang chạy vượt ngưỡng mới không?
5. Core bằng 0 có đồng nghĩa executor không bao giờ tạo luồng không?
6. keepAliveTime có giới hạn thời gian chạy của tác vụ không?

**Gợi ý:** (1) Có, vì chưa đạt ngưỡng core. (2) Sau core, việc tiếp tục xếp hàng nên không đi tới nhánh mở rộng. (3) Việc thứ tư có thể được giao trực tiếp cho luồng mới. (4) Không. (5) Không. (6) Không, nó liên quan thời gian rảnh.

Để dự đoán việc tiếp theo được nhận thế nào, hãy kiểm tra theo thứ tự **số luồng so với core → khả năng nhận của queue → số luồng so với maximum → chính sách từ chối**, đồng thời nhớ trạng thái có thể thay đổi đồng thời.
