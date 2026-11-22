# Cache listener trong multicaster của Spring Framework

## 1. Vì sao multicaster cần cache danh sách listener?

Trong mô hình **Spring Application Events**, code phát sự kiện qua `ApplicationEventPublisher.publishEvent(...)`, còn `ApplicationEventMulticaster` quyết định những `ApplicationListener` nào phù hợp rồi gọi chúng. Một context có thể chứa rất nhiều listener: listener nhận `OrderPlacedEvent`, listener nhận `PaymentCapturedEvent`, listener tổng quát nhận `ApplicationEvent`, listener từ `@EventListener`, listener có ràng buộc generic hoặc loại `source` đặc biệt.

Nếu mỗi lần phát một event, Spring phải quét lại toàn bộ danh sách listener, phân tích generic type của từng bean và kiểm tra khả năng nhận event, công việc **chọn listener** có thể trở thành overhead đáng kể ở đường xử lý nóng (hot path). Do đó, các multicaster tiêu chuẩn dựa trên `AbstractApplicationEventMulticaster` có cơ chế **cache kết quả tiền lọc listener** cho các loại event/source đã gặp.

Mục đích của cache này:

- Giảm số lần kiểm tra listener có hỗ trợ một loại event và source type hay không.
- Hạn chế việc lặp lại một số bước suy luận generic type / lựa chọn bean listener.
- Tăng hiệu quả khi ứng dụng phát **rất nhiều event cùng loại** với tập listener ít thay đổi.
- Vẫn bảo toàn khả năng làm mới danh sách khi một listener được thêm hoặc gỡ qua API của multicaster.

**Cache listener không phải là cache nội dung event, không phải cache kết quả nghiệp vụ, không phải hệ thống lưu trữ sự kiện, và không làm listener bỏ qua các event tiếp theo.**

Ví dụ: phát liên tục 10.000 `OrderPlacedEvent` cùng source type. Spring có thể tái sử dụng tập *ứng viên listener phù hợp theo type* cho các lần phát sau; tuy nhiên listener `onOrderPlaced(...)` vẫn được gọi cho **từng event**, điều kiện `@EventListener(condition=...)` vẫn phải được đánh giá với **dữ liệu từng event**, và business logic vẫn chạy theo những lần nhận thực tế.

## 2. Vị trí cache trong luồng phân phối event

Luồng khái niệm:

~~~text
ApplicationEventPublisher.publishEvent(event)
    |
    v
ApplicationContext
    |
    v
ApplicationEventMulticaster.multicastEvent(event, eventType)
    |
    v
AbstractApplicationEventMulticaster.getApplicationListeners(...)
    |
    +-- Tạo key từ ResolvableType(event) + sourceType(event)
    |
    +-- Cache hit phù hợp?
    |       |
    |       +-- Có -> dùng danh sách listener đã tiền lọc
    |       |
    |       +-- Không -> kiểm tra listener theo event/source type
    |                   -> có thể lưu kết quả vào cache
    |
    v
SimpleApplicationEventMulticaster.invokeListener(...)
    |
    +-- ApplicationListener / GenericApplicationListener
    |       -> xử lý event mới
    |
    +-- ApplicationListenerMethodAdapter (@EventListener)
            -> đánh giá condition cho EVENT hiện tại
            -> gọi phương thức nếu condition thỏa
~~~

Những lớp cần phân biệt:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `ApplicationEventPublisher` | API mà application code dùng để công bố event. |
| `ApplicationContext` | Thường là publisher và ủy quyền việc phát cho multicaster. |
| `ApplicationEventMulticaster` | Quản lý listener, chọn listener thích hợp và phân phối event. |
| `AbstractApplicationEventMulticaster` | Cung cấp đăng ký listener và logic lựa chọn/tiền lọc có cache. |
| `SimpleApplicationEventMulticaster` | Triển khai phát sự kiện; mặc định gọi listener đồng bộ trên thread của publisher, có thể cấu hình executor. |
| `GenericApplicationListener` | Listener có thể khai báo hỗ trợ `ResolvableType` và `sourceType`; hữu ích để giải thích cơ chế matching. |
| `ApplicationListenerMethodAdapter` | Bộ chuyển đổi dùng cho method `@EventListener`; có logic xử lý điều kiện và method arguments. |

**Điểm tách rời quan trọng:** `getApplicationListeners(...)` giúp tìm **ai có khả năng nhận** event theo type/source. Nó không nhất thiết quyết định rằng phương thức đã đủ điều kiện nghiệp vụ để chạy. Ví dụ listener có `@EventListener(condition="#p0.amount() > 1000")` vẫn có thể nằm trong tập ứng viên được cache cho mọi `PaymentChanged`; từng lần nhận nó phải kiểm tra `amount()` của event cụ thể.

## 3. Cache key: ResolvableType của event và Class của source

Trong triển khai `AbstractApplicationEventMulticaster` thuộc nhánh Spring Framework 6.2, key tiền lọc listener bao gồm hai phần chính:

1. **`ResolvableType eventType`**: thông tin kiểu event; có thể mang theo generic type nếu Spring biết được.
2. **`Class<?> sourceType`**: class của `event.getSource()` (khi có).

Ví dụ:

~~~text
Key A:
  eventType = OrderPlacedEvent
  sourceType = String
  -> danh sách listener ứng viên cho event loại này và source class này

Key B:
  eventType = OrderPlacedEvent
  sourceType = Integer
  -> một key khác dù cùng lớp event

