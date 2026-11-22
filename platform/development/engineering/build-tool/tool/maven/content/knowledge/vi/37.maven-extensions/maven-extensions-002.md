# Cấu trúc dự án plugin và `packaging=maven-plugin` trong Apache Maven

## 1. Plugin Maven là gì và tại sao cần `packaging=maven-plugin`?

Một Maven plugin là một thành phần mở rộng **có thể được Maven gọi như build goal**, ví dụ `compiler:compile`, `surefire:test` hoặc một goal do nhóm tự viết. Plugin không chỉ là JAR chứa Java classes: Maven cần biết **goal nào được cung cấp, class nào thực thi goal, tham số nào nhận từ POM/CLI, yêu cầu phiên bản Maven/JDK và những metadata để tạo plugin class realm**.

Trong một dự án plugin Java, cách khai báo trung tâm trong `pom.xml` là:

```xml
<packaging>maven-plugin</packaging>
```

Giá trị này chọn **lifecycle mapping dành cho Maven plugin**: vẫn biên dịch Java, chạy tests và tạo JAR, đồng thời kích hoạt bước tạo **plugin descriptor** tại đường dẫn `META-INF/maven/plugin.xml` và metadata phục vụ nhận diện plugin. JAR sinh ra có thể được `install` vào Maven local repository hoặc `deploy` đến một Maven repository để dự án khác gọi.

Một project `packaging=jar` thông thường có thể có class `GreetMojo`, nhưng chỉ đóng gói class **chưa đủ** để Maven hiểu goal `greet`. Ngược lại, khai báo `maven-plugin` nhưng không có Mojo hợp lệ thì plugin thiếu goal hữu ích. Cần **cấu trúc source + Maven Plugin API + annotations + Plugin Tools + descriptor** làm việc cùng nhau.

Bài học hướng dẫn một ví dụ **Java 17, Maven 3.9.x**:

- Project plugin: `dev.learning.plugins:notice-maven-plugin:1.0.0-SNAPSHOT`, packaging `maven-plugin`.
- Mojo Java: `GreetMojo`, khai báo goal `greet` bằng `@Mojo`.
- Tham số: `greeting`, `recipient` nhận từ CLI/POM bằng `@Parameter`.
- Phần logic thuần Java: `GreetingText`, có **4 JUnit 5 tests**.
- Project consumer: POM riêng chỉ dùng plugin đã được cài qua Maven repository, có execution chạy ở phase `validate`.
- Kiểm tra JAR/descriptor, HelpMojo, gọi goal trực tiếp và qua lifecycle.

**Trọng tâm:** hiểu rõ **đâu là Maven plugin project, đâu là Java library project, Maven biết goal qua cơ chế nào và `packaging=maven-plugin` làm thay đổi điều gì**.

## 2. Phân biệt plugin, dependency, extension, parent và aggregator

| Thành phần | Mục đích | Nơi thường khai báo |
| --- | --- | --- |
| Project Java library | Cung cấp class/API cho application | `<dependencies>` của consumer |
| Project Maven plugin | Cung cấp goals cho Maven build | `<build><plugins>` của consumer |
| Maven plugin API | Các interfaces/classes để **viết** Mojo | `<dependencies>` của plugin project |
| Maven Plugin Tools | Tạo descriptor, help goal, documentation | Build plugins của plugin project |
| Maven extension | Mở rộng Maven core/lifecycle/resolver theo cơ chế extension | `.mvn/extensions.xml` hoặc build extensions |
| Parent POM | Kế thừa cấu hình, dependency/plugin management | `<parent>` của child |
| Aggregator POM | Tập hợp modules vào Reactor build | `<modules>`, thường packaging `pom` |

Một project plugin vẫn dùng `<dependencies>` để compile code của chính Mojo, nhưng **dự án consumer phải đưa plugin vào `<build><plugins>` để khai báo goal/execution**, không phải `<dependencies>` của app.

Ví dụ **SAI khi muốn chạy goal**:

```xml
<dependencies>
    <dependency>
        <groupId>dev.learning.plugins</groupId>
        <artifactId>notice-maven-plugin</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </dependency>
</dependencies>
```

Cấu hình trên chỉ tạo một **project dependency**, không đăng ký goal cho Maven lifecycle. Cách đúng là:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>dev.learning.plugins</groupId>
            <artifactId>notice-maven-plugin</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </plugin>
    </plugins>
</build>
```

Hai đoạn là **mảnh POM minh họa**, không phải POM hoàn chỉnh; phần thực hành sẽ có hai POM chạy được.

## 3. Plugin gồm những thành phần nào?

Một plugin Java đơn giản có năm thành phần chính:

1. **POM:** GAV, `<packaging>maven-plugin</packaging>`, dependency Maven Plugin API và annotations, cấu hình compiler/Plugin Tools.
2. **Mojo:** class Java triển khai một Maven goal, thường `extends AbstractMojo`, có `@Mojo(name = "...")` và `execute()`.
3. **Parameters:** trường annotated `@Parameter`, đọc từ POM `<configuration>`, user property `-D...` hoặc Maven expressions.
4. **Plugin descriptor:** file XML `META-INF/maven/plugin.xml` do Maven Plugin Plugin sinh, ghi goal/implementation/parameters.
5. **Artifact:** JAR đóng gói descriptor và classes, đi cùng POM để Maven tải như một build plugin.

Tên **Mojo** là thuật ngữ của Maven cho một goal implementation. Một Maven plugin JAR có thể chứa **nhiều Mojo**, mỗi Mojo có một `@Mojo(name = "...")` khác nhau. Một plugin có thể cung cấp `notice:greet`, `notice:check` và `notice:report` trong tương lai.

### 3.1. Dòng chảy thực thi

```text
Consumer chạy Maven goal hoặc lifecycle phase
                |
                v
Maven resolve plugin GAV từ pluginRepositories/local repo
                |
                v
Maven đọc META-INF/maven/plugin.xml trong plugin JAR
                |
                v
Maven tạo plugin class realm, resolve plugin dependencies
                |
                v
Maven inject @Parameter / cấu hình component phù hợp
                |
                v
Maven gọi GreetMojo.execute()
                |
                v
getLog().info(...) hoặc ném MojoFailure/ExecutionException
```

**Plugin class realm** khác project compile/test classpath. Một library trên project `<dependencies>` **không tự nằm trong classpath của plugin**. Nếu plugin cần thư viện hỗ trợ lúc thực thi, khai báo nó trong POM plugin hoặc dùng plugin dependencies phù hợp; không ngầm trông chờ consumer app đã khai báo thư viện đó.

## 4. Cấu trúc thư mục đề xuất cho plugin và consumer độc lập

Ví dụ bố cục dễ tái hiện:

```text
maven-plugin-lab/
├── plugin/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/learning/plugins/
│       │   ├── GreetingText.java
│       │   └── GreetMojo.java
│       └── test/java/dev/learning/plugins/
│           └── GreetingTextTest.java
└── consumer/
    └── pom.xml
