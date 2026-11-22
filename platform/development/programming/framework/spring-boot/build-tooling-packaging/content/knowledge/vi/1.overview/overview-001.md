# Công cụ build và đóng gói giải quyết vấn đề gì trong ứng dụng Spring Boot?

## 1. Vấn đề thực tế: từ mã nguồn đến ứng dụng có thể chạy

Một ứng dụng Spring Boot không chỉ có các tệp Java. Nó còn phụ thuộc vào Spring Framework, Spring Boot, thư viện web, JSON, JDBC, driver cơ sở dữ liệu, tệp cấu hình và tài nguyên. Khi phát triển trên máy cá nhân, IDE thường tự biên dịch và ghép classpath nên ứng dụng chạy được. Nhưng khi chuyển sang máy kiểm thử, máy chủ hoặc môi trường CI/CD, các câu hỏi xuất hiện:

- Lấy **đúng phiên bản** của từng thư viện ở đâu? Giải quyết phụ thuộc bắc cầu và xung đột phiên bản thế nào?
- Biên dịch hàng chục/hàng trăm tệp Java, xử lý resources và chạy kiểm thử theo thứ tự nào?
- Giao cho môi trường triển khai **một sản phẩm xác định** gồm mã đã biên dịch và các thư viện cần thiết bằng cách nào?
- Làm sao chạy cùng một phiên bản ứng dụng ở môi trường khác mà không phải mở IDE, tự dựng classpath hoặc biên dịch lại?
- Làm thế nào để máy CI tạo ra artifact, kiểm tra chất lượng và bàn giao cho bước phát hành theo quy trình lặp lại được?

**Build tool** như Maven hoặc Gradle giải quyết việc tự động hóa quy trình từ source đến artifact. **Spring Boot build plugin** bổ sung khả năng đóng gói phù hợp với mô hình chạy của Spring Boot, đặc biệt là executable JAR/WAR và, khi cần, OCI container image.

> Ý chính: build giúp tạo sản phẩm phần mềm một cách có kiểm soát; packaging giúp mang sản phẩm đó đến môi trường chạy theo định dạng phù hợp. Cả hai nối quá trình phát triển với kiểm thử và triển khai.

## 2. Phân biệt build, package, run và deploy

| Hoạt động | Đầu vào → đầu ra | Câu hỏi được giải quyết |
| --- | --- | --- |
| **Dependency resolution** | Khai báo dependencies → bộ thư viện theo phiên bản | Ứng dụng cần những thư viện nào để biên dịch, kiểm thử và chạy? |
| **Compile / process resources** | Java và resources → class, resources đã xử lý | Biến nguồn thành nội dung JVM có thể sử dụng thế nào? |
| **Test / verify** | Mã đã biên dịch → kết quả kiểm thử và kiểm tra | Có đủ điều kiện cho bước tiếp theo hay chưa? |
| **Package** | Class, resources, runtime dependencies → JAR/WAR hoặc image | Cần bàn giao một artifact ra sao? |
| **Run** | Artifact và cấu hình runtime → tiến trình ứng dụng | JVM/container khởi động chương trình bằng cách nào? |
| **Deploy** | Artifact/image đã chọn → một môi trường vận hành | Đưa phiên bản đó lên máy chủ, nền tảng hoặc cluster thế nào? |

Build và package là các bước chuẩn bị artifact. Chạy ứng dụng là bước khởi động tiến trình từ artifact đó; deploy còn cần hạ tầng, cấu hình, mạng, dữ liệu và chiến lược phát hành. Vì vậy **build thành công không đồng nghĩa ứng dụng chắc chắn khởi động hoặc phục vụ được yêu cầu trong production**.

## 3. Maven và Gradle giải quyết những khó khăn nào?

### 3.1. Quản lý thư viện thay cho chép JAR bằng tay

Thay vì tải từng JAR, đặt thủ công vào thư mục và tự duy trì classpath, dự án khai báo dependency theo group, tên, phiên bản hoặc để cơ chế dependency management chọn phiên bản. Maven/Gradle tải artifact từ repository, xác định phụ thuộc bắc cầu và xây classpath riêng cho compile, test, runtime.

Spring Boot cung cấp tập phiên bản thư viện tương thích thông qua **Spring Boot BOM / dependency management**. Điều này giảm nguy cơ mỗi thành viên tự chọn phiên bản Spring, Jackson, logging hoặc server khác nhau. Tuy nhiên, BOM không tự bảo đảm mọi dependency hoặc bản nâng cấp đều không có lỗi; nhóm vẫn phải kiểm thử và rà soát bảo mật.

