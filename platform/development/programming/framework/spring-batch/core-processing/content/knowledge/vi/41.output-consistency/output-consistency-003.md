# Database output và unique constraint trong Spring Batch

Một batch job thường đọc dữ liệu từ file, API hoặc database rồi ghi kết quả vào bảng đích. Nếu cùng một input được xử lý hai lần, job có thể tạo bản ghi trùng, ghi đè dữ liệu ngoài ý muốn hoặc làm sai số liệu nghiệp vụ. Tình huống này có thể xảy ra khi file nguồn chứa duplicate, khi operator restart job, khi scheduler khởi chạy lại, hoặc khi nhiều partition cùng xử lý một business key.

Unique constraint là hàng rào bảo vệ cuối cùng ở database để một hoặc nhiều cột không có giá trị trùng theo quy tắc đã khai báo. Trong Spring Batch, constraint này phối hợp với writer, transaction, retry, skip và restart để bảo vệ tính nhất quán của output. Tuy nhiên, chỉ thêm constraint không tự giải quyết mọi tình huống duplicate. Job còn phải xác định một record nào được xem là cùng một nghiệp vụ, xử lý duplicate theo đúng contract và thiết kế writer an toàn khi được gọi lại.

## 1. Vì sao database output cần unique constraint?

Giả sử job import order từ file. Mỗi order có source order ID và customer ID. Nếu cùng một order xuất hiện hai lần, câu INSERT đơn giản có thể tạo hai hàng giống nhau:

~~~text
Input file
  |
  +--> Order O-100
  +--> Order O-101
  +--> Order O-100   (duplicate)
  |
  v
JdbcBatchItemWriter
  |
  v
imported_order
  |
  +--> O-100
  +--> O-101
  +--> O-100   (không mong muốn)
~~~

Một cách kiểm tra ở Java là giữ Set các ID đã thấy, nhưng cách này chỉ kiểm soát được phạm vi mà một instance đang quan sát. Nó không bảo vệ được trước:

- Một lần chạy khác xử lý cùng file.
- Job restart sau khi một side effect đã commit.
- Hai partition xử lý cùng một key.
- Hai application instance chạy cùng một batch.
- Một request khác ghi cùng bảng ngoài batch job.

Database unique constraint được kiểm tra ở nơi dữ liệu được lưu, nên có thể bảo vệ dữ liệu trước các writer cạnh tranh cùng lúc. Đây là lớp bảo vệ quan trọng cho business key và idempotency key.

## 2. Unique constraint là gì?

Unique constraint yêu cầu giá trị của một cột hoặc tổ hợp cột không được trùng giữa các hàng theo quy tắc của database.

Ví dụ một bảng chỉ cho phép một order có cùng source order ID:

~~~sql
create table imported_order (
    id bigint generated always as identity primary key,
    source_order_id varchar(80) not null,
    customer_id varchar(80) not null,
    total_amount decimal(18, 2) not null,
    imported_at timestamp not null,
    constraint uk_imported_order_source
        unique (source_order_id)
);
~~~

Nếu một câu INSERT cố tạo hàng thứ hai có cùng source_order_id, database từ chối thao tác bằng lỗi unique violation. Tên constraint rõ ràng giúp log và thông báo lỗi dễ hiểu hơn.

Unique constraint thường được database thực thi bằng unique index hoặc cấu trúc index tương đương. Nó là quy tắc được database bảo đảm, không phải một kiểm tra tùy chọn trong Java.

## 3. Primary key và unique constraint khác nhau thế nào?

Primary key xác định danh tính chính của một hàng. Unique constraint bảo đảm tính duy nhất cho một business key hoặc một tổ hợp thuộc tính khác.

| Đặc điểm | Primary key | Unique constraint |
| --- | --- | --- |
| Mục đích | Định danh hàng | Ngăn trùng một giá trị hoặc tổ hợp giá trị |
| Số lượng trên bảng | Một primary key | Có thể có nhiều unique constraint |
| NULL | Không cho phép NULL | Cách xử lý NULL phụ thuộc database |
| Quan hệ tham chiếu | Thường được foreign key tham chiếu | Có thể được tham chiếu nếu đáp ứng quy tắc database |
| Ví dụ | id | source_system + source_record_id |

Một bảng có thể dùng surrogate primary key là id, đồng thời có unique constraint trên source_system và source_record_id để ngăn một record nguồn được import hai lần.

Không nên chỉ dựa vào generated primary key để chống duplicate nghiệp vụ. Nếu mỗi lần import tạo một ID mới, hai bản sao của cùng một source record vẫn có thể trở thành hai hàng hợp lệ theo primary key.

## 4. Unique constraint trên nhiều cột

Nhiều khi một cột không đủ để xác định record duy nhất. Ví dụ customer code có thể lặp giữa các tenant, hoặc external reference chỉ duy nhất trong một hệ thống nguồn.

~~~sql
create table customer_import (
    id bigint generated always as identity primary key,
    tenant_id varchar(40) not null,
    source_system varchar(40) not null,
    source_customer_id varchar(80) not null,
    customer_name varchar(200) not null,
    constraint uk_customer_import_source
        unique (tenant_id, source_system, source_customer_id)
);
~~~

Trong ví dụ này, cùng source_customer_id có thể xuất hiện ở tenant khác hoặc source system khác, nhưng không thể trùng trong cùng tổ hợp ba cột.

Thứ tự cột trong unique constraint không thay đổi quy tắc logic về tính duy nhất của tổ hợp, nhưng có thể ảnh hưởng cách index hỗ trợ query. Hãy thiết kế index theo cả constraint và các truy vấn lookup thực tế.

## 5. Chọn đúng business key

Unique constraint chỉ có ích khi cột hoặc tổ hợp cột phản ánh đúng danh tính nghiệp vụ. Một số ví dụ:

| Loại dữ liệu | Business key có thể dùng |
| --- | --- |
| Record import từ file | source_file_id + source_record_number |
| Event từ message broker | source_system + event_id |
| Customer từ nhiều hệ thống | tenant_id + source_system + external_customer_id |
| Giao dịch thanh toán | payment_provider + provider_transaction_id |
| Dòng hóa đơn | invoice_id + line_number |

Trước khi thêm constraint, cần trả lời:

- Hai record có cùng key có chắc là cùng một nghiệp vụ không?
- Key có thể thay đổi theo thời gian không?
- Key có chỉ duy nhất trong tenant, source system hay business date không?
- Có cần giữ lại nhiều phiên bản của cùng record không?
- Nếu producer gửi lại record cũ với nội dung khác, đó là duplicate hay update?

Không chọn một cột có vẻ tiện như customer name hoặc email làm unique key nếu nghiệp vụ cho phép nhiều customer có cùng giá trị hoặc giá trị đó có thể thay đổi.

## 6. Idempotency key khác business key

Business key nhận diện một thực thể nghiệp vụ, còn idempotency key nhận diện một thao tác hoặc event cần được áp dụng tối đa một lần về mặt logic.

Ví dụ cùng customer có nhiều lần cập nhật địa chỉ. Customer ID là business key của customer, nhưng không thể dùng nó để loại bỏ mọi event sau event đầu tiên. Mỗi update cần một event ID riêng:

~~~text
Customer C-100
  |
  +--> Event E-001: đổi địa chỉ lần 1
  +--> Event E-002: đổi địa chỉ lần 2
  +--> Event E-003: đổi địa chỉ lần 3
~~~

Có thể tạo bảng inbox hoặc processed_event:

~~~sql
create table processed_event (
    source_system varchar(40) not null,
    event_id varchar(100) not null,
    processed_at timestamp not null,
    constraint uk_processed_event
        unique (source_system, event_id)
);
~~~

Khi event được xử lý lại do retry/restart, unique key trên event giúp nhận diện thao tác đã được áp dụng. Business table vẫn có key riêng để bảo vệ tính duy nhất của customer/order.

Không dùng một business key làm idempotency key nếu cùng business entity được phép nhận nhiều event hợp lệ.

## 7. Khai báo unique constraint trong JPA entity

Với JPA, có thể mô tả unique constraint bằng @Table:

~~~java
@Entity
@Table(
    name = "customer_import",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_customer_import_source",
            columnNames = {
                "tenant_id",
                "source_system",
                "source_customer_id"
            }
        )
    }
)
public class CustomerImport {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "source_system", nullable = false)
    private String sourceSystem;

    @Column(name = "source_customer_id", nullable = false)
    private String sourceCustomerId;
}
~~~

@UniqueConstraint mô tả schema cho JPA provider khi tạo DDL. Trong production, không nên phụ thuộc vào việc Hibernate tự cập nhật schema để bảo đảm constraint đã tồn tại. Dùng migration tool như Flyway hoặc Liquibase để triển khai constraint một cách có kiểm soát.

Annotation không thay thế kiểm tra database thực tế. Cần xác nhận unique constraint đã được tạo trên đúng schema và đúng môi trường.

## 8. @Column(unique = true) và @Table(uniqueConstraints)

@Column(unique = true) phù hợp với unique constraint một cột:

~~~java
@Column(name = "external_id", nullable = false, unique = true)
private String externalId;
~~~

Với unique constraint nhiều cột, dùng @Table(uniqueConstraints = ...):

~~~java
@Table(
    uniqueConstraints = @UniqueConstraint(
        name = "uk_tenant_external_id",
        columnNames = {"tenant_id", "external_id"}
    )
)
~~~

Các annotation này là metadata mapping. Việc database thực sự có constraint phụ thuộc schema được tạo/cập nhật như thế nào. Nếu production dùng migration, migration phải chứa DDL tương ứng.

Không nên tạo unique constraint trong Java rồi giả định mọi môi trường đã có cùng cấu trúc. Kiểm tra migration, schema version và catalog của database.

## 9. Tạo unique constraint bằng migration

Một migration SQL có thể thêm constraint:

~~~sql
alter table imported_order
add constraint uk_imported_order_source
unique (source_system, source_order_id);
~~~

Trước khi chạy migration trên bảng đang có dữ liệu, phải tìm và xử lý duplicate hiện tại:

~~~sql
select source_system, source_order_id, count(*) as duplicate_count
from imported_order
group by source_system, source_order_id
having count(*) > 1;
~~~

Nếu query trả về hàng, migration thêm constraint có thể thất bại. Cần xác định record nào là bản chuẩn, record nào cần merge, archive hoặc xóa theo quy tắc nghiệp vụ.

Không xóa duplicate tự động chỉ dựa vào thời gian tạo mới nhất/cũ nhất nếu chưa biết record nào là đúng. Có thể tồn tại khác biệt về trạng thái, payment hoặc quan hệ foreign key.

## 10. Unique constraint và NULL

Không nên giả định mọi database xử lý NULL trong unique constraint giống nhau. Một số database cho phép nhiều hàng có NULL trong cột unique vì NULL được xem là unknown; một số engine hoặc loại index có quy tắc khác. Với unique constraint nhiều cột, hành vi còn phụ thuộc tổ hợp cột và vendor.

Nếu business key bắt buộc phải có giá trị, khai báo NOT NULL cho các cột thành phần:

~~~sql
source_system varchar(40) not null,
source_record_id varchar(100) not null,
constraint uk_source_record
    unique (source_system, source_record_id)
~~~

Nếu NULL có ý nghĩa nghiệp vụ, hãy quyết định rõ có cho phép nhiều record chưa có key hay không. Có thể cần partial/filtered unique index hoặc expression index tùy database. Đây là tính năng vendor-specific, cần migration và integration test theo đúng engine.

Không dùng chuỗi rỗng hoặc một sentinel như UNKNOWN làm key chung cho mọi record thiếu ID nếu điều đó làm các record hợp lệ xung đột với nhau.

## 11. Chuẩn hóa dữ liệu trước khi áp dụng unique key

Hai giá trị có thể khác nhau về biểu diễn nhưng được nghiệp vụ xem là cùng một key:

- ABC và abc.
- Email có khoảng trắng đầu/cuối.
- Mã có dấu gạch nối hoặc không có dấu gạch nối.
- Unicode được mã hóa theo dạng chuẩn khác nhau.

Nếu database collation không phân biệt hoa thường, unique constraint có thể xem ABC và abc là cùng giá trị. Nếu collation phân biệt, chúng có thể được coi là khác nhau. Quy tắc còn tùy database và kiểu cột.

