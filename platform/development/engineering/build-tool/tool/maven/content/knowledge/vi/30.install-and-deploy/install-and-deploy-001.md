# install: đưa artifact và POM vào kho cục bộ

## 1. Học xong bài này, bạn làm được gì?

Khi xây dựng một thư viện Java bằng Maven, lệnh `mvn package` thường tạo JAR trong `target/`. Nhưng một project Maven **khác** không tự động biết JAR đó nằm ở đâu. Nếu bạn muốn project thứ hai khai báo thư viện vừa xây bằng Maven dependency coordinates, thư viện cần xuất hiện trong một repository mà Maven Resolver có thể truy cập.

Phase `install` giải quyết nhu cầu phát triển cục bộ:

~~~bash
mvn clean install
~~~

Với project có `<packaging>jar</packaging>`, Maven thông thường biên dịch, kiểm thử, đóng JAR, rồi cài **JAR chính và POM tương ứng** vào **local Maven repository**. Sau đó một project khác có thể dùng cặp coordinates `groupId:artifactId:version` trong `pom.xml` để Maven resolve JAR, không cần chỉ định đường dẫn thủ công tới `target/foo.jar`.

Sau bài này bạn sẽ:

1. Hiểu local repository là gì và vai trò khác nhau của **artifact file** và **POM metadata**.
2. Phân biệt `package`, `verify`, `install` và `deploy` trong default lifecycle.
3. Biết goal `maven-install-plugin:install` được gọi vào thời điểm nào.
4. Dự đoán chính xác đường dẫn artifact/POM trong local repository theo Maven coordinates.
5. Build một thư viện Java 17, dùng `mvn clean install`, rồi **tiêu thụ nó ở một project Java 17 độc lập**.
6. Biết khi nào cần `install:install-file` cho JAR tạo ngoài Maven.
7. Cấu hình local repository bằng Maven settings hoặc `-Dmaven.repo.local`.
8. Hiểu tác động của `-N`, multi-module reactor, classifiers, SNAPSHOT, local cache và CI.
9. Chẩn đoán lỗi artifact not found, sai version, stale JAR, POM thiếu dependencies và repository khác dự kiến.

Các ví dụ dùng **Java 17+**, Maven 3.9.x tương thích và Maven Install Plugin **3.1.4**. Các phiên bản được ghim để học/tái lập hành vi; không khẳng định đây luôn là phiên bản mới nhất.

## 2. Local repository là gì?

Maven dùng hệ thống repositories để tìm POM, artifacts và plugin dependencies. Có ba khái niệm cần phân biệt:

- **Local repository:** kho trên máy (hoặc filesystem/container của runner) mà Maven sử dụng để lưu/cached artifacts đã tải, và artifacts do bạn `install`.
- **Remote repository:** kho Maven có thể truy cập qua mạng hoặc transport được hỗ trợ, ví dụ Maven Central, Nexus hoặc Artifactory.
- **Reactor artifacts:** artifacts từ các module tham gia **cùng một Maven reactor build**; một module có thể dùng artifact của module khác mà không nhất thiết cần install trước.

Theo cấu hình phổ biến, local repository nằm ở:

~~~text
~/.m2/repository
~~~

Trên Unix-like, dấu `~` thường đại diện home directory. Trên Windows, repository mặc định thường nằm dưới:

~~~text
C:\Users\<username>\.m2\repository
~~~

Đây là các **đường dẫn minh họa**. Maven settings hoặc CLI option có thể đổi local repository, nên không thể suy ra đường dẫn thật chỉ từ hệ điều hành.

**Local repository không phải `target/`.** `target/` thuộc một project build cụ thể; local repository là vùng lưu trữ dùng lại giữa nhiều project/invocation.

## 3. Artifact không chỉ là file JAR

Một Maven dependency có các tọa độ nhận diện:

~~~text
groupId : artifactId : version
~~~

Ví dụ:

~~~text
dev.learning.local : message-core : 1.0.0
~~~

Trong trường hợp thông thường:

- `groupId=dev.learning.local`: không gian tên.
- `artifactId=message-core`: tên artifact.
- `version=1.0.0`: phiên bản được phát hành/cài.
- `packaging=jar` ở POM: Maven tạo JAR main artifact.
- `type=jar` nếu khai báo dependency mặc định: biểu thị loại artifact cần resolve.
- `classifier`, khi có, phân biệt artifacts phụ như `sources`, `javadoc` hoặc `tests`.

Khi Maven cài artifact JAR, thông thường có ít nhất hai file có vai trò khác nhau:

~~~text
message-core-1.0.0.jar
message-core-1.0.0.pom
~~~

**JAR** chứa Java classes/resources của thư viện. **POM** chứa Maven project model và thông tin dependency cần thiết để các consumer project biết cách resolve các dependencies bắc cầu theo cơ chế Maven.

Nếu thiếu POM phù hợp, việc resolve một JAR không đồng nghĩa Maven biết đầy đủ các dependencies mà thư viện cần ở runtime.

## 4. Local repository layout theo Maven coordinates

Maven chuyển các dấu chấm trong `groupId` thành thư mục:

~~~text
groupId:    dev.learning.local
artifactId: message-core
version:    1.0.0
packaging:  jar
~~~

Đường dẫn mặc định tương ứng:

~~~text
~/.m2/repository/
└── dev/
    └── learning/
        └── local/
            └── message-core/
                └── 1.0.0/
                    ├── message-core-1.0.0.jar
                    └── message-core-1.0.0.pom
~~~

Đây là những file **chính** bạn cần nhận diện. Maven có thể tạo thêm repository metadata, tracking files và cache markers tùy resolver/version; không giả định directory chỉ có đúng hai files.

Hệ quả:

1. Đổi `groupId` làm thay đổi đường dẫn group.
2. Đổi `artifactId` làm thay đổi artifact directory và filename.
3. Đổi `version` tạo đường dẫn version khác.
4. Hai bản source khác nhau cùng GAV không phải hai artifacts được Maven phân biệt theo source commit; Maven nhìn vào **coordinates**.
5. Nếu file được đặt ở đường dẫn khác cấu trúc repository, Maven không tự coi nó là một dependency có coordinates hợp lệ.

**Không copy JAR bằng tay vào `~/.m2/repository/...`** để thay `install`: thao tác đó dễ để lại POM/metadata không khớp. Maven Install Plugin là cách được hỗ trợ để cài các artifacts.

## 5. install nằm ở đâu trong Maven default lifecycle?

Khi chạy:

~~~bash
mvn install
~~~

Maven chạy các phase cần thiết trước đó của **default lifecycle**, không chỉ mỗi goal `install:install`.

Một sơ đồ các phase quan trọng:

~~~text
validate
   |
compile
   |
test
   |
package
   |
verify
   |
install
   |
deploy
~~~

Trong thực tế còn nhiều phase trung gian như `process-resources`, `test-compile`, `pre-integration-test`, `integration-test` và `post-integration-test`. Sơ đồ trên được rút gọn để thấy thứ tự.

| Lệnh | Kết quả chính |
| --- | --- |
| `mvn compile` | Biên dịch source vào output directory |
| `mvn test` | Chạy các kiểm thử đơn vị được cấu hình |
| `mvn package` | Tạo JAR/WAR hoặc artifact theo packaging |
| `mvn verify` | Chạy các kiểm tra tới phase verify |
| `mvn install` | Chạy các phase trước, rồi cài artifact/POM vào local repository |
| `mvn deploy` | Chạy lifecycle tới deploy và có bước đưa artifact/POM lên **remote repository** nếu được cấu hình |

