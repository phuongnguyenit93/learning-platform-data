# Mojo, goal và plugin descriptor trong mô hình thực thi Maven

Khi chạy `mvn compile`, Maven không tự có một hàm Java mang tên `compile` cho mọi dự án. Maven xác định các **goal** cần chạy từ lifecycle và cấu hình POM, tìm plugin cung cấp từng goal, đọc metadata để biết **Mojo** triển khai goal đó, cấu hình tham số rồi mới gọi mã thực thi. Mấu chốt của cơ chế này là **plugin descriptor** nằm bên trong plugin JAR.

Bài học làm rõ bốn khái niệm:

- **Plugin:** một artifact Maven chứa tập chức năng phục vụ build, ví dụ `maven-compiler-plugin` hoặc plugin do nhóm tự viết.
- **Goal:** thao tác có tên được plugin công bố, ví dụ `compiler:compile`, `surefire:test`, `help:describe`. Một plugin có thể có nhiều goal.
- **Mojo:** lớp/đối tượng triển khai một goal. Với plugin Java cho Maven 3, thông thường class kế thừa `AbstractMojo`, khai báo `@Mojo` và cài đặt phương thức `execute()`.
- **Plugin descriptor:** metadata `META-INF/maven/plugin.xml` trong plugin JAR, mô tả goal, implementation, parameters và yêu cầu thực thi để Maven biết cách tạo/gọi Mojo.

```text
            mvn validate / mvn plugin:goal
                         |
                         v
               Effective POM + CLI
                         |
                         v
        Lifecycle phase + <executions>
                         |
                         v
              Maven execution plan
                         |
                         v
       Plugin artifact + plugin realm
                         |
                         v
     META-INF/maven/plugin.xml descriptor
                         |
                         v
          Goal -> Mojo implementation
                         |
                         v
      Parameter injection -> execute()
                         |
                         v
            Maven logs / kết quả
```

Đây là sơ đồ khái niệm, **không phải thứ tự method nội bộ bắt buộc** của từng phiên bản Maven. Những bước giải quyết artifact, cấu hình plugin, dependency collection/resolution và thực thi có thể liên quan nhiều thành phần của Maven Core.

Bài tập trung vào **Maven 3.x, Java 17+, Maven Plugin Tools Java annotations**. Maven 4 phát triển các API/descriptor mới, vì vậy những thông tin về cấu trúc descriptor và class plugin dưới đây gắn với cách phát triển Java plugin phổ biến trong Maven 3.

## 1. Phân biệt plugin, goal, phase, Mojo và execution

| Thuật ngữ | Ví dụ | Vai trò |
| --- | --- | --- |
| Plugin | `org.apache.maven.plugins:maven-compiler-plugin` | Artifact cung cấp chức năng build. |
| Goal | `compiler:compile` | Tên thao tác được plugin công bố. |
| Mojo | Java class thực hiện goal `compile` | Logic thực tế mà Maven gọi. |
| Lifecycle | `default`, `clean`, `site` | Chuỗi phase để tổ chức build. |
| Phase | `validate`, `compile`, `test`, `package` | Mốc của lifecycle, không phải class Java. |
| Execution | `<execution>` gắn goal vào phase | Cấu hình một lần chạy goal trong build plan. |
| Descriptor | `META-INF/maven/plugin.xml` | Ánh xạ tên goal sang implementation và metadata. |
| Project POM | `pom.xml` | Khai báo dự án, plugins, dependencies, executions. |

Ví dụ:

```bash
mvn compile
```

Đây là yêu cầu chạy phase `compile` của default lifecycle, bao gồm các phase cần thiết đứng trước nó. Tùy packaging và POM, Maven gọi những goal tương ứng.

Trong khi đó:

```bash
mvn org.apache.maven.plugins:maven-compiler-plugin:3.14.1:compile
```

gọi **một goal cụ thể** của plugin theo tọa độ đầy đủ. Lệnh này không đồng nghĩa thực hiện đầy đủ lifecycle đến phase `compile`; nếu project cần output do phase trước tạo ra, chạy goal riêng lẻ có thể thiếu đầu vào.

Dạng rút gọn:

```bash
mvn compiler:compile
```

dùng `compiler` là **plugin prefix**. Maven phải giải quyết prefix thành plugin thật dựa trên cấu hình và repository metadata. Trong script/CI, dạng GAV đầy đủ thường rõ ràng hơn.

**Kết luận:** goal không phải phase; Mojo không phải goal name; một phase có thể chạy nhiều goals và một goal có thể có nhiều executions.

## 2. Plugin là artifact Maven, nhưng không phải dependency Java của ứng dụng

