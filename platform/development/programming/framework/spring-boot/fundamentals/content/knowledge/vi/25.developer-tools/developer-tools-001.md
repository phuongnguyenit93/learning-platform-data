# Spring Boot Devtools và phạm vi dependency khi phát triển

Trong lúc phát triển ứng dụng Spring Boot, lập trình viên thường chỉnh sửa Java, HTML, template, CSS và cấu hình nhiều lần. Nếu mỗi thay đổi đều phải dừng tiến trình, build lại toàn bộ JAR rồi chạy thủ công, vòng phản hồi sẽ chậm. **Spring Boot Devtools** là tập công cụ dành cho giai đoạn phát triển để rút ngắn chu trình sửa code → quan sát kết quả.

Tuy nhiên, Devtools khác với một thư viện nghiệp vụ thông thường. Nó điều chỉnh hành vi của ứng dụng khi đang chạy trên máy phát triển, có cơ chế theo dõi classpath, tự khởi động lại context và thay đổi một số thiết lập mặc định. Vì vậy, ngoài cách sử dụng, cần hiểu rõ **phạm vi dependency** để Devtools có mặt khi phát triển nhưng không vô tình trở thành một thành phần vận hành trong production.

## 1. Spring Boot Devtools là gì?

Dependency chính là:

~~~text
org.springframework.boot:spring-boot-devtools
~~~

Khi được thêm vào classpath của một ứng dụng đang chạy theo chế độ phát triển, Devtools cung cấp một số tiện ích:

- **Automatic restart:** phát hiện những thay đổi thích hợp trên classpath và khởi động lại ứng dụng.
- **LiveReload:** cung cấp một LiveReload server để trình duyệt tương thích có thể tải lại trang khi tài nguyên thay đổi.
- **Development-time defaults:** điều chỉnh một số cấu hình mặc định thuận tiện cho quá trình phát triển, ví dụ giảm caching của template hoặc cung cấp thông tin chẩn đoán hữu ích.
- **Điểm cấu hình restart:** cho phép loại trừ thư mục, theo dõi đường dẫn bổ sung hoặc dùng trigger file để kiểm soát thời điểm khởi động lại.

Devtools không thay thế compiler, build tool hay IDE. Nó cũng không phải Java HotSwap thuần túy: khi thay đổi classpath cần restart, Spring Boot có thể tạo lại ApplicationContext, đăng ký bean và chạy lại các bước khởi tạo.

Các hành vi trên chủ yếu có ý nghĩa trong **vòng lặp phát triển tại máy lập trình**. Production thường cần artifact bất biến, lifecycle được kiểm soát và không có thành phần theo dõi thay đổi source code.

## 2. Phân biệt restart, LiveReload và build

Ba thao tác thường bị gọi chung là “tự reload”, nhưng thực tế khác nhau.

| Cơ chế | Điều kích hoạt | Kết quả |
|---|---|---|
| IDE/compiler | Lưu, build hoặc compile source | Ghi class/resource mới vào output directory |
| Devtools restart | Thay đổi phù hợp trên classpath đã được theo dõi | Khởi động lại phần ứng dụng bằng restart classloader |
| LiveReload | Một thay đổi tài nguyên có thể phát tín hiệu reload | Trình duyệt tương thích tải lại trang |

Ví dụ, bạn chỉnh một lớp Java:

~~~java
@RestController
@RequestMapping("/hello")
public class HelloController {

    @GetMapping
    public String hello() {
        return "Hello from Devtools";
    }
}
~~~

Đổi chuỗi trả về rồi **compile class** để output classpath được cập nhật. Devtools phát hiện thay đổi và thực hiện restart. Sau khi restart hoàn tất, request mới sẽ dùng phiên bản class mới.

Nếu chỉ lưu file `HelloController.java` mà IDE không biên dịch, `HelloController.class` trong output directory có thể chưa đổi. Devtools theo dõi classpath chứ không phải tự biên dịch mọi file nguồn Java; vì vậy chưa chắc có restart.

