# Khám phá `BOOT-INF/classes`, `BOOT-INF/lib` và các lớp Spring Boot Loader trong JAR thực thi

## 1. Mục tiêu: nhìn vào JAR và hiểu chính xác cách `java -jar` chạy Spring Boot

Một ứng dụng Spring Boot có thể được đóng gói thành **executable JAR** chứa mã ứng dụng, resource, thư viện runtime và mã **Spring Boot Loader**. Thay vì chỉ nhớ lệnh `java -jar app.jar`, người học cần hiểu **mỗi thành phần nằm ở đâu, vì sao được đặt như vậy, và trình tự JVM tìm được `main()` của ứng dụng**.

Bài này tập trung vào ba khu vực:

- **`BOOT-INF/classes/`**: class và resource **của ứng dụng** được build từ main source set.
- **`BOOT-INF/lib/`**: các JAR **phụ thuộc runtime** được đặt dưới dạng *nested JARs*, vẫn giữ cấu trúc archive riêng của chúng.
- **`org/springframework/boot/loader/...`** ở **gốc archive**: các class của Spring Boot Loader dùng làm entrypoint và xây dựng classloader có khả năng truy cập hai khu vực trên.

Một executable JAR điển hình còn có `META-INF/MANIFEST.MF` khai báo `Main-Class` và `Start-Class`; có thể có `BOOT-INF/classpath.idx` hoặc `BOOT-INF/layers.idx` tùy cách đóng gói.

**Kết luận quan trọng:** Java không tự động hiểu rằng `BOOT-INF/classes` là classpath và không có cơ chế chuẩn để nạp trực tiếp các JAR lồng sâu trong một JAR. Spring Boot Loader là lớp khởi động bổ sung giải quyết chính vấn đề này.

### Ba câu hỏi cần trả lời sau bài học

1. Khi mở `jar tf app.jar`, bạn xác định được class ứng dụng, file cấu hình, thư viện runtime và code Boot Loader không?
2. Vì sao manifest trỏ `Main-Class` tới `JarLauncher` thay vì class `@SpringBootApplication` của bạn?
3. Tại sao một **plain JAR** và một **Spring Boot executable JAR** cùng có đuôi `.jar` nhưng không thể chạy theo cùng cách?

Các ví dụ dùng **Java 17** và **Spring Boot 3.3.13** để giải thích package/class name nhất quán; đây là bộ phiên bản minh họa, **không phải tuyên bố phiên bản mới nhất**. Các phiên bản khác, đặc biệt trước Spring Boot 3.2, có thể dùng package/tên launcher khác. Luôn quan sát manifest và nội dung JAR **thực tế** thay vì sao chép tên class launcher từ một tutorial khác.

## 2. Một executable JAR của Spring Boot trông như thế nào?

Đây là sơ đồ **khái niệm** của một executable JAR sau `spring-boot:repackage` (Maven) hoặc `bootJar` (Gradle). Tên artifact/version phụ thuộc project:

~~~text
hello-boot-0.0.1-SNAPSHOT.jar
|
+-- META-INF/
|   +-- MANIFEST.MF
|
+-- org/springframework/boot/loader/
|   +-- launch/
|   |   +-- JarLauncher.class
|   |   +-- LaunchedClassLoader.class
|   |   +-- ...
|   +-- jar/
|   |   +-- NestedJarFile.class
|   |   +-- ...
|   +-- ...
|
+-- BOOT-INF/
    +-- classes/
    |   +-- com/example/hello/HelloApplication.class
    |   +-- application.properties
    |   +-- static/...             (nếu có)
    |   +-- templates/...          (nếu có)
    |
    +-- lib/
    |   +-- spring-boot-3.3.13.jar
    |   +-- spring-context-<resolved-version>.jar
    |   +-- ...                    (các runtime JAR thực tế)
    |
    +-- classpath.idx             (tùy cấu hình)
    +-- layers.idx                (tùy cấu hình)
~~~

Các tên thư viện ở sơ đồ có mục đích minh họa; file chính xác được lấy từ dependency resolution của project. Cấu trúc **thư mục** của archive tương đối ổn định, còn tập dependency khác nhau theo starter, scope, excluded dependencies, plugin và module.

| Vị trí | Vai trò | Được tạo từ đâu? | Đọc bằng cách nào? |
| --- | --- | --- | --- |
| `META-INF/MANIFEST.MF` | Metadata entrypoint, version và thông tin archive. | Jar packaging/Spring Boot build plugin. | `unzip -p app.jar META-INF/MANIFEST.MF` hoặc giải nén mục này bằng `jar xf`. |
| `BOOT-INF/classes/` | Production `.class` và resource của project. | `src/main/java`, `src/main/resources`, annotation/generated output đã được build. | `jar tf app.jar` rồi lọc theo prefix. |
| `BOOT-INF/lib/` | Dependency JAR được đóng trong outer JAR. | Runtime classpath được build tool resolve. | `jar tf app.jar` để xem tên nested JAR; trích riêng một nested JAR để xem bên trong. |
| `org/springframework/boot/loader/` | Boot loader bootstrap/launcher và loader infrastructure. | Mã loader được Maven/Gradle Spring Boot plugin thêm vào executable archive. | Lọc `jar tf` theo prefix này. |
| `BOOT-INF/classpath.idx` | Chỉ dẫn thứ tự classpath entries khi launcher chạy bằng `java -jar`. | Có thể do packaging plugin tạo. | Đọc entry nếu có; không mặc nhiên bắt buộc. |
| `BOOT-INF/layers.idx` | Metadata phân chia archive thành các layer phục vụ container image/extraction. | Tính năng layered archive của build plugin. | Đọc index nếu có; không dùng như danh sách dependency classpath thông thường. |

**Cẩn trọng với thuật ngữ:** “fat JAR”, “uber JAR”, “runnable JAR” thường được dùng lẫn nhau. Trong Spring Boot, điểm đặc trưng ở đây là **dependency JARs được lồng nguyên dạng**, khác cách một shaded JAR có thể gộp/relocate các `.class` của nhiều dependency vào một không gian tên phẳng.

## 3. `BOOT-INF/classes`: ứng dụng của bạn nằm ở đâu?

Khi Maven hoặc Gradle biên dịch mã chính của project, output thường nằm tạm ở:

- Maven: `target/classes/com/example/hello/HelloApplication.class`.
- Gradle: `build/classes/java/main/com/example/hello/HelloApplication.class` và resource ở `build/resources/main/`.

Khi đóng executable JAR, những output chính này được đưa vào **`BOOT-INF/classes/`**, chẳng hạn:

~~~text
BOOT-INF/classes/com/example/hello/HelloApplication.class
BOOT-INF/classes/com/example/hello/Greeter.class
BOOT-INF/classes/application.properties
~~~

### 3.1. `BOOT-INF/classes` không phải thư mục bình thường trên đĩa

Khi nhìn file `hello-boot.jar` trong file explorer, bạn chỉ thấy **một file archive**. Đường dẫn `BOOT-INF/classes/...` là **entry bên trong ZIP/JAR**, không phải một folder được Java tự tạo bên cạnh archive.

