# Thuộc tính dòng lệnh và khả năng ghi đè cấu hình trong Maven

## 1. Vấn đề: cùng một POM, nhiều lần build khác nhau

Dự án Maven thường có một cấu hình mặc định trong `pom.xml`, nhưng máy lập trình viên, pipeline CI và môi trường thử nghiệm không phải lúc nào cũng dùng cùng giá trị. Có lúc bạn muốn đổi phiên bản Java dùng để biên dịch, chọn bộ kiểm thử, đặt chuỗi hiển thị trong tài nguyên, bật một profile hoặc dùng kho local khác **cho một lần chạy**, mà không muốn sửa rồi commit `pom.xml`.

Maven cung cấp **user properties** qua tùy chọn dòng lệnh:

```bash
mvn -Dten.thuoc.tinh=gia-tri clean verify
```

Ví dụ:

```bash
mvn -Dmaven.compiler.release=17 clean package
mvn -DskipTests=true package
mvn -Dtest=AppTest test
```

Cách diễn giải đúng: `-D` đưa một cặp **tên = giá trị** vào phiên chạy Maven. Thành phần nào của Maven hoặc plugin **đọc đúng tên property đó** mới chịu ảnh hưởng. Nó không phải một nút “ghi đè mọi trường POM” và không tự thay cấu trúc XML cố định.

Kết quả học tập của bài: bạn sẽ khai báo property mặc định trong POM, ghi đè bằng `-D`, quan sát hiệu ứng bằng chương trình Java 17 và resource filtering, kiểm chứng effective model, phân biệt `-D` với `-P` và `-s`, đồng thời nhận biết giới hạn của việc ghi đè cấu hình.

## 2. Bản đồ các nguồn cấu hình

Khi Maven xây dựng một dự án, các giá trị có thể đến từ nhiều nơi:

| Nguồn | Ví dụ | Vai trò |
| --- | --- | --- |
| Thuộc tính dự án trong POM | `<properties><app.greeting>Xin chào</app.greeting></properties>` | Giá trị mặc định được quản lý trong mã nguồn |
| POM cha và profile đang hoạt động | `<profiles>...<properties>...` | Giá trị hoặc cấu hình áp dụng tùy dự án/môi trường |
| Thuộc tính người dùng (user properties) | `-Dapp.greeting=Chào` | Giá trị do người gọi Maven cung cấp cho lần chạy |
| Thuộc tính hệ thống của JVM chạy Maven | `java.version`, `user.home` | Thông tin môi trường Java/Maven |
| Biến môi trường | `${env.JAVA_HOME}` | Giá trị lấy từ môi trường của tiến trình Maven |
| Cấu hình Maven settings | `~/.m2/settings.xml`, `-s settings-ci.xml` | Mirror, proxy, server, profile settings, local repository |
| Cấu hình plugin | `<configuration><release>17</release></configuration>` | Giá trị cụ thể của tham số plugin/goal |

Không có một **bảng thứ tự ưu tiên duy nhất** áp dụng cho mọi trường và mọi plugin. Với **những biểu thức/property được hỗ trợ**, user properties từ `-D` thường ưu tiên hơn giá trị cùng tên trong `<properties>` khi Maven hay plugin giải quyết biểu thức. Với **Maven Resources Plugin filtering** ở ví dụ bên dưới, tài liệu chính thức xác nhận tham số `-D` thay được property mặc định từ POM.

Tuy nhiên, cần tách hai trường hợp:

1. **Giá trị được tham chiếu bằng property**: ví dụ tài nguyên chứa `@app.greeting@`, hoặc plugin dùng property `maven.compiler.release`. Đây là điểm ghi đè phù hợp.
2. **Giá trị được ghi cố định hoặc cấu trúc XML**: ví dụ POM đặt `<artifactId>my-library</artifactId>`, plugin có một cấu hình cứng không đọc property, hay `<modules>`. Tự tạo `-DartifactId=other` không có nghĩa Maven đổi danh tính dự án.

Vì thế phải trả lời ba câu: **tên property chính xác là gì, thành phần nào đọc nó, và lúc nào nó được đánh giá?**

## 3. Cú pháp CLI và quy tắc truyền tham số

Cấu trúc thông dụng:

```bash
mvn -Dkey=value clean verify
mvn clean verify -Dkey=value
mvn -Dkey1=one -Dkey2=two test
```

Thông thường Maven chấp nhận tùy chọn trước hoặc sau phase/goal. Cần phân biệt:

- `-Dkey=value`: truyền một giá trị tên `key` vào Maven.
- `-Dkey`: viết tắt thường được dùng để bật một cờ boolean được plugin hỗ trợ. Khi cần tính rõ ràng, dùng `-Dkey=true` hoặc `-Dkey=false`.
- `-Pprofile-id`: yêu cầu kích hoạt profile Maven, không phải khai báo property có tên `profile-id`.
- `-s /path/settings.xml`: chọn user settings, không phải ghi đè một property POM.
- `-f /path/pom.xml`: chọn POM cần chạy.
- `-o`: chạy offline, không phải user property.
- `-Dtest=AppTest`: truyền tên property `test` được Maven Surefire Plugin sử dụng để lọc test; không phải chọn tệp POM.

### 3.1. Đường dẫn hoặc giá trị có khoảng trắng

Trên Bash/zsh, bao toàn bộ đối số:

```bash
mvn "-Dapp.greeting=Chào buổi sáng" clean package
```

Trên Windows PowerShell:

```powershell
mvn '-Dapp.greeting=Chào buổi sáng' clean package
```

Cả hai cách nhằm truyền **một argument** có dạng `-Dapp.greeting=Chào buổi sáng`. Nếu không đặt dấu nháy và shell tách thành các từ, Maven có thể hiểu nhầm những từ còn lại là phase hoặc goal. Không dựa vào ví dụ quote của Bash để chạy nguyên xi trong Windows CMD, PowerShell hoặc hệ thống CI có shell khác.

### 3.2. Dấu dollar và biểu thức trong shell

Trong POM, cú pháp như `${app.greeting}` được **Maven** diễn giải ở nơi hỗ trợ interpolation. Nhưng trong shell Bash, chuỗi chứa `$` có thể bị shell mở rộng trước khi Maven nhìn thấy. Nếu cần truyền **nguyên văn** biểu thức `${...}` trong một đối số Bash, dùng dấu nháy đơn hoặc escape phù hợp.

PowerShell cũng có quy tắc mở rộng chuỗi, và CMD dùng cú pháp biến môi trường khác. Trong bài thực hành, ta truyền giá trị thực qua `-D` thay vì gửi chuỗi `${...}` từ CLI để tránh nhầm lẫn.

## 4. Khai báo property mặc định trong pom.xml

Đặt giá trị dùng chung trong `<properties>`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <app.greeting>Xin chào</app.greeting>
</properties>
```

Đoạn trên là **một phần của POM**, không phải POM đầy đủ.

- `maven.compiler.release` là tên property được Maven Compiler Plugin hỗ trợ khi cấu hình của plugin cho phép.
- `project.build.sourceEncoding` thường được các plugin liên quan dùng làm encoding mặc định.
- `app.greeting` là **property do dự án tự đặt**. Maven không tự hiểu nó là lời chào: phải tham chiếu property đó trong resource, POM hoặc plugin thì mới có hiệu lực.

Khi viết một property cho nhóm dùng chung, chọn tên rõ nghĩa và giá trị mặc định an toàn. Những lựa chọn quan trọng như phiên bản Java, dependency/plugin version và thông số phát hành vẫn nên được review trong cấu hình mã nguồn, thay vì âm thầm dựa vào tham số chỉ tồn tại trên máy một người.

## 5. Ví dụ độc lập: -D thay giá trị được lọc vào tài nguyên

Trong bài này ta dùng **Maven Resources Plugin** để lọc một tài nguyên văn bản. Ví dụ cụ thể giúp quan sát sự khác biệt giữa property trong POM và giá trị ở lần chạy, thay vì chỉ suy đoán Maven đã ghi đè.

Cấu trúc dự án:

```text
property-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/App.java
    │   └── resources/application.properties
    └── test/
        └── java/dev/example/AppTest.java
```

### 5.1. pom.xml hoàn chỉnh

Dùng Java 17+, Maven 3.9.x và các phiên bản plugin khai báo rõ:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>property-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <app.greeting>Xin chào</app.greeting>
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
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp này có ba thành phần thiết yếu cho bài:

1. Property mặc định `<app.greeting>Xin chào</app.greeting>`.
2. `<filtering>true</filtering>` để Maven Resources Plugin xử lý các placeholder trong `src/main/resources`. Nếu không bật, resource sẽ được sao chép nguyên văn.
3. Compiler Plugin và Surefire Plugin để build Java 17 và chạy JUnit Jupiter.

Lưu ý: không nên đặt tài nguyên nhị phân như PNG, ảnh, PDF vào vùng lọc text một cách thiếu kiểm soát; lọc chúng có thể làm hỏng nội dung. Trong dự án thật, chỉ lọc các tệp văn bản cần thay biến.

### 5.2. Tệp resource được Maven thay biến

Tạo `src/main/resources/application.properties`:

```properties
greeting=@app.greeting@
```

Dấu `@...@` là một cú pháp placeholder được Maven Resources Plugin hỗ trợ. Khi xử lý resource, plugin thay nó bằng giá trị property `app.greeting`. Ở đây ta cố ý dùng `@...@` để phân biệt rõ placeholder được Maven lọc lúc build với cách Java đọc tệp ở runtime.

Sau `mvn process-resources` (và khi không có `-D` ghi đè), Maven sẽ tạo:

```text
target/classes/application.properties
```

Nội dung tệp đó sẽ là:

```properties
greeting=Xin chào
```

**Tệp trong `src/main/resources` vẫn giữ nguyên placeholder.** Bản đã lọc nằm trong `target/classes` và thường được đóng vào JAR của dự án. Đây là dữ liệu tạo ra **lúc build**, không phải giá trị tự động thay đổi khi ứng dụng đang chạy.

### 5.3. Mã Java đọc resource một cách đúng encoding

Tạo `src/main/java/dev/example/App.java`:

```java
package dev.example;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static String messageFor(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên phải có nội dung");
        }

        Properties properties = new Properties();
        try (InputStream stream =
                     App.class.getResourceAsStream("/application.properties")) {
            if (stream == null) {
                throw new IllegalStateException("Thiếu application.properties");
            }
            properties.load(new InputStreamReader(
                    stream, StandardCharsets.UTF_8));
        } catch (IOException exception) {
            throw new IllegalStateException(
                    "Không đọc được application.properties", exception);
        }

        String greeting = properties.getProperty("greeting");
        if (greeting == null) {
            throw new IllegalStateException("Thiếu thuộc tính greeting");
        }
        return greeting + ", " + name.strip() + "!";
    }

    public static void main(String[] args) {
        System.out.println(messageFor("Lan"));
    }
}
```

Điểm kỹ thuật quan trọng: `Properties.load(InputStream)` theo quy ước cũ đọc byte ở dạng ISO-8859-1; ví dụ này dùng `Properties.load(Reader)` với `StandardCharsets.UTF_8` để giữ đúng chữ tiếng Việt trong resource đã lọc. Đây cũng là lý do phải khai báo encoding của Resources Plugin và lưu tệp nguồn bằng UTF-8.

Tạo `src/test/java/dev/example/AppTest.java`:

```java
package dev.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AppTest {
    @Test
    void createsGreetingForName() {
        assertTrue(App.messageFor(" Lan ").endsWith(", Lan!"));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> App.messageFor("   "));
    }
}
```

Kiểm thử thứ nhất không cố định phần lời chào vì mục đích bài tập là cho phép thay nó qua `-D`. Kiểm thử thứ hai đảm bảo tên chỉ có khoảng trắng bị từ chối. Hai kiểm thử này vẫn đúng dù phần mở đầu là `Xin chào` hay `Chào buổi sáng`.

### 5.4. Chạy mặc định và xác nhận stdout

Ở thư mục `property-demo` có `pom.xml`, chạy:

```bash
mvn clean package
java -cp target/classes dev.example.App
```

Đầu ra **chính xác của chương trình Java** (không tính log Maven):

```text
Xin chào, Lan!
```

Lúc này, bạn có thể mở `target/classes/application.properties` và xác nhận:

```properties
greeting=Xin chào
```

### 5.5. Ghi đè trong một lần build bằng -D

Trên Linux/macOS:

```bash
mvn "-Dapp.greeting=Chào buổi sáng" clean package
java -cp target/classes dev.example.App
```

Trên Windows PowerShell:

```powershell
mvn '-Dapp.greeting=Chào buổi sáng' clean package
java -cp target/classes dev.example.App
```

Kết quả của lệnh `java` trong cả hai trường hợp:

```text
Chào buổi sáng, Lan!
```

Dòng bên trong `target/classes/application.properties` giờ là:

```properties
greeting=Chào buổi sáng
```

Chỉ một lần build được đổi giá trị. `pom.xml` vẫn có giá trị mặc định `Xin chào` và `src/main/resources/application.properties` vẫn chứa `@app.greeting@`. Khi chạy lại `mvn clean package` **không truyền `-D`**, kết quả quay về giá trị mặc định.

Lệnh `clean` trước `package` giúp tránh nhầm bản tài nguyên cũ với bản vừa được xử lý. Trong CI, các tệp build trong `target/` không nên được xem như cấu hình nguồn cần commit.

## 6. Ba tầng cần phân biệt: build time, runtime và JVM properties

Ví dụ trên **không truyền property từ Maven tới một Java process đang chạy**. Nó làm hai bước tách biệt:

1. Maven nhận `-Dapp.greeting=...`, Maven Resources Plugin dùng giá trị đó để tạo resource trong `target/classes` lúc build.
2. Java chạy sau đó đọc resource đã tạo, nên nhìn thấy giá trị mới.

Điều này khác với:

```bash
java -Dapp.greeting=Hello -cp target/classes dev.example.App
```

Lệnh `java -D...` đặt JVM system property cho tiến trình ứng dụng, nhưng **mã `App` trong ví dụ không gọi `System.getProperty("app.greeting")`**, nên nó không thay nội dung `application.properties` đã được Maven tạo. Chỉ khi mã ứng dụng chủ động đọc system property thì tùy chọn JVM đó mới có ý nghĩa đối với logic chạy.

Tương tự, `mvn -Dapp.greeting=Hello package` không tự đảm bảo một chương trình Java chạy trong tương lai nhìn thấy `System.getProperty("app.greeting")` bằng `Hello`. Tác dụng của `-D` phụ thuộc cách Maven/plugin sử dụng thuộc tính.

Đừng dùng resource filtering để đưa token hoặc password vào JAR: đó sẽ biến secret thành dữ liệu có thể trích xuất từ artifact, ngay cả khi bạn không commit secret vào Git.

## 7. Ghi đè một tham số plugin: phải biết property name mà plugin hỗ trợ

Nhiều plugin Maven công bố property cho tham số cấu hình của chúng:

| Property CLI | Plugin/thành phần thường dùng | Ý nghĩa điển hình |
| --- | --- | --- |
| `-Dmaven.compiler.release=17` | Maven Compiler Plugin | Chọn mục tiêu Java `--release` khi plugin lấy giá trị từ property |
| `-DskipTests=true` | Maven Surefire Plugin | Bỏ qua thực thi test, thông thường vẫn biên dịch mã test |
| `-Dmaven.test.skip=true` | Compiler Plugin và plugin test liên quan | Bỏ qua cả biên dịch lẫn chạy test trong cấu hình thông dụng |
| `-Dtest=AppTest` | Maven Surefire Plugin | Chỉ chọn những unit test phù hợp mẫu |
| `-Dmaven.repo.local=/abs/path` | Maven Core | Dùng kho Maven local chỉ định |
| `-Dapp.greeting=Hello` | Dự án tự khai báo | Có tác dụng khi được POM/plugin/resource sử dụng |

**Các property không phải tên tùy ý.** Để xác định tham số plugin nào có thể thay bằng `-D`, xem tài liệu về plugin goal và trường **User Property** của tham số đó.

Ví dụ đọc thông tin plugin Surefire:

```bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-surefire-plugin -Dgoal=test -Ddetail
```

Nếu POM chỉ viết:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
</plugin>
```

và khai báo `maven.compiler.release` trong `<properties>` như dự án mẫu, property đó thường là cách thích hợp để thay target. Nhưng nếu POM có:

```xml
<configuration>
    <release>17</release>
</configuration>
```

thì đây là **một cấu hình trực tiếp**, có thể được plugin xem là giá trị đã chỉ định. Không nên khẳng định `-Dmaven.compiler.release=11` luôn thay được giá trị `17` đã viết cứng. Nếu muốn cố ý cho phép thay, có thể đưa property vào cấu hình:

```xml
<configuration>
    <release>${maven.compiler.release}</release>
</configuration>
```

Các đoạn cấu hình vừa nêu là **đoạn con** của Compiler Plugin, không phải POM hoàn chỉnh. Và yêu cầu `--release` không đồng nghĩa Maven tự chuyển sang một JDK khác: JDK đang chạy Maven vẫn phải hỗ trợ target được yêu cầu.

## 8. Thứ tự ưu tiên: hiểu theo nơi giải quyết biểu thức, không học thuộc một công thức toàn cục

Xét property `app.greeting` được khai báo ở POM với `Xin chào`.

| Tình huống | Giá trị mà resource filtering dùng trong ví dụ |
| --- | --- |
| Chỉ dùng POM mặc định | `Xin chào` |
| Chạy với `-Dapp.greeting=Hello` | `Hello` |
| Chạy với `-Dapp.greeting="Chào bạn"` | `Chào bạn` |
| Profile đặt `app.greeting=Chào từ profile` và đang active, không có CLI override | Giá trị của profile đang active, theo mô hình/profile có hiệu lực |
| Profile active và CLI truyền `-Dapp.greeting=Hello` | `Hello` đối với resource filtering trong ví dụ |

Cần kiểm chứng thực tế khi nhiều profile khai báo cùng tên. Maven hợp nhất model, kế thừa từ POM cha và tính profile active; kết quả cuối cùng cũng phụ thuộc nơi property được dùng. Với **resource filtering**, user properties thường được ưu tiên hơn project properties. Nhưng một field XML cố định, thông tin được tính bởi Maven Core, plugin không hỗ trợ property hoặc bước chạy không tham chiếu giá trị đó sẽ không thể thay đổi chỉ bằng cách đặt tên `-D` giống field.

Một phản ví dụ:

```xml
<groupId>dev.example</groupId>
<artifactId>property-demo</artifactId>
<version>1.0.0-SNAPSHOT</version>
```

Chạy:

```bash
mvn -Dproject.version=9.9.9 help:evaluate -Dexpression=project.version -q -DforceStdout
```

Không nên xem `-Dproject.version=9.9.9` là lệnh chỉnh tọa độ artifact trong POM: `project.version` là **biểu thức truy cập model**. Việc đặt một user property có cùng chuỗi tên không tự viết lại `<version>1.0.0-SNAPSHOT</version>` đã khai báo. Muốn thay phiên bản theo pipeline, dùng một cơ chế được Maven hỗ trợ như **CI-friendly version** với placeholder `${revision}` được cấu hình đúng, hoặc quy trình cập nhật version (ví dụ Maven Versions Plugin) có review.

Ngoài ra, một CLI property viết sai tên có thể được Maven chấp nhận mà không báo lỗi nhưng không thay đổi gì vì không thành phần nào đọc nó. Phải xác minh bằng kết quả plugin, resource đã xử lý hoặc effective model.

## 9. Profile (-P) so với user properties (-D)

Profile là một tập cấu hình có tên. Có thể bật qua `-P<id>` hoặc điều kiện kích hoạt (JDK, OS, property, file...). Profile có thể đóng góp dependencies, plugins, repositories và properties.

Thêm ví dụ **đoạn con ở cấp `<project>` trong POM**:

```xml
<profiles>
    <profile>
        <id>demo</id>
        <properties>
            <app.greeting>Chào từ profile</app.greeting>
        </properties>
    </profile>
</profiles>
```

Bây giờ chạy:

```bash
mvn -Pdemo clean process-resources
```

Khi profile `demo` đang active, tài nguyên ví dụ sẽ chứa:

```properties
greeting=Chào từ profile
```

Nếu tiếp tục thêm property CLI:

```bash
mvn -Pdemo "-Dapp.greeting=Chào từ CLI" clean process-resources
```

Trong resource filtering, đầu ra sẽ là:

```properties
greeting=Chào từ CLI
```

**Điểm khác biệt:** `-Pdemo` kích hoạt cả profile (có thể đổi cấu trúc và plugin), còn `-Dapp.greeting=...` chỉ đặt property. Đặt `-Ddemo=true` không đồng nghĩa kích hoạt profile có ID `demo`.

Tuy vậy, profile **có thể được kích hoạt bằng property nếu POM khai báo rõ điều kiện kích hoạt**:

```xml
<activation>
    <property>
        <name>env.demo</name>
        <value>true</value>
    </property>
</activation>
```

Nếu đặt đoạn này bên trong profile, Maven có thể kích hoạt profile khi gọi `mvn -Denv.demo=true ...`. Đây là một cơ chế rõ ràng của profile; không phải tính năng tự động gắn `-D` với tên profile. Xem profile active bằng:

```bash
mvn help:active-profiles
mvn -Pdemo help:active-profiles
```

**Lưu ý:** các đặc điểm của profile được giải quyết trong lúc xây dựng model. Không nên giả định một property do chính profile A tạo ra luôn có thể kích hoạt profile B theo cùng một cách trên mọi phiên bản Maven. Với nhu cầu kiểm soát rõ ràng, ưu tiên kích hoạt trực tiếp `-P` hoặc điều kiện đã được tài liệu hóa.

## 10. Settings, biến môi trường và model: những điểm -D không thay thế được

Không nhầm `-D` với việc thay đổi những đầu vào khác của Maven:

- **Settings:** `mvn -s settings-ci.xml verify` chọn user settings, ví dụ cấu hình mirror, proxy hoặc credentials. Một user property thông thường không thay được toàn bộ settings file.
- **Local repository:** `mvn "-Dmaven.repo.local=/abs/maven-cache" test` là property **đặc biệt Maven Core hiểu**; đây không phải một tên do dự án tự định nghĩa. Trên Windows cần dùng đường dẫn hợp lệ của máy.
- **POM:** `mvn -f subproject/pom.xml verify` chọn tệp mô hình build. `-Dpom.xml=...` không tương đương.
- **Môi trường/JDK:** `JAVA_HOME` và cấu hình toolchain/JDK quyết định công cụ Java nào có thể được sử dụng. `-Djava.version=21` không phải cách cài hoặc đổi JDK thực.
- **Dependency/plugin version:** khi version viết cố định ở POM, `-Dsome.version=...` chỉ có tác dụng nếu cấu hình thực sự tham chiếu property `${some.version}` ở vị trí được Maven hỗ trợ.
- **Khả năng truy cập repository:** token, quyền và địa chỉ repository thuộc settings/CI/remote server; một tên `-D` bất kỳ không làm Maven tự có quyền.
- **Plugin configuration:** những giá trị không có User Property có thể cần được cấu hình trực tiếp trong POM hoặc qua profile.

Với giá trị nhạy cảm, tránh truyền token dưới dạng `-Dpassword=...` trên CLI vì chúng có thể lộ trong lịch sử shell, thông tin tiến trình hoặc log. Dùng kho bí mật và cách truyền thông tin an toàn theo nền tảng CI.

## 11. Cách xem giá trị Maven thật sự sử dụng

### 11.1. Kiểm tra một biểu thức bằng Help Plugin

Từ thư mục chứa `pom.xml`:

```bash
mvn help:evaluate -Dexpression=app.greeting -q -DforceStdout
```

Nếu dùng POM ví dụ chưa có profile ghi đè, output là:

```text
Xin chào
```

Khi thêm user property:

```bash
mvn "-Dapp.greeting=Hello" help:evaluate -Dexpression=app.greeting -q -DforceStdout
```

Kết quả mong đợi:

```text
Hello
```

Các lệnh Help Plugin có thể cần tải plugin/dependency lần đầu. Đầu ra console thực tế có thể có thông báo từ launcher, đặc biệt nếu một IDE hoặc wrapper cung cấp log bổ sung; điều quan trọng là giá trị biểu thức mà Help Plugin trả về.

### 11.2. Xem effective POM và active profiles

```bash
mvn help:effective-pom
mvn -Pdemo help:effective-pom
mvn -Pdemo help:active-profiles
```

`help:effective-pom` cho thấy mô hình sau khi xử lý kế thừa và profile đang hoạt động. Nhưng **không nên xem việc một dòng XML xuất hiện trong effective POM là bằng chứng duy nhất về runtime effect của plugin**: một số user properties được plugin đọc trực tiếp khi thực thi goal; chúng có thể không làm thay đổi mọi trường XML hiển thị.

Dùng `help:describe` để tìm User Property được plugin công bố, và chạy thử chính goal rồi quan sát kết quả tạo ra:

```bash
mvn "-Dapp.greeting=Chào thử" clean process-resources
```

Sau đó mở `target/classes/application.properties` để kiểm tra dòng `greeting=Chào thử`. Đây là bằng chứng trực tiếp về giá trị mà Resources Plugin đã xử lý.

Nếu cần debug sâu:

```bash
mvn -X "-Dapp.greeting=Hello" test
```

`-X` in nhiều log, có thể chứa URL nội bộ hoặc chi tiết môi trường; không chia sẻ nguyên log ra nơi công khai.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `-Dapp.greeting=...` không tác dụng | Resource chưa bật filtering hoặc sai tên property | Kiểm tra `<filtering>true</filtering>`, placeholder và property name |
| Chuỗi có khoảng trắng gây lỗi “Unknown lifecycle phase” | Shell tách giá trị thành nhiều đối số | Quote toàn bộ `"-Dapp.greeting=..."` |
| Văn bản tiếng Việt sai dấu khi Java đọc resource | Dùng `Properties.load(InputStream)` không phù hợp với UTF-8 | Đọc bằng `InputStreamReader(..., UTF_8)` |
| Tưởng `-Dfoo=bar` đổi `<artifactId>` | `foo` không được model/plugin sử dụng để đặt artifactId | Dùng cấu hình model hoặc cơ chế đổi version phù hợp |
| `-Dmaven.compiler.release` bị bỏ qua | Plugin có cấu hình trực tiếp, tên property sai hoặc plugin cũ | Xem cấu hình thực tế, tài liệu plugin, debug log |
| `-DskipTests` nhưng kiểm thử vẫn có lỗi biên dịch | `skipTests` thường bỏ bước chạy test, không bỏ test-compile | Sửa test hoặc hiểu đúng `maven.test.skip`; không tắt test để qua QA |
| `-Pdemo` không bật | Sai ID profile hoặc profile không được khai báo trong phạm vi Maven đang chạy | Xem `help:active-profiles` |
| `-Ddemo=true` không bật profile `demo` | Profile không khai báo activation theo property | Dùng `-Pdemo` hoặc thêm activation đúng |
| Giá trị chỉ thay đổi trong JAR, không đổi ứng dụng đang chạy | Resource filtering diễn ra lúc build, không phải runtime | Build lại và chạy artifact mới |
| Tham số chạy đúng trên Bash nhưng lỗi PowerShell | Quote và quy tắc mở rộng biến khác nhau | Dùng cú pháp tương ứng với shell |
| Muốn đổi local repo bằng property tự đặt | Maven chỉ nhận key đặc biệt `maven.repo.local` | Dùng `-Dmaven.repo.local=...` hoặc settings |
| Các máy CI cho kết quả khác nhau | Truyền user properties khác nhau, JDK/plugin/profiles khác | Ghi lại lệnh CI, effective config và phiên bản tool |

Không nên kết luận “Maven bỏ qua `-D`” chỉ vì `pom.xml` không bị sửa. **User property có hiệu lực trong phiên build**, và POM nguồn thường giữ nguyên. Kiểm tra đúng output: resource đã lọc, tham số plugin hoặc báo cáo test.

## 13. Bài tập tự kiểm tra

1. Chạy `mvn clean package` và xác nhận Java in `Xin chào, Lan!`. Kiểm tra `src/main/resources/application.properties` và `target/classes/application.properties`; tệp nào chứa placeholder?
2. Chạy `mvn "-Dapp.greeting=Chúc mừng" clean package` rồi chạy `App`. Dự đoán chuỗi `Chúc mừng, Lan!` và giải thích từng bước chuyển giá trị.
3. Chạy lại `mvn clean package` không có `-D`; chứng minh giá trị quay về mặc định mà POM chưa từng bị sửa.
4. Thêm profile `demo` trong mục 9, thử `-Pdemo` và thử đồng thời `-Pdemo -Dapp.greeting=Hello`; so sánh kết quả filtering.
5. Sửa `@app.greeting@` thành `@app.greetng@` (sai chính tả) trong resource thử nghiệm. Tại sao lệnh `-Dapp.greeting=...` không còn thay đúng chỗ? Khôi phục tên đúng sau thử nghiệm.
6. Đặt `-Dmaven.compiler.release=11` khi đang dùng JDK 17 và nguồn Java chỉ sử dụng API hỗ trợ từ Java 11; quan sát có thể biên dịch không. Giải thích vì sao điều này không đồng nghĩa đổi JVM đang chạy Maven.
7. Chạy `mvn help:evaluate -Dexpression=app.greeting -q -DforceStdout` và lệnh có bổ sung `-Dapp.greeting=Hello`. So sánh hai giá trị.
8. Tìm một tham số của Surefire Plugin trong tài liệu, ghi lại **User Property** chính xác và chỉ rõ có tác dụng ở goal nào.
9. Một đồng nghiệp nói “thêm `-Dproject.version=2.0` là đủ phát hành bản 2.0” trong khi POM cố định `<version>1.0.0-SNAPSHOT</version>`. Hãy giải thích vì sao nhận định đó thiếu căn cứ và cách kiểm chứng tọa độ artifact.

## 14. Tóm tắt và tài liệu tham khảo

Ghi nhớ ba quy tắc: **(1)** dùng `-Dkey=value` để cung cấp một user property **trong lần chạy Maven**; **(2)** property chỉ có tác dụng khi Maven/model/plugin/resource thực sự sử dụng nó; **(3)** với các cấu hình kết cấu, profile, settings và giá trị plugin cố định, cần kiểm tra cách hỗ trợ override thay vì giả định `-D` thay đổi mọi thứ.

Nguồn tài liệu chính thức:
- [Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Maven Compiler Plugin — Setting release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Help Plugin — Goals and Usage](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html)
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
