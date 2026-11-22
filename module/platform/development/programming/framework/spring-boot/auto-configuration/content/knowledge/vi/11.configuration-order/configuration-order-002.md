# before, after, beforeName và afterName trên @AutoConfiguration

## 1. Mục tiêu và tình huống cần giải quyết

Trong một ứng dụng Spring Boot, nhiều lớp auto-configuration có thể cùng tham gia đăng ký bean. Một lớp có thể cung cấp bean nền tảng; lớp khác chỉ muốn đăng ký bean tích hợp **nếu bean nền tảng đó đã được khai báo**. Lúc này, thứ tự xử lý các **lớp auto-configuration** là một phần quan trọng của kết quả.

Spring Boot 3.3 cung cấp bốn thuộc tính ngay trên `@AutoConfiguration` để diễn đạt quan hệ thứ tự:

- `before`: áp dụng auto-configuration hiện tại **trước** một hoặc nhiều auto-configuration được tham chiếu bằng `Class`.
- `after`: áp dụng auto-configuration hiện tại **sau** một hoặc nhiều auto-configuration được tham chiếu bằng `Class`.
- `beforeName`: tương tự `before` nhưng tham chiếu bằng **tên lớp đầy đủ** (`String`).
- `afterName`: tương tự `after` nhưng tham chiếu bằng **tên lớp đầy đủ** (`String`).

Sau bài này, bạn cần: chọn được đúng thuộc tính; hiểu vì sao có bản `Class` và bản `String`; biết ranh giới giữa thứ tự đăng ký bean definition với thứ tự tạo bean; đọc đúng tên lớp lồng nhau dùng ký tự `$`; kiểm thử xem điều kiện bean phụ thuộc thứ tự có cho kết quả dự kiến hay không.

**Phạm vi:** bài chỉ nói về thứ tự **auto-configuration** trong Spring Boot 3.3.x, không định nghĩa lại thứ tự của component scanning, lifecycle của mọi bean hoặc thứ tự gọi các phương thức Java.

## 2. Spring Boot tải và sắp xếp auto-configuration như thế nào?

Với starter hoặc thư viện tự cung cấp auto-configuration, các lớp đủ điều kiện được liệt kê trong tài nguyên:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ:

```text
com.acme.autoconfigure.CacheAutoConfiguration
com.acme.autoconfigure.MetricsAutoConfiguration
com.acme.autoconfigure.CacheMetricsAutoConfiguration
```

Spring Boot thu thập ứng viên từ các file `AutoConfiguration.imports` có trên classpath, xét cơ chế loại trừ/điều kiện và áp dụng quy tắc sắp xếp. Thuộc tính `before`/`after` cùng hai biến thể `Name` đóng vai trò **gợi ý thứ tự tương đối** cho các auto-configuration được chọn.

**Không thiết kế thứ tự phụ thuộc vào thứ tự dòng trong `AutoConfiguration.imports`.** File dùng để **khai báo ứng viên**, còn quan hệ “cấu hình nào trước cấu hình nào” nên được viết rõ bằng thuộc tính thứ tự.

Một trình tự khái niệm:

```text
AutoConfiguration.imports
           |
           v
  Tập ứng viên auto-configuration
           |
           v
  Áp dụng metadata và quy tắc before/after
           |
           v
  Xử lý cấu hình, đăng ký bean definitions
           |
           v
  Khởi tạo bean khi context cần
           ^
           |
  Phụ thuộc bean / @DependsOn tác động tại đây
```

**Ranh giới bắt buộc nhớ:** tài liệu Spring Boot nói rằng thứ tự áp dụng auto-configuration chỉ ảnh hưởng đến **thứ tự bean definition được định nghĩa**. Thứ tự các instance bean được khởi tạo về sau được quyết định bởi quan hệ phụ thuộc của bean và `@DependsOn`, không được bảo đảm chỉ bằng `before` hoặc `after`.

