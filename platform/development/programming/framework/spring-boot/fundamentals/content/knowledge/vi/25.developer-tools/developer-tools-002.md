# Automatic restart dựa trên thay đổi classpath

Trong quá trình phát triển ứng dụng Spring Boot, lập trình viên liên tục sửa controller, service, cấu hình hoặc template rồi chạy lại để xem kết quả. Nếu mỗi lần đều phải dừng JVM, khởi chạy lại ứng dụng và đợi toàn bộ dependency được nạp, vòng lặp sửa–chạy–kiểm tra trở nên chậm chạp.

**Spring Boot DevTools** cung cấp một tính năng quan trọng: **automatic restart dựa trên thay đổi classpath**. Khi phát hiện các file trong những classpath directory được theo dõi đã thay đổi và đã ổn định, DevTools có thể đóng application context hiện tại rồi khởi động lại ứng dụng **trong cùng tiến trình JVM** bằng một classloader mới cho phần code đang phát triển.

Điểm cốt lõi không phải là “cứ lưu file Java thì Spring Boot tự biên dịch”. Automatic restart phản ứng với **thay đổi của classpath**, ví dụ file `.class` sau khi IDE build hoặc file resource sau khi được copy tới output directory. Nếu sửa source nhưng bản đã biên dịch không thay đổi, DevTools có thể không thấy điều gì cần restart.

Bài học trình bày cơ chế hoạt động, hai classloader của DevTools, cách thiết lập với Maven/Gradle và IDE, phân biệt restart với browser LiveReload và JVM HotSwap, cấu hình loại trừ và trigger file, xử lý lỗi, bảo mật môi trường production và các bài thực hành có thể tự quan sát.

## 1. Vấn đề mà automatic restart giải quyết

Giả sử một API Spring Boot có endpoint:

~~~java
@RestController
@RequestMapping("/greeting")
public class GreetingController {

    @GetMapping
    public String greeting() {
        return "Hello";
    }
}
~~~

Khi người phát triển đổi chuỗi trả về thành `"Xin chào"`, điều mong muốn là sớm gọi lại endpoint để thấy kết quả. Không có cơ chế hỗ trợ, quy trình thường là:

~~~text
Sửa GreetingController.java
          |
          v
Dừng ứng dụng đang chạy
          |
          v
Biên dịch / khởi động lại JVM
          |
          v
Đợi Spring ApplicationContext sẵn sàng
          |
          v
Gọi lại GET /greeting
~~~

Với DevTools, khi đang chạy ứng dụng ở chế độ phát triển:

~~~text
Sửa GreetingController.java
          |
          v
IDE hoặc công cụ build cập nhật file .class
          |
          v
Thư mục classpath thay đổi
          |
          v
DevTools phát hiện thay đổi, đợi file ổn định
          |
          v
Đóng context và restart bằng classloader mới
          |
          v
Gọi lại GET /greeting
~~~

Quy trình thứ hai giảm thao tác thủ công và thường nhanh hơn một lần khởi động JVM mới, vì một phần dependency không cần nạp lại từ đầu.

### 1.1. Mục tiêu và giới hạn

Automatic restart dành cho **vòng lặp phát triển local**. Nó giúp thử thay đổi code/configuration nhanh hơn, nhưng không phải:

- Công cụ triển khai hot update cho production.
- Cơ chế hot reload tùy ý mọi class bên trong JVM.
- Hệ thống biên dịch Java thay cho IDE hoặc build tool.
- Cơ chế đồng bộ source code giữa máy lập trình và server.
- Công cụ tự migrate database, giữ nguyên session hoặc trạng thái ứng dụng khi restart.
- Giải pháp thay thế việc chạy test sau khi sửa code.

Hãy xem nó là công cụ giúp **khởi tạo lại phần ứng dụng đang phát triển** khi classpath có thay đổi, không phải tính năng bảo đảm mọi trạng thái runtime được giữ nguyên.

## 2. Spring Boot DevTools là gì?

DevTools là tập công cụ hỗ trợ trải nghiệm phát triển của Spring Boot, gồm một số khả năng như:

- Automatic restart khi classpath thay đổi.
- Các mặc định dành cho development, ví dụ điều chỉnh việc cache template ở những công nghệ tương ứng.
- Tích hợp LiveReload cho browser trong điều kiện phù hợp.
- Một số tiện ích hỗ trợ quy trình phát triển khác tùy phiên bản Boot.

Dependency chính:

~~~text
org.springframework.boot:spring-boot-devtools
~~~

Trong ứng dụng Spring Boot bình thường, tính năng restart được bật khi DevTools có mặt trong môi trường chạy phù hợp và không bị tắt bởi cấu hình.

### 2.1. Vì sao gọi là restart, không phải recompile?

DevTools không đọc cú pháp Java rồi chạy `javac`. Nó quan sát **những location trong runtime classpath**, đặc biệt là thư mục chứa class/resource đã biên dịch.

Ví dụ với Maven:

~~~text
src/main/java/com/example/GreetingController.java
                     |
                  javac
                     v
target/classes/com/example/GreetingController.class
                     |
              DevTools quan sát
                     v
               Restart context
~~~

Hoặc với Gradle:

~~~text
src/main/java/com/example/GreetingController.java
                     |
            Gradle / IDE compile
                     v
build/classes/java/main/com/example/GreetingController.class
                     |
              DevTools quan sát
                     v
               Restart context
~~~

Nếu IDE đã lưu source nhưng chưa compile, file `.class` trên classpath có thể không thay đổi. Kết quả là **không có automatic restart**, dù code trong editor đã khác.

### 2.2. Classpath là gì trong ngữ cảnh này?

Classpath chứa các vị trí JVM/ClassLoader dùng để tìm class và resource khi chạy chương trình. Trong một project development, nó thường gồm:

- Thư mục class Java đã biên dịch.
- Thư mục resource đã copy đến output.
- JAR dependency của thư viện.
- Các module output directory khác nếu chúng có trong runtime classpath.

Không phải mọi vị trí đều được DevTools reload theo cách giống nhau. Thiết kế DevTools chủ yếu ưu tiên class/resource do người phát triển sửa trong những **directory**, còn thư viện JAR ổn định thường được giữ ở tầng classloader cơ sở.

## 3. Hai classloader: cơ sở của cơ chế restart nhanh

Một ý tưởng quan trọng của Spring Boot DevTools là sử dụng **hai classloader**.

~~~text
                  JVM đang chạy
                         |
                +--------+--------+
                |                 |
                v                 v
       Base ClassLoader   Restart ClassLoader
       ----------------   -------------------
       JAR dependency     Class của project
       ít thay đổi        Resource đang phát triển
                |                 |
                +--------+--------+
                         |
                         v
                 Spring ApplicationContext
                         |
                 [Thay đổi classpath]
                         |
                         v
              Context cũ được đóng
              Restart ClassLoader cũ bỏ đi
              Restart ClassLoader mới được tạo
              Context mới được khởi động
                         |
                         v
                   JVM vẫn còn
~~~

### 3.1. Base classloader

Base classloader thường chứa các thư viện ít thay đổi: các JAR dependency của Spring Framework, Spring Boot và thư viện bên ngoài.

Những class ổn định này không phải tải lại toàn bộ sau mỗi lần restart. Đó là một trong những lý do restart bằng DevTools có thể nhanh hơn kết thúc JVM rồi khởi động tiến trình mới.

### 3.2. Restart classloader

Restart classloader thường chứa class và resource của project nằm trong những classpath directory đang phát triển.

