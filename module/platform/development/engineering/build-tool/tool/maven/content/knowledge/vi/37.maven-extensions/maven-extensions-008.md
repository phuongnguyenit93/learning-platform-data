# Kiểm thử plugin bằng dự án mẫu và kiểm chứng gọi qua Maven

> **Mở rộng Maven — Build Tool Maven.** Bài học hướng dẫn kiểm chứng một plugin Maven tự viết bằng cách chạy **một dự án consumer độc lập**. Không chỉ unit test cho Java code, chúng ta còn kiểm plugin descriptor, gọi goal trực tiếp với tọa độ đầy đủ, gắn goal vào lifecycle, kiểm tham số được inject, kiểm file đầu ra và tự động hóa bằng Maven Invoker Plugin.

## 1. Maven plugin cần được kiểm thử theo nhiều lớp

Maven plugin là một artifact chứa các **Mojo** mà Maven có thể thực thi. Một class Java chạy đúng khi JUnit gọi trực tiếp chưa chứng minh Maven có thể sử dụng class đó. Maven còn phải:

1. Resolve artifact theo **groupId:artifactId:version**.
2. Mở plugin JAR và đọc **META-INF/maven/plugin.xml**.
3. Nhận diện goal, các tham số và requirements.
4. Inject giá trị từ POM, command line và ngữ cảnh Maven project.
5. Chạy goal trong đúng phase/execution và đúng consumer module.
6. Xử lý output/exit code khi thành công hay lỗi.

| Lớp QA | Kiểm điều gì? | Chưa kiểm được gì? |
| --- | --- | --- |
| JUnit cho helper | Logic format, Unicode, newline | Metadata và Maven injection |
| Plugin descriptor | Maven nhận ra goal/parameters | Goal thực sự tạo output đúng |
| CLI goal invocation | Maven resolve plugin và gọi goal thật | Lifecycle binding |
| Consumer lifecycle test | Goal chạy đúng phase và output được assert | Mọi version JDK/Maven |
| Invoker fixtures | Maven chạy nhiều sample projects tự động | Những scenarios chưa được xây |

**Mục tiêu của bài:** chứng minh Maven có gọi đúng goal từ đúng artifact, tạo đúng file tại đúng project, và build fail khi input sai. **BUILD SUCCESS** một mình là chưa đủ.

## 2. Dự án thực hành

Tạo thư mục **plugin-lab** chứa hai project Maven độc lập:

~~~text
plugin-lab/
├── demo-maven-plugin/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/lesson/plugin/
│       │   ├── EmitMojo.java
│       │   └── MessageText.java
│       └── test/java/dev/lesson/plugin/MessageTextTest.java
└── sample-consumer/
    ├── pom.xml
    └── src/
        ├── main/java/dev/lesson/consumer/ConsumerApp.java
        └── test/java/dev/lesson/consumer/PluginOutputTest.java
~~~

Plugin: **dev.lesson:demo-maven-plugin:1.0.0**. Goal: **emit**. Khi Maven consumer gọi goal, plugin viết file **sample-consumer/target/plugin-message.txt**, nội dung UTF-8:

~~~text
PLUGIN_MESSAGE=Hello Maven
~~~

Có một LF cuối file. Dự án mẫu phải đọc đúng file đó, không tự tạo file để qua test.

**Yêu cầu:** JDK 17, Maven 3.9.x (bản tham chiếu 3.9.16), Maven Central/mirror được phép để resolve plugins/dependencies. Ví dụ chỉ install plugin vào local repository thử nghiệm, không publish server từ xa.

## 3. Plugin POM đầy đủ

Tệp **demo-maven-plugin/pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>demo-maven-plugin</artifactId>
    <version>1.0.0</version>
    <packaging>maven-plugin</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <plugin.tools.version>3.16.0</plugin.tools.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-plugin-api</artifactId>
            <version>3.9.16</version>
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
                <artifactId>maven-plugin-plugin</artifactId>
                <version>${plugin.tools.version}</version>
                <configuration>
                    <goalPrefix>demo</goalPrefix>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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

