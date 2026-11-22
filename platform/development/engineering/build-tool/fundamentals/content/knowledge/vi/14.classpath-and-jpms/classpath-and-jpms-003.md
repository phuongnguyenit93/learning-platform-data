# Vì sao biên dịch thành công nhưng chạy vẫn thiếu thư viện

Một chương trình Java có thể biên dịch thành công nhưng thất bại ngay khi khởi chạy với lỗi như `ClassNotFoundException`, `NoClassDefFoundError` hoặc `NoSuchMethodError`. Điều này thường xảy ra vì **môi trường biên dịch và môi trường chạy không sử dụng cùng tập thư viện**, hoặc artifact được tạo ra không mang theo dependency mà ứng dụng cần.

Compiler chỉ cần tìm thấy những kiểu và API được mã nguồn tham chiếu trong quá trình biên dịch. Khi chạy, JVM phải nạp được tất cả lớp cần thiết theo luồng thực thi thực tế, từ classpath, module path hoặc classloader của container. Hai môi trường có thể khác nhau về đường dẫn, version, scope dependency, cách đóng gói và cơ chế nạp lớp.

Bài này giải thích sự khác nhau giữa compile classpath và runtime classpath, cách Maven/Gradle xây dựng hai tập dependency, vai trò của classpath và Java Platform Module System (JPMS), cùng quy trình tìm nguyên nhân khi build thành công nhưng ứng dụng thiếu thư viện lúc chạy.

## 1. Compile classpath và runtime classpath là hai tập khác nhau

**Compile classpath** là tập thư mục và thư viện mà compiler sử dụng để tìm các lớp, interface, annotation và kiểu dữ liệu được tham chiếu trong mã nguồn.

**Runtime classpath** là tập vị trí mà JVM hoặc classloader dùng để tìm lớp khi ứng dụng thực thi. Nó cần bao gồm những lớp được nạp trong các nhánh thực thi thực tế, kể cả những lớp chỉ được nạp động qua reflection, service provider hoặc cấu hình.

Ví dụ, mã nguồn gọi một thư viện JSON:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

public class Main {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        System.out.println(mapper.writeValueAsString("hello"));
    }
}
```

Nếu `jackson-databind` có trên compile classpath, `javac` có thể tìm thấy `ObjectMapper` và biên dịch lớp `Main`. Nhưng nếu khi chạy lệnh `java` không có JAR Jackson trên runtime classpath, JVM không thể nạp `ObjectMapper` và chương trình thất bại.

```text
Mã nguồn .java
     |
     v
Compile classpath
     |
     v
   javac  -------------------->  Main.class
                                      |
                                      v
                               Runtime classpath
                               / module path
                                      |
                                      v
                                     JVM
                                      |
                          nạp lớp và dependency lúc chạy
```

Biên dịch thành công chỉ chứng minh compiler đã tìm thấy các kiểu cần thiết cho lần biên dịch đó. Nó không chứng minh những thư viện đó có mặt trong artifact phát hành hoặc môi trường triển khai.

### 1.1. Một ví dụ tái hiện bằng lệnh thủ công

Giả sử thư mục dự án có cấu trúc:

```text
demo/
├── lib/
│   └── example-library.jar
├── src/
│   └── Main.java
└── out/
```

Biên dịch với thư viện:

```bash
javac -cp lib/example-library.jar -d out src/Main.java
```

Lệnh này thành công vì compiler tìm thấy lớp trong `example-library.jar`.

Nếu chạy mà quên thư viện:

```bash
java -cp out Main
```

JVM chỉ tìm lớp trong `out` và các vị trí mặc định của Java platform. Nó không tự biết rằng lúc biên dịch ta đã dùng `lib/example-library.jar`.

Chạy đúng:

```bash
# Linux/macOS
java -cp "out:lib/example-library.jar" Main

