# Các phase chuẩn bị, biên dịch và thực thi kiểm thử trong Maven

## 1. Hiểu dòng chảy từ mã nguồn đến kết quả kiểm thử

Một dự án Java trước khi có thể kiểm thử cần trải qua nhiều công việc: chuẩn bị tài nguyên, biên dịch mã sản phẩm, chuẩn bị tài nguyên kiểm thử, biên dịch mã kiểm thử rồi mới thực thi các bài test. Maven tổ chức công việc đó thành **các phase có thứ tự** trong vòng đời build mặc định (`default lifecycle`).

Ví dụ, khi chạy:

```bash
mvn test
```

Maven không đơn giản “mở test rồi chạy”. Nó duyệt các phase trước và tới `test`, trong đó các **plugin goal** đã được gắn vào phase thực hiện công việc thật. Với một dự án Java dùng `packaging=jar`, đường đi thường thấy là:

```text
validate
  ↓
initialize / generate-sources / process-sources / generate-resources
  ↓
process-resources        → sao chép tài nguyên sản phẩm
  ↓
compile                  → biên dịch Java sản phẩm
  ↓
process-classes / generate-test-sources / process-test-sources
  ↓
generate-test-resources / process-test-resources
                           → chuẩn bị tài nguyên kiểm thử
  ↓
test-compile             → biên dịch Java kiểm thử
  ↓
process-test-classes
  ↓
test                     → thực thi kiểm thử đơn vị
```

Đây là **thứ tự phase**, không có nghĩa tất cả phase đều có tác vụ cụ thể trong mọi dự án. Một phase có thể không làm gì nếu không được gắn plugin goal. Bản chất của Maven là kết hợp **mốc chuẩn của vòng đời** với **plugin thực thi thao tác**. Nếu chạy `mvn compile`, Maven đi đến `compile` và dừng; nếu chạy `mvn test`, Maven đi tiếp tới `test`.

## 2. Phân biệt phase, goal và lệnh Maven

| Khái niệm | Ví dụ | Nghĩa |
| --- | --- | --- |
| Lifecycle | `default`, `clean` | Chuỗi các phase được Maven định nghĩa |
| Phase | `process-resources`, `compile`, `test-compile`, `test` | Mốc trong vòng đời; lệnh gọi phase chạy các phase trước nó |
| Plugin | Maven Resources Plugin, Maven Compiler Plugin, Maven Surefire Plugin | Thành phần chứa logic thực thi |
| Plugin goal | `resources:resources`, `compiler:compile`, `compiler:testCompile`, `surefire:test` | Công việc cụ thể do plugin thực hiện |
| CLI gọi phase | `mvn test` | Đi qua các phase của vòng đời `default` đến `test` |
| CLI gọi goal trực tiếp | `mvn surefire:test` | Yêu cầu goal đó; không mặc định dựng toàn bộ đầu vào mà các phase trước tạo |

**Đừng đồng nhất `test` phase với `surefire:test` goal.** Trong dự án JAR thông thường, goal Surefire được gắn vào phase `test`, nhưng lệnh gọi trực tiếp goal có thể không chạy các bước biên dịch và chuẩn bị trước đó. Ngược lại, `mvn test` có thể thực hiện thêm goal của những plugin khác do POM cấu hình.

Maven có ba lifecycle chính: `clean`, `default` và `site`. Lệnh `mvn clean test` lần lượt yêu cầu phase `clean` của clean lifecycle và phase `test` của default lifecycle. `clean` xóa đầu ra build được quản lý, không phải phase đứng ngay trước `compile` trong default lifecycle.

## 3. Các phase chuẩn bị cho việc biên dịch

### 3.1. `validate` và `initialize`

- `validate`: Maven xác nhận thông tin và cấu hình dự án cần thiết cho build hợp lệ ở mức vòng đời/phần thực thi có liên quan. Không nên hiểu phase này tự thực hiện toàn bộ kiểm tra chất lượng mã nguồn, định dạng, bảo mật hoặc dependency.
- `initialize`: mốc để các plugin chuẩn bị trạng thái build, thuộc tính hoặc thư mục khi dự án có cấu hình phù hợp. Trong dự án JAR tối giản, phase này có thể không có goal đáng chú ý.

Một số dự án thêm plugin kiểm tra quy tắc, phiên bản Java hoặc cấu hình ở `validate`. Việc đó đến từ **binding và cấu hình plugin của dự án**, không phải vì phase tự có khả năng kiểm tra mọi vấn đề.

