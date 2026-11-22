# Ranh giới giao dịch của changeset và hành vi khi có lỗi

Một câu hỏi quan trọng khi chạy Liquibase là: **nếu changeset chứa nhiều thao tác, thao tác thứ ba thất bại thì hai thao tác trước có bị hoàn tác không?** Không thể trả lời chỉ bằng việc changelog có `rollback` hoặc ứng dụng đang sử dụng transaction. Kết quả thực tế còn phụ thuộc vào phạm vi transaction mà Liquibase mở, thuộc tính `runInTransaction`, khả năng hỗ trợ transactional DDL của DBMS và thời điểm database ghi nhận thành công.

Bài học thuộc chương **Giao dịch và khóa** của module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`. Mục tiêu module là quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trong phạm vi đó, bài này giải thích **ranh giới giao dịch của changeset**, hành vi khi migration gặp lỗi và cách kiểm tra trạng thái trước khi tiếp tục triển khai.

## 1. Các khái niệm dễ nhầm

| Khái niệm | Tác dụng | Điều không được suy diễn |
|---|---|---|
| **Changeset** | Đơn vị thay đổi Liquibase nhận diện bằng `id`, `author` và đường dẫn changelog. | Một changelog không mặc nhiên là một transaction duy nhất. |
| **Transaction của changeset** | Gom các câu lệnh phù hợp trong một phạm vi commit/rollback nếu DBMS và lệnh SQL hỗ trợ. | Không đảm bảo mọi DDL có thể bị rollback trên mọi DBMS. |
| **`runInTransaction`** | Điều khiển yêu cầu Liquibase chạy changeset trong transaction khi có thể. | `true` không thể bắt MySQL/Oracle rollback DDL vốn tự commit. |
| **`DATABASECHANGELOG`** | Ghi nhận lịch sử changeset, checksum và trạng thái thực thi. | Không phải bản sao toàn bộ schema hoặc bằng chứng mọi lệnh đã hoàn tác khi có lỗi. |
| **`DATABASECHANGELOGLOCK`** | Điều phối tránh nhiều tiến trình Liquibase cùng quản lý migration trên một database. | Không khóa toàn bộ hoạt động đọc/ghi của ứng dụng. |
| **Rollback SQL của Liquibase** | Các thao tác đảo ngược được gọi có chủ đích bởi lệnh rollback. | Không có nghĩa Liquibase tự gọi lệnh rollback mỗi khi `update` lỗi. |
| **Rollback của database transaction** | DBMS hủy các thao tác *chưa commit* mà transaction thực sự bao phủ. | Không khôi phục được DDL đã tự commit hoặc tác động ngoài transaction. |

Phân biệt hai nghĩa của “rollback” là trọng tâm:

1. **Rollback transaction do lỗi:** DBMS hủy các thay đổi chưa commit khi transaction bị rollback.
2. **Liquibase rollback command:** thao tác triển khai ngược một hoặc nhiều changeset theo tag, số lượng, ngày hoặc cơ chế phù hợp; cần định nghĩa rollback và điều kiện thực thi tương ứng.

Hai cơ chế có thể cùng xuất hiện trong một quy trình vận hành nhưng **không thay thế nhau**.

## 2. Đơn vị transaction mặc định là changeset, không phải toàn changelog

Trong Liquibase, mặc định một changeset có `runInTransaction="true"`. Nếu database và loại lệnh hỗ trợ, Liquibase thực hiện các thay đổi thuộc changeset trong transaction và commit khi changeset hoàn tất. Khi một thay đổi trong changeset lỗi, Liquibase có thể rollback transaction chứa các thao tác chưa commit của **changeset đó**.

Ví dụ changelog chứa:

~~~text
master.xml
  changeset 001: tạo bảng product
  changeset 002: thêm cột + cập nhật dữ liệu
  changeset 003: tạo index
~~~

Nếu `001` thành công và commit, `002` thất bại, **không được giả định** `001` sẽ bị rollback chỉ vì cùng nằm trong `master.xml`. `003` thông thường chưa được thực thi do `update` dừng tại lỗi. Trên một DBMS hỗ trợ transaction đầy đủ đối với các lệnh của `002`, các thao tác chưa commit bên trong `002` có thể được rollback. Trên DBMS có DDL tự commit, có thể tồn tại thay đổi của `002` dù Liquibase đã báo lỗi.

### 2.1. Luồng xử lý khái quát

~~~mermaid
flowchart TD
    A[Đọc changelog và kiểm tra cấu hình] --> B[Giành khóa DATABASECHANGELOGLOCK]
    B --> C[Đối chiếu DATABASECHANGELOG và bộ lọc]
    C --> D{Changeset cần chạy?}
    D -->|Không| M[Xét changeset tiếp theo]
    D -->|Có| E[Kiểm tra preconditions thích hợp]
    E --> F{Được phép thực thi?}
    F -->|Không| N[Áp dụng onFail hoặc onError]
    F -->|Có| G[Thực thi các change theo cấu hình transaction]
    G --> H{Tất cả change thành công?}
    H -->|Có| I[Hoàn tất transaction và ghi lịch sử theo cơ chế Liquibase]
    I --> M
    H -->|Không| J[Thử rollback phần transaction chưa commit nếu có thể]
    J --> K[Báo lỗi và dừng, cần kiểm tra trạng thái thật]
    M --> L{Còn changeset?}
    L -->|Có| C
    L -->|Không| O[Kết thúc và giải phóng khóa]
    K --> P[Xử lý lỗi và khóa theo kết quả thực tế]
~~~

Đây là **sơ đồ khái niệm**, không mô tả chính xác mọi lời gọi JDBC hoặc thứ tự ghi metadata của từng phiên bản. Trong thực tế Liquibase còn xử lý checksum, change execution listeners, context/label, DBMS filters, validation và việc dọn khóa. Quan trọng là **kết quả “update failed” không chứng minh database đã trở về trạng thái cũ**.

### 2.2. `runInTransaction` đặt ở đâu?

Đây là **thuộc tính của changeset**. Ví dụ XML:

~~~xml
<changeSet id="2026-11-add-status" author="db-team"
           runInTransaction="true">
    <addColumn tableName="customer_record">
        <column name="status" type="VARCHAR(20)"/>
    </addColumn>
    <sql>
        UPDATE customer_record
        SET status = 'ACTIVE'
        WHERE status IS NULL
    </sql>
</changeSet>
~~~

Đoạn này nằm trong `databaseChangeLog` hợp lệ và giả định bảng `customer_record` đã tồn tại. Liquibase sẽ yêu cầu chạy trong transaction theo mặc định, nhưng **khả năng hủy DDL `addColumn` phụ thuộc DBMS**. Trên một số hệ, thêm cột có thể commit độc lập trước khi lệnh `UPDATE` gặp lỗi.

Đừng nhầm `runInTransaction` với transaction của ứng dụng `@Transactional` trong Spring. Liquibase thường chạy qua cơ chế quản lý kết nối riêng khi migration khởi động; một service method có `@Transactional` không tự biến toàn bộ changelog thành transaction của service đó.

## 3. Database quyết định DDL có rollback được hay không

SQL được chia đại khái thành:

- **DML**: `INSERT`, `UPDATE`, `DELETE`. Trên bảng và storage engine hỗ trợ transaction, DML có thể được rollback khi chưa commit.
- **DDL**: `CREATE TABLE`, `ALTER TABLE`, `DROP INDEX`... Khả năng nằm trong transaction khác nhau đáng kể theo DBMS và loại thao tác.
- **Câu lệnh đặc biệt**: ví dụ `CREATE INDEX CONCURRENTLY` của PostgreSQL không chạy trong một transaction block thông thường.

| DBMS | Hành vi DDL điển hình | Hệ quả khi changeset lỗi |
|---|---|---|
| **PostgreSQL** | Nhiều DDL phổ biến có thể chạy trong transaction; có ngoại lệ như `CREATE INDEX CONCURRENTLY`. | Với DDL hỗ trợ transaction, các thay đổi chưa commit trong changeset thường bị hủy khi rollback. |
| **MySQL/MariaDB** | Nhiều DDL như `CREATE TABLE`, `ALTER TABLE` gây implicit commit, tùy lệnh/engine. | Bảng/cột có thể đã tồn tại dù một lệnh sau trong cùng changeset lỗi. |
| **Oracle Database** | Nhiều DDL thực hiện implicit commit trước/sau lệnh. | DDL đã thành công thường không bị rollback bởi transaction sau đó. |
| **Microsoft SQL Server** | Nhiều DDL hỗ trợ transaction, nhưng tồn tại ngoại lệ, giới hạn và thao tác có khóa mạnh. | Cần kiểm tra riêng loại DDL, thiết lập transaction và database version. |

**Lưu ý:** “Atomic DDL” theo một tài liệu DBMS có thể nói về **tính nguyên tử/khả năng phục hồi của chính một lệnh DDL khi crash**, không nhất thiết là khả năng người dùng rollback lệnh đó cùng với DML khác trong transaction. Đừng đồng nhất hai khái niệm.

### 3.1. Minh họa MySQL/Oracle

Giả sử một changeset có trình tự:

~~~sql
CREATE TABLE migration_tmp (id BIGINT PRIMARY KEY);
INSERT INTO migration_tmp(id) VALUES (1);
INSERT INTO migration_tmp(id) VALUES (1); -- Trùng khóa, dự kiến lỗi
~~~

Với PostgreSQL trong một transaction phù hợp, việc lỗi khóa chính làm transaction không thể commit; bảng và dữ liệu mới trong changeset có thể được rollback toàn bộ. Với DBMS mà `CREATE TABLE` tự commit, **bảng có thể vẫn tồn tại** sau lỗi. Các `INSERT` có thể được rollback tùy transaction thực tế của DML, nhưng bảng đã được tạo không nhất thiết biến mất.

Vì thế, cùng một changelog có thể tạo ra **hai trạng thái hậu lỗi khác nhau** giữa PostgreSQL và MySQL/Oracle.

## 4. Bài thử đầy đủ: một changeset cố tình thất bại

Ví dụ sau dùng PostgreSQL để quan sát trực tiếp ranh giới transaction. **Chỉ chạy trên database thử nghiệm có thể xóa**, không chạy trên database dùng chung hoặc production.

### 4.1. Changelog XML

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
                        https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <!-- Changeset 001 được commit độc lập khi chạy thành công -->
    <changeSet id="001-create-lab-control" author="db-team"
               runInTransaction="true">
        <createTable tableName="migration_lab_control">
            <column name="id" type="BIGINT">
                <constraints primaryKey="true" nullable="false"/>
            </column>
        </createTable>
        <rollback>
            <dropTable tableName="migration_lab_control"/>
        </rollback>
    </changeSet>

    <!-- Changeset 002 cố tình chèn trùng khóa ngay trong một transaction -->
    <changeSet id="002-demonstrate-failure" author="db-team"
               runInTransaction="true">
        <createTable tableName="migration_lab_event">
            <column name="id" type="BIGINT">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="description" type="VARCHAR(100)"/>
        </createTable>

        <insert tableName="migration_lab_event">
            <column name="id" valueNumeric="1"/>
            <column name="description" value="first"/>
        </insert>
        <insert tableName="migration_lab_event">
            <column name="id" valueNumeric="1"/>
            <column name="description" value="duplicate"/>
        </insert>

        <rollback>
            <dropTable tableName="migration_lab_event"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

Lưu changelog mẫu vào một vị trí thử nghiệm do người học tự chọn. Các lệnh chạy dưới đây giả định file là `db/changelog/transaction-lab.xml`. Không cần và không được tạo thêm một file bài học nào khác trong phần Knowledge này; tên tệp chỉ là hướng dẫn khi người học thực hành độc lập.

### 4.2. Dự đoán kết quả trước khi chạy

1. `001` tạo bảng `migration_lab_control`, hoàn tất và được ghi lịch sử.
2. `002` tạo bảng `migration_lab_event`, chèn `id = 1` thành công lần đầu.
3. Lệnh `INSERT` thứ hai với `id = 1` vi phạm primary key, khiến `002` thất bại.
4. Trên PostgreSQL với transaction và lệnh hỗ trợ rollback, các thay đổi chưa commit của `002` bị hủy: **bảng `migration_lab_event` không còn tồn tại**.
5. Bảng `migration_lab_control` từ changeset `001` vẫn tồn tại; `DATABASECHANGELOG` có bản ghi thành công của `001` nhưng không có bản ghi thực thi thành công cho `002`.

Nếu chạy cùng thử nghiệm với DBMS tự commit DDL, kết quả tại bước 4 **có thể khác**. Đó là điều cần quan sát chứ không phải sai số có thể bỏ qua.

### 4.3. Chạy và xác minh

Các lệnh Liquibase CLI minh họa; cần cấu hình kết nối tới **database thử**, JDBC driver và thông tin xác thực phù hợp:

~~~bash
liquibase --changelog-file=db/changelog/transaction-lab.xml validate
liquibase --changelog-file=db/changelog/transaction-lab.xml update
~~~

Lệnh `update` được kỳ vọng **báo lỗi** tại changeset `002`. Sau lỗi, dùng truy vấn chỉ đọc trên PostgreSQL:

~~~sql
SELECT to_regclass('public.migration_lab_control') AS control_table,
       to_regclass('public.migration_lab_event') AS event_table;

SELECT ID, AUTHOR, FILENAME, EXECTYPE, DATEEXECUTED, MD5SUM
FROM DATABASECHANGELOG
WHERE ID IN ('001-create-lab-control', '002-demonstrate-failure')
ORDER BY ORDEREXECUTED;
~~~

Kỳ vọng `control_table` trả tên bảng, `event_table` trả `NULL` và lịch sử chỉ ghi `001`. Thử nghiệm giả định schema là `public`; nếu cấu hình default schema khác, hãy sửa truy vấn cho phù hợp.

### 4.4. Có nên chạy lại ngay sau lỗi?

**Không.** Vì mã ví dụ vẫn cố tình chèn trùng khóa, chạy lại sẽ tiếp tục thất bại. Với database có DDL tự commit, lần chạy lại còn có thể lỗi sớm hơn vì bảng `migration_lab_event` đã tồn tại.

Trong bài lab, sau khi đã quan sát và ghi lại trạng thái, có thể sửa changeset **chưa từng chạy thành công** để bản ghi thứ hai dùng `id = 2`, rồi thử lại trên database thử. Trong dự án thật, trước mọi thay đổi nội dung cần đối chiếu tất cả môi trường: nếu một môi trường đã thực thi cùng changeset, không được sửa nó tùy tiện vì còn liên quan checksum và lịch sử.

## 5. Khi đặt runInTransaction=false

`runInTransaction="false"` yêu cầu Liquibase không bao changeset bằng transaction quản lý theo cách thông thường. Thuộc tính này cần thiết cho một số câu lệnh **không cho phép chạy bên trong transaction block**, nhưng đánh đổi khả năng rollback tự động của nhiều bước.

### 5.1. Ví dụ PostgreSQL CREATE INDEX CONCURRENTLY

Trên PostgreSQL, `CREATE INDEX CONCURRENTLY` giúp giảm mức chặn hoạt động ghi so với cách tạo index thông thường trong một số tình huống, nhưng không được thực thi bên trong transaction block. Một changeset riêng có thể khai báo:

~~~xml
<changeSet id="003-create-payment-event-index"
           author="db-team" dbms="postgresql"
           runInTransaction="false">
    <preConditions onFail="HALT" onError="HALT">
        <tableExists tableName="payment_event"/>
    </preConditions>
    <sql splitStatements="false">
        CREATE INDEX CONCURRENTLY idx_payment_event_created_at
        ON payment_event (created_at)
    </sql>
    <rollback>
        <sql splitStatements="false">
            DROP INDEX CONCURRENTLY IF EXISTS
                idx_payment_event_created_at
        </sql>
    </rollback>
</changeSet>
~~~

Đoạn này chỉ là changeset XML mẫu, **không nối trực tiếp** vào bài lab ở mục 4 nếu database chưa có bảng `payment_event(created_at)`. Để kiểm thử, hãy chuẩn bị bảng này trong database riêng. Lệnh rollback cũng phải được kiểm tra ở chế độ chạy không nằm trong transaction block theo phiên bản Liquibase đang dùng; không mặc định chỉ vì khai báo rollback mà SQL đã tương thích với executor.

### 5.2. Tại sao chỉ nên đặt một thao tác logic?

Nếu `runInTransaction=false` mà changeset chứa nhiều câu:

~~~text
Change A: hoàn tất
Change B: hoàn tất
Change C: lỗi
~~~

`A` và `B` **có thể đã commit**, nhưng changeset `C` chưa kết thúc thành công và bản ghi lịch sử có thể không đại diện cho trạng thái database. Đây là nguồn tạo ra trạng thái “schema đã đổi nhưng Liquibase cho rằng changeset chưa chạy”.

Quy tắc an toàn:

- Tách thao tác bắt buộc không-transactional thành changeset **riêng**, nhỏ, dễ kiểm chứng.
- Không trộn `CREATE INDEX CONCURRENTLY` với nhiều DDL/DML khác trong cùng changeset.
- Chuẩn bị SQL kiểm tra trạng thái sau lỗi và SQL dọn dẹp **có kiểm soát**.
- Thử chạy lại trên database đại diện, đặc biệt với đối tượng được tạo một phần.
- Chỉ chọn `runInTransaction=false` khi có lý do kỹ thuật rõ ràng.

### 5.3. Index bị tạo dở

Trên PostgreSQL, một lần `CREATE INDEX CONCURRENTLY` thất bại có thể để lại **index không hợp lệ**. Không chỉ kiểm tra tên index đã tồn tại: cần xem trạng thái `indisvalid`. Ví dụ:

~~~sql
SELECT idx.relname AS index_name, i.indisvalid
FROM pg_index i
JOIN pg_class idx ON idx.oid = i.indexrelid
JOIN pg_namespace n ON n.oid = idx.relnamespace
WHERE n.nspname = 'public'
  AND idx.relname = 'idx_payment_event_created_at';
~~~

Nếu index không hợp lệ, phải đánh giá nguyên nhân và lên kế hoạch xử lý, chẳng hạn dọn index theo cách DBMS hỗ trợ rồi triển khai lại. **`IF NOT EXISTS` không chứng minh một index trùng tên là hợp lệ**. Tránh chạy lại một cách mù quáng.

## 6. Lỗi xảy ra ở đâu quyết định trạng thái

Không phải mọi lỗi migration đều xảy ra ở cùng một điểm:

| Thời điểm lỗi | Trạng thái có thể xảy ra | Cách tiếp cận |
|---|---|---|
| **Parse/validate changelog** trước khi thực thi | Chưa gửi change tới DBMS trong lần chạy đó. | Sửa cú pháp, cấu trúc, checksum hoặc cấu hình rồi validate lại. |
| **Precondition fail** với `HALT` | Changeset không thực thi các change; lệnh bị dừng. | Kiểm tra điều kiện và schema; không tự đánh dấu đã chạy. |
| **Precondition fail** với `CONTINUE` | Changeset được bỏ qua tạm thời khi chính sách hợp lệ. | Kiểm tra có nên xét lại ở lần triển khai sau. |
| **Precondition fail** với `MARK_RAN` | Không áp dụng change nhưng có thể ghi `EXECTYPE=MARK_RAN`. | Chỉ dùng khi đã xác minh trạng thái thực tế tương đương mục tiêu. |
| **DML thất bại trong transaction còn hiệu lực** | DML chưa commit có thể bị rollback. | Xác minh cả dữ liệu và bản ghi lịch sử. |
| **DDL tự commit rồi lệnh kế tiếp lỗi** | Schema thay đổi một phần dù update thất bại. | So sánh metadata, SQL preview và lịch sử; xây remediation. |
| **Câu lệnh chạy ngoài transaction lỗi** | Một phần thao tác hoặc object không hợp lệ có thể còn tồn tại. | Kiểm tra chi tiết DBMS và xử lý trạng thái dở dang trước khi retry. |
| **Mất kết nối lúc commit/ghi lịch sử** | Chưa chắc client có thể biết DB đã commit bước nào. | Điều tra từ phía DBMS và `DATABASECHANGELOG` trước khi quyết định. |
| **Lỗi trong rollback command** | Các bước rollback trước đó có thể đã thực thi; trạng thái dở dang. | Kiểm tra schema/data và các changeset đã được ghi nhận, không chạy lại tùy tiện. |

Trong nhiều trường hợp, khi Liquibase báo lỗi một changeset, bản ghi `EXECUTED` mới **chưa** được ghi cho changeset đó. Tuy nhiên, đừng biến điều này thành bất biến tuyệt đối cho mọi loại thay đổi, DBMS hoặc loại lỗi: phải kiểm tra lịch sử thực tế.

### 6.1. failOnError=false có giúp tiếp tục an toàn không?

Thuộc tính `failOnError` có thể thay đổi cách Liquibase phản ứng khi một change báo lỗi trong changeset. **Không nên đặt `failOnError="false"` chỉ để pipeline xanh**. Việc cho phép tiếp tục không đồng nghĩa dữ liệu nhất quán, không đảm bảo thao tác lỗi đã được bỏ qua an toàn và có thể khiến lịch sử khó giải thích.

Nếu một thay đổi **được phép không thực hiện** trong một số tình huống, hãy mô tả điều kiện hợp lệ bằng precondition, phân tách changeset hoặc thay đổi thiết kế. Nếu thay đổi bắt buộc, ưu tiên để lỗi dừng triển khai và điều tra nguyên nhân.

### 6.2. runOnChange, runAlways không phải cơ chế retry lỗi

`runOnChange` cho phép xét thực thi lại changeset khi nội dung thay đổi theo cơ chế checksum; `runAlways` phục vụ trường hợp cần chạy trong mỗi lần update đủ điều kiện. Chúng **không tự chữa** database đã thay đổi một phần do lỗi DDL.

Một changeset chưa ghi nhận thực thi có thể được xét ở lần chạy sau, nhưng phải kiểm tra trạng thái schema trước. Cố dùng `runAlways` hoặc sửa checksum để ép lệnh chạy lại có thể làm hư dữ liệu.

## 7. Phân biệt DATABASECHANGELOGLOCK với transaction lock

Liquibase sử dụng bảng `DATABASECHANGELOGLOCK` để điều phối việc chạy migration: thông thường chỉ một tiến trình Liquibase giữ khóa changelog cho một database tại một thời điểm. Trong khi đó, **khóa transaction/DDL của DBMS** bảo vệ bảng, hàng, index hoặc metadata mà các câu SQL đang thay đổi.

| Loại khóa | Mục đích | Không bảo vệ được |
|---|---|---|
| **Liquibase changelog lock** | Tránh hai tiến trình Liquibase cùng cập nhật lịch sử và áp dụng migration vào cùng một database. | Không tự chặn mọi câu `INSERT`/`UPDATE` từ ứng dụng. |
| **DBMS transaction/row lock** | Bảo vệ tính nhất quán thao tác dữ liệu theo isolation và transaction. | Không đảm bảo Liquibase chỉ chạy một instance nếu không có cơ chế điều phối changelog. |
| **DBMS DDL/schema lock** | Điều phối các thay đổi cấu trúc và truy vấn liên quan. | Không đảm bảo mọi DDL rollback được sau commit. |

### 7.1. Kiểm tra trạng thái khóa Liquibase

Truy vấn chỉ đọc:

~~~sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

`LOCKED` cho biết trạng thái khóa, `LOCKGRANTED` và `LOCKEDBY` có thể hỗ trợ điều tra tiến trình giữ khóa. Nếu một tiến trình bị dừng đột ngột, khóa có thể còn được ghi nhận và lần chạy sau phải chờ hoặc hết thời gian chờ theo cấu hình.

**Không tự ý gọi `releaseLocks` hoặc sửa bảng khóa** chỉ vì thấy `LOCKED=true`. Trước tiên phải chắc chắn **không còn một tiến trình Liquibase nào đang chạy** trên database đó; giải phóng nhầm khóa có thể cho phép hai tiến trình migration chồng nhau.

### 7.2. Khóa Liquibase không ngăn schema thay đổi bởi hệ thống khác

Ngay cả khi chỉ có một Liquibase giữ khóa, tài khoản khác vẫn có thể chạy SQL ngoài Liquibase nếu có quyền; ứng dụng vẫn có thể gửi DML trong lúc migration đang chạy, trừ khi DBMS chặn bằng khóa hoặc quy trình vận hành hạn chế lưu lượng.

Với migration tác động bảng lớn, cần lập kế hoạch lock duration, thời gian timeout, kích thước bảng, transaction isolation, thứ tự triển khai ứng dụng và tác động người dùng. `DATABASECHANGELOGLOCK` không phải “chế độ bảo trì” tự động.

## 8. Rollback khai báo và rollback transaction

Trong XML:

~~~xml
<changeSet id="add-customer-flag" author="db-team">
    <addColumn tableName="customer_record">
        <column name="verified" type="BOOLEAN"/>
    </addColumn>
    <rollback>
        <dropColumn tableName="customer_record"
                    columnName="verified"/>
    </rollback>
</changeSet>
~~~

Đây là phần tử trong changelog hợp lệ, chưa phải tài liệu XML độc lập. `rollback` định nghĩa cách **gỡ cột** khi chạy rollback command thích hợp. Nó không phải callback được Liquibase đảm bảo tự động gọi nếu `addColumn` thành công nhưng bước tiếp theo trong cùng changeset lỗi.

Các giới hạn:

- `DROP COLUMN` làm mất dữ liệu đã ghi vào cột sau khi triển khai.
- Một số change có auto rollback được Liquibase hỗ trợ, nhiều change khác cần rollback tường minh; phải kiểm tra loại change và DBMS.
- DDL ngoài transaction có thể để lại object ngay cả khi changeset chưa được ghi lịch sử; rollback command theo lịch sử có thể **không tìm thấy changeset lỗi để đảo ngược**.
- Với schema đang có dữ liệu quan trọng, rollback code và **restore từ backup** là hai khả năng khác nhau; đôi khi chỉ restore mới khôi phục đủ dữ liệu.

### 8.1. Ranh giới nhiều changeset

Giả sử:

~~~text
001: Tạo bảng customer_status       -> SUCCESS, đã commit
002: Backfill dữ liệu 1 triệu hàng  -> SUCCESS, đã commit
003: Thêm NOT NULL constraint       -> FAILED
~~~

Ngay cả trên DBMS có transactional DDL, lỗi ở `003` thông thường **không tự đảo ngược** `001` và `002`. Nếu quyết định hủy toàn bộ bản phát hành, phải có kế hoạch rollback các changeset đã thành công theo đúng thứ tự và kiểm tra khả năng phục hồi dữ liệu. Trong một số tình huống nên triển khai tiếp changeset sửa lỗi thay vì rollback dữ liệu lớn.

## 9. Quy trình xử lý sự cố sau khi update thất bại

Mục tiêu không phải “làm cho Liquibase chạy lại bằng mọi giá”, mà là **đưa trạng thái database, changelog và lịch sử về cùng một sự thật có thể kiểm chứng**.

### Bước 1: Dừng retry tự động

Ngắt vòng retry nếu thay đổi có thể không idempotent hoặc có DDL tự commit. Xác định môi trường, JDBC URL đích, default schema, bản Liquibase, id/author/filename của changeset lỗi và câu SQL/exception cuối cùng.

### Bước 2: Xác nhận không còn migration khác chạy

Kiểm tra tiến trình deploy, log và `DATABASECHANGELOGLOCK`. Nếu khóa còn giữ, phân biệt tiến trình đang chạy với khóa thật sự bị kẹt. Không phá khóa chỉ dựa trên thời gian chờ.

### Bước 3: Đối chiếu lịch sử

~~~sql
SELECT ID, AUTHOR, FILENAME, EXECTYPE, DATEEXECUTED, MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
~~~

Tìm changeset cuối cùng có trạng thái thành công, changeset lỗi có bản ghi hay chưa, có `MARK_RAN` hoặc `RERAN` ngoài dự kiến không. Đường dẫn `FILENAME` cũng quan trọng nếu changelog vừa đổi vị trí; `logicalFilePath` có thể giữ ổn định định danh khi di chuyển file.

### Bước 4: Kiểm tra schema và dữ liệu **thật**

Đối chiếu với mục tiêu của changeset:

- Bảng đã tạo chưa? Cột có tồn tại với đúng kiểu và constraint không?
- Index đã hoàn tất và hợp lệ chưa?
- Dữ liệu backfill đã được áp dụng một phần hay toàn bộ?
- Có row count hoặc bất biến nghiệp vụ nào sai?
- Có locks còn hoạt động, transaction chưa kết thúc hoặc kết nối bị treo không?

Không chỉ nhìn `DATABASECHANGELOG`: dữ liệu có thể đã đổi dù không có bản ghi thành công.

### Bước 5: Chọn phương án phục hồi

| Trạng thái quan sát | Hướng xử lý nên cân nhắc |
|---|---|
| Không có thay đổi nào được commit và changeset chưa ghi lịch sử | Sửa nguyên nhân gây lỗi, review SQL rồi retry có kiểm soát. |
| DDL đã commit một phần, không có bản ghi history | Thiết kế cleanup hoặc migration bổ sung dựa trên trạng thái hiện tại; xác minh trước retry. |
| Một changeset trước đã thành công, changeset sau lỗi | Giữ nguyên bản ghi thành công; chỉ xử lý changeset lỗi hoặc lập rollback phát hành có chủ đích. |
| Changeset được ghi `MARK_RAN` nhưng object thực tế thiếu | Điều tra chính sách precondition và schema drift; không xóa metadata tùy tiện. |
| Index PostgreSQL tạo không hợp lệ | Kiểm tra `pg_index.indisvalid`, dọn/khôi phục index theo quy trình DBMS. |
| DML gây mất dữ liệu | Dùng backup, recovery hoặc compensating migration đã phê duyệt; đừng coi `DROP/CREATE` là khôi phục dữ liệu. |
| Không rõ commit đã xảy ra trước khi mất kết nối | Thu thập bằng chứng ở database, đối chiếu log/mốc thời gian và lịch sử trước khi hành động. |

### Bước 6: Kiểm chứng sau phục hồi

Chạy `validate`, `status` và SQL preview trên đúng database; sau đó thử thay đổi trên bản sao dữ liệu đại diện. Khi đã an toàn mới cho pipeline tiếp tục. Lưu bằng chứng sự cố và các bước sửa vào hồ sơ triển khai.

**Tránh giải pháp tắt:** không xóa bừa hàng trong `DATABASECHANGELOG`, không dùng `clearCheckSums`, `changelogSync` hay `MARK_RAN` để che chênh lệch schema, và không chạy `releaseLocks` khi chưa chắc chắn tiến trình cũ đã kết thúc. Những công cụ này có mục đích chính đáng nhưng không thay thế điều tra trạng thái.

## 10. Preconditions, context, checksum và lịch sử liên quan thế nào?

Một changeset được thực thi trong bối cảnh nhiều cơ chế:

- **Context/label/DBMS filters:** xác định changeset nào thuộc phạm vi lần chạy; không chứng minh SQL bên trong có thể rollback.
- **Preconditions:** kiểm tra giả định về schema/data trước khi thực thi; `onFail="HALT"` thường là lựa chọn phù hợp cho điều kiện bắt buộc. Chúng không loại trừ race condition giữa kiểm tra và DDL.
- **Checksum:** phát hiện một định nghĩa changeset đã chạy bị thay đổi ngoài chính sách; không phản ánh số hàng đã commit khi changeset thất bại.
- **`runInTransaction`:** điều khiển phạm vi transaction mà Liquibase yêu cầu; không ghi đè quy tắc implicit commit của DBMS.
- **Rollback:** phương án chủ động triển khai ngược khi đã quyết định; không mặc nhiên thực hiện lúc `update` thất bại.

Ví dụ một precondition `not(tableExists)` với `onFail="MARK_RAN"` có thể tránh tạo bảng trùng, nhưng **chỉ bảng tồn tại thôi chưa chứng minh schema tương đương**. Dùng nó để che lỗi do changeset bị chạy lại sau khi file chuyển vị trí có thể khiến lịch sử sai lệch nghiêm trọng. Trước hết phải kiểm tra bộ ba định danh và `DATABASECHANGELOG.FILENAME`.

## 11. Spring Boot và CI/CD: tránh nhiều lần migration đồng thời

Một ứng dụng Spring Boot có thể bật Liquibase khi khởi động:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/master.xml
~~~

Nếu triển khai nhiều instance cùng lúc, các instance có thể cùng cố chạy migration. `DATABASECHANGELOGLOCK` thường giúp serialize hoạt động Liquibase, nhưng không thay thế chiến lược triển khai. Những tình huống cần chú ý:

1. Instance A đang giữ khóa và thực hiện một DDL lâu; instance B chờ khóa hoặc hết timeout.
2. Instance A thất bại sau DDL tự commit; instance B có thể gặp schema đã đổi một phần nếu ngay lập tức thử lại.
3. Tài khoản ứng dụng khác phiên bản vẫn ghi dữ liệu trong lúc schema thay đổi; lỗi có thể đến từ contract ứng dụng chứ không chỉ từ Liquibase.
4. Pipeline CI/CD chạy Liquibase trước khi phát hành, nhưng ứng dụng vẫn để `spring.liquibase.enabled=true`; cần quy ước rõ bên chịu trách nhiệm migration.

Các nguyên tắc vận hành:

- Khóa phiên bản Liquibase Core/CLI, JDBC driver, extension và changelog artifact qua các môi trường.
- Chỉ định rõ **một quy trình sở hữu migration**; nếu startup migration vẫn bật, hiểu hành vi chờ khóa và timeout.
- Review SQL preview và lock impact trước thay đổi bảng lớn, đặc biệt `ALTER TABLE` hoặc tạo index.
- Dùng chiến lược expand–migrate–contract khi cần ứng dụng cũ và mới cùng tồn tại.
- Giám sát thời gian giữ lock, lỗi migration, trạng thái schema và ảnh hưởng truy vấn.
- Dùng database staging có lịch sử và lượng dữ liệu đại diện; database trống không đủ để lộ mọi lỗi transaction/lock.

### 11.1. Lệnh kiểm chứng

~~~bash
liquibase --changelog-file=db/changelog/master.xml validate
liquibase --changelog-file=db/changelog/master.xml status --verbose
liquibase --changelog-file=db/changelog/master.xml update-sql
~~~

Cú pháp có thể khác theo phiên bản CLI (đặc biệt tên lệnh sinh SQL trong các bản cũ). Kết nối và credential phải lấy từ cấu hình/secret được quản lý an toàn. SQL preview không thực thi migration, nên **không thể tự kiểm chứng** hành vi rollback transaction hay thời gian giữ khóa khi chạy thật.

## 12. Thực hành có kiểm chứng

### Bài A — Hai changeset và một lỗi cố tình

Dùng PostgreSQL thử nghiệm và changelog ở mục 4:

1. Dự đoán trạng thái của bảng và `DATABASECHANGELOG` sau khi `002` lỗi.
2. Chạy `validate`, `update` rồi kiểm tra bằng `to_regclass` và truy vấn lịch sử.
3. Xác nhận `001` được giữ lại và `002` được rollback nhờ transaction.
4. Sửa nguyên nhân lỗi của changeset chưa từng chạy thành công (trên bản lab), chạy lại và xác minh cả hai changeset đã được ghi nhận.
5. Chạy lại `update` lần nữa, kiểm tra Liquibase không thực thi lại changeset thông thường đã hoàn tất.

### Bài B — So sánh DDL transactional và implicit commit

Trên database thử thứ hai thuộc DBMS khác được dự án hỗ trợ:

1. Dự đoán liệu `CREATE TABLE` có thể bị rollback khi câu `INSERT` sau lỗi hay không.
2. Thực hiện cùng chuỗi thao tác trong một changeset trên dữ liệu giả lập.
3. So sánh table existence, row count, lịch sử và log lỗi với PostgreSQL.
4. Ghi lại quy tắc transaction/DDL của đúng phiên bản DBMS thay vì suy luận từ tên Liquibase `runInTransaction=true`.
5. Thiết kế phương án cleanup có kiểm chứng cho trạng thái DDL tồn tại nhưng changeset chưa ghi lịch sử.

### Bài C — Nontransactional index

Chỉ trên PostgreSQL test có bảng `payment_event(created_at)`:

1. Viết changeset riêng `runInTransaction=false` cho `CREATE INDEX CONCURRENTLY`.
2. Kiểm tra SQL preview và chạy trên bảng thử nghiệm.
3. Truy vấn `pg_index`, xác minh index có `indisvalid=true`.
4. Thảo luận trường hợp lệnh bị ngắt giữa chừng và cách phát hiện index không hợp lệ.
5. Kiểm tra độc lập khả năng rollback `DROP INDEX CONCURRENTLY` theo cách chạy Liquibase thực tế.

**Tiêu chí đạt:** giải thích được transaction boundary ở cấp changeset, chứng minh sự khác nhau giữa DBMS, nhận diện schema drift sau lỗi, phân biệt hai loại rollback và biết kiểm tra khóa Liquibase trước khi retry.

## 13. Checklist xử lý transaction và lỗi

- [ ] Đã xác định **một changeset** chứa những thao tác nào và vì sao.
- [ ] Đã biết `runInTransaction` của changeset, hiểu giá trị mặc định.
- [ ] Đã kiểm tra DBMS/loại DDL có rollback trong transaction được không.
- [ ] Những lệnh không cho chạy trong transaction được tách riêng, có kế hoạch phục hồi.
- [ ] Tránh nhét nhiều DDL/DML không-transactional vào một changeset.
- [ ] Đã phân biệt transaction rollback với Liquibase rollback command.
- [ ] Có explicit rollback hoặc restore plan nếu migration có thể phá hủy dữ liệu.
- [ ] Đã xác định precondition/filter phù hợp; không dùng `MARK_RAN` để che drift.
- [ ] Khi update lỗi, đã kiểm tra `DATABASECHANGELOG` và schema/data trước retry.
- [ ] Đã kiểm tra `DATABASECHANGELOGLOCK` và tiến trình migration trước khi giải phóng khóa.
- [ ] Đã xét DBMS DDL/schema locks, timeout và tác động lên traffic của ứng dụng.
- [ ] Pipeline và Spring Boot có phân công rõ ràng ai chạy migration.
- [ ] Đã thử cả database trống và database đã có lịch sử/dữ liệu thực tế.
- [ ] SQL preview, rollback và kế hoạch recovery đã được review trên DBMS đích.

## 14. Câu hỏi tự kiểm tra

1. Vì sao một changelog gồm ba changeset không được xem là một transaction duy nhất?
2. `runInTransaction=true` có bảo đảm rollback được mọi DDL trên Oracle và MySQL không? Vì sao?
3. Kết quả thay đổi bảng có thể khác nhau thế nào giữa PostgreSQL và MySQL nếu changeset lỗi sau `CREATE TABLE`?
4. Nếu changeset `002` thất bại, changeset `001` đã commit có tự động bị hủy không?
5. Khi nào dùng `runInTransaction=false` với `CREATE INDEX CONCURRENTLY`?
6. Tại sao không nên chứa nhiều câu SQL không-transactional trong một changeset?
7. Sau `CREATE INDEX CONCURRENTLY` thất bại, vì sao chỉ kiểm tra tên index tồn tại là chưa đủ?
8. `DATABASECHANGELOGLOCK` khác khóa DDL và row lock của DBMS ở mục đích nào?
9. Trước khi chạy `releaseLocks` cần xác minh điều gì?
10. Liquibase rollback command khác transaction rollback khi gặp lỗi như thế nào?
11. Tại sao `DATABASECHANGELOG` không đủ để kết luận một DDL đã được hoàn tác?
12. Vì sao `failOnError=false` hoặc `MARK_RAN` không phải cách mặc định sửa một migration lỗi?
13. Những dữ liệu và log nào cần thu thập trước khi retry trên production?
14. Cần thay đổi quy trình triển khai ra sao nếu nhiều instance Spring Boot đồng thời khởi động với Liquibase được bật?

## Kết luận

**Transaction boundary của Liquibase chủ yếu gắn với từng changeset, nhưng mức bảo vệ thực sự do DBMS và loại SQL quyết định.** Một changeset báo lỗi có thể rollback hoàn toàn, rollback một phần hoặc để lại đối tượng đã commit. Quản lý tốt migration vì thế đòi hỏi hiểu `runInTransaction`, DDL transaction support, `DATABASECHANGELOG`, `DATABASECHANGELOGLOCK` và khác biệt giữa rollback transaction với rollback command. Khi kiểm chứng đầy đủ trên database đại diện và điều tra trạng thái thật trước retry, nhóm có thể triển khai schema an toàn hơn, kiểm toán được và khôi phục có kế hoạch khi xảy ra sự cố.
