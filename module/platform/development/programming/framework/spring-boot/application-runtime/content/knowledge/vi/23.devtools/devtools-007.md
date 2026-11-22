# Chẩn đoán lỗi classloader trong dự án nhiều module dùng Spring Boot Devtools

## 1. Hiện tượng và mục tiêu

Trong dự án Spring Boot có nhiều Maven/Gradle modules, lập trình viên có thể gặp tình huống code chạy đúng khi đóng gói JAR nhưng bị lỗi khi chạy từ IDE hoặc sau một lần Devtools tự khởi động lại:

- ClassCastException với thông báo một class không thể cast thành chính class cùng tên.
- ClassNotFoundException, NoClassDefFoundError hoặc LinkageError ở một module dùng chung.
- Một annotation hoặc service provider được tìm thấy trong lần chạy đầu nhưng không được nhận diện sau restart.
- Đổi mã của module library, IDE thông báo build thành công nhưng app vẫn dùng hành vi cũ.
- Lỗi chỉ xuất hiện sau lần restart thứ hai hoặc thứ ba.
- Đóng Devtools restart thì lỗi biến mất; đổi sang JAR chạy bình thường lại không thể tái hiện.

Những biểu hiện này không tự chứng minh Devtools có bug. Ta cần phân biệt **classloader identity**, **classpath visibility**, **dependency/version mismatch**, **stale build output** và **lifecycle leak**.

Bài này hướng dẫn phương pháp có thể tái hiện: xác định code thực sự được nạp từ đâu, đo loader của từng class, thử tắt restart trong cùng điều kiện, cấu hình META-INF/spring-devtools.properties khi cần, rồi kiểm tra lại lỗi gốc. Ví dụ dùng **Spring Boot 3.5.x và Java 17+**.

## 2. Vì sao cùng tên class lại không cùng kiểu?

Trong Java, class identity phụ thuộc ít nhất vào hai yếu tố:

~~~text
Class identity = (binary name, defining ClassLoader)

Ví dụ:
  example.contract.SharedMessage  do Loader A định nghĩa
  example.contract.SharedMessage  do Loader B định nghĩa

Dù binary name giống nhau, đây là hai Class objects khác nhau
khi A và B thực sự định nghĩa class độc lập.
~~~

Một object của loại được Loader A định nghĩa không tự cast được sang loại cùng tên do Loader B định nghĩa. Đây là lý do có thể thấy thông báo kiểu:

~~~text
ClassCastException:
example.contract.SharedMessage cannot be cast to
example.contract.SharedMessage
~~~

Không nên chỉ nhìn FQCN mà kết luận compiler hoặc JVM bị sai. Hãy đo **Class.getClassLoader()**, so sánh hai Class objects bằng toán tử **==** và kiểm tra **CodeSource**. Một loader cũng có thể ủy quyền cho parent; do đó loader mà code gọi để tìm class không nhất thiết là loader cuối cùng định nghĩa class.

### Những gì thường bị nhầm

- Hai class khác nhau nhưng **cùng tên** chưa chắc có cùng binary compatibility.
- Một **CodeSource URL** giống nhau chưa chắc hai Class objects cùng identity nếu được hai loaders định nghĩa độc lập.
- Loader hiển thị trong log không chắc là nguyên nhân gốc; một dependency có thể thiếu hoặc bị đóng gói sai.
- ClassCastException có thể xuất hiện ở plugin architecture, OSGi hoặc custom URLClassLoader mà không liên quan Spring Boot Devtools.

## 3. Base classloader và restart classloader

Spring Boot Devtools dùng **hai classloaders** để tự động restart nhanh:

| Loader | Thường nạp | Hành vi khi Devtools restart |
| --- | --- | --- |
| Base | Thư viện ổn định từ các JARs, ví dụ third-party dependencies | Thường được tái sử dụng |
| Restart | Application classes và resources đang phát triển, thường từ output directories của IDE | Được thay thế bằng loader mới |

Sơ đồ:

~~~text
JVM không thoát
      |
      +-- Base ClassLoader
      |     Spring/third-party JAR
      |     một số module được resolve từ JAR
      |     được giữ qua restart
      |
      +-- Restart ClassLoader #1
            app/target/classes
            một số IDE open projects
               |
      Devtools nhận thay đổi classpath
               |
      +-- Base ClassLoader vẫn còn
      |
      +-- Restart ClassLoader #2
            khởi tạo ApplicationContext mới
            nạp lại application classes
~~~

Cơ chế này giảm thời gian restart vì không nạp lại mọi JAR. Nó cũng tạo ra ranh giới: code trong **base** có thể được nạp trước code trong **restart**, hoặc một module bị coi là JAR ổn định dù source của nó đang được sửa trong cùng repository.

Đặc biệt, Spring Boot 3.5 Reference nêu rằng **mỗi open project trong IDE thường được nạp qua restart loader**, còn **regular JAR files thường được nạp qua base loader**. Với Maven spring-boot:run hoặc Gradle bootRun, module chứa @SpringBootApplication có thể thuộc restart, trong khi các modules khác được resolved dạng JAR lại thuộc base. Đây là **mặc định có điều kiện**, không nên đoán thay cho việc kiểm tra runtime classpath thật.

### Project nhiều module dễ có hai hình dạng classpath

~~~text
IDE mở cả hai modules:
  app/target/classes/                 -> thường restart
  shared-contract/target/classes/     -> thường restart
  spring-core-*.jar                   -> thường base

Maven chỉ chạy module app:
  app/target/classes/                 -> thường restart
  ~/.m2/.../shared-contract-*.jar     -> thường base
  spring-core-*.jar                   -> thường base
~~~

