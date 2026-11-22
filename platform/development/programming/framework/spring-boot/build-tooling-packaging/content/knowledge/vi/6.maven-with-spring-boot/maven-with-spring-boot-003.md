# Sử dụng BOM khi dự án Spring Boot đã có Maven parent riêng

## 1. Bài toán thực tế và mục tiêu

Trong dự án Spring Boot đơn giản, Maven thường kế thừa `org.springframework.boot:spring-boot-starter-parent` để nhận một bộ mặc định: phiên bản thư viện, Java/compiler configuration, Maven plugin management, cơ chế đóng gói và một số quy tắc lọc resources. Nhưng hệ thống doanh nghiệp thường có **parent POM riêng** quy định JDK, plugin versions, repositories, quality gates hoặc conventions. Một project Maven chỉ có **một parent trực tiếp**. Vậy làm thế nào giữ `company-parent` mà vẫn nhận bộ phiên bản thư viện của Spring Boot?

Giải pháp là **import Spring Boot BOM** (`org.springframework.boot:spring-boot-dependencies`) vào `<dependencyManagement>` của dự án hoặc parent phù hợp, giữ nguyên `<parent>` đã chọn. BOM cung cấp **version management** cho dependencies; cấu hình plugin và build lifecycle cần được kiểm soát riêng.

Sau bài học, bạn có thể:

- Phân biệt `<parent>`, `<dependencyManagement>`, BOM import và `<dependencies>`.
- Biết khi nào đặt Spring Boot BOM vào project, module hoặc parent trung gian.
- Cấu hình POM đầy đủ khi đã có corporate parent và không dùng `spring-boot-starter-parent`.
- Hiểu vì sao import BOM không tự cấu hình Spring Boot Maven Plugin, Java compiler hay `repackage`.
- Kiểm tra effective POM, dependency tree và executable JAR.
- Giải quyết xung đột phiên bản giữa BOM, parent và dependency trực tiếp; tránh override sai.
- Nâng phiên bản Spring Boot BOM và Maven Plugin theo một thay đổi có thể kiểm chứng.

**Ví dụ dùng Spring Boot 3.5.16 và Java 17** để có phiên bản cụ thể, không khẳng định đây là version phù hợp cho mọi dự án. Khi áp dụng vào hệ thống thật, chọn release Boot, Java và Maven được tổ chức hỗ trợ, đồng thời xem tài liệu chính thức của dòng release đó.

## 2. Ba khái niệm phải tách biệt

### 2.1. Maven parent

Parent của một project được khai báo trong `<parent>`:

~~~xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
</parent>
~~~

Maven xây dựng **effective POM** bằng cách tổng hợp cấu hình từ Super POM, các parent kế thừa, profile đang bật và POM của module. Parent riêng có thể quản lý plugin versions, compiler, test, repositories, properties và dependency management.

Maven project **chỉ có một phần tử `<parent>`**; không thể đặt đồng thời `company-parent` và `spring-boot-starter-parent` làm hai parent trực tiếp.

### 2.2. Dependency management

`<dependencyManagement>` cung cấp phiên bản, scope hoặc những cấu hình được quản lý cho dependencies khi chúng được sử dụng. Nó **không tự thêm thư viện vào classpath**.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>sample-library</artifactId>
            <version>1.2.3</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây chỉ là đoạn POM minh họa. `sample-library` không tự được tải và đặt vào classpath chỉ vì có trong phần quản lý này. Muốn sử dụng nó, project vẫn cần khai báo dependency trong `<dependencies>`, hoặc nó phải xuất hiện qua một đường phụ thuộc bắc cầu.

### 2.3. BOM import

BOM (Bill of Materials) là **POM artifact** cung cấp một tập dependency management. Spring Boot phát hành `spring-boot-dependencies` để quản lý version của nhiều Spring modules, starters và thư viện bên thứ ba phù hợp với release Boot đó.

Dùng dependency với **`<type>pom</type>`** và **`<scope>import</scope>` trong **`<dependencyManagement>`** để đưa các managed dependencies từ BOM vào project:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`scope=import` chỉ có ý nghĩa cho dependency loại `pom` trong `dependencyManagement`; đây không phải `runtime`, `compile` hay `test`. Nó không biến BOM thành một thư viện runtime và không tự kích hoạt Spring Boot ứng dụng.

### 2.4. Hình dung luồng cấu hình

