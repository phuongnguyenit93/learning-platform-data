# Kiểm tra đặc tính Oracle và các trình điều khiển khác trước khi sử dụng

Spring Data Relational R2DBC cung cấp mô hình truy cập dữ liệu chung, nhưng không làm cho mọi hệ quản trị và R2DBC driver có cùng hành vi. Một tính năng có thể tồn tại trong R2DBC SPI nhưng chưa được driver triển khai; driver có thể hỗ trợ nhưng Spring Data dialect chưa sinh đúng SQL; database có thể chấp nhận câu lệnh nhưng có semantics khác với hệ quản trị mà nhóm đã dùng trước đó.

Oracle là ví dụ điển hình cần kiểm tra có hệ thống. Cú pháp phân trang, sequence, generated values, kiểu dữ liệu, LOB, transaction isolation, locking, DDL và error code có thể khác PostgreSQL, MySQL, SQL Server hoặc H2. Việc ứng dụng khởi động và chạy được một câu SELECT đơn giản chưa chứng minh toàn bộ tính năng persistence hoạt động đúng.

Bài học này hướng dẫn cách đánh giá Oracle R2DBC và các driver khác trước khi chọn dùng trong dự án. Trọng tâm là phân biệt ba lớp năng lực: database, R2DBC driver và Spring Data R2DBC dialect; lập ma trận tính năng; thử các trường hợp quan trọng bằng integration test; và ghi lại giới hạn cần biết trước khi triển khai.

## 1. Vì sao không thể coi các R2DBC driver là tương đương?

R2DBC định nghĩa SPI chung cho các thao tác như mở connection, tạo statement, bind giá trị, thực thi query, đọc result và quản lý transaction. SPI giúp ứng dụng dùng một kiểu API reactive nhất quán.

Tuy nhiên, SPI không chuẩn hóa toàn bộ SQL hoặc mọi tính năng riêng của từng database. Các khác biệt có thể nằm ở:

- Cú pháp SQL và placeholder của bind parameter.
- Cách sinh ID, sequence và trả generated values.
- Kiểu dữ liệu và conversion giữa database với Java.
- LOB, JSON, array, enum, XML và kiểu dữ liệu do người dùng định nghĩa.
- Transaction isolation, savepoint, locking và DDL.
- Metadata của schema, table, column và generated key.
- Batch statement, nhiều result và stored procedure.
- Cancellation, timeout, pooling và TLS.
- SQLState, vendor error code và exception translation.

Một ứng dụng có thể dùng cùng ReactiveCrudRepository trên hai database nhưng vẫn phải điều chỉnh schema, query, mapping hoặc transaction behavior.

~~~text
Ứng dụng Spring Data R2DBC
          |
          v
Spring Data dialect / mapping
          |
          v
R2DBC SPI
          |
          v
Driver cụ thể
          |
          v
Database engine
~~~

Mỗi lớp có một hợp đồng riêng. Cần xác định tính năng đang cần thuộc lớp nào trước khi đánh giá hỗ trợ.

## 2. Ba lớp cần kiểm tra: database, driver và Spring Data dialect

### 2.1. Khả năng của database

Database engine quyết định SQL nào hợp lệ và semantics thực thi:

- Có hỗ trợ OFFSET ... FETCH hay cần ROWNUM/ROW_NUMBER()?
- Isolation level nào được hỗ trợ?
- DDL có thể rollback trong transaction hay gây implicit commit?
- Sequence và generated column hoạt động thế nào?
- Có hỗ trợ RETURNING, SELECT FOR UPDATE, JSON, array hoặc LOB ra sao?

Một tính năng database có thể tồn tại nhưng driver không cung cấp API để sử dụng thuận tiện.

### 2.2. Khả năng của R2DBC driver

Driver quyết định cách ánh xạ SPI vào protocol và API của database:

- Placeholder SQL nào được chấp nhận?
- Statement.returnGeneratedValues(...) có hoạt động không?
- Java type nào có thể bind và đọc?
- Blob/Clob có được stream không?
- Có hỗ trợ savepoint, isolation và cancellation không?
- Lỗi database được đưa ra dưới lớp R2dbcException nào?

Không nên kết luận driver hỗ trợ một tính năng chỉ vì database hỗ trợ tính năng tương ứng.

### 2.3. Khả năng của Spring Data R2DBC dialect

Spring Data sử dụng dialect để biết cách sinh SQL và biểu diễn khác biệt database. Dialect có thể cung cấp thông tin về:

- Bind markers.
- Cú pháp phân trang.
- Cách lấy generated values.
- Identifier processing.
- Kiểu dữ liệu đơn giản và conversion.
- Một số khả năng SQL đặc thù.

Driver có thể chạy được SQL thủ công nhưng Spring Data dialect chưa chắc đã sinh SQL đúng cho repository method hoặc entity callback. Ngược lại, dialect có thể khai báo một khả năng nhưng driver phiên bản hiện tại chưa triển khai đầy đủ.

**Kết luận kỹ thuật cần dựa trên cả ba lớp.** Không lấy một câu trả lời “Oracle hỗ trợ” làm bằng chứng rằng Oracle R2DBC, phiên bản driver đang dùng và Spring Data hiện tại đều hỗ trợ tính năng đó.

## 3. Oracle R2DBC trong hệ sinh thái Spring

