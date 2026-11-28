# Cấu hình tự động thay đổi giữa các dòng Spring Boot

## Mục tiêu bài học

Spring Boot tự động cấu hình Spring Session dựa trên dependency trong classpath, loại ứng dụng, bean đã đăng ký và các thuộc tính cấu hình. Khi nâng cấp giữa các dòng Spring Boot, cơ chế auto-configuration có thể thay đổi do Spring Framework, Spring Session, Servlet API, tên thuộc tính và cách quản lý phiên bản thay đổi theo.

Với module Spring Session, việc nâng cấp cần bảo đảm repository vẫn được phát hiện đúng, Session ID vẫn được truyền theo hợp đồng cũ, dữ liệu phiên vẫn đọc được và các instance trong giai đoạn triển khai đồng thời không xung đột.

Sau bài học, bạn có thể:

- Giải thích các điều kiện đầu vào ảnh hưởng đến Spring Boot auto-configuration.
- Phân biệt cấu hình do Boot tự động tạo với cấu hình thủ công bằng annotation.
- Nhận biết thay đổi đáng chú ý giữa Spring Boot 2.x và 3.x.
- Cập nhật dependency, Java, Servlet API và thuộc tính cấu hình khi nâng cấp.
- Chọn rõ repository khi nhiều implementation cùng xuất hiện trên classpath.
- Kiểm tra bean, filter và điều kiện auto-configuration sau khi chuyển dòng Boot.
- Lập kế hoạch nâng cấp mà vẫn bảo vệ session đang hoạt động trong Redis hoặc JDBC.

## 1. Auto-configuration của Spring Session hoạt động dựa trên điều gì?

Spring Boot auto-configuration là tập hợp cấu hình có điều kiện. Boot kiểm tra classpath, loại ứng dụng, bean hiện có và property để quyết định bean nào cần được đăng ký.

Với Spring Session, các yếu tố chính gồm:

| Yếu tố | Ảnh hưởng |
|---|---|
| Web application type | Xác định ứng dụng dùng Servlet hay reactive WebFlux |
| Dependency Spring Session | Cung cấp integration và repository tương ứng |
| Data starter/client | Cung cấp kết nối Redis, JDBC hoặc kho dữ liệu khác |
| Bean repository | Có thể khiến auto-configuration mặc định lùi lại |
| Thuộc tính spring.session.* | Chọn loại store, timeout, namespace, flush/save mode hoặc schema |
| Thuộc tính kết nối dữ liệu | Cung cấp Redis connection hoặc JDBC DataSource |
| Annotation cấu hình thủ công | Có thể đăng ký repository/filter theo cách tường minh |

Ví dụ, ứng dụng Servlet có Spring Session Redis, Spring Data Redis và Redis connection factory có thể được Boot cấu hình để sử dụng Redis repository. Ứng dụng Servlet có Spring Session JDBC và DataSource có thể dùng JDBC repository.

Dependency chỉ cung cấp các lớp cần thiết. Để auto-configuration tạo được repository, ứng dụng vẫn cần connection factory hoặc DataSource hợp lệ.

### Auto-configuration không phải phép đoán ngẫu nhiên

Boot dựa trên các điều kiện xác định. Nếu thêm nhiều repository implementation vào classpath, hoặc tự đăng ký bean tương ứng, kết quả lựa chọn có thể khác với kỳ vọng.

Khi nâng cấp cần kiểm tra:

- Dependency tree thực tế.
- Loại web application mà Boot nhận diện.
- Repository bean đã được tạo.
- Session filter đã được đăng ký.
- Resolver và cookie/header configuration đang được sử dụng.
- Property nào đã được bind và property nào không còn được nhận diện.

Không nên dựa vào việc ứng dụng khởi động thành công để kết luận session đang dùng đúng repository.

## 2. Phân biệt cấu hình tự động và cấu hình thủ công

Có hai cách tổ chức phổ biến.

**Cấu hình do Spring Boot quản lý**