# Windows
java -cp "out;lib/example-library.jar" Main
```

Classpath separator là dấu hai chấm (`:`) trên Linux/macOS và dấu chấm phẩy (`;`) trên Windows. Nếu có nhiều JAR, cần đưa tất cả dependency runtime cần thiết vào classpath hoặc dùng wildcard phù hợp.

### 1.2. Compiler không nạp mọi lớp mà chương trình sẽ dùng

Compiler kiểm tra các tham chiếu tĩnh trong mã nguồn. Một số lớp chỉ được tìm khi chương trình chạy, chẳng hạn:

- Lớp được nạp qua `Class.forName("com.example.Driver")`.
- Implementation được tìm qua `ServiceLoader`.
- Driver JDBC được phát hiện qua service provider.
- Plugin được nạp từ thư mục plugin hoặc classloader riêng.
- Tên lớp được lấy từ file cấu hình, XML hoặc database.
- Một nhánh code hiếm khi chạy mới tham chiếu đến một lớp tùy chọn.

Vì các tên lớp này có thể chỉ xuất hiện dưới dạng chuỗi hoặc metadata, compiler không nhất thiết phát hiện được việc thiếu chúng. Chương trình có thể chạy qua các luồng thông thường rồi mới lỗi khi người dùng kích hoạt một chức năng cụ thể.

## 2. Những nguyên nhân phổ biến

| Nguyên nhân | Vì sao compile vẫn thành công? | Điều xảy ra lúc chạy |
|---|---|---|
| Thiếu dependency trên runtime classpath | Dependency có trên compile classpath | JVM không tìm thấy lớp cần nạp |
| Dependency scope chỉ dành cho compile | Build tool loại dependency khỏi runtime graph | Ứng dụng thiếu thư viện khi thực thi |
| Plain JAR không chứa dependency | Compiler/build tool đã resolve dependency để compile | Chỉ file JAR ứng dụng được phân phối, thư viện ngoài không đi kèm |
| Launcher dựng classpath không đầy đủ | IDE hoặc build tool dùng classpath đầy đủ | Script, service hoặc lệnh triển khai bỏ sót JAR |
| Dùng `java -jar` sai cách | Compile dùng classpath riêng | `-cp` không bổ sung classpath như khi chạy tên lớp; cần manifest hoặc packaging phù hợp |
| Container cung cấp API nhưng môi trường thực tế không có | Compile dùng API JAR trên máy build | Server thiếu API/implementation hoặc cung cấp version không tương thích |
| Khác biệt classpath và module path | Compile tìm được module/API | JVM không resolve module hoặc module không đọc/export package cần thiết |
| Version runtime không tương thích | Compile dựa trên API của version mới | Lỗi liên kết như `NoSuchMethodError` hoặc `NoSuchFieldError` |
| Dependency bắc cầu không được khai báo/đóng gói đúng | Compile classpath có dependency gián tiếp | Runtime không có dependency cần thiết |
| Khác biệt classloader | Compile chỉ dùng một classpath tổng hợp | Container/plugin nạp lớp từ loader khác hoặc bị che khuất |

Trước khi sửa, hãy xác định lỗi thuộc loại “không tìm thấy lớp”, “không resolve được module” hay “tìm thấy lớp nhưng API khác version”. Các nhóm lỗi này có nguyên nhân và cách xử lý khác nhau.

## 3. Phân biệt các lỗi thiếu lớp và lỗi không tương thích

### 3.1. `ClassNotFoundException`

`ClassNotFoundException` thường xuất hiện khi code yêu cầu nạp một lớp theo tên nhưng classloader không tìm thấy lớp đó.

Ví dụ:

```java
Class<?> driver = Class.forName("org.postgresql.Driver");
```

Nếu PostgreSQL JDBC driver không có trên classpath mà classloader sử dụng, lệnh trên có thể ném `ClassNotFoundException`.

Lỗi này thường gặp trong các tình huống dùng reflection, plugin hoặc cấu hình tên lớp. Cần tìm xem classloader nào đang được dùng và dependency có mặt trong môi trường của classloader đó hay không.

### 3.2. `NoClassDefFoundError`

`NoClassDefFoundError` là một `LinkageError`. Lỗi thường xảy ra khi JVM cần định nghĩa hoặc liên kết một lớp nhưng không tìm được định nghĩa cần thiết trong lúc chạy. Một nguyên nhân phổ biến là dependency có lúc compile nhưng không có lúc runtime.

Ví dụ `Main` đã compile với `example-library.jar`, nhưng khi chạy `Main` gọi phương thức dùng lớp `com.example.Helper` mà JAR chứa `Helper` bị thiếu. JVM có thể báo:

```text
Exception in thread "main" java.lang.NoClassDefFoundError: com/example/Helper
```

Đôi khi `NoClassDefFoundError` xuất hiện sau khi một lớp đã thất bại trong quá trình khởi tạo tĩnh ở lần đầu. Khi đó cần xem stack trace trước đó và thông báo `Caused by`, vì lỗi gốc có thể là exception trong static initializer chứ không đơn giản là thiếu file JAR.

### 3.3. `NoSuchMethodError` và `NoSuchFieldError`

Hai lỗi này thường biểu thị JVM đã tìm thấy lớp nhưng lớp được nạp không có method hoặc field mà bytecode đang cần.

Ví dụ:

- Compile dựa trên `library-api:2.0` có method `newMethod()`.
- Runtime lại nạp `library-api:1.0`, không có method đó.
- JVM có thể ném `NoSuchMethodError` khi code gọi method.

Đây là vấn đề tương thích binary/version, không phải lúc nào cũng là thiếu JAR. Cần xác định chính xác file JAR nào đã được nạp và vì sao runtime chọn version đó.

### 3.4. `UnsupportedClassVersionError`

Lỗi này thường xuất hiện khi runtime Java cũ hơn phiên bản bytecode mà compiler tạo ra. Compiler có thể chạy bằng JDK mới, trong khi server dùng JRE/JDK cũ.

Kiểm tra:

```bash
java -version
javac -version
```

Nếu dùng Gradle/Maven Wrapper, cũng cần xem JVM chạy build tool và compiler toolchain. Có thể dùng `javac --release` hoặc cấu hình compiler plugin để tạo bytecode/API tương thích với phiên bản Java mục tiêu, nhưng phải bảo đảm code và dependency cũng hỗ trợ phiên bản đó.

## 4. Maven: scope quyết định dependency có trên runtime classpath hay không

Maven có nhiều dependency scope, và mỗi scope ảnh hưởng đến compile/test/runtime classpath cũng như dependency propagation.

| Scope | Compile main | Runtime ứng dụng | Test | Ghi chú |
|---|---:|---:|---:|---|
| `compile` | Có | Có | Có | Scope mặc định; thường dùng cho dependency ứng dụng |
| `provided` | Có | Không trong runtime classpath thông thường | Có | Môi trường triển khai được kỳ vọng cung cấp |
| `runtime` | Không cho compile main thông thường | Có | Có | Thư viện cần khi chạy nhưng mã nguồn không cần tham chiếu trực tiếp |
| `test` | Không cho compile main | Không cho runtime ứng dụng | Có | Chỉ dùng cho kiểm thử |
| `system` | Có | Có theo cấu hình | Có | Dựa vào đường dẫn cục bộ, khó tái tạo và không nên dùng thông thường |

Ví dụ cấu hình:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.17.2</version>
        <scope>compile</scope>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>42.7.4</version>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>6.0.0</version>
        <scope>provided</scope>
    </dependency>

    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Trong ví dụ:

- Jackson có trên compile và runtime classpath.
- PostgreSQL driver có trên runtime classpath, dù mã nguồn không cần import trực tiếp class driver.
- Servlet API có trên compile/test classpath, nhưng được kỳ vọng do servlet container cung cấp lúc chạy.
- JUnit chỉ dành cho test.

Nếu ứng dụng standalone cần PostgreSQL driver nhưng dependency bị khai báo `provided` hoặc `test`, compile có thể thành công mà runtime không có driver. Cần chọn scope theo trách nhiệm cung cấp dependency của ứng dụng.

### 4.1. `provided` không phải là cách “đóng gói thư viện vào JAR”

Scope `provided` mô tả dependency có mặt khi compile và test nhưng được runtime environment cung cấp. Với Maven WAR Plugin, dependency `provided` thường không được đưa vào `WEB-INF/lib`.

Nếu ứng dụng không chạy trong container cung cấp dependency đó, cần thay scope hoặc cung cấp thư viện qua cơ chế runtime khác. Chỉ đánh dấu `provided` không khiến JVM tự tìm hoặc tải thư viện.

### 4.2. Dependency bắc cầu

Một dependency `compile` có thể kéo theo các dependency bắc cầu. Maven phân giải graph dựa trên POM của các artifact. Tuy nhiên, dependency có scope `provided` hoặc `test` không truyền bắc cầu như `compile` theo các quy tắc scope Maven.

Nếu ứng dụng phụ thuộc một thư viện mà thư viện đó có dependency runtime, cần kiểm tra dependency graph và scope sau khi Maven mediation. Không nên giả định mọi thư viện xuất hiện trong compile tree đều tự động có trong runtime tree.

## 5. Gradle: compileClasspath và runtimeClasspath

Gradle Java plugin tạo các configuration để phân biệt dependency cần khi compile, chạy và kiểm thử.

| Configuration | Compile main | Runtime main | Mục đích |
|---|---:|---:|---|
| `implementation` | Có | Có | Dependency dùng trong implementation và runtime |
| `api` (Java Library plugin) | Công bố cho compile consumer | Có trong runtime graph | Dependency thuộc API công khai của thư viện |
| `compileOnly` | Có | Không | Dependency chỉ cần compile hoặc do runtime bên ngoài cung cấp |
| `compileOnlyApi` | Có và được công bố cho compile consumer | Không được thêm vào runtime chỉ vì configuration này | Kiểu compile-only xuất hiện trong public API |
| `runtimeOnly` | Không cho compile main | Có | Driver/provider cần khi chạy |
| `testImplementation` | Không cho compile main | Không cho runtime ứng dụng | Dependency cho test |
| `testRuntimeOnly` | Không cho compile test | Có cho test runtime | Dependency chỉ cần khi chạy test |

Ví dụ:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
    runtimeOnly("org.postgresql:postgresql:42.7.4")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.0")
}

tasks.test {
    useJUnitPlatform()
}
```

