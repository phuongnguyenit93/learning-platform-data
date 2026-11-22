# Hợp nhất danh sách ứng viên, xử lý trùng lặp và danh sách loại trừ

> **Ngữ cảnh:** Spring Boot 3.3.x, Spring Framework 6.1 và Java 17+. Bài thuộc chủ đề **Khám phá ứng viên** của cơ chế auto-configuration. Trọng tâm là cách danh sách *auto-configuration candidate classes* được tập hợp, loại tên trùng, áp dụng exclusions và đưa về một danh sách để Spring tiếp tục xử lý. Đây là bước lựa chọn **lớp cấu hình**, không phải bước tạo tất cả bean.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích nguồn gốc của danh sách các **auto-configuration candidates** và vì sao nhiều JAR cùng đóng góp vào danh sách đó.
2. Phân biệt **loại trùng ở một lần chọn**, **hợp nhất giữa các entry** và **sắp xếp kết quả cuối**.
3. Biết ba cách loại trừ chính: `exclude`, `excludeName` và `spring.autoconfigure.exclude`; hiểu chúng tác động vào **auto-configuration class names**.
4. Diễn giải cơ chế `AutoConfigurationImportSelector` và `AutoConfigurationGroup` khi có nhiều nguồn candidates hoặc nhiều lần deferred import.
5. Nhận biết tình huống exclude không hợp lệ, tên class cũ, điều kiện không khớp và bean mặc định nhường chỗ là **những hiện tượng khác nhau**.
6. Chạy một ứng dụng Spring Boot nhỏ có candidate khai báo lặp, rồi thử exclusion và property condition; viết test chứng minh behavior của context.

**Ý chính:** Danh sách candidates đi vào selector có thể chứa tên lặp và các configuration cuối cùng không được dùng. Boot phải *chuẩn hóa tập tên → trừ exclusions → lọc điều kiện có thể lọc sớm → sắp thứ tự → import*. Sau khi import, Spring vẫn tiếp tục xét các `@Conditional` của configuration và `@Bean`.

## 2. Một candidate là gì, đến từ đâu?

Trong Spring Boot 3.x, mỗi JAR có thể cung cấp tệp:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ JAR thứ nhất:

```text
com.acme.cache.CacheAutoConfiguration
com.acme.metrics.MetricsAutoConfiguration
```

JAR thứ hai:

```text
com.acme.metrics.MetricsAutoConfiguration
com.acme.search.SearchAutoConfiguration
```

Nếu chỉ nối các dòng theo thứ tự tìm được, ta có:

```text
CacheAutoConfiguration
MetricsAutoConfiguration
MetricsAutoConfiguration
SearchAutoConfiguration
```

`MetricsAutoConfiguration` lặp lại. Boot không nên coi hai dòng cùng tên là hai auto-configuration độc lập cần được thực thi hai lần.

**Đơn vị nhận dạng để loại trùng ở giai đoạn này là tên lớp đầy đủ (fully qualified class name / FQCN)**, ví dụ `com.acme.metrics.MetricsAutoConfiguration`. Hai class khác tên cùng tạo bean một type **không phải** trường hợp “trùng candidate”; vấn đề tạo bean sẽ cần điều kiện bean, thứ tự auto-configuration hoặc giải pháp thiết kế riêng.

### 2.1. Nguồn dữ liệu khác với kết quả cuối cùng

Tệp imports chỉ công bố *candidate*. Để một configuration thật sự được áp dụng, còn có những cổng sau:

```text
Runtime classpath / ClassLoader
  |
  v
Nhiều resource AutoConfiguration.imports
  |
  v
Danh sách tên candidate (có thể trùng)
  |
  v
Loại trùng, exclusions, import filters
  |
  v
AutoConfigurationGroup hợp nhất và sắp xếp
  |
  v
Spring xử lý các imported configuration classes
  |
  v
@Conditional ở class / @Bean method
  |
  v
Bean definitions, sau đó bean instances
```

Vì vậy, **thấy tên trong imports không có nghĩa bean xuất hiện**; ngược lại, chỉ nhìn thấy bean vắng mặt chưa đủ kết luận class chưa từng là candidate.

Trong Spring Boot 3.x, `ImportCandidates` đọc các tệp imports theo tên annotation thích hợp. Các JAR phải thực sự ở runtime classpath và loader liên quan phải nhìn thấy resource. Cơ chế đăng ký candidate này khác việc dùng `spring.factories` với khóa `EnableAutoConfiguration` trong các thế hệ Boot cũ; `spring.factories` vẫn có các vai trò khác ở một số extension points.

## 3. Hai tầng xử lý trùng lặp

### 3.1. Tầng một: loại tên trùng trong mỗi AutoConfigurationEntry

`AutoConfigurationImportSelector` có phương thức `getAutoConfigurationEntry(...)`, về mặt logic:

```text
candidates = getCandidateConfigurations(...)
candidates = removeDuplicates(candidates)

exclusions = getExclusions(...)
checkExcludedClasses(candidates, exclusions)
candidates.removeAll(exclusions)

candidates = applyAutoConfigurationImportFilters(candidates)
notifyImportListeners(candidates, exclusions)

return AutoConfigurationEntry(candidates, exclusions)
```