Điều này quan trọng khi viết code đọc resource:

~~~java
// Đọc resource trên classpath: tương thích với cách đóng gói chuẩn.
try (var stream = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream("application.properties")) {
    if (stream == null) {
        throw new IllegalStateException("Resource not found");
    }
    // Xử lý stream nếu ứng dụng thực sự cần.
}
~~~

Đoạn này chỉ là **mảnh Java minh họa resource loading**, không phải chương trình độc lập. Khi ứng dụng được chạy qua Boot Loader, `BOOT-INF/classes` thuộc runtime classpath của ứng dụng nên resource có thể được tìm thấy. Với mã ứng dụng, thường dùng Spring `Environment`/`@ConfigurationProperties` để đọc cấu hình thay vì mở file thủ công.

Phản ví dụ phổ biến:

~~~java
// Không đúng khi resource chỉ tồn tại bên trong executable JAR:
new java.io.File("BOOT-INF/classes/application.properties");
~~~

`File` trỏ một path trên **filesystem**, không trỏ tới entry bên trong JAR. Lệnh này có thể không tồn tại dù resource đã được đóng trong archive. Đừng ép resource trên classpath phải có `File`; dùng `getResourceAsStream`, URL/resource abstraction hoặc trích ra nơi thích hợp.

### 3.2. Main code, test code và generated output khác nhau

- `src/main/java` và `src/main/resources` là đầu vào sản xuất, thường đi vào `BOOT-INF/classes` sau biên dịch/xử lý resource.
- `src/test/java` và `src/test/resources` **không** mặc nhiên được đóng vào executable runtime JAR. Nếu thấy class test trong archive, hãy kiểm tra source sets và cấu hình packaging tùy biến.
- Dependency chỉ có test scope/`testImplementation` không được đưa vào `BOOT-INF/lib` của executable JAR thông thường.
- Generated classes/resources có thể có mặt nếu build đã nối chúng vào main output.
- `application.properties`/`application.yml` có thể nằm tại `BOOT-INF/classes` nếu source có file tương ứng; **không phải mọi project bắt buộc có**.

Để tìm main class theo package, hãy lọc `jar tf` với đường dẫn thật, không chỉ dò chuỗi `Application`: một module có thể có nhiều `@Configuration` hoặc class name khác.

## 4. `BOOT-INF/lib`: các dependency JAR lồng nhau

Một Spring Boot Web app có thể cần Spring Framework, Jackson, embedded servlet container và logging. Đóng tất cả dependency classes vào classpath bên ngoài theo cách truyền thống sẽ đòi bạn phân phối nhiều file JAR cùng script classpath. Spring Boot executable JAR thường gói **từng dependency JAR như một entry** trong `BOOT-INF/lib`:

~~~text
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/spring-core-<version>.jar
BOOT-INF/lib/spring-web-<version>.jar
BOOT-INF/lib/<embedded-server>.jar
BOOT-INF/lib/<logging-dependency>.jar
...
~~~

Đây là **tên mẫu**, không phải output bắt buộc. Version của từng dependency cần đọc từ manifest/dependency tree hoặc tên JAR thật trong archive, không đoán từ version Boot.

### 4.1. Nested JAR khác gì một thư viện được giải nén?

**Nested JAR:**

~~~text
outer-app.jar
  +-- BOOT-INF/lib/library-a-1.0.jar
        (là một file JAR hoàn chỉnh nằm bên trong outer-app.jar)
~~~

**Shaded/flattened JAR:**

~~~text
outer-app.jar
  +-- com/vendor/a/ClassA.class
  +-- com/vendor/b/ClassB.class
        (dependency classes được gộp trực tiếp vào outer archive)
~~~

Spring Boot Loader giữ nested JAR riêng, hỗ trợ tìm dependency theo từng archive, giảm nhu cầu gộp trùng các file resource/class trong quá trình build. Nhưng nested JAR **không tự làm xung đột dependency biến mất**: nếu hai version của cùng thư viện cùng được đưa vào runtime classpath, thứ tự load/compatibility vẫn cần xử lý.

### 4.2. Vì sao JDK không đủ để nạp JAR lồng JAR?

Cú pháp chuẩn `java -jar outer.jar` yêu cầu JVM đọc `META-INF/MANIFEST.MF` và chạy `Main-Class`. Java classpath tiêu chuẩn không có quy tắc “tự coi từng file `BOOT-INF/lib/*.jar` đang nằm trong một file ZIP là một classpath entry”.

Ví dụ truyền thống:

~~~bash
java -cp "lib/*:classes" com.example.hello.HelloApplication
~~~

đòi `lib/` và `classes/` có thật trên filesystem (đồng thời cách phân tách classpath khác nhau giữa Linux/macOS và Windows). Cách đó **không áp dụng nguyên xi** với `BOOT-INF/lib` nằm bên trong outer JAR.

Boot Loader bổ sung khả năng truy cập nested JAR mà không buộc dự án tự giải nén tất cả dependency trước khi chạy.

### 4.3. Quy tắc ZIP: nested JAR entry cần `STORED`

Theo đặc tả Spring Boot Loader, **ZIP entry của một nested JAR trong outer archive** cần dùng phương thức `ZipEntry.STORED` (không nén lại ở cấp entry ngoài). Điều này giúp loader seek trực tiếp tới vùng dữ liệu nested archive. **Bên trong** nested JAR, các class/resource vẫn có thể được nén theo chuẩn JAR; các entry khác của outer JAR cũng có thể được nén.

Đừng nhầm “STORED” là “Spring Boot không nén dependency”. Nó chỉ là yêu cầu cho **entry bao lấy nested JAR**, để loader truy cập vị trí dữ liệu hiệu quả. Vì vậy, khi xây archive bằng một ZIP tool tùy ý hoặc script tự viết, thao tác repack ZIP không giữ nguyên yêu cầu này có thể làm JAR trông vẫn mở được bằng `jar tf` nhưng không chạy được qua Spring Boot Loader.

**Khuyến nghị:** để `spring-boot-maven-plugin` hoặc `BootJar` tạo layout phù hợp. Không tự thao tác outer ZIP trong production pipeline trừ khi biết rõ chuẩn loader và có smoke test `java -jar` sau biến đổi.

## 5. Các lớp Boot Loader: tại sao nằm ở gốc JAR?

Khi gọi:

~~~bash
java -jar hello-boot-0.0.1-SNAPSHOT.jar
~~~

Java launcher sẽ đọc thuộc tính `Main-Class` từ manifest. Ở Spring Boot 3.3 executable JAR thông thường, entrypoint không phải class ứng dụng mà là:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.hello.HelloApplication
~~~

**Cách hiểu đúng:**

- `Main-Class` = **bootstrap class** mà JVM biết cách gọi trực tiếp từ JAR. Với Spring Boot 3.3, đó thường là `org.springframework.boot.loader.launch.JarLauncher`.
- `Start-Class` = **main class của ứng dụng**, nơi có `public static void main(String[] args)` và gọi `SpringApplication.run(...)`.
- Boot Loader tìm `Start-Class`, dựng runtime classpath và gọi main của ứng dụng sau khi có classloader phù hợp.