Ngược lại, khi bạn chỉnh một file CSS trong `static/`, browser có thể cần reload để thấy giao diện mới, nhưng thường không cần khởi tạo lại toàn bộ ApplicationContext.

## 3. Thêm Devtools bằng Gradle: developmentOnly

Với ứng dụng Spring Boot sử dụng Gradle plugin của Spring Boot, cách khai báo được khuyến nghị là cấu hình **`developmentOnly`**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Trong ví dụ, các chuỗi phiên bản là chỗ điền phiên bản plugin thực tế của dự án, không phải version có thể chạy nguyên xi.

Nếu dùng Gradle Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "<spring-boot-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    developmentOnly("org.springframework.boot:spring-boot-devtools")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

`developmentOnly` thể hiện rằng Devtools phục vụ quá trình phát triển. Cấu hình được Spring Boot Gradle plugin hỗ trợ để dependency có mặt ở classpath khi chạy ứng dụng theo workflow phát triển phù hợp, nhưng không tự được đưa vào executable archive tạo bằng `bootJar` hoặc `bootWar` theo cách đóng gói tiêu chuẩn.

### Vì sao không nên đặt vào implementation?

Một dependency `implementation` là một phần của mô hình dependency chính của ứng dụng. Devtools không cung cấp API nghiệp vụ mà code production cần gọi và không nên trở thành runtime dependency được đóng gói vào ứng dụng triển khai.

Khai báo:

~~~groovy
developmentOnly 'org.springframework.boot:spring-boot-devtools'
~~~

diễn đạt ý định rõ hơn:

- Lập trình viên có Devtools khi chạy trong workflow phát triển.
- Build tool có thể xử lý dependency khác với các thư viện runtime thực sự.
- Việc đóng gói deployment không cần mang theo cơ chế tự restart dành cho IDE.

Đừng nhầm `developmentOnly` với Spring profile `dev`: đây là **Gradle dependency configuration ở build time**, không phải active profile của Spring ApplicationContext.

### Nếu dự án không dùng Spring Boot Gradle plugin?

`developmentOnly` không phải một cấu hình mặc định luôn tồn tại trong mọi project Gradle. Nó được cung cấp và tích hợp bởi plugin Spring Boot phù hợp. Với build script tự định nghĩa, cần kiểm tra chính xác cấu hình dependency nào được dùng trong classpath chạy ứng dụng và archive đóng gói.

Không nên sao chép `developmentOnly` vào một project Gradle thuần rồi mặc định Gradle sẽ hiểu cấu hình này nếu chưa có plugin hoặc định nghĩa cấu hình tương ứng.

## 4. Thêm Devtools bằng Maven: optional dependency

Trong dự án Maven, cách khai báo thông dụng là:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-devtools</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

Phần tử `<optional>true</optional>` rất quan trọng. Với Maven, nó cho biết dependency là **optional đối với project sử dụng thư viện chứa khai báo đó**; các project phụ thuộc transitively không tự kéo Devtools vào như một dependency bắt buộc.

Điểm cần phân biệt:

- `optional` là cơ chế của Maven để kiểm soát **transitive dependency**.
- Nó **không phải** Spring profile, không tự bật profile `dev`.
- Nó **không có nghĩa** Devtools bị loại khỏi mọi classpath của chính project đang khai báo.
- Việc loại Devtools khỏi executable JAR còn liên quan cấu hình repackaging của Spring Boot Maven Plugin.

Với Maven, Spring Boot Maven Plugin mặc định loại Devtools khỏi artifact đã `repackage` (trừ khi dự án cố ý thay đổi hành vi này). Nhờ vậy, `mvn spring-boot:run` trong môi trường phát triển có thể sử dụng Devtools, còn executable JAR để triển khai không cần đóng gói nó.

### Scope runtime có được không?

