# Bật SQL log, bind log và bảo vệ dữ liệu nhạy cảm

Khi vận hành ứng dụng **Spring Data Relational JDBC**, log SQL giúp tìm nguyên nhân query chậm, sai tên cột, mapping lỗi hoặc số lượng câu lệnh phát sinh ngoài dự kiến. Cần phân biệt hai loại thông tin:

- **SQL log:** ghi câu lệnh SQL được thực thi, thường vẫn giữ placeholder như dấu hỏi hoặc named parameter.
- **Bind log:** ghi giá trị thực tế được bind vào từng placeholder, có thể bao gồm email, số điện thoại, token, địa chỉ, dữ liệu thanh toán hoặc thông tin cá nhân khác.

Trong Spring JDBC, có thể bật log SQL ở mức DEBUG và log giá trị bind ở mức TRACE của `StatementCreatorUtils`. Nếu ứng dụng dùng MyBatis, có thể bật logger theo namespace mapper hoặc statement. Những cấu hình này hữu ích khi debug, nhưng bind log có rủi ro lộ dữ liệu cao. **Chỉ bật ở phạm vi và thời gian cần thiết, đồng thời giữ log giá trị nhạy cảm tắt trong production.**

Bài học trình bày cách bật SQL log và bind log cho Spring Data JDBC, cấu hình MyBatis, chọn logger có phạm vi nhỏ, dùng profile riêng, đọc log đúng cách và bảo vệ dữ liệu nhạy cảm trong log.

## 1. SQL log và bind log khác nhau thế nào?

Giả sử repository chạy query:

~~~sql
SELECT id, email, status
FROM customer
WHERE email = ?
  AND status = ?;
~~~

SQL log có thể cho thấy:

~~~text
Executing prepared SQL statement
[SELECT id, email, status FROM customer WHERE email = ? AND status = ?]
~~~

Nó giúp xác định câu lệnh nào đã chạy, bảng/cột nào được truy cập và cấu trúc điều kiện ra sao.

Bind log có thể cho thấy:

~~~text
Setting SQL statement parameter value:
column index 1, parameter value [alice@example.com],
value class [java.lang.String], SQL type 12

Setting SQL statement parameter value:
column index 2, parameter value [ACTIVE],
value class [java.lang.String], SQL type 12
~~~

Bind log giúp xác nhận ứng dụng truyền đúng giá trị và kiểu dữ liệu. Nhưng nó cũng tiết lộ dữ liệu đầu vào thực tế.

| Loại log | Thông tin thường thấy | Rủi ro |
| --- | --- | --- |
| SQL log | SQL text, tên bảng/cột, placeholder | Lộ cấu trúc schema và logic truy vấn |
| Bind log | Giá trị thực tế, Java type, JDBC type, vị trí parameter | Có thể lộ PII, secret, token và dữ liệu nghiệp vụ |
| Result log | Số hàng hoặc dữ liệu kết quả tùy framework/logger | Có thể lộ nội dung database |
| Timing log | Thời gian thực thi, số hàng, lỗi | Thường ít nhạy cảm hơn nhưng vẫn cần kiểm soát |

SQL log và bind log nên được bật độc lập. Trong nhiều tình huống, SQL text cùng thời gian thực thi đã đủ để điều tra mà không cần ghi giá trị bind.

## 2. Bật SQL log cho Spring Data JDBC

Spring Data JDBC sử dụng Spring JDBC ở tầng thực thi. `JdbcTemplate` ghi các câu SQL ở mức DEBUG theo logger category của lớp template.

Trong `application-local.yml`:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
~~~

Hoặc trong `application.properties`:

~~~properties
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
~~~

Sau khi bật, log thường cho thấy query hoặc update đang được thực thi và SQL text với placeholder. `NamedParameterJdbcTemplate` dùng hạ tầng Spring JDBC bên dưới; tùy phiên bản và đường thực thi, SQL được ghi qua logger của `JdbcTemplate` hoặc các lớp liên quan trong package `org.springframework.jdbc.core`.