Vì sao thứ tự định nghĩa vẫn có ý nghĩa? `@ConditionalOnBean` và `@ConditionalOnMissingBean` quan sát các bean definition **đã được xử lý tới thời điểm điều kiện được xét**. Khi một auto-configuration thực sự phụ thuộc định nghĩa của cấu hình khác, quan hệ thứ tự rõ ràng giúp tránh bỏ sót bean.

## 3. Bốn thuộc tính: bảng đối chiếu

Giả sử lớp đang viết là `CurrentAutoConfiguration` và lớp được nhắc tới là `TargetAutoConfiguration`.

| Thuộc tính trên `CurrentAutoConfiguration` | Loại dữ liệu | Ý nghĩa khi cả hai là ứng viên | Ví dụ |
| --- | --- | --- | --- |
| `before` | `Class<?>[]` | `Current` được áp dụng trước `Target` | `@AutoConfiguration(before = TargetAutoConfiguration.class)` |
| `after` | `Class<?>[]` | `Current` được áp dụng sau `Target` | `@AutoConfiguration(after = TargetAutoConfiguration.class)` |
| `beforeName` | `String[]` | `Current` được áp dụng trước auto-configuration có tên lớp đó | `@AutoConfiguration(beforeName = "com.acme.TargetAutoConfiguration")` |
| `afterName` | `String[]` | `Current` được áp dụng sau auto-configuration có tên lớp đó | `@AutoConfiguration(afterName = "com.acme.TargetAutoConfiguration")` |

Tất cả mặc định là mảng rỗng `{}`; không khai báo thuộc tính nghĩa là không thêm quan hệ tương ứng. Mỗi thuộc tính nhận được **nhiều phần tử**:

```java
@AutoConfiguration(
    after = {CoreAutoConfiguration.class, StorageAutoConfiguration.class},
    beforeName = {"com.acme.optional.ReportingAutoConfiguration"}
)
public class IntegrationAutoConfiguration {
    // Bean definitions ...
}
```

Đây là **snippet minh họa**; các lớp `CoreAutoConfiguration`, `StorageAutoConfiguration` và `IntegrationAutoConfiguration` được giả định tồn tại. Khi các lớp đích cùng được chọn, `IntegrationAutoConfiguration` cần đứng sau hai lớp đầu, đồng thời đứng trước `ReportingAutoConfiguration`. Nếu một lớp tham chiếu **không phải ứng viên được áp dụng**, khai báo quan hệ thứ tự không tự thêm hay tự kích hoạt lớp đó.

Trong Spring Boot 3.3, bốn thuộc tính là các **alias** của annotation chuyên dụng:

- `before` ↔ `@AutoConfigureBefore(value = ...)`.
- `beforeName` ↔ `@AutoConfigureBefore(name = ...)`.
- `after` ↔ `@AutoConfigureAfter(value = ...)`.
- `afterName` ↔ `@AutoConfigureAfter(name = ...)`.

Với code mới dùng `@AutoConfiguration`, khai báo trực tiếp một trong bốn thuộc tính thường rõ ràng hơn; không cần lặp cả thuộc tính và annotation chuyên dụng để diễn đạt cùng một quan hệ.

### 3.1. Cách hiểu `before`

```java
@AutoConfiguration(before = SearchClientAutoConfiguration.class)
public class SearchTransportAutoConfiguration {
    // Khai báo transport dùng cho search client.
}
```

Ý nghĩa: nếu `SearchClientAutoConfiguration` được chọn, xử lý `SearchTransportAutoConfiguration` trước nó. Đây là quan hệ “**tôi đứng trước lớp đích**”, chứ không có nghĩa lớp đích bị loại bỏ hoặc bean transport chắc chắn được khởi tạo đầu tiên.

### 3.2. Cách hiểu `after`

```java
@AutoConfiguration(after = SearchTransportAutoConfiguration.class)
public class SearchClientAutoConfiguration {
    // Khai báo search client phụ thuộc vào transport.
}
```

