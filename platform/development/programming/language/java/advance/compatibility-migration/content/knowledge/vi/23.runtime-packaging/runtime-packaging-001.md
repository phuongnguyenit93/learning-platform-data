# Cấu trúc JDK sau phiên bản 8 và sự thay đổi của rt.jar hoặc tools.jar

Khi nâng từ Java 8 lên Java 11, 17, 21 hoặc mới hơn, lỗi có thể xuất hiện ngay trong script/build: một plugin tìm `lib/tools.jar`, một IDE mở `jre/lib/rt.jar`, hoặc Dockerfile copy thư mục `jre/` bên trong JDK. Những đường dẫn đó từng tồn tại trên JDK 8 nhưng không còn phù hợp từ JDK 9.

**JEP 220 – Modular Run-Time Images** và **JPMS (Java Platform Module System)** thay đổi cách tổ chức các thành phần nền tảng. Các class Java SE và compiler vẫn hiện diện trong những JDK phù hợp, nhưng không còn được đóng gói thành `rt.jar` và `tools.jar`. Thay vào đó là modular runtime images, các module như `java.base` và `jdk.compiler`, cùng cách truy cập tài nguyên `jrt:`.

Bài học phân biệt layout trước/sau JDK 8, vai trò của `lib/modules`, `jmods`, `jimage`, `jlink`; hướng dẫn sửa Maven/Gradle/Dockerfile, lựa chọn Java Compiler API, chẩn đoán class loader và xác minh môi trường chạy trong quá trình Java Advance Compatibility Migration.

## 1. JDK, JRE và runtime image không đồng nghĩa

- **JDK:** một bộ phân phối gồm runtime Java và các công cụ phát triển, chẳng hạn `java`, `javac`, `jar` và `javadoc`.
- **JRE:** môi trường có thể chạy chương trình Java; không nhất thiết chứa compiler/tooling.
- **Runtime image:** tập tin, native libraries, module data và launcher tạo thành một môi trường chạy cụ thể, có thể do JDK cung cấp hoặc được tùy chỉnh bằng `jlink`.

Một JDK có thể chứa runtime mà **không có thư mục con tên `jre`**. Khi nâng từ JDK 8, điều cần kiểm tra là Java executable, module availability và version thực tế, thay vì bắt buộc có một đường dẫn kiểu `jdk/jre/lib/rt.jar`.

## 2. Cấu trúc JDK 8 điển hình

```text
jdk8/
├── bin/
│   ├── java
│   ├── javac
│   └── jar
├── include/
├── lib/
│   ├── tools.jar
│   └── dt.jar
└── jre/
    ├── bin/java
    └── lib/
        ├── rt.jar
        ├── resources.jar
        ├── charsets.jar
        ├── ext/
        └── security/
```

Sơ đồ khái niệm; các bản vendor và hệ điều hành có thể khác ở native libraries và file bổ sung.

| File/thư mục | Vai trò truyền thống |
|---|---|
| `jre/lib/rt.jar` | Chứa nhiều Java SE runtime classes/resources. |
| `lib/tools.jar` | Chứa nhiều implementation classes của các công cụ JDK, nhất là compiler. |
| `jre/lib/ext/` | Extension mechanism cũ, cho phép nạp extensions theo vị trí đặc biệt. |
| `lib/endorsed/` | Cơ chế endorsed standards override trước Java 9. |
| `jre/lib/security/` | Một số cấu hình và dữ liệu bảo mật. |
| `bin/java`, `bin/javac` | Launcher và compiler. |

Script legacy thường kiểm tra:

```bash
test -f "${JAVA_HOME}/jre/lib/rt.jar"
test -f "${JAVA_HOME}/lib/tools.jar"
```

Đây là kiểm tra file vật lý đặc thù của JDK 8, **không phải cách xác định liệu JDK hiện đại có hỗ trợ Java hay có compiler**.

## 3. rt.jar từng được sử dụng như thế nào?

Trên JDK 8, nhiều class Java SE nằm trong `rt.jar`. Ví dụ:

```java
import java.net.URL;

public class LocatePlatformClass {
    public static void main(String[] args) {
        URL location = ClassLoader.getSystemResource(
                "java/lang/Class.class");
        System.out.println(location);
    }
}
```

Kết quả điển hình trên JDK 8:

```text
jar:file:/opt/jdk8/jre/lib/rt.jar!/java/lang/Class.class
```

Một số tool cũ lợi dụng đường dẫn này để:
- Duyệt class nền tảng bằng `JarFile` hoặc `ZipFile`.
- Copy `rt.jar` vào artifact ứng dụng.
- Tạo source/API index cho IDE.
- Suy ra JDK location từ resource URL.
- Thêm `rt.jar` vào classpath/bootclasspath để biên dịch.

Những cách làm này phụ thuộc vào **chi tiết đóng gói**. Ứng dụng thông thường không cần khai báo `rt.jar` để sử dụng `java.lang`, `java.util` hoặc các Java SE APIs được hỗ trợ.

## 4. tools.jar và cấu hình Maven đời cũ

Một cấu hình legacy thường thấy:

```xml
<dependency>
    <groupId>jdk.tools</groupId>
    <artifactId>jdk.tools</artifactId>
    <version>1.8</version>
    <scope>system</scope>
    <systemPath>${java.home}/../lib/tools.jar</systemPath>
</dependency>
```

Trên JDK 8, `java.home` của tiến trình chạy trong JDK có thể trỏ tới `jdk8/jre`, nên `../lib/tools.jar` tình cờ đúng. Sang JDK 9+, `java.home` thường trỏ tới gốc runtime image và file `tools.jar` không còn. Build có thể lỗi dù `javac` vẫn hoạt động.

Không nên giải quyết bằng cách copy `tools.jar` cũ hoặc tạo artifact giả mang tên `jdk.tools`. Phải xác định chính xác plugin/code cần compiler API hay các implementation internals rồi chuyển sang cách được hỗ trợ.