Nếu một module cung cấp DTO, annotation, interface, proxy hoặc library integration cần được nạp cùng phần application classes, khác biệt đó có thể gây ClassCastException, lỗi reflection hoặc không tìm thấy type.

**Cần phân biệt:** base và restart cùng tồn tại là thiết kế bình thường. Lỗi chỉ xuất hiện khi class bị định nghĩa không tương thích giữa các loaders, loader thiếu visibility, hoặc giữ object từ một restart generation cũ.

## 4. Phép thử đầu tiên: tắt hoàn toàn Devtools restart

Spring Boot hướng dẫn cách đầu tiên để chẩn đoán là **tạm vô hiệu hóa restart**. Nếu lỗi biến mất, classloader boundary của Devtools đáng được điều tra.

### Cách chắc chắn: JVM System property

Trong **VM options** của IDE chạy ứng dụng:

~~~text
-Dspring.devtools.restart.enabled=false
~~~

Hoặc đặt **trước SpringApplication.run**:

~~~java
package example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AppWithoutRestart {

    public static void main(String[] args) {
        System.setProperty(
                "spring.devtools.restart.enabled", "false");
        SpringApplication.run(AppWithoutRestart.class, args);
    }
}
~~~

Đây là **file Java hoàn chỉnh** nếu có dependency Spring Boot phù hợp; nó được dùng như lựa chọn chẩn đoán, không phải entrypoint đồng thời với demo ở phần 8.

Trong Maven plugin có thể truyền JVM argument đến JVM của ứng dụng:

~~~bash
mvn -pl app spring-boot:run -Dspring-boot.run.jvmArguments=-Dspring.devtools.restart.enabled=false
~~~

Cách quote tham số có thể khác theo shell; khi dùng IDE, nhập VM option trực tiếp vào Run Configuration dễ kiểm soát hơn. Điều quan trọng: property phải đến **JVM của ứng dụng trước run**, không chỉ tới Maven launcher ở tiến trình khác.

### Vì sao đặt trong application.properties chưa đủ?

~~~properties
spring.devtools.restart.enabled=false
~~~

Theo Spring Boot 3.5 Reference, cách này thường **ngừng việc theo dõi file để restart**, nhưng **restart classloader vẫn có thể được khởi tạo**. Vì vậy nó chưa phải phép thử cô lập triệt để classloader. Khi cần loại hoàn toàn hỗ trợ restart, dùng System property sớm hoặc bỏ dependency Devtools khỏi classpath.

### Ma trận so sánh

| Trạng thái | Điều quan sát | Kết luận tạm thời |
| --- | --- | --- |
| Devtools restart bật | Có ClassCastException | Chưa đủ chứng cứ |
| Cùng launch mode, System property tắt restart | Hết lỗi | Bằng chứng mạnh cho boundary Devtools |
| Cả hai đều lỗi | Kiểm tra dependencies, JAR, version, missing class |
| java -jar chạy được, IDE lỗi | So sánh classpath và packaging; không chỉ riêng Devtools |
| Sau nhiều restart mới lỗi | Kiểm tra static cache, threads, TCCL và classloader leak |

Đừng đổi đồng thời **cách launch, phiên bản Java, Maven profile và cấu hình restart** khi đang so sánh. Tốt nhất là thay đúng một biến để kết quả có thể giải thích.

## 5. Thu thập bằng chứng đúng class, đúng loader

Đối với những type xuất hiện trong stack trace, nên thu:

1. Binary class name.
2. Định danh **Class.getClassLoader()**.
3. URL nguồn class qua **getProtectionDomain().getCodeSource()**, nếu tồn tại.
4. **Thread.currentThread().getContextClassLoader()** ở thread gây lỗi.
5. Các URL của resource tên **path/to/Type.class** từ getResources.
6. Build tool dependency tree và classpath runtime.
7. Thời điểm lỗi: startup đầu, sau compile hay sau một vài restart.
8. Kết quả khi tắt restart hoàn toàn.

Một helper Java:

~~~java
package example.app;

import java.security.CodeSource;

public final class LoaderInfo {

    private LoaderInfo() {
    }

    public static void print(String label, Class<?> type) {
        ClassLoader loader = type.getClassLoader();
        CodeSource source =
                type.getProtectionDomain().getCodeSource();

        System.out.println(label + ".name=" + type.getName());
        System.out.println(label + ".loader="
                + (loader == null ? "bootstrap"
                        : loader.getClass().getName() + "@"
                        + Integer.toHexString(
                                System.identityHashCode(loader))));
        System.out.println(label + ".source="
                + (source == null
                        ? "<unknown>"
                        : source.getLocation()));
    }
}
~~~

Đây là một **helper Java có thể biên dịch**, nhưng không có main; hãy gọi từ code khác. **CodeSource** có thể null, đặc biệt với bootstrap/generated classes, và identity hashcode không ổn định giữa các JVM runs.

Một đoạn cần chạy ở đúng thread bị lỗi:

~~~java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

System.out.println("TCCL=" + tccl);
~~~

Đây là mảnh code minh họa. **TCCL** đặc biệt hữu ích khi thư viện dùng reflection, ServiceLoader, resource lookup hoặc deserialization.

Không log classpath paths/CodeSource cùng credentials hay dữ liệu nội bộ vào endpoint công khai. Phép đo chỉ nên diễn ra trong môi trường dev/test.

## 6. Đọc các exception có ngữ cảnh

