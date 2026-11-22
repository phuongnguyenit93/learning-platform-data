# Annotation điều kiện mới và cách xác minh phiên bản bắt đầu hỗ trợ

## 1. Vì sao phải kiểm tra phiên bản trước khi dùng annotation?

Spring Boot bổ sung các annotation điều kiện theo từng dòng phát hành. Một annotation xuất hiện trong tài liệu mới nhất không có nghĩa nó tồn tại trong mọi phiên bản Boot mà ứng dụng hoặc thư viện đang hỗ trợ.

Ví dụ, `@ConditionalOnBooleanProperty` được giới thiệu ở Spring Boot 3.5.0. Một thư viện vẫn cam kết tương thích với Boot 3.3 không thể import annotation này rồi mong project 3.3 biên dịch thành công. Ngược lại, `@ConditionalOnThreading` đã có từ Boot 3.2.0 nên có thể dùng trong các project 3.2, 3.3, 3.4 và 3.5.

Khi xem một annotation mới, cần trả lời bốn câu hỏi:

1. **Annotation xuất hiện từ phiên bản nào?** Kiểm tra Javadoc của đúng dòng release và mục `Since`.
2. **Phiên bản ứng dụng thực sự resolve là phiên bản nào?** Kiểm tra Maven/Gradle dependency graph và BOM.
3. **API chỉ mới có hay ngữ nghĩa cũng thay đổi?** Đọc release notes và migration notes.
4. **Phiên bản thấp nhất mà thư viện cam kết hỗ trợ có API đó không?** Biên dịch và chạy test với đúng baseline.

Bài này tập trung vào Spring Boot 3.x, với ví dụ tương thích Boot 3.3.13 và project kiểm thử dùng Boot 3.5.0, Java 17+. Các mốc phiên bản được đối chiếu từ Javadoc versioned và release notes chính thức.

## 2. Bảng mốc phiên bản của một số condition annotations

Không phải tất cả annotation trong bảng đều mới. Các annotation cũ được đưa vào để làm mốc so sánh và cho thấy cách đọc `Since`.

| Annotation | Phiên bản đầu tiên | Ý nghĩa | Ghi chú tương thích |
| --- | --- | --- | --- |
| `@ConditionalOnProperty` | 1.1.0 | Kiểm tra giá trị property trong Environment | Có trong Boot 3.3 |
| `@ConditionalOnWarDeployment` | 2.3.0 | Chỉ match khi chạy WAR truyền thống trong Servlet container | Có trong Boot 3.3 |
| `@ConditionalOnThreading` | 3.2.0 | Kiểm tra threading mode platform/virtual | Có từ Boot 3.2 |
| `Threading` | 3.2.0 | Enum `PLATFORM` và `VIRTUAL` dùng với condition threading | Có từ Boot 3.2 |
| `@ConditionalOnBooleanProperty` | 3.5.0 | Condition chuyên cho boolean property | Không có trong Boot 3.3/3.4 |
| `@ConditionalOnBooleanProperties` | 3.5.0 | Annotation container cho nhiều `@ConditionalOnBooleanProperty` | Có từ Boot 3.5 |
| `@ConditionalOnProperties` | 3.5.0 | Annotation container cho nhiều `@ConditionalOnProperty` | Có từ Boot 3.5 |

Javadoc versioned của `@ConditionalOnBooleanProperty` ghi rõ `Since: 3.5.0`. Javadoc của `@ConditionalOnThreading` và enum `Threading` ghi `Since: 3.2.0`. Đây là mốc API công khai; release notes của từng dòng xác nhận ngữ cảnh thay đổi.

Hai mốc đáng chú ý:

- **Boot 3.2.0:** giới thiệu `@ConditionalOnThreading` để cấu hình theo platform threads hoặc virtual threads.
- **Boot 3.5.0:** giới thiệu `@ConditionalOnBooleanProperty`; đồng thời `@ConditionalOnProperty` và `@ConditionalOnBooleanProperty` trở thành repeatable annotations.

