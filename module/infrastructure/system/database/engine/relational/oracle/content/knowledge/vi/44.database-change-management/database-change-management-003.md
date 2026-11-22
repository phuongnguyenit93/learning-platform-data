# Khóa triển khai, lịch sử migration và phát hiện schema drift

Trong một ứng dụng sử dụng Oracle Database, schema thay đổi theo từng phiên bản ứng dụng: thêm bảng, cột, index, constraint, sequence, package, view hoặc sửa dữ liệu nền. Nếu nhiều máy chủ ứng dụng hoặc pipeline cùng triển khai, các thay đổi này cần được điều phối để tránh hai tiến trình cùng chạy migration, chạy sai thứ tự hoặc ghi nhận lịch sử không khớp với cấu trúc database thực tế.

Ba cơ chế cần được quản lý riêng nhưng phối hợp chặt chẽ:

- **Migration lock** bảo đảm chỉ một tiến trình được thực hiện thay đổi schema trong cùng phạm vi tại một thời điểm.
- **Migration history** ghi lại migration nào đã chạy, phiên bản, checksum, thời điểm và trạng thái thực thi.
- **Schema drift detection** so sánh cấu trúc database thực tế với trạng thái mong đợi từ migration hoặc model chuẩn để phát hiện thay đổi ngoài quy trình.

Lịch sử migration trả lời câu hỏi “công cụ đã ghi nhận những thay đổi nào?”. Drift detection trả lời câu hỏi “schema hiện tại có còn đúng với trạng thái mong đợi không?”. Hai câu hỏi này khác nhau: một migration có thể được ghi nhận là thành công nhưng DBA vẫn có thể sửa schema thủ công sau đó. Khi đó history không thay đổi, nhưng schema đã drift.

## 1. Migration và trạng thái schema mong đợi

Database migration là một thay đổi có phiên bản, được mô tả bằng SQL hoặc cấu hình migration. Mỗi migration nên có mục tiêu rõ ràng và được lưu trong source control cùng với code ứng dụng.

Ví dụ một migration thêm cột trạng thái xử lý:

~~~sql
ALTER TABLE orders
  ADD processing_status VARCHAR2(20);
~~~

Migration tiếp theo tạo index:

~~~sql
CREATE INDEX ix_orders_processing_status
  ON orders(processing_status);
~~~

Khi các migration được áp dụng theo thứ tự, schema chuyển từ trạng thái ban đầu sang trạng thái mới. Tập migration đã được version control là nguồn mô tả cách xây dựng schema mong đợi.

Một pipeline điển hình:

~~~text
Source control
    |
    | migration scripts + application code
    v
CI validation
    |
    | kiểm tra cú pháp, checksum, dependency
    v
Deployment coordinator
    |
    | acquire migration lock
    v
Oracle Database
    |
    | apply migration theo thứ tự
    | ghi migration history
    v
Post-deployment verification
    |
    | validate history và schema
    v
Release hoàn tất
~~~

Không nên xem migration script là một lệnh SQL tùy ý chạy thủ công. Migration cần được review, kiểm thử trên database tương đương, ghi nhận trong repository và triển khai theo quy trình có thể tái hiện.

### Versioned migration và repeatable migration

Các công cụ như Flyway và Liquibase hỗ trợ cách mô tả migration khác nhau.

- **Versioned migration** có phiên bản hoặc định danh duy nhất, chạy theo thứ tự và thường chỉ áp dụng một lần trên mỗi database/schema.
- **Repeatable migration** được chạy lại khi nội dung thay đổi theo cơ chế checksum hoặc quy tắc của công cụ. Thường dùng cho view, package hoặc object cần đồng bộ lại từ source.

Ví dụ tên file Flyway:

~~~text
V001__create_customer_table.sql
V002__add_customer_status.sql
V003__create_order_index.sql
R__refresh_reporting_views.sql
~~~

V là versioned migration; R là repeatable migration theo quy ước Flyway. Tên và quy tắc chính xác cần tuân thủ cấu hình Flyway của dự án.

Trong Liquibase, changeset có author và id duy nhất trong phạm vi changelog, ví dụ:

~~~xml
<changeSet id="2026-11-14-001" author="db-team">
    <createTable tableName="CUSTOMER">
        <column name="CUSTOMER_ID" type="NUMBER(19)">
            <constraints primaryKey="true" nullable="false"/>
        </column>
        <column name="STATUS" type="VARCHAR2(20)"/>
    </createTable>
</changeSet>
~~~

Không đổi nội dung migration đã áp dụng chỉ để làm file hiện tại trông giống schema. Hãy tạo migration mới để sửa trạng thái database. Với migration đã triển khai, thay đổi lịch sử hoặc checksum có thể làm mất khả năng tái hiện và che giấu sai lệch.

## 2. Migration lock giải quyết vấn đề gì?

Giả sử hai pipeline A và B cùng triển khai lên một database:

1. A đọc history và thấy migration V010 chưa chạy.
2. B cũng đọc history và thấy V010 chưa chạy.
3. A bắt đầu thực hiện V010.
4. B cũng bắt đầu thực hiện V010.
5. Cả hai có thể cùng tạo object, sửa cùng bảng hoặc ghi cùng migration history.

Kết quả có thể là lỗi object đã tồn tại, trạng thái history không nhất quán, DDL bị thực hiện dở dang hoặc deployment thất bại giữa chừng.

Migration lock tạo một điểm điều phối chung để chỉ một runner được quyền thay đổi schema trong phạm vi được bảo vệ. Runner khác phải chờ, dừng hoặc báo lỗi theo chính sách.