Có thể chuẩn hóa key trước khi ghi:

~~~java
public String normalizeExternalId(String value) {
    if (value == null) {
        throw new InvalidInputException("externalId is required");
    }
    return value.strip().toUpperCase(Locale.ROOT);
}
~~~

Hãy áp dụng cùng quy tắc ở mọi producer/writer và cân nhắc lưu cả raw value nếu cần audit. Không thay đổi normalization rule giữa các lần restart của cùng batch mà không có versioning.

## 12. Đừng nối nhiều cột thành một chuỗi key tùy tiện

Một cách dễ gây collision là nối chuỗi:

~~~java
String key = tenantId + "-" + externalId;
~~~

Nếu dữ liệu có dấu gạch nối, hai tổ hợp khác nhau có thể tạo cùng chuỗi. Ví dụ tenant A-B với ID C và tenant A với ID B-C đều có thể tạo A-B-C.

Tốt hơn là dùng unique constraint trên từng cột:

~~~sql
unique (tenant_id, external_id)
~~~

Nếu hệ thống bắt buộc cần một idempotency string, dùng encoding không nhập nhằng, length-prefix hoặc UUID/hash được tạo từ canonical representation có version. Database vẫn nên bảo vệ các cột nghiệp vụ gốc khi có thể.

## 13. Database là nơi quyết định uniqueness

Một kiểm tra trước khi insert thường có dạng:

~~~java
if (!repository.existsBySourceOrderId(order.sourceOrderId())) {
    repository.save(order);
}
~~~

Cách này có race condition:

~~~text
Worker A: SELECT -> chưa có O-100
Worker B: SELECT -> chưa có O-100
Worker A: INSERT O-100 -> thành công
Worker B: INSERT O-100 -> duplicate
~~~

Hai worker có thể cùng quan sát trạng thái chưa tồn tại trước khi một worker ghi. Kiểm tra Java chỉ cải thiện thông báo hoặc tránh một số lần ghi thừa; nó không thay thế unique constraint.

Database constraint là cơ chế cuối cùng để đồng bộ quyết định giữa các transaction cạnh tranh.

## 14. Vì sao SELECT rồi INSERT không đủ?

Ngay cả khi job chạy đơn thread, một ứng dụng khác hoặc một lần chạy batch khác có thể ghi cùng key trong khoảng thời gian giữa SELECT và INSERT.

Đây là check-then-act race. Transaction isolation thông thường không biến hai câu lệnh riêng biệt thành thao tác insert-if-absent nguyên tử.

Các lựa chọn:

- Cố gắng INSERT trực tiếp và để unique constraint quyết định.
- Dùng cú pháp upsert/insert-if-absent do database hỗ trợ.
- Dùng khóa/serialization có chủ đích nếu nghiệp vụ cần.
- Dùng staging và merge theo một quy trình có transaction rõ ràng.

Không dùng SELECT NOT EXISTS như hàng rào duy nhất để chống duplicate khi có concurrency.

## 15. Ghi output bằng JdbcBatchItemWriter

JdbcBatchItemWriter phù hợp để ghi nhiều item bằng cùng một câu SQL:

~~~java
@Bean
JdbcBatchItemWriter<ImportedOrder> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<ImportedOrder>()
        .dataSource(dataSource)
        .sql("""
            insert into imported_order
                (source_system, source_order_id, customer_id, total_amount)
            values
                (:sourceSystem, :sourceOrderId, :customerId, :totalAmount)
            """)
        .beanMapped()
        .assertUpdates(true)
        .build();
}
~~~

Nếu chunk chứa hai item có cùng source_system và source_order_id, unique constraint từ chối duplicate. JdbcBatchItemWriter chuyển lỗi JDBC lên step; Spring Batch xử lý theo transaction và fault-tolerance policy.

assertUpdates(true) kiểm tra update count theo quy tắc của writer, nhưng không thay thế unique constraint. Unique constraint bảo vệ tính duy nhất; assertUpdates kiểm tra câu lệnh có tác động hàng theo kỳ vọng.

## 16. Duplicate key trong JDBC batch

Khi một item trong JDBC batch vi phạm unique constraint, driver có thể ném BatchUpdateException hoặc exception được Spring dịch sang DataAccessException, thường có thể là DuplicateKeyException tùy driver và đường gọi.

Các chi tiết cần nhớ:

- Exception có thể được bọc nhiều lớp; kiểm tra root cause và SQLState/vendor code khi cần.
- Update counts có thể cho biết một số statement đã chạy trước khi lỗi xảy ra.
- Không phải driver nào cũng báo chính xác item gây lỗi theo cùng cách.
- Nếu batch nằm trong transaction chunk, rollback sẽ hoàn tác các thay đổi transactional chưa commit.
- Với autocommit hoặc resource ngoài transaction, có thể tồn tại kết quả một phần.

Không giả định một batch lỗi có nghĩa database chưa thực hiện statement nào. Dựa vào transaction và database engine thực tế để bảo vệ tính nhất quán.

## 17. Unique violation có nên skip không?

Duplicate key có thể có hai ý nghĩa khác nhau:

1. Input bị sai hoặc có hai record mâu thuẫn cùng business key.
2. Job đang replay một record đã được ghi thành công trong lần chạy trước, và duplicate chính là dấu hiệu thao tác đã được áp dụng.

Không thể quyết định skip chỉ dựa trên tên DuplicateKeyException. Cần biết constraint nào vi phạm và contract của output.

Ví dụ:

| Tình huống | Xử lý thường phù hợp |
| --- | --- |
| Hai dòng trong cùng file có cùng source key nhưng nội dung khác | Quarantine hoặc fail theo policy |
| Cùng event được gửi lại sau timeout | Idempotent replay hoặc xác nhận đã xử lý |
| Business key đã tồn tại từ batch trước nhưng đây là bản cập nhật mới | UPDATE/upsert theo version hoặc event ID |
| Vi phạm unique constraint không liên quan đến idempotency | Fail và điều tra dữ liệu/schema |

Skip mọi DuplicateKeyException có thể che giấu lỗi thiết kế key hoặc dữ liệu xung đột.

## 18. Insert-if-absent và upsert

Nếu database hỗ trợ, câu SQL có thể xử lý duplicate theo cách nguyên tử:

PostgreSQL:

~~~sql
insert into imported_order
    (source_system, source_order_id, customer_id, total_amount)
values
    (:sourceSystem, :sourceOrderId, :customerId, :totalAmount)
on conflict (source_system, source_order_id) do nothing;
~~~

MySQL:

~~~sql
insert into imported_order
    (source_system, source_order_id, customer_id, total_amount)
values
    (:sourceSystem, :sourceOrderId, :customerId, :totalAmount)
on duplicate key update
    customer_id = values(customer_id),
    total_amount = values(total_amount);
~~~

Đây là cú pháp theo vendor, không phải SQL portable. Hãy chọn hành vi rõ ràng:

- DO NOTHING: giữ hàng hiện tại nếu key đã tồn tại.
- DO UPDATE: cập nhật hàng hiện tại bằng dữ liệu mới.
- MERGE: biểu diễn nhánh matched/unmatched theo dialect database.

Upsert không tự quyết định dữ liệu nào mới hơn hoặc có hợp lệ để ghi đè hay không. Cần điều kiện version, event time hoặc business rule để tránh một event cũ ghi đè trạng thái mới.

## 19. assertUpdates khi dùng DO NOTHING

Với INSERT ... ON CONFLICT DO NOTHING, một item duplicate có thể tạo update count bằng 0 vì database không chèn hàng mới. Nếu JdbcBatchItemWriter bật assertUpdates(true), writer có thể coi kết quả zero-row là lỗi.

Nếu zero update là kết quả được mong đợi cho duplicate replay, có thể cấu hình:

~~~java
.assertUpdates(false)
~~~

Tuy nhiên, tắt assertion cũng có nghĩa writer không phát hiện được các trường hợp zero-row khác có thể là lỗi. Chỉ dùng khi SQL đã được thiết kế để zero-row là kết quả hợp lệ và có kiểm thử xác nhận.

Nếu cần phân biệt inserted, already existed và rejected, có thể dùng câu SQL/returning clause riêng theo database hoặc writer tùy chỉnh ghi nhận kết quả. Không suy ra trạng thái nghiệp vụ chỉ từ việc writer không ném exception.

## 20. Upsert phải bảo vệ dữ liệu mới khỏi dữ liệu cũ

Một upsert đơn giản có thể ghi đè hàng hiện tại dù input mới thực ra cũ hơn:

~~~sql
insert into customer_snapshot
    (customer_id, status, source_version)
values
    (:customerId, :status, :sourceVersion)
on conflict (customer_id)
do update set
    status = excluded.status,
    source_version = excluded.source_version;
~~~

Nếu event version 5 đến sau event version 8, câu SQL trên có thể ghi lùi dữ liệu về version 5.

Có thể thêm điều kiện version:

~~~sql
insert into customer_snapshot
    (customer_id, status, source_version)
values
    (:customerId, :status, :sourceVersion)
on conflict (customer_id)
do update set
    status = excluded.status,
    source_version = excluded.source_version
where excluded.source_version > customer_snapshot.source_version;
~~~

Đây là ví dụ PostgreSQL. Cú pháp và semantics cần điều chỉnh theo database khác. Nếu hai version bằng nhau nhưng payload khác nhau, cần xác định đó là replay hợp lệ hay conflict dữ liệu.

## 21. Chống duplicate ở nhiều lớp

Một thiết kế vững chắc thường có nhiều lớp bảo vệ:

~~~text
Input
  |
  v
Normalize business key
  |
  v
Optional in-memory/chunk dedup
  |
  v
Processor validation
  |
  v
Database writer
  |
  v
Unique constraint / upsert
  |
  v
Persisted output
~~~

Mỗi lớp có mục đích riêng:

- Normalize bảo đảm cùng một key có cùng representation.
- Dedup trong chunk giảm số lần gửi duplicate tới database.
- Validation cung cấp lỗi nghiệp vụ dễ hiểu.
- Unique constraint bảo vệ concurrency và mọi đường ghi.
- Upsert/idempotency xử lý replay theo contract.

Không bỏ unique constraint chỉ vì đã có dedup trong processor. In-memory dedup không thể bảo vệ các process hoặc transaction cạnh tranh.

## 22. Deduplicate trong một chunk

Nếu chunk nhỏ và có duplicate rõ ràng, processor có thể dùng một service hoặc writer adapter để phát hiện trùng trong phạm vi chunk. Tuy nhiên, ItemProcessor chỉ nhận từng item; giữ Set trong field processor sẽ khiến state vượt qua chunk boundary và có thể sai khi retry hoặc multi-threading.

Một cách có chủ đích là deduplicate từ nguồn bằng SQL:

~~~sql
select source_system, source_order_id, customer_id, total_amount
from (
    select s.*,
           row_number() over (
               partition by source_system, source_order_id
               order by source_updated_at desc, source_row_id desc
           ) as rn
    from staging_order s
    where batch_id = :batchId
) ranked
where rn = 1
order by source_system, source_order_id;
~~~

Query này chọn một record theo quy tắc version/time đã xác định. Cần kiểm tra database hỗ trợ window function và quy tắc chọn winner có đúng nghiệp vụ hay không.

Nếu duplicate phải được báo lỗi thay vì chọn winner, query hoặc bước validation cần phát hiện nhóm duplicate và đưa chúng vào quarantine.

## 23. Deduplication qua staging table

Với input lớn, staging table giúp kiểm soát duplicate trước khi ghi bảng nghiệp vụ:

~~~text
Source file
   |
   v
Staging table
   |
   +--> validate source key
   |
   +--> detect duplicate groups
   |
   +--> select accepted records
   |
   v
Target table with unique constraint
~~~

Staging có thể lưu batch ID, source row number, raw key, normalized key và validation status. Sau khi xác định duplicate, job có thể:

- Chấp nhận một record theo quy tắc rõ ràng.
- Từ chối toàn bộ nhóm duplicate.
- Chọn bản có source version mới nhất.
- Lưu nhóm duplicate vào bảng lỗi để operator xử lý.

Staging giúp tái chạy validation mà không phải đọc lại file gốc, nhưng cần retention và cleanup policy để không tích lũy dữ liệu vô hạn.

