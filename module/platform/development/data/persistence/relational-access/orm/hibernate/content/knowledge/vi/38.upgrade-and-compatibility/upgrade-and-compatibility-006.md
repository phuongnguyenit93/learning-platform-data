# Kiểm tra chiến lược sinh định danh, sequence và naming strategy trong Hibernate ORM

## 1. Vì sao nâng cấp Hibernate có thể làm lộ lỗi định danh và tên database?

Một entity dùng khóa chính tự tăng:

~~~java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.AUTO)
    private Long id;
}
~~~

Ứng dụng chạy nhiều năm trên PostgreSQL. Khi nâng cấp Spring Boot/Hibernate, môi trường test tạo ra một sequence mới có tên khác; môi trường production lại đã có sequence cũ, allocation size khác với cấu hình entity. Một migration không đồng bộ sequence state, nên INSERT tiếp theo đụng primary key đã tồn tại.

Một vấn đề khác: entity khai báo `purchaseOrder`, `createdAt`, nhưng schema production đang dùng `purchase_order`, `created_at`. Sau khi thay Spring Boot hoặc naming strategy, Hibernate có thể tìm tên khác, tạo DDL khác hoặc không validate được schema cũ.

Những lỗi này thường không nằm trong business method. Chúng xuất hiện ở ranh giới giữa:

- Chiến lược sinh identifier của JPA/Hibernate.
- Cơ chế IDENTITY, SEQUENCE, TABLE hoặc UUID của database.
- Optimizer và allocation size mà Hibernate dùng để giảm số lần gọi sequence.
- Tên generator logic trong mapping.
- Tên sequence/table vật lý trong database.
- Implicit naming strategy và physical naming strategy.
- Schema/migration đã tồn tại từ những phiên bản ứng dụng trước.

Khi nâng cấp, cần kiểm tra các thành phần đó như một hợp đồng tương thích dữ liệu. **Không đổi generator hoặc naming strategy chỉ vì cấu hình mới trông gọn hơn**; phải biết schema cũ, dữ liệu cũ và mọi writer đang sử dụng sequence/table nào.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt identifier của entity với business key và public identifier.
2. So sánh IDENTITY, SEQUENCE, TABLE, UUID và assigned identifiers.
3. Hiểu cách `allocationSize`, sequence increment và Hibernate optimizers liên hệ với nhau.
4. Nhận diện gaps trong sequence và lý do không dùng sequence cho số nghiệp vụ gapless.
5. Kiểm tra `GenerationType.AUTO` khi dialect hoặc Hibernate version thay đổi.
6. Phân biệt generator name, database sequence name và physical identifier.
7. Hiểu vai trò của implicit và physical naming strategies.
8. Kiểm tra quoted identifiers, case folding, schema/catalog và reserved words.
9. Lập migration an toàn khi đổi generator, sequence hoặc naming strategy.
10. Xác minh generated IDs, sequence state và SQL thực tế bằng database độc lập.
11. Dùng Testcontainers để kiểm thử đúng database production.
12. Xây dựng upgrade tests phát hiện schema drift trước khi deploy.

Ví dụ dùng Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Boot 3.x, Spring Data JPA và PostgreSQL. Một số chi tiết generator/naming thay đổi theo Hibernate version và dialect; khi nâng cấp cần đối chiếu đúng phiên bản đích thay vì giả định mọi version có cùng defaults.

## 2. Identifier, business key và public ID là ba khái niệm khác nhau

Một bảng Order có thể có:

| Trường | Mục đích | Ví dụ |
|---|---|---|
| Primary key | Định danh row/entity trong database | `id = 901` |
| Business key | Mã nghiệp vụ người dùng nhận diện | `SO-2026-00042` |
| Public identifier | ID đưa ra API, khó đoán hoặc ổn định ngoài hệ thống | UUID |
| Organization scope | Namespace sở hữu dữ liệu | `organization_id = 7` |

### 2.1. Primary key nên ổn định

ID của entity thường không đổi trong suốt vòng đời row. Nó được dùng bởi foreign keys, persistence context, cache và các integration nội bộ.

### 2.2. Business key có quy tắc riêng

Số hóa đơn hoặc mã đơn hàng có thể cần:

- Unique theo organization.
- Unique theo năm tài chính.
- Có prefix theo cửa hàng.
- Có thể thay đổi khi sửa dữ liệu legacy.
- Có yêu cầu pháp lý về trình tự.

Không mặc định `@GeneratedValue` trên primary key cũng là cơ chế cấp business number.

### 2.3. UUID không tự bảo vệ authorization

Một UUID khó đoán có thể hữu ích làm public ID, nhưng server vẫn phải kiểm tra người dùng có quyền truy cập row. Identifier strategy không thay thế tenant/organization authorization.

### 2.4. Không dùng MAX(id) + 1

~~~sql
SELECT MAX(id) + 1 FROM purchase_orders;
~~~

không phải một generator an toàn. Hai transactions có thể cùng đọc một MAX rồi cùng chọn ID; concurrency sẽ tạo duplicate hoặc race. Dùng identity/sequence, UUID hoặc một cơ chế cấp số có locking/atomic update được thiết kế riêng.

## 3. Các chiến lược sinh ID của Jakarta Persistence

JPA cung cấp các giá trị chính của `GenerationType`:

| Strategy | Cơ chế | Phù hợp khi |
|---|---|---|
| `IDENTITY` | Database sinh ID khi INSERT qua identity/auto-increment column | DB hỗ trợ identity; cần generated key trực tiếp |
| `SEQUENCE` | Lấy ID từ database sequence trước/độc lập với INSERT | Database có sequence; cần tối ưu allocation/batching |
| `TABLE` | Dùng một bảng để lưu/cấp các giá trị định danh | Cần generator table-based hoặc DB không có sequence/identity phù hợp |
| `UUID` | Sinh UUID theo provider/JPA support | Muốn ID phân tán, không cần round trip để lấy numeric key |
| `AUTO` | Provider chọn chiến lược phù hợp theo kiểu ID/dialect/provider | Muốn provider quyết định, chấp nhận phụ thuộc version/dialect |

Jakarta Persistence 3.1 bổ sung `GenerationType.UUID`; dự án cũ hoặc provider cũ có thể không hỗ trợ annotation/enum này. Hibernate cũng có các extension generator riêng. Kiểm tra phiên bản Jakarta Persistence và Hibernate thực tế.

### 3.1. AUTO không phải một hợp đồng database cố định

`AUTO` yêu cầu provider chọn chiến lược. Kết quả có thể phụ thuộc:

- Kiểu Java của identifier.
- Database dialect.
- Khả năng sequence/identity của database.
- Hibernate version.
- Cấu hình generator/naming.

Nếu schema production cần một sequence tên cụ thể và allocation size cụ thể, khai báo `SEQUENCE` rõ ràng thường dễ kiểm soát hơn `AUTO`.

### 3.2. Không suy ra AUTO luôn là IDENTITY

Một ứng dụng chuyển từ H2 sang PostgreSQL có thể thấy DDL/generator khác dù entity annotation không đổi. Vì vậy phải kiểm tra SQL, schema và generator thực tế của từng database.

### 3.3. AUTO có thể tiện cho demo, nhưng nâng cấp cần kiểm chứng

Khi đổi Hibernate version, đừng chỉ chạy unit tests rồi deploy. Hãy kiểm tra DDL, sequence names, optimizer, generated values và migration path trên database production.

## 4. IDENTITY: database sinh ID tại INSERT

Mapping:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
~~~

PostgreSQL DDL minh họa:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(50) NOT NULL
);
~~~

Database tạo giá trị khi INSERT; JDBC driver/Hibernate lấy generated key để gán lại cho entity.

### 4.1. Ưu điểm

- Mapping đơn giản.
- Database quản lý việc cấp ID.
- Không cần khai báo sequence riêng trong entity.
- Dễ tương thích với các schema auto-increment/identity hiện có nếu mapping đúng.

### 4.2. Chi phí

- Hibernate thường phải thực hiện INSERT sớm để biết ID.
- Có thể hạn chế JDBC batching INSERT cho entities dùng IDENTITY.
- Không có sẵn dải ID để gán trước khi INSERT.
- Hành vi DDL/identity syntax phụ thuộc database.

### 4.3. Identity và flush timing

Với IDENTITY, Hibernate thường cần INSERT để lấy generated ID. Do đó SQL có thể được phát sớm hơn so với một số generator khác. Không dựa vào giả định “persist luôn chưa gửi SQL cho tới commit”.

### 4.4. JDBC batching

`hibernate.jdbc.batch_size` hữu ích cho nhiều INSERT/UPDATE trong các trường hợp hỗ trợ. Tuy nhiên IDENTITY generation thường ngăn Hibernate gom các INSERT theo cách batching thông thường vì mỗi INSERT cần generated key. Nếu write throughput lớn, so sánh SEQUENCE với pooled optimizer trên database hỗ trợ sequence.

### 4.5. Identity không bảo đảm ID liên tiếp

Rollback, concurrent inserts và engine implementation có thể tạo gaps. Không assert IDs 1,2,3 liên tiếp trong test.

## 5. SEQUENCE: lấy ID từ database sequence

Mapping:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_id_gen"
    )
    @SequenceGenerator(
        name = "purchase_order_id_gen",
        sequenceName = "purchase_order_seq",
        allocationSize = 50
    )
    private Long id;
}
~~~

Sequence database:

