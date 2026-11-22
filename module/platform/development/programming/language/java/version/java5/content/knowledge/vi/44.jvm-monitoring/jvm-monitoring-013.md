# Thuộc tính, thao tác và thông báo của MBean ứng dụng

## 1. Ba cách tương tác với một thành phần được quản lý

Ngoài các MXBean có sẵn của JVM, ứng dụng có thể đưa chính thành phần của mình ra giao diện quản lý JMX dưới dạng **MBean**.

Ví dụ, một bộ theo dõi xử lý công việc cần cho người vận hành:

- Đọc số công việc đã hoàn thành và đổi tên hiển thị.
- Chủ động đặt lại thống kê.
- Nhận sự kiện khi tên hiển thị thay đổi hoặc khi thống kê được đặt lại.

Ba nhu cầu này tương ứng với:

| Thành phần giao diện | Vai trò | Ví dụ |
|---|---|---|
| Thuộc tính (attribute) | Đọc hoặc ghi một giá trị quản lý có tên/kiểu rõ ràng | `CompletedCount`, `DisplayName` |
| Thao tác (operation) | Yêu cầu thực hiện một hành động | `resetStatistics()` |
| Thông báo (notification) | Thành phần phát sự kiện đến các bên đã đăng ký nhận | Sự kiện đổi tên hoặc đặt lại thống kê |

MBean là đối tượng được quản lý có tên đăng ký trong MBeanServer. Việc gọi thuộc tính/thao tác đi qua giao diện quản lý; không có nghĩa mọi phương thức public của đối tượng đều được đưa ra JMX. [Gói javax.management](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/package-summary.html)

Bài dùng **Standard MBean** và API JMX hiện hành trên Java 17+. Không cần Spring hoặc mở cổng JMX từ xa để chạy ví dụ.

## 2. Thuộc tính: hợp đồng đọc/ghi, không phải phơi bày field

Với Standard MBean, các mẫu phương thức trong giao diện quản lý xác định thuộc tính:

~~~java
String getDisplayName();
void setDisplayName(String value);
long getCompletedCount();
~~~

Đây là các khai báo minh họa bên trong interface, chưa phải một tệp Java độc lập.

Chúng tạo ra:

| Tên thuộc tính JMX | Kiểu | Khả năng |
|---|---|---|
| `DisplayName` | `java.lang.String` | Đọc và ghi |
| `CompletedCount` | `long` | Chỉ đọc |

Tên thuộc tính ở đây bắt đầu bằng chữ hoa theo phần hậu tố của getter/setter. Dùng `getAttribute(name, "DisplayName")`, không truyền tên field `displayName` hoặc chuỗi `getDisplayName()`.

Getter và setter của cùng một thuộc tính phải nhất quán kiểu. Với thuộc tính boolean, mẫu `boolean isEnabled()` cũng có thể xác định getter.

Một thuộc tính quản lý không nhất thiết là một field được trả nguyên trạng. Getter có thể đọc thống kê từ thành phần khác; setter có thể kiểm tra ràng buộc trước khi áp dụng cấu hình. Tuy vậy, getter nên có ngữ nghĩa đọc rõ ràng và chi phí phù hợp, không âm thầm thực hiện công việc dài hoặc tác động khó dự đoán.

Setter cũng không tự bảo đảm giá trị hợp lệ chỉ vì lời gọi đi qua JMX. Lớp triển khai vẫn phải kiểm tra các điều kiện nghiệp vụ như chuỗi không rỗng, giới hạn cấu hình hoặc quan hệ giữa các tham số.

## 3. Thao tác: diễn đạt một hành động tường minh

Trong giao diện Standard MBean, phương thức không thuộc mẫu thuộc tính trở thành operation. Ví dụ:

~~~java
void resetStatistics();
~~~

Đặt lại thống kê là một hành động, không phải “đặt thuộc tính Reset thành true”. Một operation có thể nhận tham số và trả kết quả; cần mô tả rõ tác dụng phụ, điều kiện gọi và ý nghĩa thành công.

Các getter/setter đã xác định attribute không đồng thời trở thành operations chỉ vì chúng là phương thức Java. Khi gọi qua MBeanServer, dùng đúng đường truy cập:

~~~text
Đọc trạng thái      -> getAttribute
Ghi cấu hình        -> setAttribute
Thực hiện hành động -> invoke
~~~

Với `invoke`, tên thao tác và chữ ký tham số phải khớp. Chữ ký chứa tên kiểu Java; tham số nguyên thủy int dùng `"int"`, không thay bằng `"java.lang.Integer"` chỉ vì giá trị trong mảng Object đã được boxing. Operation không có tham số có thể được gọi với mảng đối số và mảng chữ ký đều rỗng. [MBeanServer](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/MBeanServer.html)

Không đưa hành động có phạm vi quá lớn vào một operation mơ hồ như `execute(String command)` khi có thể thiết kế một giao diện hẹp, có kiểu và dễ kiểm tra hơn.

## 4. Thông báo: sự kiện phải được triển khai chủ động

Thuộc tính thay đổi không tự động sinh notification. **MBean phải tự tạo và phát thông báo.** `AttributeChangeNotification` là lớp chuẩn để mô tả thay đổi thuộc tính, gồm tên/kiểu thuộc tính, giá trị cũ và giá trị mới. [AttributeChangeNotification](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/AttributeChangeNotification.html)

Một `Notification` thông thường có các phần chính:

| Trường | Ý nghĩa |
|---|---|
| `type` | Loại sự kiện dạng chuỗi, ví dụ `example.jobs.statistics.reset` |
| `source` | Nguồn phát; nên dùng ObjectName của MBean |
| `sequenceNumber` | Số thứ tự do nguồn phát quản lý |
| `timeStamp` | Mốc thời gian tạo/phát sự kiện theo thiết kế |
| `message` | Nội dung mô tả cho người đọc |
| `userData` | Dữ liệu bổ sung có hợp đồng kiểu/ngữ nghĩa rõ ràng |

Không dùng message làm mã loại sự kiện để công cụ phải phân tích câu chữ. Type dành cho phân loại; message dành cho mô tả. Khi dữ liệu đi qua JMX từ xa, ưu tiên dữ liệu đơn giản, tương thích giữa hai phía, thay vì nhét cả đối tượng dịch vụ vào userData. [Notification](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/Notification.html)

`NotificationBroadcasterSupport` cung cấp việc đăng ký/hủy listener và gửi sự kiện. `MBeanNotificationInfo` mô tả các loại thông báo mà MBean có thể phát để công cụ khám phá. **Khai báo metadata không thay thế lời gọi sendNotification.**

## 5. Ví dụ đầy đủ: bộ theo dõi công việc

Ví dụ có hai mặt hoạt động:

- Ứng dụng gọi `recordCompleted()` để ghi nhận công việc hoàn thành.
- Công cụ quản lý đọc/ghi các thuộc tính, gọi `resetStatistics()` và đăng ký listener qua MBeanServer.

`recordCompleted()` không nằm trong giao diện quản lý, nên không được đưa ra thành operation JMX. Điều này minh họa ranh giới giữa API nội bộ của thành phần và API quản lý.

### Tệp 1: JobMonitorMBean.java

Giao diện quản lý phải public. Với quy ước Standard MBean đang dùng, tên interface là tên lớp triển khai cộng hậu tố MBean, cùng package.

~~~java
public interface JobMonitorMBean {
    String getDisplayName();
    void setDisplayName(String value);
    long getCompletedCount();
    void resetStatistics();
}
~~~

### Tệp 2: JobMonitor.java

Lớp bảo vệ trạng thái dùng chung bằng synchronized. Nó tạo sự kiện khi cập nhật trạng thái, rồi gửi sau khi đã ra khỏi vùng giữ khóa.

~~~java
import java.util.Objects;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import javax.management.ObjectName;

