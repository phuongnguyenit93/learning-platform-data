# keepAliveTime và vòng đời luồng nhàn rỗi

## 1. Vì sao một nhóm luồng cần co lại?

Một nhóm luồng có thể mở rộng trong đợt tải cao rồi gặp khoảng thời gian không có công việc mới. Giữ mọi luồng nền tảng đã tạo giúp tránh chi phí khởi động lại, nhưng cũng giữ tài nguyên không còn cần thiết.

`keepAliveTime` của `ThreadPoolExecutor` tham gia quyết định khi nào một luồng **đang rảnh chờ công việc** có thể được thu hồi.

Nó không phải thời hạn chạy của tác vụ, không phải timeout chờ kết quả và không tự giới hạn thời gian một công việc nằm trong hàng đợi.

Để hiểu đúng, cần tách ba khoảng thời gian:

| Khoảng thời gian | Đối tượng đang chờ hoặc làm việc | Liên quan trực tiếp tới keepAliveTime? |
|---|---|---|
| Tác vụ đợi tới lượt trong queue | Tác vụ chưa chạy | Không |
| Tác vụ đang chạy, kể cả chặn I/O | Luồng đã được giao công việc | Không |
| Luồng chưa có công việc, chờ lấy việc từ queue | Luồng xử lý đang rảnh | Có, nếu luồng thuộc diện được timeout |

Một luồng đang chờ cơ sở dữ liệu trong thân tác vụ không được coi là “rảnh chờ việc” theo ý nghĩa quản lý này.

## 2. Mặc định: thu hồi luồng vượt mức core

Ví dụ khai báo minh họa:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,
        6,
        20, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(10));
