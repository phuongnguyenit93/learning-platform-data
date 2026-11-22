# Thay đổi mã, chạy lại và xác minh kết quả quan sát được

Trong dự án Spring Boot đầu tiên, việc chạy thành công ứng dụng mới chỉ là bước khởi đầu. Công việc thường ngày của lập trình viên là **thay đổi mã, đưa thay đổi đó vào tiến trình đang chạy, rồi kiểm chứng ứng dụng có biểu hiện đúng như dự kiến hay không**.

Một thay đổi tưởng như đơn giản, chẳng hạn sửa câu chào của API, có thể chưa xuất hiện khi bạn gọi HTTP endpoint. Lý do không nhất thiết là đoạn Java sai: có thể bạn chưa biên dịch lại, chưa khởi động lại server, đang gọi nhầm cổng, hoặc vẫn chạy một file JAR được tạo từ mã cũ.

Bài học này xây dựng một vòng phản hồi có thể lặp lại:

~~~text
Đọc hành vi hiện tại
         │
         ▼
Chọn một thay đổi cụ thể
         │
         ▼
Sửa mã nguồn và lưu file
         │
         ▼
Biên dịch / chạy lại ứng dụng
         │
         ▼
Gửi request đến đúng tiến trình
         │
         ▼
Quan sát status, response, log
         │
         ▼
So sánh với kết quả mong đợi
         │
    ┌────┴─────┐
    ▼          ▼
   Đúng        Sai
    │          │
    ▼          ▼
Ghi nhận    Tìm nguyên nhân,
kết quả     sửa và thử lại
~~~

Điểm cốt lõi là phân biệt **“mã nguồn đã sửa”**, **“mã đã được build”**, **“mã đang chạy”** và **“kết quả mà client quan sát”**. Chúng liên quan chặt chẽ nhưng không tự động là một.

## 1. Ta đang muốn xác minh điều gì?

Giả sử ứng dụng đầu tiên có endpoint:

~~~http
GET /api/greeting?name=Lan
~~~

Ban đầu, server trả về:

~~~json
{
  "message": "Xin chào, Lan!"
}
~~~

Bạn muốn thay thành:

~~~json
{
  "message": "Xin chào, Lan! Đây là phiên bản đã sửa."
}
~~~

Một phép kiểm chứng có ý nghĩa phải trả lời được ba câu hỏi:

1. **Có đúng mã mới được thực thi không?** Biên dịch và khởi động lại là cách phổ biến để cập nhật class đã thay đổi vào tiến trình JVM.
2. **Có gọi đúng ứng dụng và đúng endpoint không?** Cần quan sát địa chỉ, cổng, HTTP method và đường dẫn.
3. **Kết quả trả về có đúng yêu cầu không?** Cần đối chiếu status, nội dung response và, khi cần, log hoặc test tự động.

Một dòng log `Started DemoApplication` chỉ chứng minh tiến trình đã hoàn thành một giai đoạn khởi động; nó **không đủ để chứng minh** endpoint đã trả nội dung mới. Ngược lại, response có nội dung mới từ một endpoint xác nhận được rằng đường xử lý tương ứng đã thực thi mã mới hoặc một cấu hình có tác dụng tương đương.

Khi kiểm chứng, hãy định nghĩa trước **kết quả mong đợi** để tránh việc nhìn bất kỳ response nào cũng xem là thành công.

## 2. Chuẩn bị dự án minh họa

Ví dụ sử dụng Java 21, Spring Boot 3.x và Maven. Với dự án Spring Boot đã có `spring-boot-starter-web`, bạn có thể bắt đầu từ phần controller. Nếu đang dùng Gradle, mã Java hoàn toàn tương tự; chỉ khác lệnh build và chạy.

Để ví dụ tự chứa, cấu trúc dự án như sau:

~~~text
demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── demo/
        │               ├── DemoApplication.java
        │               ├── GreetingController.java
        │               └── GreetingResponse.java
        └── resources/
            └── application.properties
~~~

### 2.1. Khai báo Maven tối thiểu

File `pom.xml`:

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
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Phiên bản trong ví dụ cố định để minh họa một dự án có thể tái hiện. Khi tạo dự án thực tế, bạn nên chọn một bản Spring Boot đang được hỗ trợ, phù hợp với Java và các thư viện của mình.

### 2.2. Điểm khởi động

File `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` giúp kích hoạt component scan và auto-configuration trong phạm vi phù hợp. Đặt controller cùng package `com.example.demo` để Spring có thể phát hiện controller theo cách quét mặc định.

### 2.3. Kiểu dữ liệu của response

File `src/main/java/com/example/demo/GreetingResponse.java`:

~~~java
package com.example.demo;

public record GreetingResponse(String message) {
}
~~~

`record` là kiểu Java gọn để mô tả dữ liệu. Khi ứng dụng web có các dependency JSON thích hợp, Spring MVC có thể chuyển một `GreetingResponse` thành JSON trong response HTTP.