| Dấu hiệu | Nhóm nguyên nhân cần ưu tiên |
| --- | --- |
| Foo cannot be cast to Foo | Hai defining classloaders hoặc old restart generation |
| ClassNotFoundException | Loader hiện tại không tìm thấy type hoặc thiếu artifact |
| NoClassDefFoundError | Class không thể load/initialize, có thể thiếu dependency hoặc init fail |
| LinkageError: loader constraint violation | Visibility/type constraint giữa loaders |
| NoSuchMethodError | Binary incompatibility, version hoặc artifact runtime cũ |
| TypeNotPresentException | Reflection/annotation tham chiếu type không hiện diện |
| @Component/@Configuration không được phát hiện | Scanning/conditional hoặc annotation type/loader |
| ObjectInputStream ClassNotFoundException | Deserialization dùng loader không thấy restart classes |
| Sửa code nhưng không đổi behavior | Classpath chưa được compile/copy hoặc JAR trong ~/.m2 cũ |

**Không gán một exception class với một nguyên nhân duy nhất.** Chẳng hạn NoClassDefFoundError có thể đến từ một static initializer lỗi trước đó; hãy đọc Caused by và thời điểm lỗi đầu tiên. NoSuchMethodError thường là mismatch giữa compile-time và runtime API, không phải mặc nhiên một sự cố Devtools.

## 7. Ví dụ Maven multi-module thực tế

Ta tạo reactor gồm:

- **shared-contract:** JAR Java 17 chỉ chứa record dùng chung.
- **app:** Spring MVC executable application, phụ thuộc shared-contract, thêm spring-boot-devtools.
- Một ApplicationRunner in loader, CodeSource, TCCL và cố ý tạo một class identity mismatch bằng URLClassLoader độc lập để giải thích ClassCastException.

### Cây thư mục

~~~text
multi-module-devtools/
  pom.xml
  shared-contract/
    pom.xml
    src/main/java/example/contract/SharedMessage.java
  app/
    pom.xml
    src/main/java/example/app/MultiModuleApplication.java
    src/main/resources/application.properties
~~~

### Root pom.xml

~~~xml
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

    <groupId>example</groupId>
    <artifactId>multi-module-devtools</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared-contract</module>
        <module>app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
    </properties>
</project>
~~~

Root là aggregator POM. Spring Boot parent quản lý Java version, dependency BOM và plugin versions cho các modules.

### shared-contract/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>example</groupId>
        <artifactId>multi-module-devtools</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>shared-contract</artifactId>
    <packaging>jar</packaging>
</project>
~~~

Đây là module JAR bình thường, không có dependency Spring hoặc Devtools. Khi IDE resolve nó thành output directory hay Maven lấy JAR từ repository, classloader placement có thể khác.

### shared-contract/src/main/java/example/contract/SharedMessage.java

~~~java
package example.contract;

public record SharedMessage(String value) {
}
~~~

Đây là một Java 17 record hợp lệ, có constructor public **SharedMessage(String)** và accessor **value()**.

### app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>example</groupId>
        <artifactId>multi-module-devtools</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>

    <dependencies>
        <dependency>
            <groupId>example</groupId>
            <artifactId>shared-contract</artifactId>
            <version>0.0.1-SNAPSHOT</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <optional>true</optional>
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

Devtools chỉ đặt ở module executable app với **optional=true**. Ở Gradle, cấu hình thường là **developmentOnly("org.springframework.boot:spring-boot-devtools")**. Không thêm Devtools ở mọi module dependency.

### app/src/main/resources/application.properties

~~~properties
spring.application.name=multi-module-devtools
server.address=127.0.0.1
server.port=8080
~~~

Bind localhost vì ứng dụng minh họa dùng cho development và chẩn đoán. Trong môi trường deploy thật, ứng dụng có thể cần bind 0.0.0.0 tùy network policy.

### app/src/main/java/example/app/MultiModuleApplication.java

~~~java
package example.app;

import java.net.URL;
import java.net.URLClassLoader;
import java.security.CodeSource;
import java.util.Enumeration;

import example.contract.SharedMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MultiModuleApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiModuleApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectClassLoaders() {
        return args -> {
            printType("APP", MultiModuleApplication.class);
            printType("SHARED", SharedMessage.class);

            ClassLoader tccl =
                    Thread.currentThread().getContextClassLoader();
            System.out.println("TCCL=" + label(tccl));

            if (tccl != null) {
                Enumeration<URL> resources = tccl.getResources(
                        "example/contract/SharedMessage.class");
                int count = 0;
                while (resources.hasMoreElements()) {
                    count++;
                    System.out.println("SHARED_RESOURCE_"
                            + count + "=" + resources.nextElement());
                }
                System.out.println("SHARED_RESOURCE_COUNT=" + count);
            }

            demonstrateIdentity();
            System.out.println("DIAGNOSTICS_DONE");
        };
    }

    private static void printType(String key, Class<?> type) {
        CodeSource source =
                type.getProtectionDomain().getCodeSource();

        System.out.println(key + "_CLASS=" + type.getName());
        System.out.println(key + "_LOADER="
                + label(type.getClassLoader()));
        System.out.println(key + "_SOURCE="
                + (source == null ? "<unknown>"
                        : source.getLocation()));
    }

    private static String label(ClassLoader loader) {
        if (loader == null) {
            return "bootstrap";
        }
        return loader.getClass().getName() + "@"
                + Integer.toHexString(
                        System.identityHashCode(loader));
    }

    private static void demonstrateIdentity() throws Exception {
        CodeSource source =
                SharedMessage.class.getProtectionDomain()
                        .getCodeSource();

        if (source == null || source.getLocation() == null) {
            System.out.println("ISOLATION_SKIPPED=no-code-source");
            return;
        }

        URL root = source.getLocation();

        // Thí nghiệm có chủ đích, KHÔNG phải lỗi Devtools.
        try (URLClassLoader isolated = new URLClassLoader(
                new URL[] { root }, null)) {

            Class<?> again = Class.forName(
                    "example.contract.SharedMessage",
                    true, isolated);

            System.out.println("SAME_BINARY_NAME="
                    + again.getName().equals(
                            SharedMessage.class.getName()));
            System.out.println("SAME_CLASS_IDENTITY="
                    + (again == SharedMessage.class));

            Object otherInstance = again.getConstructor(String.class)
                    .newInstance("other-loader");

            try {
                SharedMessage unexpected =
                        (SharedMessage) otherInstance;
                System.out.println("UNEXPECTED_CAST="
                        + unexpected.value());
            } catch (ClassCastException expected) {
                System.out.println("ISOLATED_CAST_FAILED=true");
            }
        }
    }

    @RestController
    static class PingController {

        @GetMapping("/demo/ping")
        public String ping() {
            return new SharedMessage("pong").value();
        }
    }
}
~~~