~~~text
             Pipeline A              Pipeline B
                 |                        |
                 | acquire lock           | acquire lock
                 v                        v
          +----------------+      +----------------+
          | Lock available?|      | Lock available?|
          +-------+--------+      +-------+--------+
                  |                       |
               granted                 waiting
                  |                       |
                  v                       |
          Run migrations                  |
                  |                       |
          Validate schema                 |
                  |                       |
             release lock                 |
                  |                       v
                  +----------------> acquire lock
                                          |
                                      Run/check
                                          |
                                      release lock
~~~

Lock phải được dùng chung giữa mọi runner có thể thay đổi cùng schema. Một biến trong bộ nhớ của pipeline, mutex trong một JVM hoặc file lock trên một agent không đủ nếu pipeline khác chạy trên máy khác.

### Phạm vi của lock

Cần quyết định lock áp dụng ở mức nào:

- Một database.
- Một schema/owner.
- Một nhóm schema được migration cùng nhau.
- Một release gồm các schema có quan hệ phụ thuộc.

Nếu ứng dụng dùng nhiều schema, hai migration độc lập có thể chạy song song nếu không có object dependency hoặc tài nguyên dùng chung. Tuy nhiên, nếu một release thay đổi foreign key, synonym, package hoặc grant liên quan giữa các schema, nên dùng một lock chung cho toàn bộ đơn vị triển khai.

Không nên khóa quá rộng trong thời gian dài nếu có thể chia phạm vi an toàn, vì nó làm giảm khả năng triển khai song song. Ngược lại, khóa quá hẹp có thể để hai runner sửa các object phụ thuộc nhau cùng lúc.

## 3. Cách triển khai migration lock

Có hai cách phổ biến:

1. Dùng cơ chế lock do migration framework cung cấp.
2. Dùng lock riêng do hệ thống triển khai quản lý khi cần điều phối nhiều công cụ hoặc nhiều schema.

Ưu tiên lock của framework khi toàn bộ migration được thực hiện qua cùng framework và phiên bản hỗ trợ. Lock riêng chỉ nên được thêm khi có yêu cầu điều phối rõ ràng; tránh tạo hai cơ chế lock cạnh tranh hoặc deadlock.

### Liquibase DATABASECHANGELOGLOCK

Liquibase sử dụng bảng DATABASECHANGELOGLOCK để ngăn nhiều Liquibase process cùng cập nhật changelog trên một database. Bảng này lưu trạng thái lock và thông tin người giữ lock theo cơ chế của phiên bản Liquibase.

Các lệnh thường dùng:

~~~bash
liquibase status
liquibase update
liquibase release-locks
~~~

- status cho biết changeset nào còn pending.
- update áp dụng changeset theo changelog.
- release-locks giải phóng lock khi cần xử lý tình huống lock còn sót sau sự cố.

Không chạy release-locks theo thói quen chỉ vì pipeline đang chờ. Trước khi giải phóng lock, xác minh process Liquibase cũ đã dừng và không còn migration đang chạy. Nếu runner cũ vẫn hoạt động, giải phóng lock có thể cho phép runner thứ hai thay đổi schema đồng thời.

Có thể kiểm tra bảng lock:

~~~sql
SELECT id,
       locked,
       lockgranted,
       lockedby
FROM databasechangeloglock;
~~~

Tên schema chứa bảng phụ thuộc cấu hình Liquibase. Tài khoản triển khai phải có quyền đọc/ghi bảng lock và quyền thực hiện DDL cần thiết.

### Flyway và điều phối migration

Flyway lưu lịch sử migration trong bảng schema history, mặc định thường là flyway_schema_history. Flyway quản lý quá trình migration và điều phối các runner theo cơ chế lock phù hợp với database và phiên bản Flyway.

Các lệnh thường gặp:

~~~bash
flyway info
flyway validate
flyway migrate
~~~

- info hiển thị trạng thái và lịch sử migration.
- validate kiểm tra các migration đã áp dụng so với migration hiện có, gồm checksum và metadata theo quy tắc Flyway.
- migrate áp dụng migration còn pending.

Không nên tự giả định rằng có thể thêm một bảng lock riêng để thay thế lock nội bộ của Flyway. Nếu dùng Flyway, hãy để framework điều phối migration và không chạy SQL migration song song bằng một công cụ khác mà không có lock chung.

### Lock riêng trong Oracle bằng DBMS_LOCK

Trong trường hợp có một deployment coordinator tự viết hoặc cần đồng bộ nhiều bước thay đổi schema ngoài framework, Oracle cung cấp DBMS_LOCK để xin application lock. DBMS_LOCK cho phép nhiều session phối hợp trên một lock name/id.

Ví dụ khái niệm:

~~~sql
DECLARE
  l_lockhandle VARCHAR2(128);
  l_result     INTEGER;
BEGIN
  DBMS_LOCK.ALLOCATE_UNIQUE(
    lockname   => 'APP_SCHEMA_MIGRATION',
    lockhandle => l_lockhandle
  );

  l_result := DBMS_LOCK.REQUEST(
    lockhandle        => l_lockhandle,
    lockmode          => DBMS_LOCK.X_MODE,
    timeout           => 300,
    release_on_commit => FALSE
  );

  IF l_result <> 0 THEN
    RAISE_APPLICATION_ERROR(
      -20001,
      'Cannot acquire migration lock, result=' || l_result
    );
  END IF;

  -- Thực hiện phần điều phối migration tại đây.

  l_result := DBMS_LOCK.RELEASE(l_lockhandle);
END;
/
~~~

