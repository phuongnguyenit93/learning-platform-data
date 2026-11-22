# Thay đổi cấu trúc mặc định của Maven khi tích hợp mã nguồn có sẵn

## 1. Vấn đề cần giải quyết

Khi đưa một ứng dụng Java đang hoạt động vào quy trình build Maven, mã nguồn hiện có có thể không nằm trong các thư mục Maven mặc định. Ví dụ, dự án cũ đặt Java trong `legacy-src/`, test trong `legacy-tests/` và tệp cấu hình trong `config/`. Nếu chỉ thêm `pom.xml` rồi chạy `mvn package`, Maven có thể không tìm thấy mã nguồn hoặc không đưa đúng tài nguyên vào artifact.

Có hai hướng hợp lệ:

1. **Chuyển mã nguồn về cấu trúc chuẩn của Maven**, nếu kiểm soát được repository và không có ràng buộc tương thích về đường dẫn.
2. **Giữ nguyên cấu trúc hiện có, khai báo lại đầu vào build trong POM** để Maven đọc đúng chỗ. Đây thường là bước chuyển tiếp hữu ích khi đang tích hợp hệ thống cũ, chuyển từ Ant, giữ quy trình sinh mã, hoặc chưa thể di chuyển tệp ngay.

Mục tiêu là giữ nguyên ý nghĩa của dự án: mã chạy chính phải được biên dịch như mã sản phẩm; test phải được biên dịch và chạy như test; resource phải nằm đúng classpath; tệp đầu ra phải tách khỏi tệp nguồn. Việc cấu hình đường dẫn cần giải quyết những quan hệ đó, không chỉ làm biến mất lỗi “không tìm thấy nguồn”.

## 2. Hiểu cấu trúc mà Maven mặc định mong đợi

Với dự án Java thông thường và packaging `jar`, các thư mục quan trọng là:

| Vai trò | Thư mục mặc định | Kết quả thường gặp |
| --- | --- | --- |
| Mã Java sản phẩm | `src/main/java` | Biên dịch vào `target/classes` |
| Resource sản phẩm | `src/main/resources` | Sao chép vào `target/classes` và có thể nằm trong JAR |
| Mã Java kiểm thử | `src/test/java` | Biên dịch vào `target/test-classes` |
| Resource kiểm thử | `src/test/resources` | Sao chép vào `target/test-classes` |
| Đầu ra build | `target` | Chứa lớp biên dịch, báo cáo test và artifact |
| POM | `pom.xml` ở gốc module | Mô tả dự án, dependency, plugin và build |

Trong Java, đường dẫn bên dưới **source root** phải phù hợp với tên `package` theo thông lệ. Ví dụ `package demo.legacy;` ứng với `src/main/java/demo/legacy/App.java`. Khi chuyển source root sang `legacy-src`, đường dẫn tương ứng trở thành `legacy-src/demo/legacy/App.java`, chứ không phải thêm `src/main/java` vào bên dưới nữa.

Maven phân biệt “source root” (chứa tệp `.java`), “resource root” (chứa tệp được sao chép lên classpath) và “output directory” (chứa tệp tạo ra). Không được dùng `<sourceDirectory>` để thay thế cho cấu hình resources; cũng không nên chỉ đổi `<directory>` để giải quyết việc Maven không tìm thấy mã nguồn.

Các quy ước này do mô hình dự án và plugin Maven phối hợp thực hiện. Vì vậy, có thể thay đường dẫn được khai báo mà vẫn sử dụng các phase chuẩn như `compile`, `test`, `package` và `verify`.

## 3. Khảo sát cấu trúc cũ trước khi sửa POM

Ví dụ một repository có cấu trúc:

```text
legacy-layout/
├── pom.xml
├── legacy-src/
│   └── demo/legacy/App.java
├── legacy-tests/
│   └── demo/legacy/AppTest.java
├── config/
│   └── app.properties
└── fixtures/
    └── expected.properties
```

Trước khi cấu hình, cần xác định:

- **Tệp Java thật sự thuộc phần nào?** `legacy-src` là mã sản phẩm hay có cả chương trình thử nghiệm, mã sinh và test? Không nên trộn các loại này vào một source root rồi vô tình đóng gói test hoặc mã demo vào JAR.
- **Test nằm ở đâu, được chạy bằng công cụ nào?** Maven Surefire chạy unit test ở phase `test`; chỉ đổi vị trí test chưa đủ nếu thiếu dependency và plugin phù hợp với JUnit/TestNG.
- **Resource được chương trình truy cập bằng cách nào?** Nếu code đọc resource bằng `ClassLoader.getResourceAsStream()`, cần giữ đúng đường dẫn logic trên classpath. Nếu code đọc đường dẫn tệp tuyệt đối hoặc đường dẫn phụ thuộc thư mục làm việc, đó là một vấn đề riêng.
- **Có nhiều source root hoặc mã được sinh tự động không?** Maven POM có `sourceDirectory` chính; trường hợp nhiều thư mục bổ sung thường cần plugin gắn thêm source roots vào đúng phase.
- **Có thư mục đầu ra từ hệ thống cũ không?** `bin/`, `out/`, `dist/`, các tệp `.class` đã build, cache IDE và thư mục sinh mã không nên được coi là source.
- **Ứng dụng đóng gói JAR, WAR hay loại khác?** `src/main/webapp` và cấu hình Maven WAR Plugin thuộc trường hợp ứng dụng web; không áp dụng máy móc thiết lập JAR cho mọi ứng dụng.

Có thể chuyển sang Maven từng bước: trước tiên cho phép build lại và test đúng trên cấu trúc cũ, sau đó mới di chuyển từng nhóm thư mục khi pipeline và IDE đã sẵn sàng.

## 4. Ví dụ đầy đủ: giữ cấu trúc cũ, chạy build Maven chuẩn

Ví dụ này sử dụng **Java 17**, Maven 3 tương thích và một dự án JAR. Các phiên bản plugin/dependency được nêu cụ thể để ví dụ có thể tái lập; chúng không phải khẳng định về phiên bản mới nhất tại thời điểm đọc.

### 4.1. Mã Java sản phẩm

Tạo tệp `legacy-src/demo/legacy/App.java`:

```java
package demo.legacy;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static String message() {
        Properties properties = new Properties();

        try (InputStream input =
                     App.class.getClassLoader()
                         .getResourceAsStream("app.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            properties.load(input);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }

        return properties.getProperty("message");
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Tệp resource `config/app.properties`:

```properties
message=Hello from legacy layout
```

Chương trình đọc `app.properties` từ **classpath**, chứ không phụ thuộc vào thư mục đang thực thi lệnh `java`. Sau bước xử lý resources, Maven cần tạo `target/classes/app.properties` để chương trình tìm được tệp này.

### 4.2. Mã kiểm thử và resource dành riêng cho test

Tạo `legacy-tests/demo/legacy/AppTest.java`:

```java
package demo.legacy;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class AppTest {
    @Test
    void readsResourceFromConfiguredLocations() throws IOException {
        Properties expected = new Properties();

        try (InputStream input =
                     getClass().getClassLoader()
                         .getResourceAsStream("expected.properties")) {
            assertNotNull(input);
            expected.load(input);
        }

        assertEquals(expected.getProperty("expected"), App.message());
    }
}
```

Tệp `fixtures/expected.properties`:

```properties
expected=Hello from legacy layout
```

Maven sẽ đặt resource test ở `target/test-classes/expected.properties`. Nó được dùng trong lúc kiểm thử, **không cần xuất hiện trong JAR sản phẩm**. Test tên `AppTest` cũng phù hợp quy tắc nhận diện mặc định phổ biến của Maven Surefire.

### 4.3. POM thay đổi đúng các đầu vào cần thiết

Tạo `pom.xml` ở gốc `legacy-layout/`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>legacy-layout</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <sourceDirectory>legacy-src</sourceDirectory>
        <testSourceDirectory>legacy-tests</testSourceDirectory>

        <resources>
            <resource>
                <directory>config</directory>
                <filtering>false</filtering>
            </resource>
        </resources>

        <testResources>
            <testResource>
                <directory>fixtures</directory>
                <filtering>false</filtering>
            </testResource>
        </testResources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích theo chức năng:

- `sourceDirectory` đổi thư mục chứa Java sản phẩm thành `legacy-src`; Maven Compiler Plugin biên dịch những lớp này trong phase phù hợp.
- `testSourceDirectory` đổi thư mục chứa Java test thành `legacy-tests`; test vẫn được biên dịch riêng và sử dụng dependency có `scope=test`.
- `resources` đưa nội dung của `config` vào classpath sản phẩm. Tệp `config/app.properties` xuất hiện dưới tên `app.properties` trong `target/classes` và trong JAR.
- `testResources` đưa `fixtures/expected.properties` vào classpath test, thường dưới `target/test-classes`; test có thể đọc bằng class loader.
- `maven-compiler-plugin` dùng `release=17` để biên dịch tương ứng Java 17 khi JDK phù hợp. `maven-surefire-plugin` chạy kiểm thử JUnit Jupiter trong phase `test`.
- `<filtering>false</filtering>` tránh thay thế biểu thức dạng biến trong resource của ví dụ. Không cần bật filtering nếu chỉ sao chép tài nguyên nguyên vẹn.

Cấu hình ở `<build>` thay đường dẫn đầu vào, **không thay vòng đời Maven**. `mvn package` vẫn đi qua các phase cho đến đóng gói; `mvn verify` tiếp tục tới phase xác minh theo các plugin được gắn.

### 4.4. Chạy và kiểm chứng đầu ra

Từ thư mục có `pom.xml`:

```bash
mvn clean verify
java -cp target/classes demo.legacy.App
```

Dòng stdout của **lệnh `java` thứ hai**, nếu resource đúng như ví dụ:

```text
Hello from legacy layout
```

Lệnh Maven đầu tiên tạo nhiều dòng log và chạy một unit test; không nên coi toàn bộ Maven log là một stdout cố định, vì log phụ thuộc phiên bản và môi trường. Khi `verify` thành công, kiểm tra:

```text
target/
├── classes/
│   ├── app.properties
│   └── demo/legacy/App.class
├── test-classes/
│   ├── expected.properties
│   └── demo/legacy/AppTest.class
├── surefire-reports/
│   └── ...
└── legacy-layout-1.0.0.jar
```

Sơ đồ chỉ thể hiện các đầu ra liên quan; Maven/plugin còn có thể tạo thư mục khác. Có thể dùng lệnh này để xem nội dung JAR:

```bash
jar tf target/legacy-layout-1.0.0.jar
```

Trong JAR mong đợi có `demo/legacy/App.class` và `app.properties`, còn `AppTest.class` và `expected.properties` không thuộc artifact chính. Có thể chạy lớp trực tiếp từ JAR bằng `java -cp target/legacy-layout-1.0.0.jar demo.legacy.App`; ví dụ chưa khai báo `Main-Class` trong manifest, nên `java -jar ...` không được mặc định là hoạt động.

Điều quan trọng cần kiểm chứng là **mã nguồn được biên dịch, resource nằm đúng classpath, test thực sự chạy và artifact chứa đúng thứ cần bàn giao**. Một thông báo `BUILD SUCCESS` đơn lẻ chưa đủ nếu Maven vô tình không tìm thấy test hoặc xây JAR rỗng.

## 5. Nhiều thư mục Java: dùng build-helper-maven-plugin

`<build><sourceDirectory>...` chỉ biểu diễn **một thư mục mã nguồn chính**. Nếu dự án có cả `legacy-src` và `extra-src`, hãy giữ source root chính rồi thêm source root phụ bằng Build Helper Maven Plugin. Với nhiều thư mục test, dùng `add-test-source` tương ứng.

Đoạn sau được đặt **bên trong `<build><plugins>` của POM đang có** (không phải một POM độc lập):

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>add-extra-java</id>
            <phase>generate-sources</phase>
            <goals>
                <goal>add-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>extra-src</source>
                </sources>
            </configuration>
        </execution>
        <execution>
            <id>add-extra-tests</id>
            <phase>generate-test-sources</phase>
            <goals>
                <goal>add-test-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>extra-tests</source>
                </sources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

`generate-sources` diễn ra trước `compile`; `generate-test-sources` trước `test-compile`. Việc gắn root bổ sung vào phase phù hợp giúp compiler biết tất cả thư mục cần xét. Nếu các root chồng lấn (ví dụ `sourceDirectory=src` và thêm `src/main/java`), phải thiết kế lại để tránh mã nguồn bị xét trùng hoặc lẫn test vào sản phẩm.

Trong dự án có mã Java được sinh tự động, nên dùng plugin sinh mã gắn vào phase như `generate-sources`, tạo đầu ra trong `target/generated-sources/...` và đăng ký root sinh ra đúng thời điểm trước `compile`. Không biên dịch hoặc commit bừa các tệp đã sinh như thể đó là mã nguồn gốc; mục tiêu là để một lần `mvn clean verify` có thể tái tạo kết quả.

**Lưu ý:** `build-helper-maven-plugin` bổ sung root cho **mã nguồn**; còn `resources` và `testResources` của POM thường đã đủ để khai báo một hoặc nhiều thư mục tài nguyên. Chỉ dùng các goal bổ sung resource của build-helper khi có nhu cầu được xác định rõ.

## 6. Resource không giống Java source

Một lỗi thường gặp khi tích hợp dự án cũ là đặt mọi thứ trong cùng một thư mục và chỉ đổi `sourceDirectory`. Maven Compiler Plugin không tự đóng gói mọi file khác `.java` vào JAR theo cách ứng dụng mong đợi. Resource cần được khai báo trong `resources`.

Nếu dự án giữ **cả** tài nguyên chuẩn và tài nguyên cũ, có thể khai báo hai resource root:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
    </resource>
    <resource>
        <directory>config</directory>
        <filtering>false</filtering>
        <includes>
            <include>**/*.properties</include>
            <include>**/*.xml</include>
        </includes>
    </resource>
</resources>
```

