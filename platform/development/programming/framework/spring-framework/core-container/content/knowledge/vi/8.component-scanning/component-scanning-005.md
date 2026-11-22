# Bộ lọc include, exclude và useDefaultFilters trong Spring Component Scan

## 1. Mục tiêu bài học

Trong Spring Core Container, `@ComponentScan` không nhất thiết phải đăng ký mọi class được đánh dấu `@Component`. Ta có thể **bổ sung loại class được tìm thấy**, **loại bỏ loại class không muốn đăng ký**, hoặc **tắt hoàn toàn bộ lọc stereotype mặc định**.

Sau bài này, bạn có thể:

- Giải thích ý nghĩa của `includeFilters`, `excludeFilters` và `useDefaultFilters` trên `@ComponentScan`.
- Dự đoán chính xác một class có được scan thành bean hay không khi các filter cùng áp dụng.
- Sử dụng `FilterType.ANNOTATION`, `ASSIGNABLE_TYPE`, `REGEX`, `ASPECTJ` và `CUSTOM` đúng phạm vi.
- Hiểu khác biệt giữa “lọc ứng viên được component scanner phát hiện” và “ngăn mọi cách đăng ký bean”.
- Viết cấu hình Java 17+ chạy được, trong đó class có annotation riêng được chọn, một class khác bị loại, và `@Service` thông thường không được đăng ký vì `useDefaultFilters=false`.
- Chẩn đoán lỗi thiếu bean, scan quá rộng, regex sai tên đầy đủ, custom `TypeFilter` lỗi và trùng bean.

**Phạm vi:** bài học chỉ nói đến bộ lọc của **component scanning** trong Spring IoC Container. Nó không thay thế `@Profile`, `@Conditional`, cấu hình Spring Data repository scanning hoặc JPA entity scanning.

## 2. Bộ lọc mặc định của component scan là gì?

Khi sử dụng:

```java
@Configuration
@ComponentScan(basePackages = "com.example.shop")
public class AppConfig {}
```

Spring tìm các class trong package `com.example.shop` và các package con, rồi áp dụng **bộ lọc mặc định**. Theo cấu hình Spring Framework thông thường, bộ lọc này nhận diện `@Component` và các annotation được meta-annotate bởi `@Component`, tiêu biểu:

- `@Service`;
- `@Repository`;
- `@Controller`;
- `@RestController` (thông qua chuỗi meta-annotation);
- `@Configuration`;
- annotation do ứng dụng tạo với `@Component` làm meta-annotation.

Nếu ứng dụng có Jakarta Inject phù hợp, Spring còn có thể hỗ trợ annotation `@Named` thông qua bộ lọc mặc định tương ứng. Trong bài, ta tập trung vào mô hình `@Component`.

**Phân biệt hai bước:**

1. **Phát hiện ứng viên:** scanner dùng package và các bộ lọc để xác định class nào phù hợp.
2. **Đăng ký/tạo bean:** container xử lý bean definition, scope, điều kiện cấu hình, phụ thuộc và vòng đời. Class phù hợp filter vẫn cần là ứng viên hợp lệ và phải có thể được container đăng ký.

Một `interface` thuần khớp `ASSIGNABLE_TYPE` không có nghĩa Spring tự khởi tạo interface làm component. Type filter còn phải đi qua các kiểm tra ứng viên hợp lệ.

## 3. Ba thuộc tính quan trọng của @ComponentScan

Giả sử cấu hình:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = org.springframework.context.annotation.FilterType.ANNOTATION,
        classes = SpecialModule.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = org.springframework.context.annotation.FilterType.ASSIGNABLE_TYPE,
        classes = LegacyAdapter.class
    )
)
public class AppConfig {}
```

Đây là ví dụ **cấu trúc**: `SpecialModule` là annotation tự định nghĩa và `LegacyAdapter` là class có thực trong ứng dụng, chưa được khai báo ở đây. Đừng copy riêng đoạn này rồi kỳ vọng biên dịch khi thiếu hai kiểu.

Ý nghĩa:

- `basePackages`: giới hạn **vùng cần quét**. Filter không tìm class ở ngoài vùng này.
- `useDefaultFilters=false`: không tự động coi stereotype `@Component`, `@Service`, `@Repository`, `@Controller`,… là đủ để được chọn.
- `includeFilters`: thêm tiêu chí cho class **đủ điều kiện được nhận diện**. Trong ví dụ, class mang `@SpecialModule` có thể được đưa vào tập ứng viên kể cả khi annotation này không meta-annotated bởi `@Component`.
- `excludeFilters`: loại class khớp điều kiện; trong ví dụ, class có kiểu `LegacyAdapter` bị loại khỏi đợt scan đó.
- `@Configuration` và `@Bean` được đăng ký rõ ràng vẫn có thể tạo bean độc lập với việc class đó có được scanner chọn hay không.

### Bảng hành vi quan trọng

| `useDefaultFilters` | `includeFilters` | `excludeFilters` | Kết quả cơ bản |
| --- | --- | --- | --- |
| `true` (mặc định) | Không khai báo | Không khai báo | Nhận component/stereotype mặc định trong package scan. |
| `true` | Có | Không | Nhận **ứng viên mặc định HOẶC ứng viên match include**. |
| `true` | Có | Có | Nhận ứng viên từ mặc định/include, **trừ** những loại match exclude. |
| `false` | Không | Không | Không có tiêu chí include mặc định để tìm component thông thường. |
| `false` | Có | Không | Chỉ nhận ứng viên match include trong package scan. |
| `false` | Có | Có | Chỉ nhận ứng viên match include **và không match exclude**. |

Điểm rất hay nhầm là `includeFilters` **không tự biến scan thành whitelist** khi `useDefaultFilters` vẫn là `true`. Nó **mở rộng** tập mà filter mặc định tìm thấy. Muốn danh sách dựa hẳn trên tiêu chí do bạn khai báo, cần cân nhắc `useDefaultFilters=false`.

## 4. Mô hình lựa chọn ứng viên

Đối với mỗi class nằm trong phạm vi scan và được xem xét bởi scanner, có thể hình dung điều kiện filter:

```text
Bắt đầu với một class trong base package
               |
               v
      Có match exclude?
         /           \
       Có             Không
       |                |
  Bỏ qua class          v
                   Match include?
                    /        \
                  Có         Không
                  |             |
               Chọn*            v
                       useDefaultFilters=true
                       và match mặc định?
                         /         \
                        Có          Không
                        |              |
                      Chọn*          Bỏ qua