Oracle cung cấp R2DBC driver riêng cho Oracle Database. Artifact, phiên bản driver, Oracle JDBC dependency nền (nếu phiên bản driver yêu cầu), R2DBC SPI và phiên bản database cần được chọn theo bảng tương thích của nhà cung cấp.

Các yếu tố cần ghi lại trước khi tích hợp:

1. Phiên bản Oracle Database và edition đang chạy.
2. Phiên bản Oracle R2DBC driver.
3. Phiên bản R2DBC SPI mà driver sử dụng.
4. Phiên bản Spring Boot và Spring Data Relational.
5. Phiên bản Java.
6. Driver phụ thuộc vào thư viện nào và phiên bản nào.
7. Hệ điều hành, kiến trúc và cách đóng gói runtime.
8. Các tính năng Oracle mà ứng dụng thực sự cần.

Không lấy phiên bản mới nhất của từng dependency rồi ghép tùy ý. Kiểm tra dependency compatibility và release notes của driver, Spring Boot BOM và Spring Data release train. Một nâng cấp driver có thể kéo theo thay đổi về SPI, JDBC dependency, mapping hoặc yêu cầu database.

### 3.1. Khai báo dependency và connection

Tên artifact và version phải lấy từ tài liệu tương thích của release được chọn. Ví dụ cấu hình khái quát:

~~~xml
<dependency>
    <groupId>com.oracle.database.r2dbc</groupId>
    <artifactId>oracle-r2dbc</artifactId>
    <version>`${oracle.r2dbc.version}`</version>
</dependency>
~~~

Tên artifact và dependency transitives có thể thay đổi giữa các release; dùng đúng tọa độ Maven được nhà cung cấp công bố cho phiên bản đang triển khai.

Connection URL thường có scheme dành riêng cho Oracle R2DBC, ví dụ dạng:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:oracle://db-host:1521/service-name
    username: `${DB_USERNAME}`
    password: `${DB_PASSWORD}`
~~~

Đây là cấu trúc minh họa. Service name, SID, wallet, TCPS, TLS và các connection option phải theo tài liệu driver và cấu hình Oracle thực tế. Không thay scheme R2DBC bằng JDBC URL jdbc:oracle:thin:....

Nếu driver yêu cầu hoặc sử dụng Oracle JDBC driver bên dưới, hãy kiểm tra phiên bản tương thích và tránh ép một JDBC driver không được hỗ trợ vào classpath.

### 3.2. Đừng suy luận non-blocking chỉ từ kiểu trả về

R2DBC API trả về Publisher, nhưng mức độ non-blocking của hoạt động I/O và cách driver sử dụng thư viện nền là chi tiết triển khai. Với Oracle driver, cần đọc tài liệu release cụ thể để hiểu kiến trúc, yêu cầu dependency, thread model và giới hạn vận hành.

Đừng tự đưa block() vào service để “làm cho Oracle hoạt động”. Nếu driver có giới hạn hoặc có đường xử lý cần scheduler riêng, giải quyết theo tài liệu chính thức và đo bằng thử nghiệm tải. Một API trả Mono không tự chứng minh mọi công đoạn bên dưới đều không chặn thread.

## 4. Kiểm tra Spring Data dialect có nhận diện Oracle hay không

Spring Data R2DBC dùng dialect để tạo SQL phù hợp với database. Khi đổi driver, hãy xác nhận dialect được chọn thực sự tương ứng với Oracle.

Các câu hỏi cần trả lời:

- Phiên bản Spring Data Relational đang dùng có Oracle dialect tích hợp không?
- Resolver nhận diện được metadata của Oracle R2DBC driver không?
- Nếu có nhiều ConnectionFactory, dialect có được gắn với đúng factory không?
- Dialect sinh bind marker và pagination SQL nào?
- Generated value strategy có phù hợp với Oracle không?
- Có cần custom dialect hoặc dùng DatabaseClient với SQL riêng không?

Không suy đoán tên class hoặc tự cấu hình một dialect chỉ dựa trên tên database. Kiểm tra tài liệu Spring Data của đúng release và xác nhận bằng integration test.

Nếu dialect không có sẵn hoặc thiếu một tính năng, các lựa chọn gồm:

1. Nâng lên phiên bản Spring Data có hỗ trợ phù hợp, sau khi kiểm tra tương thích.
2. Dùng DatabaseClient cho truy vấn đặc thù với SQL Oracle rõ ràng.
3. Viết custom dialect/provider nếu Spring Data extension point của phiên bản đó hỗ trợ và nhóm có thể duy trì.
4. Dùng repository cho phần SQL portable và tách riêng adapter Oracle cho phần đặc thù.

Không nên thay dialect nội bộ bằng reflection hoặc override class không public; cách đó dễ hỏng khi nâng phiên bản.

## 5. SQL phân trang: Oracle khác LIMIT/OFFSET ra sao?

Nhiều ví dụ SQL trên PostgreSQL hoặc MySQL dùng:

~~~sql
SELECT id, order_number
FROM purchase_order
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;
~~~

Oracle Database hỗ trợ cú pháp phân trang OFFSET ... ROWS FETCH NEXT ... ROWS ONLY ở các phiên bản hỗ trợ row limiting clause:

~~~sql
SELECT id, order_number
FROM purchase_order
ORDER BY created_at DESC, id DESC
OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Với hệ Oracle cũ hơn chưa hỗ trợ cú pháp này, thường phải dùng ROWNUM hoặc ROW_NUMBER() trong truy vấn lồng nhau. Cần kiểm tra phiên bản database thực tế thay vì chỉ dựa vào tên Oracle.

