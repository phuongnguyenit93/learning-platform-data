# Xác định lớp main tự động và cấu hình khi có nhiều điểm khởi động trong Spring Boot

## 1. Mục tiêu và bài toán

Khi đóng gói một dự án Spring Boot thành **JAR thực thi**, Maven hoặc Gradle cần biết **lớp Java nào chứa điểm vào ứng dụng**. Với một lớp có phương thức `public static void main(String[] args)`, công cụ build thường tự phát hiện được. Nhưng khi repository có nhiều lớp main — chẳng hạn ứng dụng API, tiến trình batch, công cụ dòng lệnh hoặc mã hỗ trợ — việc tự phát hiện có thể trở nên mơ hồ hoặc chọn không đúng ý định.

Sau bài học, bạn có thể:

1. Giải thích **lớp main của ứng dụng**, cách Spring Boot Maven/Gradle plugin tìm lớp này và giới hạn của auto-detection.
2. Phân biệt manifest **`Main-Class`** (Spring Boot launcher) với **`Start-Class`** (lớp main do bạn viết) trong executable JAR.
3. Cấu hình rõ ràng main class cho **Maven Spring Boot Plugin** (`start-class` khi kế thừa Parent, `mainClass` khi cấu hình trực tiếp) và **Gradle Spring Boot Plugin** (`springBoot.mainClass`, `bootJar.mainClass`, `bootRun.mainClass`).
4. Thiết kế và chạy được project Java 17+ có **hai điểm khởi động**, xác minh lớp nào được đóng gói và thực thi.
5. Đánh giá khi nào cần một JAR với một entry point, khi nào nên chia thành nhiều module/artifact; tránh phát hành các JAR khác nội dung nhưng cùng tên/phiên bản.
6. Chẩn đoán lỗi “không tìm thấy main class”, “không xác định được main class”, sai manifest hoặc JAR không thể chạy bằng `java -jar`.

**Giả định ví dụ:** Spring Boot **3.3.5**, Java **17**, Maven Wrapper hoặc Gradle Wrapper tương thích. Các phiên bản dùng làm minh họa nhất quán, **không phải chỉ dẫn nâng dự án thực tế lên bản này**. Với Spring Boot release khác, luôn kiểm tra tài liệu đúng version vì một số tên launcher và cách ưu tiên chọn main class đã thay đổi theo thời gian.

## 2. Có ba khái niệm “main” rất dễ nhầm

### 2.1. Java application main method

Ví dụ lớp Java có điểm vào:

~~~java
package com.example.demo;

public class DemoApplication {
    public static void main(String[] args) {
        System.out.println("ENTRY=DEMO");
    }
}
~~~

Đây là class Java độc lập có thể chạy trực tiếp. File phải đặt ở `src/main/java/com/example/demo/DemoApplication.java` trong project Maven/Gradle, hoặc tự biên dịch và chạy bằng JDK:

~~~bash
javac -d out src/main/java/com/example/demo/DemoApplication.java
java -cp out com.example.demo.DemoApplication
~~~

Output chính xác:

~~~text
ENTRY=DEMO
~~~

Công thức nhận diện Java main thông thường là **`public static void main(String[] args)`** (hoặc khai báo tham số tương đương như `String... args`). Một phương thức tên `main` nhưng không `static`, sai tham số hoặc không truy cập được sẽ không là entry point tiêu chuẩn mà các plugin ở ví dụ này tìm kiếm.

### 2.2. Lớp ứng dụng Spring Boot

Một Spring Boot application thường có dạng:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Ở đây **Java main** gọi `SpringApplication.run(...)` để khởi tạo `ApplicationContext`. Annotation `@SpringBootApplication` kết hợp các chức năng như auto-configuration và component scanning; nó **không tự sinh phương thức main**. Chỉ đánh dấu `@SpringBootApplication` trên lớp không có main không khiến lớp ấy trở thành entry point hợp lệ cho cấu hình đóng gói tiêu chuẩn.

### 2.3. `Main-Class` và `Start-Class` trong manifest

Khi Spring Boot đóng gói một **executable JAR** theo layout JAR thông dụng, `META-INF/MANIFEST.MF` thường chứa hai mục quan trọng:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.DemoApplication
~~~

Đây là **trích đoạn manifest điển hình của Spring Boot 3.3**, không phải toàn bộ manifest. Vị trí và tên launcher có thể khác giữa các phiên bản/layout.

- **`Main-Class`**: lớp mà JVM gọi trước khi thực thi `java -jar app.jar`. Với Spring Boot executable JAR thông thường, đây là **Boot launcher**. Launcher thiết lập classloader để tìm các JAR dependency lồng bên trong archive.
- **`Start-Class`**: lớp ứng dụng do bạn viết, chứa phương thức main mà launcher sẽ gọi sau khi thiết lập classpath.
- **`BOOT-INF/classes/`**: chứa class/resource đã biên dịch của ứng dụng.
- **`BOOT-INF/lib/`**: chứa dependency JAR lồng trong executable archive.