### 2.1. Bật logger package rộng hơn

Nếu cần thêm thông tin về JDBC core:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

Cấu hình package rộng có thể tạo nhiều log hơn. Hãy bắt đầu với logger cụ thể và mở rộng khi cần.

Không bật root logger ở DEBUG chỉ để xem SQL. Việc đó có thể tạo lượng log rất lớn từ web, security, framework và thư viện khác.

## 3. Bật bind log cho Spring JDBC

Spring Framework có logger:

~~~text
org.springframework.jdbc.core.StatementCreatorUtils
~~~

Lớp này chuẩn bị giá trị cho `PreparedStatement`. Khi TRACE được bật, nó có thể ghi:

- Vị trí parameter trong statement.
- Giá trị parameter.
- Java class của giá trị.
- SQL type được dùng để bind.

Cấu hình:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
~~~

Hoặc:

~~~properties
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE
~~~

Ví dụ log:

~~~text
DEBUG JdbcTemplate - Executing prepared SQL statement
  [SELECT id FROM customer WHERE email = ?]

TRACE StatementCreatorUtils - Setting SQL statement parameter value:
  column index 1, parameter value [alice@example.com],
  value class [java.lang.String], SQL type 12
~~~

Đây là lý do bind log cần được coi là dữ liệu nhạy cảm: giá trị được ghi trực tiếp vào log message. Nếu parameter chứa password, access token, refresh token, số tài khoản, email hoặc thông tin cá nhân, log có thể trở thành một bản sao của dữ liệu đó.

### 3.1. Bind log không phải lúc nào cũng là SQL đã thay placeholder

Spring JDBC thường ghi SQL và bind values ở hai log message riêng. Bạn cần ghép chúng theo thứ tự thực thi và vị trí parameter.

Ví dụ:

~~~sql
UPDATE customer
SET status = ?, updated_at = ?
WHERE id = ?;
~~~

Bind log:

~~~text
index 1 -> ACTIVE
index 2 -> 2026-11-13T10:15:00
index 3 -> 42
~~~

Khi điều tra, phải ghép đúng thứ tự parameter. Không suy luận giá trị theo thứ tự field trong Java object nếu query có expression hoặc parameter được bind có điều kiện.

### 3.2. Null và kiểu JDBC

Với giá trị null, bind log có thể ghi parameter value là null và SQL type tương ứng. Nếu database báo lỗi kiểu dữ liệu, hãy xem cả SQL type và Java type. Chỉ nhìn chuỗi null không đủ để biết driver đã bind NULL theo kiểu SQL nào.

## 4. Bật SQL và parameter log cho MyBatis

Nếu ứng dụng Spring Data JDBC dùng MyBatis integration hoặc MyBatis mapper riêng, log được phân loại theo namespace mapper hoặc statement ID.

Ví dụ namespace:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <select id="findById" resultMap="purchaseOrderMap">
        SELECT id, order_number, status
        FROM purchase_order
        WHERE id = #{id}
    </select>
</mapper>
~~~

Có thể bật logger cho mapper:

~~~yaml
logging:
  level:
    com.example.orders.PurchaseOrderMapper: DEBUG
~~~

Hoặc bật cho một statement cụ thể:

~~~yaml
logging:
  level:
    com.example.orders.PurchaseOrderMapper.findById: TRACE
~~~

MyBatis hỗ trợ logging theo package, mapper namespace hoặc tên statement đầy đủ. Thông thường DEBUG hiển thị câu SQL được chuẩn bị và parameter list; TRACE có thể hiển thị thêm chi tiết kết quả.

Ví dụ log MyBatis:

~~~text
==> Preparing: SELECT id, order_number, status
              FROM purchase_order WHERE id = ?
==> Parameters: 42(Long)
<== Total: 1
~~~