~~~sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1
    INCREMENT BY 50;
~~~

DDL thực tế phải khớp chiến lược optimizer và Hibernate version. Ví dụ trên minh họa cấu hình allocation block 50; không copy `INCREMENT BY 50` nếu provider/generator được cấu hình theo cách khác.

### 5.1. Generator name khác sequenceName

Trong:

~~~java
@SequenceGenerator(
    name = "purchase_order_id_gen",
    sequenceName = "purchase_order_seq"
)
~~~

- `name`: tên generator logic được tham chiếu từ `@GeneratedValue(generator=...)`.
- `sequenceName`: tên database sequence mà generator sử dụng.

Hai tên này không bắt buộc giống nhau. `name` thuộc metadata JPA; `sequenceName` là tên đối tượng database, còn có thể chịu ảnh hưởng của schema/catalog và naming rules/provider.

### 5.2. Sequence cấp ID trước INSERT

Hibernate có thể gọi `nextval` trước khi INSERT row. Entity có thể nhận ID trước flush, tùy generator/optimizer.

### 5.3. Lợi ích

- Có thể lấy trước ID và gom INSERT bằng JDBC batching trong các trường hợp hỗ trợ.
- Hỗ trợ allocation/optimizer giảm số lần gọi sequence.
- Tách việc cấp ID khỏi thao tác INSERT.
- Phù hợp với database như PostgreSQL, Oracle và các hệ thống có sequence.

### 5.4. Sequence không phải business counter gapless

Sequence thường không rollback giá trị đã cấp. Một transaction lấy nextval rồi rollback vẫn có thể làm mất số đó. Optimizer còn có thể cấp trước một block rồi ứng dụng restart, tạo gaps.

## 6. allocationSize và sequence increment

`allocationSize` mô tả số identifier mà provider có thể phân bổ từ một lần lấy giá trị sequence theo cơ chế generator/optimizer.

~~~java
@SequenceGenerator(
    name = "order_id_gen",
    sequenceName = "purchase_order_seq",
    allocationSize = 50
)
~~~

### 6.1. Vì sao cần allocation?

Nếu mỗi entity đều gọi database sequence một lần, một batch 10.000 rows có thể tạo nhiều round trips tới sequence. Pooled optimizers lấy một block và cấp các ID trong block ở phía ứng dụng.

### 6.2. Khái niệm pooled allocation

Giả sử block size là 50. Thay vì yêu cầu database cho mỗi entity, Hibernate lấy một giá trị sequence dùng làm mốc theo optimizer rồi cấp một dải IDs trong block. Cách diễn giải chính xác mốc đầu/cuối phụ thuộc optimizer (pooled hay pooled-lo) và initial value.

Không suy ra rằng giá trị `nextval` chính là ID đầu tiên trong block. Hãy xem SQL/optimizer của Hibernate version đang chạy.

### 6.3. Sequence INCREMENT BY phải phù hợp

Với pooled optimizer, sequence increment thường cần khớp allocation size theo generator contract. Nếu annotation khai báo 50 nhưng database sequence increment 1, Hibernate có thể báo mismatch, điều chỉnh theo mismatch strategy hoặc tạo nguy cơ phân bổ không đúng nếu cấu hình sai.

### 6.4. Không tùy tiện đổi allocationSize khi hệ thống đang chạy

Nếu phiên bản ứng dụng A dùng block 50 và phiên bản B chuyển sang 1, các instances có thể cùng dùng một sequence với assumptions khác nhau. Rolling deployment trong giai đoạn hai version cùng chạy cần tương thích generator; thay đổi này phải có kế hoạch migration và rollout.

### 6.5. Tên mismatch strategy

Hibernate có cấu hình liên quan sequence increment size mismatch như `hibernate.id.sequence.increment_size_mismatch_strategy` ở các phiên bản hỗ trợ. Các lựa chọn và default có thể thay đổi theo version; kiểm tra tài liệu/provider config của phiên bản đích. Trong production, ưu tiên làm schema sequence khớp generator contract và dùng log/exception để phát hiện mismatch thay vì dựa vào auto-fix không được kiểm soát.

## 7. Pooled và pooled-lo optimizers

Hibernate có nhiều optimizer cho sequence generators. Hai tên thường gặp:

- `pooled`
- `pooled-lo`

Cả hai đều giảm số lần gọi database sequence bằng cách cấp một nhóm IDs cho mỗi lần lấy sequence value, nhưng khác cách diễn giải sequence value và biên allocation.

### 7.1. Vì sao optimizer là chi tiết quan trọng khi nâng cấp?

Hai application instances có thể chạy đồng thời. Nếu mỗi instance tự cấp IDs trong block, các blocks phải không chồng nhau. Sequence increment và optimizer phải thống nhất để bảo đảm uniqueness giữa:

- Nhiều threads trong một JVM.
- Nhiều application instances.
- Nhiều pods/servers.
- Phiên bản ứng dụng cũ và mới trong rolling deployment.

### 7.2. Không tự tính block bằng ví dụ đơn giản

Các ví dụ hi-lo thường có cách dùng high/low khác nhau. Không viết script migration giả định “nextval * allocationSize” nếu chưa biết optimizer thực tế.

### 7.3. Restart có thể làm mất phần block chưa dùng

Nếu instance đã lấy một block 50 nhưng chỉ dùng 3 IDs rồi restart, các IDs còn lại có thể không bao giờ được cấp. Gaps là bình thường.

### 7.4. Sequence values không nhất thiết tăng đúng một

Khi database sequence increment bằng allocation block, các giá trị nextval quan sát được có thể nhảy theo block. Không dùng sequence state để tính “số rows đã tạo”.

### 7.5. Kiểm tra optimizer qua SQL/log

Trong test/diagnostic:

- Bật SQL logging để xem sequence calls.
- Xác định Hibernate version và generator metadata.
- Kiểm tra database sequence increment.
- Tạo nhiều entities qua nhiều transactions.
- Chạy nhiều application instances nếu cần xác minh concurrency.

Không chỉ nhìn annotation allocationSize rồi kết luận runtime optimizer.

## 8. Initial value, start value và trạng thái sequence

`@SequenceGenerator` có `initialValue` và `allocationSize`. Database sequence cũng có START WITH và INCREMENT BY.

~~~java
@SequenceGenerator(
    name = "order_id_gen",
    sequenceName = "purchase_order_seq",
    initialValue = 1,
    allocationSize = 50
)
~~~

### 8.1. Initial value không phải sequence hiện tại

Initial value mô tả giá trị khởi đầu khi generator/schema được tạo theo metadata. Nếu sequence production đã tồn tại, thay đổi annotation không tự đưa sequence hiện tại về initial value.

### 8.2. Migration không nên reset sequence một cách mù quáng

Nếu bảng có IDs đến 50000 mà sequence được reset về 1, INSERT mới có thể va chạm primary key. Cần đồng bộ sequence state với dữ liệu thực và optimizer.

### 8.3. PostgreSQL setval

Với một sequence đơn giản increment 1, ví dụ:

~~~sql
SELECT setval(
    'purchase_order_seq',
    COALESCE((SELECT MAX(id) FROM purchase_orders), 1),
    EXISTS (SELECT 1 FROM purchase_orders)
);
~~~

Nếu bảng rỗng, is_called=false khiến lần nextval tiếp theo trả start value theo sequence; nếu có rows, sequence được đánh dấu đã gọi ở max(id), lần tiếp theo sẽ tiến theo increment. Đây là ví dụ PostgreSQL cho sequence đơn giản, không phải công thức an toàn cho mọi pooled optimizer/allocation size.

### 8.4. Pooled sequence cần đồng bộ theo optimizer

Với allocationSize lớn hơn 1, việc setval phải xét cách Hibernate diễn giải high/low và increment. Có thể cần sequence value nằm đúng block boundary theo generator contract. Không chạy công thức MAX(id) chung cho mọi hệ thống trước khi xác minh optimizer/version.

### 8.5. Sequence có thể được dùng chung nhiều bảng

Nếu một sequence cấp IDs cho nhiều entity tables, khi đồng bộ cần xét MAX across all participating tables, không chỉ MAX của một bảng. Tốt hơn là xác định rõ sequence ownership và migration.

## 9. Một sequence riêng cho mỗi entity hay sequence dùng chung?

### 9.1. Sequence riêng

~~~java
@SequenceGenerator(
    name = "purchase_order_gen",
    sequenceName = "purchase_order_seq",
    allocationSize = 50
)
~~~

~~~java
@SequenceGenerator(
    name = "customer_gen",
    sequenceName = "customer_seq",
    allocationSize = 50
)
~~~

Ưu điểm:

- Tên dễ hiểu, dễ kiểm tra ownership.
- Có thể điều chỉnh generator theo entity.
- Dễ đồng bộ sequence state với bảng tương ứng.

Chi phí là nhiều database objects và migrations hơn.

### 9.2. Sequence dùng chung

Nhiều entity có thể cùng dùng một sequence nếu ID uniqueness toàn hệ thống được mong muốn. Khi đó một ID có thể thuộc Order hoặc Customer; loại entity vẫn cần xác định riêng.

Ưu điểm là ít sequence objects. Nhược điểm là sequence state không ánh xạ trực tiếp với MAX(id) của một bảng; migration/diagnostics phải biết tất cả consumers.

### 9.3. Không chia sẻ sequence chỉ để tránh khai báo

