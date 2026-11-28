# SQL tùy chỉnh và khác biệt cú pháp giữa các hệ quản trị

Spring Session JDBC dùng SQL để tạo, đọc, cập nhật và xóa session cùng các thuộc tính của session. Mô hình dữ liệu chung gồm bảng metadata và bảng attributes, nhưng mỗi hệ quản trị có thể khác nhau về kiểu dữ liệu nhị phân, cách đặt schema, cú pháp giới hạn số dòng, upsert, khóa và script khởi tạo. Khi triển khai trên PostgreSQL, MySQL, SQL Server, Oracle hoặc database tương thích JDBC khác, cần chọn đúng schema và hiểu SQL mà repository sử dụng.

SQL tùy chỉnh có thể cần khi tổ chức dùng tên bảng riêng, schema riêng, quy ước đặt tên, yêu cầu tối ưu truy vấn hoặc database chưa được Spring Session hỗ trợ trực tiếp. Tuy nhiên, thay đổi SQL phải giữ nguyên hợp đồng dữ liệu và thứ tự thao tác mà repository kỳ vọng. Chỉ thay một câu lệnh mà không xét các câu đọc, ghi, cleanup và transaction liên quan có thể làm phiên được tạo nhưng không đọc lại được, thuộc tính bị bỏ sót hoặc logout không xóa hết dữ liệu.

## 1. SQL trong Spring Session JDBC

Spring Session JDBC dùng repository để ánh xạ API session của Servlet sang các thao tác JDBC. Ở mức khái niệm, các thao tác chính gồm:

| Thao tác | Dữ liệu liên quan | Mục đích |
|---|---|---|
| Tạo session | Bảng session | Lưu ID, thời gian tạo, thời gian truy cập và thời hạn |
| Đọc session | Bảng session và bảng attributes | Tra cứu theo session ID, sau đó khôi phục thuộc tính |
| Cập nhật session | Bảng session | Cập nhật metadata và thời điểm truy cập |
| Thêm/cập nhật attribute | Bảng attributes | Lưu bytes theo cặp session và tên thuộc tính |
| Xóa attribute | Bảng attributes | Loại bỏ một thuộc tính khỏi session |
| Xóa session | Cả hai bảng | Thu hồi session và các thuộc tính liên quan |
| Cleanup | Bảng session và quan hệ cascade | Xóa dữ liệu đã hết hạn theo lịch |

Tên bảng mặc định thường là **SPRING_SESSION** và **SPRING_SESSION_ATTRIBUTES**. Trong schema tiêu chuẩn, bảng attributes tham chiếu khóa chính nội bộ của bảng session. Khi tùy chỉnh SQL hoặc schema, phải giữ đúng quan hệ này và mọi ràng buộc mà repository cần.

Ví dụ truy vấn khái niệm để đọc session:

~~~sql
SELECT PRIMARY_ID,
       SESSION_ID,
       CREATION_TIME,
       LAST_ACCESS_TIME,
       MAX_INACTIVE_INTERVAL,
       EXPIRY_TIME,
       PRINCIPAL_NAME
FROM SPRING_SESSION
WHERE SESSION_ID = ?;
~~~

Ký tự ? là placeholder positional của JDBC. Giá trị session ID phải được bind qua PreparedStatement hoặc API Spring JDBC, không nối trực tiếp vào chuỗi SQL.

Sau khi có PRIMARY_ID, repository đọc các thuộc tính:

~~~sql
SELECT ATTRIBUTE_NAME, ATTRIBUTE_BYTES
FROM SPRING_SESSION_ATTRIBUTES
WHERE SESSION_PRIMARY_ID = ?;
~~~

Đây là mô tả logic truy vấn. Câu lệnh thực tế, số lần đọc và cách batch phụ thuộc phiên bản Spring Session, repository và database.

## 2. Phân biệt cấu hình schema, table name và câu SQL

Ba loại tùy chỉnh thường bị nhầm lẫn:

| Loại tùy chỉnh | Ví dụ | Tác động |
|---|---|---|
| Schema/DDL | Chọn script PostgreSQL hoặc SQL Server, điều chỉnh kiểu binary theo database | Quy định cấu trúc bảng, cột, index và khóa ngoại |
| Tên bảng | Đổi tiền tố hoặc dùng bảng trong schema riêng | Thay đổi đối tượng database mà repository truy cập |
| Nội dung câu SQL | Thay cú pháp truy vấn, cleanup hoặc thao tác ghi | Thay đổi cách repository thực hiện thao tác JDBC |

Thay script schema không tự động có nghĩa mọi câu SQL runtime được thay đổi. Tương tự, đổi tên bảng không tự động tạo bảng mới. Cần đồng bộ DDL, tên bảng và cấu hình repository.

Spring Boot có các thuộc tính JDBC session thường dùng:

~~~yaml
spring:
  session:
    jdbc:
      initialize-schema: never
      schema: classpath:db/session-schema.sql
      table-name: SPRING_SESSION
      cleanup-cron: "0 * * * * *"
~~~

- **initialize-schema** điều khiển việc khởi tạo schema theo chính sách của ứng dụng; giá trị cụ thể được hỗ trợ phụ thuộc phiên bản Spring Boot.
- **schema** chỉ tới script schema cần dùng nếu ứng dụng thực hiện khởi tạo bằng script.
- **table-name** cấu hình tên bảng session theo cơ chế Spring Session JDBC hỗ trợ; repository dùng tên này để xây dựng tên bảng liên quan theo quy ước của phiên bản.
- **cleanup-cron** điều khiển lịch chạy cleanup theo cú pháp cron của Spring.

Trong production, thường quản lý DDL bằng Flyway, Liquibase hoặc quy trình migration của tổ chức rồi đặt chính sách khởi tạo schema phù hợp, thường là không tự khởi tạo lại khi ứng dụng chạy. Không để nhiều instance đồng thời cố tạo hoặc thay đổi schema trong lúc khởi động nếu không có quy trình migration an toàn.

Tên thuộc tính cấu hình và khả năng tùy chỉnh cần được kiểm tra theo phiên bản Spring Boot/Spring Session của dự án. Không giả định một thuộc tính cấu hình tồn tại giống nhau trong mọi phiên bản.

## 3. Dùng script schema đúng với hệ quản trị

Spring Session JDBC cung cấp schema script theo các nền tảng database được hỗ trợ. Script đã tính đến khác biệt kiểu dữ liệu và cú pháp DDL. Nên bắt đầu từ script của đúng database và đúng phiên bản thư viện, sau đó đưa thay đổi cần thiết vào migration được quản lý.

Các phần cần giữ tương thích:

- Khóa chính của bảng session.
- Unique constraint hoặc unique index trên session ID.
- Index hỗ trợ tìm session hết hạn và principal nếu repository cần.
- Khóa chính kép của bảng attributes.
- Khóa ngoại từ bảng attributes tới khóa chính nội bộ của bảng session.
- Kiểu dữ liệu đủ chứa bytes serialize của thuộc tính.
- Độ dài cột đủ chứa định danh, tên thuộc tính và principal theo yêu cầu ứng dụng.

Không nên tự viết lại toàn bộ schema từ một ví dụ trên internet rồi dùng trực tiếp ở production. Schema có thể thay đổi giữa các phiên bản Spring Session và các hệ quản trị. Hãy so sánh script đi kèm artifact của phiên bản dự án, kiểm tra migration và chạy integration test với database thực.

## 4. Khác biệt kiểu dữ liệu giữa các hệ quản trị

Một khác biệt lớn nằm ở cột lưu dữ liệu thuộc tính đã serialize. Cột này phải chứa bytes, không phải một chuỗi văn bản bị chuyển mã tùy tiện.