Khi dùng Spring Data Pageable, không giả định dialect tự động sinh SQL đúng chỉ vì query có Pageable. Chạy integration test trên Oracle để xác nhận:

- Trang đầu.
- Trang giữa.
- Trang cuối.
- Kích thước trang bằng 0 hoặc giá trị không hợp lệ.
- Sort nhiều cột.
- Sort key có giá trị trùng.
- Offset lớn.
- Query có join hoặc projection.

Phân trang luôn cần thứ tự xác định, thường thêm khóa duy nhất làm tie-breaker. Không có ORDER BY thì database không bảo đảm thứ tự hàng giữa các request.

### 5.1. Keyset pagination có thể giảm phụ thuộc offset

Nếu danh sách lớn hoặc thay đổi liên tục, có thể dùng seek/keyset pagination bằng điều kiện trên sort key thay vì offset. Ví dụ với thứ tự giảm dần:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE created_at < :last_created_at
   OR (created_at = :last_created_at AND id < :last_id)
ORDER BY created_at DESC, id DESC
FETCH NEXT :page_size ROWS ONLY;
~~~

Cú pháp bind marker và khả năng bind limit cần xác nhận với driver Oracle R2DBC. Ví dụ trên minh họa SQL; không coi tên tham số :last_created_at là cú pháp placeholder portable của mọi driver.

Keyset vẫn cần cursor chứa toàn bộ sort key và không tự tạo snapshot. Nếu sort key có thể thay đổi, hàng có thể di chuyển qua cursor.

## 6. Placeholder và parameter binding

R2DBC SPI cung cấp Statement.bind(index, value) và bindNull, nhưng cú pháp placeholder trong SQL phụ thuộc driver.

Một số driver dùng dấu ?, driver khác dùng dạng có tên hoặc số thứ tự như $1 hoặc :name/:1. Không sao chép nguyên SQL từ PostgreSQL sang Oracle mà không kiểm tra.

Spring DatabaseClient có thể cung cấp named parameter abstraction và chuyển đổi sang bind marker của dialect. Nhưng cần xác nhận dialect được chọn đúng và driver nhận cú pháp sau khi chuyển đổi.

Khi viết SQL trực tiếp:

- Dùng placeholder theo tài liệu Oracle R2DBC release hiện tại.
- Bind giá trị, không nối chuỗi người dùng vào SQL.
- Dùng bindNull(index, type) hoặc API tương đương được hỗ trợ.
- Kiểm tra cách bind enum, timestamp, UUID và kiểu số.
- Không bind tên bảng, tên cột hoặc từ khóa sort như value parameter; dùng whitelist identifier.
- Kiểm tra thứ tự parameter sau khi query được tạo động.

Một smoke test phải thực hiện ít nhất một SELECT có bind, một INSERT có bind, một UPDATE và một giá trị null.

## 7. Sinh khóa chính: sequence, identity và generated values

Oracle có nhiều chiến lược sinh ID:

- Sequence tường minh.
- Identity column trên phiên bản Oracle hỗ trợ.
- Trigger kết hợp sequence trong schema cũ.
- ID do ứng dụng cấp.

Sequence có thể được lấy trước khi insert:

~~~sql
SELECT order_seq.NEXTVAL FROM dual;
~~~

Sau đó bind ID vào INSERT:

~~~sql
INSERT INTO purchase_order (id, order_number, status)
VALUES (:id, :order_number, :status);
~~~

DUAL là bảng đặc biệt thường dùng để chọn một biểu thức trong Oracle. Placeholder trong ví dụ phải thay bằng cú pháp bind đúng của driver.

Oracle có cú pháp RETURNING ... INTO để lấy giá trị do DML tạo hoặc thay đổi, nhưng cách dùng qua R2DBC phụ thuộc khả năng của Oracle R2DBC driver và API Statement.returnGeneratedValues(...) trong release đang dùng.

Trước khi dựa vào generated values, hãy kiểm tra:

1. Driver có hỗ trợ returnGeneratedValues cho loại INSERT/UPDATE đó không?
2. Có thể yêu cầu tên cột nào?
3. Kết quả được trả dưới dạng Result.map hay API khác?
4. Identity và sequence có cùng behavior không?
5. Batch insert có trả generated values theo từng hàng không?
6. Khi insert nhiều hàng, thứ tự generated key có được bảo đảm không?

Không dùng SELECT MAX(id) để tìm ID vừa insert. Với request đồng thời, kết quả có thể thuộc transaction khác. Nếu generated value API chưa đáp ứng, có thể lấy sequence trước rồi insert với ID đã biết, sau khi xác nhận chiến lược đó phù hợp schema.

## 8. Kiểu dữ liệu Oracle và Java mapping

Tên kiểu dữ liệu của Oracle không giống PostgreSQL hoặc MySQL. Mapping tự động phụ thuộc driver, Spring converters và kiểu cột cụ thể.

