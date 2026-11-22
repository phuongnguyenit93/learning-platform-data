# Kiểm tra thay đổi Boot Loader, jarmode và cấu trúc đóng gói giữa các phiên bản

## 1. Mục tiêu và phạm vi

Spring Boot executable JAR/WAR không chỉ là archive chứa class và dependency. Plugin đóng gói còn tạo manifest, đặt application classes vào đúng thư mục, nhúng Spring Boot Loader, ghi index cho classpath/layers và có thể thêm công cụ chạy ở chế độ jarmode. Dockerfile, shell script, systemd unit, deployment pipeline và các bước phân tích artifact thường phụ thuộc vào những chi tiết này.

Khi nâng Spring Boot, build vẫn có thể thành công nhưng artifact hoặc image không còn chạy đúng nếu:

- Script vẫn gọi `-Djarmode=layertools` sau khi jarmode này bị loại bỏ.
- Dockerfile hard-code launcher class hoặc đường dẫn loader cũ.
- Build vẫn cấu hình `LoaderImplementation.CLASSIC` dù Boot 4 đã loại bỏ lựa chọn đó.
- Pipeline trông đợi launch script được nhúng trong executable JAR.
- Optional runtime dependency không còn được đưa vào executable archive theo mặc định.
- Dockerfile copy nhầm `*-plain.jar`, file `.original` hoặc artifact có classifier khác.
- Layer index hoặc jarmode tools bị tắt trong khi image build vẫn cần chúng.

Bài này giải thích cấu trúc executable archive, vai trò của Boot Loader, manifest, nested JAR, `classpath.idx`, `layers.idx`, jarmode và cách thay đổi qua các thế hệ Boot 3.3, 3.5, 4.0 và 4.1. Nội dung tập trung vào packaging Maven/Gradle và cách kiểm chứng artifact thật trước khi phát hành.

Sau bài này, bạn có thể:

- Đọc cấu trúc JAR/WAR và phân biệt launcher với main class của ứng dụng.
- Xác minh `Main-Class`, `Start-Class`, loader classes và các thư mục `BOOT-INF`/`WEB-INF`.
- Hiểu mốc chuyển từ `layertools` sang `tools` và lệnh thay thế.
- Loại bỏ cấu hình classic loader và embedded launch script khi nâng lên Boot 4.
- Kiểm tra thay đổi mặc định về optional dependencies trong Maven executable archive.
- Cấu hình `includeTools`, layers và `includeOptional` đúng mục đích.
- Cập nhật Dockerfile, scripts, service unit và CI artifact selection.
- Chạy kiểm tra archive, extraction, `java -jar` và container smoke test.

## 2. Bản đồ thay đổi theo phiên bản

Các mốc quan trọng cần nhớ:

| Phiên bản | Thay đổi liên quan đến packaging |
| --- | --- |
| Spring Boot 3.2 và cũ hơn | Các dự án có thể còn dùng `-Djarmode=layertools`, cấu hình `layers.includeLayerTools` hoặc loader implementation kiểu classic. |
| Spring Boot 3.3 | Giới thiệu jarmode `tools`; `extract` thay cho `layertools extract`, `list-layers` thay cho `layertools list-layers`. `layertools` và cấu hình cũ bị deprecated. |
| Spring Boot 3.5 | Tiếp tục hỗ trợ `tools`, layered archives, `includeTools` và các launcher trong package `org.springframework.boot.loader.launch`. Maven Plugin 3.5.7 trở lên có `includeOptional`. |
| Spring Boot 4.0 | Loại bỏ classic uber-JAR loader option; loại bỏ embedded launch scripts dùng để tạo fully executable JAR; optional Maven dependencies không còn được đưa vào uber JAR theo mặc định. |
| Spring Boot 4.1 | Loại bỏ jarmode `layertools`; dùng `tools`. Cấu trúc executable JAR/WAR và launcher manifest tiêu chuẩn vẫn dùng các đường dẫn `BOOT-INF`/`WEB-INF` và `org.springframework.boot.loader.launch`. |

Nguồn chính thức cần đọc cùng nhau: [Spring Boot 3.3 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes), [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide), [Spring Boot 4.1 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes).

**Điểm quan trọng:** không nên coi đây là một lần đổi tên package launcher duy nhất. Manifest launcher tiêu chuẩn `org.springframework.boot.loader.launch.JarLauncher` được tài liệu Boot 3.5 và Boot 4.1 cùng sử dụng. Các breaking changes chính là lựa chọn loader implementation, launch script, jarmode và dependency inclusion. Hãy đọc manifest của artifact do build tạo ra thay vì tự đoán tên class.

## 3. Executable JAR khác plain JAR như thế nào?

Plain JAR thường chứa class/resources của module. Nó không tự đóng gói toàn bộ runtime dependencies theo cấu trúc mà Spring Boot Loader có thể nạp trực tiếp bằng `java -jar`.

Executable JAR do Spring Boot Maven/Gradle Plugin tạo có thêm:

- Spring Boot Loader classes ở root của archive.
- Application classes trong `BOOT-INF/classes/`.
- Runtime dependencies dưới dạng nested JAR trong `BOOT-INF/lib/`.
- `META-INF/MANIFEST.MF` với launcher class và application main class.
- Có thể có `BOOT-INF/classpath.idx` và `BOOT-INF/layers.idx`.
- Có thể chứa `spring-boot-jarmode-tools` để hỗ trợ extraction/layer operations.

Cấu trúc minh họa:

~~~text
application.jar
|
+-- META-INF/
|   +-- MANIFEST.MF
|
+-- org/springframework/boot/loader/
|   +-- ... Boot Loader classes ...
|
+-- BOOT-INF/
    +-- classes/
    |   +-- com/example/Application.class
    |   +-- application.yml
    |
    +-- lib/
    |   +-- spring-boot-*.jar
    |   +-- spring-context-*.jar
    |   +-- application-dependency-*.jar
    |
    +-- classpath.idx     (optional)
    +-- layers.idx        (optional)
~~~

Java launcher đọc manifest để gọi Boot Loader. Loader thiết lập classloader phù hợp, đọc các nested JAR và sau đó gọi main class của ứng dụng. Nhờ vậy người dùng có thể chạy:

~~~bash
java -jar application.jar
~~~

Mô hình này khác shaded/fat JAR truyền thống. Shaded JAR thường giải nén rồi gộp class từ dependency vào cùng một archive; Boot executable JAR giữ dependency dưới dạng nested JAR riêng. Cách này tránh nhiều xung đột khi các thư viện có resource hoặc tên file trùng nhau và vẫn cho phép nhìn thấy dependency nào được đóng gói.

Tài liệu: [Executable Jar Format](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html).

## 4. Executable WAR và WEB-INF/lib-provided

Executable WAR có cấu trúc khác JAR vì nó có thể được chạy bằng embedded server hoặc triển khai vào Servlet container bên ngoài.

~~~text
application.war
|
+-- META-INF/
|   +-- MANIFEST.MF
|
+-- org/springframework/boot/loader/
|   +-- ... Boot Loader classes ...
|
+-- WEB-INF/
    +-- classes/
    |   +-- com/example/Application.class
    |
    +-- lib/
    |   +-- application dependencies
    |
    +-- lib-provided/
        +-- embedded-container dependencies
        +-- dependencies needed for executable WAR
~~~

- `WEB-INF/classes/` chứa class và resource của ứng dụng.
- `WEB-INF/lib/` chứa dependency thông thường.
- `WEB-INF/lib-provided/` chứa dependency cần khi chạy WAR độc lập nhưng được đánh dấu `provided` trong mô hình build để tránh xung đột khi triển khai vào container truyền thống.

Executable WAR có launcher manifest thích hợp và có thể chạy bằng `java -jar application.war`. Khi deploy lên external Tomcat/Servlet container, kiểm tra container version và provided dependencies riêng; một WAR chạy được bằng embedded launcher không tự chứng minh external container có cùng classpath hoặc Servlet API.

Không copy `BOOT-INF/lib` rules của JAR vào Dockerfile xử lý WAR. Đường dẫn và ý nghĩa provided dependencies khác nhau.

## 5. Manifest: launcher và application main class

Manifest có hai vai trò khác nhau:

- `Main-Class` là class khởi động Spring Boot Loader.
- `Start-Class` là class có `public static void main(String[] args)` của ứng dụng.

Ví dụ executable JAR:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.Application
~~~

Ví dụ executable WAR:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.Application
~~~

Không nhầm `Main-Class` với `Start-Class`. Nếu đặt `Main-Class` thành `com.example.Application` trong khi archive vẫn chứa nested dependencies, JVM không tự hiểu cách nạp nested JAR. Khi dùng Spring Boot Maven Plugin, plugin quản lý manifest; nếu cần thay `mainClass` hoặc layout, cấu hình ở Spring Boot Plugin thay vì cố sửa manifest bằng một plugin JAR khác.

### 5.1. JarLauncher, WarLauncher và PropertiesLauncher

- `JarLauncher` đọc nested libraries trong `BOOT-INF/lib/`.
- `WarLauncher` đọc libraries trong `WEB-INF/lib/` và `WEB-INF/lib-provided/`.
- `PropertiesLauncher` cho phép thêm vị trí dependency ngoài archive; mặc định vẫn tìm trong `BOOT-INF/lib/`, đồng thời có thể đọc `LOADER_PATH`, `loader.path` hoặc cấu hình trong `loader.properties`.

`PropertiesLauncher` hữu ích khi môi trường triển khai cần mount thư mục plugin/library bên ngoài archive. Tuy nhiên, phải kiểm soát version, quyền truy cập và tính bất biến của thư mục đó; dependency bên ngoài có thể làm cùng một JAR chạy ra kết quả khác giữa các môi trường.

Ví dụ đặt launcher qua manifest trong Gradle:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    manifest {
        attributes(
            "Main-Class" to "org.springframework.boot.loader.launch.PropertiesLauncher",
            "Start-Class" to "com.example.Application"
        )
    }
}
~~~

Chỉ chọn `PropertiesLauncher` khi thực sự cần loader path động. Với ứng dụng thông thường, để plugin chọn launcher theo layout mặc định.

Tài liệu: [Launching Executable Jars](https://docs.spring.io/spring-boot/4.1/specification/executable-jar/launching.html).

## 6. Package Boot Loader và thay đổi classic loader

Spring Boot Loader là bootstrap code bên trong executable archive. Package launcher chuẩn trong Boot 3.5 và Boot 4.1 là:

~~~text
org.springframework.boot.loader.launch.JarLauncher
org.springframework.boot.loader.launch.WarLauncher
org.springframework.boot.loader.launch.PropertiesLauncher
~~~

Các class loader được đặt trong archive dưới root path `org/springframework/boot/loader/`. Không nhầm package Java của launcher với đường dẫn archive của các loader classes.

### 6.1. Classic uber-JAR loader bị loại bỏ trong Boot 4.0

Một số build Boot 3.x có thể chọn classic loader implementation bằng cấu hình plugin. Spring Boot 4.0 đã loại bỏ classic uber-JAR loader. Nếu build đang có cấu hình dưới đây, phải bỏ nó khi nâng lên Boot 4:

Maven:

~~~xml
<configuration>
    <loaderImplementation>CLASSIC</loaderImplementation>
</configuration>
~~~

Gradle Groovy DSL:

~~~groovy
tasks.named("bootJar") {
    loaderImplementation = org.springframework.boot.loader.tools.LoaderImplementation.CLASSIC
}
~~~

Gradle Kotlin DSL:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    loaderImplementation =
        org.springframework.boot.loader.tools.LoaderImplementation.CLASSIC
}
~~~

