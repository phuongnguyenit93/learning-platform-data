# Kiểm soát JDK, encoding, annotation processor và phụ thuộc để tái lập bản build Java

> **Ngữ cảnh:** Java Advance – compilation → Tích hợp build. Mục tiêu là khiến cùng một commit, cùng cấu hình và cùng bộ đầu vào tạo ra sản phẩm build có thể kiểm chứng, đồng thời giải thích được mọi sai khác khi đổi máy phát triển hoặc chạy CI.

## 1. “Build tái lập” thực sự có nghĩa gì?

Một bản build **reproducible** khi các bên độc lập có thể dựng lại **đúng cùng các byte** của artifact (ví dụ `.jar`), từ cùng mã nguồn, chỉ dẫn build và môi trường đầu vào được xác định. Một build **repeatable** có thể chạy thành công nhiều lần nhưng chưa chắc cho ra file có cùng SHA-256. Một build **hermetic** cố gắng cô lập đầu vào được phép sử dụng; đây là phương tiện hữu ích để tiến gần đến reproducibility, không tự động bảo đảm kết quả.

Mô hình tư duy:

```text
Artifact = f(
  source + resources,
  JDK/javac + build tool/plugins,
  dependency graph + annotation processors,
  compiler flags + charset + environment,
  generated files + archive metadata
)
```

Nếu một đối số của `f` thay đổi âm thầm thì SHA-256 khác nhau là điều có thể xảy ra. Ví dụ: dùng Java 17 thay Java 21; lấy dependency phiên bản `1.+`; nguồn được lưu theo Windows-1258 nhưng biên dịch theo UTF-8; annotation processor tự chèn thời gian hiện tại; hoặc JAR chứa timestamp ở các ZIP entry.

Cần phân biệt ba mức chất lượng:

1. **Build thành công:** mã biên dịch và test chạy được.
2. **Build nhất quán về chức năng:** chương trình hoạt động giống nhau, nhưng JAR vẫn có thể khác từng byte.
3. **Build tái lập ở mức bit:** cùng một tập đầu vào đã cố định tạo cùng nội dung và metadata của artifact, đối chiếu được bằng hash.

Không nên khẳng định “đã tái lập hoàn toàn” chỉ vì hai lần build liên tiếp trên một máy cho ra cùng hash: đường dẫn, locale, hệ điều hành hoặc cache có thể vẫn là nguồn đầu vào ẩn.

## 2. Chuẩn hóa JDK: kiểm soát trình biên dịch và API đích

### 2.1. Bốn thông số cần phân biệt

| Thông số | Quyết định điều gì? | Rủi ro nếu không khóa |
| --- | --- | --- |
| **JDK chạy build tool** | JVM chạy Maven/Gradle và các plugin | Plugin hoặc logic build chạy khác |
| **JDK dùng `javac`** | Trình biên dịch sinh bytecode | Khác minor/patch/vendor có thể thay đổi kết quả |
| **Ngôn ngữ/API mục tiêu** | Tính năng Java và Java API được phép dùng | Build qua nhưng không chạy trên runtime đích |
| **JDK chạy test/app** | Môi trường xác thực sau biên dịch | Test chỉ qua trên máy lập trình viên |

`-source` giới hạn cú pháp, `-target` giới hạn class-file version, nhưng riêng cặp này **không** ngăn chương trình tham chiếu Java API mới hơn phiên bản đích. Hãy dùng `--release 17` khi phải chạy trên Java 17. `--release` kiểm soát đồng thời mức ngôn ngữ, bytecode và tập API của nền tảng Java được phép biên dịch. Tuy nhiên `--release 17` **không pin bản vá/vender của `javac`**; JDK 17.0.x và JDK 21 biên dịch với `--release 17` chưa chắc tạo byte giống nhau.

Ví dụ độc lập với build tool, dùng JDK 17+:

**`src/Hello.java`**

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Tiếng Việt: cà phê");
    }
}
```

Chạy trong thư mục chứa `src`:

```bash
javac -version
javac -encoding UTF-8 --release 17 -proc:none -d out src/Hello.java
java -cp out Hello
```

Stdout của lệnh `java` (khi source được lưu UTF-8 và console hiển thị Unicode):

```text
Tiếng Việt: cà phê
```

`javac` thường không in gì khi thành công; dòng in từ `javac -version` phụ thuộc bản JDK thực tế. `-proc:none` phù hợp cho chương trình **không cần annotation processor**. Nếu chương trình cần sinh source, phải bật và khai báo đúng processor như phần 4.

### 2.2. Cách pin môi trường thực tế

- Commit **Maven Wrapper** (`mvnw`, `.mvn/wrapper/*`) hoặc **Gradle Wrapper** (`gradlew`, `gradle/wrapper/*`), chỉ định bản Maven/Gradle cụ thể. Với Gradle, nên kiểm tra `distributionSha256Sum` trong `gradle-wrapper.properties`; wrapper quản lý bản build tool, **không tự pin JDK**.
- Cố định JDK theo **major + vendor + patch** trong CI image hoặc toolchain distribution đã kiểm tra hash. Toolchain chỉ nói “Java 17” vẫn có thể chọn nhiều bản 17.0.x; tùy yêu cầu bit-identical, phải chuẩn hóa bản phát hành cụ thể.
- Trong Maven, **Toolchains Plugin** có thể chọn một JDK cho các plugin hỗ trợ, tách khỏi JDK chạy Maven. Với Gradle, khai báo **Java toolchain**. Toolchain giúp tránh phụ thuộc `JAVA_HOME` tùy máy, nhưng vẫn phải quản lý provenance/bản patch của JDK.
- Ghi và kiểm tra `java -version`, `javac -version`, `./mvnw -version` hoặc `./gradlew --version`, cùng hệ điều hành và kiến trúc trên CI. Lưu thông tin này ở build provenance/log, **không nhất thiết nhúng đường dẫn máy hay thời điểm chạy vào JAR**.
- Đảm bảo IDE dùng cùng compiler, annotation processing và target release với CLI; chỉ tin build CI bằng wrapper, không dựa vào việc IDE báo xanh.

Một lỗi thường gặp là cài JDK 21 để chạy Maven, cấu hình `<maven.compiler.release>17</maven.compiler.release>` rồi tưởng rằng đang dùng javac 17. Cấu hình này chỉ buộc **đích API/bytecode 17**; muốn lựa chọn đúng compiler cần toolchain và môi trường được khóa.

## 3. Encoding: cố định cách diễn giải source và resource

**UTF-8** nên là quy ước cho toàn bộ `.java`, `.properties`, template, JSON, YAML và tài nguyên văn bản. Tệp chứa chữ “cà phê” có thể gây lỗi biên dịch, ký tự hỏng trong chuỗi hay khác nội dung artifact nếu compiler/resource-filtering đọc bằng charset mặc định khác.

- Lưu file vật lý bằng UTF-8; cấu hình editor và `.editorconfig`. Tránh đổi charset im lặng khi chạy trên Windows/Linux.
- Đối với `javac` thuần, dùng `-encoding UTF-8`. Trong Maven, dùng `project.build.sourceEncoding` và cấu hình rõ khi plugin đặc thù không kế thừa giá trị. Trong Gradle, đặt `JavaCompile.options.encoding = "UTF-8"`.
- File Java và resource **có đường xử lý khác nhau**. Chỉ cấu hình compiler encoding **không** đảm bảo tài nguyên có filtering được đọc/ghi đúng charset; kiểm tra cấu hình Maven Resources Plugin, cơ chế filtering của Gradle và encoding riêng của những generator.
- Khi Java chạy, dùng overload có `StandardCharsets.UTF_8` cho I/O tự viết thay vì phụ thuộc charset mặc định của hệ thống. Charset mặc định của JDK hiện đại thường là UTF-8 (JEP 400 từ Java 18), nhưng phần build cũ, tool bên thứ ba hoặc cấu hình tùy chỉnh vẫn có thể lệch.
- Chuẩn hóa newline (`LF` nếu repo dùng), thứ tự file và cách sinh tài nguyên khi có công cụ phụ thuộc CRLF/đường dẫn; `.gitattributes` có thể quản lý line ending. Không “thay toàn repo” tùy tiện chỉ để sửa một build.

**Ví dụ `.editorconfig`:**

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
```

`.editorconfig` ảnh hưởng cách editor lưu file; nó **không thay thế** cờ encoding trong compiler hay resource plugin.

## 4. Annotation processors: coi chúng là công cụ build cần kiểm soát

Annotation processor chạy trong giai đoạn biên dịch, có thể sinh file `.java`, metadata hoặc resource. Lombok, MapStruct, AutoValue và nhiều thư viện khác dùng cơ chế này. Chúng ảnh hưởng trực tiếp đến đầu ra và có quyền thực thi mã trong quá trình build.

### 4.1. Nguyên tắc

1. **Khai báo processor riêng biệt**, không để classpath runtime tình cờ quyết định processor nào chạy. Trong Maven 3 + Compiler Plugin 3.x, dùng `annotationProcessorPaths` và, khi cần, danh sách `annotationProcessors`; trong Gradle dùng configuration `annotationProcessor`.
2. **Pin phiên bản processor và các phụ thuộc transitives** như những dependency build khác. Bảo đảm processor tương thích JDK/`javac` được chọn.
3. Nếu **không có processor**, chỉ rõ `-proc:none`. Nếu có, liệt kê processor được phép chạy và kiểm soát options của nó; không bật quét toàn classpath chỉ vì tiện.
4. Nhiều generator có thể tạo banner chứa timestamp, đường dẫn tuyệt đối, thứ tự duyệt file thiếu ổn định, tên người dùng hoặc dữ liệu môi trường. Cấu hình tùy chọn loại bỏ các giá trị không ổn định khi thư viện cung cấp; cần kiểm tra output của `generated-sources`.
5. Phân biệt **generated sources** là đầu ra biên dịch có thể tái tạo và **sources được commit**: không nên trộn file sinh từ hai phiên bản generator vào cùng thư mục mà không dọn sạch.

**Thay đổi quan trọng:** từ **JDK 23**, `javac` mặc định **không còn tự chạy processor chỉ vì tìm thấy trên classpath**. Hãy cấu hình processor rõ ràng để build không “mất” mã được sinh khi nâng JDK. `-proc:full` cho phép xử lý annotation rồi biên dịch, nhưng tự bật mọi processor tìm thấy trên classpath có thể tạo rủi ro bảo mật/tái lập; prefer khai báo processor có chủ đích. `-proc:only` chỉ xử lý annotation, không biên dịch tiếp.

### 4.2. Maven: tách processor path

Đoạn sau dành cho project **đã dùng MapStruct**; đây là một **phần cấu hình compiler plugin**, không phải POM độc lập:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.14.1</version>
  <configuration>
    <release>17</release>
    <annotationProcessorPaths>
      <path>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct-processor</artifactId>
        <version>1.6.3</version>
      </path>
    </annotationProcessorPaths>
    <annotationProcessors>
      <annotationProcessor>org.mapstruct.ap.MappingProcessor</annotationProcessor>
    </annotationProcessors>
    <compilerArgs>
      <arg>-Amapstruct.suppressGeneratorTimestamp=true</arg>
      <arg>-Amapstruct.suppressGeneratorVersionInfoComment=true</arg>
    </compilerArgs>
  </configuration>
</plugin>
```

Thư viện API `org.mapstruct:mapstruct:1.6.3` phải được khai báo riêng trong `<dependencies>` nếu mã sử dụng các annotation MapStruct. Hai tùy chọn `-A...` ngăn việc generator chèn metadata dễ làm output đổi giữa các lần build. Processor ví dụ là một **công cụ biên dịch**, không phải dependency runtime.

### 4.3. Gradle: tách compile và processor dependencies

```kotlin
dependencies {
    implementation("org.mapstruct:mapstruct:1.6.3")
    annotationProcessor("org.mapstruct:mapstruct-processor:1.6.3")
}

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(
        listOf(
            "-processor", "org.mapstruct.ap.MappingProcessor",
            "-Amapstruct.suppressGeneratorTimestamp=true",
            "-Amapstruct.suppressGeneratorVersionInfoComment=true"
        )
    )
}
```

Đây là **đoạn bổ sung** cho `build.gradle.kts` có plugin Java và repositories phù hợp. Khi bật processor, **không** giữ cấu hình `-proc:none` của ví dụ không processor ở phần 6. Trong project đa module, mỗi module cần quản lý processor path riêng.

## 5. Dependency graph: phiên bản trực tiếp và bắc cầu đều là đầu vào

Một dependency được xác định không chỉ bởi `group:artifact:version` mà còn có classifier, packaging, biến thể, repository, thuộc tính metadata, transitives và checksum file thực tế.

### 5.1. Điều cần cố định

- Tránh `SNAPSHOT`, `latest.release`, `+`, version range mở hay phụ thuộc lấy từ branch Git di động trong build phát hành. Hôm nay và tuần sau có thể resolve sang byte khác dù POM/Gradle script không đổi.
- Pin version của **dependencies trực tiếp, transitive**, build plugins và processor. **Maven BOM/dependencyManagement** giúp căn chỉnh phiên bản, nhưng chỉ đặt BOM không đóng băng mọi artifact/plugin hoặc đảm bảo repository không đổi.
- **Gradle dependency locking** ghi phiên bản đã resolve cho từng configuration; commit `gradle.lockfile` (và lockfile khác nếu có). **Dependency verification** bổ sung checksum/signature để phát hiện artifact bị thay byte; khóa phiên bản và kiểm tra checksum là **hai vấn đề khác nhau**.
- Với Maven, pin plugin versions và quy tắc dependency trong POM/parent/BOM, tránh SNAPSHOT; xem `./mvnw dependency:tree` và `./mvnw help:effective-pom`. Repository manager nội bộ, policies “không redeploy release” và checksum giúp chặn artifact bị thay trên cùng GAV; Maven không có Gradle-style dependency lock tích hợp một cách tương đương.
- Chốt thứ tự và nguồn repositories. Tránh `mavenLocal()` hoặc `~/.m2/repository` chứa bản artifact tự cài khác remote trong CI phát hành. Đừng tắt checksum verification khi checksum sai; xác minh nguyên nhân.
- Tách dependency cho compile, runtime, test, processor. Đổi processor transitives cũng có thể đổi source sinh ra dù `implementation` không đổi.

**Gradle Kotlin DSL, minh họa locking:**

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Sau khi cấu hình dependency, chạy qua wrapper trong project:

```bash
./gradlew build --write-locks
./gradlew --write-verification-metadata sha256 help
```

Kiểm tra diff rồi commit lockfile và `gradle/verification-metadata.xml`. Lệnh sinh metadata kiểm tra checksum có thể tải/resolve những artifact liên quan tác vụ được chạy; metadata cần bao phủ **đủ mọi configuration** dùng ở CI và phải được review trước khi commit. Không chạy flag ghi lock trong build CI thường xuyên: CI cần **tiêu thụ lock đã commit**, và báo lỗi nếu lệch.

### 5.2. Build tool và plugin cũng là dependencies

Các yếu tố như Maven Compiler/Resources/JAR Plugin, Gradle Java plugin, plugin shading, Kotlin/Groovy compiler, codegen, native library hoặc Docker image base đều tác động đến output. Lock phiên bản **wrapper + plugins + toolchains + external binaries** cùng với dependency graph. Pin bằng tag di động như `latest` vẫn để lộ đầu vào biến động.

## 6. Ví dụ cấu hình Maven cho project Java 17 không có processor

Đây là **POM hoàn chỉnh tối giản** cho Java thuần; giả định `src/main/java/demo/Hello.java` bên dưới. Dùng Maven Wrapper đã commit và JDK được chuẩn hóa ở CI.

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>reproducible-java</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
          <proc>none</proc>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-resources-plugin</artifactId>
        <version>3.3.1</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
      </plugin>
    </plugins>
  </build>
</project>
```

**`src/main/java/demo/Hello.java`**

```java
package demo;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Build Java ổn định");
    }
}
```

Lệnh (Unix/macOS dùng `./mvnw`; Windows dùng `mvnw.cmd`):

```bash
./mvnw -B clean package
java -cp target/classes demo.Hello
```

Stdout chính xác từ lệnh `java`:

```text
Build Java ổn định
```

`project.build.outputTimestamp` cố định thời gian đóng gói cho các Maven plugin hỗ trợ reproducible archive, không khắc phục việc plugin khác nhúng thời gian, đường dẫn hoặc dữ liệu ngẫu nhiên. Phiên bản POM ở trên là **ví dụ có chủ đích cho bài Java không cần annotation processor**; dùng MapStruct/Lombok phải bỏ `<proc>none</proc>` và khai báo processor rõ như phần 4. Nếu build dùng resource filtering, cần rà charset/line ending và giá trị được chèn vào resource.

**Chọn JDK bằng Maven Toolchains Plugin** (đoạn dưới bổ sung vào `<build><plugins>` khi muốn chọn JDK 17 đã cài):

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-toolchains-plugin</artifactId>
  <version>3.3.0</version>
  <executions>
    <execution>
      <goals>
        <goal>select-jdk-toolchain</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <version>[17,18)</version>
  </configuration>
</plugin>
```

`[17,18)` yêu cầu JDK thuộc dòng 17; để chuẩn hóa **cả patch/vendor**, khóa distribution và checksum ở CI hoặc ràng buộc toolchain chặt hơn, xác minh compiler thực tế. Plugin/compiler cần hỗ trợ toolchain; Maven runtime vẫn do môi trường khởi động Maven quyết định.

## 7. Ví dụ Gradle Kotlin DSL cho project Java 17 không có processor

**`build.gradle.kts`** (ví dụ project Java thuần, Gradle có thể chạy bằng JDK tương thích với bản Gradle đã chọn):

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
    options.compilerArgs.add("-proc:none")
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

dependencyLocking {
    lockAllConfigurations()
}
```

- Gradle toolchain chọn compiler Java 17 cho Java tasks, `options.release.set(17)` xác nhận API/bytecode đích; vẫn nên cố định bản patch/vendor ở môi trường CI nếu cần artifact bit-identical.
- Hai thuộc tính archive loại bỏ timestamp không ổn định và thứ tự mục phụ thuộc filesystem. Gradle **9.0+** đã dùng mặc định reproducible archive cho các tác vụ archive chuẩn; khai báo tường minh vẫn hữu ích nếu cần hỗ trợ Gradle cũ.
- `options.compilerArgs.add("-proc:none")` chỉ dành cho bài **không có processor**. Có processor thì bỏ cờ này và khai báo `annotationProcessor` như phần 4.
- `lockAllConfigurations()` là bước cấu hình: phải chạy `--write-locks` khi thay phụ thuộc, commit lockfile và dùng CI kiểm tra việc resolve.

Cấu trúc source, output và lệnh cơ bản:

```text
src/main/java/demo/Hello.java
build.gradle.kts
settings.gradle.kts
gradlew
gradle/wrapper/gradle-wrapper.properties
```

```bash
./gradlew clean build
java -cp build/classes/java/main demo.Hello
```

Dùng cùng class `demo.Hello` ở phần Maven sẽ in `Build Java ổn định`. Trong project có dependencies mới, một `build.gradle.kts` với repo `mavenCentral()` không tự khóa nội dung: cần thêm locking/verification và quản lý repository từ `settings.gradle.kts` nếu tổ chức quy định.

## 8. JAR và bước packaging: những byte dễ thay đổi

Một `.jar` là ZIP archive. Ngay cả khi `.class` trùng nhau, SHA-256 JAR vẫn có thể lệch do entry timestamps, thứ tự entries, quyền file, thứ tự manifest, file sinh tự động, đường dẫn, chữ ký hoặc metadata do plugin ghi vào.

Kiểm tra lần lượt:

- **ZIP entries:** timestamp cố định; thứ tự đóng gói xác định; quyền file/line ending ổn định.
- **Manifest và metadata:** không chứa build time, hostname, username, absolute working directory, random build id hoặc tên nhánh đang thay đổi.
- **Generated resources:** được sắp xếp có thứ tự ổn định trước khi serialize JSON/YAML/service descriptors; không phụ thuộc iteration order của hash collection hay thứ tự file system.
- **Locale/time zone:** không format ngày/number bằng locale mặc định; đặt timezone/locale xác định cho generator nếu có.
- **External tools:** Protobuf/OpenAPI/ANTLR codegen, native compiler, container assembler… cần version/config được pin.
- **Build cache:** cache giúp nhanh nhưng có thể che giấu đầu vào thiếu khai báo; thử cold build và so sánh trên môi trường độc lập. Không dùng “xóa cache thì hết lỗi” làm lời giải thay thế.

Ví dụ lỗi:

```java
// Đoạn minh họa nguồn không tái lập; đừng nhúng giá trị này vào artifact:
String generatedAt = java.time.Instant.now().toString();
```

Nếu một generator đưa `generatedAt` vào file Java/resource thì hai lần build cách nhau một giây có thể ra JAR khác nhau. Cách sửa là bỏ dữ liệu không cần thiết hoặc lấy giá trị **được cố định, kiểm soát và có nguồn gốc** như timestamp của release đã quy ước.

## 9. Quy trình kiểm chứng reproducibility bằng CI

**Bước 1 – Định danh đầu vào.** Kiểm tra sạch working tree, commit ID, wrapper version, JDK distribution/version/hash, dependency lock/checksums, processor versions, env cần thiết và lệnh build.

**Bước 2 – Build sạch hai lần.** Thực hiện ở **hai thư mục/máy hoặc container độc lập**, không mang theo `target`/`build`/output từ lần trước. Khi có thể, dùng clean environment và toolchain/repository mirror được kiểm soát.

**Bước 3 – So sánh artifact theo byte.** Ví dụ trên Linux/macOS:

```bash
sha256sum build-a/target/reproducible-java-1.0.0.jar
sha256sum build-b/target/reproducible-java-1.0.0.jar
cmp build-a/target/reproducible-java-1.0.0.jar build-b/target/reproducible-java-1.0.0.jar
```

Đường dẫn `build-a` và `build-b` đại diện cho hai workspace độc lập sau khi copy artifact về nơi so sánh. Lệnh `cmp` trả exit code **0** nếu byte giống nhau, khác 0 nếu lệch. SHA-256 phải bằng nhau mới đạt tiêu chí bit-for-bit; **không bịa sẵn một giá trị hash** vì hash phụ thuộc toàn bộ đầu vào thực tế. Trên Windows PowerShell, dùng `Get-FileHash -Algorithm SHA256 <path>` cho từng artifact.

**Bước 4 – Điều tra diff nếu hash khác.** So sánh nội dung ZIP entry, timestamp, manifest, bytecode (`javap -v`), generated sources, dependency tree và build log. Công cụ `diffoscope` rất hữu ích để thấy sai khác sâu trong archive. Với Maven, `maven-artifact-plugin` có goal `artifact:compare` để so build thứ hai với bản đã cài, nhưng kiểm tra trên **môi trường khác** vẫn cần thiết để phát hiện environment leak.

**Bước 5 – Giữ bằng chứng.** CI nên lưu log phiên bản JDK/build tool, dependency lock/checksum, command, source revision và hash cuối cùng. Artifact xuất bản nên có provenance/SBOM và quy trình xác thực nguồn cung khi cần; các tài liệu này có thể thay đổi theo từng release, nên lưu **riêng** nếu mục tiêu JAR cố định từng byte.

### Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và sửa |
| --- | --- | --- |
| Build chạy tại IDE, lỗi ở CI | `JAVA_HOME`/compiler, flags hoặc processor khác | In phiên bản JDK, dùng wrapper/toolchain và build CLI |
| `invalid target release` | Compiler quá cũ so với release | Chọn JDK `javac` đủ mới, giữ `--release` phù hợp |
| `cannot find symbol` cho class sinh | Processor không chạy, đặc biệt JDK 23+ | Khai báo processor path/class rõ, kiểm tra generated sources |
| Tiếng Việt bị lỗi trong class/resource | Source hay filtering đọc sai charset | Kiểm tra byte file, `-encoding` và resource encoding UTF-8 |
| Cùng commit nhưng dependency khác | Dynamic version/SNAPSHOT, repo khác hoặc artifact bị thay | Dependency tree, lock, checksum verification và repository policy |
| `.class` giống nhưng JAR hash khác | ZIP timestamp/order, manifest hoặc metadata | So sánh ZIP entry và cấu hình reproducible archive |
| Chỉ khác giữa hai OS | Line endings, đường dẫn, file permissions, locale | Chuẩn hóa input và generator; xác minh trên hai môi trường |
| Chạy build lại thì hết lỗi | Output/caches từ build trước hoặc race | Clean isolated build, dọn generated output đúng cách và rà task inputs |

## 10. Checklist áp dụng cho một repository

- [ ] Source/resources dùng UTF-8, line ending có quy ước; compiler và resource filtering cấu hình charset tường minh.
- [ ] Wrapper được commit, bản Maven/Gradle và plugin đã pin; CI dùng wrapper.
- [ ] Compiler JDK, API target `--release`, vendor/patch và runtime kiểm thử được xác định phù hợp yêu cầu.
- [ ] Annotation processors chạy có chủ đích, version/path/options được pin; không có processor thì tắt rõ ràng.
- [ ] Dependency graph trực tiếp/transitive, repositories và artifact checksums được kiểm soát; không có version động trong release.
- [ ] Generator không chèn clock, random, hostname, user hay absolute path vào sản phẩm phát hành.
- [ ] JAR/archive có entry timestamp và thứ tự ổn định; build từ workspace sạch.
- [ ] CI build độc lập, so hash, lưu provenance và có cách điều tra khi diff.

**Giới hạn quan trọng:** bộ cấu hình minh họa ở trên là nền móng, không phải “chứng chỉ reproducible”. Khả năng tái lập mức bit phải được **kiểm chứng trên artifact thực**, với toàn bộ công cụ sinh mã, plugin, dependency, tài nguyên và môi trường đặc thù của dự án.

## Tài liệu chính thống nên tham khảo

- Apache Maven – Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Apache Maven Compiler Plugin: https://maven.apache.org/plugins/maven-compiler-plugin/
- Apache Maven Toolchains Plugin: https://maven.apache.org/plugins/maven-toolchains-plugin/
- Gradle – Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle – Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle – Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle – Working With Files/Archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Oracle `javac` specification: https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- JDK 23 annotation-processing behavior: https://inside.java/2024/06/18/quality-heads-up/
- Reproducible Builds – JVM: https://reproducible-builds.org/docs/jvm/