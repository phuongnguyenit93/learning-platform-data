# Cache danh sách listener trong Spring Event Multicaster

Khi một ứng dụng Spring công bố nhiều event cùng loại, việc tìm lại toàn bộ listener và kiểm tra từng listener ở mỗi lần công bố là công việc lặp lại. Spring có cơ chế **cache danh sách listener phù hợp** ngay trong event multicaster. Bài này giải thích cache được tạo ở đâu, khóa tra cứu gồm những gì, khi nào cache được sử dụng hoặc làm mới, và điều gì **không** được cache.

## 1. Cache nằm ở đâu trong luồng phát event?

Luồng thường gặp trong một `ApplicationContext`:

~~~text
ApplicationEventPublisher.publishEvent(event)
    -> ApplicationContext chuyển event tới ApplicationEventMulticaster
        -> chọn các ApplicationListener phù hợp với event
            -> gọi từng listener
~~~

`ApplicationEventMulticaster` là giao diện điều phối. Trong Spring Framework, `SimpleApplicationEventMulticaster` kế thừa `AbstractApplicationEventMulticaster`. Lớp trừu tượng quản lý đăng ký, lọc và cache listener; lớp `SimpleApplicationEventMulticaster` phụ trách phát event tới các listener đã chọn. Theo mặc định, listener được gọi đồng bộ trên luồng phát event; việc cấu hình executor là chuyện riêng, không phải chức năng của cache.

**Cần phân biệt ba thứ:**

- **Registry**: tập listener đã đăng ký với multicaster, gồm các instance và tên bean.
- **Listener cache**: kết quả lọc từ registry cho một tổ hợp kiểu event và kiểu nguồn phát. Cache giúp tránh lặp lại bước lựa chọn khi có event tương tự.
- **Thực thi listener**: phương thức xử lý vẫn chạy cho **mỗi event** được phát. Spring không lưu kết quả thực thi hoặc bỏ qua event chỉ vì cache hit.

Ví dụ: có 200 listener đăng ký, nhưng chỉ 5 listener quan tâm `OrderCreatedEvent`. Lần tra cứu đầu cần xác định 5 listener này; những lần sau có cùng khóa cache có thể dùng lại tập phù hợp. **Con số 200/5 chỉ là minh họa**, không phải hằng số của Spring.

## 2. Khóa cache: kiểu event và kiểu source

Trong triển khai `AbstractApplicationEventMulticaster`, phần cốt lõi có thể diễn đạt như sau:

~~~text
cacheKey = (
    eventType  : ResolvableType,
    sourceType : Class<?> lấy từ event.getSource() hoặc null
)

cachedListeners = retrieverCache.get(cacheKey)
~~~

- **`eventType`** dùng `ResolvableType`, vì thế có thể biểu đạt thông tin generic chứ không chỉ tên class. Chẳng hạn, với `PayloadApplicationEvent<T>`, kiểu payload có thể ảnh hưởng đến listener phù hợp.
- **`sourceType`** là kiểu runtime của đối tượng `event.getSource()`. Đây là **class của source**, không phải danh tính object source, ID giao dịch hay nội dung payload.
- Hai event có cùng `eventType` nhưng source thuộc hai class khác nhau có thể có **hai khóa cache khác nhau**. Điều này cần thiết vì `GenericApplicationListener` hoặc `SmartApplicationListener` có thể lọc theo source type.

Ví dụ về khóa (giản lược):

| Event type | Source type | Cache key |
| --- | --- | --- |
| `OrderCreatedEvent` | `CheckoutService.class` | `(OrderCreatedEvent, CheckoutService)` |
| `OrderCreatedEvent` | `CheckoutService.class` (source object khác) | **Cùng khóa** với dòng trên |
| `OrderCreatedEvent` | `AdminService.class` | **Khóa khác** |
| `OrderCancelledEvent` | `CheckoutService.class` | **Khóa khác** |

Cache thuộc **một multicaster instance**, không phải bộ nhớ dùng chung toàn ứng dụng hay cache phân tán. Hai `ApplicationContext` riêng có thể sở hữu các multicaster và registry khác nhau.

## 3. Cache miss, cache hit và bước lọc

Diễn tiến rút gọn của `getApplicationListeners(event, eventType)`:

1. Tạo `ListenerCacheKey` từ kiểu event và kiểu source.
2. Tìm `CachedListenerRetriever` tương ứng trong `retrieverCache` (triển khai dùng cấu trúc concurrent để hỗ trợ truy cập đồng thời).
3. **Cache hit và entry đã sẵn sàng**: lấy danh sách listener từ retriever; không cần lọc lại toàn bộ registry theo event/source type.
4. **Cache miss**: xét điều kiện có thể cache; nếu phù hợp, tạo retriever mới, lọc listener rồi lưu kết quả. Nếu không phù hợp, vẫn lọc và phát event bình thường nhưng không giữ entry cache.
5. Trả về danh sách phù hợp cho multicaster thực thi.

