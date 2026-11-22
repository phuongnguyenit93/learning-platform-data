# `src/main/resources` và tài nguyên của ứng dụng trong Maven

## 1. `src/main/resources` dùng để làm gì?

Trong một dự án Maven Java, mã nguồn Java của ứng dụng thường nằm ở `src/main/java`, còn **tài nguyên cần được đưa vào classpath lúc chạy** được đặt trong `src/main/resources`. Tài nguyên có thể là tệp `.properties`, mẫu văn bản, JSON, XML, SQL, thông báo theo ngôn ngữ, chứng chỉ công khai hoặc hình ảnh nhỏ mà ứng dụng cần đọc.

Maven dùng quy ước thư mục để xử lý chúng trong quá trình build: đối với dự án JAR thông thường, các tệp trong `src/main/resources` được sao chép vào **`target/classes`**, giữ nguyên đường dẫn tương đối. Khi đóng gói với pha `package`, chúng thường trở thành **các entry trong JAR**, bên cạnh bytecode Java. Nhờ đó, ứng dụng có thể đọc tài nguyên qua **classpath** mà không phụ thuộc vào thư mục làm việc hiện tại.

Có ba ý quan trọng cần phân biệt từ đầu:

- `src/main/resources` là **vị trí của nguồn tài nguyên trong dự án**, không phải một đường dẫn bắt buộc tồn tại khi triển khai JAR.
- `target/classes` là **đầu ra build** chứa các lớp `.class` và tài nguyên đã được xử lý/sao chép. Không nên sửa thủ công các tệp trong đây vì build sau có thể ghi đè.
- Classpath là **cơ chế tìm lớp và tài nguyên** của JVM. Nó có thể chỉ tới một thư mục như `target/classes` hoặc tới một tệp JAR; tài nguyên classpath không nhất thiết là một `java.io.File` thông thường.

Bài này tạo một dự án Java 17 chạy được, đọc cấu hình `.properties` và một mẫu thông báo UTF-8. Sau đó ta quan sát đường đi của tài nguyên qua build, JAR và quá trình chạy chương trình.

## 2. Cây thư mục ví dụ

Tạo dự án Maven `resources-demo`:

~~~text
resources-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── App.java
        └── resources/
            ├── config/
            │   └── app.properties
            └── templates/
                └── greeting.txt
~~~

Ở đây:

| Đường dẫn | Vai trò |
| --- | --- |
| `pom.xml` | Khai báo tọa độ dự án, Java release và cấu hình Maven. |
| `src/main/java/com/example/App.java` | Lớp Java đọc và sử dụng các tài nguyên. |
| `src/main/resources/config/app.properties` | Các cặp khóa–giá trị cấu hình của ứng dụng. |
| `src/main/resources/templates/greeting.txt` | Mẫu thông báo văn bản UTF-8. |
| `target/classes/config/app.properties` | Bản sao resource xuất hiện sau khi Maven xử lý resources. |
| `target/classes/templates/greeting.txt` | Mẫu thông báo được copy sau build. |

Thư mục con `config/` và `templates/` không có ý nghĩa đặc biệt với Maven; ta chọn chúng để tổ chức nội dung dễ hiểu. Đường dẫn **tương đối tính từ `src/main/resources`** sẽ trở thành đường dẫn dùng để tra cứu tài nguyên trên classpath.

Ví dụ, tệp ở `src/main/resources/config/app.properties` có tên tài nguyên classpath là **`config/app.properties`**. Không đưa tiền tố `src/main/resources` vào tên tài nguyên khi đọc bằng ClassLoader.

Có thể tạo thư mục bằng shell Bash trên Linux/macOS:

~~~bash
mkdir -p resources-demo/src/main/java/com/example
mkdir -p resources-demo/src/main/resources/config
mkdir -p resources-demo/src/main/resources/templates
cd resources-demo
~~~

Hoặc dùng Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path "resources-demo\src\main\java\com\example" | Out-Null
New-Item -ItemType Directory -Force -Path "resources-demo\src\main\resources\config" | Out-Null
New-Item -ItemType Directory -Force -Path "resources-demo\src\main\resources\templates" | Out-Null
Set-Location resources-demo
~~~

Sau đó tạo các tệp bên dưới bằng trình soạn thảo và lưu bằng UTF-8. Các lệnh tạo thư mục không tự tạo nội dung các tệp.

## 3. Tạo `pom.xml` cho dự án Java 17

Tại thư mục gốc `resources-demo`, tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>resources-demo</artifactId>
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
        </plugins>
    </build>
</project>
~~~

POM này cố ý **không khai báo `<resources>`**. Maven đã có quy ước mặc định cho `src/main/resources`, nên ví dụ đơn giản không cần cấu hình thêm. `maven.compiler.release` đặt đích Java 17; thuộc tính `project.build.sourceEncoding` giúp các plugin có hỗ trợ xác định charset của mã nguồn/tài nguyên văn bản. Phiên bản Maven Compiler Plugin được khai báo rõ để việc biên dịch Java 17 không phụ thuộc vào phiên bản plugin compiler do Maven mặc định chọn.

Tệp JAR dự kiến sau `mvn package` là `target/resources-demo-1.0-SNAPSHOT.jar`. Vì ví dụ chưa cấu hình manifest `Main-Class`, ta sẽ chạy bằng `java -cp`, không dựa vào `java -jar`.

## 4. Tạo tài nguyên cấu hình và mẫu thông báo

Tệp **`src/main/resources/config/app.properties`** có nội dung:

~~~properties
app.name=Demo tài nguyên Maven
~~~

Tệp **`src/main/resources/templates/greeting.txt`** có nội dung:

~~~text
Xin chào, {name}!
~~~

Các tệp này cần được lưu bằng **UTF-8** để dấu tiếng Việt giữ nguyên. Trong mẫu trên, `{name}` chỉ là dấu thay thế do mã Java của chúng ta tự xử lý; Maven không tự suy diễn hay thay thế nội dung đó.

Tệp `.properties` dùng cú pháp cơ bản `key=value`. Có thể lưu nhiều cặp cấu hình:

~~~properties
app.name=Demo tài nguyên Maven
app.mode=local
~~~

Nhưng chương trình bên dưới chỉ cần `app.name`. Việc đặt tệp này dưới `src/main/resources` không khiến nó tự trở thành biến môi trường hay tự được Java nạp: **chương trình phải chủ động yêu cầu đọc**.

## 5. Viết Java đọc tài nguyên từ classpath

Tạo tệp **`src/main/java/com/example/App.java`**:

~~~java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        Properties config = new Properties();

        try (InputStream input =
                     App.class.getResourceAsStream("/config/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Không tìm thấy config/app.properties trên classpath");
            }
            config.load(new InputStreamReader(input, StandardCharsets.UTF_8));
        }

        String template;
        try (InputStream input = App.class.getClassLoader()
                .getResourceAsStream("templates/greeting.txt")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Không tìm thấy templates/greeting.txt trên classpath");
            }
            template = new String(input.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }

        System.out.println("Ứng dụng: " + config.getProperty("app.name"));
        System.out.println(template.replace("{name}", "Maven"));
    }
}
~~~

Đây là **một chương trình Java 17 hoàn chỉnh**: không dùng thư viện ngoài JDK, không cần framework, không truy cập file bằng đường dẫn tuyệt đối của máy. Hai kiểu đọc tài nguyên cùng được dùng để giải thích API:

- `App.class.getResourceAsStream("/config/app.properties")`: phương thức của `Class`. **Dấu `/` đầu tiên** chỉ đường dẫn tuyệt đối tính từ **gốc classpath**. Nếu không có dấu `/`, tên tài nguyên được giải nghĩa tương đối với package của class `App`, tức `com/example`.
- `App.class.getClassLoader().getResourceAsStream("templates/greeting.txt")`: phương thức của `ClassLoader`. Tên truyền vào phải tương đối với **gốc classpath**, thông thường **không có dấu `/` đứng đầu**.
- Cả hai trả về `InputStream` nếu tìm thấy. Nếu không thấy, chúng thường trả về **`null`**; vì vậy chương trình kiểm tra `null` trước khi đọc, tránh `NullPointerException` không rõ nguyên nhân.
- `try-with-resources` đóng stream sau khi đọc xong, kể cả khi có ngoại lệ. Đây là cách đúng để quản lý tài nguyên I/O.
- `StandardCharsets.UTF_8` làm rõ cách giải mã byte thành chuỗi ký tự. `InputStreamReader` giúp `Properties.load(Reader)` đọc đúng văn bản Unicode UTF-8.
- `input.readAllBytes()` phù hợp với tệp mẫu rất nhỏ trong ví dụ. Với tệp lớn, nên đọc theo luồng hoặc theo bộ đệm để không giữ toàn bộ nội dung trong RAM.
- `String.strip()` loại bỏ ký tự xuống dòng/cuối khoảng trắng trong mẫu; `replace("{name}", "Maven")` tạo thông báo đầu ra.

**Vì sao `Properties.load(new InputStreamReader(..., UTF_8))` quan trọng?** Cách gọi `Properties.load(InputStream)` truyền thống diễn giải byte theo quy tắc ISO-8859-1 của định dạng properties, chứ không tự hiểu mọi tệp đều là UTF-8. Để đọc trực tiếp ký tự tiếng Việt như `tài nguyên`, dùng **`load(Reader)` với charset rõ ràng** như trên. Nếu chỉ có tệp ASCII và dùng escape Unicode thì hai cách có thể cho kết quả tương đương, nhưng chúng không phải API đồng nhất về encoding.

## 6. Build, kiểm tra các bản sao resource và chạy ứng dụng

Trước tiên, kiểm tra công cụ:

~~~bash
mvn --version
java -version
javac -version
~~~

Dùng JDK 17 trở lên và Maven có thể chạy với JDK đó. Chạy lệnh ở thư mục có `pom.xml`:

~~~bash
mvn clean package
~~~

Maven xử lý tài nguyên trong pha **`process-resources`** của vòng đời build. Đối với dự án JAR này, Maven Resources Plugin sao chép tài nguyên ở `src/main/resources` sang `target/classes`; sau đó Maven Compiler Plugin biên dịch lớp Java và pha `package` tạo tệp JAR.

Đoạn log kết thúc thành công thường có:

~~~text
[INFO] BUILD SUCCESS
~~~

Kiểm tra thư mục sau build:

~~~text
resources-demo/
├── pom.xml
├── src/
│   └── main/
│       ├── java/com/example/App.java
│       └── resources/
│           ├── config/app.properties
│           └── templates/greeting.txt
└── target/
    ├── classes/
    │   ├── com/example/App.class
    │   ├── config/app.properties
    │   └── templates/greeting.txt
    └── resources-demo-1.0-SNAPSHOT.jar
~~~

Cây trên chỉ hiển thị các tệp quan trọng: Maven có thể tạo thêm thư mục metadata hoặc báo cáo trong `target`.

Chạy trực tiếp từ thư mục lớp đã build:

~~~bash
java -cp target/classes com.example.App
~~~

**Stdout dự kiến chính xác:**

~~~text
Ứng dụng: Demo tài nguyên Maven
Xin chào, Maven!
~~~

Tiếp theo, chạy **chính các lớp và resource ở trong JAR**:

~~~bash
java -cp target/resources-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout dự kiến chính xác vẫn là:**

~~~text
Ứng dụng: Demo tài nguyên Maven
Xin chào, Maven!
~~~

Đây là bằng chứng quan trọng: cùng đường dẫn classpath `config/app.properties` và `templates/greeting.txt` hoạt động khi classpath trỏ tới thư mục `target/classes` **hoặc** JAR. Khi đưa JAR sang máy khác, không cần gửi kèm cả cây `src/main/resources` để đọc hai tệp đã được đóng gói trong JAR.

Có thể liệt kê entry trong JAR bằng công cụ của JDK:

~~~bash
jar tf target/resources-demo-1.0-SNAPSHOT.jar
~~~

Tìm những entry có tên:

~~~text
com/example/App.class
config/app.properties
templates/greeting.txt
~~~

Danh sách hoàn chỉnh sẽ có thêm metadata như `META-INF/`. Đường dẫn tài nguyên trong JAR là **`config/app.properties`**, không phải `src/main/resources/config/app.properties`.

Lệnh `java -jar target/resources-demo-1.0-SNAPSHOT.jar` **chưa chắc hoạt động** với POM này vì manifest chưa có `Main-Class`. Để chạy ví dụ đúng và có thể kiểm chứng, hãy dùng `java -cp ... com.example.App` như trên.

## 7. Classpath và đường dẫn filesystem khác nhau thế nào?

Giả sử chương trình được chạy trong thư mục gốc dự án, bạn có thể thử:

~~~java
new java.io.File("src/main/resources/config/app.properties");
~~~

Đây là đường dẫn filesystem **tương đối với working directory** của tiến trình Java. Nó có thể hoạt động ở môi trường phát triển khi đang đứng trong thư mục dự án, nhưng thường thất bại khi chỉ triển khai tệp JAR tại thư mục khác. Đó là lý do không nên dùng `new File("src/main/resources/...")` để đọc tài nguyên đã đóng gói.

Tương tự, việc gọi `getResource(...)` rồi chuyển URL thành `Path`/`File` không an toàn cho mọi trường hợp: khi resource nằm trong JAR, URL thường dùng lược đồ `jar:` thay vì đường dẫn `file:` thông thường. Dùng `getResourceAsStream` là cách phù hợp khi chỉ muốn đọc nội dung byte bất kể nguồn là thư mục hay JAR.

So sánh:

| Nhu cầu | Cách đọc phù hợp | Lưu ý |
| --- | --- | --- |
| Đọc tệp đóng gói cùng ứng dụng | `Class.getResourceAsStream` hoặc `ClassLoader.getResourceAsStream` | Dùng tên tương đối với classpath. |
| Đọc tệp bên ngoài có đường dẫn cố định, ví dụ tệp cấu hình của môi trường triển khai | `Files.newInputStream(Path)`, `Files.readString(Path, charset)` | Đường dẫn file phải do môi trường chạy cung cấp; không giả định file nằm trong JAR. |
| Ghi dữ liệu khi chạy | Thư mục dữ liệu ngoài JAR, cơ sở dữ liệu hoặc storage được cấp quyền | Tài nguyên đã đóng gói trong JAR không phải vùng ghi dữ liệu runtime. |
| Đọc một phần nội dung tệp lớn | Dùng stream và buffer | Tránh `readAllBytes()` nếu kích thước lớn/không kiểm soát được. |

**Classpath resource** thường lý tưởng cho tài nguyên đi cùng phiên bản mã nguồn: thông điệp mặc định, template, mẫu dữ liệu, schema hoặc file cấu hình mặc định công khai. **Cấu hình triển khai** có thể khác theo môi trường (địa chỉ database, cổng, credential, đường dẫn lưu file), nên thường cần cơ chế external configuration phù hợp thay vì gắn cứng mọi giá trị trong JAR.

## 8. `src/main/resources` và `src/test/resources`

Maven phân biệt tài nguyên dùng khi chạy ứng dụng với tài nguyên dành cho test:

~~~text
src/
├── main/
│   ├── java/
│   └── resources/
│       └── config/app.properties
└── test/
    ├── java/
    └── resources/
        └── fixtures/sample.json
~~~

- `src/main/resources` được xử lý trong pha `process-resources`, thường đưa vào `target/classes` và đưa vào artifact JAR chính.
- `src/test/resources` được xử lý trong pha `process-test-resources`, thường đưa vào `target/test-classes` để test truy cập được khi chạy.
- Với JAR thông thường, `src/test/resources` **không được đóng gói vào JAR ứng dụng chính**. Nó là dữ liệu phục vụ test, ví dụ file fixture JSON, XML, tệp đầu vào cho parser, dữ liệu giả hoặc cấu hình test.

Một test Maven có thể đọc `fixtures/sample.json` từ classpath test mà không cần biết đường dẫn `src/test/resources` trên máy. Khi test chạy, classpath thường có cả `target/test-classes` lẫn `target/classes`; nếu đặt **trùng tên resource** ở test và main, resource của test có thể che resource ứng dụng tùy classpath order. Vì vậy nên đặt tên/đường dẫn rõ ràng và kiểm tra đúng dữ liệu khi kết quả test bất thường.

Không đặt secret thật hay dữ liệu cá nhân vào fixture commit lên repository. Chúng có thể xuất hiện trong lịch sử Git hoặc artifact CI.

## 9. Maven xử lý resource mặc định ra sao?

Đối với dự án Java JAR thông thường không tùy chỉnh resource, Maven lấy các tài nguyên phù hợp trong `src/main/resources` rồi sao chép sang output directory mặc định là `target/classes`. Các đặc điểm chính:

1. **Giữ cấu trúc thư mục tương đối.** `images/logo.png` ở gốc tài nguyên sẽ có tên `images/logo.png` trên classpath/JAR.
2. **Sao chép nội dung như tài nguyên**, không biên dịch file `.properties`, `.txt` hay `.png` thành bytecode Java.
3. **Resource filtering mặc định không bật cho các tài nguyên ứng dụng của cấu hình ví dụ**. Chuỗi như `@project.version@` thường vẫn giữ nguyên nếu không cấu hình filtering.
4. **Không tự quét mọi thư mục bất kỳ.** Nếu đặt file ngoài thư mục resource được Maven khai báo, Maven không tự biết phải đưa vào artifact.
5. **`mvn clean`** xóa output build cũ theo cấu hình clean; vì thế nếu vừa sửa resource, chạy `mvn clean package` sẽ giúp đảm bảo không bị nhầm tệp cũ trong `target`.

Có thể kiểm tra resource đã được copy **trước khi biên dịch Java** bằng:

~~~bash
mvn resources:resources
~~~

Lệnh này gọi trực tiếp goal `resources` của Maven Resources Plugin. Trong dự án thực tế, cú pháp này có thể dùng phiên bản plugin được resolve từ cấu hình; để kiểm chứng build đầy đủ vẫn nên dùng lệnh lifecycle chuẩn `mvn clean package`. Không cần gọi riêng goal đó trước mỗi lần build bình thường.

## 10. Khi nào cần cấu hình `<resources>` trong `pom.xml`?

Khi không theo quy ước mặc định hoặc muốn điều chỉnh tài nguyên được copy, bạn có thể khai báo `<resources>` bên trong `<build>`.

### 10.1. Chọn lọc tài nguyên bằng `includes` / `excludes`

Ví dụ dưới đây **chỉ là một mảnh cấu hình** để chèn vào bên trong thẻ `<build>` của POM, ngang cấp `<plugins>`. Nó chọn copy các tệp `.properties` và `.txt`, bỏ những tệp còn lại:

~~~xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <includes>
            <include>**/*.properties</include>
            <include>**/*.txt</include>
        </includes>
        <filtering>false</filtering>
    </resource>
</resources>
~~~

Với cấu hình này, file `config/app.properties` và `templates/greeting.txt` vẫn được copy; một file `images/logo.png` nằm trong cùng thư mục sẽ không được copy vì không khớp `includes`. **Khi đã khai báo `<resources>` tùy chỉnh, cần bao gồm đầy đủ những thư mục và loại file bạn muốn đóng gói.** Không giả định cấu hình mặc định vẫn tự cộng thêm tất cả file ở `src/main/resources`.

Để thay đổi thư mục đầu ra bên trong `target/classes`, một resource còn có thể dùng `<targetPath>`; đây là tính năng có ích trong một số kiểu đóng gói chuyên biệt nhưng không cần cho cấu trúc mặc định.

### 10.2. Resource filtering: thay placeholder trong lúc build

**Filtering** nghĩa là Maven thay các biểu thức được nhận diện trong file resource bằng giá trị cấu hình khi **build**, trước khi đưa file vào `target/classes`. Chẳng hạn tạo thêm `src/main/resources/build-info.properties`:

~~~properties
build.version=@project.version@
~~~

Khi bật resource filtering cho tệp `.properties`, Maven Resources Plugin có thể thay `@project.version@` bằng phiên bản `1.0-SNAPSHOT` của POM:

~~~properties
build.version=1.0-SNAPSHOT
~~~

Đây là giá trị được gắn tại **thời điểm build**. Nếu chuyển JAR đã build sang máy khác, nó không tự đổi theo biến môi trường của máy đó.

Để chỉ lọc `.properties` mà **không lọc file khác**, bạn có thể dùng mảnh cấu hình sau bên trong `<build>`:

~~~xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <includes>
            <include>**/*.properties</include>
        </includes>
        <filtering>true</filtering>
    </resource>
    <resource>
        <directory>src/main/resources</directory>
        <excludes>
            <exclude>**/*.properties</exclude>
        </excludes>
        <filtering>false</filtering>
    </resource>
</resources>
~~~

Mảnh cấu hình này có hai nhóm không trùng nhau: các tệp `.properties` được filtering; các tệp còn lại được copy nguyên nội dung. Dùng nó để **thay thế phần `<resources>` tùy chỉnh cũ**, không thêm nhiều thẻ `<resources>` song song. Trong ví dụ đơn giản ban đầu, bạn không cần bật filtering.

**Không bật filtering tùy tiện cho ảnh, font, file nén, PDF hay các tệp nhị phân.** Xử lý chúng như văn bản có thể làm hỏng byte và khiến resource không đọc được. Ngoài ra filtering có thể vô tình thay chuỗi placeholder mà ứng dụng dự định xử lý lúc runtime. Với nội dung Unicode, cần nhất quán về encoding; thuộc tính `project.build.sourceEncoding` và cấu hình Maven Resources Plugin liên quan phải phù hợp charset thực tế của tệp.

**Filtering không phải công cụ để đưa mật khẩu/secret vào JAR.** Các giá trị được thay ở build time có thể tồn tại nguyên văn trong artifact và dễ bị trích xuất. Với secret hay cấu hình thay đổi theo môi trường, hãy dùng cơ chế cấu hình bên ngoài, biến môi trường hoặc secret manager do môi trường vận hành cung cấp.

## 11. Những nhầm lẫn và lỗi thường gặp

| Triệu chứng | Giải thích có khả năng xảy ra | Kiểm tra và sửa |
| --- | --- | --- |
| `getResourceAsStream(...)` trả về `null` | Sai tên tài nguyên, thiếu file trên classpath, khác chữ hoa/chữ thường hoặc copy chưa được thực hiện. | Kiểm tra `src/main/resources`, `target/classes` và `jar tf`; so chính xác ký tự trong tên file. |
| Chạy trong IDE được nhưng chỉ chạy JAR thì không thấy resource | Mã đang dùng đường dẫn filesystem như `src/main/resources/...` hoặc IDE thêm thư mục nguồn vào classpath. | Đổi sang classpath stream; kiểm tra tài nguyên có nằm trong JAR. |
| `App.class.getResourceAsStream("config/app.properties")` không tìm thấy | `Class.getResourceAsStream` không có `/` hiểu tên theo package `com/example`. | Dùng `App.class.getResourceAsStream("/config/app.properties")` hoặc ClassLoader với `"config/app.properties"`. |
| `ClassLoader.getResourceAsStream("/config/app.properties")` không tìm thấy | ClassLoader thường yêu cầu tên tương đối từ gốc, không có dấu `/` đầu. | Dùng `"config/app.properties"`. |
| Tiếng Việt bị méo như `Ã...` | Tệp có charset khác charset lúc đọc; hoặc dùng `Properties.load(InputStream)` trên UTF-8. | Lưu UTF-8, nạp `Properties.load(Reader)` với `StandardCharsets.UTF_8`; đọc text theo UTF-8. |
| Tên resource khác nhau giữa máy Windows và Linux | Tên file có chữ hoa/thường không khớp; hệ điều hành/filesystem có quy tắc khác nhau. | Đặt tên thống nhất và kiểm tra đúng case. |
| File `.png` bị lỗi sau build | Resource filtering đã xử lý nhầm file nhị phân. | Đặt binary trong resource group `<filtering>false</filtering>` rồi build lại. |
| Placeholder như `@project.version@` không được thay | Resource filtering chưa bật, hoặc file bị loại khỏi nhóm được filtering. | Kiểm tra `<resources>`, `includes`, cú pháp placeholder và output trong `target/classes`. |
| Tệp nằm trong nguồn nhưng không có trong JAR | Đặt file sai chỗ, bị `excludes` loại, hoặc build chưa chạy lại. | Kiểm tra cấu hình resources, `mvn clean package` và `jar tf`. |
| Resource được đọc thành công nhưng lúc runtime không ghi sửa được | Một entry trong JAR không phải file cấu hình ghi trực tiếp. | Ghi vào vị trí ngoài JAR do ứng dụng kiểm soát. |
| Sau thay đổi file kết quả vẫn cũ | Dùng artifact build trước hoặc chạy nhầm một JAR khác. | `mvn clean package`, kiểm tra timestamp/đường dẫn artifact và classpath thực tế. |

Một nguyên tắc chẩn đoán tốt là lần lượt kiểm tra: **file nguồn có tồn tại → Maven có copy vào `target/classes` → JAR có entry tương ứng → classpath lúc chạy có chứa thư mục/JAR đó → tên resource và cách đọc có chính xác không**. Không nên sửa code đọc stream trước khi chắc chắn artifact có chứa resource.

## 12. Bài thực hành áp dụng và kiểm chứng

Với dự án `resources-demo` vừa tạo, thực hiện tuần tự:

1. Chạy `mvn clean package` và xác nhận `BUILD SUCCESS`.
2. Tìm `target/classes/config/app.properties` và `target/classes/templates/greeting.txt`. So sánh nội dung với file nguồn.
3. Chạy `jar tf target/resources-demo-1.0-SNAPSHOT.jar` và xác nhận cả hai resource ở đường dẫn tương đối.
4. Chạy `java -cp target/resources-demo-1.0-SNAPSHOT.jar com.example.App` và đối chiếu đúng hai dòng stdout.
5. Sửa `templates/greeting.txt` thành `Chúc bạn học tốt, {name}!`, chạy lại `mvn clean package` rồi chạy ứng dụng. Dòng đầu giữ nguyên; dòng thứ hai phải trở thành `Chúc bạn học tốt, Maven!`.
6. Đổi đường dẫn từ `templates/greeting.txt` sang `templates/missing.txt` trong Java, build rồi chạy lại. Quan sát ngoại lệ có thông báo tài nguyên không tìm thấy; sửa lại đường dẫn và kiểm chứng.
7. Thử thêm `src/test/resources/fixtures/data.txt` và kiểm tra rằng resource này không tự được đưa vào JAR ứng dụng chính.

**Câu hỏi tự đánh giá:** Tại sao code đọc resource bằng classpath vẫn chạy được từ JAR? Vì sao đường dẫn nguồn `src/main/resources/config/app.properties` không phải tên resource khi dùng ClassLoader? Hai phương thức `Class.getResourceAsStream` và `ClassLoader.getResourceAsStream` khác nhau ở dấu `/` thế nào? Filtering xảy ra lúc build hay runtime? Tại sao cần giữ file cấu hình nhạy cảm ở ngoài JAR?

Khi trả lời được bằng chính kết quả build và chạy, bạn đã hiểu vai trò của `src/main/resources` trong vòng đời Maven: **tài nguyên nguồn → process-resources → target/classes → đóng gói JAR → đọc từ classpath**.
