# Vòng đời Maven: process-resources, compile và process-classes

## 1. Ba phase liên tiếp giải quyết ba việc khác nhau

Khi Maven xây dựng một dự án Java, mã nguồn `.java` và các tài nguyên như `.properties` không đi thẳng thành JAR. Trong **default lifecycle**, ba phase `process-resources`, `compile`, `process-classes` nằm liên tiếp theo thứ tự đó và chuẩn bị đầu ra cho các bước kiểm thử, đóng gói phía sau.

| Phase | Mục đích | Goal tiêu biểu với `<packaging>jar</packaging>` | Đầu ra mặc định |
| --- | --- | --- | --- |
| `process-resources` | Sao chép, xử lý tài nguyên của ứng dụng | `resources:resources` | Các resource từ `src/main/resources` được đưa vào `target/classes` |
| `compile` | Biên dịch mã Java chính | `compiler:compile` | File `.class` trong `target/classes` |
| `process-classes` | Xử lý thêm kết quả sau khi biên dịch, nếu dự án cần | **Không có goal mặc định** với packaging `jar` | Không nhất thiết xuất hiện file mới; phụ thuộc goal bạn tự gắn |

Điểm dễ nhầm nhất: **`process-classes` là phase có sẵn, nhưng không tự động “xử lý bytecode” cho mọi ứng dụng Java.** Muốn làm việc ở phase này (ví dụ instrument/enhance bytecode, kiểm tra hoặc tạo metadata từ class đã biên dịch), dự án phải có một plugin goal thực sự được gắn vào phase đó.

Sau bài học, bạn sẽ biết cách kiểm chứng thứ tự ba phase trong Maven 3.9.x bằng một dự án Java 17 chạy được, quan sát nội dung của `target/classes`, thấy resource filtering hoạt động, hiểu lúc nào cần `process-classes`, và phân biệt các lệnh phase với gọi plugin goal trực tiếp.

## 2. Vị trí trong default lifecycle

Trình tự rút gọn của Maven 3:

~~~text
validate
   |
initialize
   |
generate-sources -> process-sources -> generate-resources
   |
process-resources       resources:resources
   |                    sao chép/lọc tài nguyên
   v
compile                 compiler:compile
   |                    Java source -> bytecode
   v
process-classes         goal tự cấu hình (nếu có)
   |                    hậu xử lý sau biên dịch
   v
generate-test-sources -> process-test-resources -> test-compile
   |
test                    surefire:test (với packaging jar)
   |
package                 jar:jar (với packaging jar)
~~~

Sơ đồ được rút gọn để tập trung vào ba phase: thực tế còn các phase như `process-test-sources`, `generate-test-resources`, `process-test-classes`, `prepare-package`. Trong default lifecycle, Maven chạy các phase theo thứ tự định nghĩa. Khi bạn gọi:

~~~bash
mvn process-resources
mvn compile
mvn process-classes
~~~

- `mvn process-resources` chạy default lifecycle **đến hết process-resources**. Với packaging `jar`, goal resource mặc định được gọi.
- `mvn compile` chạy qua `process-resources` rồi đến `compile`. Vì vậy, khi biên dịch Java, những resource cần thiết đã có cơ hội được sao chép trước.
- `mvn process-classes` chạy qua **cả hai phase trước** rồi đến `process-classes`. Nếu không gắn goal tại `process-classes`, Maven có thể hoàn thành phase này mà không làm thêm gì.
- `mvn package` chạy các phase trước đó, bao gồm ba phase trên, rồi tiếp tục test và đóng gói; trong một project `jar` bình thường có test, test sẽ chạy trước khi tạo JAR.

`clean` thuộc một lifecycle khác. `mvn clean compile` nghĩa là dọn đầu ra cũ rồi đi qua default lifecycle đến `compile`; không phải “chỉ chạy riêng đúng một goal biên dịch”.

## 3. Phase process-resources: chuyển tài nguyên vào classpath

### 3.1. Resource là gì, nằm ở đâu?

Maven mặc định coi `src/main/resources` là thư mục tài nguyên của ứng dụng. Những file không phải mã Java nhưng ứng dụng cần lúc chạy thường được đặt ở đây, ví dụ:

~~~text
src/main/resources/
├── application.properties
├── banner.txt
├── data/sample.json
└── templates/message.txt
~~~

Với `<packaging>jar</packaging>`, Maven mặc định gắn goal `maven-resources-plugin:resources` vào `process-resources`. Goal này sao chép các tài nguyên được chọn đến thư mục đầu ra, thông thường là `target/classes`, **giữ đường dẫn tương đối**:

~~~text
src/main/resources/application.properties  -> target/classes/application.properties
src/main/resources/data/sample.json        -> target/classes/data/sample.json
~~~

`target/classes` là một **classpath root**: Java có thể tìm resource bằng tên tương đối bên trong thư mục đó, không cần sửa đường dẫn tuyệt đối theo nơi chạy chương trình. Khi đóng JAR thông thường, nội dung có trong `target/classes` thường cũng là nguồn để đóng gói các file trong JAR.

Nếu `src/main/resources` không tồn tại, Maven Resources Plugin có thể bỏ qua thư mục không tồn tại; đó không mặc nhiên là lỗi build. Nếu bạn chỉ có mã Java mà chưa có file resource, phase `process-resources` vẫn là một mốc có thật trong lifecycle.

### 3.2. Mặc định copy nguyên trạng, filtering là tùy chọn

Theo mặc định, Maven **không** tự thay mọi chuỗi giống biến trong file tài nguyên. Với một tài nguyên text:

~~~properties
message=@app.greeting@
~~~

nếu copy **không filtering**, nội dung ở `target/classes/application.properties` vẫn là:

~~~properties
message=@app.greeting@
~~~

Khi cấu hình `<filtering>true</filtering>`, Resources Plugin có thể thay `@app.greeting@` bằng property `app.greeting` từ POM, settings/filter file hoặc command line (tùy cấu hình và thứ tự ưu tiên). Ví dụ POM có:

~~~xml
<properties>
    <app.greeting>Hello from resources</app.greeting>
</properties>

<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
        </resource>
    </resources>
</build>
~~~

Thì sau `process-resources`, file đích có:

~~~properties
message=Hello from resources
~~~

Maven Resources Plugin hỗ trợ cách viết placeholder `@...@` và `${...}`. Bài này dùng `@...@` để tránh nhầm với placeholder của một số framework khi ứng dụng chạy. **Filtering là thao tác lúc build**, không phải chương trình Java tự thay biến sau khi đã phát hành artifact.

**Cẩn thận với resource nhị phân.** Không bật filtering bừa bãi trên ảnh, font, file zip, certificate hoặc các nội dung nhị phân vì lọc/chuyển mã có thể làm hỏng byte. Ở dự án thực tế, nên giới hạn chỉ các file văn bản cần lọc, hoặc tách thư mục resource cần lọc khỏi resource cần copy nguyên trạng. Không đưa mật khẩu hoặc token thực vào resource sẽ được đóng gói công khai.

### 3.3. Resource encoding ảnh hưởng kết quả

Nếu bạn lọc file text tiếng Việt, hãy chọn encoding nhất quán. Riêng Java `Properties.load(InputStream)` theo cách dùng truyền thống đọc `.properties` theo ISO-8859-1; còn `ResourceBundle` trên Java hiện đại có quy tắc encoding khác. Cần phân biệt **encoding của Resources Plugin khi ghi** với **cách API Java sẽ đọc**. Ví dụ thực hành dùng toàn bộ giá trị ASCII nên tránh khác biệt mã hóa và có thể quan sát chính xác.

Với Maven Resources Plugin 3.3.1, có thể cấu hình `propertiesEncoding` cho các file `.properties` khi muốn rõ quy tắc đọc/ghi; project Java quốc tế hóa cũng cần cân nhắc việc escape ký tự theo API đọc file. Đừng chỉ nhìn `project.build.sourceEncoding=UTF-8` rồi tự kết luận mọi thư viện/runtime luôn dùng UTF-8 với `.properties`.

## 4. Phase compile: từ Java source sang file class

Với dự án `jar` mặc định, phase `compile` gắn với `maven-compiler-plugin:compile`. Compiler Plugin tìm mã trong `src/main/java` (cùng những source root đã cấu hình), sử dụng JDK/compiler đã chọn và tạo bytecode trong `target/classes`.

Ví dụ:

~~~text
src/main/java/vn/example/lifecycle/App.java
                       |
                       | mvn compile
                       v
target/classes/vn/example/lifecycle/App.class
~~~

Thư mục dưới `target/classes` phản ánh package Java; vì vậy lớp `vn.example.lifecycle.App` phải được chạy bằng tên đầy đủ này:

~~~bash
java -cp target/classes vn.example.lifecycle.App
~~~

Cách biên dịch của Compiler Plugin phụ thuộc cấu hình và phiên bản công cụ. Với Java 17, nên dùng cấu hình:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

