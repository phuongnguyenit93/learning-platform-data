# Vì sao JVM cần Boot Loader để chạy JAR có thư viện lồng bên trong

## 1. Bài toán: một file JAR, nhưng bên trong có rất nhiều JAR khác

Khi phát triển ứng dụng Spring Boot, chúng ta thường thêm những dependencies như Spring Framework, Jackson, logging và embedded servlet container. Chạy trong IDE hoặc qua Maven/Gradle có vẻ đơn giản vì công cụ build tự tạo **classpath** chứa thư mục class của ứng dụng và nhiều file JAR riêng biệt đã tải về.

Khi đưa ứng dụng lên server, việc phải sao chép hàng chục hoặc hàng trăm JAR phụ thuộc vào đúng thư mục, đúng phiên bản và viết đúng lệnh **java -cp ...** dễ gây sai sót. Spring Boot giải quyết bằng cách tạo **executable JAR**: một file phân phối chứa ứng dụng, những runtime dependencies và một phần mã khởi động chuyên dụng.

Ví dụ một Spring Boot JAR có thể có cấu trúc:

~~~text
loader-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── ... các class của Spring Boot Loader ...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/loaderdemo/LoaderDemoApplication.class
    │   ├── com/example/loaderdemo/NestedController.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-....jar
    │   ├── spring-context-....jar
    │   ├── jackson-databind-....jar
    │   └── ...
    ├── classpath.idx  (nếu có)
    └── layers.idx     (nếu có)
~~~

