# Biên dịch dự án JPMS với module-info.java bằng Maven

**JPMS (Java Platform Module System)** là hệ thống module được Java giới thiệu từ Java 9. Trong một dự án Java 17, ta có thể khai báo ranh giới module bằng tệp `module-info.java` và sử dụng Maven Compiler Plugin để biên dịch theo **module path** thay vì chỉ dựa vào classpath truyền thống.

Một điểm thường gây nhầm lẫn: **module Maven** và **module JPMS** không đồng nghĩa. Maven module là một dự án con có `pom.xml` và thường được liệt kê trong `<modules>` của aggregator. JPMS module là một đơn vị do JVM/javac nhận diện bằng tên trong `module-info.java`, có quan hệ `requires` và các quy tắc `exports`, `opens`. Hai khái niệm có thể ánh xạ một-một trong dự án đơn giản, nhưng do hai hệ thống khác nhau quản lý.

Ví dụ tối giản về module descriptor:

```java
module dev.training.catalog.cli {
    requires dev.training.catalog.core;
}
```

Điều này có nghĩa module `dev.training.catalog.cli` **đọc** module `dev.training.catalog.core`. Muốn mã trong CLI sử dụng một class ở module Core, lớp đó còn phải thuộc **package được export** (và có access modifier phù hợp):

```java
module dev.training.catalog.core {
    exports dev.training.catalog.api;
}
```

Maven đồng thời cần biết nơi tìm artifact chứa module Core, ví dụ bằng dependency trong POM của CLI:

```xml
<dependency>
    <groupId>dev.training.jpms</groupId>
    <artifactId>catalog-core</artifactId>
    <version>1.0.0</version>
</dependency>
```

**Ba khai báo không thay thế nhau:** `<dependency>` giúp Maven giải quyết artifact; `requires` giúp JPMS thiết lập quan hệ đọc giữa module; `exports` cho phép mã ngoài module truy cập API trong package phù hợp.

Bài này hướng dẫn xây dựng **hai Maven subprojects chứa hai JPMS named modules**, cấu hình biên dịch Java 17, build reactor, chạy bằng `java --module-path --module`, kiểm tra `module-info.class`, sửa lỗi liên quan module readability và package exports, và hiểu giới hạn khi kết hợp thư viện Java cũ.

## 1. Ba lớp mô hình cần phân biệt

| Tầng | Khái niệm | File / công cụ | Điều nó quyết định |
| --- | --- | --- | --- |
| Maven project | Artifact `groupId:artifactId:version` | `pom.xml`, Maven Resolver | Build, dependencies, version, plugin, repository. |
| Maven reactor | Dự án nhiều module Maven | Parent `<modules>`, `-pl`, `-am` | Tập subprojects và thứ tự build theo quan hệ thực. |
| JPMS | Java named module | `module-info.java`, `javac`, JVM | Tên module, readability, package accessibility và service binding. |
| Java package | Namespace của class | `package x.y;` | Nhóm class; không tự tạo JPMS module. |
| Java classpath | Cơ chế tìm class truyền thống | `-cp` / `--class-path` | Các class thường thuộc unnamed module khi chạy trên classpath. |
| Java module path | Cơ chế quan sát named modules | `-p` / `--module-path` | Nơi javac/JVM tìm explicit hoặc automatic modules. |

Ví dụ:

```text
Maven groupId:     dev.training.jpms
Maven artifactId:  catalog-core
Maven version:     1.0.0
JPMS module name:  dev.training.catalog.core
Java API package:  dev.training.catalog.api
Java class:        dev.training.catalog.api.Greeting
```

Những tên này được chọn sao cho dễ hiểu, nhưng **JPMS module name không được suy ra từ Maven artifactId bằng một quy tắc chung có thể tin cậy**. Với explicit module, tên chính thức được ghi trong `module-info.java`; với automatic module, tên có thể đến từ manifest hoặc được suy ra theo quy tắc từ tên JAR.

### Tại sao cần module-info.java?

Khi code chỉ dùng classpath, việc giữ một JAR trên classpath thường khiến các `public` class/package của JAR dễ được truy cập bởi những JAR khác. Với JPMS, **module descriptor** cung cấp hàng rào API: module chỉ đọc những modules phù hợp, và các package không được `exports` không tự trở thành API bên ngoài, ngay cả khi trong đó có class `public`.

JPMS không thay thế access modifiers của Java. Nếu class là package-private, việc package được export cũng không làm class đó thành public. Muốn class được sử dụng từ module khác, phải thỏa cả **module readability, package export và Java visibility**.

## 2. Tệp module-info.java nằm ở đâu?

Với cấu trúc Maven tiêu chuẩn, đặt file ở:

```text
src/main/java/module-info.java
```

File phải nằm **ngay tại source root** của module tương ứng, không nằm trong thư mục package `dev/training/...`. Nó khai báo đúng một Java module:

```java
module dev.training.catalog.core {
    exports dev.training.catalog.api;
}
```

Tệp này không khai báo `package`, không chứa `public class Main` và không thay thế các class Java thông thường. Khi compile, `javac` tạo `module-info.class`; Maven JAR Plugin sẽ đóng gói class descriptor đó vào JAR module.

Một cấu trúc tương ứng:

```text
catalog-core/
├── pom.xml
└── src/main/java/
    ├── module-info.java
    └── dev/training/catalog/api/
        └── Greeting.java
```

Nếu vô tình đặt `module-info.java` vào `src/test/java`, bạn đang tác động tới **test compilation**, không tự làm main artifact thành module JPMS. Nếu bỏ file khỏi cả main source và generated bytecode, JAR sẽ không còn explicit module descriptor trong main artifact.

## 3. Các directive quan trọng của module-info.java

Một module descriptor có thể khai báo:

```java
module dev.training.example {
    requires java.logging;
    requires transitive dev.training.publicapi;
    requires static dev.training.compileonly;

    exports dev.training.example.api;
    exports dev.training.example.internal to dev.training.friend;

    opens dev.training.example.model to dev.training.framework;

    uses dev.training.example.spi.Formatter;
    provides dev.training.example.spi.Formatter
        with dev.training.example.impl.DefaultFormatter;
}
```

**Đây là một đoạn minh họa cú pháp, không phải file chạy được độc lập**: các modules, packages và classes giả định trong ví dụ phải có thật mới compile thành công. Các directive có vai trò:

| Directive | Ý nghĩa |
| --- | --- |
| `requires m;` | Module hiện tại đọc module `m` (và cần module đó được quan sát/resolve theo quy tắc JPMS). |
| `requires transitive m;` | Module khác đọc module hiện tại cũng có thể đọc `m` theo quy tắc transitive readability. |
| `requires static m;` | Bắt buộc để compile, nhưng sự hiện diện của `m` ở runtime là tùy chọn theo module resolution; code sử dụng nó vẫn có thể lỗi nếu thiếu. |
| `exports p;` | Cho phép modules khác truy cập `public` types trong package `p` nếu có readability. |
| `exports p to a,b;` | Qualified export, chỉ cho modules `a` và `b` được truy cập. |
| `opens p;` | Mở package để hỗ trợ deep reflection ở runtime; **không cấp quyền import/compile** tương tự `exports`. |
| `opens p to framework;` | Chỉ mở package cho module được chỉ định, hữu ích cho thư viện reflection. |
| `uses ServiceType;` | Module dùng service qua cơ chế JPMS `ServiceLoader`. |
| `provides ServiceType with Impl;` | Module cung cấp implementation service. |

Module luôn đọc `java.base` một cách **ngầm định**, vì vậy các ví dụ Java đơn giản không cần thêm `requires java.base;`. Nếu dùng API logging của JDK, ví dụ `java.util.logging`, module thường cần `requires java.logging;`.

### 3.1. Readability và accessibility là hai điều kiện khác nhau

Giả sử CLI có `requires dev.training.catalog.core;`. Điều này tạo **readability edge** tới Core. Nếu package `dev.training.catalog.internal` không được export, CLI **không thể import** một `public` class trong package nội bộ đó qua JPMS thông thường.

Ngược lại, nếu Core có `exports dev.training.catalog.api;` nhưng CLI không có `requires dev.training.catalog.core;`, CLI có thể vẫn không đọc được module Core. Để sử dụng API bình thường, **cả hai vế phải đúng**.

### 3.2. `opens` không phải `exports`

`exports` cung cấp access ở compile/run time tới các public/protected types và members thích hợp; `opens` cho phép reflective access sâu hơn ở runtime. Một framework JSON/ORM có thể cần reflection vào constructor/field không public và vì vậy cần `opens`, nhưng bạn không nên viết `open module` hoặc `--add-opens` trên toàn bộ ứng dụng chỉ vì một lỗi chưa xác định.

Ưu tiên **mở đúng package cho đúng module** và kiểm tra tài liệu của framework. `opens` cũng không tự làm một package trở thành API để import từ module khác.

### 3.3. `requires transitive` không phải “Maven transitive dependency”

Maven tự thu thập dependency bắc cầu qua các POM. JPMS `requires transitive` định nghĩa **module readability** khi module khách hàng đọc module hiện tại. Một artifact có thể xuất hiện trong Maven dependency tree nhưng vẫn không thể dùng API của nó trong named module nếu thiếu readability phù hợp.

Ví dụ:
- Maven: app -> facade -> API, app có thể nhận API JAR bắc cầu.
- JPMS: app `requires facade;` và facade `requires transitive api;` cho phép app đọc module API.
- Nếu facade chỉ `requires api;`, app không tự được readability tới API. App có thể cần `requires api;` trực tiếp.

## 4. Maven Compiler Plugin biên dịch JPMS như thế nào?

Từ Java 9, `javac` hỗ trợ:
- `--release` để chọn ngữ nghĩa API/bytecode Java mục tiêu.
- `--module-path` hoặc `-p` để tìm modules.
- `--module` hoặc các tùy chọn modular compilation tùy ngữ cảnh.
- `--class-path` hoặc `-cp` cho kiểu compile truyền thống.

Maven Compiler Plugin 3.14.1 hỗ trợ `useModulePath` (mặc định `true` trong cấu hình hỗ trợ) và có thể sử dụng module path khi **đích Java 9+ và `module-info.java`/`module-info.class` xuất hiện**. Với lab Java 17 chuẩn, không cần đưa `--module-path` thủ công vào `compilerArgs`: Maven giải quyết dependency từ POM và chuyển chúng cho compiler theo cơ chế plugin.

Cấu hình quan trọng:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
        </plugin>
    </plugins>
</build>
```

Đây là đoạn POM, không phải file độc lập. `maven.compiler.release` tương ứng tùy chọn `javac --release 17`. Điều này khác với chỉ thiết lập `<source>17</source>` và `<target>17</target>`: `--release` còn lựa chọn tập API JDK mục tiêu được hỗ trợ.

**Máy chạy Maven phải có JDK với `javac` hỗ trợ release 17**, ví dụ JDK 17 trở lên còn hỗ trợ `--release 17`. Nếu Maven chạy bằng JRE hoặc JDK quá cũ, `pom.xml` không thể tự tạo một compiler mới. Dùng `mvn -version` và `javac -version` để đối chiếu; Maven Toolchains có thể cấu hình JDK build khác khi thật sự cần.

### 4.1. Nếu `useModulePath=false` thì sao?

Với Maven Compiler Plugin hỗ trợ tham số này:

```xml
<configuration>
    <useModulePath>false</useModulePath>
</configuration>
```

bắt plugin luôn dùng classpath theo cấu hình parameter. Đối với project có `module-info.java` và `requires` tên module, điều này có thể gây lỗi “module not found” hoặc lỗi liên quan visibility vì modular sources cần môi trường compile thích hợp. **Không dùng tắt module path để chữa một lỗi JPMS mà chưa hiểu nguyên nhân**. Trong dự án JPMS chuẩn, giữ mặc định phù hợp thường đơn giản hơn.

### 4.2. Compile goal và lifecycle

Với packaging `jar`, goal `compiler:compile` được bind vào phase `compile` và `compiler:testCompile` vào `test-compile`. Vì vậy:

```bash
mvn compile
```

gọi các goal cần thiết của lifecycle tới `compile`; không phải cùng nghĩa với việc chỉ gọi riêng `mvn compiler:compile`.

Khi chạy Maven reactor nhiều module, Maven có thể sắp xếp thứ tự dự án theo các **artifact dependency edges** được khai báo thực sự, chứ không chỉ dựa vào thứ tự dòng `<module>`. Đây là điểm thiết yếu cho lab 2 module dưới đây.

## 5. Lab Java 17: hai Maven modules, hai JPMS named modules

Ta tạo:
1. `catalog-core`: một Maven subproject có JPMS module `dev.training.catalog.core`, export package `dev.training.catalog.api`.
2. `catalog-cli`: một Maven subproject có JPMS module `dev.training.catalog.cli`, `requires` module Core và gọi API của Core.

**Sơ đồ hai loại quan hệ song song:**

```text
Maven reactor:
  jpms-lab (packaging=pom)
  ├── catalog-core  (dev.training.jpms:catalog-core:1.0.0)
  └── catalog-cli   (dev.training.jpms:catalog-cli:1.0.0)
         |
         +---- dependency Maven ----> catalog-core