```

**Không có root aggregator POM** trong bài; hai thư mục `plugin` và `consumer` chỉ đặt cạnh nhau cho dễ hướng dẫn. Consumer được build sau khi plugin đã được `install`; điều này thử được việc **Maven resolve plugin artifact từ repository**, không âm thầm lấy class từ build output của source plugin.

Quy tắc layout:

- `plugin/src/main/java`: các Mojo và classes hỗ trợ.
- `plugin/src/main/resources`: resource cần đóng vào plugin JAR, nếu có.
- `plugin/src/test/java`: unit tests và test helpers.
- `plugin/target/classes`: compiler output, sẽ có `META-INF/maven/plugin.xml` sau descriptor generation.
- `plugin/target/notice-maven-plugin-1.0.0-SNAPSHOT.jar`: artifact chính để dùng trong Maven.
- `consumer/pom.xml`: khai báo plugin như `<build><plugins>`, có thể bind goal vào lifecycle.

Không đặt một Mojo dưới `consumer/src/main/java` rồi nghĩ consumer sẽ trở thành Maven plugin. **Project có `<packaging>maven-plugin</packaging>` và metadata phù hợp mới là plugin producer**.

## 5. Tên artifact: đúng quy ước Maven Plugin Naming

Theo hướng dẫn Apache Maven, plugins của bên thứ ba nên có dạng:

```text
<ten-cua-plugin>-maven-plugin
```

Ví dụ:

```text
notice-maven-plugin
```

Không nên đặt plugin của tổ chức theo dạng:

```text
maven-notice-plugin
```

Mẫu `maven-...-plugin` được Maven dự trữ cho những plugins chính thức của Apache Maven dưới `org.apache.maven.plugins`; dùng nó cho plugin bên ngoài có thể gây nhầm lẫn và vi phạm quy ước thương hiệu.

Tọa độ của ví dụ:

```text
groupId:    dev.learning.plugins
artifactId: notice-maven-plugin
version:    1.0.0-SNAPSHOT
packaging:  maven-plugin
goal:       greet
prefix:     notice
```

GAV là danh tính artifact. `greet` **không phải version hoặc classifier**; nó là goal được descriptor đăng ký. Prefix `notice` thường được suy ra từ tên `notice-maven-plugin` và có thể được khai báo tường minh bằng `goalPrefix` trong Maven Plugin Plugin. **Dùng full plugin coordinates khi cần chắc chắn**, vì prefix resolution còn phụ thuộc POM/settings/repository metadata.

## 6. POM plugin hoàn chỉnh, Java 17

Tạo `plugin/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.plugins</groupId>
    <artifactId>notice-maven-plugin</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>maven-plugin</packaging>
    <name>Learning Notice Maven Plugin</name>
    <description>Minimal greeting Mojo for Maven 3 / Java 17.</description>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <plugin.tools.version>3.15.2</plugin.tools.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-plugin-api</artifactId>
            <version>3.9.9</version>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.apache.maven.plugin-tools</groupId>
            <artifactId>maven-plugin-annotations</artifactId>
            <version>${plugin.tools.version}</version>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-plugin-plugin</artifactId>
                <version>${plugin.tools.version}</version>
                <configuration>
                    <goalPrefix>notice</goalPrefix>
                </configuration>
                <executions>
                    <execution>
                        <id>generate-plugin-help</id>
                        <goals>
                            <goal>helpmojo</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích những quyết định có ý nghĩa:

1. **`<packaging>maven-plugin</packaging>`** tạo lifecycle mapping của plugin thay vì JAR application thông thường; plugin JAR vẫn được đóng gói.
2. `maven-plugin-api` cung cấp `AbstractMojo`, `MojoExecutionException`, `MojoFailureException`, logger, v.v. Với plugin Maven 3, API này do Maven runtime cung cấp; `provided` là lựa chọn phù hợp với ví dụ.
3. `maven-plugin-annotations` cung cấp `@Mojo`, `@Parameter`, `@Component`; annotations được dùng khi build descriptor, thường để `provided`.
4. `maven-plugin-plugin` thuộc **build plugins**, không thuộc production dependencies; nó **đọc metadata từ Mojo và sinh descriptor**.
5. `<goalPrefix>notice</goalPrefix>` chỉ định prefix metadata để Maven/plugin tools tài liệu hóa, không bảo đảm mọi máy đều có thể dùng `mvn notice:greet` mà không cấu hình prefix resolution.
6. `helpmojo` tạo một goal trợ giúp dùng cho documentation; đây là bổ sung hữu ích, **không thay thế goal `greet`**.
7. JUnit Jupiter ở test scope vì chỉ dùng trong tests, Surefire chạy JUnit 5.
8. Compiler release 17 phù hợp code dùng `String.strip()` và các API có trong Java 17.
9. Pin các plugin versions giúp reproducibility. Các versions chọn theo hướng dẫn Maven Plugin Tools và ví dụ Maven 3; **không phải tuyên bố về phiên bản mới nhất hoặc security baseline của tổ chức**.
10. Plugin không cần Maven extension hay custom `META-INF/plexus/components.xml` thủ công trong ví dụ annotation-based Mojo.

**Không xóa `maven-plugin-api` vì nghĩ `packaging=maven-plugin` tự thêm mọi Java API vào compiler classpath.** Packaging chọn lifecycle; POM vẫn phải khai báo dependencies để compiler tìm được `AbstractMojo` và annotations.

## 7. Vì sao `maven-plugin-api` và `maven-plugin-annotations` là hai dependencies khác nhau?

`org.apache.maven:maven-plugin-api` chứa **runtime-facing Maven plugin interfaces/classes**, trong đó có `AbstractMojo`. Còn `org.apache.maven.plugin-tools:maven-plugin-annotations` chứa những annotation dùng để **mô tả goal và tham số**.

| Dependency | Java import ví dụ | Mục đích |
| --- | --- | --- |
| `maven-plugin-api` | `org.apache.maven.plugin.AbstractMojo` | Viết Mojo implementation và log/exception |
| `maven-plugin-annotations` | `org.apache.maven.plugins.annotations.Mojo` | Khai báo goal cho descriptor generator |
| `maven-plugin-plugin` | Không import vào source Java | Build tool tạo descriptor/help |
| `junit-jupiter` | `org.junit.jupiter.api.Test` | Test Java logic của plugin |

**Đừng thay `maven-plugin-api` bằng `maven-core` một cách vô tội vạ.** Nếu Mojo thực sự cần `MavenProject`, `MavenSession` hoặc services khác, có thể phải khai báo Maven API/core đúng version/scope theo tài liệu, nhưng ví dụ tối thiểu không cần các class đó.

Nếu `AbstractMojo` import không resolve ở `compile`, kiểm `maven-plugin-api` dependency và scope. Nếu `@Mojo` không resolve, kiểm `maven-plugin-annotations`. Nếu Java compile pass nhưng descriptor không có goal, kiểm Maven Plugin Plugin/lifecycle và annotation extraction.

## 8. Logic thuần Java: `GreetingText.java`

Tệp `plugin/src/main/java/dev/learning/plugins/GreetingText.java`:

```java
package dev.learning.plugins;

public final class GreetingText {
    private GreetingText() {
    }

    public static String format(String greeting, String recipient) {
        if (greeting == null || greeting.isBlank()) {
            throw new IllegalArgumentException(
                    "greeting must not be blank");
        }
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "recipient must not be blank");
        }
        return greeting.strip() + ", " + recipient.strip() + "!";
    }
}
```

Đây là class Java bình thường, không phụ thuộc Maven API. Việc tách logic ra khỏi `execute()` có hai lợi ích:

- Unit tests không cần khởi động Maven container để kiểm phần logic định dạng/validation.
- Mojo mỏng hơn: chỉ nhận configuration, gọi logic và chuyển lỗi sang kiểu Maven biết xử lý.

Output của phương thức:

```java
GreetingText.format(" Hello ", " Maven ")
```

là:

```text
Hello, Maven!
```

Đây là **biểu thức minh họa**, chưa phải một file có `public static void main`. Người học có thể chạy Unit Test ở phần tiếp theo thay vì viết thêm launcher riêng.

### 8.1. Quy ước validate đầu vào

Ví dụ kiểm `null`/blank để không log một lời chào rỗng dù POM/CLI có cấu hình sai. Với plugin thực, validation có thể gồm file existence, path nằm trong workspace, enum values hoặc quyền được cấp.

Không tự đọc environment secrets hoặc log các cấu hình nhạy cảm. Một plugin được Maven thực thi trong quá trình build có khả năng tác động files/network theo code, vì vậy phải coi nó là **build-time executable code** chứ không phải chỉ là metadata.

## 9. Mojo thực tế: `GreetMojo.java`

Tệp `plugin/src/main/java/dev/learning/plugins/GreetMojo.java`:

```java
package dev.learning.plugins;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugin.MojoFailureException;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

// Goal "greet" is callable as <plugin-coordinates>:greet.
@Mojo(name = "greet", threadSafe = true)
public final class GreetMojo extends AbstractMojo {

    // Override with -Dnotice.greeting=Welcome.
    @Parameter(property = "notice.greeting", defaultValue = "Hello")
    private String greeting;

    // Override with -Dnotice.recipient=Team.
    @Parameter(property = "notice.recipient", defaultValue = "Maven")
    private String recipient;

    @Override
    public void execute()
            throws MojoExecutionException, MojoFailureException {
        try {
            getLog().info(GreetingText.format(
                    greeting, recipient));
        } catch (IllegalArgumentException problem) {
            throw new MojoFailureException(problem.getMessage());
        }
    }
}
```