Sequence chung có thể làm ID ranges khó đọc và migration phức tạp. Chọn theo yêu cầu global identity, schema ownership và vận hành.

### 9.4. Không dùng sequence name logic làm business API

Tên sequence là chi tiết persistence. Consumer bên ngoài không nên gọi trực tiếp sequence để lấy Order number nếu generator contract thuộc Hibernate.

## 10. TABLE generator

JPA:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.TABLE,
    generator = "order_table_gen"
)
@TableGenerator(
    name = "order_table_gen",
    table = "id_generator",
    pkColumnName = "generator_name",
    valueColumnName = "next_value",
    pkColumnValue = "purchase_order",
    allocationSize = 50
)
private Long id;
~~~

Bảng generator minh họa:

~~~sql
CREATE TABLE id_generator (
    generator_name VARCHAR(100) PRIMARY KEY,
    next_value BIGINT NOT NULL
);
~~~

### 10.1. Cách hoạt động

Provider đọc/cập nhật một row trong bảng generator để cấp IDs. Row locking hoặc atomic update bảo vệ việc cấp số giữa các transactions.

### 10.2. Ưu điểm

- Không cần database sequence/identity.
- Có thể hoạt động trên nhiều database hỗ trợ table locking/update semantics.
- Allocation size có thể giảm số lần truy cập bảng generator.

### 10.3. Nhược điểm

- Có thể tạo contention trên generator row/table.
- Cần index/PK và locking đúng.
- Dễ thành bottleneck khi ghi nhiều.
- Migration/initial row data phải chính xác.

### 10.4. Kiểm tra row generator

~~~sql
SELECT generator_name, next_value
FROM id_generator
WHERE generator_name = 'purchase_order';
~~~

Test nên tạo nhiều IDs và xác minh uniqueness/concurrency trên database đích. Không chỉ assert một entity có ID.

## 11. UUID identifiers

Jakarta Persistence 3.1 có:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
private UUID id;
~~~

Hibernate cũng hỗ trợ:

~~~java
@Id
@UuidGenerator
private UUID id;
~~~

### 11.1. Ưu điểm

- Sinh ID mà không cần round trip sequence để lấy numeric key.
- Có thể tạo ID ở nhiều application instances mà không cần một sequence chung.
- Hữu ích cho distributed writes, offline creation hoặc public identifiers.

### 11.2. Chi phí

- UUID thường rộng hơn BIGINT.
- Index/FK có thể lớn hơn.
- Random UUID có thể gây locality/write amplification trên một số index structures.
- Cách lưu UUID (native UUID, binary, char) ảnh hưởng kích thước và driver mapping.

### 11.3. UUID generator style

Hibernate `@UuidGenerator` có các styles tùy version, ví dụ RANDOM và TIME. Kiểm tra API version và database mapping; không giả định mọi Hibernate version tạo cùng UUID version/ordering.

### 11.4. UUID native type và representation

PostgreSQL có native `uuid`. Một database khác có thể lưu UUID dưới dạng binary hoặc character. Migration và native SQL cần dùng đúng type/cast.

### 11.5. UUID có thể được tạo trước persist

Nếu ID được tạo ở application, entity có thể có identifier ngay khi new. Spring Data `save()` quyết định persist/merge theo entity new-detection strategy; với assigned/generated UUID cần kiểm tra cách nhận diện new state/version.

### 11.6. UUID không thay business number

UI/hoá đơn vẫn có thể cần số đơn SO-2026-00042. UUID là identifier kỹ thuật, business number có quy tắc cấp riêng.

## 12. Assigned identifiers và composite identifiers

Một số hệ thống import ID từ legacy:

~~~java
@Id
private Long id;
~~~

Không có `@GeneratedValue`; ứng dụng gán ID trước khi persist.

### 12.1. Khi phù hợp

- ID đến từ hệ thống nguồn có contract ổn định.
- Composite key là một phần tự nhiên của domain.
- Data migration cần giữ ID cũ.
- ID được sinh bởi một service phân tán riêng.

### 12.2. Rủi ro

- Duplicate IDs nếu source không bảo đảm uniqueness.
- Spring Data new detection có thể coi entity có ID là existing và gọi merge.
- Không có database generator tự bảo vệ nếu app gán trùng.
- Cần kiểm tra sequence state nếu import vào bảng vẫn dùng sequence cho rows mới.

### 12.3. Persistable.isNew

Spring Data JPA cho phép entity implement `Persistable<ID>` để điều khiển new detection. Dùng khi ID được gán trước persist và default detection không phù hợp; cần quản lý flag new/persisted đúng lifecycle.

### 12.4. Composite ID

JPA hỗ trợ `@EmbeddedId` và `@IdClass`. Composite identifier thường không dùng một generated value đơn giản như IDENTITY trên toàn bộ key; thành phần key và association mapping cần được thiết kế rõ.

### 12.5. @MapsId

`@MapsId` dùng khi association đóng góp một phần/toàn bộ derived identifier, ví dụ child share parent key. Khi nâng cấp Hibernate, kiểm tra insert order, referenced columns và column ownership bằng integration tests.

## 13. Sequence và JDBC insert batching

Một batch tạo nhiều Orders:

~~~java
for (int i = 0; i < 1000; i++) {
    entityManager.persist(new PurchaseOrder(...));
}
entityManager.flush();
~~~

### 13.1. Với IDENTITY

Hibernate cần generated key từ database sau INSERT; điều này thường hạn chế batching INSERT theo cơ chế Hibernate/JDBC thông thường.

### 13.2. Với SEQUENCE

Hibernate có thể cấp ID trước, sau đó gom INSERT statements theo:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
~~~

### 13.3. Batch size không phải allocationSize

| Cấu hình | Mục đích |
|---|---|
| `allocationSize` | Số IDs được phân bổ theo generator/optimizer block |
| `hibernate.jdbc.batch_size` | Số JDBC statements có thể gom trong batch |
| `hibernate.default_batch_fetch_size` | Gom lazy SELECT loads |

Ba cấu hình này không thay thế nhau.

### 13.4. Sequence preallocation và insert batch phối hợp

Một ứng dụng có thể lấy một block IDs rồi gửi INSERT theo JDBC batch. Nếu transaction rollback, block/sequence values vẫn có thể bị tiêu thụ. Đó là trade-off giữa throughput và contiguous IDs.

### 13.5. Đo hiệu năng thật

So sánh IDENTITY và SEQUENCE bằng cùng database, cùng số rows, cùng batch size, cùng network/transaction settings. Không suy ra từ H2 vì engine/driver có thể khác.

## 14. AUTO và thay đổi dialect khi nâng cấp

Entity:

~~~java
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
~~~

Khi database hoặc dialect thay đổi:

- Provider có thể chọn generator khác.
- DDL mới có thể yêu cầu sequence/table khác.
- SQL INSERT có thể thay đổi.
- Optimizer/allocation size có thể khác.
- Schema cũ có thể không có database object mà mapping mới mong đợi.

### 14.1. AUTO làm tăng tính phụ thuộc provider

JPA để provider quyết định. Đây có thể là tiện ích, nhưng không phải hợp đồng schema độc lập với Hibernate.

### 14.2. Khi cần ổn định schema, khai báo rõ

~~~java
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "purchase_order_id_gen"
)
~~~

và `@SequenceGenerator` với tên sequence/schema/allocation size rõ.

### 14.3. Nhưng explicit SEQUENCE cũng cần migration

Annotation không tự bảo đảm sequence production tồn tại, increment đúng hoặc state lớn hơn IDs đã import. DDL/migration và runtime test vẫn cần thiết.

### 14.4. Kiểm tra generated SQL sau nâng cấp

Trong test integration:

- Xem Hibernate gọi sequence nào.
- Xem INSERT target table/columns.
- Xác nhận generated ID.
- Xác nhận sequence state.
- Xác nhận batch behavior nếu quan trọng.

Không dựa vào annotation diff đơn thuần.

## 15. Naming strategy có hai tầng

Hibernate có hai khái niệm quan trọng:

1. **ImplicitNamingStrategy**: quyết định logical name khi mapping không khai báo tên tường minh.
2. **PhysicalNamingStrategy**: chuyển logical name thành physical identifier mà database sử dụng.

Ví dụ:

~~~java
@Entity
class PurchaseOrder {
    private Instant createdAt;
}
~~~

Logical names có thể gần với:

~~~text
PurchaseOrder
createdAt
~~~

Physical naming strategy có thể biến thành:

~~~text
purchase_order
created_at
~~~

### 15.1. Implicit naming

Nếu không chỉ định `@Table(name=...)`, Hibernate cần suy ra tên bảng. Nếu không chỉ định `@Column(name=...)`, Hibernate suy ra tên cột từ property/attribute và context.

### 15.2. Physical naming

Physical naming strategy có thể áp dụng quy tắc snake_case, lower-case, prefix/suffix hoặc chuẩn tên riêng của dự án lên logical identifiers.

### 15.3. Explicit name vẫn có thể qua physical strategy

Một `@Table(name = "PurchaseOrder")` thường cung cấp explicit logical name; physical naming strategy vẫn có thể chuyển đổi identifier đó tùy implementation. Đừng cho rằng explicit annotation luôn bypass mọi physical naming transformation.

### 15.4. Naming strategy không đổi dữ liệu

Đổi từ `createdAt` sang `created_at` trong mapping không tự rename column production. Cần migration đổi schema hoặc cấu hình naming tương thích với schema hiện tại.