~~~text
                         boot-app/pom.xml
                                |
          <parent> com.example:company-parent:1.0.0
                                |
                      Maven POM inheritance
            compiler / surefire / company conventions
                                |
       <dependencyManagement> trong app hoặc parent
                                |
          import spring-boot-dependencies:3.5.16
                                |
             version management cho các thư viện
                                |
             <dependencies> của app thực sự dùng
             starter-web, starter-test, jdbc driver...
                                |
                  Maven resolve dependency graph
                                |
                    compile -> test -> package
~~~

Parent và BOM trả lời **hai câu hỏi khác nhau**: “Module kế thừa quy tắc build từ ai?” và “Tập phiên bản thư viện được quản lý theo đâu?”.

## 3. Cú pháp chuẩn khi dùng corporate parent

Giả sử child POM hiện có parent riêng:

~~~xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Trong **cùng project đó**, thêm BOM import:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo dependencies như thông thường:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Hai starters **không cần `<version>` riêng** vì Spring Boot BOM đã quản lý. Nhưng **BOM không tự tạo các `<dependency>` này**: nếu chỉ import BOM và không khai báo Web starter, project không tự có Spring MVC hay embedded server.

Maven cho phép đặt BOM version vào property của project:

~~~xml
<properties>
    <spring-boot.version>3.5.16</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`${spring-boot.version}` là **cú pháp property interpolation thông thường của Maven**. Đặt property này trong POM để chọn **version của BOM** là hợp lệ; nó khác với cố thay property nằm **bên trong BOM đã được import**, cần lưu ý ở mục 8.

## 4. Import BOM khác kế thừa spring-boot-starter-parent thế nào?

| Khả năng | Kế thừa `spring-boot-starter-parent` | Parent riêng + Spring Boot BOM import |
| --- | --- | --- |
| Parent trực tiếp | Boot starter parent | Parent của doanh nghiệp |
| Managed dependency versions từ Spring Boot | Có | Có |
| Khai báo starter không cần version | Có | Có, nếu được BOM quản lý |
| Maven plugin management của Boot parent | Có theo kế thừa | **Không import kèm** |
| Goal `spring-boot:repackage` được bind bởi starter parent | Có | **Phải tự cấu hình** khi muốn executable archive |
| Các compiler/JDK defaults của Boot parent | Có | Parent riêng hoặc module phải tự đảm bảo |
| Encoding, `-parameters`, resource filtering Boot parent | Có các cấu hình mặc định | Không tự nhận cùng cấu hình |
| Khả năng giữ corporate parent | Không làm parent trực tiếp đồng thời | Có |

Nếu không sử dụng Spring Boot parent, **dependency version management vẫn còn** nhờ BOM, nhưng việc đóng gói Spring Boot và phiên bản plugin cần được khai báo rõ ràng hoặc được corporate parent quản lý đúng.

Cũng không nên hiểu **BOM import** tương đương với câu lệnh “thêm tất cả Spring modules vào classpath”: `dependencyManagement` chỉ quản lý các dependency có thể được resolve sau này.

## 5. Ví dụ đầy đủ, có thể chạy: một parent riêng + ứng dụng Boot

Tạo dự án mẫu gồm parent POM và child module như sau:

~~~text
company-demo/
├── pom.xml
└── boot-app/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/bootapp/
        │   ├── BootAppApplication.java
        │   └── PingController.java
        └── test/java/com/example/bootapp/
            └── BootAppApplicationTests.java
~~~

**Điều kiện chạy:** JDK 17 hoặc JDK mới hơn tương thích, Maven 3.9+ phù hợp, truy cập Maven repository và không có dịch vụ khác chiếm cổng 8080. Ví dụ tự khai báo parent local nên **không cần tìm artifact company-parent ở repository nội bộ**.

### 5.1. Parent POM hoàn chỉnh: company-demo/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>boot-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                    <configuration>
                        <release>17</release>
                        <parameters>true</parameters>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.2.5</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Ý nghĩa:

- Parent có `<packaging>pom</packaging>` nên là module cấu hình/aggregate, không phải ứng dụng JAR.
- `<modules>` dùng để chỉ định các child được Maven reactor build; **không thay thế** việc child khai báo `<parent>`.
- `<pluginManagement>` giữ version/compiler defaults của Maven plugins. Các plugin gắn với lifecycle (như compiler, surefire của packaging JAR) sẽ dùng cấu hình được quản lý khi được thực thi. `pluginManagement` không bảo đảm mọi goal tùy ý sẽ tự chạy.
- Compiler dùng `<release>17</release>` và `<parameters>true</parameters>`. Chúng là ví dụ về những defaults mà corporate parent nên cân nhắc tự quản lý.
- Surefire 3.2.5 hỗ trợ chạy JUnit Jupiter trong module mẫu.