Parameter list có thể chứa giá trị thực tế. Vì vậy, bật logger mapper ở DEBUG cũng cần được xem xét như một hành động có thể làm lộ dữ liệu, tùy phiên bản MyBatis và cấu hình logging.

### 4.1. Chọn logging implementation

MyBatis có internal log factory và có thể tự chọn implementation dựa trên thư viện có trong classpath. Trong ứng dụng Spring Boot dùng SLF4J/Logback, có thể cấu hình rõ MyBatis sử dụng SLF4J nếu auto-detection chọn implementation khác.

Trong `mybatis-config.xml`:

~~~xml
<configuration>
    <settings>
        <setting name="logImpl" value="SLF4J"/>
    </settings>
</configuration>
~~~

Nếu dùng `SqlSessionFactoryBean`, nạp file cấu hình MyBatis tương ứng. Với MyBatis Spring Boot starter, có thể cấu hình property `mybatis.configuration.log-impl` theo phiên bản starter đang dùng.

Không cần ép `logImpl` nếu auto-detection đã chọn đúng logging framework và log hoạt động như mong muốn.

### 4.2. Chọn logger namespace

Thay vì bật toàn bộ `org.apache.ibatis`, có thể bật riêng mapper:

~~~yaml
logging:
  level:
    com.example.orders.PurchaseOrderMapper: DEBUG
    com.example.catalog.ProductMapper: INFO
~~~

Điều này giới hạn log vào module đang điều tra. Khi xử lý xong, trả logger về mức phù hợp để tránh tiếp tục ghi parameter values.

## 5. Cấu hình log theo profile

Không nên bật bind log trong cấu hình mặc định dùng chung cho mọi môi trường. Hãy đặt nó trong profile local hoặc debug có thời hạn.

Ví dụ `application.yml`:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.jdbc.core.JdbcTemplate: INFO
    org.springframework.jdbc.core.StatementCreatorUtils: OFF
~~~

Ví dụ `application-local.yml`:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
~~~

Chạy local bằng environment variable:

~~~text
SPRING_PROFILES_ACTIVE=local
~~~

Khi profile local không được kích hoạt, bind logger vẫn tắt. Tùy cấu hình môi trường, profile có thể được chọn bằng environment variable, command line hoặc deployment configuration.

### 5.1. Dùng profile debug tạm thời

Nếu cần điều tra ở môi trường staging:

1. Tạo cấu hình debug riêng.
2. Chỉ bật logger cho mapper/repository liên quan.
3. Giới hạn thời gian bật.
4. Dùng dữ liệu thử đã được làm sạch.
5. Xác nhận log được lưu ở nơi có quyền truy cập hạn chế.
6. Tắt cấu hình sau khi thu thập đủ bằng chứng.

Không để một profile debug trở thành cấu hình production mặc định.

### 5.2. Không commit dữ liệu nhạy cảm cùng cấu hình

File cấu hình chỉ nên chứa logger category và level. Không ghi password, API key, token, connection string có credential hoặc dữ liệu thật vào source control, log message hay script debug.

## 6. Bảo vệ dữ liệu nhạy cảm trong log

Bind logging có thể ghi nguyên giá trị parameter. Những trường cần xem là nhạy cảm gồm:

- Password, PIN, secret và API key.
- Access token, refresh token, session ID và cookie.
- Số thẻ, thông tin tài khoản hoặc dữ liệu thanh toán.
- Email, số điện thoại, địa chỉ và định danh cá nhân.
- Nội dung tin nhắn, ghi chú riêng tư hoặc dữ liệu sức khỏe.
- Payload chứa thông tin khách hàng hoặc dữ liệu nội bộ.

Ngay cả khi một giá trị không phải secret, nó vẫn có thể là dữ liệu cá nhân hoặc dữ liệu nghiệp vụ cần giới hạn truy cập.

### 6.1. Không bật TRACE bind log trong production

Nguyên tắc an toàn:

- Giữ `StatementCreatorUtils` ở OFF hoặc mức không ghi giá trị parameter trong production.
- Chỉ bật DEBUG SQL khi có nhu cầu vận hành rõ ràng và đã đánh giá nội dung SQL.
- Không bật TRACE cho toàn bộ mapper package nếu không cần.
- Không dùng root DEBUG/TRACE để điều tra một query đơn lẻ.
- Tắt logger debug sau khi hoàn tất điều tra.

Nếu cần kiểm tra production issue, ưu tiên log metadata đã làm sạch: operation name, query identifier, elapsed time, row count, SQLState, vendor error code và trace ID.

### 6.2. Masking và allowlist

Nếu tổ chức cần ghi một phần parameter để điều tra, hãy dùng cơ chế logging có khả năng masking hoặc allowlist:

- Chỉ ghi các trường được phê duyệt.
- Che giá trị như email, phone và account number.
- Không ghi password/token dù đã che một phần.
- Với identifier cần đối chiếu, cân nhắc hash có salt hoặc pseudonymous ID phù hợp chính sách.
- Không ghi toàn bộ DTO hoặc request JSON bằng `toString()`.

Masking cần xảy ra trước khi log được ghi ra appender. Che dữ liệu sau khi log đã được gửi tới hệ thống tập trung không loại bỏ bản sao ban đầu.

### 6.3. Không tự log PreparedStatement với giá trị

Không tự viết:

~~~java
log.debug("Executing query with customer data: {}", customer);
~~~

hoặc:

~~~java
log.debug("SQL={}, parameters={}", sql, parameters);
~~~

nếu `customer` hoặc `parameters` có thể chứa dữ liệu nhạy cảm. Hãy log query identifier và metadata đã chọn lọc.

### 6.4. Cẩn trọng với P6Spy và datasource-proxy

Các công cụ như P6Spy hoặc datasource-proxy có thể ghi SQL và parameter ở tầng DataSource, hữu ích khi muốn quan sát nhiều đường thực thi JDBC. Tuy nhiên, chúng cũng có thể ghi giá trị nhạy cảm hoặc tạo lượng log rất lớn.

Trước khi bật:

- Kiểm tra formatter và khả năng masking.
- Xác định logger/appender nhận output.
- Giới hạn package, query hoặc môi trường.
- Đánh giá overhead và tác động hiệu năng.
- Không mặc định rằng công cụ đã che dữ liệu an toàn.

Không dùng tính năng thay placeholder bằng giá trị để tạo SQL copy-paste trong production nếu chưa có chính sách masking và kiểm soát truy cập.

## 7. Log lỗi SQL mà không lộ parameter

Khi query thất bại, log nên giúp người vận hành xác định lỗi mà không cần ghi toàn bộ dữ liệu đầu vào.

Thông tin thường hữu ích:

- Tên operation hoặc statement ID.
- Tên repository/mapper.
- Trace ID hoặc correlation ID.
- Thời gian thực thi.
- Số hàng dự kiến hoặc số hàng bị ảnh hưởng nếu có.
- Loại exception Spring.
- SQLState và vendor error code.
- Tên constraint/index nếu exception cung cấp và việc ghi tên đó không làm lộ dữ liệu.

Ví dụ:

~~~java
try {
    repository.save(order);
} catch (DataAccessException ex) {
    log.error(
            "Failed to persist order; operation=createOrder, traceId={}",
            traceId,
            ex
    );
    throw ex;
}
~~~

Không thêm `order.toString()` hoặc request body vào log exception nếu object có thể chứa dữ liệu khách hàng. Exception stack trace thường đủ để xác định lớp lỗi; parameter values nên được kiểm tra trong môi trường an toàn với dữ liệu đã làm sạch.

## 8. Đọc log để điều tra vấn đề

### 8.1. Query không chạy như mong đợi

Kiểm tra:

1. SQL text có đúng statement không?
2. Table/column alias có đúng không?
3. Có điều kiện WHERE nào bị thiếu không?
4. Số placeholder có khớp số parameter không?
5. JDBC type có phù hợp kiểu cột không?
6. Có conversion hoặc null binding bất thường không?

