# Tạo WAR chạy độc lập và triển khai Spring Boot vào servlet container

## 1. Mục tiêu: một WAR, hai cách chạy

Spring Boot có thể đóng gói ứng dụng thành **executable WAR**. Artifact này có hai cách chạy:

1. Chạy độc lập bằng lệnh **java -jar**, sử dụng embedded servlet container được đóng gói cùng WAR.
2. Deploy WAR vào servlet container bên ngoài như Apache Tomcat; container bên ngoài quản lý process, HTTP connector và lifecycle của ứng dụng.

Đây là cách hữu ích khi tổ chức có nền tảng Tomcat dùng chung nhưng vẫn muốn giữ khả năng chạy thử artifact trực tiếp trong môi trường developer hoặc CI.

~~~text
Source code + Maven dependencies
              |
              v
       mvn clean verify
              |
              v
    release-demo-0.1.0.war
       /                \
      /                  \
     v                    v
java -jar app.war    External Tomcat
     |                    |
Embedded Tomcat       Servlet container
     |                    |
     +--------+-----------+
              |
              v
       Spring Boot app
       /ready, /version
~~~

**Executable WAR vẫn là một file WAR chuẩn để triển khai vào servlet container.** Spring Boot Maven Plugin bổ sung launcher và đặt các dependency của embedded container vào **WEB-INF/lib-provided**. Khi chạy bằng **java -jar**, launcher sử dụng các dependency đó; khi deploy vào external Tomcat, container cung cấp servlet engine của nó.

Ví dụ xuyên suốt bài:
- Java 17.
- Spring Boot 3.5.0.
- Maven 3.9.x.
- Packaging war.
- Apache Tomcat 10.1 cho external deployment.

Các version được pin để ví dụ nhất quán. Với dự án thật, kiểm tra Spring Boot system requirements và ma trận tương thích của servlet container mà tổ chức đang vận hành.

## 2. Kiểm tra tương thích servlet container trước khi build

Spring Boot 3.x dùng Jakarta EE APIs. Các package Servlet chuyển từ namespace **javax.servlet.*** sang **jakarta.servlet.***.

Vì vậy, cần chọn servlet container tương thích với Jakarta Servlet mà Spring Boot 3.5 hỗ trợ. Tomcat 10.1 là lựa chọn phù hợp cho ví dụ này; dùng JDK 17 khi chạy ứng dụng.

| Thành phần | Ví dụ sử dụng | Lưu ý |
| --- | --- | --- |
| Java | JDK 17 | Cùng major version ở build và runtime để tránh khác biệt không mong muốn |
| Spring Boot | 3.5.0 | Dùng Jakarta namespace |
| Maven | 3.9.x | Quản lý dependency và WAR packaging |
| External container | Tomcat 10.1 | Jakarta Servlet 6.0 |
| Artifact | release-demo-0.1.0.war | Chạy độc lập hoặc deploy external |

Không deploy ứng dụng Spring Boot 3.x vào Tomcat 9 hoặc container chỉ hỗ trợ javax.servlet. Lỗi thường xuất hiện dưới dạng ClassNotFoundException, NoClassDefFoundError hoặc lỗi khởi tạo Servlet vì API namespace không tương thích.

Nếu đang duy trì ứng dụng Spring Boot 2.x cũ dùng javax.*, cần xử lý migration riêng. Không trộn thư viện javax.servlet và jakarta.servlet trong cùng một deployment rồi mong container tự chuyển đổi.

Trước khi chọn container, xác nhận:
- Container version nằm trong phạm vi Spring Boot hỗ trợ.
- JDK runtime đáp ứng yêu cầu của cả Spring Boot và container.
- Container không dùng thư viện Spring/Jakarta cũ được chép thủ công vào thư mục shared lib.
- Các thư viện bên thứ ba trong ứng dụng đã có phiên bản tương thích Jakarta.

## 3. Cấu trúc Maven project

Ví dụ dùng project nhỏ có hai endpoint để xác minh cả executable WAR và external deployment:

~~~text
release-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/release/
                └── ReleaseDemoApplication.java
~~~

WAR không bắt buộc phải có web.xml nếu ứng dụng sử dụng Servlet 3.0+ programmatic initialization. Spring Boot dùng SpringBootServletInitializer để đăng ký application với servlet container.

## 4. Cấu hình pom.xml để tạo executable WAR

Đây là file pom.xml hoàn chỉnh cho ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>release-demo</artifactId>
    <version>0.1.0</version>
    <name>release-demo</name>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.1. Vì sao phải đổi packaging thành war?

Phần tử packaging war yêu cầu Maven WAR lifecycle tạo web archive. Artifact đầu ra có đuôi .war, cấu trúc WEB-INF/classes và WEB-INF/lib, phù hợp với servlet container.

Nếu vẫn để jar, Maven tạo JAR thông thường. JAR Spring Boot có thể chạy độc lập nhưng không phải WAR để deploy vào Tomcat theo cách này.

### 4.2. Vì sao starter Tomcat dùng provided scope?

spring-boot-starter-web mặc định kéo theo embedded Tomcat. Khi triển khai vào external Tomcat, servlet engine đã được container cung cấp.

Đặt spring-boot-starter-tomcat ở scope provided giúp mô hình deployment nhận biết dependency này được servlet container cung cấp. Spring Boot Maven Plugin vẫn giữ các provided dependencies cần thiết cho chế độ executable WAR trong WEB-INF/lib-provided.

Kết quả:
- WEB-INF/lib: application libraries và các dependency runtime thông thường.
- WEB-INF/lib-provided: embedded container libraries được dùng khi chạy executable WAR.
- External Tomcat dùng servlet engine của chính nó khi deploy WAR.

Không đưa thêm một Tomcat version khác vào WEB-INF/lib hoặc thư mục shared lib của server để chữa lỗi classpath. Trước tiên kiểm tra scope và dependency tree.

### 4.3. Spring Boot Maven Plugin đóng vai trò gì?

Spring Boot Maven Plugin chạy goal repackage để biến WAR vừa tạo thành executable WAR. Khi dùng spring-boot-starter-parent, cấu hình plugin execution mặc định được quản lý bởi parent.

Khai báo plugin trong build/plugins như ví dụ để bật Spring Boot packaging. Nếu dự án không kế thừa spring-boot-starter-parent, hãy cấu hình plugin version tương thích và khai báo execution của goal repackage rõ ràng:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Không thêm một plugin version tùy ý khác với Spring Boot dependency management. Giữ plugin cùng dòng version với Spring Boot để tránh mismatch trong quá trình repackage.

## 5. Viết application class hỗ trợ cả hai chế độ

Tạo file **src/main/java/com/example/release/ReleaseDemoApplication.java**:

~~~java
package com.example.release;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ReleaseDemoApplication extends SpringBootServletInitializer {

    public static void main(String[] args) {
        SpringApplication.run(ReleaseDemoApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(ReleaseDemoApplication.class);
    }

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    @GetMapping("/version")
    public String version() {
        return "release-demo:0.1.0";
    }
}
~~~

### 5.1. Vai trò của main()

main() khởi động Spring Boot theo cách thông thường. Khi chạy:

~~~bash
java -jar target/release-demo-0.1.0.war
~~~

Spring Boot sử dụng embedded Tomcat nằm trong executable WAR và khởi động web server như một ứng dụng độc lập.

### 5.2. Vai trò của SpringBootServletInitializer

External servlet container không khởi động ứng dụng bằng cách gọi main() như một tiến trình Spring Boot thông thường. Container khởi tạo web application theo Servlet API.

SpringBootServletInitializer kết nối quá trình khởi tạo đó với Spring ApplicationContext. Method configure() trả về nguồn cấu hình chính của ứng dụng:

~~~java
@Override
protected SpringApplicationBuilder configure(
        SpringApplicationBuilder application) {
    return application.sources(ReleaseDemoApplication.class);
}
~~~

Class chính vừa có main() vừa kế thừa SpringBootServletInitializer, vì vậy cùng một artifact hỗ trợ hai cách chạy.

Nếu thiếu initializer hoặc cấu hình configure() sai, executable WAR có thể chạy tốt bằng java -jar nhưng thất bại khi deploy vào external Tomcat. Đây là một trong những khác biệt quan trọng nhất khi kiểm tra WAR hai chế độ.

### 5.3. Vì sao không cần web.xml?

Với servlet container hỗ trợ Servlet 3.0 trở lên, ứng dụng có thể được khởi tạo bằng cơ chế programmatic initialization. Spring Boot dùng initializer và Servlet APIs để đăng ký application.

Chỉ tạo WEB-INF/web.xml khi ứng dụng có yêu cầu cấu hình legacy cụ thể. Không tạo file rỗng chỉ để làm cho WAR được nhận diện.

## 6. Build WAR và kiểm tra artifact

Từ thư mục gốc release-demo, chạy:

~~~bash
java -version
mvn -version
mvn -B -ntp clean verify
~~~

verify chạy các phase trước đó của Maven lifecycle, gồm compile, test, package và các bước verify được cấu hình trong project. Spring Boot Maven Plugin repackage WAR theo cấu hình parent/plugin.

Artifact chính:

~~~text
target/release-demo-0.1.0.war
~~~

Nếu build thất bại, xem exception gốc và Maven phase bị lỗi. Không xem file WAR cũ từ lần build trước là bằng chứng build hiện tại thành công.

### 6.1. Xem cấu trúc WAR

Dùng JDK jar tool:

~~~bash
jar tf target/release-demo-0.1.0.war
~~~

Trên Linux/macOS, lọc các thành phần quan trọng:

~~~bash
jar tf target/release-demo-0.1.0.war \
  | grep -E 'WEB-INF/(classes|lib|lib-provided)/|spring-boot'
~~~

Trên Windows Command Prompt:

~~~cmd
jar tf target\release-demo-0.1.0.war | findstr /I "WEB-INF spring-boot"
~~~

Kiểm tra có các thành phần:
- WEB-INF/classes/com/example/release/ReleaseDemoApplication.class
- WEB-INF/lib/ chứa Spring Boot application dependencies.
- WEB-INF/lib-provided/ chứa embedded Tomcat libraries cho executable WAR.
- Spring Boot loader entries do plugin tạo.

Tên/version các thư viện thực tế phụ thuộc dependency management. Không hardcode danh sách JAR giả định; đọc output của artifact đã build.

### 6.2. Kiểm tra Maven dependency tree

Xem dependency liên quan đến servlet container:

~~~bash
mvn -B -ntp dependency:tree \
  -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
~~~

Kiểm tra effective POM nếu cấu hình packaging hoặc plugin execution khác dự kiến:

~~~bash
mvn -B -ntp help:effective-pom
~~~

Kết quả cần được đọc cùng với cấu hình scope và nội dung WAR. Dependency tree giải thích Maven resolution; jar tf xác nhận nội dung archive thực tế.

## 7. Chạy executable WAR độc lập

Sau khi build thành công:

~~~bash
java -jar target/release-demo-0.1.0.war
~~~

Spring Boot khởi động embedded Tomcat. Mặc định ví dụ dùng HTTP port 8080.

Mở terminal khác và kiểm tra:

~~~bash
curl -i http://localhost:8080/ready
curl -i http://localhost:8080/version
~~~

Response body lần lượt:

~~~text
ready
release-demo:0.1.0
~~~

Có thể đổi port cho lần chạy độc lập:

~~~bash
java -jar target/release-demo-0.1.0.war --server.port=9090
~~~

Sau đó gọi http://localhost:9090/ready và http://localhost:9090/version.

Port server.port được embedded server sử dụng trong chế độ này. Khi deploy external Tomcat, port HTTP do connector của Tomcat quản lý trong conf/server.xml.

## 8. Chuẩn bị external Tomcat

### 8.1. Chọn đúng Tomcat

Với Spring Boot 3.5 và Jakarta Servlet, dùng external container tương thích; ví dụ Tomcat 10.1. Tải bản phân phối từ website Apache Tomcat chính thức, xác minh checksum/signature theo quy trình của tổ chức và chọn bản vá được vận hành hỗ trợ.

Không chỉ nhìn tên sản phẩm Tomcat mà bỏ qua major version. Tomcat 9 sử dụng javax.servlet; Tomcat 10.1 sử dụng jakarta.servlet.

### 8.2. Kiểm tra JDK mà Tomcat sử dụng

External Tomcat chạy bằng JVM của process/container. Đặt JAVA_HOME tới JDK 17 hoặc JDK được Spring Boot version của ứng dụng hỗ trợ.

Trên Linux/macOS:

~~~bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"

"$CATALINA_HOME/bin/catalina.sh" version
~~~

Trên Windows Command Prompt:

~~~cmd
set JAVA_HOME=C:\Java\jdk-17
set PATH=%JAVA_HOME%\bin;%PATH%

%CATALINA_HOME%\bin\catalina.bat version
~~~

Xác nhận output Tomcat hiển thị Java version và Java home dự kiến. Một service Tomcat được cài dưới dạng Windows Service hoặc systemd service có thể dùng environment khác với terminal; kiểm tra cấu hình service thực tế.

### 8.3. Phân biệt CATALINA_HOME và CATALINA_BASE

- CATALINA_HOME: thư mục cài đặt bộ binary Tomcat.
- CATALINA_BASE: thư mục instance chứa cấu hình, logs, deployed applications và runtime data.

Với bản cài đơn giản, hai thư mục có thể trùng nhau. Trong production, một Tomcat binary có thể phục vụ nhiều instance với CATALINA_BASE riêng.

WAR cần được đặt trong thư mục webapps của instance đang chạy, thường là:

~~~text
$CATALINA_BASE/webapps/
~~~

Nếu chưa cấu hình CATALINA_BASE, Tomcat thường dùng CATALINA_HOME làm base mặc định.

## 9. Deploy WAR vào Tomcat 10.1

### 9.1. Đặt tên WAR để xác định context path

Tomcat thường suy ra context path từ tên WAR:
- release-demo.war → /release-demo
- ROOT.war → /
- inventory.war → /inventory

Để URL dễ đọc, copy artifact versioned sang tên triển khai ổn định release-demo.war. File nguồn trong target vẫn giữ version để release record nhận diện chính xác.

### 9.2. Deploy trên Linux/macOS

Nếu Tomcat instance đang dùng CATALINA_BASE:

~~~bash
cp target/release-demo-0.1.0.war \
  "$CATALINA_BASE/webapps/release-demo.war"
~~~

Nếu dùng bản cài đơn giản không tách base:

~~~bash
cp target/release-demo-0.1.0.war \
  "$CATALINA_HOME/webapps/release-demo.war"
~~~

Khởi động Tomcat ở foreground để theo dõi log:

~~~bash
"$CATALINA_HOME/bin/catalina.sh" run
~~~

Nếu service Tomcat đã được quản lý bởi systemd hoặc service manager, dùng quy trình deploy/restart của môi trường đó. Tránh khởi động thêm một process Tomcat thứ hai trên cùng port.

### 9.3. Deploy trên Windows

Trong Command Prompt, khi CATALINA_BASE đã được cấu hình:

~~~cmd
copy target\release-demo-0.1.0.war "%CATALINA_BASE%\webapps\release-demo.war"
%CATALINA_HOME%\bin\catalina.bat run
~~~

Nếu không tách CATALINA_BASE, dùng %CATALINA_HOME%\webapps.

Nếu Tomcat đang chạy dưới dạng Windows Service, hãy dùng service manager và thư mục instance mà service đó thực sự sử dụng. Terminal hiện tại không nhất thiết phản ánh cấu hình của Windows Service.

### 9.4. Kiểm tra context path và endpoint

Với file triển khai release-demo.war, gọi:

~~~bash
curl -i http://localhost:8080/release-demo/ready
curl -i http://localhost:8080/release-demo/version
~~~

Response body lần lượt:

~~~text
ready
release-demo:0.1.0
~~~

Khác biệt URL cần nhớ:

| Chế độ | URL |
| --- | --- |
| Executable WAR, embedded Tomcat | http://localhost:8080/ready |
| External Tomcat, WAR tên release-demo.war | http://localhost:8080/release-demo/ready |
| External Tomcat, WAR tên ROOT.war | http://localhost:8080/ready |

Nếu URL bị 404, kiểm tra context path theo đúng tên WAR trước khi sửa controller mapping.

## 10. Ai quản lý port và context path?

Hai chế độ chạy có chủ thể quản lý khác nhau:

| Cấu hình | Executable WAR | External Tomcat |
| --- | --- | --- |
| HTTP port | Embedded Tomcat, thường qua server.port | External Tomcat connector trong conf/server.xml |
| Context path | Thường là / nếu không cấu hình thêm | Container deployment name/context descriptor |
| JVM process | java -jar ...war | Tomcat service/process |
| Server lifecycle | Spring Boot launcher | External container |
| Servlet engine | Embedded Tomcat trong WAR | Tomcat cài bên ngoài |
| Log startup | Console/logging của ứng dụng | Tomcat logs và application logs |

Không dùng server.port để thay đổi listener port của external Tomcat. Chỉnh connector trong server.xml theo quy trình vận hành container, rồi restart/reload service theo cách tổ chức quản lý.

Với external deployment, context path thường do tên WAR hoặc context descriptor quyết định. Nếu đổi tên artifact triển khai, URL có thể đổi dù source code và controller mapping không thay đổi.

## 11. Kiểm tra deployment thực tế

Một build Maven thành công chỉ chứng minh artifact đã được tạo. Cần kiểm tra WAR trong chính servlet container mục tiêu.

### 11.1. Kiểm tra startup logs

Khi deploy, xem log Tomcat:
- logs/catalina.*.log
- logs/localhost.*.log
- Console output khi chạy catalina.sh run hoặc catalina.bat run.
- Application logs theo logging configuration của project.

Tìm thông tin Tomcat đã deploy context, Spring ApplicationContext startup và lỗi khởi tạo bean. Không chỉ kiểm tra file WAR có xuất hiện trong webapps; container có thể tạo thư mục expanded nhưng ứng dụng vẫn startup thất bại.

### 11.2. Smoke test HTTP

Kiểm tra status code và response body:

~~~bash
curl -fsS http://localhost:8080/release-demo/ready
curl -fsS http://localhost:8080/release-demo/version
~~~

-f làm curl trả exit code khác 0 khi HTTP response là lỗi; -sS giữ output gọn nhưng vẫn hiển thị lỗi. Với ứng dụng triển khai ở context root, bỏ /release-demo khỏi URL.

Có thể kiểm tra status/header bằng:

~~~bash
curl -i http://localhost:8080/release-demo/ready
~~~

### 11.3. Phân biệt lỗi startup và lỗi request

- **Startup failure:** Tomcat không deploy được context hoặc Spring context không khởi tạo. Xem log trước khi gọi endpoint.
- **404:** request đã tới server nhưng context path hoặc route không đúng, hoặc ứng dụng chưa deploy thành công.
- **500:** route có thể đã được nhận diện nhưng xử lý request phát sinh lỗi; xem application stack trace.
- **Connection refused:** không có process lắng nghe port đó, Tomcat chưa chạy hoặc connector dùng port khác.
- **503:** proxy/load balancer hoặc container có thể đánh dấu instance chưa sẵn sàng; kiểm tra health routing và startup state.

Không sửa code controller khi nguyên nhân là Tomcat chưa start hoặc URL context path sai.

## 12. Không để thư viện server bị trùng lặp

Một WAR thường chứa Spring libraries trong WEB-INF/lib. External Tomcat cung cấp Servlet API và server implementation.

Một số lỗi classloading thường gặp:
- ClassCastException dù tên class giống nhau: có thể class được load từ classloader khác nhau.
- NoSuchMethodError: dependency version xung đột giữa WAR và shared libraries.
- NoClassDefFoundError với javax.servlet.*: thư viện cũ chưa được migrate sang Jakarta.
- NoClassDefFoundError với jakarta.servlet.*: container/API không tương thích hoặc dependency scope sai.
- Bean/Servlet initialization failure: initializer, listener hoặc cấu hình deployment sai.

Cách điều tra:
1. Kiểm tra WEB-INF/lib và WEB-INF/lib-provided.
2. Xem mvn dependency:tree để tìm version conflict.
3. Kiểm tra CATALINA_HOME/lib và CATALINA_BASE/lib xem có Spring/Jakarta libraries được thêm thủ công không.
4. Đảm bảo Tomcat version hỗ trợ Servlet namespace của ứng dụng.
5. Dùng một dependency management source nhất quán cho Spring Boot modules.

Không copy Spring Boot JAR vào Tomcat shared lib để chữa lỗi thiếu class. Việc đó có thể khiến nhiều ứng dụng dùng chung một version library và gây xung đột classloader.

## 13. Cấu hình ứng dụng khi chạy ở hai môi trường

Các cấu hình ứng dụng dùng chung có thể đặt trong src/main/resources/application.properties hoặc external configuration theo môi trường.

Ví dụ:

~~~properties
spring.application.name=release-demo
logging.level.root=INFO
~~~

Đối với executable WAR:
- server.port có thể điều chỉnh embedded Tomcat.
- JVM options và environment variables của process chạy java -jar quyết định runtime.

Đối với external Tomcat:
- Port/listener và TLS connector thuộc cấu hình Tomcat.
- JVM options thuộc service/container process.
- Context path thuộc deployment name hoặc context descriptor.
- Application properties vẫn có thể được cấp qua external configuration, nhưng phải xác nhận đúng cơ chế và vị trí cấu hình mà Spring Boot đang đọc.

Không đưa secret production vào WAR hoặc application.properties được commit. Dùng secret store/environment configuration của nền tảng triển khai.

Nếu cần cùng một WAR cho nhiều môi trường, giữ artifact bất biến và cấp cấu hình bên ngoài. Ghi lại config version/secret reference cùng release để có thể tái hiện deployment.

## 14. Kiểm thử và CI cho executable WAR

### 14.1. Build một artifact duy nhất

Pipeline cơ bản:

~~~bash
mvn -B -ntp clean verify
jar tf target/release-demo-0.1.0.war
~~~

Sau khi build:
1. Lưu WAR làm CI artifact.
2. Tính SHA-256 của file WAR.
3. Chạy thử bằng java -jar.
4. Deploy đúng file WAR đó vào servlet container tương thích.
5. Chạy smoke test trên context path thực tế.
6. Gắn kết quả test với cùng checksum và build ID.

Tính checksum:

~~~bash
sha256sum target/release-demo-0.1.0.war
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash target/release-demo-0.1.0.war -Algorithm SHA256
~~~

Checksum là định danh bytes của artifact. Không dùng version string đơn lẻ để chứng minh WAR trong CI và WAR đã deploy là cùng một file.

### 14.2. Test cả hai chế độ

| Test | Mục đích |
| --- | --- |
| mvn clean verify | Compile, unit tests và Maven lifecycle |
| jar tf ...war | Xác nhận archive có cấu trúc WAR và loader |
| java -jar ...war | Kiểm tra executable mode với embedded Tomcat |
| Deploy vào Tomcat 10.1 | Kiểm tra external servlet initialization |
| GET /ready | Kiểm tra ứng dụng đã sẵn sàng nhận request |
| GET /version | Xác nhận đúng artifact/version đang chạy |
| Startup log review | Phát hiện bean, classloader và Servlet errors |

Không coi test java -jar thay thế cho external deployment test. Hai chế độ đi qua hai đường khởi tạo server khác nhau.

### 14.3. Kiểm tra trong CI mà không cần giữ một Tomcat production

Có thể dùng một Tomcat test instance/container có version được pin và chạy trong job integration test:
- Khởi động container tương thích Jakarta Servlet.
- Copy/deploy WAR đã build.
- Chờ health endpoint sẵn sàng với timeout có giới hạn.
- Gọi smoke test.
- Thu thập logs nếu deployment thất bại.
- Dừng và loại bỏ test instance sau job.

Pin image/version Tomcat trong CI và production theo cùng compatibility policy. Nếu production dùng cấu hình/context descriptor riêng, bổ sung deployment test đại diện cho cấu hình đó.

## 15. Lỗi thường gặp khi tạo và deploy WAR

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Maven tạo JAR thay vì WAR | packaging vẫn là jar | Đặt packaging war rồi build sạch |
| WAR không chạy bằng java -jar | Spring Boot repackage chưa chạy hoặc thiếu main class | Kiểm tra plugin execution và manifest |
| WAR chạy độc lập nhưng external Tomcat không deploy | Thiếu SpringBootServletInitializer hoặc configure() sai | Kế thừa initializer và trả về application source |
| Tomcat báo thiếu javax.servlet | App/dependency dùng namespace cũ hoặc server sai version | Dùng Jakarta-compatible dependency và Tomcat 10.1 |
| Tomcat báo thiếu jakarta.servlet | External container không cung cấp Jakarta Servlet phù hợp | Nâng container lên version tương thích |
| Embedded Tomcat conflict khi deploy | Starter Tomcat không ở provided hoặc libraries bị copy trùng | Kiểm tra scope, WEB-INF/lib-provided và shared lib |
| URL trả 404 sau deploy | Context path được suy ra từ tên WAR | Gọi đúng /release-demo hoặc dùng tên ROOT.war |
| Port 8080 đã được sử dụng | Một process/server khác đang lắng nghe | Kiểm tra process/connector; đổi port đúng môi trường |
| Connection refused | Tomcat chưa chạy hoặc connector port khác | Kiểm tra process và server.xml |
| HTTP 500 | Application code/bean/config phát sinh lỗi | Đọc application stack trace |
| WAR có trong webapps nhưng không hoạt động | Deployment/startup thất bại sau khi container nhận file | Kiểm tra catalina/localhost logs |
| NoSuchMethodError | Spring/library version xung đột hoặc shared library cũ | Kiểm tra dependency tree và Tomcat shared lib |
| ClassCastException khi load Servlet/filter | Classloader hoặc duplicate API classes | Loại trùng Servlet API/server libraries |
| Java version mismatch | Tomcat service dùng JDK khác terminal | Kiểm tra service environment và catalina version |
| Build pass nhưng external deployment fail | Chỉ kiểm thử executable mode | Thêm integration test với đúng servlet container |
| Đổi tên WAR làm URL thay đổi | Tomcat dùng tên WAR để tạo context path | Cố định deployment filename hoặc context descriptor |
| web.xml không tồn tại | Nhầm rằng mọi WAR đều cần web.xml | Dùng Servlet 3+ initializer; chỉ thêm descriptor khi có yêu cầu cụ thể |

## 16. Cập nhật, rollback và quản lý artifact

Một quy trình deploy có thể lặp lại nên:
1. Build WAR từ commit đã được duyệt.
2. Chạy mvn clean verify.
3. Ghi GAV/version, build ID và SHA-256.
4. Kiểm tra executable mode.
5. Deploy WAR vào Tomcat test và chạy smoke test.
6. Promote đúng artifact sang môi trường tiếp theo.
7. Ghi lại Tomcat version, JDK version, context path và config reference.
8. Lưu WAR trước đó theo retention policy để rollback.

Khi cập nhật ứng dụng:
- Dùng deployment process của nền tảng để tránh copy WAR khi container đang ghi/đọc file.
- Đảm bảo instance cũ đã drain traffic nếu có load balancer.
- Xác nhận application startup hoàn tất trước khi nhận traffic.
- Giữ log của cả deploy và startup.
- Nếu rollback, triển khai lại artifact cũ đã xác định bằng checksum.

Đừng build lại source trong production host để tạo WAR khác với artifact đã được QA. Một release nên promote cùng một file đã kiểm thử.

## 17. Checklist trước khi bàn giao WAR

### Build và cấu trúc

- [ ] Maven project đặt packaging war.
- [ ] Java/Spring Boot/Maven versions đã được pin.
- [ ] spring-boot-starter-tomcat dùng scope provided.
- [ ] Spring Boot Maven Plugin thực hiện repackage.
- [ ] Main class kế thừa SpringBootServletInitializer.
- [ ] configure() trả về đúng application source.
- [ ] mvn clean verify thành công.
- [ ] WAR có WEB-INF/classes, WEB-INF/lib và các entry cần thiết.
- [ ] Executable WAR có loader và WEB-INF/lib-provided phù hợp.

### External servlet container

- [ ] Container version hỗ trợ Jakarta Servlet mà app cần.
- [ ] JDK của Tomcat service đáp ứng yêu cầu ứng dụng.
- [ ] Context path được xác định từ tên WAR/descriptor.
- [ ] External container quản lý HTTP port và TLS connector.
- [ ] Không có Spring/Servlet libraries xung đột trong shared lib.
- [ ] Startup logs không có lỗi deployment.
- [ ] Smoke tests trả response mong đợi.

### Release và vận hành

- [ ] Cùng một WAR được test ở executable và external mode.
- [ ] SHA-256 được lưu cùng build ID/release.
- [ ] WAR và config được quản lý riêng.
- [ ] Secret không được đóng gói trong artifact.
- [ ] Có log, health check, rollback artifact và retention policy.
- [ ] Deployment dùng quy trình của môi trường thay vì sửa file thủ công không truy vết.

## 18. Tài liệu chính thức

- Spring Boot 3.5 – [Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html): triển khai ứng dụng Spring Boot dạng WAR vào servlet container và SpringBootServletInitializer.
- Spring Boot 3.5 – [Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): repackage, executable archives và WAR packaging.
- Spring Boot 3.5 – [System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java và servlet container compatibility.
- Spring Boot 3.5 – [Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): servlet application initialization và embedded container.
- Apache Tomcat 10.1 – [Application Developer's Guide](https://tomcat.apache.org/tomcat-10.1-doc/appdev/): cấu trúc web application và deployment.
- Apache Tomcat 10.1 – [Manager App HOW-TO](https://tomcat.apache.org/tomcat-10.1-doc/manager-howto.html): triển khai/undeploy qua Manager khi môi trường đã bật và bảo vệ chức năng này.
- Apache Tomcat 10.1 – [Migration Guide](https://tomcat.apache.org/migration-10.html): khác biệt Jakarta namespace khi chuyển từ Tomcat 9 sang Tomcat 10.
- Apache Maven – [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): các phase package, verify và lifecycle.
- Apache Maven – [Maven WAR Plugin](https://maven.apache.org/plugins/maven-war-plugin/): cấu hình WAR packaging.

**Ghi nhớ:** Một executable Spring Boot WAR có thể vừa chạy bằng java -jar với embedded Tomcat, vừa deploy vào external servlet container. Để hỗ trợ cả hai, đặt packaging là war, chuyển embedded Tomcat sang scope provided, bật Spring Boot repackage, và cho main application kế thừa SpringBootServletInitializer. Sau khi build, kiểm tra cấu trúc WAR, chạy độc lập, deploy vào Tomcat Jakarta-compatible rồi smoke test đúng context path của artifact.