# Cursor transaction

Trong Spring Batch, cursor reader thường mở một database cursor và giữ nó trong suốt vòng đời của Step để đọc lần lượt các hàng từ ResultSet. Trong khi đó, chunk-oriented Step thường mở một transaction cho mỗi chunk, ghi dữ liệu rồi commit hoặc rollback. Hai vòng đời này liên quan nhưng không nhất thiết dùng cùng một JDBC connection hoặc cùng một transaction.

Điểm cần hiểu rõ là cursor có thể tiếp tục mở qua nhiều lần commit của chunk. Với cấu hình mặc định của JdbcCursorItemReader, cursor thường dùng connection riêng, tách khỏi transaction xử lý chunk. Nếu bật shared extended connection, cursor có thể dùng connection được chia sẻ với transaction của Step và cần driver hỗ trợ giữ cursor qua commit. Lựa chọn này ảnh hưởng đến isolation, khả năng rollback, tài nguyên database và cách reader tiếp tục khi restart.

## 1. Cursor reader và chunk transaction có vòng đời khác nhau

Một cursor reader thực hiện truy vấn và giữ ResultSet mở để lấy từng hàng. Chunk-oriented Step gom các item thành nhóm, xử lý rồi ghi trong transaction.

Ví dụ chunk size là 100:

~~~text
Step bắt đầu
   |
   v
Mở cursor và ResultSet
   |
   v
Đọc 100 item
   |
   v
Processor xử lý
   |
   v
Writer ghi 100 item
   |
   v
Commit transaction của chunk 1
   |
   v
Đọc 100 item tiếp theo từ cursor đang mở
   |
   v
Writer ghi chunk 2
   |
   v
Commit transaction của chunk 2
   |
   v
...
   |
   v
Đóng cursor khi Step kết thúc
~~~

Cursor thường tồn tại lâu hơn một chunk. Transaction của chunk lại bắt đầu và kết thúc nhiều lần trong cùng Step. Nếu nhầm hai vòng đời này thành một, có thể gặp lỗi cursor bị đóng sau commit, giữ transaction quá lâu hoặc hiểu sai dữ liệu mà reader nhìn thấy.

Cần phân biệt:

- **Cursor lifecycle:** mở statement/ResultSet, fetch hàng, đóng resource.
- **Chunk transaction:** bao quanh một nhóm item và các thao tác ghi liên quan.
- **StepExecution lifecycle:** quản lý toàn bộ lần chạy Step, bao gồm reader/writer state và metadata checkpoint.

## 2. Mặc định JdbcCursorItemReader dùng connection riêng

JdbcCursorItemReader thường mở cursor trên một connection riêng, không tham gia transaction đang bao quanh chunk. Connection này được giữ để đọc ResultSet cho đến khi reader đóng.

Trong cấu hình mặc định, useSharedExtendedConnection là false. Do đó:

- Transaction manager điều khiển connection dùng cho các thao tác chunk, chẳng hạn writer JDBC.
- Cursor reader dùng connection khác để giữ ResultSet.
- Commit hoặc rollback của writer không trực tiếp commit/rollback connection cursor.
- Cursor có thể tiếp tục đọc sau khi transaction chunk đã commit.

Mô hình:

~~~text
                    Step
                     |
          +----------+----------+
          |                     |
          v                     v
   Cursor connection      Chunk transaction
          |                     |
          v                     v
   SELECT / ResultSet       INSERT / UPDATE
          |                     |
          |                     v
          |                 COMMIT chunk
          |
          v
    Fetch next row
~~~

Cách tách connection giúp reader giữ cursor mở trong khi transaction ghi được commit theo từng chunk. Nó cũng có nghĩa cursor không tự động nhìn thấy hoặc tham gia mọi thay đổi được thực hiện trong transaction writer.

Không suy luận rằng vì reader và writer dùng cùng một DataSource bean nên chúng chắc chắn dùng cùng JDBC connection. Điều quan trọng là connection thực tế được cấp và cách transaction manager bind connection.

## 3. Vì sao cursor cần tồn tại qua nhiều lần commit?

Một truy vấn cursor có thể trả về hàng triệu bản ghi. Nếu đóng và mở lại truy vấn sau mỗi chunk, database phải thực hiện lại nhiều công việc và reader phải xác định vị trí tiếp tục.

Cursor reader giữ ResultSet để fetch dần. Chunk transaction có thể commit nhiều lần mà reader vẫn tiếp tục trên cursor.

