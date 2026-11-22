# Thứ tự tập hợp bean với `Ordered`, `@Order` và `@Priority` trong Spring

## 1. Bài toán: nhiều bean cùng kiểu nhưng cần chạy đúng thứ tự

Trong Spring Core Container, một interface có thể có nhiều bean implementation. Khi tiêm `List<T>` hoặc `T[]`, Spring có thể thu thập tất cả bean phù hợp rồi **sắp xếp các phần tử** theo metadata về thứ tự. Điều này hữu ích cho chuỗi xử lý (pipeline), bộ kiểm tra dữ liệu, danh sách plugin, các bước chuẩn hóa hoặc nhóm handler cần chạy tuần tự.

Ví dụ, có ba bước xử lý một đơn hàng:

1. Kiểm tra đầu vào.
2. Tính giá.
3. Ghi log.

Nếu gọi bước tính giá trước khi kiểm tra đầu vào, kết quả có thể sai hoặc phát sinh lỗi. Một `List<OrderStep>` được Spring sắp xếp theo thứ tự khai báo cho phép thêm bước mới mà không cần viết lại toàn bộ cấu trúc pipeline.

Ba cách khai báo thứ tự thường gặp là:

- `org.springframework.core.Ordered`: **interface** cho bean tự cung cấp giá trị thứ tự tại runtime thông qua `getOrder()`.
- `org.springframework.core.annotation.Order`: **annotation của Spring** gắn thứ tự lên lớp hoặc một phương thức `@Bean`.
- `jakarta.annotation.Priority`: **annotation chuẩn Jakarta** đặt lên kiểu (class); Spring hiểu nó như metadata thứ tự, đồng thời nó còn có thể tham gia lựa chọn một ứng viên trong một số tình huống cần một bean.

**Quy ước chung khi sắp xếp:** số **nhỏ hơn đi trước**. Ví dụ `5` được xếp trước `10`, rồi `30`. “Priority cao hơn” ở đây không có nghĩa là giá trị số lớn hơn.

Mục tiêu của bài học là biết chính xác cơ chế áp dụng ở điểm tiêm nhiều phần tử, chọn đúng công cụ cho từng tình huống và tránh nhầm **thứ tự danh sách** với **thứ tự khởi tạo bean**.

## 2. Spring sắp thứ tự ở đâu?

Một dependency nhiều phần tử có thể xuất hiện trong constructor, field hoặc tham số phương thức `@Bean`:

```java
// Trích đoạn minh họa; interface Step và bean sở hữu
// constructor này được khai báo đầy đủ trong ví dụ bên dưới.
public Pipeline(List<Step> steps) {
    this.steps = List.copyOf(steps);
}
```

Khi Spring dựng `Pipeline` và cần `List<Step>`, container sẽ:

1. Tìm các bean có kiểu phù hợp với `Step`, xét cả các điều kiện autowire và qualifier nếu có.
2. Thu thập bean được chọn vào collection.
3. Với `List` hoặc mảng được autowire, sử dụng bộ so sánh thứ tự thích hợp để xếp các bean dựa vào `Ordered`, `@Order` hoặc `@Priority`.
4. Tiêm danh sách/mảng đã được sắp xếp vào đối tượng nhận dependency.

Vì thế, thứ tự **không phụ thuộc** vào việc method `@Bean` nằm trên hay dưới trong file nguồn. Khi có giá trị order khác nhau, Spring sắp dựa trên giá trị đó.

Trong trường hợp **không khai báo bất kỳ giá trị thứ tự nào**, tài liệu Spring mô tả các phần tử theo thứ tự đăng ký bean definition trong container. Tuy nhiên, không nên dùng thứ tự đăng ký làm hợp đồng nghiệp vụ lâu dài: thay đổi cấu hình, component scanning hay cách đăng ký bean có thể làm thứ tự quan sát thay đổi.

### Collection nào có hợp đồng thứ tự đáng tin?

