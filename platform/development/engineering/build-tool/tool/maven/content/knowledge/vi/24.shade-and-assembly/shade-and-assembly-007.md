# Dependency-reduced POM và ảnh hưởng đến dự án tiêu thụ

Khi xây dựng ứng dụng hoặc thư viện Java bằng Maven, dự án thường khai báo các dependency trong `pom.xml`. Maven sử dụng những khai báo đó để tải thư viện cho quá trình biên dịch, kiểm thử và thực thi, đồng thời công bố thông tin phụ thuộc cho các **dự án tiêu thụ (consumer projects)** khi artifact được phát hành.

**Maven Shade Plugin** cho phép gộp một phần hoặc toàn bộ bytecode/resources của các dependency vào JAR chính (*uber JAR*, *shaded JAR*), tùy chọn đổi tên package (*relocation*). Khi thư viện đã nằm trong JAR kết quả, consumer có thể **không cần Maven tải JAR thư viện đó như một dependency riêng**. Để metadata phát hành phản ánh thực tế này, Shade Plugin có chức năng tạo **dependency-reduced POM**.

Trong **Maven Shade Plugin 3.6.2**, tham số `createDependencyReducedPom` mặc định là `true`. Khi bật, Shade tạo file `dependency-reduced-pom.xml`, trong đó các dependencies đã được đưa vào shaded JAR có thể được loại khỏi danh sách `<dependencies>`. Trong luồng build/install/deploy thông thường, POM rút gọn này có thể trở thành metadata mà consumer sử dụng để resolve artifact đã shading.

**Bốn nguyên tắc nền tảng:**

1. **Source POM khác published POM.** Producer vẫn phải khai báo các dependencies cần để compile. POM rút gọn là đầu ra build, không phải nguồn cần chỉnh tay.
2. **Giảm POM khác giảm kích thước JAR.** File `dependency-reduced-pom.xml` mô tả dependency graph; `minimizeJar` là cơ chế khác, liên quan classes được giữ trong shaded JAR.
3. **Một POM và nhiều biến thể JAR có thể gây xung đột hợp đồng.** Khi Shade thay main JAR, giảm metadata thường phù hợp; khi shaded JAR chỉ được attach bằng classifier, main JAR có thể vẫn cần dependency gốc.
4. **Phải thử consumer độc lập.** Producer build thành công không có nghĩa artifact đã publish đủ bytecode, resources và metadata để một dự án khác chạy đúng.

Mục tiêu bài học: hiểu cơ chế `shade:shade`, so sánh original/reduced/installed/embedded POM, thực hành một **producer/consumer Java 17 chạy được**, kiểm chứng bằng `jar --list`, `dependency:tree`, unit test và Java launcher, nắm sự khác nhau giữa Shade và Assembly, tránh lỗi metadata khi phát hành nhiều artifacts.

## 1. Maven dependency graph trước và sau Shade

Một thư viện `message-bundle` sử dụng Commons Lang có source POM:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

Trước shading, consumer nhận một thư viện chưa đóng gói Commons Lang bên trong:

```text
consumer-app
  |
  +-- message-bundle:1.0.0
         |
         +-- commons-lang3:3.14.0
```

Maven sẽ resolve `commons-lang3` nếu các dependency scope và mediation rules của consumer cho phép. Đó là hành vi đúng: bytecode thư viện `message-bundle` dùng các class `org.apache.commons.lang3.*` và cần JAR Commons Lang trên runtime classpath.

Sau khi Shade gộp và relocate Commons Lang, shaded JAR có thể chứa:

```text
message-bundle-1.0.0.jar
  |
  +-- dev/training/shade/api/MessageFacade.class
  +-- dev/training/shade/internal/lang3/StringUtils.class
  +-- ... các class/resources Commons Lang được chọn ...
```

Về nguyên tắc, consumer chỉ cần shaded `message-bundle-1.0.0.jar` để dùng API `MessageFacade`. Nếu published POM vẫn liệt kê Commons Lang ở scope compile/runtime, Maven có thể tải thêm JAR Commons Lang gốc, dù dependency đã nằm trong shaded JAR. POM rút gọn giúp ngăn sự phụ thuộc transitively không còn thiết yếu đó.

**Không diễn giải quá mức:** dependency biến mất khỏi Maven graph **không đồng nghĩa bytecode bị xóa khỏi sản phẩm**. Code Commons Lang vẫn có thể nằm trong shaded JAR dưới namespace mới; vẫn cần theo dõi license, SBOM và vulnerabilities của bản thư viện được nhúng.

## 2. Bốn POM cần phân biệt

| File hoặc đối tượng | Thông thường nằm ở đâu? | Được dùng cho mục đích gì? |
| --- | --- | --- |
| **Source POM** | `producer/pom.xml` | Compile/test/package producer với dependencies gốc. |
| **Dependency-reduced POM** | `producer/dependency-reduced-pom.xml` | Metadata được Shade sinh, phản ánh dependencies đã gộp. |
| **Installed/published POM** | Maven repository: `.../message-bundle-1.0.0.pom` | Nguồn metadata để consumer resolve artifact và transitive dependencies. |
| **Embedded POM** | Bên trong JAR: `META-INF/maven/<group>/<artifact>/pom.xml` | Metadata được archive mang theo; không mặc định là nơi Maven Resolver lấy dependency graph. |

Quy trình:

```text
Source POM
    |
    +-- Maven compiler/test/JAR
    |        |
    |        +-- compiled classes và JAR gốc
    |
    +-- shade:shade ở phase package
             |
             +-- shaded main JAR (hoặc attached classifier)
             |
             +-- dependency-reduced-pom.xml
                         |
                  Maven install/deploy
                         |
             Repository: artifact.jar + artifact.pom
                         |
                  Consumer resolves metadata
```

