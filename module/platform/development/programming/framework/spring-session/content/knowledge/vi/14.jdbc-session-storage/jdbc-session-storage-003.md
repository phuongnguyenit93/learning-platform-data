# @EnableJdbcHttpSession và cấu hình tự động của Spring Boot

Spring Session JDBC lưu trạng thái phiên vào cơ sở dữ liệu quan hệ để nhiều instance ứng dụng có thể dùng chung session. Trong ứng dụng Servlet, Spring Session thay thế cách lưu phiên cục bộ của container bằng một repository JDBC. Ứng dụng vẫn thao tác với `HttpSession`, còn Spring Session đảm nhiệm việc tải, lưu, hết hạn và xóa dữ liệu phiên.

Có hai cách cấu hình phổ biến: bật Spring Session bằng annotation `@EnableJdbcHttpSession` hoặc để Spring Boot tự cấu hình dựa trên dependency, `DataSource` và các thuộc tính `spring.session`. Hai cách cùng hướng tới việc tạo repository JDBC và đăng ký filter quản lý phiên, nhưng mức độ cấu hình tường minh và trách nhiệm khởi tạo khác nhau.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của `@EnableJdbcHttpSession` trong ứng dụng Servlet.
- Cấu hình Spring Session JDBC bằng Spring Boot auto-configuration.
- Chuẩn bị dependency, `DataSource`, transaction manager và schema.
- Phân biệt cấu hình repository với khởi tạo bảng database.
- Chọn một cơ chế cấu hình nhất quán, tránh tạo repository/filter trùng lặp.
- Kiểm thử lưu, đọc, hết hạn và chia sẻ phiên giữa nhiều instance.

## 1. Spring Session JDBC hoạt động ở đâu?

Trong ứng dụng Servlet, `SessionRepositoryFilter` bọc request và response. Khi controller hoặc filter gọi `request.getSession()`, API Servlet được ánh xạ tới repository của Spring Session. Với JDBC, repository thường là `JdbcIndexedSessionRepository` và lưu session cùng thuộc tính vào các bảng quan hệ.

Luồng xử lý khái quát:

~~~mermaid
sequenceDiagram
    participant C as Trình duyệt
    participant F as SessionRepositoryFilter
    participant R as JdbcIndexedSessionRepository
    participant D as Database
    C->>F: Request kèm session cookie
    F->>R: Tìm session theo ID
    R->>D: SELECT session và attributes
    D-->>R: Dữ liệu phiên
    R-->>F: HttpSession được Spring Session quản lý
    F->>F: Controller và filter xử lý request
    F->>R: Lưu thay đổi trước khi response hoàn tất
    R->>D: INSERT/UPDATE/DELETE
    D-->>R: Kết quả transaction
    R-->>F: Hoàn tất lưu phiên
    F-->>C: Response và session cookie nếu cần
~~~

Repository dùng database chung nên instance A có thể tạo phiên và instance B đọc lại phiên đó. Điều này hữu ích khi chạy sau load balancer mà không phụ thuộc sticky session. Tất cả instance cần dùng cùng database, schema, tên bảng, cách tuần tự hóa thuộc tính và chính sách timeout.

Spring Session JDBC là tích hợp Servlet đồng bộ. Không áp dụng `@EnableJdbcHttpSession` cho ứng dụng WebFlux. Ứng dụng reactive cần một reactive session repository phù hợp; JDBC blocking không trở thành reactive chỉ vì được gọi từ handler WebFlux.

## 2. Các dependency cần thiết

Một ứng dụng Spring Boot Servlet dùng JDBC thường cần:

| Dependency | Vai trò |
|---|---|
| `spring-boot-starter-web` | Spring MVC và Servlet runtime |
| `spring-boot-starter-jdbc` | `DataSource`, JDBC và transaction infrastructure |
| `spring-session-jdbc` | Repository lưu phiên bằng JDBC |
| JDBC driver | Kết nối database thực tế, ví dụ PostgreSQL hoặc MySQL |

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Ví dụ dùng PostgreSQL; thay driver theo hệ quản trị cơ sở dữ liệu của dự án. Khi dự án dùng Spring Boot parent hoặc BOM, không tự ghi version cho Spring Session, Spring JDBC và driver nếu BOM đã quản lý chúng. Hãy chọn một dòng Spring Boot tương thích với JDK và dùng phiên bản thư viện do dependency management của dòng đó cung cấp.

Nếu ứng dụng không dùng Spring Boot, nhóm phát triển phải tự quản lý phiên bản Spring Framework, Spring Session, JDBC driver và các thư viện liên quan. Cần kiểm tra ma trận tương thích trước khi ghép phiên bản.

## 3. Cấu hình bằng Spring Boot auto-configuration

Với Spring Boot, cách đơn giản thường là thêm `spring-session-jdbc`, cung cấp `DataSource` và đặt các thuộc tính `spring.session`. Boot nhận diện các thành phần này và cấu hình repository JDBC cùng filter Servlet phù hợp.

Ví dụ `application.yml` cho PostgreSQL:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/appdb
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  session:
    store-type: jdbc
    timeout: 30m
    jdbc:
      initialize-schema: always
      table-name: SPRING_SESSION
      cleanup-cron: "0 * * * * *"
~~~

Các giá trị trong ví dụ:

- `spring.datasource.*` cấu hình kết nối database. Trong production, lấy thông tin xác thực từ secret manager hoặc biến môi trường, không commit mật khẩu thật vào source control.
- `spring.session.store-type: jdbc` yêu cầu dùng JDBC khi dòng Boot hỗ trợ thuộc tính lựa chọn store này. Nếu chỉ có một loại session repository trên classpath, một số phiên bản có thể tự suy luận; khi có nhiều store, hãy cấu hình tường minh theo tài liệu phiên bản.
- `spring.session.timeout` đặt thời gian không hoạt động tối đa của phiên. Chọn giá trị phù hợp chính sách bảo mật và trải nghiệm.
- `spring.session.jdbc.initialize-schema` điều khiển việc khởi tạo schema. `always` hữu ích trong môi trường phát triển hoặc test; production nên quản lý schema bằng migration.
- `table-name` xác định tên bảng mà repository sử dụng. Nếu đổi tên bảng, schema trong database cũng phải được tạo với đúng tên và cấu trúc.
- `cleanup-cron` cấu hình lịch dọn các phiên hết hạn nếu property này được hỗ trợ trong dòng Boot đang dùng. Hãy xác minh cú pháp và giá trị mặc định theo phiên bản.

Không sao chép nguyên cấu hình vào mọi phiên bản Spring Boot mà không kiểm tra metadata cấu hình. Các property có thể thay đổi theo dòng phát hành. Dùng cấu hình được IDE metadata hoặc tài liệu chính thức của đúng phiên bản xác nhận.

### 3.1. Khi nào cần chỉ định store-type?

Nếu ứng dụng chỉ có một repository session khả dụng, Boot có thể tự chọn dựa trên dependency và bean có mặt. Khi classpath chứa nhiều loại store, ví dụ Redis và JDBC, hãy chỉ rõ store được dùng để tránh phụ thuộc vào thứ tự auto-configuration hoặc điều kiện runtime:

~~~yaml
spring:
  session:
    store-type: jdbc
~~~

Nếu phiên bản Boot dự án không còn cung cấp property này hoặc có cơ chế chọn store khác, hãy dùng cấu hình được hỗ trợ bởi phiên bản đó. Sau khi khởi động, kiểm tra log auto-configuration và bean repository thực tế để xác nhận ứng dụng đang dùng JDBC.

## 4. Khởi tạo schema cho Spring Session

Spring Session JDBC cần các bảng lưu metadata phiên và thuộc tính. Schema tiêu chuẩn thường gồm:

| Bảng | Vai trò |
|---|---|
| `SPRING_SESSION` | Metadata phiên như primary ID, session ID, thời điểm tạo, lần truy cập gần nhất, khoảng inactivity, thời điểm hết hạn và principal name |
| `SPRING_SESSION_ATTRIBUTES` | Các thuộc tính phiên đã được tuần tự hóa, liên kết với phiên qua khóa chính |

Tên cột, kiểu dữ liệu, chỉ mục và kiểu khóa có thể khác theo database vendor. Spring Session cung cấp schema script tương ứng cho các hệ quản trị được hỗ trợ. Hãy dùng đúng script theo database thực tế, không tự lấy schema PostgreSQL rồi áp dụng nguyên trạng lên SQL Server hoặc Oracle.

Trong môi trường phát triển, có thể để Spring Boot khởi tạo schema:

~~~yaml
spring:
  session:
    jdbc:
      initialize-schema: always
~~~

Với production, nên để công cụ migration như Flyway hoặc Liquibase tạo và nâng cấp bảng:

~~~yaml
spring:
  session:
    jdbc:
      initialize-schema: never
~~~

Sau đó, đưa schema Spring Session phù hợp database vào migration scripts của dự án. Migration cần được chạy trước khi instance ứng dụng bắt đầu nhận traffic. Không để nhiều instance cùng khởi động và đồng thời chạy DDL trên schema production nếu quy trình triển khai không kiểm soát việc đó.

### 4.1. Đổi tên bảng

Nếu dùng tên bảng riêng, ví dụ `APP_SESSION` và `APP_SESSION_ATTRIBUTES`, phải bảo đảm repository và schema migration thống nhất. Thuộc tính `table-name` của repository thường điều khiển tên bảng chính và bảng thuộc tính theo quy ước của implementation; hãy kiểm tra cách ghép tên bảng của phiên bản đang dùng.

Không chỉ đổi property mà quên đổi schema. Khi repository truy cập bảng không tồn tại hoặc thiếu cột/index cần thiết, ứng dụng có thể khởi động lỗi hoặc request đầu tiên truy cập session mới gặp lỗi SQL.

## 5. Cấu hình tường minh bằng @EnableJdbcHttpSession

Khi không dùng Spring Boot auto-configuration cho session hoặc cần cấu hình Java tường minh, có thể bật Spring Session JDBC bằng `@EnableJdbcHttpSession`.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.FlushMode;
import org.springframework.session.SaveMode;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession(
        maxInactiveIntervalInSeconds = 1800,
        tableName = "SPRING_SESSION",
        flushMode = FlushMode.ON_SAVE,
        saveMode = SaveMode.ON_SET_ATTRIBUTE
)
public class JdbcSessionConfiguration {
}
~~~

Annotation này kích hoạt cấu hình Spring Session JDBC cho ứng dụng Servlet. Nó đăng ký thành phần repository và `SessionRepositoryFilter` để ánh xạ `HttpSession` sang lưu trữ JDBC.

Các tham số minh họa:

- `maxInactiveIntervalInSeconds` đặt timeout không hoạt động, tính bằng giây.
- `tableName` chọn tên bảng phiên theo khả năng của phiên bản.
- `flushMode` xác định thời điểm thay đổi được đẩy xuống repository.
- `saveMode` xác định phạm vi thuộc tính được lưu.

Hãy xác minh các thuộc tính annotation trong đúng phiên bản Spring Session đang dùng. Nếu một thuộc tính không tồn tại ở phiên bản cũ, hãy dùng cấu hình được phiên bản đó hỗ trợ.

Ứng dụng cần có `DataSource` phù hợp. Trong cấu hình Spring thuần, thường cung cấp cả transaction manager:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
~~~

Đoạn import transaction manager này dùng được cho cấu hình Spring JDBC tương ứng; với ứng dụng Jakarta Servlet, namespace Servlet thay đổi nhưng `javax.sql.DataSource` vẫn là API Java SE. Nếu dùng Spring Boot, starter JDBC thường tự cấu hình `DataSource` và transaction manager khi có đủ thông tin kết nối, nên không cần tự khai báo lại nếu không có yêu cầu đặc biệt.

