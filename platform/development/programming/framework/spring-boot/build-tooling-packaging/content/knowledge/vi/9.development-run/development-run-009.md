# Nhận diện chênh lệch giữa classpath phát triển và classpath của archive

Một ứng dụng Spring Boot có thể chạy tốt bằng `./gradlew bootRun` hoặc `mvn spring-boot:run` nhưng lại gặp `ClassNotFoundException`, thiếu file cấu hình hoặc hành vi khác khi triển khai bằng `java -jar app.jar`. Nguyên nhân thường nằm ở **classpath thực sự được dùng ở hai cách chạy**, cách build tool phân loại dependency, quy tắc đóng gói artifact và cả cách Spring Boot launcher nạp class từ các JAR lồng nhau.

Bài này hướng dẫn cách **nhận diện, giải thích và kiểm chứng** chênh lệch đó bằng dữ liệu quan sát được. Mục tiêu không phải làm cho mọi classpath giống hệt nhau: một số khác biệt, đặc biệt các thành phần dành riêng cho phát triển, là **có chủ đích**. Điều quan trọng là phân biệt khác biệt hợp lệ với dependency hoặc resource bị bỏ sót khi đóng gói.

## 1. Classpath là gì và tại sao có nhiều loại?

**Java classpath** là tập các vị trí (thư mục class/resource và JAR) mà Java class loader có thể dùng để tìm class và tài nguyên. Một ứng dụng Spring Boot còn có cơ chế launcher/class loader để xử lý các thư viện JAR nằm **bên trong executable archive**. Do đó không thể lấy một chuỗi `java.class.path` rồi coi đó là danh sách đầy đủ mọi class mà Spring Boot đang nạp.

Trong project Java thông thường, Gradle phân biệt các classpath/configuration sau:

| Loại | Dùng khi nào? | Thường chứa gì? |
| --- | --- | --- |
| `compileClasspath` | Biên dịch mã nguồn chính | API và dependency cần lúc compile; có thể bao gồm `compileOnly` |
| `runtimeClasspath` | Chạy mã nguồn chính | Class/resource đã biên dịch và dependency runtime theo cấu hình project |
| `testCompileClasspath` | Biên dịch test | Dependency mã nguồn chính, test và thư viện chỉ dùng cho test |
| `testRuntimeClasspath` | Chạy test | Test classes, application classes và dependency phục vụ test |
| `bootRun.classpath` | Chạy ứng dụng qua Gradle | Mặc định dựa trên runtime classpath của main source set; có thể được tùy chỉnh |
| `bootJar.classpath` | Tạo executable Spring Boot JAR | Các thành phần được task đóng gói; plugin có thể loại dependency dành riêng cho phát triển |

Trong Maven, scope như `compile`, `runtime`, `provided` và `test` đóng vai trò phân định mục đích, nhưng không ánh xạ hoàn toàn một-một với configuration của Gradle. Các plugin Maven/Gradle còn có thể áp dụng quy tắc packaging riêng.

**Câu hỏi cần tách rõ:**

1. **Compiler có thấy class không?** Kiểm tra compile classpath.
2. **Tiến trình phát triển có thấy class/resource không?** Kiểm tra classpath mà `bootRun` hoặc `spring-boot:run` thực sự dùng.
3. **Archive chứa class/resource/JAR không?** Kiểm tra output của `bootJar`, `bootWar` hoặc Maven `repackage`.
4. **JVM triển khai có nạp được không?** Chạy đúng archive với Java runtime, cấu hình và loader thực tế.

Một dependency nằm trong build script **không tự chứng minh** nó được đưa vào executable archive; một JAR đã có trong archive cũng chưa đảm bảo môi trường đích có đầy đủ configuration, native library hay quyền truy cập tài nguyên cần thiết.

## 2. Vì sao `bootRun` khác `java -jar`?

### 2.1. Chạy từ output directories của project

Với Spring Boot Gradle plugin và Java plugin, `bootRun` là task thuộc loại `BootRun` (mở rộng `JavaExec`). Mặc định task dùng runtime classpath của main source set. Trong một project điển hình, nó tham chiếu các vị trí tương tự:

~~~text
build/classes/java/main/
build/resources/main/
<Gradle cache>/.../spring-boot-*.jar
<Gradle cache>/.../spring-context-*.jar
<Gradle cache>/.../các runtime dependencies khác
[tùy chỉnh thêm thư mục/JAR dành riêng cho bootRun]
~~~

Đây là sơ đồ minh họa, không phải output cố định. Đường dẫn thực tế phụ thuộc Gradle version, OS, source sets, plugins, project path và cấu hình task. `bootRun` không cần tạo executable JAR trước khi chạy.