Điểm thường gây nhầm:
- Nếu chỉ mở JAR xem `META-INF/maven/.../pom.xml`, có thể vẫn thấy POM gốc.
- Tham số `useDependencyReducedPomInJar` điều khiển POM nhúng, **khác** `createDependencyReducedPom`.
- Với luồng chuẩn, file `.pom` nằm cạnh JAR trong Maven repository quan trọng hơn đối với dependency resolution của consumer.
- Khi đánh giá kết quả, hãy kiểm tra **cả reduced POM được sinh lẫn published POM thực tế**, không giả định chỉ vì generated file tồn tại thì đã được deploy đúng.

## 3. Cấu hình cơ bản của Maven Shade Plugin

Đoạn trong `<build><plugins>` của POM:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>shade-distribution</id>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <createDependencyReducedPom>true</createDependencyReducedPom>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây chỉ là **plugin snippet**, không phải toàn bộ `pom.xml`. Goal `shade:shade` có default phase `package`, nhưng vẫn cần một execution/binding hoặc gọi goal có chủ đích. Bật `createDependencyReducedPom=true` là tường minh; giá trị mặc định của tham số trong 3.6.2 vốn là `true`.

Shade có thể:
- Chọn dependencies để gộp qua `artifactSet`.
- Lọc nội dung JAR qua `filters`.
- Relocate classes/resources bằng `relocations`.
- Hợp nhất service descriptors và manifest qua `transformers`.
- Thu gọn class content qua `minimizeJar`.
- Sinh reduced POM.
- Thay main JAR hoặc attach JAR có classifier.

**Không tự động có nghĩa** Shade sẽ làm cho một thư viện bất kỳ thành một executable JAR có `Main-Class`. Nếu tạo ứng dụng chạy bằng `java -jar`, cần cấu hình manifest và kiểm tra runtime. Lab bên dưới xây **thư viện có shaded dependency**, nên dùng `java -cp` thay vì đòi executable manifest trong producer.

### 3.1. createDependencyReducedPom=true

Khi một dependency đã được chọn và đưa vào uber JAR, goal có thể loại nó khỏi `<dependencies>` trong generated reduced POM theo tài liệu plugin. Điều này giảm dependency graph mà consumer nhìn thấy. Nó **không sửa Java imports trong source code** và cũng không khiến Maven Compiler Plugin không cần dependency đó.

### 3.2. createDependencyReducedPom=false

```xml
<configuration>
    <createDependencyReducedPom>false</createDependencyReducedPom>
</configuration>
```

Khi tắt, plugin không sinh reduced POM theo cơ chế đó. Việc này có thể hữu ích nếu artifact chính vẫn cần dependency gốc, chẳng hạn **JAR chính unshaded và shaded JAR chỉ là classifier phụ**. Tuy nhiên nếu main JAR đã chứa relocated dependency, consumer có thể bị kéo thêm dependency gốc không cần thiết.

### 3.3. Không xóa hết dependencies một cách máy móc

Reduced POM không phải “POM không có dependencies”. Project có thể:
- Chỉ shade một tập con dependency.
- Giữ dependency cần ở runtime bên ngoài.
- Có dependency `provided` do container/JDK/platform cung cấp.
- Có dependency API public không thích hợp để relocate.
- Dùng service provider/native library cần artifact riêng.
- Có transitive dependencies cần promote theo hợp đồng được thiết kế.

Nếu loại sai dependency, consumer có thể compile hoặc run lỗi, dù producer từng build thành công.

## 4. Lab Java 17 với hai dự án độc lập

Ta sử dụng **producer** tên `message-bundle`, phụ thuộc Commons Lang 3.14.0 để định dạng lời chào, và **consumer** tên `consumer-app`. Producer shade và relocate Commons Lang rồi install artifact. Consumer được build như một Maven project riêng để kiểm chứng dependency metadata ở local repository.

Sơ đồ thư mục:

```text
shade-reduced-lab/
├── producer/
│   ├── pom.xml
│   └── src/main/java/dev/training/shade/api/
│       └── MessageFacade.java
└── consumer/
    ├── pom.xml
    ├── src/main/java/dev/training/consumer/
    │   └── ConsumerApp.java
    └── src/test/java/dev/training/consumer/
        └── ConsumerAppTest.java
```

**Yêu cầu:** JDK 17+, Maven 3.6.3+ phù hợp các plugin đã ghim, có quyền ghi local Maven repository và có thể tải dependencies/plugins từ Maven Central hoặc mirror hợp lệ nếu chưa có cache. Ví dụ cố ý không có root aggregator POM; các lệnh dùng `-f` để chọn producer hoặc consumer.

### 4.1. Chuẩn bị source directories

Linux/macOS:

```bash
mkdir -p shade-reduced-lab/producer/src/main/java/dev/training/shade/api
mkdir -p shade-reduced-lab/consumer/src/main/java/dev/training/consumer
mkdir -p shade-reduced-lab/consumer/src/test/java/dev/training/consumer
cd shade-reduced-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "shade-reduced-lab/producer/src/main/java/dev/training/shade/api" | Out-Null
New-Item -ItemType Directory -Force -Path "shade-reduced-lab/consumer/src/main/java/dev/training/consumer" | Out-Null
New-Item -ItemType Directory -Force -Path "shade-reduced-lab/consumer/src/test/java/dev/training/consumer" | Out-Null
Set-Location shade-reduced-lab
```

Các lệnh sau giả định current directory là `shade-reduced-lab`.

### 4.2. POM đầy đủ của producer