| Hệ quản trị | Kiểu nhị phân thường gặp | Lưu ý |
|---|---|---|
| PostgreSQL | **BYTEA** | Phù hợp lưu dữ liệu nhị phân; dùng script PostgreSQL tương ứng |
| MySQL/MariaDB | **BLOB** hoặc biến thể dung lượng lớn | Chú ý giới hạn kích thước, charset và cấu hình packet |
| SQL Server | **VARBINARY(MAX)** | Có thể dùng kiểu nhị phân lớn; kiểm tra giới hạn row và driver |
| Oracle | **BLOB** | LOB có thể cần cách bind/đọc phù hợp với driver và Spring JDBC |
| H2 | Kiểu binary large object hoặc kiểu binary tương ứng | Thường dùng cho test; không chứng minh SQL production tương thích |

Metadata session thường lưu thời điểm dưới dạng số nguyên lớn (epoch milliseconds) và timeout dưới dạng số giây. Cách này giúp tránh khác biệt giữa kiểu timestamp, timezone và hàm ngày giờ của các database. Không tự đổi các cột thời gian sang TIMESTAMP nếu chưa điều chỉnh cả SQL và mapping của repository.

Ngoài kiểu nhị phân, cần chú ý:

- Độ dài CHAR/VARCHAR cho session ID, principal và attribute name.
- Quy tắc so sánh chữ hoa/chữ thường và collation.
- Kiểu số nguyên và cách JDBC driver ánh xạ sang Java.
- Cách database lưu chuỗi Unicode.
- Kiểu LOB và cách driver truyền dữ liệu lớn.

## 5. Khác biệt tên schema và quoting identifier

Tên schema và quy tắc trích dẫn identifier không thống nhất giữa các hệ quản trị:

| Hệ quản trị | Cách chỉ định schema thường gặp | Cách quote identifier thường gặp |
|---|---|---|
| PostgreSQL | app.SPRING_SESSION | "SPRING_SESSION" |
| MySQL | app.SPRING_SESSION (database thường đóng vai trò schema) | **SPRING_SESSION** |
| SQL Server | dbo.SPRING_SESSION | [SPRING_SESSION] hoặc double quote khi bật cấu hình tương ứng |
| Oracle | APP.SPRING_SESSION | "SPRING_SESSION" |

Nên ưu tiên tên bảng/cột đơn giản, không dùng từ khóa SQL, không chứa dấu cách và tránh phụ thuộc vào quoting. PostgreSQL chuyển identifier không quote về chữ thường; identifier được quote có thể phân biệt hoa/thường. Một bảng được tạo bằng tên có quote và chữ hoa có thể không được tìm thấy nếu SQL runtime tham chiếu theo cách khác.

Nếu dùng schema riêng, cần đảm bảo user database có quyền trên schema và các bảng. Với connection pool, mọi connection phải có search path hoặc default schema nhất quán. Không chỉ kiểm tra kết nối bằng tài khoản quản trị, vì ứng dụng có thể chạy bằng user có quyền hẹp hơn.

## 6. Khác biệt cú pháp giới hạn số dòng và phân trang

Truy vấn cleanup hoặc công việc bảo trì có thể cần xử lý theo batch để tránh xóa quá nhiều dữ liệu trong một transaction. Cú pháp giới hạn số dòng khác nhau:

| Hệ quản trị | Ví dụ giới hạn kết quả |
|---|---|
| PostgreSQL | LIMIT 100 |
| MySQL | LIMIT 100 |
| SQL Server | TOP (100) hoặc OFFSET ... FETCH NEXT ... |
| Oracle 12c+ | FETCH FIRST 100 ROWS ONLY |

Ví dụ truy vấn PostgreSQL/MySQL:

~~~sql
SELECT SESSION_ID, EXPIRY_TIME
FROM SPRING_SESSION
WHERE EXPIRY_TIME < ?
ORDER BY EXPIRY_TIME
LIMIT 100;
~~~

Ví dụ SQL Server:

~~~sql
SELECT TOP (100) SESSION_ID, EXPIRY_TIME
FROM SPRING_SESSION
WHERE EXPIRY_TIME < ?
ORDER BY EXPIRY_TIME;
~~~

Ví dụ Oracle 12c trở lên:

~~~sql
SELECT SESSION_ID, EXPIRY_TIME
FROM SPRING_SESSION
WHERE EXPIRY_TIME < ?
ORDER BY EXPIRY_TIME
FETCH FIRST 100 ROWS ONLY;
~~~

Đây là các biến thể SQL minh họa cho truy vấn đọc theo batch. Không thay câu cleanup chuẩn bằng truy vấn giới hạn dòng một cách tùy tiện. Nếu cần cleanup theo batch, phải bảo đảm mỗi batch tiến triển, không bỏ sót dữ liệu, xử lý khóa cạnh tranh và phù hợp transaction semantics của repository.

## 7. Khác biệt upsert và cập nhật thuộc tính

Khi thêm hoặc cập nhật thuộc tính, repository cần duy trì một dòng duy nhất cho cặp SESSION_PRIMARY_ID và ATTRIBUTE_NAME. Một số database hỗ trợ cú pháp upsert riêng:

| Hệ quản trị | Cú pháp thường gặp |
|---|---|
| PostgreSQL | INSERT ... ON CONFLICT (...) DO UPDATE |
| MySQL/MariaDB | INSERT ... ON DUPLICATE KEY UPDATE |
| SQL Server | Có thể dùng UPDATE rồi INSERT có kiểm soát; MERGE cần đánh giá kỹ |
| Oracle | Có thể dùng MERGE INTO hoặc thao tác update/insert trong transaction |

Ví dụ PostgreSQL:

~~~sql
INSERT INTO SPRING_SESSION_ATTRIBUTES
    (SESSION_PRIMARY_ID, ATTRIBUTE_NAME, ATTRIBUTE_BYTES)
VALUES (?, ?, ?)
ON CONFLICT (SESSION_PRIMARY_ID, ATTRIBUTE_NAME)
DO UPDATE SET ATTRIBUTE_BYTES = EXCLUDED.ATTRIBUTE_BYTES;
~~~

Ví dụ MySQL:

~~~sql
INSERT INTO SPRING_SESSION_ATTRIBUTES
    (SESSION_PRIMARY_ID, ATTRIBUTE_NAME, ATTRIBUTE_BYTES)
VALUES (?, ?, ?)
ON DUPLICATE KEY UPDATE ATTRIBUTE_BYTES = VALUES(ATTRIBUTE_BYTES);
~~~

Các ví dụ trên minh họa khác biệt dialect. Cú pháp MySQL có thể có cảnh báo hoặc deprecation ở các phiên bản mới đối với một số cách tham chiếu giá trị; hãy dùng cú pháp được phiên bản server hỗ trợ. Với SQL Server, không mặc định dùng MERGE mà không xem xét các vấn đề đồng thời và lịch sử lỗi của phiên bản. Câu SQL thực tế phải được kiểm thử với driver và database đích.

Không phải mọi phiên bản Spring Session cho phép thay từng câu upsert qua một property cấu hình. Nếu repository đã cung cấp extension point cho SQL trong phiên bản đang dùng, hãy dùng đúng API đó. Nếu không, cần một repository tùy chỉnh hoặc adapter được kiểm thử, thay vì giả định có một thuộc tính chung như spring.session.jdbc.sql.*.

## 8. SQL cleanup và khác biệt giữa hết hạn với xóa vật lý

Spring Session JDBC lưu thời điểm hết hạn trong EXPIRY_TIME. Một session đã quá hạn phải được xem là không hợp lệ khi repository tra cứu, ngay cả khi dòng dữ liệu vẫn còn trước lần cleanup tiếp theo.

SQL khái niệm để tìm session quá hạn:

~~~sql
SELECT PRIMARY_ID, SESSION_ID
FROM SPRING_SESSION
WHERE EXPIRY_TIME < ?;
~~~

SQL khái niệm để xóa:

~~~sql
DELETE FROM SPRING_SESSION
WHERE EXPIRY_TIME < ?;
~~~

