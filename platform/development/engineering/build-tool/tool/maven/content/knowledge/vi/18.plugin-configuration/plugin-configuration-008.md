# Truyền giá trị qua user property khi Maven Plugin hỗ trợ

## 1. Mục tiêu: thay tham số của một lần build mà không phải sửa POM

Maven cho phép truyền **user property** (thuộc tính do người gọi cung cấp) qua tùy chọn dòng lệnh `-Dten=gia-tri`. Một số Maven Plugin công bố rằng **parameter** (tham số của goal) có thể được cấu hình từ một user property cụ thể. Khi đó người dùng có thể thay đổi giá trị trong **lần chạy Maven hiện tại** mà không cần sửa `pom.xml`.

Ví dụ:

```bash
mvn -B -Dmaven.compiler.release=17 clean compile
mvn -B -Dtest=GreetingTest test
mvn -B -DskipTests=true package
```

Ba lệnh minh họa ba mục đích khác nhau:

- `maven.compiler.release`: Maven Compiler Plugin hỗ trợ thuộc tính này cho parameter `release`, tức mức API/ngôn ngữ/bytecode Java mà compiler nhắm tới.
- `test`: Maven Surefire Plugin hỗ trợ thuộc tính này để chọn test class hoặc phương thức test.
- `skipTests`: Surefire hỗ trợ thuộc tính này để bỏ qua **thực thi** unit test. Không nên bật mặc định ở CI kiểm chứng chất lượng.

**Điểm quyết định của bài học:** truyền `-Dmy.option=value` **không khiến mọi plugin tự hiểu** `my.option`. Giá trị chỉ ảnh hưởng nếu Maven/plugin **thực sự sử dụng nó**, chẳng hạn một goal có parameter gắn user property tương ứng hoặc POM ánh xạ property đó vào một parameter được hỗ trợ.

### Học xong có thể làm gì?

1. Phân biệt **user property**, **POM property**, **plugin parameter** và **Java system property**.
2. Tra tài liệu goal để tìm chính xác dòng **User Property** thay vì đoán tên khóa.
3. Truyền `-D...` từ terminal, Maven Wrapper hoặc CI và kiểm tra tác động thực tế.
4. Viết `<configuration>` có thể điều khiển qua một tên property do dự án chọn.
5. Phân biệt thay đổi **lệnh Maven** với thay đổi **JVM chạy Maven/test/ứng dụng**.
6. Chẩn đoán trường hợp “đã truyền `-D` nhưng plugin không đổi hành vi”.

## 2. Bốn khái niệm phải tách rõ

| Khái niệm | Ví dụ | Nơi xuất hiện | Ý nghĩa |
| --- | --- | --- | --- |
| **Maven user property** | `-Dmaven.compiler.release=17` | CLI Maven hoặc nguồn đối số Maven phù hợp | Thuộc tính người gọi cấp cho Maven session |
| **POM property** | `<demo.mode>dev</demo.mode>` trong `<properties>` | POM/parent/profile | Giá trị cấu hình được mô hình dự án định nghĩa |
| **Plugin parameter** | `release` của goal `compiler:compile` | Descriptor/Mojo của plugin, cấu hình `<configuration>` | Một đầu vào cụ thể của goal |
| **JVM system property** | `java -Ddemo.mode=prod ...` | Trình khởi chạy Java | Thuộc tính của JVM đang chạy chương trình |

Trong ngữ cảnh Maven, cả POM property và user property đều có thể được tham chiếu qua biểu thức kiểu `${ten}`, nhưng **nguồn, phạm vi và cơ chế ưu tiên** cần được hiểu đúng. Với những property trùng tên, user property truyền trên CLI thông thường được dùng để ghi đè giá trị POM property trong Maven session; tuy nhiên, khi tham số plugin còn có `<configuration>` tường minh, default, execution-level config hoặc logic nội bộ riêng, không nên suy diễn một thứ tự ưu tiên tuyệt đối cho mọi plugin và mọi Maven version.

**Java system property không tự là Maven user property.** Nếu chạy `java -Ddemo.mode=prod ...` sau build, nó chỉ đặt property của JVM ứng dụng đó. Nếu đặt `-Ddemo.mode=prod` trong `.mvn/jvm.config`, launcher Java đặt một JVM system property cho tiến trình Maven; đó là một tuyến đầu vào khác với đối số Maven CLI `-Ddemo.mode=prod`. Một số plugin có thể đọc cả hai nhưng không có quy tắc chung “giống nhau hoàn toàn” cho mọi trường hợp.

## 3. Cơ chế một plugin nhận giá trị từ -D

Một Maven goal được triển khai bằng một Mojo có các parameter. Plugin descriptor mô tả tên, kiểu, giá trị mặc định và trong nhiều trường hợp **User Property** mà Maven/plugin cho phép dùng từ CLI.

Ví dụ rút gọn về ý tưởng tác giả plugin có thể viết:

```java
@Parameter(property = "demo.limit", defaultValue = "10")
private int limit;
```

**Đây chỉ là đoạn minh họa Java của một plugin do người khác viết, không phải chương trình Maven Plugin đầy đủ có thể compile độc lập.** Ý nghĩa: plugin author tuyên bố parameter `limit` nhận giá trị từ user property `demo.limit`, với giá trị mặc định là 10 theo cách plugin được thiết kế.