Ưu điểm trong phát triển: class/resources vừa được build có thể chạy trực tiếp, một số thay đổi có thể được áp dụng nhanh, và classpath có thể bao gồm công cụ chỉ phục vụ development như `spring-boot-devtools`.

### 2.2. Chạy từ executable Spring Boot JAR

`bootJar` tạo một archive có bố cục đặc trưng:

~~~text
classpath-demo.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...      (Boot launcher)
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/demo/...             (class ứng dụng)
    │   ├── application.yml                  (nếu có)
    │   └── tài nguyên được package
    └── lib/
        ├── spring-boot-*.jar
        ├── spring-context-*.jar
        └── các runtime dependency được đóng gói
~~~

Lệnh:

~~~bash
java -jar build/libs/classpath-demo.jar
~~~

khởi động executable archive qua launcher được khai báo trong manifest. Spring Boot launcher tạo cơ chế nạp class cho `BOOT-INF/classes` và các nested JAR trong `BOOT-INF/lib`. Java class loader chuẩn không tự biết cách xử lý tất cả nested JAR theo cách này; Boot launcher đảm nhiệm phần đặc thù của archive.

Các khác biệt thường thấy:

| Khía cạnh | `bootRun` | `java -jar` executable Boot JAR |
| --- | --- | --- |
| Nguồn class ứng dụng | Output directory của main source set | `BOOT-INF/classes` trong archive |
| Dependency | Những vị trí JAR thuộc classpath của task | Các nested JAR đã đóng gói ở `BOOT-INF/lib` |
| Development-only dependency | Có thể xuất hiện, tùy cấu hình | Thường được loại khỏi archive theo mặc định |
| Tài nguyên thêm bằng `bootRun.classpath` | Có thể được nhìn thấy | Không tự đi vào archive |
| Cấu hình JVM | `bootRun`, JVM args/system properties của task | JVM args/system properties của lệnh triển khai |
| Tốc độ thay đổi mã | Thuận tiện cho phát triển | Phải rebuild artifact để nhận thay đổi đã sửa |
| Cách nạp class | Chủ yếu qua classpath phát triển; devtools có thể thêm loader | Boot launcher xử lý nested JAR |
| Mục đích | Chạy từ source/build output | Kiểm chứng và phân phối artifact cụ thể |

**Không được nhầm cấu hình runtime với classpath.** Hai lần chạy có thể có classpath giống về thư viện nhưng cho hành vi khác vì `spring.profiles.active`, environment variables, system properties, Java version, working directory, secrets, network hoặc port. Vì vậy chẩn đoán phải có bằng chứng class/resource thực sự thiếu, thay vì tự động đổ lỗi cho classpath.

## 3. Các loại dependency có mặt hoặc vắng mặt như thế nào?

### 3.1. Gradle configurations thông dụng

Với Java/Spring Boot Gradle project:

| Khai báo | Compile main | Runtime main | Executable Boot JAR thông thường |
| --- | --- | --- | --- |
| `implementation 'group:artifact'` | Có | Có | Thường có, nếu thuộc dependency của task đóng gói |
| `compileOnly 'group:artifact'` | Có | Không được thêm chỉ nhờ `compileOnly` | Không được đóng gói chỉ nhờ `compileOnly` |
| `runtimeOnly 'group:artifact'` | Không dùng để compile main | Có | Thường được đóng gói |
| `testImplementation 'group:artifact'` | Không dùng để compile main | Không | Không; phục vụ test |
| `testRuntimeOnly 'group:artifact'` | Không | Không | Không; phục vụ test runtime |
| `annotationProcessor 'group:artifact'` | Chạy trong annotation processing khi compile | Không tự thành runtime dependency | Không được đóng gói chỉ nhờ cấu hình này |
| `developmentOnly 'group:artifact'` của Boot plugin | Không phải cơ chế compile thông thường | Dùng cho development runtime | Mặc định loại khỏi Boot archive |

Bảng mô tả **mặc định quan trọng để học**, không phải luật áp dụng cho mọi custom source set hay plugin. Nếu build script tự nối một configuration vào `bootJar.classpath` hoặc `bootRun.classpath`, kết quả có thể thay đổi; phải xem cấu hình task thực tế.

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.postgresql:postgresql'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **mảnh `build.gradle`**, giả định plugins/repositories và dependency management đã được thiết lập. PostgreSQL JDBC driver cần cho runtime nếu ứng dụng sử dụng PostgreSQL; `spring-boot-devtools` phục vụ development; `starter-test` không được đem vào JAR production chỉ vì test chạy thành công.

### 3.2. Devtools: chênh lệch có chủ đích

`spring-boot-devtools` là ví dụ quan trọng nhất:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Với tích hợp mặc định của Spring Boot Gradle plugin, `developmentOnly` phục vụ classpath phát triển và **được loại khỏi executable JAR/WAR**. Spring Boot Maven plugin cũng mặc định loại devtools khỏi repackaged archive. Điều này giúp các tính năng phát triển như restart/reload không thành phần mặc định của sản phẩm triển khai.