Trong tổ chức thật, **không sửa parent chung chỉ để phục vụ một module nếu bạn không sở hữu parent đó**; có thể đặt cấu hình cần thiết ở module hoặc parent trung gian theo quy định dự án.

### 5.2. Child POM hoàn chỉnh: company-demo/boot-app/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>company-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>boot-app</artifactId>
    <packaging>jar</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>3.5.16</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.5.16</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là cấu trúc quan trọng của bài:

1. Child **chỉ kế thừa `company-parent`**, không có Spring Boot starter parent thứ hai.
2. Child import **Boot BOM** để lấy versions của dependencies như `spring-boot-starter-web`.
3. Child tự thêm **`spring-boot-maven-plugin`**, pin version và bind goal `repackage` để `mvn package` sinh executable Spring Boot JAR.
4. Child kế thừa compiler và Surefire settings từ corporate parent của ví dụ.

`relativePath` trỏ về parent local `../pom.xml`. Nếu parent thực tế được phát hành trong repository và không nằm trong thư mục cha, dự án có thể dùng `<relativePath/>` để tránh Maven tìm parent sai tại đường dẫn mặc định; vẫn phải bảo đảm repository/credentials resolve được parent.

### 5.3. Java: lớp khởi động

Tạo tệp `boot-app/src/main/java/com/example/bootapp/BootAppApplication.java`:

~~~java
package com.example.bootapp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BootAppApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootAppApplication.class, args);
    }
}
~~~

Lớp này là source Java hợp lệ khi biên dịch trong project Maven có Boot dependencies. Nó không phải chương trình tự biên dịch bằng lệnh `javac BootAppApplication.java` độc lập vì các Spring imports cần classpath do Maven giải quyết.

### 5.4. Java: controller HTTP

Tạo `boot-app/src/main/java/com/example/bootapp/PingController.java`:

~~~java
package com.example.bootapp;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Controller nằm cùng package với ứng dụng nên được component scanning tìm thấy. Spring Web cung cấp các annotation và web runtime cần thiết. Với cổng mặc định 8080 và ứng dụng chạy ổn, HTTP GET `/ping` trả về response body chính xác là `pong`.

### 5.5. Java: kiểm thử khởi động context

Tạo `boot-app/src/test/java/com/example/bootapp/BootAppApplicationTests.java`:

~~~java
package com.example.bootapp;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class BootAppApplicationTests {

    @Test
    void contextLoads() {
        // Pass nếu Spring ApplicationContext có thể được khởi tạo.
    }
}
~~~

JUnit Jupiter và Spring Boot Test do `spring-boot-starter-test` cung cấp cho **test classpath**. Surefire sẽ chạy test ở phase `test`. Không cần mong đợi một stdout cố định từ JUnit; số lượng log và format thay đổi theo plugin/environment.

### 5.6. Lệnh chạy và output có thể kiểm tra

Mở terminal trong thư mục gốc `company-demo/`:

~~~bash
java -version
javac -version
mvn -version
mvn clean package
~~~

Khi build thành công, executable JAR dự kiến là `boot-app/target/boot-app-1.0.0.jar` theo artifact/version của ví dụ. Chạy:

~~~bash
java -jar boot-app/target/boot-app-1.0.0.jar
~~~

Từ terminal khác:

~~~bash
curl -s http://localhost:8080/ping
~~~

Kết quả **response body**, nếu ứng dụng chạy ở cổng mặc định:

~~~text
pong
~~~

Log Spring Boot và Maven có thể khác giữa các máy, vì vậy chỉ khẳng định body endpoint. Nếu port 8080 bị chiếm hoặc `server.port` được đổi, cần dùng port thực tế.

Lệnh build module theo reactor:

~~~bash
mvn -pl boot-app -am clean package
~~~

`-pl` chọn module `boot-app`; `-am` build các reactor projects cần thiết. Vì ví dụ được viết thủ công không có Maven Wrapper, dùng lệnh `mvn`. Nếu project thật đã có Wrapper, dùng `./mvnw` (Linux/macOS) hoặc `.\mvnw.cmd` (Windows PowerShell) với các đối số tương ứng.

