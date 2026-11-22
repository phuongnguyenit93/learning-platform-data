# ClassNotFoundException và NoClassDefFoundError

Khi nâng JDK, framework hoặc dependency của một hệ thống Java, hai lỗi rất dễ bị nhầm là `ClassNotFoundException` và `NoClassDefFoundError`. Cả hai đều có thể xuất hiện khi runtime không tìm hoặc không sử dụng được một lớp, nhưng **chúng khác loại, khác thời điểm phát sinh và có thể có nguyên nhân gốc rất khác nhau**. Chẩn đoán nhầm sẽ dẫn tới cách chữa sai: thêm hàng loạt JAR vào classpath, tắt module encapsulation, hoặc rollback JDK trong khi vấn đề thật chỉ là một dependency không được đóng gói.

Bài học thuộc chủ đề **Java Advance Compatibility Migration**, chương **Chẩn đoán lỗi**, tập trung vào cách đọc stack trace, hiểu cơ chế load–link–initialize của JVM, xác định lỗi classpath/module path, phân biệt lỗi thiếu class với lỗi khởi tạo lớp, truy vết Maven/Gradle, fat JAR, container, Java EE/Jakarta và JPMS. Các ví dụ đi từ mã có thể tái hiện đến quy trình xử lý production an toàn.

## 1. So sánh nhanh hai lỗi

| Tiêu chí | `ClassNotFoundException` | `NoClassDefFoundError` |
|---|---|---|
| Loại | **Checked exception** kế thừa `ReflectiveOperationException`. | **Error** kế thừa `LinkageError`. |
| Ý nghĩa cốt lõi | Một API yêu cầu tìm/nạp class theo tên nhưng classloader không tìm được. | JVM hoặc một thành phần dùng class không thể hoàn tất việc xác định/định nghĩa class cần thiết hoặc lớp đã ở trạng thái khởi tạo lỗi. |
| Điểm thường gặp | `Class.forName(...)`, `ClassLoader.loadClass(...)`. | Tham chiếu bytecode tới một class lúc runtime, hoặc dùng lại class từng khởi tạo thất bại. |
| Thời điểm | Khi lệnh nạp class theo tên được thực thi. | Có thể trong loading, linking, resolution hoặc khi khởi tạo/tiếp tục sử dụng class đã bị đánh dấu erroneous. |
| Ai thường phát ra? | API reflection/class loading báo trực tiếp. | JVM hoặc code liên quan trong quá trình linkage/initialization. |
| Xử lý mã | Có thể `catch (ClassNotFoundException e)` để xử lý tính năng tùy chọn. | Không nên coi là một ngoại lệ nghiệp vụ cần bắt và tiếp tục. |
| Cách điều tra đầu tiên | Tên class cần nạp, classloader được dùng, classpath/module graph. | Đọc toàn bộ message + `Caused by`, xác định thiếu definition hay initialization đã thất bại. |

**Quy tắc thực hành:** đừng suy luận chỉ từ tên lỗi. `NoClassDefFoundError` **không luôn** có nghĩa file `.class` không tồn tại; có thể class hiện diện nhưng đã khởi tạo thất bại ở một lần sử dụng trước.

## 2. Cấu trúc kế thừa và ý nghĩa xử lý

```text
java.lang.Throwable
├── java.lang.Exception
│   └── java.lang.ReflectiveOperationException
│       └── java.lang.ClassNotFoundException
└── java.lang.Error
    └── java.lang.LinkageError
        └── java.lang.NoClassDefFoundError
```

`ClassNotFoundException` là checked exception. Với API khai báo `throws ClassNotFoundException`, Java compiler buộc bạn bắt hoặc khai báo `throws`.

`NoClassDefFoundError` là một `Error`, thuộc nhóm sự cố liên kết thực thi. Java compiler không buộc bạn bắt nó. Thông thường, **cần sửa môi trường, dependency hoặc lỗi khởi tạo**, không nên coi việc `catch (NoClassDefFoundError e)` rồi bỏ qua là giải pháp migration.

Cả hai đều có thể tồn tại trong chuỗi nguyên nhân:

```text
java.lang.NoClassDefFoundError: com/example/codec/Codec
    at com.example.App.main(App.java:15)
Caused by: java.lang.ClassNotFoundException:
    com.example.codec.Codec
    at ...ClassLoader.loadClass(...)
```

Trong ví dụ này, đoạn code của JVM cần class `Codec`, nhưng classloader được gọi bên dưới không tìm thấy. `ClassNotFoundException` là nguyên nhân lồng dưới; `NoClassDefFoundError` là lỗi biểu hiện ở nơi JVM đang giải quyết tham chiếu.

## 3. JVM load, link và initialize một class như thế nào?

Sơ đồ khái niệm:

```text
        Tham chiếu class / Class.forName / class loading
                              |
                              v
                 LOAD: tìm/định nghĩa class
                              |
                              v
        LINK: verify -> prepare -> resolve references*
                              |
                              v
                   INITIALIZE: static fields,
                  static initializers, superclass
                              |
                              v
                         Sử dụng class

* Resolution có thể thực hiện linh hoạt, không bắt buộc
  mọi symbolic reference đều resolve ngay một thời điểm.
```

Cần hiểu những pha này để biết vì sao “compile được” khác “chạy được”.

### 3.1. Loading

Classloader tìm bytecode hoặc module class definition phù hợp. Nếu một API như `ClassLoader.loadClass("x.Y")` không tìm được, nó có thể ném `ClassNotFoundException`.

### 3.2. Linking

JVM xác minh bytecode, chuẩn bị các trường tĩnh, và giải quyết symbolic references theo quy tắc JVM. Một class có thể được nạp rồi nhưng khi thực thi tới lời gọi cần một dependency khác lại thất bại do không tìm thấy definition. Lúc đó có thể nhận `NoClassDefFoundError`.

### 3.3. Initialization

JVM chạy static field initializers và static initializer blocks khi class được khởi tạo lần đầu theo các quy tắc về active use. Nếu initialization thất bại:
- Lần đầu có thể nhận `ExceptionInInitializerError` nếu một non-Error exception thoát ra từ initializer.
- Các lần dùng tiếp theo có thể nhận `NoClassDefFoundError: Could not initialize class ...` do class đã bị đánh dấu erroneous trong classloader liên quan.

Vì vậy, với `NoClassDefFoundError`, việc chỉ hỏi “JAR có chứa class không?” chưa đủ.

## 4. Ví dụ 1: ClassNotFoundException khi nạp động

Một ứng dụng cho phép bật plugin theo cấu hình:

```java
package demo;

public class DynamicPluginLoader {
    public static void main(String[] args) {
        String pluginClass = "demo.plugins.ReportPlugin";

        try {
            Class<?> type = Class.forName(pluginClass);
            System.out.println("Loaded: " + type.getName());
        } catch (ClassNotFoundException e) {
            System.err.println(
                "Plugin class not available: " + pluginClass);
            e.printStackTrace();
        }
    }
}
```

Nếu `demo.plugins.ReportPlugin` không nằm trong không gian tìm kiếm của loader được sử dụng:

```text
Plugin class not available: demo.plugins.ReportPlugin
java.lang.ClassNotFoundException:
    demo.plugins.ReportPlugin
    at ...
```

Ở đây mã cố ý nạp một class bằng **tên chuỗi**. `Class.forName` có thể tải và khởi tạo class; nếu mục tiêu chỉ là kiểm tra sự hiện diện mà không khởi tạo, có overload:

```java
Class<?> type = Class.forName(
    "demo.plugins.ReportPlugin",
    false,
    Thread.currentThread().getContextClassLoader());
```

Giá trị `false` yêu cầu **không khởi tạo** class như một phần của lời gọi này; nó không đảm bảo dependency khác sẽ không được liên kết hoặc loader sẽ không gặp lỗi khác. Cần xử lý riêng các sự cố `LinkageError` nếu ranh giới plugin thật sự cần cô lập chúng, đồng thời không che lỗi production.

### 4.1. Khi nào nên bắt lỗi này?

Một plugin **thực sự tùy chọn** có thể trả thông báo rõ và vô hiệu hóa riêng tính năng khi class vắng mặt theo hợp đồng. Nhưng nếu `ReportPlugin` là thành phần bắt buộc, tốt hơn là **fail fast** khi startup, tránh hệ thống báo khỏe rồi thất bại lúc khách hàng sử dụng tính năng.

Không viết một khối `catch (Exception e) { }` hoặc `catch (Throwable t) { }` bỏ qua toàn bộ lỗi nạp plugin. Nó có thể che `ExceptionInInitializerError`, lỗi version và các sự cố nghiêm trọng.