Đây là ví dụ minh họa API; triển khai thực tế cần xử lý exception để luôn release lock khi có lỗi. Lưu ý DBMS_LOCK.ALLOCATE_UNIQUE có thể commit transaction hiện tại; chỉ gọi nó trong deployment session chuyên biệt sau khi các thay đổi nghiệp vụ trước đó đã được commit hoặc rollback có chủ đích. DBMS_LOCK có thể cần quyền EXECUTE được cấp trực tiếp cho user chạy code; quyền chỉ nhận qua role có thể không đủ trong một số ngữ cảnh PL/SQL stored program.

Một số lưu ý:

- X mode là exclusive lock, chỉ một session giữ được trong cùng phạm vi lock.
- timeout giới hạn thời gian chờ.
- release_on_commit điều khiển lock có được giải phóng khi transaction commit hay không.
- DDL Oracle có implicit commit, vì vậy không dựa vào rollback transaction để giải phóng application lock nếu cấu hình lock không gắn với commit.
- Nếu session chết, Oracle giải phóng lock session-owned theo cơ chế database; coordinator vẫn cần timeout và quan sát trạng thái runner.

DBMS_LOCK là primitive để đồng bộ session, không phải một migration framework. Nó không tự kiểm tra version, checksum, dependency hoặc ghi lịch sử migration.

## 4. Lock timeout, stale lock và phục hồi sau sự cố

Một migration runner có thể bị kill, mất kết nối hoặc host bị restart. Cần phân biệt:

- Lock còn được một database session thực sự giữ.
- Lock metadata còn đánh dấu locked nhưng session sở hữu đã chết.
- Runner vẫn chạy nhưng pipeline mất kết nối đến runner.
- Migration đã hoàn tất DDL nhưng chưa ghi xong lịch sử.

Không được chỉ dựa vào thời gian lock đã tồn tại để kết luận lock stale. Một migration lớn có thể chạy lâu hơn dự kiến. Cần đối chiếu process, database session, SQL đang chạy, log migration và trạng thái DDL.

### Quy trình xử lý lock bị kẹt

1. Xác định framework và database/schema mà lock bảo vệ.
2. Xem bảng lock hoặc thông tin session theo hướng dẫn framework.
3. Kiểm tra pipeline/agent sở hữu lock còn chạy hay không.
4. Kiểm tra session Oracle, SQL đang thực hiện và wait event nếu có quyền.
5. Xác nhận migration không còn hoạt động và trạng thái database đã được đánh giá.
6. Dùng lệnh release lock chính thức của framework hoặc giải phóng application lock theo API tương ứng.
7. Chạy validate/status để xác định migration nào đã được ghi nhận.
8. Kiểm tra schema thực tế trước khi chạy lại migration.

Không xóa trực tiếp dòng trong DATABASECHANGELOGLOCK hoặc sửa cột LOCKED bằng SQL tùy tiện. Dùng API của framework để tránh làm sai trạng thái nội bộ hoặc giải phóng lock khi runner khác còn hoạt động.

### Timeout và retry

Một runner chờ lock nên có timeout hữu hạn. Nếu hết thời gian, pipeline cần báo rõ đang bị migration khác giữ lock, kèm thông tin database/schema và thời điểm bắt đầu chờ. Retry nên có backoff để nhiều pipeline không liên tục tranh lock.

Nếu một migration có thể chạy lâu, timeout lock phải dựa trên thời gian thực tế và cửa sổ triển khai. Không đặt timeout quá ngắn rồi tự động giải phóng lock. Việc hết thời gian chờ chỉ có nghĩa runner này không lấy được lock; không có nghĩa runner đang giữ lock đã thất bại.

## 5. Migration history lưu những gì?

Migration history là bảng metadata do công cụ quản lý để biết database đã được cập nhật đến đâu. Đây là căn cứ để framework quyết định migration nào pending, đã áp dụng hoặc cần xác minh.

### Flyway schema history

Flyway lưu các thông tin như version, description, type, script, checksum, thời gian thực thi, trạng thái thành công và thời lượng migration. Tên bảng mặc định thường là flyway_schema_history nhưng có thể đổi bằng cấu hình.

Ví dụ truy vấn:

~~~sql
SELECT installed_rank,
       version,
       description,
       type,
       script,
       checksum,
       installed_on,
       execution_time,
       success
FROM flyway_schema_history
ORDER BY installed_rank;
~~~

Cấu trúc cột có thể thay đổi theo phiên bản Flyway và cấu hình. Hãy kiểm tra schema history table thực tế trước khi viết query giám sát cố định.

### Liquibase DATABASECHANGELOG

Liquibase ghi nhận changeset đã chạy trong DATABASECHANGELOG. Các cột thường gặp gồm ID, AUTHOR, FILENAME, DATEEXECUTED, ORDEREXECUTED, EXECTYPE, MD5SUM, DESCRIPTION và LIQUIBASE.

Ví dụ:

~~~sql
SELECT id,
       author,
       filename,
       dateexecuted,
       orderexecuted,
       exectype,
       md5sum,
       description
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Changeset được nhận diện bằng tổ hợp định danh như id, author và đường dẫn changelog. Checksum giúp phát hiện nội dung changeset đã áp dụng bị sửa so với nội dung hiện tại theo quy tắc Liquibase.

### History không phải bản sao schema

Migration history cho biết công cụ đã ghi nhận gì, nhưng không chứa đầy đủ định nghĩa hiện tại của mọi object trong database. Nó không chứng minh rằng:

- DBA chưa sửa bảng thủ công.
- Index chưa bị drop.
- Grant chưa bị thay đổi.
- Package body chưa bị sửa.
- Constraint chưa bị disable.
- Object chưa bị tạo thêm ngoài migration.
- Cấu hình session/database chưa thay đổi hành vi migration.