### 2.4. Controller ban đầu

File `src/main/java/com/example/demo/GreetingController.java`:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/api/greeting")
    public GreetingResponse greeting(
            @RequestParam(defaultValue = "Bạn") String name) {
        return new GreetingResponse("Xin chào, " + name + "!");
    }
}
~~~

Trong đoạn mã trên:

- `@RestController` đánh dấu một component xử lý HTTP và trả dữ liệu response body.
- `@GetMapping("/api/greeting")` ánh xạ request `GET` tại đường dẫn này đến method `greeting`.
- `@RequestParam` đọc tham số `name` trong query string. Nếu không cung cấp, ứng dụng dùng `Bạn`.
- `GreetingResponse` cung cấp đối tượng dữ liệu để bộ chuyển đổi HTTP ghi thành JSON.

### 2.5. Cấu hình cổng và tên ứng dụng

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=demo
server.port=8080
~~~

Cổng `8080` được đặt rõ trong ví dụ để dễ kiểm tra. Nếu máy đã có chương trình khác dùng cổng đó, bạn phải chọn một cổng còn trống hoặc dừng chương trình đang giữ cổng.

## 3. Bước 1: Chạy phiên bản ban đầu và ghi nhận mốc so sánh

Từ thư mục `demo`, cần có JDK và Maven phù hợp.

Kiểm tra các lệnh cơ bản nếu môi trường chưa được thiết lập:

~~~bash
java -version
mvn -version
~~~

`java -version` cho biết Java runtime được gọi từ terminal. `mvn -version` còn cho biết Java mà Maven đang dùng. Việc hai lệnh trỏ đến những JDK khác nhau có thể khiến build và chạy có hành vi khó hiểu.

Khởi động bằng Maven:

~~~bash
mvn spring-boot:run
~~~

Nếu dự án có **Maven Wrapper**, có thể dùng:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell, dùng wrapper tương ứng nếu đã tồn tại:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Không phải mọi dự án đều có các file wrapper. Lệnh dùng wrapper chỉ hoạt động nếu chúng có sẵn trong dự án.

Khi Spring Boot khởi động thành công, log thường chứa các thông tin tương tự:

~~~text
... Tomcat started on port 8080 (http) ...
... Started DemoApplication in ... seconds ...
~~~

Chi tiết log và thời gian có thể khác nhau theo phiên bản, cấu hình và môi trường. Dấu hiệu hữu ích là không có lỗi khởi động làm ứng dụng thoát và server lắng nghe trên cổng mong đợi.

**Giữ terminal chạy server hoạt động.** Một ứng dụng web đang chạy trong terminal thường tiếp tục chiếm terminal đó cho đến khi bạn dừng nó. Hãy mở terminal thứ hai để gửi HTTP request.

### 3.1. Gọi endpoint trước khi sửa

Trong terminal thứ hai:

~~~bash
curl -i "http://localhost:8080/api/greeting?name=Lan"
~~~

Nếu PowerShell đang dùng alias khác cho `curl`, hãy gọi rõ chương trình:

~~~powershell
curl.exe -i "http://localhost:8080/api/greeting?name=Lan"
~~~

Một response tương đương là:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"message":"Xin chào, Lan!"}
~~~

Định dạng header cụ thể, thứ tự header và khoảng trắng trong JSON có thể khác. Phần cần đối chiếu là:

| Yếu tố quan sát | Mong đợi ở phiên bản ban đầu |
| --- | --- |
| HTTP method | `GET` |
| URL | `http://localhost:8080/api/greeting?name=Lan` |
| HTTP status | `200 OK` |
| Content type | JSON (`application/json`) |
| Trường JSON | `message` |
| Giá trị `message` | `Xin chào, Lan!` |

Bạn cũng có thể thử khi không truyền tên:

~~~bash
curl -i "http://localhost:8080/api/greeting"
~~~

Khi đó `name` mặc định là `Bạn`, vì controller có `@RequestParam(defaultValue = "Bạn")`.

**Ghi nhận mốc ban đầu trước khi sửa.** Nếu endpoint chưa hoạt động ngay từ đầu, hãy xử lý vấn đề khởi động hoặc đường dẫn trước, rồi mới dùng nó để xác minh một thay đổi mới.

## 4. Bước 2: Sửa đúng phần mã tạo ra hành vi

Mục tiêu thay đổi ở đây là: thêm câu `Đây là phiên bản đã sửa.` vào nội dung lời chào. Giữ nguyên endpoint, method và cấu trúc JSON để việc so sánh tập trung vào một thay đổi.

Mở `GreetingController.java` và sửa **một dòng trả về**.

**Trước khi sửa:**

~~~java
return new GreetingResponse("Xin chào, " + name + "!");
~~~

**Sau khi sửa:**

~~~java
return new GreetingResponse(
        "Xin chào, " + name + "! Đây là phiên bản đã sửa.");
~~~