JPMS runtime:
  dev.training.catalog.cli
         |
         +---- requires -----------> dev.training.catalog.core
                                          |
                                          +---- exports dev.training.catalog.api
```

Hai subprojects được gộp bởi Maven aggregator nhưng mỗi subproject có **POM** riêng và **module descriptor** riêng. Lab không yêu cầu thư viện Java bên ngoài, chỉ dùng JDK17 và Maven plugins chuẩn.

### 5.1. Cây thư mục đầy đủ

```text
jpms-lab/
├── pom.xml
├── catalog-core/
│   ├── pom.xml
│   └── src/main/java/
│       ├── module-info.java
│       └── dev/training/catalog/api/
│           └── Greeting.java
└── catalog-cli/
    ├── pom.xml
    └── src/main/java/
        ├── module-info.java
        └── dev/training/catalog/cli/
            └── Main.java
```

Hãy tạo đúng các tệp được trình bày trong những mục sau. Trong Java, thư mục source code phải tương ứng với khai báo `package`, và `module-info.java` không nằm dưới package.

Linux/macOS, từ thư mục làm việc muốn tạo dự án:

```bash
mkdir -p jpms-lab/catalog-core/src/main/java/dev/training/catalog/api
mkdir -p jpms-lab/catalog-cli/src/main/java/dev/training/catalog/cli
cd jpms-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "jpms-lab/catalog-core/src/main/java/dev/training/catalog/api" | Out-Null
New-Item -ItemType Directory -Force -Path "jpms-lab/catalog-cli/src/main/java/dev/training/catalog/cli" | Out-Null
Set-Location jpms-lab
```

### 5.2. Parent aggregator POM: `jpms-lab/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.jpms</groupId>
    <artifactId>jpms-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>catalog-core</module>
        <module>catalog-cli</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
```

Giải thích:
- `packaging=pom` dành cho parent/aggregator, không tạo một application JAR cho root.
- `<modules>` liệt kê hai Maven subprojects cần đưa vào reactor khi chạy từ root.
- `maven.compiler.release=17` được các child projects kế thừa qua `<parent>`.
- `pluginManagement` quản lý version của Compiler/JAR Plugin khi chúng được dùng qua lifecycle mặc định ở child `jar` projects. Nó **không tự bind một goal mới tùy ý**.
- Parent không đưa `catalog-core` vào classpath CLI chỉ vì đã liệt kê nó trong `<modules>`. CLI vẫn phải có `<dependency>`.

### 5.3. POM của Core: `catalog-core/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training.jpms</groupId>
        <artifactId>jpms-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>catalog-core</artifactId>
    <packaging>jar</packaging>
</project>
```

Maven coordinates của project là `dev.training.jpms:catalog-core:1.0.0`. `groupId` và `version` được kế thừa từ parent; `artifactId` riêng là `catalog-core`.

**Tệp `catalog-core/src/main/java/module-info.java`:**

```java
module dev.training.catalog.core {
    exports dev.training.catalog.api;
}
```

Core khai báo JPMS module tên `dev.training.catalog.core` và xuất public API package `dev.training.catalog.api`.

**Tệp `catalog-core/src/main/java/dev/training/catalog/api/Greeting.java`:**

```java
package dev.training.catalog.api;

public final class Greeting {

    private Greeting() {
    }

    public static String message(String who) {
        return "Hello, " + who + " from JPMS!";
    }
}
```

Class là `public` và nằm trong package đã export. Phương thức `message()` trả về String cố định theo tham số, không phụ thuộc timestamp, locale hay network.

### 5.4. POM của CLI: `catalog-cli/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training.jpms</groupId>
        <artifactId>jpms-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>catalog-cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.training.jpms</groupId>
            <artifactId>catalog-core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

**Maven dependency** của CLI tới Core là **trực tiếp** và dùng `compile` scope mặc định. Điều này giúp reactor biết Core cần build trước CLI và giúp Compiler Plugin tìm artifact Core.

Dùng `${project.version}` ở đây phù hợp vì hai child projects kế thừa **cùng phiên bản 1.0.0**. Nếu tổ chức version mỗi module độc lập, không áp dụng biểu thức này một cách máy móc.

**Tệp `catalog-cli/src/main/java/module-info.java`:**

```java
module dev.training.catalog.cli {
    requires dev.training.catalog.core;
}
```

`requires` phải dùng **tên JPMS module `dev.training.catalog.core`**, không dùng Maven `artifactId=catalog-core` hoặc tọa độ `dev.training.jpms:catalog-core`.

**Tệp `catalog-cli/src/main/java/dev/training/catalog/cli/Main.java`:**

```java
package dev.training.catalog.cli;

import dev.training.catalog.api.Greeting;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message("Maven"));
    }
}
```

CLI có main class ở package của chính module CLI, gọi public API của Core. CLI **không cần export** package `dev.training.catalog.cli` để Java launcher gọi main class bằng cú pháp `--module module/mainclass`.

## 6. Biên dịch toàn reactor bằng Maven

Đứng tại thư mục `jpms-lab`:

```bash
mvn -version
mvn -B -ntp clean package
```

Yêu cầu máy có JDK 17+ và Maven tương thích với các plugin được ghim. Lần chạy đầu Maven có thể tải Maven Compiler Plugin, Maven JAR Plugin và dependencies của chúng; không cần tải thư viện ứng dụng bên thứ ba cho lab.

Quy trình được kỳ vọng:
1. Maven đọc root POM, thu thập `catalog-core` và `catalog-cli`.
2. Nhờ dependency POM, reactor biết CLI cần artifact Core.
3. Compiler Plugin biên dịch Core, phát sinh `module-info.class` và `Greeting.class`.
4. JAR Plugin đóng gói Core thành `catalog-core-1.0.0.jar`.
5. CLI được biên dịch với module Core khả dụng trên module path; javac kiểm tra `requires` và `exports`.
6. JAR Plugin đóng gói CLI thành `catalog-cli-1.0.0.jar`.

Đầu ra dự kiến:

```text
catalog-core/target/catalog-core-1.0.0.jar
catalog-cli/target/catalog-cli-1.0.0.jar
```

Maven log thực tế có thêm các phase, plugin goal headers và `BUILD SUCCESS` nếu mọi bước hoàn thành. **Không dùng đoạn mô tả này làm toàn bộ stdout chính xác**; thứ tự log và thời gian phụ thuộc môi trường.

### 6.1. Vì sao build ở root quan trọng?

Nếu bạn chạy:

```bash
mvn -f catalog-cli/pom.xml package
```