Đây là **pseudocode mô tả vai trò của API**, không phải bản sao nguyên văn mã nguồn và không dùng để compile. Thứ tự thiết yếu: *lấy candidates → loại trùng → thu exclusions → kiểm tra exclusions → xóa excluded names → lọc → trả kết quả cùng exclusions*.

Trong triển khai nhánh Boot 3.3, hàm trợ giúp `removeDuplicates` sử dụng đặc tính của `LinkedHashSet` để giữ một bản sao mỗi tên và duy trì thứ tự lần xuất hiện đầu tiên **ở bước đó**.

Ví dụ:

| Danh sách thô | Sau loại trùng |
| --- | --- |
| `A, B, A, C, B` | `A, B, C` |
| `A, A, A` | `A` |
| `B, A, C` | `B, A, C` |

**Không suy ra thứ tự này chính là thứ tự import cuối**: sau đó, `AutoConfigurationGroup` còn sắp xếp theo metadata order và before/after.

### 3.2. Tầng hai: hợp nhất kết quả của nhiều lần deferred selector

`AutoConfigurationImportSelector` triển khai `DeferredImportSelector` và cung cấp một `Group` là `AutoConfigurationGroup`. Khi Spring xử lý các selector cùng group, group nhận nhiều `AutoConfigurationEntry`.

Giả sử có hai entry sau khi mỗi entry đã loại trùng và loại exclusion cục bộ:

```text
Entry 1:
  configurations = [A, B]
  exclusions     = [C]

Entry 2:
  configurations = [C, D]
  exclusions     = [B]
```

Group không đơn giản nối hai mảng rồi import; group:

1. Gom tất cả exclusions: `{C, B}`.
2. Gom tất cả configurations vào tập không trùng: `{A, B, C, D}`.
3. Xóa **tập exclusions chung**: chỉ còn `{A, D}`.
4. Sắp xếp các configuration còn lại, rồi tạo `Group.Entry` tương ứng để Spring import.

Kết quả **A và D** minh họa một tính chất quan trọng: **exclusion của một entry có thể loại candidate được entry khác đóng góp trong cùng group**. Khi tự đọc source, hãy chú ý `AutoConfigurationGroup.selectImports()`, thay vì chỉ quan sát `getAutoConfigurationEntry()`.

Trong ứng dụng thông thường có một lớp chính kích hoạt auto-configuration, đường group vẫn được sử dụng; nhiều entry không phải lúc nào cũng xuất hiện. Đừng nhầm ví dụ nhiều entry với một khẳng định rằng Spring Boot luôn tạo hai entry cho mọi ứng dụng.

### 3.3. Tại sao group cần giữ lại exclusions?

Mỗi `AutoConfigurationEntry` có hai loại thông tin:

- `configurations`: tên cấu hình còn lại từ lần xử lý selector đó;
- `exclusions`: tập tên cần loại.

Nếu entry 1 đã xóa C nhưng entry 2 vẫn đóng góp C, việc hợp nhất chỉ các danh sách `configurations` sẽ đưa C quay lại. Giữ `exclusions` cho group cho phép trừ toàn bộ exclusion ở cấp kết quả chung. Đây là lý do không thể coi phần exclusions là dữ liệu phụ vô nghĩa sau khi đã lọc cục bộ.

### 3.4. Hai thứ “trùng” không tương đương

| Loại trùng | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Trùng **FQCN auto-configuration** | `A` xuất hiện hai lần trong imports | Selector/group loại trùng tên trong danh sách |
| Hai **auto-configurations khác nhau** tạo bean `Client` | `AAutoConfiguration` và `BAutoConfiguration` | Cần điều kiện bean / thứ tự / thiết kế để tránh xung đột |
| Cùng bean được đăng ký qua scanning và imports | Class auto-configuration bị component scan nhận ngoài ý muốn | Lỗi ranh giới package/đăng ký, không giải quyết chỉ bằng dedup tên trong selector |
| Hai JAR cùng chứa binary class `com.acme.A` khác bytecode | Dependency collision | Vấn đề classpath/classloader; dedup tên imports **không bảo đảm** chọn đúng implementation |

Cần xác định đang gặp tầng nào trước khi sửa.

## 4. Các nguồn loại trừ auto-configuration

Spring Boot cho phép người xây ứng dụng yêu cầu **không áp dụng một auto-configuration cụ thể**.