Ví dụ:

~~~text
Cursor query:
  SELECT id, amount
  FROM orders
  WHERE business_date = ?
  ORDER BY id

Chunk 1: id 1..100       -> commit
Chunk 2: id 101..200     -> commit
Chunk 3: id 201..300     -> commit
...
Chunk N: id cuối         -> commit
~~~

Việc commit mỗi chunk giúp giới hạn thời gian transaction ghi và lượng dữ liệu cần rollback. Cursor vẫn mở để đọc phần còn lại.

Tuy nhiên, một cursor mở lâu cũng giữ connection và tài nguyên database lâu. Tùy database, nó có thể giữ snapshot, giữ phiên transaction hoặc làm tăng áp lực lên undo/version storage. Cần cân bằng lợi ích streaming với thời gian giữ resource.

## 4. Shared extended connection là gì?

JdbcCursorItemReader có tùy chọn dùng shared extended connection. Khi bật, cursor connection được chia sẻ với các thao tác khác trong Step thông qua ExtendedConnectionDataSourceProxy.

Mục tiêu là dùng chung connection theo cách cho phép cursor tồn tại qua các lần commit của chunk. Driver database phải hỗ trợ cursor holdability qua commit, thường liên quan đến HOLD_CURSORS_OVER_COMMIT.

Cấu hình khái quát:

~~~text
Transaction manager
        |
        v
Physical JDBC connection
        ^
        |
ExtendedConnectionDataSourceProxy
        |
        +--> JdbcCursorItemReader
        |
        +--> các thao tác JDBC trong Step
~~~

Trong chế độ này, connection được giữ mở qua commit của chunk để ResultSet/cursor không bị đóng. Cấu hình cần đúng cả proxy lẫn thuộc tính reader; chỉ bật cờ shared connection mà dùng DataSource thông thường sẽ không đáp ứng yêu cầu của cơ chế này.

Không bật shared connection chỉ vì muốn reader và writer "cùng transaction". Hãy xác định rõ mục tiêu: giữ cursor qua commit, dùng cùng connection, hay cần một isolation boundary cụ thể. Shared connection có các điều kiện và trade-off riêng.

## 5. Cấu hình ExtendedConnectionDataSourceProxy

Để sử dụng shared extended connection, tạo proxy bọc DataSource gốc và cấu hình reader dùng proxy đó.

Ví dụ cấu hình:

~~~java
@Bean
ExtendedConnectionDataSourceProxy extendedDataSource(
        DataSource dataSource) {
    return new ExtendedConnectionDataSourceProxy(dataSource);
}
~~~

Khai báo reader:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Order> orderCursorReader(
        ExtendedConnectionDataSourceProxy extendedDataSource) {

    JdbcCursorItemReader<Order> reader =
            new JdbcCursorItemReader<>();

    reader.setName("orderCursorReader");
    reader.setDataSource(extendedDataSource);
    reader.setSql("""
            select id, customer_id, amount
            from orders
            where business_date = ?
            order by id
            """);
    reader.setRowMapper((rs, rowNum) -> new Order(
            rs.getLong("id"),
            rs.getLong("customer_id"),
            rs.getBigDecimal("amount")));
    reader.setUseSharedExtendedConnection(true);
    reader.setFetchSize(500);
    reader.setSaveState(true);

    return reader;
}
~~~

ExtendedConnectionDataSourceProxy phải bọc DataSource được dùng bởi transaction manager của Step. Transaction manager và reader phải tham chiếu đến cùng nguồn connection cơ sở theo cấu hình của ứng dụng.

Các import, bean wiring và cách cấu hình transaction manager phụ thuộc phiên bản Spring và cách ứng dụng khai báo DataSource. Không tạo hai pool độc lập rồi kỳ vọng proxy có thể chia sẻ physical connection giữa chúng.

## 6. Driver phải hỗ trợ HOLD_CURSORS_OVER_COMMIT

Khi shared extended connection được bật, cursor phải sống qua commit của chunk. Điều này đòi hỏi JDBC driver và database hỗ trợ giữ cursor qua commit.

JDBC có holdability:

- CLOSE_CURSORS_AT_COMMIT: cursor bị đóng khi transaction commit.
- HOLD_CURSORS_OVER_COMMIT: cursor được giữ mở qua commit.