Người gọi có thể dùng:

```bash
mvn -Ddemo.limit=25 some-plugin:some-goal
```

*Chỉ khi* plugin thực tế có parameter/goal tương ứng, thuộc tính `demo.limit` mới có tác dụng như mong đợi. `some-plugin` và `some-goal` ở đây là tên giả định **để giải thích cơ chế**, không phải lệnh thực hành của dự án mẫu.

Ở các plugin thật, parameter có thể được cấu hình bằng:

- **User property** chính thức mà tài liệu goal liệt kê.
- **`<configuration>` trong POM**, gán trực tiếp tên parameter.
- **Một biểu thức trong configuration**, ví dụ `<parameter>${demo.parameter}</parameter>`. Cách này giúp dự án tự quy ước một property riêng, kể cả khi plugin không trực tiếp công bố cùng tên đó là user property.
- **Giá trị mặc định và logic plugin**, nếu không có cấu hình hiệu lực nào cung cấp giá trị khác.

Không phải tất cả parameter đều có user property. Một số chỉ cấu hình được bằng POM hoặc được tính theo project/runtime context. Không nên đoán tên `-D` bằng cách thêm dấu chấm vào tên parameter; **tra metadata của đúng plugin version và đúng goal**.

## 4. Cách tìm đúng User Property của một goal

### 4.1. Từ trang tài liệu goal chính thức

Tài liệu Apache Maven cho từng goal thường có bảng **Optional Parameters** và phần chi tiết. Ví dụ:

| Plugin / Goal | Parameter | User Property được tài liệu công bố | Công dụng |
| --- | --- | --- | --- |
| Compiler Plugin `compiler:compile` | `release` | `maven.compiler.release` | `javac --release` / mục tiêu Java phù hợp |
| Compiler Plugin `compiler:compile` | `showWarnings` | `maven.compiler.showWarnings` | Hiện hoặc ẩn cảnh báo biên dịch trong phạm vi plugin |
| Surefire Plugin `surefire:test` | `test` | `test` | Chọn test class/method |
| Surefire Plugin `surefire:test` | `skipTests` | `skipTests` | Bỏ qua thực thi unit test |
| Surefire Plugin `surefire:test` | `skip` | `maven.test.skip` | Bỏ qua test; kết hợp với các plugin hỗ trợ để bỏ qua cả test compilation |
| Surefire Plugin `surefire:test` | `failIfNoTests` | `failIfNoTests` (kiểm tra ở phiên bản đang dùng) | Kiểm soát khi không tìm thấy test phù hợp |

**Một khóa có thể khác tên parameter.** Ví dụ parameter `release` không dùng `-Drelease` như một quy ước chung; tài liệu Compiler Plugin xác nhận khóa `maven.compiler.release`. Ngược lại, Surefire dùng khóa `test` cho parameter `test`. Đọc đúng dòng **User Property**, không suy ra từ một ví dụ khác.

Với `failIfNoTests`, trang goal của plugin version cụ thể mới là nguồn quyết định; dự án cũng có thể đặt nó tường minh trong POM. Nếu tham số đang dùng **không công bố user property**, hãy ánh xạ giá trị từ một POM property như trình bày ở phần 8 thay vì giả định CLI sẽ tự gắn.

### 4.2. Dùng Maven Help Plugin để tra descriptor

Maven Help Plugin hỗ trợ goal `help:describe`. Có thể dùng tọa độ đầy đủ của Help Plugin để kiểm tra Maven Compiler Plugin phiên bản cụ thể:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.4.0:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0 -Dgoal=compile -Ddetail
```

Với Maven Surefire Plugin 3.2.5:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.4.0:describe -Dplugin=org.apache.maven.plugins:maven-surefire-plugin:3.2.5 -Dgoal=test -Ddetail
```

Trong output, tìm parameter `release`/`test`/`skipTests` và thông tin **User property**. Định dạng hiển thị phụ thuộc bản plugin và Help Plugin, nên không chép toàn bộ một dòng giả làm output ổn định.

Nếu dùng cú pháp ngắn:

```bash
mvn help:describe -Dplugin=compiler -Dgoal=compile -Ddetail
```

thì Maven phải phân giải prefix/phiên bản plugin; trong dự án yêu cầu kiểm chứng nhất quán, **nêu tọa độ đầy đủ có version** rõ ràng hơn. Bản Java và Maven runtime vẫn phải đáp ứng yêu cầu của plugin phiên bản đó.

### 4.3. Đừng dùng help:evaluate thay cho chứng cứ plugin đã sử dụng property