### Vì sao cấu hình như vậy?

- **packaging=maven-plugin** kích hoạt lifecycle dành cho Maven plugin, gồm xử lý descriptor; không dùng packaging jar thông thường.
- **maven-plugin-api** cung cấp AbstractMojo, MojoExecutionException và MojoFailureException. Scope **provided** phù hợp vì Maven runtime cung cấp API tương ứng.
- **maven-plugin-annotations** cho phép Plugin Tools đọc @Mojo và @Parameter.
- **maven-plugin-plugin 3.16.0** sinh descriptor. Goal **plugin:descriptor** đã được bind theo plugin packaging, vì vậy không cần thêm execution descriptor trùng lặp.
- **goalPrefix=demo** mô tả prefix. Prefix lookup ở CLI còn chịu ảnh hưởng pluginGroups; ta ưu tiên gọi đầy đủ groupId/artifactId/version.
- JUnit Jupiter chỉ dùng ở test scope.
- Compiler release 17 là baseline của binary. Không tuyên bố plugin chạy trên Java 11 khi code dùng Java 17.
- Theo hướng dẫn chính thức, tên **prefix-maven-plugin** là dạng thường dùng cho plugin ngoài Apache Maven. Dạng **maven-prefix-plugin** được dành cho plugin của Apache Maven.

**Cảnh báo:** Plugin API tương thích với Maven runtime là một vấn đề riêng với Java bytecode target. Nếu muốn hỗ trợ nhiều phiên bản Maven, cần kiểm Maven/JDK compatibility matrix.

## 4. Java code cho plugin

Tệp **demo-maven-plugin/src/main/java/dev/lesson/plugin/MessageText.java**:

~~~java
package dev.lesson.plugin;

final class MessageText {
    private MessageText() {
    }

    static String render(String message) {
        return "PLUGIN_MESSAGE=" + message + "\n";
    }
}
~~~

Tệp **demo-maven-plugin/src/main/java/dev/lesson/plugin/EmitMojo.java**:

~~~java
package dev.lesson.plugin;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugin.MojoFailureException;
import org.apache.maven.plugins.annotations.LifecyclePhase;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

/**
 * Emits a UTF-8 file for the project invoking this Maven goal.
 */
@Mojo(
    name = "emit",
    defaultPhase = LifecyclePhase.GENERATE_RESOURCES,
    threadSafe = true
)
public final class EmitMojo extends AbstractMojo {

    @Parameter(property = "demo.message", defaultValue = "Hello Maven")
    private String message;

    @Parameter(
        defaultValue = "${project.build.directory}",
        readonly = true,
        required = true
    )
    private File buildDirectory;

    @Override
    public void execute()
            throws MojoExecutionException, MojoFailureException {
        if (message == null || message.isBlank()) {
            throw new MojoFailureException(
                "demo.message must not be blank");
        }

        Path output = buildDirectory.toPath()
                .resolve("plugin-message.txt");

        try {
            Files.createDirectories(output.getParent());
            Files.writeString(
                output,
                MessageText.render(message),
                StandardCharsets.UTF_8
            );
            getLog().info("WROTE plugin-message.txt");
        } catch (IOException e) {
            throw new MojoExecutionException(
                "Cannot write plugin-message.txt", e);
        }
    }
}
~~~

### Phân tích Mojo

**@Mojo(name="emit")** đặt tên goal. **defaultPhase=GENERATE_RESOURCES** là metadata của goal; nó **không tự bind** vào lifecycle của mọi consumer project khi plugin chỉ được khai trong build/plugins.

**threadSafe=true** là một cam kết của tác giả về khả năng chạy song song. Ví dụ dùng build directory riêng của mỗi project, không có shared mutable static state. Plugin thật phải kiểm race conditions trước khi công bố thuộc tính này.

