# Phụ thuộc tùy chọn và ảnh hưởng đến dự án sử dụng thư viện

Một thư viện Java có thể cung cấp chức năng chính mà không cần mọi thư viện phụ trợ. Ví dụ, một thư viện xử lý dữ liệu có thể tích hợp thêm Jackson để đọc JSON, SLF4J để ghi log, hoặc một driver để kết nối tới một hệ thống cụ thể. Không phải ứng dụng nào sử dụng thư viện đó cũng cần tất cả các tích hợp này.

Nếu mọi dependency đều được truyền tự động tới mọi dự án sử dụng thư viện, dependency graph của ứng dụng có thể lớn hơn cần thiết. Ứng dụng có thể phải tải những thư viện không dùng, gặp xung đột version, hoặc vô tình kéo thêm thành phần có giấy phép và yêu cầu bảo mật riêng.

**Phụ thuộc tùy chọn (optional dependency)** là cách biểu diễn một dependency chỉ cần cho một phần chức năng hoặc chỉ nên được đưa vào khi consumer chủ động chọn. Cách khai báo và hành vi cụ thể khác nhau giữa Maven và Gradle. Cần hiểu dependency nào có mặt trong project đang phát triển, dependency nào được truyền sang consumer, và dependency nào cần có khi ứng dụng thực sự chạy.

## 1. Dependency của thư viện ảnh hưởng đến consumer như thế nào?

Giả sử có ba module:

```text
application
    |
    v
reporting-library
    |
    +----> json-library
    |
    +----> cloud-storage-sdk
    |
    +----> logging-api
```

`application` sử dụng `reporting-library`. Thư viện này có chức năng xuất báo cáo cơ bản, đồng thời hỗ trợ JSON và lưu báo cáo lên cloud. Ứng dụng chỉ xuất báo cáo văn bản có thể không cần cloud SDK. Nếu mọi dependency của `reporting-library` đều được truyền xuống consumer một cách tự động, ứng dụng có thể nhận thêm các thư viện không sử dụng.

Dependency có thể ảnh hưởng đến consumer ở nhiều khía cạnh:

- **Compile classpath:** compiler của consumer có nhìn thấy kiểu dữ liệu từ dependency hay không.
- **Runtime classpath:** dependency có được đưa vào môi trường chạy của ứng dụng hay không.
- **Dependency graph:** dependency bắc cầu có tiếp tục kéo các dependency khác vào hay không.
- **Version resolution:** nhiều module có thể yêu cầu các version khác nhau của cùng một thư viện.
- **Kích thước và thời gian phân giải:** nhiều artifact hơn có thể làm tăng dữ liệu tải, cache và thời gian build.
- **Bảo mật và giấy phép:** dependency bổ sung tạo thêm thành phần cần theo dõi lỗ hổng, bản vá và điều kiện sử dụng.
- **Tính tương thích:** API công khai của thư viện có thể vô tình làm consumer phụ thuộc vào kiểu của một thư viện phụ trợ.

Vì vậy, khi thiết kế dependency cho một thư viện dùng chung, cần phân biệt dependency bắt buộc với dependency chỉ phục vụ một tính năng bổ sung.

## 2. Dependency tùy chọn không có nghĩa là dependency không được sử dụng

Một hiểu nhầm thường gặp là cho rằng dependency có cờ optional thì project hiện tại không cần thư viện đó. Trong Maven, điều này không đúng.

Khi một dependency được đánh dấu optional trong POM của thư viện:

1. Chính thư viện vẫn có thể sử dụng dependency đó trong quá trình compile hoặc runtime theo scope đã khai báo.
2. Maven không tự động truyền dependency optional đó sang dependency graph của project sử dụng thư viện.
3. Nếu consumer muốn dùng tính năng phụ thuộc vào thư viện optional, consumer phải khai báo dependency tương ứng một cách tường minh.

Optional chủ yếu điều khiển **tính bắc cầu (transitivity)**. Nó không tự biến dependency thành lazy loading, không tự kiểm tra tính năng có được gọi hay không, và cũng không bảo đảm ứng dụng có thể chạy khi thiếu class mà code đang cần.

Trong Gradle, không có một thuộc tính `optional = true` chung tương đương trực tiếp cho mọi dependency. Gradle sử dụng các configuration như `api`, `implementation`, `compileOnly`, `runtimeOnly` và mô hình variant/feature để thể hiện dependency được cung cấp ở classpath nào và consumer chọn tính năng nào.