Tệp `producer/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.shade</groupId>
    <artifactId>message-bundle</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>

    <build>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>bundle-runtime</id>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <createDependencyReducedPom>true</createDependencyReducedPom>
                            <shadedArtifactAttached>false</shadedArtifactAttached>
                            <minimizeJar>false</minimizeJar>

                            <artifactSet>
                                <includes>
                                    <include>org.apache.commons:commons-lang3</include>
                                </includes>
                            </artifactSet>

                            <relocations>
                                <relocation>
                                    <pattern>org.apache.commons.lang3</pattern>
                                    <shadedPattern>dev.training.shade.internal.lang3</shadedPattern>
                                </relocation>
                            </relocations>

                            <filters>
                                <filter>
                                    <artifact>*:*</artifact>
                                    <excludes>
                                        <exclude>META-INF/*.SF</exclude>
                                        <exclude>META-INF/*.DSA</exclude>
                                        <exclude>META-INF/*.RSA</exclude>
                                    </excludes>
                                </filter>
                            </filters>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích chính:
- Producer cần `commons-lang3` trên compile classpath vì Java source sẽ import `StringUtils`.
- `<artifactSet>` chọn một dependency để đưa vào shaded JAR.
- `<relocations>` đổi package của Commons Lang trong output sang namespace nội bộ. Điều này giúp tránh trùng class giữa Commons Lang gốc và code đã được gộp.
- `<shadedArtifactAttached>false</shadedArtifactAttached>` là mode **thay main artifact**, không tạo riêng artifact có classifier.
- `<createDependencyReducedPom>true</createDependencyReducedPom>` tạo metadata đã giảm.
- `<minimizeJar>false</minimizeJar>` tránh loại nhầm classes khi đang kiểm chứng POM. Đây là chọn lựa cho lab, không phải mệnh lệnh cho mọi build.
- Filters bỏ một số chữ ký archive cũ có thể trở nên vô hiệu khi gộp JAR. **Không nên loại sạch toàn bộ `META-INF`**, vì license, notices và service descriptors có thể quan trọng.

### 4.3. Java source của producer

Tệp `producer/src/main/java/dev/training/shade/api/MessageFacade.java`:

```java
package dev.training.shade.api;

import org.apache.commons.lang3.StringUtils;

public final class MessageFacade {

    private MessageFacade() {
    }

    public static String message(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + StringUtils.capitalize(name.strip()) + "!";
    }
}
```

Đây là class Java 17 hoàn chỉnh. Producer **biên dịch bằng tên package Commons Lang gốc**, còn Shade thay đổi references trong bytecode đã đóng gói. Public API trả về `String`, không để lộ kiểu của Commons Lang trong method signature, nhờ vậy consumer không phải import implementation detail.

Nếu public API của bạn trả về `org.apache.commons.lang3.tuple.Pair` hoặc một class của dependency bị relocate, shading có thể làm đổi public binary contract và gây lỗi cho consumer. Đó là vấn đề thiết kế API, **không phải thứ mà reduced POM có thể sửa bằng cách xóa dependency**.

### 4.4. Build và install producer

Từ thư mục root lab:

```bash
mvn -version
mvn -B -ntp -f producer/pom.xml clean install
```

Trong lần build thành công:
1. Maven resolve `commons-lang3:3.14.0` để compile.
2. Compiler Plugin biên dịch `MessageFacade`.
3. JAR Plugin tạo main JAR.
4. Shade Plugin chạy ở `package`, gộp/relocate Commons Lang và **thay main JAR**.
5. Shade tạo `producer/dependency-reduced-pom.xml`.
6. Install Plugin lưu JAR đã shading và POM thích hợp vào local repository.

Các file có ý nghĩa:

```text
producer/pom.xml
producer/dependency-reduced-pom.xml
producer/target/message-bundle-1.0.0.jar
```

Shade có thể lưu thêm bản JAR cũ mang tên dạng `original-message-bundle-1.0.0.jar` tùy mode/configuration. **Không dùng bản gốc đó làm artifact chính đã publish**.

### 4.5. So sánh source với reduced POM

Trong **source POM**, phần dependencies có:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
```

Sau shading theo lab, phần dependencies có ý nghĩa cho consumer trong **reduced POM** không còn dependency Commons Lang bình thường, vì bytecode đã được đưa vào shaded artifact. Một hình thức XML khái niệm:

```xml
<dependencies/>
```

**Đây chỉ là snippet minh họa phần dependencies, không phải toàn bộ POM generated.** Generated POM có thể vẫn chứa tên `commons-lang3` trong cấu hình `<artifactSet>` của Shade Plugin. Vì vậy **không chỉ tìm chuỗi `commons-lang3` trên toàn bộ file**; hãy kiểm tra đúng các `<dependency>` entries.

### 4.6. Kiểm tra bytecode thực trong shaded JAR

```bash
jar --list --file producer/target/message-bundle-1.0.0.jar
```

Trong các entries của JAR, cần tìm:

```text
dev/training/shade/api/MessageFacade.class
dev/training/shade/internal/lang3/StringUtils.class
```

Đây là các entry tiêu biểu, không phải danh sách đầy đủ. Nếu JAR không chứa `StringUtils.class` trong package relocated, xem plugin execution, filters, `artifactSet`, `relocations`, đúng file main JAR và Maven build log.

Nếu JAR có đủ class nhưng POM vẫn kéo Commons Lang ở consumer, bạn mới xác minh được **phần vật lý**, chưa xác minh metadata phát hành.

### 4.7. Kiểm tra published POM trong local repository

Với local repository mặc định, producer artifact có thể được cài tại:

```text
~/.m2/repository/dev/training/shade/message-bundle/1.0.0/
    message-bundle-1.0.0.jar
    message-bundle-1.0.0.pom
```

Trên Windows hoặc khi Maven settings thay đổi local repository, đường dẫn thực có thể khác. Hãy đọc **file `message-bundle-1.0.0.pom`** cạnh JAR, so sánh nó với `producer/dependency-reduced-pom.xml` và source POM. File repository POM này mới là nguồn metadata một consumer độc lập sẽ resolve theo Maven rules.