| Điểm tiêm | Cách dùng | Điều cần nhớ |
| --- | --- | --- |
| `List<Step>` | Pipeline cần duyệt các bước có thứ tự | **Khuyến nghị:** Spring hỗ trợ sắp theo order metadata |
| `Step[]` | API nhận mảng các bước | Spring hỗ trợ sắp theo order metadata |
| `Set<Step>` | Tập phần tử không nhấn mạnh thứ tự | Không nên dựa vào thứ tự lặp của `Set` như một hợp đồng thực thi |
| `Map<String, Step>` | Tra cứu bean theo tên | Key là tên bean; đừng đồng nhất thứ tự duyệt map với thứ tự pipeline |

Điểm quan trọng: dùng `List` hoặc mảng khi *thứ tự xử lý là đặc tính nghiệp vụ*. Nếu cần tra cứu theo tên, `Map` phù hợp hơn; nếu cần trình tự thực thi, hãy lấy `List` rồi duyệt `for` hoặc `stream` theo thứ tự đã nhận.

## 3. Quy tắc so sánh giá trị order

Các giá trị thường dùng:

| Metadata | Ví dụ giá trị | Vị trí so với các giá trị khác |
| --- | ---: | --- |
| `@Order(-100)` | -100 | Trước `@Order(0)` |
| `@Order(0)` | 0 | Trước `@Priority(10)` |
| `@Priority(10)` | 10 | Trước `Ordered#getOrder() = 20` |
| `Ordered#getOrder()` | 20 | Trước `@Order(100)` |
| `@Order(100)` | 100 | Trước bean không có order |
| Không khai báo thứ tự | `Ordered.LOWEST_PRECEDENCE` về ngữ nghĩa | Thường ở cuối danh sách đã sắp |

Không có quy tắc “`@Priority` luôn đứng trước `@Order`” chỉ vì tên annotation là Priority. **Giá trị thứ tự mới là yếu tố quyết định** trong so sánh thông thường. `@Order(5)` đứng trước `@Priority(10)`, và `@Priority(10)` đứng trước `Ordered#getOrder() = 20`.

`Ordered` có các hằng số:

```java
Ordered.HIGHEST_PRECEDENCE  // Integer.MIN_VALUE
Ordered.LOWEST_PRECEDENCE   // Integer.MAX_VALUE
```

Số âm hoàn toàn hợp lệ. Tuy vậy, nên dùng những mức dễ hiểu như `0, 10, 20, 30` để chừa khoảng thêm bước mới. Số order là một **thứ hạng so sánh**, không phải số giây, số luồng hay mức ưu tiên của hệ điều hành.

### Nếu trùng giá trị thì sao?

Nếu hai bean đều có `@Order(10)`, comparator không có đủ thông tin từ order để xác định thứ tự tương đối. Trong thực tế, kết quả còn chịu ảnh hưởng thứ tự đầu vào của quá trình sắp xếp; **không được viết nghiệp vụ đòi hỏi bean A luôn trước B chỉ nhờ cả hai cùng order**. Hãy gán hai giá trị riêng nếu thứ tự giữa chúng quan trọng.

### Một interface khác tên gần giống: `PriorityOrdered`

`org.springframework.core.PriorityOrdered` mở rộng `Ordered`, nhưng đây là **interface riêng**, không phải annotation `jakarta.annotation.Priority`. Trong `OrderComparator` của Spring, đối tượng thực thi `PriorityOrdered` được xếp **trước các đối tượng `Ordered` thông thường**, ngay cả khi giá trị `getOrder()` của nó lớn hơn giá trị trên một đối tượng Ordered thường. Cơ chế này thường có ý nghĩa trong xử lý hạ tầng Spring; với các pipeline ứng dụng thông thường, `Ordered` hoặc `@Order` là đủ. Không tự động suy luận thứ tự của `PriorityOrdered` từ ví dụ `@Priority` bên dưới.

## 4. Phân biệt ba cách khai báo

### 4.1. `Ordered`: giá trị thứ tự theo instance

Một bean implement interface của Spring:

```java
import org.springframework.core.Ordered;

final class ConfigurableStep implements Step, Ordered {
    private final int order;

    ConfigurableStep(int order) {
        this.order = order;
    }

    @Override
    public int getOrder() {
        return order;
    }

    @Override
    public String name() {
        return "configurable";
    }
}
```

