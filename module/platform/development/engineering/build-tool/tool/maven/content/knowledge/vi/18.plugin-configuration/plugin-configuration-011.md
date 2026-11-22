# Xác minh cấu hình hiệu lực trước khi chạy goal trong Maven

## 1. Vì sao cần xác minh trước khi thực thi?

Trong một dự án Java, cấu hình của Maven plugin có thể nằm ở nhiều nơi: parent POM, POM module, `pluginManagement`, `plugins`, profiles, `executions` hoặc thuộc tính truyền từ CLI. Goal mà bạn chuẩn bị chạy có thể không dùng đúng giá trị đang nhìn thấy trong một đoạn `pom.xml` riêng lẻ.

Ví dụ một nhóm tin rằng Compiler Plugin đang biên dịch Java 17, nhưng một profile trong CI kích hoạt khác với máy cá nhân; hoặc JAR Plugin được cấu hình tạo `Main-Class`, nhưng gọi trực tiếp `jar:jar` có thể sử dụng execution/context khác với goal được bind ở phase `package`. Chỉ đọc một mảnh POM chưa đủ để kết luận.

**Xác minh cấu hình hiệu lực trước khi chạy goal** là kiểm tra có hệ thống:

1. **Project model:** POM sau khi áp dụng kế thừa, profiles và cấu hình quản lý plugin chứa gì?
2. **Plugin descriptor:** goal thực sự hỗ trợ những tham số nào, kiểu dữ liệu, giá trị mặc định và user property nào?
3. **Mojo execution:** ở invocation và execution cụ thể, plugin được nạp với những tham số thực tế nào?
4. **Artifact/output:** sau khi chạy, kết quả có phản ánh giá trị dự kiến không?

Không có một lệnh Maven duy nhất bảo đảm hiển thị chính xác mọi lớp trên cho tất cả plugin. Bài này trình bày cách kết hợp **Maven Help Plugin**, kiểm tra POM, lệnh debug có kiểm soát và việc kiểm chứng đầu ra thực tế.

Mục tiêu sau bài học:

- Phân biệt POM nguồn, **effective POM** và **runtime configuration của goal/Mojo**.
- Xác minh Maven profile, version plugin, property, `pluginManagement`, `executions` và goal.
- Biết dùng `help:effective-pom`, `help:active-profiles`, `help:evaluate`, `help:describe`, `help:effective-settings`.
- Hiểu một số lý do khiến `mvn package` và `mvn jar:jar` không cùng ngữ nghĩa.
- Thực hành Java 17 với Maven Compiler Plugin và JAR Plugin, kiểm chứng thông tin manifest.
- Chẩn đoán lỗi sai JDK, sai profile, sai execution hoặc config bị override mà không sửa mò POM.

Phạm vi: Maven 3.x và POM model 4.0.0, Java 17. Phiên bản plugin trong bài được chốt để dễ tái hiện, không khẳng định chúng là bản mới nhất.

## 2. Bốn tầng cấu hình cần phân biệt

| Tầng | Nguồn | Câu hỏi trả lời | Giới hạn |
| --- | --- | --- | --- |
| **POM nguồn** | `pom.xml` của module, parent POM. | Nhóm đã khai báo gì trong file? | Chưa tính đầy đủ kế thừa, profiles, CLI và descriptor. |
| **Effective POM** | `help:effective-pom`. | Maven đã hợp nhất POM/parent/profile thành model nào? | Không phải bản dump hoàn chỉnh mọi tham số của một Mojo khi thực thi. |
| **Plugin/goal descriptor** | `help:describe` và plugin docs. | Goal có tham số nào, default/`User Property`/requirements ra sao? | Mô tả tham số nói chung, không nhất thiết là giá trị đã inject ở invocation này. |
| **Mojo execution + output** | Log `mvn -X` có kiểm duyệt; artifact hoặc tác động của goal. | Goal thật sự chạy với cấu hình nào, và đã làm gì? | Không phải plugin nào cũng log rõ mọi giá trị; có thông tin nhạy cảm. |

**Chốt khái niệm:** `effective POM` là **model đã kết hợp**, còn cấu hình của một Mojo còn có thể phụ thuộc vào **plugin descriptor**, Maven expressions, user properties, execution ID và trạng thái/lựa chọn lúc gọi goal. Nếu chỉ xem POM XML rồi tuyên bố mọi tham số của goal đã được xác minh, kết luận có thể thiếu căn cứ.

### Sơ đồ dòng chảy

~~~text
Parent POM + module pom.xml + super POM
                  │
           active Maven profiles
                  │
                  ▼
          Effective project model
                  │
         pluginManagement / plugins
                  │
         goal/execution/phase đã chọn
                  │
       Plugin descriptor + expressions
                  │
            Maven user properties
                  │
                  ▼
           Mojo parameter values
                  │
                  ▼
         Plugin goal thực thi
                  │
                  ▼
        JAR / classes / reports / log
~~~

Sơ đồ thể hiện các nguồn ảnh hưởng **ở mức khái niệm**, không phải bảng ưu tiên tuyến tính đúng cho mọi tham số. Một user property chỉ tác động tới parameter nếu goal/plugin thực sự sử dụng property hoặc cấu hình biểu thức đó.

## 3. Phase và goal: xác nhận đúng thứ bạn sắp chạy

Trước hết phân biệt:

~~~bash
mvn compile
mvn compiler:compile
mvn package
mvn jar:jar
~~~

- `mvn compile`: yêu cầu chạy default lifecycle đến phase `compile`; Maven còn chạy các goal bound ở những phase trước.
- `mvn compiler:compile`: gọi trực tiếp goal `compile` của Maven Compiler Plugin; không tự động chạy toàn bộ phase trước đó.
- `mvn package`: chạy lifecycle đến phase `package` theo packaging của project, bao gồm những goal phù hợp như compile, test và jar.
- `mvn jar:jar`: gọi trực tiếp một goal của JAR Plugin; không phải bản thay thế toàn bộ `package`.

Một goal có thể được bind vào nhiều executions với cấu hình khác nhau. Khi gọi trực tiếp, Maven còn có khái niệm **CLI execution**; việc chọn cấu hình execution cho lời gọi trực tiếp không nên suy ra từ tên phase hoặc từ cấu hình của một execution khác.

**Việc xác minh phải gắn với invocation thật.** Nếu CI chạy `mvn -Pprod clean verify` nhưng bạn chỉ kiểm tra `mvn help:effective-pom` không có `-Pprod`, hai invocation không còn cùng bối cảnh.

## 4. Tìm đúng Maven project và active profiles

Trước khi kiểm tra plugin, xác nhận Maven/JDK và project:

~~~bash
mvn --version
java -version
mvn help:active-profiles
~~~

`mvn --version` cho biết Maven và JDK mà Maven đang sử dụng; `java -version` cho biết lệnh `java` hiện tại trên terminal. Trong môi trường có nhiều JDK, hai lệnh không nhất thiết dùng cùng một installation. Compiler Toolchains có thể chọn thêm JDK khác nếu được cấu hình.

Nếu bạn dùng multi-module Maven reactor, phải xác định **module cần điều tra**. Ví dụ:

~~~bash
mvn -f service/pom.xml help:effective-pom -Doutput=service-effective.xml
~~~

Lệnh trên là ví dụ **có điều kiện**, chỉ chạy khi project thật có `service/pom.xml`. `-f` chỉ định POM mục tiêu. Một goal của module `service` không nhất thiết nhận cấu hình giống parent aggregator hoặc module `web`.

### Profiles phải giống lần chạy thật

Kiểm tra riêng:

~~~bash
mvn -Pdev help:active-profiles
mvn -Pprod help:active-profiles
~~~

Một POM profile có thể thay properties, plugins hoặc executions. Profiles ở `settings.xml` còn có thể bổ sung repositories và properties. Theo cơ chế Maven, effects của profiles đang active được đưa vào model; **profile không active không tham gia**.

Đừng viết trong báo cáo “Plugin đang chạy production config” khi chỉ thấy một profile có ID `prod` **được khai báo**. Phải xác minh nó **đã active trong invocation**.

## 5. `help:effective-pom` — công cụ nền tảng

Lệnh tối thiểu:

~~~bash
mvn help:effective-pom
~~~

Thực tế thường nên xuất ra file:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Lệnh này tạo **effective POM** cho build hiện tại sau khi xét các profiles đang active. File xuất ra giúp bạn tìm:

- `<properties>` sau khi model được kết hợp.
- `<build><plugins>` và `<build><pluginManagement>`.
- Version của plugin được khai báo/quản lý.
- `<configuration>` của plugin, các `<executions>` và ID/phase/goals.
- Cấu hình khác do parent/super POM và profile đóng góp.

### Biết cấu hình đến từ đâu với verbose

Maven Help Plugin 3.5.2 hỗ trợ tùy chọn `verbose` để thêm chú thích vị trí nguồn cho phần tử XML:

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-verbose.xml
~~~

Khi có cấu hình kế thừa khó hiểu, các chú thích nguồn trong file này giúp xác định phần tử xuất phát từ parent, POM hiện tại hoặc profile nào. Nội dung và độ chi tiết comment tùy Help Plugin; không coi comment là một API ổn định để viết script parsing.

### Điều effective POM **không** hứa hẹn

`help:effective-pom` không phải màn hình tất cả giá trị parameter **sau khi plugin container inject vào Mojo**. Một số giá trị mặc định được định nghĩa trong **goal descriptor** hoặc hình thành qua Maven expressions ở thời điểm chạy goal.

Ví dụ `<configuration><release>17</release></configuration>` trong effective POM là chứng cứ có một khai báo cấu hình. Nhưng để biết compiler goal trong invocation thật có lấy giá trị đó không, còn phải kiểm tra:

- Plugin/goal version có đúng không?
- Có execution-specific config nào áp dụng không?
- Có user property/toolchain làm thay đổi parameter không?
- Log compilation hoặc đầu ra bytecode có đúng Java release không?

**Không tự động suy ra** mọi tham số không xuất hiện trong effective POM là không được thiết lập: plugin descriptor còn có default values.

## 6. `help:describe` — định nghĩa tham số của goal

Một cách hỏi plugin/goal chính xác:

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0 -Dgoal=compile -Ddetail=true
~~~

Nội dung goal description có thể cho thấy:

- Tên goal và ý nghĩa.
- Những tham số hợp lệ và kiểu dữ liệu.
- Required/default value.
- **User Property** nếu plugin công bố property đó.
- Những yêu cầu về project/lifecycle/phase nếu được descriptor mô tả.

So với effective POM:

| Câu hỏi | Công cụ thích hợp |
| --- | --- |
| “POM hiệu lực có khai báo `release` không?” | `help:effective-pom` |
| “Goal `compile` có hỗ trợ `release` không?” | `help:describe` hoặc tài liệu Compiler Plugin đúng version |
| “Parameter `release` có thể gán bằng user property nào?” | `help:describe` / goal docs |
| “Compiler đã nhận giá trị nào trong lần chạy này?” | Log `-X` có kiểm duyệt và kiểm chứng bytecode/command thật |
| “Ứng dụng chạy trên JDK nào?” | JDK runtime, toolchain, deployment config |

`help:describe` **không thực thi goal được mô tả**. Nó là goal của Help Plugin dùng để xem thông tin một plugin khác.

### Tránh suy đoán từ tên property

Ví dụ phổ biến của Compiler Plugin là `maven.compiler.release`. Nhưng không phải mọi parameter của mọi plugin đều có user property, và không phải biến `-DsomeName=value` nào cũng override cấu hình XML. Phải kiểm tra chính descriptor/tài liệu của goal.

Ngay cả khi có user property, một `<configuration>` tường minh và Maven expression có thể tương tác khác với suy đoán “mọi `-D` luôn thắng”. Hãy kiểm tra kết quả trong invocation dự kiến.

## 7. `help:evaluate` — xem Maven expression cụ thể

Thay vì đọc cả effective POM, có thể đánh giá một biểu thức:

~~~bash
mvn help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn help:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
~~~

Với một project hợp lệ có các property tương ứng, lệnh thứ nhất cho artifactId, lệnh thứ hai cho release property. Nó **không tự kiểm tra** một plugin/goal đã sử dụng property đó.

Lưu ý:

- `-q` giảm log Maven, `-DforceStdout` đề nghị Help Plugin in kết quả ngay cả ở chế độ quiet.
- Nếu property thiếu hoặc expression không resolve được, output có thể không như kỳ vọng; không ép mọi Maven version phải in một chuỗi lỗi giống nhau.
- CLI có thể được truyền property `-D...` để thử dự đoán, nhưng kết quả chỉ phản ánh expression evaluation trong context lệnh đó.
- `help:evaluate` không tự thực thi `compiler:compile` hoặc `jar:jar`.

### Các giá trị nên kiểm tra

Với một lần chạy Java build phổ biến, các expression hữu ích gồm:

~~~text
project.groupId
project.artifactId
project.version
project.packaging
project.build.directory
maven.compiler.release
~~~

Nhưng **không phải tất cả plugin parameters đều ánh xạ thành Maven properties truy vấn được**. Đôi khi chúng chỉ được khai báo trong plugin `<configuration>`. Trong trường hợp đó, effective POM, goal descriptor và debug logs sẽ phù hợp hơn.

## 8. `pluginManagement` khác `plugins`

Một nguồn nhầm lẫn phổ biến:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đây là **mảnh POM**, không phải file XML độc lập. `pluginManagement` chỉ cung cấp **quy tắc quản lý** version/config cho plugin khi nó được sử dụng trong project hoặc các module con.

Trong khi đó:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

là khai báo plugin được dùng trong build. Version/config có thể được hợp nhất từ `pluginManagement` và khai báo `<plugins>`, hoặc từ parent. Khi plugin đã được bind bởi lifecycle packaging, management cũng có thể tác động tới plugin tương ứng.

**Điểm cần xác minh:** một plugin có mặt trong `pluginManagement` chưa có nghĩa một goal tùy ý của plugin đó sẽ được chạy trong lifecycle; phải có binding, execution hoặc invocation phù hợp.

### Khi parent và module cùng khai báo

Parent POM có thể chốt version và thiết lập chung, còn module con thêm hoặc override các tham số plugin. `help:effective-pom` cần chạy ở **module cần xây** để kiểm tra phần hợp nhất.

Nếu module con tự đặt `<inherited>false</inherited>`, `combine.self` hoặc `combine.children` ở những nơi phù hợp, kết quả merge có thể thay đổi. Không áp dụng quy tắc “child luôn override toàn bộ” vì cấu hình plugin thường được **merge theo cấu trúc XML**, và chính sách kế thừa/execution ID cũng quan trọng.

## 9. Plugin-level config và execution-specific config

Một plugin có thể có cấu hình chung:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <encoding>UTF-8</encoding>
    </configuration>
</plugin>
~~~

Và trong trường hợp khác, plugin có thêm `<executions>`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <encoding>UTF-8</encoding>
    </configuration>
    <executions>
        <execution>
            <id>copy-extra</id>
            <phase>generate-resources</phase>
            <goals>
                <goal>copy-resources</goal>
            </goals>
            <configuration>
                <outputDirectory>${project.build.directory}/extra</outputDirectory>
                <resources>
                    <resource>
                        <directory>src/extra-resources</directory>
                    </resource>
                </resources>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **mảnh cấu hình minh họa**. Nó chỉ hợp lý khi thư mục `src/extra-resources` tồn tại và được tạo như một phần dự án. Với goal `copy-resources`, `outputDirectory` và `resources` nằm trong configuration dành cho execution `copy-extra`.

**Điểm cần nhớ:** một goal có thể chạy bằng:

- Một execution được bind vào lifecycle phase.
- Một execution cụ thể do người dùng yêu cầu theo cú pháp thích hợp ở Maven version hỗ trợ.
- Một lời gọi goal trực tiếp từ CLI.

Các invocation có thể khác context/configuration. Đọc đúng **execution ID, phase và goal** trong effective POM, không chỉ đọc plugin-level `<configuration>`.

### Tại sao execution ID quan trọng?

Parent/child POM có thể merge executions với cùng `id`. Các execution ID phổ biến do lifecycle tạo (ví dụ `default-compile` hay `default-jar` trong packaging tương ứng) còn có ngữ nghĩa liên quan binding mặc định. Một execution do bạn đặt tên `verify-docs` chưa chắc được gọi khi bạn thực thi `mvn plugin:goal` trực tiếp.

Khi định cấu hình một goal quan trọng:

1. Xác định goal trong plugin nào.
2. Xác định invocation qua lifecycle hay CLI.
3. Xác định execution ID liên quan.
4. Tìm plugin-level và execution-level `<configuration>`.
5. Kiểm tra log và output thực tế.

**Đừng mặc định** mọi goal `jar:jar` được chạy đều dùng execution `default-jar` trong mọi bối cảnh.

## 10. Java 17 thực hành: một cấu hình plugin có đầu ra kiểm chứng được

Ta sẽ tạo một JAR có **manifest chứa main class và trường `Build-Channel`**. Giá trị trường này được cấu hình trong Maven JAR Plugin và lấy từ Maven property. Khi thay profile `dev` hoặc `prod`, bạn sẽ quan sát:

1. Active profile và property hiệu lực.
2. Cấu hình JAR Plugin ở effective POM.
3. Giá trị thật đã được đưa vào manifest của JAR.
4. Dòng stdout của chính ứng dụng Java chạy từ JAR.

Cây thư mục:

~~~text
plugin-effective-config-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── App.java
~~~

### 10.1. POM đầy đủ có pluginManagement, plugins và profiles

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>plugin-effective-config-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.channel>local</demo.channel>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                    <configuration>
                        <release>${maven.compiler.release}</release>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <showWarnings>true</showWarnings>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.App</mainClass>
                        </manifest>
                        <manifestEntries>
                            <Build-Channel>${demo.channel}</Build-Channel>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>dev</id>
            <properties>
                <demo.channel>dev</demo.channel>
            </properties>
        </profile>
        <profile>
            <id>prod</id>
            <properties>
                <demo.channel>prod</demo.channel>
            </properties>
        </profile>
    </profiles>
</project>
~~~

**Phân tích POM:**

- `maven.compiler.release=17` chốt Java 17. Compiler Plugin được quản lý phiên bản `3.13.0` và `<release>${maven.compiler.release}</release>`.
- Trong `<build><plugins>`, Compiler Plugin chỉ thêm `<showWarnings>true</showWarnings>`; cấu hình `release` được merge từ `pluginManagement`.
- JAR Plugin nhận version `3.4.2` từ `pluginManagement` và cấu hình archive từ `<plugins>`.
- `Main-Class` cho phép chạy JAR bằng `java -jar`.
- `Build-Channel` là **trường manifest tùy chỉnh**, giá trị được Maven nội suy từ property `demo.channel` khi build.
- Property cơ sở `local` dùng khi không kích hoạt `dev` hay `prod`.
- Profile `dev` và `prod` cung cấp giá trị `demo.channel` khác nhau. **Không có profile nào tự active** trong POM mẫu.

**Lưu ý:** mảnh `${...}` ở trên khi tạo thành Markdown được hiển thị đúng cú pháp Maven như `${demo.channel}` (ký hiệu dollar + ngoặc nhọn). Maven POM phải chứa dấu dollar thực tế. Không viết dấu cách giữa dollar và ngoặc nhọn.

### 10.2. Java class đọc thông tin đã ghi vào manifest

Tạo `src/main/java/com/example/App.java`:

~~~java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.util.jar.Manifest;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        try (InputStream input =
                     App.class.getResourceAsStream("/META-INF/MANIFEST.MF")) {
            if (input == null) {
                throw new IllegalStateException(
                        "JAR manifest was not found on classpath");
            }

            Manifest manifest = new Manifest(input);
            String channel = manifest.getMainAttributes()
                    .getValue("Build-Channel");

            if (channel == null) {
                throw new IllegalStateException(
                        "Build-Channel attribute is missing");
            }

            System.out.println("Build channel: " + channel);
            System.out.println("Effective plugin configuration demo");
        }
    }
}
~~~

Đây là Java 17 thuần với `java.util.jar.Manifest` thuộc JDK. Khi chạy trong JAR theo lệnh `java -jar` với một JAR chứa manifest, `getResourceAsStream` tìm resource `META-INF/MANIFEST.MF` và đọc trường custom.

Vì POM ví dụ tạo **một JAR đơn giản duy nhất**, đọc manifest qua classpath trong chương trình này phù hợp. Trong một ứng dụng nhiều JAR/classloader, nhiều `META-INF/MANIFEST.MF` có thể tồn tại, nên ứng dụng production muốn biết metadata của chính artifact thường phải có cách xác định nguồn chính xác hơn. Ví dụ này chỉ nhằm **quan sát kết quả JAR Plugin**.

### 10.3. Xác minh trước khi build với profile dev

Trong thư mục dự án:

~~~bash
mvn --version
mvn -Pdev help:active-profiles
mvn -Pdev help:evaluate -Dexpression=demo.channel -q -DforceStdout
mvn -Pdev help:effective-pom -Doutput=effective-dev.xml
~~~

Kết quả cần xác nhận:

- `help:active-profiles` cho thấy profile `dev` active.
- `help:evaluate` trên POM này dự kiến in giá trị `dev`.
- `effective-dev.xml` có plugin management và cấu hình JAR Plugin thể hiện `Build-Channel` dùng giá trị dự kiến, tùy cách plugin Help biểu diễn expression đã được nội suy.

**Đừng chỉ xem một trong ba bước.** Active profile không chứng minh mọi expression của plugin đã được dùng; expression evaluation không chứng minh plugin đã chạy.

Khi kiểm tra effective POM, tìm:

~~~xml
<artifactId>maven-compiler-plugin</artifactId>
<version>3.13.0</version>
<release>17</release>
<showWarnings>true</showWarnings>
~~~

Các phần tử trên có thể **không liền kề** trong XML: version, configuration của plugin và entries trong `pluginManagement`/`plugins` có thể xuất hiện ở các vị trí khác nhau. Đây là **những dòng cần tìm**, không phải một đoạn XML độc lập để dán vào POM.

Với JAR Plugin, tìm các trường:

~~~xml
<artifactId>maven-jar-plugin</artifactId>
<version>3.4.2</version>
<mainClass>com.example.App</mainClass>
<Build-Channel>dev</Build-Channel>
~~~

Nếu Help Plugin hiển thị expression chưa được triển khai hoàn toàn trong một vị trí, hãy kiểm tra giá trị thông qua `help:evaluate`, debug context hoặc artifact thực tế thay vì đoán.

### 10.4. Build và đối chiếu đầu ra

Sau khi đã xem cấu hình, build:

~~~bash
mvn -Pdev clean package
~~~

Chạy chương trình:

~~~bash
java -jar target/plugin-effective-config-demo-1.0-SNAPSHOT.jar
~~~

**Stdout chính xác của ứng dụng:**

~~~text
Build channel: dev
Effective plugin configuration demo
~~~

Maven có thể ghi nhiều log `BUILD SUCCESS` trong quá trình build; **hai dòng trên chỉ là stdout của Java**.

Vì JAR Plugin ghi manifest, bạn có thể dùng công cụ JDK để xác nhận entry `META-INF/MANIFEST.MF` có tồn tại:

~~~bash
jar tf target/plugin-effective-config-demo-1.0-SNAPSHOT.jar
~~~

Tìm `META-INF/MANIFEST.MF`. `jar tf` chỉ liệt kê tên entry, **không đọc nội dung**. Chương trình Java ở trên là một cách đọc nội dung cụ thể.

### 10.5. Cùng POM, nhưng profile prod

Kiểm tra trước:

~~~bash
mvn -Pprod help:active-profiles
mvn -Pprod help:evaluate -Dexpression=demo.channel -q -DforceStdout
mvn -Pprod help:effective-pom -Doutput=effective-prod.xml
~~~

Property dự kiến là `prod`. Tiếp đó:

~~~bash
mvn -Pprod clean package
java -jar target/plugin-effective-config-demo-1.0-SNAPSHOT.jar
~~~

**Stdout chính xác:**

~~~text
Build channel: prod
Effective plugin configuration demo
~~~

**Khác biệt không nằm ở mã Java**: chính cấu hình Maven/JAR Plugin đã tạo manifest khác. Dù tên file JAR vẫn là `plugin-effective-config-demo-1.0-SNAPSHOT.jar`, nội dung có thể khác vì profile đã thay property.

Đây là lý do phải ghi nhận **active profiles và configuration** cho build phát hành: nếu CI build bằng `prod` nhưng máy cá nhân kiểm tra effective POM của `dev`, hai bên không phân tích cùng một artifact.

### 10.6. Thử user property `-D`

Giữ profile `dev` nhưng truyền property trên CLI:

~~~bash
mvn -Pdev -Ddemo.channel=qa help:evaluate -Dexpression=demo.channel -q -DforceStdout
~~~

Đối với POM mẫu và cơ chế Maven CLI user properties, giá trị kỳ vọng là `qa`. Để kiểm chứng **cách JAR Plugin thật dùng giá trị này**, chạy:

~~~bash
mvn -Pdev -Ddemo.channel=qa clean package
java -jar target/plugin-effective-config-demo-1.0-SNAPSHOT.jar
~~~

Kết quả mong đợi:

~~~text
Build channel: qa
Effective plugin configuration demo
~~~

Đây là phép thử trực tiếp cho expression `${demo.channel}` được dùng trong JAR Plugin. Không suy rộng rằng `-Dfoo=bar` luôn override mọi plugin parameter: chỉ những parameter/expressions có liên quan mới bị ảnh hưởng. Với goal khác, phải xem tài liệu descriptor và cấu hình tường minh.

**Lưu ý bảo mật:** thông tin nhạy cảm không nên được đặt vào manifest. Trong bài chỉ dùng nhãn `dev`, `prod`, `qa`. Đừng biến ví dụ này thành cách nhúng password/token vào JAR.

## 11. Đối chiếu config thực thi bằng debug log

Nếu hiệu quả thực tế khác effective POM, có thể chạy Maven với debug:

~~~bash
mvn -Pdev -X package
~~~

Maven có thể in cấu hình của plugin goal trong các dòng debug, gồm các tham số đã được đưa vào Mojo. Một số phiên bản/plugin in các dòng kiểu `(f) release = 17`, `(f) showWarnings = true` hoặc những giá trị cấu hình khác.

**Không bảo đảm mọi plugin/version in tất cả tham số giống nhau.** Đây là công cụ **chẩn đoán**, không phải một chuẩn có cấu trúc ổn định để parse bằng script. Không chỉ dựa vào log để khẳng định một plugin đã tạo đúng artifact nếu có thể kiểm chứng đầu ra trực tiếp.

### Log có thể chứa gì nhạy cảm?

Log `-X` có thể chứa:

- Địa chỉ repository nội bộ, proxy, đường dẫn cá nhân.
- Giá trị Maven user properties.
- File paths và thông tin môi trường.
- Cấu hình plugin/khóa truy cập trong trường hợp dự án quản lý secrets không đúng.

Vì vậy chỉ chia sẻ đoạn log **đã rà soát và che thông tin nhạy cảm**. Tránh ghi password lên command line `-Dpassword=...` khi có lựa chọn quản lý secret an toàn hơn.

### Không có `dry-run` thống nhất cho mọi Maven goal

Một số plugin có tham số `dryRun` hoặc goal kiểm tra riêng, nhưng Maven không có quy tắc rằng **mọi `plugin:goal` đều hỗ trợ `-DdryRun=true`**. Lệnh đó có thể bị bỏ qua hoàn toàn nếu plugin không đọc user property `dryRun`.

Trước một goal có tác động (deploy, release, publish, xóa tài nguyên), hãy:

1. Kiểm tra cấu hình và scope như hướng dẫn.
2. Đọc goal descriptor để biết có dry-run/tham số an toàn nào thật sự được hỗ trợ.
3. Dùng môi trường thử nghiệm và quyền hạn phù hợp.
4. Tránh thực thi production goal chỉ để “xem config”.

## 12. Xác minh `help:effective-settings` khi repository/settings có liên quan

Một plugin có thể cần tải artifact, metadata, credentials hoặc kết nối repository. Một POM hiệu lực đúng vẫn chưa đủ nếu Maven dùng settings khác với dự định.

Lệnh:

~~~bash
mvn help:effective-settings
~~~

giúp kiểm tra cấu hình settings đã kết hợp (global/user settings). Nó khác `help:effective-pom` vì settings phục vụ các cấu hình như:

- Mirrors/repositories và plugin repositories liên quan.
- Profiles trong settings và những properties/repositories được profile kích hoạt.
- Proxy/server IDs theo cấu trúc Maven settings.
- Local repository path.

**Không chia sẻ nguyên `help:effective-settings`** khi chưa kiểm tra thông tin nhạy cảm. Dù một số công cụ có cơ chế che password, đừng giả định mọi phiên bản/plugin/log đều che toàn bộ bí mật.

Đối với lỗi plugin goal không tải được, `help:effective-pom` có thể không đủ. Cần xem cả **effective settings**, plugin repositories, mirrors và mạng.

## 13. Các thứ tự ưu tiên dễ hiểu sai

### 13.1. Không có một bảng “CLI luôn cao nhất” áp dụng mọi tình huống

Maven dùng nhiều tầng cấu hình. Cần phân biệt:

- **Model properties:** biểu thức `${name}` trong POM/plugin configuration có thể tham chiếu project property, user property từ `-D` hoặc các nguồn khác theo context.
- **Goal user properties:** một Mojo parameter chỉ bị điều khiển trực tiếp qua property nếu plugin/descriptor hỗ trợ nó hoặc cấu hình chứa expression liên quan.
- **Plugin-level vs execution-level configuration:** execution-specific config có thể bổ sung hoặc thay những giá trị ở cấp plugin.
- **Parent vs child configuration:** Maven merge XML theo rules của model và cấu hình `combine.*` khi có.
- **Profile activation:** chỉ các profile active tham gia; các phần tử do profile đóng góp được merge vào model.

Vì vậy “đã thêm `-Drelease=17`” không chứng minh Compiler Plugin nhận 17; property phổ biến là `maven.compiler.release`, và cách nó được dùng phụ thuộc POM/plugin. Một cách khác là tường minh `<release>${maven.compiler.release}</release>` trong plugin configuration như ví dụ.

### 13.2. Profile chỉ có trong source không có nghĩa đã active

Hai POM cùng nội dung nhưng invocation khác:

~~~bash
mvn help:effective-pom -Doutput=base.xml
mvn -Pprod help:effective-pom -Doutput=prod.xml
~~~

có thể cho model khác nhau. Nếu profile `prod` chưa active trong lệnh thứ nhất, dữ liệu từ nó không được áp dụng. **Luôn dùng cùng `-P`/`-D` với invocation goal bạn định kiểm tra**.

### 13.3. Thay POM sau khi tạo file effective POM

`effective-pom.xml` là **snapshot báo cáo tại thời điểm lệnh chạy**, không phải một file theo dõi thay đổi. Nếu bạn đổi parent/profile/CLI mà không chạy lại Help Plugin, báo cáo cũ không còn đại diện cho invocation mới.

### 13.4. Plugin version không xuất hiện trong POM nguồn

Một plugin có thể được quản lý ở parent, được bind mặc định bởi packaging hoặc chọn version qua Maven plugin version resolution. Do đó nếu POM hiện tại không ghi `<version>`, đừng kết luận plugin “không có version”. Hãy xem effective POM, log của execution và chốt plugin version cho build quan trọng.

## 14. Trường hợp Maven đa module

Ví dụ reactor:

~~~text
parent/
├── pom.xml
├── api/pom.xml
└── service/pom.xml
~~~

Parent quản lý Compiler Plugin Java 17; module `service` override một phần config. Để kiểm tra module `service`, đừng chỉ chạy `help:effective-pom` ở root rồi kết luận.

Có thể dùng:

~~~bash
mvn -f service/pom.xml help:effective-pom -Doutput=service-effective.xml
~~~

Hoặc khi cần chạy trong reactor theo module, dùng tùy chọn `-pl` phù hợp, nhưng lưu ý Help Plugin goal có thể là aggregator và file output có thể khác theo cách invocation/selector. Khi nghi ngờ, chỉ định đúng `-f` và quan sát project được báo cáo trong XML.

### Những dấu hiệu đáng kiểm tra

- Parent dùng `pluginManagement`, module dùng `plugins`.
- Cùng plugin nhưng config khác nhau giữa modules.
- Một execution ID trùng giữa parent/child.
- `<inherited>false</inherited>` hoặc plugin configuration XML có `combine.self` / `combine.children`.
- Profiles khác nhau ở parent, module hoặc settings.
- Mỗi module có packaging riêng (JAR, WAR, POM), nên lifecycle bindings khác nhau.

**Một file effective POM cho một module không phải bản tổng hợp mọi module.** Trong CI, lưu báo cáo hoặc validation của đúng module tạo artifact.

## 15. Một số lỗi và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Compiler dùng Java release khác kỳ vọng. | Parent/profile/plugin config hoặc property khác. | `help:evaluate`, `effective-pom`, `help:describe`, `-X` và bytecode version. |
| Chạy `-Pprod` nhưng JAR có Build-Channel=local. | Sai profile, gọi nhầm POM, property/entry bị override, dùng JAR cũ. | `help:active-profiles`, `help:evaluate`, effective POM, build sạch, đọc manifest. |
| Version plugin khác máy CI. | Parent hoặc plugin version chưa chốt. | `mvn --version`, effective POM, pin plugin version. |
| `<pluginManagement>` có config nhưng goal không chạy. | Management không tự bind/tạo execution. | Xem `<plugins>`, executions và lifecycle bindings. |
| `mvn compiler:compile` khác `mvn compile`. | Direct goal vs lifecycle phase. | Kiểm tra các phase/goals trước và execution ID. |
| Goal bị áp config không như POM. | Execution-level config hoặc descriptor default/CLI property. | So plugin-level/execution-level config, `help:describe`, `-X`. |
| `-Dfoo=bar` không đổi output. | Plugin không đọc property hoặc XML đã chọn giá trị khác. | Xem user property/parameter của goal, dùng test đầu ra. |
| `help:evaluate` in giá trị đúng nhưng artifact khác. | Giá trị chỉ có ở project model, goal không dùng nó, hoặc artifact cũ. | Kiểm tra plugin config, clean build, manifest/class. |
| Xem effective POM sai module. | Terminal đang ở aggregator hoặc dùng `-f` sai. | Chỉ định đúng POM của module cần điều tra. |
| Plugin tải thất bại dù POM config đúng. | Plugin repository, mirror, proxy, credential hoặc offline mode. | `help:effective-settings`, plugin repositories, Maven log. |
| XML từ `help:effective-pom` không chứa mọi default. | Default có trong plugin descriptor, không phải POM model. | `help:describe` và kiểm tra goal thực thi. |
| `-X` không cho thấy tham số mong muốn. | Plugin/Maven version log khác nhau hoặc tham số không được báo. | Kiểm chứng artifact và tài liệu plugin, không parse log cứng. |
| `mvn package` tạo JAR không chạy bằng `java -jar`. | Manifest thiếu Main-Class hoặc JAR/manifest đang dùng sai. | Kiểm tra JAR Plugin config và `META-INF/MANIFEST.MF`. |
| Build success nhưng cấu hình chưa đúng. | Goal có thể thành công với default khác dự kiến. | Viết kiểm chứng đầu ra trước khi promote/deploy. |

## 16. Checklist kiểm chứng trước goal có tác động

Trước một goal quan trọng, xác nhận:

- [ ] Đang ở đúng project/module/POM và đúng Maven/JDK/toolchain.
- [ ] Lệnh là lifecycle phase hay plugin goal, với đúng prefix/coordinates và version.
- [ ] `-P`, `-D`, settings, environment của lần kiểm tra trùng invocation thực tế.
- [ ] Active profiles đã được kiểm tra, không chỉ có trong POM nguồn.
- [ ] Effective POM chỉ ra đúng plugin GA/version/configuration và các executions liên quan.
- [ ] `help:describe` xác nhận parameter thật sự tồn tại, user property và default.
- [ ] Plugin-level và execution-level config đã được phân biệt.
- [ ] Nếu output phụ thuộc một property, `help:evaluate` hoặc test phù hợp xác nhận expression.
- [ ] Tham số nhạy cảm không bị in vào log, POM, manifest hoặc artifact.
- [ ] Nếu cần, `-X` được đọc với kiểm soát dữ liệu nhạy cảm.
- [ ] Tác động của goal đã được hiểu; không giả định tất cả goals có dry-run.
- [ ] Có kiểm chứng output/test cho hành vi quan trọng, không chỉ tin `BUILD SUCCESS`.

**Chìa khóa:** trước khi chạy một goal có khả năng phát hành/triển khai, hãy kiểm chứng các giá trị dự định bằng những goal đọc/chẩn đoán **không tạo side effects sản xuất**, rồi mới thực hiện theo quy trình của nhóm.

## 17. Bài tập và đáp án tự kiểm tra

### Bài A — Xác minh project mẫu

1. Tạo đúng POM và `App.java` ở mục 10.
2. Chạy `mvn -Pdev help:active-profiles`; giải thích vì sao profile này được dùng.
3. Chạy `mvn -Pdev help:evaluate -Dexpression=demo.channel -q -DforceStdout`; ghi giá trị.
4. Tạo `effective-dev.xml` và tìm Compiler Plugin, JAR Plugin, versions và `Build-Channel`.
5. Build bằng `mvn -Pdev clean package` rồi chạy `java -jar ...`; so stdout với dự đoán.
6. Lặp lại với profile `prod`, đối chiếu manifest/ stdout.
7. Thử `-Ddemo.channel=qa` để thấy Maven user property ảnh hưởng expression trong JAR Plugin.
8. Dùng `help:describe` mô tả JAR Plugin goal `jar` và so với `-X` trong môi trường thực hành.
9. Giải thích vì sao `help:effective-pom` không đủ để chứng minh mọi default của goal.

### Bài B — Phân tích không cần chạy build

Cho POM mô tả:

~~~xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</pluginManagement>
~~~

Hãy trả lời:

- Chỉ có `pluginManagement` đã đủ chắc chắn goal `compile` sẽ chạy trong mọi project chưa?
- Nếu project là `packaging=pom` và không có source Java thì có giống JAR packaging không?
- Nếu child thêm `<showWarnings>true</showWarnings>` ở `<plugins>`, bạn kiểm tra cấu hình merged bằng gì?
- Nếu goal compile được gọi trực tiếp thay vì phase compile, có chắc các phase trước đã chạy không?
- Nếu một profile khác override `release`, cần chứng cứ gì trước khi build?

### Bài C — Chẩn đoán bối cảnh CI

CI chạy `mvn -Pprod -Ddemo.channel=release clean package`, trong khi máy dev dùng `mvn -Pdev clean package`. Hãy nêu:

1. Những nguồn configuration khác nhau.
2. Hai lệnh Help Plugin nào cần chạy để so active profile và expression hiệu lực.
3. Cách xem JAR Plugin configuration theo từng invocation.
4. Cách kiểm chứng manifest của artifact thật.
5. Vì sao không nên dùng cùng một artifact release version nhưng nội dung khác nhau mà không ghi provenance.

### Câu hỏi tự đánh giá

- Effective POM có bao gồm plugin descriptor defaults sau khi Mojo được inject chưa?
- `help:describe` thực thi Compiler Plugin goal compile hay chỉ mô tả nó?
- Vì sao `pluginManagement` không đồng nghĩa với `<plugins>`?
- User property `-Dfoo=bar` có chắc làm thay mọi tham số tên foo không?
- `-Pprod` trong POM mẫu có tự nhúng password hay URL production không?
- `mvn jar:jar` có tương đương `mvn package` không?
- Trong multi-module reactor, nên lấy effective POM của module nào?
- Khi nào cần đọc `help:effective-settings` thay vì chỉ `help:effective-pom`?
- Nếu kết quả artifact khác kỳ vọng dù `BUILD SUCCESS`, nguồn nào cần kiểm tra thêm?

## 18. Tổng kết

**Cấu hình hiệu lực trước khi chạy Maven goal không thể được xác minh chỉ bằng việc nhìn một đoạn `pom.xml`.** Cần kết hợp:

1. **Đúng invocation/context**: Maven/JDK, POM/module, `-P`, `-D`, settings.
2. **Effective POM**: các khai báo đã merge từ parent, profiles, `pluginManagement`, `plugins` và `executions`.
3. **Goal descriptor**: tham số hợp lệ, user property, default và yêu cầu của Mojo.
4. **Execution validation**: debug có kiểm soát và đầu ra thật như JAR, class files, report.

Ví dụ Java 17 cho thấy cùng một cấu hình JAR Plugin có thể ghi `Build-Channel=dev`, `prod` hoặc `qa` tùy context Maven. Nhưng **nhìn thấy một Maven property không chứng minh plugin đã dùng nó**; chỉ kết quả build/kiểm tra goal mới xác nhận hành vi.

Khi cần build ổn định, chốt plugin version, thống nhất profiles/settings trong CI, dùng các goal Help Plugin trước thao tác có tác động và **không coi `help:effective-pom` là bản dump đầy đủ mọi tham số thực thi**.

## Tài liệu chính thức

- Apache Maven Help Plugin — effective-pom: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Apache Maven Help Plugin — describe: https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html
- Apache Maven Help Plugin — evaluate: https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html
- Apache Maven Help Plugin — active-profiles: https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html
- Apache Maven Help Plugin — effective-settings: https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Introduction to Build Profiles: https://maven.apache.org/guides/introduction/introduction-to-profiles.html
- Apache Maven JAR Plugin — Manifest Customization: https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html