Không suy ra published POM bằng cách giải nén `META-INF/maven/.../pom.xml` bên trong JAR: Shade có tùy chọn riêng `useDependencyReducedPomInJar` cho embedded metadata.

## 5. Consumer độc lập: compile và chạy không cần Commons Lang JAR riêng

### 5.1. Consumer POM đầy đủ

Tệp `consumer/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.consumer</groupId>
    <artifactId>consumer-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.training.shade</groupId>
            <artifactId>message-bundle</artifactId>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Consumer **không khai báo `commons-lang3`**. Nó chỉ dùng API của producer. JUnit Jupiter có `scope=test` nên không cần khi chạy production main class. Vì hai POM được build riêng, kết quả giúp kiểm tra **metadata đã install**, thay vì phụ thuộc vào Maven reactor state đang giữ producer project model trong memory.

### 5.2. Java main của consumer

Tệp `consumer/src/main/java/dev/training/consumer/ConsumerApp.java`:

```java
package dev.training.consumer;

import dev.training.shade.api.MessageFacade;

public final class ConsumerApp {

    private ConsumerApp() {
    }

    public static void main(String[] args) {
        System.out.println(MessageFacade.message("maven"));
    }
}
```

Đây là Java class đầy đủ có `main()`. Nó không import class Commons Lang, chỉ gọi `MessageFacade`.

### 5.3. JUnit Jupiter consumer test

Tệp `consumer/src/test/java/dev/training/consumer/ConsumerAppTest.java`:

```java
package dev.training.consumer;

import org.junit.jupiter.api.Test;
import dev.training.shade.api.MessageFacade;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ConsumerAppTest {

    @Test
    void formatsMessageViaShadedDependency() {
        assertEquals("Hello, Maven!", MessageFacade.message("maven"));
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(IllegalArgumentException.class,
            () -> MessageFacade.message("  "));
    }
}
```

Hai tests kiểm tra public API của producer từ **dự án khác**, điều mà chỉ build producer không chứng minh. Tên `ConsumerAppTest` khớp naming convention mặc định của Surefire.

### 5.4. Build consumer

Sau khi producer được install thành công:

```bash
mvn -B -ntp -f consumer/pom.xml clean verify
```

Surefire của consumer sẽ chạy **2 unit tests**. Dòng thống kê kỳ vọng:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Đây không phải toàn bộ stdout Maven; console còn có plugin headers, prefixes, timestamps/timings và các dòng khác tùy môi trường.

### 5.5. Chạy Java main chỉ với main classes và shaded producer JAR

Linux/macOS, tại root lab:

```bash
java -cp "consumer/target/classes:producer/target/message-bundle-1.0.0.jar" dev.training.consumer.ConsumerApp
```

Windows PowerShell:

```powershell
java -cp "consumer\target\classes;producer\target\message-bundle-1.0.0.jar" dev.training.consumer.ConsumerApp
```

**Stdout chính xác của ứng dụng:**

```text
Hello, Maven!
```

Không thêm `commons-lang3-3.14.0.jar` vào runtime classpath. Nếu shaded producer JAR đã chứa thư viện được relocate, chương trình vẫn chạy. Dùng `java -cp` thay vì `java -jar` vì consumer JAR mặc định chưa có `Main-Class` và không tự gộp dependency producer.

### 5.6. Xem Maven dependency tree ở consumer

```bash
mvn -B -ntp -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Cây của consumer có dependency trực tiếp `message-bundle:1.0.0` và JUnit test dependencies. Với published reduced POM đúng, **không nên có dependency Commons Lang được kéo qua `message-bundle`**.

Lọc vào artifact cần kiểm tra:

```bash
mvn -B -ntp -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree "-Dincludes=org.apache.commons:commons-lang3"
```

Output khi không có match tùy phiên bản plugin; không trông chờ một dòng stdout cố định. Nếu Commons Lang vẫn xuất hiện, cần phân biệt nó đến từ `message-bundle` hay một dependency **khác** của consumer.

### 5.7. Ba kiểm tra phải đi cùng nhau

| Kiểm tra | Câu hỏi được trả lời |
| --- | --- |
| `jar --list` trên shaded producer JAR | Class/bytecode đã được gộp và relocate thật chưa? |
| Repository POM và `dependency:tree` | Dependency đã được giảm trong published metadata chưa? |
| Consumer tests + `java -cp` | Consumer chạy được với classpath dự kiến không? |

**Chỉ thấy dependency biến mất khỏi tree chưa phải thành công**. Nó cũng có thể biến mất do cấu hình sai khiến consumer thiếu class runtime.

## 6. Nếu không tạo dependency-reduced POM thì sao?

Khi đặt:

```xml
<createDependencyReducedPom>false</createDependencyReducedPom>
```

cho producer **shaded main JAR**, published metadata có thể vẫn giữ `commons-lang3` ở scope compile. Consumer có thể nhận hai bộ code:
1. Bytecode Commons Lang đã relocate trong shaded `message-bundle.jar`.
2. JAR Commons Lang gốc tải transitively theo published POM.

Do relocation, hai namespace khác nhau nên lab có thể vẫn chạy, nhưng graph lớn hơn dự kiến và có thể ảnh hưởng mediation, audit/SBOM hoặc class/resource collisions trong hệ thống phức tạp.

**Không thay flag rồi deploy đè một release bất biến cùng GAV vào remote repository.** Khi thực nghiệm so sánh hai chính sách, dùng version hoặc coordinates riêng để kết quả có thể truy vết chính xác.

Khi `createDependencyReducedPom=false` có chủ đích, hãy giải thích vì sao artifact consumer vẫn cần original dependency declarations; điều đó đặc biệt quan trọng với mô hình **shaded classifier phụ**.

## 7. Shaded artifact chính và attached artifact có classifier