Ứng dụng khai báo dependency cần thiết và cung cấp property. Boot phát hiện module phù hợp, tạo repository, connection factory hoặc DataSource khi đủ điều kiện và đăng ký tích hợp web.

Ví dụ dependency cho Servlet + Redis:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")
}
~~~

Với Spring Boot plugin và dependency management đã được cấu hình, không cần tự ghi version riêng cho các artifact được BOM quản lý.

**Cấu hình thủ công**

Ứng dụng có thể dùng annotation như @@EnableRedisHttpSession@@ hoặc @@EnableJdbcHttpSession@@ để bật repository Servlet tương ứng. Cách này hữu ích khi cần kiểm soát cấu hình chi tiết hoặc không dùng auto-configuration của Boot.

Ví dụ:

~~~java
@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
public class SessionConfiguration {
}
~~~

Không nên vừa bật repository thủ công vừa mong Boot tự chọn một repository khác. Các cấu hình có thể tạo bean hoặc filter trùng, hoặc khiến auto-configuration lùi lại do bean đã tồn tại.

Hãy chọn một nguồn cấu hình chủ đạo. Nếu dùng Boot, ưu tiên property và bean extension point được tài liệu hóa. Chỉ dùng annotation thủ công khi có lý do cụ thể và đã xác minh điều kiện back-off của phiên bản đó.

### Phân biệt Servlet và WebFlux

Servlet dùng @@HttpSession@@ và filter chain. WebFlux dùng @@WebSession@@ và reactive session repository. Không thể dùng annotation Servlet để bật session reactive.

Ví dụ cấu hình thủ công Redis cho Servlet:

~~~java
@EnableRedisHttpSession
~~~

Ví dụ cấu hình thủ công Redis cho WebFlux:

~~~java
@EnableRedisWebSession
~~~

Tên annotation minh họa sự khác nhau của API. Chọn đúng theo application type; không đưa cả hai vào cùng một ứng dụng chỉ để tránh quyết định web stack.

## 3. Những thay đổi đáng chú ý giữa Spring Boot 2.x và 3.x

Spring Boot 3 là một bước chuyển lớn về nền tảng. Ứng dụng cần nâng cấp Java và chuyển từ Java EE namespace sang Jakarta EE namespace. Spring Session và Spring Framework cũng chuyển major version tương ứng.

| Khu vực | Dòng Boot 2.x | Dòng Boot 3.x |
|---|---|---|
| Nền tảng Java | Tùy phiên bản Boot 2; các bản cuối hỗ trợ Java 8 trở lên | Java 17 trở lên |
| Spring Framework | 5.x | 6.x |
| Spring Session | Dòng 2.x tương ứng | Dòng 3.x tương ứng |
| Servlet API | javax.servlet.* | jakarta.servlet.* |
| Container Servlet | Các container tương thích javax, ví dụ Tomcat 9 | Container Jakarta, ví dụ Tomcat 10.1 |
| Redis connection properties | Thường dùng spring.redis.* | Dùng spring.data.redis.* |
| Dependency versions | Nên theo BOM của Boot 2.x đang dùng | Nên theo BOM của Boot 3.x đang dùng |

Bảng này mô tả hướng thay đổi giữa hai thế hệ, không thay thế compatibility matrix của một bản phát hành cụ thể. Hãy kiểm tra yêu cầu Java, Spring Session, Spring Data và container cho đúng minor/patch version dự án chọn.

### Chuyển javax sang jakarta

Với ứng dụng Servlet, import trong code cần chuyển từ:

~~~java
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpSession;
~~~

sang:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
~~~

Spring Session 3.x làm việc trên nền Jakarta Servlet. Một dependency cũ còn kéo javax.servlet vào classpath có thể gây lỗi compile, lỗi kiểu dữ liệu hoặc xung đột khi khởi động.

Không thay chuỗi javax thành jakarta một cách máy móc trong toàn bộ repository. Chỉ các API thuộc Jakarta EE được chuyển namespace; package của thư viện Spring như org.springframework.session.* vẫn giữ namespace riêng.