Vì vậy, cần kết hợp history với schema comparison hoặc kiểm tra object cụ thể.

## 6. Checksum và validate migration history

Checksum là dấu kiểm được tạo từ nội dung migration hoặc changeset. Nếu file migration đã áp dụng bị sửa, checksum hiện tại có thể khác checksum được lưu trong history.

Điều này giúp phát hiện tình huống một migration cũ bị chỉnh sửa sau khi đã triển khai. Ví dụ:

1. V005 được áp dụng lên production.
2. History lưu checksum của nội dung V005 tại thời điểm chạy.
3. Developer sửa file V005 trên branch để đổi tên cột.
4. Pipeline chạy validate.
5. Công cụ phát hiện checksum không khớp.

Đây là dấu hiệu cần điều tra. Không sửa checksum history bằng tay để làm pipeline xanh. Nếu thay đổi schema là cần thiết, tạo migration mới, ví dụ V006, để chuyển từ trạng thái hiện tại sang trạng thái mong muốn.

### Flyway validate

~~~bash
flyway validate
~~~

Validate kiểm tra migration đã áp dụng có khớp với migration có sẵn trong cấu hình hiện tại theo quy tắc Flyway hay không. Nó phát hiện các vấn đề như checksum mismatch, migration bị thiếu hoặc metadata không nhất quán.

Validate không phải phép so sánh toàn bộ schema Oracle với một model chuẩn. Một DBA có thể thêm cột thủ công mà flyway validate vẫn thành công nếu history và các migration file không thay đổi.

### Liquibase validate và checksum

~~~bash
liquibase validate
liquibase status
~~~

validate kiểm tra tính hợp lệ của changelog và các cấu trúc Liquibase có thể xác minh. Liquibase cũng có thể phát hiện checksum changeset đã áp dụng không còn khớp. Tuy nhiên, validate không thay thế schema diff giữa database thực tế và baseline mong đợi.

Các lệnh repair/clear-checksums có thể được dùng trong một số tình huống có kiểm soát, nhưng không phải cách thông thường để xử lý migration bị sửa. Trước khi dùng, cần hiểu rõ thay đổi nào đã được áp dụng, vì sao checksum thay đổi và ảnh hưởng đến mọi môi trường.

## 7. Schema drift là gì?

Schema drift là sự khác biệt giữa cấu trúc database hiện tại và cấu trúc được mong đợi theo source of truth đã chọn.

Ví dụ migration định nghĩa:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER(19) NOT NULL,
    customer_name VARCHAR2(200) NOT NULL,
    status VARCHAR2(20),
    CONSTRAINT pk_customers PRIMARY KEY (customer_id)
);
~~~

Sau đó một DBA tạo thêm cột ngoài migration:

~~~sql
ALTER TABLE customers
  ADD legacy_flag CHAR(1);
~~~

Nếu cột legacy_flag không được định nghĩa trong migration/model chuẩn, database đã có drift. History có thể vẫn báo tất cả migration thành công vì thay đổi thủ công không ghi vào history table.

### Các dạng drift thường gặp

| Dạng drift | Ví dụ | Hệ quả |
|---|---|---|
| Object tồn tại ngoài migration | Bảng, view, sequence được tạo thủ công | Các môi trường có schema khác nhau |
| Object bị thiếu | Index hoặc constraint bị drop | Hiệu năng hoặc toàn vẹn dữ liệu suy giảm |
| Định nghĩa khác | Độ dài VARCHAR2, precision, nullable thay đổi | Lỗi ghi/đọc hoặc hành vi khác |
| Object bị sửa | Package, trigger, view body thay đổi | Logic production khác source control |
| Quyền khác | Grant/revoke ngoài quy trình | Ứng dụng lỗi quyền hoặc lộ dữ liệu |
| Trạng thái khác | Constraint disabled, index unusable | Ràng buộc hoặc kế hoạch truy vấn thay đổi |
| Thay đổi storage/partition | Tablespace, partition hoặc logging attribute khác | Vận hành và hiệu năng không đồng nhất |

Không phải mọi khác biệt metadata đều là drift cần sửa. Một số thuộc tính được Oracle tự điều chỉnh hoặc có thể khác có chủ đích theo môi trường, ví dụ tablespace, storage clause, statistics hoặc cấu hình vật lý. Cần định nghĩa baseline và allowlist cho các khác biệt được chấp nhận.

### Schema drift khác data drift

Schema drift là thay đổi cấu trúc như table, column, index, constraint, package hoặc grant. Data drift là dữ liệu nghiệp vụ khác kỳ vọng, ví dụ số lượng bản ghi, giá trị tham chiếu hoặc dữ liệu đồng bộ giữa hệ thống.

Migration history và schema diff tập trung vào schema. Kiểm tra data drift cần quy tắc riêng như count, checksum dữ liệu, kiểm tra referential integrity hoặc đối soát nghiệp vụ.

## 8. Xác định source of truth cho schema

Muốn phát hiện drift, trước tiên phải xác định trạng thái nào là chuẩn. Có thể dùng một hoặc kết hợp các nguồn:

- **Versioned migration scripts** trong source control.
- **Liquibase changelog** hoặc **Flyway migration history**.
- **DDL baseline** được xuất từ database chuẩn đã review.
- **JPA entity model** cho phần schema được ORM quản lý.
- **Database object scripts** cho package, view, trigger, synonym, grant và object không nằm trong JPA model.

Không nên dùng JPA entity model làm source of truth duy nhất nếu ứng dụng còn nhiều object PL/SQL, materialized view, partition, function-based index hoặc quyền database. Hibernate schema validation chủ yếu kiểm tra mapping entity với schema liên quan; nó không kiểm tra toàn bộ database object.