Key C:
  eventType = PaymentCapturedEvent
  sourceType = String
  -> một key khác vì event type khác
~~~

**Source type không phải nội dung source.** Hai event có `getSource()` trả ra chuỗi khác nhau (`"checkout-1"` và `"checkout-2"`) vẫn dùng **cùng source class `String`**, nên có thể chung key. Event có source là `Integer` khác key dù payload nghiệp vụ không đổi.

Với payload object được publish trực tiếp, Spring thường bao nó thành `PayloadApplicationEvent<T>`. `ResolvableType` có thể bao gồm thông tin payload generic `T` để chọn listener theo kiểu payload. Vì vậy không nên chỉ nhìn `event.getClass() == PayloadApplicationEvent.class` rồi cho rằng mọi payload sẽ có cùng tập listener. **Thông tin generic có thể là thành phần quan trọng của matching**.

Đây là mô tả theo triển khai của Spring 6.2, **không phải lời hứa công khai rằng mọi subclass, mọi phiên bản Spring và mọi cấu hình đều có cùng một cache-key implementation**. Khi tùy chỉnh multicaster, cần đọc Javadoc/source của đúng phiên bản đang dùng.

## 4. Cache miss, cache hit và chi phí matching

### 4.1. Lần đầu gặp một key

Trong đường xử lý thông thường, khi cache chưa có entry cho `(eventType, sourceType)`, multicaster có thể:

- Lấy danh sách listener đã đăng ký trực tiếp.
- Lấy tên listener bean từ `BeanFactory` khi thích hợp.
- Kiểm tra listener hỗ trợ event type hay không.
- Với listener hỗ trợ lọc source, kiểm tra `sourceType`.
- Sắp xếp listener theo `Ordered` / `@Order` khi cần.
- Lưu tập listener đã tiền lọc (hoặc thông tin tên bean phù hợp) vào một cấu trúc cache.

Một cache miss không có nghĩa “không listener nào nhận”. Nó chỉ có nghĩa chưa có kết quả lựa chọn sẵn cho key đó. Kể cả **tập kết quả rỗng** cũng có thể hữu ích để tránh quét lại ứng viên mỗi lần phát một kiểu event không được quan tâm.

### 4.2. Những lần tiếp theo cùng key

Ở cache hit đã được khởi tạo, Spring có thể bỏ qua những bước chọn ứng viên lặp lại, dùng danh sách/metadata đã lưu rồi thực hiện dispatch. **Mỗi event vẫn cần được gửi cho listener tương ứng**; cache không phải công cụ dedup và không làm giảm số lần gọi method nghiệp vụ.

Điều này đặc biệt hữu ích khi hệ thống lặp lại cùng một số ít event types. Ví dụ:

~~~text
10.000 OrderPlacedEvent cùng source class
    |
    +-- lượt đầu: tính tập ứng viên
    +-- lượt sau: có thể lấy tập ứng viên đã tiền lọc
    |
    +-- listener vẫn nhận 10.000 event
~~~

Nếu mỗi event có một source class khác hoặc rất nhiều event types động, tỷ lệ cache hit có thể kém hơn, dù số lượng event vẫn lớn.

### 4.3. Không phải mọi lookup đều chắc chắn cache được

Spring có các biện pháp tránh cache những class không được coi là **cache-safe** đối với bean classloader của ứng dụng. Trong môi trường có classloader thay đổi như hot reload, plugin loading hoặc ứng dụng container phức tạp, không nên khẳng định mọi event đều luôn có entry cache.

Ở đường concurrency, một thread có thể gặp entry đang được thread khác xây dựng; Spring có thể thực hiện lựa chọn cục bộ thay vì coi entry chưa hoàn thiện là kết quả hợp lệ. Điều này bảo vệ tính đúng đắn, nhưng có nghĩa **đếm số lần matching trên hệ thống đa luồng không phải là cách đo “cache hit tuyệt đối”**.

## 5. Khi thêm hoặc gỡ listener, cache có còn đúng không?

Nếu tập listener thay đổi nhưng cache không thay đổi, multicaster có thể phát event cho listener đã gỡ hoặc không nhận ra listener mới. Vì vậy **việc vô hiệu hóa cache (cache invalidation) là một phần bắt buộc của cơ chế đăng ký listener**.

Trong implementation Spring 6.2, các API thay đổi tập listener như sau làm cache lựa chọn được làm mới:

- `addApplicationListener(listener)`: thêm listener instance.
- `addApplicationListenerBean(beanName)`: thêm listener theo tên bean.
- `removeApplicationListener(listener)`: gỡ instance.
- `removeApplicationListenerBean(beanName)`: gỡ listener bean.
- `removeApplicationListeners(predicate)` và `removeApplicationListenerBeans(predicate)`: gỡ theo điều kiện.
- `removeAllListeners()`: gỡ toàn bộ listener đã đăng ký.

Lược đồ:

~~~text
Cache: (TicketEvent, String) -> [TicketListener]
            |
            | multicaster.removeApplicationListener(TicketListener)
            v
      Cache lựa chọn được làm mới
            |
            | publish TicketEvent mới
            v
      Không gọi TicketListener đã bị gỡ

multicaster.addApplicationListener(TicketListener)
            |
            v
      Cache được làm mới lần nữa
            |
            | publish TicketEvent cùng key cũ
            v
      TicketListener có thể lại được chọn
~~~

**Không cần — và không nên — thao tác trực tiếp vào `retrieverCache` bằng reflection để “xóa cho chắc”.** Nó là chi tiết implementation nội bộ. Hãy đăng ký hoặc gỡ listener thông qua API chính thức.

