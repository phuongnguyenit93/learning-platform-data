# Metadata POM và phụ thuộc bắc cầu của thư viện xuất bản trong Maven

## 1. Vì sao người dùng một thư viện không chỉ cần file JAR?

Giả sử có ba thành phần Java:

~~~text
consumer-app
    |
    | chỉ khai báo dependency trực tiếp
    v
greeting-library:1.0.0
    |
    | dependency trong POM của thư viện
    v
core-text:1.0.0
~~~

`greeting-library` gọi một class thuộc `core-text`. Khi người dùng thêm đúng **một dependency** vào `greeting-library`, Maven có thể tự tải thêm `core-text` nhờ cơ chế **transitive dependencies (phụ thuộc bắc cầu)**.

Điều đó chỉ vận hành đúng khi repository cung cấp không chỉ binary JAR mà còn **POM mô tả thư viện và quan hệ dependency của nó**, đồng thời mọi POM/artifact được tham chiếu đều có thể resolve.

Nếu chỉ chép một file `greeting-library-1.0.0.jar` lên máy rồi chạy, JVM không tự đọc Maven dependencies; nếu `core-text` không có trên runtime classpath, mã thư viện có thể gây `NoClassDefFoundError`. Nếu deploy JAR kèm một **POM rỗng chỉ có GAV**, consumer Maven cũng không tự biết thư viện cần `core-text`.

**Ý chính:** khi phát hành một Maven library, POM không phải “tệp build chỉ dành cho tác giả”. Nó là **artifact descriptor** mà downstream builds sử dụng để biết danh tính, nguồn gốc, dependencies, scopes, optional flags và các quy tắc liên quan.

Bài này tập trung vào **Install và Deploy**: nội dung POM phải đúng trước khi cài đặt/phát hành thư viện, những gì Maven consumer thực sự kế thừa qua dependency graph, và cách kiểm chứng bằng ba Maven projects Java 17 chạy độc lập.

## 2. Phân biệt artifact JAR, POM và maven-metadata.xml

Ba loại file có chức năng riêng:

| File | Vai trò | Maven consumer cần để làm gì? |
| --- | --- | --- |
| `greeting-library-1.0.0.jar` | Java bytecode/resources của thư viện. | Compile/run các class của thư viện. |
| `greeting-library-1.0.0.pom` | Project Object Model được phát hành với thư viện. | Xây effective model của library, đọc dependencies, scopes, exclusions, parent. |
| `maven-metadata.xml` | Metadata ở các cấp group/artifact/version trong Maven repository. | Hỗ trợ khám phá versions, SNAPSHOT resolution hoặc những quy trình liên quan. |

Với repository layout chuẩn và GAV `org.example.library:greeting-library:1.0.0`:

~~~text
org/example/library/greeting-library/
├── maven-metadata.xml                  # có thể có ở artifact level
└── 1.0.0/
    ├── greeting-library-1.0.0.jar
    ├── greeting-library-1.0.0.pom
    └── ... checksums/signatures nếu repository áp dụng ...
~~~

**POM artifact ≠ `maven-metadata.xml`.** Dependency `core-text` được khai báo trong `greeting-library-1.0.0.pom`, không phải trong `maven-metadata.xml`. Bản snapshot có thể dùng metadata để ánh xạ base version `1.0.1-SNAPSHOT` sang timestamped files, nhưng nội dung dependency vẫn đến từ POM tương ứng.

Tên file không phải bằng chứng có metadata hợp lệ. Một file JAR được đổi tên thành `greeting-library-1.0.0.jar` không làm Maven biết POM hoặc dependencies của nó.

## 3. Metadata POM gồm những lớp thông tin nào?

Một POM xuất bản cần được xem ở ít nhất ba lớp:

**(1) Tọa độ và packaging.** `modelVersion`, `groupId`, `artifactId`, `version`, `packaging`. Đây là danh tính của artifact mà Maven consumer khai báo.

**(2) Metadata dành cho con người và hệ sinh thái.** `name`, `description`, `url`, `licenses`, `developers`, `scm`, và có thể `organization`, `issueManagement`, `ciManagement`. Dữ liệu này giúp người dùng biết tác giả, giấy phép, source code và cách liên hệ/bảo trì. Kho công khai như Maven Central có yêu cầu riêng về những thông tin được cung cấp.

**(3) Mô tả để Maven resolve build graph.** `dependencies`, `dependencyManagement`, `parent`, `properties` và thông tin có ảnh hưởng đến effective POM. Đây là lớp giúp một consumer tải đúng thư viện bắc cầu.

Ví dụ **mảnh dependency đúng chỗ** trong POM của library:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example.library</groupId>
        <artifactId>core-text</artifactId>
        <version>1.0.0</version>
        <scope>compile</scope>
    </dependency>
</dependencies>
~~~

Khi một app khai báo `greeting-library` với scope compile, Maven có thể đưa `core-text` vào dependency graph của app theo luật transitivity.

Ngược lại, chỉ thêm `core-text` vào `<dependencyManagement>` của library **không tự tạo dependency**. `dependencyManagement` quản lý version/scope cho dependencies thực sự được sử dụng trong model, không thay `<dependencies>`.

## 4. “Đã publish library” nghĩa là gì với một consumer Maven?

Quá trình bình thường:

~~~text
TÁC GIẢ                                NGƯỜI DÙNG
src/main/java + pom.xml               consumer/pom.xml
             |                              |
       mvn package                            |
             |                              |
       library.jar + POM                      |
             |                              |
        mvn install/deploy                    |
             |                              |
        Maven repository --------------------+
             |                              |
             +--> library-1.0.0.pom --- đọc dependencies
             +--> library-1.0.0.jar --- compile/run
             +--> core-text-1.0.0.pom - đọc dependency tiếp
             +--> core-text-1.0.0.jar - đưa vào classpath
~~~

`install` cài artifact/POM vào **local repository** của máy build; `deploy` gửi chúng tới **remote Maven repository** theo cấu hình được cấp quyền. `package` thường tạo JAR trong `target`, nhưng không thay việc cài đặt hoặc phát hành metadata để một consumer độc lập resolve được.

Nếu thư viện đã deploy ở một remote repository nhưng dependency POM của nó trỏ đến artifact không có trong bất kỳ repository mà consumer có quyền truy cập, transitive resolution vẫn thất bại.

Cụm “tự tải dependency bắc cầu” luôn đi kèm điều kiện **dependency được mô tả chính xác và có thể resolve**.

## 5. Ví dụ thực hành: ba dự án độc lập, không chung reactor

Để chứng minh POM thực sự được cài đặt và được consumer đọc, ta cố tình **không** dùng một aggregator gộp cả ba thành một reactor. Mỗi project có POM riêng:

~~~text
published-library-demo/
├── core-text/
│   ├── pom.xml
│   └── src/main/java/org/example/core/TextNormalizer.java
├── greeting-library/
│   ├── pom.xml
│   └── src/main/java/org/example/greeting/GreetingService.java
└── consumer-app/
    ├── pom.xml
    └── src/main/java/org/example/consumer/Main.java
~~~

Ba project là các **thư mục sibling**, mỗi project được build từ POM của nó, theo thứ tự:

1. Build và `install` `core-text:1.0.0` vào local Maven repository.
2. Build và `install` `greeting-library:1.0.0`; POM của nó khai báo `core-text:1.0.0` là dependency.
3. Build `consumer-app` với **một dependency trực tiếp `greeting-library:1.0.0`**, không tự khai báo `core-text`.
4. Chạy `dependency:tree` và `copy-dependencies` để thấy cả hai JAR hiện trong runtime classpath.
5. Chạy Java 17; stdout có thể suy chính xác từ ba file source.

Môi trường: **JDK 17+**, **Maven 3.9.x**, có quyền tải Maven plugins từ repository thích hợp (hoặc các plugins đã cache). Version plugin trong ví dụ được pin. Đây là **thử nghiệm local install**; không upload bất kỳ file nào lên Maven Central hay kho tổ chức.

## 6. POM hoàn chỉnh của core-text: thư viện tầng dưới

Tạo file `core-text/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.library</groupId>
    <artifactId>core-text</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Core Text Example</name>
    <description>Utilities for normalizing text with Java 17.</description>
    <url>https://example.org/core-text/</url>

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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`core-text` có tọa độ `org.example.library:core-text:1.0.0` và không có project dependencies bên ngoài. URL `example.org` là dữ liệu mẫu, **không trỏ website thật của một thư viện đã xuất bản**.

Tệp POM này đủ cho **thử nghiệm cài local**. Để đưa một artifact thật lên Maven Central, cần chuẩn bị thêm license/developer/SCM metadata, sources/Javadoc, signatures, yêu cầu namespace và quy trình publishing tương ứng. **Không công bố các giá trị ví dụ `org.example.library` hoặc `example.org` như thể đã xác minh quyền sở hữu tên miền/namespace.**

## 7. Mã Java của core-text

Tạo `core-text/src/main/java/org/example/core/TextNormalizer.java`:

~~~java
package org.example.core;

import java.util.Locale;

public final class TextNormalizer {
    private TextNormalizer() {
    }

    public static String normalize(String input) {
        return input.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

Class này chỉ dùng JDK. `strip()` loại khoảng trắng đầu/cuối theo Unicode; `toUpperCase(Locale.ROOT)` chuyển chữ hoa không phụ thuộc locale mặc định của máy. Ví dụ:

~~~text
TextNormalizer.normalize(" Maven ") -> "MAVEN"
~~~

API demo giả định `input` khác null. Khi null, lời gọi `strip()` ném `NullPointerException`; phần xử lý null không liên quan đến metadata dependency nên không thêm chính sách giả.

Tệp Java nằm đúng package path `org/example/core`. `mvn package` tạo `core-text-1.0.0.jar` với class này, **nhưng không vì thế tạo một bản POM artifact ở remote repository**; phải install/deploy theo lifecycle.

## 8. POM hoàn chỉnh của greeting-library: phần metadata quyết định

Tạo `greeting-library/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.library</groupId>
    <artifactId>greeting-library</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Greeting Library Example</name>
    <description>Java 17 greeting API built on core-text.</description>
    <url>https://example.org/greeting-library/</url>

    <licenses>
        <license>
            <name>Apache License, Version 2.0</name>
            <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
            <distribution>repo</distribution>
        </license>
    </licenses>

    <developers>
        <developer>
            <id>example-maintainer</id>
            <name>Example Maintainer</name>
        </developer>
    </developers>

    <scm>
        <connection>scm:git:https://example.org/greeting-library.git</connection>
        <url>https://example.org/greeting-library/source</url>
        <tag>HEAD</tag>
    </scm>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.example.library</groupId>
            <artifactId>core-text</artifactId>
            <version>1.0.0</version>
            <scope>compile</scope>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Tất cả XML trên là một POM hoàn chỉnh cho ví dụ local**, không chứa `<parent>` và không cần aggregator. Metadata `licenses/developers/scm` được đặt để minh họa các trường thường quan trọng khi xuất bản, nhưng **tác giả của một thư viện thực phải thay bằng dữ liệu pháp lý/đầu mối/source repository chính xác**. URL `example.org`/developer minh họa không phù hợp để gửi một release production lên Maven Central.

**Điểm then chốt là `<dependencies>`:**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example.library</groupId>
        <artifactId>core-text</artifactId>
        <version>1.0.0</version>
        <scope>compile</scope>
    </dependency>
</dependencies>
~~~

Đây là **dependency thực sự**, không chỉ quản lý version. Maven ghi quan hệ này trong POM artifact của `greeting-library` được `install`/`deploy`. Consumer Maven đọc quan hệ để resolve `core-text` bắc cầu.

Không đánh đồng source-level import với Maven dependency discovery: Maven không quét bytecode của JAR để đoán `core-text` một cách đáng tin; **POM metadata** mới là nguồn để xây graph.

## 9. Mã Java của greeting-library

Tạo `greeting-library/src/main/java/org/example/greeting/GreetingService.java`:

~~~java
package org.example.greeting;

import org.example.core.TextNormalizer;

public final class GreetingService {
    private GreetingService() {
    }

    public static String greet(String name) {
        return "Hello, " + TextNormalizer.normalize(name) + "!";
    }
}
~~~

`GreetingService` **thực sự gọi class từ `core-text`**, không chỉ có dependency “cho đẹp”. Khi biên dịch `greeting-library`, Maven cần `core-text:1.0.0` trên compile classpath.

Với đối số `" Maven "`, `TextNormalizer.normalize` trả `"MAVEN"`, rồi `GreetingService.greet` trả:

~~~text
Hello, MAVEN!
~~~

Class này có thể compile khi `core-text` đã được install/deploy đúng GAV. Runtime consumer cũng cần core-text JAR. Nếu một người dùng copy riêng greeting-library JAR mà bỏ core-text JAR, lỗi có thể xuất hiện **khi phương thức gọi đến TextNormalizer được chạy**, không nhất thiết ngay lúc class consumer được load.

## 10. POM hoàn chỉnh của consumer-app: chỉ một dependency trực tiếp