Không có gì sai khi `spring-boot-devtools` nhìn thấy trong môi trường `bootRun` nhưng **không thấy** ở `BOOT-INF/lib`. Đây là khác biệt **thiết kế**. Khi cần kiểm chứng, tra tài liệu plugin/version và mở archive thực tế, thay vì dựa vào điều bạn nghĩ dependency sẽ được đóng gói.

### 3.3. Các trường hợp dễ gây thiếu class thật

- **Dùng `compileOnly` cho thư viện phải chạy lúc runtime:** biên dịch thành công nhưng lúc `java -jar` thiếu class; trong development cũng có thể thiếu, trừ khi IDE hoặc công cụ khác vô tình bổ sung.
- **Dùng `testImplementation` cho thư viện mà mã chính cần:** test có thể pass vì test classpath rộng hơn, nhưng ứng dụng production không có dependency.
- **Kéo dependency qua IDE/manual classpath:** IDE chạy được nhờ library tự thêm, còn Gradle/Maven package đúng theo build script nên thiếu.
- **Khai báo sai scope Maven:** thư viện chỉ ở `test` hoặc `provided` không thuộc runtime packaging theo cách người viết tưởng.
- **Bị exclude theo rule packaging:** `bootJar`/`repackage`, exclusions hoặc custom task classpath bỏ module khỏi archive.
- **Class thực sự có nhưng không load được dependency bắc cầu:** một class có mặt nhưng quá trình load/initialize gặp `NoClassDefFoundError` vì class khác bị thiếu.

Không sửa bằng cách chuyển **mọi** dependency sang `implementation`. Hãy xác định thư viện đó cần ở compile, runtime, test hay chỉ development, rồi chỉnh **đúng scope/configuration**.

## 4. Thí nghiệm có thể chạy: development resource hiện diện, archive không có

Bài thực hành dưới đây tạo khác biệt **có chủ đích và dễ đo**: thêm thư mục `dev-only/` vào classpath của `bootRun`, còn `bootJar` dùng cấu hình đóng gói thông thường. Java kiểm tra sự hiện diện của resource qua **context class loader**; không phải suy ra từ đường dẫn.

Mẫu dùng Java **17**, Spring Boot **3.3.5**, Gradle wrapper **8.7** (hoặc phiên bản tương thích). Version cố định chỉ để minh họa, không có nghĩa là version mới nhất. Không cần database, HTTP server hoặc mạng khi chạy ứng dụng sau khi dependencies đã tải về.

Cấu trúc:

~~~text
classpath-demo/
├── settings.gradle
├── build.gradle
├── dev-only/
│   └── dev-only-marker.txt
└── src/
    └── main/
        ├── java/com/example/demo/ClasspathDemoApplication.java
        └── resources/main-marker.txt
~~~

### 4.1. `settings.gradle`

~~~groovy
rootProject.name = 'classpath-demo'
~~~

### 4.2. `build.gradle` đầy đủ

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.run.BootRun

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}

tasks.named('bootRun', BootRun) {
    // Chỉ thêm thư mục này vào classpath của bootRun.
    classpath files('dev-only')
}

tasks.named('bootJar', BootJar) {
    archiveFileName.set('classpath-demo.jar')
}
~~~

`classpath files('dev-only')` là lời gọi **thêm** classpath entry của `JavaExec`, không thay thế main runtime classpath mà Spring Boot plugin đã thiết lập. `dev-only/` là thư mục ở root project, chứa một resource file ngay bên trong. Đoạn cấu hình **không** thêm thư mục này vào `sourceSets.main.resources` hoặc `bootJar.classpath`, nên nó không tự được copy vào executable JAR.

### 4.3. File `src/main/java/com/example/demo/ClasspathDemoApplication.java`

~~~java
package com.example.demo;

import java.net.URL;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ClasspathDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClasspathDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner checkResources() {
        return args -> {
            ClassLoader loader =
                    Thread.currentThread().getContextClassLoader();

            System.out.println("MAIN_RESOURCE=" +
                    state(loader.getResource("main-marker.txt")));
            System.out.println("DEV_ONLY_RESOURCE=" +
                    state(loader.getResource("dev-only-marker.txt")));
        };
    }

    private static String state(URL resource) {
        return resource == null ? "absent" : "present";
    }
}
~~~

Đây là chương trình Java 17+ chạy được khi kết hợp với hai file Gradle ở trên. Việc sử dụng context class loader giúp kiểm tra resource có thật sự tìm được trong **runtime hiện tại**, kể cả khi Spring Boot launcher tổ chức các nested JAR khác cách JVM thông thường xử lý system classpath.