| Kiểu Oracle thường gặp | Kiểu Java có thể cân nhắc | Điều cần kiểm tra |
|---|---|---|
| NUMBER | BigDecimal | Precision, scale và giới hạn giá trị |
| NUMBER(p,0) | Long, Integer, BigInteger hoặc BigDecimal | Giá trị thực tế có vượt miền kiểu không |
| VARCHAR2 | String | Character set, độ dài byte/char và collation |
| NVARCHAR2 | String | Unicode và driver conversion |
| CHAR / NCHAR | String | Padding khoảng trắng và semantics so sánh |
| DATE | Kiểu ngày giờ Java phù hợp | Oracle DATE có cả phần thời gian |
| TIMESTAMP | LocalDateTime hoặc kiểu được driver hỗ trợ | Precision và timezone semantics |
| TIMESTAMP WITH TIME ZONE | OffsetDateTime/Instant nếu hỗ trợ | Giữ offset hay normalize về instant |
| TIMESTAMP WITH LOCAL TIME ZONE | Kiểu thời gian theo driver | Giá trị được chuẩn hóa theo session timezone |
| RAW | byte[] hoặc ByteBuffer | Độ dài và conversion |
| BLOB | Blob/publisher bytes hoặc kiểu ứng dụng | Streaming, buffering và resource lifetime |
| CLOB / NCLOB | Clob hoặc text | Character encoding và kích thước lớn |
| JSON, XMLTYPE, object type | String hoặc kiểu chuyên biệt | Hỗ trợ driver và conversion tùy phiên bản |

Bảng chỉ là gợi ý thiết kế, không phải cam kết conversion cho mọi phiên bản driver. Kiểm tra tài liệu type mapping của driver và viết test round-trip cho kiểu quan trọng.

### 8.1. NUMBER không mặc nhiên là Long

Oracle NUMBER có thể lưu giá trị số lớn, số thập phân hoặc số nguyên. Nếu map mọi NUMBER sang Long, có thể mất phần thập phân hoặc overflow.

- Dùng BigDecimal khi cần giữ precision/scale.
- Dùng Long khi schema và miền nghiệp vụ bảo đảm giá trị nguyên nằm trong giới hạn.
- Kiểm tra precision và scale trong schema.
- Test giá trị biên, âm, null và số thập phân.

Không dùng double cho số tiền hoặc dữ liệu cần độ chính xác thập phân.

### 8.2. Oracle DATE có phần giờ

Oracle DATE lưu năm, tháng, ngày, giờ, phút và giây; nó không chỉ là ngày lịch như một số kiểu DATE của hệ quản trị khác. Nếu map sang LocalDate, phần thời gian có thể bị bỏ.

Nếu nghiệp vụ cần thời điểm, dùng kiểu Java và converter phù hợp, thường cân nhắc LocalDateTime hoặc kiểu có timezone tùy cột và quy ước hệ thống.

### 8.3. Timezone và session

TIMESTAMP WITH TIME ZONE và TIMESTAMP WITH LOCAL TIME ZONE có semantics khác nhau. Session timezone cũng có thể ảnh hưởng cách hiển thị hoặc chuyển đổi giá trị.

Kiểm tra bằng test:

- Lưu một thời điểm có offset khác UTC.
- Đọc lại qua cùng connection và connection mới.
- Đổi session timezone nếu ứng dụng có thao tác này.
- Xác nhận instant không bị dịch ngoài ý muốn.
- Xác nhận precision khi database làm tròn hoặc cắt phần fractional seconds.

Đừng dùng LocalDateTime rồi tự coi nó là UTC nếu schema không ghi timezone và ứng dụng chưa có quy ước rõ ràng.

## 9. LOB và dữ liệu lớn

Oracle thường dùng BLOB, CLOB và NCLOB cho dữ liệu lớn. R2DBC SPI có abstraction Blob và Clob, nhưng khả năng stream, lifecycle và mapping phụ thuộc driver.

Cần kiểm tra:

- Driver có hỗ trợ đọc LOB theo kiểu streaming không?
- Có tự buffer toàn bộ dữ liệu vào memory không?
- LOB locator có còn hợp lệ sau khi result/connection đóng không?
- Có cần tiêu thụ hoặc giải phóng LOB riêng không?
- Cancellation giữa lúc stream có giải phóng resource không?
- Batch hoặc transaction có giới hạn với LOB không?

Không chuyển một BLOB lớn thành byte[] nếu kích thước có thể vượt bộ nhớ an toàn. Với file lớn, cân nhắc stream theo chunk và giới hạn concurrency.

Test với dữ liệu rỗng, null, nhỏ hơn buffer, lớn hơn buffer và payload lớn gần giới hạn ứng dụng. Kiểm tra cả upload, download, cancellation và cleanup.

## 10. JSON, array, enum và kiểu dữ liệu đặc thù

Một ứng dụng chuyển từ PostgreSQL sang Oracle có thể dựa vào jsonb, array, enum native hoặc operator riêng. Không giả định Oracle biểu diễn hoặc driver map các kiểu này giống nhau.

Cần lập danh sách kiểu dữ liệu đặc thù đang sử dụng:

- JSON document và toán tử truy vấn JSON.
- SQL array.
- Enum.
- UUID.
- Spatial/geospatial.
- XML.
- User-defined object type.
- Binary/RAW.
- Full-text hoặc vector type nếu có.

Với mỗi loại, xác định:

1. Database Oracle phiên bản nào hỗ trợ kiểu đó?
2. Driver có bind và đọc kiểu đó qua R2DBC SPI không?
3. Spring Data converter có sẵn hay cần custom converter?
4. Query operator có portable không?
5. Có index phù hợp và execution plan đúng không?
6. Dữ liệu có round-trip không mất precision hoặc format không?

