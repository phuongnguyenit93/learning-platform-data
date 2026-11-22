# Lần theo cấu hình tiền đề qua quan hệ before và after

## 1. Mục tiêu: tìm đúng cấu hình phải chạy trước một auto-configuration

Một auto-configuration thường phụ thuộc vào bean definition do cấu hình khác cung cấp. Ví dụ, cấu hình JDBC cần biết cấu hình nền tảng đã đăng ký bean kiểu `DataSource`; cấu hình repository cần biết `JdbcTemplate` đã được định nghĩa; cấu hình web adapter cần chờ cấu hình MVC nền tảng.

Khi thấy `@ConditionalOnBean` không khớp hoặc `@ConditionalOnMissingBean` lại cho phép tạo bean mặc định, hãy lần theo các câu hỏi:

- Cấu hình nào cung cấp bean tiền đề?
- Cấu hình đó có thật sự là một **auto-configuration candidate** trong lần khởi động này không?
- Cấu hình hiện tại khai báo `before` hay `after` đối với tiền đề nào?
- Có đường phụ thuộc gián tiếp qua một hoặc nhiều cấu hình trung gian không?
- Điều kiện của cấu hình tiền đề có khớp và bean definition có công bố kiểu đủ rõ không?
- Bean bị thiếu vì thứ tự xử lý, vì candidate bị loại, hay vì một điều kiện khác?

Bài này hướng dẫn đọc đồ thị phụ thuộc từ metadata `before`/`after`, lần theo tiền đề trực tiếp và gián tiếp, kiểm tra candidate/exclusion và xác nhận bằng `ApplicationContextRunner`. Phạm vi là Spring Boot 3.3.x, Spring Framework 6.1 và Java 17+.

## 2. Trước tiên phải xác định cấu hình nào thực sự được xem xét

Không phải class nào mang `@Configuration` cũng tự động trở thành auto-configuration. Trong Spring Boot 3.x, các auto-configuration được phát hiện qua resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng chứa tên đầy đủ của một class auto-configuration; có thể dùng `#` cho comment. Resource này được đóng gói trong JAR của thư viện. Spring Boot đọc các candidate từ resource trên runtime classpath.

Ví dụ nội dung file của một thư viện:

```text
com.example.storage.autoconfigure.StorageAutoConfiguration
com.example.jdbc.autoconfigure.JdbcAutoConfiguration
com.example.repository.autoconfigure.RepositoryAutoConfiguration
```

Các class này nên nằm trong package riêng và **không được component-scan như configuration thông thường**. Auto-configuration nên được nạp qua imports file; khi cần kết hợp configuration khác, dùng `@Import` cụ thể thay cho bật component scan rộng.

Một class có annotation `@AutoConfiguration` nhưng không được phát hiện qua cơ chế import thích hợp sẽ không tự xuất hiện chỉ vì class có mặt trong JAR. Vì vậy, trước khi lần theo quan hệ thứ tự, phải xác nhận candidate đã được đưa vào tập đang xử lý.

### 2.1. Pipeline candidate ở mức khái niệm

Trong luồng `@EnableAutoConfiguration` tiêu chuẩn, có thể hình dung:

```text
Runtime classpath
      |
      v
Đọc AutoConfiguration.imports từ các JAR
      |
      v
Loại candidate trùng lặp
      |
      v
Áp dụng exclusions
      |
      v
Áp dụng AutoConfigurationImportFilter
      |
      v
Tập candidate được chọn
      |
      v
AutoConfigurationSorter đọc before / after / order
      |
      v
Import các auto-configuration theo thứ tự đã sắp xếp
      |
      v
Xử lý condition và đăng ký bean definitions
```

Các bước này giải thích vì sao một cạnh `after` không thể tự đưa một class bị loại trở lại danh sách. Trước khi tranh luận về thứ tự, cần kiểm tra class nguồn có được phát hiện và còn nằm trong tập candidate sau exclusions/filter hay không.

Các cơ chế loại candidate thường gặp:

- `@EnableAutoConfiguration(exclude = ...)` loại class theo kiểu.
- `excludeName` loại theo tên class, hữu ích khi không muốn tham chiếu trực tiếp một dependency tùy chọn.
- Property `spring.autoconfigure.exclude` cho phép loại auto-configuration từ cấu hình ứng dụng.
- `AutoConfigurationImportFilter` có thể lọc candidate dựa trên metadata, thường để loại nhanh những cấu hình không phù hợp.
- Một condition ở cấp class như `@ConditionalOnClass` hoặc `@ConditionalOnProperty` có thể khiến configuration không được xử lý/đăng ký như mong đợi sau khi candidate đã được tìm thấy.

Phân biệt **không có trong candidate set** với **candidate có mặt nhưng condition không khớp**. Đây là hai nguyên nhân khác nhau và cần chứng cứ khác nhau.

