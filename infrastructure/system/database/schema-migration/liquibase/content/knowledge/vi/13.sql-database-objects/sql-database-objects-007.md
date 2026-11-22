# Quản lý sequence và các đối tượng đặc thù hệ quản trị bằng Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng **changelog**, **changeset**, **precondition**, **checksum** và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **SQL và đối tượng** này tập trung vào **sequence** và những đối tượng có đặc tính riêng của từng hệ quản trị cơ sở dữ liệu (DBMS), chẳng hạn function, procedure, trigger, view vật hóa, enum, extension hoặc đối tượng phân vùng.

Điểm quan trọng là Liquibase quản lý **vòng đời thay đổi** nhưng không xóa bỏ khác biệt giữa các DBMS. Một thuộc tính hay câu lệnh hợp lệ trên PostgreSQL có thể không tồn tại trên MySQL, hoặc có ngữ nghĩa khác trên Oracle và SQL Server. Vì vậy cần phân biệt rõ thao tác Liquibase có thể biểu diễn bằng change type chung, thao tác phải dùng SQL riêng của DBMS, và cách kiểm chứng trạng thái thực tế sau migration.

Sau bài này, bạn có thể chọn chiến lược cấp mã bằng sequence, viết changeset tạo/sửa/xóa sequence, dùng sequence cho cột hoặc ORM, chuẩn bị migration an toàn cho dữ liệu sẵn có và quản lý đối tượng riêng của database mà vẫn duy trì lịch sử triển khai đáng tin cậy.

## 1. Sequence là gì, giải quyết vấn đề nào?

**Sequence** là đối tượng của database phát sinh một chuỗi giá trị, thường là số nguyên, theo quy tắc như giá trị khởi đầu, bước tăng, giới hạn trên/dưới, cache và việc quay vòng. Sequence thường được dùng làm nguồn cấp khóa định danh cho hàng mới, nhưng có thể được dùng cho mã chứng từ kỹ thuật, số thứ tự xử lý hoặc những mục đích khác nếu đặc tính của nó phù hợp.

Với PostgreSQL, có thể hình dung luồng:

~~~text
INSERT hóa đơn
    |
    +--> lấy giá trị kế tiếp từ invoice_id_seq
    |             |
    |             +--> 1000, 1001, 1002, ...
    |
    +--> ghi invoice.id
                  |
                  +--> PK/UNIQUE đảm bảo id không trùng trong bảng
~~~

Cần tách ba khái niệm:

- **Sequence cấp giá trị**: sequence không tự trở thành ràng buộc duy nhất cho mọi bảng sử dụng nó. Khóa chính hoặc UNIQUE mới bảo vệ tính duy nhất tại bảng.
- **Default/identity hoặc ứng dụng yêu cầu giá trị**: sequence có thể được gắn với default của cột, được ORM gọi trước khi INSERT hoặc được SQL lấy giá trị trực tiếp.
- **Khóa chính là bất biến nghiệp vụ kỹ thuật**: số sinh ra từ sequence thường chỉ là surrogate key; mã hóa đơn có yêu cầu liên tục, không bỏ số, kiểm toán hoặc pháp lý có thể cần cơ chế riêng.

Đặc biệt, **sequence không bảo đảm một dãy số không có khoảng trống**. Giá trị đã cấp có thể bị bỏ do transaction rollback, INSERT lỗi, ứng dụng lấy trước rồi không dùng, cache bị mất khi tiến trình/database dừng, hoặc các lần cấp giá trị đồng thời. PostgreSQL không rollback thay đổi giá trị do **nextval** tạo ra như rollback dữ liệu thông thường. Vì vậy, đừng dùng sequence như nguồn số chứng từ bắt buộc liền mạch nếu nghiệp vụ cần bảo đảm không thiếu số.

## 2. Khả năng hỗ trợ khác nhau giữa các DBMS

Các DBMS phổ biến có cơ chế sinh số khác nhau. Bảng dưới đây định hướng lựa chọn, nhưng cần kiểm tra phiên bản database và Liquibase cụ thể trước khi triển khai:

| DBMS | Cơ chế thường dùng | Lưu ý khi viết migration |
|---|---|---|
| **PostgreSQL** | CREATE SEQUENCE, nextval, identity column | Có sequence độc lập; SERIAL/BIGSERIAL và GENERATED ... AS IDENTITY là các chiến lược liên quan nhưng khác về quản lý dependency |
| **Oracle Database** | CREATE SEQUENCE, sequence.NEXTVAL; identity ở phiên bản hỗ trợ | Cú pháp, quyền, cache, ORDER và vòng đời sequence phụ thuộc Oracle |
| **SQL Server** | CREATE SEQUENCE, NEXT VALUE FOR; IDENTITY | SEQUENCE khác IDENTITY, không được thay thế máy móc hai cơ chế |
| **MySQL/InnoDB** | AUTO_INCREMENT cho cột | Không có CREATE SEQUENCE tổng quát tương đương PostgreSQL; không mặc định dùng createSequence |
| **SQLite** | INTEGER PRIMARY KEY/rowid, tùy chọn AUTOINCREMENT | Không có đối tượng sequence độc lập theo kiểu PostgreSQL; không dùng lệnh CREATE SEQUENCE |

Một vài biến thể database khác có thể hỗ trợ đối tượng sequence theo cú pháp hoặc điều kiện riêng. Ngay cả khi Liquibase cung cấp change type **createSequence**, không có nghĩa change type đó được mọi DBMS hỗ trợ giống nhau.

