# SmartInitializingSingleton và thời điểm singleton đã được chuẩn bị

Trong vòng đời bean của Spring, mỗi bean có các callback khởi tạo riêng. Tuy nhiên, đôi khi một thành phần cần đợi các singleton thông thường trong container được khởi tạo xong rồi mới xây dựng registry, kiểm tra tính nhất quán hoặc thực hiện bước chuẩn bị dùng chung.

Spring cung cấp interface `SmartInitializingSingleton` cho thời điểm này. Container gọi `afterSingletonsInstantiated()` sau giai đoạn khởi tạo trước các singleton không lazy. Callback cho biết những singleton thông thường đã được chuẩn bị trong giai đoạn bootstrap; nó không có nghĩa mọi bean trong ứng dụng đều đã được tạo hoặc ứng dụng đã sẵn sàng nhận request.

## 1. SmartInitializingSingleton là gì?

`SmartInitializingSingleton` thuộc package `org.springframework.beans.factory` và có một phương thức:

~~~java
public interface SmartInitializingSingleton {

    void afterSingletonsInstantiated();
}
~~~

Một bean triển khai interface này sẽ nhận callback `afterSingletonsInstantiated()` khi Spring hoàn tất giai đoạn pre-instantiation của các singleton thông thường trong quá trình khởi tạo ApplicationContext.

Có thể dùng callback để:

- Xây dựng registry từ các thành phần singleton đã được đăng ký.
- Kiểm tra cấu hình tổng thể sau khi các singleton eager đã được khởi tạo.
- Kết nối hoặc lập chỉ mục các thành phần cần nhìn thấy nhiều bean đã tồn tại.
- Thực hiện bước chuẩn bị nội bộ phụ thuộc vào trạng thái khởi tạo của các singleton khác.

Callback này được thiết kế cho giai đoạn bootstrap của container. Nó không phải callback chạy sau mỗi request, không phải callback khi một bean bất kỳ được tạo, và cũng không phải callback hủy bean.

## 2. Callback được gọi ở thời điểm nào?

Trong quá trình refresh ApplicationContext, Spring thực hiện nhiều giai đoạn. Phần liên quan đến callback có thể hình dung như sau:

~~~text
ApplicationContext.refresh()
        |
        v
Đăng ký BeanPostProcessor và chuẩn bị hạ tầng context
        |
        v
finishBeanFactoryInitialization()
        |
        v
preInstantiateSingletons()
        |
        +--> Tạo các singleton không lazy
        |    Tiêm dependency và chạy callback khởi tạo
        |
        v
Gọi afterSingletonsInstantiated()
cho các singleton triển khai SmartInitializingSingleton
        |
        v
finishRefresh()
        |
        +--> Khởi tạo LifecycleProcessor
        +--> Khởi động các SmartLifecycle phù hợp
        +--> Phát ContextRefreshedEvent
        |
        v
Spring Boot chạy ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
~~~

Trong mỗi bean, constructor, dependency injection và các callback khởi tạo như `@PostConstruct`, `InitializingBean.afterPropertiesSet()` hoặc `initMethod` đã được xử lý trong lúc bean đó được tạo. Sau đó, khi Spring hoàn tất việc tạo các singleton eager thông thường, nó mới gọi `afterSingletonsInstantiated()` trên những singleton triển khai interface này.

Vì vậy, callback có thể quan sát các singleton eager khác sau khi chúng đã được khởi tạo. Nó chạy trong quá trình refresh, trước `ContextRefreshedEvent`; do đó không nên diễn giải callback này thành tín hiệu rằng ApplicationContext đã hoàn tất toàn bộ quá trình refresh hoặc Spring Boot đã sẵn sàng nhận traffic.

## 3. Ví dụ: xây dựng registry sau khi các handler được khởi tạo

Giả sử ứng dụng có nhiều handler thanh toán. Mỗi handler cung cấp mã nhà cung cấp và được Spring quản lý như một singleton. Registry cần lập chỉ mục các handler theo mã để những service khác tra cứu nhanh.

