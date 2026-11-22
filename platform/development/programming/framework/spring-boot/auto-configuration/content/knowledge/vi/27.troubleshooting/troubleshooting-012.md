# Kết quả khác nhau giữa IDE, kiểm thử và JAR do classpath hoặc đóng gói

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Xử lý sự cố  
**Mục tiêu:** Chẩn đoán trường hợp ứng dụng chạy khác nhau khi bấm Run trong IDE, chạy test bằng Maven/Gradle hoặc khởi động từ JAR đã đóng gói. Bài tập trung vào dependency graph, classpath của từng giai đoạn, resource trùng tên, cấu hình theo profile/working directory và cấu trúc JAR thường so với Spring Boot executable JAR.

## 1. Vì sao cùng một source có thể cho kết quả khác nhau?

Một ứng dụng Java không chạy chỉ bằng source code. JVM cần một tập class, resource, dependency và cấu hình cụ thể ở từng lần chạy.

Ví dụ một auto-configuration có thể:

- Chạy tốt khi bấm Run trong IntelliJ.
- Pass toàn bộ unit test.
- Nhưng không tạo bean khi chạy `java -jar app.jar`.

Điều đó không nhất thiết có nghĩa logic Java sai. Ba môi trường có thể đang dùng ba tập đầu vào khác nhau:

| Môi trường | Những gì thường được dùng |
| --- | --- |
| IDE Run | Output directory của module, dependency do IDE import, JDK và Run Configuration riêng |
| Maven/Gradle test | Main output + test output + dependency test/runtime + test resources + test properties |
| JAR production | Class/resource đã đóng gói + dependency được publish hoặc lồng trong executable JAR + environment/profile lúc triển khai |

Một khác biệt nhỏ cũng có thể thay đổi kết quả:

- IDE đang dùng dependency version mới, nhưng JAR được build từ version cũ.
- Test có thư viện optional do `testImplementation` hoặc Maven `test` cung cấp, còn production runtime không có.
- `src/test/resources/application.yml` chứa property bật feature, nhưng JAR production không có property đó.
- Auto-configuration class có trong JAR nhưng file registration bị thiếu.
- Shaded JAR giữ một file `AutoConfiguration.imports` cuối cùng và làm mất entry từ dependency khác.
- Ứng dụng chạy từ thư mục khác nên Spring Boot nạp một `application.yml` bên ngoài JAR khác với file IDE đang dùng.

Muốn tìm nguyên nhân, trước hết phải xác định **JVM thực sự nhìn thấy class nào, resource nào, dependency version nào và property source nào** trong từng môi trường.

## 2. Phân biệt classpath với cấu hình Spring Environment

Hai vấn đề thường bị gọi chung là “classpath”, nhưng chúng là hai lớp khác nhau.

**Classpath** quyết định JVM có thể tìm thấy class và resource nào. Ví dụ:

- `com.acme.ReportClient` có nằm trong JAR dependency không?
- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` có được tìm thấy không?
- Có hai JAR cùng chứa `com/acme/ReportClient.class` không?
- Resource `application.yml` đến từ `target/classes`, `target/test-classes` hay JAR bên ngoài?

**Spring Environment** quyết định giá trị cấu hình nào có hiệu lực sau khi các nguồn cấu hình được nạp. Ví dụ:

- `acme.report.enabled` đến từ `application.yml`, environment variable hay command line?
- Profile `test`, `dev` hoặc `prod` nào đang active?
- Property trong `@DynamicPropertySource` có ghi đè file cấu hình không?
- File `./config/application.yml` bên ngoài JAR có ghi đè cấu hình đóng gói không?

Một class có thể được nạp đúng nhưng property lại khác. Ngược lại, property có thể đúng nhưng auto-configuration class không được tìm thấy.

Hãy chẩn đoán riêng hai câu hỏi:

1. JVM có nhìn thấy đúng class/resource không?
2. Spring có nhận đúng property và điều kiện để tạo bean không?

## 3. Ba classpath cần so sánh

### 3.1. IDE Run classpath

Khi chạy ứng dụng từ IDE, IDE thường lấy output directory của module và dependency graph mà nó đã import từ Maven hoặc Gradle.

Ví dụ IntelliJ có thể chạy với:

```text
module/out/production/classes
module/target/classes
module/build/classes/java/main
dependency-a.jar
dependency-b.jar
```

Đường dẫn cụ thể phụ thuộc IDE, build tool và cấu hình module. Run Configuration còn có thể chọn module classpath khác với module chứa main class.

Kiểm tra trong IDE:

- Project SDK và Module SDK có đúng JDK không?
- Run Configuration đang dùng đúng module/classpath chưa?
- Working directory là thư mục nào?
- Environment variables và VM options có giống môi trường production không?
- Active profiles có giống nhau không?
- IDE có vừa reload Maven/Gradle project sau khi thay dependency không?
- IDE dùng compiler/build riêng hay delegate build/run cho Maven/Gradle?
- Generated sources và annotation processing có được bật đúng không?

Nếu IDE dùng model dependency cũ, việc sửa `pom.xml` hoặc `build.gradle` chưa chắc cập nhật ngay classpath của Run Configuration. Reload project và kiểm tra dependency tree của build tool.

### 3.2. Test classpath

Test thường có nhiều dependency và resource hơn ứng dụng production.

Với Maven, test classpath thường gồm:

- `target/test-classes`
- `target/classes`
- Dependency scope `compile`, `runtime` và `test` theo quy tắc Maven.
- Dependency `provided` cũng có mặt trên compile/test classpath, dù không có trên runtime classpath production.

Với Gradle Java plugin, các configuration quan trọng gồm:

- `compileClasspath`: dependency để compile source chính.
- `runtimeClasspath`: dependency để chạy source chính.
- `testCompileClasspath`: dependency để compile test.
- `testRuntimeClasspath`: output của main/test cùng dependency cần để chạy test.

Một dependency có thể chỉ tồn tại trong test:

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

Hoặc:

```kotlin
dependencies {
    testImplementation("org.testcontainers:postgresql:1.20.4")
}
```

Nếu test chỉ pass nhờ một dependency test-only, ứng dụng production sẽ không tự có dependency đó.

Test resources cũng có thể làm kết quả khác:

```text
src/main/resources/application.yml
src/test/resources/application.yml
```

Test có thể nạp property, profile hoặc mock configuration riêng. Ngoài file resource, các annotation sau cũng làm thay đổi Environment:

```java
@SpringBootTest(properties = "acme.report.enabled=true")
@ActiveProfiles("test")
@TestPropertySource(properties = "acme.report.mode=test")
```

`@DynamicPropertySource` cũng có thể cung cấp giá trị trong test. Vì vậy, khi test pass nhưng JAR không hoạt động, hãy so sánh property source thực tế và dependency test với runtime production.

### 3.3. Runtime classpath của JAR

JAR thường và Spring Boot executable JAR có cấu trúc khác nhau.

Một JAR library thông thường có thể chứa:

```text
acme-report-autoconfigure.jar
├── com/acme/report/ReportProperties.class
├── com/acme/report/autoconfigure/ReportAutoConfiguration.class
└── META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Dependency của library thường được tải riêng theo POM hoặc Gradle Module Metadata. Chúng không tự động được nhúng vào JAR library.

Một Spring Boot executable JAR thường có cấu trúc:

```text
application.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/acme/Application.class
    │   └── application.yml
    └── lib/
        ├── spring-boot-....jar
        ├── acme-report-autoconfigure-....jar
        └── jackson-databind-....jar
```

Application class nằm trong `BOOT-INF/classes`; dependency nằm trong `BOOT-INF/lib`. Spring Boot Loader biết cách đọc nested JAR.

Vì vậy:

- Chạy executable Boot JAR bằng `java -jar application.jar`.
- Không coi executable Boot JAR như một JAR thường rồi chỉ đặt nó vào `java -cp application.jar`.
- JAR library thường không phải executable application và không nhất thiết có main manifest hoặc dependency đóng gói.

Tài liệu Spring Boot mô tả rõ cấu trúc nested JAR và cách Loader đọc `BOOT-INF/classes`/`BOOT-INF/lib`.

## 4. Maven: scope làm thay đổi classpath nào?

Maven dependency scope quyết định dependency xuất hiện trong classpath nào và được truyền tiếp ra sao.

| Scope | Compile main | Runtime main | Test | Consumer |
| --- | --- | --- | --- | --- |
| `compile` | Có | Có | Có | Được truyền tiếp |
| `provided` | Có | Không | Có | Không truyền như dependency thông thường |
| `runtime` | Không | Có | Có | Được truyền ở runtime |
| `test` | Không | Không | Có | Không truyền |
| `system` | Có | Có | Có | Dựa vào đường dẫn local, không khuyến nghị |
| `import` | Không phải dependency classpath | Không | Không | Nhập dependency management từ BOM |

Ví dụ:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-core</artifactId>
        <version>1.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Một số trường hợp thường gây chênh lệch:

- Code import một class nhưng dependency chỉ có scope `runtime`: compile main có thể thất bại.
- Code cần class lúc chạy nhưng dependency chỉ có scope `provided`: IDE/test có thể chạy được, production runtime thiếu class nếu container không cung cấp.
- Test dùng thư viện ở scope `test`: test pass, JAR production không chứa dependency đó.
- Dependency được đánh dấu `optional`: module hiện tại vẫn dùng dependency theo scope của nó, nhưng consumer không tự nhận dependency transitive đó.
- Chỉ khai báo artifact trong `dependencyManagement`: Maven quản lý version/configuration, nhưng chưa thêm artifact vào classpath nếu không khai báo trong `dependencies`.

Kiểm tra dependency tree:

```bash
mvn dependency:tree
```

Chỉ xem dependency runtime:

```bash
mvn dependency:tree -Dscope=runtime
```

Tìm nguồn của một thư viện cụ thể:

```bash
mvn dependency:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Kiểm tra POM sau khi kế thừa parent và profile:

```bash
mvn help:effective-pom
```

Nếu dependency có nhiều version, đọc dependency tree để xem version được Maven chọn và nhánh nào đưa nó vào graph. Không dựa vào danh sách dependency trong IDE để kết luận version của JAR cuối.

## 5. Gradle: phân biệt dependency declaration và resolved classpath

Với Java plugin hoặc Java Library plugin, dependency thường được khai báo bằng configuration:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure:3.3.13")
    runtimeOnly("org.postgresql:postgresql:42.7.5")
    testImplementation("org.springframework.boot:spring-boot-starter-test:3.3.13")
}
```

Các configuration dùng để khai báo dependency khác với configuration được resolve thành classpath:

| Configuration | Vai trò |
| --- | --- |
| `implementation` | Dependency compile/runtime nội bộ của module |
| `api` | Dependency được công bố trên API của Java library |
| `compileOnly` | Chỉ có trong compile classpath của module |
| `runtimeOnly` | Chỉ có trong runtime classpath |
| `testImplementation` | Dependency compile/runtime cho test |
| `testRuntimeOnly` | Dependency chỉ cần khi chạy test |
| `compileClasspath` | Tập artifact thực tế dùng để compile main |
| `runtimeClasspath` | Tập artifact thực tế dùng để chạy main |
| `testCompileClasspath` | Tập artifact dùng để compile test |
| `testRuntimeClasspath` | Tập artifact dùng để chạy test |

Xem dependency của runtime:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Xem dependency test:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Tìm lý do một version được chọn:

```bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
```

Nếu dependency chỉ xuất hiện trong `testRuntimeClasspath`, đừng giả định nó có trong ứng dụng đã đóng gói. Nếu dependency là `compileOnly`, code có thể compile nhưng runtime cần một nguồn cung cấp khác.

Với Java Library, `api` và `implementation` cũng ảnh hưởng metadata publication của consumer. Khi lỗi chỉ xuất hiện ở một ứng dụng phụ thuộc vào library, hãy kiểm tra cả `runtimeElements`/`apiElements` hoặc POM/Gradle Module Metadata đã publish.

## 6. Resource có thể khác nhau dù classpath nhìn có vẻ đúng

Classpath không chỉ chứa `.class`; nó còn chứa resource như:

- `application.yml` và `application.properties`.
- `META-INF/spring.factories`.
- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- `META-INF/spring-configuration-metadata.json`.
- `META-INF/services/...`.
- `logback-spring.xml`.
- File schema, template, migration SQL hoặc message bundle.

Hai JAR có thể cùng chứa resource cùng đường dẫn. ClassLoader có thể trả về một resource khi gọi `getResource`, nhưng `getResources` cho phép liệt kê tất cả resource trùng tên.

Ví dụ:

```java
Enumeration<URL> urls = Thread.currentThread()
        .getContextClassLoader()
        .getResources(
                "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports"
        );

while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

Nếu có nhiều JAR cùng cung cấp imports file, phải xác định công cụ đóng gói có giữ và gộp đầy đủ entry hay không.

### 6.1. Auto-configuration class có trong JAR nhưng không được nạp

Đối với Spring Boot 2.7 trở lên, kiểm tra:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng là một fully qualified class name. Đối với Boot 2.6 và cũ hơn, kiểm tra key `EnableAutoConfiguration` trong `META-INF/spring.factories`.

Boot 2.7 hỗ trợ cả hai cơ chế; Boot 3 không còn dùng key `EnableAutoConfiguration` cũ để đăng ký auto-configuration.

Một JAR có class:

```text
com/acme/report/autoconfigure/ReportAutoConfiguration.class
```

nhưng thiếu file imports tương ứng vẫn chưa đủ để Boot tự khám phá class đó.

Nếu dùng Maven Shade hoặc Gradle Shadow, nhiều dependency có thể cùng chứa imports file. Plugin cần append/merge resource để giữ đủ entry. Với Maven Shade, ví dụ:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
```

Với Gradle Shadow:

```groovy
tasks.withType(com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
}
```

Nếu còn giữ `spring.factories`, cũng phải merge file properties đúng cách. Kiểm tra artifact cuối sau khi shade; kiểm tra riêng JAR dependency trước khi shade chưa đủ.

### 6.2. IDE không autocomplete nhưng runtime vẫn hoạt động

IDE có thể cần configuration metadata để gợi ý property. File thường nằm tại:

```text
META-INF/spring-configuration-metadata.json
```

Metadata được sinh bởi `spring-boot-configuration-processor` hoặc cung cấp thủ công. Nếu file không được đóng gói, IDE có thể không gợi ý key dù `@ConfigurationProperties` và Binder vẫn hoạt động ở runtime.

