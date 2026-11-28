# Spring Session JDBC và nhu cầu dùng cơ sở dữ liệu quan hệ

Spring Session cho phép ứng dụng Servlet tiếp tục sử dụng HttpSession quen thuộc, trong khi dữ liệu phiên được lưu trong một kho dùng chung. Khi chọn JDBC, session được lưu trong các bảng của cơ sở dữ liệu quan hệ thông qua JdbcIndexedSessionRepository. Nhiều instance ứng dụng có thể cùng đọc và cập nhật session nếu chúng kết nối tới cùng database, dùng cùng schema, cấu hình và định dạng dữ liệu tương thích.

JDBC là lựa chọn phù hợp khi tổ chức đã có nền tảng cơ sở dữ liệu quan hệ được vận hành tốt, muốn giảm số hệ thống cần quản lý hoặc cần đặt dữ liệu session trong hạ tầng database hiện có. Tuy nhiên, session có đặc tính truy cập thường xuyên và thời hạn ngắn; đưa chúng vào database nghiệp vụ có thể làm tăng tải ghi, transaction, index và công việc cleanup. Vì vậy, quyết định dùng JDBC cần dựa trên yêu cầu vận hành và tải thực tế.

Bài này giải thích Spring Session JDBC hoạt động như thế nào, khi nào nên chọn cơ sở dữ liệu quan hệ, cách cấu hình repository và schema, cách dữ liệu session được lưu, xử lý hết hạn, transaction, bảo mật, kiểm thử và vận hành nhiều instance.

## 1. Spring Session JDBC giải quyết vấn đề gì?

Trong ứng dụng Servlet mặc định, HttpSession thường do Servlet container quản lý. Khi triển khai nhiều instance, session trong bộ nhớ của một node không tự động có mặt ở node khác. Sticky session ở load balancer có thể giữ request của người dùng trên cùng node, nhưng không giải quyết hoàn toàn việc node restart, scale hoặc failover.

Spring Session thay thế phần lưu trữ session mặc định bằng một repository. Với JDBC, repository lưu dữ liệu trong cơ sở dữ liệu quan hệ:

~~~text
Browser
   |
   | Cookie chứa session ID
   v
Load balancer
   |
   +------------------+
   |                  |
   v                  v
App instance A     App instance B
   |                  |
   +--------+---------+
            |
            v
      JdbcIndexedSessionRepository
            |
            v
     Shared relational database
       SPRING_SESSION
       SPRING_SESSION_ATTRIBUTES
~~~

Khi request đến instance A, Spring Session dùng session ID trong cookie để tìm session trong database. Request tiếp theo có thể đến instance B; node B tìm cùng session ID trong cùng repository và tiếp tục xử lý.

Spring Session JDBC giúp:

- Chia sẻ session giữa nhiều instance mà không phụ thuộc bộ nhớ cục bộ của từng node.
- Giữ session qua lần restart hoặc thay thế instance, miễn là database và dữ liệu session còn hợp lệ.
- Dùng cơ chế backup, replication, giám sát, kiểm soát truy cập và quy trình khôi phục database đã có.
- Tra cứu session theo session ID và theo principal name thông qua repository indexed.
- Quản lý timeout không hoạt động và dọn các dòng session hết hạn bằng tác vụ cleanup.

Spring Session không biến database thành nơi lưu mọi trạng thái nghiệp vụ. Session vẫn nên chứa dữ liệu nhỏ gắn với tương tác hiện tại, chẳng hạn locale, một số lựa chọn giao diện, mã tham chiếu giỏ hàng hoặc SecurityContext. Đơn hàng, tồn kho, thanh toán và dữ liệu cần tính nhất quán nghiệp vụ vẫn thuộc các bảng và service nghiệp vụ.

## 2. Khi nào nên chọn JDBC?

Cơ sở dữ liệu quan hệ thường phù hợp nếu tổ chức đã có hạ tầng SQL ổn định, đội vận hành hiểu rõ database và tải session có thể đáp ứng bằng dung lượng hiện tại hoặc một database chuyên dụng.

| Nhu cầu hoặc điều kiện | JDBC có thể phù hợp khi |
|---|---|
| Hạ tầng hiện có | Tổ chức đã vận hành PostgreSQL, MySQL, SQL Server, Oracle hoặc database quan hệ được Spring Session hỗ trợ |
| Quản trị dữ liệu | Cần tận dụng backup, replication, giám sát, phân quyền và quy trình khôi phục của database |
| Nhiều instance | Các node có thể kết nối tới cùng database với độ trễ và độ sẵn sàng phù hợp |
| Truy vấn quản trị | Cần tìm session theo principal name hoặc thời điểm hết hạn bằng các index có sẵn |
| Mức tải | Số lượng session và tần suất cập nhật không làm quá tải database |
| Kiến trúc triển khai | Có thể tách pool hoặc database session khỏi tải truy vấn nghiệp vụ khi cần |