Một nguyên tắc thực tế là migration scripts định nghĩa thay đổi có phiên bản; DDL baseline dùng làm đối chiếu; model ứng dụng chỉ là một nguồn bổ sung cho phần entity mapping.

### Phân biệt drift được chấp nhận và drift ngoài ý muốn

Ví dụ mỗi môi trường dùng tablespace khác nhau nhưng cùng một cấu trúc logic. Nếu so sánh DDL thô, công cụ có thể báo khác biệt. Hãy chuẩn hóa hoặc loại các thuộc tính vật lý theo chính sách.

Ngược lại, không nên bỏ qua khác biệt nullable, data type, precision, constraint hoặc index chỉ vì chúng không làm migration fail ngay lập tức. Những khác biệt này có thể gây lỗi ở dữ liệu biên hoặc làm thay đổi hiệu năng.

Nên duy trì danh sách rõ ràng:

- Thuộc tính bắt buộc phải giống nhau ở mọi môi trường.
- Thuộc tính được phép khác theo environment.
- Object được tạo tự động hoặc do Oracle quản lý.
- Object tạm thời cần loại khỏi so sánh.
- Schema/owner thuộc phạm vi kiểm tra.

## 9. Phát hiện drift bằng Liquibase diff

Liquibase có khả năng so sánh database với database tham chiếu hoặc changelog/model được cấu hình. Các lệnh thường gặp:

~~~bash
liquibase diff
liquibase diff-changelog
~~~

- diff báo khác biệt giữa reference và target.
- diff-changelog có thể tạo changelog mô tả các khác biệt được phát hiện để review.

Ví dụ khái niệm: database DEV là reference, database TEST là target. Nếu TEST thiếu index hoặc có thêm column, diff sẽ thể hiện khác biệt theo phạm vi object mà Liquibase hỗ trợ và cấu hình.

Cần xác định rõ reference URL/schema và target URL/schema. Không chạy diff với nhầm chiều rồi tự động sinh changelog để áp dụng. File diff là đề xuất thay đổi, cần review vì có thể chứa khác biệt vật lý không nên đưa vào migration.

Một số cách dùng Liquibase phụ thuộc phiên bản và loại snapshot/reference được cấu hình. Cần kiểm tra tài liệu đúng phiên bản của Liquibase và extension Oracle nếu có.

### Diff giữa hai database

Ví dụ lệnh minh họa dùng properties file để tránh đưa password lên command line:

~~~bash
liquibase --defaults-file=liquibase-dev.properties diff
~~~

File properties cần chỉ định reference và target tương ứng theo phiên bản Liquibase, ví dụ URL, username, schema và driver. Bảo vệ file chứa thông tin xác thực bằng secret manager hoặc cơ chế phù hợp; không commit password vào source control.

### Diff changelog và review

~~~bash
liquibase --defaults-file=liquibase-diff.properties diff-changelog
~~~

Kết quả diff-changelog có thể dùng làm cơ sở tạo migration mới, nhưng phải review:

- Object nào thực sự cần đưa vào source control?
- Có khác biệt chỉ thuộc storage/environment không?
- Có làm mất dữ liệu nếu drop/alter không?
- Có cần backfill dữ liệu trước khi đặt NOT NULL hoặc tạo constraint không?
- Có phụ thuộc object hoặc thứ tự triển khai không?
- Có tương thích với phiên bản ứng dụng đang chạy không?

Không tự động áp dụng mọi khác biệt diff lên production. Drift có thể là thay đổi khẩn cấp có chủ đích, thay đổi sai hoặc một object Oracle sinh ra theo cấu hình môi trường.

## 10. Phát hiện drift bằng DDL và data dictionary của Oracle

Có thể dùng DBMS_METADATA để lấy DDL của object thực tế. Ví dụ:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
         'TABLE',
         'CUSTOMERS',
         'APP'
       )
FROM dual;
~~~

Lấy DDL index:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
         'INDEX',
         'IX_CUSTOMERS_STATUS',
         'APP'
       )
FROM dual;
~~~

Lấy DDL package:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
         'PACKAGE',
         'ORDER_API',
         'APP'
       )
FROM dual;
~~~

Với package body, dùng object type phù hợp:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
         'PACKAGE_BODY',
         'ORDER_API',
         'APP'
       )
FROM dual;
~~~

DBMS_METADATA có thể bị ảnh hưởng bởi quyền, transform parameters, phiên bản và các thuộc tính được chọn để xuất. DDL trả về có thể chứa tablespace hoặc storage clauses khác nhau giữa môi trường; cần chuẩn hóa trước khi so sánh.

### Kiểm tra bảng và cột

~~~sql
SELECT owner,
       table_name,
       column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM all_tab_columns
WHERE owner = 'APP'
ORDER BY table_name, column_id;
~~~

### Kiểm tra index

~~~sql
SELECT owner,
       index_name,
       table_name,
       uniqueness,
       status,
       visibility
FROM all_indexes
WHERE owner = 'APP'
ORDER BY table_name, index_name;
~~~

### Kiểm tra constraint

~~~sql
SELECT owner,
       constraint_name,
       table_name,
       constraint_type,
       status,
       validated
FROM all_constraints
WHERE owner = 'APP'
ORDER BY table_name, constraint_name;
~~~

### Kiểm tra object invalid

~~~sql
SELECT owner,
       object_type,
       object_name,
       status
FROM all_objects
WHERE owner = 'APP'
  AND status <> 'VALID'
ORDER BY object_type, object_name;
~~~

### Kiểm tra grant

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM all_tab_privs
WHERE owner = 'APP'
ORDER BY table_name, grantee, privilege;
~~~

