# Thực thi tuần tự các phase khi gọi một phase phía sau trong Maven

## 1. Nguyên tắc cốt lõi của Maven Build Lifecycle

Khi chạy `mvn package`, Maven **không chỉ chạy riêng phase `package`**. Maven đi qua các phase trước đó trong cùng **default lifecycle**, theo thứ tự xác định sẵn, đến hết `package`. Tương tự, `mvn verify` đi qua các phase từ `validate` đến `verify`; `mvn install` đi tiếp tới `install`; `mvn deploy` đi tới `deploy`.

Ví dụ rút gọn:

```text
validate
   |
   v
compile
   |
   v
test
   |
   v
package
   |
   v
verify
   |
   v
install
   |
   v
deploy
```

Đây là **những mốc chính** của default lifecycle, không phải toàn bộ danh sách phase. Giữa chúng còn nhiều phase trung gian như `generate-sources`, `process-resources`, `test-compile`, `prepare-package` và `integration-test`. Maven đi qua **tất cả các phase đứng trước phase đích trong cùng lifecycle**; tại mỗi phase, nó thực thi các plugin goal được gắn vào phase đó, nếu có.

Quy tắc thực hành:

- Muốn **biên dịch mã chính**, gọi `mvn compile`.
- Muốn **chạy unit test**, gọi `mvn test`; Maven đã thực hiện các phase cần để chuẩn bị và biên dịch mã.
- Muốn **tạo JAR/WAR**, gọi `mvn package`; không cần tự gõ lại `compile` và `test`.
- Muốn **kiểm tra build đến bước verify**, gọi `mvn verify`; nó bao gồm `package` và các phase trước.
- Muốn **cài artifact vào local Maven repository**, gọi `mvn install`; nó đã bao gồm `verify` và các phase trước.
- Muốn **đưa artifact lên remote repository**, gọi `mvn deploy` khi đã cấu hình quyền và đích triển khai; đây là thao tác xuất bản có tác động bên ngoài.

Điều này giúp script CI/CD ngắn gọn và giữ thứ tự chuẩn. Chạy một phase ở phía sau có thể **làm nhiều việc hơn tên phase gợi ý**, nên cần chọn đúng điểm kết thúc mong muốn.

## 2. Lifecycle, phase và plugin goal là ba khái niệm khác nhau

Để hiểu nguyên tắc tuần tự, phải phân biệt:

| Khái niệm | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **Lifecycle** | Quy trình cấp cao gồm danh sách phase có thứ tự | `default`, `clean`, `site` |
| **Phase** | Một mốc trong lifecycle; có thể chứa 0, 1 hoặc nhiều goal | `compile`, `test`, `package`, `verify` |
| **Plugin goal** | Công việc cụ thể do một Maven plugin triển khai | `compiler:compile`, `surefire:test`, `jar:jar` |

**Phase không phải tên một chương trình độc lập.** Chẳng hạn, với dự án có `<packaging>jar</packaging>`, Maven thường có những liên kết mặc định:

```text
process-resources  -> resources:resources
compile            -> compiler:compile
process-test-resources -> resources:testResources
test-compile       -> compiler:testCompile
test               -> surefire:test
package            -> jar:jar
install            -> install:install
deploy             -> deploy:deploy
```

Đây là các goal điển hình, **không phải bảng bắt buộc giống nhau cho mọi packaging**. Dự án `war` có goal tạo WAR ở `package`; dự án `pom` có thể không cần biên dịch Java hoặc tạo JAR. Các plugin được khai báo trong POM còn có thể bổ sung goal cho phase.

**Điểm quan trọng:** “Maven chạy qua mọi phase trước” không có nghĩa “mọi phase đều có công việc thấy được trên log”. Phase không có goal nào được liên kết có thể đi qua mà không chạy task cụ thể; vì vậy đừng đếm số dòng log để suy ra Maven đã “bỏ qua” phase.

## 3. Maven có ba lifecycle tích hợp và mỗi lifecycle có thứ tự riêng

Maven thường có ba lifecycle tích hợp:

1. **`default`**: biên dịch, kiểm thử, đóng gói, kiểm tra, cài và triển khai artifact.
2. **`clean`**: dọn các output đã sinh từ lần build trước.
3. **`site`**: tạo và công bố trang tài liệu cho dự án.

### `default`: các mốc thường gặp

```text
validate -> compile -> test -> package -> verify -> install -> deploy
```

Khi gọi một phase cuối hơn, Maven thực hiện các phase trước thuộc **default lifecycle**.

### `clean`: thứ tự độc lập

```text
pre-clean -> clean -> post-clean
```

`mvn clean` chỉ đi tới phase `clean` của clean lifecycle; nó **không tự chạy** `compile`, `test` hay `package` trong default lifecycle. `mvn post-clean` mới đi qua cả ba phase của clean lifecycle.

### `site`: thứ tự độc lập

```text
pre-site -> site -> post-site -> site-deploy
```

`mvn site` tạo site theo lifecycle riêng, **không mặc định chạy `test` hoặc `package`**. `mvn site-deploy` có thể xuất bản tài liệu ra đích đã cấu hình.

**Không có một chuỗi duy nhất “clean → default → site” chạy tự động ở mọi lệnh.** Maven chỉ thực hiện những lifecycle/phase/goal được yêu cầu trên dòng lệnh (và những liên kết do plugin/build quy định).

## 4. Danh sách thứ tự đầy đủ của default lifecycle trong Maven 3

Bảng dưới đây giúp nhìn thấy các phase trung gian mà một sơ đồ rút gọn thường bỏ qua. Đây là thứ tự chuẩn của **Maven 3 default lifecycle**; nhiều phase chỉ làm việc khi dự án/plugin gắn goal tương ứng.

| Thứ tự | Phase | Chức năng chính |
| ---: | --- | --- |
| 1 | `validate` | Kiểm tra POM và thông tin cần cho build |
| 2 | `initialize` | Khởi tạo trạng thái build, thuộc tính, thư mục cần thiết |
| 3 | `generate-sources` | Sinh mã nguồn nếu có generator |
| 4 | `process-sources` | Xử lý nguồn trước biên dịch nếu được cấu hình |
| 5 | `generate-resources` | Sinh tài nguyên |
| 6 | `process-resources` | Sao chép/xử lý tài nguyên chính |
| 7 | `compile` | Biên dịch nguồn chính |
| 8 | `process-classes` | Xử lý thêm lớp đã biên dịch nếu có |
| 9 | `generate-test-sources` | Sinh mã nguồn test |
| 10 | `process-test-sources` | Xử lý mã nguồn test |
| 11 | `generate-test-resources` | Sinh tài nguyên test |
| 12 | `process-test-resources` | Sao chép/xử lý tài nguyên test |
| 13 | `test-compile` | Biên dịch mã nguồn test |
| 14 | `process-test-classes` | Xử lý thêm lớp test đã biên dịch |
| 15 | `test` | Thực hiện unit test bằng plugin thích hợp |
| 16 | `prepare-package` | Chuẩn bị cho đóng gói nếu có cấu hình |
| 17 | `package` | Đóng gói artifact như JAR/WAR |
| 18 | `pre-integration-test` | Thiết lập môi trường integration test |
| 19 | `integration-test` | Chạy thao tác integration test khi có plugin gắn vào |
| 20 | `post-integration-test` | Thu dọn môi trường integration test |
| 21 | `verify` | Xác minh kết quả và các tiêu chí chất lượng |
| 22 | `install` | Đưa artifact vào local Maven repository |
| 23 | `deploy` | Đưa artifact tới remote repository đã cấu hình |

Các mô tả là mục tiêu của từng phase, **không bảo đảm Maven có công việc tương ứng để chạy** trong mọi dự án. Ví dụ dự án JAR thuần Java không có plugin integration test thì đi qua các phase integration test mà không tự động chạy test tích hợp nào.

Maven 4 có bổ sung cơ chế phase trước/sau và một số thay đổi orchestration; bảng trên dành cho Maven 3 và mô hình lifecycle phổ biến trong dự án Maven hiện tại. Luôn xem phiên bản Maven dự án đang sử dụng khi phân tích log rất chi tiết.