JDBC có thể kém phù hợp nếu ứng dụng có lượng request rất lớn, session được cập nhật liên tục hoặc database quan hệ đang là điểm nghẽn của giao dịch nghiệp vụ. Mỗi lần truy cập session có thể cập nhật metadata và thời hạn, do đó một endpoint chỉ đọc dữ liệu nghiệp vụ vẫn có thể phát sinh thao tác ghi session nếu nó truy cập HttpSession.

### So sánh JDBC với Redis

| Tiêu chí | Spring Session JDBC | Spring Session Redis |
|---|---|---|
| Kho dữ liệu | Bảng trong cơ sở dữ liệu quan hệ | Key và cấu trúc dữ liệu Redis |
| Hết hạn | Cột thời gian hết hạn và job cleanup | TTL của key và cơ chế expiration |
| Chia sẻ giữa instance | Qua cùng database | Qua cùng Redis deployment |
| Tra cứu principal | JdbcIndexedSessionRepository hỗ trợ index principal | RedisIndexedSessionRepository hỗ trợ index principal |
| Sự kiện vòng đời | JdbcIndexedSessionRepository không phát session event tích hợp như Redis indexed | Redis indexed có cơ chế event dựa trên notification/Pub/Sub |
| Vận hành | Dùng công cụ SQL, transaction, backup và database monitoring | Cần vận hành Redis, memory, persistence, replication và notification |
| Tải ghi | Có thể tạo UPDATE/INSERT và transaction trên database | Có thể tạo lệnh Redis và lưu lượng replication |
| Phù hợp | Tổ chức muốn dùng hạ tầng SQL và có tải phù hợp | Tổ chức cần kho session chuyên dụng có đặc tính Redis |

Không có lựa chọn tốt nhất cho mọi hệ thống. Hãy so sánh độ trễ, thông lượng, mức sẵn sàng, khả năng phục hồi, chi phí vận hành và yêu cầu tra cứu. Không chọn JDBC chỉ vì database đã có sẵn nếu session traffic có thể cạnh tranh trực tiếp với giao dịch quan trọng.

## 3. JdbcIndexedSessionRepository và API session chung

Spring Session JDBC sử dụng JdbcIndexedSessionRepository. Repository này triển khai SessionRepository và FindByIndexNameSessionRepository, vì vậy ứng dụng có thể:

- Tạo session.
- Tìm session theo session ID.
- Lưu thay đổi session.
- Xóa session.
- Tìm các session theo principal name.

Trong ứng dụng Servlet, SessionRepositoryFilter kết nối repository với HttpSession. Controller và service vẫn có thể dùng HttpSession như trước:

~~~java
@GetMapping("/preferences")
public PreferencesView preferences(HttpSession session) {
    String locale = (String) session.getAttribute("app.locale");
    return preferencesService.load(locale);
}
~~~

Controller không cần tự viết SQL để tìm session. Spring Session filter tải session qua repository và lưu các thay đổi theo cấu hình FlushMode/SaveMode.

Một lợi ích của repository indexed là tra cứu session theo principal:

~~~java
Map<String, ? extends Session> userSessions =
        sessionRepository.findByPrincipalName(principalName);
~~~

Kết quả là ánh xạ từ session ID tới đối tượng Session. Không trả trực tiếp đối tượng Session ra API; hãy tạo DTO chỉ chứa dữ liệu an toàn. Session có thể chứa SecurityContext và các thuộc tính nội bộ.

## 4. Cấu hình Spring Session JDBC

### Dependency

Ứng dụng cần Spring Session JDBC và JDBC support của Spring Boot hoặc Spring Framework. Với Spring Boot, thường dùng starter JDBC để cung cấp DataSource và starter Spring Session JDBC để cung cấp repository:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-jdbc</artifactId>
    </dependency>
</dependencies>
~~~

Phiên bản dependency nên được quản lý bằng Spring Boot dependency management hoặc BOM tương thích. Không tự chọn một phiên bản Spring Session không tương thích với Spring Framework/Spring Boot của ứng dụng.

### Cấu hình Java

Với ứng dụng Servlet dùng cấu hình Java, bật JDBC session:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    tableName = "SPRING_SESSION"
)
public class SessionConfiguration {
}
~~~

Cấu hình này yêu cầu một DataSource có thể được inject vào Spring Session. Trong ứng dụng Spring Boot, DataSource thường được tạo từ cấu hình datasource hiện có. Trong ứng dụng Spring Framework độc lập, cần khai báo DataSource và transaction infrastructure phù hợp.

EnableJdbcHttpSession kích hoạt cấu hình JDBC và tạo bean Spring Session filter có tên springSessionRepositoryFilter. Filter bọc request để lời gọi HttpSession đi qua JdbcIndexedSessionRepository.

