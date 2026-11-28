# Chọn phiên bản JDK, Spring Boot, Spring Session và thư viện kho tương thích

Spring Session giúp ứng dụng Spring quản lý phiên làm việc độc lập với một máy chủ ứng dụng. Trong môi trường nhiều instance, các instance có thể dùng chung phiên qua kho lưu trữ như Redis hoặc JDBC. Để triển khai ổn định, cần chọn một bộ phiên bản tương thích gồm JDK, Spring Boot, Spring Session, thư viện kết nối kho dữ liệu, driver và nền tảng chạy ứng dụng.

Không nên chọn riêng từng thư viện theo số phiên bản mới nhất. Spring Boot quản lý một tập hợp phiên bản đã được kiểm tra cùng nhau thông qua dependency management. Hãy lấy phiên bản Spring Boot làm điểm neo, dùng các phiên bản Spring Framework, Spring Data và Spring Session mà BOM của Boot quản lý, sau đó kiểm tra phiên bản JDK, kho dữ liệu và driver theo tài liệu của chính dòng phát hành đó.

## Mục tiêu

Sau bài học, bạn có thể:

- Chọn JDK dựa trên yêu cầu của Spring Boot và môi trường build, kiểm thử, production.
- Chọn dòng Spring Session tương thích với Spring Boot và nền tảng Servlet đang dùng.
- Chọn đúng module Spring Session cho Redis hoặc JDBC và các thư viện kết nối tương ứng.
- Dùng BOM của Spring Boot để tránh xung đột phiên bản thư viện.
- Kiểm tra cây phụ thuộc, schema, serializer và khả năng tương thích khi nâng cấp.

## 1. Xác định nền tảng ứng dụng trước khi chọn phiên bản

Trước tiên, xác định ứng dụng chạy theo mô hình nào. Bài học này tập trung vào ứng dụng Servlet dùng `HttpSession`, thường được triển khai với Spring MVC và một Servlet container như Tomcat hoặc Jetty. Spring Session cũng hỗ trợ WebFlux, nhưng WebFlux dùng `WebSession` và các tích hợp reactive tương ứng; không thể lấy nguyên cấu hình Servlet rồi áp dụng cho ứng dụng reactive.

Hãy ghi lại các thông tin sau:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| JDK | JDK nào có sẵn trong CI, môi trường phát triển và production? Có thể nâng cấp đồng bộ không? |
| Spring Boot | Ứng dụng đang dùng dòng Boot nào? Có cần nâng cấp vì tính năng, bảo mật hoặc vòng đời hỗ trợ không? |
| Web stack | Ứng dụng dùng Spring MVC/Servlet hay WebFlux? Dùng embedded server hay triển khai lên container bên ngoài? |
| Session repository | Cần lưu phiên trong Redis hay JDBC? Có yêu cầu dùng chung phiên giữa nhiều instance không? |
| Hạ tầng | Phiên bản Redis, database, driver, proxy và nền tảng triển khai hiện tại là gì? |
| Vòng đời | Hệ thống có thể nâng JDK, schema database và dịch vụ Redis cùng một đợt hay phải chuyển đổi theo giai đoạn? |

Các thông tin này quyết định bộ phiên bản khả thi. Ví dụ, nếu ứng dụng phải chạy trên một JDK cũ do giới hạn máy chủ, không thể chọn một dòng Spring Boot yêu cầu JDK mới hơn. Nếu hệ thống dùng Servlet API `javax.servlet`, không thể tùy ý đưa một thư viện chỉ tương thích với hệ Jakarta `jakarta.servlet` vào cùng classpath.

## 2. Chọn JDK theo yêu cầu của Spring Boot

Spring Boot công bố phiên bản Java tối thiểu và phạm vi JDK được hỗ trợ cho từng dòng phát hành. Đọc mục System Requirements của đúng phiên bản Boot dự định dùng trước khi cài thư viện. Không suy ra yêu cầu JDK chỉ từ phiên bản Spring Framework hoặc từ máy phát triển của một thành viên trong nhóm.

Một số mốc chuyển đổi quan trọng:

| Dòng nền tảng | Đặc điểm cần chú ý |
|---|---|
| Spring Boot 2.x | Các dòng cũ có thể chạy trên Java 8 trở lên tùy bản phát hành. Cần kiểm tra chính xác patch release và các thư viện đi kèm. |
| Spring Boot 3.x | Yêu cầu Java 17 trở lên. Nền tảng chuyển sang Spring Framework 6 và Jakarta EE; API Servlet dùng namespace `jakarta.*`. |
| Dòng Spring Boot mới hơn | Kiểm tra yêu cầu JDK, Spring Framework, Servlet container và dependency BOM trong tài liệu của chính dòng đó. Không tự suy ra tương thích chỉ từ số major. |

Khi đã chọn JDK, cần bảo đảm cùng một mức Java được dùng nhất quán ở các nơi:

- Máy phát triển và IDE.
- CI build và chạy unit test, integration test.
- Công cụ đóng gói container image.
- JVM chạy ứng dụng trong staging và production.

Một ứng dụng có thể biên dịch thành công trên JDK mới nhưng không chạy được trên JVM cũ nếu bytecode hoặc thư viện yêu cầu API mới. Hãy đặt toolchain hoặc compiler release rõ ràng trong build để tránh phụ thuộc vào JDK mặc định trên máy.

Ví dụ Maven đặt phiên bản Java bằng thuộc tính `java.version`:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

Giá trị `17` chỉ là ví dụ cho một ứng dụng thuộc dòng Spring Boot yêu cầu Java 17. Hãy thay bằng phiên bản phù hợp với dòng Boot và chính sách runtime đã chọn. Không nâng `java.version` mà quên nâng JDK trong CI và image production.

Với Gradle, có thể khai báo Java toolchain:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Toolchain giúp build chọn đúng JDK cho tác vụ Java. Máy chạy ứng dụng vẫn phải có runtime tương thích. Hãy kiểm tra cả `java -version` trong môi trường triển khai, không chỉ cấu hình build.

## 3. Chọn Spring Session theo dòng Spring Boot

Spring Boot quản lý các phiên bản Spring Framework, Spring Data và nhiều dự án Spring khác thông qua bộ dependency management. Spring Session cần tương thích với các nền tảng này, do đó nên dùng phiên bản Spring Session được BOM của Spring Boot chỉ định.

Quy tắc định hướng phổ biến:

| Nền tảng | Dòng Spring Session thường tương ứng | Namespace Servlet |
|---|---|---|
| Spring Boot 2.x / Spring Framework 5.x | Spring Session 2.x | `javax.servlet.*` |
| Spring Boot 3.x / Spring Framework 6.x | Spring Session 3.x | `jakarta.servlet.*` |
| Spring Boot ở dòng mới hơn | Dòng Spring Session được BOM tương ứng quản lý | Xác minh theo nền tảng Servlet/Jakarta của dòng Boot đó |

Bảng trên dùng để nhận biết dòng tương thích, không thay thế ma trận chính thức cho từng patch release. Một ứng dụng có thể gặp lỗi biên dịch hoặc runtime nếu trộn Spring Session 3 với nền tảng Boot 2, hoặc trộn thư viện Servlet `javax` với container chỉ cung cấp `jakarta`.

Điểm chuyển từ `javax.*` sang `jakarta.*` là thay đổi lớn khi nâng từ Boot 2 lên Boot 3. Cần kiểm tra:

- Import Servlet trong source code và thư viện nội bộ.
- Phiên bản Servlet container, filter và listener.
- Các thư viện bảo mật, logging, tracing và integration khác.
- Cấu hình XML, descriptor và custom filter nếu dự án có sử dụng.
- Các dependency nội bộ có đóng gói API `javax.servlet` hoặc `jakarta.servlet`.

Không giải quyết lỗi namespace bằng cách thêm cả hai API Servlet vào classpath. Điều đó có thể làm dự án biên dịch nhưng không làm cho hai hệ sinh thái tương thích với nhau.

Nếu ứng dụng đang chạy ổn định trên Boot 2, hãy lập kế hoạch nâng cấp riêng để chuyển sang Boot 3 hoặc dòng mới hơn. Đọc migration guide, cập nhật namespace và kiểm thử toàn bộ web stack trước khi đưa thay đổi vào production. Không chỉ đổi version Spring Session rồi kỳ vọng các thư viện khác tự tương thích.