**Vì sao Boot Loader nằm ở gốc `org/...`?** JVM khởi chạy từ outer JAR phải có thể tìm được `Main-Class` **ngay trên classpath của archive ngoài**. Nếu chỉ đặt `JarLauncher.class` dưới `BOOT-INF/classes`, JVM chưa có logic bổ sung để biết vị trí đó nên không thể bắt đầu. Vì vậy **bootstrap code ở gốc**, còn **application code ở `BOOT-INF/classes`**.

### 5.1. Các class/nhóm class đáng nhận diện

| Class/nhóm | Vai trò khái niệm | Điều cần nhớ |
| --- | --- | --- |
| `org.springframework.boot.loader.launch.JarLauncher` | Entrypoint cho executable JAR, khởi tạo classpath cố định của JAR layout. | Tìm app classes ở `BOOT-INF/classes` và dependency JARs ở `BOOT-INF/lib`. |
| `org.springframework.boot.loader.launch.Launcher` | Cơ sở chung của launcher. | Hỗ trợ thiết lập classloader và gọi app main class. |
| `org.springframework.boot.loader.launch.LaunchedClassLoader` | Classloader do launcher dùng cho ứng dụng đã khởi chạy. | Có khả năng load classes/resources từ classpath do Boot Loader thiết lập. |
| `org.springframework.boot.loader.jar.NestedJarFile` | Hỗ trợ truy cập dữ liệu từ nested JAR/outer archive. | Không phải dependency nghiệp vụ của app; là chi tiết runtime packaging. |
| `org.springframework.boot.loader.launch.WarLauncher` | Launcher cho executable WAR. | WAR dùng đường dẫn `WEB-INF`, không dùng đúng JAR layout. |
| `org.springframework.boot.loader.launch.PropertiesLauncher` | Launcher linh hoạt hơn cho cấu hình path ngoài nếu được sử dụng. | Chỉ xuất hiện và được chọn khi kiểu launch/layout tương ứng được cấu hình; không mặc nhiên cần trong mọi app. |

Với **Spring Boot 3.3.13**, package `...loader.launch.JarLauncher` được xác nhận trong API của phiên bản. Các tài liệu Boot 2.x hoặc Boot 3.1 trở về trước có thể đưa ví dụ `org.springframework.boot.loader.JarLauncher` (không có phân đoạn `launch`), nên **không dùng chúng để sửa manifest của JAR 3.3**.

### 5.2. Luồng khởi động thực tế

~~~mermaid
flowchart TD
  CMD["java -jar hello-boot.jar"] --> MF["JVM đọc META-INF/MANIFEST.MF"]
  MF --> ML["Main-Class: JarLauncher (Boot Loader root classes)"]
  ML --> CL["Thiết lập runtime classpath / LaunchedClassLoader"]
  CL --> APP["BOOT-INF/classes: application classes/resources"]
  CL --> DEPS["BOOT-INF/lib: nested dependency JARs"]
  CL --> ST["Đọc Start-Class"]
  ST --> MAIN["Gọi HelloApplication.main(args)"]
  MAIN --> SB["SpringApplication.run: tạo Spring context"]
  SB --> READY["HTTP app ready / job starts"]
~~~

Lưu ý sơ đồ đơn giản hóa nhiều chi tiết xử lý manifest, nested URL và loading. Điểm phải nhớ là **JVM gọi loader trước**, không nhảy thẳng vào ứng dụng nằm trong `BOOT-INF/classes`.

### 5.3. `java -cp app.jar MyApplication` vì sao thường thất bại?

~~~bash
# Phản ví dụ: không nên dùng cho JAR đã đóng theo layout Spring Boot
java -cp hello-boot-0.0.1-SNAPSHOT.jar com.example.hello.HelloApplication
~~~

Classpath tiêu chuẩn với outer JAR không tự nhận diện `BOOT-INF/classes` làm classpath root. Do đó JVM có thể báo `ClassNotFoundException` hoặc không tìm thấy main class, dù `jar tf` cho thấy file `BOOT-INF/classes/com/example/hello/HelloApplication.class` tồn tại.

Lệnh đúng để kiểm chứng executable Boot JAR là:

~~~bash
java -jar hello-boot-0.0.1-SNAPSHOT.jar --server.port=18085
~~~

Không cần thêm thủ công `BOOT-INF/lib/*.jar` vào `-cp` khi launcher đã xử lý. Lưu ý một số tùy biến `PropertiesLauncher` hoặc kiểu launch khác có quy tắc khác; bài này đang giải thích **JarLauncher layout mặc định**.

### 5.4. Context ClassLoader và thư viện bên thứ ba

Một số code reflection/service loading dùng context classloader của thread. Spring Boot Loader khuyến nghị truy cập class/resource qua `Thread.currentThread().getContextClassLoader()` hoặc các Spring resource abstractions khi thích hợp. Không nên cố buộc `ClassLoader.getSystemClassLoader()` tìm nested dependency, vì system classloader ban đầu không có đầy đủ classpath mà Boot Loader dựng.

Khi một thư viện báo không tìm thấy resource/class trong khi `BOOT-INF/lib` đã chứa JAR, hãy kiểm tra nó sử dụng classloader nào, có đòi path filesystem thật hay không, và có yêu cầu native library/temp extraction không. Tránh phản ứng bằng cách copy dependency JAR lung tung vào root archive.

## 6. Manifest là bản đồ để biết JAR có thể chạy thế nào

Một JAR tiêu chuẩn có manifest tại `META-INF/MANIFEST.MF`. Ở Spring Boot executable JAR, ví dụ minh họa:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.hello.HelloApplication
Spring-Boot-Version: 3.3.13
~~~

Các trường khác có thể được thêm bởi build plugin và cấu hình project (ví dụ implementation metadata, các đường dẫn Spring Boot, build tools, classpath index). **Không yêu cầu manifest của mọi JAR có đúng từng dòng ở trên**. Điều bắt buộc với tình huống `java -jar` là entrypoint phù hợp; với layout Boot JAR thông thường `Start-Class` chỉ ra application main class.

### 6.1. Phân biệt Main-Class và Start-Class

Hỏi: “Tôi đã đánh dấu `@SpringBootApplication`, tại sao manifest không ghi lớp ấy ở `Main-Class`?”

Trả lời: vì launcher cần mở classpath từ `BOOT-INF/classes` và `BOOT-INF/lib` **trước** khi JVM có thể load app class. `Main-Class` trỏ tới loader class ở root; `Start-Class` trỏ tới ứng dụng. Nếu xây một **plain JAR** có `Main-Class` trực tiếp trỏ tới app, nó chỉ chạy được nếu mọi dependency được cung cấp theo cách tương thích ở ngoài; đuôi `.jar` tự nó không làm app độc lập.

### 6.2. Kiểm tra manifest bằng CLI

Nếu máy có `unzip` (macOS/Linux thường có nhưng không bảo đảm):

~~~bash
unzip -p target/hello-boot-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
~~~

