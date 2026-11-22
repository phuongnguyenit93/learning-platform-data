# Chạy compile, test, package và quan sát đầu ra của dự án Maven đầu tiên

## 1. Mục tiêu thực hành

Trong một dự án Java dùng Apache Maven, ba lệnh `mvn compile`, `mvn test` và `mvn package` không phải ba bước độc lập bất kỳ. Chúng yêu cầu Maven thực thi đến ba **phase** khác nhau của cùng **default lifecycle**. Khi chạy phase sau, Maven cũng thực thi những phase cần thiết đứng trước phase đó trong lifecycle.

Sau bài này, bạn có thể:

1. Tự tạo dự án Java thuần dùng Maven và JDK 17, có mã ứng dụng và JUnit test.
2. Chạy `compile`, `test`, `package` từ terminal và đọc được `BUILD SUCCESS` hoặc `BUILD FAILURE`.
3. Quan sát chính xác vị trí file `.class`, test report và `.jar` trong thư mục `target/`.
4. Giải thích vì sao `mvn package` bình thường chạy cả test, vì sao một test hỏng có thể chặn JAR và vì sao `mvn compile` chưa tạo JAR.
5. Chạy chương trình đã biên dịch hoặc đã đóng gói, phân biệt JAR thông thường với executable/fat JAR.

Ví dụ dùng **Maven 3.9.x**, **JDK 17 trở lên** và **JUnit 5**. Mục tiêu là quan sát quá trình build của một dự án nhỏ; không cần Spring Boot, máy chủ ứng dụng hoặc cơ sở dữ liệu. Các bước kiểm tra file được thực hiện sau mỗi lệnh nên bạn có thể tự đối chiếu kết quả trên máy.

## 2. Hiểu luồng build trước khi gõ lệnh

Với dự án có `<packaging>jar</packaging>`, các mốc chính của default lifecycle có thể hình dung như sau:

~~~text
validate
   |
   v
compile            --> biên dịch src/main/java --> target/classes
   |
   v
test-compile       --> biên dịch src/test/java --> target/test-classes
   |
   v
test               --> chạy unit test --> target/surefire-reports
   |
   v
package            --> tạo JAR --> target/<artifactId>-<version>.jar
~~~

Đây là sơ đồ **rút gọn**: Maven còn nhiều phase trung gian, ví dụ xử lý resources. Khi chạy `mvn package`, Maven đi qua các phase trước đó (bao gồm `compile` và `test`) trong default lifecycle; Maven không chỉ “đóng gói những thứ đã tình cờ có sẵn”.

Phân biệt ba khái niệm:

- **Lifecycle:** chuỗi công đoạn Maven quy định, chẳng hạn `default` và `clean`.
- **Phase:** một mốc như `compile`, `test`, `package`. Lệnh `mvn test` yêu cầu chạy lifecycle đến phase `test`.
- **Plugin goal:** công việc cụ thể được gắn với phase, chẳng hạn goal `compiler:compile` biên dịch mã chính, `surefire:test` chạy unit test, `jar:jar` tạo JAR. Với `packaging=jar`, Maven đã có các binding tiêu chuẩn; trong POM có thể cấu hình và ghim phiên bản plugin.

`clean` thuộc lifecycle **khác** default lifecycle. Vì vậy `mvn clean package` có nghĩa là làm sạch kết quả cũ rồi chạy default lifecycle đến `package`.

## 3. Chuẩn bị và dựng cấu trúc dự án

### 3.1. Xác nhận JDK và Maven

Chạy trong Terminal, PowerShell hoặc CMD:

~~~bash
java -version
javac -version
mvn -version
~~~

Cần có JDK, không chỉ môi trường chạy Java: Maven Compiler Plugin dùng trình biên dịch của JDK. Hãy nhìn cả dòng `Java version` và `Java home` của `mvn -version`. Nếu `java -version` là 17 nhưng Maven dùng JDK thấp hơn, biên dịch với release 17 có thể thất bại; sửa cấu hình `JAVA_HOME` và `PATH` trước khi tiếp tục.

