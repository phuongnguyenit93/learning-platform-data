# Phân biệt dependency xuất bản tới người dùng với dependency chỉ phục vụ biên dịch

**Chủ đề:** Spring Boot Auto Configuration  
**Ngữ cảnh:** Starter tùy chỉnh  
**Mục tiêu:** Khi phát triển một Java library, auto-configuration module hoặc starter, xác định dependency nào phải đi theo artifact đến ứng dụng tiêu thụ, dependency nào chỉ cần trong quá trình biên dịch/test của module hiện tại, và cách công bố lựa chọn đó đúng trong Maven hoặc Gradle.

## 1. Hai câu hỏi khác nhau khi khai báo dependency

Một dependency có thể được cần bởi mã nguồn của module đang xây dựng, nhưng không nhất thiết phải xuất hiện trên classpath của mọi ứng dụng sử dụng module đó.

Ví dụ thư viện `acme-json-autoconfigure` có adapter dùng Jackson:

```java
public interface JsonCodec {
    String encode(Map<String, ?> value);
}
```

Implementation nội bộ:

```java
final class JacksonJsonCodec implements JsonCodec {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public String encode(Map<String, ?> value) {
        try {
            return this.objectMapper.writeValueAsString(value);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Cannot encode JSON", ex);
        }
    }
}
```

Ứng dụng chỉ dùng contract `JsonCodec`. Nó không cần biên dịch source code của mình với `ObjectMapper` nếu không trực tiếp sử dụng Jackson. Nhưng khi nhánh Jackson thực sự được kích hoạt, Jackson vẫn phải có mặt ở runtime.

Do đó cần phân biệt:

1. **Dependency cần cho chính module:** compiler, test hoặc runtime của module hiện tại cần thư viện đó để xây dựng/chạy code.
2. **Dependency cần công bố cho consumer:** ứng dụng phụ thuộc vào artifact của module có cần thư viện đó trong compile classpath hoặc runtime classpath của chính nó không?

Câu trả lời phụ thuộc vào việc dependency có xuất hiện trong public API hay chỉ được dùng bên trong implementation, và dependency có cần khi chạy hay không.

## 2. Dependency được “xuất bản” nghĩa là gì?

Khi publish một Java library lên Maven repository hoặc một Maven-compatible repository, artifact thường gồm:

- JAR chứa class/resource của chính module.
- POM mô tả tọa độ artifact, dependency, scope, optionality và thông tin build.
- Với Gradle Module Metadata, có thêm file `.module` mô tả các variant và dependency theo từng classpath.

JAR thông thường **không tự chứa mọi dependency**. Công cụ build của ứng dụng đọc metadata đã publish để giải quyết dependency graph, tải những artifact cần thiết và dựng compile/runtime classpath.

Ví dụ:

```text
Ứng dụng consumer
    |
    +---- acme-json-starter
                |
                +---- acme-json-autoconfigure
                |          |
                |          +---- acme-core
                |          +---- Jackson (optional ở module này)
                |
                +---- Jackson (runtime dependency của starter)
```

Ở đây module auto-configuration có thể biên dịch với Jackson nhưng không ép tất cả consumer trực tiếp của module đó phải nhận Jackson. Starter dành cho tính năng JSON chủ động thêm Jackson vào runtime graph của ứng dụng.

**Published dependency không đồng nghĩa dependency được nhúng vào JAR.** Đây là hai cơ chế khác nhau:

- Dependency metadata điều khiển việc công cụ build tải thư viện vào classpath.
- Shaded/uber JAR hoặc Spring Boot executable JAR đóng gói dependency theo cách riêng để phân phối/chạy.

## 3. Chọn scope trong Maven

Maven có các scope thường gặp: `compile`, `provided`, `runtime`, `test`, `system` và `import`. Scope quyết định dependency xuất hiện trong classpath nào và cách truyền tiếp qua dependency graph.

| Scope | Compile classpath của module | Runtime classpath của module | Test classpath | Truyền tới consumer |
| --- | --- | --- | --- | --- |
| `compile` (mặc định) | Có | Có | Có | Có |
| `provided` | Có | Không | Có | Không |
| `runtime` | Không | Có | Có | Có, ở runtime |
| `test` | Không | Không | Có | Không |
| `system` | Có | Có | Có | Không theo cơ chế repository thông thường; cần đường dẫn local |
| `import` | Không phải dependency classpath thông thường | Không | Không | Chỉ dùng để nhập dependency management từ BOM trong `dependencyManagement` |

`system` hiếm khi là lựa chọn phù hợp trong dự án hiện đại vì phụ thuộc đường dẫn JAR trên máy cụ thể. Nên dùng repository và dependency thông thường.