### 4.1. `exclude`: loại bằng class literal

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }
}
```

Đây là **ví dụ riêng**, chỉ biên dịch khi dependency cung cấp `DataSourceAutoConfiguration` có trên compile classpath. Nó không thuộc project demo ở mục 8.

`@SpringBootApplication` chuyển thuộc tính `exclude` đến `@EnableAutoConfiguration`. Bạn nên dùng class literal khi dự án thật có dependency liên quan, IDE có thể refactor và compiler có thể phát hiện sai tên.

### 4.2. `excludeName`: loại bằng tên lớp đầy đủ

```java
@SpringBootApplication(excludeName = {
    "com.acme.cache.CacheAutoConfiguration",
    "com.acme.search.SearchAutoConfiguration"
})
```

Đoạn trên là **trích phần annotation**, cần đặt trên class ứng dụng để thành mã compile độc lập. `excludeName` hữu ích khi không muốn tham chiếu class literal trong source, chẳng hạn một auto-configuration nằm ở dependency optional.

Chỉ dùng tên auto-configuration, **không dùng tên bean method, interface, starter artifact hoặc annotation bất kỳ**.

### 4.3. `spring.autoconfigure.exclude`: loại từ Environment

Trong `application.properties`:

```properties
spring.autoconfigure.exclude=com.acme.cache.CacheAutoConfiguration,com.acme.search.SearchAutoConfiguration
```

Hoặc lúc chạy:

```bash
java -jar app.jar --spring.autoconfigure.exclude=com.acme.cache.CacheAutoConfiguration
```

Cả ba hình thức trên cùng đóng góp tên vào tập exclusions, nhưng đến từ các nguồn cấu hình khác nhau. Property cho phép điều chỉnh ngoài code, hữu ích khi xử lý các môi trường chạy hoặc thử nghiệm.

**Đừng nhầm** `spring.autoconfigure.exclude` với `spring.boot.enableautoconfiguration=false`: cái đầu loại **những class được nêu tên**, còn cái sau vô hiệu hóa cơ chế chọn auto-configuration mặc định ở mức rộng hơn. Nó cũng không gỡ dependency khỏi classpath.

### 4.4. Exclusion nào được ưu tiên khi cùng class xuất hiện nhiều lần?

Các exclusions được **hợp thành một tập**. Nếu bạn exclude `A` qua annotation và cùng lúc qua property, kết quả vẫn là **A bị loại**; không có chuyện “lần thứ hai bật lại A”. Đây là lựa chọn loại trừ, không phải cấu hình override hai chiều.

Ví dụ:

```text
Candidates = [A, B, C, A, D, B]

exclude      = [B]
excludeName  = [C]
property     = [B, D]

Sau loại trùng     [A, B, C, D]
Hợp exclusions     {B, C, D}
Còn lại            [A]
```

Khi xem cấu hình, nhớ properties chịu quy tắc precedence của `Environment`. Cùng key property được khai báo ở nhiều nguồn có thể được bind thành giá trị khác theo độ ưu tiên; **tập exclusions** là kết quả sau khi selector đọc các attributes/property đã có hiệu lực, không đơn giản là nối văn bản từ mọi file properties của ứng dụng.

## 5. Khi nào exclusion bị xem là không hợp lệ?

`AutoConfigurationImportSelector` có bước `checkExcludedClasses(...)`. Trong cơ chế mặc định của Spring Boot 3.3, nếu tên cần exclude chỉ đến **một class hiện diện ở classpath nhưng không thuộc danh sách auto-configuration candidate hợp lệ**, Boot có thể báo:

```text
The following classes could not be excluded because they are not auto-configuration classes:
    - com.example.SomeRegularConfiguration
```

Đây là mẫu trích **ý nghĩa thông báo**, không cam kết y hệt whitespace của log ở mọi patch version.

Vì sao? Exclusion là một cơ chế để **loại auto-configuration**, không phải lệnh xóa `@Configuration` tùy ý do ứng dụng trực tiếp khai báo. Nếu class không phải candidate auto-configuration thì việc exclude nó không giải quyết đúng đối tượng.

Cần phân biệt:

| Tình huống | Giải thích |
| --- | --- |
| Tên là candidate auto-configuration hợp lệ | Có thể loại khỏi tập candidates |
| Tên chỉ đến một `@Configuration` thường **có mặt** nhưng không phải candidate | Selector có thể báo exclusion không hợp lệ |
| Tên class **không tồn tại** tại runtime | Kiểm tra hợp lệ của exclusion có thể bỏ qua tên vắng mặt, không thể từ đó khẳng định một candidate đã bị loại |
| Tên class cũ đã được đổi hoặc xóa | Kiểm tra imports và metadata tương thích với phiên bản Boot/library hiện tại; tránh giả định tên cũ vẫn hoạt động |

Khi nâng cấp Spring Boot hoặc một starter, hãy xem tên auto-configuration có đổi không; không nên chỉ copy nguyên danh sách exclusions từ một hệ thống cũ.

### 5.1. Các phạm vi exclusion không bao phủ

Exclusion theo `spring.autoconfigure.exclude` hoặc `excludeName` **không**:
- Xóa JAR hoặc class khỏi runtime classpath;
- Cấm ứng dụng tự tạo một bean cùng type;
- Bảo đảm các auto-configuration khác không tạo bean tương tự;
- Hủy một `@Configuration` mà ứng dụng tự import trực tiếp bằng `@Import`;
- Thay thế các condition như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`.

Ví dụ, loại `DataSourceAutoConfiguration` không làm driver JDBC biến mất; code ứng dụng vẫn có thể tự tạo `DataSource`. Cũng có thể còn cấu hình liên quan yêu cầu `DataSource` và khiến startup thất bại nếu bạn chưa xử lý phụ thuộc.

## 6. Bộ lọc import và thứ tự sau hợp nhất

