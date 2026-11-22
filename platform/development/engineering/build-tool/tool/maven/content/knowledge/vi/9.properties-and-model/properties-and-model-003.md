# `project.basedir`, `build.directory` và đường dẫn đầu ra trong Maven

## 1. Mục tiêu

Trong Maven, **thư mục dự án**, **thư mục nguồn** và **thư mục chứa kết quả build** là các khái niệm khác nhau. Vì dự án đơn giản thường được build ngay tại nơi chứa `pom.xml`, người mới dễ tưởng mọi đường dẫn đều tính từ terminal, hoặc cho rằng `target/` là vị trí cố định không thể thay đổi.

Bài này giúp bạn:

- Hiểu `project.basedir`, `project.build.directory` và các đường dẫn đầu ra có liên quan.
- Tìm được vị trí `target/classes`, `target/test-classes`, JAR và tài nguyên đã đóng gói.
- Dùng `mvn help:evaluate` và `help:effective-pom` kiểm tra đường dẫn hiệu lực.
- Thay đổi `build.directory` hoặc `finalName` có chủ đích, biết những gì **không tự thay đổi**.
- Xử lý đường dẫn tương đối khi gọi `mvn -f`, chạy Java từ thư mục khác, dùng IDE/CI và dự án đa module.
- Tạo và chạy một ví dụ Java 17 có kết quả kiểm chứng rõ ràng.

Giả định có JDK 17+ và Maven tương thích. Trước khi thực hành, kiểm tra bằng `mvn --version`, `java -version` và `javac -version` từ đúng terminal sử dụng.

## 2. `project.basedir`: gốc của project Maven

`project.basedir` là thư mục gốc của **project Maven đang xét**, thông thường là thư mục chứa `pom.xml` tương ứng. Trong POM, bạn tham chiếu bằng biểu thức `${project.basedir}`.

Ví dụ:

~~~text
work/
└── path-demo/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
~~~

Với project `path-demo`, giá trị `project.basedir` là thư mục `work/path-demo` sau khi được Maven giải quyết thành đường dẫn thực tế. Nó có thể có dạng `/home/student/work/path-demo` trên Linux/macOS hoặc `C:\work\path-demo` trên Windows; không nên hard-code đường dẫn của một máy vào POM dùng chung.

Ví dụ một **mảnh cấu hình** trong POM:

~~~xml
<properties>
    <input.file>${project.basedir}/data/input.txt</input.file>
</properties>
~~~

Đây chỉ là khai báo property tên `input.file`; nó **không tự tạo hoặc mở** tệp `data/input.txt`. Một plugin hoặc chương trình phải được cấu hình sử dụng property thì tệp mới được truy cập.

### `basedir` không đồng nghĩa với working directory

| Khái niệm | Được quyết định bởi | Tình huống |
| --- | --- | --- |
| `project.basedir` | POM của project Maven | Gốc cho các đường dẫn dự án. |
| Thư mục hiện hành của shell | Vị trí terminal khi gọi lệnh | Dùng để tìm tệp theo đường dẫn tương đối của shell. |
| `System.getProperty("user.dir")` | Working directory của JVM đang chạy | Có thể là nơi chạy ứng dụng đã đóng gói, không phải thư mục của POM. |
| Thư mục gốc Git/repository | Cấu trúc repository | Có thể chứa nhiều project hoặc module Maven. |

Nếu đang đứng tại `work/` và gọi:

~~~bash
mvn -f path-demo/pom.xml validate
~~~

Maven chọn POM trong `work/path-demo`. `project.basedir` của project **vẫn là thư mục chứa POM**, không biến thành `work/` chỉ vì terminal đang đứng ở đó.

Để tự chứng minh:

~~~bash
mvn -f path-demo/pom.xml help:evaluate -Dexpression=project.basedir -q -DforceStdout
~~~

Giá trị in ra phụ thuộc máy; hãy kiểm tra phần cuối của đường dẫn trỏ về `path-demo`. Đường dẫn có khoảng trắng nên được đặt trong ngoặc kép, chẳng hạn `-f "my projects/path-demo/pom.xml"`.

## 3. `project.build.directory`: gốc của kết quả build