## 24. Transaction chunk và unique constraint

Trong chunk-oriented step, writer thường chạy trong transaction của chunk:

~~~text
BEGIN CHUNK TRANSACTION
  Read items
  Process items
  INSERT batch into target
  Update checkpoint metadata
COMMIT
~~~

Nếu một insert vi phạm unique constraint và exception làm transaction rollback, các thay đổi transactional của chunk chưa commit sẽ được hoàn tác. Item thuộc chunk có thể được đọc/xử lý lại theo retry hoặc restart policy.

Để bảo đảm business output và checkpoint nhất quán, writer phải dùng datasource/transaction manager được cấu hình phù hợp với step. Nếu output ghi sang datasource khác hoặc autocommit connection riêng, rollback chunk không tự động hoàn tác output đó.

Unique constraint vẫn cần thiết dù transaction rollback đúng. Nó bảo vệ dữ liệu khi một transaction khác hoặc một job execution khác ghi cùng key.

## 25. Restart và duplicate output

Một failure window thường gặp:

~~~text
1. Job đọc item K-100
2. Writer ghi K-100
3. Database commit thành công
4. Process dừng trước khi trạng thái execution/checkpoint được đồng bộ như dự kiến
5. Job được khởi động lại
6. K-100 có thể được gửi lại
~~~

Tính nguyên tử giữa business output và batch metadata phụ thuộc cấu hình JobRepository/transaction manager. Khi chúng không cùng một transaction, không thể chỉ dựa vào checkpoint để bảo đảm item không bị gửi lại.

Unique key theo source identity ngăn tạo hàng thứ hai. Upsert hoặc insert-if-absent giúp replay an toàn nếu đó là contract mong muốn. Với side effect khác database, cần idempotency key hoặc outbox/inbox.

Không khẳng định unique constraint tạo exactly-once processing. Nó bảo đảm uniqueness của hàng theo key; việc xử lý nghiệp vụ, event và các resource khác vẫn cần thiết kế riêng.

## 26. Nhiều job hoặc partition ghi cùng một key

Giả sử hai partition cùng đọc hai file có chung source order ID:

~~~text
Partition A -> INSERT source_order_id = O-100
Partition B -> INSERT source_order_id = O-100
~~~

Một transaction có thể thắng, transaction còn lại nhận unique violation hoặc kết quả upsert tùy SQL. Đây là behavior mong muốn nếu chỉ một hàng được phép tồn tại.

Nếu thứ tự đến quyết định winner, kết quả có thể không xác định khi hai partition chạy đồng thời. Đừng để dữ liệu cuối cùng phụ thuộc worker nào commit trước nếu nghiệp vụ cần quy tắc version hoặc precedence rõ ràng.

Các cách xử lý:

- Partition theo business key để cùng key luôn vào một partition.
- Dùng versioned upsert chỉ chấp nhận bản mới hơn.
- Dùng staging rồi merge theo một quy tắc xác định.
- Dùng lock hoặc serialization khi thực sự cần thứ tự.
- Ghi conflict vào bảng riêng để xử lý sau.

Unique constraint ngăn duplicate row nhưng không quyết định bản ghi nào đúng khi có hai payload khác nhau cho cùng key.

## 27. Retry duplicate key có ích không?

Duplicate key do cùng input thường là lỗi deterministic. Retry cùng item với cùng key sẽ tiếp tục vi phạm constraint. Vì vậy, không cấu hình DuplicateKeyException là transient retry exception một cách mặc định.

Retry có thể phù hợp nếu exception thực tế là deadlock hoặc lỗi kết nối tạm thời. Duplicate key chỉ nên được coi là thành công/replay khi application có thể xác nhận đó là cùng một operation đã áp dụng trước đó.

Ví dụ hai event cùng event ID nhưng payload khác nhau không nên tự động coi là duplicate vô hại. Có thể producer đã tái sử dụng ID sai hoặc dữ liệu bị thay đổi. Cần so sánh checksum/version hoặc lưu payload fingerprint để phát hiện conflict.

## 28. Skip duplicate hay quarantine?

Nếu duplicate là lỗi dữ liệu, có thể cấu hình skip exception sau khi đã xác định chính xác constraint:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(orderWriter)
    .faultTolerant()
    .skip(DuplicateOrderException.class)
    .skipLimit(25)
    .listener(orderSkipListener)
    .build();
~~~

Trong thực tế, JdbcBatchItemWriter có thể phát ra exception JDBC/Spring khác nhau tùy driver và cách batch được thực thi. Nếu chỉ muốn skip một constraint cụ thể, có thể cần adapter phân loại root cause, SQLState/vendor code và tên constraint thành DuplicateOrderException.

Không bắt mọi DuplicateKeyException rồi bỏ qua. Constraint khác có thể đại diện cho dữ liệu sai nghiêm trọng. Nếu record cần được xử lý lại, quarantine phải lưu source key, batch ID, row number và lý do.

## 29. Xác định constraint nào đã vi phạm

Một bảng có thể có nhiều unique constraint:

~~~sql
constraint uk_order_source unique (source_system, source_order_id),
constraint uk_order_number unique (order_number)
~~~

Vi phạm uk_order_source có thể là replay cùng source record. Vi phạm uk_order_number có thể là hai order khác nhau bị cấp cùng số chứng từ. Hai lỗi có thể có chính sách khác nhau.

Thông tin constraint name có thể xuất hiện trong message/vendor exception, nhưng định dạng phụ thuộc database và driver. Không parse message tự do nếu có cách đọc SQLState, vendor code hoặc metadata exception đáng tin cậy hơn.

Nếu cần logic chính xác theo constraint, bọc tầng persistence để chuyển lỗi database thành exception nghiệp vụ có kiểu rõ ràng. Ghi log root cause để operator vẫn có thể điều tra.

## 30. JPA writer và thời điểm constraint được kiểm tra

Với JPA, entity có thể được persist vào persistence context trước khi SQL thực sự chạy. Unique constraint thường được database kiểm tra khi INSERT/UPDATE được flush hoặc transaction commit.

Ví dụ:

~~~java
public class CustomerJpaWriter implements ItemWriter<CustomerImport> {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public void write(Chunk<? extends CustomerImport> chunk) {
        for (CustomerImport item : chunk) {
            entityManager.persist(item);
        }
        entityManager.flush();
    }
}
~~~

