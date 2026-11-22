# Khả năng xác định kiểu sớm và ảnh hưởng tới autowiring của FactoryBean trong Spring Framework

## 1. Vấn đề: Spring phải biết kiểu bean trước khi có object thật

Trong Spring Core Container, một dependency thường được khai báo bằng **kiểu**, ví dụ constructor của `ReportService` cần một `Encoder`. Để chọn đúng bean, Spring phải nhận diện **những bean definition nào có thể cung cấp object gán được vào kiểu `Encoder`**, ngay cả khi object chưa được tạo.

Với bean thông thường, Spring có thể dựa vào class/return type của `@Bean` method hoặc bean definition. Nhưng một **`FactoryBean<T>`** là trường hợp đặc biệt: bản thân bean là một factory; object mà ứng dụng nhận khi gọi `getBean("beanName")` là **sản phẩm của `FactoryBean.getObject()`**, không phải instance factory.

Ví dụ:

```text
bean name: "textEncoder"
         |
         v
    EncoderFactory  implements FactoryBean<Encoder>
         |
         +-- getObjectType() -> Encoder.class
         |                      ^
         |                      |
         |         Spring biết kiểu product
         |         khi chưa cần tạo Encoder
         |
         +-- getObject() -> Encoder thật
                                |
                                v
                         ReportService
                        (inject Encoder)
```

**Khả năng xác định kiểu sớm (early type prediction)** nghĩa là container có thể **suy ra kiểu sản phẩm** từ metadata hoặc hỏi `FactoryBean.getObjectType()` để ghép dependency **mà chưa nhất thiết gọi `getObject()`**. Đây là một phần quan trọng để constructor autowiring, `getType()`, `getBeanNamesForType()` và type-based lookup hoạt động đúng.

Mấu chốt: **không đồng nhất việc nhận diện type, khởi tạo factory và tạo product**. Ba bước đó có thể diễn ra ở các thời điểm khác nhau.

## 2. FactoryBean<T> có hai danh tính kiểu

Giao diện `org.springframework.beans.factory.FactoryBean<T>` cung cấp ba method chính:

```java
// Chữ ký API rút gọn để học, không tự định nghĩa lại trong ứng dụng.
public interface FactoryBean<T> {
    T getObject() throws Exception;
    Class<?> getObjectType();
    default boolean isSingleton() { return true; }
}
```

Trong Spring Framework 6.x, `getObjectType()` được phép trả `null` khi chưa biết kiểu. Tuy nhiên API Javadoc lưu ý rõ: autowiring có thể **bỏ qua một FactoryBean nếu nó trả null ở thời điểm cần phát hiện kiểu**. Vì vậy hãy trả type đáng tin cậy, càng sớm càng tốt.

Giả sử bean definition có tên `"textEncoder"`, instance factory là `EncoderFactory` và product là `Encoder`:

| Truy vấn | Spring muốn biết/lấy gì? | Kết quả kỳ vọng |
| --- | --- | --- |
| `getBean("textEncoder")` | Product | Một `Encoder` |
| `getBean("&textEncoder")` | Chính factory | Một `EncoderFactory` |
| `getType("textEncoder")` | Kiểu product | `Encoder.class` nếu có thể dự đoán |
| `getType("&textEncoder")` | Kiểu factory | `EncoderFactory.class` |
| `getBeanNamesForType(Encoder.class)` | Những tên bean có product phù hợp | Có thể gồm `textEncoder` |
| `getBeanNamesForType(EncoderFactory.class)` | Các bean có type phù hợp | Không dùng để thay cho việc lấy factory bằng `&` |
| `getBean("textEncoder", Encoder.class)` | Product có kiểm tra type | `Encoder` hoặc lỗi type khi không khớp |

Ký tự `&` là hằng `BeanFactory.FACTORY_BEAN_PREFIX`, dùng **dereference factory** khi truy vấn theo tên. Không gắn `&` khi muốn product được inject vào ứng dụng.

### Khác biệt giữa type của factory và type của product

```java
public final class EncoderFactory implements FactoryBean<Encoder> {
    @Override
    public Encoder getObject() {
        // Sinh product khi container cần.
        return new PrefixEncoder("v1:");
    }

    @Override
    public Class<?> getObjectType() {
        return Encoder.class;
    }
}
```

Đây là fragment cần interface `Encoder`, class `PrefixEncoder` và import `FactoryBean`; không phải chương trình chạy độc lập. Type Java của instance factory là `EncoderFactory`, nhưng **kiểu được công bố cho bean name thông thường là `Encoder`**. Nếu đang giải dependency `Encoder`, Spring cần biết **sản phẩm**, không chỉ class thực thi factory.

## 3. getObjectType() phải chính xác, nhẹ và chạy sớm được

Javadoc Spring nhấn mạnh `getObjectType()` **có thể được gọi trước khi FactoryBean được khởi tạo hoàn toàn**. Trong tình huống type matching, Spring không muốn khởi tạo product chỉ để biết product là class nào.

Một implementation tốt:

```java
@Override
public Class<?> getObjectType() {
    return Encoder.class;
}
```

Một implementation rủi ro:

```java
@Override
public Class<?> getObjectType() {
    return product.getClass(); // product có thể null trước getObject().
}
```

