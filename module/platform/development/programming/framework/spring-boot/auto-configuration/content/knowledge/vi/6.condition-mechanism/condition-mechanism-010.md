# Phân biệt cấu hình không được nhập, điều kiện không khớp và bean khởi tạo thất bại

> **Phạm vi:** Spring Boot 3.3.x, Spring Framework 6.1, Java 17+. Bài này phân biệt ba nguyên nhân tưởng như giống nhau khi một tính năng tự cấu hình không hoạt động: **auto-configuration không được import**, **điều kiện không match**, và **bean đã được chọn để tạo nhưng khởi tạo thất bại**. Các ví dụ là các tình huống có thể quan sát bằng log, condition report và kiểm thử, không đánh đồng “không thấy bean” với “ứng dụng không khởi động”.

## 1. Ba câu hỏi khác nhau

Khi một ứng dụng Spring Boot được thêm starter, nhiều người hỏi ngay: “Vì sao không có bean X?”. Câu hỏi này bỏ qua những ranh giới rất quan trọng.

1. **Cấu hình có được khám phá và import không?** Spring Boot đã đưa tên auto-configuration cần xét vào quy trình xử lý `@Import` hay chưa?
2. **Cấu hình hoặc phương thức @Bean có qua các điều kiện không?** Có thể đã tìm thấy class nhưng `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`... không match.
3. **Bean definition được đăng ký thì bean instance có được tạo thành công không?** Một factory method, constructor, dependency injection hoặc callback vòng đời có thể ném lỗi khi context khởi tạo.

Ba trạng thái này không tương đương. Chúng cần những bằng chứng, hướng sửa và loại kiểm thử khác nhau.

| Trạng thái | Điều đã xảy ra | Điều chưa xảy ra | Dấu hiệu thường gặp |
| --- | --- | --- | --- |
| **Không được import** | Selector có thể chưa thấy candidate hoặc đã loại bởi exclusion | Spring chưa xử lý auto-configuration đó như một import có hiệu lực | Imports resource thiếu, class không nằm trong candidate list, explicit exclusion |
| **Condition không match** | Configuration đã là ứng viên để xét; Spring/Boot đánh giá điều kiện phù hợp | Bean definition tương ứng không được đăng ký, hoặc cả configuration bị bỏ qua | Negative matches trong condition report, property/classpath/bean condition fail |
| **Bean khởi tạo thất bại** | Bean definition tồn tại và Spring bắt đầu tạo instance | Không có bean hoạt động thành công; với eager bean thông thường context refresh thất bại | `BeanCreationException`, chuỗi `Caused by` từ constructor/factory/dependency/lifecycle |

**Cảnh báo:** Bảng là mô hình chẩn đoán. Boot có các tối ưu lọc condition ở pha selection; một điều kiện classpath có thể được dùng để lọc candidate sớm. Khi cần kết luận chính xác, phải kiểm tra *nguyên nhân* và thời điểm xử lý, chứ không chỉ suy từ việc class không nằm trong một danh sách log.

## 2. Bản đồ thời điểm: từ JAR đến đối tượng

```text
Ứng dụng khởi động / SpringApplication.run(...)
                 |
                 v
@SpringBootApplication => @EnableAutoConfiguration
                 |
                 v
@Import(AutoConfigurationImportSelector.class)
                 |
                 +--> Đọc META-INF/spring/*.AutoConfiguration.imports
                 |      |
                 |      +--> Không có tên class? ------> KHÔNG ĐƯỢC NHẬP
                 |      |
                 |      +--> exclude / loại candidate? -> KHÔNG ĐƯỢC NHẬP
                 |
                 v
Candidate auto-configuration được xem xét
                 |
                 +--> @Conditional không match ------> BỊ BỎ QUA DO CONDITION
                 |
                 v
Đăng ký các bean definitions phù hợp
                 |
                 +--> @Bean method condition fail ---> KHÔNG ĐĂNG KÝ BEAN
                 |
                 v
Spring giải quyết phụ thuộc, tạo instance
                 |
                 +--> constructor/factory/init throw -> KHỞI TẠO THẤT BẠI
                 |
                 v
ApplicationContext refresh thành công
                 |
                 v
ApplicationRunner, CommandLineRunner, ứng dụng phục vụ request
```

`AutoConfigurationImportSelector` chọn tên configuration classes; `@Conditional` có thể tác động ở mức class hoặc bean method; bean factory tạo instance sau khi bean definition được đăng ký. **Chọn candidate không có nghĩa Spring tạo đối tượng ngay.**

### 2.1. “Không có bean” chưa phải nguyên nhân

Một query kiểu `context.getBeanProvider(Client.class).getIfAvailable()` trả `null` có thể do:
- Không có cấu hình nào cung cấp bean;
- Class auto-configuration không được tìm hoặc bị exclude;
- Condition trên class không đạt;
- Condition trên bean method không đạt;
- Bean được đăng ký dưới type/name khác;
- Bean có cấu hình lazy và chưa được tạo (trong trường hợp này bean *vẫn có thể có definition*; provider thường có thể tạo khi được yêu cầu);
- Context đã thất bại trước khi truy vấn có thể thực hiện.

Vì vậy, hãy tách câu hỏi **bean definition có được đăng ký?** và **instance có được tạo thành công?**. Không lấy việc một runner không in dòng output làm bằng chứng một configuration không được import: runner có thể chưa chạy vì context thất bại.

### 2.2. Ba trạng thái không nhất thiết loại trừ mọi tình huống hỗn hợp

Một ứng dụng có thể có nhiều auto-configurations, một class bị exclude trong khi class khác không match condition, và bean của class thứ ba thất bại khi tạo. Vì vậy chẩn đoán phải gắn với **một configuration class và một bean cụ thể**, không kết luận toàn hệ thống chỉ nằm ở một trạng thái.