Nếu code chính không import API của Devtools, có thể khai báo rõ phạm vi runtime:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <scope>runtime</scope>
    <optional>true</optional>
</dependency>
~~~

`runtime` cho biết dependency không cần ở compile classpath nhưng có thể dùng khi chạy. `optional` vẫn có nhiệm vụ kiểm soát sự lan truyền transitive sang project phụ thuộc.

Tuy nhiên, không nên nhầm khái niệm **Maven runtime scope** với **môi trường production**. Trong Maven, một runtime dependency có thể được đưa vào runtime classpath; việc loại nó khỏi executable archive là trách nhiệm của packaging/plugin hoặc quy trình build tương ứng.

## 5. So sánh phạm vi dependency trong Gradle và Maven

| Mục đích | Gradle | Maven |
|---|---|---|
| Thêm Devtools cho phát triển | `developmentOnly` khi dùng Boot Gradle plugin | Dependency `spring-boot-devtools` với `optional=true` |
| Tránh kéo Devtools transitively sang project khác | Phụ thuộc vào mô hình cấu hình và publishing của Gradle | `<optional>true</optional>` |
| Không đưa vào executable archive | Boot Gradle plugin xử lý `developmentOnly` theo cách đóng gói tiêu chuẩn | Spring Boot Maven Plugin mặc định exclude Devtools khi repackage |
| Chạy ứng dụng từ build tool | `bootRun` | `spring-boot:run` |
| Đóng gói executable JAR | `bootJar` | `package` kết hợp `repackage` của Boot plugin |

Điều quan trọng là không gán hai hệ thống dependency scope cho nhau theo tên. Maven không có `developmentOnly` chuẩn giống Gradle plugin của Spring Boot; Gradle cũng không dùng `optional=true` với cùng ý nghĩa khai báo trong POM.

Dù dùng build tool nào, hãy giữ quy tắc: **Devtools là phụ thuộc dành cho developer, không phải một thành phần cần thiết của ứng dụng khi triển khai**.

## 6. Devtools hoạt động như thế nào với hai classloader?

Automatic restart của Devtools dựa trên hai nhóm classloader:

1. **Base classloader:** thường chứa các thư viện ít thay đổi, ví dụ những dependency JAR từ bên thứ ba.
2. **Restart classloader:** thường chứa class và resource đang phát triển của ứng dụng trong output directory.

Khi thay đổi phù hợp được phát hiện, Devtools không cần tải lại mọi dependency JAR. Nó có thể đóng phần context cũ, loại bỏ restart classloader cũ, rồi tạo restart classloader mới để nạp code ứng dụng đã thay đổi.

~~~text
Lần khởi chạy đầu
     |
     +--> Base classloader
     |      +--> Spring Framework
     |      +--> Các thư viện bên thứ ba
     |
     +--> Restart classloader #1
            +--> Controller
            +--> Service
            +--> Application configuration
                     |
                 Classpath đổi
                     |
                     v
              Đóng context cũ
                     |
                     v
           Restart classloader #2
            +--> Controller mới
            +--> Service mới
            +--> Configuration mới
                     |
                     v
           Tạo ApplicationContext mới
~~~

Vì base classloader thường được giữ lại, restart có thể nhanh hơn một cold start toàn bộ JVM.

### Restart không phải giữ nguyên toàn bộ state

Spring singleton được tạo lại khi ApplicationContext restart. Những trạng thái chỉ tồn tại trong memory của bean có thể bị mất. Các kết nối, scheduler và resource được Spring quản lý cần được dừng hoặc giải phóng đúng lifecycle; tránh giữ state trong static singleton hoặc thread tự tạo không được quản lý.

Nếu đang xử lý tác vụ dài, một lần restart có thể làm gián đoạn tác vụ. Trong môi trường phát triển, đây thường là đánh đổi chấp nhận được, nhưng không nên hiểu restart là cơ chế nâng cấp phiên bản không gián đoạn.