### 3.2. `generate-sources` và `process-sources`

- `generate-sources`: nơi hợp lý để plugin sinh mã Java từ schema, protobuf, OpenAPI hoặc đầu vào được kiểm soát, rồi đăng ký source root trước bước compile.
- `process-sources`: dành cho các thao tác xử lý nguồn có chủ đích trước khi biên dịch.

Không nên ghi mã đã sinh vào `src/main/java` bằng một script tùy tiện nếu dự án có thể dùng thư mục như `target/generated-sources` và plugin đăng ký root đúng thời điểm. Điều này giúp `mvn clean compile` tạo lại mã sau khi xóa `target` và tránh khiến IDE/CI phụ thuộc đầu ra cũ.

**Lưu ý:** gắn một plugin vào `generate-sources` không tự động bảo đảm các tệp được tạo ra trở thành Java source root. Plugin sinh mã hoặc build-helper phải khai báo/đăng ký nguồn cho bước compiler phù hợp.

### 3.3. `generate-resources` và `process-resources`

- `generate-resources`: điểm chuẩn bị hoặc sinh resource khi có plugin được cấu hình.
- `process-resources`: thông thường chạy `maven-resources-plugin:resources` để sao chép/lọc resource sản phẩm từ `src/main/resources` vào `target/classes` trong dự án JAR.

Giả sử có:

```text
src/main/resources/app.properties
```

với nội dung:

```properties
target=Maven
```

Sau khi chạy `mvn process-resources`, tệp dự kiến nằm ở:

```text
target/classes/app.properties
```

Tệp properties **không phải tệp Java cần biên dịch**. Nó được đưa vào classpath sản phẩm, để ứng dụng có thể đọc bằng class loader. Maven không tự tạo bản sao của mọi tệp ở mọi thư mục; nguồn resource và bộ lọc lấy từ cấu hình POM và các quy ước đang có hiệu lực.

Nếu trong `pom.xml` bật filtering cho resource, nội dung có thể được thay thế theo thuộc tính Maven. Với resource cần giữ nguyên byte hoặc chứa định dạng nhị phân, phải cân nhắc kỹ filtering, include/exclude và encoding.

## 4. Phase `compile`: tạo lớp Java sản phẩm

Với `packaging=jar` thông thường, goal mặc định được gắn vào `compile` là `compiler:compile` của Maven Compiler Plugin. Plugin lấy mã Java từ `src/main/java` (hoặc source roots đã khai báo), dùng JDK/compiler phù hợp và ghi tệp `.class` vào `target/classes`.

Ví dụ:

```text
src/main/java/demo/lifecycle/App.java
    ↓ compiler:compile
target/classes/demo/lifecycle/App.class
```

Cần phân biệt ba thành phần:

- **Nguồn Java:** tệp `.java` dưới source root sản phẩm.
- **Đầu ra của compiler:** tệp `.class` cùng cấu trúc package dưới `target/classes`.
- **Artifact đóng gói:** tệp JAR/WAR được tạo ở phase sau, thường là `package`; chạy đến `compile` chưa nhất thiết có JAR.

Khi mã có dependency để biên dịch, Maven tính compile classpath từ các dependency và scope thích hợp. Dependency chỉ dùng cho test không mặc nhiên trở thành thư viện sản phẩm. Biên dịch có thể thất bại vì sai Java release, thiếu thư viện, lỗi cú pháp hoặc thiếu mã được sinh ở phase trước.

**Ví dụ chốt Java 17:** dùng thuộc tính `maven.compiler.release` hoặc cấu hình `<release>17</release>` cho Maven Compiler Plugin, và bảo đảm JDK được Maven sử dụng có khả năng biên dịch cho Java 17. Maven không tự nâng/hạ phiên bản JDK của máy chỉ vì thay đổi POM.

## 5. Chuẩn bị và biên dịch mã kiểm thử

Sau `compile`, Maven còn một chuỗi phase riêng cho test:

| Phase | Ý nghĩa trong dự án Java |
| --- | --- |
| `process-classes` | Có thể xử lý lớp Java đã biên dịch, ví dụ tăng cường bytecode, khi có plugin |
| `generate-test-sources` | Sinh thêm mã nguồn test nếu cần |
| `process-test-sources` | Xử lý nguồn test trước biên dịch nếu được cấu hình |
| `generate-test-resources` | Sinh tài nguyên dành cho test |
| `process-test-resources` | Thông thường gọi `resources:testResources`, chép `src/test/resources` vào `target/test-classes` |
| `test-compile` | Thông thường gọi `compiler:testCompile` để biên dịch `src/test/java` vào `target/test-classes` |
| `process-test-classes` | Cho phép xử lý lớp test đã biên dịch nếu có plugin |
| `test` | Thông thường gọi `surefire:test` để thực thi unit test |

