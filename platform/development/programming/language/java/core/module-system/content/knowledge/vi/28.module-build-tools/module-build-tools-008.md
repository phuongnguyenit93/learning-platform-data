# Packaging modular JAR trong build

Một ứng dụng sử dụng Java Platform Module System (JPMS) không chỉ cần file `module-info.java` trong source. Khi build, hệ thống phải **biên dịch descriptor thành `module-info.class` và đóng gói class đó đúng vị trí bên trong JAR**. Artifact nhận được gọi là **modular JAR** (thường cũng gọi là explicit modular JAR).

Packaging đúng giúp `java`, `javac`, `jdeps` và `jlink` nhận diện tên module, dependency, package export/open và service declaration. Ngược lại, nếu `module-info.class` bị bỏ sót hoặc đặt sai chỗ, JAR có thể trở thành automatic module khi đặt trên module path, khiến boundary và khả năng kiểm tra dependency khác xa thiết kế ban đầu.

Bài viết hướng dẫn cấu trúc artifact, build bằng lệnh JDK, cấu hình Maven/Gradle, đóng gói resource và service provider, kiểm tra kết quả và xử lý những lỗi phổ biến.

## 1. Modular JAR khác JAR thông thường ở đâu?

Trong tình huống phổ biến, một explicit modular JAR có cấu trúc:

~~~text
org.example.greeter.jar
├── module-info.class
├── org/
│   └── example/
│       └── greeter/
│           ├── api/
│           │   └── GreetingService.class
│           └── internal/
│               └── DefaultGreetingService.class
└── META-INF/
    └── MANIFEST.MF
~~~

`module-info.class` nằm **ngay tại gốc JAR**, không nằm dưới tên package và cũng không nằm dưới thư mục `classes/` bên trong JAR thông thường.

Descriptor có thể bắt nguồn từ source:

~~~java
module org.example.greeter {
    exports org.example.greeter.api;
}
~~~

Tại compile-time, `javac` tạo `module-info.class` chứa `Module` attribute. Khi đặt JAR trên module path, module system đọc descriptor này để xác định các quan hệ module.

So sánh:

| Loại artifact | Dấu hiệu | Hành vi khi đặt trên module path |
| --- | --- | --- |
| Explicit modular JAR | Có descriptor `module-info.class` hợp lệ | JPMS sử dụng đúng `requires`, `exports`, `opens`, `uses`, `provides` |
| Non-modular JAR | Không có descriptor | Có thể trở thành automatic module với tên được suy ra hoặc khai báo qua manifest |
| JAR trên classpath | Dù có descriptor hay không, được dùng qua classpath | Class của JAR được nạp trong unnamed module của class loader tương ứng |
| JMOD | Định dạng `.jmod` với các section riêng | Chủ yếu là đầu vào compile/link-time, không phải JAR runtime trực tiếp |

Chỉ đặt `Automatic-Module-Name` vào manifest không tạo explicit modular JAR. Nó chỉ cung cấp tên ổn định cho automatic module khi artifact chưa có descriptor được dùng trong cấu hình module path.

## 2. Ví dụ hoàn chỉnh với hai module

Ta xây dựng một module API và một module CLI sử dụng API đó.

Cấu trúc source:

~~~text
project/
└── src/
    ├── org.example.greeter/
    │   ├── module-info.java
    │   └── org/example/greeter/api/
    │       └── GreetingService.java
    └── org.example.cli/
        ├── module-info.java
        └── org/example/cli/
            └── Main.java
~~~

Descriptor cho API:

~~~java
// src/org.example.greeter/module-info.java
module org.example.greeter {
    exports org.example.greeter.api;
}
~~~

Class API:

~~~java
// src/org.example.greeter/org/example/greeter/api/GreetingService.java
package org.example.greeter.api;

public final class GreetingService {
    private GreetingService() {}

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Descriptor cho CLI:

~~~java
// src/org.example.cli/module-info.java
module org.example.cli {
    requires org.example.greeter;
}
~~~

Main class:

~~~java
// src/org.example.cli/org/example/cli/Main.java
package org.example.cli;

import org.example.greeter.api.GreetingService;

public final class Main {
    public static void main(String[] args) {
        System.out.println(GreetingService.greet("JPMS"));
    }
}
~~~

Phần tiếp theo sẽ biên dịch, đóng gói và chạy cả hai module từ modular JAR thực tế.

## 3. Biên dịch bằng javac trước khi đóng gói

Từ thư mục `project`, dùng:

~~~bash
javac \
  --module-source-path src \
  -d out \
  -m org.example.greeter,org.example.cli
~~~

Trong đó:

- `--module-source-path src` xác định thư mục chứa source được phân theo tên module.
- `-d out` chỉ định thư mục output cho các class đã biên dịch.
- `-m` nêu các root module cần biên dịch.

Sau khi biên dịch thành công, output có cấu trúc:

~~~text
out/
├── org.example.greeter/
│   ├── module-info.class
│   └── org/example/greeter/api/GreetingService.class
└── org.example.cli/
    ├── module-info.class
    └── org/example/cli/Main.class
~~~

Mỗi module có một thư mục output độc lập với `module-info.class` tại gốc của thư mục module đó.

Không dùng `-C out .` để tạo một JAR chung chứa hai module descriptor ở hai thư mục con. Với packaging theo module, mỗi explicit module cần artifact hoặc vùng output tương ứng để công cụ JPMS tìm đúng descriptor.

Nếu đang sử dụng Maven/Gradle, công cụ build sẽ thay thế bước gọi `javac` thủ công, nhưng nguyên tắc descriptor tại gốc artifact vẫn giống nhau.

## 4. Đóng gói bằng jar --create

Tạo thư mục phân phối:

~~~bash
mkdir dist
~~~

Đóng gói module API:

~~~bash
jar --create \
  --file dist/org.example.greeter.jar \
  -C out/org.example.greeter .
~~~

Đóng gói module CLI:

~~~bash
jar --create \
  --file dist/org.example.cli.jar \
  -C out/org.example.cli .
~~~

Tùy chọn `-C directory .` yêu cầu công cụ đổi ngữ cảnh sang thư mục module rồi đưa toàn bộ nội dung trong đó vào gốc JAR. Đây là lý do `module-info.class` xuất hiện đúng ở gốc artifact.

Kiểm tra nội dung:

~~~bash
jar --list --file dist/org.example.greeter.jar
jar --list --file dist/org.example.cli.jar
~~~

Output rút gọn:

~~~text
META-INF/
META-INF/MANIFEST.MF
module-info.class
org/example/greeter/api/GreetingService.class
~~~

Có thể thiết lập main class khi đóng gói CLI:

~~~bash
jar --create \
  --file dist/org.example.cli.jar \
  --main-class org.example.cli.Main \
  -C out/org.example.cli .
~~~

Nếu không gắn main-class metadata, vẫn có thể chạy bằng cú pháp `-m MODULE/MAIN_CLASS` với tên main class đầy đủ.

## 5. Chạy các modular JAR đã đóng gói

Đưa cả hai JAR lên module path:

~~~bash
java \
  --module-path dist \
  --module org.example.cli/org.example.cli.Main
~~~

Kết quả:

~~~text
Hello, JPMS!
~~~

JPMS tìm `org.example.cli` trong `dist`, đọc descriptor `requires org.example.greeter` và resolve module dependency.

Có thể dùng tên rút gọn:

~~~bash
java -p dist -m org.example.cli/org.example.cli.Main
~~~

Nếu đã lưu main class metadata trong modular JAR, có thể dùng dạng chỉ có tên module theo cấu hình hỗ trợ:

~~~bash
java -p dist -m org.example.cli
~~~

Điều cần tránh là chạy:

~~~bash
java -cp dist/org.example.cli.jar org.example.cli.Main
~~~

Cách chạy classpath này không sử dụng JAR dưới dạng explicit named module. `module-info.class` trong JAR không tự biến việc khởi chạy classpath thành chạy modular.

## 6. Kiểm tra descriptor trong artifact

Đừng dựa vào tên file `.jar` để khẳng định packaging đúng. Hãy xem artifact thực tế.

Lệnh hữu ích nhất:

~~~bash
jar --describe-module \
  --file dist/org.example.greeter.jar
~~~

Kết quả sẽ thể hiện module name cùng các directive trong descriptor, ví dụ:

~~~text
org.example.greeter
exports org.example.greeter.api
requires java.base mandated
~~~

Phần `requires java.base mandated` là dependency ngầm do module system áp dụng, dù source không viết `requires java.base;`.

Kiểm tra module CLI:

~~~bash
jar --describe-module \
  --file dist/org.example.cli.jar
~~~

Kết quả có thể gồm:

~~~text
org.example.cli
requires java.base mandated
requires org.example.greeter
~~~

Lệnh tiếp theo kiểm tra Java launcher có thể nhận diện hai module từ thư mục phân phối:

~~~bash
java --module-path dist --list-modules
~~~

Tập module quan sát được sẽ bao gồm system modules và các module hợp lệ trong thư mục `dist`.

Nếu muốn xem dependency thực tế ở mức module:

~~~bash
jdeps --module-path dist --check org.example.cli
~~~

`jdeps` hữu ích để phát hiện dependency graph và kiểm tra các ràng buộc module. Nó không thay thế việc khởi chạy thử ứng dụng, đặc biệt nếu có reflection hoặc service provider nạp động.

## 7. Build modular JAR bằng Maven

Trong Maven, mỗi Maven module thường tạo một artifact riêng. Cần phân biệt **Maven module** (một dự án/artifact trong multi-module build) với **JPMS module** (định nghĩa bằng `module-info.java`).

Giả sử cấu trúc:

~~~text
workspace/
├── pom.xml
├── greeter-api/
│   ├── pom.xml
│   └── src/main/java/
│       ├── module-info.java
│       └── org/example/greeter/api/GreetingService.java
└── greeter-cli/
    ├── pom.xml
    └── src/main/java/
        ├── module-info.java
        └── org/example/cli/Main.java
~~~

Parent POM chỉ định hai project con:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>org.example</groupId>
  <artifactId>workspace</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>

  <modules>
    <module>greeter-api</module>
    <module>greeter-cli</module>
  </modules>

  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <pluginManagement>
      <plugins>
        <plugin>
          <groupId>org.apache.maven.plugins</groupId>
          <artifactId>maven-compiler-plugin</artifactId>
          <version>3.14.1</version>
        </plugin>
        <plugin>
          <groupId>org.apache.maven.plugins</groupId>
          <artifactId>maven-jar-plugin</artifactId>
          <version>3.4.2</version>
        </plugin>
      </plugins>
    </pluginManagement>
  </build>
</project>
~~~

Trong `greeter-api/pom.xml`, project có `groupId=org.example`, `artifactId=greeter-api`, `version=1.0.0`, `packaging=jar` và tham chiếu parent. Trong `greeter-cli/pom.xml`, khai báo dependency Maven:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.example</groupId>
    <artifactId>greeter-api</artifactId>
    <version>1.0.0</version>
  </dependency>
</dependencies>
~~~

Và descriptor Java trong project CLI:

~~~java
module org.example.cli {
    requires org.example.greeter;
}
~~~

Hai khai báo này phục vụ mục đích khác nhau:

- `<dependency>` trong POM giúp Maven lấy artifact và đưa dependency vào quá trình build.
- `requires` trong `module-info.java` tạo quan hệ readability tại cấp JPMS.

Khi dependency là explicit named module và toolchain/plugin được cấu hình phù hợp, Maven Compiler Plugin biên dịch module theo module path. Maven JAR Plugin đóng gói output trong `target/classes`, bao gồm `module-info.class`.

Build từ thư mục root:

~~~bash
mvn clean package
~~~

Kết quả thường là:

~~~text
greeter-api/target/greeter-api-1.0.0.jar
greeter-cli/target/greeter-cli-1.0.0.jar
~~~

Tên JAR là Maven artifact name, không nhất thiết trùng tên JPMS module. **Tên module thực tế được quyết định bởi descriptor**, không phải `artifactId`.

Kiểm tra:

~~~bash
jar --describe-module \
  --file greeter-api/target/greeter-api-1.0.0.jar
~~~

Khi dùng plugin hoặc version Maven khác, hãy kiểm tra khả năng hỗ trợ JPMS và cấu hình compiler tương ứng thay vì mặc định mọi JAR được tạo ra đều modular.

## 8. Build modular JAR bằng Gradle

Với Gradle Java Plugin, một cách cấu hình Kotlin DSL cho project có `module-info.java`:

~~~kotlin
plugins {
    java
}

java {
    modularity.inferModulePath.set(true)

    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

Cấu trúc source tiêu chuẩn:

~~~text
greeter-api/
├── build.gradle.kts
└── src/main/java/
    ├── module-info.java
    └── org/example/greeter/api/GreetingService.java
~~~

Trong project CLI, khai báo dependency tới project API:

~~~kotlin
dependencies {
    implementation(project(":greeter-api"))
}
~~~

Và file `src/main/java/module-info.java` của CLI:

~~~java
module org.example.cli {
    requires org.example.greeter;
}
~~~

Tương tự Maven, `implementation(project(":greeter-api"))` giúp Gradle cung cấp artifact để compile, còn `requires org.example.greeter` là quan hệ module được kiểm tra bởi `javac`.

Build:

~~~bash
./gradlew clean jar
~~~

Hoặc trên Windows:

~~~powershell
.\gradlew.bat clean jar
~~~

JAR thường nằm trong:

~~~text
greeter-api/build/libs/
greeter-cli/build/libs/
~~~

Dùng `jar --describe-module --file ...` để xác nhận descriptor thực sự đã được đóng gói. Nếu Gradle đang biên dịch trên classpath, hãy kiểm tra `modularity.inferModulePath`, toolchain và các dependency được nhận diện như named/automatic module.

## 9. Chọn Java release và toolchain thống nhất

Module descriptor được giới thiệu trong Java 9. Vì vậy:

- Build explicit modular JAR thông thường cần compiler hỗ trợ JPMS.
- `--release` phải tương thích với các API được dùng và class-file target.
- Java runtime dùng để chạy phải có khả năng đọc class file và module descriptor đã biên dịch.
- CI, local và môi trường phát hành nên sử dụng toolchain có phiên bản được quản lý rõ.

Ví dụ `javac`:

~~~bash
javac --release 21 \
  --module-source-path src \
  -d out \
  -m org.example.greeter,org.example.cli
~~~

Trong Maven:

~~~xml
<properties>
  <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Trong Gradle, dùng Java toolchain để quản lý compiler. Nếu ứng dụng phải chạy trên Java 17, biên dịch `--release 21` sẽ tạo class file không phù hợp. Hãy chọn Java release theo runtime tối thiểu được hỗ trợ.

Một số thư viện muốn hỗ trợ Java 8 và cung cấp descriptor cho Java 9+ có thể áp dụng **multi-release JAR**: class thông thường tương thích Java 8, còn `module-info.class` đặt trong `META-INF/versions/9/` cùng manifest `Multi-Release: true`. Đây là quy trình đóng gói nâng cao cần cấu hình build riêng và kiểm tra trên cả hai nhóm runtime; không nên chỉ chuyển vị trí `module-info.class` thủ công rồi mặc định mọi công cụ nhận đúng.

## 10. Packaging resource mà không phá cấu trúc module

Modular JAR vẫn có thể chứa file resource:

~~~text
org.example.greeter.jar
├── module-info.class
├── org/example/greeter/api/GreetingService.class
├── org/example/greeter/messages.properties
└── META-INF/MANIFEST.MF
~~~

Với Maven hoặc Gradle, resource trong `src/main/resources` thường được copy vào output rồi đóng gói vào JAR.

Ví dụ:

~~~text
greeter-api/
├── src/main/java/module-info.java
├── src/main/java/org/example/greeter/api/GreetingService.java
└── src/main/resources/org/example/greeter/messages.properties
~~~

Không để `module-info.class` vào `src/main/resources` như một file độc lập không được compiler quản lý. Descriptor nên được biên dịch từ `module-info.java`.

Việc resource tồn tại trong JAR không bảo đảm mọi module khác có thể đọc resource đó tùy ý. Resource trong named module chịu các quy tắc truy cập module/resource tương ứng; đối với resource đóng trong package, quyền mở package và cách gọi API lấy resource có thể ảnh hưởng tới khả năng đọc từ bên ngoài.

Khi dùng framework đọc resource hoặc reflection, hãy kiểm tra package `opens` và cơ chế class loader thay vì đưa toàn bộ source vào thư mục resource để “né” module boundary.

## 11. Packaging service provider

Nếu module cung cấp implementation cho SPI, khai báo `provides ... with ...` trong descriptor:

~~~java
module org.example.greeter.provider {
    requires org.example.greeter.api;

    provides org.example.greeter.api.Greeter
        with org.example.greeter.provider.DefaultGreeter;
}
~~~

Module consumer khai báo:

~~~java
module org.example.greeter.client {
    requires org.example.greeter.api;
    uses org.example.greeter.api.Greeter;
}
~~~

Khi đóng gói JAR, `module-info.class` sẽ chứa service metadata phù hợp. Khi sử dụng explicit named module trên module path, `ServiceLoader` đọc thông tin provider theo module descriptor.

Các thư viện legacy thường dùng file:

~~~text
META-INF/services/org.example.greeter.api.Greeter
~~~

Cơ chế này phù hợp cho provider được khám phá qua classpath hoặc cách dùng tương thích. Với explicit named module, hãy định nghĩa `provides` đúng trong `module-info.java`; đừng chỉ chép file `META-INF/services` rồi kỳ vọng service sẽ được module system tự xử lý như khai báo module.

Việc provider JAR có trên module path cũng chưa chắc đủ để nó được resolve vào runtime graph của một ứng dụng. Có thể cần đưa provider module vào tập root phù hợp, cấu hình service binding hoặc dùng plugin layer tương ứng. Hãy kiểm tra `java --show-module-resolution` và cách ứng dụng gọi `ServiceLoader` khi provider không được tìm thấy.

## 12. Nhiều dependency: đừng đóng gói sai ranh giới module

Trong modular build, mỗi module có descriptor và tập package riêng. Không nên tạo một fat JAR bằng cách gộp tùy ý class của nhiều explicit modules vào cùng một JAR rồi giữ lại một descriptor bất kỳ.

Các rủi ro:

- Chỉ có một `module-info.class` được giữ lại, làm mất thông tin module của dependency khác.
- Package bị gộp gây split package hoặc xung đột namespace.
- `requires`, `exports`, `opens` và service declarations không còn phản ánh nội dung thực tế.
- Những công cụ phân tích module có thể cho kết quả sai so với build ban đầu.

Nếu ứng dụng cần một artifact triển khai, cân nhắc:

1. Giữ mỗi explicit module là một modular JAR và phân phối cùng module path.
2. Dùng `jlink` để liên kết các module cần thiết thành runtime image.
3. Dùng `jpackage` khi cần gói cài đặt ứng dụng và runtime theo nền tảng.
4. Chỉ tạo fat JAR khi chủ động từ bỏ hoặc tái thiết kế module boundaries, với cấu hình packaging phù hợp và test rõ ràng.

Đối với dependency legacy không có descriptor, Maven/Gradle có thể đưa chúng vào module path dưới dạng automatic modules trong một số cấu hình. Tên automatic module có thể dựa trên `Automatic-Module-Name` hoặc tên JAR. Đừng để module descriptor phụ thuộc vào tên suy ra dễ thay đổi nếu có thể chuyển thư viện thành explicit modular JAR.

## 13. Kiểm tra module name ổn định

Một module được định danh bởi tên trong `module-info.java`, chẳng hạn:

~~~java
module org.example.greeter {
    exports org.example.greeter.api;
}
~~~

Artifact có thể được phát hành dưới tên:

~~~text
greeter-api-1.0.0.jar
~~~

Điều này hoàn toàn bình thường: Maven/Gradle quản lý artifact coordinate, còn JPMS quản lý module name.

Nếu artifact chưa có descriptor, có thể dùng manifest entry:

~~~text
Automatic-Module-Name: org.example.greeter
~~~

để cung cấp tên module ổn định khi JAR được đặt trên module path. Tuy nhiên, artifact đó vẫn là **automatic module** khi chưa có explicit descriptor.

Sau khi thêm `module-info.java` thật, nên giữ tên module ổn định nếu các consumer đã sử dụng tên đó trong `requires`. Đổi tên module là thay đổi hợp đồng ở cấp module và có thể yêu cầu tất cả downstream consumers cập nhật descriptor.

## 14. Kiểm tra build artifact trong CI

Một build thành công chưa bảo đảm packaging đúng JPMS. Có thể thêm các bước kiểm tra artifact vào pipeline.

**Kiểm tra descriptor:**

~~~bash
jar --describe-module --file dist/org.example.greeter.jar
~~~

**Liệt kê entry gốc:**

~~~bash
jar --list --file dist/org.example.greeter.jar
~~~

Đảm bảo có `module-info.class` ở gốc JAR (trừ trường hợp multi-release JAR được thiết kế có chủ đích).

**Liệt kê module mà launcher nhìn thấy:**

~~~bash
java --module-path dist --list-modules
~~~

**Chạy ứng dụng modular:**

~~~bash
java -p dist -m org.example.cli/org.example.cli.Main
~~~

**Hiển thị module resolution:**

~~~bash
java --show-module-resolution \
  --module-path dist \
  -m org.example.cli/org.example.cli.Main
~~~

Nếu CI cần đảm bảo artifact không vô tình chuyển thành automatic module, hãy kiểm tra output `jar --describe-module` có descriptor và các directive dự kiến. Nhiều quy trình cũng kiểm tra tên module, exports và requires bằng test hoặc script nhỏ để ngăn build plugin làm mất `module-info.class`.

Chỉ kiểm tra rằng file JAR “chạy được” bằng `java -cp ...` là chưa đủ: classpath có thể bỏ qua module boundary nên che giấu lỗi packaging.

## 15. Dùng modular JAR làm đầu vào jlink

Một lợi ích của explicit modular JAR là có thể tham gia quá trình liên kết runtime image bằng `jlink` khi toàn bộ dependency tương thích.

Ví dụ:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:dist" \
  --add-modules org.example.cli \
  --launcher greeter=org.example.cli/org.example.cli.Main \
  --output runtime-image
~~~

Sau khi linking thành công:

~~~bash
./runtime-image/bin/greeter
~~~

Kết quả:

~~~text
Hello, JPMS!
~~~

Windows sử dụng dấu chấm phẩy thay dấu hai chấm khi ghép nhiều đường dẫn trong `--module-path`:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;dist" --add-modules org.example.cli --launcher greeter=org.example.cli/org.example.cli.Main --output runtime-image
~~~

`jlink` yêu cầu tập module có thể liên kết phù hợp. Automatic modules không được hỗ trợ như explicit modules trong quá trình linking thông thường. Nếu một dependency chỉ tồn tại dưới dạng automatic module, nên cân nhắc modularize thư viện hoặc điều chỉnh kiến trúc trước khi yêu cầu `jlink` tạo image.

Nếu ứng dụng không cần runtime image riêng, phân phối modular JAR với JDK/runtime tương thích và module path rõ ràng vẫn là phương án hợp lệ.

## 16. Lỗi phổ biến và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| `jar --describe-module` báo automatic module | Không có `module-info.class` được đóng gói đúng | Kiểm tra output compiler và nội dung JAR |
| `module not found: org.example.greeter` | Artifact không nằm trên module path hoặc tên module không khớp | Kiểm tra `--module-path`, descriptor và tên JAR thực tế |
| `package ... is not visible` | Module consumer thiếu readability hoặc dependency chưa export package | Kiểm tra `requires`, `exports` và compiler module path |
| `ClassNotFoundException` khi chạy | Khác biệt giữa classpath và module path, hoặc artifact/resource bị thiếu | Kiểm tra cách launch và nội dung artifact |
| Duplicate module name | Hai artifact cùng định nghĩa hoặc công bố cùng module name | Làm sạch module path và dependency resolution |
| Split package gây lỗi resolution | Hai named modules có package trùng trong graph không hợp lệ | Tách package và điều chỉnh module boundaries |
| `java -cp` chạy nhưng `java -m` thất bại | Build chưa thực sự đáp ứng module boundary | Kiểm tra modular launch, `requires`, `exports`, `opens` |
| Service provider không được tìm thấy | Thiếu `provides`, `uses`, hoặc provider chưa được resolve | Kiểm tra descriptor, root modules và service binding |
| `jlink` từ chối automatic module | Dependency chưa có explicit module descriptor | Modularize dependency hoặc chọn hình thức phân phối khác |
| CI dùng class-file version không phù hợp runtime | Compiler toolchain hoặc `--release` cao hơn runtime mục tiêu | Khóa JDK/toolchain và chạy test trên runtime thấp nhất hỗ trợ |

## 17. Quy trình packaging đề xuất

Với một project modular mới, quy trình thực tế có thể đi theo thứ tự:

1. **Thiết kế module name:** chọn tên ổn định, rõ ràng và không phụ thuộc vào version artifact.
2. **Viết descriptor:** khai báo `requires`, `exports`, `opens`, `uses`, `provides` cần thiết.
3. **Thiết lập build tool:** chọn JDK toolchain và Java release; cấu hình Maven/Gradle nhận diện module path.
4. **Biên dịch:** đảm bảo `module-info.java` được compiler chuyển thành `module-info.class`.
5. **Đóng gói từng module:** giữ descriptor ở gốc modular JAR; kèm class/resource phù hợp.
6. **Kiểm tra artifact:** dùng `jar --list` và `jar --describe-module`.
7. **Chạy theo module path:** dùng `java -p ... -m ...` thay vì chỉ chạy classpath.
8. **Kiểm tra resolution:** dùng `--show-module-resolution` và `jdeps` nếu cần.
9. **Kiểm tra dịch vụ/reflective access:** xác nhận service provider được resolve và package mở đúng module.
10. **Phân phối:** chọn modular JAR + module path hoặc image do `jlink` tạo theo yêu cầu triển khai.

Checklist này nên được tự động hóa trong build/CI để việc thêm dependency hoặc thay plugin không vô tình làm mất module metadata.

## Kết luận

**Packaging modular JAR** nghĩa là bảo toàn ranh giới JPMS từ source tới artifact phân phối. Một explicit modular JAR cần mang `module-info.class` hợp lệ ở đúng vị trí, đồng thời chứa class, resource và metadata phù hợp với descriptor.

`javac` tạo descriptor và các class; `jar` đóng gói từng module; Maven/Gradle tự động hóa các bước đó khi được cấu hình đúng. Sau build, hãy dùng `jar --describe-module`, `java --module-path ... --list-modules` và modular launch để kiểm tra artifact. Không dựa vào việc JAR chạy được trên classpath để kết luận cấu hình module đã chính xác. Với hệ thống cần runtime image gọn và dễ phân phối, modular JAR hợp lệ cũng là nền tảng quan trọng cho quá trình liên kết bằng `jlink`.