Plugin có tọa độ Maven `groupId:artifactId:version`, được giải quyết từ local repository, remote repository hoặc mirror phù hợp.

Ví dụ:

```text
org.apache.maven.plugins:maven-compiler-plugin:3.14.1
org.apache.maven.plugins:maven-jar-plugin:3.4.2
org.apache.maven.plugins:maven-help-plugin:3.5.2
```

Những số version này là **bản cụ thể để học**, không phải tuyên bố phiên bản mới nhất.

Trong POM:

```xml
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

Đây là cấu hình **build plugin**, không phải dependency mà code ứng dụng tự động `import` được. Dependencies của project nằm trong `<dependencies>`, còn dependencies để chạy plugin được Maven giải quyết cho **plugin realm** riêng.

```text
Project classpath:                Plugin class realm:
  my-app                            maven-compiler-plugin
    └── application-api.jar          └── supporting-plugin-library.jar
```

Một dependency trong `dependencyManagement` của project **không mặc nhiên điều khiển mọi dependency nội bộ của plugin**. Nếu lỗi xảy ra khi plugin khởi tạo, hãy kiểm tra phiên bản plugin, plugin repository, plugin dependencies và JVM chạy Maven thay vì chỉ xem dependency tree của ứng dụng.

## 3. Cách goal xuất hiện trong một lần build

Có hai hình thức sử dụng chính.

### 3.1. Gọi goal trực tiếp

```text
mvn groupId:artifactId:version:goal
mvn plugin-prefix:goal
```

Ví dụ:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe
mvn help:describe
```

Để dùng prefix ngắn cho plugin nhóm riêng, Maven có thể cần `pluginGroups` và prefix metadata. Nếu Maven báo “No plugin found for prefix”, thử dạng GAV đầy đủ trước khi suy luận plugin không tồn tại.

### 3.2. Bind goal vào lifecycle phase

Đoạn cấu hình sau chỉ được đặt trong POM đã có `<project>`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.example.training</groupId>
            <artifactId>greeting-maven-plugin</artifactId>
            <version>1.0.0</version>
            <executions>
                <execution>
                    <id>greet-on-validate</id>
                    <phase>validate</phase>
                    <goals>
                        <goal>greet</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Khi project chạy `mvn validate`, Maven nhận ra cần gọi goal `greet` ở phase `validate`. Nếu chỉ khai báo plugin trong `<plugins>` **mà không có execution hoặc binding thích hợp**, Maven không tự chạy tất cả goals của plugin.

`<id>` là tên một execution, `<goal>` là tên thao tác, `<phase>` là vị trí nó được gắn. Không dùng `<id>` như tên Java class hoặc tên goal.

## 4. Mojo là điểm vào thực thi của goal

Một Mojo Java phổ biến:

- Kế thừa `org.apache.maven.plugin.AbstractMojo` hoặc triển khai interface `Mojo` thích hợp.
- Được đánh dấu `@Mojo(name = "...")` để Plugin Tools tạo metadata.
- Triển khai `execute()`.
- Nhận parameters qua `@Parameter`.
- Ghi log qua `getLog()`.
- Dùng exception Maven phù hợp để báo lỗi.

Một class tối thiểu, hợp lệ về Java:

```java
package org.example.training.mojo;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.Mojo;

@Mojo(name = "ping")
public final class PingMojo extends AbstractMojo {
    @Override
    public void execute() throws MojoExecutionException {
        getLog().info("Ping from Maven Mojo");
    }
}
```

Đây là **class Mojo độc lập về mã Java** nhưng chưa phải một Maven plugin hoàn chỉnh. Nó không có `main()` để chạy bằng `java PingMojo`, và Maven không tự tìm được goal nếu chỉ đưa file `.class` vào một JAR thường không có descriptor.

Khi goal được gọi, **nội dung thông điệp** là:

```text
Ping from Maven Mojo
```

Maven logging có thể thêm `[INFO]` và các dòng khác; vì vậy đây không phải toàn bộ stdout của Maven.

Hai ngoại lệ thường gặp:
- `MojoExecutionException`: goal không thể hoàn thành vì sự cố thực thi/kỹ thuật.
- `MojoFailureException`: mục tiêu kiểm tra của goal thất bại theo điều kiện nghiệp vụ được dự kiến, chẳng hạn quy tắc chất lượng không đạt.

Exception khiến build thất bại theo cơ chế Maven; không nên dùng chuỗi log nghiệp vụ làm bằng chứng duy nhất để kết luận job thành công.

## 5. Plugin descriptor: metadata mà Maven đọc để biết goal

Plugin Java cho Maven 3 thường đóng gói file:

```text
greeting-maven-plugin-1.0.0.jar
├── META-INF/
│   └── maven/
│       └── plugin.xml
└── org/example/training/mojo/
    └── GreetMojo.class
```