Đoạn rủi ro là fragment minh họa, field `product` chưa được định nghĩa ở đây. Nếu `product` mới được tạo trong `getObject()`, `@PostConstruct` hoặc một bước sau, `getObjectType()` có thể ném `NullPointerException` hoặc trả null, làm việc tìm type thất bại.

Lỗi khác:

```java
@Override
public Class<?> getObjectType() {
    return getObject().getClass(); // Sai: tạo product để đoán kiểu.
}
```

Fragment trên chỉ có thể biên dịch nếu `getObject()` không khai báo checked exception hoặc được xử lý exception thích hợp; đây là **anti-pattern**, không phải code sản xuất. Nó có thể mở kết nối, tạo thread, chạm DB hoặc kéo một dependency chain vào lúc Spring chỉ đang hỏi “kiểu gì?”. Điều này làm tăng startup latency, nguy cơ circular dependency và side effect không mong muốn.

**Quy tắc tốt:**
1. Nếu product luôn implement `Encoder`, thường trả `Encoder.class` dù implementation cụ thể được chọn theo cấu hình.
2. Nếu consumer cần một class cụ thể, type trả về phải tương thích với concrete class đó; khai báo interface quá rộng có thể làm lookup theo concrete type không tìm thấy.
3. Không ném exception chỉ vì chưa biết kiểu. API cho phép trả `null`, nhưng phải chấp nhận hạn chế về autowiring.
4. Không phụ thuộc field được inject muộn hoặc file/network chưa sẵn sàng.
5. Không có side effect; method có thể được Spring gọi nhiều lần trong quá trình xử lý metadata.
6. Không dùng `getObjectType()` làm initialization method cho product.
7. Giữ kiểu được công bố **ổn định**, tương thích với mọi product factory có thể trả trong quá trình tồn tại.

Nếu `getObjectType()` quảng bá `CsvEncoder.class` nhưng `getObject()` trả `JsonEncoder` không kế thừa type đó, container có thể chọn bean sai khi autowire, rồi phát sinh lỗi type mismatch lúc tạo. Type metadata phải trung thực.

## 4. Type resolution diễn ra ở nhiều giai đoạn

Có ít nhất ba lớp thông tin:

**(A) Metadata của bean definition:** Spring có thể biết class của FactoryBean, signature generic `FactoryBean<Encoder>`, return type của factory method hoặc metadata được registrar đăng ký trước khi factory instance tồn tại.

**(B) FactoryBean instance:** Khi cần thêm thông tin và chính sách cho phép, Spring có thể khởi tạo factory và gọi `getObjectType()`. Điều này **không nhất thiết** tạo product.

**(C) Product thật:** `getObject()` tạo hoặc trả product, và lúc này mới biết chắc instance cụ thể của đối tượng cuối cùng.

```text
BeanDefinition / generic / factory-method return type
                  |
                  v
        có đủ type metadata?
           |              |
          Có             Không
           |              |
           |              v
           |       chính sách allow eager init?
           |             |            |
           |            Có           Không
           |             |            |
           |        instantiate      type có thể
           |        FactoryBean       chưa biết
           |             |
           |        getObjectType()
           |             |
           +-------------+
                  |
             chọn candidate
                  |
       khi dependency thực sự cần
                  |
            FactoryBean.getObject()
                  |
             product được dùng
```

Đây là mô hình khái niệm của khả năng dự đoán type, không phải trace toàn bộ phương thức nội bộ của một version Spring. Một số path có thể ưu tiên metadata/generic, một số path gọi factory và một số path bỏ qua factory chưa khởi tạo để tránh side effect.

### Phân biệt hai cấp “eager”

- **Eager initialize FactoryBean để kiểm tra kiểu**: có thể tạo **factory instance** rồi gọi `getObjectType()`. Nó không đồng nghĩa `getObject()` đã được gọi.
- **Eager initialize FactoryBean product**: tạo chính **product** ở startup, ví dụ do một singleton eager khác phụ thuộc vào product, hoặc `SmartFactoryBean.isEagerInit()` có cấu hình thích hợp.

Đừng nhìn log constructor của factory rồi kết luận product cũng đã tạo. Muốn xác định, đo riêng số lần gọi `FactoryBean.getObject()` hoặc sự kiện khởi tạo product.

## 5. Ảnh hưởng trực tiếp tới constructor autowiring

Giả sử bean nghiệp vụ cần một `Encoder`:

```java
public final class ReportService {
    private final Encoder encoder;

    public ReportService(Encoder encoder) {
        this.encoder = encoder;
    }

    public String render(String text) {
        return encoder.encode(text);
    }
}
```

Đây là fragment cần interface `Encoder`, chưa phải source độc lập. Khi Spring tạo `ReportService`, nó phải tìm bean có object type tương thích với `Encoder`. Nếu bean duy nhất được sản xuất bởi `EncoderFactory` thì Spring có thể:

1. Tìm type từ bean definition/generic signature.
2. Khi cần, gọi `EncoderFactory.getObjectType()`.
3. Nhận diện tên bean `textEncoder` là một candidate kiểu `Encoder`.
4. Lấy product qua container (có thể dẫn tới `getObject()`) để inject.

Đặc biệt, bước (2) **không cần tạo product** nếu factory công bố type đúng. Nhưng bước (4) thường sẽ tạo product **khi `ReportService` thực sự được khởi tạo**; constructor injection không biến dependency thành lazy nếu không có lazy proxy/provider riêng.