Không bật đồng thời EnableJdbcHttpSession và một cấu hình repository session khác cho cùng Servlet application. Nếu ứng dụng dùng Spring Boot auto-configuration, hãy kiểm tra cơ chế auto-config đang hoạt động trước khi tự khai báo annotation để tránh tạo cấu hình hoặc filter trùng.

### Cấu hình Spring Boot

Với Spring Boot, có thể dùng starter và cấu hình DataSource trong application.yml. Ví dụ minh họa:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/appdb
    username: app_session_user
    password: ${SESSION_DB_PASSWORD}
    hikari:
      maximum-pool-size: 20

  session:
    jdbc:
      initialize-schema: never
      table-name: SPRING_SESSION
    timeout: 30m
~~~

Tên property và các khả năng cấu hình có thể thay đổi theo phiên bản Spring Boot. Hãy đối chiếu configuration metadata của phiên bản đang dùng. Không lưu mật khẩu trực tiếp trong file cấu hình được commit; dùng secret manager hoặc biến môi trường được bảo vệ.

Trong production, thường nên quản lý schema bằng công cụ migration như Flyway hoặc Liquibase và đặt initialize-schema thành never. Cấu hình tự khởi tạo schema có thể hữu ích trong môi trường phát triển hoặc test, nhưng quyền tạo bảng không nên được cấp tùy tiện cho tài khoản runtime production.

## 5. Schema JDBC gồm những bảng nào?

Schema mặc định của Spring Session JDBC thường gồm hai bảng:

- SPRING_SESSION lưu metadata của session.
- SPRING_SESSION_ATTRIBUTES lưu từng thuộc tính của session.

Cấu trúc khái niệm:

~~~text
SPRING_SESSION
  PRIMARY_ID
  SESSION_ID
  CREATION_TIME
  LAST_ACCESS_TIME
  MAX_INACTIVE_INTERVAL
  EXPIRY_TIME
  PRINCIPAL_NAME

SPRING_SESSION_ATTRIBUTES
  SESSION_PRIMARY_ID
  ATTRIBUTE_NAME
  ATTRIBUTE_BYTES
~~~

Các cột chính:

| Cột | Vai trò |
|---|---|
| PRIMARY_ID | Khóa nội bộ của dòng session |
| SESSION_ID | Session ID mà client gửi qua cookie |
| CREATION_TIME | Thời điểm tạo session |
| LAST_ACCESS_TIME | Thời điểm truy cập gần nhất |
| MAX_INACTIVE_INTERVAL | Thời gian không hoạt động tối đa, tính bằng giây |
| EXPIRY_TIME | Thời điểm session hết hạn, dùng cho tra cứu và cleanup |
| PRINCIPAL_NAME | Tên principal, nếu repository xác định được |
| SESSION_PRIMARY_ID | Khóa ngoại từ bảng thuộc tính tới dòng session |
| ATTRIBUTE_NAME | Tên thuộc tính trong HttpSession |
| ATTRIBUTE_BYTES | Nội dung thuộc tính đã được tuần tự hóa |

SPRING_SESSION có khóa chính nội bộ PRIMARY_ID và chỉ mục duy nhất trên SESSION_ID. Các index thường có thêm EXPIRY_TIME để hỗ trợ cleanup và PRINCIPAL_NAME để tra cứu session theo người dùng. Bảng thuộc tính dùng khóa chính kết hợp SESSION_PRIMARY_ID và ATTRIBUTE_NAME; khóa ngoại liên kết tới bảng session và thường xóa cascade khi session bị xóa.

### Ví dụ schema PostgreSQL ở mức minh họa

~~~sql
CREATE TABLE SPRING_SESSION (
    PRIMARY_ID CHAR(36) NOT NULL,
    SESSION_ID CHAR(36) NOT NULL,
    CREATION_TIME BIGINT NOT NULL,
    LAST_ACCESS_TIME BIGINT NOT NULL,
    MAX_INACTIVE_INTERVAL INT NOT NULL,
    EXPIRY_TIME BIGINT NOT NULL,
    PRINCIPAL_NAME VARCHAR(100),
    CONSTRAINT SPRING_SESSION_PK PRIMARY KEY (PRIMARY_ID)
);

CREATE UNIQUE INDEX SPRING_SESSION_IX1
    ON SPRING_SESSION (SESSION_ID);

CREATE INDEX SPRING_SESSION_IX2
    ON SPRING_SESSION (EXPIRY_TIME);

CREATE INDEX SPRING_SESSION_IX3
    ON SPRING_SESSION (PRINCIPAL_NAME);

CREATE TABLE SPRING_SESSION_ATTRIBUTES (
    SESSION_PRIMARY_ID CHAR(36) NOT NULL,
    ATTRIBUTE_NAME VARCHAR(200) NOT NULL,
    ATTRIBUTE_BYTES BYTEA NOT NULL,
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_PK
        PRIMARY KEY (SESSION_PRIMARY_ID, ATTRIBUTE_NAME),
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_FK
        FOREIGN KEY (SESSION_PRIMARY_ID)
        REFERENCES SPRING_SESSION(PRIMARY_ID)
        ON DELETE CASCADE
);
~~~