JAR thật có thể chứa thêm manifest, POM metadata và resources. Đoạn trên chỉ nhấn mạnh hai thành phần.

Plugin descriptor `META-INF/maven/plugin.xml` chứa:

| Metadata | Ý nghĩa |
| --- | --- |
| `groupId`, `artifactId`, `version` | Danh tính của plugin. |
| `goalPrefix` | Prefix phục vụ cú pháp `prefix:goal`. |
| `mojos` | Danh sách các Mojo/goal được công bố. |
| `goal` | Tên goal người dùng gọi. |
| `implementation` | Tên class triển khai, ví dụ `org.example.training.mojo.GreetMojo`. |
| `phase` | Default lifecycle phase nếu Mojo khai báo. |
| `parameters` | Tên, kiểu, thuộc tính bắt buộc và mô tả parameters. |
| `configuration` | Giá trị mặc định/cách inject parameters được biểu diễn trong descriptor. |
| `requiresProject` | Goal yêu cầu Maven project hay không. |
| `requiresDependencyResolution` | Scope dependency của project phải resolve trước khi goal chạy. |
| `aggregator`, `threadSafe` | Thông tin về phạm vi reactor và khả năng chạy song song. |

Đoạn descriptor **lược bớt nhiều phần** để dễ học:

```xml
<plugin>
    <groupId>org.example.training</groupId>
    <artifactId>greeting-maven-plugin</artifactId>
    <version>1.0.0</version>
    <goalPrefix>greeting</goalPrefix>
    <mojos>
        <mojo>
            <goal>greet</goal>
            <implementation>org.example.training.mojo.GreetMojo</implementation>
            <phase>validate</phase>
            <parameters>
                <parameter>
                    <name>name</name>
                    <type>java.lang.String</type>
                </parameter>
            </parameters>
        </mojo>
    </mojos>
</plugin>
```

Đây **không phải descriptor Maven hoàn chỉnh để copy và dùng như production metadata**. Plugin Tools sẽ sinh các phần tương ứng với Mojo annotations và POM theo đúng phiên bản tooling, gồm cả default configuration. Không chỉnh file đã sinh trong `target`; hãy sửa nguồn annotations và build lại.

### 5.1. Phân biệt ba file thường bị nhầm

| File | Nơi thường gặp | Mục đích |
| --- | --- | --- |
| `pom.xml` | Root dự án/plugin và artifact POM trong repository | Tọa độ, dependencies, packaging, build config. |
| `META-INF/maven/plugin.xml` | Trong plugin JAR | Ánh xạ goals → Mojo classes, parameters và execution requirements. |
| `maven-metadata.xml` | Repository layout | Metadata version, plugin prefix và các dữ liệu resolution phù hợp. |

`pom.xml` không thay `plugin.xml`. Maven có thể giải quyết được plugin JAR theo GAV nhưng vẫn báo lỗi khi descriptor thiếu hoặc goal không có trong descriptor.

## 6. Plugin Tools biến annotations thành descriptor bằng cách nào?

Khi viết:

```java
@Mojo(
    name = "greet",
    defaultPhase = LifecyclePhase.VALIDATE,
    threadSafe = true
)
```

Plugin Tools hiểu class này công bố goal `greet` với default phase metadata `validate` và được tác giả đánh dấu thread-safe.

Khi viết:

```java
@Parameter(property = "greet.name", defaultValue = "Maven")
private String name;
```

Plugin Tools ghi thông tin về parameter `name`, default value và user property phù hợp vào descriptor.

**Điểm quan trọng:** `defaultPhase=VALIDATE` **không tự kích hoạt goal** ở mọi project chỉ vì plugin được liệt kê trong `<plugins>`. Nó có thể làm phase mặc định khi project khai báo execution mà không ghi phase; để học và vận hành dễ kiểm chứng, nên bind tường minh `<phase>validate</phase>` trong POM.

`threadSafe=true` cũng không làm code tự nhiên an toàn: class ghi file chung, dùng static mutable state hoặc gọi API không có bảo vệ concurrency vẫn có thể xảy ra race condition trong Maven parallel build.

### 6.1. Goal sinh descriptor là `plugin:descriptor`

**Maven Plugin Plugin** (artifact `org.apache.maven.plugins:maven-plugin-plugin`) cung cấp goal **`plugin:descriptor`** để sinh descriptor. Tài liệu phiên bản Plugin Plugin 3.16.0 mô tả goal này có default phase `process-classes`, sau khi các class Java đã được biên dịch. Với packaging `maven-plugin`, Maven có lifecycle bindings phục vụ tạo descriptor và đóng gói plugin artifact.