### 3.2. Tự động hóa các công đoạn lặp lại

Một lệnh build có thể kích hoạt chuỗi công việc: xử lý resources → biên dịch → kiểm thử → tạo archive. Build tool theo dõi quan hệ phụ thuộc giữa các task/phase và báo lỗi ở bước thất bại. Không cần mỗi lập trình viên ghi nhớ hàng loạt lệnh javac hay chép thư viện bằng tay.

Maven dùng **lifecycle/phase** như compile, test, package, verify; Gradle dùng **task và dependency graph** như compileJava, test, bootJar, build. Tên và cách kích hoạt khác nhau, nhưng mục tiêu chung là mô tả quy trình dưới dạng cấu hình có thể chạy lại.

### 3.3. Chuẩn hóa giữa máy phát triển và CI

Tệp **pom.xml** hoặc **build.gradle(.kts)** là định nghĩa build được lưu cùng mã nguồn. Maven Wrapper (**mvnw**) hoặc Gradle Wrapper (**gradlew**) giúp các máy sử dụng bản công cụ build phù hợp mà dự án đã chọn. Pipeline có thể dùng cùng một lệnh như trên máy cá nhân để chạy kiểm thử, tạo artifact và lưu kết quả.

Tính lặp lại còn phụ thuộc vào phiên bản JDK, dependency repository, phiên bản plugin, biến môi trường và cấu hình build. Wrapper/BOM là nền tảng hữu ích; khi yêu cầu tái lập nghiêm ngặt, cần thêm kiểm soát phiên bản, dependency locking/verification và đầu vào build ổn định.

### 3.4. Hỗ trợ dự án lớn

Build tool mô hình hóa các module, dependencies giữa module, task dùng chung, cache và build tăng dần. Nhờ đó, khi dự án lớn lên, nhóm vẫn có quy trình tập trung để biên dịch và kiểm thử thay vì nhiều script rời rạc không nhất quán.

## 4. Vì sao Spring Boot cần cơ chế đóng gói riêng?

Một JAR Java thông thường chứa class/resources của dự án nhưng **không mặc nhiên chứa toàn bộ các JAR phụ thuộc**. Nếu chạy bằng java -jar trong khi thiếu dependency trên classpath, ứng dụng có thể gặp lỗi không tìm thấy class. Việc gửi một JAR mỏng kèm hàng chục thư viện và script khởi động là khả thi, nhưng khó bàn giao và dễ sai.

Spring Boot Maven Plugin và Gradle Plugin có thể tạo **executable archive**: JAR/WAR chứa mã ứng dụng, resources, runtime dependencies và thành phần launcher cần thiết. Khi dùng executable JAR, ta có thể khởi động bằng một lệnh:

~~~bash
java -jar ten-ung-dung.jar
~~~

Với executable JAR điển hình, cấu trúc bên trong gồm:

~~~text
ten-ung-dung.jar
├── META-INF/
├── BOOT-INF/
│   ├── classes/   # class và resources của ứng dụng
│   └── lib/       # các JAR dependency cần lúc chạy
└── org/springframework/boot/loader/...  # launcher của Spring Boot
~~~

Launcher của Spring Boot hiểu cách tải class từ các JAR lồng bên trong archive. Đây là điểm khác với việc chỉ nén tất cả tệp vào một ZIP hoặc JAR thông thường. Tên lớp launcher và chi tiết định dạng có thể thay đổi theo phiên bản Spring Boot; ý nghĩa của BOOT-INF/classes và BOOT-INF/lib vẫn là tách mã ứng dụng khỏi thư viện phụ thuộc.

**Lợi ích:** nhóm có thể lưu, kiểm thử, chuyển giao và triển khai một artifact đã được xác định, hạn chế việc môi trường nhận phải tự giải lại toàn bộ dependencies hoặc dựng classpath thủ công. Máy chạy vẫn cần một phiên bản Java tương thích và các dịch vụ/cấu hình bên ngoài mà ứng dụng sử dụng.

## 5. Các loại artifact và khi nào dùng