`release` hướng bộ biên dịch sử dụng API/bytecode tương thích phiên bản Java yêu cầu (khi JDK đang chạy hỗ trợ). Đây **không phải** cách cài hoặc chọn JDK 17 tự động. Kiểm tra JDK thực tế bằng `mvn -version`/`./mvnw -version` và `JAVA_HOME` nếu gặp lỗi `release version 17 not supported`.

Điều cần nhớ:

- `compile` biên dịch **mã ứng dụng**, không phải `src/test/java`. Mã test được biên dịch ở phase `test-compile` sau đó.
- `compile` không tự chạy phương thức `main`; muốn chạy chương trình, dùng `java` hoặc một goal thích hợp.
- `compile` không tự tạo JAR. Để đóng gói một dự án `jar`, chạy đến `package`.
- `process-resources` chạy **trước `compile`** khi gọi phase, nên resource đã được copy vào classpath đầu ra. Không có nghĩa Maven buộc mọi đoạn mã Java phải đọc resource trong lúc biên dịch.
- Kết quả biên dịch có thể được Maven cache/so sánh đầu vào giữa các lần chạy; nếu muốn quan sát một lần build rõ ràng, dùng `mvn clean compile` để loại file cũ.

## 5. Phase process-classes: chỗ để hậu xử lý class đã biên dịch

Theo định nghĩa vòng đời, `process-classes` chạy ngay sau `compile` và trước các phase chuẩn bị/biên dịch test. Nó hữu ích khi **mã bytecode hoặc metadata chỉ tồn tại sau khi class được biên dịch**.

Một số loại công việc có thể được gắn vào đây khi dự án thực sự cần:

- **Bytecode enhancement**: một công cụ tăng cường hoặc biến đổi bytecode cho mục đích framework, instrument hoặc tối ưu đặc thù.
- **Instrumentation/metadata**: sinh file mô tả, phân tích/đánh dấu lớp sau khi đã biên dịch, với plugin tương thích.
- **Kiểm tra cấu trúc class**: chạy công cụ kiểm tra trên `.class` trước khi test/đóng gói, nếu công cụ phù hợp phase này.

Các ví dụ trên là **khả năng sử dụng**, không phải hành vi mặc định của Maven. Với packaging `jar`, bảng binding chuẩn **không gắn goal nào cho `process-classes`**. Nếu POM không khai báo execution cho phase này, chạy `mvn process-classes` vẫn chạy các phase trước, nhưng không phát sinh thao tác hậu xử lý riêng.

### 5.1. Cách gắn một goal vào phase

Một execution trong `pom.xml` thường có dạng:

~~~xml
<plugin>
    <groupId>...</groupId>
    <artifactId>...</artifactId>
    <version>...</version>
    <executions>
        <execution>
            <id>ten-execution</id>
            <phase>process-classes</phase>
            <goals>
                <goal>ten-goal</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây chỉ là **khung cấu hình**, không phải một plugin thật để copy nguyên văn. Plugin cần cung cấp goal, cấu hình tương thích và thực hiện công việc phù hợp ở mốc đó. `<phase>` xác định vị trí gắn; `<goal>` xác định việc sẽ làm. Chỉ ghi `<phase>process-classes</phase>` mà không có goal phù hợp thì chưa định nghĩa hành vi.

Ở bài thực hành dưới đây, ta dùng Maven AntRun Plugin để **tạo một file dấu mốc**. Việc ghi file này chỉ nhằm nhìn thấy rõ `process-classes` có chạy; nó không phải cách tăng cường bytecode và không phải cấu hình bắt buộc cho dự án thật.

### 5.2. Process-classes khác test và package

`process-classes` vẫn là một phase **trước** `test-compile`, `test`, `package`. Vì thế:

- `mvn process-classes` không mặc nhiên biên dịch hay thực thi unit test.
- `mvn process-classes` không mặc nhiên tạo file JAR.
- Các goal được gắn tại `process-classes` vẫn chạy khi bạn gọi một phase **sau** nó, ví dụ `mvn test` hoặc `mvn package`.
- Nếu goal hậu xử lý bị lỗi, Maven có thể dừng ở phase này trước khi test được chạy. Thứ tự này giúp kiểm tra lỗi đúng mốc.

## 6. Thực hành đầy đủ: so sánh ba phase trên cùng một dự án

Ví dụ dùng **Maven 3.9.x, JDK 17 và JUnit Jupiter 5**. Dự án có một file resource được lọc, một class Java đọc resource, một bộ test và một plugin tạo dấu mốc ở `process-classes`.

### 6.1. Cấu trúc dự án

Tạo cây thư mục `lifecycle-demo`:

~~~text
lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/lifecycle/App.java
    │   └── resources/application.properties
    └── test/
        └── java/vn/example/lifecycle/AppTest.java
~~~

Khi thao tác, luôn đứng ở thư mục có `pom.xml` hoặc dùng `mvn -f <duong-dan-pom>`. Maven cần truy cập mạng khi plugin/dependency chưa có trong local repository.

### 6.2. POM hoàn chỉnh: `lifecycle-demo/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <app.greeting>Hello from resources</app.greeting>
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
                <configuration>
                    <propertiesEncoding>ISO-8859-1</propertiesEncoding>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>create-phase-marker</id>
                        <phase>process-classes</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <echo file="${project.build.directory}/process-classes.marker">process-classes completed</echo>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
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

Giải thích những điểm tác động đến ba phase:

- `<resources>` bật filtering cho `src/main/resources`. Ví dụ này **chỉ có một file properties dạng văn bản ASCII**; cấu hình cần được giới hạn lại khi dự án có file nhị phân.
- `maven-resources-plugin` được gắn sẵn với `process-resources` bởi packaging `jar`; khai báo ở đây giúp ghim phiên bản và thiết lập encoding của file properties.
- `maven-compiler-plugin` được gắn với `compile` bởi packaging `jar`; `maven.compiler.release=17` quy định cấp Java.
- `maven-antrun-plugin` có execution rõ `<phase>process-classes</phase>` và `<goal>run</goal>`. Ant task `echo` ghi một file text vào `target/process-classes.marker`. **File marker nằm ngoài `target/classes`** nên không tự đi vào JAR. Đây là dấu hiệu quan sát phase, không phải bước build được Maven làm sẵn.
- Surefire và JAR Plugin để sau này kiểm chứng test/đóng gói; hai plugin ấy không phải nội dung công việc chính của ba phase đang học.
- `<packaging>jar</packaging>` là điều kiện ngầm quan trọng: với packaging khác (ví dụ `pom` ở POM cha), binding mặc định có thể khác. Không suy ra rằng mọi dự án Maven đều tạo `.class`.

### 6.3. Resource đầu vào

File `src/main/resources/application.properties`:

~~~properties
message=@app.greeting@
~~~

Lúc này file **nguồn** còn giữ placeholder. Sau khi Resources Plugin lọc, **file đích** `target/classes/application.properties` sẽ có:

~~~properties
message=Hello from resources
~~~

Nếu sau build bạn thấy file nguồn bị đổi thành giá trị cuối, rất có thể một thao tác khác đã sửa nhầm nguồn. Resources Plugin trong ví dụ đọc ở `src/main/resources` và ghi đến `target/classes`; nó không cần sửa file nguồn.

### 6.4. Java 17: đọc resource và thực thi mã đã biên dịch

File `src/main/java/vn/example/lifecycle/App.java`:

~~~java
package vn.example.lifecycle;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static int sum(int left, int right) {
        return Math.addExact(left, right);
    }

    public static String readMessage() {
        Properties properties = new Properties();

        try (InputStream input = App.class.getClassLoader()
                .getResourceAsStream("application.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing application.properties");
            }
            properties.load(input);
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot read application.properties", exception);
        }

        return properties.getProperty("message");
    }

    public static void main(String[] args) {
        System.out.println("Resource: " + readMessage());
        System.out.println("Sum: " + sum(2, 3));
    }
}
~~~

Chương trình dùng classpath resource từ `target/classes` hoặc JAR. Phương thức `getResourceAsStream` dùng đường dẫn tương đối tính từ classpath root (không dùng `src/main/resources` khi chạy sau build), nhờ vậy chương trình không phụ thuộc thư mục làm việc nếu đóng gói đúng.

Với giá trị resource đã lọc và bytecode chạy được, stdout chính xác là:

~~~text
Resource: Hello from resources
Sum: 5
~~~

`Math.addExact` dùng phương thức có sẵn trong Java 17 và ném ngoại lệ khi cộng tràn `int`. Đầu ra trên là kết quả từ `main`; nó **không** bao gồm log của Maven khi build.

### 6.5. Unit test để nhìn ranh giới trước và sau process-classes

File `src/test/java/vn/example/lifecycle/AppTest.java`:

~~~java
package vn.example.lifecycle;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void sumsNumbers() {
        assertEquals(5, App.sum(2, 3));
    }

    @Test
    void readsFilteredResource() {
        assertEquals("Hello from resources", App.readMessage());
    }
}
~~~