Giữ nguyên phần còn lại:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/api/greeting")
    public GreetingResponse greeting(
            @RequestParam(defaultValue = "Bạn") String name) {
        return new GreetingResponse(
                "Xin chào, " + name + "! Đây là phiên bản đã sửa.");
    }
}
~~~

Lưu file bằng trình biên tập. Nếu IDE mở nhiều tab, hãy chắc chắn file được lưu đúng đường dẫn `src/main/java/com/example/demo/GreetingController.java`.

Một thay đổi có thể quan sát rõ nên có đặc điểm:

- **Nhỏ:** dễ xác định chính xác đoạn mã nào chịu trách nhiệm.
- **Có tác dụng bên ngoài:** có thể nhìn thấy trong HTTP response, log, dữ liệu lưu hoặc tác động mà bạn có quyền kiểm tra.
- **Có kết quả mong đợi định trước:** trước khi chạy lại, ta đã biết JSON cần trả gì.
- **Có thể lặp lại:** cùng đầu vào và điều kiện phù hợp tạo ra kết quả nhất quán.

Lưu file chỉ thay đổi **source trên ổ đĩa**. Nó không bảo đảm class mới đã được nạp vào JVM đang chạy.

## 5. Bước 3: Đưa mã mới vào ứng dụng đang chạy

### 5.1. Cách chắc chắn cho người mới: dừng và khởi động lại

Quay về terminal đang chạy `mvn spring-boot:run`, dừng chương trình bằng `Ctrl+C`. Đợi tiến trình kết thúc rồi chạy lại:

~~~bash
mvn spring-boot:run
~~~

Trong quy trình này, Maven chuẩn bị ứng dụng từ source theo vòng đời liên quan và Spring Boot tạo một tiến trình chạy mới. Khi source đã lưu và được biên dịch thành công, controller mới được sử dụng ở lần khởi động tiếp theo.

~~~text
Sửa GreetingController.java
            │
            ▼
        Lưu source
            │
            ▼
Dừng tiến trình Spring Boot cũ
            │
            ▼
Biên dịch source mới và chạy lại
            │
            ▼
Tiến trình JVM mới phục vụ /api/greeting
~~~

Nếu thay đổi gây lỗi biên dịch, ứng dụng **không thể khởi động thành công từ các class mới** cho đến khi sửa lỗi. Hãy đọc thông báo compiler và vị trí file/dòng trước khi thử lại.

### 5.2. Nếu chạy từ IDE

Trong IntelliJ IDEA, Eclipse hoặc VS Code, thao tác cụ thể phụ thuộc vào cấu hình dự án và IDE. Cách xác định nhất là:

1. Lưu `GreetingController.java`.
2. Dừng phiên chạy ứng dụng cũ.
3. Chạy lại cấu hình Spring Boot/main class, để IDE biên dịch source thay đổi.
4. Quan sát log mới rồi gọi lại endpoint.

Một số IDE hỗ trợ **HotSwap**, tự build hoặc tự restart. Chức năng đó không nên được giả định là đang bật. Đặc biệt, HotSwap tiêu chuẩn chỉ hỗ trợ một tập thay đổi nhất định; thay đổi cấu trúc class thường có giới hạn khác với thay đổi phần thân method.

### 5.3. Nếu chạy bằng executable JAR

Với cách đóng gói, hãy phân biệt rõ **build JAR** và **chạy JAR**:

~~~bash
mvn clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

`mvn clean package` xóa output build cũ rồi thực hiện các bước đến giai đoạn package, trong đó có biên dịch và chạy những kiểm thử được cấu hình theo vòng đời Maven. Lệnh `java -jar` khởi chạy một artifact đã được đóng gói.

Nếu chỉ sửa `.java` rồi tiếp tục chạy **JAR cũ** mà không build lại, bạn có thể nhận response cũ dù source đã thay đổi đúng.

**Trình tự cần nhớ với JAR:**

~~~text
Thay source → Build JAR mới → Dừng tiến trình cũ → Chạy JAR mới → Gọi HTTP
~~~

Việc đặt JAR mới lên đĩa cũng không tự thay thế class đã nạp trong một tiến trình JVM cũ. Bạn cần cơ chế triển khai/restart thực sự để tiến trình sử dụng artifact mới.

### 5.4. Nếu dự án dùng Gradle

Đối với dự án Spring Boot dùng Gradle và plugin Spring Boot, các thao tác tương đương thường là:

~~~bash
./gradlew bootRun
~~~

Để đóng gói:

~~~bash
./gradlew clean bootJar
~~~

Trên PowerShell, nếu repository có Gradle Wrapper:

~~~powershell
.\gradlew.bat bootRun
.\gradlew.bat clean bootJar
~~~

Executable JAR thường được tạo trong `build/libs/`; tên cụ thể phụ thuộc cấu hình dự án. Chỉ chạy `java -jar` với đúng artifact mới đã build thành công. Các lệnh này mô tả **lựa chọn thay thế** Maven khi dự án được thiết lập bằng Gradle; không phải chạy cả hai công cụ build cho một dự án.

