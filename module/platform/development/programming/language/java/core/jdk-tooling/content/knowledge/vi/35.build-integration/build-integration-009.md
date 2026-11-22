# Xây dựng ứng dụng Java theo module

**Module build** là quy trình biên dịch, kiểm tra dependency, đóng gói và chạy ứng dụng Java sử dụng Java Platform Module System (JPMS). Một dự án modular chia code thành các module có tên; mỗi module khai báo dependency và package API được phép truy cập trong file **module-info.java**.

Khi build đúng cấu trúc, compiler phát hiện dependency bị thiếu hoặc package chưa được export; JAR giữ module descriptor; runtime giải quyết module graph trên module path; và **jlink** có thể tạo runtime image chỉ chứa các module cần thiết.

Bài này đi từ cấu trúc source, module descriptor và lệnh javac/jar đến jdeps, jlink, Maven, Gradle, CI và lỗi thường gặp. Ví dụ được xây dựng theo Java 17+ và đã kiểm tra trên OpenJDK 24.0.2, Maven 3.9.12 và Gradle 9.2.1.

## 1. Java module là gì?

Module là đơn vị đóng gói và quản lý dependency ở mức cao hơn package. Một module có:

- Tên duy nhất trong module graph.
- Module descriptor, thường là module-info.java.
- Các package được export để module khác truy cập.
- Các dependency khai báo bằng requires.
- Có thể khai báo service được sử dụng hoặc cung cấp.
- Ranh giới truy cập và encapsulation rõ ràng.

Ví dụ một ứng dụng có hai module:

~~~text
com.acme.greeter
    exports com.acme.greeter

com.acme.app
    requires com.acme.greeter
~~~

Module com.acme.app sử dụng API công khai của com.acme.greeter. Compiler và runtime đều kiểm tra quan hệ này.

### Module khác package như thế nào?

Package nhóm class theo namespace và tổ chức source code. Module nhóm nhiều package, kiểm soát package nào được export và module nào được đọc.

Một package public không tự động được module khác truy cập nếu package đó không được export bởi module sở hữu nó.

### Module khác Maven/Gradle project như thế nào?

Một module JPMS là khái niệm ở cấp Java runtime và module descriptor. Một Maven module hoặc Gradle subproject là đơn vị build.

Một Maven project có thể tạo ra một modular JAR; nhiều Maven projects có thể tạo thành một ứng dụng modular. Tương tự, một Gradle subproject có thể chứa một module JPMS.

Tên Maven artifactId, Gradle project name và JPMS module name không bắt buộc giống nhau. Khi build, cần quản lý cả ba tên nhất quán.

## 2. Cấu trúc source của dự án nhiều module

Một dự án có hai module có thể dùng cấu trúc:

~~~text
modular-app/
├── src/
│   ├── com.acme.greeter/
│   │   ├── module-info.java
│   │   └── com/acme/greeter/Greeter.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
├── out/
└── mods/
~~~

Trong cách tổ chức này, tên thư mục ngay dưới src là tên module. Bên trong mỗi thư mục module, package được đặt theo đường dẫn tương ứng.

Các công cụ build hiện đại cũng hỗ trợ cấu trúc multi-project riêng, ví dụ Maven dùng từng module folder có pom.xml và Gradle dùng subproject. Điều quan trọng là mỗi module JPMS có module-info.java đúng với module name của nó.

## 3. Viết module-info.java

Module descriptor khai báo tên module và các quy tắc phụ thuộc/truy cập.

### requires

Khai báo dependency module:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

Module com.acme.app có thể đọc các public type nằm trong package được export bởi com.acme.greeter.

### exports

Export package để module khác sử dụng API public:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

Chỉ package được export mới được module khác truy cập theo quy tắc JPMS. Các package còn lại vẫn được giữ encapsulated.

### requires transitive

Dùng khi API public của module phụ thuộc vào type từ module khác và các module downstream cần đọc dependency đó:

~~~java
module com.acme.api {
    requires transitive com.acme.model;
}
~~~

Module đọc com.acme.api cũng được hưởng khả năng đọc com.acme.model theo module graph. Chỉ dùng transitive khi dependency là một phần của API được expose.

### requires static

Dùng cho dependency cần ở compile time nhưng không bắt buộc phải có khi resolve runtime trong mọi tình huống:

~~~java
module com.acme.app {
    requires static com.acme.optionaltool;
}
~~~