Theo tài liệu Shade Plugin, mặc định `shadedArtifactAttached=false`: plugin **thay JAR chính của project** bằng shaded JAR. Điều này phù hợp với lab, nơi main JAR đã chứa Commons Lang và consumer dùng dependency thông thường không classifier.

Khi muốn vừa giữ main JAR gốc vừa tạo shaded artifact:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>attach-shaded-jar</id>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
                <shadedArtifactAttached>true</shadedArtifactAttached>
                <shadedClassifierName>all</shadedClassifierName>
                <createDependencyReducedPom>false</createDependencyReducedPom>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **cấu hình thay thế để minh họa**, không phải phần bổ sung nên chép nguyên xi vào lab. Kết quả theo convention:

```text
message-bundle-1.0.0.jar       (main JAR chưa shade)
message-bundle-1.0.0-all.jar   (shaded JAR có classifier all)
```

Consumer chọn shaded classifier:

```xml
<dependency>
    <groupId>dev.training.shade</groupId>
    <artifactId>message-bundle</artifactId>
    <version>1.0.0</version>
    <classifier>all</classifier>
    <type>jar</type>
</dependency>
```

**Điểm dễ sai:** các artifact cùng `groupId:artifactId:version` nhưng khác classifier thông thường **chia sẻ một published POM của project**. Không giả định có POM độc lập cho classifier `all`. Nếu giảm POM chung, consumer lấy **main JAR unshaded** có thể **mất transitively dependency** mà JAR gốc vẫn yêu cầu.

Vì thế:
- Main shaded JAR thay artifact chính: giảm POM thường hợp lý nếu đã gộp đủ dependencies.
- Main unshaded + attached shaded classifier: **giữ metadata cần cho main JAR**, tránh giảm POM chung vô ý.
- Nếu hai biến thể có dependency contract khác nhau đáng kể, cân nhắc **hai Maven modules / hai GAV khác nhau** để mỗi artifact có POM phù hợp.
- Muốn cung cấp file shaded phụ mà không thay main/JAR metadata, có thể xem `outputFile`, nhưng theo docs khi đặt `outputFile` thì Shade không tự thay main artifact hay attach output, và các tham số như `shadedArtifactAttached` và `createDependencyReducedPom` bị bỏ qua trong mode này. Muốn publish file output đó cần cơ chế attach/deploy riêng.

**Hợp đồng của published POM quan trọng ngang với nội dung JAR.** Chọn classifier chỉ để phân biệt file không tự tạo một mô hình transitivity mới.

## 8. So sánh Maven Shade và Maven Assembly Plugin

Maven Assembly Plugin có khả năng tạo archives phân phối hoặc JAR kết hợp dependency, ví dụ descriptor `jar-with-dependencies`.

Một plugin snippet:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>3.7.1</version>
    <configuration>
        <descriptorRefs>
            <descriptorRef>jar-with-dependencies</descriptorRef>
        </descriptorRefs>
    </configuration>
    <executions>
        <execution>
            <id>bundle-assembly</id>
            <phase>package</phase>
            <goals>
                <goal>single</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **snippet minh họa Assembly**, không phải lệnh cần thêm vào producer lab.

Artifact có thể có tên như:

```text
message-bundle-1.0.0-jar-with-dependencies.jar
```

**Assembly không có nghĩa giống Shade:**
- Shade hỗ trợ class relocation, resource transformers và `createDependencyReducedPom` theo cơ chế được mô tả.
- Assembly tập trung tạo archives/bundles theo descriptors; **không tự tạo dependency-reduced POM theo cùng cơ chế của Shade**.
- Assembly artifact có classifier có thể chia sẻ metadata với main artifact; consumer phải chọn đúng classifier nếu muốn lấy archive đó.
- Cả hai cần kiểm tra duplicate classes/resources, service files, archive signatures và license notices.
- Đừng kết luận rằng chỉ vì file có tên `jar-with-dependencies` thì Maven consumer tự dùng file đó hoặc các dependency sẽ tự biến mất khỏi POM.

## 9. Các tùy chọn nâng cao của reduced POM

### 9.1. keepDependenciesWithProvidedScope

```xml
<configuration>
    <createDependencyReducedPom>true</createDependencyReducedPom>
    <keepDependenciesWithProvidedScope>true</keepDependenciesWithProvidedScope>
</configuration>
```

Theo tài liệu Shade Plugin, thay vì xóa hẳn dependencies được gộp, plugin có thể giữ chúng trong reduced POM với **scope `provided`**. Provided scope không tự đưa dependency lên consumer runtime classpath như compile dependency; vì vậy đừng bật với mục tiêu “chắc chắn sẽ tải thư viện”.

### 9.2. promoteTransitiveDependencies

```xml
<configuration>
    <promoteTransitiveDependencies>true</promoteTransitiveDependencies>
</configuration>
```

Tùy chọn này có thể đưa các transitive dependencies của một dependency đã bị remove lên thành direct dependencies trong reduced POM. Nó giúp giữ những artifacts downstream vẫn cần trong một số trường hợp, nhưng có thể làm graph thay đổi theo cách khó lường nếu bật vô điều kiện.

**Không xem đây là giải pháp tự động cho mọi vấn đề thiếu class.** Hãy kiểm tra generated POM, consumer dependency graph và runtime behavior. Nếu một dependency đã được shade nhưng một subtree của nó thực sự còn cần, phải đánh giá tại sao subtree đó chưa được đóng gói đúng.

### 9.3. useBaseVersion

```xml
<configuration>
    <useBaseVersion>true</useBaseVersion>
</configuration>
```

Ảnh hưởng đến cách phiên bản của dependencies còn lại được ghi trong reduced POM, đặc biệt với SNAPSHOT có timestamp resolved version. Nó không làm thay đổi class relocation. Cần hiểu versioning/reproducibility policy trước khi dùng.

### 9.4. minimizeJar và entryPoints