* Sau đó còn kiểm tra điều kiện ứng viên bean hợp lệ.
```

Sơ đồ thể hiện kết quả logic: **exclude thắng include/default** trong cùng quá trình scan. Ở bản triển khai, scanner có thể kiểm tra exclude trước và dừng sớm. Đừng hiểu sơ đồ là thứ tự gọi từng matcher theo đúng hình vẽ.

Ta có thể viết công thức mô hình:

```text
eligibleByFilters =
    inBasePackage
    AND NOT excluded
    AND (
        matchesAnyInclude
        OR (useDefaultFilters AND matchesDefault)
    )
```

Công thức chỉ mô tả bộ lọc, **chưa** bao gồm các bước kiểm tra concrete/independent candidate, các điều kiện như `@Conditional`, xử lý bean name hay bean definition đã đăng ký.

### Nhiều include và exclude

Trong một mảng `includeFilters`, nhiều bộ lọc thường kết hợp theo phép **OR**: class chỉ cần khớp một bộ lọc include. Tương tự, nhiều loại trừ có tác dụng loại class nếu **bất kỳ** exclude filter nào khớp.

Do đó:

```java
includeFilters = {
    @ComponentScan.Filter(
        type = FilterType.ANNOTATION, classes = FeatureA.class),
    @ComponentScan.Filter(
        type = FilterType.ANNOTATION, classes = FeatureB.class)
}
```

có nghĩa “FeatureA **hoặc** FeatureB”, không phải “phải đồng thời mang cả hai”. Đây là đoạn annotation minh họa, cần import `ComponentScan`, `FilterType` và khai báo hai annotation nghiệp vụ.

Nếu cần điều kiện phức tạp “A **và** B”, có thể dùng `FilterType.CUSTOM` để kiểm tra cả hai metadata trong một `TypeFilter`, hoặc sắp xếp thiết kế package/annotation sao cho rõ ràng hơn.

## 5. useDefaultFilters: true và false

### 5.1. Mặc định true: vẫn quét các stereotype

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.shop",
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = Experimental.class
    )
)
class AppConfig {}
```

Giả định `Experimental` là annotation do ứng dụng định nghĩa. Với `useDefaultFilters=true` mặc định:

- `@Service StandardService` trong package vẫn là ứng viên;
- `@Repository StandardRepository` vẫn là ứng viên;
- class `@Experimental PreviewEngine` có thể được nhận nếu filter khớp, **dù `@Experimental` không phải meta-annotation của `@Component`**;
- class không khớp cả default lẫn include sẽ bị bỏ qua.

**Sai lầm:** “Thêm `includeFilters = Experimental` là Spring chỉ còn quét class Experimental.” Điều này sai khi chưa tắt mặc định.

### 5.2. useDefaultFilters=false: chỉ giữ tiêu chí tự khai báo

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = Experimental.class
    )
)
class AppConfig {}
```

Lúc này, class chỉ có `@Service` hoặc `@Component` mà không mang `@Experimental` sẽ không được scanner này chọn. Lưu ý, không nhất thiết **mọi bean** trong context đều mất: bean từ `@Bean`, `@Import`, class cấu hình đăng ký trực tiếp và cơ chế khác vẫn có thể tồn tại.

### 5.3. Tắt mặc định mà quên include

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false
)
```

Với cách này, scanner không có bộ lọc stereotype mặc định và không được cấp include filter nào; kết quả là **không tự tìm thấy các component thông thường** trong vùng quét. Cấu hình này hiếm khi là ý định của ứng dụng. Nếu `@Configuration` được đưa trực tiếp vào `AnnotationConfigApplicationContext`, bản thân nó vẫn tồn tại; đừng nhầm điều đó với việc scanner tìm thấy service.

### 5.4. Khi nào nên giữ mặc định?

Phần lớn ứng dụng nên để `useDefaultFilters=true` vì cấu trúc package và stereotype đã mô tả rõ các component. Chỉ dùng `false` khi muốn một cơ chế chọn thành phần chủ động, ví dụ triển khai plugin với annotation chuyên biệt, tách bộ adapter thử nghiệm khỏi thành phần thông thường, hoặc dựng context rất hẹp phục vụ công cụ.

Đừng dùng bộ lọc phức tạp chỉ để thay thế việc tổ chức package rõ ràng.

## 6. Ví dụ Java 17+ hoàn chỉnh: include + exclude + tắt default

Chương trình này **không cần Spring Boot**. Nó dùng Spring Framework 6.2.9, Java 17 và `AnnotationConfigApplicationContext`. Tất cả class đặt trong cùng một file Java để dễ chạy và quan sát chính xác.