Với Spring JDBC, ghép SQL log ở DEBUG với bind log trong một khoảng thời gian ngắn tại local/test để xác định parameter sai.

### 8.2. Query chậm

SQL log giúp xác định câu lệnh, nhưng không tự giải thích nguyên nhân chậm. Cần xem thêm:

- Thời gian thực thi.
- Số hàng trả về hoặc bị cập nhật.
- Index và execution plan.
- Lock wait, blocking session và connection pool.
- Kích thước result set.
- Số query phát sinh trong một use case.

Không cần bật bind log nếu vấn đề chỉ liên quan execution plan và index. Có thể dùng query ID và dữ liệu test đã làm sạch để phân tích.

### 8.3. Nhiều query ngoài dự kiến

Nếu một lần đọc aggregate tạo ra nhiều câu SQL, kiểm tra mapping relation, collection child và cách service truy cập repository. SQL log có thể cho thấy N+1 pattern hoặc việc tải aggregate lặp. Không dùng bind values thật nếu chỉ cần đếm số câu query.

## 9. Cấu hình log trong YAML và properties

Một cấu hình local tập trung:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
    com.example.orders.PurchaseOrderMapper: DEBUG
    com.example.catalog.ProductMapper: INFO
~~~

Tương đương properties:

~~~properties
logging.level.root=INFO
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE
logging.level.com.example.orders.PurchaseOrderMapper=DEBUG
logging.level.com.example.catalog.ProductMapper=INFO
~~~

Đây là ví dụ cho môi trường local/debug. Trước khi dùng, kiểm tra mapper namespace và logging implementation thực tế. Trong production, tắt TRACE bind values và chỉ bật SQL logger có phạm vi nhỏ khi cần.

### 9.1. Logging levels

| Level | Cách dùng thường gặp |
| --- | --- |
| ERROR | Lỗi cần xử lý |
| WARN | Tình trạng bất thường nhưng ứng dụng vẫn hoạt động |
| INFO | Sự kiện vận hành quan trọng |
| DEBUG | SQL text, flow kỹ thuật hoặc chi tiết phục vụ debug |
| TRACE | Parameter values và chi tiết thực thi rất sâu |

Ý nghĩa chính xác của từng logger phụ thuộc thư viện. Không giả định TRACE chỉ ghi metadata; `StatementCreatorUtils` có thể ghi giá trị bind thực tế.

## 10. Bảo vệ log ở tầng vận hành

Ngay cả khi ứng dụng đã mask parameter, log vẫn cần được bảo vệ như một kho dữ liệu:

- Giới hạn quyền đọc log theo vai trò.
- Dùng TLS khi truyền log tới hệ thống tập trung.
- Mã hóa log khi lưu trữ nếu chính sách yêu cầu.
- Thiết lập retention và xóa log đúng thời hạn.
- Không đưa log nhạy cảm vào ticket, chat hoặc báo cáo không kiểm soát.
- Kiểm tra quyền truy cập của nhà cung cấp observability.
- Theo dõi thay đổi cấu hình logger trong production.
- Đảm bảo log không chứa dữ liệu do người dùng nhập có thể gây log injection hoặc làm giả dòng log.