## 5. Ví dụ 2: NoClassDefFoundError vì class có lúc compile nhưng không có lúc chạy

Hai file Java:

```text
src/
└── demo/
    ├── App.java
    └── Helper.java
```

`src/demo/Helper.java`:

```java
package demo;

public final class Helper {
    public static String message() {
        return "Helper is present";
    }
}
```

`src/demo/App.java`:

```java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println(Helper.message());
    }
}
```

Biên dịch cả hai:

```bash
mkdir -p build/classes build/runtime/demo
javac -d build/classes src/demo/App.java src/demo/Helper.java
java -cp build/classes demo.App
```

Kết quả khi đủ class:

```text
Helper is present
```

Bây giờ giả lập một package/runtime thiếu dependency: **chỉ copy App.class**, không copy Helper.class.

```bash
cp build/classes/demo/App.class build/runtime/demo/
java -cp build/runtime demo.App
```

Một kết quả điển hình:

```text
Exception in thread "main" java.lang.NoClassDefFoundError:
    demo/Helper
    at demo.App.main(App.java:5)
Caused by: java.lang.ClassNotFoundException: demo.Helper
    at ...
```

Ở đây `App.class` được biên dịch với một symbolic reference tới `Helper`. Khi runtime cần giải quyết tham chiếu nhưng không thấy `Helper.class`, JVM không thể hoàn tất liên kết và tạo `NoClassDefFoundError`.

Lưu ý:
- Lệnh `mkdir`/`cp` sử dụng cú pháp Unix/macOS/Git Bash. Trên Windows PowerShell, dùng `New-Item -ItemType Directory` và `Copy-Item` tương ứng.
- Nếu xóa cả `App.class`, thông báo có thể là “Could not find or load main class demo.App” với `ClassNotFoundException` ở nguyên nhân; đó là tình huống khác với việc **main class tồn tại nhưng dependency của nó thiếu**.

## 6. Ví dụ 3: NoClassDefFoundError sau khi static initializer thất bại

Đây là trường hợp quan trọng nhất dễ bị bỏ sót khi migration. File `InitFailureDemo.java`:

```java
package demo;

public class InitFailureDemo {
    static class Configuration {
        static final int PORT = loadPort();

        private static int loadPort() {
            throw new IllegalStateException(
                "Missing required environment configuration");
        }
    }

    public static void main(String[] args) {
        for (int i = 1; i <= 2; i++) {
            System.out.println("Attempt " + i);
            try {
                System.out.println(Configuration.PORT);
            } catch (Throwable failure) {
                failure.printStackTrace(System.out);
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -d out src/demo/InitFailureDemo.java
java -cp out demo.InitFailureDemo
```

Kết quả khái niệm:

```text
Attempt 1
java.lang.ExceptionInInitializerError
Caused by: java.lang.IllegalStateException:
    Missing required environment configuration

Attempt 2
java.lang.NoClassDefFoundError:
    Could not initialize class demo.InitFailureDemo$Configuration
```

Ở lần 1, class `Configuration` **có mặt** và đã được tìm thấy, nhưng static initialization thất bại. JVM đánh dấu class ở trạng thái khởi tạo lỗi. Ở lần 2 trong cùng classloader, việc sử dụng nó dẫn tới `NoClassDefFoundError`.

**Cách sửa đúng:** tìm lỗi *đầu tiên* khi class được khởi tạo: thiếu environment, sai credentials, network call trong static init, thiếu native library hoặc exception của thư viện; không vội thêm JAR chỉ vì lần sau nhìn thấy `NoClassDefFoundError`.

Chương trình ví dụ cố tình `catch (Throwable)` để **minh họa hai lần sử dụng trong một process**. Đây không phải mẫu xử lý sự cố production.

## 7. Stack trace nào cần đọc trước?

Khi gặp:

```text
java.lang.NoClassDefFoundError:
    Could not initialize class com.example.storage.ConnectionHolder
```

Đừng chỉ search class `ConnectionHolder` có trong JAR hay không. Trước tiên:
1. Tìm lần xuất hiện **đầu tiên** của lỗi trong log theo process/instance.
2. Tìm `ExceptionInInitializerError`, `IllegalStateException` hoặc native linkage error trước đó.
3. Đọc toàn bộ `Caused by:` chain và `Suppressed:` nếu có.
4. Xác định ứng dụng đã bị restart chưa; classloader trong process mới có thể thử initialize lại.
5. Kiểm tra source của static field initializer/static block và các dependencies được gọi ở đó.

Ngược lại, nếu lỗi là:

```text
java.lang.NoClassDefFoundError: jakarta/servlet/Filter
Caused by: java.lang.ClassNotFoundException:
    jakarta.servlet.Filter
```

đó là dấu hiệu mạnh về **runtime class/module/dependency chưa cung cấp API Jakarta Servlet tương ứng**, chẳng hạn chạy library Jakarta trên Servlet container cũ.

Cần ưu tiên lỗi gốc, không áp cùng một cách chữa cho hai chuỗi lỗi khác nhau.

## 8. Đọc tên class trong message đúng cách

Trong thông báo:

```text
java.lang.NoClassDefFoundError:
    com/example/codec/JsonCodec
```

tên dùng dấu `/` thường phản ánh internal/binary name trong bytecode. Đổi sang tên class Java để tìm file:

```text
com.example.codec.JsonCodec
com/example/codec/JsonCodec.class
```

Với class lồng nhau:

```java
package demo;

public class Outer {
    public static class Inner { }
}
```

Tên binary dùng cho reflection/classloader là:

```text
demo.Outer$Inner
```

Không phải `demo.Outer.Inner` khi gọi `Class.forName`. Mặt khác, API `Outer.Inner.class` vẫn là cú pháp source hợp lệ.

Cũng lưu ý Java package/class names có phân biệt chữ hoa và chữ thường. Một artifact từng chạy trên môi trường filesystem không phân biệt hoa thường vẫn có thể lỗi sau khi lên Linux container.

## 9. Phân biệt lỗi trực tiếp và lỗi gián tiếp

Ví dụ ứng dụng chỉ gọi:

```java
new com.example.reports.ReportService().render();
```

nhưng runtime thiếu `org.example.json.JsonProvider` nằm trong **dependency của ReportService**. Message có thể nhắc class thiếu này, không phải lớp ở dòng source mà developer nhìn thấy.

Sơ đồ:

```text
Application
   |
   v
ReportService.class  (present)
   |
   v
JsonProvider.class   (missing at runtime)
   |
   v
NoClassDefFoundError
```

Điều tra phải tìm **class nào thật sự không được định nghĩa** và **artifact nào lẽ ra cung cấp nó**, không chỉ nhìn dependency direct của module application.

Đây là nơi `mvn dependency:tree`, `gradle dependencies` và `jdeps` hỗ trợ xác định transitive dependencies hoặc build/package scope sai.

## 10. Nguyên nhân phổ biến: thiếu runtime dependency

Các kịch bản thường gặp:
- JAR chỉ nằm trong compile classpath, không nằm ở runtime classpath.
- Maven dependency dùng `provided` nhưng chạy như standalone app không có container cung cấp.
- Gradle dependency dùng `compileOnly` thay vì `implementation` khi runtime thật cần class.
- Dependency được exclude hoặc conflict resolution chọn bản khác dự kiến.
- Build tạo thin JAR nhưng khi deploy quên thư mục `lib/`.
- Container build chỉ copy application JAR, không copy dependencies cần thiết.
- Một provider bị bỏ khi tạo shaded/uber JAR.
- CI test classpath vô tình có thư viện mà production không có.

Hãy xác định cả ba:
1. **Artifact cần class** (consumer).
2. **Artifact cung cấp class** (provider).
3. **Runtime classloader/module graph** quyết định provider có nhìn thấy không.

Không chữa bằng cách thêm tất cả thư viện compile và test vào production. Điều đó có thể kéo theo xung đột, tăng tấn công bề mặt hoặc phá dependency management.

## 11. Maven scopes và khác biệt compile–runtime

Trong Maven:

| Scope | Hành vi thường gặp | Rủi ro migration |
|---|---|---|
| `compile` | Có ở compile/runtime classpath phù hợp. | Version conflict hoặc thiếu transitive artifact sau packaging. |
| `runtime` | Cần khi chạy, không cần trực tiếp để compile source. | Có thể bị bỏ nếu chỉ copy main JAR. |
| `provided` | Dùng lúc compile/test nhưng kỳ vọng runtime/container cung cấp. | Standalone deployment có thể thiếu class. |
| `test` | Chỉ dành cho tests. | Test xanh nhưng production thiếu thư viện. |
| `system` | Phụ thuộc file ở đường dẫn cụ thể. | Khó di động, đặc biệt `tools.jar` cũ. |
| `import` | Dùng cho BOM trong dependencyManagement. | Không tự thêm dependency runtime. |