Lớp này thuộc `src/test/java`. Khi chỉ chạy đến `process-classes`, Maven **chưa** chạy goal test-compile/surefire mặc định; khi gọi `mvn test` hoặc `mvn package`, Maven sẽ tiếp tục các phase biên dịch và chạy test. Với POM ở trên, có hai test cần chạy.

## 7. Thí nghiệm A: dừng ở process-resources

Trước tiên kiểm tra JDK Maven đang dùng:

~~~bash
java -version
mvn -version
~~~

Sau đó, từ thư mục `lifecycle-demo`:

~~~bash
mvn clean process-resources
~~~

`clean` xóa đầu ra cũ. Default lifecycle đến `process-resources` sẽ gọi Resources Plugin với resource filtering trong POM. Hãy mở file:

~~~text
target/classes/application.properties
~~~

Nội dung mong đợi:

~~~properties
message=Hello from resources
~~~

**Những thứ chưa được tạo bởi lần build sạch này:** file `target/classes/vn/example/lifecycle/App.class`, `target/process-classes.marker`, `target/test-classes/.../AppTest.class` và `target/lifecycle-demo-1.0.0.jar`.

Tại sao chưa có `App.class`? Vì lệnh mới dừng tại `process-resources`; phase `compile` nằm **sau**. Nếu cố chạy:

~~~bash
java -cp target/classes vn.example.lifecycle.App
~~~

thì không thể tìm được lớp `App` từ lần build này, bởi chỉ có resource được sao chép, chưa có bytecode ứng dụng. Không nên kết luận tài nguyên lỗi chỉ vì chương trình chưa chạy được ở mốc này.

Có thể thử một thay đổi **chỉ có tác dụng tại build time**:

~~~bash
mvn -Dapp.greeting=CLI_OK clean process-resources
~~~

Đọc lại `target/classes/application.properties`:

~~~properties
message=CLI_OK
~~~

Lựa chọn `-Dapp.greeting=CLI_OK` cung cấp property Maven cho bước filtering. Nó không sửa giá trị `app.greeting` trong `pom.xml` và không tự truyền sang một tiến trình Java được chạy sau đó. **Khi kết thúc thí nghiệm, chạy lại lệnh không có `-D`** để khôi phục đầu ra mặc định cho các bước tiếp theo.

## 8. Thí nghiệm B: dừng ở compile

Chạy:

~~~bash
mvn clean compile
~~~

Sau khi clean, Maven thực thi đến `process-resources` rồi `compile`. Kiểm tra hai nhóm file:

~~~text
target/
└── classes/
    ├── application.properties
    └── vn/
        └── example/
            └── lifecycle/
                └── App.class
~~~

`target/classes/application.properties` vẫn có giá trị lọc từ property mặc định:

~~~properties
message=Hello from resources
~~~

`App.class` xuất hiện vì Compiler Plugin đã biên dịch file `App.java`. Bây giờ có thể chạy:

~~~bash
java -cp target/classes vn.example.lifecycle.App
~~~

Stdout:

~~~text
Resource: Hello from resources
Sum: 5
~~~

Từ lần build **`clean compile`**, `target/process-classes.marker` chưa xuất hiện, vì phase `process-classes` chưa chạy. `target/test-classes` và test report cũng chưa được tạo từ lần build sạch này; file JAR chưa có.

Mối liên hệ quan trọng: **resource và class nằm chung classpath root**. Java có thể tải `application.properties` vì `process-resources` đã copy nó trước khi `compile` hoàn tất. Compiler Plugin tự nó không thực hiện filtering cho file `.properties` trong ví dụ; đó là trách nhiệm của Resources Plugin.

## 9. Thí nghiệm C: dừng ở process-classes

Chạy:

~~~bash
mvn clean process-classes
~~~

Từ POM đã khai báo, thứ tự goal quan sát được là:

~~~text
resources:resources  -> process-resources
compiler:compile     -> compile
antrun:run           -> process-classes (do POM tự gắn)
~~~

Tên goal có thể có tiền tố và phiên bản plugin trong log (ví dụ `antrun:3.1.0:run`); điều quan trọng là goal `antrun:run` xuất hiện **sau compiler**. Sau lệnh này, tìm:

~~~text
target/
├── classes/
│   ├── application.properties
│   └── vn/example/lifecycle/App.class
└── process-classes.marker
~~~

File `target/process-classes.marker` chứa nội dung:

~~~text
process-classes completed
~~~

Đây là dấu mốc do **AntRun Plugin được cấu hình trong POM** tạo ra. Nếu bạn xóa nguyên phần plugin `maven-antrun-plugin` khỏi POM rồi chạy lại `mvn clean process-classes`, các phase vẫn chạy tới đó nhưng **không có file marker**, vì Maven không có goal mặc định được gắn tại `process-classes` cho packaging `jar`.

