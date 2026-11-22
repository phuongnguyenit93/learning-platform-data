# Tách interface quản trị khỏi interface nghiệp vụ trong Spring Framework JMX

## 1. Vấn đề: hai nhóm người dùng, hai loại hợp đồng

Một ứng dụng Spring có thể có \`OrderService\` xử lý đơn hàng, đồng thời cần cho đội vận hành xem số lượng đơn đang chờ, tạm dừng tác vụ nhập dữ liệu, đặt lại bộ đếm hoặc kích hoạt đồng bộ. Các yêu cầu ấy cùng liên quan đến một thành phần, nhưng có mục đích khác nhau:

- **Interface nghiệp vụ** mô tả các hành vi phục vụ use case: đặt hàng, hủy đơn hợp lệ, tính phí, xác nhận thanh toán.
- **Interface quản trị** mô tả những gì người vận hành cần xem hoặc điều khiển: trạng thái, số liệu tổng hợp, bật/tắt công việc nền, yêu cầu làm mới một tài nguyên.
- **Giao thức JMX** là một cách xuất interface quản trị ra công cụ như JConsole, VisualVM hoặc client JMX tùy chỉnh.

Nếu thêm \`getPendingCount()\`, \`resetCounters()\`, \`pauseSync()\` và annotation JMX trực tiếp vào \`OrderService\`, lớp nghiệp vụ dần chứa cả các thao tác vận hành. Hệ quả là hợp đồng nghiệp vụ phình ra, các client thường có thể nhìn thấy method không cần thiết, khó phân quyền và việc thay JMX bằng giao thức khác kéo theo sửa mã lõi.

Nguyên tắc chính: **nghiệp vụ quyết định quy tắc và trạng thái; interface quản trị chỉ cung cấp một góc nhìn và các lệnh vận hành được cho phép.** JMX adapter phụ thuộc vào các abstraction của ứng dụng; lõi ứng dụng không phụ thuộc JMX.

## 2. Mô hình kiến trúc đề xuất

\`\`\`text
         Business API / Controller / Scheduler
                        |
                 OrderOperations
                        |
                Application Service
                   /         \
              Domain        State/metrics
                   \         /
                   Management port
                        ^
                        |
              Spring JMX adapter
             (MBean/ManagedResource)
                        ^
                        |
               MBeanServer / JMX
                        ^
                        |
                 Operations client
\`\`\`

Đường phụ thuộc trong mã nguồn đi từ adapter bên ngoài vào interface ứng dụng. Một đối tượng triển khai có thể phục vụ cả business port lẫn management port, nhưng **không cần cho một caller thấy toàn bộ method của cả hai interface**. Với hệ thống lớn hơn, lớp quản trị đọc từ một \`ManagementFacade\` hoặc \`ReadModel\` chuyên biệt; các lệnh điều khiển được chuyển sang application command handler.

Phân biệt ba cấp interface:

1. **Business port**: ngôn ngữ miền và use case.
2. **Management port**: hợp đồng quản trị độc lập giao thức, dùng DTO/snapshot phù hợp.
3. **JMX MBean interface hoặc annotated adapter**: lớp xuất management port dưới kiểu và cú pháp JMX.

Tên \`*MBean\` là quy ước JMX cho Standard MBean, không bắt buộc phải xuất hiện ở domain hoặc business port.

## 3. Business interface chỉ chứa thao tác nghiệp vụ

Ví dụ ứng dụng xử lý đơn hàng:

\`\`\`java
package com.example.orders.application;

public interface OrderOperations {
    String placeOrder(PlaceOrderCommand command);
    void cancelOrder(String orderId);
}
\`\`\`

\`\`\`java
package com.example.orders.application;

public record PlaceOrderCommand(
    String customerId,
    String productId,
    int quantity
) {}
\`\`\`

Business interface không chứa \`getHeapUsed()\`, \`resetStatistics()\` hay \`pauseWorker()\`. Các use case không cần biết ứng dụng có bật JMX hay không.

Phần nghiệp vụ cũng tránh import \`javax.management.*\` và \`org.springframework.jmx.*\`. Ngay cả khi service dùng Spring để quản lý dependency injection, hợp đồng nghiệp vụ vẫn không cần gắn annotation quản trị lên method.

## 4. Management port độc lập JMX

Tạo một hợp đồng riêng ở application layer:

\`\`\`java
package com.example.orders.application;

import java.time.Instant;

public record OrderWorkerSnapshot(
    boolean paused,
    int queueDepth,
    long processedTotal,
    Instant lastProcessedAt
) {}
\`\`\`

\`\`\`java
package com.example.orders.application;

public interface OrderWorkerManagement {
    OrderWorkerSnapshot snapshot();
    void pause();
    void resume();
}
\`\`\`

Tên các method vẫn thể hiện ý định ứng dụng, không chứa từ \`MBean\`, \`ObjectName\` hoặc \`MBeanServer\`. \`snapshot()\` trả một DTO bất biến để adapter có thể dịch thành thuộc tính dễ quan sát. \`pause()\` và \`resume()\` biểu diễn lệnh có ràng buộc, không cho phép client tùy ý sửa trạng thái nội bộ.

Việc tách port giúp:

- Giữ hợp đồng nghiệp vụ nhỏ và ổn định.
- Áp dụng chính sách cho lệnh vận hành ở đúng tầng.
- Kiểm thử quản trị độc lập công cụ JMX.
- Sử dụng lại management port từ HTTP admin endpoint, CLI, internal console hoặc scheduler nếu có nhu cầu.
- Tắt JMX mà không phá vỡ luồng xử lý đơn hàng.

## 5. Một service triển khai hai interface

Một cách tổ chức đơn giản là service triển khai cả hai port nhưng chỉ expose mỗi port tới đúng caller:

\`\`\`java
package com.example.orders.application;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService
        implements OrderOperations, OrderWorkerManagement {

    private final AtomicBoolean paused = new AtomicBoolean(false);
    private final AtomicLong processedTotal = new AtomicLong();
    private volatile Instant lastProcessedAt;

    @Override
    public String placeOrder(PlaceOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        // Ví dụ rút gọn: logic kiểm tra, persist và phát sự kiện nằm ở đây.
        String newOrderId = java.util.UUID.randomUUID().toString();
        processedTotal.incrementAndGet();
        lastProcessedAt = Instant.now();
        return newOrderId;
    }

    @Override
    public void cancelOrder(String orderId) {
        // Thực thi quy tắc hủy đơn thật trong ứng dụng.
    }

    @Override
    public OrderWorkerSnapshot snapshot() {
        return new OrderWorkerSnapshot(
            paused.get(), 0, processedTotal.get(), lastProcessedAt
        );
    }

    @Override
    public void pause() {
        paused.set(true);
    }

    @Override
    public void resume() {
        paused.set(false);
    }
}
\`\`\`

Đây là ví dụ để minh họa cấu trúc interface, không phải worker queue hoàn chỉnh. Trong hệ thống thật, \`paused\` phải được luồng worker kiểm tra tại checkpoint hợp lệ, bộ đếm được cập nhật ở thời điểm chính xác, và \`queueDepth\` lấy từ queue hoặc hệ thống messaging thực. Đừng hiểu \`pause()\` là chặn tất cả business operation; ý nghĩa của pause phải được định nghĩa rõ.

Cách triển khai này phù hợp khi một service nhỏ thực sự sở hữu cả nghiệp vụ và trạng thái worker. Với hệ thống lớn, có thể dùng hai lớp \`OrderApplicationService\` và \`OrderWorkerManagementService\` cùng gọi một domain service hoặc service nội bộ, tránh tạo một class ôm quá nhiều trách nhiệm.

## 6. Standard MBean: interface quản trị là hợp đồng JMX

JMX Standard MBean sử dụng quy ước **interface tên \`<ImplementationClassName>MBean\`**. Interface ấy chỉ liệt kê những attribute và operation muốn xuất qua JMX, dù implementation có thêm nhiều method public khác.

\`\`\`java
package com.example.orders.jmx;

public interface OrderWorkerMonitorMBean {
    boolean isPaused();
    int getQueueDepth();
    long getProcessedTotal();
    String getLastProcessedAt();
    void pause();
    void resume();
}
\`\`\`

\`\`\`java
package com.example.orders.jmx;

import com.example.orders.application.OrderWorkerManagement;

public final class OrderWorkerMonitor
        implements OrderWorkerMonitorMBean {

    private final OrderWorkerManagement management;

    public OrderWorkerMonitor(OrderWorkerManagement management) {
        this.management = management;
    }

    @Override
    public boolean isPaused() {
        return management.snapshot().paused();
    }

    @Override
    public int getQueueDepth() {
        return management.snapshot().queueDepth();
    }

    @Override
    public long getProcessedTotal() {
        return management.snapshot().processedTotal();
    }

    @Override
    public String getLastProcessedAt() {
        var value = management.snapshot().lastProcessedAt();
        return value == null ? "" : value.toString();
    }

    @Override
    public void pause() {
        management.pause();
    }

    @Override
    public void resume() {
        management.resume();
    }
}
\`\`\`

Ở đây \`OrderWorkerMonitorMBean\` là **JMX-facing interface**, còn \`OrderWorkerManagement\` là **application port**. Hai interface có thể giống nhau ở một số method nhưng khác về kiểu trả về, tên gọi và mức độ hiển thị. Adapter đổi \`Instant\` thành \`String\` ISO-8601 vì client JMX có thể hiển thị nó đơn giản; các DTO phức tạp có thể yêu cầu Open MBean mapping.

Đăng ký với platform \`MBeanServer\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Worker,name=Primary"
);

OrderWorkerMonitor monitor = new OrderWorkerMonitor(management);
server.registerMBean(monitor, name);
\`\`\`

Biến \`management\` là instance \`OrderWorkerManagement\` do Spring cung cấp hoặc được inject. Khi dừng module, unregister đúng \`ObjectName\` nếu ứng dụng sở hữu đăng ký này. \`javax.management\` là package chuẩn Java SE; JMX không chuyển sang \`jakarta.management\` khi nâng cấp Spring.

## 7. Spring JMX annotation: adapter không cần interface *MBean

Spring Framework cũng hỗ trợ xuất các method bằng metadata annotation. Với cách này, interface JMX riêng không bắt buộc, nhưng vẫn nên giữ **management port tách biệt**.

\`\`\`java
package com.example.orders.jmx;

import com.example.orders.application.OrderWorkerManagement;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Worker,name=Primary",
    description = "Order worker operations"
)
public final class OrderWorkerJmxAdapter {
    private final OrderWorkerManagement management;

    public OrderWorkerJmxAdapter(OrderWorkerManagement management) {
        this.management = management;
    }

    @ManagedAttribute(description = "Whether processing is paused")
    public boolean isPaused() {
        return management.snapshot().paused();
    }

    @ManagedAttribute(description = "Pending work count")
    public int getQueueDepth() {
        return management.snapshot().queueDepth();
    }

    @ManagedAttribute(description = "Completed jobs")
    public long getProcessedTotal() {
        return management.snapshot().processedTotal();
    }

    @ManagedOperation(description = "Pause background processing")
    public void pause() {
        management.pause();
    }

    @ManagedOperation(description = "Resume background processing")
    public void resume() {
        management.resume();
    }
}
\`\`\`

Để annotation hoạt động, Spring phải dùng một \`MBeanExporter\` với metadata assembler/naming strategy phù hợp hoặc cấu hình tương đương được framework cung cấp. Trong Spring Boot, auto-configuration JMX phụ thuộc phiên bản và thuộc tính ứng dụng, chẳng hạn \`spring.jmx.enabled=true\`; không nên tạo nhiều exporter chồng chéo đăng ký cùng \`ObjectName\`.

Cách annotation phù hợp khi dự án dùng Spring quản lý bean và muốn kiểm soát bề mặt JMX ngay tại adapter. Cách Standard MBean phù hợp khi cần hợp đồng JMX Java chuẩn rõ ràng hoặc muốn tránh Spring-specific annotation trong chính lớp adapter.

## 8. Khi nào quản trị chỉ đọc, khi nào cho phép điều khiển?

Không phải trạng thái nào có thể quan sát cũng cần có setter hoặc operation thay đổi nó.

| Nhu cầu | Management interface | Bề mặt JMX |
| --- | --- | --- |
| Xem worker đang pause | \`snapshot().paused()\` | Read-only attribute \`Paused\` |
| Xem backlog | \`snapshot().queueDepth()\` | Read-only attribute \`QueueDepth\` |
| Xem tổng tác vụ hoàn thành | \`snapshot().processedTotal()\` | Read-only attribute \`ProcessedTotal\` |
| Dừng nhận tác vụ nền tạm thời | \`pause()\` | Operation \`pause\` |
| Tiếp tục xử lý | \`resume()\` | Operation \`resume\` |
| Đổi nội dung một đơn hàng | Business use case với authorization | Không xuất operation JMX chung chung |

Với hệ thống nhiều instance, cần làm rõ lệnh tác động tới một JVM, một worker group hay toàn bộ cụm. Một JMX operation trên instance A không tự động broadcast sang B/C. Nếu cần lệnh toàn cụm, application port phải dùng cơ chế điều phối phân tán thay vì giả định JMX đảm nhận việc này.

Các lệnh quản trị nguy hiểm như xóa queue, reset transaction state hoặc thay đổi policy phải có kiểm soát riêng: xác thực/phân quyền ở connector, giới hạn hành vi ở tầng ứng dụng, kiểm toán, và điều kiện bảo vệ tính nhất quán.

## 9. Không để business interface bị ô nhiễm bởi JMX

Một ví dụ dễ gặp:

\`\`\`java
public interface OrderService {
    String placeOrder(PlaceOrderCommand command);
    void cancelOrder(String orderId);

    // Không thuộc hợp đồng nghiệp vụ:
    long getProcessedTotal();
    void resetManagementStatistics();
    void reRegisterMBean();
}
\`\`\`

Cấu trúc trên trộn use case với quản trị và lifecycle JMX. Tách thành:

\`\`\`java
public interface OrderOperations {
    String placeOrder(PlaceOrderCommand command);
    void cancelOrder(String orderId);
}

public interface OrderWorkerManagement {
    OrderWorkerSnapshot snapshot();
    void pause();
    void resume();
}
\`\`\`

Operation \`reRegisterMBean()\` thường không thuộc management port ứng dụng. Đó là trách nhiệm lifecycle của adapter/exporter, \`MBeanServer\` hoặc infrastructure. Đừng đưa nó vào domain service.

Tương tự, tránh để management port nhận/trả trực tiếp \`ObjectName\`, \`MBeanInfo\`, \`AttributeList\` hoặc ném \`JMException\`. Các kiểu này thuộc JMX adapter. Để port dùng kiểu Java/domain có ý nghĩa với ứng dụng, adapter chuyển lỗi và kiểu dữ liệu theo yêu cầu JMX.

## 10. Lệnh quản trị phải đi qua cùng quy tắc nghiệp vụ

Tách interface không có nghĩa tạo đường tắt vượt quy tắc miền. Ví dụ \`pause()\` không thể được sử dụng để vô hiệu hóa invariant của giao dịch đang xử lý; nó nên đánh dấu “không nhận thêm công việc mới” và cho phép tác vụ dở dang hoàn tất an toàn.

Nếu vận hành cần điều chỉnh giới hạn concurrency, management port có thể định nghĩa:

\`\`\`java
public interface WorkerTuning {
    int currentConcurrencyLimit();
    void changeConcurrencyLimit(int requested);
}
\`\`\`

Application service chịu trách nhiệm xác minh \`requested\` nằm trong khoảng hợp lệ, xem tác động của việc thay đổi và điều phối với executor. Adapter JMX chỉ chuyển \`getConcurrencyLimit()\` và \`setConcurrencyLimit(int)\` đến port. MBean setter không được tự ý chỉnh trực tiếp thread pool mutable của domain mà thiếu kiểm tra.

Lệnh lâu nên trả về nhanh cùng một request ID/trạng thái để theo dõi. Không giữ thread gọi JMX trong suốt quá trình retry hay xử lý dữ liệu lớn.

## 11. Snapshot và ranh giới đồng thời

Bề mặt quản trị thường cần đọc trạng thái trong khi nhiều thread đang chạy. Một interface đọc \`snapshot()\` rõ ràng giúp đặt trách nhiệm tạo ảnh chụp nhất quán vào application layer.

\`\`\`java
public record WorkerSnapshot(
    boolean paused,
    int queued,
    int running,
    long completed
) {}
\`\`\`

Nếu \`queued\`, \`running\` và \`completed\` cần tương ứng cùng một thời điểm, service phải đồng bộ hoặc công bố một immutable snapshot đã được tính toán chung, ví dụ \`AtomicReference<WorkerSnapshot>\`. Tập hợp các getter trả các biến \`volatile\` riêng không đảm bảo tính nguyên tử cho toàn bộ bản snapshot.

MBean adapter có thể gọi \`snapshot()\` cho từng getter, vì mỗi thuộc tính JMX được đọc độc lập. Nếu client cần bảo đảm nhất quán trên nhiều trường, hãy tạo snapshot JMX kiểu phù hợp (ví dụ \`CompositeData\`) hoặc chấp nhận và tài liệu hóa tính chất eventually consistent của từng metric.

## 12. Kiểm thử ba tầng

### 12.1. Kiểm thử logic nghiệp vụ

Kiểm tra \`OrderOperations\` hoạt động theo quy tắc domain, không cần dựng \`MBeanServer\`. Đây là bằng chứng rằng business use case độc lập JMX.

### 12.2. Kiểm thử adapter bằng fake port

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.time.Instant;

class OrderWorkerJmxAdapterTest {
    @Test
    void delegatesManagementCallsOnly() {
        class Fake implements OrderWorkerManagement {
            boolean paused;
            @Override
            public OrderWorkerSnapshot snapshot() {
                return new OrderWorkerSnapshot(
                    paused, 5, 12, Instant.parse("2026-01-01T00:00:00Z")
                );
            }
            @Override
            public void pause() { paused = true; }
            @Override
            public void resume() { paused = false; }
        }

        Fake fake = new Fake();
        OrderWorkerJmxAdapter adapter = new OrderWorkerJmxAdapter(fake);

        assertEquals(5, adapter.getQueueDepth());
        assertEquals(12, adapter.getProcessedTotal());
        adapter.pause();
        assertTrue(fake.paused);
        adapter.resume();
        assertFalse(fake.paused);
    }
}
\`\`\`

Adapter test chỉ cần management port, không cần bean nghiệp vụ hay Spring context đầy đủ.

### 12.3. Kiểm thử tích hợp MBeanServer

Tạo test context và kiểm tra \`ObjectName\` được đăng ký, các attribute \`Paused\`, \`QueueDepth\`, \`ProcessedTotal\` có thể đọc, operation \`pause\`/\`resume\` gọi đúng logic. Đóng context và unregister MBean để tránh ảnh hưởng test khác.

Có thể thêm quy tắc kiến trúc (ví dụ ArchUnit) chặn các package \`domain\` và \`application\` import \`org.springframework.jmx\` và \`javax.management\`; chỉ package \`adapter.jmx\` hoặc \`infrastructure.jmx\` được phép phụ thuộc chúng.

## 13. Chọn mức độ tách interface

Ba cách thường dùng:

| Cách | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Service thực thi business + management ports | Ít lớp, quản lý một trạng thái | Module nhỏ, nhiệm vụ quản trị đơn giản |
| Service quản trị riêng gọi application/domain API | Phân trách nhiệm tốt hơn | Nhiều metric và operation, chính sách vận hành phức tạp |
| Management facade/read model độc lập và JMX adapter | Hạn chế truy cập trực tiếp lõi, dễ thay protocol | Hệ thống lớn, nhiều kênh vận hành |

Dù chọn cách nào, adapter JMX không nên import repository hoặc aggregate để sửa trạng thái tùy tiện. Khi chỉ cần số liệu kỹ thuật thuần túy (CPU, memory, thread), có thể dùng Platform MXBeans hoặc hệ thống metrics thay vì thêm phương thức không thuộc miền vào service.

## 14. Các lỗi thường gặp

- **Đặt \`@ManagedResource\` ngay trên domain entity:** Chuyển annotation sang adapter.
- **Cho business interface kế thừa \`SomethingMBean\`:** Đảo chiều phụ thuộc bằng management port riêng và adapter triển khai MBean.
- **Đưa \`ObjectName\` vào DTO nghiệp vụ:** Giữ định danh JMX trong infrastructure.
- **Xuất mọi method public của service:** Dùng Standard MBean interface nhỏ hoặc adapter annotate đúng method.
- **Cho phép sửa trực tiếp trường trạng thái qua JMX setter:** Chuyển thành application command có validate và điều kiện chuyển trạng thái.
- **Tạo management operation không có audit và policy:** Định nghĩa quyền, log và guard cho từng lệnh ảnh hưởng hệ thống.
- **Nhầm tách interface với tách service:** Hai interface có thể cùng được một class triển khai; mục tiêu là tách hợp đồng và dependency.

## 15. Ghi nhớ

**Business interface nói ứng dụng làm gì cho nghiệp vụ; management interface nói người vận hành được xem và điều khiển gì; JMX interface/adapter nói chúng được biểu diễn qua JMX ra sao.** Ba vai trò cần tách rõ, dù đôi khi được thực thi bởi cùng một service. Khi thay, tắt hoặc kiểm thử JMX mà không cần sửa hợp đồng nghiệp vụ, thiết kế đã đạt được tính độc lập cần thiết.