Đoạn trên **minh họa**, dùng cùng interface `Step` trong chương trình hoàn chỉnh ở mục 5. `getOrder()` có thể trả về một giá trị nhận từ cấu hình, vì thế nhiều instance của cùng một class có thể có thứ tự khác nhau.

Ưu điểm: linh hoạt, xác định theo instance. Đổi lại, class business phải phụ thuộc vào Spring API `Ordered`.

### 4.2. `@Order`: metadata cố định

Khai báo trên class:

```java
@Order(10)
final class ValidationStep implements Step {
    @Override
    public String name() {
        return "validation";
    }
}
```

Hoặc khai báo riêng trên **phương thức `@Bean`**:

```java
@Bean
@Order(5)
Step loggingStep() {
    return new PlainStep("logging");
}
```

Đây là hai đoạn **minh họa** sử dụng `Step` và `PlainStep` được khai báo ở mục 5; các annotation/import phụ trợ có trong chương trình hoàn chỉnh.

Đặt `@Order` trên phương thức `@Bean` đặc biệt hữu ích khi không kiểm soát source class (thư viện bên thứ ba) hoặc một class được khai báo thành nhiều bean với vai trò khác nhau.

`@Order` trên **lớp `@Configuration`** có mục đích khác: ảnh hưởng thứ tự xử lý giữa các configuration class. Nó **không truyền giá trị order** xuống mọi bean tạo bởi các phương thức `@Bean` bên trong. Muốn điều khiển bean trong collection, đặt metadata trên **lớp bean đích** hoặc **từng phương thức `@Bean` tương ứng**.

### 4.3. `@Priority`: annotation chuẩn Jakarta

Ví dụ:

```java
import jakarta.annotation.Priority;

@Priority(30)
final class NotifyStep implements Step {
    @Override
    public String name() {
        return "notify";
    }
}
```

Đây là đoạn **minh họa**, dùng interface `Step` trong chương trình hoàn chỉnh. Với Spring Framework 6+, import đúng là `jakarta.annotation.Priority`. Tránh copy import legacy `javax.annotation.Priority` từ các dự án Spring Framework 5 cũ.

**Lưu ý quan trọng:** `jakarta.annotation.Priority` không cho phép đặt trực tiếp trên phương thức `@Bean`. Muốn gán thứ tự cho một bean được tạo bằng phương thức factory, dùng `@Order` trên phương thức đó. Ngoài thứ tự collection, `@Priority` còn có ngữ nghĩa chọn một ứng viên được ưu tiên khi nhiều bean có thể phù hợp với dependency đơn; không nên nhầm tình huống đó với thứ tự phần tử của một `List`.

### So sánh nhanh

| Đặc điểm | `Ordered` | `@Order` | `@Priority` |
| --- | --- | --- | --- |
| Kiểu | Interface Spring | Annotation Spring | Annotation Jakarta |
| Nơi dùng điển hình | Bean instance triển khai `getOrder()` | Class bean, method `@Bean` | Class bean |
| Order thay đổi theo instance | Có | Không (giá trị annotation cố định) | Không (giá trị annotation cố định) |
| Spring xử lý khi tiêm `List`/array | Có | Có | Có |
| Dùng trực tiếp trên method `@Bean` | Không; instance implement interface | Có | **Không** |
| Liên quan đến chọn một bean | Không dùng thay `@Primary`/qualifier | Không dùng thay `@Primary`/qualifier | Có thể tham gia phân giải ưu tiên trong trường hợp cụ thể |
| Phù hợp nhất khi | Order đến từ cấu hình/runtime | Ứng dụng Spring có thứ tự tĩnh | Tích hợp thư viện hoặc code dùng chuẩn Jakarta |

Nếu một instance vừa implement `Ordered` vừa có annotation `@Order`/`@Priority` trên class, `AnnotationAwareOrderComparator` thông thường ưu tiên giá trị do instance `getOrder()` cung cấp so với annotation tĩnh. Đừng cấu hình đồng thời hai nguồn thứ tự trái ngược nếu không có lý do: chỉ rõ một nguồn là dễ bảo trì hơn.

## 5. Dự án chạy được: một collection, ba cơ chế order