Đây là cấu hình cũ để chỉ ra implementation classic. Boot 4 không còn lựa chọn này; hãy xóa cấu hình khỏi POM/build script và để plugin Boot 4 tạo loader mặc định.

Đừng thay bằng cách tự thêm dependency `spring-boot-loader` hoặc tự chép launcher class vào JAR. Spring Boot Plugin phải tạo archive và manifest đồng bộ với loader implementation của đúng phiên bản.

### 6.2. Không hard-code class launcher cũ

Các Dockerfile hoặc script rất cũ có thể gọi trực tiếp class `org.springframework.boot.loader.JarLauncher`. Với archive được đóng gói theo tài liệu Boot 3.5/4.1, launcher manifest tiêu chuẩn dùng package `org.springframework.boot.loader.launch`.

Kiểm tra các nơi hard-code:

- `Main-Class` trong manifest tự tạo.
- `ENTRYPOINT`/`CMD` của Dockerfile.
- Java command trong shell script hoặc service unit.
- `-Dloader.main`, classpath tự ghép hoặc custom launcher.
- Script giải nén archive rồi gọi launcher class trực tiếp.

Ưu tiên `java -jar application.jar`. Nếu bắt buộc gọi launcher class trực tiếp, phải kiểm tra manifest, classpath và loader version thực tế.

## 7. Embedded launch scripts bị loại bỏ trong Boot 4.0

Boot 3.x có thể tạo fully executable JAR bằng embedded launch script. Script được nối vào đầu archive để Unix-like OS có thể chạy file như shell script; plugin Maven có thuộc tính `executable` và `embeddedLaunchScript`, Gradle có `launchScript()`.

Ví dụ Maven cũ:

~~~xml
<configuration>
    <executable>true</executable>
</configuration>
~~~

Ví dụ Gradle cũ:

~~~groovy
tasks.named("bootJar") {
    launchScript()
}
~~~

Boot 4.0 đã loại bỏ embedded launch scripts. Hãy xóa cấu hình này khi nâng cấp. Executable JAR thông thường vẫn chạy bằng:

~~~bash
java -jar application.jar
~~~

Nếu cần chạy ứng dụng như một service, đưa lệnh khởi động vào service manager, container runtime hoặc deployment platform:

- systemd unit trên Linux.
- Docker/OCI `ENTRYPOINT`.
- Kubernetes container command.
- Gradle Application Plugin nếu cần script phân phối riêng.
- Process manager/Windows service wrapper do tổ chức hỗ trợ.

Không dùng launch script nhúng trong JAR mới và không giả định `java -Djarmode=tools -jar` có thể xử lý một archive có embedded launch script. Tài liệu Boot 3.5 nêu tools mode không dùng được với fully executable archive có launch script.

Tài liệu: [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).

## 8. Jarmode: từ layertools sang tools

Jarmode cho phép bootstrap code của Boot chạy một công cụ thay vì khởi động ứng dụng. Nó thường được dùng trong Docker build để đọc archive, liệt kê layer hoặc tách archive thành các thư mục.

### 8.1. Trước Boot 3.3: layertools

Các Dockerfile cũ có thể chứa:

~~~bash
java -Djarmode=layertools -jar application.jar list
java -Djarmode=layertools -jar application.jar extract
~~~

Jarmode `layertools` đã được deprecated trong Spring Boot 3.3.

### 8.2. Từ Boot 3.3: dùng tools

Boot 3.3 giới thiệu `tools` và thay thế các lệnh cũ:

| Lệnh cũ | Lệnh mới |
| --- | --- |
| `java -Djarmode=layertools -jar app.jar extract` | `java -Djarmode=tools -jar app.jar extract --layers` |
| `java -Djarmode=layertools -jar app.jar list-layers` | `java -Djarmode=tools -jar app.jar list-layers` |

Các lệnh thường dùng:

~~~bash
java -Djarmode=tools -jar application.jar
java -Djarmode=tools -jar application.jar help
java -Djarmode=tools -jar application.jar list-layers
java -Djarmode=tools -jar application.jar help extract
java -Djarmode=tools -jar application.jar extract
java -Djarmode=tools -jar application.jar extract --layers --destination extracted
~~~

- `extract` không có `--layers` tạo efficient layout: một JAR ứng dụng và các thư viện đã tách vào thư mục `lib/`. Layout này hữu ích cho startup, CDS và AOT cache.
- `extract --layers` tách nội dung theo `layers.idx` để Docker/OCI có thể tạo image layers riêng.
- `list-layers` hiển thị các layer có thể trích xuất.
- `help` và `help extract` hiển thị các command/options của chính archive đang chạy.

### 8.3. Boot 4.1 loại bỏ layertools

Spring Boot 4.1 loại bỏ jarmode `layertools`. Nếu script vẫn gọi `-Djarmode=layertools`, nó sẽ không còn là đường chạy hợp lệ. Hãy chuyển sang `-Djarmode=tools`, sau đó chạy thử command trên archive Boot 4.1 thực tế.

