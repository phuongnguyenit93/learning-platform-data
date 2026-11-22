# Compile modules trong multi-project build

Trong một dự án Java có nhiều project con, mỗi project có thể tạo một JAR riêng. Nếu dùng Java Platform Module System (JPMS), từng project con có thể đồng thời là một **named module** với file `module-info.java`, dependency và API công khai riêng. Khi biên dịch, build tool cần sắp xếp đúng thứ tự project, đặt artifact đầu vào trên **module path** và bảo đảm các chỉ thị `requires`/`exports` khớp với dependency của hệ thống build.

Điểm dễ nhầm lẫn: **multi-project build** của Maven hoặc Gradle là cấu trúc quản lý công việc build; **module graph** của JPMS là cấu trúc dependency mà `javac` và JVM kiểm tra. Hai cấu trúc có liên quan nhưng không tự đồng bộ với nhau. Một dependency được khai báo trong `pom.xml` hoặc `build.gradle` chưa tự tạo chỉ thị `requires`; ngược lại, khai báo `requires` không khiến Maven hoặc Gradle tự tải artifact không có trong dependency configuration.

Bài này dùng cùng một ví dụ Java, sau đó biên dịch bằng `javac`, tổ chức dưới dạng **Maven multi-module reactor** và **Gradle multi-project build**.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt build project/module với JPMS named module.
- Chia mã nguồn thành các project con có `module-info.java` riêng.
- Xác định thứ tự build và module path cho từng bước biên dịch.
- Viết `requires`, `requires transitive` và `exports` đúng theo API thực tế.
- Cấu hình Maven reactor để biên dịch các project phụ thuộc nhau.
- Cấu hình Gradle multi-project với `java-library` và `modularity.inferModulePath`.
- Chẩn đoán `module not found`, `package is not visible`, classpath/module path sai, split package và lỗi do dependency không được truyền tới consumer.
- Kiểm tra kết quả từ JAR và chạy ứng dụng bằng `java -m`.

## 1. Hai đồ thị cần hiểu

Giả sử hệ thống có ba project:

~~~text
api        -> chứa public data model
service    -> triển khai nghiệp vụ, dùng api
app        -> điểm khởi chạy, dùng service
~~~

Ở mức build, quan hệ được mô tả như sau:

~~~text
app (build project)
  └── depends on service (build project)
        └── depends on api (build project)
~~~

Ở mức JPMS, ứng dụng có các module:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.service
    |
    | requires transitive
    v
com.acme.api
~~~

Hai graph có thể cùng hướng nhưng được khai báo ở **hai nơi khác nhau**:

| Lớp | Nguồn cấu hình | Mục đích |
|---|---|---|
| Maven | `pom.xml` trong mỗi project | Tải artifact, thiết lập compile/test/runtime classpath, quyết định thứ tự reactor |
| Gradle | `settings.gradle`, `build.gradle` | Khai báo project con, dependency configuration, task graph |
| JPMS | `module-info.java` | Tên module, readability, exports, opens và service declaration |

Nếu service build thiếu dependency tới api, compiler thường không tìm thấy module `com.acme.api`. Nếu service build có dependency nhưng descriptor thiếu `requires com.acme.api;`, compiler có thể thấy JAR mà vẫn từ chối sử dụng kiểu vì module service không đọc được api.

## 2. Cấu trúc dự án thống nhất

Ta dùng bố cục chuẩn Maven/Gradle:

~~~text
jpms-multi-project/
├── api/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/acme/api/Message.java
├── service/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/acme/service/GreetingService.java
└── app/
    └── src/main/java/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

Khi dùng Maven sẽ thêm `pom.xml` ở root và các project con. Khi dùng Gradle sẽ thêm `settings.gradle`, `build.gradle` ở root và cấu hình con. Hai biến thể build được trình bày riêng; **không cần áp dụng cả Maven và Gradle cho cùng một lần build**.

### 2.1. API module

`api/src/main/java/module-info.java`:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

`api/src/main/java/com/acme/api/Message.java`:

~~~java
package com.acme.api;

public record Message(String text) {
}
~~~

Module này export package chứa kiểu dữ liệu mà các module khác được phép sử dụng. Ví dụ dùng Java 17 trở lên để dùng `record` mà không cần cấu hình preview feature.

### 2.2. Service module

`service/src/main/java/module-info.java`:

~~~java
module com.acme.service {
    requires transitive com.acme.api;
    exports com.acme.service;
}
~~~

`service/src/main/java/com/acme/service/GreetingService.java`:

~~~java
package com.acme.service;

import com.acme.api.Message;

public final class GreetingService {
    public Message greet(String name) {
        return new Message("Xin chào, " + name);
    }
}
~~~