## 16. ImplicitNamingStrategy và PhysicalNamingStrategy trong Spring Boot

Hibernate có các SPI naming strategy; Spring Boot có thể cung cấp defaults/integration riêng.

Spring Boot properties thường gặp:

~~~yaml
spring:
  jpa:
    hibernate:
      naming:
        implicit-strategy: org.hibernate.boot.model.naming.ImplicitNamingStrategyJpaCompliantImpl
        physical-strategy: org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy
~~~

Tên class và property cần kiểm tra theo Spring Boot/Hibernate version. Một số phiên bản Boot từng dùng class Spring-specific như `SpringPhysicalNamingStrategy`; phiên bản khác dùng `CamelCaseToUnderscoresNamingStrategy`. Không copy class name cũ vào version mới mà không kiểm tra dependency.

### 16.1. Hibernate properties trực tiếp

Hibernate có thể nhận:

~~~properties
hibernate.implicit_naming_strategy=...
hibernate.physical_naming_strategy=...
~~~

Spring Boot có namespace cấu hình riêng để truyền vào Hibernate. Tránh khai báo cùng một strategy ở nhiều nơi với giá trị mâu thuẫn.

### 16.2. Default phụ thuộc integration

Hibernate standalone, Spring Boot và custom persistence bootstrap có thể chọn defaults khác. Khi nâng cấp, kiểm tra effective configuration/logs hoặc metadata thực tế.

### 16.3. Naming strategy custom

Một class implement `PhysicalNamingStrategy` có thể override:

- Table name.
- Column name.
- Sequence name.
- Schema name.
- Catalog name.

Nếu custom strategy chỉ xử lý table/column mà bỏ sequence, tên generator có thể không theo quy tắc dự án mong muốn.

### 16.4. Giữ strategy ổn định qua upgrade

Nếu production schema được tạo bằng một strategy custom, phải giữ strategy tương thích hoặc viết migration rename object trước khi đổi. Đừng thay class mặc định rồi mong Hibernate tự tìm lại mọi object cũ.

## 17. Tên generator, logical sequence và physical sequence

Có ít nhất ba tầng tên:

~~~java
@SequenceGenerator(
    name = "purchase_order_id_gen",
    sequenceName = "purchase_order_seq",
    schema = "app"
)
~~~

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Generator name | `purchase_order_id_gen` | Tên logic được tham chiếu trong mapping |
| Logical sequence name | `purchase_order_seq` | Tên sequence khai báo trong annotation |
| Physical qualified name | `app.purchase_order_seq` | Object database sau naming/schema resolution |

### 17.1. Generator name không phải database object

Không chạy:

~~~sql
SELECT nextval('purchase_order_id_gen');
~~~

trừ khi database thật sự có sequence mang tên đó. Thông thường tên này chỉ là generator metadata.

### 17.2. Schema/catalog

Một sequence có thể nằm trong schema riêng. Nếu mapping bỏ schema và connection search_path thay đổi, Hibernate có thể tìm sequence ở schema khác hoặc báo missing object.

### 17.3. Sequence name cũng chịu naming

PhysicalNamingStrategy có callback cho sequence names trong Hibernate SPI. Vì vậy kiểm tra DDL/runtime SQL để biết tên cuối cùng; đừng chỉ đọc `sequenceName` trong annotation.

### 17.4. Naming collision

Hai generator/entity có thể cùng suy ra tên sequence sau khi:

- Chuyển camelCase thành snake_case.
- Cắt tên theo giới hạn identifier của database.
- Thêm prefix/suffix.
- Lowercase/uppercase.

Test metadata và catalog để phát hiện collision/truncation.

## 18. Implicit sequence naming và thay đổi giữa Hibernate versions

Khi dùng sequence generator mà không khai báo sequenceName rõ, Hibernate cần chọn tên database object theo naming rules của version/provider.

Hibernate 6 có cơ chế `ImplicitDatabaseObjectNamingStrategy` và property liên quan:

~~~properties
hibernate.id.db_structure_naming_strategy=...
~~~

Các lựa chọn/behavior cụ thể phụ thuộc Hibernate version; thường được nhắc đến với các chiến lược như `standard`, `legacy` và `single`.

### 18.1. Vì sao đây là migration concern?

Một version cũ có thể dùng một sequence chung; version mới có thể suy ra tên sequence theo entity hoặc quy tắc khác. Schema production đã có sequence cũ, nhưng mapping mới có thể gọi sequence mới chưa tồn tại.

### 18.2. Không dựa vào default implicit sequence name

Nếu cần tương thích schema lâu dài, khai báo:

~~~java
@SequenceGenerator(
    name = "order_gen",
    sequenceName = "purchase_order_seq",
    allocationSize = 50
)
~~~

và tạo object đó bằng migration. Đây là cách làm rõ contract hơn phụ thuộc default naming.

### 18.3. Nếu phải giữ legacy naming

Có thể dùng naming strategy compatibility phù hợp với Hibernate version hoặc explicit sequenceName. Trước khi chọn property `hibernate.id.db_structure_naming_strategy`, kiểm tra version đích và behavior được tài liệu hóa; không đoán giá trị vì cùng một tên strategy có thể có default/semantics thay đổi.

### 18.4. Tránh tạo sequence mới song song ngoài ý muốn

Nếu migration tạo `purchase_order_seq` nhưng Hibernate mới gọi `purchase_order_seq_seq`, hai sequences có thể cùng tồn tại. Ứng dụng vẫn chạy một thời gian nhưng sequence cũ không được dùng; khi rollback app version hoặc deploy một instance cũ, ID allocation có thể va chạm nếu cả hai generators không được phối hợp.

## 19. Naming strategy cho bảng và cột

Ví dụ:

~~~java
@Entity
@Table(name = "PurchaseOrder")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "createdAt")
    private Instant createdAt;
}
~~~

Physical strategy có thể tạo:

~~~text
purchase_order
created_at
~~~

### 19.1. Schema cũ dùng PascalCase

Nếu database đã có `"PurchaseOrder"` và `"createdAt"` được tạo bằng quoted identifiers, đổi sang lowercase snake_case không tự tương thích. PostgreSQL phân biệt quoted mixed-case identifiers.

### 19.2. Schema migration phải rename có chủ đích

~~~sql
ALTER TABLE "PurchaseOrder"
RENAME TO purchase_order;

ALTER TABLE purchase_order
RENAME COLUMN "createdAt" TO created_at;
~~~

Đây là ví dụ PostgreSQL; cần kiểm tra dependencies như views, triggers, functions, grants, indexes và external SQL trước khi rename.

### 19.3. Không để entity mapping và migration dùng hai quy tắc khác nhau

Nếu migration tạo `purchase_order` nhưng physical strategy map thành `purchase_orders`, ứng dụng có thể báo table not found. Có thể dùng explicit @Table/@Column và strategy thống nhất, hoặc test schema catalog sau migration.

### 19.4. Tên dài và truncation

Database có giới hạn độ dài identifiers. Hai logical names dài khác nhau có thể bị cắt thành cùng physical name. Naming strategy custom nên tạo tên ổn định, tránh collision; database catalog tests giúp phát hiện.

## 20. Quoted identifiers, case folding và reserved words

Một tên như `order`, `user`, `group`, `key` có thể trùng reserved words hoặc gây khó khi dùng native SQL.

### 20.1. Tránh reserved words nếu có thể

Ưu tiên tên như:

~~~text
purchase_order
app_user
order_group
~~~

thay vì đặt tên bảng `order` hoặc `user` rồi phải quote ở mọi câu SQL.

### 20.2. PostgreSQL unquoted identifiers

PostgreSQL chuyển unquoted identifiers về lowercase. `PurchaseOrder` không quote được hiểu như `purchaseorder`, còn `"PurchaseOrder"` giữ nguyên case.

### 20.3. Quoting trong Hibernate

Hibernate hỗ trợ quoted identifiers theo cách phụ thuộc provider/dialect, ví dụ dùng dấu backtick trong một số annotation mapping hoặc quoted name theo chuẩn JPA. Kiểm tra cú pháp của version đang dùng; không trộn quote syntax giữa Java annotation, SQL migration và database.

### 20.4. Global quoting

Một số cấu hình có thể quote tất cả identifiers, ví dụ `hibernate.globally_quoted_identifiers`. Bật global quoting trên schema đã tồn tại có thể thay đổi cách database resolve case-sensitive names. Không bật chỉ để tránh reserved word; kiểm tra migration/schema trước.

### 20.5. Test native SQL

Native SQL phải dùng đúng physical quoted/unquoted names. JPQL dùng entity/property names; native SQL dùng tên bảng/cột database. Hai namespace này không giống nhau.

## 21. Naming strategy và association columns

Implicit naming đặc biệt dễ gây bất ngờ với:

- `@JoinColumn`.
- `@JoinTable`.
- `@Embedded` attributes.
- `@ElementCollection`.
- Inheritance discriminator columns.
- Secondary tables.

Ví dụ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

Provider có thể suy ra join column từ property/entity identifiers. Nếu strategy đổi, tên physical FK column có thể khác.

### 21.1. Khai báo tên quan hệ quan trọng

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
~~~

Explicit name giúp hợp đồng rõ hơn, nhưng vẫn phải xem physical naming transformation và database schema.

### 21.2. Join table

~~~java
@ManyToMany
@JoinTable(
    name = "user_roles",
    joinColumns = @JoinColumn(name = "user_id"),
    inverseJoinColumns = @JoinColumn(name = "role_id")
)
private Set<Role> roles;
~~~