## 5. JDK 9 sử dụng modular run-time images

JEP 220 thay đổi cấu trúc runtime từ Java 9:

- Các class/resource nền tảng được chứa trong **module image**, không còn JAR nội bộ `rt.jar`, `tools.jar`, `dt.jar` theo kiểu cũ.
- Ở nhiều bản OpenJDK, module data nằm trong `lib/modules`; đây là format implementation-specific, **không phải ZIP/JAR**.
- URI `jrt:` và JRT filesystem cho phép truy cập class/resource trong image mà không cần mở file vật lý.
- Cấu hình dùng cho người vận hành được bố trí rõ hơn dưới `conf/`.
- Các tools và APIs được phân thành các module phù hợp như `jdk.compiler` và `jdk.jlink`.

Sai lầm cần tránh:

```text
rt.jar -> java.base.jar        (không phải quy tắc chuyển đổi)
tools.jar -> jdk.compiler.jar (không tồn tại như JAR thay thế cố định)
```

Không nên mở `lib/modules` bằng `JarFile` hoặc thêm nó vào classpath như một dependency.

## 6. JDK 9–10 so với JDK 11 trở đi

| Giai đoạn | Runtime packaging | Điều cần ghi nhớ |
|---|---|---|
| Java 8 trở về trước | JDK thường chứa JRE con ở `jdk/jre/`; JRE cũng có thể tải riêng. | `rt.jar` trong JRE, `tools.jar` trong JDK. |
| JDK 9–10 | Oracle từng phân phối JDK/JRE modular images riêng, không còn JRE lồng trong JDK theo layout cũ. | Cùng dạng cấu trúc `bin/`, `conf/`, `lib/`. |
| JDK 11+ | Oracle JDK không còn JRE tải riêng theo hình thức cũ, nhưng JDK vẫn chứa runtime; có thể tạo image riêng. | Không hardcode `jdk/jre`, `rt.jar`, `tools.jar`. |
| Bản phân phối khác | Vendor có thể phát hành runtime package/custom image riêng. | Kiểm tra thực tế từng vendor/version và license. |

“JDK 11 không có JRE” là diễn đạt thiếu chính xác nếu hiểu là **không thể chạy Java**. Cách đúng: không còn phân phối JRE độc lập theo mô hình Oracle cũ, nhưng runtime vẫn nằm trong JDK hoặc custom image.

## 7. Cấu trúc JDK hiện đại điển hình

```text
jdk-21/
├── bin/
│   ├── java
│   ├── javac
│   ├── jar
│   ├── jdeps
│   ├── jlink
│   ├── jmod
│   └── jimage
├── conf/
│   └── security/
│       └── java.security
├── include/
├── jmods/
│   ├── java.base.jmod
│   ├── java.logging.jmod
│   └── jdk.compiler.jmod
├── legal/
└── lib/
    ├── modules
    ├── src.zip
    └── ...
```

Đây là ví dụ JDK đầy đủ; custom runtime có thể không có `javac`, `jmods/` hoặc `src.zip`.

| Đường dẫn | Vai trò | Hạn chế |
|---|---|---|
| `bin/` | Executables sẵn có trong image. | Không giả định mọi công cụ tồn tại trong jlink image. |
| `conf/` | File cấu hình người triển khai có thể chỉnh sửa. | Không tự suy vị trí truststore từ layout cũ. |
| `lib/modules` | Dữ liệu module đã link trong runtime. | Không phải JAR hoặc classpath entry. |
| `jmods/` | JMOD đầu vào cho linker/công cụ. | Không dùng như runtime JAR. |
| `include/` | Header native/JNI. | Không nhất thiết có ở runtime tối giản. |
| `lib/src.zip` | Source code để đọc/debug khi phân phối có cung cấp. | Không cần cho việc chạy ứng dụng. |
| `legal/` | Notices/license. | Cần quan tâm khi phân phối image. |

## 8. Các module phân chia những gì trước đây nằm trong JAR nội bộ?

| Vai trò | Module điển hình | Ví dụ |
|---|---|---|
| Nền tảng cơ bản | `java.base` | `java.lang`, `java.util`, I/O. |
| Logging | `java.logging` | `java.util.logging`. |
| JDBC | `java.sql` | `java.sql.Connection`. |
| XML | `java.xml` | DOM, SAX, JAXP. |
| Compiler API chuẩn | `java.compiler` | `javax.tools.JavaCompiler`. |
| Compiler implementation | `jdk.compiler` | `javac` và nhiều implementation classes. |
| Javadoc | `jdk.javadoc` | `javadoc`. |
| Dependency analysis | `jdk.jdeps` | `jdeps`. |
| Runtime image tools | `jdk.jlink` | `jlink`, `jmod`, `jimage`. |
| Attach tools | `jdk.attach` | `com.sun.tools.attach.VirtualMachine`. |

**Tên package không giống tên module**. Ví dụ `javax.tools` vẫn là Java SE Compiler API, không phải package Jakarta; không thay `javax.*` hàng loạt.

## 9. Kiểm tra module có trong JDK/image

```bash
java --list-modules
java --describe-module java.base
java --describe-module jdk.compiler
```

Một phần kết quả `--list-modules` trên JDK 21 có thể là:

```text
java.base@21
java.compiler@21
java.logging@21
java.sql@21
jdk.compiler@21
jdk.jlink@21
```

Danh sách phụ thuộc image; custom runtime có thể chứa ít module hơn. Nếu không thấy module cần dùng, không thể khắc phục bằng cách tự tạo một `rt.jar`.

## 10. jrt: thay cho jar:file: khi đọc class nền tảng

Với chương trình:

```java
System.out.println(
    ClassLoader.getSystemResource("java/lang/Class.class"));
```

JDK 8 có thể trả:

```text
jar:file:/opt/jdk8/jre/lib/rt.jar!/java/lang/Class.class
```