Một khác biệt cần nhớ: nếu **thay đổi trạng thái nội bộ** của một listener mà không thay đổi đăng ký, Spring không tự coi đó là lý do invalidation. Nếu listener có `supportsEventType(...)` hoặc `supportsSourceType(...)` phụ thuộc vào biến mutable thay đổi theo thời gian, kết quả cache có thể không phản ánh cách bạn muốn dùng chúng. Hãy coi các predicate này là **khả năng hỗ trợ kiểu tương đối ổn định**, không dùng chúng làm bộ lọc nội dung event thay đổi từng lần.

## 6. Ví dụ Java 17+ chạy được: quan sát matching được cache

Ví dụ dưới đây không đụng tới field cache nội bộ. Thay vào đó, nó viết một `GenericApplicationListener` đếm số lần Spring hỏi **“listener này có hỗ trợ event type không?”**, rồi phát nhiều event và thay đổi đăng ký.

Trong một `SimpleApplicationEventMulticaster` độc lập theo phiên bản đã chốt, các lần phát event cùng type và cùng source class tái sử dụng tập ứng viên, nên bộ đếm type-check không tăng cho lần thứ hai. Sau khi source class thay đổi, key khác và bộ đếm tăng. Sau khi gỡ rồi thêm lại listener, kết quả matching cần được tính lại.

Ví dụ dùng Spring Framework **6.2.9** (chốt phiên bản để đầu ra có ý nghĩa), Java 17+ và Maven. Không cần tạo `ApplicationContext` vì chúng ta muốn quan sát **trực tiếp multicaster** mà không có các lifecycle listener từ context.

### 6.1. Cấu trúc dự án

