# Giới hạn tìm nested JAR của URLClassLoader và khác biệt với launcher chuyên dụng

## 1. Vấn đề: JAR “có chứa thư viện” nhưng không nạp được class

Một file Java Archive (JAR) thực chất là một ZIP archive theo định dạng JAR. JAR có thể chứa file, thư mục, class và **một file JAR khác như một entry dữ liệu**. Ví dụ:

~~~text
outer.jar
├── META-INF/
│   └── MANIFEST.MF
├── app/Main.class
└── lib/
    └── helper.jar
        └── (bên trong helper.jar)
            demo/lib/Helper.class
~~~

Nhìn cấu trúc, có thể nghĩ rằng:

~~~java
new URLClassLoader(new URL[] { outerJarUrl })
        .loadClass("demo.lib.Helper");
~~~

sẽ tự mở `outer.jar`, phát hiện `lib/helper.jar` rồi đi tiếp vào archive con. **Đây là suy luận sai đối với `URLClassLoader` tiêu chuẩn của JDK.** Nó tìm lớp từ **các URL trong search path và các quy tắc tra cứu JAR tiêu chuẩn**, không tự duyệt mọi entry `*.jar` bên trong JAR đang mở như những classpath roots mới.

**Chốt trọng tâm:**

- File `outer.jar` có thể tồn tại và chứa `helper.jar`.
- `URLClassLoader` thông thường **có thể nhìn thấy entry `lib/helper.jar` như một resource** trong outer JAR.
- Nhưng `demo.lib.Helper` nằm *bên trong byte stream của entry `helper.jar`*, không nằm tại đường `demo/lib/Helper.class` của **outer JAR**.
- Muốn load trực tiếp class từ nested archive **mà không trích ra**, cần một cơ chế có hiểu biết về nested archive, chẳng hạn **launcher/ClassLoader chuyên dụng** của một framework. Một giải pháp khác là **trích JAR con thành file JAR thật rồi đặt file đó vào runtime classpath/URLClassLoader**.
- Không phải mọi file được gọi là “executable/fat JAR” đều cùng cơ chế. **Shaded/uber JAR** có thể đưa class vào thẳng cùng một archive, còn **nested JAR** giữ library dưới dạng JAR riêng nằm bên trong.

Bài này giải thích giới hạn của **`java.net.URLClassLoader`**, phân biệt với Spring Boot executable JAR và thực nghiệm Java 17+ có stdout kiểm chứng.

## 2. Trước hết phân biệt ba dạng đóng gói

### 2.1. Plain JAR + dependency nằm ngoài

~~~text
dist/
├── app.jar
└── lib/
    ├── a.jar
    └── b.jar
~~~

`app.jar` là JAR của ứng dụng, `a.jar` và `b.jar` là những **file thực tế** trong hệ thống tệp. Launcher có thể:

- Dùng `java -cp "app.jar:lib/a.jar:lib/b.jar" app.Main` trên Linux/macOS.
- Dùng `java -cp "app.jar;lib/a.jar;lib/b.jar" app.Main` trên Windows.
- Dùng manifest `Class-Path` thích hợp hoặc script launcher do công cụ build tạo, tùy deployment.

Mỗi JAR được liệt kê là một **classpath entry** độc lập; `URLClassLoader` tiêu chuẩn có thể dùng URL trỏ đến các file JAR như vậy.

### 2.2. Shaded/uber JAR: gộp class vào một archive

~~~text
app-all.jar
├── META-INF/MANIFEST.MF
├── app/Main.class
├── demo/lib/Helper.class
└── another/lib/Codec.class
~~~

Không có một `helper.jar` cần mở lồng để tìm `Helper.class`: class của dependency đã được đưa **trực tiếp** vào JAR ngoài theo đường package của nó. Khi không có xung đột/relocation đặc biệt, class loader chuẩn có thể tìm `demo/lib/Helper.class` như entry của một JAR bình thường.

Các công cụ như Maven Shade Plugin, Gradle Shadow và những build task tương tự có thể tạo archive dạng này theo cấu hình. Đừng nhầm chữ “fat JAR” với “nested JAR”: cách đóng gói thực sự mới quyết định cơ chế nạp.

**Rủi ro riêng của shaded JAR:** trùng đường class/resource, chữ ký JAR, `META-INF/services`, relocation package, license/metadata và multi-release entries có thể cần xử lý chính xác khi merge.

