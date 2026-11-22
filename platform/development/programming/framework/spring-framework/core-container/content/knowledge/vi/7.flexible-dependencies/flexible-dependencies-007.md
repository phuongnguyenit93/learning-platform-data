# Duyệt nhiều ứng viên bằng stream và orderedStream trong Spring Core Container

## Mục tiêu

Khi ứng dụng có nhiều bean triển khai cùng một interface — ví dụ nhiều bước kiểm tra, bộ chuyển đổi, handler, plugin hoặc chiến lược nghiệp vụ — đôi khi ta muốn **lấy tất cả các bean tương thích rồi duyệt qua chúng**. Spring Core Container hỗ trợ cách làm này thông qua `org.springframework.beans.factory.ObjectProvider<T>`:

- `provider.stream()` cung cấp một Java `Stream<T>` tuần tự gồm các bean phù hợp, **không có cam kết thứ tự**.
- `provider.orderedStream()` cung cấp một Java `Stream<T>` tuần tự gồm các bean phù hợp đã được **Spring sắp xếp theo bộ so sánh thứ tự bean**.

Hai phương thức trên thuộc cơ chế IoC/Dependency Injection của Spring, **không phải reactive stream** như Reactor `Flux`, stream dữ liệu qua HTTP hay Java virtual thread. Kết quả cuối cùng là một `java.util.stream.Stream` thông thường, dùng các thao tác Java như `map`, `filter`, `forEach`, `findFirst` và `toList`.

Bài này hướng dẫn cách tiêm provider, kiểm soát thứ tự bằng `@Order`/`Ordered`, kết hợp `@Qualifier` và generic, phân biệt trường hợp 0–n bean, hiểu lazy/scope, tránh lỗi nghiệp vụ và thực hành bằng chương trình Java 17 chạy được.

## 1. Từ một dependency đến nhiều ứng viên

Giả sử ứng dụng có ba bean triển khai interface sau:

```java
interface Rule {
    String name();
}
```

Ba bean có thể thực hiện kiểm tra đầu vào, bổ sung thông tin, hoặc ghi dữ liệu phân tích. Nếu consumer khai báo duy nhất `Rule rule`, Spring phải tìm **một** ứng viên; khi có nhiều bean mà không chọn được một cách rõ ràng, ứng dụng có thể lỗi `NoUniqueBeanDefinitionException`.

Nếu muốn xử lý **tất cả** các ứng viên, có các lựa chọn:

| Cách nhận dependency | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `Rule rule` | Chọn một bean `Rule` | Phải có đúng một strategy hoặc chiến lược đã được chọn rõ |
| `List<Rule> rules` | Collection các bean phù hợp được tiêm khi tạo consumer | Pipeline cố định, tập thành phần được xác định tại thời điểm khởi tạo |
| `ObjectProvider<Rule> provider` | Giữ khả năng tra cứu bean khi cần | Lookup linh hoạt, truy vấn tại thời điểm xử lý |
| `provider.stream()` | Lấy nhiều bean phù hợp, không cam kết thứ tự | Kiểm tra membership, thống kê, tác vụ độc lập thứ tự |
| `provider.orderedStream()` | Lấy nhiều bean phù hợp theo thứ tự Spring | Pipeline, chuỗi kiểm tra hoặc callback có mức ưu tiên |

Ví dụ ý tưởng với provider:

```java
// Đoạn minh họa trong một bean do Spring quản lý.
private final ObjectProvider<Rule> rules;

Pipeline(ObjectProvider<Rule> rules) {
    this.rules = rules;
}

void execute() {
    rules.orderedStream().forEach(rule -> runRule(rule));
}
```

Trong đoạn minh họa, `runRule` là method do ứng dụng tự xây; import provider bằng:

```java
import org.springframework.beans.factory.ObjectProvider;
```

Một `ObjectProvider<T>` có thể được Spring tiêm **ngay cả khi không tồn tại bean `T` nào**. Sự vắng mặt của ứng viên lúc duyệt sẽ tạo **stream rỗng**, thay vì một collection `null`.

## 2. Khác biệt chính xác giữa `stream()` và `orderedStream()`

### `stream()` không cam kết thứ tự

```java
provider.stream()
        .map(Rule::name)
        .forEach(System.out::println);
```

Provider trả một stream tuần tự gồm các instance bean phù hợp. Theo hợp đồng Spring, thứ tự của `stream()` **không được bảo đảm**; trong một số ứng dụng bạn có thể thấy thứ tự tương tự thứ tự đăng ký bean, nhưng đó không phải căn cứ để thiết kế nghiệp vụ.