**@Parameter(property="demo.message", defaultValue="Hello Maven")** cho phép người dùng truyền **-Ddemo.message=...**. **@Parameter(defaultValue="${project.build.directory}")** nhận thư mục target của project đang gọi goal. Đây là lý do phải kiểm bằng consumer POM: nếu chỉ tự new EmitMojo trong unit test, các trường chưa được Maven inject.

**MojoFailureException** mô tả input user không hợp lệ; **MojoExecutionException** chứa lỗi thực thi và cause I/O. **getLog().info** được tích hợp với Maven logging. **StandardCharsets.UTF_8** và LF trong MessageText giúp so chính xác nội dung.

Code chỉ viết dưới thư mục target của project; không sửa source/POM của consumer. Nếu thiếu quyền ghi, exception làm Maven fail; đây là hành vi đúng.

## 5. Unit test của plugin

Tệp **demo-maven-plugin/src/test/java/dev/lesson/plugin/MessageTextTest.java**:

~~~java
package dev.lesson.plugin;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class MessageTextTest {

    @Test
    void formatsWithPrefixAndLf() {
        assertEquals(
            "PLUGIN_MESSAGE=Hello Maven\n",
            MessageText.render("Hello Maven")
        );
    }

    @Test
    void preservesVietnameseText() {
        assertEquals(
            "PLUGIN_MESSAGE=Chào Maven\n",
            MessageText.render("Chào Maven")
        );
    }
}
~~~

Đây là hai unit tests nhanh. Chúng phát hiện lỗi format và Unicode nhưng **không thể chứng minh descriptor được tạo, goal được resolve, Maven inject fields hoặc goal chạy đúng phase**.

## 6. Build plugin và install vào isolated local repository

Từ root **plugin-lab**, Bash:

~~~bash
REPO="$(pwd)/.m2-lab"
mvn -B -ntp -Dmaven.repo.local="$REPO" \
  -f demo-maven-plugin/pom.xml clean install
~~~

PowerShell, viết trên một dòng để tránh khác biệt về ký tự xuống dòng của shell:

~~~powershell
$repo = Join-Path (Get-Location).Path ".m2-lab"
mvn -B -ntp "-Dmaven.repo.local=$repo" -f demo-maven-plugin/pom.xml clean install
~~~

Kết quả dự kiến:

1. Maven compile Java 17.
2. Maven Plugin Plugin xử lý Mojo annotations và tạo descriptor.
3. Surefire chạy MessageTextTest.
4. Maven đóng JAR plugin.
5. Install plugin artifact vào **.m2-lab**, không publish lên remote.

Đường dẫn Maven local repository dự kiến:

~~~text
.m2-lab/dev/lesson/demo-maven-plugin/1.0.0/
    demo-maven-plugin-1.0.0.jar
    demo-maven-plugin-1.0.0.pom
~~~

Lệnh **install** không phải **deploy**. Không cần repository publish URL hoặc credentials. Tham số **maven.repo.local** không bật offline; lần đầu Maven vẫn có thể tải artifacts từ nguồn được phép.

### Kiểm plugin descriptor nằm trong JAR

~~~bash
jar tf demo-maven-plugin/target/demo-maven-plugin-1.0.0.jar
~~~

Danh sách phải có:

~~~text
META-INF/maven/plugin.xml
~~~

Và thường có bản descriptor ở:

~~~text
demo-maven-plugin/target/classes/META-INF/maven/plugin.xml
~~~

Một phần descriptor minh họa:

~~~xml
<mojo>
    <goal>emit</goal>
    <implementation>dev.lesson.plugin.EmitMojo</implementation>
</mojo>
~~~

Đây chỉ là fragment, **không phải toàn bộ XML để copy**. Descriptor thật có metadata cho goals và parameters. Thiếu descriptor thì kiểm packaging, annotations, Plugin Plugin version và log plugin:descriptor; không nghĩ unit tests pass là đủ.