flush() đẩy SQL pending xuống database để lỗi constraint có thể xuất hiện trong write phase. Tuy nhiên, transaction vẫn chưa commit chỉ vì flush thành công; constraint deferred (nếu database hỗ trợ và được cấu hình) có thể chỉ được kiểm tra ở commit.

Nếu không flush trong writer, exception có thể xuất hiện muộn hơn ở transaction commit. Khi debug hoặc cấu hình skip, cần hiểu exception phát sinh ở đâu trong lifecycle.

JpaItemWriter hoặc repository có thể có behavior flush/clear riêng theo phiên bản. Kiểm tra implementation/configuration đang dùng và test trên database thật.

## 31. Unique constraint và JPA cascade

Một entity persist có thể cascade sang child entities. Unique constraint có thể nằm ở bảng child, join table hoặc bảng liên kết. Khi persist parent, lỗi có thể phát sinh từ một child record chứ không phải bảng chính.

Ví dụ:

~~~java
@OneToMany(cascade = CascadeType.PERSIST)
private List<OrderLine> lines;
~~~

Nếu hai order cùng chứa một line key duy nhất trong phạm vi invoice, constraint ở order_line có thể bị vi phạm khi flush. Khi đó exception không nhất thiết nói rõ từ item cha nào gây lỗi.

Hãy thiết kế cascade có chủ đích, xác định business key của từng bảng và kiểm tra constraint ở mọi bảng được ghi. Với batch lớn, persist graph phức tạp có thể làm khó xác định record lỗi; cân nhắc DTO/flat output và writer chuyên biệt.

## 32. Unique constraint với soft delete

Nếu bảng dùng soft delete, record cũ vẫn còn trong database:

~~~sql
update customer
set deleted_at = current_timestamp
where customer_id = :customerId;
~~~

Một unique constraint thông thường vẫn tính cả hàng đã soft delete. Vì vậy, không thể insert một hàng mới cùng key nếu constraint áp dụng trên toàn bảng.

Nếu nghiệp vụ cho phép tái sử dụng key sau khi xóa mềm, có thể dùng:

- Partial/filtered unique index chỉ áp dụng cho hàng chưa deleted, nếu database hỗ trợ.
- Một bảng current-state riêng và bảng history riêng.
- Composite key có version hoặc validity range.
- Quy trình restore hàng cũ thay vì insert hàng mới.

Partial/filtered index là tính năng phụ thuộc database. Cần kiểm tra migration, query plan và behavior khi restore record.

## 33. Unique constraint và lịch sử phiên bản

Nếu cần lưu nhiều phiên bản của cùng một entity, không đặt unique constraint chỉ trên business key. Hãy mở rộng key theo version hoặc tách bảng current và history.

Ví dụ:

~~~sql
create table customer_version (
    customer_id varchar(80) not null,
    version_no integer not null,
    customer_name varchar(200) not null,
    effective_from date not null,
    constraint pk_customer_version
        primary key (customer_id, version_no)
);
~~~

Nếu cần bảo đảm chỉ có một version hiện hành, cách thực thi phụ thuộc database và model. Có thể dùng current flag với filtered unique index, hoặc quản lý khoảng hiệu lực bằng transaction/constraint phù hợp.

Không bỏ unique constraint để cho phép duplicate rồi hy vọng ứng dụng tự chọn đúng phiên bản. Hãy biểu diễn version trong schema.

## 34. Unique key trong multi-tenant system

Trong hệ thống multi-tenant, key thường chỉ duy nhất trong tenant:

~~~sql
unique (tenant_id, external_customer_id)
~~~

Nếu chỉ đặt unique(external_customer_id), hai tenant có thể không import được cùng một mã hợp lệ. Ngược lại, nếu bỏ tenant_id khỏi query lookup, processor có thể cập nhật nhầm dữ liệu của tenant khác.

Hãy bảo đảm:

- Tenant ID là một phần của unique key khi contract yêu cầu.
- JobParameters chứa tenant scope và ổn định khi restart.
- Reader, processor, writer đều bind tenant đúng.
- Cache key có tenant ID.
- Integration test thử hai tenant có cùng external ID.

Không lấy tenant ID từ payload không đáng tin cậy nếu job đã được khởi chạy cho một tenant cụ thể. So sánh và từ chối mismatch để tránh cross-tenant write.

## 35. Unique constraint và collation

Database collation quyết định một số phép so sánh chuỗi, bao gồm phân biệt hoa thường hoặc dấu trong nhiều hệ thống. Điều này ảnh hưởng đến uniqueness:

- Collation case-insensitive có thể xem abc và ABC là cùng key.
- Collation case-sensitive có thể xem chúng là hai key khác nhau.
- Một số collation xử lý accent hoặc Unicode normalization theo quy tắc riêng.

Nếu business key phải case-insensitive, cần thống nhất canonicalization và index/collation. Không chỉ gọi toUpperCase() trong một processor nếu các đường ghi khác không áp dụng cùng quy tắc.

Với database hỗ trợ functional index, có thể tạo unique index trên biểu thức chuẩn hóa, ví dụ lower(email). Đây là SQL vendor-specific và cần cân nhắc query phải dùng cùng biểu thức để tận dụng index.

## 36. Batch writer và nhiều constraint

Một INSERT có thể vi phạm nhiều quy tắc khác nhau:

- Primary key duplicate.
- Business key duplicate.
- Foreign key không tồn tại.
- NOT NULL violation.
- CHECK constraint.

Không nên gom tất cả thành “duplicate” hoặc “invalid item”. Phân loại theo constraint và nguyên nhân:

| Constraint | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| Primary key | ID nội bộ trùng | Thường là lỗi nghiêm trọng hoặc ID generation bug |
| Business unique key | Record nghiệp vụ đã tồn tại | Replay/upsert/quarantine theo contract |
| Foreign key | Parent/reference không tồn tại | Enrich/validate, quarantine hoặc fail |
| NOT NULL | Field bắt buộc thiếu | Data validation/skip nếu được phép |
| CHECK | Giá trị vi phạm miền hợp lệ | Business validation hoặc quarantine |

