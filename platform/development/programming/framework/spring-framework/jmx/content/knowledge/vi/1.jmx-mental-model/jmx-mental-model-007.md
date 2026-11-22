# Đưa khả năng quản trị ra ngoài ứng dụng mà không làm mã miền phụ thuộc JMX

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring có thể cần cho đội vận hành xem số lượng tác vụ đang chạy, trạng thái đồng bộ, ngưỡng giới hạn hoặc chủ động yêu cầu nạp lại cấu hình. Những nhu cầu này thuộc **mặt phẳng quản trị (management plane)**, khác với luồng nghiệp vụ thông thường. Nếu nhúng \`javax.management.*\` hoặc \`jakarta.management.*\` vào các lớp miền, quy tắc nghiệp vụ sẽ bị ràng buộc với giao thức quản trị cụ thể, khó kiểm thử và khó dùng lại qua HTTP, CLI hay scheduler.

Mục tiêu là **đưa ra bên ngoài đúng một bề mặt quản trị có kiểm soát**, còn lõi nghiệp vụ chỉ biết các khái niệm và thao tác của chính nó. Spring Framework hỗ trợ xuất một bean qua JMX bằng \`MBeanExporter\` và các annotation như \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`. Đó là công cụ của lớp adapter, không phải hợp đồng bắt buộc của miền.

## 2. Mô hình tư duy: hai cổng, một lõi

