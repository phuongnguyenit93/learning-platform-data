# Giới hạn của việc loại trừ lớp cấu hình thông thường hoặc lớp lồng nhau nội bộ

## 1. Đề bài: loại trừ đúng thứ mà Spring Boot đang tự nạp

Trong Spring Boot, ứng dụng có thể có nhiều nguồn đăng ký cấu hình:

- **Auto-configuration** được Spring Boot phát hiện qua danh sách ứng viên và tự import.
- Lớp **`@Configuration` thông thường** do dự án khai báo qua `@Import`, component scan, hoặc đăng ký chủ động.
- Lớp **`@Configuration` lồng nhau** nằm bên trong một lớp cấu hình khác, được Spring xử lý trong quá trình phân tích cấu hình cha hoặc được import độc lập.

Khi dùng `@SpringBootApplication(exclude = ...)`, người mới học thường tưởng có thể đặt vào danh sách loại trừ **bất kỳ** class `@Configuration` nào. Đây là nhầm lẫn quan trọng: tính năng này chủ yếu loại những **auto-configuration candidates** được chọn bởi Spring Boot. Một lớp cấu hình thông thường hoặc lớp lồng nhau nội bộ của một auto-configuration không mặc nhiên là một ứng viên được loại trừ độc lập.

Mục tiêu của bài:

1. Phân biệt phạm vi loại trừ của `@SpringBootApplication(exclude/excludeName)`, `@EnableAutoConfiguration` và `spring.autoconfigure.exclude` với cơ chế import/scan thông thường.
2. Giải thích vì sao exclude một `@Configuration` thường hoặc một nested class nội bộ có thể gây lỗi hoặc không đạt mục đích.
3. Chọn **lớp auto-configuration cấp ngoài** ổn định khi cần loại bỏ cả tính năng, hoặc chọn điều kiện/cách import phù hợp khi chỉ muốn tắt một phần.
4. Chứng minh bằng ví dụ Java 17+ và Spring Boot 3.3, kèm bảng tình huống, cách gỡ lỗi và giới hạn cần nhớ.

## 2. Ba đường nạp cấu hình khác nhau

Xem mô hình khái quát:

```text
                    ApplicationContext
                           |
             +-------------+--------------+
             |             |              |
             v             v              v
   AutoConfiguration     @Import(...)   @ComponentScan
      .imports              |              |
             |             |              |
             v             v              v
   Auto-config candidate  @Configuration   @Configuration/
             |           thông thường      @Component
             |             |              |
       Exclude filter       |              |
       của Boot áp dụng     |              |
             |             |              |
             v             v              v
        Bean definitions sau khi các điều kiện/đăng ký hợp lệ
```

Cả ba đường có thể dẫn đến các bean definition trong cùng một context, nhưng **không dùng chung một bộ lọc loại trừ**.

### 2.1. Auto-configuration do Spring Boot tự tìm

Trong Spring Boot 3.3, thư viện/starter công bố các auto-configuration ứng viên trong tài nguyên:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ file này có:

```text
com.example.report.ReportAutoConfiguration
com.example.cache.CacheAutoConfiguration
```

Trong quá trình chạy `@EnableAutoConfiguration` (được `@SpringBootApplication` gộp sẵn), Boot thu thập danh sách ứng viên, áp dụng các điều kiện/bộ lọc, xử lý những class bị exclude, rồi import phần phù hợp. **Đối tượng của `exclude` là các ứng viên trong danh sách auto-configuration.**

Khai báo lớp bằng `@AutoConfiguration` là một phần của việc xây dựng auto-config, nhưng để Spring Boot tự tìm trong ứng dụng thực tế, class đó cần nằm trong `AutoConfiguration.imports` của một thư viện trên classpath. Không nên để auto-configuration bị component scan hoặc import thủ công cùng lúc.