### Nâng cấp container

Spring Boot 3 dùng container hỗ trợ Jakarta Servlet. Ví dụ Tomcat 10.1 thuộc thế hệ Jakarta, còn Tomcat 9 thuộc thế hệ Servlet javax. Khi deploy WAR lên application server ngoài, cần xác nhận server tương thích với phiên bản Boot và Servlet API mới.

Nếu container không tương thích, Spring Session filter có thể không đăng ký đúng hoặc ứng dụng không khởi tạo được dù dependency Spring Session đã được nâng cấp.

## 4. Dependency management và tương thích Spring Session

Spring Boot quản lý phiên bản của nhiều thư viện thông qua BOM. Spring Session, Spring Data, Spring Framework và các thư viện liên quan cần nằm trong tập phiên bản tương thích.

Với Gradle, có thể để Spring Boot plugin và dependency management quản lý version:

~~~gradle
plugins {
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
    java
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")
}
~~~

Các version 3.x.y và 1.x.y chỉ là placeholder. Dùng phiên bản phát hành thực tế đã chọn trong dự án; không sao chép placeholder vào build file.

Với Maven, dùng Spring Boot parent hoặc import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi BOM quản lý Spring Session, không tự ép một version khác chỉ vì muốn lấy một tính năng mới. Nếu cần nâng Spring Session ngoài version Boot quản lý, phải kiểm tra ma trận tương thích của Spring Framework và Spring Data, sau đó kiểm thử toàn bộ repository.

### Tránh trộn major version

Các trường hợp dễ gây lỗi:

- Spring Boot 3 cùng Spring Session 2.x.
- Spring Boot 2 cùng dependency Servlet Jakarta chỉ dành cho Spring Framework 6.
- Spring Data Redis bị ép version khác với BOM.
- Có nhiều version của cùng một artifact trong dependency graph.
- Thư viện nội bộ vẫn compile với javax.servlet nhưng ứng dụng chuyển sang jakarta.servlet.

Kiểm tra dependency tree thay vì chỉ xem các dependency khai báo trực tiếp. Một starter có thể kéo transitive dependency cũ vào classpath.

## 5. Property Redis thay đổi giữa các dòng Boot

Một thay đổi cấu hình thường gặp khi nâng từ Boot 2 sang Boot 3 là prefix cho Redis connection properties.

Ví dụ trong nhiều ứng dụng Boot 2.x:

~~~properties
spring.redis.host=localhost
spring.redis.port=6379
spring.redis.password=REDIS_PASSWORD
~~~

Trong Boot 3.x:

~~~properties
spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.data.redis.password=REDIS_PASSWORD
~~~

Nếu chỉ giữ property cũ sau khi nâng Boot, ứng dụng có thể không bind host/port/password theo ý muốn và chuyển sang giá trị mặc định hoặc không kết nối được.

Cần tìm và cập nhật mọi nguồn cấu hình:

- application.properties.
- application.yml.
- Profile như application-prod.yml.
- Environment variables.
- Config server hoặc secret manager.
- Helm chart, manifest Kubernetes và biến trong pipeline triển khai.

Không chỉ sửa file local rồi cho rằng production đã cập nhật. Property có thể được ghi đè bởi environment hoặc external configuration.

### Property session và property kết nối Redis là hai nhóm khác nhau

Ví dụ:

~~~properties
spring.session.redis.namespace=shop:session
spring.session.redis.flush-mode=on-save
spring.session.timeout=30m
~~~

Các property trên cấu hình Spring Session. Trong khi đó, spring.data.redis.* cấu hình kết nối Redis của Spring Data Redis ở Boot 3.

Đổi prefix connection không có nghĩa phải đổi namespace session. Tuy nhiên, hãy kiểm tra metadata session và property hỗ trợ trong đúng phiên bản.

## 6. Property JDBC và cấu hình schema

Ứng dụng dùng JDBC cần DataSource và Spring Session JDBC repository.

Dependency ví dụ:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.session:spring-session-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