Mục đích:

1. `PilotJob` mang annotation `@Pilot` **không** có `@Component` vẫn được đưa vào context do include filter.
2. `DirectJob` **không có annotation stereotype** vẫn được chọn do `ASSIGNABLE_TYPE`.
3. `BlockedJob` mang `@Pilot` nhưng bị exclude, chứng minh exclude thắng include.
4. `RegularJob` có `@Service` nhưng bị bỏ qua vì `useDefaultFilters=false`.

### 6.1. Cấu trúc dự án

```text
filter-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/FilterDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'filter-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.FilterDemo'
}
```

**`src/main/java/demo/FilterDemo.java`**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.TreeSet;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FilterType;
import org.springframework.stereotype.Service;

public class FilterDemo {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext ctx =
                new AnnotationConfigApplicationContext(ScanConfig.class)) {

            System.out.println("pilot=" + ctx.containsBean("pilotJob"));
            System.out.println("direct=" + ctx.containsBean("directJob"));
            System.out.println("blocked=" + ctx.containsBean("blockedJob"));
            System.out.println("regular=" + ctx.containsBean("regularJob"));

            var jobs = ctx.getBeansOfType(Job.class);
            System.out.println("selected=" +
                    String.join(",", new TreeSet<>(jobs.keySet())));

            System.out.println("run=" +
                    jobs.get("pilotJob").run() + "|" +
                    jobs.get("directJob").run());
        }
    }
}

interface Job {
    String run();
}

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@interface Pilot {
}

// Chọn qua ANNOTATION, dù @Pilot không meta-annotated @Component.
@Pilot
class PilotJob implements Job {
    @Override
    public String run() {
        return "pilot";
    }
}

// Chọn qua ASSIGNABLE_TYPE, không cần @Component.
class DirectJob implements Job {
    @Override
    public String run() {
        return "direct";
    }
}

// Match @Pilot nhưng bị exclude theo class.
@Pilot
class BlockedJob implements Job {
    @Override
    public String run() {
        return "blocked";
    }
}

// Có @Service nhưng bộ lọc default đang tắt.
@Service
class RegularJob implements Job {
    @Override
    public String run() {
        return "regular";
    }
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(
    basePackageClasses = FilterDemo.class,
    useDefaultFilters = false,
    includeFilters = {
        @ComponentScan.Filter(
            type = FilterType.ANNOTATION,
            classes = Pilot.class
        ),
        @ComponentScan.Filter(
            type = FilterType.ASSIGNABLE_TYPE,
            classes = DirectJob.class
        )
    },
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = BlockedJob.class
    )
)
class ScanConfig {
}
```

Các class `Job`, `PilotJob`, `DirectJob`, `BlockedJob`, `RegularJob` và `ScanConfig` là các top-level type không `public` trong file; Java cho phép điều này. Lớp `FilterDemo` duy nhất là `public` và tên file đúng tên class. Spring có thể phát hiện các class top-level độc lập trong package `demo`; việc không ghi `public` không biến chúng thành inner class.

`basePackageClasses=FilterDemo.class` chỉ dùng package của `FilterDemo` làm gốc quét. Class `FilterDemo` không tự được chọn vì không có filter phù hợp.

### 6.2. Chạy chương trình

Từ thư mục `filter-demo`, với Gradle và JDK 17+:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows. `javac FilterDemo.java` riêng lẻ không đủ vì thiếu Spring JAR; Gradle sẽ resolve dependency rồi biên dịch/chạy class `demo.FilterDemo`.

**Stdout dự kiến do chương trình in ra:**

```text
pilot=true
direct=true
blocked=false
regular=false
selected=directJob,pilotJob
run=pilot|direct
```

Các log tải dependency hoặc cấu hình Gradle, nếu có, nằm ngoài các dòng do `System.out.println` này tạo.

### 6.3. Phân tích từng ứng viên

| Class | Khớp default stereotype? | Khớp include? | Khớp exclude? | Kết quả |
| --- | --- | --- | --- | --- |
| `PilotJob` | Không; `@Pilot` không là `@Component` | Có, `ANNOTATION Pilot` | Không | **Được chọn** |
| `DirectJob` | Không | Có, `ASSIGNABLE_TYPE DirectJob` | Không | **Được chọn** |
| `BlockedJob` | Không | Có, `ANNOTATION Pilot` | Có, `ASSIGNABLE_TYPE BlockedJob` | **Bị loại** |
| `RegularJob` | Có, `@Service` | Không | Không | **Bị loại** vì default tắt |
| `ScanConfig` | Có, `@Configuration` | Không | Không | Không được *scan thêm*; được đăng ký trực tiếp khi tạo context |

Tập `getBeansOfType(Job.class)` chứa `directJob` và `pilotJob`. `TreeSet` chỉ dùng để **sắp tên khi in stdout ổn định**; không chứng minh thứ tự Spring tìm bean trên classpath. `run=pilot|direct` được viết theo thứ tự lấy bean bằng key, nên không phụ thuộc vào thứ tự map.

### 6.4. Thử các thay đổi có ý nghĩa

**Thay `useDefaultFilters = false` thành `true`.** Khi ấy `RegularJob` trở thành ứng viên vì mang `@Service`; các include vẫn hợp lệ. `ScanConfig` cũng có thể được scanner nhận diện do `@Configuration`, nhưng việc nó đã được đăng ký trực tiếp không tạo thêm một `Job`. Đừng mặc định rằng đổi flag chỉ thêm đúng một bean của *mọi kiểu*.

**Bỏ exclude cho `BlockedJob`.** `BlockedJob` sẽ được thêm vào vì khớp `@Pilot`. Đây là bằng chứng exclude đang chặn một class vốn được include.

**Bỏ include cho `DirectJob`.** Với default vẫn tắt, bean `directJob` không được scan. Lời gọi `jobs.get("directJob").run()` của demo sẽ thất bại vì mã mẫu vẫn yêu cầu key này. Nếu thử biến thể, cần điều chỉnh phần in kết quả hoặc chỉ kiểm tra `containsBean` để quan sát một cách có kiểm soát.

**Đặt `@Component` trên `RegularJob` nhưng giữ `useDefaultFilters=false`.** Bean vẫn không xuất hiện nếu không khớp include. Thêm stereotype không vượt qua công tắc đã tắt bộ lọc mặc định.

## 7. FilterType.ANNOTATION

`ANNOTATION` là kiểu filter mặc định của `@ComponentScan.Filter`. Nó nhận các class mang một annotation được chỉ định hoặc meta-annotation tương ứng.

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = ExperimentalFeature.class
    )
)
```