## 7. POM của dự án consumer

Tệp **sample-consumer/pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>sample-consumer</artifactId>
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
                <groupId>dev.lesson</groupId>
                <artifactId>demo-maven-plugin</artifactId>
                <version>1.0.0</version>
                <executions>
                    <execution>
                        <id>emit-consumer-message</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>emit</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <systemPropertyVariables>
                        <demo.output.file>${project.build.directory}/plugin-message.txt</demo.output.file>
                    </systemPropertyVariables>
                </configuration>
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

**Giải thích:**

- Custom plugin được khai ở **build/plugins**, không phải dependencies của Java application.
- Plugin version và GAV trùng bản đã install.
- Execution ID **emit-consumer-message** xác định lần gọi trong consumer.
- Phase **generate-resources** nằm trước compile/test, bảo đảm file được tạo trước khi consumer JUnit đọc nó.
- Surefire truyền system property **demo.output.file** tới JUnit để test biết file target. Đây là property cho **test**, khác **demo.message** là input của Mojo.
- POM không hardcode message, nên default là **Hello Maven**.

## 8. Consumer code và test xác nhận output thật

Tệp **sample-consumer/src/main/java/dev/lesson/consumer/ConsumerApp.java**:

~~~java
package dev.lesson.consumer;

public final class ConsumerApp {
    private ConsumerApp() {
    }

    public static String status() {
        return "CONSUMER_OK";
    }

    public static void main(String[] args) {
        System.out.println(status());
    }
}
~~~

Tệp **sample-consumer/src/test/java/dev/lesson/consumer/PluginOutputTest.java**:

~~~java
package dev.lesson.consumer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;

class PluginOutputTest {

    @Test
    void pluginCreatedFileInConsumerTarget() throws IOException {
        String fileName = System.getProperty("demo.output.file");
        assertNotNull(fileName, "Missing Surefire output property");

        Path output = Path.of(fileName);
        assertTrue(Files.isRegularFile(output));

        assertEquals(
            "PLUGIN_MESSAGE=Hello Maven\n",
            Files.readString(output, StandardCharsets.UTF_8)
        );
    }

    @Test
    void ordinaryJavaCodeRuns() {
        assertEquals("CONSUMER_OK", ConsumerApp.status());
    }
}
~~~

Test đầu tiên **không tạo generated file**. Nó bắt lỗi nếu Mojo không được gọi, ghi nhầm target, sai UTF-8 hoặc nội dung không đúng. Phải chạy **clean verify** để loại file cũ; nếu không, stale file từ lần trước có thể khiến test xanh giả khi goal bị tắt.

## 9. Kiểm gọi goal trực tiếp bằng Maven

Từ root **plugin-lab**, sau khi đã install plugin:

~~~bash
REPO="$(pwd)/.m2-lab"
mvn -B -ntp -Dmaven.repo.local="$REPO" \
  -f sample-consumer/pom.xml \
  dev.lesson:demo-maven-plugin:1.0.0:emit
~~~

Cú pháp fully qualified:

~~~text
groupId : artifactId : version : goal
dev.lesson : demo-maven-plugin : 1.0.0 : emit
~~~

Maven resolve đúng plugin, đọc descriptor, inject parameters và chạy **EmitMojo.execute()** trong consumer context.

Log dự kiến có dạng:

~~~text
[INFO] --- demo-maven-plugin:1.0.0:emit (default-cli) @ sample-consumer ---
[INFO] WROTE plugin-message.txt
[INFO] BUILD SUCCESS
~~~

**default-cli** thường là execution ID khi goal được gọi trực tiếp. Đọc output:

~~~bash
cat sample-consumer/target/plugin-message.txt
~~~

Kết quả hiển thị:

~~~text
PLUGIN_MESSAGE=Hello Maven
~~~

Tệp chứa LF cuối dòng. Lưu ý: **một lệnh gọi goal trực tiếp không tự chạy full lifecycle** đến compile/test. Đây là phép kiểm goal invocation, không phải full consumer QA.