**Điểm cần hiểu:**

- `@Mojo(name = "greet")` đăng ký tên **goal**, không phải Java method `greet()`. Maven gọi `execute()` để thực thi.
- `extends AbstractMojo` cung cấp `getLog()` và chuẩn triển khai `Mojo`.
- `@Parameter` định nghĩa tham số mà Maven có thể inject từ config/CLI.
- `property = "notice.recipient"` liên kết với Maven user property `-Dnotice.recipient=...`.
- `defaultValue` được dùng khi không có giá trị được cấu hình phù hợp.
- `threadSafe = true` là lời khai báo tác giả rằng goal an toàn khi được chạy trong build parallel; trong ví dụ Mojo chỉ dùng local fields/log và không sửa shared files. **Không gắn `threadSafe=true` cho plugin thực có shared mutable state nếu chưa audit**.
- `getLog().info(...)` tốt hơn `System.out.println()` vì dùng kênh Maven logging.
- `MojoFailureException` phù hợp cho **sai input do người sử dụng có thể sửa**; `MojoExecutionException` dùng khi goal gặp vấn đề thực thi ngoài dự kiến (ví dụ lỗi I/O).

Chữ ký `execute()` được phép khai báo cả hai Maven exceptions dù logic mẫu chỉ chủ động ném `MojoFailureException`. Compiler không yêu cầu thực thi một nhánh ném cả hai.

### 9.1. Goal không tự chạy khi chỉ có annotation

Vì ví dụ dùng:

```java
@Mojo(name = "greet", threadSafe = true)
```

và **không khai báo `defaultPhase`**, goal `greet` chỉ chạy khi người dùng gọi trực tiếp hoặc bind nó vào một phase bằng `<executions>` trong consumer POM.

Ngay cả nếu thêm:

```java
@Mojo(
    name = "greet",
    defaultPhase = LifecyclePhase.VALIDATE,
    threadSafe = true
)
```

thì `defaultPhase` là **metadata phase được khuyến nghị khi goal được cấu hình/bind theo cơ chế hỗ trợ**; **không tự gắn goal vào tất cả Maven projects** chỉ vì plugin có một annotation. Muốn dự án consumer chạy goal khi `mvn validate`, hãy khai báo plugin execution ở consumer.

## 10. Tham số `@Parameter`: POM configuration, CLI và Maven expressions

Trong Mojo:

```java
@Parameter(property = "notice.greeting", defaultValue = "Hello")
private String greeting;
```

Có các cách cấp giá trị:

**Mặc định từ annotation:**

```bash
mvn dev.learning.plugins:notice-maven-plugin:1.0.0-SNAPSHOT:greet
```

nếu goal chạy trong Maven project và không bị POM/config khác override, message mặc định là `Hello, Maven!`.

**Đổi qua user properties:**

```bash
mvn dev.learning.plugins:notice-maven-plugin:1.0.0-SNAPSHOT:greet \
    -Dnotice.greeting=Hi \
    -Dnotice.recipient=Team
```

message từ Mojo khi input hợp lệ:

```text
Hi, Team!
```

**Đổi qua POM plugin configuration:**

```xml
<configuration>
    <greeting>Welcome</greeting>
    <recipient>Developers</recipient>
</configuration>
```

message là:

```text
Welcome, Developers!
```

**Lưu ý về ưu tiên:** nếu POM explicit `<greeting>Welcome</greeting>`, user property `-Dnotice.greeting=Hi` không nhất thiết thay được literal trong cấu hình goal. Nếu muốn CLI có thể override rõ ràng, dùng POM properties rồi tham chiếu biểu thức:

```xml
<properties>
    <notice.greeting>Welcome</notice.greeting>
</properties>
<build>
    <plugins>
        <plugin>
            <groupId>dev.learning.plugins</groupId>
            <artifactId>notice-maven-plugin</artifactId>
            <version>1.0.0-SNAPSHOT</version>
            <configuration>
                <greeting>${notice.greeting}</greeting>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Sau đó command-line `-Dnotice.greeting=Hi` có thể override **user property** của POM. Đây là **mảnh POM**; POM consumer đầy đủ ở phần 15.

### 10.1. Những annotation khác có ích

- `@Parameter(readonly = true, defaultValue = "${project}")`: thường dùng cho Maven project context khi Mojo khai báo đúng kiểu `MavenProject` và dependency API/core cần thiết.
- `@Parameter(required = true)`: Maven kiểm presence, còn validation nghiệp vụ chi tiết vẫn nên do plugin thực hiện.
- `@Component`: inject một Maven/Plexus component theo cơ chế được Maven Plugin Tools hỗ trợ.
- `@Execute`: điều khiển forked lifecycle trong những tình huống nâng cao; không cần cho goal log của bài.

Các ví dụ này **không phải code bổ sung cần dán vào GreetMojo**. Đặc biệt `MavenProject` là type khác `String`, cần dependency Maven core/project phù hợp nếu dùng; đừng thêm injection một cách máy móc rồi để compiler fail.

## 11. Unit tests bằng JUnit Jupiter 5

Tệp `plugin/src/test/java/dev/learning/plugins/GreetingTextTest.java`:

```java
package dev.learning.plugins;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTextTest {

    @Test
    void createsDefaultGreeting() {
        assertEquals("Hello, Maven!",
                GreetingText.format("Hello", "Maven"));
    }

    @Test
    void trimsWhitespace() {
        assertEquals("Hi, Team!",
                GreetingText.format(" Hi ", " Team "));
    }

    @Test
    void rejectsBlankGreeting() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> GreetingText.format("  ", "Maven"));
        assertEquals(
                "greeting must not be blank",
                error.getMessage());
    }

    @Test
    void rejectsBlankRecipient() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> GreetingText.format("Hello", " "));
        assertEquals(
                "recipient must not be blank",
                error.getMessage());
    }
}
```

Các tests trên chỉ kiểm `GreetingText` độc lập, nên có thể chạy bằng Surefire mà không mock MavenProject hoặc khởi động Plexus container. Điều này làm bài demo ổn định và dễ gỡ lỗi.

**Đúng 4 test methods** trong `GreetingTextTest`. Sau `mvn clean verify`, mong đợi:

```text
Tests run: 4
Failures: 0
Errors: 0
Skipped: 0
```

Đây là các **giá trị kỳ vọng**, không phải một Maven stdout transcript đã được chạy.

### 11.1. Unit test không thay được integration test Mojo

`GreetingTextTest` **không kiểm** việc:

- `@Mojo` đã được Plugin Tools nhận diện;
- descriptor có goal `greet`;
- Maven inject `@Parameter` đúng;
- consumer có thể resolve plugin artifact;
- `mvn validate` đã bind goal và thực thi;
- plugin hoạt động trên Maven/JDK/runtime của user.

Vì vậy phần 14–17 sẽ **build/install plugin và chạy từ consumer độc lập**. Với plugin chuyên nghiệp, còn có thể dùng Maven Plugin Testing Harness hoặc Maven Invoker Plugin để tự động hóa các fixture builds.

## 12. Điều gì diễn ra khi `packaging=maven-plugin` được build?

Lifecycle Maven gắn với packaging của project. Với plugin project trong bài, luồng khái quát là:

```text
validate
  |
  v
generate-sources / process-sources
  |   (có thể sinh HelpMojo)
  v
compile
  |   (Maven Compiler Plugin)
  v
process-classes
  |   (Maven Plugin Plugin: descriptor)
  v
test-compile
  |   (Maven Compiler Plugin: testCompile)
  v
test
  |   (Maven Surefire Plugin)
  v
package
  |   (Maven JAR Plugin + plugin metadata)
  v
verify
  |
  v
install (tùy lệnh người dùng)
  |
  v