## 3. Maven: khai báo dependency optional

Trong Maven, dependency có thể được đánh dấu bằng phần tử `<optional>true</optional>`.

Ví dụ, `reporting-library` có chức năng JSON tùy chọn:

```xml
<dependencies>
  <dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.17.2</version>
    <optional>true</optional>
  </dependency>
</dependencies>
```

Dependency này vẫn thuộc dependency của `reporting-library`. Mã nguồn của thư viện có thể import Jackson và biên dịch phần tích hợp JSON. Tuy nhiên, một project khác chỉ khai báo `reporting-library` sẽ không tự động nhận `jackson-databind` qua quan hệ bắc cầu.

Ví dụ consumer:

```xml
<dependencies>
  <dependency>
    <groupId>com.example</groupId>
    <artifactId>reporting-library</artifactId>
    <version>1.0.0</version>
  </dependency>
</dependencies>
```

Consumer trên nhận `reporting-library` cùng các dependency bắc cầu thông thường của nó, nhưng không tự nhận dependency Jackson được đánh dấu optional trong POM của thư viện.

Nếu ứng dụng cần dùng chức năng JSON, hãy khai báo Jackson trực tiếp:

```xml
<dependencies>
  <dependency>
    <groupId>com.example</groupId>
    <artifactId>reporting-library</artifactId>
    <version>1.0.0</version>
  </dependency>

  <dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.17.2</version>
  </dependency>
</dependencies>
```

Khi đó, ứng dụng chủ động chọn dependency mà tính năng JSON cần.

### 3.1. Optional ảnh hưởng đến consumer, không xóa dependency khỏi project gốc

Hãy phân biệt hai dependency graph:

```text
Dependency graph của reporting-library

reporting-library
    |
    +----> jackson-databind (optional trong POM)
```

```text
Dependency graph của application chỉ khai báo reporting-library

application
    |
    v
reporting-library
```

Khi consumer khai báo Jackson trực tiếp:

```text
application
    |
    +----> reporting-library
    |
    +----> jackson-databind
```

Đây là lý do thư viện vẫn có thể compile phần tích hợp optional trong khi ứng dụng consumer không bắt buộc phải tải thư viện phụ trợ đó.

### 3.2. Optional độc lập với scope

Trong Maven, scope xác định dependency được sử dụng ở những classpath nào và có được truyền bắc cầu hay không. Optional là một thuộc tính bổ sung điều khiển việc dependency có được truyền xuống consumer hay không.

Một số scope phổ biến:

| Scope | Compile classpath của project hiện tại | Runtime classpath của project hiện tại | Truyền bắc cầu tới consumer |
|---|---|---|---|
| `compile` | Có | Có | Có, nếu không optional |
| `provided` | Có | Không theo runtime thông thường | Không truyền như dependency runtime thông thường |
| `runtime` | Không cần cho compile source chính | Có | Có ở runtime, nếu không optional |
| `test` | Có trong test compile | Có trong test runtime | Không |
| `system` | Có theo đường dẫn hệ thống khai báo | Có theo cấu hình tương ứng | Không; scope này thường nên tránh |

Khi đánh dấu một dependency `compile` là optional, dependency vẫn có thể tham gia compile/runtime của chính project khai báo nó, nhưng bị loại khỏi dependency graph bắc cầu của consumer. Nếu scope vốn đã không truyền bắc cầu, optional không làm nó trở nên truyền bắc cầu.

Không nên dùng `optional` để thay thế `provided`, `runtime` hoặc `test`. Hãy chọn scope theo thời điểm dependency cần thiết, rồi dùng optional nếu muốn giới hạn việc truyền dependency sang project tiêu thụ.

## 4. Ảnh hưởng tới API công khai của thư viện

Một dependency optional có thể xuất hiện trong API công khai. Ví dụ:

```java
package com.example.reporting;

import com.fasterxml.jackson.databind.JsonNode;

public class JsonReportReader {
    public JsonNode read(String json) {
        // Parse JSON bằng Jackson.
        return null;
    }
}
```

Nếu `jackson-databind` được đánh dấu optional trong POM của thư viện, consumer không tự nhận Jackson. Khi consumer muốn gọi `read(...)` hoặc compile code làm việc với `JsonNode`, nó cần khai báo Jackson trực tiếp để compiler tìm được kiểu `JsonNode`.