Vì vậy, **đừng nhầm “chọn lớp main của ứng dụng” với “thay `Main-Class` của manifest thành lớp của mình”**. Nếu thay `Main-Class` của một Spring Boot fat JAR thành `com.example.demo.DemoApplication` bằng Maven Jar Plugin/Gradle Jar manifest, bạn có thể bỏ qua launcher cần thiết để nạp nested dependencies. Với Spring Boot plugin, phần cần cấu hình thường là **`mainClass` / `Start-Class`**, không phải ghi đè launcher tùy tiện.

## 3. Spring Boot tự phát hiện main class như thế nào?

**Điểm khởi đầu của auto-detection** là các class đã được biên dịch trong **main source set** của ứng dụng:

- **Gradle `bootJar` và `bootRun`**: Spring Boot Gradle plugin có khả năng dò lớp chứa `public static void main(String[])` trong output của main source set. Nếu xác định được ứng viên phù hợp, nó đặt ứng viên làm main class của task.
- **Maven `spring-boot:repackage` / `spring-boot:run`**: Spring Boot Maven plugin tìm lớp có phương thức main trong compiled classes. Cách ưu tiên ứng viên và xử lý nhiều lớp có thể khác giữa các phiên bản plugin; tài liệu hiện đại nêu ưu tiên lớp có `@SpringBootApplication` khi phù hợp. Dù vậy, **không nên dựa vào hành vi lựa chọn ngầm khi có nhiều ứng viên**.
- **Lớp trong `src/test/java`** không phải nguồn entry point của một executable JAR ứng dụng thông thường vì test classes không thuộc main output dùng để repackage/bootJar. Một main method trong bộ test không nhất thiết gây xung đột; cần xem cấu hình nguồn/thư mục thực tế của build.

### Khi nào tự động tìm main thường ổn?

Khi project có **một lớp main rõ ràng**, cách tự động đơn giản và giảm cấu hình:

~~~text
src/main/java/com/example/demo/DemoApplication.java
    └── public static void main(String[] args)
~~~

Chạy `package` (Maven) hoặc `bootJar` (Gradle); sau đó kiểm tra `Start-Class` trong archive. Đây vẫn là bước xác nhận cần thiết khi phát hành.

### Khi nào tự động tìm main không còn an toàn?

- Có **hai hoặc nhiều lớp** trong main output đều có main method.
- Có main method trong lớp công cụ CLI được thêm sau, hoặc ứng dụng được tách thành **API + batch**.
- Một lớp `@SpringBootApplication` được di chuyển/đổi package và main class cấu hình cũ vẫn trỏ vào tên cũ.
- Build multi-module vô tình đưa nhiều output của module khác nhau lên classpath task đóng gói.
- Plugin Maven và Gradle hoặc các phiên bản khác nhau có **quy tắc tìm main không giống hệt nhau**.

Một số plugin/build có thể báo lỗi do main class mơ hồ, một số trường hợp có thể chọn một ứng viên không như bạn mong muốn. **Không coi thứ tự quét class, thứ tự file, hay việc local build “tình cờ thành công” là hợp đồng ổn định.** Khi có từ hai entry point, hãy chỉ định **tên class đầy đủ gồm package (FQCN)** một cách tường minh và kiểm tra artifact.

## 4. Ví dụ thực hành có hai điểm khởi động độc lập

Để hiểu rõ tình huống, tạo một dự án Spring Boot tên `entrypoint-demo` với **hai application class ở hai package khác nhau**:

~~~text
entrypoint-demo/
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    ├── store/
                    │   └── StoreApplication.java
                    └── batch/
                        └── BatchApplication.java
~~~

Hai package `com.example.store` và `com.example.batch` là các nhánh riêng, giúp mỗi `@SpringBootApplication` có **phạm vi component scan mặc định riêng**. Ví dụ chỉ dùng `spring-boot-starter`, không mở HTTP server, database hoặc scheduler. Nhờ vậy kết quả kiểm tra entry point không phụ thuộc service ngoài.

### 4.1. File `src/main/java/com/example/store/StoreApplication.java`

~~~java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        System.out.println("ENTRY=STORE");
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

### 4.2. File `src/main/java/com/example/batch/BatchApplication.java`

~~~java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchApplication {

    public static void main(String[] args) {
        System.out.println("ENTRY=BATCH");
        SpringApplication.run(BatchApplication.class, args);
    }
}
~~~

Cả hai class đều có phương thức main hợp lệ và đều là Spring Boot application. **Cố tình có nhiều ứng viên** để làm nổi bật yêu cầu chọn lớp khởi động khi đóng gói. Mục tiêu của ví dụ không phải chạy hai application cùng lúc trong một JVM.

Các chuỗi **`ENTRY=STORE`** và **`ENTRY=BATCH`** là dấu hiệu chính xác được in bởi mã Java. Sau đó Spring Boot có thể in banner/log startup với timestamp, PID và phiên bản khác nhau; **không dùng toàn bộ log làm stdout cố định**.

Khi thực sự triển khai, **Store** và **Batch** thường có đời sống khác nhau; nếu cả hai là hai ứng dụng độc lập cần phát hành, mô hình nhiều module/artifact tách biệt có thể phù hợp hơn việc đóng gói tùy biến một JAR chung.

