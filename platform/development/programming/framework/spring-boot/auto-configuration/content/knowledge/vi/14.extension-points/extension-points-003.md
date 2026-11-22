# Xử lý không có, có một hoặc có nhiều thành phần mở rộng

## 1. Mục tiêu và bài toán

Một **điểm mở rộng** (*extension point*) là hợp đồng cho phép ứng dụng hoặc thư viện bổ sung hành vi mà không sửa mã lõi. Trong Spring Boot, điểm mở rộng thường được biểu diễn bằng interface hoặc callback; các triển khai được đăng ký thành bean trong `ApplicationContext`.

Ví dụ, một starter xử lý thông điệp công bố interface `MessageExtension`. Ứng dụng sử dụng starter có thể không đăng ký triển khai nào, đăng ký một triển khai, hoặc cài nhiều triển khai từ nhiều module khác nhau. Starter phải xử lý chính xác **cả ba trường hợp**:

- **Không có extension (0):** chọn chính sách rõ ràng: giữ nguyên kết quả (*no-op*), cung cấp triển khai mặc định (*fallback*), tắt tính năng, hoặc báo lỗi cấu hình nếu extension là bắt buộc.
- **Có đúng một extension (1):** sử dụng triển khai đó mà không cần người dùng cấu hình thêm, nếu hợp đồng cho phép.
- **Có nhiều extension (N > 1):** chọn một chính sách có chủ ý: áp dụng **tất cả theo thứ tự**, chọn một theo qualifier/ưu tiên, hợp nhất kết quả, hoặc từ chối trường hợp nhập nhằng. Không lấy ngẫu nhiên “bean đầu tiên”.

Mục tiêu sau bài này: đọc đúng sự khác nhau giữa “bean tồn tại” và “bean duy nhất”, dùng `ObjectProvider<T>`, `orderedStream()`, `@Order` và điều kiện của Spring Boot khi thích hợp; thiết kế fallback và lỗi trùng rõ ràng; chạy chương trình Java 17+ để quan sát 0/1/N extension.

**Giới hạn:** chúng ta đang thiết kế extension **được quản lý bằng Spring bean** trong ngữ cảnh Spring Boot Auto Configuration. Java `ServiceLoader`, plugin động được tải ngoài JVM và việc nạp JAR ở runtime là những cơ chế khác, không được tự động kích hoạt chỉ vì khai báo extension interface.

## 2. Xác định hợp đồng trước khi chọn annotation

Giả sử điểm mở rộng là:

```java
public interface MessageExtension {
    String id();
    String apply(String input);
}
```

Đoạn trên minh họa hợp đồng; trong chương trình chạy đầy đủ ở mục 6, interface sẽ nằm trong class demo. Ý nghĩa hai phương thức:

- `id()`: định danh logic của extension, để cấu hình, thông báo lỗi và phát hiện trùng. Đây **không nhất thiết** là tên bean Spring.
- `apply(input)`: biến đổi đầu vào và trả ra đầu ra. Ứng dụng tự quy định được phép đổi nội dung, trả `null`, ném exception, có side effect hay không. Trong ví dụ, quy ước trả chuỗi không null.

Với một interface như vậy, quyết định thiết kế quan trọng nhất là **ngữ nghĩa khi có nhiều implementation**. Hai cách phổ biến không thể tự thay thế cho nhau:

1. **Chuỗi xử lý / danh sách handler:** tất cả extension có ích. Mỗi extension xử lý kết quả từ extension trước, nên thứ tự là một phần của hợp đồng.
2. **Một chiến lược được chọn:** nhiều extension là các lựa chọn cạnh tranh. Ứng dụng phải chỉ định `@Qualifier`, tên, cấu hình định danh, hoặc một chính sách chọn duy nhất.

Đừng viết một điểm mở rộng theo dạng “tôi mong luôn có một bean” nếu giao diện công khai cho phép cài nhiều plugin; khi plugin thứ hai xuất hiện, injection một giá trị `MessageExtension` có thể thành nhập nhằng.

### Bảng quyết định theo số thành phần

| Tình huống | Nếu điểm mở rộng là danh sách xử lý | Nếu điểm mở rộng đòi một chiến lược |
| --- | --- | --- |
| **0 bean** | Trả lại input hoặc dùng fallback đã được nêu rõ | Dùng default nếu cho phép, hoặc báo lỗi “thiếu chiến lược” |
| **1 bean** | Thực thi một lần | Chọn bean duy nhất |
| **N bean** | Sắp xếp và chạy tất cả; xác định quy tắc lỗi và trùng | Chọn bằng tiêu chí rõ ràng hoặc fail-fast |
| **Có @Primary** | Không khiến các bean còn lại biến mất khỏi danh sách | Có thể giúp Spring xác định một ứng viên cho single-value injection |
| **Thứ tự @Order** | Quan trọng để định nghĩa trình tự pipeline | Không đồng nghĩa bean có thứ tự thấp tự trở thành “ứng viên duy nhất” |

