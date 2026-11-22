# Vai trò của lớp nguồn chính và @SpringBootApplication

## 1. Bức tranh tổng thể

Trong ứng dụng Spring Boot, **lớp nguồn chính** (main application class) là điểm vào quen thuộc của chương trình Java. Nó thường chứa phương thức \`public static void main(String[] args)\` và gọi \`SpringApplication.run(...)\` để khởi động Spring. Lớp này cũng thường mang annotation \`@SpringBootApplication\`, xác định nơi Spring Boot lấy cấu hình gốc, tìm các thành phần ứng dụng và kích hoạt cơ chế tự cấu hình.

Hai vai trò cần phân biệt:

- **\`main()\` cùng \`SpringApplication.run()\`**: thực sự bắt đầu quá trình khởi chạy, xây dựng và làm mới \`ApplicationContext\`, rồi đưa ứng dụng đến trạng thái sẵn sàng (nếu khởi động thành công).
- **\`@SpringBootApplication\`**: mô tả cấu hình nền cho ứng dụng Spring; bản thân annotation không tự thực thi chương trình, không tự tạo máy chủ web nếu thiếu các thư viện phù hợp.

Mô hình khởi chạy thông dụng:

~~~text
JVM thực thi main(String[] args)
  └─ SpringApplication.run(DemoApplication.class, args)
       ├─ Chuẩn bị Environment (properties, profile, tham số chạy...)
       ├─ Tạo và làm mới ApplicationContext
       ├─ Nạp cấu hình, quét bean, áp dụng auto-configuration
       ├─ Khởi tạo các bean và kết nối phụ thuộc
       ├─ Khởi động web server nhúng nếu đây là ứng dụng web
       ├─ Chạy ApplicationRunner / CommandLineRunner
       └─ Phát tín hiệu ứng dụng sẵn sàng
~~~

Đây là trình tự khái quát để hiểu vai trò từng thành phần, không phải danh sách đầy đủ mọi callback nội bộ. Nếu cấu hình hoặc bean có lỗi, tiến trình có thể dừng trước bước sẵn sàng.

## 2. Lớp nguồn chính đảm nhiệm những gì?

Một lớp chính điển hình:

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

Giải thích từng phần:

1. \`package com.example.demo;\` định vị lớp trong cấu trúc package. Package của lớp gắn \`@SpringBootApplication\` thường là gốc để quét các component bên dưới.
2. \`public static void main(String[] args)\` là entry point theo quy ước Java. Khi chạy lớp trực tiếp, JVM gọi phương thức này trước.
3. \`DemoApplication.class\` cung cấp một nguồn cấu hình chính cho \`SpringApplication\`; nhờ annotation trên lớp đó, Boot khám phá được cấu hình Spring và package khởi đầu.
4. \`args\` được chuyển tiếp để Spring Boot xử lý các tham số dòng lệnh như \`--spring.profiles.active=dev\` hoặc \`--server.port=9090\`. Không tự ý bỏ \`args\` nếu ứng dụng cần cấu hình lúc chạy.
5. \`SpringApplication.run(...)\` khởi động context và trả về một \`ConfigurableApplicationContext\`. Trong ứng dụng thông thường, không cần giữ biến kết quả; trong công cụ hoặc ứng dụng không phải web, có thể giữ để quản lý vòng đời khi có nhu cầu thực tế.

Lớp chính là **điểm tổ chức cấu hình**, không phải nơi bắt buộc phải đặt toàn bộ controller, service, repository hoặc mã nghiệp vụ. Nên giữ \`main()\` ngắn, đưa chức năng vào các bean có trách nhiệm rõ ràng. Một ứng dụng có thể có các cách bootstrap nâng cao (ví dụ \`SpringApplicationBuilder\`), nhưng ví dụ trên là cách chuẩn, dễ đọc và dễ bảo trì.

## 3. @SpringBootApplication thực chất kết hợp ba cơ chế

Về ý nghĩa, \`@SpringBootApplication\` kết hợp các annotation cốt lõi sau:

| Thành phần | Vai trò |
| --- | --- |
| \`@SpringBootConfiguration\` | Đánh dấu lớp là nguồn cấu hình Spring Boot, dựa trên cơ chế \`@Configuration\`; lớp có thể khai báo các phương thức \`@Bean\`. |
| \`@EnableAutoConfiguration\` | Cho phép Spring Boot xét các lớp tự cấu hình thích hợp, tùy theo dependency, các bean hiện có, thuộc tính và điều kiện runtime. |
| \`@ComponentScan\` | Tìm các lớp thành phần được đánh dấu như \`@Component\`, \`@Service\`, \`@Repository\`, \`@Controller\`, \`@RestController\`, \`@Configuration\` trong vùng package quét. |

### 3.1. Nguồn cấu hình: @SpringBootConfiguration

Lớp \`DemoApplication\` có thể khai báo:

~~~java
@Bean
CommandLineRunner announce() {
    return args -> System.out.println("Ứng dụng đã khởi tạo các bean");
}
~~~

Đây là **đoạn minh họa đặt bên trong một lớp cấu hình**, không phải một chương trình Java độc lập. \`@Bean\` yêu cầu import \`org.springframework.context.annotation.Bean\`; kiểu \`CommandLineRunner\` thuộc \`org.springframework.boot\`. Spring sẽ quản lý đối tượng được trả về như một bean, và Boot sẽ gọi runner sau khi context đã được khởi tạo. Với ứng dụng lớn, nên tách các cấu hình chuyên biệt sang những lớp \`@Configuration\` phù hợp.

### 3.2. Tự cấu hình: @EnableAutoConfiguration

Boot kiểm tra những gì có trên classpath và những cấu hình người viết đã khai báo để quyết định thêm bean nào. Ví dụ:

- Có thư viện web thích hợp, Boot có thể cấu hình môi trường web và máy chủ nhúng.
- Có cơ chế truy cập dữ liệu cùng cấu hình cần thiết, Boot có thể thiết lập các bean hỗ trợ truy cập dữ liệu.
- Nếu người viết đã cung cấp bean phù hợp, nhiều auto-configuration sẽ **nhường chỗ** cho bean đó theo điều kiện của chính cấu hình.

Điều này không có nghĩa mọi dependency đều biến thành bean, hay ứng dụng sẽ chạy đúng dù thiếu cấu hình bắt buộc. Mỗi auto-configuration có điều kiện riêng; cần đọc thông báo lỗi và báo cáo điều kiện khi một cấu hình không hoạt động như mong đợi. Có thể dùng tùy chọn khởi động \`--debug\` để xem báo cáo đánh giá điều kiện tự cấu hình.

### 3.3. Quét thành phần: @ComponentScan

Theo mặc định, vùng quét bắt đầu ở **package chứa lớp \`@SpringBootApplication\` và các package con**.

~~~text
com.example.demo
├─ DemoApplication.java          <- @SpringBootApplication
├─ api/
│  └─ GreetingController.java    <- được quét nếu có annotation phù hợp
├─ service/
│  └─ GreetingService.java       <- được quét
└─ repository/
   └─ ItemRepository.java        <- tùy cơ chế Spring Data / khai báo bean
~~~

Ví dụ lớp ở \`com.example.shared\` là package anh em với \`com.example.demo\`, nên **không** mặc nhiên nằm trong vùng component scan của lớp trên. Khuyến nghị đặt lớp chính tại package gốc bao trùm các thành phần của ứng dụng, ví dụ \`com.example\`, khi đúng với ranh giới module.

Cần phân biệt **component scanning** với cơ chế khám phá JPA entity và Spring Data repository. Thuộc tính \`scanBasePackages\` của \`@SpringBootApplication\` chỉ thay đổi vùng **component scan**; nó không tự đổi tất cả các package dùng cho entity hoặc repository. Khi tổ chức JPA ở package khác, cân nhắc \`@EntityScan\`, \`@EnableJpaRepositories\` và cấu hình tương ứng, tùy stack cụ thể.

Không nên đưa lớp chính vào *default package* (không khai báo \`package\`): phạm vi quét có thể trở nên quá rộng, gây hiệu ứng ngoài ý muốn và làm khó quản lý cấu trúc ứng dụng.

## 4. Ví dụ đầy đủ, chạy được với Java 17+

Mục tiêu: dùng \`@SpringBootApplication\` để Spring tìm một service trong package con, inject nó vào một runner và in thông báo khi khởi động xong.

Tạo một dự án Maven từ **Spring Initializr** (https://start.spring.io): chọn Java 17 hoặc bản JDK mới tương thích với phiên bản Spring Boot đã chọn, đặt group \`com.example\`, artifact \`demo\`, package \`com.example.demo\` và dependency **Spring Web**. Dự án được tạo đã có cấu hình build cùng Maven Wrapper. Đặt hai tệp sau:

~~~text
src/main/java/com/example/demo/
├─ DemoApplication.java
└─ greeting/
   └─ GreetingService.java
~~~

**Tệp \`src/main/java/com/example/demo/DemoApplication.java\`:**

~~~java
package com.example.demo;

import com.example.demo.greeting.GreetingService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner printGreeting(GreetingService greetingService) {
        return args -> System.out.println(greetingService.greet("Spring Boot"));
    }
}
~~~

**Tệp \`src/main/java/com/example/demo/greeting/GreetingService.java\`:**

~~~java
package com.example.demo.greeting;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Chạy trong thư mục gốc dự án:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell
.\mvnw.cmd spring-boot:run
~~~

Trong phần output, ngoài banner và các log tùy phiên bản/môi trường, chương trình sẽ in **chính xác dòng do runner tạo**:

~~~text
Xin chào, Spring Boot!
~~~

Vì đã thêm Spring Web, ứng dụng thông thường vẫn chạy để phục vụ HTTP bằng máy chủ nhúng; **không có endpoint do ví dụ này định nghĩa**, nên truy cập \`/\` có thể nhận HTTP 404 và điều đó không phải lỗi khởi động. Dừng ứng dụng bằng \`Ctrl+C\`.

**Vì sao ví dụ hoạt động?** \`@SpringBootApplication\` trên \`com.example.demo.DemoApplication\` quét được \`com.example.demo.greeting.GreetingService\`; \`@Service\` làm nó trở thành bean. Spring gọi phương thức \`@Bean printGreeting(...)\` với bean này được inject sẵn. Sau khi context được làm mới, Boot chạy \`CommandLineRunner\`, vì thế lời chào xuất hiện trong quá trình khởi động. Không có câu lệnh \`new GreetingService()\` nào trong lớp chính.

Có thể đóng gói bằng \`./mvnw package\` (Windows dùng \`.\mvnw.cmd package\`) rồi chạy archive thực thi trong \`target/\` bằng \`java -jar\`. Tên tệp JAR cụ thể phụ thuộc \`artifactId\` và \`version\` trong \`pom.xml\`; công cụ build của Spring Boot chịu trách nhiệm đóng gói các lớp và cấu hình entry point thích hợp.

## 5. Nhìn sâu hơn vào SpringApplication.run()

\`SpringApplication.run(DemoApplication.class, args)\` là cầu nối giữa entry point Java và runtime Spring Boot.

**Giai đoạn chuẩn bị:** Boot xác định loại ứng dụng (ví dụ web servlet hay không phải web) dựa trên môi trường và dependency; xử lý các nguồn cấu hình, profile, tham số dòng lệnh; chuẩn bị \`Environment\` và tạo \`ApplicationContext\` phù hợp.

**Giai đoạn nạp cấu hình:** Lớp chính cung cấp nguồn cấu hình; cơ chế component scan thu thập các bean definition trong phạm vi cho phép; auto-configuration đóng góp các bean definition nếu điều kiện được đáp ứng. Có dependency trên classpath **không đồng nghĩa** mọi bean liên quan đều chắc chắn được tạo.

**Giai đoạn làm mới context:** Spring xử lý bean factory, dependency injection, lifecycle callback và khởi tạo các singleton không khai báo lazy. Với ứng dụng web, quá trình refresh cũng bao gồm khởi tạo các thành phần web cần thiết và khởi động máy chủ nhúng. Lỗi tạo bean hoặc xung đột cấu hình ở đây có thể khiến ứng dụng thoát.

**Giai đoạn sau refresh:** Spring Boot gọi các \`ApplicationRunner\` và \`CommandLineRunner\` (nếu có), rồi thông báo ứng dụng sẵn sàng thông qua \`ApplicationReadyEvent\` khi toàn bộ chuỗi thành công. Các runner được dùng để xử lý công việc khởi động có giới hạn, không nên là nơi thực hiện tác vụ lâu dài khiến ứng dụng bị chậm sẵn sàng.

Khi ứng dụng dừng, context được đóng theo vòng đời Spring và các callback hủy bean được xử lý. Nếu cần tự quản lý context trong chương trình không có web server, API \`ConfigurableApplicationContext.close()\` có thể được dùng đúng lúc; không gọi \`close()\` ngay sau \`run()\` trong một ứng dụng web đang cần phục vụ yêu cầu.

### Một lưu ý về args và cấu hình bên ngoài

Giữ nguyên \`args\` trong lời gọi \`run\` giúp Boot đọc tham số khởi chạy. Chẳng hạn, khi chạy archive, đối số:

~~~text
--spring.profiles.active=dev
~~~

có thể chọn profile \`dev\`; đối số \`--server.port=9090\` có thể thay đổi cổng máy chủ web nếu ứng dụng có web server và không có cấu hình ưu tiên hơn. Các giá trị này đi qua hệ thống externalized configuration của Spring Boot; chúng không phải tham số truyền trực tiếp cho constructor của lớp chính. \`CommandLineRunner\` nhận mảng đối số chạy và \`ApplicationRunner\` nhận \`ApplicationArguments\` đã được phân tích.

## 6. Đặt lớp chính ở đâu cho đúng?

Cấu trúc thường dễ bảo trì:

~~~text
com.example.shop
├─ ShopApplication.java
├─ web/
├─ application/
├─ domain/
├─ infrastructure/
└─ config/
~~~

Nếu \`ShopApplication\` ở \`com.example.shop\`, component scan mặc định có thể tìm các thành phần Spring trong các package con. Lớp chính nên có một vai trò rõ ràng: tạo điểm vào, giữ annotation cấu hình gốc, và chỉ chứa cấu hình ngắn gọn thật sự gắn với bootstrap.

Trường hợp phải quét thêm package ngoài gốc, \`@SpringBootApplication\` có \`scanBasePackages\` hoặc \`scanBasePackageClasses\` để điều chỉnh. Tuy nhiên, quét quá rộng dễ kéo theo controller, service hoặc \`@Configuration\` không thuộc ứng dụng, gây trùng bean hoặc kích hoạt cấu hình ngoài ý muốn. Ưu tiên sửa cấu trúc package theo phạm vi sở hữu trước khi mở rộng quét. Với nhiều module, hãy xác định rõ module nào chịu trách nhiệm tạo bean, thay vì mặc định quét toàn bộ mã dùng chung.

**Không nhầm lẫn các vị trí sau:**

- **Entry point Java:** lớp có \`main()\`, được JVM hoặc cơ chế đóng gói chọn để thực thi.
- **Nguồn cấu hình Spring Boot:** lớp gắn \`@SpringBootApplication\`; trong dự án thông thường hai vai trò nằm cùng một lớp.
- **Bean nghiệp vụ:** service/controller/repository được Spring tạo và quản lý theo quy tắc scan hoặc cấu hình.
- **Cấu hình bên ngoài:** \`application.properties\`, \`application.yml\`, biến môi trường, tham số dòng lệnh; các nguồn này điều chỉnh cách ứng dụng chạy nhưng không thay thế điểm vào Java.

## 7. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể gặp | Hướng kiểm tra |
| --- | --- | --- |
| \`UnsatisfiedDependencyException\` / không tìm thấy service | Service không được đăng ký bean, nằm ngoài vùng quét, hoặc điều kiện tạo bean không thỏa | Kiểm tra package của lớp chính, package service, \`@Service\`/\`@Bean\` và điều kiện cấu hình |
| Có nhiều bean cùng kiểu, inject không rõ đối tượng | Component scan kéo vào nhiều implementation hoặc nhiều cấu hình khai báo cùng kiểu | Thu hẹp phạm vi quét; dùng \`@Qualifier\`/\`@Primary\` khi phù hợp |
| Ứng dụng chạy xong rồi thoát | Dự án không phải web và không còn công việc/thread giữ JVM hoạt động | Kiểm tra dependency và loại ứng dụng; chương trình batch/CLI kết thúc là bình thường |
| Port đã bị chiếm | Hai tiến trình muốn lắng nghe cùng cổng | Xem log lỗi bind, dừng tiến trình chiếm cổng hoặc cấu hình \`server.port\` khác |
| Khởi động thành công nhưng truy cập \`/\` nhận 404 | Chưa có controller mapping tương ứng, hoặc mapping khác đường dẫn | Kiểm tra \`@RestController\`, \`@RequestMapping\`/\`@GetMapping\` và đường dẫn yêu cầu |
| Auto-configuration không tạo bean dự kiến | Thiếu dependency/properties, không đủ điều kiện hoặc đã có bean thay thế | Kiểm tra dependency, cấu hình, log và báo cáo điều kiện với \`--debug\` |
| IDE chạy nhầm lớp hoặc JAR không khởi động | Run configuration chọn sai main class; gói JAR không phải executable Boot archive | Kiểm tra \`main()\`, cấu hình chạy của IDE và plugin đóng gói Spring Boot |

Một số nguyên tắc tránh lỗi:

1. **Đừng đặt \`@SpringBootApplication\` lên mọi service.** Đây là cấu hình gốc của ứng dụng, không phải annotation chung cho bean nghiệp vụ.
2. **Đừng dùng \`new\` để tạo thủ công một service rồi kỳ vọng Spring inject cho đối tượng đó.** Để Spring quản lý bean hoặc khai báo \`@Bean\` thích hợp.
3. **Đừng chuyển lớp chính sang package con tùy tiện.** Làm vậy thay đổi vùng quét mặc định và có thể khiến các bean ở package anh em biến mất.
4. **Đừng kết luận rằng annotation tự tạo server.** Có server hay không phụ thuộc vào loại ứng dụng, dependency và cấu hình runtime.
5. **Đừng mở rộng scan để chữa một lỗi mà chưa hiểu nguyên nhân.** Quét đúng package là yêu cầu về cấu trúc và ranh giới module, không chỉ là mẹo sửa lỗi.
6. **Đọc thông báo lỗi đầu tiên có nguyên nhân cụ thể.** Dòng \`APPLICATION FAILED TO START\` chỉ là dấu hiệu tổng quát; stack trace và failure analysis mới giúp xác định bean hoặc điều kiện bị lỗi.

## 8. Câu hỏi kiểm tra và bài tập

**Câu hỏi 1:** Nếu \`main()\` có nhưng lớp không gắn \`@SpringBootApplication\`, chương trình có thể chạy không?

Có thể gọi \`SpringApplication.run()\` với một nguồn cấu hình khác được thiết lập phù hợp, nhưng bạn sẽ không mặc nhiên nhận đủ ba cơ chế nêu trên từ lớp chính đó. Java vẫn thực thi \`main()\`; việc Spring Boot thiết lập context đúng hay không phụ thuộc cấu hình đã cung cấp.

**Câu hỏi 2:** \`GreetingService\` ở \`com.example.other\` có tự được tìm thấy khi lớp chính ở \`com.example.demo\` không?

Không qua component scan mặc định của \`com.example.demo\`. Cần tổ chức lại package hoặc khai báo phạm vi scan/cấu hình phù hợp. Với JPA/repository, hãy xem thêm cơ chế scan riêng của từng công nghệ.

**Câu hỏi 3:** Vì sao ví dụ có \`CommandLineRunner\` thay vì gọi trực tiếp \`greet()\` trong \`main()\`?

Runner được Spring quản lý như một bean và thực thi sau khi context đã khởi tạo; Spring inject \`GreetingService\` vào runner. Ngược lại, gọi mã nghiệp vụ trực tiếp trước \`SpringApplication.run()\` có thể xảy ra khi các bean và cấu hình Spring chưa sẵn sàng.

**Bài tập ngắn:** Di chuyển \`GreetingService\` sang một package anh em bên ngoài \`com.example.demo\` rồi quan sát lỗi inject khi khởi động. Sau đó đưa service trở lại package con hoặc cấu hình vùng quét hợp lý; giải thích thay đổi bằng quy tắc component scan thay vì chỉ nhìn vào thông báo lỗi.

## 9. Ghi nhớ

- \`main()\` là điểm bắt đầu do JVM gọi; \`SpringApplication.run()\` khởi động runtime Spring Boot.
- \`@SpringBootApplication\` kết hợp nguồn cấu hình, auto-configuration và component scan.
- **Package của lớp chính quyết định vùng component scan mặc định**; tổ chức package phù hợp là yếu tố quan trọng để ứng dụng chạy đúng.
- Auto-configuration chịu các điều kiện từ classpath, properties, bean đã tồn tại và môi trường chạy.
- Các bean, runner, server nhúng và sự kiện sẵn sàng thuộc các giai đoạn khác nhau của khởi động; xác định đúng giai đoạn giúp chẩn đoán lỗi hiệu quả.