Đoạn này thay thế khối `<resources>` tương ứng ở ví dụ POM trước đó. Khi khai báo `<resources>` rõ ràng, **đừng mặc định tài nguyên trong `src/main/resources` vẫn được tự động cộng thêm**: nếu còn sử dụng thư mục đó thì đưa nó vào danh sách như trên. Điều tương tự áp dụng cho `<testResources>` và `src/test/resources`.

Với `<targetPath>`, có thể điều chỉnh vị trí tương đối của resource dưới thư mục đầu ra. Chẳng hạn `<targetPath>config</targetPath>` sẽ đưa `app.properties` vào `target/classes/config/app.properties`; khi ấy mã dùng classpath phải tìm `config/app.properties` thay vì `app.properties`. Mọi thay đổi đường dẫn resource cần kiểm chứng bằng hành vi thực tế của chương trình và danh sách file trong JAR.

`filtering=true` là một chức năng khác: Maven thay biểu thức trong resource bằng giá trị cấu hình trong quá trình build. Không bật filtering tùy tiện cho tệp nhị phân, khóa bí mật hoặc tệp cần giữ nguyên byte. Tệp cấu hình nhạy cảm của môi trường production không nên tự động được đưa vào artifact chỉ vì toàn bộ thư mục cũ được khai báo là resource root.

## 7. Khi nào nên chuyển thư mục về chuẩn?

**Giữ cấu trúc cũ bằng POM** phù hợp khi cần build chạy ổn định trước, công cụ ngoài đang dùng đường dẫn cũ, hoặc việc đổi cây thư mục gây rủi ro lớn. Tuy nhiên, nhiều ngoại lệ dần làm POM khó đọc, đặc biệt khi các plugin khác vẫn giả định cấu trúc chuẩn.

**Chuyển về cấu trúc Maven** phù hợp khi nhóm có thể cập nhật đường dẫn trong IDE, CI, script đóng gói và tài liệu. Ví dụ chuyển:

```text
legacy-src/demo/legacy/App.java
    -> src/main/java/demo/legacy/App.java

legacy-tests/demo/legacy/AppTest.java
    -> src/test/java/demo/legacy/AppTest.java

config/app.properties
    -> src/main/resources/app.properties

fixtures/expected.properties
    -> src/test/resources/expected.properties
```

Sau khi di chuyển, bỏ các override đã không còn cần thiết; để Maven sử dụng quy ước mặc định, tránh việc cấu hình cũ trỏ vào thư mục trống. Thực hiện thay đổi theo bước nhỏ, so sánh test và thành phần artifact trước/sau. Nếu di chuyển làm thay đổi vị trí resource trong classpath thì cần sửa đường dẫn truy cập trong Java và test tương ứng.

Trường hợp dự án nhiều module, mỗi module có `pom.xml` và source root riêng. Không nên dùng đường dẫn tương đối qua nhiều cấp đến thư mục của module khác chỉ để “lắp” các nguồn vào một module; đó có thể là dấu hiệu cần phân định lại module và dependency. Đường dẫn tương đối trong cấu hình build thông thường phải được hiểu từ gốc của **module POM hiện tại**.

## 8. Những lỗi phổ biến khi tích hợp cấu trúc cũ

| Biểu hiện | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| JAR được tạo nhưng không có lớp ứng dụng | Maven nhìn vào source root trống hoặc sai đường dẫn | Kiểm tra `sourceDirectory`, tên package, lớp trong `target/classes` và JAR |
| Test không chạy, báo 0 test | Test root sai, class không đúng mẫu tên, thiếu provider/plugin hoặc test chưa được nhận diện | Kiểm tra `testSourceDirectory`, tên `*Test`, Surefire reports và dependency test |
| `ClassNotFoundException` khi chạy | Sai tên main class/classpath, đóng gói sai lớp hoặc thiếu dependency runtime | Kiểm tra đường dẫn `.class`, nội dung JAR và lệnh khởi chạy |
| `Missing app.properties` | Resource root không cấu hình, bị lọc bỏ hoặc sai đường dẫn classpath | Kiểm tra `resources`, `target/classes`, `jar tf` và cách đọc resource |
| Test resource xuất hiện trong artifact sản phẩm | Gộp nhầm test resource vào `resources` | Tách `testResources` và kiểm tra JAR |
| Build biên dịch cả test như mã sản phẩm | `sourceDirectory` bao trùm thư mục test | Chia lại roots hoặc di chuyển test riêng |
| Build chạy máy cá nhân nhưng lỗi trong CI | Phụ thuộc đường dẫn tuyệt đối, thư mục làm việc, file không được commit hoặc khác chữ hoa/thường | Dùng đường dẫn tương đối với module, kiểm tra case, bảo toàn file cần thiết |
| `mvn clean` làm mất tệp quan trọng | Mã nguồn hoặc tài nguyên quan trọng bị đặt trong `target` | Đưa nguồn thật ra khỏi thư mục đầu ra; không chỉnh `clean` để che vấn đề |
| Resource chuẩn đột ngột không còn trong JAR | POM khai báo riêng `resources` và bỏ quên thư mục chuẩn | Khai báo đầy đủ các resource root còn được sử dụng |