## 3. Trường hợp 1 — Auto-configuration không được nhập

Một auto-configuration chỉ được Spring Boot tự tìm thấy khi có con đường khám phá hợp lệ. Với Boot 3.x, một thư viện thông thường khai báo file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ nội dung:

```text
com.example.diagnostics.autoconfigure.DemoAutoConfiguration
```

Tệp này chứa **tên đầy đủ** của class auto-configuration, không chứa tên bean, không chứa tên artifact và không phải lệnh “tạo bean ngay”.

### 3.1. Những lý do phổ biến khiến cấu hình không được import

- **Chưa kích hoạt auto-configuration:** ứng dụng không có `@EnableAutoConfiguration` (thường đi kèm `@SpringBootApplication`), hoặc đã đặt `spring.boot.enableautoconfiguration=false` cho cơ chế mặc định.
- **JAR không có trong runtime classpath:** dependency chỉ ở test/compile, bị exclude khỏi dependency graph hoặc artifact deploy chưa được cập nhật.
- **Có JAR nhưng thiếu resource imports:** thư viện compile được nhưng resource bị đặt sai tên/đường dẫn hoặc không được đóng gói.
- **Tên class trong imports sai:** đổi package/class nhưng không sửa metadata, hoặc phát hành artifact có version không khớp.
- **Đã exclude rõ ràng:** `@SpringBootApplication(exclude=...)`, `excludeName` hoặc `spring.autoconfigure.exclude` gạt configuration tương ứng khỏi danh sách áp dụng.
- **Lọc candidate sớm:** import filter/classpath metadata có thể loại candidate trước khi Spring xử lý sâu class configuration; trường hợp này cần xác minh filter và condition liên quan chứ không mặc định coi là “không thấy JAR”.
- **Cơ chế nạp class/resource khác dự kiến:** ClassLoader hoặc phương thức đóng gói trong môi trường triển khai khiến imports resource không được nhìn thấy.

Trong Boot 3.x, khai báo auto-configuration candidate theo imports file là cách chuẩn. Các phiên bản cũ từng dùng khóa `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `META-INF/spring.factories`; không nên chỉ copy metadata cũ mà không kiểm tra quy ước đúng cho phiên bản Boot.

### 3.2. Exclude là quyết định “không import” có chủ đích

Ví dụ property:

```properties
spring.autoconfigure.exclude=com.example.diagnostics.autoconfigure.DemoAutoConfiguration
```

Khi class được liệt kê là candidate hợp lệ, cấu hình đó bị loại khỏi auto-configuration mặc định. Điều này **không gỡ JAR**, không xóa mọi bean cùng type do ứng dụng/auto-configuration khác tạo, và không phải `@ConditionalOnProperty`.

Hai lựa chọn annotation tương ứng:

```java
@SpringBootApplication(exclude = DemoAutoConfiguration.class)
```

```java
@SpringBootApplication(excludeName =
        "com.example.diagnostics.autoconfigure.DemoAutoConfiguration")
```

Hai dòng trên là **fragment annotation thay thế**, không phải hai annotations đặt đồng thời lên một class và không phải file Java độc lập. `exclude` cần class literal compile-time; `excludeName` nhận FQCN string và hữu ích khi không muốn phụ thuộc compile-time vào class đó.

**Kiểm tra trước khi exclude:** phải là auto-configuration class phù hợp, không phải `@Configuration` ứng dụng bình thường. Khi exclude một class có mặt nhưng không phải auto-configuration candidate hợp lệ, Boot có thể báo cấu hình exclude không hợp lệ.

### 3.3. Bằng chứng nào giúp phân loại “không import”?

Đọc theo thứ tự:
1. `jar tf` / nội dung artifact để chắc chắn class và imports resource được đóng gói.
2. Build dependency graph và runtime classpath thực sự.
3. Annotation `@EnableAutoConfiguration` và các exclusions (annotation/property).
4. Condition evaluation report: tìm mục **Exclusions**; nếu một cấu hình không xuất hiện ở report, cần thêm bằng chứng về imports/JAR, không kết luận ngay condition fail.
5. Nếu dùng custom loader, kiểm tra resource loader và ClassLoader đang dùng.

**Điểm dễ nhầm:** “Không thấy auto-configuration trong Positive matches” không đủ để xác nhận nó không được import. Nó có thể ở Negative matches, Exclusions hoặc phần Unconditional classes, hoặc bản report đã bị lọc hiển thị theo cách khác.

## 4. Trường hợp 2 — Configuration hoặc @Bean condition không khớp

Giả sử class đã được Boot xét, nhưng điều kiện chặn nó:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
class DemoAutoConfiguration {
    // Các @Bean chỉ được xét nếu class-level condition đạt.
}
```

Đây là **fragment minh họa**, chưa phải mã đầy đủ để compile.

Khi `demo.feature.enabled=false`, điều kiện class-level không match. Bean mặc định của class không được đăng ký. **Đây không phải lỗi tạo bean**: factory method không bị gọi để rồi ném exception.

### 4.1. Phân biệt class condition và method condition