### 3.1. `compile`: dependency công khai theo mặc định

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-core</artifactId>
    <version>1.0.0</version>
</dependency>
```

Không khai báo scope nghĩa là `compile`. Module hiện tại dùng dependency khi biên dịch và chạy; consumer cũng nhận nó theo dependency graph.

Dùng khi:

- Public API của library có type thuộc dependency.
- Consumer cần compile với type đó.
- Dependency là một phần bắt buộc để sử dụng artifact.
- Thư viện thực sự cần dependency ở runtime và muốn nó được truyền tiếp.

Đừng để một dependency chỉ dùng nội bộ trở thành compile dependency công khai nếu không cần thiết; nó làm tăng classpath và coupling của mọi consumer.

### 3.2. `runtime`: cần chạy nhưng không cần để biên dịch source của module

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

Một JDBC driver thường là ví dụ phù hợp: mã ứng dụng có thể chỉ dùng `DataSource`/JDBC API và không import class cụ thể của driver, nhưng driver phải có mặt khi kết nối database.

Consumer nhận dependency này trong runtime classpath nhưng không nhận nó trong compile classpath chỉ vì dependency runtime được truyền qua.

Nếu source code của module trực tiếp import `org.postgresql.Driver`, scope `runtime` sẽ không đủ để biên dịch source đó; khi ấy cần xem lại thiết kế hoặc scope. Không chọn scope chỉ theo tên gọi “driver”, hãy chọn theo classpath thực tế cần thiết.

### 3.3. `provided`: module cần compile/test, runtime do môi trường cung cấp

```xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
```

`provided` nói rằng dependency cần trong lúc compile/test nhưng dự kiến được container hoặc nền tảng cung cấp khi chạy. Maven không truyền dependency này như một dependency thông thường tới consumer.

Ví dụ thường gặp là Servlet API khi ứng dụng được triển khai trong servlet container đã cung cấp API đó.

**Không dùng `provided` chỉ để “giảm dependency”** nếu runtime thực tế không có thư viện. Nếu consumer chạy standalone và không có container cung cấp API, có thể gặp `ClassNotFoundException`/`NoClassDefFoundError`.

### 3.4. `test`: chỉ phục vụ test của module

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

JUnit, Mockito, Testcontainers hoặc fixture chỉ dùng trong `src/test` nên ở `test`. Chúng không nên trở thành dependency runtime của ứng dụng chỉ vì thư viện có viết unit test.

### 3.5. `optional=true`: không truyền dependency tiếp, nhưng vẫn dùng trong module hiện tại

Ví dụ module auto-configuration cần Jackson để compile và khi nhánh Jackson chạy:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <optional>true</optional>
</dependency>
```

Nếu không khai báo scope, scope vẫn là `compile`. Trong chính module `acme-json-autoconfigure`, Jackson có mặt ở compile, runtime và test classpath theo scope đó.

Khác biệt nằm ở consumer: một dự án chỉ phụ thuộc vào `acme-json-autoconfigure` **không tự động nhận** Jackson như dependency transitive. Nếu consumer muốn bật adapter Jackson, nó phải tự thêm Jackson hoặc phụ thuộc một starter đã chủ động cung cấp nó.

`optional=true` không có nghĩa:

- Thư viện không cần trong runtime của module hiện tại.
- Maven không tải dependency khi build module hiện tại.
- Dependency bị xóa khỏi JAR/metadata của module hiện tại.
- Dependency tự động được nạp nếu classpath thiếu.
- Dependency có thể bị tham chiếu an toàn ở mọi chữ ký class bất kể condition.

Đây là khác biệt quan trọng nhất: **optional điều khiển tính truyền tiếp; scope điều khiển classpath của module.**

### 3.6. `dependencyManagement` không thêm dependency vào classpath

Một BOM thường được import như sau:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

BOM quản lý version/scope/exclusions cho dependency được khai báo ở nơi khác. Chỉ đặt một artifact trong `dependencyManagement` **không** làm artifact đó được tải hoặc thêm vào classpath. Vẫn phải khai báo nó trong `<dependencies>` nếu module thực sự cần.

## 4. Chọn configuration trong Gradle `java-library`

Gradle phân biệt dependency dành cho API công khai và dependency chỉ dành cho implementation. Với một Java library, nên dùng plugin `java-library` thay vì chỉ nhìn mọi dependency như một danh sách chung.