Ở đây `GreetingService.greet()` trả về `Message`, một kiểu public thuộc module api. Vì kiểu từ api là một phần của public API của service, dùng `requires transitive com.acme.api;` là thiết kế hợp lý: consumer đọc service có thể đọc api theo quan hệ chuyển tiếp.

Nếu api chỉ là dependency implementation nội bộ, không xuất hiện trong public API, service thường chỉ cần:

~~~java
requires com.acme.api;
~~~

### 2.3. App module

`app/src/main/java/module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

`app/src/main/java/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.api.Message;
import com.acme.service.GreetingService;

public class Main {
    public static void main(String[] args) {
        Message result = new GreetingService().greet("JPMS");
        System.out.println(result.text());
    }
}
~~~

App khai báo trực tiếp `requires com.acme.service;`; module api được đọc gián tiếp nhờ `requires transitive` của service. Điều này không có nghĩa mọi dependency đều nên để transitive: chỉ dùng transitive khi module phía sau thuộc hợp đồng public API của module trung gian.

Kết quả kỳ vọng khi chạy:

~~~text
Xin chào, JPMS
~~~

## 3. Biên dịch thủ công để hiểu module path

Trước khi dùng build tool, có thể biên dịch từng module với `javac`. Việc này làm rõ Maven/Gradle cần tự động hóa những gì.

Tạo ba thư mục đầu ra:

~~~text
out/
├── api/
├── service/
└── app/
~~~

### 3.1. Biên dịch api trước

~~~bash
javac -d out/api \
    api/src/main/java/module-info.java \
    api/src/main/java/com/acme/api/Message.java
~~~

Kết quả có dạng:

~~~text
out/api/
├── module-info.class
└── com/acme/api/Message.class
~~~

`out/api` là root của compiled module: file `module-info.class` nằm ngay tại root đó.

### 3.2. Biên dịch service với module path chỉ tới api

~~~bash
javac --module-path out/api -d out/service \
    service/src/main/java/module-info.java \
    service/src/main/java/com/acme/service/GreetingService.java
~~~

`javac` đọc descriptor của service, thấy `requires transitive com.acme.api;` và dùng module path để tìm compiled module api.

Nếu bỏ `--module-path out/api`, compiler có thể báo:

~~~text
module not found: com.acme.api
~~~

### 3.3. Biên dịch app với các module cần thiết

Linux/macOS:

~~~bash
javac --module-path "out/api:out/service" -d out/app \
    app/src/main/java/module-info.java \
    app/src/main/java/com/acme/app/Main.java
~~~

Trên Windows, module path dùng dấu chấm phẩy:

~~~powershell
javac --module-path "out/api;out/service" -d out/app app/src/main/java/module-info.java app/src/main/java/com/acme/app/Main.java
~~~

App cần có cả service lẫn api trên module path vì app sử dụng kiểu `Message` từ api trong mã nguồn. `requires transitive` tạo readability, nhưng **compiler vẫn cần tìm được module thật** qua module path hoặc nguồn module tương ứng.

### 3.4. Chạy ứng dụng

Linux/macOS:

~~~bash
java --module-path "out/api:out/service:out/app" \
    -m com.acme.app/com.acme.app.Main
~~~

Windows:

~~~powershell
java --module-path "out/api;out/service;out/app" -m com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Xin chào, JPMS
~~~

Thứ tự build:

~~~text
compile(api) -> compile(service) -> compile(app) -> run(app)
~~~

Đây chính là thứ tự mà build tool cần tổ chức dựa trên dependency graph của project.

## 4. Module source path khác cách bố trí multi-project

Một số ví dụ JPMS dùng:

~~~bash
javac --module-source-path src -d out -m com.acme.api,com.acme.service,com.acme.app
~~~

Lệnh này phù hợp khi source được xếp theo module dưới một module source path như:

~~~text
src/
├── com.acme.api/
├── com.acme.service/
└── com.acme.app/
~~~

Nhưng dự án Maven/Gradle thường bố trí source của mỗi project ở `api/src/main/java`, `service/src/main/java`, `app/src/main/java`. Khi đó, **không được máy móc lấy `--module-source-path src` từ ví dụ trước**, vì layout không tương ứng.

Build tool thường biên dịch từng project từ source set của chính nó, kết hợp compiled artifact của các dependency trên module path. Đây là cách phù hợp với multi-project build có vòng đời và output riêng cho từng project.

## 5. Maven multi-module reactor

Maven dùng root aggregator POM để liệt kê các Maven module cần build. Trong ví dụ này, ta đặt một Maven project cho mỗi JPMS module.

Cấu trúc:

~~~text
jpms-multi-project/
├── pom.xml
├── api/
│   ├── pom.xml
│   └── src/main/java/...
├── service/
│   ├── pom.xml
│   └── src/main/java/...
└── app/
    ├── pom.xml
    └── src/main/java/...