Nếu dùng `compileOnly` cho PostgreSQL driver, compiler vẫn có thể biên dịch những đoạn code tham chiếu API mà driver cung cấp, nhưng runtime classpath do Gradle tạo sẽ không có driver. Nếu code dùng JDBC auto-discovery, lỗi có thể chỉ xuất hiện lúc mở kết nối vì không tìm được provider.

### 5.1. Kiểm tra hai configuration

Chạy:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Hai cây dependency giúp so sánh thư viện nào có khi compile và thư viện nào có khi chạy. Nếu dependency xuất hiện trong `compileClasspath` nhưng vắng ở `runtimeClasspath`, hãy xem configuration khai báo và dependency propagation.

Để xem vì sao một version được chọn hoặc dependency đến từ đâu:

```bash
./gradlew dependencyInsight \
    --dependency postgresql \
    --configuration runtimeClasspath
```

Lệnh này tập trung vào một dependency trong configuration được chỉ định. Nó giúp xác định version được chọn, đường đi trong graph và lý do selection.

## 6. Build thành công nhưng JAR không chứa dependency

Một nguyên nhân rất phổ biến là nhầm lẫn giữa runtime classpath và nội dung của JAR.

Task `jar` tiêu chuẩn của Gradle Java plugin và Maven JAR Plugin thường đóng gói lớp và resource của chính project. Chúng không mặc định nhúng toàn bộ dependency vào bên trong JAR.