Tại mốc `process-classes`, ví dụ vẫn **chưa** biên dịch/chạy `AppTest` hoặc tạo JAR. Nếu dùng `mvn test`/`mvn package` sau đó, Maven sẽ đi qua `process-classes` và tạo marker trước khi thực thi các công việc test và đóng gói. Đừng cho rằng `process-classes` là một tên khác của `test`.

## 10. Đối chiếu trực tiếp ba lần chạy sạch

| Quan sát sau lệnh | `mvn clean process-resources` | `mvn clean compile` | `mvn clean process-classes` |
| --- | --- | --- | --- |
| `target/classes/application.properties` đã lọc | Có | Có | Có |
| `target/classes/.../App.class` | Chưa | Có | Có |
| `target/process-classes.marker` do AntRun tạo | Chưa | Chưa | Có |
| `target/test-classes/.../AppTest.class` | Chưa | Chưa | Chưa |
| `target/surefire-reports/` từ test | Chưa | Chưa | Chưa |
| `target/lifecycle-demo-1.0.0.jar` | Chưa | Chưa | Chưa |
| Chạy `java -cp target/classes vn.example.lifecycle.App` | Chưa chạy được | Chạy được | Chạy được |

Bảng áp dụng cho **POM có plugin AntRun đã khai báo ở mục 6**, và mỗi lần đều bắt đầu bằng `clean`. Các plugin có thể tạo thêm metadata, cache hoặc thư mục khác trong `target/`; bảng chỉ xét các đầu ra cần kiểm tra.

Một bài tập hữu ích là **thực hiện từng lệnh, chụp lại cây `target/` ở ba mốc rồi giải thích sự khác biệt**. Nhớ đọc `BUILD SUCCESS`/`BUILD FAILURE` và log goal; nhìn file có sẵn sau một lệnh **không clean** có thể gây ngộ nhận vì file cũ còn lại.

## 11. Liên hệ với test, package và JAR

Để thấy các phase vừa học đóng góp thế nào vào JAR, chạy tiếp từ đầu với:

~~~bash
mvn clean test
mvn clean package
~~~

`mvn clean test` vẫn đi qua `process-resources`, `compile` và `process-classes`, sau đó biên dịch/chạy `AppTest`. Với ví dụ trên, kết quả dự kiến là **2 test PASS**, có report trong `target/surefire-reports`. Sau lệnh này từ trạng thái sạch, JAR chưa được tạo.

`mvn clean package` đi tiếp đến `package`; nếu hai test đều pass, Maven tạo:

~~~text
target/lifecycle-demo-1.0.0.jar
~~~

Dùng JDK `jar` để kiểm tra JAR:

~~~bash
jar tf target/lifecycle-demo-1.0.0.jar
~~~

Trong danh sách entry, bạn phải tìm được (thứ tự có thể khác):

~~~text
application.properties
vn/example/lifecycle/App.class
~~~

File `process-classes.marker` **không** nằm trong JAR vì bài học tạo nó tại `target/`, **không** nằm trong `target/classes`. Nếu một plugin hậu xử lý thực sự thay đổi `.class` trong `target/classes` ở `process-classes`, JAR Plugin sau đó có thể đóng gói các bytecode đã biến đổi. Đó là lý do phase này nằm trước `package`.

Chạy từ JAR trên classpath (không dùng `java -jar` khi POM chưa khai báo `Main-Class` trong manifest):

~~~bash
java -cp target/lifecycle-demo-1.0.0.jar vn.example.lifecycle.App
~~~

Kết quả:

~~~text
Resource: Hello from resources
Sum: 5
~~~

Hai đầu ra ở đây cùng xuất hiện vì JAR chứa **cả resource đã được lọc** và **bytecode đã biên dịch**. Resource đầu vào vẫn nằm ở `src/main/resources/application.properties` với placeholder; build tạo bản sao dùng khi chạy.

## 12. Gọi phase khác gọi plugin goal trực tiếp

So sánh các lệnh:

~~~bash
mvn process-resources
mvn resources:resources

mvn compile
mvn compiler:compile

mvn process-classes
mvn antrun:run
~~~

Cột trái (lệnh phase) yêu cầu Maven thực thi **các phase trước đó trong lifecycle** và phase được chỉ định. Cột phải (goal) yêu cầu **một công việc plugin cụ thể**, có thể không gọi các phase tiền nhiệm; một goal cũng có thể có yêu cầu/fork lifecycle riêng theo mô tả plugin.