**Khuyến nghị:** chuyển các dự án Boot 3.x sang `tools` ngay trong giai đoạn chuẩn bị nâng cấp. Như vậy Dockerfile và script không còn phụ thuộc lệnh đã deprecated trước khi chuyển Boot major.

Nguồn: [Spring Boot 3.3 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes) và [Spring Boot 4.1 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes).

## 9. includeTools và việc nhúng jarmode tools vào archive

Khi tạo layered archive, plugin thêm `spring-boot-jarmode-tools` để `java -Djarmode=tools -jar ...` hoạt động. Tùy phiên bản plugin, việc tắt layer creation không đồng nghĩa với việc tắt tools JAR.

Từ Boot 3.3, cấu hình cũ `layers.includeLayerTools` được thay bằng `includeTools`. Dùng property mới:

Maven:

~~~xml
<configuration>
    <includeTools>true</includeTools>
</configuration>
~~~

Gradle Groovy DSL:

~~~groovy
tasks.named("bootJar") {
    includeTools = true
}
~~~

Gradle Kotlin DSL:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    includeTools.set(true)
}
~~~

Nếu archive không cần lệnh extraction/layer tools, có thể đặt `includeTools=false`. Nhưng nếu Dockerfile dùng jarmode tools, phải giữ tools dependency trong archive.

Không nhầm hai cấu hình:

- `layers.enabled=false` tắt việc tạo layer index/metadata theo cấu hình plugin.
- `includeTools=false` loại tools JAR khỏi archive.

Nếu build script dùng `layers.enabled=false` nhưng Dockerfile vẫn gọi `list-layers` hoặc `extract --layers`, image build có thể thất bại vì không còn layer metadata hoặc tools dependency phù hợp. Kiểm tra cả hai giá trị cùng lúc.

## 10. layers.idx, layer order và Docker cache

Layered JAR vẫn dùng layout executable JAR thông thường, đồng thời thêm `BOOT-INF/layers.idx`. Mặc định, các layer được chia theo mức độ thường xuyên thay đổi:

1. `dependencies`: dependency release không chứa `SNAPSHOT`.
2. `spring-boot-loader`: loader classes.
3. `snapshot-dependencies`: dependency có version chứa `SNAPSHOT`.
4. `application`: project/module dependencies, application classes và resources.

Ví dụ nội dung index:

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/library-a.jar"
  - "BOOT-INF/lib/library-b.jar"
- "spring-boot-loader":
  - "org/"
- "snapshot-dependencies":
  - "BOOT-INF/lib/library-snapshot.jar"
- "application":
  - "BOOT-INF/classes/"
  - "META-INF/"
~~~

Thứ tự layer có ý nghĩa. Dependency ổn định nên nằm trước; application code thay đổi thường xuyên nên nằm sau. Khi chỉ sửa source code, Docker có thể reuse dependency layers từ image trước và chỉ rebuild application layer.

`layers.idx` dùng cho việc chia archive thành OCI/Docker layers. Nó không phải danh sách classpath. `classpath.idx` có vai trò khác: ghi thứ tự các nested dependency JAR cần đưa vào classpath.

### 10.1. Tùy chỉnh layer

Chỉ tùy chỉnh layer khi có lý do rõ ràng, ví dụ một nhóm dependency nội bộ thay đổi theo chu kỳ riêng. Khi tùy chỉnh:

- Đảm bảo mọi archive entry cần thiết được gán vào đúng layer.
- Không để một file bị claim bởi nhiều rule ngoài ý muốn.
- Ghi rõ thứ tự layer.
- Kiểm tra `list-layers` và output extraction sau khi thay rule.
- Xác minh Dockerfile COPY đủ tất cả thư mục layer được tạo.

Nếu layer order đổi, cache behavior của Docker image cũng đổi. Đo lại kích thước image và số layer bị rebuild sau một thay đổi source/dependency mẫu.

## 11. classpath.idx và thứ tự dependency

`BOOT-INF/classpath.idx` có thể được plugin tạo tự động. Nó liệt kê nested JAR theo thứ tự classpath mà build system sử dụng khi chạy ứng dụng.

Ví dụ:

~~~text
- "BOOT-INF/lib/dependency-a.jar"
- "BOOT-INF/lib/dependency-b.jar"
~~~

Một số lưu ý:

- Plugin có thể tạo index tự động.
- Index được dùng khi chạy archive bằng `java -jar`.
- Nó không được dùng khi chạy ứng dụng từ IDE, `mvn spring-boot:run` hoặc Gradle `bootRun`.
- Khi bật reproducible builds, entries trong classpath index có thể được sắp xếp alphabetically theo quy tắc của plugin.
- Không tự tạo `classpath.idx` tùy tiện nếu không hiểu thứ tự dependency và cách launcher đọc nó.

Nếu ứng dụng chạy khác nhau giữa IDE và `java -jar`, kiểm tra classpath index, dependency order, duplicate classes/resources và cách plugin tạo archive.

## 12. Thay đổi optional dependencies trong Maven executable JAR

Đây là một thay đổi packaging có thể làm ứng dụng khởi động được ở local nhưng thiếu class khi chạy artifact.

Trong Spring Boot Maven Plugin 3.5.16, `includeOptional` có default `true`. Trong Spring Boot 4.0, optional dependencies không còn được đưa vào uber JAR theo mặc định. Maven Plugin 4.1 cũng ghi default `includeOptional=false`.

Nếu ứng dụng thực sự cần một dependency Maven được khai báo `<optional>true</optional>` trong executable archive, cần quyết định rõ:

1. Dependency đó có phải runtime requirement bắt buộc của ứng dụng không?
2. Nó có nên là dependency trực tiếp không optional của application module?
3. Nếu vẫn muốn giữ cách khai báo optional, có cần đặt `includeOptional=true` cho executable archive không?