Ý nghĩa: nếu `SearchTransportAutoConfiguration` được chọn, xử lý `SearchClientAutoConfiguration` sau. Bạn có thể chọn khai báo `before` ở bên cung cấp hoặc `after` ở bên tiêu thụ tùy bên nào nắm rõ dependency; trong đa số trường hợp **một quan hệ rõ ràng là đủ**.

**Không hiểu `after` như `@DependsOn`.** Nó cũng không có nghĩa Spring Boot sẽ chờ một kết nối mạng hoạt động hoặc chờ bean của cấu hình đích đã khởi tạo xong.

## 4. Vì sao có `beforeName` và `afterName`?

Hai thuộc tính này diễn đạt **cùng loại quan hệ thứ tự** nhưng dùng tên lớp `String` thay vì tham chiếu lớp `Class`.

```java
@AutoConfiguration(
    afterName = "org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration"
)
public class MyMvcIntegrationAutoConfiguration {
    // Phần tích hợp MVC được đăng ký sau auto-configuration tương ứng.
}
```

`afterName` phù hợp khi mã của bạn muốn nhắc tới một auto-configuration từ thư viện tùy chọn hoặc không muốn ràng buộc trực tiếp việc **biên dịch** vào lớp đích. Nó cũng có ích khi hai starter do các nhóm khác nhau phát triển, hoặc khi dùng tên lớp từ dependency không nhất thiết có trong mọi phiên bản tổ hợp.

**Tên phải là tên class Java đầy đủ (fully qualified class name)**, không phải tên bean, tên package, tên module Maven hay tên file. Ví dụ:

- Đúng với lớp top-level: `"com.acme.search.SearchAutoConfiguration"`.
- Đúng với lớp lồng: `"com.acme.search.SearchModule$TransportAutoConfiguration"`.
- Sai nếu muốn tham chiếu lớp lồng: `"com.acme.search.SearchModule.TransportAutoConfiguration"`.
- Sai nếu chỉ ghi bean name: `"searchClient"`.

Với lớp lồng, ký tự `$` là quy ước tên nhị phân cần dùng trong các string tham chiếu và trong `AutoConfiguration.imports`.

### 4.1. Khi nào dùng Class, khi nào dùng tên String?

- **Dùng `before` / `after`** khi code của bạn chủ động biết lớp auto-configuration đích và có thể tham chiếu lớp đó khi biên dịch. Công cụ IDE dễ điều hướng và hỗ trợ kiểm tra tên khi đổi class.
- **Dùng `beforeName` / `afterName`** khi muốn biểu đạt quan hệ với auto-configuration tùy chọn mà không khai báo class trực tiếp trong mã nguồn. Cần tự kiểm tra chuỗi có khớp tên Java thực tế sau refactor.
- **Nếu lớp đích không có mặt** hoặc không được nhập thành auto-configuration, quan hệ thứ tự với nó không có đối tượng để áp dụng. Không có cơ chế “tìm và tải dependency” phát sinh từ bốn thuộc tính này.

**Một giới hạn quan trọng:** `afterName` không thay thế `@ConditionalOnClass`. Nếu tính năng tích hợp yêu cầu class của thư viện khác, hãy thêm điều kiện class phù hợp và cô lập những bean/method tham chiếu class tùy chọn. Thứ tự và điều kiện tồn tại thư viện là **hai trách nhiệm khác nhau**.

Ví dụ cho tích hợp tùy chọn:

```java
@AutoConfiguration(
    afterName = "org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration"
)
@ConditionalOnClass(name = "org.springframework.web.servlet.DispatcherServlet")
public class MyOptionalMvcAutoConfiguration {
    // Các bean MVC thuộc cấu hình này ...
}
```