~~~text
listener-cache-demo/
├── pom.xml
└── src/main/java/ListenerCacheDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>listener-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/ListenerCacheDemo.java`:

~~~java
import org.springframework.context.ApplicationEvent;
import org.springframework.context.event.GenericApplicationListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.ResolvableType;

public class ListenerCacheDemo {

    public static final class TicketEvent extends ApplicationEvent {
        private final String ticketId;

        public TicketEvent(Object source, String ticketId) {
            super(source);
            this.ticketId = ticketId;
        }

        public String ticketId() {
            return ticketId;
        }
    }

    public static final class CountingListener
            implements GenericApplicationListener {

        private int typeChecks;
        private int received;

        @Override
        public boolean supportsEventType(ResolvableType eventType) {
            typeChecks++;
            return TicketEvent.class.equals(eventType.toClass());
        }

        @Override
        public void onApplicationEvent(ApplicationEvent event) {
            TicketEvent ticketEvent = (TicketEvent) event;
            received++;
            System.out.println("HANDLE " + ticketEvent.ticketId());
        }

        public int typeChecks() {
            return typeChecks;
        }

        public int received() {
            return received;
        }
    }

    public static void main(String[] args) {
        var multicaster = new SimpleApplicationEventMulticaster();
        var listener = new CountingListener();

        multicaster.addApplicationListener(listener);

        // Hai event cùng loại + source đều thuộc String.class.
        multicaster.multicastEvent(new TicketEvent("web-1", "T-1"));
        multicaster.multicastEvent(new TicketEvent("web-2", "T-2"));

        System.out.println("TYPE_CHECKS_AFTER_TWO="
                + listener.typeChecks());

        // Cùng event type nhưng source là Integer thay vì String.
        multicaster.multicastEvent(new TicketEvent(42, "T-3"));

        System.out.println("TYPE_CHECKS_NEW_SOURCE="
                + listener.typeChecks());

        // Gỡ listener và phát thêm event: không còn handler.
        multicaster.removeApplicationListener(listener);
        multicaster.multicastEvent(new TicketEvent("web-3", "T-4"));
        System.out.println("RECEIVED_WHILE_REMOVED="
                + listener.received());

        // Đăng ký lại listener; lựa chọn theo type được tính lại.
        multicaster.addApplicationListener(listener);
        multicaster.multicastEvent(new TicketEvent("web-4", "T-5"));

        System.out.println("TYPE_CHECKS_AFTER_READD="
                + listener.typeChecks());
        System.out.println("TOTAL_RECEIVED=" + listener.received());
    }
}
~~~

Chạy trong thư mục chứa `pom.xml` với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ListenerCacheDemo
~~~

**Stdout của chương trình ở cấu hình minh họa (Spring Framework 6.2.9, multicaster đồng bộ, không có listener khác):**

~~~text
HANDLE T-1
HANDLE T-2
TYPE_CHECKS_AFTER_TWO=1
HANDLE T-3
TYPE_CHECKS_NEW_SOURCE=2
RECEIVED_WHILE_REMOVED=3
HANDLE T-5
TYPE_CHECKS_AFTER_READD=3
TOTAL_RECEIVED=4
~~~

### 6.2. Đọc kết quả cho đúng

- `T-1`: Spring phải tìm tập listener cho key `(TicketEvent, String)` lần đầu, nên gọi `supportsEventType(...)`.
- `T-2`: vẫn là `TicketEvent` và source class `String`, nên sử dụng lựa chọn đã cache; `typeChecks` không tăng, nhưng `onApplicationEvent(...)` **vẫn chạy**.
- `T-3`: event type không đổi, nhưng source là `Integer`, tạo key khác. Spring kiểm tra hỗ trợ event type lại, nên `typeChecks` tăng thành 2.
- Gỡ listener rồi phát `T-4`: multicaster không gọi listener đã gỡ; `received` vẫn là 3. Không nên nhầm việc này với một condition nghiệp vụ đã chặn event.
- Thêm listener lại rồi phát `T-5`: tập đăng ký và cache đã thay đổi; Spring kiểm tra lại khả năng nhận event type, đưa bộ đếm lên 3.
- Tổng số lần `onApplicationEvent(...)` chạy là **4**, dù số lần kiểm tra `supportsEventType(...)` chỉ là 3. Đây chính là khác biệt giữa **matching cache** và **invocation**.

**Giới hạn của cách đo:** bộ đếm này phản ánh việc gọi một predicate matching trong cấu hình demo, không đo trực tiếp latency, allocation hay tốc độ throughput. Nó cũng không đại diện cho số cache hit/miss trong mọi phiên bản Spring hoặc mọi custom multicaster. Nếu cần quan sát implementation field thật, dùng profiler/source khi điều tra nhưng tránh biến field nội bộ thành API ứng dụng.

## 7. GenericApplicationListener, SmartApplicationListener và @EventListener

### 7.1. ApplicationListener<E> đơn giản

~~~java
@Component
class OrderListener implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        // Business logic cho event đã matching.
    }
}
~~~

*Đoạn tích hợp minh họa: cần import `ApplicationListener`, `@Component` và định nghĩa `OrderPlacedEvent extends ApplicationEvent`.*

Với listener kiểu này, Spring dùng thông tin generic type (`OrderPlacedEvent`) để xét loại event phù hợp. Tùy class và bean configuration, lớp `GenericApplicationListenerAdapter` có thể hỗ trợ việc phân tích generic type của listener.

### 7.2. GenericApplicationListener khi cần lọc event/source type

~~~java
class RegionListener implements GenericApplicationListener {

    @Override
    public boolean supportsEventType(ResolvableType eventType) {
        return OrderPlacedEvent.class.isAssignableFrom(
                eventType.toClass());
    }

    @Override
    public boolean supportsSourceType(Class<?> sourceType) {
        return sourceType != null &&
                RegionEventPublisher.class.isAssignableFrom(sourceType);
    }

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        // Xử lý event đã qua bước matching.
    }
}
~~~

*Đây là mã tích hợp minh họa: cần định nghĩa `OrderPlacedEvent`, `RegionEventPublisher` và import `GenericApplicationListener`, `ResolvableType` và `ApplicationEvent`.*

Ở đây `supportsSourceType(...)` nhận **Class**, không phải instance `source`; không nên viết logic đòi kiểm tra field `regionId` của một source object. Nếu cần lọc theo dữ liệu riêng của từng event, hãy dùng condition hoặc kiểm tra trong handler.

### 7.3. @EventListener có condition

~~~java
@EventListener(condition = "#p0.totalMinorUnits() >= 100000")
public void onLargeOrder(OrderPlaced event) {
    // Mỗi event có giá trị totalMinorUnits khác nhau.
}
~~~

*Snippet minh họa cho một bean có method nhận record `OrderPlaced` phù hợp.*

Spring có thể cache việc xác định **method listener hỗ trợ loại OrderPlaced**. Nhưng **điều kiện SpEL phải được kiểm tra cho từng payload**, vì event `A` có số tiền 120.000 còn event `B` có thể chỉ 30.000. Vì vậy:

~~~text
Same eventType/sourceType
    |
    +-- listener candidate list: cached
    |
    +-- Event A: total=120000 -> condition true -> handler invoked
    |
    +-- Event B: total=30000  -> condition false -> handler skipped
~~~

Đây là điểm thường gây nhầm: “listener nằm trong cache” **không có nghĩa** `@EventListener(condition)` đã được đánh giá thành true và được lưu vĩnh viễn.

## 8. Listener bean, singleton và prototype: cache giữ những gì?

Multicaster có thể đăng ký listener theo hai đường:

~~~java
multicaster.addApplicationListener(existingListener);
multicaster.addApplicationListenerBean("auditEventListener");
~~~

*Hai lời gọi minh họa cho multicaster đã được gắn BeanFactory nếu dùng đường đăng ký theo bean name.*

- `addApplicationListener(...)` nhận instance và đưa vào tập listener được quản lý bởi multicaster.
- `addApplicationListenerBean(...)` nhận **tên bean**, cho phép multicaster lấy bean qua `BeanFactory` và tránh một số công việc khởi tạo không cần thiết ở giai đoạn đăng ký.
- Trong triển khai Spring 6.2, cache có thể giữ **listener instance** và/hoặc **tên listener bean** đã tiền lọc, thay vì cố giữ vĩnh viễn mọi instance cho tất cả scope.
- Với bean không phải singleton, Spring cần giữ semantics của bean scope; **không nên khẳng định** mọi lần phát cùng key sẽ tái sử dụng một object prototype duy nhất vì cache có entry.

Khi debug prototype listener, hãy phân biệt chi phí **chọn kiểu listener** với chi phí **khởi tạo instance**. Cache matching có thể giúp giảm một loại overhead, nhưng prototype creation vẫn có chi phí và vòng đời riêng.

**Khuyến nghị:** dùng singleton, stateless listener cho phần lớn domain/application events. Nếu cần dữ liệu mỗi event, truyền qua payload hoặc tạo state cục bộ trong handler; tránh đưa mutable state của từng event vào một bean singleton mà không có đồng bộ phù hợp.

## 9. Cache invalidation không thay thế nghiệp vụ động

Một sai lầm kiến trúc là cố dùng `supportsEventType` hoặc `supportsSourceType` để lọc điều kiện thay đổi **theo từng event value** hoặc theo một cờ feature bật/tắt liên tục:

~~~java
// Anti-pattern về tư duy:
@Override
public boolean supportsEventType(ResolvableType type) {
    return featureFlagService.isEnabled() &&
           TicketEvent.class.equals(type.toClass());
}
~~~

*Đoạn minh họa chưa có class/dependency hoàn chỉnh.*

Nếu feature flag đổi trong lúc ứng dụng đang chạy, **cache matching không buộc phải đánh giá lại predicate cho mỗi event cùng key**. Listener có thể tiếp tục nằm trong danh sách ứng viên hoặc bị loại khỏi đó cho đến khi cache thay đổi vì lý do khác.

Nếu cần feature flag trên mỗi occurrence:

~~~java
@Override
public boolean supportsEventType(ResolvableType type) {
    return TicketEvent.class.equals(type.toClass());
}

@Override
public void onApplicationEvent(ApplicationEvent event) {
    if (!featureFlagService.isEnabled()) {
        return;
    }
    handleTicket((TicketEvent) event);
}
~~~

*Đoạn tích hợp minh họa; cần định nghĩa `featureFlagService` và `handleTicket`.*

Bằng cách đó, type matching vẫn ổn định, còn quyết định nghiệp vụ được đánh giá **mỗi lần event đến**. Nếu cần dừng hẳn listener vì thay đổi cấu hình, có thể gỡ listener bằng API đăng ký/gỡ chính thức rồi thêm lại khi phù hợp, nhưng hãy quản lý thread-safety, lifecycle và ownership rõ ràng.

Tương tự, không dùng cache matching để suy luận rằng listener đã xử lý thành công event lần trước. Nếu business handler thất bại, cache ứng viên không “nhớ” thất bại hoặc tự thực hiện retry.

## 10. Generic event types và PayloadApplicationEvent

Spring hỗ trợ lựa chọn listener theo kiểu generic thông qua `ResolvableType`. Đây là lý do `multicastEvent(event, eventType)` nhận cả type hint nếu có.

Ví dụ một hệ thống có:

~~~java
public record OrderPlaced(String orderId) {}
public record PaymentCaptured(String paymentId) {}
~~~

Khi gọi:

~~~java
publisher.publishEvent(new OrderPlaced("ORD-1"));
publisher.publishEvent(new PaymentCaptured("PAY-1"));
~~~

*Các đoạn này là mô hình tích hợp minh họa với `ApplicationEventPublisher`; cần import và bean context phù hợp.*

Các object không kế thừa `ApplicationEvent` được Spring bao thành `PayloadApplicationEvent<OrderPlaced>` hoặc `PayloadApplicationEvent<PaymentCaptured>` về mặt generic typing. Listener method có thể khai báo `onOrderPlaced(OrderPlaced event)` và `onPayment(PaymentCaptured event)` để Spring phân phối đúng.

**Không phải cứ wrapper runtime class giống nhau là cache matching giống nhau.** `ResolvableType` mang thông tin payload type nếu có. Nếu công bố event với generic type bị xóa hoặc type hint không đầy đủ, behavior matching có thể khác; khi thiết kế event generic thực thụ, cân nhắc triển khai `ResolvableTypeProvider` hoặc cung cấp type hint qua API thích hợp nếu Spring yêu cầu.

Một vấn đề hiệu năng thực tế là có quá nhiều event types rất đặc thù hoặc source classes động. Khi đó số cache key có thể tăng. Tuy nhiên **không nên tối ưu bằng cách gộp tất cả event vào một `ObjectEvent` rồi tự switch kiểu ở mọi listener**, vì điều đó mất type safety và làm contract khó bảo trì. Chỉ đổi event design khi có kết quả đo chứng minh bottleneck.

## 11. Đồng bộ, bất đồng bộ và thứ tự listener

Cache ứng viên **không quyết định** thread sẽ chạy listener. `SimpleApplicationEventMulticaster` mặc định gọi listener trong thread publisher. Khi cấu hình executor, nó có thể chạy listener trên thread khác:

~~~java
var multicaster = new SimpleApplicationEventMulticaster();
multicaster.setTaskExecutor(eventExecutor);
~~~

*Đoạn tích hợp; cần có `eventExecutor` phù hợp và quản lý vòng đời executor.*

Những điều khác nhau:

| Thuộc tính | Cache lựa chọn listener | Executor / @Async |
| --- | --- | --- |
| Mục tiêu | Giảm overhead tìm listener phù hợp | Thay đổi nơi và lúc listener thực thi |
| Đầu vào | Event type, source type và registry | Task, queue, worker thread |
| Kết quả | Tập ứng viên listener | Lịch thực thi listener |
| Có làm body listener chạy ít đi? | Không, trừ việc lọc type vốn phải có | Không tự giảm số event, chỉ có thể thay đổi concurrency |
| Có tự đưa ThreadLocal sang worker? | Không | Không mặc định; cần context propagation phù hợp |
| Có bảo đảm retry/durable delivery? | Không | Không |

Khi executor bất đồng bộ, thứ tự hoàn tất có thể khác thứ tự publish, dù danh sách listener được sắp theo `@Order`. Spring 6.1+ còn có `supportsAsyncExecution()` để một số listener (ví dụ transaction-synchronized listener) yêu cầu chạy trong thread gốc ở mức multicaster.

Đừng quy lỗi **listener chạy muộn**, **mất ThreadLocal**, **thứ tự log khác** hoặc **transaction không còn** cho cache lựa chọn. Đó thường là câu chuyện về scheduling, context propagation, transaction hoặc vòng đời.

## 12. Hiệu năng: cache matching giúp bao nhiêu?

Không có con số “nhanh hơn X%” cố định cho mọi ứng dụng. Lợi ích phụ thuộc:

- Số lượng listener đã đăng ký.
- Số loại event và source class thực tế.
- Tỷ lệ lặp lại key `(eventType, sourceType)`.
- Độ phức tạp của generic matching, `supportsEventType` và `supportsSourceType`.
- Singleton/prototype bean resolution.
- Chi phí body listener: truy vấn DB, HTTP, ghi file, serialization, logging, transaction và retry.
- Executor queueing, context switching, allocation, contention và GC.
- Tần suất đăng ký/gỡ listener động gây cache invalidation.

Nếu mỗi listener gọi HTTP 200 ms, việc cache matching tiết kiệm vài phép kiểm tra sẽ khó trở thành bottleneck chính. Ngược lại, với event nội bộ rất ngắn, tần suất cao và hàng trăm listener, overhead chọn ứng viên có thể đáng quan tâm.

### 12.1. Đo đúng thứ cần đo

Để đánh giá hiệu quả, nên phân biệt:

1. **End-to-end publish latency:** từ lúc gọi `publishEvent` đến khi các listener đồng bộ hoàn tất (không đồng nghĩa hoàn tất nếu có async).
2. **Listener selection overhead:** chi phí tìm ứng viên theo event/source type.
3. **Listener invocation overhead:** tạo adapter/điều phối/gọi handler.
4. **Business handler latency:** DB, network, lock, IO, các rule nghiệp vụ.
5. **Async queue delay:** thời gian chờ trước khi worker chạy.
6. **Allocation/GC:** allocation từ event instances, adapters, context propagation và logging.

Trong profiling, hãy xác định stack/frame thực tế có nhiều thời gian ở `AbstractApplicationEventMulticaster.getApplicationListeners(...)`, `GenericApplicationListenerAdapter`, `ApplicationListenerMethodAdapter` hay ở chính handler.

### 12.2. Benchmark đáng tin thay vì System.nanoTime một lần

Nếu cần kiểm thử microbenchmark, dùng **JMH** hoặc profiler tương đương, kèm:

- Warm-up JVM/JIT và làm ấm các loại event được thử.
- Test một event type lặp lại, nhiều event type xen kẽ, source types đa dạng.
- So sánh số lượng listener khác nhau, ví dụ 10/100/1000.
- Không đưa `System.out.println(...)` vào hot loop: console IO che lấp chi phí lựa chọn.
- Giữ nguyên số listener nhận và cùng business work giữa các lượt đo.
- Nếu chạy async, đo cả queueing/backpressure và thời điểm tất cả listener thật sự hoàn tất.
- Thu p50/p95/p99, throughput, CPU, allocation và lỗi thay vì chỉ một trung bình.
- Kiểm soát môi trường: JDK, Spring version, heap, GC, hardware và quyền CPU.

Ví dụ ở phần 6 minh họa **hành vi matching**, không phải kết quả benchmark. Không suy ra phần trăm cải thiện từ số lần `supportsEventType(...)` được gọi.

## 13. Cache và những vấn đề về classloader, hot reload

Các cấu trúc cache giữ tham chiếu kiểu Java. Trong môi trường thay classloader (devtools restart, plugin unload, server deploy/undeploy), việc giữ class không còn hợp lệ có thể gây vấn đề bộ nhớ. Vì vậy implementation Spring có kiểm tra **cache-safety** trước khi lưu những event/source class trong trường hợp tương ứng.

Một số nguyên tắc:

- Không cố tự cache `Class<?>` hoặc `ResolvableType` bằng static global map không có chiến lược lifecycle khi ứng dụng có dynamic class loading.
- Với mỗi `ApplicationContext` mới, xem registry và cache listener là một phần vòng đời context; không tái dùng một multicaster cũ một cách tùy tiện xuyên các vòng reload.
- Nếu plugin có event class riêng, xác định ai sở hữu và gỡ listener khi plugin unload; không dùng reflection vào cache để “thử xóa”.
- Khi memory profiling, phân biệt cache key hợp lệ với leak do classloader/resource giữ bởi ứng dụng.
- Không đoán size của cache chỉ từ số event đã phát: key liên quan đến **kiểu**, không phải giá trị payload.

Trong hệ thống nhiều source class khác nhau, cache có thể có nhiều entry hơn dự kiến. Đây là lý do nên dùng các source object rõ nghĩa, tránh tạo source type mới ngẫu nhiên cho từng event.

## 14. Các trường hợp tưởng cache sai nhưng nguyên nhân ở nơi khác

| Hiện tượng | Phỏng đoán sai thường gặp | Nguyên nhân cần kiểm tra |
| --- | --- | --- |
| Listener không nhận event mới | Cache giữ danh sách cũ | Event type không khớp, bean chưa đăng ký, context khác, điều kiện SpEL false |
| Listener lúc chạy lúc không | Cache “random” | Dữ liệu event/condition thay đổi, transaction phase, async race |
| Gỡ listener rồi vẫn thấy một log | Cache chưa invalidated | Một task async đã được submit trước khi gỡ; hoặc còn listener khác |
| Listener nhận trùng | Cache gọi hai lần | Nhiều listener cùng xử lý, context hierarchy phát qua parent, đăng ký trùng ở tầng ứng dụng |
| Thêm listener xong event cũ không xuất hiện | Cache không refresh | Spring Application Events không phải event history/replay |
| Listener tăng CPU | Cache “không hiệu quả” | Logic xử lý, IO/logging/SpEL/serialization/lock mới là bottleneck |
| Lỗi generic event routing | Cache key sai | `ResolvableType` không đủ generic information, listener declaration không tương thích |
| Prototype listener có object khác sau nhiều event | Cache không hoạt động | Cache type matching khác bean lifecycle và scope |
| Async listener không thấy transaction | Cache không giữ transaction | Thread-bound transaction không tự chuyển qua executor |
| Feature flag đổi nhưng listener vẫn thuộc tập ứng viên | Cache quá “cứng” | Dùng dynamic business predicate trong `supportsEventType` thay vì tại handler |

### Tác vụ async đã xếp hàng trước khi gỡ listener

Một nuance dễ bỏ sót: ngay cả khi `removeApplicationListener(...)` làm mới cache, **một số task đã được multicaster gửi vào executor trước thời điểm gỡ** có thể vẫn giữ tham chiếu listener. Do vậy có thể thấy thêm log sau thao tác gỡ mà không chứng minh Spring tiếp tục chọn listener đã bị gỡ cho các event được publish *sau đó*.

Nếu cần dừng xử lý tức thời, phải xử lý lifecycle executor, cancellation, drain queue, cờ shutdown và idempotency theo yêu cầu; cache invalidation một mình không hứa “mọi task đang chạy lập tức ngừng”.

## 15. Cách sử dụng an toàn trong ứng dụng thực tế

### 15.1. Giữ listener type ổn định, business filter tại đúng tầng

- Dùng event class/record mô tả rõ sự thật nghiệp vụ.
- Dùng `ApplicationListener<E>` hoặc `@EventListener` typed; tránh `ApplicationListener<ApplicationEvent>` tổng quát cho mọi module nếu không cần.
- Không đặt feature flag động hoặc kiểm tra nội dung event vào `supportsEventType(...)`.
- Với rule ngắn, dùng `@EventListener(condition=...)`; với rule phức tạp, xử lý trong service/handler có test rõ ràng.
- Không cố gắng “precompute business results” trong quá trình chọn type.

### 15.2. Tránh đăng ký/gỡ listener liên tục trong hot path

Nếu mỗi request lại gọi `addApplicationListener(...)` và `removeApplicationListener(...)`, ứng dụng có thể làm mất lợi ích cache và tạo thêm contention. Với phần lớn ứng dụng, listener nên được đăng ký khi context khởi tạo và giữ ổn định.

Nếu nghiệp vụ bắt buộc thay đổi thành phần xử lý, cân nhắc một listener ổn định **ủy quyền tới registry handler động** của riêng ứng dụng có đồng bộ/thread-safety và test phù hợp, thay vì biến danh sách listener của Spring thành cấu trúc thay đổi liên tục theo từng request.

### 15.3. Đừng tối ưu quá sớm bằng cách viết lại multicaster

`SimpleApplicationEventMulticaster` đã có nền tảng matching cache từ `AbstractApplicationEventMulticaster`. Viết custom multicaster chỉ để “thêm cache listener” thường không cần thiết và có nguy cơ phá type matching, thứ tự, lifecycle hoặc transaction semantics.

Khi có bottleneck được chứng minh qua profiling, xem xét thay đổi event design, lượng listener, body handler, batch processing hoặc cách dùng executor **trước** khi tạo cache thứ hai chồng lên cache nội bộ.

### 15.4. Tách event bus nội bộ với broker

Matching cache chỉ giúp dispatch **trong cùng JVM/context**. Nó không làm event trở thành durable, không tự retry, không bảo đảm exactly-once, không giữ offset và không giải quyết giao dịch giữa database với broker.

Nếu event cần đi qua process boundary, dùng broker/outbox/event store phù hợp và đánh giá performance ở tầng serialization, network, queue, partition, consumer handler và database. Không viện dẫn listener cache để khẳng định mất message hay duplicate đã được xử lý.

## 16. Kiểm thử regression và chẩn đoán khi nghi cache

Một bộ kiểm thử có ích nên xác minh **semantics**, không chỉ số lượng cache entry nội bộ:

1. Listener typed nhận đúng loại event; không nhận event khác loại.
2. Hai lần phát cùng event type/source type vẫn gọi handler hai lần.
3. Listener mới thêm qua `addApplicationListener(...)` nhận các event phát **sau** khi thêm.
4. Listener đã gỡ không nhận event mới trong cấu hình đồng bộ không có task tồn đọng.
5. Listener có `@EventListener(condition)` vẫn đánh giá rule theo từng payload.
6. Listener lọc `supportsSourceType(...)` nhận đúng source class và loại class không phù hợp.
7. Khi có generic events, type matching không nhầm generic payload giữa các domain.
8. Nếu có async, test listener đang chạy/đang queue trong tình huống remove/close một cách xác định, không dựa vào `Thread.sleep(...)`.
9. Nếu có prototype bean, xác nhận lifecycle của bean đúng expectation mà không dựa vào cache nội bộ.
10. Khi reload context hoặc dynamic plugin, có test gỡ listener/resource và kiểm tra memory/lifecycle theo phạm vi thực tế.

**Đề xuất quy trình chẩn đoán:**

~~~text
Event không đến listener?
  |
  +-- Publisher có thực sự publish đúng object/type?
  |      |
  |      +-- Không -> sửa publisher
  |      +-- Có
  |
  +-- Listener có được đăng ký trong cùng context?
  |      |
  |      +-- Không -> sửa bean registration
  |      +-- Có
  |
  +-- Event type/source type khớp listener?
  |      |
  |      +-- Không -> sửa declaration / generic / source filter
  |      +-- Có
  |
  +-- @EventListener.condition hoặc transaction phase có chặn?
  |      |
  |      +-- Có -> test rule, transaction, context
  |      +-- Không
  |
  +-- Listener có chạy async?
         |
         +-- Có -> kiểm tra executor, queue, error handler, ordering
         +-- Không -> thu stack trace/profiling, kiểm tra handler
~~~

Đừng chỉnh reflection vào `retrieverCache` chỉ vì thấy listener không chạy. Nếu một vấn đề có thể tái hiện sau khi thêm/gỡ listener bằng API chính thức, tạo **minimal reproducer** theo phiên bản Spring đang dùng và đánh giá cùng test rõ ràng.

## 17. Bài tập tự kiểm tra

**Câu 1.** Spring cache danh sách ứng viên theo từng event instance hay theo loại event/source?

**Đáp án:** Theo thông tin kiểu, trong implementation Spring 6.2 là `ResolvableType` của event và `Class` của source. Hai event cùng type/source class nhưng có giá trị payload khác thường dùng chung key.

**Câu 2.** Khi cache hit, `@EventListener` có còn được gọi cho event mới không?

**Đáp án:** Có, nếu type/source matching và điều kiện thực tế thỏa. Cache chỉ giúp giảm bước tìm ứng viên, không bỏ xử lý những event tiếp theo.

**Câu 3.** Vì sao `condition="#p0.amount() > 1000"` không thể được xem là true vĩnh viễn chỉ vì listener đã nằm trong cache?

**Đáp án:** Vì condition phụ thuộc vào `amount()` của **từng event**. Spring phải đánh giá nó khi event đến method listener; cache lựa chọn theo type không bao gồm giá trị số tiền.

**Câu 4.** Sau khi gọi `multicaster.removeApplicationListener(listener)`, cần dùng reflection xóa `retrieverCache` không?

**Đáp án:** Không. API gỡ listener của multicaster chịu trách nhiệm invalidation theo implementation; truy cập field nội bộ không được khuyến nghị.

**Câu 5.** Một `GenericApplicationListener.supportsSourceType(...)` nhận tham số gì, và có thể phân loại theo `source.customerId` không?

**Đáp án:** Nó nhận **Class của source**, không phải instance. Vì vậy không dùng nó để so sánh dữ liệu `customerId` của từng source object; hãy lọc trong handler hoặc contract event.

**Câu 6.** Hai `TicketEvent` có source value khác nhau nhưng đều thuộc `String`. Chúng có thể dùng cùng cache key không?

**Đáp án:** Có, nếu `ResolvableType` của event cũng giống nhau và điều kiện cache-safe cho phép. Key quan tâm source **class**, không phải nội dung chuỗi.

**Câu 7.** Tại sao dùng feature flag bên trong `supportsEventType(...)` có thể gây kết quả khó đoán sau khi flag đổi?

**Đáp án:** Vì kết quả matching cho key có thể đã được cache, nên predicate không nhất thiết được gọi lại cho mỗi event. Dynamic business logic nên đặt trong method xử lý hoặc một tầng kiểm tra phù hợp.

**Câu 8.** Vì sao số `TYPE_CHECKS_AFTER_TWO` trong ví dụ có thể bằng 1 nhưng số event nhận là 2?

**Đáp án:** Spring có thể tái dùng kết quả matching cho lần thứ hai; cả hai event vẫn được phát đến listener và business handler chạy hai lần.

**Câu 9.** Nếu một listener đã bị gỡ nhưng vẫn in log một lần nữa trong ứng dụng async, điều đó chắc chắn chứng minh cache stale không?

**Đáp án:** Không. Task có thể đã được submit trước lúc gỡ và đang chạy trong executor. Phân tích thời điểm submit, remove và queue.

**Câu 10.** Cache listener có giúp bảo đảm event được ghi bền vững và replay sau khi JVM restart không?

**Đáp án:** Không. Đó là cache lựa chọn listener trong multicaster. Lưu trữ và replay là trách nhiệm của event store/broker/outbox riêng.

## Tài liệu tham khảo

- [Spring Framework 6.2 Javadoc — AbstractApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html): đăng ký/gỡ listener và `getApplicationListeners(...)` theo event type.
- [Spring Framework 6.2 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): dispatch mặc định đồng bộ, executor và `supportsAsyncExecution`.
- [Spring Framework 6.2 Javadoc — GenericApplicationListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/GenericApplicationListener.html): `supportsEventType(ResolvableType)`, `supportsSourceType(...)`.
- [Spring Framework 6.2 Javadoc — ApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html): các API đăng ký/gỡ và multicasting.
- [Spring Framework source — AbstractApplicationEventMulticaster.java](https://github.com/spring-projects/spring-framework/blob/v6.2.9/spring-context/src/main/java/org/springframework/context/event/AbstractApplicationEventMulticaster.java): chi tiết triển khai `ListenerCacheKey`, `CachedListenerRetriever`, invalidation, classloader cache-safety; khi xem source hãy chọn tag chính xác phù hợp với phiên bản đang chạy.
- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `@EventListener`, điều kiện theo payload, generic events và thứ tự listener.