Riêng `mvn antrun:run` khi gọi trực tiếp không đảm bảo dùng cùng execution `create-phase-marker` được cấu hình gắn với `process-classes`; Maven có thể chọn execution mặc định cho lời gọi CLI. **Để thử đúng execution marker của bài, hãy chạy `mvn process-classes`.**

Không dùng `mvn compiler:compile` làm cách kiểm chứng toàn bộ quy trình tài nguyên + biên dịch: khi bạn gọi goal compiler trực tiếp từ trạng thái sạch, chưa chắc Resources Plugin đã copy resource. Chạy `mvn compile` mới bảo đảm default lifecycle đi qua `process-resources` trước đó theo thứ tự thông thường.

## 13. Cấu hình thực tế: when nên giữ, khi nào bỏ goal ở process-classes?

Ví dụ marker minh họa execution nhưng không phải lý do nên thêm AntRun vào mọi dự án. Với dự án thực tế, chỉ sử dụng `process-classes` khi công cụ cần đầu vào là **file `.class`** hoặc các cấu trúc đã được biên dịch.

Một số tiêu chí khi chọn phase:

1. **Nếu chỉ cần copy/lọc file resource:** dùng `process-resources` và Resources Plugin; không cần xử lý bytecode.
2. **Nếu cần sinh mã Java trước khi compiler chạy:** nhiều công cụ code generation phù hợp `generate-sources` (và đăng ký source root) hơn `process-classes`, vì code phải tồn tại **trước `compile`**.
3. **Nếu cần can thiệp bytecode của lớp chính:** `process-classes` thường hợp lý hơn phase trước `compile`, miễn plugin tương thích và giữ class hợp lệ.
4. **Nếu cần sửa/kiểm tra file class của test:** `process-test-classes` là phase khác, diễn ra sau `test-compile`; đừng nhầm với `process-classes` của mã sản phẩm.
5. **Nếu cần đóng gói artifact:** sử dụng `package`/plugin đóng gói tương ứng; không mặc định đóng gói trong `process-classes`.
6. **Nếu thao tác chỉ phục vụ minh họa:** giữ nó ở project học tập, không đem marker hoặc AntRun vào một hệ thống thực tế chỉ để “điền cho đủ phase”.

**Lựa chọn plugin/phần mở rộng có tác động đến các phase sau.** Nếu mục tiêu hậu xử lý là biến đổi bytecode, đầu ra phải nằm ở vị trí compiler/JAR Plugin sử dụng; ghi file ngoài `target/classes` sẽ không biến đổi những lớp được đóng gói. Ngược lại, để kiểm chứng phase bằng marker, ghi file ngoài `target/classes` giúp tránh mang tệp thí nghiệm vào JAR sản phẩm.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể và cách xác minh |
| --- | --- |
| Sau `mvn process-resources` không có `App.class` | Đúng với lần build sạch: phase compile chưa chạy |
| Sau `mvn compile` chưa có file JAR | Đúng: packaging nằm sau compile; chạy `mvn package` khi cần JAR |
| Resource có `@app.greeting@` nguyên văn | Chưa bật filtering, file không nằm trong resource được xử lý, property sai tên hoặc gọi sai goal/config |
| Resource có ký tự tiếng Việt lỗi dấu | Mismatch encoding khi filtering hoặc API Java đọc properties; kiểm tra encoding cả hai phía |
| `App.class` có nhưng chương trình báo `Missing application.properties` | File resource không được copy vào classpath root, sai đường dẫn hoặc chạy với classpath thiếu resource |
| `process-classes` chạy nhưng marker không có | Chưa khai báo/không kích hoạt execution AntRun; kiểm tra `<phase>`, `<goals>`, `<configuration>` |
| Maven lỗi khi chạy AntRun Plugin | Plugin/dependency chưa tải được, sai cú pháp XML/Ant target hoặc không có quyền ghi thư mục output |
| Marker có nhưng JAR không có marker | Marker được tạo ngoài `target/classes`; đây là lựa chọn có chủ đích |
| Không có test report sau `process-classes` | Bình thường, phase `test` chưa chạy; gọi `mvn test` |
| Test hoặc JAR có sau khi chạy `mvn compile` | Có thể là đầu ra cũ từ lần build trước; so sánh sau `mvn clean compile` |
| `release version 17 not supported` | Maven sử dụng JDK cũ; kiểm tra `mvn -version` và `JAVA_HOME` |
| Resource nhị phân bị hỏng khi package | Filtering đã áp dụng cho file không phải văn bản; giới hạn tập file được lọc hoặc tách thư mục |
| Build chỉ lỗi trong CI | So sánh JDK, phiên bản Maven/plugin, encoding, file resource, phân biệt đường dẫn và quyền truy cập trên CI |