Đây là lỗi trải nghiệm tooling; hãy kiểm tra metadata trong JAR và IDE indexing. Đừng kết luận auto-configuration runtime hỏng chỉ vì IDE báo không resolve property.

## 7. Phân biệt JAR thường, `jar` và `bootJar`

Trong dự án Spring Boot, hai artifact thường bị nhầm:

- `jar`: JAR Java thông thường, chứa class/resource của module.
- `bootJar`: executable JAR của ứng dụng Spring Boot, chứa Spring Boot Loader và dependency nested trong `BOOT-INF/lib`.

Với Gradle, task `bootRun` chạy ứng dụng từ classpath của build; nó không phải phép thử cuối cùng cho cấu trúc executable JAR. Tương tự, chạy từ IDE thường dùng output directory và dependency đã resolve, không đọc nested JAR theo cách `java -jar` làm.

Với Maven, `spring-boot-maven-plugin` có goal `repackage` để tạo executable archive. Nếu plugin không chạy hoặc bị cấu hình skip, artifact có thể là JAR thường dù source và test đều pass.

Ví dụ plugin Maven:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Với Gradle Spring Boot plugin, build executable artifact bằng:

```bash
./gradlew clean bootJar
```

Nếu module là thư viện auto-configuration/starter, thông thường cần publish JAR library chứa class, resource registration và metadata; không biến module thư viện thành executable Boot JAR chỉ để đóng gói dependency.

## 8. Kiểm tra nội dung artifact thật sự được chạy

Sau khi build, kiểm tra đúng file JAR mà môi trường deploy sử dụng.

Với Maven:

```bash
mvn clean package
jar tf target/acme-report-app-1.0.0.jar
```

Tìm các phần quan trọng trên Linux/macOS:

```bash
jar tf target/acme-report-app-1.0.0.jar |
    grep -E 'BOOT-INF/(classes|lib)/|AutoConfiguration.imports|spring.factories|spring-configuration-metadata.json'
```

Trên Windows PowerShell:

```powershell
jar tf target/acme-report-app-1.0.0.jar |
    Select-String 'BOOT-INF/(classes|lib)/|AutoConfiguration.imports|spring.factories|spring-configuration-metadata.json'
```

Đọc manifest:

```bash
unzip -p target/acme-report-app-1.0.0.jar META-INF/MANIFEST.MF
```

Với executable Boot JAR, cần thấy `BOOT-INF/classes`, `BOOT-INF/lib` và manifest có thông tin launcher/start class phù hợp.

Với Gradle:

```bash
./gradlew clean bootJar
jar tf build/libs/acme-report-app-1.0.0.jar
```

Nếu cần đọc một resource trong JAR:

```bash
unzip -p target/acme-report-app-1.0.0.jar \
    BOOT-INF/classes/application.yml
```

Đường dẫn trên chỉ đúng khi resource nằm ở root classpath của ứng dụng và được đóng gói vào `BOOT-INF/classes`. Nếu resource đến từ dependency JAR nested, cần xác định dependency tương ứng trong `BOOT-INF/lib` và kiểm tra JAR đó riêng sau khi trích xuất.

**Luôn chạy đúng artifact vừa kiểm tra:**

```bash
java -jar target/acme-report-app-1.0.0.jar
```

Nếu production dùng một đường dẫn artifact khác, hãy kiểm tra checksum/version hoặc tên build được deploy. Chạy file vừa build ở local không chứng minh server đang chạy đúng file đó.

## 9. Dùng JVM để tìm nguồn class và resource

Khi nghi ngờ class bị nạp từ một JAR cũ hoặc dependency trùng lặp, có thể in ra nguồn class.

Ví dụ Java 17:

```java
package demo;

import java.io.IOException;
import java.net.URL;
import java.security.CodeSource;
import java.util.Enumeration;

public final class ClasspathProbe {

    private ClasspathProbe() {
    }

    public static void main(String[] args) throws IOException {
        describe(ClasspathProbe.class);

        for (String resourceName : args) {
            listResources(resourceName);
        }
    }

    private static void describe(Class<?> type) {
        CodeSource source = type.getProtectionDomain().getCodeSource();
        URL classResource = type.getResource(type.getSimpleName() + ".class");

        System.out.println("class=" + type.getName());
        System.out.println("classLoader=" + type.getClassLoader());
        System.out.println("classResource=" + classResource);
        System.out.println("codeSource="
                + (source == null ? "<unavailable>" : source.getLocation()));
    }

    private static void listResources(String resourceName)
            throws IOException {

        ClassLoader loader =
                Thread.currentThread().getContextClassLoader();

        if (loader == null) {
            loader = ClasspathProbe.class.getClassLoader();
        }

        System.out.println("resource=" + resourceName);

        Enumeration<URL> resources = loader.getResources(resourceName);
        int count = 0;

        while (resources.hasMoreElements()) {
            count++;
            System.out.println("  [" + count + "] " + resources.nextElement());
        }

        if (count == 0) {
            System.out.println("  <not found>");
        }
    }
}
```