Maven Help Plugin còn hỗ trợ:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.4.0:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
```

Lệnh này giúp quan sát giá trị biểu thức/property trong Maven context. Khi ta truyền `-Dmaven.compiler.release=17`, có thể dùng nó để thấy giá trị đang có. Nhưng **Maven biết một property** không chứng minh **một plugin đã sử dụng nó**; việc đó cần được xác minh qua descriptor, log goal, cấu hình hiệu lực hoặc kết quả hành vi.

Một property không được goal nào đọc vẫn có thể tồn tại trong Maven session và được hiển thị bởi công cụ hỗ trợ. Đây là lý do người học nên phân biệt “đã truyền giá trị” với “đã tác động lên parameter”.

## 5. Cú pháp truyền user property từ dòng lệnh

Mẫu chung:

```text
mvn [options] -Dten=gia-tri <phase-hoac-plugin-goal>
```

Ví dụ:

```bash
mvn -B -Dmaven.compiler.release=17 clean compile
mvn -B -Dtest=GreetingTest test
mvn -B "-Dtest=GreetingTest#formatsName" test
mvn -B -DskipTests=true package
```

Lưu ý:

- `-Dten=gia-tri` là **một tham số CLI Maven**. Không phải một goal, phase hay Maven profile.
- Đặt `-D` trước hoặc sau phase thường đều được parser Maven hỗ trợ, nhưng cách đặt gần đầu lệnh dễ đọc trong script.
- Nếu giá trị có khoảng trắng, ký tự shell đặc biệt hoặc dấu `#` dùng để chọn method, **quote toàn bộ đối số** theo shell thực tế. Ví dụ `"-Dtest=GreetingTest#formatsName"`.
- Các giá trị Boolean thường dùng chuỗi `true`/`false`, số nguyên dùng dạng số như `5`, nhưng **plugin parameter là nơi quyết định kiểu và giá trị hợp lệ**.
- `-DskipTests` không nên dùng làm mặc định trong CI kiểm chứng chất lượng; nếu buộc phải bỏ test ở một stage, stage khác cần chạy thật.
- Không truyền password, access token hoặc private key trên CLI trừ khi quy trình bảo mật tổ chức cho phép rõ ràng: tham số có thể xuất hiện trong log, process listing hoặc lịch sử shell.

Một lệnh chứa `-Dmaven.compiler.release=17` không cài JDK 17. Phải có JDK đủ khả năng biên dịch mục tiêu đó; cần xem `mvn -version` và Toolchains nếu dự án sử dụng.

## 6. Ví dụ hoàn chỉnh Java 17 + JUnit 5: ba user property điều khiển build

Ví dụ này có POM đủ để chạy, code Java dùng cú pháp **record của Java 17** và hai JUnit test. Nó minh họa ba hành vi có thể quan sát:

1. Với mặc định POM, `mvn clean verify` compile Java 17 và chạy **2 unit test**.
2. `-Dtest=GreetingTest#formatsName` chọn **một test method** của Surefire (3.2.5).
3. `-Dmaven.compiler.release=11` làm biên dịch **thất bại có chủ đích** vì code có `record` yêu cầu Java 16+; nhờ đó chứng minh property tác động lên compiler.
4. `-DskipTests=true` bỏ **thực thi** unit test mà Surefire chịu trách nhiệm, không nên coi là một lần kiểm chứng test thành công.

### 6.1. Cây thư mục

```text
plugin-user-property-demo/
├── pom.xml
└── src/
    ├── main/java/demo/userprop/Greeting.java
    └── test/java/demo/userprop/GreetingTest.java
```

Điều kiện:

- JDK **17+** (để biên dịch source `record` nhắm tới Java 17).
- Một bản Maven tương thích với các plugin được pin.
- Kết nối repository đã được phê duyệt hoặc cache có đủ JUnit và Maven plugins.
- Thực hiện các lệnh từ thư mục gốc `plugin-user-property-demo/`.

### 6.2. pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>plugin-user-property-demo</artifactId>
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
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Ở đây `<maven.compiler.release>17</maven.compiler.release>` trong POM thiết lập giá trị **mặc định của dự án**. Compiler Plugin `3.13.0` có parameter `release` hỗ trợ user property `maven.compiler.release`. Chúng ta **không** đặt `<release>17</release>` cứng trong plugin `<configuration>`, để giữ đường ghi đè qua property dễ hiểu.

JUnit Jupiter có `scope=test`, còn Surefire `3.2.5` hỗ trợ JUnit Platform. Việc pin plugin version giúp tài liệu goal và cách thực hiện các lệnh trong bài học thống nhất hơn.

### 6.3. Mã Java 17 sản phẩm

Tệp `src/main/java/demo/userprop/Greeting.java`:

```java
package demo.userprop;

public record Greeting(String name) {

    public Greeting {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
    }

    public String message() {
        return "Hello, " + name.strip() + "!";
    }

    public static void main(String[] args) {
        System.out.println(new Greeting(" Maven ").message());
    }
}
```

`record` là cú pháp Java hỗ trợ chính thức từ Java 16; dùng Java 17 là phù hợp. Compact canonical constructor kiểm tra đầu vào và Java gán giá trị tham số cho thành phần record sau phần thân constructor, nên `message()` có thể đọc `name`.

Mã chỉ dùng Java Standard Library khi chạy, nên sau compile không cần thêm JAR runtime của thư viện bên ngoài vào classpath để gọi `main`.

### 6.4. Mã JUnit Jupiter

Tệp `src/test/java/demo/userprop/GreetingTest.java`:

```java
package demo.userprop;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTest {

    @Test
    void formatsName() {
        assertEquals("Hello, Maven!",
                     new Greeting(" Maven ").message());
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                     () -> new Greeting("   "));
    }
}
```

Lớp `GreetingTest` có đúng hai phương thức `@Test`. Tên lớp kết thúc bằng `Test` đáp ứng quy ước phát hiện test thường gặp của Surefire. Với POM này, Surefire phát hiện và thực thi test qua JUnit Platform khi lệnh Maven chạy đến phase `test`.

### 6.5. Lần chạy chuẩn: không thay property trên CLI