## 5. Maven Spring Boot Plugin: khi chỉ có một điểm khởi động

### 5.1. Một `pom.xml` cơ sở có thể build

Dùng POM sau cho ví dụ ở mục 4; đây là **POM đầy đủ**, giả định repository đã có Maven Wrapper `mvnw` / `mvnw.cmd` và JDK 17:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>entrypoint-demo</artifactId>
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

Nếu chỉ có **một** main class trong `src/main/java`, `spring-boot-maven-plugin` thường sẽ tìm được để đóng gói. Nhưng ví dụ tại mục 4 có **hai** main class; hãy dùng cách tường minh ở phần tiếp theo để tránh phụ thuộc việc phát hiện tự động.

**Vì sao không cần khai báo goal `repackage`?** Trong dự án kế thừa `spring-boot-starter-parent`, execution `repackage` đã được parent cấu hình sẵn và được kích hoạt khi plugin `spring-boot-maven-plugin` được khai báo. Nếu dự án **không kế thừa parent**, phải xem phần cấu hình explicit execution ở mục 7.

**Đóng gói**: `./mvnw clean package` tạo archive từ compiled classes và dependencies. Trước `repackage`, Maven Jar Plugin tạo JAR chuẩn; `repackage` tạo **Spring Boot executable JAR** với launcher, classpath layout và `Start-Class`.

## 6. Maven có Spring Boot Starter Parent: dùng `start-class`

Với `pom.xml` ở mục 5, thêm **một property** trong chính `<properties>` đang tồn tại:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>com.example.store.StoreApplication</start-class>
</properties>
~~~

Đây là **đoạn thay thế cho phần `<properties>` trong POM ở mục 5**, không phải file `pom.xml` độc lập. `spring-boot-starter-parent` đưa property `start-class` vào cấu hình Spring Boot Maven plugin theo convention của parent, giúp các goal cần main class biết rõ lớp cần chạy.

### Build và chạy bản Store

Linux/macOS:

~~~bash
./mvnw --version
./mvnw clean package
java -jar target/entrypoint-demo-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean package
java -jar .\target\entrypoint-demo-0.0.1-SNAPSHOT.jar
~~~

**Kết quả có thể kiểm chứng:** trong output chạy ứng dụng sẽ có dòng:

~~~text
ENTRY=STORE
~~~

Ngoài dòng này còn có banner/log Spring Boot (có thể không cố định). Vì example chỉ dùng starter cơ bản, ứng dụng thường hoàn tất startup và kết thúc thay vì lắng nghe HTTP port; đó không phải lỗi launcher.

### Đổi sang bản Batch

Chỉ đổi property:

~~~xml
<start-class>com.example.batch.BatchApplication</start-class>
~~~

Chạy lại `clean package` rồi `java -jar` cùng tên JAR. Lần này marker chính xác là:

~~~text
ENTRY=BATCH
~~~

**Quan trọng:** hai lần build đã tạo ra **hai nội dung artifact khác nhau với cùng tên file** `entrypoint-demo-0.0.1-SNAPSHOT.jar`. Đây là phép thử học tập; **không xuất bản xen kẽ cả hai artifact dưới cùng tọa độ Maven/version như thể chúng giống nhau**. Nếu phải triển khai Store và Batch độc lập, nên chọn module hoặc classifier/artifact ID riêng cùng quy trình phát hành rõ ràng.

### Khi Maven project có nhiều entry point

Nếu không thiết lập `start-class`, Maven plugin có thể chọn lớp main không mong muốn hoặc báo không xác định được ứng viên tùy phiên bản/cấu hình. **Chọn tường minh** bằng FQCN là cách duy trì một điểm khởi động ổn định cho cả terminal, IDE, CI và runtime.

Nếu một lớp main được di chuyển package nhưng property vẫn trỏ lớp cũ, `repackage` hoặc việc chạy executable JAR có thể thất bại. Kiểm tra **FQCN sau biên dịch**, không chỉ tên file trong IDE.

## 7. Maven không kế thừa Starter Parent: dùng `mainClass` của plugin

Một dự án có corporate parent hoặc chỉ import `spring-boot-dependencies` BOM thường **không hưởng mọi plugin management và execution của `spring-boot-starter-parent`**. Trong trường hợp đó, nên đặt lựa chọn main class và repackage execution **trực tiếp ở Spring Boot Maven Plugin**.

Đoạn sau thuộc `<build><plugins>` của một POM đã thiết lập dependency/JDK/packaging riêng:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.5</version>
    <configuration>
        <mainClass>com.example.store.StoreApplication</mainClass>
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

**Đây là fragment XML**, không phải POM độc lập. Nhớ đặt đúng vị trí `<build><plugins>`, không đưa cấu hình `mainClass` vào `maven-jar-plugin`. Nếu project dùng Starter Parent và đã có plugin ở mục 5, **không tạo thêm một plugin trùng**; chỉ chọn một chiến lược cấu hình phù hợp.