### Giải thích tính runnable

- Tất cả imports được khai báo. App chạy trên Java 17 với record type nằm trong shared-contract.
- Spring Boot Starter Web khởi tạo embedded Tomcat; @RestController nested static được component scan phát hiện.
- ApplicationRunner được chạy sau context refresh.
- URLClassLoader được tạo từ CodeSource URL của SharedMessage. Nếu module shared là JAR từ Maven repository, URL đó thường trỏ tới file .jar. Nếu module được import dưới dạng output directory, nó có thể trỏ tới thư mục classes.
- Loader có parent **null** trong thí nghiệm để không delegate SharedMessage cho application loader; nó vẫn truy cập các bootstrap Java core classes.
- Cả hai Class objects có FQCN giống nhau, nhưng khác defining loader. Cast được **cố ý** thử và bắt ClassCastException.
- Nếu CodeSource không có, demo ghi ISOLATION_SKIPPED, không đoán đường dẫn.
- Các giá trị CodeSource, hashcode, số resource URLs và classloader cụ thể tùy môi trường.

Đây là **một ứng dụng chạy bình thường**; ClassCastException cố tình tạo được bắt để chương trình tiếp tục. Nó không phải ví dụ cố tạo lỗi Spring context khi startup.

### Build và chạy

Ở thư mục root:

~~~bash
java -version
mvn -version

# Build tất cả module dependencies và cài vào local Maven repository:
mvn -pl app -am install -DskipTests

# Sau đó chạy riêng module có Spring Boot main:
mvn -pl app spring-boot:run
~~~

Lệnh đầu dùng **-pl app -am** để build app cùng module phụ thuộc trong reactor. Lệnh thứ hai chỉ chạy app, nên shared-contract có thể được resolve từ JAR đã install ở Maven local repository. Nếu bạn import cả reactor vào IDE và chạy main trực tiếp, classpath shape có thể khác.

Không chạy **spring-boot:run** trên mọi reactor module, vì module shared-contract không có Spring Boot main application.

Khi app đang chạy, kiểm tra:

~~~bash
curl -i http://127.0.0.1:8080/demo/ping
~~~

Body:

~~~text
pong
~~~

HTTP status kỳ vọng là 200 khi server hoạt động bình thường. Các HTTP headers và format version tùy Tomcat/curl.

### Các marker tự in

Nếu URL CodeSource có thể dùng cho một URLClassLoader độc lập, những marker có giá trị xác định:

~~~text
APP_CLASS=example.app.MultiModuleApplication
SHARED_CLASS=example.contract.SharedMessage
SAME_BINARY_NAME=true
SAME_CLASS_IDENTITY=false
ISOLATED_CAST_FAILED=true
DIAGNOSTICS_DONE
~~~

Ví dụ **chỉ minh họa hình dạng** của các dòng biến đổi:

~~~text
APP_LOADER=org.springframework.boot.devtools.restart.classloader.RestartClassLoader@...
SHARED_LOADER=jdk.internal.loader.ClassLoaders$AppClassLoader@...
SHARED_SOURCE=file:/.../.m2/repository/example/shared-contract/0.0.1-SNAPSHOT/shared-contract-0.0.1-SNAPSHOT.jar
TCCL=org.springframework.boot.devtools.restart.classloader.RestartClassLoader@...
SHARED_RESOURCE_COUNT=1
~~~

Không viết test phụ thuộc vào **...**, loader identity hashcode, exact path hoặc count 1. Điều cần đối chiếu là **APP_LOADER vs SHARED_LOADER** và **SOURCE là classes directory hay JAR**.

**Quan trọng:** ngay cả sau khi sửa mapping classloader thành công, dòng **ISOLATED_CAST_FAILED=true** vẫn có thể xuất hiện vì demo cố ý tạo một loader thứ ba độc lập. Không lấy đó làm bằng chứng bản sửa thất bại.

## 8. So sánh bản chạy có restart và không restart

Chạy app như trên với Devtools enabled và lưu phần output diagnostic. Sau đó dừng hẳn JVM, chạy lại bằng VM option:

~~~text
-Dspring.devtools.restart.enabled=false
~~~

Trong IDE, đặt vào cấu hình Run. Với Maven plugin, truyền JVM argument như mục 4.

So sánh ít nhất:

| Dữ liệu | Restart enabled | Restart disabled |
| --- | --- | --- |
| APP_LOADER | Có thể là RestartClassLoader | Thường là application loader thông thường |
| SHARED_LOADER | Base hoặc restart tùy classpath | Theo classpath khi không dùng Devtools restart |
| APP_SOURCE | app/classes | Có thể vẫn app/classes |
| SHARED_SOURCE | JAR hoặc classes directory | Theo cách Maven/IDE resolve |
| Lỗi nghiệp vụ gốc | Có/không | Có/không |
| URLClassLoader intentional cast | Vẫn fail theo thiết kế demo | Vẫn fail theo thiết kế demo |