## 3. Đọc đúng chiều của before và after

Spring Boot hỗ trợ hai cách diễn đạt quan hệ:

- `@AutoConfiguration(before = Other.class)` hoặc `@AutoConfigureBefore(Other.class)`: cấu hình hiện tại cần được áp dụng **trước** `Other`.
- `@AutoConfiguration(after = Other.class)` hoặc `@AutoConfigureAfter(Other.class)`: cấu hình hiện tại cần được áp dụng **sau** `Other`.

`@AutoConfiguration` cung cấp các thuộc tính `before`, `beforeName`, `after` và `afterName` như alias cho annotation thứ tự tương ứng. Có thể dùng annotation riêng `@AutoConfigureBefore` / `@AutoConfigureAfter` nếu muốn.

Ví dụ:

```java
@AutoConfiguration
class StorageAutoConfiguration {
    // Định nghĩa StorageClient hoặc bean nền tảng.
}

@AutoConfiguration(after = StorageAutoConfiguration.class)
class JdbcAutoConfiguration {
    // Được áp dụng sau StorageAutoConfiguration.
}
```

Ở đây `JdbcAutoConfiguration` khai báo mình phải chạy sau `StorageAutoConfiguration`. Hướng mũi tên trong đồ thị là:

```text
StorageAutoConfiguration  --->  JdbcAutoConfiguration
       tiền đề                       cấu hình phụ thuộc
```

Đừng đọc nhầm `after = StorageAutoConfiguration.class` thành “Storage chạy sau JDBC”. Annotation nằm trên JDBC và chỉ rõ cấu hình mà JDBC cần chờ.

### 3.1. Quy tắc đổi annotation thành cạnh đồ thị

Chọn một quy ước thống nhất: mũi tên đi từ cấu hình cần áp dụng trước sang cấu hình được áp dụng sau.

| Annotation trên cấu hình A | Cạnh cần vẽ | Diễn giải |
| --- | --- | --- |
| `A @AutoConfiguration(after = B.class)` | `B -> A` | B là tiền đề trực tiếp của A |
| `A @AutoConfiguration(before = B.class)` | `A -> B` | A là tiền đề trực tiếp của B |
| `A @AutoConfigureAfter(B.class)` | `B -> A` | Tương đương quan hệ after trên |
| `A @AutoConfigureBefore(B.class)` | `A -> B` | Tương đương quan hệ before trên |

Mẹo nhớ: `after` liệt kê những class đã phải được áp dụng; `before` liệt kê những class chưa được áp dụng.

### 3.2. Ví dụ lần theo một chuỗi tiền đề

Giả sử có ba cấu hình:

```java
@AutoConfiguration
class StorageAutoConfiguration {
}

@AutoConfiguration(after = StorageAutoConfiguration.class)
class JdbcAutoConfiguration {
}

@AutoConfiguration(after = JdbcAutoConfiguration.class)
class RepositoryAutoConfiguration {
}
```

Đồ thị:

```text
StorageAutoConfiguration
          |
          v
JdbcAutoConfiguration
          |
          v
RepositoryAutoConfiguration
```

Nếu đang điều tra `RepositoryAutoConfiguration`, hãy lần ngược:

1. `RepositoryAutoConfiguration.after` chỉ `JdbcAutoConfiguration`.
2. Mở `JdbcAutoConfiguration`; `JdbcAutoConfiguration.after` chỉ `StorageAutoConfiguration`.
3. `StorageAutoConfiguration` không khai báo tiền đề khác trong ví dụ.
4. Chuỗi tiền đề là `Storage -> Jdbc -> Repository`.

Đây là quan hệ **bắc cầu**: `Storage` phải đứng trước `Repository` thông qua `Jdbc`. Không cần thêm `after = StorageAutoConfiguration.class` vào Repository nếu quan hệ trực tiếp qua Jdbc đã diễn đạt đúng hợp đồng; chỉ thêm cạnh trực tiếp khi nó thể hiện một phụ thuộc độc lập thực sự.

### 3.3. Nhiều tiền đề không tự tạo thứ tự giữa chúng

Nếu A khai báo:

```java
@AutoConfiguration(after = {
        StorageAutoConfiguration.class,
        MetricsAutoConfiguration.class
})
class ReportingAutoConfiguration {
}
```

đồ thị có hai cạnh:

```text
StorageAutoConfiguration  ----\
                               ---> ReportingAutoConfiguration
MetricsAutoConfiguration  ----/
```

Hai cấu hình Storage và Metrics đều là tiền đề của Reporting, nhưng **không có kết luận** rằng Storage phải đứng trước Metrics hoặc ngược lại. Muốn xác định thứ tự giữa chúng, phải tìm một cạnh khác trong metadata. Không tự tạo thứ tự từ cách viết danh sách trong annotation.