Hai mức condition khác nhau:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.Client")
class VendorAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(ClientAdapter.class)
    ClientAdapter clientAdapter() { /* ... */ }
}
```

Đây là fragment dùng các type giả định, **không compile độc lập**.

- `@ConditionalOnClass` trên class quyết định việc áp dụng cả configuration; nếu SDK không có, phần configuration được bảo vệ bị bỏ qua.
- `@ConditionalOnMissingBean` trên `@Bean` quyết định **chỉ default bean đó** có được đăng ký hay không. Nếu ứng dụng đã cung cấp adapter khác, condition không match và default bean nhường chỗ.
- Khi default bean back off, context có thể vẫn có **bean cùng type của ứng dụng**. Vì vậy “không tạo bean mặc định” không phải “không có bean”.
- Một configuration có thể được import mà **không đóng góp bean nào**, hoặc đóng góp chỉ một phần bean methods tùy conditions.

### 4.2. Các nguyên nhân condition không match thường gặp

| Condition | Câu hỏi | Tình huống không match |
| --- | --- | --- |
| `@ConditionalOnClass` | Type có hiện diện ở classpath mà loader nhìn thấy? | Thiếu optional SDK lúc runtime |
| `@ConditionalOnMissingClass` | Type có vắng mặt không? | Class cần phải vắng lại xuất hiện |
| `@ConditionalOnProperty` | Property có giá trị theo quy tắc kích hoạt? | `enabled=false` hoặc property thiếu khi `matchIfMissing=false` |
| `@ConditionalOnBean` | Bean phù hợp đã được Spring biết tại thời điểm kiểm tra? | Chưa có bean type/name cần thiết |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp? | Ứng dụng đã khai báo bean tương ứng |
| `@ConditionalOnWebApplication` | Context có kiểu web phù hợp? | Chạy batch/non-web context |
| `@ConditionalOnResource` | Resource tương ứng được tìm thấy? | Tệp cấu hình/resource không hiện diện |

Các condition dựa trên bean definitions cần chú ý **thứ tự xử lý configuration**. Auto-configuration được defer nhằm cho phép cấu hình ứng dụng đăng ký bean definitions trước, nhưng không có nghĩa mọi bean đã khởi tạo xong khi condition xét.

### 4.3. Condition report đọc thế nào?

Chạy ứng dụng với `--debug`:

```bash
java -jar app.jar --debug
```

Hoặc với Maven plugin:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug"
```

Trong condition evaluation report, các phần thường gặp:
- **Positive matches**: những điều kiện được báo cáo là đã match.
- **Negative matches**: những điều kiện được báo cáo là không match, kèm lý do.
- **Exclusions**: tên các auto-configurations bị loại trừ.
- **Unconditional classes**: cấu hình không có điều kiện tương ứng trong report.

Định dạng và câu chữ có thể thay đổi giữa các phiên bản/patch. Một condition tùy biến chỉ trả boolean có thể không có thông điệp rõ như condition built-in của Boot; khi cần diagnostics tốt, cân nhắc `SpringBootCondition` với `ConditionOutcome`.

### 4.4. Không phải “không thấy trong report” thì chắc chắn không được nhập

Một số điều kiện classpath có thể được xử lý từ metadata sớm và được hiển thị theo cơ chế báo cáo riêng. Khả năng quan sát phụ thuộc Spring Boot version, log level và cách thu thập report. Hãy đối chiếu thêm imports resource, exclusions, bean definitions, logs và exception chain. Tránh suy diễn từ duy nhất một mục vắng mặt.

## 5. Trường hợp 3 — Bean đã được chọn nhưng khởi tạo thất bại

Khi Spring đăng ký được bean definition, quá trình tạo object vẫn có thể lỗi:

```java
@Bean
DemoService demoService() {
    throw new IllegalStateException("Simulated bean creation failure");
}
```

Đây là fragment đặt trong configuration, không phải file Java độc lập. Bean definition có thể tồn tại nhưng **factory method** ném exception khi Spring gọi. Với singleton eager mặc định, quá trình refresh context thường thất bại và ứng dụng Spring Boot không hoàn thành startup.

### 5.1. Các điểm lỗi có thể xảy ra sau khi bean definition đã đăng ký

| Giai đoạn | Ví dụ lỗi | Bằng chứng thường gặp |
| --- | --- | --- |
| Resolve dependencies | Missing required bean, ambiguity, circular dependency | `UnsatisfiedDependencyException`, `NoUniqueBeanDefinitionException` hoặc exception liên quan |
| Constructor/factory method | Runtime exception, missing credentials, invalid parameter | `BeanCreationException` với nguyên nhân gốc |
| Property binding / validation | Port/range invalid, type conversion fail | Binding/validation exception |
| Init callback | `@PostConstruct`, `InitializingBean`, init method ném lỗi | `BeanCreationException` có nested cause |
| FactoryBean / type initialization | Factory hoặc type resolution lỗi | FactoryBean creation/lookup exception |
| External resources | Kết nối DB, message broker, filesystem không sẵn sàng | Exception gốc của driver/client, có thể được wrap |
| Runtime class/API linkage | `NoClassDefFoundError`, `NoSuchMethodError` | Một dạng `LinkageError`, không đơn thuần là condition false |

**Đừng sửa mọi lỗi startup bằng cách thêm `@ConditionalOnClass`**. Nếu class tồn tại nhưng dependency cấu hình sai, endpoint không truy cập được hay constructor ném exception, condition class có thể match hoàn toàn hợp lệ.

### 5.2. Khác biệt giữa eager, lazy và sử dụng về sau

Không phải mọi bean đều được tạo khi context refresh:
- Singleton **non-lazy** thông thường được tạo trong startup; lỗi tạo bean hay làm startup thất bại.
- Bean **lazy** có thể chưa được khởi tạo cho đến khi được yêu cầu; context có thể đã khởi động thành công nhưng lỗi mới xuất hiện ở request hoặc dependency lookup sau đó.
- Prototype thường được tạo khi được lấy từ factory; lỗi chỉ xảy ra khi thực sự yêu cầu.
- Một phương thức nghiệp vụ ném exception **sau khi bean đã được tạo** là lỗi thực thi chức năng, không nhất thiết là lỗi khởi tạo bean.

Vì vậy, “application started” không chứng minh mọi lazy bean hoạt động, còn “startup failed” không tự chỉ ra configuration chưa được import. Phải đọc đúng exception và lifecycle.

### 5.3. Tại sao phải đọc Root cause?

Ví dụ stack trace rút gọn theo ý nghĩa:

```text
org.springframework.beans.factory.BeanCreationException:
  Error creating bean with name 'demoService'
Caused by: java.lang.IllegalStateException:
  Simulated bean creation failure
```

Đây là **mẫu mô phỏng nội dung**, không cam kết từng ký tự log thực tế. Nguyên nhân gốc `IllegalStateException` nói rõ factory method đã được thực thi và ném lỗi. Điều đó khác hoàn toàn với condition không match, khi method không được gọi.

Một chain có thể chứa nhiều lớp wrapper, chẳng hạn exception từ dependency A được đóng gói trong lỗi tạo bean B. Đọc từ bean đầu tiên gặp lỗi rồi lần đến **Caused by sâu nhất** để tìm tác nhân gốc.

## 6. Ma trận chẩn đoán nhanh

| Quan sát | Đầu tiên nên hỏi | Bằng chứng xác nhận | Hướng xử lý |
| --- | --- | --- | --- |
| Không có tên configuration trong imports/JAR | Đã đóng gói đúng metadata chưa? | `jar tf`, nội dung imports, dependency graph | Sửa đóng gói/dependency/metadata |
| Configuration nằm ở Exclusions | Ai đã exclude? | `spring.autoconfigure.exclude`, annotation `exclude`/`excludeName` | Sửa exclusion nếu không chủ ý |
| Configuration nằm ở Negative matches | Condition nào không match? | Condition evaluation report | Sửa property/classpath/bean condition hoặc chấp nhận bỏ qua |
| Configuration match nhưng không có bean mặc định | Bean-method condition có back off không? | Report + bean definitions + user bean | Giữ user override hoặc sửa chính sách default |
| Context fail khi tạo `demoService` | Factory/constructor/init ném gì? | `BeanCreationException` + root cause | Sửa code, dependency và cấu hình thực thi |
| Context lên nhưng request đầu lỗi | Bean lazy hay method nghiệp vụ? | Logs lúc request, lifecycle, lazy/prototype | Sửa runtime call hoặc bean init |
| Chạy test pass nhưng deploy không có bean | Artifact/runtime có khác test không? | JAR manifest/imports, resolved versions, image | Kiểm tra môi trường và classloader |

Một quy tắc thực hành: **lấy bằng chứng của tầng hiện tại trước khi sửa tầng khác**. Không xóa exclusion để chữa lỗi constructor; không thay property flag để chữa imports resource không tồn tại.

## 7. Demo đầy đủ: cùng một service, ba kết quả

Tạo một Spring Boot Maven project nhỏ. Mục đích là quan sát đúng:
1. **Không import** bằng cách loại auto-configuration ở selection;
2. **Condition không match** bằng property;
3. **Bean creation failure** bằng factory method ném exception có chủ đích.

Ví dụ dùng **Java 17, Spring Boot 3.3.13**, không cần database/web server. Khi ứng dụng chạy bình thường, runner in một dòng để bạn nhìn thấy bean hoạt động.

### 7.1. Cấu trúc project

```text
autoconfig-diagnosis-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── diagnostics/
    │   │       ├── DemoService.java
    │   │       └── autoconfigure/DemoAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/example/diagnostics/
        └── AutoConfigurationDiagnosisTest.java
```

Đặt `DemoApplication` trong package `com.example.app` và lớp auto-configuration trong `com.example.diagnostics.autoconfigure`. Hai package là nhánh ngang cấp, nên component scan mặc định của app không tự quét thư viện; **imports resource** chịu trách nhiệm đăng ký candidate.

### 7.2. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>autoconfig-diagnosis-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Parent kiểm soát các version phụ thuộc tương thích với Boot 3.3.13. Cài JDK 17+ và Maven trước khi chạy lệnh `mvn`.

### 7.3. Hợp đồng DemoService

Tạo `src/main/java/com/example/diagnostics/DemoService.java`:

```java
package com.example.diagnostics;

@FunctionalInterface
public interface DemoService {
    String handle(String request);
}
```

Giữ API trung tính với Spring để minh họa “có hay không có bean triển khai” mà không phụ thuộc vào web/database. Nó không có constructor hay lifecycle riêng.

### 7.4. Auto-configuration có cả condition và đường tạo bean có thể lỗi

Tạo `src/main/java/com/example/diagnostics/autoconfigure/DemoAutoConfiguration.java`:

```java
package com.example.diagnostics.autoconfigure;

import com.example.diagnostics.DemoService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class DemoAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DemoService.class)
    DemoService demoService(Environment environment) {
        boolean shouldFail = environment.getProperty(
                "demo.feature.fail", Boolean.class, false);

        if (shouldFail) {
            throw new IllegalStateException(
                    "Simulated bean creation failure");
        }

        return request -> "OK:" + request;
    }
}
```

Phân tích chính xác theo ba trạng thái:

- Nếu class **bị exclude**, selector không import `DemoAutoConfiguration`; Spring không xử lý method `demoService` từ class này.
- Nếu class **được xét nhưng `demo.feature.enabled=false`**, `@ConditionalOnProperty` không match và method `demoService` không được đăng ký.
- Nếu class **được xét và condition match**, bean definition được đăng ký; lúc Spring gọi factory method, property `demo.feature.fail=true` khiến nó ném `IllegalStateException`. Trường hợp này phát sinh lỗi tạo bean, thường được wrap trong `BeanCreationException`.
- `@ConditionalOnMissingBean(DemoService.class)` là một đường back-off khác: khi consumer tự tạo bean, default factory method không được chạy. Nếu app đã có bean và `fail=true`, app có thể vẫn chạy vì bean mặc định đã nhường chỗ. Đây là hành vi đúng của auto-configuration.
- Vì `demo.feature.enabled` dùng `matchIfMissing=true`, khi không có property này, Spring mặc định coi condition đạt. Đây là lựa chọn của ví dụ, không phải mọi tính năng Boot đều mặc định bật.

