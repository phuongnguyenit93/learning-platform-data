# Thứ tự, mất notification và giới hạn bảo đảm chuyển giao trong JMX

## 1. Mục tiêu

Java Management Extensions (JMX) cho phép MBean phát thông báo (*notification*) về thay đổi trạng thái, cảnh báo và sự kiện quản trị. Spring Framework có thể tích hợp cơ chế này qua JMX exporter, \`NotificationPublisher\` và listener.

Tuy nhiên, **nhận notification không đồng nghĩa với nhận một luồng sự kiện có bảo đảm giao nhận như message broker**. Một notification có thể được xử lý chậm, bỏ sót khi listener chưa đăng ký, mất khi kết nối JMX remote bị gián đoạn hoặc không còn quan sát được khi tiến trình JVM kết thúc. Sequence number giúp theo dõi nguồn phát nhưng không tạo ra cơ chế replay.

Sau bài học, bạn có thể:

- Phân biệt thứ tự phát, thứ tự dispatch, thứ tự callback và thứ tự quan sát thực tế.
- Hiểu phạm vi và giới hạn của \`Notification.sequenceNumber\`.
- Nhận diện các kịch bản notification bị mất hoặc bỏ lỡ.
- Giải thích vì sao JMX không mặc định bảo đảm *exactly-once*, *at-least-once*, lưu bền vững hay phát lại thông báo.
- Thiết kế consumer chịu lỗi bằng cách kiểm tra trạng thái hiện tại, phát hiện khoảng trống, kết nối lại và đồng bộ.
- Chọn đúng công cụ khi thông báo cần độ tin cậy cao và audit lâu dài.

## 2. Notification là gì?

Trong JMX, đối tượng phát notification thường triển khai \`NotificationBroadcaster\` hoặc \`NotificationEmitter\`. \`Notification\` có các thông tin như:

- \`type\`: chuỗi phân loại sự kiện.
- \`source\`: nguồn phát.
- \`sequenceNumber\`: số thứ tự do phía phát đặt.
- \`timeStamp\`: thời điểm gán cho notification.
- \`message\`: mô tả.
- \`userData\`: dữ liệu bổ sung tùy chọn.

Một \`NotificationListener\` nhận callback:

\`\`\`java
void handleNotification(Notification notification, Object handback);
\`\`\`

Ví dụ về các sự kiện:

\`\`\`text
com.example.jobs.started
com.example.jobs.progress
com.example.jobs.failed
com.example.jobs.completed
\`\`\`

Notification phù hợp để **báo cho công cụ quản trị rằng có một thay đổi đáng chú ý**. Người nghe thường có thể đọc lại attribute của MBean để xác định trạng thái hiện tại.

Notification không tự động là một transaction log. JMX không mặc nhiên lưu sự kiện vào đĩa, gán consumer offset, xác nhận đã xử lý thành công, retry bền vững hoặc cung cấp API phát lại lịch sử.

## 3. Bốn khái niệm về thứ tự cần phân biệt

Giả sử một MBean lần lượt phát ba thông báo:

\`\`\`text
Tại nguồn phát:
N1 (seq=1) -> N2 (seq=2) -> N3 (seq=3)
\`\`\`

Cần phân biệt các mốc:

| Khái niệm | Ý nghĩa | Điều không thể tự suy ra |
|---|---|---|
| **Thứ tự tạo** | Thread ứng dụng tạo các đối tượng notification theo trình tự nào | Chưa chứng minh chúng được gửi theo thứ tự đó |
| **Thứ tự phát** | MBean gọi \`sendNotification()\` theo trình tự nào | Chưa chứng minh listener ở xa nhìn thấy đủ và liên tục |
| **Thứ tự chuyển giao/callback** | Hệ thống JMX và listener nhận hoặc xử lý các notification theo trình tự nào | Không bảo đảm logic bất đồng bộ hoàn tất cùng thứ tự |
| **Thứ tự nghiệp vụ** | Trạng thái hoặc transaction nào thực sự xảy ra trước | Không thể lấy timestamp hoặc sequence tùy ý làm toàn bộ lịch sử nghiệp vụ |

Đặc biệt, nếu nhiều thread cùng phát notification, cần xác định rõ **điểm tuần tự hóa tại nguồn**. Tăng counter, tạo notification và gọi \`sendNotification()\` ở các thread khác nhau không nhất thiết là một thao tác nguyên tử.

### Ví dụ lệch thứ tự do cạnh tranh thread

\`\`\`text
Thread A: lấy sequence = 10 ----[bị dừng]---- send(N10)
Thread B: lấy sequence = 11 ---- send(N11)
Listener: N11, sau đó N10
\`\`\`

Ngay cả khi sequence tăng đơn điệu khi cấp phát, thứ tự gọi \`sendNotification()\` vẫn có thể khác nếu thiếu đồng bộ hóa bao quanh thao tác phát.

Nếu thứ tự mang ý nghĩa bắt buộc, hãy phát qua một hàng đợi hoặc một bộ điều phối tuần tự do ứng dụng kiểm soát. Nếu consumer xử lý bất đồng bộ bằng nhiều worker, cũng cần cơ chế bảo toàn thứ tự ở chính consumer.

## 4. Sequence number: hữu ích nhưng không phải cam kết giao nhận

\`Notification\` có trường \`sequenceNumber\` kiểu \`long\`; trong ví dụ Java phổ biến, nguồn phát chủ động đặt giá trị này. JMX API không biến sequence number thành một bộ đếm toàn cục, bền vững, tự quản lý cho mọi notification.

Ví dụ một nguồn phát:

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class JobMonitor extends NotificationBroadcasterSupport {
    private final AtomicLong nextSequence = new AtomicLong();

    public void jobStarted(String jobId) {
        long sequence = nextSequence.incrementAndGet();

        Notification notification = new Notification(
            "com.example.jobs.started",
            this,
            sequence,
            System.currentTimeMillis(),
            "Job started: " + jobId
        );

        notification.setUserData(jobId);
        sendNotification(notification);
    }
}
\`\`\`

Ở đây \`AtomicLong\` giúp tránh hai thread cấp cùng một sequence trong cùng instance. Nó **không tự bảo đảm** rằng hai lời gọi \`sendNotification()\` hoàn tất theo cùng thứ tự khi có concurrency.

### Sequence number có thể hỗ trợ điều gì?

- Log kèm sequence để xác định notification đến theo thứ tự nào.
- Phát hiện **dấu hiệu** bị bỏ qua một hoặc nhiều sequence nếu hợp đồng nguồn phát quy định mỗi sự kiện có một số liên tục.
- Nhận diện thứ tự đảo khi nguồn phát cam kết số thứ tự phản ánh thứ tự sự kiện.
- Đối chiếu giữa log nguồn phát và log listener trong chẩn đoán sự cố.

### Sequence number không tự chứng minh điều gì?

- Không chứng minh đã giao đúng một lần.
- Không chứng minh mọi listener đều nhận được.
- Không chứng minh notification đã được xử lý thành công.
- Không chứng minh một chuỗi số không có lỗ hổng tương ứng với toàn bộ sự kiện nghiệp vụ.
- Không chứng minh sequence vẫn tiếp tục sau khi JVM hoặc MBean được khởi động lại.
- Không tự cung cấp API lấy lại notification bị mất.

**Đáng chú ý:** Nguồn phát có thể chủ ý dùng sequence cách quãng, reset counter hoặc phát nhiều loại notification theo những quy tắc riêng. Chỉ xem \`seq=10\` rồi \`seq=12\` là dấu hiệu mất sự kiện khi hợp đồng nguồn phát định nghĩa rõ một dãy liên tục, không reset trong cùng epoch.

## 5. Những nơi notification có thể bị mất hoặc không được quan sát

### 5.1. Listener chưa được đăng ký

Nếu notification được phát trước \`addNotificationListener()\`, listener đó thông thường sẽ không nhận lại lịch sử. Đăng ký listener không khiến JMX tự replay các thông báo trước thời điểm đăng ký.

\`\`\`text
T1: MBean phát N1
T2: Listener được đăng ký
T3: MBean phát N2
Kết quả quan sát: listener có thể thấy N2 nhưng không thấy N1
\`\`\`

Vì vậy, không dùng notification duy nhất để khởi tạo toàn bộ state của công cụ quản trị. Hãy **đọc trạng thái ban đầu** và dùng notification làm tín hiệu cập nhật.

### 5.2. Listener bị gỡ hoặc MBean bị unregister

Khi listener bị xóa, đối tượng MBean bị unregister hoặc thay thế, các notification sau đó có thể không còn được gửi đến subscription cũ. Sau khi đăng ký lại, cần kiểm tra lại trạng thái.

### 5.3. Kết nối remote bị gián đoạn

JMX remote thường được dùng qua \`JMXConnector\` và \`MBeanServerConnection\`. Network partition, timeout, reconnect, kết nối đóng hoặc server JVM restart có thể làm client không nhận được một số thông báo.

Việc kết nối lại không tự chứng minh notification phát trong lúc offline đã được phát lại. Tùy connector, có thể tồn tại buffer hoặc cơ chế thu hồi nội bộ; không nên dựa vào chúng như bảo đảm lưu bền vững và replay nghiệp vụ.

### 5.4. Buffer hoặc hệ thống nhận không theo kịp

Một số triển khai remote có cơ chế buffer, hàng đợi hoặc polling để chuyển notification tới client. Nếu nguồn phát quá nhanh, client chậm hoặc bộ nhớ/buffer có giới hạn, một số notification có thể bị bỏ qua, tùy cách cài đặt.

Không thể khẳng định mọi JMX connector đều có hành vi overflow giống nhau. Cần xem tài liệu triển khai cụ thể, cấu hình và metric/log phù hợp.

### 5.5. JVM hoặc tiến trình bị dừng

Khi JVM kết thúc hoặc gặp sự cố, các notification chỉ đang tồn tại trong bộ nhớ có thể biến mất. \`NotificationBroadcasterSupport\` không phải persistent event store.

### 5.6. Listener ném exception hoặc xử lý bất đồng bộ lỗi

Việc một callback được gọi không đồng nghĩa logic xử lý đã hoàn tất. Listener có thể:

- Ném exception.
- Bị chặn bởi I/O hoặc deadlock.
- Đưa sự kiện sang executor nội bộ rồi mất sự kiện khi executor đóng.
- Xử lý lặp lại do logic reconnect của chính ứng dụng.
- Chạy chậm khiến những sự kiện mới đến bị tồn đọng.

Phân biệt **đã chuyển đến callback** với **đã xử lý và ghi nhận thành công**. Không nên gọi chung hai kết quả này là “delivered”.

## 6. Phạm vi bảo đảm của API JMX

JMX cung cấp các giao diện phát và nghe notification nhưng **không định nghĩa cho mọi cấu hình một hợp đồng end-to-end giống durable message queue**.

| Bảo đảm | Có mặc định với notification JMX không? | Ghi chú |
|---|---|---|
| Có thể đăng ký listener và nhận notification | Có, khi emitter/listener và kết nối hoạt động | Là chức năng cơ bản của API |
| Thứ tự callback luôn trùng thứ tự nghiệp vụ | Không thể mặc định | Phụ thuộc concurrency, executor và cách nguồn phát |
| Mỗi notification được xử lý đúng một lần trên toàn hệ thống | Không | Không có transaction/ack nghiệp vụ mặc định |
| Tự động phát lại notification trước khi listener đăng ký | Không | Không phải event log |
| Lưu bền qua JVM restart | Không | Cần storage riêng |
| Bảo đảm remote client nhận đủ khi disconnect/reconnect | Không thể giả định | Phụ thuộc triển khai và cơ chế phục hồi ngoài JMX |
| Cho phép dùng sequence để phát hiện bất thường | Có thể | Cần hợp đồng sequence rõ ràng |
| Có thể đọc lại state hiện tại của MBean | Có nếu MBean expose attribute/operation tương ứng | Đây là chiến lược phục hồi thường dùng |

Không nên đưa ra khẳng định tuyệt đối như “JMX luôn đảo thứ tự” hoặc “JMX luôn làm mất sự kiện”. Trong môi trường ổn định, nhiều notification có thể được chuyển giao theo đúng trình tự mong muốn. Điểm quan trọng là **API tự thân không cung cấp những cam kết giao nhận bền vững mà ứng dụng có thể dựa vào trong mọi điều kiện lỗi**.

### Local listener và remote listener khác nhau

Với local listener trong cùng JVM, đường đi thường ngắn hơn và tránh lỗi mạng. Mặc dù vậy, callback vẫn chịu ảnh hưởng của thiết kế emitter, executor, concurrency và vòng đời listener.

Với remote listener, thêm các yếu tố: kết nối, serialization, client fetch, buffer, reconnect và khác biệt triển khai. Vì vậy, một thử nghiệm local chạy đúng thứ tự không chứng minh hành vi trong production qua remote JMX.

## 7. \`NotificationBroadcasterSupport\` và lựa chọn executor

Một MBean có thể dùng \`NotificationBroadcasterSupport\`:

\`\`\`java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class StatusMonitor extends NotificationBroadcasterSupport {
    public void publish(Notification notification) {
        sendNotification(notification);
    }
}
\`\`\`

Các constructor của \`NotificationBroadcasterSupport\` cho phép cung cấp \`Executor\` để điều phối listener callback. Executor mặc định có thể gọi listener trong luồng phát; khi dùng executor bất đồng bộ, thời gian và thứ tự xử lý còn phụ thuộc chính sách scheduling của executor.

Ví dụ:

\`\`\`java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.management.NotificationBroadcasterSupport;

ExecutorService callbacks = Executors.newSingleThreadExecutor();

NotificationBroadcasterSupport broadcaster =
    new NotificationBroadcasterSupport(callbacks);
\`\`\`

Một executor đơn luồng có thể giúp chạy callback theo thứ tự các task được đưa vào queue của executor đó. Nhưng để giữ thứ tự nghiệp vụ end-to-end, còn phải xác định thứ tự phát, tránh nhiều producer đua nhau và xử lý lifecycle/shutdown đúng cách. Executor đơn luồng không tạo persistence hoặc replay.

Nếu tự cấp executor, ứng dụng chịu trách nhiệm quản lý tài nguyên và đóng nó khi thích hợp. Không cấu hình \`newCachedThreadPool()\` hoặc queue không giới hạn một cách tùy tiện cho luồng notification có tốc độ cao mà không kiểm soát tải.

## 8. Thiết kế listener chịu được mất notification

Một listener bền vững về mặt vận hành nên coi notification là **tín hiệu phải đối chiếu lại với nguồn trạng thái**. Mẫu phổ biến:

\`\`\`text
Khởi tạo:
  1. Kết nối tới đúng MBeanServer/MBean.
  2. Đăng ký listener.
  3. Đọc snapshot trạng thái hiện tại.
  4. Ghi nhận phiên/epoch của nguồn nếu có.

Khi nhận notification:
  5. Kiểm tra type/source/sequence theo hợp đồng.
  6. Nếu có gap/đảo thứ tự/reset -> đánh dấu cần đồng bộ.
  7. Đọc lại snapshot khi cần.
  8. Áp dụng cập nhật idempotent vào trạng thái hiển thị.

Khi mất kết nối:
  9. Đánh dấu thông tin đang stale.
 10. Tái kết nối và đăng ký listener.
 11. Đọc snapshot mới; không suy diễn rằng đã nhận đủ lịch sử.
\`\`\`

Bước đăng ký listener và đọc snapshot vẫn có thể có race: một event xảy ra trước, trong hoặc sau snapshot. Để bảo đảm trạng thái hoàn toàn nhất quán, API nguồn cần cung cấp cơ chế snapshot/version có thể đối chiếu. Ví dụ \`stateVersion\` được tăng mỗi lần đổi trạng thái và trả về cùng snapshot giúp consumer bỏ qua dữ liệu cũ hoặc yêu cầu đọc lại khi có xung đột.

Nếu không có version, cách an toàn là coi notification như trigger **refresh toàn bộ trạng thái**, chấp nhận eventual consistency cho mục đích quan sát.

### Ví dụ listener tối giản

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationListener;

public final class MonitorListener implements NotificationListener {
    private final AtomicLong lastSeen = new AtomicLong(-1);

    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {

        long current = notification.getSequenceNumber();
        long previous = lastSeen.getAndSet(current);

        if (previous >= 0 && current != previous + 1) {
            System.out.printf(
                "Can dong bo lai: prev=%d, current=%d%n",
                previous, current
            );
        }

        System.out.println(notification.getType());
        // Với UI vận hành: yêu cầu đọc lại state hiện tại ở đây
        // hoặc enqueue refresh vào một executor được quản lý.
    }
}
\`\`\`

Ví dụ này chỉ nhằm minh họa cách phát hiện **dấu hiệu bất thường sequence**. Nó giả định callback được xử lý tuần tự, một nguồn phát có sequence liên tục, không reset và không có loại notification bị filter. Nếu callback đồng thời hoặc có nhiều nguồn, \`getAndSet()\` không bảo toàn thứ tự quan sát và có thể tạo cảnh báo sai. Trong hệ thống thật, dùng xử lý tuần tự cho từng nguồn và theo dõi \`source + epoch + sequence\`; nếu chỉ vài loại event đi qua filter, cần điều chỉnh chính sách phát hiện gap.

Khi có gap, **không thể tự khôi phục nội dung thông báo mất chỉ bằng sequence number**. Hãy yêu cầu snapshot hoặc dùng event store riêng nếu phải biết từng sự kiện.

## 9. Thiết kế hợp đồng nguồn phát rõ ràng

Khi tự viết MBean phát notification, nên công bố:

1. **Ý nghĩa từng type**: ví dụ \`job.failed\` là báo lỗi thoáng qua hay chuyển trạng thái bền vững.
2. **Phạm vi sequence**: mỗi MBean hay cả ứng dụng; liên tục hay cách quãng; có reset sau restart hay không.
3. **Điểm tuần tự hóa**: event được đánh số tại thời điểm nào; đa thread có được phép phát song song không.
4. **Epoch hoặc instance ID**: phân biệt vòng đời MBean/JVM, tránh hiểu nhầm sequence reset thành replay.
5. **Snapshot API**: attribute hoặc operation cho phép consumer đọc state hiện tại.
6. **Lỗi và kết nối**: consumer cần làm gì khi mất kết nối hoặc không nhận đủ.
7. **Ý nghĩa giao nhận**: notification chỉ là tín hiệu quan sát hay có yêu cầu audit/đảm bảo không mất.

Một contract rõ ràng giúp client không phải đoán từ việc “ở môi trường thử nghiệm notification chạy đúng”.

### Ví dụ snapshot kết hợp version

\`\`\`java
public record JobSnapshot(
    String state,
    long version,
    String instanceId
) {}
\`\`\`

Một MBean có thể expose operation/attributes tương đương cho state, version và instance ID. Khi \`job.completed\` đến, client đọc \`JobSnapshot\`; nếu \`version\` đã tăng, UI hiển thị trạng thái mới. Nếu nhận notification muộn mang version cũ, client không ghi đè snapshot mới hơn.

Để version thực sự hữu ích, **nguồn phát phải cập nhật state và version nhất quán**. Chỉ thêm một trường \`long\` không giải quyết race nếu state và version không được công bố cùng một logic đồng bộ.

## 10. Spring Framework: phát notification từ MBean

Spring JMX có thể expose một Spring bean dưới dạng MBean và hỗ trợ \`NotificationPublisherAware\`:

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Monitor,name=ImportJob"
)
public class ImportJobMonitor implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    public void onJobFailed(String reason) {
        Notification notification = new Notification(
            "com.example.jobs.failed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Import failed"
        );
        notification.setUserData(reason);
        publisher.sendNotification(notification);
    }
}
\`\`\`

Đây là ví dụ minh họa lớp phát notification. Để chạy trong ứng dụng thực tế, cần thiết lập JMX export phù hợp, cấu hình metadata notification nếu cần và bảo đảm \`NotificationPublisher\` đã được Spring cấp trước khi gọi \`onJobFailed\`. Nếu nghiệp vụ gọi từ nhiều thread và thứ tự quan trọng, còn cần điểm tuần tự hóa thay vì chỉ dùng \`AtomicLong\`.

Spring cung cấp cầu nối xuất bản JMX và đăng ký listener; Spring **không biến notification thành sự kiện được lưu bền, có ack hoặc replay**. Những tính chất ấy phải do thiết kế ứng dụng hoặc hạ tầng messaging đảm nhận.

### Không nhầm với Spring ApplicationEvent

\`ApplicationEventPublisher\` thuộc mô hình sự kiện trong Spring application context, còn JMX \`NotificationPublisher\` hướng tới hệ thống quản trị JMX. Chúng có lifecycle và cơ chế dispatch riêng. Sự tồn tại của Spring event hoặc JMX notification không tự tạo bảo đảm giao nhận bền vững; nếu cần, phải thiết kế rõ cơ chế persistence và delivery.

## 11. JMX remote: quan sát gián đoạn và phục hồi

Ví dụ remote client có thể sử dụng \`JMXConnector\`:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.NotificationListener;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
            connector.getMBeanServerConnection();

    ObjectName name = new ObjectName(
        "com.example.jobs:type=Monitor,name=ImportJob"
    );

    NotificationListener listener = (n, handback) -> {
        System.out.println(
            n.getSequenceNumber() + " " + n.getType()
        );
    };

    connection.addNotificationListener(
        name, listener, null, null
    );

    // Thực tế: duy trì phiên nghe, đọc snapshot và xử lý reconnect.
    // Tránh kết thúc ngay sau khi đăng ký listener.
}
\`\`\`

Đây là đoạn minh họa phương thức đăng ký listener, chưa phải chương trình client chạy liên tục. Để vận hành cần:
- Có connector server được cấu hình và bảo vệ phù hợp.
- Theo dõi lỗi kết nối và vòng đời connection.
- Khi reconnect, đăng ký lại listener với connection mới.
- Đồng bộ snapshot và nhận biết dữ liệu stale.
- Tránh tạo nhiều listener trùng do reconnect mà không cleanup.
- Đặt timeout và giới hạn retry/backoff hợp lý.

Tùy JMX connector và triển khai, có thể xuất hiện thông báo quản lý connection như \`JMXConnectionNotification\`. Theo dõi chúng giúp client phát hiện đứt kết nối, nhưng bản thân connection notification cũng không chứng minh đã nhận đầy đủ mọi MBean notification.

## 12. Khi nào cần message broker hoặc event store?

JMX notification hữu ích khi:
- Công cụ quản trị cần biết “đã có thay đổi” và đọc lại trạng thái.
- Cần cảnh báo vận hành tạm thời, dung lượng vừa phải.
- Listener đang online và mất vài sự kiện riêng lẻ có thể bù bằng snapshot.
- Mục tiêu chính là quan sát nội bộ Java/JMX.

Nếu yêu cầu là:
- **Không được bỏ sót từng sự kiện** khi JVM restart hoặc client offline.
- **Audit** đầy đủ, truy vấn lịch sử nhiều ngày/tháng.
- **Retry** khi consumer xử lý lỗi.
- Consumer group, offset, backpressure, reprocessing.
- Giao dịch nghiệp vụ cần độ bền dữ liệu và xác nhận xử lý.

...thì cần giải pháp khác, chẳng hạn event log/message broker có lưu bền (Kafka, RabbitMQ với cấu hình phù hợp), database outbox, hoặc bảng audit có cơ chế transaction và consumer xử lý riêng.

Không nên diễn giải rằng “dùng broker là tự động exactly-once”. Mỗi broker và cấu hình có phạm vi bảo đảm cụ thể; end-to-end exactly-once thường cần thêm idempotency, transaction hoặc deduplication phía consumer.

### Kiến trúc kết hợp

\`\`\`text
             Nghiệp vụ thay đổi state
                       |
               Database transaction
                       |
              Outbox / event log
                       |
           Reliable event processing
                       |
            +----------+----------+
            |                     |
      Business consumers     Metrics / audit
            |
   (tùy chọn) cập nhật state
            |
        JMX MBean
            |
   JMX notification: "state changed"
            |
        Admin console
            |
      Đọc snapshot hiện tại
\`\`\`

Trong thiết kế này, luồng sự kiện nghiệp vụ có cơ chế lưu bền riêng; JMX notification đóng vai trò tín hiệu quan sát có thể bị bỏ lỡ và được phục hồi bằng cách đọc state.

## 13. Chẩn đoán sự cố khi thiếu hoặc đảo thứ tự notification

Khi client báo “mất một notification”, cần tách các giả thuyết:

| Triệu chứng | Điều cần kiểm tra |
|---|---|
| Thấy seq 100 rồi 102 | Nguồn có phát 101 không? Counter có liên tục? Filter có loại bỏ event? |
| Thấy seq 102 trước 101 | Nhiều producer? Executor dispatch bất đồng bộ? Consumer xử lý song song? |
| Không nhận gì sau reconnect | Listener đã đăng ký lại trên connection mới chưa? ObjectName và MBean có đúng không? |
| Sau restart seq quay về 1 | Source có reset counter? Có instance ID/epoch không? |
| Callback chạy nhưng UI không cập nhật | Logic downstream có lỗi? Có queue bị bỏ hoặc thread bị block? |
| Chỉ remote client bị thiếu | Mạng, connector, buffer, polling, timeout, churn kết nối? |
| Mất notification trước lúc client bật | Client có kỳ vọng sai về replay? Có snapshot để khởi tạo không? |

Thực hành logging nên ghi:
- Timestamp của nguồn và thời điểm client nhận (không giả định đồng hồ hai máy đồng bộ tuyệt đối).
- ObjectName/nguồn, type, sequence, instance ID/epoch.
- Lifecycle listener: register/unregister/reconnect.
- Số lượng phát, số lượng callback, lỗi xử lý, thời điểm đọc snapshot.
- Số lượng queue/buffer và độ trễ nếu implementation có cung cấp.

Không log dữ liệu bí mật trong \`userData\`. Đối với hệ thống lớn, dùng metric để đo số notification được phát, nhận, lỗi và lần resync; không dựa hoàn toàn vào chính notification để phát hiện việc notification không đến.

## 14. Ví dụ tình huống đầy đủ

Giả sử MBean quản trị import dữ liệu có trạng thái:

\`\`\`text
IDLE -> RUNNING -> COMPLETED
                 -> FAILED
\`\`\`

Nguồn phát:

\`\`\`text
N41: RUNNING
N42: COMPLETED
\`\`\`

Client kết nối sau N41 và chỉ thấy N42. Nếu UI khởi tạo bằng cách đợi notification, nó có thể không bao giờ thấy \`RUNNING\`. Nhưng nếu UI đọc \`CurrentStatus\` sau khi đăng ký listener, nó sẽ thấy trạng thái phù hợp tại thời điểm snapshot.

Một tình huống khác:

\`\`\`text
Client thấy: N41, [mất mạng], N44
\`\`\`

Gap \`41 -> 44\` có thể cảnh báo thiếu N42/N43 **nếu** sequence liên tục và cùng epoch. Client không được tự suy luận nội dung hai notification bị mất. Nó phải đọc lại \`CurrentStatus\`, \`StateVersion\` hoặc truy vấn event store nếu cần lịch sử đầy đủ.

Nếu hệ thống bắt buộc xử lý mọi lần chuyển trạng thái, snapshot chỉ cung cấp trạng thái mới nhất và có thể không phản ánh các trạng thái trung gian; khi đó cần event store có lưu lịch sử.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một listener nhận sequence 10 rồi 12. Có thể khẳng định mất notification 11 không?  
**Trả lời:** Chỉ có thể xem là dấu hiệu nếu source contract quy định số liên tục, cùng epoch và không có filter. Không thể kết luận nếu counter có bước nhảy hợp lệ.

**Câu 2.** \`AtomicLong.incrementAndGet()\` có bảo đảm callback theo thứ tự số tăng không?  
**Trả lời:** Không. AtomicLong bảo đảm cấp số nguyên tử, còn thread có thể gọi \`sendNotification()\` không cùng thứ tự và executor/consumer có thể thay đổi thứ tự xử lý.

**Câu 3.** Client mới đăng ký listener có nhận lại notification cũ không?  
**Trả lời:** Không thể trông chờ JMX tự replay notification đã phát trước lúc đăng ký. Cần snapshot hoặc event store tùy yêu cầu.

**Câu 4.** Khi remote JMX reconnect, việc đăng ký lại listener có đủ để phục hồi lịch sử không?  
**Trả lời:** Không. Phải đồng bộ trạng thái, nhận diện epoch và nếu cần mọi sự kiện, truy vấn nguồn lưu bền riêng.

**Câu 5.** Vì sao một notification đến callback chưa được coi là xử lý thành công?  
**Trả lời:** Listener có thể lỗi trong logic, queue async có thể mất sự kiện hoặc cập nhật downstream thất bại. JMX không cung cấp acknowledgement nghiệp vụ end-to-end mặc định.

**Câu 6.** Yêu cầu “mọi giao dịch phải được audit sau restart” có nên chỉ dùng JMX notification không?  
**Trả lời:** Không. Cần lưu bền giao dịch/sự kiện trong database, outbox hoặc broker/event store với hợp đồng giao nhận thích hợp.

## 16. Ghi nhớ

1. JMX notification là **cơ chế báo hiệu quản trị**, không phải log sự kiện có lưu bền mặc định.
2. \`sequenceNumber\` do nguồn phát gán; nó giúp chẩn đoán nhưng không tạo ordering hoặc delivery guarantee.
3. Nhiều thread, executor bất đồng bộ, remote connector và consumer downstream đều có thể ảnh hưởng đến thứ tự quan sát.
4. Listener đăng ký muộn, mất kết nối, buffer giới hạn, JVM restart và lỗi xử lý đều là nguồn gây thiếu dữ liệu.
5. Thiết kế consumer theo hướng **snapshot + notification + resynchronization**, với version/epoch khi cần.
6. Nếu phải giữ từng sự kiện, cần thiết kế persistence, replay, retry và idempotency ngoài phạm vi cơ bản của JMX.
7. Đánh giá bảo đảm theo **toàn bộ đường đi từ producer đến tác động nghiệp vụ**, không suy ra từ việc một callback đã được gọi.

### Tài liệu tham khảo

- Java SE 21 API — \`javax.management.Notification\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Java SE 21 API — \`NotificationBroadcasterSupport\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 API — \`NotificationListener\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE 21 API — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 API — \`JMXConnector\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html
- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