### 2.3. Nested JAR: giữ JAR con nguyên vẹn trong JAR ngoài

~~~text
app-nested.jar
├── META-INF/MANIFEST.MF
├── app/Main.class
└── lib/helper.jar       <-- file JAR con là một entry trong archive ngoài
    └── demo/lib/Helper.class  (nằm trong archive con)
~~~

`jar --list --file app-nested.jar` liệt kê `lib/helper.jar`, nhưng **không tự liệt kê** `demo/lib/Helper.class` như một entry trực tiếp của archive ngoài.

Nếu thêm `app-nested.jar` vào `URLClassLoader`, loader có thể tìm `app/Main.class` (nếu class nằm trực tiếp ở root), nhưng **không tự biến `lib/helper.jar` thành một classpath entry mới**. Đây chính là giới hạn bài học phân tích.

## 3. `URLClassLoader` thực sự tìm từ đâu?

Theo [Java SE 17 `URLClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), loader này dùng các URL tham chiếu đến **JAR files và directories**:

- URL `file:` kết thúc bằng `/` đại diện một directory classpath root.
- URL `file:` trỏ tới JAR file đại diện một JAR có thể được mở để tìm class/resource.
- URL dạng `jar:...!/` được xử lý theo quy tắc của JAR URL/`JarURLConnection`.
- Các URL được tra theo cơ chế delegation và thứ tự search path tương ứng; `parent` có thể trả class trước `findClass` của loader con.
- `getURLs()` trả các URL trong search path của chính `URLClassLoader`; danh sách này **không tự hiển thị mọi JAR bị nhúng như entry trong archive ngoài**.

### 3.1. Cách class name ánh xạ thành resource name

Binary name:

~~~text
demo.lib.Helper
~~~

thường tương ứng với class resource:

~~~text
demo/lib/Helper.class
~~~

Để load từ một JAR URL thông thường, entry này phải được tìm theo logic JAR classpath root. Nhưng khi archive ngoài có:

~~~text
BOOT-INF/lib/helper.jar
~~~

thì loader chỉ có **entry chứa byte của một JAR con**; đường `demo/lib/Helper.class` không phải entry trực tiếp trong archive ngoài.

Vì vậy cần tách hai câu hỏi:

| Câu hỏi | Trả lời khi chỉ thêm `outer.jar` vào URLClassLoader |
|---|---|
| Có thể tìm resource `BOOT-INF/lib/helper.jar` không? | **Có thể**, vì đây là entry thật của outer JAR |
| Có thể tự load `demo.lib.Helper` từ bên trong resource đó không? | **Không theo hành vi tìm nested JAR thông thường của JDK URLClassLoader** |
| Có thể load `app.Main` nếu `app/Main.class` nằm trực tiếp trong outer JAR? | Có, nếu đúng loader/đường classpath và không gặp ràng buộc khác |
| Có thể load `demo.lib.Helper` từ một **file `helper.jar` độc lập** được thêm vào URLClassLoader không? | Có, với JAR hợp lệ và không có vấn đề class/dependency khác |

Tìm được resource `helper.jar` không đồng nghĩa JVM đã biết cách tìm từng `.class` bên trong file resource đó.

### 3.2. Đừng nhầm URL của một entry với URL classpath root

Java `jar:` URL tiêu chuẩn có cú pháp đại ý:

~~~text
jar:<url-của-JAR>!/<entry>
~~~

Ví dụ một class resource trong JAR **không lồng nhau**:

~~~text
jar:file:/some/dir/helper.jar!/demo/lib/Helper.class
~~~

Nhưng chuỗi ghép kiểu:

~~~text
jar:file:/some/dir/outer.jar!/BOOT-INF/lib/helper.jar!/demo/lib/Helper.class
~~~

**không tự trở thành cách chuẩn để `JarURLConnection` mở “JAR trong JAR”**. Giao thức JAR URL/JDK thông thường không bảo đảm xử lý nhiều tầng `!/` như một classpath root độc lập. Không nên xây URL thủ công rồi giả định `URLClassLoader` tự hiểu nested archive.

Một framework có thể cài **protocol handler/JAR abstraction chuyên dụng**, tạo ra URL nhìn có vẻ tương tự nhưng ngữ nghĩa do framework cung cấp. Khi đó kết quả không còn là hành vi mặc định thuần JDK.

### 3.3. Resource là dữ liệu, không phải một JAR được mount tự động

Chương trình vẫn có thể lấy byte của entry nested:

~~~java
try (java.util.jar.JarFile outer =
        new java.util.jar.JarFile("build/outer.jar")) {
    java.util.jar.JarEntry nested =
            outer.getJarEntry("BOOT-INF/lib/helper.jar");
    try (java.io.InputStream in = outer.getInputStream(nested)) {
        // Có thể đọc byte helper.jar như dữ liệu thông thường.
    }
}
~~~

Đoạn trên là **snippet minh họa**, không thể biên dịch độc lập nếu không đặt trong phương thức thích hợp và xử lý import/exception. Nó chứng minh việc **đọc entry của outer JAR** hoàn toàn có thể, nhưng không có bước JVM tự đọc tiếp định dạng class/JAR bên trong. Muốn dùng class từ byte đó cần chiến lược thích hợp: trích archive và đưa đường dẫn vào loader, tạo custom loader, hoặc dùng launcher chuyên dụng.

## 4. Vì sao `java -jar outer.jar` không tự giải quyết nested JAR?

Lệnh:

~~~sh
java -jar outer.jar
~~~

yêu cầu Java launcher chạy main class được khai báo bởi **manifest `Main-Class`** trong JAR ngoài. Theo tài liệu [Java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html), khi dùng `-jar`, classpath tùy chọn của người dùng không được kết hợp như lệnh `java -cp ... Main`.

Điều đặc biệt quan trọng: `java -jar` **không có nghĩa** “Java tự tìm mọi JAR con nằm bên trong JAR ngoài”.

Ví dụ JAR có:

~~~text
META-INF/MANIFEST.MF:
  Main-Class: app.Main

outer.jar:
  app/Main.class
  BOOT-INF/lib/helper.jar
~~~

Ứng dụng `app.Main` có thể khởi chạy nếu class của nó nằm ở vị trí mà launcher tiêu chuẩn tìm thấy. Nhưng class trong `BOOT-INF/lib/helper.jar` vẫn **không tự hiện diện** trên classpath chỉ vì có entry `helper.jar`.

Đặc biệt, `Class-Path` của manifest tiêu chuẩn **không phải cú pháp để nạp các JAR con như một entry bên trong JAR ngoài**. Nó mô tả các đường dẫn classpath liên quan theo hợp đồng manifest, thường dùng cho external dependencies. Để chạy nested libraries bên trong archive duy nhất cần cơ chế đọc phù hợp.

### Phân biệt “chạy được” và “nạp mọi dependency”

Có thể `java -jar app.jar` khởi động `main()` thành công, rồi gặp:

~~~text
java.lang.NoClassDefFoundError: demo/lib/Helper
~~~

khi thực sự cần đến class trong JAR con. Đây thường là dấu hiệu layout chứa nested library nhưng quá trình launch **không cài loader hiểu layout đó**. Tuy nhiên, không phải mọi `NoClassDefFoundError` đều do nested-JAR: lỗi initialization, version và linkage khác cũng có thể dẫn đến nó. Cần xem cause và lệnh launch.

## 5. Launcher chuyên dụng giải quyết vấn đề như thế nào?

Một **launcher chuyên dụng** có thể thực hiện các công việc mà launcher JDK tiêu chuẩn không tự làm:

1. Đọc định dạng archive của framework.
2. Phân biệt phần **application classes** với phần **libraries**.
3. Truy cập archive con qua abstraction/JAR API riêng hoặc, với giải pháp khác, trích chúng ra file tạm.
4. Tạo/cấu hình ClassLoader nhận biết các vị trí đó.
5. Thiết lập môi trường cần thiết (ví dụ TCCL theo thiết kế framework).
6. Gọi `main()` thật của ứng dụng sau khi đã chuẩn bị loader.

**Không có một kỹ thuật duy nhất cho mọi framework.** Cách truy cập nested JAR trực tiếp và cách giải nén tạm là hai lựa chọn triển khai khác nhau. Không nên khẳng định launcher nào cũng luôn extract JAR con.

### 5.1. Ví dụ Spring Boot executable JAR

Tài liệu chính thức của Spring Boot mô tả cấu trúc điển hình:

~~~text
myapp.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...  (các class bootstrap của Boot)
└── BOOT-INF/
    ├── classes/
    │   └── com/example/MyApplication.class
    └── lib/
        ├── dependency-1.jar
        └── dependency-2.jar
~~~

Chính layout này cho thấy **`BOOT-INF/classes/` không phải classpath root tiêu chuẩn** của `java -cp myapp.jar com.example.MyApplication`, và `BOOT-INF/lib/*.jar` là những library JAR **lồng**.

Khi artifact được đóng gói bởi Spring Boot plugin đúng chuẩn và chạy theo cách được hỗ trợ:

~~~sh
java -jar myapp.jar
~~~

manifest thường dùng launcher của Spring Boot làm main entry point:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.MyApplication
~~~

- `Main-Class` là **launcher** nằm ở vị trí có thể nạp bằng Java launcher tiêu chuẩn.
- `Start-Class` chỉ định **main class thực sự của ứng dụng**.
- Spring Boot launcher tạo môi trường nạp cần thiết cho `BOOT-INF/classes` và `BOOT-INF/lib` rồi mới gọi app main.

Tên class `org.springframework.boot.loader.launch.JarLauncher` áp dụng cho **layout Spring Boot hiện đại** (ví dụ Boot 3.2+). Tên package của launcher khác nhau giữa một số thế hệ Spring Boot; không nên copy manifest từ phiên bản khác mà không đối chiếu bản Boot đang dùng.

**Nguồn:** [Spring Boot — Launching Executable Jars](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html).

### 5.2. Tại sao Spring Boot có thể đọc JAR lồng?

Tài liệu Spring Boot mô tả abstraction `NestedJarFile`: nó ánh xạ những entry của nested JAR tới vị trí trong JAR ngoài để có thể truy cập byte của class/resource bên trong mà **không nhất thiết phải giải nén mọi thư viện ra disk**.

Spring Boot cung cấp cơ chế tương thích với URL/JAR connection cho các dạng URL nội bộ như:

~~~text
jar:nested:/path/myapp.jar/!BOOT-INF/lib/dependency-1.jar!/pkg/Type.class
~~~

Đây là **ví dụ cú pháp do Spring Boot hỗ trợ bằng cơ chế của nó**, **không phải** cú pháp được `URLClassLoader` JDK độc lập bảo đảm hiểu chỉ nhờ gọi `new URL(...)`. Đừng suy từ hình thức gần giống `jar:...!/` rằng URL protocol đã trở thành chuẩn JDK đa tầng.

**Nguồn:** [Spring Boot — NestedJarFile](https://docs.spring.io/spring-boot/specification/executable-jar/jarfile-class.html).

### 5.3. Điều gì xảy ra nếu bỏ qua launcher Spring Boot?

Giả sử bạn cố chạy:

~~~sh
java -cp myapp.jar com.example.MyApplication
~~~

với một archive Spring Boot đúng layout. JVM tiêu chuẩn có thể không tìm thấy `com.example.MyApplication`, vì class nằm dưới `BOOT-INF/classes/com/example/...` thay vì root package path. Ngay cả khi tìm được entry bằng API đọc JAR, các libraries dưới `BOOT-INF/lib/` cũng không được tự nạp vào standard classpath.

Vì vậy, **Spring Boot `bootJar` không tương đương plain JAR** của Gradle/Maven. Dùng đúng launcher hoặc cơ chế unpack/exploded được tài liệu hóa cho version đó. Không coi `java -jar` là nguyên nhân duy nhất giúp nested JAR hoạt động; **chính bootstrap classes và loader của Spring Boot trong artifact** cung cấp khả năng này.

## 6. Thực hành độc lập Java 17+: standard URLClassLoader thấy nested entry nhưng không thấy class

Thực hành này **không cần Spring Boot, Maven hay Gradle**. Ta tự tạo một JAR chứa một JAR con, thử tìm class bên trong qua standard URLClassLoader, sau đó **trích JAR con ra file thật** và nạp lại bằng standard URLClassLoader.

### 6.1. Cấu trúc source và output

~~~text
demo/
├── src/
│   ├── app/
│   │   └── NestedJarDemo.java
│   └── lib/
│       └── demo/lib/Helper.java
└── build/
    ├── app/
    ├── lib/
    ├── pack/
    │   └── BOOT-INF/lib/helper.jar
    ├── helper.jar
    ├── outer.jar
    └── helper-extracted.jar   (tạo khi chạy)
~~~

Đường `BOOT-INF/lib/` ở thực hành chỉ được chọn để mô phỏng **vị trí một JAR lồng**; `outer.jar` của bài **không phải** Spring Boot executable JAR, vì nó không chứa Boot loader. Điều này giúp cô lập giới hạn của Java/JDK thuần.

### 6.2. Tệp `src/lib/demo/lib/Helper.java`

~~~java
package demo.lib;

public class Helper {
    public static String message() {
        return "from-library";
    }
}
~~~

`Helper.class` sẽ chỉ xuất hiện **trong JAR con**; không được vô tình đưa `build/lib` hoặc `build/helper.jar` lên classpath runtime của launcher trong bước thử thất bại.

### 6.3. Tệp `src/app/NestedJarDemo.java`

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public class NestedJarDemo {
    public static void main(String[] args) throws Exception {
        Path outer = Path.of("build/outer.jar");

        try (URLClassLoader flat = new URLClassLoader(
                new URL[] { outer.toUri().toURL() },
                NestedJarDemo.class.getClassLoader())) {

            System.out.println("nestedEntryVisible="
                    + (flat.getResource("BOOT-INF/lib/helper.jar") != null));

            try {
                flat.loadClass("demo.lib.Helper");
                System.out.println("ordinaryLoaderFound=true");
            } catch (ClassNotFoundException expected) {
                System.out.println("ordinaryLoaderFound=false");
            }
        }

        Path extracted = Path.of("build/helper-extracted.jar");
        try (JarFile archive = new JarFile(outer.toFile())) {
            JarEntry nested =
                    archive.getJarEntry("BOOT-INF/lib/helper.jar");
            try (InputStream stream = archive.getInputStream(nested)) {
                Files.copy(stream, extracted,
                        StandardCopyOption.REPLACE_EXISTING);
            }
        }

        try (URLClassLoader unpacked = new URLClassLoader(
                new URL[] { extracted.toUri().toURL() },
                NestedJarDemo.class.getClassLoader())) {

            Class<?> helper = unpacked.loadClass("demo.lib.Helper");
            System.out.println("extractedLoaderFound="
                    + (helper.getClassLoader() == unpacked));
            System.out.println("message="
                    + helper.getMethod("message").invoke(null));
        }
    }
}
~~~

**Phân tích trước khi chạy:**

- `outer.toUri().toURL()` trỏ đến một **file JAR thông thường trên disk**. `URLClassLoader flat` tìm trong archive ngoài.
- `flat.getResource("BOOT-INF/lib/helper.jar")` tìm **entry là byte dữ liệu của JAR con**, nên có thể trả URL resource.
- `flat.loadClass("demo.lib.Helper")` tìm class theo đường `demo/lib/Helper.class` tương ứng, **không có ở root archive ngoài**, dẫn đến `ClassNotFoundException` được bắt.
- `JarFile` đọc entry `BOOT-INF/lib/helper.jar` và `Files.copy` lưu byte đó thành **file `build/helper-extracted.jar`**.
- `URLClassLoader unpacked` dùng URL của **JAR đã được trích**; bây giờ `demo/lib/Helper.class` nằm trực tiếp trong JAR đang tìm, nên load thành công.
- Chương trình dùng `try-with-resources` để đóng các URLClassLoader/JarFile có thể giữ file handles. Việc đóng loader không đảm bảo unload mọi class ngay lập tức.

### 6.4. Biên dịch và đóng gói trên Linux/macOS

Từ thư mục `demo`, dùng JDK 17 trở lên:

~~~sh
mkdir -p build/app build/lib build/pack/BOOT-INF/lib
javac --release 17 -d build/lib src/lib/demo/lib/Helper.java
jar --create --file build/helper.jar -C build/lib .
cp build/helper.jar build/pack/BOOT-INF/lib/helper.jar
javac --release 17 -d build/app src/app/NestedJarDemo.java
jar --create --file build/outer.jar --main-class NestedJarDemo \
    -C build/app . \
    -C build/pack BOOT-INF/lib/helper.jar
java -jar build/outer.jar
~~~

Dấu `\` cuối dòng chỉ là cú pháp nối lệnh shell POSIX. Có thể viết lệnh `jar --create ...` trên **một dòng** nếu không dùng Bash/POSIX shell.

### 6.5. Lệnh tương đương trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/app, build/lib, build/pack/BOOT-INF/lib | Out-Null
javac --release 17 -d build/lib src/lib/demo/lib/Helper.java
jar --create --file build/helper.jar -C build/lib .
Copy-Item build/helper.jar build/pack/BOOT-INF/lib/helper.jar
javac --release 17 -d build/app src/app/NestedJarDemo.java
jar --create --file build/outer.jar --main-class NestedJarDemo -C build/app . -C build/pack BOOT-INF/lib/helper.jar
java -jar build/outer.jar
~~~

Với cả hai hệ điều hành, hãy chạy từ đúng thư mục `demo` vì `Path.of("build/outer.jar")` là đường dẫn tương đối. Không thêm `build/helper.jar` hoặc `build/lib` vào runtime classpath khi chạy ví dụ.

### 6.6. Stdout chính xác đã được kiểm chứng

~~~text
nestedEntryVisible=true
ordinaryLoaderFound=false
extractedLoaderFound=true
message=from-library
~~~

Bốn dòng thể hiện **ba trạng thái khác nhau**:

1. `nestedEntryVisible=true`: outer JAR thực sự chứa entry có tên `BOOT-INF/lib/helper.jar`; standard loader có thể tìm entry như một resource.
2. `ordinaryLoaderFound=false`: standard loader **không tự đi tiếp vào JAR con** để nạp class.
3. `extractedLoaderFound=true`: khi library được lưu thành file JAR riêng, loader mới định nghĩa được class.
4. `message=from-library`: class đã được nạp và có thể gọi public method.

**Ranh giới của thí nghiệm:** việc trích archive ở đây chỉ để làm rõ cơ chế. Trong ứng dụng production, việc extract thư viện cần chú ý bảo mật input, thư mục tạm, quyền ghi, cleanup, đồng bộ/concurrency và checksum/khả năng tái lập build. Không trích tùy tiện nội dung archive không đáng tin.

### 6.7. Cách xác minh “file con” và “class trực tiếp” trong JAR

~~~sh
jar --list --file build/outer.jar
jar --list --file build/helper.jar
~~~

Với `outer.jar`, bạn thấy `NestedJarDemo.class` và `BOOT-INF/lib/helper.jar`. Với `helper.jar`, bạn thấy `demo/lib/Helper.class`. Phép kiểm tra này giúp tách **resource JAR lồng** và **class root thực sự mà `URLClassLoader` đi tìm**.

## 7. Bảng so sánh các cơ chế chạy và nạp dependency

| Cơ chế | Layout thư viện | Ai cung cấp khả năng đọc? | Có cần nested-JAR-aware loader? |
|---|---|---|---|
| `java -cp "app.jar:lib/helper.jar" app.Main` | External JAR files | Java launcher + built-in loader | **Không** |
| `new URLClassLoader(new URL[]{helperFileUrl})` | External JAR file URL | `URLClassLoader` tiêu chuẩn | **Không** |
| `new URLClassLoader(new URL[]{outerFileUrl})`, helper nằm trong outer | Nested JAR entry | URLClassLoader tiêu chuẩn **không tự đọc entry thành classpath JAR** | **Có**, nếu muốn nạp trực tiếp từ nested |
| Shaded/uber JAR | Dependency classes gộp vào root JAR | Built-in loader/URLClassLoader thường là đủ | **Không** nếu package hợp lệ |
| Spring Boot executable JAR `java -jar` | `BOOT-INF/classes` + `BOOT-INF/lib/*.jar` | Boot launcher + nested-archive loader/handler | **Có, Boot cung cấp** |
| Extract helper.jar rồi nạp bằng URLClassLoader | JAR con thành file độc lập | Code extract + URLClassLoader tiêu chuẩn | **Không** sau khi extract |
| Container/script chạy JAR distribution | Thư mục app + lib/*.jar | Script tạo `-cp` hoặc launcher framework | Tùy packaging |

Bảng mô tả **cơ chế điển hình**, không phải cam kết tất cả framework đều đóng gói đúng một cách. “Executable JAR” chỉ nói artifact có đường khởi chạy phù hợp; phải xác định kiểu launcher và layout class thực tế.

## 8. Các nhầm lẫn quan trọng

### “Dùng `java -jar` thì JVM tự nạp mọi nested JAR”

Sai. `java -jar` chỉ chọn JAR/main entry point theo hợp đồng launcher. Spring Boot executable JAR dùng `java -jar` **vì manifest trỏ đến Boot launcher** biết cách đọc nested libraries.

### “`URLClassLoader` nạp resource `helper.jar` được thì nạp class ở trong đó được”

Sai. Resource của outer archive khác archive nằm bên trong resource đó. `getResource("BOOT-INF/lib/helper.jar") != null` không chứng minh `loadClass("demo.lib.Helper")` thành công.

### “Ghi URL `jar:file:/outer.jar!/lib/helper.jar!/` là đủ”

Sai trong chuẩn JDK thông thường. Một lớp xử lý archive/URL chuyên dụng phải hiểu ngữ nghĩa nhiều tầng; cú pháp có dấu `!/` không tự cấp capability nạp nested JAR.

### “Thêm `BOOT-INF/lib` vào `-cp` là sẽ dùng được thư viện”

Không đúng nếu đó chỉ là **đường entry bên trong một outer JAR** và không phải directory thật trên disk. Khi trích archive thành thư mục, classpath có thể trỏ đến các file JAR đã được trích; nhưng **cơ chế này khác với tìm trực tiếp nested JAR chưa trích**.

### “Plain JAR, shaded JAR, Boot JAR chỉ khác tên gọi”

Sai: chúng khác về cách ghi dependency và classpath roots. Một plain JAR có thể dùng external libs, shaded JAR merge class files, Boot JAR thường dùng nested libs và bootstrap loader.

### “Spring Boot luôn giải nén tất cả JAR con ra thư mục tạm”

Không chính xác. Spring Boot hỗ trợ truy cập nested JAR thông qua abstraction như `NestedJarFile` và không cần unpack toàn bộ dependency ra files trong cách hoạt động thông thường.

### “Bất kỳ tên package/class bị thiếu nào đều do nested-JAR limitation”

Không chính xác. `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, `UnsupportedClassVersionError` và `IllegalAccessError` có nguyên nhân khác nhau; cần xem stack trace, version, loader và archive layout trước khi kết luận.

## 9. Quy trình chẩn đoán dự án thật

Nếu dự án đã được build thành một JAR, có nested dependencies, nhưng không tìm được class:

1. **Xem cấu trúc archive thực tế:** dùng `jar --list --file app.jar` hoặc công cụ ZIP. Thư viện là file ngoài, JAR lồng dưới `BOOT-INF/lib`, hay classes merge trực tiếp?
2. **Đọc manifest:** `Main-Class` là class ứng dụng, Boot launcher hay launcher riêng? Có `Start-Class` khi dùng format của Spring Boot? Manifest có `Class-Path` external phù hợp không?
3. **Kiểm tra lệnh launch thật:** `java -jar`, `java -cp`, IDE, `gradlew run`, `bootRun`, script container có thể tạo loader/classpath khác nhau.
4. **Xác định loader đang tìm class:** `ClassLoader.getSystemClassLoader()` có phải loader chứa nested dependencies không? Framework có child/special loader không? In `getClassLoader()` của class đã được nạp nếu có thể.
5. **Đối chiếu class name và entry:** tìm đường `demo/lib/Helper.class` ở root của JAR được loader hỗ trợ hay chỉ nằm trong `helper.jar` là một entry?
6. **Nếu dùng Spring Boot:** chạy đúng Boot launcher/package format phù hợp với version, tránh bỏ qua bootstrapping bằng cách chạy thẳng `Start-Class` từ root outer JAR.
7. **Nếu dùng URLClassLoader thuần JDK:** truyền URL của **file JAR thật/directory thật**; đừng giả định loader tự expand nested JARs.
8. **Nếu cần sửa packaging:** chọn external libs + launch script, shaded JAR hoặc framework-compatible nested JAR có launcher; kiểm thử từ artifact phát hành, không chỉ trong IDE.
9. **Nếu vẫn lỗi sau khi tìm được class:** kiểm tra dependencies bắc cầu, phiên bản, JPMS exports, loader identity và lỗi liên kết/initialization, không chỉ vị trí JAR.

### Công cụ thường dùng

~~~sh
jar --list --file app.jar
jar --describe-module --file app.jar
java -Xlog:class+load=info -jar app.jar
~~~

`jar --describe-module` hữu ích khi liên quan JPMS; không bắt buộc mọi executable archive là named module. `-Xlog:class+load` trên JDK HotSpot hiện đại giúp quan sát nguồn class đang load, nhưng output dài và phụ thuộc JDK; không dùng như stdout cố định của demo.

### Câu hỏi khi gặp stack trace

| Triệu chứng | Kiểm tra trước |
|---|---|
| `ClassNotFoundException: demo.lib.Helper` từ `URLClassLoader` | URL search path; class có ở JAR root hay chỉ bên trong nested JAR? |
| `NoClassDefFoundError: demo/lib/Helper` khi chạy plain outer JAR | Runtime loader thiếu dependency, archive layout và nguyên nhân gốc |
| `ClassNotFoundException` khi chạy Boot `Start-Class` bằng `-cp` | Có bỏ qua Boot launcher hoặc sai layout `BOOT-INF/classes` không? |
| Chạy `bootRun` tốt, `java -jar` thất bại | Artifact đã đóng gói đúng `bootJar` chưa? Version/manifest/loader có đúng? |
| `NoSuchMethodError` mặc dù class được tìm thấy | Phiên bản dependency compile/runtime, ABI mismatch |
| `ClassCastException` với cùng binary class name | Class có bị hai loaders định nghĩa thành hai runtime types không? |

## 10. Tự kiểm tra kiến thức

1. Vì sao `jar --list --file outer.jar` liệt kê `lib/helper.jar` nhưng không liệt kê `demo/lib/Helper.class` bên trong JAR con như một entry trực tiếp?
2. `getResource("BOOT-INF/lib/helper.jar") != null` chứng minh điều gì? Điều gì nó **không** chứng minh?
3. `URLClassLoader` tiêu chuẩn nhận URL trỏ đến một directory hoặc JAR file bên ngoài. Vì sao nó không tự duyệt mọi JAR entry trong archive ngoài?
4. Sự khác nhau giữa `app-all.jar` shaded và `app-nested.jar` nested là gì?
5. Khi chạy `java -jar app.jar`, JVM dựa trên manifest attribute nào để chọn main class?
6. Vì sao không nên đưa `BOOT-INF/classes/com/example/App.class` vào outer JAR rồi mong `java -cp outer.jar com.example.App` tự tìm thấy?
7. Spring Boot `JarLauncher` chịu trách nhiệm gì trước khi gọi `Start-Class`?
8. Ký hiệu `jar:nested:...` có phải giao thức URL chung được mọi JDK `URLClassLoader` mặc định hỗ trợ không?
9. Vì sao trích JAR con thành file thật rồi đưa URL file đó vào `URLClassLoader` làm phép thử thành công?
10. Chỉ cần đặt `BOOT-INF/lib/helper.jar` trong archive và đổi `Main-Class` thành app main class có đủ để tạo Spring Boot-compatible executable JAR không?
11. Một framework có bắt buộc phải giải nén mọi nested JAR ra disk không? Nêu cơ chế thay thế.
12. Khi muốn chọn giữa external libs, shaded JAR và framework launcher, bạn cân nhắc tính gọn của artifact, khả năng cập nhật library, rủi ro merge resource và khả năng chạy độc lập ra sao?
13. Hai bước nào kiểm chứng được **archive layout** và **loader thực sự dùng** khi lỗi chỉ xuất hiện sau deploy?
14. Vì sao `java.class.path` không phản ánh đầy đủ những JAR mà framework custom loader có thể tìm thấy?
15. Nếu loader tìm được class nhưng method bị thiếu, đó còn là giới hạn nested JAR hay cần điều tra version/ABI?

**Tiêu chí hoàn thành:** tự tạo và chạy `outer.jar` của mục 6; dự đoán chính xác bốn dòng stdout; phân biệt được “JAR con là resource” với “JAR con là classpath entry”; giải thích đúng vai trò Boot launcher hoặc launcher chuyên dụng và lựa chọn được một packaging/runtime path nhất quán.

## 11. Tài liệu gốc để tra cứu

- [Java SE 17 — `URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): cơ chế tìm từ URL của JAR/directory và delegation.
- [Java SE 21 — `JarURLConnection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/JarURLConnection.html): ngữ nghĩa JAR URL của JDK.
- [Java SE 21 — Java launcher `java`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-cp`, `-jar`, manifest/main class và module path.
- [Spring Boot — Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html): vì sao nested JAR không phải tính năng nạp class tiêu chuẩn và layout `BOOT-INF`.
- [Spring Boot — NestedJarFile](https://docs.spring.io/spring-boot/specification/executable-jar/jarfile-class.html): cách Boot truy cập nested archive và URL/connection.
- [Spring Boot — Launching Executable Jars](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html): `JarLauncher`, `Main-Class` và `Start-Class`.

Quy tắc trình bày dùng hợp đồng của JDK và Spring Boot được tài liệu hóa; ví dụ thực nghiệm được biên dịch bằng `javac --release 17` và chạy bằng Java, không cần framework. Dạng URL và tên launcher cụ thể phải được đối chiếu với phiên bản framework đang sử dụng.