Ví dụ project Gradle:

```kotlin
dependencies {
    implementation("com.google.guava:guava:33.3.1-jre")
}
```

Gradle biết Guava là dependency runtime. Nhưng file `app.jar` do task `jar` tiêu chuẩn tạo ra thường không chứa các lớp của Guava. Nếu chỉ chuyển `app.jar` sang máy khác và chạy:

```bash
java -jar app.jar
```

JVM có thể báo thiếu lớp Guava vì dependency JAR không được phân phối và manifest không chỉ đến thư viện bên ngoài.

Có ba cách triển khai phổ biến:

1. Phân phối JAR ứng dụng cùng thư mục `lib/` và dựng classpath khi chạy.
2. Tạo fat JAR/uber JAR hoặc executable archive có cơ chế nạp dependency.
3. Đưa ứng dụng vào môi trường runtime/container đã có quy ước cung cấp dependency.

### 6.1. Phân phối thư viện trong thư mục `lib/`

Ví dụ cấu trúc phân phối:

```text
distribution/
├── app.jar
├── lib/
│   ├── guava.jar
│   ├── jackson-databind.jar
│   └── jackson-core.jar
└── bin/
    └── run.sh
```

Chạy trên Linux/macOS:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

Chạy trên Windows:

```bat
java -cp "app.jar;lib/*" com.example.Main
```

Wildcard `lib/*` đưa các JAR nằm trực tiếp trong thư mục `lib` vào classpath. Nó không tự tìm đệ quy trong các thư mục con.

### 6.2. `java -jar` và `-cp` không kết hợp theo cách nhiều người nghĩ

Khi chạy lớp chính theo classpath:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

JVM dùng classpath được chỉ định để tìm lớp.

Khi chạy:

```bash
java -jar app.jar
```

JVM dùng JAR được chỉ định làm nguồn khởi chạy và lấy lớp chính từ manifest. Classpath dòng lệnh thông thường không được áp dụng như trong chế độ chạy tên lớp. Nếu ứng dụng cần JAR bên ngoài, có thể khai báo `Class-Path` trong manifest hoặc dùng launcher/packaging phù hợp.