Đây là ví dụ cho PostgreSQL để giải thích cấu trúc. Không dùng nguyên xi cho mọi database: kiểu dữ liệu nhị phân có thể là BLOB, BYTEA hoặc kiểu tương ứng; cú pháp index, khóa ngoại và giới hạn tên cũng khác nhau. Spring Session cung cấp schema script theo database được hỗ trợ. Hãy dùng đúng script cho dialect thực tế hoặc chuyển nội dung tương ứng vào migration của dự án.

Không tự sửa tên cột hoặc kiểu dữ liệu mà không kiểm tra SQL repository đang sử dụng. Nếu đổi tên bảng, hãy cấu hình tableName tương ứng và bảo đảm migration tạo đúng cả bảng session lẫn bảng attributes cùng các index.

## 6. Tại sao thuộc tính được lưu ở bảng riêng?

Metadata session có cấu trúc tương đối cố định, trong khi thuộc tính do ứng dụng thêm có số lượng và kiểu dữ liệu thay đổi. Tách thuộc tính sang bảng riêng giúp repository thêm, cập nhật hoặc xóa một thuộc tính theo tên mà không cần tạo một cột SQL cho từng thuộc tính ứng dụng.

Ví dụ một session có thể có:

~~~text
SPRING_SESSION
  PRIMARY_ID = p-100
  SESSION_ID = s-abc
  LAST_ACCESS_TIME = ...
  EXPIRY_TIME = ...
  PRINCIPAL_NAME = linh.nguyen

SPRING_SESSION_ATTRIBUTES
  p-100 | SPRING_SECURITY_CONTEXT | <serialized bytes>
  p-100 | app.locale             | <serialized bytes>
  p-100 | app.activeCartId       | <serialized bytes>
~~~

ATTRIBUTE_BYTES là dữ liệu đã được chuyển đổi/tuần tự hóa. Không giả định rằng có thể đọc trực tiếp giá trị bằng SQL text. Tùy serializer, dữ liệu có thể là byte array không thể diễn giải bằng mắt.

Không nên lưu entity JPA, proxy Hibernate, kết nối, stream hoặc object có vòng đời request vào session. Ưu tiên ID tham chiếu và DTO nhỏ. Cách này giảm kích thước dữ liệu, thời gian serialize và rủi ro không tương thích khi nâng cấp ứng dụng.

## 7. Tuần tự hóa và tương thích phiên bản

JDBC repository cần chuyển thuộc tính Java thành dữ liệu nhị phân để lưu trong ATTRIBUTE_BYTES, sau đó chuyển lại thành object khi đọc. Cơ chế chuyển đổi phụ thuộc ConversionService và cấu hình serializer của ứng dụng. Cấu hình mặc định thường dựa trên Java serialization cho các thuộc tính Serializable.

Nếu session tồn tại qua nhiều lần triển khai, serializer và class của thuộc tính phải tương thích. Những thay đổi có thể làm session cũ không đọc được gồm:

- Đổi package hoặc tên class.
- Thay kiểu field hoặc class hierarchy.
- Đổi serialVersionUID không tương thích.
- Xóa hoặc đổi tên enum value.
- Thay serializer từ Java serialization sang JSON mà không có bước chuyển đổi.
- Nâng cấp Spring Security khiến class principal hoặc Authentication thay đổi.

Đối với dữ liệu cần giữ qua deploy, hãy kiểm thử bằng fixture được tạo bởi artifact cũ. Không chỉ tạo object bằng class mới rồi serialize trong cùng test, vì cách đó không xác nhận tương thích ngược.

Các nguyên tắc thực tế:

- Lưu ID tham chiếu thay vì toàn bộ entity.
- Dùng kiểu dữ liệu nhỏ và ổn định.
- Không dùng enum ordinal làm dữ liệu lưu trữ lâu dài.
- Nếu payload có vòng đời dài, thêm schema version và mapper chuyển đổi.
- Kiểm thử SecurityContext, principal và authorities qua nâng cấp.
- Nếu session cũ không thể đọc an toàn, yêu cầu xác thực lại theo chính sách; không bỏ qua lỗi deserialize rồi tiếp tục cấp quyền.

Đổi schema SQL và đổi định dạng thuộc tính là hai thay đổi khác nhau. Migration bảng có thể thành công nhưng dữ liệu byte cũ vẫn không deserialize được. Cần kiểm thử cả database schema lẫn payload session.

## 8. Hết hạn session và cleanup trong JDBC