Tương tự, nếu một candidate không có cạnh kết nối với candidate khác, đừng dựa vào thứ tự tình cờ trong file imports, thứ tự alphabet hay thứ tự đối số test để suy ra quan hệ nghiệp vụ.

## 4. Lần ngược tiền đề trực tiếp và gián tiếp

Khi đã chọn được class đích, hãy đọc metadata theo hai hướng.

### 4.1. Đọc thuộc tính after ngay trên class đích

Ví dụ:

```java
@AutoConfiguration(
    after = {
        DataSourceAutoConfiguration.class,
        JdbcTemplateAutoConfiguration.class
    })
class RepositoryAutoConfiguration {
}
```

Hai class trong `after` là tiền đề trực tiếp được khai báo. Với mỗi class:

1. Xác nhận tên class chính xác.
2. Tìm class trong candidate imports.
3. Mở class đó và đọc `before`/`after` của nó.
4. Lặp lại cho đến khi tới các cấu hình nền không còn tiền đề được khai báo hoặc tới một candidate không có trong tập hiện tại.

### 4.2. Tìm cấu hình khác có before trỏ về class đích

Không phải mọi quan hệ đều được viết trong `after` của class đích. Một cấu hình khác có thể khai báo:

```java
@AutoConfiguration(before = RepositoryAutoConfiguration.class)
class RepositoryMetricsAutoConfiguration {
}
```

Do đó, khi lần theo đồ thị ngược, phải tìm cả những class khác có `before` tham chiếu đến class đang điều tra. Nếu chỉ đọc `after` của class đích, bạn có thể bỏ sót các predecessor được khai báo từ phía còn lại.

Quy tắc tìm kiếm thực tế:

- **Đi ngược:** tìm tất cả class A có `after` chứa B, và tất cả class A có `before` chứa B theo chiều cạnh A → B (tức predecessor của B).
- **Đi xuôi:** từ B, tìm các class B có `after` chứa A (A → B), và các class B có `before` chứa C (B → C).
- Lặp lại để thu được các đường trực tiếp và bắc cầu.

### 4.3. Ghi lại đồ thị thay vì chỉ ghi một danh sách

Một bảng truy vết giúp người review kiểm tra dễ hơn:

| Cấu hình | Quan hệ khai báo | Cạnh chuẩn hóa | Vai trò |
| --- | --- | --- | --- |
| `StorageAutoConfiguration` | Không có | — | Nguồn bean nền |
| `JdbcAutoConfiguration` | `after = StorageAutoConfiguration` | Storage → JDBC | Tiền đề trực tiếp |
| `RepositoryAutoConfiguration` | `after = JdbcAutoConfiguration` | JDBC → Repository | Cấu hình đang phụ thuộc |
| `RepositoryMetricsAutoConfiguration` | `before = RepositoryAutoConfiguration` | Metrics → Repository | Tiền đề khác |

Đồ thị tương ứng có thể là:

```text
StorageAutoConfiguration ---> JdbcAutoConfiguration ---\
                                                        ---> RepositoryAutoConfiguration
RepositoryMetricsAutoConfiguration -------------------/
```

Từ hình này chỉ kết luận Storage và Metrics đều đứng trước Repository. Không có cạnh giữa Storage và Metrics thì không khẳng định cái nào trước cái nào.

## 5. beforeName và afterName: quan hệ không cần class literal

Khi cấu hình hiện tại phụ thuộc vào một auto-configuration thuộc thư viện tùy chọn, dùng class literal có thể tạo phụ thuộc compile-time không mong muốn. `@AutoConfiguration` cung cấp `beforeName` và `afterName` để tham chiếu tên class đầy đủ:

```java
@AutoConfiguration(
    afterName = "com.example.storage.autoconfigure.StorageAutoConfiguration")
class JdbcAutoConfiguration {
}
```

Hoặc:

```java
@AutoConfiguration(
    beforeName = "com.example.metrics.autoconfigure.MetricsAutoConfiguration")
class StorageAutoConfiguration {
}
```

Tên phải khớp chính xác fully qualified class name. Với nested class, dùng dấu `$` phân cách class ngoài và class lồng, ví dụ:

```java
@AutoConfiguration(
    afterName = "com.example.OuterConfiguration$NestedAutoConfiguration")
class DependentAutoConfiguration {
}
```

`afterName` không tự thêm class được tham chiếu vào candidate list. Nó chỉ mô tả quan hệ nếu class tên đó có trong tập auto-configuration đang sắp xếp. Nếu class vắng mặt, bị exclude hoặc không được chọn, quan hệ không thể cung cấp bean tiền đề.

Khi điều tra lỗi tên, kiểm tra package, chữ hoa/thường, nested `$`, refactor package và file replacements. Không dùng tên bean runtime thay cho tên class auto-configuration.