Compile và chạy:

```bash
javac -d out src/main/java/demo/ClasspathProbe.java
java -cp out demo.ClasspathProbe \
    META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports \
    application.yml
```

Trong ứng dụng thật, gọi `describe(ReportService.class)` để xem class đang được nạp từ đâu. Gọi `listResources(...)` để liệt kê mọi bản resource cùng tên.

Một số lưu ý:

- `CodeSource` có thể `null` với class do bootstrap/platform classloader hoặc khi môi trường không cung cấp thông tin nguồn.
- Đường dẫn hiển thị trong executable Boot JAR có thể là URL nested JAR, không giống đường dẫn JAR thông thường.
- Nếu có nhiều resource cùng tên, phải kiểm tra thứ tự và nội dung từng URL.
- Probe chỉ cho biết nguồn class/resource; nó không giải thích property nào thắng trong Spring Environment.

Trên Java 17, có thể bật log class loading:

```bash
java -Xlog:class+load=info -jar target/acme-report-app-1.0.0.jar
```

Tìm tên class trong log để thấy JVM nạp nó từ nguồn nào. Log có thể rất dài; lọc theo package hoặc class đang nghi ngờ.

## 10. Kiểm tra JDK và bytecode

IDE có thể dùng một JDK, Maven/Gradle chạy bằng JDK khác, còn production lại dùng JRE/JDK khác.

So sánh:

```bash
java -version
javac -version
mvn -version
./gradlew --version
```

Đối chiếu:

- JDK mà IDE Project SDK sử dụng.
- JDK chạy Maven/Gradle daemon.
- `maven.compiler.release` hoặc Gradle Java toolchain.
- JDK runtime của container/server.
- Phiên bản bytecode của thư viện nội bộ và dependency.

Nếu code được compile bằng JDK mới nhưng deploy trên runtime cũ, lỗi có thể là:

```text
UnsupportedClassVersionError
```

Nếu class có mặt nhưng API không tương thích, có thể gặp:

```text
NoSuchMethodError
NoClassDefFoundError
AbstractMethodError
```

Các lỗi này thường chỉ ra binary/dependency mismatch hoặc classpath khác nhau. Đọc class và dependency version thực tế trước khi sửa source.

Với Maven, cấu hình `maven.compiler.release` hoặc `<release>` để xác định API/bytecode mục tiêu. Với Gradle, dùng Java toolchain để compiler và test runtime có cấu hình rõ ràng.

## 11. Cấu hình ngoài JAR và working directory

Một nguyên nhân rất phổ biến là cùng một JAR nhưng chạy từ hai thư mục khác nhau.

Spring Boot tìm `application.properties`/`application.yaml` ở các vị trí mặc định, gồm classpath root, classpath `/config`, thư mục hiện tại và thư mục `config/` bên ngoài. File bên ngoài có thể ghi đè file được đóng gói.

Ví dụ:

```text
deploy/
├── application.jar
└── config/
    └── application-prod.yml
```

Chạy từ thư mục deploy có thể nạp `config/application-prod.yml`. Nếu IDE chạy từ thư mục project với một file cấu hình khác, kết quả có thể khác dù cùng source.

Kiểm tra:

```java
System.out.println("user.dir=" + System.getProperty("user.dir"));
```

So sánh các giá trị:

- Working directory.
- `SPRING_PROFILES_ACTIVE`.
- JVM system properties (`-D...`).
- Environment variables.
- Command-line arguments (`--key=value`).
- `spring.config.location`, `spring.config.additional-location`.
- `spring.config.import`.

Thứ tự property source của Spring Boot cho phép environment variables, system properties, command line và test-specific properties ghi đè các giá trị từ file. Vì vậy, chỉ mở `application.yml` không đủ để kết luận giá trị cuối cùng của Environment.

Để tái hiện chính xác:

```bash
java -jar target/acme-report-app-1.0.0.jar \
    --spring.profiles.active=prod \
    --acme.report.enabled=true
```

Dùng đúng profile và argument mà môi trường thật sử dụng. Nếu cần bổ sung file cấu hình ngoài JAR, có thể truyền `spring.config.additional-location`; nếu dùng `spring.config.location`, nhớ rằng nó thay thế vị trí mặc định.

## 12. Test có thể vô tình che lỗi production

### 12.1. Test dependency làm optional library luôn có mặt

Giả sử auto-configuration có:

```java
@ConditionalOnClass(name = "com.vendor.client.VendorClient")
```

Nếu test starter kéo `com.vendor:vendor-client` vào test classpath, condition luôn match. Nhưng consumer production không khai báo vendor client có thể không có bean tương ứng.

Dùng `FilteredClassLoader` để mô phỏng classpath thiếu dependency:

```java
this.contextRunner
        .withClassLoader(new FilteredClassLoader("com.vendor.client"))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean("vendorService");
        });
```

Bài test này kiểm tra cả condition và việc ứng dụng không lỗi linkage khi optional class vắng mặt.

### 12.2. Test property khác production property

Một test có thể bật feature qua:

```java
@SpringBootTest(properties = "acme.report.enabled=true")
```

Trong khi production không có property này. Nếu condition mặc định `matchIfMissing = false`, auto-configuration sẽ không tạo bean ở production.

Hãy test ba trạng thái theo contract:

- Property thiếu.
- Property `false`.
- Property `true`.

Với test dùng profile, xác nhận `@ActiveProfiles` và file profile-specific đúng như dự kiến.

### 12.3. Test resource che resource production

Kiểm tra xem `src/test/resources` có chứa file cùng tên với `src/main/resources` không. Những resource này có thể làm test nạp cấu hình khác.

Nếu cần kiểm tra registration file, có thể viết test:

```java
@Test
void autoConfigurationImportsResourceIsVisible() throws IOException {
    String resource =
            "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

    Enumeration<URL> urls = getClass()
            .getClassLoader()
            .getResources(resource);

    assertThat(Collections.list(urls)).isNotEmpty();
}
```

Test trên xác nhận resource có trên test classpath. Nó vẫn chưa chứng minh artifact cuối sau Shade/Shadow chứa đủ nội dung. Hãy kết hợp với kiểm tra JAR cuối cùng và một consumer smoke test.

## 13. Chẩn đoán bằng Condition Evaluation Report

Nếu class và resource đã có nhưng bean vẫn không xuất hiện, kiểm tra condition.

Chạy:

```bash
java -jar target/acme-report-app-1.0.0.jar --debug
```

Spring Boot ghi Condition Evaluation Report, giúp xác định:

- Auto-configuration nào match/no-match.
- `@ConditionalOnClass` có tìm thấy class không.
- `@ConditionalOnProperty` nhận giá trị nào.
- `@ConditionalOnMissingBean` có nhìn thấy bean của ứng dụng không.
- Condition nào khiến bean method hoặc configuration class bị bỏ qua.

Nếu ứng dụng dùng Actuator và expose endpoint phù hợp, `/actuator/conditions` có thể cung cấp báo cáo dạng JSON. Hãy bảo vệ endpoint theo chính sách vận hành của ứng dụng.

Trong test, có thể dùng `ConditionEvaluationReportLoggingListener` với `ApplicationContextRunner` để in lý do match/no-match. Dùng report để tìm nguyên nhân, sau đó viết assertion kiểm tra bean thực tế.

Không kết luận rằng auto-configuration registration sai chỉ vì bean không xuất hiện. Class có thể đã được import nhưng condition không match; hai tình huống cần cách sửa khác nhau.

## 14. Quy trình so sánh IDE, test và JAR

Khi tái hiện lỗi, làm theo cùng một thứ tự cho cả ba môi trường:

### Bước 1 — Ghi nhận runtime

Thu thập:

```bash
java -version
mvn -version
./gradlew --version
```

Ghi lại JDK, build tool, profile, working directory, JVM arguments và environment variables.

### Bước 2 — Xác nhận dependency graph

Maven:

```bash
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dscope=test
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

So sánh version thực tế, đặc biệt dependency Spring Boot, Spring Framework và thư viện optional.

### Bước 3 — Xác nhận nguồn class/resource

Dùng `ClasspathProbe`, `ClassLoader.getResources(...)` hoặc Java class loading log để biết class/resource nào được nạp từ đâu.

Kiểm tra resource registration, metadata và cấu hình có trùng tên giữa nhiều JAR hay không.

### Bước 4 — Build sạch artifact

Maven:

```bash
mvn clean verify
```

Gradle:

```bash
./gradlew clean test bootJar
```

Không dùng output cũ từ lần build trước. Với dependency snapshot hoặc cache nghi ngờ, chỉ refresh khi đã xác định cần lấy lại artifact:

```bash
mvn -U clean verify
./gradlew --refresh-dependencies clean test bootJar
```

### Bước 5 — Kiểm tra nội dung JAR

```bash
jar tf target/acme-report-app-1.0.0.jar
```

Xác nhận class, registration file, metadata và nested dependency đúng như mong đợi. Nếu dùng shaded JAR, kiểm tra artifact sau khi shade.

### Bước 6 — Chạy chính artifact đó

```bash
java -jar target/acme-report-app-1.0.0.jar --debug
```

Dùng cùng profile, environment variables, command-line properties và external config như môi trường thật.

### Bước 7 — So sánh hành vi

Ghi lại:

- Bean có xuất hiện không và implementation nào được inject.
- Condition report cho biết lý do match/no-match nào.
- Property cuối cùng và nguồn của nó.
- Class/resource URL thực tế.
- Version dependency được chọn.
- Log class loading nếu có lỗi linkage.

Khi mọi đầu vào đã tương đương mà kết quả vẫn khác, lúc đó mới xem xét khác biệt lifecycle, classloader hoặc hành vi phụ thuộc phiên bản framework.

## 15. Bảng triệu chứng và hướng kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Bước xác minh |
| --- | --- | --- |
| IDE chạy, JAR báo `ClassNotFoundException` | Dependency chỉ có trong IDE/module classpath, không có trong runtime artifact | Dependency tree runtime và `BOOT-INF/lib` |
| Test pass, production thiếu bean | Test dependency/property/profile có thêm điều kiện cần thiết | So sánh `testRuntimeClasspath` với `runtimeClasspath`; xem Condition Report |
| JAR có class nhưng auto-configuration không chạy | Thiếu hoặc sai registration resource | `jar tf`, đọc `AutoConfiguration.imports`/`spring.factories` |
| Chỉ shaded JAR bị thiếu bean | Resource registration bị ghi đè hoặc không merge | So sánh resource trước/sau Shade/Shadow |
| IDE không autocomplete property, runtime vẫn bind | Configuration metadata thiếu hoặc IDE chưa index dependency mới | Kiểm tra `spring-configuration-metadata.json`, reload IDE |
| IDE và JAR đọc giá trị khác | Working directory, profile hoặc external config khác nhau | `user.dir`, active profiles, property sources |
| Chạy `bootRun` pass nhưng `java -jar` fail | Khác biệt giữa resolved classpath và executable archive/packaging | Build `bootJar`, kiểm tra manifest và nested libs, chạy đúng JAR |
| `NoSuchMethodError` chỉ ở production | Version dependency được resolve khác hoặc class cũ được nạp | Dependency insight/tree và class origin |
| `UnsupportedClassVersionError` | Runtime JDK cũ hơn bytecode | `java -version`, compiler release/toolchain |
| Test thấy hai bean nhưng JAR chỉ có một | Test classpath có thêm config/implementation | So sánh resource/classpath và condition report |
| Resource xuất hiện nhiều lần | Nhiều JAR cùng chứa cùng đường dẫn | `ClassLoader.getResources(...)` |
| JAR local đúng nhưng server vẫn sai | Server chạy artifact cũ hoặc cấu hình ngoài khác | Xác minh version/checksum, startup path và environment |

## 16. Những lỗi thường gặp

**Lỗi 1 — Chỉ kiểm tra `compileClasspath`.**  
Code compile được chưa chứng minh dependency có trong runtime. Kiểm tra runtime classpath và artifact đã đóng gói.

**Lỗi 2 — Tin rằng test pass là production classpath đúng.**  
Test có thêm dependency, resource và property. So sánh test runtime với runtime production.

**Lỗi 3 — Cho rằng dependency trong POM đã nằm trong JAR library.**  
POM mô tả dependency graph; JAR library thường không nhúng dependency. Executable Boot JAR có cấu trúc đóng gói riêng.

**Lỗi 4 — Dùng `java -cp app.jar` để chạy executable Boot JAR.**  
Nested JAR cần Spring Boot Loader. Dùng `java -jar app.jar`.

**Lỗi 5 — Chỉ kiểm tra class `.class`.**  
Auto-configuration cần registration resource; IDE có thể cần metadata; ServiceLoader cần file services. Kiểm tra toàn bộ resource contract.

**Lỗi 6 — Chỉ kiểm tra JAR trước khi shade.**  
Shade/Shadow có thể làm mất hoặc ghi đè resource. Kiểm tra artifact cuối cùng.

**Lỗi 7 — Đổ lỗi cho IDE cache ngay khi kết quả khác nhau.**  
Trước tiên xác nhận module classpath, JDK, working directory, profiles và dependency model IDE đã import.

**Lỗi 8 — Bắt lỗi linkage rồi âm thầm bỏ qua.**  
`NoClassDefFoundError` hoặc `NoSuchMethodError` thường chỉ ra dependency mismatch. Giữ root cause và sửa graph/classpath.

**Lỗi 9 — Chỉ so sánh file `application.yml`.**  
Giá trị cuối còn chịu ảnh hưởng của profile, environment variables, system properties, command line, test annotations và file ngoài JAR.

**Lỗi 10 — Dùng `bootRun` thay cho kiểm tra executable JAR.**  
`bootRun` chạy từ classpath của build. Hãy build `bootJar`/repackage rồi chạy `java -jar`.

**Lỗi 11 — Không clean giữa các lần build.**  
Class/resource cũ có thể còn sót trong output directory. Chạy `clean` khi kiểm tra lỗi packaging hoặc thay đổi dependency.

**Lỗi 12 — Sửa condition để che lỗi đóng gói.**  
Nếu class/resource không được nạp, sửa `@ConditionalOnProperty` không khắc phục registration hoặc classpath. Xác định đúng lớp lỗi trước khi sửa.

## 17. Checklist trước khi phát hành

- [ ] IDE, Maven/Gradle và production dùng JDK phù hợp với bytecode mục tiêu.
- [ ] Run Configuration chọn đúng module và working directory.
- [ ] Dependency trực tiếp được khai báo đúng scope/configuration.
- [ ] Runtime classpath có đủ dependency cần thiết.
- [ ] Test-only dependency không bị nhầm là production dependency.
- [ ] Test resources và test properties không che lỗi production.
- [ ] Optional dependency được kiểm tra cả khi có và khi vắng mặt.
- [ ] Auto-configuration registration resource có trong đúng module/JAR.
- [ ] Configuration metadata có trong artifact nếu cần IDE completion.
- [ ] Resource trùng tên được kiểm tra và merge đúng khi shade.
- [ ] Plain JAR và executable Boot JAR được phân biệt.
- [ ] `jar tf` xác nhận nội dung artifact cuối.
- [ ] Artifact được chạy thử bằng `java -jar`.
- [ ] Profile, external config, environment variables và command line được ghi nhận.
- [ ] Condition Evaluation Report được kiểm tra khi bean match/no-match khác mong đợi.
- [ ] CI lưu dependency tree và test report cho build quan trọng.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao ứng dụng chạy trong IDE nhưng JAR báo thiếu class?  
**Đáp án:** IDE có thể thêm dependency vào module classpath, trong khi runtime artifact không có dependency tương ứng. Kiểm tra runtime dependency graph và nội dung JAR.

**Câu 2.** Vì sao test pass nhưng bean auto-configuration không xuất hiện khi production chạy?  
**Đáp án:** Test có thể dùng test-only dependency, test resources, profile hoặc property riêng. So sánh test runtime classpath và property source với production.

**Câu 3.** `mvn dependency:tree -Dscope=runtime` giúp kiểm tra điều gì?  
**Đáp án:** Dependency được Maven đưa vào runtime graph và version được chọn cho ứng dụng.

**Câu 4.** Gradle configuration nào mô tả dependency graph khi chạy main application?  
**Đáp án:** `runtimeClasspath`; test dùng `testRuntimeClasspath`.

**Câu 5.** Vì sao executable Boot JAR cần `java -jar`?  
**Đáp án:** Dependency nằm trong nested `BOOT-INF/lib`; Spring Boot Loader đọc cấu trúc nested JAR. `java -cp` thông thường không tự mở nested JAR.

**Câu 6.** Class có trong JAR nhưng auto-configuration không được nạp. Cần kiểm tra gì?  
**Đáp án:** Registration resource đúng phiên bản Boot, đường dẫn imports/factories và việc resource có bị mất khi shade hay không.

**Câu 7.** Vì sao `getResource(...)` chưa đủ khi nghi có resource trùng tên?  
**Đáp án:** Nó chỉ trả về một URL phù hợp. `getResources(...)` liệt kê tất cả resource cùng đường dẫn để phát hiện bản trùng.

**Câu 8.** `bootRun` pass nhưng `java -jar` fail gợi ý điều gì?  
**Đáp án:** Build classpath và executable archive có thể khác nhau; cần kiểm tra packaging, nested dependencies, manifest và resource trong JAR cuối.

**Câu 9.** Vì sao cùng JAR nhưng chạy từ hai thư mục khác nhau có thể đọc cấu hình khác?  
**Đáp án:** Spring Boot tìm external config từ working directory và các vị trí `config/`; file ngoài JAR có thể ghi đè file đóng gói.

**Câu 10.** `NoSuchMethodError` thường gợi ý điều gì?  
**Đáp án:** JVM đã nạp một version class không có method mà code gọi; kiểm tra dependency mediation, class origin và version runtime.

## 19. Nguyên tắc cần nhớ

- IDE Run, test runtime và executable JAR có thể dùng classpath khác nhau.
- Classpath quyết định class/resource được tìm thấy; Spring Environment quyết định giá trị cấu hình cuối.
- Maven scopes và Gradle configurations làm thay đổi dependency graph theo compile, runtime và test.
- Test resources, test dependencies, profiles và test properties có thể che lỗi production.
- JAR library thường không nhúng dependency; executable Boot JAR dùng `BOOT-INF/classes` và `BOOT-INF/lib`.
- Chạy executable Boot JAR bằng `java -jar`, sau đó kiểm tra chính artifact đó.
- Kiểm tra resource registration, metadata và file services cùng với `.class`.
- Dùng `ClassLoader.getResources`, class origin và `-Xlog:class+load=info` để tìm nguồn thực tế.
- So sánh working directory, active profile, environment variables và external config.
- Đọc dependency tree và Condition Evaluation Report trước khi sửa logic condition.

### Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Spring Boot 3.3 — Nested JARs and Executable Archive Structure](https://docs.spring.io/spring-boot/3.3/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 — Creating and Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