Nếu không có mapping chuẩn, có thể lưu JSON dưới dạng text/CLOB hoặc dùng adapter chuyên biệt, nhưng phải cân nhắc indexing, validation, queryability và chi phí chuyển đổi. Không chọn kiểu thay thế chỉ vì test đơn giản chạy được.

## 11. Identifier, schema và metadata

Oracle thường lưu identifier không quote theo quy tắc uppercase; identifier được quote có semantics phân biệt chữ hoa/chữ thường. Điều này có thể ảnh hưởng:

- Tên bảng và cột trong @Table, @Column.
- Alias trong native query.
- Schema và owner.
- Metadata trả về từ RowMetadata.
- Cách Spring Data sinh identifier.
- Migration tạo bảng bằng tên có quote.

Ví dụ:

~~~sql
CREATE TABLE CUSTOMER (
    ID NUMBER(19) PRIMARY KEY,
    EMAIL VARCHAR2(200) NOT NULL
);
~~~

Nếu tạo identifier có quote và chữ thường:

~~~sql
CREATE TABLE "customer" (
    "id" NUMBER(19) PRIMARY KEY
);
~~~

thì tên quoted có thể cần được tham chiếu chính xác như đã tạo. Tránh trộn quy tắc quoted và unquoted nếu không có lý do.

Khi dùng projection hoặc DatabaseClient, đặt alias rõ ràng:

~~~sql
SELECT c.ID AS CUSTOMER_ID,
       c.EMAIL AS CUSTOMER_EMAIL
FROM CUSTOMER c;
~~~

Kiểm tra cách driver trả tên cột và cách truy cập bằng label/index. Không giả định metadata casing giống PostgreSQL.

## 12. Sequence, schema owner và quyền truy cập

Oracle thường tổ chức object theo schema owner. User kết nối có thể không phải owner của bảng và cần quyền truy cập được cấp tường minh.

Trước khi triển khai, kiểm tra:

- User kết nối có quyền SELECT/INSERT/UPDATE/DELETE trên bảng không?
- Có quyền dùng sequence không?
- Synonym có được dùng không và driver/schema metadata xử lý thế nào?
- Current schema/session được thiết lập ra sao?
- Migration chạy bằng user nào?
- Object nằm trong schema nào?
- Quoted identifier và tên owner có khớp không?

Không chạy ứng dụng bằng tài khoản DBA hoặc schema owner có quyền quá rộng chỉ để tránh lỗi permission. Tạo user runtime với quyền tối thiểu cần thiết và user migration riêng nếu quy trình triển khai yêu cầu.

## 13. Transaction isolation và DDL semantics

Isolation level không có semantics đồng nhất giữa các hệ quản trị.

Oracle thường dùng READ COMMITTED làm mức mặc định và hỗ trợ SERIALIZABLE với mô hình nhất quán riêng. Không giả định Oracle cung cấp đúng behavior của REPEATABLE READ như PostgreSQL hoặc SQL Server. Kiểm tra tài liệu Oracle và cách driver ánh xạ yêu cầu isolation từ R2DBC SPI.

Các câu hỏi cần kiểm tra:

- Mức isolation nào được driver chấp nhận?
- setTransactionIsolationLevel có thực sự thay đổi session không?
- Database từ chối hay ánh xạ một mức không hỗ trợ?
- Transaction có snapshot consistency theo statement hay transaction?
- Lỗi serialization/transaction conflict được driver biểu diễn thế nào?
- Savepoint có hoạt động qua driver không?
- Read-only transaction có được database cưỡng chế không?

### 13.1. DDL có thể gây implicit commit

Oracle có semantics DDL khác nhiều database: phần lớn DDL thực hiện implicit commit trước và sau câu lệnh. Vì vậy, không giả định có thể rollback CREATE TABLE, ALTER TABLE hoặc DROP TABLE như một DML bình thường.

Điều này quan trọng với test dùng @Transactional để rollback. DDL trong test có thể tồn tại sau rollback hoặc ảnh hưởng transaction theo cách khác mong đợi.

Nên chạy migration/schema setup ở giai đoạn khởi tạo database riêng, tách khỏi transaction test nghiệp vụ. Nếu cần kiểm thử DDL, tạo database/schema ephemeral và xác nhận behavior trực tiếp.

### 13.2. Savepoint và nested transaction

NESTED trong Spring thường cần savepoint. Kiểm tra Oracle driver có hỗ trợ các thao tác savepoint mà transaction manager yêu cầu ở release đang dùng hay không.

Đừng suy luận REQUIRES_NEW, NESTED hoặc isolation chỉ từ annotation. Chúng còn phụ thuộc connection pool, transaction manager và driver.

## 14. Locking và câu lệnh đặc thù

Oracle hỗ trợ các dạng row locking như SELECT ... FOR UPDATE; một số tùy chọn như NOWAIT, WAIT và SKIP LOCKED có semantics riêng.

Ví dụ minh họa:

~~~sql
SELECT id, available_quantity
FROM INVENTORY
WHERE id = :id
FOR UPDATE;
~~~

Cần xác nhận placeholder và cú pháp thực tế với driver Oracle R2DBC. Lock thường được giữ đến khi transaction commit hoặc rollback. Transaction càng dài, khả năng contention càng cao.