## 6. Phân biệt thứ tự tương đối, thứ tự ưu tiên và thứ tự khởi tạo

Ba cơ chế thường bị nhầm:

| Cơ chế | Dùng để làm gì? | Không làm gì? |
| --- | --- | --- |
| `@AutoConfiguration(before/after)` | Biểu đạt phụ thuộc tương đối giữa các auto-configuration | Không ép thứ tự constructor hoặc tạo instance |
| `@AutoConfigureOrder` | Cho thứ tự tổng quát giữa các auto-configuration không có quan hệ trực tiếp | Không diễn đạt rõ một bean tiền đề cụ thể |
| `@DependsOn` / dependency injection | Điều khiển quan hệ tạo bean instance | Không khiến một condition đã đánh giá chạy lại |

Spring Boot cũng ghi rõ: thứ tự áp dụng auto-configuration chỉ ảnh hưởng thứ tự **bean definitions được đăng ký**. Việc khởi tạo các bean sau đó do dependency của bean và `@DependsOn` quyết định.

Ví dụ:

```java
@Bean
ConsumerService consumerService(StorageClient storageClient) {
    return new ConsumerService(storageClient);
}
```

Dependency injection đã thể hiện `ConsumerService` cần `StorageClient`. Container sẽ đảm bảo dependency cần thiết được cung cấp khi tạo consumer. Không cần thêm `@DependsOn` chỉ để làm injection hoạt động.

Ngược lại, `@ConditionalOnBean(StorageClient.class)` được đánh giá trong quá trình xử lý cấu hình. Nếu auto-configuration cung cấp StorageClient chưa được xử lý khi condition chạy, việc thêm `@DependsOn` không giúp condition nhìn thấy bean definition. Khi đó cần xem `before`/`after` và metadata kiểu.

`@Order` thông thường cũng không phải cách thay thế cho `@AutoConfigureBefore`/`@AutoConfigureAfter`. Nếu cần quan hệ tương đối, hãy khai báo cạnh cụ thể. `@AutoConfigureOrder` chỉ phù hợp khi cần một ưu tiên tổng quát giữa các auto-configuration không biết trực tiếp về nhau.

## 7. Xác minh candidate, exclusions và điều kiện trước khi kết luận lỗi ordering

Một cạnh đồ thị chỉ có ích khi hai đầu là candidate có liên quan trong lần khởi động hiện tại.

### 7.1. Xác nhận resource imports

Trong JAR, kiểm tra có resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

và có tên class đang cần. Nếu thư viện chứa nhiều auto-configuration, đọc hết file để xác định các candidate cùng nhóm.

### 7.2. Kiểm tra exclusion

Tìm:

- `@EnableAutoConfiguration(exclude = ...)`
- `excludeName`
- `spring.autoconfigure.exclude`
- Cấu hình test có `exclude`/`excludeName`
- Exclusion hoặc import filter do framework/thư viện tích hợp thêm

Nếu source bị loại, `after` của consumer không thể khiến source được import trở lại.

### 7.3. Kiểm tra condition của chính source

Ngay cả khi source là candidate và được áp dụng trước, bean tiền đề vẫn có thể không xuất hiện nếu:

- `@ConditionalOnClass` không khớp.
- `@ConditionalOnProperty` tắt hoặc thiếu giá trị cần thiết.
- `@ConditionalOnBean`/`@ConditionalOnMissingBean` của source không khớp.
- `@Bean` method bị điều kiện riêng loại bỏ.
- Bean definition được đăng ký nhưng kiểu trả về/FactoryBean metadata không đủ để condition phía sau nhận diện.
- Bean name/type mà consumer kiểm tra không phải hợp đồng thực tế của source.

Do đó, trace thứ tự không dừng ở class annotation. Hãy mở bean method tạo prerequisite và đọc toàn bộ condition trên class, nested configuration và method đó.

### 7.4. Kiểm tra đổi tên class

Nếu một auto-configuration được di chuyển/đổi tên, Boot 3.x hỗ trợ resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
```

Resource này ánh xạ class cũ sang class thay thế. Vì class auto-configuration có thể được tham chiếu trong `before`/`after` và `exclude`, khi refactor package cần cập nhật quan hệ và replacement metadata tương ứng. Không để tên cũ còn sót trong `afterName` rồi giả định Boot sẽ đoán class mới.

## 8. Quy trình thực tế để lần theo tiền đề trong project

Áp dụng lần lượt để không nhầm một class có trong source code với một candidate thực sự được nạp.

### Bước 1: tìm dependency chứa auto-configuration

Với Gradle, xem runtime dependency graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm riêng thư viện liên quan:

```bash
./gradlew dependencyInsight --dependency storage-starter --configuration runtimeClasspath
```

Thay `storage-starter` bằng tên module/artifact thực tế. Mục tiêu là xác nhận thư viện nằm trong runtime classpath và biết JAR nào cần mở.

### Bước 2: tìm imports resource bên trong JAR

Liệt kê nội dung JAR:

```bash
jar tf path/to/storage-starter.jar
```

Lọc tên resource bằng công cụ phù hợp (ví dụ `grep` trên Linux/macOS hoặc `Select-String` trong PowerShell). Sau khi xác nhận đường dẫn, giải nén riêng resource vào thư mục tạm để đọc:

```bash
jar xf path/to/storage-starter.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Đọc file đã giải nén. Không chỉnh trực tiếp JAR dependency; đây là bước đọc để truy nguyên candidate.