Khi có thay đổi cần restart:

1. ApplicationContext hiện tại được đóng.
2. Những thành phần lifecycle được yêu cầu shutdown theo cơ chế Spring.
3. Restart classloader cũ không còn dùng để phục vụ context mới.
4. Một restart classloader mới được tạo để thấy class/resource mới.
5. ApplicationContext mới được xây dựng và startup lại.

Mô tả này là mô hình khái quát, không phải cam kết thứ tự đóng mọi tài nguyên trong tất cả phiên bản Boot và mọi custom lifecycle.

### 3.3. Restart không phải tạo JVM mới

Khác với dừng `java` rồi chạy lại, DevTools thường restart **bên trong cùng JVM**. Vì vậy:

- Process ID có thể giữ nguyên.
- Một số class được nạp ở base classloader không cần nạp lại.
- Cơ chế khởi động Spring vẫn được thực hiện cho application context mới.
- Lifecycle listener và startup logic liên quan có thể chạy lại.
- Những tài nguyên ngoài context hoặc được giữ bởi classloader sống lâu cần được quản lý cẩn thận.

Không nên mặc định mọi static field hoặc trạng thái bên ngoài Spring đều được reset. Tính chất của state phụ thuộc classloader chứa class đó, reference còn tồn tại và cách tài nguyên được quản lý.

### 3.4. Vì sao có thể phát sinh lỗi classloader?

Hai class có cùng tên đầy đủ nhưng được nạp bởi **hai classloader khác nhau** không nhất thiết được JVM coi là cùng một type.

Trong hệ thống sử dụng reflection, Java serialization, service loader hoặc proxy phức tạp, đôi khi xuất hiện lỗi như:

~~~text
ClassCastException:
com.example.SomeType cannot be cast to com.example.SomeType
~~~

Lỗi này có thể gây ngạc nhiên vì tên class hai phía giống nhau. Một nguyên nhân khả dĩ là hai phiên bản `SomeType` được nạp từ hai classloader khác nhau.

Không phải mọi `ClassCastException` như vậy đều do DevTools. Tuy nhiên, nếu lỗi chỉ xuất hiện khi automatic restart, cần kiểm tra classloader boundary trước khi sửa logic nghiệp vụ.

## 4. Thêm spring-boot-devtools với Maven

Trong một Spring Boot Maven project, thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Dấu `optional=true` có ý nghĩa: khi module của bạn được dùng làm dependency của project khác, Maven không tự kéo DevTools tới project phụ thuộc chỉ vì module này khai báo nó.

Đối với một ứng dụng độc lập, cấu hình này giúp thể hiện DevTools là dependency dành cho phát triển chứ không phải thành phần chức năng nghiệp vụ.

### 4.1. Cách chạy

Tùy project:

~~~bash
mvn spring-boot:run
~~~

Hoặc chạy main class từ IDE.

Để thấy restart sau khi sửa Java, bảo đảm IDE hoặc Maven thực sự cập nhật output classes. Chạy `mvn spring-boot:run` không làm cho việc gõ code trong editor tự trở thành bytecode mới nếu không có công cụ nào build/copy output.

### 4.2. Có phải Java source và target/classes luôn đồng bộ?

Không. Ví dụ:

~~~text
src/main/java/com/example/MessageService.java
target/classes/com/example/MessageService.class
~~~

File Java có thể đã được lưu, nhưng file `.class` trong `target/classes` vẫn mang nội dung cũ.

Cần bật build tự động phù hợp trong IDE hoặc chủ động chạy một bước compile. Khi output file trên classpath thay đổi, DevTools mới có tín hiệu cho restart.

### 4.3. Không cần đóng gói JAR mỗi lần sửa

Đối với vòng lặp phát triển, cách chạy trực tiếp từ classpath directory thuận tiện hơn tạo full executable JAR sau mỗi lần sửa. Spring Boot DevTools được thiết kế cho workflow này.

Nếu chạy một executable JAR theo cách triển khai thông thường, DevTools thường tự vô hiệu hóa các tính năng development restart. Không nên xây quy trình production dựa vào việc thay class trong một JAR đang chạy.

## 5. Thêm spring-boot-devtools với Gradle

Với Spring Boot Gradle plugin hỗ trợ `developmentOnly`, có thể khai báo:

Gradle Groovy DSL:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    developmentOnly("org.springframework.boot:spring-boot-devtools")
}
~~~

`developmentOnly` thể hiện rõ dependency dành cho quá trình development và tránh đưa nó vào phần runtime của ứng dụng đã đóng gói theo quy ước plugin.

Có thể chạy project bằng:

~~~bash
./gradlew bootRun
~~~

Trên Windows không có shell Bash, có thể dùng:

~~~powershell
.\gradlew.bat bootRun
~~~

### 5.1. Không nhầm bootRun với continuous compilation

`bootRun` là nhiệm vụ chạy ứng dụng, còn việc source được biên dịch lại trong lúc ứng dụng đang chạy phụ thuộc IDE/build workflow.

Một IDE có thể tự cập nhật output class khi build. Trong workflow terminal, có thể cần chạy compile/classes tương ứng để làm mới classpath output. Không nên kết luận DevTools hỏng chỉ vì task chạy ứng dụng không tự phát hiện thay đổi trong source.

### 5.2. Gradle daemon và DevTools restart là hai cơ chế khác nhau

Gradle daemon giữ một tiến trình hỗ trợ build để tăng tốc các task Gradle. DevTools restart làm mới Spring application context trong JVM chạy ứng dụng.

Chúng không phải cùng một cơ chế, dù cả hai đều có thể giảm thời gian vòng lặp phát triển.

## 6. Điều gì thực sự kích hoạt automatic restart?

DevTools theo dõi classpath và so sánh trạng thái của những directory phù hợp trong các đợt kiểm tra.

Các thay đổi thường có thể kích hoạt restart:

- Một class `.class` mới được ghi vào output directory.
- Một class `.class` bị thay thế sau khi build.
- Một class được xóa khỏi output directory.
- Một resource được cập nhật ở một vị trí được theo dõi và không thuộc mẫu loại trừ restart.
- Những directory bổ sung đã được cấu hình theo dõi có thay đổi phù hợp.

Ví dụ:

~~~text
IDE: save MessageService.java
    |
    +-- Chưa compile
    |      |
    |      +--> target/classes không đổi
    |                |
    |                +--> Có thể chưa restart
    |
    +-- IDE build / compile
           |
           +--> target/classes/MessageService.class đổi
                     |
                     +--> DevTools phát hiện
                               |
                               +--> Restart
~~~

### 6.1. Thay đổi source không đồng nghĩa thay đổi classpath

Một quy tắc rất quan trọng:

> **DevTools quan sát runtime classpath, không giám sát trực tiếp mọi file source trong editor như một công cụ biên dịch.**

Với Java, muốn thay đổi hành vi, code phải được biên dịch thành class mới. Với resource, phải xem resource đang nằm ở đâu và công cụ build có copy vào output hay chưa.

### 6.2. Chờ thay đổi ổn định trước khi restart

Một lần build có thể cập nhật nhiều file liên tiếp. Nếu restart ngay khi file đầu tiên vừa thay đổi, context có thể nhìn thấy classpath chưa cập nhật xong.

DevTools có cơ chế polling và khoảng yên lặng (*quiet period*) để chờ các thay đổi ổn định rồi mới restart.

Có thể điều chỉnh:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