Vì vậy, nếu thư viện có baseline Boot 3.3, có thể dùng `@ConditionalOnThreading` nhưng chưa thể dùng `@ConditionalOnBooleanProperty`.

## 3. @ConditionalOnBooleanProperty — annotation mới từ Boot 3.5.0

### 3.1. Vấn đề mà annotation này giải quyết

`@ConditionalOnProperty` có từ lâu và có thể kiểm tra boolean property bằng cách đặt `havingValue = "true"`. Tuy nhiên, mặc định của nó mang ý nghĩa tổng quát: property phải hiện diện và giá trị không được là chuỗi `false`. Vì vậy, với một property có kiểu boolean, cách viết mặc định có thể khiến một chuỗi khác như `yes` hoặc `enabled` vẫn được xem là match.

Ví dụ:

```java
@Bean
@ConditionalOnProperty(prefix = "acme.audit", name = "enabled")
AuditClient auditClient() {
    return new AuditClient();
}
```

Với `havingValue` để trống, condition mặc định match khi property có mặt và khác `false`. Đây là hành vi hữu ích cho một số property dạng chuỗi, nhưng không diễn đạt rõ rằng key phải là boolean.

`@ConditionalOnBooleanProperty` được thêm trong Boot 3.5.0 để thể hiện ý định đó trực tiếp.

### 3.2. Cú pháp và giá trị mặc định

```java
@Bean
@ConditionalOnBooleanProperty(
        prefix = "acme.audit",
        name = "enabled")
AuditClient auditClient() {
    return new AuditClient();
}
```

Các thuộc tính chính:

| Thuộc tính | Kiểu | Mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| `prefix` | `String` | `""` | Prefix áp dụng cho các property |
| `name` / `value` | `String[]` | rỗng | Tên property cần kiểm tra |
| `havingValue` | `boolean` | `true` | Giá trị boolean mong đợi |
| `matchIfMissing` | `boolean` | `false` | Có match nếu property không được khai báo không |

Với ví dụ trên:

| Giá trị `acme.audit.enabled` | Kết quả |
| --- | --- |
| `true` | Match |
| `false` | No-match |
| Không khai báo | No-match |
| Giá trị không phải boolean hợp lệ | Không thỏa điều kiện boolean; hãy xác thực giá trị đầu vào theo contract của ứng dụng |

Nếu muốn bật bean khi property là false:

```java
@Bean
@ConditionalOnBooleanProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = false)
DisabledAuditMarker disabledAuditMarker() {
    return new DisabledAuditMarker();
}
```

Nếu muốn property bị thiếu cũng được xem là false:

```java
@Bean
@ConditionalOnBooleanProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = false,
        matchIfMissing = true)
DisabledAuditMarker disabledAuditMarker() {
    return new DisabledAuditMarker();
}
```

Đọc kỹ cả `havingValue` và `matchIfMissing`. Property vắng mặt là một trạng thái riêng, không đồng nghĩa với property hiện diện và có giá trị false.

### 3.3. So sánh với @ConditionalOnProperty

| Cách viết | Điều kiện mặc định |
| --- | --- |
| `@ConditionalOnProperty(prefix="acme.audit", name="enabled")` | Property có mặt và không bằng chuỗi `false` |
| `@ConditionalOnProperty(prefix="acme.audit", name="enabled", havingValue="true")` | Property có mặt và bằng chuỗi `true` |
| `@ConditionalOnBooleanProperty(prefix="acme.audit", name="enabled")` | Property có mặt và có giá trị boolean `true` |