trước khi `catalog-core:1.0.0` đã có trong local/remote Maven repository phù hợp, Maven có thể báo **Could not resolve dependencies**. POM của CLI có dependency đến Core, nhưng Maven invocation chỉ đọc POM CLI nên không tự gom reactor root khi bạn dùng `-f` như vậy.

Chạy từ root:

```bash
mvn -pl :catalog-cli -am clean package
```

có thể chọn CLI cùng upstream reactor project mà CLI cần (Core), nhờ `-pl` (*projects list*) và `-am` (*also make*). Đây là cách build từng phần trong một reactor mà vẫn bảo đảm dependencies module nội bộ được cung cấp.

`<modules>` là quan hệ aggregation; `<dependency>` mới là quan hệ artifact dependency. Nếu bỏ dependency CLI -> Core, reactor không thể suy ra classpath Java đúng chỉ từ việc cả hai được liệt kê trong root.

## 7. Chạy ứng dụng bằng JPMS module path

Sau khi `mvn clean package` thành công và đứng tại **jpms-lab**, dùng Java launcher với cả hai JAR.

**Linux/macOS:**

```bash
java --module-path "catalog-core/target/catalog-core-1.0.0.jar:catalog-cli/target/catalog-cli-1.0.0.jar" --module dev.training.catalog.cli/dev.training.catalog.cli.Main
```

**Windows PowerShell:**

```powershell
java --module-path "catalog-core\target\catalog-core-1.0.0.jar;catalog-cli\target\catalog-cli-1.0.0.jar" --module dev.training.catalog.cli/dev.training.catalog.cli.Main
```

**Stdout chính xác của chương trình Java:**

```text
Hello, Maven from JPMS!
```

Các thành phần lệnh:
- `--module-path` hoặc `-p` cho JVM biết nơi tìm các module JAR.
- Linux/macOS phân tách entries trên path bằng `:`, Windows bằng `;`.
- `--module` hoặc `-m` chọn **module main** và có thể chỉ định `/fully.qualified.MainClass`.
- `dev.training.catalog.cli/dev.training.catalog.cli.Main` gồm tên module trước dấu `/` và main class sau dấu `/`.
- VM giải quyết `dev.training.catalog.cli` và dependency `requires dev.training.catalog.core` từ module path trước khi thực thi.

Trong lab, không cần `--class-path` cho hai JAR này vì cả hai có explicit module descriptor. Đừng dùng `java -jar catalog-cli/target/catalog-cli-1.0.0.jar` rồi kết luận JPMS lỗi: JAR mặc định có thể thiếu manifest `Main-Class` và không tự chứa JAR Core.

### 7.1. Tại sao runtime cần cả hai JAR?

Maven đã giúp compile project và tạo hai artifacts, nhưng **Maven JAR Plugin mặc định không gộp dependencies thành một fat JAR**. Nếu deploy chỉ CLI JAR mà không cấp Core JAR trên module path, JVM không thể thỏa `requires dev.training.catalog.core` và khởi động modular app sẽ thất bại.

Một cách đóng gói phân phối nghiêm túc cần cấu hình launcher, module path, image/container hoặc `jlink` theo nhu cầu. `mvn package` không có nghĩa tạo sẵn một JVM runtime image đủ mọi module.

### 7.2. Tại sao classpath truyền thống không thể thay thế tất cả?

Trong một ứng dụng có `module-info.class`, chạy trên classpath có thể khiến code được xử lý theo unnamed-module classpath semantics thay vì named-module semantics mong muốn. Nếu mục tiêu là **kiểm chứng JPMS**, phải chạy trên module path như ví dụ.

Classpath có thể được dùng để hỗ trợ migration từng phần, nhưng không nên kết luận ứng dụng đã kiểm tra được `requires/exports/opens` chỉ vì `java -cp` chạy được.

## 8. Kiểm tra JAR có module-info.class hay chưa

Dùng công cụ JDK `jar`.

Đứng tại `jpms-lab`:

```bash
jar --list --file catalog-core/target/catalog-core-1.0.0.jar
jar --list --file catalog-cli/target/catalog-cli-1.0.0.jar
```

Trong danh sách entries của mỗi JAR, tìm:

```text
module-info.class
```

Với Core JAR, bạn cũng phải thấy `dev/training/catalog/api/Greeting.class`; với CLI JAR có `dev/training/catalog/cli/Main.class`. Thứ tự và các entries manifest có thể khác theo plugin/JDK.

### 8.1. Mô tả module được đóng gói

Dùng:

```bash
jar --describe-module --file catalog-core/target/catalog-core-1.0.0.jar
jar --describe-module --file catalog-cli/target/catalog-cli-1.0.0.jar
```

Đầu ra sẽ thể hiện thông tin module thật, như:
- Core: tên `dev.training.catalog.core` và export `dev.training.catalog.api`.
- CLI: tên `dev.training.catalog.cli` và requires `dev.training.catalog.core`.

Không giả định toàn bộ text/order của `jar --describe-module` giống nhau ở mọi JDK. Nếu một JAR không có `module-info.class`, `jar --describe-module` có thể mô tả **derived automatic module** thay vì explicit module; hãy đọc dấu hiệu đó cẩn thận.

### 8.2. Dùng Java launcher xem modules

**Linux/macOS:**

```bash
java --module-path "catalog-core/target/catalog-core-1.0.0.jar:catalog-cli/target/catalog-cli-1.0.0.jar" --describe-module dev.training.catalog.core
```

**Windows PowerShell:**

```powershell
java --module-path "catalog-core\target\catalog-core-1.0.0.jar;catalog-cli\target\catalog-cli-1.0.0.jar" --describe-module dev.training.catalog.core
```

Lệnh mô tả có thể giúp xác nhận module descriptor thực tế đã được JVM nhìn thấy. Nếu không thể tìm module, kiểm tra đường dẫn JAR, tên module, quá trình package và có descriptor thật trong JAR hay không.

**Mẹo chẩn đoán:** có thể dùng `java --validate-modules` với module path phù hợp để phát hiện một số vấn đề module path trước khi khởi chạy. Nhưng không coi nó là kiểm thử đầy đủ tính tương thích hoặc quyền reflective access của framework.

## 9. Thử lỗi có kiểm soát: thiếu requires

Sau khi lab chạy đúng, hãy **thử trên một bản sao để học**, không sửa mất source đang sử dụng nếu cần build ổn định.

Trong `catalog-cli/src/main/java/module-info.java`, thay nội dung bằng:

```java
module dev.training.catalog.cli {
}
```

Sau đó chạy:

```bash
mvn -B -ntp clean compile
```

Vì `Main.java` có:

```java
import dev.training.catalog.api.Greeting;
```