JDK 9+ có thể trả:

```text
jrt:/java.base/java/lang/Class.class
```

Một `JarURLConnection` cast như:

```java
URL location = ClassLoader.getSystemResource(
    "java/lang/Class.class");
java.net.JarURLConnection jar =
    (java.net.JarURLConnection) location.openConnection();
```

có thể thất bại trên JDK 9+, vì URL không còn dùng `jar:`. Hướng sửa:
- Muốn đọc một resource: dùng `getResourceAsStream` hoặc mở URL stream.
- Muốn biết module chứa class: dùng `Class.getModule()`.
- Muốn duyệt platform classes: dùng JRT filesystem.
- Muốn kiểm tra API Java SE hỗ trợ: dùng compiler/Javadoc thay vì quét JAR vật lý.

## 11. JRT filesystem qua java.nio.file

```java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;

public class JrtReader {
    public static void main(String[] args) throws Exception {
        FileSystem fs = FileSystems.getFileSystem(
            URI.create("jrt:/"));
        Path classFile = fs.getPath(
            "/modules/java.base/java/lang/Object.class");
        System.out.println(Files.exists(classFile));
        System.out.println(Files.size(classFile));
    }
}
```

Trên JDK 9+, đường dẫn `/modules/java.base/...` là đường dẫn **logic bên trong JRT filesystem**, không phải thư mục thực `${JAVA_HOME}/modules/java.base`.

Đừng nhầm:
- URI resource `jrt:/java.base/java/lang/Object.class`.
- NIO JRT path `/modules/java.base/java/lang/Object.class`.

Ứng dụng nghiệp vụ thường không cần quét toàn bộ nền tảng; phương án này chủ yếu dành cho IDE hoặc công cụ phân tích class.

## 12. jimage, jmods và lib/modules

Trên full JDK, xem image:

```bash
jimage list "$JAVA_HOME/lib/modules"
```

Trên Windows PowerShell, có thể gọi một dòng:

```powershell
& "$env:JAVA_HOME\bin\jimage.exe" list "$env:JAVA_HOME\lib\modules"
```

Kiểm tra một JMOD:

```bash
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
```

| Thành phần | Công dụng |
|---|---|
| `lib/modules` | Dữ liệu module runtime mà JVM sử dụng. |
| `jmods/*.jmod` | Artifacts thường dùng làm đầu vào cho `jlink`. |
| `app.jar` | JAR ứng dụng; `java -jar` vẫn được hỗ trợ. |

JMOD không phải một JAR để thêm vào `-cp`. Cũng không có yêu cầu `jimage`/`jmod` xuất hiện trong image rút gọn chỉ dùng để chạy chương trình.
## 13. Thay tools.jar bằng Java Compiler API được hỗ trợ

Nếu ứng dụng cần biên dịch source Java khi chạy, đừng thêm `tools.jar` thủ công. API chuẩn là `javax.tools` trong module `java.compiler`:

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class EmbeddedCompiler {
    public static void main(String[] args) {
        JavaCompiler compiler =
            ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            throw new IllegalStateException(
                "No system Java compiler in this runtime");
        }

        int result = compiler.run(
            null, System.out, System.err, "Hello.java");

        if (result != 0) {
            throw new IllegalStateException(
                "javac exited with " + result);
        }
    }
}
```

Ví dụ giả định có file `Hello.java` trong working directory. Chương trình phải được chạy trên runtime image có compiler implementation.

Trên JDK 9+:
- `java.compiler` cung cấp API chuẩn cho code ứng dụng.
- `jdk.compiler` cung cấp compiler implementation trong JDK.
- Một custom runtime image chỉ có `java.base` có thể khiến `ToolProvider.getSystemJavaCompiler()` trả về `null`.

Vì thế không phải cứ có `bin/java` thì có compiler. Nếu ứng dụng phát sinh Java source tại runtime, hãy đưa compiler module/toolchain vào deployment một cách có chủ đích hoặc tách bước biên dịch sang build service.

### 13.1. Không nhầm compiler API với compiler internals

Code dùng `com.sun.tools.javac.*` có thể gặp lỗi từ Java 9 dù `jdk.compiler` vẫn hiện diện, vì nhiều package implementation không được `exports` công khai. Một số API khác như Attach API có module riêng `jdk.attach`.

Không có quy tắc “import class nào trước đây từ tools.jar thì chỉ cần thêm `requires jdk.compiler`”. Cần xem từng class và mức hỗ trợ. Ưu tiên API chính thức, nâng plugin/annotation processor, tránh duy trì `--add-exports` như phương án dài hạn.

## 14. java.home khác JAVA_HOME

Hai giá trị hay bị nhầm:
- `JAVA_HOME` là environment variable do người dùng, shell, CI hoặc build tool quản lý.
- `java.home` là JVM system property mô tả Java runtime image của process đang chạy.

Kiểm tra trực tiếp:

```java
public class RuntimeHome {
    public static void main(String[] args) {
        System.out.println("JAVA_HOME = "
            + System.getenv("JAVA_HOME"));
        System.out.println("java.home = "
            + System.getProperty("java.home"));
        System.out.println("java.version = "
            + System.getProperty("java.version"));
    }
}
```

Ở JDK 8, `java.home` của một tiến trình chạy từ JDK thường trỏ tới JRE con. Ở JDK 9+, nó thường trỏ tới gốc runtime image. Còn `JAVA_HOME` có thể chỉ đến **JDK khác** với JVM thực sự đang chạy.

Không dùng `java.home + "/../lib/tools.jar"` để phát hiện compiler. Dùng `ToolProvider.getSystemJavaCompiler()` hoặc cấu hình toolchain/JDK executable rõ ràng.

## 15. Class loader thay đổi sau JPMS

JDK 9+ thay đổi implementation class loader:
- Application/system class loader không còn được bảo đảm là `URLClassLoader`.
- Extension class loader kiểu JDK 8 được thay bằng khái niệm **platform class loader**.
- Không nên giả định mọi Java SE class đều được định nghĩa bởi bootstrap class loader.
- Class/module resolution và quyền truy cập `exports`, `opens` trở nên quan trọng.

Đoạn code legacy:

```java
import java.net.URLClassLoader;