## 6. Bước 4: Gọi lại endpoint và quan sát kết quả

Sau khi server mới khởi động, tại terminal thứ hai chạy:

~~~bash
curl -i "http://localhost:8080/api/greeting?name=Lan"
~~~

Kết quả mong đợi:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"message":"Xin chào, Lan! Đây là phiên bản đã sửa."}
~~~

So sánh với phiên bản ban đầu:

| Thuộc tính | Trước sửa | Sau sửa |
| --- | --- | --- |
| URL | `GET /api/greeting?name=Lan` | Giữ nguyên |
| Status | `200` | `200` |
| Dạng dữ liệu | JSON | JSON |
| `message` | `Xin chào, Lan!` | `Xin chào, Lan! Đây là phiên bản đã sửa.` |

Như vậy, phản hồi mới có thể quan sát được theo đúng mục tiêu: **cùng request, cùng cấu trúc, khác giá trị dự kiến**.

Cần tránh kết luận quá mức. Response này chưa chứng minh mọi chức năng khác của ứng dụng đều hoạt động, cũng không chứng minh hệ thống có độ an toàn hoặc hiệu năng đủ để triển khai production. Nó xác nhận một hành vi cụ thể của một đường xử lý cụ thể tại thời điểm kiểm tra.

### 6.1. Kiểm tra thêm đầu vào thứ hai

Gửi request không có `name`:

~~~bash
curl -i "http://localhost:8080/api/greeting"
~~~

Phản hồi mong đợi:

~~~json
{"message":"Xin chào, Bạn! Đây là phiên bản đã sửa."}
~~~

Phép thử này xác nhận quy tắc mặc định của tham số vẫn hoạt động sau khi sửa câu chào.

### 6.2. Thử một đường dẫn không tồn tại

~~~bash
curl -i "http://localhost:8080/api/not-found"
~~~

Một ứng dụng Spring MVC không có mapping phù hợp thường trả HTTP `404 Not Found`. Nội dung body lỗi có thể thay đổi theo phiên bản và cấu hình, vì thế tập trung vào status. Đây là một trường hợp giúp phân biệt “server chạy được nhưng gọi sai route” với “server không khởi động”.

### 6.3. Quan sát HTTP status và body là hai phép kiểm khác nhau

Một endpoint có thể trả `200` nhưng body sai, hoặc trả JSON mong đợi trong một tình huống giả lập nhưng thực tế HTTP status không đúng hợp đồng. Với API đầu tiên, nên xem tối thiểu:

- **Status:** server xử lý request thành công hay báo lỗi gì?
- **Content type:** phản hồi có dạng JSON như hợp đồng hay không?
- **Body:** những trường và giá trị có đúng không?
- **Địa chỉ request:** host, port, path, method và tham số có đúng không?

Khi cần xác nhận chính xác cấu trúc JSON, có thể parse JSON rồi kiểm tra trường thay vì so sánh cả chuỗi body. Thứ tự thuộc tính và khoảng trắng trong JSON không phải lúc nào cũng có ý nghĩa.

## 7. Phân biệt log build, log khởi động và log request

Người mới thường thấy nhiều dòng chữ trong terminal và tưởng tất cả đều xác nhận một điều. Trên thực tế, chúng phản ánh những giai đoạn khác nhau.

| Nguồn thông tin | Chứng minh hoặc hỗ trợ kiểm tra điều gì? | Chưa chứng minh điều gì? |
| --- | --- | --- |
| Log biên dịch Maven/Gradle | Build task đã xử lý source và dependency theo quy trình | Endpoint chắc chắn trả dữ liệu mong đợi |
| Log `Started DemoApplication` | Application context đã hoàn tất khởi động tương ứng | Request cụ thể đã chạy đúng logic |
| Log server lắng nghe cổng | Server bắt đầu phục vụ tại một cổng | Client đang gọi đúng cổng hoặc đúng tiến trình |
| HTTP status và body | Kết quả thực tế client nhận được từ request | Mọi luồng nghiệp vụ khác đều đúng |
| Log do mã ứng dụng ghi | Dấu vết hỗ trợ xác định đường xử lý | Tất cả hành vi đã thành công từ đầu đến cuối |

Để quan sát trực tiếp khi một method được gọi, có thể thêm logging một cách có chủ đích.

Ví dụ trong `GreetingController`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
~~~

Khai báo logger trong class:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(GreetingController.class);
~~~

Và trong method:

~~~java
log.info("Greeting endpoint invoked");
return new GreetingResponse(
        "Xin chào, " + name + "! Đây là phiên bản đã sửa.");
~~~

Đây là các đoạn **bổ sung** vào controller của ví dụ, không phải một file Java độc lập. Sau khi lưu và chạy lại, một request hợp lệ tới endpoint sẽ tạo log tương ứng khi cấu hình logging cho phép hiển thị mức `INFO`.