Đổi implicit naming có thể tác động tên join table/cột nếu chúng không được khai báo. Migration cần theo dõi tất cả database objects, không chỉ entity tables.

### 21.3. Composite FK

Với @JoinColumns, mỗi physical column name và referencedColumnName phải khớp đúng DDL. Naming strategy có thể làm tên cuối khác annotation logical name; kiểm tra generated SQL và schema.

## 22. Schema, catalog và search_path

Một sequence/table có thể được qualify:

~~~java
@Table(name = "purchase_orders", schema = "app")
~~~

~~~java
@SequenceGenerator(
    name = "order_gen",
    sequenceName = "purchase_order_seq",
    schema = "app"
)
~~~

### 22.1. Default schema

Hibernate có thể dùng default schema/catalog config hoặc JDBC connection defaults. PostgreSQL còn có `search_path`.

### 22.2. Search path có thể làm test pass nhưng production fail

Test database user có thể mặc định schema `public`, production app user có `search_path=app,public`. Một sequence không qualify schema có thể resolve khác nhau.

### 22.3. Kiểm tra current_schema/search_path

~~~sql
SELECT current_schema(), current_schemas(true);
SHOW search_path;
~~~

Đây là PostgreSQL diagnostic. Test bằng runtime database role để thấy schema resolution thực tế.

### 22.4. Grants

Sequence có thể tồn tại nhưng app user thiếu quyền USAGE/SELECT/UPDATE phù hợp. Test bằng role runtime; chạy migration bằng owner rồi test bằng superuser có thể che permission error.

## 23. Đổi naming strategy là một schema migration

Giả sử version cũ:

~~~text
purchaseOrder
createdAt
hibernate_sequence
~~~

Version mới dự định:

~~~text
purchase_order
created_at
purchase_order_seq
~~~

Đây là thay đổi database contract, không chỉ refactor Java.

### 23.1. Lập mapping cũ → mới

| Object cũ | Object mới | Consumer cần kiểm tra |
|---|---|---|
| Table `purchaseOrder` | `purchase_order` | Hibernate, views, reports, ETL |
| Column `createdAt` | `created_at` | Native SQL, BI, triggers |
| Sequence `hibernate_sequence` | `purchase_order_seq` | Hibernate instances, jobs, scripts |
| Join table cũ | `user_roles` | Association mappings, migrations |

### 23.2. Expand–migrate–contract

Với hệ thống cần zero/low downtime:

1. Thêm object mới hoặc compatibility layer.
2. Đồng bộ dữ liệu/sequence state.
3. Deploy app có thể hoạt động với schema transition.
4. Chuyển reads/writes sang object mới.
5. Xác nhận không còn consumer cũ.
6. Xóa object cũ ở release sau.

Không thể luôn giữ hai sequences độc lập cho cùng một bảng và cho cả hai cấp IDs an toàn; cần một kế hoạch coordination rõ.

### 23.3. View/alias không thay thế mọi object rename

Một view tương thích có thể giúp một số SELECT cũ, nhưng không nhất thiết hỗ trợ INSERT/UPDATE/sequence calls như table cũ. Đối với sequence, compatibility wrapper cần được thiết kế riêng.

### 23.4. Không rename sequence khi app cũ còn gọi

Rolling deployment có thể có pods cũ và mới cùng chạy. Nếu pod cũ gọi `hibernate_sequence` và pod mới gọi `purchase_order_seq`, hai sequence có thể cấp ranges không phối hợp. Trước khi cutover phải có một cơ chế cấp IDs chung hoặc rollout đảm bảo không có writers đồng thời dùng hai nguồn độc lập.

## 24. Migration sequence state sau import/backfill

Một quy trình data import:

1. Import rows với IDs giữ nguyên từ legacy.
2. Bảng đã có IDs tới 100000.
3. Hibernate sequence vẫn ở vùng 1–5000.
4. INSERT mới có thể va chạm primary key.

### 24.1. Kiểm tra max ID

~~~sql
SELECT MAX(id) FROM purchase_orders;
~~~

### 24.2. Kiểm tra sequence state trên PostgreSQL

~~~sql
SELECT last_value, is_called
FROM purchase_order_seq;
~~~

Quyền đọc sequence metadata có thể cần quyền phù hợp.

### 24.3. Đồng bộ sequence đơn giản

Với generator đơn giản increment 1:

~~~sql
SELECT setval(
    'purchase_order_seq',
    COALESCE((SELECT MAX(id) FROM purchase_orders), 1),
    EXISTS (SELECT 1 FROM purchase_orders)
);
~~~

### 24.4. Xác minh optimizer trước khi dùng công thức

Nếu allocationSize > 1 và Hibernate dùng pooled/pooled-lo, sequence increment và next value phải được căn theo optimizer. Công thức đơn giản trên có thể không đủ hoặc không an toàn. Xác minh với Hibernate version, generator configuration và SQL sequence calls thực tế.

### 24.5. Nhiều bảng dùng chung sequence

Nếu một sequence được dùng cho nhiều tables, MAX(id) phải được xác định trên toàn bộ consumer namespace. Không đồng bộ theo một bảng rồi để bảng khác va chạm.

### 24.6. Đồng bộ sequence không được chạy tùy tiện khi app còn ghi

Một app instance có thể đang giữ block IDs đã preallocate. Reset sequence khi instances còn dùng block cũ có thể tạo overlap. Thực hiện maintenance theo rollout/quiesce strategy, hoặc dùng cơ chế chuyển đổi đã được kiểm thử với concurrent writers.

## 25. Migration thay đổi allocationSize

Giả sử cũ:

~~~java
allocationSize = 1
~~~

mới:

~~~java
allocationSize = 50
~~~

### 25.1. Cần xem cả ba thành phần

- Annotation/generator metadata.
- Database sequence INCREMENT BY.
- Runtime optimizer của Hibernate.

### 25.2. Sequence increment

Migration PostgreSQL minh họa:

~~~sql
ALTER SEQUENCE purchase_order_seq INCREMENT BY 50;
~~~

Chỉ chạy nếu optimizer/generator contract đích yêu cầu increment 50. Nếu provider đang dùng optimizer khác, DDL này có thể sai.

### 25.3. Rollout version cũ và mới

Không giả định hai versions có thể cùng sử dụng một sequence sau khi increment thay đổi. Cần kiểm tra compatibility matrix hoặc triển khai downtime/stop-the-world cho thay đổi không tương thích.

### 25.4. Rollback app version

Nếu app mới đã dùng block 50 và sequence increment 50, rollback app cũ allocation 1 có thể gây mismatch hoặc cấp IDs không theo assumptions. Rollback plan phải bao gồm schema/generator compatibility, không chỉ deploy lại binary.

## 26. Naming strategy custom và compatibility test

Một custom strategy có thể:

~~~java
public class LegacyPhysicalNamingStrategy
        extends PhysicalNamingStrategyStandardImpl {

    @Override
    public Identifier toPhysicalTableName(
            Identifier name,
            JdbcEnvironment context) {
        // Chuyển logical table name theo quy tắc legacy.
        return name;
    }
}
~~~

Đây là skeleton minh họa; implementation thật cần xử lý quoting, catalog/schema/table/sequence/column nhất quán.

### 26.1. Không override một phần rồi quên sequence

Nếu strategy đổi table/column nhưng không sequence, generator name có thể đi theo default khác. Đối với naming compatibility, test tất cả object categories.

### 26.2. Naming strategy phải deterministic

Không dùng:

- Random suffix.
- Current timestamp.
- Environment-specific logic khó dự đoán.
- Locale-dependent lowercasing không ổn định.

Một logical identifier phải tạo cùng physical identifier trong mọi instance/version có cùng config.

### 26.3. Tránh tên collision sau normalization

Ví dụ `orderItem` và `order_item` có thể cùng map về `order_item`. Custom strategy có thể kiểm tra naming collisions trong bootstrap/schema tests.

### 26.4. Test bằng metadata và SQL

Khởi động SessionFactory, chạy persist/query, capture SQL và kiểm tra schema catalog. Không chỉ unit test method `toPhysicalColumnName`; behavior cuối cùng phụ thuộc Hibernate bootstrap và dialect.

## 27. Kiểm tra generator metadata và SQL thực tế

Một quy trình nâng cấp:

1. Ghi lại Hibernate/Spring Boot/JPA version cũ.
2. Ghi lại version mới.
3. Xác định entity nào dùng AUTO/IDENTITY/SEQUENCE/TABLE/UUID/assigned.
4. Ghi generator name, sequenceName, schema, initialValue, allocationSize.
5. Xác định physical naming strategy và implicit sequence naming strategy.
6. Chạy integration test trên database production version.
7. Capture SQL trước/sau.
8. Kiểm tra schema objects và sequence state.

### 27.1. SQL logging

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Bind TRACE có thể log identifiers và dữ liệu nhạy cảm; chỉ bật trong test/diagnostic kiểm soát, không bật rộng trong production.

### 27.2. Xem sequence calls

Với PostgreSQL, có thể thấy SQL dạng:

~~~sql
select nextval('app.purchase_order_seq');
~~~

Tên cuối có thể được quote/qualify khác. Đây là SQL minh họa; capture runtime SQL của ứng dụng để xác định chính xác.

### 27.3. Kiểm tra DDL không chỉ từ log Hibernate