### 7.5. File imports để selector có tên candidate

Tạo đúng file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.diagnostics.autoconfigure.DemoAutoConfiguration
```

Nếu xóa file này khỏi artifact hoặc nhập sai FQCN, đường discovery qua Spring Boot 3.x sẽ không tìm thấy cấu hình này. **Trong demo, chúng ta dùng exclusion để mô phỏng “không import” mà không cần chỉnh/xóa resource mỗi lần chạy.** Hãy giữ file imports khi kiểm thử hai trạng thái condition và bean creation, để không trộn nhiều nguyên nhân.

### 7.6. App quan sát bean khi startup thành công

Tạo `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.diagnostics.DemoService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printService(ObjectProvider<DemoService> services) {
        return args -> {
            DemoService service = services.getIfAvailable();
            System.out.println(service == null
                    ? "SERVICE=ABSENT"
                    : "SERVICE=" + service.handle("ping"));
        };
    }
}
```

`ObjectProvider` là cố ý: khi bean không được đăng ký, app vẫn có thể khởi động và in `SERVICE=ABSENT`. Nếu runner inject trực tiếp tham số `DemoService` bắt buộc, việc không import/condition fail sẽ gây lỗi injection của **runner**, khiến ba trạng thái bị lẫn. Chính vì vậy demo không inject bắt buộc.

### 7.7. Trường hợp mặc định: configuration có, condition match, bean hoạt động

Chạy ở thư mục chứa POM:

```bash
mvn test
mvn spring-boot:run
```

Dòng do `ApplicationRunner` in ra:

```text
SERVICE=OK:ping
```

Maven và Spring Boot có thể in thêm startup logs. Đó chỉ là dòng *do runner tạo*, không phải toàn bộ stdout.

### 7.8. Tình huống A: không import do exclusion

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--spring.autoconfigure.exclude=com.example.diagnostics.autoconfigure.DemoAutoConfiguration"
```

Dòng do runner in:

```text
SERVICE=ABSENT
```

Lý do: cấu hình bị loại khỏi selection của auto-configuration. `DemoService` vắng mặt vì **không có default configuration được import**; không phải do `demoService` method ném lỗi.

Thử thêm `--debug` để đọc mục Exclusions:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --spring.autoconfigure.exclude=com.example.diagnostics.autoconfigure.DemoAutoConfiguration"
```

Khi sửa một dự án thật, kiểm tra exclusion có chủ đích hay vô tình được truyền qua environment/configuration không.

### 7.9. Tình huống B: condition không match

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.feature.enabled=false"
```

Dòng do runner in cũng là:

```text
SERVICE=ABSENT
```

**Nhưng nguyên nhân khác A.** Ở B, class vẫn là candidate trong imports và không bị exclude; `@ConditionalOnProperty` chặn việc áp dụng configuration. Condition evaluation report sẽ giúp thấy negative match của `DemoAutoConfiguration` với property condition.

Đọc report:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --demo.feature.enabled=false"
```

Đừng chỉ so sánh stdout của runner: A và B có **cùng kết quả đầu ra nghiệp vụ** nhưng **khác nguyên nhân ở pipeline**.

### 7.10. Tình huống C: bean được chọn nhưng khởi tạo thất bại

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.feature.fail=true"
```

Ở đây `demo.feature.enabled` vẫn mặc định true, nên configuration match. `demoService(...)` được gọi và ném:

```text
java.lang.IllegalStateException: Simulated bean creation failure
```

Spring Boot **không hoàn thành startup** với eager singleton thất bại. Không có dòng `SERVICE=ABSENT` hoặc `SERVICE=OK:ping` từ runner, vì runner chỉ thực thi sau khi context startup thành công. Console sẽ chứa log lỗi và chuỗi exception rộng hơn đoạn trên; mẫu trên là phần **root cause** cần tìm.

Chẩn đoán với report/log:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --demo.feature.fail=true"
```

Tình huống C thường có `BeanCreationException` bọc `IllegalStateException`. Đây **không phải negative condition**; condition có thể match nhưng factory method vẫn fail.

### 7.11. Tình huống D: consumer override bean mặc định

Bổ sung method sau **vào bên trong class `DemoApplication`** (không phải file Java độc lập):

```java
@Bean
DemoService customDemoService() {
    return request -> "CUSTOM:" + request;
}
```

Chạy với các properties mặc định:

```text
SERVICE=CUSTOM:ping
```

Dù imports và class-level condition vẫn cho phép xử lý auto-configuration, `@ConditionalOnMissingBean` ngăn việc đăng ký default bean vì app đã cung cấp `DemoService`. Đây là **bean-method condition không match nhưng ứng dụng vẫn có bean cùng type**.

Nếu chạy `demo.feature.fail=true` khi đã có custom bean, default factory method không bị gọi nên không ném lỗi; kết quả vẫn có thể là `SERVICE=CUSTOM:ping`. Đây là cách chứng minh “factory method fail” không phải hệ quả tất yếu chỉ vì một property tồn tại — nó phụ thuộc bean definition thực sự được chọn.

**Lưu ý:** Xóa method tùy biến sau thí nghiệm để trở lại kết quả mặc định trong các tình huống A–C.

## 8. Tự động kiểm tra ba trạng thái bằng ApplicationContextRunner

Một bộ test tốt không chỉ assert “không có bean”. Nó phải phân biệt:
- Context **chạy thành công** nhưng bean vắng mặt;
- Context **không thể startup** vì lỗi tạo bean;
- Context **có bean của consumer** và auto-configuration back off.

Tạo `src/test/java/com/example/diagnostics/AutoConfigurationDiagnosisTest.java`:

```java
package com.example.diagnostics;