Các view ALL_* hiển thị object mà user hiện tại có quyền nhìn thấy. DBA có thể dùng DBA_* để xem phạm vi rộng hơn. Để so sánh chính xác, phải dùng cùng owner, cùng quyền quan sát và cùng phiên bản/cấu hình metadata.

Không nên so sánh duy nhất số lượng object. Hai schema có cùng số table vẫn có thể khác cột, constraint, index, trigger hoặc package body.

## 11. Kiểm tra schema drift bằng Hibernate/JPA

Hibernate có thể kiểm tra một phần schema dựa trên entity mapping. Với Spring Boot, thuộc tính phổ biến:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

validate yêu cầu Hibernate kiểm tra schema liên quan đến mapping entity khi khởi động. Nếu thiếu table/column hoặc kiểu dữ liệu không tương thích theo phạm vi provider kiểm tra, ứng dụng có thể không khởi động.

Các giá trị thường gặp:

| Giá trị | Hành vi |
|---|---|
| none | Không tự kiểm tra hoặc cập nhật schema |
| validate | Kiểm tra mapping với schema |
| update | Cố gắng điều chỉnh schema theo mapping |
| create | Tạo schema khi khởi động |
| create-drop | Tạo schema lúc khởi động và drop khi đóng |

Trong môi trường production, thường nên dùng migration tool để quản lý DDL và đặt ddl-auto=validate hoặc none theo quy trình. Tránh dùng update/create/create-drop trên production vì ứng dụng có thể tự thay đổi schema ngoài lịch sử migration và kiểm soát triển khai.

Hibernate validate không phải công cụ drift đầy đủ. Nó không kiểm tra tất cả index, grant, trigger, package, procedure hoặc object không được entity mapping quản lý. Nó cũng không thay thế Liquibase diff hoặc kiểm tra DDL.

## 12. Xử lý drift: reconcile có kiểm soát

Khi phát hiện drift, đừng lập tức chạy diff-changelog lên production. Trước tiên cần xác định nguyên nhân và trạng thái dữ liệu.

Quy trình đề xuất:

1. **Đóng băng thay đổi cạnh tranh.** Dừng hoặc điều phối migration khác trong cùng phạm vi.
2. **Thu thập bằng chứng.** Lấy migration history, log deployment, DDL thực tế, object metadata và thời điểm thay đổi.
3. **Phân loại drift.** Object thiếu, object thừa, định nghĩa khác, quyền khác hay trạng thái object khác.
4. **Xác định nguồn thay đổi.** Migration, thao tác DBA, script khẩn cấp, tool khác hay thay đổi tự động.
5. **Đánh giá tác động dữ liệu.** Kiểm tra có dữ liệu phụ thuộc, constraint bị disable, index unusable hoặc package đang được ứng dụng sử dụng không.
6. **Chọn trạng thái chuẩn.** Xác định schema thực tế hay migration source control là đúng theo yêu cầu nghiệp vụ.
7. **Tạo migration sửa sai.** Nếu cần đưa database về chuẩn, tạo migration mới có thể tái hiện và review.
8. **Kiểm thử trên bản sao gần production.** Kiểm tra DDL, thời gian lock, dữ liệu, rollback/forward recovery và tương thích ứng dụng.
9. **Áp dụng dưới migration lock.** Chỉ một runner thay đổi schema trong phạm vi.
10. **Chạy lại validate/diff.** Xác nhận drift được giải quyết và history nhất quán.

Nếu thay đổi thủ công là một hotfix hợp lệ đã chạy trên production, cần đưa nó trở lại source control bằng migration tương ứng hoặc quy trình baseline/repair chính thức của framework. Không tạo một migration giả chỉ để đánh dấu trạng thái mà không kiểm tra database đã có đúng object và dữ liệu hay chưa.

### Ví dụ: cột được tạo thủ công trên production

Giả sử DBA đã thêm cột LEGACY_CODE vào production nhưng migration repository chưa có thay đổi này.

Có hai lựa chọn:

- Nếu cột không còn cần thiết, tạo migration có kiểm tra trạng thái và kế hoạch drop an toàn sau khi xác nhận không có ứng dụng sử dụng.
- Nếu cột là thay đổi nghiệp vụ cần giữ, tạo migration mô tả cột đó để các môi trường khác có thể tái hiện. Trước khi áp dụng, kiểm tra production đã có cột để tránh lỗi “column already exists”; có thể dùng precondition hoặc migration adoption theo công cụ.

Không chỉnh sửa migration cũ đã áp dụng để thêm cột. Tạo migration mới giúp history phản ánh đúng chuỗi thay đổi.

## 13. Oracle DDL và tính giao dịch của migration

Một khác biệt quan trọng khi dùng Oracle là nhiều câu DDL thực hiện implicit commit. Các lệnh như CREATE, ALTER và DROP thường commit transaction hiện tại trước khi thực hiện và commit sau khi hoàn tất thành công theo quy tắc Oracle.

Điều này ảnh hưởng đến cách migration framework quản lý transaction:

- Không giả định một migration chứa nhiều DDL có thể rollback toàn bộ như một transaction DML thông thường.
- Nếu migration chạy được một phần rồi lỗi, các DDL trước đó có thể đã commit.
- Framework có thể ghi nhận migration thất bại, nhưng schema vẫn chứa một phần thay đổi đã thực hiện.
- Chạy lại migration có thể gặp lỗi object đã tồn tại hoặc trạng thái nửa chừng.

Ví dụ:

~~~sql
ALTER TABLE customers ADD status VARCHAR2(20);
CREATE INDEX ix_customers_status ON customers(status);
~~~