Trên PowerShell:

~~~powershell
$repo = Join-Path (Get-Location).Path ".m2-lab"
mvn -B -ntp "-Dmaven.repo.local=$repo" -f sample-consumer/pom.xml dev.lesson:demo-maven-plugin:1.0.0:emit
Get-Content -Encoding UTF8 sample-consumer/target/plugin-message.txt
~~~

## 10. Kiểm goal qua lifecycle

Từ root **plugin-lab**:

~~~bash
REPO="$(pwd)/.m2-lab"
mvn -B -ntp -Dmaven.repo.local="$REPO" \
  -f sample-consumer/pom.xml clean verify
~~~

Điều cần xảy ra:

1. Clean xóa target consumer.
2. Phase generate-resources chạy **emit-consumer-message**.
3. Plugin ghi plugin-message.txt.
4. Compiler xử lý Java source và tests.
5. Surefire chạy PluginOutputTest, xác minh output file.
6. Maven tiến đến verify nếu tests pass.

Log minh họa:

~~~text
[INFO] --- demo-maven-plugin:1.0.0:emit (emit-consumer-message) @ sample-consumer ---
[INFO] WROTE plugin-message.txt
[INFO] --- maven-surefire-plugin:3.5.2:test (default-test) @ sample-consumer ---
[INFO] Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
[INFO] BUILD SUCCESS
~~~

Để kết luận plugin hoạt động, cần **cả goal banner và output assertion**. Nếu chỉ thấy BUILD SUCCESS nhưng không thấy goal banner, plugin có thể không hề được gọi.

Sau build, Java main:

~~~bash
java -cp sample-consumer/target/classes dev.lesson.consumer.ConsumerApp
~~~

Stdout chính xác:

~~~text
CONSUMER_OK
~~~

Đó là stdout của Java app, **khác log của Maven Mojo**.

## 11. Test cấu hình tham số

Mojo khai:

~~~java
@Parameter(property = "demo.message", defaultValue = "Hello Maven")
private String message;
~~~

Gọi goal với property CLI:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" \
  -f sample-consumer/pom.xml \
  "-Ddemo.message=Chào Maven" \
  dev.lesson:demo-maven-plugin:1.0.0:emit
~~~

File dự kiến là:

~~~text
PLUGIN_MESSAGE=Chào Maven
~~~

Để truyền message từ POM, thêm fragment sau vào khai báo plugin consumer:

~~~xml
<configuration>
    <message>Chào từ POM</message>
</configuration>
~~~

Khi đó file tương ứng:

~~~text
PLUGIN_MESSAGE=Chào từ POM
~~~

**Cảnh báo test:** JUnit consumer đang assert **Hello Maven**. Nếu đổi message rồi chạy **verify**, cần điều chỉnh expected value hoặc test configuration theo use case mới. Không bỏ assert để làm build xanh.

### Negative test input blank

Trong Bash:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" \
  -f sample-consumer/pom.xml \
  "-Ddemo.message=   " \
  dev.lesson:demo-maven-plugin:1.0.0:emit
~~~

Khi CLI truyền giá trị chỉ gồm dấu cách, **String.isBlank()** trả true, Mojo ném **MojoFailureException** và Maven dự kiến báo:

~~~text
demo.message must not be blank
~~~

Đây là **expected failure**. Trong CI, phải assert nonzero và đúng loại lỗi; không coi một lỗi network/permission bất kỳ là pass của negative test.

Nếu output directory không thể ghi, **IOException** được giữ làm cause trong **MojoExecutionException**; không nên phá quyền host filesystem để mô phỏng, hãy dùng sandbox kiểm thử riêng.

## 12. Kiểm plugin descriptor bằng Maven Help Plugin

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" \
  -f sample-consumer/pom.xml \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:describe \
  -Dplugin=dev.lesson:demo-maven-plugin:1.0.0 \
  -Dgoal=emit -Ddetail=true