```xml
<configuration>
    <minimizeJar>true</minimizeJar>
</configuration>
```

Minimize phân tích tham chiếu class và bỏ classes được cho là không sử dụng; không phải chức năng giảm dependency metadata. Với libraries dùng reflection/ServiceLoader/serialization, kết quả minimization có thể bỏ mất class mà consumer chỉ gọi gián tiếp. `entryPoints` giúp điều chỉnh tập điểm khởi đầu, nhưng không biến phân tích tĩnh thành bảo đảm đúng mọi runtime behavior.

Lab cố ý để `minimizeJar=false`. Với thư viện public API, cần consumer integration tests trước khi bật minimize để tiết kiệm vài MB.

## 10. File dependency-reduced-pom.xml, vị trí và build song song

Theo Shade 3.6.2, `dependencyReducedPomLocation` mặc định:

```text
${basedir}/dependency-reduced-pom.xml
```

Thực tế ở lab: `producer/dependency-reduced-pom.xml`. Vì file nằm ở basedir thay vì `target`, nó có thể còn sau `mvn clean`. Hãy ignore file generated nếu project không chủ định quản lý nó trong version control:

```gitignore
/dependency-reduced-pom.xml
/drp-*.pom
```

Đây là snippet cho `producer/.gitignore`, không phải command.

**Cảnh báo từ tài liệu Shade:** đặt `dependencyReducedPomLocation` ở một thư mục khác `${basedir}` có thể làm thay đổi giá trị `${basedir}` cho những executions chạy **sau Shade**, dẫn tới side effect không mong muốn. Không di chuyển file generated ra thư mục khác bằng option này nếu chưa kiểm tra kỹ.

`generateUniqueDependencyReducedPom` có thể tạo file `drp-UNIQUE.pom` để giảm xung đột các lần build song song cùng basedir:

```xml
<configuration>
    <generateUniqueDependencyReducedPom>true</generateUniqueDependencyReducedPom>
</configuration>
```

Plugin đặt property `maven.shade.dependency-reduced-pom` đến filename tương ứng. Tuy nhiên nó không giải quyết mọi xung đột khi nhiều Maven invocations cùng ghi `target` hoặc local repository; hãy dùng isolated workspaces cho CI khi phù hợp.

## 11. useDependencyReducedPomInJar và published POM

Theo Shade Plugin 3.6.2:

```xml
<configuration>
    <createDependencyReducedPom>true</createDependencyReducedPom>
    <useDependencyReducedPomInJar>true</useDependencyReducedPomInJar>
</configuration>
```

`useDependencyReducedPomInJar` chọn việc nhúng **reduced POM thay vì source POM** vào JAR. Mặc định flag này là `false`. Nó bị bỏ qua khi `createDependencyReducedPom=false`.

Điều quan trọng:
- **Embedded POM** là metadata trong JAR, thường dưới `META-INF/maven/.../pom.xml`.
- **Published POM** là file `.pom` ngoài JAR ở Maven repository.
- Maven Resolver của consumer thường dùng published POM để xác định transitive dependencies.
- Bật flag nhúng không tự sửa một remote repository đã publish bản metadata sai trước đó.

Do đó muốn kiểm tra một release, đọc **file .pom thật cạnh JAR ở repository** thay vì dựa vào nội dung JAR hoặc generated file riêng rẽ.

## 12. Public API và binary compatibility khi relocation

Cùng một dependency có thể:
- Chỉ được dùng **nội bộ** trong implementation, như lab `StringUtils.capitalize`; công khai API chỉ là `String`. Đây là trường hợp thuận lợi để relocate.
- Xuất hiện **trong method signatures của public API**, như một kiểu từ thư viện bên ngoài. Relocate kiểu này có thể làm đổi API mà consumers đã compile theo, gây `NoClassDefFoundError` hoặc compilation/binary errors.
- Được load qua **reflection bằng class name string**, ServiceLoader, annotation processing hoặc native bindings. Shade không luôn phát hiện và sửa mọi chuỗi/tài nguyên như compiler bình thường.

Ví dụ **chữ ký minh họa, không thuộc file Java runnable của lab**:

```java
public org.apache.commons.lang3.tuple.Pair<String, Integer> parse(String text);
```

Nếu công bố chữ ký này rồi relocate `org.apache.commons.lang3`, consumers có thể cần kiểu gốc mà POM reduced không còn công bố. Cách thiết kế tốt hơn:
- Không expose dependency implementation type trong public API khi muốn shade/relocate nó.
- Dùng types của thư viện mình quản lý hoặc JDK chuẩn trong public signatures.
- Giữ dependency thường nếu public contract yêu cầu.
- Phát hành artifact/API variant riêng nếu thật sự cần hai hợp đồng.

**Reduced POM không chứng minh binary compatibility**; cần compile và chạy consumer thật.

## 13. ServiceLoader, resources và vấn đề merge

Dependency JAR có thể mang:
- `META-INF/services/...`.
- `META-INF/MANIFEST.MF`.
- `META-INF/LICENSE`, `META-INF/NOTICE`.
- Resources theo đường dẫn package.
- Service/DI/framework/serialization metadata.
- Native library files.

Nếu nhiều JAR có cùng tên service file, phải hợp nhất nội dung thay vì một file ghi đè file kia. Shade có `ServicesResourceTransformer`:

```xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
```

Đây là snippet tùy chọn cho `<configuration>`, không cần thêm vào lab Commons Lang chỉ để có nội dung lớn hơn. Khi cần executable shaded JAR, có thể dùng `ManifestResourceTransformer` và đặt `Main-Class` theo entrypoint thực tế, nhưng bài này hướng dẫn **library consumption**, không tạo executable distribution.