### 2.2. @Configuration thông thường

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class BusinessConfiguration {
    @Bean
    BusinessService businessService() {
        return new BusinessService();
    }
}
```

Đây là **mã minh họa**, giả sử `BusinessService` đã được định nghĩa và các import cần thiết có mặt. Nếu `BusinessConfiguration` được đưa vào context bằng `@Import(BusinessConfiguration.class)` hoặc được component scan tìm thấy, nó là **cấu hình người dùng**. Nó không tự biến thành auto-configuration candidate chỉ vì có `@Configuration` và `@Bean`.

Do đó, cấu hình sau thường là **sai**:

```java
@SpringBootApplication(exclude = BusinessConfiguration.class)
public class Application {
}
```

Nếu class này hiện diện trên classpath nhưng **không** nằm trong danh sách auto-configuration candidates, Spring Boot 3.3 thường dừng lúc khởi động với `IllegalStateException`, nêu rằng class không thể bị loại vì không phải auto-configuration class. Exclude ở đây **không phải** một cách tổng quát để xóa mọi `@Configuration`.

### 2.3. Cấu hình lồng nhau nội bộ

Một auto-configuration có thể tổ chức logic thành các class static lồng nhau:

```java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class WriterConfiguration {
        @Bean
        ReportWriter reportWriter() {
            return new ReportWriter();
        }
    }
}
```

Đoạn này cũng là minh họa, giả sử `ReportWriter` tồn tại. `WriterConfiguration` là **chi tiết triển khai** nằm bên trong `ReportAutoConfiguration`. Nếu chỉ `ReportAutoConfiguration` được liệt kê trong `AutoConfiguration.imports`, class `WriterConfiguration` không trở thành **một mục độc lập** trong danh sách ứng viên.

Vì thế, cố gắng loại `ReportAutoConfiguration.WriterConfiguration.class` bằng `@SpringBootApplication(exclude = ...)` không phải cách được hỗ trợ cho cấu trúc này; nếu class lồng nhau có mặt nhưng không là auto-configuration candidate độc lập, Boot có thể báo lỗi “not auto-configuration classes”.

**Phạm vi public API được Spring Boot công bố để exclude là tên lớp auto-configuration**, không phải tên các bean method hoặc nested configuration nội bộ. Một phiên bản thư viện khác có thể đổi tên, chuyển hoặc xóa class nội bộ, khiến cấu hình dựa vào nội bộ bị vỡ.

## 3. Các cách exclude hợp lệ và giới hạn của từng cách

### 3.1. Dùng class khi có dependency trực tiếp

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class Application {
}
```

Đây là ví dụ hợp lệ để loại **auto-configuration ứng viên** `DataSourceAutoConfiguration`. Nó không tự động gỡ bỏ mọi bean datasource mà ứng dụng đã tạo bằng cách khác.

### 3.2. Dùng tên đầy đủ khi không muốn tham chiếu class

```java
@SpringBootApplication(
    excludeName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
public class Application {
}
```

Hoặc trong file `application.properties`:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Và với `@EnableAutoConfiguration` trực tiếp:

```java
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
public class Application {
}
```

Trong ba cách trên, Spring Boot vẫn đang thao tác với **tập auto-configuration được chọn**. `excludeName` dùng tên fully qualified dưới dạng chuỗi, tiện khi class có thể vắng mặt khỏi classpath biên dịch; nó **không mở rộng phạm vi** sang `@Configuration` thường hoặc nested internal class.

### 3.3. Không đánh đồng “class có annotation” với “ứng viên đang được Boot import”

| Đối tượng | Cơ chế nạp chính | Có phù hợp để dùng Spring Boot auto-configuration exclude? |
|---|---|---|
| `DataSourceAutoConfiguration` do Boot công bố | `AutoConfiguration.imports` | **Có** |
| Auto-config tùy chỉnh `ReportAutoConfiguration` được liệt kê trong imports | `AutoConfiguration.imports` | **Có** |
| `BusinessConfiguration` thường, được `@Import` trực tiếp | `@Import` | **Không** |
| `FeatureConfiguration` thường được component scan tìm thấy | `@ComponentScan` | **Không** |
| `ReportAutoConfiguration.WriterConfiguration` là nested class chỉ được phân tích thông qua lớp ngoài | Thành viên cấu hình nội bộ của auto-config cha | **Không** như một auto-config candidate độc lập |
| Nested class được tác giả **cố ý** công bố như một auto-config candidate riêng trong imports | `AutoConfiguration.imports` với tên JVM có `$` | **Về cơ chế có thể**, nhưng là trường hợp hiếm; chỉ dựa vào API tác giả công bố ổn định |
| Bean riêng do người dùng khai báo bằng `@Bean` | `@Configuration` hoặc đăng ký thủ công | Exclude auto-config không trực tiếp xóa bean đó |