### 4.4. Hai file resource

**`src/main/resources/main-marker.txt`**:

~~~text
main resource
~~~

**`dev-only/dev-only-marker.txt`**:

~~~text
development resource
~~~

Cả hai file chứa một dòng text UTF-8. Java ở ví dụ chỉ kiểm tra chúng **có được nạp qua class loader hay không**, không đọc nội dung file, vì vậy kết quả không phụ thuộc vào ký tự xuống dòng cuối file.

### 4.5. Chạy qua development classpath

Nếu project đã có Gradle Wrapper:

~~~bash
./gradlew -q bootRun --args='--spring.main.banner-mode=off --logging.level.root=OFF'
~~~

Hai dòng do ứng dụng in là:

~~~text
MAIN_RESOURCE=present
DEV_ONLY_RESOURCE=present
~~~

`main-marker.txt` xuất hiện do `src/main/resources` được xử lý thành main resources. `dev-only-marker.txt` xuất hiện vì ta đã **thêm `dev-only/` vào `bootRun.classpath`**. Gradle hoặc Spring Boot có thể in các dòng khác tùy môi trường; hai dòng trên là kết quả logic của chính chương trình.

### 4.6. Đóng gói và chạy executable archive

~~~bash
./gradlew -q clean bootJar
java -jar build/libs/classpath-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Hai dòng do ứng dụng in:

~~~text
MAIN_RESOURCE=present
DEV_ONLY_RESOURCE=absent
~~~

Đây là khác biệt **được thiết kế trong build script**. `main-marker.txt` được copy vào archive dưới `BOOT-INF/classes`; `dev-only-marker.txt` chỉ được thêm riêng cho `bootRun` nên không được `bootJar` đóng gói. Kết quả không phản ánh “lỗi Spring Boot”: archive chứa đúng những gì task packaging được hướng dẫn.

Kiểm tra JAR trực tiếp:

~~~bash
jar tf build/libs/classpath-demo.jar
~~~

Trong danh sách entry, có thể tìm:

~~~text
BOOT-INF/classes/com/example/demo/ClasspathDemoApplication.class
BOOT-INF/classes/main-marker.txt
BOOT-INF/lib/spring-boot-*.jar
~~~

Đường dẫn thư viện có tên version cụ thể chứ không chứa dấu `*` thật; dòng `BOOT-INF/lib/spring-boot-*.jar` là **mẫu khái quát**, không phải output nguyên văn của `jar tf`. `BOOT-INF/classes/dev-only-marker.txt` không có trong archive ở cấu hình bài này.

Trên Windows PowerShell, chạy `.\gradlew.bat` thay `./gradlew` và nên viết lệnh trên một dòng, điều chỉnh dấu nháy của đối số nếu shell yêu cầu. Nếu chưa có wrapper, dùng Gradle phiên bản tương thích để tạo một lần bằng `gradle wrapper --gradle-version 8.7` rồi dùng wrapper.

### 4.7. Bài học từ thí nghiệm

Chạy cùng một `main()`, cùng một project, nhưng resource khác nhau vì **classpath được cấu hình cho từng đường thực thi**. Nếu file đó cần ở production, cách đúng là chuyển nó thành runtime resource được quản lý trong `src/main/resources` hoặc một nguồn cấu hình ngoài thích hợp, **không** chỉ nối thêm vào `bootRun.classpath`. Nếu resource chứa secret hoặc cấu hình phụ thuộc môi trường, không tùy tiện nhúng nó vào archive; nên sử dụng external configuration và secret store ở môi trường chạy.

## 5. Những khác biệt khác cần kiểm tra ngoài ví dụ resource

### 5.1. Devtools: có trong phát triển, thiếu trong archive theo mặc định

Nếu thêm vào Gradle:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

`bootRun` có thể hưởng tính năng developer tools; executable Boot JAR thông thường loại dependency này. Điều đó có chủ đích. Nếu devtools dùng restart class loader trong phát triển, lỗi nạp class có thể còn liên quan đến sự phân tách **base class loader** và **restart class loader**, không đơn thuần là thiếu JAR. Việc tắt restart khi chẩn đoán có thể giúp phân biệt lỗi loader, nhưng không nên bật devtools cho môi trường production chỉ để “chữa” triệu chứng.

Spring Boot documentation lưu ý devtools có thể gây vấn đề class loading, đặc biệt với multi-module projects. Hãy phân biệt **dependency có trong classpath phát triển** với **class loader nào thực sự nạp class**.

### 5.2. Thư viện transitive bị exclude hoặc version conflict

Một starter có thể mang nhiều dependency bắc cầu. Gradle/Maven sẽ resolve version dựa trên declarations, dependency management/BOM, exclusions và các quy tắc riêng. Runtime classpath và đóng gói có thể lệch nếu task packaging dùng configuration khác hoặc có exclusions.