mà module CLI không `requires dev.training.catalog.core`, `javac` có thể báo lỗi kiểu “package ... is not visible” hoặc “module ... does not read ...”. **Nội dung lỗi chính xác phụ thuộc compiler và phiên bản JDK**; trọng tâm là **thiếu readability** chứ không phải thiếu Maven dependency.

Khôi phục:

```java
module dev.training.catalog.cli {
    requires dev.training.catalog.core;
}
```

Nếu bỏ Maven `<dependency>` trong POM nhưng giữ `requires`, lỗi có thể thành “module not found: dev.training.catalog.core” vì Maven không cung cấp artifact Core cho compiler. Hai lỗi thể hiện **hai tầng cấu hình khác nhau**.

## 10. Thử lỗi có kiểm soát: package không được export

Trong `catalog-core/src/main/java/module-info.java`, đổi thành:

```java
module dev.training.catalog.core {
}
```

Trong khi CLI vẫn:

```java
module dev.training.catalog.cli {
    requires dev.training.catalog.core;
}
```

`Greeting` là `public` nhưng package `dev.training.catalog.api` **không được xuất**. Build có thể báo lỗi visibility tương tự “package dev.training.catalog.api is not visible (module dev.training.catalog.core does not export it)”.

Khôi phục:

```java
module dev.training.catalog.core {
    exports dev.training.catalog.api;
}
```

**Bài học:** public class không đủ nếu package không được export; `requires` không tự export package của module khác.

### 10.1. Có nên dùng `--add-exports` để chữa tạm?

Tùy chọn `--add-exports module/package=target` có thể tạo qualified export bổ sung khi chạy/compile theo quy tắc javac/JVM. Đây là **công cụ tương thích hoặc migration**, không phải lời khuyên mặc định để xuyên qua encapsulation.

Trong code do nhóm sở hữu, nên sửa module descriptor của module nguồn hoặc thiết kế public API phù hợp. Nếu framework/bên thứ ba không thể sửa ngay, ghi rõ lý do và phạm vi của flag rồi đánh giá lại khi nâng phiên bản thư viện.

## 11. `module-info.java` và `pom.xml` có phải đồng bộ từng dòng không?

Không có quy tắc “mỗi Maven dependency nhất thiết phải có đúng một `requires`” trong mọi trường hợp. Cần hiểu mục đích của chúng:

| Tình huống | POM Maven | module-info.java |
| --- | --- | --- |
| CLI compile dùng public API Core | Khai báo dependency `catalog-core`. | `requires dev.training.catalog.core;`. |
| Dùng `java.logging` của JDK | Thường không có Maven dependency riêng cho JDK module. | `requires java.logging;`. |
| Dependency chỉ dùng trong unit tests | `<scope>test</scope>`. | Test module/JPMS testing strategy quyết định cách đọc module. |
| Dependency ở runtime nhưng không trực tiếp import API | Maven scope `runtime` hoặc cơ chế packaging thích hợp. | Tùy mô hình JPMS/service; có thể cần service binding. |
| Library đóng vai trò API facade | Có thể dùng Maven dependency transitive. | `requires transitive api.module;` nếu contract đọc module API cần được lan truyền. |
| Dependency compile-only theo thiết kế | Scope Maven phù hợp với packaging. | `requires static optional.module;` khi đúng ý nghĩa JPMS, không phải ánh xạ tự động 1:1. |

### 11.1. Tại sao module name và Maven coordinates có thể khác?

JPMS module name có thể được nhà phát hành định nghĩa trong `module-info.class`. Maven chỉ quản lý tọa độ artifact và tải đúng JAR. Một artifact có:
- `groupId=org.example`
- `artifactId=service-api`
- `version=2.1.0`
nhưng JPMS module name `org.example.service`.

Không viết `requires org.example.service.api;` chỉ vì nhìn artifactId; hãy kiểm tra `jar --describe-module --file ...` hoặc tài liệu chính thức của JAR.

### 11.2. Tại sao dependency:tree không thay thế JPMS inspection?

`mvn dependency:tree` hiển thị **đồ thị Maven dependencies** và version/scope. Nó không trực tiếp khẳng định module name, `exports`, `opens` hay việc JVM đọc modules theo `requires`. Khi gặp JPMS errors, dùng cả:
- `mvn dependency:tree` để biết artifact thực được giải quyết.
- `jar --describe-module` để xem descriptor.
- `module-info.java` để hiểu API boundary.
- `java --module-path ... --module ...` để kiểm chứng runtime.

## 12. Tích hợp thư viện chưa có module-info.java

Nhiều JAR cũ được phát hành trước Java 9. Khi đặt lên module path, JPMS có thể xử lý chúng như **automatic modules**. Automatic module được đặt tên bằng:
1. Giá trị `Automatic-Module-Name` trong manifest nếu có; hoặc
2. Tên suy ra từ filename JAR theo quy tắc Java, có thể không ổn định khi đổi tên/version/package artifact.

Vì vậy **không đoán module name từ Maven GAV**. Dùng công cụ:

```bash
jar --describe-module --file path/to/legacy-library.jar
```

Đường dẫn là chỗ thay bằng JAR thật. Nếu output có dấu hiệu “automatic”, module này không có descriptor explicit trong bytecode. Module name phụ thuộc manifest hoặc cách Java suy ra, nên dùng thư viện được maintainer cung cấp tên module ổn định khi có thể.

### 12.1. Hạn chế khi dùng automatic modules

Automatic module giúp migration nhưng có các rủi ro:
- Package export/readability có tính permissive hơn explicit modules.
- Tên module suy ra có thể đổi khi thư viện được phát hành bản modular chính thức.
- Hai JAR cùng package hoặc cùng module name có thể gây xung đột trong module path.
- Dependency của thư viện cũ có thể cần cấu hình riêng khi kết hợp named modules và classpath.

Đặc biệt, **named module không thể dùng một `requires` bình thường để đọc “unnamed module”** chứa những class chỉ ở classpath. Đặt một JAR trên classpath rồi thêm `requires artifact.name;` không đủ. Khi cần kết hợp trong migration, hãy kiểm tra cách xây module path/automatic modules và những flags mở rộng thay vì coi classpath/module path như một danh sách hoán đổi không cần phân biệt.

### 12.2. Không thêm Automatic-Module-Name nếu đã có explicit module-info

Khi JAR đã có `module-info.class` hợp lệ, tên explicit từ descriptor là nguồn xác định. Manifest `Automatic-Module-Name` chủ yếu giúp đặt tên ổn định cho **non-modular JAR** khi nó được đưa lên module path.

## 13. Vấn đề split packages và trùng module names

**Split package** xuất hiện khi cùng một package có class ở nhiều modules. Với JPMS named modules, tình huống này có thể gây lỗi compile hoặc module resolution do readability/visibility constraints.