JdbcCursorItemReader dùng shared extended connection cần khả năng hold cursor qua commit. Driver có thể xử lý khác nhau theo database, cursor type và cách tạo statement.

Không giả định mọi database đều hỗ trợ cùng hành vi. Trước khi bật shared connection, kiểm tra:
- Database engine và version.
- JDBC driver version.
- Cursor type/holdability mà driver thực sự cấp.
- Cách transaction manager commit connection.
- Cách driver xử lý ResultSet sau commit.
- Hành vi khi rollback hoặc reconnect.

Nếu driver không hỗ trợ holdability cần thiết, reader có thể gặp lỗi khi commit, cursor bị đóng hoặc việc đọc tiếp không còn hợp lệ. Khi đó, dùng cấu hình cursor connection riêng mặc định hoặc chọn reader/pattern khác phù hợp hơn.

## 7. Transaction manager và DataSource phải khớp

Chunk transaction được điều khiển bởi PlatformTransactionManager. Với JDBC, transaction manager thường được cấu hình trên DataSource tương ứng.

Ví dụ:

~~~java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

Trong cấu hình shared extended connection, ExtendedConnectionDataSourceProxy cần bọc chính DataSource mà transaction manager sử dụng. Proxy giúp reader lấy connection mở rộng được quản lý cùng lifecycle transaction.

Nếu transaction manager dùng DataSource A nhưng reader dùng DataSource B hoặc một pool khác, hai bên không chia sẻ connection như mong muốn. Dù URL database giống nhau, hai connection vật lý vẫn là hai session độc lập.

Với nhiều DataSource, cần xác định rõ reader đọc từ database nào và writer ghi vào database nào. Một transaction manager JDBC thông thường không tự tạo transaction phân tán nguyên tử giữa hai DataSource.

## 8. Chunk commit không đồng nghĩa cursor query được chạy lại

Khi một chunk commit, writer transaction kết thúc. Cursor reader vẫn tiếp tục đọc từ ResultSet hiện tại nếu connection/driver giữ cursor hợp lệ.

Ví dụ:

~~~text
Cursor mở một lần:
  SELECT ... ORDER BY id

Chunk transaction:
  begin -> write chunk 1 -> commit
  begin -> write chunk 2 -> commit
  begin -> write chunk 3 -> commit

Cursor:
  fetch rows 1..100
  fetch rows 101..200
  fetch rows 201..300
  close khi Step kết thúc
~~~

Vì cursor không được tạo lại sau mỗi chunk, reader không phải thực hiện lại toàn bộ truy vấn ở mỗi lần commit. Tuy nhiên, dữ liệu mà cursor trả về được xác định theo semantics của database, transaction isolation và cách driver thực thi cursor.

Không mặc định cursor luôn phản ánh dữ liệu mới nhất sau mỗi chunk. Nhiều database xác định tập kết quả tại thời điểm mở truy vấn hoặc theo snapshot/transaction cụ thể. Hành vi chính xác cần dựa vào database và isolation level.

## 9. Isolation level và tính nhất quán dữ liệu

Transaction isolation ảnh hưởng việc reader nhìn thấy dữ liệu nào trong khi Job đang chạy. Cần phân biệt isolation của cursor connection với isolation của chunk transaction khi chúng là hai connection riêng.

Một số mức isolation phổ biến:

| Isolation | Hành vi khái quát | Điều cần chú ý với cursor |
|---|---|---|
| READ_UNCOMMITTED | Có thể đọc dữ liệu chưa commit nếu database hỗ trợ | Có nguy cơ dirty read |
| READ_COMMITTED | Chỉ đọc dữ liệu đã commit tại thời điểm đọc theo semantics database | Các lần đọc có thể thấy thay đổi mới tùy cursor/database |
| REPEATABLE_READ | Giữ tính nhất quán mạnh hơn trong transaction | Có thể giữ version/lock lâu hơn |
| SERIALIZABLE | Mức cô lập cao, có thể hạn chế concurrency | Dễ phát sinh blocking hoặc serialization failure |

Các mức isolation được hiện thực khác nhau giữa database. Một cursor query duy nhất không nhất thiết có cùng hành vi snapshot trên mọi engine. Ví dụ, một số database dùng MVCC và giữ snapshot của câu SELECT; một số cơ chế cursor yêu cầu transaction mở lâu; một số driver có thể fetch theo lô.