**Ngoại lệ cần nói rõ:** Spring Boot cho phép trường hợp không thường gặp là **nested auto-configuration được đăng ký như một candidate độc lập**, với tên class JVM dùng `$` trong file imports. Khi đó có thể xét nó như một candidate thực sự. Điều này khác với những nested class nội bộ mà tác giả không công bố. Không thể kết luận “mọi nested class đều không bao giờ exclude được”; điều kiện cần là nó thuộc danh sách ứng viên của cơ chế đang lọc.

## 4. Vì sao loại trừ nested internal class là rủi ro?

Spring Boot có thể tổ chức logic của một auto-configuration như sau:

```text
ReportAutoConfiguration           <-- candidate được công bố
├── FileWriterConfiguration      <-- nested @Configuration nội bộ
│   ├── @Bean fileWriter()
│   └── @Bean fileFormatter()
└── NetworkWriterConfiguration   <-- nested @Configuration nội bộ
    └── @Bean networkWriter()
```

Người dùng thấy lỗi ở bean `fileWriter` và muốn viết:

```java
@SpringBootApplication(
    exclude = ReportAutoConfiguration.FileWriterConfiguration.class)
class Application {
}
```

Đây là **mã phản ví dụ**, giả định nested type truy cập được ở thời điểm biên dịch. Các hạn chế gồm:

1. Nếu `FileWriterConfiguration` không phải một mục riêng trong imports, exclude này không hợp lệ đối với bộ lọc của Boot.
2. Nhiều nested class trong thư viện là package-private/private, nên thậm chí **không thể tham chiếu bằng `.class`** từ code bên ngoài.
3. Dù truy cập được, tên và cấu trúc nested class **không phải public API được cam kết**, nên cập nhật thư viện có thể phá vỡ cách cấu hình dựa vào chi tiết nội bộ.
4. Nếu nested class được import hoặc phát hiện qua **một đường khác**, việc exclude outer auto-config không đảm bảo xóa bản đăng ký độc lập đó. Phải tìm và xử lý đúng đường nạp.

Nếu muốn tắt **toàn bộ auto-configuration**, dùng tên class cấp ngoài mà thư viện công bố:

```java
@SpringBootApplication(exclude = ReportAutoConfiguration.class)
class Application {
}
```

Nếu chỉ muốn tắt một **nhánh nhỏ** bên trong nó, hãy tìm thuộc tính cấu hình chính thức của thư viện, một `@ConditionalOnProperty`/`@ConditionalOnClass` phù hợp, hoặc cung cấp bean thay thế nếu auto-config có `@ConditionalOnMissingBean`. Exclude cả outer class có thể làm mất nhiều bean khác liên quan; cân nhắc phạm vi mong muốn trước khi chọn.

## 5. Ví dụ chạy được: exclude outer auto-config nhưng @Configuration thường vẫn tồn tại

Ví dụ này dùng **Java 17+** và **Spring Boot 3.3.x**. Ta tạo:

- Một auto-configuration được công bố qua `AutoConfiguration.imports`, có hai bean: một từ lớp ngoài và một từ nested internal configuration.
- Một `@Configuration` thông thường được `@Import`, cũng có một bean ở lớp ngoài và một bean từ nested configuration.
- Một ứng dụng loại trừ **outer auto-configuration**, rồi in sự tồn tại của bốn bean theo tên.

### 5.1. Cấu trúc dự án