\`\`\`text
JConsole / VisualVM / JMX client
             |
         JMX MBean
             |
 Spring management adapter
 (@ManagedResource, @ManagedOperation)
             |
       Application port
             |
       Application service
             |
        Domain model
\`\`\`

- **Domain model** giữ bất biến nghiệp vụ, quyết định trạng thái hợp lệ và hoàn toàn không biết JMX.
- **Application service/port** cung cấp truy vấn trạng thái và lệnh quản trị theo ngôn ngữ ứng dụng, chẳng hạn \`getSnapshot()\` hoặc \`requestRefresh()\`.
- **Management adapter** chuyển port thành thuộc tính và operation JMX, đặt tên ObjectName, mô tả, xác thực/giới hạn quyền ở ranh giới vận hành.
- **JMX agent/connector** lo giao thức và khả năng truy cập từ công cụ vận hành. Nó có vòng đời và chính sách bảo mật riêng.

Bề mặt JMX nên ổn định, nhỏ và thiên về quan sát. Một operation quản trị phải có ý nghĩa rõ ràng, điều kiện cho phép, dấu vết kiểm toán và khả năng xử lý lỗi.

## 3. Thiết kế port độc lập giao thức

Ví dụ ứng dụng điều phối một công việc đồng bộ dữ liệu. Phần ứng dụng định nghĩa hợp đồng không mang kiểu JMX:

\`\`\`java
public record SyncSnapshot(
    String state,
    long completedCount,
    java.time.Instant lastSuccessAt
) {}

public interface SyncManagement {
    SyncSnapshot snapshot();
    void requestRefresh();
}
\`\`\`

\`SyncSnapshot\` là giá trị đọc duy nhất; không trả trực tiếp entity mutable, repository hay cấu trúc nội bộ có thể bị thay đổi ngoài ý muốn. \`requestRefresh()\` diễn đạt một ý định nghiệp vụ, không chứa khái niệm MBean hoặc \`ObjectName\`.

Service thực thi có thể được gọi từ scheduler, API HTTP hoặc adapter JMX:

\`\`\`java
@Service
public class SyncApplicationService implements SyncManagement {
    private final java.util.concurrent.atomic.AtomicLong completed =
        new java.util.concurrent.atomic.AtomicLong();
    private volatile java.time.Instant lastSuccessAt;
    private final java.util.concurrent.atomic.AtomicBoolean running =
        new java.util.concurrent.atomic.AtomicBoolean(false);

    @Override
    public SyncSnapshot snapshot() {
        return new SyncSnapshot(
            running.get() ? "RUNNING" : "IDLE",
            completed.get(),
            lastSuccessAt
        );
    }

    @Override
    public void requestRefresh() {
        if (!running.compareAndSet(false, true)) {
            throw new IllegalStateException("Refresh already running");
        }
        try {
            // Trong ứng dụng thực: chuyển lệnh sang hàng đợi hoặc executor được quản lý.
            // Ví dụ rút gọn này chỉ minh họa trạng thái và điều kiện đồng thời.
            completed.incrementAndGet();
            lastSuccessAt = java.time.Instant.now();
        } finally {
            running.set(false);
        }
    }
}
\`\`\`

Ví dụ trên chỉ mô phỏng tác vụ tức thời. Với công việc dài, hãy đưa lệnh vào executor/queue của ứng dụng và trả về nhanh; không để lời gọi JMX giữ thread điều khiển trong nhiều phút. Cần quy định rõ lệnh trùng, retry, timeout và idempotency theo nghiệp vụ.

## 4. Adapter Spring JMX: chỉ bọc hợp đồng

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.app:type=Sync,name=Primary",
    description = "Operational view of the sync service"
)
public class SyncJmxAdapter {
    private final SyncManagement management;

    public SyncJmxAdapter(SyncManagement management) {
        this.management = management;
    }

    @ManagedAttribute(description = "Current sync state")
    public String getState() {
        return management.snapshot().state();
    }

    @ManagedAttribute(description = "Number of completed sync cycles")
    public long getCompletedCount() {
        return management.snapshot().completedCount();
    }

    @ManagedAttribute(description = "Last successful completion in ISO-8601")
    public String getLastSuccessAt() {
        var last = management.snapshot().lastSuccessAt();
        return last == null ? "" : last.toString();
    }

    @ManagedOperation(description = "Request a synchronization refresh")
    public void refresh() {
        management.requestRefresh();
    }
}
\`\`\`

Adapter này chứa metadata JMX, nhưng interface và service không import thư viện JMX. Các getter trả kiểu đơn giản vì JMX clients làm việc thuận tiện với \`String\`, số và kiểu JMX chuẩn; tránh đưa record phức tạp hoặc proxy bean ra giao diện mà không có mapping rõ.

Để Spring đọc các annotation quản trị và đăng ký MBean:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
class JmxConfiguration {
    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MBeanExporter mbeanExporter(
            AnnotationJmxAttributeSource source) {
        var assembler = new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        var naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        var exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);
        return exporter;
    }
}
\`\`\`

Khi dùng Spring Boot, cấu hình xuất MBean có thể được tự động thiết lập theo phiên bản và thuộc tính ứng dụng (ví dụ \`spring.jmx.enabled=true\`). Không khai báo thêm exporter thủ công nếu Boot đã tạo một exporter phù hợp; chọn một nguồn cấu hình rõ ràng để tránh trùng đăng ký.

## 5. Quy tắc thiết kế bề mặt quản trị

| Nội dung | Nên làm | Cần tránh |
| --- | --- | --- |
| Thuộc tính | Trạng thái, bộ đếm, timestamp, ngưỡng đã lọc | Entity mutable, bí mật, dữ liệu khách hàng |
| Lệnh | \`refresh()\`, \`pause()\`, \`resume()\` với điều kiện rõ | \`executeSql(String)\`, \`invokeAny(String)\` |
| Tên MBean | Domain và cặp key ổn định, ví dụ \`com.example.app:type=Sync,name=Primary\` | Tên ngẫu nhiên mỗi lần khởi động |
| Trả lỗi | Thông điệp vận hành hữu ích, không lộ thông tin nhạy cảm | Stack trace/credential trong dữ liệu công khai |
| Đồng thời | Lệnh an toàn khi gọi lặp, trạng thái snapshot nhất quán | Gọi tác vụ dài trực tiếp trên thread JMX |
| Phụ thuộc | Adapter phụ thuộc \`SyncManagement\` | Domain service phụ thuộc \`MBeanServer\` |

**Chú ý tính nhất quán:** Nếu các trường snapshot phải phản ánh cùng một thời điểm, hãy xây dựng snapshot dưới cùng cơ chế đồng bộ hoặc lưu một immutable snapshot bằng \`AtomicReference\`. Nhiều \`volatile\` riêng lẻ không tự tạo giao dịch đọc nguyên tử.

**Chú ý ranh giới:** JMX là kênh điều khiển vận hành, không phải nơi phơi bày đầy đủ API nghiệp vụ. Các lệnh có tác động lớn như xóa dữ liệu, đổi khóa hoặc dừng hệ thống đòi hỏi kiểm soát riêng; không thêm chỉ vì annotation giúp xuất operation dễ dàng.

## 6. Cấu hình và vận hành

Có hai bước khác nhau:

1. **Đăng ký MBean trong JVM** qua Spring exporter. Khi đó MBean hiện diện trong platform \`MBeanServer\`; đây là khả năng nội bộ của JVM.
2. **Cho phép client bên ngoài kết nối** qua JMX connector hoặc giải pháp giám sát phù hợp. Cơ chế mạng, xác thực, TLS, firewall và quyền truy cập do môi trường triển khai quyết định.

Không đồng nhất \`spring.jmx.enabled\` với việc đã mở cổng JMX remote an toàn. Đặc biệt tránh cấu hình tắt authentication/SSL cho môi trường thật. Nếu chỉ cần metrics/health, một endpoint quan sát chuyên dụng (chẳng hạn Micrometer/Actuator trong Spring Boot) có thể phù hợp hơn việc mở MBean operation từ xa.

Đặt object name theo dạng domain:key=value, ví dụ:

\`\`\`text
com.example.app:type=Sync,name=Primary
\`\`\`

Nếu có nhiều instance trên cùng một \`MBeanServer\`, thêm thuộc tính phân biệt ổn định để tránh \`InstanceAlreadyExistsException\`. Đừng vô tình ghi đè MBean khác bằng chế độ registration thay thế.

## 7. Kiểm thử ranh giới

Mục tiêu kiểm thử không phải chứng minh JConsole hiển thị đẹp, mà là chứng minh adapter chuyển lời gọi chính xác và domain không phụ thuộc JMX.

\`\`\`java
class SyncJmxAdapterTest {
    @org.junit.jupiter.api.Test
    void exposesSnapshotAndDelegatesRefresh() {
        class Fake implements SyncManagement {
            boolean requested;
            public SyncSnapshot snapshot() {
                return new SyncSnapshot("IDLE", 7, null);
            }
            public void requestRefresh() { requested = true; }
        }

        var fake = new Fake();
        var adapter = new SyncJmxAdapter(fake);

        org.junit.jupiter.api.Assertions.assertEquals("IDLE", adapter.getState());
        org.junit.jupiter.api.Assertions.assertEquals(7, adapter.getCompletedCount());
        org.junit.jupiter.api.Assertions.assertEquals("", adapter.getLastSuccessAt());
        adapter.refresh();
        org.junit.jupiter.api.Assertions.assertTrue(fake.requested);
    }
}
\`\`\`

Kiểm thử tích hợp riêng có thể dựng Spring \`ApplicationContext\`, lấy \`MBeanServer\`, kiểm tra \`isRegistered(ObjectName)\`, đọc attribute và gọi operation qua giao diện JMX. Dọn context và registration sau mỗi lần kiểm thử để không để rò trạng thái giữa các ca kiểm thử.

Kiểm thử kiến trúc nên chặn dependency ngược từ các package \`domain\` và \`application\` sang \`org.springframework.jmx\`, \`javax.management\`/ \`jakarta.management\` hoặc \`SyncJmxAdapter\`. Có thể kiểm tra bằng ArchUnit hoặc quy tắc build tách module.

## 8. Các tình huống vận dụng

**Quan sát:** SRE hỏi “đang chạy hay chờ?”; adapter chỉ lấy snapshot và xuất thuộc tính \`State\`. Không phải sửa service cho nhu cầu JConsole.

**Điều khiển:** Người vận hành gọi \`refresh()\`; adapter ủy quyền cho port. Application service kiểm tra trạng thái đang chạy, phân quyền theo kiến trúc triển khai và quyết định có nhận lệnh hay từ chối. Không chứa logic nghiệp vụ trong method annotated.

**Thay giao thức:** Sau này thêm HTTP admin endpoint, CLI hoặc actuator endpoint thì các adapter mới gọi lại \`SyncManagement\`; không viết lại domain model.

**Tắt JMX:** Không đăng ký exporter hoặc vô hiệu cấu hình JMX; luồng nghiệp vụ vẫn chạy như cũ. Đây là phép thử quan trọng cho mức độ tách biệt.

## 9. Sai lầm thường gặp và cách sửa

- **Đánh dấu \`@ManagedResource\` ngay trên aggregate/domain service:** Di chuyển annotation sang adapter và sử dụng interface ứng dụng.
- **Xuất tất cả bean:** Chỉ chọn bean quản trị cần thiết, phân biệt rõ lệnh đọc và lệnh thay đổi trạng thái.
- **Trả DTO có cấu trúc phức tạp như một attribute:** Map ra các giá trị đơn giản hoặc định nghĩa Open MBean mapping có chủ đích.
- **Thực hiện công việc lâu trong \`@ManagedOperation\`:** Đưa vào hàng đợi, trả nhanh và cung cấp trạng thái theo dõi riêng.
- **Dùng JMX làm cơ chế phân quyền nghiệp vụ:** Áp dụng quyền tại kênh vận hành và kiểm tra điều kiện/ủy quyền ở tầng ứng dụng tương ứng.
- **Giả định MBean luôn sẵn có trên mạng:** Kiểm tra riêng cấu hình connector và chính sách bảo mật.

## 10. Ghi nhớ

Tư duy cốt lõi: **JMX là adapter quản trị đặt ở rìa ứng dụng**. Application port mô tả điều cần quan sát và điều được phép ra lệnh; domain thực hiện luật nghiệp vụ; Spring JMX chuyển hợp đồng ấy thành MBean cho người vận hành. Khi bỏ JMX, thay giao thức, hoặc đổi công cụ giám sát mà không phải sửa miền, ranh giới kiến trúc đã làm đúng vai trò của nó.