Log có thể được sao chép sang nhiều nơi: file local, stdout container, collector, SIEM, APM và bản backup. Việc xóa một bản sao không bảo đảm các bản sao khác cũng được xóa.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Bật DEBUG root logger để xem SQL | Log quá nhiều, khó tìm query | Bật logger JDBC hoặc mapper cụ thể |
| Chỉ bật JdbcTemplate DEBUG nhưng chờ thấy giá trị bind | SQL log thường giữ placeholder | Chỉ bật StatementCreatorUtils TRACE khi thật sự cần |
| Bật TRACE bind log lâu dài | Lộ PII, token hoặc dữ liệu thanh toán | Tắt trong production, bật tạm thời ở môi trường an toàn |
| Nghĩ SQL log và bind log giống nhau | Bỏ sót thông tin parameter hoặc đánh giá sai rủi ro | Tách hai loại log |
| Bật MyBatis logging nhưng không có output | Log implementation hoặc namespace chưa đúng | Kiểm tra logImpl và logger mapper |
| Bật toàn bộ org.apache.ibatis TRACE | Ghi quá nhiều statement/result | Chọn namespace hoặc statement cụ thể |
| Log toàn bộ DTO/request | Có thể lộ dữ liệu nhạy cảm | Log metadata đã allowlist |
| Dùng P6Spy mà không cấu hình masking | Ghi SQL kèm giá trị thật | Kiểm tra formatter, filter và retention |
| Ghi SQL parameter vào exception message | Dữ liệu nhạy cảm xuất hiện trong error log | Log operation ID, SQLState và trace ID |
| Bật log trong application.yml dùng chung | Production vô tình nhận cấu hình debug | Đặt trong profile local/debug riêng |
| Dựa vào SQL log để kết luận nguyên nhân query chậm | Không thấy execution plan hoặc lock wait | Dùng database monitoring và execution plan |

## 12. Quy trình bật log để debug an toàn

Khi cần điều tra một lỗi JDBC:

1. **Xác định query/mapper:** tìm repository method, logger category hoặc namespace liên quan.
2. **Bật SQL DEBUG có phạm vi:** ưu tiên `JdbcTemplate` hoặc mapper cụ thể.
3. **Kiểm tra dữ liệu có nhạy cảm không:** xác định query có bind PII, secret hoặc payment data không.
4. **Chỉ bật bind TRACE khi cần:** dùng local/staging với dữ liệu giả hoặc đã làm sạch.
5. **Thu thập log tối thiểu:** query text, type, SQLState, thời gian và trace ID.
6. **Phân tích kết quả:** kiểm tra placeholder, JDBC type, null, index và execution plan.
7. **Tắt logger debug:** khôi phục mức log phù hợp sau khi điều tra.
8. **Xử lý log đã tạo:** lưu trong nơi có kiểm soát, tuân theo retention và xóa bản sao không cần thiết.
9. **Ghi lại nguyên nhân:** dùng query ID/operation name và mô tả đã làm sạch, không đính kèm parameter thật.

## Ghi nhớ

Trong Spring Data JDBC, SQL của `JdbcTemplate` thường được ghi ở DEBUG qua logger `org.springframework.jdbc.core.JdbcTemplate`. Giá trị bind của `PreparedStatement` có thể được ghi ở TRACE qua `org.springframework.jdbc.core.StatementCreatorUtils`. Với MyBatis, có thể bật logger theo mapper namespace hoặc statement; DEBUG thường cho thấy SQL và parameter list, còn TRACE có thể bổ sung thông tin kết quả.

SQL log và bind log là hai loại thông tin khác nhau. SQL text với placeholder giúp tìm câu lệnh; bind log cho thấy giá trị thực tế nhưng có thể chứa PII, token, password hoặc dữ liệu thanh toán. Hãy bật log theo profile local/debug, giới hạn logger, chỉ bật bind TRACE trong môi trường an toàn và tắt sau khi điều tra. Trong production, ưu tiên operation ID, trace ID, thời gian, số hàng, SQLState và thông tin lỗi đã làm sạch. Bảo vệ log bằng masking/allowlist, quyền truy cập, mã hóa và retention phù hợp; đừng coi log là nơi lưu trữ dữ liệu nghiệp vụ.

## Tài liệu tham khảo

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Framework — JDBC core classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — StatementCreatorUtils source](https://github.com/spring-projects/spring-framework/blob/main/spring-jdbc/src/main/java/org/springframework/jdbc/core/StatementCreatorUtils.java)
- [MyBatis — Logging](https://mybatis.org/mybatis-3/logging.html)
- [MyBatis — Configuration settings](https://mybatis.org/mybatis-3/configuration.html)