~~~

### 5.1. Root pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>jpms-multi-project</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>

  <modules>
    <module>api</module>
    <module>service</module>
    <module>app</module>
  </modules>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

`<modules>` cho Maven biết có ba project con trong reactor. Maven sẽ sử dụng dependency quan hệ giữa các project để tính thứ tự build cần thiết; không nên dựa vào thứ tự dòng `<module>` để thay thế khai báo dependency.

Thuộc tính `maven.compiler.release=17` giúp biên dịch thống nhất theo Java 17. Trong ví dụ này, Maven Compiler Plugin 3.13.0 được dùng để minh họa cấu hình; không có ý nghĩa bắt buộc mọi hệ thống phải sử dụng đúng phiên bản đó.

### 5.2. api/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>com.acme</groupId>
    <artifactId>jpms-multi-project</artifactId>
    <version>1.0.0</version>
  </parent>

  <artifactId>api</artifactId>
  <packaging>jar</packaging>
</project>
~~~

Artifact có tên `api`, nhưng JPMS module được đặt tên trong descriptor là `com.acme.api`. Maven artifactId và JPMS module name không nhất thiết trùng nhau.

### 5.3. service/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>com.acme</groupId>
    <artifactId>jpms-multi-project</artifactId>
    <version>1.0.0</version>
  </parent>

  <artifactId>service</artifactId>

  <dependencies>
    <dependency>
      <groupId>com.acme</groupId>
      <artifactId>api</artifactId>
      <version>1.0.0</version>
    </dependency>
  </dependencies>
</project>
~~~

Dependency Maven cho phép reactor biết service phải được build sau api và cấp artifact api cho quá trình biên dịch service. Descriptor service **vẫn phải** có:

~~~java
requires transitive com.acme.api;
~~~

Một dòng dependency Maven và một chỉ thị JPMS giải quyết hai nhiệm vụ khác nhau.

### 5.4. app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>com.acme</groupId>
    <artifactId>jpms-multi-project</artifactId>
    <version>1.0.0</version>
  </parent>

  <artifactId>app</artifactId>

  <dependencies>
    <dependency>
      <groupId>com.acme</groupId>
      <artifactId>service</artifactId>
      <version>1.0.0</version>
    </dependency>
  </dependencies>
</project>
~~~

App chỉ khai báo dependency Maven trực tiếp tới service. Vì dependency api của service có scope compile mặc định, Maven dependency transitivity thông thường sẽ mang artifact api đến compile graph của app. Điều này giúp compiler tìm module api, trong khi `requires transitive` của JPMS cho phép module app đọc api qua service.

Trong các hệ thống yêu cầu kiểm soát dependency trực tiếp hoặc có cấu hình scope khác, có thể cần khai báo dependency rõ ràng tới api ở app để bảo đảm artifact có mặt. Không thay đổi descriptor một cách mù quáng: xem xét public API và dependency graph thực tế.

### 5.5. Build bằng Maven reactor

Chạy tại thư mục root:

~~~bash
mvn clean package
~~~

Maven xây dựng các Maven module theo thứ tự dependency phù hợp. Đối với ví dụ, thứ tự logic là:

~~~text
api -> service -> app
~~~

Chỉ build app và các project mà nó phụ thuộc:

~~~bash
mvn -pl app -am clean package
~~~

Trong đó:

- `-pl app` chọn project app trong reactor.
- `-am` (*also make*) bổ sung các project mà app phụ thuộc để Maven build cùng.
- `clean package` xóa output cũ và tạo các JAR.

Nếu chỉ chạy `mvn -pl app package` khi dependency của app chưa được cài vào local repository, build có thể thất bại vì artifact chưa có. `-am` là cách rõ ràng để Maven kéo các project upstream vào lượt reactor.

### 5.6. Kiểm tra JAR và chạy Java module

Sau khi package, các JAR có dạng:

~~~text
api/target/api-1.0.0.jar
service/target/service-1.0.0.jar
app/target/app-1.0.0.jar
~~~

Xem module descriptor:

~~~bash
jar --describe-module --file api/target/api-1.0.0.jar
jar --describe-module --file service/target/service-1.0.0.jar
jar --describe-module --file app/target/app-1.0.0.jar
~~~

Trên Linux/macOS:

~~~bash
java --module-path "api/target/api-1.0.0.jar:service/target/service-1.0.0.jar:app/target/app-1.0.0.jar" \
     -m com.acme.app/com.acme.app.Main
~~~

Trên Windows PowerShell:

~~~powershell
java --module-path "api/target/api-1.0.0.jar;service/target/service-1.0.0.jar;app/target/app-1.0.0.jar" -m com.acme.app/com.acme.app.Main
~~~