```

Các lớp được import từ `java.util.concurrent`.

Cấu hình nói rằng:

- Nhóm có ngưỡng core bằng 2.
- Có thể mở rộng tới 6 luồng khi quy tắc nhận việc yêu cầu.
- Mặc định, khi số luồng đang có vượt core, những luồng dư đang rảnh có thể bị thu hồi sau khoảng chờ lấy việc theo keep-alive.
- Các luồng ở mức core không bị thu hồi chỉ vì rảnh trong cấu hình mặc định.

Giả sử đợt tải đã làm nhóm có 6 luồng. Sau khi công việc kết thúc và không có thêm việc, nhóm có thể giảm dần về mức 2.

Không hiểu “luồng dư” như một nhãn vĩnh viễn gắn vào từng đối tượng Thread. Chính sách dựa trên số lượng luồng và trạng thái chờ tại thời điểm xét; không có hợp đồng rằng một luồng tên cụ thể luôn là luồng core được giữ mãi.

Các quy tắc chính được mô tả trong [ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

### Không bảo đảm một mốc kết thúc theo đồng hồ tuyệt đối

Không nên khẳng định “đúng 20 giây sau dòng log tác vụ hoàn tất, số luồng chắc chắn bằng 2”. Luồng còn phải quay lại đường lấy công việc, hết khoảng chờ và được hệ thống cấp thời gian để kết thúc.

Keep-alive là chính sách chờ và thu hồi, không phải một hệ thống lập lịch thời gian thực. Trong quan sát hoặc kiểm thử, cần chờ điều kiện thích hợp trong một giới hạn, thay vì chụp số luồng ngay sau một khoảng sleep sát ngưỡng.

## 3. Thêm công việc trước khi hết thời gian rảnh

Luồng rảnh chờ việc không có nghĩa nó đã bị dừng. Nếu nhận được công việc trong lúc chờ, nó tiếp tục xử lý công việc ấy.

Sau khi xong, nó quay lại lấy việc theo chính sách hiện tại. Không nên coi keepAliveTime là “tuổi thọ tối đa của luồng tính từ lúc được tạo”.

Ví dụ một luồng có thể tồn tại hàng giờ nếu thường xuyên nhận việc, dù keepAliveTime chỉ là 30 giây. Điều đó không cho thấy cấu hình bị lỗi; luồng chưa trải qua điều kiện rảnh cần thiết để bị thu hồi.

### Những gì keepAliveTime không làm

```java
executor.submit(() -> {
    Thread.sleep(10_000);
    return "finished";
});
```

Đây là mã minh họa. Dù keepAliveTime của nhóm là 100 ms, nó không dùng tham số ấy để ngắt tác vụ ngủ 10 giây. Tác vụ đang giữ luồng thực thi, nên luồng đó không ở trạng thái chờ công việc mới của executor.

Nếu cần thời hạn cho phép tính, phải thiết kế timeout, hủy và phản hồi ngắt riêng, theo hợp đồng của công việc và các API được gọi.

## 4. allowCoreThreadTimeOut: cho phép thu hồi cả luồng core

Muốn chính sách rảnh áp dụng tới cả mức core, dùng:

```java
executor.allowCoreThreadTimeOut(true);
```

Điều kiện quan trọng: keepAliveTime phải **lớn hơn 0**. Bật core timeout với keep-alive bằng 0 là cấu hình không hợp lệ.

Khi đã bật:

- Các luồng core cũng có thể bị thu hồi khi không nhận việc trong khoảng chờ.
- Nếu không còn công việc, nhóm có thể co về 0.
- Executor vẫn có thể đang mở, chưa shutdown.
- Khi có công việc mới, nó có thể tạo luồng trở lại.

Vì thế, core bằng 2 không luôn đồng nghĩa có hai luồng sống mọi thời điểm. Core vẫn là ngưỡng trong quy tắc nhận việc; chính sách timeout quyết định có giữ chúng trong thời gian rảnh hay không.

### Chọn thứ tự cấu hình hợp lệ

Ví dụ:

```java
executor.setKeepAliveTime(5, TimeUnit.SECONDS);
executor.allowCoreThreadTimeOut(true);
```

Không bật core timeout khi keep-alive đang bằng 0 rồi kỳ vọng setter sau đó sẽ sửa lỗi. Mỗi lời gọi phải hợp lệ tại thời điểm thực hiện.

Nếu core timeout đang bật, đặt keepAliveTime về 0 cũng không hợp lệ. Muốn làm vậy, cần tắt core timeout trước và hiểu lại chính sách thu hồi sau thay đổi.

## 5. Các API để cấu hình và quan sát

| API | Ý nghĩa |
|---|---|
| `setKeepAliveTime(time, unit)` | Đổi khoảng chờ rảnh dùng cho timeout |
| `getKeepAliveTime(unit)` | Đọc giá trị theo đơn vị yêu cầu |
| `allowCoreThreadTimeOut(boolean)` | Bật hoặc tắt timeout cho core |
| `allowsCoreThreadTimeOut()` | Kiểm tra chính sách core timeout |
| `getPoolSize()` | Số luồng hiện có trong nhóm lúc quan sát |
| `getLargestPoolSize()` | Số luồng lớn nhất nhóm từng có, là thông tin lịch sử |
| `isShutdown()` | Đã yêu cầu đóng executor hay chưa |

Không nhầm `getLargestPoolSize()` với số luồng hiện tại. Nhóm từng tăng lên 6 rồi co về 2 vẫn có thể báo largest bằng 6.

Đọc keep-alive theo đơn vị quá thô có thể làm phần lẻ bị cắt. Ví dụ giá trị nhỏ hơn một giây có thể được báo là 0 khi đọc bằng đơn vị giây, dù cấu hình thực tế dương ở đơn vị mili giây. Chọn đơn vị phù hợp khi kiểm tra.

## 6. Chương trình Java 17+: luồng hết hạn rồi được tạo lại

Ví dụ đặt core và max đều bằng 1, bật core timeout và dùng ThreadFactory đặt tên luồng theo số lần tạo.

Để không đoán thời điểm bằng sleep, ThreadFactory bọc vòng đời của luồng xử lý: sau khi phần chạy của worker trả về, nó mở một chốt thông báo. Chốt này phục vụ quan sát trong thí nghiệm.

Lưu thành **`IdleWorkerDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class IdleWorkerDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger created = new AtomicInteger();
        CountDownLatch firstWorkerEnded = new CountDownLatch(1);

        ThreadFactory factory = worker -> {
            int number = created.incrementAndGet();
            return new Thread(() -> {
                try {
                    worker.run();
                } finally {
                    if (number == 1) {
                        firstWorkerEnded.countDown();
                    }
                }
            }, "idle-worker-" + number);
        };

        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1,
                1,
                100, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>(),
                factory);

        executor.allowCoreThreadTimeOut(true);

        try {
            Future<String> first = executor.submit(
                    () -> Thread.currentThread().getName());

            System.out.println(
                    "first task: " + first.get(5, TimeUnit.SECONDS));

            if (!firstWorkerEnded.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "First worker did not expire");
            }

            System.out.println(
                    "workers after idle: " + executor.getPoolSize());
            System.out.println(
                    "shutdown after idle: " + executor.isShutdown());

            Future<String> second = executor.submit(
                    () -> Thread.currentThread().getName());

            System.out.println(
                    "second task: " + second.get(5, TimeUnit.SECONDS));
            System.out.println(
                    "threads created: " + created.get());
        } finally {
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
}
```

Biên dịch và chạy:

```shell
javac --release 17 IdleWorkerDemo.java
java IdleWorkerDemo
```

Stdout chính xác:

```text
first task: idle-worker-1
workers after idle: 0
shutdown after idle: false
second task: idle-worker-2
threads created: 2
```

### Đọc kết quả

1. Tác vụ đầu chạy trên luồng đầu tiên được factory tạo.
2. Sau đó không có việc mới và core timeout được bật, nên worker kết thúc sau thời gian rảnh.
3. Chốt `firstWorkerEnded` chỉ được mở khi phần chạy worker đã trả về; lúc kiểm tra, nhóm không còn worker.
4. `isShutdown()` vẫn là false: hết luồng không phải đóng executor.
5. Gửi việc mới làm tạo `idle-worker-2`.

Số 100 ms chỉ giúp thí nghiệm diễn ra nhanh; nó không phải giá trị khuyến nghị cho môi trường thật. Các khoảng chờ năm giây là giới hạn để báo lỗi nếu không quan sát được tiến triển, không phải cách sắp xếp thứ tự bằng phỏng đoán.

Ví dụ không dùng số luồng ngay sau `Future.get()` để khẳng định worker đã được thu hồi. Nó chờ tín hiệu vòng đời riêng, vì nhận kết quả tác vụ và kết thúc luồng là hai sự kiện khác nhau.

`main` khai báo `throws Exception` để giữ ví dụ tập trung. Ứng dụng thực cần quyết định cách phản hồi lỗi lấy kết quả và ngắt tại tầng sở hữu executor.

## 7. Quan hệ với queue và mức mở rộng

Keep-alive chỉ thu hồi số luồng đã được tạo; nó không làm một cấu hình tự mở rộng tới maximum.

Giả sử core bằng 2, max bằng 8 nhưng dùng queue luôn còn chỗ. Nhóm thường chỉ tạo tới mức core trong hoạt động nhận việc thông thường. Keep-alive không khiến nó tự tạo thêm sáu luồng rồi mới thu hồi.

Nếu dùng queue hữu hạn và đợt tải làm nhóm mở rộng, lúc rảnh cơ chế thu hồi mới thể hiện rõ việc co từ mức cao về core, hoặc về 0 khi bật core timeout.

Khi queue còn công việc có thể thực thi ngay, cần phân tích lý do worker không nhận được việc thay vì chỉ tăng keepAliveTime. Công việc đã được giao nhưng chặn lâu, ThreadFactory có vấn đề hoặc một lớp queue/lập lịch chuyên biệt đều cần chẩn đoán riêng.

Không tự đưa Runnable vào `getQueue()` để đánh thức hay khởi động lại nhóm. Hãy dùng `execute` hoặc `submit` để giữ đúng quy trình tiếp nhận và vòng đời.

## 8. Liên hệ với các factory thông dụng

### Cached pool

`Executors.newCachedThreadPool()` tái sử dụng luồng rảnh và có thể tạo thêm khi cần. Theo cấu hình tiêu chuẩn, luồng không dùng trong 60 giây được thu hồi.

Mốc 60 giây không phải thời hạn cho một tác vụ. Một tác vụ chặn lâu vẫn có thể giữ luồng lâu hơn nhiều.

### Fixed pool

`newFixedThreadPool(n)` giữ cấu hình core và maximum bằng nhau. Theo thiết lập mặc định của factory, các luồng đã tạo không tự biến mất chỉ vì rảnh theo cơ chế thu hồi phần vượt core.

Không suy luận từ tên “pool” rằng mọi factory đều có cùng chính sách co giãn. Hợp đồng factory được mô tả tại [Executors API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html).

### Luồng ảo theo từng tác vụ

`newVirtualThreadPerTaskExecutor()` trên Java 21+ tạo một luồng ảo mới cho mỗi tác vụ; đó không phải nhóm luồng tái sử dụng điều chỉnh bằng keepAliveTime của ThreadPoolExecutor.

Không áp dụng việc giữ một số luồng rảnh trong pool nền tảng như một quy tắc chung cho mô hình mỗi tác vụ một luồng.

## 9. Chọn keep-alive theo chi phí và hình dạng tải

Giá trị nhỏ có thể giảm tài nguyên giữ trong khoảng yên ắng, nhưng nếu công việc tới thành từng đợt cách nhau ngắn, nhóm có thể liên tục hủy rồi tạo lại luồng.

Giá trị lớn giữ luồng lâu hơn, có thể giảm chi phí khởi động sau khoảng nghỉ, nhưng tài nguyên của những luồng không sử dụng tồn tại lâu hơn.

Cần đo những yếu tố phù hợp:

- Khoảng cách giữa các đợt công việc.
- Số luồng thường xuyên cần và số luồng chỉ cần lúc cao điểm.
- Chi phí tạo luồng và khởi tạo môi trường liên quan.
- Độ trễ của tác vụ đầu sau khoảng nghỉ.
- Mức sử dụng bộ nhớ và tần suất tạo/thu hồi luồng.

Không có con số duy nhất tối ưu cho mọi hệ thống. Nếu mục tiêu là giới hạn tải, keep-alive không thay thế maximum, dung lượng queue hoặc chính sách tiếp nhận.

### Không dùng timeout để chữa ThreadLocal bị giữ sai

Luồng được tái sử dụng có thể giữ dữ liệu ThreadLocal nếu công việc không dọn đúng. Thu hồi luồng sớm có thể làm hiện tượng ít lộ hơn nhưng không sửa trách nhiệm dọn dẹp.

Nếu tác vụ gắn dữ liệu theo yêu cầu vào ThreadLocal, cần xóa hoặc phục hồi trong `finally` theo hợp đồng của ứng dụng. Không đợi keep-alive thu hồi mới xem là đã giải phóng dữ liệu của yêu cầu.

## 10. Những thay đổi cấu hình và trường hợp đặc biệt

Đổi keepAliveTime bằng setter có thể ảnh hưởng việc chờ rảnh hiện tại, nhưng không dùng nó làm cam kết chính xác rằng một luồng cụ thể sẽ biến mất ở một mốc cố định.

Giảm core hoặc maximum cũng có thể làm một số luồng trở thành dư và được thu hồi khi rảnh. Nó không ép dừng tác vụ đang chạy giữa chừng.

### Scheduler có chính sách riêng

`ScheduledThreadPoolExecutor` dùng các luồng core và queue công việc trễ. Tài liệu của lớp khuyến cáo không đặt core về 0 hoặc bật core timeout một cách thông thường, vì có thể không còn luồng để xử lý việc khi tới thời điểm được phép chạy.

Vì vậy, không sao chép cấu hình core timeout của ví dụ sang scheduler chỉ vì lớp ấy kế thừa ThreadPoolExecutor.

Xem lưu ý trong [ScheduledThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html).

## 11. Thu hồi worker không thay thế shutdown

Khi các worker tự hết hạn, executor vẫn có thể nhận việc mới. Ngược lại, sau shutdown, mục tiêu là đóng vòng đời tiếp nhận và tiến tới kết thúc toàn bộ bộ thực thi.

Hai trạng thái cần tách:

```text
Không có worker nhưng executor đang mở:
    công việc mới có thể tạo worker

Executor đã shutdown:
    không dùng như một bộ thực thi mở để nhận việc mới
```

Không dựa vào core timeout để thay cho việc đóng một executor do thành phần mình sở hữu. Việc đóng cần được gọi rõ khi vòng đời thành phần kết thúc, kèm thời hạn chờ và chính sách nếu tác vụ không chịu dừng.

Một tác vụ đang chạy vô hạn không trở thành rảnh chỉ vì lâu không có đầu vào mới. Với nó, keep-alive không giúp executor kết thúc; cần giải quyết khả năng dừng của chính tác vụ.

## 12. Tự kiểm tra

1. KeepAliveTime là 2 giây: một tác vụ chạy 10 giây có bị dừng ở giây thứ hai không?
2. Mặc định, core bằng 3 và nhóm từng lên 7 luồng: khi hoàn toàn rảnh thường co về mức nào?
3. Bật core timeout với keep-alive bằng 0 có hợp lệ không?
4. Nhóm co về 0 có nghĩa đã shutdown chưa?
5. Vì sao kiểm tra pool size ngay sau khi Future trả kết quả chưa chứng minh được việc thu hồi?
6. Keep-alive nhỏ có luôn tốt hơn vì giữ ít luồng không?

**Gợi ý:** (1) Không. (2) Mức core, nếu không có thay đổi cấu hình hay sự kiện khác. (3) Không. (4) Chưa. (5) Worker còn phải quay lại chờ việc rồi mới có thể hết hạn. (6) Không; có thể tăng tần suất tạo lại luồng và độ trễ sau khoảng nghỉ.

KeepAliveTime điều khiển **việc giữ lại luồng đang chờ công việc**, và chỉ áp dụng tới các luồng được chính sách hiện tại cho phép timeout.