Nếu cần một tập dữ liệu bất biến cho toàn Job, cân nhắc:
- Chạy query trên snapshot hoặc staging table.
- Dùng watermark cố định được xác định trước khi đọc.
- Dùng business date hoặc batch ID cố định trong WHERE.
- Dùng khóa sắp xếp ổn định và duy nhất.
- Chọn isolation level phù hợp sau khi đo tác động lên database.

Không tăng isolation lên SERIALIZABLE theo mặc định chỉ để "an toàn". Transaction dài và cursor mở lâu có thể làm giảm concurrency hoặc tạo lock contention.

## 10. Cursor connection riêng và thay đổi dữ liệu nguồn

Với cấu hình mặc định, cursor reader và writer chunk có thể dùng hai connection riêng. Điều này có ý nghĩa khi Step vừa đọc vừa cập nhật cùng database.

Ví dụ reader đọc hàng có status NEW, writer đổi status thành PROCESSED. Nếu cursor query được mở trước và database xác định result set theo snapshot, reader có thể tiếp tục nhìn thấy những hàng thuộc tập ban đầu. Nhưng hành vi cụ thể phụ thuộc database, isolation và cursor implementation.

Các câu hỏi cần trả lời trước khi triển khai:

- Có transaction khác thêm hàng mới phù hợp với query trong lúc Job chạy không?
- Hàng đã đọc có thể bị cập nhật hoặc xóa bởi process khác không?
- Writer có cập nhật chính bảng reader đang đọc không?
- Cursor giữ snapshot từ lúc execute query hay fetch theo semantics khác?
- Nếu Job restart, dữ liệu nguồn có còn cùng version không?
- Có thể dùng batch ID hoặc watermark để cố định tập dữ liệu không?

Nếu Job cần xử lý chính xác một batch đầu vào, thường nên có điều kiện lọc ổn định, ví dụ batch_id = ?, hoặc tạo snapshot/staging set trước khi bắt đầu cursor. Không phụ thuộc vào việc cursor tự động tạo ra snapshot nghiệp vụ mà không kiểm tra database.

## 11. Commit và rollback của chunk ảnh hưởng reader thế nào?

Khi writer ném exception, transaction chunk có thể rollback. Rollback hoàn tác các thay đổi transactional trong chunk, nhưng không có nghĩa JDBC cursor tự quay về vị trí trước khi đọc item.

Cursor là một ResultSet đang được tiến về phía trước. Vị trí đọc trong bộ nhớ và checkpoint được lưu trong ExecutionContext là hai thứ khác nhau.

Spring Batch quản lý việc khôi phục item theo chunk processing và fault-tolerance semantics. Với một số reader, framework có thể buffer item để trình bày lại sau rollback; khi restart, reader khôi phục từ checkpoint đã commit. Không tự viết logic giả định rằng JDBC rollback sẽ đưa cursor về hàng đầu chunk.

Một mô hình khái quát:

~~~text
Checkpoint đã commit tại item 200
          |
          v
Đọc item 201..300
          |
          v
Writer lỗi -> rollback chunk
          |
          v
Step xử lý lại theo retry/recovery policy
          |
          v
Nếu process dừng và restart:
  mở cursor mới
  khôi phục từ checkpoint bền vững
  tiếp tục sau điểm commit đã lưu
~~~

Checkpoint thường được cập nhật cùng ranh giới commit của chunk. Vì vậy, nếu process dừng sau chunk đã commit, restart có thể bắt đầu từ checkpoint cuối. Nếu có tác động ngoài transaction, như ghi file hoặc gọi HTTP, cần idempotency hoặc đối soát để tránh side effect trùng.

## 12. Checkpoint và restart của JdbcCursorItemReader

JdbcCursorItemReader có thể lưu state đọc trong Step ExecutionContext. Khi restart, reader mở lại truy vấn và khôi phục vị trí đọc theo checkpoint đã lưu.

Để restart đáng tin cậy:

- Đặt tên reader ổn định bằng setName hoặc builder name.
- Bật saveState(true) nếu cần checkpoint.
- Dùng ORDER BY với khóa xác định và duy nhất.
- Giữ nguyên query và các tham số có ảnh hưởng tới tập kết quả.
- Bảo đảm dữ liệu nguồn không thay đổi theo cách làm checkpoint cũ mất ý nghĩa.
- Không đổi reader name hoặc cấu trúc state giữa các lần triển khai đang cần restart.