Nếu khóa ngoại bảng attributes được định nghĩa với ON DELETE CASCADE, database tự xóa các dòng thuộc tính khi dòng session cha bị xóa. Nếu schema không có cascade, repository hoặc cleanup implementation phải xóa dữ liệu con theo đúng thứ tự. Không thêm hoặc bỏ cascade mà chưa kiểm tra cách repository thực hiện delete.

Các điểm khác biệt cần xem xét:

- Cách database khóa dòng khi cleanup cạnh tranh với request cập nhật session.
- Có cần chia cleanup thành batch để tránh transaction dài không.
- Index trên EXPIRY_TIME có được dùng trong execution plan không.
- Thời điểm truyền tham số thời gian có cùng đơn vị epoch milliseconds không.
- Job cleanup có chạy đồng thời trên nhiều instance và gây tranh chấp không.

Không thay thời gian bằng hàm database như NOW() hoặc GETDATE() nếu logic repository hiện truyền epoch milliseconds từ ứng dụng. Trộn timezone, kiểu timestamp và đơn vị giây/milliseconds có thể xóa nhầm session hoặc giữ session quá lâu.

## 9. Placeholder, tham số và JDBC driver

Spring JDBC thường dùng placeholder positional ? cho tham số trong câu SQL. Mỗi dấu hỏi được bind theo thứ tự. Không nối dữ liệu đầu vào như session ID, principal name hoặc attribute name vào chuỗi SQL.

Ví dụ:

~~~java
String sql = """
    SELECT PRIMARY_ID, SESSION_ID, EXPIRY_TIME
    FROM SPRING_SESSION
    WHERE SESSION_ID = ?
    """;

SessionRow row = jdbcTemplate.queryForObject(
    sql,
    rowMapper,
    sessionId
);
~~~

Tên bảng và tên cột không thể bind như giá trị thông thường bằng placeholder. Nếu table name được cấu hình động, phải kiểm tra nó đến từ cấu hình tin cậy, validate theo quy tắc identifier và quote đúng dialect. Không lấy tên bảng từ request.

Với LOB/BLOB, cách bind dữ liệu lớn có thể khác nhau theo driver. Hãy kiểm tra:

- Kích thước tối đa của thuộc tính session và giới hạn packet/request.
- Hành vi streaming so với buffer toàn bộ bytes trong heap.
- Cách driver xử lý byte[], Blob hoặc InputStream.
- Transaction và thời gian sống của stream/connection.
- Cách xử lý NULL, empty bytes và dữ liệu lớn.

Không tự thay cột binary bằng text chỉ để xem dữ liệu dễ hơn. Việc chuyển bytes thành chuỗi có thể làm hỏng serialization format.

## 10. Khi nào cần thay câu SQL runtime?

Trước khi viết SQL tùy chỉnh, hãy xác định chính xác vấn đề:

| Nhu cầu | Hướng xử lý ưu tiên |
|---|---|
| Chỉ đổi tên bảng | Dùng cấu hình table-name/tableName mà phiên bản hỗ trợ |
| Đổi schema hoặc kiểu cột theo database | Dùng schema script riêng và migration |
| Chọn đúng dialect đã được hỗ trợ | Dùng schema và repository mặc định tương ứng |
| Tối ưu index | Đo execution plan; giữ nguyên các ràng buộc repository cần |
| Thay cleanup schedule | Cấu hình cron cleanup nếu API/Boot version hỗ trợ |
| Thay câu truy vấn vì database chưa được hỗ trợ | Xem extension point của repository; nếu không đủ, triển khai repository tùy chỉnh |
| Thêm hint/locking hoặc query đặc thù | Đánh giá transaction và concurrency; dùng custom repository có kiểm thử |

Spring Session JDBC không phải ORM tự sinh SQL theo một dialect JPA tổng quát. Repository sử dụng các câu SQL được thiết kế cho các database/platform mà phiên bản đó hỗ trợ. Vì vậy, thay một bean Hibernate Dialect hoặc cấu hình JPA không tự thay SQL của Spring Session.

