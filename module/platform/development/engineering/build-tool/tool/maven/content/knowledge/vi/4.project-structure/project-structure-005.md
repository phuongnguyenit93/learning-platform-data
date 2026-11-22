# target/classes, target/test-classes và các đầu ra trung gian trong Maven

## 1. Bức tranh chung: từ nguồn vào đến sản phẩm build

Trong dự án Maven theo quy ước, **src/** chứa mã nguồn và tài nguyên do nhóm phát triển quản lý; **target/** chứa kết quả do Maven và các plugin tạo ra. Hai thư mục quan trọng nhất khi build Java là:

- **target/classes**: bytecode của phần ứng dụng/thư viện và resource chính đã được xử lý.
- **target/test-classes**: bytecode của các lớp kiểm thử và resource dành cho kiểm thử.

Ngoài hai thư mục này, **target/** còn có thể chứa báo cáo test, mã nguồn sinh tự động, thông tin hỗ trợ biên dịch, metadata và các artifact đã đóng gói.

Ví dụ từ **src/main/java/vn/example/Greeting.java**, Maven Compiler Plugin biên dịch thành **target/classes/vn/example/Greeting.class**. Từ **src/test/java/vn/example/GreetingTest.java**, plugin biên dịch thành **target/test-classes/vn/example/GreetingTest.class**. Đường dẫn tệp **.class** phản ánh tên package Java.

Từ khóa quan trọng là **“có thể”**: Maven không sinh mọi thư mục sau một lệnh bất kỳ. Đầu ra phụ thuộc vào **pha lifecycle đã chạy**, **packaging**, **plugin**, phiên bản công cụ và cấu hình POM. Một dự án có packaging **pom** không nhất thiết tạo bytecode; một dự án chưa chạy test không nhất thiết có báo cáo test.

Hiểu đúng đường đi này giúp chẩn đoán lỗi classpath, xem test nào được biên dịch, phân biệt artifact chính với file test, tránh sửa nhầm file sinh tự động và giải thích khác biệt giữa kết quả build trên máy cá nhân với CI.

## 2. Cấu trúc Maven tiêu chuẩn

Với dự án Java có packaging **jar**, sau khi chạy build và test, có thể thấy cấu trúc điển hình:

~~~text
maven-output-demo/
├── pom.xml
├── src/                                      # ĐẦU VÀO
│   ├── main/
│   │   ├── java/
│   │   │   └── vn/example/build/Greeting.java
│   │   └── resources/
│   │       └── app.properties
│   └── test/
│       ├── java/
│       │   └── vn/example/build/GreetingTest.java
│       └── resources/
│           └── fixture.txt
└── target/                                   # ĐẦU RA
    ├── classes/
    │   ├── vn/example/build/Greeting.class
    │   └── app.properties
    ├── test-classes/
    │   ├── vn/example/build/GreetingTest.class
    │   └── fixture.txt
    ├── surefire-reports/
    │   └── TEST-vn.example.build.GreetingTest.xml
    └── maven-output-demo-1.0.0.jar
~~~

Sơ đồ trên mô tả đầu ra **điển hình sau pha package**, khi kiểm thử JUnit được cấu hình và chạy. Tên của báo cáo XML phụ thuộc plugin và test đã thực sự thực thi; các thư mục khác có thể xuất hiện thêm. **src/** cần được lưu và quản lý bằng Git; **target/** thường là kết quả có thể tạo lại.

| Nguồn hoặc kết quả | Vị trí mặc định | Mục đích |
| --- | --- | --- |
| Mã nguồn chính | **src/main/java** | Java class của ứng dụng/thư viện. |
| Resource chính | **src/main/resources** | Tệp cấu hình/dữ liệu để lên classpath chính. |
| Mã nguồn test | **src/test/java** | Unit test và mã hỗ trợ kiểm thử. |
| Resource test | **src/test/resources** | Dữ liệu/cấu hình chỉ dùng cho test. |
| Bytecode và resource chính | **target/classes** | Đầu vào cho chạy ứng dụng và đóng gói JAR chính. |
| Bytecode và resource test | **target/test-classes** | Đầu vào cho việc thực thi test. |
| Kết quả test | **target/surefire-reports** | Báo cáo do Maven Surefire Plugin tạo nếu chạy. |
| Artifact chính | **target/artifactId-version.jar** | JAR được sinh khi packaging là jar và pha package chạy thành công. |

## 3. target/classes có những gì?

Maven thường lấy nguồn Java từ **project.build.sourceDirectory**, mặc định **src/main/java**, và biên dịch sang **project.build.outputDirectory**, mặc định **target/classes**. Maven Compiler Plugin tạo **.class** (bytecode JVM), không chép nguyên tệp **.java** sang output.

Ví dụ một class khai báo package **vn.example.build**:

~~~java
package vn.example.build;

public final class Greeting {
    public static String message() {
        return "Xin chào, Maven!";
    }
}
~~~

Nếu file nguồn nằm ở **src/main/java/vn/example/build/Greeting.java**, đầu ra dự kiến là **target/classes/vn/example/build/Greeting.class**. Một file nguồn có thể tạo nhiều tệp **.class** (ví dụ lớp lồng nhau); không nên giả định tương quan một-một giữa file nguồn và bytecode.

Maven Resources Plugin thường chạy ở pha **process-resources** để sao chép/xử lý nội dung **src/main/resources/** sang cùng **target/classes/**. Vì vậy thư mục này chứa được cả:

- **.class** của chương trình;
- **.properties**, **.xml**, **.yaml**, ảnh, văn bản hoặc resource khác;
- resource được plugin bổ sung theo cấu hình riêng.

Chẳng hạn **src/main/resources/app.properties** có thể được sao chép thành **target/classes/app.properties**. Khi triển khai, chương trình nên truy cập resource qua **classpath** thay vì phụ thuộc vào đường dẫn source của máy build.

Với **packaging=jar**, Maven JAR Plugin thường đóng gói nội dung **target/classes** vào artifact chính. Do đó cần tránh đặt bí mật triển khai trong **src/main/resources**: chúng có thể đi vào JAR được phát hành.

Có **target/classes** không đồng nghĩa toàn bộ build thành công. Pha **compile** có thể đã chạy xong trong khi test ở pha sau còn thất bại. Hãy đối chiếu mục tiêu Maven và mã thoát của lần build.

## 4. target/test-classes có những gì?

Hai mặc định liên quan đến test là:

- **project.build.testSourceDirectory**: **src/test/java**.
- **project.build.testOutputDirectory**: **target/test-classes**.

Ở pha **process-test-resources**, Maven xử lý resource từ **src/test/resources/** sang **target/test-classes**. Ở **test-compile**, Maven Compiler Plugin biên dịch các lớp test vào đó. Tại pha **test**, Maven Surefire Plugin có thể thực thi test đã được nhận diện và tạo báo cáo.

**Classpath dành cho test** thường gồm **target/test-classes**, **target/classes** và các dependency phù hợp cho kiểm thử. Vì vậy **GreetingTest** có thể gọi **Greeting.message()** mà không phải đóng gói JAR trước.

| Khía cạnh | target/classes | target/test-classes |
| --- | --- | --- |
| Mã nguồn | **src/main/java** | **src/test/java** |
| Resource | **src/main/resources** | **src/test/resources** |
| Được tạo ở pha | **process-resources / compile** | **process-test-resources / test-compile** |
| Chức năng | Chạy và đóng gói ứng dụng/thư viện | Chạy unit test và đọc fixture |
| Có trong JAR chính mặc định | Có với nội dung được JAR Plugin đưa vào | **Không** |
| Có dùng dependency scope test | Không thuộc classpath chính thông thường | Có thể có dependency test như JUnit |

**Không coi test-classes là một thư mục runtime cần triển khai.** JAR chính mặc định không chứa lớp test và fixture test. Muốn xuất bản test classes cho mục đích đặc biệt thì phải cấu hình goal như **jar:test-jar**; đó là artifact phụ, không tự xuất hiện trong mọi dự án.

Tương tự, dependency **scope=test** phục vụ kiểm thử, không nên chuyển sang **compile** chỉ để sửa lỗi test không tìm thấy lớp nếu nguyên nhân thực tế là đặt nhầm file hoặc cấu hình plugin.

## 5. Mối liên hệ với Maven lifecycle

Với dự án đóng gói JAR thông thường, các pha quan trọng có thứ tự:

~~~text
validate
   |
process-resources          sao chép/xử lý resource chính
   |
compile                    biên dịch Java chính
   |
process-test-resources     sao chép/xử lý resource test
   |
test-compile               biên dịch Java test
   |
test                       chạy unit test qua Surefire
   |
package                    đóng gói artifact (ví dụ JAR)
   |
verify                     chạy các kiểm tra bổ sung đã được bind
~~~

Sơ đồ chỉ hiển thị những mốc liên quan đến bài học; lifecycle thật còn có các pha xen giữa. Khi gọi một pha, Maven chạy các pha đứng trước nó **trong cùng lifecycle**.

| Lệnh | Đầu ra có thể mong đợi |
| --- | --- |
| **mvn compile** | Tạo/cập nhật **target/classes**; chưa yêu cầu test-compile. |
| **mvn test-compile** | Có thể tạo cả **target/classes** và **target/test-classes**, chưa yêu cầu chạy test. |
| **mvn test** | Chạy các pha trước và Surefire test; thường có **target/surefire-reports** nếu test chạy. |
| **mvn package** | Chạy đến package, có thể tạo JAR cho packaging **jar** sau các pha test. |
| **mvn verify** | Chạy đến verify; các kiểm tra bổ sung chỉ có khi được cấu hình/bind. |
| **mvn clean** | Chạy lifecycle clean để dọn thư mục build (**target/** mặc định). |
| **mvn clean test** | Dọn đầu ra cũ rồi biên dịch/chạy test. |

**Không mong đợi JAR sau mvn test**: pha test đứng trước package. **Không mong đợi target/test-classes sau mvn compile**: test-compile chưa chạy. **Không mặc định mọi test đều chạy** chỉ vì có file Java trong thư mục test: framework, tên lớp, plugin và cấu hình phải phù hợp.

## 6. Ví dụ Java 17 với Maven và JUnit Jupiter

Ví dụ độc lập dưới đây tạo hai class và hai resource để quan sát đúng thư mục đích. Cần Maven 3.x và JDK 17+; phiên bản plugin được chỉ định để tránh sự khác biệt của plugin mặc định.

### 6.1. Tệp pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>maven-output-demo</artifactId>
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
            <version>5.10.2</version>
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
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**maven.compiler.release=17** yêu cầu API và bytecode phù hợp Java 17. **junit-jupiter** chỉ dùng cho test; Surefire **3.2.5** hỗ trợ chạy test bằng JUnit Platform.

### 6.2. Tệp src/main/java/vn/example/build/Greeting.java

~~~java
package vn.example.build;

public final class Greeting {
    private Greeting() {
    }

    public static String greet(String name) {
        return "Xin chào, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println(greet("Maven"));
    }
}
~~~

### 6.3. Tệp src/test/java/vn/example/build/GreetingTest.java

~~~java
package vn.example.build;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void greetsUser() {
        assertEquals("Xin chào, Maven!", Greeting.greet("Maven"));
    }
}
~~~

### 6.4. Resource đầu vào

Tệp **src/main/resources/app.properties**:

~~~properties
app.name=Maven Output Demo
~~~

Tệp **src/test/resources/fixture.txt**:

~~~text
only-for-tests
~~~

Những resource trên phục vụ việc quan sát thư mục đầu ra; ví dụ Java không bắt buộc phải đọc chúng để chạy thành công.

### 6.5. Thực hiện và đối chiếu

Chạy trong thư mục gốc có POM:

~~~bash
mvn -B clean compile
~~~

Sau đó thường có hai tệp:

~~~text
target/classes/vn/example/build/Greeting.class
target/classes/app.properties
~~~

Tiếp tục:

~~~bash
mvn -B test
~~~

Khi test đã biên dịch và Surefire chạy thành công, thường có thêm:

~~~text
target/test-classes/vn/example/build/GreetingTest.class
target/test-classes/fixture.txt
target/surefire-reports/TEST-vn.example.build.GreetingTest.xml
~~~

Tên **GreetingTest** khớp mẫu nhận diện test phổ biến của Surefire. Test xác nhận **greet("Maven")** trả về chuỗi dự kiến. Không nên giả định log của Maven giống từng ký tự trên mọi máy vì plugin, đường dẫn, bộ nhớ đệm và thời gian có thể khác nhau.

Để chạy chương trình trực tiếp từ **target/classes**:

~~~bash
java -cp target/classes vn.example.build.Greeting
~~~

**Đầu ra chuẩn của riêng lệnh Java này**:

~~~text
Xin chào, Maven!
~~~

Tiếp tục đóng gói JAR:

~~~bash
mvn -B package
jar tf target/maven-output-demo-1.0.0.jar
~~~

**jar tf** liệt kê các mục trong JAR. Thường sẽ thấy **vn/example/build/Greeting.class** và **app.properties**. JAR chính **không chứa GreetingTest.class và fixture.txt** theo mặc định. Nội dung đầy đủ còn có metadata như **META-INF/**.

JAR ví dụ **không có Main-Class** trong manifest, vì vậy đừng tự giả định chạy được bằng **java -jar**. Nếu muốn chạy chương trình từ JAR thường, sử dụng:

~~~bash
java -cp target/maven-output-demo-1.0.0.jar vn.example.build.Greeting
~~~

Lệnh này cũng in **Xin chào, Maven!** nếu build và đường dẫn đúng.

## 7. Những đầu ra trung gian khác có thể gặp

Không phải thư mục con nào của **target/** cũng thuộc Maven core. Nhiều thứ chỉ xuất hiện khi plugin tương ứng chạy:

| Đường dẫn | Công cụ và thời điểm thường tạo | Mục đích |
| --- | --- | --- |
| **target/generated-sources/annotations/** | Annotation processor trong pha compile | Java source được sinh tự động, có thể vắng mặt/rỗng. |
| **target/generated-test-sources/test-annotations/** | Annotation processing trong test-compile | Java source được sinh cho test. |
| **target/maven-status/maven-compiler-plugin/** | Một số phiên bản Maven Compiler Plugin | Metadata trạng thái biên dịch; cấu trúc tùy phiên bản. |
| **target/surefire-reports/** | Maven Surefire Plugin ở pha test | Báo cáo text/XML của unit test. |
| **target/failsafe-reports/** | Maven Failsafe Plugin khi được cấu hình | Báo cáo integration test. |
| **target/maven-archiver/** | Plugin đóng gói dùng Maven Archiver | Metadata hỗ trợ tạo archive. |
| **target/site/** | Maven Site Plugin/lifecycle site | Trang tài liệu/báo cáo được sinh khi có cấu hình phù hợp. |
| **target/dependency/** | Goal như dependency:copy-dependencies | Các dependency được sao chép vào build output; không mặc định tồn tại. |
| **target/jacoco.exec**, **target/site/jacoco/** | JaCoCo nếu cấu hình và thực thi | Dữ liệu và báo cáo code coverage. |
| **target/*.jar**, **target/*.war** | Plugin/package tương ứng | Artifact cuối cùng hoặc phụ, phụ thuộc packaging. |

**Generated sources** là mã nguồn **.java** do tool sinh; **compiled classes** là bytecode **.class** do compiler tạo. Khi annotation processing được bật và có processor thích hợp, mã nguồn sinh ra có thể được đưa vào vòng biên dịch. Không sửa nội dung dưới **target/generated-sources** như thể đó là mã nguồn chính, vì lần build sau có thể tạo lại và ghi đè.

**maven-status** là chi tiết triển khai của plugin, không phải API ổn định để ứng dụng đọc. Không viết logic ứng dụng phụ thuộc trực tiếp vào file metadata nội bộ này.

**surefire-reports** giúp CI và người phát triển kiểm tra test. Một bài test thất bại vẫn có thể tạo báo cáo hữu ích; chỉ thấy một báo cáo cũ không đủ chứng minh test vừa được chạy. Kiểm tra mã thoát, log và báo cáo của đúng lần build.

**failsafe-reports** và **surefire-reports** khác nhau: Surefire thường chạy unit test ở pha test; Failsafe thường được bind vào các pha integration-test/verify khi dự án cấu hình. Không suy luận rằng Failsafe tự chạy vì thư mục **src/test/java** tồn tại.

## 8. target/ khác local Maven repository

**target/** là kết quả build của **mỗi module**. Nó không phải kho cache dependency. Maven thường sử dụng:

- **target/**: class, resource, report và artifact của module hiện tại;
- **~/.m2/repository/**: repository cục bộ chứa dependency, plugin và artifact được tải/cài đặt;
- **.mvn/** trong repository dự án: cấu hình Maven hoặc tệp Maven Wrapper (nếu có);
- **~/.m2/wrapper/dists/**: nơi Maven Wrapper thường cache bản phân phối Maven, nếu dùng Wrapper.

Chạy **mvn clean** sẽ dọn thư mục build do Clean Plugin quản lý, mặc định là **target/**, **không xóa toàn bộ dependency trong ~/.m2/repository/**. Vì thế build sau clean vẫn có thể tái sử dụng thư viện đã cache.

Trong **multi-module project**, mỗi module Java thường có **target/** riêng. POM gốc có packaging **pom** có thể không chứa **target/classes** vì không biên dịch mã Java; hãy nhìn đúng module chứa source thay vì chỉ tìm ở thư mục gốc.

## 9. Build gia tăng, clean build và các tùy chọn bỏ qua test

Các lệnh **mvn compile** và **mvn test** không mặc nhiên xóa sạch đầu ra trước mỗi lần chạy. Plugin có thể tận dụng kết quả biên dịch trước đó, nhưng hành vi phụ thuộc phiên bản, cấu hình và dữ liệu nguồn.

Nếu vừa xóa hoặc đổi tên class mà vẫn thấy file **.class** cũ, hoặc local cho kết quả khác CI, hãy thử build sạch:

~~~bash
mvn clean test
~~~

Hoặc kiểm tra cả đóng gói/những goal gắn tới verify:

~~~bash
mvn clean verify
~~~

**clean** giúp loại bỏ khả năng một số file build cũ gây nhiễu; không nhất thiết phải clean ở mọi lượt phát triển nếu incremental build phù hợp.

Cần phân biệt hai cách bỏ qua test:

- **-DskipTests**: Surefire thường bỏ qua **thực thi** test, trong khi pha **test-compile** vẫn có thể biên dịch test.
- **-Dmaven.test.skip=true**: Compiler và Surefire Plugin có hỗ trợ bỏ qua cả **biên dịch và chạy test** khi giá trị này được bật.

Do đó, có **target/test-classes** không chứng minh bài test đã chạy; và không có báo cáo test mới có thể do test bị skip. Khi kiểm tra CI cần xem cả lệnh thực tế, cấu hình plugin và log.

## 10. Có nên đổi đường dẫn mặc định không?

Maven cho phép cấu hình **build.directory**, **outputDirectory**, **testOutputDirectory** trong POM. Ví dụ đoạn cấu hình minh họa đặt trong phần **project**:

~~~xml
<build>
    <directory>custom-build</directory>
    <outputDirectory>custom-build/classes</outputDirectory>
    <testOutputDirectory>custom-build/test-classes</testOutputDirectory>
</build>
~~~

Đây là **đoạn POM minh họa, không phải pom.xml hoàn chỉnh**. Với cấu hình đó, các output chính/test chuyển sang **custom-build**. Những plugin có đường dẫn mặc định dựa trên build directory cũng có thể thay đổi; plugin có path cấu hình riêng phải kiểm tra độc lập.

Chỉ đổi layout khi có nhu cầu thực sự, chẳng hạn tương thích một pipeline/IDE cũ. Việc đổi mặc định ảnh hưởng lệnh CI, Dockerfile, tài liệu, báo cáo, script kiểm thử và công cụ phân tích. Với dự án mới, giữ **target/classes** và **target/test-classes** giúp đồng đội và công cụ đoán đúng cấu trúc.

Không cần sửa tay file trong **target/** để “cấu hình” project; hãy sửa POM, nguồn chính, nguồn test hoặc cấu hình plugin tạo ra file đó.

## 11. Chẩn đoán các tình huống thường gặp

**Chạy mvn validate nhưng không thấy target/classes.** Pha validate chưa yêu cầu biên dịch. Chạy **mvn compile**, kiểm tra packaging và module chứa mã nguồn.

**Đã chạy mvn compile nhưng không thấy target/test-classes.** Pha compile chưa tới **test-compile**. Chạy **mvn test-compile** hoặc **mvn test**, xác nhận có nguồn test.

**Có file .class nhưng Java báo ClassNotFoundException.** Kiểm tra package, thư mục classpath gốc và tên lớp đầy đủ. Với **vn.example.build.Greeting**, dùng **java -cp target/classes vn.example.build.Greeting**; không truyền đường dẫn file **Greeting.class** làm tên lớp.

**Resource nằm trong src/main/resources nhưng chương trình không đọc được.** Xác minh **process-resources** đã chạy, file xuất hiện trong **target/classes** hoặc JAR và code tải theo resource path/classpath. Tránh dùng đường dẫn tương đối đến thư mục source khi triển khai.

**Test tìm được thư viện nhưng khi chạy JAR lại thiếu class.** Dependency **scope=test** chỉ có ở classpath test, không tự được đưa vào runtime. Nếu logic sản phẩm thực sự cần dependency, hãy khai báo đúng scope và chiến lược phân phối dependency.

**JAR không chứa lớp Test.** Đó là mặc định mong muốn. Nếu cần test fixture cho module khác, hãy nghiên cứu artifact test phụ thay vì trộn mã test vào JAR chính.

**Đầu ra trong target có dữ liệu cũ.** Lệnh không có clean có thể giữ lại một số file sinh từ lượt trước. Chạy **mvn clean test** và kiểm tra đầu ra của lượt chạy mới.

**Báo cáo surefire-reports không có hoặc đã cũ.** Xác minh plugin nhận diện được test, test không bị bỏ qua và pha test thực sự chạy. Đừng chỉ dựa vào sự tồn tại của thư mục báo cáo.

**Thư mục target vô tình được đưa lên Git.** Với dự án thông thường, thêm vào **.gitignore**:

~~~gitignore
target/
~~~

Nếu file đã được Git theo dõi, thay đổi **.gitignore** đơn thuần không loại nó khỏi index; cần thao tác Git riêng có chủ đích. Không mặc định commit bytecode, JAR hoặc báo cáo build nếu nhóm không có yêu cầu đặc biệt.

**Cấu hình thực tế không giống đường dẫn mặc định.** Kiểm tra parent POM, profile và effective POM:

~~~bash
mvn help:effective-pom
mvn -X test
~~~

**-X** xuất log debug; có thể dài và chứa thông tin môi trường, nên xem xét trước khi chia sẻ. Khi kiểm tra một mục tiêu, luôn phân biệt **đường dẫn mặc định theo Maven** với **đường dẫn hiệu lực của POM đang chạy**.

## 12. Điều nên nhớ

**src/main** và **src/test** là đầu vào do nhóm quản lý; **target/classes** và **target/test-classes** là đầu ra biên dịch của hai luồng tương ứng. Những đầu ra khác trong **target/** chỉ xuất hiện khi plugin/pha liên quan tạo chúng. Với packaging JAR, **target/classes** thường là nguồn cho artifact chính, còn **target/test-classes** phục vụ kiểm thử và không tự được đưa vào artifact phát hành.

Khi cần xác minh, đi theo đúng trình tự **compile → test-compile → test → package**, đối chiếu thư mục đầu ra và chạy **mvn clean verify** nếu cần loại trừ file build cũ. Điều này giúp đọc cấu trúc dự án Maven một cách có căn cứ và tránh sửa nhầm những file có thể được sinh lại.

### Tài liệu tham khảo chính thức

- [Apache Maven — Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Compiler Plugin — compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Maven Compiler Plugin — testCompile](https://maven.apache.org/plugins/maven-compiler-plugin/testCompile-mojo.html)
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