Nếu chỉ muốn kiểm kê bean theo tên, có thể tự sắp xếp kết quả:

```java
List<String> names = provider.stream()
        .map(Rule::name)
        .sorted()
        .toList();
```

Ở đây `sorted()` là phép sắp xếp **theo tên do ứng dụng lựa chọn**, không phải sắp xếp theo `@Order` của Spring. Method `Stream.toList()` có từ Java 16, nên chạy được trên Java 17.

### `orderedStream()` tuân theo thứ tự Spring

```java
provider.orderedStream()
        .forEach(rule -> runRule(rule));
```

Spring dùng *common order comparator* của bean factory để sắp xếp các bean trong stream. Với cấu hình annotation thông thường, các chỉ dẫn quan trọng là:

- `org.springframework.core.Ordered` — đối tượng có thể cung cấp số thứ tự qua `getOrder()`.
- `org.springframework.core.annotation.Order` — khai báo mức ưu tiên trên class bean hoặc phương thức `@Bean`.
- `jakarta.annotation.Priority` — annotation chuẩn trên class được Spring nhận diện trong cơ chế sắp thứ tự.

**Số order nhỏ hơn được xếp trước.** Ví dụ `@Order(10)` được ưu tiên trước `@Order(30)`. Hai bean cùng số order hoặc không khai báo order không tạo một hợp đồng nghiệp vụ chắc chắn về thứ tự tương đối; nếu hai bước phải chạy trước–sau, hãy gán ưu tiên rõ ràng hoặc tự xây comparator có khóa phụ.

`@Order` là thứ tự **khi lấy nhiều bean theo cơ chế sắp xếp**, không phải lệnh buộc Spring khởi tạo bean có số nhỏ trước bean có số lớn. Thời điểm khởi tạo phụ thuộc quan hệ dependency và vòng đời Spring.

### So sánh trong một ví dụ

Giả sử:

| Bean | Giá trị `Rule.name()` | Order |
| --- | --- | --- |
| `validationRule` | `validate` | 30 |
| `enrichmentRule` | `enrich` | 10 |
| `analyticsRule` | `analytics` | 20 |

Khi dùng `stream().map(Rule::name).sorted().toList()`, kết quả là `[analytics, enrich, validate]` vì được sắp theo **tên**.

Khi dùng `orderedStream().map(Rule::name).toList()`, kết quả là `[enrich, analytics, validate]` vì được sắp theo **10, 20, 30**.

Không nên dùng kết quả thứ nhất làm bằng chứng về thứ tự gốc của `stream()`; chính phép `sorted()` đã tạo ra thứ tự có thể dự đoán.

## 3. Ví dụ đầy đủ có thể biên dịch và chạy

Chương trình sau dùng Spring Framework thuần, Java 17 và Maven. Nó minh họa cả hai API, `@Qualifier` lọc nhiều bean, `@Primary` chọn một bean và provider không có ứng viên.

### 3.1. Cấu trúc dự án

```text
provider-stream-demo/
├── pom.xml
└── src/main/java/demo/ProviderStreamDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>provider-stream-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/demo/ProviderStreamDemo.java`:

```java
package demo;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

public class ProviderStreamDemo {

    interface Rule {
        String name();
    }

    record NamedRule(String name) implements Rule {
    }

    static final class ReportService {
        private final ObjectProvider<Rule> all;
        private final ObjectProvider<Rule> mandatory;
        private final ObjectProvider<Rule> missing;
        private final Rule preferred;

        ReportService(ObjectProvider<Rule> all,
                      ObjectProvider<Rule> mandatory,
                      ObjectProvider<Rule> missing,
                      Rule preferred) {
            this.all = all;
            this.mandatory = mandatory;
            this.missing = missing;
            this.preferred = preferred;
        }

        void printReport() {
            // Sắp THEO TÊN để output ổn định, không dựa vào
            // thứ tự mặc định của ObjectProvider.stream().
            System.out.println("all.byName=" +
                    all.stream().map(Rule::name).sorted().toList());

            // Thứ tự do Spring quyết định theo @Order.
            System.out.println("all.bySpringOrder=" +
                    all.orderedStream().map(Rule::name).toList());

            // Chỉ lấy những Rule có qualifier "mandatory".
            System.out.println("mandatory.bySpringOrder=" +
                    mandatory.orderedStream().map(Rule::name).toList());

            // Không có ứng viên: stream rỗng.
            System.out.println("missing.size=" +
                    missing.stream().toList().size());

            // Chọn một bean dùng @Primary.
            System.out.println("single.preferred=" + preferred.name());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean("validationRule")
        @Order(30)
        @Qualifier("mandatory")
        Rule validationRule() {
            return new NamedRule("validate");
        }

        @Bean("enrichmentRule")
        @Order(10)
        @Qualifier("mandatory")
        Rule enrichmentRule() {
            return new NamedRule("enrich");
        }

        @Bean("analyticsRule")
        @Order(20)
        @Primary
        @Qualifier("metrics")
        Rule analyticsRule() {
            return new NamedRule("analytics");
        }

        @Bean
        ReportService reportService(
                ObjectProvider<Rule> all,
                @Qualifier("mandatory") ObjectProvider<Rule> mandatory,
                @Qualifier("notRegistered") ObjectProvider<Rule> missing,
                Rule preferred) {
            return new ReportService(all, mandatory, missing, preferred);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(ReportService.class).printReport();
        }
    }
}
```