```bash
mvn -version
mvn -B clean verify
java -cp target/classes demo.userprop.Greeting
```

Nếu môi trường phù hợp, Maven build thành công và Surefire chạy **2 test, 0 failures, 0 errors**. Phần log Maven có thể khác tùy runtime/mirror; đọc báo cáo ở:

```text
target/surefire-reports/
```

Stdout **của riêng lệnh `java` thứ ba** là:

```text
Hello, Maven!
```

`mvn -version` hiển thị Maven runtime và Java runtime đang dùng. Nếu Maven chạy dưới JDK không hỗ trợ `--release 17` thì phải sửa môi trường JDK, không thể giải quyết chỉ bằng property.

### 6.6. Truyền -Dtest để Surefire chọn test

Chạy **cả lớp** `GreetingTest`:

```bash
mvn -B "-Dtest=GreetingTest" test
```

Surefire nhận user property `test` cho parameter `test`. Với ví dụ này, **hai phương thức test trong lớp** được lựa chọn. Chú ý có thể không cần dấu nháy kép nếu tên class không có ký tự đặc biệt; dùng nháy kép giúp câu lệnh rõ ràng trong script.

Chạy **một phương thức**:

```bash
mvn -B "-Dtest=GreetingTest#formatsName" test
```

Với Surefire 3.2.5 và JUnit Jupiter như ví dụ, mục tiêu là chỉ chạy test method `formatsName`. Test `rejectsBlankName` không nằm trong bộ test được yêu cầu ở lệnh này. Kiểm tra báo cáo Surefire sau khi chạy để xác nhận số test thực tế; đừng chỉ kết luận từ exit code.

**Quan trọng:** chọn một test class/phương thức chỉ phục vụ chẩn đoán nhanh. Trước khi merge hoặc phát hành phải chạy bộ kiểm thử đầy đủ theo chính sách nhóm.

### 6.7. Truyền -Dmaven.compiler.release để thay mục tiêu biên dịch

POM đặt mặc định 17. Dùng đúng user property do Compiler Plugin công bố:

```bash
mvn -B -Dmaven.compiler.release=17 clean compile
```

Lệnh này đặt mục tiêu Java 17, phù hợp source `record` và dự kiến thành công.

Bây giờ **cố ý thử cấu hình sai**:

```bash
mvn -B -Dmaven.compiler.release=11 clean compile
```

Với JDK hỗ trợ `--release 11`, Maven Compiler Plugin yêu cầu biên dịch theo Java 11 và **dự kiến build thất bại** vì Java 11 không hỗ trợ khai báo `record`. Nội dung exact của error message có thể khác giữa JDK/Compiler Plugin, nhưng thường chỉ ra record/syntax không được hỗ trợ ở release 11.

Đây là phép thử an toàn trong dự án mẫu, không nên áp dụng tùy tiện để làm pipeline sản xuất thất bại. Sau thí nghiệm, **khôi phục build bằng lệnh hoàn chỉnh**:

```bash
mvn -B clean verify
```

Lệnh mới không còn `-Dmaven.compiler.release=11`, vì vậy POM lại cung cấp giá trị mặc định 17. Điều này chứng minh một user property CLI được cấp theo **lần chạy Maven** chứ không sửa file `pom.xml` trên đĩa.

### 6.8. Truyền -DskipTests để quan sát tác động nhưng không coi là QA pass

```bash
mvn -B -DskipTests=true clean package
```

Surefire `3.2.5` có parameter `skipTests` tương ứng user property `skipTests`. Nó bỏ **việc chạy** test; việc biên dịch test có thể vẫn xảy ra như bình thường ở lifecycle. Nếu Maven tạo JAR thành công, đó **không** chứng minh hai test vừa được thực thi.

Phân biệt:

| Thuộc tính | Tác dụng phổ biến trong dự án có Compiler/Surefire plugin tương thích | Lưu ý |
| --- | --- | --- |
| `-DskipTests=true` | Bỏ qua chạy unit test của Surefire; test source thường vẫn được biên dịch | Không dùng làm bằng chứng test pass |
| `-Dmaven.test.skip=true` | Có thể bỏ qua cả compile test và thực thi test vì Compiler/Surefire cùng hỗ trợ thuộc tính này | Không tương đương skipTests |
| `-Dtest=GreetingTest` | Chọn lớp test cần chạy; không phải yêu cầu bỏ test | Kiểm chứng số test và exit code |
| `-Dmaven.compiler.release=17` | Nhắm Java release 17 cho Compiler Plugin khi parameter được bind đúng | Không cài JDK 17 |

Với Failsafe/integration tests và các phiên bản plugin khác, **không được tự suy luận rằng một cờ skip duy nhất luôn điều khiển mọi bộ test**. Phải kiểm tra tài liệu của từng plugin/version và POM thực tế.

Để xác minh đúng trạng thái cuối, chạy lại:

```bash
mvn -B clean verify
```

Sau đó đọc `target/surefire-reports` và xác nhận **hai test đã chạy**, không bị skip. Không thay thế bước này bằng `mvn package -DskipTests`.

## 7. User property có tác động ở mức project/Maven session, không phải tự đổi chương trình Java

Đây là điểm dễ nhầm khi học Maven:

```bash
mvn -B -Ddemo.message=Hello test
java -cp target/classes demo.userprop.Greeting
```