Nếu cần tương thích Boot 3.3, cách viết rõ ràng là:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
AuditClient auditClient() {
    return new AuditClient();
}
```

Cách này có thể dùng trước Boot 3.5 và diễn đạt rõ rằng chỉ giá trị `true` mới bật bean. Không cần nâng baseline lên 3.5 chỉ để thay một annotation nếu `@ConditionalOnProperty` đã đáp ứng contract.

### 3.4. Repeatable từ Boot 3.5.0

Trong Boot 3.5.0, `@ConditionalOnBooleanProperty` có thể xuất hiện nhiều lần trên cùng class hoặc method:

```java
@Bean
@ConditionalOnBooleanProperty(
        prefix = "acme",
        name = "audit-enabled")
@ConditionalOnBooleanProperty(
        prefix = "acme",
        name = "metrics-enabled")
CombinedMonitoring combinedMonitoring() {
    return new CombinedMonitoring();
}
```

Các điều kiện được tổng hợp bởi `@ConditionalOnBooleanProperties`. Trong ví dụ, bean chỉ phù hợp khi cả hai property thỏa điều kiện.

Với Boot 3.3, không thể lặp trực tiếp `@ConditionalOnProperty` vì annotation chưa repeatable ở phiên bản đó. Hãy dùng một annotation với nhiều tên:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme",
        name = {"audit-enabled", "metrics-enabled"},
        havingValue = "true")
CombinedMonitoring combinedMonitoring() {
    return new CombinedMonitoring();
}
```

Khi khai báo nhiều tên trong thuộc tính `name`, tất cả property phải match. Đây là cách tương thích tốt với các phiên bản cũ.

## 4. @ConditionalOnThreading — có từ Boot 3.2.0

### 4.1. Mục đích

`@ConditionalOnThreading` cho phép cấu hình bean dựa trên threading mode đang hoạt động. Nó hữu ích khi một integration cần chọn executor, scheduler hoặc adapter riêng cho platform threads và virtual threads.

Annotation nằm trong package:

```java
org.springframework.boot.autoconfigure.condition.ConditionalOnThreading
```

Enum `Threading` nằm trong package:

```java
org.springframework.boot.autoconfigure.thread.Threading
```

Enum có hai giá trị:

- `Threading.PLATFORM`: platform threads; active khi virtual threads không active.
- `Threading.VIRTUAL`: virtual threads; active khi `spring.threads.virtual.enabled=true` và ứng dụng chạy trên Java 21 trở lên.

### 4.2. Ví dụ chọn bean theo threading mode

```java
@Bean
@ConditionalOnThreading(Threading.VIRTUAL)
TaskExecutionStrategy virtualTaskExecutionStrategy() {
    return new VirtualTaskExecutionStrategy();
}

@Bean
@ConditionalOnThreading(Threading.PLATFORM)
TaskExecutionStrategy platformTaskExecutionStrategy() {
    return new PlatformTaskExecutionStrategy();
}
```

Ví dụ trên minh họa hai implementation cùng implement `TaskExecutionStrategy`. Chỉ bean phù hợp với threading mode hiện tại được đăng ký.

Để kích hoạt virtual threads trong ứng dụng Boot 3.2+:

```properties
spring.threads.virtual.enabled=true
```

Điều kiện virtual yêu cầu Java 21+. Nếu ứng dụng chạy Java 17 hoặc property không bật, `Threading.VIRTUAL` không active và `Threading.PLATFORM` là lựa chọn phù hợp.

### 4.3. Liên hệ với phiên bản hỗ trợ

`@ConditionalOnThreading` và enum `Threading` đều có Javadoc `Since: 3.2.0`. Release notes Boot 3.2 cũng nêu annotation mới này được thêm để hỗ trợ các concerns liên quan virtual threads.

Nếu thư viện cần hỗ trợ Boot 3.1 trở xuống, import `@ConditionalOnThreading` sẽ không biên dịch. Cần dùng một condition tương thích với baseline cũ hoặc tách implementation theo version. Không thể chỉ thay version Java mà làm annotation của Boot 3.2 xuất hiện trong Boot 3.1.

## 5. Cách xác minh phiên bản đầu tiên hỗ trợ một annotation