Nếu code thực sự cần class của dependency khi chạy, ứng dụng vẫn phải cung cấp module đó trong runtime environment phù hợp. requires static không làm cho việc gọi class không tồn tại trở nên an toàn.

### exports có giới hạn

Có thể export một package chỉ cho module cụ thể:

~~~java
module com.acme.internal {
    exports com.acme.internal.spi to com.acme.plugin;
}
~~~

Đây là qualified export. Các module khác không được truy cập package đó theo cách export thông thường.

### opens và open module

exports dành cho truy cập kiểu thông thường tới public API. opens cho phép reflective access sâu hơn vào package tại runtime.

~~~java
module com.acme.model {
    opens com.acme.model.dto to com.fasterxml.jackson.databind;
}
~~~

Điều này thường cần với framework serialization, dependency injection hoặc ORM sử dụng reflection.

Có thể mở toàn bộ package bằng:

~~~java
open module com.acme.legacy {
    requires com.acme.common;
}
~~~

Chỉ dùng open module khi thật sự cần. Mở quá rộng làm giảm encapsulation của module.

### uses và provides

Service loader có thể được khai báo trong module descriptor:

~~~java
module com.acme.app {
    uses com.acme.spi.Formatter;
}
~~~

Module cung cấp implementation:

~~~java
module com.acme.json {
    requires com.acme.spi;
    provides com.acme.spi.Formatter
        with com.acme.json.JsonFormatter;
}
~~~

Khi build và link, service provider modules có thể được đưa vào runtime image bằng tùy chọn jlink --bind-services.

## 4. Ví dụ ứng dụng hai module hoàn chỉnh

Module greeter cung cấp một API đơn giản; module app gọi API đó.

### Greeter module

File **src/com.acme.greeter/module-info.java**:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

File **src/com.acme.greeter/com/acme/greeter/Greeter.java**:

~~~java
package com.acme.greeter;

public final class Greeter {
    public String message() {
        return "Hello from modular Java";
    }
}
~~~

### App module

File **src/com.acme.app/module-info.java**:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

File **src/com.acme.app/com/acme/app/Main.java**:

~~~java
package com.acme.app;

import com.acme.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().message());
    }
}
~~~

Module app chỉ sử dụng được Greeter vì greeter export package com.acme.greeter và app khai báo requires com.acme.greeter.

## 5. Biên dịch nhiều module bằng javac

Đứng tại thư mục modular-app:

~~~bash
javac --release 17 --module-source-path src -d out -m com.acme.greeter,com.acme.app
~~~

Giải thích:

- --release 17: biên dịch theo Java SE 17 API và class file tương ứng.
- --module-source-path src: chỉ ra thư mục chứa source của nhiều module.
- -d out: thư mục output.
- -m: chọn các module cần biên dịch.

Compiler tự giải quyết quan hệ requires giữa hai module. Module app phụ thuộc greeter nên compiler tìm source của greeter trong module-source-path.

Kết quả có dạng:

~~~text
out/
├── com.acme.greeter/
│   ├── module-info.class
│   └── com/acme/greeter/Greeter.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Đây là **exploded modules**: mỗi module được biên dịch vào một thư mục riêng, module-info.class nằm ở root của thư mục module.

### Chạy exploded modules

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Trong đó:

- --module-path out: nơi runtime tìm các module.
- -m com.acme.app/com.acme.app.Main: chọn module và main class.

Stdout chính xác:

~~~text
Hello from modular Java
~~~

### Biên dịch một module khi dependency đã được build

Trong dự án lớn, module có thể được build riêng. Khi dependency đã nằm trên module path:

~~~bash
javac --release 17 --module-path mods -d out/app app-src/module-info.java app-src/com/acme/app/Main.java
~~~

Module path phải chứa các module mà module đang biên dịch yêu cầu. Nếu dependency chưa được build hoặc không có module descriptor phù hợp, compiler sẽ báo không resolve được module.

## 6. Đóng gói modular JAR bằng jar

Sau khi biên dịch, có thể đóng gói từng module thành JAR.

Tạo thư mục mods:

~~~bash
mkdir mods
~~~

Trên Windows PowerShell có thể dùng:

~~~powershell
New-Item -ItemType Directory -Path mods -Force
~~~

Đóng gói greeter:

~~~bash
jar --create --file mods/com.acme.greeter.jar -C out/com.acme.greeter .
~~~