Định nghĩa hợp đồng:

~~~java
public interface PaymentHandler {

    String providerCode();

    void validateConfiguration();
}
~~~

Các handler có thể được triển khai riêng:

~~~java
import org.springframework.stereotype.Component;

@Component
public class CardPaymentHandler implements PaymentHandler {

    @Override
    public String providerCode() {
        return "card";
    }

    @Override
    public void validateConfiguration() {
        // Kiểm tra cấu hình cục bộ cần thiết cho handler.
    }
}
~~~

Registry triển khai `SmartInitializingSingleton`:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
public class PaymentHandlerRegistry
        implements SmartInitializingSingleton {

    private final List<PaymentHandler> handlers;
    private Map<String, PaymentHandler> handlersByCode = Map.of();

    public PaymentHandlerRegistry(List<PaymentHandler> handlers) {
        this.handlers = handlers;
    }

    @Override
    public void afterSingletonsInstantiated() {
        Map<String, PaymentHandler> discovered = new LinkedHashMap<>();

        for (PaymentHandler handler : handlers) {
            handler.validateConfiguration();

            PaymentHandler previous = discovered.putIfAbsent(
                    handler.providerCode(),
                    handler
            );

            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate payment provider: "
                                + handler.providerCode()
                );
            }
        }

        this.handlersByCode = Map.copyOf(discovered);
    }

    public PaymentHandler getRequired(String providerCode) {
        PaymentHandler handler = handlersByCode.get(providerCode);

        if (handler == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment provider: " + providerCode
            );
        }

        return handler;
    }
}
~~~

Khi Spring tạo `PaymentHandlerRegistry`, dependency dạng `List<PaymentHandler>` được phân giải và các handler cần thiết được tạo. Phương thức constructor chỉ lưu danh sách. Việc kiểm tra và lập chỉ mục được thực hiện trong `afterSingletonsInstantiated()`, khi giai đoạn tạo các singleton eager thông thường đã hoàn tất.

Sau callback, các service có thể gọi `getRequired("card")` để lấy handler tương ứng. Nếu có hai handler cùng khai báo một mã, exception được ném ra trong giai đoạn bootstrap và quá trình refresh context thất bại. Lỗi cấu hình được phát hiện ngay khi khởi động thay vì xuất hiện ở một request sau đó.

Trong ứng dụng thực tế, phương thức `validateConfiguration()` nên kiểm tra trạng thái cấu hình cục bộ hoặc tính nhất quán của bean. Nếu việc kiểm tra cần gọi dịch vụ từ xa, hãy cân nhắc timeout, retry và chính sách startup riêng; callback này chạy đồng bộ trong quá trình khởi tạo context và có thể làm chậm hoặc chặn startup.

## 4. Singleton nào được tính là đã khởi tạo?

Cần hiểu chính xác phạm vi của cụm từ “all singleton beans” trong callback này.

### Singleton eager

Các singleton thông thường không được đánh dấu lazy sẽ được Spring tạo trong giai đoạn pre-instantiation. Khi callback được gọi, những singleton này đã trải qua quá trình khởi tạo của chúng.

Đây là nhóm bean mà `SmartInitializingSingleton` được thiết kế để phối hợp.

### Singleton lazy

Bean có `@Lazy` hoặc được định nghĩa lazy không nhất thiết được tạo trong giai đoạn pre-instantiation. Nếu bean chưa được tạo, không thể giả định rằng callback của một `SmartInitializingSingleton` sẽ nhìn thấy instance đã khởi tạo của bean đó.

Nếu callback cần một bean lazy, việc chủ động truy cập bean có thể làm nó được tạo sớm và làm thay đổi ý nghĩa lazy ban đầu. Chỉ làm vậy khi đây là quyết định thiết kế có chủ đích.

Ngoài ra, bean triển khai `SmartInitializingSingleton` cũng cần được khởi tạo trong giai đoạn pre-instantiation để nhận callback startup thông thường. Nếu chính bean callback bị lazy và chỉ được tạo sau giai đoạn này, đừng giả định container sẽ gọi bù `afterSingletonsInstantiated()` cho nó.