Ví dụ Maven:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <includeOptional>true</includeOptional>
    </configuration>
</plugin>
~~~

Nếu optional dependencies chỉ dành cho module consumer hoặc tính năng được bật có điều kiện, không nên đưa tất cả vào production JAR một cách máy móc. Chỉ bật `includeOptional` sau khi hiểu dependency graph và mục đích của từng optional dependency.

**Phạm vi:** `includeOptional` là cấu hình Maven Plugin. Gradle quản lý dependency/variant theo mô hình riêng; hãy kiểm tra `runtimeClasspath` và output của `bootJar` thay vì giả định Gradle có cùng default Maven.

Tài liệu: [Boot 3.5 Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html), [Boot 4.1 Maven Plugin Packaging](https://docs.spring.io/spring-boot/4.1/maven-plugin/packaging.html), [Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).

## 13. Maven: repackage, layout và artifact gốc

Spring Boot Maven Plugin tạo executable archive qua goal `repackage`. Goal này xử lý JAR/WAR được tạo ở phase `package`; gọi goal riêng mà không chạy phase package có thể không có source archive để repack.

Lệnh thường dùng:

~~~bash
./mvnw clean package
~~~

Hoặc khi cần gọi rõ goal:

~~~bash
./mvnw package spring-boot:repackage
~~~

Nếu project kế thừa `spring-boot-starter-parent`, execution `repackage` thường đã được cấu hình sẵn; chỉ cần khai báo plugin theo hướng dẫn.

### 13.1. Maven archive layouts

Plugin hỗ trợ các layout:

| Layout | Ý nghĩa |
| --- | --- |
| `JAR` | Executable JAR tiêu chuẩn. |
| `WAR` | Executable WAR; provided dependencies được đặt trong `WEB-INF/lib-provided`. |
| `ZIP` hoặc `DIR` | Layout tương tự JAR nhưng dùng `PropertiesLauncher`. |
| `NONE` | Gộp dependencies/resources nhưng không nhúng bootstrap loader. |

Ví dụ:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.Application</mainClass>
        <layout>JAR</layout>
    </configuration>
</plugin>
~~~

`Main-Class` được plugin quản lý theo layout. Nếu dùng layout `ZIP`, launcher có thể là `PropertiesLauncher`; không copy manifest của layout `JAR` vào layout `ZIP`.

### 13.2. Artifact gốc và .original

Maven repackage mặc định đổi tên artifact không executable ban đầu thành `.original`. Có thể cấu hình classifier để giữ plain archive và executable archive song song.

Ví dụ một project có thể tạo:

~~~text
target/
  application.jar
  application.jar.original
~~~

Đừng để Dockerfile dùng wildcard `target/*.jar` rồi vô tình copy archive không mong muốn. Chỉ định chính xác artifact executable, classifier và tên file đã được xác minh.

### 13.3. Maven configuration mẫu cho Boot 4

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.Application</mainClass>
        <includeTools>true</includeTools>
        <includeOptional>false</includeOptional>
        <layers>
            <enabled>true</enabled>
        </layers>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là cấu hình minh họa cho Boot 4 khi muốn layered JAR có tools và không đưa optional dependencies vào archive. Nếu ứng dụng cần optional runtime dependencies, đặt `includeOptional=true` sau khi kiểm tra. Nếu project dùng parent đã cấu hình repackage, tránh tạo execution trùng lặp.

## 14. Gradle: bootJar, bootWar và plain archive

Gradle plugin cung cấp các task:

- `bootJar`: tạo executable JAR.
- `bootWar`: tạo executable WAR.
- `jar`/`war`: tạo plain archive theo Java/War plugin.

Khi Spring Boot plugin cấu hình `bootJar`, task `jar` thường dùng classifier `plain` để cả hai archive có thể cùng tồn tại.

Ví dụ:

~~~text
build/libs/
  application-1.0.0.jar
  application-1.0.0-plain.jar
~~~

Build:

~~~bash
./gradlew clean bootJar
./gradlew clean bootWar
./gradlew clean build
~~~

`build`/`assemble` được cấu hình để phụ thuộc `bootJar` khi dùng Java plugin. Hãy xem task output thay vì đoán artifact name.

### 14.1. Cấu hình layered bootJar

Kotlin DSL:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    layered {
        enabled.set(true)
    }
    includeTools.set(true)
    mainClass.set("com.example.Application")
}
~~~

Groovy DSL:

~~~groovy
tasks.named("bootJar") {
    layered {
        enabled = true
    }
    includeTools = true
    mainClass = 'com.example.Application'
}
~~~

Nếu không dùng jarmode tools:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    includeTools.set(false)
}
~~~

Khi đã đặt `includeTools=false`, Dockerfile không thể tiếp tục gọi `java -Djarmode=tools -jar ...` trên archive đó. Hãy giữ cấu hình đồng bộ với image build.

### 14.2. Đặt classifier rõ ràng

Nếu pipeline cần executable JAR với classifier `boot` và plain JAR không classifier:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    archiveClassifier.set("boot")
}

tasks.named<Jar>("jar") {
    archiveClassifier.set("")
}
~~~

Nếu plain JAR không cần thiết, có thể disable `jar` task trong một số ứng dụng thông thường. Không disable `jar` task nếu build native image hoặc plugin khác cần nó; kiểm tra các task consumer trước khi thay đổi.

## 15. Docker multi-stage build với jarmode tools

Layered JAR cho phép tách dependency ổn định và application code thành các Docker layers riêng. Mỗi `COPY` có thể tạo một layer mới; khi code đổi nhưng dependencies giữ nguyên, Docker có thể reuse các layer dependency.