Bạn thường chỉ cần:

```bash
mvn package
```

trong project plugin đã cấu hình đúng, rồi kiểm tra file `target/classes/META-INF/maven/plugin.xml` và entry cùng tên trong JAR. Có thể gọi riêng `plugin:descriptor` để chẩn đoán, nhưng với annotation-based Mojo, nếu chưa compile các class cần thiết thì gọi goal quá sớm có thể không thu được metadata đúng.

**Không nhầm goal `plugin:descriptor` với file descriptor**: goal là thao tác sinh file, còn `META-INF/maven/plugin.xml` là sản phẩm metadata.

## 7. Lab Java 17: tự xây một Maven plugin và gọi goal

Lab gồm hai project:
- `greeting-maven-plugin`: tạo plugin JAR, class `GreetMojo`, descriptor.
- `demo-consumer`: dùng plugin đã install, bind goal `greet` vào `validate`.

Yêu cầu: JDK 17+, Maven 3.x phù hợp với phiên bản plugins được nêu, mạng truy cập repository hoặc cache artifact đầy đủ. Ví dụ dùng `maven-plugin-api:3.9.16`, `maven-plugin-annotations:3.16.0`, `maven-plugin-plugin:3.16.0` và `maven-compiler-plugin:3.14.1`; số version được ghim để bản lab rõ ràng, không hàm ý Maven trên máy nào cũng có sẵn chúng.

### 7.1. Cấu trúc thư mục

```text
plugin-lab/
├── greeting-maven-plugin/
│   ├── pom.xml
│   └── src/main/java/org/example/training/mojo/GreetMojo.java
└── demo-consumer/
    └── pom.xml
```

Root `plugin-lab` không có aggregator POM. Vì vậy mọi lệnh dùng `-f` để chọn project.

Linux/macOS:

```bash
mkdir -p plugin-lab/greeting-maven-plugin/src/main/java/org/example/training/mojo
mkdir -p plugin-lab/demo-consumer
cd plugin-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "plugin-lab/greeting-maven-plugin/src/main/java/org/example/training/mojo" | Out-Null
New-Item -ItemType Directory -Force -Path "plugin-lab/demo-consumer" | Out-Null
Set-Location plugin-lab
```

### 7.2. POM plugin hoàn chỉnh

Tệp `greeting-maven-plugin/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.training</groupId>
    <artifactId>greeting-maven-plugin</artifactId>
    <version>1.0.0</version>
    <packaging>maven-plugin</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
                <artifactId>maven-plugin-plugin</artifactId>
                <version>${plugin.tools.version}</version>
                <configuration>
                    <goalPrefix>greeting</goalPrefix>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích:
- Packaging `maven-plugin` lựa chọn lifecycle phù hợp để tạo plugin descriptor và JAR plugin.
- Artifact tên `greeting-maven-plugin` tuân theo quy ước đặt tên plugin do nhóm tự viết. Dạng `maven-<name>-plugin` được Apache Maven khuyến cáo dành cho plugins chính thức.
- Dependency `maven-plugin-api` cung cấp `AbstractMojo`, `MojoExecutionException` và APIs mà Mojo sử dụng.
- Dependency `maven-plugin-annotations` cung cấp `@Mojo`, `@Parameter`, `LifecyclePhase`.
- Hai dependency trên dùng `provided` để giảm nguy cơ đóng gói Maven API trùng lặp không cần thiết vào plugin.
- Plugin Plugin được ghim version `3.16.0` để Plugin Tools sinh descriptor. `goalPrefix=greeting` phục vụ tên prefix; gọi GAV đầy đủ vẫn không cần prefix mapping.
- Java release 17 xác định bytecode plugin yêu cầu JVM tương thích khi Maven chạy.

### 7.3. Class Mojo hoàn chỉnh

Tệp `greeting-maven-plugin/src/main/java/org/example/training/mojo/GreetMojo.java`:

```java
package org.example.training.mojo;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.LifecyclePhase;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

/**
 * Logs a greeting when the greet goal runs.
 */
@Mojo(
    name = "greet",
    defaultPhase = LifecyclePhase.VALIDATE,
    threadSafe = true
)
public final class GreetMojo extends AbstractMojo {

    /**
     * Person or team to greet.
     */
    @Parameter(property = "greet.name", defaultValue = "Maven")
    private String name;