Cần đánh giá **lỗi nghiệp vụ gốc**, không đánh giá thông qua thí nghiệm type identity có chủ đích.

Nếu lỗi chỉ xảy ra khi restart enabled, ưu tiên module classpath mapping, TCCL, reflection/deserialization hoặc references từ restart loader cũ. Nếu lỗi vẫn xảy ra ở cả hai, ưu tiên dependency versions và build output.

## 9. Cấu hình META-INF/spring-devtools.properties

Spring Boot 3.5 cung cấp file **META-INF/spring-devtools.properties** để chỉ định các classpath entries được kéo vào restart loader hoặc đẩy xuống base loader.

Ví dụ sau khi đã xác minh shared-contract nằm trong JAR ở base nhưng muốn đưa module đó vào restart:

Tạo file:

~~~text
app/src/main/resources/META-INF/spring-devtools.properties
~~~

Nội dung:

~~~properties
# Pattern áp lên classpath entry, không phải Java package name.
restart.include.shared-contract=.*shared-contract-0[.]0[.]1-SNAPSHOT[.]jar
~~~

Giải thích:

- Key bắt đầu **restart.include.**.
- Tên suffix **shared-contract** để phân biệt rule; mọi key cần duy nhất.
- Regex khớp classpath entry có filename **shared-contract-0.0.1-SNAPSHOT.jar**.
- Dùng **[.]** cho dấu chấm literal, tránh việc escape backslash qua Java Properties.
- Nếu artifact version khác hoặc classpath path khác, phải chỉnh regex để khớp **đúng classpath entry đang chạy**.
- Nếu import module shared như output directory, entry có thể không chứa tên JAR; regex này sẽ không match.

Ví dụ cho module classes directory:

~~~properties
restart.include.shared-classes=.*shared-contract.*target.*classes.*
~~~

Đây là regex tương đối rộng cho mục đích minh họa; hãy thu hẹp theo path thực và chỉ dùng nếu module không nằm trong restart loader sẵn. Đừng copy cả hai rules vào mọi project mà không đo.

### Trường hợp đưa library về base

Có thể dùng:

~~~properties
restart.exclude.legacy-library=.*legacy-library-1[.]2[.]3[.]jar
~~~

Key prefix **restart.exclude.** sẽ chỉ thị classpath entry tương ứng thuộc **base classloader**. Chỉ làm khi bạn biết thư viện cần tồn tại ổn định và không phụ thuộc application-specific types từ restart loader.

### Quy tắc quan trọng của Spring Boot

- File phải ở **META-INF/spring-devtools.properties**, được copy vào runtime classpath.
- Prefix keys là **restart.include.** và **restart.exclude.**.
- Giá trị property là **regex áp vào classpath paths**, không phải quy tắc package name.
- Mọi keys phải duy nhất.
- Spring Boot đọc **tất cả** META-INF/spring-devtools.properties trên classpath, kể cả file nằm trong JAR thư viện.
- Những loader mapping rules **không thay thế bằng System properties** thông thường.
- Sau khi thêm/sửa file, restart JVM để có một phép thử rõ ràng, rồi đọc lại **APP_LOADER**, **SHARED_LOADER** và lỗi thật.
- Không đưa tất cả third-party libraries lên restart loader nếu không có lý do; làm thế giảm lợi ích restart và có thể gây vấn đề khác.

### Điều gì KHÔNG phải loader mapping?

Trong **application.properties** có:

~~~properties
spring.devtools.restart.exclude=static/**,public/**
spring.devtools.restart.additional-exclude=generated/**
spring.devtools.restart.additional-paths=../shared-contract/src/main
~~~

Các property này cấu hình **watcher**: path nào thay đổi thì restart/reload, và theo dõi path ngoài classpath. Chúng **không có nghĩa di chuyển module sang base hoặc restart loader**.

So sánh:

| Tên | Nơi đặt | Tác dụng |
| --- | --- | --- |
| spring.devtools.restart.exclude | application.properties | Tránh full restart khi một số resources thay đổi |
| spring.devtools.restart.additional-exclude | application.properties | Bổ sung exclusion paths cho watcher |
| spring.devtools.restart.additional-paths | application.properties | Theo dõi thêm paths |
| restart.include.shared-contract | META-INF/spring-devtools.properties | Đưa classpath entry sang restart loader |
| restart.exclude.legacy-library | META-INF/spring-devtools.properties | Đưa entry sang base loader |

**Không đặt restart.include.shared-contract trong application.properties rồi kỳ vọng classloader mapping hoạt động.**

## 10. Reflection và annotation không được nhận diện

Spring Boot Devtools Reference nêu vấn đề một số classes được **reflection** load, nhất là **annotations**, có thể được parent loader nạp sớm trước khi classes ứng dụng sử dụng annotations đó được restart loader nạp.

Cách điều tra:

1. Xác định annotation FQCN, module định nghĩa và runtime CodeSource.
2. In loader của annotation type được framework dùng, so sánh với type mà application nhìn thấy.
3. Kiểm tra missing dependencies, component scan base packages và @Conditional trước khi đổ lỗi classloader.
4. Tắt hẳn Devtools restart, xem kết quả có đổi không.
5. Nếu xác nhận boundary mismatch, cân nhắc đưa project-related annotation module vào restart loader bằng include rule.
6. Kiểm thử lại startup, reflection và proxy behavior ở lần restart tiếp theo.

Một class không được Spring scan **không mặc nhiên** là lỗi classloader: package scan, annotation metadata và condition evaluation cũng có thể là nguyên nhân.

## 11. ServiceLoader và thread context classloader

Một số thư viện tìm plugins thông qua **java.util.ServiceLoader**, dùng TCCL hoặc explicit loader.

Mảnh minh họa:

~~~java
ServiceLoader<MyService> loader =
        ServiceLoader.load(
                MyService.class,
                Thread.currentThread().getContextClassLoader());
~~~

Đoạn này chưa độc lập: cần import **java.util.ServiceLoader** và interface **MyService**. Khi provider implementation nằm trong restart nhưng interface lại được định nghĩa hai lần bởi loaders khác nhau, việc chỉ đổi TCCL không sửa được type identity. Phải kiểm tra:

- Service interface được định nghĩa bởi loader nào?
- Provider implementation có visibility và đúng type identity không?
- JAR có file META-INF/services phù hợp?
- Runtime TCCL có trỏ tới loader đúng không?
- Module build/dependency version có chính xác không?

Không dùng setContextClassLoader tùy tiện để che một dependency thiếu. Nếu một thư viện cần thay TCCL tạm thời, phải restore trong finally và xem contract của thư viện.

## 12. ObjectInputStream và serialization

Tài liệu Spring Boot 3.5 nêu rằng Devtools restart có thể không hợp với **standard ObjectInputStream**, vì class resolution không luôn dùng loader có thể nhìn thấy application classes.

Khi dữ liệu được phép deserialize và có kiểm soát, Spring Framework cung cấp **ConfigurableObjectInputStream**:

~~~java
import java.io.InputStream;

import org.springframework.core.ConfigurableObjectInputStream;

try (InputStream input = /* trusted input */;
     ConfigurableObjectInputStream in =
             new ConfigurableObjectInputStream(
                     input,
                     Thread.currentThread().getContextClassLoader())) {

    Object obj = in.readObject();
}
~~~