Ví dụ nguy hiểm:

```text
module alpha.jar:
    dev.training.shared.Config

module beta.jar:
    dev.training.shared.Helper
```

Cả hai cùng package `dev.training.shared`, nhưng khác JPMS modules. Các lỗi có thể nêu package được đọc từ nhiều module hoặc module path chứa xung đột. **Không mặc định Maven dependency:tree sẽ bắt lỗi này**, vì đó là kiểm tra dựa trên module/package layout, không phải chỉ GAV.

Hướng xử lý:
- Tách package thành namespace thuộc đúng module.
- Loại JAR trùng hoặc bỏ bản không tương thích.
- Không tự gộp JAR và hy vọng JPMS cho qua.
- Tránh classloader hacks hoặc `--patch-module` nếu chưa hiểu rủi ro.
- Xem dependency tree để phát hiện bản thừa và xem contents/descriptor của các JAR liên quan.

**Tên module trùng** cũng là vấn đề: hai JAR khác nhau có thể tuyên bố cùng một JPMS module name. Maven coordinates khác nhau không bảo đảm module names khác nhau.

## 14. `requires static` không đồng nghĩa Maven `provided` hoặc `optional`

Ba cơ chế diễn tả những chuyện khác nhau:
- `requires static other.module;`: JPMS dependency cần để compile, optional khi resolve runtime.
- Maven `<scope>provided</scope>`: dependency có trong compile/test context nhưng runtime kỳ vọng môi trường cung cấp.
- Maven `<optional>true</optional>`: Maven transitive dependency không tự được truyền đến các project consumers.

Chúng có thể xuất hiện cùng nhau trong một hệ thống, nhưng **không có ánh xạ tự động 1:1**. Nếu code thực sự gọi class của module static dependency lúc chạy mà module không tồn tại, chương trình vẫn có thể gặp lỗi nạp class hoặc không thực thi được chức năng đó. Dùng `requires static` có chủ đích cho integration optional, không dùng để “giấu” một dependency bắt buộc.

## 15. `requires transitive`: thiết kế API facade

Giả sử một module thư viện `dev.training.catalog.facade` export API mà signature có kiểu từ module `dev.training.catalog.core`. Nếu người tiêu thụ facade cần sử dụng public types của Core trong contract, facade có thể khai báo:

```java
module dev.training.catalog.facade {
    requires transitive dev.training.catalog.core;
    exports dev.training.catalog.facade.api;
}
```

Đây là đoạn module-info minh họa, không thuộc hai module của lab cơ bản. Cần có module facade và package `dev.training.catalog.facade.api` tương ứng mới compile được.

Khi client `requires dev.training.catalog.facade;`, quy tắc transitive readability làm client có thể đọc module Core trong phạm vi JPMS. **Maven vẫn cần có artifact tương ứng trên module path**, thông qua direct/transitive Maven dependencies và cấu hình project phù hợp.

Không lạm dụng `requires transitive` cho mọi dependency nội bộ: nó mở rộng bề mặt API module mà clients có thể đọc và tăng coupling. Chỉ dùng khi contract thực sự đòi hỏi.

## 16. `opens` và frameworks dùng reflection

Một số frameworks JSON, DI/ORM hoặc test runner cần truy cập constructor/fields không public. Với JPMS, một package chỉ được `exports` chưa chắc cho phép **deep reflection**.

Ví dụ có module `dev.training.catalog.core` và package `dev.training.catalog.model` cần cho framework giả định `dev.training.serialization`:

```java
module dev.training.catalog.core {
    exports dev.training.catalog.api;
    opens dev.training.catalog.model to dev.training.serialization;
}
```

Đây là **ví dụ cấu hình giả định**: nếu thêm vào lab, phải tạo package `model`, có module framework thật và điều chỉnh dependencies phù hợp. Không chép nguyên đoạn rồi khẳng định compile được với source lab ban đầu.

Các lỗi runtime có thể có `InaccessibleObjectException` khi framework thử setAccessible trên member không được mở. Hướng đúng là:
1. Xác định package và module đích từ stack trace.
2. Kiểm tra tài liệu của framework.
3. Nếu sở hữu module nguồn, cân nhắc `opens p to framework.module;`.
4. Nếu không thể sửa nguồn, cân nhắc tạm `--add-opens source.module/package=target.module` với lý do và phạm vi rõ ràng.
5. Giữ nguyên tắc cấp quyền tối thiểu; không mở toàn bộ module chỉ để dập một log.

## 17. Kiểm thử dự án JPMS bằng Maven

JPMS có thể ảnh hưởng **unit tests** vì test code thường muốn truy cập classes không được export hoặc dùng reflection/framework test.

Maven Surefire Plugin có hướng dẫn *Java Modularity (JPMS) in Tests* và xử lý module path theo cấu hình/phiên bản plugin, bao gồm những tình huống phải patch test classes vào module chính hoặc sử dụng test module riêng. Không nên tự suy ra behavior của Surefire chỉ từ việc main source có `module-info.java`.

Trong dự án thật:
- Ghim version Maven Surefire Plugin đã kiểm thử, ví dụ 3.5.3 khi môi trường tổ chức chấp nhận.
- Nếu dùng JUnit 5, khai báo dependency đúng version và kiểm tra hệ sinh thái JPMS của test engine/provider.
- Xác định test code thuộc **test module riêng**, được patch vào module main hay chạy trên classpath.
- Không thêm `opens`/`--add-opens` vô điều kiện chỉ để test qua; mở package thật sự cần tới đúng framework.
- Chạy `mvn clean verify` trong môi trường có JDK/Maven nhất quán và kiểm tra reports.

**Lab ở mục 5–8 không khai báo test framework**, nên không có các tests riêng. `mvn clean package` ở đó dùng để xác minh biên dịch/đóng gói và khởi chạy, không phải minh chứng đã kiểm thử JPMS với JUnit.

### 17.1. Phân biệt testCompile và runtime

Có thể gặp tình huống:
- `mvn compile` thành công vì main modules/exports đúng.
- `mvn test-compile` thất bại vì test source không nhìn thấy package cần kiểm thử.
- `mvn test` thất bại khi framework sử dụng reflection vào package không `opens`.
- `java --module ...` vẫn chạy đúng với modules ứng dụng.

Những lỗi này xảy ra ở **những classpath/module path và requirements khác nhau**. Đừng dùng `mvn -DskipTests package` làm “giải pháp” cho JPMS. Nếu phải bỏ tests tạm thời, ghi nhận nguyên nhân và kiểm tra lại trước khi phát hành.

## 18. Cấu hình nâng cao: compilerArgs, module path và toolchains