Đây là đoạn annotation minh họa đặt trên một class cấu hình; `ExperimentalFeature` là annotation do ứng dụng định nghĩa. Spring có thể đưa class như sau vào container khi scan:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ExperimentalFeature {}

@ExperimentalFeature
public class PreviewDiscountPolicy {}
```

Đoạn minh họa cần import `ElementType`, `Target`, `Retention`, `RetentionPolicy`. Nếu muốn code tự chạy, đặt mỗi public top-level type vào file tên tương ứng.

**Hai trường hợp phải phân biệt:**

- Annotation tùy chỉnh **không** có `@Component`: scanner mặc định thường không chọn, nhưng `includeFilters=ANNOTATION` có thể chọn.
- Annotation tùy chỉnh **có** `@Component` là meta-annotation: scanner mặc định đã có thể chọn, ngay cả khi không thêm filter.

Ví dụ meta-stereotype:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@org.springframework.stereotype.Component
public @interface BusinessComponent {}
```

Đây là ví dụ cấu trúc; cần import các annotation type của Java. Với `@BusinessComponent`, nhiều ứng dụng không cần include filter riêng. Trong trường hợp quy tắc chọn quá đặc thù, include filter vẫn hữu ích khi kết hợp `useDefaultFilters=false`.

**Lưu ý:** ANNOTATION dùng để tìm metadata trên **type** được quét, không tìm method `@GetMapping` hay các method mang annotation riêng để tự tạo bean tương ứng. Method-level scanning là vấn đề khác.

## 8. FilterType.ASSIGNABLE_TYPE

`ASSIGNABLE_TYPE` chọn các class có thể gán cho một kiểu mục tiêu, tức là class ấy chính là kiểu cần xét, kế thừa superclass hoặc hiện thực interface.

```java
@ComponentScan(
    basePackages = "com.example.shop.handlers",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = CommandHandler.class
    )
)
```

Với giả định `CommandHandler` là interface nghiệp vụ, scanner có thể chọn các implementation trong package được quét, kể cả khi chưa đánh dấu `@Component`:

```java
interface CommandHandler {
    void execute();
}

class CreateOrderHandler implements CommandHandler {
    public void execute() {}
}

class CancelOrderHandler implements CommandHandler {
    public void execute() {}
}
```

Đây là ví dụ hai đoạn độc lập cần đặt trong cùng package hoặc import kiểu phù hợp. Scanner vẫn phải kiểm tra tính hợp lệ của candidate; nó không khởi tạo interface `CommandHandler`.

**Cảnh báo về số lượng:** khi lọc bằng một base interface rất rộng, có thể scan nhiều implementation và gây `NoUniqueBeanDefinitionException` lúc injection đơn theo interface. Nếu muốn nhiều bean, injection `List<CommandHandler>` là lựa chọn rõ ràng. Nếu muốn một, cân nhắc `@Qualifier`, `@Primary` hoặc giới hạn phạm vi package/type hợp lý.

Bộ lọc theo type là một phép tìm trên **metadata của class**, không bảo đảm mọi kiểu có thể gán đều có constructor hay dependencies phù hợp để Spring tạo thành công.

## 9. FilterType.REGEX

`REGEX` chọn class theo **tên đầy đủ (fully qualified class name)**, tức là bao gồm package và tên class. Nó không phân tích giá trị nghiệp vụ của object và không áp regex lên tên bean sau khi tạo.

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.REGEX,
        pattern = "com\\.example\\.shop\\.adapter\\..*Adapter"
    )
)
```

Ở đây:

- `com\\.example\\.shop\\.adapter\\.` trong literal Java dùng `\\.` để trở thành dấu chấm thật trong regex.
- `.*Adapter` khớp các tên kết thúc bằng `Adapter` trong package đang mô tả.
- Regex kiểm tra tên class đầy đủ; `basePackages` vẫn quyết định nơi scanner tìm các class để thử.

Ví dụ `com.example.shop.adapter.SqlAdapter` khớp pattern. `com.example.shop.service.StockService` không khớp. `com.example.shop.adapter.SqlAdapterV2` cũng không khớp vì không kết thúc bằng `Adapter`.

**Lỗi Java string phổ biến:** viết `pattern="com\.example\..*"` sẽ gây lỗi escape không hợp lệ trong mã Java vì `\.` không phải escape hợp lệ của Java string. Cần viết `"com\\.example\\..*"` trong Java source để engine regex nhận `com\.example\..*`.

**Không dùng regex khi type/annotation đã đủ:** tên package và class có thể thay đổi khi refactor, khiến bộ lọc không còn bắt đúng class mà IDE/compiler ít có khả năng cảnh báo. Nếu hệ thống có annotation mô tả capability, lọc bằng `ANNOTATION` thường rõ ý định hơn.

## 10. FilterType.ASPECTJ

`ASPECTJ` nhận một **AspectJ type pattern expression** để xét kiểu. Ví dụ dạng tham khảo theo tài liệu Spring:

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASPECTJ,
        pattern = "com.example..*Service+"
    )
)
```