Việc lọc xét các cơ chế Spring hỗ trợ, chẳng hạn:

- `ApplicationListener<E>`: khai báo kiểu event quan tâm bằng generic.
- `GenericApplicationListener` và `SmartApplicationListener`: có thể quyết định dựa trên `supportsEventType(...)` và `supportsSourceType(...)`.
- Listener được đăng ký bằng **bean name**: Spring có thể kiểm tra trước kiểu bean để loại bớt ứng viên rồi mới lấy instance khi cần. Cache có thể giữ **tên bean** cùng với listener instance phù hợp, vì không phải mọi bean đều phải được đóng đinh thành một instance duy nhất.
- Các phương thức `@EventListener` được Spring thích nghi thành listener; việc chọn ứng viên cũng đi qua hạ tầng multicaster.

Đây là **cache của kết quả lọc theo kiểu**. Nếu một `@EventListener(condition = "...")` có điều kiện phụ thuộc nội dung event, điều kiện xử lý vẫn cần được đánh giá khi event chạy. Không được suy luận rằng cache hit đồng nghĩa điều kiện lần trước tự động đúng cho mọi payload về sau.

## 4. Ví dụ Java chạy được: cache và cập nhật listener

Ví dụ sau dùng **Java 17+** và `spring-context`. Ta phát hai event cùng kiểu/source, thêm một listener mới, rồi phát tiếp. Việc thêm listener phải khiến multicaster nhận ra tập listener đã thay đổi.

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'demo.ListenerCacheDemo'
}
~~~

Tạo `src/main/java/demo/ListenerCacheDemo.java`:

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

public final class ListenerCacheDemo {

    static final class OrderCreatedEvent extends ApplicationEvent {
        private final int orderId;

        OrderCreatedEvent(Object source, int orderId) {
            super(source);
            this.orderId = orderId;
        }

        int orderId() {
            return orderId;
        }
    }

    static final class OrderListener implements ApplicationListener<OrderCreatedEvent> {
        private final String name;

        OrderListener(String name) {
            this.name = name;
        }

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println(name + " -> order " + event.orderId());
        }
    }

    public static void main(String[] args) {
        var multicaster = new SimpleApplicationEventMulticaster();
        multicaster.addApplicationListener(new OrderListener("A"));

        Object source = new Object();
        multicaster.multicastEvent(new OrderCreatedEvent(source, 1));
        multicaster.multicastEvent(new OrderCreatedEvent(source, 2));

        // Thay đổi registry: Spring phải loại cache listener cũ.
        multicaster.addApplicationListener(new OrderListener("B"));
        multicaster.multicastEvent(new OrderCreatedEvent(source, 3));
    }
}
~~~

Chạy trong dự án Gradle với Java 17+ (nếu đã có Gradle Wrapper thì dùng `./gradlew run --quiet`; trên Windows dùng `gradlew.bat run --quiet`):

~~~text
A -> order 1
A -> order 2
A -> order 3
B -> order 3
~~~

**Giải thích từng lần phát:**

| Thời điểm | Registry | Kết quả mong đợi |
| --- | --- | --- |
| Phát đơn 1 | A | A nhận event; multicaster có thể xây cache cho khóa tương ứng |
| Phát đơn 2 | A | A vẫn được gọi; cache đủ điều kiện có thể được tái sử dụng |
| Đăng ký B | A, B | Cache đã có bị invalidated/clear do thay đổi registry |
| Phát đơn 3 | A, B | Cả A và B nhận event theo registry hiện tại |

Kết quả stdout **chứng minh listener mới được nhận**; chỉ riêng stdout **không chứng minh số lần cache hit**. Muốn xác nhận hit/miss cụ thể, cần quan sát triển khai Spring bằng debugger/profiler hoặc phép đo chuyên biệt. Không có API công khai chuẩn kiểu `getListenerCacheHitCount()` của multicaster.

**Vì sao dùng class `OrderListener` cụ thể?** Kiểu `ApplicationListener<OrderCreatedEvent>` được thể hiện rõ cho cơ chế kiểm tra generic. Ví dụ không dựa vào việc Spring phải suy diễn kiểu event từ lambda bị xóa generic tại runtime.

## 5. Khi nào cache được làm mới hoặc không được dùng?

Các phương thức đăng ký/hủy đăng ký trên `AbstractApplicationEventMulticaster`, ví dụ `addApplicationListener(...)`, `addApplicationListenerBean(...)`, `removeApplicationListener(...)` và `removeAllListeners()`, làm thay đổi registry và khiến kết quả lọc cũ không còn đáng tin cậy. Triển khai Spring xóa `retrieverCache` khi thực hiện những thay đổi này; lần phát kế tiếp sẽ tính lại theo registry hiện có.

Điều này khác với việc thay đổi **trạng thái bên trong** một listener. Ví dụ, listener đã đăng ký nhưng tự kiểm tra một cờ `enabled` khi xử lý event: thay đổi cờ đó không nhất thiết thay đổi registry và không phải lý do để tự động xây lại listener cache. Cờ cần được kiểm tra trong hàm xử lý ở mỗi lần gọi.

