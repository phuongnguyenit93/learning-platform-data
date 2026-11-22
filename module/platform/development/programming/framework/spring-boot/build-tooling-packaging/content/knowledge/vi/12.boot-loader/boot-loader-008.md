# Phân biệt archive lồng của Spring Boot với JAR gộp bằng Maven Shade hoặc Gradle Shadow

## 1. Mục tiêu và phạm vi

Khi đóng gói ứng dụng Java thành **một file có thể chạy bằng `java -jar`**, bạn có thể gặp những tên gọi `executable JAR`, `fat JAR`, `uber JAR`, `shaded JAR` và **Spring Boot executable JAR**. Các khái niệm này **không hoàn toàn đồng nghĩa**.

- **Spring Boot executable JAR theo layout mặc định:** giữ phần lớn dependency ở dạng **các file JAR lồng bên trong JAR chính**, thường tại `BOOT-INF/lib/`. Spring Boot Loader tạo classloader đọc được nested dependencies đó.
- **Maven Shade Plugin / Gradle Shadow Plugin:** thường **mở các dependency JAR**, trộn file `.class` và resources vào **cùng không gian thư mục của một JAR gộp** (uber/shaded JAR). Việc gộp có thể kèm merge resources, đổi package (relocation) và các bước xử lý trùng lặp.

Cả hai có thể cho ra **một file duy nhất để phát hành**, nhưng **layout, classloading, manifest, khả năng phân tích dependencies và rủi ro xung đột tài nguyên khác nhau**.

Sau bài này, bạn có thể:

1. Nhận diện chính xác kiểu archive từ `jar tf` và `META-INF/MANIFEST.MF`.
2. Giải thích `BOOT-INF/classes`, `BOOT-INF/lib`, `JarLauncher` và `Start-Class` của Spring Boot.
3. Phân biệt cơ chế Boot Loader với cách gộp bytecode của Shade/Shadow.
4. Tạo một **Spring Boot nested JAR**, một **Maven shaded JAR** và một **Gradle shadow JAR** bằng những ví dụ tách biệt, có lệnh chạy và output có thể kiểm chứng.
5. Hiểu `META-INF/services`, Spring auto-configuration metadata, resource collisions, relocation, signature files và tác động của minimization.
6. Biết khi nào ưu tiên Boot `bootJar`/`repackage` và khi nào dùng Shade hoặc Shadow cho CLI tool/library.
7. Tránh lỗi kết hợp Boot repackage với shade vào cùng artifact hoặc nhầm “một JAR” với “một cấu trúc bên trong giống nhau”.

**Phiên bản minh họa:** Java 17+, Spring Boot `3.5.16`, Apache Commons Lang `3.17.0`, Maven Shade `3.6.2`, Shadow `9.3.0`. Đây là **tọa độ cụ thể để minh họa và tái tạo ví dụ**, không phải yêu cầu tất cả dự án phải nâng lên những version đó. Shadow `9.3.0` cần ít nhất **Gradle 9.0** và Java 17 theo compatibility matrix của GradleUp. Kiểm tra phiên bản được project/CI hỗ trợ trước khi sao chép cấu hình.

## 2. “Fat JAR” mô tả khả năng phân phối, không mô tả duy nhất một layout

Nhiều nhóm gọi cả Boot executable JAR và shaded JAR là **fat JAR** vì chúng đều mang theo những dependencies cần chạy. Cách phân biệt chính xác hơn là **nhìn cấu trúc bên trong**.

### 2.1. JAR thư viện/thông thường (thin JAR)

~~~text
plain-app.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/app/
    └── App.class
~~~

Một JAR thông thường thường chỉ chứa classes/resources của project. Dependency bên ngoài **không tự được nhúng** chỉ vì có trong `pom.xml` hay `build.gradle`. Khi muốn chạy, cần có đúng classpath hoặc một cơ chế phân phối dependencies. Có `Main-Class` cũng không biến nó thành self-contained archive nếu các thư viện cần thiết chưa có trên classpath.

### 2.2. Spring Boot nested executable JAR

~~~text
nested-boot-0.0.1-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   └── com/example/archives/NestedBootApplication.class
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-context-*.jar
    │   ├── commons-lang3-3.17.0.jar
    │   └── ...
    ├── classpath.idx                  # có thể có
    └── layers.idx                     # có thể có
~~~

Các file `BOOT-INF/lib/*.jar` vẫn là **JAR riêng biệt** được đặt như entries của outer ZIP/JAR. Class của Commons Lang không xuất hiện trực tiếp ở đường dẫn root `org/apache/commons/lang3/StringUtils.class` trong **outer JAR**; nó nằm **bên trong** entry `commons-lang3-3.17.0.jar`.

Spring Boot Loader là chương trình khởi động đặc biệt dùng classloader phù hợp để tìm app classes trong `BOOT-INF/classes` và dependency classes trong nested JARs. JVM chuẩn **không tự thêm nested JARs vào classpath** nếu chỉ nhận một `-cp outer.jar` thông thường.

### 2.3. Maven shaded hoặc Gradle shadow JAR

~~~text
flat-app-1.0.0-all.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── services/...
├── com/example/archives/
│   └── App.class
├── org/apache/commons/lang3/
│   └── StringUtils.class
└── ... nhiều classes/resources được gộp ...
~~~

Ở đây dependency classes được **giải nén và đưa vào không gian classpath root của cùng một JAR**. Không cần Spring Boot Loader để tìm `org.apache.commons.lang3.StringUtils` vì class file đã hiện diện như một entry bình thường. Nếu archive manifest có `Main-Class: com.example.archives.App` và đủ dependencies, JVM launcher thông thường có thể chạy bằng `java -jar`.

**Nhấn mạnh:** việc gộp **không tự giải quyết** các file trùng tên, cấu hình SPI, reflection hoặc version incompatibility. Shade và Shadow cung cấp công cụ xử lý những tình huống này, nhưng trách nhiệm cấu hình vẫn thuộc dự án.

## 3. Bảng so sánh kỹ thuật

| Khía cạnh | Spring Boot nested executable JAR | Maven Shade / Gradle Shadow |
| --- | --- | --- |
| Cách lưu dependencies | Từng JAR riêng ở `BOOT-INF/lib/` | Classes/resources từ dependencies thường được gộp vào JAR chính |
| App classes | `BOOT-INF/classes/` | Root package path như `com/example/...` |
| Main-Class thường gặp | `org.springframework.boot.loader.launch.JarLauncher` | Class `main` của ứng dụng |
| Start-Class | Ghi tên application main class trong manifest | Không cần convention `Start-Class` của Boot Loader |
| Classloader | Spring Boot Loader hỗ trợ nested JARs | Java classpath/JAR loading thông thường cho file gộp |
| Khả năng nhìn từng dependency JAR | Tên và boundary JAR khá rõ | Ranh giới JAR gốc bị gộp, khó phân biệt chỉ bằng `jar tf` |
| Trùng resource cùng path | Giữ các files trong những JAR riêng, classloader có thể tìm resources | Phải chọn/merge/transform để tránh mất dữ liệu |
| Relocation package | Không phải mục tiêu chính của `repackage` | Shade/Shadow hỗ trợ relocation theo cấu hình |
| `META-INF/services` | Giữ descriptors ở JARs tương ứng | Thường cần merge services descriptors |
| Tối ưu layer cho container | Có `layers.idx` và tooling Boot phù hợp | Không có `layers.idx` Boot một cách tự động |
| Dùng làm library dependency | Executable JAR không phù hợp để dùng trực tiếp như thin library | Shaded library có thể dùng, nhưng relocation/API cần kiểm soát |
| Build Maven | Spring Boot Maven Plugin `repackage` | Maven Shade Plugin `shade` |
| Build Gradle | Spring Boot Gradle Plugin `bootJar` | GradleUp Shadow Plugin `shadowJar` |