### Bước 3: tìm annotation trong source

Trong source project hoặc source JAR, tìm:

```bash
rg -n "@AutoConfiguration|@AutoConfigureBefore|@AutoConfigureAfter|@AutoConfigureOrder|beforeName|afterName" .
```

Thu thập tất cả class có quan hệ đến class đích. Nếu class chỉ có trong dependency binary, mở source JAR/IDE decompiler hoặc đọc annotation metadata qua công cụ phù hợp.

### Bước 4: chuẩn hóa thành đồ thị

Đổi mọi relation thành mũi tên từ trước sang sau:

- `A after B` → `B -> A`.
- `A before B` → `A -> B`.

Đánh dấu candidate nào có trong imports, candidate nào bị exclude, candidate nào bị filter và candidate nào có condition không khớp. Sau đó lần ngược từ cấu hình đích để tìm toàn bộ predecessor trực tiếp và gián tiếp.

### Bước 5: đối chiếu bean condition

Tìm method `@Bean` sử dụng `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`. So sánh type/name condition yêu cầu với kiểu trả về/metadata của bean nguồn. Một đồ thị đúng vẫn không đảm bảo condition match nếu source không đăng ký bean hoặc type không nhận diện được.

### Bước 6: chứng minh bằng test

Dùng `ApplicationContextRunner` và `AutoConfigurations.of(...)` để dựng context nhỏ. Giữ classpath/property giống nhau, chỉ thay quan hệ `before`/`after` hoặc việc có/không có source. Assert cả bean cuối cùng lẫn việc condition cho phép/không cho phép bean phụ thuộc.

### Bước 7: debug sorter khi cần

Khi metadata phức tạp, đặt breakpoint trong `AutoConfigurationSorter.getInPriorityOrder(...)` hoặc luồng `AutoConfigurationImportSelector` để xem tập candidate và thứ tự đã sắp xếp trong đúng phiên bản Spring Boot đang chạy. Đây là lớp nội bộ để debug; không phụ thuộc trực tiếp vào implementation class này trong code sản phẩm.

`--debug` và Conditions Evaluation Report hữu ích để tìm condition nào match/no-match, nhưng report không phải một danh sách chính thức thay thế cho việc lần theo metadata thứ tự. Dùng debugger hoặc test đảo thứ tự đầu vào để xác nhận relation.

## 9. Ví dụ đồ thị tiền đề hoàn chỉnh

Giả sử thư viện có các candidate:

- `StorageAutoConfiguration`: cung cấp `StorageMarker`.
- `JdbcAutoConfiguration`: cần Storage, khai báo `after = StorageAutoConfiguration`.
- `RepositoryAutoConfiguration`: cần JDBC, khai báo `after = JdbcAutoConfiguration`.
- `MetricsAutoConfiguration`: cần repository, khai báo `after = RepositoryAutoConfiguration`.
- `RepositoryMetricsAutoConfiguration`: khai báo `before = RepositoryAutoConfiguration`.

Đồ thị:

```text
StorageAutoConfiguration
          |
          v
JdbcAutoConfiguration
          |
          v
RepositoryAutoConfiguration <--- RepositoryMetricsAutoConfiguration
          |
          v
MetricsAutoConfiguration
```

Nếu đang điều tra `MetricsAutoConfiguration`, lần ngược sẽ thu được:
`RepositoryAutoConfiguration`, sau đó `JdbcAutoConfiguration`, sau đó `StorageAutoConfiguration`; đồng thời tìm class khác khai báo `before = MetricsAutoConfiguration` hoặc `before = RepositoryAutoConfiguration` để phát hiện predecessor ở phía ngược.

Không kết luận `RepositoryMetricsAutoConfiguration` phải đứng trước Storage hoặc JDBC vì đồ thị không có cạnh như vậy. Nó chỉ cần đứng trước Repository.