Đây là **snippet minh họa**; dự án thực tế phải có các dependency và mã bean tương ứng. `afterName` chỉ sắp xếp tương đối khi auto-configuration MVC thực sự được áp dụng; `@ConditionalOnClass` mới kiểm tra class yêu cầu.

## 5. Quan hệ thứ tự là tương đối, không tạo lịch chạy toàn cục

Có thể hình dung bốn thuộc tính như khai báo các cạnh của đồ thị có hướng:

```text
@AutoConfiguration(before = B.class) trên A:   A ---> B

@AutoConfiguration(after = B.class) trên C:    B ---> C

Khi cả ba cùng được áp dụng:               A ---> B ---> C
```

Đây không phải câu lệnh “chạy A, hoàn thành toàn bộ bean A, rồi chạy B”. Thứ tự xử lý auto-configuration cần tuân theo quan hệ đã nêu, nhưng giữa các lớp **không có quan hệ trực tiếp** có thể tồn tại nhiều thứ tự hợp lệ khác nhau.

Ví dụ:

```text
A ---> B ---> C       D (không có ràng buộc với A/B/C)
```

Không nên kết luận D luôn đứng trước hay sau A/B/C. Nếu việc thiết lập đúng phụ thuộc vào D, hãy khai báo quan hệ với D. Tránh tạo chu trình kiểu `A before B` và `B before A` vì các yêu cầu mâu thuẫn nhau, khó duy trì và không phản ánh phụ thuộc hợp lệ của hệ thống.

### 5.1. Quan hệ thứ tự không ép điều kiện của đích thành true

Giả sử `B` được đăng ký sau `A` theo `after = A.class`, nhưng A có:

```java
@AutoConfiguration
@ConditionalOnProperty(prefix = "sample", name = "enabled",
                       havingValue = "true")
public class A {
    // Bean của A ...
}
```

Nếu `sample.enabled=false`, A không tạo bean theo cấu hình đó. Điều kiện `@ConditionalOnBean` trong B vẫn có thể không khớp; **đặt thứ tự không làm mất hiệu lực các điều kiện**. Trường hợp đích không nằm trong `AutoConfiguration.imports` cũng không được tự đưa vào chỉ vì bị nhắc trong `before`/`after`.

## 6. Ví dụ Java 17+ chạy độc lập: quan sát cả bốn thuộc tính

Để quan sát tác động của mỗi thuộc tính một cách riêng biệt, ví dụ này tạo **bốn cặp** auto-configuration. Trong mỗi cặp, “source” đăng ký một bean nguồn; “target” chỉ đăng ký bean kết quả khi đã nhìn thấy bean nguồn qua `@ConditionalOnBean(name = ...)`.

Điểm cố ý của bài thực hành: file `AutoConfiguration.imports` **liệt kê target trước source** để thể hiện cách các khai báo `before`/`after` mang ý nghĩa độc lập với thứ tự dòng trong file. Ta kiểm tra trạng thái bean sau khi context được tạo, **không dùng thứ tự in của constructor làm bằng chứng**.

Dùng **Spring Boot 3.3.13**, **JDK 17+**, **Maven 3.8+**. Cấu trúc:

```text
auto-configuration-order-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── OrderDemo.java
        └── resources/
            └── META-INF/
                └── spring/
                    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>auto-configuration-order-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
            <version>3.3.13</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/OrderDemo.java`:

```java
package demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
public class OrderDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(OrderDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println(
                "before=" + context.containsBean("beforeResult")
            );
            System.out.println(
                "after=" + context.containsBean("afterResult")
            );
            System.out.println(
                "beforeName=" + context.containsBean("beforeNameResult")
            );
            System.out.println(
                "afterName=" + context.containsBean("afterNameResult")
            );
        }
    }

    // CẶP 1: before (Class reference).
    @AutoConfiguration(before = BeforeTarget.class)
    public static class BeforeSource {
        @Bean("beforeSeed")
        String beforeSeed() {
            return "available";
        }
    }

    @AutoConfiguration
    public static class BeforeTarget {
        @Bean("beforeResult")
        @ConditionalOnBean(name = "beforeSeed")
        String beforeResult() {
            return "matched";
        }
    }

    // CẶP 2: after (Class reference).
    @AutoConfiguration
    public static class AfterSource {
        @Bean("afterSeed")
        String afterSeed() {
            return "available";
        }
    }

    @AutoConfiguration(after = AfterSource.class)
    public static class AfterTarget {
        @Bean("afterResult")
        @ConditionalOnBean(name = "afterSeed")
        String afterResult() {
            return "matched";
        }
    }

    // CẶP 3: beforeName (tên lớp đầy đủ, dùng ký tự $).
    @AutoConfiguration(beforeName = "demo.OrderDemo$BeforeNameTarget")
    public static class BeforeNameSource {
        @Bean("beforeNameSeed")
        String beforeNameSeed() {
            return "available";
        }
    }

    @AutoConfiguration
    public static class BeforeNameTarget {
        @Bean("beforeNameResult")
        @ConditionalOnBean(name = "beforeNameSeed")
        String beforeNameResult() {
            return "matched";
        }
    }

    // CẶP 4: afterName (tên lớp đầy đủ, dùng ký tự $).
    @AutoConfiguration
    public static class AfterNameSource {
        @Bean("afterNameSeed")
        String afterNameSeed() {
            return "available";
        }
    }

    @AutoConfiguration(afterName = "demo.OrderDemo$AfterNameSource")
    public static class AfterNameTarget {
        @Bean("afterNameResult")
        @ConditionalOnBean(name = "afterNameSeed")
        String afterNameResult() {
            return "matched";
        }
    }
}
```

File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
# Mỗi cặp cố ý liệt kê target trước source.
demo.OrderDemo$BeforeTarget
demo.OrderDemo$BeforeSource

demo.OrderDemo$AfterTarget
demo.OrderDemo$AfterSource

demo.OrderDemo$BeforeNameTarget
demo.OrderDemo$BeforeNameSource