Trước khi chọn một cú pháp, cần xác định ít nhất: **loại DBMS, phiên bản server, phiên bản Liquibase, driver JDBC, schema được dùng, quyền của tài khoản migration**, và yêu cầu tương thích với ORM. Khi cần dùng SQL chuyên biệt, khai báo điều kiện DBMS hoặc tách changelog phù hợp để không chạy nhầm trên cơ sở dữ liệu khác.

## 3. Tạo sequence bằng createSequence

Liquibase có change type **createSequence** để định nghĩa sequence theo cách khai báo. Ví dụ giả sử dùng PostgreSQL, schema mặc định đã được cấu hình và chưa có sequence tên **invoice_id_seq**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-invoice-sequence
      author: database-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - not:
            - sequenceExists:
                sequenceName: invoice_id_seq
      changes:
        - createSequence:
            sequenceName: invoice_id_seq
            startValue: 1000
            incrementBy: 1
            minValue: 1000
            cycle: false
      rollback:
        - dropSequence:
            sequenceName: invoice_id_seq
~~~

Những thuộc tính cốt lõi:

| Thuộc tính | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| **sequenceName** | Tên sequence cần tạo | Tên có thống nhất theo quy ước, schema và giới hạn định danh không? |
| **schemaName** (nếu dùng) | Schema chứa sequence | Tài khoản migration có quyền và search path có nhất quán không? |
| **startValue** | Giá trị bắt đầu khi cấp số | Có dữ liệu cũ đã sử dụng giá trị này chưa? |
| **incrementBy** | Bước tăng/giảm giá trị | ORM và các ứng dụng cùng dùng sequence có tương thích không? |
| **minValue/maxValue** | Giới hạn giá trị | Có đủ khoảng giá trị cho tăng trưởng dài hạn không? |
| **cycle** | Cho phép quay vòng khi đến giới hạn | Quay vòng có gây đụng khóa chính hoặc trùng mã không? |
| **cacheSize** | Số giá trị dự trữ theo cơ chế DBMS | Cân bằng hiệu năng, khoảng trống có thể xảy ra và vận hành như thế nào? |

Các thuộc tính có thể khác về hỗ trợ và cách biểu diễn theo DBMS/Liquibase. **ordered** hoặc những tùy chọn nâng cao khác nếu có cũng phải được kiểm tra theo nền tảng cụ thể; không sao chép thuộc tính Oracle sang PostgreSQL mà không xác minh.

**Precondition sequenceExists** được dùng ở đây để dừng nếu tên sequence đã tồn tại. Không nên tự động cấu hình **onFail: MARK_RAN** chỉ vì trùng tên: sequence sẵn có có thể có increment, min/max, cache, ownership hoặc quyền khác mong muốn. Nếu cần baseline, phải kiểm tra sự tương đương trước khi đánh dấu migration đã chạy.

**Rollback dropSequence** chỉ xóa đối tượng sequence khi database cho phép. Nó không “trả lại” các số đã cấp và không khôi phục dữ liệu đã dùng số đó. Nếu cột default hoặc đối tượng khác còn phụ thuộc vào sequence, dropSequence có thể bị từ chối. Khi tổ chức nhiều changeset, cần lên thứ tự rollback phù hợp.

## 4. Gắn sequence vào cột của bảng

Tạo sequence chưa có nghĩa mọi INSERT tự động sử dụng nó. Phải xác định **ai lấy số**: default của cột, cơ chế identity, ORM, hoặc ứng dụng.

Giả sử sequence đã được tạo ở changeset 001, ta tạo bảng hóa đơn với giá trị mặc định lấy từ sequence:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-create-invoice
      author: database-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - not:
            - tableExists:
                tableName: invoice
      changes:
        - createTable:
            tableName: invoice
            columns:
              - column:
                  name: id
                  type: bigint
                  defaultValueSequenceNext: invoice_id_seq
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_id
                  type: bigint
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: timestamp
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: invoice
~~~

Thuộc tính **defaultValueSequenceNext** mô tả default lấy giá trị sequence kế tiếp nếu change type và DBMS đang dùng hỗ trợ. Hãy kiểm tra SQL sinh ra bởi **liquibase update-sql**: với PostgreSQL, kết quả thường liên quan tới **nextval**; trên DBMS khác, Liquibase có thể không hỗ trợ biểu đạt này.

Có thể khai báo cùng hành vi bằng SQL riêng cho PostgreSQL khi cần điều khiển chi tiết:

~~~sql
ALTER TABLE invoice
ALTER COLUMN id SET DEFAULT nextval('invoice_id_seq');
~~~

Đoạn SQL trên giả sử cả bảng lẫn sequence có trong schema mà search path giải quyết đúng. Với môi trường nhiều schema, nên ghi rõ schema để tránh gắn nhầm sequence cùng tên ở schema khác.

**Quản lý ownership:** trong PostgreSQL, sequence tạo bằng CREATE SEQUENCE độc lập có thể không tự phụ thuộc vòng đời vào cột. Nếu muốn sequence được gắn về mặt sở hữu đối tượng với cột, có thể dùng:

~~~sql
ALTER SEQUENCE invoice_id_seq OWNED BY invoice.id;
~~~