Tạo `consumer-app/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.consumer</groupId>
    <artifactId>consumer-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Consumer App Example</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.example.library</groupId>
            <artifactId>greeting-library</artifactId>
            <version>1.0.0</version>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Cố ý không khai báo `core-text` ở consumer.** Maven sẽ lấy dependency này **bắc cầu từ POM của greeting-library**. Điều đó không trái quy tắc “khai báo thư viện được mã nguồn dùng trực tiếp”: consumer code ở mục 11 **chỉ import `GreetingService`**, không import `TextNormalizer`.

`scope` của dependency greeting-library được lược bỏ nên mặc định là `compile`. Nếu consumer cần gọi trực tiếp type của `core-text` trong source code của chính mình, việc khai báo `core-text` trực tiếp là lựa chọn tốt hơn dù hiện nó xuất hiện transitively, vì giúp contract của consumer rõ ràng và ổn định khi greeting-library đổi implementation dependencies.

## 11. Mã Java consumer-app và kết quả dự kiến

Tạo `consumer-app/src/main/java/org/example/consumer/Main.java`:

~~~java
package org.example.consumer;

import org.example.greeting.GreetingService;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(GreetingService.greet(" Maven "));
    }
}
~~~

Chương trình không có import `org.example.core.TextNormalizer`. Maven compile dependency `greeting-library`, còn khi gọi `GreetingService.greet` tại runtime, JVM sẽ cần class `TextNormalizer`.

**Stdout chính xác của ứng dụng khi cả hai JAR dependency có mặt:**

~~~text
Hello, MAVEN!
~~~

Để đảm bảo output dễ xác minh trên mọi terminal, ví dụ dùng chuỗi ASCII, tránh khác biệt console encoding trên một số môi trường Windows khi hiển thị tiếng Việt.

## 12. Build và install đúng thứ tự, không cần root aggregator

Tại thư mục `published-library-demo/` (thư mục cha của ba subfolders), chạy mỗi lệnh **một Maven invocation riêng**:

~~~bash
mvn -B -ntp -f core-text/pom.xml clean install
mvn -B -ntp -f greeting-library/pom.xml clean install
mvn -B -ntp -f consumer-app/pom.xml clean package
~~~

Giải thích:

1. Lệnh đầu compile, package và install `core-text` vào local repository cùng POM.
2. Lệnh hai resolve `core-text` từ local repository, compile `greeting-library` rồi install JAR + POM của chính nó.
3. Lệnh ba build consumer-app; Maven tìm `greeting-library:1.0.0` và đọc POM đã được install, từ đó resolve thêm `core-text:1.0.0`.

Không nhất thiết cần JAR package `consumer-app` để làm API; mục tiêu là chứng minh consumer dependency resolution. Vì example không có test source, `clean install` chạy lifecycle thích hợp nhưng không có unit tests của demo.

Nếu lệnh hai chạy **trước** lệnh core-text trong một local repository sạch, Maven có thể báo không resolve được `core-text`. Đây là hành vi dự kiến, không phải “Maven transitive dependencies bị hỏng”.

**Quan trọng:** `mvn -f greeting-library/pom.xml install` cài thư viện vào **local repository**, không tự deploy lên Maven Central. Consumer chạy ở máy khác cần các artifacts/POMs được deploy vào remote mà máy đó có quyền truy cập.

## 13. Xem dependency:tree từ consumer

Tại `published-library-demo/consumer-app/`:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Kết quả sẽ có cấu trúc tương đương (bỏ các dòng log/banner):

~~~text
org.example.consumer:consumer-app:jar:1.0.0
\- org.example.library:greeting-library:jar:1.0.0:compile
   \- org.example.library:core-text:jar:1.0.0:compile
~~~

Trong phần mô tả Maven tree trên, hai ký tự `\ -` chỉ là cách biểu diễn hierarchy bằng text; Maven output thực có thể dùng các ký tự `+-` và `\-` tùy vị trí nhánh.

Điểm xác minh không phải hình thức indentation, mà là:

- `greeting-library` xuất hiện là **direct dependency** của consumer.
- `core-text` xuất hiện **một cấp sâu hơn** bên dưới greeting-library.
- Cả hai có version `1.0.0` và effective scope `compile` trong setup đã cho.
- Consumer POM **không** trực tiếp khai báo core-text.

Bạn có thể xem dependency graph bằng một lệnh từ thư mục cha nếu dùng `-f`:

~~~bash
mvn -B -ntp -f consumer-app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Hai cách đọc cùng POM có thể tạo log khác đường dẫn, nhưng dependency graph về GAV như nhau.

## 14. Chạy Java với transitive runtime dependencies

Tại `consumer-app/`, sau khi build:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime
~~~

Maven Dependency Plugin sẽ copy những project dependencies có effective scope phù hợp **runtime classpath**, bao gồm direct compile `greeting-library` và transitive compile `core-text`, vào thư mục output mặc định `target/dependency/`:

~~~text
consumer-app/
├── target/classes/org/example/consumer/Main.class
└── target/dependency/
    ├── greeting-library-1.0.0.jar
    └── core-text-1.0.0.jar
~~~

Sau đó, trên **Linux/macOS** chạy:

~~~bash
java -cp "target/classes:target/dependency/*" org.example.consumer.Main
~~~

Trên **Windows PowerShell/CMD** dùng `;` để phân cách classpath:

~~~powershell
java -cp "target\classes;target\dependency\*" org.example.consumer.Main
~~~

**Stdout chính xác của riêng lệnh Java:**

~~~text
Hello, MAVEN!
~~~

`target/dependency/*` là cú pháp wildcard classpath của Java launcher: đưa các JAR bên trong thư mục vào classpath. Dấu `*` được đặt trong chuỗi để shell không tự mở rộng không đúng ý; JVM/launcher xử lý classpath wildcard. Nó **không có nghĩa** Maven tự đóng gói một uber-JAR.

Nếu chỉ chạy:

~~~bash
java -cp "target/classes" org.example.consumer.Main
~~~

thì consumer không tìm được `GreetingService`. Nếu chỉ thêm `greeting-library-1.0.0.jar` mà không có core-text, lời gọi tới `TextNormalizer` sẽ thiếu class. Có dependency bắc cầu trong Maven **không** tự khiến lệnh `java -cp` thủ công nạp JAR nếu bạn không cung cấp runtime classpath phù hợp.

## 15. Cài đặt vào local repository: POM nào thực sự được lưu?

Sau `mvn install` thư viện, cấu trúc local repository mặc định thường như sau:

~~~text
~/.m2/repository/
└── org/example/library/
    ├── core-text/1.0.0/
    │   ├── core-text-1.0.0.jar
    │   └── core-text-1.0.0.pom
    └── greeting-library/1.0.0/
        ├── greeting-library-1.0.0.jar
        └── greeting-library-1.0.0.pom
~~~

Local repository có thể được đổi bằng `settings.xml` hoặc tham số `-Dmaven.repo.local=...`; vì vậy đường dẫn `~/.m2/repository` chỉ là default thông dụng. Các metadata/sidecar files khác có thể tồn tại nhưng không cần liệt kê hết để hiểu cơ chế.

Đọc file:

~~~text
.../org/example/library/greeting-library/1.0.0/greeting-library-1.0.0.pom
~~~

thường thấy một **POM artifact** giữ dependency tới `core-text`, chứ không chỉ POM có GAV. Maven consumer dùng descriptor ấy để tính transitive graph.

**Đừng sửa thủ công file POM trong local repository** rồi công bố quy trình đã đúng. Điều đó có thể chỉ che lỗi của nguồn POM, không thay bản đã deploy remote và khiến build ở máy bạn khác máy đồng nghiệp. Sửa source `greeting-library/pom.xml` rồi phát hành version thích hợp.

## 16. Điều gì xảy ra khi phát hành “JAR trần” kèm generic POM?

Maven Install Plugin hoặc Deploy Plugin có tùy chọn tạo **generic/minimal POM** trong trường hợp chỉ có một third-party JAR, không có POM gốc. Generic POM thường có những field tối thiểu:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.library</groupId>
    <artifactId>greeting-library</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
</project>
~~~

POM trên **không khai báo `core-text`**. Nếu Maven consumer chỉ nhìn generic POM này, nó không có đủ metadata để biết library thực sự cần gì. Khi consumer compile một class chỉ dùng `GreetingService`, build có thể **trông như thành công**, nhưng tại runtime, lệnh Java thiếu `core-text` có thể gây `NoClassDefFoundError`.

**Phân biệt hai use case:**

- **Cài JAR bên thứ ba không có POM:** generic POM là giải pháp hạn chế, có thể chấp nhận cho một artifact cô lập với dependencies được quản lý ngoài.
- **Phát hành thư viện Maven của chính bạn:** cần publish POM **thật**, có dependencies/scopes/optional/exclusions và metadata đúng. Không dùng generic POM chỉ để “đỡ viết XML”.

Các tools như `install:install-file`/`deploy:deploy-file` có tham số `pomFile` để cung cấp POM thực khi cần thủ công; thông thường với project Maven, **ưu tiên `mvn install`/`mvn deploy` theo POM nguồn**.

Đừng chạy một lệnh install-file lên cùng GAV đã cài sẵn rồi âm thầm thay POM có dependency bằng generic POM. Nó làm sai graph trên chính local repository, khó debug và không phản ánh release process hợp lệ.

## 17. Maven đọc phụ thuộc bắc cầu thế nào?

Với dependency graph:

~~~text
A (consumer)
  -> B (greeting-library)
       -> C (core-text)
~~~

Maven đọc POM của B, nhận dependency C; tiếp tục đọc POM của C để tính graph (có thể sâu hơn nhiều cấp). Maven không giới hạn concept ở “chỉ hai tầng”, nhưng dependency cycles hoặc conflict có thể gây lỗi.

Trong ví dụ:

- A khai báo B với effective scope `compile`.
- B khai báo C với `scope=compile`.
- A nhận C bắc cầu, thường có effective scope `compile`.

Đây là hành vi theo **POM dependency metadata**, không phải do A cùng Git repository với B/C hay Maven dùng bytecode scanning.

Có các cơ chế làm hạn chế hoặc biến đổi graph: **scope**, **optional**, **exclusions**, **dependency mediation** (chọn version khi xung đột) và **dependencyManagement** của consumer. Vì vậy “B phụ thuộc C” không có nghĩa **mọi consumer** sẽ luôn nhận C trên **mọi classpath**.

## 18. Scope ảnh hưởng phụ thuộc bắc cầu ra sao?

Theo Maven Dependency Mechanism, scope direct dependency và transitive dependency tương tác để xác định classpath cuối:

| Scope của C trong POM B | B là compile dependency của A | Kết quả thường thấy ở A |
| --- | --- | --- |
| `compile` (hoặc không khai báo scope) | A → B compile | C được đưa vào A với effective scope compile. |
| `runtime` | A → B compile | C được đưa vào A với effective scope runtime, không vào compile classpath của A. |
| `provided` | A → B compile | C không được truyền bắc cầu tới A theo matrix Maven. |
| `test` | A → B compile | C không được truyền bắc cầu tới A. |
| `system` | A → B compile | Không nên dùng để phát hành portable library; systemPath gắn với máy xây. |
| `import` | Chỉ hợp lệ với dependency type `pom` trong dependencyManagement. | Không phải runtime dependency scope; dùng để import BOM management. |

Các scopes chính:

- **compile**: mặc định, dùng ở compile/test/runtime và được truyền xuống consumer phù hợp.
- **runtime**: không cần tại compile của module khai báo nhưng cần khi ứng dụng chạy; truyền bắc cầu với runtime semantics.
- **provided**: cần compile/test tại module khai báo, môi trường/container chịu trách nhiệm cung cấp khi chạy; không nên kỳ vọng transitively đến consumer.
- **test**: chỉ cho test compile/runtime của module khai báo; không được truyền như một production dependency cho consumer.
- **system**: dùng path local được chỉ định, không tải từ repository; có tính di động kém và không phù hợp library công khai.
- **import**: chỉ cho BOM trong `<dependencyManagement>` với type pom.

**Không đặt dependency cần cho `GreetingService.greet` vào scope `test` hoặc `provided`** rồi mong consumer sẽ có core-text trên runtime classpath. Trong demo, dependency `core-text` được khai báo `compile` vì implementation của library thực sự sử dụng nó khi chạy.

## 19. API dependencies và implementation dependencies: chọn scope có chủ đích

Một library có thể dùng dependency theo hai kiểu:

**Chỉ dùng nội bộ ở implementation.** `GreetingService.greet(String)` trả `String`, nhưng code bên trong dùng `TextNormalizer`. Consumer không phải import core-text trong source code của nó, song runtime của library vẫn cần JAR core-text. Với Maven thông thường, `compile` dependency vẫn transitively hiện diện khi consumer khai báo greeting-library.

**Đưa type của dependency lên public API.** Ví dụ **mảnh minh họa**, không thuộc source runnable:

~~~java
package org.example.greeting;

import org.example.core.TextNormalizer;

public final class GreetingApi {
    private GreetingApi() {
    }

    public static TextNormalizer normalizerTypeExample() {
        throw new UnsupportedOperationException("Only an API-shape illustration");
    }
}
~~~

Đoạn trên chỉ minh họa về **public type phụ thuộc library khác**, không phải một API design có ý nghĩa nghiệp vụ; trong code thật, nên dùng một public type có thể sử dụng được. Khi public method parameters/return types/annotations/generics nhắc đến type từ dependency, consumer compiler có thể cần các types đó trong compile classpath. `provided`/`optional`/`exclusions` sai có thể khiến downstream compile fail.

Nguyên tắc: **dependency mà thư viện cần trực tiếp nên được khai báo trực tiếp**, không chỉ trông chờ một thư viện trung gian tình cờ kéo vào. Tương tự, consumer trực tiếp sử dụng `TextNormalizer` trong source của mình nên thêm dependency `core-text` vào POM consumer, ngay cả khi đang nhận nó transitively; như vậy consumer không bị phụ thuộc mơ hồ vào implementation detail của greeting-library.

## 20. Optional dependencies: library không ép mọi consumer tải một tính năng

Giả sử library hỗ trợ tính năng phụ tùy chọn (ví dụ một adapter cho database). Nó có thể khai báo:

~~~xml
<dependency>
    <groupId>org.example.addons</groupId>
    <artifactId>database-adapter</artifactId>
    <version>2.0.0</version>
    <optional>true</optional>
</dependency>
~~~

Đây là **mảnh POM giả định**, không thuộc runnable demo và artifact `org.example.addons` không được phát hành trong bài. `optional=true` có nghĩa dependency phục vụ build/feature của thư viện nhưng **không mặc định được kéo bắc cầu** vào consumer. Khi consumer muốn feature đó, consumer khai báo `database-adapter` trực tiếp theo version cần thiết.

Tránh dùng optional để che một dependency **bắt buộc** cho đường chạy cốt lõi. Nếu đổi `core-text` thành optional nhưng `GreetingService.greet` luôn cần `TextNormalizer`, consumer dùng feature cơ bản có thể gặp `NoClassDefFoundError` trừ khi khai báo core-text riêng. Điều này là một POM contract không thuận tiện và dễ gây lỗi.

Khi một library có nhiều chức năng tùy chọn lớn, tách thành các module artifacts riêng thường dễ quản lý hơn việc có rất nhiều optional dependencies trong một JAR.

## 21. Exclusions: consumer chủ động bỏ một nhánh dependency

Người dùng có thể không muốn nhận một dependency bắc cầu cụ thể vì conflict, vulnerability hoặc muốn thay implementation. Trong POM consumer, đặt exclusion trên **dependency cạnh tạo đường vào graph**:

~~~xml
<dependency>
    <groupId>org.example.library</groupId>
    <artifactId>greeting-library</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.example.library</groupId>
            <artifactId>core-text</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Đây là **mảnh minh họa tác động của exclusions**, không nên áp dụng vào POM runnable của demo. Với `GreetingService` đang gọi trực tiếp `TextNormalizer`, exclusion sẽ khiến runtime **thiếu core-text** nếu không cung cấp một artifact thay thế phù hợp.

Một exclusion được gắn vào **đường quan hệ A → B**, không phải cờ cấm toàn cục cho mọi đường có thể đưa C vào graph. Nếu C còn được kéo vào qua dependency khác, nó có thể vẫn xuất hiện. Muốn đảm bảo một nhóm artifact không xuất hiện trên classpath, có thể dùng Maven Enforcer Plugin với banned dependencies policy và rà soát tất cả các đường.

**Đừng exclude bừa bãi chỉ để làm dependency tree ngắn lại**. Trước hết xác định artifact không cần/không tương thích rồi chạy test thực tế.

## 22. Phiên bản xung đột: dependency mediation

Giả sử app có graph:

~~~text
consumer
├── greeting-library:1.0.0
│   └── logging-api:1.2.0
└── other-library:1.0.0
    └── logging-api:2.0.0
~~~

Đây là **ví dụ lý thuyết với artifacts không có trong runnable demo**. Maven 3 thường sử dụng nguyên tắc **nearest definition** khi cùng một artifact xuất hiện với nhiều phiên bản: đường gần consumer hơn được ưu tiên. Nếu hai đường cùng độ sâu, thứ tự declaration có thể quyết định phiên bản chọn khi không có quy tắc quản lý khác.

Khi version quan trọng, consumer có thể:

- Khai báo direct dependency `logging-api:2.0.0` để chủ động chọn version.
- Dùng `dependencyManagement` của consumer/parent để quản lý version transitive.
- Dùng Maven Enforcer rules như `dependencyConvergence` hoặc `requireUpperBoundDeps` theo release policy để phát hiện graph xung đột.
- Chạy `dependency:tree` và tests để kiểm binary/API compatibility, vì **chọn một version** không đảm bảo mọi dependency sử dụng nó đều tương thích.

**Đặc biệt:** `dependencyManagement` của **consumer effective POM** có thể ảnh hưởng phiên bản transitive được chọn, và có ưu tiên khác với mediation nearest. `dependencyManagement` của Maven build plugins không điều khiển plugin dependencies theo cách tương tự project dependencies.

Một consumer có thể build được hôm nay rồi lỗi sau khi thư viện publish update với dependency versions mới; vì vậy thư viện xuất bản cần theo dõi compatibility và semver/release notes.

## 23. dependencyManagement và BOM không tạo ra dependency

Mảnh `dependencyManagement` trong consumer:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.library</groupId>
            <artifactId>core-text</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Dòng này **chỉ đặt một rule version** nếu `core-text` xuất hiện trong graph. Nó không khiến consumer compiler/runtime tự có core-text nếu không có dependency thực tế nào đưa nó vào.

**BOM import** là một trường hợp khác:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.platform</groupId>
            <artifactId>library-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **mảnh minh họa**, không phải BOM đã xuất bản trong demo. Nó đưa các dependency management entries của BOM vào model consumer, **không** tự thêm những libraries ấy làm dependencies.

BOM POM là một artifact khác với library JAR, thường dùng packaging `pom`. Maven consumer phải resolve BOM đó nếu POM của consumer hoặc parent đang import nó.

**Không dùng BOM thay metadata dependency của library**: `greeting-library` vẫn cần khai báo rằng code của nó thực sự phụ thuộc `core-text`, dù platform BOM quản lý version.

## 24. Parent POM có thể làm metadata publication khó hơn

Ví dụ library xuất bản dưới một parent:

~~~xml
<parent>
    <groupId>org.example.build</groupId>
    <artifactId>company-build-parent</artifactId>
    <version>3.1.0</version>
    <relativePath>../parent/pom.xml</relativePath>
</parent>

<artifactId>greeting-library</artifactId>
~~~

Đây là **mảnh child POM**, không thuộc runnable demo (demo cố tình không có parent). Khi consumer Maven đọc published POM của `greeting-library`, nó có thể cần resolve parent `org.example.build:company-build-parent:3.1.0` để dựng **effective model** và xác định inherited metadata/dependencyManagement.

`relativePath` trên máy tác giả không giúp consumer ngoài source tree nếu parent POM không có ở repository được phép truy cập. Nếu parent chỉ nằm trong laptop, một build local của tác giả có thể pass trong khi người dùng báo `Non-resolvable parent POM`.

Một thư viện có parent cần phát hành:

1. Đảm bảo parent POM cùng **đúng GAV/version** có thể resolve trong target repository hoặc repository phù hợp.
2. Đảm bảo published child POM có parent reference đúng.
3. Kiểm dependencyManagement/properties từ parent thực sự mang lại những versions cần thiết.
4. Test consumer trên environment không có source parent.
5. Nếu dùng shared parent private, cân nhắc public compatibility và quyền truy cập khi phát hành library công khai.

Thư viện độc lập trong bài không có parent nên giảm một nguyên nhân gây lỗi khi học cách resolve transitive dependencies.

## 25. POM đăng lên repository phải consumable, không chỉ build được ở source tree

Một source POM có thể dùng:

~~~xml
<version>${revision}${changelist}</version>
~~~

trong cơ chế **Maven 3 CI-friendly versions**, hoặc một tập property/BOM/parent phức tạp. Source reactor có thể build được vì properties/local parent có sẵn, nhưng **published POM** cần được consumer ngoài source tree đọc/resolved đúng.

Với Maven 3 CI-friendly versions, Apache Maven hướng dẫn dùng **Flatten Maven Plugin** (ví dụ mode `resolveCiFriendliesOnly`) khi phù hợp để published POM chứa phiên bản đã resolve. Việc flatten phải được cấu hình/test kỹ: **không xóa mất các dependencies cần cho transitive resolution** trong quá trình tạo published descriptor.

Dù dùng plugin nào, kiểm artifact thực tế ở repository:

- POM GAV đúng artifact/JAR.
- `dependencies` giữ những dependency thực sự cần cho consumer.
- `scope`, `optional` và `exclusions` đúng.
- `parent`/BOM imports nếu còn được tham chiếu thì resolve được.
- CI-friendly placeholders hoặc dynamic properties không bị publish sai.
- Sources/Javadocs/signatures/licenses đáp ứng policy kho đích.

**Một JAR được build thành công nhưng POM được publish thiếu dependencies là một release lỗi về metadata.**

## 26. Phân biệt library POM với POM của plugin và build dependency

Maven có hai đồ thị khác nhau cần tách bạch:

- **Project dependencies** dưới `<dependencies>` phục vụ compile/test/runtime của ứng dụng.
- **Plugin dependencies** của Maven plugins phục vụ process build, không phải thư viện Java sẽ tự đi theo mọi consumer khi họ dùng JAR của bạn.

Ví dụ mảnh build plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
    </plugins>
</build>
~~~

`maven-compiler-plugin` dùng lúc compile nhưng **consumer không cần plugin này trên application runtime classpath** chỉ vì library POM có build configuration. Maven có plugin class realms riêng.

Tương tự, nếu library dùng test dependency `junit-jupiter` với `scope=test`, consumer không nên tự nhận JUnit như một production transitive dependency chỉ vì tests của library dùng nó.

Khi phân tích một JAR “tại sao Maven tải thêm file X?”, cần phân biệt **resolver tải build plugin** và **resolver tải project dependency**. `dependency:tree` của consumer tập trung vào project dependencies; debug plugin nên nhìn effective POM/build logs và plugin dependency resolution riêng.

## 27. Dùng dependency:analyze để tránh khai báo trực tiếp thiếu/thừa

Apache Maven Dependency Plugin hỗ trợ goal `analyze`:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:analyze
~~~

Goal phân tích tham chiếu class trong bytecode để phát hiện các trường hợp như:

- Source code trực tiếp dùng classes từ dependency chỉ đi vào **transitively** (*used undeclared*).
- Dependency được khai báo trực tiếp nhưng chương trình không thực sự sử dụng theo phân tích tĩnh (*unused declared*).

Tuy nhiên, analysis dựa trên bytecode có hạn chế với reflection, ServiceLoader, annotation processors, DI framework và dynamic loading. Đừng tự xóa một dependency runtime quan trọng chỉ vì `analyze` báo unused. Hãy đối chiếu POM semantics và behavior.

Với runnable demo, `consumer-app` chỉ import `GreetingService` nên direct dependency greeting-library là đủ; `core-text` là transitive runtime dependency hợp lệ. Nếu consumer bổ sung import `TextNormalizer`, hãy khai báo trực tiếp core-text trong POM consumer để dependency ownership rõ.

## 28. Consumer mới và kiểm thử tách biệt local cache

Nếu chỉ build trên máy tác giả, một `~/.m2/repository` đã có sẵn nhiều artifacts có thể che lỗi publication. Ví dụ tác giả đã tự install `core-text` nhưng quên deploy lên remote; consumer của họ pass, còn một người dùng thật trên máy sạch không resolve được transitive dependency.

Quy trình test release đáng tin:

1. Publish library JAR + **đúng POM** và mọi parent/BOM artifacts cần thiết tới kho staging/test có quyền.
2. Chỉ định một **local repository riêng** khi kiểm consumer, tránh tình cờ dùng artifact đã install ở môi trường dev.
3. Dùng consumer POM chỉ khai báo library trực tiếp.
4. Chạy `dependency:tree`/`copy-dependencies`.
5. Chạy unit/runtime smoke test trên JARs được tải.
6. Kiểm repository manager đã có đúng POM, checksum và release version.

Ví dụ tham số tách local cache:

~~~bash
mvn -B -ntp -Dmaven.repo.local=./isolated-m2 dependency:tree
~~~

Lệnh mang tính minh họa; nó chỉ thành công nếu consumer có thể truy cập các repositories chứa artifact, parent, plugins và dependencies. **Đừng chạy lệnh cô lập cache này trong runnable demo local install ở mục 12 rồi kết luận thư viện bị lỗi**: local install artifacts chỉ nằm trong local repository trước đó, không có trong cache mới.

Trên CI, không phụ thuộc vào những artifacts tồn tại tình cờ trong home directory; ghi rõ repo/mirror settings và version đã phát hành.

## 29. Install so với Deploy trong workflow xuất bản

| Lệnh | Kết quả chính | Phạm vi người dùng |
| --- | --- | --- |
| `mvn package` | Tạo JAR trong `target/`. | Workspace build. |
| `mvn install` | Đưa artifact/POM vào local repository. | Những Maven projects dùng cùng local repo trên máy đó. |
| `mvn deploy` | Deploy artifact/POM lên remote repository theo configuration. | Các clients có quyền và cấu hình resolve remote repo. |
| `install:install-file` | Cài một file artifact tùy chọn, có thể dùng POM cung cấp hoặc generic POM. | Local, cần cẩn thận metadata. |
| `deploy:deploy-file` | Gửi artifact tùy chọn tới remote; có tùy chọn `pomFile`. | Remote, cần permission và POM đúng. |

Với một Maven library có source/POM, thường ưu tiên lifecycle `install`/`deploy` thay vì `install-file`/`deploy-file`; Maven sẽ có POM descriptor từ project thực. Các plugin **không tự bảo đảm** giấy phép hoặc nội dung POM được khai báo đúng: phần đó do chủ dự án chịu trách nhiệm.

**Không chạy `mvn deploy` trong demo** nếu chưa cấu hình `distributionManagement`, repository credentials, namespace và quyền. Remote deploy là hành động phát hành có tác dụng bên ngoài.

Một cấu hình remote repository minh họa (không thuộc POM runnable):

~~~xml
<distributionManagement>
    <repository>
        <id>release-repo</id>
        <url>https://repo.example.org/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>snapshot-repo</id>
        <url>https://repo.example.org/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
~~~

`example.org` là miền ví dụ, không phải endpoints thật. Trong thực tế credentials thường được quản lý trong Maven `settings.xml` hoặc CI secrets, khớp `<id>` tương ứng; **không ghi token/password trực tiếp vào `pom.xml`**.

## 30. Release/SNAPSHOT và tính nhất quán của metadata

Với release `1.0.0`, một repository có chính sách tốt sẽ **không cho overwrite** cùng GAV. Nếu POM publication bị sai dependencies, không nên sửa âm thầm `greeting-library-1.0.0.pom` trên kho release trong khi JAR giữ nguyên mà consumer đã cache bản cũ. Cách thích hợp thường là **phát hành một version mới** và thông báo sửa metadata.

Với `-SNAPSHOT`, remote repository có thể lưu timestamped builds dưới base version; cùng `1.0.1-SNAPSHOT` có thể khác bytes/POM theo lần deploy. Maven metadata ở level version giúp resolver chọn snapshot. Điều này hữu ích trong phát triển nhưng làm consumer khó tái lập nếu không khóa artifacts.

Trước release:

- Đảm bảo các internal và external dependencies của library có versions đã release, theo repository policy.
- Pin plugin/dependency versions khi cần reproducibility.
- Giữ POM và JAR thuộc **cùng source commit/cùng release artifact set**.
- Kiểm parent/BOM và POM transitive dependency GAV đều resolve được.
- Kiểm checksum/signature/artifact provenance theo yêu cầu của kho.
- Nếu release candidate có external mutable SNAPSHOT dependencies, xác định rủi ro và giải quyết theo policy.

Maven Central có các điều kiện riêng cho public release (source/Javadoc/signatures/metadata/namespace); **đọc yêu cầu mới nhất của nhà cung cấp repository** trước khi cấu hình pipeline thật.

## 31. Public publication metadata: những field người dùng thật cần

Một thư viện public nên có đủ metadata mô tả:

| Trường | Vì sao quan trọng |
| --- | --- |
| `name` | Tên thân thiện cho người dùng tìm kiếm/review. |
| `description` | Mô tả chức năng và giới hạn ứng dụng. |
| `url` | Đường dẫn tài liệu/trang chủ có thể truy cập. |
| `licenses/license` | Thông tin giấy phép đúng với quyền phân phối thực tế. |
| `developers/developer` | Đầu mối bảo trì, nhận báo lỗi/đóng góp. |
| `scm/connection`, `scm/url` | Nguồn mã, kiểm tra version/tag tương ứng. |
| `groupId:artifactId:version` | Tọa độ để consumer khai báo. |
| `dependencies` | Danh sách cần cho dependency resolution. |
| `parent` | Nguồn inherited metadata nếu có; phải resolve được. |
| `packaging` | Loại artifact được publish. |

Theo tài liệu chính thức của Sonatype Central, public publishing có thể yêu cầu **sources/Javadoc JAR, chữ ký và thông tin POM** theo chính sách hiện hành. **Ví dụ local trong bài không phải một upload package hoàn chỉnh lên Central**, vì nó dùng tọa độ/example URLs và chỉ minh họa metadata fields.

**Tách hai khái niệm:** khai báo đẹp ở `<name>`, `<description>` chưa đủ để Maven tải dependencies; và khai báo đúng dependencies chưa chắc đủ để kho public chấp nhận publication nếu thiếu license/developers/SCM/signatures.

## 32. Fat JAR, shaded JAR và POM transitive dependencies

Một số thư viện đóng gói **uber-JAR** (Shade/Assembly), khiến classes từ third-party dependencies được nhúng trực tiếp trong một JAR. Điều này **không tự động có nghĩa** POM được publish phải xóa mọi dependency, hay Maven consumer không còn dùng transitive resolution.

Có các tình huống:

1. **Library JAR bình thường:** dependencies được giữ là JARs riêng, POM khai báo đầy đủ.
2. **Application executable uber-JAR:** thường dành cho chạy độc lập; POM deployment cho app có mục tiêu khác library consumer.
3. **Shaded library:** phụ thuộc được relocate/nhúng; phải quyết định thông tin POM publication, classifier và dependency-reduced POM **theo chính xác cấu hình plugin**, tránh double inclusion hoặc class conflicts.

**Đừng phát hành một JAR có classes đã nhúng rồi đồng thời để POM kê khai dependency một cách máy móc**, khiến consumer nhận cả bản classes bên trong JAR và bản dependency riêng ngoài JAR. Ngược lại, cũng không bỏ dependencies cần thiết khỏi POM chỉ vì một số JARs đã được bundle.

Với bài này, **không dùng Shade/Assembly**: hai JAR core-text và greeting-library vẫn là artifacts riêng, nên consumer graph minh bạch và bài học transitive dependency được thể hiện trực tiếp.

## 33. Troubleshooting: consumer tải sai hoặc thiếu dependency

| Triệu chứng | Nguyên nhân có thể | Hướng chẩn đoán |
| --- | --- | --- |
| `Could not find artifact greeting-library:1.0.0`. | Library mới install local máy tác giả, chưa deploy remote hoặc repo URL/quyền sai. | Kiểm GAV, repository và publication. |
| Consumer thấy greeting-library nhưng không thấy core-text trong tree. | Library POM thiếu `dependencies`, core-text bị optional/test/provided hoặc consumer exclude. | Đọc **published POM** và `dependency:tree`. |
| `NoClassDefFoundError: TextNormalizer` khi chạy Java thủ công. | Runtime classpath thiếu core-text JAR. | Dùng `copy-dependencies` và wildcard classpath, kiểm effective scope. |
| Generic POM chỉ có GAV. | Dùng `generatePom=true` thay POM nguồn có dependencies. | Publish POM thật, version release mới nếu cần. |
| `Non-resolvable parent POM`. | Published library POM tham chiếu parent private/missing/wrong version. | Publish parent đúng GAV hoặc thiết kế descriptor consumable. |
| `Non-resolvable import POM`. | BOM dependencyManagement chưa publish/có repo access. | Kiểm BOM GAV/repository credentials. |
| Consumer dùng core-text version khác tác giả. | Dependency mediation/management override hoặc conflicts. | Kiểm `dependency:tree`, effective POM, versions. |
| Thêm `dependencyManagement` nhưng library vẫn thiếu C. | Management không tạo dependency thật. | Thêm `core-text` vào library `<dependencies>`. |
| `provided` dependency không đến consumer. | Scope không transitive theo matrix. | Đặt scope theo runtime contract hoặc yêu cầu container cung cấp. |
| Bật `optional=true` gây runtime thiếu C. | Consumer không nhận optional dependency. | Cho consumer khai báo trực tiếp hoặc sửa API/library contract. |
| Exclusion không xóa C khỏi toàn graph. | C đi vào qua một nhánh khác. | Xem các đường trong dependency tree và Enforcer rules. |
| Thư viện build pass trên máy tác giả, fail trên CI mới. | Cache local chứa missing parent/BOM/library. | Test với repo sạch/staging và source artifacts đúng. |
| CI consumer tải version SNAPSHOT khác. | Metadata/updatePolicy thay phiên bản resolved. | Pin release hoặc ghi snapshot timestamp/provenance. |
| JAR được publish nhưng không có `-sources.jar`. | Chưa cấu hình Maven Source Plugin/publication yêu cầu. | Bổ sung sources/javadoc packaging theo policy. |
| Maven Central từ chối upload. | Thiếu metadata, signatures, namespace hoặc files policy. | Đối chiếu yêu cầu hiện hành của Central/portal. |
| `dependency:analyze` báo unused nhưng runtime fail khi xóa dependency. | Reflection/ServiceLoader/dynamic loading không hiện rõ trong static analysis. | Review code và test runtime/feature path. |
| Java JAR đã compile nhưng Maven plugin vẫn tải thêm artifacts. | Nhầm project dependencies và plugin dependencies. | Xem logs plugin resolution riêng. |

**Thứ tự điều tra:** consumer POM → artifact GAV/remote availability → **published library POM** → parent/BOM availability → dependency scopes/optional/exclusions → mediation → runtime classpath → CI/cache/repository policy.

## 34. Quy trình QA trước khi publish một library dùng lại được

**Bước 1 — Kiểm binary.** Compile, unit tests, integration tests, Java target/JDK compatibility, public API surface.

**Bước 2 — Kiểm POM nguồn.** Đúng GAV, packaging, name/description/license/developers/SCM, dependencies trực tiếp, scopes, optional flags và exclusions.

**Bước 3 — Kiểm model.** Dùng `help:effective-pom` để biết parent/BOM/properties resolution và xem dependency tree của library.

**Bước 4 — Cài thử local.** `mvn clean install`, đọc JAR/POM trong local repository. Không dùng install-file generic POM nếu source POM có dependencies thật.

**Bước 5 — Consumer smoke test.** Một project ngoài reactor chỉ khai báo library làm direct dependency; dùng `dependency:tree` và runtime test để xác minh transitive deps. Với public publication, thử bằng local cache riêng và remote staging.

**Bước 6 — Kiểm remote repository.** POM, JAR, sources/javadoc/signatures/checksum, parent/BOM và mọi transitive artifact đều available theo quyền truy cập thực tế.

**Bước 7 — Chốt release.** Nếu có vấn đề metadata, sửa trước khi phát hành; nếu release đã immutable, dùng version mới theo chính sách thay vì lặng lẽ ghi đè cùng GAV.

Mẫu lệnh kiểm:

~~~bash
mvn -B -ntp -f core-text/pom.xml clean install
mvn -B -ntp -f greeting-library/pom.xml clean install
mvn -B -ntp -f consumer-app/pom.xml clean package
mvn -B -ntp -f consumer-app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Sau đó, từ `consumer-app/`, dùng `copy-dependencies` và `java -cp` như mục 14. Không có lệnh nào trong checklist này tự xuất bản remote artifact.

## 35. Các câu hỏi tự kiểm tra

1. **Tại sao chỉ copy JAR lên repository là chưa đủ cho một Maven library?**  
   Vì consumer cần POM artifact để biết project metadata và dependencies bắc cầu.

2. **`maven-metadata.xml` có chứa trực tiếp danh sách core-text dependencies của greeting-library không?**  
   Không; dependencies nằm trong POM artifact.

3. **Consumer khai báo greeting-library, core-text có tự xuất hiện không?**  
   Có nếu POM thư viện khai báo dependency phù hợp, scope/optional/exclusion không chặn và artifact resolve được.

4. **`dependencyManagement` trong POM của thư viện có tự thêm core-text cho consumers không?**  
   Không; phải có dependency thực tế.

5. **Core-text scope test trong library có truyền sang app runtime không?**  
   Không; test scope không là production transitive dependency.

6. **`optional=true` có nghĩa “Maven sẽ luôn tải dependency khi chạy” không?**  
   Không; consumer không tự nhận optional dependency từ library.

7. **Exclusion có xóa một GAV khỏi mọi đường dẫn graph không?**  
   Không mặc định; exclusions gắn trên quan hệ dependency cụ thể.

8. **Khi nhiều versions cùng xuất hiện transitively, Maven chọn thế nào?**  
   Maven 3 có cơ chế nearest definition, cùng độ sâu xét thứ tự declaration; consumer management/direct declaration có thể chi phối.

9. **Nếu library được publish kèm POM có parent, consumer cần gì?**  
   Parent POM đúng version phải resolve được để dựng effective model.

10. **Vì sao `install:install-file -DgeneratePom=true` có thể làm mất transitive dependency?**  
    Generic POM thường chỉ chứa GAV/packaging mà không biết dependencies thực.

11. **`mvn install` có tạo remote artifact cho đồng đội không?**  
    Không; install là local repository, deploy mới là remote publication.

12. **Người dùng chỉ khai báo greeting-library, có cần copy cả core-text JAR khi chạy Java thủ công không?**  
    Có nếu library sử dụng core-text tại runtime; Maven resolution không tự thiết lập `java -cp` do người dùng viết tay.

13. **Vì sao consumer nên khai báo một library trực tiếp nếu source code thực sự import type của nó?**  
    Vì rõ dependency ownership và không phụ thuộc tình cờ vào graph transitive của thư viện khác.

14. **`<plugin>maven-compiler-plugin</plugin>` trong published POM có biến thành runtime dependency của app không?**  
    Không; build plugin và project dependency classpath là hai thế giới riêng.

15. **Làm sao xác nhận bản POM trên remote đúng hơn bản POM trong workspace tác giả?**  
    Inspect published POM hoặc thử consumer từ staging/fresh local cache, kiểm tree và runtime.

16. **Một release library có external SNAPSHOT dependency có thể mất tính tái lập không?**  
    Có, nếu snapshot mutable được đổi qua thời điểm.

17. **Vì sao không sửa đè release POM sau khi public?**  
    Vì các clients có thể cache descriptor cũ, dẫn tới cùng GAV có graph khác nhau; phát hành version mới là quy trình an toàn hơn.

18. **Các trường name/description/license/SCM có thay thế dependency metadata không?**  
    Không; chúng là thông tin dành cho hệ sinh thái và con người, còn `dependencies` quyết định graph.

## 36. Checklist nhanh cho người viết và người dùng thư viện

- [ ] GAV, packaging và version của JAR trùng published POM.
- [ ] POM của library có `<dependencies>` đúng với code thật.
- [ ] Không để chỉ có generic POM nếu thư viện có dependencies bắt buộc.
- [ ] Scope compile/runtime/provided/test phản ánh classpath contract.
- [ ] Optional/exclusions là quyết định có chủ đích, không làm hỏng use case chính.
- [ ] BOM/parent POM được phát hành hoặc resolve được với đúng version.
- [ ] Metadata name/description/url/licenses/developers/scm đúng thực tế.
- [ ] External dependencies dùng versions có thể resolve từ kho được phép.
- [ ] Release artifacts immutable; snapshot update policy được hiểu đúng.
- [ ] Không dùng `systemPath` cho library cần portable distribution.
- [ ] Người tiêu dùng không phải phụ thuộc local cache tình cờ của tác giả.
- [ ] Có consumer test **ngoài reactor**, dùng dependency:tree và runtime smoke.
- [ ] Dùng `dependency:analyze` có kiểm lại reflection/runtime paths.
- [ ] Dùng Maven deploy lifecycle hoặc deploy-file kèm POM thật, không gây mất metadata.
- [ ] Cần sources/Javadoc/signatures khi repository đích yêu cầu.
- [ ] Khi Shade/uber-JAR được dùng, published POM phản ánh artifact packaging thật.
- [ ] Không tự cho rằng Maven build plugins là transitive dependencies của library.
- [ ] Chỉ công bố sau khi consumer từ repository sạch resolve graph và chạy được.

## 37. Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, mediation, scopes, exclusions, optional và management.
- [Apache Maven — Introduction to Optional and Excludes Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies): semantics của optional và exclusions.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): dependencies, metadata, parent, dependencyManagement, repository.
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): POM model, effective inheritance và cấu trúc project.
- [Apache Maven — Frequently Asked Questions About Project Metadata](https://maven.apache.org/project-faq.html): vì sao metadata và dependencies trong published POM phải đúng.
- [Apache Maven — Maven Repositories](https://maven.apache.org/repositories/): repository layout và artifacts.
- [Apache Maven — Maven Metadata](https://maven.apache.org/repositories/metadata.html): phân biệt repository metadata với POM artifact.
- [Apache Maven — Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/): install/install-file và local publication.
- [Apache Maven — Generating a Generic POM](https://maven.apache.org/components/plugins/maven-install-plugin/examples/generic-pom-generation.html): giới hạn của một POM tự sinh tối thiểu.
- [Apache Maven — Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/): deploy lifecycle, deploy-file và remote artifacts.
- [Apache Maven — Disable the Generation of Generic POM](https://maven.apache.org/plugins/maven-deploy-plugin/examples/disabling-generic-pom.html): `generatePom` với deploy-file.
- [Apache Maven — Dependency Plugin, tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): kiểm graph đã resolve.
- [Apache Maven — Dependency Plugin, copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): gom runtime JARs để kiểm dùng thực tế.
- [Apache Maven — Dependency Plugin, analyze](https://maven.apache.org/plugins/maven-dependency-plugin/analyze-mojo.html): cảnh báo used undeclared và unused declared.
- [Apache Maven — Maven CI Friendly Versions](https://maven.apache.org/guides/mini/guide-maven-ci-friendly.html): published POM khi dùng revision/changelist.
- [Sonatype Central — Publishing Requirements](https://central.sonatype.org/publish/requirements/): yêu cầu POM metadata/sources/Javadoc/signatures của kho công khai.

**Kết luận:** Khi xuất bản một Maven library, **JAR cung cấp mã chạy, còn POM cung cấp hợp đồng dependency cho consumer**. Trong ví dụ, consumer chỉ khai báo greeting-library, nhưng Maven vẫn resolve core-text nhờ `<dependencies>` trong POM đã install/deploy của greeting-library. Hãy kiểm graph, scopes, optional/exclusions, parent/BOM và published POM thực tế; **đừng để một generic POM hoặc thư viện chỉ có JAR làm mất phụ thuộc bắc cầu**. Một release đáng tin cần binary, POM và các artifacts tham chiếu nhất quán, có thể resolve trên môi trường consumer sạch.