    @Override
    public void execute() throws MojoExecutionException {
        getLog().info("Hello, " + name + " from Mojo!");
    }
}
```

Đây là class Java hợp lệ nhưng không có phương thức `main`. Maven gọi `execute()` thông qua plugin framework.

Mapping:
- Goal name: `greet`.
- Mojo implementation: `org.example.training.mojo.GreetMojo`.
- Default phase metadata: `validate`.
- Parameter: `name`.
- User property khi thích hợp: `greet.name`.
- Default parameter value: `Maven`.
- Nội dung log do mã tạo: `Hello, ... from Mojo!`.

### 7.4. Build plugin, kiểm tra descriptor và install

Từ `plugin-lab`:

```bash
mvn -version
mvn -B -ntp -f greeting-maven-plugin/pom.xml clean install
```

Nếu Maven, JDK và repository resolution phù hợp, Maven biên dịch class, chạy các goal phục vụ plugin packaging, tạo descriptor và cài plugin vào **local Maven repository** của máy.

Các đường dẫn kết quả được kỳ vọng:

```text
greeting-maven-plugin/target/classes/META-INF/maven/plugin.xml
greeting-maven-plugin/target/greeting-maven-plugin-1.0.0.jar
```

Kiểm tra entry thật trong JAR:

```bash
jar --list --file greeting-maven-plugin/target/greeting-maven-plugin-1.0.0.jar
```

Tìm hai entry:

```text
META-INF/maven/plugin.xml
org/example/training/mojo/GreetMojo.class
```

Đây chỉ là **hai entry kỳ vọng**; output đầy đủ còn những file khác và thứ tự có thể khác.

Lọc output trong Linux/macOS:

```bash
jar --list --file greeting-maven-plugin/target/greeting-maven-plugin-1.0.0.jar | grep -E 'plugin.xml|GreetMojo.class'
```

Trong PowerShell:

```powershell
jar --list --file greeting-maven-plugin/target/greeting-maven-plugin-1.0.0.jar | Select-String "plugin.xml|GreetMojo.class"
```

Mở file `target/classes/META-INF/maven/plugin.xml` bằng editor để xem metadata sinh ra. Tìm các đoạn `<goal>greet</goal>`, `<implementation>org.example.training.mojo.GreetMojo</implementation>` và tham số `name`. **Không chỉnh file trong `target`** để sửa plugin lâu dài vì `mvn clean` sẽ xóa nó; sửa annotation/POM rồi build lại.

**`install` không phải `deploy`:** install cài plugin tại máy này; CI hoặc máy đồng nghiệp khác cần artifact ở remote repository phù hợp hoặc quy trình build/install riêng.

### 7.5. POM consumer hoàn chỉnh

Tệp `demo-consumer/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.consumer</groupId>
    <artifactId>demo-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <build>
        <plugins>
            <plugin>
                <groupId>org.example.training</groupId>
                <artifactId>greeting-maven-plugin</artifactId>
                <version>1.0.0</version>
                <configuration>
                    <name>Team</name>
                </configuration>
                <executions>
                    <execution>
                        <id>greet-on-validate</id>
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

POM consumer:
- Chọn plugin bằng GAV.
- Cấu hình tham số `name=Team`.
- Gắn goal `greet` vào phase `validate` qua execution có ID riêng.
- Không cần Java source vì `validate` chạy trước bước compile.

### 7.6. Gọi goal qua phase hoặc trực tiếp

Từ `plugin-lab`, chạy:

```bash
mvn -B -ntp -f demo-consumer/pom.xml validate
```

Maven log dự kiến chứa **message nghiệp vụ**:

```text
Hello, Team from Mojo!
```

Đây không phải toàn bộ stdout; Maven có thể thêm `[INFO]`, plugin execution heading và `BUILD SUCCESS`.

Gọi goal **trực tiếp**:

```bash
mvn -B -ntp -f demo-consumer/pom.xml org.example.training:greeting-maven-plugin:1.0.0:greet
```

Goal được gọi theo GAV; không phải chạy tất cả các phase trong lifecycle. Vì consumer POM vẫn cấu hình `name=Team`, message được kỳ vọng giống ví dụ trên.

Để thấy user property từ `@Parameter(property="greet.name")` mà **không bị cấu hình `name=Team` của consumer ghi đè**, gọi từ chính plugin project đã install:

```bash
mvn -B -ntp -f greeting-maven-plugin/pom.xml org.example.training:greeting-maven-plugin:1.0.0:greet -Dgreet.name=CLI
```

Message kỳ vọng trong trường hợp này:

```text
Hello, CLI from Mojo!
```

Không suy ra một thứ tự ưu tiên tuyệt đối cho mọi trường hợp khi user property và `<configuration>` của execution đều hiện diện; kiểm tra đúng mô hình và goal invocation đang thực thi.

## 8. Xem mô tả goal bằng `help:describe`

Goal `help:describe` của Maven Help Plugin giúp đọc metadata của plugin/goal mà không phải mở mã Java.