public class CastSystemLoader {
    public static void main(String[] args) {
        URLClassLoader loader = (URLClassLoader)
            ClassLoader.getSystemClassLoader();
        System.out.println(loader.getURLs().length);
    }
}
```

có thể ném `ClassCastException` trên JDK 9+. Đừng dùng implementation type của system class loader như một hợp đồng.

Với Java 9+, có API:

```java
ClassLoader platform =
    ClassLoader.getPlatformClassLoader();
```

Nhưng không nên giả định mọi platform class được định nghĩa bởi loader đó. Nếu cần load plugin JAR riêng, ứng dụng có thể tạo và quản lý một `URLClassLoader` của **chính mình** thay vì cast system loader.

## 16. Lấy thông tin module chứa class

Thay vì suy từ `rt.jar`:

```java
public class ClassModules {
    public static void main(String[] args) {
        System.out.println(String.class.getModule().getName());
        System.out.println(
            java.sql.Connection.class.getModule().getName());
    }
}
```

Trên JDK 9+ có thể in:

```text
java.base
java.sql
```

`Class.getModule()` là API từ Java 9. Nếu cần tiếp tục biên dịch tương thích Java 8, phải thiết kế một đường code khác hoặc dùng cơ chế phản chiếu khi thật cần thiết.

## 17. Classpath vẫn chạy bình thường

Việc có JPMS không bắt buộc mọi ứng dụng phải trở thành named module.

Ứng dụng truyền thống:

```bash
java -cp "app.jar:libs/*" com.example.Main
```

Trên Windows classpath thường dùng dấu chấm phẩy:

```powershell
java -cp "app.jar;libs/*" com.example.Main
```

Những class trên classpath thuộc **unnamed module**. Java vẫn cung cấp các Java SE modules tương ứng theo quy tắc resolution. Không cần thêm `rt.jar` hay `tools.jar` vào classpath.

Ứng dụng modular:

```bash
java --module-path mods \
  --module com.example.app/com.example.Main
```

Có thể dùng named modules, automatic modules và classpath cùng nhau trong một số kiến trúc, nhưng phải xử lý package/module conflicts và module graph. Chuyển sang module path không phải phép thay thế trực tiếp cho mọi đường dẫn classpath cũ.

## 18. Extension mechanism và endorsed standards đã bị loại

Trên Java 8, `jre/lib/ext/`, `java.ext.dirs`, `lib/endorsed/` và `java.endorsed.dirs` có thể được dùng để nạp JAR hoặc ghi đè API theo cơ chế cũ.

Từ JDK 9, các cơ chế này bị loại bỏ. Nếu directory hoặc system property tương ứng vẫn tồn tại, launcher/compiler ở các bản được tài liệu hóa có thể từ chối khởi động hoặc báo lỗi.

Cách xử lý:
1. Xác định JAR nào trước đây nằm trong `ext/`.
2. Đưa nó vào dependency/classpath/module path được khai báo rõ.
3. Xóa thư mục và property cũ khỏi image và script khởi động.
4. Nếu từng dùng endorsed override, đánh giá cơ chế upgradeable modules hoặc cách thay thế API phù hợp với runtime đích.
5. Kiểm thử classloader và API compatibility sau chuyển.

Đừng dùng `-Xbootclasspath/p` để thêm class nền tảng từ JDK 8 vào JDK mới. Các cơ chế bootclasspath prepend cũ không còn được hỗ trợ như trước. Các cờ `--patch-module`, `--add-opens` và `--add-exports` có mục tiêu riêng, không phải biện pháp thay thế extension mechanism chung.

## 19. Cấu hình security và conf/

Một số script JDK 8 dùng đường dẫn:

```text
${JAVA_HOME}/jre/lib/security/java.security
${JAVA_HOME}/jre/lib/security/java.policy
```

Sau modular image, những file cấu hình có thể chỉnh sửa thường nằm ở:

```text
${JAVA_HOME}/conf/security/java.security
${JAVA_HOME}/conf/security/java.policy
```

Không có nghĩa mọi file trong `lib/security/` đều chuyển vào `conf/security/`. Truststore, certificate data và security resources phụ thuộc vào JDK/version/vendor. Nếu cần truststore tùy chỉnh, nên dùng cấu hình JVM/app được hỗ trợ và quản lý nó như một artifact có lifecycle riêng.

Vì sao cần cẩn thận:
- Thay đổi security property có thể ảnh hưởng TLS, certificate path validation hoặc thuật toán.
- Copy file `java.security` từ JDK 8 sang JDK mới có thể ghi đè chính sách bảo mật hiện đại.
- Nếu image tạo bằng `jlink`, cấu hình và các security providers phải được kiểm chứng trong chính image đó.

## 20. Chọn javac và phân biệt compiler target với runtime

Dù `tools.jar` biến mất, full JDK vẫn có `javac`. Kiểm tra:

```bash
java -version
javac -version
```

Hai lệnh có thể chọn JDK khác nhau khi máy có nhiều Java installations. Maven/Gradle còn có thể dùng Toolchains để chọn compiler khác JVM chạy build.

Một sự cố thực tế:
- CI chạy Maven/Gradle trên JDK 21.
- Java source biên dịch theo target 17.
- Unit tests lại chạy trên JDK 21.
- Production dùng JDK 17.

Nếu không có test nào chạy trên Java 17, kết luận “đã tương thích Java 17” chưa có đủ bằng chứng.

### 20.1. Không tiếp tục dùng rt.jar làm bootclasspath

Một lệnh cũ:

```bash
javac -source 8 -target 8 \
  -bootclasspath /opt/jdk8/jre/lib/rt.jar \
  -d out src/com/example/Main.java