`-Ddemo.message=Hello` tạo user property trong Maven session. Nhưng trong POM và code mẫu không có plugin hoặc biểu thức nào dùng `demo.message`. Chương trình Java tiếp tục in:

```text
Hello, Maven!
```

Nếu đổi thành:

```bash
java -Ddemo.message=Hello -cp target/classes demo.userprop.Greeting
```

ta đang đặt **JVM system property cho ứng dụng Java mới được khởi chạy**. Tuy nhiên, `Greeting.java` không gọi `System.getProperty("demo.message")` nên kết quả in ra **vẫn** là `Hello, Maven!`.

Tóm lại, **một property tồn tại không bắt buộc mọi thành phần sử dụng nó**. Plugin phải khai báo hỗ trợ hoặc POM phải ánh xạ property; Java runtime cũng cần code/configuration riêng để đọc nó.

## 8. Truyền property do dự án đặt tên bằng <configuration>

Không phải mọi plugin parameter có user property sẵn. Dự án vẫn có thể làm một parameter configurable **nếu plugin có tham số tương ứng trong POM**.

Giả sử muốn đặt quy tắc `failIfNoTests` của Surefire từ tên property do dự án quản lý, `demo.tests.required`. Đặt trong `<properties>`:

```xml
<properties>
    <demo.tests.required>true</demo.tests.required>
</properties>
```

Sau đó khai báo plugin Surefire:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <failIfNoTests>${demo.tests.required}</failIfNoTests>
    </configuration>
</plugin>
```

Cả hai là **các đoạn XML cần đặt vào đúng vị trí trong một POM hợp lệ**, không phải tệp `pom.xml` hoàn chỉnh thứ hai. Ý nghĩa:

1. Parameter `failIfNoTests` là parameter của Surefire.
2. POM đặt giá trị của parameter đó bằng biểu thức `${demo.tests.required}`.
3. Dự án khai báo mặc định `true`.
4. Người gọi có thể truyền:

```bash
mvn -B -Ddemo.tests.required=false test
```

Khi biểu thức được Maven/plugin giải quyết phù hợp, user property ghi đè giá trị mặc định của project và thay đổi cấu hình `failIfNoTests` trong lần gọi đó. **Nhưng trong dự án mẫu đã có test, việc đổi flag này không tự khiến test thất bại hay bị bỏ qua**: nó chỉ điều khiển hành vi khi Surefire **không tìm thấy test**.

Điều cần phân biệt:

- `-DfailIfNoTests=false` là tên **do chính parameter/plugin có thể công bố** tùy version.
- `-Ddemo.tests.required=false` là tên **do nhóm định nghĩa và nối vào POM**.
- Nếu bỏ phần `<failIfNoTests>${demo.tests.required}</failIfNoTests>` khỏi configuration, một property tự đặt tên như `demo.tests.required` sẽ **không còn tự động điều khiển Surefire** chỉ vì nó hiện diện.

Trong code review, cách ánh xạ tường minh giúp người đọc biết dự án cung cấp “núm điều chỉnh” nào mà không cần nhớ mọi tên property nội bộ của plugin.

### 8.1. Khi plugin không có parameter tương ứng

Nếu plugin không có parameter `fooBar`, thêm:

```xml
<configuration>
    <fooBar>${demo.foo}</fooBar>
</configuration>
```

không có nghĩa plugin sẽ tự thực hiện hành vi mới. Plugin có thể bỏ qua cấu hình không được hỗ trợ hoặc báo lỗi tùy implementation/validation. **POM interpolation không tự tạo tính năng cho plugin**. Cần xác nhận parameter thật trên trang goal chính thức.

## 9. Tránh ghi đè tường minh mà không biết precedence

Một tình huống dễ gây nhầm:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
```

Sau đó chạy:

```bash
mvn -Dmaven.compiler.release=11 compile
```

Có thể người viết kỳ vọng version 11 “tự thắng” vì CLI `-D`. Tuy nhiên, ở đây POM đã gán `<release>17</release>` **tường minh**. Plugin còn có cơ chế cấu hình/ưu tiên riêng, nên không thể áp quy tắc “mọi user property luôn ghi đè mọi plugin XML config” cho mọi plugin.

Nếu mong muốn được điều khiển từ CLI, hãy thiết kế **một nguồn sự thật rõ ràng**. Ví dụ:

```xml
<properties>
    <demo.java.release>17</demo.java.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>${demo.java.release}</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là một **đoạn con của POM**, không được đặt song song với phần `<build>` đã có trong ví dụ đầy đủ nếu chưa hợp nhất XML. Người gọi dùng `-Ddemo.java.release=17` hoặc `-Ddemo.java.release=11` theo chính sách. Không dùng đồng thời nhiều property tương tự mà không nắm rõ cái nào có hiệu lực. Với ứng dụng viết bằng Java 17 `record`, chọn release 11 vẫn gây lỗi compile đúng như đã giải thích.

**Quy tắc thực tế:** khi `-D...` có vẻ bị bỏ qua, hãy xem **cấu hình plugin hiệu lực ở đúng execution** và tài liệu parameter, không chỉ xem giá trị property trong Maven session.

## 10. Project property, user property và phạm vi nhiều module

Trong Maven Reactor có nhiều module:

```text
root/
├── pom.xml              parent/aggregator
├── api/pom.xml
├── service/pom.xml
└── app/pom.xml
```

Khi chạy từ root:

```bash
mvn -B -Dmaven.compiler.release=17 clean verify
```

user property ở CLI thuộc về **Maven session đang chạy Reactor**. Nó có thể được các goal Compiler Plugin trong nhiều module cùng quan sát, **nếu từng module dùng parameter/property tương ứng** và không có configuration ghi đè theo cơ chế áp dụng.

Nhưng:

- Module `api` có thể dùng một compiler configuration riêng hoặc toolchain khác.
- Module `app` có thể có profile/execution khác, làm parameter hiệu lực khác.
- Plugin không chạy trong một module thì property của plugin đó không có cơ hội tác động ở module ấy.
- `<modules>` là cơ chế tổng hợp; `<parent>` mới giúp module kế thừa POM properties/plugin management. **Chỉ thuộc cùng Reactor không chứng minh mọi module đã kế thừa cấu hình giống nhau**.
- Nếu `-Dtest=GreetingTest` áp dụng cho một Reactor có nhiều module không có test khớp tên, Surefire có thể thất bại ở module không có test được chỉ định. Khi chọn test trong một module, cân nhắc `-pl` và `-am` thích hợp cùng cấu hình Surefire.

Ví dụ chỉ kiểm thử module `app` (khi module này đã có các artifact nội bộ cần thiết hoặc được xây đúng Reactor):

```bash
mvn -B -pl :app -am "-Dtest=GreetingTest" test
```

**Cảnh báo:** `-am` có thể đưa thêm module vào lần chạy, và `-Dtest=GreetingTest` có thể áp lên Surefire của những module đó. Vì vậy, khi test class chỉ tồn tại ở app, lệnh có thể cần cấu hình cụ thể để không fail ở module upstream; đừng mặc định sao chép lệnh này sang CI. Với module demo đơn POM ở phần 6, `mvn -Dtest=GreetingTest test` là lựa chọn đơn giản, rõ ràng.

## 11. Cấu hình Maven session bằng .mvn/maven.config và biến môi trường

Một số repository muốn đặt **Maven CLI arguments dùng chung**. Tệp `.mvn/maven.config` có thể chứa:

```text
-B
-Dmaven.compiler.release=17
```

Với Maven **3.9+**, mỗi tham số Maven trong `maven.config` cần nằm trên một dòng riêng. Những tham số này tham gia quá trình gọi Maven theo cấu hình project; tên property vẫn phải được plugin/POM hỗ trợ mới tạo tác động.

Tuy nhiên, đối với các property **điều chỉnh kết quả test, mức Java hoặc việc skip test**, cần cân nhắc xem chúng có thực sự nên là mặc định chung cho mọi thành viên và CI hay không. Không commit `-DskipTests=true` như mặc định chỉ để build nhanh nếu quy trình yêu cầu test được thực thi.

Phân biệt các kênh đầu vào:

| Nguồn | Ví dụ | Tác động chủ yếu |
| --- | --- | --- |
| Maven CLI | `mvn -Dtest=GreetingTest test` | User property của Maven session |
| `.mvn/maven.config` | `-Dmaven.compiler.release=17` | Maven CLI argument dùng chung project |
| `MAVEN_ARGS` (bản Maven hỗ trợ) | `-B -Ddemo.mode=ci` | Maven arguments qua biến môi trường |
| `MAVEN_OPTS` | `-Xmx1g` | JVM options của tiến trình Maven |
| `.mvn/jvm.config` | `-Xmx512m` | JVM options của tiến trình Maven |
| `java -D...` | `java -Ddemo.mode=ci ...` | System property của **JVM ứng dụng** |

**Không nhầm:** `maven.config` phục vụ Maven CLI, còn `jvm.config` và `MAVEN_OPTS` phục vụ Java launcher của Maven. Một `-D` trong JVM options bắt đầu là **system property**, khác đường đi user property `-D` trên Maven CLI.

Đặc biệt, truyền `-Dfoo=value` cho **Maven** không tự đảm bảo JVM fork của Surefire hay ứng dụng sau build nhận cùng một Java system property. Với Surefire, các system properties đưa vào JVM test phụ thuộc tham số và cơ chế của **đúng phiên bản Surefire**, như `systemPropertyVariables`, việc promote user properties và cấu hình fork. Với ứng dụng sau build, phải dùng launcher/runtime config thích hợp.

## 12. Kiểm tra giá trị thực tế thay vì đoán mức ưu tiên

Một quy trình chẩn đoán nên đi từ **input → configuration → goal execution → output**.

### 12.1. Kiểm tra input

```bash
mvn -version
mvn org.apache.maven.plugins:maven-help-plugin:3.4.0:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
```

Xem Maven/JDK runtime và giá trị property trong Maven context. Nếu dùng user property tường minh:

```bash
mvn -Dmaven.compiler.release=17 org.apache.maven.plugins:maven-help-plugin:3.4.0:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
```

Stdout của lệnh Help Plugin có thể khác theo phiên bản, project và mode quiet, nhưng mục tiêu kiểm chứng là **giá trị biểu thức** `maven.compiler.release`.

### 12.2. Kiểm tra cấu hình hiệu lực

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.4.0:effective-pom
```

