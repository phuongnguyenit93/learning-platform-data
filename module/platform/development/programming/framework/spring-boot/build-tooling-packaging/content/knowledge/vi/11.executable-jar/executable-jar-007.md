# Quản lý archive thường, archive thực thi và hậu tố plain hoặc original

## Mục tiêu và vấn đề cần giải quyết

Trong một dự án Spring Boot, sau khi chạy `./mvnw package` hoặc `./gradlew build`, thư mục `target/` hay `build/libs/` đôi khi xuất hiện **nhiều file cùng tên gốc**:

```text
# Ví dụ Gradle
demo-0.0.1-SNAPSHOT.jar
demo-0.0.1-SNAPSHOT-plain.jar

# Ví dụ Maven với repackage mặc định
demo-0.0.1-SNAPSHOT.jar
demo-0.0.1-SNAPSHOT.jar.original

# Ví dụ Maven nếu cấu hình classifier "exec"
demo-0.0.1-SNAPSHOT.jar
demo-0.0.1-SNAPSHOT-exec.jar
```

Các file này không phải bản sao tùy ý. Chúng thể hiện **hai loại sản phẩm khác nhau**: archive Java thông thường và archive Spring Boot thực thi. Chọn nhầm file có thể làm `java -jar` không chạy, ứng dụng thiếu thư viện runtime, một module khác không thể import lớp Java, hoặc pipeline đẩy nhầm artifact lên kho/phát hành.

Sau bài học, bạn có thể:

1. Giải thích **plain JAR/WAR** và **Spring Boot executable JAR/WAR**, cấu trúc bên trong và mục đích sử dụng.
2. Đọc đúng quy ước **Gradle `jar`/`bootJar`, `war`/`bootWar`** và hậu tố `-plain.jar`/`-plain.war`.
3. Giải thích **Maven `spring-boot:repackage`**, lý do có `.jar.original` hoặc `.war.original` và ý nghĩa của cấu hình `<classifier>exec</classifier>`, `<attach>`.
4. Cấu hình tên archive/classifier an toàn, không để hai task cùng ghi vào một đường dẫn, không vô hiệu hóa archive thông thường khi vẫn cần nó.
5. Dùng `jar tf`, manifest và lệnh chạy thật để **xác định chính xác** artifact nào chạy độc lập, artifact nào dùng làm dependency, và artifact nào được stage deploy chọn.
6. Viết kiểm tra đơn giản trong CI để ngăn nhầm `plain`, `original`, JAR từ module khác hoặc file build cũ.

**Phạm vi:** ứng dụng Spring Boot sử dụng Maven hoặc Gradle, chủ yếu JAR thực thi; WAR được đưa vào vì quy tắc plain/bootWar và original cũng áp dụng tương tự. Ví dụ dùng **Spring Boot 3.3.13, Java 17** và một Gradle Wrapper tương thích; đây là phiên bản minh họa, không phải phiên bản buộc mọi dự án phải dùng. Cần đối chiếu đúng tài liệu plugin nếu dùng Spring Boot 4.x hay Gradle/Maven khác.

## 1. Hai dạng archive: nhìn giống nhau bên ngoài, khác công dụng

### 1.1 Archive Java thông thường (plain)

Một JAR thông thường do Gradle `jar` hoặc Maven Jar Plugin tạo chủ yếu chứa **class và resources của module** theo layout package Java. Ví dụ:

```text
demo-0.0.1-SNAPSHOT-plain.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       └── demo/
│           └── DemoApplication.class
└── application.properties                 (nếu có)
```

Đây là **cấu trúc minh họa**, không phải cây file duy nhất mà mọi JAR đều phải có. Trong một plain JAR kiểu phổ biến:

- Class được đặt trực tiếp theo package, ví dụ `com/example/demo/DemoApplication.class` ở gốc archive.
- JAR **không tự mang tất cả dependency runtime** dưới dạng nested JAR chỉ vì nó được đóng bằng `jar`. Một số plugin khác có thể tạo fat/shaded JAR theo cách riêng.
- Có thể được Maven/Gradle project khác tiêu thụ như dependency bình thường, vì Java classloader của ứng dụng tiêu thụ hiểu class ở root.
- Thường **không đủ để chạy độc lập** bằng `java -jar` trong Spring Boot app có dependency. Tuy nhiên, không có quy tắc "plain JAR tuyệt đối không bao giờ chạy được": một plain JAR có manifest và classpath được chuẩn bị thích hợp, hoặc một chương trình chỉ dùng JDK, vẫn có thể chạy. Từ `plain` mô tả **cách đóng gói**, không phải phép kiểm tra máy móc mọi khả năng thực thi.

Một module thư viện Java thường cần loại này để chia sẻ API/class cho module khác; không phải mọi module trong repository đều phải dùng Spring Boot executable packaging.

### 1.2 Spring Boot executable JAR

Một Spring Boot executable JAR do Gradle `bootJar` hoặc Maven `spring-boot:repackage` tạo thường có dạng:

```text
demo-0.0.1-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/demo/DemoApplication.class
│   │   └── application.properties
│   ├── lib/
│   │   ├── spring-boot-....jar
│   │   └── ...dependency runtime khác...
│   ├── classpath.idx                 (có thể có)
│   └── layers.idx                    (khi bật layers)
└── org/springframework/boot/loader/...
```

- `BOOT-INF/classes` chứa class và resource của ứng dụng.
- `BOOT-INF/lib` chứa các JAR dependency được công cụ packaging chọn để ứng dụng có thể chạy độc lập với classpath chứa nested JAR.
- `org/springframework/boot/loader/...` là bộ launcher hỗ trợ khởi động và đọc nested JAR theo định dạng của Boot.
- Manifest của **Spring Boot 3.3.x** thường có các thuộc tính như `Main-Class: org.springframework.boot.loader.launch.JarLauncher` và `Start-Class: com.example.demo.DemoApplication`. Giá trị thực phụ thuộc phiên bản, layout và tên main class.
- Có thể chạy bằng `java -jar <đường-dẫn-file-boot>.jar` nếu JDK và môi trường runtime phù hợp.

**Đừng gọi executable Boot JAR là shaded JAR theo nghĩa tất cả JAR được giải nén/gộp class vào root.** Spring Boot mặc định **lồng** các dependency JAR; những plugin Shade/Shadow có thể có mô hình khác.

### 1.3 Tại sao Boot JAR không thích hợp làm dependency Java thông thường?

Một module khác trông chờ tải `com/example/demo/DemoApplication.class` từ root của dependency JAR. Nhưng trong Spring Boot executable JAR, class đó nằm trong `BOOT-INF/classes/com/example/demo/...`. Classloader thông thường của Maven/Gradle consumer **không tự coi `BOOT-INF/classes` là root package**, nên mô hình dùng executable JAR như dependency thư viện thường không phù hợp.