```text
exclusion-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       ├── app/
    │       │   └── ExclusionDemoApplication.java
    │       ├── regular/
    │       │   └── RegularConfiguration.java
    │       └── autoconfigure/
    │           └── OptionalFeatureAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 5.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>exclusion-demo</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. RegularConfiguration.java

```java
package demo.regular;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RegularConfiguration {

    @Bean("regularMarker")
    String regularMarker() {
        return "from-regular-configuration";
    }

    @Configuration(proxyBeanMethods = false)
    public static class InternalConfiguration {

        @Bean("regularNestedMarker")
        String regularNestedMarker() {
            return "from-regular-nested-configuration";
        }
    }
}
```

Lớp `RegularConfiguration` không được khai báo là auto-configuration candidate. Spring Framework có thể tự xử lý `static` nested `@Configuration` như một phần của quá trình phân tích lớp cha; vì vậy khi cấu hình cha được import, `regularNestedMarker` được tạo cùng với `regularMarker`. Đây là cách nhóm bean definition của **cấu hình thông thường**, không phải một auto-config mới.

### 5.4. OptionalFeatureAutoConfiguration.java

```java
package demo.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class OptionalFeatureAutoConfiguration {

    @Bean("autoMarker")
    String autoMarker() {
        return "from-auto-configuration";
    }

    @Configuration(proxyBeanMethods = false)
    public static class InternalConfiguration {

        @Bean("autoNestedMarker")
        String autoNestedMarker() {
            return "from-auto-nested-configuration";
        }
    }
}
```

Lớp ngoài `OptionalFeatureAutoConfiguration` là auto-config. `InternalConfiguration` là lớp `@Configuration` lồng nhau dùng để chia nhóm bean bên trong. Trong bài này chỉ lớp ngoài được công bố như một candidate.

### 5.5. Công bố candidate

File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
demo.autoconfigure.OptionalFeatureAutoConfiguration
```

Không thêm `InternalConfiguration` vào file imports. Đây là điều kiện cốt lõi để phân biệt **lớp auto-config được công bố** với **lớp lồng nhau thuộc triển khai nội bộ**.

### 5.6. ExclusionDemoApplication.java

```java
package demo.app;

import demo.autoconfigure.OptionalFeatureAutoConfiguration;
import demo.regular.RegularConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;

@SpringBootApplication(exclude = OptionalFeatureAutoConfiguration.class)
@Import(RegularConfiguration.class)
public class ExclusionDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ExclusionDemoApplication.class, args)) {

            System.out.println("regularMarker="
                    + context.containsBean("regularMarker"));
            System.out.println("regularNestedMarker="
                    + context.containsBean("regularNestedMarker"));
            System.out.println("autoMarker="
                    + context.containsBean("autoMarker"));
            System.out.println("autoNestedMarker="
                    + context.containsBean("autoNestedMarker"));
        }
    }
}
```

Chú ý ba chi tiết thiết kế có chủ đích:

1. Ứng dụng nằm trong package `demo.app`. Component scan mặc định của `@SpringBootApplication` chỉ quét package đó và các package con; các class ở `demo.regular` hoặc `demo.autoconfigure` **không lọt vào context qua scan ngoài ý muốn**.
2. `RegularConfiguration` được thêm bằng `@Import`, một đường nạp độc lập với auto-configuration exclusion.
3. `OptionalFeatureAutoConfiguration` được công bố trong imports và bị exclude bằng đúng class **ứng viên** của nó. Khi class ngoài không được import qua auto-config path, các nested configuration thuộc quá trình phân tích của lớp ngoài đó cũng không được đăng ký theo đường này.

### 5.7. Chạy và kiểm tra kết quả

Tại thư mục `exclusion-demo`, cài JDK 17+ và Maven, chạy:

```bash
mvn -q spring-boot:run
```

Bốn dòng được viết bởi `System.out.println` (Spring Boot có thể ghi thêm banner/log khác):

```text
regularMarker=true
regularNestedMarker=true
autoMarker=false
autoNestedMarker=false
```

Giải thích:

| Bean | Nguồn | Vì sao có/không? |
|---|---|---|
| `regularMarker` | `RegularConfiguration` | Cấu hình được `@Import` nên vẫn được đăng ký |
| `regularNestedMarker` | `RegularConfiguration.InternalConfiguration` | Nested `@Configuration` được xử lý cùng cấu hình thường |
| `autoMarker` | `OptionalFeatureAutoConfiguration` | Lớp auto-config được exclude khỏi candidate list |
| `autoNestedMarker` | `OptionalFeatureAutoConfiguration.InternalConfiguration` | Nested configuration không được phân tích theo đường import lớp cha đã bị exclude |