Database constraint là lớp bảo vệ cuối cùng. Processor có thể kiểm tra trước để tạo lỗi dễ hiểu, nhưng constraint vẫn phải tồn tại để bảo vệ race condition và mọi đường ghi.

## 37. Dữ liệu đầu vào duplicate và thứ tự xử lý

Nếu cùng một key xuất hiện nhiều lần trong file với payload khác nhau, phải có quy tắc:

- First wins: giữ bản xuất hiện đầu tiên.
- Last wins: dùng bản xuất hiện cuối cùng.
- Highest version wins: dùng source version lớn nhất.
- Reject all duplicates: đưa mọi record trong nhóm vào quarantine.
- Merge: kết hợp field theo quy tắc domain.

Không để kết quả phụ thuộc chunk size. Nếu first/last wins chỉ được tính trong một chunk, duplicate nằm ở hai chunk khác nhau có thể cho kết quả khác. Cần deduplicate trên toàn batch hoặc dùng staging/query có thứ tự xác định.

Nếu thứ tự input quan trọng, lưu source sequence/row number và dùng nó trong quy tắc winner. Đừng dựa vào thứ tự commit của nhiều partition.

## 38. Tối ưu index cho unique constraint

Unique constraint thường cần index để database kiểm tra uniqueness và hỗ trợ lookup. Cân nhắc:

- Chọn độ dài và kiểu dữ liệu key phù hợp.
- Tránh key quá dài nếu không cần thiết.
- Dùng đúng thứ tự cột theo query pattern.
- Không tạo nhiều index trùng lặp không cần thiết.
- Đánh giá chi phí ghi vì mỗi insert/update phải duy trì index.
- Theo dõi lock contention khi nhiều worker ghi cùng vùng key.

Unique index có thể làm tăng chi phí ghi, nhưng thường là trade-off cần thiết để bảo vệ dữ liệu. Nếu job có throughput cao, đo execution plan và lock wait thay vì bỏ constraint để tăng tốc.

## 39. Xử lý migration khi bảng đã có duplicate

Trước khi thêm unique constraint vào bảng lớn:

1. Chạy query phát hiện duplicate theo key dự kiến.
2. Xác định nguyên nhân và quy tắc giữ/merge dữ liệu.
3. Lập kế hoạch xử lý foreign key và bảng phụ thuộc.
4. Đánh giá lock và thời gian tạo index trên bảng lớn.
5. Triển khai migration phù hợp với khả năng online index của database.
6. Xác nhận constraint tồn tại sau migration.
7. Chạy test writer với duplicate để xác nhận lỗi được nhận diện.

Một số database hỗ trợ tạo index online/concurrently với giới hạn riêng. Không giả định DDL giống nhau giữa các vendor. Với bảng lớn, migration có thể cần giai đoạn cleanup, tạo index, rồi gắn constraint theo quy trình được database hỗ trợ.

Không chỉ thêm annotation trong entity rồi chờ Hibernate tự thay đổi schema production.

## 40. Kiểm thử unique constraint bằng database thật

Unit test mock repository không chứng minh unique constraint tồn tại. Cần integration test với database engine tương thích production, ví dụ Testcontainers.

Các test cơ bản:

- Insert key lần đầu thành công.
- Insert cùng key lần thứ hai bị từ chối hoặc được xử lý theo upsert.
- Hai cột trong composite key có cùng giá trị nhưng tenant khác nhau được chấp nhận nếu contract cho phép.
- Cùng tenant/source/key bị từ chối.
- NULL và empty string tuân theo policy.
- Case normalization và collation cho kết quả mong đợi.
- Soft-deleted row có/không chặn key mới theo schema.

H2 có thể dùng cho một số test SQL portable, nhưng không thay thế test trên database production khi dùng partial index, upsert, collation hoặc semantics riêng của driver.

## 41. Kiểm thử duplicate trong cùng chunk

Tạo input chứa hai item cùng idempotency key:

~~~java
Chunk<ImportedOrder> chunk = new Chunk<>(List.of(
    order("SRC-A", "O-100"),
    order("SRC-A", "O-101"),
    order("SRC-A", "O-100")
));
~~~

Với INSERT thông thường và unique constraint, test cần xác nhận:

- Writer ném exception phù hợp khi gặp duplicate.
- Transaction chunk rollback theo cấu hình.
- Không còn hàng của chunk chưa commit nếu transaction rollback.
- Skip/quarantine behavior đúng nếu step được cấu hình fault tolerant.

Kết quả cụ thể khi batch statement thất bại phụ thuộc driver/database. Hãy kiểm tra bảng sau khi transaction hoàn tất, không chỉ assert exception type.

## 42. Kiểm thử duplicate qua hai chunk

Duplicate có thể nằm ở hai chunk khác nhau:

~~~text
Chunk 1: O-100, O-101 -> COMMIT
Chunk 2: O-100, O-102 -> duplicate O-100
~~~

Một Set cục bộ trong processor có thể phát hiện duplicate nếu nó giữ state toàn step, nhưng cách đó khó restart và concurrency. Unique constraint vẫn phải bắt được duplicate giữa các chunk.

Integration test cần chạy step với chunk size nhỏ để ép duplicate sang chunk tiếp theo. Xác nhận chunk đầu vẫn tồn tại, chunk thứ hai được rollback/skip theo policy và không có duplicate row.

## 43. Kiểm thử restart và idempotent replay

Một restart test nên mô phỏng item đã ghi thành công rồi được gửi lại:

1. Chạy job với một batch có source record ID ổn định.
2. Commit một hoặc nhiều chunk.
3. Làm job dừng ở một failure point có thể dẫn đến replay.
4. Restart cùng JobInstance.
5. Xác nhận unique key ngăn hàng trùng hoặc upsert giữ trạng thái đúng.
6. Kiểm tra count và payload của từng business key.

Test nên phân biệt replay cùng payload với cùng key nhưng payload khác. Replay cùng payload có thể là no-op hợp lệ; payload khác có thể là conflict cần quarantine hoặc version check.

Đừng chỉ assert tổng row count nếu bảng có thể chứa record khác từ batch trước. Query theo batch ID/source key để xác nhận chính xác.

## 44. Kiểm thử concurrency và race condition

Để xác nhận unique constraint bảo vệ hai writer đồng thời:

1. Chuẩn bị hai transaction hoặc hai job worker.
2. Cùng cố gắng insert một key.
3. Điều phối để cả hai cùng bắt đầu gần nhau.
4. Xác nhận database chỉ lưu một hàng cho key đó.
5. Xác định worker thua nhận duplicate/upsert result theo thiết kế.

Test concurrency cần dùng database thật và synchronization barrier phù hợp; test tuần tự không chứng minh race condition đã được bảo vệ.

Nếu ứng dụng dùng nhiều datasource hoặc nhiều database instance, constraint chỉ bảo vệ trong database/schema nơi nó tồn tại. Không có unique constraint xuyên nhiều database độc lập.

## 45. Kiểm thử JPA flush và constraint timing

Với JPA writer, test cả hai thời điểm:

- Khi gọi persist/merge.
- Khi flush hoặc transaction commit.

Ví dụ:

~~~java
assertThatThrownBy(() -> {
    writer.write(new Chunk<>(List.of(first, duplicate)));
    entityManager.flush();
}).isInstanceOf(PersistenceException.class);
~~~

Exception cụ thể có thể được wrap bởi Hibernate/Spring. Test nên xác định root cause và xác nhận database không chứa duplicate sau rollback.

Không giữ transaction test bên ngoài nếu nó làm sai lệch transaction chunk hoặc che giấu commit/rollback. Tạo fixture và kiểm tra dữ liệu bằng transaction rõ ràng.

## 46. Theo dõi duplicate và conflict trong production

Metrics nên phân biệt:

- Số item insert thành công.
- Số replay đã tồn tại và được xử lý như no-op.
- Số business key conflict.
- Số unique violation theo constraint.
- Số retry, skip và quarantine.
- Số upsert update so với insert nếu database cung cấp thông tin.
- Số lỗi constraint khác như foreign key, NOT NULL hoặc CHECK.

Log cần có job execution ID, step execution ID, source batch ID, business key và tên constraint nếu xác định được. Không log toàn bộ payload nhạy cảm.

Một tỷ lệ duplicate tăng đột ngột có thể cho thấy producer gửi lại file, scheduler chạy trùng, checkpoint không đồng bộ hoặc partition bị overlap. Alert giúp tìm nguyên nhân thay vì chỉ tăng skip limit.

## 47. Những lỗi thường gặp khi dùng unique constraint trong batch

**Chỉ dùng Set trong Java để chống duplicate:** không bảo vệ nhiều process hoặc restart. Giữ unique constraint trong database.

**Chọn sai business key:** key quá rộng hoặc quá hẹp gây chặn record hợp lệ hoặc cho phép duplicate. Xác định contract trước khi tạo constraint.

**Quên tenant/source system trong composite key:** hai nguồn có thể dùng cùng external ID. Đưa scope vào key nếu nghiệp vụ yêu cầu.

**Giả định NULL có cùng behavior ở mọi database:** kiểm tra engine và dùng NOT NULL khi key bắt buộc.

**Dùng SELECT rồi INSERT làm hàng rào:** có race condition. Dùng constraint và upsert/insert-if-absent phù hợp.

**Skip mọi DuplicateKeyException:** có thể che lỗi constraint khác hoặc payload conflict. Xác định constraint và ý nghĩa nghiệp vụ.

**Retry duplicate key:** cùng input thường tiếp tục lỗi. Chỉ retry lỗi transient; xử lý replay bằng idempotency.

**Tắt assertUpdates để bỏ qua lỗi:** zero-row update có thể che business key sai. Chỉ tắt khi zero-row là kết quả được thiết kế.

**Cho rằng unique constraint tạo exactly-once:** nó chỉ bảo vệ uniqueness theo key. Remote side effect và nhiều datasource cần idempotency/outbox riêng.

**Upsert không kiểm tra version:** event cũ có thể ghi đè dữ liệu mới. Thêm source version/effective time vào rule update.

**Thêm constraint khi bảng đã có duplicate:** migration có thể thất bại hoặc yêu cầu cleanup. Kiểm tra dữ liệu trước khi deploy.

**Dùng annotation thay migration:** schema production có thể không có constraint. Quản lý DDL bằng migration và xác minh sau deploy.

**Không test với database production:** H2 có thể khác về NULL, collation, upsert, update count và error behavior. Dùng engine thật cho test phụ thuộc vendor.

**Để kết quả phụ thuộc worker thắng race:** cùng key với payload khác có thể cho output không xác định. Dùng version/precedence rule hoặc quarantine conflict.

## 48. Quy trình thiết kế database output có unique constraint

Trước tiên, xác định business key và idempotency key riêng biệt. Quyết định phạm vi duy nhất: toàn hệ thống, theo tenant, theo source system, theo batch hay theo version. Chuẩn hóa representation của key và xác định NULL, case sensitivity, soft delete và version semantics.

Tiếp theo, triển khai primary key, unique constraint, NOT NULL và index bằng migration. Kiểm tra duplicate hiện có trước khi thêm constraint. Trong writer, dùng prepared/named parameters và chọn INSERT, upsert hoặc insert-if-absent theo contract. Không dựa vào SELECT-before-INSERT để chống race. Phân loại duplicate replay khác với dữ liệu xung đột; retry chỉ cho lỗi tạm thời và skip/quarantine chỉ khi nghiệp vụ cho phép.

Cuối cùng, kiểm thử database thật với duplicate trong cùng chunk, giữa các chunk, qua restart và giữa hai transaction đồng thời. Kiểm tra transaction rollback, update count, JPA flush timing và behavior của đúng driver. Theo dõi duplicate/conflict theo constraint trong production và giữ quy trình xử lý record quarantine để có thể reprocess.

Database output và unique constraint là nền tảng để batch job ghi dữ liệu nhất quán khi input có duplicate, job restart hoặc nhiều worker cạnh tranh. Unique constraint bảo vệ quy tắc dữ liệu ở database; writer và transaction xác định cách lỗi được xử lý; idempotency key và upsert giúp replay an toàn theo contract. Khi business key được chọn đúng, schema được quản lý bằng migration và các failure window được kiểm thử trên database thật, batch có thể chạy lại mà không tạo dữ liệu trùng hoặc ghi đè sai kết quả.