Nếu `JdbcAutoConfiguration` bị exclude, chuỗi bị đứt. Nếu `StorageAutoConfiguration` có mặt nhưng condition của bean Storage không khớp, `JdbcAutoConfiguration` vẫn có thể được áp dụng sau nó nhưng `@ConditionalOnBean(StorageMarker.class)` có thể no-match. Nếu Storage bean definition khai báo kiểu quá rộng, condition cũng có thể không nhận diện được. Mỗi tình huống có cách sửa khác nhau.

## 10. Thực hành chạy được: kiểm chứng quan hệ trực tiếp, gián tiếp và before

Bộ test sau tạo các auto-configuration lồng trong một test class để cô lập. `AutoConfigurations.of(...)` sử dụng cơ chế sắp xếp auto-configuration; thứ tự truyền các class vào helper không phải hợp đồng ordering.

### 10.1. Cấu trúc project

```text
auto-configuration-prerequisite-trace/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/AutoConfigurationPrerequisiteTraceTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'auto-configuration-prerequisite-trace'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

test {
    useJUnitPlatform()
}
```

### 10.2. File test Java 17 hoàn chỉnh

`src/test/java/demo/AutoConfigurationPrerequisiteTraceTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationPrerequisiteTraceTest {

    record StorageMarker(String origin) {}

    record JdbcMarker(String source) {}

    record RepositoryMarker(String source) {}

    record EarlyMarker(String source) {}

    record NameBasedMarker(String source) {}

    record FallbackMarker(String origin) {}

    @AutoConfiguration
    static class StorageAutoConfiguration {

        @Bean
        StorageMarker storageMarker() {
            return new StorageMarker("storage");
        }
    }

    @AutoConfiguration(after = StorageAutoConfiguration.class)
    static class JdbcAutoConfiguration {

        @Bean
        @ConditionalOnBean(StorageMarker.class)
        JdbcMarker jdbcMarker(StorageMarker storage) {
            return new JdbcMarker(storage.origin());
        }
    }

    @AutoConfiguration(after = JdbcAutoConfiguration.class)
    static class RepositoryAutoConfiguration {

        @Bean
        @ConditionalOnBean(JdbcMarker.class)
        RepositoryMarker repositoryMarker(JdbcMarker jdbc) {
            return new RepositoryMarker(jdbc.source());
        }
    }

    @AutoConfiguration(before = StorageAutoConfiguration.class)
    static class EarlyObserverAutoConfiguration {

        @Bean
        @ConditionalOnBean(StorageMarker.class)
        EarlyMarker earlyMarker() {
            return new EarlyMarker("storage was already visible");
        }
    }

    @AutoConfiguration(
            afterName =
                    "demo.AutoConfigurationPrerequisiteTraceTest$StorageAutoConfiguration")
    static class NameBasedJdbcAutoConfiguration {

        @Bean
        @ConditionalOnBean(StorageMarker.class)
        NameBasedMarker nameBasedMarker() {
            return new NameBasedMarker("name-based prerequisite");
        }
    }

    @AutoConfiguration(after = StorageAutoConfiguration.class)
    static class FallbackAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(StorageMarker.class)
        FallbackMarker fallbackMarker() {
            return new FallbackMarker("fallback");
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void afterRelationMakesPrerequisiteVisible() {
        // Consumer được truyền trước; metadata after vẫn sắp Storage lên trước.
        runner.withConfiguration(AutoConfigurations.of(
                JdbcAutoConfiguration.class,
                StorageAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(StorageMarker.class);
                    assertThat(context).hasSingleBean(JdbcMarker.class);
                    assertThat(context).hasBean("storageMarker");
                    assertThat(context).hasBean("jdbcMarker");
                    assertThat(context.getBean(JdbcMarker.class).source())
                            .isEqualTo("storage");
                });
    }

    @Test
    void beforeRelationCanMakeConsumerRunTooEarly() {
        // Storage được truyền trước, nhưng EarlyObserver khai báo before Storage.
        runner.withConfiguration(AutoConfigurations.of(
                StorageAutoConfiguration.class,
                EarlyObserverAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasBean("storageMarker");
                    assertThat(context).doesNotHaveBean("earlyMarker");
                    assertThat(context).hasSingleBean(StorageMarker.class);
                });
    }

    @Test
    void afterNameResolvesTheExactPrerequisiteClassName() {
        runner.withConfiguration(AutoConfigurations.of(
                NameBasedJdbcAutoConfiguration.class,
                StorageAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasBean("storageMarker");
                    assertThat(context).hasSingleBean(NameBasedMarker.class);
                });
    }

    @Test
    void transitiveAfterRelationsExposeTheFullPrerequisiteChain() {
        runner.withConfiguration(AutoConfigurations.of(
                RepositoryAutoConfiguration.class,
                JdbcAutoConfiguration.class,
                StorageAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(StorageMarker.class);
                    assertThat(context).hasSingleBean(JdbcMarker.class);
                    assertThat(context).hasSingleBean(RepositoryMarker.class);
                    assertThat(context.getBean(RepositoryMarker.class).source())
                            .isEqualTo("storage");
                });
    }

    @Test
    void missingPrerequisiteLeavesConditionalFeatureAbsent() {
        runner.withConfiguration(AutoConfigurations.of(
                JdbcAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(StorageMarker.class);
                    assertThat(context).doesNotHaveBean(JdbcMarker.class);
                });
    }

    @Test
    void fallbackAfterSourceBacksOffWhenSourceExists() {
        runner.withConfiguration(AutoConfigurations.of(
                FallbackAutoConfiguration.class,
                StorageAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(StorageMarker.class);
                    assertThat(context).hasBean("storageMarker");
                    assertThat(context).doesNotHaveBean("fallbackMarker");
                });
    }
}
```