## 5. Lấy một phase làm điểm kết thúc: điều gì được thực thi?

Với project JAR thông thường, xét các lệnh riêng biệt:

| Lệnh | Các phase mặc định được đi qua | Kết quả thường mong đợi |
| --- | --- | --- |
| `mvn validate` | Từ `validate` đến `validate` | Kiểm tra mô hình dự án; chưa biên dịch |
| `mvn compile` | `validate` → ... → `compile` | Biên dịch mã chính vào `target/classes` |
| `mvn test` | `validate` → ... → `test` | Biên dịch mã chính + test rồi chạy unit test |
| `mvn package` | `validate` → ... → `package` | Chạy các bước trước và tạo JAR/WAR |
| `mvn verify` | `validate` → ... → `verify` | Có artifact và các kiểm tra gắn đến `verify` |
| `mvn install` | `validate` → ... → `install` | Cài artifact vào kho cục bộ |
| `mvn deploy` | `validate` → ... → `deploy` | Triển khai artifact lên kho từ xa nếu cấu hình hợp lệ |

Ký hiệu `...` bao gồm **mọi phase trung gian** theo bảng mục 4. Những lệnh trong bảng được hiểu là **các lần chạy riêng biệt**, không phải một lệnh duy nhất có bảy đối số.

Ví dụ:

```bash
mvn -B -ntp package
```

Maven không nhảy thẳng đến JAR Plugin; nó trải qua giai đoạn xử lý tài nguyên, biên dịch nguồn, biên dịch test, test và những phase đã được định nghĩa trước `package`. Tại phase có goal được gắn, plugin thực hiện goal đó. Nếu một goal lỗi, Maven thường dừng build trước khi đến phase sau.

```bash
mvn -B -ntp verify
```

Lệnh này đi tiếp qua các phase sau `package`, gồm `pre-integration-test`, `integration-test`, `post-integration-test` và `verify`. Nó **không có nghĩa chắc chắn sẽ có integration test**: phải có plugin và cấu hình thích hợp. Nếu cần kiểm tra tổng thể trong CI, `verify` thường là một điểm kết thúc phù hợp.

## 6. Hai câu hỏi dễ nhầm về thứ tự phase

### “Nếu chạy `mvn package`, có cần gọi `mvn compile` trước không?”

**Không.** `compile` đứng trước `package` trong default lifecycle. Maven đi qua `compile` ở cùng lượt gọi `package`.

Ví dụ, **chỉ cần**:

```bash
mvn -B -ntp package
```

Không bắt buộc chạy:

```bash
mvn compile
mvn test
mvn package
```

Ba lệnh trên là **ba lượt build**. Lượt cuối vẫn đi qua các phase từ đầu đến `package`. Maven/plugin có thể dùng cơ chế incremental hoặc tái sử dụng output nên công việc thực tế không nhất thiết diễn ra y hệt, nhưng đó không phải cách rút gọn lifecycle.

### “Nếu chạy `mvn verify`, có phải nó bỏ qua `package` không?”

**Không.** `package` đứng trước `verify`. Maven cần đi qua `package` và các phase trung gian trước khi đến `verify`. Với `jar`, nó thường sinh artifact ở `package` rồi mới chạy các kiểm tra hậu đóng gói được liên kết.

**Lưu ý:** Nếu chạy nhiều phase trong **cùng dòng lệnh**, Maven xử lý các task được chỉ định theo thứ tự, và mỗi yêu cầu phase có thể dẫn tới thực hiện lại các phase trước. Vì thế không gõ `mvn compile test package` để “ép tuần tự hơn”. Khi chỉ muốn đi tới một phase thuộc cùng lifecycle, chọn **phase cuối cần đạt**: `mvn package`, `mvn verify` hoặc `mvn install`.

## 7. Ví dụ đầy đủ: từ Java 17 đến JAR bằng một phase đích