Ví dụ sau dùng **JDK 17+**, **Spring Framework 6.2.19**, không cần Spring Boot hoặc web server. Để minh họa đầy đủ, có năm bean kiểu `Step`:

- `bean-method`: `@Order(5)` trên method `@Bean`.
- `annotated`: `@Order(10)` trên class.
- `dynamic`: implement `Ordered`, trả về `20`.
- `jakarta-priority`: `@Priority(30)` trên class.
- `unordered`: không khai báo metadata, xuất hiện cuối.

### 5.1. Cấu trúc tệp

```text
spring-ordering-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── OrderingDemo.java
```

Nội dung `settings.gradle`:

```groovy
rootProject.name = 'spring-ordering-demo'
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

application {
    mainClass = 'OrderingDemo'
}
```

Dependency Jakarta được khai báo tường minh để Java compile annotation `@Priority`. Spring Context cung cấp container, `@Configuration`, `@Bean`, `@Order`, `Ordered` và cơ chế autowiring.

### 5.2. Mã nguồn Java hoàn chỉnh

`src/main/java/OrderingDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

import jakarta.annotation.Priority;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

public class OrderingDemo {

    interface Step {
        String name();
    }

    static final class PlainStep implements Step {
        private final String name;

        PlainStep(String name) {
            this.name = name;
        }

        @Override
        public String name() {
            return name;
        }
    }

    @Order(10)
    static final class AnnotatedStep implements Step {
        @Override
        public String name() {
            return "annotated";
        }
    }

    static final class DynamicStep implements Step, Ordered {
        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public String name() {
            return "dynamic";
        }
    }

    @Priority(30)
    static final class JakartaStep implements Step {
        @Override
        public String name() {
            return "jakarta-priority";
        }
    }

    record Inspection(List<Step> steps, Step[] array) {
        List<String> listNames() {
            return steps.stream().map(Step::name).toList();
        }

        List<String> arrayNames() {
            return Arrays.stream(array).map(Step::name).toList();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        Step unordered() {
            return new PlainStep("unordered");
        }

        @Bean
        Step dynamic() {
            return new DynamicStep();
        }

        @Bean
        Step annotated() {
            return new AnnotatedStep();
        }

        @Bean
        Step jakartaPriority() {
            return new JakartaStep();
        }

        @Bean
        @Order(5)
        Step orderedFactoryMethod() {
            return new PlainStep("bean-method");
        }

        @Bean
        Inspection inspection(List<Step> steps, Step[] array) {
            return new Inspection(List.copyOf(steps), array.clone());
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Inspection inspection = context.getBean(Inspection.class);

            System.out.println("list  = " + inspection.listNames());
            System.out.println("array = " + inspection.arrayNames());
        }
    }
}
```

### 5.3. Cách chạy

Tại thư mục `spring-ordering-demo`, sử dụng bản Gradle tương thích với JDK đã chọn:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, thay lệnh trên bằng `./gradlew run --quiet` (macOS/Linux) hoặc `.\gradlew.bat run --quiet` (Windows PowerShell).

Stdout do chương trình in:

```text
list  = [bean-method, annotated, dynamic, jakarta-priority, unordered]
array = [bean-method, annotated, dynamic, jakarta-priority, unordered]
```

Đối chiếu giá trị:

| Phần tử | Nguồn order | Giá trị so sánh |
| --- | --- | ---: |
| `bean-method` | `@Order(5)` trên method `@Bean` | 5 |
| `annotated` | `@Order(10)` trên class | 10 |
| `dynamic` | `Ordered#getOrder()` | 20 |
| `jakarta-priority` | `@Priority(30)` trên class | 30 |
| `unordered` | Không có metadata order | `LOWEST_PRECEDENCE` |

Mặc dù method `unordered()` xuất hiện **đầu tiên** trong class `Config`, bean `unordered` được xếp **cuối** `List<Step>` và `Step[]` vì các bean khác có order rõ ràng. Điều này cho thấy thứ tự collection được quyết định bởi metadata, không phải việc developer viết method nào trước trong source.

Bài kiểm tra này cũng chứng minh Spring xem `@Order` trên method `orderedFactoryMethod()` khi resolve collection. Class `PlainStep` của bean đó không có annotation; nếu chỉ nhìn vào class instance, ta sẽ không thấy giá trị `5`.