Ví dụ manifest:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/guava.jar lib/jackson-databind.jar lib/jackson-core.jar
```

Đường dẫn trong manifest được diễn giải tương đối với vị trí JAR chứa manifest. Những JAR được tham chiếu vẫn phải được phân phối ở đúng vị trí; manifest không nhúng chúng vào `app.jar`.

### 6.3. Fat JAR và executable archive

Fat JAR/uber JAR gom ứng dụng và dependency runtime vào một gói hoặc một cấu trúc archive đặc biệt. Các công cụ thường gặp gồm:

- Maven Shade Plugin.
- Maven Assembly Plugin.
- Gradle Shadow Plugin.
- Spring Boot `bootJar`.

Với Spring Boot executable JAR, dependency thường được đặt trong cấu trúc archive riêng và Spring Boot launcher nạp chúng. Vì vậy không nên giả định mọi executable JAR đều có cấu trúc như một JAR thuần.

Khi tạo fat JAR, cần xem xét duplicate resource, `META-INF/services`, chữ ký JAR, license, thư viện native và classloader. Chỉ thêm dependency vào build file chưa đủ; phải cấu hình task/plugin đóng gói đúng mục tiêu.

## 7. Launcher và môi trường triển khai có thể làm mất classpath

Ứng dụng chạy được trong IDE nhưng không chạy được khi deploy thường do IDE tự dựng classpath đầy đủ từ build model, trong khi script triển khai chỉ gọi một file JAR.

Ví dụ, IDE chạy:

```text
java -cp app.jar;lib/a.jar;lib/b.jar com.example.Main
```

nhưng script server chỉ chạy:

```bash
java -jar app.jar
```

Hai lệnh có môi trường classpath khác nhau. Chương trình thành công trong IDE không chứng minh gói triển khai có đầy đủ dependency.

Các nơi cần kiểm tra:

- Script `.sh`, `.bat`, PowerShell hoặc service unit khởi chạy ứng dụng.
- Biến môi trường `CLASSPATH` nếu launcher có sử dụng.
- Tham số `-cp`, `-classpath`, `-jar`, `--module-path`.
- Thư mục làm việc hiện tại và đường dẫn tương đối.
- Nội dung thư mục `lib/` trong gói triển khai.
- Cấu hình classloader của application server/container.
- Dockerfile, image layer và lệnh `ENTRYPOINT`/`CMD`.
- Cấu hình pipeline copy artifact sang máy đích.

Không nên dựa vào `CLASSPATH` toàn cục như một giải pháp mặc định. Lệnh khởi chạy nên thể hiện rõ các dependency cần thiết để có thể tái tạo và debug.

## 8. Classpath trong Java: thư mục, JAR và thứ tự tìm lớp

Classpath là danh sách các vị trí mà classloader dùng để tìm lớp và resource. Một mục classpath có thể là:

- Thư mục gốc chứa package/class đã biên dịch.
- File JAR hoặc ZIP chứa lớp và resource.
- Wildcard chỉ các JAR trực tiếp trong một thư mục, theo cú pháp launcher hỗ trợ.

Ví dụ:

```bash
java -cp "build/classes:lib/*:config" com.example.Main
```

Trên Windows:

```bat
java -cp "build\classes;lib\*;config" com.example.Main
```

Đường dẫn thư mục `build/classes` phải là gốc package. Nếu lớp có tên `com.example.Main`, file cần nằm ở `build/classes/com/example/Main.class`.

Khi có nhiều JAR chứa cùng một tên lớp, thứ tự và cơ chế classloader có thể quyết định lớp nào được nạp. Điều này có thể dẫn đến việc compile dựa trên version mới nhưng runtime nạp version cũ.

### 8.1. Xem classpath mà tiến trình sử dụng

Có thể in classpath JVM:

```java
public class ShowClasspath {
    public static void main(String[] args) {
        System.out.println(System.getProperty("java.class.path"));
    }
}
```

Lưu ý rằng trong môi trường module hoặc container có classloader tùy chỉnh, `java.class.path` không phản ánh toàn bộ mọi module/classloader mà ứng dụng có thể sử dụng. Nó là một bằng chứng hữu ích cho classpath của ứng dụng, không phải bản đồ hoàn chỉnh của mọi lớp có thể nạp.

Để xem nguồn nạp lớp trên Java hiện đại:

```bash
java -Xlog:class+load=info -cp "app.jar:lib/*" com.example.Main
```

Log này có thể cho biết lớp được nạp từ JAR hoặc vị trí nào. Khi chạy trong container, cần cấu hình JVM options cho tiến trình server và xem classloader tương ứng.

## 9. Classloader: có JAR trên máy chưa chắc classloader nhìn thấy

JVM không tìm lớp bằng cách quét mọi JAR trên ổ đĩa. Lớp chỉ được tìm trong các nguồn mà classloader hiện tại biết đến.

Trong ứng dụng Java thông thường, system/application classloader sử dụng classpath. Trong application server, plugin framework hoặc môi trường modular, có thể có nhiều classloader với phạm vi riêng.

Ví dụ:

```text
JVM
 |
 +-- Platform/Class Loader
 |
 +-- Application Class Loader
 |      +-- app.jar
 |      +-- lib/a.jar
 |      +-- lib/b.jar
 |
 +-- Server/Plugin Class Loader
        +-- server-api.jar
        +-- plugin-x.jar
```

Sơ đồ chỉ minh họa một mô hình có nhiều classloader; thứ tự cha-con và quy tắc delegation phụ thuộc nền tảng. Một JAR có thể tồn tại trên filesystem nhưng không nằm trong phạm vi của classloader cần dùng.

Trong môi trường container:

- Server có thể cung cấp API qua parent classloader.
- Ứng dụng có thể có classloader riêng cho từng deployment.
- Một số server dùng quy tắc ưu tiên class của server hoặc class của ứng dụng theo cấu hình.
- Hai bản cùng tên class được nạp bởi hai classloader khác nhau có thể được JVM xem là hai kiểu khác nhau.

Vì vậy, khi thấy lỗi cast không tương thích hoặc `ClassCastException` dù hai lớp có cùng tên đầy đủ, hãy xem cả classloader đã định nghĩa từng lớp.

## 10. JPMS: module path khác classpath

Từ Java 9, Java Platform Module System (JPMS) cho phép ứng dụng khai báo module và quan hệ phụ thuộc module rõ ràng. Một module thường có file `module-info.java`.

Ví dụ:

```java
module com.example.app {
    requires java.logging;
    requires com.example.library;
}
```

Khai báo `requires` cho biết module cần đọc module khác. Khi biên dịch và chạy ứng dụng theo module system, các module cần thiết phải được tìm thấy và resolve trên module path (hoặc thuộc module system phù hợp).

### 10.1. Compile module và run module

Ví dụ cấu trúc:

```text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Biên dịch với module path:

```bash
javac --module-path lib \
      -d out \
      --module-source-path src \
      -m com.example.app
```

Chạy module:

```bash
java --module-path "out:lib" \
     --module com.example.app/com.example.app.Main
```

Trên Windows, thay dấu `:` trong module path bằng `;`.

Nếu thư viện có mặt trên classpath nhưng ứng dụng khai báo `requires com.example.library`, JVM module resolver không nhất thiết coi JAR trên classpath là module có tên `com.example.library`. Cần đặt module tương ứng trên module path hoặc điều chỉnh thiết kế classpath/module cho đúng.

### 10.2. Module không chỉ cần tồn tại; package còn phải được đọc và export

JPMS có các quy tắc về readability và accessibility:

- `requires` khai báo quan hệ đọc giữa các module.
- `exports` công khai một package để module khác truy cập kiểu public trong package đó.
- `opens` cho phép truy cập reflective sâu vào package theo quy tắc module.
- `requires transitive` truyền khả năng đọc dependency đến các module phụ thuộc consumer.
- `requires static` biểu thị dependency cần lúc compile nhưng có thể không bắt buộc resolve lúc runtime.

Ví dụ module thư viện:

```java
module com.example.library {
    exports com.example.library.api;
}
```

Module ứng dụng:

```java
module com.example.app {
    requires com.example.library;
}
```

Nếu package không được export, module khác có thể không truy cập được API public của package đó dù JAR nằm trên module path. Khi framework dùng reflection, có thể cần `opens` hoặc tùy chọn mở package phù hợp.

### 10.3. `requires static` và compile thành công nhưng runtime thiếu module

Khai báo:

```java
module com.example.app {
    requires static com.example.optional;
}
```

cho phép dependency module được yêu cầu khi compile nhưng không bắt buộc phải có trong module graph lúc runtime. Điều này phù hợp với một số API tùy chọn chỉ được dùng khi có mặt.

Tuy nhiên, nếu code thực sự gọi lớp của module tùy chọn ở một nhánh chạy mà module đó không có, ứng dụng vẫn có thể thất bại khi nạp lớp hoặc resolve liên kết. `requires static` không biến dependency thành thư viện tự có; nó chỉ điều chỉnh điều kiện resolve module.

### 10.4. Classpath và unnamed module

JAR đặt trên classpath thường thuộc unnamed module. Mã trong named module có thể tương tác với unnamed module theo các quy tắc JPMS, nhưng named module không thể dùng `requires` để yêu cầu một unnamed module theo tên module thông thường.

Nhiều thư viện cũ chưa có `module-info.class` có thể được dùng trên module path dưới dạng automatic module, với tên module suy ra từ metadata/tên JAR. Tên automatic module có thể khác tên Maven `artifactId`; nên kiểm tra tên module thay vì đoán.

Nếu dự án pha trộn classpath và module path, hãy xác định rõ thư viện nào là named module, automatic module và classpath entry. Một JAR “có trên máy” chưa đủ; nó phải nằm đúng vị trí để được resolver và classloader nhìn thấy.

## 11. ServiceLoader và dependency được nạp động

Một số API tìm implementation thông qua service provider thay vì tham chiếu class cụ thể trong mã nguồn. Ví dụ JDBC driver hoặc plugin có thể được phát hiện qua `ServiceLoader`.

Mã nguồn:

```java
ServiceLoader<MyService> services = ServiceLoader.load(MyService.class);
for (MyService service : services) {
    service.execute();
}
```

Compiler chỉ cần biết interface `MyService`. Implementation có thể được cung cấp từ JAR riêng và đăng ký bằng metadata `META-INF/services/...` trong classpath, hoặc qua khai báo `provides ... with ...` trong module descriptor.

Nếu API có mặt nhưng provider JAR bị thiếu hoặc metadata không được đóng gói đúng, compile vẫn thành công nhưng danh sách service có thể rỗng hoặc phát sinh lỗi khi provider được nạp.

Với module system, module provider có thể khai báo:

```java
module com.example.provider {
    requires com.example.api;
    provides com.example.api.MyService
        with com.example.provider.DefaultMyService;
}
```

Module sử dụng service khai báo:

```java
module com.example.app {
    requires com.example.api;
    uses com.example.api.MyService;
}
```

Khi chạy modular application, provider module cũng cần được resolve và có mặt trong module layer phù hợp. Chỉ compile với API module không tự thêm implementation provider vào runtime.

## 12. Maven và Gradle: cách tìm dependency bị thiếu

Khi ứng dụng thiếu lớp, cần so sánh dependency graph compile và runtime.

### 12.1. Maven

Xem dependency tree:

```bash
./mvnw dependency:tree
```

Lọc một dependency cụ thể:

```bash
./mvnw dependency:tree -Dincludes=org.postgresql:postgresql
```

Tạo runtime classpath:

```bash
./mvnw dependency:build-classpath \
    -Dmdep.outputFile=runtime-classpath.txt
```

Lệnh `dependency:build-classpath` cần Maven Dependency Plugin. Kiểm tra scope và cấu hình plugin nếu muốn xuất một classpath cụ thể. Với WAR, kiểm tra nội dung archive:

```bash
jar --list --file target/order-web.war
```

Xem các dependency nằm trong `WEB-INF/lib/` và so sánh với những gì container cung cấp. Với plain JAR, đừng kỳ vọng toàn bộ dependency Maven sẽ nằm bên trong file JAR.

### 12.2. Gradle

So sánh hai graph:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Xem lý do chọn dependency:

```bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
```

Kiểm tra task và output:

```bash
./gradlew tasks --all
jar --list --file build/libs/app.jar
```

Nếu ứng dụng dùng Java Library plugin, cần phân biệt dependency công bố qua `api` với dependency nội bộ qua `implementation`. Nếu dependency được đánh dấu `compileOnly`, nó không tự xuất hiện trong runtime classpath. Nếu build một WAR, kiểm tra thêm cấu hình provided của WAR plugin.

## 13. Kiểm tra artifact thực tế thay vì chỉ xem build file

Một build file cho biết ý định cấu hình. Artifact được tạo mới cho biết nội dung thực tế mà ta sẽ triển khai.

Với JAR, có thể liệt kê nội dung:

```bash
jar --list --file build/libs/app.jar
```

Hoặc dùng công cụ ZIP để xem archive. Kiểm tra:

- Có lớp chính và resource cần thiết không?
- Có dependency được kỳ vọng nhúng vào fat JAR không?
- Có `META-INF/MANIFEST.MF` và `Main-Class` không?
- Có `Class-Path` nếu dùng JAR phụ thuộc bên ngoài không?
- Có `META-INF/services/` hoặc module descriptor cần thiết không?

Với WAR, kiểm tra `WEB-INF/classes`, `WEB-INF/lib` và cấu trúc metadata. Với Spring Boot executable JAR, xem cấu trúc archive đặc thù, ví dụ thư mục `BOOT-INF/lib` và `BOOT-INF/classes`.

Nếu artifact đúng nhưng ứng dụng vẫn thiếu thư viện, chuyển sang kiểm tra lệnh khởi chạy, classpath/module path và classloader ở môi trường đích.

## 14. Quy trình điều tra theo thứ tự

Khi nhận được lỗi thiếu thư viện, hãy thu thập bằng chứng theo từng bước:

**Bước 1 — Ghi lại lỗi chính xác.** Lấy tên đầy đủ của lớp/module bị thiếu và stack trace đầu tiên. Phân biệt `ClassNotFoundException`, `NoClassDefFoundError`, `FindException`, `NoSuchMethodError` và `UnsupportedClassVersionError`.

**Bước 2 — Xác định lúc lỗi xảy ra.** Lỗi xuất hiện khi khởi động, khi gọi một chức năng, khi nạp plugin, khi mở kết nối database hay khi framework quét component? Lỗi chỉ xuất hiện trong một nhánh chạy có thể liên quan đến reflection hoặc service provider.

**Bước 3 — Kiểm tra compile và runtime graph.** Dùng `dependency:tree`/`dependency:build-classpath` của Maven hoặc `dependencies --configuration compileClasspath/runtimeClasspath` của Gradle.

**Bước 4 — Kiểm tra scope và version.** Tìm `provided`, `compileOnly`, `runtime`, `runtimeOnly`, `test` và dependency exclusions. Xem version thực tế sau mediation/selection.

**Bước 5 — Kiểm tra artifact.** Liệt kê nội dung JAR/WAR và xác nhận thư viện có được phân phối hay không. Kiểm tra manifest, service metadata và module descriptor nếu có.

**Bước 6 — Kiểm tra lệnh khởi chạy.** Đối chiếu `-cp`, `-jar`, `--module-path`, working directory, thư mục `lib/`, script/service/Docker entrypoint.

**Bước 7 — Kiểm tra runtime thật.** Xác nhận JDK/JRE, server/container, module graph, classloader và version thư viện được nạp.

**Bước 8 — Sửa nguồn sở hữu và chạy lại.** Điều chỉnh dependency declaration, packaging hoặc deployment configuration tại nơi phù hợp; sau đó build lại và kiểm tra artifact/runtime.

Không nên bắt đầu bằng việc thêm ngẫu nhiên nhiều JAR vào classpath. Điều đó có thể che lỗi cấu hình và tạo xung đột version khó phát hiện.

## 15. Bảng triệu chứng và hướng tìm nguyên nhân