Nếu ALTER TABLE thành công nhưng CREATE INDEX thất bại, không thể mặc định rollback sẽ xóa cột status. Cần kiểm tra schema thực tế trước khi sửa hoặc chạy lại.

### Thiết kế migration an toàn với DDL Oracle

- Chia thay đổi lớn thành các migration nhỏ, có trạng thái kiểm tra được.
- Dùng precondition hoặc script kiểm tra object trước khi tạo/drop khi công cụ hỗ trợ.
- Tránh trộn DDL và DML trong cùng changeset nếu kỳ vọng rollback nguyên tử.
- Với backfill dữ liệu lớn, tách thành job DML có batch/commit strategy riêng.
- Ghi log rõ bước đã hoàn thành và bước thất bại.
- Chuẩn bị migration khôi phục tiến về trạng thái mong muốn; không giả định rollback tự động luôn khả thi.

Liquibase có thuộc tính runInTransaction cho changeset, nhưng trên Oracle DDL vẫn có implicit commit. Việc đặt runInTransaction=false không làm DDL trở nên rollback được; chỉ dùng khi changeset chứa lệnh không thể chạy trong transaction hoặc theo yêu cầu cụ thể của công cụ. Hãy kiểm tra hành vi đúng phiên bản và thiết kế từng changeset sao cho có thể phục hồi.

### Expand-and-contract deployment

Với ứng dụng chạy nhiều instance và không thể dừng toàn bộ khi đổi schema, dùng chiến lược expand-and-contract:

1. **Expand**: thêm cột/table/index mới theo cách tương thích với phiên bản ứng dụng cũ.
2. **Deploy ứng dụng trung gian**: code có thể đọc/ghi cả cấu trúc cũ và mới hoặc ghi song song trong giai đoạn chuyển tiếp.
3. **Backfill**: chuyển dữ liệu hiện có theo batch và kiểm tra kết quả.
4. **Switch**: chuyển ứng dụng sang dùng cấu trúc mới.
5. **Contract**: sau khi mọi instance cũ đã dừng và dữ liệu đã đồng bộ, xóa cấu trúc cũ trong một migration riêng.

Ví dụ thêm cột mới nullable trước:

~~~sql
ALTER TABLE customers
  ADD display_name VARCHAR2(200);
~~~

Sau đó ứng dụng mới ghi display_name và backfill dữ liệu. Chỉ sau khi xác nhận mọi code path đã dùng cột mới mới cân nhắc bỏ cột cũ hoặc đặt constraint bắt buộc.

Không drop/rename cột ngay trong cùng release nếu phiên bản ứng dụng cũ còn đang chạy và vẫn truy cập cột đó. Migration cần tương thích theo thứ tự triển khai, không chỉ đúng khi chạy trên schema cuối cùng.

## 14. Lịch sử migration và audit triển khai

Migration history của framework là nguồn ghi nhận kỹ thuật. Đối với vận hành và audit, nên bổ sung thông tin deployment ở pipeline hoặc hệ thống change management:

- Release/application version.
- Commit SHA hoặc build artifact.
- Database unique name và schema/owner.
- Migration tool và phiên bản.
- Người hoặc service account khởi chạy.
- Thời điểm bắt đầu/kết thúc.
- Migration version/changeset đã áp dụng.
- Kết quả và lỗi.
- Ticket/change request và cửa sổ triển khai.
- Bằng chứng validate/diff sau migration.

Không nhất thiết ghi tất cả metadata vào bảng history do framework sở hữu. Có thể lưu trong hệ thống audit/deployment riêng hoặc pipeline artifact. Không thêm cột tùy tiện vào bảng Flyway/Liquibase nếu framework không hỗ trợ schema đó.

### Truy vấn trạng thái migration

Với Flyway, xem schema history:

~~~sql
SELECT version,
       description,
       script,
       installed_on,
       execution_time,
       success
FROM flyway_schema_history
ORDER BY installed_rank;
~~~

Với Liquibase:

~~~sql
SELECT id,
       author,
       filename,
       dateexecuted,
       exectype,
       md5sum
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Tài khoản đọc audit nên chỉ có quyền cần thiết. Tránh cho ứng dụng runtime quyền sửa hoặc xóa history table. Việc repair/baseline phải do tài khoản triển khai có kiểm soát thực hiện.

## 15. Pipeline triển khai có lock, history và drift check

Một pipeline database deployment có thể gồm các giai đoạn:

~~~text
1. Build
   - đóng gói migration
   - lưu commit/build identity
          |
          v
2. Static validation
   - kiểm tra tên/phiên bản migration
   - kiểm tra changelog và checksum
          |
          v
3. Acquire migration lock
   - chờ hoặc fail nếu lock đang được giữ
          |
          v
4. Pre-deployment inspection
   - kiểm tra database/schema/version
   - đọc migration history
   - phát hiện drift quan trọng
          |
          v
5. Apply migration
   - chạy theo thứ tự
   - ghi history
   - lưu log
          |
          v
6. Post-deployment verification
   - validate migration history
   - schema diff/metadata checks
   - kiểm tra object invalid
          |
          v
7. Release lock
          |
          v
8. Deploy/enable application
   - smoke test
   - theo dõi lỗi và hiệu năng
~~~

Cần có nhánh cleanup để giải phóng lock khi job thất bại, nhưng chỉ release lock mà runner hiện tại thực sự sở hữu. Nếu pipeline bị kill đột ngột, cơ chế framework hoặc database session phải quản lý lock; bước cleanup trong shell không thể được xem là bảo đảm duy nhất.

### Tách migration khỏi mỗi instance ứng dụng

