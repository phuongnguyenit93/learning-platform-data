# Artifact, dependency, repository, classpath và lifecycle trong Spring Boot

Khi xây dựng một ứng dụng Spring Boot, các công cụ như Maven và Gradle phải trả lời năm câu hỏi: **sản phẩm nào cần tạo ra (artifact), cần những thư viện nào (dependency), lấy chúng ở đâu (repository), JVM/trình biên dịch tìm các lớp ở đâu (classpath), và những công việc build chạy theo trình tự nào (lifecycle)**. Năm khái niệm này liên kết với nhau, nhưng mỗi khái niệm có một vai trò riêng.

## 1. Bức tranh tổng thể

```text
Mã nguồn + cấu hình build
       |
       | khai báo dependency và repository
       v
Giải quyết phiên bản, tải các artifact phụ thuộc
       |
       v
Tạo compile/test/runtime classpath phù hợp
       |
       v
Lifecycle hoặc đồ thị task: compile -> test -> package
       |
       v
Artifact đầu ra: JAR/WAR (có thể là JAR chạy được của Spring Boot)
```

Ví dụ, một ứng dụng khai báo `spring-boot-starter`. Công cụ build tìm các artifact cần thiết trong repository, giải quyết các dependency bắc cầu, đưa các thư viện thích hợp vào classpath để biên dịch/chạy, rồi tạo JAR theo các bước build. **Khai báo dependency**, **đưa lớp lên classpath** và **đóng gói thư viện vào JAR** là ba việc liên quan nhưng không đồng nghĩa.

## 2. Artifact — thứ được tạo ra hoặc được dùng lại

**Artifact** là sản phẩm có định danh và thường có phiên bản mà công cụ build có thể tạo ra, lưu trữ, tải xuống hoặc phân phối: file `.jar`, `.war`, `.pom` và các dạng khác. Một thư viện bên thứ ba là artifact đầu vào; JAR ứng dụng của chính dự án là artifact đầu ra.

Trong Maven, ba thành phần định danh cơ bản là **GAV**:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| `groupId` | Nhóm/tổ chức sở hữu | `com.example` |
| `artifactId` | Tên module/sản phẩm | `build-terms-demo` |
| `version` | Phiên bản | `0.0.1-SNAPSHOT` |

Tọa độ `com.example:build-terms-demo:0.0.1-SNAPSHOT` chỉ ra **artifact nào**; định dạng đóng gói (`jar`, `war`, `pom`) và đôi khi `classifier` (ví dụ artifact chứa source hoặc test) xác định **biến thể file**. `SNAPSHOT` biểu thị phiên bản đang phát triển, có thể thay đổi giữa các lần xuất bản; bản phát hành cố định phù hợp hơn cho việc tái lập build. Không nên suy từ tên file rằng mọi JAR đều tự chạy được.

Đầu ra phổ biến:
- Maven: `target/build-terms-demo-0.0.1-SNAPSHOT.jar`.
- Gradle: `build/libs/build-terms-demo-0.0.1-SNAPSHOT.jar` (khi `rootProject.name` và `version` được thiết lập như ví dụ phía dưới).
- Spring Boot: task `bootJar`/goal `repackage` tạo **executable JAR** chứa mã ứng dụng cùng các dependency runtime cần thiết. JAR thư viện thông thường thường không chứa các dependency này.

## 3. Dependency — một artifact mà thành phần khác cần

**Dependency** là quan hệ phụ thuộc: module A cần module B để biên dịch, kiểm thử hoặc chạy. Một dependency được khai báo có thể kéo theo **transitive dependencies** (phụ thuộc bắc cầu). Ví dụ một Spring Boot starter có thể đưa vào cả các thư viện Spring, logging và autoconfiguration; không phải tất cả đều được liệt kê trực tiếp trong cấu hình của ứng dụng.