Hai điểm quan trọng:

1. `test-compile` chỉ đảm bảo **biên dịch mã test**, không có nghĩa test đã chạy. Một bộ test biên dịch thành công vẫn có thể thất bại khi thực thi vì logic sai, dữ liệu sai, lỗi môi trường hoặc ngoại lệ.
2. Classpath test thường có quyền thấy lớp sản phẩm trong `target/classes`, lớp test/resource test trong `target/test-classes` và các dependency test. Resource test không nên được đưa nhầm vào JAR sản phẩm.

Sự tách biệt này cho phép dự án dùng test framework như JUnit Jupiter mà không kéo thư viện unit test vào dependency runtime của artifact ứng dụng. Tuy nhiên, việc một test được Maven nhận diện và chạy hay không còn phụ thuộc plugin Surefire, framework/engine, tên lớp và cấu hình.

## 6. Phase `test`: thực thi kiểm thử đơn vị

Khi phase `test` chạy trong dự án Java JAR thông thường, Maven Surefire Plugin thực thi test theo cấu hình và test engine phù hợp, thường thông qua các tên lớp như `*Test`. Surefire cung cấp log kết quả và các báo cáo trong `target/surefire-reports`.

Một build có thể **biên dịch thành công nhưng kiểm thử thất bại**. Khi test trả kết quả không đúng hoặc ném exception không mong đợi, Surefire thường báo thất bại làm quá trình Maven dừng với mã thoát khác 0, trừ khi dự án cố ý cấu hình bỏ qua lỗi hoặc bỏ qua test.

Không được xem thông báo `BUILD SUCCESS` là bằng chứng “tất cả test đã chạy” nếu repository có cấu hình skip, không tìm thấy test hoặc chạy một phần test. Cần xem báo cáo thực tế: số test chạy, số lỗi và số test bị bỏ qua.

### Vì sao `mvn test` không đòi đóng gói?

Phase `test` đứng **trước `package`** trong default lifecycle, nên unit test thông thường chạy dựa trên lớp đã biên dịch và dependency cần thiết, không cần JAR sản phẩm đã đóng gói. Còn kiểm thử tích hợp đòi khởi động ứng dụng đã đóng gói có thể cần phase về sau như `integration-test` và `verify`, cùng Maven Failsafe Plugin hoặc cấu hình khác. Không nên mặc định Surefire sẽ thực hiện toàn bộ kiểm thử tích hợp hoặc triển khai.

## 7. Ví dụ Java 17 và JUnit 5: chạy từng phase và quan sát bằng chứng

Ví dụ sau có thể tạo thành **một dự án Maven độc lập**. Nó dùng một chương trình Java đọc resource, một lớp unit test và phiên bản plugin được khai báo cụ thể để tránh việc máy khác lấy plugin mặc định không phù hợp. Các phiên bản chỉ là mốc ví dụ có thể tái lập, không phải lời khẳng định mới nhất.

### 7.1. Cây thư mục

```text
lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/lifecycle/App.java
    │   └── resources/
    │       └── app.properties
    └── test/
        └── java/
            └── demo/lifecycle/AppTest.java
```

### 7.2. Mã sản phẩm

Tệp `src/main/java/demo/lifecycle/App.java`:

```java
package demo.lifecycle;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static String message(String name) {
        return "Hello, " + name;
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input = App.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            properties.load(input);
        }

        System.out.println(message(properties.getProperty("target")));
    }
}
```

Tệp `src/main/resources/app.properties`:

```properties
target=Maven
```

Ở `process-resources`, Maven sao chép `app.properties` vào `target/classes`. Ở `compile`, Maven tạo `App.class`. Khi chạy chương trình với classpath trỏ tới `target/classes`, Java thấy cả lớp biên dịch và resource.

### 7.3. Mã kiểm thử

Tệp `src/test/java/demo/lifecycle/AppTest.java`:

```java
package demo.lifecycle;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void greetingMaven() {
        assertEquals("Hello, Maven", App.message("Maven"));
    }

    @Test
    void greetingJava() {
        assertEquals("Hello, Java", App.message("Java"));
    }
}
```