Ví dụ trong WAR triển khai trên Jakarta Servlet container tương thích:

```xml
<dependency>
  <groupId>jakarta.servlet</groupId>
  <artifactId>jakarta.servlet-api</artifactId>
  <version>VERSION_MATCHING_CONTAINER</version>
  <scope>provided</scope>
</dependency>
```

Placeholder version phải được thay bằng version phù hợp runtime. Khi chạy JAR standalone không có servlet container, không thể giữ cùng giả định `provided` mà mong runtime tự cung cấp Servlet API.

Lệnh chẩn đoán:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Với multi-module, chạy trong module đang lỗi và đối chiếu scope thực tế. `effective-pom` giúp thấy inheritance/management; dependency tree giúp thấy resolved dependencies. Cần kiểm tra artifact được đóng gói và triển khai, không chỉ POM.

## 12. Gradle configurations và runtimeClasspath

Một lỗi thường gặp:

```kotlin
dependencies {
    compileOnly("com.example:codec-api:1.0")
}
```

Nếu code thật sự dùng `Codec` tại runtime mà không có container/module khác cung cấp, `compileOnly` là sai ý nghĩa.

Thay bằng dependency thích hợp:

```kotlin
dependencies {
    implementation("com.example:codec-api:1.0")
}
```

Phiên bản/artifact minh họa. Với implementation provider tải qua SPI, có thể còn cần thêm dependency runtime riêng.

Các lệnh:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency codec-api \
  --configuration runtimeClasspath
```

Trong multi-project build, dùng đúng task/configuration của subproject bị lỗi. `testRuntimeClasspath` có thể lớn hơn `runtimeClasspath`, nên không thể lấy kết quả test thành công làm chứng cứ package production đủ class.

## 13. Compile classpath, test classpath và production classpath

Một pipeline có thể dùng bốn classpath khác nhau:

```text
javac compileClasspath
         |
         v
   testRuntimeClasspath
         |
         v
   packaged artifact
         |
         v
production runtime classpath
```

Ví dụ:
- Maven Surefire test classpath chứa một library vì test dependency.
- Spring Boot `bootJar` chứa các runtime dependencies do plugin chọn.
- Deployment thực lại dùng thin JAR và quên copy provider.
- Hoặc application server cung cấp Servlet/JPA classes với version khác thư viện compile.

Vì vậy, hãy điều tra **classpath/module path của process đang thất bại**. Nếu code chạy trên full IDE classpath nhưng hỏng trong Docker, sự khác nhau quan trọng nằm ở packaging/deployment.
## 14. Kiểm tra nội dung JAR và cấu trúc fat JAR

Một bước chẩn đoán hữu ích là xác nhận **class nào thực sự nằm trong artifact nào**.

Ví dụ với JAR thông thường:

```bash
jar tf build/libs/app.jar
```

Tìm class `com/example/codec/JsonCodec.class` trong artifact được cho là cung cấp nó. Nhưng cần phân biệt:

- **Thin JAR:** thường chứa ứng dụng, dependency JAR cần được cung cấp riêng trên classpath hoặc bởi một launcher.
- **Fat/uber JAR:** đã gộp nhiều class/dependency theo cơ chế build.
- **Spring Boot executable JAR:** thường có `BOOT-INF/classes/` và các JAR lồng trong `BOOT-INF/lib/`, được launcher của Spring Boot xử lý.
- **WAR:** có thể dùng `WEB-INF/classes/`, `WEB-INF/lib/` và một số API `provided` từ container.

Ví dụ cấu trúc của một Spring Boot executable JAR:

```text
app.jar
├── BOOT-INF/
│   ├── classes/
│   │   └── com/example/App.class
│   └── lib/
│       ├── spring-core-....jar
│       └── codec-provider-....jar
└── META-INF/
    └── ...
```

Một JAR lồng trong `BOOT-INF/lib/` **không trở thành classpath bình thường chỉ vì ta chạy `java -cp app.jar com.example.App`**. Với Spring Boot executable JAR, sử dụng cơ chế launch do plugin tạo, thường là:

```bash
java -jar app.jar
```

Nếu `java -jar` chạy được nhưng một cách launch khác không tìm thấy class, cần xem lại entry point/launcher và cách classpath được dựng, không kết luận JAR hỏng.

### 14.1. Với shaded/uber JAR

Nếu dùng Maven Shade hoặc Gradle Shadow:
- Kiểm tra filters/exclusions có loại mất class không.
- Kiểm tra relocation đã đổi package name chưa.
- Kiểm tra `META-INF/services` có được merge phù hợp không.
- Kiểm tra các chữ ký số/thông tin module có bị ảnh hưởng không.
- Kiểm tra dependency được gộp có cùng phiên bản/API kỳ vọng không.

Một shaded JAR có thể chứa bytecode `com.example.Codec` nhưng service provider configuration vẫn trỏ tới tên package cũ; lúc này lỗi có thể xuất hiện ở `ServiceLoader` hoặc downstream reflection.

## 15. JPMS: “class có trong file” chưa có nghĩa module đọc được

Từ Java 9, module system bổ sung một lớp quản lý phụ thuộc. Một named module có thể khai báo:

```java
module com.example.app {
    requires com.example.codec;
}
```

Nếu module `com.example.codec` không tìm được khi resolve module graph, launcher có thể thông báo:

```text
java.lang.module.FindException:
    Module com.example.codec not found,
    required by com.example.app
```

Đây **không nhất thiết** là `ClassNotFoundException`/`NoClassDefFoundError`. Lỗi tương tự về ý nghĩa “thiếu thành phần” nhưng xảy ra ở **module resolution**, có type riêng.

Đối chiếu:

| Hiện tượng | Loại lỗi thường gặp | Vấn đề chính |
|---|---|---|
| Named module bắt buộc không nằm trên module path/image | `FindException` hoặc `ResolutionException`. | Module graph không resolve được. |
| Class của dependency runtime không được loader tìm thấy | `ClassNotFoundException`/`NoClassDefFoundError`. | Class definition không khả dụng trong loader context. |
| Package tồn tại nhưng không export cho caller | `IllegalAccessError` hoặc lỗi access tương ứng. | Module access/readability, không phải thiếu class thuần túy. |
| Reflection vào package không open | `InaccessibleObjectException`. | JPMS strong encapsulation. |
| Class file cần Java cao hơn runtime | `UnsupportedClassVersionError`. | Bytecode version, không phải classpath chỉ đơn thuần thiếu. |

Vì vậy, đừng thêm `--add-opens` để sửa mọi thông báo có chữ “class not found”. `--add-opens` giải quyết quyền **deep reflection** trong một số bối cảnh; nó không đưa JAR/module chưa tồn tại vào runtime.

### 15.1. Lệnh chẩn đoán module

```bash
java --list-modules
java --describe-module java.sql
java --show-module-resolution \
  --module-path mods \
  --module com.example.app/com.example.Main
```

Các tên module ứng dụng là ví dụ; cần dùng module descriptor thực tế. `--list-modules` phản ánh modules có trong runtime image; module của ứng dụng trên `--module-path` không tự xuất hiện trong danh sách image chỉ vì có file trên disk.

Với custom runtime tạo bởi `jlink`, cần xác nhận modules cần dùng đã được link vào image. Nếu image thiếu module được nạp động, full JDK có thể chạy được nhưng image rút gọn thất bại.

## 16. Java EE/Jakarta: hai namespace không thay thế nhau

Migration từ Java EE sang Jakarta EE là nguyên nhân điển hình dẫn tới lỗi khi class name thay đổi.

Một thư viện cũ tham chiếu:

```java
import javax.servlet.Filter;
```

Nhưng runtime mới chỉ có:

```java
import jakarta.servlet.Filter;
```

Hai kiểu có tên gần giống và chức năng tương đương ở những thế hệ API tương ứng nhưng **không cùng Java class identity**.

Ví dụ lỗi trong một Jakarta Servlet container khi đưa vào plugin cũ:

```text
java.lang.NoClassDefFoundError: javax/servlet/Filter
Caused by: java.lang.ClassNotFoundException:
    javax.servlet.Filter