Một số property Spring Session JDBC thường gặp:

~~~properties
spring.session.jdbc.initialize-schema=never
spring.session.jdbc.table-name=SPRING_SESSION
spring.session.timeout=30m
~~~

Hãy kiểm tra property được hỗ trợ trong dòng Boot/Spring Session đang dùng. initialize-schema quyết định cách schema được khởi tạo theo cơ chế tích hợp; production thường nên quản lý schema qua Flyway hoặc Liquibase và đặt chính sách khởi tạo phù hợp.

Khi nâng Boot, không nên đồng thời thay schema, table name, database engine và serializer nếu chưa có kế hoạch migration. Thay đổi nhiều lớp cùng lúc làm khó xác định nguyên nhân nếu session không đọc được.

### DataSource và repository

Boot cần một DataSource hợp lệ. Nếu ứng dụng có nhiều DataSource, cần xác định DataSource nào được repository Spring Session sử dụng. Không giả định bean Primary luôn là database mong muốn nếu cấu hình thay đổi theo profile.

Nếu tự cấu hình repository JDBC, cần bảo đảm schema và transaction manager phù hợp. Tránh tạo thêm @EnableJdbcHttpSession trong khi auto-configuration đã đăng ký repository.

## 7. Chọn store khi nhiều repository cùng có trên classpath

Một ứng dụng có thể kéo nhiều Spring Session module do dependency trực tiếp hoặc transitive. Ví dụ vừa có Spring Session Redis vừa có Spring Session JDBC.

Khi nhiều implementation cùng xuất hiện, không nên dựa vào thứ tự classpath để quyết định store. Hãy xác định rõ repository mong muốn bằng property được phiên bản Boot hỗ trợ hoặc bằng cấu hình tường minh.

Trong nhiều dòng Spring Boot, property spring.session.store-type có thể chọn loại store như Redis hoặc JDBC. Giá trị hợp lệ và khả năng auto-detect phụ thuộc phiên bản. Kiểm tra metadata configuration và tài liệu đúng release trước khi dùng.

Ví dụ minh họa:

~~~properties
spring.session.store-type=redis
~~~

Hoặc:

~~~properties
spring.session.store-type=jdbc
~~~

Đừng thêm cả hai module vào production nếu không cần. Giữ classpath tối thiểu giúp auto-configuration dễ dự đoán hơn.

### Khi nào dùng store-type rõ ràng?

- Có nhiều Spring Session repository module trên classpath.
- Dependency được kéo vào bởi starter khác.
- Môi trường dev/test/prod có tập dependency tương tự nhưng store mong muốn khác.
- Muốn tránh auto-detection chọn implementation ngoài ý muốn.

Nếu phiên bản đang dùng không hỗ trợ property này hoặc có cấu hình khác, dùng extension point công khai được tài liệu hóa. Không phụ thuộc vào class auto-configuration nội bộ của Boot vì tên và điều kiện của chúng có thể thay đổi giữa release.

## 8. Property timeout và cookie không nên bị nhầm lẫn

Khi nâng cấp, kiểm tra các giá trị thời hạn và cách chúng được bind.

spring.session.timeout thường biểu diễn thời gian không hoạt động của session. Nếu không đặt, Boot có thể sử dụng giá trị từ cấu hình Servlet session theo quy tắc của phiên bản.

Không nhầm:

| Property hoặc khái niệm | Phạm vi |
|---|---|
| spring.session.timeout | Thời hạn session do Spring Session quản lý |
| server.servlet.session.timeout | Thời hạn session Servlet container; quan hệ fallback cần kiểm tra theo Boot version |
| Redis key TTL | Thời gian tồn tại vật lý của key session |
| JDBC expiration time | Thời điểm hết hạn được lưu trong hàng session |
| Cookie Max-Age | Thời gian trình duyệt giữ cookie |

Đổi Boot có thể làm property không còn bind do đổi tên hoặc đổi prefix. Nhưng không nên dùng việc thay property để thay đổi chính sách timeout một cách vô tình.