Ví dụ xem Compiler Plugin:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.14.1 -Dgoal=compile -Ddetail
```

Với plugin lab:

```bash
mvn -f demo-consumer/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=org.example.training:greeting-maven-plugin:1.0.0 -Dgoal=greet -Ddetail
```

Thông tin có thể gồm goal name, mô tả, requirements, default phase, parameters, user properties và default values tùy phiên bản plugin, metadata đã đóng gói và cách Help Plugin trình bày.

Để liệt kê nhiều goals trong plugin, bỏ `-Dgoal=...`:

```bash
mvn -f demo-consumer/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=org.example.training:greeting-maven-plugin:1.0.0 -Ddetail
```

**Phân biệt:** `help:describe` trình bày metadata; `plugin:descriptor` sinh descriptor khi tạo plugin; `META-INF/maven/plugin.xml` là file Maven cần để thực thi. Ba thứ này không thay thế nhau.

## 9. `pluginManagement`, `plugins` và `executions`

| Cấu hình | Tác dụng |
| --- | --- |
| `<build><pluginManagement>` | Cấp version/cấu hình mẫu cho plugin khi được sử dụng phù hợp; **không tự tạo goal execution**. |
| `<build><plugins>` | Khai báo plugin được dùng; áp dụng version/configuration cho các goals được bind hoặc được gọi. |
| `<plugin><executions>` | Chọn goals và phase/ID để chạy trong lifecycle. |
| `<plugin><configuration>` | Cung cấp tham số ở cấp plugin. |
| `<execution><configuration>` | Cung cấp cấu hình riêng cho execution tương ứng. |

Ví dụ parent chỉ có:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.example.training</groupId>
            <artifactId>greeting-maven-plugin</artifactId>
            <version>1.0.0</version>
        </plugin>
    </plugins>
</pluginManagement>
```

thì các module con **không tự chạy `greet`**. Cần plugin được sử dụng bởi một binding/execution thực sự hoặc được gọi trên CLI. Việc quản lý version khác với việc kích hoạt một task.

### Packaging và default lifecycle bindings

Maven có các bindings tùy packaging:
- `jar`: thường bind goals liên quan `resources`, `compiler`, `surefire`, `jar` vào phases mặc định.
- `pom`: không tự tạo JAR Java từ mã nguồn như packaging `jar`.
- `maven-plugin`: thêm lifecycle goals tạo descriptor/plugin metadata cho artifact plugin.

Đặc tính `@Mojo(defaultPhase=...)` của goal tùy chỉnh không được hiểu như một “lifecycle binding toàn cục” mới.

## 10. Từ execution plan đến `execute()`

Có thể nhìn việc Maven thực thi một goal thành những trách nhiệm:

1. **Model building:** đọc `pom.xml`, parent, profiles và settings liên quan.
2. **Lifecycle planning:** chọn phases/goals từ CLI, packaging và `<executions>`.
3. **Plugin resolution:** tìm plugin artifact/POM theo GAV từ repositories và mirror.
4. **Descriptor loading:** đọc `META-INF/maven/plugin.xml` để biết goals và implementation.
5. **Mojo selection:** chọn `MojoDescriptor` theo tên goal.
6. **Requirements:** xác định goal có cần project, network, dependency resolution hay aggregator context không.
7. **Plugin realm:** tạo/chuẩn bị class loading context của plugin và dependencies nội bộ.
8. **Configuration:** áp dụng cấu hình POM/execution, giá trị mặc định và expressions/parameters phù hợp.
9. **Invocation:** tạo/configure Mojo rồi gọi `execute()`.
10. **Reporting:** chuyển log, lỗi và trạng thái sang Maven build result.

Đây là các trách nhiệm **khái niệm**, không phải chuỗi nội bộ cố định mọi phiên bản.

### Các metadata về requirements

- `requiresProject`: goal đòi hỏi được gọi trong ngữ cảnh một Maven project hay không.
- `requiresDependencyResolution`: Maven cần resolve dependency files của project ở scope được khai báo trước khi gọi goal.
- `requiresDependencyCollection`: goal cần tập thông tin dependencies mà chưa nhất thiết cần mọi file artifact đã resolve.
- `aggregator`: goal hoạt động ở phạm vi reactor/project set theo cơ chế đặc thù của nó.
- `threadSafe`: annotation về tính an toàn chạy song song, không phải bằng chứng tự thân rằng implementation không có race condition.

Một plugin dùng `requiresDependencyResolution` đang nói tới nhu cầu dữ liệu **project dependencies**, không có nghĩa sẽ trộn toàn bộ plugin dependencies vào classpath ứng dụng.