public class JobMonitor extends NotificationBroadcasterSupport
        implements JobMonitorMBean {
    public static final String RESET_TYPE = "example.jobs.statistics.reset";

    private final ObjectName source;
    private String displayName = "jobs";
    private long completedCount;
    private long sequence;

    public JobMonitor(ObjectName source) {
        super(
            new MBeanNotificationInfo(
                new String[] { AttributeChangeNotification.ATTRIBUTE_CHANGE },
                AttributeChangeNotification.class.getName(),
                "A management attribute changed"),
            new MBeanNotificationInfo(
                new String[] { RESET_TYPE },
                Notification.class.getName(),
                "Statistics were reset")
        );
        this.source = Objects.requireNonNull(source);
    }

    @Override
    public synchronized String getDisplayName() {
        return displayName;
    }

    @Override
    public void setDisplayName(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("DisplayName must not be blank");
        }

        Notification event;
        synchronized (this) {
            if (displayName.equals(value)) {
                return;
            }
            String previous = displayName;
            displayName = value;
            event = new AttributeChangeNotification(
                source, ++sequence, System.currentTimeMillis(),
                "Display name changed", "DisplayName",
                String.class.getName(), previous, value);
        }
        sendNotification(event);
    }

    @Override
    public synchronized long getCompletedCount() {
        return completedCount;
    }

    public synchronized void recordCompleted() {
        completedCount++;
    }

    @Override
    public void resetStatistics() {
        Notification event;
        synchronized (this) {
            long previous = completedCount;
            completedCount = 0;
            event = new Notification(
                RESET_TYPE, source, ++sequence, System.currentTimeMillis(),
                "Statistics reset");
            event.setUserData(previous);
        }
        sendNotification(event);
    }
}
~~~

Các quyết định trong lớp:

- `DisplayName` không chấp nhận null hoặc chuỗi chỉ có khoảng trắng.
- Gán lại đúng tên hiện tại không thay đổi trạng thái nên không phát sự kiện đổi tên.
- `CompletedCount` không có setter trong MBean interface, vì thế là thuộc tính chỉ đọc qua JMX.
- `recordCompleted()` là đường cập nhật từ ứng dụng, không phải operation JMX.
- `resetStatistics()` đặt bộ đếm về 0 và phát sự kiện riêng, mang giá trị cũ trong userData.
- Sequence number dùng chung cho các sự kiện của đối tượng này và được tăng trong cùng vùng bảo vệ trạng thái.
- Source dùng đúng ObjectName sẽ được đăng ký, giúp listener nhận diện nguồn.

### Tệp 3: MBeanAppDemo.java

Chương trình đăng ký MBean, thêm listener, thực hiện các tương tác rồi dọn đăng ký do mình tạo.

