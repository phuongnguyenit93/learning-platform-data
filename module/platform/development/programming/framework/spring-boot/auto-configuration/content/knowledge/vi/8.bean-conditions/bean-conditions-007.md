# SearchStrategy.CURRENT, ANCESTORS và ALL trong cây ApplicationContext

## 1. Vì sao cần SearchStrategy?

Spring có thể chạy nhiều `ApplicationContext` theo quan hệ **cha – con**. Mỗi context giữ những bean definition của chính nó. Khi tra cứu bean, context con có thể nhìn thấy bean từ cha theo quy tắc của Spring, nhưng cha không tự nhìn thấy bean chỉ được khai báo trong con.

Khi Spring Boot đánh giá điều kiện kiểu “có bean `X` hay không?”, câu hỏi quan trọng là: **tìm bean trong context hiện tại hay cả các context cha?** Enum `org.springframework.boot.autoconfigure.condition.SearchStrategy` cho phép chọn vùng tìm kiếm bằng thuộc tính `search` của bean condition.

Sau bài này, bạn có thể đọc cây context, dự đoán các điều kiện `@ConditionalOnBean` / `@ConditionalOnMissingBean` và chọn phạm vi đúng khi viết auto-configuration.

## 2. Ba giá trị: CURRENT, ANCESTORS và ALL

Xét chuỗi context sau, với điều kiện đang được đánh giá **ở WebContext**:

```text
RootContext
    |
    v
ServiceContext
    |
    v
WebContext  <-- context hiện tại
```

| Chiến lược | Nơi được tìm | Nơi không được tìm |
|---|---|---|
| `SearchStrategy.CURRENT` | Chỉ `WebContext` | `ServiceContext`, `RootContext` |
| `SearchStrategy.ANCESTORS` | `ServiceContext` và `RootContext` | `WebContext` |
| `SearchStrategy.ALL` | `WebContext` và toàn bộ tổ tiên | Không loại trừ context nào trên nhánh đi lên |

**`ANCESTORS` bao gồm mọi tổ tiên, không chỉ cha trực tiếp**, và luôn loại trừ context đang xét. **`ALL` bao gồm hiện tại và mọi tổ tiên**, không có nghĩa là tìm sang context anh em hoặc các context con khác. Nếu chỉ có một context gốc, `ANCESTORS` không có nơi nào để tìm; `CURRENT` và `ALL` xét cùng một context.

Quan hệ cha – con giữa các `ApplicationContext` là điểm quyết định. Hai package Java, hai lớp `@Configuration`, hay hai bean scope `singleton`/`prototype` không tự tạo thành hai context.

## 3. SearchStrategy được dùng ở đâu?

Ba bean condition quan trọng của Spring Boot 3.3 đều hỗ trợ thuộc tính `search` và mặc định là **`SearchStrategy.ALL`**:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.boot.autoconfigure.condition.SearchStrategy;