Không nên dựa vào một trang tài liệu mới nhất hoặc kết quả autocomplete của IDE. Dùng nhiều bằng chứng độc lập.

### 5.1. Bước 1 — mở Javadoc đúng phiên bản

Tìm annotation trong Javadoc có version rõ ràng, ví dụ:

- Boot 3.3: `https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html`
- Boot 3.5: `https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBooleanProperty.html`
- Boot 3.2: `https://docs.spring.io/spring-boot/docs/3.2.0/api/org/springframework/boot/autoconfigure/condition/ConditionalOnThreading.html`

Trong trang Javadoc, tìm mục `Since`. Ví dụ:

| Javadoc | Giá trị Since |
| --- | --- |
| `ConditionalOnProperty` | 1.1.0 |
| `ConditionalOnThreading` | 3.2.0 |
| `ConditionalOnBooleanProperty` | 3.5.0 |

Đừng chỉ mở trang `https://docs.spring.io/spring-boot/api` không có version trong URL rồi suy luận rằng annotation có mặt trong version đang dùng. Trang đó thường trỏ tới API hiện hành.

### 5.2. Bước 2 — đối chiếu release notes

Javadoc cho biết mốc `Since`; release notes giải thích annotation được thêm để giải quyết vấn đề gì và có thay đổi liên quan nào khác.

Các mốc cần đọc:

- Spring Boot 3.2 Release Notes: giới thiệu `@ConditionalOnThreading`.
- Spring Boot 3.5 Release Notes: giới thiệu `@ConditionalOnBooleanProperty`.
- Spring Boot 3.5 Release Notes: `@ConditionalOnProperty` và `@ConditionalOnBooleanProperty` trở thành repeatable.
- Spring Boot 3.4 Release Notes: thay đổi một trường hợp đánh giá `@ConditionalOnBean`/`@ConditionalOnMissingBean` trên `@Bean` method khi dùng thuộc tính `annotation`.

Release notes giúp tránh nhầm giữa “annotation mới” và “annotation cũ nhưng hành vi thay đổi”.

### 5.3. Bước 3 — kiểm tra artifact thực tế

Annotation thuộc artifact `spring-boot-autoconfigure`. Có thể kiểm tra JAR đã được Maven tải về.

Linux/macOS:

```bash
jar tf ~/.m2/repository/org/springframework/boot/spring-boot-autoconfigure/3.3.13/spring-boot-autoconfigure-3.3.13.jar | grep ConditionalOnBooleanProperty.class
```

Với JAR Boot 3.3.13, lệnh trên không trả về class `ConditionalOnBooleanProperty`.

Kiểm tra Boot 3.5.0:

```bash
jar tf ~/.m2/repository/org/springframework/boot/spring-boot-autoconfigure/3.5.0/spring-boot-autoconfigure-3.5.0.jar | grep ConditionalOnBooleanProperty.class
```

Kết quả phải chứa:

```text
org/springframework/boot/autoconfigure/condition/ConditionalOnBooleanProperty.class
```

Có thể dùng `javap` để kiểm tra class và chữ ký API:

```bash
javap -classpath ~/.m2/repository/org/springframework/boot/spring-boot-autoconfigure/3.5.0/spring-boot-autoconfigure-3.5.0.jar org.springframework.boot.autoconfigure.condition.ConditionalOnBooleanProperty
```

Trên Windows PowerShell:

```powershell
$jarPath = Join-Path $env:USERPROFILE ".m2\repository\org\springframework\boot\spring-boot-autoconfigure\3.5.0\spring-boot-autoconfigure-3.5.0.jar"
jar tf $jarPath | Select-String "ConditionalOnBooleanProperty.class"
javap -classpath $jarPath org.springframework.boot.autoconfigure.condition.ConditionalOnBooleanProperty
```

Nếu class không có trong JAR đã resolve, code import annotation sẽ không biên dịch, dù IDE có thể đang hiển thị Javadoc của một version khác.