### Nếu getObjectType() trả null?

Một factory chưa biết type có thể khiến Spring **không đưa product đó vào candidate list** cho injection kiểu `Encoder`. Kết quả có thể là `NoSuchBeanDefinitionException`/`UnsatisfiedDependencyException` lúc tạo `ReportService` (tùy vị trí khởi tạo và error wrapping). Nếu còn candidate khác, Spring có thể inject candidate khác hoặc báo ambiguity, thay vì chọn factory “bị ẩn”.

```java
@Override
public Class<?> getObjectType() {
    return null; // Chỉ nên dùng khi thật sự chưa thể suy ra type.
}
```

Không khẳng định rằng **mọi** đường lookup đều thất bại khi null. Ví dụ lấy theo **tên bean** `getBean("textEncoder")` vẫn có thể gọi `getObject()` để lấy product. Có trường hợp metadata khác giúp type được nhận diện. Kết luận đúng là **trả null gây rủi ro lớn cho type-based discovery/autowiring**, không phải cấm Spring lấy product theo tên.

### Không nhầm lỗi injection với lỗi tạo product

| Triệu chứng | Phát hiện ở bước nào? | Khả năng gây ra |
| --- | --- | --- |
| Không tìm thấy candidate `Encoder` | Type discovery | `getObjectType()` null/sai, factory chưa được xem xét, package/profile sai |
| Tìm thấy hai candidates | Candidate selection | Hai product có type phù hợp; cần `@Qualifier`/`@Primary` |
| Đã chọn candidate nhưng constructor init lỗi | Product creation | `getObject()` ném exception, thiếu config, network fail |
| `BeanNotOfRequiredTypeException` | Type contract | Product không tương thích với type đang yêu cầu |
| Lấy `&textEncoder` nhưng cast sang `Encoder` | Truy xuất nhầm danh tính | `&` trả factory, không phải product |
| Injection xảy ra trước lần startup mong đợi | Eager dependent singleton | Constructor injection cần product thật khi consumer được tạo |

## 6. Ví dụ Spring Core hoàn chỉnh — xác định type trước khi tạo product

Mẫu dưới đây dùng **Java 17+, Maven 3.9+, Spring Framework 6.2.18**. Ta cố ý để `ReportService` là **lazy singleton**, nên lúc context refresh sẽ có `EncoderFactory` nhưng chưa cần tạo product. Sau đó thực hiện type query, kiểm tra counter và cuối cùng mới yêu cầu `ReportService` để quan sát thời điểm product được tạo.

### 6.1. Cấu trúc project

```text
factorybean-type-demo/
├── pom.xml
└── src/main/java/edu/example/type/
    ├── Encoder.java
    ├── PrefixEncoder.java
    ├── EncoderFactory.java
    ├── ReportService.java
    ├── AppConfig.java
    └── Main.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>factorybean-type-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>edu.example.type.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/type/Encoder.java**

```java
package edu.example.type;

public interface Encoder {
    String encode(String text);
}
```

**src/main/java/edu/example/type/PrefixEncoder.java**

```java
package edu.example.type;

public record PrefixEncoder(String prefix) implements Encoder {
    @Override
    public String encode(String text) {
        return prefix + text;
    }
}
```

**src/main/java/edu/example/type/EncoderFactory.java**

```java
package edu.example.type;

import org.springframework.beans.factory.FactoryBean;

public final class EncoderFactory implements FactoryBean<Encoder> {
    private Encoder shared;
    private int count;

    @Override
    public synchronized Encoder getObject() {
        // Tạo product đúng một lần khi có người thật sự cần.
        if (shared == null) {
            shared = new PrefixEncoder("v1:");
            count++;
        }
        return shared;
    }

    @Override
    public Class<?> getObjectType() {
        // Quan trọng: không gọi getObject() và không cần state init muộn.
        return Encoder.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }

    public synchronized int productCreationCount() {
        return count;
    }
}
```

**src/main/java/edu/example/type/ReportService.java**

```java
package edu.example.type;

public final class ReportService {
    private final Encoder encoder;

    public ReportService(Encoder encoder) {
        this.encoder = encoder;
    }

    public String render(String text) {
        return encoder.encode(text);
    }

    public Encoder encoderReference() {
        return encoder;
    }
}
```

**src/main/java/edu/example/type/AppConfig.java**

```java
package edu.example.type;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean("textEncoder")
    public EncoderFactory encoderFactory() {
        return new EncoderFactory();
    }

    @Bean
    @Lazy
    public ReportService reportService(Encoder encoder) {
        return new ReportService(encoder);
    }
}
```

**src/main/java/edu/example/type/Main.java**

```java
package edu.example.type;