Lệnh này có yêu cầu về quyền sở hữu/schema và làm thay đổi quan hệ phụ thuộc đối tượng. Khi xóa bảng/cột, sequence có thể bị xóa theo dependency. Vì thế khi viết rollback, phải cân nhắc thứ tự xóa default, bảng và sequence; không dùng **DROP ... CASCADE** chỉ để vượt lỗi mà chưa xem các đối tượng bị ảnh hưởng.

### Sequence, SERIAL và IDENTITY khác nhau thế nào?

Trong PostgreSQL, **SERIAL/BIGSERIAL** là cách khai báo thuận tiện khiến database tạo sequence và default liên quan; **GENERATED ... AS IDENTITY** là cơ chế identity theo chuẩn SQL với metadata/semantics riêng; **CREATE SEQUENCE** tạo đối tượng độc lập để bạn chủ động gắn vào cột hoặc cho ứng dụng sử dụng. Chọn một chiến lược rõ ràng, tránh tạo trùng sequence thủ công bên cạnh sequence database đã tự sinh cho cùng cột.

Tương tự, **AUTO_INCREMENT** của MySQL hay **IDENTITY** của SQL Server là cơ chế cấp số gắn với cột; không đồng nghĩa có đối tượng sequence độc lập với tên tương ứng để Liquibase có thể thay đổi bằng **alterSequence**.

## 5. Đọc giá trị sequence và hiểu hành vi transaction

Với PostgreSQL:

~~~sql
-- Lấy một giá trị kế tiếp và tiêu thụ giá trị đó
SELECT nextval('invoice_id_seq');

-- Đọc giá trị sequence hiện tại qua đối tượng sequence
SELECT last_value, is_called
FROM invoice_id_seq;
~~~

**nextval** cấp một giá trị mới cho lần gọi đó. Việc kiểm tra sequence bằng cách chạy nextval trên production có thể làm phát sinh khoảng trống số mà ứng dụng không hề dùng; không nên dùng nó như truy vấn chỉ đọc.

**currval** trên PostgreSQL trả lại giá trị đã được **nextval** cấp trong **phiên kết nối hiện tại** cho sequence đó; nếu phiên này chưa gọi nextval cho sequence, currval sẽ báo lỗi. Nó không phải cách đọc “ID cuối cùng toàn hệ thống”.

**last_value** từ đối tượng sequence có thể phản ánh trạng thái dự trữ/cache thay vì giá trị cuối cùng đã được INSERT thành công. Với DBMS có cache, không thể dựa đơn giản vào last_value để suy ra số lớn nhất hiện có trong bảng. Để kiểm tra dữ liệu thật, dùng MAX(id) ở bảng nghiệp vụ, kết hợp metadata của sequence và hiểu các writer đang hoạt động.

Ba hệ quả thực tiễn:

1. **Rollback transaction không thu hồi số đã cấp.** Một INSERT bị rollback vẫn có thể khiến lần cấp tiếp theo nhảy số.
2. **Cấp số đồng thời không có nghĩa thứ tự commit đồng thời.** Transaction nhận số nhỏ hơn có thể commit sau transaction nhận số lớn hơn.
3. **Cache và chu kỳ sống của database có thể tạo khoảng trống.** Tăng cacheSize có thể giúp giảm chi phí cấp số trong một số DBMS, nhưng không thể dùng sequence để bảo đảm chuỗi số liên tục.

Nếu nghiệp vụ yêu cầu đánh số chứng từ có kiểm toán không bỏ số, cần thiết kế riêng quy trình phát hành số, transaction, hủy số, báo cáo và yêu cầu pháp lý; không mặc định lấy ID sequence làm số chứng từ chính thức.

## 6. Sửa sequence bằng alterSequence

Khi tải tăng, có thể cần điều chỉnh **cacheSize**, **incrementBy**, giới hạn hoặc các thuộc tính được hỗ trợ bởi DBMS. Liquibase cung cấp **alterSequence** cho những thay đổi mà nền tảng hỗ trợ.

Ví dụ tăng cache của sequence PostgreSQL đã tồn tại từ 1 lên 20, giả sử giá trị cũ đã được xác nhận:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-tune-invoice-sequence-cache
      author: database-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - sequenceExists:
            sequenceName: invoice_id_seq
      changes:
        - alterSequence:
            sequenceName: invoice_id_seq
            cacheSize: 20
      rollback:
        - alterSequence:
            sequenceName: invoice_id_seq
            cacheSize: 1
~~~

Rollback ở đây phục hồi **thuộc tính cache đã biết**; nó không khôi phục các giá trị đã tiêu thụ hay đưa số quay về mốc ban đầu. Nếu cache ban đầu của môi trường không phải 1, rollback minh họa này không phù hợp. Cần xác nhận cấu hình trước migration và triển khai cùng cấu hình kỳ vọng qua các môi trường.

### Vì sao thay incrementBy cần cẩn thận?

Giả sử sequence dùng cho Hibernate với **allocationSize**. Đổi **incrementBy** từ 1 thành 50 trong database mà không đánh giá cấu hình của ORM có thể gây lỗi kiểm tra schema, sai giả định của ID generator hoặc cách cấp số khó dự đoán. Ngay cả khi SQL migration hợp lệ, ứng dụng vẫn có thể khởi động lỗi hoặc cấp ID không như thiết kế.