### Một số vấn đề với classloader

Trong dự án multi-module, một số module có thể bị đưa vào base classloader thay vì restart classloader, khiến thay đổi của module đó không xuất hiện như mong đợi sau restart. Một số thư viện dùng reflection, serialization hoặc lưu trữ class reference trong static state cũng có thể nhạy cảm với ranh giới classloader.

Khi gặp lỗi classloader khó giải thích, có thể thử chạy ứng dụng không có restart để phân biệt lỗi nghiệp vụ với lỗi do restart classloader; sau đó điều chỉnh restart include/exclude nếu thật sự cần.

## 7. Chạy Devtools trong IDE

Một workflow thông dụng:

1. Thêm dependency Devtools đúng scope.
2. Đồng bộ Maven/Gradle project.
3. Chạy main class có `@SpringBootApplication` trong IDE.
4. Sửa một lớp Java.
5. Để IDE compile code thành class mới trong output directory.
6. Devtools quan sát classpath và restart ứng dụng.

Ví dụ main class:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Trong IntelliJ IDEA, thao tác build project hoặc cơ chế build tự động được bật theo cấu hình IDE có thể cập nhật output classes. Trong Eclipse, cơ chế tự động build thường giúp các class được biên dịch khi file nguồn thay đổi.

Tên menu và hành vi cụ thể có thể khác nhau theo phiên bản IDE. Điểm ổn định là **Devtools phải nhìn thấy sự thay đổi của compiled class/resource trên classpath**, không chỉ thay đổi source file chưa được biên dịch.

### Khi chạy bằng Gradle

Với Spring Boot Gradle plugin:

~~~bash
./gradlew bootRun
~~~

Trong quá trình phát triển, `bootRun` sử dụng classpath của ứng dụng và có thể có Devtools khi dependency được khai báo `developmentOnly` đúng cách. Tuy nhiên, bản thân lệnh `bootRun` không biến Gradle thành một trình biên dịch liên tục mọi source thay đổi trong lúc task đang chạy.

Bạn vẫn cần workflow cập nhật output classpath, chẳng hạn IDE build hoặc một cơ chế build phù hợp. Khi thay đổi Java không được biên dịch, không nên đợi Devtools tự compile source thay Gradle.

### Khi chạy bằng Maven

Có thể chạy:

~~~bash
mvn spring-boot:run
~~~

Maven plugin chạy ứng dụng từ project thay vì chỉ chạy executable JAR đã đóng gói. Với dependency Devtools hiện diện, automatic restart có thể hoạt động khi compiled classes/resources thay đổi.

Maven compile hay IDE build vẫn là phần riêng của vòng làm việc. Nếu không có thay đổi trên classpath, Devtools không có tín hiệu để restart.

## 8. File tĩnh và template thường không cần restart context

Trong ứng dụng web, các tài nguyên thuộc những đường dẫn phổ biến như:

~~~text
/META-INF/maven
/META-INF/resources
/resources
/static
/public
/templates
~~~

thường được Devtools xem là tài nguyên có thể thay đổi mà **không cần khởi động lại ApplicationContext**. Thay đổi của chúng có thể tạo tín hiệu LiveReload hoặc được phục vụ trực tiếp theo cấu hình phát triển.

Ví dụ:

~~~text
src/main/resources/
├── static/
│   ├── css/site.css
│   └── js/site.js
└── templates/
    └── home.html
~~~

Khi sửa `site.css`, web server không nhất thiết phải tạo lại các bean. Nếu file resource được cập nhật trong vị trí mà runtime theo dõi, browser có thể reload để đọc CSS mới.

Một số template engine vốn cache template đã xử lý. Devtools áp dụng các development-time defaults giúp giảm caching cho những integration phù hợp, vì vậy thay đổi template có thể xuất hiện mà không cần restart.