Hoặc chỉ dùng JDK `jar`:

~~~bash
# Thực hiện trong một thư mục inspect riêng để không ghi đè file dự án.
mkdir -p jar-inspect
cd jar-inspect
jar xf ../target/hello-boot-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

Lệnh trên ví dụ Maven: `target/` nằm ở root trước khi `cd`. Nếu dùng Gradle, sửa path tương ứng từ `build/libs/`. Trên Windows có thể dùng PowerShell `Get-Content META-INF/MANIFEST.MF` sau khi extract. Dùng **thư mục inspect mới** để tránh ghi đè dữ liệu trong working directory khi dùng `jar xf`.

Tìm `Main-Class` và `Start-Class` **thực tế**. Nếu vắng `Main-Class`, `java -jar` thường báo `no main manifest attribute`. Nếu `Main-Class` có tên launcher cũ hoặc class không nằm trong archive, phải xem lại plugin configuration/packaging trước khi thủ công sửa manifest.

## 7. Thực hành runnable: tạo một executable JAR nhỏ

Ví dụ dùng một Spring Boot Web app trả `pong` để việc quan sát archive gắn với hành vi chạy thật. **Dùng một trong hai cách build Maven hoặc Gradle**, không cần cả hai Wrapper trong cùng project nếu nhóm không chủ ý hỗ trợ cả hai.

Cấu trúc mã:

~~~text
hello-boot/
  pom.xml                           (nếu Maven)
  # hoặc settings.gradle/build.gradle (nếu Gradle)
  src/main/java/com/example/hello/HelloApplication.java
  src/main/resources/application.properties
  src/test/java/com/example/hello/HelloApplicationTest.java
~~~

### 7.1. Java source: điểm vào và HTTP endpoint

File `src/main/java/com/example/hello/HelloApplication.java`:

~~~java
package com.example.hello;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class HelloApplication {

    public static void main(String[] args) {
        SpringApplication.run(HelloApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=hello-boot
server.port=8080
~~~

Class path trong JAR sẽ là `BOOT-INF/classes/com/example/hello/HelloApplication.class`, và resource sẽ là `BOOT-INF/classes/application.properties` nếu cấu hình packaging thông thường. Giá trị `8080` trong resource có thể được override qua `--server.port=18085` khi chạy.

Test `src/test/java/com/example/hello/HelloApplicationTest.java`:

~~~java
package com.example.hello;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class HelloApplicationTest {

    @Test
    void pingReturnsPong() {
        assertEquals("pong", new HelloApplication().ping());
    }
}
~~~

Test trên kiểm tra **method logic** mà không khởi động Spring context, vì vậy nó không thay thế HTTP smoke test của executable JAR. Nó đủ để người học phân biệt `src/test/java` với `src/main/java` và quan sát rằng test class **không** được đóng vào `BOOT-INF/classes`.

### 7.2. Maven: POM hoàn chỉnh để `repackage`

File `pom.xml`:

~~~xml
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
    <artifactId>hello-boot</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

Với Boot starter parent, plugin được quản lý và execution `repackage` đã được cấu hình trong chuỗi parent. Khi khai báo plugin như trên, `mvn package` tạo archive thông thường rồi Spring Boot plugin repackaging thành **executable archive**.

Lệnh (nếu dự án đã có Maven Wrapper):

~~~bash
./mvnw clean package

# File output theo GAV ví dụ, xác nhận lại tên thật ở target/
jar tf target/hello-boot-0.0.1-SNAPSHOT.jar
~~~

**Đầu ra dự kiến:** package build có test `HelloApplicationTest` được phát hiện và pass; `target/hello-boot-0.0.1-SNAPSHOT.jar` chứa launcher và `BOOT-INF`. Maven có thể còn tạo `*.jar.original` là original plain JAR trước repackaging; không dùng file ấy làm executable artifact.

Nếu dự án **không dùng Spring Boot starter parent mà chỉ import BOM**, phải khai báo `spring-boot-maven-plugin` **version** và binding goal `repackage` phù hợp; BOM chỉ quản lý dependency versions, không tự thêm build plugin execution.

### 7.3. Gradle: `bootJar` tạo cùng kiểu layout

`settings.gradle`:

~~~groovy
rootProject.name = 'hello-boot'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Lệnh (nếu dự án đã có Gradle Wrapper tương thích):

~~~bash
# Chạy tests/check rồi đóng gói, theo đồ thị thực tế của build
./gradlew clean build

# Chỉ yêu cầu task tạo executable JAR
./gradlew bootJar

# Kiểm tra archive được bootJar tạo:
jar tf build/libs/hello-boot-0.0.1-SNAPSHOT.jar
~~~

`bootJar` tạo executable JAR theo layout Boot. Trong dự án Java plugin, `jar` có thể còn tạo một **plain JAR** (thường mang classifier `plain`), ví dụ `hello-boot-0.0.1-SNAPSHOT-plain.jar`. Không nhầm chúng: `jar tf` cho phép phân biệt dựa vào nội dung, và `java -jar` kiểm tra được khả năng chạy.

### 7.4. Hai lệnh đóng gói, cùng bài kiểm chứng cấu trúc

Dù dùng Maven hay Gradle, cần xác nhận ít nhất:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/hello/HelloApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/<các-dependency-thực-tế>.jar
~~~

Không yêu cầu thứ tự entry giống sơ đồ; `jar tf` thường in nhiều dòng và thứ tự tùy cách tạo archive. Nếu loader version khác, đường dẫn launcher chính xác được xác định bằng manifest của file thực tế.

## 8. Khám phá JAR từ ngoài vào trong bằng lệnh thật

**Nguyên tắc:** trước tiên tìm đúng file JAR, rồi đọc manifest, phân loại entry theo prefix và sau cùng mới trích một nested dependency để phân tích. Không chạy lệnh extract lên toàn bộ workspace và không sửa artifact đã được build trước khi thực hiện smoke test.

### 8.1. Bước 1 — danh sách các entry

Maven (đường dẫn ví dụ):

~~~bash
jar tf target/hello-boot-0.0.1-SNAPSHOT.jar
~~~

Gradle:

~~~bash
jar tf build/libs/hello-boot-0.0.1-SNAPSHOT.jar
~~~

`jar tf` **chỉ liệt kê các entry ở cấp archive đang được mở**. Khi thấy `BOOT-INF/lib/spring-core-....jar`, nó hiển thị **file nested JAR như một entry**, không tự liệt kê mọi `.class` ở bên trong nested JAR đó.

Bộ lọc macOS/Linux (cần `grep`):

~~~bash
JAR=target/hello-boot-0.0.1-SNAPSHOT.jar

# Lấy các entry chính và bỏ bớt các class/metadata không cần quan sát ngay
jar tf "$JAR" | grep -E '^(META-INF/MANIFEST.MF|BOOT-INF/classes/|BOOT-INF/lib/|org/springframework/boot/loader/)'
~~~

Nếu output quá lớn, lọc riêng từng lớp:

~~~bash
jar tf "$JAR" | grep '^BOOT-INF/classes/'
jar tf "$JAR" | grep '^BOOT-INF/lib/'
jar tf "$JAR" | grep '^org/springframework/boot/loader/'
~~~

PowerShell (không cần `grep`):

~~~powershell
$jar = "target/hello-boot-0.0.1-SNAPSHOT.jar"
jar tf $jar | Select-String '^BOOT-INF/classes/'
jar tf $jar | Select-String '^BOOT-INF/lib/'
jar tf $jar | Select-String '^org/springframework/boot/loader/'
~~~

Đổi `$jar` thành đúng đường dẫn nếu dùng Gradle. Các lệnh trên **không chạy ứng dụng**; chúng chỉ đọc archive.

### 8.2. Bước 2 — đọc manifest và kiểm tra launcher

Nếu có `unzip`:

~~~bash
unzip -p "$JAR" META-INF/MANIFEST.MF
~~~

Tìm `Main-Class` và `Start-Class`. Với Boot 3.3.13 ở ví dụ, kỳ vọng:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.hello.HelloApplication
~~~

Nếu không cài `unzip`, dùng JDK `jar xf` trong **thư mục tạm mới**, không giải nén đè vào source:

~~~bash
mkdir -p jar-inspect
cd jar-inspect
jar xf ../target/hello-boot-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

Từ `jar-inspect` quay ra root bằng `cd ..` trước các lệnh kiểm tra archive khác. Với Windows PowerShell, tạo một thư mục kiểm tra và dùng `jar xf`/`Get-Content` tương tự, điều chỉnh dấu đường dẫn.

### 8.3. Bước 3 — xem nested JAR từ `BOOT-INF/lib`

Giả sử `jar tf` đã cho biết **tên chính xác** `BOOT-INF/lib/spring-core-6.x.y.jar`. Ở đây `6.x.y` là ký hiệu, phải thay bằng version thật. Chỉ trích một dependency mà bạn muốn kiểm tra:

~~~bash
# Ví dụ cú pháp sau khi đã thay <version-thuc-te>
unzip -p "$JAR" "BOOT-INF/lib/spring-core-<version-thuc-te>.jar" > spring-core-inspect.jar
jar tf spring-core-inspect.jar
~~~

Trong shell ví dụ trên, chạy các lệnh từ root nơi `$JAR` đã được thiết lập và trích vào thư mục kiểm tra có quyền ghi. **Không dùng trực tiếp literal `<version-thuc-te>` trong shell** vì ký tự ngoặc nhọn nhọn có thể bị hiểu là redirection; thay bằng tên phiên bản thực hoặc dấu file path an toàn trước khi chạy.

Có thể thay `unzip -p` bằng `jar xf` vào thư mục inspect, nhưng khi đó sẽ tạo cả path `BOOT-INF/lib/...` và bạn cần mở nested JAR đã trích bằng một lệnh `jar tf` thứ hai. Việc mở một entry cấp ngoài và sau đó mở nested archive cấp trong là **hai thao tác**, không phải một lần liệt kê tự động.

### 8.4. Bước 4 — kiểm tra file cấu hình đã được đóng

Nếu có file `application.properties` ở source main:

~~~bash
unzip -p "$JAR" BOOT-INF/classes/application.properties
~~~

Nội dung ở đây là resource **sau quá trình build/packaging**, có thể khác với source nếu Maven filtering/Gradle `processResources` đã chạy. Nếu resource được generate hoặc relocate bởi plugin, kiểm tra path thực tế trước khi kết luận thiếu.

Bằng chứng mong đợi ở ví dụ:

~~~properties
spring.application.name=hello-boot
server.port=8080
~~~

Khi chạy `java -jar ... --server.port=18085`, CLI override `8080` mà **không cần sửa file đã đóng gói**. Đây là thực hành đúng cho runtime configuration.

## 9. `NestedJarFile` và cách Spring Boot Loader truy cập nội dung bên trong

Một JAR ngoài thực chất là ZIP archive chứa directory/index các entries. Để load một class từ nested dependency, loader cần giải quyết:

1. `BOOT-INF/lib/spring-core-...jar` nằm ở vị trí byte nào trong **outer JAR**?
2. Bên trong nested JAR, file `org/springframework/.../SomeClass.class` nằm ở vị trí nào?
3. Classloader làm sao đọc resource bytes và định nghĩa class khi classpath entry không phải một file JAR độc lập trên filesystem?

Cơ chế Spring Boot Loader dùng các thành phần như `NestedJarFile` và hỗ trợ URL/protocol thích hợp để ánh xạ nested entry tới vùng dữ liệu trong outer archive, thay vì bắt buộc giải nén tất cả dependency ra thư mục trước khi khởi động.

**Không phải một JVM “đã nạp toàn bộ JAR vào RAM”.** Loader có thể truy cập theo offset/index trong archive và để class loading xảy ra theo nhu cầu. Cách hoạt động cụ thể có thể thay đổi theo phiên bản Boot; người lập trình ứng dụng thông thường chỉ cần phụ thuộc vào **classpath behavior đúng**, không gọi trực tiếp API nội bộ của loader.

### 9.1. URL classpath và các tình huống tương thích

Boot Loader hỗ trợ truy cập nested JAR resources qua các URL phù hợp với cơ chế của Boot. Một số framework dùng `URLClassLoader`, `ServiceLoader`, reflection hoặc resource scanning; trong điều kiện được hỗ trợ, chúng chạy trên classpath mà Boot Loader dựng.

Nếu một thư viện giả định resource URL bắt buộc có scheme `file:` hoặc cố chuyển JAR resource URL thành `java.io.File`, việc đọc có thể thất bại khi resource nằm trong nested archive. Giải pháp đúng thường là dùng stream/resource abstraction, hoặc (nếu thư viện thật sự cần file vật lý) **trích riêng resource vào temp directory** theo API phù hợp rồi cleanup. Không giải nén cả executable JAR chỉ để che một giả định sai trong code.

### 9.2. Thử `ClassLoader` — đoạn code quan sát

Đây là **đoạn Java minh họa**, không phải chương trình độc lập:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

try (var in = loader.getResourceAsStream("application.properties")) {
    if (in == null) {
        throw new IllegalStateException("Missing application.properties");
    }
    // Có thể đọc file properties từ InputStream mà không cần File vật lý.
}
~~~

Khi project được Spring Boot Launcher khởi động, context classloader có thể tìm resource trên application classpath. Đừng dùng tên `BOOT-INF/classes/application.properties` như resource name truyền vào classloader: đối với code đang chạy, classpath root tương ứng chính là `BOOT-INF/classes/`, vì vậy resource name thường là `application.properties`.

### 9.3. Vì sao có thể thấy nhiều loader classes nhưng không có trong dependency tree?

Spring Boot Loader được đưa vào outer executable archive bởi **plugin packaging**. Nó không nhất thiết được liệt kê như một runtime dependency riêng của project trong cùng ý nghĩa với `spring-web` hoặc `jackson-databind`. Khi so sánh dependency tree với archive content, phân biệt:

- **Build plugin/loader infrastructure** ở root.
- **Resolved runtime dependencies** nằm ở `BOOT-INF/lib`.
- **Application output** nằm ở `BOOT-INF/classes`.

Như vậy, nếu một class loader nằm ở root mà dependency tree không có nó như một direct dependency, đó chưa phải lỗi. Trái lại, nếu toàn bộ `BOOT-INF/lib` trống ở một Spring Boot Web app, cần xem plugin classpath/repackage và dependency scopes thật.

## 10. `classpath.idx` và `layers.idx`: cùng nằm ở BOOT-INF nhưng khác trách nhiệm

Một Spring Boot executable JAR có thể chứa các file index ở `BOOT-INF`. Chúng **không** thay thế `BOOT-INF/classes` hoặc `BOOT-INF/lib`.

### 10.1. `BOOT-INF/classpath.idx` — thứ tự thư viện

Ví dụ **định dạng minh họa**:

~~~text
- "BOOT-INF/lib/example-a-1.0.jar"
- "BOOT-INF/lib/example-b-2.0.jar"
~~~

Classpath index xác định thứ tự entries trên classpath mà Spring Boot Launcher sử dụng **khi archive được thực thi qua `java -jar`**. Nó không phải lệnh bắt Gradle/Maven dùng thứ tự đó trong dev mode và không tự giải quyết conflict dependency.

- `jar tf "$JAR" | grep '^BOOT-INF/classpath.idx$'` để xem index có tồn tại không (macOS/Linux).
- `unzip -p "$JAR" BOOT-INF/classpath.idx` để đọc nội dung nếu có.
- Đọc entries thực tế thay vì dùng tên placeholder.
- Khi app chạy từ IDE hoặc `spring-boot:run`/`bootRun`, classpath của build tool khác; không nên suy mọi trạng thái dev đều dùng index này.

### 10.2. `BOOT-INF/layers.idx` — tách layer để build image

Ví dụ minh họa dạng YAML-like của layer index:

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/example-a-1.0.jar"
  - "BOOT-INF/lib/example-b-2.0.jar"
- "application":
  - "BOOT-INF/classes/"
  - "META-INF/"
~~~

`layers.idx` phân nhóm những file/thư mục của archive thành các layer để công cụ đóng image có thể tái sử dụng cache hiệu quả hơn. Tùy plugin, cấu trúc có thể còn layer `spring-boot-loader` và `snapshot-dependencies`; phần minh họa ở trên **không phải toàn bộ mặc định bắt buộc**.

**Không đánh đồng:**

- `classpath.idx`: metadata liên quan tới **thứ tự classpath** cho Boot launcher.
- `layers.idx`: metadata liên quan tới **phân lớp artifact/container image**.
- Cả hai không tự nêu “đây là dependency bị thiếu” hay “project này đã được security scan”.

Một layered JAR vẫn là **executable JAR**. Nếu không có `layers.idx` trong một archive tùy biến, điều đó không tự chứng minh archive không thể chạy; cần kiểm tra launcher, classes/lib và `java -jar`.

### 10.3. Khi nào layer thực sự hữu ích?

Trong CI/CD với image nhiều lớp, mã ứng dụng thay đổi thường xuyên hơn bộ dependency. Nếu app classes được đặt ở một layer khác dependency JAR, image builder có thể tái sử dụng layer dependency khi chỉ sửa business code. Tuy nhiên hiệu quả cache còn phụ thuộc Dockerfile/buildpacks/layer order thực tế.

Với Spring Boot 3.3 có hỗ trợ extract archive và launcher phù hợp qua các chế độ được tài liệu hướng dẫn. Đây là kỹ thuật tối ưu deployment **bổ sung**; bài học cốt lõi vẫn là hiểu executable archive và đọc đúng `BOOT-INF`. Không tùy tiện chạy lệnh extract jarmode của một phiên bản khác khi chưa xem `java -Djarmode=tools -jar app.jar help` hoặc tài liệu build của dự án.

## 11. So sánh ba loại artifact dễ bị nhầm

| Loại | Cấu trúc chính | Có thể chạy ngay `java -jar` mà không có classpath ngoài? | Khi nào dùng? |
| --- | --- | --- | --- |
| **Plain/library JAR** | Classes/resources thường ở root package paths, dependency không tự nhúng. | **Không mặc định**. Có thể thiếu `Main-Class` hoặc runtime deps. | Thư viện, output trung gian, artifact dành cho ứng dụng khác tiêu thụ. |
| **Spring Boot executable JAR** | Loader ở root; app ở `BOOT-INF/classes`; runtime jars ở `BOOT-INF/lib`; manifest trỏ launcher/Start-Class. | **Có**, khi archive đúng, JDK và runtime config/dependency ngoài phù hợp. | Triển khai Spring Boot standalone. |
| **Shaded/flattened uber JAR** | Nhiều dependency classes được gộp cùng package paths trong một archive. | Tùy manifest/shading config và compatibility. | Một cách phân phối khác, có trade-off conflict/relocation/resource merging. |

**Không chọn artifact bằng kích thước đơn thuần.** Boot executable JAR thường lớn hơn plain JAR vì chứa runtime dependencies, nhưng kích thước lớn nhỏ không xác nhận đúng entrypoint. Hãy kiểm tra **`BOOT-INF` + manifest + smoke test**.

### 11.1. Maven `.jar.original` và Gradle `-plain.jar`

- **Maven:** khi Boot `repackage` xử lý JAR thông thường và thay thế output, có thể giữ bản gốc với suffix `.jar.original`.
- **Gradle:** khi cả `jar` và `bootJar` được tạo, JAR thông thường có thể nhận classifier `plain` và JAR executable thường không có classifier, tùy cấu hình.
- Khi deploy, dùng file **executable Boot JAR** được pipeline công bố; không chọn bằng wildcard rồi lấy file đầu tiên.

Với Gradle:

~~~bash
# Ví dụ để xem file do build tạo, không phải lệnh chọn artifact an toàn cho CI
ls -l build/libs/
~~~

Trong CI cần kiểm tra rõ tên archive/metadata hoặc cấu hình archiveFileName cố định, tránh deploy nhầm `*-plain.jar`.

### 11.2. Executable WAR là biến thể khác

Spring Boot WAR có layout **`WEB-INF/classes`**, `WEB-INF/lib` và có thể `WEB-INF/lib-provided`, dùng `WarLauncher` khi chạy theo kiểu executable WAR. Vì thế, không dùng bộ tiêu chí `BOOT-INF/classes` để kết luận một **WAR** bị lỗi. Bài này chỉ đánh giá **executable JAR**, không áp nguyên xi cho WAR hoặc native image.

## 12. Chạy chính artifact vừa khám phá

Sau khi tạo JAR, đóng mọi instance `spring-boot:run` hoặc `bootRun` đang dùng port muốn thử, rồi chạy **file JAR thực**:

~~~bash
# Maven artifact mẫu:
java -jar target/hello-boot-0.0.1-SNAPSHOT.jar --server.port=18085

# Hoặc Gradle artifact mẫu:
# java -jar build/libs/hello-boot-0.0.1-SNAPSHOT.jar --server.port=18085
~~~

Mở terminal thứ hai:

~~~bash
curl -i http://localhost:18085/ping
~~~

**Kỳ vọng:** HTTP status `200`, body chính xác `pong`. Header/console log không có output cố định do JDK/OS/network/runtime khác nhau. Dừng ứng dụng bằng Ctrl+C sau kiểm thử.

Nếu lệnh `java -jar` chạy thành công và xử lý `GET /ping`, bạn đã kiểm chứng **loader + classpath nested dependencies + application classes + HTTP runtime** cùng phối hợp trên artifact. Tuy nhiên đó vẫn là một phép smoke test, không chứng minh mọi business flow, bảo mật, throughput hay môi trường production được kiểm tra đầy đủ.

### 12.1. Khi log có lỗi trước khi app ready

- Lỗi **`no main manifest attribute`**: kiểm tra đúng executable JAR, plugin repackage/bootJar và manifest.
- Lỗi **`Could not find or load main class org.springframework.boot.loader...JarLauncher`**: Main-Class không phù hợp đường dẫn loader thực tế, archive bị chỉnh hoặc dùng phiên bản loader không tương thích.
- Lỗi **`ClassNotFoundException: com.example.hello.HelloApplication`**: so `Start-Class` với entry `BOOT-INF/classes/com/example/hello/HelloApplication.class`.
- Lỗi **`NoClassDefFoundError`/`ClassNotFoundException` của framework**: kiểm tra dependency có trong `BOOT-INF/lib` và đã được chọn trong runtimeClasspath, scope/exclusion/configuration có đúng không.
- Lỗi **`UnsupportedClassVersionError`**: runtime JDK không hỗ trợ bytecode version mà project đã compile.
- Lỗi Spring context/DB/port: đây có thể là **runtime configuration**, không nhất thiết lỗi loader. Xem cause và resource trong archive.

Trước khi sửa manifest hay giải nén lại, kiểm tra mục tiêu và runtime evidence; nhiều lỗi xuất phát từ nhầm plain JAR với executable JAR.

## 13. Checklist chẩn đoán theo lớp

| Dấu hiệu | Khả năng nguyên nhân | Cách kiểm chứng có thể làm ngay |
| --- | --- | --- |
| `jar tf` thấy `BOOT-INF/classes` nhưng không thấy `org/springframework/boot/loader`. | Archive tự tạo hoặc packaging không chứa Boot Loader đúng layout. | Xem `Main-Class`, `bootJar`/`repackage` và task đã chạy. |
| Có `BOOT-INF/lib` nhưng `jar tf` không liệt kê class bên trong dependency. | `jar tf` mới mở **outer JAR**, chưa mở nested JAR. | Trích riêng nested jar rồi gọi `jar tf` lên file đã trích. |
| Có launcher nhưng thiếu `BOOT-INF/classes/...Application.class`. | Chọn sai main module/source set, build không đưa class vào archive. | Kiểm tra đường dẫn source, compile output, `Start-Class` và packaging task. |
| Manifest ghi `Main-Class` là app class chứ không phải loader. | Có thể là plain JAR hoặc tùy biến executable layout. | Xem mọi entry và chạy `java -jar` theo cơ chế tương ứng. |
| `Start-Class` trỏ một FQCN khác với source. | Khai báo mainClass sai, nhiều main methods hoặc manifest tùy biến. | So `Start-Class` với FQCN từ source và entry trong `BOOT-INF/classes`. |
| Không có `application.properties` dưới BOOT-INF/classes. | File không có ở main resources, bị relocate/filter hoặc source set khác. | Kiểm tra `src/main/resources`, `processResources`/`target/classes`. |
| Có JAR nhưng thiếu thư viện runtime. | Dependency để ở test/provided/compileOnly, bị exclude hoặc bootJar classpath tùy biến. | Maven `dependency:tree`, Gradle `runtimeClasspath`, archive `BOOT-INF/lib`. |
| Thấy hai version của cùng thư viện. | Conflict hoặc cấu hình resolution/custom packaging chưa đúng. | Dependency tree/dependencyInsight và danh sách archive; không tự xóa một JAR trong archive. |
| `java -cp outer.jar ...` báo không tìm thấy app. | JDK classpath không hiểu `BOOT-INF/classes` là root. | Dùng `java -jar` để Boot Loader thiết lập classpath. |
| Thư viện tìm resource bằng `new File(resourceUrl.toURI())` thất bại. | Resource bên trong JAR/nested JAR không phải file vật lý. | Chuyển sang stream/resource APIs hoặc trích riêng theo nhu cầu thực. |
| Có `layers.idx` nhưng ứng dụng fail. | Layer index không bảo đảm launcher/runtime config đúng. | Đọc manifest, libs/classes, smoke test; phân biệt layer với classpath. |
| Repack ZIP bằng tool khác xong JAR không launch. | Có thể mất layout/metadata, compression mode `STORED` hoặc manifest bị thay. | So output plugin gốc với archive sau xử lý, ưu tiên build lại bằng Boot plugin. |
| Dev run hoạt động, packaged JAR fail. | Development classpath và executable archive khác nhau. | So Maven/Gradle dependency scopes, resources, repackage, launcher và runtime config. |
| Chạy trên máy A thành công, máy B lỗi. | Khác JDK, environment variables, profile, port, external service, quyền filesystem. | Ghi JVM version + args + artifact hash + config sources; đừng suy từ JAR structure alone. |

### 13.1. Cần phân biệt lỗi lớp nào?

1. **Build/compile:** Maven/Gradle resolve dependencies và tạo main classes/resource có thành công?
2. **Packaging:** Boot plugin có chạy, manifest có đúng, `BOOT-INF`/loader đầy đủ?
3. **Nested dependency loading:** JAR có đúng library và classloader đọc được không?
4. **Application bootstrap:** `Start-Class` đúng, `SpringApplication.run` tạo context thành công?
5. **Runtime/environment:** port/profile/secret/DB/broker/JDK có đúng không?
6. **Business behavior:** request/job có đáp ứng hợp đồng tối thiểu không?

Một lỗi nằm ở bước 5–6 không nên “sửa” bằng cách tùy tiện di chuyển các entry trong `BOOT-INF/lib`; một lỗi bước 2 cũng không giải quyết bằng việc đổi `server.port`.

## 14. Kiểm chứng với build tools: đừng chỉ dựa vào danh sách file

### 14.1. Maven

~~~bash
./mvnw -version
./mvnw clean verify
./mvnw dependency:tree
jar tf target/hello-boot-0.0.1-SNAPSHOT.jar
~~~

Từ `mvn verify`, đảm bảo test thật được phát hiện và pass; từ `dependency:tree`, xem version/scopes đã resolve. Sau đó kiểm tra `BOOT-INF/lib`: một dependency xuất hiện trong tree nhưng không có trong executable archive có thể là do scope hoặc packaging exclusion hợp lệ, **không mặc nhiên lỗi**.

### 14.2. Gradle

~~~bash
./gradlew --version
./gradlew clean build
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-core
jar tf build/libs/hello-boot-0.0.1-SNAPSHOT.jar
~~~

`dependencyInsight` cho biết version được chọn và lý do (BOM/constraint/conflict resolution). `bootJar` thường đóng dependencies từ runtimeClasspath đúng theo cấu hình plugin. Các configuration như `testImplementation` không được xem là runtime application dependencies.

### 14.3. Lưu artifact và bằng chứng phù hợp

Một gói bàn giao tối thiểu nên giữ:

- Commit/build number và version của Spring Boot build plugin.
- JDK version dùng build và runtime theo yêu cầu tổ chức.
- Lệnh build và report test đã chạy (không chỉ dòng thành công chung).
- Tên archive/đường dẫn chính xác; tùy pipeline có checksum/digest cho traceability.
- Danh sách entry quan trọng: `Main-Class`, `Start-Class`, `BOOT-INF/classes`, `BOOT-INF/lib`, loader.
- Kết quả `java -jar` và smoke test/job outcome.
- Nếu có scan bảo mật/SBOM, dùng metadata/dependency version thật từ artifact thay vì đọc số version dự đoán.

Archive cấu trúc đúng là **điều kiện cần** để loader chạy, không phải bằng chứng đầy đủ về bảo mật và tính sẵn sàng production.

## 15. Bài tập tự thực hành và tiêu chí đạt

### Bài tập A — phân loại 12 entry từ một JAR thật

Dùng `jar tf` với executable JAR tự build và phân loại ít nhất:

- [ ] `META-INF/MANIFEST.MF`.
- [ ] `org/springframework/boot/loader/launch/JarLauncher.class` (hoặc launcher theo manifest/version thực).
- [ ] Một class Boot Loader khác ở root.
- [ ] Application main class ở `BOOT-INF/classes`.
- [ ] Một file resource ở `BOOT-INF/classes` (nếu project có).
- [ ] Ít nhất một JAR `spring-boot-...jar` dưới `BOOT-INF/lib`.
- [ ] Một JAR của Spring Framework dưới `BOOT-INF/lib`.
- [ ] Một JAR server/JSON/logging nếu starter tương ứng được dùng.
- [ ] `BOOT-INF/classpath.idx` nếu có; nếu không có, ghi rõ “không tạo”.
- [ ] `BOOT-INF/layers.idx` nếu có; nếu không có, ghi rõ “không tạo”.
- [ ] `Main-Class` từ manifest.
- [ ] `Start-Class` từ manifest.

Với từng entry, giải thích nó thuộc **application**, **dependency**, **loader**, **manifest** hay **index**. Không ghi tên artifact giả định như thể đã đọc từ JAR thật.

### Bài tập B — mở nested JAR đúng cách

1. Liệt kê `BOOT-INF/lib`, chọn một dependency JAR tồn tại thật.
2. Trích chính entry đó ra một thư mục kiểm tra tách biệt.
3. Mở file trích bằng `jar tf` lần nữa và tìm một package/class bên trong.
4. Giải thích vì sao `jar tf outer.jar` chỉ hiển thị tên nested JAR và vì sao Boot Loader vẫn có thể nạp class từ đó.

### Bài tập C — đối chiếu plain JAR và executable Boot JAR

Với Gradle nếu có cả `jar` và `bootJar`, hoặc Maven có `.jar.original`, so sánh:

| Tiêu chí | Plain JAR | Boot executable JAR |
| --- | --- | --- |
| Main classes ở root hay `BOOT-INF/classes`? | Quan sát thật | Quan sát thật |
| Có `BOOT-INF/lib` không? | Quan sát thật | Quan sát thật |
| Có Boot Loader root classes không? | Quan sát thật | Quan sát thật |
| `Main-Class`/`Start-Class` có gì? | Quan sát thật | Quan sát thật |
| `java -jar` thành công với runtime classpath không cần bổ sung? | Kiểm thử thật | Kiểm thử thật |

Sau đó kết luận tại sao cùng `.jar` nhưng không thể lựa chọn artifact triển khai theo wildcard/tên file ngẫu nhiên.

### Bài tập D — kiểm chứng runtime

1. Chạy `./mvnw clean package` hoặc `./gradlew clean bootJar`.
2. Xác nhận main class và dependencies trong executable archive.
3. Chạy `java -jar ... --server.port=18085`.
4. Gọi `curl -i http://localhost:18085/ping`; ghi HTTP 200 và body `pong` nếu môi trường đáp ứng.
5. Dừng app bằng Ctrl+C; ghi lại tên chính xác của artifact/JDK và nguyên nhân nếu có lỗi.

### Câu hỏi tự kiểm tra

1. Vì sao `HelloApplication.class` ở `BOOT-INF/classes` thay vì thư mục root của archive?
2. Vì sao `Main-Class` phải trỏ Boot Loader, còn `Start-Class` trỏ application?
3. `BOOT-INF/lib/spring-core-....jar` là file hay thư mục? `jar tf` của outer archive có tự liệt kê `.class` bên trong nó không?
4. Spring Boot Loader giải quyết giới hạn nào của Java classpath chuẩn?
5. Tại sao nested ZIP entry thường phải dùng `STORED`?
6. Vì sao `new File("BOOT-INF/classes/application.properties")` không đáng tin khi chạy `java -jar`?
7. `classpath.idx` khác `layers.idx` ở chỗ nào?
8. Vì sao Boot executable JAR khác một shaded JAR?
9. Khi có `NoClassDefFoundError`, bạn kiểm tra `BOOT-INF/lib`, dependency graph và classloader theo thứ tự nào?
10. Vì sao `spring-boot:run` hoặc `bootRun` thành công không đảm bảo packaged JAR chạy thành công?

**Tiêu chí hoàn thành:** người học không chỉ kể tên ba vùng archive mà **tự build**, đọc **manifest và entry thật**, mở được một nested dependency, giải thích luồng Boot Launcher → classloader → `Start-Class` → Spring application, và chạy được **đúng executable JAR** với một phép kiểm chứng hành vi. Nếu thiếu một trong các bằng chứng ấy, ghi rõ phần chưa được xác minh thay vì đánh dấu thành công chung.

## Tài liệu tham khảo chính thức

- [Spring Boot — Executable JAR Format: Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Spring Boot — Launching Executable Jars](https://docs.spring.io/spring-boot/3.4/specification/executable-jar/launching.html)
- [Spring Boot 3.3.13 API — JarLauncher](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/loader/launch/JarLauncher.html)
- [Spring Boot 3.3.13 API — LaunchedClassLoader](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/loader/launch/LaunchedClassLoader.html)
- [Spring Boot 3.3 — Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 — Efficient Deployments](https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html)
- [Java SE 17 — `jar` Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html)

**Ghi nhớ:** `BOOT-INF/classes` là mã/resource của app; `BOOT-INF/lib` là các JAR runtime được lồng lại; **Boot Loader ở gốc JAR** là cầu nối giúp `java -jar` tìm được chúng và gọi `Start-Class`. Tất cả những kiểm tra trong bài là hướng dẫn để thực hành; không mặc nhận kết quả mẫu là log đã được đo trên máy của người học.