import com.example.diagnostics.autoconfigure.DemoAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationDiagnosisTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestApplication.class);

    @Test
    void defaultAutoConfigurationCreatesBean() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DemoService.class);
            assertThat(context.getBean(DemoService.class)
                    .handle("ping")).isEqualTo("OK:ping");
        });
    }

    @Test
    void explicitlyExcludedConfigurationIsNotApplied() {
        runner.withPropertyValues(
                "spring.autoconfigure.exclude="
                        + DemoAutoConfiguration.class.getName())
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(DemoService.class);
                });
    }

    @Test
    void unmatchedConditionSkipsBeanWithoutFailingStartup() {
        runner.withPropertyValues("demo.feature.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(DemoService.class);
                });
    }

    @Test
    void factoryFailurePreventsContextStartup() {
        runner.withPropertyValues("demo.feature.fail=true")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(IllegalStateException.class);
                });
    }

    @Test
    void consumerBeanMakesAutoConfigurationBackOff() {
        runner.withUserConfiguration(ConsumerConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DemoService.class);
                    assertThat(context.getBean(DemoService.class)
                            .handle("ping")).isEqualTo("CUSTOM:ping");
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class TestApplication {
    }

    @Configuration(proxyBeanMethods = false)
    static class ConsumerConfiguration {
        @Bean
        DemoService customDemoService() {
            return request -> "CUSTOM:" + request;
        }
    }
}
```

Test có chủ đích dùng `@EnableAutoConfiguration` trên một configuration test để đi qua **AutoConfigurationImportSelector** và file imports. Khác với:

```java
.withConfiguration(AutoConfigurations.of(DemoAutoConfiguration.class))
```

cách cấp class trực tiếp ở dòng trên **bỏ qua bước khám phá candidate từ imports**, vì thế không phù hợp nếu mục tiêu test là chứng minh exclusion trong selector. Dòng đó là fragment minh họa, không nằm trong test class ở trên.

### 8.1. Vì sao test không “assert bean không có” cho cả ba trường hợp?

`factoryFailurePreventsContextStartup` không assert `doesNotHaveBean` vì **context chưa refresh thành công**. Khi runner phát hiện startup failure, cách kiểm tra đúng là `hasFailed()` và `getStartupFailure()`; không truy vấn bean như thể context hoạt động bình thường.

Các test `explicitlyExcluded...` và `unmatchedCondition...` lại assert `hasNotFailed()` rồi `doesNotHaveBean(...)`, vì thiếu bean là kết quả **mong đợi** khi cấu hình không được import hoặc bị chặn bởi condition.

Test default/consumer cho biết bean đang được tạo và override đúng, nhưng không thay thế hoàn toàn một integration test trên JAR thư viện đã publish.

### 8.2. Chạy test và kiểm tra packaging

```bash
mvn test
mvn package
jar tf target/autoconfig-diagnosis-demo-0.0.1-SNAPSHOT.jar
```

Trong executable JAR, bạn cần thấy resource:

```text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Với thư viện JAR thông thường, resource nằm trực tiếp dưới `META-INF/spring/...` từ root. Nếu Maven test chạy nhưng artifact triển khai không có resource, việc khám phá auto-configuration ở runtime có thể khác test.

### 8.3. Ma trận kỳ vọng

| Trường hợp | Config được chọn để xét? | Class/method condition match? | Bean khởi tạo? | Context kết quả |
| --- | --- | --- | --- | --- |
| Mặc định | Có | Có | Thành công | Started; `SERVICE=OK:ping` |
| Exclude configuration | Không | Không đánh giá config này theo đường auto-config | Không có default | Started; `SERVICE=ABSENT` |
| Property enabled=false | Có candidate; bị chặn bởi condition | Không ở class level | Không có default | Started; `SERVICE=ABSENT` |
| Property fail=true | Có | Có | **Thất bại** | **Startup failure**; runner không chạy |
| Consumer tự cấp `DemoService` | Có | Class match; bean-method missing-bean condition không match | Dùng bean consumer | Started; `SERVICE=CUSTOM:ping` |

“Được chọn để xét” mang nghĩa khái niệm; việc một class được lọc sớm qua optimized import filters cần phân tích thêm nếu bạn đi sâu vào implementation. Với property condition của demo, cốt lõi vẫn là **không match**, không phải thiếu imports resource.

## 9. ConditionEvaluationReport: dùng bằng chứng thay vì đoán

Trong Spring Boot, `ConditionEvaluationReport` lưu thông tin điều kiện của auto-configuration và một số nguồn khác. Khi chạy với `--debug`, ứng dụng thường log condition report, giúp xem cái gì match hoặc không match.

### 9.1. Exclusions và Negative matches không phải một mục

- `Exclusions`: những auto-configurations **được yêu cầu loại trừ** theo annotation/property.
- `Negative matches`: điều kiện được báo cáo là **không đạt** khi đánh giá configuration hoặc bean method.
- `Positive matches`: condition **đạt**.
- `Unconditional classes`: các configuration được báo cáo là không mang condition tương ứng ở mức này.

Với demo:
- Exclude `DemoAutoConfiguration` → tìm ở **Exclusions**.
- `demo.feature.enabled=false` → tìm lý do condition property không match.
- `demo.feature.fail=true` → condition property vẫn match, nhưng log lỗi bean creation; đừng tìm nguyên nhân chính ở Negative matches.
- Bean consumer → method-level `@ConditionalOnMissingBean` không match; có thể thấy reason về bean đã tồn tại.

### 9.2. Khi không thấy class trong report

Đừng kết luận ngay “config không import”. Hãy kiểm tra:
1. Resource imports có chứa tên đó trong **runtime artifact** không?
2. Có exclude nào được áp dụng không?
3. Class có trong runtime classpath không?
4. Có nhập sai FQCN, version hoặc chuyển package không?
5. Logging có thực sự bật/thu đầy đủ report không?
6. Có class condition được optimized filter đánh giá trước bước parse không?