Một dependency cần được xét theo ít nhất ba yếu tố:
1. **Danh tính và phiên bản**: lấy thư viện nào, phiên bản nào sau khi giải quyết xung đột.
2. **Mục đích sử dụng**: cần lúc compile, runtime hay test.
3. **Quan hệ bắc cầu**: dependency nào được kéo thêm; có dependency nào phải loại trừ hay không.

### Maven scope và Gradle configuration

| Ý định | Maven | Gradle thường gặp | Ý nghĩa thực tế |
|---|---|---|---|
| Dùng lúc compile và runtime | `compile` (mặc định) | `implementation` | Có mặt khi biên dịch và khi chạy ứng dụng |
| Chỉ cần khi biên dịch | `provided` | `compileOnly` | Thường giả định môi trường chạy cung cấp thư viện; ngữ nghĩa không hoàn toàn tương đương |
| Chỉ cần lúc chạy | `runtime` | `runtimeOnly` | Không cần cho việc biên dịch mã chính |
| Chỉ dùng cho test | `test` | `testImplementation` | Không đóng gói như dependency runtime thông thường |
| Phơi bày API của thư viện cho module dùng nó | Không có scope tương đương trực tiếp | `api` với plugin `java-library` | Dependency là một phần API công khai của thư viện |

Trong Maven, `provided` vẫn có mặt ở classpath compile và test, nhưng không ở runtime thông thường; trong Gradle, `compileOnly` không tự động trở thành dependency runtime. Không dùng các cấu hình này thay cho `implementation` chỉ vì muốn JAR nhỏ đi: khi chạy có thể gặp `NoClassDefFoundError`.

**Quản lý phiên bản khác với thêm dependency.** `dependencyManagement` của Maven hoặc BOM (Bill of Materials) chỉ quản lý phiên bản/quy tắc phối hợp phiên bản; chỉ khi module thực sự khai báo dependency thì thư viện mới được đưa vào đồ thị phụ thuộc. Spring Boot dùng BOM để giữ các phiên bản thư viện tương thích. Maven `spring-boot-starter-parent` cung cấp các thiết lập build và quản lý dependency; Gradle có thể dùng `platform('org.springframework.boot:spring-boot-dependencies:...')`.

Khi nhiều nhánh kéo các phiên bản khác nhau của cùng module, công cụ build thực hiện **dependency resolution** theo quy tắc riêng. Maven thường dùng quy tắc phụ thuộc gần nhất trong đồ thị; Gradle xét các yêu cầu/constraint và chọn phiên bản theo cơ chế giải quyết xung đột của Gradle. Vì vậy phải kiểm tra **phiên bản thực tế được giải quyết**, thay vì chỉ nhìn dependency khai báo trực tiếp.

Các lệnh chẩn đoán:

```bash
# Maven: xem cây phụ thuộc đã được giải quyết
mvn dependency:tree

# Gradle: xem dependency của runtime classpath
./gradlew dependencies --configuration runtimeClasspath

# Windows, khi dự án có Gradle Wrapper
gradlew.bat dependencies --configuration runtimeClasspath
```

`./gradlew`/`gradlew.bat` cần các file Gradle Wrapper trong dự án. Maven tương tự có `./mvnw`/`mvnw.cmd` nếu dự án đã tạo Maven Wrapper.

## 4. Repository — nơi lưu và tìm artifact

**Repository** trong ngữ cảnh build là kho artifact được xuất bản kèm metadata, không phải mặc nhiên là Git repository chứa mã nguồn.

- **Remote repository:** máy chủ lưu artifact để tải về, ví dụ Maven Central hoặc repository nội bộ của tổ chức.
- **Local Maven repository:** thông thường `~/.m2/repository`; lưu các artifact đã tải/cài đặt. `mvn install` còn đưa artifact đang build vào kho local này.
- **Gradle dependency cache:** Gradle lưu artifact và metadata đã giải quyết dưới thư mục cache của Gradle (thường trong `~/.gradle/caches`); cache này không giống hệt một Maven repository.
- **Plugin repository:** nơi tìm build plugin; trong Gradle, repository cho plugin và repository cho dependency có thể cấu hình độc lập.