**`install` không phải `deploy`**. Install là bước local; deploy là bước chia sẻ lên remote repository. Chạy `mvn install` không tự upload JAR cho đồng đội hoặc Maven Central.

### Vì sao nên dùng clean install?

~~~bash
mvn -B -ntp clean install
~~~

`clean` thuộc clean lifecycle, thường xóa output trong `target/` trước khi build. `install` thuộc default lifecycle, làm các bước build/testing/packaging rồi cài vào repository. Ghép hai lifecycle giúp giảm nguy cơ cài một JAR được tạo từ classes/resources cũ.

**Không phải mỗi lần cài đều buộc phải clean**; nhưng để học, kiểm tra release candidate hoặc điều tra lỗi stale output, `clean install` là lựa chọn dễ kiểm soát.

## 6. Maven Install Plugin: goal install:install

Maven Install Plugin xử lý bước đưa project artifacts vào local repository.

Full goal có dạng:

~~~text
org.apache.maven.plugins:maven-install-plugin:3.1.4:install
~~~

Với packaging `jar`, default lifecycle thông thường bind goal này vào phase `install`. Bạn chỉ cần:

~~~bash
mvn install
~~~

nếu project/lifecycle đã cấu hình đúng.

Theo tài liệu chính thức, `install:install` cài:

- **Main artifact** của project, như JAR/WAR/EAR, khi packaging có artifact tương ứng.
- **POM** của project.
- Các **attached artifacts** nếu plugin khác đã tạo/attach trong lifecycle, ví dụ source JAR hoặc javadoc JAR.

Không nên mặc định mọi dependency JAR của project sẽ được **copy** vào cùng directory của artifact bạn vừa install. Dependencies đã được resolve vẫn nằm ở **tọa độ riêng** của chúng trong repository.

### Một số parameters quan trọng

- `maven.install.skip`: nếu true, bỏ qua installation cho project tương ứng.
- `installAtEnd`: có thể hoãn installation đến cuối multi-module build; nếu build fail, tránh partial installs theo cơ chế hỗ trợ của plugin. Tính năng được tài liệu đánh dấu là thử nghiệm.
- `allowIncompleteProjects`: cho phép một số dạng project không có main artifact; mặc định false trong Plugin 3.1.4, nên cần thiết kế packaging đúng thay vì bật bừa.

**Cẩn thận:** Trong Maven Install Plugin 3.x, option cũ `createChecksum` không còn là cách được hỗ trợ để yêu cầu plugin tạo checksums. Nếu cần kiểm tra integrity, dùng công cụ checksum hoặc cơ chế release/provenance chuyên biệt.

## 7. Bài lab: hai project độc lập, không có reactor chung

Để thấy rõ tác dụng của local repository, chúng ta **không tạo root aggregator POM**. Có hai Maven projects độc lập đặt cạnh nhau:

1. `message-core` là thư viện Java 17.
2. `message-cli` là ứng dụng Java 17 phụ thuộc `message-core:1.0.0`.

Nếu build message-cli trước khi library được install và local/remote repositories chưa có artifact ấy, Maven không thể resolve dependency.

Nếu cài message-core rồi build message-cli, Maven sẽ resolve từ local repository mà không cần khai báo systemPath tới file JAR.

Cấu trúc:

~~~text
install-local-lab/
├── message-core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/learning/core/MessageService.java
│       └── test/java/dev/learning/core/MessageServiceTest.java
└── message-cli/
    ├── pom.xml
    └── src/
        ├── main/java/dev/learning/cli/Main.java
        └── test/java/dev/learning/cli/MainTest.java
~~~

**Điểm kiểm chứng:** hai POM **không có `<parent>` trỏ vào nhau**, không có `<modules>` và không build cùng reactor. Sau khi library `install`, consumer dùng chính Maven repository resolution.

### 7.1. Thư viện: message-core/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.local</groupId>
    <artifactId>message-core</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Những điểm cần hiểu:

- `groupId:artifactId:version` tạo coordinates `dev.learning.local:message-core:1.0.0`.
- `packaging=jar` khiến phase package tạo JAR.
- Compiler Plugin dùng Java 17.
- Surefire chạy test JUnit Jupiter; test dependency không tự nằm trong main JAR.
- Install Plugin được ghim version cho lab; bạn không phải gọi trực tiếp `install:install` khi chạy `mvn install`.
- POM này không khai báo external runtime dependencies. Consumer chỉ cần message-core JAR và JDK để chạy code ví dụ.

### 7.2. message-core/src/main/java/dev/learning/core/MessageService.java

~~~java
package dev.learning.core;

public final class MessageService {

    private MessageService() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return "Hello, " + name.strip() + " from message-core";
    }
}
~~~

Code sử dụng `String.isBlank()` và `String.strip()`, đều có trong Java 17. Nó không phụ thuộc thư viện runtime bên ngoài.

### 7.3. message-core/src/test/java/dev/learning/core/MessageServiceTest.java

