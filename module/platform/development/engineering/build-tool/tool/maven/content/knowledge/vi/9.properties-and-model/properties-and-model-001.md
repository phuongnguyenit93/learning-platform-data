# Khai báo properties và tái sử dụng giá trị bằng biểu thức ${...} trong Maven

## 1. Properties dùng để làm gì trong mô hình Maven?

Trong Maven, **property** là một giá trị có tên để dùng lại trong cấu hình build. Thay vì lặp nhiều lần phiên bản dependency, mức Java hoặc tên hiển thị của ứng dụng, ta khai báo giá trị ở một nơi rồi tham chiếu bằng biểu thức **`${ten.property}`**.

Ví dụ một phần trong `pom.xml`:

~~~xml
<properties>
    <java.release>17</java.release>
    <junit.version>5.11.4</junit.version>
</properties>
~~~

Ở một vị trí khác trong cùng POM có thể viết:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>${junit.version}</version>
    <scope>test</scope>
</dependency>
~~~

Maven dùng `5.11.4` khi xử lý dependency vì `junit.version` đã được định nghĩa. Tương tự, `${java.release}` có thể được dùng trong tham số của Maven Compiler Plugin.

**Ba ý cần nhớ ngay:**

1. `<properties>` thuộc **Project Object Model (POM)** và thường chứa các giá trị build có thể chia sẻ.
2. `${...}` là cú pháp nội suy tại thời điểm **Maven xử lý mô hình/cấu hình**; bản thân Java không hiểu nó như cú pháp Java.
3. Việc thay `${...}` bên trong **tệp resource** như `app.properties` là một bước khác, gọi là *resource filtering*; nó chỉ diễn ra khi thư mục/tệp được cấu hình cho phép filtering.

Đừng nhầm `<properties>` trong POM với `java.util.Properties` của Java: cả hai đều là cách làm việc với key-value, nhưng một bên thuộc quá trình Maven build, còn bên kia là API để chương trình đọc dữ liệu khi chạy.

## 2. Những nguồn property thường gặp

Maven có thể lấy giá trị từ nhiều nguồn. Cách tham chiếu giúp phân biệt chúng:

| Nguồn | Biểu thức mẫu | Ý nghĩa |
| --- | --- | --- |
| Khai báo tùy chỉnh trong `<properties>` | `${app.title}`, `${junit.version}` | Giá trị do dự án/parent/profile đặt tên |
| Trường của mô hình dự án | `${project.groupId}`, `${project.artifactId}`, `${project.version}` | Tọa độ và metadata hiện hành của project |
| Thư mục dự án | `${project.basedir}` | Thư mục gốc của project hiện tại |
| Biến môi trường | `${env.JAVA_HOME}`, `${env.PATH}` | Giá trị từ môi trường của tiến trình Maven |
| Maven settings | `${settings.offline}` | Thông tin tương ứng trong `settings.xml`, khi được mô hình hỗ trợ |
| Java system properties | `${java.home}`, `${user.home}` | Các thuộc tính của JVM chạy Maven |
| Tham số CLI | `mvn -Dapp.title=DemoCLI package` | Giá trị người dùng cấp cho lần chạy đó |

Một số tên là **đường dẫn trong mô hình** (`project.version`), không phải key tùy ý phải khai báo trong `<properties>`. Ví dụ, POM có `<version>1.0.0</version>` thì `${project.version}` biểu thị `1.0.0` đối với project hiện tại. Với module kế thừa, giá trị model tương ứng với module đang xử lý, không mặc nhiên là version của mọi module khác.

Dấu chấm trong một property tùy chỉnh như `junit.version` là **một phần của tên key**, không yêu cầu phải tạo XML lồng nhiều cấp. Chữ hoa/chữ thường có ý nghĩa: `${app.title}` và `${app.Title}` không nên được coi là cùng key. Với biến môi trường, sự khác biệt tên và cách hệ điều hành quy chuẩn hóa biến cũng có thể ảnh hưởng kết quả; cần xem môi trường thực chạy Maven.

**Đừng coi `${java.version}` và `${maven.compiler.release}` là một:** `java.version` có thể là Java system property mô tả JVM chạy Maven hoặc một key dự án tự đặt (tùy ngữ cảnh); còn `maven.compiler.release` được Compiler Plugin hỗ trợ để cấu hình mức Java mục tiêu. Khai báo `<maven.compiler.release>17</maven.compiler.release>` không tự cài JDK 17.

## 3. Dự án thực hành Java 17: một chỗ khai báo, nhiều chỗ sử dụng

Ta tạo project `properties-lab`. Nó minh họa đồng thời:

- Khai báo property để kiểm soát mức Java và phiên bản JUnit.
- Dùng `${junit.version}` trong khai báo dependency.
- Dùng `${app.title}` và `${project.version}` trong một tệp cấu hình được **filter lúc build**.
- Chạy Java đọc tệp kết quả bằng `java.util.Properties` để thấy giá trị thực.
- Thử thay `app.title` bằng tham số `-D` mà không sửa POM.

Cấu trúc thư mục:

~~~text
properties-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/App.java
    │   └── filtered-resources/app.properties
    └── test/
        └── java/example/AppTest.java
~~~

Thư mục `filtered-resources` được đặt riêng có chủ ý để chỉ filter đúng file văn bản cần thay thế. Ảnh, font, file nhị phân hoặc tài nguyên có cú pháp `${...}` riêng của framework không nên bị filter một cách vô tình.

### 3.1. `pom.xml` đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>properties-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.11.4</junit.version>
        <app.title>Ứng dụng Maven</app.title>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
            </resource>
            <resource>
                <directory>src/main/filtered-resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>app.properties</include>
                </includes>
            </resource>
        </resources>

        <plugins>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích những chỗ quan trọng:

- `<junit.version>5.11.4</junit.version>` là key tự khai báo, được dùng ở `<dependency><version>${junit.version}</version>`.
- `<maven.compiler.release>17</maven.compiler.release>` là property **được Compiler Plugin nhận diện trực tiếp**; không cần thêm `<release>${maven.compiler.release}</release>` trong ví dụ này.
- `<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>` định hướng encoding khi compiler/resources plugin sử dụng property này.
- `<app.title>Ứng dụng Maven</app.title>` là property **do dự án đặt tên**; Maven không tự lấy tên đó để đổi tên artifact hay in trên console.
- Với `<filtering>true</filtering>` trên đúng `src/main/filtered-resources`, Maven Resources Plugin thay các placeholder được nhận diện khi copy file vào `target/classes`. Thư mục `src/main/resources`, nếu tồn tại, được copy không filtering.
- Ba plugin có version cụ thể để ví dụ dễ tái lập; phiên bản ở đây phục vụ minh họa chứ không phải lời khẳng định chúng mới nhất.

### 3.2. Tệp nguồn resource với biểu thức `${...}`

Tạo `src/main/filtered-resources/app.properties` với **đúng** nội dung:

~~~properties
display.name=${app.title}
build.version=${project.version}
artifact.id=${project.artifactId}
~~~

Các biểu thức này **chưa** phải giá trị cuối cùng. Khi chạy `mvn process-resources` hoặc một pha sau nó như `package`, Maven Resources Plugin xử lý và tạo `target/classes/app.properties` tương đương:

~~~properties
display.name=Ứng dụng Maven
build.version=1.0.0
artifact.id=properties-lab
~~~

Nội dung ví dụ trên là **kết quả dự kiến của quá trình filtering**. Project property `app.title` tạo ra tên hiển thị, còn hai giá trị `project.version` và `project.artifactId` lấy từ POM hiện hành. Maven không chỉnh sửa tệp nguồn trong `src/main/filtered-resources`; nó tạo bản sao đã được xử lý trong output directory.

Nếu không bật filtering, file chỉ được copy và thường vẫn chứa nguyên chuỗi `${app.title}`. Vì thế thấy placeholder xuất hiện trong file `target/classes/app.properties` là dấu hiệu cần kiểm tra cấu hình filtering hoặc tên property.

### 3.3. Chương trình Java đọc kết quả sau filtering

Tạo `src/main/java/example/App.java`:

~~~java
package example;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static Properties loadConfig() throws IOException {
        Properties properties = new Properties();
        try (InputStream input = App.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            try (InputStreamReader reader =
                    new InputStreamReader(input, StandardCharsets.UTF_8)) {
                properties.load(reader);
            }
        }
        return properties;
    }

    public static void main(String[] args) throws IOException {
        Properties config = loadConfig();
        System.out.println(config.getProperty("display.name"));
        System.out.println("version=" + config.getProperty("build.version"));
    }
}
~~~

Mã dùng `Properties.load(Reader)` với `StandardCharsets.UTF_8` để đọc chính xác chuỗi tiếng Việt của ví dụ. `Properties.load(InputStream)` truyền thống diễn giải byte theo ISO-8859-1, vì vậy sẽ không tương đương nếu tài nguyên chứa Unicode UTF-8 như `Ứng dụng Maven`.

Java chỉ nhìn thấy **bản app.properties đã copy vào classpath**. Lớp `App` không gọi Maven và không phân tích `${...}` khi chạy; toàn bộ interpolation đã được Maven làm trước đó ở build time.

### 3.4. Unit test xác nhận thuộc tính được tạo ra

Tạo `src/test/java/example/AppTest.java`:

~~~java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.IOException;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void readsFilteredProperties() throws IOException {
        Properties config = App.loadConfig();

        assertNotNull(config.getProperty("display.name"));
        assertFalse(config.getProperty("display.name").isBlank());
        assertEquals("1.0.0", config.getProperty("build.version"));
        assertEquals("properties-lab", config.getProperty("artifact.id"));
    }
}
~~~

Test không khóa tên hiển thị thành một chuỗi cố định, vì phần sau sẽ thay nó bằng `-Dapp.title=DemoCLI`. Test vẫn xác nhận dữ liệu có giá trị và phiên bản/artifact khớp mô hình. JUnit sử dụng dependency test-scoped; khi chạy `java -cp target/classes example.App` ta không cần nạp JUnit.

### 3.5. Build và quan sát đầu ra

Tại thư mục chứa POM:

~~~bash
mvn -B -ntp clean package
java -cp target/classes example.App
~~~

Yêu cầu JDK 17+ và Maven hoạt động. Với các tệp đúng như trên, Maven chạy goal resources, compile, test và jar; lần build hợp lệ kết thúc bằng `BUILD SUCCESS`.

**Stdout chính xác của lệnh Java thứ hai:**

~~~text
Ứng dụng Maven
version=1.0.0
~~~

Lưu ý `mvn clean package` **không tự gọi** `main` của `App`. Hai dòng trên chỉ xuất hiện khi lệnh `java` riêng được chạy. Có thể xem tệp đã được lọc bằng công cụ đọc file `target/classes/app.properties` và so sánh với bản nguồn để thấy rõ sự thay thế.

## 4. Ghi đè một property cho từng lần chạy bằng `-D`

Không cần sửa POM để đổi tên hiển thị trong lần build thử nghiệm:

~~~bash
mvn -B -ntp -Dapp.title=DemoCLI clean package
java -cp target/classes example.App
~~~

Trong ví dụ này, Maven Resources Plugin nhận **user property** từ dòng lệnh; đối với resource filtering, giá trị `-Dapp.title=DemoCLI` được ưu tiên hơn giá trị mặc định `<app.title>Ứng dụng Maven</app.title>` của POM. File output vì thế chứa `display.name=DemoCLI`.

Stdout của chương trình sau lệnh build mới:

~~~text
DemoCLI
version=1.0.0
~~~

`-Dkey=value` phải được truyền nguyên vẹn thành một đối số. Với giá trị chứa khoảng trắng, cách quote phụ thuộc shell, ví dụ trên Bash dùng `'-Dapp.title=Demo CLI'`. Trong Windows PowerShell, nên đặt cả đối số trong dấu nháy kép: `"-Dapp.title=Demo CLI"`. Nếu dùng Maven Wrapper, các tùy chọn vẫn được Maven nhận theo cách tương tự.

**Phạm vi thay đổi:** `-D` chỉ cấp giá trị cho lần thực thi Maven đó; nó không sửa `pom.xml` gốc. Dù vậy, giá trị mới **có thể được đóng vào artifact** khi resource filtering diễn ra. Nếu build ở CI, hãy lưu lại tập property không nhạy cảm được dùng để bảo đảm artifact có cấu hình đúng môi trường.

Không suy rộng quy tắc ưu tiên của resource filtering sang mọi trường hợp mô hình Maven: các biểu thức đặc biệt `${project.*}`, parent/child resolution và một số phần tử được Maven xử lý sớm có quy tắc riêng. Đặc biệt, không trông đợi `-Dproject.version=...` hay `-DartifactId=...` là cách chuẩn để đổi tọa độ dự án.

## 5. Phân biệt tham chiếu trong POM và lọc tệp tài nguyên

Có hai tình huống sử dụng `${...}` rất khác nhau:

| Tình huống | Nơi chứa biểu thức | Ai xử lý? | Khi nào? |
| --- | --- | --- | --- |
| Property interpolation trong POM | Ví dụ `<version>${junit.version}</version>` của dependency | Maven model builder/configuration | Trong quá trình đọc, xây dựng mô hình và cấu hình goal |
| Resource filtering | Ví dụ `display.name=${app.title}` | Maven Resources Plugin/Maven Filtering | Khi copy nguồn text được đánh dấu `filtering=true` |
| Giá trị trong mã Java | Ví dụ `String text = "${app.title}";` | Không ai tự thay chỉ vì có Maven | Java nhận literal string trừ khi có cơ chế khác được cấu hình |
| Giá trị trong config runtime của framework | Ví dụ Spring placeholder `${PORT:8080}` | Framework có thể xử lý lúc khởi động | Runtime, **không mặc nhiên** là Maven |

Nếu bạn ghi `${app.title}` trong tệp Java và biên dịch bình thường, Maven **không thay nội dung string literal** trong mã Java. Tương tự, một tệp `application.properties` có placeholder do Spring xử lý lúc runtime không nhất thiết nên bật Maven filtering. Hai tầng có thể dùng cú pháp trùng nhau và gây thay thế ngoài ý muốn.

**Khuyến nghị:** chỉ filter những file text thực sự cần giá trị tại build time, hoặc dùng delimiter riêng như `@app.title@` cho Maven trong một thư mục được cấu hình rõ ràng. Không bật filtering hàng loạt trên toàn bộ tree resources chỉ để thay một giá trị.

## 6. Sử dụng giá trị từ project, system, environment và settings

Một số ví dụ phổ biến bên trong POM hoặc cấu hình plugin:

~~~xml
<properties>
    <build.label>${project.artifactId}-${project.version}</build.label>
    <source.root>${project.basedir}</source.root>
</properties>
~~~

`${project.basedir}` thường giúp biểu diễn đường dẫn tương đối theo project hiện tại. Trong multi-module reactor, project/module đang được thực thi có `project.basedir` và `project.artifactId` riêng. Tránh hardcode đường dẫn tuyệt đối của máy lập trình viên vào POM.

Ví dụ về `env` và Java system property:

- `${env.JAVA_HOME}`: giá trị biến môi trường mà tiến trình Maven thấy, nếu được thiết lập.
- `${env.CI}`: biến môi trường tùy hệ thống CI; có thể hoàn toàn không tồn tại ở máy local.
- `${java.home}`: đường dẫn Java home của JVM đang chạy Maven; không nhất thiết trùng từng ký tự với biến `JAVA_HOME`.
- `${settings.offline}`: giá trị thiết lập offline trong Maven settings hiệu lực.

**Không dựa vào sự tồn tại của biến môi trường không bắt buộc.** Nếu không có giá trị hoặc tên tham chiếu bị viết sai, một placeholder có thể không được thay theo cách bạn chờ đợi. Sử dụng default được khai báo rõ ở POM/profile hoặc fail build bằng quy tắc kiểm tra thích hợp nếu đầu vào là bắt buộc.

Các biểu thức project built-in như `${project.version}` không cần thêm `<project.version>` vào `<properties>`; chúng phản ánh mô hình Maven. Nếu muốn hiển thị version cho Java tại runtime, lọc nó qua resource như ví dụ thay vì mong Java tự truy vấn POM.

## 7. Property trong parent POM và dự án nhiều module

Với multi-module, `<properties>` trong **parent POM** là nơi quản lý một số cấu hình dùng chung, còn các module con có thể kế thừa giá trị khi khai báo `<parent>`. Ví dụ đoạn trong parent:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <junit.version>5.11.4</junit.version>
</properties>
~~~

Một module con không tự khai báo lại vẫn có thể dùng:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>${junit.version}</version>
    <scope>test</scope>
</dependency>
~~~

Nếu module con **có khai báo lại** `<junit.version>...</junit.version>`, giá trị của mô hình con có thể thay thế giá trị kế thừa. Dùng khả năng override có chủ đích, vì nếu các module dùng phiên bản dependency không tương thích, build có thể khó chẩn đoán.

Phân biệt:

- **Inheritance**: module con khai báo `<parent>`; dùng để kế thừa cấu hình và properties theo quy tắc Maven.
- **Aggregation**: project gốc liệt kê `<modules>`; Maven Reactor dùng danh sách này để build các module. Có module trong `<modules>` **không tự động** làm module đó kế thừa properties của aggregator.

Với version nhiều dependency, `<dependencyManagement>` và BOM có thể phù hợp hơn việc khai báo cùng property ở từng module. Property hữu ích để đặt tên cho phiên bản, nhưng dependency management mới là cơ chế Maven quyết định version mặc định của dependency ở các POM con khi dùng đúng cách.

## 8. Profiles và các giá trị thay đổi theo môi trường

Maven profile có thể đóng góp **properties** khi được kích hoạt. Ví dụ một đoạn thêm vào trong `<project>`:

~~~xml
<profiles>
    <profile>
        <id>dev</id>
        <properties>
            <app.title>Ứng dụng Maven DEV</app.title>
        </properties>
    </profile>
    <profile>
        <id>staging</id>
        <properties>
            <app.title>Ứng dụng Maven STAGING</app.title>
        </properties>
    </profile>
</profiles>
~~~

Khi bổ sung phần này vào POM demo và chạy:

~~~bash
mvn -B -ntp -Pdev clean package
java -cp target/classes example.App
~~~

Resource filtering sẽ dùng giá trị `app.title` của profile `dev`, vì profile đó đang kích hoạt. Kết quả dự kiến của chương trình:

~~~text
Ứng dụng Maven DEV
version=1.0.0
~~~

Tùy các profile hoạt động đồng thời, inheritance và user properties, cách xác định giá trị cuối có thể phức tạp; **không nên kích hoạt nhiều profile đặt cùng một key rồi đoán kết quả**. Để xem profile thực sự được bật, chạy `mvn help:active-profiles`; để xem cấu hình POM sau kết hợp, dùng `mvn help:effective-pom`.

Profiles nên mô tả sự khác biệt build có thể quản lý; thông tin bí mật và credential của môi trường không nên được commit vào property của POM. Các môi trường release/CI cần định nghĩa rõ profile được phép và kiểm tra artifact tương ứng.

## 9. Kiểm tra property được nội suy thành giá trị nào

Khi Maven tạo ra kết quả không đúng mong đợi, đừng sửa ngẫu nhiên nhiều key. Hãy xác định **giá trị cuối**, **nơi dùng** và **bước chuyển đổi**.

### Dùng Maven Help Plugin

Ví dụ:

~~~bash
mvn help:evaluate -Dexpression=project.version -q -DforceStdout
mvn help:evaluate -Dexpression=app.title -q -DforceStdout
~~~

Lệnh đầu xem giá trị model `project.version`, lệnh sau xem property `app.title`. Output dự kiến của từng lệnh, khi chạy từ thư mục project ví dụ và không bật profile hay `-D` override:

~~~text
1.0.0
~~~

và:

~~~text
Ứng dụng Maven
~~~

Lưu ý: `help:evaluate` là goal của Maven Help Plugin, không phải lệnh Java; lần đầu Maven có thể cần tải plugin. Cách hiển thị phụ thuộc phiên bản plugin và cờ `-q`/`-DforceStdout`, nhưng kết quả đánh giá mới là điều cần kiểm tra.

Để xem mô hình hiệu lực:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

File `effective-pom.xml` giúp kiểm tra inheritance, plugin configuration và profile đã tham gia; đây là **file tạo ra bởi lệnh chẩn đoán**, không phải file source POM nên không cần commit. File output có thể chứa metadata nội bộ hoặc đường dẫn; rà soát trước khi chia sẻ.

### Kiểm tra tệp filtered thực tế

Với ví dụ ở mục 3:

1. Đọc `src/main/filtered-resources/app.properties` và xác nhận còn các placeholder `${...}`.
2. Chạy `mvn -B -ntp clean process-resources`.
3. Đọc `target/classes/app.properties`; phải thấy giá trị thay thế.
4. Chạy `mvn -B -ntp test` hoặc `package`; unit test xác nhận file tồn tại và nội dung quan trọng không sai.
5. Chạy Java từ `target/classes` nếu muốn biết chương trình nhận giá trị nào.

Nếu nguồn đúng nhưng output vẫn là `${app.title}`, hãy kiểm tra `<filtering>true</filtering>`, đường dẫn resource, include/exclude, plugin đã chạy, spelling của key và profile/`-D` đang dùng. Nếu output đúng nhưng Java đọc sai, hãy xem classpath và đường dẫn `getResourceAsStream`, không vội sửa POM.

## 10. Giới hạn nội suy: không phải vị trí nào cũng cho đặt `${...}`

Nên dùng properties ở những nơi Maven cho phép, phổ biến nhất là:

- Phiên bản dependency và các tham số plugin.
- Java release, source encoding, tên báo cáo hoặc các tùy chọn build.
- Tên giá trị được dùng trong tệp text được filtering.
- Các giá trị cấu hình do parent/profile chia sẻ.

**Không giả định bất kỳ XML element nào cũng có thể thay bằng property tùy ý.** Maven cần biết một số phần của mô hình dự án **trước khi** có thể giải quyết property đầy đủ, đặc biệt tọa độ của parent, artifactId và thông tin tham gia Reactor. Việc viết `<artifactId>${my.artifact}</artifactId>` hoặc `<parent><version>${my.version}</version></parent>` không phải một chiến lược chung an toàn. Maven có cơ chế **CI-friendly versions** riêng với các placeholder đặc biệt `${revision}`, `${sha1}`, `${changelist}`; muốn dùng cần hiểu quy tắc riêng và yêu cầu flatten/publish POM phù hợp khi phát hành.

Không tạo chuỗi property tự tham chiếu như `<a>${a}</a>` hoặc các chu trình `a→b→a`: chúng không tạo giá trị hữu ích, có thể dẫn tới lỗi hoặc placeholder không được resolve. Đừng nhồi logic nghiệp vụ vào property expression; Maven property interpolation không phải ngôn ngữ lập trình có điều kiện/vòng lặp.

Một biểu thức `${...}` còn nguyên trong log hoặc artifact thường là dấu hiệu phải kiểm tra nguồn property, nơi Maven có hỗ trợ interpolation không và thời điểm plugin thực thi.

## 11. Bảo vệ tệp resources và dữ liệu bí mật

Resource filtering là một thao tác **ghi giá trị vào artifact**. Nếu filter token hoặc password vào `app.properties`, secret có thể bị đóng trực tiếp trong JAR/WAR và sau đó bị lưu ở nhiều repository, container image hoặc máy người dùng. Vì vậy:

- **Không đặt token/password trong `<properties>` của POM** được commit và không truyền secret thô bằng `-Dsecret=...` nếu chúng có thể lọt vào shell history, process list hoặc log CI.
- Với thông tin cần giữ bí mật lúc runtime (credential DB, API key), dùng secret store/secret injection của môi trường chạy, không đóng vào artifact chung.
- Không bật filtering cho file nhị phân như ảnh, font hay JAR: biến đổi byte có thể làm hỏng chúng.
- Nếu một framework sử dụng cú pháp `${...}` tại runtime (ví dụ cấu hình Spring), tách file runtime khỏi file Maven filtering hoặc dùng delimiter Maven riêng như `@app.title@` và cấu hình delimiter rõ ràng.
- Khi mở `effective-pom.xml`, `mvn -X` hoặc output resources, chú ý URL nội bộ, đường dẫn, tài khoản và tham số nhạy cảm trước khi chia sẻ.

Nếu cần dùng delimiter `@...@` riêng cho resources, có thể cấu hình Maven Resources Plugin (đoạn minh họa **nằm trong** `<plugin><configuration>`, không phải POM hoàn chỉnh):

~~~xml
<delimiters>
    <delimiter>@</delimiter>
</delimiters>
<useDefaultDelimiters>false</useDefaultDelimiters>
~~~

Sau đó tệp filtered có thể dùng `display.name=@app.title@` thay vì `${app.title}`; còn các placeholder kiểu `${PORT:8080}` của framework sẽ không bị Maven Filtering xử lý bởi default delimiter `${...}`. Đây là cách giảm xung đột khi hai công cụ có cùng cú pháp placeholder. Áp dụng nhất quán cho đúng resource cần filter.

## 12. Các lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Dependency báo invalid version hoặc không resolve được `${lib.version}` | Property sai tên, thiếu hoặc không nằm trong mô hình hiệu lực | Kiểm tra `<properties>`, parent/profile; thử `help:evaluate` |
| Artifact chứa nguyên `${app.title}` | Resource không được filtering, đường dẫn không khớp hoặc key không tồn tại | Xem cấu hình `<resources>` và `target/classes` |
| Java in tên hiển thị cũ | Chưa build lại, đọc classpath cũ, `-D` thiếu hoặc profile khác | Chạy `clean package`, đối chiếu file filtered đầu ra |
| CLI `-Dapp.title=...` không tác động | Key khác, shell tách argument, vị trí tham chiếu không dùng key đó | Xem nguyên lệnh, `help:evaluate`, file filtered |
| Có cảnh báo `platform encoding` hoặc tiếng Việt lỗi | Source/resource encoding khác Java reader | Đặt UTF-8 và dùng `Properties.load(Reader)` |
| `maven.compiler.release=17` nhưng compiler không hỗ trợ | JDK Maven đang dùng quá cũ hoặc plugin không phù hợp | Kiểm tra `mvn -version`, plugin, toolchain |
| Module con không nhận property của POM gốc | Chỉ cấu hình `<modules>`, không có `<parent>` phù hợp | Phân biệt aggregation và inheritance |
| Giá trị đổi bất ngờ khi chạy CI | Có `-D`, profile active, system/env khác | Ghi cấu hình không nhạy cảm, xem effective POM/profile |
| Placeholder runtime của framework bị thay ngoài ý muốn | Maven filtering và framework cùng dùng `${...}` | Tách resource hoặc đổi delimiter dành riêng cho Maven |
| File ảnh hoặc dữ liệu binary bị hỏng | Filtering nhầm file nhị phân | Chỉ filter text; để binary trong resource không lọc |

Một thực hành hữu ích: sửa **một yếu tố một lần**, kiểm tra `help:evaluate` và `target/classes` trước khi chạy cả ứng dụng. Nếu đã có resource filtering, cần so sánh **file nguồn** và **file đầu ra**, vì chỉ đọc `pom.xml` không đủ chứng minh artifact đã chứa giá trị đúng.

## 13. Bài tập tự kiểm tra

**Câu 1.** POM có `<junit.version>5.11.4</junit.version>`. Viết biểu thức tái sử dụng nó trong dependency.  
**Đáp án:** `<version>${junit.version}</version>`.

**Câu 2.** Dự án khai báo `<version>1.0.0</version>`. Muốn ghi version hiện hành vào file filtered, nên dùng gì?  
**Đáp án:** `${project.version}`, không cần thêm key tùy chỉnh để sao chép version.

**Câu 3.** File `src/main/resources/app.properties` có `title=${app.title}` nhưng Maven chỉ copy thông thường. File trong `target/classes` đã có tên hiển thị chưa?  
**Đáp án:** Chưa. Không có `filtering=true`, placeholder thường được copy nguyên.

**Câu 4.** Tại sao Java trong ví dụ dùng `Properties.load(Reader)` thay vì `Properties.load(InputStream)`?  
**Đáp án:** Để chủ động đọc tệp UTF-8 chứa tiếng Việt; overload InputStream truyền thống dùng ISO-8859-1.

**Câu 5.** Muốn thử tên hiển thị DemoCLI mà không sửa POM, chạy gì?  
**Đáp án:** `mvn -Dapp.title=DemoCLI clean package` rồi kiểm tra resource/output. Lệnh `-D` không sửa POM.

**Câu 6.** Module được liệt kê trong `<modules>` của aggregator nhưng không khai báo parent tương ứng có tự kế thừa property của aggregator?  
**Đáp án:** Không. Aggregation và inheritance khác nhau.

**Câu 7.** Có nên đặt database password vào POM property rồi filter vào JAR?  
**Đáp án:** Không nên. Giá trị có thể bị đóng vào artifact và lộ qua repo/log; dùng secret store/runtime injection.

**Câu 8.** Một framework có `${PORT:8080}` để xử lý lúc runtime. Làm sao tránh Maven thay thế vô ý?  
**Đáp án:** Không filter file runtime đó, hoặc cấu hình Maven Resources Plugin dùng delimiter riêng như `@...@` trên những file cần filtering.

## 14. Checklist khi dùng properties trong dự án

- [ ] Dùng tên key dễ hiểu, nhất quán, ví dụ `junit.version`, `app.title`.
- [ ] Với metadata project, ưu tiên `${project.version}`, `${project.artifactId}` thay vì nhân bản giá trị.
- [ ] Khai báo version dependency trong `<properties>` hoặc quản lý qua `<dependencyManagement>` khi phù hợp.
- [ ] Khóa phiên bản plugin quan trọng và xác nhận Java release phù hợp JDK.
- [ ] Phân biệt property interpolation trong POM với resource filtering trong `src/main/*`.
- [ ] Chỉ filter text cần thiết, tránh binary và placeholder runtime.
- [ ] Kiểm tra giá trị bằng `help:evaluate`, `help:effective-pom` và file `target/classes`.
- [ ] Kiểm tra tác động của CLI `-D`, profile và parent trước khi phát hành.
- [ ] Không chứa secret trong POM, lệnh `-D` hoặc artifact phân phối.
- [ ] Chạy lại `mvn clean test`/`package` và kiểm tra output của chương trình.

## Tài liệu chính thức

- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): khai báo `<properties>`, tham chiếu trong dependency, thừa kế và mô hình dự án.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): cách truy cập `project.*`, `env.*`, `settings.*`, Java system properties.
- [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html): bật filtering, delimiter, encoding và escaping.
- [Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html): biểu thức `${...}`, `@...@`, `-D`, cấu hình resource directory.
- [Maven Help Plugin — help:evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html): đánh giá một biểu thức property trong Maven.
- [Apache Maven — CI Friendly Versions](https://maven.apache.org/maven-ci-friendly.html): trường hợp đặc biệt cho placeholder revision/changelist trong version.

**Tóm lại:** `<properties>` giúp tập trung cấu hình, `${...}` giúp Maven dùng lại giá trị đúng nơi có hỗ trợ interpolation. Khi muốn đưa giá trị sang file cấu hình của ứng dụng, phải chọn đúng tài nguyên để **filter lúc build**; khi cần dữ liệu động/bí mật tại runtime, nên để framework hoặc môi trường chạy xử lý thay vì đóng cứng vào artifact.