Nếu dự án vừa cần **công bố thư viện** vừa cần **chạy ứng dụng**, có thể giữ plain artifact làm main dependency và đặt executable artifact dưới **classifier riêng**, hoặc thiết kế tách thành hai module `library` và `application`. Không cần phát hành mọi Boot JAR như dependency cho module khác.

### 1.4 Hậu tố của tên file không tự chứng minh cấu trúc

Có thể một đồng nghiệp đổi tên `demo-plain.jar` thành `demo.jar`. File vẫn là plain archive. Cũng có thể đặt tên Boot JAR là `demo-exec.jar`, `demo-boot.jar` hoặc tên tùy chọn. Vì vậy:

> **Tên gợi ý mục đích; task đóng gói, manifest, layout và phép thử thực tế mới chứng minh loại artifact.**

Đừng đoán chỉ dựa vào kích thước, đuôi `.jar`, sự có mặt của `Main-Class`, hoặc việc file tồn tại trong `target`/`build/libs`.

## 2. Bảng thuật ngữ để không nhầm `plain`, `original` và `classifier`

| Thuật ngữ | Hệ build / nguồn | Ý nghĩa |
| --- | --- | --- |
| `jar` (task/goal thường) | Gradle `jar` hoặc Maven Jar Plugin ở phase `package` | Đóng gói classes/resources vào JAR thường |
| `bootJar` | Spring Boot Gradle plugin + Java plugin | Tạo **executable Boot JAR** |
| `bootWar` | Spring Boot Gradle plugin + War plugin | Tạo **executable Boot WAR** |
| `spring-boot:repackage` | Spring Boot Maven Plugin | Lấy JAR/WAR đã được tạo trong Maven lifecycle và đóng gói lại theo layout Boot |
| `-plain.jar` / `-plain.war` | **Gradle** (convention classifier mặc định của plain task khi có Boot task) | Một **artifact thường riêng** do task `jar`/`war` tạo |
| `.jar.original` / `.war.original` | **Maven** khi `repackage` thay thế main artifact | **Bản sao lưu archive trước khi repackage**, giữ cục bộ ở `target` theo cơ chế mặc định |
| `-exec.jar`, `-boot.jar` | Maven/Gradle khi người dùng cấu hình classifier khác | Hậu tố do cấu hình đặt cho artifact; **không có nghĩa bắt buộc** trong mọi dự án |
| `classifier` | Maven artifact coordinates hoặc Gradle `archiveClassifier` | Dùng để phân biệt các biến thể có cùng tên gốc và phiên bản |
| `attach` (Maven) | Spring Boot Maven Plugin | Quyết định repackaged artifact có được gắn vào quá trình `install`/`deploy` hay không |
| `layout=NONE` (Maven) | Spring Boot Maven Plugin | Có thể đưa nested libraries vào JAR nhưng không cung cấp main launcher: **không phải executable layout thông thường** |

**Lưu ý quan trọng:** `.jar.original` không phải một Maven **classifier** tên `original`. Nó là hậu tố backup của file đã bị `repackage` thay thế. Ngược lại `-plain.jar` thường là classifier thật của Gradle plain `jar` task. Đây là điểm khác biệt của đề bài.

## 3. Gradle: `jar` và `bootJar` là hai task riêng

### 3.1 Cấu hình mẫu cho một Spring Boot JAR

Tệp `settings.gradle`:

```groovy
rootProject.name = 'demo'
```

Tệp `build.gradle` (Groovy DSL) có thể dùng cho bài thực hành:

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ví dụ này không cần web starter vì chỉ minh họa JAR chạy một chương trình console Spring Boot. Dự án cần một lớp Java có `main` như phần 7. `io.spring.dependency-management` ở đây cung cấp dependency version management theo BOM của Boot khi dùng plugin tương ứng; nó không tạo task `bootJar`. Chính `org.springframework.boot` kết hợp `java` mới tạo Boot archive task.

### 3.2 Những task cần phân biệt

Khi áp dụng Java plugin và Spring Boot Gradle plugin:

| Task | Tác dụng | Output mặc định ví dụ |
| --- | --- | --- |
| `compileJava` | Biên dịch mã Java | `build/classes/java/main` |
| `processResources` | Xử lý resources | `build/resources/main` |
| `jar` | JAR thường, class ở root | `build/libs/demo-0.0.1-SNAPSHOT-plain.jar` |
| `bootJar` | Spring Boot executable JAR, class ở `BOOT-INF/classes` | `build/libs/demo-0.0.1-SNAPSHOT.jar` |
| `assemble` | Lifecycle tập hợp artifact; Boot nối `bootJar` vào `assemble` | Có thể chạy các archive task đã được nối vào lifecycle |
| `build` | Lifecycle gồm `assemble` và các bước kiểm tra | Có thể sinh cả executable và plain archive tùy task enable/config |
| `bootRun` | Chạy source set/runtime classpath khi phát triển | **Không phải** task tạo JAR |

Với Boot Gradle plugin 3.3, tài liệu xác nhận khi `bootJar` được cấu hình, task `jar` được đặt **convention classifier `plain`**. Nhờ đó hai task có đầu ra **khác đường dẫn**, không va chạm. Tương tự, `bootWar` và `war` dùng classifier `plain` cho task WAR thường.

**`-plain` không có nghĩa build lỗi, artifact cũ hoặc "chưa chạy Spring Boot plugin".** Nó là một file thật được Gradle tạo để phân biệt plain archive với Boot archive.

Để sinh rõ cả hai trong bài thực hành:

```bash
./gradlew clean jar bootJar
```

Sau lệnh trên, nếu giữ cấu hình mẫu và không có tùy biến classifier, các file mong đợi là:

```text
build/libs/demo-0.0.1-SNAPSHOT-plain.jar
build/libs/demo-0.0.1-SNAPSHOT.jar
```

Đây là tên theo quy ước của `rootProject.name`/`version` mẫu, không phải kết quả stdout của Gradle đã thực chạy. Trong dự án thật có thể có archive khác, classifier tùy chọn hoặc task bị disable.

### 3.3 Đổi classifier: cho Boot mang `-boot`, plain dùng tên không hậu tố

Đôi khi CI/publishing muốn **plain JAR có tên chính**, còn executable JAR dùng `-boot.jar`. Cấu hình **trong `build.gradle`**:

```groovy
tasks.named('bootJar') {
    archiveClassifier = 'boot'
}

tasks.named('jar') {
    archiveClassifier = ''
}
```

Sau `./gradlew clean jar bootJar`, tên dự kiến:

```text
build/libs/demo-0.0.1-SNAPSHOT.jar           # plain
build/libs/demo-0.0.1-SNAPSHOT-boot.jar      # executable
```