**cacheSize của DBMS không đồng nhất với allocationSize của ORM.** Cache sequence là tối ưu hóa phía database; allocationSize là cách trình sinh ID của ORM phân bổ hoặc dự trữ ID. Cách hai giá trị tương tác phụ thuộc loại generator, phiên bản Hibernate và chiến lược optimizer. Khi đổi một trong hai, hãy kiểm tra trường hợp nhiều instance ứng dụng, ứng dụng cũ đang chạy song song, khả năng tương thích và giá trị thực tế được cấp.

### Có nên bật cycle?

Với sequence dùng cho PRIMARY KEY, **cycle: true** có nguy cơ quay lại giá trị đã tồn tại nếu dãy số chạm giới hạn, gây lỗi unique key. Hầu hết trường hợp cấp ID nên dùng dải số đủ lớn và **không quay vòng**. Cần theo dõi dung lượng còn lại của kiểu dữ liệu, kế hoạch tăng trưởng và chiến lược mở rộng trước khi cạn giá trị.

## 7. Đồng bộ sequence với dữ liệu có sẵn

Khi nhập dữ liệu lịch sử, khôi phục từ backup hoặc chuyển đổi từ ID tự sinh sang sequence riêng, **giá trị kế tiếp** có thể thấp hơn ID lớn nhất đang tồn tại. Khi đó INSERT mới có thể bị trùng khóa chính.

Ví dụ PostgreSQL:

~~~sql
SELECT MAX(id) AS max_id
FROM invoice;

SELECT sequencename, start_value, min_value,
       max_value, increment_by, cache_size, cycle
FROM pg_sequences
WHERE schemaname = 'public'
  AND sequencename = 'invoice_id_seq';
~~~

Đầu tiên cần kiểm tra kiểu ID, số hàng, sequence mặc định đang dùng và sự có mặt của nhiều writer. Nếu phải đặt lại trạng thái sequence trong PostgreSQL, có thể dùng **setval** hoặc lệnh **ALTER SEQUENCE ... RESTART** theo kế hoạch và ngữ nghĩa transaction của phiên bản DBMS.

Ví dụ thao tác quản trị đã xác nhận **MAX(invoice.id) = 2400**, không có writer đồng thời và giá trị tiếp theo cần là **2401**:

~~~sql
SELECT setval('invoice_id_seq', 2400, true);
~~~

Trong PostgreSQL, tham số **true** cho biết giá trị đặt đã được coi như đã gọi, nên lần nextval tiếp theo tăng theo increment. Nhưng **setval không có tác dụng rollback transaction theo cách thông thường**; không nên đặt lại sequence thấp hơn những ID có thể đã cấp hoặc thấp hơn dữ liệu đang tồn tại. Nếu bảng trống hoặc có dữ liệu thấp hơn minValue, cần thiết kế riêng giá trị bắt đầu và cách dùng tham số is_called; không sao chép con số trong ví dụ sang production.

**Cạnh tranh dữ liệu là rủi ro lớn:** giữa truy vấn MAX(id) và setval, một writer khác có thể cấp giá trị mới. Hãy kiểm soát writer, khóa/phạm vi bảo trì hoặc dùng quy trình chuyển đổi đảm bảo không ai cùng cấp ID trong giai đoạn đồng bộ. Kiểm tra lại khả năng INSERT ngay sau migration trên database thử nghiệm và có kế hoạch phục hồi.

Nếu cần quản lý bước đồng bộ này bằng Liquibase, hãy dùng một changeset có SQL chuyên biệt PostgreSQL, precondition về schema/data phù hợp và ghi rõ tính không đảo ngược. Không đánh dấu rollback “trả lại giá trị cũ” nếu việc đó có thể cấp lại các ID đã được dùng sau migration.

## 8. Tích hợp với Spring Boot và JPA/Hibernate

Khi Liquibase sở hữu schema, Spring Boot có thể cấu hình:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Trong entity dùng JPA, có thể khai báo generator lấy giá trị từ sequence đã do Liquibase tạo:

~~~java
@Entity
@Table(name = "invoice")
public class Invoice {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "invoice_id_generator"
    )
    @SequenceGenerator(
        name = "invoice_id_generator",
        sequenceName = "invoice_id_seq",
        allocationSize = 1
    )
    private Long id;

    // Các thuộc tính nghiệp vụ khác
}
~~~

Đây là ví dụ mô tả mapping, giả sử các annotation và import JPA đã có. Giá trị **allocationSize=1** được chọn để dễ hiểu với sequence **incrementBy=1** trong ví dụ. Với ứng dụng thực tế, hãy kiểm tra phiên bản Hibernate, optimizer, schema, quyền sequence và SQL phát sinh; việc dùng allocationSize lớn hơn cần được thiết kế đồng bộ với cách tạo sequence.

Khi JPA sinh ID bằng **GenerationType.SEQUENCE**, Hibernate có thể lấy giá trị sequence trước INSERT rồi gửi ID tường minh. Nếu cột đồng thời có **DEFAULT nextval(...)**, default chỉ được sử dụng khi INSERT không truyền giá trị ID theo quy tắc DBMS. Đây có thể là chủ đích để hỗ trợ SQL bên ngoài ORM, nhưng cần tránh cho các thành phần dùng các sequence khác nhau hoặc tự sinh ID theo hai chính sách xung đột.

Nếu database không hỗ trợ sequence độc lập như PostgreSQL, hãy chọn cơ chế identity phù hợp của DBMS và mapping JPA tương ứng. Không cố chạy createSequence trên MySQL chỉ để giữ giống nguyên ví dụ PostgreSQL.