Tên các thư viện và versions chỉ mang tính minh họa; phiên bản phụ thuộc thực tế do build resolver chọn. **BOOT-INF/classes/** chứa class và resource của ứng dụng, **BOOT-INF/lib/** chứa **các file JAR nguyên vẹn lồng bên trong JAR ngoài**. Các class ở **org/springframework/boot/loader/** phục vụ việc khởi động.

**Câu hỏi trung tâm:** Nếu file **loader-demo-1.0.0.jar** là một JAR hợp lệ, vì sao không để Java/JVM tự tìm mọi class ở **BOOT-INF/lib/**? Tại sao phải có **Spring Boot Loader** và **JarLauncher**?

Câu trả lời ngắn: **cơ chế classpath/JAR tiêu chuẩn của Java không tự động coi một file JAR nằm bên trong file JAR khác là một classpath entry**. Spring Boot Loader bổ sung khả năng truy cập và nạp những JAR lồng nhau, dựng class loader thích hợp, rồi mới gọi **main()** của ứng dụng.

Điểm chính xác cần ghi nhớ: **JVM không cần Spring Boot Loader trong mọi ứng dụng Java**. Nó chỉ cần một cơ chế tương đương khi muốn thực thi **định dạng archive lồng JAR của Spring Boot** mà không bung từng thư viện thành file riêng. Bạn cũng có thể chạy Java bằng các JAR đặt ngoài trên classpath hoặc dùng một kiểu đóng gói khác.

## 2. JVM bình thường tìm class như thế nào?

### 2.1. Classpath là tập vị trí tìm class/resource

Một ứng dụng Java có main class là **com.example.Main** và thư viện ngoài **my-lib.jar** có thể chạy theo kiểu thông thường:

~~~bash
java -cp "classes:lib/my-lib.jar" com.example.Main
~~~

Trên Windows, dấu phân cách classpath thường là **;**, ví dụ:

~~~powershell
java -cp "classes;lib/my-lib.jar" com.example.Main
~~~

Ở đây:
- **classes/** là thư mục có cấu trúc package **com/example/Main.class**.
- **lib/my-lib.jar** là **một file JAR riêng nằm trên filesystem**.
- JVM và các class loader tiêu chuẩn có thể tìm classes/resources qua những classpath entries đã được cung cấp.
- **-cp** chỉ định các vị trí classpath, **không tạo ra** thư viện mới và không tìm đệ quy mọi JAR lồng bên trong mỗi JAR.

Một JAR cơ bản thường đặt **com/example/Main.class** ngay theo đường dẫn package ở **gốc archive**. Nếu lớp Main được đặt dưới một thư mục lồng riêng như **BOOT-INF/classes/com/example/Main.class**, một class loader thông thường coi file JAR ngoài là classpath entry **không tự xem BOOT-INF/classes là một classpath root riêng**.

### 2.2. Chế độ java -jar dùng manifest

Một JAR thông thường có manifest chỉ định:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
~~~

Khi chạy:

~~~bash
java -jar app.jar
~~~

Java launcher đọc **META-INF/MANIFEST.MF**, xác định **Main-Class**, nạp class đó theo quy tắc thực thi JAR, rồi gọi phương thức **public static void main(String[] args)**.

Khi dùng **-jar**, các thiết lập classpath do người dùng truyền bằng **-cp / -classpath** hoặc **CLASSPATH** không được dùng theo cách chạy tên main class thông thường. Nếu cần thêm JAR ngoài cho ordinary executable JAR, có thể cấu hình **Class-Path** trong manifest với những JAR external phù hợp. Nhưng **Class-Path không biến file JAR lồng ở BOOT-INF/lib thành JAR mà Java tự mở đệ quy**.

Vì vậy **java -jar** giải quyết việc tìm main entry point, **không tự giải quyết** định dạng **JAR chứa JAR**.

### 2.3. Tại sao đặt một file .jar trong file .jar chưa đủ?

Giả sử archive có:

~~~text
plain-app.jar
├── META-INF/MANIFEST.MF
├── com/example/Main.class
└── BOOT-INF/lib/utility.jar
                  └── (bên trong utility.jar có com/example/Utility.class)
~~~

**jar tf plain-app.jar** sẽ nhìn thấy entry **BOOT-INF/lib/utility.jar**, nhưng **Utility.class** không phải entry trực tiếp ở root của **plain-app.jar**. Java launcher thông thường không coi entry **utility.jar** là một module/classpath root độc lập. Nếu **Main** gọi **Utility**, runtime có thể báo **NoClassDefFoundError** hoặc một lỗi liên quan đến class loading.

Đây không phải vấn đề “JVM không hỗ trợ ZIP” — Java đọc được JAR/ZIP ở nhiều tình huống. Vấn đề là **quy tắc classpath chuẩn không tự mở JAR bên trong JAR và nối tất cả file con vào tập nguồn tìm class**.

## 3. Spring Boot executable JAR giữ thư viện dưới dạng nested JAR

Định dạng Spring Boot giữ ranh giới của từng dependency:

| Vị trí trong archive | Chứa gì? | Tác dụng |
| --- | --- | --- |
| **META-INF/MANIFEST.MF** | Metadata khởi động | Trỏ đến Boot launcher và main class thật |
| **org/springframework/boot/loader/** | Boot Loader classes | Entry point và các lớp hỗ trợ nạp nested JAR |
| **BOOT-INF/classes/** | Compiled class + main resources của ứng dụng | Classpath root của application |
| **BOOT-INF/lib/*.jar** | Runtime dependency archives | Spring, Jackson, logging, server... |
| **BOOT-INF/classpath.idx** (tùy cấu hình) | Thứ tự đưa JAR lên classpath | Giúp launcher giữ classpath order như build system |
| **BOOT-INF/layers.idx** (tùy cấu hình) | Chỉ mục layers | Phục vụ tách Docker/OCI image layers, không phải danh sách class bắt buộc |

Đường dẫn **BOOT-INF/lib/jackson-databind-...jar** là **entry file** của JAR ngoài; nội dung bên trong vẫn là một cấu trúc JAR của Jackson. Spring Boot dùng cơ chế truy cập lồng nhau thay vì giải nén toàn bộ dependencies xuống một thư mục tạm trước mỗi lần chạy.

Điều này mang lại:
- Một executable archive dễ sao chép và triển khai.
- Có thể phân biệt từng dependency theo tên JAR/version thay vì trộn toàn bộ classes.
- Giữ phần lớn metadata/resources của từng JAR theo archive gốc.
- Có thể dùng cùng cách packaging trên nhiều môi trường hỗ trợ JVM.

Cần phân biệt **Spring Boot executable JAR** với **thin/plain JAR**: một plain JAR thường chỉ chứa class/resource của project và dựa vào external classpath để lấy dependencies. Cả hai đều là file JAR, nhưng **bố trí class và cách chạy** khác nhau.

## 4. Boot Loader là gì và không phải là gì?

**Spring Boot Loader** là mã Java hỗ trợ khởi động archive Spring Boot. Nó không phải:
- Một JVM mới thay thế HotSpot/OpenJ9.
- Spring **ApplicationContext** hay container quản lý bean.
- Công cụ quản lý dependency versions như Maven/Gradle.
- Một cơ chế tự tải thư viện còn thiếu từ internet khi runtime.
- Một lý do để bỏ qua việc chọn JDK tương thích.

Trong Spring Boot 3.5, những lớp launcher được mô tả trong package **org.springframework.boot.loader.launch**:

- **JarLauncher**: dùng cấu trúc executable JAR với **BOOT-INF/classes** và **BOOT-INF/lib**.
- **WarLauncher**: dùng cấu trúc executable WAR, ví dụ **WEB-INF/classes**, **WEB-INF/lib** và **WEB-INF/lib-provided**.
- **PropertiesLauncher**: có thể thêm đường dẫn thư viện qua cấu hình loader như **loader.path / LOADER_PATH**, phù hợp một số mô hình cần mở rộng classpath có kiểm soát.

**Tên package có thể thay đổi theo phiên bản Spring Boot.** Một số bài viết Boot cũ sử dụng **org.springframework.boot.loader.JarLauncher**. Từ Boot 3.2, tên thường thấy là **org.springframework.boot.loader.launch.JarLauncher**; khi debug phải đọc **manifest của artifact đang có**, không sao chép tên launcher từ ví dụ nhiều năm trước.

### 4.1. Launcher chạy trước ứng dụng

Trong Spring Boot executable JAR, **Main-Class** không nhất thiết là **com.example.MyApplication**. Nó thường là **JarLauncher**:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.loaderdemo.LoaderDemoApplication
~~~

**Main-Class** được Java launcher gọi trước; **Start-Class** được Boot Loader dùng để tìm main class thực sự. Đây là giải pháp bắc cầu: Java hiểu manifest và chạy một class accessible ngay tại root archive; Boot Loader sau đó hiểu phần cấu trúc nested JAR riêng của Boot.

Đừng nhầm hai thuộc tính: nếu **Main-Class** trỏ thẳng vào ứng dụng nhưng class đó nằm ở **BOOT-INF/classes**, Java launcher tiêu chuẩn có thể không tìm được nó. **Start-Class** không phải một thuộc tính mặc định mà Java launcher tự diễn giải giống **Main-Class**; nó là convention của Spring Boot Loader.

### 4.2. Ai chịu trách nhiệm việc gì?

| Thành phần | Việc chính |
| --- | --- |
| **java launcher / JVM** | Đọc manifest trong chế độ -jar, khởi động Java runtime, tải class entry point theo quy tắc tiêu chuẩn |
| **Boot JarLauncher** | Hiểu cấu trúc Boot archive; hình thành các classpath entries cần thiết từ application classes và nested libs |
| **Boot nested-JAR support / ClassLoader** | Đọc class và resource từ những JAR nằm bên trong outer archive |
| **Application main()** | Gọi SpringApplication.run hoặc logic Java của ứng dụng |
| **SpringApplication / ApplicationContext** | Tạo context, đăng ký bean, auto-configuration, khởi động web server nếu có |
| **Embedded Tomcat/Jetty/Netty** | Xử lý request theo cấu hình runtime nếu dependency phù hợp |

Boot Loader **giải vấn đề đóng gói và nạp classes**. Spring Framework và Spring Boot application infrastructure **giải vấn đề thực thi ứng dụng và cấu hình nghiệp vụ**. Đây là hai tầng tách biệt.

## 5. Trình tự khi gõ java -jar application.jar

~~~text
$ java -jar loader-demo-1.0.0.jar
                  |
                  v
  Java đọc META-INF/MANIFEST.MF
                  |
                  v
  Tìm Main-Class = ...launch.JarLauncher
                  |
                  v
  Nạp và gọi launcher main()
                  |
                  v
  Boot Loader truy cập BOOT-INF/classes và BOOT-INF/lib/*.jar
                  |
                  v
  Tạo class loader hỗ trợ nested JAR, dựng classpath
                  |
                  v
  Tìm Start-Class = com.example.loaderdemo.LoaderDemoApplication
                  |
                  v
  Gọi LoaderDemoApplication.main(args)
                  |
                  v
  SpringApplication.run(...); Spring context + server
~~~

Lưu ý:
1. **Không có bước mặc định “mở và giải nén tất cả các JAR ra ổ đĩa”**. Hỗ trợ nested JAR của Boot có thể nạp nội dung trực tiếp từ outer archive.
2. Truyền **--server.port=9090** sau tên JAR là đối số cho ứng dụng Spring Boot; nó **không thay thế** Main-Class hay Boot Loader.
3. Classpath khi khởi chạy Boot archive khác cách IDE hoặc **spring-boot:run / bootRun** tạo classpath. IDE thường dùng **build/classes** và những dependency JAR đã giải ra thành file riêng trong Gradle/Maven cache.
4. Spring Boot Loader là phần khởi động, không tự đảm bảo ứng dụng sẽ thành công: thiếu JDK, lỗi main class, missing dependency, lỗi bean hoặc cấu hình database vẫn có thể khiến runtime dừng.

## 6. Boot đọc nested JAR trực tiếp như thế nào?

### 6.1. Vấn đề kỹ thuật với ZIP/JAR hai tầng

JAR dựa trên ZIP. JAR ngoài có danh sách entries, trong đó có một entry **BOOT-INF/lib/dependency.jar**. Bản thân entry đó lại là **một ZIP/JAR độc lập** có danh sách classes/resources. Các Java APIs chuẩn không cung cấp cơ chế classpath mặc định để đi xuyên qua cả hai lớp này trong lúc **java -jar** chạy.

Spring Boot cung cấp lớp hỗ trợ nested archive, điển hình là **NestedJarFile**. Theo đặc tả Boot, khi đọc archive, loader có thể ánh xạ các entries của JAR lồng tới **offset vật lý** trong file JAR ngoài. Khi cần một class/resource cụ thể, nó seek đến vị trí tương ứng mà **không bắt buộc giải nén toàn bộ archive ra ổ đĩa** hoặc tải toàn bộ JAR vào RAM.

Sơ đồ minh họa:

~~~text
outer.jar
+------------------------------------------------+
| BOOT-INF/classes/... | BOOT-INF/lib/tool.jar   |
|   Main.class         | +---------------------+ |
|                      | | LibA.class          | |
|                      | | LibB.class          | |
|                      | +---------------------+ |
+------------------------------------------------+
          ^                         ^
  entry trong outer           entries của nested JAR
                                   |
                             offset mapping
                                   |
                             class loader đọc bytes
~~~

**NestedJarFile** không phải API thay thế toàn bộ hành vi class loader của JVM. Nó là một thành phần giúp truy cập entries; class loader của Spring Boot sử dụng các URLs/nguồn tài nguyên thích hợp để nạp class/resource theo Java class-loading contract.

### 6.2. Vì sao nested JAR entry phải là STORED?

Đặc tả executable JAR của Spring Boot quy định **entry chứa một nested JAR trong ZIP ngoài phải dùng phương thức ZipEntry.STORED** (không nén chính entry đó). Mục đích là cho phép seek trực tiếp đến byte-offset bên trong nested JAR để đọc các entries.

Điểm dễ hiểu sai: **STORED chỉ áp dụng cho entry JAR nằm trong outer JAR**; **bản thân các entries bên trong nested JAR vẫn có thể được nén**. Các entries khác của outer JAR cũng có thể có compression phù hợp. Không cần tắt nén toàn bộ Spring Boot archive.

Maven **spring-boot:repackage** và Gradle **bootJar** tạo định dạng phù hợp. Nếu tự chỉnh sửa JAR bằng công cụ zip thông thường rồi nén lại nested jar entries không đúng chuẩn, Boot Loader có thể lỗi khi mở thư viện; đừng tự thay ZIP compression method hoặc tái cấu trúc **BOOT-INF/lib** nếu không hiểu các ràng buộc packaging.

### 6.3. Nested URLs và truy cập resource

Spring Boot Loader hỗ trợ URLs dành cho nested content. Trong các phiên bản Boot mới, tài liệu minh họa dạng:

~~~text
jar:nested:/path/myapp.jar/!BOOT-INF/lib/mylib.jar!/com/example/Library.class
~~~

URL này minh họa một class **Library.class** nằm trong **mylib.jar**, và **mylib.jar** lại nằm trong outer **myapp.jar**. Boot cung cấp cách mở kết nối tương thích với các Java APIs như **JarURLConnection**/URL-based class loading.