## 4. Chọn module Spring Session theo repository

Spring Session tách phần tích hợp theo loại kho lưu trữ. Chỉ thêm module tương ứng với repository ứng dụng định dùng.

| Mục đích | Dependency chính | Thư viện kết nối thường đi kèm |
|---|---|---|
| Lưu phiên trong Redis | `org.springframework.session:spring-session-data-redis` | `org.springframework.boot:spring-boot-starter-data-redis` |
| Lưu phiên trong JDBC | `org.springframework.session:spring-session-jdbc` | `org.springframework.boot:spring-boot-starter-jdbc` và JDBC driver của database |
| Dùng Servlet MVC | `org.springframework.boot:spring-boot-starter-web` | Servlet container do starter hoặc môi trường triển khai cung cấp |

`spring-session-data-redis` cung cấp tích hợp repository Redis của Spring Session. Starter Data Redis cung cấp cấu hình và thư viện truy cập Redis của Spring Data Redis. `spring-session-jdbc` cung cấp repository JDBC; starter JDBC và driver cung cấp kết nối đến hệ quản trị cơ sở dữ liệu.

Không thêm cả Redis và JDBC chỉ vì muốn “đủ lựa chọn”. Khi có nhiều repository trên classpath, cần cấu hình rõ repository nào là nguồn lưu phiên thực tế. Nếu ứng dụng cần chuyển đổi kho lưu trữ, hãy thực hiện như một thay đổi kiến trúc có kế hoạch, bao gồm dữ liệu phiên đang hoạt động, TTL, logout, khả năng tương thích và rollback.

Với Redis, kiểm tra các yếu tố:

- Phiên bản Redis server hoặc dịch vụ Redis tương thích với thư viện client được chọn.
- Spring Data Redis và Lettuce/Jedis được BOM quản lý tương thích.
- TLS, xác thực, ACL, timeout, connection pool và network policy phù hợp môi trường.
- Cấu hình serializer được thống nhất giữa các instance.
- TTL, namespace và keyspace notifications phù hợp cách vận hành của ứng dụng.

Với JDBC, kiểm tra:

- Phiên bản database và JDBC driver được hỗ trợ cùng nhau.
- Schema Spring Session đúng với hệ quản trị cơ sở dữ liệu thực tế.
- Quyền tạo, đọc, cập nhật và xóa các bảng cần thiết.
- Kích thước cột, kiểu nhị phân/LOB, transaction và giới hạn connection pool.
- Chiến lược migration schema và dọn phiên hết hạn.

Đừng chọn phiên bản driver chỉ theo phiên bản database ghi trên máy chủ. Hãy đọc ma trận tương thích của driver, JDK và database, rồi dùng phiên bản mà BOM quản lý nếu BOM đó đáp ứng yêu cầu vận hành.

## 5. Dùng BOM của Spring Boot để đồng bộ phiên bản

BOM (Bill of Materials) là danh sách phiên bản dependency được quản lý cùng nhau. Khi dùng Spring Boot, BOM giúp tránh việc tự đặt các phiên bản Spring Framework, Spring Data, Spring Session và thư viện liên quan không cùng một bộ đã được kiểm tra.

Nguyên tắc thực hành:

1. Chọn một patch release Spring Boot phù hợp với yêu cầu JDK và chính sách hỗ trợ.
2. Dùng Spring Boot parent hoặc import `spring-boot-dependencies` BOM.
3. Khai báo dependency Spring Session và Spring Data mà không ghi version nếu BOM đã quản lý.
4. Chỉ override một dependency khi có lý do kỹ thuật cụ thể, đã kiểm tra tương thích và có test xác nhận.
5. Kiểm tra cây dependency sau khi thay đổi để phát hiện nhiều phiên bản cùng xuất hiện.

### 5.1. Maven với Spring Boot parent

Ví dụ sau minh họa ứng dụng Servlet dùng Redis. Thay `BOOT_VERSION_DA_CHON` bằng patch release Spring Boot đã được xác minh trong dự án. Không giữ nguyên chuỗi placeholder khi build.

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>BOOT_VERSION_DA_CHON</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
</dependencies>
~~~