Ngoài exclusions do người dùng nêu, Spring Boot có thể áp dụng các `AutoConfigurationImportFilter` để loại một số candidate sớm, thường dựa trên metadata classpath/conditions.

**Các phép loại khác nhau**:

| Tác vụ | Nơi xảy ra | Ý nghĩa |
| --- | --- | --- |
| `removeDuplicates` | Trong selector | Một tên candidate chỉ giữ một lần ở danh sách của entry |
| `getExclusions` | Trong selector | Thu tên loại trừ theo annotation/property |
| `configurations.removeAll(exclusions)` | Trong selector | Trừ exclusions khỏi danh sách entry |
| `AutoConfigurationImportFilter` | Khi chuẩn bị entry | Có thể lọc nhanh theo metadata trước khi xử lý sâu từng configuration |
| Union + `removeAll(allExclusions)` | Trong group | Ngăn candidate từ entry khác “đưa lại” tên đã bị exclude |
| `AutoConfigurationSorter` | Trên tập còn lại | Sắp thứ tự theo metadata ưu tiên / before-after |
| `@Conditional` ở class/bean | Trong Spring configuration processing | Quyết định đăng ký configuration/bean theo context thực |

**Thứ tự trong file imports không phải hợp đồng thứ tự cuối cùng.** Sau khi group hợp nhất, `AutoConfigurationSorter` áp dụng quan hệ thứ tự; nếu cần ưu tiên, các auto-configuration có thể dùng `@AutoConfiguration(before=..., after=...)`, `beforeName`, `afterName` hoặc metadata tương ứng. Thứ tự này chủ yếu tác động đến việc xét configuration và bean definitions, **không cam kết thứ tự khởi tạo bean instance**.

### 6.1. Tại sao không nên tự làm sort bằng tên class?

Xếp tên class theo ABC hoặc tin vào thứ tự JAR có thể làm sai giả định của `@ConditionalOnMissingBean` giữa các cấu hình. Hãy dựa trên metadata mà Boot hỗ trợ và kiểm thử cả trường hợp ứng dụng có bean riêng.

### 6.2. Phân biệt AutoConfigurationImportFilter với @ConditionalOnMissingBean

Ví dụ một auto-configuration tạo `CacheClient` mặc định:

```java
@Bean
@ConditionalOnMissingBean(CacheClient.class)
CacheClient cacheClient() {
    return new CacheClient();
}
```

Đây là **fragment minh họa**, không phải file Java độc lập. Điều kiện dựa trên bean cần biết các bean definitions đã được xử lý, vì vậy không nên mô tả nó như một so sánh tên trong danh sách candidates. Thư viện có thể được import hợp lệ, nhưng bean của nó không được tạo vì ứng dụng đã tự khai báo bean phù hợp.

## 7. Bài thực hành Java 17: tự mô phỏng hợp nhất và loại trùng

Để tách ý tưởng **tập hợp danh sách** khỏi framework, tạo file `CandidateMergeDemo.java` sau:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class CandidateMergeDemo {
    public static void main(String[] args) {
        List<String> candidates = List.of(
                "Alpha", "Beta", "Alpha", "Gamma", "Beta");

        Set<String> unique = new LinkedHashSet<>(candidates);
        System.out.println("unique=" + new ArrayList<>(unique));

        Set<String> exclusions = Set.of("Beta", "Gamma");
        unique.removeAll(exclusions);
        System.out.println("remaining=" + new ArrayList<>(unique));

        List<String> entryOne = List.of("Alpha", "Beta");
        List<String> entryTwo = List.of("Gamma", "Delta");
        Set<String> allExcluded = Set.of("Beta", "Gamma");

        Set<String> merged = new LinkedHashSet<>();
        merged.addAll(entryOne);
        merged.addAll(entryTwo);
        merged.removeAll(allExcluded);
        System.out.println("group=" + new ArrayList<>(merged));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac CandidateMergeDemo.java
java CandidateMergeDemo
```

Stdout chính xác:

```text
unique=[Alpha, Beta, Gamma]
remaining=[Alpha]
group=[Alpha, Delta]
```

Vì sao đúng? `LinkedHashSet` giữ thứ tự đưa vào lần đầu và không cho tên lặp. `removeAll` trừ tập exclusions. Đoạn này chỉ mô phỏng **phần toán học của hợp nhất**; Spring Boot thực tế còn có nhiều bước như đọc imports, kiểm tra exclusion hợp lệ, lọc metadata và sort theo dependency/order. Không suy ra Spring Boot chỉ chạy ba dòng thao tác set trên đây.

## 8. Demo Spring Boot: candidate trùng, exclude và condition là ba chuyện riêng

Bài thực hành dưới đây dùng **Java 17 + Spring Boot 3.3.13 + Maven**. Cùng một project có hai auto-configuration được công bố trong imports; một tên xuất hiện **hai lần có chủ ý** để quan sát việc tên trùng không khiến xuất hiện hai bean.

**Lưu ý:** Khi xuất bản thư viện thật, bạn nên để một tên candidate xuất hiện **một lần** và đóng gói auto-configuration trong JAR riêng. Dòng trùng trong bài là tình huống thực nghiệm, không phải quy ước viết imports.

### 8.1. Cấu trúc project

```text
candidate-merge-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── feature/
    │   │       ├── AlphaFeature.java
    │   │       ├── BetaFeature.java
    │   │       └── autoconfigure/
    │   │           ├── AlphaAutoConfiguration.java
    │   │           └── BetaAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/app/
            └── AutoConfigurationDiscoveryTest.java
```

Package của app là `com.example.app`, còn hai cấu hình thư viện là `com.example.feature.autoconfigure`. Chúng ở hai nhánh ngang cấp nên component scanning mặc định của app **không vô tình nhận** hai auto-configuration; chúng được phát hiện qua imports resource.

### 8.2. `pom.xml`

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
    <artifactId>candidate-merge-demo</artifactId>
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

Project không cần web server hoặc database. Spring Boot parent quản lý versions tương thích trong nhánh 3.3. Demo giả định bạn có JDK 17+ và Maven 3.x.

### 8.3. Hai type đơn giản để quan sát bean

`src/main/java/com/example/feature/AlphaFeature.java`

```java
package com.example.feature;

public record AlphaFeature(String name) {
}
```

`src/main/java/com/example/feature/BetaFeature.java`

```java
package com.example.feature;

public record BetaFeature(String name) {
}
```

`record` được Java 17 hỗ trợ. Hai type không phụ thuộc vào Spring, chỉ dùng để nhìn thấy bean mặc định nào đã được đăng ký.

### 8.4. Hai lớp auto-configuration

`src/main/java/com/example/feature/autoconfigure/AlphaAutoConfiguration.java`

```java
package com.example.feature.autoconfigure;

import com.example.feature.AlphaFeature;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AlphaAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AlphaFeature.class)
    AlphaFeature alphaFeature() {
        return new AlphaFeature("alpha");
    }
}
```

`src/main/java/com/example/feature/autoconfigure/BetaAutoConfiguration.java`

```java
package com.example.feature.autoconfigure;