Các triệu chứng:

- `ClassNotFoundException`: loader không tìm thấy một class được truy vấn theo tên.
- `NoClassDefFoundError`: class được tham chiếu nhưng không thể hoàn tất định nghĩa/nạp một dependency cần thiết (hoặc từng lỗi lúc khởi tạo). Đọc phần **Caused by** trong stack trace, đừng suy ra chỉ một nguyên nhân.
- `NoSuchMethodError` hoặc `NoSuchFieldError`: có thể là **sai phiên bản tương thích nhị phân** dù tên class vẫn tìm được. So sánh version classpath và các JAR thực sự được nạp.

Đừng sửa bằng cách thêm tùy tiện tất cả thư viện vào `bootJar`. Trước tiên xác định module nào được yêu cầu và phiên bản nào đang chạy.

### 5.3. Resource, template, SPI và cấu hình

File trong `src/main/resources` thường vào `build/resources/main` khi phát triển rồi vào `BOOT-INF/classes` khi đóng gói. Các nguồn tài nguyên khác, ví dụ:

- File đặt cạnh thư mục project nhưng không nằm dưới resource source directory.
- File được IDE thêm thủ công vào development classpath.
- File được task generator tạo ra nhưng chưa nối vào `processResources` hoặc `bootJar`.
- Descriptor `META-INF/services/...` dùng bởi `ServiceLoader`.
- Template hoặc asset có đường dẫn khác sau khi đóng gói.
- File ở hệ thống file ngoài và được truy cập bằng relative path dựa trên current working directory.

có thể hoạt động ở development nhưng không có trong archive. Ngoài classpath, hãy kiểm tra **đường dẫn file tuyệt đối/tương đối**. Ví dụ `new File("config/local.properties")` tìm file theo working directory; nó **không** tự đọc resource từ `BOOT-INF/classes`.

Với tài nguyên đóng gói, dùng API classpath thích hợp, chẳng hạn:

~~~java
try (var stream = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream("main-marker.txt")) {
    if (stream == null) {
        throw new IllegalStateException("Missing classpath resource");
    }
    byte[] data = stream.readAllBytes();
    System.out.println("RESOURCE_BYTES=" + data.length);
}
~~~

Đây là đoạn Java minh họa **đặt trong method có quyền ném/khai báo `IOException`** hoặc có xử lý exception phù hợp; không phải file Java độc lập. Đối với tài nguyên trong nested JAR, không giả định `getResource(...).getFile()` luôn trả về đường dẫn file hệ thống có thể mở bằng `new File(...)`. Dùng `getResourceAsStream`/Spring `Resource` là lựa chọn bền vững hơn khi chỉ cần đọc nội dung.

### 5.4. Test chạy được nhưng artifact không chạy

`testRuntimeClasspath` thường có test classes và libraries như JUnit, Mockito hoặc Testcontainers mà production không có. Nếu code chạy trong test nhờ dependency thuộc `testImplementation` nhưng runtime chính cần nó, artifact sẽ thiếu. Các helper test, test configuration và fake service thường **không nên** vào production; chỉ các dependency thật sự phục vụ ứng dụng mới phải đặt ở runtime scope.

`bootTestRun` (nếu plugin/version hỗ trợ) chạy một test main class với test runtime classpath; nó **không thay thế** kiểm chứng executable Boot JAR trong production.

### 5.5. WAR khác executable JAR

Với Spring Boot executable WAR, layout dùng `WEB-INF/classes`, `WEB-INF/lib` và có thể `WEB-INF/lib-provided` cho các thành phần phục vụ kịch bản vừa chạy executable vừa deploy vào servlet container bên ngoài. Đừng áp sơ đồ `BOOT-INF/classes`/`BOOT-INF/lib` của executable JAR cho mọi file `.war`.

Một dependency `providedRuntime` trong dự án WAR có ý nghĩa khác `runtimeOnly`; với external servlet container, server có thể cung cấp Servlet API/container runtime. Nếu ứng dụng chạy được bằng `bootRun` nhưng thiếu dependency trong WAR, cần kiểm tra **loại packaging, scope và container đích**, không chỉ tên file.

### 5.6. Java version và runtime environment

Archive có thể chứa đúng mọi class, nhưng JVM production quá cũ so với bytecode, dẫn đến `UnsupportedClassVersionError`. Đây là lỗi **tương thích Java version**, không đơn thuần là thiếu classpath. Với thư viện native, mismatch OS/architecture cũng có thể gây `UnsatisfiedLinkError`. Cấu hình Spring profiles, database URL, chứng chỉ, network hoặc quyền ghi file cũng có thể khiến ứng dụng thất bại dù classpath đầy đủ.