Cả hai kiểu có thể bị lỗi nếu thiếu dependencies hoặc có version conflicts. Bảng nói về **cấu trúc và hành vi đóng gói**, không hứa một cơ chế luôn nhỏ hơn, nhanh hơn, bảo mật hơn hay dễ deploy hơn trong mọi project.

## 4. Spring Boot Loader thực sự làm gì?

### 4.1. Java launcher chỉ đọc Main-Class bên ngoài

Khi chạy:

~~~bash
java -jar nested-boot-0.0.1-SNAPSHOT.jar
~~~

Java launcher đọc `META-INF/MANIFEST.MF` của outer JAR để lấy `Main-Class`. Với Boot executable JAR kiểu `JAR` ở dòng 3.5, manifest tiêu biểu là:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.archives.NestedBootApplication
Spring-Boot-Version: 3.5.16
~~~

Đây là **minh họa các manifest attributes có liên quan**, không phải bảo đảm toàn bộ manifest thực tế chỉ có bốn dòng. Spring Boot Maven/Gradle plugin có thể bổ sung metadata khác.

Luồng thực thi:

~~~text
java -jar app.jar
    |
    v
MANIFEST.MF : Main-Class = JarLauncher
    |
    v
Boot Loader định vị BOOT-INF/classes và BOOT-INF/lib/*.jar
    |
    v
Tạo classloader thích hợp cho nested JAR entries
    |
    v
MANIFEST.MF : Start-Class = application main
    |
    v
com.example.archives.NestedBootApplication.main(args)
    |
    v
SpringApplication.run(...)
~~~

Spring Boot có `WarLauncher` cho executable WAR, `PropertiesLauncher` trong những layout phù hợp và các cơ chế loader khác theo version. **Tên package của launcher thay đổi giữa các dòng Boot cũ và mới**; ví dụ `org.springframework.boot.loader.launch.JarLauncher` là của Boot 3.5, không sao chép từ hướng dẫn Boot 2.x vào manifest của 3.x mà không đối chiếu.

### 4.2. Vì sao JVM bình thường không tự load JAR bên trong JAR?

Một `JAR` về bản chất dùng định dạng ZIP. Java classpath chuẩn biết tìm class từ directory hoặc JAR được đặt trên classpath, nhưng **không định nghĩa cơ chế tự duyệt toàn bộ JAR trong JAR rồi thêm mỗi cái vào classpath**. Boot Loader triển khai cơ chế đọc nested archive, xây dựng loader/classpath và gọi application entrypoint.

Vì vậy:

~~~bash
# Đúng cho executable Boot JAR theo manifest:
java -jar nested-boot-0.0.1-SNAPSHOT.jar
~~~

không tương đương với:

~~~bash
# Không nên giả định JVM chuẩn tự hiểu BOOT-INF/lib/ khi chạy -cp:
java -cp nested-boot-0.0.1-SNAPSHOT.jar \
  com.example.archives.NestedBootApplication
~~~

Lệnh thứ hai sẽ không tự tìm `BOOT-INF/classes` và nested dependency JARs theo layout mặc định. Nó có thể báo `ClassNotFoundException` hoặc thiếu dependencies.

### 4.3. Nested JAR entry và phương thức nén

Theo đặc tả executable JAR của Boot, nested JAR entry trong outer archive phải được ghi với ZIP method **`STORED`** (không nén thêm outer entry). Điều này cho phép Boot Loader định vị/seek nội dung bên trong nested archive trực tiếp. **Bên trong nested dependency JAR**, các entries vẫn có thể đã được nén bình thường; `STORED` chỉ nói về **entry đại diện cho cả nested JAR** trong outer archive.

Nếu tự mở rồi zip lại executable Boot JAR bằng tool không giữ đúng phương thức lưu nested entries, archive có thể **không chạy được**, dù `jar tf` vẫn liệt kê được. Đừng thay bước đóng gói chuẩn của Boot Maven/Gradle plugin bằng một script ZIP thủ công thiếu kiểm chứng.

### 4.4. Classloader và thư viện bên thứ ba

Ứng dụng chạy dưới Boot Loader thường cần các thư viện lấy resources/classes bằng **thread context classloader** khi thích hợp. Một số thư viện dùng `ClassLoader.getSystemClassLoader()` hoặc giả định mỗi dependency là một file path riêng trực tiếp trên disk có thể không hoạt động như lúc chạy từ IDE.

Không kết luận thư viện nào lỗi chỉ từ tên API: hãy chạy integration test bằng chính executable JAR. Một số thư viện đòi unpack, và Spring Boot Maven Plugin hỗ trợ `requiresUnpack` cho các trường hợp phù hợp; đừng tự extract toàn bộ dependencies như cách “sửa” mặc định.

## 5. Ví dụ A — tạo Spring Boot nested executable JAR

Đây là một project **độc lập** để thấy rõ layout Boot Loader. Project **không cần web server**, chỉ in một dòng khi khởi động thành công. Ví dụ dùng Commons Lang để người học thấy một dependency JAR được giữ nguyên ở `BOOT-INF/lib`.

### 5.1. Cấu trúc thư mục

~~~text
nested-boot/
├── pom.xml
└── src/main/java/com/example/archives/
    └── NestedBootApplication.java
~~~

Nếu tạo từ Spring Initializr, có thêm `mvnw`, `mvnw.cmd` và `.mvn/wrapper/`. Nếu tự tạo chỉ hai file ở trên, dùng Maven cài sẵn với lệnh `mvn`.

### 5.2. pom.xml hoàn chỉnh

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
    <artifactId>nested-boot</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
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

Spring Boot starter parent ở ví dụ này đã cấu hình execution `repackage`. Vì vậy Maven `package` tạo JAR executable có Boot Loader; bạn **không cần thêm Maven Shade Plugin**. Nếu project thực tế có corporate parent riêng, BOM import không tự kế thừa plugin management/execution này; cần khai báo `spring-boot-maven-plugin` + version + goal `repackage` đúng.

### 5.3. Java 17+ source

Tạo `src/main/java/com/example/archives/NestedBootApplication.java`:

~~~java
package com.example.archives;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NestedBootApplication {

    public static void main(String[] args) {
        SpringApplication.run(NestedBootApplication.class, args);
    }

    @Bean
    ApplicationRunner showArchiveType() {
        return args -> System.out.println(
                "BOOT_OK " + StringUtils.capitalize("hello"));
    }
}
~~~

Đây là Java source hoàn chỉnh của ứng dụng Spring Boot. `@Bean ApplicationRunner` chạy sau khi context đã khởi tạo. `StringUtils.capitalize("hello")` trả chuỗi `Hello`, do đó dòng **do code ứng dụng tự in** có thể kiểm chứng chính xác là:

~~~text
BOOT_OK Hello
~~~

Spring Boot còn có startup logs (thời gian, logger, environment tùy máy), vì vậy **không khẳng định toàn bộ stdout** chỉ chứa một dòng này.

### 5.4. Build và chạy

Từ directory chứa `pom.xml`:

~~~bash
java -version
mvn -version
mvn clean package
java -jar target/nested-boot-0.0.1-SNAPSHOT.jar
~~~

Nếu project có Maven Wrapper:

~~~bash
./mvnw clean package
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd clean package
java -jar .\target\nested-boot-0.0.1-SNAPSHOT.jar
~~~

Lệnh Wrapper chỉ dùng nếu file `mvnw`/`mvnw.cmd` **thực sự có trong project**. Build cần JDK 17+ tương thích với Spring Boot và mạng/repository khi dependencies chưa được cache.

### 5.5. Kiểm chứng archive

~~~bash
jar tf target/nested-boot-0.0.1-SNAPSHOT.jar
~~~

Tìm các entries đại diện:

~~~text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/archives/NestedBootApplication.class
BOOT-INF/lib/commons-lang3-3.17.0.jar
BOOT-INF/lib/spring-boot-*.jar
~~~

Dấu `*` ở dòng cuối là **minh họa một nhóm tên JAR có version khác nhau**, không phải một đường dẫn literal được bảo đảm trong `jar tf`.

Đừng kỳ vọng outer `jar tf` hiển thị:

~~~text
org/apache/commons/lang3/StringUtils.class
~~~

vì class đó nằm **bên trong** `BOOT-INF/lib/commons-lang3-3.17.0.jar`, không ở root của outer archive.

Đọc manifest trên Linux/macOS nếu có `unzip`:

~~~bash
unzip -p target/nested-boot-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
~~~

Kết quả cần chú ý là `Main-Class: org.springframework.boot.loader.launch.JarLauncher` và `Start-Class: com.example.archives.NestedBootApplication`. Trên Windows không có `unzip` sẵn, có thể mở JAR như ZIP bằng một công cụ archive rồi xem `META-INF/MANIFEST.MF` ở chế độ chỉ đọc; không cần tự repack archive.

## 6. Maven Shade: trộn classes và resources vào một uber JAR

### 6.1. Maven Shade Plugin làm gì?

`maven-shade-plugin` có goal `shade`; thông thường nó lấy classes/resources của project và runtime dependencies đã resolve, **giải nén và trộn** vào JAR kết quả. Các tính năng đáng chú ý:

- `ManifestResourceTransformer` để đặt `Main-Class` (có thể đặt manifest entries khác).
- `ServicesResourceTransformer` để merge `META-INF/services/*` và cập nhật tên provider khi relocation phù hợp.
- `relocations` để chuyển package class names nhằm tránh xung đột classpath.
- `filters` để chỉ định include/exclude resource/metadata, ví dụ chữ ký không còn hợp lệ sau khi gộp.
- `shadedArtifactAttached` và `shadedClassifierName` để giữ artifact thường và xuất thêm bản shaded có classifier riêng.

**Shade không phải Spring Boot Loader.** Trong ví dụ tiếp theo, chúng ta cố ý dùng một **Java CLI project thuần** để chứng minh shaded JAR có thể tự chạy bằng JVM thông thường, không cần cơ chế tìm nested dependencies.

### 6.2. Cấu trúc project Shade tách biệt

~~~text
flat-maven/
├── pom.xml
└── src/main/java/com/example/archives/
    └── App.java
~~~

Tệp `App.java`:

~~~java
package com.example.archives;

import org.apache.commons.lang3.StringUtils;

public final class App {

    private App() {}

    public static void main(String[] args) {
        System.out.println(
                "FLAT_OK " + StringUtils.capitalize("hello"));
    }
}
~~~

Đây là Java 17+ source hoàn chỉnh. Nếu chạy thành công với Commons Lang trên classpath, stdout **chính xác** là:

~~~text
FLAT_OK Hello
~~~

### 6.3. pom.xml hoàn chỉnh cho Maven Shade

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>flat-maven</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <shadedArtifactAttached>true</shadedArtifactAttached>
                            <shadedClassifierName>all</shadedClassifierName>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>com.example.archives.App</mainClass>
                                </transformer>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- `maven-compiler-plugin` đặt compiler theo Java 17.
- `shade` chạy tại phase `package` sau khi Maven Jar Plugin tạo JAR project theo lifecycle thường.
- `shadedArtifactAttached=true` và classifier `all` tạo **artifact shaded riêng**, thường là `target/flat-maven-1.0.0-all.jar`. Bản thường `target/flat-maven-1.0.0.jar` vẫn tồn tại và **không tự có Commons Lang bên trong**.
- `createDependencyReducedPom=false` tắt việc tạo `dependency-reduced-pom.xml` trong ví dụ ứng dụng đơn giản. Với thư viện được publish, lựa chọn này có hậu quả đối với dependency metadata/POM và cần thiết kế riêng.
- `ManifestResourceTransformer` đặt `Main-Class: com.example.archives.App` để JVM chạy trực tiếp.
- `ServicesResourceTransformer` xử lý các Java SPI service descriptors trùng đường dẫn. Ví dụ chỉ dùng Commons Lang nên không phụ thuộc vào transformer này để in stdout; thêm nó để giới thiệu best practice khi xây ứng dụng nhiều dependencies.

**Đừng thêm `spring-boot-maven-plugin` vào project Shade này** chỉ để có `java -jar`. Maven Shade đã tạo executable manifest. Nếu bạn đang xây ứng dụng Spring Boot thực sự, mặc định dùng Boot plugin với nested layout sẽ ít nguy cơ phá resource/auto-configuration hơn.

### 6.4. Build, chạy và kiểm tra

~~~bash
mvn clean package
java -jar target/flat-maven-1.0.0-all.jar
jar tf target/flat-maven-1.0.0-all.jar
~~~

Trong JAR shaded, tìm:

~~~text
META-INF/MANIFEST.MF
com/example/archives/App.class
org/apache/commons/lang3/StringUtils.class
~~~

Với cấu hình ví dụ, **không cần** và thông thường **không có** `BOOT-INF/lib/commons-lang3-3.17.0.jar` hoặc Boot `JarLauncher`. Đọc manifest:

~~~bash
unzip -p target/flat-maven-1.0.0-all.jar META-INF/MANIFEST.MF
~~~

Giá trị quan trọng:

~~~text
Main-Class: com.example.archives.App
~~~

Output chương trình:

~~~text
FLAT_OK Hello
~~~

**Không chạy nhầm bản thin JAR** `target/flat-maven-1.0.0.jar` và quy lỗi sang Shade: đó là output khác. Thin JAR có thể không có `Main-Class`, hoặc khi được cấu hình manifest thì vẫn thiếu dependency ở runtime nếu không có classpath ngoài.

## 7. Gradle Shadow: nguyên lý tương tự Maven Shade

### 7.1. GradleUp Shadow tạo uber JAR

Gradle Shadow (hiện được duy trì dưới plugin ID `com.gradleup.shadow`) tạo task `shadowJar` khi áp dụng cùng Java/Kotlin JVM/Groovy plugin tương ứng. Mặc định `shadowJar` gộp project classes/resources với `runtimeClasspath` dependencies và dùng classifier `all`, không phải nested JAR format của Spring Boot.

Tên plugin cũ `com.github.johnrengelman.shadow` có thể tồn tại trong repo lâu năm. Với project mới, dùng plugin ID `com.gradleup.shadow` phù hợp phiên bản Gradle/Java mà dự án hỗ trợ.

Ví dụ sau sử dụng cùng `App.java` như Maven Shade tại mục 6; chỉ thay build tool. **Không đặt Maven POM và Gradle build vào cùng bài thực hành rồi chạy cả hai trong một project** nếu chưa hiểu nguồn dependencies/artifact nào là chính.

### 7.2. Cấu trúc project Gradle riêng

~~~text
flat-gradle/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/archives/
    └── App.java
~~~

Nội dung `settings.gradle`:

~~~groovy
rootProject.name = 'flat-gradle'
~~~

Tạo `App.java` giống mục 6.2:

~~~java
package com.example.archives;

import org.apache.commons.lang3.StringUtils;

public final class App {

    private App() {}

    public static void main(String[] args) {
        System.out.println(
                "FLAT_OK " + StringUtils.capitalize("hello"));
    }
}
~~~

### 7.3. build.gradle hoàn chỉnh — Groovy DSL

~~~groovy
plugins {
    id 'java'
    id 'com.gradleup.shadow' version '9.3.0'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('shadowJar') {
    archiveBaseName.set('flat-gradle')
    archiveClassifier.set('all')
    manifest {
        attributes 'Main-Class': 'com.example.archives.App'
    }
}
~~~

Giải thích:

- `java` plugin cung cấp `compileJava`, `jar`, `test` và những cơ chế Java project thông thường.
- `com.gradleup.shadow` tạo `shadowJar`, mặc định trộn dependencies từ `runtimeClasspath`.
- `toolchain Java 17` chọn compiler tương thích nếu JDK/toolchain có sẵn/được cấu hình provision.
- `archiveClassifier='all'` giúp phân biệt shaded artifact với thin `jar`.
- `manifest Main-Class` gọi trực tiếp `App.main` qua launcher tiêu chuẩn, **không cần Boot JarLauncher**.

Với Shadow `9.3.0`, dùng **Gradle 9.0+** và Java 17+ để chạy Gradle plugin. Đừng copy version này vào dự án đang khóa Gradle 8.x; thay bằng phiên bản Shadow tương thích theo compatibility matrix chính thức. **Đừng suy luận** rằng cài JDK 17 đủ để chạy mọi Gradle version: kiểm tra cả `gradle -version`.

### 7.4. Build và chạy trên các hệ điều hành

Với Gradle đã cài:

~~~bash
gradle shadowJar
java -jar build/libs/flat-gradle-1.0.0-all.jar
jar tf build/libs/flat-gradle-1.0.0-all.jar
~~~

Nếu project có Gradle Wrapper đã sinh từ `gradle wrapper`:

~~~bash
./gradlew shadowJar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat shadowJar
java -jar .\build\libs\flat-gradle-1.0.0-all.jar
~~~

Cũng như Maven Shade, stdout kỳ vọng là:

~~~text
FLAT_OK Hello
~~~

Và các entries đại diện gồm:

~~~text
com/example/archives/App.class
org/apache/commons/lang3/StringUtils.class
META-INF/MANIFEST.MF
~~~

`BOOT-INF/lib/commons-lang3-3.17.0.jar` **không phải** cách Shadow thông thường gói dependency trong output này. Nếu bạn thấy JAR lồng nguyên vẹn trong output, xem lại task inputs và các thao tác `from(...)`/`zipTree(...)` tùy chỉnh.

### 7.5. Gradle bootJar khác shadowJar

Trong một **Spring Boot Gradle project**, Boot plugin dùng task `bootJar` tạo nested executable Boot archive. Trong một **Java + Shadow project** như ví dụ, task `shadowJar` tạo JAR gộp.

Khi cùng áp dụng Boot Gradle plugin và Shadow, các task có thể cùng tồn tại, nhưng **output không nên tùy tiện ghi vào cùng đường dẫn**. Cần định nghĩa rõ:

- Task nào là artifact chính để deploy.
- Archive name/classifier của `bootJar` và `shadowJar`.
- Task nào được CI/CD gọi và artifact nào được publish.
- Test nào chạy qua chính artifact sản phẩm.

Không dùng `zipTree(bootJar.archiveFile)` rồi gộp thêm dependencies để “biến Boot JAR thành shaded JAR” theo bản năng: Boot JAR đã có `BOOT-INF` và loader layout riêng; bạn có thể tạo ra archive có hai cơ chế classpath chồng chéo hoặc manifest sai.

## 8. Vấn đề lớn của JAR gộp: các resources trùng tên

### 8.1. Vì sao classes merge chưa đủ?

Nhiều Java libraries có **cùng tên resource file**:

~~~text
library-a.jar: META-INF/services/com.example.spi.Plugin
library-b.jar: META-INF/services/com.example.spi.Plugin
~~~

Mỗi file liệt kê một hoặc nhiều implementation của cùng Java SPI. Khi shade, nếu bạn chỉ giữ file đầu tiên (hoặc file sau cùng) tại đường dẫn trùng, `ServiceLoader` sẽ **mất một số provider**. Khi nested JARs được giữ riêng, classloader có thể đọc resource descriptors từ các dependency riêng để tổng hợp providers theo quy tắc chuẩn.

Tương tự, Spring Framework/Spring Boot có nhiều resources đặc biệt trong `META-INF/`. Cơ chế gộp phải hiểu **định dạng và semantics** của từng resource, không thể chỉ chọn file đầu tiên tùy tiện.

### 8.2. Maven Shade: ServicesResourceTransformer

Đoạn trong `maven-shade-plugin`:

~~~xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
        <mainClass>com.example.archives.App</mainClass>
    </transformer>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
~~~

`ServicesResourceTransformer` merge các file `META-INF/services/*` và cập nhật provider class names liên quan nếu dùng relocation phù hợp. **Nó không tự merge mọi loại cấu hình**, ví dụ file JSON, properties hay Spring auto-configuration imports. Có các transformer khác (như `AppendingTransformer`), nhưng dùng sai định dạng có thể làm metadata không hợp lệ.

### 8.3. Gradle Shadow: mergeServiceFiles và duplicate strategy

Với Shadow `9.x`, phải chú ý **`duplicatesStrategy`**: nếu đặt `EXCLUDE` quá sớm, những service descriptor trùng path có thể bị loại **trước khi transformer được gọi**, khiến `mergeServiceFiles()` không nhìn thấy đủ input.

Khi cần merge các service descriptors, có thể cấu hình `build.gradle` (đoạn nằm trong Java + Shadow project):

~~~groovy
tasks.named('shadowJar') {
    duplicatesStrategy = DuplicatesStrategy.INCLUDE
    mergeServiceFiles()

    filesNotMatching('META-INF/services/**') {
        duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    }
}
~~~

Ý tưởng: **giữ mọi descriptor trùng path để transformer xử lý**, nhưng không vô ý mang mọi resource trùng khác vào output. Với project phức tạp, cần audit các collisions khác, đặc biệt license/notice, properties, Spring metadata và file signatures. Không dùng `INCLUDE` cho tất cả mà bỏ qua warning/duplicate entries.

Trong Shadow `9.x`, cơ chế duplicate strategy có những thay đổi giữa minor versions; luôn đối chiếu tài liệu đúng version, xem build logs và có thể bật `failOnDuplicateEntries` khi đã thống nhất chiến lược xử lý tài nguyên.

### 8.4. Spring Boot auto-configuration metadata

Spring Boot 3.x dùng resource dạng:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

để liệt kê các lớp auto-configuration từ dependencies. Ngoài ra hệ sinh thái Spring có thể dùng `META-INF/spring.factories`, `META-INF/spring.handlers`, `META-INF/spring.schemas` và những metadata khác.

Khi Shade/Shadow gộp một ứng dụng Boot mà thiếu merge strategy phù hợp, **một số auto-configurations hoặc factories có thể biến mất**, dẫn đến ứng dụng khởi động nhưng thiếu beans, thiếu converters, hoặc lỗi bất ngờ ở runtime.

**`mergeServiceFiles()` chỉ xử lý `META-INF/services`**, không tự biến tất cả Spring resources thành file hợp lệ. Nếu buộc dùng shaded Spring Boot app, hãy thiết kế transformers theo từng resource format, test full startup/critical flows và kiểm tra artifact cuối. Với Spring Boot app thông thường, **Boot nested packaging là lựa chọn mặc định an toàn hơn**, vì giữ boundaries của dependencies và metadata theo cách mà Boot runtime mong đợi.

### 8.5. META-INF/MANIFEST.MF và chữ ký JAR

Một dependency JAR có thể chứa files chữ ký như:

~~~text
META-INF/SOMELIB.SF
META-INF/SOMELIB.RSA
META-INF/SOMELIB.DSA
~~~

Khi Shade/Shadow giải nén và sửa nội dung archive, chữ ký của dependency gốc **không còn đại diện cho bytes của JAR gộp**. Giữ nguyên signatures có thể gây lỗi `SecurityException: Invalid signature file digest for Manifest main attributes` ở runtime.

Maven Shade có thể loại những signature files không hợp lệ bằng `filters`, ví dụ đoạn đặt trong `<configuration>` của plugin:

~~~xml
<filters>
    <filter>
        <artifact>*:*</artifact>
        <excludes>
            <exclude>META-INF/*.SF</exclude>
            <exclude>META-INF/*.DSA</exclude>
            <exclude>META-INF/*.RSA</exclude>
        </excludes>
    </filter>
</filters>
~~~

Đây là cách xử lý metadata chữ ký **khi trộn JAR**, không phải lời khuyên bỏ qua kiểm tra nguồn tải dependency. Cần tiếp tục xác minh artifact dependencies trước build, tạo SBOM/checksums/signed release artifact theo chính sách của nhóm và giữ license/notice bắt buộc. Shadow có cơ chế loại signatures JAR và JAR index theo cấu hình mặc định được tài liệu hóa; vẫn phải kiểm tra bản plugin và output thật.

## 9. Relocation: tính năng của Shade/Shadow, không phải đóng gói nested

### 9.1. Relocation là gì?

Giả sử plugin/library A và ứng dụng đều cần một thư viện có package `org.example.util` nhưng ở hai version khó tương thích. Maven Shade hoặc Shadow có thể **đổi tên package/class** của dependency **khi đóng gói**, ví dụ:

~~~text
Trước: org.example.util.Helper
Sau:   com.acme.internal.shaded.util.Helper
~~~

Mục đích là giảm xung đột namespace trên classpath của **consumer**. Điều này đặc biệt hữu ích khi phát hành một library/plugin dùng trong môi trường có nhiều dependencies khó kiểm soát.

**Relocation không phải version upgrade**; nó thay bytecode class references và một số resource descriptors theo khả năng của tool. Thay package tên class có thể ảnh hưởng **reflection, serialized class names, resource lookup, ServiceLoader, JNI, module-info, frameworks scan class names bằng chuỗi**, v.v.

### 9.2. Maven Shade relocation minh họa

Trong `maven-shade-plugin`, dưới `<configuration>`:

~~~xml
<relocations>
    <relocation>
        <pattern>org.apache.commons.lang3</pattern>
        <shadedPattern>com.example.internal.shaded.lang3</shadedPattern>
    </relocation>
</relocations>
~~~

Nếu áp dụng cho CLI demo, class `StringUtils` trong **output** có thể nằm ở đường dẫn mới, và bytecode `App.class` được plugin điều chỉnh để tham chiếu tên mới. **Source Java vẫn import** package gốc khi compile; relocation là bước packaging.

### 9.3. Gradle Shadow relocation minh họa

Trong `build.gradle`, bên trong task `shadowJar`:

~~~groovy
tasks.named('shadowJar') {
    relocate 'org.apache.commons.lang3',
             'com.example.internal.shaded.lang3'
}
~~~

Cả hai đoạn chỉ là **ví dụ cấu hình thêm**, không phải yêu cầu bắt buộc của ba project cơ bản. Với Spring Boot app, **đừng bật relocation đại trà cho `org.springframework.*`**: rất nhiều metadata, reflection và framework contracts phụ thuộc vào tên class/package.

### 9.4. Minimization có thể phá runtime reflection

Shade có `minimizeJar`; Shadow có `minimize()`. Các cơ chế giảm kích thước dựa vào phân tích tham chiếu tĩnh có thể loại classes **chỉ được load qua reflection, SPI, cấu hình, Spring DI/auto-configuration hoặc serialization**. Một project có thể compile và unit-test pass, nhưng runtime báo `ClassNotFoundException` sau khi minimize.

Quy tắc: **đo output thật, có allowlist/exclusions và chạy integration/smoke tests** trước khi dùng minimize cho ứng dụng Spring Boot hoặc plugin framework phức tạp.

## 10. Vì sao không bật cả Boot repackage và Maven Shade cùng một artifact?

### 10.1. Hai plugin đang thay đổi cấu trúc theo các quy tắc khác nhau

Nếu một `pom.xml` bind đồng thời `maven-shade-plugin:shade` và `spring-boot-maven-plugin:repackage` vào `package` cho **cùng một artifact**, kết quả phụ thuộc thứ tự các goal, classifier, thao tác thay thế source JAR và những files/manifest được mỗi plugin viết. Bạn có thể thấy:

- Boot repackage xử lý JAR đã được shade, khiến dependencies bị đóng vừa dưới dạng classes gộp vừa dưới dạng nested libraries.
- Shade xử lý một executable Boot JAR, gộp lại files nhưng giữ `BOOT-INF`/loader theo layout không mong muốn.
- `Main-Class` bị thay đổi từ `JarLauncher` sang ứng dụng, hoặc ngược lại; manifest và file tree không còn khớp.
- Mất resource descriptors, class duplicates và unexpected dependency conflicts.
- CI publish nhầm classifier `original`/`all`/`exec`, rồi production chạy một artifact khác artifact đã test.

**Không có quy tắc “Shade luôn chạy trước rồi Boot tự hiểu”** áp dụng chung. Nếu cần hai formats, tạo **artifacts/classifiers hoặc modules tách biệt**, kiểm soát task/goal cho từng output, đảm bảo không trùng file path và smoke-test **chính xác file sẽ deploy**.

### 10.2. Với Spring Boot app thông thường: chọn plugin chuẩn của Boot

Maven:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Nếu dùng `spring-boot-starter-parent`, goal `repackage` đã được cấu hình trong parent; nếu không dùng parent đó, cần tự thêm execution/version phù hợp.

Gradle khi dùng Spring Boot plugin:

~~~bash
./gradlew bootJar
~~~

Chọn `bootJar` để tạo executable nested JAR có Boot loader; không dùng `shadowJar` chỉ vì thấy chữ “fat JAR” trong yêu cầu triển khai.

### 10.3. Với CLI tool, Maven plugin, thư viện Java đặc thù

Nếu ứng dụng là CLI tool Java thuần dùng `main`, không có Spring Boot app lifecycle, Shade/Shadow thường phù hợp để phát hành **một JAR chạy trực tiếp**. Nếu mục tiêu là **library để người khác nhúng**, `shadedArtifactAttached` (Maven) hoặc một variant phù hợp (Gradle) có thể giúp publish **bản có relocation** mà không ghi đè thin artifact. Nhưng phải đảm bảo Maven POM/Gradle module metadata phản ánh dependencies chính xác và không vô tình mang hai bản cùng classes vào consumer.

**Boot executable JAR không phù hợp để dùng trực tiếp làm library dependency** vì app classes nằm dưới `BOOT-INF/classes`; compiler/classloader của project tiêu thụ không coi đó là layout thông thường. Hãy tách shared classes thành library module có thin JAR hoặc publish artifact phù hợp theo tài liệu Boot.

## 11. Cách kiểm tra kiểu JAR trong CI

### 11.1. Bước 1: chạy jar tf

~~~bash
jar tf target/nested-boot-0.0.1-SNAPSHOT.jar
jar tf target/flat-maven-1.0.0-all.jar
jar tf build/libs/flat-gradle-1.0.0-all.jar
~~~

Các đường dẫn này thuộc **ba project tách biệt** trong bài; phải chạy tại project root tương ứng, không chạy cả ba trong cùng một thư mục nếu chưa copy artifacts về nơi chung.

Bảng nhận diện:

| Nếu thấy | Kết luận phù hợp |
| --- | --- |
| `BOOT-INF/classes` + `BOOT-INF/lib/*.jar` + Boot `JarLauncher` | Boot nested executable JAR kiểu thông thường |
| `org/apache/commons/lang3/StringUtils.class` trực tiếp tại root và có `Main-Class=App` | Shaded/uber JAR của ví dụ |
| Chỉ `com/example/archives/App.class`, không có Commons Lang classes/JAR | Thin JAR, cần runtime classpath ngoài |
| `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` | Executable WAR layout của Boot (khác JAR) |
| Không có `BOOT-INF/lib` nhưng có `BOOT-INF/classes` | Có thể là archive tùy biến hoặc thiếu dependencies; cần kiểm manifest và build log |

`jar tf` chỉ liệt kê **entries của JAR hiện tại**, không tự bung tất cả file bên trong nested JAR entry. Muốn kiểm tra một class cụ thể trong dependency của Boot nested archive, hãy biết nó nằm trong `BOOT-INF/lib/<dependency>.jar` và kiểm tra dependency đó bằng công cụ ZIP phù hợp, nhưng **không repack sản phẩm** trong lúc chẩn đoán.

### 11.2. Bước 2: đọc Main-Class và Start-Class

Nếu môi trường có `unzip`:

~~~bash
unzip -p target/nested-boot-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
unzip -p target/flat-maven-1.0.0-all.jar META-INF/MANIFEST.MF
~~~

Mẫu kỳ vọng:

~~~text
Boot:   Main-Class=org.springframework.boot.loader.launch.JarLauncher
        Start-Class=com.example.archives.NestedBootApplication

Shade:  Main-Class=com.example.archives.App
        (không cần Start-Class theo Boot Loader)
~~~

Hai dòng `Boot:` và `Shade:` là **bảng ghi chú minh họa**, không phải định dạng chính xác của manifest. Trong file manifest thực tế, mỗi attribute có dạng `Name: Value`.

### 11.3. Bước 3: chạy chính file artifact sẽ phát hành

~~~bash
java -jar target/nested-boot-0.0.1-SNAPSHOT.jar
java -jar target/flat-maven-1.0.0-all.jar
java -jar build/libs/flat-gradle-1.0.0-all.jar
~~~

Kỳ vọng:

~~~text
BOOT_OK Hello
FLAT_OK Hello
FLAT_OK Hello
~~~

Đây là **ba kết quả từ ba lần chạy độc lập**, không phải một lệnh in ba dòng liên tục. Boot có startup logs ngoài dòng ứng dụng; các CLI flat ví dụ chỉ có một dòng do `main` in nếu thành công. Nếu đặt logging/agents hoặc môi trường lạ, stdout có thể có các dòng bổ sung.

### 11.4. Bước 4: so sánh dependency tree và archive

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Dependency tree cho biết Maven/Gradle đã chọn **versions nào**; `jar tf` cho biết **các files nào thực sự có trong artifact**. Khi Shade/Shadow merge, file `.class` mất thông tin tên JAR nguồn trong layout; đừng dựa vào `jar tf` của uber JAR để suy đoán dependency version gốc.

### 11.5. Bước 5: kiểm lỗi resource/service

Ngoài việc chạy main, kiểm chứng những chức năng cần SPI/reflection/auto-configuration:

- `ServiceLoader` tìm đủ providers cần thiết.
- Spring context khởi tạo và tạo đủ beans (khi dùng Boot).
- Serialization, JSON modules, JDBC drivers và logging providers hoạt động đúng.
- Resource lookup tìm được `META-INF/*` phù hợp.
- Không có duplicate entries bất thường hoặc `SecurityException` do signature files.
- Tên artifact/classifier đúng với release pipeline.

Nếu chỉ có `java -jar` chạy và in “Hello” thì chưa đủ để kết luận một Spring Boot app có hàng chục starters đã được shade an toàn.

## 12. Tốc độ, kích thước, layering và supply chain

### 12.1. Tốc độ khởi động

Không có kết luận phổ quát “nested JAR chậm hơn” hay “shaded JAR nhanh hơn”. Startup chịu ảnh hưởng classloading, file I/O, filesystem/cache, CPU, JIT, reflection, Spring bean creation, container base image và số lượng dependencies.

- Nested JAR: Boot Loader có overhead khởi tạo loader/classpath, nhưng giữ thư viện đóng gói theo layout Boot đã tối ưu và hỗ trợ nhiều cơ chế packaging.
- Shaded JAR: ít classpath entries về hình thức, nhưng merge quá lớn hoặc xử lý metadata không đúng cũng có thể làm startup lỗi/chậm; đổi package và minimize có tác động riêng.

Muốn so sánh, hãy build **cùng functionality**, dùng cùng JDK/runtime, lặp benchmark nhiều lần sau warmup và đo từ process start tới readiness thật. Không so kích thước file khác nhau rồi suy ra startup time.

### 12.2. Docker/OCI layers

Spring Boot nested executable JAR có thể kèm `BOOT-INF/layers.idx`. Boot Maven/Gradle tooling hoặc container-image tooling có thể dùng metadata này để chia dependencies, loader, snapshot dependencies và app classes thành layers riêng; điều này có thể cải thiện cache reuse khi chỉ code ứng dụng đổi.

Một shaded JAR không tự có Boot `layers.idx`, vì classes/resources đã gộp vào chung archive. Vẫn có thể xây image nhiều layers bằng chiến lược khác, nhưng cần cấu hình và công cụ riêng; **không khẳng định shaded JAR không thể containerize**.

### 12.3. Kích thước file và tính tái lập

- Nested JAR giữ từng dependency archive (một số đã có nén riêng). Outer entry `STORED` cần cho Boot Loader seek, nên không suy kích thước theo “nén hai lớp”.
- Shade/Shadow gộp bytes và có thể xử lý duplicate resources, relocation/minimize. Kích thước lớn/nhỏ hơn phụ thuộc nội dung và cấu hình.
- Reproducible builds phụ thuộc version locks/BOM, timestamps, file ordering, archive settings và build environment. Có thể kiểm tra checksums của **cùng build inputs** trên CI ổn định.
- Khi một library có license/NOTICE yêu cầu giữ thông tin phân phối, shade không miễn nghĩa vụ giữ chúng. Không loại `META-INF/LICENSE`/`NOTICE` chỉ để tối ưu size nếu vi phạm license terms.

### 12.4. Dependency scanning và SBOM

Đối với Boot nested JAR, mỗi nested dependency thường còn filename/version rõ ràng, giúp nhiều công cụ phân tích JAR nhận diện ranh giới. Trong shaded JAR, class files đã gộp và package có thể được relocated; một scanner chỉ nhìn archive có thể khó suy ra chính xác nguồn thư viện.

**Không có kiểu đóng gói nào tự bảo đảm an toàn:** vẫn phải pin dependencies, quét vulnerabilities theo dependency graph ở build time, lưu SBOM (SPDX/CycloneDX nếu quy trình yêu cầu), kiểm tra license và chỉ phát hành artifact đã test.

## 13. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| Boot JAR có `BOOT-INF/lib` nhưng chạy `java -cp app.jar Main` báo thiếu class | JVM chuẩn không nhận nested JAR classpath | Chạy `java -jar`, dùng manifest Boot Loader; không coi outer jar là thin classpath |
| `no main manifest attribute` khi chạy JAR | Đang chạy thin JAR hoặc Shade/Shadow chưa đặt Main-Class | Xem `META-INF/MANIFEST.MF` và artifact/classifier thực tế |
| Boot executable JAR manifest `Main-Class` là app main | Plugin/transformer khác ghi đè manifest hoặc sai layout | Chỉ định lại build ownership, dùng Boot plugin `repackage` chuẩn |
| Shaded JAR báo `NoClassDefFoundError` | Dependency bị exclude, minimize hoặc classpath/version conflict | Kiểm dependency tree, include/minimize, `jar tf` |
| Shade/Shadow có class nhưng Spring beans/auto-config thiếu | Spring META-INF resource bị ghi đè, chưa merge | Kiểm auto-config imports/factories, dùng Boot nested mặc định khi thích hợp |
| `ServiceLoader` chỉ thấy một provider | `META-INF/services` trùng path bị drop | Dùng ServicesResourceTransformer/mergeServiceFiles và duplicate strategy đúng |
| Shadow `mergeServiceFiles()` không hiệu lực | `duplicatesStrategy=EXCLUDE` loại input trước transformer | Bật INCLUDE cho service descriptors, xử lý resource khác rõ ràng |
| `SecurityException: Invalid signature file digest` | JAR gộp giữ signature files từ dependency đã bị thay bytes | Loại signatures không còn hợp lệ khỏi merged artifact; giữ xác minh nguồn ở build |
| `FileNotFoundException` khi thư viện tìm JAR path thật | Library giả định dependency là file ngoài trên disk | Xem classloader/resource APIs, `requiresUnpack` nếu library thật sự cần |
| Hai plugins cùng package tạo output khó dự đoán | Shade và Boot repackage ghi cùng artifact/manifest | Tách artifact/classifier/task, smoke-test đúng file phát hành |
| `jar tf` không tìm thấy `StringUtils.class` trong Boot JAR | Class nằm trong nested commons-lang3 JAR | Tìm `BOOT-INF/lib/commons-lang3-...jar` thay vì root class |
| Gradle báo không tương thích Shadow plugin | Shadow 9.3.0 yêu cầu Gradle >= 9.0, Java >= 17 | Dùng Gradle Wrapper/plugin release tương thích |
| Kích thước JAR giảm nhưng runtime lỗi reflection | `minimize` loại classes dùng động | Tắt minimize/định nghĩa exclusions, chạy full integration tests |
| Maven build có hai JAR `...jar` và `...-all.jar` | `shadedArtifactAttached=true` | Publish đúng classifier; đừng deploy nhầm thin JAR |
| Runtime version khác dependency tree | Artifact cũ hoặc plugin filter/relocation khác build hiện tại | `clean package`, kiểm build logs, checksum và output artifact |

### 13.1. Phương pháp chẩn đoán theo ba câu hỏi

**Câu hỏi A — Archive là kiểu gì?** Dùng `jar tf` để tìm `BOOT-INF/lib` (nested) hoặc root dependency classes (shaded).

**Câu hỏi B — Ai là entrypoint?** Đọc manifest. Boot kiểu `JAR` có `Main-Class: JarLauncher` + `Start-Class`; shaded CLI có `Main-Class` là app.

**Câu hỏi C — Tài nguyên cần thiết còn đủ không?** Với Shade/Shadow, kiểm `META-INF/services`, Spring metadata, duplicates, relocation và class loaders. Với Boot nested, kiểm dependencies có ở `BOOT-INF/lib` và build plugin không exclude chúng.

## 14. Bài tập thực hành

**Bài 1 — Nhận diện file.** Một JAR có `BOOT-INF/classes` và `BOOT-INF/lib/foo-1.0.jar`. Một JAR khác có `org/example/Foo.class` tại root. JAR nào là nested?  
**Đáp án:** JAR thứ nhất theo layout Boot nested; JAR thứ hai có dấu hiệu flatten/gộp classes (hoặc có thể là thin JAR), cần kiểm thêm manifest/dependencies để phân loại chính xác.

**Bài 2 — Manifest.** Vì sao Boot JAR `Main-Class` thường không trỏ trực tiếp vào `@SpringBootApplication`?  
**Đáp án:** Vì Boot Loader cần khởi tạo classloader truy cập `BOOT-INF/classes` và nested dependencies trước khi gọi `Start-Class` của ứng dụng.

**Bài 3 — Kết quả stdout.** Chạy ba ví dụ trong bài. Boot in `BOOT_OK Hello`, Shade và Shadow in `FLAT_OK Hello`. Cách đóng gói khác nhau có bắt buộc tạo khác biệt về output business logic không?  
**Đáp án:** Không. Khác biệt chính là layout và classloading. Các ví dụ này in prefix khác nhau để giúp phân biệt project, không phải vì nested/shaded tự thay đổi logic.

**Bài 4 — Java SPI.** Hai JAR chứa cùng path `META-INF/services/com.example.spi.Plugin`, mỗi file khai báo một implementation khác nhau. Điều gì xảy ra nếu Shade chỉ giữ file đầu?  
**Đáp án:** Provider của file sau có thể bị mất; dùng ServicesResourceTransformer. Shadow cần mergeServiceFiles và kiểm duplicate handling.

**Bài 5 — Jar tf.** Vì sao không thể chỉ dùng `jar tf boot-app.jar` rồi tìm `org/apache/commons/lang3/StringUtils.class`?  
**Đáp án:** `jar tf` chỉ liệt kê entries của outer JAR, còn class ở trong `BOOT-INF/lib/commons-lang3-3.17.0.jar`.

**Bài 6 — Relocation.** Dự án là library nhúng vào ứng dụng khác có dependency version conflict. Tính năng nào hữu ích hơn: Boot repackage hay Shade/Shadow relocation?  
**Đáp án:** Có thể dùng Shade/Shadow relocation một cách có kiểm thử vì cần đổi namespace; Boot executable JAR không phải hình thức library dependency thông thường.

**Bài 7 — Build song song hai định dạng.** Bạn cần Boot runnable JAR và thin library JAR cho modules khác. Có nên dùng một archive duy nhất làm cả hai?  
**Đáp án:** Không. Dùng artifacts/modules/classifiers tách biệt với output và publishing rõ ràng; thư viện nên có class layout root bình thường.

**Bài 8 — Chọn cách đóng gói.** Một REST API Spring Boot dùng nhiều starters, Jackson modules và Spring auto-config. Team định Shade toàn bộ “để giảm container image size”. Nên làm gì trước?  
**Đáp án:** Ưu tiên Boot plugin/nested JAR và Boot layers/tooling; đo image size/startup thực tế. Nếu vẫn muốn Shade, phải thiết kế merge metadata và integration tests, không lấy tên gọi “fat JAR” làm lý do.

## 15. Checklist trước khi phát hành

- [ ] Đã xác định artifact là Spring Boot nested JAR, shaded/uber JAR hay thin JAR.
- [ ] Đã đọc `META-INF/MANIFEST.MF` và kiểm `Main-Class`/`Start-Class` phù hợp với layout.
- [ ] Với Boot: thấy `BOOT-INF/classes`, `BOOT-INF/lib`, Boot Loader và chạy `java -jar` thành công.
- [ ] Với Shade/Shadow: thấy dependencies cần thiết ở root classes/resources và manifest trỏ app main.
- [ ] Đã kiểm tra dependency tree/versions và artifact cuối cùng **đúng file được deploy**.
- [ ] Đã đánh giá resource collisions, `META-INF/services` và metadata Spring khi gộp.
- [ ] Relocation/minimize chỉ bật khi có use case rõ, có integration tests cho reflection/SPI.
- [ ] Đã xử lý signatures/NOTICE/licenses và rà yêu cầu compliance.
- [ ] Không để Boot repackage và Shade/Shadow vô tình thao tác cùng output hoặc classifier.
- [ ] Nếu dùng Shadow, plugin ID/version tương thích Gradle/Java thực tế.
- [ ] Có smoke test chạy file bằng `java -jar` ở môi trường gần production.
- [ ] Đã lưu build provenance, dependency graph và SBOM theo yêu cầu của nhóm.

## 16. Tài liệu chính thức

- Spring Boot 3.5 — Nested JARs: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html
- Spring Boot 3.5 — Launching Executable Jars: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html
- Spring Boot 3.5 — Executable Jar Restrictions: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/restrictions.html
- Spring Boot 3.5 — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Build/Using a Boot App as Dependency: https://docs.spring.io/spring-boot/3.5/how-to/build.html
- Maven Shade Plugin — Executable JAR: https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html
- Maven Shade Plugin — Resource Transformers: https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html
- Maven Shade Plugin — Class Relocation: https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html
- GradleUp Shadow — Getting Started: https://gradleup.com/shadow/getting-started/
- GradleUp Shadow — Merging and Duplicates: https://gradleup.com/shadow/configuration/merging/
- GradleUp Shadow — Relocation: https://gradleup.com/shadow/configuration/relocation/
- GradleUp Shadow — Compatibility Matrix: https://gradleup.com/shadow/
- Commons Lang 3.17.0 Artifact: https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.17.0

**Kết luận:** Với ứng dụng Spring Boot, **nested executable archive + Boot Loader** là đường đóng gói chuẩn: dependencies giữ dạng JAR riêng trong `BOOT-INF/lib` và loader biết cách nạp chúng. Maven Shade/Gradle Shadow tạo **JAR gộp classes/resources**, hữu ích cho Java CLI hoặc relocation của thư viện, nhưng cần chủ động xử lý trùng resource, SPI, manifest và metadata. Đừng đánh đồng “chỉ một file JAR” với “cùng cơ chế classloading”; hãy dùng `jar tf`, manifest và smoke tests để xác nhận artifact sẽ triển khai.