Đóng gói app và khai báo main class:

~~~bash
jar --create --file mods/com.acme.app.jar --main-class com.acme.app.Main -C out/com.acme.app .
~~~

Một modular JAR có module-info.class ở root archive. Main class metadata giúp công cụ biết entry point của ứng dụng.

### Kiểm tra module descriptor trong JAR

~~~bash
jar --describe-module --file mods/com.acme.greeter.jar
jar --describe-module --file mods/com.acme.app.jar
~~~

Kết quả đại diện:

~~~text
com.acme.greeter
exports com.acme.greeter
requires java.base mandated

com.acme.app
requires com.acme.greeter
requires java.base mandated
contains com.acme.app
main-class com.acme.app.Main
~~~

java.base là module nền tảng được requires ngầm định trong mọi module thông thường.

### Chạy từ modular JAR

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Stdout:

~~~text
Hello from modular Java
~~~

Có thể chỉ định module path bằng danh sách JAR. Trên Windows dùng dấu chấm phẩy; trên Linux/macOS dùng dấu hai chấm. Dùng thư mục mods thường đơn giản hơn khi có nhiều module.

## 7. Module path và classpath

Module path và classpath có quy tắc resolution khác nhau.

| Classpath | Module path |
|---|---|
| Tập hợp class và JAR trên class loader | Tập hợp named modules |
| Không có module descriptor vẫn chạy được | Modular JAR hoặc automatic module |
| Không kiểm soát package bằng exports/requires | Có module graph và strong encapsulation |
| Dependency có thể bị trùng class | Module name và package split được kiểm tra chặt hơn |
| Phù hợp ứng dụng legacy hoặc thư viện chưa modular | Phù hợp ứng dụng JPMS |

### Automatic module

Một JAR không có module-info.class nhưng đặt trên module path có thể trở thành automatic module. Tên module có thể lấy từ Automatic-Module-Name trong manifest hoặc suy ra từ tên JAR.

Automatic module export tất cả package và đọc các module khác theo quy tắc rộng hơn named module thông thường. Đây là cầu nối cho thư viện chưa modular, nhưng không có cùng mức encapsulation.

Nếu duy trì thư viện lâu dài, hãy kiểm tra module name ổn định và cân nhắc tạo explicit module descriptor khi phù hợp.

### Unnamed module

Code chạy trên classpath thuộc unnamed module. Named module không tự động đọc unnamed module. Khi chuyển ứng dụng legacy sang JPMS, có thể cần chia module dần hoặc dùng các cờ như --add-reads trong giai đoạn chuyển tiếp.

Không dùng --add-exports hoặc --add-opens làm giải pháp lâu dài nếu có thể sửa module descriptor hoặc dependency đúng cách.

## 8. Kiểm tra dependency bằng jdeps

jdeps phân tích dependency ở mức package, class hoặc module. Nó hữu ích để kiểm tra module graph trước khi package hoặc tạo runtime image.

### Xem dependency summary

~~~bash
jdeps -summary mods/com.acme.app.jar
~~~

### Kiểm tra module graph

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

Lệnh này kiểm tra descriptor và quan hệ dependency của module.

### In danh sách module cần cho runtime

~~~bash
jdeps --module-path mods --print-module-deps mods/com.acme.app.jar
~~~

Kết quả đại diện:

~~~text
com.acme.greeter,java.base
~~~

Danh sách này có thể dùng làm đầu vào cho jlink --add-modules. jdeps không bao gồm chính root module app trong danh sách dependency được in.

### Tìm dependency tới JDK internal API

~~~bash
jdeps --jdk-internals mods/com.acme.app.jar
~~~

Nếu code phụ thuộc vào JDK internal API, cần thay bằng public API được hỗ trợ. Internal API có thể thay đổi hoặc bị đóng trong JDK mới.

### Tạo gợi ý module descriptor cho JAR legacy

~~~bash
jdeps --generate-module-info generated-modules legacy-library.jar
~~~

jdeps có thể tạo module-info.java gợi ý cho thư viện chưa modular. File tạo ra cần được review thủ công, đặc biệt về exports, requires và reflective access.

Không coi descriptor do công cụ sinh ra là thiết kế module hoàn chỉnh.

## 9. Tạo custom runtime bằng jlink

Một ứng dụng modular có thể được đóng gói cùng runtime image chỉ chứa các module cần thiết thay vì yêu cầu người dùng cài một JDK đầy đủ.