Đây là **mảnh ví dụ**, không phải file chạy độc lập. Input thật, xử lý exception và loại dữ liệu phải được xác định theo hệ thống.

**Cảnh báo an toàn:** Java native deserialization dữ liệu không tin cậy có rủi ro nghiêm trọng. Việc đổi classloader cho ObjectInputStream **không làm deserialization an toàn** và không chống gadget attacks. Khi có thể, dùng định dạng/schema rõ ràng hoặc allowlist kiểm soát thay cho deserialize arbitrary objects.

Nếu lỗi đến từ third-party library không dùng TCCL khi deserialize, Spring Boot khuyến nghị liên hệ nhà phát triển thư viện. Không có một regex Devtools bảo đảm sửa tất cả trường hợp đó.

## 13. Lỗi chỉ xảy ra sau nhiều lần restart

Devtools thay restart classloader cũ bằng instance mới. Nhưng một object trong **base loader** hoặc một background thread sống lâu có thể giữ reference tới class, bean, proxy hoặc TCCL thuộc restart loader trước đó:

~~~text
Base classloader
    |
    +--> static cache / shared library singleton
                  |
                  +--> Class<?> hoặc object từ RestartLoader #1

RestartLoader #2 được tạo
    |
    +--> app dùng class mới cùng tên
                  |
                  +--> cast/proxy/metadata có thể không tương thích
~~~

Những nguyên nhân thường gặp:

- Static Map trong library base giữ key là application Class object.
- ThreadLocal/MDC trên thread pool không được cleanup.
- Executor, timer, scheduler hoặc listener không unregister khi context đóng.
- Third-party cache giữ Spring bean proxy từ ApplicationContext cũ.
- ClassLoader/TCCL bị giữ như một static reference.
- JDBC/messaging client không đóng đúng contract.

Hậu quả có thể gồm ClassCastException sau restart, tài nguyên/thread leak hoặc metaspace tăng. **Không kết luận mọi biến động metaspace là classloader leak**; cần xem classloader statistics, heap roots và actual references.

Biện pháp: ngừng background workers khi ApplicationContext đóng, xóa cache/listener registrations có lifecycle, dọn ThreadLocal đúng scope, đóng clients và tránh cache references từ restart loader trong base singleton.

Devtools dựa vào **ApplicationContext shutdown hook** để restart an toàn. Nếu code tắt shutdown hook bằng **SpringApplication.setRegisterShutdownHook(false)**, tài liệu cảnh báo restart không hoạt động đúng.

## 14. Khi chỉ thay source mà Devtools không restart

Devtools theo dõi **classpath resources**, không theo dõi bất kỳ file .java ở mọi vị trí.

- IntelliJ IDEA thường cần **Build > Build Project** hoặc cấu hình tự compile phù hợp.
- Eclipse có thể cập nhật output khi save nếu automatic build bật.
- Maven/Gradle cần compile để class files/resources đổi trên runtime classpath.
- Module shared đang đi vào app từ JAR **~/.m2/repository**: chỉ sửa source của shared không làm JAR cũ tự đổi.
- Compile nhiều modules theo đợt có thể khiến watcher restart giữa lúc output directory chưa đồng bộ.

Có thể điều chỉnh watcher trong môi trường chậm:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

Các số trên là ví dụ để thử nghiệm, không phải giá trị tối ưu cho mọi máy. Chúng điều chỉnh thời điểm polling và quiet period; không chuyển class vào loader khác.

Có thể dùng trigger file:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

File cần hiện diện trên classpath. Sửa trigger file khiến Devtools **kiểm tra** các classpath changes đã được phát hiện, không nhất thiết restart khi không có thay đổi đáng kể.

### Rebuild module shared đúng cách

~~~bash
mvn -pl app -am clean install -DskipTests
mvn -pl app dependency:tree
mvn -pl app spring-boot:run
~~~

Đây là lệnh cho project demo. Không tự xóa toàn bộ ~/.m2 hoặc đổi nhiều library versions khi chưa có bằng chứng; clean rebuild là một bước kiểm chứng artifact stale, không phải phép sửa vạn năng.