import com.example.feature.BetaFeature;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = AlphaAutoConfiguration.class)
@ConditionalOnProperty(
        prefix = "demo.beta",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class BetaAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(BetaFeature.class)
    BetaFeature betaFeature() {
        return new BetaFeature("beta");
    }
}
```

`BetaAutoConfiguration` được sắp **sau** `AlphaAutoConfiguration` trong quá trình xử lý auto-configuration nhờ `@AutoConfiguration(after=...)`; điều này không tạo ra yêu cầu bean Beta phải phụ thuộc Alpha. `@ConditionalOnProperty` quyết định có áp dụng Beta configuration hay không; `@ConditionalOnMissingBean` hỗ trợ app thay thế bean mặc định.

### 8.5. Tệp imports có tên lặp có chủ ý

Tạo đúng đường dẫn:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.feature.autoconfigure.AlphaAutoConfiguration
com.example.feature.autoconfigure.BetaAutoConfiguration
com.example.feature.autoconfigure.AlphaAutoConfiguration
```

Ý nghĩa:

- Có **ba dòng candidate**.
- Có **hai tên class duy nhất**.
- Không có exclusion ở trạng thái mặc định.
- `AlphaAutoConfiguration` được công bố hai lần có chủ ý để minh họa dedup tên ứng viên.
- Danh sách auto-configurations cuối vẫn phải qua filter, sort và xử lý conditions.

Nếu thay dòng thứ ba bằng một class khác tên nhưng cũng tạo `AlphaFeature`, đó **không** còn là bài toán trùng tên; phải thiết kế điều kiện bean và thứ tự phù hợp.

### 8.6. Ứng dụng hiển thị trạng thái hai bean

`src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.feature.AlphaFeature;
import com.example.feature.BetaFeature;
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
    ApplicationRunner showFeatures(
            ObjectProvider<AlphaFeature> alpha,
            ObjectProvider<BetaFeature> beta) {
        return args -> {
            AlphaFeature a = alpha.getIfAvailable();
            BetaFeature b = beta.getIfAvailable();

            System.out.println("ALPHA=" +
                    (a == null ? "ABSENT" : a.name()));
            System.out.println("BETA=" +
                    (b == null ? "ABSENT" : b.name()));
        };
    }
}
```

`ObjectProvider` để runner không đòi hỏi bắt buộc hai bean; nhờ đó ứng dụng vẫn chạy khi Beta bị exclude hoặc condition không match.

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Hai dòng do runner in trong trường hợp mặc định:

```text
ALPHA=alpha
BETA=beta
```

Các startup log của Boot và Maven còn được in thêm; đây là **hai dòng từ `ApplicationRunner`**, không phải toàn bộ stdout.

### 8.7. Exclusion thật sự loại candidate

Chạy lại từ project:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--spring.autoconfigure.exclude=com.example.feature.autoconfigure.BetaAutoConfiguration
```

Hai dòng từ runner:

```text
ALPHA=alpha
BETA=ABSENT
```

Ta không xóa `BetaAutoConfiguration.class` hoặc `BetaFeature.class` khỏi JAR. Chúng vẫn ở classpath, nhưng tên `BetaAutoConfiguration` bị loại khỏi tập auto-configuration cho context này.

Có thể thay cách điều khiển từ property bằng:

```java
@SpringBootApplication(excludeName =
        "com.example.feature.autoconfigure.BetaAutoConfiguration")