`@EnableJdbcHttpSession` không thay thế việc tạo database hoặc bảng. Schema phải tồn tại trước khi repository truy cập. Annotation cũng không phải cấu hình cho reactive `WebSession`.

## 6. So sánh hai cách cấu hình

| Tiêu chí | Spring Boot auto-configuration | `@EnableJdbcHttpSession` |
|---|---|---|
| Cách kích hoạt | Dependency, `DataSource` và property phù hợp | Annotation trên class `@Configuration` |
| Repository | Boot tạo repository theo điều kiện và store đã chọn | Cấu hình Spring Session JDBC được import bởi annotation |
| Filter | Boot đăng ký filter theo auto-configuration | Cấu hình annotation đăng ký `SessionRepositoryFilter` |
| Timeout | Thường đặt qua `spring.session.timeout` | Có thể đặt bằng `maxInactiveIntervalInSeconds` |
| Schema | Boot có thể khởi tạo schema theo property | Cần tự bảo đảm schema được tạo bởi migration hoặc script |
| Phù hợp | Ứng dụng Boot dùng cấu hình chuẩn | Ứng dụng Spring cấu hình thủ công hoặc cần cấu hình Java tường minh |

Với ứng dụng Spring Boot thông thường, ưu tiên auto-configuration để giảm cấu hình lặp. Dùng annotation khi dự án chủ động quản lý cấu hình Spring Session bằng Java hoặc không dựa vào cơ chế auto-configuration của Boot.

Tránh bật cả hai cơ chế một cách tùy tiện. Việc cùng khai báo annotation và để Boot tự cấu hình có thể tạo ra cấu hình cạnh tranh, bean trùng hoặc làm khó xác định repository/filter nào đang hoạt động. Nếu có lý do kết hợp, cần kiểm tra điều kiện auto-configuration, bean thực tế và thứ tự filter trong phiên bản dự án.

## 7. Filter order và tích hợp Servlet

`SessionRepositoryFilter` cần chạy trước các filter khác có sử dụng `HttpSession`, bao gồm các filter bảo mật. Khi filter này bọc request/response, các lời gọi `getSession()` từ những thành phần phía sau mới được chuyển tới Spring Session repository.

Trong Spring Boot, thứ tự đăng ký filter thường được cấu hình tự động. Nếu ứng dụng tự đăng ký filter hoặc dùng container bên ngoài, hãy kiểm tra thứ tự thực tế. Một filter chạy trước `SessionRepositoryFilter` có thể truy cập session cục bộ của container thay vì session JDBC, gây ra hai trạng thái phiên khác nhau.

Nếu dùng Spring Security, kiểm thử đăng nhập, lưu SecurityContext, session fixation protection và logout. Spring Security cần làm việc với session do Spring Session quản lý; không để một filter tùy chỉnh vô tình tạo session cục bộ trước filter của Spring Session.

## 8. Transaction và quyền truy cập database

Spring Session JDBC thực hiện các thao tác đọc/ghi trên database. Database phải cho phép ứng dụng:

- Đọc metadata phiên và thuộc tính.
- Tạo phiên mới.
- Cập nhật thời gian truy cập và các thuộc tính.
- Xóa phiên hết hạn hoặc bị logout.
- Dọn dữ liệu phụ trợ theo schema và repository.

Trong production, dùng tài khoản database có quyền tối thiểu cần thiết. Tài khoản migration có thể có quyền DDL để tạo bảng và chỉ mục; tài khoản runtime thường chỉ cần quyền DML trên các bảng Spring Session.

Transaction manager cần trỏ tới đúng `DataSource` mà repository sử dụng. Nếu ứng dụng có nhiều database, đừng để repository session vô tình dùng nhầm transaction manager hoặc datasource nghiệp vụ. Việc cấu hình sai có thể khiến thao tác session không nằm trong transaction mong muốn hoặc kết nối đến database không có schema.

