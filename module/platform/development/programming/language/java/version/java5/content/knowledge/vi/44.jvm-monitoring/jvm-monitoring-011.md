# MemoryNotificationInfo và ngưỡng sử dụng bộ nhớ được hỗ trợ

## 1. Từ lấy mẫu đến nhận thông báo

Một tác vụ định kỳ có thể đọc mức dùng bộ nhớ rồi tự so sánh với ngưỡng. Cách khác là để JVM phát hiện điều kiện vượt ngưỡng ở một vùng bộ nhớ và phát **thông báo JMX** cho ứng dụng.

Thông báo giúp ứng dụng nhận tín hiệu để giảm tải, ghi nhận bằng chứng hoặc yêu cầu điều tra. Nó không phải lời hứa rằng luôn còn đủ thời gian cứu một lần cấp phát sắp thất bại. Cần phân biệt **dữ liệu sự kiện**, **chính sách đặt ngưỡng** và **hành động ứng dụng lựa chọn sau sự kiện**.

`MemoryMXBean` hỗ trợ thông báo về điều kiện bộ nhớ; `MemoryPoolMXBean` cho phép hỏi và cấu hình ngưỡng của từng pool khi JVM hỗ trợ. `MemoryNotificationInfo` là đối tượng mô tả dữ liệu trong thông báo, không tự đăng ký listener hay tự thiết lập ngưỡng. [MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html).

```text
Chọn pool và kiểm tra khả năng
    -> đăng ký listener trên MemoryMXBean
    -> cấu hình ngưỡng của pool
    -> JVM phát hiện điều kiện thích hợp
    -> Notification chứa dữ liệu CompositeData
    -> MemoryNotificationInfo.from(...)
    -> xử lý nhẹ và chuyển việc nặng ra ngoài callback
```

## 2. Hai loại ngưỡng trả lời hai câu hỏi khác nhau

| Loại | Câu hỏi | Kiểm tra khả năng | Đặt ngưỡng |
| --- | --- | --- | --- |
| Usage threshold | Mức dùng được JVM quan sát đã đạt/vượt ngưỡng chưa? | `isUsageThresholdSupported()` | `setUsageThreshold(bytes)` |
| Collection usage threshold | Sau nỗ lực thu hồi bộ nhớ, phần còn dùng đã đạt/vượt ngưỡng chưa? | `isCollectionUsageThresholdSupported()` | `setCollectionUsageThreshold(bytes)` |

Mỗi pool có thể hỗ trợ một loại, cả hai hoặc không hỗ trợ loại nào. Không lấy kết quả kiểm tra usage threshold để cho phép gọi setter của collection usage threshold. Ngưỡng tính bằng **byte**, phải không âm và không vượt mức tối đa của pool nếu mức tối đa được xác định. Giá trị 0 tắt kiểm tra vượt ngưỡng tương ứng; ngưỡng dương bật khả năng kiểm tra đó. [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html).

Việc đặt ngưỡng không cấp thêm bộ nhớ, không thay `-Xmx` và không áp đặt hạn mức cứng cho mỗi lệnh cấp phát. Một vùng được thiết kế để thường xuyên đầy rồi thu gom cần chính sách khác với vùng chứa dữ liệu tồn tại lâu.

Đối với ngưỡng sau thu gom, “sau thu gom” nói tới nỗ lực thu hồi của JVM trong pool đó. Không mặc định đó là sau một lần Full GC cho toàn bộ tiến trình, và cũng không cần chủ động gọi GC để đọc hoặc nhận cơ chế thông báo này.

## 3. Nguồn phát là MemoryMXBean, dữ liệu nói pool nào

Đăng ký listener cục bộ vào đối tượng phát:

```java
NotificationEmitter emitter =
        (NotificationEmitter) ManagementFactory.getMemoryMXBean();
```

Không ép `MemoryPoolMXBean` thành `NotificationEmitter` để mong nhận sự kiện của pool. Pool chịu trách nhiệm cấu hình ngưỡng; thông báo bộ nhớ được phát từ MemoryMXBean và dữ liệu cho biết pool liên quan.

Hai loại chuẩn:

```java
MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED
MemoryNotificationInfo.MEMORY_COLLECTION_THRESHOLD_EXCEEDED
```

Listener nên lọc loại trước khi đọc dữ liệu. Một nguồn JMX có thể phát nhiều loại thông báo; không suy rằng mọi `userData` đều mang cùng cấu trúc. [MemoryNotificationInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryNotificationInfo.html).

`Notification` là vỏ sự kiện với các trường như loại, nguồn, số thứ tự, dấu thời gian và `userData`. Số thứ tự của vỏ sự kiện không phải bộ đếm vượt ngưỡng của pool. Khi ghi bằng chứng, giữ rõ nguồn và loại, thay vì chỉ ghi một con số “count” không có ngữ cảnh. [Notification](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html).

## 4. Giải mã MemoryNotificationInfo

Dữ liệu bộ nhớ được mang trong `Notification.getUserData()` dưới dạng `CompositeData`, một cấu trúc kiểu mở của JMX. Không ép trực tiếp `userData` thành `MemoryNotificationInfo`.

Đoạn minh họa:

```java
if (notification.getUserData() instanceof CompositeData data) {
    MemoryNotificationInfo info = MemoryNotificationInfo.from(data);
    if (info != null) {
        String poolName = info.getPoolName();
        long usedBytes = info.getUsage().getUsed();
        long count = info.getCount();
    }
}
```

Dữ liệu chính gồm:

| Trường | Cách hiểu |
| --- | --- |
| `getPoolName()` | Tên pool gây thông báo |
| `getUsage()` | Ảnh chụp MemoryUsage khi thông báo được dựng |
| `getCount()` | Số đếm vượt ngưỡng tương ứng khi thông báo được dựng |

`MemoryUsage` chứa `init`, `used`, `committed`, `max` theo byte. `max` có thể không xác định và mang giá trị `-1`; nếu tính tỷ lệ thì phải kiểm tra mẫu số. Không đọc lại pool rồi coi giá trị mới là chính ảnh chụp của sự kiện: ứng dụng và GC có thể đã làm bộ nhớ thay đổi. [MemoryUsage](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html).