Trong Maven 3.x, đường dẫn build mặc định thường tương đương:

~~~text
${project.basedir}/target
~~~

Thuộc tính để xem là **`project.build.directory`**; còn trong `pom.xml`, bạn cấu hình nó bằng thẻ `<build><directory>...</directory></build>`. Không cần tự khai báo nếu muốn giữ mặc định.

Một dự án đã chạy `mvn package` có thể có:

~~~text
path-demo/
├── pom.xml
├── src/main/java/...
├── src/main/resources/...
└── target/
    ├── classes/
    ├── test-classes/
    └── path-demo-1.0-SNAPSHOT.jar
~~~

Cây trên giản lược: không phải mọi thư mục đều xuất hiện trong một dự án không có test; Maven/plugin còn có thể sinh metadata và báo cáo khác.

`target/` là **đầu ra sinh ra được**, không phải nơi lưu bản gốc mã nguồn. `mvn clean` thông thường xóa output theo cấu hình Maven Clean Plugin. Không đặt file duy nhất, tài liệu không thể tái tạo hoặc dữ liệu người dùng trong thư mục build.

### Phân biệt các trường trong model

| Thuộc tính | Giá trị mặc định thường gặp | Mục đích |
| --- | --- | --- |
| `project.basedir` | Thư mục chứa POM | Mốc gốc của project. |
| `project.build.sourceDirectory` | `src/main/java` | Nguồn Java chính. |
| `project.build.testSourceDirectory` | `src/test/java` | Nguồn Java cho test. |
| `project.build.resources` | Danh sách tài nguyên, mặc định có `src/main/resources` | Khai báo tài nguyên của ứng dụng. |
| `project.build.testResources` | Danh sách tài nguyên, mặc định có `src/test/resources` | Khai báo tài nguyên test. |
| `project.build.directory` | `target` | Thư mục build output gốc. |
| `project.build.outputDirectory` | `target/classes` | Bytecode và resource chính đã xử lý. |
| `project.build.testOutputDirectory` | `target/test-classes` | Bytecode và resource test. |
| `project.build.finalName` | `artifactId-version` | Tên cơ sở của artifact build. |
| `project.reporting.outputDirectory` | `target/site` | Đầu ra site/reporting thường dùng. |

Các giá trị trong bảng chỉ là **mặc định phổ biến**: parent POM, profile và plugin có thể thay đổi chúng. `resources` và `testResources` là tập hợp resource descriptors, không chỉ một chuỗi đường dẫn. Mỗi plugin cũng có thể có output parameter riêng, vì thế không suy luận mọi file do mọi plugin tạo đều nằm dưới một thư mục duy nhất.

### Từ nguồn tới kết quả

~~~text
src/main/java/com/example/App.java
       │
       │ compiler:compile
       ▼
target/classes/com/example/App.class
       │
       │ jar:jar với packaging=jar
       ▼
target/path-demo-1.0-SNAPSHOT.jar

src/main/resources/messages/hello.txt
       │
       │ resources:resources
       ▼
target/classes/messages/hello.txt
       │
       │ đóng gói vào JAR
       ▼
Entry trong JAR: messages/hello.txt
~~~

**Maven không biên dịch ở ngay nơi chứa mã nguồn.** Các goal biên dịch và xử lý tài nguyên viết kết quả vào output directory; goal đóng gói dùng những kết quả đó để tạo JAR. Khi đổi nơi xuất kết quả, thư mục nguồn chưa chắc thay đổi.

## 4. `finalName` và tên artifact khác `build.directory` như thế nào?

Với tọa độ:

~~~xml
<groupId>org.example</groupId>
<artifactId>path-demo</artifactId>
<version>1.0-SNAPSHOT</version>
<packaging>jar</packaging>
~~~

JAR được tạo trong thư mục output mặc định thường có tên:

~~~text
target/path-demo-1.0-SNAPSHOT.jar
~~~

Maven thường lấy phần tên cơ sở từ `project.build.finalName`, mặc định là `${project.artifactId}-${project.version}`. Đổi `<finalName>demo-app</finalName>` trong `<build>` có thể khiến file JAR thành `target/demo-app.jar`, **nhưng tọa độ Maven vẫn là `org.example:path-demo:1.0-SNAPSHOT`**.