**Không đồng nhất điều này với hot-module replacement của frontend bundler.** LiveReload thường yêu cầu reload trang hoặc tài nguyên trong browser; nó không tự thay thế một JavaScript module đang chạy mà vẫn giữ nguyên mọi state như một hệ thống frontend HMR chuyên dụng.

## 9. LiveReload: khi nào trình duyệt tự làm mới?

Devtools có thể khởi động một LiveReload server khi ứng dụng phát triển chạy. Trình duyệt cần extension, client hoặc công cụ tương thích để nhận tín hiệu và tự reload.

Có thể tắt LiveReload:

~~~yaml
spring:
  devtools:
    livereload:
      enabled: false
~~~

Tắt LiveReload không có nghĩa automatic restart cũng bị tắt. Đây là hai cơ chế riêng: restart xử lý phần ứng dụng Java/context, còn LiveReload giúp trình duyệt quan sát thay đổi.

Nếu browser không tự cập nhật, nên phân biệt:

- Devtools có phát hiện thay đổi resource không?
- Ứng dụng có cần restart context hay chỉ cần reload trang?
- LiveReload server có được bật không?
- Trình duyệt có client tương thích và đã kết nối không?
- Browser cache hoặc frontend build pipeline có giữ phiên bản tài nguyên cũ không?

LiveReload có ích trong vòng lặp phát triển web, nhưng không thay thế việc kiểm thử giao diện ở điều kiện production.

## 10. Kiểm soát automatic restart

Devtools cho phép điều chỉnh việc theo dõi thay đổi để giảm restart không cần thiết.

### Tắt restart bằng configuration property

Nếu muốn giữ các tiện ích Devtools khác nhưng không tự restart, có thể cấu hình:

~~~yaml
spring:
  devtools:
    restart:
      enabled: false
~~~

Thiết lập này ngăn automatic restart. Tuy nhiên, Spring Boot có thể vẫn khởi tạo cơ chế restart classloader ở giai đoạn sớm ngay cả khi property trong config file đã đặt thành `false`.

Nếu cần vô hiệu hóa toàn bộ restart support rất sớm, đặt system property **trước khi** gọi `SpringApplication.run()`:

~~~java
@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        System.setProperty(
                "spring.devtools.restart.enabled",
                "false"
        );

        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Có thể truyền system property khi chạy JVM thay vì hard-code:

~~~bash
java -Dspring.devtools.restart.enabled=false -jar app.jar
~~~

Trong ví dụ cuối, hành vi còn phụ thuộc Devtools có thực sự hiện diện và được kích hoạt trong runtime tương ứng hay không. Với một executable JAR production chuẩn, Devtools thường vốn đã không được đóng gói.

### Loại trừ những đường dẫn không nên restart