~~~java
package dev.learning.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class MessageServiceTest {

    @Test
    void greetsName() {
        assertEquals(
                "Hello, Maven from message-core",
                MessageService.greet(" Maven "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MessageService.greet("  "));
    }
}
~~~

Hai tests xác nhận cả output chuẩn và cách xử lý input trống. Đừng đưa test class này vào thư viện main JAR để tiêu thụ như API chính.

## 8. Project tiêu thụ: message-cli

Consumer là một project **độc lập**. Nó không biết source tree của message-core, chỉ biết dependency coordinates trong POM.

### 8.1. message-cli/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.local</groupId>
    <artifactId>message-cli</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.learning.local</groupId>
            <artifactId>message-core</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven cần tìm `dev.learning.local:message-core:jar:1.0.0` trong local repository hoặc repository được cấu hình. Khi library vừa được install, local repository có artifact để Maven dùng.

**Không dùng `<scope>system</scope>` và `<systemPath>...target/message-core.jar</systemPath>`.** Đó là cách gắn dependency vào đường dẫn máy cục bộ, không phù hợp với Maven repository-based dependency management và làm project khó tái lập.

### 8.2. message-cli/src/main/java/dev/learning/cli/Main.java

~~~java
package dev.learning.cli;

import dev.learning.core.MessageService;

public final class Main {

    private Main() {
    }

    public static String message() {
        return MessageService.greet("Maven");
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Class này import `MessageService` từ dependency JAR. Nếu dependency thiếu, compiler không tìm được package; nếu có đúng JAR và Java classpath, class chạy được.

### 8.3. message-cli/src/test/java/dev/learning/cli/MainTest.java

~~~java
package dev.learning.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class MainTest {

    @Test
    void usesInstalledLibrary() {
        assertEquals(
                "Hello, Maven from message-core",
                Main.message());
    }
}
~~~

Test của consumer sử dụng class từ thư viện, nên việc test PASS sau cài đặt là một minh chứng hữu ích rằng dependency đã được Maven resolve và đưa vào test classpath.

## 9. Chạy lab theo đúng thứ tự

Từ thư mục cha `install-local-lab`, kiểm tra toolchain:

~~~bash
mvn -version
java -version
~~~

### Bước 1 — Build và install thư viện

~~~bash
mvn -B -ntp -f message-core/pom.xml clean install
~~~

Nếu Maven có quyền ghi local repository, plugins/dependencies resolve được và tests PASS, lệnh kết thúc:

~~~text
BUILD SUCCESS
~~~

Trong log, bạn nên thấy các goals như compiler, surefire, jar và install. Install Plugin có thể in thông điệp với ý nghĩa:

~~~text
Installing .../message-core/pom.xml to .../repository/dev/learning/local/message-core/1.0.0/message-core-1.0.0.pom
Installing .../message-core/target/message-core-1.0.0.jar to .../repository/dev/learning/local/message-core/1.0.0/message-core-1.0.0.jar
~~~

Đây là **dòng log minh họa nội dung**, không phải transcript đã chạy thật; ký hiệu `...` thay cho absolute paths trên máy.

### Bước 2 — Xác nhận hai file chính

Ở local repository mặc định, tìm:

~~~text
~/.m2/repository/dev/learning/local/message-core/1.0.0/message-core-1.0.0.jar
~/.m2/repository/dev/learning/local/message-core/1.0.0/message-core-1.0.0.pom
~~~

Đường dẫn thực tế phải điều chỉnh nếu dùng custom local repository. Các file metadata khác có thể xuất hiện và là bình thường.

Kiểm tra nội dung JAR bằng JDK:

~~~bash
jar tf message-core/target/message-core-1.0.0.jar
~~~

Bạn cần thấy entry:

~~~text
dev/learning/core/MessageService.class
~~~

Main JAR **không nên** có `MessageServiceTest.class`, vì tests nằm ở `target/test-classes`. Và JAR được install thường có nội dung tương ứng artifact đã package, không phải source files.

### Bước 3 — Build consumer

~~~bash
mvn -B -ntp -f message-cli/pom.xml clean verify
~~~

Nếu `message-core:1.0.0` đã cài vào cùng local repository mà consumer sử dụng:

- Maven resolve dependency theo coordinates.
- Compiler của message-cli tìm được `MessageService`.
- `MainTest` PASS.
- Consumer JAR `message-cli/target/message-cli-1.0.0.jar` được tạo.
- Maven có thể báo `BUILD SUCCESS`.

Nếu bước này fail vì artifact not found, kiểm tra tọa độ, đường dẫn local repository và kết quả install của bước 1; đừng chỉ đọc tên JAR trong thư mục `target` của thư viện.

### Bước 4 — Chạy Java qua Maven dependency classpath

~~~bash
mvn -B -ntp -f message-cli/pom.xml org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=dev.learning.cli.Main
~~~

Exec Maven Plugin dùng classpath của project/dependencies để chạy Java main. Dòng do **ứng dụng** in chính xác:

~~~text
Hello, Maven from message-core
~~~

Maven/Exec Plugin có thể in thêm log khác; dòng trên là stdout của `System.out.println` chứ không phải toàn bộ transcript của goal.

**Điểm quan trọng:** consumer không hề chỉ định đường dẫn đến `message-core/target/`. Maven đã resolve thư viện qua repository theo GAV.

## 10. Chạy bằng java -cp để thấy artifact cục bộ

Nếu local repository vẫn ở đường dẫn mặc định và bạn đứng tại `install-local-lab`, có thể dùng Java launcher trực tiếp để chạy consumer:

Linux/macOS:

~~~bash
java -cp "message-cli/target/message-cli-1.0.0.jar:$HOME/.m2/repository/dev/learning/local/message-core/1.0.0/message-core-1.0.0.jar" dev.learning.cli.Main
~~~

Windows PowerShell:

~~~powershell
java -cp "message-cli\target\message-cli-1.0.0.jar;$HOME\.m2\repository\dev\learning\local\message-core\1.0.0\message-core-1.0.0.jar" dev.learning.cli.Main
~~~

Output chính xác:

~~~text
Hello, Maven from message-core
~~~

Phân biệt classpath separator: `:` trên Unix-like, `;` trên Windows.

**Cảnh báo:** Với custom `<localRepository>`, lệnh cần dùng đường dẫn khác. Trong production, không nên viết script deploy phụ thuộc trực tiếp vào home Maven cache của developer; hãy tạo distribution/startup script hoặc executable packaging theo yêu cầu.

### Vì sao không chạy java -jar consumer.jar?

`message-cli` trong lab được đóng thành **plain JAR** và chưa cấu hình `Main-Class`. Ngoài ra, plain JAR **không tự nhúng** dependency `message-core`. Vì vậy:

~~~bash
java -jar message-cli/target/message-cli-1.0.0.jar
~~~

không phải lệnh thực thi hợp lệ theo thiết kế hiện tại. Muốn dùng `java -jar`, cần manifest entry point và một chiến lược cung cấp runtime dependencies (các JAR cạnh nhau cùng manifest Class-Path, launcher script, Maven Shade Plugin hoặc packaging khác).

**Maven install chỉ phục vụ resolution/local reuse, không biến main JAR thành fat JAR.**

## 11. install được chứng minh bằng consumer khác, không phải bằng JAR trong target

Một nhầm lẫn phổ biến là nghĩ:

> “Tôi thấy `target/message-core-1.0.0.jar`, vậy project khác dùng được dependency rồi.”

Điều đó **chưa đủ**.

Maven có thể build JAR thành công ở `package`, nhưng GAV chưa xuất hiện trong local repository. Consumer resolve theo coordinates, không tự scan các thư mục `target` kế bên.

Để chứng minh install:

1. Library có `pom.xml` xác định GAV.
2. `mvn clean install` thành công.
3. Local repository chứa **main artifact và POM** ở đường dẫn GAV.
4. Project **độc lập** có dependency coordinates đúng.
5. Maven consumer resolve, compile và test thành công.
6. Dùng dependency tree hoặc diagnostic log khi cần để biết chính xác dependency đã chọn.

Chỉ có project trong **cùng reactor** là ngoại lệ quan trọng: Maven Reactor có thể đáp ứng dependency từ sibling modules mà **chưa cần install**. Đó là lý do lab cố tình làm hai project độc lập.

## 12. Xem dependency đã được resolve

Chạy từ thư mục cha:

~~~bash
mvn -B -ntp -f message-cli/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dincludes=dev.learning.local
~~~

Trích output dự kiến:

~~~text
dev.learning.local:message-cli:jar:1.0.0
\- dev.learning.local:message-core:jar:1.0.0:compile
~~~

Đây là **đoạn tree rút gọn**; output thực tế có thêm goal/report headers, các dependencies test và plugin version information.

Lệnh này chứng minh Maven nhìn thấy `message-core` trong resolved dependency graph của consumer. Nếu muốn biết file cụ thể được dùng, xem debug output/CLI goal phù hợp với Maven Resolver, hoặc kiểm tra local repository của Maven session.

**Giới hạn:** dependency:tree không chứng minh main JAR được xây từ source commit mới nhất. Nó chỉ phản ánh graph đã resolve theo repository/session hiện hành.

## 13. Mối liên hệ giữa JAR và POM được install

Maven Install Plugin lưu **POM project model** cùng artifact. Khi một consumer khai báo:

~~~xml
<dependency>
    <groupId>dev.learning.local</groupId>
    <artifactId>message-core</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Maven cần artifact metadata để xác định packaging và các dependencies bắc cầu.

Giả sử một library khác khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
~~~

Đây là **đoạn minh họa**, không thuộc POM message-core trong lab. Nếu library này được install với POM phù hợp, consumer sẽ có thông tin để resolve Commons Lang như dependency bắc cầu theo Maven scope/optional/exclusions rules.

Nếu chỉ cung cấp binary JAR mà không có POM thật, consumer có thể thiếu thông tin các thư viện cần thiết. Chạy được một testcase đơn giản không bảo đảm mọi runtime classpath đúng.

### Parent POM có cần có trong repository không?

Khi POM đã install tham chiếu một parent:

~~~xml
<parent>
    <groupId>dev.example</groupId>
    <artifactId>build-parent</artifactId>
    <version>1.0.0</version>
</parent>
~~~

Consumer/Maven Resolver có thể cần parent model để tạo effective dependencies/metadata. Nếu parent POM chưa có trong repository có thể truy cập và `relativePath` local không áp dụng trong môi trường tiêu thụ, dependency resolution có thể lỗi.

**Vì thế:** khi phát hành hoặc install artifact có parent POM riêng, cần bảo đảm **parent POM cũng được resolve được** (install/deploy parent theo quy trình phù hợp). Không chỉ copy child JAR.

## 14. Khi packaging là pom: install cái gì?

Một project aggregator/parent thường có:

~~~xml
<packaging>pom</packaging>
~~~

Project này **không cần tạo main JAR**. Khi chạy:

~~~bash
mvn -N install
~~~

từ một root aggregator POM trong multi-module repo, Maven có thể cài chính **POM artifact** của starting root vào local repository mà không build child modules.

Ví dụ coordinates:

~~~text
dev.example:build-parent:pom:1.0.0
~~~

thì local repository sẽ có:

~~~text
~/.m2/repository/dev/example/build-parent/1.0.0/build-parent-1.0.0.pom
~~~

**Không diễn giải:** `-N install` ở root tự cài mọi child JAR; `-N` là non-recursive.

Với full multi-module build:

~~~bash
mvn clean install
~~~

Maven chạy install phase trên những reactor projects được chọn, theo thứ tự build phù hợp. Khi root/children hợp lệ, root POM và child artifacts có thể cùng được install.

## 15. Maven multi-module: khi nào không cần install trước?

Trong một reactor:

~~~text
multi-project/
├── pom.xml                  (packaging pom)
├── library/
│   └── pom.xml              (jar)
└── app/
    └── pom.xml              (jar, dependency library)
~~~

Nếu root khai báo modules và app khai báo dependency library cùng coordinates/version phù hợp, chạy:

~~~bash
mvn -B -ntp clean verify
~~~

thường đủ để Maven resolve library qua **reactor**, ngay cả khi library chưa được install vào local repository.

Maven sắp thứ tự library trước app. Điều này khác bài lab độc lập ở mục 7, nơi consumer không tham gia cùng reactor với library.

### Vì sao vẫn cần install?

- Khi muốn **project độc lập ngoài reactor** resolve thư viện.
- Khi cần parent POM trong local repository để project khác kế thừa.
- Khi có một tool/build process riêng tiêu thụ Maven coordinates từ repository.
- Khi chuẩn bị artifacts cho những bước tiếp theo nhưng vẫn ở cùng môi trường phát triển.

Trong CI monorepo, `-pl :app -am verify` thường tốt hơn việc install siblings thủ công từng cái để tránh dùng library bản cũ. `install` không thay thế thiết kế reactor dependency graph.

## 16. installAtEnd: tránh partial local installs trong reactor

Maven Install Plugin 3.1.4 có tham số `installAtEnd`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-install-plugin</artifactId>
    <version>3.1.4</version>
    <configuration>
        <installAtEnd>true</installAtEnd>
    </configuration>
</plugin>
~~~

Đây là **đoạn plugin configuration minh họa**, không phải POM độc lập. Khi được áp dụng đúng trong multi-module build, plugin có thể hoãn việc cài các artifacts cho đến cuối reactor; nếu một project fail, mục tiêu là tránh các project đã build thành công sớm bị cài một phần.

Lưu ý:

- Tài liệu plugin mô tả tính năng này là **experimental**.
- Mặc định `installAtEnd=false`, nên có thể thấy một vài modules đã được install trước khi một module sau fail.
- `installAtEnd` không tự tạo transaction ACID hoặc rollback mọi filesystem modification ở repository theo mọi tình huống.
- Nếu CI yêu cầu atomic publish cho team, cần thiết kế remote repository/staging/release riêng; không coi local cache là bản phân phối chính thức.

## 17. Bỏ qua bước install có chủ đích

Plugin có option:

~~~bash
mvn -B -ntp install -Dmaven.install.skip=true
~~~

Khi `maven.install.skip=true` được plugin nhận, goal install có thể bỏ qua việc cài artifact. Những phase trước như compile/test/package **vẫn có thể đã chạy**.

Điều này hữu ích trong một số workflow kiểm thử, nhưng trong lab, nếu bạn dùng cờ skip thì consumer project không nên kỳ vọng artifact mới xuất hiện trong local repository.

**Cảnh báo CI:** Một pipeline in `BUILD SUCCESS` sau lệnh có skip-install có thể chưa cài artifact. Hãy đọc install goal log và xác nhận đúng file ở local repository.

Không dùng skip-install để che lỗi thiếu main artifact hoặc thiết kế packaging sai.

## 18. install không đẩy artifact lên remote repository

So sánh chính xác:

| Hoạt động | Local repository | Remote repository |
| --- | --- | --- |
| `mvn package` | Không bắt buộc cài project artifact | Không tự upload |
| `mvn install` | Cài project artifacts/POM | Không tự upload |
| `mvn deploy` | Thường chạy cả các phase trước, gồm install, theo lifecycle | Cố gắng upload artifact/POM lên remote theo cấu hình deploy |
| `mvn install:install-file` | Cài một external artifact | Không tự upload |
| `mvn deploy:deploy-file` | Có thể có hoạt động local theo goal/runtime | Upload external artifact tới remote được chỉ định |

Remote deploy cần cấu hình tương ứng (ví dụ `distributionManagement`, Maven Deploy Plugin, repository URL và credential mapping trong `settings.xml`).

**Không được suy luận rằng đồng đội có thể tải dependency chỉ vì bạn đã chạy `mvn install` trên laptop.** Local repo thường thuộc người dùng/máy hoặc runner cụ thể.

Nếu team cần chia sẻ một version, dùng internal Maven repository được quản lý hoặc quy trình release/deploy hợp lệ.

## 19. Cài JAR được tạo ngoài Maven: install:install-file

Đôi khi bạn có một JAR không được tạo trong Maven project: thư viện nội bộ cũ hoặc binary vendor chỉ được phân phối qua file. Maven Install Plugin có goal:

~~~text
install:install-file
~~~

Đây là **goal khác** với lifecycle `install:install`. Nó được thiết kế để install một file có sẵn vào local repository.

### Ví dụ dùng coordinates từ CLI

Giả sử có file thật:

~~~text
artifacts/vendor-utils-1.0.jar
~~~

và bạn chọn coordinates nội bộ:

~~~text
dev.vendor:vendor-utils:1.0.0
~~~

Từ working directory có file đó, gọi:

~~~bash
mvn org.apache.maven.plugins:maven-install-plugin:3.1.4:install-file -Dfile=artifacts/vendor-utils-1.0.jar -DgroupId=dev.vendor -DartifactId=vendor-utils -Dversion=1.0.0 -Dpackaging=jar -DgeneratePom=true
~~~

Đây là **lệnh mẫu có điều kiện**: phải có file `artifacts/vendor-utils-1.0.jar` thật. Trong bài lab Java 17 ở mục 7, chúng ta không tạo file vendor này, nên lệnh không thuộc quy trình build runnable chính.

Nếu không có POM thật, `generatePom=true` tạo một POM tối thiểu; nó **không thể tự suy ra đầy đủ** các third-party dependencies mà binary JAR cần.

### Khi vendor cung cấp POM

Nếu có:

~~~text
artifacts/vendor-utils-1.0.jar
artifacts/vendor-utils.pom
~~~

nên dùng:

~~~bash
mvn org.apache.maven.plugins:maven-install-plugin:3.1.4:install-file -Dfile=artifacts/vendor-utils-1.0.jar -DpomFile=artifacts/vendor-utils.pom
~~~

Goal lấy coordinates và metadata từ POM khi hợp lệ. Đây là lựa chọn tốt hơn so với tự tạo minimal POM nếu vendor POM mô tả chính xác dependency graph.

### Tránh nhầm lẫn

- `install:install`: được gọi cho Maven **project artifact** sau lifecycle packaging.
- `install:install-file`: cài **file bên ngoài** vào repository theo coordinates/POM.
- Không nên chạy `install-file` trên output JAR của một Maven project bình thường nếu có thể chạy `mvn install`: goal project install giữ quan hệ artifact/POM/attached artifacts thống nhất hơn.
- Không tự dựng một POM giả có dependency sai để làm Maven hết báo lỗi; consumer có thể gặp runtime failures.

## 20. Nếu install-file cần kho cục bộ riêng

Install Plugin hỗ trợ parameter `localRepositoryPath` cho `install-file`. Ví dụ:

~~~bash
mvn org.apache.maven.plugins:maven-install-plugin:3.1.4:install-file -Dfile=artifacts/vendor-utils-1.0.jar -DgroupId=dev.vendor -DartifactId=vendor-utils -Dversion=1.0.0 -Dpackaging=jar -DlocalRepositoryPath=/tmp/maven-vendor-cache
~~~

Đây là ví dụ **Unix-like** và cũng yêu cầu vendor file thật. Option này điều khiển location **cho goal install-file**. Nếu project tiêu thụ lại dùng local repository khác, artifact mới cài có thể không được tìm thấy.

Khi muốn **toàn Maven invocation** dùng một local repository độc lập, dùng:

~~~bash
mvn -Dmaven.repo.local=/tmp/maven-lab-repository clean install
~~~

Đường dẫn thực tế phải là path ghi được và phù hợp OS. Trong CI, việc cô lập repository giúp xác nhận project không vô tình dùng artifact cũ từ developer cache; lần đầu vẫn cần resolve plugins/dependencies từ remote nếu chưa cached.

## 21. Tùy chỉnh local repository qua settings.xml

Maven Settings có thể định nghĩa:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <localRepository>/opt/maven-repository</localRepository>
</settings>
~~~

Đây là **cấu hình minh họa** cho một môi trường Unix-like; đường dẫn phải tồn tại/ghi được hoặc Maven phải có khả năng tạo ra nó. File cấu hình người dùng thường ở:

~~~text
~/.m2/settings.xml
~~~

Ngoài ra, Maven có thể dùng global settings và cho phép lựa chọn settings file khác:

~~~bash
mvn -s path/to/settings.xml clean install
~~~

Trong quá trình chẩn đoán, dùng Maven Help Plugin để xem effective settings, ví dụ:

~~~bash
mvn -B -ntp -f message-core/pom.xml help:effective-settings
~~~

**Cẩn thận:** settings có thể chứa thông tin server credentials hoặc thông tin nội bộ. Không đăng toàn bộ effective settings lên issue công khai; nếu cần chia sẻ, phải redact secrets/tokens/URL nhạy cảm.

### CLI override cho một lần build

~~~bash
mvn -B -ntp -Dmaven.repo.local=/tmp/isolated-m2 -f message-core/pom.xml clean install
~~~

Nếu consumer chạy lại với default repository `~/.m2/repository`, nó sẽ **không tự biết** artifact đã được cài ở `/tmp/isolated-m2`.

Do đó consumer phải dùng cùng option:

~~~bash
mvn -B -ntp -Dmaven.repo.local=/tmp/isolated-m2 -f message-cli/pom.xml clean verify
~~~

**Bài học:** Khi debug “tôi đã install nhưng Maven vẫn không thấy”, phải xác định chính xác local repository của **cả build tạo artifact và build tiêu thụ**.

## 22. Kiểm tra local repository bằng filesystem

Khi dùng repository mặc định, có thể kiểm tra file bằng hệ điều hành:

Linux/macOS:

~~~bash
ls -l "$HOME/.m2/repository/dev/learning/local/message-core/1.0.0/"
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem "$HOME\.m2\repository\dev\learning\local\message-core\1.0.0"
~~~

Kỳ vọng có ít nhất:

~~~text
message-core-1.0.0.jar
message-core-1.0.0.pom
~~~

Đây là hai file cốt lõi; các metadata files bổ sung không phải lỗi.

Bạn có thể đọc POM đã install để kiểm tra đúng coordinates và dependency declarations. Không tự chỉnh trực tiếp POM trong local repository để “vá” một build; thay POM gốc rồi `install` lại hoặc phát hành một version được kiểm soát.

### Xác minh cùng một version

Nếu `message-core-1.0.0.jar` trong repository khác với `message-core/target/message-core-1.0.0.jar` ở local build, có thể build/install vào repository khác, build thất bại trước phase install hoặc artifact được cài từ lần trước.

So sánh checksum là một bước hỗ trợ, ví dụ Linux:

~~~bash
sha256sum message-core/target/message-core-1.0.0.jar
sha256sum "$HOME/.m2/repository/dev/learning/local/message-core/1.0.0/message-core-1.0.0.jar"
~~~

Nếu nội dung bằng nhau, SHA-256 bằng nhau. Nhưng checksum không thay thế thông tin build provenance; file có thể thuộc source revision nào đó mà không có metadata xác minh thêm.

## 23. Version không đúng khiến artifact “biến mất”

Library được cài theo:

~~~text
dev.learning.local:message-core:1.0.0
~~~

Nhưng consumer khai báo:

~~~xml
<dependency>
    <groupId>dev.learning.local</groupId>
    <artifactId>message-core</artifactId>
    <version>1.0.1</version>
</dependency>
~~~

thì Maven sẽ tìm **version 1.0.1**, không tự dùng `1.0.0` chỉ vì tên artifact gần giống.

Cần kiểm tra đủ:

- `groupId` chính xác, kể cả dấu chấm.
- `artifactId` chính xác, kể cả dấu gạch nối.
- `version` chính xác.
- `type/packaging` phù hợp.
- `classifier` khi được khai báo.
- Local/remote repository đang được dùng.

**Đừng sửa bằng cách đổi filename JAR trong repository** nhưng không đổi POM/coordinates. Hãy nhất quán version trong producer và consumer.

## 24. SNAPSHOT so với release version

Trong quá trình phát triển, version có thể là:

~~~xml
<version>1.0.1-SNAPSHOT</version>
~~~

`-SNAPSHOT` biểu thị một version đang phát triển, có thể thay đổi qua các lần build/install. Maven local repository lưu artifacts và metadata SNAPSHOT theo quy tắc resolver/repository type.

Một vài quy tắc:

- Chạy `install` nhiều lần cùng `1.0.1-SNAPSHOT` có thể cập nhật local snapshot artifact.
- Với release version như `1.0.0`, build lại cùng GAV rồi install lên local repo có thể **thay thế** artifact cục bộ; điều này không phải release management đáng tin cậy cho team.
- Không nên tái sử dụng release GAV để đại diện những binaries khác nhau trong môi trường chia sẻ.
- Nếu consumer chạy với local artifact stale, build outcome có thể khác máy/CI dù POM ghi cùng version.
- `-U` liên quan chính sách kiểm tra cập nhật snapshot/remote metadata, **không phải lệnh “cài lại project”**. Nếu producer source đổi, hãy build/install producer đúng cách hoặc build cùng reactor.

Khi project có nhiều developer, thông thường nên có internal remote repository để công bố snapshots/releases theo chính sách, thay vì mỗi người chia sẻ thư mục `.m2` cá nhân.

## 25. install và attached artifacts: sources, javadoc, classifier

Maven project có thể tạo thêm artifacts gắn classifier:

~~~text
message-core-1.0.0.jar
message-core-1.0.0-sources.jar
message-core-1.0.0-javadoc.jar
~~~

Những attached artifacts thường được tạo bởi Maven Source/Javadoc Plugins và **được attach vào project** trong lifecycle. Khi install phase chạy, Maven Install Plugin có thể cài cả main artifact, POM và attached artifacts.

**Không phải cứ chạy install là chắc chắn có sources.jar hoặc javadoc.jar.** Phải cấu hình các plugin/executions tạo và attach chúng trước phase install.

Consumer muốn dùng source JAR để IDE hiển thị source code, không phải thay classpath runtime:

~~~xml
<dependency>
    <groupId>dev.learning.local</groupId>
    <artifactId>message-core</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Maven/IDE vẫn dùng main JAR cho bytecode, và có thể tải classifier `sources`/`javadoc` khi artifacts ấy tồn tại.

Nếu artifact sử dụng classifier `tests`, `all` hoặc `exec`, consumer phải khai báo đúng classifier/type nếu muốn resolve artifact đó. Đừng mặc định thư viện dưới classifier có layout như main JAR.

## 26. Dependency scopes và POM được install

Khi install POM, các dependency declarations giữ những scopes đã khai báo:

- `compile`: API/library cần cho compilation và thường runtime.
- `runtime`: chỉ cần lúc chạy nhưng không nhất thiết compile.
- `provided`: môi trường dự kiến cung cấp ở runtime, thường không transitive như compile.
- `test`: chỉ áp dụng test của chính project theo Maven rules.
- `optional`: yêu cầu consumer quyết định có khai báo dependency ấy trực tiếp không.

Maven Resolver quyết định transitivity dựa vào POM, dependency graph, scopes, exclusions và dependencyManagement. Không phải mọi dependency từng tải khi build producer đều được “kèm” sang consumer.

Trong lab, JUnit có `<scope>test</scope>` nên consumer **không tự nhận** JUnit chỉ vì message-core được install; consumer khai báo JUnit riêng để chạy `MainTest`.

**Local repository chứa binary và metadata, không thay thế quy tắc transitivity của Maven.**

## 27. Tại sao không nên dùng system scope?

Một đoạn cấu hình không nên dùng cho lab:

~~~xml
<dependency>
    <groupId>dev.learning.local</groupId>
    <artifactId>message-core</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>/home/me/project/message-core/target/message-core-1.0.0.jar</systemPath>
</dependency>
~~~

Đây là **phản ví dụ**, không phải cấu hình khuyến nghị.

Nhược điểm:

- Phụ thuộc filesystem path của một máy.
- Không dùng Maven repository metadata/normal resolution.
- Khó tái lập trên CI/Windows/team.
- POM consumer không nói đúng cách library được quản lý/phát hành.
- Không giải quyết đầy đủ transitive dependencies.

Cách đúng trong trường hợp producer là Maven project: chạy `mvn install` ở producer, khai báo dependency coordinates thông thường ở consumer, hoặc build cả hai trong một reactor.

## 28. Khi nào phải dùng install:install-file thay cho install?

| Tình huống | Cách làm |
| --- | --- |
| Project Maven có POM và lifecycle chuẩn | `mvn clean install` |
| JAR vendor được tạo ngoài Maven, không có POM | `install:install-file` cùng GAV và POM tối thiểu có kiểm soát |
| JAR vendor có POM chính xác | `install:install-file -DpomFile=...` |
| Cần build hai modules có source chung | Reactor `mvn -pl ... -am verify/install` |
| Cần chia sẻ JAR cho đồng đội | Deploy lên remote repository, không chỉ local install |
| Cần tạo executable CLI một file | Packaging/manifest/dependency distribution; install không tự giải quyết |
| Cần kiểm tra transitive deps | POM có dependency metadata đúng và `dependency:tree` |

**Lưu ý:** Một số JAR do Maven tạo chứa embedded POM dưới `META-INF/maven/...`. Phiên bản Install Plugin và options có thể lấy metadata ấy cho `install-file` khi thích hợp. Tuy nhiên với một project Maven đầy đủ, dùng `mvn install` vẫn đơn giản và ít rủi ro POM lệch hơn.

## 29. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `message-cli` báo Could not find artifact | Library chưa install, GAV sai hoặc repo khác | Đối chiếu producer POM, consumer POM, local repo path |
| `message-core.jar` tồn tại ở target nhưng consumer fail | Chỉ package, chưa install | Chạy producer `clean install` |
| Consumer vẫn dùng code/library cũ | Local repo có artifact GAV cũ | Rebuild/install producer, so checksum và GAV |
| File JAR có nhưng POM thiếu | Install thủ công/corrupt repository | Dùng Install Plugin và POM đúng, không chép tay |
| Parent POM could not be resolved | Parent chưa có trong repository của consumer | Install/deploy parent hoặc sửa parent resolution |
| Offline build không tìm được plugin | `-o` nhưng plugin/dependency chưa cached | Populate cache từ kho hợp lệ trước |
| `mvn install` báo success nhưng không có artifact như mong đợi | Skip install, packaging pom, classifier hoặc repo khác | Xem plugin logs, `maven.install.skip`, POM packaging |
| Chạy `install:install` trực tiếp báo missing main artifact | Chưa qua package phase | Dùng lifecycle `mvn install` thay vì chỉ goal |
| `install-file` tạo POM nhưng consumer lỗi runtime | Minimal POM không mô tả transitive dependencies | Dùng vendor POM thật hoặc bổ sung metadata phù hợp |
| Maven không ghi được repository | File permission, disk full, security software | Xem đường dẫn/ownership/quota thực tế, không tự đoán |
| Artifact có classifier nhưng dependency không thấy | Consumer đang yêu cầu main artifact | Khai báo classifier/type đúng |
| CI khác local | Different JDK/Maven/settings/local cache | Pin toolchain, log Maven version, isolate local repo |
| Rebuild release version nhưng consumer khác máy vẫn cũ | Local install không publish remote | Đổi version và deploy chính thức |
| `-N install` chỉ có parent POM | Non-recursive bỏ children | Chạy full reactor install nếu cần child artifacts |
| JAR resolve được nhưng Java launcher lỗi | Runtime classpath thiếu dependency | Dùng classpath/distribution phù hợp, không đổ lỗi install |
| Dependency tree hiển thị version ngoài ý muốn | Dependency mediation/management | Xem tree, effective POM và exclusions |

## 30. Quy trình chẩn đoán “đã install nhưng không thấy”

Khi gặp lỗi:

~~~text
Could not find artifact dev.learning.local:message-core:jar:1.0.0
~~~

làm theo thứ tự:

1. Kiểm tra producer: `message-core/pom.xml` có đúng groupId/artifactId/version/packaging không?
2. Xem lệnh producer đã chạy tới phase `install` chưa, hay dừng ở `package`/`verify`?
3. Xem build log có `install:install` và dòng “Installing ... to ...” hay skip/fail?
4. Xác định local repo thật của producer: default path, `settings.xml` hay `-Dmaven.repo.local`?
5. Tìm cả `message-core-1.0.0.jar` **và** `message-core-1.0.0.pom` ở GAV path.
6. Xác định local repo của **consumer**, so có trùng producer repo không.
7. Kiểm tra dependency coordinates và classifier/type của consumer.
8. Nếu project đang offline, xác nhận cả plugins và transitive dependencies đã cached.
9. Chạy `dependency:tree` trên consumer để thấy graph sau resolution.
10. Nếu library có parent POM riêng, bảo đảm parent resolvable.
11. Nếu local artifact nghi stale, build producer sạch, install lại đúng GAV rồi so JAR checksum.
12. Nếu CI cần isolation, dùng một local repository riêng cho lab thay vì chỉnh repository toàn máy.

**Không xóa bừa `~/.m2/repository`** để “sửa Maven”: nó có thể rất lớn và chứa nhiều artifacts đang được project khác dùng. Nếu thật sự cần điều tra cache hỏng, cô lập repository hoặc xử lý đúng đường dẫn artifact sau khi đã xác minh nguyên nhân.

## 31. CI: khi nào local install là cần thiết?

Trong một pipeline multi-module, Maven reactor có thể tự resolve dependencies giữa modules, nên full reactor `verify` không cần “install từng module rồi build module tiếp” chỉ để compiler thấy sibling artifacts.

Ngược lại, nếu CI có các **jobs tách rời**, local repository mỗi job có thể là filesystem/container khác nhau. Chạy `mvn install` trong job A **không tự chuyển** artifact sang job B.

Các lựa chọn có chủ đích:

1. Build/test tất cả modules trong một Maven reactor.
2. Truyền artifacts giữa jobs bằng hệ thống artifact storage chính thức của CI.
3. Deploy version đã kiểm thử lên một remote Maven repository nội bộ và để downstream jobs resolve.
4. Dùng cùng persistent cache nếu policy cho phép, nhưng không coi cache là release artifact.
5. Tránh những lệnh copy file không có metadata POM, khiến consumer không resolve đúng graph.

Khi xây pipeline release, cần tách rõ mục tiêu **cache**, **artifact transfer** và **publication**. Local Maven repository chủ yếu phục vụ resolution trong môi trường build, không phải hệ thống phát hành có kiểm soát cho cả tổ chức.

## 32. Lệnh hữu ích trong quá trình làm việc

| Lệnh | Tác dụng |
| --- | --- |
| `mvn -version` | Xem Maven/JDK đang thực thi |
| `mvn -B -ntp clean package` | Tạo artifact trong target |
| `mvn -B -ntp clean verify` | Kiểm tra build tới verify, chưa cài artifact dự án |
| `mvn -B -ntp clean install` | Build/test/package rồi cài artifact/POM local |
| `mvn -B -ntp install -Dmaven.install.skip=true` | Đi qua install nhưng skip installation goal theo plugin policy |
| `mvn -B -ntp -N install` | Với aggregator POM, cài starting POM mà không build child modules |
| `mvn -B -ntp help:effective-settings` | Kiểm tra Maven settings; cần bảo vệ secrets |
| `mvn -B -ntp help:effective-pom` | Kiểm tra POM hiệu lực |
| `mvn -B -ntp dependency:tree` | Xem dependency graph của project |
| `mvn -B -ntp -Dmaven.repo.local=/tmp/new-repo clean install` | Dùng local repo cô lập, ví dụ Unix-like |
| `mvn install:install-file ...` | Cài một file artifact ngoài Maven build |

Cảnh báo về dòng cuối: `...` là ký hiệu rút gọn, **không phải tham số CLI thực**. Mẫu lệnh `install-file` đầy đủ có ở mục 19.

## 33. Bài tập kiểm tra kiến thức có đáp án

1. **`mvn install` có khác `mvn package` không?**  
   **Đáp án:** Có. Install chạy tiếp tới phase install và cài artifact/POM vào local repo.

2. **Local Maven repository mặc định thường ở đâu?**  
   **Đáp án:** `~/.m2/repository`, trừ khi cấu hình khác.

3. **Cặp file chính của library JAR sau install là gì?**  
   **Đáp án:** JAR và POM tương ứng cùng GAV.

4. **GAV `dev.learning.local:message-core:1.0.0` map path thế nào?**  
   **Đáp án:** `dev/learning/local/message-core/1.0.0/`.

5. **Consumer Maven có tự đọc `../message-core/target/*.jar` không?**  
   **Đáp án:** Không; nó resolve dependency theo repository/reactor.

6. **Tại sao bài lab dùng hai project độc lập?**  
   **Đáp án:** Để chứng minh consumer cần library từ repository thay vì reactor.

7. **Gọi `mvn clean install` có chạy tests không?**  
   **Đáp án:** Có, theo default lifecycle và plugins đã cấu hình, trừ khi được skip hoặc cấu hình khác.

8. **JAR đã install có tự chứa JUnit test dependencies không?**  
   **Đáp án:** Không. Plain JAR không tự nhúng dependencies.

9. **POM được install giúp consumer việc gì?**  
   **Đáp án:** Resolve metadata/packaging và transitive dependencies theo rules.

10. **Local install có upload JAR lên Maven Central không?**  
    **Đáp án:** Không.

11. **Muốn đưa artifact lên remote repository theo workflow Maven dùng phase nào?**  
    **Đáp án:** `deploy` với cấu hình remote repository phù hợp.

12. **Goal chính của Maven Install Plugin là gì?**  
    **Đáp án:** `install:install`.

13. **Lệnh nào dùng cho vendor JAR không thuộc Maven project?**  
    **Đáp án:** `install:install-file`.

14. **Nếu vendor có POM, nên truyền option nào?**  
    **Đáp án:** `-DpomFile=...`.

15. **Minimal generated POM có tự mô tả đầy đủ third-party dependencies không?**  
    **Đáp án:** Không.

16. **Vì sao không copy JAR bằng tay vào `.m2/repository`?**  
    **Đáp án:** Dễ sai POM/metadata/repository consistency.

17. **Project packaging `pom` sau install thường có file chính nào?**  
    **Đáp án:** POM artifact, không nhất thiết có JAR.

18. **`mvn -N install` tại aggregator POM có install child JARs không?**  
    **Đáp án:** Không, non-recursive chỉ xử lý starting project.

19. **Reactor có thể resolve sibling dependencies khi chưa install không?**  
    **Đáp án:** Có, trong multi-module build phù hợp.

20. **Nếu consumer dùng version 1.0.1 nhưng producer cài 1.0.0 thì sao?**  
    **Đáp án:** Maven tìm 1.0.1; không tự coi 1.0.0 là tương đương.

21. **Cách đổi local repository cho một Maven invocation?**  
    **Đáp án:** `-Dmaven.repo.local=<path>`.

22. **Cách cấu hình local repository qua settings?**  
    **Đáp án:** `<localRepository>absolute/path</localRepository>`.

23. **Nếu producer và consumer dùng hai repository paths khác nhau?**  
    **Đáp án:** Consumer có thể không thấy artifact vừa install.

24. **`installAtEnd` nhằm giải quyết vấn đề gì?**  
    **Đáp án:** Hoãn installation trong reactor để hạn chế partial installs khi build fail.

25. **`maven.install.skip=true` ảnh hưởng gì?**  
    **Đáp án:** Bỏ bước cài artifact khi plugin nhận option, không nhất thiết bỏ compile/test/package.

26. **Một JAR sources có được install mặc định ở mọi project không?**  
    **Đáp án:** Không; cần attached artifact được tạo bởi plugin tương ứng.

27. **Classifier ảnh hưởng việc resolve thế nào?**  
    **Đáp án:** Phân biệt artifacts phụ với main artifact, consumer phải yêu cầu đúng loại.

28. **Vì sao `java -jar message-cli.jar` không phải lệnh demo chính?**  
    **Đáp án:** Lab tạo plain JAR chưa có Main-Class và không nhúng message-core dependency.

29. **Consumer Java class in dòng gì trong lab?**  
    **Đáp án:** `Hello, Maven from message-core`.

30. **Sau khi install, nên kiểm tra những gì trước khi kết luận thành công?**  
    **Đáp án:** Lệnh install và log, đúng GAV, đúng local repo, JAR + POM và consumer resolution.

31. **Version SNAPSHOT khác release ở điểm nào quan trọng với local install?**  
    **Đáp án:** SNAPSHOT là bản đang phát triển; cùng coordinates có thể được cài lại, dễ xuất hiện stale artifact nếu quản lý kém.

32. **Có nên coi local repo là công cụ phân phối bản release cho team?**  
    **Đáp án:** Không; nên dùng remote repository/CI artifact publication có kiểm soát.

33. **Một parent POM chưa resolve được có thể ảnh hưởng consumer không?**  
    **Đáp án:** Có, nếu consumer cần model metadata của artifact tham chiếu parent đó.

34. **Maven install có tạo checksum theo option createChecksum từ plugin 3.x không?**  
    **Đáp án:** Không; option cũ đã bị loại khỏi Install Plugin 3.x.

35. **Khi build CI ở container khác, library được install trên laptop có sẵn không?**  
    **Đáp án:** Không mặc nhiên; cần repository/artifact transfer được cấu hình.

## 34. Checklist trước khi dùng install trong dự án thật

- [ ] Ghim Maven/JDK/plugin versions phù hợp hoặc dùng Maven Wrapper.
- [ ] Producer POM có groupId/artifactId/version/packaging đúng.
- [ ] Build và tests đã đạt trước phase install.
- [ ] Dùng `mvn clean install` khi cần tránh stale build outputs.
- [ ] Xác nhận goal `install:install` thực sự chạy, không bị skip.
- [ ] Xác nhận JAR (hoặc loại artifact khác) và POM được cài đúng path.
- [ ] Biết local repository thực đang ở đâu; xem settings/CLI overrides.
- [ ] Không sửa JAR/POM metadata trực tiếp trong local repository.
- [ ] Consumer dùng tọa độ dependency đúng, không hard-code systemPath.
- [ ] Consumer resolve artifact thành công từ repository đúng.
- [ ] Nếu producer có parent POM riêng, bảo đảm parent cũng resolvable.
- [ ] Với module cùng reactor, cân nhắc `-am` thay vì install sibling thủ công.
- [ ] Không nhầm install với deploy/chia sẻ artifact cho đồng đội.
- [ ] Không nhầm Maven repository resolution với Java runtime classpath.
- [ ] Kiểm tra transitive dependencies/scope/optional/exclusions đúng theo POM.
- [ ] Có chiến lược versioning, tránh tái sử dụng release GAV cho binaries khác.
- [ ] Khi cần sources/javadoc, bảo đảm attached artifacts được tạo trước install.
- [ ] Nếu dùng `install-file`, ưu tiên original vendor POM khi có.
- [ ] Không coi minimal generated POM là mô tả đầy đủ runtime dependencies.
- [ ] Với CI nhiều jobs, dùng artifact storage hoặc remote Maven repository rõ ràng.
- [ ] Không dựa vào persistent local cache như bằng chứng release provenance.
- [ ] Không xóa toàn bộ `.m2/repository` khi chưa xác định lỗi.
- [ ] Khi repo thiếu artifact, kiểm tra producer/consumer dùng cùng repository path.
- [ ] Khi build thất bại, đọc lỗi Maven/plugin thật; không suy đoán quyền hoặc firewall.
- [ ] Lưu lệnh build, Maven version, artifact coordinates và kết quả kiểm tra để tái lập.

## 35. Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase `package`, `verify`, `install` và `deploy`.
- [Apache Maven — Install Plugin Introduction](https://maven.apache.org/plugins/maven-install-plugin/): mục đích local installation, goals và mặc định repository path.
- [Apache Maven — install:install Goal](https://maven.apache.org/plugins/maven-install-plugin/install-mojo.html): project main artifact, POM, attached artifacts, `installAtEnd` và skip.
- [Apache Maven — install:install-file Goal](https://maven.apache.org/plugins/maven-install-plugin/install-file-mojo.html): external file, pomFile, coordinates và localRepositoryPath.
- [Apache Maven — Installing a Custom POM](https://maven.apache.org/plugins/maven-install-plugin/examples/custom-pom-installation.html): sử dụng POM được cung cấp khi cài file.
- [Apache Maven — Installing an Artifact to a Specific Local Repository](https://maven.apache.org/plugins/maven-install-plugin/examples/specific-local-repo.html): localRepositoryPath.
- [Apache Maven — Guide to Installing 3rd Party JARs](https://maven.apache.org/guides/mini/guide-3rd-party-jars-local.html): install-file và lý do không chép JAR thủ công.
- [Apache Maven — Maven Settings Reference](https://maven.apache.org/settings.html): localRepository và settings configuration.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): repository resolution và local/remote repositories.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, scopes và dependency management.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor và module dependencies.
- [Apache Maven — Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/): đối chiếu install local với deploy remote.
- [Apache Maven — Dependency Plugin: tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): kiểm tra resolved dependency graph.
- [MojoHaus — Exec Maven Plugin](https://www.mojohaus.org/exec-maven-plugin/): chạy Java main từ Maven project classpath.

**Kết luận:** `install` đưa **artifact và POM của project** vào Maven local repository theo coordinates để project khác có thể resolve dependency. Nó **khác** với `package` chỉ tạo artifact trong target và `deploy` chia sẻ artifact qua remote repository. Hãy xác nhận đúng JAR, POM, GAV và local repository path, rồi thử một consumer project độc lập để kiểm chứng việc cài đã thực sự có tác dụng.