```

nên được thay trên javac hiện đại có hỗ trợ release đích:

```bash
javac --release 8 \
  -d out src/com/example/Main.java
```

Với target Java 17:

```bash
javac --release 17 \
  -d out src/com/example/Main.java
```

`--release` kiểm soát source level, class file target và API nền tảng có thể truy cập cho release tương ứng. Nó **không**:
- Tự thay đổi JVM chạy unit tests.
- Biến dependency đã biên dịch bằng Java mới hơn thành Java cũ.
- Mang `rt.jar` của JDK cũ trở lại.
- Cho phép mọi release tùy ý; compiler có khoảng release được hỗ trợ.

Kiểm tra `javac --help` và compatibility của dependencies.

## 21. Maven: bỏ tools.jar systemPath

Nếu POM khai báo:

```xml
<dependency>
    <groupId>jdk.tools</groupId>
    <artifactId>jdk.tools</artifactId>
    <version>1.8</version>
    <scope>system</scope>
    <systemPath>${java.home}/../lib/tools.jar</systemPath>
</dependency>
```

hãy tìm call site/plugin thực sự dùng nó rồi loại cấu hình giả định layout JDK.

Nếu mục tiêu là biên dịch source theo Java 17:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Nếu cần compiler JDK cụ thể khác JVM Maven, dùng Maven Toolchains khi plugin hỗ trợ. Không thêm `jdk.compiler.jmod` vào Maven dependencies để thay `tools.jar`.

Nếu annotation processor/plugin dùng trực tiếp `com.sun.tools.javac.*`, cần nâng plugin lên phiên bản tương thích JDK. Một số công cụ có thể tạm cần module export options, nhưng nên giới hạn phạm vi và có kế hoạch loại bỏ.

## 22. Gradle: Java Toolchains thay hardcoded đường dẫn

Ví dụ `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Test runtime có thể được chọn riêng:

```kotlin
tasks.test {
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
```

Các cấu hình này không dựa vào tên JAR nội bộ của JDK. Tuy nhiên, cần version Gradle hỗ trợ JVM chạy daemon và JDK được chọn làm toolchain; setting một JavaLanguageVersion không tự bảo đảm máy/runner đã cài JDK đó.

## 23. Strong encapsulation không phải lỗi thiếu rt.jar

Trên JDK hiện đại, có thể gặp:

```text
java.lang.reflect.InaccessibleObjectException:
  module java.base does not "opens java.lang" ...
```

Ở đây class **vẫn tồn tại**. Lỗi là module không cấp quyền deep reflection. Các thay đổi theo JEP 396/403 làm rõ và siết quyền truy cập JDK internals.

Phân biệt nguyên nhân:

| Dấu hiệu | Nguyên nhân khả dĩ | Xử lý |
|---|---|---|
| Không tìm được file `rt.jar` | Layout thay đổi từ JDK 9. | Xóa giả định file, dùng JRT/API. |
| Không tìm được `tools.jar` | Tooling chuyển sang modules. | Dùng `javax.tools`/Toolchains. |
| `InaccessibleObjectException` | JPMS chặn reflection. | Nâng library, dùng public API; workaround hẹp khi cần. |
| `ClassNotFoundException` | Dependency/module thiếu hoặc chưa resolve. | Kiểm tra runtime graph/classpath. |
| `NoSuchMethodError` | API/binary mismatch. | Xem resolved dependency versions. |

`--add-opens` có thể nới quyền reflection tạm thời nhưng **không khôi phục `rt.jar`**, và không thay thế việc sửa các phụ thuộc internals.

## 24. Những công cụ quét class nền tảng phải được cập nhật

Trước JDK 9, một IDE hoặc bytecode analyzer có thể làm:

```text
Read java.home
   -> find jre/lib/rt.jar
   -> open JarFile
   -> iterate *.class
```

Cách này không còn đúng trên modular image. Thay bằng:
- JRT filesystem cho việc duyệt classes/resources của image.
- `Class.getModule()` để xác định module của class.
- `ClassLoader.getResourceAsStream` cho resource đã biết.
- `jdeps` để phân tích dependencies.
- `javac --release`/Javadoc để kiểm tra public APIs.
- Bytecode libraries hỗ trợ class file format của JDK đích.

Thư viện như ASM, Byte Buddy, Javassist hoặc framework scanning cũ có thể thất bại thêm vì class file major version mới, ngay cả khi đường dẫn `rt.jar` đã được sửa. Cần nâng các thành phần này theo support matrix của JDK mục tiêu.
## 25. jlink: tạo runtime image thay vì copy JRE cũ

Từ JDK 9, công cụ `jlink` cho phép xây dựng một runtime image theo tập Java modules cần dùng. Ví dụ:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging \
  --output runtime-image
```

Sau đó:

```bash
./runtime-image/bin/java --list-modules
```

Runtime image thường có `bin/java` và `lib/modules` nhưng có thể không có `javac`, `jmods`, `jlink` hoặc Javadoc. Nó được thiết kế để **chạy** phần mềm, không nhất thiết dùng như một JDK phát triển đầy đủ.

Ví dụ trên **không đủ cho mọi ứng dụng**. Nếu chương trình cần JDBC, XML, crypto providers, nhiều ngôn ngữ/locale, JMX, native/JNI hoặc plugin động, cần điều chỉnh module graph và kiểm thử phù hợp.

### 25.1. Dùng jdeps để xác định module tĩnh

```bash
jdeps --print-module-deps \
  --class-path "libs/*" \
  app.jar
```

Output minh họa:

```text
java.base,java.logging,java.sql
```

Từ tập modules đã kiểm tra, có thể tạo image:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging,java.sql \
  --output runtime-app
```