`mainClass` cấu hình trực tiếp cho Spring Boot Maven Plugin và điều khiển lớp khởi động mà plugin dùng. `repackage` chạy sau khi Maven đã tạo JAR nguồn trong `package`; gọi riêng `./mvnw spring-boot:repackage` trên một workspace chưa có JAR nguồn có thể thất bại. Để build đầy đủ, dùng `./mvnw clean package` (khi execution đã gắn lifecycle), hoặc theo tài liệu plugin khi gọi goal cụ thể sau phase package.

Khi chỉ import BOM, BOM **chủ yếu quản lý phiên bản dependency**, không làm Maven tự biết nên repackage hoặc chọn lớp main. Đây là ranh giới quan trọng giữa **dependency management** và **build plugin configuration**.

## 8. Gradle Spring Boot Plugin: cách chọn lớp main cho executable JAR

### 8.1. Một ví dụ Groovy DSL có thể build

Với cùng hai file Java ở mục 4, chọn Gradle thay cho Maven. `settings.gradle`:

~~~groovy
rootProject.name = 'entrypoint-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
}

springBoot {
    mainClass = 'com.example.store.StoreApplication'
}
~~~

Gradle `java` plugin tạo main source set; Spring Boot plugin tạo task `bootJar` và `bootRun`; `io.spring.dependency-management` cùng Spring Boot plugin quản lý các phiên bản dependency qua BOM tương ứng. `springBoot.mainClass` là cấu hình **cấp dự án** để sử dụng một main class nhất quán cho các task Boot liên quan.

**Khi chỉ có một main class**, có thể bỏ block `springBoot { mainClass = ... }` và để Gradle tự tìm. **Khi có hai class**, giữ block tường minh như trên.

`repositories { mavenCentral() }` ở project là hợp lệ cho build mẫu chưa bật `FAIL_ON_PROJECT_REPOS`. Nếu project thật quản lý repositories tập trung ở settings, hãy dùng chính sách hiện có và **không** thêm project repository trái quy tắc.

### 8.2. Cách viết bằng Kotlin DSL

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "entrypoint-demo"
~~~