Maven parent cung cấp dependency management. Vì vậy, ví dụ không khai báo version riêng cho Spring Session và Spring Data Redis. Nếu thêm version thủ công vào từng dependency, dự án có thể vô tình bỏ qua phiên bản mà Boot đã kiểm thử.

Với repository JDBC, thay dependency Redis bằng nhóm JDBC:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <!-- Ví dụ dùng PostgreSQL; chọn driver theo database thực tế. -->
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Nếu dự án không kế thừa `spring-boot-starter-parent`, có thể import `spring-boot-dependencies` trong `dependencyManagement`. Cần bảo đảm BOM được import đúng phiên bản với Spring Boot plugin/runtime mà ứng dụng sử dụng.

### 5.2. Gradle dùng platform BOM

Với Gradle, có thể import BOM bằng `platform` để dependency không cần khai báo version riêng:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_VERSION_DA_CHON'
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:BOOT_VERSION_DA_CHON'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Thay placeholder bằng cùng một phiên bản Boot đã chọn. Với repository JDBC, dùng `spring-session-jdbc`, `spring-boot-starter-jdbc` và driver tương ứng. Trong dự án đã dùng plugin quản lý dependency của Spring, hãy tuân theo một cách import BOM nhất quán thay vì khai báo BOM lặp lại không cần thiết.

### 5.3. Khi không dùng Spring Boot

Nếu ứng dụng Spring Framework không dùng Boot, nhóm phát triển phải tự quản lý phiên bản Spring Framework, Spring Session, Spring Data, client Redis hoặc JDBC driver. Có thể dùng BOM của Spring Session và BOM của các dự án liên quan, nhưng phải kiểm tra ma trận tương thích giữa chúng. Đây là cấu hình có trách nhiệm quản lý phiên bản cao hơn; không sao chép danh sách version từ một dự án Boot khác mà chưa xác minh.

## 6. Phân biệt version của thư viện và version của dịch vụ lưu trữ

Version của `spring-session-data-redis` không phải version Redis server. Tương tự, version `spring-session-jdbc` không quyết định version PostgreSQL, MySQL, Oracle hay database khác.

Có ít nhất bốn lớp phiên bản cần xác minh:

1. Thư viện tích hợp Spring Session.
2. Spring Data Redis hoặc Spring JDBC cùng client/driver.
3. Dịch vụ Redis hoặc hệ quản trị cơ sở dữ liệu.
4. JDK và môi trường chạy ứng dụng.

Ví dụ, nâng Spring Boot có thể làm BOM nâng Spring Data Redis và Redis client. Dù Redis server không đổi, cần kiểm thử kết nối, xác thực, TLS, serializer và hành vi timeout. Với JDBC, nâng driver có thể làm thay đổi TLS mặc định, xử lý kiểu dữ liệu, connection properties hoặc hành vi transaction.

Đối với JDBC, Spring Session cần schema phù hợp với database. Các script schema có thể khác nhau theo nhà cung cấp. Dùng đúng script hoặc migration đã điều chỉnh cho hệ quản trị cơ sở dữ liệu thực tế; kiểm tra bảng `SPRING_SESSION` và `SPRING_SESSION_ATTRIBUTES`, kiểu cột và chỉ mục trước khi khởi chạy.

Trong production, nên quản lý schema bằng công cụ migration như Flyway hoặc Liquibase thay vì để nhiều instance tự chạy thay đổi schema đồng thời khi khởi động. Tài khoản runtime thường chỉ cần quyền thao tác dữ liệu; tài khoản migration có thể được cấp quyền DDL riêng.

Đối với Redis, định dạng dữ liệu được ghi bởi serializer cũng là một phần của tương thích. Nếu thay serializer hoặc kiểu class lưu trong session, dữ liệu do phiên bản cũ ghi có thể không đọc được bởi phiên bản mới. Cần có chiến lược chuyển đổi hoặc chờ phiên cũ hết TTL trước khi bỏ khả năng đọc định dạng cũ.

## 7. Kiểm tra cây dependency và phiên bản thực tế