### 10.3. Chạy test

Trong thư mục project:

```bash
gradle test --tests demo.AutoConfigurationPrerequisiteTraceTest
```

Nếu có Gradle Wrapper trên Linux/macOS:

```bash
./gradlew test --tests demo.AutoConfigurationPrerequisiteTraceTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.AutoConfigurationPrerequisiteTraceTest
```

Kết quả kỳ vọng là **6 test passed**. Đây là kết quả dự kiến khi dependency tải được và JDK/Gradle tương thích; log Gradle không có một stdout cố định.

### 10.4. Vì sao từng test quan trọng?

| Test | Metadata được thử | Điều cần quan sát |
| --- | --- | --- |
| `afterRelationMakesPrerequisiteVisible` | JDBC `after` Storage | Dù đối số test truyền JDBC trước, bean Storage được định nghĩa trước khi JDBC condition xét; JDBC bean xuất hiện |
| `beforeRelationCanMakeConsumerRunTooEarly` | EarlyObserver `before` Storage | Condition chạy trước Storage nên không tạo early marker; Storage vẫn có sau refresh |
| `afterNameResolvesTheExactPrerequisiteClassName` | `afterName` | Chuỗi FQCN đúng giúp sắp xếp khi không dùng class literal |
| `transitiveAfterRelationsExposeTheFullPrerequisiteChain` | Storage → JDBC → Repository | Cả hai cạnh after tạo được chuỗi tiền đề bắc cầu |
| `missingPrerequisiteLeavesConditionalFeatureAbsent` | Thiếu Storage candidate | Condition bean không khớp; không có JDBC marker |
| `fallbackAfterSourceBacksOffWhenSourceExists` | Fallback `after` Source + MissingBean | Source đã hiện diện nên fallback không đăng ký |

Test `beforeRelationCanMakeConsumerRunTooEarly` rất hữu ích: sau khi context refresh, `storageMarker` có tồn tại, nhưng `earlyMarker` vẫn vắng. Điều đó chứng minh điều kiện không tự chạy lại khi source được xử lý muộn hơn.

Test `afterName` sử dụng tên nested class có dấu `$`. Nếu đổi tên/package class, chuỗi phải được cập nhật theo tên class mới.

## 11. Các lỗi thường gặp khi lần theo before/after

| Triệu chứng | Nguyên nhân | Cách điều tra |
| --- | --- | --- |
| Thêm `after` nhưng condition vẫn no-match | Source không phải candidate, bị exclude/filter hoặc condition của source không khớp | Kiểm tra imports, exclusions, report và condition của source |
| Class có trong JAR nhưng không xuất hiện khi khởi động | Không có trong `AutoConfiguration.imports` hoặc resource đóng gói sai | Kiểm tra nội dung JAR và resource path |
| Consumer có `after` nhưng bean nguồn vẫn không được tìm thấy | Source có mặt nhưng không tạo bean; hoặc return type/FactoryBean metadata quá rộng | Đọc bean method, condition và kiểu khai báo |
| Quan hệ before/after không đổi khi đổi thứ tự file imports | Boot sắp xếp candidate bằng metadata | Không dựa vào dòng trong imports; kiểm chứng bằng test |
| Dùng `@DependsOn` nhưng condition vẫn fail | Đã sửa thứ tự tạo instance, trong khi lỗi xảy ra khi xử lý bean definition | Sửa quan hệ auto-configuration |
| Dùng `@Order` mà auto-config vẫn sai thứ tự | `@Order` không thay cho quan hệ auto-config | Dùng `@AutoConfiguration(before/after)` hoặc `@AutoConfigureBefore/After` |
| `afterName` không có tác dụng | Sai FQCN, sai `$` của nested class hoặc target không nằm trong candidate set | Đối chiếu tên class trong imports/JAR |
| Có nhiều predecessor nhưng thứ tự giữa chúng không như dự đoán | Chỉ có cạnh cùng trỏ tới consumer, chưa có cạnh giữa các predecessor | Vẽ đủ graph; không suy ra thứ tự không được khai báo |
| Source đã bị exclude | Quan hệ order không thể nạp lại source | Bỏ exclusion hoặc sửa candidate discovery theo đúng ý định |
| Test pass nhưng ứng dụng thật khác | Test không tái hiện cùng candidate set, exclusions, properties, classpath hoặc context | So sánh đầu vào test với runtime và dùng report/debugger |