Không ghi token, mật khẩu, thông tin riêng tư hoặc dữ liệu nhạy cảm vào log chỉ để kiểm tra một endpoint. Trong bài này, status và JSON body đã đủ để xác nhận lời chào; logging là một công cụ bổ trợ khi cần lần theo luồng xử lý.

## 8. Khi nào cần build, restart hoặc chỉ refresh trình duyệt?

“Chạy lại” có nhiều nghĩa. Loại thay đổi quyết định bước cập nhật cần thực hiện.

| Bạn thay đổi gì? | Cách cập nhật chắc chắn cho dự án đầu tiên |
| --- | --- |
| Java source (`.java`) | Lưu → biên dịch lại → restart ứng dụng |
| `application.properties` hoặc `application.yml` | Lưu → restart ứng dụng để nạp cấu hình mới |
| Dependency trong `pom.xml` hoặc `build.gradle` | Resolve/build dependency → restart ứng dụng |
| Executable JAR đã đóng gói | Build JAR mới → dừng tiến trình cũ → chạy JAR mới |
| Nội dung hiển thị của trang frontend do công cụ khác build | Thực hiện quy trình build/reload tương ứng rồi tải lại trang |
| Chỉ thay URL trong client hoặc tham số query | Gửi request mới, thường không cần restart server |

Bảng mô tả cách làm ổn định cho người mới. Một số môi trường có công cụ tự phát hiện file thay đổi và restart/reload, nhưng chỉ nên dựa vào chúng sau khi đã hiểu cơ chế đang hoạt động.

**Refresh trình duyệt không biên dịch Java.** Nếu server vẫn chạy class cũ, việc bấm F5 nhiều lần sẽ không khiến source Java mới tự được nạp.

## 9. Spring Boot DevTools có giúp tự chạy lại không?

Spring Boot DevTools là tiện ích tùy chọn cho vòng phát triển. Khi được cấu hình đúng, nó có thể phát hiện thay đổi trên classpath và kích hoạt **application restart** để bạn thấy mã mới nhanh hơn. Nó không thay thế bước biên dịch Java.