Các chính sách này là quyết định nghiệp vụ của starter. Spring cung cấp API để hiện thực chứ không thể suy ra ý định chỉ từ interface.

## 3. Tra cứu 0/1/N bean trong Spring: chọn đúng công cụ

### 3.1. `ObjectProvider<MessageExtension>` và `orderedStream()`

Trong bean quản lý pipeline:

```java
@Bean
MessagePipeline messagePipeline(
    ObjectProvider<MessageExtension> extensionProvider
) {
    List<MessageExtension> ordered =
        extensionProvider.orderedStream().toList();
    return new MessagePipeline(ordered);
}
```

Đây là **snippet minh họa** (giả định `MessagePipeline` tồn tại). `ObjectProvider<T>` là API của Spring để tra cứu đối tượng linh hoạt. `orderedStream()` tạo stream các bean tương thích với `T` theo thứ tự comparator của BeanFactory, có xét `Ordered` và `@Order` ở Spring context phù hợp.

- **0 extension:** `orderedStream()` rỗng; `toList()` trả danh sách rỗng. Bean pipeline vẫn tạo được.
- **1 extension:** danh sách có một đối tượng.
- **N extension:** danh sách chứa tất cả bean phù hợp được đưa ra từ provider, theo thứ tự đã xác định; pipeline tự chọn cách kết hợp.

Ưu điểm ở đây: điểm mở rộng thực sự hỗ trợ **zero-or-more**, không cần tạo một bean dummy chỉ để làm cho injection một phần tử thành công. `ObjectProvider` giải quyết bean tại lúc được truy cập; khi chuyển thành `List` và lưu trong pipeline ở constructor, bạn tạo **ảnh chụp** danh sách ở thời điểm xây pipeline. Nếu cần tra động ở mỗi lượt xử lý, có thể giữ provider và gọi `orderedStream()` lúc chạy, sau khi cân nhắc chi phí và lifecycle.

Các bean được chọn vẫn chịu quy tắc candidate/qualifier của Spring. Nếu áp dụng `@Qualifier` lên injection point hoặc có bean không đủ điều kiện autowire, danh sách trả về có thể khác toàn bộ bean definition cùng kiểu.

### 3.2. Vì sao không dùng ngay `getObject()` / `getIfAvailable()` / `getIfUnique()`?

Các API một kết quả mang ngữ nghĩa khác:

| Cách lấy bean | Không có bean | Một ứng viên | Nhiều ứng viên không xác định được một ứng viên ưu tiên |
| --- | --- | --- | --- |
| `provider.getObject()` | Lỗi không có bean | Trả bean | Lỗi nhập nhằng |
| `provider.getIfAvailable()` | Trả `null` | Trả bean | Có thể ném `NoUniqueBeanDefinitionException` |
| `provider.getIfUnique()` | Trả `null` | Trả bean | Trả `null` nếu không có ứng viên duy nhất |
| `provider.orderedStream()` | Stream rỗng | Stream có một phần tử | Stream chứa các bean phù hợp, đã sắp theo quy tắc order |

**Lưu ý `@Primary`:** trong Spring 6.1, `getIfUnique()` có thể trả về bean `@Primary` khi có nhiều bean nhưng vẫn xác định được một ứng viên ưu tiên. Vì vậy **`getIfUnique() != null` không chứng minh trong context có đúng một bean**; để kiểm cardinality, hãy đếm các ứng viên qua stream hoặc kiểm danh sách. `getIfAvailable()` cũng có thể giải quyết được một ứng viên khi có primary/qualifier phù hợp; không giả định nó luôn lỗi nếu có từ hai bean trở lên.

Ví dụ:

```java
MessageExtension selected = provider.getIfUnique();
```

Đoạn này phù hợp khi hợp đồng thực sự là “dùng một ứng viên Spring coi là duy nhất; nếu không có ứng viên được chọn thì không chạy”, **không** phù hợp khi nhiều extension đều phải được thực thi. Nó cũng có nguy cơ âm thầm coi 0 bean và nhiều bean nhập nhằng như cùng một trạng thái `null`.

### 3.3. `Optional<T>`, `List<T>` và `Map<String,T>`

Spring cũng hỗ trợ các dạng injection:

```java
// Minh họa chữ ký constructor, không phải chương trình độc lập.
public ExampleService(Optional<MessageExtension> optional) { ... }
public ExampleService(List<MessageExtension> extensions) { ... }
public ExampleService(Map<String, MessageExtension> byBeanName) { ... }
```