Tên tệp tại `target/` không quyết định cách artifact được đặt tên trong repository cục bộ hoặc remote Maven repository. Khi `mvn install` hoặc publish, Maven dùng tọa độ artifact và quy tắc lưu trữ của repository. Không nhầm `finalName` với `artifactId`, và không nhầm nó với đường dẫn thư mục.

## 5. Thực hành đầy đủ: Java 17 với đường dẫn mặc định

Ta tạo project `path-demo` với một lớp Java và một tài nguyên classpath. Cây thư mục cần có:

~~~text
path-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── App.java
        └── resources/
            └── messages/
                └── hello.txt
~~~

**Bash trên Linux/macOS:**

~~~bash
mkdir -p path-demo/src/main/java/com/example
mkdir -p path-demo/src/main/resources/messages
cd path-demo
~~~

**PowerShell trên Windows:**

~~~powershell
New-Item -ItemType Directory -Force -Path "path-demo\src\main\java\com\example" | Out-Null
New-Item -ItemType Directory -Force -Path "path-demo\src\main\resources\messages" | Out-Null
Set-Location path-demo
~~~

Các lệnh trên chỉ tạo thư mục. Hãy tạo nội dung ba file bên dưới bằng một trình soạn thảo UTF-8.

### 5.1. Tệp `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>path-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ở POM này, `directory`, `outputDirectory`, `sourceDirectory` và `finalName` **không được khai báo**. Maven sẽ sử dụng cấu hình nền tương ứng. Ta chỉ chốt các thông số cần thiết cho Java 17 và hai plugin trọng tâm của ví dụ. Mặc định `jar` của packaging có thể được suy ra ngay cả khi bỏ thẻ `<packaging>jar</packaging>`, nhưng viết rõ để dễ học.

### 5.2. Tệp Java `src/main/java/com/example/App.java`

~~~java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        try (InputStream input =
                     App.class.getResourceAsStream("/messages/hello.txt")) {
            if (input == null) {
                throw new IllegalStateException("Missing classpath resource");
            }
            String message =
                    new String(input.readAllBytes(), StandardCharsets.UTF_8).strip();
            System.out.println(message);
        }
    }
}
~~~

Đây là chương trình Java 17 hoàn chỉnh, không dùng dependency ngoài JDK. Nó cố ý đọc resource bằng **classpath**, vì khi chạy từ JAR tài nguyên không còn là file trong `src/main/resources` trên máy triển khai.

### 5.3. Tệp `src/main/resources/messages/hello.txt`

~~~text
Maven output paths are clear!
~~~

Mẫu văn bản chỉ có một dòng. Ký tự newline cuối file (nếu có) được loại bỏ bởi `String.strip()` trong ví dụ.

### 5.4. Build và chạy từ output mặc định

Đứng trong `path-demo/`, chạy:

~~~bash
mvn clean package
~~~

Khi Maven tải được các plugin cần thiết và biên dịch thành công, log kết thúc bằng `BUILD SUCCESS`. Các file quan trọng sẽ xuất hiện:

~~~text
target/
├── classes/
│   ├── com/example/App.class
│   └── messages/hello.txt
└── path-demo-1.0-SNAPSHOT.jar
~~~

Đây không phải cây liệt kê đầy đủ mọi file phát sinh. Kiểm tra classpath bằng lệnh:

~~~bash
java -cp target/classes com.example.App
~~~

**Stdout chính xác:**

~~~text
Maven output paths are clear!
~~~

Chạy từ JAR vừa tạo:

~~~bash
java -cp target/path-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout chính xác cũng là:**

~~~text
Maven output paths are clear!
~~~

Dùng `-cp` thay vì `java -jar`, vì ví dụ chưa cấu hình `Main-Class` trong manifest. Chương trình chạy được từ cả `target/classes` lẫn JAR chứng minh resource đã được copy và đóng gói đúng.

Liệt kê entry trong JAR nếu cần:

~~~bash
jar tf target/path-demo-1.0-SNAPSHOT.jar
~~~

Trong kết quả, tìm `com/example/App.class` và `messages/hello.txt`. Entry JAR không có tiền tố `src/main/resources`.

## 6. Kiểm tra đường dẫn bằng `help:evaluate` và `effective-pom`

Maven Help Plugin giúp xem **giá trị hiệu lực**, không phải tự đoán bằng cách nhìn tên thư mục. Trong `path-demo/`, chạy độc lập các lệnh:

~~~bash
mvn help:evaluate -Dexpression=project.basedir -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.directory -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.outputDirectory -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.testOutputDirectory -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.finalName -q -DforceStdout
~~~

Giá trị khái niệm cần quan sát:

~~~text
<project-directory>
<project-directory>/target
<project-directory>/target/classes
<project-directory>/target/test-classes
path-demo-1.0-SNAPSHOT
~~~

Năm dòng này là **minh họa từ năm lời gọi riêng**, không phải một transcript thống nhất. Dấu phân cách và đường dẫn tuyệt đối trên máy bạn có thể khác.

Để thấy model POM đã kết hợp cấu hình nguồn, Super POM, parent và profile:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Tìm các thẻ `<directory>`, `<outputDirectory>`, `<testOutputDirectory>`, `<sourceDirectory>`, `<finalName>` trong file sinh ra. Nếu Help Plugin hỗ trợ, thử:

~~~bash
mvn help:effective-pom -Dverbose=true -Doutput=effective-pom-verbose.xml
~~~

Chế độ verbose có thể thêm thông tin nguồn gốc khai báo. `effective-pom.xml` là **tệp báo cáo**, không phải nơi sửa cấu hình dự án. Tùy Maven/Help Plugin, có thể cần tải plugin qua mạng trong lần chạy đầu.

Không quên: một plugin có thể có tham số output riêng. Nếu model nói một nơi nhưng file xuất hiện nơi khác, cần xem **log plugin** và cấu hình plugin tương ứng.

## 7. Đổi `build.directory` thành một thư mục khác

Giả sử bạn muốn kết quả build nằm trong `build-output/`. **Thay trọn thẻ `<build>`** trong POM của mục 5 bằng:

~~~xml
<build>
    <directory>build-output</directory>
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
~~~

Đây là **mảnh cấu hình thay thế**, không phải một POM đầy đủ. Không tạo hai thẻ `<build>` cùng cấp trong một project.

Chạy:

~~~bash
mvn clean package
mvn help:evaluate -Dexpression=project.build.directory -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.outputDirectory -q -DforceStdout
~~~

Với project mẫu, đầu ra quan trọng sẽ chuyển thành:

~~~text
build-output/
├── classes/
│   ├── com/example/App.class
│   └── messages/hello.txt
└── path-demo-1.0-SNAPSHOT.jar
~~~

Chạy JAR theo đường dẫn mới:

~~~bash
java -cp build-output/path-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout chính xác:**

~~~text
Maven output paths are clear!
~~~

### Điều gì thay đổi, điều gì giữ nguyên?

- `project.build.directory` đổi từ `target` sang `build-output`.
- `project.build.outputDirectory` mặc định dựa trên build directory nên thường đổi thành `build-output/classes`.
- Đầu ra resource chính đi cùng output classes theo cấu hình Maven Resources Plugin mặc định.
- `src/main/java`, `src/main/resources` và `project.basedir` **không tự chuyển vị trí**.
- Tọa độ `org.example:path-demo:1.0-SNAPSHOT` không đổi.
- `target/` từ lần build trước **có thể vẫn tồn tại**. `mvn clean` sau khi cấu hình đổi không tự đi quét các thư mục output cũ từng dùng. Đừng chạy nhầm JAR cũ rồi cho rằng cấu hình mới không có tác dụng.

Khi cần dọn file cũ, hãy xác minh nguồn gốc và phạm vi thư mục trước khi xóa thủ công.

## 8. Đổi riêng `outputDirectory` và `finalName`

Thay `build.directory` là thay gốc output. Maven cũng cho phép điều chỉnh các thành phần riêng, nhưng cần hiểu hậu quả.

### 8.1. `outputDirectory` — nơi chứa class/resource chính

Đây là mảnh XML **đặt bên trong `<build>`**:

~~~xml
<outputDirectory>${project.build.directory}/bytecode</outputDirectory>
~~~

Nếu build directory vẫn mặc định, đường dẫn output class sẽ thường thành `target/bytecode`. Các plugin biên dịch/đóng gói tuân theo các trường model phù hợp, trừ khi bị cấu hình riêng. Thay `outputDirectory` **không tự đổi** nguồn `src/main/java`, test output directory hay tên JAR.

Với dự án có plugin đặc thù, hãy kiểm tra tham số output của chính plugin, tránh giả định mọi file cùng chuyển nơi.

### 8.2. `finalName` — tên file sản phẩm đóng gói

Đây cũng là mảnh cấu hình **bên trong `<build>`**:

~~~xml
<finalName>demo-app</finalName>
~~~

Với packaging `jar` và build directory mặc định, JAR chính thường có tên `target/demo-app.jar`. Nếu build directory đã đổi sang `build-output`, file tương ứng thường ở `build-output/demo-app.jar`. Tuy nhiên **`artifactId` và `version` vẫn giữ nguyên**.

Không dùng `finalName` như đường dẫn tuyệt đối đến JAR. Nó là **tên cơ sở**; plugin đóng gói quyết định phần mở rộng, classifier và đích output theo cấu hình.

### 8.3. Xem cấu hình nào bị ảnh hưởng

~~~text
project.basedir                   = <project-directory>
project.build.directory           = <project-directory>/target
project.build.outputDirectory     = <project-directory>/target/classes
project.build.testOutputDirectory = <project-directory>/target/test-classes
project.build.finalName           = path-demo-1.0-SNAPSHOT
~~~

Một mảnh `<directory>build-output</directory>` thường kéo theo các đường dẫn phụ thuộc `project.build.directory`. Một mảnh `<outputDirectory>...</outputDirectory>` tác động trực tiếp đến class/resource output, không phải toàn bộ hệ thống. Một mảnh `<finalName>...</finalName>` chủ yếu thay tên artifact.

## 9. Đường dẫn tương đối, tuyệt đối và tính di động

### 9.1. Sử dụng đường dẫn tương đối có mốc rõ ràng

Trong `<build>`, cấu hình:

~~~xml
<directory>build-output</directory>
~~~

thường giúp mỗi checkout dùng thư mục output riêng bên dưới basedir. Cách khai báo có mốc rõ là:

~~~xml
<directory>${project.basedir}/build-output</directory>
~~~

Cả hai mô tả ý định đặt output trong project khi được Maven giải quyết thông thường. Tránh viết đường dẫn tuyệt đối phụ thuộc một máy như `C:\Users\someone\Desktop\project\target` hoặc `/home/someone/project/target` vào POM dùng chung, trừ khi có yêu cầu môi trường rõ ràng.

Cú pháp `${project.basedir}` là **Maven expression trong POM**, không phải phép mở rộng biến shell. Để biểu diễn dấu `&` trong nội dung XML, phải escape thành `&amp;`.

### 9.2. Với `mvn -f`, Java launcher vẫn có working directory riêng

Nếu ở thư mục cha của project:

~~~bash
mvn -f path-demo/pom.xml package
~~~

Maven build project `path-demo` vào output đã cấu hình của **project**. Nhưng sau đó:

~~~bash
java -cp target/path-demo-1.0-SNAPSHOT.jar com.example.App
~~~

có thể lỗi vì Java launcher giải quyết `target/...` theo **working directory của JVM tại thời điểm chạy**. Khi vẫn đứng ở thư mục cha, dùng:

~~~bash
java -cp path-demo/target/path-demo-1.0-SNAPSHOT.jar com.example.App
~~~

Nếu project đã đổi build directory thì thay `target` bằng `build-output`. Nguyên tắc: `-f` chọn POM cho Maven, nhưng **không làm Java launcher tự hiểu basedir Maven**.

### 9.3. Trong dự án nhiều module

Một repository có thể như sau:

~~~text
repo/
├── pom.xml
└── modules/
    ├── api/
    │   └── pom.xml
    └── service/
        └── pom.xml
~~~

Nếu mỗi module dùng default output và reactor được cấu hình đúng, các thư mục thường tách biệt:

~~~text
repo/target/
repo/modules/api/target/
repo/modules/service/target/
~~~

`project.basedir` trong mỗi module tương ứng với thư mục của chính module. Nó **không luôn là Git root, không luôn là basedir của aggregator**. Parent/aggregator `pom` packaging có thể không tạo JAR, trong khi module `jar` tạo artifact riêng.

Ví dụ từ `repo/`:

~~~bash
mvn -pl modules/api -am package
~~~

Lệnh chọn module và các project cần thiết trong reactor theo cơ chế Maven; nó **không đổi basedir của module `api`** thành dự án gốc. Tránh ép nhiều module ghi cùng một thư mục output tuyệt đối vì có nguy cơ đè `classes`, report và plugin metadata của nhau, nhất là khi build song song.

## 10. `target` khác `~/.m2/repository`

Đây là nhầm lẫn phổ biến khi học Maven.

| Thư mục | Vai trò |
| --- | --- |
| `target/` hoặc `build-output/` | Kết quả build ngay trong workspace project. |
| `~/.m2/repository/` | Cache và Maven local repository, nơi dependency được lưu/cài; vị trí có thể tùy cấu hình. |
| Maven remote repository | Máy chủ tải dependency hoặc đích phát hành artifact theo cấu hình riêng. |

`mvn package` tạo artifact trong build output directory; `mvn install` còn đưa artifact/POM vào repository Maven cục bộ theo tọa độ dự án. Ví dụ một kho local có thể chứa:

~~~text
~/.m2/repository/
└── org/
    └── example/
        └── path-demo/
            └── 1.0-SNAPSHOT/
                ├── path-demo-1.0-SNAPSHOT.jar
                └── path-demo-1.0-SNAPSHOT.pom
~~~

Cấu trúc minh họa bỏ qua file metadata phụ. `mvn clean` **không xóa kho repository cục bộ** và đổi `build.directory` cũng không làm kho này đổi vị trí. Nếu thay vị trí local repository qua Maven settings hoặc `maven.repo.local`, đó là một cấu hình khác.

## 11. Debug khi đường dẫn đầu ra không như mong đợi

Làm theo thứ tự để tránh sửa nhầm:

1. **Kiểm tra lệnh đang chạy ở đâu:** xem terminal current directory (Bash: `pwd`; PowerShell: `Get-Location`) và có dùng `-f` không.
2. **Xác định Maven/JDK:** chạy `mvn --version`, lưu ý Maven Wrapper/IDE/CI có thể chọn bản khác.
3. **Hỏi model hiệu lực:** `help:evaluate` cho `project.basedir`, `project.build.directory`, `project.build.outputDirectory` và `project.build.finalName`.
4. **Xem POM hợp nhất:** `help:effective-pom`, parent, profile, `pluginManagement` và cấu hình plugin cụ thể.
5. **Kiểm tra phase đã yêu cầu:** `mvn compile` biên dịch nhưng chưa bắt buộc tạo JAR; `mvn package` mới tới pha đóng gói.
6. **Đọc log plugin:** goal thực tế có thể có `outputDirectory` hoặc tham số riêng.
7. **Đối chiếu file thật:** kiểm tra vị trí và tên JAR mới, tránh dùng artifact cũ còn sót từ cấu hình trước.

Nếu cần log chi tiết:

~~~bash
mvn -X package
~~~

`-X` xuất thông tin debug, có thể tiết lộ đường dẫn, biến môi trường và cấu hình nhạy cảm. Chỉ chia sẻ phần log đã rà soát.

### Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không thấy `target/` sau `mvn package` | `build.directory` đã được override hoặc build chưa thành công. | Hỏi `project.build.directory` và xem log. |
| `ClassNotFoundException` sau khi build thành công | `java -cp` trỏ vào thư mục/JAR sai hoặc gọi sai tên class đầy đủ. | Kiểm tra `outputDirectory`, basedir và `com.example.App`. |
| Dùng `mvn -f` được nhưng `java -cp target/...` lỗi | CWD của Java khác basedir của POM. | Điều chỉnh classpath theo working directory của Java. |
| Không có JAR sau `mvn compile` | Chưa chạy phase `package`. | Chạy `mvn package`. |
| Đổi `finalName` nhưng tọa độ Maven vẫn cũ | `finalName` chỉ đổi tên cơ sở của đầu ra build. | Đổi GAV riêng nếu thực sự muốn đổi định danh artifact. |
| Thấy cả `target` và `build-output` | Thư mục cũ chưa được dọn sau khi đổi directory. | Dùng output hiện tại; chỉ xóa thư mục cũ sau khi xác nhận an toàn. |
| Test report nằm khác chỗ dự đoán | Plugin test/report có output parameter riêng. | Xem plugin config và log goal tạo báo cáo. |
| Resource có trong source nhưng không nằm trong JAR | Chưa xử lý resources, bị excludes loại hoặc plugin tùy chỉnh. | Kiểm tra `target/classes`, `jar tf` và cấu hình resource. |
| Các module ghi đè file nhau | Nhiều module được gán chung output path. | Tách output theo từng module. |
| `mvn clean` không dọn một thư mục | Clean áp dụng vào output hiện tại và cấu hình plugin. | Xem model và Maven Clean Plugin trước khi sửa. |
| IDE build được nhưng CLI khác | Khác Maven/JDK, working directory, profile hoặc settings. | So sánh invocation/effective POM giữa các môi trường. |

## 12. Bài tập thực hành và tiêu chí đạt

Thực hiện tuần tự:

1. Tạo project `path-demo` và ba file từ mục 5.
2. Kiểm tra `mvn --version` rồi chạy `mvn clean package`; ghi nhận output thật trong `target/`.
3. Chạy `java -cp target/path-demo-1.0-SNAPSHOT.jar com.example.App`, xác nhận đúng một dòng `Maven output paths are clear!`.
4. Dùng `help:evaluate` để xác định `project.basedir`, `project.build.directory`, `project.build.outputDirectory` và `project.build.finalName`.
5. Đổi `<directory>` thành `build-output` theo mục 7; build và chạy bằng đường dẫn JAR mới.
6. Từ thư mục cha, chạy `mvn -f path-demo/pom.xml help:evaluate -Dexpression=project.basedir -q -DforceStdout`; xác nhận basedir vẫn trỏ tới `path-demo`.
7. Chạy Java từ thư mục cha bằng classpath có tiền tố `path-demo/build-output/`.
8. Đặt `<finalName>demo-app</finalName>` vào `<build>` và quan sát tên JAR thay đổi trong khi `groupId:artifactId:version` không đổi.
9. Nêu hai lý do vì sao trong reactor multi-module không nên cho nhiều module dùng chung output directory tuyệt đối.

**Tự kiểm tra:** `project.basedir` khác `user.dir` ra sao? `build.directory` có đồng nghĩa `outputDirectory` không? Vì sao `mvn clean` không xóa `~/.m2/repository`? Thay `finalName` có đổi tọa độ artifact không? Vì sao Maven `-f` build thành công nhưng Java launcher có thể không tìm được class?

### Ghi nhớ

**`project.basedir` xác định gốc project; `project.build.directory` xác định gốc đầu ra; `project.build.outputDirectory` xác định nơi chứa bytecode/resource chính; `project.build.finalName` xác định tên cơ sở của artifact đóng gói.** Maven giải quyết cấu hình theo POM hiệu lực và plugin, còn JVM cần classpath phù hợp với thư mục chạy hiện tại.

Khi gặp đường dẫn bất ngờ, hãy **hỏi Maven về giá trị hiệu lực, kiểm tra plugin tạo file rồi đối chiếu artifact thật**, thay vì đoán theo một thư mục `target` cố định.

## Tài liệu chính thức

- Maven POM Reference: https://maven.apache.org/pom.html
- Maven Introduction to the POM: https://maven.apache.org/guides/introduction/introduction-to-the-pom.html
- Maven Help Plugin — `help:evaluate`: https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html
- Maven Help Plugin — `help:effective-pom`: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