// Các đoạn annotation minh họa, đặt trên @Bean hoặc cấu hình thích hợp:
// @ConditionalOnBean(value = Client.class, search = SearchStrategy.ALL)
// @ConditionalOnMissingBean(value = Client.class, search = SearchStrategy.CURRENT)
// @ConditionalOnSingleCandidate(value = Client.class, search = SearchStrategy.ANCESTORS)
```

Trong ba dòng ví dụ cuối, `Client` là kiểu giả định của ứng dụng:

- `@ConditionalOnBean` khớp khi tồn tại bean thỏa các yêu cầu đã khai báo ở phạm vi đang xét. Có nhiều yêu cầu thì tất cả phải được đáp ứng; không nhất thiết cùng một bean đáp ứng mọi yêu cầu.
- `@ConditionalOnMissingBean` khớp khi **không có** bean thỏa các yêu cầu trong phạm vi đang xét. Nó thường được dùng để cung cấp bean mặc định khi người dùng chưa khai báo bean tương ứng.
- `@ConditionalOnSingleCandidate` đòi hỏi một ứng viên phù hợp xác định được cho kiểu bean; nhiều bean cùng kiểu vẫn có thể đạt nếu chọn được một ứng viên `@Primary`.

`search` chỉ quyết định **phạm vi đánh giá điều kiện**. Nó không tạo parent context, không tự đăng ký bean, không đổi phạm vi component scan và không thay thế `@Qualifier` hoặc cơ chế inject.

## 4. Bảng quyết định theo nơi bean tồn tại

Giả sử đang đánh giá điều kiện tại **Child**, tìm bean kiểu `Marker`. Bean trong ví dụ đủ tư cách ứng viên, có tên khác nhau và đã được Spring xử lý trước khi điều kiện chạy.

### `@ConditionalOnBean(Marker.class)`

| Vị trí của `Marker` | CURRENT | ANCESTORS | ALL |
|---|---|---|---|
| Chỉ ở Parent | Không khớp | Khớp | Khớp |
| Chỉ ở Child | Khớp | Không khớp | Khớp |
| Cả Parent và Child | Khớp | Khớp | Khớp |
| Không nơi nào có | Không khớp | Không khớp | Không khớp |

### `@ConditionalOnMissingBean(Marker.class)`

Với đúng một yêu cầu theo kiểu như trên, kết quả là nghịch đảo:

| Vị trí của `Marker` | CURRENT | ANCESTORS | ALL |
|---|---|---|---|
| Chỉ ở Parent | Khớp | Không khớp | Không khớp |
| Chỉ ở Child | Không khớp | Khớp | Không khớp |
| Cả Parent và Child | Không khớp | Không khớp | Không khớp |
| Không nơi nào có | Khớp | Khớp | Khớp |

Hệ quả thường gặp: Child không có `Marker` nhưng Parent có. `@ConditionalOnMissingBean(Marker.class)` dùng mặc định `ALL` nên **không tạo bean dự phòng** ở Child. Đổi sang `search = CURRENT` khiến điều kiện **có thể khớp**, vì lúc đó chỉ kiểm tra Child.

Bảng này là mô hình cơ bản theo kiểu bean. Bean trùng tên giữa cha và con có thể bị che khuất trong tra cứu; ứng viên đặc biệt cũng có thể làm kết quả khác phép đếm cơ học mọi bean definition. Khi có các trường hợp đó, hãy đọc báo cáo điều kiện thực tế.

## 5. Ví dụ Java 17+: Parent có Marker, Child không có

Ví dụ sau có hàm `main` độc lập. Đặt file `SearchStrategyDemo.java` vào một dự án có Spring Framework 6.x và Spring Boot 3.3.x (bao gồm `spring-context`, `spring-boot-autoconfigure`), rồi chạy `SearchStrategyDemo.main` từ IDE với classpath của dự án. Không cần khởi động web server.

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.SearchStrategy;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SearchStrategyDemo {

    public static class Marker {}

    @Configuration(proxyBeanMethods = false)
    public static class ParentConfiguration {
        @Bean
        public Marker parentMarker() {
            return new Marker();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ChildConfiguration {
        @Bean("checkCurrent")
        @ConditionalOnBean(value = Marker.class, search = SearchStrategy.CURRENT)
        public String checkCurrent() {
            return "found current";
        }

        @Bean("checkAncestors")
        @ConditionalOnBean(value = Marker.class, search = SearchStrategy.ANCESTORS)
        public String checkAncestors() {
            return "found ancestors";
        }

        @Bean("checkAll")
        @ConditionalOnBean(value = Marker.class, search = SearchStrategy.ALL)
        public String checkAll() {
            return "found all";
        }

        @Bean("missingCurrent")
        @ConditionalOnMissingBean(
                value = Marker.class, search = SearchStrategy.CURRENT)
        public String missingCurrent() {
            return "missing current";
        }

        @Bean("missingAll")
        @ConditionalOnMissingBean(
                value = Marker.class, search = SearchStrategy.ALL)
        public String missingAll() {
            return "missing all";
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext parent =
                     new AnnotationConfigApplicationContext(
                             ParentConfiguration.class)) {
            try (AnnotationConfigApplicationContext child =
                         new AnnotationConfigApplicationContext()) {
                child.setParent(parent);
                child.register(ChildConfiguration.class);
                child.refresh();

                System.out.println("OnBean CURRENT   : "
                        + child.containsLocalBean("checkCurrent"));
                System.out.println("OnBean ANCESTORS : "
                        + child.containsLocalBean("checkAncestors"));
                System.out.println("OnBean ALL       : "
                        + child.containsLocalBean("checkAll"));
                System.out.println("Missing CURRENT  : "
                        + child.containsLocalBean("missingCurrent"));
                System.out.println("Missing ALL      : "
                        + child.containsLocalBean("missingAll"));
            }
        }
    }
}
```

Kết quả `System.out` kỳ vọng (các dòng log do thư viện ghi thêm, nếu có, không thuộc output sau):

```text
OnBean CURRENT   : false
OnBean ANCESTORS : true
OnBean ALL       : true
Missing CURRENT  : true
Missing ALL      : false
```

Cách suy luận:

1. Parent được tạo và refresh trước, nên bean `parentMarker` kiểu `Marker` đã hiện diện.
2. Child được gắn với Parent bằng `setParent(parent)` trước khi `register` cấu hình và `refresh`.
3. Child không định nghĩa `Marker`. Do đó `@ConditionalOnBean(search = CURRENT)` không khớp, trong khi `ANCESTORS` và `ALL` tìm được `parentMarker`.
4. Với `@ConditionalOnMissingBean`, `CURRENT` khớp vì Child thiếu `Marker`, còn `ALL` không khớp vì Parent đã có.
5. `containsLocalBean(...)` kiểm tra bean **được đăng ký tại Child**, giúp quan sát đúng kết quả. `containsBean(...)` có thể tra cứu tiếp ở parent và không phù hợp bằng cho phép kiểm tra cục bộ này.

Trong mã trên các phương thức có điều kiện trả về `String` để dễ in kết quả; một ứng dụng thực tế có thể trả về service, client hay adapter. Ví dụ chủ động dùng `@Configuration` vì mọi bean ở Parent đã được xử lý trước khi Child đánh giá điều kiện; trong production, các điều kiện bean thường đặt trong auto-configuration để kiểm soát thứ tự.

## 6. Tình huống chọn chiến lược

### CURRENT: cho phép bean riêng ở mỗi context

```java
@Bean
@ConditionalOnMissingBean(
        value = RequestHandler.class,
        search = SearchStrategy.CURRENT)
RequestHandler localHandler() {
    return new DefaultRequestHandler();
}
```

Đoạn mã minh họa với hai kiểu do ứng dụng định nghĩa `RequestHandler` và `DefaultRequestHandler`. Child có thể tự tạo handler ngay cả khi Parent có một handler cùng kiểu. Dùng khi mỗi context được thiết kế để có cấu hình riêng, đồng thời chấp nhận khả năng tồn tại bean cùng kiểu ở nhiều tầng.

### ANCESTORS: chỉ khớp nếu cha cung cấp dịch vụ

```java
@Bean
@ConditionalOnBean(
        value = SharedRegistry.class,
        search = SearchStrategy.ANCESTORS)
RegistryBridge registryBridge(SharedRegistry registry) {
    return new RegistryBridge(registry);
}
```

Đoạn mã minh họa với kiểu `SharedRegistry` / `RegistryBridge` tự định nghĩa. Bean chỉ có ở Child không đủ; điều kiện yêu cầu `SharedRegistry` tại một tổ tiên. Lưu ý, **điều kiện khớp không bảo đảm tham số `registry` chắc chắn được inject từ Parent** nếu Child cũng có ứng viên cùng kiểu. Cần xét riêng quy tắc chọn bean khi inject.

### ALL: nhường quyền cho bean có sẵn trong cây context

```java
@Bean
@ConditionalOnMissingBean(
        value = MetricsReporter.class,
        search = SearchStrategy.ALL)
MetricsReporter metricsReporter() {
    return new DefaultMetricsReporter();
}
```

Đoạn mã minh họa với hai kiểu ứng dụng tự định nghĩa. Auto-configuration chỉ cung cấp `MetricsReporter` mặc định khi cả Child lẫn các context tổ tiên đều chưa có bean tương ứng. Đây là lựa chọn thường gặp để tránh tạo một bean mặc định trùng vai trò với bean dùng chung từ Parent.

## 7. Những giới hạn quan trọng

**Thứ tự xử lý bean definition:** `@ConditionalOnBean` và `@ConditionalOnMissingBean` chỉ đánh giá các định nghĩa bean mà context đã xử lý **đến thời điểm kiểm tra**. Một bean xuất hiện về sau có thể làm trực giác “cuối cùng có bean X” bị sai. Spring Boot khuyến nghị dùng các điều kiện này trong auto-configuration, vì các bean do người dùng khai báo thường được xử lý trước. Khi phụ thuộc vào bean do auto-configuration khác tạo, hãy dùng cơ chế sắp thứ tự như `@AutoConfiguration(after = ...)`.

**Single candidate khác bean exists:** `@ConditionalOnSingleCandidate(value = TaskExecutor.class, search = ALL)` cần chọn được một ứng viên phù hợp. Có hai `TaskExecutor` mà không chọn được ứng viên duy nhất thì `@ConditionalOnBean(TaskExecutor.class)` có thể khớp nhưng `@ConditionalOnSingleCandidate` không. Một ứng viên `@Primary` phù hợp có thể giúp điều kiện single-candidate khớp. `search` quyết định các context được đưa vào phép xem xét ứng viên.