Với Maven, có thể thêm vào `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Sau đó chạy lại dự án trong chế độ phát triển. Một số điểm cần phân biệt:

1. Sửa file `.java` làm **source thay đổi**, nhưng DevTools dựa vào những thay đổi thích hợp trên **classpath**. IDE hoặc build tool phải đưa class đã biên dịch mới vào classpath để cơ chế restart phát hiện.
2. Với chế độ khởi chạy hoặc cấu hình IDE khác nhau, có thể cần build project, biên dịch lại class hoặc bật cơ chế tự build của IDE.
3. DevTools không bảo đảm hỗ trợ mọi loại thay đổi cấu hình/runtime bằng reload tức thời; vẫn có trường hợp cần restart thủ công.
4. DevTools dành cho **phát triển**, không phải cơ chế cập nhật mã production.

Nếu muốn học rõ vòng đời cơ bản, lần đầu hãy dừng và chạy lại bằng tay. Sau khi đã quan sát thành công, DevTools giúp rút ngắn vòng phản hồi, nhưng không làm thay đổi nguyên tắc: **mã mới phải đến được tiến trình phục vụ request**.

## 10. Những tình huống “đã sửa nhưng kết quả vẫn cũ”

Các tình huống sau rất phổ biến trong dự án đầu tiên. Hãy bắt đầu từ tín hiệu quan sát được thay vì sửa ngẫu nhiên nhiều file.

### 10.1. Quên lưu file

**Triệu chứng:** Trong trình biên tập có câu chào mới, nhưng response vẫn là câu cũ.

**Khả năng:** Nội dung đã sửa chỉ đang nằm trong bộ nhớ của trình soạn thảo. Build tool đọc file trên ổ đĩa vẫn thấy nội dung cũ.

**Cách xử lý:** Lưu file, kiểm tra tab không còn dấu hiệu thay đổi chưa lưu, build/restart rồi gọi lại endpoint.

### 10.2. Chưa biên dịch hoặc chưa restart

**Triệu chứng:** Source trên ổ đĩa đúng, không báo lỗi, nhưng khi gọi API vẫn nhận body cũ.

**Khả năng:** JVM đang chạy class được biên dịch trước khi sửa. Trường hợp này rất thường gặp nếu không dùng DevTools hoặc IDE không tự build.

**Cách xử lý:** Dừng server, chạy lại qua Maven/Gradle/IDE, đợi startup hoàn tất, rồi request lần nữa.

### 10.3. Chạy nhầm JAR hoặc nhầm thư mục dự án

**Triệu chứng:** Build thành công, khởi chạy được, nhưng phiên bản API không đổi.

**Khả năng:** Terminal đang chạy một JAR cũ hoặc thư mục khác. Dự án có thể có nhiều artifact hoặc nhiều module.

**Cách xử lý:** Xem đường dẫn hiện tại, kiểm tra file JAR được gọi trong lệnh, build lại đúng module và khởi chạy đúng artifact. Với Maven, lệnh `mvn clean package` trong dự án minh họa sẽ tạo artifact mới ở `target/` nếu build thành công.

Đừng đoán JAR mới chỉ dựa vào phần tên gần giống; cần dùng đúng đường dẫn artifact vừa được tạo.

### 10.4. Gọi sai cổng

**Triệu chứng:** HTTP không kết nối được, hoặc trả dữ liệu cũ dù log ứng dụng mới cho biết đang lắng nghe cổng khác.

**Khả năng:** Ứng dụng mới chạy tại `8081`, nhưng client vẫn gọi `8080`. Có thể có một ứng dụng cũ vẫn chạy tại `8080`.

**Cách xử lý:** Đọc log cổng khi khởi động và các cấu hình `server.port`. Sau đó đối chiếu nguyên văn URL trong client.

Ví dụ nếu ứng dụng chạy ở `8081`:

~~~bash
curl -i "http://localhost:8081/api/greeting?name=Lan"
~~~

Nếu bạn chủ động đổi cổng mà vẫn muốn so sánh, hãy ghi lại **host và port** đang được kiểm tra trong từng lượt.

### 10.5. Cổng đang bị chiếm

**Triệu chứng:** Log khởi động chứa thông báo tương tự `Port 8080 was already in use`; ứng dụng mới không start được.

**Khả năng:** Có một tiến trình đã sử dụng cổng, có thể chính là ứng dụng cũ chưa dừng.

**Cách xử lý:** Dừng phiên chạy cũ hoặc đổi cổng cho phiên mới, chẳng hạn:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=8081
~~~

Đây là cú pháp của Maven Spring Boot plugin để chuyển argument cho ứng dụng. Một lựa chọn khác sau khi đóng gói là:

~~~bash
java -jar target/demo-0.0.1-SNAPSHOT.jar --server.port=8081
~~~

Chỉ dùng một cổng mà bạn đã xác nhận còn trống. Nếu hai phiên bản chạy song song để so sánh, ghi rõ cổng nào là cũ, cổng nào là mới.

### 10.6. Nhận HTTP 404

**Triệu chứng:** Có kết nối tới server nhưng status là `404 Not Found`.

**Khả năng:** Request đi sai path, gọi sai ứng dụng, controller chưa được Spring phát hiện hoặc mapping không đúng.

**Cách xử lý:** Kiểm tra từng yếu tố: `GET` hay `POST`, `/api/greeting` có chính xác không, controller nằm trong package được component scan không, server đang nhận request trên cổng nào. Đừng kết luận lỗi ở mã trả lời chào chỉ vì một path khác trả 404.

### 10.7. Nhận HTTP 405 hoặc 400

- `405 Method Not Allowed` có thể xuất hiện khi dùng HTTP method không được route hỗ trợ, chẳng hạn gửi `POST` đến endpoint chỉ khai báo `@GetMapping`.
- `400 Bad Request` có thể xuất hiện khi Spring không thể chuyển hoặc kiểm tra tham số đầu vào theo hợp đồng handler.

Trong ví dụ `/api/greeting`, hãy dùng `GET` và tham số `name` dạng chuỗi. Nếu đang dùng Postman, kiểm tra method ở thanh chọn cạnh URL thay vì chỉ nhìn tên endpoint.

### 10.8. Nhận HTTP 500

**Triệu chứng:** Server nhận request, nhưng khi xử lý có lỗi bên trong nên trả `500 Internal Server Error`.

**Khả năng:** Method controller hoặc dependency gặp exception chưa được xử lý theo ý đồ, hoặc hạ tầng xử lý response gặp lỗi.

**Cách xử lý:** Xem stack trace và log ứng dụng tại thời điểm request, tìm exception đầu tiên có ý nghĩa và đường gọi liên quan. Sau khi sửa, build/restart và kiểm tra lại bằng cùng input.

Không nên chỉ nhìn body lỗi rồi sửa ngẫu nhiên controller; stack trace thường cho biết nơi lỗi phát sinh cụ thể hơn.

### 10.9. Build thất bại nhưng một server khác vẫn trả lời

**Triệu chứng:** Maven/Gradle báo lỗi biên dịch, nhưng `curl` vẫn nhận JSON.

**Khả năng:** Có một tiến trình ứng dụng được khởi chạy từ lần trước vẫn hoạt động. HTTP response từ tiến trình đó **không chứng minh build mới thành công**.

**Cách xử lý:** Xác định và dừng phiên chạy cũ, sửa lỗi compile rồi khởi động một phiên mới có log rõ ràng. Không dùng response của một tiến trình tồn tại từ trước để kết luận về mã vừa sửa.

### 10.10. Response có vẻ không đổi vì cache

Trong ví dụ HTTP đơn giản, nguyên nhân thường là tiến trình hoặc cổng, nhưng với ứng dụng lớn hơn, browser, proxy hoặc các lớp cache có thể khiến dữ liệu quan sát không phản ánh request mới nhất.

Khi nghi ngờ cache, thử gọi bằng `curl` trực tiếp đến địa chỉ backend đang phát triển và đối chiếu log nhận request. Đừng mặc định tắt cache là cách sửa mọi tình huống; trước tiên xác định response đến từ thành phần nào.

## 11. Dùng kết quả thực tế để khoanh vùng lỗi

Hãy đi từ dấu hiệu cụ thể theo trình tự:

~~~mermaid
flowchart TD
    A["Gửi GET /api/greeting"] --> B{"Kết nối được?"}
    B -->|Không| C["Kiểm tra tiến trình, host, port, log startup"]
    B -->|Có| D{"HTTP status?"}
    D -->|404/405| E["Kiểm tra route và HTTP method"]
    D -->|500| F["Đọc exception và log request"]
    D -->|200| G{"Body đúng phiên bản mới?"}
    G -->|Có| H["Ghi nhận thay đổi đã quan sát được"]
    G -->|Không| I["Kiểm tra save, build, restart, JAR và cổng"]
~~~

Trình tự này giảm số biến cần điều tra cùng một lúc:

- Nếu **không kết nối được**, hãy giải quyết kết nối hoặc khởi động trước; chưa thể kiểm tra nội dung.
- Nếu **kết nối được nhưng status sai**, xem route, method và log xử lý request.
- Nếu **status đúng nhưng body cũ**, tập trung vào bản build, tiến trình, cổng và file source đã lưu.
- Nếu **status và body đúng**, thay đổi cụ thể đã có bằng chứng thực tế.

Đừng sửa thêm năm chỗ cùng lúc chỉ để xem lỗi có biến mất không. Mỗi lần thay đổi nhiều yếu tố, bạn mất khả năng biết chính xác điều gì đã tạo ra kết quả.

## 12. Kiểm tra không chỉ bằng mắt: assertion cho kết quả

Với dự án nhỏ, `curl -i` đủ để học cách quan sát. Khi phải lặp đi lặp lại một phép kiểm, bạn có thể viết script hoặc automated test để tự xác nhận điều kiện thành công.

### 12.1. Kiểm tra bằng PowerShell

Trong PowerShell có thể lấy JSON thành đối tượng:

~~~powershell
$response = Invoke-RestMethod -Uri "http://localhost:8080/api/greeting?name=Lan"
$response.message
~~~

Kết quả:

~~~text
Xin chào, Lan! Đây là phiên bản đã sửa.
~~~

Bạn có thể viết điều kiện kiểm tra:

~~~powershell
$expected = "Xin chào, Lan! Đây là phiên bản đã sửa."
if ($response.message -ne $expected) {
    throw "Response khong dung gia tri mong doi."
}
Write-Output "Da xac minh response moi."
~~~

Cách này làm việc so sánh cụ thể hơn việc nhìn vào body dài và tự kết luận bằng cảm giác. Đoạn script chỉ kiểm tra **giá trị trường `message`**; nó không phải bộ kiểm thử đầy đủ cho tất cả status hay trường hợp lỗi.

### 12.2. Kiểm thử HTTP với Spring Boot

Khi đã quen các thao tác thủ công, có thể thêm `spring-boot-starter-test` vào `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo file `src/test/java/com/example/demo/GreetingControllerTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsUpdatedGreeting() throws Exception {
        mockMvc.perform(get("/api/greeting").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Xin chào, Lan! Đây là phiên bản đã sửa."));
    }
}
~~~

Sau đó chạy:

~~~bash
mvn test
~~~

`MockMvc` đi qua hạ tầng xử lý Spring MVC nhưng không cần mở HTTP port thật. Kiểm thử này giúp phát hiện nếu phần mã điều khiển response bị thay đổi ngoài dự định trong tương lai.

Cần phân biệt:

- **Manual HTTP check:** gửi request thật đến tiến trình đang chạy; xác minh bạn đang truy cập bản triển khai nào.
- **MockMvc test:** kiểm tra cách Spring MVC xử lý request trong môi trường test; hữu ích cho regression, nhưng không tự chứng minh artifact đang được triển khai ở cổng `8080` là artifact mới nhất.
- **Build thành công:** xác nhận các bước build tương ứng đã hoàn tất; không thay thế phép kiểm chức năng mà client cần.

Một dự án nghiêm túc nên kết hợp những mức kiểm tra phù hợp với rủi ro và chi phí, nhưng trong bài đầu tiên chỉ cần hiểu rõ vì sao từng phép kiểm tồn tại.

## 13. Lưu dấu vết để lần thay đổi sau dễ đối chiếu

Khi kết thúc một vòng sửa mã, nên ghi nhận ngắn gọn bốn thông tin:

| Thông tin | Ví dụ |
| --- | --- |
| Thay đổi trong source | Sửa chuỗi trả về của `GreetingController.greeting` |
| Cách đưa mã vào runtime | Dừng server cũ, chạy `mvn spring-boot:run` |
| Request đã gửi | `GET http://localhost:8080/api/greeting?name=Lan` |
| Kết quả đã quan sát | `200`, JSON `message` chứa câu “Đây là phiên bản đã sửa.” |