Điều này tạo ra một hợp đồng quan trọng: **nếu kiểu của dependency optional xuất hiện trong chữ ký API công khai, consumer sử dụng API đó phải cung cấp dependency tương ứng**.

Một thiết kế khác là giữ kiểu của thư viện optional bên trong implementation và không để nó xuất hiện trong public API:

```java
package com.example.reporting;

public interface ReportExporter {
    byte[] export(String reportContent);
}
```

Phần implementation có thể dùng một thư viện JSON hoặc cloud SDK, nhưng public API không bắt consumer phải compile với các kiểu đó. Tuy vậy, nếu implementation thực sự cần thư viện ở runtime khi tính năng được gọi, thư viện phải có mặt trên runtime classpath lúc đó. Việc dependency không truyền bắc cầu không tự giải quyết vấn đề runtime.

Với thư viện có API công khai, nên cân nhắc:

- Dùng kiểu của chính thư viện cho public API khi có thể.
- Giữ adapter và tích hợp tùy chọn trong package/module riêng.
- Không để kiểu của dependency tùy chọn rò rỉ vào API chính nếu consumer không cần biết về nó.
- Tài liệu hóa dependency bổ sung mà consumer phải khai báo khi bật tính năng.

## 5. Gradle: hiểu các configuration trước khi gọi một dependency là tùy chọn

Gradle phân loại dependency thông qua configurations. Java plugin cung cấp các configuration như `implementation`, `compileOnly`, `runtimeOnly`, `testImplementation` và các configuration liên quan. Java Library plugin bổ sung `api`, `compileOnlyApi` để biểu diễn rõ dependency của public API.

Các configuration không phải những biến thể khác nhau của một cờ optional. Mỗi configuration xác định dependency tham gia vào classpath nào và được công bố ra sao.

| Configuration | Compile classpath của project hiện tại | Runtime classpath của project hiện tại | Khả năng xuất hiện ở consumer |
|---|---|---|---|
| `api` (Java Library plugin) | Có | Có | Có trên compile và runtime classpath phù hợp của consumer |
| `implementation` | Có | Có | Có ở runtime consumer; không được lộ vào compile classpath consumer như API dependency |
| `compileOnly` | Có | Không | Không được truyền như runtime dependency của consumer |
| `compileOnlyApi` (Java Library plugin) | Có | Không | Có trên compile classpath consumer, không phải runtime dependency |
| `runtimeOnly` | Không | Có | Có trên runtime classpath consumer |
| `testImplementation` | Có trong test compile | Có trong test runtime | Chỉ thuộc test source set của project hiện tại |

Chi tiết publication phụ thuộc plugin và metadata được tạo. Bảng trên mô tả mô hình Java/Java Library phổ biến.

### 5.1. `implementation` không phải optional

Trong thư viện dùng Java Library plugin:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
```

`implementation` có nghĩa dependency cần cho implementation của project. Consumer không cần dependency này trên compile classpath chỉ để biên dịch với public API của thư viện, nhưng dependency vẫn cần ở runtime nếu thư viện sử dụng nó. Khi publish, dependency implementation thông thường được thể hiện để consumer nhận ở runtime.

Do đó, `implementation` giúp che dependency khỏi compile API của consumer; nó không có nghĩa dependency không được truyền tới consumer.

### 5.2. `compileOnly` cũng không tương đương Maven optional

Ví dụ:

```groovy
dependencies {
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}
```

`compileOnly` cung cấp dependency cho compile của project hiện tại nhưng không đưa nó vào runtime classpath thông thường của project. Nó phù hợp với API do container cung cấp hoặc dependency chỉ cần để compile.

`compileOnly` không phải cờ “consumer có thể chọn”. Nếu consumer cần dependency ở runtime, consumer phải tự cung cấp. Nếu dependency xuất hiện trong public API và consumer cần compile với kiểu đó, `compileOnlyApi` có thể phù hợp hơn trong Java Library plugin.

## 6. Gradle: cách biểu diễn tính năng tùy chọn

Nếu thư viện có một tính năng bổ sung thực sự, Gradle Java Library plugin có thể dùng **feature variants**. Feature variant cho phép thư viện công bố một phần capability riêng cùng dependency của nó. Consumer có thể chọn capability đó khi cần tính năng.

Ví dụ thư viện có chức năng hỗ trợ JSON qua Gson:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0.0'

java {
    registerFeature('gsonSupport') {
        usingSourceSet(sourceSets.create('gsonSupport'))
        capability('com.example', 'reporting-library-gson-support', '1.0.0')
    }
}

dependencies {
    gsonSupportImplementation 'com.google.code.gson:gson:2.11.0'
}

publishing {
    publications {
        create('mavenJava', MavenPublication) {
            from components.java
        }
    }
}
```

