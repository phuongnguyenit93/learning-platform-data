# SQL command recording

SQL command recording là việc ghi nhận các câu lệnh SQL và ngữ cảnh thực thi cần thiết để truy vết hoạt động trong cơ sở dữ liệu. Trong Privileged Access Management (PAM), mục tiêu không chỉ là lưu nội dung người dùng đã gõ, mà là nối được người hoặc workload, quyền được cấp, phiên kết nối, lệnh đã gửi và kết quả quan sát được.

Một bản ghi SQL không tự chứng minh thay đổi đã commit. Một video màn hình không tự chứng minh database đã nhận lệnh. Một thống kê truy vấn tổng hợp cũng không phải lịch sử đầy đủ của từng lần thực thi. Thiết kế recording cần mô tả rõ từng loại bằng chứng và giới hạn của nó.

Bài học dùng PostgreSQL 18 để minh họa một số điểm kỹ thuật về protocol và logging. Kiến trúc chuẩn hóa, policy PAM và sự kiện JSON trong bài là mô hình đề xuất, không phải cấu hình có thể áp dụng nguyên trạng cho mọi database hoặc sản phẩm PAM.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt SQL command recording với ghi hình terminal, query statistics và transaction recovery log.
- Xác định trường dữ liệu cần thu để gắn lệnh với danh tính, grant và phiên.
- Phân biệt lệnh được gửi, được thực thi, báo thành công và thay đổi đã commit.
- Xử lý prepared statement, bind parameter, batch và lệnh chạy trong procedure.
- Thiết kế che dữ liệu nhạy cảm mà không tạo kết luận sai về độ đầy đủ.
- Kiểm soát đường kết nối bỏ qua recorder.
- Xây dựng phép thử về độ bao phủ, toàn vẹn và khả năng truy xuất bằng chứng.

## 2. Cần ghi “lệnh” ở thời điểm nào?

### 2.1. Chuỗi sự kiện của một thao tác

~~~text
Người hoặc workload tạo yêu cầu
              |
              v
Client chuẩn bị câu lệnh
              |
              v
Gateway hoặc driver gửi tới database
              |
              v
Database phân tích, kiểm tra quyền và thực thi
              |
              v
Client nhận kết quả hoặc lỗi
              |
              v
Transaction commit, rollback hoặc chưa xác định
~~~

Một thiết kế có thể quan sát được một số hoặc tất cả các bước. Cần nói chính xác nguồn nào ghi sự kiện ở bước nào.

Ví dụ, lịch sử trong SQL editor có thể chứa câu lệnh đã soạn nhưng chưa chạy. Ngược lại, câu lệnh do driver hoặc script sinh ra có thể được thực thi mà không từng xuất hiện trên màn hình.

### 2.2. Những câu hỏi khác nhau

| Câu hỏi | Bằng chứng thường cần |
| --- | --- |
| Người dùng đã định làm gì? | Yêu cầu, runbook và nội dung client khi có |
| Database đã nhận lệnh nào? | Recorder hiểu protocol hoặc log engine phù hợp |
| Lệnh bị từ chối vì quyền không? | Lỗi và audit ở điểm kiểm tra liên quan |
| Lệnh đã hoàn tất chưa? | Sự kiện hoàn tất hoặc phản hồi của engine |
| Dữ liệu đã commit chưa? | Ngữ cảnh transaction và bằng chứng kết thúc phù hợp |
| Người dùng đã nhận dữ liệu gì? | Quan sát kết quả nếu được thiết kế và cho phép |
| Ai đứng sau tài khoản dùng chung? | Log xác thực, grant và mapping phiên ngoài database |
| Có đường không được ghi không? | Inventory và kiểm thử độ bao phủ |

Không dùng một nguồn bằng chứng trả lời vượt câu hỏi mà nguồn đó có thể chứng minh.

### 2.3. Recording là kiểm soát phát hiện và điều tra

Chỉ ghi lệnh không tự ngăn lệnh trái phép. Nếu cần chặn theo policy, phải có điểm thực thi riêng và kiểm tra khả năng của điểm đó.

Một hệ thống có thể vừa ghi vừa kiểm soát lệnh, nhưng hai chức năng cần nghiệm thu độc lập:

- Lệnh ngoài quyền có bị chặn không?
- Lệnh được gửi hoặc bị chặn có được ghi đúng không?
- Khi recorder lỗi, hệ thống phản ứng thế nào?

Không lấy việc có log làm bằng chứng rằng mọi hành động đã được cho phép đúng.

## 3. Phân biệt các cách ghi nhận

### 3.1. Bảng so sánh

| Nguồn | Có ích cho | Giới hạn cần biết |
| --- | --- | --- |
| SQL editor history | Nội dung được soạn hoặc chạy qua một client | Có thể sửa, xóa, thiếu script và công cụ khác |
| Terminal hoặc video recording | Ngữ cảnh tương tác của người dùng | Không đảm bảo thấy mọi SQL do driver gửi |
| Gateway hiểu protocol | Câu lệnh và thông tin protocol mà gateway xử lý | Không thấy đường bypass hoặc nội dung ngoài khả năng giải mã |
| Native database logging | Những hoạt động engine ghi theo cấu hình | Phụ thuộc loại log, mức ghi và quyền thay cấu hình |
| Audit extension hoặc tính năng audit | Hành động và đối tượng theo khả năng sản phẩm | Phải kiểm tra phiên bản, loại sự kiện và overhead |
| Query statistics | Tần suất, thời gian và hành vi tổng hợp | Không phải từng lần thực thi theo timeline |
| Cơ chế phục hồi hoặc thay đổi dữ liệu | Khôi phục và phân tích trạng thái theo khả năng | Không mặc định có danh tính người thật và mọi lần đọc dữ liệu |