| Triệu chứng | Hướng kiểm tra đầu tiên |
|---|---|
| `ClassNotFoundException: org.postgresql.Driver` | Driver có trên runtime classpath không? Có bị khai báo `provided`, `compileOnly` hoặc thiếu trong thư mục `lib/` không? |
| `NoClassDefFoundError: com/fasterxml/...` | Dependency runtime hoặc dependency bắc cầu có bị thiếu khỏi artifact/deployment không? |
| `NoSuchMethodError` trong thư viện | Runtime đang nạp version nào? Có nhiều version trong classpath/container không? |
| IDE chạy được nhưng `java -jar` lỗi | IDE dựng classpath đầy đủ; JAR có manifest Class-Path hoặc fat packaging chưa? |
| Chạy bằng `java -cp` được nhưng `java -jar` lỗi | Lệnh `-jar` không dùng classpath dòng lệnh theo cách thông thường; kiểm tra manifest/packaging |
| WAR chạy ở server A nhưng lỗi ở server B | Hai container cung cấp API/version và classloader policy có giống nhau không? |
| `FindException: Module ... not found` | Module có trên `--module-path` và được resolve không? |
| `IllegalAccessError` hoặc lỗi reflective access | Module có `exports`/`opens` phù hợp không? Có dùng API nội bộ JDK không? |
| Provider không được tìm thấy | Kiểm tra `META-INF/services`, `uses`/`provides` và provider JAR/module có trong runtime không? |
| `UnsupportedClassVersionError` | Runtime Java có đủ mới cho bytecode không? |

## 16. Ví dụ hoàn chỉnh: compile thành công nhưng thiếu JDBC driver

Giả sử một ứng dụng sử dụng JDBC API:

```java
import java.sql.Connection;
import java.sql.DriverManager;

public class DatabaseCheck {
    public static void main(String[] args) throws Exception {
        try (Connection connection = DriverManager.getConnection(
                "jdbc:postgresql://localhost:5432/app",
                "app",
                "secret")) {
            System.out.println(connection.isValid(2));
        }
    }
}
```

Mã nguồn chỉ tham chiếu `java.sql`, API thuộc Java platform. Compiler không cần PostgreSQL driver để biên dịch đoạn code trên. Nhưng lúc chạy, JDBC cần tìm một driver phù hợp cho URL `jdbc:postgresql:`. Nếu driver không có trên runtime classpath, `DriverManager` có thể báo không tìm thấy driver phù hợp.

Maven nên khai báo driver là runtime dependency:

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>42.7.4</version>
    <scope>runtime</scope>
</dependency>
```

Gradle:

```kotlin
dependencies {
    runtimeOnly("org.postgresql:postgresql:42.7.4")
}
```

Build tool sẽ đưa driver vào runtime dependency graph. Tuy nhiên, nếu tạo plain JAR và chỉ copy JAR ứng dụng sang máy khác, driver vẫn phải được phân phối riêng hoặc nhúng bằng packaging phù hợp. Dependency graph đúng không tự bảo đảm file triển khai đã chứa tất cả thư viện.

## 17. Ví dụ hoàn chỉnh: Servlet API do container cung cấp

Một servlet dùng `jakarta.servlet` cần API ở compile time. Project có thể khai báo Maven scope `provided` hoặc Gradle `compileOnly`/cấu hình WAR provided tương ứng.

Maven:

```xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
```

Compile thành công là điều mong đợi. Khi đóng gói WAR, API thường không nằm trong `WEB-INF/lib`; container phải cung cấp API và implementation tương thích. Nếu deploy WAR vào một server không hỗ trợ Jakarta Servlet 6 hoặc cấu hình classloader không phù hợp, ứng dụng có thể thất bại dù compile đã thành công.

Trong trường hợp này, giải pháp đúng có thể là chọn container tương thích hoặc điều chỉnh API version mục tiêu. Thêm Servlet API vào WAR một cách tùy tiện có thể tạo xung đột với API mà server cung cấp.

## 18. Những điều cần ghi nhớ

- Compile classpath và runtime classpath là hai tập dependency khác nhau.
- Compiler chỉ xác nhận các kiểu cần thiết cho quá trình biên dịch; nó không bảo đảm thư viện được phân phối khi chạy.
- Maven scope `provided`, `test` và Gradle `compileOnly` có thể làm dependency vắng khỏi runtime classpath ứng dụng.
- Maven `runtime` và Gradle `runtimeOnly` dành cho dependency cần lúc chạy nhưng không cần trên compile classpath chính.
- Plain JAR không mặc định chứa tất cả dependency; cần thư mục `lib/`, manifest classpath, fat JAR hoặc môi trường cung cấp thư viện.
- `java -jar` sử dụng manifest và không áp dụng `-cp` như chế độ chạy tên lớp.
- Classpath và module path là hai cơ chế tìm/resolve khác nhau; JPMS còn có `requires`, `exports`, `opens`, `uses` và `provides`.
- Lỗi `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError` và `FindException` gợi ý các nhóm nguyên nhân khác nhau.
- Dependency graph, artifact thực tế, lệnh khởi chạy và classloader runtime đều cần được kiểm tra.

Khi chương trình compile thành công nhưng chạy thiếu thư viện, hãy lần theo toàn bộ đường đi của dependency: được khai báo ở đâu, có trên compile classpath hay không, có trên runtime graph hay không, được đóng gói hoặc cung cấp bởi môi trường nào, và classloader/module resolver có nhìn thấy nó hay không. Đối chiếu các bước đó sẽ chỉ ra nơi cần sửa mà không phải thêm JAR một cách phỏng đoán.