Feature `gsonSupport` tạo source set và các configuration liên quan như `gsonSupportImplementation`. Dependency Gson được gắn với feature đó thay vì mặc nhiên là dependency implementation của main variant.

Consumer dùng Gradle có thể yêu cầu capability:

```groovy
dependencies {
    implementation('com.example:reporting-library:1.0.0') {
        capabilities {
            requireCapability('com.example:reporting-library-gson-support')
        }
    }
}
```

Khi publish, Gradle Module Metadata có thể mô tả feature variant và capability để Gradle consumer lựa chọn. POM Maven truyền thống không biểu diễn đầy đủ mô hình variant/capability này; consumer Maven thường cần khai báo dependency bổ sung theo tài liệu của thư viện.

Tên capability trong ví dụ được khai báo tường minh bằng `capability(...)`, giúp consumer có một định danh ổn định để yêu cầu. Version capability cần được đồng bộ với version publication hoặc chính sách version của dự án.

### 6.1. Feature variant và source set

Feature variant có thể có source set riêng. Ví dụ:

```text
src/
├── main/java/                 # API và implementation cốt lõi
└── gsonSupport/java/          # Adapter dùng Gson
```

Phần code trong `gsonSupport` có thể chứa implementation phụ thuộc Gson. Consumer chỉ yêu cầu feature khi muốn sử dụng adapter đó.

Feature variants phù hợp khi thư viện có một chức năng bổ sung có thể nhận diện rõ. Nếu chỉ cần một dependency compile-only hoặc runtime-only đơn giản, không nhất thiết phải tạo feature variant.

### 6.2. Consumer không yêu cầu feature

Nếu consumer chỉ khai báo dependency chính mà không yêu cầu capability `gson-support`, Gradle sẽ chọn main variant theo thuộc tính phù hợp và không tự chọn feature variant như một dependency bắt buộc. Điều này giúp consumer không cần tải Gson nếu họ không dùng tính năng đó.

Nếu consumer yêu cầu feature nhưng version/capability không có trong publication, Gradle có thể báo lỗi không tìm được variant phù hợp. Cần kiểm tra metadata được publish và capability mà consumer yêu cầu.

## 7. Runtime optional: xử lý khi dependency không có mặt

Một thư viện có thể thiết kế tích hợp optional bằng reflection hoặc cơ chế provider để chỉ nạp thành phần phụ khi tính năng được sử dụng. Nhưng cần hiểu giới hạn của cách này.

Ví dụ, code cốt lõi không tham chiếu trực tiếp kiểu của thư viện optional trong public API:

```java
public final class OptionalJsonSupport {
    public boolean isAvailable() {
        try {
            Class.forName("com.google.gson.Gson");
            return true;
        } catch (ClassNotFoundException ex) {
            return false;
        }
    }
}
```

Đoạn code trên chỉ kiểm tra khả năng nạp class `Gson` bằng class loader của lớp gọi. Nó không kiểm tra rằng toàn bộ dependency tree của Gson đã đầy đủ hoặc tính năng có thể chạy thành công.

Khi thực sự sử dụng thư viện optional, cần xử lý trường hợp dependency thiếu bằng thông báo rõ ràng:

```java
public final class JsonExporter {
    public byte[] export(String value) {
        try {
            Class<?> gsonType = Class.forName("com.google.gson.Gson");
            Object gson = gsonType.getConstructor().newInstance();
            Object json = gsonType.getMethod("toJson", Object.class)
                .invoke(gson, value);
            return json.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
        } catch (ClassNotFoundException ex) {
            throw new IllegalStateException(
                "JSON support is not available. Add Gson to the runtime classpath.",
                ex
            );
        } catch (ReflectiveOperationException ex) {
            throw new IllegalStateException("Cannot initialize JSON support", ex);
        }
    }
}
```

Ví dụ này minh họa reflection và cách báo lỗi khi thiếu thư viện. Trong ứng dụng thật, nên dùng adapter được kiểm thử, xử lý đúng ngoại lệ và cân nhắc `ServiceLoader` hoặc module integration thay vì phản chiếu trực tiếp ở nhiều vị trí.