jlink lấy module từ JDK jmods và application module path, resolve dependency closure rồi tạo runtime image.

Ví dụ trên Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --launcher app=com.acme.app/com.acme.app.Main --output runtime-image
~~~

Trên Windows PowerShell, module path dùng dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --launcher app=com.acme.app/com.acme.app.Main --output runtime-image
~~~

Giải thích:

- --module-path: JDK jmods và các application modules.
- --add-modules com.acme.app: module root để link.
- --launcher: tạo lệnh app để khởi chạy main class.
- --output: thư mục runtime image.

jlink tự đưa các dependency cần thiết của com.acme.app vào image, ví dụ com.acme.greeter và java.base.

### Chạy runtime image

Linux/macOS:

~~~bash
./runtime-image/bin/app
~~~

Windows:

~~~powershell
.\runtime-image\bin\app.bat
~~~

Hoặc chạy module trực tiếp bằng runtime được link:

~~~bash
runtime-image/bin/java -m com.acme.app/com.acme.app.Main
~~~

Stdout:

~~~text
Hello from modular Java
~~~

### Giới hạn của jlink

- jlink cần explicit modules hoặc JMODs có thể link.
- Automatic modules và JAR chỉ nằm trên classpath không phải đầu vào link thông thường.
- Runtime image phụ thuộc nền tảng/kiến trúc mà JDK dùng để tạo image.
- jlink chạy từ JDK hiện tại sẽ tạo runtime dựa trên phiên bản JDK đó; --release khi compile không làm jlink tự tạo runtime của release cũ.
- Service provider có thể cần --bind-services để đưa provider modules vào image.
- Cần kiểm tra native libraries, charset, security provider và resource mà ứng dụng sử dụng động.

Nếu ứng dụng cần Java 17 runtime image, hãy dùng JDK 17 jlink để tạo image tương ứng, kể cả khi source được build từ JDK mới hơn với --release 17.

### Tối ưu image

Có thể bỏ debug symbols, header files và man pages:

~~~bash
jlink --strip-debug --no-header-files --no-man-pages --compress=zip-6 --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output runtime-image
~~~

Đo kích thước image và chạy smoke test sau khi link. Image nhỏ hơn không có nghĩa ứng dụng đã được kiểm thử đầy đủ trên mọi hệ điều hành.

## 10. Tích hợp module build với Maven

Maven multi-module project dùng parent POM làm aggregator và mỗi JPMS module là một Maven child project.

Cấu trúc:

~~~text
modular-maven/
├── pom.xml
├── greeter/
│   ├── pom.xml
│   └── src/main/java/
│       ├── module-info.java
│       └── com/acme/greeter/Greeter.java
└── app/
    ├── pom.xml
    └── src/main/java/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

### Parent pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>modular-parent</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>greeter</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Parent POM khai báo các child modules và cấu hình compiler release. Maven reactor xác định thứ tự build theo dependency giữa các project.

### greeter/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme</groupId>
        <artifactId>modular-parent</artifactId>
        <version>1.0-SNAPSHOT</version>
    </parent>

    <artifactId>greeter</artifactId>
</project>
~~~

File module-info.java trong source greeter khai báo:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

### app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme</groupId>
        <artifactId>modular-parent</artifactId>
        <version>1.0-SNAPSHOT</version>
    </parent>

    <artifactId>app</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>greeter</artifactId>
            <version>1.0-SNAPSHOT</version>
        </dependency>
    </dependencies>
</project>
~~~

Module descriptor của app khai báo dependency JPMS:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

Lưu ý hai loại dependency:

- Maven dependency xác định artifact cần có trên build classpath/module path.
- requires xác định quan hệ đọc module ở runtime và compile time của JPMS.

Cả hai cần khớp. Chỉ khai báo Maven dependency mà quên requires sẽ khiến source module không đọc được module cần dùng.

### Build Maven reactor

Từ thư mục root:

~~~bash
mvn clean verify
~~~

Chỉ build app cùng các dependency project cần thiết:

~~~bash
mvn -pl app -am clean verify
~~~

- -pl app: chọn Maven project app.
- -am: build các project mà app phụ thuộc.
- clean verify: xóa output cũ, build, chạy các verification/test phase và xác nhận build hoàn tất.