Đây là bằng chứng có thể diễn giải và thực hiện lại. Nếu làm việc với Git, bạn cũng có thể dùng `git diff` để xem chính xác dòng mã đã sửa trước khi commit. Đó là thao tác xem thay đổi trong repository, không trực tiếp chứng minh kết quả runtime.

Trong nhóm phát triển, ghi rõ “đã thay đổi gì và quan sát thấy gì” hữu ích hơn những câu mơ hồ như “code chạy ổn” hoặc “hình như đã cập nhật”.

## 14. Bài thực hành: tự tạo ba vòng thay đổi có thể kiểm chứng

### Thực hành 1: Thay câu trả lời

Giữ nguyên controller hiện tại. Đổi thông điệp thành:

~~~java
return new GreetingResponse(
        "Chúc bạn học Spring Boot hiệu quả, " + name + "!");
~~~

Trước khi chạy, viết ra response mong đợi cho `name=Minh`. Sau đó dừng ứng dụng, chạy lại và gửi:

~~~bash
curl -i "http://localhost:8080/api/greeting?name=Minh"
~~~

Đối chiếu status và giá trị `message` với câu đã dự đoán.

### Thực hành 2: Thay giá trị mặc định của query parameter

Đổi:

~~~java
@RequestParam(defaultValue = "Bạn") String name
~~~