~~~

Lệnh này kiểm Maven hiểu goal **emit** và các tham số trong descriptor. Nó **không chạy logic emit**. Vì vậy vẫn cần direct invocation hoặc consumer lifecycle test.

### Prefix ngắn vs fully qualified goal

Lệnh:

~~~bash
mvn demo:emit
~~~

có thể fail **No plugin found for prefix 'demo'** nếu custom groupId **dev.lesson** chưa có trong plugin groups lookup. Settings có thể khai fragment:

~~~xml
<pluginGroups>
    <pluginGroup>dev.lesson</pluginGroup>
</pluginGroups>
~~~

Nhưng khi QA, dùng **dev.lesson:demo-maven-plugin:1.0.0:emit** đơn giản hơn: không đoán prefix metadata, không tự chỉnh global settings.

### Khai plugin không đồng nghĩa chạy goal

| Trường hợp | Goal có chạy? |
| --- | --- |
| Plugin chỉ trong build/plugins, không có execution | Không tự động |
| Chỉ trong pluginManagement | Không |
| @Mojo có defaultPhase nhưng consumer không khai execution | Không tự động |
| Consumer bind emit tại generate-resources, gọi verify | Có |
| Gọi trực tiếp fully qualified goal | Có |
| Chỉ chạy validate, goal bind ở generate-resources | Không đi đến phase đó |

Execution ID ở consumer và tên goal là hai thứ khác nhau. **emit** là goal; **emit-consumer-message** là execution mà người dùng có thể tìm trong log.

## 13. Tự động hóa bằng Maven Invoker Plugin

Để kiểm nhiều Maven consumers ở CI, Maven có **maven-invoker-plugin 3.10.1**. Các goals:

- **invoker:install** chuẩn bị plugin artifact trong repository dành cho IT.
- **invoker:integration-test** chạy các Maven test projects.
- **invoker:verify** kiểm kết quả.
- **invoker:run** chạy và xác minh một tập fixtures trong một goal.

Phần này là **tùy chọn nâng cao** bổ sung vào plugin project. Thư mục:

~~~text
demo-maven-plugin/
└── src/it/
    └── emit-basic/
        ├── pom.xml
        ├── invoker.properties
        └── verify.bsh
~~~

Thêm fragment sau vào **build/plugins** của plugin POM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-invoker-plugin</artifactId>
    <version>3.10.1</version>
    <configuration>
        <projectsDirectory>src/it</projectsDirectory>
        <cloneProjectsTo>${project.build.directory}/it</cloneProjectsTo>
        <localRepositoryPath>${project.build.directory}/it-repo</localRepositoryPath>
        <postBuildHookScript>verify</postBuildHookScript>
    </configuration>
    <executions>
        <execution>
            <id>plugin-it</id>
            <goals>
                <goal>install</goal>
                <goal>run</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Fixture **src/it/emit-basic/pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.lesson.it</groupId>
    <artifactId>emit-basic-fixture</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <build>
        <plugins>
            <plugin>
                <groupId>dev.lesson</groupId>
                <artifactId>demo-maven-plugin</artifactId>
                <version>1.0.0</version>
                <executions>
                    <execution>
                        <id>emit-fixture-message</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>emit</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Fixture **src/it/emit-basic/invoker.properties**:

~~~properties
invoker.goals = generate-resources
invoker.buildResult = success
~~~

Fixture **src/it/emit-basic/verify.bsh**:

~~~java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

File output = new File(basedir, "target/plugin-message.txt");

if (!output.isFile()) {
    throw new java.io.FileNotFoundException(
        "Missing plugin output: " + output
    );
}

String actual = new String(
    Files.readAllBytes(output.toPath()),
    StandardCharsets.UTF_8
);

if (!"PLUGIN_MESSAGE=Hello Maven\n".equals(actual)) {
    throw new IllegalStateException("Unexpected output: " + actual);
}

