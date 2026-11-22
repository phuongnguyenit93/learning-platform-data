# Viết mã nguồn và kiểm thử theo cấu trúc Maven

## 1. Mục tiêu: biến một thư mục mã Java thành dự án có thể xây dựng và kiểm chứng

Khi viết một chương trình Java nhỏ, ta có thể đặt tất cả tệp `.java` cạnh nhau và gọi `javac` thủ công. Nhưng khi dự án phát triển, cần phân biệt mã ứng dụng, mã kiểm thử, tài nguyên và thư viện phụ thuộc; đồng thời mọi thành viên cần chạy được cùng một quy trình build. **Maven** giải quyết vấn đề này bằng hai quy ước cốt lõi:

1. **Cấu trúc thư mục chuẩn**: Maven biết tìm mã nguồn chính, mã kiểm thử và tài nguyên ở đâu.
2. **`pom.xml`**: mô tả danh tính dự án, phiên bản Java, thư viện phụ thuộc và các plugin build.

Trong bài này, bạn sẽ tạo một dự án Maven `jar` dùng **Java 17**, viết một lớp xử lý lời chào, gọi nó từ hàm `main`, kiểm thử bằng **JUnit Jupiter 5**, chạy lệnh Maven, đọc kết quả và hiểu tệp nào được đưa vào JAR.

Dòng công việc cần nắm:

```text
Viết pom.xml và mã nguồn ở src/main/java
                |
                v
       mvn compile  --> target/classes
                |
                v
Viết kiểm thử ở src/test/java
                |
                v
       mvn test     --> target/test-classes + surefire-reports
                |
                v
       mvn package  --> target/hello-maven-1.0.0-SNAPSHOT.jar
```

Đây là các mốc trong vòng đời build, không phải các thao tác phải luôn gọi riêng từng lần. Chẳng hạn `mvn package` thông thường đã chạy bước biên dịch và kiểm thử trước khi tạo JAR.

## 2. Chuẩn bị môi trường và hiểu cấu trúc dự án

Bạn cần **JDK 17 trở lên** và Maven có thể gọi được trong terminal. Kiểm tra:

```bash
java -version
javac -version
mvn -version
```

`mvn -version` cần cho thấy Maven sử dụng JDK phù hợp. Nếu terminal dùng JDK cũ, hãy sửa `JAVA_HOME` và `PATH` trước khi build. Lần chạy Maven đầu tiên có thể cần mạng để tải plugin và thư viện về kho cục bộ (thường là `~/.m2/repository`).

Tạo thư mục dự án `hello-maven` và các tệp theo sơ đồ sau, bằng IDE hoặc trình quản lý tệp:

```text
hello-maven/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── dev/
    │           └── study/
    │               └── maven/
    │                   ├── WelcomeService.java
    │                   └── App.java
    └── test/
        └── java/
            └── dev/
                └── study/
                    └── maven/
                        └── WelcomeServiceTest.java
```

Ý nghĩa từng vị trí:

| Đường dẫn | Chứa gì? | Maven xử lý như thế nào? |
| --- | --- | --- |
| `pom.xml` | Tên, phiên bản, dependency và plugin | Maven đọc để xác định cách build |
| `src/main/java` | Mã Java của ứng dụng/thư viện | Biên dịch ở phase `compile` |
| `src/main/resources` | Tài nguyên ứng dụng (nếu có): `.properties`, văn bản, cấu hình | Sao chép vào `target/classes`; thường được đóng gói cùng sản phẩm |
| `src/test/java` | Mã kiểm thử Java | Biên dịch ở `test-compile`, chạy bằng công cụ kiểm thử ở `test` |
| `src/test/resources` | Dữ liệu hoặc cấu hình dành riêng cho kiểm thử | Sao chép vào `target/test-classes`; không mặc định được đóng vào JAR chính |
| `target/` | Tệp sinh ra: class, báo cáo test, JAR | Maven tạo khi build; thường không commit vào Git |

Hai thư mục `resources` **không bắt buộc phải tồn tại** nếu bài thực hành chưa dùng tài nguyên. Đường dẫn `dev/study/maven` tương ứng với khai báo `package dev.study.maven;` ở đầu mỗi tệp Java trong ví dụ. Tên gói Java và `groupId` là hai khái niệm khác nhau, nhưng dùng tên nhất quán giúp dự án dễ hiểu.

**Nguyên tắc quan trọng:** giữ mã kiểm thử trong `src/test/java`. Nhờ đó Maven có thể đặt JUnit vào classpath của bước kiểm thử mà không đưa thư viện test vào phụ thuộc chạy thông thường của ứng dụng.