`jdeps` chủ yếu phân tích **static references**. Nó không đảm bảo nhận diện mọi phụ thuộc được load bằng reflection, `ServiceLoader`, JDBC driver, crypto provider, plugin hoặc service configuration bên ngoài. Cần bổ sung modules theo chức năng thật và chạy integration tests trên **image cuối**, không chỉ trên JDK build.

### 25.2. Service providers và dữ liệu runtime

Tùy ứng dụng, có thể cần:
- `jdk.crypto.ec` cho một số cryptographic algorithms/protocols.
- `jdk.localedata` cho locale data mở rộng.
- `jdk.charsets` cho các charset bổ sung.
- `jdk.unsupported` nếu một số thư viện vẫn phụ thuộc các API được tiếp tục cung cấp ở đó.

Đây là các ví dụ cần **xác minh**, không phải danh sách bắt buộc cho mọi project. Tùy chọn `jlink --bind-services` có thể kéo thêm service providers và làm image lớn hơn. Một image thiếu provider có thể khởi động bình thường nhưng chỉ lỗi khi thực hiện TLS handshake, xử lý encoding hiếm hoặc gọi plugin.

### 25.3. Image là sản phẩm có vòng đời

Custom runtime phải được:
- Tạo từ đúng JDK vendor/version/build.
- Build cho đúng OS/CPU architecture.
- Kiểm tra native libraries và system dependencies.
- Ghi checksum/provenance.
- Cập nhật lại khi có JDK security patches.
- Kiểm thử cùng application artifact mới.

Giảm image size không tự động tạo ra một hệ thống an toàn nếu image bị bỏ quên không cập nhật.

## 26. Dockerfile và CI: bỏ giả định jdk/jre

Một Dockerfile legacy có thể chứa:

```dockerfile
# Mẫu cũ không phù hợp cho JDK 11+
COPY --from=builder /opt/java/jre /opt/java/jre
ENV JAVA_HOME=/opt/java/jre
ENTRYPOINT ["/opt/java/jre/bin/java", "-jar", "/app/app.jar"]
```

Nếu builder dùng JDK 17/21, `/opt/java/jre` không nhất thiết tồn tại.

Có hai cách phổ biến:

1. Sử dụng một runtime base image có hỗ trợ và cập nhật bảo mật theo vendor.
2. Dùng JDK đầy đủ ở build stage, tạo `jlink` runtime, copy **toàn bộ runtime image** vào runtime stage có OS/native dependencies tương thích.

Luồng khái niệm:

```text
JDK build stage
      |
      +--> compile/package app.jar
      |
      +--> jdeps -> select required modules
      |
      +--> jlink -> /opt/runtime
                         |
                         v
                Runtime container
                /opt/runtime/bin/java
                /app/app.jar
```

Các bẫy cần tránh:
- Build runtime trên Windows rồi copy sang Linux.
- Copy runtime được link cho kiến trúc CPU khác.
- Giữ image cũ khi ứng dụng đã nâng JDK/library.
- Loại bỏ CA certificates/TLS providers khiến HTTPS thất bại.
- Thiếu timezone, locale hoặc native libraries.
- Dùng `javac` trong runtime nhưng image chỉ có `java`.
- Tưởng container base image khác nhau chỉ khác kích thước, không ảnh hưởng glibc, fonts hay security policy.

Nếu dùng `jlink` cho ứng dụng chưa modular hóa, ứng dụng vẫn có thể được triển khai trên classpath nếu runtime image chứa đủ Java modules. Không bắt buộc phải có `module-info.java` trong mọi JAR ứng dụng để dùng một runtime rút gọn.

## 27. Java launcher và java.home: cách xác minh đúng tiến trình

Một CI agent có thể có nhiều JDK, nên các lệnh:

```bash
java -version
javac -version
```

chưa chắc cùng chỉ tới một installation. Trong Maven/Gradle, compiler toolchain và JVM chạy test có thể khác nhau.

Nên in thông tin **từ chính process ứng dụng/test**:

```java
import java.nio.charset.Charset;

public class RuntimeProbe {
    public static void main(String[] args) {
        System.out.println("Version: "
            + Runtime.version());
        System.out.println("Vendor: "
            + System.getProperty("java.vendor"));
        System.out.println("java.home: "
            + System.getProperty("java.home"));
        System.out.println("JAVA_HOME: "
            + System.getenv("JAVA_HOME"));
        System.out.println("Default charset: "
            + Charset.defaultCharset());
    }
}
```

Ví dụ dùng `Runtime.version()` cần JDK 9+. Trên JDK 8, có thể thay bằng `System.getProperty("java.version")`.

Đừng lấy đường dẫn `java.home` ghép với `../lib/tools.jar`, vì cách giải thích `java.home` đã khác sau JDK 8 và custom image có thể không có công cụ biên dịch.

## 28. Classpath và module path: chọn theo mục tiêu

Ứng dụng non-modular vẫn có thể chạy:

```bash
java -cp "app.jar:libs/*" com.example.Main
```

Trên Windows, dùng classpath separator phù hợp:

```powershell
java -cp "app.jar;libs/*" com.example.Main
```

Ở chế độ classpath, application classes nằm trong **unnamed module**; không cần `rt.jar` hay `tools.jar`.

Ứng dụng named module:

```bash
java --module-path mods \
  --module com.example.app/com.example.Main
```

Đặt một JAR lên module path có thể làm thay đổi cách resolve modules và quyền truy cập package. Tránh đưa JMODs của JDK vào runtime classpath/module path như artifact ứng dụng. Các Java platform modules đã nằm trong runtime image và được JVM giải quyết qua module system.

Một ứng dụng chỉ dùng Java SE public APIs có thể nâng JDK mà không cần modular hóa toàn bộ mã nguồn ngay lập tức. Nhưng nếu dùng JDK internals, JPMS encapsulation vẫn có thể ảnh hưởng cả code trên classpath.