## 6. Tại sao import BOM vẫn phải khai báo Maven Plugin?

BOM `spring-boot-dependencies` quản lý **dependencies**. Khi import dưới `<dependencyManagement>`, Maven **không import pluginManagement của Spring Boot parent** và không tự mang các execution được starter parent cung cấp.

Đặc biệt:

- `spring-boot-maven-plugin` là một **Maven build plugin**, không phải một dependency thông thường của app.
- Nếu corporate parent không quản lý version plugin này, project phải pin version trong `<build><plugins>` hoặc `<pluginManagement>` thích hợp.
- Nếu muốn executable JAR/WAR khi chạy `mvn package`, cần goal `repackage` được bind. Với Boot starter parent, execution này thường đã có sẵn; với parent riêng phải chủ động cấu hình hoặc kế thừa từ parent nội bộ có cấu hình tương đương.
- Các thiết lập Java compiler release, `-parameters`, resource filtering và plugin versions cũng phải được corporate parent hoặc module cung cấp; BOM không tự đặt chúng.
- Nếu project chỉ viết **thư viện Java** dùng Spring Boot dependencies mà không cần chạy Boot application, không nhất thiết phải thêm `spring-boot-maven-plugin`.

Một đoạn riêng để pin plugin và bind executable packaging:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.5.16</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Đây là đoạn POM, **không phải POM độc lập**. Nếu parent riêng đã quản lý plugin và execution, xem effective POM để tránh cấu hình trùng không cần thiết.

## 7. Phân biệt version do BOM quản lý với version thực sự được resolve

### 7.1. Kiểm tra effective POM

Maven Help Plugin có thể xuất effective POM sau inheritance/import/profile:

~~~bash
mvn -pl boot-app help:effective-pom
~~~

Khi đọc kết quả, tìm `dependencyManagement`, `spring-boot-starter-web`, `spring-boot-maven-plugin`, compiler, Surefire và `repackage`. Tập trung vào **module boot-app**, vì parent root có packaging `pom` và không phải nơi chạy Boot app.

Có thể ghi kết quả vào file (trong thực hành tự chạy; tên/đường dẫn tùy working directory/module):

~~~bash
mvn -pl boot-app help:effective-pom -Doutput=effective-pom.xml
~~~

Maven Help Plugin in đường dẫn file đã ghi; hãy theo thông báo thực tế để xác định vị trí. Việc thấy BOM trong source POM không chứng minh toàn bộ managed dependencies đã có hiệu lực; effective POM giúp kiểm tra cấu hình sau khi Maven kết hợp nguồn.

### 7.2. Kiểm tra dependency tree

~~~bash
mvn -pl boot-app dependency:tree
mvn -pl boot-app dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
~~~

Lệnh đầu hiển thị dependency graph của module; lệnh sau giới hạn theo tọa độ starter. Trên Windows PowerShell, đặt biểu thức `-Dincludes=...` trong dấu nháy kép nếu shell xử lý tham số khác dự kiến.

Ví dụ về **định dạng dòng kết quả**, không phải toàn bộ log cố định:

~~~text
[INFO] com.example:boot-app:jar:1.0.0
[INFO] \- org.springframework.boot:spring-boot-starter-web:jar:3.5.16:compile
~~~

Nếu thực tế xuất hiện version khác version BOM, kiểm tra parent inheritance, BOM khác, dependency management tường minh, dependency version trực tiếp và dependency mediation. Không sửa các version ngẫu nhiên chỉ để ép output khớp kỳ vọng.

### 7.3. Kiểm tra artifact executable

~~~bash
mvn -pl boot-app -am clean package
jar tf boot-app/target/boot-app-1.0.0.jar
~~~

Một executable Spring Boot JAR thường chứa `BOOT-INF/classes/` (mã ứng dụng) và `BOOT-INF/lib/` (thư viện), cùng Spring Boot loader. Nếu chỉ có JAR thông thường và `java -jar` không chạy, kiểm tra Spring Boot Maven Plugin và execution `repackage`. `mvn package` có thể thành công khi plugin Boot không được cấu hình nhưng artifact không có layout executable.

## 8. Override dependency version khi đang import BOM

### 8.1. Hiểu giới hạn của property override