Đây là **thay đổi classifier**, không chuyển đổi lại logic hai task. `jar` vẫn là plain, `bootJar` vẫn là Boot. Nếu pipeline trước đây chỉ copy `demo-0.0.1-SNAPSHOT.jar` để chạy `java -jar`, sau khi thay đổi classifier nó có thể copy **nhầm plain JAR**. Phải cập nhật stage artifact selection **cùng commit**.

**Kotlin DSL `build.gradle.kts`**, cú pháp tường minh kiểu task tương đương (trích đoạn; file phải áp dụng đúng plugin):

```kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    archiveClassifier.set("boot")
}

tasks.named<org.gradle.api.tasks.bundling.Jar>("jar") {
    archiveClassifier.set("")
}
```

Không chép `archiveClassifier = 'boot'` kiểu Groovy sang Kotlin DSL. Kotlin dùng string với nháy kép và property API `set(...)`.

### 3.4 Có nên tắt plain `jar`?

Spring Boot Gradle Plugin cho phép:

```groovy
tasks.named('jar') {
    enabled = false
}
```

Kotlin DSL tương ứng:

```kotlin
tasks.named<org.gradle.api.tasks.bundling.Jar>("jar") {
    enabled = false
}
```

Cấu hình này khiến task `jar` **không tạo plain JAR** khi được gọi, giúp một ứng dụng thuần chỉ muốn executable archive bớt đầu ra. Nhưng **không nên mặc định tắt**:

- Module Java thư viện hoặc `java-library` có thể cần plain JAR để làm dependency.
- Một số hệ thống `maven-publish`, task phân phối hoặc CI phụ thuộc output của `jar`.
- **Tài liệu Spring Boot cảnh báo không tắt `jar` khi tạo native images** (liên quan tích hợp Gradle/GraalVM).
- Tắt task `jar` không tự làm `bootJar` chạy, cũng không tự xác định main class của app; phải kiểm tra task graph và build lại.
- Không thay classifier của cả `jar` và `bootJar` thành chuỗi rỗng `''` cùng lúc: hai task sẽ nhắm **cùng tên file**, có thể ghi đè/sinh kết quả không dự đoán được.

Nếu chỉ muốn **CI lấy đúng một file**, cách tốt hơn thường là cấu hình stage lấy **output đúng task** thay vì tắt task cần cho các workflow khác.

### 3.5 Đổi tên archive không đổi loại archive

Các thuộc tính Gradle như `archiveBaseName`, `archiveVersion`, `archiveClassifier` và `archiveFileName` giúp chọn tên output. Ví dụ:

```groovy
tasks.named('bootJar') {
    archiveFileName = 'service-app.jar'
}
```

Nó chỉ đổi tên output của `bootJar` thành `service-app.jar`; nó không làm plain `jar` trở thành Boot JAR, và cũng không làm `service-app.jar` tự an toàn để deploy. Khi dùng tên cố định, kiểm tra các variant và task khác không vô tình ghi vào cùng đường dẫn.

Đường dẫn mặc định là `build/libs/`, nhưng cũng có thể đổi bằng `destinationDirectory` hoặc configuration khác. Đừng hardcode đường dẫn tên file từ ví dụ nếu dự án có custom archive properties.

## 4. Maven: một JAR được tạo trước rồi `repackage` biến nó thành Boot JAR

### 4.1 Ví dụ POM cho `repackage` mặc định

Ví dụ `pom.xml` tối giản cho ứng dụng Spring Boot không cần HTTP server, với cấu hình bản Java 17:

```xml
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
    <artifactId>demo</artifactId>
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
```

Khi kế thừa `spring-boot-starter-parent`, goal `repackage` đã được parent cấu hình cho execution tên `repackage`; khai báo plugin trong POM là đủ để kích hoạt trong lifecycle thông thường. Trong project **chỉ import Spring Boot BOM mà không kế thừa parent**, bạn không được mặc định có execution này: phải gắn `spring-boot:repackage` vào phase `package` (hoặc chạy goal đúng quy trình).

Chạy từ thư mục có `pom.xml` và Maven Wrapper:

```bash
./mvnw clean package
```

Với cấu hình ở trên và lớp `main` như phần 7, sau `package` thông thường sẽ có:

```text
target/demo-0.0.1-SNAPSHOT.jar              # Boot executable JAR
target/demo-0.0.1-SNAPSHOT.jar.original     # plain JAR trước khi repackage
```

Maven tạo JAR thường trước (thường do Maven Jar Plugin), sau đó Spring Boot Maven Plugin **repackage** nó theo layout executable. Khi goal không được cấu hình classifier, nó **thay thế main artifact** bằng file repackaged. File gốc được đổi tên thành `.original` trong thư mục build để giữ lại bản trước khi đóng gói lại.

**Chỗ dễ nhầm nhất:**

- `demo-0.0.1-SNAPSHOT.jar` sau repackage mặc định là **Boot executable JAR**.
- `demo-0.0.1-SNAPSHOT.jar.original` là **plain backup file**, không phải JAR "được Gradle đặt classifier original" và không phải định dạng dành cho container deploy.
- `.original` là tên file **cục bộ** (backup), không mặc định là Maven artifact phụ được upload cùng main JAR vào repository.
- `mvn install`/`deploy` ở chế độ mặc định sẽ xử lý **main artifact đã repackage**; nó không biến `.original` thành artifact maven có classifier chỉ vì file vẫn nằm trong `target`.

Lệnh `jar tf target/demo-0.0.1-SNAPSHOT.jar.original` vẫn có thể dùng để xem byte JAR ban đầu (JAR thực chất là ZIP; công cụ `jar` nhận đường dẫn file), nhưng file có đuôi `.original` không phải file nên copy vào Dockerfile với tên "JAR để chạy" mà không kiểm tra thêm.

### 4.2 Lệnh `mvn package` khác `spring-boot:repackage` gọi riêng

`spring-boot:repackage` **cần một source JAR/WAR đã tồn tại** từ phase `package`. Theo tài liệu, không nên chỉ gọi trơ `./mvnw spring-boot:repackage` trên một build chưa có archive nguồn.

Với project đã cấu hình plugin hợp lệ, cách an toàn thông thường là:

```bash
./mvnw clean package
```

Nếu project không được parent gắn sẵn goal repackage, một kiểu gọi đúng thứ tự là:

```bash
./mvnw package spring-boot:repackage
```

Cần chú ý **nếu goal repackage đã chạy trong `package`**, việc gọi thêm một lần ở cùng chuỗi lệnh có thể tạo thao tác không mong muốn hoặc không cần thiết. Đừng chạy cả hai kiểu bừa bãi; kiểm tra `help:effective-pom` và danh sách execution trước.

### 4.3 `<classifier>exec</classifier>`: giữ plain làm artifact chính