## 15. Phân biệt lỗi dependency với lỗi classloader

Một số ca phổ biến:

### Ca A: Same FQCN nằm trong hai JARs

Một shaded library vô tình đóng gói class của shared module và app cũng phụ thuộc JAR nguyên gốc. **getResources("example/contract/SharedMessage.class")** có thể trả nhiều URLs. Cần sửa dependency/shading/relocation và version alignment; không chỉ thêm restart.include.

### Ca B: NoSuchMethodError sau khi đổi shared DTO

Compile app dựa trên API mới nhưng runtime JAR shared cũ. So sánh CodeSource, dependency tree và method signature; rebuild/install module shared. Lỗi này có thể tồn tại khi Devtools hoàn toàn tắt.

### Ca C: ClassNotFoundException trong thư viện phản chiếu

Framework dùng base loader hoặc TCCL không nhìn thấy type ở restart. Xác minh type có trên runtime classpath trước; nếu có nhưng visibility sai, thử include module đúng.

### Ca D: Java serialization không đọc được class

ObjectInputStream resolve type theo loader không phù hợp. Xem giới hạn được Spring Boot công bố, kiểm tra TCCL và nguồn dữ liệu. Không deserialize untrusted bytes.

### Ca E: Code khác IDE và JAR

IDE chạy modules dạng target/classes, còn JAR executable có nested libraries và Devtools auto-disabled. Đây là **hai runtime classpaths khác nhau**; kiểm tra từng cấu hình, không suy ra chạy JAR là bằng chứng mọi classloader rule đều đúng.

## 16. Lưu ý về packaged application và production

Spring Boot Devtools thường **tự vô hiệu hóa** trong fully packaged application, đặc biệt khi chạy **java -jar**. Spring Boot Maven/Gradle repackaging cũng **không đóng Devtools vào executable archive theo mặc định** ở những cấu hình thông thường.

Có cách ép restart enabled bằng **-Dspring.devtools.restart.enabled=true**, nhưng **không thực hiện trong production**: tài liệu cảnh báo đưa Devtools vào production tạo rủi ro bảo mật. Bài học này giới hạn ở môi trường development/test.

Đối với runtime production:

- Không phát các endpoints debug classpath/loader cho người dùng công khai.
- Không lưu secrets vào logs classpath, heap dump hoặc stack trace được chia sẻ không kiểm soát.
- Không dựa vào Devtools để tự khởi động lại production Pods.
- Dùng quy trình deploy/restart, health probes và observability thích hợp.
- Kiểm tra duplicate dependencies và binary compatibility bằng build/release pipeline.

Spring Boot cũng lưu ý auto-restart **không được hỗ trợ với AspectJ weaving** theo tài liệu Devtools; một số ResourceLoader overrides cũng có giới hạn. Cần kiểm tra tình huống cụ thể thay vì cố dùng restart.include cho mọi vấn đề.

## 17. Runbook 12 bước cho một sự cố thật

1. **Tái hiện:** ghi Spring Boot/JDK version, IDE, Maven/Gradle task, module nào vừa sửa và số vòng restart.
2. **Lấy exception chain:** đọc root cause, FQCN, method/class signature và các loader names có trong message.
3. **In Class.getClassLoader():** cho expected type, actual type, annotation/proxy nếu có.
4. **In CodeSource:** xác định .class đến từ app/target/classes, module/target/classes hay JAR trong repository.
5. **Đọc TCCL:** ở đúng thread và call site gây lỗi.
6. **Xem resource duplicates:** ClassLoader.getResources() và dependency:tree.
7. **Tắt hẳn Devtools restart:** qua JVM System property trước SpringApplication.run.
8. **So sánh cùng launch mode:** lỗi có biến mất hay không, đừng đổi JVM/profile cùng lúc.
9. **Sửa gốc:** nếu artifact stale, rebuild module; nếu duplicate class, sửa dependency; nếu loader boundary, dùng META-INF/spring-devtools.properties.
10. **Restart sạch:** xác minh file devtools properties và artifacts mới đã xuất hiện trên runtime classpath.
11. **Đọc lại loader mapping và test lỗi thật:** không dùng kết quả thí nghiệm intentionally isolated loader để đánh giá.
12. **Regression:** thử IDE full reactor, Maven bootRun, sửa shared module rồi restart nhiều lần và packaged JAR không dùng Devtools.

### Bảng quyết định nhanh

| Tín hiệu | Bước kế tiếp |
| --- | --- |
| Disable restart thì hết lỗi | Soi base/restart boundary và include/exclude |
| Disable restart vẫn lỗi | Dependency tree, binary API, missing artifacts |
| Shared JAR cũ từ Maven repository | Build/install đúng module và restart app |
| Hai URLs của cùng class | Duplicate classes/shading/version conflict |
| Annotation class được base load sai boundary | Kiểm tra reflective loader và include module liên quan |
| ObjectInputStream lỗi resolve app type | Xem TCCL/ConfigurableObjectInputStream |
| Chỉ lỗi sau nhiều lần restart | Cleanup threads, caches, references từ generation cũ |
| Không thấy restart sau sửa code | Kiểm tra compiled classpath output/watcher |
| Only packaged JAR works | So sánh runtime classpaths/Devtools enablement |

## 18. Câu hỏi và bài tập

**Câu 1.** Hai class có binary name giống nhau nhưng defining ClassLoader khác nhau có phải một Java type không?

**Câu 2.** Vì sao Devtools có base loader và restart loader? Những classpath entries nào thường vào mỗi loader?

**Câu 3.** Cách tắt **hoàn toàn** restart để cô lập lỗi khác gì đặt spring.devtools.restart.enabled=false trong application.properties?