Ví dụ Dockerfile:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS builder
WORKDIR /builder

COPY target/application.jar application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

FROM eclipse-temurin:21-jre
WORKDIR /application

COPY --from=builder /builder/extracted/dependencies/ ./
COPY --from=builder /builder/extracted/spring-boot-loader/ ./
COPY --from=builder /builder/extracted/snapshot-dependencies/ ./
COPY --from=builder /builder/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

Thay base image bằng JDK/JRE image đã được tổ chức phê duyệt, pin tag/digest theo policy và đảm bảo runtime Java phù hợp với bytecode của ứng dụng.

### 15.1. Đừng copy sai artifact

Maven có thể tạo `.original`; Gradle có thể tạo `-plain.jar`; project có thể dùng classifier `boot`. Dùng đường dẫn artifact cụ thể:

~~~dockerfile
COPY target/application.jar application.jar
~~~

Nếu dùng Gradle:

~~~dockerfile
ARG JAR_FILE=build/libs/application-1.0.0.jar
COPY ${JAR_FILE} application.jar
~~~

Không dựa vào `COPY target/*.jar` hoặc `COPY build/libs/*.jar` nếu thư mục có nhiều archive. Một Docker build có thể thành công nhưng copy nhầm plain archive và chỉ fail ở runtime.

### 15.2. Không dùng jarmode nếu archive không có tools

Kiểm tra trước khi gọi `extract`:

- Plugin có bật layers/đưa tools JAR vào archive không?
- Có `BOOT-INF/layers.idx` nếu dùng `extract --layers` không?
- Archive có phải executable JAR do Spring Boot Plugin tạo không?
- Có embedded launch script ở build cũ không?
- `includeTools` có bị đặt false không?

Nếu không cần extraction, có thể copy executable JAR trực tiếp vào runtime image và chạy `java -jar`. Layering là tối ưu cache/image build, không phải điều kiện để executable JAR hoạt động.

## 16. Archive indexes và reproducible builds

Hai index file có mục đích riêng:

| File | Vị trí | Dùng cho |
| --- | --- | --- |
| `classpath.idx` | `BOOT-INF/classpath.idx` | Thứ tự nested dependency JAR khi launcher tạo classpath. |
| `layers.idx` | `BOOT-INF/layers.idx` | Phân nhóm archive entries để tạo Docker/OCI layers. |

`classpath.idx` có thể được tạo cho JAR và WAR. `layers.idx` được dùng cho JAR. Các index files có cú pháp tương thích YAML nhưng Spring Boot không parse chúng như YAML tổng quát; phải tuân thủ chính xác format mà tài liệu mô tả.

Khi bật reproducible builds, plugin có thể chuẩn hóa thứ tự entries/timestamp. Nếu tự sửa index hoặc zip archive sau khi repackaging, có thể làm mất reproducibility hoặc thay đổi checksum. Nên để build plugin quản lý các file này và kiểm tra artifact được tạo ra từ clean build.

## 17. Nested JAR restrictions và thư viện cần unpack

Spring Boot Loader cần đọc nội dung nested JAR trực tiếp từ executable archive. Có một số giới hạn kỹ thuật:

- Zip entry đại diện cho nested JAR phải được ghi theo `ZipEntry.STORED`, không nén entry đó ở outer archive, để loader có thể seek trực tiếp tới nested content.
- Bản thân file nested JAR vẫn có thể chứa nội dung đã nén.
- Code cần nạp class từ nested JAR nên dùng `Thread.getContextClassLoader()`; `ClassLoader.getSystemClassLoader()` không nhìn thấy nested JAR theo cách thông thường.
- Một số thư viện giả định JAR luôn tồn tại như file riêng trên filesystem. Với các thư viện đó, cấu hình `requiresUnpack` để Boot Loader giải nén dependency ra thư mục tạm lúc chạy.

Ví dụ Maven:

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

Ví dụ Gradle:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    requiresUnpack("**/jruby-complete-*.jar")
}
~~~

Chỉ dùng `requiresUnpack` cho dependency đã xác định có vấn đề khi chạy nested. Giải nén mọi dependency làm tăng thời gian khởi động, I/O và dung lượng thư mục tạm.