Nếu module có thể được module khác dùng làm dependency, hoặc bạn muốn lưu đồng thời hai dạng archive trong Maven repository, cấu hình **custom classifier cho Boot repackage**.

Giữ POM trên và đổi phần Spring Boot plugin thành:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <classifier>exec</classifier>
        <attach>true</attach>
    </configuration>
</plugin>
```

Đây là **trích đoạn thay thế plugin trong `<build><plugins>`** của project dùng `spring-boot-starter-parent`. Vì parent đã gắn execution `repackage`, cấu hình ở cấp plugin áp dụng cho execution đó. `<attach>true</attach>` là mặc định của goal; nêu rõ để mô tả việc xuất bản hai artifact. Với dự án **không dùng parent**, bạn còn phải khai báo execution `repackage` thích hợp.

Sau `./mvnw clean package`, nếu chưa có artifact source khác cùng classifier `exec`, file kỳ vọng:

```text
target/demo-0.0.1-SNAPSHOT.jar             # plain JAR, artifact Maven chính
target/demo-0.0.1-SNAPSHOT-exec.jar        # executable Boot JAR, artifact classifier "exec"
```

Diễn giải:

- `demo-0.0.1-SNAPSHOT.jar` là JAR thường, lớp Java ở root (nếu không có plugin đặc biệt khác).
- `demo-0.0.1-SNAPSHOT-exec.jar` chứa Boot loader, `BOOT-INF/classes` và nested dependencies.
- Chạy `java -jar target/demo-0.0.1-SNAPSHOT-exec.jar` nếu muốn chạy ứng dụng. Dùng main JAR plain làm dependency khi thích hợp.
- Với `attach=true`, `mvn install`/`deploy` có thể đăng ký hai artifact: main không classifier và artifact classifier `exec`. Người tiêu thụ cần chỉ rõ classifier nếu muốn lấy `exec`.
- Không mặc định có `.jar.original` nữa khi **main artifact không bị thay thế**, vì hai file đầu ra đã có tên khác nhau.

**Chi tiết chuyên sâu đáng nhớ:** khi cấu hình `classifier`, Maven Repackage Plugin trước tiên có thể tìm một artifact **đã tồn tại với classifier đó** làm nguồn để repackage. Nếu tồn tại, nó có thể repackage artifact classifier đó; nếu không, nó dùng main archive rồi gắn bản repackaged làm supplemental artifact. Vì thế khi có custom Maven Jar Plugin tạo nhiều classifier, phải xem execution order và source artifact thực tế, không chỉ đọc `<classifier>exec</classifier>` một cách cô lập.

### 4.4 `<attach>false</attach>` không phải "không tạo file"

Thông số `attach` của Maven Boot Plugin điều khiển việc **gắn repackaged artifact cho install/deploy**. Khi `attach=false`, không nên suy ra plugin "bỏ qua tạo Boot JAR"; theo tài liệu, mục tiêu có thể là vẫn tạo archive thực thi cục bộ, nhưng không phát hành nó như artifact được gắn kèm.

Trường hợp thông dụng `attach=true` và classifier rỗng: repackaged JAR thay main artifact. Trường hợp classifier `exec` + `attach=true`: hai artifact cùng được xuất bản dưới tọa độ khác nhau. Còn nếu điều chỉnh `attach=false`, hãy thử cả `package` lẫn `install` trong một repository test hoặc kiểm tra metadata phát hành để biết chính xác file nào đi đâu. **Không nhầm "file tồn tại trong target" với "file được publish".**

### 4.5 Maven `finalName` ảnh hưởng tên file, không đổi packaging

Nếu POM có:

```xml
<build>
    <finalName>app-service</finalName>
</build>
```

thì main archive thường sẽ lấy tên `target/app-service.jar` (và `target/app-service.jar.original` nếu repackage mặc định). Với classifier `exec`, ví dụ file là `target/app-service-exec.jar` theo hành vi plugin tương ứng.

`<finalName>` **khác** `<classifier>`:

- `finalName` chủ yếu điều khiển tên file trong thư mục build.
- `classifier` phân biệt artifact Maven được attach/publish; khi dùng Boot plugin, nó cũng quyết định chọn artifact nguồn/đầu ra cần repackage.
- Maven coordinates cho dependency còn gồm `groupId`, `artifactId`, `version`, `type` và `classifier`; đổi tên file bằng `finalName` không tự đổi toàn bộ tọa độ repository.

Đừng sửa `finalName` chỉ để "xóa .original"; bản backup có vai trò riêng và sẽ xuất hiện khi plugin thay thế main artifact theo mặc định.

## 5. So sánh Gradle `-plain.jar` và Maven `.jar.original` theo dòng thời gian

### Gradle: hai task / hai output độc lập

```text
source Java/resources
        |
        +-- jar ------------> build/libs/demo-0.0.1-SNAPSHOT-plain.jar
        |                         (archive thường)
        |
        \-- bootJar --------> build/libs/demo-0.0.1-SNAPSHOT.jar
                                  (Boot executable archive)
```

- `jar`/`bootJar` có output riêng, convention classifier giúp tránh trùng.
- Không có bước mặc định "đổi tên bản plain sang `.original`" để chuẩn bị executable archive.
- Hai file cùng tồn tại khi hai task tương ứng được chạy, hoặc có thể chỉ một file khi pipeline chạy riêng một task.
- `-plain` là **classifier theo cách tạo tên file** ở task `jar`, có thể cấu hình thành tên khác.

### Maven: một main artifact có thể bị thay thế

```text
source Java/resources
        |
        v
maven-jar-plugin:jar ----> target/demo-0.0.1-SNAPSHOT.jar  (ban đầu là plain)
        |
        v
spring-boot:repackage ---> target/demo-0.0.1-SNAPSHOT.jar
                            (đã chuyển thành Boot executable)
                             +
                            target/demo-0.0.1-SNAPSHOT.jar.original
                            (bản lưu trước repackage)