Để đối chiếu, **nếu bỏ tham số `exclude`** nhưng giữ nguyên các file khác và không có điều kiện nào loại lớp auto-config, kết quả mong đợi là cả bốn bean có mặt. Đây là phép kiểm chứng thực nghiệm rằng việc thiếu hai bean auto xuất phát từ exclusion.

Không nên dùng bean name làm thước đo tổng quát khi dự án thực tế có nhiều lớp tạo cùng loại bean. Ví dụ cố ý đặt tên khác nhau để quan sát đường nạp rõ ràng.

## 6. Hai ví dụ sai thường gặp: thường và lồng nhau

### 6.1. Sai: exclude lớp @Configuration được @Import

Thay phần annotation trên ứng dụng thành:

```java
@SpringBootApplication(exclude = RegularConfiguration.class)
@Import(RegularConfiguration.class)
public class ExclusionDemoApplication {
    // ...
}
```

Đây là **phản ví dụ**, không phải bản code để chạy thành công. `RegularConfiguration` là lớp `@Configuration` thông thường, **không** nằm trong danh sách auto-configuration candidates. Nếu class có trong classpath như ví dụ, Spring Boot 3.3 kiểm tra exclude và phát hiện đối tượng không phải candidate: quá trình khởi động thất bại với thông báo dạng:

```text
The following classes could not be excluded because they are not auto-configuration classes:
    - demo.regular.RegularConfiguration
```

Đây là **phần thông điệp chẩn đoán tiêu biểu**, không phải toàn bộ stack trace. Đừng sửa bằng cách chuyển sang `excludeName = "demo.regular.RegularConfiguration"` hay `spring.autoconfigure.exclude=demo.regular.RegularConfiguration`: các lựa chọn đó vẫn đi qua cơ chế loại trừ **auto-configuration**.

Cách giải quyết: nếu không muốn nạp `RegularConfiguration` thì bỏ `@Import(RegularConfiguration.class)`, dùng `@Profile`/`@ConditionalOnProperty` cho cấu hình do mình sở hữu, hoặc điều chỉnh component scan khi đó thật sự là nguồn nạp.

### 6.2. Sai: exclude nested internal class của auto-config

Ví dụ:

```java
@SpringBootApplication(
    exclude = OptionalFeatureAutoConfiguration.InternalConfiguration.class)
public class ExclusionDemoApplication {
    // ...
}
```

Đây cũng là **phản ví dụ**. Dù nested class `public static` nên code có thể biên dịch, file `AutoConfiguration.imports` trong ví dụ chỉ công bố lớp **ngoài**. Nested class không phải candidate độc lập, nên exclude inner không loại được một phần nội bộ và dẫn tới kiểm tra exclude không hợp lệ trong Spring Boot 3.3.

Cách sửa khi muốn tắt **toàn bộ tính năng**:

```java
@SpringBootApplication(
    exclude = OptionalFeatureAutoConfiguration.class)
public class ExclusionDemoApplication {
    // ...
}
```

Nếu chỉ muốn tắt **bean trong lớp con**, không có một thao tác `exclude` ở cấp bean method trong `@SpringBootApplication`. Hãy dùng một tùy chọn chính thức của thư viện, bean thay thế (khi auto-config hỗ trợ), hoặc sửa thiết kế auto-configuration mà bạn sở hữu để thêm condition cho nhánh tương ứng.

## 7. Bảng chẩn đoán theo trường hợp đầu vào