### Prototype và các scope khác

Prototype được tạo mỗi khi container được yêu cầu cung cấp instance. Nó không thuộc nhóm singleton được pre-instantiate, vì vậy không nhận callback `SmartInitializingSingleton` cho từng instance.

Các scope như request hoặc session cũng có vòng đời riêng. Không dùng interface này để xử lý khởi tạo hay hủy cho từng instance thuộc các scope đó.

### Bean được tạo sau giai đoạn bootstrap

Một bean được tạo muộn do lazy lookup hoặc do code yêu cầu sau khi context đã refresh không làm cho callback toàn cục chạy lại. `SmartInitializingSingleton` là mốc của giai đoạn pre-instantiation, không phải một listener theo dõi liên tục mọi bean được tạo trong suốt thời gian ứng dụng chạy.

## 5. So sánh với các callback và sự kiện khác

Các cơ chế khởi tạo của Spring có thời điểm và phạm vi khác nhau:

| Cơ chế | Thời điểm | Phạm vi sử dụng |
|---|---|---|
| Constructor | Khi tạo instance | Khởi tạo trạng thái ban đầu và nhận dependency |
| `@PostConstruct` | Trong quá trình khởi tạo từng bean | Chuẩn bị chính bean đó sau khi dependency được tiêm |
| `InitializingBean.afterPropertiesSet()` | Trong quá trình khởi tạo từng bean | Callback khởi tạo ở cấp bean |
| `@Bean(initMethod = "...")` | Trong quá trình khởi tạo từng bean | Gọi phương thức init được cấu hình |
| `SmartInitializingSingleton` | Sau giai đoạn pre-instantiation của singleton thông thường | Công việc cần đợi các singleton eager được khởi tạo |
| `ContextRefreshedEvent` | Sau khi ApplicationContext hoàn tất refresh | Thành phần cần biết context đã refresh |
| `ApplicationRunner` / `CommandLineRunner` | Trong quá trình khởi động Spring Boot, sau refresh | Công việc startup của ứng dụng |
| `ApplicationReadyEvent` | Sau khi các runner hoàn tất | Thành phần cần biết Spring Boot đã phát tín hiệu sẵn sàng |

### So với @PostConstruct

`@PostConstruct` chạy trong quá trình khởi tạo bean hiện tại. Nó phù hợp để kiểm tra hoặc chuẩn bị trạng thái nội bộ của bean sau khi dependency đã được tiêm.

Nó không có nghĩa mọi singleton khác trong ứng dụng đều đã được khởi tạo. Nếu logic cần trạng thái của các singleton không nằm trong dependency graph trực tiếp, không nên dựa vào thứ tự tình cờ giữa các bean để chạy logic đó trong `@PostConstruct`.

`SmartInitializingSingleton` phù hợp hơn khi bước chuẩn bị cần đợi giai đoạn tạo các singleton eager thông thường kết thúc.

### So với ContextRefreshedEvent

`ContextRefreshedEvent` được phát khi ApplicationContext đã hoàn tất refresh. Nó phù hợp khi thành phần cần phản ứng với sự kiện context đã được nạp xong.

Một ứng dụng có context hierarchy hoặc cơ chế refresh có thể phát sự kiện này ở nhiều context hoặc nhiều lần trong vòng đời tương ứng. Listener cần kiểm tra đúng context và thiết kế sao cho xử lý lặp an toàn khi cần.

`SmartInitializingSingleton` gắn với giai đoạn pre-instantiation của bean factory, trước sự kiện refresh hoàn tất.

### So với ApplicationRunner và ApplicationReadyEvent

Trong Spring Boot, `ApplicationRunner` và `CommandLineRunner` phù hợp cho công việc khởi động ứng dụng cần nhận tham số hoặc chạy sau khi context đã refresh, chẳng hạn nạp dữ liệu ban đầu hoặc kiểm tra điều kiện startup ở cấp ứng dụng.