Schema production do Flyway/Liquibase quản lý. Hãy đọc migration và database catalog; Hibernate-generated DDL trong test không phải source of truth nếu production không dùng ddl-auto.

### 27.4. Không assert alias/query string toàn bộ

Hibernate version có thể thay alias/format. Assert tên sequence, bảng, cột và semantics cần thiết; tránh phụ thuộc alias tự sinh.

## 28. PostgreSQL catalog queries để kiểm tra names

### 28.1. Bảng/cột

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'purchase_orders'
ORDER BY ordinal_position;
~~~

### 28.2. Sequence

~~~sql
SELECT
    schemaname,
    sequencename,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    cache_size
FROM pg_sequences
WHERE schemaname = 'app';
~~~

### 28.3. Sequence state

~~~sql
SELECT last_value, is_called
FROM app.purchase_order_seq;
~~~

### 28.4. Dependencies

Có thể xem sequence dependency với identity/serial columns qua PostgreSQL catalogs. Identity columns thường có dependency khác với sequence được gọi thủ công; khi migration/rename, kiểm tra dependency thay vì chỉ tìm tên string.

### 28.5. Kiểm tra schema và quoting

~~~sql
SELECT current_schema();
SHOW search_path;
~~~

Các query này PostgreSQL-specific. Dùng runtime role để xác nhận object resolution/permissions.

## 29. Hibernate schema validation có thể bỏ sót điều gì?

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

`validate` hữu ích để phát hiện một số sai lệch giữa entity mapping và schema như table/column/type. Tuy nhiên không xem nó là kiểm toán đầy đủ mọi database object.

Có thể vẫn cần kiểm tra riêng:

- Sequence increment/allocation compatibility theo provider/version.
- Partial/expression indexes.
- Trigger/function bodies.
- RLS policies.
- Grants/permissions.
- Deferrable constraints.
- Stored procedures.
- Extensions.
- Generated column expressions.
- Naming collisions.

### 29.1. Migration là source of truth

Nếu Flyway/Liquibase quản lý schema, test đúng migration path và dùng Hibernate validate để bổ sung. Không dùng Hibernate `update` để tự điều chỉnh production schema.

### 29.2. Catalog assertion

Viết test SQL kiểm tra sequence increment/name, indexes và constraints mà Hibernate validate không bao phủ đầy đủ.

### 29.3. Runtime assertion

Thử persist nhiều rows, đọc generated IDs, kiểm tra uniqueness và query bằng tên physical objects. Catalog đúng nhưng app user thiếu quyền vẫn có thể fail runtime.

## 30. Spring Boot properties khi nâng cấp

Một cấu hình minh họa:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
      naming:
        implicit-strategy: org.hibernate.boot.model.naming.ImplicitNamingStrategyJpaCompliantImpl
        physical-strategy: org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        id:
          db_structure_naming_strategy: standard
~~~

Không copy toàn bộ YAML này như cấu hình mặc định cho mọi project. Class names, property binding và accepted strategy values phụ thuộc Hibernate/Spring Boot version.

### 30.1. Tránh khai báo duplicate config

Một property có thể được đặt ở:

- application.yml.
- application profile.
- Environment variable.
- JVM system property.
- Spring test properties.
- Custom EntityManagerFactory bean.

Giá trị cuối cùng có thể không phải file YAML bạn đang đọc. Kiểm tra effective configuration.

### 30.2. Test profile không nên đổi naming strategy âm thầm

Nếu H2 test dùng naming strategy khác PostgreSQL production, schema H2 pass không chứng minh schema production. Dùng cùng naming configuration hoặc test đúng DB.

### 30.3. Không hard-code dialect cũ

Hibernate mới có thể tự detect dialect từ JDBC metadata. Explicit dialect cũ hoặc class đã deprecated/removed có thể gây lỗi upgrade. Chỉ override khi có lý do, dùng class tương thích version.

## 31. Nâng cấp Hibernate 5 lên 6 hoặc 6 lên 7: kiểm tra những gì?

Một upgrade lớn có thể thay đổi:

- Bootstrapping và APIs.
- Dialect classes.
- Type system và JDBC mappings.
- SQL rendering.
- Generator defaults/naming.
- Implicit database object naming.
- Sequence optimizer behavior/configuration.
- Schema generation/validation.
- Identifier quoting và metadata interpretation.

### 31.1. Không chỉ chạy compile

Code compile không chứng minh migration/schema/generator tương thích. Các lỗi thường chỉ xuất hiện khi SessionFactory khởi động hoặc khi INSERT đầu tiên gọi sequence.

### 31.2. Kiểm tra deprecations trước upgrade

Thay generator APIs deprecated, dialect class cũ, naming strategy custom dùng SPI cũ và properties không còn được hỗ trợ. Làm theo migration guide đúng version.

### 31.3. Baseline schema trước và sau

Dump database object names/definitions:

- Tables/columns.
- PK/FK/unique/check constraints.
- Indexes.
- Sequences.
- Triggers/functions.

So sánh với migration mới dự kiến. Đừng dùng output DDL của H2 làm baseline PostgreSQL.

### 31.4. Chạy app cũ và mới trên schema compatibility branch

Nếu cần rolling upgrade, kiểm tra cả binary cũ và mới với schema transition. Một app version cũ có thể không hiểu naming/generator mới dù app mới chạy tốt.

## 32. Migration đổi IDENTITY sang SEQUENCE

Đây là thay đổi lớn vì generator và DDL khác nhau.

### 32.1. Kiểm kê dữ liệu

~~~sql
SELECT MAX(id) FROM purchase_orders;
~~~

Kiểm tra primary key, foreign keys và mọi consumer external lưu ID.

### 32.2. Tạo sequence mới

~~~sql
CREATE SEQUENCE app.purchase_order_seq
    START WITH 1
    INCREMENT BY 1;
~~~

Đây chỉ là generator đơn giản allocationSize=1. Nếu dùng pooled allocation, thiết kế increment/optimizer tương ứng.

### 32.3. Đồng bộ sequence với dữ liệu

Với increment 1, có thể dùng setval formula phù hợp. Nếu table rỗng, đảm bảo nextval bắt đầu đúng; nếu có rows, đảm bảo ID mới lớn hơn MAX(id).

### 32.4. Deploy mapping mới

Chuyển `GenerationType.IDENTITY` sang `SEQUENCE` cùng explicit sequenceName và allocationSize đã migration. Test app mới trên database đã có data.

### 32.5. Rolling deployment

Nếu app cũ vẫn dùng identity column và app mới dùng sequence, hai generator có thể không đồng bộ. Cần cutover có downtime/maintenance hoặc một thiết kế compatibility để cả hai writers lấy ID từ nguồn thống nhất.

### 32.6. Rollback

Rollback app version không tự rollback sequence state/DDL. Giữ schema tương thích hoặc có migration rollback đã được test; không xóa sequence mới ngay khi app mới đã cấp IDs.

## 33. Migration đổi sequence naming

Giả sử cũ `hibernate_sequence`, mới `purchase_order_seq`.

### 33.1. Không tạo sequence mới rồi để state mặc định

Nếu sequence mới bắt đầu từ 1 trong khi bảng đã có IDs, collision có thể xảy ra.

### 33.2. Chuyển sequence state có kiểm soát

Với generator đơn giản, đồng bộ từ MAX(id). Với pooled optimizer, đồng bộ theo increment/block semantics. Nếu sequence dùng chung nhiều entity, xét tất cả consumers.

### 33.3. Rename hay create-and-copy?

PostgreSQL có thể rename sequence, nhưng cần kiểm tra:

- Mapping cũ còn gọi tên cũ không?
- Defaults/identity dependencies có theo rename không?
- Permissions/grants có được giữ không?
- Monitoring/scripts có tham chiếu tên cũ không?

Create sequence mới có thể an toàn hơn cho migration staged nhưng cần coordination để tránh hai nguồn cấp IDs độc lập.

### 33.4. Test app version cũ/mới

Test:

1. App cũ persist một entity.
2. Chạy migration.
3. App mới persist entity tiếp.
4. Kiểm tra IDs không trùng.
5. Nếu rolling, test hai versions đồng thời trong môi trường kiểm soát.

## 34. Migration thay physical naming strategy

Ví dụ từ mixed case sang snake_case:

~~~sql
ALTER TABLE app."PurchaseOrder"
RENAME TO purchase_order;

ALTER TABLE app.purchase_order
RENAME COLUMN "createdAt" TO created_at;
~~~

### 34.1. Lập danh sách tất cả object

Bao gồm:

- Tables.
- Columns.
- Sequences.
- Join tables.
- Indexes.
- Constraints.
- Views/materialized views.
- Functions/triggers.
- Native SQL trong app.
- ETL/reporting jobs.

### 34.2. Explicit names giảm phụ thuộc defaults

Có thể thêm `@Table`, `@Column`, `@JoinColumn`, `@SequenceGenerator` rõ ràng. Nhưng physical strategy vẫn có thể biến đổi tên; kiểm tra cuối cùng.

### 34.3. Không rename chỉ một phía

Nếu migration rename column nhưng app version cũ vẫn query tên cũ, deployment sẽ fail. Cần compatibility plan cho readers/writers cũ.

### 34.4. Rollback naming

Rollback migration rename phải xét data mới và object dependencies. Nếu có app version mới đã ghi dữ liệu, rollback schema/app cần được thử trước.

## 35. Test strategy: kiểm tra generator với database thật