## 11. Những lỗi điển hình

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `No plugin found for prefix 'greeting'` | Prefix mapping hoặc `pluginGroups` thiếu | Gọi GAV đầy đủ; xem plugin group ID và settings. |
| `PluginResolutionException` | Artifact plugin hoặc POM không tải được | Kiểm tra tọa độ, `pluginRepositories`, mirror, credentials. |
| `No plugin descriptor found at META-INF/maven/plugin.xml` | JAR không đóng gói như plugin | Xem packaging, Plugin Plugin và entry trong JAR. |
| `Could not find goal 'greet'` | Descriptor thiếu goal hoặc sai tên | Xem `@Mojo(name="greet")`, rebuild/install đúng version. |
| `mvn validate` không chạy `greet` | Không có execution/binding | Xem `<executions>` và `<phase>validate</phase>`. |
| Giá trị parameter không đúng | Tên XML, alias, property hoặc config khác | Xem descriptor, `help:describe` và effective POM. |
| `UnsupportedClassVersionError` | JVM chạy Maven thấp hơn bytecode plugin | Xem `mvn -version`; chạy với JDK 17+ cho lab. |
| Mojo ném exception | Lỗi thực thi hoặc chất lượng | Đọc root cause, dữ liệu đầu vào và log đã kiểm duyệt. |
| Plugin lỗi khi chạy `-T` | Shared state/file không an toàn | Test concurrency, kiểm tra `threadSafe` thực tế. |
| Consumer không thấy plugin vừa build | Chưa install/publish đúng artifact | Dùng `install` cho lab hoặc repository dùng chung. |

### 11.1. Không tìm được prefix

Lệnh `mvn greeting:greet` có thể fail dù JAR plugin đã tồn tại. Prefix discovery cần metadata và danh sách plugin groups phù hợp.

Đối với plugin nhóm riêng, một đoạn `settings.xml` có thể khai báo:

```xml
<pluginGroups>
    <pluginGroup>org.example.training</pluginGroup>
</pluginGroups>
```

Đây là **đoạn XML trong `<settings>`**, không phải POM dự án. Nếu chỉ cần một invocation chắc chắn, dùng:

```bash
mvn -f demo-consumer/pom.xml org.example.training:greeting-maven-plugin:1.0.0:greet
```

### 11.2. JAR có class nhưng thiếu descriptor

Xác nhận theo thứ tự:
1. Plugin POM có `<packaging>maven-plugin</packaging>`?
2. Java class có đúng `@Mojo` và nằm trong `src/main/java`?
3. Maven Plugin Plugin có version và đã được chạy trong lifecycle?
4. `target/classes/META-INF/maven/plugin.xml` có tồn tại?
5. JAR cuối có entry `META-INF/maven/plugin.xml`?
6. Consumer có đang tải một bản plugin cũ trong local repository?

Chỉ thấy `GreetMojo.class` trong JAR **không đủ**; Maven cần descriptor để biết goal name, implementation và parameter mapping.

### 11.3. Goal chạy nhưng parameter mặc định không đổi

Nếu Java field là `name`, cách cấu hình trực tiếp là:

```xml
<configuration>
    <name>Team</name>
</configuration>
```

Không tự viết `<greetingName>Team</greetingName>` nếu Mojo không công bố parameter/alias đó. Maven không đoán từ ý nghĩa tiếng Anh. Hãy dùng `help:describe -Ddetail` và metadata thật.

### 11.4. Lỗi plugin không phải lỗi application dependency

Plugin chạy trong Maven JVM và có class realm riêng. Lỗi nạp class của plugin khác với ứng dụng Java thiếu runtime JAR. Tương tự, `<repositories>` giải quyết project dependencies không nhất thiết sửa được lỗi từ `<pluginRepositories>`. Phải xác định loại artifact và giai đoạn build gặp lỗi.

## 12. Thực hành tốt khi viết plugin riêng

1. Đặt tên goal theo hành động rõ ràng, ví dụ `generate-schema` hoặc `verify-contracts`.
2. Viết Javadoc và mô tả parameters để tài liệu/help được sinh hữu ích.
3. Dùng Plugin Tools sinh descriptor từ annotations thay vì chỉnh XML bằng tay.
4. Ghim version của plugin, Maven API và Plugin Tools theo bộ đã kiểm thử.
5. Dùng `provided` cho Maven API/annotations phù hợp, tránh classpath xung đột.
6. Xác định rõ goal yêu cầu project, dependency resolution và online mode hay không.
7. Nếu goal tạo file, ưu tiên output dưới `${project.build.directory}` và cho phép cấu hình đường dẫn.
8. Báo lỗi bằng exception Maven đúng mục đích; không ghi secret/token vào log.
9. Chỉ đánh dấu thread-safe sau khi kiểm tra state/file shared trong parallel builds.
10. Test bằng **project consumer thật** để kiểm tra descriptor, execution binding và parameter injection, không chỉ test riêng Java method.
11. Dùng Maven Plugin Testing Harness và integration testing khi phát triển plugin production.
12. Không tin rằng `package` tự publish; cần `install`/`deploy` và quyền truy cập repository phù hợp.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `mvn compile` và `mvn compiler:compile` có giống nhau không?