```

Đây là **dòng annotation thay cho annotation cũ trong `DemoApplication`**, không phải file độc lập. Nếu sửa source theo cách này, nhớ xóa `excludeName` sau thí nghiệm để quay lại trạng thái mặc định.

### 8.8. Condition không khớp có cùng kết quả bean nhưng khác nguyên nhân

Chạy:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.beta.enabled=false
```

Runner cũng in:

```text
ALPHA=alpha
BETA=ABSENT
```

Điểm khác biệt: **Beta vẫn có thể được chọn làm candidate và được import**, nhưng `@ConditionalOnProperty` khiến Spring không áp dụng cấu hình này. Đây không phải exclusion ở tầng danh sách. Cách chẩn đoán là xem **condition report**, thay vì giả định hai lệnh giống nhau vì stdout của app giống nhau.

### 8.9. Đọc condition report để phân biệt

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Với property disable hoặc exclusion, hãy tìm mục liên quan `BetaAutoConfiguration` trong report:

- **Exclusions** phản ánh những tên auto-configuration bị loại do exclusion.
- **Negative matches** phản ánh cấu hình/điều kiện không match.
- **Positive matches** phản ánh điều kiện đã match.
- **Unconditional classes** có thể liệt kê cấu hình không có condition tương ứng ở mức báo cáo.

Đầu ra có thể khác theo phiên bản Boot và danh sách auto-configurations trên classpath. Không dùng một mẫu log giả định làm căn cứ duy nhất; xem nguyên nhân do condition/exclusion thực tế.

## 9. Kiểm thử context: không tạo trùng bean và xử lý exclusion

Tạo `src/test/java/com/example/app/AutoConfigurationDiscoveryTest.java`:

```java
package com.example.app;

import com.example.feature.AlphaFeature;
import com.example.feature.BetaFeature;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationDiscoveryTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(DemoApplication.class);

    @Test
    void duplicateCandidateNameDoesNotCreateDuplicateBean() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AlphaFeature.class);
            assertThat(context).hasSingleBean(BetaFeature.class);
            assertThat(context.getBean(AlphaFeature.class).name())
                    .isEqualTo("alpha");
        });
    }

    @Test
    void exclusionRemovesAutoConfigurationFromSelection() {
        runner.withPropertyValues(
                "spring.autoconfigure.exclude="
                        + "com.example.feature.autoconfigure.BetaAutoConfiguration")
                .run(context -> {
                    assertThat(context).hasSingleBean(AlphaFeature.class);
                    assertThat(context).doesNotHaveBean(BetaFeature.class);
                });
    }

    @Test
    void propertyConditionCanSkipBetaWithoutExcludingIt() {
        runner.withPropertyValues("demo.beta.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(AlphaFeature.class);
                    assertThat(context).doesNotHaveBean(BetaFeature.class);
                });
    }
}
```

Chạy:

```bash
mvn test
```

**Điều các test chứng minh:** Context dùng app thật vẫn tạo đúng một `AlphaFeature`, có thể bỏ Beta do exclude, và có thể bỏ Beta do property condition. Test đầu là bằng chứng behavior đầu ra; **việc chỉ có một bean không tự nó chứng minh chính xác dòng mã nào trong selector đã loại tên trùng**, vì `@ConditionalOnMissingBean` cũng tham gia bảo vệ bean. Để đối chiếu thuật toán dedup, xem source `removeDuplicates`/`AutoConfigurationGroup.selectImports` của phiên bản đang dùng.

Khác với runner gán trực tiếp:

```java
.withConfiguration(AutoConfigurations.of(AlphaAutoConfiguration.class))
```

runner ở bài **dùng `DemoApplication.class` có `@SpringBootApplication`**, tức giữ lại đường `@EnableAutoConfiguration` và cơ chế khám phá resource. Cách gán `AutoConfigurations.of(...)` trực tiếp hữu ích để test các điều kiện của một auto-configuration, nhưng **bỏ qua một phần đường khám phá candidates từ imports**, nên không phải test duy nhất khi nghiên cứu selector.

### 9.1. Kiểm tra file imports khi đóng gói

```bash
mvn package
jar tf target/candidate-merge-demo-0.0.1-SNAPSHOT.jar
```

Trong executable JAR do Boot Maven plugin đóng gói, resource dự kiến hiện diện dưới:

```text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Trong JAR thư viện thông thường, resource nằm tại `META-INF/spring/...`. Một artifact thiếu file hoặc có class name sai có thể khiến ứng dụng không nhận được auto-configuration mặc dù class Java đã compile.

### 9.2. Thử thêm một bean do ứng dụng tự định nghĩa

Để tách dedup candidates với back-off bean, bổ sung vào **bên trong `DemoApplication`**:

```java
@Bean
AlphaFeature applicationAlphaFeature() {
    return new AlphaFeature("custom");
}
```

Đây là đoạn thêm vào class cũ, không phải file Java mới. Khi chạy app mặc định, output trở thành:

```text
ALPHA=custom
BETA=beta
```

Vì `AlphaAutoConfiguration` có `@ConditionalOnMissingBean(AlphaFeature.class)`, nó nhường chỗ cho bean của app. Tình huống này chứng minh cơ chế **back-off khi đã có bean**, hoàn toàn khác việc hai dòng imports có cùng FQCN.

Nếu thêm method này trước khi chạy test đầu tiên, test kiểm tra giá trị `alpha` sẽ cần được điều chỉnh theo mục đích test; hãy chạy test nguyên bản trước, sau đó mới thử tùy biến bean.

## 10. Phân tích trường hợp nhiều nguồn exclusion và hợp nhất

Một số hiện tượng chỉ rõ khi xét tập nhiều entry, nhiều config sources hoặc nhiều phiên bản thư viện.

### 10.1. Exclusion từ một entry ảnh hưởng toàn group

Giả sử:

```text
Import group:
  E1 configurations=[A, B], exclusions=[C]
  E2 configurations=[B, C], exclusions=[B]