- `Optional<T>` biểu thị dependency **không bắt buộc**, nhưng chỉ phù hợp với **một lựa chọn**; nếu có nhiều ứng viên không phân giải được, vẫn có thể xảy ra lỗi nhập nhằng. `Optional` không phải container chứa mọi plugin.
- `List<T>` và `Map<String,T>` có thể dùng để lấy nhiều bean (map có key là **tên bean**). Tuy nhiên, nếu không có bean phù hợp, hành vi injection còn tùy thuộc điểm injection và độ bắt buộc; trong bài này chọn `ObjectProvider<T>.orderedStream()` để trường hợp 0 luôn tường minh và ổn định.
- `Map<String,T>` giúp chẩn đoán bean tên gì hoặc chọn theo bean name. Tên bean **khác** với `id()` của hợp đồng plugin nếu ứng dụng không chủ động đồng bộ hai giá trị.

Nếu pipeline luôn chạy tất cả implementation, hãy dùng API **nhiều kết quả**. Nếu pipeline chỉ chạy một implementation, hãy thiết kế chính sách **duy nhất** và test khi cấu hình có hai plugin.

## 4. Thứ tự khi có nhiều extension

Giả sử một extension thêm prefix và một extension thêm suffix. Hai phép biến đổi có thể không giao hoán:

```text
input = "hello"

prefix trước suffix: [A:hello]|B
suffix trước prefix: [A:hello|B]
```

Nếu bạn để phụ thuộc vào thứ tự bean được đăng ký hoặc thứ tự duyệt classpath, kết quả có thể thay đổi khi thêm starter/module khác.

### 4.1. `@Order` và `Ordered`

Có thể gắn `@Order` lên lớp bean hoặc phương thức `@Bean`:

```java
@Bean
@Order(10)
MessageExtension prefixExtension() {
    return new PrefixExtension();
}

@Bean
@Order(20)
MessageExtension suffixExtension() {
    return new SuffixExtension();
}
```

Đây là snippet dựa trên các kiểu giả định, bản đầy đủ ở mục 6. **Số nhỏ có ưu tiên sớm hơn**: khi provider dùng `orderedStream()`, prefix có order 10 được thực thi trước suffix có order 20. Các implementation cũng có thể triển khai `Ordered`, trả về thứ tự qua `getOrder()`.

**Không nhầm `@Order` với thứ tự khởi tạo singleton.** Thứ tự danh sách để xử lý extension và thứ tự Spring tạo instance bean là hai vấn đề khác nhau; Spring quyết định dependency khởi tạo dựa trên injection/`@DependsOn` và lifecycle.

Nếu hai extension có **cùng** giá trị order, không lấy thứ tự tương đối của chúng làm logic nghiệp vụ. Khi thứ tự ổn định là yêu cầu quan trọng, hãy bổ sung khóa phụ như `id()` và kiểm dữ liệu bằng comparator minh bạch, hoặc yêu cầu các plugin khai báo thứ tự không trùng.

### 4.2. Ưu tiên không có nghĩa loại bỏ extension khác

`@Order(10)` **không** mang nghĩa “chọn một bean thắng cuộc”. Với `orderedStream()`, cả bean order 10 và 20 đều tham gia. Ngược lại, `@Primary` hướng tới giải quyết dependency **một bean**; nó không thể thay thế thiết kế pipeline nhiều thành phần.

Nếu nghiệp vụ muốn “chỉ plugin có priority cao nhất được chạy”, hãy viết chính sách **chọn một** (cùng cách xử lý hòa điểm) hoặc cấu hình rõ plugin ID. Không vô tình dùng `orderedStream().findFirst()` như một cách chọn ngầm khi chưa quyết định luật hòa.

## 5. Chính sách khi không có extension và khi bị trùng

### 5.1. Không có extension: no-op hay fallback?

Hai mô hình hợp lệ:

**Mô hình A — no-op:** pipeline là bean lõi, danh sách extension có thể rỗng. Khi rỗng, trả lại input hoặc làm công việc cốt lõi mà không áp dụng plugin. Mô hình này thuận tiện nếu extension là tùy chọn. Ví dụ ở mục 6 dùng mô hình A.

```java
String process(String input) {
    String result = input;
    for (MessageExtension extension : extensions) {
        result = extension.apply(result);
    }
    return result;
}
```

**Mô hình B — fallback bean:** starter đăng ký một implementation mặc định **chỉ khi không có implementation của ứng dụng**:

```java
@AutoConfiguration
class ExtensionFallbackAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageExtension.class)
    MessageExtension defaultMessageExtension() {
        return new DefaultMessageExtension();
    }
}
```

Đây là snippet minh họa; `DefaultMessageExtension` phải được định nghĩa trong dự án thực tế. Trong Spring Boot, `@ConditionalOnMissingBean(MessageExtension.class)` để starter **nhường quyền** khi ứng dụng đã cung cấp extension. Nếu đã có một hoặc nhiều bean `MessageExtension` được biết đến tại thời điểm kiểm tra, bean fallback này không được đăng ký.

**Phân biệt kết quả:** với mô hình A, 0 extension nghĩa là pipeline xử lý 0 plugin. Với mô hình B, khi người dùng không khai báo plugin, context vẫn có **một extension mặc định** sau auto-configuration. Không mô tả fallback như “danh sách vẫn rỗng”.