JDBC không có TTL tự động cho từng dòng giống Redis. Spring Session lưu thời điểm hết hạn trong cột EXPIRY_TIME và dùng MAX_INACTIVE_INTERVAL cùng LAST_ACCESS_TIME để quản lý thời gian không hoạt động.

Về khái niệm:

~~~text
EXPIRY_TIME = LAST_ACCESS_TIME + MAX_INACTIVE_INTERVAL
~~~

Khi session được truy cập và lưu lại, repository cập nhật thời điểm hoạt động và thời điểm hết hạn. Nếu người dùng không hoạt động quá thời gian cấu hình, session không còn hợp lệ dù dòng dữ liệu có thể chưa được xóa vật lý.

JdbcIndexedSessionRepository có tác vụ cleanup để xóa các session hết hạn cùng các thuộc tính liên quan. Lịch cleanup mặc định thường chạy mỗi phút và có thể cấu hình bằng cleanupCron của EnableJdbcHttpSession hoặc property Spring Boot tương ứng.

Ví dụ:

~~~java
@Configuration
@EnableJdbcHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    cleanupCron = "0 * * * * *"
)
public class SessionConfiguration {
}
~~~

Job cleanup giúp giới hạn dữ liệu tồn đọng. Nó không phải cơ chế xác định duy nhất session còn hợp lệ hay không. Repository phải từ chối session đã hết hạn khi tra cứu, ngay cả khi cleanup chưa chạy tới dòng đó.

### Cookie và timeout phía máy chủ

Cookie ở trình duyệt và session trong database có vòng đời riêng. Cookie còn hạn không chứng minh session trong database còn hợp lệ. Cookie có thể bị xóa trong khi dòng session còn tồn tại đến khi timeout hoặc cleanup xử lý.

Cần phối hợp:

- Timeout không hoạt động phía server.
- Thời hạn cookie ở trình duyệt.
- Chính sách absolute timeout nếu nghiệp vụ yêu cầu.
- Luồng logout và invalidate session.
- Job cleanup và thời gian lưu dữ liệu tồn dư.

Không dùng việc browser đóng tab làm bảo đảm session đã bị xóa khỏi database.

## 9. Principal index và quản lý session theo người dùng

JdbcIndexedSessionRepository hỗ trợ FindByIndexNameSessionRepository. Repository lưu principal name trong cột PRINCIPAL_NAME và có index để tìm các session của một người dùng.

Trong ứng dụng Spring Security, Spring Session có thể xác định principal từ SecurityContext được lưu trong session. Với cơ chế xác thực tùy chỉnh, ứng dụng có thể đặt thuộc tính principal index theo API Spring Session:

~~~java
session.setAttribute(
    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
    principalName
);
~~~

Giá trị principal phải đến từ kết quả xác thực đáng tin cậy, không lấy trực tiếp từ request client. Principal name cần ổn định và nhất quán giữa lúc ghi và lúc truy vấn.

Ví dụ tìm các session:

~~~java
Map<String, ? extends Session> sessions =
        repository.findByPrincipalName(authentication.getName());
~~~

Có thể dùng chức năng này để liệt kê phiên đăng nhập hoặc thu hồi session cụ thể. Trước khi xóa, hãy kiểm tra session ID thuộc principal hiện tại hoặc principal mà người gọi có quyền quản trị. Không trả Session object trực tiếp ra API và không ghi session ID vào log.

JDBC repository có principal index nhưng không phát session lifecycle events tích hợp như RedisIndexedSessionRepository. Nếu nghiệp vụ cần thông báo chắc chắn khi session bị xóa hoặc hết hạn, hãy thiết kế audit/outbox hoặc cơ chế sự kiện riêng. Không giả định job cleanup JDBC sẽ phát SessionExpiredEvent cho listener.

## 10. Transaction và ranh giới lưu session

JdbcIndexedSessionRepository sử dụng transaction để thực hiện các thao tác lưu session và thuộc tính. Cấu hình mặc định của repository dùng transaction operations với propagation REQUIRES_NEW để thao tác session có transaction riêng trong các trường hợp phù hợp.

Điều này có một hệ quả quan trọng: không nên giả định thay đổi session và thay đổi nghiệp vụ trong cùng request luôn commit hoặc rollback cùng nhau.

Ví dụ:

~~~java
@Transactional
public void submitOrder(HttpSession session, OrderCommand command) {
    orderService.createOrder(command);
    session.setAttribute("app.lastOrderId", command.orderId());
}
~~~

Nếu repository session dùng transaction riêng, thao tác lưu session có thể commit độc lập với transaction tạo đơn hàng. Vì vậy, không dùng session làm nơi ghi nhận trạng thái giao dịch cần tính nguyên tử với database nghiệp vụ.

Đối với dữ liệu đơn hàng, thanh toán, tồn kho hoặc chuyển tiền, hãy lưu trong transaction nghiệp vụ và dùng khóa/optimistic locking phù hợp. Session chỉ nên giữ tham chiếu hoặc trạng thái giao diện.