Nếu dùng SKIP LOCKED cho worker lấy job, cần xác định semantics khi không có hàng khả dụng và cách tránh job bị bỏ qua quá lâu. Nếu dùng NOWAIT, lỗi lock conflict có thể cần được chuyển thành trạng thái retry hoặc conflict nghiệp vụ.

Các hệ quản trị khác có cú pháp và behavior locking khác. Đừng viết query lock trong repository rồi kỳ vọng dùng nguyên vẹn trên mọi driver.

## 15. Stored procedure, function và nhiều result

Stored procedure và function có khác biệt lớn giữa Oracle, PostgreSQL, SQL Server và MySQL:

- Cú pháp gọi.
- IN/OUT/IN OUT parameter.
- Cursor/ref cursor.
- Nhiều result set.
- Kiểu object/record trả về.
- Transaction behavior bên trong procedure.
- Exception và error code.

R2DBC SPI có mô hình Result, nhưng khả năng biểu diễn OUT parameter hoặc cursor cụ thể phụ thuộc driver. Không giả định một stored procedure JDBC có thể gọi bằng cùng API trên R2DBC.

Nếu ứng dụng phụ thuộc procedure:

1. Tạo một spike riêng trên driver mục tiêu.
2. Gọi procedure có input đơn giản.
3. Thử output scalar.
4. Thử cursor/result set.
5. Kiểm tra null, kiểu số và LOB.
6. Kiểm tra lỗi trong procedure.
7. Kiểm tra transaction commit/rollback.
8. Kiểm tra cancellation và connection cleanup.

Nếu driver không hỗ trợ đầy đủ, cân nhắc thay procedure bằng SQL hoặc service-side orchestration, hoặc giữ một adapter JDBC riêng nếu kiến trúc cho phép và chấp nhận hai mô hình kết nối.

## 16. Batch và nhiều statement

Không phải driver nào cũng hỗ trợ batch hoặc Statement.add() giống nhau về hiệu năng và kết quả.

Cần kiểm tra:

- Batch có thực thi tất cả binding sets không?
- getRowsUpdated() trả một count hay nhiều count?
- Một lỗi giữa batch có dừng các phần tử sau không?
- Kết quả một phần có thể đã commit không?
- Batch có thể lấy generated key cho từng hàng không?
- Có giới hạn kích thước batch hoặc số parameter không?
- Batch có hoạt động trong transaction không?

Nếu yêu cầu atomicity, đặt batch trong transaction và kiểm tra rollback trên database mục tiêu. Không coi batch tự động tương đương transaction.

Đo throughput và memory với kích thước batch thực tế. Một batch quá lớn có thể tạo áp lực memory, lock hoặc redo/undo log.

## 17. Cancellation, timeout và connection pool

Reactive API cho phép subscriber hủy subscription, nhưng driver có thể khác nhau về cách gửi cancel tới database và giải phóng tài nguyên.

Kiểm tra:

- Hủy một SELECT đang chạy có dừng server-side statement không?
- Hủy một INSERT khi chưa nhận response có thể đã commit không?
- Connection sau cancellation có được trả về pool an toàn không?
- Statement timeout và transaction timeout có khác nhau không?
- Pool acquisition timeout có được phân biệt với query timeout không?
- Driver có validation/reset connection trước khi trả về pool không?

Không retry một thao tác ghi chỉ vì client nhận cancellation. Database có thể đã thực hiện và commit thao tác trước khi cancellation được xử lý. Dùng idempotency key, unique constraint hoặc thiết kế operation có thể xác định kết quả sau timeout.

Khi cấu hình pool, đo:

- Số connection đang active/idle.
- Thời gian chờ lấy connection.
- Số lần validation thất bại.
- Số connection bị dispose.
- Thời gian query và transaction.
- Tỷ lệ timeout/cancellation.

Không dùng một connection cho nhiều request đồng thời trừ khi driver và API cụ thể cho phép; thông thường mỗi transaction cần một connection có ownership rõ ràng.

## 18. TLS, wallet và kết nối Oracle trong môi trường thật

Oracle deployment có thể yêu cầu TLS/TCPS, wallet, certificate hoặc các cơ chế xác thực riêng. Cách cấu hình connection option phụ thuộc driver version và môi trường Oracle.

Trước khi production:

- Xác nhận driver hỗ trợ TLS mode và certificate chain đang dùng.
- Xác nhận wallet/credential được mount và đọc từ secret manager.
- Kiểm tra hostname verification và certificate rotation.
- Không tắt xác minh certificate chỉ để test kết nối.
- Không ghi password hoặc wallet secret vào log.
- Kiểm tra kết nối từ đúng container/VM/runtime giống production.
- Đo thời gian kết nối và behavior khi database failover.

Một connection thành công từ máy developer không chứng minh deployment production có network route, wallet và quyền phù hợp.

## 19. Error code và exception translation

Cùng một lỗi nghiệp vụ có thể có exception subtype, SQLState hoặc vendor code khác nhau giữa Oracle và các driver khác.

Ví dụ:

- Unique constraint violation.
- Foreign key violation.
- Deadlock hoặc lock timeout.
- Serialization conflict.
- Connection lost.
- Invalid SQL.
- Data conversion error.

Spring có thể chuyển lỗi R2DBC thành DataAccessException, nhưng subtype cụ thể phụ thuộc thông tin driver cung cấp và translator của phiên bản Spring.