Quy trình khái quát: đọc tọa độ dependency → hỏi repository/cached metadata → xác định phiên bản và dependency bắc cầu → tải hoặc dùng bản cache → đưa artifact thích hợp vào classpath. Khi máy không kết nối mạng, build vẫn có thể thành công nếu mọi artifact cần thiết đã có trong cache; ngược lại có thể báo lỗi `Could not resolve dependency` dù mã nguồn không đổi.

Cấu hình Maven thường dựa trên Maven Central mặc định và repository nội bộ từ `settings.xml`/POM khi cần. Với Gradle, khai báo kho cho dependency trong `build.gradle`:

```groovy
repositories {
    mavenCentral()
}
```

Không nên thêm repository không đáng tin cậy hoặc hardcode mật khẩu vào file build. Một repository thiếu artifact, lỗi xác thực hoặc metadata xung đột là vấn đề **resolution**, chưa chắc là lỗi Java.

## 5. Classpath — nơi Java tìm lớp và tài nguyên

**Classpath** là tập vị trí (thư mục chứa `.class`, JAR) được trình biên dịch hoặc JVM dùng để tìm các lớp và tài nguyên. Khái niệm này khác với đường dẫn mã nguồn và khác với nơi lưu repository. Trong ứng dụng hiện đại có thể còn có **module path** của JPMS, nhưng phần lớn dự án Spring Boot thông thường vẫn dựa chủ yếu vào classpath.

Các classpath thường gặp:
- **Compile classpath:** các thư viện cần để biên dịch mã trong `src/main/java`.
- **Test classpath:** mã đã biên dịch của ứng dụng và các thư viện phục vụ test.
- **Runtime classpath:** mã ứng dụng cùng các dependency cần lúc chạy, có thể khác compile classpath.

Ví dụ Java 17 thuần dưới đây cho thấy một thư mục chứa bytecode được thêm vào classpath. Tạo file `src/demo/ClasspathDemo.java`:

```java
package demo;

public class ClasspathDemo {
    public static void main(String[] args) {
        System.out.println(ClasspathDemo.class.getName());
        System.out.println(
            ClasspathDemo.class.getResource("ClasspathDemo.class") != null
        );
    }
}
```

Tại thư mục gốc ví dụ, chạy:

```bash
javac -d out src/demo/ClasspathDemo.java
java -cp out demo.ClasspathDemo
```

Stdout chính xác:

```text
demo.ClasspathDemo
true
```

`-d out` đặt file `.class` vào `out/demo/`; `-cp out` cho JVM biết root của package `demo`. Nếu quên `-cp out` và lớp không có trên classpath mặc định, lệnh chạy sẽ gặp lỗi không tìm thấy main class. Nhiều mục classpath được phân tách bằng `;` trên Windows và `:` trên Linux/macOS; để chạy một thư mục duy nhất như trên thì không cần dấu phân tách.

Cần phân biệt hai loại lỗi:
- `ClassNotFoundException`: mã đang cố nạp một lớp theo tên nhưng không tìm được trên classpath/module path tại thời điểm nạp.
- `NoClassDefFoundError`: JVM cần một định nghĩa lớp tại runtime nhưng không thể nạp được (thường do thiếu dependency, cũng có thể do lớp khởi tạo thất bại).

Với Spring Boot executable JAR, cấu trúc thường có `BOOT-INF/classes` (mã/tài nguyên ứng dụng) và `BOOT-INF/lib` (các dependency JAR). **Spring Boot launcher** thiết lập cách nạp các JAR lồng bên trong; không giả định rằng lệnh `java -cp app.jar ...` của Java thuần sẽ tự đọc các JAR lồng nhau. Chạy ứng dụng đóng gói bằng `java -jar app.jar`. Khi dùng `-jar`, Java launcher không sử dụng lựa chọn `-cp` như một classpath bổ sung cho ứng dụng.

## 6. Lifecycle — các công việc của build diễn ra theo trình tự nào?

### Maven: lifecycle, phase và plugin goal