### FlushMode và SaveMode

Hai chính sách có ý nghĩa riêng:

- FlushMode quyết định khi nào thay đổi session được ghi xuống repository.
- SaveMode quyết định thuộc tính nào được đưa vào thao tác lưu.

Các lựa chọn thường dùng gồm FlushMode.ON_SAVE hoặc IMMEDIATE, và SaveMode.ON_SET_ATTRIBUTE, ON_GET_ATTRIBUTE hoặc ALWAYS. Với ứng dụng web thông thường, ON_SAVE cùng ON_SET_ATTRIBUTE thường là điểm bắt đầu hợp lý. Nếu code sửa object mutable tại chỗ mà không gọi setAttribute lại, hãy sửa cách cập nhật hoặc cân nhắc ON_GET_ATTRIBUTE sau khi đo tác động.

Không nên coi SaveMode là cách tắt ghi metadata. Request truy cập session vẫn có thể cập nhật lastAccessedTime và thời hạn session. Một endpoint chỉ đọc nghiệp vụ vẫn có thể phát sinh ghi ở bảng session.

## 11. Tải database và chiến lược vận hành

JDBC session tạo tải lên database theo số lượng session và tần suất truy cập. Các hoạt động có thể gồm:

- SELECT session theo SESSION_ID.
- SELECT/ghi thuộc tính trong SPRING_SESSION_ATTRIBUTES.
- INSERT session mới.
- UPDATE thời điểm truy cập và hết hạn.
- INSERT, UPDATE hoặc DELETE thuộc tính.
- DELETE các session hết hạn và thuộc tính liên quan.

Tải phụ thuộc FlushMode, SaveMode, kích thước session, số request có truy cập session và số thuộc tính được đọc/ghi.

### Tách pool hoặc database session

Nếu session traffic cạnh tranh với transaction nghiệp vụ, có thể cân nhắc:

- Dùng database riêng cho session.
- Dùng schema riêng hoặc table prefix riêng.
- Dùng DataSource/pool riêng để giới hạn connection session.
- Đặt giới hạn kích thước thuộc tính session.
- Giảm việc truy cập HttpSession không cần thiết.
- Đo và tối ưu query/index trước khi tăng pool.

Tách pool giúp cô lập số connection nhưng không tạo thêm năng lực CPU/IO nếu vẫn dùng cùng database server. Database riêng hoặc instance riêng mới tạo ranh giới tài nguyên rõ hơn.

### Connection pool

Mỗi instance ứng dụng có thể có connection pool riêng. Khi scale số instance, tổng số connection tiềm năng là tổng pool của tất cả node. Ví dụ 10 instance với maximum-pool-size 20 có thể tạo tới 200 connection nếu tất cả pool đều mở tối đa.

Hãy tính tổng pool theo tải và giới hạn database. Không tăng pool chỉ để che giấu query chậm; điều đó có thể làm database quá tải hơn.

## 12. Schema migration và nhiều instance

Schema session là một phần của hợp đồng giữa các phiên bản ứng dụng. Mọi instance phải sử dụng cùng tên bảng, cột, index và kiểu dữ liệu tương thích.

Trong production:

- Dùng script schema phù hợp với database vendor.
- Quản lý thay đổi schema bằng Flyway/Liquibase hoặc quy trình migration được kiểm soát.
- Không để mỗi instance tự chạy DDL khi khởi động.
- Dùng tài khoản migration có quyền DDL riêng.
- Tài khoản runtime chỉ cần quyền SELECT/INSERT/UPDATE/DELETE cần thiết trên các bảng session.
- Kiểm thử migration trên bản sao schema và dữ liệu giả trước khi triển khai.
- Khi đổi tableName, phải cập nhật migration và cấu hình đồng bộ trên tất cả node.

Rolling deployment cần tương thích schema. Nếu phiên bản mới yêu cầu cột mới nhưng node cũ chưa biết cột đó, hãy dùng chiến lược expand-contract: thêm schema theo hướng tương thích trước, triển khai code đọc/ghi tương thích, rồi mới loại bỏ cấu trúc cũ trong lần phát hành sau.

Cùng với schema, serializer và class thuộc tính session cũng cần tương thích. Schema SQL tương thích không đảm bảo byte trong ATTRIBUTE_BYTES có thể deserialize bởi phiên bản mới hoặc cũ.

## 13. Bảo mật dữ liệu session trong database

Session thường chứa dữ liệu xác thực và ngữ cảnh người dùng. Khi lưu bằng JDBC, cần bảo vệ cả kết nối, quyền database và dữ liệu lưu trữ.