```

Ngược lại, thư viện Spring Framework/Jakarta mới chạy trên Servlet container cũ có thể báo thiếu `jakarta/servlet/Filter`.

Cách xử lý:
1. Xác định namespace và phiên bản Servlet/container thực tế.
2. Xác định JAR nào tham chiếu `javax.servlet` và JAR nào tham chiếu `jakarta.servlet`.
3. Nâng **cùng nhóm** web framework, filters, Servlet/Jakarta API và container.
4. Đảm bảo scope `provided` hay bundled phù hợp kiểu deployment.
5. Chạy integration test trên **đúng container đích**, không chỉ unit test với mocks.

Không chỉ thêm cả hai API JAR để “chữa” lỗi. Một class triển khai `javax.servlet.Filter` **không** trở thành `jakarta.servlet.Filter`; việc có cả hai definitions còn có thể làm cấu hình runtime phức tạp hơn.

### 16.1. Không replace mọi javax.*

Một số package như `javax.sql`, `javax.naming`, `javax.crypto` và `javax.tools` vẫn thuộc Java SE. Khi phân loại lỗi, xác định API owner/module và bản Jakarta tương ứng, tránh sửa hàng loạt import không thuộc phạm vi Jakarta EE.

## 17. JAXB/JAX-WS/Java EE modules đã bị loại khỏi JDK 11

JDK 8 từng phân phối một số Java EE/CORBA modules. Theo **JEP 320**, JDK 11 loại bỏ các module liên quan, trong đó có JAXB và JAX-WS thuộc nhóm Java EE.

Ví dụ một ứng dụng cũ:

```java
import javax.xml.bind.JAXBContext;
```

Có thể biên dịch/chạy trước đây nếu phụ thuộc JDK cung cấp. Khi nâng tới Java 11+, nếu không thêm JAXB API/implementation phù hợp, có thể gặp:

```text
java.lang.NoClassDefFoundError:
    javax/xml/bind/JAXBContext
```

hoặc trong một đường nạp động:

```text
java.lang.ClassNotFoundException:
    javax.xml.bind.JAXBContext
```

Cách sửa:
1. Xác định source dùng **JAXB namespace `javax.xml.bind`** hay đã chuyển sang `jakarta.xml.bind`.
2. Khai báo đúng JAXB API và **implementation/provider** độc lập với JDK.
3. Kiểm tra Java/Jakarta EE/Spring framework version compatibility.
4. Chạy marshalling/unmarshalling integration tests và kiểm tra schema.
5. Không trộn ngẫu nhiên API `javax.xml.bind` với implementation chỉ hỗ trợ `jakarta.xml.bind` đời mới.

**Điểm tinh tế:** thiếu JAXB API và thiếu JAXB provider không biểu hiện giống nhau. Nếu API class tồn tại nhưng implementation provider không tìm thấy, có thể xuất hiện exception thuộc JAXB API hoặc service provider error, chứ không nhất thiết là `NoClassDefFoundError`. Cần đọc toàn bộ stack trace thay vì chốt nguyên nhân từ mỗi dòng đầu.

## 18. Classloader isolation trong application server và plugin host

Ngay cả khi JAR tồn tại trên disk, classloader dùng bởi đoạn code lỗi có thể **không nhìn thấy** nó.

Các kiến trúc thường gặp:
- Application server có classloader cho từng WAR/EAR/module.
- Plugin host tạo classloader riêng cho mỗi plugin.
- OSGi hoặc hệ thống module tự quản lý visibility.
- Spring Boot loader xử lý nested JARs.
- Test runner và IDE tạo nhiều classloader cho các nhóm classes.
- Container nạp agent/framework ở vùng classloader khác ứng dụng.
- Thread context classloader (TCCL) được dùng bởi thư viện SPI.

Sơ đồ:

```text
Bootstrap / Platform
          |
          v
Application Loader
     /         \
    v           v
Plugin Loader A  Plugin Loader B
    |                 |
 codec-A.jar       codec-B.jar
```

Nếu code trong Loader A yêu cầu class chỉ nhìn thấy ở Loader B, sự tồn tại của `codec-B.jar` không làm class tự được nạp. Mỗi loader có quy tắc delegation/visibility của riêng nó.

### 18.1. Xem loader của một class đã nạp thành công

```java
public class LoaderDiagnostics {
    public static void print(Class<?> type) {
        System.out.println("Class: " + type.getName());
        System.out.println("Loader: " + type.getClassLoader());
        System.out.println("Module: " + type.getModule());
        System.out.println("Code source: " +
            (type.getProtectionDomain().getCodeSource() == null
                ? "<unknown>"
                : type.getProtectionDomain()
                      .getCodeSource().getLocation()));
    }
}
```

Ví dụ cần Java 9+ vì dùng `getModule()`. Giá trị `getClassLoader() == null` thường liên quan bootstrap loader; không phải lỗi.

Trong môi trường production, không in thông tin internal paths/classloader tùy tiện vào response hoặc logs công khai. Dùng trong môi trường chẩn đoán được kiểm soát.

### 18.2. Context ClassLoader

Một số thư viện lấy loader:

```java
ClassLoader loader =
    Thread.currentThread().getContextClassLoader();
```

TCCL có thể khác loader định nghĩa code thư viện. Điều đó có thể giải thích vì sao `Class.forName(name)` thành công trong một module nhưng `Class.forName(name, true, loader)` hoặc service provider discovery ở thread khác thất bại.

Khi chẩn đoán, ghi **loader nào được dùng tại call site**. Không giải quyết bằng cách đặt toàn bộ JVM classpath thành một thư mục chứa mọi JAR nếu kiến trúc thực sự cần cô lập plugin.

## 19. ServiceLoader: không tìm thấy provider khác không tìm thấy class

Với Java SPI:

```java
import java.util.ServiceLoader;

ServiceLoader<MyService> loader =
    ServiceLoader.load(MyService.class);

for (MyService service : loader) {
    service.run();
}
```

Để tìm implementation từ classpath, thường cần file:

```text
META-INF/services/com.example.spi.MyService
```

nội dung:

```text
com.example.spi.DefaultMyService
```

Với named modules, có thể cần module descriptor tương ứng:

```java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.MyService
        with com.example.provider.DefaultMyService;
}
```

Module consumer sử dụng `ServiceLoader.load(MyService.class)` có thể cần:

```java
module com.example.consumer {
    requires com.example.spi;
    uses com.example.spi.MyService;
}
```

Các snippets minh họa; packages/module names phải khớp project thật.

Nếu thiếu provider:
- Có thể nhận danh sách rỗng mà không có `ClassNotFoundException`.
- Nếu provider configuration trỏ tới class không tồn tại/sai, có thể nhận `ServiceConfigurationError`.
- Nếu provider class có dependency thiếu, có thể nhận một `LinkageError` lồng trong lỗi SPI.
- Nếu module không được resolve/linked, `ServiceLoader` có thể không nhìn thấy provider dù artifact nằm trong thư mục.

Khi chuyển từ classpath sang module path hoặc tạo custom runtime, cần kiểm tra `META-INF/services`, `uses`/`provides`, `--add-modules` và `jlink --bind-services` theo đúng trường hợp. Không coi tất cả lỗi provider discovery là một `ClassNotFoundException`.

## 20. Class được tạo bởi code generator/annotation processor

Lớp thiếu đôi khi không phải source viết tay. Các generator có thể tạo:
- JPA metamodel.
- MapStruct mapper implementations.
- QueryDSL classes.
- JAXB classes.
- Protobuf/Avro generated types.
- OpenAPI clients.
- DI/container factory classes.

Một build local có generated classes tồn tại từ lần biên dịch cũ, còn CI clean build hoặc production package lại thiếu chúng.

Cách xử lý:
1. Xác định class nào được generator sinh ra.
2. Kiểm tra annotation processor/plugin có chạy đúng pha build không.
3. Kiểm tra JDK và version generator có hỗ trợ class file/annotation mới không.
4. Kiểm tra generated source được biên dịch và generated class được đóng gói.
5. Chạy clean/reproducible build trong CI đúng toolchain để loại phụ thuộc build output cũ.

Không nên copy class generated của lần build trước vào source như một giải pháp lâu dài; lần sinh lại tiếp theo có thể tạo tên hoặc API khác.

## 21. Static initializer thất bại do nguyên nhân ngoài classpath

Một lớp có thể chứa:

```java
public final class DatabaseBootstrap {
    static final ConnectionPool POOL = createPool();