Các bean condition như `@ConditionalOnMissingBean` xét những bean definition đã được xử lý **tại thời điểm đánh giá**. Spring Boot khuyến nghị đặt chúng trong auto-configuration để xử lý sau bean người dùng; với nhiều auto-config liên quan nhau, hãy khai báo `@AutoConfiguration(after = ...)` khi cần. Nếu fallback phải luôn chạy cùng các plugin khác thì **không** dùng `@ConditionalOnMissingBean(MessageExtension.class)`: hãy định nghĩa fallback như bước xử lý độc lập hoặc một bean luôn hiện diện và quy định thứ tự của nó.

### 5.2. Khi extension bắt buộc

Nếu chức năng không thể hoạt động mà thiếu plugin, fail-fast là hợp lý hơn việc âm thầm bỏ qua:

```java
List<MessageExtension> found =
    provider.orderedStream().toList();

if (found.isEmpty()) {
    throw new IllegalStateException(
        "At least one MessageExtension is required"
    );
}
```

Lỗi nên nêu **loại extension cần thiết, điều kiện để đăng ký và bước khắc phục**, tránh báo một thông điệp khó chẩn đoán như “unexpected null”. Việc chủ động fail nên được thiết kế từ yêu cầu nghiệp vụ; không áp dụng cho điểm mở rộng tùy chọn.

### 5.3. Khi có nhiều extension nhưng chỉ chấp nhận một

Một ứng dụng có thể coi 0 là không kích hoạt, 1 là hợp lệ, N > 1 là lỗi:

```java
List<MessageExtension> found =
    provider.orderedStream().toList();

if (found.size() > 1) {
    throw new IllegalStateException(
        "Expected at most one MessageExtension, found " + found.size()
    );
}

MessageExtension selected = found.isEmpty() ? null : found.get(0);
```

Đây là **kiểm số lượng thật**; khác với `getIfUnique()` vì Spring có thể nhận biết một ứng viên `@Primary` trong nhiều bean. Một hợp đồng cho phép `@Primary` chọn một bean cũng hợp lý, nhưng phải ghi rõ và test riêng.

### 5.4. Phát hiện trùng định danh logic khi chạy N plugin

Hai bean có thể có tên Spring khác nhau nhưng cùng `id()`. Nếu `id()` là khóa duy nhất, hãy kiểm:

```java
Set<String> seen = new HashSet<>();
for (MessageExtension extension : extensions) {
    if (!seen.add(extension.id())) {
        throw new IllegalStateException(
            "Duplicate MessageExtension id: " + extension.id()
        );
    }
}
```

Snippet này cần `import java.util.Set;` và `import java.util.HashSet;` trong một class có biến `extensions`. Việc kiểm **logic ID** tránh xử lý cùng một loại plugin hai lần do hai module cùng đăng ký. Spring có những quy tắc riêng cho **trùng bean name**, nhưng chúng không thay thế kiểm id nghiệp vụ.

Một điểm mở rộng tốt cần quy định cả **tên/ID plugin**, **thứ tự**, **cách xử lý lỗi**, **có cho phép chạy nhiều implementation cùng lúc không**, và **có cần fallback hay không**.

## 6. Ví dụ Java 17+ chạy độc lập: 0, 1 và 2 extension

Ví dụ dùng **Spring Boot 3.3.13**, **Spring Framework 6.1.x**, JDK 17+ và Maven. Nó mô phỏng starter bằng một `@AutoConfiguration` tạo bean `MessagePipeline`. Các extension là bean do “ứng dụng” khai báo trong những lớp `@Configuration` riêng.

Để ba kịch bản độc lập trong cùng một `main`, chương trình dùng `AnnotationConfigApplicationContext` và **chủ động đăng ký lớp cấu hình**. Do đó ví dụ quan sát chính xác cơ chế quản lý bean, `ObjectProvider`, `@Order` và `@ConditionalOnMissingBean` mà không cần khởi động web server. Khi triển khai starter thật, `@AutoConfiguration` phải được nhập qua `AutoConfiguration.imports` (hướng dẫn ở mục 7), không được dựa vào component scanning của starter.

### 6.1. Cấu trúc

```text
extension-cases-demo/
├── pom.xml
└── src/main/java/demo/ExtensionCasesDemo.java
```

### 6.2. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>extension-cases-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. File `src/main/java/demo/ExtensionCasesDemo.java`