Kết quả mong đợi:

~~~text
Xin chào, JPMS
~~~

Các JAR phải có `module-info.class` đúng ở root. Chỉ việc Maven đóng gói thành `jar` chưa đủ để khẳng định nó là explicit named module.

## 6. Gradle multi-project build

Gradle tổ chức project con thông qua `settings.gradle`. Mỗi project có dependency configuration riêng; Gradle sẽ chạy task cần thiết theo project dependency.

Cấu trúc:

~~~text
jpms-multi-project/
├── settings.gradle
├── build.gradle
├── api/
│   ├── build.gradle
│   └── src/main/java/...
├── service/
│   ├── build.gradle
│   └── src/main/java/...
└── app/
    ├── build.gradle
    └── src/main/java/...
~~~

### 6.1. settings.gradle

~~~groovy
rootProject.name = 'jpms-multi-project'

include 'api', 'service', 'app'
~~~

Khai báo này cho Gradle biết có ba project. Nó không tự tạo quan hệ dependency giữa chúng.

### 6.2. Root build.gradle

~~~groovy
subprojects {
    apply plugin: 'java'

    java {
        modularity.inferModulePath = true
    }

    tasks.withType(JavaCompile).configureEach {
        options.release = 17
        options.encoding = 'UTF-8'
    }
}
~~~

`modularity.inferModulePath = true` yêu cầu Java plugin suy luận module path cho compilation dựa trên các dependency có nhận diện module phù hợp. Thuộc tính này giúp build tool đặt compiled module/JAR vào đường dẫn thích hợp thay vì chỉ classpath.

Khi một project có `module-info.java` nhưng thư viện trong dependency chưa có tên module ổn định, cần kiểm tra cách dependency được phân loại. Không phải mọi JAR nằm trong `dependencies` đều được resolver sử dụng theo cùng cách ở mọi phiên bản/configuration Gradle.

### 6.3. api/build.gradle

Với cấu hình root ở trên, `api/build.gradle` có thể để trống:

~~~groovy
// api chưa có project dependency.
~~~

Project api vẫn dùng Java plugin đã áp dụng từ root, tạo task `compileJava` và `jar` cho source set mặc định.

### 6.4. service/build.gradle

Vì public API của service trả về `Message` từ api, dùng Java Library plugin và khai báo dependency dạng `api`:

~~~groovy
apply plugin: 'java-library'

dependencies {
    api project(':api')
}
~~~

Tại đây có hai khái niệm cần phân biệt:

- Gradle `api project(':api')`: dependency của service được công bố cho consumer compilation graph.
- JPMS `requires transitive com.acme.api;`: module nào đọc service cũng đọc module api.

Chúng có liên quan nhưng không tương đương. Một cấu hình Gradle `api` không tự sinh dòng `requires transitive` trong `module-info.java`, và `requires transitive` không tự thêm project dependency vào Gradle.

Nếu kiểu api chỉ dùng nội bộ trong service, có thể chuyển dependency Gradle sang:

~~~groovy
dependencies {
    implementation project(':api')
}
~~~

và đổi descriptor service thành `requires com.acme.api;`. Việc chọn `api` hay `implementation` dựa trên hợp đồng public API và cách Gradle phân chia compile/runtime dependency.

### 6.5. app/build.gradle

Ứng dụng cần Application plugin để cung cấp task `run`:

~~~groovy
apply plugin: 'application'

dependencies {
    implementation project(':service')
}

application {
    mainModule = 'com.acme.app'
    mainClass = 'com.acme.app.Main'
}
~~~

`mainModule` là tên JPMS module, còn `mainClass` là tên fully qualified Java class. Chúng không nhất thiết bằng Gradle project name.

### 6.6. Build và chạy bằng Gradle

Từ root:

~~~bash
./gradlew :app:build
~~~

Trên Windows:

~~~powershell
.\gradlew.bat :app:build
~~~

Gradle tính task dependency cần thiết để biên dịch api, service rồi app. Muốn chạy:

~~~bash
./gradlew :app:run
~~~

Trên Windows:

~~~powershell
.\gradlew.bat :app:run
~~~

Kết quả mong đợi:

~~~text
Xin chào, JPMS
~~~

Kiểm tra project graph:

~~~bash
./gradlew projects
~~~

Kiểm tra compile dependency của app:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
~~~

Kiểm tra runtime dependency:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Các dependency configuration cho biết artifact nào được Gradle đưa tới từng task. Khi debug module path, cần kết hợp chúng với descriptor và compiler arguments thực tế.

## 7. Vì sao build dependency chưa đủ để compile module?

Một lỗi rất phổ biến trong multi-project build là nghĩ rằng:

~~~groovy
dependencies {
    implementation project(':api')
}
~~~

hoặc:

~~~xml
<dependency>
  <groupId>com.acme</groupId>
  <artifactId>api</artifactId>
  <version>1.0.0</version>
</dependency>
~~~

đã tự tạo quan hệ đọc module.

Trong JPMS, nếu service import từ api thì `module-info.java` của service phải có `requires com.acme.api;` hoặc `requires transitive com.acme.api;` theo đúng contract.

Mối quan hệ đầy đủ:

~~~text
Build configuration:
  service -> artifact api
  (phân phối compiled JAR cho javac)

JPMS descriptor:
  com.acme.service -> com.acme.api
  (khai báo readability trong module graph)
~~~

Thiếu một trong hai lớp có thể gây lỗi biên dịch. Vì vậy, khi chuyển dự án classpath sang JPMS, cần cập nhật **cả build graph lẫn module graph**, không chỉ thêm `module-info.java`.

## 8. Ba kiểu lỗi compile phổ biến

### 8.1. Không tìm thấy module

Ví dụ:

~~~text
error: module not found: com.acme.api
~~~

Có thể xảy ra khi:

- Project service chưa khai báo dependency tới project api trong Maven/Gradle.
- Artifact api chưa được build hoặc chưa xuất hiện trong compiler module path.
- Tên module trong `requires` không khớp tên thật của artifact.
- Compiler dùng nhầm source/output directory hoặc profile build.

Cách xử lý:

1. Xác nhận file `api/src/main/java/module-info.java` có `module com.acme.api`.
2. Xác nhận project service khai báo dependency build tới api.
3. Kiểm tra module path mà `javac` thực sự nhận.
4. Build reactor/project dependencies cùng lượt thay vì compile project con đơn lẻ khi upstream chưa sẵn sàng.

### 8.2. Package không nhìn thấy do thiếu requires

Một thông báo có thể chứa:

~~~text
package com.acme.api is not visible
(package com.acme.api is declared in module com.acme.api,
 but module com.acme.service does not read it)
~~~

Lúc này compiler đã biết module chứa package nhưng module sử dụng không có readability. Sửa `requires` trong descriptor của module **sử dụng**.

### 8.3. Package không export

Ví dụ:

~~~text
package com.acme.api is not visible
(package com.acme.api is declared in module com.acme.api,
 which does not export it)
~~~

Sửa `exports com.acme.api;` trong descriptor của module **cung cấp**, nếu package đó thật sự được công bố cho consumer.

Không dùng `--add-exports` như giải pháp mặc định cho một package nội bộ. Nếu ứng dụng đang import implementation không thuộc public API, cần xem lại thiết kế.

## 9. requires transitive và API dependency trong Maven/Gradle

Giả sử service có public method:

~~~java
public Message greet(String name)
~~~

Trong đó `Message` đến từ module api. App dùng kiểu `Message` ở compile time.

Để bảo đảm toàn bộ pipeline:

| Lớp | Service khai báo | Ý nghĩa |
|---|---|---|
| JPMS | `requires transitive com.acme.api;` | App đọc service được truyền readability tới api |
| Maven | Dependency tới artifact `api` | Maven reactor và compiler có module api |
| Gradle | `api project(':api')` | Public API dependency của service được truyền cho compile graph của consumer |

Không phải lúc nào cũng cần cấu hình ba dòng trong mọi dự án. Tùy build tool và thiết kế, nhưng cả **readability JPMS** và **khả năng compiler tìm artifact** phải được đáp ứng.

### 9.1. Nếu đổi requires transitive thành requires

Khi service thay:

~~~java
requires transitive com.acme.api;
~~~

thành:

~~~java
requires com.acme.api;
~~~

app chỉ `requires com.acme.service;` sẽ không tự đọc module api qua service nữa. Nếu app vẫn trực tiếp dùng `Message`, hãy khai báo dependency trực tiếp tại app:

~~~java
module com.acme.app {
    requires com.acme.service;
    requires com.acme.api;
}
~~~

Build graph cũng cần bảo đảm artifact api có mặt cho compilation của app. Không nên giả định một dependency transitive ở build tool sẽ thay thế quan hệ đọc JPMS.

### 9.2. requires static

`requires static` dùng khi một module dependency cần ở compile time nhưng được phép không hiện diện ở runtime theo thiết kế. Nó không thay thế dependency configuration của Maven/Gradle và không tự mang class/JAR vào compiler module path.

Với annotation API chỉ phục vụ compile:

~~~java
module com.acme.service {
    requires static com.acme.annotations;
}
~~~

Build tool vẫn cần cung cấp annotation artifact khi biên dịch. Annotation processor còn có cấu hình processor path/plugin riêng, không thể suy ra chỉ từ dòng `requires static`.

## 10. Compilation bằng source module so với compiled module JAR