import java.util.Arrays;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class Main {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            EncoderFactory factory =
                    context.getBean("&textEncoder", EncoderFactory.class);

            System.out.println("type: "
                    + context.getType("textEncoder").getSimpleName());
            System.out.println("created before request: "
                    + factory.productCreationCount());

            String[] names = context.getBeanNamesForType(Encoder.class);
            Arrays.sort(names);
            System.out.println("candidates: " + Arrays.toString(names));
            System.out.println("created after type query: "
                    + factory.productCreationCount());

            ReportService report = context.getBean(ReportService.class);
            System.out.println("result: " + report.render("abc"));
            System.out.println("created after autowire: "
                    + factory.productCreationCount());

            Encoder byName = context.getBean("textEncoder", Encoder.class);
            System.out.println("same product: "
                    + (byName == report.encoderReference()));
            System.out.println("factory type: "
                    + context.getType("&textEncoder").getSimpleName());
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Các dòng `System.out.println` của chương trình:**

```text
type: Encoder
created before request: 0
candidates: [textEncoder]
created after type query: 0
result: v1:abc
created after autowire: 1
same product: true
factory type: EncoderFactory
```

**Giải thích:**
- Constructor `AnnotationConfigApplicationContext(AppConfig.class)` tự gọi `refresh()`; factory bean singleton có thể được tạo để phục vụ metadata, nhưng product chưa bắt buộc phải tạo.
- `@Lazy` trên bean `ReportService` khiến consumer không eager-create lúc refresh. Ở sample này không có bean khác yêu cầu `Encoder` sớm.
- `getType("textEncoder")` và `getBeanNamesForType(Encoder.class)` dùng type metadata/`getObjectType()`; không cần `getObject()` nên product counter vẫn 0.
- `context.getBean(ReportService.class)` tạo lazy consumer; constructor dependency `Encoder` được resolve qua product của factory, khiến `getObject()` tạo record `PrefixEncoder` một lần.
- Do `isSingleton()==true` và chính factory giữ reference `shared`, lookup `getBean("textEncoder")` sau đó trả lại product đã có.
- `getType("&textEncoder")` hỏi type của factory, không phải type product.

Bài ví dụ có output theo quan hệ và giá trị tường minh, không phụ thuộc việc classpath scan hay thứ tự tạo các bean không liên quan. Các log Maven/Spring khác có thể xuất hiện tùy môi trường; tám dòng trên là log do chính `Main` in ra.

**Thử nghiệm:** Thay `getObjectType()` bằng `return null;` rồi chạy lại. Một số đường truy vấn type có thể trả null hoặc không tìm thấy `textEncoder`; việc autowire `Encoder` có thể thất bại. Không coi đây là một “kết quả stdout mới” cố định cho mọi đường Spring introspection; phải kiểm tra exception chain thực tế, bởi Spring có thể suy luận từ generic signature/metadata hoặc đã instantiate factory.

## 7. getBeanNamesForType(), getBeansOfType() và allowEagerInit

Ba khái niệm hay bị đánh đồng:

1. **`getType("beanName")`**: hỏi kiểu của một tên bean. Nếu product type không xác định, có thể trả null hoặc phải xem xét khởi tạo factory tùy overload/path.
2. **`getBeanNamesForType(...)`**: tìm **tên** các candidate theo type. Nó có các overload cho phép điều chỉnh phạm vi tìm bean và chính sách initialization.
3. **`getBeansOfType(...)`**: trả về **map tên → instance**, nên nó phải resolve object thật cho các kết quả phù hợp; việc trả map thường làm bean creation xảy ra.

Ví dụ với `ConfigurableListableBeanFactory` (trong Spring context có `ListableBeanFactory`), các API:

```java
String[] candidates =
        context.getBeanNamesForType(Encoder.class);

String[] conservative =
        context.getBeanNamesForType(Encoder.class, true, false);

java.util.Map<String, Encoder> instances =
        context.getBeansOfType(Encoder.class);
```

Đây là fragment phụ thuộc `context`, `Encoder` đã định nghĩa. Ba method đều thuộc `ListableBeanFactory` được `ApplicationContext` hỗ trợ. **`getBeansOfType()` không chỉ liệt kê metadata**: nó có thể tạo product và những dependency liên quan để cung cấp map instance.

### Ý nghĩa của includeNonSingletons và allowEagerInit

| Tham số | Giá trị | Hệ quả |
| --- | --- | --- |
| `includeNonSingletons=true` | Cho phép prototype/scoped/non-singleton candidates | Bao gồm phạm vi rộng hơn |
| `includeNonSingletons=false` | Chỉ xét singleton phù hợp | Có xét product singleton của FactoryBean theo khả năng xác định |
| `allowEagerInit=true` | Cho phép init factory/lazy infrastructure **khi cần type matching** | Có thể sinh side effect của factory initialization |
| `allowEagerInit=false` | Hạn chế eager initialization để tìm type | Có thể **không liệt kê** product FactoryBean chưa có factory instance/metadata đủ tốt |

Đặc biệt, tài liệu `ListableBeanFactory.getBeanNamesForType(type, includeNonSingletons, allowEagerInit)` giải thích rằng khi `allowEagerInit=false`, việc kiểm tra FactoryBeans có thể chỉ xét raw factory thay vì product nếu cần tạo factory để hỏi `getObjectType()`. Vì thế **kết quả tìm tên rỗng không chứng minh chắc chắn rằng không có bean có thể tạo product kiểu đó**.

`allowEagerInit=true` **không có nghĩa** Spring luôn gọi `FactoryBean.getObject()` ngay lập tức. Nó thường cho phép **factory itself** được tạo để làm type detection, trong khi việc tạo product riêng có thể vẫn chờ lúc dependency thực sự được resolve.

Ví dụ phân tích:

```text
A. Product type biết từ BeanDefinition / generic metadata
   -> có thể nhận diện tên candidate mà chưa tạo FactoryBean.

B. Product type chỉ xác định trong factory.getObjectType()
   -> có thể cần instantiate factory trước khi tìm thấy candidate.

C. Product type chỉ biết sau một call nặng tới getObject()
   -> API FactoryBean thiết kế không khuyến khích cách này;
      Spring có thể bỏ qua candidate hoặc phát sinh side effect không mong muốn.
```

Khi xây framework, plugin registry hay startup health check, cân nhắc **lookup theo tên rồi resolve có chọn lọc**. Dùng `getBeansOfType` để load mọi service plugin có thể vô tình kích hoạt các FactoryBean đắt tiền.

### Kết quả theo thứ tự và context hierarchy

Một `ListableBeanFactory` thông thường tìm **các bean của factory hiện tại**, không tự quét bean trong mọi parent/child context. Đối với hierarchy, sử dụng `BeanFactoryUtils.beanNamesForTypeIncludingAncestors(...)` khi cần. Không mặc định một tên product có ý nghĩa giống nhau trong toàn bộ JVM/pod.

## 8. Tại sao getObjectType() trả null làm autowiring khó đoán?

Giả sử cấu hình sau:

```java
public final class UnknownEncoderFactory implements FactoryBean<Encoder> {
    private Encoder product;

    @Override
    public Encoder getObject() {
        if (product == null) {
            product = new PrefixEncoder("unknown:");
        }
        return product;
    }

    @Override
    public Class<?> getObjectType() {
        return product == null ? null : product.getClass();
    }
}
```

Đây là fragment minh họa chống pattern, cần imports `FactoryBean` và types `Encoder`/`PrefixEncoder`. Lúc container chỉ hỏi type của bean chưa tạo product, factory trả `null`. Spring có thể không nhận diện candidate này khi resolve dependency `Encoder` theo type. Nếu application lấy product bằng tên trước, sau đó việc type discovery lại có kết quả khác. Điều này dẫn đến lỗi **phụ thuộc thứ tự sử dụng** rất khó debug.

**Sửa:** nếu luôn tạo `PrefixEncoder` thì trả `PrefixEncoder.class` hoặc ít nhất `Encoder.class` ngay từ đầu, không dựa vào trạng thái `product`.

Nếu product class chỉ được quyết định từ một key config nhưng đều implement interface `Encoder`, trả `Encoder.class` thường đủ cho các consumer inject `Encoder`. Consumer inject trực tiếp `PrefixEncoder` có thể không phát hiện bean nếu type metadata chỉ công bố interface; đây là giới hạn lựa chọn type dự đoán, không phải product không implement `PrefixEncoder` lúc runtime.

### Hệ quả với @ConditionalOnBean trong Spring Boot

Mặc dù chủ đề chính là Spring Core, hệ thống thực tế còn dùng `@ConditionalOnBean(Encoder.class)` trong Spring Boot auto-configuration. Những condition kiểu này thường dựa trên type metadata và thời điểm registration của bean definitions. Một FactoryBean ẩn product type có thể khiến điều kiện không nhận diện bean như dự kiến. Nếu làm starter/auto-configuration, đặc biệt cần cung cấp `getObjectType()` đúng, return signature rõ và metadata đủ sớm. Không nhầm behavior của Spring Boot condition với một contract của `FactoryBean` rằng nó tự sửa được mọi type matching.

## 9. Khi có nhiều candidate: @Qualifier và @Primary

Giả sử hai factory bean đều công bố `Encoder.class`:

```java
@Configuration(proxyBeanMethods = false)
class MultiConfig {
    @Bean("fastEncoder")
    FactoryBean<Encoder> fastEncoder() {
        return new FastEncoderFactory();
    }

    @Bean("safeEncoder")
    FactoryBean<Encoder> safeEncoder() {
        return new SafeEncoderFactory();
    }
}
```

Snippet chỉ mô tả kiến trúc, chưa biên dịch vì `FastEncoderFactory`/`SafeEncoderFactory` chưa được định nghĩa. Khi cả hai product đều là candidate của `Encoder`, constructor injection `ReportService(Encoder encoder)` có thể báo `NoUniqueBeanDefinitionException` (thường được wrap khi tạo consumer).

Sửa bằng qualifier trên injection point:

```java
@Service
class ReportService {
    private final Encoder encoder;

    ReportService(@Qualifier("safeEncoder") Encoder encoder) {
        this.encoder = encoder;
    }
}
```

Snippet cần imports `@Service`/`@Qualifier` và `Encoder`. `@Qualifier` chọn product bean có tên/qualifier tương ứng; không yêu cầu consumer giữ một instance `FactoryBean`.

Hoặc đánh dấu một definition product là primary:

```java
@Bean("safeEncoder")
@Primary
FactoryBean<Encoder> safeEncoder() {
    return new SafeEncoderFactory();
}
```

Snippet cần `@Bean`, `@Primary` và factory type. `@Primary` ưu tiên candidate trong autowiring khi có nhiều bean cùng type; nó **không sửa** việc type chưa được phát hiện. Với một FactoryBean trả null ở `getObjectType()`, gắn `@Primary` không bảo đảm candidate sẽ tự xuất hiện trong mọi truy vấn.

**Tổng hợp:**

| Vấn đề | Công cụ phù hợp | Điều cần có từ FactoryBean |
| --- | --- | --- |
| Spring không biết có product kiểu gì | `getObjectType()`, return type/metadata rõ | Kiểu phải đúng, biết được sớm |
| Có đúng một candidate | Autowiring theo type | FactoryBean phải được phát hiện |
| Có nhiều candidate cùng type | `@Qualifier`, `@Primary` | Các candidates phải được phát hiện |
| Dependency optional | `ObjectProvider<Encoder>`, `Optional<Encoder>` | Không tạo object nếu chưa cần, nhưng type discovery vẫn quan trọng |
| Muốn nhiều implementations | `List<Encoder>`, `Map<String, Encoder>` | Product type cần đúng để tham gia collection |
| Muốn inject chính factory | `getBean("&name")` hoặc cấu hình injection phù hợp | Không nhầm factory với product |

## 10. Generic type: Class<?> chưa biểu diễn đầy đủ Repository<User>

`getObjectType()` trả về một `Class<?>`. Nó chỉ biểu diễn **raw class/interface type**, không trực tiếp biểu diễn tham số generic cụ thể như `Repository<User>`. Spring dùng `ResolvableType` và metadata từ bean definitions/factory method/target declaration khi cần suy luận type generic.

Ví dụ mục tiêu:

```java
interface Repository<T> {
    T findById(String id);
}

record User(String id) {}

final class UserRepository implements Repository<User> {
    @Override
    public User findById(String id) {
        return new User(id);
    }
}
```

Đây là Java snippet hoàn chỉnh về types nhưng không được gắn vào project `Encoder` của mục 6. Nếu factory tạo `Repository<User>` và `getObjectType()` trả `Repository.class`, thông tin `<User>` không nằm trong đối tượng `Class<?>` đó. Spring có thể suy ra generic từ `FactoryBean<Repository<User>>` hoặc metadata bean definition trong một số trường hợp, nhưng không nên mặc định mọi định nghĩa raw type đều đủ để autowire chính xác `Repository<User>` và phân biệt với `Repository<Order>`.

**Nên làm:**
- Khai báo generic signature cụ thể trên class/factory method, ví dụ `FactoryBean<Repository<User>>` thay vì raw `FactoryBean`.
- Cung cấp `getObjectType()` chính xác ở mức class hoặc interface.
- Nếu viết infrastructure tự đăng ký bean definitions, cân nhắc cung cấp `ResolvableType` trong metadata khi framework hỗ trợ.
- Tạo integration test với hai product khác generic arguments để xác nhận Spring chọn bean đúng, tránh dựa vào type erasure hoặc suy luận hời hợt.
- Nếu những product rất khác nhau theo config runtime, thường nên đăng ký bean definitions riêng rõ ràng, thay vì một factory mơ hồ không thể dự đoán type.

### Metadata FACTORY_BEAN_OBJECT_TYPE_ATTRIBUTE

Spring có hằng `FactoryBean.OBJECT_TYPE_ATTRIBUTE` với giá trị key `"factoryBeanObjectType"`. Infrastructure tạo `BeanDefinition` bằng code có thể đặt metadata này để báo sớm kiểu sản phẩm khi không thể suy từ factory class.

Ví dụ ý tưởng với Spring BeanDefinition API:

```java
BeanDefinition definition =
        BeanDefinitionBuilder.genericBeanDefinition(EncoderFactory.class)
                .getBeanDefinition();

definition.setAttribute(FactoryBean.OBJECT_TYPE_ATTRIBUTE, Encoder.class);
```

Snippet cần imports `BeanDefinition`, `BeanDefinitionBuilder`, `FactoryBean` và `EncoderFactory`; code phải được dùng trong registrar/BeanDefinitionRegistry phù hợp, **không** phải project runnable của mục 6. Ở Spring 6.1+/6.2, attribute phải là `Class<?>` hoặc `ResolvableType` (hoặc không có attribute), **không đặt chuỗi `"com.example.Encoder"`**: Spring có thể ném lỗi do kiểu metadata không hợp lệ. Đây là API cho tác giả infrastructure; ứng dụng thường chỉ cần `getObjectType()` đúng.

**Không lạm dụng:** attribute không thay việc `getObject()` trả product thực sự đúng type và không thay cơ chế xử lý injection bình thường. Metadata sai có thể khiến Spring phát hiện candidate nhưng lỗi lúc resolve instance.

## 11. FactoryBean và lifecycle: một lý do cần type prediction sớm

Một factory là bean thực thụ, còn product là object do factory cung cấp.

```text
Container refresh / dependency discovery
  |
  +-- có thể inspect BeanDefinition, generic signature
  +-- có thể tạo FactoryBean để gọi getObjectType()
  |
  +-- FactoryBean instance được initialize:
        constructor, injection, @PostConstruct, InitializingBean...
  |
  +-- product được yêu cầu:
        FactoryBean.getObject()
        cache nếu factory singleton và product singleton phù hợp
  |
  +-- inject product vào consumer
```

Spring có thể có logic post-process object do FactoryBean trả về, nhưng **không suy ra sản phẩm tự động nhận toàn bộ lifecycle như một bean definition bình thường**. Nếu product quản lý socket/SDK thread pool, cần làm rõ người chịu trách nhiệm khởi tạo/đóng resource. Factory singleton có thể implement `DisposableBean` để cleanup product mà nó sở hữu, hoặc dùng managed lifecycle component riêng.

### Khi nào factory đã tạo nhưng product chưa?

- Context refresh dựng factory singleton eager nhưng chưa có consumer yêu cầu product.
- Một type lookup cho phép eager initialization của **factory** để xem `getObjectType()`, nhưng chưa cần `getObject()`.
- App gọi `getBean("&textEncoder")` để kiểm tra factory, chưa yêu cầu product.
- Bean consumer lazy chưa được resolve.

### Khi nào product có thể tạo sớm?

- Một eager singleton consumer inject product trong constructor.
- `getBeansOfType(Encoder.class)` cần trả map instance.
- Code gọi `getBean("textEncoder")`, kể cả trước khi application fully ready nếu được phép.
- `SmartFactoryBean.isEagerInit()` quảng bá product cần eager initialization trong quy trình pre-instantiation thích hợp.

`isSingleton()==true` không đồng nghĩa product được tạo ngay khi context refresh. Nó nói về **identity của object được share/cached**. Ngược lại, `@Lazy` trên consumer chỉ trì hoãn việc resolve dependency của consumer nếu không có nơi khác tạo product sớm.

## 12. Thực hành chẩn đoán lỗi bằng API Spring

Khi gặp injection failure liên quan FactoryBean, đừng sửa ngay bằng `@Primary` hoặc `@Lazy`. Phân tách các câu hỏi theo đúng giai đoạn:

```java
// Trong ApplicationContext ctx đã refresh:
System.out.println(ctx.getType("textEncoder"));
System.out.println(ctx.getType("&textEncoder"));

System.out.println(
        java.util.Arrays.toString(
                ctx.getBeanNamesForType(Encoder.class, true, false)));

System.out.println(
        java.util.Arrays.toString(
                ctx.getBeanNamesForType(Encoder.class, true, true)));

Encoder product = ctx.getBean("textEncoder", Encoder.class);
```

Snippet debug không phải chương trình chạy độc lập, `ctx`/`Encoder` cần được định nghĩa. **Lưu ý:** gọi `getBean` ở dòng cuối sẽ tạo product nếu chưa có; chỉ chạy khi chấp nhận side effect. So sánh hai overload `allowEagerInit` giúp phân biệt candidate do metadata nhận ra với candidate cần khởi tạo factory để khám phá.

Checklist:

1. Bean definition `textEncoder` thực sự đăng ký trong đúng `ApplicationContext` chưa? `@Profile` và `@Conditional` có loại nó không?
2. Bean được lấy là `"textEncoder"` (product) hay `"&textEncoder"` (factory)?
3. `getType("textEncoder")` trả gì **trước** khi tạo product?
4. `FactoryBean.getObjectType()` có thể trả null ở pha sớm không? Có phụ thuộc `@PostConstruct`/field được inject muộn không?
5. Type công bố có tương thích với output của `getObject()` ở mọi cấu hình không?
6. Factory có bị initialize sớm khi `allowEagerInit=true` không? Initialization này có side effect bất hợp lý không?
7. Có nhiều bean product cùng type? `@Qualifier`/`@Primary` đúng vị trí chưa?
8. Type là generic `Repository<User>` hay raw `Repository`? Metadata có đủ để phân biệt không?
9. `getObject()` có ném exception, trả null hoặc tạo proxy không assignable như khai báo không?
10. Bean consumer eager hay lazy? Product đã có người dùng khác resolve trước đó không?
11. Nếu dùng programmatic registry, attribute `factoryBeanObjectType` đúng kiểu `Class`/`ResolvableType` không?
12. Test có vô tình gọi `getBeansOfType` khiến toàn bộ products được instantiate trước khi assert không?

### Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| Autowiring `Encoder` báo không có bean dù có FactoryBean | `getObjectType()` null, bean profile không active, type metadata thiếu | Công bố type ổn định, test type lookup sớm |
| `getBean("textEncoder")` chạy, injection theo type lại lỗi | Lookup theo tên không yêu cầu cùng metadata như type matching | Sửa `getObjectType`/generic/definition metadata |
| `getType("textEncoder")` trả null trước startup use | Factory chưa thể dự đoán product type | Trả common interface hoặc metadata sớm |
| Có hai FactoryBean product type `Encoder` | Ambiguity | `@Qualifier`, `@Primary`, hoặc inject collection |
| `getType("&textEncoder")` khác type mong muốn | Đang hỏi type factory | Bỏ `&` khi hỏi product |
| `getBeanNamesForType(..., false)` thiếu candidate | Eager type introspection không được phép | Hiểu trade-off, dùng metadata hoặc truy vấn phù hợp |
| `getBeansOfType` làm SDK client kết nối sớm | Phải materialize instances để trả map | Liệt kê tên rồi resolve có chọn lọc |
| `getObjectType()` truy vấn network | Side effect trong type discovery | Loại bỏ I/O khỏi type prediction |
| Attribute `factoryBeanObjectType` là `String` | Metadata không hợp lệ ở Spring 6.1+ | Dùng `Class<?>` hoặc `ResolvableType` |
| Product type là JDK proxy interface, khai báo concrete class | Dự đoán class quá cụ thể, không assignable | Công bố đúng interface mà proxy implement |
| `FactoryBean<Repository>` không phân biệt generic User/Order | Mất parameterized metadata | Khai báo generic cụ thể và test autowiring |
| Consumer `@Lazy` nhưng product vẫn tạo lúc refresh | Có eager dependency hoặc `SmartFactoryBean` | Kiểm tra graph, factory lifecycle và startup logic |
| Factory singleton, product không singleton | `isSingleton() == false` | Phân biệt lifecycle của factory và product |
| Product singleton không thread-safe | Cùng reference được nhiều luồng dùng | Thiết kế immutable/synchronization riêng |

## 13. Bài tập tự đánh giá

1. Vì sao Spring cần biết `FactoryBean.getObjectType()` trước khi gọi `getObject()`?
2. `getBean("textEncoder")` và `getBean("&textEncoder")` khác nhau thế nào?
3. Nếu `getObjectType()` phụ thuộc field `product` mới gán ở `getObject()`, điều gì có thể xảy ra khi Spring autowire?
4. `FactoryBean<Encoder>` trả product `PrefixEncoder`; consumer inject `Encoder` có hợp lệ không nếu `getObjectType()` trả `Encoder.class`?
5. Consumer inject trực tiếp `PrefixEncoder` có chắc được chọn nếu factory chỉ công bố `Encoder.class` không?
6. `isSingleton()==true` có bắt buộc product được tạo lúc `refresh()` không?
7. Sự khác biệt giữa `getBeanNamesForType` và `getBeansOfType` là gì?
8. `getBeanNamesForType(Encoder.class, true, false)` có thể bỏ sót loại candidate nào?
9. Vì sao `getObjectType()` không nên gọi remote API để lấy product class?
10. Có hai FactoryBean đều công bố `Encoder.class`, làm sao chọn một cho injection?
11. `FactoryBean.OBJECT_TYPE_ATTRIBUTE` cần dạng dữ liệu nào trên Spring 6.2?
12. Tại sao một `Class<?>` không đủ đại diện `Repository<User>`?
13. `FactoryBean` có thể được tạo nhưng product chưa tạo không?
14. `@Lazy` trên `ReportService` có giúp trì hoãn product nếu một singleton khác eager inject nó không?
15. Trong ví dụ runnable, dòng `created after type query: 0` minh họa điều gì?

**Gợi ý đáp án:** (1) Để nhận diện candidate/autowire mà không tạo product. (2) Không prefix trả product, có `&` trả factory. (3) Null hoặc exception khi type lookup, candidate có thể bị bỏ qua. (4) Có. (5) Không chắc, type được công bố quá rộng. (6) Không. (7) Một bên trả names, bên còn lại trả instances. (8) FactoryBean/lazy bean cần eager init để dự đoán kiểu. (9) Gây side effect/latency/circular reference. (10) `@Qualifier`/`@Primary`. (11) `Class<?>` hoặc `ResolvableType`, không phải String. (12) Java Class không mang type argument; dùng generic signature/metadata. (13) Có. (14) Không, nơi khác vẫn có thể yêu cầu product. (15) Type prediction không đòi gọi `getObject()` trong project đó.

## 14. Nguyên tắc triển khai thực tế

- Luôn phân biệt **factory type**, **product type** và **product instance**.
- `getObjectType()` là contract quan trọng cho **autowiring by type**, không phải một method phụ tùy ý.
- Trả type chính xác và ổn định từ metadata/kiểu đã biết **mà không tạo product**.
- Chấp nhận `null` chỉ khi thật sự không thể xác định, và hiểu lookup by type có thể bỏ qua factory.
- Thiết kế factory initialization nhẹ; type discovery có thể khiến factory được tạo trước khi business logic dùng product.
- Thận trọng với `allowEagerInit` khi viết plugin registries/startup scanners.
- Không dùng `getBeansOfType` nếu chỉ muốn liệt kê tên và không chấp nhận product creation.
- Dùng `@Qualifier`/`@Primary` khi **nhiều candidate đúng type**, không dùng để che giấu metadata sai.
- Với generic dependency, kiểm tra `ResolvableType`/declaration thực tế trong integration tests.
- Tránh side effect trong `getObjectType()`; tạo resource thật trong `getObject()` với timeout/error policy.
- Nếu product shared, bảo đảm thread safety và cleanup tài nguyên phù hợp; `isSingleton()` không thay điều này.
- Viết test kiểm chứng **type query không tạo product**, rồi test autowiring và identity riêng.

## 15. Tài liệu chính thức

- Spring Framework — Customizing Instantiation Logic with FactoryBean: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework 6.2 — FactoryBean Javadoc (getObjectType, isSingleton, OBJECT_TYPE_ATTRIBUTE): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/FactoryBean.html
- Spring Framework 6.2 — ListableBeanFactory Javadoc (getBeanNamesForType, allowEagerInit): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html
- Spring Framework 6.2 — BeanFactory Javadoc (FACTORY_BEAN_PREFIX, getType): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/BeanFactory.html
- Spring Framework 6.2 — AbstractBeanFactory getTypeForFactoryBean metadata: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/support/AbstractBeanFactory.html
- Spring Framework 6.2 — ResolvableType Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/ResolvableType.html
- Spring Framework 6.2 — SmartFactoryBean Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/SmartFactoryBean.html