Nếu lỗi liên quan đến resource, đừng chỉ sửa `java -cp` để “cho chạy được” trên máy cá nhân; cần xác minh đường đi của resource từ cây nguồn → `target/classes`/`target/test-classes` → artifact hoặc test runtime.

## 9. Quy trình kiểm chứng sau khi đổi cấu trúc

Thực hiện lần lượt từ gốc module:

1. **Kiểm tra POM hiệu lực:** chạy `mvn help:effective-pom` để xem cấu hình thực tế sau khi kế thừa parent POM, profile và quản lý plugin. Nếu lưu kết quả ra tệp, chỉ dùng để kiểm tra; không sửa POM dựa trên suy đoán.
2. **Build từ trạng thái sạch:** chạy `mvn clean verify`. Với JAR ví dụ, lệnh này biên dịch mã sản phẩm, xử lý resources, biên dịch/chạy test và đóng gói theo cấu hình.
3. **Kiểm tra số test:** xem `target/surefire-reports` hoặc phần tổng kết Surefire. Build thành công nhưng `Tests run: 0` chưa chứng minh cấu hình test đúng.
4. **Kiểm tra lớp và tài nguyên:** kiểm tra `target/classes`, `target/test-classes`; so sánh vị trí resource với đường dẫn mà Java đọc từ classpath.
5. **Mở artifact:** dùng `jar tf target/legacy-layout-1.0.0.jar`; chắc chắn lớp sản phẩm và resource cần thiết có mặt, còn nguồn test và fixture không bị đóng gói nhầm.
6. **Chạy hành vi thật:** dùng classpath phù hợp để chạy main class hoặc chạy đúng cơ chế ứng dụng sử dụng trong môi trường triển khai. Kiểm tra kết quả và lỗi thiếu resource/dependency.
7. **Kiểm tra môi trường khác:** chạy lại trong CI sạch và hệ điều hành mục tiêu. Tránh dựa vào output tạm, IDE tự thêm source root, hoặc tệp không nằm trong version control.

Với dự án nhiều module, cần chạy từ đúng reactor/đúng module và kiểm tra build của module phụ thuộc; không kết luận toàn bộ repository ổn chỉ vì một module đã `compile`.

## 10. Nguyên tắc quyết định

Khi cần tích hợp mã nguồn Java hiện có, hãy xác định **đầu vào thật của build** trước: mã sản phẩm, mã test, tài nguyên sản phẩm, tài nguyên test, nguồn sinh tự động và đầu ra. Sau đó chọn ít thay đổi nhất để Maven hiểu đúng các đầu vào đó.

Sử dụng `sourceDirectory` và `testSourceDirectory` cho một root Java tương ứng; `resources` và `testResources` cho file không biên dịch; `build-helper-maven-plugin` khi có nhiều root Java; plugin chuyên biệt khi cần xử lý WAR, mã sinh, tích hợp kiểm thử hoặc bước đóng gói đặc biệt. Giữ `target` làm đầu ra, kiểm tra cả lớp, tài nguyên, test và artifact sau khi build. Khi ràng buộc cũ không còn, đưa cây thư mục về quy ước Maven và xóa cấu hình ngoại lệ không cần thiết.

### Tài liệu tham khảo

- [Apache Maven — Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout)
- [Apache Maven — POM Reference, Build và Resources](https://maven.apache.org/pom.html)
- [MojoHaus — Build Helper Maven Plugin: thêm source/test source roots](https://www.mojohaus.org/build-helper-maven-plugin/usage.html)
- [Apache Maven — Resources Plugin](https://maven.apache.org/plugins/maven-resources-plugin/)
- [Apache Maven — Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