**Đáp án:** Không. Lệnh đầu yêu cầu phase `compile` trong lifecycle; lệnh sau gọi trực tiếp goal `compile` của Compiler Plugin.

**Câu 2.** Goal được Maven map tới Java class qua đâu?

**Đáp án:** Qua plugin descriptor `META-INF/maven/plugin.xml` trong plugin JAR, chứa tên goal và implementation metadata.

**Câu 3.** Chỉ có class `@Mojo(name="greet")` trong JAR là đủ cho Maven gọi goal không?

**Đáp án:** Không. JAR plugin phải có descriptor hợp lệ và được resolve đúng.

**Câu 4.** `@Mojo(defaultPhase=VALIDATE)` có làm goal tự chạy với `mvn validate` không?

**Đáp án:** Không. Cần execution/binding tương ứng hoặc gọi goal trực tiếp.

**Câu 5.** `pluginManagement` có làm plugin tự chạy không?

**Đáp án:** Không. Nó quản lý cấu hình/versions khi plugin được sử dụng phù hợp.

**Câu 6.** Tham số Java `@Parameter private String name` nhận giá trị từ `<configuration><name>Team</name></configuration>` là gì?

**Đáp án:** `Team`, với cấu hình POM của lab.

**Câu 7.** Vì sao `mvn greeting:greet` có thể báo không tìm thấy plugin, nhưng lệnh GAV đầy đủ hoạt động?

**Đáp án:** Prefix mapping cần plugin groups/repository metadata; dạng GAV đầy đủ nêu rõ plugin cần resolve.

**Câu 8.** `mvn package` trong project plugin có tự làm plugin dùng được trên CI khác không?

**Đáp án:** Không. Nó tạo artifact dưới `target`; CI cần resolve artifact được publish hoặc phải tự build/install.

**Câu 9.** Dùng goal nào để xem mô tả goal và parameters từ plugin metadata?

**Đáp án:** `help:describe` với `-Dplugin=...`, `-Dgoal=...` và `-Ddetail` khi cần.

**Câu 10.** `threadSafe=true` có bảo đảm một Mojo chia sẻ mutable state chạy song song an toàn không?

**Đáp án:** Không. Đó là metadata/cam kết; implementation phải thực sự an toàn và được kiểm thử.

**Câu 11.** Tại sao `dependency:tree` của ứng dụng không nhất thiết liệt kê dependencies nội bộ của Compiler Plugin?

**Đáp án:** Plugin realm khác project dependency graph.

**Câu 12.** Consumer gọi `mvn validate` và log có `Hello, Team from Mojo!` nhưng chưa có JAR app; có lỗi không?

**Đáp án:** Không. `validate` xảy ra trước `package`; trong lab goal chỉ phát thông điệp.

## Tài liệu tham khảo chính thức

- [Apache Maven – Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development): viết Mojo, đóng gói plugin, chạy goal và cấu hình tham số.
- [Apache Maven – Plugin Descriptor (Maven 3)](https://maven.apache.org/ref/3.9.9/maven-plugin-api/plugin.html): `META-INF/maven/plugin.xml`, goalPrefix, mojos, implementation và parameters.
- [Apache Maven Plugin Plugin – Java annotations](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/using-annotations.html): `@Mojo`, `@Parameter` và cách sinh descriptor.
- [Apache Maven Plugin Plugin – plugin:descriptor](https://maven.apache.org/plugin-tools/maven-plugin-plugin/descriptor-mojo.html): goal sinh plugin descriptor và default phase.
- [Apache Maven Plugin Plugin – Usage](https://maven.apache.org/plugin-tools/maven-plugin-plugin/usage.html): vị trí output `target/classes/META-INF/maven/plugin.xml`.
- [Apache Maven Help Plugin – help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html): thông tin goals và parameters.
- [Apache Maven – Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases, packaging và lifecycle bindings.
- [Apache Maven – Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): `plugins`, `pluginManagement` và `executions`.
- [Apache Maven – Plugin Prefix Mapping](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html): cú pháp `prefix:goal` và plugin groups.
- [Apache Maven – Mojo API Specification](https://maven.apache.org/developers/mojo-api-specification.html): yêu cầu metadata, class Java và Mojo lifecycle.