- Dùng TLS khi kết nối database qua mạng.
- Giới hạn quyền tài khoản runtime vào đúng schema và bảng session.
- Tách tài khoản migration có quyền DDL khỏi tài khoản runtime.
- Mã hóa dữ liệu lưu trữ theo chính sách database/storage.
- Bảo vệ backup và bản sao database vì chúng có thể chứa SecurityContext và dữ liệu người dùng.
- Không ghi session ID, cookie, token hoặc nội dung thuộc tính session vào log.
- Không đưa session ID vào URL hoặc metric label.
- Giới hạn thời gian lưu dữ liệu và xác nhận cleanup hoạt động.
- Dùng secret manager cho mật khẩu database.

Java serialization không phải mã hóa. Dữ liệu byte trong ATTRIBUTE_BYTES không nên được coi là bí mật chỉ vì không đọc được bằng SQL text. Người có quyền truy cập database và class phù hợp có thể giải mã nội dung. Nếu cần bảo vệ ở mức payload, phải thiết kế encryption và quản lý khóa riêng, đồng thời kiểm thử rotation và khả năng đọc dữ liệu cũ.

## 14. Kiểm thử Spring Session JDBC

Kiểm thử với MockHttpSession có thể xác minh controller nhưng không chứng minh repository JDBC, schema, transaction hoặc cleanup hoạt động. Cần integration test với database tương thích production, có thể dùng Testcontainers.

Các trường hợp nên kiểm tra:

| Ca kiểm thử | Kết quả cần xác nhận |
|---|---|
| Tạo session | Có dòng trong SPRING_SESSION và các thuộc tính tương ứng |
| Request tiếp theo | Cùng cookie tải lại đúng session |
| Cập nhật thuộc tính | Dữ liệu trong SPRING_SESSION_ATTRIBUTES được cập nhật |
| Xóa thuộc tính | Dòng thuộc tính được loại bỏ |
| Invalidate session | Session bị xóa và thuộc tính liên quan được cascade/delete |
| Hết hạn | findById không trả session hợp lệ sau timeout |
| Cleanup | Job xóa dòng hết hạn và dữ liệu thuộc tính |
| Principal lookup | findByPrincipalName trả đúng session của người dùng |
| Nhiều instance | Node A tạo, node B đọc được cùng session |
| Transaction | Xác nhận ranh giới commit/rollback theo cấu hình repository |
| Deserialize cũ | Session được ghi bởi artifact trước đọc được hoặc bị từ chối có kiểm soát |
| Database outage | Lỗi kết nối được phân biệt với session không tồn tại |

Ví dụ test repository ở mức khái niệm:

~~~java
@Test
void sessionCanBeReadByAnotherRequest() {
    Session session = repository.createSession();
    session.setAttribute("app.locale", "vi-VN");
    repository.save(session);

    Session loaded = repository.findById(session.getId());

    assertThat(loaded).isNotNull();
    assertThat(loaded.getAttribute("app.locale")).isEqualTo("vi-VN");
}
~~~

Với test hết hạn, đặt maxInactiveInterval ngắn và polling có giới hạn để xác nhận repository không còn trả session hợp lệ. Không chỉ kiểm tra dòng vật lý đã bị xóa; job cleanup có thể chạy sau thời điểm hết hạn logic.

Với test nhiều instance, hai application context hoặc hai ứng dụng test phải dùng cùng database, schema, tableName và serializer. Test một repository object duy nhất không chứng minh được cấu hình giữa các node giống nhau.

## 15. Chẩn đoán sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Ứng dụng không khởi động được repository | Thiếu DataSource hoặc transaction infrastructure | Kiểm tra bean, URL, credential và driver |
| Lỗi thiếu bảng hoặc cột | Schema chưa được cài đặt hoặc migration sai vendor | Kiểm tra script/schema version và quyền runtime |
| Request tạo session nhưng request sau không thấy | Cookie, tableName, database hoặc cấu hình node không đồng nhất | So sánh response cookie và cấu hình mọi instance |
| Người dùng bị đăng xuất sau deploy | Serializer/class không tương thích hoặc schema/namespace thay đổi | Kiểm thử fixture session cũ và migration |
| Database tăng tải ghi | Nhiều request truy cập session, SaveMode/FlushMode hoặc session lớn | Đo query, connection pool và kích thước thuộc tính |
| Session hết hạn nhưng dòng vẫn còn | Cleanup chưa chạy hoặc job bị lỗi | Kiểm tra EXPIRY_TIME và lịch cleanup |
| Tra cứu principal trả rỗng | PRINCIPAL_NAME không được xác định hoặc principal name không đồng nhất | Kiểm tra SecurityContext và index |
| Database deadlock hoặc lock contention | Request đồng thời cập nhật session hoặc cleanup cạnh tranh | Xem execution plan, transaction và lock wait |
| Deserialize exception | Payload cũ hoặc serializer không tương thích | Kiểm tra classpath, conversion và fixture |
| Chỉ một số node lỗi | Cấu hình DataSource, tableName, serializer hoặc dependency khác nhau | So sánh cấu hình runtime và version |