Tập configurations trước trừ chung = [A, B, C]
Tập exclusions chung             = {B, C}
Kết quả trước sort                = [A]
```

Trong trường hợp này, không nên kết luận “E2 vẫn còn C nên C phải được import”: group loại `C` do exclusion từ E1. Đây là ví dụ cơ chế **hợp nhất và loại trừ của group**, không phải yêu cầu luôn tạo nhiều `@EnableAutoConfiguration` trong ứng dụng.

### 10.2. Trùng candidate không đồng nghĩa có hai tài nguyên imports sai

Một class có thể xuất hiện trong imports của nhiều JAR, hoặc lặp trong cùng resource. Ở tầng selection, Boot loại trùng theo FQCN. Tuy nhiên, **việc đóng gói cùng class bytecode trong nhiều JAR vẫn có thể là dependency conflict** và cần xử lý riêng ở dependency graph. Dedup tên ở selector không giải quyết chuyện classloader nạp class nào khi nhiều JAR tranh nhau cùng binary name.

### 10.3. Sắp thứ tự sau hợp nhất

Giả sử config A yêu cầu chạy `after` B, dù raw candidates từ imports có thứ tự `[A, B]` thì sorter có thể chọn `[B, A]`. Không nên dùng “lần xuất hiện đầu tiên” từ `LinkedHashSet` làm hợp đồng thứ tự cấu hình cuối. Hãy công bố metadata `@AutoConfiguration(after=...)` và test condition trên bean nếu thứ tự này quan trọng.

### 10.4. Một auto-configuration bị loại có thể để lại bean từ nơi khác

Nếu bạn exclude `FooAutoConfiguration` nhưng ứng dụng vẫn có bean `Foo`, có thể:
- Ứng dụng tự khai báo `@Bean Foo`;
- Auto-configuration khác tạo bean `Foo`;
- Component scanning đang quét một `@Component Foo`;
- Test configuration/`@Import` khác đã đưa bean vào context.

Vì vậy **exclusion không tương đương bảo đảm vắng mặt bean theo type**. Cần truy vết nguồn bean definition thực tế.

## 11. Quy trình chẩn đoán khi danh sách candidate gây nhầm lẫn

Khi “đã exclude mà bean còn”, “không thấy configuration”, hoặc “cùng thư viện tạo bean không nhất quán”, hãy đi theo thứ tự:

1. **Kiểm tra đúng JAR runtime.** Với Maven dùng `mvn dependency:tree`; với Gradle dùng `runtimeClasspath`/`dependencyInsight`. Đừng chỉ nhìn test classpath.
2. **Kiểm tra imports trong artifact.** Mở `jar tf` của JAR thực tế và nội dung `AutoConfiguration.imports`; tên phải đầy đủ và resource ở đúng đường dẫn.
3. **Kiểm tra nơi kích hoạt.** Ứng dụng có `@EnableAutoConfiguration` (thường qua `@SpringBootApplication`) hay đã tắt `spring.boot.enableautoconfiguration`?
4. **Liệt kê exclusions đúng nguồn.** Xem `exclude`, `excludeName`, `spring.autoconfigure.exclude` và property effective sau precedence.
5. **Phân loại lỗi exclude.** Nếu Boot báo class không phải auto-configuration, xem class đó có trong candidate imports hay không và có đúng phiên bản runtime không.
6. **Kiểm tra import filter và classpath condition.** Class optional thiếu, resources vắng mặt hoặc version không phù hợp có thể làm candidate bị lọc hoặc cấu hình không match.
7. **Kiểm tra condition report.** Dùng `--debug` để phân biệt Exclusions và Negative matches; đọc nguyên nhân cụ thể.
8. **Truy vết bean thực tế.** Nếu bean vẫn tồn tại sau exclusion, tìm bean definition từ ứng dụng, component scan hoặc auto-configuration khác.
9. **Đối chiếu thứ tự.** Với hai auto-configurations cùng phụ thuộc vào `@ConditionalOnMissingBean`, xác định `before/after` và điều kiện cần thay vì dựa vào thứ tự imports ngẫu nhiên.
10. **Test consumer thật.** Test bean creation, no duplicate, exclusion, property disable, custom bean, đồng thời kiểm tra resource trong JAR.

Ghi nhớ: **phân biệt cái gì bị loại ở tầng selection với cái gì bị chặn ở tầng condition/bean.**

## 12. Lỗi phổ biến và cách sửa

| Ngộ nhận | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “Một dòng imports tương ứng chắc chắn một bean” | Imports công bố configuration class, không phải bean | Theo dõi selection rồi condition |
| “Có tên trùng là chắc chắn tạo hai bean” | Selector và group loại trùng FQCN; bean còn phụ thuộc conditions | Xác định có trùng tên hay trùng bean type |
| “Loại trùng giữ nguyên thứ tự imports mãi mãi” | Group có bước sort theo metadata | Dùng `before/after` khi cần thứ tự |
| “Mọi exclusion đều thắng bằng cách xóa bean” | Exclusion chỉ loại auto-configuration tương ứng | Truy vết những nơi khác đăng ký bean |
| “Exclude class thường cũng được” | Selector có kiểm tra excluded classes có hợp lệ | Chỉ exclude auto-configuration candidates |
| “`@ConditionalOnProperty` là exclusion” | Đây là condition ở pha xử lý configuration | Xem Negative matches, không phải chỉ Exclusions |
| “`@ConditionalOnMissingBean` chạy khi đang gộp chuỗi names” | Bean condition cần context bean definitions | Tách hai giai đoạn |
| “Mỗi JAR cho một selector riêng rồi tạo bean riêng” | Nhiều resources cùng đóng góp candidates vào selector/group | Quan sát tập candidate chung |
| “Đổi tên configuration không ảnh hưởng exclusions cũ” | Exclusion phụ thuộc tên class cụ thể | Kiểm tra version, resource và metadata migration |
| “`spring.autoconfigure.exclude` loại luôn dependency” | Class/JAR vẫn ở classpath | Dùng build tool để thay đổi dependency graph |
| “Cùng FQCN từ hai JAR khác bytecode không nguy hiểm” | Dedup tên không sửa classpath conflict | Gỡ trùng JAR và kiểm thử runtime |

## 13. Tự kiểm tra

**Câu 1.** Danh sách ứng viên là `[A, B, A, C, B]`, exclude `B`. Kết quả trước import filter và sort là gì?

**Đáp án:** Sau dedup là `[A, B, C]`; trừ `B` còn `[A, C]`.

**Câu 2.** Trong cùng group, entry 1 đóng góp A và B; entry 2 đóng góp B và C nhưng có exclusion A. A có quay lại vì entry 1 đã đóng góp không?

**Đáp án:** Không. Group hợp nhất configurations và loại **tập exclusions chung** trước sort/import. Chỉ còn B và C.

**Câu 3.** Một JAR khai báo cùng `FooAutoConfiguration` hai dòng trong imports. Có phải Boot phải khởi tạo hai instance của bean `Foo`?

**Đáp án:** Không. Tên candidate trùng được loại trong quá trình chọn. Hơn nữa, số bean cuối còn bị chi phối bởi `@Bean` và `@Conditional`.

**Câu 4.** Exclude `BarAutoConfiguration` nhưng ứng dụng vẫn có `BarClient`. Có mâu thuẫn không?

**Đáp án:** Không nhất thiết. Bean có thể do ứng dụng, scanning hoặc configuration khác tạo. Exclusion chỉ loại một cấu hình tự động có tên được nêu.

**Câu 5.** `@ConditionalOnProperty` không match có giống `spring.autoconfigure.exclude` không?

**Đáp án:** Không. Property condition được đánh giá khi xử lý configuration; exclusion tác động vào danh sách candidates trước import.

**Câu 6.** Tại sao phải phân biệt loại trùng trong selector với loại trùng ở group?

**Đáp án:** Selector chuẩn hóa mỗi entry; group còn hợp nhất nhiều entry, trừ mọi exclusions chung và sort trước import. Nếu chỉ nhìn một entry có thể bỏ qua hiệu ứng của exclusion do entry khác đóng góp.

**Câu 7.** Có nên dựa trên thứ tự dòng imports để bảo đảm `@ConditionalOnMissingBean` hoạt động như mong muốn?

**Đáp án:** Không. Group có sorter và metadata thứ tự. Thiết kế thứ tự rõ ràng bằng `before/after` khi cần, đồng thời test các tình huống app tự cung cấp bean.

## 14. Ghi nhớ

Ba phép biến đổi chính cần phân biệt:

```text
1. DEDUP       [A, B, A, C]       -> [A, B, C]
2. EXCLUDE     [A, B, C] - {B}    -> [A, C]
3. GROUP       union(entries) - union(exclusions) -> sort -> import
```

Các phép trên chỉ chọn **lớp cấu hình tự động**. Sau đó Spring đánh giá điều kiện của class và phương thức `@Bean`, đăng ký bean definitions phù hợp và tạo bean theo lifecycle. Đây là cách đọc đúng khi một starter có trên classpath nhưng bean không xuất hiện, hoặc một exclusion có hiệu lực mà bean cùng type vẫn tồn tại.

### Tài liệu tham khảo

- Spring Boot 3.3 API — `AutoConfigurationImportSelector`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Framework — `DeferredImportSelector`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html
- Java 17 — `LinkedHashSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html