`from()` chuyển đổi theo cấu trúc được quy định; `CompositeData` không đúng hợp đồng có thể làm chuyển đổi thất bại. Kiểm tra kiểu giúp tránh ép sai lớp, nhưng không thay thế kiểm tra cấu trúc dữ liệu. [CompositeData](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html), [MemoryNotificationInfo.from](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryNotificationInfo.html#from(javax.management.openmbean.CompositeData)).

## 5. Vì sao ở trên ngưỡng không có nghĩa nhận liên tục?

Với usage threshold, khi mức dùng đạt/vượt ngưỡng, JVM có thể phát thông báo cho đợt vượt đó. Việc mức dùng cứ ở cao không tạo một thông báo định kỳ sau mỗi giây. Để có đợt vượt tiếp theo, mức dùng cần xuống dưới ngưỡng rồi đạt/vượt lại.

Ví dụ chính sách có ngưỡng 800 MiB:

```text
Mức dùng: 700 -> 850 -> 900 -> 750 -> 830 MiB
Đợt vượt:        lần 1                  lần 2
```

Đây là sơ đồ khái niệm; không cam kết JVM lấy mẫu đúng từng điểm hay phát ngay tại mỗi mốc. Cơ chế kiểm tra chạy tại các thời điểm JVM cho là phù hợp.

Collection usage threshold có ý nghĩa riêng: quan sát phần còn dùng sau nỗ lực thu hồi và bộ đếm phát hiện tương ứng. Không dùng quy tắc “chỉ một thông báo cho cả giai đoạn ở cao” của usage threshold để suy đoán máy móc mọi sự kiện sau thu gom. [MemoryNotificationInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryNotificationInfo.html).

Khi cần hiển thị “hệ thống vẫn đang ở trạng thái cao”, kết hợp sự kiện với lấy mẫu thưa và trạng thái cảnh báo của ứng dụng. Tách trạng thái đang cao khỏi số thông báo đã nhận để tránh báo “đã bình thường” chỉ vì một thời gian không có sự kiện mới.

## 6. Ví dụ Java hoàn chỉnh: đăng ký và quan sát có giới hạn

Chương trình Java 17+ sau chọn một heap pool hỗ trợ usage threshold, có `max` xác định; đăng ký listener trước rồi đặt ngưỡng xấp xỉ 80% giới hạn. Nó quan sát trong khoảng hai giây và khôi phục ngưỡng cũ khi kết thúc.

**Chạy trong JVM riêng của ví dụ.** Ngưỡng là cấu hình dùng chung của pool trong JVM, không phải cấu hình riêng tư của listener. Mã minh họa giả định không có thành phần khác cùng thay ngưỡng đó.

Lưu thành `MemoryThresholdWatch.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryNotificationInfo;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.util.Comparator;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationEmitter;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;
import javax.management.openmbean.CompositeData;

public class MemoryThresholdWatch {
    record Event(String type, MemoryNotificationInfo info) {}

    static boolean supportedType(String type) {
        return MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED.equals(type)
                || MemoryNotificationInfo.MEMORY_COLLECTION_THRESHOLD_EXCEEDED
                        .equals(type);
    }

    static MemoryNotificationInfo decode(Notification notification) {
        if (!supportedType(notification.getType())
                || !(notification.getUserData() instanceof CompositeData data)) {
            return null;
        }
        return MemoryNotificationInfo.from(data);
    }

    public static void main(String[] args) throws Exception {
        MemoryPoolMXBean pool = ManagementFactory.getMemoryPoolMXBeans()
                .stream()
                .filter(p -> p.getType() == MemoryType.HEAP)
                .filter(MemoryPoolMXBean::isUsageThresholdSupported)
                .sorted(Comparator.comparing(MemoryPoolMXBean::getName))
                .findFirst().orElse(null);
        MemoryUsage usage = pool == null ? null : pool.getUsage();
        if (usage == null || usage.getMax() <= 0) {
            System.out.println("SKIPPED: no suitable heap pool");
            return;
        }

        String poolName = pool.getName();
        long threshold = usage.getMax() - usage.getMax() / 5;
        long previous = pool.getUsageThreshold();
        ArrayBlockingQueue<Event> events = new ArrayBlockingQueue<>(16);
        AtomicLong dropped = new AtomicLong();
        AtomicLong decodeErrors = new AtomicLong();
        NotificationEmitter emitter =
                (NotificationEmitter) ManagementFactory.getMemoryMXBean();
        NotificationFilter filter =
                n -> supportedType(n.getType());
        NotificationListener listener = (notification, handback) -> {
            try {
                MemoryNotificationInfo info = decode(notification);
                if (info != null && poolName.equals(info.getPoolName())
                        && !events.offer(new Event(notification.getType(), info))) {
                    dropped.incrementAndGet();
                }
            } catch (IllegalArgumentException ex) {
                decodeErrors.incrementAndGet();
            }
        };

        emitter.addNotificationListener(listener, filter, null);
        int processed = 0;
        try {
            pool.setUsageThreshold(threshold);
            System.out.println("Watching pool=" + poolName);
            System.out.println("Usage threshold bytes=" + threshold);
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
            while (System.nanoTime() - deadline < 0) {
                Event event = events.poll(100, TimeUnit.MILLISECONDS);
                if (event != null) {
                    processed++;
                    MemoryNotificationInfo info = event.info();
                    System.out.println(event.type() + " | pool=" +
                            info.getPoolName() + " | used=" +
                            info.getUsage().getUsed() + " | count=" +
                            info.getCount());
                }
            }
        } finally {
            try {
                emitter.removeNotificationListener(listener, filter, null);
            } finally {
                if (pool.isValid()) {
                    pool.setUsageThreshold(previous);
                }
            }
        }
        System.out.println("Events processed=" + processed);
        System.out.println("Dropped events=" + dropped.get());
        System.out.println("Decode errors=" + decodeErrors.get());
    }
}
```

Biên dịch và chạy:

```shell
javac MemoryThresholdWatch.java
java -Xmx128m MemoryThresholdWatch
```

Một lần chạy thực tế trên JDK 24 dùng G1 in:

```text
Watching pool=G1 Old Gen
Usage threshold bytes=107374183
Events processed=0
Dropped events=0
Decode errors=0
```

Đây không phải đầu ra bắt buộc của mọi JVM. Tên pool, giới hạn và số sự kiện có thể khác. Nếu không có pool phù hợp, chương trình in:

```text
SKIPPED: no suitable heap pool
```

### Đọc đúng kết quả

`Events processed=0` là kết quả hợp lệ: ví dụ không cố cấp phát bộ nhớ để ép vượt ngưỡng. Chạy xong chứng minh đường đăng ký, đặt ngưỡng, chờ và dọn dẹp đã thực hiện; **chưa chứng minh JVM đã phát một sự kiện vượt ngưỡng trong lần chạy đó**.

80% là lựa chọn minh họa. Biểu thức `max - max / 5` tránh nhân nguyên có nguy cơ tràn số; nó làm tròn theo byte nên không nhất thiết đúng một số phần trăm tròn tuyệt đối. Trong ứng dụng thật, chọn pool theo chính sách rõ ràng, không lấy pool đầu tiên theo thứ tự tên chỉ vì ví dụ làm như vậy.

Listener lọc cả hai loại chuẩn và chỉ nhận dữ liệu của pool đã chọn. Chương trình chỉ cấu hình usage threshold; nó không tự thiết lập collection usage threshold.

Callback giải mã rồi đưa đối tượng nhỏ vào hàng đợi có giới hạn 16 phần tử. `offer()` báo thất bại khi không còn chỗ, nên mã tăng bộ đếm bỏ sự kiện thay vì chặn chờ chỗ trống. Phần in console nằm ở luồng chính. [BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Cửa sổ xử lý chỉ kéo dài khoảng hai giây; số đã xử lý không phải tổng số JVM từng phát. Với hệ thống giám sát chạy lâu dài, cần thiết kế vòng đời consumer, cách xử lý phần còn trong hàng đợi khi dừng và chính sách khi nguồn gửi nhanh hơn tốc độ xử lý.

## 7. Ví dụ giải mã xác định, không cần làm cạn bộ nhớ

Để kiểm tra đường `MemoryNotificationInfo.from()` mà không phụ thuộc GC hoặc tải thật, có thể dựng dữ liệu `CompositeData` theo đúng schema và gọi hàm `decode()` của ví dụ trên.

Đây là **sự kiện mô phỏng**. Nó không đến từ JVM, không kích hoạt một ngưỡng thật và không chứng minh khả năng phát sự kiện của một pool. `CompositeDataSupport` cho phép dựng cấu trúc với tên trường và kiểu mở được chỉ rõ. [CompositeDataSupport](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeDataSupport.html).

Lưu thêm `MemoryInfoDecodeDemo.java` cùng thư mục với tệp trước:

```java
import java.lang.management.MemoryNotificationInfo;
import javax.management.Notification;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

public class MemoryInfoDecodeDemo {
    public static void main(String[] args) throws Exception {
        String[] memoryFields = {"init", "used", "committed", "max"};
        CompositeType memoryType = new CompositeType(
                "java.lang.management.MemoryUsage", "Memory usage",
                memoryFields, memoryFields,
                new OpenType<?>[] {SimpleType.LONG, SimpleType.LONG,
                        SimpleType.LONG, SimpleType.LONG});
        CompositeData usage = new CompositeDataSupport(
                memoryType, memoryFields, new Object[] {0L, 850L, 900L, 1000L});

        String[] infoFields = {"poolName", "usage", "count"};
        CompositeType infoType = new CompositeType(
                "java.lang.management.MemoryNotificationInfo", "Memory event",
                infoFields, infoFields,
                new OpenType<?>[] {SimpleType.STRING, memoryType,
                        SimpleType.LONG});
        CompositeData data = new CompositeDataSupport(
                infoType, infoFields, new Object[] {"example-pool", usage, 1L});

        Notification notification = new Notification(
                MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED, "demo", 1L);
        notification.setUserData(data);
        MemoryNotificationInfo info = MemoryThresholdWatch.decode(notification);
        if (info == null) {
            throw new IllegalStateException("No decoded information");
        }
        System.out.println("Synthetic pool=" + info.getPoolName());
        System.out.println("Used bytes=" + info.getUsage().getUsed());
        System.out.println("Count=" + info.getCount());
    }
}
```

Chạy:

```shell
javac MemoryThresholdWatch.java MemoryInfoDecodeDemo.java
java MemoryInfoDecodeDemo
```

Stdout chính xác:

```text
Synthetic pool=example-pool
Used bytes=850
Count=1
```

Ảnh chụp mô phỏng có `used=850`, `committed=900`, `max=1000`, đúng quan hệ dung lượng hợp lệ. Chương trình đi qua bước xác minh loại sự kiện, kiểm tra `CompositeData` và chuyển đổi sang đối tượng chuyên biệt. Đừng bỏ bước này rồi tự ép các trường mà chưa kiểm tra cấu trúc.

## 8. Giữ callback nhẹ và quản lý vòng đời listener

`NotificationListener.handleNotification()` cần trả về nhanh để tránh chặn nguồn phát. Khi bộ nhớ đang chịu áp lực, một callback tạo báo cáo lớn, chụp heap, gửi mạng đồng bộ hoặc đợi khóa lâu có thể làm tình hình xấu hơn. [NotificationListener](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html).

Nên thực hiện một số việc nhỏ: nhận diện loại, đọc pool và mức dùng, ghi vào cấu trúc có giới hạn hoặc đánh dấu trạng thái. Công việc tốn tài nguyên cần đi qua cơ chế điều phối có giới hạn, gộp yêu cầu trùng và có cách báo khi đã bỏ bớt sự kiện. Không thay một callback nhẹ bằng hàng đợi vô hạn.

Dùng đúng bộ ba `listener, filter, handback` để gỡ một đăng ký cụ thể bằng `NotificationEmitter.removeNotificationListener(...)`. Đăng ký trùng cùng listener có thể dẫn tới nhiều lần nhận; không đăng ký lại trong mỗi vòng lấy mẫu. Luồng gọi callback phụ thuộc triển khai, nên dữ liệu chia sẻ giữa callback và consumer phải an toàn cho truy cập đồng thời. [NotificationEmitter](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationEmitter.html).

Nếu ứng dụng khác cũng quản lý ngưỡng, không tự khôi phục một giá trị cũ rồi ghi đè cấu hình mới của bên đó. Cần có một nơi chịu trách nhiệm cho chính sách ngưỡng và vòng đời đăng ký. Ví dụ JVM riêng ở trên có thể khôi phục trực tiếp vì quyền quản lý đã được giới hạn rõ.

## 9. Chính sách vận hành và các giới hạn

Chọn ngưỡng dựa trên pool, tải bình thường, giới hạn tài nguyên và thời gian cần phản ứng. Một mức đặt quá thấp có thể tạo tín hiệu ít giá trị; đặt quá sát giới hạn có thể không còn khoảng đệm để xử lý. Với pool không có `max`, chỉ dùng ngưỡng byte tuyệt đối nếu đã hiểu phạm vi và có chính sách phù hợp; không giả định `-1` là dung lượng để nhân tỷ lệ.

Thông báo có thể hỗ trợ giảm nhận việc mới, giảm công việc nền hoặc bật điều tra có kiểm soát. Nó không tự chứng minh rò rỉ và không bảo đảm tránh mọi `OutOfMemoryError`. Tài nguyên ngoài heap, tốc độ tăng đột biến và khả năng JVM kiểm tra ngưỡng đều ảnh hưởng tới kết quả.

Theo dõi bằng chứng tối thiểu: JVM nào, thời điểm, loại sự kiện, pool, `used/committed/max`, số đếm và hành động đã áp dụng. Đừng đồng nhất số đếm trong `MemoryNotificationInfo`, số thứ tự của `Notification` và số callback ứng dụng đã xử lý. Chúng trả lời những câu hỏi khác nhau.

Nếu dùng JMX từ xa, kết nối và truyền thông báo có vòng đời riêng; cần xử lý mất kết nối và đối chiếu trạng thái hiện tại sau khi kết nối lại. Đăng ký listener không thay thế việc theo dõi sức khỏe của đường truyền giám sát.

## 10. Lỗi thường gặp và bài tập

| Lỗi | Cách sửa |
| --- | --- |
| Đăng ký nhận thông báo trên pool thay vì nguồn bộ nhớ | Dùng MemoryMXBean hoặc ObjectName tương ứng khi qua JMX |
| Đặt mọi loại ngưỡng cho mọi pool | Kiểm tra từng khả năng riêng |
| Coi 0 là ngưỡng báo ngay khi dùng bộ nhớ | 0 tắt kiểm tra vượt ngưỡng |
| Ép `userData` thành MemoryNotificationInfo | Nhận CompositeData rồi gọi `from()` |
| Không có thông báo trong hai giây nên kết luận hệ thống hỏng | Kiểm tra hỗ trợ, cấu hình, loại sự kiện và điều kiện quan sát |
| Gửi mạng hoặc tạo báo cáo lớn trong callback | Chuyển sang xử lý có giới hạn ngoài callback |
| Không gỡ listener khi thành phần dừng | Gắn đăng ký và gỡ đăng ký vào vòng đời rõ ràng |
| Sự kiện mô phỏng giải mã được nên khẳng định ngưỡng thật hoạt động | Tách kiểm tra schema khỏi kiểm tra tích hợp với JVM |

Bài tập:

1. Chạy chương trình quan sát trên JVM riêng; ghi rõ pool và khả năng hỗ trợ thực tế, kể cả trường hợp không có sự kiện.
2. Chạy ví dụ giải mã rồi thay `count` bằng một số hợp lệ khác; giải thích vì sao số đó không phải số callback mà chương trình vừa nhận.
3. Thiết kế trạng thái cảnh báo “bộ nhớ còn cao” kết hợp sự kiện và lấy mẫu, sao cho không phát lặp thông báo mỗi lần đọc.
4. Nêu cách gỡ listener và xử lý hàng đợi khi thành phần giám sát dừng, kể cả lúc phần xử lý phía sau đang chậm.

Hiểu rõ nguồn phát, điều kiện hỗ trợ, dữ liệu ảnh chụp và vòng đời xử lý giúp bạn dùng thông báo bộ nhớ như một tín hiệu vận hành có giới hạn rõ ràng.