Khi session không tìm thấy, repository có thể trả null. Khi database không kết nối được, đó là lỗi hạ tầng. Không chuyển lỗi database thành trạng thái anonymous vì điều đó che giấu sự cố và có thể làm sai quyết định xác thực. Tương tự, lỗi deserialize không đồng nghĩa session đã hết hạn.

## 16. Quy trình đưa JDBC session vào production

Một trình tự triển khai thực tế:

1. Xác định tải session dự kiến: session đồng thời, request/giây, số thuộc tính và kích thước trung bình.
2. Chọn database và xác nhận latency, availability, backup, replication và giới hạn connection.
3. Thêm dependency Spring Session JDBC tương thích với phiên bản Spring Boot/Framework.
4. Cấu hình DataSource, credential, TLS và pool.
5. Cài schema đúng database vendor bằng migration có kiểm soát.
6. Bật EnableJdbcHttpSession hoặc cấu hình auto-configuration của Boot, chỉ dùng một cơ chế.
7. Chọn timeout, tableName, FlushMode và SaveMode.
8. Kiểm thử cookie, login, logout, principal lookup và nhiều instance.
9. Kiểm thử hết hạn logic, cleanup và tải đồng thời.
10. Xác minh serializer có thể đọc session tồn tại từ phiên bản trước.
11. Thiết lập metric cho query latency, pool saturation, lỗi SQL, session lookup miss và cleanup.
12. Chuẩn bị backup/restore và quy trình xử lý database outage.

Nên thử tải với phân bố request thực tế. Một endpoint chỉ đọc có thể vẫn cập nhật lastAccessTime, do đó tải JDBC session có thể gần với số request truy cập session chứ không chỉ số request thay đổi thuộc tính.

## 17. Khi nào nên dùng database session riêng?

Dùng chung database nghiệp vụ giúp giảm hạ tầng, nhưng cũng làm session traffic và giao dịch nghiệp vụ chia sẻ tài nguyên. Nếu session được cập nhật rất thường xuyên, có thể ảnh hưởng truy vấn đơn hàng, thanh toán hoặc các giao dịch quan trọng.

Cân nhắc database/schema riêng khi:

- Session traffic tăng nhanh và có thể cạnh tranh connection.
- Có yêu cầu backup/retention khác với dữ liệu nghiệp vụ.
- Muốn giới hạn quyền truy cập session cho một tài khoản riêng.
- Có thể scale session database độc lập.
- Sự cố session không nên làm database nghiệp vụ cạn connection.
- Muốn dọn hoặc xóa session mà không ảnh hưởng bảng nghiệp vụ.

Nếu dùng schema riêng trên cùng server, cần nhớ tài nguyên CPU, I/O, WAL/transaction log và connection vẫn có thể dùng chung. Mức cô lập cần thiết sẽ quyết định chỉ tách schema, tách database hay tách hẳn database instance.

## 18. Checklist lựa chọn và vận hành

Trước khi chọn Spring Session JDBC, hãy xác nhận:

- Database quan hệ có đủ thông lượng và độ sẵn sàng cho session workload.
- Tất cả instance dùng cùng database, schema, tableName và serializer.
- Schema được tạo bằng script phù hợp vendor và quản lý bằng migration.
- Runtime account có quyền tối thiểu; migration account được tách riêng.
- Session chỉ lưu dữ liệu nhỏ, cần thiết và có thể tuần tự hóa.
- Timeout và cleanup được cấu hình, giám sát.
- Đã hiểu JDBC repository không cung cấp session lifecycle event tích hợp như Redis indexed.
- Đã hiểu transaction session có thể độc lập với transaction nghiệp vụ.
- Đã kiểm thử principal lookup, logout, expiry, concurrency và database outage.
- Đã kiểm tra rolling deployment và khả năng đọc session cũ.
- Đã bảo vệ backup, log, cookie và session ID.
- Đã đo tác động lên connection pool và truy vấn nghiệp vụ.

Spring Session JDBC phù hợp khi cơ sở dữ liệu quan hệ đáp ứng được tải session và tổ chức muốn tận dụng nền tảng SQL đã có. JdbcIndexedSessionRepository cung cấp lưu trữ session dùng chung, tra cứu theo principal và cleanup dựa trên thời điểm hết hạn. Đổi lại, ứng dụng cần quản lý schema, transaction, serialization, tải ghi và cleanup một cách chủ động. Hãy giữ session nhỏ, dùng migration có kiểm soát và kiểm thử nhiều instance để việc lưu session bằng JDBC hoạt động ổn định qua các lần triển khai.

## Tài liệu tham khảo

- [Spring Session — JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [JdbcIndexedSessionRepository Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/jdbc/JdbcIndexedSessionRepository.html)
- [EnableJdbcHttpSession Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/jdbc/config/annotation/web/http/EnableJdbcHttpSession.html)
- [Spring Boot — Spring Session properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)