Khi **kế thừa** `spring-boot-starter-parent`, một số phiên bản được điều khiển bằng properties có thể được project con override theo hướng dẫn Boot. Nhưng khi chỉ **import** `spring-boot-dependencies`, bạn **không thể trông đợi** việc đặt một property cùng tên với property nội bộ của BOM sẽ override tất cả managed version.

Ví dụ chỉ thêm:

~~~xml
<properties>
    <slf4j.version>2.0.17</slf4j.version>
</properties>
~~~

không phải cách đáng tin để override SLF4J version do BOM import quản lý. **Đừng kết luận version đã thay đổi nếu chưa kiểm tra effective POM và dependency tree.**

### 8.2. Override bằng mục dependencyManagement tường minh

Khi buộc phải dùng version đã được kiểm chứng khác với BOM, Spring Boot hướng dẫn đặt managed dependency **trước entry import BOM**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**Version SLF4J ở đây chỉ minh họa cú pháp**; tuyệt đối không coi việc ép version thành một khuyến nghị chung. Đổi thư viện thấp tầng có thể gây `NoSuchMethodError`/`ClassNotFoundException` hoặc xung đột với các module Spring. Cần kiểm tra tương thích, báo cáo bảo mật và test end-to-end.

Một phiên bản được khai báo trực tiếp ở `<dependencies>` cũng có thể override managed version cho dependency trực tiếp đó; tuy nhiên điều này có thể khiến graph thiếu đồng bộ khi nhiều thành phần phụ thuộc chung một thư viện. Với nhu cầu quản lý nhất quán các đường transitive, `dependencyManagement` rõ ràng hơn.

## 9. Parent có quản lý dependency, hoặc project import nhiều BOM

Doanh nghiệp có thể đã import một company BOM, một framework BOM hoặc Spring Cloud BOM. Những BOM này có thể cùng quản lý một tọa độ artifact.

### 9.1. Thứ tự import

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>company-dependencies</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi hai BOM cùng được import **ở cùng cấp POM** và quản lý trùng dependency, **BOM được import trước thường ưu tiên** với những tọa độ trùng, nếu POM hiện tại không có managed entry tường minh ghi đè. Maven chính thức có ví dụ: import BOM X rồi Y, cùng quản lý artifact A thì định nghĩa từ X được chọn.

Nhưng đừng suy ra rằng “BOM đứng trước luôn thắng trong mọi trường hợp”: cấu hình `dependencyManagement` kế thừa từ parent, khai báo trực tiếp tại child, explicit dependency version và các đường transitive cũng ảnh hưởng **effective** version. Dùng `help:effective-pom` cùng `dependency:tree` để kiểm chứng.

### 9.2. Đặt BOM ở parent hay từng module?

**Đặt ở parent chung:** hợp lý khi toàn bộ module kế thừa parent đều phải dùng cùng Spring Boot line và parent được nhóm sở hữu quản lý. Chỉ thay parent là có thể ảnh hưởng nhiều modules nên phải review phạm vi.

**Đặt ở từng module Boot:** hợp lý khi parent chung phục vụ cả ứng dụng Boot, thư viện Java và các service khác. Mỗi module Boot import BOM riêng, quản lý version mà không áp đặt nó lên module không dùng Boot.

**Parent trung gian:** nếu có nhiều module Boot, có thể tạo một parent cấp module kế thừa corporate parent và chứa Boot BOM/Boot plugin policies; các module tiếp tục kế thừa parent trung gian. Mỗi module vẫn chỉ có **một parent trực tiếp**, nhưng chuỗi kế thừa có thể nhiều tầng.

Nếu dùng Spring Cloud, phải chọn đúng release train tương thích Spring Boot và import Spring Cloud BOM theo hướng dẫn chính thức. **Không tự thêm Spring Cloud BOM** nếu project không dùng Spring Cloud.

## 10. Lưu ý quan trọng về Maven versions, resources và deployment