Một số cursor reader khôi phục bằng cách di chuyển tới item đã đọc trước đó; điều này có thể yêu cầu đọc/bỏ qua các hàng từ đầu truy vấn. Với tập dữ liệu lớn, thời gian restart có thể tăng theo vị trí checkpoint. Driver hỗ trợ absolute positioning có thể giúp tối ưu trong những trường hợp phù hợp, nhưng phải kiểm tra semantics và khả năng của driver.

Không dùng checkpoint row number nếu thứ tự kết quả không ổn định. Luôn có ORDER BY phù hợp, tốt nhất dựa trên khóa duy nhất. Nếu nhiều hàng có cùng giá trị sort, thứ tự giữa chúng có thể không xác định.

## 13. Fetch size và cursor transaction

Fetch size là gợi ý cho JDBC driver về số hàng nên lấy mỗi lần từ database. Nó có thể ảnh hưởng số lần round trip, bộ nhớ phía client và thời gian giữ cursor.

Ví dụ:

~~~java
reader.setFetchSize(500);
~~~

Fetch size không phải chunk size:

- Chunk size quyết định số item được xử lý/ghi trong một transaction.
- Fetch size là gợi ý về số hàng driver fetch từ database trong một lần.
- Hai giá trị có thể khác nhau.

Ví dụ chunk size 100 và fetch size 500: driver có thể lấy trước một nhóm hàng lớn hơn một chunk, trong khi Step vẫn commit sau mỗi 100 item. Điều này có thể giảm round trip nhưng cũng làm tăng dữ liệu đệm và có thể ảnh hưởng bộ nhớ.

Một số driver chỉ thực sự streaming khi fetch size được đặt và connection ở trạng thái transaction phù hợp. PostgreSQL JDBC chẳng hạn có điều kiện riêng liên quan auto-commit và fetch size. Không giả định setFetchSize là đủ để đảm bảo server-side cursor trên mọi driver.

Đo thực tế với database/driver production-like và chọn giá trị dựa trên throughput, heap usage và thời gian giữ connection.

## 14. Query timeout, max rows và tài nguyên cursor

Cursor mở lâu tiêu thụ tài nguyên database. Có thể cấu hình thêm các giới hạn phù hợp:

- Fetch size để điều chỉnh batch fetch.
- Query timeout để giới hạn thời gian thực thi câu truy vấn ban đầu.
- Max rows nếu chỉ cần xử lý một tập có giới hạn.
- Driver-specific properties để điều chỉnh cursor hoặc streaming.
- Connection pool size đủ cho cursor connection và chunk connection.
- Timeout/monitoring cho Job và Step.

Query timeout thường giới hạn thời gian thực thi câu SQL, không nhất thiết là giới hạn toàn bộ thời gian cursor được mở và đọc. Sau khi query thực thi, việc fetch hàng có thể kéo dài; cần hiểu cách driver áp dụng timeout.

Không giữ cursor mở vô hạn khi Job bị treo. Cần có giới hạn thời gian cho Job, xử lý stop/shutdown có kiểm soát và đảm bảo reader close resource khi Step kết thúc.

## 15. Cursor connection riêng ảnh hưởng connection pool

Khi dùng cursor connection riêng, một Step có thể cần ít nhất một connection cho reader và một connection cho chunk transaction nếu writer cũng truy cập database qua transaction manager.

Nếu chạy nhiều Job hoặc partition song song, số connection tăng lên:

~~~text
4 worker partition
  |
  +--> 4 cursor connections
  |
  +--> 4 chunk transaction connections
  |
  +--> các connection cho service khác
~~~

Đây là mô hình minh họa; số connection thực tế phụ thuộc reader/writer và transaction resource. Nhưng cần tính connection pool theo concurrency, không chỉ theo số Step.

Nếu pool quá nhỏ, reader có thể giữ connection cursor trong khi writer chờ connection khác, gây cạn pool hoặc starvation. Với shared extended connection, một connection được dùng chung theo cấu hình, nhưng có thể tăng contention hoặc giới hạn throughput.

Theo dõi active/idle/pending connections, connection acquisition time và thời gian cursor mở. Đừng chỉ tăng pool size mà không kiểm tra giới hạn connection của database.

## 16. Cursor và cập nhật chính bảng đang đọc

Một tình huống phổ biến là đọc các hàng cần xử lý rồi writer cập nhật trạng thái của chính các hàng đó.

Ví dụ:

~~~sql
SELECT id, status
FROM orders
WHERE status = 'NEW'
ORDER BY id
~~~