Đây là đoạn cấu hình minh họa sử dụng **cú pháp pattern của AspectJ**, không phải Java regex. Dấu `..` và `+` có ý nghĩa theo AspectJ; cần kiểm tra kiểu thực tế khớp theo cú pháp AspectJ và có dependency hỗ trợ AspectJ type pattern (thường `aspectjweaver`) khi dùng filter này.

`ASPECTJ` ở đây **chỉ dùng để lựa chọn class lúc scan**, không tự động bật Spring AOP, không tạo aspect và không can thiệp vào lời gọi method. Cũng không nên nhầm với annotation `@Aspect`. Với đa số bài toán chọn component theo danh mục, `ANNOTATION`, `ASSIGNABLE_TYPE` hoặc `REGEX` dễ hiểu hơn.

## 11. FilterType.CUSTOM và TypeFilter

Khi các kiểu mặc định không biểu diễn được tiêu chí mong muốn, có thể tự triển khai `org.springframework.core.type.filter.TypeFilter` (giao diện thực nằm trong package `org.springframework.core.type.filter`).

```java
package com.example.shop.config;

import java.io.IOException;
import org.springframework.core.type.classreading.MetadataReader;
import org.springframework.core.type.classreading.MetadataReaderFactory;
import org.springframework.core.type.filter.TypeFilter;

public final class EndsWithGatewayFilter implements TypeFilter {
    @Override
    public boolean match(
            MetadataReader metadataReader,
            MetadataReaderFactory metadataReaderFactory) throws IOException {

        String className =
                metadataReader.getClassMetadata().getClassName();

        return className.endsWith("Gateway");
    }
}
```

Đây là một class `TypeFilter` Java hợp lệ khi có `spring-core` trên classpath (được Spring Context mang vào). Có thể sử dụng như sau ở cấu hình cùng dự án:

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.CUSTOM,
        classes = EndsWithGatewayFilter.class
    )
)
```

Đoạn cấu hình minh họa cần import `ComponentScan`, `FilterType` và `EndsWithGatewayFilter`, đặt trên class phù hợp.

**Vì sao dùng `MetadataReader`?** Scanner đọc metadata .class bằng cơ chế phù hợp, tránh buộc phải tạo instance của tất cả type để xem chúng có cần đăng ký hay không. Custom filter nên được thiết kế **nhanh, dễ dự đoán, không side effect**. Không kết nối database, gửi request mạng hoặc tải những class nặng chỉ để quyết định include/exclude.

`MetadataReaderFactory` hỗ trợ truy cập metadata của class liên quan, chẳng hạn superclass hoặc interface khi tiêu chí nâng cao cần; hãy tránh tự tạo classloader hay đọc tài nguyên tùy tiện cho mỗi file .class.

Nếu match nhiều class không thể khởi tạo thành component thì hệ thống vẫn cần xử lý tính hợp lệ của candidate; TypeFilter không bỏ qua toàn bộ nguyên tắc tạo bean.

## 12. Cách kết hợp include và exclude trong tình huống thật

### 12.1. Vẫn quét mặc định nhưng loại những class cũ

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = LegacyComponent.class
    )
)
class AppConfig {}
```

Giả định `LegacyComponent` là annotation tự định nghĩa. Khi `useDefaultFilters` giữ `true`, Spring tiếp tục tìm các stereotype thông thường nhưng loại class được đánh dấu legacy. Điều này phù hợp nếu phần lớn kiến trúc vẫn tuân theo `@Component`.

### 12.2. Chọn một nhóm plugin có annotation riêng

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.plugins",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = PluginComponent.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = DisabledPlugin.class
    )
)
class PluginConfig {}
```

Đây là đoạn minh họa cần hai annotation nghiệp vụ. Với bộ lọc này, class mang `@PluginComponent` được chọn trừ khi đồng thời mang `@DisabledPlugin`. **Tính bật/tắt tại thời điểm runtime** không được tự động cập nhật liên tục: đây là quyết định đăng ký bean khi Spring dựng context. Muốn bật/tắt tính năng động cần cơ chế khác phù hợp.

### 12.3. Đổi implementation trong test

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.shop.data",
    includeFilters = @ComponentScan.Filter(
        type = FilterType.REGEX,
        pattern = ".*Stub.*Repository"
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = org.springframework.stereotype.Repository.class
    )
)
class TestDataConfig {}
```

Ý tưởng: include những class có tên như `StubCustomerRepository` và exclude các class mang `@Repository` trong lượt scan này. Nếu **stub cũng mang `@Repository`**, nó cũng sẽ bị loại vì exclude thắng include; vì vậy cần thiết kế marker/stub rõ ràng.

Cấu hình test còn phụ thuộc các configuration khác đã được import hoặc autoconfigure. Chỉ exclude ở một lượt scan **không chứng minh** rằng bean gốc không thể được đăng ký qua lượt scan khác, `@Bean`, `@Import` hoặc auto-configuration.

