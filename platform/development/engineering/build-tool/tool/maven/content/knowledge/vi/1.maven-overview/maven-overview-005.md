# Phân biệt mã nguồn, đầu ra biên dịch và artifact bàn giao trong Maven

## 1. Ba khái niệm nằm ở ba giai đoạn khác nhau

Khi xây dựng một dự án Java bằng Maven, cần phân biệt **thứ được viết và quản lý**, **thứ công cụ sinh ra trong quá trình build** và **thứ được đóng gói để chuyển cho nơi sử dụng**. Chúng liên quan với nhau nhưng có mục đích, vòng đời và quy tắc quản lý khác nhau.

| Khái niệm | Bản chất | Vị trí thường gặp | Ai sử dụng? | Có nên đưa vào Git? |
| --- | --- | --- | --- | --- |
| **Mã nguồn (source)** | Mã Java, tài nguyên, kiểm thử và cấu hình build do nhóm phát triển quản lý | **src/main/java**, **src/main/resources**, **src/test/java**, **pom.xml** | Lập trình viên, compiler, plugin Maven | Thường **có**, trừ bí mật và dữ liệu sinh tự động |
| **Đầu ra biên dịch (compiled/build output)** | Bytecode **.class**, tài nguyên đã sao chép và các sản phẩm trung gian trong quá trình build | **target/classes**, **target/test-classes**, các thư mục dưới **target/** | JVM trong lúc thử nghiệm, trình đóng gói, công cụ kiểm thử | Thường **không**; có thể tạo lại |
| **Artifact bàn giao (deliverable artifact)** | Đơn vị đã đóng gói, có tên/phiên bản, dùng để phân phối, triển khai hoặc làm dependency | Ví dụ **target/hello-maven-1.0.0.jar**, **target/app.war** | Ứng dụng khác, kho artifact, hệ thống CI/CD, môi trường triển khai | Thường đưa vào **artifact repository/release**, không commit file nhị phân vào Git |

Luồng điển hình:

~~~text
Mã nguồn + pom.xml + dependencies + JDK
    |  Maven xử lý tài nguyên và biên dịch
    v
target/classes/ (bytecode .class + resources)
    |  Maven kiểm thử, chạy các plugin và đóng gói
    v
target/<artifactId>-<version>.jar (hoặc WAR, loại gói khác)
    |  Phát hành/công bố artifact
    v
Kho artifact hoặc môi trường sử dụng
~~~

**Điểm mấu chốt:** Một file **.class** đã được biên dịch chưa đương nhiên là artifact phát hành; một file **.jar** đã được đóng gói cũng chưa đương nhiên chạy được bằng lệnh **java -jar**.

## 2. Mã nguồn: dữ liệu đầu vào có thể sửa và quản lý phiên bản

Với layout Maven tiêu chuẩn:

- **src/main/java/**: mã Java sản phẩm. Ví dụ **com/example/hello/App.java**.
- **src/main/resources/**: tài nguyên cần đưa vào classpath khi chạy, chẳng hạn **app.properties** hoặc template.
- **src/test/java/** và **src/test/resources/**: mã và tài nguyên dành cho kiểm thử; thông thường không đóng gói vào JAR chính.
- **pom.xml**: mô tả Maven project: tọa độ, dependencies, plugins, cấu hình build và packaging. Đây là **cấu hình nguồn của quy trình build**, không phải bytecode.
- Có thể có các file quản lý khác như **README.md**, **.gitignore**, cấu hình CI, và Maven Wrapper (**mvnw**, **mvnw.cmd**, **.mvn/**).

Mã nguồn Java là văn bản để compiler hiểu; JVM bình thường chạy bytecode tạo từ Java, không chạy trực tiếp từng file nguồn nằm trong thư mục của dự án như một artifact Maven. Java 11+ có chế độ chạy trực tiếp một file nguồn, nhưng đó là khả năng riêng của launcher Java và không biến file ấy thành JAR bàn giao.

Việc thay đổi **pom.xml** hoặc dependency cũng có thể làm thay đổi kết quả build dù không sửa **.java**. Do đó, muốn tái tạo bản build, chỉ lưu các file Java là chưa đủ.

## 3. Đầu ra biên dịch: những gì Maven tạo trong target/

Với **packaging=jar**, các bước chính thường là:

1. **process-resources** sao chép/xử lý tài nguyên sản phẩm sang **target/classes/**.
2. **compile** biên dịch Java trong **src/main/java/** thành file **.class** trong **target/classes/**.
3. **test-compile** biên dịch mã kiểm thử sang **target/test-classes/**; các kiểm thử chạy ở pha **test**.
4. **package** sử dụng các kết quả cần thiết để tạo JAR chính trong **target/**.

Ví dụ file nguồn **src/main/java/com/example/hello/App.java** thường trở thành **target/classes/com/example/hello/App.class**. Tên class và cấu trúc package được giữ dưới dạng đường dẫn tương ứng. Tài nguyên **src/main/resources/app.properties** thường được sao chép thành **target/classes/app.properties**; bản thân file tài nguyên không phải bytecode Java.

Không phải mọi file dưới **target/** đều là artifact để chuyển giao:

| Đường dẫn sau build | Mục đích |
| --- | --- |
| **target/classes/** | Các class sản phẩm và resource được chuẩn bị cho classpath |
| **target/test-classes/** | Class/resource dùng cho kiểm thử, khi có kiểm thử |
| **target/surefire-reports/** | Báo cáo kiểm thử do Surefire tạo, khi plugin chạy kiểm thử |
| **target/maven-status/** | Thông tin nội bộ của một số plugin |
| **target/*.jar** hoặc **target/*.war** | Ứng viên artifact được đóng gói theo loại dự án/plugin |

Các thư mục này phụ thuộc lệnh đã chạy và plugin thực tế; không nên mặc định tất cả đều xuất hiện sau mọi lần build. Ví dụ **mvn compile** chưa phải là yêu cầu đóng gói JAR mới.

Thư mục **target/** thường được liệt kê trong **.gitignore**. Lệnh **mvn clean** xóa đầu ra build mặc định trong **target/** để build lại từ nguồn; nó không xóa **src/**, **pom.xml** hay bộ nhớ đệm dependency trong **~/.m2/repository/**.

## 4. Artifact bàn giao: sản phẩm đã đóng gói có danh tính rõ ràng

Trong Maven, artifact thường được xác định bằng các tọa độ:

- **groupId**: nhóm/tổ chức, ví dụ **com.example**.
- **artifactId**: tên thành phần, ví dụ **hello-maven**.
- **version**: phiên bản, ví dụ **1.0.0**.
- **packaging/type**: cách đóng gói, phổ biến là **jar**, **war** hoặc **pom**.
- **classifier** (nếu có): phân biệt biến thể như **sources** hoặc **javadoc**.

Với **groupId=com.example**, **artifactId=hello-maven**, **version=1.0.0** và **packaging=jar**, tên đầu ra mặc định thường là **hello-maven-1.0.0.jar**. Tên file có thể được đổi bằng cấu hình build, nên tọa độ Maven và tên file vật lý là hai thông tin liên quan nhưng không đồng nhất hoàn toàn.

JAR là file ZIP có cấu trúc chuẩn; thông thường nó chứa các **.class**, tài nguyên và metadata như **META-INF/**. Sau khi đóng gói, một nhóm có thể bàn giao JAR cho nhóm khác, tải vào kho Maven hoặc đưa vào pipeline triển khai. **Không cần bàn giao toàn bộ thư mục target/classes** nếu giao diện phân phối yêu cầu một JAR chuẩn.

Tuy nhiên, **JAR mặc định của dự án Maven Java thường là thin JAR**: chứa mã/tài nguyên của chính dự án nhưng **không tự nhúng mọi dependency bên ngoài**. Bên nhận dùng nó như thư viện thường cần để Maven/Gradle phân giải thêm dependencies từ metadata POM. Nếu cần ứng dụng chạy độc lập, phải thiết kế cách cung cấp dependency và điểm khởi chạy phù hợp, chẳng hạn cấu hình manifest, classpath, plugin tạo executable/uber JAR hoặc gói triển khai khác. Không suy ra “JAR = ứng dụng tự chạy” chỉ từ phần mở rộng.

## 5. Ví dụ hoàn chỉnh với Java 17 và Maven

Giả sử muốn bàn giao ứng dụng nhỏ có package **com.example.hello**. Cấu trúc tệp do người phát triển tạo:

~~~text
hello-maven/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/hello/App.java
        └── resources/
            └── app.properties
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello-maven</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

**src/main/java/com/example/hello/App.java**:

~~~java
package com.example.hello;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();
        try (InputStream input = App.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IOException("Missing app.properties");
            }
            properties.load(input);
        }

        String name = properties.getProperty("name", "world");
        System.out.println("Hello, " + name + "!");
    }
}
~~~

**src/main/resources/app.properties**:

~~~properties
name=Maven
~~~

Yêu cầu môi trường: JDK 17+ phù hợp với cấu hình **release 17**, Maven 3.9+ (hoặc Maven Wrapper tương ứng), chạy các lệnh từ thư mục chứa **pom.xml**. Kiểm tra trước bằng:

~~~bash
java -version
mvn -version
~~~

**Bước A – biên dịch nhưng chưa đóng gói:**

~~~bash
mvn clean compile
java -cp target/classes com.example.hello.App
~~~

Kết quả chuẩn của lệnh **java**:

~~~text
Hello, Maven!
~~~

Ở thời điểm này, **target/classes/com/example/hello/App.class** là bytecode đã được biên dịch và **target/classes/app.properties** là resource đã sao chép. Sau **clean compile**, chưa có lý do để kỳ vọng JAR của lần build này đã được tạo.

**Bước B – đóng gói:**

~~~bash
mvn clean package
jar tf target/hello-maven-1.0.0.jar
java -cp target/hello-maven-1.0.0.jar com.example.hello.App
~~~

Lệnh **jar tf** liệt kê thành phần bên trong archive; trong số đó phải có **com/example/hello/App.class** và **app.properties**. Danh sách còn có thể chứa metadata tùy plugin. Kết quả chuẩn của lệnh **java** cuối cùng là:

~~~text
Hello, Maven!
~~~

Ở đây, **target/hello-maven-1.0.0.jar** là artifact JAR bàn giao; file **.java** vẫn nằm trong **src/main/java/**, còn **.class** được sao chép vào JAR từ đầu ra biên dịch. Lệnh **java -cp ... com.example.hello.App** gọi class có phương thức **main** trên classpath và chạy được ví dụ này vì không có thư viện ngoài.

**Không dùng ngay** lệnh **java -jar target/hello-maven-1.0.0.jar** cho ví dụ trên: POM chưa cấu hình thuộc tính **Main-Class** trong manifest, nên JVM không biết class khởi động. Nếu yêu cầu bàn giao một JAR chạy bằng **java -jar**, có thể bổ sung vào plugin **maven-jar-plugin**:

~~~xml
<configuration>
    <archive>
        <manifest>
            <mainClass>com.example.hello.App</mainClass>
        </manifest>
    </archive>
</configuration>
~~~

Đặt đoạn **configuration** làm phần tử con của plugin **maven-jar-plugin**, build lại bằng **mvn clean package**; khi đó JAR có entry point và lệnh sau chạy được với ứng dụng không có dependency bên ngoài:

~~~bash
java -jar target/hello-maven-1.0.0.jar
~~~

Kết quả:

~~~text
Hello, Maven!
~~~

Việc thêm **Main-Class** không tự nhúng dependencies. Với ứng dụng có thư viện ngoài, cần giải quyết classpath hoặc phương án đóng gói riêng.

## 6. Phân biệt các lệnh Maven theo đầu ra

Maven có build lifecycle với các pha nối tiếp. Khi gọi một pha, Maven thực hiện các pha cần thiết đứng trước trong cùng lifecycle.

| Lệnh | Kết quả cần quan tâm | Điều lệnh **không** bảo đảm |
| --- | --- | --- |
| **mvn clean** | Dọn đầu ra build mặc định | Không biên dịch/đóng gói lại |
| **mvn compile** | Tạo class và resources sản phẩm trong **target/classes/** | Không yêu cầu tạo JAR |
| **mvn test** | Biên dịch phần cần thiết và chạy kiểm thử ở pha **test** | Không yêu cầu tạo artifact đóng gói |
| **mvn package** | Thực hiện các pha cần thiết rồi đóng gói artifact theo **packaging** | Không tự công bố lên kho từ xa |
| **mvn install** | Đóng gói và cài artifact/POM vào Maven repository cục bộ | Không phải thao tác phát hành từ xa |
| **mvn deploy** | Thực hiện lifecycle đến pha deploy, công bố artifact lên remote repository đã cấu hình | Không phải chỉ copy file sang một thư mục tùy ý |

**clean** thuộc lifecycle riêng. Vì vậy, **mvn clean package** thường hữu ích khi muốn tránh sử dụng nhầm kết quả build cũ. Pha **package** thường chạy test theo lifecycle mặc định; nếu test fail, bản build thường dừng trước khi có artifact hợp lệ. Không nên phát hành một JAR còn sót từ lượt build trước chỉ vì nó đang tồn tại dưới **target/**.

Ví dụ sau **mvn install**, artifact **com.example:hello-maven:1.0.0** thường có file trong kho cục bộ:

~~~text
~/.m2/repository/com/example/hello-maven/1.0.0/
    hello-maven-1.0.0.jar
    hello-maven-1.0.0.pom
~~~

Đây là bản được **cài cho máy phát triển hoặc quá trình build cục bộ tham chiếu**, chưa đồng nghĩa với việc bên ngoài có thể tải nó. Muốn chia sẻ giữa máy hoặc CI, thường dùng remote artifact repository và quy trình **deploy** có cấu hình/ủy quyền phù hợp.

## 7. Chọn đúng thứ để bàn giao theo tình huống

| Nhu cầu | Nên bàn giao/quản lý | Vì sao |
| --- | --- | --- |
| Đồng đội cần tiếp tục phát triển, review, sửa lỗi | Repository mã nguồn, POM, wrapper và hướng dẫn build | Họ cần đầu vào để sửa và tái tạo kết quả |
| Một module Java được dùng làm dependency | Artifact JAR + POM/metadata và dependency trong kho Maven | Công cụ build của bên nhận phân giải tọa độ và phụ thuộc |
| Kiểm thử nhanh class vừa biên dịch trên máy | **target/classes/** trong classpath cục bộ | Tiện thử nghiệm, chưa phải bản phát hành chuẩn |
| Triển khai ứng dụng dịch vụ | Gói chạy được đã kiểm chứng, cấu hình, dependencies/runtime cần thiết | Đảm bảo ứng dụng thực sự khởi động trong môi trường đích |
| Phát hành web application truyền thống | Có thể là WAR tùy kiến trúc và container | **packaging** quyết định loại gói |
| Phục vụ phân tích, gỡ lỗi bản build | Artifact theo phiên bản, checksum, test report, log build, commit nguồn liên quan | Có thể truy vết từ bản bàn giao tới nguồn và quá trình tạo |

Với library, người dùng thường chỉ cần khai báo dependency Maven bằng tọa độ thay vì chép JAR trực tiếp. Với ứng dụng chạy độc lập, định nghĩa artifact bàn giao cần bao gồm điều kiện chạy (Java version, thư viện ngoài, cách start) chứ không chỉ tên file.

## 8. Kiểm tra trước khi gọi một tệp là “artifact bàn giao”

1. **Nguồn rõ ràng:** xác định commit/tag và các phiên bản dependency/plugin đã dùng; không build từ file chỉnh tay ngoài repository mà không ghi nhận.
2. **Build thành công:** chạy lệnh phù hợp, thường **mvn clean verify** hoặc pipeline có kiểm thử/kiểm tra chất lượng; đảm bảo exit code thành công.
3. **Đúng loại đóng gói:** kiểm tra **pom.xml** và file thực tế (**jar**, **war**, v.v.); dự án **packaging=pom** không tạo JAR sản phẩm chỉ vì có **pom.xml**.
4. **Đúng tên/phiên bản:** kiểm tra **groupId**, **artifactId**, **version**, classifier nếu có; tránh bàn giao nhầm **SNAPSHOT** hoặc file từ build cũ.
5. **Đúng thành phần:** dùng **jar tf path/to/file.jar** (hoặc công cụ phù hợp) để xác nhận class/resource cần thiết có trong gói. Tránh đưa source bí mật, khóa truy cập hay cấu hình nhạy cảm vào resources.
6. **Chạy/tiêu thụ được:** thử đúng cách bên nhận sẽ dùng; **java -jar** chỉ phù hợp khi JAR có entry point và dependency được cung cấp đầy đủ.
7. **Phân phối truy vết được:** công bố trong artifact repository hoặc release có phiên bản, đường dẫn, checksum và lịch sử CI; không coi **target/** trên laptop là kho phát hành.
8. **Không nhầm test output với sản phẩm:** **target/test-classes/** và báo cáo test là đầu ra kiểm thử; JAR chính thông thường không đóng gói test classes.

## 9. Các nhầm lẫn thường gặp và cách tự kiểm chứng

**“Có file .class là đã có JAR để giao.”** Sai: **.class** là đầu ra compiler; JAR phải được tạo bởi pha đóng gói/plugin tương ứng. Hãy chạy **mvn clean package** rồi kiểm tra file artifact thực tế.

**“Đã có JAR thì luôn chạy được bằng java -jar.”** Sai: cần manifest entry point và dependencies có mặt lúc chạy. Kiểm tra nội dung JAR, manifest và thử lệnh khởi động đúng với kiểu gói.

**“Thư mục target chứa toàn bộ thứ phải commit.”** Sai trong dự án Maven thông thường: **target/** chứa kết quả có thể tái tạo và sản phẩm tạm, thường bị Git ignore. Cam kết lưu mã nguồn, POM, wrapper và cấu hình build cần thiết.

**“mvn install là đã upload artifact cho nhóm khác.”** Sai: **install** đưa artifact vào kho Maven **trên máy hiện tại**. Phân phối qua máy khác cần kho dùng chung, release hoặc cơ chế chuyển giao đã thống nhất.

**“JAR không thấy thư viện ngoài thì Maven đóng gói sai.”** Chưa chắc: JAR mặc định không nhúng transititive dependencies. Kiểm tra loại artifact cần dùng và cấu hình đóng gói.

**“Sửa .java xong có thể lấy ngay JAR cũ dưới target.”** Không an toàn: file cũ có thể chưa phản ánh nguồn mới. Xóa đầu ra cũ, build lại, kiểm tra timestamp/phiên bản và thử nghiệm artifact.

Ba câu hỏi kiểm tra nhanh: **Tôi đang sửa cái gì?** → nguồn; **compiler vừa tạo cái gì?** → class/resources; **người nhận sẽ tải và sử dụng cái gì?** → artifact đã đóng gói và xác thực. Khi tách rõ ba lớp này, việc debug Maven, quản lý Git, thiết lập CI/CD và phát hành Java sẽ chính xác hơn.