```java
package demo;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

public final class ExtensionCasesDemo {

    // Hợp đồng extension: có ID và phép biến đổi văn bản.
    interface MessageExtension {
        String id();
        String apply(String input);
    }

    static final class PrefixExtension implements MessageExtension {
        @Override
        public String id() {
            return "prefix";
        }

        @Override
        public String apply(String input) {
            return "[A:" + input + "]";
        }
    }

    static final class SuffixExtension implements MessageExtension {
        @Override
        public String id() {
            return "suffix";
        }

        @Override
        public String apply(String input) {
            return input + "|B";
        }
    }

    static final class MessagePipeline {
        private final List<MessageExtension> extensions;

        MessagePipeline(List<MessageExtension> extensions) {
            this.extensions = List.copyOf(extensions);

            // Kiểm duy nhất theo ID nghiệp vụ, không chỉ tên bean.
            Set<String> ids = new HashSet<>();
            for (MessageExtension extension : this.extensions) {
                if (!ids.add(extension.id())) {
                    throw new IllegalStateException(
                        "Duplicate extension id: " + extension.id()
                    );
                }
            }
        }

        int extensionCount() {
            return extensions.size();
        }

        String process(String input) {
            String result = input;
            for (MessageExtension extension : extensions) {
                result = extension.apply(result);
            }
            return result;
        }
    }

    // Mô phỏng auto-configuration của một starter.
    @AutoConfiguration
    static class PipelineAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(MessagePipeline.class)
        MessagePipeline messagePipeline(
            ObjectProvider<MessageExtension> provider
        ) {
            return new MessagePipeline(
                provider.orderedStream().toList()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrefixConfiguration {
        @Bean("prefixExtension")
        @Order(10)
        MessageExtension prefixExtension() {
            return new PrefixExtension();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SuffixConfiguration {
        @Bean("suffixExtension")
        @Order(20)
        MessageExtension suffixExtension() {
            return new SuffixExtension();
        }
    }

    static void runCase(
        String label,
        Class<?>... extensionConfigurations
    ) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            // Đăng ký lớp auto-configuration tường minh
            // để mỗi ví dụ dùng một context cô lập.
            context.register(PipelineAutoConfiguration.class);

            if (extensionConfigurations.length > 0) {
                context.register(extensionConfigurations);
            }
            context.refresh();

            MessagePipeline pipeline =
                context.getBean(MessagePipeline.class);

            System.out.printf(
                "%s: extensions=%d, output=%s%n",
                label,
                pipeline.extensionCount(),
                pipeline.process("message")
            );
        }
    }

    public static void main(String[] args) {
        runCase("none");
        runCase("one", PrefixConfiguration.class);

        // Cố ý đăng ký Suffix trước Prefix.
        // @Order + orderedStream đảm bảo Prefix chạy trước.
        runCase(
            "many",
            SuffixConfiguration.class,
            PrefixConfiguration.class
        );
    }
}
```

### 6.4. Chạy và giải thích output

Cần JDK 17+, Maven 3.8+ và khả năng lấy dependency. Tại thư mục `extension-cases-demo` chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ExtensionCasesDemo
```

Ba dòng **do chương trình tự in** (không tính thông báo Maven nếu môi trường có thêm):

```text
none: extensions=0, output=message
one: extensions=1, output=[A:message]
many: extensions=2, output=[A:message]|B
```

**Kịch bản none:** chỉ có `PipelineAutoConfiguration`. Bean `MessagePipeline` được đăng ký; `ObjectProvider<MessageExtension>.orderedStream()` rỗng; vòng lặp không chạy, nên `process("message")` giữ nguyên đầu vào. Đây là chính sách **no-op hợp lệ** khi không có extension.

**Kịch bản one:** thêm bean `prefixExtension`. Provider tìm được một `MessageExtension`; pipeline chạy `PrefixExtension` và trả `[A:message]`. Không cần chọn một bean theo tên vì hợp đồng pipeline là “chạy tất cả extension hiện có”.

**Kịch bản many:** hai bean được đăng ký từ hai lớp cấu hình. Mặc dù mã gọi `runCase` truyền `SuffixConfiguration.class` **trước** `PrefixConfiguration.class`, provider được yêu cầu `orderedStream()` và các phương thức `@Bean` có `@Order(10)` và `@Order(20)`; extension prefix chạy trước, suffix chạy sau. Kết quả là `[A:message]|B`, không phải `[A:message|B]`.

**Kiểm soát lỗi trùng:** constructor `MessagePipeline` kiểm `id()`. Nếu có hai extension cùng trả `"prefix"`, quá trình tạo pipeline ném `IllegalStateException("Duplicate extension id: prefix")`, khiến context không khởi tạo thành công. Đó là chính sách fail-fast có chủ đích, khác với việc lấy đại một plugin.

**Vai trò `@ConditionalOnMissingBean` ở ví dụ:** annotation chỉ áp dụng lên bean **pipeline**, để người dùng có thể tự khai báo pipeline thay thế. Nó **không** ngăn người dùng khai báo nhiều `MessageExtension`; vì vậy luồng zero/one/many vẫn hoạt động. Nếu đặt `@ConditionalOnBean(MessageExtension.class)` lên cả cấu hình pipeline thì kịch bản none sẽ không còn tạo pipeline, trái với yêu cầu no-op.

Chương trình đăng ký `PipelineAutoConfiguration` trực tiếp để tách bạch ba trường hợp; trong starter thực tế Spring Boot tự nạp auto-configuration từ imports file. Các quy tắc thứ tự extension vẫn giống nhau.

## 7. Áp dụng trong một starter Spring Boot thực tế

Một thiết kế phổ biến:

```text
my-library-autoconfigure/
├── src/main/java/com/acme/lib/
│   ├── MessageExtension.java
│   ├── MessagePipeline.java
│   └── MessagePipelineAutoConfiguration.java
└── src/main/resources/META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports

my-application/
└── src/main/java/com/example/app/
    ├── MyExtensionConfiguration.java
    └── ...
```

Ở module autoconfigure, file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` liệt kê FQCN:

```text
com.acme.lib.MessagePipelineAutoConfiguration
```

Auto-configuration cung cấp **bean pipeline**:

```java
@AutoConfiguration
public class MessagePipelineAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessagePipeline.class)
    MessagePipeline messagePipeline(
        ObjectProvider<MessageExtension> extensions
    ) {
        return new MessagePipeline(
            extensions.orderedStream().toList()
        );
    }
}
```

Đây là **snippet minh họa**, giả định `MessagePipeline` và `MessageExtension` đã được định nghĩa trong module thư viện. Người sử dụng cung cấp extension bằng `@Bean`/`@Component` của ứng dụng:

```java
@Configuration(proxyBeanMethods = false)
class MyExtensionConfiguration {

    @Bean
    @Order(100)
    MessageExtension sanitizeExtension() {
        return new SanitizeExtension();
    }
}
```

`SanitizeExtension` là kiểu giả định của ứng dụng; snippet không là file Java độc lập.

**Điểm quan trọng:** starter không nên dùng `@ComponentScan` để tự quét package ứng dụng, cũng không nên buộc ứng dụng phải import thủ công lớp auto-configuration. Spring Boot 3.3 yêu cầu khai báo auto-configuration trong imports file. Extension của ứng dụng được đăng ký theo quy trình bean configuration thông thường; sau đó provider lấy các candidate.

### 7.1. Back off của pipeline và fallback của extension là hai điều khác nhau

- `@ConditionalOnMissingBean(MessagePipeline.class)`: cho phép **thay thế toàn bộ pipeline** do starter cung cấp.
- `@ConditionalOnMissingBean(MessageExtension.class)`: cho phép **cung cấp một implementation mặc định** khi chưa có extension nào.

Không hoán đổi hai kiểu condition này vì chúng nhắm tới **hai loại bean khác nhau**. Nếu ứng dụng muốn tự tùy biến *pipeline* nhưng vẫn dùng các extension đăng ký tự động, hãy cho phép bean pipeline do ứng dụng cung cấp thay thế theo điều kiện thứ nhất. Nếu muốn pipeline mặc định cộng với tất cả extension, giữ pipeline luôn đăng ký theo điều kiện thiếu pipeline và **không bắt buộc** phải có extension.

### 7.2. Tính ổn định khi module thay đổi

Thêm dependency mới có thể bổ sung một bean `MessageExtension`. Nếu pipeline mặc định chạy **tất cả** extension, kết quả của ứng dụng sẽ thay đổi theo đúng hợp đồng đó. Vì thế:

- Định nghĩa định danh plugin và mặc định enable/disable rõ ràng.
- Quy định thứ tự ưu tiên và trường hợp cùng order.
- Xác định liệu một plugin có được chạy nhiều lần, có id trùng, hoặc có thể thay thế plugin khác.
- Nếu extension chạm dữ liệu nhạy cảm/IO, giải thích rõ tác dụng phụ và xử lý exception.
- Trong logging, nêu tên/id extension và reason khi không chạy, tránh tự in payload nhạy cảm.
- Kiểm tra tính tương thích khi nâng starter, vì có thêm extension mới có thể đổi đầu ra mà không cần sửa cấu hình ứng dụng.

Đừng dùng `@Primary` để giả định danh sách sẽ tự co lại còn một phần tử. Nếu thư viện buộc chỉ có một chiến lược, hãy dùng injection có qualifier/chính sách chọn riêng và viết test cho tình huống có từ hai bean trở lên.

## 8. Kiểm thử ba trường hợp và điều kiện lỗi

Bộ kiểm thử cơ bản của một extension point phải có **ít nhất** ba kịch bản:

| Kịch bản | Setup | Kết quả cần xác minh |
| --- | --- | --- |
| **0** | Không đăng ký `MessageExtension` | Pipeline vẫn được tạo nếu chính sách no-op; output không đổi, hoặc fallback được tạo nếu policy đã chọn fallback |
| **1** | Một bean `PrefixExtension` | Extension chạy đúng một lần; không cần có `@Primary` |
| **2+** | Hai bean cùng interface, đăng ký ngược thứ tự ưu tiên | Chạy đúng số lần và **đúng thứ tự**; không bỏ sót bean |
| **Trùng ID** | Hai bean tên khác nhau nhưng cùng `id()` | Context thất bại với thông tin duplicate, nếu hợp đồng yêu cầu ID duy nhất |
| **Thay thế pipeline** | Người dùng cung cấp `@Bean MessagePipeline` | `@ConditionalOnMissingBean(MessagePipeline.class)` khiến pipeline mặc định back off; không sinh hai pipeline |
| **Plugin lỗi** | Một extension ném exception | Tuân theo policy: fail-fast hoặc cô lập lỗi và tiếp tục; hành vi phải được kiểm chứng |