Tài liệu: [Executable Jar Restrictions](https://docs.spring.io/spring-boot/4.1/specification/executable-jar/restrictions.html).

## 18. Kiểm tra artifact bằng công cụ dòng lệnh

Sau khi build, kiểm tra archive thực tế thay vì chỉ tin build log.

### 18.1. Liệt kê archive entries

Maven:

~~~bash
./mvnw clean package
jar tf target/application.jar
~~~

Gradle:

~~~bash
./gradlew clean bootJar
jar tf build/libs/application-1.0.0.jar
~~~

Tìm các entry:

- `META-INF/MANIFEST.MF`
- `org/springframework/boot/loader/`
- `BOOT-INF/classes/`
- `BOOT-INF/lib/`
- `BOOT-INF/classpath.idx`
- `BOOT-INF/layers.idx`

Với WAR, tìm `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided`.

### 18.2. Đọc manifest

Trên Linux/macOS có `unzip`:

~~~bash
unzip -p target/application.jar META-INF/MANIFEST.MF
~~~

Trên Windows hoặc môi trường không có `unzip`, dùng `jar xf` trong thư mục tạm:

~~~powershell
New-Item -ItemType Directory -Force manifest-check
Set-Location manifest-check
jar xf ..\target\application.jar META-INF/MANIFEST.MF
Get-Content .\META-INF\MANIFEST.MF
~~~

Xác nhận:

- `Main-Class` trỏ đến launcher đúng layout.
- `Start-Class` trỏ đến application main class.
- Không có class launcher cũ bị hard-code.
- Các attributes tùy chỉnh như `Class-Path`, `Loader-Path` hoặc build metadata có giá trị đúng.

### 18.3. Kiểm tra jarmode và layers

~~~bash
java -Djarmode=tools -jar target/application.jar list-layers
java -Djarmode=tools -jar target/application.jar help extract
java -Djarmode=tools -jar target/application.jar extract --layers --destination target/extracted
~~~

Kiểm tra các thư mục được tạo:

~~~text
target/extracted/
  dependencies/
  spring-boot-loader/
  snapshot-dependencies/
  application/
~~~

Không chỉ xác nhận command exit code 0; kiểm tra đủ layer và file cần thiết, sau đó chạy executable layout đã extract nếu đó là cách production deploy.

### 18.4. Kiểm tra checksum và nội dung

Lưu checksum của artifact phát hành:

~~~bash
sha256sum target/application.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash .\target\application.jar -Algorithm SHA256
~~~

So sánh checksum giữa artifact CI, artifact đã publish và artifact Docker build sử dụng. Nếu Docker build dùng file khác tên/classifier hoặc rebuild artifact ở stage sau, cần lưu bằng chứng chính xác artifact nào được đưa vào image.

## 19. Quy trình migration Boot 3.x lên Boot 4.x

Thực hiện theo thứ tự có thể kiểm chứng:

1. **Chốt baseline:** build clean, lưu checksum, manifest, `jar tf`, Dockerfile và CI output của bản hiện tại.
2. **Quét repo:** tìm `jarmode=layertools`, `LoaderImplementation.CLASSIC`, `loaderImplementation`, `launchScript()`, `executable=true`, `embeddedLaunchScript`, `includeLayerTools`, `includeOptional` và mọi launcher class hard-code.
3. **Nâng jarmode sớm:** từ Boot 3.3 trở đi chuyển sang `tools`; chạy lệnh `extract`, `list-layers` trên artifact Boot 3.5.
4. **Xử lý loader config:** xóa `loaderImplementation=CLASSIC` khi nâng Boot 4.0.
5. **Xử lý launch script:** bỏ cấu hình fully executable JAR; chuyển command sang service/container manager hoặc Gradle Application Plugin.
6. **Rà optional dependencies:** kiểm tra Maven `includeOptional` vì Boot 4 đổi default sang false.
7. **Rà layers/tools:** xác nhận `layers.enabled`, `includeTools`, `layers.idx` và Dockerfile đồng bộ.
8. **Nâng plugin cùng Boot:** đảm bảo Spring Boot Maven/Gradle Plugin cùng generation với Spring Boot runtime.
9. **Build archive:** chạy clean package/bootJar/bootWar và kiểm tra manifest, layout, indexes, classifier.
10. **Build container:** chạy extraction, COPY layers và startup trong image runtime.
11. **Smoke test:** chạy `java -jar`, health endpoint và một luồng chức năng quan trọng.
12. **Publish test:** kiểm tra artifact đã publish và Docker image digest có đúng nội dung đã QA.
13. **Rollback:** giữ lại image/artifact cũ và biết rõ cách quay về nếu archive mới thiếu dependency hoặc loader.

### 19.1. Quét cấu hình cũ trong repository

Dùng ripgrep:

~~~bash
rg -n "jarmode=layertools|LoaderImplementation\\.CLASSIC|loaderImplementation|launchScript\\(|embeddedLaunchScript|executable>true|includeLayerTools|includeOptional|org\\.springframework\\.boot\\.loader\\.JarLauncher" .
~~~

Xem cả thư mục deployment và pipeline, không chỉ POM/build.gradle:

- Dockerfile và Dockerfile templates.
- Shell scripts, Makefile, build scripts.
- Helm chart, Kubernetes manifests.
- systemd unit hoặc service wrapper.
- CI workflows, release scripts và artifact publishing.
- Internal build plugin/convention plugin.
- README/runbook vận hành.

Nếu repo không có `rg`, dùng `grep -R` hoặc tìm kiếm tương đương. Đọc ngữ cảnh từng match trước khi sửa; không thay chuỗi hàng loạt mà không xác nhận nó thuộc version/build path nào.

## 20. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `no main manifest attribute` | Plain JAR hoặc manifest không có launcher | Kiểm tra `Main-Class`; build bằng `repackage`/`bootJar`. |
| `ClassNotFoundException` cho `JarLauncher` | Manifest gọi sai package/class hoặc loader classes thiếu | Đọc manifest và kiểm tra `org/springframework/boot/loader/`. |
| `ClassNotFoundException` cho application main class | `Start-Class` sai hoặc application classes không nằm trong `BOOT-INF/classes` | Kiểm tra build output và `Start-Class`. |
| `NoClassDefFoundError` chỉ xuất hiện trên production | Dependency bị loại khỏi archive, thường là optional/provided/excluded | Kiểm tra `BOOT-INF/lib`, Maven `includeOptional`, dependency scope và runtimeClasspath. |
| `jarmode=layertools` không hoạt động | Boot 4.1 đã loại bỏ layertools | Dùng `-Djarmode=tools`. |
| `jarmode=tools` không được nhận diện | Tools JAR không được đóng gói hoặc archive không phải Boot executable JAR | Kiểm tra `includeTools`, `spring-boot-jarmode-tools` và manifest. |
| `list-layers` không có kết quả phù hợp | Không có `layers.idx` hoặc layers đã bị tắt | Kiểm tra `layers.enabled`, archive index và `extract --layers`. |
| Docker extraction thất bại | Dockerfile dùng archive có launch script, thiếu tools JAR hoặc sai artifact | Dùng executable archive bình thường, `includeTools=true`, chọn đúng file. |
| `LoaderImplementation.CLASSIC` không còn resolve | Boot 4 loại bỏ classic loader implementation | Xóa cấu hình CLASSIC khỏi Maven/Gradle. |
| JAR không chạy như shell script sau nâng Boot 4 | Embedded launch script đã bị loại bỏ | Dùng `java -jar` trong service/container hoặc Application Plugin. |
| Docker image không tìm thấy thư viện | COPY sai layer hoặc layer index/custom layer rules thay đổi | Chạy `list-layers`, kiểm tra extracted tree và COPY đủ từng layer. |
| App chạy trong IDE nhưng fail với `java -jar` | Classpath index, dependency order hoặc archive contents khác | Kiểm tra `classpath.idx`, manifest và dependency graph. |
| JAR build pass nhưng startup chậm | Nested JAR loading, unpack hoặc archive quá lớn | Đo startup; cân nhắc tools `extract` efficient layout và CDS/AOT. |
| Dependency xuất hiện local nhưng không có trong artifact | Scope/optional/default inclusion thay đổi hoặc đang chạy plain/executable archive khác | Kiểm tra effective POM và `jar tf`. |
| Pipeline publish nhầm file | Wildcard lấy `.original` hoặc `-plain.jar` | Pin artifact path/classifier; xác minh manifest trước publish. |
| `PropertiesLauncher` không nạp external lib | `LOADER_PATH`/`loader.path` sai hoặc quyền file không phù hợp | Kiểm tra environment, loader.properties và archive layout. |
| Library lỗi khi chạy nested JAR | Thư viện cần file JAR trên filesystem | Cấu hình `requiresUnpack` cho đúng dependency. |

### Trình tự chẩn đoán nhanh

1. Xác định file thực sự đang chạy bằng checksum và tên artifact.
2. Chạy `jar tf` để kiểm tra archive layout.
3. Đọc `META-INF/MANIFEST.MF`.
4. Kiểm tra `BOOT-INF/classes`, `BOOT-INF/lib`, `classpath.idx`, `layers.idx`.
5. Chạy `java -Djarmode=tools -jar app.jar list-layers`.
6. So sánh Maven/Gradle config giữa bản cũ và mới.
7. Chạy `java -jar` bằng cùng runtime JDK với production.
8. Build và smoke test Docker image cuối cùng, không chỉ kiểm tra builder stage.

## 21. Bài thực hành và tiêu chí hoàn thành

Thực hành trên một ứng dụng Spring Boot Maven hoặc Gradle:

1. Build artifact Boot 3.5 và lưu checksum.
2. Chạy `jar tf`; ghi lại các thư mục `BOOT-INF`/`WEB-INF`.
3. Đọc manifest, xác nhận `Main-Class` và `Start-Class`.
4. Kiểm tra `classpath.idx` và `layers.idx` nếu có.
5. Chạy `java -Djarmode=tools -jar app.jar list-layers`.
6. Chạy `extract --layers --destination extracted`; kiểm tra bốn layer mặc định.
7. Tìm và chuyển mọi `layertools` invocation sang `tools`.
8. Tìm cấu hình `LoaderImplementation.CLASSIC` và ghi nhận vị trí cần bỏ khi nâng Boot 4.
9. Tìm embedded launch script config và thay bằng service/container command.
10. Kiểm tra Maven `includeOptional`; xác định dependency runtime nào cần giữ khi đổi sang Boot 4.
11. Nâng Spring Boot Plugin cùng version Boot; build JAR/WAR mới.
12. So sánh manifest và archive entries giữa Boot 3.5 và Boot 4.
13. Build Docker image bằng multi-stage `tools extract`; xác nhận từng layer được COPY.
14. Chạy container, kiểm tra startup/health và một request quan trọng.
15. Kiểm tra artifact publish và checksum; xác nhận không chọn nhầm plain/original archive.
16. Viết migration note liệt kê các cấu hình đã đổi và lệnh kiểm chứng.

**Đạt yêu cầu khi:** bạn đọc được manifest và cấu trúc JAR/WAR; giải thích được vai trò của Boot Loader và `jarmode`; thay được `layertools` bằng `tools`; xử lý được classic loader, embedded launch script và optional dependency changes; Docker image dùng đúng layers; và artifact Boot 4 đã qua `java -jar`/container smoke test.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 Release Notes – tools jarmode và layertools deprecation](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes)
- [Spring Boot 3.5 – Nested JARs](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.5 – Launching Executable Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html)
- [Spring Boot 3.5 – Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 – Dockerfiles](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 4.0 Migration Guide – classic loader and launch scripts](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Boot 4.1 Release Notes – layertools removal](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes)
- [Spring Boot 4.1 – Launching Executable Jars](https://docs.spring.io/spring-boot/4.1/specification/executable-jar/launching.html)
- [Spring Boot 4.1 – Executable Jar Restrictions](https://docs.spring.io/spring-boot/4.1/specification/executable-jar/restrictions.html)
- [Spring Boot 4.1 – Maven Plugin Packaging](https://docs.spring.io/spring-boot/4.1/maven-plugin/packaging.html)
- [Spring Boot 4.1 – Gradle Plugin Packaging](https://docs.spring.io/spring-boot/4.1/gradle-plugin/packaging.html)
- [Spring Boot 4.1 – Dockerfiles](https://docs.spring.io/spring-boot/4.1/reference/packaging/container-images/dockerfiles.html)