**Không dùng phép tách URL bằng tay để suy ra một đường dẫn file thật**: nested URL không đồng nghĩa **/path/myapp.jar/BOOT-INF/lib/mylib.jar** là thư mục có thể mở bằng File API. Thay vào đó, dùng class loader/resource APIs, hoặc dùng packaging API riêng nếu thực sự cần thao tác với archive.

## 7. Tại sao Thread Context ClassLoader quan trọng?

Trong Java, có nhiều class loader với vai trò khác nhau: bootstrap/platform, application/system, và các class loader được framework tạo thêm. Spring Boot Loader thiết lập môi trường để main application có thể tìm classes/resources từ **BOOT-INF/classes** và nested libs.

Các thư viện sử dụng **Thread.currentThread().getContextClassLoader()** thường hoạt động phù hợp trong mô hình này. Nhiều cơ chế SPI và resource lookup dựa trên **Thread Context ClassLoader (TCCL)**. Nhưng một thư viện cố nạp dependency lồng bên trong bằng:

~~~java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
Class<?> type = systemLoader.loadClass(
        "com.fasterxml.jackson.databind.ObjectMapper");
~~~

có thể không tìm thấy class trong **BOOT-INF/lib** khi chạy bằng **java -jar** trên archive Boot. Lý do: **system class loader không tự có cùng tầm nhìn với class loader mà Boot Launcher dùng để nạp nested JARs**. Đừng coi đoạn code trên là phương án đúng để nạp dependencies của Spring Boot.

Một cách hợp lý hơn khi dùng SPI/resource APIs là dùng TCCL:

~~~java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

Class<?> type = loader.loadClass(
        "com.fasterxml.jackson.databind.ObjectMapper");

System.out.println(type.getName());
~~~

Đây là **đoạn method-body minh họa**, không phải class Java độc lập để biên dịch. Nếu đặt vào method có khai báo hoặc xử lý **ClassNotFoundException**, với Jackson tồn tại trong runtime classpath của ví dụ bên dưới, dòng stdout dự kiến là:

~~~text
com.fasterxml.jackson.databind.ObjectMapper
~~~

Tuy nhiên, không phải mọi thư viện đều phải viết code thủ công như thế. Với Spring, thường nên để dependency injection, ServiceLoader đúng class loader hoặc API của framework thực hiện việc nạp. Mục tiêu của đoạn trên là hiểu phạm vi nhìn thấy classes.

**Đặc tả Spring Boot lưu ý** các thư viện cố sử dụng **ClassLoader.getSystemClassLoader()** để tải class nằm trong nested JAR có thể gặp lỗi. Trong trường hợp library yêu cầu JAR phải tồn tại như file riêng trên filesystem, xem phần **requiresUnpack** hoặc cách đóng gói khác.

## 8. Ví dụ chạy được: Spring Boot dùng Jackson từ BOOT-INF/lib

Ta sẽ dùng một endpoint cần **com.fasterxml.jackson.databind.ObjectMapper**. Class **ObjectMapper** đến từ dependency Jackson trong starter-web và được đóng gói dưới một JAR ở **BOOT-INF/lib**. Từ đó ta có thể kiểm tra thực tế Boot Loader nạp được dependency lồng mà không cần chạy với một danh sách thủ công **-cp**.

Phiên bản ví dụ: **Java 17, Spring Boot 3.5.16**. Đây là một tổ hợp nhằm minh họa định dạng executable JAR của Boot 3.5; với dự án mới hãy dùng nhánh đang được hỗ trợ theo chính sách tổ chức. Dùng **Maven hoặc Gradle**, không phải cả hai cùng lúc. Các tệp Java được dùng chung cho hai phương án.

### 8.1. Cấu trúc thư mục

~~~text
loader-demo/
├── pom.xml                    (nếu dùng Maven)
│   hoặc
├── build.gradle               (nếu dùng Gradle)
├── settings.gradle            (nếu dùng Gradle)
├── mvnw / mvnw.cmd / .mvn/wrapper/...         (Maven Wrapper)
├── gradlew / gradlew.bat / gradle/wrapper/... (Gradle Wrapper)
└── src/
    ├── main/java/com/example/loaderdemo/
    │   ├── LoaderDemoApplication.java
    │   └── NestedController.java
    ├── main/resources/application.properties
    └── test/java/com/example/loaderdemo/
        └── NestedControllerTests.java
~~~

Wrapper scripts và metadata phải được tạo bằng Spring Initializr hoặc công cụ Wrapper tương ứng. Chỉ tạo **pom.xml** hoặc **build.gradle** sẽ không tự sinh **./mvnw** hoặc **./gradlew**.

### 8.2. Main class

Tệp **src/main/java/com/example/loaderdemo/LoaderDemoApplication.java**:

~~~java
package com.example.loaderdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoaderDemoApplication.class, args);
    }
}
~~~

Class này không tự nạp nested JARs. Việc đó xảy ra trước khi **main()** của class này được gọi khi chạy executable archive bằng **java -jar**.