Spring Boot cung cấp `ApplicationContextRunner` để viết test auto-configuration theo những tổ hợp bean, property, classpath khác nhau. Ví dụ dưới đây là **snippet định hướng** cho bài kiểm thử (cần class, imports và dependency test thực tế):

```java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(MessagePipelineAutoConfiguration.class)
    )
    .withUserConfiguration(MyExtensionConfiguration.class)
    .run(context -> {
        MessagePipeline pipeline = context.getBean(MessagePipeline.class);
        // assert số plugin, thứ tự và output theo hợp đồng.
    });
```

Mẫu trên giả định đã import `ApplicationContextRunner`, `AutoConfigurations` và các lớp thực tế của dự án; test runner lấy từ `spring-boot-test` (thường qua `spring-boot-starter-test`). Chú ý: đoạn này chỉ minh họa setup, không được quảng bá là một test hoàn chỉnh khi chưa có assertions.

**Kiểm thử ngược thứ tự:** cố tình đăng ký bean có `@Order(20)` trước bean `@Order(10)` (như mục 6), sau đó yêu cầu kết quả phù hợp với 10 → 20. Kiểm tra cả trường hợp thêm plugin thứ ba hoặc thay đổi một thứ tự để bảo đảm pipeline không dựa vào vị trí source code.

**Kiểm thử bean người dùng:** trong auto-configuration, condition thiếu bean có thể bị ảnh hưởng bởi thứ tự bean definition đã xử lý. Spring Boot khuyến nghị chỉ sử dụng bean conditions trong các auto-configuration, và sắp xếp bằng `@AutoConfiguration(after = ...)` khi phụ thuộc auto-configuration khác. Đừng đánh giá điều kiện tồn tại từ một class đơn thuần đang có trên classpath: phải có bean definition được đăng ký.

## 9. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Inject duy nhất `MessageExtension` nhưng cho phép nhiều plugin | Có thể gặp lỗi nhập nhằng dependency khi plugin thứ hai xuất hiện | Dùng `ObjectProvider<MessageExtension>.orderedStream()` nếu muốn chạy tất cả |
| Dùng `Optional<MessageExtension>` để xử lý 0/1/N | `Optional` chỉ biểu diễn một giá trị hoặc vắng mặt, không chứa nhiều implementation | Nếu nhiều plugin hợp lệ, dùng danh sách/stream |
| Dùng `getIfUnique() == null` để kết luận “không có plugin” | Nhiều plugin nhập nhằng cũng có thể trả `null` | Đếm stream nếu cần phân biệt 0 và N |
| Cho rằng `@Primary` làm các plugin khác biến mất | `@Primary` chỉ giúp chọn một dependency trong trường hợp thích hợp | Với pipeline nhiều bước, lấy mọi candidate bằng `orderedStream()` |
| Tin vào thứ tự khai báo/scan thay cho `@Order` | Kết quả pipeline có thể đổi khi refactor/thêm module | Khai báo order hoặc comparator có hợp đồng rõ ràng |
| Gắn `@ConditionalOnBean(MessageExtension.class)` lên cả pipeline hỗ trợ no-op | Khi 0 plugin, pipeline biến mất dù tính năng nên vẫn có | Tạo pipeline độc lập, nhận provider rỗng |
| Dùng `@ConditionalOnMissingBean(MessagePipeline.class)` và nghĩ nó tạo fallback plugin | Nó chỉ kiểm bean `MessagePipeline` | Dùng condition nhắm đúng kiểu extension nếu cần fallback |
| Dùng cùng bean name/ID rồi cho rằng Spring luôn hợp nhất hợp lệ | Có thể lỗi trùng tên bean, hoặc trùng logic ID giữa tên khác nhau | Định nghĩa chính sách trùng và kiểm logic ID riêng |
| Bỏ qua lỗi plugin hoặc nuốt exception không log | Khó phát hiện xử lý thiếu và dữ liệu sai | Chọn fail-fast hoặc isolation có kiểm soát và thông báo lỗi có ngữ cảnh |
| Tưởng `@Order` quyết định thời điểm bean khởi tạo | Đây là quy tắc sắp xếp collection/extension, không là quan hệ dependency khởi tạo | Dùng injection/`@DependsOn` cho lifecycle |
| Nhầm classpath có interface với có bean implementation | Class tồn tại không có nghĩa bean đã được đăng ký | Kiểm bean candidates và condition report |
| Kết quả chạy khác khi có nhiều BeanFactory/context cha–con | Provider ở từng context/qualifier có tập ứng viên khác | Xác định context và qualifier, test đúng môi trường |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một starter cung cấp `MessagePipeline`, nhưng ứng dụng không khai báo `MessageExtension` nào. `provider.orderedStream().toList()` trả gì?  
**Đáp án:** Danh sách rỗng. Nếu pipeline chọn no-op, nó trả kết quả không đổi; không cần bean extension giả để tồn tại.