return true;
~~~

**verify.bsh là BeanShell hook script**, không phải Java class độc lập để javac compile. Invoker cung cấp biến **basedir**. Hook xác minh file và nội dung; nếu ném exception thì integration test failure.

Sau khi bổ sung cấu hình và fixtures:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" \
  -f demo-maven-plugin/pom.xml clean verify
~~~

Invoker có thể lưu log ở **demo-maven-plugin/target/it/emit-basic/build.log** theo cấu hình cloneProjectsTo. Cần xem cả goal invocation lẫn hook result. Nếu goal không viết file nhưng Maven build được, hook phải bắt lỗi; đó là giá trị của integration verification.

### Invoker còn kiểm được gì?

Có thể thêm fixtures:

- Default message.
- CLI/POM override với Unicode.
- Invalid input và expected build failure.
- Multi-module reactor để kiểm output vào target riêng.
- Parallel build khi plugin công bố threadSafe.
- Windows/Linux và các Maven/JDK versions được hỗ trợ.

Mỗi fixture cần assert **output hoặc failure reason thực**, không chỉ assert build exit 0.

## 14. Plugin Testing Harness: khác với Invoker thế nào?

Apache Maven cũng có **Maven Plugin Testing Harness** để kiểm Mojo với context và injected parameters mà không cần chạy Maven con cho mỗi case. Một số API cũ dùng **MojoRule**, thế hệ mới có **@MojoTest/@InjectMojo** với JUnit Jupiter. Khi sử dụng phải chọn đúng API theo version đã pin.

| Phương pháp | Nên dùng để kiểm |
| --- | --- |
| Unit JUnit | Hàm thuần Java, validation, format |
| Plugin Testing Harness | Mojo injection/behavior trong test context |
| Consumer Maven project | Resolve GAV, descriptor, CLI invocation, lifecycle, file output |
| Maven Invoker Plugin | Tự động kiểm nhiều consumer projects trên CI |

**Không bỏ consumer/Invoker chỉ vì unit coverage cao.** Maven lifecycle và plugin metadata là hai bề mặt mà unit test helper không quan sát được.

## 15. Lỗi thường gặp và cách điều tra

| Triệu chứng | Khả năng gốc | Bước kiểm |
| --- | --- | --- |
| JAR thiếu plugin.xml | Sai packaging/descriptor generation | maven-plugin packaging, plugin-plugin logs |
| Could not find goal emit | Annotation/descriptor hoặc version sai | @Mojo name, plugin.xml, GAV |
| Plugin not found | Plugin chưa install hoặc khác local repo | Dùng cùng -Dmaven.repo.local |
| No plugin found for prefix demo | Custom plugin group chưa được lookup | Gọi GAV fully qualified |
| Consumer BUILD SUCCESS nhưng không có output | Không có execution hoặc phase chưa chạy | build/plugins/executions và goal banner |
| File ghi vào target sai | Hardcode path hoặc injection sai | project.build.directory |
| Consumer test đọc nhầm file cũ | Không chạy clean | clean verify |
| Unicode/EOL khác | Charset/newline không rõ | UTF-8 và LF assertions |
| Override không hoạt động | Sai property hoặc POM config ưu tiên | @Parameter, help:describe |
| Blank input vẫn được chấp nhận | Validation không chạy hoặc message bị override | MojoFailureException và CLI property |
| IO error mơ hồ | Không giữ exception cause | MojoExecutionException(message,cause) |
| API/class version lỗi | Maven/JDK runtime không phù hợp | mvn -version, Java target |
| Invoker pass nhưng file sai | Thiếu verify hook | assert exact content |
| CI dùng artifact plugin cũ | Repo cache hoặc version mismatch | Isolated repo và pinned GAV |
| Parallel build race | Shared state/path | Multi-module/parallel fixtures |