| Configuration | Module hiện tại | Consumer compile classpath | Consumer runtime classpath | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `api` | Compile + runtime | Có | Có | Dependency cần cho API và được công bố |
| `implementation` | Compile + runtime | Không | Có | Dependency nội bộ, vẫn cần khi consumer chạy |
| `compileOnly` | Compile, không runtime | Không | Không | Chỉ cần biên dịch module hiện tại |
| `compileOnlyApi` | Compile, không runtime | Có | Không | Consumer cần type khi compile, runtime được cung cấp ở nơi khác |
| `runtimeOnly` | Runtime, không compile | Không | Có | Dependency chỉ cần khi chạy |
| `testImplementation` | Test compile/runtime | Không | Không | Dependency chỉ cho test |
| `testRuntimeOnly` | Test runtime | Không | Không | Dependency chỉ cho chạy test |
| `annotationProcessor` | Compile/code generation | Không | Không | Processor dùng trong build, không phải dependency runtime của consumer |

Các configuration test được tách riêng; bảng tập trung vào ý nghĩa xuất bản. Dependency `implementation` không được đưa vào compile classpath của consumer, nhưng vẫn được truyền ở runtime để library hoạt động. Đây là lý do `implementation` phù hợp cho phần lớn dependency nội bộ.

### 4.1. `api`: type của dependency xuất hiện trong public API

```kotlin
plugins {
    `java-library`
}

dependencies {
    api("com.acme:acme-core:1.0.0")
}
```

Dùng `api` khi consumer cần dependency trên compile classpath để biên dịch với public surface của library.

Ví dụ public method trả về type `com.acme.core.Result`, public constructor nhận `com.acme.core.Request`, hoặc lớp công khai kế thừa một superclass từ dependency. Consumer cần nhìn thấy những type đó khi compile.

`api` cũng có runtime dependency. Nếu dependency không cần ở runtime (ví dụ đã được cung cấp hoặc shaded theo một hợp đồng rõ ràng), hãy xem xét `compileOnlyApi`.

### 4.2. `implementation`: compile và runtime của module, chỉ runtime của consumer

```kotlin
dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}
```

Dùng khi mã nguồn module cần Jackson nhưng public API không phơi bày `ObjectMapper` hoặc type Jackson cho consumer. Dependency vẫn được cung cấp ở runtime của ứng dụng để implementation hoạt động, nhưng không làm compile classpath của consumer phụ thuộc trực tiếp vào Jackson.

Đây là lựa chọn phù hợp cho dependency nội bộ bắt buộc của library, không phải dependency “chỉ compile”.

### 4.3. `compileOnly`: chỉ có ở compile classpath của module

```kotlin
dependencies {
    compileOnly("org.projectlombok:lombok:1.18.36")
    annotationProcessor("org.projectlombok:lombok:1.18.36")
}
```

`compileOnly` phù hợp khi dependency chỉ cần cho compiler và không được đưa vào runtime hoặc publication thông thường. Lombok thường còn được khai báo trong `annotationProcessor` để chạy annotation processor.

Với thư viện mà code runtime thật sự gọi một class thuộc dependency, **không** đặt dependency duy nhất ở `compileOnly` trừ khi runtime đã được bảo đảm cung cấp class đó (ví dụ nền tảng/container hoặc dependency được đóng gói/shaded riêng). Nếu không, consumer có thể compile thành công nhưng lỗi khi chạy.

### 4.4. `compileOnlyApi`: type cần cho consumer compile nhưng runtime do nơi khác cung cấp

```kotlin
dependencies {
    compileOnlyApi("jakarta.servlet:jakarta.servlet-api:6.1.0")
}
```

Dùng khi type của dependency xuất hiện trong public API nên consumer cần nó để compile, nhưng dependency không được library cung cấp ở runtime vì một nền tảng khác chịu trách nhiệm.

Đây là trường hợp hẹp. Nếu consumer cần thư viện cả khi chạy, dùng `api` thay vì `compileOnlyApi`.

### 4.5. `runtimeOnly`: consumer cần ở runtime nhưng không cần compile

```kotlin
dependencies {
    runtimeOnly("org.postgresql:postgresql:42.7.5")
}
```

Phù hợp với JDBC driver khi code chỉ dùng JDBC API chuẩn và không trực tiếp import class của driver. Gradle đưa dependency vào runtime classpath của module và công bố cho consumer ở runtime variant.

### 4.6. `annotationProcessor` và dependency cho code generation

```kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor:3.3.13")
}
```

Annotation processor tham gia build để sinh metadata/code. Nó không phải dependency mà ứng dụng cần để chạy bean hoặc service của thư viện. Đặt processor ở configuration riêng tránh vô tình đưa công cụ build vào runtime graph.

## 5. Maven `optional` không tương đương Gradle `compileOnly`