## 6. Phương pháp chứng minh class/resource có thật ở đâu

### 6.1. Kiểm tra dependency graph của Gradle

Trong thư mục project dùng Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-boot-devtools --configuration runtimeClasspath
~~~

- `compileClasspath` cho biết các thư viện liên quan đến compile main.
- `runtimeClasspath` cho biết graph runtime main theo configuration của project; không đồng nghĩa toàn bộ output archive nếu Boot plugin có packaging exclusion.
- `testRuntimeClasspath` giúp phát hiện dependency chỉ xuất hiện khi chạy test.
- `dependencyInsight` giúp lần ngược đường dependency, lý do chọn version và các yêu cầu cạnh tranh.

Các lệnh này có output phụ thuộc project, version Gradle và repository; không có một stdout cố định cho mọi ứng dụng. Với multi-project build, chỉ rõ project:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

`:app` chỉ là tên subproject giả định. Thay bằng đường dẫn đúng của module ứng dụng. Build root không nhất thiết có cùng dependency graph với subproject.

### 6.2. Kiểm tra archive trực tiếp

~~~bash
./gradlew clean bootJar
jar tf build/libs/classpath-demo.jar
~~~

Chú ý ba nhóm entry:

1. **`BOOT-INF/classes`:** class/resources của ứng dụng có thực sự vào archive?
2. **`BOOT-INF/lib`:** JAR dependency cụ thể có vào archive, đúng version không?
3. **Manifest/launcher:** đây là executable Spring Boot JAR hay plain JAR?

Với Gradle Spring Boot plugin, task `jar` và `bootJar` có thể cùng tồn tại; các version mới thường để plain JAR với classifier `plain` theo mặc định. Nếu vô tình chạy file `*-plain.jar`, lỗi có thể do **chọn sai artifact** chứ không phải do `bootJar` đóng gói sai.

Không xem kết quả `./gradlew dependencies` như bằng chứng duy nhất về artifact: đó là graph configuration, còn `jar tf` cho biết **thành phần thực tế trong file được tạo ra**.

### 6.3. Kiểm tra class loader đang dùng

Để xem một class có nạp được tại runtime hay không, có thể thêm một probe nhỏ:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
try {
    Class<?> type = Class.forName(
            "com.example.somepackage.OptionalIntegration", false, loader);
    System.out.println("CLASS_FOUND=" + type.getName());
} catch (ClassNotFoundException ex) {
    System.out.println("CLASS_MISSING=com.example.somepackage.OptionalIntegration");
}
~~~

Đây là **đoạn kiểm tra minh họa**, cần thay tên class bằng class thực sự quan tâm và đặt trong Java method. `Class.forName(..., false, loader)` tránh chủ động initialize class trong lời gọi này, nhưng việc resolve/link phụ thuộc cấu trúc class vẫn có thể gây linkage errors khác. Một class tìm được chưa chắc mọi dependency của nó đều tương thích hoặc hoạt động được.

Với resource, dùng:

~~~java
var url = Thread.currentThread()
        .getContextClassLoader()
        .getResource("main-marker.txt");
System.out.println(url == null ? "RESOURCE_MISSING" : "RESOURCE_FOUND");
~~~

Giá trị URL của nested JAR có thể có scheme/cú pháp khác tùy Spring Boot version. **Đừng đoán đường dẫn URL rồi ép sang `File`** nếu resource nằm trong archive; đọc bằng stream/API thích hợp.

### 6.4. Vì sao `System.getProperty("java.class.path")` chưa đủ?

Khi `java -jar app.jar`, system classpath ở tầng Java launcher có thể chỉ phản ánh đường dẫn **app.jar**, trong khi Boot launcher nạp nhiều nested JAR qua class loader chuyên dụng. Khi chạy `bootRun`, property này thường liệt kê nhiều thư mục/JAR riêng. So sánh trực tiếp hai chuỗi đó có thể tạo **kết luận giả rằng các dependency của JAR đều mất**.

Muốn chứng minh thiếu thành phần, hãy kiểm tra **archive entries và khả năng nạp class/resource bằng runtime class loader**, thay vì chỉ so độ dài của `java.class.path`.

### 6.5. Kiểm tra Maven khi dùng `spring-boot:run` và `repackage`

Trong dự án Maven:

~~~bash
mvn dependency:tree
mvn help:effective-pom
mvn clean package
jar tf target/ten-ung-dung.jar
java -jar target/ten-ung-dung.jar
~~~

`mvn dependency:tree` giúp kiểm tra cây dependency theo scope, `effective-pom` cho biết parent/dependencyManagement/plugin configuration sau kế thừa. `spring-boot-maven-plugin:repackage` tạo executable archive nếu được bind đúng vào packaging lifecycle; chỉ có BOM hoặc starter dependency **không tự đảm bảo** JAR đã được repackage.