**Cách đọc log:** tìm dòng plugin như `resources:3.3.1:resources`, `compiler:3.14.1:compile` và `antrun:3.1.0:run`; chúng cho biết goal nào đã được gọi. Khi Maven dừng ở `process-resources`, đừng sửa code Java nếu lỗi thực tế là không thể đọc/copy resource. Khi dừng ở `compile`, hãy đọc thông báo compiler. Khi dừng ở `process-classes`, kiểm tra execution/plugin hậu xử lý bạn đã cấu hình.

Trong các dự án nhiều module, thứ tự **giữa các module** do reactor và dependency graph quyết định. Bên trong mỗi module, thứ tự phase vẫn theo lifecycle. Không được đánh đồng “`app` build sau `core`” với “`process-classes` chạy sau `compile`”: một quan hệ là giữa project, quan hệ còn lại là giữa các bước build của từng project.

## 15. Bài tập cuối bài và tiêu chí tự kiểm tra

**Bài tập A — Dự đoán đầu ra:** Không nhìn bảng mục 10, viết ba dự đoán tương ứng `mvn clean process-resources`, `mvn clean compile`, `mvn clean process-classes`: có `application.properties` đã lọc hay chưa, có `App.class` chưa, có `process-classes.marker` chưa. Chạy lần lượt rồi đối chiếu.

**Bài tập B — Thay đổi property tại thời điểm build:** Chạy `mvn -Dapp.greeting=CLI_OK clean process-resources` và mở file đích. Giải thích vì sao `src/main/resources/application.properties` vẫn giữ `@app.greeting@`. Chạy lại lệnh không có `-D` và kiểm tra giá trị trở về mặc định.

**Bài tập C — Resource trên classpath:** Sau `mvn clean compile`, chạy `java -cp target/classes vn.example.lifecycle.App`. Nếu cố tình đổi tên resource thành `application-other.properties`, mô tả vì sao Java ném `IllegalStateException`. Khôi phục tên file đúng rồi chạy lại để thấy stdout chuẩn.

**Bài tập D — Chứng minh process-classes có tác dụng nhờ execution:** Tạm bỏ riêng execution AntRun khỏi POM và chạy `mvn clean process-classes`. Marker không xuất hiện nhưng class và resource vẫn có. Khôi phục execution, chạy lại và tìm marker. Điều này chứng minh **phase vẫn tồn tại dù không có goal mặc định**.

**Bài tập E — Phân biệt main/test/package:** Chạy `mvn clean process-classes` rồi `mvn clean test`, so sánh `target/test-classes` và `target/surefire-reports`. Cuối cùng chạy `mvn clean package`, dùng `jar tf` để xem những tệp nào từ `target/classes` được đóng gói.

**Bài tập F — Sửa lỗi có chủ đích:** Thử đặt `@app.greting@` (sai chính tả) trong resource rồi chạy `mvn clean compile`. Quan sát phần nào của đầu ra không đúng và giải thích đó là lỗi lọc resource chứ không nhất thiết là lỗi Java compile. Khôi phục đúng `@app.greeting@`.

Bạn đạt mục tiêu khi có thể nói chính xác:

- **`process-resources`** chuẩn bị tài nguyên ở vị trí runtime/classpath, có thể filtering khi cấu hình.
- **`compile`** biên dịch Java thành bytecode chính và đi sau `process-resources`.
- **`process-classes`** là điểm nối để hậu xử lý các class **sau khi biên dịch**, nhưng không tự làm việc nếu không có goal gắn vào.
- Cả ba diễn ra **trước unit test và package** trong default lifecycle Maven 3.
- Bằng chứng đáng tin là **goal được gọi trong log và file sinh ra từ một build sạch**, không chỉ tên phase.

## 16. Tài liệu chính thức

- [Introduction to the Build Lifecycle – Apache Maven](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): thứ tự phase và binding mặc định cho `jar`.
- [Apache Maven Resources Plugin – Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html): nguồn property, placeholder `@...@`/`${...}` và cảnh báo filtering nhị phân.
- [Apache Maven Resources Plugin – Filtering Properties Files](https://maven.apache.org/plugins/maven-resources-plugin/examples/filtering-properties-files.html): encoding của `.properties` khi filtering.
- [Apache Maven Compiler Plugin – Setting the Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): compiler release và API Java tương ứng.
- [Apache Maven AntRun Plugin 3.1.0 – Usage](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/usage.html): `antrun:run` với `<target>` và execution.