Maven có các lifecycle chuẩn như **default**, **clean** và **site**. Lifecycle `default` gồm các phase theo thứ tự; chạy một phase sẽ chạy các phase đứng trước cần thiết trong cùng lifecycle. Ví dụ:

| Lệnh/phase | Công việc chính |
|---|---|
| `mvn validate` | Kiểm tra thông tin dự án |
| `mvn compile` | Biên dịch mã chính (sau các phase trước đó) |
| `mvn test` | Biên dịch và chạy unit test theo cấu hình |
| `mvn package` | Đóng gói artifact, ví dụ JAR |
| `mvn verify` | Chạy kiểm tra để xác nhận artifact phù hợp |
| `mvn install` | Cài artifact vào local Maven repository |
| `mvn deploy` | Xuất bản artifact vào remote repository đã cấu hình |

`mvn clean package` chạy phase `clean` thuộc lifecycle `clean` trước, sau đó chạy đến `package` trong lifecycle `default`. `clean` không phải phase của lifecycle `default`. `deploy` trong Maven là **xuất bản artifact vào repository**, không có nghĩa tự triển khai ứng dụng lên production.

**Plugin goal** là hành động cụ thể do plugin thực hiện (ví dụ `compiler:compile` hoặc `spring-boot:repackage`); Maven ánh xạ các goal vào phase theo packaging và cấu hình plugin. Có thể gọi goal trực tiếp, chẳng hạn `mvn dependency:tree`, mà không đồng nghĩa chạy toàn bộ phase `package`.

### Gradle: đồ thị task thay vì Maven phase

Gradle mô hình hóa build bằng **task** và quan hệ phụ thuộc giữa các task. Plugin `java` cung cấp những task như `compileJava`, `test`, `jar`, `build`. Spring Boot Gradle plugin thêm `bootJar` và `bootRun` cho dự án phù hợp. Khi chạy `gradle build`, Gradle thực hiện các task cần thiết theo đồ thị phụ thuộc; không có chuỗi phase mặc định `validate -> compile -> ... -> deploy` giống Maven.

```bash
# Chạy một task và những task mà nó phụ thuộc
./gradlew build

# Tạo executable JAR của Spring Boot
./gradlew bootJar

# Chạy ứng dụng trực tiếp từ project
./gradlew bootRun

# Xem đồ thị task được lên kế hoạch mà chưa thực thi
./gradlew build --dry-run
```

Task có thể được bỏ qua khi đầu vào/đầu ra không đổi hoặc tận dụng cache khi hợp lệ. Vì vậy log `UP-TO-DATE`/`FROM-CACHE` không nhất thiết nghĩa là task chưa được xét đến.

## 7. Ví dụ nối đủ năm khái niệm trong dự án Spring Boot

Ví dụ dùng **Java 17** và phiên bản Spring Boot **3.5.0** để các đoạn cấu hình có phiên bản cụ thể, có thể áp dụng cùng nhau. Đây là phiên bản minh họa; dự án thực tế cần chọn phiên bản hiện còn được hỗ trợ và cập nhật bản vá. Chọn **Maven hoặc Gradle**, không đặt hai cấu hình dưới đây vào một build rồi giả định chúng tự đồng bộ.

### Phương án Maven

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>build-terms-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

Không khai báo `version` riêng cho hai starter vì parent quản lý các phiên bản tương ứng; bản thân hai thẻ `dependency` mới làm chúng được sử dụng.

Tạo `src/main/java/com/example/buildterms/BuildTermsApplication.java`:

```java
package com.example.buildterms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BuildTermsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BuildTermsApplication.class, args);
    }
}
```

Yêu cầu: JDK 17+ và Maven khả dụng, có kết nối hoặc cache đủ dependency. Chạy tại thư mục chứa `pom.xml`:

```bash
mvn clean package
java -jar target/build-terms-demo-0.0.1-SNAPSHOT.jar
```

