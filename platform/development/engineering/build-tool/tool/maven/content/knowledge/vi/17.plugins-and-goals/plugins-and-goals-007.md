# Dùng help:describe để đọc goal, tham số và yêu cầu thực thi trong Maven

## 1. Tại sao cần tra cứu metadata của plugin?

Khi chạy Maven, các bước như biên dịch Java, kiểm thử, xử lý resources, đóng gói JAR hoặc triển khai artifact được thực hiện chủ yếu thông qua **plugin goals**. Mỗi plugin có nhiều goal, mỗi goal lại có **tham số riêng**, các giá trị mặc định và yêu cầu riêng khi thực thi. Chỉ đọc tên goal không đủ để biết một flag có hợp lệ hay không.

Ví dụ bạn muốn:
- biết `compiler:compile` nhận `<release>` hay `<source>`, kiểu giá trị của chúng và cách truyền bằng `-D`;
- tìm goal nào được cung cấp bởi `maven-compiler-plugin`;
- biết goal cần một Maven project, cần resolve dependencies hay không;
- xác định goal có default lifecycle phase, có hỗ trợ parallel build và có phải aggregator không;
- phân biệt “goal được mô tả” với “goal đã được Maven thực sự chạy”;
- giải thích khác biệt giữa phiên bản plugin đang đọc tài liệu và phiên bản thật trong dự án.

Maven Help Plugin có goal **`help:describe`** để tra cứu mô tả plugin hoặc một goal (Mojo). Nó đọc metadata mà plugin công bố, bao gồm **goals, parameters và các execution requirements**. Đây là một bước tra cứu trước khi chỉnh POM hoặc khi tìm hiểu vì sao lệnh Maven không hoạt động như dự kiến.

> **Nguyên tắc cốt lõi:** chạy `help:describe` là **đọc thông tin**. Nó **không thực thi goal** được mô tả; muốn biên dịch, chạy test hoặc package thì phải gọi phase/goal thật bằng một lệnh riêng.

Bài này dùng Maven 3.9.x, Maven Help Plugin 3.5.2, Maven Compiler Plugin 3.13.0 và Java 17 để có tên phiên bản cụ thể, nhưng cách tra cứu có thể áp dụng cho nhiều plugin khác.

## 2. Những khái niệm cần phân biệt trước khi dùng help:describe

### 2.1. Plugin là artifact; goal là thao tác do plugin cung cấp

Plugin có tọa độ Maven, ví dụ:

```text
groupId    = org.apache.maven.plugins
artifactId = maven-compiler-plugin
version    = 3.13.0
```

Plugin này có các goal như `compiler:compile` (biên dịch source chính) và `compiler:testCompile` (biên dịch test source). Goal còn được gọi là **Mojo** (*Maven plain Old Java Object*) trong ngữ cảnh Maven plugin descriptors.

Cú pháp gọi goal trực tiếp bằng prefix:

```bash
mvn compiler:compile
```

Cú pháp ghim tọa độ đầy đủ:

```bash
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile
```

Với dạng prefix ngắn `compiler:compile`, Maven phải phân giải plugin prefix và version theo cấu hình/metadata đang có. Dạng đầy đủ hữu ích khi muốn tái lập một lỗi ở đúng plugin version.

### 2.2. Goal không đồng nghĩa lifecycle phase

`compile` là **phase của default build lifecycle**; `compiler:compile` là **goal thuộc Compiler Plugin**.

```bash
mvn compile
```

yêu cầu Maven chạy các phase đến `compile`, bao gồm các goal được lifecycle mapping và POM gắn vào các phase thích hợp. Với project `packaging=jar` thông thường, một phần của bước này là `compiler:compile`.

Ngược lại:

```bash
mvn compiler:compile
```

gọi goal compiler trực tiếp, không nhất thiết chạy tất cả những phase trước đó như khi gọi `mvn compile`. Nếu project cần tạo source/resource trước compile, kết quả hai cách có thể khác.

**`help:describe` hỗ trợ cả hai hướng tìm hiểu:**
- `-Dcmd=compile`: hỏi về **phase** và lifecycle mapping theo project/packaging.
- `-Dcmd=compiler:compile`: hỏi về **plugin goal**.
- `-Dplugin=compiler -Dgoal=compile`: chọn đúng goal bên trong một plugin cụ thể.

### 2.3. Plugin descriptor, effective POM và runtime là ba nguồn khác nhau

Có ba câu hỏi riêng:

1. **Goal có khả năng gì?** Xem `help:describe` và goal documentation của đúng plugin version.
2. **Project đang cấu hình gì?** Xem `help:effective-pom`, parent, profile, `pluginManagement` và `<build><plugins>`.
3. **Lần build thực sự làm gì?** Xem Maven execution log, test reports, output files và lỗi thực tế.

Một plugin có parameter `release` không có nghĩa project đang đặt `release=17`; và một project đặt `release=17` không bảo đảm JDK hiện tại đủ mới để biên dịch. Không dùng một công cụ để thay thế tất cả những bằng chứng khác.

## 3. Lệnh help:describe đầy đủ và các tham số của chính nó

Maven Help Plugin 3.5.2 cung cấp goal:

```text
org.apache.maven.plugins:maven-help-plugin:3.5.2:describe
```

Cách gọi ngắn:

```bash
mvn help:describe -Dplugin=compiler
```

Cách gọi đủ tọa độ để ghim version Help Plugin:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=compiler
```

**Phân biệt hai phiên bản:** `maven-help-plugin:3.5.2` là **công cụ đang mô tả**, còn `maven-compiler-plugin:3.13.0` là **plugin được mô tả**. Ghim cả hai giúp tránh trả lời nhầm khi nhiều bản plugin cùng tồn tại trong local repository.

### 3.1. Bảng tham số của help:describe

| Tham số truyền vào goal describe | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `-Dplugin=...` | Xác định plugin bằng prefix, `groupId:artifactId` hoặc `groupId:artifactId:version` | `-Dplugin=compiler` |
| `-Dgoal=...` | Chỉ xem một goal thuộc plugin đã chỉ định | `-Dgoal=compile` |
| `-Ddetail=true` | Xem thông tin chi tiết hơn, nhất là parameters và requirements | `-Ddetail=true` |
| `-Dminimal=true` | Yêu cầu báo cáo gọn hơn | `-Dminimal=true` |
| `-Dcmd=...` | Mô tả một Maven command: phase, lifecycle hoặc goal | `-Dcmd=compile` |
| `-DgroupId=...` | GroupId của plugin, dùng cùng artifactId | `-DgroupId=org.apache.maven.plugins` |
| `-DartifactId=...` | ArtifactId của plugin, dùng cùng groupId | `-DartifactId=maven-compiler-plugin` |
| `-Dversion=...` | Version plugin được mô tả khi chỉ định groupId/artifactId riêng | `-Dversion=3.13.0` |
| `-Doutput=...` | Ghi báo cáo mô tả vào file UTF-8 thay vì in ra console | `-Doutput=compiler-describe.txt` |

Không bắt buộc cung cấp đồng thời `-Dplugin` và bộ `-DgroupId/-DartifactId/-Dversion`. Chọn **một cách xác định plugin** rõ ràng.

Các tên `plugin`, `goal`, `detail`, `cmd` là **tham số của Maven Help Plugin's describe goal**. Chúng không phải các tham số `release`, `fork` hoặc `outputDirectory` của Compiler Plugin. Đừng nhầm **công cụ mô tả** với **goal được mô tả**.

### 3.2. Ba cách tra cứu cùng một plugin

**Dạng ngắn theo prefix:**

```bash
mvn help:describe -Dplugin=compiler
```

Nhanh và tiện nhưng có thể chọn plugin version tùy project/plugin prefix resolution. Không dùng kết quả làm chứng cứ cho một version cụ thể nếu chưa xem đầu output.

**Dạng group/artifact/version tách trường:**

```bash
mvn help:describe -DgroupId=org.apache.maven.plugins -DartifactId=maven-compiler-plugin -Dversion=3.13.0
```

Thích hợp khi đã biết tọa độ plugin.

**Dạng ghim cả hai plugin versions và chọn goal:**

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0" -Dgoal=compile -Ddetail=true
```

Đây là lệnh chính của bài. Dấu nháy quanh `-Dplugin=...` cũng phù hợp trên Linux/macOS và giúp tránh một số vấn đề truyền đối số của PowerShell. Lệnh này sẽ **mô tả** `compiler:compile` ở phiên bản 3.13.0, chứ không thực hiện biên dịch.

## 4. Đọc từ tổng quan plugin đến một goal cụ thể

### Bước 1: xem toàn bộ goals

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0"
```

Kết quả sẽ có thông tin plugin identity, goal prefix, mô tả và các goal mà descriptor công bố. Điều cần rút ra: plugin nào, version nào, và **goal nào thực sự tồn tại**. Một số plugin có nhiều goal nhưng không có nghĩa toàn bộ chúng chạy trong mọi lifecycle.

### Bước 2: giới hạn vào đúng goal

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0" -Dgoal=compile
```

Đây là cách tránh phải đọc metadata của cả plugin khi bạn chỉ cần `compile`. Nếu muốn mô tả goal biên dịch test, thay `-Dgoal=compile` bằng `-Dgoal=testCompile`; hai goal liên quan nhưng yêu cầu, source roots và output có thể khác.

### Bước 3: bật chi tiết

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0" -Dgoal=compile -Ddetail=true
```

Tùy descriptor và phiên bản công cụ, kết quả chi tiết có thể cho biết:
- tên và mô tả của goal;
- các thuộc tính như **requires project**, **requires dependency resolution**, **default phase**, **thread-safe** và **aggregator** khi được khai báo;
- danh sách **parameters**, types, required/default values, user properties;
- metadata từ version nào parameter xuất hiện, và thông tin khác nếu plugin công bố.

**Đừng kỳ vọng từng phiên bản plugin in chính xác các nhãn giống nhau**. Dựa vào ý nghĩa của trường, không sao chép một khối “output chính xác” từ phiên bản cũ làm tiêu chuẩn.

### Bước 4: tìm đúng vị trí cấu hình

Nếu thấy Compiler Plugin parameter `release` hỗ trợ user property `maven.compiler.release`, có thể chọn một trong các cách cấu hình POM:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

hoặc plugin configuration:

```xml
<build>
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
</build>
```

Đây là **hai đoạn XML riêng biệt**, không phải hai POM hoàn chỉnh. Chỉ dùng một nguồn cấu hình rõ ràng trong ví dụ thực hành để tránh khó phân biệt priority. User property thường cho phép chạy `mvn -Dmaven.compiler.release=17 compile`.

## 5. Cách đọc từng trường parameter: không đoán từ tên

### 5.1. Parameter name và XML element

Tên parameter là điểm bắt đầu để viết `<configuration>` của goal. Ví dụ `release` được biểu diễn là:

```xml
<configuration>
    <release>17</release>
</configuration>
```

Nhưng không phải tất cả parameters đều nhận một chuỗi đơn; list/map/file/boolean có cấu trúc khác. Xem **Parameter Details** và ví dụ của **đúng plugin version** khi cấu hình nested elements.

### 5.2. Type có ý nghĩa gì?

Bảng thường gặp:

| Type trong metadata | Cách hiểu |
| --- | --- |
| `String` | Giá trị chuỗi; có thể vẫn phải hợp lệ theo một tập giá trị |
| `boolean` | true/false |
| `File` | Đường dẫn file hoặc thư mục |
| `List<String>` | Nhiều phần tử chuỗi, cần đúng cấu trúc XML mà plugin yêu cầu |
| `int` hoặc số khác | Giá trị số; có thể bị giới hạn phạm vi |
| `Map` / object | Cấu trúc phức hợp, phải đọc tài liệu |

Type **không có nghĩa plugin tự validate mọi giá trị trước khi build**. Ví dụ parameter kiểu String không chấp nhận mọi nội dung String về mặt nghiệp vụ; `release=banana` vẫn không phải lựa chọn hợp lệ để biên dịch Java.

### 5.3. Required không đồng nghĩa bắt buộc truyền -D

Một parameter có thể được đánh dấu `Required: Yes` nhưng lại có **Default** lấy từ Maven model. Ví dụ `outputDirectory` của compiler goal có thể sử dụng expression từ project. Điều đó có nghĩa goal cần giá trị sau khi Maven đánh giá cấu hình, **không phải** bạn phải cung cấp `-DoutputDirectory` mỗi lần chạy.

Giá trị có thể đến từ:
- giá trị mặc định trong descriptor;
- `project.build.outputDirectory` hoặc Maven project model;
- `<configuration>` trong POM/parent/plugin execution;
- profile/user properties và các nguồn khác theo quy tắc Maven.

Ngược lại, `Required: No` không cam kết goal luôn chạy được với mọi môi trường khi không truyền tham số. Nó vẫn có thể cần file input, JDK hoặc service bên ngoài.

### 5.4. Default: hằng số hoặc biểu thức cần giải quyết

Metadata có thể có default là biểu thức, chẳng hạn:

```text
Parameter: outputDirectory
Default: ${project.build.outputDirectory}
```

Đây là **bản diễn giải trường metadata**, không khẳng định help:describe luôn in đúng hai dòng này. Maven còn phải nội suy `${project.build.outputDirectory}` trong ngữ cảnh POM thật (đối với project JAR thông dụng, thường hướng tới `target/classes`).

**Default không nhất thiết là giá trị cuối cùng**. Nếu POM override output directory hoặc plugin configuration, giá trị thực tế khi goal chạy có thể khác.

### 5.5. User Property: tên đúng sau -D

Compiler Plugin goal `compile` công bố parameter `release` với user property `maven.compiler.release`. Vì vậy có thể gọi:

```bash
mvn -Dmaven.compiler.release=17 compile
```

**Không tự suy luận `-Drelease=17` cũng hoạt động**. Để cấu hình bằng CLI, dùng đúng tên **User Property** do plugin công bố. Một số parameters không có user property độc lập; khi đó bạn cần cấu hình trong POM/plugin phù hợp, không tự bịa cờ dòng lệnh.

### 5.6. Since, deprecated và plugin version

Nếu parameter có trường `Since`, kiểm tra version plugin bạn đang dùng đã hỗ trợ chưa. Nếu parameter được đánh dấu deprecated, đọc lời giải thích/thay thế. Trang tài liệu Compiler Plugin mới có thể mô tả thêm parameters không có ở bản 3.13.0; luôn **ghim version trong lệnh `help:describe`** và ưu tiên tài liệu khớp version.

Khi nâng plugin version, kiểm tra plugin requirements (Maven/JDK), các tham số bị đổi và compatibility trước khi dùng tính năng mới.

## 6. Yêu cầu thực thi của goal: đọc và hiểu đúng

Đây là phần trọng tâm thứ hai của đề bài, bên cạnh parameters.

### 6.1. Requires a Maven project

Nếu metadata cho biết `Requires a Maven project to be executed`, goal cần một POM/ngữ cảnh project phù hợp. `compiler:compile` có yêu cầu đó.

Đừng chạy `compiler:compile` ở thư mục rỗng rồi mong Maven tự đi tìm mọi file `.java` trên máy. Goal compiler còn cần source roots, output directories và thông tin project liên quan.

**Một số goal của Maven Help Plugin** có thể tra cứu metadata mà không cần project cụ thể, nhưng điều đó **không đồng nghĩa** goal mà nó đang mô tả cũng không cần project.

### 6.2. Requires dependency resolution

Goal `compiler:compile` có yêu cầu giải quyết project dependencies trong scope `compile` trước khi thực thi phần biên dịch. Nghĩa là Maven phải có những JAR phù hợp cho compile classpath, nếu project cần.

Hệ quả:
- repository không truy cập được hoặc dependency sai tọa độ có thể làm build thất bại trước khi thực sự biên dịch;
- mô tả “scope compile” không có nghĩa plugin trở thành dependency compile của ứng dụng;
- Maven plugin có **plugin classpath** riêng, còn ứng dụng có **project dependency graph** riêng;
- goal khác có thể yêu cầu scope test hoặc yêu cầu khác, không được mặc định dùng giống compiler goal.

`help:describe` giúp đọc yêu cầu resolution; để biết **những dependency cụ thể nào được chọn**, dùng `dependency:tree`.

### 6.3. Default lifecycle phase không chứng minh goal tự chạy trong mọi project

Metadata compiler goal có thể cho biết default phase là `compile`. Nhưng **một goal có default phase** và **một packaging lifecycle mapping gắn goal ấy** là hai khái niệm liên quan nhưng không giống nhau.

Với một project `packaging=jar` thông thường, `mvn compile` gọi compiler goal theo mapping. Với project `packaging=pom` hoặc custom packaging, mapping và executions có thể khác.

Vì vậy hãy dùng:
- `help:describe -Dcmd=compile` để xem thông tin phase trong context của project;
- `help:effective-pom` để xem plugin executions;
- Maven logs để biết chính xác goal nào đã chạy trong build.

### 6.4. Thread-safe là thông tin về goal, không phải chứng nhận toàn hệ thống

Maven Compiler Plugin goal `compile` được mô tả là thread-safe và hỗ trợ parallel builds. Điều đó giúp Maven quản lý reactor khi dùng `-T`, nhưng **không có nghĩa** các goal khác, custom scripts, annotation processors hoặc resource bên ngoài trong cùng build đều thread-safe.

Một goal không đánh dấu thread-safe có thể gây cảnh báo khi build parallel. Không nên bật `-T` chỉ vì riêng compiler goal có metadata tích cực. Phải xét toàn bộ lifecycle và dependency graph.

### 6.5. Aggregator không phải aggregator POM

Một plugin goal có thể được đánh dấu **aggregator**. Help Plugin `help:describe` được công bố là aggregator goal; goal đó có semantics ở mức tổng hợp reactor. Trong khi đó **aggregator POM** là POM có `<modules>`.

Đừng nhầm:
- `aggregator=true` ở plugin descriptor;
- `<packaging>pom</packaging>` và `<modules>` ở project;
- `requiresProject=true`;
- `threadSafe=true`.

Đây là các thuộc tính riêng. Một aggregator goal không có nghĩa nó sẽ biên dịch tất cả module giống `mvn compile`.

### 6.6. Metadata không bao quát mọi yêu cầu ngoại vi

`help:describe` không thể xác minh mọi tiền đề ngoài Maven:
- JDK/toolchain cần có phiên bản phù hợp;
- goal deploy có thể cần credentials/quyền repository;
- integration test có thể cần container/service/database;
- goal xử lý file có thể cần input path tồn tại;
- môi trường CI có thể thiếu variables hoặc quyền ghi.

**Đọc requirements là bước đầu, không thay thế chạy thử**. Với plugin đặc thù, luôn đọc tài liệu plugin version và kiểm tra môi trường thật.

## 7. -Dcmd giúp phân biệt phase, lifecycle và plugin goal

### 7.1. Mô tả phase `compile`

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dcmd=compile
```

Lệnh này yêu cầu mô tả phase `compile` trong context project/packaging. Nó có thể hiển thị lifecycle và goal được mapping; **nó không chạy compiler**.

### 7.2. Mô tả goal `compiler:compile`

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dcmd=compiler:compile" -Ddetail=true
```

Đây là cách hỏi một Maven goal qua dạng command. Khi muốn kiểm soát phiên bản Compiler Plugin rõ ràng hơn, dùng `-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0 -Dgoal=compile` như mục 3.

### 7.3. Mô tả lifecycle `clean`

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dcmd=clean
```

Maven có thể giải thích clean lifecycle với `pre-clean`, `clean` và `post-clean`. Lệnh trên **không xóa** `target`. Lệnh thực thi là:

```bash
mvn clean
```

Đó là hai hành động hoàn toàn khác nhau. Không nên nhầm việc dùng Help Plugin với việc chạy lifecycle chỉ vì cả hai chứa tên `clean`.

### 7.4. Tự đọc tham số của chính help:describe

`help:describe` là một goal, nên cũng có metadata của chính nó. Dùng:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:help -Ddetail=true -Dgoal=describe
```

Goal `help:help` (ở đây gọi bằng tọa độ đầy đủ) cung cấp tài liệu tham số cho các goal **trong Help Plugin**. Khi mục tiêu là xem Compiler Plugin, dùng `help:describe` với `-Dplugin=compiler`.

Một số plugin cũng có goal `plugin-prefix:help` riêng, nhưng không nên mặc định tất cả plugin hỗ trợ cùng loại help goal. `help:describe` là cách chung để tra cứu plugin descriptor.

## 8. Thực hành đầy đủ: Maven 3.9.x + Java 17

Ta tạo project đơn giản với một `pom.xml` và một Java class. Mục đích không chỉ là làm Hello World mà là thấy rõ sự khác nhau giữa **mô tả goal**, **chạy phase compile** và **chạy code đã biên dịch**.

### 8.1. Cấu trúc thư mục

```text
describe-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── describe/
                        └── App.java
```

Mở terminal ở thư mục `describe-lab`. Cần Maven 3.9.x và JDK 17+, kết nối repository khi phải tải plugin lần đầu.

### 8.2. Tệp `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>describe-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

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
```

Giải thích:
- `packaging=jar` chọn lifecycle mapping thông dụng.
- `maven.compiler.release=17` yêu cầu compile theo Java 17 khi JDK hỗ trợ.
- `maven-compiler-plugin:3.13.0` ghim version đúng với goal sẽ tra cứu.
- Không cần khai báo thư viện ngoài vì code sử dụng JDK.
- Mã POM này **không tự chạy** khi bạn gọi `help:describe`; nó là ngữ cảnh của các lệnh Maven.

### 8.3. Tệp `src/main/java/com/example/describe/App.java`

```java
package com.example.describe;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Hello, Maven help:describe!");
    }
}
```

Đây là một class Java 17 hoàn chỉnh có `main(String[] args)`. Path source khớp package và tên class. Sau khi biên dịch thành công, file bytecode thường nằm dưới `target/classes/com/example/describe/App.class`.

### 8.4. Bước 1 — xác định Maven và Java phiên bản nào đang chạy

```bash
mvn -version
```

Nếu Maven đang dùng JDK 11 mà POM đòi `release=17`, compiler có thể lỗi vì JDK không hỗ trợ target này, trừ khi có toolchain/compiler cấu hình riêng. **Đây là lỗi môi trường biên dịch, không phải lỗi `help:describe`.**

### 8.5. Bước 2 — mô tả Compiler Plugin, chưa biên dịch

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0" -Dgoal=compile -Ddetail=true
```

Hãy tìm thông tin dạng:

| Điều cần tìm | Ý nghĩa |
| --- | --- |
| `maven-compiler-plugin:3.13.0` | Chính xác plugin version đang mô tả |
| `compile` | Goal đang mô tả |
| Requires project | Có, goal cần Maven project |
| Requires dependency resolution | Scope `compile` |
| Default phase | `compile` |
| Thread-safe | Goal công bố hỗ trợ parallel execution |
| `release` | Parameter của compiler goal |
| `maven.compiler.release` | User property cho parameter `release` |
| `outputDirectory` | Nơi class output được ghi, thường từ project model |

Đây là **bảng diễn giải metadata kỳ vọng**, không phải bản chép nguyên văn log. Dạng hiển thị phụ thuộc Help Plugin và descriptor/version Compiler Plugin.

**Lưu ý:** dù lệnh mô tả thành công, nó **không sinh ra** `App.class`. Nếu thư mục `target/classes` đã có từ lần build cũ, cần phân biệt dữ liệu cũ với kết quả của thao tác hiện tại.

### 8.6. Bước 3 — so sánh phase và goal

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dcmd=compile
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dcmd=compiler:compile" -Ddetail=true
```

Lệnh đầu hỏi thông tin **phase compile**, lệnh sau hỏi **goal compiler:compile**. Cả hai đều là lệnh tra cứu; không thay thế `mvn compile`.

### 8.7. Bước 4 — thực sự biên dịch

```bash
mvn clean compile
```

Maven chạy clean lifecycle và default lifecycle đến `compile`; ở ví dụ này compiler biên dịch `App.java` và tạo `target/classes/com/example/describe/App.class` nếu build thành công.

### 8.8. Bước 5 — chạy Java và xem stdout chính xác

```bash
java -cp target/classes com.example.describe.App
```

Dòng **stdout chỉ của lệnh Java**:

```text
Hello, Maven help:describe!
```

Log `mvn clean compile` có thể khác nhau tùy Maven/JDK/cache và tình trạng repository. **Dòng trên không phải toàn bộ stdout của Maven**; nó là kết quả trực tiếp của `System.out.println` trong Java.

### 8.9. Bước 6 — dùng đúng tên user property

Metadata của `release` cung cấp user property `maven.compiler.release`. Có thể dùng:

```bash
mvn -Dmaven.compiler.release=17 clean compile
```

Ở POM trên, property vốn đã là 17 nên ví dụ này không tạo khác biệt có thể nhìn thấy; nó nhằm minh họa **cách dùng tên user property đúng**. Đừng dùng `-Drelease=17` chỉ vì parameter tên `release`.

Nếu đổi release thành 21 trên JDK 17, có thể gặp lỗi `release version 21 not supported`. Không xem đó là mâu thuẫn của Help Plugin: mô tả metadata không đảm bảo compiler/JDK đang có đủ khả năng.

## 9. Lưu mô tả vào file và xem effective configuration

### 9.1. Dùng -Doutput

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0" -Dgoal=compile -Ddetail=true -Doutput=compiler-describe.txt
```

`-Doutput` yêu cầu Help Plugin ghi mô tả ra file `compiler-describe.txt` bằng UTF-8. File đó là **tài liệu đầu ra của Help Plugin**, không phải source/build artifact của Compiler Plugin. Nếu plugin không in phần mô tả dài ra console khi có `-Doutput`, hãy mở file đã chỉ định.

### 9.2. Xem effective POM

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

`help:effective-pom` cho biết POM sau parent/profile/interpolation và cấu hình build phù hợp. Ở ví dụ, tìm `maven-compiler-plugin` version `3.13.0` và property `maven.compiler.release`.

So sánh:
- **`help:describe`:** goal hỗ trợ gì, các parameter/requirements nào tồn tại?
- **`help:effective-pom`:** project đã cấu hình/nhận version/plugin/values gì?
- **`mvn -X compile`:** Maven thực sự chọn plugin/execution configuration như thế nào? Log debug rất dài và có thể chứa thông tin hạ tầng, cần lọc trước khi chia sẻ.

### 9.3. Plugin version được mô tả khác với plugin version thực thi

Bạn có thể dùng `help:describe` để đọc Compiler Plugin 3.13.0 dù project thực tế đang chạy version khác. Vì thế:
1. Lấy version thực tế từ `help:effective-pom` hoặc Maven build log.
2. Truyền **đúng version đó** trong `-Dplugin=groupId:artifactId:version`.
3. Nếu có hướng dẫn dùng option mới, xác minh option đã tồn tại ở version đang chạy.

`mvn -version` chỉ cho biết Maven/JDK, không tự nói compiler plugin version.

## 10. Plugin execution trong POM khác metadata goal

Trong POM, plugin có thể được cấu hình ở cấp chung hoặc theo từng execution:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <executions>
        <execution>
            <id>extra-compile</id>
            <phase>compile</phase>
            <goals>
                <goal>compile</goal>
            </goals>
            <configuration>
                <showWarnings>true</showWarnings>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn minh họa cấu trúc execution**, không dán vào POM runnable ở mục 8. Với `packaging=jar` mặc định, compiler goal vốn đã được mapping vào phase compile; thêm một execution nữa có thể làm compilation được yêu cầu thêm lần nữa.

`help:describe` có thể cho biết parameter `showWarnings` thuộc goal nào và User Property nào, nhưng **không tự cho bạn biết mọi execution được merge thế nào trong project**. Phải xem `help:effective-pom` và log lifecycle nếu muốn hiểu số lần goal chạy.

### 10.1. Goal có thể có default phase mà vẫn chưa được bind tự động

Default phase trong descriptor là **metadata của goal**. Việc Maven chạy goal lúc nào còn liên quan packaging lifecycle mappings và những `<execution>` trong POM. Vì vậy khi chạy `mvn verify`, đừng đọc default phase của một plugin rồi khẳng định nó chắc chắn có mặt trong mọi project.

### 10.2. Các goal trong cùng một plugin có thể khác metadata

`compiler:compile` và `compiler:testCompile` đều là goal của Compiler Plugin nhưng xử lý source roots/dependencies và output khác nhau. Nếu cần config test compiler, hãy mô tả riêng:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0" -Dgoal=testCompile -Ddetail=true
```

Đừng lấy danh sách parameters của `compile` rồi giả định `testCompile` hoàn toàn tương đồng. Với những plugin có nhiều goals, luôn lưu **plugin GAV và goal cụ thể** trong tài liệu/issue.

## 11. Lỗi thường gặp khi dùng help:describe

| Triệu chứng | Cách kiểm tra và xử lý |
| --- | --- |
| `No plugin found for prefix 'compiler'` | Prefix resolution không tìm được plugin; thử GAV đầy đủ |
| `Plugin ... could not be resolved` | Kiểm tra GAV/version, repository, mirror, proxy, credentials, offline/cache |
| Mô tả quá ngắn | Thêm `-Dgoal=... -Ddetail=true` |
| Output quá dài | Chọn đúng goal bằng `-Dgoal=...`; tránh mô tả toàn bộ plugin |
| Chỉ truyền `-Dgoal=compile` | Cần plugin để biết goal compile thuộc plugin nào |
| Nhầm `-Dcmd=compile` và `-Dgoal=compile` | `cmd` mô tả phase/command; `goal` mô tả goal trong plugin đã chọn |
| Mô tả bản 3.13.0 nhưng build dùng bản khác | Xem effective POM, pluginManagement, parent và Maven log |
| `-Dmaven.compiler.release=17` vẫn lỗi target | Kiểm tra JDK/toolchains và plugin version đang chạy |
| `-Drelease=17` không tác động | Phải dùng đúng User Property, ví dụ `maven.compiler.release` |
| Required: Yes nhưng không truyền `-D` | Có thể parameter có default expression hoặc được inject từ model |
| Mô tả `outputDirectory` khác đường dẫn thấy ở build | Có thể project override outputDirectory hoặc plugin configuration |
| `help:describe` thành công nhưng chưa có class | Đúng, lệnh mô tả **không thực thi** `compiler:compile` |
| Gọi goal trực tiếp khác gọi phase | `mvn compiler:compile` không tương đương mọi bước của `mvn compile` |
| `-Doutput=...` không in mô tả trên terminal | Kết quả đang được ghi vào file |
| PowerShell truyền `-D...` gây lỗi parse | Thử bao trọn đối số như `"-Dplugin=..."` |
| Có thông tin thread-safe nhưng `-T` vẫn cảnh báo | Các plugin/goals khác trong build có thể không thread-safe |
| Plugin docs mới có parameter mà lệnh mô tả không thấy | Bạn đang dùng plugin version cũ; so khớp đúng version |
| Project nhiều module khó phân biệt context | Dùng `-f path/to/pom.xml` khi cần và xem mục aggregator/phase |
| `help:effective-pom` không in default parameter của plugin | Effective POM không phải bản sao plugin descriptor; cần cả hai lệnh |
| Lỗi mạng khi mô tả plugin dù không build | `help:describe` có thể phải tải Help Plugin hoặc metadata plugin được mô tả |

### 11.1. Vì sao help:describe có thể thất bại trong chế độ offline?

`help:describe` không chạy Compiler Plugin, nhưng nó vẫn cần **phân giải Help Plugin và thông tin plugin được mô tả**. Nếu các artifact cần thiết chưa có trong local repository, chạy offline `-o` có thể lỗi. Đây là vấn đề resolution/cache, không phải thiếu source Java.

Kiểm tra mạng, mirror/proxy/repository, plugin version và settings; nếu phải debug sâu, dùng `mvn -e` hoặc `-X` có chọn lọc. Không chia sẻ nguyên log có credentials, đường dẫn nội bộ hoặc token.

### 11.2. Đừng dựa vào một phần output để kết luận goal an toàn

Một goal metadata cho biết `threadSafe=true` không có nghĩa tất cả plugin trong reactor thread-safe. `Required: No` cũng không có nghĩa goal không cần JDK, file hoặc service. `Default phase=compile` không có nghĩa mọi project đóng gói `pom` sẽ compile code.

Luôn kết hợp:
1. Metadata goal từ `help:describe`.
2. Cấu hình project từ `help:effective-pom`.
3. Plugin docs đúng version.
4. Kết quả Maven thực thi và test đại diện.

## 12. Quy trình thực tế khi đọc một plugin goal chưa biết

1. **Ghi đúng plugin GAV và goal từ log lỗi hoặc POM.** Đừng chỉ dựa vào tên prefix.
2. **Xem plugin overview** bằng `help:describe -Dplugin=groupId:artifactId:version`.
3. **Xem goal chi tiết** bằng `-Dgoal=... -Ddetail=true`.
4. **Ghi các parameter quan trọng**: Name, Type, Required, Default, User Property, Since, deprecated nếu có.
5. **Ghi các execution requirements**: Requires Project, Requires Dependency Resolution, Default Phase, Thread-safe, Aggregator nếu được công bố.
6. **Đọc effective POM** của đúng module để tìm cấu hình và executions đã áp dụng.
7. **Thử một thay đổi nhỏ**, dùng CLI user property đúng hoặc plugin configuration được tài liệu hỗ trợ.
8. **Chạy lifecycle/goal thực tế**, kiểm tra class output, test reports và hành vi của ứng dụng.
9. **Ghi lại lý do và phiên bản** để đồng đội/CI có thể lặp lại kết quả.

Với plugin đặc thù yêu cầu database, Docker, network hoặc deploy credentials, thêm một bước kiểm tra các yêu cầu ngoại vi của plugin docs. Không dùng Help Plugin như công cụ xác minh trạng thái các service ấy.

## 13. Bài tập tự đánh giá

**Bài tập 1:** Lệnh nào tra cứu và lệnh nào thực thi?

```bash
mvn help:describe -Dplugin=compiler -Dgoal=compile -Ddetail=true
mvn compile
```

Đáp án: lệnh đầu **mô tả**, lệnh sau **thực thi lifecycle đến compile**.

**Bài tập 2:** Bạn thấy parameter `release` có User Property `maven.compiler.release`. Muốn đặt Java 17, nên dùng `-Drelease=17` hay `-Dmaven.compiler.release=17`? Đáp án: **`-Dmaven.compiler.release=17`**.

**Bài tập 3:** Parameter `outputDirectory` được đánh dấu required nhưng có default expression từ project. Bạn có bắt buộc nhập `-DoutputDirectory` mỗi lần? **Không**, Maven có thể tính giá trị từ model/config.

**Bài tập 4:** `-Dcmd=compile` hỏi thông tin gì? **Một phase**. `-Dcmd=compiler:compile` hỏi thông tin gì? **Một plugin goal**.

**Bài tập 5:** Goal compiler:compile yêu cầu dependency resolution scope compile. Điều đó có nghĩa Maven sẽ dùng toàn bộ các JAR tồn tại trong `~/.m2`? **Không**; chỉ những dependency được project phân giải cho scope phù hợp.

**Bài tập 6:** Một goal thread-safe có bảo đảm mọi custom script trong build an toàn khi chạy `mvn -T 4` không? **Không**.

**Bài tập 7:** Lệnh `help:describe` mô tả Compiler Plugin version 3.13.0 nhưng build log hiện 3.12.1. Kết quả mô tả có chắc phản ánh plugin đang thực thi không? **Không**; phải mô tả đúng version thực tế.

**Bài tập 8:** Chạy `-Dgoal=testCompile -Ddetail=true` cho cùng Compiler Plugin 3.13.0. So sánh source roots, dependency resolution và output với `compile`. Tại sao không nên sao chép config hai goal mà không kiểm tra?

## 14. Checklist trước khi thay plugin configuration

- [ ] Đã biết đúng **plugin groupId:artifactId:version** và goal.
- [ ] Đã gọi `help:describe` với `-Dgoal=... -Ddetail=true`.
- [ ] Đã phân biệt Name, Type, Required, Default, User Property và Since của parameter.
- [ ] Đã đọc Requires Project, dependency resolution, phase, thread-safe và aggregator nếu plugin công bố.
- [ ] Đã đối chiếu `help:effective-pom` trong đúng module.
- [ ] Đã dùng đúng tên `-Duser.property`, không đoán từ tên XML.
- [ ] Đã phân biệt **mô tả goal** với **thực thi goal hoặc lifecycle phase**.
- [ ] Đã kiểm tra Maven/JDK/toolchains và khả năng phân giải artifacts.
- [ ] Đã chạy build/test thực tế sau khi thay cấu hình.
- [ ] Đã lọc dữ liệu nhạy cảm trước khi chia sẻ logs hoặc output files.

**Ghi nhớ trọng tâm:** `help:describe` trả lời “**Goal này có những tham số, default và yêu cầu thực thi nào?**”. `help:effective-pom` trả lời “**Project đã cấu hình gì?**”. Còn chạy Maven và kiểm thử trả lời “**Build thực sự làm gì?**”. Biết dùng cả ba sẽ giúp bạn tránh đoán sai plugin parameters, lifecycle bindings và execution requirements.

### Tài liệu Apache Maven chính thức

- [Maven Help Plugin — help:describe và các tham số](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
- [Maven Help Plugin — Configuring Describe Goal](https://maven.apache.org/plugins/maven-help-plugin/examples/describe-configuration.html)
- [Maven Help Plugin — Usage](https://maven.apache.org/plugins/maven-help-plugin/usage.html)
- [Maven Compiler Plugin — compiler:compile goal](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