## 3. Khai báo `pom.xml` tối thiểu nhưng chạy kiểm thử được

Tạo `hello-maven/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.study</groupId>
    <artifactId>hello-maven</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
        <plugins>
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

Đọc từng thành phần theo tác dụng thực tế:

- `groupId:artifactId:version` là **tọa độ Maven** của artifact, ở đây `dev.study:hello-maven:1.0.0-SNAPSHOT`. `SNAPSHOT` biểu thị phiên bản đang phát triển.
- `<packaging>jar</packaging>` quy định sản phẩm chính là JAR; với cấu hình này tên mặc định là `hello-maven-1.0.0-SNAPSHOT.jar`.
- `maven.compiler.release=17` yêu cầu Compiler Plugin biên dịch theo ngôn ngữ/API Java 17 (phải chạy với một JDK hỗ trợ release này).
- `project.build.sourceEncoding=UTF-8` xác định cách đọc mã nguồn, quan trọng khi có chuỗi tiếng Việt trong Java.
- Dependency `org.junit.jupiter:junit-jupiter` cung cấp API và thành phần chạy kiểm thử JUnit Jupiter. `scope=test` làm nó sẵn có khi biên dịch/chạy test, không biến JUnit thành dependency runtime của ứng dụng.
- `maven-compiler-plugin` xử lý biên dịch; `maven-surefire-plugin` tìm và chạy unit test trong phase `test`. Ghim phiên bản plugin giúp cách build ổn định hơn giữa các môi trường.

**Phân biệt:** `<dependencies>` là thư viện mà mã ứng dụng/test dùng; `<build><plugins>` là công cụ Maven thực thi trong quá trình build. Chỉ khai báo JUnit nhưng không có mã `@Test` thì Maven không tự tạo ra bài kiểm thử.

## 4. Viết mã nguồn chính trong `src/main/java`

Tạo `src/main/java/dev/study/maven/WelcomeService.java`:

```java
package dev.study.maven;