| Yêu cầu/tình huống | Hành động | Kết quả chính |
|---|---|---|
| Không cần toàn bộ auto-config X | `exclude = XAutoConfiguration.class` | Boot không import candidate X theo auto-config path |
| Không có dependency compile-time vào X | `excludeName = "pkg.XAutoConfiguration"` | Loại candidate theo tên, không phải loại class thường |
| Loại một `@Configuration` được `@Import` | Dùng `exclude = RegularConfiguration.class` | **Sai cơ chế**; với class hiện diện nhưng không là candidate, thường startup error |
| Loại một `@Configuration` được scan | Dùng `spring.autoconfigure.exclude=...` | **Sai cơ chế**; phải sửa phạm vi hoặc filter scan |
| Loại nested internal class không nằm trong imports | `exclude = OuterAutoConfiguration.InnerConfiguration.class` | **Sai cơ chế**; không phải candidate riêng |
| Loại auto-config cấp ngoài chứa nested internal | `exclude = OuterAutoConfiguration.class` | Nested đi cùng outer thường không được đăng ký theo đường đó |
| Tắt một bean nội bộ nhưng giữ các bean còn lại | Tìm property chính thức, condition của nhánh, hoặc bean override theo contract | Có thể tắt chọn lọc nếu thư viện cung cấp extension point |
| Class X được import trực tiếp, lại đồng thời có trong imports | Chỉ exclude X khỏi auto-config candidates | Đường `@Import(X.class)` riêng vẫn có thể đăng ký X |
| Bean loại A vẫn xuất hiện dù exclude auto-config A | Tìm `@Bean`/`@Component`/import khác cung cấp bean | Exclude auto-config không xóa bean có nguồn khác |
| Nested class **thực sự** là candidate được công bố riêng | Exclude đúng tên candidate (thường dùng `$` cho nested) | Cơ chế có thể áp dụng; vẫn cần dựa vào API chính thức của thư viện |

Điểm cần nhớ: không thể chỉ nhìn **cấu trúc Java** để kết luận class có nằm trong danh sách auto-configuration hay không. Hãy xác định class đó được **công bố/nạp bằng cơ chế nào**.

## 8. Cách xử lý đúng khi muốn bỏ một @Configuration thông thường

### 8.1. Nếu được @Import trực tiếp

```java
@Configuration(proxyBeanMethods = false)
@Import({SecurityConfiguration.class, ReportingConfiguration.class})
public class ApplicationConfiguration {
}
```

Đây là ví dụ minh họa với các class giả định. Nếu không còn muốn `ReportingConfiguration`, bỏ class đó khỏi danh sách `@Import` hoặc bao điều kiện quanh việc import/configuration theo thiết kế đang sở hữu. `@SpringBootApplication(exclude = ReportingConfiguration.class)` không giải quyết yêu cầu trên.

Nếu nguồn import đến từ **một thư viện**, trước hết tìm tùy chọn cấu hình chính thức của thư viện; không loại cấu hình bằng cách dựa vào tên lớp nội bộ không được cam kết.

### 8.2. Nếu do component scan

Đặt vùng quét vừa đủ và, nếu cần thiết, dùng filter scan:

```java
@ComponentScan(
    basePackages = "demo.business",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyFeatureConfiguration.class
    )
)
```

Đoạn trên cần các import Spring tương ứng và các class hiện hữu trong ứng dụng; đây là **minh họa filter scan**, không phải chương trình độc lập. Filter này chỉ ảnh hưởng những class được **tìm thấy qua lần component scan tương ứng**. Nếu `LegacyFeatureConfiguration` còn được `@Import` bằng đường riêng, filter scan **không ngăn** đường import đó. Ngược lại, không nên mở rộng scan quá mức rồi dùng hàng chục exclude filters như một cách sửa cấu trúc package chưa rõ.

### 8.3. Nếu bạn sở hữu lớp @Configuration