Kiểm thử session hết hạn bằng repository thực tế, không chỉ kiểm tra property đã bind.

## 9. Spring Boot Properties Migrator

Khi chuyển giữa các dòng Boot có thay đổi tên property, có thể dùng spring-boot-properties-migrator như công cụ hỗ trợ trong giai đoạn nâng cấp.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Gradle:

~~~gradle
runtimeOnly("org.springframework.boot:spring-boot-properties-migrator")
~~~

Công cụ này có thể phát hiện một số property đã đổi tên hoặc không còn được hỗ trợ và đưa ra thông báo trong lúc ứng dụng khởi động. Hãy dùng version được BOM của Boot quản lý.

Quy trình:

1. Thêm migrator tạm thời khi nâng Boot.
2. Khởi động ứng dụng trong môi trường phát triển hoặc test.
3. Đọc cảnh báo property và sửa cấu hình theo tên mới.
4. Chạy lại kiểm thử với profile tương ứng.
5. Gỡ migrator khỏi dependency production sau khi hoàn tất chuyển đổi.

Migrator không thay thế việc đọc migration guide, kiểm tra external configuration hoặc kiểm thử hành vi repository. Nó không bảo đảm mọi thay đổi cấu hình đều được phát hiện.

## 10. Kiểm tra auto-configuration sau nâng cấp

Sau khi nâng dependency và property, cần xác minh Boot đã tạo đúng bean.

### Bật condition evaluation report

Có thể khởi động ứng dụng với debug mode để xem báo cáo điều kiện auto-configuration:

~~~bash
java -jar app.jar --debug
~~~

Báo cáo giúp tìm hiểu cấu hình nào được áp dụng hoặc lùi lại do thiếu class, thiếu property hoặc bean đã tồn tại.

Không nên phụ thuộc vào tên class auto-configuration nội bộ làm hợp đồng lâu dài. Hãy đọc kết quả để hiểu điều kiện, sau đó xác minh bean và hành vi thực tế.

### Kiểm tra Actuator conditions

Nếu ứng dụng đã dùng Spring Boot Actuator, endpoint conditions có thể giúp quan sát kết quả điều kiện auto-configuration. Endpoint này có thể tiết lộ thông tin cấu hình nội bộ; chỉ bật trong môi trường vận hành được bảo vệ và không công khai tùy tiện.

### Kiểm tra bean và filter

Có thể kiểm tra trong integration test:

- Có đúng một SessionRepository được sử dụng.
- Có SessionRepositoryFilter trong Servlet application.
- Có resolver mong muốn, ví dụ cookie hoặc header.
- Redis repository có connection factory hoạt động.
- JDBC repository dùng DataSource và schema mong muốn.
- Không có bean repository trùng hoặc filter session tự đăng ký hai lần.

Một ứng dụng khởi động thành công vẫn có thể dùng sai repository nếu cả Redis và JDBC đều có trên classpath.

## 11. Thay đổi API Servlet và code ứng dụng

Khi chuyển Boot 2 sang Boot 3, rà soát toàn bộ code dùng Servlet API:

- Import javax.servlet.* chuyển sang jakarta.servlet.*.
- Filter, listener, servlet và custom wrapper cần compile với Jakarta API.
- Dependency bên thứ ba phải có phiên bản hỗ trợ Jakarta.
- Container triển khai phải tương thích Jakarta Servlet.
- Test dùng MockMvc và Spring Test phải theo version Spring Boot mới.

Ví dụ filter cũ:

~~~java
import javax.servlet.Filter;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
~~~

Sau khi nâng:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
~~~

Các package không thuộc Jakarta EE không đổi theo quy tắc này. Ví dụ org.springframework.session.web.http vẫn thuộc Spring Session.

Nếu một thư viện cũ chỉ hỗ trợ javax, hãy nâng thư viện đó hoặc thay thế bằng bản tương thích. Không thêm đồng thời hai API namespace để che lỗi compile; việc đó có thể làm runtime khó dự đoán.