### 5.4. Bước 4 — kiểm tra dependency version được resolve

Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-autoconfigure
```

Gradle:

```bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration compileClasspath
```

Kết quả cần xác nhận:

- Version thực tế của `spring-boot-autoconfigure`.
- Dependency nào kéo version đó vào.
- Có version override hoặc conflict không.
- Version có đồng bộ với `spring-boot`, `spring-boot-test` và plugin Boot không.

Không được suy ra version của thư viện từ version của Gradle/Maven plugin. Plugin build và thư viện trên compile/runtime classpath là hai thành phần khác nhau.

### 5.5. Bước 5 — biên dịch với version thấp nhất mà thư viện hỗ trợ

Giả sử thư viện công bố hỗ trợ Boot 3.3.13 trở lên. Hãy tạo CI matrix:

| Build | Boot BOM/parent | Source được phép dùng |
| --- | --- | --- |
| Compatibility baseline | 3.3.13 | `@ConditionalOnProperty`, `@ConditionalOnThreading` |
| Feature baseline mới | 3.5.0 | Có thể dùng `@ConditionalOnBooleanProperty` và repeatable conditions |

Nếu source import `@ConditionalOnBooleanProperty` mà build với Boot 3.3.13, compiler sẽ báo không tìm thấy symbol. Đây là một lỗi compatibility thực sự, không phải lỗi condition runtime.

Đối với thư viện, baseline hỗ trợ phải được phản ánh trong CI và tài liệu phát hành. Đối với ứng dụng, version được chọn bởi BOM của ứng dụng phải cung cấp mọi API mà source đang import.

## 6. Chiến lược tương thích khi annotation chỉ có ở version mới

### 6.1. Giữ baseline cũ: dùng API cũ có cùng semantics

Nếu thư viện cần hỗ trợ Boot 3.3, dùng:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
AuditClient auditClient() {
    return new AuditClient();
}
```

Không import `@ConditionalOnBooleanProperty` vào module chung. Cách này giữ source tương thích với Boot 3.3 mà vẫn kiểm tra boolean true một cách rõ ràng.

### 6.2. Nâng minimum supported version

Nếu muốn dùng annotation mới, cập nhật minimum supported version lên Boot 3.5.0:

- Nâng BOM/parent trong project.
- Kiểm tra dependency graph không trộn Spring Boot artifacts khác version.
- Chạy unit/integration tests.
- Cập nhật documentation và release notes của thư viện.
- Kiểm tra ứng dụng consumer thực sự dùng Boot 3.5+.

Không chỉ nâng version của riêng `spring-boot-autoconfigure`. Hãy nâng đồng bộ theo Boot BOM để tránh trộn các thành phần không tương thích.

### 6.3. Tách module theo dòng Boot khi cần hai baseline

Nếu sản phẩm bắt buộc hỗ trợ Boot 3.3 và muốn dùng API mới trên Boot 3.5, có thể tách module:

```text
acme-feature-core/
acme-feature-spring-boot-33/
acme-feature-spring-boot-35/
```

Module Boot 3.3 dùng `@ConditionalOnProperty`; module Boot 3.5 dùng `@ConditionalOnBooleanProperty`. Starter/adapter tương ứng chọn module phù hợp.

Cách này phù hợp khi có nhiều khác biệt API thực sự. Nếu chỉ khác một annotation và API cũ vẫn đáp ứng đúng semantics, giữ một module chung thường dễ bảo trì hơn.

### 6.4. Không dùng reflection để che một dependency compile-time thiếu

Một annotation được compiler ghi vào class metadata. Reflection không phải cách đơn giản để “gọi annotation nếu version có, nếu không thì bỏ qua”. Nếu code phải hỗ trợ nhiều version, dùng API chung có sẵn ở baseline hoặc tách artifact theo version.