Nếu phải tùy chỉnh SQL runtime, cần xem source/API của đúng phiên bản thư viện để biết câu lệnh nào có thể thay đổi. Không dựa vào tên phương thức nội bộ hoặc constant từ phiên bản cũ vì API có thể đã đổi. Khi viết repository riêng, cần giữ đủ hành vi: create, find, update, delete, attribute persistence, principal lookup, expiration và transaction.

## 11. Ví dụ cấu hình tên bảng và schema script riêng

Một cấu hình Spring Boot có thể trỏ đến script schema do dự án quản lý:

~~~yaml
spring:
  session:
    jdbc:
      initialize-schema: never
      schema: classpath:db/spring-session-postgresql.sql
      table-name: APP_SESSION
      cleanup-cron: "0 */5 * * * *"
~~~

Trong production, nếu migration tool đã tạo schema thì initialize-schema: never giúp tránh ứng dụng tự chạy script khởi tạo ngoài quy trình. Đường dẫn schema cần được dùng đúng theo cách Boot khởi tạo schema ở phiên bản hiện tại; nếu không dùng auto-initialization, migration tool phải tham chiếu script đã kiểm soát.

Tên bảng thực tế và tên bảng attributes được repository suy ra theo quy ước hỗ trợ của phiên bản. Trước khi đặt tiền tố hoặc tên tùy chỉnh, hãy xác minh chính xác tên bảng mà repository truy vấn. Nếu bảng được đặt trong schema riêng, kiểm tra cơ chế qualify schema, search path và quyền database user.

## 12. Chuyển database hoặc thay dialect

Di chuyển từ một hệ quản trị sang hệ khác không chỉ là đổi JDBC URL. Cần kiểm kê:

1. Phiên bản Spring Session và script schema hiện tại.
2. Tên schema, bảng, index, constraint và collation.
3. Kiểu dữ liệu binary, độ dài cột và cách lưu thời gian.
4. SQL runtime có tùy chỉnh và các extension point đang dùng.
5. Transaction isolation, lock timeout, connection pool và driver version.
6. Dữ liệu session còn hiệu lực và serializer đang dùng.

Session thường có TTL tương đối ngắn; trong một số lần chuyển đổi, tổ chức có thể chọn kết thúc toàn bộ session cũ và yêu cầu người dùng đăng nhập lại. Nếu cần giữ phiên, phải có kế hoạch chuyển dữ liệu và xác minh bytes attribute tương thích. Không chỉ copy hai bảng bằng công cụ migration rồi giả định repository mới đọc được mọi dòng.

Một chiến lược chuyển đổi có kiểm soát:

- Dựng schema mới bằng script chính thức của database đích.
- Chạy integration test tạo/đọc/cập nhật/xóa session trên database mới.
- Nếu cần giữ session, chuyển metadata và attribute bytes theo đúng định dạng, kiểm tra khóa chính/khóa ngoại.
- Kiểm tra số lượng session còn hạn và số dòng attributes sau chuyển đổi.
- Chuyển traffic theo giai đoạn, tránh để hai hệ thống cùng ghi một session ID vào hai store không đồng bộ.
- Có phương án rollback hoặc chủ động buộc đăng nhập lại nếu dữ liệu không tương thích.

## 13. Kiểm thử SQL tùy chỉnh

SQL tùy chỉnh cần được kiểm thử với database thật hoặc môi trường tương thích chính xác. H2 có thể hữu ích cho test nhanh nhưng không đại diện đầy đủ cho cú pháp, locking, LOB, collation và transaction của PostgreSQL, MySQL, SQL Server hoặc Oracle.

Ma trận kiểm thử nên có:

| Kịch bản | Điều cần xác minh |
|---|---|
| Khởi tạo schema | Script chạy được trên đúng database và tạo đủ constraint/index |
| Tạo session | Dòng metadata được ghi và ID là duy nhất |
| Ghi nhiều attributes | Bảng con lưu đủ tên và bytes |
| Đọc session | Thuộc tính được deserialize đúng |
| Cập nhật attribute | Không tạo duplicate cho khóa kép |
| Xóa attribute | Chỉ thuộc tính yêu cầu bị xóa |
| Logout/invalidate | Dòng cha và dữ liệu con được xóa đúng |
| Expiration cleanup | Session hết hạn bị dọn theo lịch và không xóa session còn hiệu lực |
| Principal lookup | Truy vấn theo principal trả đúng nhiều session nếu có |
| Concurrent update | Không mất dữ liệu do upsert/locking sai |
| LOB lớn | Driver ghi/đọc bytes theo giới hạn dự kiến |
| Multi-instance | Hai instance cùng đọc/ghi một session qua cùng database |
| Migration | SQL và schema mới đọc được dữ liệu được ghi trước đó |

Kiểm tra execution plan cho các truy vấn tra session ID, tìm session theo principal và cleanup theo expiration. Đảm bảo index hỗ trợ điều kiện WHERE thực tế. Đừng thêm index tùy tiện trên cột LOB hoặc các tổ hợp không được truy vấn; mỗi index bổ sung đều tăng chi phí ghi.

## 14. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Lỗi cú pháp gần LIMIT hoặc TOP | Dùng SQL của database khác | Dùng script/query đúng dialect |
| Không tìm thấy bảng | Sai schema, search path hoặc table name không khớp | Kiểm tra cấu hình repository và migration |
| Lỗi kiểu binary khi lưu attributes | DDL dùng kiểu không tương thích với driver | Dùng kiểu LOB/binary trong schema chuẩn của database |
| Trùng session ID | Thiếu unique constraint/index | Khôi phục ràng buộc và kiểm tra dữ liệu trùng |
| Attribute mồ côi | Thiếu FK/cascade hoặc custom delete không xóa bảng con | Đồng bộ quan hệ cha-con và transaction |
| Cleanup xóa nhầm phiên | Sai đơn vị thời gian hoặc timezone | Giữ epoch milliseconds và kiểm tra tham số bind |
| Upsert lỗi khi có request đồng thời | Cú pháp upsert/locking không phù hợp database | Dùng câu SQL tương thích và kiểm thử concurrency |
| SQL tùy chỉnh chạy ở dev nhưng lỗi production | Dev dùng H2, production dùng database khác | Test bằng cùng engine và driver với production |
| Repository không dùng câu SQL dự kiến | Cấu hình chỉ đổi schema/table, không thay query runtime | Xác minh API repository và điểm mở rộng theo version |
| Chậm sau khi thêm index | Index không khớp truy vấn hoặc làm tăng write cost | Dùng execution plan và workload đo được |

## 15. Nguyên tắc triển khai

- Bắt đầu từ schema script chính thức cho database và phiên bản Spring Session đang dùng.
- Phân biệt rõ tùy chỉnh DDL, table name và câu SQL runtime.
- Dùng migration tool để quản lý schema production; không để nhiều instance tự khởi tạo schema cạnh tranh.
- Chọn đúng kiểu binary/LOB và giữ nguyên đơn vị thời gian mà repository mong đợi.
- Giữ primary key, unique index, composite key và foreign key cần thiết.
- Không giả định JPA Dialect điều khiển SQL của Spring Session JDBC.
- Chỉ thay câu SQL qua extension point được phiên bản hỗ trợ hoặc repository tùy chỉnh có kiểm thử; không bịa property cấu hình chung.
- Bind giá trị bằng placeholder; chỉ cho phép table/schema identifier từ cấu hình tin cậy.
- Kiểm thử upsert, cleanup, locking và LOB trên database đích.
- Khi đổi dialect hoặc serializer, có kế hoạch migration và tương thích session đang tồn tại.

Spring Session JDBC cung cấp một mô hình session thống nhất, nhưng SQL và schema vẫn phải phù hợp với hệ quản trị cơ sở dữ liệu cụ thể. Khi giữ nguyên hợp đồng giữa metadata, attributes, khóa và transaction, đồng thời chỉ tùy chỉnh qua các điểm mở rộng được hỗ trợ, ứng dụng có thể vận hành session ổn định trên nhiều database mà không làm sai lệch vòng đời phiên.