**Câu 4.** Tại sao lỗi Foo cannot be cast to Foo không thực sự vô lý?

**Câu 5.** Khi cùng một module đi vào runtime dưới dạng JAR so với target/classes, classloader placement có thể khác thế nào?

**Câu 6.** File và property nào dùng để kéo shared module JAR vào restart classloader?

**Câu 7.** Regex của restart.include được match với package name hay classpath path?

**Câu 8.** spring.devtools.restart.exclude và restart.exclude.some-library khác nhau ở đâu?

**Câu 9.** Tại sao SAME_BINARY_NAME=true, SAME_CLASS_IDENTITY=false và ISOLATED_CAST_FAILED=true trong demo không phải bug Devtools?

**Câu 10.** Dùng Maven app spring-boot:run nhưng vừa sửa shared-contract. Vì sao có thể vẫn thấy version cũ?

**Câu 11.** Khi ServiceLoader không thấy provider, ngoài TCCL còn cần kiểm tra gì?

**Câu 12.** ConfigurableObjectInputStream có làm cho Java native deserialization của input không tin cậy trở thành an toàn không?

**Câu 13.** Một static cache ở base loader giữ Class<?> từ restart loader cũ. Rủi ro là gì?

**Câu 14.** Chạy java -jar thành công có đủ xác nhận Devtools classloader mapping đúng không?

### Đáp án gợi ý

1. Không, type identity phụ thuộc binary name và defining loader.
2. Để tái sử dụng third-party classes và restart nhanh; JAR thường base, open projects/classes directories thường restart.
3. JVM System property đặt trước run loại hỗ trợ restart, còn application property có thể chỉ ngừng watcher.
4. Hai types cùng tên có thể được các loaders khác nhau định nghĩa.
5. JAR thường vào base, source directory của open project thường vào restart.
6. META-INF/spring-devtools.properties với restart.include.<uniqueName>.
7. Classpath entry path.
8. Một bên chỉnh watcher/resource restart trigger, một bên chỉnh classloader selection.
9. URLClassLoader độc lập cố ý tạo một defining loader khác.
10. JAR trong ~/.m2 có thể chưa được rebuild/install.
11. Service interface identity, META-INF/services và dependency/classpath.
12. Không; vẫn cần bảo mật deserialization và tránh untrusted data.
13. Classloader/metaspace leak hoặc type mismatch giữa generations.
14. Không; packaged JAR có hình dạng classpath khác và Devtools thường disabled.

## 19. Checklist trước khi kết luận

- [ ] Đã lấy đúng Bài/Java/Boot/IDE/Maven versions đang gây lỗi?
- [ ] Đã ghi actual classloader, expected classloader và CodeSource?
- [ ] Đã đọc TCCL trên đúng thread?
- [ ] Đã kiểm tra classpath resources có trùng class không?
- [ ] Đã kiểm tra JAR/module version bằng dependency:tree?
- [ ] Đã thử tắt restart hoàn toàn bằng JVM property?
- [ ] Đã phân biệt lỗi Devtools boundary với stale JAR/missing dependency?
- [ ] Đã xác định regex áp lên đúng classpath entry?
- [ ] File META-INF/spring-devtools.properties ở đúng resource path?
- [ ] Đã phân biệt restart.include/exclude và spring.devtools.restart.exclude?
- [ ] Đã rebuild module shared và kiểm tra classpath thật?
- [ ] Đã quan sát restart generation sau compile?
- [ ] Đã xem TCCL, reflection, annotation và ServiceLoader khi liên quan?
- [ ] Đã rà soát serialization security?
- [ ] Đã dọn background threads/static caches sau restart?
- [ ] Không bật Devtools restart trong production?
- [ ] Đã kiểm tra lỗi gốc biến mất, không chỉ là thay đổi thông điệp log?
- [ ] Đã lưu regression test và giải thích vì sao phải include/exclude module?

## 20. Kết luận và tài liệu chính thức

Khi Devtools gặp lỗi classloader trong dự án nhiều module, không nên giải quyết bằng cách chỉ tắt restart, xóa toàn bộ Maven cache hoặc tăng watcher timeout. Hãy đi theo chuỗi bằng chứng:

~~~text
Stack trace và FQCN
        |
        v
ClassLoader + CodeSource + TCCL
        |
        v
Kiểm tra output directory / JAR / duplicates
        |
        v
Thử -Dspring.devtools.restart.enabled=false
        |
        +--> Lỗi vẫn còn: kiểm tra artifact/dependency/API
        |
        +--> Lỗi biến mất: kiểm tra base/restart boundary
                          |
                          v
         META-INF/spring-devtools.properties
         restart.include / restart.exclude
                          |
                          v
                 Rebuild, restart, readback
                 và kiểm tra lỗi thật
~~~

**Tài liệu chính thức:**

1. Spring Boot 3.5 Developer Tools — Diagnosing Classloading Issues, Customizing Restart Classloader, Restart vs Reload, Known Limitations: https://docs.spring.io/spring-boot/3.5/reference/using/devtools.html
2. Spring Boot Maven Plugin 3.5 — Running your application: https://docs.spring.io/spring-boot/3.5/maven-plugin/run.html
3. Java 17 Class API — getClassLoader, getProtectionDomain: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
4. Java 17 URLClassLoader API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
5. Java 17 ServiceLoader API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
6. Spring Framework 6.2 ConfigurableObjectInputStream: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/ConfigurableObjectInputStream.html

Ví dụ dùng **Java 17+**, **Spring Boot 3.5.16**, **Maven multi-module** và Devtools chỉ cho development. Kết quả loader/hashcode/path không giống nhau giữa IDE, Gradle, Maven và packaged JAR; phải kiểm chứng trên classpath của chính môi trường đang gặp sự cố.