Không nên dùng reflection chỉ để che một dependency bắt buộc. Nếu mọi đường chạy đều cần Gson, hãy khai báo nó như dependency bắt buộc. Optional chỉ phù hợp khi ứng dụng thực sự có thể hoạt động hợp lệ mà không có tính năng đó.

## 8. `ServiceLoader` và kiến trúc plugin

Một cách tổ chức tích hợp tùy chọn là định nghĩa interface trong module cốt lõi và để module adapter cung cấp implementation.

```text
reporting-api
     ^
     |
     +---- reporting-json-adapter
     |          |
     |          +---- JSON library
     |
     +---- reporting-cloud-adapter
                |
                +---- Cloud SDK
```

Ứng dụng chỉ cần `reporting-api` cho chức năng cốt lõi. Nếu muốn xuất JSON, nó thêm `reporting-json-adapter`; nếu muốn lưu cloud, nó thêm adapter tương ứng.

Interface cốt lõi:

```java
public interface ReportWriter {
    String format();

    byte[] write(String report);
}
```

Adapter JSON triển khai interface này và khai báo dependency tới JSON library trong module riêng. Có thể đăng ký implementation qua `META-INF/services` và tìm bằng `ServiceLoader`:

```java
import java.util.ServiceLoader;

ServiceLoader<ReportWriter> writers = ServiceLoader.load(ReportWriter.class);

for (ReportWriter writer : writers) {
    System.out.println("Available format: " + writer.format());
}
```

Nếu không có adapter trên runtime classpath, service tương ứng không xuất hiện trong kết quả. Core module vẫn có thể hoạt động với chức năng mặc định.

Thiết kế này thường rõ ràng hơn việc để một thư viện lớn kéo tất cả SDK vào mọi consumer. Mỗi adapter có dependency và vòng đời version riêng; consumer chủ động chọn adapter cần thiết.

## 9. Optional dependency và version conflict

Dependency tùy chọn vẫn có thể gây xung đột khi consumer khai báo nó trực tiếp hoặc một dependency khác cũng yêu cầu cùng thư viện.

Ví dụ:

```text
application
   |
   +---- reporting-library
   |          |
   |          +---- jackson-databind (optional)
   |
   +---- analytics-library
              |
              +---- jackson-databind (required)
```

Vì `analytics-library` yêu cầu Jackson, consumer vẫn có Jackson trong dependency graph dù `reporting-library` đánh dấu nó optional. Optional không phải quy tắc loại bỏ dependency khỏi toàn bộ graph trong mọi trường hợp; nó chỉ ngăn đường truyền bắc cầu từ dependency optional của thư viện đó.

Nếu consumer khai báo một version khác, Maven/Gradle sẽ áp dụng cơ chế resolution tương ứng. Điều này có thể dẫn tới:

- Một version được chọn thay cho version mà thư viện đã kiểm thử.
- `NoSuchMethodError` hoặc `NoClassDefFoundError` nếu runtime classpath không tương thích.
- Hành vi khác nhau giữa local và production nếu dependency resolution không được kiểm soát.

Thư viện nên công bố version range/constraint hoặc dependency management phù hợp với hệ sinh thái, đồng thời kiểm thử với những version được hỗ trợ. Consumer cần xem dependency tree khi xảy ra xung đột.

Với Maven:

```bash
mvn dependency:tree
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Các lệnh này giúp xác định dependency nào kéo thư viện vào và version nào được chọn.

## 10. Optional dependency và public API compatibility

Một thư viện nên cân nhắc dependency optional từ góc độ consumer API, không chỉ từ góc độ build.

Ví dụ, nếu public method trả về `JsonNode`, consumer muốn compile code gọi method đó phải có Jackson trên compile classpath. Nếu dependency được đánh dấu optional, consumer phải tự thêm dependency. Điều này cần được ghi rõ trong tài liệu.

Nếu thư viện thay đổi một dependency từ required thành optional, một số consumer có thể bị lỗi compile hoặc runtime nếu họ vô tình dựa vào việc dependency bắc cầu trước đây luôn có mặt. Đây là thay đổi có thể ảnh hưởng tương thích dù API của thư viện không đổi.

Ngược lại, thay dependency optional thành required có thể làm dependency graph của consumer tăng lên, có thể gây xung đột version hoặc yêu cầu tuân thủ giấy phép/bảo mật mới. Vì vậy, thay đổi tính optional nên được xem xét như thay đổi hợp đồng phân phối.

Khi phát hành version mới, cần xem xét:

- Public API có tham chiếu kiểu của dependency đó không?
- Consumer hiện tại có thể đang dựa vào dependency bắc cầu không?
- Tính năng có thực sự hoạt động khi thiếu dependency không?
- Runtime có nạp lớp optional chỉ khi cần không?
- Tài liệu có nêu dependency consumer cần khai báo khi bật tính năng không?
- Version mới có làm thay đổi dependency graph hoặc variant selection không?

## 11. Optional dependency trong module JPMS

Java Platform Module System (JPMS) có directive `requires static` để biểu diễn một module cần thiết ở compile time nhưng không bắt buộc phải có mặt ở runtime theo cùng cách với `requires` thông thường.

Ví dụ trong `module-info.java`:

```java
module com.example.reporting {
    requires java.logging;
    requires static com.fasterxml.jackson.databind;
}
```

`requires static` cho phép module được biên dịch khi dependency có mặt trong module path, nhưng module đó không bắt buộc phải được resolve ở runtime chỉ vì directive này. Nếu code thực sự sử dụng class của module đó khi chạy, module vẫn cần có mặt và được resolve theo cấu hình runtime tương ứng.

Directive này thuộc hệ thống module của Java, không phải thay thế trực tiếp cho Maven `<optional>true</optional>` hoặc Gradle feature variants. Maven/Gradle vẫn quản lý dependency resolution và publication metadata riêng.

## 12. Khi nào nên dùng dependency optional?

Optional phù hợp khi:

- Thư viện có tích hợp phụ trợ mà chỉ một nhóm consumer cần.
- Một adapter hoặc plugin có thể được cài thêm khi ứng dụng bật tính năng.
- Dependency chỉ cần cho một đường chạy tùy chọn và core vẫn hoạt động khi thiếu nó.
- Muốn tránh truyền tự động một dependency lớn hoặc có yêu cầu riêng sang mọi consumer.
- API và tài liệu đã mô tả rõ consumer phải khai báo dependency bổ sung khi sử dụng tính năng.

Không nên dùng optional khi:

- Mọi đường chạy chính đều cần dependency đó.
- Public API bắt buộc dùng kiểu của dependency và không có hướng dẫn consumer rõ ràng.
- Chỉ muốn che dependency khỏi compile classpath nhưng vẫn cần nó ở runtime; khi đó phải chọn configuration đúng như `implementation`, `compileOnly` hoặc `runtimeOnly` tùy trường hợp.
- Dùng optional để tránh khai báo dependency graph chính xác.
- Tính năng không thể hoạt động an toàn khi thiếu thư viện nhưng code không kiểm tra hoặc báo lỗi rõ ràng.

## 13. Hướng dẫn cho consumer sử dụng thư viện có optional feature

Khi tích hợp một thư viện có dependency tùy chọn, consumer nên:

1. Đọc tài liệu để biết tính năng nào cần artifact bổ sung.
2. Xác định dependency cần cho compile hay runtime.
3. Khai báo dependency trực tiếp trong project nếu cần sử dụng tính năng.
4. Kiểm tra version tương thích với thư viện chính.
5. Xem dependency tree để phát hiện version conflict hoặc dependency được kéo vào từ module khác.
6. Kiểm thử cả trường hợp có và không có optional dependency nếu ứng dụng hỗ trợ cả hai.
7. Đảm bảo packaging/deployment đưa dependency cần thiết vào runtime classpath.

Ví dụ consumer Maven bật JSON support:

```xml
<dependencies>
  <dependency>
    <groupId>com.example</groupId>
    <artifactId>reporting-library</artifactId>
    <version>1.0.0</version>
  </dependency>
  <dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.17.2</version>
  </dependency>