**Tìm theo kiểu và tìm theo tên:** `@ConditionalOnBean(value = Client.class)` kiểm tra theo kiểu, còn `@ConditionalOnBean(name = "client")` kiểm tra theo tên. Trong hệ thống parent–child, tên bean trùng nhau và quy tắc shadowing có thể ảnh hưởng kết quả tra cứu. Không nên suy luận chỉ từ tổng số bean kiểu đó nhìn thấy trong debugger.

**Không phải mọi bean đều là ứng viên hợp lệ:** Điều kiện bean có thể bỏ qua bean không đủ điều kiện autowiring hoặc các ứng viên bị loại theo quy tắc của phiên bản Spring Boot đang dùng. Nếu kết quả khác bảng đơn giản ở trên, cần xem cả type, name, candidate flags và thời điểm xử lý.

**Bean lookup không tương đương điều kiện:** `child.getBean(Service.class)` có thể tìm đến bean ở Parent, nhưng `@ConditionalOnBean(value = Service.class, search = CURRENT)` vẫn không khớp khi Child không có bean phù hợp cục bộ. Ngoài ra, `@Primary`, `@Qualifier` và generic type có thể ảnh hưởng chuyện inject; `search` không tự điều khiển tất cả các quy tắc đó.

**Không dùng ANCESTORS theo quán tính:** Nhiều ứng dụng Spring Boot thông thường có một context duy nhất. `ANCESTORS` chỉ hữu ích khi có parent context thực sự. Một `@Configuration` lồng trong một lớp khác vẫn có thể thuộc cùng một context.

## 8. Gỡ lỗi theo trình tự

1. Xác định chính xác **context đánh giá điều kiện**, rồi xem chuỗi `applicationContext.getParent()` để biết có những ancestor nào.
2. Xác định yêu cầu theo **type** hay **name** và xem bean được đăng ký ở tầng nào. Kiểm tra cả trường hợp bean cha và con trùng tên.
3. Đọc thuộc tính `search`; nếu bị bỏ qua thì mặc định là `ALL`.
4. Dùng **Condition Evaluation Report**: chạy ứng dụng Spring Boot với `--debug` để xem positive/negative condition matches. Nếu đã dùng Actuator và endpoint tương ứng được bật, có thể quan sát `/actuator/conditions`.
5. Khi điều kiện phụ thuộc auto-configuration khác, kiểm tra **thứ tự đăng ký định nghĩa bean**, không chỉ kiểm tra danh sách bean sau khi ứng dụng chạy xong.
6. Khi tự kiểm thử, phân biệt `containsLocalBean` với các thao tác có thể tìm qua parent. Đọc loại bean, tên bean và các tiêu chí ứng viên trước khi kết luận lỗi nằm ở `SearchStrategy`.

## 9. Bài tập tự kiểm tra

**Câu 1.** Child không có `CacheClient`; Parent có. `@ConditionalOnMissingBean(value = CacheClient.class, search = CURRENT)` khớp không?

**Đáp án:** Có. CURRENT chỉ xem Child, nên điều kiện “thiếu bean” khớp.

**Câu 2.** Child có `CacheClient`; Parent không có. `@ConditionalOnBean(value = CacheClient.class, search = ANCESTORS)` khớp không?

**Đáp án:** Không. ANCESTORS loại bỏ Child khỏi phạm vi tìm kiếm.

**Câu 3.** Root có `CacheClient`; Middle và Leaf không có. Ở Leaf, `@ConditionalOnBean(value = CacheClient.class, search = ANCESTORS)` khớp không?

**Đáp án:** Có. Root cũng là một ancestor của Leaf, dù không phải cha trực tiếp.

**Câu 4.** Không có `CacheClient` ở cả Child và Parent. `@ConditionalOnMissingBean(CacheClient.class)` khớp không?

**Đáp án:** Có. Mặc định ALL không tìm được bean nào trên nhánh cha–con.

## 10. Ghi nhớ

- **CURRENT:** chỉ context hiện tại.
- **ANCESTORS:** toàn bộ các context cha, không gồm hiện tại.
- **ALL:** hiện tại và toàn bộ các context cha; cũng là giá trị `search` mặc định cho ba bean condition đã học.

Hãy chọn `search` từ yêu cầu kiến trúc: bean phải riêng tại Child, bắt buộc đến từ Parent hay được phép dùng chung trong cây context. Với `@ConditionalOnMissingBean`, nhớ rằng mặc định `ALL` có thể làm Child **không tạo bean mới** khi Parent đã có bean cùng kiểu.

### Tài liệu chính thức

- [Spring Boot SearchStrategy API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html)
- [Spring Boot 3.3 ConditionalOnBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html)
- [Spring Boot 3.3 ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.3 ConditionalOnSingleCandidate API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