Mở terminal tại thư mục `provider-stream-demo` và chạy (yêu cầu JDK 17+ và Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ProviderStreamDemo
```

Các dòng **chương trình tự in ra** (không tính thông điệp logging do môi trường Maven hoặc Spring thêm vào):

```text
all.byName=[analytics, enrich, validate]
all.bySpringOrder=[enrich, analytics, validate]
mandatory.bySpringOrder=[enrich, validate]
missing.size=0
single.preferred=analytics
```

### 3.2. Giải thích từng kết quả

**`all.byName`:** `ObjectProvider<Rule> all` tìm cả ba bean `Rule`. Sau khi gọi `map(Rule::name).sorted()`, chúng được sắp theo thứ tự từ điển thành `analytics, enrich, validate`. Lời gọi `sorted()` là điều kiện cần để output này xác định.

**`all.bySpringOrder`:** `orderedStream()` dùng thứ tự đã khai báo. `enrichmentRule` có `@Order(10)`, `analyticsRule` có `@Order(20)`, và `validationRule` có `@Order(30)`. Vì vậy danh sách là `enrich, analytics, validate`.

**`mandatory.bySpringOrder`:** tham số `ObjectProvider<Rule> mandatory` mang `@Qualifier("mandatory")`. Spring chỉ chọn `enrichmentRule` và `validationRule`, sau đó sắp theo `10` rồi `30`. Một qualifier có thể được gắn cho **nhiều bean** cùng lúc.

**`missing.size`:** không có bean `Rule` với qualifier `notRegistered`. Spring vẫn inject được `ObjectProvider<Rule>`, và `stream()` cho một stream rỗng, nên kích thước bằng 0.

**`single.preferred`:** Spring cần chọn **một** `Rule` cho tham số `Rule preferred`, vì vậy `@Primary` của `analyticsRule` được áp dụng. Nhưng `@Primary` không loại các bean khác khỏi `all.stream()` hoặc `all.orderedStream()`.

### 3.3. Kiểm tra khi thay order

Hãy đổi `@Order(30)` trên `validationRule` thành `@Order(5)` rồi chạy lại:

- `all.byName` vẫn là `[analytics, enrich, validate]` vì vẫn sắp theo tên.
- `all.bySpringOrder` thành `[validate, enrich, analytics]` vì `5` đứng trước `10` và `20`.
- `mandatory.bySpringOrder` thành `[validate, enrich]`.
- `missing.size` và `single.preferred` không đổi.

Thử nghiệm này tách rõ **thứ tự trong Java Stream tự tạo** với **thứ tự BeanFactory của Spring**.

## 4. Thứ tự và lựa chọn ứng viên khi duyệt stream

`orderedStream()` dùng quy tắc order của Spring: giá trị nhỏ hơn được xếp trước. `Ordered#getOrder()` lấy giá trị từ instance, `@Order` khai báo trên class hoặc phương thức `@Bean`, còn `jakarta.annotation.Priority` áp dụng ở class. Khi hai bean cùng order, ứng dụng không nên giả định thứ tự tương đối luôn ổn định; pipeline bắt buộc trước–sau cần order riêng hoặc comparator rõ ràng.

Điểm cần kiểm tra khi dùng **provider stream** là metadata đi theo **bean definition**. Chẳng hạn `@Order(5)` trên phương thức `@Bean` có thể được Spring dùng khi `orderedStream()` sắp xếp, dù class của object được trả về không có annotation. Nếu lấy những object đó rồi tự gọi một comparator bên ngoài BeanFactory, metadata của factory method có thể không còn sẵn. Vì vậy hãy kiểm thử thứ tự tại chính điểm sử dụng provider.

| Cơ chế | Ảnh hưởng khi lấy stream bean |
| --- | --- |
| `@Qualifier` và kiểu generic ở injection point | Thu hẹp **ứng viên** trước khi duyệt |
| `@Order`, `Ordered`, `@Priority` | Sắp thứ tự **trong `orderedStream()`** |
| `@Primary` | Ưu tiên khi chọn **một bean**; không tự xóa phần tử khỏi stream |
| `@DependsOn` | Điều khiển quan hệ khởi tạo, không phải thứ tự duyệt |

`@Order` trên `@Configuration` không tự truyền xuống mọi `@Bean` bên trong. Bài về thứ tự collection đã giải thích chi tiết `PriorityOrdered`, thứ tự tie và factory method; tại đây chỉ cần biết các quy tắc ấy quyết định kết quả **`orderedStream()`**, còn `stream()` không cam kết thứ tự.

## 5. Lọc nhiều bean theo `@Qualifier` và generic

### 5.1. `@Qualifier` trên injection point của provider

Spring có thể xét qualifier khi tạo provider tại injection point:

```java
// Đoạn minh họa trong class Spring-managed:
private final ObjectProvider<Rule> mandatoryRules;

MyService(@Qualifier("mandatory") ObjectProvider<Rule> mandatoryRules) {
    this.mandatoryRules = mandatoryRules;
}
```

Khi sau đó gọi `mandatoryRules.stream()`/`orderedStream()`, tập ứng viên đã chịu điều kiện lọc tương ứng. Thực tế một qualifier như `mandatory` có thể gắn lên **hai hoặc nhiều bean**. Không nên dùng qualifier như một "lệnh chọn duy nhất" nếu ứng dụng cần một nhóm.

Có thể đặt qualifier trên bean đăng ký bằng `@Bean` hoặc `@Component`. Bean name cũng được dùng trong một số điều kiện chọn ứng viên, nhưng **tên bean** và **qualifier nghiệp vụ** là hai khái niệm nên thể hiện rõ trong thiết kế.

### 5.2. Generic type giúp thu hẹp ứng viên

Spring có thể dùng generic type của bean và injection point như một tiêu chí tìm ứng viên. Ví dụ:

```java
// Đoạn minh họa, cần đặt trong cấu hình/bean đầy đủ.
interface Decoder<T> {
    T decode(byte[] input);
}

@Bean
Decoder<String> stringDecoder() {
    return input -> new String(input,
            java.nio.charset.StandardCharsets.UTF_8);
}

@Bean
Decoder<byte[]> bytesDecoder() {
    return input -> input.clone();
}

// Trong constructor một bean khác:
DecoderRegistry(ObjectProvider<Decoder<String>> stringDecoders) {
    this.stringDecoders = stringDecoders;
}
```

Đây là minh họa để đưa vào cấu hình phù hợp, không phải chương trình độc lập. `ObjectProvider<Decoder<String>>` có thể chọn các bean với metadata generic phù hợp kiểu `Decoder<String>`. Kết quả phụ thuộc Spring có đủ thông tin generic ở bean definition; khai báo `@Bean` trả raw `Decoder` làm mất thông tin quan trọng.

Nếu mã dùng `ObjectProvider<Object>`, tức là nó tìm một tập bean rất rộng và khó kiểm soát. Nên dùng interface hẹp, generic rõ ràng và qualifier có nghĩa nghiệp vụ.

### 5.3. Không tự nhầm lọc kiểu với lọc instance

`@Qualifier` và generic có thể ảnh hưởng **tập bean candidate** trước khi lấy stream. Trong khi đó, `provider.stream().filter(rule -> ...)` là phép Java Stream xử lý **đối tượng bean đã được lấy**. Đối với bean có khởi tạo tốn kém, sự khác nhau này có ý nghĩa: filter sau khi lấy bean không có tác dụng ngăn Spring tạo bean đó khi cần.

## 6. Không có bean, có một bean và có nhiều bean

`ObjectProvider<T>` phục vụ cả lookup đơn lẻ lẫn duyệt nhiều bean. Hãy phân biệt kết quả của từng API:

| Tập ứng viên phù hợp | `stream()` | `orderedStream()` | `getObject()` / `getIfAvailable()` |
| --- | --- | --- | --- |
| Không có bean nào | Stream rỗng | Stream rỗng | `getObject()` thường lỗi thiếu bean; `getIfAvailable()` trả `null` |
| Có một bean | Một phần tử | Một phần tử | Trả bean đó |
| Có nhiều bean | Nhiều phần tử | Nhiều phần tử theo Spring order | Phải phân giải ứng viên đơn lẻ; có thể lỗi nhập nhằng |

Khi có nhiều ứng viên, `stream()` **không mặc định chọn một trong số chúng**. Đó là lý do truy vấn stream thường đúng hơn gọi `getObject()` trong hệ thống plugin nhiều implementation.

Ví dụ kiểm tra không có ứng viên:

```java
// Minh họa trong class đã có ObjectProvider<Rule> rules.
if (rules.stream().findAny().isEmpty()) {
    System.out.println("No matching Rule beans");
}
```

Nếu có bean phù hợp nhưng nó ném exception trong constructor hoặc `@Bean` factory method, thao tác tiêu thụ stream **vẫn có thể ném lỗi tạo bean**. Đừng bắt mọi exception rồi coi như "không có rule": tập ứng viên rỗng là một trạng thái hợp lệ, còn bean tạo lỗi là sự cố cấu hình/chạy chương trình.

Lưu ý `getIfAvailable()` xử lý thiếu dependency, nhưng **không có nghĩa chắc chắn không gặp lỗi nhập nhằng** khi có nhiều ứng viên. Nếu chỉ muốn lấy một ứng viên trong tình huống duy nhất, xem hợp đồng của `getIfUnique()`/`ifUnique()`. Trong bài toán cần chạy 0..n rule, stream mới là API đúng ý định.

## 7. Java Stream: thao tác an toàn và thời điểm thực thi

Kết quả `ObjectProvider.stream()`/`orderedStream()` là Java `Stream<T>`, nên dùng được các operation quen thuộc:

```java
// Những đoạn minh họa dưới đây nằm trong class có provider:
// Lấy list ở thời điểm hiện tại:
List<Rule> current = provider.orderedStream().toList();

// Chỉ lấy tên, không phụ thuộc thứ tự gốc:
List<String> names = provider.stream()
        .map(Rule::name).sorted().toList();

// Lấy rule đầu tiên theo Spring order:
Optional<Rule> first = provider.orderedStream().findFirst();

// Thực hiện nghiệp vụ theo thứ tự Spring:
provider.orderedStream().forEach(rule -> apply(rule));
```

Các đoạn trên cần import `java.util.List` và `java.util.Optional`; method `apply` phải do ứng dụng định nghĩa.

### 7.1. Stream chỉ dùng một lượt

Không lưu trực tiếp một `Stream<Rule>` vào field rồi gọi nhiều terminal operations trên cùng đối tượng stream:

```java
// Mã minh họa lỗi:
Stream<Rule> once = provider.orderedStream();
long count = once.count();
List<Rule> again = once.toList(); // IllegalStateException hoặc lỗi reuse
```

Cách đúng là **gọi lại provider** để tạo stream mới hoặc thu thành `List<Rule>` nếu cần sử dụng nhiều lần trên một snapshot:

```java
List<Rule> snapshot = provider.orderedStream().toList();
long count = snapshot.size();
snapshot.forEach(rule -> apply(rule));
```

Với Java 17, `Stream.toList()` trả một list không cho phép sửa trực tiếp. Nếu muốn chỉnh collection, hãy tạo bản sao mutable có chủ đích.

### 7.2. Stream operations có thể dừng sớm

`findFirst()`, `anyMatch()` và `limit(n)` có thể chỉ đi qua một phần ứng viên. Dùng chúng cho truy vấn tìm kiếm, không dùng để bảo đảm mọi handler đã được gọi. Khi cần xử lý hết các rule, dùng `forEach` trên stream đã chọn. Đừng dùng `count()` rồi suy ra side effect trong các intermediate operations chắc chắn đã xảy ra: Java Stream có quyền tối ưu trong phạm vi hợp đồng API.

### 7.3. Không tự đổi sang xử lý song song

Hai phương thức Spring trả **sequential stream**. Gọi `parallel()` trên đó chuyển việc thực thi sang mô hình xử lý song song theo Java Stream; Spring order vẫn liên quan tới encounter order, nhưng side effect có thể chạy xen kẽ giữa các thread.

Một pipeline ghi database, gọi API hoặc phụ thuộc trạng thái của bước trước **không nên tự tiện thêm `parallel()`**. Muốn concurrency phải có thiết kế an toàn thread, giao dịch và ngữ nghĩa thứ tự riêng.

### 7.4. Muốn thứ tự khác Spring thì dùng comparator riêng

Ví dụ application muốn sắp theo `Rule.name()`:

```java
List<Rule> alphabetical = provider.stream()
        .sorted(java.util.Comparator.comparing(Rule::name))
        .toList();
```

Nếu hai rule trùng tên, comparator trả bằng nhau; khi cần thứ tự nghiệp vụ toàn phần, bổ sung định danh/khóa phụ rõ ràng. Đừng coi thứ tự bean registration là một tie-breaker ổn định.

## 8. Provider, lazy initialization và scope

`ObjectProvider<T>` được tiêm như một điểm truy cập vào BeanFactory. Khi consumer gọi provider, BeanFactory phân giải các ứng viên tại thời điểm đó.

Tuy nhiên có hai khía cạnh không nên nhầm:

**Thời điểm consumer gọi provider** khác **thời điểm singleton bean đã được tạo**. Spring mặc định có thể khởi tạo non-lazy singleton từ lúc context khởi động. Vì thế giữ `ObjectProvider<T>` trong field không đồng nghĩa các bean `T` đều chưa được tạo. `@Lazy` và quan hệ dependency quyết định việc trì hoãn khởi tạo.

**Tra cứu lại bean** khác **tạo instance mới**. Với singleton, hai lần gọi provider thường nhận lại cùng singleton. Với prototype, mỗi lần bean được phân giải có thể nhận instance mới theo cơ chế scope. Với scoped proxy, phải hiểu thêm cách proxy đại diện cho đối tượng hiện hành.

Khi pipeline cần một snapshot cố định:

```java
// Minh họa: phần constructor của class đã có provider.
this.rules = provider.orderedStream().toList();
```

Vì collection được xác định tại lúc constructor chạy, consumer có cách sử dụng giống danh sách cố định. Khi muốn lookup theo từng lượt:

```java
// Minh họa: phần method thực thi trong class đã có provider.
void process() {
    provider.orderedStream().forEach(this::processOne);
}
```

Đây là lựa chọn thiết kế có chủ đích, không phải một kiểu tự động thay đổi cấu hình Spring runtime. Phần lớn ứng dụng đăng ký bean trong giai đoạn khởi động; provider không bảo đảm mọi hệ thống có thể tùy ý hot-plug bean vào context đang chạy rồi tất cả thao tác đều nhận thấy thay đổi đó.

## 9. Các overload lọc kiểu trong Spring Framework 6.2

Ngoài `stream()`/`orderedStream()` không tham số, những bản Spring 6.2 đủ mới hỗ trợ bộ lọc **theo kiểu ứng viên**:

```java
// Chữ ký API minh họa, không phải class Java độc lập:
Stream<T> stream(Predicate<Class<?>> customFilter);
Stream<T> orderedStream(Predicate<Class<?>> customFilter);

Stream<T> stream(Predicate<Class<?>> customFilter,
                 boolean includeNonSingletons);
Stream<T> orderedStream(Predicate<Class<?>> customFilter,
                        boolean includeNonSingletons);
```

Hai overload nhận `Predicate<Class<?>>` xuất hiện từ Spring **6.2.3**; các overload nhận thêm `includeNonSingletons` xuất hiện từ **6.2.5**. Chúng có mặt ở Spring Framework 6.2.19 được dùng trong `pom.xml` của ví dụ.

- `customFilter` nhận **class kiểu ứng viên**, khác với `Stream.filter(Predicate<T>)` lọc theo instance đã được lấy.
- `includeNonSingletons` cho phép quyết định có tính tới prototype/scoped bean cùng với singleton trong overload tương ứng, thay vì chỉ singleton.
- Hằng `ObjectProvider.UNFILTERED` của API hỗ trợ việc bỏ lọc mặc định ở một số overload. Đây là khả năng nâng cao, có thể cho ra ứng viên khác với phạm vi autowire thường thấy. Đừng dùng tràn lan để vượt qua một qualifier đã được thiết kế có chủ đích.

Ví dụ cú pháp khi muốn lọc kiểu theo quy ước class name:

```java
// Đoạn minh họa trong class có ObjectProvider<Rule> provider:
List<Rule> selected = provider.orderedStream(
        type -> type.getSimpleName().endsWith("Rule"),
        true
).toList();
```

Ví dụ này cho thấy predicate nhận `Class<?>` chứ không nhận `Rule`. Nhưng tên class rất dễ đổi khi refactor/proxy/lambda; đối với quy tắc nghiệp vụ thực tế, qualifier hoặc interface chuyên biệt rõ ràng và ổn định hơn. Không cần những overload này cho hầu hết ứng dụng dùng `stream()`/`orderedStream()` bình thường.

## 10. Ứng dụng vào các tình huống điển hình

### 10.1. Pipeline có thứ tự nghiệp vụ

Ví dụ hệ thống xử lý đơn hàng có `ValidationStep`, `EnrichmentStep` và `PersistenceStep`. Nếu thứ tự bắt buộc là validate → enrich → persist, gán metadata order minh bạch và gọi `orderedStream()`. Trước khi triển khai, xác định bước nào được phép thất bại và khi nào dừng pipeline. `@Order` không tự định nghĩa rollback hay chính sách lỗi của từng bước.

### 10.2. Plugin độc lập, không quan tâm thứ tự

Một tác vụ thống kê số plugin, kiểm tra khả năng hỗ trợ hoặc xây tập tên có thể dùng `stream()`. Nếu in report ra cho người đọc, sắp xếp tên bằng Java Stream để output ổn định mà không ràng buộc business behavior vào bean registration.

### 10.3. Chọn handler đầu tiên phù hợp

```java
// Đoạn minh họa, interface Handler cần supports(Request) và handle(Request).
Optional<Handler> selected = handlers.orderedStream()
        .filter(handler -> handler.supports(request))
        .findFirst();

selected.ifPresent(handler -> handler.handle(request));
```

`findFirst()` lấy handler đầu tiên theo thứ tự đã định trong stream; ở đây `orderedStream()` có vai trò quyết định. Nếu nhiều handler cùng ưu tiên và cùng hỗ trợ request, cần một thứ tự phụ ổn định hoặc thay đổi thiết kế selection.

### 10.4. Đăng ký theo khóa nghiệp vụ

```java
// Minh họa trong class có ObjectProvider<Rule> provider:
Map<String, Rule> byBusinessName = provider.stream().collect(
        java.util.stream.Collectors.toMap(Rule::name, rule -> rule)
);
```

Khóa ở đây là kết quả `Rule.name()` do ứng dụng định nghĩa, không phải bean name của Spring. Nếu hai rule trả cùng tên, `Collectors.toMap` theo cấu hình này sẽ ném lỗi vì khóa trùng. Hãy định nghĩa chính sách trùng khóa rõ ràng thay vì tùy tiện cho phép ghi đè.

## 11. Lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân phổ biến | Cách sửa |
| --- | --- | --- |
| Rule chạy theo thứ tự ngoài ý muốn | Dựa vào thứ tự đăng ký khi gọi `stream()` | Dùng `orderedStream()` với metadata order đúng |
| `orderedStream()` không theo thứ tự dự kiến | `@Order` đặt sai cấp, bỏ sót bean, hai bean cùng order | Đặt order tại bean class/`@Bean`; dùng tie-breaker rõ |
| Bean mong đợi không xuất hiện | Chưa đăng ký, không nằm trong component scan, generic/qualifier không khớp hoặc không phải autowire candidate | Kiểm tra bean definition và injection point |
| Có nhiều bean nhưng `getObject()` lỗi | API đó phải trả một bean, trong khi ứng viên không xác định duy nhất | Dùng `stream()`/`orderedStream()` nếu thật sự cần tất cả |
| Chọn `@Primary` nhưng stream vẫn có nhiều bean | `@Primary` ưu tiên single-bean resolution, không lọc stream | Dùng qualifier/kiểu riêng nếu muốn một nhóm |
| Provider stream rỗng | Không có ứng viên hợp lệ tại injection point | Kiểm tra `T`, qualifier, generic và cấu hình đăng ký |
| Duyệt stream gặp lỗi tạo bean | Bean đích khởi tạo hoặc scope lỗi | Sửa exception gốc, không coi là tập rỗng |
| Dùng lại stream và bị lỗi | Stream đã qua terminal operation | Gọi provider để tạo stream mới hoặc lưu list snapshot |
| Chỉ chạy một handler dù muốn tất cả | Dùng `findFirst()`/`limit(1)` | Dùng `forEach` để xử lý hết |
| Handler chạy đồng thời ngoài dự kiến | Tự gọi `parallel()` và có side effect | Dùng sequential hoặc thiết kế concurrency có chủ đích |
| Kết quả khác giữa các môi trường | Dựa vào thứ tự không được bảo đảm hoặc thứ tự khi order trùng | Kiểm thử thứ tự bằng `@Order`/comparator và khóa phụ |

Khi debug, hãy kiểm tra theo trình tự: (1) bean đã đăng ký trong đúng context; (2) kiểu `T` và generic; (3) qualifier và autowire candidate; (4) đây là truy vấn nhiều hay một bean; (5) có metadata `@Order`/`Ordered` hay không; (6) bean có khởi tạo thất bại hoặc scope ngoài dự định hay không.

Cần nhớ thêm: `@Order` trên `@Configuration` không tự áp dụng lên các method `@Bean`, `@DependsOn` không phải thứ tự duyệt, và `ObjectProvider<T>` không phải cơ chế loại bỏ mọi lỗi bean creation.

## 12. Kiểm thử và bài tập

### Kiểm thử có ý nghĩa

Trong ví dụ `ProviderStreamDemo` ở mục 3, ta có thể đặt các assert sau vào method `printReport()` để kiểm tra đúng thỏa thuận giữa application và container:

```java
// Đoạn bổ sung dùng trong ReportService của chương trình mục 3.
if (!all.orderedStream().map(Rule::name).toList()
        .equals(java.util.List.of("enrich", "analytics", "validate"))) {
    throw new AssertionError("Wrong Spring order");
}

if (!mandatory.orderedStream().map(Rule::name).toList()
        .equals(java.util.List.of("enrich", "validate"))) {
    throw new AssertionError("Wrong mandatory selection or order");
}

if (!missing.stream().findAny().isEmpty()) {
    throw new AssertionError("Expected empty stream");
}
```

Không có dòng stdout mới khi các điều kiện đúng; khi sai, code ném `AssertionError` tương ứng. Các kiểm tra này mạnh hơn việc chụp thứ tự tình cờ từ `stream()` không sắp xếp.

### Bài tập 1: thay đổi `@Order`

Đổi `@Order(30)` của validation thành `@Order(5)`. Dự đoán hai dòng `all.bySpringOrder` và `mandatory.bySpringOrder`.

**Đáp án:** lần lượt là `[validate, enrich, analytics]` và `[validate, enrich]`. Dòng `all.byName` vẫn xếp theo tên, nên không đổi.

### Bài tập 2: mở rộng nhóm qualifier

Đổi qualifier trên `analyticsRule` từ `metrics` sang `mandatory`. Kết quả `mandatory.bySpringOrder` thế nào?

**Đáp án:** `[enrich, analytics, validate]` vì cả ba bean cùng đủ điều kiện và được sắp theo `10,20,30`.

### Bài tập 3: không còn bean `Rule`

Xóa các phương thức `@Bean` trả `Rule`. Đồng thời loại bỏ hoặc sửa tham số `Rule preferred` của `reportService` vì nó đang là dependency bắt buộc. `ObjectProvider<Rule>.orderedStream().toList()` cho kết quả gì?

**Đáp án:** một list rỗng; provider có thể được tiêm dù không có bean đích. Nếu vẫn giữ `Rule preferred` bắt buộc, context sẽ không dựng được consumer đó.

### Bài tập 4: dùng `List<T>` hay `ObjectProvider<T>`

Một consumer chỉ cần biết tất cả plugin **một lần tại thời điểm tạo bean**. Có cần dùng provider không?

**Đáp án:** không nhất thiết. `List<Plugin>` trực tiếp là thiết kế đơn giản và diễn đạt đúng yêu cầu. Provider thích hợp khi cần lookup theo từng lượt hoặc hành vi linh hoạt theo scope.

### Bài tập 5: hai bean cùng order

Nếu `validationRule` và `analyticsRule` cùng `@Order(20)` mà nghiệp vụ yêu cầu validation luôn trước analytics, có thể tin thứ tự xuất hiện tình cờ trong danh sách được không?

**Đáp án:** không nên. Hãy cho chúng order khác nhau hoặc định nghĩa comparator có khóa phụ ổn định và kiểm thử trường hợp trùng order.

## Kết luận kiến thức

`ObjectProvider<T>` cho phép một bean Spring truy vấn các ứng viên `T` khi cần. `stream()` phù hợp khi bạn muốn duyệt tất cả ứng viên mà không phụ thuộc thứ tự; `orderedStream()` phù hợp khi nghiệp vụ yêu cầu thứ tự do Spring xác lập bằng `Ordered`, `@Order` hoặc cơ chế annotation tương ứng.

Qualifier và generic quyết định **ứng viên nào tham gia**; order quyết định **trình tự duyệt**; `@Primary` thường giải quyết bài toán **chọn một bean**, không lọc cả stream. Khi không có ứng viên, stream rỗng là bình thường; khi bean được chọn khởi tạo thất bại, lỗi vẫn cần được xử lý. Java Stream vẫn có những đặc tính thông thường: tiêu thụ một lần, phép xử lý có thể dừng sớm, và concurrency phải được thiết kế riêng.

## Tài liệu chính thức

- Spring Framework — [`ObjectProvider<T>` Javadoc, 6.2.x](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): `stream()`, `orderedStream()`, bộ lọc kiểu và overload có tham số scope.
- Spring Framework — [Using `@Autowired`, 6.2](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html): nhiều bean ứng viên, thứ tự, quy tắc injection.
- Spring Framework — [Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html): qualifier trên các injection point.
- Spring Framework — [`Order` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/annotation/Order.html): ý nghĩa annotation và hạn chế.
- Java SE 17 — [`Stream<T>` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): xử lý stream tuần tự, terminal operations và giới hạn tái sử dụng.