Không hardcode SQLState của PostgreSQL hoặc vendor code của Oracle trong domain service. Nếu cần phân biệt constraint cụ thể, đặt logic đó trong adapter database-specific và kiểm thử bằng lỗi thật.

Test exception translation bằng cách cố ý vi phạm unique/FK constraint, không chỉ mock DuplicateKeyException.

## 20. Ma trận kiểm tra tính năng trước khi chọn driver

Tạo một ma trận cho các tính năng mà ứng dụng thực sự dùng:

| Nhóm | Kiểm tra | Bằng chứng cần có |
|---|---|---|
| Kết nối | URL, authentication, TLS/wallet, failover | Smoke test trên môi trường gần production |
| Tương thích | Java, SPI, driver, Spring Boot, database version | Dependency matrix/release notes |
| Dialect | Resolver chọn đúng dialect | Integration test và SQL thực tế |
| CRUD | Insert, select, update, delete | Repository test |
| Binding | Positional/named marker, null, số, timestamp | Test bind theo kiểu |
| Pagination | Pageable, sort nhiều cột, offset lớn | Test trang đầu/giữa/cuối |
| Generated key | Identity, sequence, return generated values | Test insert đơn và batch |
| Mapping | NUMBER, DATE, TIMESTAMP, RAW, LOB, JSON | Round-trip test |
| Transaction | Commit, rollback, isolation | Test hai connection |
| Locking | FOR UPDATE, NOWAIT, SKIP LOCKED | Concurrent integration test |
| Savepoint | Nested transaction | Test rollback về savepoint |
| DDL | Migration và implicit commit | Test trên database mới |
| Batch | Add bindings, counts, lỗi giữa batch | Integration test |
| Procedure | IN/OUT, cursor, nhiều result | Test procedure thật |
| Cancellation | Cancel SELECT/INSERT, cleanup | StepVerifier và pool metrics |
| Error translation | Constraint, timeout, lock, network | Assert exception/cause thật |
| Performance | Query plan, pool, throughput, LOB memory | Load test và execution plan |
| Operations | Metrics, tracing, health check, secret rotation | Test deployment-like environment |

Không cần mọi ứng dụng phải hỗ trợ mọi dòng. Đánh dấu N/A nếu tính năng không được dùng; đánh dấu Unknown nếu chưa có bằng chứng. Không đổi Unknown thành Supported chỉ vì compile thành công.

## 21. Bộ smoke test tối thiểu cho Oracle R2DBC

Trước khi viết toàn bộ repository, tạo một module thử nghiệm nhỏ kết nối đúng Oracle version và chạy:

1. Tạo connection và đóng connection.
2. SELECT hằng số hoặc một hàng từ bảng kiểm thử.
3. SELECT có bind parameter.
4. Bind SQL NULL với kiểu Java cụ thể.
5. INSERT, đọc generated ID hoặc sequence.
6. UPDATE và xác nhận rows updated.
7. DELETE và xác nhận constraint.
8. Đọc NUMBER nguyên và thập phân.
9. Round-trip DATE/TIMESTAMP có fractional seconds.
10. Đọc/ghi LOB nếu ứng dụng dùng.
11. Commit và rollback transaction.
12. Kiểm tra isolation/locking bằng hai connection.
13. Chạy pagination query.
14. Hủy publisher và kiểm tra connection pool.
15. Gây unique/FK violation và quan sát exception.
16. Chạy migration từ database mới.

Smoke test nên được tự động hóa trong CI nếu Oracle là database production. Dùng đúng driver, Spring Data version và cấu hình kết nối mà ứng dụng sẽ triển khai.

## 22. Kiểm tra khác biệt với các driver khác

Khi so sánh Oracle với PostgreSQL, MySQL/MariaDB, SQL Server hoặc H2, hãy dùng một bảng câu hỏi thay vì chỉ so tên database:

| Hạng mục | Oracle | PostgreSQL | MySQL/MariaDB | SQL Server | H2 |
|---|---|---|---|---|---|
| Pagination syntax | OFFSET/FETCH ở phiên bản hỗ trợ; có legacy alternatives | LIMIT/OFFSET | LIMIT/OFFSET | OFFSET/FETCH với yêu cầu ORDER BY | Có cú pháp riêng theo compatibility mode |
| Generated IDs | Sequence/identity và driver generated values | Identity/sequence, thường có RETURNING | Auto-increment | Identity/sequence, OUTPUT | Identity/sequence |
| Bind marker | Theo Oracle R2DBC release | Theo PostgreSQL driver | Theo driver | Theo driver | Theo driver |
| JSON/array | Tùy kiểu Oracle và driver | JSONB/array phong phú | JSON và hỗ trợ array khác biệt | JSON/TVP tùy phiên bản | Tùy version |
| Isolation | Default thường READ COMMITTED; SERIALIZABLE | MVCC và các mức riêng | Phụ thuộc engine, thường InnoDB | Các mức và snapshot tùy cấu hình | Không đại diện production engine |
| DDL transaction | Nhiều DDL có implicit commit | Nhiều DDL có thể transactional | Phụ thuộc câu lệnh/engine | Phụ thuộc câu lệnh | Khác production |
| LOB | BLOB/CLOB/NCLOB | Large object/bytea/text | BLOB/TEXT | LOB types | Kiểu tương thích |
| Error codes | Oracle SQL/vendor code | SQLState/vendor code | SQLState/vendor code | SQLState/vendor code | Mã riêng |