Mỗi project con có thể phụ thuộc một trong hai nguồn:

- Compiled output của project dependency (class directory có `module-info.class`).
- Modular JAR đã được package.

Ở giai đoạn phát triển, build tool thường tái sử dụng compiled classes giữa các project để tránh package lại JAR sau mỗi thay đổi. Ở giai đoạn phát hành, JAR là artifact chuẩn được dùng trong module path.

Điểm cốt lõi: compiler phải thấy module descriptor và class tương ứng qua module path, bất kể module đến từ directory hay JAR.

Để xác định một JAR có descriptor:

~~~bash
jar --describe-module --file api/target/api-1.0.0.jar
~~~

Để xem file class bên trong:

~~~bash
jar tf api/target/api-1.0.0.jar
~~~

Kết quả cần có:

~~~text
module-info.class
com/acme/api/Message.class
~~~

Tên Maven artifact không phải tên JPMS module. Luôn tin vào descriptor thật hơn là suy đoán từ filename.

## 11. Khác biệt giữa compile classpath và module path

Trong dự án Java truyền thống, dependency thường nằm trên classpath. Với explicit named module, compiler cần nhận diện named module để kiểm tra `requires` và `exports`.

Một số nhầm lẫn:

**JAR ở classpath nhưng descriptor requires tên module**

~~~text
module com.acme.service {
    requires com.acme.api;
}
~~~

Nếu artifact api chỉ được cung cấp trên classpath, compiler không thể tìm nó dưới tên named module như kỳ vọng. Cần bảo đảm build tool đặt artifact đúng trên module path.

**Thư viện chưa có module-info.class**

JAR đặt trên module path có thể là automatic module. Tên module có thể đến từ `Automatic-Module-Name` hoặc filename. Dùng:

~~~bash
jar --describe-module --file libs/legacy.jar
~~~

để xác định tên mà `requires` phải sử dụng.

**Giữ cùng thư viện ở cả classpath và module path**

Điều này có thể gây nhầm version, class identity hoặc diagnostic khó hiểu. Không nên dùng cùng một artifact hai lần trong một lượt compile/run trừ khi có lý do kỹ thuật được kiểm soát rõ ràng.

## 12. Lỗi split package trong multi-project build

Hai project con có thể vô tình chứa class thuộc cùng một package:

~~~text
api/src/main/java/com/acme/shared/Model.java

service/src/main/java/com/acme/shared/Helper.java
~~~

Nếu api và service trở thành hai named module khác nhau, cùng chứa `com.acme.shared`, đó là split package.

Hậu quả phụ thuộc cách module được resolve và compiler/linker nhìn thấy package. Một lỗi điển hình có thể là:

~~~text
module com.acme.app reads package com.acme.shared
from both com.acme.api and com.acme.service
~~~

Cách sửa bền vững là:

- Di chuyển các class API chung vào một module sở hữu duy nhất.
- Đổi package implementation của service sang namespace như `com.acme.service.internal`.
- Cập nhật `exports`, `requires` và imports.
- Clean build để loại bỏ bytecode package cũ.

Đừng thêm `--add-exports` để chữa split package: flag export thay đổi khả năng truy cập, không thay đổi module sở hữu package.

## 13. Kiểm tra thứ tự compile và dependency resolution

### 13.1. Với Maven

Chạy toàn reactor:

~~~bash
mvn clean verify
~~~

Hoặc build app kèm dependency:

~~~bash
mvn -pl app -am package
~~~

Nếu lỗi chỉ xuất hiện khi chạy Maven trong thư mục app riêng, nguyên nhân có thể là artifact upstream chưa được install hoặc version trong repository không khớp reactor.

Kiểm tra Maven dependency tree:

~~~bash
mvn -pl app dependency:tree
~~~

### 13.2. Với Gradle

~~~bash
./gradlew :app:build
~~~

Xem task graph và log chi tiết hơn khi cần:

~~~bash
./gradlew :app:compileJava --info
~~~

Xem dependency configuration:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
~~~

Nếu app compile không nhìn thấy `com.acme.api`, kiểm tra:

- `service/build.gradle` có `api project(':api')` hay chỉ `implementation`?
- `service/module-info.java` có `requires transitive com.acme.api;` không?
- App cần phụ thuộc trực tiếp vào api hay không?
- Compile task có đang đặt named modules đúng module path không?

Đây là hai lớp cấu hình khác nhau, nên cần đối chiếu cả build tool lẫn JPMS descriptor.

## 14. Unit tests trong multi-project modular build

Project có `module-info.java` không có nghĩa các test framework luôn tự chạy trên module path như ứng dụng production.

Các tình huống thường gặp:

- Test framework cần reflection để tìm/test class.
- Unit test nằm ở `src/test/java` nhưng module chính đã strong-encapsulated.
- Test framework hoặc plugin build có chiến lược `--patch-module`, module path, classpath khác nhau.
- Test dùng mocking hoặc reflection vào thành viên private, có thể yêu cầu `opens`/`--add-opens` trong phạm vi test.

Cách kiểm tra:

1. Build main code thành công trước.
2. Chạy unit test của từng project.
3. Chạy integration test của project app với dependency thật.
4. Kiểm tra test runner và compiler args thực tế khi xuất hiện lỗi accessibility.
5. Tránh mở toàn bộ module production chỉ vì test framework yêu cầu reflection; ưu tiên cấu hình test plugin phù hợp.

Maven:

~~~bash
mvn test
~~~

Gradle:

~~~bash
./gradlew test
~~~

Điểm đáng chú ý: thành công của `compileJava` không bảo đảm `test` chạy đúng, và test chạy đúng trên classpath chưa chứng minh runtime production trên module path cũng đúng.

## 15. Compile module cần service provider

Nếu hệ thống tách SPI và implementation thành các project con khác nhau:

~~~text
spi -> provider -> app
~~~

Có thể có descriptor:

Module SPI:

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

Module provider:

~~~java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingProvider
        with com.acme.provider.DefaultGreetingProvider;
}
~~~

Module app:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.GreetingProvider;
}
~~~

Trong build tool, project provider phải được đóng gói và cung cấp trong runtime configuration/module path phù hợp. Chỉ khai báo `provides` trong descriptor mà không phân phối module provider hoặc không đưa nó vào configuration thích hợp thì `ServiceLoader` có thể không tìm thấy provider lúc chạy.

Đây là ví dụ vì sao compile graph và runtime graph có thể khác nhau: app có thể biên dịch chỉ với SPI, còn provider phải xuất hiện ở runtime.

## 16. Phối hợp với CI/CD

Một pipeline phổ biến có thể gồm:

~~~text
Checkout source
      |
      v
Resolve build dependencies
      |
      v
Compile api
      |
      v
Compile service
      |
      v
Compile app
      |
      v
Unit + integration tests
      |
      v
Package modular JARs
      |
      v
Run module-resolution smoke test
      |
      v
Publish artifacts
~~~

Cần đảm bảo:

- CI dùng đúng JDK/toolchain, ví dụ Java 17 nếu source dùng record.
- Build tool dùng dependency lock hoặc version constraints nhất quán.
- Artifact module descriptor không bị loại khỏi JAR khi đóng gói.
- Lệnh chạy production dùng module path chứa đủ các required modules.
- Không vô tình chạy app bằng classpath trong CI trong khi production chạy bằng module path.
- Module path được dựng đúng với hệ điều hành và các profile build tương ứng.

Một smoke test tối thiểu sau package:

~~~bash
java --module-path "api/target/api-1.0.0.jar:service/target/service-1.0.0.jar:app/target/app-1.0.0.jar" \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

Trên Windows đổi dấu `:` thành `;`. Dùng `--show-module-resolution` giúp nhìn rõ module nào được resolve, còn output app xác nhận chức năng cơ bản hoạt động.

## 17. Những sai lầm cần tránh

**Chỉ cấu hình requires mà bỏ dependency trong build tool.** Compiler không tự tải module JAR theo tên trong `module-info.java`.

**Chỉ cấu hình dependency trong build tool mà bỏ requires.** Artifact tồn tại không đồng nghĩa module sử dụng được phép đọc nó.

**Đồng nhất Gradle project name/Maven artifactId với JPMS module name.** Tên JPMS đến từ descriptor hoặc quy tắc automatic module.

**Dùng requires transitive cho mọi dependency.** Transitive nên phản ánh phần API mà consumer cần đọc, không phải mở rộng graph thiếu kiểm soát.

**Đưa tất cả thư viện lên classpath để né lỗi compile.** Việc này bỏ qua mục tiêu kiểm soát module và có thể che những lỗi package/accessibility.

**Chuyển cả package implementation của nhiều project vào một namespace chung.** Có thể tạo split package khi các project trở thành named module.

**Giả định module path trên Windows và Linux có cùng dấu phân cách.** Dùng `;` trên Windows, `:` trên Linux/macOS.

**Bỏ qua clean build sau khi đổi package.** Bytecode cũ có thể vẫn tồn tại trong output và xuất hiện trong artifact.

**Chạy Maven một project con mà không đưa upstream dependencies vào reactor.** Dùng `-am` khi cần build các project phụ thuộc cùng lượt.

## 18. Quy trình thực hành đề xuất

Khi chuyển một multi-project build hiện có sang JPMS, hãy thực hiện theo trình tự:

1. Liệt kê tất cả Maven/Gradle project con và quan hệ dependency giữa chúng.
2. Gán tên JPMS module ổn định cho từng project thực sự muốn modular hóa.
3. Đặt `module-info.java` trong đúng source root của từng project.
4. Chuyển project thấp tầng trước, ví dụ API/model không có nhiều dependency.
5. Dựng `requires`/`exports` theo quan hệ dùng public API thật.
6. Cập nhật Maven/Gradle project dependencies để compiler tìm đủ artifact.
7. Xác nhận việc suy luận module path hoặc cấu hình module path rõ ràng.
8. Biên dịch từ root với reactor/task graph, không chỉ build module ngẫu nhiên.
9. Dùng `jar --describe-module` để xác nhận modular JAR.
10. Chạy app trên module path và xem `--show-module-resolution`.
11. Kiểm tra test framework, reflection, providers và CI.
12. Chỉ chuyển thêm project/library khi các mốc trước đã chạy ổn định.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Maven reactor có ba module `api`, `service`, `app`. Có phải tên JPMS của chúng lần lượt là `api`, `service` và `app` không?

**Trả lời:** Không nhất thiết. Maven artifactId/build module khác tên JPMS module. Trong ví dụ, tên JPMS là `com.acme.api`, `com.acme.service` và `com.acme.app`.

**Câu 2.** Service khai báo dependency Gradle `implementation project(':api')` nhưng `module-info.java` không có `requires com.acme.api;`. Compiler có tự hiểu quan hệ đọc không?

**Trả lời:** Không. Build dependency làm artifact có thể được tìm, còn JPMS cần quan hệ readability từ descriptor.

**Câu 3.** Tại sao app trong ví dụ chỉ `requires com.acme.service;` mà vẫn dùng `Message` từ api?

**Trả lời:** Vì service khai báo `requires transitive com.acme.api;` và api export package chứa `Message`; build tool cũng phải cung cấp artifact api cho compiler.

**Câu 4.** Vì sao trong Gradle service dùng `api project(':api')` thay vì `implementation`?

**Trả lời:** Vì public API của service dùng kiểu `Message` từ api. Gradle `api` giúp truyền dependency đến compile graph của consumer, độc lập với JPMS `requires transitive`.

**Câu 5.** App POM đã khai báo service nhưng Maven chạy trong thư mục app báo không tìm thấy artifact service. Nên làm gì?

**Trả lời:** Chạy reactor từ root với `mvn -pl app -am package` hoặc bảo đảm artifact upstream phù hợp đã được cài/phát hành. Kiểm tra cả artifact version và dependency scope.

**Câu 6.** Project có `module-info.java` nhưng `javac` báo `module not found: com.acme.api`. Bước đầu nên kiểm tra gì?

**Trả lời:** Kiểm tra module name thực tế, dependency build và compiler module path. Nếu api mới biên dịch ra directory/JAR, xác nhận output đó được cung cấp cho bước compile đang lỗi.

**Câu 7.** Trong multi-project, một project có thể chứa nhiều JPMS module không?

**Trả lời:** Có thể thiết kế build phức tạp hơn, nhưng cấu hình đơn giản, dễ bảo trì thường là một JPMS named module cho mỗi Java project con có descriptor và artifact riêng.

**Câu 8.** App chạy được trên classpath nhưng khi chuyển sang module path báo package không visible. Vì sao?

**Trả lời:** JPMS thực thi quy tắc readability/exports; class public trong package chưa export hoặc module sử dụng chưa có requires tương ứng sẽ không tự truy cập được.

**Câu 9.** Một test framework không dùng được reflection vào package của module app. Có nên tự động thêm `open module` cho production không?

**Trả lời:** Không nên mặc định. Trước hết kiểm tra cấu hình test runner, cần mở đúng package cho đúng framework/module, và tránh mở rộng quyền không cần thiết trong production.

**Câu 10.** Làm sao biết JAR sau `mvn package` thật sự là explicit module?

**Trả lời:** Dùng `jar --describe-module --file path/to/app.jar` hoặc kiểm tra `module-info.class` ở root JAR. Không suy luận chỉ từ việc file có đuôi `.jar`.

## Tổng kết

Compile các Java module trong multi-project build đòi hỏi phối hợp **hai hệ dependency**:

- Maven/Gradle quyết định artifact, compile classpath/module path và thứ tự build.
- JPMS quyết định module readability, package exports và các ràng buộc khi biên dịch/chạy.

Một thiết kế ổn định khai báo đúng project dependency ở build tool, đúng `requires`/`requires transitive` trong descriptor, và đúng `exports` cho những package API thực sự được công bố. Sau khi build, cần kiểm tra modular JAR và chạy bằng `java --module-path ... -m ...` để bảo đảm cả quá trình compile lẫn runtime cùng dùng một module graph nhất quán.