deploy (chỉ khi publish có cấu hình/quyền)
```

Chi tiết phase/goal bindings phụ thuộc Maven version, Plugin Tools version và cấu hình project. **Điểm cố định cần nắm**: Maven compile Mojo classes trước khi descriptor extractor đọc annotations; descriptor được đưa vào plugin JAR; test chạy trong lifecycle; JAR và POM có thể install/deploy.

Với Maven Plugin Tools 3.x, descriptor goal `plugin:descriptor` được gắn vào `process-classes` trong hướng dẫn phổ biến; `plugin:addPluginArtifactMetadata` tham gia packaging/metadata stage. Không viết tay descriptor khi dùng annotations trong pipeline chuẩn.

### 12.1. `jar` và `maven-plugin` khác nhau tại đâu?

| Packaging | Đầu ra chính | Metadata Maven plugin |
| --- | --- | --- |
| `jar` | Java JAR | Không tự sinh plugin descriptor bằng plugin lifecycle |
| `maven-plugin` | Java JAR dùng làm Maven plugin | Có lifecycle bindings phục vụ descriptor/plugin metadata |
| `pom` | Không đóng gói main Java JAR mặc định | Dùng cho parent/aggregator/dependency management |
| `war` | Web archive | Phục vụ servlet/web deployment, không phải Mojo plugin |

**Sai lầm thường gặp:** nhìn thấy file `.jar` rồi kết luận `<packaging>jar</packaging>` là tương đương `<packaging>maven-plugin</packaging>`. Chúng khác nhau ở **role và lifecycle metadata**, dù đuôi artifact cuối cùng có thể giống nhau.

## 13. Build plugin và kiểm tra descriptor

Từ thư mục `maven-plugin-lab/` (nơi có `plugin/` và `consumer/`):

```bash
mvn -B -ntp -f plugin/pom.xml clean verify
```

Trong build thành công, mục tiêu QA:

1. Java compiler compile `GreetingText` và `GreetMojo`.
2. Maven Plugin Plugin sinh metadata của goal `greet`.
3. Surefire chạy đủ 4 JUnit 5 tests.
4. Maven JAR Plugin đóng gói main artifact:
   `plugin/target/notice-maven-plugin-1.0.0-SNAPSHOT.jar`.
5. Plugin descriptor ở `plugin/target/classes/META-INF/maven/plugin.xml` và được đóng vào JAR.

Đường dẫn được kỳ vọng:

```text
plugin/target/classes/dev/learning/plugins/GreetingText.class
plugin/target/classes/dev/learning/plugins/GreetMojo.class
plugin/target/classes/META-INF/maven/plugin.xml
plugin/target/surefire-reports/TEST-dev.learning.plugins.GreetingTextTest.xml
plugin/target/notice-maven-plugin-1.0.0-SNAPSHOT.jar
```

Đây là paths **dự kiến theo Maven project layout**, không phải báo cáo rằng chúng đã được tạo trên hệ thống hiện tại.

### 13.1. Xem entries trong JAR

Linux/macOS hoặc Windows có `jar` của JDK trên PATH:

```bash
jar tf plugin/target/notice-maven-plugin-1.0.0-SNAPSHOT.jar
```

Các entries cần có:

```text
META-INF/maven/plugin.xml
dev/learning/plugins/GreetMojo.class
dev/learning/plugins/GreetingText.class
```

`jar tf` chỉ liệt kê archive contents; nó **chưa chứng minh descriptor chứa đúng tên goal/parameters**. Để kiểm nội dung plugin XML, giải nén/đọc entry hoặc dùng Help Plugin ở phần tiếp.

### 13.2. Plugin descriptor chứa gì?

Plugin Tools dựa trên annotations và POM để mô tả:

```xml
<mojos>
    <mojo>
        <goal>greet</goal>
        <implementation>dev.learning.plugins.GreetMojo</implementation>
        <!-- ... parameters, requirements and configuration ... -->
    </mojo>
</mojos>
```

Đây là **fragment sơ đồ minh họa**, không phải toàn bộ descriptor thực tế. Plugin Tools còn thêm version, required Java/Maven versions, execution flags, plugin dependencies, naming và cấu hình metadata. **Không copy đoạn rút gọn này thành plugin.xml** thay output generator.

### 13.3. Có nên tự sửa plugin.xml trong target?

Không. `target/classes/META-INF/maven/plugin.xml` là **generated build output**. Sửa tay có thể làm một lượt local run “tạm được” nhưng file sẽ mất khi `mvn clean`. Nguồn đúng để sửa là Java annotations, POM/Plugin Plugin config, rồi build lại.

Nếu thiếu descriptor, xem `plugin:descriptor` có thực thi không, project packaging có đúng không và extractor có đọc `@Mojo` không. Chỉ import `@Mojo` vào source **chưa chứng minh** descriptor generation đã thành công.

## 14. Cài plugin vào local Maven repository

Trước khi consumer ở một Maven run khác resolve được custom plugin:

```bash
mvn -B -ntp -f plugin/pom.xml clean install
```

Với source/POM đúng, `install` chạy trước đó các phases cần thiết, rồi cài:

```text
dev/learning/plugins/notice-maven-plugin/1.0.0-SNAPSHOT/
    notice-maven-plugin-1.0.0-SNAPSHOT.jar
    notice-maven-plugin-1.0.0-SNAPSHOT.pom
    ... Maven metadata/tracking files tùy repository ...
```

`install` đặt artifacts vào **local Maven repository của môi trường thực thi**. Điều đó không tự publish plugin lên Maven Central hay repository của tổ chức.

Nếu bạn chạy producer với `-Dmaven.repo.local=/qa/m2` và consumer không dùng cùng repository path, consumer có thể báo không tìm thấy plugin. Hai Maven commands phải dùng cùng local repository, hoặc producer cần deploy tới repository consumer truy cập được.

### 14.1. Linux/macOS: local repo cô lập

Để không phụ thuộc cache mặc định của developer:

```bash
REPO="$PWD/.qa-m2"

mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f plugin/pom.xml clean install

mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f consumer/pom.xml validate
```

Lần đầu tải plugin/JUnit và dependencies khác sẽ cần quyền truy cập Maven Central/mirror được cấu hình. Không xóa thư mục `~/.m2` của các project khác. Nếu dùng `.qa-m2` đã có từ buổi trước, nó không còn hoàn toàn mới nhưng vẫn có thể dùng cho local install demo.

### 14.2. Windows PowerShell: local repo cô lập

Từ `maven-plugin-lab`:

```powershell
$repo = Join-Path (Get-Location) '.qa-m2'

mvn -B -ntp "-Dmaven.repo.local=$repo" `
    -f plugin/pom.xml clean install
if ($LASTEXITCODE -ne 0) {
    throw 'Plugin build or install failed'
}

mvn -B -ntp "-Dmaven.repo.local=$repo" `
    -f consumer/pom.xml validate
if ($LASTEXITCODE -ne 0) {
    throw 'Consumer plugin execution failed'
}
```

Khi dùng PowerShell line continuation, dấu backtick phải đứng cuối dòng và không có khoảng trắng phía sau. Các example Maven dùng JDK 17+, Maven 3.9.x tương thích với versions đã pin trong POM.

## 15. Consumer `pom.xml`: bind goal vào phase `validate`

Tạo `consumer/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.consumer</groupId>
    <artifactId>notice-plugin-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <notice.greeting>Welcome</notice.greeting>
        <notice.recipient>Team</notice.recipient>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>dev.learning.plugins</groupId>
                <artifactId>notice-maven-plugin</artifactId>
                <version>1.0.0-SNAPSHOT</version>

                <configuration>
                    <greeting>${notice.greeting}</greeting>
                    <recipient>${notice.recipient}</recipient>
                </configuration>

                <executions>
                    <execution>
                        <id>announce-validation</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>greet</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Consumer này dùng `packaging=pom` vì nó chỉ đóng vai trò **khách hàng gọi plugin**, không có Java source hoặc JAR output. Điều đó không ảnh hưởng việc chạy plugin đã bind vào `validate`. Bản plugin mới được build/install theo GAV trước đó.

### 15.1. Mỗi phần của cấu hình consumer

- `<build><plugins>`: đăng ký plugin thực sự tham gia build.
- `<groupId>`, `<artifactId>`, `<version>`: yêu cầu đúng plugin artifact.
- `<configuration>`: mapping tham số Maven sang fields `greeting`, `recipient` của Mojo.
- `<executions>`: khai báo **khi nào goal chạy trong lifecycle**.
- `<phase>validate</phase>`: bind `greet` vào phase đầu của lifecycle.
- `<goal>greet</goal>`: tên goal phải khớp `@Mojo(name = "greet")` và descriptor.
- POM properties `notice.*`: cung cấp defaults và cho phép user properties từ CLI override nhất quán.