Khi dùng CI/CD chạy migration riêng, cấu hình runtime ứng dụng để không tự chạy lại Liquibase ngoài chủ đích; còn với mô hình chạy migration khi khởi động, cần kiểm soát nhiều replica và giám sát DATABASECHANGELOGLOCK.

## 9. Quản lý các đối tượng đặc thù DBMS

Ngoài sequence, ứng dụng thường dùng đối tượng mà Liquibase không có change type chung đầy đủ hoặc ngữ nghĩa có nhiều khác biệt.

| Đối tượng | Ví dụ mục đích | Hướng quản lý |
|---|---|---|
| **View** | Đóng gói một truy vấn và quyền đọc | Dùng createView/dropView khi DBMS và định nghĩa hỗ trợ; hoặc SQL riêng |
| **Materialized view** | Lưu kết quả truy vấn để đọc nhanh | Thường cần SQL DBMS riêng, chính sách refresh, index và rollback |
| **Function/Stored procedure** | Logic chạy trong database | Dùng change type phù hợp khi được hỗ trợ; SQL hoặc sqlFile cho cú pháp chuyên biệt |
| **Trigger** | Phản ứng trước/sau INSERT/UPDATE/DELETE | SQL riêng; chú ý thứ tự tạo hàm trigger và trigger, quyền, tác động DML |
| **ENUM/UDT/domain** | Kiểu dữ liệu riêng và ràng buộc giá trị | SQL DBMS riêng, kiểm tra phụ thuộc khi sửa/xóa kiểu |
| **Extension/package** | Tính năng mở rộng hoặc thư viện database | SQL riêng, có thể đòi quyền cao và chính sách vận hành riêng |
| **Partition/table inheritance** | Phân vùng dữ liệu lớn | Cần đánh giá cú pháp, index, khóa, constraint, lịch vận hành theo DBMS |
| **Policy/RLS** | Giới hạn quyền đọc/ghi theo hàng | SQL và quyền riêng DBMS, kiểm thử với vai trò ứng dụng thực |

Không có một thiết kế SQL chung chạy chính xác trên mọi loại database cho các đối tượng này. Changelog có thể dùng **dbms**, contexts, labels và các include rõ ràng để triển khai định nghĩa phù hợp từng môi trường, trong khi vẫn giữ lịch sử changeset có thể review.

### Ví dụ function PostgreSQL bằng sql

Giả sử muốn tạo hàm chuẩn hóa email dùng lại trong SQL. PL/pgSQL và nhiều định nghĩa function có dấu chấm phẩy bên trong; cần lưu ý công cụ tách câu lệnh.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-normalize-email-function
      author: database-team
      dbms: postgresql
      runOnChange: true
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE OR REPLACE FUNCTION normalize_email(p_input text)
              RETURNS text
              LANGUAGE sql
              AS $function$
                SELECT lower(btrim(p_input));
              $function$;
      rollback:
        - sql:
            sql: |
              DROP FUNCTION IF EXISTS normalize_email(text);
~~~

Trong ví dụ này:

- **dbms: postgresql** ngăn việc chạy định nghĩa riêng PostgreSQL trên DBMS khác.
- **splitStatements: false** để Liquibase gửi toàn bộ đoạn SQL cho driver theo cách phù hợp với cú pháp function và dấu chấm phẩy bên trong.
- **runOnChange: true** cho phép chạy lại khi nội dung function được sửa, bởi câu lệnh **CREATE OR REPLACE FUNCTION** được thiết kế cho việc cập nhật định nghĩa tương thích.
- **rollback** xóa function; điều này chỉ hợp lệ nếu không có đối tượng đang phụ thuộc và việc xóa thực sự là điều mong muốn. Khi function đã được sử dụng bởi view, trigger hoặc query, cần lên thứ tự migration/rollback cẩn thận.

Không phải mọi sửa đổi function đều có thể **CREATE OR REPLACE** an toàn; thay đổi kiểu trả về hoặc signature có thể đòi drop và tạo lại, đồng thời ảnh hưởng dependency và quyền truy cập. Khi chỉ sửa function để triển khai lại định nghĩa, runOnChange có thể phù hợp; với thay đổi schema một lần, nên tạo changeset mới.

### Khi nào dùng sqlFile?

Khi nội dung procedure, trigger, view phức tạp dài hàng trăm dòng, có thể lưu SQL thành file được version hóa và tham chiếu bằng **sqlFile** trong changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 011-deploy-report-procedure
      author: database-team
      dbms: postgresql
      runOnChange: true
      changes:
        - sqlFile:
            path: sql/report_procedure.sql
            relativeToChangelogFile: true
            splitStatements: false
~~~

Ví dụ giả định file **sql/report_procedure.sql** tồn tại cạnh thư mục changelog theo đường dẫn đã chỉ định. Khi dùng sqlFile, phải quản lý đường dẫn và nội dung SQL cùng mã nguồn. Hãy review tác động của những tùy chọn như **splitStatements**, **endDelimiter** và **stripComments** theo phiên bản Liquibase/DBMS; cấu hình sai có thể tách nhầm câu lệnh trong một procedure hoặc trigger.