Trong lab, cấu hình chuẩn chỉ cần `maven.compiler.release=17` và plugin version hỗ trợ. Maven Compiler Plugin xử lý module path theo metadata nguồn/module.

Đôi khi hệ thống lớn cần thêm compiler arguments:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <release>17</release>
        <compilerArgs>
            <arg>-Xlint:all</arg>
        </compilerArgs>
    </configuration>
</plugin>
```

Đây là **đoạn trong `<build><plugins>`**; không phải POM hoàn chỉnh. `-Xlint:all` phục vụ chẩn đoán compiler warnings. Không cần thêm `--module-path` thủ công nếu Maven đang quản lý dependencies/modulepath đúng. Tự ghép path cục bộ bằng string trong POM có thể làm mất portability và gây lệch so với Maven Resolver.

### 18.1. Compiler Plugin với Maven 3 và Maven 4

Phiên bản Maven Compiler Plugin 4.x có những cơ chế project type/dependency mới khi sử dụng Maven 4. Tài liệu của 4.x có hướng dẫn JPMS riêng, nhưng **không nên trộn cấu hình 4.x vào lab 3.14.1**. Nếu nâng Maven/Compiler Plugin, kiểm tra migration guide và test thực tế, thay vì chỉ thay version trong POM.

### 18.2. Biên dịch Java 17 đòi hỏi compiler phù hợp

Cấu hình `<release>17</release>` không tự cài JDK 17. Với Maven Toolchains Plugin, có thể chọn compiler JDK đã cài ngoài JVM chạy Maven tùy plugin/toolchain setup; việc này cần cấu hình toolchains riêng. Nếu không dùng toolchain, hãy đảm bảo `mvn -version` cho biết Maven đang chạy bằng JDK đủ mới.

Lỗi “release version 17 not supported” thường chỉ ra compiler hiện tại không hỗ trợ `--release 17`. Sửa JDK/toolchain, **không bỏ module-info.java như một mẹo vòng tránh**.

## 19. Cách xác minh module graph và Maven dependency graph

### Maven dependency tree

Sau build đầy đủ, từ root:

```bash
mvn -pl :catalog-cli dependency:tree
```

Đầu ra minh họa liên quan đến dependency:

```text
dev.training.jpms:catalog-cli:jar:1.0.0
\- dev.training.jpms:catalog-core:jar:1.0.0:compile
```

Đây là **dạng rút gọn**, không phải toàn bộ Maven log. Nếu goal được chạy ở một invocation với Maven local repository không có Core artifact và cần resolve ngoài reactor, có thể cần chạy `mvn install` từ root hoặc dùng cách invocation có đủ upstream reactor context.

### JPMS module descriptor

```bash
jar --describe-module --file catalog-core/target/catalog-core-1.0.0.jar
jar --describe-module --file catalog-cli/target/catalog-cli-1.0.0.jar
```

Lệnh này cho thấy **module name, requires và exports**, không phải version của Maven dependencies. Kết hợp hai kết quả mới thấy đầy đủ cả artifact resolution và module readability.

### Chạy ở modular mode

```bash
java -p "catalog-core/target/catalog-core-1.0.0.jar:catalog-cli/target/catalog-cli-1.0.0.jar" -m dev.training.catalog.cli/dev.training.catalog.cli.Main
```

Lệnh này theo cú pháp Linux/macOS và là dạng viết gọn của `--module-path`, `--module` ở mục 7. Nếu chạy từ Windows PowerShell, phải dùng dấu `;` thay vì `:` trên module path.

## 20. Lỗi JPMS điển hình và cách sửa

| Triệu chứng | Gốc nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `module not found: dev.training.catalog.core` | Maven/Javac không thấy artifact module Core trên module path hoặc tên module bị sai. | Kiểm tra POM dependency, đúng module-info, reactor, local repository và compiler configuration. |
| `package ... is not visible` | CLI thiếu `requires` hoặc package chưa được export. | Kiểm tra cả `requires` của consumer và `exports` của provider. |
| `package ... is declared in module ... which does not export it` | Class public nhưng package không phải API exported. | Export package công khai có chủ đích hoặc sửa code dùng đúng public API. |
| `UnsupportedClassVersionError` | JDK runtime/Maven JVM thấp hơn bytecode được build. | Đối chiếu Java/JDK, giữ release đúng requirement. |
| `release version 17 not supported` | Compiler JDK không hỗ trợ Java 17. | Dùng JDK 17+ hoặc toolchains phù hợp. |
| `module-info.class` không có trong JAR | File nguồn đặt sai, compile không chạy hoặc packaging khác. | Kiểm tra `src/main/java/module-info.java`, compiler, jar contents. |
| Runtime không resolve Core | Chỉ deploy CLI JAR, thiếu Core JAR trên module path. | Cấp tất cả required modules trong launcher/distribution. |
| Two modules export the same package | Split package/trùng package qua các named modules đọc được. | Tách package, loại JAR trùng hoặc chọn dependencies tương thích. |
| `InaccessibleObjectException` | Framework dùng deep reflection mà package chưa mở. | `opens` đúng package/module hoặc flag migration có kiểm soát. |
| Maven build thành công nhưng `java -jar` lỗi | Launcher không có manifest Main-Class hoặc dependencies. | Chạy `java -p ... -m ...`, hoặc cấu hình launcher/package phù hợp. |
| Code compile trong IDE nhưng Maven fail | JDK/module path/annotation processing khác. | Reimport Maven POM, kiểm tra JDK, module-info và flags. |
| Test compile hoặc reflection fail | JPMS testing khác main compilation. | Xem Surefire JPMS mode/test descriptor và mở quyền tối thiểu. |

### 20.1. Phân biệt ba loại “không tìm thấy”

**Không tìm thấy Maven artifact:** POM báo `Could not resolve dependencies` — vấn đề nằm ở Maven GAV/repository/reactor, trước khi compiler có đủ JAR.

**Không tìm thấy JPMS module:** compiler/JVM báo `module not found` — artifact có thể đã có, nhưng module name hoặc module path không khớp.

**Không được truy cập package:** compiler báo `package is not visible` hoặc runtime reflection báo access error — JAR/module có thể tồn tại nhưng readability/exports/opens chưa cho phép.

Ba trường hợp này có cách xử lý khác nhau. Đừng tự thêm mọi JAR vào classpath mà không xác định tầng bị lỗi.

## 21. Quy trình migration một ứng dụng Maven cũ sang JPMS

Một dự án classpath truyền thống có thể từng được build mà không có `module-info.java`. Để modularize:

1. **Kiểm kê dependency graph** bằng Maven và biết những JAR nào còn non-modular.
2. **Chọn tên module ổn định** theo namespace tổ chức; kiểm tra khả năng xung đột với modules có sẵn.
3. **Giữ package names rõ ràng** và loại split packages giữa các dự án module.
4. **Tạo `module-info.java` trong `src/main/java`** của module định chuyển, chỉ khai báo `requires` thực sự cần.
5. **Chỉ export public API packages**, không export toàn bộ packages nội bộ.
6. **Xử lý framework reflection** bằng `opens` đúng phạm vi khi có nhu cầu.
7. **Pin JDK và Maven Compiler Plugin** tương thích; dùng `--release` thay vì chỉ cấu hình source/target khi có thể.
8. **Kiểm tra automatic module names** bằng `jar --describe-module` và metadata manifest; tránh dựa vào tên suy đoán khó ổn định.
9. **Build reactor và chạy modular mode**, không chỉ build ở IDE/classpath.
10. **Cấu hình lại test runtime** (Surefire/JPMS) khi tests có đặc thù access.
11. **Đóng gói distribution hợp lệ**, có launcher/module path/runtime dependencies rõ ràng.
12. **Chạy integration tests trên CI** ở JDK mục tiêu và ghi nhận module access flags tạm để có kế hoạch loại bỏ.

Không phải dự án nào cũng cần modularize mọi dependency ngay. JPMS hữu ích khi muốn encapsulation, modular runtime hoặc API boundary rõ ràng, nhưng migration có thể gặp khó khăn với thư viện cũ và frameworks reflection. Đánh giá lợi ích so với chi phí bảo trì, không thêm module descriptor chỉ để “cho hiện đại”.

## 22. Câu hỏi ôn tập và đáp án

**Câu 1.** `module-info.java` của Core nên nằm ở đâu trong Maven project?

**Đáp án:** `catalog-core/src/main/java/module-info.java`, ngay source root. Nó được compile thành `module-info.class`.

**Câu 2.** Maven `<artifactId>catalog-core</artifactId>` có nghĩa JPMS module tên `catalog-core` không?

**Đáp án:** Không. Module name của ví dụ là `dev.training.catalog.core`, lấy từ `module-info.java`.

**Câu 3.** CLI có Maven dependency đến Core nhưng không có `requires dev.training.catalog.core;`. Import class ở Core có chắc compile được trong JPMS không?

**Đáp án:** Không. Maven tìm được artifact chưa đủ; JPMS còn cần readability tới module Core.

**Câu 4.** Core có `exports dev.training.catalog.api;` nhưng CLI không có Maven dependency. Chỉ thêm `requires` là đủ không?

**Đáp án:** Không nếu Maven không cung cấp artifact Core trên module path; phải giải quyết dependency artifact đúng.

**Câu 5.** Vì sao Java public class trong package `dev.training.catalog.internal` vẫn có thể không dùng được từ CLI?

**Đáp án:** Package nội bộ không được `exports` trong module descriptor của Core, nên module khác không được truy cập API đó qua JPMS thông thường.

**Câu 6.** Cách Maven chọn JDK target trong lab là gì?

**Đáp án:** Parent POM đặt `<maven.compiler.release>17</maven.compiler.release>` và quản lý Maven Compiler Plugin 3.14.1.

**Câu 7.** Lệnh nào build cả hai Maven projects theo quan hệ dependency từ root?

**Đáp án:** `mvn -B -ntp clean package` khi đứng trong `jpms-lab`.

**Câu 8.** Vì sao chạy `java --module-path ... --module ...` mà không dùng `java -jar`?

**Đáp án:** Đó là cách launch named module theo JPMS, resolve `requires` từ module path. JAR mặc định không nhất thiết có Main-Class và không đóng gói mọi dependency.

**Câu 9.** Lệnh JDK nào xem metadata module của một JAR?

**Đáp án:** `jar --describe-module --file path/to/artifact.jar`.

**Câu 10.** `requires transitive api.module;` có thay thế Maven `<dependencies>` không?

**Đáp án:** Không. Nó điều khiển JPMS readability, không tải artifact qua Maven repository.

**Câu 11.** `opens` có khiến một package được export để compile import không?

**Đáp án:** Không. `opens` chủ yếu cấp quyền reflection runtime; `exports` phục vụ accessibility public API.

**Câu 12.** `requires static` và Maven `optional` có hoàn toàn giống nhau không?

**Đáp án:** Không. Chúng thuộc JPMS resolution và Maven dependency transitivity tương ứng, không có mapping một-một.

**Câu 13.** Hai JAR khác groupId nhưng chứa cùng JPMS module name có thể gây vấn đề không?

**Đáp án:** Có. Maven GAV độc lập với module name; module path có thể gặp trùng tên modules.

**Câu 14.** Maven package thành công có bảo đảm Surefire tests dùng reflection sẽ chạy không?

**Đáp án:** Không. JPMS test module path và framework reflective access phải được cấu hình/kiểm chứng riêng.

**Câu 15.** Vì sao `-pl :catalog-cli -am` có ích trong Maven reactor?

**Đáp án:** Nó chọn CLI và các upstream Maven projects cần thiết, giúp Core được build cùng invocation thay vì đòi Core đã được install từ trước.

## 23. Tài liệu tham khảo chính thức

- [Oracle Java SE 17 – Java Language Specification, Chapter 7 (Modules)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): module declarations; `requires`, `exports`, `opens`, `uses` và `provides`; readability.
- [Oracle Java SE 17 – java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--module-path`, `--module`, `--describe-module` và các lựa chọn module runtime.
- [Oracle Java SE 17 – javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `--module-path`, compiler modules và module source layout.
- [Oracle Java SE 17 – jar](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): `--describe-module` và `--list` để xem nội dung/descriptor của JAR.
- [Apache Maven Compiler Plugin 3.14.1 – Usage](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.1/usage.html): compiler goals, lifecycle binding và version plugin.
- [Apache Maven Compiler Plugin – Java 9+ module-info](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/module-info.html): ứng dụng Java 9+ có module-info và trường hợp dual-compatibility Java 8.
- [Apache Maven Compiler Plugin 3.14.0 – compiler:testCompile](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.0/testCompile-mojo.html): `useModulePath` (mặc định true khi module-info và Java9+).
- [Apache Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): Maven goals/phases và lifecycle bindings theo packaging.
- [Apache Maven – Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): Maven reactor, subprojects và thứ tự dự án.
- [Apache Maven Surefire Plugin – Java Modularity (JPMS) in Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/jpms.html): test modules, test engines và các cấu hình JPMS.
- [OpenJDK – JEP 261: Module System](https://openjdk.org/jeps/261): mục tiêu JPMS và mô hình module path.