Bật/tắt bằng điều kiện tường minh:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "demo.reporting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class ReportingConfiguration {

    @Bean
    ReportWriter reportWriter() {
        return new ReportWriter();
    }
}
```

Đây là một **mảnh minh họa**, yêu cầu import các annotation và kiểu `ReportWriter`. Khi property không được bật, class không được đăng ký theo điều kiện này; không cần lạm dụng auto-config exclude. Có thể đặt `@ConditionalOnProperty` tại **lớp nested cụ thể** nếu chỉ muốn một nhánh con có điều kiện, trong khi vẫn giữ outer configuration.

Nếu dùng `@Profile("reporting")`, điều kiện phụ thuộc vào profile được kích hoạt, khác cơ chế của `spring.autoconfigure.exclude`. Chọn quy tắc đúng với yêu cầu triển khai; không tự coi profile và feature flag là một.

### 8.4. Nếu muốn thay bean do auto-config cung cấp

Nhiều auto-configuration có `@ConditionalOnMissingBean`, nghĩa là sẽ **nhường quyền** khi ứng dụng cung cấp một bean phù hợp. Đây là **thay thế hành vi** có kiểm soát mà không cần exclude cả outer configuration. Nhưng cách này chỉ phù hợp khi thư viện thực sự có điều kiện back-off tương ứng, và cần kiểm tra type/name/qualifier. `@Primary` chỉ điều chỉnh lựa chọn bean cho inject; nó **không loại** bean gốc khỏi context.

## 9. Đường nạp độc lập: hai bẫy nâng cao

### 9.1. Đã exclude auto-config nhưng bean vẫn xuất hiện

Giả sử có:

```java
@SpringBootApplication(exclude = ReportAutoConfiguration.class)
@Import(ReportAutoConfiguration.class)
class Application {
}
```

Đây là **phản ví dụ thiết kế**: cùng một class có thể được Spring Boot loại khỏi **đường auto-configuration**, nhưng lại được đăng ký qua `@Import` trực tiếp. Không nên hiểu `exclude` là cấm tuyệt đối class tồn tại trong toàn bộ ứng dụng. Cách đúng là bảo đảm auto-config không đồng thời bị import/scan ngoài cơ chế mà Boot dành cho nó.

Đây cũng là lý do Spring Boot khuyến nghị tách auto-configuration vào package chuyên biệt và **không để component scan phát hiện nó**.

### 9.2. Nested configuration được đăng ký độc lập

Một nested class có thể được `@Import(Outer.Inner.class)` hoặc component scan phát hiện **độc lập** với outer. Khi đó, kể cả outer bị loại khỏi đường auto-config, nested class vẫn có thể được phân tích theo đường nạp riêng.

Còn có một điểm dễ bỏ sót trong Spring Framework: nếu điều kiện nằm trên **lớp ngoài**, nó không nhất thiết được áp dụng cho nested class **khi nested được phát hiện độc lập**. Với cấu hình do mình sở hữu, nên đặt điều kiện cần thiết trực tiếp trên nested class hoặc dùng một composed annotation phù hợp nếu nested có thể được import/scan riêng.

Kết luận thực tế: **exclude outer sẽ ngăn các nested class được đưa vào như phần của chính outer theo đường auto-config đó**, nhưng không cam kết ngăn mọi con đường đăng ký độc lập mà ứng dụng đã thiết kế.

## 10. Quy trình gỡ lỗi khi loại trừ không đạt kết quả

1. **Ghi chính xác class muốn loại.** Đó là outer auto-config, regular `@Configuration`, hay nested internal class? Không đoán dựa trên cách đặt tên.
2. **Xác định đường nạp class.** Kiểm tra danh sách `AutoConfiguration.imports` của các jar liên quan cho auto-config; còn cấu hình thường thì tìm nơi `@Import`, `@ComponentScan`, khai báo trực tiếp hoặc registrar đăng ký.
3. **Đối chiếu dạng exclude.** `@SpringBootApplication(exclude)`, `@EnableAutoConfiguration(exclude)` và `spring.autoconfigure.exclude` chỉ xử lý auto-config candidates theo cơ chế tương ứng.
4. **Nếu báo “not auto-configuration classes”**, class được yêu cầu exclude đang có trên classpath nhưng không nằm trong danh sách candidates mà selector xem xét. Chuyển về đúng cơ chế nạp; đừng chỉ đổi `exclude` thành `excludeName`.
5. **Nếu bean vẫn tồn tại**, tìm bean definition nguồn gốc thực sự. Bean có thể do user config, import độc lập hoặc auto-config khác cung cấp.
6. **Kiểm tra report điều kiện.** Trong ứng dụng Spring Boot, bật `--debug` để xem **Condition Evaluation Report**. Với Spring Boot Actuator được cấu hình/expose, endpoint `/actuator/conditions` có thể cho biết auto-configuration nào khớp/không khớp. Đừng coi absence/presence của bean đơn lẻ là bằng chứng đầy đủ.
7. **Thử từng phương án với context nhỏ** bằng `ApplicationContextRunner` hoặc integration test để xác nhận cả cấu hình cần giữ và cấu hình cần tắt. Nên thử trường hợp auto-config tồn tại, bị exclude, property flag tắt và regular config có mặt.

### Checklist trước khi thêm một exclusion

- [ ] Class đích là **ứng viên auto-configuration công bố**, không chỉ là `@Configuration` bất kỳ.
- [ ] Nếu là nested class, có chứng cứ nó là **candidate độc lập**, hay chỉ là implementation detail?
- [ ] Exclusion có làm mất các bean khác trong outer auto-config mà ứng dụng đang cần không?
- [ ] Bean bị nhắm tới có thể được cung cấp bởi một class khác không?
- [ ] Có property hoặc `@ConditionalOnMissingBean` chính thức giúp tắt/thay riêng phần mong muốn không?
- [ ] Đã kiểm tra ứng dụng vẫn khởi động và những bean cần giữ vẫn có mặt chưa?

## 11. Câu hỏi tự kiểm tra

**Câu 1:** `RegularConfiguration` chỉ được nạp bằng `@Import(RegularConfiguration.class)`. Có thể dùng `@SpringBootApplication(exclude = RegularConfiguration.class)` để loại nó không?

**Trả lời:** Không. Nó không phải auto-config candidate được Boot chọn. Nếu class hiện diện nhưng không là candidate, cấu hình exclude này thường gây lỗi khi khởi động. Hãy sửa `@Import` hoặc điều kiện của chính cấu hình đó.

**Câu 2:** `OuterAutoConfiguration` được công bố trong `AutoConfiguration.imports`, có `static class InnerConfiguration` lồng nhau nhưng `InnerConfiguration` không được công bố riêng. Muốn tắt toàn bộ tính năng, nên exclude class nào?

**Trả lời:** Exclude `OuterAutoConfiguration`. Không cố dùng tên class nội bộ `InnerConfiguration` như một API ổn định.

**Câu 3:** Nếu chỉ muốn tắt `InnerConfiguration` nhưng giữ các bean khác của outer thì dùng gì?

**Trả lời:** Ưu tiên property/condition hoặc cơ chế mở rộng chính thức do tác giả cung cấp. Nếu bạn sở hữu auto-config, có thể tự thêm `@ConditionalOnProperty` ở nhánh inner. Không có `@SpringBootApplication(excludeBeanMethod = ...)` cho yêu cầu này.

**Câu 4:** Exclude `XAutoConfiguration` rồi nhưng vẫn có bean kiểu `XService`. Điều đó có chứng minh `exclude` thất bại không?

**Trả lời:** Không. Bean có thể do cấu hình người dùng, auto-config khác, component scan hoặc import độc lập tạo. Cần xác định bean definition nguồn gốc.

**Câu 5:** Nested class dùng tên JVM `com.example.Outer$NestedAutoConfiguration` trong file `AutoConfiguration.imports` như **ứng viên riêng biệt**. Có thể loại theo tên class đó không?

**Trả lời:** Về cơ chế, nếu nó thực sự là candidate độc lập trong imports thì có thể tham gia bộ lọc exclude. Nhưng đây là trường hợp hiếm; chỉ nên phụ thuộc vào tên được tác giả công bố và cam kết như một public API.

## 12. Ghi nhớ

**Loại trừ auto-configuration là lọc danh sách ứng viên auto-config, không phải xóa tùy ý mọi lớp `@Configuration` hoặc bean trong ApplicationContext.**

- Với **outer auto-configuration được công bố**, dùng `exclude`/`excludeName`/`spring.autoconfigure.exclude` đúng tên class của nó.
- Với **regular @Configuration**, xử lý nguồn `@Import`, component scan, điều kiện hoặc cấu trúc ứng dụng.
- Với **nested internal configuration**, không coi class nội bộ như một exclusion point độc lập khi nó không được công bố riêng. Muốn tắt cả tính năng, loại outer; muốn tắt một nhánh, dùng extension point/condition phù hợp.
- Việc loại outer chỉ cắt **đường auto-config import**. Nếu class hoặc bean được nạp độc lập bằng đường khác, hãy xử lý chính đường nạp đó.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Auto-configuration / Disabling Specific Auto-configuration Classes](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — SpringBootApplication.exclude/excludeName](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html)
- [Spring Boot 3.3 API — AutoConfigurationImportSelector](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html)
- [Spring Framework — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html)