Writer cập nhật status thành PROCESSED.

Cần xác định cursor query có tiếp tục trả các hàng theo result set ban đầu hay bị ảnh hưởng bởi cập nhật, tùy database/driver. Nếu reader và writer dùng hai connection, writer commit không nhất thiết thay đổi result set đã mở. Nếu dùng shared connection, semantics có thể khác và cần kiểm thử.

Một thiết kế ổn định hơn là xác định tập đầu vào trước khi xử lý:
- Gán batch ID cho các hàng được chọn.
- Chụp danh sách ID vào staging table.
- Dùng watermark cố định và khóa sắp xếp duy nhất.
- Chuyển hàng sang trạng thái IN_PROGRESS bằng một transaction/claim strategy rõ ràng.

Không để nhiều Job đồng thời cùng chọn và xử lý các hàng NEW mà không có cơ chế claim hoặc khóa phù hợp. Cursor transaction không tự giải quyết tranh chấp giữa các Job.

## 17. So sánh cursor connection riêng và shared extended connection

| Tiêu chí | Connection riêng (mặc định) | Shared extended connection |
|---|---|---|
| Connection reader | Riêng với transaction chunk | Chia sẻ qua proxy với connection transaction |
| Cursor qua chunk commit | Được giữ trên connection reader riêng | Cần holdability qua commit |
| DataSource | DataSource bình thường có thể dùng | Cần ExtendedConnectionDataSourceProxy |
| Yêu cầu driver | Phụ thuộc cursor thông thường | Cần hỗ trợ HOLD_CURSORS_OVER_COMMIT |
| Isolation | Cursor và writer có thể ở session/transaction khác nhau | Cùng connection nên semantics khác |
| Connection pool | Có thể cần thêm connection cho cursor | Có thể giảm connection riêng nhưng giữ connection lâu |
| Phù hợp | Cấu hình mặc định, reader/writer độc lập | Khi cần shared connection và driver hỗ trợ rõ ràng |

Không có lựa chọn tốt nhất cho mọi database. Dùng connection riêng nếu không có lý do cụ thể để chia sẻ và driver không hỗ trợ holdability. Dùng shared extended connection khi cần semantics đó, driver hỗ trợ và đã kiểm thử với transaction manager thực tế.

## 18. Khi nào nên dùng JdbcCursorItemReader?

Cursor reader thường phù hợp khi:
- Cần đọc tuần tự một tập dữ liệu lớn.
- Query có thể trả ResultSet ổn định.
- Database và driver hỗ trợ cursor/streaming phù hợp.
- Có thể giữ connection mở trong thời gian Step chạy.
- Thứ tự dữ liệu và chiến lược restart được xác định rõ.

Cần cân nhắc giải pháp khác khi:
- Connection bị giới hạn hoặc Job chạy rất lâu.
- Cursor giữ snapshot/lock gây áp lực lớn.
- Dữ liệu nguồn thay đổi liên tục và cần xác định tập input chính xác.
- Restart từ đầu query quá tốn kém.
- Driver không hỗ trợ cursor behavior cần thiết.

JdbcPagingItemReader là lựa chọn thay thế thường gặp. Nó đọc theo từng page thay vì giữ một ResultSet cursor mở xuyên suốt. Tuy nhiên, paging cũng cần sort key ổn định và chiến lược tránh bỏ sót/trùng khi dữ liệu nguồn thay đổi. Chọn reader theo semantics dữ liệu, không chỉ theo benchmark tốc độ.

## 19. Kiểm thử cursor transaction

Kiểm thử với H2 hoặc mock có thể giúp xác nhận cấu hình cơ bản, nhưng không chứng minh đầy đủ cursor holdability của database production. Cần integration test trên database và JDBC driver gần với môi trường thật.

Các kịch bản quan trọng:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Đọc qua nhiều chunk | Cursor tiếp tục sau mỗi chunk commit |
| Writer commit | ResultSet vẫn đọc được item tiếp theo |
| Writer rollback | Chunk được phục hồi theo retry/restart semantics |
| Shared connection bật | Driver giữ cursor qua commit |
| Driver không hỗ trợ holdability | Lỗi được phát hiện rõ khi khởi chạy/test |
| Job restart | Reader khôi phục từ checkpoint cuối đã commit |
| Source thay đổi khi Job chạy | Hành vi nhất quán theo isolation đã chọn |
| Writer cập nhật bảng nguồn | Không mất hoặc lặp hàng ngoài chủ đích |
| Nhiều Job đồng thời | Connection pool và lock behavior chấp nhận được |
| Step bị stop | Cursor và connection được đóng đúng lifecycle |
| Query timeout | Job kết thúc theo chính sách timeout |
| Fetch size thay đổi | Throughput và memory được đo, không suy đoán |