Tương tự, không kết luận “bean đã được tạo” khi chỉ thấy positive match của class; factory method có thể lỗi khi instance được tạo.

### 9.3. Đọc bean creation failure đúng cách

Một chuỗi lỗi thường có dạng:

```text
Error creating bean with name 'demoService'
...
Caused by: java.lang.IllegalStateException:
  Simulated bean creation failure
```

Nội dung này là **mô phỏng rút gọn**, không phải toàn bộ stack trace đảm bảo giống từng patch version. Đọc `Caused by` sâu nhất, đồng thời xem bean đầu tiên thất bại. Nếu bean B lỗi vì inject bean A lỗi, điểm sửa có thể nằm ở A.

### 9.4. Actuator conditions endpoint

Nếu có `spring-boot-starter-actuator`, endpoint `/actuator/conditions` có thể trả điều kiện khi được cấu hình để expose và cấp quyền phù hợp. Điều này hữu ích khi cần xem report qua HTTP, nhưng **không bật public endpoint vô điều kiện trên production**: báo cáo có thể tiết lộ cấu trúc dependency/cấu hình. Demo hiện tại không cần Actuator.

## 10. Cách phân loại lỗi từ log và exception

### 10.1. Không import: thường không có BeanCreationException từ bean đó

Khi class không được import, Spring không gọi factory method của nó trong đường đó. Nhưng ứng dụng **vẫn có thể** có lỗi khác: một bean bắt buộc ở nơi khác đòi service vắng mặt, gây `UnsatisfiedDependencyException`.

Ví dụ:
- `FeatureAutoConfiguration` bị exclude;
- Controller/service khác bắt buộc inject `FeatureClient`;
- Không có bean `FeatureClient` → startup có thể thất bại do injection.

Lúc này, root cause là **missing dependency** của controller/service; nguyên nhân xa hơn là configuration bị loại. Không gọi đây là “factory method của auto-configuration bị lỗi”, vì method chưa chạy.

### 10.2. Condition không match: thiếu bean có thể là hành vi thiết kế

`@ConditionalOnMissingBean` không match khi consumer có bean riêng: đó thường là hành vi tốt. `@ConditionalOnProperty` không match khi người dùng cố ý tắt feature cũng là expected behavior.

Đừng cố ép mọi condition match bằng cách xóa bean user hoặc thêm SDK không cần thiết. Trước tiên đọc hợp đồng của starter: có default-on hay opt-in, có yêu cầu classpath bean/property/web environment nào?

### 10.3. Bean tạo thất bại: không nhất thiết là cấu hình condition sai

Nếu condition match, factory method được chọn và lỗi vì thiếu token/URL, thêm `@ConditionalOnProperty` có thể khiến startup tránh lỗi nhưng cũng có thể che cấu hình sai. Quyết định fail-fast hay optional/degrade cần dựa trên hợp đồng nghiệp vụ:
- Service thiết yếu → fail startup với thông báo rõ có thể đúng.
- Feature optional → disable bằng property hoặc fallback hợp lệ có thể phù hợp.
- Kết nối external unstable → retry/backoff/health policy thay vì làm điều kiện classpath giả.

Các condition nên **không có side effect**; network probe trong `Condition.matches` không thay thế health check hoặc connection management.

## 11. Những sai lầm thường gặp

| Sai lầm | Vì sao dẫn đến chẩn đoán sai | Sửa thế nào |
| --- | --- | --- |
| “Không có bean” = “auto-config không được import” | Condition có thể không match, hoặc default bean back off | Xem imports + exclusions + condition report |
| “Không thấy class ở Positive matches” = “thiếu JAR” | Class có thể ở Negative/Exclusions/Unconditional classes | Đọc toàn report và metadata JAR |
| “Condition true” = “object đã tạo” | Condition chủ yếu quyết định đăng ký definition | Kiểm tra bean lifecycle và root cause |
| “Startup fail” = “@ConditionalOnClass sai” | Có thể là lỗi constructor, binding, inject hoặc external API | Đọc stack trace và exception chain |
| “Đổi property rồi bean tự xuất hiện trong context đang chạy” | Conditions thường được đánh giá lúc xây context | Khởi động context mới hoặc dùng runtime toggle đúng thiết kế |
| “Exclude auto-config là gỡ dependency” | JAR/class vẫn ở runtime classpath | Sửa build graph nếu muốn loại dependency |
| “@ConditionalOnMissingBean làm mất service” | Nó nhường chỗ cho consumer bean; có thể vẫn có type đó | Kiểm tra bean owner/name/type |
| “Kiểm thử non-starting context bằng getBean” | Context chưa refresh hoàn tất | Assert startup failure và root cause |
| “Test cấp AutoConfigurations.of là test discovery” | Cấp trực tiếp class nên không chứng minh imports resource | Test `@EnableAutoConfiguration` + consumer/JAR |
| “Bean không lỗi lúc startup thì chắc chắn không lỗi” | Lazy/prototype beans và runtime methods có thể lỗi muộn | Test lifecycle và first-use |
| “Bật --debug thay thế hoàn toàn logs lỗi” | Report nêu conditions, không thay stack trace factory failure | Kết hợp report, cause, config và runtime artifact |
| “Thêm @Conditional để che BeanCreationException là đủ” | Có thể chỉ né vấn đề chứ không sửa hợp đồng cấu hình | Xác định feature optional hay bắt buộc |

## 12. Checklist chẩn đoán trong dự án thật

Khi nghi ngờ auto-configuration, thực hiện các bước theo thứ tự:

1. **Chỉ rõ bean và class cần điều tra:** tên bean, type, auto-configuration dự kiến cung cấp, artifact/starter.
2. **Xác minh artifact runtime:** chạy `mvn dependency:tree` hoặc Gradle `dependencies --configuration runtimeClasspath`; kiểm tra image/JAR deploy, imports resource và FQCN.
3. **Xác minh đường kích hoạt:** `@EnableAutoConfiguration` có được bật? `spring.boot.enableautoconfiguration=false` có được set?
4. **Kiểm tra exclusion:** `@SpringBootApplication(exclude...)`, `excludeName`, `spring.autoconfigure.exclude`, Exclusions trong report.
5. **Đọc class-level conditions:** `@ConditionalOnClass`, property, web/resource condition; xem Negative matches.
6. **Đọc bean-level conditions:** `@ConditionalOnMissingBean`, `@ConditionalOnBean`; xem có user bean hoặc bean từ auto-config khác không.
7. **Nếu context startup thất bại:** xác định bean đầu tiên lỗi, full `Caused by` chain, method/constructor/init/binding/dependency.
8. **Nếu context chạy nhưng hành vi sai:** kiểm tra lazy bean, instance thực và method-level/runtime exceptions.
9. **Reproduce bằng test:** tạo test riêng cho selection/exclusion, conditions, startup failure và consumer override.
10. **Đối chiếu môi trường thật:** classloader, property precedence, profile, version dependency, connector đến external service.

Không tự thay đổi exclusions/properties bừa bãi trước khi có bằng chứng. Một fix đúng ở local có thể chỉ che một lỗi production khác.

### 12.1. Một vài lệnh hữu ích

Maven:

```bash
mvn dependency:tree
mvn test
mvn package
jar tf target/autoconfig-diagnosis-demo-0.0.1-SNAPSHOT.jar
```

Gradle (nếu dự án có wrapper):

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
```

Các lệnh dependency cho biết graph do build tool resolve; nếu JAR thực tế do container/launcher/custom ClassLoader xử lý khác, cần kiểm tra classpath của **process đang chạy**, không chỉ graph ở workspace.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `DemoAutoConfiguration` nằm trong imports resource nhưng bị nêu ở `spring.autoconfigure.exclude`. Nó có được áp dụng như auto-configuration bình thường không?

**Đáp án:** Không. Exclusion loại tên đó khỏi tập auto-configuration mặc định. Class/JAR vẫn có thể hiện diện, nhưng factory method của class đó không chạy theo đường auto-configuration.

**Câu 2.** `demo.feature.enabled=false` làm runner in `SERVICE=ABSENT`. Có thể kết luận file imports bị thiếu không?

**Đáp án:** Không. Trong demo, imports vẫn đúng; property condition không match khiến bean không được đăng ký.

**Câu 3.** `demo.feature.fail=true` làm startup lỗi. Condition report có thể hiển thị class-level condition match không?

**Đáp án:** Có. Condition đạt và bean definition được đăng ký, nhưng factory method ném exception khi tạo instance.

**Câu 4.** Exclude configuration mà ứng dụng vẫn có bean `DemoService`. Điều này có mâu thuẫn không?

**Đáp án:** Không. Bean có thể do ứng dụng, component scanning hoặc configuration khác tạo. Exclusion chỉ loại một auto-configuration có tên cụ thể.

**Câu 5.** `@ConditionalOnMissingBean(DemoService.class)` không match nhưng app có `DemoService` của consumer. Đó có phải lỗi startup?

**Đáp án:** Không; đó là back-off đúng thiết kế.

**Câu 6.** Một `@Bean` method ném exception nhưng được `@Lazy`. Vì sao ứng dụng có thể báo started?

**Đáp án:** Vì lazy bean có thể chưa được tạo trong startup. Khi bean được yêu cầu sau đó, lỗi mới xảy ra; phải kiểm thử first-use.

**Câu 7.** Tại sao test lỗi tạo bean nên assert `getStartupFailure()` thay vì chỉ `doesNotHaveBean`?

**Đáp án:** Vì context đã failed; truy vấn như context hoạt động bình thường có thể không hợp lệ và che nguyên nhân thật.

**Câu 8.** Nếu một auto-configuration có `@ConditionalOnClass` không match, có phải import selector luôn chọn rồi Spring mới bỏ qua trong mọi version/đường xử lý?

**Đáp án:** Không. Boot có thể lọc classpath conditions sớm từ metadata. Điều quan trọng là xác định **condition fail do classpath**, không nhầm thành imports resource bị thiếu.

**Câu 9.** Tại sao `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` không đủ để kiểm tra imports resource?

**Đáp án:** Vì runner được cấp class auto-configuration trực tiếp, không cần selector khám phá tên từ imports. Hãy dùng test với `@EnableAutoConfiguration` và kiểm tra artifact.

**Câu 10.** Nếu bean thất bại khi bind configuration properties, bạn nên sửa theo tầng nào?

**Đáp án:** Bean creation/binding failure — kiểm tra property values, conversion, validation và exception chain; không mặc định gỡ imports hay tắt class condition.

## 14. Ghi nhớ

Ba kết luận phải đi kèm ba loại bằng chứng:

```text
KHÔNG IMPORT
  -> kiểm tra candidate resource, classpath, @EnableAutoConfiguration, Exclusions

CONDITION KHÔNG MATCH
  -> kiểm tra condition report, classpath/property/bean condition, phase

BEAN KHỞI TẠO THẤT BẠI
  -> kiểm tra bean definition, BeanCreationException, deepest cause, lifecycle
```

Trong thực tế, việc một bean vắng mặt có thể là **hành vi đúng** của feature optional, còn startup failure là tín hiệu cần sửa code/config/đường phụ thuộc. Chỉ khi xác định được mình đang đứng ở tầng nào mới chọn được thay đổi chính xác và tránh chữa sai nguyên nhân.

### Tài liệu chính thức

- Spring Boot 3.3 — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — `ConditionEvaluationReport` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 — `ApplicationContextRunner` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Framework 6.1 — `BeanCreationException` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/BeanCreationException.html
- Spring Boot 3.3 — `ConditionalOnMissingBean` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