## 12. Nâng cấp repository Redis hoặc JDBC theo từng bước

Không nên thay đổi cùng lúc Boot major version, repository, serializer, schema và cookie contract nếu không cần thiết.

Một trình tự có thể kiểm soát:

1. Ghi lại dependency tree và cấu hình đang chạy.
2. Chọn phiên bản Java và Spring Boot mục tiêu.
3. Nâng Spring Session theo BOM tương ứng.
4. Sửa import Servlet javax sang jakarta nếu chuyển Boot 3.
5. Cập nhật property connection và property session đã đổi tên.
6. Xác minh repository bean và filter được tạo đúng.
7. Giữ nguyên cookie/header contract nếu mục tiêu không phải đổi giao thức.
8. Kiểm tra serializer và khả năng đọc session đang lưu.
9. Chạy integration test trên Redis hoặc database thực tế.
10. Triển khai canary hoặc rolling deployment có kế hoạch rollback.

### Redis

Khi nâng Boot/Spring Session, kiểm tra:

- Prefix connection properties.
- Redis client và version tương thích.
- Namespace session.
- Serializer và type metadata.
- Flush/save mode.
- Keyspace notifications nếu cần event hết hạn.
- Các instance cũ và mới có đọc được dữ liệu do nhau ghi không.

Không đổi namespace để chữa lỗi auto-configuration nếu không có kế hoạch chuyển dữ liệu. Namespace mới có thể khiến ứng dụng không tìm thấy các session cũ.

### JDBC

Kiểm tra:

- JDBC driver và version.
- DataSource, pool và transaction configuration.
- Schema script và migration.
- Tên bảng nếu đã tùy chỉnh.
- Kiểu nhị phân của thuộc tính.
- Serializer/converter và class DTO.
- Khả năng đọc session do phiên bản cũ ghi.

Không tự chạy schema initialization có thể xóa hoặc tái tạo bảng trong production. Migration phải được thực hiện theo quy trình quản lý database.

## 13. Kiểm thử tương thích giữa các dòng Boot

Một bộ test nâng cấp nên có nhiều mức.

| Loại test | Điều cần xác minh |
|---|---|
| Context startup test | Application context khởi tạo và repository bean đúng |
| Configuration binding test | Property cũ/mới được bind theo release |
| Servlet integration test | Filter, resolver và HttpSession hoạt động |
| Redis integration test | Tạo, đọc, cập nhật, expire session trên Redis |
| JDBC integration test | Tạo, đọc, lưu, xóa session với schema và driver thật |
| Serialization compatibility test | Instance mới đọc được dữ liệu do phiên bản trước ghi |
| Multi-instance test | Hai instance dùng chung repository và resolver tương thích |
| Rolling deployment test | Instance cũ/mới cùng hoạt động trong giai đoạn chuyển tiếp |

### Ví dụ kiểm thử context

Có thể dùng @@SpringBootTest@@ để khởi động application context và kiểm tra repository được inject. Không chỉ kiểm tra bean tồn tại; cần xác minh đúng implementation mong muốn.

Ví dụ khung:

~~~java
@SpringBootTest
class SessionRepositoryConfigurationTest {

    @Autowired
    SessionRepository<?> sessionRepository;

    @Test
    void shouldCreateSessionRepository() {
        assertThat(sessionRepository).isNotNull();
    }
}
~~~

Đây là khung minh họa. Assertion thực tế cần kiểm tra implementation hoặc hành vi theo cấu hình mong muốn, không nên ép kiểu mù quáng nếu test chạy trên nhiều profile.

### Test property migration

Với mỗi profile:

- Khởi động context bằng cấu hình mới.
- Xác minh Redis host/port hoặc JDBC URL thực sự được dùng.
- Xác minh timeout và namespace.
- Kiểm tra log không còn cảnh báo property cũ.
- Kiểm tra external config và biến môi trường đã cập nhật.

Không dùng test chỉ nạp application-test.properties nếu production dùng Config Server hoặc biến môi trường khác. Cần kiểm tra các nguồn cấu hình tương đương.