Maven compiler plugin nhận biết module-info.java và có thể dùng module path cho modular project. Hãy giữ phiên bản compiler plugin hiện đại và đặt maven.compiler.release để tránh dùng source/target mặc định cũ.

### Chạy modular JAR Maven

Windows PowerShell:

~~~powershell
java --module-path "greeter/target/greeter-1.0-SNAPSHOT.jar;app/target/app-1.0-SNAPSHOT.jar" -m com.acme.app/com.acme.app.Main
~~~

Linux/macOS:

~~~bash
java --module-path "greeter/target/greeter-1.0-SNAPSHOT.jar:app/target/app-1.0-SNAPSHOT.jar" -m com.acme.app/com.acme.app.Main
~~~

## 11. Tích hợp module build với Gradle

Gradle multi-project build thường ánh xạ một JPMS module thành một Gradle subproject.

Cấu trúc:

~~~text
modular-gradle/
├── settings.gradle
├── build.gradle
├── greeter/
│   ├── build.gradle
│   └── src/main/java/
│       ├── module-info.java
│       └── com/acme/greeter/Greeter.java
└── app/
    ├── build.gradle
    └── src/main/java/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'modular-app'
include 'greeter', 'app'
~~~

### build.gradle ở root

~~~groovy
allprojects {
    group = 'com.acme'
    version = '1.0.0'
}

subprojects {
    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }
}
~~~

### greeter/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    modularity.inferModulePath = true
}
~~~

Module descriptor:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

### app/build.gradle

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':greeter')
}

java {
    modularity.inferModulePath = true
}

application {
    mainModule = 'com.acme.app'
    mainClass = 'com.acme.app.Main'
}
~~~

Module descriptor:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

implementation project(':greeter') là dependency ở Gradle project graph. requires com.acme.greeter là dependency trong JPMS module graph. Hai khai báo phải cùng mô tả quan hệ mà source code sử dụng.

modularity.inferModulePath = true yêu cầu Gradle suy luận module path từ module descriptor và dependency. Đây là cấu hình rõ ràng, hữu ích khi build project modular.

### Build và chạy Gradle

Dùng Gradle Wrapper trong dự án.

Windows:

~~~powershell
.\gradlew.bat :app:build
.\gradlew.bat :app:run
~~~

Linux/macOS:

~~~bash
./gradlew :app:build
./gradlew :app:run
~~~

Build toàn bộ project:

~~~bash
./gradlew clean build
~~~

Tạo application distribution:

~~~bash
./gradlew :app:installDist
~~~

Gradle Application Plugin tạo script khởi chạy và distribution. Khi khai báo mainModule, mainClass, Gradle có thể chạy ứng dụng trên module path theo cấu hình modularity.

### Java Library: api và implementation

Với module thư viện, dùng java-library plugin để phân biệt dependency public API và implementation:

- api: dependency là một phần của public compile API mà consumer cần đọc.
- implementation: dependency phục vụ nội bộ implementation và không được expose như public API dependency của consumer.

Quyết định api/implementation cần khớp với module descriptor và public types được export. Không khai báo api chỉ để giải quyết lỗi module-path mà chưa xem xét API boundary.

## 12. Annotation processors, tests và resources

### Annotation processors

Annotation processor có thể chạy trên classpath hoặc module path riêng. javac có các option:

~~~bash
--processor-path
--processor-module-path
-processor
-proc
~~~

Với Maven/Gradle, khai báo annotation processor trong cấu hình compiler plugin hoặc annotationProcessor dependency configuration thay vì đưa processor vào runtime module của ứng dụng.

Nếu processor cần truy cập module internals, kiểm tra exports/opens và compiler options trong đúng giai đoạn build.

### Tests trong dự án modular

Test code có thể cần truy cập package nội bộ hoặc dùng reflection. Khi đó test framework và build plugin có thể dùng cơ chế patch module hoặc add-reads/add-opens.

Không mở package production rộng hơn chỉ để làm test chạy. Ưu tiên test qua exported API; chỉ dùng compiler/runtime test flags có phạm vi rõ ràng cho các test cần kiểm tra nội bộ.

### Resources

Resources đặt trong source/resource directory của từng module được build tool đóng gói vào artifact theo quy tắc tương ứng.

Với JPMS, code trong module có thể truy cập resource theo module/class API. Nếu framework cần reflection hoặc truy cập resource qua package khác, kiểm tra opens và cách framework tìm resource.

## 13. Kiểm tra dependency và module graph trong CI