Dự án dùng `spring-boot-starter-parent` có thể khai báo `spring-boot-maven-plugin` trong `<build><plugins>` để nhận execution `repackage` do parent quản lý. Dự án chỉ import Spring Boot BOM cần cấu hình plugin/execution riêng. File JAR cụ thể trong `target/` phụ thuộc `artifactId`, `version`, classifier và plugin settings. Tên `ten-ung-dung.jar` trong ví dụ là **mẫu thay thế bằng tên artifact thật**, không phải file được Maven mặc định tạo.

Spring Boot Maven plugin mặc định loại devtools khỏi repackaged archive. Vì vậy trong Maven cũng có thể xuất hiện chênh lệch development/runtime có chủ đích.

## 7. Quy trình chẩn đoán từng bước

Khi nghe “chạy `bootRun` ổn nhưng `java -jar` lỗi”, hãy làm theo thứ tự sau:

1. **Tái hiện đúng hai lệnh** tại cùng source revision. Xác nhận `bootRun` chạy class/resources hiện tại và `bootJar` đã được rebuild sau lần sửa cuối.
2. **Ghi lại lỗi chính xác**: class name/resource path, exception chain và thời điểm lỗi. Phân biệt lỗi nạp class, version không tương thích, file path và cấu hình môi trường.
3. **Kiểm tra dependency configuration**: `runtimeClasspath`, `developmentOnly`, `compileOnly`, `testRuntimeClasspath`, transitive exclusions và resolved versions.
4. **Mở đúng archive sẽ deploy** bằng `jar tf`. Kiểm tra class tại `BOOT-INF/classes`, JAR tại `BOOT-INF/lib`, resource và manifest. Không nhầm `plain.jar` với `bootJar`.
5. **Đối chiếu cấu hình task**: có custom `bootRun.classpath`, `sourceResources`, `bootJar.classpath`, generated resources, packaging exclusions, custom sourceSets hay convention plugins không?
6. **Kiểm tra runtime Java và launcher**: Java version/architecture, arguments, profiles, working directory, container image, environment/secrets.
7. **Sửa đúng nơi sở hữu dữ liệu**: đổi dependency scope nếu thư viện thật sự cần runtime; đưa resource cần đóng gói vào main resources; loại development-only resources khỏi production nếu chúng không nên đi theo archive.
8. **Chạy lại kiểm chứng**: `clean bootJar` (hoặc Maven `clean package`), đọc archive, thử đúng file `java -jar` và chạy tests quan trọng.

Một kết luận QA hữu ích phải nói rõ **thiếu cái gì**, **thiếu ở đâu**, **đường dependency/resource nào tạo ra khác biệt**, **thay đổi nào đã sửa** và **đã kiểm chứng bằng lệnh nào**.

## 8. Các sai lầm thường gặp

| Triệu chứng | Kết luận vội dễ sai | Cách nhận diện chính xác |
| --- | --- | --- |
| `java.class.path` của `java -jar` chỉ có một JAR | “Tất cả dependency bị mất” | Kiểm tra nested JAR ở `BOOT-INF/lib` và Boot launcher |
| Devtools không có trong archive | “`bootJar` đóng gói sai” | Xác minh `developmentOnly` và default devtools exclusion |
| IDE chạy được, JAR lỗi thiếu class | “JVM production không hỗ trợ Spring” | So IDE/run classpath, Gradle runtime configuration, artifact và Java version |
| Test pass, runtime thiếu library | “Thư viện đã có vì test dùng được” | Kiểm tra `testImplementation` vs runtime dependencies |
| Resource đọc được bằng `new File(...)` lúc dev, lỗi trong JAR | “Spring Boot không đóng gói resources” | Kiểm tra `BOOT-INF/classes` và chuyển sang classpath resource stream khi phù hợp |
| `NoClassDefFoundError` | “Chắc chắn thiếu đúng class trong message” | Đọc nguyên nhân lồng nhau, phụ thuộc bắc cầu, class initialization |
| `NoSuchMethodError` | “Class hoàn toàn không tồn tại” | Kiểm tra version conflict/binary incompatibility |
| Ứng dụng không kết nối database | “Thiếu JDBC driver” | Kiểm tra driver trong archive **và** URL, credential, mạng, DB, profile |
| `java -jar` báo không có main manifest | “Sai source code” | Có thể đang chạy plain JAR thay vì Boot executable JAR |
| Thay `bootRun.classpath` thì JAR vẫn không có resource | “Gradle bỏ qua cấu hình” | `bootRun` và `bootJar` là hai task có classpath/đầu ra khác nhau |
| WAR chạy ở embedded container nhưng lỗi ở external container | “WAR hỏng” | Kiểm tra `providedRuntime`, external container, classpath và API version |