## 14. Rolling deployment và session đang hoạt động

Trong rolling deployment, instance mới và cũ có thể chạy song song. Điều này tạo ra một yêu cầu: cả hai phải hiểu dữ liệu session mà instance còn lại ghi, ít nhất trong thời gian chuyển tiếp.

Các điểm cần tương thích:

- Session ID format và cookie/header name.
- Repository namespace hoặc database schema.
- Serializer và class DTO.
- Cách lưu và flush thuộc tính.
- Cách xử lý timeout và expiration.
- Spring Session major version và API lưu trữ.

### Rủi ro khi thay đổi định dạng

Nếu instance mới đổi serializer hoặc DTO, instance cũ có thể không deserialize được dữ liệu mới. Nếu đổi namespace, hai phiên bản có thể nhìn thấy hai tập session khác nhau. Nếu đổi cookie name, client có thể gửi cookie cũ mà instance mới không đọc.

Một số chiến lược:

- Giữ tương thích đọc/ghi trong thời gian rolling.
- Thực hiện migration dữ liệu có kiểm soát.
- Drain instance cũ trước khi bắt đầu ghi định dạng mới.
- Chấp nhận buộc đăng nhập lại nếu chính sách sản phẩm cho phép và có kế hoạch truyền thông.
- Giữ rollback path có thể đọc dữ liệu đã ghi bởi phiên bản mới.

Không nên chỉ rollback binary nếu phiên bản mới đã ghi dữ liệu mà phiên bản cũ không đọc được. Rollback phải tính đến schema, serializer và trạng thái session.

## 15. Các lỗi thường gặp khi nâng Spring Boot

**Ứng dụng không kết nối Redis sau khi nâng Boot.**  
Kiểm tra property prefix spring.redis.* và spring.data.redis.*, profile, biến môi trường, secret và Redis connection factory.

**Không compile do javax.servlet không tồn tại.**  
Chuyển import Servlet sang jakarta.servlet và nâng dependency bên thứ ba hỗ trợ Jakarta.

**Có nhiều SessionRepository hoặc filter.**  
Kiểm tra annotation @Enable..., auto-configuration, bean tùy chỉnh và dependency module trùng.

**Repository JDBC được chọn dù mong muốn Redis.**  
Kiểm tra classpath, spring.session.store-type nếu release hỗ trợ, và điều kiện auto-configuration.

**Session cũ không deserialize được.**  
Kiểm tra Spring Session version, serializer, class DTO, serialVersionUID và khả năng tương thích giữa instance.

**Cookie cũ không được nhận.**  
Kiểm tra resolver, cookie name/path/domain, Secure, SameSite và proxy.

**Ứng dụng khởi động nhưng session không được chia sẻ giữa instance.**  
Kiểm tra Redis endpoint, JDBC database, namespace, schema, serializer và repository implementation.

**Schema JDBC không tương thích sau nâng cấp.**  
So sánh schema script và migration guide của phiên bản mới; kiểm tra thay đổi bằng database test trước production.

**Property cũ vẫn còn trong Config Server.**  
Sửa external configuration, environment variables và deployment manifest, không chỉ sửa file trong repository.

## 16. Quy trình nâng cấp thực tế

Một checklist có thể dùng cho pull request nâng Spring Boot:

1. Xác định Boot version hiện tại và version mục tiêu.
2. Xác nhận Java runtime và Servlet container tương thích.
3. Cập nhật parent/BOM hoặc Gradle plugin.
4. Xóa version Spring Session bị pin riêng nếu BOM quản lý.
5. Cập nhật Spring Session major version phù hợp.
6. Chuyển javax.servlet sang jakarta.servlet nếu nâng sang Boot 3.
7. Cập nhật property Redis prefix và các property bị đổi tên.
8. Kiểm tra spring.session.store-type hoặc cấu hình repository tường minh.
9. Kiểm tra auto-configuration report và repository bean.
10. Kiểm thử cookie/header resolver, timeout, save/flush và lifecycle event.
11. Kiểm thử serialization với session cũ.
12. Chạy integration test với Redis hoặc database thật.
13. Thử rolling deployment và rollback trong môi trường staging.
14. Theo dõi lỗi session, deserialize, connection và tỷ lệ đăng nhập lại sau triển khai.