```

- `.original` chỉ là bản backup cục bộ theo luồng mặc định.
- Nếu thêm custom classifier `exec`, đường ra thay đổi thành **plain main JAR và Boot `-exec.jar`**, không cần thay thế main archive.
- Nếu không chạy `repackage`, `target/demo-...jar` có thể vẫn là plain và **không có** `.original`. Vì vậy nhìn tên file không phải cách duy nhất biết goal đã chạy.

### Bảng đối chiếu theo cấu hình mặc định

| Câu hỏi | Gradle Boot plugin | Maven Boot plugin |
| --- | --- | --- |
| Ai tạo plain JAR? | `jar` task | Maven Jar Plugin trong `package` |
| Ai tạo Boot executable JAR? | `bootJar` task | `spring-boot:repackage` goal |
| Tên Boot JAR mặc định trong ví dụ | `demo-0.0.1-SNAPSHOT.jar` | `demo-0.0.1-SNAPSHOT.jar` |
| Tên plain JAR mặc định trong ví dụ | `demo-0.0.1-SNAPSHOT-plain.jar` | `demo-0.0.1-SNAPSHOT.jar.original` |
| Plain JAR là artifact độc lập? | Có, output của một task độc lập | Trước khi repackage là main JAR; sau repackage mặc định còn bản `.original` cục bộ |
| Khi muốn main artifact là plain | Đổi classifier của `jar` thành rỗng và `bootJar` thành `boot` (hoặc cấu hình publication có chủ đích) | Đặt `<classifier>exec</classifier>` cho Boot repackage |
| Có nên deploy plain làm executable? | Không, trừ khi nó được thiết kế đặc biệt để chạy | Không, trừ khi có cơ chế khởi động/dependency riêng |
| Kiểm tra đáng tin nhất | Xem task, `jar tf`/manifest, chạy đúng Boot JAR | Xem execution `repackage`, `jar tf`/manifest, chạy đúng Boot JAR |

## 6. Khi muốn đóng gói WAR: `war`, `bootWar`, `-plain.war` và `.war.original`

Đề bài tập trung JAR thực thi, nhưng sự khác nhau **plain vs executable** cũng áp dụng cho WAR trong ứng dụng Spring MVC/Servlet.

### 6.1 Gradle WAR

Khi có Gradle `war` plugin và Boot plugin, task `war` tạo WAR thường; `bootWar` tạo Boot executable WAR. Khi cả hai được tạo theo mặc định, tên minh họa:

```text
build/libs/demo-0.0.1-SNAPSHOT-plain.war    # war thường
build/libs/demo-0.0.1-SNAPSHOT.war          # bootWar executable
```

Cách áp dụng plugin và servlet dependency **trích đoạn Groovy**:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

Đoạn này không phải `build.gradle` hoàn chỉnh; cần `repositories`, `group`, `version`, JDK và lớp ứng dụng phù hợp. `war` áp dụng `java` ngầm. Để deploy WAR ra servlet container ngoài, ứng dụng cần triển khai `SpringBootServletInitializer` và container tương thích, không chỉ sửa `jar` thành `war`.

Có thể đổi classifier cho WAR theo cùng nguyên tắc:

```groovy
tasks.named('bootWar') {
    archiveClassifier = 'boot'
}
tasks.named('war') {
    archiveClassifier = ''
}
```

Sau đó plain WAR có thể lấy tên chính `demo-0.0.1-SNAPSHOT.war`, còn Boot WAR dùng `demo-0.0.1-SNAPSHOT-boot.war`. **Phải cập nhật deployment pipeline** để chọn đúng file.

### 6.2 Maven WAR

Với Maven `<packaging>war</packaging>` và goal `repackage` đã được gắn đúng, file WAR gốc có thể được lưu thành `target/demo-0.0.1-SNAPSHOT.war.original` khi executable WAR thay thế artifact chính. Nếu dùng classifier `exec`, có thể giữ plain WAR làm main artifact và tạo thêm `...-exec.war`.

Maven Boot executable WAR thường có `WEB-INF/classes`, `WEB-INF/lib` và có thể `WEB-INF/lib-provided`. WAR thường cũng có `WEB-INF/classes` và `WEB-INF/lib`, nên chỉ thấy thư mục `WEB-INF` **không đủ để kết luận WAR executable**. Hãy kiểm tra Boot loader/manifest và thử `java -jar` trên đúng Boot WAR. Nếu deploy vào servlet container ngoài, còn phải kiểm tra tương thích container/initializer/provided dependencies.

**Không coi `-plain.war` là một file "không thể deploy":** WAR thường có thể là artifact phù hợp cho servlet container ngoài. Nhưng nếu pipeline kỳ vọng `java -jar`, plain WAR có thể thiếu Boot launcher. Chọn artifact theo **cách vận hành mục tiêu**, không theo suy luận "Boot luôn tốt hơn plain".

## 7. Một lớp Java 17+ dùng để kiểm chứng artifact

Để tránh ngụy tạo stdout hoặc phụ thuộc môi trường web, tạo **một ứng dụng Spring Boot không có HTTP server**. Với cả POM Maven lẫn build.gradle đã cho, tạo file:

```text
src/main/java/com/example/demo/DemoApplication.java
```

Nội dung đầy đủ:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
        System.out.println("ARCHIVE_OK");
    }
}
```

Đây là lớp Java hợp lệ cho **project Spring Boot có dependency starter và Java 17+**. Nó **không độc lập** khi gọi `javac DemoApplication.java` trần vì cần Spring Boot classes trên classpath. Dùng `./mvnw package` hoặc `./gradlew bootJar` để biên dịch và đóng gói.

Khi build thành executable Boot JAR và chạy với JDK tương thích:

```bash
# Maven, không cấu hình classifier
java -jar target/demo-0.0.1-SNAPSHOT.jar

# Gradle, dùng classifier mặc định của Boot task
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

Ứng dụng sẽ in **dòng do chương trình tự in**:

```text
ARCHIVE_OK
```

Trên thực tế có thể còn Spring Boot banner, startup log, cảnh báo hoặc output khác; đoạn trên **không phải stdout đầy đủ** của một lượt chạy thật. Nếu đổi `<classifier>exec</classifier>` ở Maven, phải chạy `java -jar target/demo-0.0.1-SNAPSHOT-exec.jar`; nếu đổi `archiveClassifier='boot'` ở Gradle, phải chạy `java -jar build/libs/demo-0.0.1-SNAPSHOT-boot.jar`.

### Kiểm tra bằng `jar tf`

Maven:

```bash
./mvnw clean package
jar tf target/demo-0.0.1-SNAPSHOT.jar
jar tf target/demo-0.0.1-SNAPSHOT.jar.original
```

Gradle:

```bash
./gradlew clean jar bootJar
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
jar tf build/libs/demo-0.0.1-SNAPSHOT-plain.jar
```

**Dấu hiệu mong đợi từ ví dụ Maven/Gradle:**

| Đường dẫn trong ZIP | Boot executable JAR | Plain JAR |
| --- | --- | --- |
| `BOOT-INF/classes/com/example/demo/DemoApplication.class` | Có | Thường không |
| `com/example/demo/DemoApplication.class` tại root | Không theo layout Boot thông thường | Có |
| `BOOT-INF/lib/` với JAR dependency | Có | Không theo cách đóng gói plain mặc định |
| `org/springframework/boot/loader/...` | Có | Thường không |
| `META-INF/MANIFEST.MF` | Có | Có |
| `Main-Class: ...JarLauncher` trong manifest | Thường có với Boot 3.3 JAR layout | Không mặc định |
| `Start-Class: com.example.demo.DemoApplication` | Thường có | Không mặc định |

Đừng kiểm tra một file `.original` ở Maven mà kết luận Boot JAR thiếu launcher: `.original` **cố ý giữ bản trước khi repackage**.

### Đọc manifest

Trên macOS/Linux nếu có `unzip`:

```bash
unzip -p build/libs/demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
```

Với Maven thay đường dẫn file. `Main-Class` và `Start-Class` của Boot 3.3 là hai thuộc tính khác nhau: launcher là lớp được JVM gọi đầu tiên; Spring Boot launcher tìm ứng dụng gốc qua `Start-Class`.

**Cảnh báo kiểm chứng:** chỉ thấy `Main-Class` chưa đủ chứng minh đầy đủ dependency đã có; một plain JAR cũng có thể được cấu hình `Main-Class`. Kết hợp **manifest + layout + chạy thật**; tùy dự án có custom loader/layout thì áp dụng tiêu chí tương ứng.

## 8. Vì sao `java -jar` bị lỗi với `-plain.jar` hoặc `.jar.original`?

Ví dụ người dùng chạy:

```bash
java -jar build/libs/demo-0.0.1-SNAPSHOT-plain.jar
```

Có thể xảy ra một trong những lỗi sau, **tùy cấu hình manifest và classpath**:

- `no main manifest attribute`: plain JAR không khai báo `Main-Class`.
- `ClassNotFoundException` hoặc `NoClassDefFoundError`: có main nhưng dependency runtime không được đóng vào archive và không có classpath bên ngoài phù hợp.
- Ứng dụng khởi động nhưng thiếu tài nguyên/dependency trong môi trường thực: đó là lý do test runtime/packaging cần đi kèm kiểm tra file.

Không có stdout/error cố định cho **mọi** plain JAR. Cách sửa đúng là **chọn executable Boot JAR** khi muốn chạy độc lập, không phải đổi tên file thành `*.jar`, xóa hậu tố `plain` hay chép `BOOT-INF` bằng tay.

Với Maven, chạy `java -jar target/demo-...jar.original` cũng thường thất bại trong Spring Boot app có dependency vì đây là **archive trước repackage**. Nó không phải là một file hỏng: chỉ phục vụ mục đích khác.

### Khi plain JAR là lựa chọn đúng

Trong một module cung cấp API hoặc domain model, plain JAR có class ở root là lựa chọn phù hợp để những module khác import. Nếu pipeline dự định phát hành một **thư viện Java**, đừng tự động chọn file lớn nhất hay Boot JAR. Trường hợp module đóng cả thư viện lẫn app, cân nhắc:

1. Tách thành module `library` dùng `java-library` và module `application` dùng Boot plugin.
2. Hoặc ở Maven, giữ plain làm main, dùng Boot classifier `exec`.
3. Hoặc ở Gradle, cấu hình classifiers và publication sao cho plain/API artifact và executable artifact có tọa độ rõ ràng.

Điều kiện quan trọng là **module tiêu thụ** không kỳ vọng đọc class từ `BOOT-INF/classes` qua classloader thông thường.

## 9. Chọn đúng artifact khi làm CI, Docker và publishing

### 9.1 Lý do không nên dùng wildcard quá rộng

Một stage copy kiểu:

```bash
cp build/libs/*.jar release/app.jar
```

có thể thất bại khi có nhiều file, hoặc được sửa sai thành "lấy file đầu tiên" mà vô tình lấy `-plain.jar`. Với Maven, `target/*.jar*` có thể khớp cả `.jar.original`, bản sources/javadoc hoặc file từ module khác.

Nguyên tắc:

- Build **từ checkout sạch** bằng đúng Wrapper và task/goal mà pipeline dự định triển khai.
- Chọn đúng **output task** hoặc **một đường dẫn artifact cố định, đã xác nhận**.
- Kiểm tra file bằng manifest/layout trước khi publish hoặc đưa vào image.
- Nếu đổi classifier hoặc `finalName`/`archiveFileName`, cập nhật CI/Dockerfile trong cùng thay đổi.
- Không nhầm file `.original` được giữ local với attached/deployed Maven artifact.
- Với Gradle, kiểm tra publication component/task thay vì mặc định rằng mọi file trong `build/libs` đều được publish lên Maven repository.

### 9.2 Ví dụ stage Maven chọn đúng Boot JAR

Với POM ví dụ dùng default repackage:

```bash
./mvnw clean package
artifact="target/demo-0.0.1-SNAPSHOT.jar"
test -f "$artifact"
jar tf "$artifact"
java -jar "$artifact"
```

`java -jar` là smoke test, với app console trong bài nó sẽ in `ARCHIVE_OK` rồi thoát trong điều kiện chạy bình thường. Trong CI thực tế, ứng dụng web thường **không tự thoát**; phải khởi động có kiểm soát, health check rồi dừng process, không gọi `java -jar` trực tiếp trong stage không có timeout/health policy.

Với Maven classifier `exec`, đổi duy nhất đường dẫn kiểm tra/deploy thành:

```bash
artifact="target/demo-0.0.1-SNAPSHOT-exec.jar"
```

Nếu một team muốn publish **plain main artifact** cho thư viện và Boot classifier cho deploy, phải cấu hình `attach`/execution chính xác và kiểm tra metadata ở Maven repository, không chỉ file local.

### 9.3 Ví dụ stage Gradle chọn đúng Boot JAR

```bash
./gradlew clean bootJar
artifact="build/libs/demo-0.0.1-SNAPSHOT.jar"
test -f "$artifact"
jar tf "$artifact"
```

Nếu `archiveClassifier = 'boot'`, phải đổi đường dẫn thành `demo-0.0.1-SNAPSHOT-boot.jar`. Một số build phức tạp đổi destination directory hoặc basename; cần lấy tên thực từ cấu hình task.

**Ví dụ trích đoạn Dockerfile** cho artifact Maven mẫu, không phải giải pháp toàn bộ pipeline:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/demo-0.0.1-SNAPSHOT.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Nếu Maven đang dùng `classifier=exec` thì Dockerfile trên sẽ **copy nhầm plain main JAR**; phải đổi thành `target/demo-0.0.1-SNAPSHOT-exec.jar`. Nếu dùng Gradle, đổi từ `target/...` sang `build/libs/...` thực tế.

### 9.4 Kiểm tra layout fail-fast bằng Bash

Đoạn sau kiểm tra **JAR executable Boot layout** của ví dụ trước khi đưa vào Docker image; khác kiểm tra ứng dụng chạy thật nhưng ngăn lỗi chọn nhầm plain/original:

```bash
#!/usr/bin/env bash
set -euo pipefail

artifact="build/libs/demo-0.0.1-SNAPSHOT.jar"

if [[ ! -f "$artifact" ]]; then
    echo "FAIL: artifact missing"
    exit 1
fi

entries="$(jar tf "$artifact")"

if ! grep -Fq 'BOOT-INF/classes/' <<< "$entries"; then
    echo "FAIL: missing BOOT-INF/classes"
    exit 1
fi

if ! grep -Fq 'BOOT-INF/lib/' <<< "$entries"; then
    echo "FAIL: missing BOOT-INF/lib"
    exit 1
fi

if ! grep -Fq 'org/springframework/boot/loader/' <<< "$entries"; then
    echo "FAIL: missing Spring Boot loader"
    exit 1
fi

echo "PASS: Spring Boot executable JAR layout detected"
```

**Áp dụng:** ví dụ ứng dụng Spring Boot 3.3 có dependency starter, output `bootJar` JAR. Với Boot JAR hợp lệ có nested dependencies và loader đúng như dự kiến, dòng do script in là:

```text
PASS: Spring Boot executable JAR layout detected
```

Dòng này **không phải kết quả đã chạy trên project của bạn**, mà là kết quả theo điều kiện của script. File nguồn không tồn tại hoặc thiếu layout sẽ in một dòng FAIL rồi exit 1. Script kiểm tra **layout**, không chứng minh JDK đúng, cấu hình runtime đúng, hoặc mọi thư viện an toàn. Nếu project thay loader/layout hoặc đóng WAR, cần điều chỉnh điều kiện.

Với WAR, phải kiểm tra `WEB-INF/classes`, `WEB-INF/lib`/`WEB-INF/lib-provided` và launcher WAR; không chạy tiêu chí `BOOT-INF/classes` của JAR lên WAR.

### 9.5 PowerShell cho người dùng Windows

```powershell
$artifact = "build/libs/demo-0.0.1-SNAPSHOT.jar"

if (-not (Test-Path -LiteralPath $artifact)) {
    throw "Artifact missing: $artifact"
}

$entries = & jar tf $artifact
if ($LASTEXITCODE -ne 0) {
    throw "Cannot read jar: $artifact"
}

if (-not ($entries | Select-String -SimpleMatch "BOOT-INF/classes/")) {
    throw "Not a Boot JAR: BOOT-INF/classes missing"
}
if (-not ($entries | Select-String -SimpleMatch "org/springframework/boot/loader/")) {
    throw "Not a Boot JAR: loader missing"
}

Write-Output "PASS: Boot JAR layout detected"
```

Đây là **bản kiểm tra layout cơ bản**: file có class/resource dưới BOOT-INF và Boot loader; nên thêm kiểm tra `BOOT-INF/lib`, manifest và smoke test tùy yêu cầu của pipeline. Nếu dùng Maven, sửa `$artifact` sang `target/demo-0.0.1-SNAPSHOT.jar` hoặc `-exec.jar` tương ứng.

### 9.6 Publishing: artifact tồn tại chưa chắc là artifact được phát hành

Ở Maven, `attach` và classifier của `repackage` quyết định main artifact hay supplemental artifact được `install/deploy`. Với Gradle, các task build archive và cấu hình `maven-publish`/publication là hai việc khác nhau: file xuất hiện trong `build/libs` chưa tự đồng nghĩa với nó nằm trên Maven repository.

**Một câu hỏi cần trả lời trước deploy/publish:** "File nào được tạo bởi task nào, có tọa độ group/artifact/version/classifier nào, và stage tiêu thụ nó dùng lệnh khởi động hay import class theo cách nào?". Chỉ sau đó mới chọn plain hay executable.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Bằng chứng và hướng xử lý |
| --- | --- | --- |
| `build/libs` có hai JAR, một file thêm `-plain` | Gradle Boot task và jar task tạo hai loại archive | Đây thường là bình thường; chọn Boot output để `java -jar` |
| `target` có `.jar.original` | Maven `repackage` thay main JAR và lưu bản cũ | Xem `target/*.jar` và manifest; đừng deploy `.original` |
| Gradle plain JAR bị nhầm là file build cũ | Không hiểu `archiveClassifier=plain` | Xem task `jar`, layout root classes và task `bootJar` |
| Maven main JAR không chạy sau khi đặt `classifier=exec` | Main artifact giờ giữ plain, Boot chuyển sang `-exec.jar` | Chạy `java -jar ...-exec.jar` và sửa CI/Dockerfile |
| Không có file `.original` ở Maven | Dùng classifier, không chạy repackage, clean xóa backup hoặc custom plugin | Kiểm tra goal execution và output archive thật |
| `mvn package` không tạo Boot JAR | Không kế thừa parent hoặc thiếu execution `repackage`; có skip/plugin khác | Xem `help:effective-pom`, đúng phase và plugin log |
| `bootJar` task không tồn tại | Chưa áp dụng Boot plugin cùng Java plugin hoặc sai module | `./gradlew tasks --all`, kiểm tra `apply false` và module |
| `bootWar` task không tồn tại | Chưa áp dụng Gradle `war` plugin hoặc sai module | Kiểm tra `plugins` và `tasks --all` |
| `bootJar` báo không tìm thấy main class | Module không có `public static void main(String[])` hợp lệ | Thêm/đặt mainClass hoặc tách module library |
| `jar tf` báo `BOOT-INF/classes` không có | Đang xem plain JAR, hoặc custom archive layout | Kiểm tra task tạo file, manifest và đường dẫn artifact |
| `no main manifest attribute` khi `java -jar` | Plain JAR không có entry point, hoặc archive bị đóng gói sai | Chọn Boot executable JAR, không đổi tên file |
| `ClassNotFoundException` khi dùng plain JAR | Plain không tự mang runtime dependencies, classpath thiếu | Dùng Boot archive khi chạy độc lập hoặc setup classpath hợp lệ |
| Maven classifier `exec` đã đặt nhưng archive bị repackage lạ | Artifact source cùng classifier đã tồn tại | Kiểm tra các execution của jar/repackage, thứ tự và classifiers |
| Gradle hai task ghi cùng tên `...jar` | `jar` và `bootJar` bị đặt classifier/tên giống nhau | Cho hai task **hai archiveFileName khác nhau**, clean rồi build lại |
| Gradle build tạo Boot JAR nhưng CI copy plain | Wildcard hoặc script chọn artifact không xác định | Định danh một đường dẫn đầu ra Boot, kiểm tra layout trước deploy |
| Cố disable `jar` làm native build lỗi | Một số native image workflow cần task jar | Bật lại `jar`, dùng classifier/CI selection thay vì disable |
| Consumer Maven không load được class của dependency | Đã publish Boot JAR ở tọa độ main, classes nằm trong BOOT-INF | Publish plain main + Boot classifier, hoặc tách library module |
| `target/*.jar` có bản cũ | Không clean trước, incremental output hoặc nhiều module | Xác định đúng file theo tên/version, kiểm tra timestamp/hash và artifact stage |
| WAR build thành công nhưng không deploy được | Sai kiểu WAR, thiếu Servlet initializer/compatibility | Phân biệt `war` vs `bootWar`, xem WAR layout và server logs |
| Build tạo file mới nhưng container vẫn chạy bản cũ | Image copy nhầm artifact, layer/cache hoặc tag chưa đổi | Kiểm tra đường COPY, sha256 artifact đã kiểm chứng, image thực deploy |

### Trình tự chẩn đoán nên dùng

1. **Xác nhận đúng build system** và module: `pom.xml` hay `build.gradle`, Maven Wrapper hay Gradle Wrapper?
2. **Ghi đúng task/goal:** `jar`, `bootJar`, `war`, `bootWar`, `repackage`?
3. **Liệt kê tên file thật:** `target/` hoặc `build/libs/`, bao gồm classifier, `.original` và file plain.
4. **Mở file nghi vấn:** `jar tf`, manifest; xem classes nằm ở root hay `BOOT-INF/classes`.
5. **Xác nhận mục đích:** chạy `java -jar`, deploy WAR container, hay publish thư viện cho module khác?
6. **Đối chiếu CI/Docker/publishing:** tập hợp artifact và classifier nào đã được sử dụng thực?
7. **Chỉ sau khi có bằng chứng** mới sửa `archiveClassifier`, `<classifier>`, `attach` hay task enable/disable; chạy lại build từ nguồn tin cậy và kiểm tra lần nữa.

## 11. Bài thực hành: kiểm tra cả hai dạng archive

### Thực hành A – Gradle

1. Tạo project theo `build.gradle` phần 3 và `DemoApplication` phần 7, với Java 17+ và Gradle Wrapper tương thích.
2. Chạy `./gradlew clean jar bootJar` rồi liệt kê `build/libs`. Với cấu hình không đổi, dự kiến có một `-plain.jar` và một JAR không classifier.
3. Mở cả hai bằng `jar tf`. Xác định class ứng dụng nằm **root** hay `BOOT-INF/classes`; tìm `BOOT-INF/lib` và Boot loader.
4. Chạy `java -jar` với **Boot JAR**, thấy dòng do chương trình in `ARCHIVE_OK`. Thử với plain JAR trên bản sao thực hành và giải thích lỗi theo manifest/dependency nếu thất bại.
5. Thêm cấu hình `bootJar.archiveClassifier='boot'` và `jar.archiveClassifier=''`; chạy clean/build, ghi đúng hai tên mới.
6. Giả sử CI còn copy `demo-0.0.1-SNAPSHOT.jar`, giải thích vì sao sau bước 5 nó có thể copy **plain**.
7. Trả lời: khi nào không nên `enabled=false` cho `jar`? Nếu có module thư viện và native image, phải kiểm tra những gì?

### Thực hành B – Maven không classifier

1. Dùng POM phần 4 và `DemoApplication` phần 7.
2. Chạy `./mvnw clean package`; liệt kê `target`.
3. Mở `demo-0.0.1-SNAPSHOT.jar` và `demo-0.0.1-SNAPSHOT.jar.original` bằng `jar tf`. So sánh `BOOT-INF/classes` với classes ở root.
4. Giải thích vì sao tên chính `...jar` giờ là **Boot JAR** dù Maven đã tạo plain trước, và `.original` là gì.
5. Chạy `java -jar` với **JAR chính sau repackage**; xác nhận dòng `ARCHIVE_OK`.
6. Trả lời: nếu bỏ plugin repackage nhưng vẫn dùng `mvn package` thì kết luận "JAR chính chạy bằng java -jar" còn chắc chắn không?

### Thực hành C – Maven dùng classifier `exec`

1. Trong nhánh/bản sao dự án, thêm `<classifier>exec</classifier>` vào cấu hình Spring Boot Maven Plugin.
2. Chạy `./mvnw clean package`; ghi lại main plain `.jar` và Boot `-exec.jar`.
3. Dùng `jar tf` chứng minh file `-exec.jar` có `BOOT-INF/classes`; file main jar không dùng layout đó.
4. Chạy `java -jar target/demo-0.0.1-SNAPSHOT-exec.jar` và xác nhận dòng `ARCHIVE_OK`.
5. Nếu dự án dùng `mvn install` vào local repository test, kiểm tra artifact với classifier `exec` được attach khi `attach=true`; tránh install/deploy lên repository production trong bài tập.
6. Giải thích tại sao module khác có thể cần plain main artifact trong khi hệ thống vận hành cần `-exec.jar`.
7. Tóm tắt khác biệt giữa "Gradle `-plain.jar` là tên task output" và "Maven `.jar.original` là backup trước repackage".

### Thực hành D – Rà soát một pipeline release giả định

Giả sử pipeline dùng:

```text
build/libs/demo-0.0.1-SNAPSHOT.jar
build/libs/demo-0.0.1-SNAPSHOT-plain.jar
```

Một commit thay `bootJar.archiveClassifier` thành `boot` và `jar.archiveClassifier` thành rỗng. Hãy viết lại đường dẫn artifact deploy, lệnh `jar tf` và `java -jar`, đồng thời nêu bước CI cần fail nếu layout không còn đúng.

Thêm tình huống Maven chuyển từ repackage không classifier sang `<classifier>exec</classifier>`: file nào **không còn nên COPY** vào Docker image, file nào phải COPY thay thế, và vì sao?

**Tiêu chí đạt:** không chỉ nhớ tên file. Bạn phải nêu được **task/goal nào sinh file**, **định dạng bên trong**, **mục tiêu dùng** (dependency hay chạy độc lập), **classifier/attach nếu publish**, và chứng minh đường dẫn artifact được kiểm tra chính là đường dẫn sẽ được triển khai.

## 12. Tài liệu tham khảo chính thức

- Spring Boot 3.3 Gradle Plugin – Packaging Executable Archives, phần `Packaging Executable and Plain Archives`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 Maven Plugin – Packaging Executable Archives, `repackage`, `.original`, `classifier`, `attach`: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot – The Executable Jar Format, nested JARs và launcher: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/index.html
- Gradle – Working with Files, archive name/classifier và reproducible archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Maven – Introduction to the Build Lifecycle, phase `package`/`install`/`deploy`: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html

**Ghi nhớ:** file đúng để chạy không được quyết định chỉ bởi một hậu tố. Hãy lần theo **build task/goal → classifier và tên output → layout/manifest → cách chạy hoặc cách tiêu thụ → stage phát hành thật**. Gradle `-plain` và Maven `.original` cùng nhắc tới bản archive thường nhưng **không cùng cơ chế và không cùng vai trò phát hành**.