## 6. Những tương tác dễ bị nhầm

### 6.1. Thứ tự không phải điều kiện lựa chọn

Order trả lời câu hỏi **“bean nào chạy trước?”**; kiểu và qualifier trả lời **“bean nào được tham gia?”**.

Ví dụ (minh họa, không phải một chương trình Java độc lập):

```java
@Autowired
@Qualifier("payment")
private List<Step> paymentSteps;
```

Spring trước tiên lấy các bean `Step` phù hợp với qualifier `payment`, rồi sắp xếp chúng nếu có metadata order. `@Order(1)` không tự đưa một bean sai kiểu hoặc không khớp qualifier vào danh sách. Tương tự, bean có `@Order(100)` vẫn thuộc danh sách nếu phù hợp; nó chỉ đứng sau các bean có giá trị order nhỏ hơn.

### 6.2. `@Primary` không đồng nghĩa “chạy trước”

`@Primary` hỗ trợ phân giải trường hợp cần **một bean** khi có nhiều ứng viên. Nó không xác định thứ tự `List<Step>`. Một bean có `@Primary` và `@Order(100)` vẫn có thể được xếp sau bean `@Order(5)` trong collection.

`@Priority` có thể ảnh hưởng đến lựa chọn một bean tại một số điểm tiêm đơn, nhưng đây là một **ngữ nghĩa bổ sung** của annotation Jakarta; không vì vậy mà `@Order` hay `Ordered` có thể được thay cho `@Primary`/`@Qualifier` trong mọi trường hợp. Việc chọn một bean và sắp xếp nhiều bean là hai bài toán khác nhau.

### 6.3. Thứ tự injection không phải thứ tự tạo singleton

Đây là một nhầm lẫn quan trọng: `@Order(1)` trên bean A **không bắt Spring khởi tạo A trước B** chỉ vì B có `@Order(2)`. Container tạo các singleton dựa vào việc resolve dependencies và quy trình khởi tạo, còn thứ tự đối tượng trong collection được quyết định khi xây dựng giá trị dependency.

Nếu một bean thực sự phụ thuộc vào bean khác để hoạt động, hãy biểu đạt phụ thuộc qua constructor hoặc, khi cần chỉ định thứ tự khởi tạo bằng tên bean, xem `@DependsOn`. Không dùng `@Order` để xây dựng hợp đồng khởi tạo singleton.

```java
@Bean
@DependsOn("configurationLoader")
Step reportStep() {
    return new PlainStep("report");
}
```

Đây là **đoạn minh họa**, chỉ hợp lệ khi context có bean tên `configurationLoader` và các import tương ứng. `@DependsOn` áp dụng cho quan hệ khởi tạo, không quyết định vị trí của `reportStep` trong `List<Step>`.

### 6.4. Thứ tự xử lý configuration class khác thứ tự bean

`@Order` có thể có ý nghĩa khi áp dụng cho configuration class hoặc các extension point đặc biệt của Spring. Tuy nhiên, `@Order(1)` trên `@Configuration AppConfig` không có nghĩa mọi bean của `AppConfig` đều đứng đầu khi tiêm `List<T>`. Muốn sắp thứ tự những bean cụ thể, dùng annotation tại bean class hoặc từng method `@Bean`, hoặc dùng `Ordered` trên instance.

### 6.5. Tự sắp xếp object bằng comparator Spring

Ngoài autowiring, có thể chủ động sắp xếp một `List` **object instance** bằng `AnnotationAwareOrderComparator`:

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.core.annotation.AnnotationAwareOrderComparator;