Một số trường hợp cần lưu ý:

- **Giới hạn class loader**: Spring kiểm tra độ an toàn khi cache kiểu event/source so với bean class loader (qua `ClassUtils.isCacheSafe(...)`). Nếu không an toàn, Spring vẫn chọn listener để dispatch nhưng có thể không cache entry đó, nhằm tránh giữ tham chiếu class loader không phù hợp.
- **Truy cập đồng thời**: một thread có thể nhìn thấy entry cache đang được thread khác xây dựng. Triển khai xử lý trường hợp entry chưa sẵn sàng bằng cách tự lấy danh sách phù hợp cho lần xử lý hiện tại; không mặc nhiên trả về danh sách rỗng.
- **Nhiều kiểu event/source**: mỗi tổ hợp khác nhau có thể tạo entry riêng. Số entry phụ thuộc kiểu sử dụng, vì vậy không nên giả định chỉ có một danh sách cache cho cả ứng dụng.
- **Bean scope**: cache chọn bean name không đồng nghĩa mọi lần dispatch đều dùng đúng một object bean ở mọi scope. Vòng đời bean vẫn do BeanFactory quản lý.

Các mô tả về `retrieverCache`, `ListenerCacheKey` và `CachedListenerRetriever` là **chi tiết triển khai**, hữu ích để hiểu và debug; không nên viết mã ứng dụng phụ thuộc vào cấu trúc private hoặc tên field nội bộ.

## 6. Cache listener không giải quyết vấn đề nào?

| Điều thường bị hiểu sai | Cách hiểu đúng |
| --- | --- |
| “Event đầu đã chạy nên event cùng loại tiếp theo bị bỏ qua.” | Mỗi event vẫn được chuyển tới các listener phù hợp. |
| “Cache chứa kết quả `onApplicationEvent`.” | Cache chứa lựa chọn listener; logic xử lý và hiệu ứng phụ vẫn chạy mỗi lần. |
| “Cache hit bỏ qua điều kiện dựa trên payload.” | Điều kiện/phép kiểm tra nghiệp vụ động vẫn phải đánh giá theo từng event. |
| “Đổi source object chắc chắn tạo khóa mới.” | Chỉ **kiểu source** tham gia khóa; hai object cùng class thường dùng cùng khóa. |
| “Cần tự gọi cache.clear() mỗi khi thêm listener.” | Sử dụng API đăng ký/hủy đăng ký của multicaster; Spring xử lý invalidation. |
| “Cache listener làm xử lý event tự động bất đồng bộ.” | Đồng bộ/bất đồng bộ là cấu hình dispatch/executor và khả năng thực thi của listener. |

Đặc biệt, đừng nhầm cache này với **Spring Cache Abstraction** (`@Cacheable`, `CacheManager`): Spring Cache Abstraction cache kết quả phương thức theo key dữ liệu; listener cache là tối ưu nội bộ của bước xác định đối tượng nhận event.

## 7. Cách áp dụng và kiểm tra trong ứng dụng thực tế

1. **Ưu tiên khai báo listener rõ kiểu**, ví dụ `ApplicationListener<OrderCreatedEvent>` hoặc `@EventListener` cho kiểu event cụ thể. Tránh đăng ký quá rộng rồi tự `instanceof` cho mọi event khi không cần.
2. **Đăng ký listener qua Spring/Multicaster API**. Nếu ứng dụng thực sự thêm/bớt listener lúc chạy, dùng `addApplicationListener` hoặc API remove tương ứng. Không chỉnh sửa trực tiếp cấu trúc cache nội bộ bằng reflection.
3. **Giữ điều kiện nghiệp vụ ở nơi xử lý**. Trạng thái đơn hàng, người dùng, cờ tính năng, dữ liệu payload có thể thay đổi giữa các event dù cache key giống nhau.
4. **Đánh giá hiệu năng đúng chỗ**. Cache giảm công đoạn chọn ứng viên; thời gian xử lý có thể vẫn chủ yếu nằm ở I/O, database, network hoặc listener chặn luồng. Đo latency và profiling thực tế trước khi tối ưu.
5. **Kiểm tra khi registry thay đổi**. Test tối thiểu nên phát event khi chỉ có A, thêm B, phát lại và xác nhận A/B đều nhận; kiểm tra remove nếu ứng dụng có dùng chức năng đó. Không viết test phụ thuộc vào field private của Spring.

**Ghi nhớ:** Với cùng `ResolvableType` và class của source, Spring có thể tái sử dụng kết quả tìm listener. Khi registry thay đổi, cache được làm mới; event và logic listener vẫn được xử lý bình thường ở mỗi lượt phát.

### Tài liệu tham khảo

- [AbstractApplicationEventMulticaster — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html)
- [SimpleApplicationEventMulticaster — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Mã nguồn AbstractApplicationEventMulticaster (Spring Framework)](https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/context/event/AbstractApplicationEventMulticaster.java)