Tạo một dự án mẫu. Ví dụ có mã Java 17 và một unit test JUnit 5 để người học quan sát rõ `compile`, `test` và `package` trong một lần gọi.

Cấu trúc file:

```text
lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/lifecycle/App.java
    └── test/
        └── java/
            └── com/example/lifecycle/AppTest.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
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
                <version>3.5.4</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`junit-jupiter` cung cấp JUnit 5 để viết/chạy test; `scope=test` không đưa nó vào dependency runtime của ứng dụng. `maven-compiler-plugin` biên dịch Java theo `release=17`; `maven-surefire-plugin` chạy unit test ở phase `test`. Các phiên bản được ghi cố định để ví dụ dễ tái tạo; thực tế còn cần mạng tải dependency/plugin ở lần build đầu.

### `src/main/java/com/example/lifecycle/App.java`

```java
package com.example.lifecycle;

public final class App {
    private App() {
    }

    public static String message(String name) {
        return "Hello, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println(message("Maven lifecycle"));
    }
}
```

### `src/test/java/com/example/lifecycle/AppTest.java`

```java
package com.example.lifecycle;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void createsExpectedMessage() {
        assertEquals("Hello, Maven lifecycle!", App.message("Maven lifecycle"));
    }
}
```

Hai tệp Java có tên, package và thư mục khớp nhau. Test minh họa không cần công cụ test ngoài Maven và JUnit 5 đã khai báo trong POM.

### Cách 1: gọi `mvn package`

Đặt terminal ở thư mục chứa `pom.xml` và dùng JDK 17+:

```bash
mvn -version
mvn -B -ntp clean package
```

Đây là yêu cầu **hai lifecycle**: `clean` dọn output cũ trước, rồi default lifecycle chạy từ `validate` đến `package`. Trong một lượt build thành công với `jar`, người học sẽ thấy các goal biên dịch mã chính, biên dịch test, chạy test và tạo JAR. Kết quả dự kiến sau build:

```text
target/classes/com/example/lifecycle/App.class
target/test-classes/com/example/lifecycle/AppTest.class
target/lifecycle-demo-1.0.0.jar
target/surefire-reports/
```

Các đường dẫn trên là các output thông dụng của những plugin trong ví dụ; log cụ thể, thời gian chạy và file report chi tiết tùy phiên bản/môi trường.

Chạy mã đã biên dịch:

```bash
java -cp target/classes com.example.lifecycle.App
```

**Stdout chính xác của lệnh `java`:**

```text
Hello, Maven lifecycle!
```

Không nhầm stdout chương trình với hàng loạt dòng `[INFO]` của Maven trong lệnh build trước. POM không cấu hình `Main-Class` trong manifest, vì vậy `java -jar target/lifecycle-demo-1.0.0.jar` không phải lệnh chạy thích hợp cho JAR mẫu này.

### Cách 2: chỉ định phase cuối hơn

```bash
mvn -B -ntp clean verify
```

Maven vẫn đi qua `compile`, `test`, `package` trước khi tới `verify`. Với POM mẫu chưa cấu hình plugin integration test và kiểm tra bổ sung ở `verify`, đừng kỳ vọng sẽ xuất hiện một loạt integration test mới. Dù vậy, quy tắc tuần tự của phase vẫn giữ nguyên.

### Cách 3: cài artifact vào local repository (khi thực sự cần)

```bash
mvn -B -ntp install
```

Default lifecycle đi đến `install`, bao gồm `verify`. Artifact có thể được cài vào local repository của Maven (thường là `~/.m2/repository/com/example/lifecycle-demo/1.0.0/`) để dự án Maven khác trên cùng máy tham chiếu. Ví dụ này không cần `deploy` và không thiết lập đích repository từ xa.

## 8. Vì sao log chỉ hiện vài goal dù có nhiều phase?

Khi chạy `mvn package` trong project `jar`, có thể thấy các dòng tương tự:

```text
[INFO] --- maven-resources-plugin:...:resources (...) @ lifecycle-demo ---
[INFO] --- maven-compiler-plugin:...:compile (...) @ lifecycle-demo ---
[INFO] --- maven-resources-plugin:...:testResources (...) @ lifecycle-demo ---
[INFO] --- maven-compiler-plugin:...:testCompile (...) @ lifecycle-demo ---
[INFO] --- maven-surefire-plugin:...:test (...) @ lifecycle-demo ---
[INFO] --- maven-jar-plugin:...:jar (...) @ lifecycle-demo ---
[INFO] BUILD SUCCESS
```

**Đoạn này là sơ đồ log minh họa**, ký hiệu `...` cố ý thay phần phiên bản/execution không cố định và không phải output chính xác của một lượt chạy đã được ghi nhận. Plugin nào thật sự xuất hiện còn tùy Maven/POM/packaging.

Giải thích:
- Goal `resources:resources` gắn với `process-resources`.
- Goal `compiler:compile` gắn với `compile`.
- Goal `resources:testResources` gắn với `process-test-resources`.
- Goal `compiler:testCompile` gắn với `test-compile`.
- Goal `surefire:test` gắn với `test`.
- Goal `jar:jar` gắn với `package`.

Không thấy dòng riêng cho `initialize`, `generate-resources`, `process-classes` hay `prepare-package` **không có nghĩa thứ tự phase bị phá vỡ**. Chúng có thể không có goal tương ứng nên không tạo dòng thực thi hiển thị.

Nếu `surefire:test` thất bại vì test sai, Maven thường dừng trước `jar:jar`. Bởi vậy không được kết luận “cứ gọi `mvn package` là luôn có JAR”; đó là **mục tiêu** nếu các bước trước hoàn tất thành công.

## 9. Packaging quyết định goal mặc định trong các phase

Hai dự án cùng gọi `mvn package` nhưng có thể thực hiện công việc khác nhau vì `<packaging>` và cấu hình plugin:

| Packaging | Đầu ra điển hình ở `package` | Điều cần nhớ |
| --- | --- | --- |
| `jar` | Tạo JAR bằng JAR Plugin | Biên dịch Java/test với những binding thông thường |
| `war` | Tạo WAR bằng WAR Plugin | Có cách đóng gói ứng dụng web riêng |
| `pom` | Thường không có artifact JAR/WAR để đóng gói ở `package` | Thường dùng cho parent/aggregator; `install/deploy` vẫn có ý nghĩa |
| Loại đóng gói khác | Phụ thuộc extension/plugin tương ứng | Không suy từ thứ tự phase để khẳng định tên artifact |

**Thứ tự phase của lifecycle** là khung điều phối; **plugin goal được gắn vào phase** quyết định công việc cụ thể. Khung này giúp Maven mở rộng mà không yêu cầu mỗi dự án phải tự lập một danh sách bước build từ đầu.

Ví dụ thêm một goal vào một phase thông qua POM:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.1.0</version>
            <executions>
                <execution>
                    <id>announce-validate</id>
                    <phase>validate</phase>
                    <goals>
                        <goal>run</goal>
                    </goals>
                    <configuration>
                        <target>
                            <echo message="POM validation phase reached"/>
                        </target>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là **một đoạn cấu hình minh họa để chèn vào `<project>` trong POM**, không phải file POM độc lập và không nên chèn thêm `<build>` thứ hai vào POM đã có `<build>`. Trong Maven 3, khi được cấu hình hợp lệ, goal `antrun:run` sẽ gắn vào `validate`; vì thế gọi `mvn package` cũng đi qua `validate` và chạy goal này trước các goal gắn ở phase sau. Ví dụ có tác dụng giảng giải, không bắt buộc dùng Antrun trong dự án thực tế.

**Nhiều goal trong cùng một phase** chạy theo thứ tự Maven xác định từ binding của packaging và cấu hình POM: các goal mặc định do packaging gắn thường chạy trước các goal khai báo bổ sung trong POM cho phase đó. Giữa **các phase khác nhau**, Maven giữ thứ tự lifecycle.

## 10. Khi nào `clean` chạy, và tại sao `clean package` thường hữu ích?

`clean` thuộc **clean lifecycle**; `package` thuộc **default lifecycle**. Lệnh:

```bash
mvn clean package
```

được hiểu là:

```text
clean lifecycle:   pre-clean -> clean
default lifecycle: validate -> ... -> package
```

Sau đó Maven có thể sinh lại `target/classes` và artifact. `clean` thường xóa output build cũ, có ích khi kiểm tra thay đổi có thể bị che khuất bởi dữ liệu build từ lần trước.

Ngược lại:

```bash
mvn package
```

không tự dọn `target/`. Điều này thường giúp build nhanh hơn nếu công cụ có thể tận dụng đầu ra hiện có, nhưng cũng có thể khiến việc kiểm tra môi trường sạch chưa đầy đủ.

Lệnh `mvn clean verify` thường phù hợp khi cần chạy một lượt build mới và các kiểm tra đến `verify`. Không nên chèn `clean` vào mọi bước nhỏ không cần thiết vì nó khiến phải tạo lại output.

**Về cú pháp:** `mvn clean package` đặt các phase trên cùng dòng lệnh, lần lượt chạy clean rồi đến package. Nó không có nghĩa `clean` là phase đứng trước `compile` trong **default lifecycle**.

## 11. Gọi trực tiếp plugin goal có khác gọi phase không?

Có. Hãy so sánh:

```bash
mvn compile
```

Lệnh trên yêu cầu **phase** `compile`, nên Maven thực hiện các phase trước trong default lifecycle và mọi goal được gắn phù hợp.

```bash
mvn compiler:compile
```

Lệnh này yêu cầu **goal** `compile` của Maven Compiler Plugin. Gọi goal trực tiếp **không tương đương việc yêu cầu chạy toàn bộ default lifecycle đến `compile`**. Các bước như xử lý tài nguyên hoặc sinh mã trước biên dịch có thể không được thực hiện theo chuỗi mà ứng dụng cần, nếu goal được gọi trực tiếp không tự kích hoạt chúng qua cơ chế riêng.

Ví dụ khác:

```bash
mvn clean dependency:tree package
```

`clean` và `package` là phase của những lifecycle tương ứng; `dependency:tree` là goal được yêu cầu trực tiếp ở giữa. Maven xử lý các task theo thứ tự gọi: dọn output, chạy goal hiển thị cây dependency, rồi chạy default lifecycle đến `package`.

**Nguyên tắc chọn lệnh:** Khi mục tiêu là kết quả build chuẩn như compile/test/package/verify, nên gọi **phase**. Chỉ gọi goal trực tiếp khi cần chính tác vụ do plugin đó cung cấp và hiểu rõ điều kiện đầu vào của nó.

## 12. Những điều thứ tự phase KHÔNG bảo đảm

1. **Không bảo đảm build thành công.** Một test có thể fail, dependency tải thất bại, hoặc plugin báo lỗi; Maven dừng theo chính sách lỗi tương ứng trước phase cuối.
2. **Không bảo đảm mỗi phase đều in log.** Nhiều phase không có goal gắn sẵn.
3. **Không bảo đảm có integration test khi gọi `verify`.** Cần plugin (ví dụ Failsafe) và cấu hình/execution tương ứng. Với Maven 3, không nên chỉ gọi thẳng `integration-test` nếu project có bước dọn môi trường ở `post-integration-test`; gọi `verify` giúp các phase sau integration test được thực hiện.
4. **Không tự động chạy `clean` trước build.** `clean` là lifecycle riêng.
5. **Không tự động triển khai ra remote repository trừ khi gọi phase liên quan và có cấu hình.** `install` ghi vào local repo; `deploy` mới là bước phát hành tới remote repo.
6. **Không làm mọi plugin chạy song song.** Thứ tự phase có tính tuần tự trong lifecycle của một project. Trong build đa module hoặc với tùy chọn chạy song song, các project/luồng có thể xen kẽ trên log; không suy từ thứ tự dòng log tổng thể rằng Maven đã đảo thứ tự phase trong từng project.
7. **Không loại trừ tối ưu/incremental.** Nếu mã không thay đổi, plugin có thể báo không cần biên dịch lại; Maven vẫn đi qua chuỗi phase.
8. **Không mặc định bỏ test.** Gọi `package`/`verify` vẫn tới phase `test`. Có thể bật cơ chế skip test, nhưng đó là thay đổi hành vi plugin, không phải bỏ qua logic thứ tự phase.
9. **Không giống giữa mọi phiên bản Maven.** Các ví dụ thứ tự đầy đủ ở đây mô tả Maven 3; Maven 4 có một số thay đổi về before/after phase và cơ chế build. Khi cần chẩn đoán chính xác, phải dùng tài liệu tương ứng bản Maven của dự án.

## 13. Skip test là bỏ qua goal hay xóa phase khỏi lifecycle?

Trong dự án dùng Surefire, một lựa chọn thường gặp:

```bash
mvn -DskipTests package
```

`-DskipTests` thường yêu cầu Surefire **không chạy test**, nhưng Maven vẫn đi qua phase `test` và có thể tiếp tục biên dịch mã test tùy cấu hình/plugin. Tùy chọn `-Dmaven.test.skip=true` còn ảnh hưởng tới bước biên dịch test của các plugin hỗ trợ thuộc tính này.

Vì vậy:

- **Phase `test` vẫn nằm trong thứ tự lifecycle**.
- **Goal/plugin có thể quyết định bỏ việc chạy test** theo tùy chọn của nó.
- Dự án vẫn có thể có các goal khác gắn cùng phase hoặc trước đó.
- Bỏ test chỉ nên dùng khi có chủ đích và hiểu tác động tới kiểm chứng chất lượng.

Nếu bài build thất bại do unit test, không nên mặc định thêm `-DskipTests` chỉ để làm cho lệnh `package` thành công. Cần xử lý lỗi test hoặc phân biệt rõ một lượt build chưa được kiểm thử đầy đủ.

## 14. Bài thực hành quan sát thứ tự theo từng lệnh

Dùng dự án `lifecycle-demo` ở mục 7:

1. **Chỉ validate**:
   
   ```bash
   mvn -B -ntp validate
   ```

   Maven đọc POM và chạy đến `validate`; không nên kỳ vọng có `target/lifecycle-demo-1.0.0.jar` mới chỉ nhờ lệnh này.

2. **Chỉ compile đến điểm đích**:
   
   ```bash
   mvn -B -ntp clean compile
   ```

   Clean chạy trước; các phase từ `validate` đến `compile` tiếp theo. Kiểm tra `target/classes/com/example/lifecycle/App.class`.

3. **Chạy unit test**:

   ```bash
   mvn -B -ntp clean test
   ```

   Maven đi đến `test` và Surefire chạy `AppTest`. Kiểm tra `target/surefire-reports/`; không kỳ vọng có JAR mới vì `package` chưa được gọi.

4. **Đóng gói**:

   ```bash
   mvn -B -ntp clean package
   ```

   Lượt này đi qua `test` rồi mới `package`. Kiểm tra `target/lifecycle-demo-1.0.0.jar`.

5. **Kiểm tra tới verify**:

   ```bash
   mvn -B -ntp clean verify
   ```

   Lượt này bao gồm `package` và các phase tiếp theo đến `verify`. Với POM hiện tại, không có cấu hình integration test riêng; kiểm tra thực tế bằng log và file được sinh.

6. **Đối chiếu log**: tìm các dòng tương ứng với `compiler:compile`, `compiler:testCompile`, `surefire:test`, `jar:jar` (khi áp dụng). Xem số lượng/tên goal phụ thuộc mục tiêu và POM.

Các lệnh ở bước 1–5 là những **lượt chạy độc lập để học tập**. Trong công việc hằng ngày, chỉ chạy lệnh với phase cuối cần thiết, ví dụ `mvn -B -ntp clean verify`, thay vì chạy đủ cả năm lượt nối tiếp.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân hoặc nhầm lẫn | Hướng xử lý |
| --- | --- | --- |
| `mvn package` chạy test dù chỉ muốn JAR | `test` đứng trước `package` | Đây là hành vi đúng của lifecycle; chọn mục tiêu/chiến lược test phù hợp |
| `mvn verify` không thấy integration test | Chưa gắn goal Failsafe/integration test vào phase liên quan | Kiểm tra cấu hình plugin và report; đừng suy chỉ từ tên phase |
| Không thấy phase `initialize` trong log | Phase không có goal được gắn nên không có dòng riêng | Kiểm tra binding/plugin, phân biệt “đi qua phase” và “chạy goal” |
| `mvn compile` không tạo JAR | `package` đứng sau `compile` | Gọi `mvn package` khi cần artifact |
| `mvn package` không xóa `target/` cũ | `clean` thuộc lifecycle khác | Chạy `mvn clean package` khi cần build sạch |
| `mvn install` cài vào máy nhưng không xuất bản lên server | `install` là local repository, `deploy` mới là remote | Dùng `deploy` chỉ khi có quyền/cấu hình đích hợp lệ |
| `mvn compiler:compile` không chạy chuẩn toàn chuỗi | Đang gọi trực tiếp plugin goal | Sử dụng `mvn compile` nếu muốn lifecycle đến compile |
| Build dừng trước `package` | Goal ở `compile`/`test` hoặc trước đó lỗi | Xem lỗi đầu tiên và sửa, không bỏ qua test tùy tiện |
| Log đa module xuất hiện xen kẽ khi build song song | Nhiều module/luồng log đồng thời | Đối chiếu theo module, packaging và command; không kết luận thứ tự nội bộ sai |
| `mvn integration-test` để lại container/test environment | Phase dọn ở `post-integration-test` chưa được chạy | Trong Maven 3, thường gọi `mvn verify` cho chuỗi test tích hợp có setup/teardown |
| `mvn deploy` báo thiếu repository hoặc quyền ghi | Cần `distributionManagement`/settings phù hợp | Kiểm tra cấu hình deploy; không tự chạy lại vào remote sai đích |

## 16. Checklist đọc nhanh một lệnh Maven

Khi thấy một lệnh Maven trong tài liệu hoặc CI, hãy tự hỏi:

- **Tham số là phase hay goal?** `package` là phase; `jar:jar` là goal.
- **Phase đích thuộc lifecycle nào?** `clean` khác `default`; `site` là lifecycle riêng.
- **Maven sẽ đi qua những phase nào trước đích?** Xem thứ tự ở mục 4.
- **Goal nào gắn vào các phase?** Phụ thuộc packaging, POM và plugin.
- **Có kết thúc ở phase phù hợp chưa?** Muốn JAR dùng `package`; muốn kiểm tra sau đóng gói có thể dùng `verify`.
- **Có đang gọi nhiều phase thừa không?** Trong cùng lifecycle, thông thường chỉ cần phase cuối.
- **Đã xét failure, test và môi trường chưa?** Một phase trước thất bại thì phase sau không thể hoàn tất.
- **Có tác động cục bộ hay bên ngoài không?** `install` ảnh hưởng local repository, `deploy` ảnh hưởng remote repository.
- **Nếu log khác dự đoán, phiên bản Maven và POM có gì đặc biệt?** Plugin binding, packaging, profile, reactor mode và phiên bản đều có thể giải thích.

**Kết luận kiến thức:** Khi gọi một phase ở phía sau, Maven thực hiện các phase đứng trước nó **trong cùng lifecycle theo thứ tự định sẵn**. Phase quyết định *mốc thứ tự*; plugin goal quyết định *việc thực sự chạy*. Chọn phase cuối cần đạt sẽ đủ để Maven tự thực hiện các bước chuẩn bị, kiểm thử và đóng gói tương ứng theo cấu hình dự án.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Running Apache Maven](https://maven.apache.org/run.html)
- [Apache Maven 3 — Lifecycles Reference](https://maven.apache.org/ref/3-LATEST/maven-core/lifecycles.html)
- [Apache Maven — Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven — What's New in Maven 4?](https://maven.apache.org/whatsnewinmaven4.html)