    private static ConnectionPool createPool() {
        String url = System.getenv("DB_URL");
        if (url == null) {
            throw new IllegalStateException("DB_URL missing");
        }
        return ConnectionPool.connect(url);
    }
}
```

`ConnectionPool` trong ví dụ là kiểu giả định của thư viện. Nếu `DB_URL` thiếu, static initialization có thể thất bại; những lần gọi sau gây `NoClassDefFoundError: Could not initialize class ...` dù class file hiện diện.

Những lỗi gốc thường thấy:
- Configuration hoặc environment variable thiếu.
- Database/TLS/IdP không sẵn sàng khi class khởi tạo.
- Credentials hoặc file cấu hình sai.
- Static field gọi code throw exception.
- Native library nạp thất bại.
- Class initializer gọi dependency khác thiếu.
- Circular initialization phức tạp dẫn tới trạng thái không hợp lệ.

**Thứ tự điều tra:** tìm lần thất bại initialization đầu tiên, khắc phục nguyên nhân thật, rồi restart/reload bằng cơ chế an toàn. Trong cùng classloader, một class đã khởi tạo thất bại không đơn giản được thử lại chỉ vì môi trường đã đổi sau đó.

## 22. Native libraries và UnsatisfiedLinkError

Một trường hợp khác:

```java
public class NativeCodec {
    static {
        System.loadLibrary("codec_native");
    }
}
```

Nếu thư viện native thiếu hoặc không phù hợp OS/architecture, JVM có thể ném:

```text
java.lang.UnsatisfiedLinkError:
    no codec_native in java.library.path
```

Đây **không phải** `ClassNotFoundException`. Nhưng nếu lỗi xảy ra trong static initialization và class bị đánh dấu erroneous, các lần sử dụng tiếp theo có thể xuất hiện `NoClassDefFoundError: Could not initialize class NativeCodec`.

Cần kiểm tra:
- `java.library.path` và cách nạp native library.
- OS, CPU architecture, ABI/glibc và container base image.
- Permission truy cập file và dependency native liên quan.
- JNI compatibility với JDK và library versions.
- Thông báo lỗi gốc trước khi thấy `NoClassDefFoundError`.

Đừng thêm JAR vào classpath để sửa `UnsatisfiedLinkError` của native binary.

## 23. Class file “wrong name” và package mismatch

Một biến thể của `NoClassDefFoundError` là:

```text
java.lang.NoClassDefFoundError:
    com/example/OldName
    (wrong name: com/example/NewName)
```

Điều này có thể xảy ra khi tên mà classloader/JVM kỳ vọng không khớp **binary name được khai báo trong class file**.

Nguyên nhân:
- Copy/rename một file `.class` mà không biên dịch lại với package/class name đúng.
- Thao tác shading/relocation bytecode sai.
- Tự viết ClassLoader định nghĩa class với tên không khớp.
- Artifact được ghép từ nhiều version không thống nhất.
- Lỗi thao tác thủ công khi đóng gói WAR/JAR.

Đổi tên file trên disk không thay đổi binary name đã được biên dịch vào class file. Hãy rebuild từ source và xem artifact thực tế, không tiếp tục rename các file `.class` để thử.

## 24. Không đánh đồng lỗi version với lỗi thiếu class

Khi ứng dụng được biên dịch trên JDK 21 rồi chạy bằng Java 17, có thể nhận:

```text
java.lang.UnsupportedClassVersionError:
    ... has been compiled by a more recent version
```

Đây là một loại lỗi class format/linkage riêng, **không phải** tình huống runtime không tìm thấy class. Đừng đi tìm JAR bị thiếu nếu bytecode đã ở đó nhưng phiên bản Java quá cũ.

Tương tự:
- `NoSuchMethodError`: class có mặt nhưng method signature runtime không khớp.
- `NoSuchFieldError`: class có mặt nhưng field runtime khác.
- `AbstractMethodError`: binary API/implementation mismatch.
- `IllegalAccessError`: quyền truy cập type/member/module không phù hợp.
- `IncompatibleClassChangeError`: class/interface binary form không tương thích.
- `ClassFormatError`: class file không hợp lệ.

Nhiều lỗi này thuộc `LinkageError` nhưng **hướng giải quyết khác nhau**. Luôn ghi đúng class, method signature, runtime version và dependency actually resolved.

## 25. Multi-release JAR và khác biệt theo JDK

Một multi-release JAR có thể chứa:

```text
META-INF/MANIFEST.MF
com/example/Codec.class
META-INF/versions/9/com/example/Codec.class
META-INF/versions/17/com/example/Codec.class
```

Tùy Java runtime, class loader có thể chọn class file ở version-specific directory tương ứng. Do đó:
- Test trên Java 8 có thể nạp implementation khác Java 17.
- Một dependency chỉ có trong bản implementation Java 17 có thể thiếu ở production.
- Compiler/runtime khác nhau có thể gặp các vấn đề API khác nhau.
- Tool scan JAR cũ có thể không hiểu multi-release entries.

Dùng `jar tf` để kiểm tra và `jdeps --multi-release <version>` theo version cần phân tích; sau đó **chạy test trên JDK thực**. Không kết luận từ bản class nằm ở root của JAR là mọi JDK đều có cùng code path.

## 26. “Chạy ở IDE được, Docker lỗi” thường là tín hiệu classpath

Hãy so sánh theo đúng thứ tự:

| Hạng mục | IDE/test | Container/prod |
|---|---|---|
| Java version/vendor | JDK của IDE | JDK/runtime trong image |
| Entry point | IDE launcher | `java -jar` hoặc custom main |
| Classpath | Project/test dependencies | Packaged artifact và runtime libs |
| Module path | Plugin IDE | Runtime module graph |
| Profiles | Dev/test | Production |
| Environment variables | Local secrets | Container env/secret manager |
| Working directory | Source root | Image working directory |
| Native libraries | Developer OS | Container OS/architecture |

Nếu JAR chứa class nhưng container không tải được, hãy kiểm tra launcher/classloader trước. Nếu lỗi chỉ xảy ra trên Java 17, đọc `Caused by`: có thể là JPMS, bytecode, provider hoặc native library, không nhất thiết một JAR thiếu.

Đặc biệt, custom runtime được tạo với `jlink` có thể không chứa module/provider mà full JDK có. `jdeps` giúp phân tích dependency tĩnh nhưng không thấy đầy đủ class nạp qua reflection hoặc service loading.
## 27. Quy trình điều tra từng bước

Một playbook hữu ích khi production báo `ClassNotFoundException` hoặc `NoClassDefFoundError`:

```text
Nhận exception đầy đủ + cause chain
               |
               v
Có "Could not initialize class"?
       /                 \
      Có                 Không
      |                    |
      v                    v
Tìm lỗi static init    Tên class nào bị thiếu?
lần đầu tiên             |
      |                  v
      |             Class có trong
      |             artifact/runtime?
      |                /       \
      |              Không      Có
      |               |         |
      |               v         v
      |       Build/package  Loader visibility,
      |       scopes/exclude module graph, version
      |               |         |
      +---------------+---------+
                      |
                      v
       Reproduce đúng launcher/JDK/image
                      |
                      v
       Sửa nguyên nhân, không thêm JAR bừa
                      |
                      v
       Test startup + đường chức năng + CI
                      |
                      v
          Canary, giám sát, release