**Cẩn trọng với ký số JAR:** nếu shade thay nội dung nhưng còn signature metadata `META-INF/*.SF`, `*.RSA`, `*.DSA` từ archive gốc, JVM có thể báo signature-related errors. Lab đã dùng filter loại các chữ ký cũ. Không xóa license/NOTICE hoặc che components khỏi auditing chỉ vì chúng nằm trong `META-INF`.

## 14. Exclusion, provided, optional và Maven mediation

Đừng nhầm giảm POM với exclusions trên consumer.

Ví dụ consumer cố exclude Commons Lang:

```xml
<dependency>
    <groupId>dev.training.shade</groupId>
    <artifactId>message-bundle</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclusion chỉ kiểm soát **artifact resolution** qua Maven graph; nó không xóa classes đã đóng sẵn vào shaded JAR. Trong lab đã reduction đúng thì exclusion đó dư thừa.

Một số distinctions:
- **`scope=provided`** nói thư viện có thể cần để compile nhưng thường do môi trường runtime cung cấp; nó không phải synonym của “đã shade”.
- **`optional=true`** tác động propagation của Maven transitive dependencies, không tự bundle bytecode.
- **Classifier** chọn variant artifact khác, không tự tạo metadata POM riêng.
- **Version mediation** vẫn áp dụng cho những dependencies còn trong graph sau reduction.
- **DependencyManagement/BOM** điều khiển version/defaults theo mô hình Maven; không tự làm shade hoặc sửa classes trong JAR.

Nếu consumer có dependency riêng tới Commons Lang vì lý do khác, `dependency:tree` vẫn có thể hiển thị Commons Lang dù producer đã reduce. Phải xem **đường đi dependency** chứ không chỉ kiểm tra một artifact có xuất hiện đâu đó hay không.

## 15. Khi nào reduced POM gây lỗi cho consumer?

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` ở consumer | Reduced POM bỏ dependency nhưng JAR không chứa class runtime cần thiết. | `jar --list`, stack trace, filters/minimize/relocation. |
| Consumer sử dụng main JAR unshaded bị thiếu dependency | Shade có classifier nhưng reduced POM chung đã loại dependency của main. | `shadedArtifactAttached`, published POM, main JAR contents. |
| Commons Lang vẫn xuất hiện trong consumer tree | POM chưa reduce, consumer có dependency khác, hoặc repository chứa metadata cũ. | Đọc installed/remote POM, đường đi dependency graph. |
| `dependency-reduced-pom.xml` tồn tại nhưng consumer không đổi | Producer mới `package`, chưa install/deploy; consumer dùng artifact khác. | GAV, repository file POM và source POM. |
| Consumer compile được nhưng runtime reflection fail | Minimize/relocation làm mất class/resource hoặc tên class string. | Consumer integration test, JAR entries, service metadata. |
| Duplicate classes hoặc ServiceLoader không hoạt động | Không relocate/hợp nhất resources đúng. | `jar --list`, transformers và classpath. |
| Build trên IDE pass nhưng CI fail | IDE dùng source graph khác metadata publish, cache artifact cũ. | CI trên repository sạch, pinned versions, consumer độc lập. |
| POM nhúng JAR khác POM repository | `useDependencyReducedPomInJar` và cơ chế publish tách biệt. | So file repository `.pom` với embedded metadata. |
| Dependency riêng bị mất sau khi đổi classifier mode | POM chung không thể phản ánh hai JAR có contracts khác nhau. | Phát hành GAV riêng hoặc thiết kế lại metadata. |

### 15.1. Lỗi POM không có dependency nhưng shaded JAR cũng thiếu class

Đây là failure quan trọng nhất: Maven Resolver không còn tải thư viện, nhưng bytecode ứng dụng vẫn tham chiếu đến class vốn nằm ngoài JAR. Nguyên nhân có thể là `artifactSet` chọn nhầm, filters loại quá nhiều files hoặc `minimizeJar`. Không nên “fix” bằng cách bật `createDependencyReducedPom=false` mà không hiểu package contract; cần xác minh bundle contents trước.

### 15.2. Producer test pass không có nghĩa consumer pass

Trong producer, Compiler Plugin và unit tests vẫn có dependency gốc từ source POM. Consumer độc lập đọc published POM. Nếu lỗi chỉ xuất hiện sau install/deploy, đó có thể là metadata/shading contract lỗi chứ không phải “Maven không tải được thư viện” chung chung.

### 15.3. Một nguồn lỗi khác: file POM mới nhưng JAR cũ

Artifact resolution có thể lấy metadata từ một repository/version nhưng JAR từ cache cũ hoặc pipeline chưa publish đồng bộ. Giữ version/release immutable, kiểm tra checksum khi có chính sách và không deploy đè cùng GAV release đã phát hành.

## 16. Checklist CI trước khi phát hành shaded artifact

- [ ] Ghim JDK/Maven/plugin versions.
- [ ] Source POM vẫn khai báo dependencies cần để compile/test.
- [ ] Cấu hình đúng `shade:shade` ở `package`.
- [ ] Hiểu mode **main replacement** hay **attached classifier**.
- [ ] `createDependencyReducedPom` được đặt theo publishing contract, không theo sở thích ngẫu nhiên.
- [ ] Reduced POM không loại dependency vẫn cần ngoài shaded JAR.
- [ ] Published `.pom` được đối chiếu với generated reduced POM.
- [ ] `jar --list` xác nhận relocated classes/resources nằm trong artifact đúng.
- [ ] Consumer dependency tree được kiểm tra từ **project độc lập**.
- [ ] Consumer chạy được mà không cần vô tình thêm các dependencies đã nhúng.
- [ ] Public API không phơi kiểu đã relocate trừ khi có thiết kế có chủ đích.
- [ ] Reflection/ServiceLoader/native resources có integration tests nếu được sử dụng.
- [ ] Không bật `minimizeJar` khi chưa kiểm tra class retention.
- [ ] Không che vulnerabilities: SBOM/license tracking vẫn bao gồm bytecode nhúng.
- [ ] Không xóa `LICENSE`/`NOTICE` khi lọc archive.
- [ ] Với classifier mode, không làm POM chung gây lỗi consumer của JAR chính.
- [ ] Không publish đè immutable release.
- [ ] Các reports và log được kiểm tra mà không lộ secrets.
- [ ] CI dừng phát hành nếu build, consumer tests hoặc metadata checks thất bại.