`build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}

springBoot {
    mainClass.set("com.example.store.StoreApplication")
}
~~~

Đây là **phương án thay thế** Groovy DSL; không đặt đồng thời cả `settings.gradle` và `settings.gradle.kts` trong cùng thư mục. Các file Java vẫn giống mục 4.

### 8.3. Dùng property trên `bootJar` để chỉ thay đổi archive

Nếu muốn chỉnh **riêng task đóng gói** thay vì cấu hình toàn dự án, trong `build.gradle` Groovy DSL:

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.store.StoreApplication'
}
~~~

Kotlin DSL:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    mainClass.set("com.example.store.StoreApplication")
}
~~~

Các đoạn này là **thay thế** block `springBoot.mainClass` trong ví dụ, không nên đồng thời dùng cả hai nếu đặt giá trị mâu thuẫn. Bản Kotlin đặt `import` ở đầu file build.

**Phân biệt phạm vi:** cấu hình trực tiếp `bootJar.mainClass` bảo đảm task `bootJar` biết entry point. Nó **không mặc nhiên** khiến task `bootRun` hoặc run configuration trong IDE chọn cùng một lớp. Để cả đóng gói và chạy tại chỗ đồng nhất, dùng **`springBoot.mainClass` cấp dự án**, hoặc cấu hình riêng cả hai task và kiểm chứng.

### 8.4. Cấu hình `bootRun` cho môi trường phát triển

Nếu chỉ muốn chạy một entry point cụ thể mà không xây JAR, Gradle dùng `bootRun`.

Groovy DSL:

~~~groovy
tasks.named('bootRun') {
    mainClass = 'com.example.batch.BatchApplication'
}
~~~

Kotlin DSL:

~~~kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    mainClass.set("com.example.batch.BatchApplication")
}
~~~

**Đoạn này chỉ điều khiển `bootRun`.** Nó không bắt buộc `bootJar` đổi main class. Trước khi giao artifact cho CI/production, kiểm tra rõ mục đích: nếu `bootRun` chạy Batch nhưng `bootJar` vẫn đóng Store, kết quả “chạy trên IDE được nhưng JAR chạy sai” là hợp lý do hai cấu hình khác nhau.

Có thể chọn `application.mainClass` khi dự án dùng thêm Gradle Application plugin. Tuy nhiên, với Spring Boot app tiêu chuẩn **không cần thêm Application plugin chỉ để chọn main**: `springBoot.mainClass` đã là cách rõ ràng hơn.

## 9. Chạy Gradle trên Windows và Linux, xác minh entry point

Trong dự án có Gradle Wrapper và cấu hình ở mục 8:

Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean bootJar
./gradlew bootRun
java -jar build/libs/entrypoint-demo-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean bootJar
.\gradlew.bat bootRun
java -jar .\build\libs\entrypoint-demo-0.0.1-SNAPSHOT.jar
~~~

Trong trường hợp đã đặt `springBoot.mainClass = com.example.store.StoreApplication`, cả `bootRun` và `java -jar` đều phải gọi ứng dụng Store. Dòng marker mong đợi trong cả hai lượt chạy là:

~~~text
ENTRY=STORE
~~~

Đổi `springBoot.mainClass` sang `com.example.batch.BatchApplication`, build lại và chạy JAR:

~~~text
ENTRY=BATCH
~~~

**Đừng bỏ qua `clean bootJar` khi thử đổi entry point:** nó giúp tránh đọc nhầm artifact cũ. Trong build bình thường, Gradle có cơ chế incremental/cache, nhưng khi kiểm tra cấu hình main class, bạn cần biết JAR đang chạy được sinh từ lần build nào.

Gradle Spring Boot plugin cũng có thể tạo **plain JAR** khi task `jar` vẫn bật; trong một số cấu hình file có classifier `-plain`. Đừng chạy nhầm `entrypoint-demo-...-plain.jar` rồi kết luận Boot launcher không hoạt động: plain JAR có thể không chứa nested dependencies và manifest phù hợp cho `java -jar`.

## 10. Kiểm tra `Start-Class` của artifact thay vì đoán từ log

Một cách xác nhận đáng tin là mở manifest của **đúng executable JAR được tạo từ lượt build mới nhất**:

~~~text
META-INF/MANIFEST.MF
~~~

Trong ví dụ Maven hoặc Gradle, hai thuộc tính quan trọng là:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.store.StoreApplication
~~~

Nếu cấu hình là Batch, dòng thứ hai phải thành:

~~~text
Start-Class: com.example.batch.BatchApplication
~~~

### 10.1. Linux/macOS: xem manifest mà không giải nén cả JAR

Giả sử có lệnh `unzip`:

~~~bash
# Maven, sau khi chạy ./mvnw clean package
unzip -p target/entrypoint-demo-0.0.1-SNAPSHOT.jar \
  META-INF/MANIFEST.MF

# Gradle, sau khi chạy ./gradlew clean bootJar
unzip -p build/libs/entrypoint-demo-0.0.1-SNAPSHOT.jar \
  META-INF/MANIFEST.MF
~~~

Đầu ra có thể gồm nhiều thuộc tính khác và được ngắt dòng theo quy tắc manifest. Hãy tìm đúng `Main-Class` và `Start-Class`, không coi trích đoạn ở trên là toàn bộ nội dung.

Nếu hệ thống chưa có `unzip`, công cụ `jar` đi kèm JDK có thể xem danh sách entry và giải nén manifest vào một **thư mục kiểm tra riêng**. Không cần sửa manifest bằng tay.

### 10.2. Windows PowerShell: dùng công cụ `jar` của JDK

Sau khi build, một cách kiểm tra **không cần cài unzip**:

~~~powershell
# Maven: chuẩn bị thư mục riêng để không ghi đè file project
New-Item -ItemType Directory -Force .\manifest-check | Out-Null
Push-Location .\manifest-check
jar xf ..\target\entrypoint-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
Get-Content .\META-INF\MANIFEST.MF
Pop-Location
~~~

Nếu dùng Gradle, trong lệnh `jar xf` thay đường dẫn bằng:

~~~powershell
jar xf ..\build\libs\entrypoint-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
~~~

Lệnh Gradle thay thế này cũng chạy **sau khi vào** `manifest-check`. Nếu PowerShell đang ở project root, đường dẫn `..\build` không chính xác: phải chọn đúng working directory. Dùng `Get-ChildItem .\target\*.jar` (Maven) hoặc `Get-ChildItem .\build\libs\*.jar` (Gradle) nếu tên JAR theo cấu hình thật khác ví dụ.

### 10.3. Kiểm tra cấu trúc nested JAR

Linux/macOS:

~~~bash
jar tf target/entrypoint-demo-0.0.1-SNAPSHOT.jar | grep '^BOOT-INF/'
~~~

Trong Gradle dùng path `build/libs/...`. Nếu chỉ có các class ở root và không có `BOOT-INF/classes` hoặc `BOOT-INF/lib`, bạn có thể đang xem **plain JAR**, chưa chạy `repackage` hoặc `bootJar`, hoặc đã chọn layout/packaging khác. Không sửa `Start-Class` để chữa một archive vốn không có loader/dependencies đúng kiểu.

**Manifest là bằng chứng build artifact**, không chứng minh ứng dụng chắc chắn khởi tạo thành công: nó vẫn có thể lỗi cấu hình, database hoặc Java runtime khi chạy. Vì vậy, kiểm tra **manifest và `java -jar`** là hai bước bổ sung nhau.

## 11. Nếu muốn chọn lớp main theo build profile/variant

Một số nhóm cần thử hai entry point từ cùng source code. Có thể cấu hình **build variant một cách chủ đích**, nhưng phải tránh đưa hai artifact khác nội dung dưới cùng tọa độ phát hành.

### 11.1. Maven profiles với Starter Parent

Nếu dự án đã dùng property `start-class` ở Parent, có thể **chuyển lựa chọn sang profile**:

~~~xml
<profiles>
    <profile>
        <id>store</id>
        <properties>
            <start-class>com.example.store.StoreApplication</start-class>
        </properties>
    </profile>
    <profile>
        <id>batch</id>
        <properties>
            <start-class>com.example.batch.BatchApplication</start-class>
        </properties>
    </profile>
</profiles>
~~~

Đây là **fragment đặt dưới `<project>`**, không phải POM độc lập. Nếu áp dụng, hãy bỏ property `start-class` cố định ở mục 6 hoặc đặt fallback rõ ràng. Chạy:

~~~bash
./mvnw -Pstore clean package
# hoặc:
./mvnw -Pbatch clean package
~~~

Sau mỗi lượt, xem `Start-Class` để bảo đảm profile đã thực sự tác động. Không bật đồng thời `-Pstore,batch` vì chúng cùng thay đổi một property, tạo conflict khó kiểm soát. **Tên JAR mặc định có thể giống nhau** giữa các lần build. Nếu cần phát hành cả hai, nên tạo module/artifact riêng hoặc cấu hình classifier/phương án phát hành chính thức.

### 11.2. Gradle property để chọn variant khi build

Trong Groovy DSL có thể đặt main class theo một Gradle project property:

~~~groovy
springBoot {
    mainClass = providers.gradleProperty('appMain')
        .orElse('com.example.store.StoreApplication')
}
~~~

Đoạn này là **cách thay thế** cho `springBoot.mainClass` cố định. Chạy:

~~~bash
./gradlew clean bootJar
./gradlew clean bootJar -PappMain=com.example.batch.BatchApplication
~~~

Lệnh đầu chọn mặc định Store, lệnh sau chọn Batch. **Gradle project property `appMain` không phải Spring runtime property**; nó được xử lý ở lúc cấu hình Gradle. Khi dùng tùy chọn này trên CI, ghi rõ `-PappMain=...` trong pipeline, ghi lại giá trị đã chọn và kiểm tra manifest. Không dùng một property không được kiểm soát để âm thầm thay entry point của artifact phát hành.

Kotlin DSL tương đương:

~~~kotlin
springBoot {
    mainClass.set(
        providers.gradleProperty("appMain")
            .orElse("com.example.store.StoreApplication")
    )
}
~~~

**Lưu ý kỹ thuật:** Nếu project áp dụng thêm cấu hình `bootJar.mainClass` hoặc `bootRun.mainClass` với giá trị khác, cần xác định cái nào thực sự được task sử dụng. Đừng kết hợp các cách điều khiển cùng một thuộc tính mà không có lý do và test cụ thể.

## 12. Một JAR, hai entry point hay hai JAR riêng?

Có **hai lớp có main method** không có nghĩa một executable JAR thông thường sẽ chạy cả hai theo thứ tự. Trong layout Spring Boot executable JAR cơ bản, một manifest sẽ chỉ có **một `Start-Class`** được chọn cho lệnh `java -jar` mặc định.

| Nhu cầu | Thiết kế phù hợp | Cần lưu ý |
| --- | --- | --- |
| Một dịch vụ Spring Boot, main khác chỉ là công cụ phát triển | Chọn main của dịch vụ rõ ràng bằng build config | Đừng để công cụ CLI vô tình trở thành entry point |
| Thử Store hoặc Batch bằng lệnh build | Dùng property/profile như mục 11 trong branch thử nghiệm | Đọc lại manifest sau **mỗi** build, tránh chạy JAR cũ |
| Store và Batch là hai ứng dụng triển khai độc lập | **Multi-module** hoặc hai project/artifact riêng, mỗi module có một entry point | Versioning, CI, Docker image, cấu hình và runtime độc lập |
| Hai artifact đóng gói cùng source nhưng khác startup | Nhiều task packaging với classifier/name riêng khi thiết kế cẩn thận | Không dùng cùng tên và cùng Maven GAV cho hai nội dung |
| Muốn chọn class lúc chạy qua `java -cp app.jar ...` | Không dùng trực tiếp cách này với Spring Boot nested JAR mặc định | Nested dependencies không được Java classpath thông thường đọc như flat JAR |

**Gợi ý cấu trúc multi-module:**

~~~text
root/
├── shared-core/              # code dùng chung, không cần executable main
├── store-app/                # StoreApplication, tạo Store executable JAR
└── batch-app/                # BatchApplication, tạo Batch executable JAR
~~~

Mỗi module app sẽ có plugin đóng gói, dependency và tên artifact thích hợp. `shared-core` dùng library plugin thông thường nếu không cần Boot launcher. Khi đó việc auto-detection trong mỗi module đơn giản hơn vì mỗi module thường có một entry point rõ ràng.

Có launcher/layout nâng cao như `PropertiesLauncher` và thuộc tính `loader.main`, nhưng đó **không phải** lý do để tùy tiện ghi đè manifest hoặc giả định `java -cp` hoạt động với nested JAR. Với nhu cầu deploy hai ứng dụng thực tế, **artifact riêng dễ hiểu, kiểm thử và vận hành hơn**.

## 13. Hiểu đúng khác nhau giữa `bootRun`, Maven `spring-boot:run` và `java -jar`

| Cách chạy | Nguồn classpath | Entry point được dùng |
| --- | --- | --- |
| `./gradlew bootRun` | Main source set output + runtime classpath của Gradle | `bootRun.mainClass` hoặc cấu hình Spring Boot project-wide/auto-detection |
| `./mvnw spring-boot:run` | Compiled classes + dependencies từ mô hình Maven | Cấu hình Spring Boot Maven plugin/auto-detection |
| `java -jar target/app.jar` | Nội dung executable archive Maven đã `repackage` | `Main-Class` launcher → `Start-Class` đã ghi trong manifest |
| `java -jar build/libs/app.jar` | Nội dung executable archive Gradle `bootJar` | `Main-Class` launcher → `Start-Class` đã ghi trong manifest |

`bootRun` và `spring-boot:run` chạy ứng dụng **tại chỗ**, không bắt buộc phải tạo JAR trước. Ngược lại, `java -jar` đọc đúng archive đã đóng gói; thay source code hoặc build config sau khi JAR được tạo **không tự cập nhật** manifest của JAR cũ.

Nếu IDE chạy được Store nhưng deployed JAR chạy Batch, hãy kiểm tra:

1. IDE Run Configuration đang chọn main class nào?
2. `bootRun` / `spring-boot:run` có mainClass riêng không?
3. Build vừa tạo JAR nào, thuộc module nào, có classifier/version gì?
4. Manifest của **chính file JAR được deploy** chứa `Start-Class` nào?

**Không** giải quyết khác biệt này bằng cách chỉ đổi cấu hình `spring.profiles.active`: Spring runtime profile chọn tập cấu hình/bean **sau khi** đã gọi một lớp main. Nó không thay entry point được ghi trong manifest.

## 14. Các lỗi thường gặp và cách xử lý đúng tầng

| Dấu hiệu | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Gradle báo không xác định main class của `bootJar` | Không có main method trong main output hoặc nhiều ứng viên | Kiểm tra `src/main/java`, package, compile output; cấu hình `springBoot.mainClass` hoặc `bootJar.mainClass` |
| Maven `repackage` không tìm được main class | Plugin không xác định được ứng viên, class không được compile hoặc package/classname sai | Chỉ định `start-class` (với Parent) hay `<mainClass>` của Spring Boot Maven Plugin |
| Maven/Gradle “build thành công” nhưng JAR chạy sai chương trình | Auto-detection/chọn biến thể sai hoặc chạy nhầm archive cũ | Kiểm tra manifest `Start-Class` và marker `ENTRY=...`, kiểm tra lại tên path/module |
| `ClassNotFoundException` / `Could not find or load main class` | FQCN trong config sai, class đã chuyển package, output không chứa class | So sánh tên package/file/bytecode với `Start-Class`, rebuild sạch |
| `no main manifest attribute` | Chạy plain JAR hoặc plugin repackage chưa thực thi | Maven: kiểm tra `spring-boot-maven-plugin` + goal repackage; Gradle: chạy `bootJar` |
| `NoClassDefFoundError` hoặc không tìm thấy Spring class khi chạy | Chạy plain JAR thiếu nested libraries hoặc archive bị chỉnh sai | Chạy đúng Boot executable JAR, kiểm tra `BOOT-INF/lib`, đừng sửa launcher manifest thủ công |
| `Main-Class` hiện `JarLauncher`, không phải `StoreApplication` | Đây là hành vi **đúng** của executable JAR Spring Boot | Đọc tiếp `Start-Class`; không cố thay launcher bằng main của app |
| `UnsupportedClassVersionError` lúc chạy | JDK runtime cũ hơn bytecode của class/dependency | Đối chiếu `java -version`, compiler toolchain và Java target |
| IDE chạy Store nhưng `java -jar` chạy Batch | IDE run config hoặc `bootRun` khác config đóng gói, hoặc JAR cũ | Đối chiếu task-level vs project-wide mainClass, manifest và timestamp build |
| Một module được chọn đúng, module khác sai | Multi-module có plugin/configuration không đồng nhất | Kiểm tra mainClass và output của từng module, dùng `:module:bootJar` hoặc `-pl` |
| Chạy app chỉ in vài log rồi thoát | Project chỉ có `spring-boot-starter`, không có web server/job dài hạn | Đây có thể bình thường; xem exception và exit code trước khi quy lỗi main |
| Bật `spring.profiles.active=batch` nhưng vẫn chạy Store | Spring profile là runtime config, không phải Java entry point | Chọn `Start-Class`/mainClass đúng ở build-time |
| Maven đặt `<start-class>` nhưng không có hiệu lực | Project không inherit `spring-boot-starter-parent` hoặc plugin config khác ghi đè | Đọc effective POM; dùng `<mainClass>` trong Spring Boot Plugin theo cấu hình project |
| Gói WAR hoặc layout `NONE` có manifest khác mẫu | Layout đóng gói khác JAR executable thông thường | Đọc config plugin/format; không ép kết luận từ ví dụ `JarLauncher` |
| JAR Store và Batch có cùng filename/version | Build theo variant đã ghi đè archive cùng tọa độ | Đặt tên/classifier/module riêng hoặc dùng quy trình phát hành tách biệt |

**Đừng chữa lỗi chọn entry point bằng cách xóa cache hàng loạt hoặc nâng framework tùy tiện.** Trước tiên ghi lại **lệnh build, plugin version, classpath nguồn, cấu hình mainClass, tên artifact, `Main-Class`, `Start-Class` và lệnh chạy thực tế**.

## 15. Kiểm tra main class trên CI và bảo đảm artifact đúng

CI nên dùng **JDK và Wrapper được dự án kiểm soát**, không dựa vào entry point được IDE tự gợi ý. Một job đúng cần có khả năng:

- Chạy Maven `clean package` hoặc Gradle `clean bootJar` ở đúng module.
- Xác định **một artifact duy nhất** cần triển khai thay vì chọn file JAR đầu tiên trong thư mục có thể chứa `-plain.jar`, `.original` hoặc bản cũ.
- Đọc manifest và xác nhận `Start-Class` khớp FQCN của ứng dụng dự kiến.
- Thực thi smoke test phù hợp (`java -jar` với runtime/config được cấp), đối chiếu marker hoặc health endpoint mà chính ứng dụng cung cấp.
- Lưu artifact dưới tên/phiên bản rõ ràng để không nhầm hai biến thể; cùng một commit nhưng khác profile/property phải được ghi nhận.
- Nếu project deploy nhiều chương trình, **tách pipeline/artifact theo module** thay vì tạo một “fat JAR” có hành vi thay đổi ngầm.

Ví dụ đoạn kiểm tra manifest cho CI Linux có `unzip`, sau khi build Maven:

~~~bash
jar_path="target/entrypoint-demo-0.0.1-SNAPSHOT.jar"
unzip -p "$jar_path" META-INF/MANIFEST.MF |
  grep -F 'Start-Class: com.example.store.StoreApplication'
~~~

Đây là lệnh kiểm tra **manifest có chứa dòng mong muốn**, không chạy ứng dụng. Khi dùng Linux shell với `set -o pipefail` hoặc shell CI có cơ chế fail-on-error thích hợp, lệnh kiểm tra thất bại sẽ khiến job không được coi là thành công. Nếu `unzip` không được cài, có thể dùng công cụ `jar` của JDK để giải nén manifest vào thư mục tạm rồi kiểm tra nội dung.

**Nhớ kiểm tra runtime:** manifest đúng chưa bảo đảm app chạy được trong image server. Java target, dependencies, Spring configuration và quyền truy cập dịch vụ bên ngoài phải được kiểm thử trong pipeline hoặc môi trường tích hợp phù hợp.

## 16. Bài thực hành có tiêu chí nghiệm thu

Dùng **một** trong hai công cụ Maven hoặc Gradle, tại branch thử nghiệm của project Spring Boot:

1. Tạo hai file `StoreApplication.java` và `BatchApplication.java` như mục 4, bảo đảm mỗi class có `public static void main(String[] args)` và in marker khác nhau.
2. Chọn POM Maven ở mục 5 hoặc Gradle build ở mục 8; **không cần dùng cả Maven và Gradle trong cùng project**.
3. Trước tiên thử build không khai báo main class: quan sát output và ghi nhận liệu plugin version hiện tại tự chọn hay báo mơ hồ. **Không dùng kết quả tình cờ ấy làm cấu hình phát hành.**
4. Chọn Store rõ ràng bằng `<start-class>` (Maven Parent) hoặc `springBoot.mainClass` (Gradle).
5. Chạy `clean package` / `clean bootJar`, rồi đọc `Start-Class` trong manifest. Xác nhận nó bằng `com.example.store.StoreApplication`.
6. Chạy `java -jar` với **đúng JAR** vừa build, quan sát marker `ENTRY=STORE`.
7. Đổi sang Batch, build lại và kiểm tra `Start-Class` + marker `ENTRY=BATCH`.
8. Nếu Gradle, thử cố tình để `bootRun` và `bootJar` khác entry point: so sánh kết quả và ghi rõ vì sao hai lệnh khác nhau. Sau đó khôi phục cấu hình nhất quán.
9. Ghi quyết định thiết kế: đây chỉ là **hai biến thể để học**, hay là **hai ứng dụng cần artifact độc lập**? Nếu là trường hợp thứ hai, đề xuất chia module/artifact.
10. Khôi phục cấu hình/main class chuẩn của dự án, chạy lại build/test và xác nhận CI có thể đọc được manifest.

**Hoàn thành bài khi** bạn trả lời chính xác: plugin tự phát hiện main trong trường hợp nào; khi có nhiều main cần khai báo ở đâu; `Main-Class` khác `Start-Class` ra sao; vì sao `java -jar` có thể chạy khác IDE; và làm thế nào chứng minh **đúng entry point nằm trong đúng artifact đang triển khai**.

## Tài liệu chính thức

- [Spring Boot Maven Plugin – Using the Plugin / Specifying Main Class](https://docs.spring.io/spring-boot/maven-plugin/using.html)
- [Spring Boot Maven Plugin – Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Maven Plugin – Repackage Goal](https://docs.spring.io/spring-boot/maven-plugin/repackage.html)
- [Spring Boot Gradle Plugin – Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Spring Boot Gradle Plugin – Running Your Application](https://docs.spring.io/spring-boot/gradle-plugin/running.html)
- [Spring Boot – Executable JAR Specification, Launching](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html)
- [Apache Maven – Introduction to Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Gradle – Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