Một integration test restart hữu ích:
1. Chạy Step với chunk size nhỏ.
2. Cho writer cố ý lỗi sau một số chunk đã commit.
3. Xác nhận StepExecution lưu checkpoint.
4. Restart cùng JobInstance.
5. Xác nhận reader tiếp tục đúng vị trí và output không trùng/thiếu.
6. Chạy lại với shared extended connection nếu ứng dụng dùng chế độ đó.

Cũng cần quan sát connection được cấp, cursor được mở/đóng và trạng thái transaction. Không dùng chỉ số read count cuối để kết luận driver đã giữ cursor đúng qua commit.

## 20. Lỗi thường gặp khi làm việc với cursor transaction

**Nghĩ rằng cursor connection mặc định tham gia transaction chunk.** Mặc định JdbcCursorItemReader thường dùng connection riêng; commit writer không điều khiển connection đó.

**Bật shared connection nhưng không dùng ExtendedConnectionDataSourceProxy.** Reader không có cơ chế connection mở rộng cần thiết.

**Driver không hỗ trợ hold cursor qua commit.** ResultSet có thể bị đóng hoặc đọc tiếp thất bại.

**Nhầm fetch size với chunk size.** Hai tham số điều khiển hai tầng khác nhau.

**Cho rằng rollback đưa cursor về đầu chunk.** Cursor position và checkpoint transaction là hai cơ chế khác nhau.

**Query không có ORDER BY ổn định.** Restart có thể bỏ sót hoặc đọc trùng khi thứ tự thay đổi.

**Dùng cursor cho Job chạy quá lâu mà không tính tài nguyên.** Connection và database cursor có thể bị giữ nhiều giờ.

**Không tính connection pool cho reader và writer.** Nhiều worker có thể làm cạn pool.

**Không hiểu isolation của database.** Reader có thể nhìn thấy tập dữ liệu khác kỳ vọng khi source thay đổi.

**Dùng shared connection chỉ để tránh thêm connection.** Có thể tăng contention và yêu cầu driver-specific behavior.

**Cho nhiều Job cùng đọc/cập nhật một tập hàng mà không claim dữ liệu.** Cursor không thay thế cơ chế điều phối và khóa nghiệp vụ.

## 21. Quy trình chọn cursor transaction phù hợp

Khi dùng JdbcCursorItemReader, hãy thực hiện theo trình tự:

1. Xác định cursor có cần dùng chung connection với transaction của Step hay không.
2. Bắt đầu với cấu hình mặc định dùng cursor connection riêng nếu không có yêu cầu khác.
3. Nếu bật shared extended connection, bọc DataSource bằng ExtendedConnectionDataSourceProxy và bật useSharedExtendedConnection.
4. Xác nhận proxy bọc đúng DataSource mà transaction manager sử dụng.
5. Kiểm tra database/driver hỗ trợ HOLD_CURSORS_OVER_COMMIT.
6. Chọn isolation level và chiến lược snapshot/watermark phù hợp với yêu cầu dữ liệu.
7. Dùng ORDER BY ổn định, tốt nhất có khóa duy nhất.
8. Cấu hình fetch size, query timeout và connection pool theo đo đạc thực tế.
9. Bật saveState và giữ reader name/query/input ổn định nếu cần restart.
10. Kiểm thử commit, rollback, restart, source mutation và stop trên database thật.
11. Theo dõi thời gian giữ cursor, connection pool, lock/version storage và throughput.

Cursor transaction là mối quan hệ giữa ResultSet được giữ mở và các transaction chunk diễn ra trong Step. Cấu hình mặc định tách cursor connection khỏi transaction chunk; shared extended connection cho phép chia sẻ connection qua commit khi proxy và driver hỗ trợ. Khi chọn đúng mô hình, kiểm soát isolation, ổn định query và kiểm thử restart trên database thực tế, cursor reader có thể đọc dữ liệu lớn theo luồng mà vẫn giữ transaction ghi ở ranh giới chunk rõ ràng.