Trong lần build đầu, Maven có thể tải plugin và thư viện từ repository qua Internet. Việc tải dependency thường khiến lần chạy đầu lâu hơn lần sau; đó chưa phải dấu hiệu chương trình có lỗi.

### 3.2. Tạo các file đúng đường dẫn

Tạo một thư mục tên `maven-first`, sau đó tạo bốn file:

~~~text
maven-first/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── vn/
    │           └── example/
    │               └── mavenfirst/
    │                   ├── App.java
    │                   └── Calculator.java
    └── test/
        └── java/
            └── vn/
                └── example/
                    └── mavenfirst/
                        └── CalculatorTest.java
~~~

Maven mặc định tìm mã chính trong `src/main/java` và test trong `src/test/java`. Thư mục `vn/example/mavenfirst` khớp với khai báo `package vn.example.mavenfirst;` trong các file Java.

### 3.3. Viết `pom.xml` hoàn chỉnh

Nội dung file `maven-first/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>maven-first</artifactId>
    <version>1.0.0</version>
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

Trong POM này:

- `groupId`, `artifactId` và `version` xác định artifact `vn.example:maven-first:1.0.0`. Với `packaging=jar`, tên JAR mặc định là `maven-first-1.0.0.jar`.
- `maven.compiler.release=17` yêu cầu biên dịch tương thích API/bytecode Java 17. Nó không tự cài JDK cho bạn.
- Dependency `junit-jupiter` với `scope=test` chỉ phục vụ mã kiểm thử, không đi vào classpath runtime của ứng dụng.
- Compiler Plugin, Surefire Plugin và JAR Plugin lần lượt xử lý biên dịch, kiểm thử và đóng gói. Ghim phiên bản giúp kết quả ít phụ thuộc vào phiên bản plugin mặc định của Maven.
- Không có plugin nào tạo fat JAR. JAR này chỉ chứa lớp/tài nguyên sản phẩm của dự án, không nhúng JUnit hoặc các thư viện bên ngoài.

### 3.4. Viết mã chính

File `src/main/java/vn/example/mavenfirst/Calculator.java`:

~~~java
package vn.example.mavenfirst;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }
}
~~~

`Math.addExact` trả tổng của hai số nguyên `int` hoặc ném `ArithmeticException` khi phép cộng tràn số. Dùng phương thức này để test có một tình huống lỗi rõ ràng, thay vì chỉ kiểm tra phép cộng dễ đoán.

File `src/main/java/vn/example/mavenfirst/App.java`:

~~~java
package vn.example.mavenfirst;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("2 + 3 = " + Calculator.add(2, 3));
    }
}
~~~

Cả hai lớp chỉ dùng Java chuẩn. Khi chạy thành công, chương trình in đúng một dòng:

~~~text
2 + 3 = 5
~~~

### 3.5. Viết hai unit test

File `src/test/java/vn/example/mavenfirst/CalculatorTest.java`:

~~~java
package vn.example.mavenfirst;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> Calculator.add(Integer.MAX_VALUE, 1));
    }
}
~~~

Test thứ nhất kiểm tra kết quả đúng; test thứ hai xác nhận `Math.addExact` xử lý tràn số bằng ngoại lệ. Surefire phiên bản đã khai báo phát hiện class có tên kết thúc bằng `Test` và chạy JUnit Jupiter test thông qua JUnit Platform.

**Điểm cần quan sát:** `CalculatorTest.java` nằm trong `src/test/java`. Nó được biên dịch vào `target/test-classes` và không được đóng gói vào JAR sản phẩm trong cấu hình mặc định này.

## 4. Thí nghiệm A — Chỉ chạy `compile`

Từ thư mục chứa `pom.xml`, chạy:

~~~bash
mvn clean compile
~~~

Quan sát log: Maven thực thi quá trình làm sạch trước, sau đó xử lý mã chính và biên dịch. Khi mọi thứ hợp lệ, cuối log có dòng:

~~~text
BUILD SUCCESS
~~~

Các thông báo plugin, thời gian thực thi và số file biên dịch có thể thay đổi giữa máy hoặc giữa các lần chạy; chỉ dùng các dấu mốc trên làm tiêu chí thay vì chép nguyên một đoạn log mẫu.

Sau `mvn clean compile`, các tệp quan trọng sẽ xuất hiện:

~~~text
target/
└── classes/
    └── vn/
        └── example/
            └── mavenfirst/
                ├── App.class
                └── Calculator.class
~~~

Maven có thể tạo thêm thư mục metadata dưới `target/`. Bảng trên chỉ nêu các file cần tìm, không phải cam kết toàn bộ `target/` chỉ chứa hai file.

Hãy thử chạy trực tiếp **các file class** vừa biên dịch:

~~~bash
java -cp target/classes vn.example.mavenfirst.App
~~~

Đầu ra của ứng dụng:

~~~text
2 + 3 = 5
~~~

Ở thời điểm này, do trước đó đã chạy `clean` và chỉ yêu cầu `compile`:

- `target/classes` có mã Java chính đã biên dịch.
- `target/test-classes` **chưa có** từ lần build sạch này.
- `target/surefire-reports` **chưa có** test report từ lần build sạch này.
- `target/maven-first-1.0.0.jar` **chưa có**, vì phase `package` chưa chạy.

Câu hỏi kiểm tra: nếu người khác đưa cho bạn một thư mục `target/classes` có các file `.class` mà không có JAR, có thể kết luận build đã chạy đến `package` chưa? **Chưa thể; chỉ riêng các file class không chứng minh đã đóng gói.**

## 5. Thí nghiệm B — Chạy `test` và đọc báo cáo

Từ thư mục gốc, chạy:

~~~bash
mvn clean test
~~~

Sau `clean`, Maven bắt đầu lại từ trạng thái sạch; quá trình này đi qua biên dịch mã chính, biên dịch mã test rồi chạy unit test. Nếu cả hai test đã viết đều thành công, trong log thường có thông tin tương tự:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Dòng `Tests run: ...` là phần thông tin về test; những dòng xung quanh, định dạng và thứ tự log có thể khác tùy plugin và cấu hình. Điều bạn cần xác nhận là **2 test đã được chạy** và **không có test fail/error**. `BUILD SUCCESS` một mình chưa chứng minh rằng dự án thực sự có test được chạy.

Các dấu mốc có thể kiểm tra:

~~~text
target/
├── classes/
│   └── vn/example/mavenfirst/
│       ├── App.class
│       └── Calculator.class
├── test-classes/
│   └── vn/example/mavenfirst/
│       └── CalculatorTest.class
└── surefire-reports/
    ├── vn.example.mavenfirst.CalculatorTest.txt
    └── TEST-vn.example.mavenfirst.CalculatorTest.xml
~~~

`target/surefire-reports` chứa báo cáo Surefire ở dạng văn bản và XML. Các đường dẫn trên phản ánh mặc định của cấu hình đã cho; nếu dự án thay đổi cấu hình báo cáo, đường dẫn/tên file có thể khác.

File `.txt` thường tóm tắt số test, lỗi và thời gian; XML còn có thông tin từng testcase. Bạn có thể mở báo cáo để xác minh:

- `addsTwoNumbers` và `rejectsOverflow` đều được thực thi.
- Tổng số test là 2, thất bại 0, lỗi 0 và bỏ qua 0.
- Nếu test thất bại, báo cáo chứa tên test và thông tin lỗi để truy tìm.

**Lưu ý:** `mvn clean test` không chạy đến `package`, vì vậy lần build sạch này chưa tạo file `target/maven-first-1.0.0.jar`.

## 6. Thí nghiệm C — Chạy `package`, mở JAR và chạy chương trình

Bây giờ chạy:

~~~bash
mvn clean package
~~~

Bạn sẽ thấy Maven đi qua những công việc đã quan sát ở hai thí nghiệm trước: biên dịch mã chính, biên dịch/chạy hai test, rồi mới tạo JAR. Nếu thành công, log kết thúc bằng:

~~~text
BUILD SUCCESS
~~~

Lần này `target/` có thêm file:

~~~text
target/maven-first-1.0.0.jar
~~~

Tên file lấy từ `artifactId=maven-first` và `version=1.0.0` trong POM. Vì chúng ta bắt đầu bằng `clean`, JAR này là kết quả của lần build hiện tại.

### 6.1. Kiểm tra JAR thực sự có gì

Dùng tiện ích `jar` đi kèm JDK:

~~~bash
jar tf target/maven-first-1.0.0.jar
~~~

Danh sách có thể có manifest và metadata Maven; quan trọng là bạn sẽ thấy các entry sau (thứ tự có thể khác):

~~~text
vn/example/mavenfirst/App.class
vn/example/mavenfirst/Calculator.class
~~~

Bạn **không** nên thấy `vn/example/mavenfirst/CalculatorTest.class` trong JAR chính. Lớp test và JUnit dependency phục vụ quá trình kiểm thử, không phải nội dung của JAR ứng dụng trong ví dụ này.

### 6.2. Chạy ứng dụng từ JAR

Vì chương trình chỉ dùng Java chuẩn, một JAR đã đóng gói là đủ trên classpath:

~~~bash
java -cp target/maven-first-1.0.0.jar vn.example.mavenfirst.App
~~~

Đầu ra **chính xác**:

~~~text
2 + 3 = 5
~~~

Không mặc định dùng `java -jar target/maven-first-1.0.0.jar` cho POM này: JAR Plugin chưa được cấu hình `Main-Class` trong manifest. `java -jar` cần manifest có điểm vào thích hợp; còn `java -cp ... <tên-lớp>` nhận trực tiếp tên lớp có phương thức `main`. Dự án có dependency runtime bên ngoài còn phải đặt chúng vào classpath hoặc cấu hình cách đóng gói/phân phối khác.

### 6.3. Kết luận từ ba lần chạy sạch

| Lệnh xuất phát từ thư mục gốc | `target/classes` | `target/test-classes` | `target/surefire-reports` | JAR chính |
| --- | --- | --- | --- | --- |
| `mvn clean compile` | Có | Chưa có | Chưa có | Chưa có |
| `mvn clean test` | Có | Có | Có | Chưa có |
| `mvn clean package` | Có | Có | Có | Có |

Bảng dựa trên chính dự án này, với hai test được phát hiện và không có cấu hình plugin bất thường. Nếu bạn chạy `mvn compile` **không clean** sau một lần `package` trước đó, JAR cũ có thể còn nằm trong `target/`; sự tồn tại của file cũ không chứng minh rằng lệnh `compile` vừa tạo nó.

## 7. Thí nghiệm D — Chủ động làm test thất bại để thấy Maven dừng

Một cách học hữu ích là tạo lỗi có kiểm soát rồi quan sát phase nào thất bại.

Tạm thời sửa **chỉ một dòng** trong `CalculatorTest.java`:

~~~java
assertEquals(99, Calculator.add(2, 3));
~~~

Vì `Calculator.add(2, 3)` thực tế trả 5, test `addsTwoNumbers` sẽ thất bại. Chạy:

~~~bash
mvn clean package
~~~

Bạn cần thấy `BUILD FAILURE`, kèm tên test bị lỗi và thông tin kiểu “expected 99, actual 5” (cách hiển thị có thể khác). Do phase `test` thất bại, Maven mặc định **không tiếp tục đến `package`**. Với `clean` ở đầu, JAR cũ bị dọn trước nên lần chạy này không tạo được `target/maven-first-1.0.0.jar`.

Mở `target/surefire-reports`: lỗi được ghi vào report, là bằng chứng đáng tin hơn việc chỉ đọc dòng `BUILD FAILURE` ở cuối terminal.

Khôi phục đúng dòng ban đầu:

~~~java
assertEquals(5, Calculator.add(2, 3));
~~~

Sau đó chạy lại:

~~~bash
mvn clean package
~~~

Kết quả trở về hai test PASS, có JAR và `BUILD SUCCESS`. **Đừng để dòng kỳ vọng 99 trong mã sau bài thực hành.**

Ngoài ra, nếu cố tình làm hỏng cú pháp `App.java` (ví dụ thiếu dấu chấm phẩy), build sẽ dừng **sớm hơn**, ở phase `compile`. Khi đó test chưa thể chạy. Hai kiểu lỗi khác nhau giúp bạn tìm đúng vị trí hỏng trong pipeline.

## 8. Đọc kết quả build một cách có hệ thống

Một câu trả lời đủ tốt cho “lệnh Maven vừa làm gì?” nên dựa trên **ba nguồn bằng chứng**:

1. **Lệnh bạn đã gọi:** `compile`, `test` hay `package`, có kèm `clean` hay không.
2. **Log của Maven:** plugin goal nào đã chạy, test có thực sự chạy và reactor/build kết thúc thành công hay thất bại. Đừng coi thời gian, số dòng log hoặc thứ tự in thông báo phụ là kết quả bất biến.
3. **Artifact sau build:** `target/classes`, `target/test-classes`, `target/surefire-reports` và `target/*.jar`. Sau lệnh có `clean`, các file này phản ánh lần chạy hiện tại rõ hơn.

Các câu hỏi nên tự trả lời khi quan sát:

- `BUILD SUCCESS` xuất hiện ở thí nghiệm A có đồng nghĩa test đã chạy chưa? **Không**; A chỉ tới `compile`.
- `mvn test` có tạo JAR không? **Không** với POM này, vì chưa tới `package`.
- `mvn package` có chạy test không? **Có** trong cấu hình mặc định, vì nó đi qua phase `test`.
- Test sai làm `mvn package` dừng ở đâu? **Ở phase `test`**, trước khi tạo JAR.
- File `App.class` và `CalculatorTest.class` có nằm cùng thư mục không? **Không**; lần lượt ở `classes` và `test-classes`.
- Có thể chạy JAR bằng `java -jar` mặc định không? **Chưa**; cần manifest/cách đóng gói thích hợp.

## 9. Sai lầm thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp và bước xác minh |
| --- | --- |
| `mvn: command not found` hoặc `mvn is not recognized` | Maven chưa cài/không nằm trong `PATH`; chạy lại `mvn -version` sau khi cấu hình |
| `invalid target release: 17` hoặc `release version 17 not supported` | Maven đang chạy bằng JDK quá cũ; kiểm tra `mvn -version` và `JAVA_HOME` |
| `package vn.example.mavenfirst does not exist`, `cannot find symbol` | Tên `package`, thư mục hoặc lớp không khớp; kiểm tra file đúng đường dẫn và chữ hoa/thường |
| `Tests run: 0` hoặc không có file report test | Test không được phát hiện, đặt sai thư mục/tên, annotation sai hoặc cấu hình Surefire/JUnit sai; kiểm tra `CalculatorTest` và phiên bản plugin |
| Test chạy nhưng báo `Failures: 1` | So sánh giá trị kỳ vọng/thực tế, đọc stack trace và file `surefire-reports` của test đó |
| `BUILD FAILURE` trước cả khi test chạy | Xem plugin/phase đầu tiên gặp lỗi, thường là cấu hình POM, dependency download hoặc compile |
| Không tìm thấy JAR sau `compile` hoặc `test` | Hai phase này chưa đóng gói; chạy `mvn package` sau khi sửa hết lỗi |
| JAR còn sau `mvn compile` | Có thể là file từ một lần `package` cũ; dùng `mvn clean compile` để so sánh chính xác |
| `no main manifest attribute` khi `java -jar` | Chưa khai báo `Main-Class` cho JAR thông thường; dùng `java -cp ... vn.example.mavenfirst.App` theo ví dụ |
| `ClassNotFoundException` khi chạy `java -cp` | Classpath hoặc tên đầy đủ `vn.example.mavenfirst.App` sai; dùng `jar tf` kiểm tra entry |
| Lần chạy đầu tải rất nhiều file | Plugin/dependency chưa có trong local repository; kiểm tra kết nối và cấu hình repository nếu có lỗi tải |

Phân biệt các cách “bỏ qua test” để tránh hiểu nhầm:

- `mvn -DskipTests package` thường vẫn biên dịch test nhưng bỏ **chạy** test.
- `mvn -Dmaven.test.skip=true package` có thể bỏ cả **biên dịch lẫn thực thi** test (được Compiler/Surefire hỗ trợ).

Hai lựa chọn này có thể cần trong tình huống đặc biệt, nhưng **không dùng để che lỗi** trong bài học: nếu bỏ chạy test, `BUILD SUCCESS` không chứng minh unit test đúng. Không xóa file báo cáo rồi kết luận test đã pass.

## 10. Bài tập thực hành và tiêu chí hoàn thành

### Bài tập 1 — Đọc kết quả từng phase

Lần lượt chạy `mvn clean compile`, `mvn clean test` và `mvn clean package`. Sau **mỗi lần**, tự điền bảng kiểm gồm: có `App.class` chưa, có `CalculatorTest.class` chưa, có test report chưa và có JAR chưa. Sau cùng so với bảng ở mục 6.3.

### Bài tập 2 — Phân biệt biên dịch và chạy chương trình

Sau `mvn clean compile`, chạy:

~~~bash
java -cp target/classes vn.example.mavenfirst.App
~~~

Sau `mvn clean package`, chạy:

~~~bash
java -cp target/maven-first-1.0.0.jar vn.example.mavenfirst.App
~~~

Cả hai phải in `2 + 3 = 5`. Giải thích: lệnh đầu lấy bytecode trong thư mục class; lệnh sau lấy bytecode từ file JAR. Cả hai dùng cùng tên lớp có `main`.

### Bài tập 3 — Kiểm tra giá trị của unit test

Cố tình thay `assertEquals(5, ...)` thành `assertEquals(99, ...)` và chạy `mvn clean package`. Ghi lại phase thất bại và file report chứa lý do. Khôi phục test, build lại, đối chiếu có JAR và hai test PASS.

### Bài tập 4 — Thêm chức năng nhỏ

Thêm phương thức sau vào `Calculator`:

~~~java
public static int multiply(int left, int right) {
    return Math.multiplyExact(left, right);
}
~~~

Đây là **đoạn thêm vào trong thân lớp `Calculator`**, không phải một chương trình Java độc lập. Viết thêm test `assertEquals(12, Calculator.multiply(3, 4));` vào lớp `CalculatorTest`, chạy `mvn clean test` và xác nhận số test tăng từ 2 lên 3. Chạy tiếp `mvn package` và kiểm tra JAR vẫn chứa `Calculator.class`.

### Tự đánh giá

Bạn hoàn thành bài khi có thể tự dựng lại cấu trúc `maven-first` từ đầu, chạy đúng ba lệnh, chỉ ra các file sinh ra, đọc báo cáo Surefire, mô tả một build bị chặn do test fail, và giải thích bằng lời của mình rằng:

> `compile` tạo bytecode ứng dụng; `test` biên dịch/chạy test; `package` đi qua các phase cần thiết để đóng gói artifact. `clean` giúp loại kết quả cũ để quan sát lần build hiện tại rõ ràng.

Nếu đã thực hiện được các bước đó, bạn có nền tảng thực tế để học tiếp về Maven dependency, plugin, lifecycle nâng cao và các dự án nhiều mô-đun.