Không thêm JAR Boot mới vào runtime chỉ để lấy một annotation trong khi ứng dụng đang chạy Boot cũ. Điều đó có thể tạo ra classpath conflict khó chẩn đoán.

## 7. Những thay đổi semantics cần kiểm tra ngoài việc có class mới

### 7.1. Boot 3.5: property annotations trở thành repeatable

Boot 3.5 làm `@ConditionalOnProperty` và `@ConditionalOnBooleanProperty` repeatable. Điều này cho phép khai báo nhiều condition annotation trên cùng element. Với Boot 3.3, dùng thuộc tính `name` chứa nhiều property để yêu cầu tất cả cùng match.

### 7.2. Boot 3.5: boolean enabled values chặt chẽ hơn

Release notes Boot 3.5 ghi nhận các giá trị được hỗ trợ cho property dạng `.enabled` được siết chặt hơn; giá trị phải là `true` hoặc `false`. Một số condition ở các phiên bản trước có thể coi mọi giá trị khác `false` là enabled.

Với custom boolean feature, hãy dùng `havingValue="true"` trên `@ConditionalOnProperty` nếu cần giữ baseline cũ, hoặc dùng `@ConditionalOnBooleanProperty` khi baseline đã là Boot 3.5+. Test cả trường hợp missing, true, false và giá trị sai contract.

### 7.3. Boot 3.4: thay đổi cách suy luận type trong bean conditions

Boot 3.4 thay đổi hành vi của `@ConditionalOnBean` và `@ConditionalOnMissingBean` khi đặt trên `@Bean` method và sử dụng thuộc tính `annotation`. Khi `annotation` được đặt, return type của method không còn tự được dùng làm type condition mặc định như trước; để khôi phục behavior cũ, cần khai báo thêm `value` bằng return type.

Ví dụ khi nâng version, hãy đọc release notes và kiểm tra những condition có nhiều thuộc tính phối hợp. Một annotation vẫn có thể tồn tại qua nhiều version nhưng semantics của nó đã đổi.

## 8. Project thực hành: kiểm tra annotation mới bằng Boot 3.5.0

Project này kiểm tra ba khả năng:

1. `@ConditionalOnBooleanProperty` chỉ đăng ký bean khi boolean property thỏa điều kiện.
2. Hai annotation boolean lặp lại có thể kết hợp trên cùng một bean.
3. `@ConditionalOnThreading` chọn bean cho platform threads khi virtual threads không active.

### 8.1. Cấu trúc project

```text
conditional-annotation-version-lab/
├── pom.xml
├── src/main/java/demo/FeatureAutoConfiguration.java
└── src/test/java/demo/ConditionalAnnotationCompatibilityTest.java
```

### 8.2. Maven POM

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>conditional-annotation-version-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Boot 3.5.0 được chọn có chủ đích vì project sử dụng `@ConditionalOnBooleanProperty`. Java 17 là baseline hợp lệ cho Boot 3.5; test threading bên dưới cố định virtual threads ở trạng thái off nên không đòi hỏi Java 21.

### 8.3. Auto-configuration

File `src/main/java/demo/FeatureAutoConfiguration.java`:

```java
package demo;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBooleanProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnThreading;
import org.springframework.boot.autoconfigure.thread.Threading;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FeatureAutoConfiguration {

    public record AuditMarker(String source) {
    }

    public record CombinedMarker(String source) {
    }

    public record PlatformMarker(String source) {
    }

    @Bean
    @ConditionalOnBooleanProperty(
            prefix = "acme.audit",
            name = "enabled")
    public AuditMarker auditMarker() {
        return new AuditMarker("boolean-property");
    }

    @Bean
    @ConditionalOnBooleanProperty(
            prefix = "acme",
            name = "audit-enabled")
    @ConditionalOnBooleanProperty(
            prefix = "acme",
            name = "metrics-enabled")
    public CombinedMarker combinedMarker() {
        return new CombinedMarker("both-flags");
    }

    @Bean
    @ConditionalOnThreading(Threading.PLATFORM)
    public PlatformMarker platformMarker() {
        return new PlatformMarker("platform-threads");
    }
}
```