- **Java/JDK:** Spring Boot 3.5 yêu cầu tối thiểu Java 17. Parent riêng phải dùng compiler plugin/configuration phù hợp, và Maven cần chạy trên JDK tương thích. Ví dụ parent đặt release 17; CI có thể dùng JDK 17 hoặc JDK mới hơn tương thích.
- **Maven plugins:** BOM import không tự cập nhật Maven Compiler/Surefire/Resources/Jar/War Plugin. Kiểm tra `mvn -version` và POM hiệu dụng khi có lỗi build.
- **Resource filtering:** Spring Boot starter parent có quy tắc filtering cho `application.properties`/`application.yml`; parent công ty có thể dùng delimiter Maven khác. Nếu Spring placeholders dạng `${spring.datasource.url}` bị Maven thay hoặc làm hỏng khi package, kiểm tra filtering configuration thay vì đổ lỗi cho BOM.
- **Executable archive:** Spring Boot Maven Plugin `repackage` đóng gói layout executable. Khi có WAR triển khai external container, cần chọn đúng packaging và xử lý dependencies của container theo contract, không sao chép y nguyên cấu hình JAR từ ví dụ.
- **Không buộc plugin version bằng dependency BOM:** version của `spring-boot-maven-plugin` cần cấu hình ở `<build>`/parent pluginManagement. Dùng version cùng release Boot trong ví dụ để dễ kiểm soát.
- **Maven Wrapper:** nếu project đã có `mvnw` và `mvnw.cmd`, ưu tiên wrapper trong CI và máy phát triển. Wrapper chỉ giúp cố định Maven runtime; vẫn cần Java và nguồn repository phù hợp.

## 11. Lộ trình nâng cấp Spring Boot BOM an toàn

Khi đổi dòng Spring Boot trong dự án có parent riêng, cần kiểm tra cả **BOM**, **Boot Maven Plugin**, **JDK**, **compiler/test plugins**, và **các BOM có thể va chạm**.

1. Chọn release Spring Boot được hỗ trợ và phù hợp yêu cầu hệ thống.
2. Đọc system requirements của đúng release: Java, Maven, các breaking changes quan trọng.
3. Kiểm tra corporate parent: có khóa version Maven plugins hoặc Java release không; có `dependencyManagement` đang đè các thư viện Boot không.
4. Cập nhật `spring-boot-dependencies` BOM version trong module hoặc parent sở hữu BOM.
5. Cập nhật/kiểm tra `spring-boot-maven-plugin` version và execution `repackage`; không chỉ cập nhật BOM.
6. So sánh effective POM trước/sau, dùng `dependency:tree` để nhìn versions của starter và các dependencies quan trọng.
7. Chạy unit/integration tests, build executable archive, chạy bản đóng gói theo mô hình deploy thật.
8. Chỉ sau khi QA đạt mới cập nhật CI, metadata/version quản lý theo quy trình của nhóm.

Không nên đưa toàn bộ Spring Framework hoặc Jackson lên một version mới tùy ý để “theo kịp” Boot; Boot BOM được thiết kế để phối hợp nhiều artifact. Override chỉ nên thực hiện khi cần và đã kiểm chứng.

## 12. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Non-resolvable parent POM` | Parent riêng sai tọa độ/version, không nằm trong local/repository hoặc `relativePath` sai | Xác minh parent GAV, đường dẫn và repository credentials trước |
| Maven yêu cầu `<version>` cho `spring-boot-starter-web` | BOM chưa import, sai `type/scope` hoặc source POM chưa resolve | Kiểm tra `dependencyManagement`, `type=pom`, `scope=import` và effective POM |
| Spring Web không có trên compile classpath dù đã import BOM | BOM chỉ quản lý version, không tự thêm thư viện | Thêm starter/dependency thực sự vào `<dependencies>` |
| `mvn package` thành công nhưng `java -jar` không chạy | Thiếu Spring Boot Maven Plugin hoặc `repackage` | Pin plugin version và bind goal; kiểm tra `BOOT-INF` |
| Plugin version thay đổi ngoài ý muốn | Corporate parent/BOM không quản lý version plugin như tưởng | Xem `build/plugins` và `pluginManagement` trong effective POM |
| `invalid target release: 17` | JDK chạy Maven thấp hơn Java release của compiler | Kiểm tra `mvn -version` và `JAVA_HOME` |
| JUnit Jupiter test không chạy | Surefire/plugin configuration quá cũ hoặc sai provider | Kiểm tra Surefire 3.x và test classpath |
| Đặt `<slf4j.version>` nhưng version không đổi | Import BOM không cho override nội bộ bằng properties giống inheritance | Khai báo dependency management tường minh, readback effective POM |
| Version của Jackson/Spring khác BOM mong muốn | Parent BOM, khai báo trực tiếp hoặc management khác có ưu tiên | Xem effective POM, dependency tree và thứ tự import |
| App chạy local nhưng lỗi `NoSuchMethodError` khi deploy | Dependencies bị override không tương thích hoặc artifacts bị trộn versions | Soát dependency tree, BOM versions, package thực tế và CI |
| Spring properties bị lọc sai lúc package | Corporate parent resource filtering thay khác Boot parent | Kiểm tra Maven Resources Plugin và delimiter, không thay config bí mật trong lúc debug |
| Không tải được BOM | Repository/proxy/credentials hoặc version không tồn tại | Xác nhận artifact/version và settings.xml, kiểm tra kết nối |