Bảng là định hướng để biết nơi cần kiểm tra, không phải bảng chứng nhận tương thích phiên bản. Mỗi driver có release riêng và khả năng khác nhau. Đặc biệt, H2 compatibility mode không làm H2 trở thành Oracle hoặc PostgreSQL thực sự.

## 23. Những sai lầm khi chuyển từ database khác sang Oracle

| Giả định | Rủi ro | Việc cần làm |
|---|---|---|
| LIMIT chạy được trên Oracle | Query lỗi cú pháp | Dùng dialect hoặc SQL Oracle phù hợp phiên bản |
| NUMBER luôn map thành Long | Mất precision hoặc overflow | Chọn Java type theo precision/scale |
| Oracle DATE chỉ có ngày | Mất phần thời gian | Chọn kiểu Java phù hợp |
| Sequence giống auto-increment | Sinh ID sai hoặc query không portable | Kiểm tra sequence/identity và generated key |
| RETURNING giống PostgreSQL | Driver không hỗ trợ cùng cách gọi | Test returnGeneratedValues và cú pháp Oracle |
| Placeholder ? dùng ở mọi driver | Binding lỗi | Dùng bind marker của driver/dialect |
| Mọi dialect hỗ trợ Pageable giống nhau | SQL phân trang sai | Test query sinh ra trên database mục tiêu |
| REPEATABLE_READ luôn có mặt | Driver/database từ chối hoặc ánh xạ khác | Kiểm tra isolation được hỗ trợ |
| DDL rollback như DML | Schema thay đổi dù test rollback | Tách migration khỏi transaction test |
| @Transactional làm mọi raw SQL cùng transaction | Một thao tác dùng connection khác hoặc commit độc lập | Kiểm tra resource binding |
| H2 test pass chứng minh Oracle pass | Khác SQL, type và transaction semantics | Chạy Oracle integration test |
| Exception subtype giống giữa driver | Mapping lỗi nghiệp vụ sai | Assert exception thật trên driver mục tiêu |
| Cancellation đồng nghĩa statement chưa chạy | Ghi có thể đã commit | Thiết kế idempotency và kiểm tra trạng thái |
| Batch tự atomic | Có thể ghi một phần | Dùng transaction nếu cần atomicity |

## 24. Quy trình ra quyết định trước khi sử dụng

Trước khi chọn Oracle R2DBC hoặc đổi sang driver khác, thực hiện theo trình tự:

1. Liệt kê database version, driver version, Spring Boot/Data version và Java version.
2. Đọc compatibility matrix, release notes và tài liệu type mapping của đúng driver.
3. Xác nhận Spring Data dialect được hỗ trợ và resolver chọn đúng dialect.
4. Liệt kê các tính năng persistence thực sự được ứng dụng dùng.
5. Tạo spike nhỏ kiểm tra kết nối, bind, CRUD, generated key và transaction.
6. Kiểm tra các kiểu dữ liệu, LOB, timezone và null quan trọng.
7. Kiểm tra pagination, locking, isolation, savepoint và DDL.
8. Kiểm tra error translation, cancellation, pool và TLS.
9. Chạy integration test trên database/driver thật, không chỉ H2.
10. Đo execution plan, latency, throughput và memory với dữ liệu gần production.
11. Ghi lại tính năng Supported, Unsupported, Workaround hoặc Unknown.
12. Chỉ triển khai khi các tính năng bắt buộc đã có bằng chứng và workaround được chấp nhận.

Một quyết định driver nên lưu lại phiên bản cụ thể, tài liệu tham chiếu, kết quả test và giới hạn đã biết. Khi nâng driver hoặc database, chạy lại ma trận vì behavior có thể thay đổi.

## 25. Ghi nhớ

- R2DBC SPI thống nhất API reactive, không thống nhất mọi cú pháp SQL hoặc tính năng database.
- Cần kiểm tra riêng database engine, R2DBC driver và Spring Data dialect.
- Oracle R2DBC có phiên bản, dependency và khả năng riêng; dùng compatibility matrix của release được chọn.
- Không thay R2DBC URL bằng JDBC URL và không suy luận non-blocking chỉ từ kiểu trả về.
- Oracle pagination, bind marker, sequence, generated values và identifier semantics khác các hệ quản trị khác.
- Oracle NUMBER, DATE, timestamp, LOB và kiểu đặc thù cần round-trip test với Java type thực tế.
- Isolation, savepoint, locking và DDL semantics phải được xác nhận trên Oracle version mục tiêu.
- returnGeneratedValues, batch, procedure, cancellation và metadata là các khả năng cần kiểm tra ở driver.
- Spring Data dialect phải nhận diện đúng Oracle; driver chạy được SQL thủ công chưa đủ chứng minh repository sinh SQL đúng.
- Không dùng H2 compatibility mode làm bằng chứng thay thế integration test với database production.
- Test lỗi constraint và SQLState thật; không giả định exception subtype giống giữa các driver.
- Cancellation hoặc timeout không chứng minh thao tác ghi chưa commit; cần idempotency cho retry.
- Ghi ma trận Supported/Unsupported/Workaround/Unknown theo phiên bản và chạy lại khi nâng cấp.
- Chỉ đưa driver vào production sau khi các tính năng bắt buộc có bằng chứng từ test và thử nghiệm vận hành.