Sau khi khai báo dependency, đừng chỉ nhìn file `pom.xml` hoặc `build.gradle`. Hãy kiểm tra phiên bản thực tế được resolve, vì dependency bắc cầu có thể đưa vào một phiên bản khác với dự kiến.

Với Maven:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Với Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency spring-session
./gradlew dependencyInsight --dependency spring-data-redis
~~~

Hãy tìm các dấu hiệu:

- Có nhiều phiên bản `spring-session-core` hoặc module Spring Session cùng xuất hiện không?
- Spring Framework và Spring Data có nằm trong dòng mà Boot BOM quản lý không?
- Có cả Servlet API `javax` và `jakarta` do dependency cũ kéo vào không?
- Redis client hoặc JDBC driver có bị override bởi dependency khác không?
- Có thư viện nào kéo một phiên bản Spring cũ vào classpath không?

Khi phát hiện xung đột, truy ngược dependency đưa phiên bản đó vào. Ưu tiên nâng thư viện gốc lên phiên bản tương thích. Chỉ dùng exclusion hoặc force version khi hiểu rõ tác động và có test chứng minh; việc ép một version vào classpath không biến các API không tương thích thành tương thích.

Có thể kiểm tra JDK và build tool bằng:

~~~bash
java -version
mvn -version
./gradlew --version
~~~

Các lệnh này giúp xác nhận môi trường đang chạy build. Trong CI và container production, cần kiểm tra tương tự để tránh trường hợp máy cá nhân dùng JDK mới nhưng pipeline hoặc runtime dùng JDK khác.

## 8. Kiểm thử bộ phiên bản đã chọn

Build thành công là bước đầu. Một bộ dependency chỉ thực sự phù hợp khi ứng dụng có thể khởi động, lưu phiên, đọc lại phiên và chia sẻ phiên giữa các instance.

Với Redis:

1. Khởi động Redis đúng phiên bản hoặc dịch vụ tương đương môi trường triển khai.
2. Xác minh kết nối, TLS, xác thực và quyền truy cập.
3. Tạo phiên qua một request, sau đó đọc lại từ request tiếp theo.
4. Dùng instance thứ hai đọc cùng phiên để xác nhận repository được chia sẻ.
5. Kiểm tra TTL, logout, xóa phiên và hành vi khi Redis tạm thời không khả dụng.
6. Kiểm tra serializer với các kiểu thuộc tính thực tế của ứng dụng.

Với JDBC:

1. Khởi động database đúng phiên bản và áp dụng schema đã chọn.
2. Xác minh driver, URL, TLS, tài khoản và connection pool.
3. Tạo phiên, đọc lại và xác nhận các hàng thuộc tính được ghi đúng.
4. Dùng instance khác đọc cùng session ID.
5. Kiểm tra transaction, timeout, lỗi kết nối và dọn phiên hết hạn.
6. Kiểm tra migration schema khi nâng cấp ứng dụng.

Ngoài kiểm thử repository, hãy chạy kiểm thử tích hợp với Spring Security nếu ứng dụng có bảo vệ đăng nhập. Xác nhận đăng nhập, session fixation protection, logout và hành vi khi phiên hết hạn. Khi chạy nhiều instance, kiểm thử request đồng thời để phát hiện ghi đè dữ liệu hoặc cập nhật mất mát.

## 9. Nâng cấp phiên bản có kiểm soát

Không nên nâng JDK, Spring Boot, Spring Session, Redis client và schema database cùng lúc nếu chưa có kiểm thử hồi quy đủ rộng. Khi có lỗi, thay đổi quá nhiều lớp sẽ làm khó xác định nguyên nhân.

Một quy trình nâng cấp thực tế:

1. Chọn patch release Boot mục tiêu và đọc release notes, system requirements, migration guide.
2. Xác nhận JDK, Servlet container, Redis/database và driver đáp ứng yêu cầu.
3. Cập nhật Boot parent hoặc BOM; bỏ các version Spring Session/Spring Data bị pin riêng nếu không còn cần thiết.
4. Xử lý thay đổi API, đặc biệt chuyển `javax.*` sang `jakarta.*` khi nâng qua ranh giới Boot 2 sang Boot 3.
5. Kiểm tra cây dependency và giải quyết xung đột.
6. Chạy unit test, integration test với repository thật và kiểm thử nhiều instance.
7. Triển khai staging, quan sát lỗi serializer, lỗi kết nối, độ trễ và số phiên.
8. Lên kế hoạch rollback có xét đến schema và định dạng session đã được ghi bởi phiên bản mới.