Hai cơ chế này thường bị nhầm vì đều có thể khiến consumer không nhận dependency theo cách thông thường. Nhưng chúng trả lời hai câu hỏi khác nhau:

| Khai báo | Module hiện tại compile? | Module hiện tại runtime? | Consumer tự nhận dependency? |
| --- | --- | --- | --- |
| Maven `compile` | Có | Có | Có, compile/runtime |
| Maven `compile` + `optional=true` | Có | Có | Không tự nhận |
| Maven `provided` | Có | Không | Không |
| Gradle `implementation` | Có | Có | Runtime, không compile |
| Gradle `compileOnly` | Có | Không | Không |
| Gradle `api` | Có | Có | Compile và runtime |
| Gradle `runtimeOnly` | Không | Có | Runtime |

Ví dụ cùng một thư viện Jackson:

- Maven `optional=true` với scope mặc định vẫn có Jackson ở runtime classpath của **module autoconfigure**. Chỉ consumer không tự nhận nó.
- Gradle `compileOnly` có Jackson trong compile classpath của **module autoconfigure**, nhưng không có trong runtime classpath của module, trừ khi được thêm riêng (ví dụ `testRuntimeOnly`) hoặc một module starter cung cấp nó.
- Gradle `implementation` có Jackson cả compile và runtime của module, consumer chỉ nhận Jackson ở runtime.
- Gradle `api` có Jackson cả compile và runtime của consumer.

Vì vậy, khi chuyển build từ Maven sang Gradle, không chuyển cơ học `<optional>true</optional>` thành `compileOnly`. Hãy xác định riêng: module có cần dependency lúc chạy không, consumer có cần compile với type đó không, và ai chịu trách nhiệm cung cấp dependency runtime.

## 6. Thiết kế module cho custom starter có adapter tùy chọn

Một cấu trúc dễ hiểu:

```text
acme/
├── acme-core/
│   └── Public API (không phụ thuộc Jackson)
├── acme-json-autoconfigure/
│   └── Auto-configuration và adapter Jackson tùy chọn
├── acme-json-starter/
│   └── Starter chủ động cung cấp adapter JSON mặc định
└── consumer-app/
    └── Ứng dụng dùng starter
```

### 6.1. Module `acme-core`

Public API không tham chiếu Jackson:

```java
package com.acme.core;

import java.util.Map;

public interface JsonCodec {
    String encode(Map<String, ?> value);
}
```

Vì consumer có thể compile với `JsonCodec` mà không cần Jackson, core không cần công bố dependency Jackson.

### 6.2. Module `acme-json-autoconfigure` trong Maven

POM rút gọn:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-core</artifactId>
        <version>${project.version}</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <optional>true</optional>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Ở module này, Jackson được dùng để biên dịch implementation và có thể chạy test/nhánh adapter. Nhưng ứng dụng chỉ phụ thuộc `acme-json-autoconfigure` sẽ không tự nhận Jackson. Nếu muốn dùng adapter Jackson, ứng dụng phải khai báo dependency hoặc dùng một starter có trách nhiệm cung cấp nó.

Nếu `JsonCodec` là public API của autoconfigure module và nó phụ thuộc `acme-core`, dependency `acme-core` phải được công bố phù hợp để consumer compile với `JsonCodec`.

### 6.3. Module `acme-json-starter` trong Maven

Starter chuyên cho tính năng JSON có thể công bố Jackson một cách chủ động:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-json-autoconfigure</artifactId>
        <version>${project.version}</version>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Vì starter khai báo Jackson ở scope `runtime` không optional, consumer nhận Jackson trong runtime classpath. Consumer không nhận Jackson chỉ vì starter có dependency runtime trong compile classpath; nếu ứng dụng muốn viết code import `ObjectMapper`, hãy khai báo Jackson trực tiếp ở compile scope trong ứng dụng.

Trong một sản phẩm thực tế, starter có thể chọn compile scope nếu muốn API sử dụng Jackson được công bố cho consumer compile. Hãy chọn theo hợp đồng của starter, không chọn chỉ vì “thêm dependency cho chắc”.

### 6.4. Module `acme-json-autoconfigure` trong Gradle

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