Một integration test tối thiểu:

~~~java
@Test
void generatesDistinctOrderIds() {
    PurchaseOrder first = new PurchaseOrder(...);
    PurchaseOrder second = new PurchaseOrder(...);

    entityManager.persist(first);
    entityManager.persist(second);
    entityManager.flush();

    assertNotNull(first.getId());
    assertNotNull(second.getId());
    assertNotEquals(first.getId(), second.getId());
}
~~~

### 35.1. Không assert liên tiếp

Không:

~~~java
assertEquals(first.getId() + 1, second.getId());
~~~

Sequence, pooling, rollback và concurrent writers tạo gaps là bình thường.

### 35.2. Test qua nhiều transactions

Tạo entities trong các transactions khác nhau để xác nhận generator tiếp tục hoạt động sau commit/restart context.

### 35.3. Test nhiều threads/instances

Nếu production chạy nhiều pods, concurrency test cần nhiều sessions/connections và nếu cần nhiều application contexts/processes để kiểm tra sequence allocation blocks không overlap.

### 35.4. Test sequence increment

Query catalog để xác nhận sequence increment phù hợp allocationSize/optimizer. Đừng chỉ assert ID unique trong một JVM; mismatch có thể xuất hiện giữa các instances.

## 36. Test naming strategy bằng schema metadata

Một test mapping có thể persist entity rồi query physical table:

~~~java
entityManager.persist(new PurchaseOrder(...));
entityManager.flush();

Integer count = jdbcTemplate.queryForObject(
    "select count(*) from app.purchase_order",
    Integer.class
);
~~~

### 36.1. Query catalog

PostgreSQL:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'app';
~~~

### 36.2. Kiểm tra sequence name

~~~sql
SELECT schemaname, sequencename, increment_by
FROM pg_sequences
WHERE schemaname = 'app';
~~~

### 36.3. Kiểm tra quoted names

Query catalog phân biệt tên vật lý thực tế; một bảng `"PurchaseOrder"` và `purchase_order` là hai identifiers khác nhau trên PostgreSQL.

### 36.4. Test custom naming strategy ở bootstrap

Khởi động SessionFactory với đúng custom strategy, chạy persist/query và xác nhận SQL/metadata. Unit test riêng cho strategy class không đủ để xác minh Hibernate thực sự áp dụng nó cho sequence/schema.

## 37. Testcontainers và migration compatibility

Khi production là PostgreSQL, chạy Testcontainers PostgreSQL đúng major version:

~~~java
@Testcontainers
@SpringBootTest
class IdentifierUpgradeIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    EntityManager entityManager;

    @Autowired
    JdbcTemplate jdbcTemplate;
}
~~~

Dependency/version phải khớp Spring Boot/Testcontainers của project.

### 37.1. Test migration từ database sạch

1. Start container.
2. Run Flyway/Liquibase migrations.
3. Hibernate `ddl-auto=validate`.
4. Persist entities bằng generator mới.
5. Query physical names/sequence metadata.

### 37.2. Test upgrade từ schema cũ

1. Tạo database theo migration version cũ.
2. Seed IDs và dữ liệu thật đại diện.
3. Đặt sequence state như production cũ.
4. Chạy migration mới.
5. Khởi động app version mới.
6. Persist thêm rows.
7. Kiểm tra không collision và mappings đúng.

### 37.3. Test rolling compatibility

Nếu cần, chạy app cũ và mới cùng database trong test riêng. Không để hai generator không tương thích cùng ghi trong production chỉ vì mỗi version chạy riêng lẻ đều pass.

### 37.4. Pin database image

Dùng PostgreSQL image version phù hợp production, không dùng `latest`. Testcontainers kiểm tra engine/version thật; H2 compatibility mode không thay thế.

## 38. Spring Data JPA và assigned/generated identifiers

Spring Data `save()` có thể chọn persist hoặc merge dựa trên entity new detection.

### 38.1. Generated ID null

Entity có generated Long ID thường được nhận diện new khi ID null, sau đó persist.

### 38.2. UUID được gán trước

Nếu UUID được tạo trong constructor, ID đã non-null trước save. Spring Data có thể coi entity là existing tùy version/new detection rules và version property. Cần test save/merge semantics hoặc implement Persistable khi phù hợp.

### 38.3. Persistable

~~~java
@Entity
public class ImportedRecord implements Persistable<UUID> {
    @Id
    private UUID id;

    @Transient
    private boolean newEntity = true;

    @Override
    public UUID getId() { return id; }

    @Override
    public boolean isNew() { return newEntity; }

    @PostPersist
    @PostLoad
    void markNotNew() { newEntity = false; }
}
~~~

Đây là mẫu minh họa; lifecycle và serialization cần được thiết kế cẩn thận. Không thêm Persistable nếu default new detection đã đúng.

### 38.4. Merge không phải insert

Nếu Spring Data coi entity là existing, `save()` có thể gọi merge. Một entity mới có ID được gán trước có thể dẫn tới SELECT/UPDATE/insert behavior khác mong muốn. Test trực tiếp SQL và row count.

## 39. Kiểm tra identifier khi import/migrate dữ liệu legacy

Một import job có thể insert ID thủ công:

~~~sql
INSERT INTO purchase_orders(id, order_number, ...)
VALUES (90001, 'SO-LEGACY', ...);
~~~

### 39.1. Đồng bộ generator sau import

Nếu bảng dùng sequence, đồng bộ sequence state theo optimizer. Nếu dùng identity, cách explicit identity insert và reset/identity override phụ thuộc database.

### 39.2. Không chạy reset sequence khi writer còn hoạt động

Pause writers hoặc dùng cutover/locking plan. Một application instance có thể đang giữ allocation block chưa dùng.

### 39.3. Import nhiều batches

Nếu job import và application online cùng ghi, cần bảo đảm ID ranges không overlap. Có thể dùng sequence chung, staging + remap, hoặc reserved ID range theo contract.

### 39.4. External references

Nếu ID được gửi tới event bus hoặc hệ thống khác, đổi generator không được tái sử dụng ID cũ. Giữ mapping/public identifier ổn định hoặc phát event migration theo contract.

## 40. Sequence không bảo đảm số nghiệp vụ liên tục

Yêu cầu:

~~~text
Invoice number: 000001, 000002, 000003, không được thiếu số
~~~

Sequence thông thường không bảo đảm điều này vì:

- Transaction rollback tiêu thụ giá trị.
- Concurrent transactions có thể commit theo thứ tự khác thứ tự cấp số.
- Pooled blocks có thể bỏ qua giá trị chưa dùng sau restart.
- Sequence cache có thể mất các giá trị chưa dùng khi database restart/crash.

### 40.1. Tách primary key và invoice number

Dùng sequence/UUID cho PK. Business invoice number có bảng counter/locking và workflow riêng theo yêu cầu pháp lý.

### 40.2. Row counter theo organization

Một thiết kế có thể dùng:

~~~sql
CREATE TABLE organization_counters (
    organization_id BIGINT NOT NULL,
    counter_name VARCHAR(50) NOT NULL,
    next_value BIGINT NOT NULL,
    PRIMARY KEY (organization_id, counter_name)
);
~~~

Cấp số bằng UPDATE atomic/RETURNING hoặc row lock trong transaction, theo quy tắc rollback và commit đã được định nghĩa. PostgreSQL sequence vẫn không rollback; counter row có thể rollback cùng transaction nhưng sẽ tạo contention.

### 40.3. Gapless không chỉ là SQL

Yêu cầu pháp lý có thể đòi xử lý hủy hóa đơn, void numbers, audit trail và nhiều loại chứng từ. Không chỉ viết `MAX(invoice_no)+1`; phải thiết kế nghiệp vụ/locking và audit.

## 41. Những lỗi naming thường gặp khi nâng cấp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Table not found | Physical naming strategy đổi | So sánh mapping với schema catalog |
| Column not found | Implicit/physical column name đổi | Explicit mapping hoặc migration rename |
| Sequence does not exist | Implicit sequence naming đổi | Explicit sequenceName/migration |
| Sequence increment mismatch | allocationSize khác DDL | Đồng bộ optimizer/increment |
| ID duplicate sau import | Sequence state thấp hơn MAX(id) | Đồng bộ sequence có kiểm soát |
| ID gaps tăng sau upgrade | Pooled allocation/restart | Chấp nhận gaps; không dùng làm business counter |
| App cũ và mới cấp ID chồng | Hai generator/sequence độc lập | Rollout compatibility và một nguồn cấp chung |
| Generator name không tìm thấy | Nhầm name với sequenceName | Phân biệt generator logic và DB object |
| Sequence ở sai schema | schema/search_path khác | Qualify schema và kiểm tra runtime role |
| Native SQL không tìm bảng | JPQL logical name bị dùng trong SQL | Dùng physical table/column names |
| Quoted table không được tìm | Case folding/quoting khác | Tránh mixed-case hoặc quote nhất quán |
| Hai tên bị cắt trùng | DB identifier length limit | Naming strategy deterministic + catalog test |
| @DataJpaTest pass, production fail | H2 schema/naming khác | Testcontainers production DB |
| ddl-auto=create-drop pass nhưng migration fail | Hibernate tự tạo schema | Test Flyway/Liquibase thật |
| UUID entity bị merge thay vì persist | Spring Data new detection | Test isNew/Version/Persistable |
| IDENTITY batching không hiệu quả | Insert cần generated key | Đo SEQUENCE/pooled nếu DB hỗ trợ |
| TABLE generator contention | Một row cấp ID chung | Sequence/UUID hoặc tối ưu allocation |
| Sequence reset gây va chạm | App đang giữ block IDs | Quiesce writers và migration theo optimizer |
| Rollback app version không chạy | Schema/generator đã đổi một chiều | Compatibility/rollback plan |