Mỗi bước nên có bằng chứng trong CI hoặc checklist release. Không xem việc build thành công là đủ để chứng minh dữ liệu session tương thích.

## 17. Tự kiểm tra

1. Spring Boot dựa vào những yếu tố nào để quyết định auto-configuration Spring Session?
2. Vì sao không nên vừa dùng auto-configuration vừa bật annotation repository thủ công mà không kiểm tra?
3. Những thay đổi nền tảng nào đáng chú ý khi chuyển Boot 2 sang Boot 3?
4. Prefix Redis connection properties thường thay đổi như thế nào?
5. Vì sao Spring Session và Spring Data nên theo BOM của Boot?
6. Khi Redis và JDBC modules cùng có trên classpath, cần kiểm tra điều gì?
7. spring.session.timeout khác Redis TTL và cookie Max-Age như thế nào?
8. Spring Boot Properties Migrator hỗ trợ việc nâng cấp ra sao?
9. Vì sao cần kiểm tra repository bean và filter sau khi ứng dụng khởi động?
10. Những dữ liệu nào cần tương thích trong rolling deployment?
11. Vì sao không nên đổi serializer và namespace cùng lúc với Boot major upgrade nếu không có migration plan?
12. Cần kiểm thử những gì trước khi triển khai bản Boot mới lên production?

### Gợi ý trả lời

1. Classpath, application type, bean hiện có, property và các điều kiện auto-configuration.
2. Có thể tạo cấu hình hoặc filter trùng, hoặc làm Boot back-off khỏi repository mong muốn.
3. Java 17, Spring Framework 6, Spring Session 3 và chuyển từ javax.servlet sang jakarta.servlet.
4. Nhiều ứng dụng chuyển từ spring.redis.* ở Boot 2 sang spring.data.redis.* ở Boot 3.
5. BOM giữ các phiên bản Spring Framework, Spring Data và Spring Session tương thích.
6. Dependency tree, store-type nếu release hỗ trợ, bean repository và điều kiện auto-configuration.
7. Timeout là chính sách session, Redis TTL là thời hạn key vật lý, cookie Max-Age là thời hạn cookie phía client.
8. Nó báo một số property đã đổi tên hoặc không còn được hỗ trợ trong quá trình khởi động.
9. Vì ứng dụng có thể khởi động nhưng dùng sai repository hoặc đăng ký filter không đúng.
10. Session ID contract, repository/schema, namespace, serializer, DTO, timeout và cách lưu dữ liệu.
11. Vì instance cũ và mới có thể không đọc được dữ liệu của nhau, dẫn đến mất phiên hoặc lỗi deserialize.
12. Context startup, property binding, repository integration, cookie, TTL, serialization, multi-instance, rolling deployment và rollback.

## Kết luận

Spring Boot auto-configure Spring Session dựa trên dependency, application type, bean và property. Khi chuyển giữa các dòng Boot, cần kiểm tra đồng thời phiên bản Spring Session, Spring Framework, Java, Servlet API, Redis/JDBC properties và repository được chọn. Đặc biệt, Boot 2 sang Boot 3 thường kéo theo chuyển javax.servlet sang jakarta.servlet và thay đổi prefix Redis connection properties.

Hãy để BOM quản lý phiên bản, giữ một cơ chế cấu hình repository rõ ràng, xác minh bean/filter sau khi khởi động và kiểm thử trên kho dữ liệu thật. Khi rolling deployment, các instance cần đọc được dữ liệu session do nhau ghi; serializer, DTO, namespace, schema và Session ID contract phải có kế hoạch tương thích. Auto-configuration chỉ là bước đăng ký bean: tính đúng đắn cuối cùng phải được xác nhận bằng integration test và kiểm tra vận hành.