**Câu 2.** Có hai bean cùng interface, một bean `@Order(100)` và một bean `@Order(10)`. Dùng `orderedStream()` có còn cả hai không?  
**Đáp án:** Có, nếu cả hai là candidate phù hợp. Bean order 10 được đưa ra trước bean order 100; `@Order` không tự lọc bớt bean.

**Câu 3.** Có hai extension tên bean lần lượt là `firstPlugin` và `secondPlugin`, cả hai `id()` đều trả `"pricing"`. Chỉ kiểm trùng tên bean có đủ không?  
**Đáp án:** Không. Hai bean tên khác nhau vẫn trùng định danh logic `"pricing"`, nên cần kiểm `id()` nếu hợp đồng yêu cầu duy nhất.

**Câu 4.** Có hai implementation với một bean `@Primary`. `provider.getIfUnique()` trả về bean thì có thể khẳng định chỉ có đúng một extension không?  
**Đáp án:** Không. Spring có thể phân giải một ứng viên primary từ nhiều bean; muốn kiểm cardinality phải đếm.

**Câu 5.** Một pipeline có thể chạy nhiều plugin nhưng lại có `@ConditionalOnBean(MessageExtension.class)` ngay trên cấu hình pipeline. Chuyện gì xảy ra khi không có plugin?  
**Đáp án:** Condition không khớp nên pipeline có thể không được đăng ký. Nếu hợp đồng muốn zero-extension no-op, phải bỏ điều kiện bắt buộc đó.

**Câu 6.** `@ConditionalOnMissingBean(MessageExtension.class)` trên bean fallback có tự động đăng ký fallback khi ứng dụng đã có một extension khác không?  
**Đáp án:** Không, nếu bean đã được biết đến lúc xét condition, fallback nhường quyền. Phải đặt condition trong auto-configuration và xem xét thứ tự xử lý các bean definition.

**Câu 7.** Plugin A thêm `[A:...]`, plugin B thêm `|B`. Cần output `[A:message]|B` cho mọi lần chạy. Thiết kế gì?  
**Đáp án:** Yêu cầu A chạy trước B, ví dụ khai báo `@Order(10)` cho A và `@Order(20)` cho B, sử dụng `orderedStream()` thay vì thứ tự đăng ký ngẫu nhiên.

**Câu 8.** Nếu N plugin đều hợp lệ nhưng nghiệp vụ chỉ cho chạy một plugin, nên áp dụng tất cả qua stream không?  
**Đáp án:** Không. Hãy xác định quy tắc chọn như plugin ID/`@Qualifier`/`@Primary` hoặc báo lỗi nhiều ứng viên; hành vi phải được ghi rõ trong hợp đồng.

## 11. Ghi nhớ và tài liệu tham khảo

- **0 / 1 / N là ba trường hợp riêng:** chọn hành vi **trước** khi viết auto-configuration.
- Với extension dạng danh sách, `ObjectProvider<T>.orderedStream()` xử lý tốt cả **0, 1 và N**, giữ được trình tự của `@Order`/`Ordered` khi cần.
- Với extension dạng chiến lược duy nhất, không đánh đồng `getIfUnique()` với “chỉ có một bean”; `@Primary` có thể chọn được một ứng viên trong nhiều bean.
- `@ConditionalOnMissingBean(Pipeline.class)` giúp người dùng thay thế pipeline; `@ConditionalOnMissingBean(Extension.class)` giúp đăng ký một fallback khi thiếu extension. Hai điều kiện có mục đích khác nhau.
- Dùng kiểm trùng **logic ID**, quy tắc order và lỗi plugin để tránh hành vi không xác định khi cài thêm module.
- Starter thật cần khai báo auto-configuration trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; các extension do ứng dụng đăng ký thành Spring bean.

Tham khảo tài liệu chính thức cho **Spring Boot 3.3 / Spring Framework 6.1**:

1. [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html), phần *Bean Conditions* và *Testing Your Auto-configuration*.
2. [Spring Framework 6.1 — ObjectProvider Javadoc](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/beans/factory/ObjectProvider.html), các phương thức `getIfAvailable()`, `getIfUnique()` và `orderedStream()`.
3. [Spring Framework 6.1 — @Order Javadoc](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/core/annotation/Order.html), thứ tự component và quan hệ với injection.
4. [Spring Boot 3.3 — @ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).
5. [Spring Boot 3.3 — @ConditionalOnSingleCandidate Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html), khi cần một candidate cho injection (không đồng nghĩa đúng một bean).