Có thể thêm các pattern loại trừ:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: logs/**,generated/**
~~~

`additional-exclude` cho phép bổ sung pattern loại trừ vào danh sách mặc định. Cách này phù hợp khi ứng dụng ghi file log hoặc resource sinh tự động vào khu vực runtime có thể theo dõi và làm restart quá thường xuyên.

Không nên dùng `exclude` để thay toàn bộ danh sách mặc định nếu mục tiêu chỉ là bổ sung vài path; sử dụng `additional-exclude` giúp giữ được các rule mặc định hữu ích.

### Theo dõi một thư mục bổ sung

Trong một số dự án, resource cần theo dõi nằm ngoài các classpath entry thông thường:

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-config
~~~

Cần bảo đảm đường dẫn có ý nghĩa với working directory của tiến trình và Devtools có thể truy cập. Khi thay đổi được phát hiện, xử lý restart hay LiveReload còn tùy phần đường dẫn đó có thuộc loại bị loại trừ khỏi restart hay không.

### Trigger file: chủ động chọn lúc restart

Trong một dự án lớn, IDE có thể compile từng class trong nhiều đợt. Nếu Devtools restart ngay sau mỗi đợt cập nhật, các restart liên tục gây gián đoạn.

Có thể sử dụng trigger file:

~~~yaml
spring:
  devtools:
    restart:
      trigger-file: .reloadtrigger
~~~

Tạo một file có tên `.reloadtrigger` trong classpath; sau khi bạn hoàn tất nhiều thay đổi, cập nhật timestamp của file này để Devtools kiểm tra các thay đổi và thực hiện restart nếu phù hợp.

Ý nghĩa của trigger file là **điều khiển thời điểm đánh giá thay đổi**, không phải thay thế compiler. Các class vẫn phải được build trước đó.

## 11. Development-time defaults và caching

Devtools còn cung cấp các giá trị mặc định thuận tiện trong môi trường phát triển. Ví dụ, khi làm việc với một số template engine, việc cache template có thể được tắt theo mặc định của Devtools để thay đổi file hiển thị nhanh hơn.

Những mặc định này được áp dụng qua một nguồn property chuyên biệt và có thể bị ghi đè bởi cấu hình explicit phù hợp của ứng dụng. Danh sách property cụ thể thay đổi theo phiên bản Spring Boot và các integration có trên classpath, nên nên hiểu nguyên tắc thay vì giả định mọi module đều có cùng behavior.

Ví dụ, ứng dụng dùng Thymeleaf có thể đặt rõ:

~~~yaml
spring:
  thymeleaf:
    cache: false
~~~

Khi cần so sánh hành vi giữa phát triển và production, hãy nhớ rằng `spring-boot-devtools` có thể làm các lựa chọn caching khác đi. Nếu production không có Devtools, ứng dụng có thể có hành vi cache như các default thông thường của Spring Boot/template engine.

Nói cách khác, Devtools giúp trải nghiệm development nhanh hơn, nhưng **không nên dùng những default của nó làm hợp đồng về caching trong production**. Hãy cấu hình các giá trị quan trọng một cách tường minh ở môi trường vận hành.

## 12. Devtools có hoạt động khi chạy JAR đã đóng gói không?

Một khác biệt quan trọng là giữa chạy **exploded classpath** trong IDE/build tool và chạy **fully packaged application**.

| Cách chạy | Mục tiêu | Devtools |
|---|---|---|
| Chạy main class từ IDE | Lặp nhanh khi sửa code | Phù hợp, nếu dependency có mặt |
| `./gradlew bootRun` | Chạy project từ Gradle | Phù hợp với development classpath |
| `mvn spring-boot:run` | Chạy project từ Maven | Phù hợp nếu dependency có mặt |
| `java -jar app.jar` sau `bootJar`/`repackage` | Chạy artifact triển khai | Devtools thường bị exclude khỏi executable archive |
| Container production | Vận hành ổn định | Không nên có cơ chế Devtools restart |

Theo mặc định, các plugin đóng gói Spring Boot loại Devtools khỏi executable archive theo cấu hình tiêu chuẩn. Ngay cả khi vì lý do đặc biệt Devtools được giữ trong một fully packaged application, Spring Boot nhận diện kiểu chạy này là môi trường production và thường vô hiệu hóa công cụ phát triển.

Không nên cố bật Devtools trên production để thay thế cơ chế rolling deployment, health checks, graceful shutdown hoặc quy trình release. Automatic restart dựa trên classpath không phải một hệ thống triển khai phiên bản an toàn cho nhiều instance.

### Phân biệt “không có trong JAR” và “có nhưng bị vô hiệu hóa”

Đây là hai tình huống khác nhau:

- **Excluded from archive:** thư viện Devtools không nằm trong executable JAR.
- **Disabled in packaged application:** thư viện có thể nằm trong classpath nhưng chức năng Devtools không được kích hoạt trong kiểu chạy production được nhận diện.

Việc dùng dependency scope đúng và packaging mặc định nhằm đạt được tình huống đầu tiên. Điều này rõ ràng và dễ kiểm soát hơn chỉ dựa vào một property để tắt tính năng sau khi đã mang toàn bộ thư viện vào production.

## 13. Devtools có liên quan Spring profile dev không?

Hai khái niệm khác nhau:

- `developmentOnly` hoặc `optional` liên quan **dependency và packaging**.
- `spring.profiles.active=dev` liên quan **cấu hình và bean của Spring ApplicationContext**.

Ví dụ:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=dev'
~~~

Lệnh trên chạy ứng dụng từ Gradle và bật Spring profile `dev`. Nếu Devtools có mặt trên development classpath, nó có thể hoạt động. Tuy nhiên, bản thân `--spring.profiles.active=dev` **không tự thêm dependency Devtools**.

Ngược lại, nếu Devtools có mặt nhưng không có active profile `dev`, các tiện ích phát triển của Devtools vẫn có thể hoạt động khi ứng dụng được chạy trong chế độ thích hợp.

Không nên quyết định đóng gói Devtools chỉ dựa vào tên Spring profile. Profile có thể được bật khi triển khai production vì lỗi cấu hình; dependency scope và cấu hình packaging phải tạo ranh giới độc lập.

## 14. Tại sao không nên đưa Devtools vào production?

Devtools được thiết kế để tối ưu vòng lặp chỉnh sửa nhanh, không phải mục tiêu vận hành của production. Các rủi ro khi cố giữ hoặc kích hoạt tính năng phát triển bao gồm:

- Restart ngoài ý muốn khi có thay đổi file hoặc resource.
- Trạng thái memory của bean bị tạo lại trong lúc ứng dụng đang xử lý công việc.
- Khác biệt về caching và hành vi chẩn đoán so với môi trường bình thường.
- Tăng bề mặt cấu hình và tương tác classloader không cần thiết.
- Tăng rủi ro nếu các chức năng điều khiển Devtools từ xa bị bật hoặc cấu hình không an toàn.

**Remote Devtools** là chức năng dành cho những kịch bản phát triển đặc biệt và có yêu cầu bảo mật riêng. Không nên mở khả năng điều khiển hoặc restart ứng dụng từ xa trên production chỉ để cập nhật code nhanh. Nếu cần triển khai lên server, hãy dùng pipeline build/deploy, artifact đã kiểm chứng và cơ chế rollout của nền tảng.

Không hard-code secret hoặc để lộ endpoint điều khiển phát triển. Đảm bảo cấu hình security, network và dependency của environment triển khai không bị phụ thuộc vào Devtools.

## 15. Multi-module và troubleshooting

Trong dự án có nhiều module, Devtools có thể không restart khi một module dùng chung thay đổi. Ví dụ:

~~~text
workspace/
├── common-domain/
├── catalog-core/
└── catalog-app/
~~~

Khi `catalog-app` phụ thuộc `common-domain`, class của module phụ thuộc có thể được nạp qua một loader khác tùy cách IDE/build tool tạo classpath. Nếu class đã thay đổi nhưng code đang chạy vẫn thấy phiên bản cũ, hãy xem đường dẫn classpath và nhóm classloader được Devtools sử dụng.

Một số lỗi thường gặp và hướng kiểm tra:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Sửa Java nhưng không restart | IDE chưa compile, output classpath chưa đổi | Build/compile project; kiểm tra output directory |
| Restart liên tục | Nhiều đợt biên dịch hoặc file generated thay đổi | Thêm exclude hoặc trigger file |
| CSS đổi nhưng trang không cập nhật | Browser chưa reload hoặc resource chưa được copy | Kiểm tra LiveReload, browser cache, resource path |
| Context restart nhưng bean state mất | Bean singleton được tạo lại | Không lưu state quan trọng chỉ trong memory dev context |
| Lỗi `ClassCastException` giữa các classloader | Class cùng tên được nạp bởi loader khác nhau | Kiểm tra multi-module classloader và các thư viện dùng static cache |
| Chạy JAR rồi Devtools không hoạt động | Packaged application/executable archive đã exclude Devtools | Dùng IDE/`bootRun`/`spring-boot:run` khi phát triển |
| Spring profile `dev` đã bật nhưng không có auto-restart | Dependency Devtools chưa có hoặc classpath không đổi | Kiểm tra scope và workflow compile |
| Chức năng development vô tình xuất hiện khi deploy | Dependency/packaging cấu hình sai | Đưa Devtools về scope phát triển và kiểm tra artifact |

Với lỗi liên quan tới classloader, một file `META-INF/spring-devtools.properties` có thể dùng các pattern `restart.include.*` và `restart.exclude.*` để điều chỉnh classpath entry nào thuộc base hoặc restart classloader. Đây là công cụ cho trường hợp đặc thù, nên dùng sau khi đã hiểu cấu trúc classpath của ứng dụng.

Ví dụ dạng cấu hình:

~~~properties
restart.include.shared=/common-domain-[\\w.-]+\\.jar
restart.exclude.legacy=/legacy-library-[\\w.-]+\\.jar
~~~

Các pattern là ví dụ minh họa và phải được điều chỉnh theo classpath entry thực tế. Không nên sao chép vào project nếu không có vấn đề classloader cụ thể.

## 16. Một quy trình phát triển Spring Boot với Devtools

Một workflow hợp lý cho ứng dụng web:

1. Thêm `spring-boot-devtools` với `developmentOnly` trong Gradle hoặc `optional=true` trong Maven.
2. Chạy ứng dụng từ IDE, Gradle `bootRun` hoặc Maven `spring-boot:run`.
3. Sửa Java và compile để classpath thay đổi; quan sát Devtools restart.
4. Sửa template/CSS và dùng browser reload hoặc LiveReload khi phù hợp.
5. Nếu restart quá thường xuyên, dùng `additional-exclude` hoặc `trigger-file`.
6. Không đặt state quan trọng vào các object memory chỉ tồn tại qua một lần restart.
7. Build executable archive bằng plugin Spring Boot.
8. Xác nhận quy trình packaging loại Devtools khỏi artifact triển khai.
9. Triển khai cùng artifact qua pipeline, cung cấp cấu hình môi trường bằng property/profile/secret theo quy định vận hành.

Ví dụ Gradle:

~~~bash
# Trong máy phát triển
./gradlew bootRun

# Trước khi triển khai
./gradlew clean bootJar
~~~

Ví dụ Maven:

~~~bash
# Trong máy phát triển
mvn spring-boot:run

# Trước khi triển khai
mvn clean package
~~~

Các lệnh build là minh họa về workflow. Devtools không khiến test hoặc bước build trở nên không cần thiết: developer có thể dùng restart để xem kết quả nhanh, còn pipeline vẫn cần biên dịch, kiểm thử và tạo artifact theo chuẩn phát hành.

## 17. Tóm tắt ranh giới sử dụng

Cần ghi nhớ ba ranh giới:

**Ranh giới dependency:** Devtools là công cụ hỗ trợ phát triển; dùng `developmentOnly` với Spring Boot Gradle plugin hoặc `optional=true` với Maven và giữ cấu hình đóng gói tiêu chuẩn.

**Ranh giới classpath:** Devtools restart khi thấy thay đổi phù hợp ở compiled class/resource, không tự động biên dịch Java source. Nó dùng base/restart classloader để giảm thời gian khởi động lại phần ứng dụng.

**Ranh giới môi trường:** Devtools phục vụ vòng lặp sửa code trên máy phát triển, không phải một thành phần cần thiết của executable JAR production. Spring profile `dev` không thay thế dependency scope, và dependency Devtools không tự bật profile `dev`.

Khi giữ đúng các ranh giới này, ứng dụng Spring Boot vừa có phản hồi nhanh trong phát triển vừa giữ được artifact triển khai gọn, dễ kiểm soát và không phụ thuộc vào cơ chế tự restart dành cho developer.