Lệnh đầu giải quyết dependency từ repository, biên dịch, kiểm thử và tạo artifact. Spring Boot Maven plugin `repackage` tạo executable JAR tại đường dẫn nêu trên. Lệnh sau chạy ứng dụng qua Boot launcher; startup log phụ thuộc cấu hình/môi trường nên không giả định một dòng stdout cố định. Dự án dùng `spring-boot-starter` (không phải starter web), vì vậy không có HTTP endpoint tự động mở trên cổng 8080.

### Phương án Gradle tương đương

Có thể tái sử dụng đúng file Java phía trên trong dự án dùng Gradle. Tạo `settings.gradle`:

```groovy
rootProject.name = 'build-terms-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Ở đây `platform` nhập các ràng buộc phiên bản từ Spring Boot BOM; `implementation` và `testImplementation` mới đưa starter vào đồ thị dependency. Với Gradle đã cài hoặc Gradle Wrapper đã được tạo cho dự án:

```bash
./gradlew clean bootJar
java -jar build/libs/build-terms-demo-0.0.1-SNAPSHOT.jar
```

Trên Windows thay `./gradlew` bằng `gradlew.bat`. Task `bootJar` đóng gói ứng dụng chạy được, còn task `jar` của Java plugin tạo JAR thông thường; chúng không thay thế nhau cho mọi mục đích sử dụng.

### Theo dõi một build từ đầu đến cuối

1. **Artifact đích:** `com.example:build-terms-demo:0.0.1-SNAPSHOT` sẽ thành JAR ứng dụng.
2. **Dependency:** `spring-boot-starter` và `spring-boot-starter-test` được khai báo; starter có dependency bắc cầu.
3. **Repository:** Maven/Gradle tra Maven Central và cache theo cấu hình để lấy các artifact còn thiếu.
4. **Classpath:** compiler dùng compile classpath; test có thêm thư viện kiểm thử; chạy ứng dụng dùng runtime dependency.
5. **Lifecycle/task:** Maven đi đến phase `package`, Gradle chạy task `bootJar` cùng các task phụ thuộc; Spring Boot đóng gói executable JAR.
6. **Runtime:** `java -jar` kích hoạt Boot launcher để truy cập classes và dependency trong JAR.

## 8. Lỗi hay gặp và cách xác định đúng tầng

| Triệu chứng | Khái niệm cần kiểm tra | Việc nên làm |
|---|---|---|
| `Could not resolve ...` / `artifact not found` | Repository + dependency | Kiểm tra tọa độ/phiên bản, repository, mạng, xác thực và cache |
| Biên dịch báo `package ... does not exist` | Compile classpath | Kiểm tra dependency đã khai báo với scope/configuration phù hợp và đã resolve |
| Test chạy được nhưng `java -jar` lỗi thiếu class | Runtime classpath + packaging | Kiểm tra `test`/`provided`/`compileOnly`, transitive exclusions và các dependency runtime |
| JAR chạy bằng `java -jar` báo không có main manifest | Artifact + packaging | Kiểm tra JAR được tạo bởi `bootJar`/`repackage` hay chỉ là JAR thường |
| `mvn package` và `mvn install` cho cảm giác khác nhau | Maven lifecycle | `install` còn đưa artifact vào local repository; `package` chưa làm việc đó |
| `gradle build` không thấy một bước chạy lại | Task graph/cache | Xem `--dry-run`, `--info` và trạng thái `UP-TO-DATE`/`FROM-CACHE` |
| Chạy JAR rồi không có endpoint HTTP | Dependency + ứng dụng | `spring-boot-starter` đơn thuần không tạo web server; cần web starter và endpoint tương ứng |

**Cách ghi nhớ:** artifact là **cái gì** được tạo/dùng; dependency là **cái gì đang cần**; repository là **lấy từ đâu**; classpath là **tìm lớp ở đâu**; lifecycle/task graph là **làm việc nào và theo thứ tự nào**. Hiểu ranh giới này giúp truy lỗi build đúng nơi thay vì sửa ngẫu nhiên version hoặc lệnh chạy.