Nếu rollback không thể biểu diễn an toàn, cần ghi rõ kế hoạch sửa tiến về phía trước hoặc chuẩn bị SQL rollback riêng được kiểm thử. Không tự giả định SQL tự do có rollback tự động như một số change type khai báo.

## 10. Kiểm soát schema, quyền và thứ tự phụ thuộc

Nhiều lỗi không đến từ cú pháp Liquibase mà từ **vị trí đối tượng** và **thứ tự tạo**:

1. **Schema:** sequence, table, function và trigger có thể cùng tên ở các schema khác nhau. Khai báo schemaName khi cần và thống nhất search path; không dựa vào cấu hình mặc định thay đổi giữa development và production.
2. **Quyền:** tài khoản migration cần quyền tạo/sửa đối tượng; tài khoản runtime cần quyền phù hợp để sử dụng sequence hoặc thực thi function. Với PostgreSQL, quyền dùng sequence và quyền INSERT vào bảng là những vấn đề riêng có thể phải cấp bổ sung.
3. **Phụ thuộc:** sequence phải tồn tại trước default dùng nextval; bảng phải tồn tại trước trigger; trigger function cần tồn tại trước khi tạo trigger; view phụ thuộc vào bảng và function đang được tham chiếu.
4. **Rollback ngược thứ tự:** thường phải tháo trigger trước khi xóa function; bỏ default hoặc xóa bảng trước khi drop sequence nếu dependency yêu cầu. Đừng dùng DROP ... CASCADE mà không xem danh sách đối tượng bị xóa.
5. **Tên định danh:** dùng quy ước tên ổn định, tránh đổi tên file changelog hoặc di chuyển changeset đã chạy vì đường dẫn tham gia định danh changeset.
6. **Tương thích đa phiên bản:** ứng dụng cũ và mới có thể cùng dùng database trong lúc triển khai cuốn chiếu. Đừng xóa sequence/function mà phiên bản ứng dụng cũ còn sử dụng.

Sơ đồ quan hệ phụ thuộc đơn giản:

~~~text
invoice_id_seq ----> invoice.id DEFAULT
                           |
invoice table ------------> report view
                           |
                           +--> trigger ----> trigger function
~~~

Nếu release thay đổi toàn bộ chuỗi này, hãy tách các bước mở rộng, chuyển đổi, xác minh và thu hẹp khi cần. Cùng một changeset lớn làm tất cả có thể khó rollback và khó xác định điểm thất bại.

## 11. Precondition, checksum và runOnChange cho đối tượng đặc thù

**Precondition** giúp kiểm tra các giả định như **sequenceExists**, **tableExists**, **viewExists** hoặc truy vấn SQL kiểm tra dữ liệu. Những kiểm tra đó chỉ xác nhận một phần trạng thái: **sequenceExists** không chứng minh cấu hình increment/cache đúng; **viewExists** không chứng minh định nghĩa SELECT đúng; **tableExists** không chứng minh schema/dữ liệu đạt yêu cầu.

Với điều kiện bắt buộc, chọn **onFail: HALT** và **onError: HALT** để dừng khi sai giả định hoặc không kiểm tra được. Chỉ dùng **MARK_RAN** cho baseline đã chứng minh đối tượng hiện có tương đương thay đổi cần tạo; không dùng như mẹo bỏ qua lỗi.

Sau khi chạy, Liquibase ghi changeset vào **DATABASECHANGELOG** cùng checksum. Khi đã deploy changeset tạo sequence, không sửa lại **startValue** hay **incrementBy** trong chính changeset cũ; hãy tạo changeset **alterSequence** mới. Nếu sửa định nghĩa cũ, checksum có thể lệch giữa các môi trường và lịch sử sẽ khó đối chiếu.

**runOnChange** phù hợp với một số view/function/procedure dùng cú pháp thay thế định nghĩa an toàn. Nó không phải lựa chọn mặc định để chạy lại **createSequence**, **dropSequence** hoặc dữ liệu backfill. **runAlways** càng cần kiểm soát vì chạy mỗi lần update phù hợp dù không đổi mã nguồn. Đặt hai cờ này bừa bãi dễ làm lặp lại thao tác phá hủy hoặc mất kiểm soát trạng thái.

Khi một đối tượng đã được tạo trực tiếp ngoài Liquibase mà nội dung changelog chưa thay đổi, runOnChange không tự phát hiện schema drift. Muốn phát hiện drift, cần dùng metadata query, diff hoặc kiểm thử thực tế theo DBMS.

## 12. Quy trình kiểm chứng trên PostgreSQL

Giả sử đã cấu hình Liquibase CLI và JDBC driver cho database thử nghiệm. Dùng cùng changelog đã review và chạy:

~~~shell
liquibase validate
liquibase update-sql
liquibase update
liquibase status --verbose
~~~

**validate** kiểm tra cấu trúc changelog và những tham chiếu có thể xác thực; nó không chứng minh SQL được DBMS đích chấp nhận hay quyền đã đủ. **update-sql** giúp xem SQL sẽ được phát sinh mà chưa áp dụng thay đổi. **update** thực thi changeset; **status --verbose** hỗ trợ quan sát những changeset còn chờ.

Sau update, có thể kiểm tra sequence bằng metadata PostgreSQL:

~~~sql
SELECT schemaname, sequencename,
       start_value, min_value, max_value,
       increment_by, cycle, cache_size
FROM pg_sequences
WHERE schemaname = 'public'
  AND sequencename = 'invoice_id_seq';