| Đầu ra | Đặc điểm | Trường hợp sử dụng |
| --- | --- | --- |
| **Executable JAR** | Đóng gói ứng dụng Boot cùng các runtime dependencies và launcher; thường chạy bằng java -jar | Dịch vụ Spring Boot triển khai độc lập trên VM, server hoặc container |
| **Executable WAR** | Archive dạng WAR có thể chạy trực tiếp khi cấu hình phù hợp | Ứng dụng servlet cần hỗ trợ kiểu triển khai WAR |
| **WAR triển khai lên servlet container bên ngoài** | Cần cấu hình phù hợp với container, dependencies và cách khởi tạo ứng dụng | Hệ thống bắt buộc dùng Tomcat/servlet container được quản lý riêng |
| **Plain JAR** | JAR thông thường, thường không có đầy đủ dependency/Boot launcher | Thư viện hoặc module cần được dự án khác dùng làm dependency |
| **OCI container image** | Đóng gói ứng dụng cùng runtime/container filesystem thành image | Triển khai qua Docker, Kubernetes hoặc nền tảng container |

Không phải artifact nào cũng thay thế nhau. Một **executable JAR của ứng dụng** không nên mặc định dùng làm **library JAR** cho module khác: mã của nó nằm trong BOOT-INF/classes và có cấu trúc khác plain JAR. Với ứng dụng Boot thông thường, executable JAR là lựa chọn phổ biến; WAR chỉ cần thiết khi có yêu cầu tương thích servlet container bên ngoài.

Spring Boot plugin còn hỗ trợ **layered archive**: tách lớp dependency, loader, snapshot dependency và mã ứng dụng để hệ thống tạo container image có thể tái sử dụng các lớp ít thay đổi. Layering chủ yếu cải thiện hiệu quả xây dựng/phân phối image; nó không thay thế việc kiểm thử hay cấu hình runtime.

## 6. Vai trò cụ thể của các plugin Spring Boot

Maven/Gradle phụ trách hệ thống build chung. Plugin Spring Boot cung cấp các tác vụ phù hợp với ứng dụng Boot:

| Nhu cầu | Maven + Spring Boot Maven Plugin | Gradle + Spring Boot Gradle Plugin |
| --- | --- | --- |
| Chạy khi phát triển | spring-boot:run | bootRun |
| Tạo executable JAR/WAR | package kết hợp goal repackage được cấu hình | bootJar hoặc bootWar |
| Chạy kiểm thử | test / verify theo lifecycle và test plugin | test / check / build theo task graph |
| Tạo OCI image bằng Cloud Native Buildpacks | spring-boot:build-image | bootBuildImage |

Với Maven, **repackage** xử lý archive đã được phase package tạo ra. Nếu dùng spring-boot-starter-parent và khai báo Spring Boot Maven Plugin theo cách chuẩn, execution repackage được cấu hình sẵn; nếu không dùng parent, cần cấu hình execution tương ứng. Không nên hiểu lệnh package của **mọi** dự án Maven đều tự sinh executable Boot JAR.

Với Gradle, khi áp dụng Spring Boot plugin cùng Java plugin, task **bootJar** được tạo; bootJar khác task **jar** dùng để tạo plain JAR. Tương tự, bootWar yêu cầu thiết lập WAR phù hợp. Khi xem thư mục output, hãy chọn đúng archive executable thay vì mặc định JAR nào cũng có thể java -jar.

**bootRun / spring-boot:run** phục vụ chạy ứng dụng từ project lúc phát triển. **bootJar / repackage** phục vụ tạo artifact để bàn giao. Hai việc có liên quan nhưng không phải một: chạy được từ IDE hoặc bootRun chưa chứng minh JAR cuối cùng đã đóng gói đúng.

## 7. Ví dụ xuyên suốt: từ source đến JAR chạy được

Giả sử tạo project tên **demo-build** bằng Spring Initializr, sử dụng Java 17+, thêm dependency Web phù hợp với phiên bản Spring Boot đã chọn và giữ Maven Wrapper hoặc Gradle Wrapper được tạo. Đặt lớp sau tại **src/main/java/com/example/demo/DemoApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Lớp này có phương thức main để khởi động Spring Boot và một HTTP endpoint **GET /ping** trả về chuỗi **pong**. Nó cần Spring Boot và Spring Web dependencies; không thể chỉ chạy lệnh javac thuần trên tệp này mà thiếu classpath của Spring.

**Nếu project dùng Gradle (Linux/macOS):**

~~~bash
./gradlew clean test bootJar
java -jar build/libs/demo-build-0.0.1-SNAPSHOT.jar
~~~

**Nếu project dùng Maven (Linux/macOS) và Spring Boot Maven Plugin đã cấu hình repackage:**

~~~bash
./mvnw clean verify
java -jar target/demo-build-0.0.1-SNAPSHOT.jar
~~~