## 17. Câu hỏi ôn tập

**Câu 1.** Dependency-reduced POM là gì?

**Đáp án:** Là POM được Shade sinh để mô tả dependencies còn cần sau khi một số dependencies đã được gộp vào shaded JAR.

**Câu 2.** `createDependencyReducedPom` mặc định là gì trong Shade Plugin 3.6.2?

**Đáp án:** `true`.

**Câu 3.** Project source có cần Commons Lang khi compile dù published reduced POM không khai báo nó?

**Đáp án:** Có. Producer Java source import `StringUtils`; Maven cần Commons Lang trên compile classpath trước khi Shade xử lý bytecode.

**Câu 4.** File nào consumer Maven Resolver thường dùng?

**Đáp án:** Published `.pom` trong Maven repository, không mặc định embedded POM trong JAR.

**Câu 5.** Vì sao không nên chỉ dùng `dependency:tree` để xác nhận Shade thành công?

**Đáp án:** Dependency có thể biến mất khỏi graph nhưng shaded JAR vẫn thiếu class cần thiết. Phải kiểm tra JAR contents và runtime.

**Câu 6.** Nếu shadedArtifactAttached=false, điều gì xảy ra?

**Đáp án:** Shade thường thay main artifact của project bằng shaded artifact, theo cấu hình mặc định.

**Câu 7.** Nếu shadedArtifactAttached=true, giảm POM chung có thể gây lỗi gì?

**Đáp án:** Main JAR không shade có thể mất transitive dependency nó còn cần, vì main và classifier JAR thường chia sẻ một published POM.

**Câu 8.** `useDependencyReducedPomInJar` có phải `createDependencyReducedPom` không?

**Đáp án:** Không. Cái thứ nhất ảnh hưởng POM nhúng trong JAR; cái thứ hai điều khiển việc tạo POM rút gọn.

**Câu 9.** `minimizeJar` và dependency reduction khác nhau thế nào?

**Đáp án:** Minimize ảnh hưởng lớp Java được giữ trong archive; reduction ảnh hưởng artifact dependencies trong POM.

**Câu 10.** Producer lab relocate package Commons Lang sang đâu?

**Đáp án:** `dev.training.shade.internal.lang3`.

**Câu 11.** Stdout chính xác của consumer app trong lab là gì?

**Đáp án:** `Hello, Maven!`.

**Câu 12.** Tại sao phải `mvn install` producer trước khi chạy Maven consumer độc lập?

**Đáp án:** Consumer không nằm trong reactor của producer nên cần resolve artifact/POM từ local/remote repository.

**Câu 13.** `keepDependenciesWithProvidedScope` dùng làm gì?

**Đáp án:** Có thể giữ dependency đã gộp trong reduced POM nhưng đổi sang `provided`, thay vì loại hẳn.

**Câu 14.** `promoteTransitiveDependencies` dùng để làm gì?

**Đáp án:** Có thể nâng transitive dependencies của dependencies đã remove thành direct dependencies để giữ graph phù hợp.

**Câu 15.** Vì sao Maven Assembly Plugin không tương đương Shade?

**Đáp án:** Assembly tạo archives/distribution theo descriptors; nó không tự cung cấp cùng cơ chế relocation và dependency-reduced POM như Shade.

**Câu 16.** `dependencyReducedPomLocation` có rủi ro gì khi đặt ngoài basedir?

**Đáp án:** Tài liệu Shade cảnh báo có thể làm `${basedir}` thay đổi cho executions chạy sau.

**Câu 17.** Reduced POM không còn Commons Lang thì artifact có hết code Commons Lang không?

**Đáp án:** Không. Code có thể vẫn ở trong shaded JAR, nên cần SBOM, vulnerability và license tracking.

**Câu 18.** Khi một thư viện công khai type của dependency đã relocate trong API, phải làm gì?

**Đáp án:** Đánh giá và thiết kế lại public API hoặc publishing contract; không chỉ giảm POM rồi giả định binary compatibility.

## 18. Tài liệu tham khảo chính thức

- [Apache Maven Shade Plugin 3.6.2 – shade:shade](https://maven.apache.org/plugins/maven-shade-plugin/shade-mojo.html): `createDependencyReducedPom`, `dependencyReducedPomLocation`, `generateUniqueDependencyReducedPom`, `keepDependenciesWithProvidedScope`, `promoteTransitiveDependencies`, `shadedArtifactAttached` và `useDependencyReducedPomInJar`.
- [Apache Maven Shade Plugin – Introduction](https://maven.apache.org/plugins/maven-shade-plugin/): chức năng shaded/uber JAR và relocation.
- [Apache Maven Shade Plugin – Attaching the Shaded Artifact](https://maven.apache.org/plugins/maven-shade-plugin/examples/attached-artifact.html): classifier và main replacement.
- [Apache Maven Shade Plugin – Selecting Contents for Uber JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/includes-excludes.html): artifactSet/filters/minimize.
- [Apache Maven Shade Plugin – Class Relocation](https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html): relocation.
- [Apache Maven Shade Plugin – Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html): services/manifest merging.
- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scope, mediation, exclusions và transitivity.
- [Apache Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase package/install/deploy.
- [Apache Maven Assembly Plugin](https://maven.apache.org/plugins/maven-assembly-plugin/): assembly archives.
- [Apache Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): quan sát dependency graph của consumer.