Hai condition boolean trên `combinedMarker` minh họa annotation repeatable. Bean chỉ phù hợp khi cả `acme.audit-enabled` và `acme.metrics-enabled` đều true.

### 8.4. JUnit 5 tests

File `src/test/java/demo/ConditionalAnnotationCompatibilityTest.java`:

```java
package demo;

import demo.FeatureAutoConfiguration.AuditMarker;
import demo.FeatureAutoConfiguration.CombinedMarker;
import demo.FeatureAutoConfiguration.PlatformMarker;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalAnnotationCompatibilityTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    FeatureAutoConfiguration.class))
                    .withPropertyValues(
                            "spring.threads.virtual.enabled=false");

    @Test
    void missingBooleanPropertyDoesNotRegisterAuditBean() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(AuditMarker.class);
            assertThat(context).hasSingleBean(PlatformMarker.class);
        });
    }

    @Test
    void trueBooleanPropertyRegistersAuditBean() {
        runner.withPropertyValues("acme.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditMarker.class);
                    assertThat(context.getBean(AuditMarker.class).source())
                            .isEqualTo("boolean-property");
                });
    }

    @Test
    void falseBooleanPropertyDoesNotRegisterAuditBean() {
        runner.withPropertyValues("acme.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditMarker.class);
                });
    }

    @Test
    void bothRepeatableBooleanConditionsMustMatch() {
        runner.withPropertyValues(
                "acme.audit-enabled=true",
                "acme.metrics-enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(CombinedMarker.class);
                });
    }

    @Test
    void oneMissingRepeatableBooleanConditionPreventsRegistration() {
        runner.withPropertyValues("acme.audit-enabled=true")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(CombinedMarker.class);
                });
    }
}
```

`ApplicationContextRunner` tạo context nhỏ để kiểm tra condition. `AutoConfigurations.of(...)` đưa class vào context trực tiếp; project này kiểm tra semantics và compile-time API, không kiểm tra việc phát hiện auto-configuration qua file `AutoConfiguration.imports`.

### 8.5. Chạy test

Từ thư mục project:

```bash
mvn clean test
```

Kết quả mong đợi:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Surefire có thể thay đổi cách trình bày summary theo version, nhưng cả năm test phải pass.

### 8.6. Thử kiểm tra compatibility với Boot 3.3

Đổi parent version trong POM từ `3.5.0` thành `3.3.13` rồi chạy:

```bash
mvn clean test
```

Build sẽ thất bại khi biên dịch vì Boot 3.3.13 không cung cấp `ConditionalOnBooleanProperty` và container tương ứng. Đây là kết quả đúng: project đang dùng API được giới thiệu sau baseline.

Để giữ Boot 3.3, thay condition boolean bằng:

```java
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

Với hai property, dùng một annotation có nhiều tên:

```java
@ConditionalOnProperty(
        prefix = "acme",
        name = {"audit-enabled", "metrics-enabled"},
        havingValue = "true")