Tự thêm `<configuration>` mà **không có `<executions>`** sẽ không làm goal chạy trong lifecycle; người dùng vẫn có thể gọi trực tiếp goal khi cần.

### 15.2. Vì sao không dùng `<pluginManagement>` để chạy goal?

`<pluginManagement>` dùng để **quản lý phiên bản/cấu hình mặc định của plugin cho những nơi áp dụng plugin**, chứ không tự kích hoạt một goal của plugin chưa được dùng. Nếu consumer chỉ khai báo:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>dev.learning.plugins</groupId>
            <artifactId>notice-maven-plugin</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </plugin>
    </plugins>
</pluginManagement>
```

thì chạy `mvn validate` **không tự log lời chào**. Phải có plugin được sử dụng ở `<build><plugins>` và execution phù hợp.

## 16. Gọi plugin từ consumer và output mong đợi

Sau `mvn -f plugin/pom.xml clean install`, chạy:

```bash
mvn -B -ntp -f consumer/pom.xml validate
```

Vì consumer bind goal ở phase `validate` và có mặc định `Welcome`/`Team`, **message chính xác được Mojo chuyển cho Maven logger** là:

```text
Welcome, Team!
```

Trong console Maven thật, bạn thường thấy một dòng dạng:

```text
[INFO] Welcome, Team!
```

Còn có log Maven về project/plugin execution và `BUILD SUCCESS`; **không coi dòng message là toàn bộ stdout**.

### 16.1. Override qua user property

```bash
mvn -B -ntp -f consumer/pom.xml validate \
    -Dnotice.greeting=Hello \
    -Dnotice.recipient=CI
```

Message dự kiến từ Mojo:

```text
Hello, CI!
```

Do consumer `<configuration>` dùng `${notice.greeting}` và `${notice.recipient}`, Maven CLI user properties có thể override các POM properties tương ứng.

### 16.2. Gọi full plugin coordinates trực tiếp

Không cần lifecycle binding mới có thể gọi goal:

```bash
mvn -B -ntp -f consumer/pom.xml \
    dev.learning.plugins:notice-maven-plugin:1.0.0-SNAPSHOT:greet \
    -Dnotice.greeting=Hi \
    -Dnotice.recipient=CLI
```

Message mong đợi:

```text
Hi, CLI!
```

Cú pháp tổng quát:

```text
mvn groupId:artifactId:version:goal
```

Đây là cách **rõ ràng nhất** khi Maven chưa biết short prefix hoặc cần xác định chính xác version.

### 16.3. Không chạy plugin từ chính source project để chứng minh install

Nếu gọi goal từ plugin project mà chưa install hoặc chưa có plugin descriptor, lỗi resolution/self-invocation có thể gây nhầm. Với mục đích kiểm **artifact đã đóng gói**, build/install plugin trước rồi chạy **consumer project riêng** trong một Maven invocation khác.

## 17. Prefix `notice:greet` và pluginGroups

Maven cho phép cú pháp rút gọn:

```text
mvn notice:greet
```

nhưng Maven phải **resolve prefix `notice` về GAV của một plugin**. Tên `notice-maven-plugin` hỗ trợ quy ước suy ra prefix; `goalPrefix` trong Plugin Tools mô tả prefix plugin. Tuy nhiên việc nhận diện plugin có thể phụ thuộc:

- Plugin có trong `<build><plugins>`/`pluginManagement` của project.
- Plugin group có trong `settings.xml` `<pluginGroups>`.
- Repository metadata về plugin prefix đã được publish/resolve.
- POM, Maven version, local repository và network availability.

Để Maven tìm plugin ở group tùy biến khi chưa khai báo plugin trong POM, user settings có thể chứa:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <pluginGroups>
        <pluginGroup>dev.learning.plugins</pluginGroup>
    </pluginGroups>
</settings>
```

Đây là **mảnh settings minh họa**, không thay thế settings thật nếu tổ chức có mirrors/credentials/proxies. Không cần sửa settings trong bài vì consumer POM đã khai báo plugin, và lệnh full GAV chắc chắn hơn khi chẩn đoán.

**Không dựa vào việc omit version** như một release strategy. Pin plugin version rõ ràng trong consumer hoặc parent pluginManagement để tránh build thay đổi do plugin mới xuất hiện.

## 18. Kiểm tra goal metadata bằng Maven Help Plugin

Có thể hỏi Help Plugin về plugin và goal đã install:

```bash
mvn -B -ntp -f consumer/pom.xml \
    org.apache.maven.plugins:maven-help-plugin:3.5.1:describe \
    -Dplugin=dev.learning.plugins:notice-maven-plugin:1.0.0-SNAPSHOT \
    -Dgoal=greet \
    -Ddetail
```

Help Plugin có thể hiển thị:

- Plugin name/GAV/version/description.
- Goal `greet` và implementation metadata.
- Parameters `greeting`, `recipient`.
- User properties `notice.greeting`, `notice.recipient`.
- Goal requirements và các flags cần biết.

Output phụ thuộc Maven/plugin tools versions và tài liệu Javadoc trong descriptor; không trình bày một transcript cố định. Nếu Help Plugin không thấy goal, **đọc plugin descriptor và kiểm packaging/plugin extraction** thay vì đổi ngẫu nhiên Maven goal syntax.

### 18.1. HelpMojo do Maven Plugin Plugin sinh

Cấu hình:

```xml
<execution>
    <id>generate-plugin-help</id>
    <goals>
        <goal>helpmojo</goal>
    </goals>
</execution>
```

sẽ sinh code của một `help` goal cho plugin trong generated sources khi lifecycle/plugin version phù hợp. Đây là **goal khác**, không phải `greet`. Khi plugin đã install, có thể thử:

```bash
mvn -B -ntp -f consumer/pom.xml \
    dev.learning.plugins:notice-maven-plugin:1.0.0-SNAPSHOT:help \
    -Ddetail=true
```

Tùy Plugin Tools version, `helpmojo` goal/documentation cần được sinh và đóng gói trước khi xuất hiện; không nhầm Maven Help Plugin `help:describe` với goal `notice:help` của chính plugin.

## 19. Cần test Mojo như thế nào ngoài unit tests?

Một plugin project cần nhiều tầng QA, vì một unit test của class thuần Java chỉ kiểm business logic:

| Mức QA | Kiểm gì | Công cụ/cách làm |
| --- | --- | --- |
| Unit test | Formatter/validators Java | JUnit Jupiter |
| Packaging check | Descriptor và classes có trong JAR | `jar tf`, descriptor read |
| Goal metadata | Goal/params được nhận dạng | Maven Help Plugin `describe` |
| Consumer smoke | Plugin inject config và thực thi | POM consumer riêng, `mvn validate` |
| Negative config | Blank input gây `MojoFailureException` | Chạy consumer trên profile/arg lỗi riêng |
| Integration tests tự động | Nhiều mẫu consumer POM/outputs | Maven Plugin Testing Harness/Invoker Plugin |
| Compatibility | Maven/JDK platforms được hỗ trợ | CI matrix |
| Release QA | Artifact đã install/deploy có thể resolve | Repo staging/consumer check |

### 19.1. Vì sao test trực tiếp new GreetMojo() không đủ?

Nếu gọi `new GreetMojo().execute()` ngoài Maven container, các private fields có `@Parameter` **không tự được inject**; giá trị có thể `null`. Tương tự `getLog()` có thể có behavior khác context Maven thật. Cách test direct Mojo đúng có thể dùng harness để tạo component container và fixture POM, hoặc tách logic cần test như `GreetingText` rồi kiểm full integration từ consumer.

### 19.2. Maven Plugin Testing Harness

Apache Maven cung cấp testing utilities để test Mojo lookup, configuration và execution trong Maven-like context. Khi dùng cần pin dependency `maven-plugin-testing-harness`/JUnit framework tương thích với Maven Plugin API và Plugin Tools version; không nhét nó vào POM tối thiểu nếu chưa cần.

### 19.3. Maven Invoker Plugin