Hai giá trị chỉ là ví dụ. Nếu build mất thời gian ghi nhiều file, một khoảng yên lặng quá ngắn có thể dẫn tới restart khi output vẫn đang thay đổi.

Không nên tăng poll interval/quiet period tùy ý nếu chưa hiểu lý do: giá trị lớn làm chậm phản hồi khi sửa code, còn giá trị quá nhỏ có thể khiến restart nhiều lần.

## 7. Ví dụ Spring Boot đầy đủ: quan sát automatic restart

Ta tạo một ứng dụng nhỏ gồm controller và service. Mục tiêu là sửa code, compile và thấy DevTools khởi động lại context.

### 7.1. Cấu trúc project

~~~text
devtools-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/devtools/
    │   ├── DevtoolsApplication.java
    │   ├── GreetingController.java
    │   ├── GreetingService.java
    │   └── StartupReporter.java
    └── resources/
        └── application.properties
~~~

### 7.2. Dependency Maven

Trong một project Spring Boot đã có parent hoặc dependency management thích hợp, thêm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-devtools</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-web` cung cấp MVC và HTTP server trong cấu hình thông thường. `spring-boot-devtools` cung cấp hỗ trợ development restart khi chạy theo cách phù hợp.

### 7.3. Class main

`DevtoolsApplication.java`:

~~~java
package com.example.devtools;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevtoolsApplication {

    public static void main(String[] args) {
        SpringApplication.run(DevtoolsApplication.class, args);
    }
}
~~~

### 7.4. Service

`GreetingService.java`:

~~~java
package com.example.devtools;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String message(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### 7.5. Controller

`GreetingController.java`:

~~~java
package com.example.devtools;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping
    public String greet(@RequestParam String name) {
        return greetingService.message(name);
    }
}
~~~

### 7.6. In thông báo khi context startup

`StartupReporter.java`:

~~~java
package com.example.devtools;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Application context started: "
                        + System.currentTimeMillis()
        );
    }
}
~~~

`ApplicationRunner` được chạy sau khi context refresh và trước thời điểm Boot hoàn tất startup. Khi DevTools restart context, runner này được gọi lại, giúp người học quan sát một mốc startup mới.

### 7.7. Chạy và thử endpoint

Khởi động từ IDE hoặc:

~~~bash
mvn spring-boot:run
~~~

Gửi request:

~~~bash
curl "http://localhost:8080/api/greetings?name=Lan"
~~~

Kết quả kỳ vọng:

~~~text
Hello, Lan!
~~~

Đổi trong `GreetingService.java`:

~~~java
return "Xin chào, " + name + "!";
~~~

Sau khi IDE/build cập nhật `GreetingService.class` trên runtime classpath, DevTools phát hiện sự thay đổi và có thể restart.

Gọi lại endpoint:

~~~bash
curl "http://localhost:8080/api/greetings?name=Lan"
~~~

Kết quả kỳ vọng:

~~~text
Xin chào, Lan!
~~~

Nếu endpoint vẫn trả chuỗi cũ, đừng vội thêm annotation Spring. Trước tiên hãy xác nhận output class thực sự được cập nhật, và ứng dụng đang chạy từ đúng output directory.

### 7.8. Dấu hiệu nhận biết restart

Trong log có thể quan sát quá trình dừng context và startup lại. Tùy phiên bản và logging, main thread sau restart có thể được đặt tên như `restartedMain`.

Không dùng riêng chuỗi log đó làm điều kiện nghiệp vụ. Đây chỉ là một dấu hiệu chẩn đoán. Có thể quan sát số lần `StartupReporter` in ra hoặc kiểm tra response mới để xác nhận hành vi.

## 8. Cấu hình IDE để output class được cập nhật

IDE là một phần quan trọng của cơ chế restart. DevTools không thể thấy class mới nếu IDE không biên dịch class đó vào nơi ứng dụng đang sử dụng.

### 8.1. IntelliJ IDEA

Trong IntelliJ IDEA, việc lưu file không phải lúc nào cũng tự biên dịch project khi ứng dụng đang chạy. Cần bảo đảm IDE có workflow cập nhật output class phù hợp, ví dụ:

- Thực hiện `Build Project` hoặc tác vụ compile sau khi sửa Java.
- Bật cơ chế build tự động nếu phiên bản IDE và chính sách project cho phép.
- Khi cần, cấu hình để auto-make hoạt động trong lúc app đang chạy; tên thiết lập có thể khác giữa các phiên bản IntelliJ.
- Kiểm tra ứng dụng chạy bằng IntelliJ classpath hay qua delegated Gradle/Maven run, vì đường dẫn output có thể khác.

Điều cần xác minh là: sau khi build, file `.class` mà JVM đang dùng đã thực sự thay đổi chưa?

### 8.2. Eclipse và Spring Tools

Eclipse có cơ chế `Build Automatically`. Khi bật và project được cấu hình đúng, lưu Java source có thể kích hoạt compile và cập nhật output class, từ đó DevTools phát hiện thay đổi.

Nếu không restart, kiểm tra build error trước. Khi file Java không compile được, thường sẽ không có class output mới hợp lệ để DevTools nạp.

### 8.3. VS Code

Trong VS Code, hành vi cập nhật class phụ thuộc Java extension, project importer và cách chạy ứng dụng. Có thể cần compile bằng Maven/Gradle hoặc dùng workflow Java extension để tạo output mới.

Không nên giả định tính năng “auto save” của editor đồng nghĩa với “auto build” của Java project.

### 8.4. Chạy bằng terminal

Nếu chạy `mvn spring-boot:run` hoặc `./gradlew bootRun`, hãy xác định cách cập nhật class output trong khi tiến trình vẫn chạy:

- Tận dụng IDE build nhưng trỏ đúng output directory.
- Chạy compile task phù hợp khi thay đổi Java.
- Dùng workflow continuous build được project hỗ trợ nếu thật sự cần.
- Tránh hai công cụ ghi vào cùng output directory theo cách không kiểm soát, vì có thể phát sinh race hoặc build conflict.

**Mục tiêu quan sát:** file được theo dõi đã thay đổi trên runtime classpath. Cách đạt được điều đó tùy công cụ và cấu trúc project.

## 9. LiveReload và automatic restart không phải một

DevTools có thể tích hợp LiveReload, nhưng **LiveReload** và **automatic restart** là hai chức năng khác nhau.

**Automatic restart** khởi tạo lại Spring application context khi classpath thay đổi cần restart.

**LiveReload** phát tín hiệu để browser được cấu hình phù hợp có thể refresh trang, thường hữu ích sau khi sửa resource như HTML, CSS hoặc JavaScript.

~~~text
Thay đổi Java -> compile -> thay đổi .class
                                 |
                                 v
                        DevTools restart
                                 |
                                 v
                         Context chạy lại

Thay đổi static resource -> copy vào classpath
                                 |
                                 v
                        Có thể không restart
                                 |
                                 v
                        LiveReload báo browser
                                 |
                                 v
                           Browser refresh
~~~

Browser có thể cần extension/client hỗ trợ LiveReload; không phải trình duyệt nào cũng tự động kết nối chỉ vì DevTools có dependency.

### 9.1. Thay đổi static content

Các vị trí như `static`, `public`, `resources` hoặc `META-INF/resources` thường được Spring Boot DevTools áp dụng chính sách loại trừ restart mặc định đối với một số tài nguyên.

Khi những file này thay đổi, DevTools có thể không restart application context, nhưng vẫn có thể phát LiveReload trong điều kiện tương ứng.

Điều này có chủ đích: sửa CSS/JS không nhất thiết cần nạp lại toàn bộ context.

### 9.2. Thay đổi template

Với các template engine được Spring Boot hỗ trợ, DevTools có thể điều chỉnh một số default như tắt template caching trong môi trường phát triển.

Tùy template engine và cấu hình tài nguyên, khi sửa template có thể chỉ cần browser refresh hoặc LiveReload, không cần context restart.

Nếu template vẫn cũ, kiểm tra:

- Đã lưu/copy template mới vào output location chưa?
- Template engine có bật cache không?
- Request đang dùng đúng template không?
- Browser có cache tài nguyên không?
- Resource đã được xử lý như thay đổi không cần restart hay chưa?

### 9.3. Có thể tắt LiveReload

Khi không muốn DevTools chạy LiveReload server:

~~~properties
spring.devtools.livereload.enabled=false
~~~

Thuộc tính này không đồng nghĩa với việc tắt toàn bộ automatic restart. Hai chức năng có cấu hình riêng.

### 9.4. So sánh nhanh

| Hành vi | Automatic restart | LiveReload |
| --- | --- | --- |
| Đối tượng chịu tác động | Spring application context | Browser/client LiveReload |
| Trigger chính | Thay đổi classpath cần restart | Thay đổi resource phù hợp |
| Khởi động lại context? | Có | Không phải bản chất của LiveReload |
| Yêu cầu browser client? | Không | Thường có |
| Thường dùng khi | Sửa class Java, cấu hình cần restart | Sửa tài nguyên giao diện |
| Có giữ nguyên context? | Không | Có thể, nếu chỉ LiveReload |

## 10. Phân biệt với JVM HotSwap

Nhiều IDE/debugger hỗ trợ **HotSwap**: khi debug, thay một số định nghĩa class trong JVM đang chạy mà không nhất thiết restart context.

Đây là cơ chế khác automatic restart.

| Tiêu chí | DevTools restart | JVM HotSwap thông thường |
| --- | --- | --- |
| Cơ chế | Đóng context, tạo restart classloader/context mới | Định nghĩa lại class đang chạy theo khả năng JVM/debugger |
| Có restart Spring context? | Có | Không nhất thiết |
| Thay đổi cấu trúc class | Có thể được nạp lại qua classloader mới | HotSwap chuẩn thường có giới hạn đáng kể |
| Bean được tạo lại | Thông thường có | Không nhất thiết |
| Runner/lifecycle callbacks | Có thể chạy lại | Không vì riêng HotSwap |
| Cần debugger? | Không | Thường cần phiên debug/hỗ trợ tương ứng |
| Phù hợp | Development phổ thông với Boot | Vòng lặp debug cho thay đổi được hỗ trợ |

Một số plugin hoặc JVM mở rộng có thể cung cấp khả năng hot reload mạnh hơn HotSwap chuẩn, nhưng đó là hệ sinh thái công cụ khác.

### 10.1. HotSwap có thể che giấu việc context chưa được khởi tạo lại

Nếu bạn đổi logic method đơn giản và debugger HotSwap thành công, endpoint có thể trả kết quả mới mà không thấy log restart.

Đó không phải dấu hiệu DevTools lỗi. Có thể IDE đã áp dụng bytecode mới trực tiếp. Nếu bạn cần kiểm tra lại cấu hình bean hoặc lifecycle, hãy xác định có thực sự cần context restart hay không.

### 10.2. Restart không phải deploy

Dù DevTools thấy code mới ở local, quy trình production vẫn cần build/test/package/deploy phù hợp. DevTools không thay thế kiểm tra tương thích của artifact hay quy trình release.

## 11. Cấu hình loại trừ những resource không cần restart

Không phải mọi thay đổi classpath đều cần restart Spring context. Một số file tĩnh hoặc template không làm thay đổi cấu hình bean.

Spring Boot DevTools có sẵn các pattern loại trừ restart đối với một số vị trí tài nguyên, thường liên quan đến static resources, template và metadata build.

Nếu muốn bổ sung loại trừ mà không thay thế những mặc định này, dùng:

~~~properties
spring.devtools.restart.additional-exclude=generated/**,fixtures/**
~~~

Ví dụ:

~~~text
src/main/resources/
├── generated/
│   └── large-report.json
├── fixtures/
│   └── sample-data.json
└── application.properties
~~~

Khi resource output có đường dẫn phù hợp với những pattern được loại trừ, việc cập nhật chúng không nhất thiết làm restart context.

### 11.1. restart.exclude và restart.additional-exclude

Hai thuộc tính khác nhau:

- `spring.devtools.restart.exclude`: chỉ định những pattern dùng để loại trừ restart, có thể thay thế tập loại trừ mặc định.
- `spring.devtools.restart.additional-exclude`: bổ sung pattern vào các loại trừ mặc định.

Trong đa số trường hợp chỉ cần loại trừ thêm một số thư mục riêng, **ưu tiên `additional-exclude`** để giữ hành vi mặc định dành cho static assets/templates.

Ví dụ:

~~~properties
spring.devtools.restart.additional-exclude=reports/**,external-cache/**
~~~

### 11.2. Không loại trừ code cần restart

Nếu bạn loại trừ quá rộng:

~~~properties
spring.devtools.restart.exclude=**
~~~

bạn có thể khiến phần lớn thay đổi không còn kích hoạt restart như mong đợi. Đừng dùng pattern loại trừ toàn bộ trừ khi mục đích đã rất rõ ràng.

### 11.3. Loại trừ restart không có nghĩa bỏ file khỏi classpath

Một resource bị loại khỏi restart **không biến mất khỏi ứng dụng**. Nó chỉ không được dùng làm tín hiệu khởi động lại theo cơ chế tương ứng. File vẫn có thể được đọc qua `ResourceLoader` nếu nó đang ở classpath.

Điều này khác việc cấu hình Maven/Gradle loại một file khỏi build output.

## 12. Theo dõi đường dẫn bổ sung

Đôi khi ứng dụng phụ thuộc vào một thư mục ngoài classpath mà bạn muốn DevTools theo dõi khi sửa.

Có thể cấu hình:

~~~properties
spring.devtools.restart.additional-paths=/opt/myapp/shared-config
~~~

Đây là ví dụ đường dẫn cho môi trường Linux hoặc container. Trên Windows, đường dẫn phải tương ứng với filesystem của máy phát triển.

`additional-paths` cho DevTools thêm vị trí cần quan sát. Nó **không tự đưa mọi file ở thư mục đó vào Java classpath**, cũng không làm cho nội dung được bind thành Spring property nếu project không có cơ chế đọc nó.

### 12.1. Khi nào nên dùng?

- Một module dùng file cấu hình ngoài project.
- Một thư mục tài nguyên được công cụ ngoài sinh ra.
- Một phần dữ liệu phát triển nằm trong thư mục chung.
- Bạn muốn restart ứng dụng khi thay đổi file ảnh hưởng đến logic khởi tạo.

### 12.2. Khi nào không nên dùng?

Nếu có một thư mục chứa log, file cache hoặc dữ liệu thay đổi liên tục, việc theo dõi toàn bộ thư mục có thể gây restart lặp lại và làm mất nhịp phát triển.

Hãy chỉ định đường dẫn hẹp, không nên trỏ tới thư mục quá rộng như toàn bộ home directory hoặc thư mục build chứa output thay đổi thường xuyên mà không cần restart.

## 13. Trigger file: chỉ restart khi bạn chủ động kích hoạt

Có những lúc build cập nhật rất nhiều class/resource, nhưng bạn chưa muốn context restart giữa chừng. Spring Boot DevTools hỗ trợ **trigger file**: chỉ khởi động lại khi một file trigger được cập nhật theo cơ chế theo dõi phù hợp.

Cấu hình:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Tạo file trigger có tên `.reloadtrigger` ở một vị trí classpath phù hợp, ví dụ:

~~~text
src/main/resources/.reloadtrigger
~~~

Cần bảo đảm file này thực sự được copy vào runtime classpath. Một file chỉ nằm trong source resources nhưng bị build tool bỏ qua sẽ không thể trở thành trigger mà DevTools quan sát được.

### 13.1. Quy trình sử dụng

1. Sửa một hoặc nhiều class Java.
2. Compile để cập nhật output classes.
3. Chuẩn bị xong toàn bộ thay đổi muốn áp dụng.
4. Cập nhật timestamp/nội dung của trigger file trên classpath.
5. DevTools phát hiện trigger và thực hiện restart cần thiết.

Ví dụ ý tưởng:

~~~text
Sửa A.java + B.java + C.java
        |
        v
IDE/Build compile các class
        |
        v
Chưa cần restart từng lần
        |
        v
Cập nhật .reloadtrigger
        |
        v
DevTools restart một lần có chủ đích
~~~

### 13.2. Trigger file không có nghĩa gọi endpoint để restart

Đây là một cơ chế theo dõi file, không phải endpoint HTTP. Đừng tạo một API public để bất kỳ người dùng nào gửi request “restart ứng dụng” dựa trên tính năng này.

### 13.3. Một điểm dễ nhầm

Property:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

là **tên file**, không phải đường dẫn filesystem tuyệt đối. DevTools cần thấy file trigger ở nơi classpath có thể tiếp cận theo quy tắc của nó.

Nếu dùng IDE cập nhật output resource tự động, việc sửa source trigger file có thể được copy sang output. Nếu không, hãy kiểm tra đường dẫn output trước khi cho rằng DevTools bỏ qua trigger.

## 14. Tắt automatic restart khi cần

Một số tình huống phát triển cần tắt restart tạm thời:

- Debug một lifecycle race mà restart gây nhiễu.
- Chạy benchmark hoặc đo thời gian startup ổn định.
- Sử dụng thư viện có classloader behavior không tương thích.
- Phát triển với công cụ khác đã đảm nhận việc restart.
- Thử nghiệm trạng thái runtime cần tồn tại cho đến khi chủ động dừng.

### 14.1. Tắt bằng application.properties

~~~properties
spring.devtools.restart.enabled=false
~~~

Trong cách dùng này, DevTools không tiếp tục thực hiện automatic restart theo cơ chế thông thường, nhưng một số thành phần nội bộ của DevTools, bao gồm việc khởi tạo restart classloader, vẫn có thể được thiết lập tùy thời điểm/property source.

Nếu bạn cần **tắt hẳn phần restart infrastructure**, hãy thiết lập system property đủ sớm trước khi `SpringApplication.run`.

### 14.2. Tắt hoàn toàn trước khi run()

~~~java
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        System.setProperty(
                "spring.devtools.restart.enabled",
                "false"
        );

        SpringApplication.run(Application.class, args);
    }
}
~~~

Đặt system property trước khi chạy Boot giúp ngăn phần restart được kích hoạt từ đầu, phù hợp khi cần kiểm tra lỗi classloader đặc thù.

Đoạn code chỉ nên dùng khi chủ đích rõ ràng, vì nó có thể làm mất lợi ích của DevTools trong workflow phát triển.

### 14.3. Bỏ dependency khỏi môi trường không cần DevTools

Trong một số trường hợp, cách đơn giản nhất là không đưa DevTools vào runtime classpath của môi trường đó. Không nên đưa DevTools vào production chỉ để rồi dựa vào một property bảo vệ.

### 14.4. Tắt LiveReload riêng

Nếu chỉ không muốn browser refresh:

~~~properties
spring.devtools.livereload.enabled=false
~~~

Automatic restart vẫn có thể hoạt động. Ngược lại, tắt automatic restart không đồng nghĩa mọi cơ chế cache, LiveReload hoặc công cụ development khác đều tắt.

## 15. Development-only: không dùng DevTools như chiến lược production

DevTools được thiết kế cho môi trường phát triển. Spring Boot thường tự phát hiện việc ứng dụng chạy như một artifact được đóng gói hoàn chỉnh và vô hiệu hóa các tính năng DevTools dành cho development.

Điều này có nghĩa:

- Chạy bằng IDE với output directory phù hợp: DevTools restart có thể hoạt động.
- Chạy qua Maven/Gradle development task phù hợp: DevTools có thể hoạt động.
- Chạy executable archive ở môi trường production: restart từ DevTools thường không được bật theo cách phát triển.
- Muốn phát hành phiên bản mới: dùng quy trình build/test/release/deploy thay vì thay class trong artifact đang chạy.

### 15.1. Vì sao nên hạn chế dependency?

DevTools có những mặc định hướng tới sự tiện lợi khi lập trình, không phải chính sách production. Tính năng quan sát file, LiveReload và cơ chế remote development (nếu được hỗ trợ/cấu hình) đều không phải thứ bạn muốn vô tình mở trong deployment thật.

Với Maven, `optional=true` giúp hạn chế propagation qua dependency graph. Với Gradle, `developmentOnly` biểu đạt đúng ý đồ sử dụng.

### 15.2. Đừng bật remote DevTools tùy tiện

Nếu dòng Spring Boot bạn đang dùng có hỗ trợ remote DevTools, đây là cơ chế phát triển cần được bảo vệ chặt chẽ, không phải endpoint quản trị phổ thông.

Không cấu hình remote restart trên server production hoặc công khai secret/endpoint chỉ để tránh redeploy. Đối với production, hãy dùng CI/CD và cơ chế rollout phù hợp.

## 16. Cấu hình hai classloader khi phát sinh xung đột

Trong đa số dự án, DevTools tự chọn classloader hợp lý: những project output directory có thể ở restart classloader, còn JAR dependency nằm ở base classloader.

Nhưng một số ứng dụng multi-module hoặc thư viện tạo proxy/serialize object có thể cần điều chỉnh.

DevTools hỗ trợ file cấu hình đặc biệt:

~~~text
META-INF/spring-devtools.properties
~~~

Các property có tiền tố như `restart.include.` hoặc `restart.exclude.` cho phép chỉ định những classpath entry nên được xử lý bởi restart/base classloader, dựa trên pattern phù hợp.

Ví dụ minh họa:

~~~properties
restart.include.shared=/shared-library-[\\w.-]+\\.jar
restart.exclude.generated=/generated-model-[\\w.-]+\\.jar
~~~

Các pattern này áp dụng cho **classpath entry URLs**, không phải một glob tùy ý của file Java source. Biểu thức trên chỉ minh họa; khi dùng thật phải đối chiếu URL và cách đóng gói dependency của project.

### 16.1. Khi nào nên điều chỉnh include?

Nếu một thư viện/project module thay đổi thường xuyên nhưng đang ở base classloader, bạn có thể cân nhắc đưa classpath entry đó sang restart classloader để nó được nạp lại cùng application classes.

### 16.2. Khi nào nên điều chỉnh exclude?

Nếu một thành phần đặc thù không hoạt động tốt khi được nạp lại qua restart classloader, bạn có thể cân nhắc chuyển entry đó sang base classloader.

Việc thay đổi classloader có thể tác động nhiều bean, serialization type và static state. Không nên thêm include/exclude theo suy đoán nếu chưa xác định classloader là nguyên nhân.

### 16.3. Cách chẩn đoán an toàn

1. Xác định lỗi chỉ xuất hiện khi DevTools restart hay cũng xảy ra khi JVM khởi động sạch.
2. Tắt hẳn restart infrastructure đủ sớm để đối chiếu hành vi.
3. Kiểm tra classpath entry chứa class liên quan.
4. Xem object cần giao tiếp giữa hai classloader như thế nào.
5. Chỉ khi đã xác định được mismatch mới cân nhắc `spring-devtools.properties`.

Nếu một lỗi biến mất sau khi tắt restart, đó là manh mối đáng giá, nhưng chưa đủ để kết luận phải cấu hình include/exclude ngay. Có thể cần sửa resource leak, serialization boundary hoặc cách cache Class object.

## 17. Automatic restart và ApplicationContext lifecycle

DevTools restart làm context hiện tại được đóng rồi tạo lại. Do đó những callback startup có thể chạy lại.

Ví dụ:

~~~java
@Component
public class StartupInitializer implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Load reference data...");
    }
}
~~~

Sau mỗi restart, method `run(...)` có thể được gọi lại. Nếu code bên trong có side effect, ví dụ chèn dữ liệu trùng vào database, bạn cần thiết kế **idempotency**.

### 17.1. Runner không nên giả định chỉ chạy một lần trong đời JVM

Trong development với DevTools, một JVM có thể chứa nhiều application context kế tiếp. Vì vậy “một lần startup” không đồng nghĩa “một lần cho đến khi process bị kill”.

Đối với migration, seed data và tác vụ startup:

- Dùng migration tool chuyên dụng khi phù hợp.
- Thiết kế thao tác có thể chạy nhiều lần mà không gây lỗi dữ liệu.
- Phân biệt dữ liệu tạm phục vụ development và dữ liệu production.
- Không đưa side effect quan trọng vào một listener mà chỉ có ý nghĩa khi thử local.

### 17.2. @PostConstruct, @PreDestroy và @Bean lifecycle

Các callback tạo/đóng bean của context cũ và context mới có thể được gọi theo vòng đời Spring.

Một bean quản lý connection, thread pool hoặc scheduled task phải cleanup phù hợp khi context đóng, nếu không có thể còn thread/file handle giữ reference tới classloader cũ và gây memory leak.

### 17.3. Trạng thái trong bean có thể mất

Giả sử một singleton bean giữ counter:

~~~java
@Service
public class CounterService {

    private int value;

    public int next() {
        return ++value;
    }
}
~~~

Sau DevTools restart, context mới thường tạo bean mới nên counter quay về trạng thái ban đầu.

Không nên dùng in-memory singleton state để lưu dữ liệu cần giữ sau restart. Nếu dữ liệu cần bền vững, chọn storage thích hợp và kiểm soát lifecycle.

### 17.4. Static state không phải lúc nào cũng reset

Một số class được nạp bởi base classloader có thể tồn tại qua restart; static field của chúng không nhất thiết biến mất.

Không nên dựa vào “DevTools restart sẽ xóa sạch mọi static cache”, cũng không nên dựa vào “static cache chắc chắn được giữ nguyên”. Điều đó phụ thuộc classloader ownership và reference giữa các module.

## 18. Restart ảnh hưởng các kết nối và tác vụ nền ra sao?

Vì context cũ được đóng, các bean quản lý tài nguyên thường phải shutdown rồi được tạo lại:

- HTTP server và những bean web liên quan.
- Connection pool do context quản lý.
- Scheduler hoặc executor do Spring quản lý.
- Consumer của message broker.
- Cache in-memory và state của các bean.
- Resource loader, client và các bean configuration khác.

Hành vi cụ thể phụ thuộc cấu hình và lifecycle implementation.

### 18.1. Request đang chạy có thể bị ảnh hưởng

DevTools restart không nên được xem là graceful rolling deployment. Một request đang xử lý có thể bị ngắt hoặc client gặp lỗi kết nối tạm thời khi context restart.

Đây là hành vi chấp nhận được trong nhiều workflow local development, nhưng không phù hợp để phục vụ traffic production.

### 18.2. Background thread cần được quản lý

Nếu ứng dụng tạo thread thủ công:

~~~java
new Thread(() -> {
    while (true) {
        // ...
    }
}).start();
~~~

mà không có cách dừng khi context đóng, thread có thể tiếp tục sống sau restart và giữ reference tới classloader cũ.

Nên dùng executor/scheduler do Spring quản lý hoặc lifecycle component như `SmartLifecycle` khi cần điều phối shutdown đúng cách. Nếu phải tự tạo thread, cần có cancellation flag, interrupt và cleanup được gọi khi context đóng.

### 18.3. Trạng thái bên ngoài có thể vẫn tồn tại

DevTools restart không reset database, Kafka topic, Redis, file đã ghi hoặc những hệ thống ngoài ứng dụng. Vì vậy restart context không đồng nghĩa reset mọi thứ về trạng thái thử nghiệm ban đầu.

Nếu một test manual cần dữ liệu sạch, hãy dùng seed/reset strategy riêng, không dựa vào automatic restart.

## 19. Automatic restart có giúp thay đổi application.properties không?

DevTools có thể phát hiện sự thay đổi của resource cấu hình khi nó nằm trong classpath được theo dõi và không bị loại trừ restart.

Ví dụ sửa:

~~~properties
app.greeting.prefix=Hello
~~~

thành:

~~~properties
app.greeting.prefix=Xin chào
~~~

Nếu IDE/build copy file mới từ `src/main/resources/application.properties` sang output directory, thay đổi đó có thể kích hoạt restart. Khi context mới được tạo, Spring Boot nạp lại cấu hình từ các property source có hiệu lực.

Tuy nhiên cần phân biệt ba bước:

1. Bạn sửa file source configuration.
2. File thực tế trên runtime classpath được cập nhật.
3. DevTools phát hiện thay đổi và restart.

Nếu bước 2 không xảy ra, ứng dụng có thể tiếp tục dùng cấu hình cũ.

### 19.1. Externalized configuration

Nếu cấu hình nằm ngoài runtime classpath, ví dụ một file được mount từ đường dẫn riêng, DevTools không mặc nhiên theo dõi nó. Có thể cần `additional-paths` hoặc cơ chế refresh khác tùy architecture.

### 19.2. Restart khác rebinding tại runtime

Restart tạo context mới và bind lại bean configuration properties. Điều này khác một tính năng **dynamic config refresh** giữ nguyên context rồi cập nhật giá trị cho bean đang chạy.

Spring Boot DevTools không phải giải pháp quản lý cấu hình động cho production.

## 20. Những lỗi thường gặp và hướng tìm nguyên nhân

### 20.1. Đã lưu Java nhưng ứng dụng không restart

**Triệu chứng:** File source đổi, log không có restart và endpoint vẫn trả kết quả cũ.

**Nguyên nhân phổ biến:** IDE chưa compile, output `.class` không đổi.

**Cách xử lý:** Build project hoặc compile class; xác nhận file .class trên runtime classpath đã được cập nhật.

### 20.2. Đã compile nhưng vẫn không restart

Có thể:

- DevTools không có trên runtime classpath.
- Ứng dụng chạy từ packaged JAR nên development restart không hoạt động như chạy IDE.
- `spring.devtools.restart.enabled=false`.
- Build output khác với runtime classpath app đang dùng.
- File nằm trong một location không được theo dõi.
- Pattern restart exclude đã loại thay đổi.
- Trigger file được bật nhưng chưa cập nhật.

**Cách xử lý:** lần lượt kiểm tra những điều kiện trên, tránh chỉnh nhiều property cùng lúc.

### 20.3. Chỉ sửa HTML/CSS mà không thấy restart

Một số static/template resource được loại khỏi restart theo mặc định. DevTools có thể chỉ gửi LiveReload nếu môi trường hỗ trợ.

**Cách xử lý:** kiểm tra resource output, template cache và browser LiveReload. Đừng coi việc không restart context là lỗi khi chỉ thay giao diện.

### 20.4. Sửa application.yml nhưng không áp dụng giá trị mới

**Nguyên nhân:** file mới chưa được copy vào classpath, app đọc external config khác có precedence cao hơn hoặc restart chưa diễn ra.

**Cách xử lý:** kiểm tra output resource, property source có hiệu lực và cấu hình restart trigger/exclude.

### 20.5. DevTools restart liên tục

**Nguyên nhân:** một file trong path theo dõi bị cập nhật lặp lại; một công cụ sinh resource sau mỗi startup; IDE/build thay đổi nhiều file liên tiếp.

**Cách xử lý:** tìm thư mục/file biến động, giảm phạm vi theo dõi, bổ sung `additional-exclude`, cân nhắc trigger file hoặc điều chỉnh quiet period.

### 20.6. Build liên tục nhưng restart quá nhiều lần

**Nguyên nhân:** các thay đổi được ghi thành nhiều đợt, mỗi đợt cách nhau đủ lâu để được xem là ổn định.

**Cách xử lý:** cân nhắc `spring.devtools.restart.quiet-period`, trigger file hoặc workflow build áp dụng cả nhóm thay đổi một lần.

### 20.7. Lỗi ClassCastException sau restart

**Nguyên nhân khả dĩ:** hai classloader đang sở hữu các bản định nghĩa class không tương thích qua ranh giới nạp class.

**Cách xử lý:** so sánh với lần chạy không có restart, xem dependency/module placement và cân nhắc `META-INF/spring-devtools.properties` nếu cần.

### 20.8. Port vẫn bị chiếm sau khi restart

**Nguyên nhân có thể:** ứng dụng tạo server/socket ngoài Spring lifecycle, không đóng khi context cũ shutdown, hoặc một process khác đang dùng port.

**Cách xử lý:** quản lý tài nguyên qua bean lifecycle; kiểm tra process/socket đang giữ port. Đừng mặc định DevTools luôn giải phóng mọi tài nguyên tạo thủ công.

### 20.9. Startup data bị chèn trùng

**Nguyên nhân:** `ApplicationRunner` hoặc listener startup tạo dữ liệu với side effect và chạy lại ở mỗi context.

**Cách xử lý:** thiết kế idempotent initialization hoặc di chuyển migration/seed sang công cụ phù hợp.

### 20.10. Dùng JVM HotSwap và không thấy log restart

**Nguyên nhân:** debugger đã áp dụng code method mới mà không restart context.

**Cách xử lý:** phân biệt HotSwap với DevTools; nếu cần kiểm tra lifecycle mới, trigger một classpath restart thực sự.

### 20.11. DevTools vô tình được đưa vào production

**Nguyên nhân:** dependency/runtime profile được cấu hình sai hoặc build artifact được tùy chỉnh làm thay đổi cách DevTools bị loại trừ.

**Cách xử lý:** dùng Maven `optional` hoặc Gradle `developmentOnly`, giữ artifact production gọn, kiểm tra dependency composition và không dùng remote development tooling trên server thật.

### 20.12. Nghĩ restart sẽ giữ nguyên in-memory state

**Nguyên nhân:** nhầm restart context với thay đổi method implementation trên một object đang sống.

**Cách xử lý:** coi bean là có thể được tạo lại; dùng store bên ngoài cho dữ liệu cần giữ và thiết kế shutdown/reinitialization rõ ràng.

## 21. Quy trình chẩn đoán một lần restart không xảy ra

Khi sửa Java nhưng kết quả chưa thay đổi, hãy thực hiện theo một thứ tự có thể quan sát:

1. **Xác nhận app đang chạy ở chế độ development** bằng IDE, `spring-boot:run` hoặc `bootRun` phù hợp.
2. **Xác nhận DevTools có mặt trong runtime classpath** và không bị loại khỏi cấu hình chạy.
3. **Xác nhận restart được bật** và không có system property tắt sớm.
4. **Kiểm tra source compile thành công**; không có lỗi Java ngăn build.
5. **Kiểm tra output directory của class đang dùng** thay đổi sau build.
6. **Kiểm tra pattern exclusion và trigger-file** có bỏ qua thay đổi hay không.
7. **Chờ đủ polling/quiet period** và quan sát log context restart.
8. **Gọi lại endpoint hoặc tác vụ** để thấy hành vi mới.
9. **Nếu có lỗi khi restart**, thử chạy sạch không có restart để phân biệt classloader issue.
10. **Chỉ sau đó mới chỉnh tuning property** nhằm giảm latency hoặc điều chỉnh classloader.

Quy trình này giúp tránh nhầm vấn đề compile, runtime classpath và DevTools với nhau.

## 22. Quan sát thời điểm restart và tác động đến ứng dụng

Có thể thiết lập một component để ghi log mỗi khi context mới bắt đầu:

~~~java
@Component
public class RestartObservation implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(RestartObservation.class);

    @Override
    public void run(ApplicationArguments args) {
        long pid = ProcessHandle.current().pid();

        log.info(
                "Context initialized, process id = {}",
                pid
        );
    }
}
~~~

Khi DevTools restart, log startup có thể xuất hiện lại trong cùng JVM và PID thường không đổi.

Điều này giúp phân biệt với việc hệ điều hành hoặc IDE đã dừng process cũ và tạo process mới.

Nếu một startup task nạp database hoặc kết nối tới service ngoài mỗi lần, việc quan sát log cũng giúp biết tác vụ bị chạy lại bao nhiêu lần.

### 22.1. Chỉ báo bổ sung

Ngoài PID và log, có thể theo dõi:

- Timestamp mới của context startup.
- Số lần runner chạy.
- Số lần bean lifecycle method được gọi.
- Loại classloader của class trong project.
- Response từ endpoint thử nghiệm.
- Thời gian từ lúc compile đến lúc endpoint phục vụ trở lại.

Những phép quan sát này giúp hiểu tính năng, nhưng không nên biến thành logic production phụ thuộc vào DevTools.

## 23. Bài thực hành

### Bài A: Thử restart sau khi đổi một service

Tạo project với `spring-boot-starter-web` và `spring-boot-devtools`. Viết `GreetingService.message()` trả `"Hello"` và controller trả kết quả đó.

Chạy qua IDE, gọi endpoint, đổi giá trị thành `"Xin chào"`. Compile project và quan sát DevTools restart. Gọi lại endpoint để xác nhận class mới được sử dụng.

### Bài B: Chứng minh save không đồng nghĩa compile

Tắt build tự động của IDE nếu phù hợp, sửa Java source và chỉ lưu file. Quan sát ứng dụng chưa restart.

Sau đó build project, bảo đảm output `.class` thay đổi và quan sát restart. Giải thích đường đi từ source đến classpath.

### Bài C: Quan sát hai classloader

Trong một runner, in:

~~~java
System.out.println(
        GreetingService.class.getClassLoader()
);
System.out.println(
        org.springframework.boot.SpringApplication.class.getClassLoader()
);
~~~

Quan sát classloader của class ứng dụng và class framework. Sau một restart, xem phần nào có dấu hiệu được tạo lại.

Không dùng chuỗi `toString()` của classloader làm contract ổn định giữa các phiên bản Boot; chỉ dùng để minh họa.

### Bài D: So sánh Java class với static resource

Tạo:

~~~text
src/main/resources/static/site.css
~~~

Sửa CSS, cập nhật resource output, quan sát có restart context hay chỉ LiveReload. Sau đó sửa một class Java, compile và so sánh.

### Bài E: Thêm một thư mục loại trừ

Tạo thư mục:

~~~text
src/main/resources/generated/
~~~

Cấu hình:

~~~properties
spring.devtools.restart.additional-exclude=generated/**
~~~

Thay một resource trong thư mục đó và quan sát hành vi. So sánh với việc thay một class `.class` thuộc project.

### Bài F: Trigger file

Bật:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Tạo trigger file trên classpath, compile nhiều thay đổi Java rồi cập nhật trigger một lần. Quan sát DevTools có restart đúng lúc bạn chủ động kích hoạt hay không.

### Bài G: Tắt restart qua hai cách

Thử:

~~~properties
spring.devtools.restart.enabled=false
~~~

Sau đó thử đặt system property trước `SpringApplication.run`. So sánh hành vi và giải thích vì sao cách thứ hai hữu ích khi cần loại bỏ cả restart classloader infrastructure.

### Bài H: Quan sát state và runner

Tạo singleton `CounterService` chứa counter tăng dần và `ApplicationRunner` ghi timestamp. Gọi endpoint làm counter tăng, sau đó thay class và restart.

Quan sát bean state và runner. Giải thích vì sao restart không có nghĩa dữ liệu trong database cũng bị reset.

### Bài I: Kiểm tra đóng gói ứng dụng

Chạy project theo development workflow rồi đóng gói một executable JAR và chạy bằng `java -jar` theo cách thông thường.

So sánh DevTools behavior và giải thích vì sao cơ chế tự restart không được dùng làm chiến lược cập nhật production.

### Bài J: Chẩn đoán restart loop

Tạo một file được cập nhật định kỳ dưới một watched path trong môi trường thử nghiệm. Quan sát nhiều lần restart; sau đó loại thư mục khỏi restart hoặc dùng trigger file.

Không thực hiện thí nghiệm gây restart liên tục trên môi trường phục vụ người dùng thực.

## 24. Câu hỏi tự kiểm tra

**1. Automatic restart dựa trên thay đổi nào?**

Dựa trên thay đổi được DevTools phát hiện ở những classpath location hoặc additional paths được theo dõi, không đơn thuần dựa trên việc lưu `.java` trong editor.

**2. DevTools có tự biên dịch Java source không?**

Không. IDE hoặc build tool phải cập nhật class output để DevTools thấy bytecode mới.

**3. Vì sao restart thường nhanh hơn khởi động JVM mới?**

DevTools thường giữ lại base classloader cho dependency ổn định và chỉ tạo lại restart classloader/context cho phần đang phát triển.

**4. Restart có tạo tiến trình Java mới không?**

Thông thường không. Context được restart trong cùng tiến trình JVM.

**5. Khi nào thêm dependency `spring-boot-devtools`?**

Trong môi trường phát triển muốn có restart và các tiện ích DevTools. Với Maven thường khai báo `optional=true`; với Gradle có thể dùng `developmentOnly`.

**6. Vì sao sửa CSS không luôn khiến context restart?**

Một số static resources được loại khỏi restart theo mặc định; thay đổi đó có thể chỉ kích hoạt LiveReload/browser refresh.

**7. LiveReload có phải DevTools restart không?**

Không. LiveReload chủ yếu phục vụ refresh browser, còn restart tái khởi tạo Spring context.

**8. JVM HotSwap khác automatic restart thế nào?**

HotSwap có thể định nghĩa lại class đang chạy với những giới hạn của JVM/debugger, còn DevTools restart tạo context và restart classloader mới.

**9. `spring.devtools.restart.additional-exclude` có mục đích gì?**

Bổ sung những pattern không nên kích hoạt context restart mà vẫn giữ các loại trừ mặc định.

**10. `spring.devtools.restart.trigger-file` dùng để làm gì?**

Cho phép chỉ restart theo cơ chế trigger file khi các thay đổi đã sẵn sàng, tránh restart giữa nhiều đợt build.

**11. `spring.devtools.restart.enabled=false` có luôn loại bỏ mọi cơ chế restart classloader không?**

Không nên mặc định như vậy nếu property chỉ được đọc ở thời điểm ứng dụng khởi tạo. Muốn tắt hoàn toàn hạ tầng restart, đặt system property đủ sớm trước khi `SpringApplication.run`.

**12. Vì sao có thể thấy lỗi class cast chỉ sau DevTools restart?**

Vì một số class có thể bị nạp qua các classloader khác nhau ở hai thế hệ context, làm type identity không tương thích ở ranh giới classloader.

**13. @PostConstruct hoặc ApplicationRunner có chạy lại không?**

Chúng có thể chạy lại khi context mới tạo bean và khởi động. Cần thiết kế startup side effect idempotent.

**14. DevTools restart có xóa dữ liệu database không?**

Không. Restart context không tự reset external storage.

**15. Có nên bật remote DevTools trên production không?**

Không. DevTools là công cụ development, không phải cơ chế deployment hoặc quản trị production.

## 25. Kết luận

**Automatic restart dựa trên thay đổi classpath** là một tính năng phát triển hữu ích của Spring Boot DevTools. Khi code Java được compile hoặc resource được copy vào vị trí classpath đang theo dõi, DevTools có thể phát hiện thay đổi, đợi output ổn định rồi đóng và khởi động lại Spring application context trong cùng JVM.

Cơ chế hai classloader giải thích vì sao restart thường nhanh hơn khởi chạy một JVM mới: dependency JAR ổn định có thể nằm trong base classloader, còn class của project được nạp lại qua restart classloader. Tuy vậy, nó cũng lý giải các rủi ro classloader mismatch, state trong bean bị reset và startup callback có thể chạy lại.

Khi sử dụng DevTools, hãy nhớ các phân biệt quan trọng:

- **Lưu source không đồng nghĩa compile:** restart cần thấy thay đổi ở runtime classpath.
- **Automatic restart không giống LiveReload:** một bên khởi động lại context, một bên chủ yếu refresh browser.
- **Automatic restart không giống JVM HotSwap:** một bên tạo context/classloader mới, một bên có thể định nghĩa lại class đang chạy.
- **Restart không phải production deploy:** không dùng DevTools để cập nhật ứng dụng đang phục vụ người dùng.
- **Cấu hình phải có chủ đích:** dùng `additional-exclude`, `additional-paths`, `trigger-file`, `poll-interval` và `quiet-period` khi thật sự cần.

Hiểu đúng ranh giới giữa editor, compiler, classpath, classloader và application context giúp bạn tận dụng Spring Boot DevTools để rút ngắn vòng lặp phát triển mà không nhầm lẫn các vấn đề build, runtime hay deployment.