Tìm `<build><plugins>`, `<pluginManagement>`, execution của goal và các biểu thức trong `<configuration>`. Với Maven có profile, parent hoặc nhiều module, kiểm tra đúng POM/module mà goal sẽ chạy.

**Cần lưu ý:** effective POM mô tả **mô hình Maven hiệu lực**, không phải lúc nào cũng phản ánh toàn bộ giá trị parameter đã được plugin tự tính ở runtime. Vì vậy, nó là một bằng chứng quan trọng nhưng không thay thế quan sát goal và output.

### 12.3. Kiểm tra parameter chính thức

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.4.0:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0 -Dgoal=compile -Ddetail
```

Tìm dòng về `release` và **User Property: maven.compiler.release**. Nếu không có property tương ứng ở parameter cần thay, không nên tự đoán thêm một tên `-D` khác.

### 12.4. Kiểm tra tác động tại goal

Chạy goal/lifecycle trong phạm vi an toàn:

```bash
mvn -B -Dmaven.compiler.release=17 clean compile
```

Xem version Compiler Plugin ở log, thông số compiler được áp dụng và kết quả compile. Với tình huống cần chứng minh khác biệt, dùng phép thử Java 17 `record` ở phần 6: ép release 11 gây lỗi có chủ đích, sau đó khôi phục 17 và build lại.

Với Surefire:

```bash
mvn -B "-Dtest=GreetingTest#formatsName" test
```

Xem `target/surefire-reports` để xác nhận method cụ thể đã chạy. Không chỉ tin rằng Maven chấp nhận `-Dtest` là đã chọn đúng method.

## 13. Cảnh báo kiểu dữ liệu, giá trị mặc định và tên property

### 13.1. Parameter kiểu boolean

```bash
mvn -DskipTests=true test
mvn -DskipTests=false test
```

Ở plugin hỗ trợ `skipTests`, hai giá trị có ý nghĩa khác nhau. Nhưng nếu POM/execution cấu hình tường minh hoặc có nhiều plugin/test runners, cần kiểm tra điều gì **thực sự chạy**. Không suy ra `skipTests=false` luôn thắng mọi cơ chế skip khác như `maven.test.skip=true` hoặc profile riêng.

### 13.2. Parameter kiểu số, danh sách hoặc đường dẫn

Một plugin có thể định nghĩa parameter kiểu số, đường dẫn hoặc collection. Việc chuyển đổi từ chuỗi `-D...` phụ thuộc loại tham số và cú pháp plugin hỗ trợ. Ví dụ **không có plugin thật kèm theo**:

```text
-Ddemo.timeout=30
-Ddemo.reports=alpha,beta
-Ddemo.output=target/reports
```

Các khóa này **chỉ là minh họa**. Đừng kết luận plugin tự parse danh sách ngăn cách dấu phẩy hay tự tạo thư mục chỉ vì property trông hợp lý; hãy xem documentation của goal cụ thể.

### 13.3. Chú ý name collision

Một tên như `test`, `skipTests` hoặc `maven.compiler.release` có thể được plugin khác đọc hoặc POM tự sử dụng. Khi đặt tên property riêng, nên chọn **namespace rõ nghĩa**, ví dụ `demo.tests.required` hoặc `company.build.channel`, và ghi vào README với default, kiểu dữ liệu, phạm vi và nơi sử dụng.

Tránh dùng một property tên quá chung như `mode`, `version` hoặc `output` cho nhiều mục đích mâu thuẫn. Nếu một CLI `-D` được truyền cho cả Reactor, rủi ro ảnh hưởng nhiều module càng lớn.

## 14. Khi nào không nên dùng CLI property?

User property hữu ích để **tinh chỉnh một lần chạy**, nhưng không phải lựa chọn phù hợp cho mọi thiết lập.

| Nhu cầu | Nguồn cấu hình thường phù hợp hơn | Vì sao |
| --- | --- | --- |
| Phiên bản dependency/library | `dependencies`/`dependencyManagement` | Phải được review và quản lý qua POM/BOM |
| Phiên bản plugin | `plugins`/`pluginManagement` | Tránh build thay đổi vì plugin metadata |
| Logic plugin/goal/phase | `<configuration>` và `<executions>` trong POM | Ghi lại cấu trúc quy trình build, không ẩn ở CLI |
| Build biến thể nhiều tham số | Maven profile đã định nghĩa rõ ràng | Dễ review nhóm lựa chọn |
| Token, password, khóa bí mật | Secret manager/CI credentials/settings bảo vệ đúng mức | CLI/log có thể rò rỉ |
| JDK chạy Maven | `JAVA_HOME`/Toolchains/CI image | `-Dmaven.compiler.release` không tự cài JDK |
| JVM options của Maven | `MAVEN_OPTS`/`.mvn/jvm.config` | Chúng được xử lý trước khi Maven chạy |
| JVM options của ứng dụng | App launcher/container config | Không tự kế thừa Maven user property |
| Một test class/method tạm thời | `-Dtest=...` khi Surefire hỗ trợ | Tiện cho điều tra lỗi, không thay full test suite |
| Giá trị đơn giản cần đổi theo job | `-Dten=value` nếu plugin/POM hỗ trợ | Không cần sửa POM cho mỗi lần build |

Đặc biệt không dùng `-DskipTests=true` hoặc `-Dmaven.test.skip=true` làm “cách sửa” khi test fail. Chúng thay đổi việc thực thi test chứ không xử lý lỗi nghiệp vụ.

## 15. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/khắc phục |
| --- | --- | --- |
| Truyền `-Dfoo=bar` nhưng plugin không đổi | Parameter không hỗ trợ user property `foo`; POM không tham chiếu nó | Tra mục **User Property** trong tài liệu goal, hoặc thêm ánh xạ POM đúng |
| Truyền `-Drelease=17` nhưng compiler vẫn dùng bản khác | Nhầm tên khóa `release` với `maven.compiler.release` | Dùng `-Dmaven.compiler.release=17` cho Compiler Plugin khi phù hợp |
| `-Dmaven.compiler.release=17` nhưng compiler vẫn dùng cấu hình khác | `<configuration><release>...` tường minh, execution/profile hoặc plugin version khác | Xem effective POM/module, docs và log goal thực thi |
| Truyền `-Dtest=...` nhưng Surefire không tìm test | Sai tên class/method, không có test phù hợp, Reactor có module khác | Xem reports, tên file/method, `-pl`/`-am` và Surefire version |
| `-DskipTests=true` mà CI xanh | Test bị skip, không chứng minh chất lượng | Bỏ skip trong stage QA và đọc test count |
| `maven.test.skip` bị hiểu là giống `skipTests` | Có plugin hỗ trợ bỏ test compilation lẫn test execution | Đọc docs Compiler/Surefire, chạy thử trên project mẫu |
| Property trong `maven.config` không có hiệu lực | Launcher không đọc đúng project root hoặc cú pháp theo version sai | Kiểm tra root, Maven version và mỗi option một dòng với Maven 3.9+ |
| Tham số có khoảng trắng/ký tự đặc biệt lỗi | Shell tách chuỗi hoặc diễn giải ký tự | Quote toàn bộ `-Dkey=value` theo shell |
| `-Dfoo=value` trên Maven nhưng Java app không thấy | Đã truyền vào Maven session, không phải JVM app | Cấu hình plugin để chuyển giá trị hoặc truyền cho Java runtime riêng |
| Plugin nhận chuỗi nhưng báo lỗi chuyển kiểu | Giá trị không hợp lệ với parameter boolean/number/enum/path | Xem tài liệu kiểu, default và accepted values |
| Chỉ một module thấy property | Goal/configuration chỉ chạy ở module đó, hoặc config/profile bị override | Đọc effective POM từng module và log Reactor |
| IDE hoạt động khác terminal/CI | IDE tự chọn Maven/JDK/profile/arguments khác | So Maven Wrapper, JDK, effective POM và command |
| Property chứa token lộ trong log | Dùng CLI thay cơ chế bảo mật | Chuyển sang secret manager/settings bảo vệ, không in giá trị |
| Cứ đổi `-D` mà không hiệu quả | Bản plugin và goal khác tài liệu đang tra | Pin version plugin, dùng `help:describe` cho version thực |

## 16. Checklist ứng dụng user property đúng cách

Trước khi thêm một `-D` vào script hoặc pipeline:

- [ ] Đã xác định **plugin GAV + goal + version** mà mình thực sự muốn điều khiển?
- [ ] Parameter cần thay có **User Property** trong tài liệu của đúng goal/version, hay POM đang ánh xạ một project property vào nó?
- [ ] Giá trị CLI có **đúng kiểu và phạm vi** (Boolean, Java release, test pattern, path...)?
- [ ] POM có `<configuration>` tường minh, execution-level config hoặc parent/profile làm khác kỳ vọng không?
- [ ] Có kiểm chứng property đã được truyền **và** goal đã thực sự sử dụng không?
- [ ] Với nhiều module, có nguy cơ user property tác động lên các module khác trong Reactor không?
- [ ] Với test, báo cáo có chứng minh test được chạy đúng phạm vi, không bị skip ngầm?
- [ ] Với Java release, đã kiểm tra **JDK đang chạy Maven**, compiler release và classfile/runtime tương ứng?
- [ ] Giá trị có chứa secret hoặc dữ liệu nhạy cảm không? Nếu có, chọn kênh bảo mật đúng thay vì CLI.
- [ ] Thiết lập có nên thuộc POM/profile vì là chính sách dài hạn, hay chỉ cần CLI vì là biến thể tạm thời?
- [ ] Có kế hoạch khôi phục lệnh chuẩn và chạy `mvn -B clean verify` để xác nhận chất lượng cuối cùng?

**Kết luận:** user property là cách linh hoạt để thay **giá trị đầu vào của plugin** trong một Maven session, nhưng chỉ khi plugin đã hỗ trợ hoặc POM ánh xạ property rõ ràng. Hãy đi theo chuỗi: **tra parameter và User Property → truyền `-D` đúng tên → kiểm tra POM/goal thực tế → xác minh kết quả và test**. Một property không được tiêu thụ không tạo ra hành vi mới; còn một property có hiệu lực có thể thay đổi cả kết quả build, nên phải được kiểm soát trong CI.

### Tài liệu chính thức

- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven Compiler Plugin — compiler:compile parameters](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Maven Surefire Plugin — surefire:test parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven Surefire Plugin — Running a Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html)
- [Maven Help Plugin — help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
- [Maven Help Plugin — help:evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html)
- [Apache Maven — Configuring Apache Maven](https://maven.apache.org/configure.html)