public final class WelcomeService {
    public String messageFor(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không được để trống");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

Lớp này có một trách nhiệm cụ thể: tạo thông điệp chào. `name.isBlank()` kiểm tra chuỗi chỉ gồm khoảng trắng; `name.strip()` bỏ khoảng trắng ở đầu/cuối. Cả hai có sẵn trên Java 17. Điều kiện `name == null || name.isBlank()` an toàn vì toán tử `||` không gọi vế phải khi `name` là `null`.

Tạo `src/main/java/dev/study/maven/App.java`:

```java
package dev.study.maven;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Maven" : args[0];
        WelcomeService service = new WelcomeService();
        System.out.println(service.messageFor(name));
    }
}
```

`App` là điểm bắt đầu chương trình, còn quy tắc tạo lời chào ở `WelcomeService`. Tách phần logic ra một lớp độc lập giúp test không phải khởi động cả ứng dụng hoặc chặn/đọc `System.out` để kiểm tra kết quả.

Tại thư mục gốc `hello-maven`, chạy:

```bash
mvn compile
java -cp target/classes dev.study.maven.App
java -cp target/classes dev.study.maven.App Lan
```

Hai lệnh `java` lần lượt in đúng:

```text
Xin chào, Maven!
```

```text
Xin chào, Lan!
```

`mvn compile` tạo `target/classes/dev/study/maven/WelcomeService.class` và `App.class`. Tham số `-cp target/classes` báo Java tìm lớp đã biên dịch ở đâu; sau đó `dev.study.maven.App` là **tên lớp đầy đủ**, gồm `package` và tên lớp. `compile` chưa biên dịch/chạy mã trong `src/test/java`.

Nếu không thấy được dấu tiếng Việt trong terminal Windows, hãy kiểm tra cấu hình bảng mã hiển thị của terminal; điều đó khác với lỗi biên dịch hoặc sai giá trị chuỗi trong Java.

## 5. Viết kiểm thử trong `src/test/java` bằng JUnit 5

Tạo `src/test/java/dev/study/maven/WelcomeServiceTest.java`:

```java
package dev.study.maven;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class WelcomeServiceTest {
    private final WelcomeService service = new WelcomeService();

    @Test
    void trimsSpacesBeforeGreeting() {
        assertEquals("Xin chào, Lan!", service.messageFor("  Lan  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> service.messageFor("   "));
    }

    @Test
    void rejectsNullName() {
        assertThrows(IllegalArgumentException.class,
                () -> service.messageFor(null));
    }
}
```

Đây là một lớp kiểm thử **độc lập và có thể chạy được** với `pom.xml` đã khai báo:

- `@Test` đánh dấu phương thức kiểm thử.
- `assertEquals(expected, actual)` so sánh **kết quả mong đợi** với giá trị thật.
- `assertThrows(IllegalArgumentException.class, action)` kiểm tra hành động phải ném đúng loại ngoại lệ; nếu không ném, kiểm thử thất bại.
- Kiểm thử trường hợp bình thường (`"  Lan  "`) và trường hợp biên (`null`, chuỗi trắng), vì kiểm tra một đầu vào đúng thôi chưa đủ.
- Không cần viết `public static void main` trong test. JUnit/Surefire tìm và thực thi phương thức có `@Test`.

Tên `WelcomeServiceTest` tuân theo mẫu Surefire nhận diện mặc định (`*Test`). Tên tùy ý như `WelcomeServiceCheck` có thể không được chọn nếu bạn chưa đổi cấu hình tìm test. Tên tệp `.java` và các khai báo `package` trong ví dụ phải khớp với sơ đồ thư mục.

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn clean test
```

Maven sẽ dọn `target`, biên dịch mã chính, biên dịch mã test, rồi chạy **3 bài kiểm thử**. Khi các phép khẳng định đúng, log cho biết cả ba đã đạt và kết thúc bằng `BUILD SUCCESS` (các dòng khác phụ thuộc môi trường). Báo cáo thường ở `target/surefire-reports/`, ví dụ `dev.study.maven.WelcomeServiceTest.txt` và tệp XML tương ứng.

Để chỉ chạy lớp này khi dự án có nhiều test:

```bash
mvn -Dtest=WelcomeServiceTest test
```

Chỉ định `-Dtest` là bộ lọc riêng của Surefire. Nó không biến code ở `src/test/java` thành mã ứng dụng và không làm thay đổi JAR chính.

## 6. Maven nối mã nguồn và test với nhau bằng cách nào?

Khi chạy `mvn test`, Maven đi qua những phase chính của **default lifecycle** theo thứ tự:

```text
process-resources
      |
    compile                (src/main/java -> target/classes)
      |
process-test-resources
      |
  test-compile             (src/test/java -> target/test-classes)
      |
     test                  (Surefire chạy bài kiểm thử)
```

Các bước xử lý resources là nơi Maven sao chép tài nguyên nếu chúng tồn tại. Trong lúc biên dịch test, test có thể tham chiếu lớp chính đã nằm trong `target/classes`. Trong lúc chạy test, classpath bao gồm lớp chính, lớp test và thư viện có phạm vi thích hợp (bao gồm dependency `test` như JUnit).

Sự phụ thuộc theo hướng này có ý nghĩa:

- **Mã chính không nên phụ thuộc ngược vào mã test.** Nếu trong `src/main/java` bạn import `org.junit.jupiter.api.Test`, cấu hình `scope=test` khiến mã chính không có JUnit ở compile classpath và có thể báo lỗi.
- **Test được biên dịch riêng.** `mvn compile` có thể thành công dù test chứa lỗi cú pháp; `mvn test` mới phát hiện lỗi ở giai đoạn `test-compile`.
- **Test thất bại làm build thất bại.** Khi Surefire báo lỗi, các phase sau như `package` trong cùng lần chạy bình thường sẽ không tiếp tục.
- **Bài test không nằm trong JAR chính.** `src/test/java` và JUnit có nhiệm vụ bảo vệ chất lượng sản phẩm, không phải mã chức năng để phân phối.

Cần phân biệt **biên dịch test** với **chạy test**: trước khi chạy, Java test cũng phải chuyển thành bytecode. Lỗi import, kiểu dữ liệu hoặc cú pháp ở test có thể khiến build dừng ngay tại `test-compile`, chưa tới bước thực thi JUnit.

## 7. Đóng gói và chạy chương trình từ JAR

Chạy:

```bash
mvn clean package
```

Trong một dự án `jar` như ví dụ, lệnh này dọn kết quả cũ, biên dịch mã chính, biên dịch và chạy unit test, rồi tạo:

```text
target/hello-maven-1.0.0-SNAPSHOT.jar
```

Dùng công cụ `jar` thuộc JDK để xem nội dung:

```bash
jar tf target/hello-maven-1.0.0-SNAPSHOT.jar
```

Trong danh sách tệp cần có `dev/study/maven/App.class` và `dev/study/maven/WelcomeService.class`. `WelcomeServiceTest.class` thường **không có** trong JAR chính vì lớp đó thuộc cây `src/test/java`.

Chạy ứng dụng trực tiếp từ JAR:

```bash
java -cp target/hello-maven-1.0.0-SNAPSHOT.jar dev.study.maven.App Hoa
```

Kết quả:

```text
Xin chào, Hoa!
```

Lệnh `java -cp ... dev.study.maven.App` chỉ định rõ lớp chính. **Không mặc định dùng `java -jar`** cho POM trên: JAR thông thường chưa có thuộc tính `Main-Class` trong manifest. Nếu muốn chạy bằng `java -jar`, phải cấu hình manifest cho lớp chính và giải quyết classpath hoặc cách đóng gói thư viện runtime ngoài JDK nếu có.

Nếu dùng `mvn package` mà chưa `clean`, tệp cũ trong `target` có thể còn đó sau một lần build thất bại. Khi muốn đối chiếu sản phẩm với một lần build xác định, dùng `mvn clean package` và chỉ tin kết quả khi lệnh trả về thành công.

## 8. Tài nguyên chính và tài nguyên test khi dự án lớn hơn

Mã Java không phải là thứ duy nhất Maven quản lý. Giả sử bạn thêm hai tệp:

```text
src/main/resources/banner.txt
src/test/resources/input-name.txt
```

Nội dung minh họa:

```text
# src/main/resources/banner.txt
Chào mừng đến với ứng dụng
```

```text
# src/test/resources/input-name.txt
Lan
```

Maven sẽ sao chép tài nguyên ứng dụng vào `target/classes/banner.txt` và tài nguyên test vào `target/test-classes/input-name.txt`. Code có thể nạp chúng từ **classpath** bằng `getResourceAsStream("/banner.txt")` hoặc `getResourceAsStream("/input-name.txt")` ở thời điểm thích hợp. File test resource thường không nằm trong JAR chính; file main resource thường được đưa vào JAR chính.

Ví dụ phương thức kiểm thử sau chỉ là **đoạn thêm vào bên trong lớp `WelcomeServiceTest`**, không phải một chương trình độc lập. Để dùng, thêm các import `java.io.InputStream`, `java.nio.charset.StandardCharsets` và `assertNotNull`:

```java
@Test
void readsTestResourceFromClasspath() throws Exception {
    try (InputStream stream = WelcomeServiceTest.class
            .getResourceAsStream("/input-name.txt")) {
        assertNotNull(stream);
        String name = new String(stream.readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8).strip();
        assertEquals("Xin chào, Lan!", service.messageFor(name));
    }
}
```

Phương thức này chạy khi đã có `src/test/resources/input-name.txt` như mô tả và nằm trong lớp test từ mục 5. Đọc bằng classpath khiến ví dụ ít phụ thuộc vào thư mục làm việc của IDE hay terminal. Nếu tài nguyên không tồn tại, `getResourceAsStream` trả `null`; `assertNotNull` làm test thất bại với lý do rõ ràng.

## 9. Vòng lặp viết mã và kiểm thử có kiểm soát

Một vòng thực hành hữu ích:

1. **Viết yêu cầu qua test.** Chẳng hạn tên có khoảng trắng đầu/cuối vẫn phải tạo lời chào đúng; ghi điều đó bằng `assertEquals`.
2. **Chạy `mvn test`.** Nếu logic chưa có, sẽ có lỗi biên dịch hoặc test thất bại. Đọc thông báo thay vì bỏ qua.
3. **Viết mã đủ để test đạt.** Sửa `WelcomeService`, sau đó chạy lại `mvn test`.
4. **Cải tiến mã nhưng giữ hành vi.** Đặt tên rõ ràng, tách trách nhiệm, chạy test lần nữa.
5. **Chạy `mvn clean package`** khi cần xác nhận cả bước đóng gói và thu được JAR mới.

Có thể thử một lỗi có chủ ý: tạm đổi kỳ vọng của `trimsSpacesBeforeGreeting` thành `"Xin chào, Mai!"`, nhưng vẫn truyền `"  Lan  "`. Khi chạy `mvn test`, JUnit báo giá trị expected/actual không khớp; Maven kết thúc bằng `BUILD FAILURE`. Khôi phục kỳ vọng về `"Xin chào, Lan!"` rồi chạy lại; test phải xanh. Đây là cách xác nhận test thực sự có khả năng bắt lỗi.

Đừng dùng một test duy nhất để khẳng định toàn bộ ứng dụng đúng: kiểm thử đơn vị tập trung vào hợp đồng của từng phần nhỏ. Hành vi phụ thuộc cơ sở dữ liệu, mạng, file system hoặc nhiều thành phần kết hợp cần được kiểm thử thêm ở cấp thích hợp.

## 10. Các lỗi thường gặp và cách tự chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `mvn: command not found` hoặc không nhận diện `mvn` | Maven chưa cài hoặc chưa có trên `PATH` | Kiểm tra cài đặt, mở terminal mới, chạy `mvn -version` |
| `release version 17 not supported` | Maven đang dùng JDK cũ | Kiểm tra `mvn -version`, `JAVA_HOME` và cấu hình JDK của IDE |
| `package dev.study.maven does not exist` hoặc không thấy lớp | Sai `package`, import, đường dẫn hay nguồn biên dịch | Đối chiếu package/tên lớp và vị trí tệp dưới `src/main/java` |
| `package org.junit.jupiter.api does not exist` | JUnit chưa ở test classpath, khai báo dependency sai hoặc đặt test trong `src/main/java` | Kiểm tra `pom.xml`, `scope=test` và `src/test/java` |
| Maven thành công nhưng không chạy test nào | Tên lớp không khớp mẫu Surefire, thiếu `@Test`, plugin/cấu hình JUnit không phù hợp | Đặt `*Test.java`, dùng `org.junit.jupiter.api.Test`, kiểm tra phiên bản Surefire |
| `Tests run: 3, Failures: 1` | Kết quả thật khác kỳ vọng | Mở `target/surefire-reports`, đọc tên test và expected/actual |
| `ClassNotFoundException` khi gọi `java` | Classpath hoặc tên lớp đầy đủ sai, chưa biên dịch | Dùng `mvn compile`, kiểm tra `target/classes` và lệnh `-cp` |
| `no main manifest attribute` khi gọi `java -jar` | JAR chưa khai báo `Main-Class` | Chạy theo `java -cp ... dev.study.maven.App` hoặc cấu hình manifest |
| Không tải được JUnit/plugin | Mạng, proxy, repository hoặc local cache gặp vấn đề | Kiểm tra log, cấu hình Maven `settings.xml` và khả năng truy cập repository |
| Test trong IDE đạt nhưng Maven không đạt | IDE và CLI dùng JDK/cấu hình hoặc working directory khác nhau | So sánh JDK và chạy `mvn clean test` tại thư mục chứa `pom.xml` |

**Đừng chữa lỗi kiểm thử bằng cách tắt kiểm thử.** `-DskipTests` thường bỏ qua bước chạy test nhưng vẫn biên dịch test; `-Dmaven.test.skip=true` có thể bỏ cả biên dịch test. Chúng hữu ích trong tình huống đặc biệt nhưng không được xem kết quả build là đã được kiểm chứng. Khi cần chạy kiểm thử trên CI, hãy để Maven thực thi test và dừng pipeline nếu test lỗi.

## 11. Bài thực hành tự kiểm tra

Hoàn thành các việc sau bằng cách chỉnh trực tiếp dự án trong bài:

1. Thêm kiểm thử cho `messageFor(" Minh ")` và dự đoán chuỗi trả về. Khi chạy, kết quả đúng là `"Xin chào, Minh!"`.
2. Thêm kiểm thử cho chuỗi rỗng `""` bằng `assertThrows`. Chú ý nó phải bị từ chối giống chuỗi chỉ có khoảng trắng.
3. Chạy `mvn compile`, kiểm tra `target/classes` rồi chạy `mvn test`; giải thích vì sao chỉ lệnh sau mới chứng minh các kiểm thử đã đạt.
4. Chạy `mvn clean package`, kiểm tra JAR và chạy `App` từ JAR bằng classpath; so sánh với chạy từ `target/classes`.
5. Chỉ sửa một giá trị expected để test thất bại, đọc báo cáo Surefire rồi sửa lại; xác nhận `mvn clean package` chỉ thành công sau khi test được khôi phục.

Bạn đã nắm đúng cấu trúc Maven khi có thể nhìn vào một tệp và biết nó thuộc **mã chính**, **mã kiểm thử**, **tài nguyên** hay **đầu ra build**; đồng thời biết lệnh nào biên dịch, lệnh nào thực thi test và khi nào có thể tin rằng JAR mới được tạo từ mã đã qua kiểm thử.

## 12. Nguồn tra cứu

- [Maven — Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html)
- [Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Surefire Plugin — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