demo.OrderDemo$AfterNameTarget
demo.OrderDemo$AfterNameSource
```

**Vì sao dùng lớp nested?** Để giữ ví dụ trong một file Java. Spring Boot 3.3 cho phép class auto-configuration lồng nhau nếu trong imports file dùng tên nhị phân có `$`. Dự án starter thật thường đặt mỗi `@AutoConfiguration` ở một lớp top-level riêng để rõ ràng hơn.

**Vì sao dùng `@SpringBootConfiguration` + `@EnableAutoConfiguration`?** Cách này kích hoạt cơ chế tự nhập auto-configuration mà không bật component scanning cho package `demo`. Auto-configuration được nạp qua imports file theo đúng ranh giới trong tài liệu, tránh để component scanning vô tình phát hiện các lớp nested và làm sai ý nghĩa bài thử.

Chạy từ thư mục `auto-configuration-order-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.OrderDemo
```

Bốn dòng do chương trình in ra (bỏ qua dòng log do môi trường Spring/Maven bổ sung):

```text
before=true
after=true
beforeName=true
afterName=true
```

**Đọc kết quả:**

1. `before=true`: `BeforeSource` được sắp xếp trước `BeforeTarget` nhờ `before = BeforeTarget.class`. Vì vậy khi điều kiện trong target đánh giá, bean definition tên `beforeSeed` đã được xử lý.
2. `after=true`: `AfterTarget` được sắp xếp sau `AfterSource` nhờ `after = AfterSource.class`. Điều kiện tên `afterSeed` khớp.
3. `beforeName=true`: `BeforeNameSource` tham chiếu target bằng chuỗi `"demo.OrderDemo$BeforeNameTarget"`. Quan hệ thứ tự hoạt động tương tự `before` dù không có class literal.
4. `afterName=true`: `AfterNameTarget` tham chiếu source bằng chuỗi `"demo.OrderDemo$AfterNameSource"`. Bean definition `afterNameSeed` được xét trước target.

Với thử nghiệm này, các bean kết quả chỉ được đăng ký khi bean nguồn đã nằm trong tập định nghĩa được kiểm tra; việc cả bốn bean kết quả tồn tại **chứng minh điều kiện bean nhìn thấy source trong kịch bản chạy**, chứ không đo thời điểm khởi tạo đối tượng.

**Giới hạn của ví dụ:** output trên là kết quả kỳ vọng từ logic và quy tắc Spring Boot 3.3. Nếu bạn muốn kiểm chứng trong môi trường hiện tại, hãy thực hiện lệnh Maven và kiểm tra bốn dòng đầu ra của `OrderDemo`; thông báo tải dependency/log có thể khác nhau giữa máy. Không dựa vào việc xóa thuộc tính rồi chạy một lần để chứng minh chắc chắn sai: khi không có quan hệ tường minh, thứ tự mặc định trong một môi trường cụ thể có thể vẫn tình cờ phù hợp.

## 7. Thứ tự auto-configuration khác thứ tự khởi tạo bean

Xét hai câu hỏi:

**Câu hỏi A:** “Khi đánh giá `@ConditionalOnBean(PaymentGateway.class)` ở auto-configuration B, Spring đã biết định nghĩa bean `PaymentGateway` từ auto-configuration A hay chưa?”

→ Liên quan đến **thứ tự áp dụng auto-configuration**, nên `@AutoConfiguration(after = A.class)` trên B có thể là một khai báo đúng, nếu A là nhà cung cấp định nghĩa đó.

**Câu hỏi B:** “Khi tạo bean `OrderService`, bean `PaymentGateway` đã được tạo xong chưa?”

→ Đây là **quan hệ phụ thuộc khi tạo bean**. Khai báo dependency trực tiếp qua tham số `@Bean` hoặc constructor:

```java
@Bean
OrderService orderService(PaymentGateway gateway) {
    return new OrderService(gateway);
}
```

Snippet này giả định hai kiểu `OrderService` và `PaymentGateway` tồn tại. Spring sẽ giải quyết dependency cho việc tạo `OrderService`. Nếu chỉ cần yêu cầu bean `metricsBootstrap` khởi tạo trước một bean khác mà không có dependency kiểu thông thường, có thể dùng `@DependsOn("metricsBootstrap")` sau khi cân nhắc thiết kế lifecycle.

**Không lấy `before` / `after` để giải quyết bài toán B.** Ngược lại, `@DependsOn` cũng không thay thế được metadata thứ tự để làm cho condition của auto-configuration “nhìn thấy” những định nghĩa bean được xử lý sau.

## 8. Thực hành trong starter và cách kiểm thử

Khi xây dựng starter có hai auto-configuration phụ thuộc nhau:

1. Viết rõ lớp nào **cung cấp bean definition** và lớp nào cần định nghĩa đó để quyết định `@ConditionalOnBean`/`@ConditionalOnMissingBean`.
2. Chọn **một điểm khai báo quan hệ** dễ hiểu, thường là `after` tại lớp tiêu thụ. Nếu dependency là tùy chọn hoặc không muốn liên kết trực tiếp khi biên dịch, dùng `afterName` với tên FQCN đã kiểm tra.
3. Đưa mỗi auto-configuration do starter sở hữu vào file `AutoConfiguration.imports`. Không dựa vào component scanning; đừng dùng `@ComponentScan` bên trong auto-configuration để tự quét một vùng tùy ý.
4. Thêm điều kiện khả dụng của thư viện (`@ConditionalOnClass`, `@ConditionalOnProperty` khi phù hợp). Thuộc tính thứ tự không có chức năng bật/tắt thư viện hoặc bảo đảm bean được tạo.
5. Kiểm thử cả khi có và không có auto-configuration đích, khi điều kiện của đích true/false, khi có bean người dùng định nghĩa, và khi lớp tùy chọn vắng mặt. Với Spring Boot, `ApplicationContextRunner` cùng `AutoConfigurations.of(...)` là cách kiểm thử gọn; trong nhiều auto-configuration, Boot dùng cùng quy tắc thứ tự như khi ứng dụng chạy thật.

Để kiểm tra một ứng dụng thực tế, bật `--debug` hoặc dùng `ConditionEvaluationReport` để biết vì sao bean condition khớp/không khớp. Kết hợp với việc xem metadata `@AutoConfiguration` và các tên trong imports file. Condition report nói về **kết quả điều kiện**, không phải trình tự chính xác các instance được tạo.

### 8.1. Khi nào dùng `@AutoConfigureOrder`?

`@AutoConfigureOrder` hỗ trợ mức ưu tiên tổng quát giữa các auto-configuration không muốn biết trực tiếp về nhau, tương tự ý nghĩa thứ tự của `@Order` nhưng được thiết kế riêng cho auto-configuration. Với phụ thuộc cụ thể kiểu “cấu hình B cần định nghĩa của A trước”, **quan hệ `after`/`afterName` rõ ràng hơn một con số ưu tiên mơ hồ**.

Không nên suy luận rằng thêm `@Order(1)` vào mọi lớp hoặc sắp lại các dòng trong imports file sẽ thay cho các quan hệ `before`/`after`. Cũng đừng dùng số ưu tiên để giải quyết vấn đề khởi tạo bean vốn cần dependency thực sự.

## 9. Lỗi phổ biến

| Cách làm sai hoặc hiểu nhầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `after = X.class` đảm bảo bean của X được tạo trước | `after` nói về xử lý auto-configuration/định nghĩa bean, không đảm bảo thời điểm khởi tạo instance | Dùng injection/constructor hoặc `@DependsOn` để diễn đạt dependency khi tạo bean |
| `afterName = "myBean"` | `afterName` cần **tên lớp auto-configuration**, không phải tên bean | Dùng `"com.acme.MyAutoConfiguration"` |
| Dùng dấu `.` thay `$` cho class nested trong chuỗi | Java binary name của nested class dùng `$` | Dùng `Outer$InnerAutoConfiguration` |
| Đọc thứ tự dòng trong imports file như thứ tự khởi tạo | Imports file dùng để liệt kê ứng viên; Boot áp dụng sorting metadata | Khai báo `before`/`after`; dùng bean dependencies cho lifecycle |
| Cho rằng `beforeName` tự thêm auto-configuration đích | Thuộc tính thứ tự không import dependency hoặc bỏ qua condition của đích | Bảo đảm đích được đăng ký qua imports file nếu cần |
| Đặt `before` và `after` tạo vòng lặp | Không có thứ tự hợp lệ để thỏa tất cả quan hệ | Thiết kế lại phụ thuộc để loại chu trình |
| Tưởng `@ConditionalOnBean` luôn nhìn thấy bean từ mọi auto-configuration | Condition đánh giá theo các bean definition đã được xử lý | Xác định cấu hình cung cấp bean và khai báo thứ tự hợp lệ |
| Dùng `Class` reference cho thư viện tùy chọn mà không xem dependency build | Có thể tạo liên kết biên dịch không mong muốn | Cân nhắc `beforeName`/`afterName` và `@ConditionalOnClass` đúng vị trí |
| Lấy `@AutoConfigureOrder` thay quan hệ phụ thuộc chính xác | Mức ưu tiên không diễn tả đối tượng mà B cần | Với quan hệ A → B, đặt `after = A.class` hoặc `afterName` ở B |
| Auto-configuration bị component scan | Có thể không đi qua cơ chế ứng viên và sắp xếp auto-configuration như dự định | Chỉ nhập qua `AutoConfiguration.imports` và vùng package riêng |

## 10. Bài tự kiểm tra

**Câu 1.** Có `@AutoConfiguration(after = DatabaseAutoConfiguration.class)` trên `AuditAutoConfiguration`. Điều gì được cam kết?  
**Đáp án:** Khi cả hai được áp dụng như auto-configuration, `DatabaseAutoConfiguration` được xử lý trước `AuditAutoConfiguration` để đăng ký bean definitions; **không** cam kết mọi database bean đã khởi tạo trước mọi audit bean.

**Câu 2.** Bạn cần tương thích với starter tùy chọn có auto-configuration `com.vendor.cloud.CloudAutoConfiguration` nhưng không muốn import lớp đó vào mã nguồn. Chọn thuộc tính nào nếu cấu hình bạn viết phải áp dụng **sau** nó?  
**Đáp án:** `afterName = "com.vendor.cloud.CloudAutoConfiguration"`, đồng thời thêm các condition cần thiết cho class/tính năng tùy chọn. Nếu đích vắng mặt thì thuộc tính này không tự tải đích.

**Câu 3.** Class đích là `com.acme.Main$NestedAutoConfiguration`. Có thể dùng `afterName = "com.acme.Main.NestedAutoConfiguration"` không?  
**Đáp án:** Không đúng định dạng tên nhị phân cho class nested; dùng `afterName = "com.acme.Main$NestedAutoConfiguration"`.

**Câu 4.** A khai báo `before = B.class`, C khai báo `after = B.class`. Quan hệ nào được xác định? D ở đâu nếu không khai báo?  
**Đáp án:** `A → B → C` khi cả ba cùng được áp dụng. D không có vị trí cố định tương đối với chuỗi đó.

**Câu 5.** Có `@AutoConfiguration(after = A.class)`, nhưng A bị `@ConditionalOnClass` loại bỏ. Điều kiện `@ConditionalOnBean` trong B có tự khớp nhờ `after` không?  
**Đáp án:** Không. `after` chỉ biểu đạt thứ tự của ứng viên có mặt; không khiến A đăng ký bean khi điều kiện của A không thỏa.

**Câu 6.** Lớp `InventoryAutoConfiguration` cần tạo một bean sau khi `CacheWarmup` hoàn thành khởi tạo. Nên chọn `after = CacheAutoConfiguration.class` hay khai báo dependency của bean?  
**Đáp án:** Quan hệ phụ thuộc khi khởi tạo bean; dùng injection/constructor hoặc `@DependsOn` theo thiết kế. `after` chỉ giải quyết thứ tự áp dụng auto-configuration.

## 11. Ghi nhớ và tài liệu tham khảo

- `before` / `after` dùng `Class`, `beforeName` / `afterName` dùng tên lớp đầy đủ `String`; hai nhóm diễn đạt cùng quan hệ **trước/sau**.
- Thứ tự là **tương đối giữa các auto-configuration**. Thuộc tính thứ tự không tạo dependency, không chọn bean, không buộc condition thành true, không cam kết thứ tự tạo instance.
- Dùng `beforeName`/`afterName` cho tên lớp tùy chọn và nhớ `$` nếu class đích lồng trong class khác.
- Thứ tự bean definition có ý nghĩa với `@ConditionalOnBean`/`@ConditionalOnMissingBean` vì điều kiện chỉ xét những bean definition đã được biết ở thời điểm đó.
- Auto-configuration của starter phải được liệt kê trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Dùng `@AutoConfigureOrder` khi cần ưu tiên chung, và bean dependency/`@DependsOn` khi cần kiểm soát việc khởi tạo.

Tài liệu chính thức (Spring Boot 3.3.13):

1. [`@AutoConfiguration` Javadoc — `before`/`after`/`beforeName`/`afterName`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html).
2. [Creating Your Own Auto-configuration — locating candidates, ordering và bean conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
3. [`@AutoConfigureBefore` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html).
4. [`@AutoConfigureAfter` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html).
5. [`@AutoConfigureOrder` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html).