// Đoạn minh họa; các class được định nghĩa trong OrderingDemo.
List<OrderingDemo.Step> steps = new ArrayList<>(List.of(
        new OrderingDemo.DynamicStep(),
        new OrderingDemo.JakartaStep(),
        new OrderingDemo.AnnotatedStep()
));
AnnotationAwareOrderComparator.sort(steps);
```

Với ví dụ này, thứ tự các object là `annotated` (10), `dynamic` (20), `jakarta-priority` (30). Nhưng một comparator chạy trên những **object thuần** không nhất thiết có metadata nguồn từ method `@Bean`. Spring autowiring collection có thể truy xuất bean definition và factory method, nên mới đọc được `@Order(5)` trên method `orderedFactoryMethod()`. Không mặc định rằng `sort(getBeansOfType(...).values())` luôn tái tạo chính xác thứ tự của collection được autowire nếu metadata order chỉ có trên factory method.

## 7. Tình huống thực tế: pipeline xử lý tuần tự

Một pipeline có ba nhóm chức năng:

- `validate`: kiểm tra dữ liệu đầu vào, `@Order(10)`.
- `transform`: chuẩn hóa dữ liệu, `@Order(20)`.
- `notify`: phát sự kiện sau khi xử lý thành công, `@Order(30)`.

Nếu inject `List<Stage>` vào một service, ta có thể thực thi `for (Stage stage : stages) { stage.execute(context); }` và mỗi class stage chỉ chịu trách nhiệm một bước. Khi thêm `enrich` giữa validate và transform, đặt `@Order(15)`, không cần sửa vòng lặp.

Cần nhớ một số giới hạn thiết kế:

- Các bước **cần thứ tự phụ thuộc mạnh** có thể thích hợp hơn với một quy trình điều phối tường minh, state machine hoặc graph dependencies; chỉ dựa vào số order sẽ khó đọc nếu có nhánh rẽ/phụ thuộc phức tạp.
- Order metadata **không tự xử lý lỗi**. Nếu `validate` ném exception, pipeline sẽ dừng hay tiếp tục phụ thuộc vào logic thực thi, không phụ thuộc `@Order`.
- Order metadata **không đồng nghĩa** chạy tuần tự. `List` chỉ chứa các bước theo thứ tự; chính đoạn code duyệt chúng và gọi `execute` mới quyết định việc chạy tuần tự, song song hay bất đồng bộ.
- Khi hai bước thực sự cần thứ tự cố định, cho chúng **hai giá trị riêng**. Kiểm thử danh sách bean đã resolve bằng context thực để phát hiện thay đổi ngoài ý muốn.

## 8. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| List không theo thứ tự mong muốn | Không gắn order lên **bean đích** hoặc method `@Bean` đúng | Kiểm tra class bean, factory method và kết quả autowire |
| Bean có `@Priority(100)` đứng sau `@Order(10)` | Giá trị **10 nhỏ hơn 100** | Hiểu quy tắc số nhỏ trước; đặt giá trị nhất quán |
| Dùng `@Priority` trên method `@Bean` và compiler lỗi | Jakarta `@Priority` không cho phép target method | Đổi thành `@Order` trên method hoặc gắn `@Priority` trên class |
| Cấu hình `@Order` trên `@Configuration` nhưng List không đổi | Order của configuration class không lan xuống bean method | Gắn `@Order` trực tiếp vào bean/method cần sắp |
| Một bean implement `Ordered` nhưng annotation khác số | `getOrder()` có thể được ưu tiên hơn annotation tĩnh | Chọn một nguồn order rõ ràng, hoặc kiểm tra comparator thực tế |
| Thứ tự giữa hai bean bằng nhau thay đổi | Hai bean có cùng order nên không có ràng buộc thứ tự tương đối | Gán order khác nhau nếu phụ thuộc nghiệp vụ |
| Set hoặc Map được duyệt không theo pipeline | Dùng collection không có hợp đồng xử lý theo order | Tiêm `List<Stage>` hoặc mảng khi cần thứ tự |
| Thấy `@Order(1)` nhưng bean vẫn khởi tạo sau bean khác | Lẫn thứ tự collection với quan hệ khởi tạo | Dùng constructor dependency/`@DependsOn` cho khởi tạo |
| Bean primary không nằm đầu List | `@Primary` không phải metadata order | Dùng `@Order`/`Ordered`/`@Priority` cho thứ tự |
| So sánh thủ công khác autowired List | Mất metadata `@Order` của factory method khi chỉ cầm object | Kiểm tra thứ tự tại điểm injection thật hoặc truyền metadata riêng |

Để chẩn đoán, log **tên và thứ tự của các bean trong List được tiêm** ở đúng điểm sử dụng. Không chỉ nhìn thứ tự khai báo method, thứ tự log khởi tạo hoặc key trong `Map<String, T>`.

## 9. Bài tập và câu hỏi kiểm tra

**Bài tập 1 — Thêm một stage.** Thêm class `IntermediateStep` có `@Order(15)` và đăng ký bằng `@Bean` trả về `new IntermediateStep()`. Dự đoán thứ tự đầu ra mục 5:

```text
[bean-method, annotated, intermediate, dynamic, jakarta-priority, unordered]
```

Vì `5 < 10 < 15 < 20 < 30` và bean không order ở cuối.

**Bài tập 2 — Đổi order runtime.** Sửa `DynamicStep#getOrder()` từ `20` sang `2`. Kết quả mới:

```text
[dynamic, bean-method, annotated, jakarta-priority, unordered]
```

Đây là trường hợp `Ordered` cho phép điều chỉnh trên instance mà không phải đổi annotation.

**Bài tập 3 — Cùng một giá trị.** Cho `@Order(10)` cả `AnnotatedStep` lẫn `JakartaStep` (thay `@Priority` ở class kia). Hỏi thứ tự giữa hai bean này có được bảo đảm không? **Không:** order bằng nhau không biểu đạt quan hệ đứng trước/sau giữa chúng.

**Bài tập 4 — Khởi tạo.** Nếu `@Order(1)` của một stage và `@Order(99)` của stage khác, có thể kết luận constructor của stage thứ nhất chạy trước không? **Không:** thứ tự collection injection không quy định thứ tự tạo singleton.

**Bài tập 5 — Phân biệt API.** Một class implement `PriorityOrdered` với `getOrder() = 100`, một class khác chỉ implement `Ordered` với `getOrder() = 1`. Khi so sánh hai object qua `OrderComparator`, class nào trước? **PriorityOrdered** trước, vì nhóm `PriorityOrdered` có quy tắc ưu tiên riêng. Đây là ngoại lệ cần phân biệt với annotation `@Priority` thông thường.

**Bài tập 6 — Kiến trúc.** Một workflow có nhánh phụ thuộc A→B, A→C, B+C→D và các bước có thể chạy song song. Có nên biểu diễn hoàn toàn bằng `@Order` không? **Không lý tưởng**: các số thứ tự chỉ biểu diễn quan hệ trước/sau tuyến tính; một graph các dependency hoặc orchestration tường minh sẽ truyền đạt đúng luồng hơn.

## 10. Những điểm cần nhớ

1. Khi inject nhiều bean cùng kiểu vào **`List<T>` hoặc `T[]`**, Spring có thể áp dụng giá trị thứ tự từ `Ordered`, `@Order`, `@Priority` để sắp xếp phần tử.
2. **Số nhỏ đi trước**; `@Order(5)` đứng trước `@Priority(30)` trong so sánh thông thường.
3. `Ordered` cho giá trị từ instance, `@Order` cho metadata tĩnh trên class hoặc method `@Bean`; `@Priority` là annotation Jakarta thường đặt trên class.
4. `@Priority` và `PriorityOrdered` là **hai cơ chế khác nhau**. `PriorityOrdered` có ưu tiên nhóm riêng so với plain `Ordered` trong `OrderComparator`.
5. Cần phân biệt **lọc bean** (type/qualifier), **sắp thứ tự bean** (`Ordered`/`@Order`/`@Priority`), **chọn một bean** (`@Primary` và các quy tắc resolution), và **thứ tự khởi tạo** (dependency graph/`@DependsOn`).
6. Nếu pipeline cần thứ tự chạy thực sự, dùng `List` cùng các order value rõ ràng và kiểm thử kết quả resolve.

### Tài liệu tham khảo chính thức

- [Spring Framework Reference — Using `@Autowired` (collection ordering)](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Framework Javadoc — `Ordered`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/Ordered.html).
- [Spring Framework Javadoc — `@Order`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/annotation/Order.html).
- [Spring Framework Javadoc — `AnnotationAwareOrderComparator`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/annotation/AnnotationAwareOrderComparator.html).
- [Spring Framework Javadoc — `OrderComparator`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/OrderComparator.html).
