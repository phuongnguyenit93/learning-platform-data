# src/test/java, src/test/resources và sự tách biệt mã kiểm thử trong dự án Maven

## 1. Vì sao Maven tách mã sản phẩm và mã kiểm thử?

Trong một dự án Java dùng Maven, **mã chạy trong sản phẩm** và **mã dùng để xác nhận sản phẩm hoạt động đúng** có mục đích khác nhau. Maven quy ước tách hai nhóm ngay trong cấu trúc thư mục:

- **src/main/java**: mã nguồn Java của ứng dụng hoặc thư viện.
- **src/main/resources**: tài nguyên của ứng dụng hoặc thư viện, ví dụ cấu hình mặc định, mẫu văn bản, template.
- **src/test/java**: mã Java dùng để kiểm thử, chẳng hạn JUnit tests, helper test, fake/stub.
- **src/test/resources**: dữ liệu thử nghiệm: JSON, CSV, XML, properties, payload giả, file đầu vào, kết quả kỳ vọng.

Sự tách biệt này giúp **đóng gói đúng thứ cần bàn giao**, **cung cấp dependency riêng cho test**, **giữ dữ liệu thử nghiệm ngoài sản phẩm**, và **chạy test với classpath phù hợp**. Một file nằm trong **src/test/** không tự động trở thành một phần của JAR/WAR sản phẩm, nhưng Maven vẫn biên dịch hoặc sao chép nó để chạy kiểm thử khi đến đúng pha.

Trong bài này, “test” chủ yếu chỉ **unit test và các test do Maven Surefire chạy ở pha test**. Kiểm thử tích hợp có thể cần môi trường, naming convention và plugin khác; ta sẽ phân biệt ở phần sau.

## 2. Bốn thư mục tiêu chuẩn và nơi xuất hiện sau build

Ví dụ cấu trúc dự án:

~~~text
sample-service/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/sample/
│   │   │       ├── GreetingService.java
│   │   │       └── App.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       ├── java/
│       │   └── com/example/sample/
│       │       └── GreetingServiceTest.java
│       └── resources/
│           └── fixtures/
│               └── person.txt
└── target/                      # chỉ xuất hiện sau khi build
    ├── classes/
    ├── test-classes/
    └── surefire-reports/        # khi chạy kiểm thử qua Surefire
~~~

Đây là layout mặc định; Maven có thể cấu hình khác trong **pom.xml**, nhưng tuân theo chuẩn sẽ dễ bảo trì và ít cần tùy chỉnh hơn.

| Nguồn | Nội dung | Bước Maven xử lý | Đích mặc định | Có vào JAR chính theo mặc định? |
| --- | --- | --- | --- | --- |
| **src/main/java/** | Mã Java sản phẩm | **compile** | **target/classes/**, dưới dạng **.class** | **Có** |
| **src/main/resources/** | Resource sản phẩm | **process-resources** | **target/classes/** | **Có** |
| **src/test/java/** | Mã test và helper test | **test-compile** | **target/test-classes/**, dưới dạng **.class** | **Không** |
| **src/test/resources/** | Fixtures và resource test | **process-test-resources** | **target/test-classes/** | **Không** |

Với packaging **jar** mặc định, Maven JAR Plugin lấy nội dung chính từ **target/classes/** để đóng gói; **target/test-classes/** không được tự động đưa vào JAR sản phẩm. Với packaging khác hoặc plugin đóng gói tùy chỉnh, cần xem cấu hình thực tế.

Đường dẫn source có từ **java** nhưng bên dưới phải phản ánh **package Java**. Ví dụ class **com.example.sample.GreetingServiceTest** đặt trong **src/test/java/com/example/sample/GreetingServiceTest.java**. Thư mục **resources** không đòi hỏi cấu trúc package, nhưng đường dẫn bên dưới nó quyết định vị trí file trong classpath.

## 3. Maven xử lý test theo vòng đời như thế nào?

Maven có default lifecycle; khi gọi một pha, Maven thực hiện các pha trước nó trong cùng lifecycle. Với dự án Java thông thường:

~~~text
src/main/resources   --process-resources----> target/classes/
src/main/java        --compile--------------> target/classes/
src/test/resources   --process-test-resources> target/test-classes/
src/test/java        --test-compile---------> target/test-classes/
                                  |
                                  v
                              test (Surefire)
                                  |
                                  v
                              package (JAR/WAR)
~~~

Các pha và tác dụng chính:

1. **process-resources**: sao chép hoặc xử lý các resources thuộc **main**.
2. **compile**: biên dịch các Java sources thuộc **main**.
3. **process-test-resources**: sao chép resources thuộc **test**.
4. **test-compile**: biên dịch test Java sources; lúc này class của **main** và các dependency thuộc test scope có thể được dùng.
5. **test**: plugin kiểm thử, thường là **maven-surefire-plugin**, khám phá và chạy test.
6. **package**: tạo artifact theo **packaging**; phần source và test đã được xử lý bởi các pha đi trước, trừ khi cấu hình bỏ qua hoặc thay đổi chúng.

Lệnh thường dùng:

~~~bash
mvn clean test
mvn clean package
~~~

**mvn clean test** thực hiện quá trình đủ để biên dịch và chạy test; nó **không yêu cầu tạo JAR cuối cùng**. **mvn clean package** thường chạy test trước khi tạo JAR. **clean** thuộc một lifecycle riêng, được gọi trước **test/package** để loại bỏ đầu ra cũ.

**mvn test** không bảo đảm tất cả các loại kiểm thử trong dự án đều chạy. Những kiểm thử tích hợp được cấu hình cho **maven-failsafe-plugin**, chẳng hạn, thường chạy ở các pha **integration-test** và **verify** khi gọi **mvn verify**, với cấu hình Failsafe thích hợp.

## 4. Classpath của main và classpath của test khác nhau

**Classpath** là tập vị trí mà Java/JUnit có thể tìm class và resources khi biên dịch hoặc chạy.

Trong mô hình Maven tiêu chuẩn:

- **Main compile/runtime classpath** gồm class/resources chính và các dependency phù hợp với scope đang xét. Không mặc nhiên có **target/test-classes/** hoặc các dependency **test**.
- **Test classpath** có thêm **target/test-classes/**, **target/classes/** và các dependency cần cho kiểm thử. Vì vậy test có thể gọi class của sản phẩm và dùng JUnit.
- Resource **src/test/resources/fixtures/person.txt** được sao chép thành **target/test-classes/fixtures/person.txt**, từ đó test có thể đọc bằng API tải resource trên classpath.
- Khi chỉ chạy ứng dụng được đóng gói bình thường, **target/test-classes/** và JUnit không còn là bộ phận của classpath sản phẩm, trừ khi người vận hành cố ý cấu hình thêm.

Trong nhiều runner Maven thông thường, test classpath đặt **target/test-classes** trước **target/classes**. Nếu có resource **cùng tên và cùng đường dẫn** ở cả **main** và **test**, resource test có thể che resource main trong test. Tránh dựa vào hiện tượng này một cách ngầm định: đặt fixtures vào thư mục **fixtures/** riêng, hoặc nêu rõ mục đích override trong test.

**Test có thể phụ thuộc vào mã main; mã main không được thiết kế để phụ thuộc vào class chỉ có trong test.** Nếu class của **src/main/java** import JUnit hoặc một helper chỉ tồn tại trong **src/test/java**, quá trình build main thường không biên dịch được hoặc bị ràng buộc sai vào môi trường kiểm thử.

## 5. Ví dụ hoàn chỉnh: Java 17 + JUnit Jupiter + fixture

Ví dụ dưới đây có mã ứng dụng, class kiểm thử và resource test. Có thể tạo lại các file trong dự án Maven mới rồi chạy đúng lệnh; **không cần đổi cấu hình thư mục mặc định**.

### 5.1. Tệp pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>test-separation</artifactId>
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
                <version>3.13.0</version>
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

**Giải thích cấu hình:**

- **maven.compiler.release=17**: yêu cầu compiler tạo mã tương thích API/bytecode Java 17, với JDK hỗ trợ cờ release 17.
- **junit-jupiter**: đưa API và engine JUnit Jupiter lên test classpath.
- **scope=test**: Maven chỉ cung cấp dependency này cho các giai đoạn kiểm thử phù hợp; JUnit không trở thành dependency khi compile/chạy ứng dụng chính theo cách mặc định.
- **maven-surefire-plugin**: chạy các test ở pha **test**; phiên bản 3.5.2 hỗ trợ JUnit Platform/Jupiter.
- **packaging=jar**: đóng gói mã và resources chính vào JAR; không đưa test classes/fixtures vào JAR này theo mặc định.

Các phiên bản trên được cố định để ví dụ có tính lặp lại. Nếu dự án thực tế đã dùng **parent POM/BOM/pluginManagement**, hãy thống nhất phiên bản theo chính sách dự án.

### 5.2. Mã sản phẩm trong src/main/java

Tạo **src/main/java/com/example/sample/GreetingService.java**:

~~~java
package com.example.sample;

public final class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Xin chào, " + name.trim() + "!";
    }
}
~~~

Đây là class sản phẩm; nó không import JUnit và không biết sự tồn tại của fixture hay test.

Tạo **src/main/java/com/example/sample/App.java**:

~~~java
package com.example.sample;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(new GreetingService().greet("Mai"));
    }
}
~~~

Class **App** dùng để chạy thử logic của sản phẩm độc lập với JUnit.

### 5.3. Resource thử nghiệm trong src/test/resources

Tạo file **src/test/resources/fixtures/person.txt** với nội dung UTF-8:

~~~text
An
~~~

Đây là một **fixture**: dữ liệu đầu vào cố định để test đọc và so sánh kết quả. File này không phải cấu hình ứng dụng cho môi trường production. Sau pha **process-test-resources**, nó nằm tại **target/test-classes/fixtures/person.txt**.

Có thể có thêm các file test JSON, XML, CSV, certificate giả hoặc mẫu HTTP payload trong cùng thư mục. Với dữ liệu liên quan riêng một test, đặt đường dẫn rõ nghĩa, tránh nhét tất cả vào thư mục gốc của resources.

### 5.4. Test trong src/test/java

Tạo **src/test/java/com/example/sample/GreetingServiceTest.java**:

~~~java
package com.example.sample;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {

    @Test
    void readsNameFromTestFixture() throws IOException {
        try (InputStream input =
                 GreetingServiceTest.class.getResourceAsStream("/fixtures/person.txt")) {
            assertNotNull(input, "Fixture fixtures/person.txt must exist");

            String name = new String(
                    input.readAllBytes(), StandardCharsets.UTF_8
            ).trim();

            String greeting = new GreetingService().greet(name);
            assertEquals("Xin chào, An!", greeting);
        }
    }

    @Test
    void rejectsBlankName() {
        GreetingService service = new GreetingService();

        assertThrows(
                IllegalArgumentException.class,
                () -> service.greet("  ")
        );
    }
}
~~~

**Vì sao ví dụ đúng về phạm vi?**

- Test đặt trong **src/test/java** và đặt tên **GreetingServiceTest**, thuộc các tên mà Surefire mặc định tìm kiếm.
- **@Test**, **assertEquals**, **assertThrows** thuộc JUnit trong **test** scope.
- Test sử dụng **GreetingService** là mã từ **src/main/java** đã biên dịch.
- **getResourceAsStream("/fixtures/person.txt")** tìm resource từ gốc classpath. Dấu **/** đầu đường dẫn là quan trọng khi gọi **Class.getResourceAsStream**: thiếu nó thì đường dẫn sẽ tương đối với package của class.
- **assertNotNull** cho lỗi rõ khi fixture không tồn tại, tránh gặp **NullPointerException** khó hiểu ở bước **readAllBytes**.
- **try-with-resources** đóng input stream khi test xong.
- **StandardCharsets.UTF_8** tránh phụ thuộc charset mặc định của hệ thống.
- Test đo giá trị trả về và exception thay vì phụ thuộc vào log ngẫu nhiên hoặc dịch vụ ngoài.