Một pipeline build modular nên làm các bước:

1. Checkout source và chọn JDK version đã pin.
2. Chạy clean build.
3. Chạy unit/integration tests.
4. Kiểm tra module descriptor trong JAR.
5. Chạy jdeps --check.
6. Kiểm tra missing dependencies và JDK internal API.
7. Tạo runtime image bằng jlink nếu sản phẩm phân phối runtime riêng.
8. Chạy smoke test trên runtime image.
9. Lưu artifact và build metadata.

Ví dụ kiểm tra JAR:

~~~bash
jar --describe-module --file app.jar
jdeps --module-path mods --check com.acme.app
jdeps --module-path mods --print-module-deps app.jar
~~~

Nếu pipeline có bước jlink, hãy dùng đúng JDK version và target OS/architecture. Runtime image thường không portable giữa Windows, Linux và macOS.

### Pin JDK và build tool

Dùng Maven Wrapper hoặc Gradle Wrapper để khóa phiên bản build tool. Dùng toolchain hoặc release configuration để chọn Java API/classfile target. Ghi lại:

- JDK vendor/version.
- Maven/Gradle version.
- Plugin versions.
- Dependency versions.
- Build flags.
- OS/architecture.
- Runtime image options.

Một build tái lập được giúp phân biệt thay đổi source với thay đổi toolchain.

## 14. Troubleshooting lỗi module build

### Module not found

Thông báo có thể giống:

~~~text
error: module not found: com.acme.greeter
~~~

Kiểm tra:

- module-info.java có đúng module name không?
- Dependency đã được build/package chưa?
- --module-path có trỏ đúng thư mục/JAR không?
- JAR có module-info.class hoặc Automatic-Module-Name không?
- Maven/Gradle dependency có được khai báo không?
- Module path có dùng đúng separator của OS không?

### Package is not visible

Có thể do module dependency chưa khai báo requires hoặc package chưa export.

Kiểm tra module descriptor của cả hai module. Đảm bảo provider export package API và consumer requires module tương ứng.

### Package is declared in module but module does not export it

Package tồn tại nhưng không export cho consumer. Thêm exports đúng package nếu đó là API dự định công khai. Không export mọi package chỉ để compiler hết lỗi.

### Module name không khớp artifact name

Maven artifactId hoặc tên file JAR có thể khác JPMS module name. Dùng jar --describe-module để xem tên module thực tế; đừng suy ra module name chỉ từ tên file.

### Split package

Hai module cùng chứa package có cùng tên có thể tạo split-package conflict khi resolve module graph. Tách package sang một module duy nhất hoặc thiết kế lại ownership.

### Illegal reflective access hoặc InaccessibleObjectException

Framework có thể cần reflective access tới package chưa mở. Xem package và module được nêu trong exception. Ưu tiên cập nhật framework hoặc khai báo opens có phạm vi cụ thể. Chỉ dùng --add-opens cho compatibility khi đã đánh giá rủi ro.

### JAR chạy trên classpath nhưng lỗi trên module path

Có thể code đang dựa vào unnamed module, reflection không được mở, split package hoặc dependency chưa có module name ổn định. Chạy jdeps và jar --describe-module để xác định module graph.

### jlink báo automatic module không hỗ trợ

Kiểm tra toàn bộ dependency trên module path. jlink cần explicit modules hoặc JMODs; thay thư viện automatic module bằng phiên bản modular, tạo explicit module descriptor phù hợp hoặc điều chỉnh kiến trúc đóng gói.

### jlink image chạy được trên máy build nhưng không chạy trên máy khác

Runtime image được tạo cho OS/architecture cụ thể. Kiểm tra native library, architecture, runtime environment và platform dependencies. Build image riêng cho từng target platform.

### Maven/Gradle compile được nhưng runtime báo module not found

Compile dependency và runtime module path có thể khác nhau. Kiểm tra dependency scope/configuration, artifact packaging, module descriptor và command khởi chạy. Đảm bảo runtime distribution chứa tất cả module cần thiết.

## 15. Nguyên tắc thiết kế module để build dễ bảo trì