~~~

Để kiểm tra cột có gắn default sequence:

~~~sql
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'invoice'
  AND column_name = 'id';
~~~

Nếu ứng dụng dùng JPA lấy ID trước khi INSERT, hãy thử tạo bản ghi qua ứng dụng và kiểm tra ID được cấp, không chỉ đọc column_default. Đối với function ở phần 9, có thể gọi trên test database:

~~~sql
SELECT normalize_email('  HELLO@EXAMPLE.COM  ');
~~~

Kết quả kỳ vọng là **hello@example.com**. Kiểm tra thêm phân quyền với đúng tài khoản runtime và thử các tham số đặc biệt mà nghiệp vụ chấp nhận.

Lịch sử Liquibase có thể kiểm tra qua:

~~~sql
SELECT id, author, filename, exectype, md5sum, dateexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Khi kiểm tra **DBMS-specific SQL**, chạy trên phiên bản DBMS thực mà pipeline production dùng. Một câu SQL hợp lệ khi parse changelog chưa chắc thành công vì quyền, dependency, extension chưa được cài hoặc khác biệt phiên bản.

Để kiểm tra rollback, dùng database thử nghiệm độc lập hoặc bản sao dữ liệu phù hợp, review SQL rollback và theo dõi phụ thuộc. Không thử drop sequence/function trực tiếp trên production đang có writer.

## 13. Baseline sequence và đối tượng đã tồn tại

Không phải dự án nào cũng bắt đầu với database rỗng. Nếu schema đã tồn tại do SQL thủ công, ORM hoặc hệ thống khác, cần đối chiếu trước khi để Liquibase tiếp quản.

Quy trình baseline:

1. **Kiểm kê:** ghi nhận các sequence, owner, min/max, increment, cache, cycle, default của cột, quyền, function, trigger và view đang tồn tại.
2. **Xác nhận quan hệ phụ thuộc:** sequence nào phục vụ cột nào, function/trigger nào đang được gọi, có ứng dụng hoặc job bên ngoài đang dùng không.
3. **So sánh với changelog mong muốn:** một đối tượng cùng tên nhưng khác cấu hình chưa đủ điều kiện để coi migration tạo đối tượng đã hoàn thành.
4. **Quyết định cách ghi lịch sử:** nếu trạng thái hiện tại đã tương đương, xem xét cơ chế baseline/changelog-sync với phạm vi được kiểm soát. Nếu còn khác biệt, tạo changeset chuyển đổi hoặc sửa tiến về phía trước.
5. **Kiểm tra trên bản sao:** chạy migrate, kiểm tra ID mới không đụng dữ liệu cũ và các object khác còn tương thích.
6. **Ghi nhận chứng cứ:** lưu SQL kiểm tra, version nguồn, mã changeset và kết quả để giải thích trạng thái staging/production.

**changelog-sync** ghi nhận changeset đã được xử lý mà không thực thi thay đổi; nếu dùng sai sẽ tạo lịch sử “đã chạy” trong khi sequence hoặc function thực tế vẫn thiếu. **clear-checksums** không sửa sự khác biệt schema; **validCheckSum** cũng không tự áp dụng SQL còn thiếu.

Với sequence đang sử dụng, phải tránh tạo thêm đối tượng trùng chức năng hoặc reset về giá trị thấp. Baseline cần đặc biệt chú ý writer đang chạy và chiến lược cấp số của Hibernate/ứng dụng khác.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý có kiểm chứng |
|---|---|---|
| createSequence không hỗ trợ | DBMS không có sequence độc lập hoặc Liquibase change type không hỗ trợ | Chọn identity/auto-increment hoặc SQL phù hợp DBMS; kiểm tra support |
| Sequence đã tồn tại | Khởi tạo trước bằng ORM/SQL, hoặc cùng tên khác schema | Kiểm kê metadata, đối chiếu cấu hình, không tự MARK_RAN |
| INSERT trùng khóa chính | Sequence cấp giá trị thấp hơn dữ liệu, nhiều nguồn cấp ID khác nhau | Kiểm tra MAX(id), writer, mapping, đồng bộ sequence có kiểm soát |
| ID có khoảng trống | Rollback, lỗi INSERT, cache, concurrent allocations | Xem đó là đặc tính bình thường nếu chỉ dùng surrogate key |
| Hibernate báo lệch increment/allocation | Generator/optimizer và sequence cấu hình không tương thích | Đối chiếu allocationSize, incrementBy và version Hibernate |
| App thiếu quyền sequence | Quyền INSERT bảng không đủ cho nextval | Cấp quyền sequence chính xác cho tài khoản runtime |
| Drop sequence thất bại | Default hoặc object khác phụ thuộc sequence | Kiểm tra dependency, lên thứ tự rollback, tránh DROP CASCADE tùy tiện |
| Function SQL bị tách sai | Có nhiều dấu chấm phẩy, delimiters không phù hợp | Kiểm tra splitStatements/endDelimiter và thử trên DBMS đích |
| Procedure/function không thay thế được | Đổi signature/return type hoặc dependency không cho phép | Lập migration riêng, quản lý phụ thuộc và rollback |
| SQL chạy trên DBMS sai | Thiếu dbms filter hoặc script chưa được phân nhánh | Dùng dbms/contexts/labels có chủ đích và test trên mọi DBMS được hỗ trợ |
| Checksum không khớp | Sửa changeset đã chạy | Khôi phục định nghĩa cũ hoặc tạo changeset mới; điều tra trước khi xử lý checksum |
| Rollback gây mất dữ liệu/đối tượng | DROP TABLE/SEQUENCE/TYPE kèm dependency hoặc đã cấp giá trị | Review SQL và phụ thuộc, dùng forward-fix/backup khi cần |