Một kiến trúc thường cần nhiều nguồn. Không cần ghi trùng mọi nội dung ở mọi nơi, nhưng phải xác định nguồn chuẩn cho từng câu hỏi.

### 3.2. Query statistics không thay thế audit theo phiên

PostgreSQL pg_stat_statements lưu thống kê theo các tổ hợp như database, user và query identifier, với nội dung truy vấn đại diện. Nó không phải chuỗi bản ghi cho từng lần chạy theo phiên PAM. [pg_stat_statements](https://www.postgresql.org/docs/18/pgstatstatements.html).

Có thể dùng thống kê hỗ trợ điều tra hiệu năng hoặc đối chiếu xu hướng, nhưng không suy ra người cụ thể đã chạy một lệnh vào một thời điểm chỉ từ số đếm tổng hợp.

### 3.3. Recording màn hình không phải SQL protocol recording

Một công cụ GUI có thể:

- Gửi truy vấn metadata tự động.
- Chạy nhiều statement từ một thao tác.
- Dùng prepared statement.
- Gửi lệnh từ một tác vụ nền.
- Retry khi mất kết nối.
- Thực hiện commit tự động theo cấu hình.

Video có thể chỉ hiển thị một nút bấm hoặc nội dung rút gọn. Ngược lại, video có thể chứa dữ liệu nhạy cảm không cần lưu cho mục tiêu audit.

Cần chọn loại recording theo bằng chứng cần có, thay vì coi càng nhiều hình ảnh là càng đầy đủ.

## 4. Xác định phạm vi recording trong Database PAM

### 4.1. Danh tính và loại công việc

Phạm vi có thể gồm:

- DBA tác nghiệp.
- Phiên superuser hoặc quyền tương đương.
- Hỗ trợ production.
- Migration.
- Job sửa dữ liệu.
- Công cụ điều tra.
- Automation quản lý tài khoản.
- Phiên break-glass.

Không bỏ workload chỉ vì nó không có màn hình. Một job có quyền mạnh có thể thực hiện nhiều lệnh hơn một phiên người dùng.

### 4.2. Nhóm hành động

| Nhóm | Ví dụ | Lý do cần theo dõi |
| --- | --- | --- |
| DDL | Tạo, sửa, xóa cấu trúc | Ảnh hưởng mô hình và khả năng truy cập dữ liệu |
| DML | Chèn, sửa, xóa | Ảnh hưởng trạng thái nghiệp vụ |
| Đọc dữ liệu | SELECT hoặc cơ chế xuất phù hợp | Có thể làm lộ dữ liệu nhạy cảm |
| Quản trị quyền | Tạo role, cấp quyền, đổi membership | Có thể tạo đường duy trì hoặc mở rộng quyền |
| Quản trị phiên | Đổi ngữ cảnh, hủy tác vụ | Ảnh hưởng trách nhiệm và tính sẵn sàng |
| Cấu hình | Thay logging, audit hoặc tham số | Có thể làm suy yếu kiểm soát |
| Procedure và function | Gọi logic trong engine | Tác động có thể không thể hiện hết trong lệnh ngoài cùng |
| Transaction | Commit, rollback, savepoint khi liên quan | Cần cho diễn giải kết quả thay đổi |

Danh mục phải được ánh xạ theo engine. Không dùng danh sách từ khóa SQL chung như thể nó bao phủ mọi dialect và mọi loại thao tác.

### 4.3. Phạm vi phải chỉ rõ cả thành công và lỗi

Một lần thử bị từ chối vẫn có thể quan trọng: thử đọc bảng ngoài quyền, tạo principal hoặc tắt audit.

Tuy nhiên, lỗi có thể xảy ra ở client, gateway, bước parse, bước kiểm tra quyền hoặc khi thực thi. Không phải mọi nguồn đều ghi mọi lỗi ở mọi lớp.

Thiết kế cần nêu mỗi loại lỗi mong muốn được thu từ đâu. Đừng chỉ thử một lệnh thành công rồi báo recording đầy đủ.

## 5. Kiến trúc recording tham khảo

### 5.1. Chuỗi xử lý

~~~text
Người / workload
       |
       v
PAM: xác thực, grant và cấp kết nối
       |
       v
Gateway hiểu database protocol
       |
       v
Database engine và audit nội bộ
       |
       +-------------------------------+
                                       |
PAM events + gateway events + DB logs  |
                    |                  |
                    v                  |
          Thu thập và tương quan <-----+
                    |
          +---------+----------+
          |                    |
          v                    v
   Kho bằng chứng gốc     Bản chuẩn hóa
   được phép lưu          và bản che dữ liệu
          |                    |
          +---------+----------+
                    v
          Rà soát và điều tra
~~~

Các thành phần có thể khác nhau tùy sản phẩm. Điều cần giữ là trách nhiệm rõ cho cấp quyền, quan sát, bảo vệ và diễn giải bằng chứng.

### 5.2. Mã hóa đường truyền

Nếu kết nối được mã hóa, một thiết bị chỉ nhìn packet trên mạng không tự thấy nội dung SQL.

Để quan sát SQL, hệ thống cần điểm tích hợp phù hợp, chẳng hạn gateway kết thúc và thiết lập lại kết nối theo kiến trúc đã phê duyệt, hoặc audit phía engine. Không tắt mã hóa như một cách mặc định để tiện recording.

Cần xác minh:

- Client tin đúng endpoint.
- Gateway xác thực đúng database đích.
- Credential không bị lộ.
- Luồng client–gateway và gateway–database được bảo vệ theo thiết kế.
- Cơ chế certificate và rotation hoạt động.

### 5.3. Đường bypass

Nếu chỉ các phiên qua gateway được ghi, cần kiểm kê:

- Endpoint trực tiếp.
- Kết nối local hoặc socket.
- Công cụ quản trị khác.
- Pipeline.
- Tài khoản kỹ thuật.
- Replication hoặc cơ chế đặc biệt khi nằm trong phạm vi.
- Đường từ máy chủ ứng dụng.
- Đường khẩn cấp.

Một người có password quản trị và quyền mạng trực tiếp có thể không cần đi qua recorder. Bảo đảm “mọi phiên đặc quyền được ghi” phải được chứng minh trên các đường thực tế.

### 5.4. Native audit và gateway bổ sung cho nhau

Gateway có thể biết người xin quyền và phiên PAM. Engine có thể biết thêm ngữ cảnh thực thi bên trong.

Cần quyết định nguồn nào hỗ trợ:

- Xác thực người thật.
- Định danh kết nối.
- Lệnh đã nhận.
- Đối tượng được truy cập.
- Lỗi.
- Lệnh con.
- Transaction.
- Thay đổi cấu hình.
- Kết quả cuối.

Không cần ép một nguồn trở thành nguồn đầy đủ cho mọi loại bằng chứng nếu nó không có khả năng đó.

## 6. Mô hình dữ liệu cho một bản ghi SQL

### 6.1. Các nhóm trường

| Nhóm | Trường minh họa |
| --- | --- |
| Nguồn | sourceType, engine, engineVersion, schemaVersion |
| Đích | instanceId, databaseName, environment |
| Danh tính | requesterId, loginPrincipal, effectivePrincipal |
| Phiên | pamSessionId, connectionId, backendReference |
| Yêu cầu | grantId, changeId, workloadRunId |
| Lệnh | statementId, parentStatementId, operation, statementText |
| Parameter | captureMode, parameterCount, dữ liệu được phép thu |
| Thời gian | observedAt, completedAt, ingestedAt |
| Kết quả | executionState, errorCode, rowCount khi có |
| Transaction | transactionReference, transactionState |
| Chất lượng | truncationState, parseState, correlationState |
| Nguồn gốc | rawReference, mappingVersion |

Không phải trường nào cũng do engine cung cấp. Dữ liệu bổ sung cần ghi rõ nó được lấy từ PAM, suy ra bằng quy tắc hay chưa xác minh.

### 6.2. Ví dụ bản ghi chuẩn hóa

~~~json
{
  "sourceType": "database-protocol-recorder",
  "engine": "postgresql",
  "engineVersion": "18",
  "instanceId": "billing-lab-01",
  "databaseName": "billing",
  "requesterId": "operator-017",
  "loginPrincipal": "pam_session_019",
  "effectivePrincipal": "billing_support",
  "pamSessionId": "session-019",
  "grantId": "DB-GRANT-2841",
  "connectionId": "connection-044",
  "statementId": "statement-008",
  "operation": "SELECT",
  "statementText": "SELECT status FROM billing.invoice WHERE invoice_id = $1",
  "parameters": {
    "captureMode": "metadata-only",
    "parameterCount": 1
  },
  "executionState": "completed",
  "transactionState": "not-observed",
  "resultCapture": "disabled",
  "correlationState": "matched",
  "rawReference": "evidence/session-019/event-008"
}
~~~

Đây không phải output nguyên bản của PostgreSQL hoặc một sản phẩm PAM cụ thể. completed không tự có nghĩa thay đổi đã commit; với một SELECT, cũng không tự chứng minh người dùng đã đọc mọi dòng trên màn hình.

### 6.3. Không tự điền dữ liệu chưa biết

Nếu không quan sát được transaction, dùng trạng thái chưa quan sát thay vì suy success.

Nếu chỉ biết principal đăng nhập, không gán nó làm người thật khi principal được dùng chung.

Nếu rowCount không có, không điền bằng 0. “Không biết số dòng” khác với “không có dòng”.

Các khác biệt nhỏ này ảnh hưởng trực tiếp tới kết luận điều tra.

## 7. Prepared statement và bind parameter

### 7.1. Text của câu lệnh không chứa mọi giá trị

Ví dụ:

~~~sql
SELECT status
FROM billing.invoice
WHERE invoice_id = $1;
~~~

Một câu lệnh chuẩn bị có thể được thực thi nhiều lần với parameter khác nhau. Nếu chỉ lưu text và bỏ ngữ cảnh thực thi, không thể phân biệt đầy đủ các lần gọi.

Trong PostgreSQL extended query protocol, Parse, Bind và Execute là những phần riêng của luồng. Recorder cần hiểu mối quan hệ giữa statement, portal và lần thực thi theo protocol, không chỉ tìm chuỗi SQL trong packet. [PostgreSQL protocol message flow](https://www.postgresql.org/docs/18/protocol-flow.html).

### 7.2. Các lựa chọn thu parameter

Có thể chọn:

- Không thu giá trị.
- Chỉ thu kiểu, vị trí và kích thước phù hợp.
- Thu một số giá trị được phân loại.
- Che giá trị nhạy cảm.
- Giới hạn kích thước theo policy.
- Lưu bản đầy đủ trong phạm vi truy cập rất hẹp khi có yêu cầu được xác nhận.

Không có lựa chọn duy nhất phù hợp cho mọi dữ liệu. Cần mô tả tác động tới khả năng điều tra.

Nếu không thu invoice_id, hồ sơ có thể chứng minh loại truy vấn đã chạy nhưng không xác định được invoice cụ thể từ nguồn đó. Báo cáo phải giữ giới hạn này.

### 7.3. Không tái tạo SQL bằng nối chuỗi tùy tiện

Việc chèn parameter vào text để “trông giống SQL đầy đủ” có thể sai khi có:

- Kiểu nhị phân.
- Encoding.
- NULL.
- Chuỗi có dấu nháy.
- Kiểu dữ liệu do engine hoặc extension định nghĩa.
- Parameter dùng trong nhiều vị trí.
- Thay đổi thiết lập phiên.

Nên giữ template và parameter được phép thu như các phần có cấu trúc. Nếu tạo bản hiển thị cho người đọc, ghi rõ đó là bản dựng để phân tích, không phải byte nguyên gốc đã gửi.

### 7.4. Normalization không đồng nghĩa ẩn danh

Thay literal bằng placeholder có thể giảm dữ liệu nhạy cảm, nhưng tên object, comment hoặc phần khác vẫn có thể chứa thông tin.

Một fingerprint phục vụ nhóm truy vấn không thay thế nội dung gốc hoặc định danh sự kiện. Nó cũng không nên được coi là mã duy nhất không có khả năng va chạm cho mọi lần thực thi.

## 8. Batch, procedure và tác động bên trong

### 8.1. Một lần gửi có thể chứa nhiều statement

Một client có thể gửi một batch gồm nhiều câu lệnh. Cần phân biệt:

- Batch ID.
- Statement trong batch.
- Thứ tự.
- Kết quả của từng phần.
- Điều kiện engine dừng hoặc tiếp tục khi lỗi.
- Transaction bao quanh.

Không tách SQL bằng cách cắt mọi dấu chấm phẩy. Dấu đó có thể nằm trong chuỗi, comment hoặc phần thân chương trình theo dialect.

Parser phải phù hợp với engine, hoặc hệ thống cần ghi rõ chỉ quan sát batch ngoài cùng.

### 8.2. Procedure và function

Một lệnh gọi procedure hoặc function có thể thực hiện nhiều hành động bên trong. Proxy nhìn lệnh ngoài cùng không tự biết mọi lệnh con hay đối tượng thực tế được truy cập.

Cần kiểm thử:

- Logic tĩnh.
- Dynamic SQL.
- Trigger.
- Thay ngữ cảnh quyền.
- Lệnh lồng nhau.
- Lỗi một phần.
- Hoạt động bất đồng bộ hoặc ở hệ thống khác.

Không dùng tên procedure “read_report” làm căn cứ rằng nó chỉ đọc dữ liệu.

### 8.3. SELECT không tự có nghĩa không có tác động

Một SELECT có thể gọi function có tác động theo khả năng engine. Các dạng SQL phức tạp cũng có thể chứa thao tác không được phản ánh bằng từ đầu tiên đơn giản.

Nếu sản phẩm có chức năng chặn lệnh, không kiểm soát bằng quy tắc chỉ cho mọi chuỗi bắt đầu bằng SELECT. Cần dựa vào quyền engine và phân tích đúng ngữ nghĩa của cơ chế được hỗ trợ.

### 8.4. Một lệnh có thể sinh nhiều record

Audit có thể tạo record theo object, lệnh con hoặc giai đoạn. Không đếm mọi record như một lần người dùng gửi lệnh mới.

Cần lưu quan hệ cha–con và nguồn. Ngược lại, cũng không gộp mọi record cùng text thành một hành động nếu chúng là các lần thực thi khác nhau.

## 9. Kết quả thực thi khác với commit

### 9.1. Ví dụ transaction

Ví dụ dưới đây chỉ dùng với bảng và dữ liệu lab giả:

~~~sql
BEGIN;

UPDATE billing.invoice
SET status = 'reviewed'
WHERE invoice_id = 1001;

ROLLBACK;
~~~

Một recorder có thể thấy UPDATE được thực thi rồi transaction bị rollback. Không được kết luận trạng thái reviewed đã được giữ lại chỉ vì có record UPDATE hoặc phản hồi hoàn tất cho statement.

PostgreSQL phân biệt nhóm thao tác trong transaction với việc commit hoặc rollback cả nhóm. [Transactions trong PostgreSQL](https://www.postgresql.org/docs/18/tutorial-transactions.html).

### 9.2. Trạng thái cần mô tả riêng

~~~text
statementObserved
statementAccepted
statementCompleted
statementFailed

transactionCommitted
transactionRolledBack
transactionUnknown
~~~

Đây là mô hình diễn giải đề xuất, không phải tên sự kiện native chung của mọi engine.

Chỉ gán trạng thái khi nguồn hỗ trợ. Nếu kết nối mất đúng lúc commit, client có thể chưa biết kết quả. Cần dùng bằng chứng phía server hoặc trạng thái nghiệp vụ phù hợp để xác minh.

### 9.3. Những trường hợp phức tạp

Kiểm thử thêm:

- Autocommit.
- Savepoint.
- Rollback một phần.
- Transaction lỗi.
- Timeout.
- Hủy lệnh.
- Retry sau mất kết nối.
- Tác vụ bên ngoài không cùng transaction.
- Command có quy tắc transaction riêng.

Không hứa một thao tác rollback sẽ hoàn tác mọi hoạt động trên mọi engine hoặc mọi hệ thống mà lệnh đã gọi tới.

### 9.4. Số dòng và dữ liệu trả về

Row count có thể giúp đánh giá phạm vi, nhưng cần biết nó mang ý nghĩa gì với command và nguồn cụ thể.

Nó không tự chứng minh:

- Những giá trị nào đã được xem.
- Client đã tải hết kết quả.
- Người dùng đã đọc toàn bộ.
- Dữ liệu đã được chuyển tiếp đi đâu.
- Thay đổi đã commit.

Recording result set là quyết định riêng, với rủi ro lưu thêm bản sao dữ liệu nhạy cảm.

## 10. Ví dụ kiểm tra logging PostgreSQL 18

### 10.1. Đọc cấu hình thực tế

Truy vấn chỉ đọc sau giúp xem một số tham số liên quan:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'log_statement',
    'log_min_error_statement',
    'log_min_duration_statement',
    'log_duration',
    'log_parameter_max_length',
    'log_parameter_max_length_on_error',
    'log_line_prefix',
    'log_destination',
    'logging_collector'
)
ORDER BY name;
~~~

pg_settings cung cấp giá trị runtime cùng thông tin nguồn cấu hình và yêu cầu thay đổi liên quan. Kết quả thể hiện ngữ cảnh được quan sát, không thay thế việc xác minh từng principal và đường kết nối cần audit. [View pg_settings](https://www.postgresql.org/docs/18/view-pg-settings.html).

Không chỉ đọc file cấu hình dự kiến rồi suy ra thiết lập đã có hiệu lực.

### 10.2. Một số giới hạn quan trọng

Trong PostgreSQL 18, log_statement chọn nhóm statement cần ghi, nhưng ngay cả all cũng không ghi mọi lỗi xảy ra trước điểm ghi tương ứng. Lỗi parse cần được xét cùng cấu hình ghi statement gây lỗi. Các thiết lập độ dài bind parameter cho log thường và log lỗi là các điều khiển riêng; giới hạn bind parameter không tự xóa literal nhạy cảm nằm trong text SQL. [Error Reporting and Logging](https://www.postgresql.org/docs/18/runtime-config-logging.html).

Hệ quả nghiệm thu:

- Thử cả thành công và lỗi sớm.
- Thử protocol mà driver thực sự dùng.
- Thử secret giả trong literal và parameter.
- Kiểm tra mọi nguồn log liên quan.
- Không dùng một tham số để tuyên bố đã giải quyết toàn bộ privacy và coverage.

### 10.3. Query chậm không đại diện cho mọi truy cập đặc quyền

Một policy hiệu năng có thể chỉ ghi lệnh chậm hoặc lấy mẫu. Điều đó không đáp ứng tự động mục tiêu ghi mọi thao tác quản trị hoặc truy cập dữ liệu quan trọng.

Cần tách:

- Yêu cầu quan sát hiệu năng.
- Yêu cầu truy vết đặc quyền.
- Yêu cầu về dữ liệu nhạy cảm.
- Khả năng và chi phí của nguồn.

Không báo “full SQL recording” khi chỉ có log theo ngưỡng thời gian.

### 10.4. Audit extension

pgAudit cung cấp session và object audit với các trường như statement ID, substatement ID, class và thông tin object theo cấu hình. Một statement có thể sinh nhiều record, và việc thu parameter là lựa chọn cần đánh giá. [Tài liệu dự án pgAudit](https://github.com/pgaudit/pgaudit).

Nếu dùng extension hoặc tính năng audit tương tự, cần xác nhận:

- Phiên bản tương thích.
- Khả năng nhà cung cấp hỗ trợ.
- Phạm vi principal và database.
- Nhóm command.
- Cách chuyển log.
- Giới hạn lệnh con.
- Overhead.
- Quyền thay cấu hình.
- Hành vi khi lỗi.

Không áp dụng một đoạn cấu hình audit chỉ vì nó chạy ở engine cùng tên nhưng khác phiên bản hoặc mô hình managed service.

## 11. Dữ liệu nhạy cảm trong recording

### 11.1. Những gì có thể bị lộ

Bản ghi có thể chứa:

- Password trong lệnh quản trị.
- Token hoặc API key.
- Định danh khách hàng.
- Dữ liệu tài chính.
- Nội dung tìm kiếm.
- Trường trong result set.
- Tên database hoặc schema mang thông tin nội bộ.
- Error message có dữ liệu.
- Script hoặc comment chứa thông tin không cần thiết.

Recording có thể trở thành kho dữ liệu nhạy cảm mới. Cần thiết kế chính sách trước khi bật thu rộng.

### 11.2. Chính sách thu theo trường và lớp

Một ma trận tham khảo:

| Dữ liệu | Cách xử lý có thể chọn |
| --- | --- |
| Metadata phiên | Thu theo nhu cầu truy vết |
| SQL template | Thu nếu phù hợp, kiểm tra literal và comment |
| Bind parameter nhạy cảm | Không thu hoặc che tại điểm được kiểm soát |
| Parameter phục vụ điều tra cụ thể | Thu theo phạm vi đã xác nhận và hạn chế truy cập |
| Password và token | Tránh thu, không đưa vào log tự tạo |
| Result set | Không mặc định thu toàn bộ |
| Lỗi | Thu mã và ngữ cảnh cần thiết, kiểm tra dữ liệu lộ trong text |
| Bản nguyên gốc được phép lưu | Bảo vệ chặt và có retention phù hợp |

Nếu policy cấm lưu một secret, chỉ che ở giao diện tìm kiếm là chưa đủ nếu bản raw, queue hoặc backup vẫn giữ nó.

### 11.3. Redaction phải có ngữ nghĩa rõ

Cần ghi:

- Trường hoặc phần nào bị che.
- Che trước hay sau khi lưu.
- Quy tắc và phiên bản.
- Bản nào còn chứa dữ liệu đầy đủ.
- Ai được xem.
- Tác động tới điều tra.

Ví dụ, chỉ giữ template và không giữ parameter là một lựa chọn tối thiểu hóa dữ liệu, nhưng sẽ giảm khả năng xác định object nghiệp vụ nếu object chỉ nằm trong parameter.

Không tuyên bố vừa không thu dữ liệu vừa có thể tái dựng đầy đủ mọi giá trị trong request.

### 11.4. Truncation không phải redaction

Cắt chuỗi theo số byte không bảo đảm đã loại secret. Một secret ngắn vẫn có thể nằm trọn ở đầu chuỗi.

Khi có truncation, phải thể hiện trạng thái. Không để analyst hiểu nội dung rút gọn là toàn bộ command.

Nếu bị cắt giữa encoding hoặc cấu trúc dữ liệu, parser cần xử lý rõ thay vì bỏ record âm thầm.

## 12. Danh tính, pool và quyền hiệu lực

### 12.1. Nối tới người hoặc workload thật

Một chuỗi có thể là:

~~~text
Người doanh nghiệp
    -> grant PAM
    -> tài khoản database tạm
    -> kết nối
    -> statement
~~~

Hoặc:

~~~text
Pipeline run
    -> policy cấp quyền
    -> credential workload
    -> pool hoặc kết nối
    -> statement
~~~

Mỗi mũi tên cần dữ liệu được bảo vệ. Một comment SQL do client tự đặt không đủ làm bằng chứng danh tính.

### 12.2. Login principal và effective principal

Lệnh có thể chạy dưới ngữ cảnh quyền khác tài khoản ban đầu, do chuyển role hoặc logic thực thi của engine.

Recording nên giữ những lớp danh tính mà nguồn thật sự quan sát được, đồng thời bảo toàn sự kiện thay ngữ cảnh khi nằm trong phạm vi.

Không gán mọi hoạt động cho principal đang thấy ở một thời điểm rồi suy ra toàn bộ phiên trước đó cũng dùng cùng quyền.

### 12.3. Connection pooling

Một backend có thể phục vụ nhiều người hoặc nhiều request. Cần hiểu:

- Session pooling hay transaction pooling.
- Đơn vị mapping.
- Thời điểm gắn và reset ngữ cảnh.
- Khả năng dùng lại prepared statement.
- Cách liên kết lần thực thi với người yêu cầu.
- Hành vi retry và reconnect.

Nếu không có mapping đáng tin cậy, chỉ có thể quy hoạt động cho ứng dụng hoặc principal trực tiếp, không tự suy ra người cuối.

### 12.4. Chủ thể của automation

Với workload, cần run ID, phiên bản triển khai, owner và nguồn cấp quyền phù hợp. Không dùng tên job do người gọi tùy ý đặt làm căn cứ duy nhất.

Cần giữ riêng:

- Người phê duyệt.
- Người hoặc hệ thống khởi chạy.
- Workload thực thi.
- Principal trực tiếp trong database.

Một người tạo pipeline không mặc định chịu trách nhiệm trực tiếp cho mọi statement của mọi lần chạy sau đó.

## 13. Toàn vẹn và khả năng sử dụng bằng chứng

### 13.1. Phân tách quyền

Những quyền cần quản lý riêng:

- Mở phiên database.
- Sửa cấu hình recorder.
- Đọc recording.
- Xem parameter nhạy cảm.
- Xuất hồ sơ.
- Đổi retention.
- Xóa bằng chứng.
- Quản trị khóa mã hóa.
- Sửa parser và rule tương quan.

Một database superuser có thể tác động tới nguồn log nội bộ theo khả năng nền tảng. Cần đánh giá lưu bằng chứng ở ranh giới ngoài quyền đó và xét cả quyền OS hoặc cloud liên quan.

### 13.2. Bản gốc, bản chuẩn hóa và bản che dữ liệu

Có thể giữ nhiều lớp:

- Record gốc mà policy cho phép thu.
- Bản chuẩn hóa phục vụ tương quan.
- Bản đã che để nhóm rộng hơn tra cứu.
- Bản trích xuất cho một vụ việc.

Cần tham chiếu nguồn và phiên bản chuyển đổi. Không sửa âm thầm bản gốc rồi trình bày như dữ liệu engine đã phát.

### 13.3. Toàn vẹn khác đầy đủ

Hash hoặc cơ chế chống thay đổi hỗ trợ kiểm tra bản ghi không bị sửa theo phạm vi được xác minh. Chúng không chứng minh mọi lệnh cần thiết đã được ghi.

Một kho recording nguyên vẹn vẫn có thể thiếu:

- Kết nối trực tiếp.
- Lệnh qua driver không hỗ trợ.
- Parameter bị loại.
- Lệnh con.
- Giai đoạn recorder bị lỗi.
- Account hoặc instance chưa onboarding.

Báo cáo phải có cả trạng thái toàn vẹn và trạng thái coverage.

### 13.4. Định danh và thứ tự

Không dùng mỗi PID làm session ID lâu dài, vì định danh có thể được tái sử dụng theo vòng đời hệ thống.

Cần kết hợp định danh nguồn, instance, kết nối, thời điểm bắt đầu và dữ liệu tương ứng theo hợp đồng nguồn. Giữ số thứ tự hoặc định danh statement khi có để dựng lại timeline.

Các record có thể tới trễ hoặc giao lại. Dedupe và sắp xếp phải bảo toàn các lần thực thi khác nhau.

## 14. Hiệu năng và lỗi recording

### 14.1. Chi phí cần đo

Recording có thể tăng:

- CPU.
- I/O.
- Dung lượng log.
- Băng thông.
- Độ trễ.
- Thời gian parser xử lý.
- Tải truy vấn kho audit.
- Chi phí lưu và truy xuất.

Đo bằng workload gần với thực tế, gồm batch lớn, parameter lớn, nhiều connection và lỗi. Không suy từ một demo nhỏ.

### 14.2. Giảm tải mà vẫn giữ đúng yêu cầu

Có thể phân loại theo:

- Principal đặc quyền.
- Loại command.
- Database và object quan trọng.
- Phiên PAM.
- Nhóm workload.

Nếu lấy mẫu hoặc bỏ một loại lệnh, ghi rõ phần bảo đảm bị giảm. Không âm thầm sampling rồi giữ nhãn “mọi lệnh đã được ghi”.

### 14.3. Chính sách khi recorder lỗi

Cần quyết định trước:

- Không mở phiên đặc quyền mới khi chưa có recording bắt buộc.
- Tạm dừng hoặc đóng phiên theo khả năng và policy.
- Cho phép ngoại lệ khẩn cấp có bằng chứng thay thế.
- Cách xử lý backlog.
- Cách cảnh báo và khôi phục.
- Ai được phê duyệt ngoại lệ.

Với workload liên tục, phải đánh giá tác động sẵn sàng. Không mặc định một hành vi chung cho mọi loại kết nối.

### 14.4. Theo dõi sức khỏe end-to-end

Các tín hiệu có ích:

- Nguồn còn phát record.
- Lỗi ghi.
- Backlog và tuổi record chờ.
- Độ trễ ingest.
- Parse lỗi.
- Truncation.
- Record bị loại.
- Quyền đọc kho hoặc khóa bị lỗi.
- Số phiên mở nhưng chưa có record mong đợi.
- Kết quả canary test.

Collector đang chạy không chứng minh dữ liệu cuối cùng đã truy xuất được.

## 15. Kiểm thử SQL command recording

### 15.1. Bộ dữ liệu lab

Dùng database và dữ liệu giả, có người chịu trách nhiệm và đích rõ. Chuẩn bị các object phục vụ:

- Đọc.
- Ghi.
- Lỗi quyền.
- Prepared statement.
- Transaction.
- Procedure hoặc function.
- Parameter nhạy cảm giả.

Không dùng secret thật để kiểm tra redaction.

### 15.2. Ma trận nghiệm thu

| Phép thử | Điều cần chứng minh |
| --- | --- |
| SELECT đơn giản | Có command và mapping phiên đúng |
| INSERT, UPDATE, DELETE trên dữ liệu lab | Có record và kết quả được diễn giải đúng |
| Lỗi cú pháp | Biết nguồn nào ghi lỗi sớm |
| Lỗi quyền | Có lỗi và principal tương ứng trong phạm vi thiết kế |
| Prepared statement chạy nhiều lần | Không gộp sai các lần Execute |
| Parameter có chuỗi, NULL và dữ liệu nhị phân | Không dựng sai nội dung hoặc làm hỏng parser |
| SQL nhiều dòng và comment | Không chia sai thành nhiều sự kiện |
| Batch nhiều statement | Giữ thứ tự và quan hệ kết quả |
| Procedure với lệnh con | Xác định rõ quan sát được tới mức nào |
| UPDATE rồi ROLLBACK | Không báo thay đổi đã commit |
| Savepoint và lỗi một phần | Không gán một trạng thái chung thiếu căn cứ |
| Mất kết nối quanh COMMIT | Giữ unknown khi chưa có bằng chứng đủ |
| Retry | Phân biệt lần gửi và tác động thực tế |
| Kết nối trực tiếp ngoài gateway | Bị chặn hoặc được nguồn khác bao phủ theo thiết kế |
| Client GUI, CLI và driver ứng dụng | Không bỏ sót vì khác công cụ |
| Pool dùng lại backend | Không nối nhầm người hoặc grant |
| Parameter và literal chứa secret giả | Kiểm tra mọi bản ghi, queue và đích lưu liên quan |
| Recorder lỗi hoặc đầy đích | Phản ứng đúng policy và có cảnh báo |
| Record giao lại | Không tăng số lệnh sai |
| Truy xuất hồ sơ cũ | Đọc được và nối tới nguồn gốc |

Mỗi phép thử cần đầu vào, sự kiện mong đợi, thời gian chờ, điều kiện PASS và giới hạn. Một lệnh thất bại do mạng không chứng minh engine đã từ chối vì thiếu quyền.

### 15.3. Kiểm thử tính độc lập của bằng chứng

Trong lab được phép, xác minh principal tác nghiệp không tự:

- Xóa recording.
- Tắt nguồn mà không để lại tín hiệu cần thiết.
- Đổi retention.
- Sửa mapping danh tính.
- Che hành động bằng cách dùng kết nối khác trong phạm vi kiểm soát.

Mục tiêu là kiểm tra ranh giới đã thiết kế, không tạo hoạt động phá hủy trên dữ liệu thật.

## 16. Tình huống thực hành: “có log UPDATE” nhưng trạng thái chưa rõ

### 16.1. Bối cảnh

Một phiên hỗ trợ production được cấp quyền sửa dữ liệu theo CHG-2841. Hệ thống recording có text UPDATE và record hoàn tất statement.

Sau đó client mất kết nối. Nhóm vận hành kết luận “dữ liệu đã được sửa thành công” nhưng chưa tìm thấy bằng chứng transaction cuối.

### 16.2. Phân tích

Cần xác định:

- Client dùng autocommit hay transaction tường minh.
- UPDATE thuộc transaction nào.
- Có COMMIT hoặc ROLLBACK được quan sát không.
- Server đã phản hồi gì.
- Có retry không.
- Có thay đổi tiếp theo từ workload khác không.
- Dữ liệu hiện tại và lịch sử phù hợp cho biết gì.
- Recording có giai đoạn thiếu hoặc trễ không.

Không dùng trạng thái hiện tại đơn lẻ để quy mọi thay đổi cho phiên đang điều tra nếu còn principal khác có thể sửa cùng dữ liệu.

### 16.3. Đầu ra cần nộp

- Timeline của phiên và các lần thực thi.
- Bảng phân biệt observed, inferred và unknown.
- Chuỗi grant–connection–statement–transaction.
- Kết luận trong phạm vi bằng chứng.
- Những nguồn cần bổ sung.
- Điều chỉnh schema hoặc pipeline nếu trước đây chỉ có một trường success.

Bài đạt khi người rà soát hiểu được điều gì đã biết chắc, điều gì chỉ là suy luận và điều gì còn chưa xác định.

## 17. Rà soát phiên và phát hiện bất thường

### 17.1. Các nhóm phát hiện

Có thể xây rule cho:

- Lệnh quản trị ngoài loại công việc được duyệt.
- Truy cập object ngoài scope.
- Tạo principal hoặc cấp quyền trong phiên hỗ trợ dữ liệu.
- Thay cấu hình recording.
- Nhiều lỗi quyền bất thường.
- Hoạt động sau thời hạn mà policy không cho phép.
- Một principal dùng nhiều đường kết nối không được giải thích.
- Phiên có recording thiếu hoặc không khớp danh tính.
- Khối lượng truy cập khác đáng kể với nhiệm vụ.

Cần dùng ngữ cảnh và quyền thực tế. Một command xuất hiện trong log không tự chứng minh nó trái phép.

### 17.2. Truy vấn minh họa

~~~sql
SELECT
    pam_session_id,
    requester_id,
    instance_id,
    operation,
    statement_id,
    observed_at,
    correlation_state,
    raw_reference
FROM normalized_sql_events
WHERE observed_at >= :start_time
  AND observed_at < :end_time
  AND (
      correlation_state IN ('unmatched', 'conflict')
      OR coverage_state = 'incomplete'
  );
~~~

Đây là SQL trên schema phân tích giả định, không phải truy vấn native của PostgreSQL audit.

Kết quả là danh sách cần đánh giá, có thể do grant tới trễ, mapping lỗi hoặc hoạt động ngoài quy trình. Không tự gán mọi dòng là hành vi xấu.

### 17.3. Hồ sơ rà soát

Nên lưu:

- Mã phiên và công việc.
- Người rà soát.
- Phạm vi recording.
- Command quan trọng.
- Kết luận và căn cứ.
- Khoảng thiếu bằng chứng.
- Hành động tiếp theo.
- Thời điểm đóng phát hiện.

Giới hạn quyền xem và xuất dữ liệu của người rà soát; SQL recording có thể chứa nội dung nhạy cảm ở nhiều môi trường.

## 18. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| Có lịch sử SQL editor là đủ audit | Không bao phủ mọi client và có thể sửa |
| Có video thì biết mọi lệnh engine nhận | Driver và tác vụ nền có thể không hiển thị đầy đủ |
| Có query fingerprint thì có từng lần thực thi | Fingerprint phục vụ nhóm, không phải timeline riêng |
| Ghi text là ghi đầy đủ prepared statement | Parameter và lần Execute cần được xử lý |
| Statement thành công là dữ liệu đã commit | Cần ngữ cảnh transaction |
| Mọi SELECT đều chỉ đọc | Phải xét ngữ nghĩa và logic được gọi |
| Proxy thấy lệnh ngoài cùng là biết mọi lệnh con | Cần kiểm thử audit phía engine |
| Giới hạn độ dài là đã che secret | Truncation không phải redaction |
| Parameter không ghi thì literal cũng an toàn | Hai vị trí dữ liệu cần kiểm soát riêng |
| Hash chứng minh mọi lệnh đã được ghi | Toàn vẹn và coverage là hai yêu cầu khác nhau |
| Đóng phiên PAM là hết mọi hoạt động DB | Kết nối, job và tác động đã tạo cần xác minh riêng |
| Không thấy SQL trong log là không có truy cập | Phải kiểm tra nguồn, phạm vi và pipeline |

## 19. Chỉ số duy trì kiểm soát

Các chỉ số có ích:

- Tỷ lệ đường truy cập đặc quyền đã có nguồn recording được kiểm thử.
- Tỷ lệ phiên nối được tới người hoặc workload và grant.
- Tỷ lệ statement có mapping kết nối đáng tin cậy.
- Số phiên hoặc giai đoạn recording bị thiếu.
- Độ trễ từ nguồn tới kho phân tích.
- Tỷ lệ parse lỗi và truncation.
- Tỷ lệ record có transaction state chưa xác định khi cần kết luận về commit.
- Số phát hiện secret giả trong các đợt kiểm thử redaction.
- Tỷ lệ truy xuất bằng chứng lịch sử thành công.
- Tỷ lệ phiên quan trọng được rà soát.
- Số ngoại lệ bỏ qua recorder chưa được đóng.
- Overhead theo workload đã xác nhận.

Không dùng dung lượng log như thước đo duy nhất. Nhiều log vẫn có thể thiếu đúng command, parameter hoặc danh tính cần cho một cuộc điều tra.

## 20. Câu hỏi tự kiểm tra

**SQL command recording có bắt buộc lưu mọi result set không?**

Không. Ghi command và ghi dữ liệu trả về là hai quyết định riêng. Cần chọn theo nhu cầu và rủi ro lưu thêm dữ liệu.

**Vì sao chỉ lưu template chưa đủ cho prepared statement?**

Vì cùng template có thể được thực thi nhiều lần với parameter khác nhau. Cần biết phạm vi parameter được thu và định danh lần thực thi.

**Có record UPDATE completed thì có thể kết luận đã commit không?**

Chưa. Transaction có thể rollback hoặc kết quả cuối chưa được quan sát.

**Có thể tách batch bằng mọi dấu chấm phẩy không?**

Không. Cần hiểu dialect, chuỗi, comment và phần thân chương trình.

**Giới hạn bind parameter có xóa secret trong literal SQL không?**

Không tự bảo đảm điều đó. Cần kiểm soát từng vị trí và từng nguồn log.

**Gateway có thể bảo đảm mọi lệnh được ghi khi còn đường trực tiếp không?**

Chỉ khi có kiểm soát hoặc nguồn bổ sung bao phủ đường đó theo thiết kế. Không thể mặc định gateway thấy luồng không đi qua nó.

**Một backend dùng chung có thể quy chắc cho một người không?**

Chỉ khi có mapping đủ tin cậy theo đúng đơn vị pooling và request. Nếu không, phải ghi giới hạn quy trách nhiệm.

**Vì sao cần giữ trạng thái unknown?**

Để tránh biến khoảng thiếu quan sát thành kết luận thành công, thất bại hoặc không có hoạt động.

SQL command recording phục vụ PAM khi nó nối được danh tính với quyền, phiên và hành động, đồng thời giữ đúng ngữ nghĩa của protocol và transaction. Độ bao phủ đã kiểm thử, dữ liệu được thu có chủ đích, bằng chứng được bảo vệ và kết luận đúng mức quan sát quan trọng hơn một tuyên bố chung rằng hệ thống đang “ghi mọi câu SQL”.