- Đặt tên module ổn định, thường dùng reverse-domain naming.
- Export ít package nhất có thể.
- Tách public API khỏi implementation packages.
- Chỉ khai báo requires cho dependency thực sự cần.
- Dùng requires transitive khi dependency thuộc public API.
- Dùng opens cho reflective access có phạm vi cụ thể.
- Tránh split package.
- Tránh phụ thuộc JDK internal APIs.
- Kiểm tra automatic modules trước khi đưa vào jlink.
- Giữ module name ổn định qua các lần đổi tên artifact.
- Quản lý module graph cùng dependency graph của Maven/Gradle.
- Build và test trên đúng JDK release mục tiêu.
- Kiểm tra runtime image trên từng platform phân phối.

## 16. Quy trình module build từ source đến runtime image

~~~text
Source modules
    |
    v
module-info.java + Java source
    |
    v
javac / Maven / Gradle
    |
    v
Exploded modules
    |
    v
jar -> modular JARs
    |
    +----> jdeps --check / --print-module-deps
    |
    v
jlink
    |
    v
Custom runtime image
    |
    v
Smoke test / package / distribution
~~~

Mỗi bước kiểm tra một lớp khác nhau:

- Compiler kiểm tra cú pháp và module dependencies.
- JAR giữ module descriptor và class/resource.
- jdeps kiểm tra dependency graph và JDK internal API.
- jlink resolve module closure và tạo runtime image.
- Smoke test xác nhận ứng dụng chạy được trên artifact cuối cùng.

Không dừng ở trạng thái compile thành công; phải chạy thử đúng modular JAR hoặc runtime image sẽ phân phối.

## 17. Checklist module build

- Có module-info.java cho từng explicit module.
- Module name duy nhất và ổn định.
- requires khớp dependency thực tế.
- exports chỉ public packages cần thiết.
- opens chỉ dùng khi reflection cần.
- Không có split package.
- Compile được bằng --module-source-path hoặc build tool.
- JAR chứa module-info.class ở root.
- jar --describe-module hiển thị descriptor đúng.
- java --module-path chạy được module main.
- jdeps --check không báo vấn đề chưa xử lý.
- jdeps --print-module-deps xác định được runtime module closure.
- jlink tạo image cho đúng JDK/OS/architecture.
- Maven/Gradle dependency graph khớp JPMS graph.
- Tests và resources được đóng gói đúng.
- CI pin JDK, plugin và build tool versions.
- Runtime image được smoke test trước khi phát hành.

## 18. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| JPMS | Java Platform Module System |
| Module descriptor | File module-info.java hoặc module-info.class |
| Named module | Module có tên và descriptor |
| Exploded module | Module được biên dịch trong một thư mục |
| Modular JAR | JAR chứa module-info.class ở root |
| Module path | Đường dẫn chứa các module để compiler/runtime resolve |
| Classpath | Đường dẫn class/JAR thuộc unnamed module |
| requires | Khai báo module dependency |
| requires transitive | Truyền khả năng đọc dependency tới consumer |
| requires static | Dependency compile-time có thể optional ở runtime |
| exports | Công khai package cho module khác |
| opens | Cho phép reflective access vào package |
| Automatic module | JAR không có descriptor được suy ra thành module trên module path |
| jdeps | Công cụ phân tích dependency |
| jlink | Công cụ tạo custom runtime image |
| jmod | Định dạng archive module của JDK |
| Maven reactor | Cơ chế build nhiều Maven projects theo dependency graph |
| Gradle subproject | Một đơn vị build trong multi-project Gradle |
| Toolchain | Cấu hình JDK dùng để compile/test/run |
| Runtime image | Bộ runtime tùy chỉnh chứa module cần thiết |

Xây dựng ứng dụng modular yêu cầu đồng bộ module descriptor, source layout, build dependency và runtime module path. Hãy bắt đầu với javac để hiểu module graph, đóng gói modular JAR, dùng jdeps để kiểm tra dependency, rồi tích hợp Maven/Gradle và jlink cho pipeline phân phối. Luôn chạy smoke test trên artifact cuối cùng thay vì chỉ xác nhận compiler thành công.

## Tài liệu tham khảo

- Oracle Java SE 24 — The Java Module System: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/package-summary.html
- Oracle JDK 24 — javac Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Oracle JDK 24 — jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Oracle JDK 24 — jdeps Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html
- Oracle JDK 24 — jlink Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html
- Apache Maven — Maven Multi-Module Projects: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Apache Maven — Maven Compiler Plugin: https://maven.apache.org/plugins/maven-compiler-plugin/
- Gradle — Building Java Modules: https://docs.gradle.org/current/userguide/java_library_plugin.html
- Gradle — Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html