### 8.3. Controller dùng Jackson

Tệp **src/main/java/com/example/loaderdemo/NestedController.java**:

~~~java
package com.example.loaderdemo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class NestedController {

    private final ObjectMapper objectMapper;

    public NestedController(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @GetMapping("/nested")
    public String nested() {
        return objectMapper.createObjectNode()
                .put("message", "nested-ok")
                .path("message")
                .asText();
    }
}
~~~

**ObjectMapper** được Spring Boot tự cấu hình thành bean khi có Jackson trên classpath. Code không tự tạo JSON string rồi trả nó về để giả lập; nó thực sự gọi một phương thức của **Jackson ObjectMapper** và lấy thuộc tính từ Jackson tree model.

Spring Boot starter-web (nhánh 3.5 trong ví dụ) đưa Jackson vào dependency graph. Khi đóng gói executable JAR, Jackson classes nằm trong **một hoặc nhiều nested dependency JAR** dưới **BOOT-INF/lib**, chứ không được copy thành class phẳng ngay tại root của outer JAR.

### 8.4. application.properties

Tệp **src/main/resources/application.properties**:

~~~properties
spring.application.name=loader-demo
server.port=8080
~~~

Giá trị 8080 được đặt tường minh để dễ kiểm tra endpoint. Nếu cổng 8080 đang được tiến trình khác dùng, có thể chạy **java -jar ... --server.port=9090** và đổi URL gọi thử tương ứng.

### 8.5. Test HTTP endpoint

Tệp **src/test/java/com/example/loaderdemo/NestedControllerTests.java**:

~~~java
package com.example.loaderdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class NestedControllerTests {

    @Autowired
    private MockMvc mvc;

    @Test
    void canUseNestedJacksonDependency() throws Exception {
        mvc.perform(get("/nested"))
                .andExpect(status().isOk())
                .andExpect(content().string("nested-ok"));
    }
}
~~~

Test xác minh endpoint sử dụng ObjectMapper thông qua Spring context. Nó chưa phải bằng chứng trực tiếp rằng executable JAR đã nạp nested libs, vì test thường chạy trên classpath do build tool tạo. **Cần chạy chính JAR** sau khi đóng gói để xác minh thêm tầng Boot Loader.

## 9. Đóng gói bằng Maven với Spring Boot Loader

Tạo **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>loader-demo</artifactId>
    <version>1.0.0</version>

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

Maven **spring-boot-starter-parent** cung cấp dependency management và execution **repackage** được cấu hình sẵn khi Spring Boot Maven Plugin được khai báo. Goal **spring-boot:repackage** làm công việc **chuyển plain JAR thành executable Boot JAR**, bổ sung layout và loader cần thiết. Nếu không dùng parent, phải cấu hình execution/version của plugin thích hợp.

Chạy trong root:

~~~bash
./mvnw --version
./mvnw clean verify
java -jar target/loader-demo-1.0.0.jar
~~~

Trên Windows dùng **mvnw.cmd**. **clean verify** bao gồm phase package theo Maven default lifecycle và chạy các kiểm thử được cấu hình; package/repackage tạo archive ở **target/**. Nếu test/build thất bại, không được giả định JAR đã sinh thành công.

Từ terminal khác:

~~~bash
curl http://localhost:8080/nested
~~~

Response body dự kiến, không có dấu ngoặc kép:

~~~text
nested-ok
~~~

Ý nghĩa: khi thực sự chạy bằng **java -jar target/loader-demo-1.0.0.jar**, Java trước hết gọi launcher theo manifest; launcher nạp được các classes của application và Jackson JAR lồng bên trong; Spring context khởi động, endpoint dùng ObjectMapper và trả về kết quả.

## 10. Đóng gói cùng ứng dụng bằng Gradle

Nếu chọn Gradle, **không dùng pom.xml** ở phần trên. Tạo **settings.gradle**:

~~~groovy
rootProject.name = 'loader-demo'
~~~

Tạo **build.gradle** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot Gradle Plugin tạo task **bootJar**, dùng classpath/dependencies của ứng dụng để tạo executable archive có layout Boot và launcher. Spring Dependency Management Plugin nhận bộ managed dependency versions theo Spring Boot plugin. Các thư viện dành riêng cho test thường không được đóng gói vào production executable JAR.

Với Gradle Wrapper phù hợp, chẳng hạn Gradle **8.14** trong dải hỗ trợ của Boot 3.5, chạy:

~~~bash
./gradlew --version
./gradlew clean test bootJar
java -jar build/libs/loader-demo-1.0.0.jar
~~~

Windows dùng **gradlew.bat**. Khi startup thành công, gọi:

~~~bash
curl http://localhost:8080/nested
~~~

Response body dự kiến cũng là:

~~~text
nested-ok
~~~

**build/libs/loader-demo-1.0.0.jar** là tên mặc định theo tên project và version, có thể khác nếu project custom archive naming. Không nên tìm JAR ở **target/** trong dự án Gradle hoặc ở **build/libs/** trong dự án Maven trừ khi build script thật đã đổi đường dẫn.

## 11. Tự kiểm tra: manifest và thư viện thật nằm ở đâu?

Một file JAR có đuôi **.jar** chưa đảm bảo được repackaged đúng. Cần kiểm tra các dấu hiệu.

### 11.1. Liệt kê những entries trong artifact

Với Maven:

~~~bash
jar tf target/loader-demo-1.0.0.jar
~~~

Với Gradle:

~~~bash
jar tf build/libs/loader-demo-1.0.0.jar
~~~

Trong danh sách dài, tìm các entry dạng:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/loaderdemo/LoaderDemoApplication.class
BOOT-INF/classes/com/example/loaderdemo/NestedController.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/spring-boot-....jar
BOOT-INF/lib/jackson-databind-....jar
BOOT-INF/lib/...
~~~

Đây là **những đường dẫn cần tìm**, không phải toàn bộ output hoặc một lời hứa về số/version JAR. **jar tf** liệt kê file entries của outer archive: nó không tự mở từng nested JAR rồi in mọi Jackson class bên trong. Muốn xem Jackson class thực sự bên trong nested dependency, cần đọc nested archive bằng công cụ phù hợp hoặc giải nén một **bản sao** phục vụ kiểm tra.

Ví dụ trên Linux/macOS có thể lọc output:

~~~bash
jar tf target/loader-demo-1.0.0.jar | grep 'BOOT-INF/lib/jackson-databind'
jar tf target/loader-demo-1.0.0.jar | grep 'loader/launch/JarLauncher.class'
~~~

Lệnh trên giả định người dùng chọn Maven. Với Gradle thay đường dẫn JAR sang **build/libs/**. Một dependency graph có thể thay Jackson implementation theo phiên bản Boot; luôn kiểm tra thư viện thực tế được resolve thay vì mặc định tên mọi thư viện là cố định.

Trên PowerShell:

~~~powershell
jar tf .\target\loader-demo-1.0.0.jar |
    Select-String 'BOOT-INF/lib/jackson-databind'
~~~

### 11.2. Xem Main-Class và Start-Class trong MANIFEST.MF

Dùng công cụ ZIP viewer hoặc trích đúng entry từ archive trong một **thư mục tạm** để tránh ghi đè file trong repository.

Linux/macOS với Maven JAR:

~~~bash
mkdir -p jar-inspect
cd jar-inspect
jar xf ../target/loader-demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
cd ..
~~~

Gradle JAR tương ứng ở **../build/libs/loader-demo-1.0.0.jar**. Trong manifest Boot 3.5 mong đợi có các trường tương tự:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.loaderdemo.LoaderDemoApplication
Spring-Boot-Version: 3.5.16
~~~

Manifest còn có thể có fields khác (implementation-title/version, Build-Jdk-Spec, layers indexes...) và các giá trị do plugin cấu hình. **Không so khớp nguyên văn toàn bộ manifest**; kiểm tra cặp **Main-Class** (launcher) và **Start-Class** (ứng dụng) là trọng tâm.

**Không nhầm lệnh jar xf với chạy ứng dụng:** jar xf trích file ZIP, không khởi động main. Nó ghi file vào thư mục hiện tại nên chỉ làm trong vị trí được phép. Nếu archive có dữ liệu nhạy cảm, không chia sẻ hoặc upload nội dung trích xuất không cần thiết.

### 11.3. Vì sao không cần Class-Path trong manifest?

Với Boot executable JAR, **JarLauncher** xác định những nested JARs theo layout của Boot, nên manifest không cần liệt kê **Class-Path: lib/a.jar lib/b.jar**. Kiểu manifest Class-Path dùng cho JARs bên ngoài ở vị trí liên quan; nó **không phải cách tiêu chuẩn để trỏ vào BOOT-INF/lib/*.jar như ZIP entries nội bộ**.

Một lỗi debug phổ biến là thấy thiếu **Class-Path** rồi kết luận executable JAR không có dependencies. Với Boot archive, hãy kiểm tra **BOOT-INF/lib**, Boot Loader classes và **Main-Class/Start-Class**.

## 12. Thí nghiệm Java thuần: nested JAR không tự thành classpath

Đây là một thí nghiệm độc lập với Spring Boot, phù hợp Java 17+; nó minh họa vấn đề **JAR-in-JAR** một cách trực tiếp trước khi áp dụng Boot Loader.

Giả sử chuẩn bị:
- Tệp **lib-src/demo/lib/Formatter.java**;
- Tệp **app-src/demo/app/Main.java**.

### 12.1. Library class

~~~java
package demo.lib;

public class Formatter {
    public static String text() {
        return "library-loaded";
    }
}
~~~

### 12.2. Main class gọi thư viện

~~~java
package demo.app;

import demo.lib.Formatter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Formatter.text());
    }
}
~~~

### 12.3. Biên dịch, tạo hai JAR và chạy classpath bình thường

Trong một workspace thí nghiệm riêng trên Linux/macOS:

~~~bash
mkdir -p lib-classes app-classes BOOT-INF/lib

javac -d lib-classes lib-src/demo/lib/Formatter.java
jar --create --file BOOT-INF/lib/demo-lib.jar -C lib-classes .

javac -cp BOOT-INF/lib/demo-lib.jar -d app-classes app-src/demo/app/Main.java
jar --create --file plain-app.jar --main-class demo.app.Main -C app-classes .

java -cp "plain-app.jar:BOOT-INF/lib/demo-lib.jar" demo.app.Main
~~~

Stdout đúng của dòng cuối:

~~~text
library-loaded
~~~

Thư viện **demo-lib.jar** hiện là một file độc lập trên filesystem và đã được liệt kê trực tiếp trong classpath — do đó Java tìm thấy class **Formatter**.

### 12.4. Nhét thư viện vào bên trong app JAR, rồi dùng java -jar

~~~bash
jar --update --file plain-app.jar -C . BOOT-INF/lib/demo-lib.jar

jar tf plain-app.jar
java -jar plain-app.jar
~~~

Lệnh cập nhật chỉ nhét **demo-lib.jar** làm entry **BOOT-INF/lib/demo-lib.jar** của outer JAR; nó **không thêm Spring Boot Loader**, không thay đổi manifest để khởi động thông qua JarLauncher và không khiến Java launcher tự liệt kê nested libs.

**Kết quả mong đợi của java -jar:** chương trình không in **library-loaded** thành công, mà báo lỗi class loading (thường có **NoClassDefFoundError: demo/lib/Formatter**). Nội dung và vị trí các dòng stack trace tùy JDK, vì vậy không xem thông điệp đầy đủ là stdout cố định.

Lý do: manifest vẫn trỏ thẳng **demo.app.Main**, nhưng **demo.lib.Formatter** chỉ có mặt trong JAR lồng, không nằm trên classpath mà java -jar tự nhìn thấy. Việc đặt folder mang tên **BOOT-INF/lib** **chưa đủ**; muốn chạy theo layout Boot cần loader, manifest và constraints của Boot archive.

**Windows:** ví dụ lệnh classpath bình thường ở bước đầu phải đổi dấu phân cách **:** thành **;**:

~~~powershell
java -cp "plain-app.jar;BOOT-INF/lib/demo-lib.jar" demo.app.Main
~~~

Trên Windows có thể tạo thư mục bằng PowerShell/Explorer; các lệnh **javac** và **jar** có tùy chọn tương tự. Không dùng thí nghiệm này để sửa archive production; làm trong workspace riêng.

## 13. Lỗi thường gặp: java -cp boot.jar com.example.Main

Một Spring Boot executable JAR đặt compiled application classes dưới:

~~~text
BOOT-INF/classes/com/example/loaderdemo/LoaderDemoApplication.class
~~~

Khi gọi:

~~~bash
java -cp loader-demo-1.0.0.jar com.example.loaderdemo.LoaderDemoApplication
~~~

Java launcher dùng JAR ngoài làm classpath root và thường không tìm **com/example/loaderdemo/LoaderDemoApplication.class** ở root archive, vì nó nằm sâu dưới **BOOT-INF/classes**. Kết quả thường là **Could not find or load main class** hoặc **ClassNotFoundException**.

Ngay cả khi cố dùng **-cp** trỏ trực tiếp tới **BOOT-INF/lib** bên trong tên file JAR, một đường dẫn như **loader-demo.jar/BOOT-INF/lib/...** không phải file JAR riêng trên filesystem. Classpath CLI chuẩn không xử lý nested layout của Boot.

**Lệnh đúng cho executable Boot JAR**:

~~~bash
java -jar loader-demo-1.0.0.jar
~~~

Nếu đang ở thư mục root Maven/Gradle, dùng đúng đường dẫn **target/...** hoặc **build/libs/...** như đã tạo. Khi muốn tự điều khiển Java classpath thay vì dùng Boot Loader, cần một **layout đã giải nén đúng cách** hoặc đóng gói khác, và phải cung cấp mọi classpath entry thực tế.

**Không tự thêm -cp sau java -jar rồi mong nó sửa được classpath.** Trong chế độ **-jar**, classpath options bên ngoài không hoạt động giống mode **-cp mainClass**; các đối số sau tên JAR có thể được chuyển tới main method.

## 14. Vì sao chạy trong IDE và bootRun vẫn chạy dù không có executable JAR?

Khi chạy Spring Boot trực tiếp trong IDE, Eclipse/IntelliJ hay:

~~~bash
./mvnw spring-boot:run
~~~

hoặc:

~~~bash
./gradlew bootRun
~~~

build tool thường tạo classpath thông thường gồm:
- thư mục classes/resources đã biên dịch của application;
- các dependency JAR được lưu riêng trong Maven/Gradle cache;
- một main application class thích hợp.

Trong tình huống này, **không cần nạp JAR lồng trong archive** vì dependencies chưa được gói bên trong **BOOT-INF/lib**. Hình dung:

~~~text
Chạy từ IDE / bootRun:
  build/classes/java/main/ + build/resources/main/
      + ~/.gradle/caches/.../jackson-....jar
      + ~/.gradle/caches/.../spring-....jar
      -> Application.main

Chạy executable JAR:
  loader-demo.jar
      + BOOT-INF/classes/
      + BOOT-INF/lib/jackson-....jar
      + BOOT-INF/lib/spring-....jar
      -> Boot JarLauncher -> Application.main
~~~

Lưu ý đường dẫn cache có thể khác nhau giữa máy và build tool. Hai đường khởi động có thể cùng dẫn tới SpringApplication.run nhưng **classpath layout** và resource URLs không hoàn toàn giống nhau.

Đây là lý do có những lỗi chỉ xuất hiện sau khi đóng gói: một thư viện dùng **File** thay vì stream/resource API, hoặc hardcode đường dẫn classpath kiểu IDE. Nên chạy smoke test **java -jar artifact thực tế** trước khi phát hành.

## 15. JarLauncher, WarLauncher, PropertiesLauncher: chọn khi nào?

### 15.1. JarLauncher

Định dạng phổ biến với **bootJar** của Gradle hoặc **spring-boot:repackage** của Maven:

~~~text
BOOT-INF/classes/
BOOT-INF/lib/
~~~

Launcher đọc classpath của archive theo layout này và dùng **Start-Class** trong manifest. Đối với ứng dụng HTTP service thông thường, đây là lựa chọn mặc định phù hợp.

### 15.2. WarLauncher

Định dạng executable WAR phổ biến:

~~~text
WEB-INF/classes/
WEB-INF/lib/
WEB-INF/lib-provided/
~~~

**WEB-INF/lib-provided/** chứa những dependencies cần khi chạy WAR theo kiểu executable/embedded nhưng không nên đưa vào đường nhìn của servlet container truyền thống như thư viện ứng dụng bình thường. Định dạng này giúp hỗ trợ những mô hình WAR có yêu cầu đặc biệt. Không tự đổi JAR thành WAR bằng cách sửa đuôi file: build plugin, packaging và application initialization phải phù hợp.

### 15.3. PropertiesLauncher

**PropertiesLauncher** cho phép kiểm soát một phần các classpath locations thêm ngoài layout chuẩn; có thể nhận các giá trị như **loader.path**, **LOADER_PATH** hoặc **loader.properties**. Ví dụ cấu hình về mặt khái niệm:

~~~properties
loader.path=external-lib/
~~~

Đây là **đoạn cấu hình loader**, không phải đặt một dòng vào **application.properties** rồi mặc định Spring Boot sẽ tự đổi launcher. Chỉ hiệu lực khi archive đã được cấu hình **Main-Class** phù hợp với PropertiesLauncher và loader nhận config ở nguồn thích hợp. Mô hình này giúp đưa một số JAR/config từ bên ngoài, nhưng cũng làm deployment phụ thuộc vào những file ngoài cần quản lý riêng.

Đa số ứng dụng Spring Boot mới **không cần PropertiesLauncher**; dùng JarLauncher mặc định đơn giản, nhất quán hơn. Chỉ dùng launcher đặc biệt khi hiểu lý do cần mở rộng classpath.

## 16. BOOT-INF/classpath.idx và layers.idx không làm thay nhiệm vụ của Loader

### 16.1. Classpath index

**BOOT-INF/classpath.idx** có thể được Maven/Gradle plugin tạo để ghi **thứ tự các nested JAR** được thêm vào classpath. Ví dụ cú pháp:

~~~text
- "BOOT-INF/lib/first.jar"
- "BOOT-INF/lib/second.jar"
~~~

Đây chỉ là **cú pháp minh họa**, không phải tên JAR thật. Đặc tả Spring Boot cho biết **classpath.idx** được Boot sử dụng khi archive chạy bằng **java -jar**, còn khi chạy IDE, **spring-boot:run** hoặc **bootRun**, nó không được dùng theo cách này.

Classpath order quan trọng nếu có cùng resource/class tên ở nhiều nguồn; nhưng index **không biến JAR thường thành executable Boot JAR**. Vẫn cần launcher và nested-JAR support. Không nên tự sửa thứ tự classpath.idx để che lỗi dependency conflict; xem lại dependency graph trước.

### 16.2. Layers index

**BOOT-INF/layers.idx** mô tả cách chia artifact thành các lớp khi xây Docker/OCI images, ví dụ tách dependencies ổn định khỏi application code hay snapshot dependencies. Nó **không phải danh sách class mà JVM bắt buộc đọc** và **không tự tạo class loader**.

Một ứng dụng có thể khởi động với JarLauncher dù không có layers.idx. Ngược lại, tạo layers.idx thủ công trong JAR không có Boot Loader **không** làm nested JARs được Java launcher hỗ trợ.

## 17. Khi nào cần unpack một nested JAR?

Hầu hết thư viện Java có thể được Boot Loader truy cập trực tiếp khi nằm dưới **BOOT-INF/lib**. Tuy nhiên, một số thư viện **tự yêu cầu một đường dẫn file JAR thật trên filesystem**, hoặc tự có cơ chế ZIP/nested loading không tương thích.

Spring Boot Maven/Gradle packaging hỗ trợ đánh dấu **requiresUnpack** với một số dependency cụ thể, để chúng được trích ra thư mục tạm khi executable archive chạy. Trong tài liệu Boot, **JRuby** là một ví dụ về thư viện có yêu cầu đặc biệt.

**Ví dụ XML minh họa cho Maven plugin** (đặt vào **configuration** của spring-boot-maven-plugin trong POM thật):

~~~xml
<configuration>
    <requiresUnpack>
        <dependency>
            <groupId>org.jruby</groupId>
            <artifactId>jruby-complete</artifactId>
        </dependency>
    </requiresUnpack>
</configuration>
~~~

Đây không phải yêu cầu cho ví dụ Jackson ở phần 8. Không thêm dependency JRuby vào project chỉ để “bật unpack”. Chỉ cấu hình khi dùng đúng thư viện và đã xác minh vấn đề.

Ràng buộc quan trọng:
- Phải có quyền tạo/đọc file ở **java.io.tmpdir** phù hợp.
- Không xóa các file được unpack khi ứng dụng còn đang dùng.
- Không mặc định thư mục tạm luôn có dung lượng và quyền phù hợp trên container/server hạn chế.
- Không giải nén mọi dependency chỉ để sửa một lỗi chưa được chẩn đoán.

## 18. So sánh Spring Boot nested JAR với shaded/uber JAR và thư viện bên ngoài

| Cách đóng gói | Dependency nằm ở đâu? | Cách JVM tìm class | Ưu/nhược điểm |
| --- | --- | --- | --- |
| **Plain/thin JAR + external lib** | Nhiều JAR riêng trên filesystem | java -cp, hoặc manifest Class-Path hợp lệ | Dễ hiểu theo Java tiêu chuẩn, nhưng cần quản lý nhiều file |
| **Shaded/uber JAR** | Class/resources từ libraries được gộp “phẳng” vào một archive | Classloader tiêu chuẩn đọc entries ở root | Một file, nhưng có nguy cơ xung đột resource/metadata và khó nhận diện thư viện gốc |
| **Spring Boot executable nested JAR** | App classes ở BOOT-INF/classes; dependencies nguyên JAR ở BOOT-INF/lib | Boot Loader + class loader nested JAR | Một file, giữ library boundaries; cần launcher/layout đúng |
| **Exploded Spring Boot application** | Archive được giải nén thành dirs/JAR files | Có thể chạy launcher hoặc classpath riêng được dựng đúng | Hữu ích cho container layers; cần bố trí file và lệnh chính xác |

Vì vậy **Boot Loader không phải cách duy nhất để chạy app chứa dependencies**. Nó là lời giải Spring Boot chọn cho **định dạng phân phối JAR lồng JAR**. Maven Shade Plugin hoặc Gradle Shadow plugin có thể tạo shaded JAR theo một kiến trúc khác; không tự thay việc dùng bootJar/repackage bằng shaded JAR nếu chưa đánh giá resource merging, metadata services, duplicates và launcher behavior.

Một plain JAR hợp lệ **không nhất thiết có thể chạy với java -jar**; nó phải có Main-Class thích hợp và tìm được dependencies. Một executable JAR Spring Boot hợp lệ cần thêm classpath/layout đúng cho loader.

## 19. Một số giới hạn kỹ thuật phải biết

### 19.1. Native library/JNI

Một Java dependency có thể chứa file native **.so**, **.dll**, **.dylib** hoặc JNI code. JVM thường cần native library được nạp theo **đường dẫn file tương ứng**; không nên giả định Java code trong nested JAR hỗ trợ trực tiếp mọi kiểu native loading giống một JAR đã bung. Khi gặp **UnsatisfiedLinkError**, kiểm tra CPU architecture, hệ điều hành, quyền tải native library và quy trình extract được library/framework hỗ trợ.

### 19.2. ClassLoader.getSystemClassLoader() không thấy mọi nested dependency

Khi một thư viện tự tìm class qua system class loader, nó có thể gặp lỗi dù class tồn tại trong **BOOT-INF/lib**. Hãy kiểm tra khả năng dùng **TCCL**, Spring Resource API hoặc SPI/loader APIs phù hợp. Đừng sửa bằng cách nhét class vào root JAR một cách ngẫu nhiên.

### 19.3. Mỗi JAR entry có yêu cầu nén riêng

Với Boot, **nested JAR ZipEntry phải STORED** để offset-seeking được hỗ trợ như đặc tả. Việc dùng zip tool để thay đổi compression hoặc archive metadata có thể làm loader không đọc được nội dung. Tốt nhất tạo artifact bằng chính Maven/Gradle Spring Boot plugin.

### 19.4. Khác biệt classpath có thể lộ xung đột

Một build có nhiều phiên bản của cùng thư viện, duplicate classes hoặc service descriptors có thể hoạt động khác khi thứ tự classpath thay đổi. **classpath.idx** có thể giúp giữ thứ tự gần với build system, nhưng không phải công cụ sửa dependency graph. Giải xung đột bằng **mvn dependency:tree** hoặc **gradlew dependencies/dependencyInsight**, và pin managed versions được kiểm thử.

### 19.5. Boot Loader không tự bảo vệ artifact khỏi tấn công

Nested JAR layout là **định dạng triển khai**, không phải encryption, sandbox hay kiểm soát an toàn thư viện. Người có JAR có thể đọc libraries và application classes bằng công cụ archive; cần bảo vệ secrets bằng runtime configuration và áp dụng SBOM, vulnerability scanning, signing/verification theo chính sách dự án.

## 20. Bảng chẩn đoán lỗi theo tầng khởi động

| Triệu chứng | Tầng cần kiểm tra | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- | --- |
| **no main manifest attribute** | java -jar/manifest | Đang chạy plain JAR, không có Main-Class | Xác định đúng bootJar/repackaged JAR; kiểm tra manifest |
| **Could not find or load main class ...JarLauncher** | Manifest/Boot Loader | Main-Class trỏ sai launcher theo version hoặc launcher classes bị thiếu | Mở manifest và jar tf; dùng plugin đúng nhánh Boot |
| **ClassNotFoundException: com.example....Application** | Start-Class/app classes | Sai FQCN main class, thiếu compiled class, app class không ở BOOT-INF/classes | Xem Start-Class, jar tf và cấu hình mainClass |
| **NoClassDefFoundError: ...jackson...** | Nested dependencies | JAR bị loại khỏi runtime classpath, archive thiếu BOOT-INF/lib hoặc loader không đọc được | Kiểm tra jar tf và Maven/Gradle runtime deps |
| **ClassNotFoundException khi dùng -cp boot.jar app.Main** | Java standard classpath | Class ở BOOT-INF/classes, không nằm root JAR | Dùng java -jar boot archive |
| **Nested JAR file cannot be opened / cannot seek** | Nested JAR format | Outer JAR bị repack sai, compression entry không STORED, archive hỏng | Rebuild bằng Boot plugin; kiểm tra công cụ tái nén |
| **UnsupportedClassVersionError** | JVM bytecode compatibility | Class build bằng Java mới hơn JVM deploy | Đồng bộ JDK compile/runtime và Spring Boot requirements |
| **UnsatisfiedLinkError** | Native library loading | JNI/native libs chưa extract hoặc sai platform | Kiểm tra thư viện native và cơ chế unpack |
| **java -jar chạy được nhưng IDE chạy khác** | Classpath/resources/profile | IDE bootRun dùng external JARs và đường nguồn khác | So sánh properties, classpath, active profiles, resource URLs |
| **jar tf có library nhưng code vẫn ClassNotFound** | Class loader/SPIs | Library dùng system loader hoặc custom resource resolution | TCCL, supported APIs và thư viện tương thích Boot |
| **Không có BOOT-INF/lib** | Packaging | Chạy nhầm plain JAR hoặc dependencies bị exclude | Kiểm tra bootJar/repackage task và output artifact |
| **Class-Path thiếu trong manifest** | Hiểu lầm định dạng Boot | Boot không cần manifest Class-Path kiểu external libs | Xem BOOT-INF/lib và JarLauncher |
| **Port already in use** | Spring runtime | Boot Loader đã làm xong, web server không bind port | Đổi server.port hoặc dừng process đang giữ port |
| **BeanCreationException** | Spring ApplicationContext | Lỗi DI/config sau khi đã nạp classes | Đọc nested cause và config, không mặc định lỗi loader |

Đọc log theo trình tự: **Java launcher → Boot launcher → ClassLoader → application main → Spring context → web server**. Nếu đã thấy Spring banner và lỗi bean, phần Boot Loader thường đã hoàn thành vai trò khởi động ban đầu; không nên đổ mọi lỗi cho nested JAR.

## 21. Khi cần kiểm chứng loader có được đóng đúng hay không

Một checklist thực tế trước deploy:

1. **Biết chính xác file sẽ chạy:** trong Maven thường là **target/<artifactId>-<version>.jar**, trong Gradle là **build/libs/<project>-<version>.jar** (tên có thể custom).
2. **Xác nhận boot packaging:** Maven có spring-boot-maven-plugin và execution repackage phù hợp; Gradle thực hiện bootJar.
3. **Kiểm tra archive entries:** có **BOOT-INF/classes**, **BOOT-INF/lib**, loader classes.
4. **Đọc manifest:** **Main-Class** trỏ launcher, **Start-Class** trỏ application main class.
5. **Xem runtime dependencies:** Jackson/Spring/libs cần thiết thực sự có ở BOOT-INF/lib; test-only dependencies không cần ở đó.
6. **Chạy java -jar:** dùng JVM tương thích với bản Spring Boot/class files; quan sát log khởi động.
7. **Gọi smoke endpoint/batch job:** xác minh application thực sự sử dụng được dependency lồng, không chỉ hiện banner.
8. **Không sửa JAR bằng công cụ zip không kiểm soát** sau khi build; nếu buộc phải ký/đóng gói lại, bảo đảm tương thích Boot Loader.
9. **Không dùng -cp boot.jar app.Main** để thay java -jar; nếu có mục tiêu exploded classpath, thiết kế riêng.
10. **Phân biệt lỗi class loading với lỗi Spring startup**, dùng đúng log/công cụ cho từng tầng.

### Kiểm tra riêng dependency graph trước packaging

Maven:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Có dependency ở runtime graph **là điều cần**, nhưng không tự chứng minh nó đã nằm trong **executable archive thực sự deploy** nếu packaging được custom. Ngược lại, thấy JAR trong BOOT-INF/lib không tự chứng minh app code có thể gọi mọi API từ nó nếu class loader, version compatibility hoặc runtime config sai.

## 22. Câu hỏi tự đánh giá

**Câu 1.** Tại sao Java có thể chạy **java -cp main.jar:lib.jar Main** nhưng không tự chạy một **lib.jar** nằm trong **main.jar/BOOT-INF/lib**?

**Đáp án:** Trong lệnh classpath đầu, main.jar và lib.jar là hai file riêng được khai báo làm classpath entries. Ở trường hợp lồng, lib.jar chỉ là một ZIP entry trong outer JAR; classpath/JAR loading tiêu chuẩn không đệ quy tìm JAR entries rồi nạp classes từ đó.

**Câu 2.** Trong Spring Boot executable JAR, **Main-Class** và **Start-Class** khác nhau thế nào?

**Đáp án:** **Main-Class** thường trỏ tới Boot **JarLauncher** để Java gọi trước. **Start-Class** trỏ tới main application class được Boot Loader gọi sau khi thiết lập class loader có khả năng nạp nested dependencies.

**Câu 3.** JVM có thực sự cần Spring Boot Loader để chạy bất kỳ ứng dụng dùng Jackson không?

**Đáp án:** Không. Nếu Jackson JAR nằm ngoài và đã được khai báo trực tiếp trong Java classpath, JVM có thể nạp class bằng cơ chế tiêu chuẩn. Boot Loader cần thiết khi dùng **layout archive JAR lồng JAR** theo Spring Boot để chạy như một file bằng java -jar.

**Câu 4.** Một JAR có **BOOT-INF/lib/jackson-databind.jar**, vì sao **jar tf** không in từng class của Jackson?

**Đáp án:** **jar tf** đang liệt kê entries của outer JAR, nên thấy một entry mang tên nested JAR. Muốn xem entries bên trong JAR con, cần đọc/mở thêm tầng archive hoặc dùng công cụ biết nested layout.

**Câu 5.** Tại sao **ClassLoader.getSystemClassLoader()** có thể thất bại nhưng **Thread.currentThread().getContextClassLoader()** tìm thấy cùng class?

**Đáp án:** Boot Launcher tạo hoặc cấu hình class loader nhìn thấy **BOOT-INF/classes** và **BOOT-INF/lib**. System loader không mặc nhiên nhìn thấy nested libs, còn TCCL phù hợp trong luồng do application launcher thiết lập có thể nhìn thấy chúng.

**Câu 6.** Tại sao **ZipEntry.STORED** quan trọng với nested JAR?

**Đáp án:** Để Spring Boot Loader có thể seek theo physical byte offsets trong outer JAR khi đọc entry của JAR con mà không phải bung toàn bộ outer archive. Nested JAR bên trong vẫn có thể chứa các ZIP entries được nén riêng.

**Câu 7.** File **BOOT-INF/layers.idx** có phải nguyên nhân JVM tìm được Jackson không?

**Đáp án:** Không. layers.idx là metadata phân lớp phục vụ image/build tooling. Loader và nested-JAR class loader mới chịu trách nhiệm tìm classes trong nested JARs; classpath.idx (nếu có) hỗ trợ thứ tự JARs khi java -jar.

**Câu 8.** Vì sao **./gradlew bootRun** thành công nhưng **java -jar build/libs/app.jar** thất bại?

**Đáp án:** Hai cách chạy dùng classpath/layout khác nhau. bootRun dùng classes/resources và dependency JARs riêng trên filesystem; executable JAR dùng Boot Loader với nested archives. Cần kiểm tra manifest, BOOT-INF/lib, cấu hình packaging, classloader và resource APIs của ứng dụng.

**Câu 9.** Nếu jar tf cho thấy đủ nested JARs, có thể bỏ integration test không?

**Đáp án:** Không. Việc có các archive đúng vị trí là bằng chứng packaging, không chứng minh versions tương thích, bean wiring đúng, web server khởi động hoặc business logic hoạt động. Vẫn cần tests và smoke test artifact thật.

## 23. Kết luận: “JVM cần Boot Loader” phải hiểu theo đúng ngữ cảnh

**Trong ngữ cảnh executable JAR có nested JARs của Spring Boot**, Java launcher có thể nạp Boot Loader ở root archive, nhưng **không tự biết mở từng JAR nằm bên trong BOOT-INF/lib thành một nguồn classpath**. Spring Boot Loader thiết lập classpath và class loader thích hợp cho application classes và runtime libraries, sau đó gọi **Start-Class.main()**.

~~~text
java -jar app.jar
    -> manifest Main-Class
    -> org.springframework.boot.loader.launch.JarLauncher
    -> BOOT-INF/classes + BOOT-INF/lib/*.jar
    -> nested-JAR class loader
    -> manifest Start-Class
    -> Application.main()
    -> SpringApplication.run()
~~~

Điều đáng nhớ là **Spring Boot Loader giải quyết một vấn đề của định dạng đóng gói**, không phải thay JVM hay Spring Framework. Nếu chuyển sang plain JAR với external libs, shaded JAR hoặc exploded deployment, cách cấu hình classpath và launcher sẽ khác. Để tự tin khi deploy, kiểm tra **manifest, nested entries và một lần chạy java -jar thực tế**.

## 24. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Executable JAR Format: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html
- Spring Boot 3.5 — Nested JARs: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html
- Spring Boot 3.5 — Spring Boot's NestedJarFile Class: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/jarfile-class.html
- Spring Boot 3.5 — Launching Executable Jars: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html
- Spring Boot 3.5 — Executable JAR Restrictions: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/restrictions.html
- Spring Boot 3.5 — Create Executable JAR & requiresUnpack: https://docs.spring.io/spring-boot/3.5/how-to/build.html
- Spring Boot 3.5 — Maven Plugin Packaging: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle Plugin Packaging: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Oracle Java — Java launcher command (-jar and classpath): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java — JAR File Specification: https://docs.oracle.com/javase/8/docs/technotes/guides/jar/jar.html