Cần phân biệt lỗi precondition **onFail/onError**, lỗi phát sinh khi chạy DDL, lỗi quyền và lỗi checksum. Không thể dùng một cấu hình bỏ qua lỗi để giải quyết tất cả vì mỗi loại báo hiệu vấn đề khác nhau.

## 15. Tình huống tổng hợp: tách ID hóa đơn khỏi cơ chế tự sinh cũ

Giả sử ứng dụng ban đầu dùng một cách cấp ID tự động; nhóm muốn chuyển sang sequence **invoice_id_seq** do Liquibase quản lý và đồng thời bổ sung function tính toán định dạng dữ liệu. Dự án có nhiều môi trường và một số bảng đã có hàng triệu bản ghi.

Một hướng triển khai hợp lý:

1. **Làm rõ hiện trạng:** cơ chế identity/sequence cũ là gì, có API nào lấy ID trước INSERT không, có job SQL chạy trực tiếp không, có nhiều replica đang ghi không.
2. **Đối chiếu dữ liệu:** kiểm tra MAX(invoice.id), kiểu dữ liệu, unique constraint và sequence hiện có để tránh tạo bộ sinh số trùng hoặc hai nguồn cấp song song.
3. **Thiết kế trạng thái đích:** xác định một generator chính thức, tên/schema, giá trị tiếp theo an toàn, increment/cache và mapping Hibernate.
4. **Viết changelog mới theo thứ tự:** tạo sequence (nếu chưa tồn tại), điều chỉnh default của cột hoặc mapping trong giai đoạn tương thích, tạo function với script DBMS phù hợp; không sửa changeset cũ đã chạy.
5. **Chuẩn bị kiểm soát writer:** kế hoạch bảo trì, đồng bộ sequence với dữ liệu có sẵn dưới điều kiện không có cấp số song song, xác minh quyền và dependency.
6. **Thử trên bản sao database:** validate, update-sql, update; thực hiện nhiều INSERT từ JPA và SQL trực tiếp, kiểm tra không đụng khóa, test function và thử rollback phù hợp.
7. **Triển khai theo phiên bản:** thay đổi schema và phiên bản ứng dụng theo kế hoạch expand/migrate/contract để tránh ứng dụng cũ dùng cơ chế ID khác trong thời gian chuyển tiếp.
8. **Xác minh sau triển khai:** kiểm tra DATABASECHANGELOG, metadata sequence, cột default, số ID lớn nhất, log lỗi unique và kết quả chạy của function trên từng môi trường.

Không nên cam kết rollback sequence về một giá trị cũ sau khi đã cấp ID cho người dùng. Khi phát hiện rủi ro cấp ID trùng, ưu tiên dừng writer và sửa tiến về phía trước bằng giá trị an toàn sau khi điều tra.

## 16. Checklist thiết kế và phát hành

- [ ] Xác định rõ DBMS, phiên bản server, Liquibase/JDBC và loại cơ chế tạo ID được hỗ trợ.
- [ ] Sequence có tên/schema, start, increment, min/max, cache và cycle có chủ đích.
- [ ] Kiểm tra sequence có tồn tại ở môi trường đích và cấu hình hiện tại có khớp mong muốn không.
- [ ] Có PK/UNIQUE bảo vệ dữ liệu; không lấy khả năng cấp số của sequence làm bảo đảm uniqueness duy nhất.
- [ ] Thống nhất cách dùng sequence giữa default/identity, ORM và SQL trực tiếp.
- [ ] Khi có dữ liệu cũ, đã kiểm tra MAX(id), writer đồng thời và kế hoạch đồng bộ không cấp ID trùng.
- [ ] Không kỳ vọng sequence liên tục, rollback được số đã cấp hoặc phản ánh thứ tự commit.
- [ ] SQL đối tượng đặc thù đã được giới hạn DBMS và quản lý dependency, quyền, rollback.
- [ ] Đã xem kết quả validate/update-sql và thử update trên DBMS tương thích.
- [ ] Đã kiểm tra precondition, checksum và lịch sử DATABASECHANGELOG, không sửa changeset đã triển khai.
- [ ] Đã thử tương thích Spring Boot/JPA và job CI/CD, xác định tiến trình chịu trách nhiệm migration.
- [ ] Đã có bằng chứng kiểm tra và phương án sửa tiến về phía trước nếu rollback không an toàn.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, quản lý sequence hiệu quả đòi hỏi hiểu cơ chế cấp số thực tế của DBMS, viết changeset có thứ tự và giữ các thay đổi đã triển khai bất biến. Đối với function, view, trigger, type, extension và những đối tượng đặc thù khác, hãy dùng change type Liquibase khi phù hợp, SQL riêng của DBMS khi cần, đồng thời luôn kiểm chứng quyền, phụ thuộc và hành vi thực tế. Nhờ kết hợp changelog, precondition, checksum, lịch sử triển khai, rollback/forward-fix và CI/CD, các môi trường có thể tiến hóa schema một cách dự đoán được mà không làm mất khả năng truy vết.