Trên Windows dùng **gradlew.bat** hoặc **mvnw.cmd** tương ứng. Tên JAR nêu trên minh họa trường hợp project/artifact **demo-build** có version **0.0.1-SNAPSHOT**; hãy kiểm tra tên thực tế trong thư mục **build/libs** hoặc **target** vì nó phụ thuộc cấu hình build.

Sau khi ứng dụng đã khởi động trên cổng 8080 (nếu không cấu hình cổng khác), mở terminal thứ hai:

~~~bash
curl http://localhost:8080/ping
~~~

HTTP response body mong đợi:

~~~text
pong
~~~

Trong ví dụ, build tool đã lấy dependencies, biên dịch, chạy kiểm thử và tạo JAR; Spring Boot plugin đóng gói JAR theo cấu trúc chạy được; lệnh java -jar khởi động tiến trình trực tiếp từ artifact. Sau đó có thể đưa chính JAR đã kiểm chứng vào môi trường khác, với điều kiện Java, cấu hình và các dịch vụ phụ thuộc tương thích.

Để kiểm tra công đoạn dễ gây nhầm lẫn, hãy so sánh:

- **./gradlew bootRun**: chạy từ môi trường build/dev, không chứng minh executable JAR đã được tạo.
- **./gradlew bootJar**: tạo executable JAR; bản thân lệnh này không khởi động server.
- **java -jar ...**: chạy JAR đã đóng gói; không cần IDE, Gradle hoặc Maven trên máy chạy.
- **./mvnw package**: tạo artifact theo lifecycle; chỉ có executable Boot JAR khi cấu hình Spring Boot plugin/repackage phù hợp.

## 8. Từ JAR đến container image và CI/CD

Với OCI image, Spring Boot plugin có thể dùng **Cloud Native Buildpacks** để tạo image từ ứng dụng mà không bắt buộc phải tự viết Dockerfile:

~~~bash
./gradlew bootBuildImage
~~~

Hoặc ở dự án Maven có plugin tương ứng:

~~~bash
./mvnw spring-boot:build-image
~~~

Quá trình này cần môi trường/build service đáp ứng yêu cầu của plugin, thường bao gồm Docker daemon phù hợp và khả năng tải các builder/run images. Image sau khi tạo vẫn cần được gắn tag, đẩy đến registry và triển khai bằng quy trình riêng nếu muốn chạy ở môi trường khác. **Tạo image không tự động đồng nghĩa đã deploy production**.

Một pipeline CI/CD cơ bản có thể là:

1. Checkout đúng commit; chọn JDK và phiên bản công cụ build qua wrapper.
2. Giải dependencies; chạy biên dịch, kiểm thử và các kiểm tra được cấu hình.
3. Tạo executable JAR hoặc OCI image và xác nhận đầu ra.
4. Gắn artifact với commit/version, lưu vào artifact repository hoặc image registry.
5. Triển khai **chính artifact đó** sang các môi trường; cung cấp cấu hình, secrets và dịch vụ cần thiết ở runtime.
6. Kiểm tra health, log, kết nối phụ thuộc và khả năng phục vụ sau khi khởi động.

Điểm mạnh là tạo một đơn vị phát hành có thể truy vết. Không phải mỗi máy chủ tự build lại nguồn theo điều kiện khác nhau. Tuy nhiên, để bảo đảm cùng một artifact có thể hoạt động ở nhiều nơi, cấu hình môi trường cần được tách hợp lý khỏi mã/đầu ra build.

## 9. Những việc build và packaging không tự giải quyết

- **Cấu hình theo môi trường:** địa chỉ database, credentials, profile, endpoint phụ thuộc hoặc feature flags vẫn phải cung cấp đúng lúc chạy; tránh nhúng secrets trực tiếp vào JAR hay image.
- **Tính đúng của chương trình:** build thành công chỉ chứng minh các bước build được yêu cầu đã hoàn tất; không thay thế test tích hợp, test hiệu năng hay kiểm tra nghiệp vụ.
- **Tương thích runtime:** JAR biên dịch cho Java mới hơn có thể không chạy trên JVM cũ; môi trường còn phải có cổng, tài nguyên và dịch vụ bên ngoài đúng.
- **Bảo mật:** dependency management giúp kiểm soát phiên bản nhưng không tự phát hiện/xóa toàn bộ lỗ hổng; cần theo dõi CVE, cập nhật thư viện/base image và áp dụng kiểm tra phù hợp.
- **Vận hành:** build tool không tự cung cấp giám sát, sao lưu dữ liệu, mở rộng tải, rollback hoặc zero-downtime deployment.