## 42. Quy trình kiểm tra trước và sau nâng cấp

### 42.1. Trước nâng cấp

Thu thập:

- Spring Boot, Hibernate ORM, Jakarta Persistence và JDBC driver versions.
- Database vendor/version.
- Mọi `@GeneratedValue` và generator definitions.
- Sequence/table names, schema, increment, cache.
- allocationSize và optimizer config.
- Implicit/physical naming strategy classes.
- DDL migrations đã áp dụng.
- Các native SQL/ETL/scripts gọi sequence trực tiếp.

### 42.2. Trong branch nâng cấp

1. Chạy test với database production bằng container.
2. Chạy migration từ schema cũ.
3. Khởi động Hibernate validate.
4. Persist entities đại diện cho từng generator.
5. Capture SQL sequence/INSERT.
6. Kiểm tra database catalogs.
7. Test concurrency/rolling compatibility nếu cần.

### 42.3. So sánh trước/sau

| Hạng mục | Version cũ | Version mới | Quyết định |
|---|---|---|---|
| Generator strategy | AUTO/SEQUENCE/... | ... | Giữ/đổi có migration |
| Sequence name | ... | ... | Tương thích/rename |
| Allocation size | ... | ... | Khớp increment |
| Optimizer | ... | ... | Không overlap blocks |
| Physical naming | ... | ... | Khớp schema |
| Implicit naming | ... | ... | Explicit/legacy compatibility |
| Generated SQL | ... | ... | Đã kiểm chứng |
| DDL/catalog | ... | ... | Migration đúng |

### 42.4. Sau nâng cấp

Theo dõi:

- Duplicate key/sequence mismatch exceptions.
- SQL errors table/column/sequence not found.
- Sequence usage rate.
- ID generation latency.
- Insert batching effectiveness.
- Migration logs.
- DB connection role/schema/search_path.

## 43. Một ví dụ mapping rõ ràng cho PostgreSQL production

Entity:

~~~java
@Entity
@Table(name = "purchase_orders", schema = "app")
public class PurchaseOrder {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_id_gen"
    )
    @SequenceGenerator(
        name = "purchase_order_id_gen",
        sequenceName = "purchase_order_seq",
        schema = "app",
        initialValue = 1,
        allocationSize = 50
    )
    private Long id;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
}
~~~

Migration minh họa cho pooled allocation 50:

~~~sql
CREATE SCHEMA IF NOT EXISTS app;

CREATE SEQUENCE app.purchase_order_seq
    START WITH 1
    INCREMENT BY 50;

CREATE TABLE app.purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
~~~

**Quan trọng:** đây là ví dụ cần đối chiếu optimizer/Hibernate version. Nếu Hibernate được cấu hình dùng sequence increment 1 hoặc optimizer không pooled, DDL increment 50 không phù hợp. Hãy xác minh SQL nextval và mismatch behavior trên phiên bản đích trước khi áp dụng.

### 43.1. Kiểm tra sau migration

~~~sql
SELECT schemaname, sequencename, increment_by
FROM pg_sequences
WHERE schemaname = 'app'
  AND sequencename = 'purchase_order_seq';
~~~

### 43.2. Persist và kiểm tra

~~~java
entityManager.persist(new PurchaseOrder(...));
entityManager.flush();
assertNotNull(order.getId());
~~~

Sau đó JDBC query row theo ID và catalog query sequence. Không assert ID liên tiếp.

## 44. Checklist kiểm tra naming và identifier strategy

1. Mỗi entity đang dùng IDENTITY, SEQUENCE, TABLE, UUID, AUTO hay assigned?
2. Chiến lược đó có phù hợp database production và write workload không?
3. AUTO có thể chọn generator khác khi dialect/version đổi không?
4. Generator logic name có bị nhầm với sequence database name không?
5. Sequence name/schema/catalog có được khai báo rõ không?
6. allocationSize có khớp optimizer và database sequence increment không?
7. Có nhiều app instances hoặc rolling versions cùng cấp IDs không?
8. Optimizer có phải pooled/pooled-lo hay strategy khác?
9. Có sequence dùng chung nhiều entity không?
10. Sequence state có lớn hơn vùng IDs đã import không?
11. Có application instance giữ block IDs khi migration/reset sequence không?
12. Có giả định ID liên tiếp/gapless trong business code không?
13. Có dùng ID primary key làm invoice/order business number không?
14. IDENTITY có ảnh hưởng JDBC insert batching không?
15. TABLE generator có gây contention không?
16. UUID storage type/index size có phù hợp database không?
17. Spring Data new detection có đúng với assigned UUID/Long IDs không?
18. ImplicitNamingStrategy hiện tại là class nào?
19. PhysicalNamingStrategy hiện tại là class nào?
20. Naming strategy có tác động sequence/schema/catalog names không?
21. Explicit @Table/@Column/@JoinColumn có khớp physical schema không?
22. Có quoted identifiers, reserved words, mixed case hoặc identifier truncation không?
23. search_path/default schema và app role permissions có đúng không?
24. Hibernate version mới có thay implicit sequence naming defaults không?
25. Có cấu hình `hibernate.id.db_structure_naming_strategy` cần tương thích không?
26. Có custom naming strategy dùng SPI cũ/deprecated không?
27. Flyway/Liquibase đã tạo/rename đúng database objects chưa?
28. Hibernate ddl-auto validate có được dùng đúng vai trò không?
29. Testcontainers có dùng đúng database vendor/version không?
30. Có test upgrade từ schema cũ với dữ liệu và sequence state thực tế không?
31. Có test nhiều transactions/instances để xác minh uniqueness không?
32. Có kiểm tra SQL, database catalogs và generated IDs sau flush/commit không?
33. Có kiểm tra app user thực tế có quyền gọi sequence không?
34. Rollback binary/schema có giữ tương thích generator/naming không?

## 45. Tổng kết: generator và naming là một phần của schema contract

~~~mermaid
flowchart TD
    A[Entity identifier mapping] --> B{Generation strategy}
    B --> C[IDENTITY]
    B --> D[SEQUENCE]
    B --> E[TABLE]
    B --> F[UUID / Assigned]
    D --> G[Optimizer + allocationSize]
    G --> H[Database sequence increment/state]
    A --> I[Logical table/column/sequence names]
    I --> J[Implicit naming]
    J --> K[Physical naming]
    K --> L[Schema/catalog/quoted identifiers]
    H --> M[Migration + runtime verification]
    L --> M
    M --> N[Upgrade-safe persistence]
~~~

Những nguyên tắc cần nhớ:

1. **IDENTITY** lấy ID từ database tại INSERT; đơn giản nhưng thường hạn chế JDBC insert batching.
2. **SEQUENCE** cấp ID độc lập với INSERT và có thể dùng pooled optimizers để giảm round trips; sequence increment phải phù hợp allocation/optimizer.
3. **TABLE** generator dùng một bảng để cấp ID, có thể tạo contention ở write workload lớn.
4. **UUID/assigned IDs** hữu ích cho distributed/import scenarios nhưng có storage, index và Spring Data new-detection implications riêng.
5. **AUTO phụ thuộc provider, dialect và version.** Nếu schema cần tên/chiến lược cố định, khai báo explicit generator.
6. **allocationSize khác JDBC batch size.** Một cái điều khiển block ID, một cái gom SQL writes.
7. **Sequence không gapless.** Rollback, pooled blocks và restart có thể tạo gaps; business numbers cần cơ chế riêng.
8. **Generator name khác sequenceName.** Tên logic JPA không phải database object.
9. **Implicit naming quyết định tên logical còn thiếu; physical naming chuyển thành tên database.** Cả table, column, sequence, schema và join objects cần được kiểm tra.
10. **Đổi naming strategy là schema migration.** Annotation mới không tự rename tables/columns/sequences production.
11. **Hibernate version có thể thay implicit sequence naming và generator behavior.** Kiểm tra migration guide/version-specific configuration, đặc biệt khi nâng cấp major version.
12. **Đồng bộ sequence sau import phải hiểu optimizer.** MAX(id)+1 hoặc setval công thức đơn giản có thể sai với shared sequence/pooled allocation.
13. **Rolling deployment cần generator compatibility.** Hai app versions không được vô tình cấp IDs từ các sequence/ranges không phối hợp.
14. **Hibernate validate không phải kiểm toán đầy đủ database objects.** Kết hợp migrations, catalog assertions và runtime tests.
15. **Testcontainers trên đúng database production** là nơi xác minh sequence, generated IDs, naming, migration, permissions và concurrency.

Khi nâng cấp Hibernate hoặc Spring Boot, hãy xem chiến lược sinh định danh và naming strategy như một phần của **hợp đồng schema đang được nhiều phiên bản ứng dụng cùng sử dụng**. Kiểm tra generator, optimizer, sequence state, tên physical objects và migration path trước khi deploy. Một mapping compile thành công chưa đủ; ứng dụng mới phải tạo ID duy nhất trên dữ liệu cũ, gọi đúng sequence trong đúng schema và đọc/ghi đúng table/column names mà database thực tế đang cung cấp.