thành:

~~~java
@RequestParam(defaultValue = "Người học") String name
~~~

Chạy lại và so sánh hai request:

~~~bash
curl -i "http://localhost:8080/api/greeting"
curl -i "http://localhost:8080/api/greeting?name=Minh"
~~~

Hãy giải thích vì sao request đầu đổi nội dung nhưng request thứ hai vẫn dùng tên `Minh`. Điều bạn quan sát liên hệ trực tiếp với quy tắc nhận tham số mặc định, không phải ngẫu nhiên từ Spring Boot.

### Thực hành 3: Đổi cổng bằng cấu hình

Đặt:

~~~properties
server.port=8081
~~~

Khởi động lại. Thử gọi lần lượt:

~~~bash
curl -i "http://localhost:8080/api/greeting?name=Lan"
curl -i "http://localhost:8081/api/greeting?name=Lan"
~~~

Quan sát sự khác biệt, nhưng hãy nhớ: cổng `8080` có thể vẫn được một chương trình khác sử dụng. Vì vậy, việc request cổng cũ không kết nối được hoặc trả một response khác còn phụ thuộc các tiến trình đang chạy trên máy. Tín hiệu đáng tin hơn là log khởi động ứng dụng mới cho thấy nó lắng nghe `8081`, rồi endpoint ở cổng đó trả kết quả mong đợi.

### Tự đánh giá sau mỗi lượt

Tự hỏi:

1. Mình đã sửa chính xác file nào, dòng nào?
2. File đó đã được lưu xuống ổ đĩa chưa?
3. Cơ chế nào đang chịu trách nhiệm biên dịch Java?
4. Tiến trình cũ đã dừng, mã mới đã được khởi động chưa?
5. Request sử dụng đúng host, port, method và path chưa?
6. Status và nội dung response có khớp dự đoán không?
7. Nếu không khớp, dấu hiệu nào giúp mình khoanh vùng nguyên nhân trước?

## 15. Kết nối bài học với công việc Spring Boot về sau

Ở mức dự án đầu tiên, thay đổi chỉ là một chuỗi trả về. Trong những dự án tiếp theo, cùng một vòng phản hồi được áp dụng khi:

- Sửa một validation rule rồi gửi request hợp lệ và không hợp lệ.
- Thêm service hoặc repository rồi quan sát việc ứng dụng khởi động và xử lý nghiệp vụ.
- Đổi cấu hình datasource rồi xác nhận ứng dụng kết nối cơ sở dữ liệu mong muốn.
- Thay quy tắc trả lỗi rồi kiểm tra HTTP status, error body và log.
- Tối ưu một đoạn xử lý rồi đo lường hiệu năng bằng phương pháp phù hợp.

Mỗi lần, câu hỏi không chỉ là **“mã có biên dịch không?”** mà còn là **“mã đúng có thực sự chạy và biểu hiện cụ thể nào chứng minh yêu cầu đã đạt?”**.

Một vòng làm việc đáng tin cậy là: **định nghĩa kết quả mong đợi → sửa và lưu mã → build/restart đúng tiến trình → gửi lại cùng request → kiểm tra status, body và bằng chứng liên quan**. Khi thành thạo chu trình này, bạn sẽ xử lý được phần lớn tình huống “tôi đã sửa nhưng ứng dụng vẫn như cũ” mà không phải dựa vào phỏng đoán.