Không nên để mọi instance Spring Boot tự chạy migration khi khởi động nếu hệ thống có nhiều replica và deployment song song mà không có cơ chế lock phù hợp. Có thể dùng một migration job riêng trong pipeline, sau đó mới rollout ứng dụng. Cách này làm rõ quyền sở hữu migration, thời gian triển khai và log audit.

Nếu vẫn dùng auto-migration lúc startup, phải xác nhận framework có lock chung, migration idempotency phù hợp và các instance khởi động đồng thời không tạo race condition. Với production, một job triển khai chuyên biệt thường dễ kiểm soát hơn.

## 16. Những sai lầm thường gặp

- **Chỉ kiểm tra history rồi kết luận schema đúng.** History không phát hiện mọi thay đổi thủ công sau migration.
- **Sửa file migration cũ đã áp dụng.** Có thể tạo checksum mismatch và làm mất khả năng tái hiện. Tạo migration mới.
- **Xóa lock thủ công khi pipeline đang chờ.** Runner cũ có thể vẫn thực hiện DDL. Xác minh owner trước khi release.
- **Dùng lock trong bộ nhớ của một agent.** Pipeline khác trên host khác không nhìn thấy lock đó.
- **Dùng một lock cho phạm vi không rõ.** Có thể vừa cho phép thay đổi xung đột vừa chặn các migration độc lập.
- **Tự viết lock nhưng không có timeout/recovery.** Runner chết có thể để trạng thái lock khó xử lý.
- **Tin rằng rollback DDL Oracle luôn khôi phục schema.** DDL thường implicit commit; cần kiểm tra trạng thái sau lỗi.
- **Tự động áp dụng diff lên production.** Diff có thể chứa thay đổi không mong muốn hoặc thuộc tính vật lý riêng môi trường.
- **Dùng Hibernate ddl-auto=update làm migration tool.** Schema thay đổi ngoài history và review.
- **So sánh DDL thô giữa môi trường khác cấu hình.** Tablespace, storage clause hoặc thuộc tính môi trường có thể tạo false positive.
- **Không kiểm tra object invalid sau DDL.** Package/view phụ thuộc có thể chuyển INVALID và làm ứng dụng lỗi.
- **Drop/rename object khi code cũ còn chạy.** Rolling deployment có thể làm một số instance truy cập object đã bị xóa.
- **Chỉ kiểm tra drift ở thời điểm release.** Thay đổi thủ công có thể xuất hiện sau đó; cần lịch kiểm tra định kỳ và audit DDL.

## 17. Quy trình vận hành đề xuất

1. **Lưu migration trong source control.** Mỗi thay đổi có định danh duy nhất, mô tả rõ và review.
2. **Chọn một migration framework chính.** Tránh nhiều công cụ cùng thay đổi một schema mà không có điều phối chung.
3. **Dùng lock chung.** Cho mọi runner có thể thay đổi cùng phạm vi schema.
4. **Không sửa migration đã áp dụng.** Tạo migration mới hoặc dùng quy trình baseline/repair có kiểm soát.
5. **Lưu history và deployment audit.** Gắn migration với release, commit và change request.
6. **Validate trước và sau migration.** Kiểm tra checksum, trạng thái pending và lỗi history.
7. **So sánh schema thực tế.** Dùng Liquibase diff, DDL metadata hoặc kiểm tra object theo baseline.
8. **Định nghĩa allowlist môi trường.** Phân biệt khác biệt vật lý được phép với khác biệt logic phải đồng nhất.
9. **Thiết kế cho Oracle DDL.** Giả định implicit commit và chuẩn bị cách tiếp tục sau migration chạy dở.
10. **Dùng expand-and-contract.** Giữ tương thích giữa schema và nhiều phiên bản ứng dụng trong rolling deployment.
11. **Kiểm tra object invalid và quyền.** Đặc biệt package, view, trigger, constraint, index và grant.
12. **Diễn tập phục hồi.** Kiểm tra kịch bản lock timeout, runner chết, DDL chạy một phần và migration checksum mismatch.

## 18. Checklist cho một lần release database

- [ ] Migration mới có version/id duy nhất và đã được review.
- [ ] Migration đã được kiểm thử trên Oracle phiên bản/cấu hình tương đương.
- [ ] Không có thay đổi trái phép trong migration đã áp dụng.
- [ ] Runner có quyền đúng mức và dùng tài khoản triển khai riêng.
- [ ] Migration lock đang được giữ bởi đúng runner.
- [ ] Không có migration khác đang chạy trên cùng phạm vi.
- [ ] History trước triển khai đã được ghi nhận.
- [ ] Schema drift trước triển khai đã được phân loại.
- [ ] Backup/recovery point phù hợp với mức rủi ro đã được xác nhận.
- [ ] DDL được thiết kế để xử lý implicit commit và partial failure.
- [ ] Thứ tự triển khai tương thích với phiên bản ứng dụng đang chạy.
- [ ] Post-check xác nhận migration history và object metadata.
- [ ] Không có object quan trọng ở trạng thái INVALID hoặc index UNUSABLE ngoài dự kiến.
- [ ] Lock được release bởi đúng owner.
- [ ] Log, commit/build identity và kết quả triển khai được lưu để audit.

Migration lock bảo vệ tính tuần tự của thay đổi schema; migration history cho biết các thay đổi có phiên bản đã được ghi nhận; drift detection xác minh database thực tế còn khớp với trạng thái chuẩn hay không. Kết hợp cả ba với cơ chế triển khai tương thích và quy trình phục hồi rõ ràng giúp schema Oracle nhất quán giữa các môi trường và giảm rủi ro khi nhiều pipeline hoặc DBA cùng tham gia thay đổi database.