### 11.1. Đừng nhầm thứ tự imports với thứ tự được áp dụng

File `AutoConfiguration.imports` là danh sách candidate, không phải tài liệu để người đọc dựa vào thứ tự dòng mà kết luận thứ tự cuối. Spring Boot thu thập candidate, áp dụng exclusion/filter rồi sắp xếp theo metadata ordering.

Tương tự, trong `ApplicationContextRunner`, không cần sắp thứ tự các class truyền vào `AutoConfigurations.of(...)` để mô phỏng quan hệ; chính metadata before/after là điều cần test.

### 11.2. Đừng nhầm điều kiện no-match với lỗi ordering

Nếu `@ConditionalOnBean` no-match, hãy xác định condition có chạy trước source không. Nếu source đã được xử lý trước mà vẫn no-match, kiểm tra:

- Type yêu cầu có đúng với kiểu trả về khai báo không?
- Bean source có bị condition khác loại không?
- Có dùng `search = SearchStrategy.CURRENT` trong khi bean ở parent context không?
- Source là sản phẩm `FactoryBean` và `getObjectType()` có công bố kiểu đủ cụ thể không?
- Consumer đang kiểm tra bean type hay bean name khác với source thực tế?

Chỉ thay `after` khi đồ thị và thời điểm cho thấy đó là nguyên nhân.

### 11.3. Đồ thị mâu thuẫn

Một chuỗi ràng buộc tạo vòng, ví dụ A `after` B, B `after` C và C `after` A, không thể có thứ tự tuyến tính thỏa tất cả cạnh. Hãy xóa hoặc thiết kế lại quan hệ để đồ thị không mâu thuẫn. Đừng cố chữa vòng bằng cách thêm `@AutoConfigureOrder`; ưu tiên phải phản ánh dependency thực sự.

## 12. Checklist review khi thêm hoặc sửa quan hệ thứ tự

- [ ] Class được đánh dấu `@AutoConfiguration` và được liệt kê trong `AutoConfiguration.imports` của JAR.
- [ ] Class tiền đề cũng có mặt trong candidate set của lần chạy cần xét.
- [ ] Đã kiểm tra `exclude`, `excludeName`, `spring.autoconfigure.exclude` và import filters.
- [ ] Đã đọc `before`, `after`, `beforeName`, `afterName` trên cả cấu hình đích và các cấu hình liên quan.
- [ ] Đã chuẩn hóa mọi relation thành cạnh từ trước sang sau.
- [ ] Đã lần theo predecessor bắc cầu, không chỉ đọc một cạnh trực tiếp.
- [ ] Không suy ra thứ tự giữa hai cấu hình nếu không có cạnh ràng buộc.
- [ ] Đã kiểm tra condition của source và kiểu bean definition mà consumer cần.
- [ ] Không dùng `@DependsOn`/`@Order` để thay cho order auto-config.
- [ ] Có test chứng minh bean xuất hiện/vắng mặt trong đúng trường hợp.
- [ ] Test đảo thứ tự đối số `AutoConfigurations.of(...)` để chứng minh metadata mới là hợp đồng.
- [ ] Có test trường hợp thiếu source và user override/fallback nếu feature có hỗ trợ.
- [ ] Đã xác minh class name string của `beforeName`/`afterName`, bao gồm `$` nếu nested.
- [ ] Đã cập nhật references/replacements khi đổi tên class.
- [ ] Đã kiểm tra không có chu trình ordering.

**Ghi nhớ:** Muốn lần theo cấu hình tiền đề, hãy bắt đầu từ candidate thực sự được chọn, đổi `before`/`after` thành cạnh có hướng, rồi lần ngược tất cả predecessor trực tiếp và gián tiếp. Sau đó xác minh source có được xử lý và tạo bean definition phù hợp trước khi consumer condition chạy. Đồ thị metadata giải thích **thứ tự định nghĩa**; bean assertions chứng minh **hành vi cuối cùng**.

## Tài liệu chính thức

- Spring Boot 3.3 — Creating Your Own Auto-configuration, candidate discovery, imports file và ordering: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 API — `@AutoConfiguration`, các thuộc tính `before`, `beforeName`, `after`, `afterName`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 API — `@AutoConfigureBefore`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html
- Spring Boot 3.3 API — `@AutoConfigureAfter`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html
- Spring Boot 3.3 API — `@AutoConfigureOrder`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html
- Spring Boot 3.3 — Testing Auto-configuration with `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