```

Sau khi thay code, chạy lại `mvn clean test` với parent 3.3.13. `@ConditionalOnThreading` vẫn dùng được vì nó đã được giới thiệu từ Boot 3.2.0.

## 9. Cách chẩn đoán lỗi khi annotation không được nhận diện

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| IDE báo không tìm thấy annotation | API không tồn tại trong version compile | Kiểm tra Javadoc `Since` và dependency tree |
| Maven báo `cannot find symbol` | Compile classpath resolve Boot thấp hơn yêu cầu | Kiểm tra `spring-boot-autoconfigure` version |
| Code compile nhưng runtime khác dự kiến | Condition có match/no-match theo Environment | Đọc Condition Evaluation Report |
| Một bean không xuất hiện | Property missing/sai giá trị hoặc condition khác no-match | Kiểm tra property, classpath, bean và profile |
| `@ConditionalOnBooleanProperty` không dùng được trên Boot 3.3 | Annotation chỉ có từ Boot 3.5.0 | Dùng `@ConditionalOnProperty(havingValue="true")` |
| `@ConditionalOnThreading` không dùng được trên Boot 3.1 | Annotation chỉ có từ Boot 3.2.0 | Dùng condition phù hợp baseline cũ hoặc nâng Boot |
| Local compile pass nhưng CI fail | Local và CI resolve dependency versions khác nhau | So sánh BOM, effective POM và dependency tree |
| Annotation có trong JAR nhưng vẫn không được compile | JAR chứa class không nằm trên compile classpath hoặc bị version conflict | Kiểm tra compileClasspath và `javap` |

Khi condition đã compile nhưng bean không xuất hiện, chạy ứng dụng với `--debug` để đọc Condition Evaluation Report. Phân biệt rõ lỗi **không có API khi compile** với lỗi **API có sẵn nhưng condition no-match lúc chạy**.

## 10. Checklist review tương thích phiên bản

- [ ] Đã xác định minimum Spring Boot version mà module công bố hỗ trợ.
- [ ] Đã mở Javadoc đúng version, không chỉ xem API latest.
- [ ] Đã ghi nhận mục `Since` của annotation và các enum/container đi kèm.
- [ ] Đã đối chiếu release notes để tìm behavior changes.
- [ ] Đã kiểm tra version thực tế của `spring-boot-autoconfigure` trong dependency graph.
- [ ] Không override riêng version một Boot artifact lệch khỏi BOM.
- [ ] Code dùng `@ConditionalOnBooleanProperty` chỉ khi baseline từ 3.5.0.
- [ ] Code dùng `@ConditionalOnThreading` chỉ khi baseline từ 3.2.0.
- [ ] Với Boot 3.3, đã dùng `@ConditionalOnProperty` với `havingValue="true"` khi cần boolean true chính xác.
- [ ] Đã kiểm tra repeatable behavior theo đúng version.
- [ ] CI biên dịch ở version thấp nhất được hỗ trợ.
- [ ] CI chạy test cho từng baseline quan trọng.
- [ ] Đã phân biệt lỗi compile-time API với condition no-match runtime.

**Ghi nhớ:** Mốc `Since` trong Javadoc cho biết API bắt đầu xuất hiện ở đâu; release notes cho biết vì sao nó được thêm và semantics nào thay đổi; JAR/dependency tree xác nhận project thực sự đang resolve version nào; cuối cùng, compile/test với minimum supported version chứng minh hợp đồng tương thích. Với ví dụ trong bài, `@ConditionalOnThreading` có từ Boot 3.2.0, còn `@ConditionalOnBooleanProperty` chỉ có từ Boot 3.5.0. Nếu vẫn hỗ trợ Boot 3.3, dùng `@ConditionalOnProperty` với `havingValue="true"` là lựa chọn tương thích.

## Tài liệu chính thức

- Spring Boot 3.2.0 API — `@ConditionalOnThreading`: https://docs.spring.io/spring-boot/docs/3.2.0/api/org/springframework/boot/autoconfigure/condition/ConditionalOnThreading.html
- Spring Boot 3.2.0 API — `Threading`: https://docs.spring.io/spring-boot/docs/3.2.0/api/org/springframework/boot/autoconfigure/thread/Threading.html
- Spring Boot 3.3 API — `@ConditionalOnProperty`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.5 API — `@ConditionalOnBooleanProperty`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBooleanProperty.html
- Spring Boot 3.5 API — `@ConditionalOnBooleanProperties`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBooleanProperties.html
- Spring Boot 3.2 Release Notes: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes
- Spring Boot 3.4 Release Notes: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes
- Spring Boot 3.5 Release Notes: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes
