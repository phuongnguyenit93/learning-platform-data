# Phân biệt thuộc tính được khai báo với tham số plugin thực sự hỗ trợ trong Maven

## 1. Vấn đề: khai báo property không đồng nghĩa plugin sẽ sử dụng

Maven cho phép đặt thuộc tính trong `<properties>` của `pom.xml`, qua dòng lệnh `-Dkey=value`, từ parent/profile và một số nguồn khác. Nhưng **Maven nhận một thuộc tính không có nghĩa bất kỳ plugin nào cũng hiểu hoặc sử dụng nó**. Plugin chỉ thay đổi hành vi khi có mối liên kết thật sự giữa thuộc tính đó với một **tham số (parameter) của goal** hoặc với cấu hình mà plugin đọc.

Ví dụ:

~~~xml
<properties>
    <build.java.level>17</build.java.level>
    <skip.my.tests>true</skip.my.tests>
</properties>
~~~

Hai property trên đều hợp lệ dưới `<project>`. Tuy nhiên:

- `build.java.level` **không phải tên user property chuẩn** của tham số `release` trong Maven Compiler Plugin. Nếu không có cấu hình nối `build.java.level` đến `<release>`, giá trị `17` không tự chọn Java release.
- `skip.my.tests` **không phải tên user property chuẩn** của tham số `skipTests` trong Maven Surefire Plugin. Khai báo `true` không tự làm Surefire bỏ qua test.
- Ngược lại, Maven Compiler Plugin hỗ trợ **`maven.compiler.release`** cho tham số `release`; Surefire hỗ trợ **`skipTests`** cho tham số cùng tên, với phiên bản plugin tương ứng.
- Có thể **tự đặt tên property** như `build.java.level` hoặc `skip.my.tests`, rồi tham chiếu tường minh từ `<configuration>` để tạo kết nối. Đây là cơ chế khác với việc plugin trực tiếp công bố tên user property.

**Câu hỏi trọng tâm:** “Property này đã tồn tại trong Maven chưa?” và “Goal của plugin có thực sự sử dụng property này không?” là **hai phép kiểm tra độc lập**.

## 2. Phân biệt bốn khái niệm liên quan

| Khái niệm | Ví dụ | Ai đọc và tác dụng |
| --- | --- | --- |
| **POM property** | `<maven.compiler.release>17</maven.compiler.release>` trong `<properties>` | Giá trị trong model Maven; có thể được nội suy bằng `${maven.compiler.release}`. |
| **Maven user property** | `mvn -Dmaven.compiler.release=17 compile` | Giá trị cho lần chạy Maven từ CLI; có thể được plugin/POM/profile dùng. |
| **Plugin goal parameter** | `release` của goal `compiler:compile`; `skipTests` của `surefire:test` | Tham số thực tế do plugin định nghĩa; có tên, kiểu dữ liệu, giá trị mặc định, ràng buộc và quy tắc gán. |
| **Tên User Property mà goal hỗ trợ** | `maven.compiler.release` cho `release`; `skipTests` cho `skipTests` | Tên được mô tả trong tài liệu goal/plugin descriptor, cho phép tham số đọc giá trị theo cơ chế plugin. |
| **POM plugin configuration** | `<configuration><release>17</release></configuration>` | Cách khai báo trực tiếp giá trị tham số trong `build/plugins` hoặc `pluginManagement` tùy trường hợp. |

Vì thế, **không phải cứ tên XML trùng nhau thì CLI property tương ứng được hỗ trợ**. Tham số `<release>` có tên `release` nhưng user property chính thức là `maven.compiler.release`, không phải mặc định `release`. Tương tự, có tham số tên `outputDirectory` nhưng user property của nó có thể mang tên khác hoặc không tồn tại.

Trong tài liệu do Maven Plugin Plugin sinh ra, phần thông tin một tham số thường có:

- **Name**: tên XML dùng trong `<configuration>`, ví dụ `release`.
- **Type**: `String`, `boolean`, `File`, `List` hoặc kiểu khác.
- **Default**: giá trị plugin dùng khi không được cấu hình ở nơi phù hợp.
- **Required / Read-only**: ràng buộc của tham số.
- **User Property**: tên CLI property được ánh xạ trực tiếp nếu plugin/goal công bố.
- **Since**: phiên bản plugin bắt đầu hỗ trợ tham số khi có thông tin.

Cần xem **đúng plugin, đúng goal và đúng phiên bản**: `compiler:compile` có tập tham số khác `surefire:test`, và các phiên bản của cùng một plugin có thể thêm, đổi hoặc bỏ tham số.

## 3. Cơ chế dữ liệu đi từ property tới plugin

Maven có thể nhận một giá trị ở nhiều nguồn, nhưng cần một “đường dẫn” để nó ảnh hưởng tới plugin:

~~~text
[1] Khai báo giá trị
    <properties> ... </properties>
    hoặc mvn -Dkey=value ...
                 |
                 v
[2] Maven model/session nhận biết property key
                 |
          +------+---------------------------+
          |                                  |
          v                                  v
[3a] Plugin goal có User Property=key?  [3b] POM có <parameter>${key}</parameter>?
          |                                  |
          +------------------+---------------+
                             |
                             v
[4] Goal có parameter được gán giá trị, nếu execution/goal thực sự chạy
                             |
                             v
[5] Plugin kiểm tra kiểu/ràng buộc và thực hiện hành vi tương ứng
~~~

Nếu **không có đường dẫn 3a hoặc 3b** (hay một cơ chế tham chiếu khác như profile/resource filtering), chỉ khai báo property chưa chắc tạo ra thay đổi hành vi. Một số plugin còn có cấu hình tường minh, giá trị mặc định, logic điều kiện và ưu tiên riêng; không được giả định `-D` luôn thắng mọi `<configuration>`.

Một property có thể có ích **mà không là User Property của plugin**. Ví dụ Maven Resources Plugin có cơ chế **resource filtering** để thay biểu thức `${demo.message}` trong tệp resource từ POM/CLI; bản thân `demo.message` không cần nằm trong danh sách user property của goal `resources:resources`. Đây là đường đi thông qua nội suy và dữ liệu đầu vào, không phải “plugin nhận tham số tên demo.message”.

Ngược lại, một property có thể tồn tại và hiển thị được bằng `help:evaluate` nhưng **không khiến goal nào thay đổi**, nếu không có ai sử dụng nó.

## 4. Một bảng ví dụ đúng – sai dễ nhận ra

| Mục tiêu | Property/parameter đúng | Ví dụ không tự có hiệu lực | Tại sao |
| --- | --- | --- | --- |
| Compile theo Java release 17 | `-Dmaven.compiler.release=17` hoặc `<release>17</release>` của Compiler Plugin | `-Djava.level=17` | `java.level` là tên tự đặt; cần POM nối nó với `release`. |
| Bật cảnh báo compiler | `-Dmaven.compiler.showWarnings=true` hoặc cấu hình `<showWarnings>true</showWarnings>` | `-DshowWarnings=true` | Tên XML parameter không nhất thiết là User Property. |
| Bỏ qua thực thi unit test | `-DskipTests=true` với Surefire | `-Dskip.my.tests=true` | Surefire không tự đọc `skip.my.tests`. |
| Chọn unit test theo tên | `-Dtest=CalculatorTest` với Surefire | `-DselectedTest=CalculatorTest` | `selectedTest` cần có ánh xạ riêng nếu muốn dùng. |
| Bỏ cả compile và thực thi test | `-Dmaven.test.skip=true` với các plugin hỗ trợ | `-DskipAllJavaTests=true` | Không có công tắc Maven chung tự hiểu mọi tên tùy ý. |
| Nội suy giá trị build vào resource | `${demo.message}` trong resource đã bật filtering | Chỉ định `-Ddemo.message=hi` nhưng resource không lọc và không có tham chiếu | Property được lưu, không có bước tiêu thụ giá trị. |
| Kích hoạt profile từ property | `<activation><property><name>env.name</name>...</property></activation>` | Chỉ đặt `-Denv.name=qa` trong dự án không có profile liên quan | Không tồn tại điều kiện kích hoạt thì không có profile cần bật. |

Tên trong bảng dựa trên các plugin/goal đã nêu; với mỗi dự án thực tế phải xác minh version và configuration cuối cùng. `-DskipTests=true` không phải lệnh thần kỳ tắt mọi loại test trong tất cả plugin; chẳng hạn plugin integration test có thể dùng tham số khác (ví dụ `skipITs` ở Failsafe).

## 5. Đọc tài liệu goal: User Property là bằng chứng quan trọng

Đừng đoán alias CLI từ tên property trong blog hoặc tên XML. Chọn **phiên bản plugin mà dự án thực sự chạy** và mở trang mô tả goal (thường có hậu tố `-mojo.html`). Ví dụ:

- [Maven Compiler Plugin — compiler:compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html): tham số `release` có **User Property: maven.compiler.release**.
- [Maven Surefire Plugin — surefire:test](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html): tham số `skipTests` có **User Property: skipTests**; tham số `skip` còn liên quan đến `maven.test.skip`.
- [Maven Help Plugin — help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html): liệt kê metadata và các tham số của plugin/goal.

Từ thư mục có `pom.xml`, có thể dùng **Help Plugin** để xem metadata plugin mà không sửa POM:

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0 -Dgoal=compile -Ddetail
~~~

Trong phần mô tả `release`, cần tìm thông tin tương ứng với **User Property: maven.compiler.release**. Với Surefire:

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-surefire-plugin:3.5.2 -Dgoal=test -Ddetail
~~~

Tìm `skipTests` và `User Property: skipTests`. Đối số `-Ddetail` ở đây điều khiển **Help Plugin** để hiển thị thông tin chi tiết; không có nghĩa mọi plugin đều hỗ trợ property `detail`.

Lưu ý:

1. `-Dplugin=...` chọn plugin để Help Plugin mô tả; **không** tự chạy goal compile hoặc test.
2. `-Dgoal=compile` chọn **goal cần xem**, không phải phase build đang chạy.
3. `-Ddetail` chỉ yêu cầu Help Plugin liệt kê thêm chi tiết, không thay cấu hình Compiler Plugin.
4. Nếu chưa tải được plugin/descriptors do mạng hoặc repository, đó là lỗi resolution, không chứng tỏ tham số không tồn tại.
5. Một số tham số có **không có User Property**. Chúng vẫn có thể được điều chỉnh qua `<configuration>` nếu plugin cho phép.

Cú pháp `<parameter>` và `User Property` không phải luôn tương đương. **Đây là cách xác minh quan trọng nhất trước khi viết một lệnh `-D...` vào README hoặc CI.**

## 6. Phân biệt parameter name và user-property name

Hai câu lệnh dưới đây **không tương đương một cách mặc định**:

~~~bash
mvn '-Drelease=17' compile
mvn '-Dmaven.compiler.release=17' compile
~~~

Với Maven Compiler Plugin, tên User Property của tham số `release` là `maven.compiler.release`. Vì vậy lệnh thứ hai dùng tên được công bố. Lệnh thứ nhất **chỉ đặt Maven property tên release**; nó không tự có quan hệ với tham số `release` trừ khi POM/plugin tạo một ánh xạ riêng.

Cách đặt tham số trực tiếp trong POM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
~~~

Đây là **mảnh XML đặt trong `<build><plugins>`**. Nó gán tham số XML `release` rõ ràng. Nhưng cách này khác với việc khai báo một property tự đặt trong `<properties>`.

Nếu nhóm muốn dùng tên riêng `build.java.level`, hãy **nối rõ bằng biểu thức**:

~~~xml
<properties>
    <build.java.level>17</build.java.level>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>${build.java.level}</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **mảnh các phần tử bên trong `<project>`**, chưa phải POM độc lập. Sau khi thêm, `mvn -Dbuild.java.level=17 compile` có thể điều khiển tham số `release` thông qua nội suy POM. Nếu không có dòng `<release>${build.java.level}</release>`, việc khai báo property không bảo đảm Compiler Plugin đọc nó.

Nếu một plugin đã có `<configuration><release>11</release></configuration>` ghi giá trị cố định, đừng tự khẳng định `-Dmaven.compiler.release=17` luôn override cấu hình tường minh đó. **Cấu hình plugin và cách plugin lấy parameter value có quy tắc ưu tiên**; hãy xem effective POM và log goal. Muốn CLI override rõ ràng, nên thiết kế cấu hình dùng biểu thức property thích hợp thay vì hard-code.

## 7. Khai báo properties trong parent/profile không tự chạy plugin

Trong parent POM hoặc một profile, bạn có thể thấy:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <skipTests>true</skipTests>
    <demo.flag>staging</demo.flag>
</properties>
~~~

Các giá trị này được đưa vào mô hình phù hợp theo quy tắc kế thừa và profile activation. Nhưng:

- `maven.compiler.release` có ý nghĩa với Compiler Plugin ở goal hỗ trợ và nếu goal đó thực thi.
- `skipTests` có ý nghĩa với Surefire theo tham số được công bố; chạy `mvn test` mới có tác vụ unit test để skip.
- `demo.flag` chỉ tồn tại dưới dạng property; chỉ có tác dụng khi POM, plugin, profile hoặc resource tham chiếu tới nó.
- Có thể có plugin được khai báo trong `pluginManagement` nhưng **chưa được kích hoạt/chạy** trong lifecycle của module đó. Property không tự kích hoạt plugin.
- Một property đặt trong profile chỉ được tính nếu profile/hiệu ứng tương ứng được kích hoạt theo điều kiện thực tế.

**Mô hình kế thừa POM**, **nguồn property** và **tham số của plugin goal** là ba vấn đề khác nhau. Chúng phối hợp với nhau nhưng không thay thế nhau.

Ví dụ profile chỉ hoạt động khi property có giá trị `ci`:

~~~xml
<profiles>
    <profile>
        <id>ci-profile</id>
        <activation>
            <property>
                <name>deploy.env</name>
                <value>ci</value>
            </property>
        </activation>
        <properties>
            <demo.flag>strict</demo.flag>
        </properties>
    </profile>
</profiles>
~~~

Dùng `mvn -Ddeploy.env=ci help:active-profiles` để kiểm tra điều kiện. Đây là **mảnh XML trong `<project>`**. Có profile active và `demo.flag=strict` vẫn không có nghĩa mọi plugin đều biết phải làm gì với `demo.flag`; cần xem plugin hoặc mục `<configuration>` liên quan.

## 8. Ví dụ Java 17 chạy được: property có nhưng test không bị skip

Ví dụ này cho thấy ba trường hợp: (a) property tùy ý đã khai báo nhưng không điều khiển Surefire, (b) User Property chính thức `skipTests` điều khiển Surefire, (c) property `demo.message` được Maven Resources Plugin sử dụng thông qua **filtering** chứ không phải một tham số plugin tên `demo.message`.

Tạo cấu trúc:

~~~text
parameter-contract-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/org/example/MessageApp.java
    │   └── resources/app.properties
    └── test/
        └── java/org/example/MessageAppTest.java
~~~

### 8.1. Tệp pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>parameter-contract-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <demo.message>Hello default</demo.message>
        <demo.skip>false</demo.skip>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Trong POM này:

- `maven.compiler.release=17` là tên user property mà Compiler Plugin hiểu khi thực thi `compiler:compile`.
- `demo.message` là property tùy ý **được tham chiếu bởi resource** có bật filtering, nên thay giá trị qua CLI sẽ thay file output.
- `demo.skip` là một property tùy ý, **không có liên kết nào** tới tham số `skipTests` của Surefire trong POM này.
- Surefire Plugin phiên bản `3.5.2` dùng `skipTests` và `maven.test.skip` theo ý nghĩa riêng. Dùng `-Ddemo.skip=true` không phải tên alias chính thức của `skipTests`.

### 8.2. Resource app.properties

Tệp `src/main/resources/app.properties`:

~~~properties
message=${demo.message}
~~~

Cơ chế resource filtering sẽ thay `${demo.message}` bằng giá trị tương ứng khi xử lý resource, ví dụ vào `target/classes/app.properties`. Nếu không bật `<filtering>true</filtering>` hoặc không dùng biểu thức, property sẽ không tự làm file thay đổi.

### 8.3. Java 17: MessageApp.java

Tệp `src/main/java/org/example/MessageApp.java`:

~~~java
package org.example;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class MessageApp {
    private MessageApp() {
    }

    public record Message(String value) {
    }

    public static Message readMessage() {
        Properties properties = new Properties();
        try (InputStream input =
                     MessageApp.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            properties.load(new InputStreamReader(input, StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new IllegalStateException("Cannot read app.properties", e);
        }
        return new Message(properties.getProperty("message"));
    }

    public static void main(String[] args) {
        System.out.println("message=" + readMessage().value());
    }
}
~~~

Dùng `record` giúp ví dụ cần Java 17 (tính năng chính thức từ Java 16), qua đó có thể quan sát tác động của cấu hình Compiler Plugin `maven.compiler.release`. Mã Java không phụ thuộc thư viện bên ngoài.

### 8.4. JUnit test: MessageAppTest.java

Tệp `src/test/java/org/example/MessageAppTest.java`:

~~~java
package org.example;

import static org.junit.jupiter.api.Assertions.assertFalse;
import org.junit.jupiter.api.Test;

class MessageAppTest {
    @Test
    void filteredMessageIsPresent() {
        assertFalse(MessageApp.readMessage().value().isBlank());
    }
}
~~~

Test này **vẫn hợp lệ** dù `demo.message` là `Hello default` hoặc `Hello Maven`. Nó dùng JUnit Jupiter `5.11.4`, version đã khai báo rõ trong POM.

### 8.5. Lần chạy A: property demo.skip tồn tại nhưng không bỏ qua test

Từ project root có `pom.xml`, dùng Maven và JDK 17+ tương thích:

~~~bash
mvn -B -ntp '-Ddemo.skip=true' clean verify
java -cp target/classes org.example.MessageApp
~~~

Với POM được cung cấp, kết quả:

- Maven nhận user property `demo.skip=true`. Khi chạy `help:evaluate`, có thể xem được giá trị đó.
- **Surefire vẫn chạy unit test** vì POM không nối `demo.skip` với tham số `skipTests` và `demo.skip` không phải user property trực tiếp của goal.
- Nếu test chạy thành công, Maven tạo báo cáo trong `target/surefire-reports/`; số test kỳ vọng là **1**.
- **Stdout chính xác của riêng lệnh `java`** là:

~~~text
message=Hello default
~~~

Lệnh Maven có log riêng tùy máy/plugin, không dùng đoạn stdout ứng dụng để mô tả toàn bộ log Maven.

### 8.6. Lần chạy B: đúng user property skipTests

~~~bash
mvn -B -ntp '-DskipTests=true' clean verify
java -cp target/classes org.example.MessageApp
~~~

Ở đây Surefire nhận tham số `skipTests=true` qua user property hỗ trợ. Unit test không được thực thi; cần nhìn log Surefire thay vì nhầm với việc bỏ qua cả các plugin build khác. `maven.compiler.release=17` vẫn dùng để compile mã chính, và resource vẫn được xử lý.

Stdout của ứng dụng sau build:

~~~text
message=Hello default
~~~

Vì dùng `clean`, báo cáo test cũ ở `target/surefire-reports/` không nên được sử dụng làm bằng chứng cho lần chạy B. Nếu cần xác minh, xem log và file được tạo sau build hiện tại.

### 8.7. Lần chạy C: property tùy ý thực sự ảnh hưởng qua resource filtering

~~~bash
mvn -B -ntp '-Ddemo.message=Hello Maven' clean package
java -cp target/classes org.example.MessageApp
~~~

Stdout của riêng lệnh Java:

~~~text
message=Hello Maven
~~~

Sự khác biệt này **không chứng minh Resources Plugin có parameter tên demo.message**. Plugin đang đọc file resource và thực hiện filtering với biểu thức `${demo.message}`. Đây là ví dụ property được tiêu thụ **qua dữ liệu đầu vào**, không phải user property alias được ghi trong goal descriptor.

Có thể thử thêm:

~~~bash
mvn -B -ntp '-Ddemo.unused=abc' clean package
java -cp target/classes org.example.MessageApp
~~~

Trong đúng dự án mẫu, property `demo.unused` không được tham chiếu và không có plugin nào được cấu hình dùng nó, nên output vẫn là:

~~~text
message=Hello default
~~~

Không suy rộng rằng mọi property tự đặt đều “vô hiệu”: nó có thể kích hoạt profile, được template đọc, hoặc được plugin khác sử dụng ở dự án khác.

### 8.8. Khi nào -Dmaven.compiler.release thực sự khác tên property tự đặt?

Vì mã mẫu dùng `record`, biên dịch yêu cầu release hỗ trợ record. Với Maven Compiler Plugin `3.13.0`:

~~~bash
mvn -B -ntp '-Dmaven.compiler.release=17' clean compile
~~~

sử dụng property được công bố và có thể biên dịch thành công với JDK phù hợp. Nếu một người chỉ thay thành:

~~~bash
mvn -B -ntp '-Dbuild.java.level=17' clean compile
~~~

trong **POM mẫu hiện tại**, `build.java.level` không được sử dụng, nên release vẫn đến từ `maven.compiler.release=17` khai báo trong POM; không có thay đổi vì tên property tự đặt. Để custom property điều khiển release, cần thêm ánh xạ `<release>${build.java.level}</release>` trong cấu hình compiler.

## 9. Biến property tùy ý thành tham số plugin bằng cấu hình tường minh

Để chính property `demo.skip` của ví dụ có tác dụng, bổ sung `<configuration>` **vào plugin maven-surefire-plugin đã tồn tại** trong `pom.xml`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <skipTests>${demo.skip}</skipTests>
    </configuration>
</plugin>
~~~

Đây là **đoạn thay thế khai báo plugin Surefire cũ**, không thêm một plugin thứ hai cùng tọa độ vào danh sách `build/plugins`. Giữ property mặc định:

~~~xml
<properties>
    <demo.skip>false</demo.skip>
</properties>
~~~

Cần đặt/mở rộng block `properties` đã có trong POM, không thêm block thứ hai trùng cấp. Sau đó:

~~~bash
mvn -B -ntp '-Ddemo.skip=true' clean verify
~~~

Vì Maven nội suy `${demo.skip}` thành `true`, plugin nhận cấu hình `skipTests=true` và bỏ qua test. Đây là ví dụ **property tùy ý → biểu thức POM → parameter thực sự**, không phải vì Surefire có sẵn alias `demo.skip`.

Giải thích chính xác:

- **Trước khi thêm ánh xạ:** `-Ddemo.skip=true` là property có mặt trong Maven, nhưng không ảnh hưởng đến `skipTests`.
- **Sau khi thêm ánh xạ:** `-Ddemo.skip=true` được POM dùng để cung cấp giá trị cho `<skipTests>`, một tham số có thật của Surefire.
- **Dù không dùng tên User Property chính thức**, property vẫn có tác dụng nhờ cấu hình trung gian rõ ràng.
- Nếu cấu hình plugin có cả literal và biểu thức khác nhau, hoặc project nhận cấu hình từ parent/profile, phải kiểm tra effective POM và cách plugin ưu tiên giá trị; không kết luận một tên CLI luôn override cấu hình cố định.

Cách quản lý thông dụng khác là dùng luôn `<skipTests>${skipTests}</skipTests>` hoặc property chính thức `skipTests`, nhưng việc tạo alias dự án riêng chỉ nên thực hiện khi nhóm thực sự cần một tên khác.

## 10. Ba phép kiểm tra: property tồn tại, plugin khai báo hỗ trợ, goal thực thi

Khi một lệnh `-D...` không tạo ra kết quả mong muốn, hãy kiểm tra lần lượt ba điều.

### 10.1. Kiểm tra property có giá trị hay không

~~~bash
mvn -q '-Ddemo.skip=true' -Dexpression=demo.skip -DforceStdout help:evaluate
~~~

Nếu Help Plugin chạy thành công, giá trị đánh giá kỳ vọng là:

~~~text
true
~~~

Nhưng **`help:evaluate` chỉ chứng minh Maven thấy property**, không chứng minh Surefire đọc nó hoặc có goal test nào đã chạy.

### 10.2. Kiểm tra tham số và tên User Property plugin hỗ trợ

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-surefire-plugin:3.5.2 -Dgoal=test -Ddetail
~~~

Xem tham số `skipTests`, kiểu dữ liệu `boolean` và User Property `skipTests`. Làm tương tự cho plugin khác, nhớ xác định goal và version chính xác.

### 10.3. Kiểm tra execution, cấu hình và hành vi thực

~~~bash
mvn help:effective-pom
mvn -B -ntp clean test
~~~

- `help:effective-pom` cho thấy cấu hình được ghép từ POM, parent, profile và các khai báo có liên quan. Nó hữu ích để tìm `<skipTests>`, `<release>`, `<plugins>`/`<pluginManagement>` và execution đang được cấu hình.
- Nó **không thay thế kiểm chứng runtime**: một plugin trong `pluginManagement` chưa chắc chạy; một parameter hiển thị trong cấu hình chưa chắc goal được thực thi.
- `mvn clean test` giúp phân biệt kết quả cũ với lần chạy mới, nhưng nhớ đọc log và báo cáo test. Test bị skip có thể không tạo báo cáo mới.
- Có thể thêm `-X` để xem thông tin debug về goal/parameter, **nhưng chỉ làm trên log an toàn**: output debug có thể chứa đường dẫn nội bộ, thông số JVM, repository, giá trị property nhạy cảm. Không đăng public nguyên log khi chưa loại bỏ secret.

**Trình tự ngắn:** property có tồn tại? → goal có User Property hoặc POM mapping tương ứng? → goal đã thực sự chạy? → kết quả thực tế đúng chưa?

## 11. Những trường hợp gây nhầm lẫn nâng cao

### 11.1. Tên XML giống tham số nhưng CLI không tự khớp

`<release>17</release>` là tên parameter XML; `-Drelease=17` không được bảo đảm là alias CLI. Tương tự, `<showWarnings>true</showWarnings>` không đồng nghĩa `-DshowWarnings=true`. Cần tìm dòng **User Property** theo goal và version.

### 11.2. Property đúng tên nhưng bị cấu hình plugin chi phối

Parent POM có thể đặt:

~~~xml
<configuration>
    <skipTests>false</skipTests>
</configuration>
~~~

Đây là mảnh configuration cần gắn vào **plugin Surefire**. Nếu child truyền `-DskipTests=true`, cách plugin xử lý còn phụ thuộc vào giá trị cấu hình tường minh, cách model nội suy và injection. Đừng áp dụng máy móc quy tắc “CLI luôn ghi đè bất kỳ XML nào”. Tốt nhất xây dựng một đầu mối rõ ràng, ví dụ `<skipTests>${demo.skip}</skipTests>`, rồi kiểm thử.

### 11.3. Plugin được quản lý nhưng chưa chạy

`pluginManagement` có thể quản lý version và default config cho plugin nhưng **không tự kích hoạt một goal tùy ý**. Một plugin/goal cần được gọi trực tiếp, được khai báo với execution hoặc có lifecycle binding phù hợp thì mới thực hiện công việc.

### 11.4. Profile thay đổi cấu hình mà không phải User Property alias

`-Ddeploy.env=ci` có thể làm profile `ci` active và profile đó thêm cấu hình plugin. Lúc này việc property tác động gián tiếp **không chứng minh plugin có tham số `deploy.env`**.

### 11.5. Surefire có thể chuyển user properties sang JVM chạy test

Một số phiên bản Surefire có cơ chế **promoteUserPropertiesToSystemProperties** (phụ thuộc plugin/version/configuration), đưa Maven user properties vào JVM/provider chạy test. Vì vậy property tự đặt có thể được **mã test đọc dưới dạng system property** trong vài cấu hình dù nó **không phải alias của `skipTests`**. Hai khái niệm “plugin nhận thuộc tính để cấu hình parameter” và “plugin chuyển property sang môi trường test” phải phân biệt. Khi cần biết JVM nhận gì, xem tài liệu đúng phiên bản và quan sát bằng test được kiểm soát.

### 11.6. Property từ parent, settings và profile có thể bị ghi đè

Maven xây dựng mô hình cuối từ parent, POM con, profile, settings, CLI và các giá trị do plugin bổ sung. Mỗi nguồn có quy tắc riêng; khi nhiều nơi cùng khai báo một tên, cần đọc model hiệu lực ở đúng môi trường. User property thường được dùng để ghi đè POM property cùng tên trong ngữ cảnh nội suy, nhưng **không thể dùng một quy tắc ưu tiên chung cho mọi tham số, mọi profile và mọi plugin**.

### 11.7. -D của Maven không giống -D của ứng dụng Java

~~~text
mvn -Ddemo.message=Hello package
    -> User property của Maven khi build.

java -Druntime.mode=dev -cp target/classes org.example.MessageApp
    -> System property của JVM chạy MessageApp.
~~~

Một lần chạy Maven có thể tạo resource hoặc plugin truyền property cho JVM con, nhưng việc đó cần cơ chế cụ thể. Đừng mặc định `System.getProperty("demo.message")` của ứng dụng sau build nhận giá trị từ `mvn -Ddemo.message=...`. Tương tự, property `maven.compiler.release` chọn mức release dùng cho biên dịch chứ không tự chọn/cài đặt JDK.

## 12. Kiểu dữ liệu, giới hạn và lỗi chuyển đổi tham số

Plugin parameter có **kiểu dữ liệu thật**. Ví dụ:

- `skipTests` của Surefire nhận giá trị boolean.
- `release` của Compiler Plugin là chuỗi biểu diễn mức release được compiler hỗ trợ.
- Một số tham số khác là `File`, `List`, `Map` hoặc cần cú pháp riêng theo plugin.

Một property có thể được Maven nhận **dưới dạng chuỗi**, nhưng plugin vẫn thất bại khi cố chuyển nó sang kiểu dữ liệu mong muốn.

Ví dụ minh họa:

~~~bash
mvn -DskipTests=abc test
mvn -Dmaven.compiler.release=not-a-java-release compile
~~~

Đây là **lệnh minh họa lỗi**, không phải lệnh nên chạy trong pipeline. Hành vi lỗi cụ thể phụ thuộc plugin/Maven/compiler/version. Điểm cần nhớ là: property tồn tại **không** đồng nghĩa giá trị hợp lệ; tên đúng nhưng sai kiểu vẫn có thể làm build thất bại.

Ngay cả khi kiểu dữ liệu hợp lệ, giá trị vẫn có thể không hỗ trợ trong môi trường hiện tại. `-Dmaven.compiler.release=21` trên JDK không hỗ trợ release 21 không biến JDK đó thành JDK 21.

## 13. Đừng nhầm Maven property với “cờ toàn cục” của Maven

Có các options thật sự của Maven CLI như `-P` (chọn profile), `-o` (offline), `-B` (batch mode), `-pl` (chọn module). Các options này điều khiển Maven ở mức CLI/reactor.

Ngược lại, `-DskipTests=true` thường là **plugin-related user property**, không phải một cờ mặc định được Maven Core định nghĩa để bỏ qua mọi loại kiểm thử trong mọi hệ thống. `-Dmaven.compiler.release=17` cũng không phải lệnh Maven Core cài JDK 17.

Ví dụ:

~~~bash
mvn -B -ntp '-DskipTests=true' verify
mvn -Pci '-Dbuild.java.level=17' verify
~~~

`-B`, `-ntp`, `-Pci` là các options Maven CLI; các `-D...` chỉ đặt property. Phần việc diễn ra sau đó tùy POM và plugin đang thực thi.

**Quy tắc đọc tài liệu:** Khi tài liệu ghi “User Property: X” thì đó là bằng chứng để dùng `-DX=value` với **goal/phiên bản tương ứng**. Nếu tài liệu chỉ có tham số XML `<X>`, đừng tự suy luận tên `X` được nhận qua CLI. Nếu không có liên kết, dùng `<configuration><X>${your.property}</X></configuration>` theo kiểu dữ liệu mà plugin hỗ trợ.

## 14. CI, bảo mật và khả năng tái lập

Trong CI, việc đặt `-Dfoo=bar` không có kiểm chứng rất dễ gây cảm giác sai rằng hệ thống đang bật một “mode” nào đó. Ví dụ:

~~~yaml
name: Verify with explicit Maven parameters
on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Verify
        run: ./mvnw -B -ntp '-Dmaven.compiler.release=17' verify
~~~

Đây là workflow minh họa **cho repository đã commit Maven Wrapper** và có `mvnw` thực thi được trên runner Linux. Phân biệt:

- `setup-java` chọn JDK; thuộc tính `maven.compiler.release` chỉ điều khiển compiler khi plugin hỗ trợ.
- `./mvnw` giúp cố định phiên bản Maven bằng Wrapper của dự án.
- `verify` chạy lifecycle theo POM; nếu project đã gắn Surefire, Failsafe hay các plugin khác, chúng thực thi theo các binding riêng.
- Không thêm các property tưởng tượng như `-DnoTestsAnywhere=true` để thay cho cấu hình plugin đúng.
- Khi nâng version plugin, cần review lại **User Property, default, semantics, deprecation** của các parameter liên quan.

Không nên truyền secret `-Dpassword=...` ở dòng lệnh: nó có thể lộ qua process list, lịch sử shell, CI logs hoặc thông tin debug. Dùng secret manager, credentials thông qua `settings.xml`/cơ chế environment được thiết kế cho công cụ, và tránh in `help:evaluate` hoặc `-X` với property nhạy cảm.

Dùng lệnh `-D` chỉ trong đúng phạm vi task đang giải quyết; nếu property là convention ổn định cho cả nhóm, cân nhắc quản lý version/cấu hình trong POM parent hoặc profile thay vì nhớ thủ công trên mỗi máy.

## 15. Bảng quyết định: khi nào dùng property nào?

| Bạn muốn gì? | Lựa chọn phù hợp | Cần xác minh |
| --- | --- | --- |
| Đặt tham số plugin có User Property được tài liệu công bố | `-Dten-duoc-cong-bo=gia-tri` hoặc property cùng tên khi phù hợp | Plugin goal/version; default và XML configuration. |
| Đặt tham số XML của plugin nhưng không có User Property | `<configuration><tenThamSo>gia-tri</tenThamSo></configuration>` | Tham số được plugin hỗ trợ ở goal đó và có đúng kiểu. |
| Điều khiển tham số XML bằng tên property riêng | `<tenThamSo>${ten.property.rieng}</tenThamSo>` | Property được nội suy trong đúng ngữ cảnh/execution. |
| Chỉ muốn một biến để dùng trong resource/POM | `<properties>` và tham chiếu `${key}`, kết hợp filtering nếu cần | Có thành phần thực sự tiêu thụ biến. |
| Chọn profile | `-Pid` hoặc activation trong POM | Profile có id/điều kiện chính xác. |
| Chọn phiên bản Java compile | Compiler Plugin `release` / `maven.compiler.release` | JDK và Compiler Plugin hỗ trợ mức release. |
| Chọn phiên bản JDK chạy Maven | Cấu hình môi trường hoặc CI/JDK toolchain | Không nhầm với Java release property. |
| Kiểm tra plugin hỗ trợ parameter nào | `help:describe -Ddetail` hoặc trang `goal-mojo.html` | Đúng plugin/goal/version. |
| Kiểm tra property đã được Maven nhận | `help:evaluate` | Property tồn tại **chưa chứng minh** plugin đã sử dụng. |
| Xác minh plugin thực thi và nhận cấu hình | Effective POM, log goal, output/test | Không dựa chỉ vào việc build nhận cú pháp CLI. |

## 16. Các lỗi thường gặp và quy trình gỡ lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `-Djava.level=17` nhưng compiler vẫn dùng release khác | Tên không phải User Property và POM chưa nối alias. | Dùng `maven.compiler.release` hoặc `<release>${java.level}</release>`. |
| Đặt `<skip.my.tests>true</skip.my.tests>` nhưng unit test vẫn chạy | Property được khai báo, Surefire không dùng nó. | Dùng `skipTests` hoặc thêm `<skipTests>${skip.my.tests}</skipTests>`. |
| `-DskipTests=true` nhưng integration test vẫn chạy | Failsafe có tham số/phiên bản riêng. | Xem đúng Failsafe `skipITs`, `maven.test.skip` và cấu hình hiện tại. |
| `help:evaluate` cho ra đúng giá trị nhưng build không đổi | Chỉ xác minh sự tồn tại; chưa xác minh consumer. | Xem goal descriptor, POM mapping và log thực thi. |
| `help:describe` không thấy tên property mong đợi | Parameter không hỗ trợ alias đó hoặc chọn sai goal/version. | Tra mục “User Property”, kiểm tra plugin/goal/version. |
| Child không được áp dụng cấu hình parent | Plugin management chưa chạy, override từ child hoặc profile inactive. | Xem effective POM đúng module và activation. |
| Build fail với boolean/string/path dù property có giá trị | Sai kiểu/ràng buộc plugin hoặc shell quote tách sai. | Kiểm tra type trong mojo docs, quote theo shell, dùng giá trị hợp lệ. |
| Dùng `-Dfoo=bar` nhưng Java app không đọc được | Đó là Maven user property, không tự là JVM system property của ứng dụng. | Truyền `java -Dfoo=bar` lúc chạy hoặc cấu hình plugin chuyển giá trị. |
| Output thay đổi sau khi sửa property nhưng không biết vì sao | Có profile, filtering, inherited configuration hoặc plugin khác dùng property. | Tìm tham chiếu `${foo}`, active profiles, effective POM, log goal. |
| Mỗi máy dùng behavior khác nhau | Maven/plugin/JDK/CI khác version hoặc profile/setting khác. | Pin phiên bản cần thiết, so effective POM và log trên cùng môi trường. |

Quy trình 5 bước:

1. Ghi rõ **plugin + version + goal** đang chạy, không chỉ tên phase như `compile` hay `test`.
2. Dùng `help:evaluate` để kiểm tra giá trị property nếu cần (không in secret).
3. Dùng `help:describe -Ddetail` hoặc tài liệu goal để xác minh **tên parameter, User Property, type, default**.
4. Mở `help:effective-pom` của đúng module và profile để tìm cấu hình được khai báo/ghi đè/nối biểu thức.
5. Chạy goal/build với output sạch, kiểm tra log, report và artifact; chỉ kết luận plugin đã sử dụng property khi có bằng chứng hành vi.

## 17. Câu hỏi tự kiểm tra

1. **POM khai báo `<foo>true</foo>` trong `<properties>`, mọi plugin có hiểu `foo` không?**  
   Không. Property tồn tại; plugin chỉ chịu ảnh hưởng nếu có alias được công bố, cấu hình nội suy, profile, resource filtering hoặc cơ chế sử dụng khác.

2. **Compiler Plugin có parameter `<release>`. `-Drelease=17` và `-Dmaven.compiler.release=17` có mặc định tương đương?**  
   Không. User Property được công bố của tham số `release` là `maven.compiler.release`.

3. **Vì sao `mvn -Ddemo.skip=true test` vẫn chạy test trong ví dụ?**  
   POM có property `demo.skip` nhưng không nối nó tới `skipTests`; Surefire không có alias `demo.skip` cho tham số đó.

4. **Làm sao để dùng chính `demo.skip` mà không đổi tên CLI?**  
   Cấu hình `<skipTests>${demo.skip}</skipTests>` trong plugin Surefire; sau đó phải xác minh phiên bản và execution.

5. **`help:evaluate` in `true` có chứng minh Surefire bỏ qua test không?**  
   Không. Nó chỉ giúp xác nhận property được Maven đánh giá thành `true`.

6. **Một plugin không có dòng User Property cho parameter có phải không cấu hình được?**  
   Không. Có thể parameter được cấu hình qua `<configuration>` hoặc cơ chế chính thức khác; cần xem documentation và giới hạn tham số.

7. **Tại sao `-Ddemo.message=Hello Maven` làm đổi ứng dụng mẫu dù Resources Plugin không có parameter `demo.message`?**  
   Resource đã bật filtering và chứa biểu thức `${demo.message}`; đây là dữ liệu nội suy, không phải parameter alias.

8. **Maven có tự cài JDK mới khi đặt `-Dmaven.compiler.release=21` không?**  
   Không. Release là tham số compiler; JDK cần được chuẩn bị riêng và hỗ trợ release đó.

## 18. Tài liệu tham khảo chính thức

- [Apache Maven Compiler Plugin — compiler:compile parameter reference](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Apache Maven Surefire Plugin — surefire:test parameter reference](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven Help Plugin — help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
- [Apache Maven Help Plugin — help:evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html)
- [Apache Maven Resources Plugin — filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)

**Ghi nhớ:** `<properties>` và `-Dkey=value` chỉ cung cấp **giá trị**; plugin goal chỉ sử dụng giá trị khi có **hợp đồng tham số hỗ trợ** hoặc **ánh xạ tường minh** thông qua POM/đầu vào của goal. Đừng đoán tên CLI từ tên XML; hãy xem mục **User Property**, kiểm tra effective POM và quan sát hành vi build thực tế.