Invoker Plugin có thể thực thi **một Maven build khác** dựa trên projects fixtures và kiểm exit code/expected results. Dùng nó rất hợp cho plugin integration tests vì goal của plugin chỉ bộc lộ đầy đủ behavior khi Maven đọc POM và tạo plugin realm/descriptor. Khi tích hợp Invoker trong một repository lớn, cấu hình cụ thể version, fixtures, pre/post-build hooks và goals phải được kiểm với Maven/JDK CI đang dùng.

**Trong bài này, `consumer/pom.xml` là integration smoke thủ công đầy đủ và runnable**, đủ để chứng minh goal được load từ plugin artifact đã install.

## 20. Phân biệt plugin lifecycle của producer và goal lifecycle của consumer

Đây là hai khái niệm dễ bị hiểu sai:

1. **Plugin producer build lifecycle:** Khi ở `plugin/`, lệnh `mvn package` dùng `<packaging>maven-plugin</packaging>` để compile Mojo classes, sinh descriptor và đóng gói JAR plugin.
2. **Consumer build lifecycle:** Khi ở `consumer/`, lệnh `mvn validate` chạy goal `greet` vì consumer đã **bind** plugin execution vào phase đó.

`packaging=maven-plugin` trong producer **không khiến** goal `greet` tự chạy ở mọi project khác. `@Mojo(name="greet")` cũng **không** làm goal tự gắn vào phase `validate` của consumer.

Sơ đồ:

```text
PLUGIN PRODUCER                           CONSUMER
  pom: packaging=maven-plugin             pom: packaging=pom
         |                                       |
  compile GreetMojo.class                 resolve plugin JAR + POM
         |                                       |
  generate META-INF/maven/plugin.xml      read plugin descriptor
         |                                       |
  package plugin JAR                      bind greet to validate
         |                                       |
  install plugin artifact ----------------> call GreetMojo.execute()
```

Người học có thể dùng cùng Maven executable cho cả hai dự án, nhưng đó là **hai Maven invocations và hai POM độc lập**.

## 21. `defaultPhase`, `requiresProject` và tính thread-safe

### 21.1. Goal name và default phase

Annotation tối giản:

```java
@Mojo(name = "greet")
```

nói lên goal name. Annotation mở rộng có thể chỉ định:

```java
@Mojo(
    name = "greet",
    defaultPhase = LifecyclePhase.VALIDATE,
    threadSafe = true
)
```

Nếu dùng fragment này, cần import `org.apache.maven.plugins.annotations.LifecyclePhase`. Đây là **fragment lựa chọn**, không thay trực tiếp code GreetMojo của bài nếu bạn chưa quyết định lifecycle semantics.

`defaultPhase` là metadata về phase mặc định của goal trong các tình huống cấu hình có hỗ trợ; **nó không tự bind plugin vào tất cả projects**. Consumer `<executions>` vẫn là cách tường minh, dễ review và tái lập nhất.

### 21.2. `requiresProject`

Nhiều goals Maven mặc định cần chạy trong một Maven project; điều này phù hợp với ví dụ consumer có `pom.xml`. Nếu thiết kế utility goal không cần POM, có thể khai báo `requiresProject=false` khi nó thật sự không truy cập project data và đã kiểm cách gọi standalone.

Đừng tự thêm `requiresProject=false` chỉ vì muốn goal chạy mọi nơi: plugin có sử dụng `${project.*}` hoặc MavenProject sẽ cần được thiết kế và xử lý khi project không tồn tại.

### 21.3. Thread safety

`@Mojo(threadSafe=true)` là lời hứa của tác giả về tính an toàn khi Maven parallel reactor build. Nếu plugin sửa cùng một file cố định, dùng static global mutable state hoặc thao tác vào thư mục chia sẻ, flag này có thể sai. Với plugin thao tác filesystem, cần guard concurrency, path scope, locking hoặc bỏ flag cho tới khi có QA đầy đủ.

## 22. Maven plugin dependencies và plugin realm

Plugin chạy bên trong Maven, nhưng dependencies của plugin có **scope và class loading** riêng. Những điểm chính:

- `maven-plugin-api` thường để `provided` để tránh đóng gói bản Maven core khác vào plugin realm và giảm conflict.
- `maven-plugin-annotations` thường `provided`, dùng để build metadata.
- Một thư viện bên ngoài mà Mojo **thực sự gọi ở runtime** cần được cung cấp qua plugin dependencies phù hợp, không mặc định lấy từ project dependencies của consumer.
- JUnit/test harness là **test dependencies** cho plugin project, không được đóng như production runtime dependency.
- Dependency management/BOM của plugin producer có thể quản lý versions; consumer project `<dependencyManagement>` **không tự thay mọi dependency của plugin realm** theo cùng cách với project classpath.
- Plugin version và Maven runtime API version cần được chọn theo **compatibility policy**, đặc biệt khi hỗ trợ Maven 3 và Maven 4.

### 22.1. Ví dụ library riêng cho Mojo

Nếu sau này Mojo dùng thư viện `org.apache.commons:commons-lang3`, nên khai báo trong **POM plugin project** với scope phù hợp, ví dụ:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

Đây là **đoạn mở rộng minh họa**, không cần cho runnable example hiện tại. Nếu chỉ đưa Commons Lang vào `consumer/pom.xml` `<dependencies>`, Mojo có thể không thấy nó khi Maven tạo plugin class realm.

### 22.2. Class realm issues không đồng nghĩa Java compiler errors

- `package ... does not exist` khi compile Mojo: POM plugin thiếu dependency/import sai.
- `NoClassDefFoundError` khi gọi goal: plugin runtime realm thiếu class/version.
- `ClassCastException` giữa Maven APIs: có thể do API/realm incompatibility hoặc đóng gói Maven core class không phù hợp.
- `PluginDescriptorParsingException` hoặc `No plugin descriptor found`: plugin JAR thiếu/không đọc được descriptor.

Cần xác định **thời điểm lỗi** trước khi sửa XML.

## 23. Multi-module plugin repository

Trong một hệ thống lớn, có thể tách logic dùng lại và plugin wrapper:

```text
build-tooling/
├── pom.xml                  (packaging=pom; modules)
├── rule-engine/
│   └── pom.xml              (packaging=jar)
└── notice-maven-plugin/
    └── pom.xml              (packaging=maven-plugin)
```

Parent/aggregator root có:

```xml
<packaging>pom</packaging>
<modules>
    <module>rule-engine</module>
    <module>notice-maven-plugin</module>
</modules>
```

Từng module có GAV và dependency graph riêng. Plugin module phải khai báo dependency vào `rule-engine` với tọa độ/version phù hợp, chứ **không chỉ thêm module vào `<modules>`** và nghĩ compiler tự thấy code.

Cảnh báo:

- Dùng Reactor để build plugin và library cùng nhau là bình thường.
- Khi **test artifact consumer độc lập**, cần chắc plugin JAR/POM cùng dependency library đã được `install` hoặc `deploy`; đừng để một test trong cùng Reactor che lỗi published metadata.
- Tránh cycle: plugin module được dùng làm build plugin của parent đang build chính plugin đó trước khi nó được tạo, dễ gây vòng phụ thuộc/self-bootstrap.
- Nếu build tooling được dùng bởi nhiều modules, quản lý versions bằng parent `pluginManagement`, rồi **kích hoạt ở các module cần chạy**.

Root aggregator nên dùng `packaging=pom`, không đổi toàn bộ root thành `maven-plugin` chỉ vì một module con là plugin.

## 24. `install`, `deploy` và consumer độc lập

Đối với project plugin:

```bash
mvn -B -f plugin/pom.xml clean install
```

cài JAR/POM plugin vào local repository. Project consumer trên cùng môi trường có thể resolve GAV để chạy goal.

Để người khác hoặc CI tải plugin, cần publish đến Maven repository đúng quyền và policy:

```text
Plugin source → clean verify → package descriptor JAR
              → install / deploy to staging
              → independent consumer smoke
              → approved release promotion
```

Một `mvn deploy` đến production cần `distributionManagement`, repository ID, credentials trong settings/CI secrets và phê duyệt. **Bài này không cấu hình URL/credentials production** và không yêu cầu deploy thật.

### 24.1. SNAPSHOT trong ví dụ

`1.0.0-SNAPSHOT` phục vụ phát triển. Khi làm release:

- Pin release version theo policy.
- Không publish đè mutable release GAV vào repository có immutability.
- So POM/descriptor/JAR và dependencies đúng candidate.
- Chạy consumer smoke bằng artifact đã staged, **không chỉ dùng `target/classes`**.
- Giữ Maven/JDK compatibility matrix và thông báo breaking changes của parameters/goals.
- Không để plugin tự tải code không kiểm soát hoặc ghi files ngoài workspace mà không có user consent phù hợp.

### 24.2. Plugin group và discoverability

`dev.learning.plugins` không thuộc plugin group mặc định của Apache. Các dự án nên **khai báo full GAV trong POM** để build tái lập. `mvn notice:greet` phụ thuộc prefix resolution; có thể cấu hình `<pluginGroups>` trong settings nhưng đó là convenience cho CLI, không thay version pinning.

## 25. Lỗi thường gặp khi tạo một Maven plugin

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `package org.apache.maven.plugin does not exist` | Thiếu `maven-plugin-api` | Thêm dependency Maven Plugin API phù hợp |
| `package org.apache.maven.plugins.annotations does not exist` | Thiếu `maven-plugin-annotations` | Thêm annotations dependency, scope provided |
| `Invalid packaging: maven-plugin` | Maven/plugin lifecycle extension không có/không hoạt động hoặc POM/typo | Kiểm Maven version và đúng spelling `maven-plugin` |
| Plugin compile nhưng JAR không có `plugin.xml` | Packaging `jar`, descriptor goal chưa chạy hoặc Plugin Tools lỗi | Kiểm packaging, `plugin:descriptor`, build logs |
| `No plugin descriptor found` | JAR không có `META-INF/maven/plugin.xml` | `jar tf`, rebuild đúng plugin lifecycle |
| `No goal named 'greet'` | `@Mojo` thiếu/sai tên, descriptor stale | Xem `plugin.xml`, clean package |
| `Mojo not found` | GAV/version/goal không đúng | Full coordinates và descriptor check |
| `Plugin ... could not be resolved` | Chưa install/deploy, local repo khác, mirror/credentials lỗi | Kiểm repository path và GAV |
| `Prefix 'notice' not found` | Chưa cấu hình pluginGroup/metadata/POM | Dùng full plugin GAV để phân biệt |
| `mvn validate` không log lời chào | Consumer thiếu `<executions>` hoặc phase/goal sai | Xem effective POM và plugin execution |
| Chỉ có `pluginManagement` mà goal không chạy | Management không tự kích hoạt plugin | Thêm plugin vào `<build><plugins>` |
| `@Parameter` không nhận `-D` | POM explicit literal override hoặc property name sai | Kiểm `<configuration>` và `${notice.*}` |
| `MavenProject` symbol not found | Thiếu Maven API/core tương ứng | Khai báo đúng dependency hoặc bỏ injection |
| `Unsupported class file major version` | Plugin build trên JDK cao hơn Maven JVM consumer | Pin compiler release và test compatibility |
| `NoClassDefFoundError` trong Mojo | Plugin realm thiếu runtime dependency | Kiểm dependencies **của plugin project** |
| JUnit test pass nhưng consumer fail | Unit test không chạy descriptor/parameter injection | Tạo independent consumer smoke |
| `0 tests` nhưng build success | Surefire discovery/skip flags sai | `failIfNoTests`, TEST-*.xml |
| Maven 4 runtime dùng Maven 3 API plugin lỗi | Compatibility/injection API thay đổi | Theo guidance Maven 4 và test version matrix |
| HelpMojo không được sinh | Plugin Plugin execution/config không đúng | Xem generated sources và `helpmojo` goal |
| `threadSafe` warning | Plugin không khai báo an toàn cho parallel builds | Kiểm shared state, annotate đúng khi đảm bảo |
| Goal ghi đè file user | Plugin không kiểm output path và validation | Scope paths, dry-run và guard overwrite |
| `mvn -o` không tải plugin mới | Offline cache chưa có artifact | Bỏ offline khi cần resolve, dùng approved repo |
| Plugin dùng tên `maven-xyz-plugin` | Không đúng quy ước bên thứ ba | Dùng `xyz-maven-plugin` |
| Consumer POM khai báo plugin trong dependencies | Maven không chạy goal từ đó | Chuyển sang `<build><plugins>` |
| Plugin bị sửa generated descriptor thủ công | `clean` làm mất fix | Sửa annotations/POM rồi rebuild |
| Plugin tải phiên bản SNAPSHOT cũ | Cache/updatePolicy khác | Kiểm GAV, metadata và artifact origin |

### 25.1. Thứ tự gỡ lỗi tối ưu

1. Plugin producer POM có `<packaging>maven-plugin</packaging>` đúng chính tả không?
2. Maven Compiler Plugin có compile được `GreetMojo` và `GreetingText` không?
3. `maven-plugin-api` và annotations có được khai báo đúng version/scope?
4. Maven Plugin Plugin có chạy `plugin:descriptor` theo lifecycle không?
5. `target/classes/META-INF/maven/plugin.xml` có goal `greet` không?
6. JAR cuối có descriptor và `GreetMojo.class` không?
7. `mvn clean install` producer có thành công và POM/JAR vào đúng local repository không?
8. Consumer khai báo plugin dưới `<build><plugins>` với GAV/version đúng không?
9. `mvn validate` có execution bind `greet` vào `validate` không?
10. Help Plugin `describe` có nhận goal/parameters không?
11. Nếu lỗi runtime, dependencies nằm trong **plugin realm** hay chỉ trong project classpath?
12. Nếu lỗi platform, Maven/JDK versions có đạt compatibility policy không?

Không sửa tất cả vấn đề một lúc. Thay một biến, chạy lại đúng Maven goal và xác minh logs/descriptor.

## 26. Negative tests: chứng minh cấu hình nào phải fail

Các thử nghiệm này chỉ thực hiện trên **copy/branch học tập**, không sửa published plugin đang được người khác dùng.

### 26.1. Đổi packaging thành jar

Giữ Java @Mojo nhưng dùng:

```xml
<packaging>jar</packaging>
```

Nếu không chủ động cấu hình descriptor generation, Maven lifecycle JAR mặc định **không tự cung cấp đủ plugin-specific metadata**. JAR có thể được tạo nhưng thiếu `META-INF/maven/plugin.xml`; consumer goal không hoạt động như một plugin hợp lệ. Đổi lại `maven-plugin` để khôi phục.

### 26.2. Bỏ @Mojo annotation

Giữ `GreetMojo extends AbstractMojo` nhưng bỏ `@Mojo`. Plugin Tools không có khai báo goal `greet` trên class này, nên descriptor không có goal tương ứng, hoặc plugin validation phát hiện thiếu goal. **Java compile đơn thuần vẫn có thể pass**, nhưng artifact không đạt yêu cầu.

### 26.3. Không install plugin trước consumer

Trong một local repository mới, chạy consumer mà chưa install/deploy producer plugin. Maven có thể fail plugin resolution. Đây là **lỗi availability**, không phải lỗi `@Parameter`.

### 26.4. Đưa plugin vào dependencies thay vì build plugins

Consumer có JAR plugin trong project classpath nhưng không có plugin execution. Chạy `mvn validate` không tự gọi `GreetMojo`. Đây là lỗi **phân loại dependency vs build plugin**.

### 26.5. Truyền recipient rỗng

Nếu consumer `<configuration>` dùng POM property như phần 15, chạy:

```bash
mvn -B -ntp -f consumer/pom.xml validate \
    -Dnotice.recipient=" "
```

Dự kiến formatter ném `IllegalArgumentException` và Mojo chuyển thành `MojoFailureException` với nội dung lỗi:

```text
recipient must not be blank
```

Maven build thất bại có chủ đích. Đây là thông điệp logic, không phải transcript cố định của Maven CLI. Đổi lại `-Dnotice.recipient=Team` trước khi kiểm build thành công.

### 26.6. Bỏ JUnit dependency

Production Mojo vẫn compile nhưng `testCompile` sẽ không tìm thấy `org.junit.jupiter.api.Test`; đây là lỗi test classpath, không liên quan Plugin Tools descriptor.

### 26.7. Dùng JDK quá cũ cho Java 17 bytecode