### 5.5. Chạy và kiểm tra kết quả

Điều kiện: Maven 3.9+ và JDK 17+ khả dụng, chạy lệnh trong thư mục chứa **pom.xml**. Nếu dự án có Maven Wrapper được commit, có thể thay **mvn** bằng **./mvnw** (Unix-like) hoặc **.\mvnw.cmd** (PowerShell).

~~~bash
mvn -version
mvn clean test
~~~

Nếu mọi dependency/plugin tải được, Maven sẽ biên dịch main rồi test, copy fixture và chạy hai phương thức test. Kết quả quan trọng là test run thành công với **2 tests** và **0 failures, 0 errors**; dòng log cụ thể có thể khác tùy phiên bản plugin, JDK và thiết lập log.

Để chạy riêng một lớp test:

~~~bash
mvn -Dtest=GreetingServiceTest test
~~~

Để quan sát ứng dụng **không sử dụng test classpath** sau khi đã biên dịch:

~~~bash
java -cp target/classes com.example.sample.App
~~~

Với console hiển thị UTF-8, stdout của lệnh **java** là:

~~~text
Xin chào, Mai!
~~~

Ứng dụng không cần JUnit hoặc file **fixtures/person.txt** để chạy lệnh này.

Để tạo JAR sản phẩm và kiểm tra nội dung:

~~~bash
mvn clean package
jar tf target/test-separation-1.0.0.jar
java -cp target/test-separation-1.0.0.jar com.example.sample.App
~~~

Lệnh **jar tf** phải liệt kê các class sản phẩm như **com/example/sample/GreetingService.class** và **com/example/sample/App.class**. Với cấu hình mặc định trong ví dụ, nó **không được có** **com/example/sample/GreetingServiceTest.class** hay **fixtures/person.txt**. Lệnh **java -cp** cuối cùng in:

~~~text
Xin chào, Mai!
~~~

Ví dụ không cấu hình **Main-Class** trong manifest nên **không giả định** có thể dùng **java -jar**. Việc đóng gói class test và resource test ra khỏi JAR độc lập với việc JAR có executable manifest hay không.

## 6. Phân biệt resource main và resource test khi đọc bằng Java

**src/main/resources** và **src/test/resources** đều là cây resources để truy cập qua classpath, nhưng chúng phục vụ các mục đích khác nhau.

| Tình huống | Đặt ở đâu? | Ai cần nó? | Có trong JAR chính mặc định? |
| --- | --- | --- | --- |
| Template email dùng bởi ứng dụng | **src/main/resources/templates/** | Mã ứng dụng trong production | Có |
| Cấu hình mặc định không chứa secret | **src/main/resources/** | Ứng dụng, thư viện | Có |
| Input JSON giả để test parser | **src/test/resources/fixtures/** | Test parser | Không |
| Expected output CSV của test | **src/test/resources/expected/** | Test so sánh | Không |
| Properties chỉ bật chế độ giả lập trong test | **src/test/resources/** | Test hoặc framework test | Không |
| File credential thực tế của CI | **Không commit vào resources** | CI secret manager / environment | Không nên đóng gói vào bất kỳ JAR nào |

Không nên mở file test resource theo đường dẫn filesystem như **src/test/resources/fixtures/person.txt** trong mã test nếu mục tiêu là test hoạt động trên cả IDE và Maven CI. Khi test chạy từ thư mục khác, đường dẫn tương đối filesystem có thể sai. Truy cập **resource trên classpath** sẽ ổn định hơn:

~~~java
try (InputStream input =
         GreetingServiceTest.class.getResourceAsStream("/fixtures/person.txt")) {
    // xử lý input; ví dụ đầy đủ ở phần trên
}
~~~

Đoạn trên chỉ minh họa API lấy resource; nó không phải một chương trình Java độc lập và cần được đặt trong một phương thức có xử lý ngoại lệ thích hợp.

Lưu ý **Class.getResourceAsStream** và **ClassLoader.getResourceAsStream** dùng quy tắc đường dẫn hơi khác:

- **SomeClass.class.getResourceAsStream("/fixtures/person.txt")**: đường dẫn tuyệt đối từ classpath root nhờ dấu **/**.
- **SomeClass.class.getClassLoader().getResourceAsStream("fixtures/person.txt")**: đường dẫn từ classpath root, thường **không thêm /**.

Test có thể đọc resource main vì **target/classes** cũng nằm trên test classpath. Ngược lại, mã main chạy độc lập không nên yêu cầu resource chỉ có ở **target/test-classes**.

## 7. Scope test trong pom.xml và ranh giới dependency

Các thư viện dùng trong test thường được khai báo trong **dependencies** với **scope=test**, chẳng hạn JUnit, Mockito hoặc các thư viện tạo dữ liệu giả (tùy nhu cầu).

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
~~~

Điều này không làm JUnit “biến mất” khỏi máy; Maven vẫn tải nó về local repository để biên dịch/chạy test. Tuy nhiên, **scope=test** nghĩa là JUnit không tham gia main compile classpath và không được khai báo như dependency runtime/compile của artifact phát hành theo cách thông thường.

Quy tắc thiết kế thực tế:

- Class ở **src/main/java** được phép phụ thuộc vào các thư viện thuộc scope phù hợp với sản phẩm, và không nên phụ thuộc vào JUnit/helper test.
- Class ở **src/test/java** được phép dùng class ở **src/main/java** và thư viện test.
- Nếu nhiều module cần tái sử dụng helper test, cân nhắc module test utilities hoặc artifact **test-jar** được xuất bản chủ ý; đừng tự copy **target/test-classes** vào JAR production.
- Nếu dependency test bị khai báo nhầm **compile** hoặc **runtime**, hãy kiểm tra lại POM; việc này có thể kéo thư viện test vào graph dependency của sản phẩm một cách không cần thiết.

Dùng **mvn dependency:tree** có thể kiểm tra cây dependency; với plugin tương ứng, **-Dscope=test** hỗ trợ lọc phạm vi hiển thị để phục vụ chẩn đoán. Đọc effective POM nếu parent hoặc dependency management làm phiên bản/scope khó đoán.

## 8. Mã test, test helper và fixture nên được tổ chức thế nào?

Thực tế, không phải mọi file trong **src/test/java** đều cần có phương thức **@Test**. Có thể đặt helper thuần Java, factory tạo object, fake implementation hoặc custom assertion ở đó vì chúng chỉ phục vụ kiểm thử.

Ví dụ:

~~~text
src/test/
├── java/com/example/sample/
│   ├── GreetingServiceTest.java     # test được Surefire phát hiện
│   └── FixtureLoader.java           # helper, không phải test độc lập
└── resources/
    ├── fixtures/
    │   ├── person.txt
    │   └── request.json
    └── expected/
        └── response.json
~~~

Nguyên tắc đáng áp dụng:

1. **Test độc lập:** mỗi test tự tạo điều kiện đầu vào cần thiết; không phụ thuộc vào thứ tự chạy test khác.
2. **Fixture nhỏ, rõ nghĩa:** dữ liệu cố định, dễ đọc, có tên gợi trường hợp nghiệp vụ; không đẩy toàn bộ dữ liệu production vào repository.
3. **Không chứa secret:** password, token thật và khóa riêng phải được quản lý bằng công cụ secrets của CI.
4. **Không sửa resource trong thư mục nguồn khi test chạy:** nếu cần ghi file, dùng thư mục tạm và dọn sau test; tránh làm Git bẩn hoặc gây xung đột khi chạy song song.
5. **Khớp package:** test thường đặt trong cùng package với class được test để hiểu chức năng và, khi phù hợp, truy cập package-private API; không nhất thiết phải cùng đường dẫn nếu có lý do tổ chức khác.
6. **Không nhập nhằng tên resource:** đặt test fixture dưới **fixtures/**, trừ khi test chủ đích kiểm tra việc override cấu hình main.
7. **Tách test lâu/chậm:** test cần database thực, network hoặc container có thể yêu cầu cấu hình integration test rõ ràng thay vì gộp hết vào unit test nhanh.

Việc **src/test/resources** được đưa lên test classpath không có nghĩa mọi thư mục bên trong sẽ tự được JUnit hiểu như test case. Plugin/framework chỉ tự chạy những test class phù hợp với cơ chế discovery của nó; file JSON/CSV chỉ là dữ liệu cho test khai thác.

## 9. Surefire khám phá test thế nào và khi nào dùng Failsafe?

Với Maven Surefire Plugin, các tên test class thường được phát hiện theo quy ước mặc định:

- **Test*.java**
- **\*Test.java**
- **\*Tests.java**
- **\*TestCase.java**

Ví dụ **GreetingServiceTest** ở phần trên khớp **\*Test.java**. Một class chỉ có tên **GreetingServiceCheck** có thể không được chạy nếu không chỉnh cấu hình include/exclude. Cũng cần framework test phù hợp (ví dụ JUnit Jupiter engine trên test classpath); có file tên **\*Test.java** nhưng không có test hợp lệ không đồng nghĩa test thực sự được thực thi.

**maven-surefire-plugin** thường chạy unit test trong pha **test**:

~~~bash
mvn test
mvn -Dtest=GreetingServiceTest test
~~~

**maven-failsafe-plugin** thường được cấu hình để chạy integration tests ở các pha **integration-test/verify** và dùng quy ước tên như **\*IT**, **IT\*** theo cấu hình. Không nên kết luận một lớp test trong **src/test/java** chắc chắn chạy ở pha **test** chỉ dựa vào tên thư mục; việc khám phá còn phụ thuộc plugin, tên class và cấu hình chạy.

Lưu ý: **src/test/java** có thể chứa cả unit test và integration test trong một dự án đơn giản. Với dự án lớn, nhóm có thể tổ chức các source set/plugin riêng để phân biệt môi trường và thời điểm chạy. Đó là quyết định cấu hình thêm, không thay đổi ý nghĩa mặc định của **src/test/resources**.

## 10. Những thao tác Maven dễ gây hiểu nhầm

| Lệnh / cấu hình | Điều thường diễn ra | Hiểu nhầm cần tránh |
| --- | --- | --- |
| **mvn compile** | Xử lý main resources và biên dịch main sources | Không tự biên dịch/chạy test ở pha test |
| **mvn test-compile** | Xử lý các pha tới test-compile, gồm copy test resources và biên dịch test sources | Không yêu cầu chạy test |
| **mvn test** | Biên dịch các phần cần thiết rồi chạy test qua Surefire | Không tạo JAR cuối cùng |
| **mvn package** | Chạy các pha trước rồi đóng gói artifact | Không mặc định đưa test classes/fixtures vào JAR chính |
| **mvn verify** | Chạy tới verify; có thể gồm integration checks khi Failsafe/plug-in khác được cấu hình | Không mặc định mọi integration test ngoài hệ Maven đều được chạy |
| **mvn -DskipTests package** | Với các plugin chuẩn, bỏ qua chạy test nhưng thường vẫn compile test sources | Bỏ chạy test không đồng nghĩa bỏ test-compile |
| **mvn -Dmaven.test.skip=true package** | Với các plugin hỗ trợ, bỏ cả việc compile và chạy test | Không dùng như cách xác nhận mã đã pass test |

Chỉ nên bỏ qua test khi có lý do rõ ràng trong workflow. Một bản build tạo JAR thành công với **-DskipTests** không chứng minh các test vừa pass.

## 11. Sai lầm thường gặp và cách xử lý

**Lỗi 1 — Đặt class test trong src/main/java.** Dẫn đến source sản phẩm import JUnit khi main compile không có dependency scope test, hoặc buộc người phát triển thêm JUnit vào main dependency sai mục đích. **Cách sửa:** chuyển test sang **src/test/java**, giữ các import framework test chỉ ở phía test.

**Lỗi 2 — Đặt fixture trong src/main/resources cho tiện.** File fixture có thể được đóng gói vào JAR sản phẩm không cần thiết, thậm chí lộ dữ liệu. **Cách sửa:** dùng **src/test/resources**, truy cập qua classpath trong test.

**Lỗi 3 — Dùng filesystem path cố định trong test.** Test pass khi chạy từ IDE nhưng fail trên CI do working directory khác. **Cách sửa:** dùng **getResourceAsStream** với đường dẫn từ classpath root.

**Lỗi 4 — Test đọc nhầm resource cùng tên với main.** Classpath test có thể ưu tiên bản ở **target/test-classes** làm test pass nhưng hành vi production khác. **Cách sửa:** đặt đường dẫn riêng hoặc viết test kiểm tra rõ tài nguyên nào được dùng.

**Lỗi 5 — Test class được biên dịch nhưng không chạy.** Tên không khớp Surefire discovery hoặc thiếu JUnit engine/provider phù hợp. **Cách sửa:** kiểm tra naming, POM và báo cáo ở **target/surefire-reports/**; đừng chỉ dựa vào thông báo build success.

**Lỗi 6 — Chạy lại test với dữ liệu cũ trong target/test-classes.** Kết quả có thể gây khó hiểu khi có thay đổi cấu hình resource hoặc artifact cũ. **Cách sửa:** tái tạo bằng **mvn clean test** trong môi trường thử nghiệm, kiểm tra file nguồn và đường dẫn resource.

**Lỗi 7 — Tin rằng scope=test làm mọi class test “không thể chạy” ngoài Maven.** Thực tế JVM vẫn có thể chạy nếu tự cung cấp classpath test/JUnit, nhưng điều đó không thuộc cách đóng gói sản phẩm mặc định. **Cách hiểu đúng:** scope và source layout kiểm soát classpath/lifecycle của Maven, không phải cơ chế bảo mật chống chạy class.

**Lỗi 8 — Đưa test JAR hoặc test fixtures vào artifact sản phẩm khi cần chia sẻ helper.** Có thể làm tăng rủi ro rò rỉ fixture, giả định sai về runtime. **Cách sửa:** thiết kế artifact test riêng có mục đích rõ, ví dụ test-jar có classifier, và chỉ publish cho đối tượng cần dùng.

**Lỗi 9 — Đặt cấu hình bí mật trong test resources rồi commit Git.** Test resource không vào JAR chính nhưng vẫn nằm trong repository, artifact lưu trữ và CI logs. **Cách sửa:** dùng dữ liệu giả; secret thật lấy từ secret manager hoặc biến môi trường được quản lý.

## 12. Kiểm tra nhanh sau khi tạo cấu trúc dự án

Lần đầu thiết lập dự án nên xác minh tuần tự:

1. Mở **pom.xml**: dependency test có **scope=test**, plugin kiểm thử hiện diện và tương thích phiên bản Java/framework.
2. Kiểm tra package/cấu trúc **src/main/java** và **src/test/java** khớp.
3. Đặt fixture tại **src/test/resources/fixtures/** và dùng đường dẫn classpath trong test.
4. Chạy **mvn clean test**; xác nhận test được phát hiện và **test count** đúng, không chỉ có BUILD SUCCESS.
5. Kiểm tra **target/classes/** chỉ chứa main class/resources, **target/test-classes/** có test class/fixtures.
6. Chạy **mvn clean package** và dùng **jar tf** để xác minh JAR chính không mang test fixture/test class.
7. Chạy ứng dụng từ **target/classes** hoặc JAR đúng cách; bảo đảm ứng dụng không phụ thuộc vào test classpath.
8. Đưa source chính, test sources, fixture giả, POM và hướng dẫn chạy test vào Git; thường bỏ qua **target/**.

Tự kiểm tra bằng ba câu hỏi: **Mã này có phục vụ runtime sản phẩm không?** Nếu có, cân nhắc **src/main/**. **Nó chỉ phục vụ phép thử hay dữ liệu kỳ vọng?** Đặt trong **src/test/**. **Nó có xuất hiện trong artifact chính không?** Kiểm tra kết quả đóng gói thật thay vì suy đoán từ tên thư mục.

## Tài liệu tham khảo

- [Apache Maven — Introduction to the Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Surefire Plugin — Using JUnit 5 Platform](https://maven.apache.org/components/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven Resources Plugin — testResources goal](https://maven.apache.org/plugins/maven-resources-plugin/testResources-mojo.html)
- [Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/)