### Cách khoanh vùng

**Lỗi parent:** ưu tiên sửa `<parent>`/`relativePath`/repository, vì Maven chưa thể dựng effective POM để áp dụng BOM.

**Lỗi dependency version:** kiểm tra `dependencyManagement` và `help:effective-pom`; phân biệt managed version với dependencies thực sự thêm vào classpath.

**Lỗi build task:** kiểm tra plugin versions và lifecycle, đặc biệt Spring Boot Maven Plugin `repackage`.

**Lỗi runtime:** kiểm tra JDK, dependencies trong JAR/WAR, entrypoint, configuration và kết quả deploy thật. Không mặc định mọi lỗi runtime do BOM.

## 13. Bài tập tự kiểm tra

**Câu 1.** Project có `company-parent`, người học thêm `spring-boot-starter-parent` làm parent thứ hai. Maven chấp nhận không?  
**Đáp án:** Không. Chỉ một parent trực tiếp; nên giữ corporate parent và import `spring-boot-dependencies` BOM.

**Câu 2.** Chỉ import BOM mà không khai báo `spring-boot-starter-web`, server HTTP có tự xuất hiện không?  
**Đáp án:** Không. BOM chỉ cung cấp metadata quản lý versions.

**Câu 3.** Khi dùng parent riêng + BOM import, có cần version riêng cho Spring Boot Maven Plugin không?  
**Đáp án:** Có nếu parent riêng chưa quản lý version plugin. BOM import không mang pluginManagement của starter parent.

**Câu 4.** Lệnh `mvn package` tạo JAR thông thường, `java -jar` báo thiếu executable manifest. Nên kiểm tra gì?  
**Đáp án:** Spring Boot Maven Plugin, goal `repackage` và executable archive layout.

**Câu 5.** Bạn muốn thay version thư viện do imported BOM quản lý nhưng property override không hiệu lực. Làm sao?  
**Đáp án:** Thêm managed dependency tường minh, kiểm thử tương thích, xem effective POM và dependency tree.

**Câu 6.** Hai BOM trong cùng POM cùng manage một artifact. Điều gì quan trọng?  
**Đáp án:** Thứ tự import và những khai báo quản lý tại parent/child; không tự suy đoán precedence, phải kiểm chứng effective version.

## 14. Checklist áp dụng

- [ ] Đã chọn đúng corporate parent và không khai báo hai `<parent>`.
- [ ] Đã import `spring-boot-dependencies` bằng `type=pom` + `scope=import` trong `dependencyManagement`.
- [ ] Các starter và dependency cần dùng được khai báo ở `<dependencies>`, bỏ version khi BOM đã quản lý.
- [ ] Đã kiểm tra parent hoặc BOM khác có override version của Spring Boot dependencies không.
- [ ] Đã kiểm tra Maven Compiler Plugin, Surefire, Maven version và Java release.
- [ ] Với executable app, đã cấu hình version và `repackage` cho Spring Boot Maven Plugin.
- [ ] Đã xác minh effective POM và dependency tree của module cụ thể.
- [ ] Đã build test, kiểm tra `BOOT-INF` và chạy artifact để xác minh runtime.
- [ ] Có quy trình đồng bộ Boot BOM/plugin khi nâng cấp.

## 15. Tài liệu chính thức

- Spring Boot 3.5 Maven Plugin — Using the Plugin / Without the Parent POM: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Maven — Introduction to the Dependency Mechanism (importing BOM): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven POM Reference: https://maven.apache.org/pom.html
- Maven Help Plugin — Effective POM: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Dependency Plugin — Dependency Tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html

**Kết quả cần đạt:** Dự án giữ parent Maven của tổ chức, sử dụng đúng managed dependency versions từ Spring Boot BOM, đồng thời tự kiểm soát Maven plugins và executable packaging. Quyết định cuối cùng dựa trên effective POM, dependency tree và artifact thực tế, không chỉ dựa vào một khai báo `<dependencyManagement>`.