`ApplicationReadyEvent` được phát sau khi các runner hoàn tất và Spring Boot phát tín hiệu ứng dụng đã sẵn sàng. Nếu cần khởi chạy một công việc gắn với trạng thái sẵn sàng của ứng dụng, hãy xem xét sự kiện này.

Không dùng `SmartInitializingSingleton` như một cách thay thế cho tín hiệu readiness. Callback chỉ cho biết giai đoạn tạo singleton eager đã kết thúc; nó không chứng minh rằng kết nối tới mọi hệ thống bên ngoài đều hoạt động hoặc ứng dụng đã qua toàn bộ startup workflow.

## 6. Những giới hạn cần lưu ý

### Không dựa vào thứ tự giữa nhiều callback

Một ứng dụng có thể có nhiều bean cùng triển khai `SmartInitializingSingleton`. Không nên thiết kế callback A phụ thuộc vào việc callback B chắc chắn đã chạy trước nếu không có cơ chế điều phối rõ ràng.

Nếu các bước cần thứ tự, hãy gom chúng vào một coordinator duy nhất hoặc biểu diễn quan hệ phụ thuộc bằng một cơ chế orchestration rõ ràng. Đừng dựa vào thứ tự tạo bean hoặc tên bean như một hợp đồng thứ tự thực thi.

### Callback chạy đồng bộ trong lúc refresh

`afterSingletonsInstantiated()` là phương thức đồng bộ. Nếu callback thực hiện công việc chậm, nó kéo dài thời gian khởi động context. Nếu callback ném exception không được xử lý, quá trình refresh có thể thất bại.

Hãy giữ callback tập trung vào việc chuẩn bị cấu trúc nội bộ, xác thực và lập chỉ mục cần thiết. Với tác vụ nền dài, có thể dùng cơ chế chạy tác vụ phù hợp sau khi ứng dụng sẵn sàng.

### Không phải callback hủy

Interface này chỉ cung cấp callback sau khi các singleton được khởi tạo. Nó không có phương thức `destroy()` hoặc `stop()`. Nếu bean cần giải phóng tài nguyên khi context đóng, hãy dùng cơ chế vòng đời hủy phù hợp như `@PreDestroy`, `DisposableBean` hoặc `@Bean(destroyMethod = "...")` cho bean có scope được container quản lý hủy.

Nếu bean là prototype, cần nhớ rằng Spring không tự động gọi callback hủy của prototype. Code sở hữu instance vẫn phải đóng tài nguyên của instance đó.

## 7. Khi nào nên chọn SmartInitializingSingleton?

Hãy cân nhắc interface này khi đồng thời có các đặc điểm:

1. Công việc thuộc giai đoạn khởi tạo container.
2. Công việc cần đợi các singleton eager thông thường được tạo và khởi tạo xong.
3. Kết quả là trạng thái nội bộ hoặc kiểm tra nhất quán phục vụ các thành phần khác.
4. Công việc có thể hoàn tất đồng bộ trong thời gian startup hợp lý.
5. Bean triển khai callback được tạo trong giai đoạn pre-instantiation.

Nếu chỉ cần khởi tạo trạng thái riêng của một bean, dùng constructor hoặc callback init của bean đó. Nếu cần chạy công việc startup cấp ứng dụng sau khi context refresh, xem xét `ApplicationRunner` hoặc `CommandLineRunner`. Nếu cần phản ứng khi context đã refresh hoặc ứng dụng đã sẵn sàng, dùng event tương ứng.

`SmartInitializingSingleton` đánh dấu một mốc cụ thể trong vòng đời container: các singleton eager thông thường đã được khởi tạo và container đang hoàn tất giai đoạn pre-instantiation. Hiểu đúng mốc này giúp đặt logic registry, validation và chuẩn bị dùng chung vào thời điểm phù hợp, đồng thời tránh nhầm nó với việc mọi bean lazy, mọi scope hay toàn bộ ứng dụng đã sẵn sàng.