Đặt connection pool đủ cho tải session cùng tải nghiệp vụ. Nếu mỗi request cần đọc và ghi session, connection pool quá nhỏ có thể làm tăng thời gian chờ và gây timeout. Theo dõi số connection đang sử dụng, thời gian lấy connection, độ trễ SQL và số lỗi database.

## 9. Timeout, cleanup và chỉ mục

Timeout session là thời gian không hoạt động tối đa, không phải thời gian sống tuyệt đối của tài khoản. Khi session hết hạn, repository phải xem nó là không còn hợp lệ và cơ chế cleanup có thể xóa bản ghi tương ứng.

Spring Session JDBC thường lưu thời điểm hết hạn trong bảng session và có tác vụ dọn dữ liệu hết hạn theo lịch. Cấu hình cleanup cron có thể được đặt qua annotation hoặc Boot property tùy phiên bản. Việc cleanup chạy định kỳ có nghĩa bản ghi hết hạn có thể còn trong database một khoảng thời gian sau khi không còn được coi là phiên hợp lệ.

Không dùng việc “bản ghi vẫn còn trong bảng” làm bằng chứng phiên vẫn có hiệu lực. Request tải phiên phải được repository kiểm tra theo thời gian hết hạn và chính sách hiện tại.

Schema chuẩn có các chỉ mục phục vụ truy vấn theo session ID, thời gian hết hạn và principal. Nếu thay schema, cần giữ các chỉ mục phù hợp với truy vấn repository. Thiếu index có thể làm truy vấn và cleanup chậm khi bảng lớn.

## 10. Triển khai nhiều instance

Khi nhiều instance cùng dùng Spring Session JDBC:

- Tất cả node trỏ tới cùng database hoặc cụm database có semantics nhất quán phù hợp.
- Schema, tên bảng, kiểu dữ liệu và chỉ mục phải giống nhau.
- Timeout, cookie resolver và cấu hình session phải thống nhất.
- Cùng dùng cách tuần tự hóa thuộc tính tương thích.
- Các node cần dùng phiên bản Spring Session tương thích trong giai đoạn rolling deployment.

Không dùng sticky session như điều kiện để dữ liệu phiên tồn tại. Client có thể được định tuyến tới bất kỳ instance nào; repository chung là nơi giữ trạng thái. Sticky session có thể được dùng như tối ưu định tuyến, nhưng không thay thế yêu cầu chia sẻ dữ liệu.

Khi nâng phiên bản ứng dụng hoặc schema, hãy triển khai migration theo thứ tự: chuẩn bị schema tương thích, triển khai các node có thể đọc dữ liệu hiện tại, chuyển traffic, theo dõi lỗi, rồi mới loại bỏ cấu trúc cũ. Nếu thay serializer hoặc class được lưu trong session, phải tính đến các phiên do node cũ tạo ra.

## 11. Kiểm thử cấu hình JDBC

Một bộ kiểm thử tối thiểu nên bao gồm:

1. Ứng dụng khởi động và kết nối được database.
2. Schema có đầy đủ bảng, cột và index mà repository yêu cầu.
3. Request tạo session và ghi một thuộc tính.
4. Request tiếp theo gửi cookie session ID và đọc lại đúng thuộc tính.
5. Request cập nhật hoặc xóa thuộc tính; thay đổi được lưu sau khi response hoàn tất.
6. Session hết hạn theo timeout và không còn được chấp nhận.
7. Logout xóa phiên ở repository và response xử lý cookie phù hợp.
8. Hai instance dùng chung database có thể đọc cùng một session.
9. Database tạm thời không khả dụng; ứng dụng xử lý lỗi theo chính sách đã thiết kế.

Trong test, có thể dùng database container hoặc database tích hợp phù hợp. H2 hữu ích cho một số kiểm thử nhanh, nhưng không thay thế hoàn toàn kiểm thử trên cùng loại database production vì kiểu cột, SQL dialect, transaction và index có thể khác.

Kiểm tra dữ liệu trực tiếp bằng SQL trong môi trường test:

~~~sql
SELECT PRIMARY_ID, SESSION_ID, CREATION_TIME,
       LAST_ACCESS_TIME, EXPIRY_TIME, PRINCIPAL_NAME
FROM SPRING_SESSION;
~~~

Và thuộc tính:

~~~sql
SELECT SESSION_PRIMARY_ID, ATTRIBUTE_NAME
FROM SPRING_SESSION_ATTRIBUTES;
~~~

Tên bảng/cột trong ví dụ là schema phổ biến. Hãy đối chiếu schema script đúng database và phiên bản Spring Session. Không truy vấn hoặc xuất `ATTRIBUTE_BYTES` ở production nếu không có lý do vận hành được phê duyệt; trường này có thể chứa dữ liệu nhạy cảm đã tuần tự hóa.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Ứng dụng không tạo được repository JDBC | Thiếu `spring-session-jdbc`, `DataSource` hoặc cấu hình store | Kiểm tra dependency, datasource và điều kiện auto-configuration |
| Lỗi thiếu bảng khi request tạo session | Schema chưa được khởi tạo hoặc migration chưa chạy | Tạo schema đúng database trước khi nhận traffic |
| Boot chọn Redis thay vì JDBC | Có nhiều store và chưa chọn rõ repository | Đặt store type nếu phiên bản hỗ trợ; kiểm tra repository bean thực tế |
| Controller thấy session nhưng filter khác không thấy | Filter chạy trước `SessionRepositoryFilter` | Sửa thứ tự filter và kiểm thử integration |
| Instance A đọc được nhưng instance B không | Node dùng datasource, schema, serializer hoặc cookie khác nhau | Đồng bộ cấu hình giữa các instance |
| Bảng session tăng kích thước liên tục | Cleanup không chạy, timeout quá dài hoặc index/SQL cleanup lỗi | Kiểm tra cleanup schedule, log SQL, index và timeout |
| Khởi động production gặp lỗi DDL | Tài khoản runtime không có quyền tạo bảng hoặc schema chưa được migration | Dùng migration riêng và đặt initialize-schema phù hợp |
| Request chậm khi tải cao | Connection pool nhỏ hoặc truy vấn session thiếu index | Đo pool, SQL latency và kiểm tra schema/index |

## 13. Checklist trước khi đưa JDBC session vào production

- [ ] Ứng dụng là Servlet/MVC và dùng `HttpSession`.
- [ ] Có `spring-session-jdbc`, JDBC starter và driver phù hợp.
- [ ] Đã chọn Boot auto-configuration hoặc cấu hình annotation tường minh.
- [ ] `DataSource` và transaction manager trỏ đúng database.
- [ ] Schema đúng vendor, tên bảng và index đã được tạo trước khi nhận traffic.
- [ ] Production dùng Flyway/Liquibase hoặc quy trình migration được kiểm soát.
- [ ] Timeout và cleanup schedule phù hợp chính sách.
- [ ] Tất cả instance dùng cùng schema, serializer, cookie và timeout.
- [ ] Filter order tương thích với Spring Security và filter tùy chỉnh.
- [ ] Đã kiểm thử tạo, đọc, cập nhật, xóa và hết hạn session.
- [ ] Đã kiểm thử nhiều instance và lỗi kết nối database.
- [ ] Database credentials và dữ liệu thuộc tính session được bảo vệ.

`@EnableJdbcHttpSession` cung cấp cách cấu hình Spring Session JDBC tường minh cho ứng dụng Servlet; Spring Boot auto-configuration giúp cấu hình repository từ dependency, `DataSource` và các property `spring.session`. Dù chọn cách nào, ứng dụng vẫn cần schema đúng database, filter chạy đúng thứ tự, timeout và cleanup được kiểm soát, cùng integration test chứng minh phiên được chia sẻ giữa các instance. Với dự án Boot thông thường, auto-configuration thường giảm cấu hình thủ công; annotation phù hợp khi dự án chủ động quản lý Spring Session bằng Java configuration.