Một ví dụ điển hình: JAR build PASS nhưng khi chạy ở máy chủ lại báo thiếu cấu hình datasource hoặc không kết nối được database. Đây là lỗi cấu hình/môi trường runtime, không phải bằng chứng rằng Gradle hoặc Maven đóng gói sai.

## 10. Lỗi phổ biến và cách nhận biết

| Hiện tượng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Chạy JAR báo **no main manifest attribute** hoặc không khởi động | Đang dùng plain JAR thay vì executable Boot JAR; thiếu cấu hình plugin | Chọn output bootJar/repackage và kiểm tra cấu hình main class/plugin |
| **ClassNotFoundException / NoClassDefFoundError** | Thiếu dependency runtime, cấu hình scope không đúng hoặc artifact đóng gói sai | Kiểm tra dependency tree/runtime classpath và nội dung artifact |
| Chạy được trong IDE nhưng lỗi với **java -jar** | IDE và archive dùng classpath/cấu hình khác nhau | Test trực tiếp artifact cuối cùng trong môi trường tương tự production |
| **UnsupportedClassVersionError** | JDK/JVM lúc chạy cũ hơn mức class được biên dịch | Đồng bộ Java toolchain và runtime tương thích |
| Build máy cá nhân PASS nhưng CI FAIL | JDK, wrapper, plugin, repository, biến môi trường hoặc test phụ thuộc máy khác nhau | Cố định các đầu vào, giữ wrapper trong VCS, loại phụ thuộc vào trạng thái máy |
| Có JAR nhưng HTTP endpoint không truy cập được | Ứng dụng chưa start xong, port/profile sai, service phụ thuộc lỗi hoặc network chặn | Xem log/health, cổng bind, cấu hình và môi trường |
| Image tạo được nhưng triển khai không chạy | Registry/architecture/runtime config, secrets hoặc dịch vụ phụ thuộc không phù hợp | Kiểm tra image, logs, cấu hình runtime, môi trường và readiness |

Đừng xử lý mọi lỗi khởi động bằng cách thêm bừa dependencies vào build. Hãy xác định nó xảy ra ở bước **resolve → compile → test → package → run → deploy** nào, rồi kiểm tra đầu vào và log của đúng bước đó.

## 11. Chọn công cụ và tự kiểm tra hiểu bài

**Maven hay Gradle?** Cả hai đều giải quyết quản lý dependency và tự động hóa build. Maven dùng lifecycle và cấu hình quy ước rõ; Gradle có mô hình task lập trình được và cơ chế build/cache linh hoạt. Việc chọn còn phụ thuộc chuẩn tổ chức, cấu trúc dự án và năng lực vận hành. Với Spring Boot, điểm cốt lõi là cấu hình đúng plugin và tạo đúng artifact, không phải tên công cụ.

**Ba câu hỏi tự kiểm tra:**

1. Vì sao một JAR chứa class của dự án có thể chạy trong IDE nhưng lỗi thiếu class khi đưa sang server? → IDE có thể cấp đủ runtime classpath; JAR thường không tự gói dependencies. Executable Boot JAR giải quyết đường chạy phổ biến này.
2. Tại sao chạy **bootRun** thành công vẫn nên thử **java -jar** trước phát hành? → Hai đường chạy có cách tạo classpath và dùng artifact khác nhau; cần kiểm tra sản phẩm thực sự sẽ bàn giao.
3. Tại sao phải giữ cùng artifact giữa test và production? → Giảm biến số từ thao tác build lại; nếu khác biệt, dễ khoanh vùng sang cấu hình, phụ thuộc môi trường hoặc vận hành.

**Kết luận:** Maven/Gradle biến quy trình build thành các bước có thể lặp lại và kiểm chứng; Spring Boot build plugin tạo artifact có cách chạy rõ ràng; hệ thống phát hành nhận một JAR/WAR/image có thể truy vết. Từ đó nhóm giảm lỗi quản lý dependencies, giảm thao tác thủ công và đưa ứng dụng từ máy lập trình đến môi trường thực thi nhất quán hơn.

### Tài liệu tham khảo chính thức

- Spring Boot — Executable Jar Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Spring Boot — Gradle Packaging Executable Archives: https://docs.spring.io/spring-boot/gradle-plugin/packaging.html
- Spring Boot — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot — Gradle Packaging OCI Images: https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html