```

### Bước 1 — Giữ nguyên dữ liệu điều tra

Ghi:
- Exception class và message **đầy đủ**.
- Stack trace từ dòng đầu tới toàn bộ `Caused by` chain.
- Process, pod/container, module, release/commit và thời gian.
- JDK version/vendor, command line và launcher thực tế.
- Thao tác gây lỗi và mức tái hiện.
- Lỗi xuất hiện ở startup, request đầu, job nền hay lần gọi thứ hai.

Không chỉ chụp một dòng cuối cùng của log. `NoClassDefFoundError: Could not initialize class` ở request thứ hai thường cần log của lần đầu để thấy nguyên nhân thực sự.

### Bước 2 — Phân loại theo message

- `ClassNotFoundException: com.example.X`: xác định API/loader yêu cầu class X.
- `NoClassDefFoundError: com/example/X`: tìm class definition/đường resolve bị thiếu.
- `NoClassDefFoundError: Could not initialize class X`: ưu tiên lỗi khởi tạo đầu tiên.
- `NoClassDefFoundError: wrong name`: nghi ngờ class file/package/binary name mismatch.
- `FindException: Module ... not found`: module graph.
- `UnsupportedClassVersionError`: runtime quá cũ so với class file.
- `InaccessibleObjectException`: reflective module access.
- `ServiceConfigurationError`: provider discovery/loading.

### Bước 3 — Kiểm chứng class nằm trong artifact nào

Dùng `jar tf` với artifact được triển khai, không chỉ file trong source directory. Với Spring Boot executable JAR, kiểm tra cả `BOOT-INF/classes` và `BOOT-INF/lib`. Với WAR, kiểm tra `WEB-INF/classes`, `WEB-INF/lib` và các API container phải cung cấp.

### Bước 4 — Kiểm tra dependency graph

Maven: `dependency:tree`, `effective-pom`, scopes, exclusions, BOM.

Gradle: `runtimeClasspath`, `dependencyInsight`, configuration của subproject, packaging tasks.

So compile/test graph với production artifact.

### Bước 5 — Kiểm tra JVM/module/classloader

Kiểm tra `java.version`, `java.home`, command line, classloader/TCCL, module path, JDK image modules và startup options. Nếu class tồn tại nhưng không visible, thêm JAR sai classloader có thể không giúp.

### Bước 6 — Tái hiện và sửa một nguyên nhân

Tạo một reproduction tối giản, thay một yếu tố tại một thời điểm: runtime dependency, launcher, classloader, Java version hoặc config initializer. Chạy lại đường nghiệp vụ đúng nơi lỗi xuất hiện và kiểm tra cả các trường hợp error path.

### Bước 7 — Kiểm thử trên deployment đích

Sau sửa, bảo đảm cả startup, integration, message processing và job hiếm có coverage. Đánh giá startup memory, classloading và thời gian chạy. Đừng chỉ kiểm tra một unit test được chạy bằng classpath khác production.

## 28. Các lệnh xem class nào được load từ đâu

Trên các JDK có hỗ trợ:

```bash
java -verbose:class -jar app.jar
```

Option này in class loading information và có thể tạo lượng log lớn. Từ Java 9, unified logging cung cấp ví dụ:

```bash
java -Xlog:class+load=info -jar app.jar
```

Muốn ghi file:

```bash
java -Xlog:class+load=info:file=classload.log \
  -jar app.jar
```

Output điển hình cho biết class name và source/module tương ứng theo JVM. Đừng suy từ cú pháp log ở một JDK rằng mọi JDK khác in giống hệt; kiểm tra `java -Xlog:help` ở bản đang chạy.

**Lưu ý an toàn:** JVM/classloading logs có thể tiết lộ absolute file paths, deployment names hoặc tham số nội bộ. Chỉ bật trong môi trường điều tra có kiểm soát, giới hạn retention và tránh chuyển logs chứa secrets tới nơi công khai.

### 28.1. Công cụ jcmd

Khi được phép attach vào JVM hiện hữu, một số lệnh hữu ích là:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.system_properties
```

Dấu `<pid>` là placeholder process ID. Những lệnh này chỉ dùng được khi công cụ/JDK và quyền truy cập process phù hợp. Thông tin command line/system properties có thể chứa dữ liệu nhạy cảm, cần kiểm soát cách thu thập và chia sẻ.

Không bật tính năng attach hoặc debugging trong production chỉ để xem một class nếu có thể dùng log startup và các công cụ khác ít xâm nhập hơn.

## 29. jar, javap và jdeps: công cụ nào trả lời câu gì?

| Công cụ | Câu hỏi trả lời | Giới hạn |
|---|---|---|
| `jar tf artifact.jar` | Artifact chứa những entry nào? | Không cho biết classloader có thấy hay không. |
| `javap -classpath ... -verbose X` | Class X chứa constant pool, fields/methods, class version gì? | Không chứng minh runtime dependency hiện diện. |
| `jdeps` | Các dependency class/module tĩnh của artifact là gì? | Không thấy đầy đủ reflection/dynamic plugin paths. |
| `mvn dependency:tree` | Maven đã resolve các artifact/version/scope nào? | Không tự xác nhận JAR nào đã được copy vào image. |
| `gradle dependencies` | Gradle configuration resolve thế nào? | Test/runtime configurations có thể khác. |
| `java --list-modules` | Runtime image chứa modules nào? | Không liệt kê mọi JAR ứng dụng trên classpath. |
| `java --show-module-resolution` | Named modules được resolve thế nào khi launch? | Không thay thế classloader diagnostics cho mọi library. |
| JVM class load logs | Những class đã được load và source quan sát được? | Khối lượng lớn, có thể thiếu đường chưa thực thi. |

Ví dụ:

```bash
jar tf app.jar
javap -classpath "app.jar:libs/*" \
  -verbose com.example.App
jdeps --missing-deps --recursive \
  --class-path "libs/*" app.jar
```

Trên Windows, phân tách classpath khác (thường `;`), và `grep`/shell quoting cũng khác. Đối với module-based application, dùng tham số module path đúng tool và JDK phiên bản tương ứng.

Khi `jdeps` báo thiếu dependency tĩnh, đây là manh mối mạnh nhưng chưa phải giải pháp hoàn chỉnh. Có thể cần artifact chỉ có ở runtime container, hoặc dynamic dependency mà `jdeps` không quan sát được.

## 30. Kiểm tra thực tế artifact đã deploy

Một tình huống phổ biến:

```text
CI workspace:
  build/libs/app.jar
  build/libs/dependency.jar

Docker image:
  /app/app.jar  (chỉ copy một file)
```

Test chạy bằng Gradle/Maven classpath có cả hai JAR, trong khi container chỉ có `app.jar`. Kết quả là production gặp lỗi dù test đã thành công.

Các bước:
1. Xác định image digest/tag đang chạy.
2. Kiểm tra lệnh launch thực tế và working directory.
3. Kiểm tra JAR, thư mục libs và manifests có trong image.
4. Đối chiếu checksum với artifact tạo từ CI.
5. Xác minh runtime Java version trong container.
6. So dependency tree với runtime classpath/package.
7. Sửa Dockerfile/build packaging và test chính **image mới**.

Đừng lấy container image đang chạy rồi thêm thủ công JAR bên trong như cách sửa lâu dài; lần deploy sau sẽ làm mất thay đổi và không có provenance.

## 31. Tình huống Spring Boot nâng major version

Giả sử ứng dụng chuyển từ Spring Boot 2.x/JDK 8 sang Spring Boot 3.x/JDK 17. Một thư viện tự viết vẫn chứa import `javax.servlet.*`.

Sau migration, ứng dụng có thể báo:

```text
java.lang.NoClassDefFoundError:
    javax/servlet/http/HttpServletRequest
```

Mặc dù Spring Boot 3 có các dependency web, các API đích nằm trong `jakarta.servlet.*`, không phải `javax.servlet.*`.

Quy trình xử lý:
1. Xem dependency graph, xác định library nào được biên dịch với Java EE API cũ.
2. Kiểm tra Servlet container/framework đã theo Jakarta target chưa.
3. Nâng/recompile custom filter/controller/interceptor phù hợp target namespace.
4. Nâng third-party dependencies liên quan, không chỉ thêm Jakarta Servlet API.
5. Kiểm tra dependency scopes và việc bundling API/provider.
6. Chạy integration test thực sự khởi tạo web context/filter chains.

Khi nâng Spring Boot 3 → Boot 4 hoặc Spring Security 6 → 7, lỗi có thể đến từ thay đổi khác của framework/dependency; cần xem release notes của đúng version chứ không mặc định mọi lỗi classloading đều vì `javax/jakarta`.

## 32. Tình huống thư viện logging hoặc JSON bị thiếu khi đổi build

Giả sử code dùng facade nhưng runtime thiếu implementation/adapter:
- Compile thành công vì có API JAR.
- Framework chạy tới đường dùng provider.
- Runtime có thể tìm không thấy provider hoặc nhận thông báo khởi tạo logging/JSON.

Không phải lần nào cũng thành `ClassNotFoundException`. Có thể có warning về provider không hiện diện, `ServiceConfigurationError` hoặc failure của framework. Khi thấy tên class trong log, cần xác nhận **framework đang tìm API, implementation hay service provider**.

Ví dụ một API library khai báo module nhưng runtime provider thiếu. Giải pháp là thêm implementation được support ở đúng runtime configuration, kiểm tra service metadata và không trộn nhiều incompatible implementations vào cùng classloader.

## 33. Tình huống custom classloader nạp plugin

Một plugin host nhận tên class từ config:

```java
public interface Plugin {
    void execute();
}
```

Một loader rút gọn:

```java
public final class PluginHost {
    public static Object loadPlugin(
            String className, ClassLoader pluginLoader)
            throws ClassNotFoundException,
                   ReflectiveOperationException {
        Class<?> type = Class.forName(
            className, true, pluginLoader);
        return type.getDeclaredConstructor().newInstance();
    }
}
```

Chữ ký ví dụ đang khai báo cả `ClassNotFoundException` và superclass của nó `ReflectiveOperationException` nên **không cần liệt kê cả hai** trong code thực tế; có thể chỉ dùng `throws ReflectiveOperationException`. Ngoài ra, production nên dùng `Plugin.class.isAssignableFrom(type)` và cast có kiểm soát để bảo đảm API plugin, thay vì trả `Object`.