Plugin producer compile với release 17, consumer Maven chạy JVM không hỗ trợ class-file version 61 sẽ lỗi khi load plugin class. Đừng giải quyết bằng cách khai báo sai JVM minimum requirement; hãy build plugin về Java version thực sự được hỗ trợ hoặc nâng runtime theo policy.

## 27. Security và chất lượng khi mở rộng Maven bằng code

Maven plugin là **code chạy trong build process**, thường có quyền đọc/ghi source/output và có thể tiếp cận environment variables. Vì vậy:

- Chỉ chạy plugin từ repository và publisher đáng tin.
- Pin plugin GAV/version; quản lý BOM/parent/pluginManagement có review.
- Không log server passwords, tokens hoặc contents nhạy cảm từ project.
- Không mặc định chạy commands shell hoặc tải code Internet bên ngoài Maven dependency policy.
- Khi viết file, giới hạn output trong workspace được phép, kiểm path traversal và guard overwrite.
- Khai báo `threadSafe` chỉ khi logic chịu được parallel Maven Reactor.
- Không dùng static mutable state chia sẻ giữa modules.
- Tránh làm lifecycle fork không cần thiết; nó có thể tạo recursion và thêm phase bất ngờ.
- Viết tests cho lỗi validation và failure mode, không chỉ happy path.
- Cung cấp plugin docs về parameters, default values, goals, Maven/JDK minimum versions.
- Dùng staging repository và consumer tests trước khi release; kiểm checksum/provenance khi có yêu cầu.
- Tránh dùng packages/classes nội bộ của Maven core khi API công khai đáp ứng được nhu cầu; nội bộ có thể đổi giữa Maven 3 và Maven 4.

**Ghi chú:** `provided` của Maven Plugin API không phải một quyền truy cập đặc biệt hoặc cơ chế sandbox bảo mật. Nó là Maven dependency scope. Maven plugin vẫn là executable code; artifact source phải được tin cậy.

## 28. Câu hỏi tự kiểm tra

**1. Vì sao `packaging=maven-plugin` vẫn tạo `.jar`?**

Vì Maven plugin thường là JAR chứa các Mojo classes, nhưng có lifecycle bổ sung để tạo descriptor/metadata cho Maven đọc. Đuôi JAR không nói lên role plugin.

**2. `@Mojo(name="greet")` có nghĩa Maven gọi method `greet()` không?**

Không. `greet` là goal name; Maven gọi `execute()` của implementation class.

**3. Class nào cung cấp `getLog()` trong ví dụ?**

`AbstractMojo` thuộc Maven Plugin API. Plugin logging giúp tích hợp với Maven console/build infrastructure.

**4. Có cần viết tay `META-INF/maven/plugin.xml` không?**

Không trong mô hình annotations. Maven Plugin Plugin phân tích @Mojo/@Parameter và sinh descriptor để đóng vào JAR.

**5. Vì sao `maven-plugin-api` và `maven-plugin-annotations` để `provided`?**

Chúng phục vụ compile/runtime Maven API và metadata annotation trong Maven 3; tránh đóng gói API/runtime không cần thiết. Scope phải được kiểm theo version/support policy của plugin thực.

**6. Có thể đưa plugin GAV vào consumer `<dependencies>` để goal tự chạy không?**

Không. Consumer cần `<build><plugins>` và execution/goal invocation phù hợp.

**7. Chỉ có `<pluginManagement>` thì `mvn validate` có chạy goal?**

Không. Nó quản lý defaults/versions nhưng không kích hoạt một custom goal chưa được sử dụng.

**8. Vì sao consumer phải chạy sau producer `install`?**

Để Maven resolve được plugin artifact JAR/POM từ local repository thay vì dùng source code chưa publish.

**9. `defaultPhase=VALIDATE` trong @Mojo có tự gắn goal vào mọi project?**

Không. Consumer cần cấu hình plugin execution hoặc một lifecycle mapping khác cố ý sử dụng goal.

**10. Vì sao `mvn notice:greet` có thể fail dù full GAV goal chạy?**

Plugin prefix resolution cần POM/pluginGroups/repository metadata phù hợp. Full coordinates loại bỏ phần lớn mơ hồ về prefix và version.

**11. Unit tests của GreetingText có đủ chứng minh descriptor đúng không?**

Không. Cần kiểm JAR/descriptor và chạy goal từ consumer Maven project riêng.

**12. Nếu goal cần Commons Lang ở runtime, khai báo ở POM nào?**

POM **plugin producer** hoặc plugin dependencies phù hợp; project dependencies của consumer không tự cung cấp class cho plugin realm.

## 29. Checklist bài thực hành và nghiệm thu plugin project

- [ ] Project POM khai báo `packaging=maven-plugin`, không phải `jar`?
- [ ] Artifact ID dùng naming convention `notice-maven-plugin`, không chiếm prefix tên Apache?
- [ ] Source file paths, `package` statements và Java class names khớp?
- [ ] `maven-plugin-api` và `maven-plugin-annotations` có dependency đúng?
- [ ] Compiler release và Maven/JDK versions phù hợp với plugin users?
- [ ] `@Mojo(name="greet")` có implementation `execute()` hợp lệ?
- [ ] `@Parameter` ghi đúng user property names và default values?
- [ ] Các tham số sai bị validate và ném Maven exception phù hợp?
- [ ] Maven Plugin Plugin được pin và tạo descriptor đúng lifecycle?
- [ ] `plugin.xml` có trong `target/classes/META-INF/maven` và JAR cuối?
- [ ] Descriptor có goal name `greet` và implementation class chính xác?
- [ ] Pure Java logic có 4 JUnit 5 tests, errors/failures/skipped bằng 0?
- [ ] `clean verify` plugin producer thành công?
- [ ] `clean install` đưa JAR + POM vào đúng local Maven repository?
- [ ] Consumer POM riêng khai báo plugin dưới `<build><plugins>`?
- [ ] Consumer `<executions>` bind goal `greet` ở phase `validate`?
- [ ] `mvn -f consumer/pom.xml validate` log `Welcome, Team!`?
- [ ] CLI override qua `-Dnotice.greeting`/`-Dnotice.recipient` hoạt động?
- [ ] Full GAV goal invocation và Help Plugin `describe` nhận goal?
- [ ] Đã hiểu giới hạn của short prefix resolution/pluginGroups?
- [ ] Không trộn application dependency với plugin dependency/class realm?
- [ ] Khi cần, đã bổ sung Maven Invoker/Testing Harness integration QA?
- [ ] Không đọc/ghi ngoài workspace, không log secrets và không lạm dụng threadSafe?
- [ ] Nếu phát hành, dùng staged repo, version pinning và consumer QA?
- [ ] Artifact đã QA chính là artifact được promote, không bị rebuild tùy tiện?

**Kết luận:** một Maven plugin project tiêu chuẩn không chỉ là Java JAR. **`packaging=maven-plugin` lựa chọn plugin lifecycle**, `@Mojo` và `@Parameter` mô tả goals, Maven Plugin Tools tạo **`META-INF/maven/plugin.xml`** và đóng descriptor vào JAR để Maven nạp/gọi plugin. Hãy tách logic Java khỏi Mojo, viết unit tests, build/install plugin rồi kiểm goal trên **consumer POM độc lập**, có `<build><plugins>` và execution gắn phase phù hợp. Hiểu đúng ranh giới giữa plugin project, project dependency, plugin realm và lifecycle là nền tảng để mở rộng Maven một cách tái lập, có kiểm soát.

### Tài liệu tham khảo chính thức

- [Apache Maven — Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development)
- [Apache Maven Plugin Tools — Introduction](https://maven.apache.org/plugin-tools/)
- [Maven Plugin Plugin — Usage](https://maven.apache.org/plugin-tools/maven-plugin-plugin/usage.html)
- [Maven Plugin Plugin — Using Java Annotations](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/using-annotations.html)
- [Maven Plugin Plugin — Plugin Descriptor](https://maven.apache.org/plugin-tools/maven-plugin-plugin/descriptor-mojo.html)
- [Maven Plugin Plugin — HelpMojo](https://maven.apache.org/plugin-tools/maven-plugin-plugin/helpmojo-mojo.html)
- [Apache Maven — Plugin Prefix Mapping](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html)
- [Apache Maven — Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Guide to Testing Maven Plugins](https://maven.apache.org/plugin-developers/plugin-testing.html)