### 12.4. Điều gì xảy ra khi include và exclude cùng khớp một class?

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = OrderProcessor.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.REGEX,
        pattern = ".*DeprecatedOrderProcessor"
    )
)
```

Nếu `DeprecatedOrderProcessor implements OrderProcessor` và tên đầy đủ kết thúc bằng `DeprecatedOrderProcessor`, bean đó bị loại. Những `OrderProcessor` khác đủ điều kiện sẽ được đưa vào tập ứng viên. Đây là quy tắc loại trừ trong **lượt scanner**.

## 13. Cấu hình XML tương đương khi gặp dự án cũ

Nhiều dự án legacy dùng `context:component-scan` thay vì annotation. Cùng ý tưởng:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan
            base-package="com.example.shop"
            use-default-filters="false">
        <context:include-filter
                type="annotation"
                expression="com.example.shop.PluginComponent"/>
        <context:exclude-filter
                type="regex"
                expression="com\.example\.shop\..*Legacy.*"/>
    </context:component-scan>
</beans>
```

Đây là ví dụ XML có tên annotation nghiệp vụ giả định `com.example.shop.PluginComponent`. Trong XML regex dùng dấu `\.` trực tiếp; không cần escape thêm theo quy tắc Java string literal. Spring XML và `@ComponentScan` đều diễn đạt cùng ý tưởng chọn/loại type bằng filter.

Các giá trị type ở XML gồm `annotation`, `assignable`, `aspectj`, `regex`, `custom`; trong Java API là các hằng của `FilterType`.

## 14. Phân biệt bộ lọc scan với các cơ chế khác

| Cơ chế | Mục đích | Quan hệ với component scan |
| --- | --- | --- |
| `basePackages` / `basePackageClasses` | Xác định **vùng classpath được quét** | Filter chỉ hoạt động bên trong vùng ấy. |
| `includeFilters` | Bổ sung class có thể được chọn | Có thể chọn class chưa mang `@Component`. |
| `excludeFilters` | Loại class khỏi **lượt scan** | Không chặn đăng ký qua các đường khác. |
| `useDefaultFilters` | Bật/tắt phát hiện stereotype mặc định | Không xóa bean đã được đăng ký bằng `@Bean` hoặc `@Import`. |
| `@Profile` | Giới hạn đăng ký theo profile active | Điều kiện cấu hình, không phải filter từ `@ComponentScan`. |
| `@Conditional` | Giới hạn đăng ký theo điều kiện cụ thể | Có thể làm bean không được đăng ký dù metadata đã được scanner nhận diện. |
| `@Primary` | Ưu tiên ứng viên khi autowire đơn | Không quyết định scanner có đưa type vào context hay không. |
| `@Qualifier` | Thu hẹp candidate khi injection | Áp dụng trong giải quyết dependency, sau chuyện scan. |
| `@Bean` | Đăng ký bean từ factory method | Đường đăng ký độc lập, không bị xóa bởi một exclude filter. |
| `@Import` | Import configuration/selector/registrar | Đường đăng ký khác với chọn component theo scanner. |

**Sai lầm nguy hiểm:** xem `excludeFilters` như “cấm class này xuất hiện trong toàn ApplicationContext”. Nếu một `@Configuration` khác khai báo bean cùng type bằng `@Bean`, exclude filter không triệt tiêu bean đó. Cần nhìn toàn bộ các đường đăng ký khi điều tra bean ngoài dự kiến.

## 15. Spring Boot và giới hạn quét

Trong Spring Boot, `@SpringBootApplication` thường bao gồm `@ComponentScan`. Các thuộc tính như `scanBasePackages` và `scanBasePackageClasses` cấu hình **component scanning**, nhưng không mặc nhiên thay mọi cơ chế scan khác, ví dụ JPA entity hoặc Spring Data repository.

Ví dụ khái niệm:

```java
@SpringBootApplication(scanBasePackages = "com.example.shop")
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Đây là snippet Spring Boot, yêu cầu dependencies Spring Boot và class trong package phù hợp. Với ứng dụng tự thêm nhiều `@ComponentScan`, hãy cẩn thận vì mỗi cấu hình scan có thể góp thêm bean definition. Một exclude filter áp dụng cho lượt scan này không đảm bảo một lượt scan khác không đăng ký type đó.

Nếu chỉ muốn loại một bean dựa trên feature flag ở Boot, có thể cấu hình bean điều kiện (`@ConditionalOnProperty`, v.v.) phù hợp với nguồn cấu hình hơn là lọc tên class bằng regex. Nhưng đây là lựa chọn thiết kế bên ngoài cơ chế filter cơ bản của Spring Framework.

## 16. Lỗi thường gặp và cách kiểm tra

### Lỗi 1 — “Có includeFilters rồi nhưng Spring vẫn scan mọi @Service”

Nguyên nhân: `useDefaultFilters` mặc định **true**, nên `@Service` vẫn được chọn. Muốn chỉ lấy class theo include filter, đặt `useDefaultFilters=false` và kiểm tra lại tất cả dependency cần thiết.

### Lỗi 2 — “Tắt useDefaultFilters thì mất toàn bộ service”

Nếu không khai báo include phù hợp, các stereotype bình thường không còn được tìm qua lượt scan này. Thêm bộ lọc include, hoặc giữ mặc định nếu muốn dùng cấu trúc stereotype thông thường.

### Lỗi 3 — “Exclude một class nhưng bean vẫn có mặt”

Cần xác định bean được đăng ký từ đâu: một `@Bean`, `@Import`, một context khác, một lần `@ComponentScan` khác hoặc auto-configuration. `excludeFilters` chỉ áp dụng với scanner được cấu hình. Trong trường hợp này, xem bean definition và nguồn cấu hình thay vì thêm hàng loạt exclude trùng nhau.

### Lỗi 4 — “REGEX không match class mong đợi”

Xác minh **tên đầy đủ** của class (`package.ClassName`), không so với tên bean. Trong Java string, nhớ dấu `\\.` để thể hiện regex literal `\.`. Kiểm tra pattern bằng dữ liệu tên class thực và lưu ý regex matcher nhận toàn bộ tên theo quy tắc matching của loại filter.

### Lỗi 5 — “ASSIGNABLE_TYPE tìm được interface nhưng không tạo được bean”

Interface hoặc abstract class không tự trở thành component có thể khởi tạo nhờ khớp filter. Chỉ concrete, independent class hợp lệ mới thường được đưa vào danh sách component candidates, ngoài những hỗ trợ riêng như lookup-method có điều kiện. Chọn implementation rõ ràng và cung cấp constructor/dependencies có thể giải quyết.

### Lỗi 6 — “Exclude filter và include filter cùng khớp; mong include thắng”

Trong một lượt scan, class khớp **exclude** bị loại ngay cả khi cũng khớp include hoặc stereotype mặc định. Đổi thiết kế điều kiện hoặc xem lại thứ tự ưu tiên nghiệp vụ trước khi viết filter.

### Lỗi 7 — “Filter CUSTOM có side effect hoặc load class tùy tiện”

Custom `TypeFilter` được gọi trong quá trình scanning; IO hoặc reflection đắt đỏ khiến startup chậm và có thể gây lỗi ngoài ý muốn. Dùng `MetadataReader` khi đủ, tránh service call, connection hay global mutable state trong matcher.

### Lỗi 8 — “Scan package quá rộng nên có bean ngoài ý muốn”

Nếu dùng `basePackages="com"` hoặc package gốc quá chung, scanner có thể đụng vô số class từ module không liên quan. Thu hẹp package quét, tách annotation nghiệp vụ hợp lý và kiểm tra import cấu hình từ nơi khác.

### Lỗi 9 — “Đưa filter của một context vào và tưởng áp dụng cho tất cả context”

Ứng dụng có thể có root ApplicationContext, child WebApplicationContext, test slice hoặc context độc lập. Bean trong context nào phụ thuộc vào scan và registration của context đó; không áp dụng filter một cách toàn cục vượt ranh giới context.

### Lỗi 10 — “Chọn bean bằng scanner nhưng constructor vẫn lỗi”

Filter có thể chọn một bean đủ điều kiện scan nhưng bean ấy cần dependency chưa tồn tại, constructor không phù hợp hoặc bean name xung đột. `includeFilters` không bypass dependency injection hay lỗi tạo bean. Khi cần, kiểm tra `UnsatisfiedDependencyException`, `BeanCreationException` và danh sách ứng viên.

### Lỗi 11 — “Đổi tên class mà không cập nhật REGEX”

Regex dựa vào tên class đầy đủ dễ bị ảnh hưởng bởi refactor. Các phép lọc dựa theo annotation hoặc interface là lựa chọn bền vững hơn khi tên class không phải hợp đồng nghiệp vụ.

### Lỗi 12 — “Nghĩ scan filter là cơ chế bật/tắt bean động sau khi context chạy”

Filter quyết định lúc scan/đăng ký; nó không tự theo dõi file cấu hình để thêm/xóa bean runtime. Với tính năng có thể bật/tắt động, nên thiết kế abstraction hoặc runtime strategy riêng, không dựa vào việc sửa `includeFilters` khi ứng dụng đang chạy.

## 17. Quan sát và kiểm thử filter

### 17.1. Kiểm tra trực tiếp bean name

```java
try (AnnotationConfigApplicationContext ctx =
         new AnnotationConfigApplicationContext(ScanConfig.class)) {
    System.out.println(ctx.containsBean("pilotJob"));
    System.out.println(ctx.containsBean("blockedJob"));
}
```

Đoạn này tái sử dụng `ScanConfig` trong ví dụ `FilterDemo`, có thể đặt trong package `demo` với import context tương ứng. Kết quả `true` rồi `false` xác minh **sự có mặt theo bean name**, không tự chứng minh mọi logic chọn đúng nếu tên bean đã được đổi.

### 17.2. Kiểm tra theo type

```java
var names = ctx.getBeanNamesForType(Job.class);
java.util.Arrays.sort(names);
for (String name : names) {
    System.out.println(name);
}
```

Đây là snippet để đặt bên trong vùng còn sống của `ctx` và dùng `Job` từ demo. Sắp xếp chỉ giúp test deterministic. Với cấu hình ví dụ gốc, tên kết quả là `directJob` rồi `pilotJob`.

### 17.3. Đọc nguồn gốc bean definition

Trong các test điều tra lỗi, có thể dùng:

```java
var factory = ctx.getBeanFactory();
var definition = factory.getBeanDefinition("pilotJob");