Một số thay đổi không thể rollback chỉ bằng cách đưa lại binary cũ. Ví dụ, nếu phiên bản mới ghi payload bằng serializer mà phiên bản cũ không đọc được, hoặc migration đã loại bỏ cột cũ, việc quay lại phiên bản trước có thể làm phiên bị lỗi. Hãy giữ khả năng đọc dữ liệu trong giai đoạn chuyển đổi hoặc chấp nhận chủ động cho phiên cũ hết hạn theo kế hoạch nghiệp vụ.

## 10. Những lỗi chọn phiên bản thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chọn Spring Session mới nhất nhưng giữ Spring Boot cũ | Lỗi class, method hoặc API không tương thích | Dùng version do BOM của Boot quản lý; chỉ nâng độc lập khi có ma trận tương thích rõ ràng |
| Chạy Boot 3 trên JDK thấp hơn yêu cầu | Build hoặc ứng dụng không khởi động | Nâng JDK ở CI và production, đặt toolchain/compiler release rõ ràng |
| Trộn `javax.servlet` với `jakarta.servlet` | Filter, listener hoặc class Servlet không được nhận diện | Đồng bộ toàn bộ web stack theo dòng Boot |
| Dùng module Redis nhưng thiếu thư viện kết nối Redis | Không có client hoặc auto-configuration cần thiết | Thêm Spring Boot Data Redis starter và kiểm tra dependency tree |
| Dùng Spring Session JDBC nhưng thiếu driver/schema | Không tạo hoặc truy cập được repository | Thêm driver phù hợp, áp dụng schema đúng database và xác minh quyền |
| Override một dependency Spring bằng version riêng | Lỗi runtime khó truy vết | Bỏ override hoặc kiểm tra tương thích, khóa version có lý do và có test |
| Nâng serializer mà không xét phiên đang tồn tại | Instance mới không đọc được session cũ | Thiết kế chuyển đổi, đọc tương thích hoặc chờ TTL hết trước khi loại định dạng cũ |
| Chỉ kiểm thử trên một instance | Bỏ sót lỗi chia sẻ session và tương thích giữa các node | Chạy integration test với ít nhất hai instance dùng chung repository |

## 11. Checklist trước khi khóa phiên bản

- [ ] Đã chọn dòng và patch release Spring Boot dựa trên yêu cầu sản phẩm và chính sách hỗ trợ.
- [ ] JDK đáp ứng yêu cầu của Boot và giống môi trường CI/runtime.
- [ ] Đã xác định ứng dụng dùng Servlet `HttpSession` hay reactive `WebSession`.
- [ ] Spring Session nằm trong dòng tương thích và được quản lý bởi BOM phù hợp.
- [ ] Chỉ thêm module repository cần dùng: Redis hoặc JDBC.
- [ ] Redis client hoặc JDBC driver tương thích với JDK và dịch vụ lưu trữ.
- [ ] Servlet container, Spring Security và các thư viện web cùng namespace `javax` hoặc `jakarta`.
- [ ] Cây dependency không có phiên bản Spring xung đột ngoài dự kiến.
- [ ] Schema JDBC hoặc serializer Redis đã được xác minh với phiên bản ứng dụng.
- [ ] Đã kiểm thử tạo, đọc, cập nhật, hết hạn và xóa phiên trên nhiều instance.
- [ ] Có kế hoạch nâng cấp, rollback và xử lý session được ghi bởi phiên bản cũ.

Việc chọn phiên bản cho Spring Session là bài toán tương thích của toàn bộ nền tảng. Hãy neo bộ dependency vào Spring Boot BOM, xác nhận JDK và namespace Servlet, chọn module Redis hoặc JDBC theo repository thực tế, rồi kiểm tra dịch vụ lưu trữ, driver, schema, serializer và hành vi nhiều instance. Cách làm này giúp ứng dụng có một bộ phiên bản nhất quán và giảm rủi ro khi nâng cấp.