## 29. Bảng triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Phương án |
|---|---|---|
| Không tìm thấy `tools.jar` trong Maven `systemPath` | Phụ thuộc layout JDK 8. | Bỏ dependency giả, nâng plugin, dùng Toolchains/`javax.tools`. |
| Script báo `jdk-21/jre/bin/java` không tồn tại | JDK mới không có JRE con. | Dùng `bin/java` của đúng runtime image. |
| `jar tf lib/modules` thất bại | `lib/modules` không phải JAR. | Dùng `jimage` hoặc JRT filesystem. |
| `JarURLConnection` cast lỗi | Platform class resource URL chuyển từ `jar:` sang `jrt:`. | Dùng stream, module API hoặc JRT FS. |
| `URLClassLoader` cast lỗi | System loader implementation thay đổi. | Dùng API công khai hoặc custom loader tự quản lý. |
| `java.ext.dirs` lỗi startup | Extension mechanism đã bị loại. | Đưa JAR vào classpath/module path đúng cách. |
| `InaccessibleObjectException` | Module encapsulation chặn reflection. | Nâng dependency; dùng public API, workaround hẹp khi cần. |
| `NoClassDefFoundError` trong jlink image | Module/dependency còn thiếu hoặc chưa resolve. | `jdeps`, bổ sung runtime modules, test dynamic loading. |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime image không có compiler implementation. | Dùng JDK hoặc image gồm compiler module. |
| Annotation processor lỗi `com.sun.tools.javac` | Phụ thuộc compiler internals hoặc version cũ. | Nâng plugin/processor, điều chỉnh API. |
| Application lỗi TLS chỉ trên custom image | Crypto provider/truststore/module hoặc native dependencies khác. | Kiểm tra image, thêm provider cần thiết và test handshake. |

Không phải lỗi nào xuất hiện khi đổi từ JDK 8 lên 17 đều liên quan đến `rt.jar`. Có thể còn vấn đề khác như library binary compatibility, JAXB/Java EE modules bị loại, Nashorn, GC, reflection hoặc charset.

## 30. Quy trình migration theo từng bước

### Bước 1 — Inventory giả định về cấu trúc JDK

Tìm trong Java source, POM, Gradle, Dockerfile, shell/batch scripts và CI config:

```text
rt.jar
tools.jar
dt.jar
jre/bin/java
jre/lib
lib/ext
lib/endorsed
java.ext.dirs
java.endorsed.dirs
sun.boot.class.path
JarURLConnection
URLClassLoader
com.sun.tools.javac
```

Một số từ khóa có thể xuất hiện trong test/documentation mà không được dùng khi chạy; xác định call sites thực tế trước khi sửa.

### Bước 2 — Xác định JDK đích và runtime image

Ghi version/build/vendor/OS/CPU architecture, full JDK hay custom runtime. Kiểm tra:

```bash
java -version
javac -version
java --list-modules
```

Trên custom runtime, `javac` vắng mặt không phải lỗi nếu image không cần biên dịch.

### Bước 3 — Phân loại nhu cầu đằng sau file cũ

| Phụ thuộc cũ | Nhu cầu thật | Giải pháp mới |
|---|---|---|
| `rt.jar` để thêm classpath | Dùng Java SE APIs | Xóa dependency thừa; runtime cung cấp modules. |
| `rt.jar` để đọc bytecode | Phân tích platform classes | JRT filesystem/`jimage`/tooling phù hợp. |
| `tools.jar` để gọi compiler | Biên dịch Java source | `javax.tools` hoặc toolchain `javac`. |
| `tools.jar` để truy cập internals | Hook vào compiler implementation | Nâng/refactor plugin, giảm phụ thuộc internals. |
| `jdk/jre` để deploy | Có Java runtime | Dùng runtime base image hoặc `jlink` image. |
| `lib/ext` | Nạp extension JAR | Classpath/module path có khai báo. |

### Bước 4 — Nâng toolchain và thư viện quét class

Đảm bảo Maven/Gradle, IDE, bytecode libraries, annotation processors và build plugins hỗ trợ JDK mới. Một plugin cũ có thể trực tiếp quét `rt.jar` dù source app không dùng đường dẫn này.

### Bước 5 — Cập nhật compile target

Dùng `javac --release` hoặc cấu hình Maven/Gradle tương ứng. Xác nhận JVM chạy unit/integration tests trên minimum runtime mà sản phẩm hỗ trợ.

### Bước 6 — Cập nhật packaging/container

Xóa bước copy `jre/`, bổ sung runtime image phù hợp OS/arch, cấu hình `conf/` và security providers. Ghim version/checksum image, tránh copy nhầm artifact cũ.

### Bước 7 — Kiểm thử runtime thực tế

Chạy ứng dụng trên **đúng image sẽ phát hành** và kiểm tra startup, class loading, JDBC, TLS, JSON/XML, service providers, locale, timezone, JNI/native code và monitoring agents. Không coi một lệnh `java -version` là đủ.

### Bước 8 — Triển khai có khả năng rollback

Lưu JDK build, module list, artifact checksum, container tag và tài liệu rollback. Nếu lỗi do runtime image, rollback có thể cần thay **cả image**, không chỉ JAR ứng dụng.

## 31. Những sai lầm cần tránh

**“Không có rt.jar nghĩa là Java SE API bị xóa.”** Sai. Phần lớn API nền tảng được tổ chức thành modules; việc API cụ thể còn hay bị loại phải kiểm tra release notes.

**“Đổi tools.jar thành jdk.compiler.jmod trong classpath.”** Sai. JMOD không phải replacement JAR runtime.

**“JDK 11 không có JRE nên không chạy Java được.”** Sai. JDK vẫn mang Java runtime và có thể tạo custom image.

**“Cứ dùng java -cp thêm lib/modules.”** Sai. `lib/modules` là dữ liệu runtime image, không phải classpath JAR.