Các lỗi có thể gặp:
- `ClassNotFoundException`: loader không tìm implementation class.
- `NoClassDefFoundError`: plugin class tìm được nhưng dependency của nó thiếu.
- `ClassCastException`: API `Plugin` được nạp từ hai classloader khác nhau, cho hai class identity không tương thích.
- `InvocationTargetException` hoặc initializer/linkage error: constructor/static initialization/provider logic thất bại.
- `ServiceConfigurationError`: SPI metadata/provider cấu hình sai.

Khắc phục đúng cần quản lý classloader delegation, API sharing, dependency isolation và lifecycle. Không chỉ chuyển mọi JAR sang system classpath, vì điều đó có thể phá plugin isolation.

## 34. ClassNotFoundException không luôn ném từ Class.forName

Những API có thể liên quan:
- `Class.forName(String)`.
- `Class.forName(String, boolean, ClassLoader)`.
- `ClassLoader.loadClass(String)`.
- Reflection/framework utilities gọi nạp class theo tên.
- JDBC driver/plugin code sử dụng tên driver/provider từ cấu hình.

Một số framework bắt `ClassNotFoundException` rồi bọc lại:

```text
org.example.ConfigurationException:
    Cannot create datasource provider
Caused by: java.lang.ClassNotFoundException:
    com.vendor.jdbc.Driver
```

Do đó, exception top-level có thể không mang tên `ClassNotFoundException`. Phải đọc cause chain để hiểu **class nào**, **loader nào** và **đường code nào** dẫn tới lỗi.

Mặt khác, gọi literal như `SomeClass.class` hay `new SomeClass()` không có nghĩa compiler buộc bạn khai báo `throws ClassNotFoundException`. JVM sẽ sử dụng cơ chế resolution của bytecode và những linkage failures tương ứng.

## 35. Tái hiện lỗi từ môi trường sạch

Một reproduction đáng tin cậy cần loại bỏ các yếu tố “đang chạy được vì máy developer có sẵn thư viện”:

1. Dùng fresh/clean build output và pinned dependencies.
2. Ghi đúng JDK version và vendor.
3. Sử dụng launcher như production: `java -jar`, classpath hay module path.
4. Chạy artifact đóng gói, không chạy trực tiếp từ IDE.
5. Dùng image tương ứng về OS/architecture.
6. Cung cấp config/env cần thiết nhưng không dùng production secrets.
7. Kích hoạt đúng đường code: endpoint, job, SPI provider hoặc static initialization.
8. Lưu full stack trace và phiên bản artifact.
9. So bản chạy lỗi với bản chạy được theo **một biến** tại một thời điểm.
10. Chuyển reproduction thành integration/regression test khi phù hợp.

Không cần chạy thử toàn bộ hệ thống sản xuất chỉ để tìm missing class nếu có thể tạo một test nhỏ mô phỏng đủ classloader/module path; nhưng một bản sửa phải được xác minh trên image/runtime đích trước release.

## 36. Cách làm integration test phòng ngừa hồi quy

Một số tests nên bổ sung sau khi đã sửa:

| Test | Mục tiêu |
|---|---|
| Packaged JAR startup | Chứng minh launcher và runtime classpath hợp lệ. |
| WAR/container deployment | Chứng minh API/container/provider tương thích. |
| Plugin discovery | Chứng minh loader/TCCL/SPI metadata đúng. |
| JAXB/JSON round trip | Chứng minh API và implementation runtime hoạt động. |
| Class initialization | Chứng minh static config/resources đầy đủ. |
| ServiceLoader/provider iteration | Chứng minh provider có trong runtime image. |
| JDK matrix | Chứng minh chạy trên baseline JDK đã cam kết. |
| Custom jlink image smoke/integration | Chứng minh Java modules/providers cần thiết hiện diện. |
| Native code path | Chứng minh binary phù hợp container/OS/architecture. |
| Scheduled/rare job | Chứng minh đường classload ít dùng đã được thực thi. |

Một test chỉ kiểm tra:

```java
assertNotNull(com.example.App.class);
```

không đủ để bảo đảm mọi dependency và initializer của app hoạt động. Cần thực hiện **hành vi** chạm tới đường classloading bị lỗi, đặc biệt với dependency optional hoặc reflection.

## 37. Đừng chữa lỗi bằng cách bắt Throwable rồi bỏ qua

Một anti-pattern:

```java
try {
    startApplication();
} catch (Throwable ignored) {
    // continue startup
}
```

Cách này có thể làm ứng dụng báo ready trong khi những thành phần quan trọng đã thất bại, và che cả các `Error` nghiêm trọng.

Có những hệ plugin thật sự cần xử lý lỗi để cô lập plugin không thiết yếu. Khi đó:
- Chỉ bắt ở **ranh giới plugin** đã được thiết kế để cô lập.
- Ghi loại lỗi và nguyên nhân đầy đủ vào hệ thống log an toàn.
- Đánh dấu plugin không khả dụng, không báo thành công giả.
- Không tiếp tục sử dụng class từng khởi tạo lỗi trong cùng loader với giả định nó đã tự hồi phục.
- Không nuốt `OutOfMemoryError`/các lỗi nghiêm trọng rồi tiếp tục bình thường.
- Định nghĩa rõ policy đối với plugin bắt buộc so với plugin tùy chọn.

Đối với service cốt lõi, **fail fast và rollback/forward-fix** thường an toàn hơn.

## 38. Bảng quyết định nhanh khi có lỗi

| Thông báo đầu tiên/quan trọng | Nghi vấn ưu tiên | Việc làm trước |
|---|---|---|
| `ClassNotFoundException: x.Y` | Loader không thấy class được yêu cầu bằng tên. | Xem name, classloader, classpath và artifact. |
| `NoClassDefFoundError: x/Y` | Dependency/definition bị thiếu khi linkage. | Tìm class provider và runtime packaging. |
| `NoClassDefFoundError: Could not initialize class X` | Class đã khởi tạo thất bại. | Tìm lỗi gốc `ExceptionInInitializerError` hoặc `Error` ban đầu. |
| `NoClassDefFoundError: wrong name` | Binary name/path mismatch. | Rebuild artifact, kiểm tra shading/renaming. |
| `ClassNotFoundException: javax.xml.bind...` sau Java 11 | JAXB không còn được JDK tự cung cấp. | Khai báo đúng API/provider artifact. |
| `NoClassDefFoundError: javax/servlet/...` sau Jakarta migration | Thư viện cũ dùng javax trên runtime jakarta. | Nâng nhóm web/library/container. |
| `NoClassDefFoundError: jakarta/servlet/...` | Runtime/container chưa có Jakarta API đúng. | Kiểm tra Servlet runtime và scopes. |
| `FindException: Module ... not found` | Module graph không resolve. | Kiểm tra module path/image/module-info. |
| `InaccessibleObjectException` | Reflection bị module chặn. | Nâng thư viện, xem `opens`/workaround đúng phạm vi. |
| `UnsupportedClassVersionError` | Runtime JDK thấp hơn class file yêu cầu. | So major version và release target. |
| `NoSuchMethodError` | Dependency binary API mismatch. | So versions/classpath và method descriptor. |
| `UnsatisfiedLinkError` | Native library/ABI/architecture thiếu. | Kiểm tra native packaging, OS và linker. |
| `ServiceConfigurationError` | SPI provider discovery/initialization lỗi. | Xem service metadata và provider/module visibility. |

Bảng là **định hướng**. Thông báo có thể được framework bọc trong các exception khác, và một hệ thống có thể gặp đồng thời nhiều nguyên nhân.

## 39. Mẫu ghi nhận một sự cố để người khác tái hiện

```yaml
incident: JAVA-COMPAT-CLASSLOAD-001
component: reporting-worker
artifact: reporting-worker.jar
release: "example-release-id"
jdk:
  version: "17"
  vendor: "example-distribution"
runtime:
  launcher: "java -jar reporting-worker.jar"
  packaging: "container"
exception:
  topLevel: "java.lang.NoClassDefFoundError"
  message: "com/example/codec/ReportCodec"
  rootCause: "ClassNotFoundException"
observedAt:
  action: "scheduled report export"
  environment: "staging"
evidence:
  - "full stack trace (secrets redacted)"
  - "runtime dependency tree"
  - "deployed artifact inventory"
suspectedCause:
  kind: "runtime dependency omitted"
resolution:
  type: "build packaging fix"
  tests:
    - "packaged-jar-startup"
    - "report-export-integration"
owner: "reporting-team"
status: "investigating"
```