Hai phương thức dùng JUnit Jupiter. Test kiểm tra hàm thuần `message()` nên không phụ thuộc vào thứ tự chạy hoặc mạng. Tên `AppTest` giúp Surefire nhận diện theo quy tắc mặc định khi dùng plugin và test framework phù hợp.

### 7.4. POM hoàn chỉnh

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
```

POM khai báo `junit-jupiter` với `scope=test`, nên test có cả API và engine cần thiết mà mã sản phẩm không phải dùng JUnit. Maven Surefire Plugin `3.2.5` hỗ trợ thực thi JUnit Platform/Jupiter. Maven Compiler Plugin dùng thuộc tính `maven.compiler.release=17` để biên dịch theo Java 17; phải có JDK hỗ trợ release đó.

Không cần gắn `<executions>` cho các goal cơ bản trên vì `packaging=jar` đã có **binding mặc định** cho các phase tương ứng. Việc khai báo plugin ở đây chủ yếu giúp cố định phiên bản.

### 7.5. Chạy từng mốc để thấy sự khác biệt

Các lệnh dưới đây **mỗi lệnh nên được hiểu như một lượt chạy riêng**. Để quan sát rõ ảnh hưởng của từng phase, có thể thêm `clean` trước một lệnh cụ thể. Chạy tại thư mục chứa `pom.xml` và sử dụng Maven tương thích, JDK 17, kết nối repository khi lần đầu cần tải plugin/dependency.

**Chỉ chuẩn bị resource sản phẩm:**

```bash
mvn clean process-resources
```

Sau lệnh này, cần có `target/classes/app.properties`. Chưa yêu cầu chạy `compile` nên không nên mặc định có `target/classes/demo/lifecycle/App.class`.

**Biên dịch lớp sản phẩm:**

```bash
mvn clean compile
```

Maven chạy các phase trước `compile`, bao gồm xử lý resources, rồi biên dịch `App.java`. Kiểm tra `target/classes/demo/lifecycle/App.class`.

**Biên dịch test nhưng chưa chạy test:**

```bash
mvn clean test-compile
```

Maven chuẩn bị và biên dịch test; sau lệnh này thường có `target/test-classes/demo/lifecycle/AppTest.class`. Chưa đến phase `test` nên không nên kết luận test đã chạy.

**Thực thi test:**

```bash
mvn clean test
```

Với cấu hình và mã đúng như ví dụ, Surefire chạy **2 test, 0 failure, 0 error**; số test có thể xác minh trong `target/surefire-reports`. Thứ tự và định dạng các dòng log Maven có thể khác theo môi trường; không nên gán một đoạn stdout Maven cố định cho mọi lần build.

Để chạy chương trình sau khi đã biên dịch:

```bash
java -cp target/classes demo.lifecycle.App
```

Stdout của chương trình Java này là:

```text
Hello, Maven
```

Có thể dùng `mvn clean package` để chạy qua test rồi tạo `target/lifecycle-demo-1.0.0.jar`. Ví dụ chưa cấu hình `Main-Class` trong manifest, nên muốn chạy trực tiếp nội dung JAR phải gọi đủ tên lớp:

```bash
java -cp target/lifecycle-demo-1.0.0.jar demo.lifecycle.App
```

Tệp `app.properties` cũng phải được đóng gói vào JAR để cách chạy này hoạt động; với cấu hình trên, Maven xử lý resources trước khi tạo JAR. Dùng `jar tf target/lifecycle-demo-1.0.0.jar` để kiểm tra các entry.

## 8. Phase nào chạy khi gõ những lệnh thường gặp?

| Lệnh | Những gì Maven cố thực hiện trong mặc định JAR |
| --- | --- |
| `mvn validate` | Đến `validate`; chưa yêu cầu biên dịch |
| `mvn process-resources` | Qua các phase chuẩn bị tới xử lý resource sản phẩm |
| `mvn compile` | Qua xử lý resource, biên dịch Java sản phẩm |
| `mvn test-compile` | Qua biên dịch sản phẩm, xử lý test resources, biên dịch mã test |
| `mvn test` | Qua mọi phase trên và thực thi unit test qua plugin tương ứng |
| `mvn package` | Qua `test` rồi đóng gói khi các bước trước thành công |
| `mvn verify` | Qua `package` và các phase kiểm tra tích hợp được cấu hình tới `verify` |
| `mvn clean test` | Chạy clean lifecycle rồi default lifecycle tới `test` |

Điều kiện **khi các bước trước thành công** rất quan trọng. Nếu `compile` thất bại, Maven thông thường dừng và chưa đến `test-compile` hay `test`. Nếu unit test thất bại và Surefire không được cấu hình bỏ qua lỗi, quá trình không đi tiếp tới `package`.

Lệnh gọi một phase luôn bao gồm các phase **đứng trước trong cùng lifecycle**, nhưng các plugin goal thực tế phụ thuộc vào packaging, POM hiệu lực, cấu hình plugin và profile. Chẳng hạn dự án `packaging=pom` không tự biên dịch Java như một module JAR, và một dự án web WAR có goal đóng gói khác JAR.

## 9. Lỗi thường gặp khi làm việc với compile và test

### 9.1. “Đã chạy `mvn test` mà không thấy test nào”

Kiểm tra:

- File test có ở `src/test/java` hoặc test source roots đã cấu hình không?
- Tên lớp có khớp quy tắc nhận diện mặc định của Surefire (ví dụ `AppTest`) không?
- Có dependency `junit-jupiter` hoặc test engine phù hợp và phiên bản Surefire hỗ trợ JUnit Jupiter không?
- Có bật `-DskipTests`, `-Dmaven.test.skip=true`, profile hoặc cấu hình loại trừ test không?
- Báo cáo trong `target/surefire-reports` có ghi nhận test nào không?

Không sửa bằng cách thêm một phase tùy ý nếu vấn đề thật sự là test discovery hoặc test engine.

### 9.2. “`mvn compile` thành công nhưng test không chạy”

Đây là kết quả đúng theo vòng đời: `compile` xảy ra trước `test-compile` và `test`. Hãy chạy `mvn test` hoặc `mvn verify` tùy mục tiêu. Đừng dùng `mvn compiler:testCompile` như thay thế cho unit test, vì goal này chỉ biên dịch.

### 9.3. “`mvn surefire:test` lỗi vì chưa có lớp test”

Gọi goal trực tiếp không mặc định biên dịch lại mã và test từ trạng thái sạch. Nếu mục tiêu là một lượt kiểm thử độc lập và lặp lại được, dùng `mvn test` để Maven tạo trước các đầu vào cần thiết.

### 9.4. “`mvn package` vẫn thành công mặc dù không thấy test thực thi”

Kiểm tra cấu hình skip, tên test, số lượng test và báo cáo Surefire. `package` chỉ chứng minh các goal thực sự được cấu hình trong build đã hoàn tất. Nếu test bị bỏ qua hoặc không có test được nhận diện, tạo JAR thành công không tương đương kiểm thử đã bao phủ đầy đủ hành vi.

### 9.5. Phân biệt hai cách bỏ qua test

- `mvn package -DskipTests`: trong cấu hình plugin phổ biến, bỏ qua **thực thi** test với Surefire, nhưng mã test thường vẫn được biên dịch.
- `mvn package -Dmaven.test.skip=true`: các plugin Maven Compiler, Surefire và Failsafe hỗ trợ property này để bỏ qua cả **biên dịch lẫn thực thi** test.

Hai lựa chọn có hệ quả khác nhau, đặc biệt khi mã test chưa biên dịch được. Không lạm dụng chúng trong CI nhằm che các lỗi kiểm thử; nếu cần tạm bỏ qua trong quy trình có chủ đích, ghi rõ phạm vi và bước xác minh bù lại.

### 9.6. Mã Java 17 không biên dịch trên CI

Xem JDK Maven thực sự dùng qua `mvn -version`; kiểm tra `maven.compiler.release`, biến `JAVA_HOME`, toolchain Maven (nếu dùng) và môi trường CI. Đặt `release=17` trong POM không tự tải một JDK mới và không khiến JDK cũ hỗ trợ biên dịch Java 17.

### 9.7. Resource tồn tại trong source nhưng chương trình không thấy

Xem `target/classes` sau `process-resources`, xác nhận `src/main/resources` được khai báo/không bị loại trừ, đường dẫn logic của `getResourceAsStream`, filtering và nội dung JAR sau `package`. Resource của test nằm ở `src/test/resources` được xử lý riêng bởi `process-test-resources`.

## 10. Mở rộng quy trình: mã sinh, test tích hợp và CI

Đối với mã sinh tự động, nên gắn plugin sinh mã vào `generate-sources` và đăng ký source root trước `compile`. Với test cần dữ liệu tạo sẵn, có thể gắn plugin chuẩn bị fixture vào phase thích hợp trước `test`, nhưng phải bảo đảm nhiệm vụ tạo ra dữ liệu ổn định, có thể chạy lại và không phụ thuộc thứ tự ngầm.

**Unit test và integration test không bắt buộc chạy cùng một phase.** Theo cách tổ chức thông thường, Surefire phục vụ unit test ở `test`, còn Maven Failsafe Plugin có thể thực thi test tích hợp ở `integration-test` và kiểm tra kết quả ở `verify`. Không gắn goal kiểm thử tích hợp vào `integration-test` một cách tùy tiện mà bỏ qua phase `verify` nếu điều đó làm sai cách Failsafe báo kết quả và dọn tài nguyên. Từ `mvn test` không thể suy ra integration test đã chạy.

Với CI, lệnh thường dùng để kiểm tra một dự án Java trước khi bàn giao là:

```bash
mvn -B clean verify
```

`-B` bật chế độ batch phù hợp CI. `clean` giúp giảm nguy cơ phụ thuộc đầu ra cũ; `verify` đi qua phase đóng gói và các bước xác minh được cấu hình. Dù vậy, mỗi dự án phải kiểm tra thật các plugin/goal và báo cáo test: không phải cứ `verify` thành công là Maven đã tự chạy kiểm thử tích hợp, kiểm tra coverage hoặc kiểm tra bảo mật khi các công việc đó chưa được gắn vào vòng đời.

Trong dự án nhiều module, Maven reactor còn xem xét quan hệ phụ thuộc giữa các module. Thứ tự các module được build và các phase bên trong từng module là hai lớp điều phối khác nhau; nên xem log reactor và kết quả từng module khi điều tra lỗi.

## 11. Cách đọc log để biết Maven dừng ở đâu

Trong log mặc định của dự án JAR, các dòng có dạng tương tự:

```text
--- resources:...:resources (...) @ lifecycle-demo ---
--- compiler:...:compile (...) @ lifecycle-demo ---
--- resources:...:testResources (...) @ lifecycle-demo ---
--- compiler:...:testCompile (...) @ lifecycle-demo ---
--- surefire:...:test (...) @ lifecycle-demo ---
```

Các dấu `...` ở đây là **ký hiệu minh họa** cho phiên bản và execution id thực tế, không phải log nguyên văn sẽ xuất hiện. Log giúp xác định plugin goal nào chạy và phase tương ứng thông qua POM/binding. Nếu gặp lỗi, kiểm tra dòng lỗi đầu tiên có ý nghĩa, plugin/goal đang chạy và điều kiện đầu vào trước khi sửa.

| Điểm dừng | Cần kiểm tra |
| --- | --- |
| `process-resources` | Đường dẫn resource, filtering, encoding và tệp bị thiếu |
| `compile` | Java syntax, `release`, dependency compile, source roots |
| `process-test-resources` | Fixture và tài nguyên test |
| `test-compile` | JUnit/test dependency, test source roots, tên package/lớp |
| `test` | Assertion, lỗi runtime, test engine/provider, test discovery và kết quả Surefire |

Khi lỗi thuộc một plugin goal, xem tài liệu đúng phiên bản plugin và POM hiệu lực bằng `mvn help:effective-pom` nếu cần. Thêm `-X` để xem log debug khi việc chẩn đoán đòi hỏi, nhưng cân nhắc dữ liệu môi trường có thể xuất hiện trong log được chia sẻ.

## 12. Ghi nhớ khi thiết kế build Maven

- **Các phase là mốc chuẩn có thứ tự:** chuẩn bị → xử lý resources → compile → chuẩn bị test → test-compile → test. Gọi một phase thường đi qua các phase trước nó.
- **Plugin goal mới làm việc thật:** `resources:resources`, `compiler:compile`, `resources:testResources`, `compiler:testCompile`, `surefire:test` là những binding điển hình cho dự án Java với `packaging=jar`.
- **Mã sản phẩm và mã test có đầu ra khác nhau:** `target/classes` và `target/test-classes`; build giữ classpath và dependency scope tương ứng.
- **`mvn test` không giống `mvn compile` hay `mvn package`:** mỗi lệnh dừng ở mốc khác nhau và tạo mức bằng chứng khác nhau.
- **Đánh giá chất lượng dựa trên kết quả thực:** kiểm tra số test đã chạy và báo cáo, không chỉ thông báo build thành công hoặc việc có file JAR.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle và lifecycle reference](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to the Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html)
- [Apache Maven Compiler Plugin — Java release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Apache Maven Resources Plugin](https://maven.apache.org/plugins/maven-resources-plugin/)
- [Apache Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html)