~~~java
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import javax.management.Attribute;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class MBeanAppDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName("example.jobs:type=JobMonitor,name=main");
        JobMonitor monitor = new JobMonitor(name);

        NotificationListener listener = (event, handback) -> {
            if (event instanceof AttributeChangeNotification change) {
                System.out.println("attribute.event="
                        + change.getAttributeName() + ": "
                        + change.getOldValue() + " -> "
                        + change.getNewValue());
            } else {
                System.out.println("operation.event=" + event.getType()
                        + ", previous=" + event.getUserData());
            }
        };

        server.registerMBean(monitor, name);
        try {
            server.addNotificationListener(name, listener, null, null);
            try {
                System.out.println("display.before="
                        + server.getAttribute(name, "DisplayName"));
                server.setAttribute(name,
                        new Attribute("DisplayName", "billing-worker"));

                monitor.recordCompleted();
                monitor.recordCompleted();
                System.out.println("completed.before="
                        + server.getAttribute(name, "CompletedCount"));

                boolean exposed = Arrays.stream(
                        server.getMBeanInfo(name).getOperations())
                        .anyMatch(op -> op.getName().equals("recordCompleted"));
                System.out.println("recordCompleted.exposed=" + exposed);

                server.invoke(name, "resetStatistics",
                        new Object[0], new String[0]);
                System.out.println("completed.after="
                        + server.getAttribute(name, "CompletedCount"));
            } finally {
                server.removeNotificationListener(name, listener);
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
~~~

Biên dịch và chạy cả ba tệp trong cùng thư mục với JDK 17+:

~~~shell
javac JobMonitorMBean.java JobMonitor.java MBeanAppDemo.java
java MBeanAppDemo
~~~

Stdout đã kiểm chứng khi chạy trên OpenJDK 24:

~~~text
display.before=jobs
attribute.event=DisplayName: jobs -> billing-worker
completed.before=2
recordCompleted.exposed=false
operation.event=example.jobs.statistics.reset, previous=2
completed.after=0
~~~

Không có kết nối mạng hay dịch vụ ngoài trong ví dụ. Listener ở cùng JVM và nhận thông báo do chính thành phần mẫu phát.

## 6. Đọc chuỗi kết quả theo đúng ba loại tương tác

1. `display.before=jobs` đến từ việc đọc attribute DisplayName.
2. `setAttribute` gọi setter, đổi trạng thái rồi phát AttributeChangeNotification; listener in giá trị cũ/mới.
3. Hai lần gọi API ứng dụng `recordCompleted()` làm bộ đếm thành 2.
4. `recordCompleted.exposed=false` kiểm tra MBeanInfo, xác nhận phương thức đó không xuất hiện trong operations.
5. `invoke` yêu cầu resetStatistics. Chính phần triển khai operation tạo thông báo riêng, không phải MBeanServer tự phát thông báo cho mọi operation.
6. Lần đọc CompletedCount sau thao tác trả 0.

Với Standard MBean, metadata của attributes và operations được suy ra từ interface. Notification metadata đến từ giao diện broadcaster của đối tượng. Có thể kiểm tra bằng `getMBeanInfo(name)` thay vì đoán điều gì đã được đưa ra JMX. [MBeanInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/MBeanInfo.html)

ObjectName `example.jobs:type=JobMonitor,name=main` là tên đăng ký của đối tượng trong MBeanServer. Nó không tự đổi khi thuộc tính DisplayName đổi thành billing-worker: tên đăng ký và thuộc tính hiển thị là hai khái niệm riêng.

Nếu tên đã được đăng ký bởi đối tượng khác, không tự hủy đối tượng đó để chạy lại ví dụ. Chọn danh tính đăng ký phù hợp vòng đời của thành phần hoặc xử lý lỗi trùng tên có chủ đích.

## 7. Listener, filter và handback

Một listener triển khai `NotificationListener`; phương thức xử lý nhận notification và một `handback` do bên đăng ký cung cấp.

Lời gọi trong ví dụ:

~~~java
server.addNotificationListener(name, listener, null, null);
~~~

Hai giá trị null nghĩa là không dùng filter và không cần ngữ cảnh handback. Listener vì thế nhận cả hai loại sự kiện của MBean.

Nếu chỉ quan tâm sự kiện đặt lại thống kê, có thể dùng filter. Đây là đoạn thay thế lời đăng ký trong ví dụ, không đăng ký thêm một lần bên cạnh nó:

~~~java
server.addNotificationListener(
    name,
    listener,
    event -> JobMonitor.RESET_TYPE.equals(event.getType()),
    null);
~~~

Filter quyết định một sự kiện có được gửi cho listener đã đăng ký hay không. Nó không làm MBean ngừng tạo sự kiện cho các listener khác. [NotificationFilter](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/NotificationFilter.html)

Phải hủy đăng ký khi bên nhận không còn cần dữ liệu. Chương trình dùng finally để gỡ listener trước khi hủy MBean; không đóng hoặc hủy MBeanServer nền tảng dùng chung của JVM.

## 8. Đồng thời và mô hình phát thông báo

`NotificationBroadcasterSupport` mặc định gọi listener cục bộ trên chính luồng gọi `sendNotification`. Vì vậy, listener xử lý chậm có thể kéo dài thời gian setter/operation trả về. Đây là lý do ví dụ gửi thông báo **sau khi ra khỏi synchronized**, để mã bên nhận không bị gọi trong khi đang giữ khóa bảo vệ trạng thái.

Bộ phát có thể dùng Executor nếu thiết kế cần mô hình khác. Khi đó phải quản lý hàng đợi, vòng đời executor và việc quá tải phù hợp; không chỉ đổi sang bất đồng bộ rồi coi mọi vấn đề đã biến mất.

Các giới hạn của ví dụ cần hiểu:

- Mỗi cập nhật trạng thái được đồng bộ, nhưng việc đổi trạng thái và xử lý xong mọi listener không phải một giao dịch chung.
- Một luồng khác có thể thay đổi trạng thái trước khi listener đọc lại getter. Sự kiện mang giá trị của lần thay đổi tương ứng, còn getter đọc trạng thái hiện tại.
- Khi nhiều luồng phát đồng thời, việc gửi ngoài khóa không tạo bảo đảm thứ tự nhận toàn cục. Sequence number giúp đối chiếu theo nguồn, không tự biến việc gửi thành hàng đợi bền vững.
- API broadcaster xử lý ngoại lệ của listener/filter theo hợp đồng riêng; không thiết kế nghiệp vụ dựa vào giả định mọi lỗi bên nhận sẽ quay lại rollback thay đổi trạng thái.
- Listener từ xa không có cùng bảo đảm đồng bộ như listener cục bộ: sendNotification trả về không chứng minh phía xa đã xử lý sự kiện.

Các hành vi phát mặc định và tùy chọn Executor được mô tả trong [NotificationBroadcasterSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html).

## 9. Notification không thay thế trạng thái hoặc nhật ký bền vững

Notification hữu ích để công cụ phản ứng nhanh với thay đổi, nhưng không nên là bản ghi duy nhất của một sự kiện nghiệp vụ bắt buộc phải lưu.

Kết nối từ xa có thể mất thông báo; JMX có loại sự kiện `JMXConnectionNotification.NOTIFS_LOST` để biểu thị khả năng đó. Sau mất kết nối hoặc nghi ngờ thiếu sự kiện, công cụ có thể cần đọc lại trạng thái bằng attribute thay vì giả định đã quan sát toàn bộ lịch sử. [JMXConnectionNotification](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/remote/JMXConnectionNotification.html)

Nếu cần kiểm toán, xử lý lại sau sự cố hoặc bảo đảm giao nhận theo yêu cầu nghiệp vụ, phải thiết kế nơi lưu và cơ chế tương ứng. Số thứ tự trong một đối tượng Java không tự cung cấp các tính chất đó.

Các operation thay đổi trạng thái cũng cần được đánh giá như API điều khiển thật: kiểm tra đầu vào, định nghĩa quyền truy cập ở lớp quản lý phù hợp và mô tả tác động rõ ràng. Đăng ký một MBean cục bộ không tự mở JMX remote; nếu hệ thống có connector thì bề mặt quản lý này có thể được truy cập thông qua connector đó.

## 10. Lỗi thường gặp và bài tập

| Cách làm | Điều cần sửa |
|---|---|
| Gọi `getAttribute(..., "displayName")` theo tên field | Dùng đúng tên attribute DisplayName từ metadata |
| Đưa getter vào `invoke` như một operation | Dùng getAttribute cho attribute |
| Tưởng mọi phương thức public đều là operation | Kiểm tra interface quản lý và MBeanInfo |
| Đổi attribute và chờ JMX tự phát thông báo | Tự tạo/phát notification trong phần triển khai |
| Chỉ khai báo MBeanNotificationInfo | Metadata mô tả khả năng, chưa thực hiện việc gửi |
| Gửi thông báo trong vùng khóa rồi gọi listener chậm | Tách cập nhật trạng thái và phát sự kiện phù hợp mô hình đồng thời |
| Quên gỡ listener khi thành phần dừng | Quản lý đăng ký theo vòng đời |
| Coi notification là lịch sử giao dịch đầy đủ | Có nguồn trạng thái/lưu trữ riêng theo yêu cầu |

Bài tập kiểm chứng:

1. Dùng MBeanInfo để xác nhận DisplayName đọc/ghi được, còn CompletedCount chỉ đọc.
2. Thay lần đăng ký listener bằng filter ở mục 7; đối chiếu những dòng thông báo còn xuất hiện.
3. Gán lại DisplayName bằng đúng giá trị hiện tại và kiểm tra không có sự kiện đổi tên mới.
4. Thêm một operation có tham số, quy định rõ tác dụng rồi gọi bằng invoke với chữ ký kiểu chính xác.
5. Mô tả cách ứng dụng thật cung cấp giá trị cho CompletedCount thay vì cho công cụ quản lý tùy ý ghi số đếm.

Một giao diện MBean tốt giúp người vận hành phân biệt được **đang đọc gì, đang thay đổi gì và vừa xảy ra sự kiện gì**, với hợp đồng nhỏ, rõ ràng và có thể kiểm chứng.