Đây là ví dụ biên bản chẩn đoán, không phải định dạng bắt buộc của JVM hoặc công cụ nào. Thay placeholders bằng dữ liệu thật; không đưa password, token hoặc thông tin nhạy cảm trong logs, config hay ticket công khai.

## 40. Quy trình migration phòng ngừa classloading failures

### Bước 1 — Chốt baseline và đích

Ghi JDK nguồn/đích, minimum supported runtime, framework/BOM/Servlet container và packaging. Với Java EE/Jakarta phải xác định rõ namespace API đích.

### Bước 2 — Kiểm kê dependency theo runtime

So compile/test/runtime graphs. Phân biệt `compileOnly`, `provided`, `runtimeOnly`, optional dependencies và service providers. Ghi rõ JAR nào được container cung cấp.

### Bước 3 — Nâng các thư viện liên kết chặt

Ví dụ Servlet/REST/CDI/JPA provider, annotation processors, bytecode libraries và native integrations. Không chỉ đổi import trong application rồi giữ implementation cũ.

### Bước 4 — Chốt cách chạy

Lựa chọn `java -jar`, classpath hoặc module path đúng artifact. Với Spring Boot executable JAR, dùng launcher được plugin cung cấp. Với custom jlink image, xác nhận modules/providers đã link.

### Bước 5 — Kiểm thử các đường nạp động

Chạy ServiceLoader, reflection, plugin loading, serialization/JAXB, scheduled jobs và các logic có static initialization; unit tests thông thường có thể chưa chạm tới chúng.

### Bước 6 — Kiểm chứng trên runtime/image thực tế

Chạy integration tests trong container/server tương tự production, không chỉ IDE. Đo classloading/initialization failures và so JDK runtime versions.

### Bước 7 — Gỡ workaround có kiểm soát

Nếu có flags tạm, dependency overrides hoặc API JAR cũ được thêm trong quá trình migration, xác định nguyên nhân gốc và điều kiện gỡ. Đừng giữ workaround mãi chỉ vì nó làm lỗi biến mất trên một môi trường.

### Bước 8 — Release/rollback và quan sát

Lưu artifact checksum, Java version, dependency graph, logs đã khử secrets, người chịu trách nhiệm, canary metrics và phương án rollback. Một thay đổi packaging có thể yêu cầu rollback cả container image chứ không chỉ JAR.

## 41. Những ngộ nhận cần tránh

**“ClassNotFoundException và NoClassDefFoundError giống nhau.”** Không. Khác nhánh `Throwable`, cơ chế kích hoạt và cách chẩn đoán.

**“NoClassDefFoundError luôn là JAR bị thiếu.”** Không. Có thể là class initialization đã thất bại hoặc binary name sai.

**“Class file có trong JAR nghĩa là JVM luôn load được.”** Không. Loader visibility, module resolution/access và format của artifact cũng quan trọng.

**“Maven/Gradle build xanh chứng minh production classpath đủ.”** Không. Test runtime có thể chứa dependency khác production package.

**“Thấy ClassNotFoundException trong Caused by thì chỉ cần thêm JAR.”** Chưa chắc. Có thể JAR có nhưng nằm ở loader khác, module không resolve hoặc cách launch sai.

**“Cứ thêm javax và jakarta API vào chung classpath.”** Không khắc phục sự khác nhau của Java type identity; cần chọn runtime/framework thế hệ tương thích.

**“Dùng --add-opens để sửa class không tìm thấy.”** Không. Flag này dành cho module reflective access, không tạo class missing.

**“Xóa hết cache/local build sẽ tự sửa.”** Clean build có thể phơi bày nguyên nhân thật; cần fix dependency/packaging, không chỉ xóa cache.

**“Cứ bắt Throwable rồi tiếp tục.”** Có thể che lỗi khởi tạo nghiêm trọng và tạo trạng thái ứng dụng giả khỏe.

**“Chạy một endpoint là đủ xác nhận mọi class tải được.”** Dependency dynamic, plugin, scheduled job và đường exception có thể chưa được kích hoạt.

## 42. Checklist chẩn đoán và nghiệm thu

- [ ] Đã ghi chính xác exception type, message, stack trace và toàn bộ cause chain.
- [ ] Đã phân biệt missing definition với `Could not initialize class`.
- [ ] Nếu initialization lỗi, đã tìm thất bại **đầu tiên**.
- [ ] Đã xác định binary name và file `.class` tương ứng, kể cả nested class.
- [ ] Đã xác định class/provider artifact lẽ ra chứa class.
- [ ] Đã xem artifact **được triển khai**, không chỉ build output local.
- [ ] Đã kiểm tra Maven/Gradle scopes, exclusions, BOM và runtime graph.
- [ ] Đã so test classpath với production runtime classpath.
- [ ] Đã kiểm tra launcher: `java -jar`, classpath, module path, WAR/container.
- [ ] Đã ghi JDK runtime version, vendor, module list và container image.
- [ ] Đã kiểm tra classloader/TCCL visibility khi có plugin/server isolation.
- [ ] Đã phân biệt `javax`/`jakarta`, JDK 11 JAXB removals và các API Java SE còn giữ `javax`.
- [ ] Đã kiểm tra SPI service files, JPMS `uses`/`provides`, `jlink` nếu liên quan.
- [ ] Đã kiểm tra generated code/annotation processing nếu class do generator tạo.
- [ ] Đã phân biệt lỗi binary API/version/native với lỗi class absent.
- [ ] Đã dùng `jar`, `javap`, `jdeps` và JVM class-load logs khi phù hợp.
- [ ] Đã tái hiện trên image/launcher gần production.
- [ ] Không dùng thêm JAR ngẫu nhiên, `--add-opens` vô cớ hoặc nuốt `Throwable` để che lỗi.
- [ ] Có integration/regression test chạm đúng đường classloading từng thất bại.
- [ ] Đã ghi owner, bằng chứng và rollback/forward-fix plan.

## 43. Tài liệu tham khảo

- [Java SE API — ClassNotFoundException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassNotFoundException.html): định nghĩa checked exception và các trường hợp class loading theo tên.
- [Java SE API — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NoClassDefFoundError.html): định nghĩa lỗi không tìm thấy definition của class mà JVM/classloader cần.
- [Java SE API — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ExceptionInInitializerError.html): exception xảy ra trong static initialization.
- [Java SE API — LinkageError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/LinkageError.html): nhóm linkage errors trong JVM.
- [Java Virtual Machine Specification, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): loading, linking, initialization và module/classloader semantics.
- [Java Language Specification — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): các điều kiện kích hoạt class initialization.
- [ClassLoader API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, resource lookup và classloader behavior.
- [Class API — forName](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): nạp class theo tên và tùy chọn initialize/classloader.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS, module resolution, module path.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): lý do JAXB/JAX-WS API không còn được JDK 11 cung cấp sẵn.
- [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): runtime image và thay đổi layout `rt.jar`/`tools.jar`.
- [JDK 21 jdeps Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): phân tích class/module dependencies.
- [JDK 21 javap Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): inspect bytecode và class file metadata.
- [JDK 21 Java Launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): classpath, module path và JVM diagnostics options.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xác định resolved runtime dependencies.
- [Gradle Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): runtimeClasspath và dependencyInsight.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/): API namespace/version cần đối chiếu khi chuyển Java EE sang Jakarta.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/): packaging, executable JAR và framework/runtime dependency management.

## Kết luận

**ClassNotFoundException** thường cho biết một lời gọi tìm/nạp lớp theo tên không tìm được class trong phạm vi classloader được sử dụng. **NoClassDefFoundError** là lỗi liên kết/khởi tạo ở runtime: nó có thể phát sinh khi JVM cần một class definition không có mặt, khi tên binary không khớp, hoặc khi class đã khởi tạo thất bại và bị đánh dấu erroneous. Vì thế, hai lỗi có thể có chung nguyên nhân là runtime classpath thiếu một dependency nhưng cũng có thể cần hướng sửa hoàn toàn khác.

Trong Java migration, hãy bắt đầu bằng **toàn bộ cause chain**, xác định giai đoạn load–link–initialize và process/classloader thực sự bị lỗi. Sau đó kiểm tra artifact đã triển khai, Maven/Gradle runtime graph, classpath/module path, JDK/Jakarta compatibility, ServiceLoader, generated code và native libraries. Tái hiện bằng đúng launcher/runtime image, sửa nguyên nhân thay vì thêm JAR hoặc mở module vô tội vạ, rồi khóa kết quả bằng integration tests và evidence cho lần triển khai tiếp theo.