dependencies {
    api("com.acme:acme-core:1.0.0")
    implementation("org.springframework.boot:spring-boot-autoconfigure:3.3.13")

    compileOnly("com.fasterxml.jackson.core:jackson-databind:2.17.2")
    testRuntimeOnly("com.fasterxml.jackson.core:jackson-databind:2.17.2")

    testImplementation("org.springframework.boot:spring-boot-starter-test:3.3.13")
}
```

Ở đây Jackson là dependency compile-only của module. `testRuntimeOnly` thêm Jackson để test nhánh optional có mặt. Một consumer chỉ dùng autoconfigure module phải tự cung cấp Jackson ở runtime nếu muốn kích hoạt adapter.

Nếu implementation của module cần Jackson ở runtime trong mọi trường hợp khi consumer dùng autoconfigure, và dependency nên được truyền tới consumer runtime nhưng không compile, có thể cân nhắc `implementation` thay vì `compileOnly`. Chọn cấu hình dựa trên mô hình phân phối thực tế của adapter.

### 6.5. Module starter trong Gradle

```kotlin
plugins {
    `java-library`
}

dependencies {
    api(project(":acme-json-autoconfigure"))
    runtimeOnly("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}
```

Starter này đưa auto-configuration vào API/runtime graph của consumer và thêm Jackson vào runtime variant. Nếu starter muốn consumer compile trực tiếp với Jackson, chuyển sang `api` (hoặc khai báo dependency trực tiếp trong consumer theo nhu cầu).

Cùng một library có thể có nhiều starter với lựa chọn dependency khác nhau: starter cơ bản không kéo adapter, `json-starter` kéo Jackson, `xml-starter` kéo XML provider. Cách phân chia này cho người dùng chọn feature rõ ràng và tránh classpath phình to.

## 7. Public API quyết định dependency nào cần công bố

Không thể chọn `api` hay `implementation` chỉ bằng cách nhìn import ở đầu file. Phải xem type dependency có xuất hiện trong **public/protected signatures và contract mà consumer cần compile** hay không.

Ví dụ:

```java
public interface ReportClient {
    com.vendor.api.Report fetch(String id);
}
```

Consumer biên dịch code gọi `fetch` cần nhìn thấy `com.vendor.api.Report`. Dependency chứa type này phải có trên consumer compile classpath.

Với Gradle:

- Dùng `api` nếu consumer cần dependency ở cả compile và runtime.
- Dùng `compileOnlyApi` chỉ khi consumer cần compile với type đó nhưng runtime có nguồn cung cấp riêng.

Với Maven, dependency compile không optional thường được truyền tiếp. Maven không có scope `compileOnly` tương đương tổng quát. Nếu public signature cần type ở runtime, không đánh dấu dependency optional rồi mong mọi consumer tự tìm được thư viện.

Ngược lại:

```java
public interface ReportClient {
    String fetchJson(String id);
}
```

Nếu implementation nội bộ dùng `com.vendor.api.Client` nhưng không lộ type đó trong API, consumer không cần compile với vendor client. Có thể dùng Gradle `implementation`; trong Maven dùng dependency phù hợp với runtime/transitivity và chính sách optional của adapter.

### 7.1. Kế thừa, annotation và generic cũng là API

Dependency không chỉ “lộ” khi xuất hiện trong kiểu trả về. Nó có thể cần thiết khi public class:

- `extends` một superclass của dependency.
- `implements` interface của dependency.
- Có public constructor/field/method parameter hoặc return type dùng dependency.
- Có generic bound hoặc public annotation mà consumer compiler cần xử lý.
- Yêu cầu processor/plugin của dependency để sinh source mà consumer phải biên dịch.

Hãy kiểm tra public surface bằng compiler và test consumer thật. Đừng chỉ tìm chuỗi import.

## 8. Dependency dành riêng cho build và test

Một số dependency chỉ phục vụ quá trình tạo artifact:

| Mục đích | Maven | Gradle |
| --- | --- | --- |
| JUnit/Mockito | `scope=test` | `testImplementation` |
| Test runtime DB/driver | `scope=test` hoặc `runtime` phù hợp test | `testRuntimeOnly` |
| Annotation processor | `maven-compiler-plugin` / `annotationProcessorPaths` | `annotationProcessor` |
| Compile-only API | Không có scope tương đương tổng quát; dùng `provided` nếu runtime do môi trường cấp và hiểu tính không transitive | `compileOnlyApi` |
| Compile-only implementation | Không có scope tương đương trực tiếp; cân nhắc `provided` theo runtime contract | `compileOnly` |
| Dependency chỉ runtime | `runtime` | `runtimeOnly` |

Maven `provided` và Gradle `compileOnly` có nét giống nhau về việc không đưa dependency vào runtime classpath của module, nhưng không nên coi là tương đương tuyệt đối trong mọi trường hợp xuất bản và phân giải transitive. Đọc classpath thực tế của producer và consumer trước khi chuyển build tool.

### 8.1. Annotation processor không phải dependency runtime

Ví dụ Gradle:

```kotlin
dependencies {
    compileOnly("org.projectlombok:lombok:1.18.36")
    annotationProcessor("org.projectlombok:lombok:1.18.36")
}
```

Ví dụ Maven Compiler Plugin có thể khai báo processor trong `annotationProcessorPaths`. Processor chạy trong build, không cần được đưa vào runtime graph của ứng dụng chỉ vì nó đã sinh mã trong lúc compile.

Tương tự, Spring Boot configuration processor sinh configuration metadata cho IDE. Ứng dụng tiêu thụ starter không cần configuration processor ở runtime để đọc `@ConfigurationProperties`.

## 9. Exclusion, optional và dependency management không giống nhau

Ba cơ chế thường bị gộp nhầm:

**Optional** do thư viện upstream công bố: “consumer không bắt buộc phải nhận dependency này; nếu cần, hãy khai báo rõ”.

**Exclusion** do consumer hoặc dependency declaration yêu cầu: “loại dependency transitive cụ thể khỏi nhánh này của dependency graph”.

Ví dụ Maven:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-json-starter</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclusion chỉ loại dependency từ nhánh dependency đó. Một artifact khác trong graph vẫn có thể đưa Jackson trở lại. Nếu starter cần Jackson để nhánh mặc định hoạt động, exclusion có thể làm condition no-match hoặc gây lỗi runtime; chỉ dùng khi biết adapter nào sẽ thay thế.

**Dependency management/BOM** quản lý version và metadata dùng chung, không tự thêm dependency vào classpath. Một project có thể import BOM nhưng vẫn phải khai báo artifact mà nó cần trong `<dependencies>`.

## 10. Phân biệt dependency metadata với fat JAR và Spring Boot executable JAR

Giả sử POM khai báo dependency `runtime`. Maven resolution thêm nó vào runtime classpath của ứng dụng; dependency không nhất thiết được copy vào JAR library thường.

Một JAR library bình thường:

```text
acme-json-autoconfigure.jar
    com/acme/json/JsonCodec.class
    com/acme/json/autoconfigure/JsonAutoConfiguration.class
```

Dependency được tải riêng qua repository theo POM/metadata.

Một Spring Boot executable JAR có thể chứa thư viện dependency lồng bên trong:

```text
application.jar
├── BOOT-INF/classes/
│   └── com/example/Application.class
└── BOOT-INF/lib/
    ├── acme-json-autoconfigure-1.0.0.jar
    ├── jackson-databind-2.17.2.jar
    └── spring-core-....jar
```

Đây là cơ chế đóng gói để chạy ứng dụng. Nó không làm thay đổi ý nghĩa của `api`, `implementation`, `optional` hay `compileOnly` trong lúc giải quyết dependency. Nếu dùng shading/relocation, phải quản lý thêm việc đóng gói class và license/resource; không coi shading là cách thay thế vô hình cho dependency contract.

## 11. Kiểm tra dependency thực tế của producer và consumer

Đừng chỉ đọc POM/build.gradle rồi đoán. Hãy kiểm tra cả hai phía.

### 11.1. Maven

Xem dependency tree của module:

```bash
mvn dependency:tree
```

Lọc một dependency cụ thể:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Xem effective POM:

```bash
mvn help:effective-pom
```

Trong consumer project, chạy `dependency:tree` để xác nhận dependency có xuất hiện và scope hiệu lực có đúng không. So sánh:

- Consumer phụ thuộc trực tiếp vào `acme-json-autoconfigure`.
- Consumer phụ thuộc vào `acme-json-starter`.

Kết quả mong đợi: Jackson không tự truyền từ autoconfigure module nếu dependency đó được đánh dấu optional; starter JSON có thể thêm Jackson ở runtime/compile theo contract của starter.

### 11.2. Gradle

Xem compile classpath:

```bash
./gradlew :acme-json-autoconfigure:dependencies --configuration compileClasspath
```

Xem runtime classpath:

```bash
./gradlew :acme-json-autoconfigure:dependencies --configuration runtimeClasspath
```

Xem consumer runtime:

```bash
./gradlew :consumer-app:dependencies --configuration runtimeClasspath
```

Tìm nguồn đưa dependency vào graph:

```bash
./gradlew :consumer-app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Các lệnh trên giúp phân biệt dependency đến từ `api`, `implementation`, `runtimeOnly`, platform/BOM hay một nhánh transitive khác.

### 11.3. Kiểm tra artifact đã publish

Với Maven, mở POM trong repository hoặc file POM được install vào local repository; xác nhận `scope` và `optional`.

Với Gradle, kiểm tra cả POM và Gradle Module Metadata (`.module`) nếu repository/publishing đã tạo cả hai. Gradle Module Metadata có thể diễn tả các variant compile/runtime của Java Library chi tiết hơn POM. Consumer dùng Maven chủ yếu dựa vào POM; consumer dùng Gradle có thể dùng metadata Gradle khi có sẵn.

Một test trong source module chưa đủ để xác nhận dependency publication. Nên có một consumer sample độc lập phụ thuộc artifact đã publish vào local/staging repository, rồi chạy compile và test với classpath đúng như người dùng thật.

## 12. Ma trận lựa chọn nhanh

| Tình huống | Maven thường dùng | Gradle `java-library` thường dùng |
| --- | --- | --- |
| Dependency xuất hiện trong public API, cần compile + runtime | `compile` (mặc định), không optional | `api` |
| Dependency chỉ nội bộ nhưng cần compile + runtime | `compile` | `implementation` |
| Dependency chỉ cần ở runtime, ví dụ JDBC driver | `runtime` | `runtimeOnly` |
| Dependency cần compile/test, runtime do container cung cấp | `provided` | `compileOnly` hoặc `compileOnlyApi` nếu consumer compile cần type |
| Dependency tùy chọn của một adapter, không tự truyền tới consumer | `optional=true` cùng scope phù hợp | `compileOnly` nếu adapter chỉ cần compile; hoặc thiết kế runtime/starter riêng nếu cần runtime |
| Dependency chỉ cho test | `test` | `testImplementation` / `testRuntimeOnly` |
| Annotation processor | Compiler plugin processor path | `annotationProcessor` |
| Quản lý version tập trung | BOM trong `dependencyManagement` | `platform(...)` / version catalog / constraints |

Bảng này là điểm bắt đầu, không phải chuyển đổi một-một giữa hai build tools. Maven scope và optionality là hai thuộc tính; Gradle configurations mô tả variants/classpaths. Chọn dựa trên public API và runtime contract.

## 13. Lỗi thường gặp

**Lỗi 1 — Đánh dấu dependency Maven optional vì không muốn consumer compile với nó.**  
`optional=true` ngăn truyền tiếp, nhưng dependency vẫn có thể cần trong runtime của chính module. Nếu chỉ cần compile, phải xem runtime contract và cách đóng gói/được cung cấp; Maven không có scope `compileOnly` tương đương tổng quát.

**Lỗi 2 — Dùng Gradle `compileOnly` cho thư viện mà implementation gọi ở runtime.**  
Consumer compile thành công nhưng có thể lỗi `NoClassDefFoundError` khi chạy. Thêm runtime dependency qua starter/consumer hoặc đổi configuration phù hợp.

**Lỗi 3 — Để implementation detail trong public signature rồi khai báo `implementation`.**  
Consumer có thể không compile được vì type cần thiết không có trên compile classpath. Dùng `api` hoặc thiết kế lại API để không lộ implementation type.

**Lỗi 4 — Dùng `api` cho tất cả dependency.**  
Classpath consumer phình to, compile phụ thuộc vào thư viện không cần thiết, tăng coupling và khả năng xung đột version. Ưu tiên `implementation` cho internal dependency trong Gradle.

**Lỗi 5 — Dùng `provided` nhưng không có container cung cấp ở runtime.**  
Ứng dụng khởi động lỗi vì thiếu class. `provided` là một lời hứa về môi trường, không phải cách bỏ dependency một cách miễn phí.

**Lỗi 6 — Cho rằng BOM đã thêm dependency.**  
`dependencyManagement`/platform quản lý version; vẫn phải khai báo dependency thực sự trong project.

**Lỗi 7 — Chỉ kiểm tra dependency tree của module thư viện.**  
Cần kiểm tra consumer sau khi publish, vì optionality, scope và variant quyết định dependency được truyền tiếp thế nào.

**Lỗi 8 — Nghĩ dependency metadata có nghĩa JAR đã chứa thư viện.**  
POM/Gradle metadata chỉ mô tả dependency graph. Fat JAR, shaded JAR và Spring Boot executable JAR là các chiến lược đóng gói riêng.

**Lỗi 9 — Đưa test/annotation processor vào runtime.**  
Tách test configuration và processor path để artifact tiêu thụ không phải nhận tool chỉ dùng lúc build.

**Lỗi 10 — Quên public API kế thừa type bên ngoài.**  
Ngay cả khi không có field hoặc method trả về type đó, superclass/interface/generic bound cũng có thể khiến consumer cần dependency ở compile time.

## 14. Checklist trước khi publish starter/library

1. Liệt kê dependency trực tiếp được source production sử dụng; không dựa vào transitive dependency tình cờ.
2. Đánh dấu type nào xuất hiện trong public/protected API, annotation, superclass, generic và extension point.
3. Xác định dependency cần ở compile, runtime, test hay annotation processing.
4. Với Maven, kiểm tra scope và `optional` riêng biệt; không dùng optional thay cho runtime scope.
5. Với Gradle, phân biệt `api`, `implementation`, `compileOnly`, `compileOnlyApi` và `runtimeOnly`.
6. Với adapter tùy chọn, đảm bảo dependency publication khớp class condition và cấu trúc auto-configuration.
7. Tạo starter riêng nếu cần cung cấp một adapter như lựa chọn mặc định.
8. Kiểm tra POM/Gradle Module Metadata sau publish.
9. Chạy consumer sample độc lập, xem compile/runtime classpath và khởi động với/không có dependency optional.
10. Đảm bảo test libraries và annotation processors không bị xuất bản thành runtime dependencies.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Module Maven dùng Jackson ở cả compile và runtime nội bộ, nhưng consumer chỉ dùng interface không phụ thuộc Jackson. Muốn consumer không tự nhận Jackson thì dùng gì?  
**Đáp án:** Dependency có scope phù hợp cho module và `optional=true`. Trong chính module, Jackson vẫn có trên classpath theo scope; consumer không nhận dependency đó một cách transitive.

**Câu 2.** Maven `optional=true` có đồng nghĩa dependency chỉ ở compile classpath không?  
**Đáp án:** Không. Optional điều khiển truyền tiếp; scope mới điều khiển classpath của module hiện tại.

**Câu 3.** Gradle library có public method trả về `com.vendor.Result` và consumer cần dùng type đó ở compile/runtime. Nên khai báo gì?  
**Đáp án:** `api("com.vendor:library:...")`.

**Câu 4.** Gradle implementation dùng thư viện logging nhưng public API không nhắc tới type của nó. Nên dùng gì?  
**Đáp án:** Thường là `implementation`, vì consumer cần dependency khi chạy nhưng không cần nó trên compile classpath chỉ để biên dịch với API của library.

**Câu 5.** Một JDBC driver không được import trong source nhưng phải có khi kết nối. Scope nào thường phù hợp?  
**Đáp án:** Maven `runtime`, Gradle `runtimeOnly`.

**Câu 6.** Servlet API được container cung cấp khi chạy; module cần compile với API nhưng không muốn đóng gói/truyền nó như runtime dependency. Có thể dùng gì?  
**Đáp án:** Maven `provided`; Gradle `compileOnly` hoặc `compileOnlyApi` tùy type có xuất hiện trong API consumer hay không.

**Câu 7.** Vì sao `compileOnly` không phải cách thay thế máy móc cho Maven `optional=true`?  
**Đáp án:** `compileOnly` loại dependency khỏi runtime classpath của producer; Maven optional không làm vậy, nó chỉ ngăn dependency được truyền tiếp sang consumer.

**Câu 8.** Một artifact xuất hiện trong `dependencyManagement` nhưng không xuất hiện trong dependency tree. Có phải Maven lỗi?  
**Đáp án:** Không. `dependencyManagement` chỉ quản lý version/configuration; project vẫn phải khai báo artifact trong `dependencies`.

**Câu 9.** Vì sao nên test một consumer độc lập sau khi publish?  
**Đáp án:** Vì dependency metadata đã xuất bản, optionality và variant quyết định classpath của consumer; test nội bộ có thể vô tình có đủ dependency nên che lỗi publication.

## 16. Nguyên tắc cần nhớ

- Dependency cần cho producer và dependency cần công bố cho consumer là hai câu hỏi độc lập.
- Maven scope điều khiển classpath; `optional=true` điều khiển dependency có truyền tiếp hay không.
- Maven optional không tương đương Gradle `compileOnly`.
- Gradle `api` dùng cho public API; `implementation` dùng cho nội bộ; `compileOnly` không cung cấp runtime; `runtimeOnly` chỉ dành cho runtime.
- Public signatures, inheritance, annotations và generic types quyết định consumer có cần dependency trên compile classpath không.
- Starter có thể công bố một adapter tùy chọn bằng cách chủ động thêm dependency runtime/compile theo hợp đồng.
- POM và Gradle Module Metadata mô tả dependency graph; chúng không tự nhúng thư viện vào JAR.
- Luôn kiểm tra dependency tree và một consumer sample độc lập trước khi phát hành.

### Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Maven Dependencies](https://maven.apache.org/repositories/dependencies.html)
- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