**Khi cần log sâu**, dùng **mvn -e** để xem cause chain, **mvn -X** để xem plugin resolution/parameters. Debug logs có thể chứa internal URLs, paths và thông tin nhạy cảm; phải redact trước khi chia sẻ.

Một lỗi Maven **Failed to execute goal** phải được gắn với **plugin:version:goal, execution ID và project artifactId**, không chỉ nhắc BUILD FAILURE.

## 16. Checklist đưa Maven plugin vào CI/release

- [ ] POM dùng packaging=maven-plugin và tên plugin hợp convention.
- [ ] Maven API, Plugin Tools, compiler, JDK versions được pin.
- [ ] Có JUnit unit tests cho pure Java logic.
- [ ] Plugin JAR chứa META-INF/maven/plugin.xml.
- [ ] Descriptor có goal/parameter names dự kiến.
- [ ] Install plugin vào local repository riêng cho integration QA.
- [ ] Consumer POM khai đúng GAV/version, build/plugins/executions.
- [ ] Direct CLI goal chạy và log đúng version/goal/module.
- [ ] Lifecycle goal chạy ở phase và execution ID dự kiến.
- [ ] Consumer clean verify kiểm file mới, không dùng stale output.
- [ ] Test kiểm UTF-8, LF, content và output directory.
- [ ] Default, CLI override và POM config được kiểm độc lập.
- [ ] Blank/invalid input cho Maven failure đúng lý do.
- [ ] I/O lỗi giữ cause và không có silent success.
- [ ] Invoker fixtures hoặc một consumer script chạy trong CI.
- [ ] Plugin prefix ngắn không được dùng thay GAV trong bước QA ban đầu.
- [ ] Maven/JDK compatibility được thử theo các baseline công bố.
- [ ] Multi-module/parallel behavior được thử nếu công bố threadSafe.
- [ ] Mã plugin chưa tin cậy không chạy cùng credentials phát hành.
- [ ] Không dùng -fn hoặc skip quality gates để làm xanh giả.
- [ ] Chỉ publish plugin sau khi đã có QA reports và review.

**Kết luận:** Một Maven plugin chỉ thật sự được kiểm chứng khi **Maven tìm được đúng plugin artifact, nhận ra descriptor, chạy goal trong dự án mẫu và tạo kết quả đã được assert**. Unit tests quan trọng nhưng chưa đủ; consumer POM và Maven Invoker fixtures kiểm phần hành vi mà người dùng thực tế trải nghiệm.

## Nguồn tham khảo chính thức

- [Apache Maven — Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development.html)
- [Maven Plugin Plugin — Java Annotations](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/using-annotations.html)
- [Maven Plugin Plugin — descriptor goal](https://maven.apache.org/plugin-tools/maven-plugin-plugin/descriptor-mojo.html)
- [Apache Maven — Plugin Prefix Resolution](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html)
- [Apache Maven — Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Invoker Plugin — Overview](https://maven.apache.org/plugins/maven-invoker-plugin/)
- [Maven Invoker Plugin — Usage](https://maven.apache.org/plugins/maven-invoker-plugin/usage.html)
- [Maven Invoker Plugin — Pre/Post Build Scripts](https://maven.apache.org/plugins/maven-invoker-plugin/examples/pre-post-build-script.html)
- [Maven Plugin Testing Harness — Getting Started](https://maven.apache.org/plugin-testing/maven-plugin-testing-harness/getting-started/index.html)
- [Apache Maven — Plugin Compatibility Plan](https://maven.apache.org/developers/compatibility-plan.html)

*Bài thực hành dùng Java 17, Maven 3.9.x, Maven Plugin Plugin/Annotations 3.16.0, Maven Plugin API 3.9.16, Maven Invoker Plugin 3.10.1, Compiler Plugin 3.13.0, Surefire 3.5.2 và JUnit Jupiter 5.11.4. Các lệnh và kết quả là ví dụ để tự thực hành; không tuyên bố đã biên dịch hoặc gọi Maven thật trong lượt soạn bài.*