System.out.println(definition.getBeanClassName());
System.out.println(definition.getResourceDescription());
```

Đây là đoạn minh họa trong cùng context `AnnotationConfigApplicationContext` của demo. `getResourceDescription()` có thể trả mô tả resource hoặc `null` tùy cách đăng ký, nên không nên đặt stdout cố định cho nó. Với bean được component scan, mô tả resource thường gợi ra file/class đã được phát hiện. Giá trị này hữu ích để truy nguồn, không phải hợp đồng output nghiệp vụ.

### 17.4. Test theo ma trận cấu hình

| Thao tác | `PilotJob` | `DirectJob` | `BlockedJob` | `RegularJob` |
| --- | --- | --- | --- | --- |
| Bản gốc: default=false, 2 include, 1 exclude | Có | Có | Không | Không |
| Bỏ exclude | Có | Có | Có | Không |
| Chuyển default=true, giữ include/exclude | Có | Có | Không | Có |
| Bỏ include `DirectJob`, giữ default=false | Có | Không | Không | Không |
| Xóa mọi include, giữ default=false | Không | Không | Không | Không |

Ma trận mô tả **sự phát hiện bởi lượt scan đang xét**. `ScanConfig` vẫn được đăng ký trực tiếp, và những bean từ cấu hình khác (nếu thêm) có thể thay đổi danh sách thực tế.

**Nên test ở hai mức:** đơn vị cho custom `TypeFilter` (tập metadata nào match), và integration với `AnnotationConfigApplicationContext` để kiểm tra bean definition và dependency thật. Nếu test sửa cấu hình scan, dựng **context mới** cho mỗi biến thể thay vì kỳ vọng context đã refresh tự quét lại.

## 18. Câu hỏi tự luyện

**Câu 1.** Một cấu hình khai báo `includeFilters = @Filter(Experimental.class)` nhưng không ghi `useDefaultFilters`. Vì sao bean `@Service` thường vẫn xuất hiện?

**Đáp:** Vì default là `true`. Include filter **bổ sung** ứng viên vào các stereotype mặc định thay vì thu hẹp chúng.

**Câu 2.** Cần quét duy nhất class mang `@Pilot`, kể cả class không có `@Component`. Cấu hình nào thể hiện đúng ý định?

**Đáp:** `useDefaultFilters=false` và `includeFilters=@Filter(type=ANNOTATION,classes=Pilot.class)`, với base package phù hợp. Class vẫn phải đủ điều kiện là component candidate và được đăng ký thành công.

**Câu 3.** Nếu class vừa match include vừa match exclude, điều gì xảy ra?

**Đáp:** Class bị loại khỏi lượt scan vì exclude có quyền phủ quyết.

**Câu 4.** Vì sao `excludeFilters` không bảo đảm không bao giờ có một bean cùng type trong container?

**Đáp:** Bean có thể được đăng ký qua `@Bean`, `@Import`, auto-configuration hoặc lượt scan khác. Exclude chỉ giới hạn một quá trình scan.

**Câu 5.** `FilterType.REGEX` so sánh với `getBean("beanName")` hay `package.ClassName`?

**Đáp:** So sánh với **tên class đầy đủ** ở metadata, không phải tên bean do Spring đặt.

**Câu 6.** `ASSIGNABLE_TYPE` với một interface có tự tạo instance interface?

**Đáp:** Không. Nó có thể chọn các class implementation đủ điều kiện trong base packages; interface tự nó không thể được constructor-instantiate như concrete component.

**Câu 7.** Nếu muốn điều kiện “class có cả hai annotation A và B” thì thêm hai include filters có đủ không?

**Đáp:** Không, các include được kết hợp theo OR. Có thể viết một custom `TypeFilter` kiểm tra đồng thời A và B hoặc tổ chức lại marker annotation.

**Câu 8.** Trong `FilterDemo`, vì sao `RegularJob` mang `@Service` nhưng `containsBean("regularJob")` trả false?

**Đáp:** `useDefaultFilters=false` tắt stereotype mặc định, còn hai include chỉ chọn `Pilot` và `DirectJob`. `RegularJob` không khớp include.

**Câu 9.** Filter `ASPECTJ` có tự biến class thành aspect không?

**Đáp:** Không. Nó dùng cú pháp type pattern để lựa chọn class lúc scan, không bật Spring AOP hay áp lời khuyên lên method.

**Câu 10.** Khi một custom filter gây thời gian startup dài, nên kiểm tra gì?

**Đáp:** Xem `TypeFilter.match()` có thực hiện IO, network, nạp class, reflection tốn kém hoặc xử lý lại metadata liên tục không; ưu tiên xử lý thông tin từ `MetadataReader` một cách nhanh, không side effect.

## 19. Tài liệu chính thức để đối chiếu

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): các filter types, ví dụ include/exclude, `useDefaultFilters` và cấu hình XML.
- [Spring Framework 6.2 — ComponentScan API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/ComponentScan.html): `includeFilters`, `excludeFilters`, `useDefaultFilters`, phạm vi scan và mặc định.
- [Spring Framework 6.2 — ComponentScan.Filter API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/ComponentScan.Filter.html): `classes`, `pattern`, `type` và quy tắc nhiều type.
- [Spring Framework 6.2 — FilterType API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/FilterType.html): năm lựa chọn ANNOTATION, ASSIGNABLE_TYPE, ASPECTJ, REGEX, CUSTOM.
- [Spring Framework — TypeFilter API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/core/type/filter/TypeFilter.html): hợp đồng triển khai matcher tự tạo.

**Ghi nhớ:** Với `@ComponentScan`, **package xác định phạm vi**, `includeFilters` bổ sung cách nhận diện, `excludeFilters` loại ứng viên và `useDefaultFilters=false` tắt phát hiện component/stereotype mặc định. Muốn dự đoán chính xác một bean có xuất hiện hay không, phải nhìn cả **filter**, **điều kiện ứng viên** và **mọi đường đăng ký bean** khác trong context.