### Tránh vá tạm bằng classpath bên ngoài mà không rõ nguyên nhân

Thêm `-cp` khi đang dùng `java -jar` không hoạt động giống chạy main class bằng `java -cp ...`: với lệnh `-jar`, Java launcher sử dụng JAR được chỉ định làm entry point và không tự ghép classpath ứng dụng từ `-cp` theo cách thông thường. Spring Boot có các launcher/mode đặc biệt để xử lý external libraries, nhưng không nên coi đó là cách mặc định khắc phục thiếu dependency trong artifact.

Nếu thư viện **thực sự** thuộc runtime application, sửa build script rồi rebuild archive để artifact chứa dependency đúng. Nếu thư viện do môi trường/container cung cấp, mô tả rõ contract triển khai và kiểm tra classloader/container tương ứng.

## 9. Bài tập đối chiếu và đáp án

**Tình huống A.** `build.gradle` có:

~~~groovy
dependencies {
    compileOnly 'org.example:some-runtime-api:1.0'
}
~~~

Compile thành công. Artifact chạy thì thiếu class của API đó. Bạn cần xem gì?

**Đáp án:** `compileOnly` không bổ sung dependency vào runtime theo mặc định. Nếu API thật sự phải được application tải khi chạy, chọn dependency scope runtime phù hợp (thường `implementation` hoặc `runtimeOnly` tùy code), xác nhận phiên bản có tồn tại và kiểm tra lại `BOOT-INF/lib`. Nếu API do external container cung cấp, cần xác nhận contract của container trước khi thay scope.

**Tình huống B.** `spring-boot-devtools` có trong `bootRun` nhưng không nằm trong `BOOT-INF/lib`.

**Đáp án:** Đây thường là kết quả mong muốn của `developmentOnly`/quy tắc đóng gói Boot. Không nên ép devtools vào production chỉ vì hai classpath không giống nhau.

**Tình huống C.** `src/main/resources/app-marker.txt` đọc được qua `getResourceAsStream` khi chạy `java -jar`, nhưng `new File("src/main/resources/app-marker.txt")` thất bại trong container.

**Đáp án:** `getResourceAsStream` tìm resource qua class loader trong archive; `new File` mở một đường dẫn vật lý tương đối với working directory của container. Chúng là hai nguồn khác nhau; không phải resource trong archive nhất thiết thiếu.

**Tình huống D.** `./gradlew dependencies --configuration runtimeClasspath` cho thấy thư viện X, nhưng `jar tf app.jar` không thấy X ở `BOOT-INF/lib`.

**Đáp án:** Kiểm tra đã mở **đúng executable archive của lượt build hiện tại** chưa; xem dependency có nằm trong cấu hình bị loại như `developmentOnly`, có bị packaging exclusion, custom `bootJar.classpath` hay filtering không. Một resolved configuration không tự chứng minh nội dung cuối của archive.

**Tình huống E.** `java -jar` báo `UnsupportedClassVersionError` trong khi mọi JAR đều có mặt.

**Đáp án:** So sánh Java bytecode target và Java runtime đích. Lỗi này thường là sai version JVM, không phải package thiếu dependency. Kiểm tra `java --version` tại đúng môi trường triển khai.

**Tình huống F.** Code in `ClassNotFoundException` cho JDBC driver nhưng chỉ xảy ra ở một container.

**Đáp án:** Kiểm tra driver thực sự nằm trong archive, container có chạy **đúng phiên bản artifact** không, và có cấu hình custom loader/profiles/version Java khác không. Không khẳng định nguyên nhân chỉ từ việc máy phát triển chạy được.

## 10. Nguồn tham khảo chính thức

- Spring Boot Gradle Plugin — [Running Your Application](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun`, runtime classpath, reload resources và JavaExec.
- Spring Boot Gradle Plugin — [Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar`, nội dung archive và development-only dependencies.
- Spring Boot — [Developer Tools](https://docs.spring.io/spring-boot/reference/using/devtools.html): devtools, class loader restart và packaged application.
- Gradle — [Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): `compileClasspath`, `runtimeClasspath` và test configurations.
- Gradle — [Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies` và `dependencyInsight`.
- Spring Boot Maven Plugin — [Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html): `repackage` và cấu trúc executable archive.

**Ghi nhớ:** **Classpath phát triển là những gì tiến trình phát triển thực sự thấy; classpath của archive là những gì task đóng gói đưa vào artifact và Boot launcher nạp khi thực thi.** Muốn kết luận đúng, hãy so **dependency graph → cấu hình task → nội dung archive → class/resource hiện diện lúc runtime**. Những phép đo này giúp xác định chênh lệch nào là chủ đích và chênh lệch nào cần sửa.