**“ClassLoader luôn là URLClassLoader.”** Sai từ khi implementation loader thay đổi ở Java 9.

**“Cứ thêm --add-opens là sửa được thiếu rt.jar.”** Sai. `--add-opens` điều chỉnh quyền phản chiếu, không tạo file JAR nội bộ.

**“jlink image chạy được Hello World nghĩa là đủ mọi service.”** Sai. Các chức năng có dependency động và service providers có thể thiếu.

**“--release 17 chứng minh production Java 17 compatible.”** Chưa đủ. Còn dependency versions, runtime modules, class loading, reflection và integration tests trên Java 17.

## 32. Checklist cuối cùng

- [ ] Không còn hardcoded `jre/lib/rt.jar`, `lib/tools.jar` hoặc `dt.jar`.
- [ ] Không còn dependency Maven `scope=system` trỏ tới JDK internals.
- [ ] Đã xác định API/tool tương đương cho nhu cầu compiler và bytecode inspection.
- [ ] Không thêm `lib/modules` hoặc `*.jmod` vào classpath như JAR.
- [ ] Các công cụ đọc platform classes hỗ trợ `jrt:` hoặc JRT filesystem.
- [ ] Không cast system/platform class loader thành `URLClassLoader`.
- [ ] Đã xử lý `lib/ext`, `lib/endorsed` và các property cũ.
- [ ] Đã xác định đường dẫn cấu hình mới dưới `conf/` nếu cần.
- [ ] Đã xác nhận `java.home`/Java version trong đúng test/process.
- [ ] Đã chọn `javac --release` hoặc Toolchains đúng baseline.
- [ ] Maven/Gradle/IDE/annotation processors hỗ trợ JDK đích.
- [ ] Nếu dùng jlink, đã kiểm tra các module được link và dependencies động.
- [ ] Đã test TLS, truststore, timezone, locale, charset và JNI nếu liên quan.
- [ ] Docker/CI không copy thư mục `jdk/jre` theo layout JDK 8.
- [ ] Runtime image phù hợp OS/architecture và được cập nhật bảo mật.
- [ ] Có chứng cứ chạy integration tests trên runtime image cuối.
- [ ] Có provenance và rollback strategy cho runtime image/JDK version.

## 33. Câu hỏi thực hành

**Câu 1:** Maven báo lỗi tìm `jdk.tools:jdk.tools:1.8` trên JDK 17. Có nên copy `tools.jar` từ JDK 8 vào thư mục JDK 17?

**Gợi ý:** Không. Cần loại bỏ phụ thuộc vào layout, nâng plugin/compiler integration hoặc dùng `javax.tools` và toolchain.

**Câu 2:** Vì sao `ClassLoader.getSystemResource("java/lang/Class.class")` trả `jrt:/java.base/...` trên Java 21 thay vì `jar:file:...rt.jar!...`?

**Gợi ý:** Java 9+ lưu Java SE classes trong modular runtime images; `jrt:` là giao diện tài nguyên phù hợp mà không phụ thuộc cấu trúc vật lý.

**Câu 3:** Dockerfile cũ copy `jdk/jre/`, builder chuyển sang JDK 21. Làm thế nào?

**Gợi ý:** Chọn runtime distribution hoặc tạo jlink image trong build stage rồi copy toàn bộ image phù hợp platform.

**Câu 4:** Một jlink image chạy được ứng dụng cơ bản nhưng lỗi khi mở kết nối HTTPS. Nguyên nhân chỉ có thể là thiếu `rt.jar`?

**Gợi ý:** Không. Kiểm tra TLS provider, truststore, JDK modules, native dependencies và cấu hình bảo mật của image.

**Câu 5:** Nếu ứng dụng đã compile bằng `javac --release 17`, có cần test trên Java 17 nữa không?

**Gợi ý:** Có. Dependency JARs, native libraries, reflection và runtime behavior không được xác nhận chỉ bằng target bytecode.

## 34. Tài liệu tham khảo

- [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): thay đổi cách đóng gói image từ JDK 9.
- [JEP 200 — The Modular JDK](https://openjdk.org/jeps/200): thiết kế JDK theo module.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS, module path và class loaders.
- [Oracle JDK Migration Guide — JDK 8 to Later](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): thay đổi layout, rt.jar/tools.jar, jrt URLs, ext/endorsed.
- [Oracle JDK 9 Migration Guide](https://docs.oracle.com/javase/9/migrate/): tác động của thay đổi khi Java 9 ra mắt.
- [JDK 9 Release Notes](https://www.oracle.com/java/technologies/javase/9-relnotes.html): thay đổi đường dẫn JDK và config.
- [JDK 21 jdk.jlink Module](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jlink/module-summary.html): jlink, jmod và jimage.
- [JDK 21 jlink](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html): xây runtime image.
- [JDK 21 jimage](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jimage.html): xem image contents.
- [JDK 21 jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): phân tích class/module dependencies.
- [JDK 21 javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): sử dụng `--release`.
- [Java Compiler API](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/package-summary.html): API `javax.tools`.
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396) và [JEP 403](https://openjdk.org/jeps/403): quyền truy cập implementation internals.

## Kết luận

Từ JDK 9, `rt.jar` và `tools.jar` không còn tồn tại trong layout Java runtime/JDK vì nền tảng đã chuyển sang **modular runtime images**. Điều này không đồng nghĩa mất Java SE APIs hay trình biên dịch: các chức năng được tổ chức trong modules, với những công cụ/API được hỗ trợ như `javax.tools`, `jrt:/`, `jdeps`, `jimage` và `jlink`. Để migration bền vững, hãy bỏ các đường dẫn hardcoded của JDK 8, phân biệt Java compiler với runtime image, cập nhật IDE/build plugins, kiểm tra JPMS/class loaders và đóng gói image đúng platform. Kiểm thử cuối cùng phải được thực hiện trên runtime thực sự triển khai, không phải chỉ trên JDK ở máy build.