</dependencies>
```

Ví dụ consumer Gradle dùng feature variant đã publish:

```groovy
dependencies {
    implementation('com.example:reporting-library:1.0.0') {
        capabilities {
            requireCapability('com.example:reporting-library-gson-support')
        }
    }
}
```

Consumer cần xác nhận capability và metadata có trong publication. Nếu sử dụng Maven hoặc công cụ không hiểu Gradle Module Metadata, cần khai báo dependency phụ trợ theo hướng dẫn của thư viện.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Project thư viện compile được nhưng consumer báo `package ... does not exist` | Dependency optional không được truyền xuống consumer | Consumer khai báo dependency trực tiếp nếu sử dụng API/tính năng đó |
| Ứng dụng compile được nhưng runtime báo `ClassNotFoundException` | Optional dependency thiếu trên runtime classpath | Thêm dependency runtime hoặc adapter tương ứng |
| `NoClassDefFoundError` khi gọi tính năng phụ | Code tham chiếu class optional nhưng runtime không có class hoặc class không nạp được | Kiểm tra dependency tree, classpath và cách khởi tạo tính năng |
| Dependency vẫn xuất hiện dù thư viện đánh dấu optional | Module khác khai báo cùng dependency như required hoặc consumer khai báo trực tiếp | Xem toàn bộ dependency graph và đường truyền dependency |
| `implementation` bị hiểu nhầm là optional | `implementation` chỉ giới hạn compile exposure của API, không loại dependency khỏi runtime consumer | Chọn configuration hoặc feature variant phù hợp |
| `compileOnly` được dùng cho thư viện cần ở runtime | Dependency chỉ có ở compile classpath của project hiện tại | Dùng `implementation`, `runtimeOnly` hoặc feature variant theo yêu cầu |
| Consumer không tìm thấy Gradle feature capability | Feature variant chưa publish hoặc consumer yêu cầu sai capability | Kiểm tra publication metadata và capability name/version |
| Maven consumer không thấy feature variant của Gradle | POM Maven không biểu diễn đầy đủ Gradle variants/capabilities | Khai báo dependency bổ sung theo tài liệu Maven |
| Thay dependency optional làm consumer cũ lỗi | Consumer từng dựa vào dependency bắc cầu trước đó | Xem đây là thay đổi hợp đồng, kiểm tra tương thích và thông báo rõ |
| Version optional dependency xung đột với module khác | Dependency được thêm qua đường khác hoặc consumer chọn version không tương thích | Dùng dependency insight/tree và quản lý version nhất quán |

## 15. Quy trình thiết kế và kiểm tra optional dependency

Khi thêm một dependency tùy chọn vào thư viện, hãy lần theo các bước:

1. **Xác định tính năng sử dụng dependency:** tính năng đó có thực sự tách khỏi chức năng cốt lõi không?
2. **Xác định thời điểm cần dependency:** compile, runtime hay cả hai?
3. **Kiểm tra public API:** kiểu của dependency có xuất hiện trong public method, field, generic signature hoặc annotation không?
4. **Chọn cơ chế phù hợp:** Maven `<optional>true</optional>`, Gradle feature variant, hoặc configuration compile/runtime phù hợp.
5. **Thiết kế hành vi khi thiếu dependency:** bỏ qua tính năng, không đăng ký adapter, hay báo lỗi rõ khi người dùng gọi tính năng đó.
6. **Publish và kiểm tra metadata:** xác nhận consumer nhận đúng dependency bắt buộc và không nhận dependency phụ không cần thiết.
7. **Kiểm thử consumer:** tạo một project chỉ dùng core và một project bật optional feature.
8. **Kiểm tra dependency graph:** dùng Maven `dependency:tree` hoặc Gradle `dependencies`/`dependencyInsight`.
9. **Tài liệu hóa:** nêu rõ artifact và version cần thêm để bật từng tính năng.

## 16. Kết luận

Dependency tùy chọn giúp thư viện cung cấp tính năng bổ sung mà không bắt mọi consumer nhận toàn bộ dependency phụ trợ. Trong Maven, `<optional>true</optional>` giữ dependency trong project khai báo nhưng ngăn nó được truyền tự động xuống consumer. Consumer muốn dùng tính năng đó cần khai báo dependency trực tiếp.

Trong Gradle, `api`, `implementation`, `compileOnly`, `compileOnlyApi` và `runtimeOnly` điều khiển classpath/publication theo các mục đích khác nhau; chúng không phải các tên khác nhau của một cờ optional. Với tính năng tùy chọn có ranh giới rõ, feature variants và capabilities có thể công bố phần chức năng riêng để Gradle consumer chủ động yêu cầu.

Khi thiết kế, hãy xét cả compile classpath, runtime classpath, public API, dependency graph, version conflict và metadata publication. Một dependency chỉ nên optional khi chức năng cốt lõi thực sự hoạt động mà không cần nó, và consumer có hướng dẫn rõ ràng để bổ sung dependency khi bật tính năng phụ.
