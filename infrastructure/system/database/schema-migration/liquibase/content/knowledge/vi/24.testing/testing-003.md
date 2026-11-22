# Nâng cấp từ dữ liệu và lược đồ của phiên bản trước

Một migration có thể chạy thành công trên database mới nhưng thất bại khi áp dụng lên database đang vận hành. Database cũ thường chứa dữ liệu tích lũy qua nhiều release, giá trị NULL, bản ghi ngoại lệ, index và constraint được tạo từ các phiên bản trước, thậm chí cả những thay đổi DBA đã thực hiện có phê duyệt. Khi schema mới được triển khai, Liquibase phải chuyển trạng thái hiện có sang trạng thái mong muốn mà vẫn bảo toàn dữ liệu và duy trì khả năng hoạt động của ứng dụng.

Bài học thuộc chương **Kiểm thử** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài này tập trung vào **kiểm thử đường nâng cấp từ schema và dữ liệu của release trước**. Bạn sẽ học cách dựng đúng trạng thái nguồn, xác định những phiên bản được hỗ trợ nâng cấp, kiểm thử migration dữ liệu, xác minh invariant trước/sau, kiểm tra tương thích ứng dụng và xử lý khi quá trình nâng cấp thất bại giữa chừng.

Sau bài học, bạn có thể:

1. Phân biệt kiểm thử cài mới với kiểm thử nâng cấp từ release cũ.
2. Tạo fixture database phản ánh đúng schema, lịch sử Liquibase và dữ liệu của phiên bản nguồn.
3. Xây dựng ma trận đường nâng cấp tuần tự và nhảy phiên bản theo chính sách sản phẩm.
4. Kiểm thử changeset DDL, backfill và chuyển đổi dữ liệu trên dữ liệu cũ có ngoại lệ.
5. Xác minh schema, dữ liệu, history và tính tương thích của ứng dụng sau nâng cấp.
6. Phát hiện rủi ro checksum, precondition, partial DDL, lock và rollback.
7. Tích hợp upgrade-path test vào CI/CD và lưu bằng chứng theo artifact/version.

## 1. Vì sao phải kiểm thử từ schema và dữ liệu của phiên bản trước?

Database của release cũ không giống database trống. Nó có một trạng thái được hình thành bởi:

- Những changeset đã chạy trong các release trước.
- Dữ liệu giao dịch được ứng dụng tạo ra.
- Những lần cập nhật dữ liệu bằng batch hoặc job nền.
- Các giá trị NULL, chuỗi rỗng, mã legacy và bản ghi ngoại lệ.
- Constraint, index, trigger, view và routine đang tồn tại.
- Quyền, schema owner và cấu hình DBMS.
- Những sai lệch có chủ đích đã được phê duyệt giữa các môi trường.

Một changeset thêm cột status có thể chạy được trên bảng trống nhưng thất bại trên bảng cũ vì có hàng không đáp ứng NOT NULL. Một migration đổi kiểu varchar sang integer có thể thành công với fixture sạch nhưng lỗi khi production có giá trị unknown. Một index mới có thể tạo được trên vài trăm hàng nhưng giữ lock quá lâu trên bảng hàng trăm triệu hàng.

Vì vậy, **upgrade-path test phải bắt đầu từ trạng thái nguồn có thật hoặc được tái tạo chính xác**, sau đó chạy đúng artifact migration sẽ phát hành.

### 1.1. Fresh install và upgrade path trả lời hai câu hỏi khác nhau

| Loại kiểm thử | Trạng thái đầu | Câu hỏi chính |
|---|---|---|
| **Fresh install** | Database trống | Changelog có dựng được schema và dữ liệu nền từ đầu không? |
| **Upgrade path** | Database ở một release cũ | Changelog mới có chuyển được schema và dữ liệu hiện tại sang trạng thái mới không? |

Ví dụ:

~~~text
Fresh install:
  empty database -> current changelog -> current schema

Upgrade path:
  release 2.4 schema + data
      -> release 2.5 migrations
      -> release 2.6 migrations
      -> current schema + migrated data
~~~

Một hệ thống có thể pass fresh install nhưng fail upgrade do dữ liệu cũ. Ngược lại, upgrade có thể pass vì database cũ đã có một đối tượng được DBA tạo thủ công, trong khi fresh install thiếu đối tượng đó.

Cần test cả hai đường nếu sản phẩm hỗ trợ cả khởi tạo mới và nâng cấp.

## 2. Xác định rõ phiên bản nguồn và phiên bản đích

Trước khi tạo fixture, phải xác định chính xác database đang ở trạng thái nào.

Một bản ghi mô tả test case nên có:

| Thuộc tính | Ví dụ |
|---|---|
| Phiên bản nguồn | 2.4.0 |
| Phiên bản đích | 2.6.0 |
| DBMS | PostgreSQL 16 |
| JDBC driver | Phiên bản được khóa trong build |
| Liquibase version | Phiên bản dùng trong pipeline |
| Root changelog nguồn | Artifact release 2.4.0 |
| Root changelog đích | Artifact đang kiểm thử |
| Context/labels | Bộ filter của môi trường đích |
| Schema | app |
| Fixture data | Bộ dữ liệu legacy đã version hóa |
| Đường nâng cấp | 2.4.0 → 2.5.0 → 2.6.0 hoặc trực tiếp 2.4.0 → 2.6.0 |

Không chỉ ghi “database cũ”. Cần biết **cũ ở release nào, đã chạy những changeset nào và có dữ liệu đại diện nào**.

### 2.1. Phiên bản ứng dụng và phiên bản schema không nhất thiết trùng nhau

Một ứng dụng có thể phát hành phiên bản 2.6 nhưng migration database đã chạy trước, hoặc database được nâng cấp riêng trong cửa sổ bảo trì. Vì thế, test fixture nên nhận diện trạng thái bằng:

- Release/artifact ứng dụng nếu có liên quan.
- Changelog artifact đã áp dụng.
- DATABASECHANGELOG.
- Schema/data contract được xác nhận.

Không suy ra schema version chỉ từ một cột app_version hoặc tên database nếu chưa có quy ước đáng tin cậy.

## 3. Tạo fixture từ artifact release cũ

Cách có độ tin cậy cao là dựng database test bằng **changelog của đúng release nguồn**, sau đó nạp dữ liệu fixture tương ứng.

Luồng khái niệm:

~~~mermaid
flowchart TD
    A[Artifact release nguồn] --> B[Tạo database test]
    B --> C[Chạy changelog nguồn]
    C --> D[Nạp fixture dữ liệu legacy]
    D --> E[Xác minh baseline schema và history]
    E --> F[Chạy changelog release đích]
    F --> G[Kiểm tra schema và dữ liệu sau nâng cấp]
~~~

Ví dụ:

~~~bash
liquibase \
  --changelog-file=release-2.4/db/changelog/db.changelog-master.yaml \
  update
~~~

Sau khi dựng schema nguồn, nạp dữ liệu fixture bằng script được quản lý riêng hoặc công cụ test của dự án. Tiếp đó, dùng root changelog của release đích để chạy update.

**Không dùng root changelog hiện tại để dựng fixture release cũ** rồi giả định đó là trạng thái nguồn. Làm vậy có thể khiến changeset mới đã được ghi nhận trước khi test upgrade bắt đầu.

### 3.1. Vì sao cần giữ artifact cũ?

Nếu nội dung changeset cũ bị sửa sau khi phát hành, checkout nhánh hiện tại có thể không còn tái tạo đúng schema nguồn. Cần dùng artifact/tag/commit release cũ đã được lưu trữ, không phụ thuộc vào file đã bị chỉnh sửa trong nhánh phát triển.

Bằng chứng cần lưu gồm:

- Release/tag/commit nguồn.
- Root changelog nguồn.
- Liquibase và driver version nếu có khác biệt.
- DBMS version.
- Hash của fixture hoặc bộ seed data.
- Log dựng baseline và kết quả xác minh.

## 4. Hai cách dựng baseline test

Có thể tạo trạng thái nguồn bằng hai cách chính.

### 4.1. Chạy changelog release cũ

Đây là cách phù hợp để kiểm tra toàn bộ lịch sử có thể dựng schema:

1. Tạo database trống.
2. Checkout artifact release cũ.
3. Chạy Liquibase update của release đó.
4. Nạp dữ liệu fixture.
5. Kiểm tra schema và DATABASECHANGELOG.
6. Chạy changelog hiện tại.

Ưu điểm: history và schema được hình thành từ cùng một quy trình mà release nguồn đã sử dụng.

Hạn chế: dựng database có thể tốn thời gian nếu lịch sử dài; cần lưu artifact cũ và dependency tương ứng.

### 4.2. Restore snapshot database nguồn

Có thể dùng snapshot/backup được tạo từ release cũ nếu đã được kiểm soát:

- Xác minh snapshot tương ứng phiên bản nào.
- Xác minh DBMS và schema metadata.
- Ẩn danh hóa dữ liệu nhạy cảm theo chính sách.
- Kiểm tra tính nhất quán của backup.
- Khôi phục vào database test cách ly.
- Xác minh DATABASECHANGELOG và catalog sau restore.

Ưu điểm: phản ánh gần hơn cấu trúc và dữ liệu đã vận hành.

Hạn chế: snapshot có thể chứa drift, dữ liệu nhạy cảm hoặc thay đổi ngoài artifact. Phải có nguồn gốc và quy trình làm sạch rõ ràng.

### 4.3. Khi nào không nên dùng fixture tự viết từ đầu?

Một script CREATE TABLE tự viết có thể tạo cấu trúc gần giống release cũ nhưng thiếu:

- Index hoặc constraint.
- Default và nullability.
- Trigger/function.
- DATABASECHANGELOG identity.
- Giá trị sequence.
- Các ngoại lệ dữ liệu đã tích lũy.

Nếu dùng fixture tự viết, phải chứng minh nó tương đương baseline nguồn theo hợp đồng đã xác định. Với đường nâng cấp quan trọng, ưu tiên artifact release hoặc snapshot có nguồn gốc.

## 5. Xác minh baseline trước khi chạy migration mới

Không chạy changelog đích ngay sau khi tạo fixture. Trước tiên xác nhận database thật sự ở trạng thái nguồn mong đợi.

### 5.1. Kiểm tra kết nối

Ví dụ PostgreSQL:

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS current_schema,
    current_user AS connected_user,
    version() AS db_version;
~~~

Đối chiếu với metadata test case để tránh dùng nhầm database hoặc DBMS version.

### 5.2. Kiểm tra lịch sử Liquibase

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Tên schema/bảng và tập cột cần điều chỉnh theo cấu hình, phiên bản Liquibase. Xác nhận:

- Những changeset nguồn cần có đã được ghi nhận.
- Không có changeset release đích bị chạy trước.
- FILENAME/logicalFilePath khớp artifact nguồn.
- Không có checksum mismatch chưa giải quyết.
- Các bản ghi bất thường được giải thích.

### 5.3. Kiểm tra schema nguồn

Dùng catalog DBMS để xác minh bảng, cột, datatype, constraint, index và những object quan trọng. Không chỉ kiểm tra số lượng bảng.

Nếu baseline đã drift so với artifact nguồn, dừng test và phân loại drift. Nếu tiếp tục mà không biết nguồn thực tế, kết quả upgrade khó có ý nghĩa.

## 6. Thiết kế dữ liệu legacy đại diện

Dữ liệu fixture quyết định chất lượng upgrade test. Một fixture chỉ có hàng “đẹp” thường không phát hiện lỗi chuyển đổi.

Với một bảng khách hàng, nên xem xét:

| Nhóm dữ liệu | Ví dụ | Rủi ro kiểm tra |
|---|---|---|
| Giá trị chuẩn | ACTIVE, INACTIVE | Mapping thông thường |
| NULL | legacy_status IS NULL | Default/backfill |
| Chuỗi rỗng | Chuỗi rỗng | Khác NULL |
| Khoảng trắng | Chuỗi có khoảng trắng | Trim/normalize |
| Chữ hoa/thường | active, Active | Quy tắc so sánh |
| Mã cũ | A, I, U | Mapping legacy |
| Giá trị không nhận diện | X, UNKNOWN | Chính sách ngoại lệ |
| Giá trị dài ở biên | Chuỗi đạt max length | Truncation |
| Bản ghi liên quan | Customer có orders | Foreign key và join |
| Bản ghi lớn | Số lượng lớn | Hiệu năng/backfill |

Fixture nên chứa đủ dữ liệu để kiểm tra logic, nhưng không cần copy toàn bộ production. Nếu dùng bản sao dữ liệu thật, phải tuân thủ yêu cầu bảo vệ và ẩn danh hóa.

### 6.1. Phân biệt NULL và chuỗi rỗng

Một migration có thể dùng:

~~~sql
WHERE legacy_status IS NULL
~~~

nhưng bỏ sót chuỗi rỗng. Nếu dữ liệu cũ dùng cả hai dạng, test cần có hàng cho từng trường hợp và định nghĩa rõ kết quả mong đợi.

Không tự động coi NULL, chuỗi rỗng, khoảng trắng và giá trị không nhận diện là cùng một trạng thái nếu nghiệp vụ chưa xác nhận.

## 7. Kiểm thử migration thêm cột và backfill

Một mẫu phổ biến là thêm cột mới, backfill dữ liệu từ cột legacy rồi áp dụng constraint.

Ví dụ trạng thái nguồn có orders.legacy_state với mã A/I/U. Changelog đích có thể chia thành nhiều changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-801-add-status-column"
      author: "orders-team"
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: status
                  type: varchar(24)

  - changeSet:
      id: "ORD-802-backfill-status"
      author: "orders-team"
      changes:
        - sql:
            sql: |
              UPDATE app.orders
              SET status = CASE
                  WHEN legacy_state = 'A' THEN 'ACTIVE'
                  WHEN legacy_state = 'I' THEN 'INACTIVE'
                  WHEN legacy_state = 'U' THEN 'UNKNOWN'
                  ELSE 'UNKNOWN'
              END
              WHERE status IS NULL;
~~~

Đây là ví dụ minh họa cho PostgreSQL và một mapping cụ thể. Tên schema, kiểu dữ liệu, cú pháp và quy tắc mapping phải phù hợp DBMS và nghiệp vụ thật.

### 7.1. Vì sao chia changeset?

Tách việc thêm cột và backfill giúp:

- Xác định bước nào thất bại.
- Kiểm tra schema trước/sau từng bước.
- Đánh giá thời gian và lock riêng.
- Có thể chia backfill theo batch khi dữ liệu lớn.
- Thiết kế rollout ứng dụng tương thích trong giai đoạn chuyển tiếp.

Tuy nhiên, tách changeset không tự bảo đảm dữ liệu được commit theo cách mong muốn. Cần xem transaction behavior của DBMS và runInTransaction.

### 7.2. Assertion sau backfill

~~~sql
SELECT
    legacy_state,
    status,
    COUNT(*) AS row_count
FROM app.orders
GROUP BY legacy_state, status
ORDER BY legacy_state, status;
~~~

Kiểm tra hàng chưa được chuyển đổi:

~~~sql
SELECT COUNT(*) AS rows_without_status
FROM app.orders
WHERE status IS NULL;
~~~

Nếu hợp đồng yêu cầu mọi hàng có status, kết quả phải bằng 0. Nếu còn ngoại lệ được chấp nhận, cần xác định rõ nhóm và cách xử lý; không đơn giản bỏ qua.

## 8. Chuyển đổi dữ liệu phải bảo toàn invariant

Một invariant là điều kiện nghiệp vụ phải đúng trước và sau migration.

Ví dụ:

- Mỗi order vẫn thuộc một customer hợp lệ.
- Tổng số đơn không bị giảm ngoài phạm vi đã duyệt.
- Mỗi order có đúng một trạng thái theo mapping.
- Giá trị tiền không bị làm tròn hoặc tràn precision.
- Không có duplicate theo khóa nghiệp vụ.
- Foreign key vẫn hợp lệ.
- Các trạng thái legacy không nhận diện được được ghi nhận theo chính sách.

Một migration có thể thay đổi biểu diễn nhưng phải bảo toàn ý nghĩa.

### 8.1. Đối chiếu số hàng

Ví dụ:

~~~sql
SELECT COUNT(*) AS total_orders
FROM app.orders;
~~~

So sánh số lượng trước và sau chỉ là kiểm tra ban đầu. Nếu migration chủ ý lọc/xóa hàng, cần đối chiếu theo khóa hoặc nhóm dữ liệu và ghi rõ số hàng dự kiến bị ảnh hưởng.

### 8.2. Đối chiếu mapping hai chiều

Với mapping trạng thái, nên kiểm tra cả:

- Mỗi giá trị legacy có trạng thái đích đúng.
- Không có trạng thái đích ngoài tập cho phép.
- Không có hàng bị bỏ qua.
- Không có nhiều giá trị legacy bị gộp ngoài ý muốn.

Ví dụ:

~~~sql
SELECT legacy_state, status, COUNT(*)
FROM app.orders
GROUP BY legacy_state, status;
~~~

Dùng expected result fixture để so sánh, không chỉ nhìn output bằng mắt.

## 9. Migration dữ liệu lớn và backfill theo batch

Với bảng lớn, một UPDATE duy nhất có thể:

- Giữ transaction quá lâu.
- Tạo lượng lớn WAL/redo.
- Tăng replication lag.
- Giữ lock hoặc gây contention.
- Tạo áp lực memory/temp space.
- Làm tăng thời gian rollback.
- Khiến ứng dụng bị chậm hoặc timeout.

Cần thử với dữ liệu đại diện về số lượng và phân bố. Nếu thiết kế backfill theo batch, xác định:

- Khóa phân trang ổn định.
- Kích thước batch.
- Điều kiện chọn hàng chưa xử lý.
- Marker hoặc trạng thái hoàn thành.
- Cách retry sau batch failure.
- Cách xử lý hàng mới phát sinh trong lúc backfill.
- Điểm dừng và tiếp tục.
- Số lượng lỗi/ngoại lệ.

### 9.1. Idempotency của backfill

Một backfill an toàn khi chạy lại không được gây tác động lặp ngoài dự kiến. Ví dụ:

~~~sql
UPDATE app.orders
SET status = 'ACTIVE'
WHERE legacy_state = 'A'
  AND status IS NULL;
~~~

Điều kiện status IS NULL giúp không ghi đè các hàng đã được xử lý hoặc được ứng dụng cập nhật, nhưng chỉ đúng nếu đó là chính sách mong muốn. Nếu cần cập nhật lại theo nguồn legacy, phải xác định rõ quyền ưu tiên giữa dữ liệu cũ và dữ liệu mới.

Không coi mọi UPDATE có WHERE là idempotent. Hãy chạy test hai lần và so sánh kết quả.

### 9.2. Khi backfill chạy ngoài changeset

Một số migration dữ liệu dài có thể cần job riêng thay vì một changeset transaction lớn. Khi đó phải quản lý rõ:

- Phiên bản job và artifact.
- Trạng thái tiến độ.
- Cách retry.
- Cách xác nhận hoàn thành.
- Quan hệ với changeset tiếp theo.
- Điều kiện để thêm constraint hoặc chuyển ứng dụng sang cột mới.

Không đánh dấu changeset hoàn tất chỉ vì job đã được khởi chạy. Cần có bằng chứng job hoàn tất và invariant dữ liệu đạt.

## 10. Nâng cấp datatype từ dữ liệu cũ

Thay đổi datatype thường có rủi ro cao vì dữ liệu legacy có thể không chuyển đổi được.

Ví dụ đổi customer.external_code từ varchar sang integer. Trước khi migration, tìm giá trị không phải số:

~~~sql
SELECT id, external_code
FROM app.customer
WHERE external_code IS NOT NULL
  AND external_code !~ '^[0-9]+$';
~~~

Đây là cú pháp PostgreSQL. DBMS khác có cách kiểm tra tương ứng.

Cần kiểm thử:

- NULL.
- Chuỗi rỗng.
- Khoảng trắng.
- Dấu âm/dương.
- Giá trị vượt giới hạn.
- Số có số 0 ở đầu.
- Giá trị không phải số.
- Dữ liệu có ý nghĩa định danh, không phải số học.

**Không phải mọi mã dạng số đều nên đổi thành kiểu số.** Ví dụ mã bưu chính hoặc số tài khoản có thể cần giữ số 0 đầu và không dùng phép tính.

### 10.1. Preflight dữ liệu trước ALTER

Có thể chạy truy vấn kiểm kê trước migration để xác định dữ liệu không hợp lệ. Kết quả phải được lưu và có chính sách xử lý: sửa dữ liệu, loại trừ, giữ datatype cũ hoặc dừng phát hành.

Không dùng CAST trực tiếp trên toàn bộ bảng mà chưa kiểm tra giá trị ngoại lệ.

## 11. Nâng cấp constraint trên dữ liệu đã tồn tại

Thêm NOT NULL, UNIQUE, CHECK hoặc FOREIGN KEY có thể thất bại vì dữ liệu cũ không đáp ứng.

Ví dụ tìm NULL trước khi thêm NOT NULL:

~~~sql
SELECT COUNT(*) AS null_status_count
FROM app.orders
WHERE status IS NULL;
~~~

Tìm duplicate trước unique constraint:

~~~sql
SELECT email, COUNT(*) AS duplicate_count
FROM app.customer
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Tìm foreign key orphan:

~~~sql
SELECT o.customer_id
FROM app.orders o
LEFT JOIN app.customer c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Trước khi thêm constraint:

1. Kiểm kê dữ liệu không đạt.
2. Xác định cách sửa hoặc ngoại lệ.
3. Backfill/clean dữ liệu.
4. Xác minh lại bằng assertion.
5. Thêm constraint.
6. Kiểm tra trạng thái validate/enabled theo DBMS.

Không dùng precondition tableExists để thay thế việc kiểm tra dữ liệu có đáp ứng constraint hay không.

## 12. Precondition cho upgrade path

Precondition có thể bảo vệ changeset trước khi chạy trên schema cũ.

Ví dụ changeset thêm cột status yêu cầu bảng orders tồn tại và cột chưa có:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-810-add-status"
      author: "orders-team"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: app
            tableName: orders
        - not:
            - columnExists:
                schemaName: app
                tableName: orders
                columnName: status
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: status
                  type: varchar(24)
~~~

Test các trường hợp:

| Trạng thái database nguồn | Kỳ vọng |
|---|---|
| orders tồn tại, status chưa có | Changeset có thể chạy |
| orders không tồn tại | HALT |
| status đã có nhưng chưa có history | HALT để điều tra drift |
| Kết nối không đọc được metadata | Lỗi được thể hiện rõ, không đánh dấu thành công |
| Đang kết nối nhầm schema | Test phát hiện sai đích |

### 12.1. Tránh MARK_RAN che giấu sai lệch

Nếu cột đã tồn tại nhưng datatype sai, onFail: MARK_RAN có thể ghi nhận changeset mà không thực hiện thay đổi. History sau đó có thể khiến nhóm nghĩ upgrade hoàn tất.

Khi dùng MARK_RAN, phải chứng minh trạng thái hiện có tương đương kết quả mong muốn. Nếu không, HALT và reconciliation thường an toàn hơn.

## 13. Changeset identity và checksum trong upgrade test

Liquibase thường nhận diện changeset bằng bộ ba:

~~~text
ID + AUTHOR + FILENAME (hoặc logicalFilePath)
~~~

Database release cũ đã ghi nhận identity và checksum của changeset cũ. Khi nâng cấp, root changelog hiện tại cần giữ các định danh đó ổn định.

Upgrade test phải phát hiện:

- File changelog cũ bị đổi đường dẫn.
- ID hoặc author bị thay đổi.
- Nội dung changeset đã triển khai bị sửa.
- Changelog release cũ không còn được include.
- Checksum mismatch.
- Changeset mới bị include lặp hoặc có identity không như dự kiến.

### 13.1. Vì sao fresh install không phát hiện hết checksum mismatch?

Database trống chưa có checksum cũ trong DATABASECHANGELOG. Nếu file changeset cũ bị sửa, fresh install có thể chạy nội dung mới và pass. Nhưng database release cũ có checksum trước đó sẽ báo mismatch.

Vì vậy, **upgrade test phải có DATABASECHANGELOG được hình thành từ artifact cũ**. Đây là lý do fixture từ release cũ có giá trị hơn việc tự tạo schema bằng script mà không có history.

### 13.2. Không sửa history để làm test pass

Khi checksum mismatch:

1. Xác định artifact nguồn đã triển khai.
2. So sánh changeset cũ và hiện tại.
3. Kiểm tra identity và logicalFilePath.
4. Kiểm tra schema thực tế.
5. Thường tạo changeset mới để điều chỉnh schema.
6. Chỉ dùng thao tác quản lý checksum đặc biệt khi có quyết định được review.

Không tự động chạy clear-checksums hoặc sửa MD5SUM trong CI để che lỗi.

## 14. Kiểm thử đường nâng cấp tuần tự và nhảy phiên bản

Sản phẩm cần xác định người dùng được nâng cấp theo đường nào.

Ví dụ:

~~~text
2.3 -> 2.4 -> 2.5 -> 2.6
2.4 ------> 2.6
2.5 ------> 2.6
~~~

Nếu chính sách hỗ trợ nâng cấp trực tiếp từ 2.3 lên 2.6, phải test đường đó. Nếu chỉ hỗ trợ nâng cấp tuần tự, tài liệu và công cụ triển khai phải ngăn hoặc hướng dẫn đúng đường.

### 14.1. Ma trận upgrade

| Phiên bản nguồn | Phiên bản đích | Có hỗ trợ? | Test cần có |
|---|---|---|---|
| 2.3 | 2.4 | Có | Upgrade cơ bản |
| 2.4 | 2.5 | Có | Upgrade cơ bản |
| 2.5 | 2.6 | Có | Upgrade cơ bản |
| 2.4 | 2.6 | Có | Skip release 2.5 |
| 2.3 | 2.6 | Không | Xác nhận bị từ chối hoặc yêu cầu nâng cấp trung gian |

Không cần test mọi cặp phiên bản có thể tưởng tượng. Chọn các đường được sản phẩm cam kết hỗ trợ và những đường có rủi ro cao.

### 14.2. Không bỏ qua changeset release trung gian nếu đường hỗ trợ yêu cầu nó

Nếu release 2.5 có migration chuyển đổi dữ liệu bắt buộc và 2.6 giả định dữ liệu đã chuyển, chạy thẳng 2.6 có thể thất bại. Có hai lựa chọn:

- Bắt buộc người dùng nâng cấp qua 2.5.
- Thiết kế 2.6 có khả năng xử lý trạng thái nguồn cũ hơn và test đầy đủ.

Không giả định Liquibase tự hiểu release version và tự chọn đường nâng cấp. Nó thực thi changelog cùng filter/identity đã cấu hình.

## 15. Kiểm thử ứng dụng trong giai đoạn chuyển tiếp

Một migration có thể cần nhiều release ứng dụng để hoàn tất. Ví dụ thêm status_new trong khi ứng dụng cũ vẫn dùng legacy_status.

Mô hình **expand–migrate–contract**:

1. **Expand:** thêm cột hoặc bảng mới theo cách tương thích.
2. **Deploy compatible application:** phiên bản ứng dụng có thể đọc/ghi cả cấu trúc cũ và mới.
3. **Migrate:** backfill dữ liệu và kiểm tra consistency.
4. **Switch:** chuyển luồng đọc/ghi sang cấu trúc mới.
5. **Contract:** bỏ cấu trúc cũ sau khi không còn phiên bản ứng dụng phụ thuộc.

### 15.1. Ma trận tương thích

| Ứng dụng | Schema cũ | Schema sau expand | Schema sau contract |
|---|---|---|---|
| App cũ | Hỗ trợ | Phải tương thích | Có thể không |
| App trung gian | Tùy thiết kế | Hỗ trợ | Có thể tương thích |
| App mới | Có thể hỗ trợ tạm thời | Hỗ trợ | Hỗ trợ |

Test phải xác nhận các cặp phiên bản được dùng trong rolling deployment. Chỉ kiểm tra app mới với schema cuối có thể bỏ sót lỗi khi instance cũ vẫn đang chạy.

### 15.2. Migration và startup

Nếu Spring Boot tự chạy Liquibase lúc khởi động, cần kiểm tra thời điểm migration so với việc khởi tạo bean, repository và các instance khác. Với rollout nhiều instance, cân nhắc migration job riêng và quy trình phát hành có kiểm soát.

## 16. Kiểm thử thay đổi xóa hoặc đổi tên cột

DROP COLUMN và rename thường là thay đổi khó tương thích ngược.

Ví dụ đổi customer.name thành customer.display_name. Thay đổi trực tiếp có thể làm ứng dụng cũ lỗi ngay.

Một quy trình an toàn hơn:

- Thêm cột display_name.
- Backfill từ name.
- Triển khai ứng dụng ghi/đọc cột mới theo giai đoạn.
- Xác minh dữ liệu hai cột nhất quán.
- Chuyển ứng dụng hoàn toàn.
- Chỉ xóa name trong release sau khi không còn client phụ thuộc.

Upgrade test cần có fixture từ release cũ, kiểm tra dữ liệu sau backfill, test ứng dụng ở giai đoạn chuyển tiếp và xác minh không xóa cột quá sớm.

**Rename không chỉ là thay đổi tên trong schema**; nó là thay đổi hợp đồng giữa database và tất cả client sử dụng database.

## 17. Kiểm thử default, sequence và identity

Dữ liệu cũ có thể làm lộ lỗi khi thay đổi default hoặc sequence.

Ví dụ thêm cột ID hoặc chuyển từ sequence sang identity cần kiểm tra:

- Giá trị hiện tại của sequence.
- Giá trị lớn nhất đã tồn tại trong bảng.
- Next value có đụng primary key không.
- Default có áp dụng cho insert mới không.
- Ứng dụng có tự cấp ID hay database cấp.
- Sequence owner và quyền.
- Cách DBMS xử lý cache/cycle/increment.

Sau migration, test insert một hàng mới bằng đúng cách ứng dụng thực hiện và xác minh ID không trùng.

Không chỉ kiểm tra sequence object tồn tại; cần kiểm tra hành vi sinh giá trị.

## 18. Kiểm thử index và constraint trên bảng đã có dữ liệu

Index hoặc constraint mới có thể thất bại khi dữ liệu legacy có duplicate hoặc NULL.

Ví dụ tạo unique index trên email:

~~~sql
SELECT email, COUNT(*)
FROM app.customer
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Nếu có duplicate, cần chính sách xử lý trước khi tạo index. Không xóa duplicate tự động nếu chưa xác định bản ghi nào được giữ và quan hệ tham chiếu.

Với bảng lớn, test thêm:

- Thời gian tạo index.
- Lock mode.
- Dung lượng.
- Replication lag.
- Khả năng tạo online/concurrently nếu DBMS hỗ trợ.
- Trạng thái index sau khi bị gián đoạn.

SQL và tùy chọn tạo index phụ thuộc DBMS; phải test trên cùng loại/version với production.

## 19. Kiểm thử transaction và partial state khi nâng cấp

Khi migration lỗi, trạng thái database sau lỗi phụ thuộc DBMS và ranh giới transaction.

- PostgreSQL hỗ trợ transaction cho nhiều DDL thông thường, nhưng có lệnh đặc biệt không chạy trong transaction block.
- MySQL/MariaDB có nhiều DDL implicit commit.
- Oracle thường có implicit commit quanh DDL.
- SQL Server hỗ trợ transaction cho nhiều DDL nhưng có ngoại lệ.
- SQLite có hành vi transaction DDL riêng.

Nếu một changeset gồm nhiều câu lệnh và câu cuối lỗi, có thể còn một phần thay đổi trên DBMS có implicit commit hoặc changeset chạy ngoài transaction.

### 19.1. Kiểm thử failure injection

Trên database disposable:

1. Dựng đúng baseline nguồn.
2. Tạo tình huống lỗi có kiểm soát ở giữa migration.
3. Ghi log SQL và kết quả.
4. Kiểm tra schema/data thật.
5. Kiểm tra DATABASECHANGELOG và lock.
6. Xác định có partial state không.
7. Thử kế hoạch reconciliation trên database bản sao.

Không retry mù chỉ vì changeset chưa có trong history. **Không có bản ghi history không chứng minh database chưa thay đổi.**

## 20. Kiểm thử rollback từ release mới về trạng thái cũ

Rollback migration cần được đánh giá theo dữ liệu thực tế sau khi nâng cấp.

Ví dụ sau khi thêm cột status, ứng dụng đã ghi giá trị vào đó. Rollback bằng dropColumn sẽ làm mất dữ liệu status.

Test cần trả lời:

- Rollback có được hỗ trợ không?
- Có khôi phục được giá trị cũ không?
- Có thay đổi nào không thể đảo ngược?
- Dữ liệu phát sinh sau update có được bảo toàn?
- Ứng dụng phiên bản cũ có hoạt động sau rollback không?
- Nếu rollback không an toàn, có forward fix hoặc restore không?

### 20.1. Rollback schema và rollback nghiệp vụ

Xóa cột mới có thể đưa schema gần trạng thái cũ nhưng không khôi phục nội dung dữ liệu đã bị loại bỏ. Hai khái niệm cần test riêng.

Đối với data migration có mất mát thông tin, cần lưu dữ liệu gốc hoặc thiết kế forward fix. Không coi rollback SQL chạy thành công là đủ.

### 20.2. Rollback trong CI không phải bằng chứng rollback production

CI dùng database cách ly và dữ liệu fixture. Production có workload, concurrency, kích thước dữ liệu và side effect khác. Test rollback là bằng chứng kỹ thuật, không thay thế kế hoạch phát hành/khôi phục đã được phê duyệt.

## 21. Kiểm tra DATABASECHANGELOG sau upgrade

Sau update, truy vấn history:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Kiểm tra:

- Changeset mới được ghi nhận đúng identity.
- Changeset cũ giữ nguyên lịch sử.
- Không có changeset tương lai hoặc ngoài filter bị chạy.
- EXECTYPE phù hợp, đặc biệt khi có MARK_RAN hoặc RERAN.
- Checksum không mismatch.
- Deployment metadata có thể truy vết nếu được cấu hình.

History phản ánh trạng thái Liquibase quản lý, không phải ảnh chụp schema hiện tại. Cần kiểm tra catalog song song.

### 21.1. Đối chiếu trước và sau

Có thể lưu danh sách identity trước migration và so sánh sau migration:

~~~text
Before:
  baseline-001
  baseline-002
  release-2.5-001

After:
  baseline-001
  baseline-002
  release-2.5-001
  release-2.6-001
  release-2.6-002
~~~

Kỳ vọng là những changeset mới được thêm theo phạm vi. Không chỉ so sánh số dòng; cần so sánh ID, AUTHOR và FILENAME.

## 22. Kiểm tra drift giữa fixture và môi trường thực tế

Một fixture được tạo từ artifact cũ có thể không phản ánh drift production. Ngược lại, snapshot production có thể chứa thay đổi DBA chưa được ghi vào changelog.

Để tăng độ tin cậy:

- Có test từ artifact release cũ.
- Có fixture data cho các ngoại lệ đã biết.
- Có kiểm tra diff/schema drift trên bản sao đã được phép.
- Có danh sách thay đổi ngoài Liquibase đã phê duyệt.
- Không tự động đồng bộ history để che khác biệt.

Nếu production có một index bổ sung hợp lệ, test phải quyết định index đó là phần mở rộng được hỗ trợ hay drift cần đưa vào quản lý. Không để fixture test âm thầm bỏ qua.

## 23. Kiểm thử nhiều đường nâng cấp trong CI/CD

Có thể xây ma trận pipeline:

~~~text
Job A:
  empty -> current changelog -> assertions

Job B:
  release 2.4 artifact -> fixture 2.4 data
    -> current changelog -> assertions

Job C:
  release 2.5 artifact -> fixture 2.5 data
    -> current changelog -> assertions

Job D:
  release 2.3 artifact -> release 2.4 -> release 2.5 -> current
    -> assertions (nếu đường này được hỗ trợ)
~~~

Mỗi job cần database riêng. Không chạy các đường nâng cấp song song trên cùng một database hoặc cùng DATABASECHANGELOGLOCK.

### 23.1. Chọn ma trận theo chính sách hỗ trợ

Nếu sản phẩm chỉ hỗ trợ nâng cấp từ hai release gần nhất, không cần dựng mọi phiên bản cũ hơn. Nhưng chính sách đó phải được công bố rõ và kiểm thử ở biên:

- Phiên bản cũ nhất được hỗ trợ.
- Phiên bản ngay trước hiện tại.
- Phiên bản nhảy cóc nếu được hỗ trợ.
- DBMS/version quan trọng.
- Những migration có rủi ro dữ liệu cao.

### 23.2. Lưu artifact cũ trong CI

Không nên phụ thuộc vào việc Git tag còn tồn tại hoặc repository bên ngoài có thể truy cập tại thời điểm test. Lưu artifact changelog/release cần thiết theo retention policy để có thể tái tạo fixture nguồn.

## 24. Tích hợp với Spring Boot

Khi Spring Boot sử dụng Liquibase, upgrade test nên kiểm tra cả migration và ứng dụng.

Ví dụ cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_upgrade_test
    username: app_runtime
    password: "<inject-at-runtime>"
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    user: migration_user
    password: "<inject-at-runtime>"
~~~

Đây là cấu hình minh họa. Việc dùng datasource riêng cho Liquibase, thứ tự startup và cách cấp credential phải phù hợp phiên bản Spring Boot/Liquibase và chính sách bảo mật.

Một integration test có thể:

1. Dựng database ở release cũ.
2. Nạp fixture dữ liệu legacy.
3. Khởi động application context với changelog hiện tại.
4. Xác minh Liquibase đã chạy đúng changeset.
5. Gọi repository/service để đọc dữ liệu đã chuyển đổi.
6. Thực hiện một thao tác ghi mới.
7. Xác minh ứng dụng và database cùng hiểu schema mới.

Không chỉ assert application context khởi động thành công. Cần kiểm tra một số đường truy cập dữ liệu thực tế.

## 25. Kiểm thử quyền và cấu hình môi trường

Upgrade có thể chạy được bằng tài khoản DBA nhưng thất bại bằng migration user của production.

Test với quyền tương đương môi trường đích:

- Đọc metadata/schema cần thiết.
- ALTER/CREATE/DROP object trong phạm vi.
- Tạo index/constraint.
- Chạy data migration.
- Ghi DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- Thực hiện grant/owner nếu changelog có yêu cầu.

Tài khoản ứng dụng runtime nên được test riêng với quyền tối thiểu. Không cấp quyền DBA cho ứng dụng chỉ để migration pass.

Cũng cần xác minh URL, database/catalog, default schema, Liquibase metadata schema, contexts và labels. Một test chạy nhầm schema có thể pass nhưng không kiểm tra database mục tiêu.

## 26. Kiểm thử hiệu năng trên dữ liệu gần thực tế

Đối với migration trên bảng lớn, cần đo:

- Thời gian hoàn thành.
- Lock wait và thời gian giữ lock.
- Số hàng được backfill.
- WAL/redo/transaction log.
- CPU, I/O, memory và temp space.
- Replication lag.
- Query latency trong thời gian migration.
- Dung lượng index và table sau thay đổi.

Không cần dùng toàn bộ dữ liệu production nếu không được phép. Có thể tạo dữ liệu tổng hợp với số lượng, phân bố và quan hệ tương tự.

Một test với 1.000 hàng không thể chứng minh UPDATE trên 100 triệu hàng sẽ hoàn thành trong cửa sổ bảo trì.

## 27. Quy trình điều tra khi upgrade test thất bại

Khi migration lỗi, giữ nguyên database test đủ lâu để điều tra, trừ khi chính sách CI yêu cầu dọn dẹp sau khi lưu snapshot/log.

Thứ tự điều tra:

1. Xác nhận đúng phiên bản nguồn, DBMS và artifact.
2. Xác nhận baseline schema/data trước khi update.
3. Đọc lỗi Liquibase và SQL/driver log.
4. Xác định changeset và statement thất bại.
5. Kiểm tra transaction behavior và runInTransaction.
6. Truy vấn schema thực tế để tìm partial state.
7. Kiểm tra DATABASECHANGELOG và DATABASECHANGELOGLOCK.
8. Kiểm tra dữ liệu bị tác động.
9. Phân loại lỗi do changelog, fixture, filter, quyền hay DBMS.
10. Sửa nguyên nhân rồi chạy lại từ baseline sạch.

Không sửa history thủ công hoặc xóa database ngay khi lỗi xuất hiện nếu cần bằng chứng để xác định trạng thái.

### 27.1. Không retry trên database đã partial state mà chưa reconciliation

Nếu một DDL đã implicit commit nhưng changeset chưa ghi history, lần retry có thể báo object exists. Trước khi chạy lại, phải quyết định:

- Hoàn tất thao tác còn thiếu.
- Rollback phần đã thực thi nếu an toàn.
- Dùng forward fix.
- Restore baseline fixture và chạy lại test.

Lựa chọn phải dựa trên trạng thái thực tế, không chỉ exit code.

## 28. Ví dụ tổng hợp: nâng cấp từ release 2.4 lên 2.5

**Trạng thái release 2.4:**

~~~sql
CREATE TABLE app.customer (
    id BIGINT PRIMARY KEY,
    legacy_status VARCHAR(8)
);
~~~

Dữ liệu:

| id | legacy_status |
|---:|---|
| 1 | A |
| 2 | I |
| 3 | U |
| 4 | NULL |
| 5 | X |

**Mục tiêu release 2.5:** thêm status với tập giá trị ACTIVE, INACTIVE, UNKNOWN; mọi hàng được chuyển đổi theo quy tắc đã phê duyệt.

### 28.1. Changeset minh họa

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "CUS-901-add-status"
      author: "customer-team"
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(24)

  - changeSet:
      id: "CUS-902-backfill-status"
      author: "customer-team"
      changes:
        - sql:
            sql: |
              UPDATE app.customer
              SET status = CASE
                  WHEN legacy_status = 'A' THEN 'ACTIVE'
                  WHEN legacy_status = 'I' THEN 'INACTIVE'
                  WHEN legacy_status = 'U' THEN 'UNKNOWN'
                  WHEN legacy_status IS NULL THEN 'UNKNOWN'
                  ELSE 'UNKNOWN'
              END
              WHERE status IS NULL;
~~~

Đây là ví dụ PostgreSQL. Trong sản phẩm thực tế, giá trị X cần được phân loại rõ: chuyển UNKNOWN, lưu bảng lỗi hay dừng migration. Không để nhánh ELSE quyết định chính sách nghiệp vụ một cách âm thầm.

### 28.2. Kết quả mong đợi

| id | legacy_status | status |
|---:|---|---|
| 1 | A | ACTIVE |
| 2 | I | INACTIVE |
| 3 | U | UNKNOWN |
| 4 | NULL | UNKNOWN |
| 5 | X | UNKNOWN (nếu đây là chính sách được phê duyệt) |

Assertion:

~~~sql
SELECT id, legacy_status, status
FROM app.customer
ORDER BY id;
~~~

Và:

~~~sql
SELECT COUNT(*) AS invalid_rows
FROM app.customer
WHERE status IS NULL
   OR status NOT IN ('ACTIVE', 'INACTIVE', 'UNKNOWN');
~~~

Kỳ vọng invalid_rows = 0 nếu hợp đồng yêu cầu tất cả hàng được chuyển đổi.

### 28.3. Các đường test

- Fresh install: chạy baseline hiện tại và release 2.5 từ database trống.
- Upgrade: dựng release 2.4 bằng artifact cũ, nạp năm hàng fixture rồi chạy release 2.5.
- Retry: chạy update lần hai và xác minh dữ liệu không đổi ngoài dự kiến.
- Rollback: chỉ thử trên database disposable; xác minh cả schema và dữ liệu theo rollback contract.
- Application: kiểm tra repository/service đọc status và vẫn xử lý được dữ liệu legacy.

## 29. Ví dụ nâng cấp constraint sau backfill

Sau khi status được backfill, release tiếp theo có thể muốn thêm NOT NULL và CHECK constraint.

Trước tiên test dữ liệu:

~~~sql
SELECT COUNT(*)
FROM app.customer
WHERE status IS NULL;
~~~

~~~sql
SELECT status, COUNT(*)
FROM app.customer
GROUP BY status;
~~~

Sau đó changeset có thể thêm constraint theo cú pháp DBMS phù hợp. Trên bảng lớn, cần đánh giá khả năng validate constraint, lock và cách chia giai đoạn. Không thêm constraint chỉ vì backfill script không báo lỗi; phải xác minh dữ liệu đã đạt invariant.

## 30. Lỗi thường gặp khi kiểm thử upgrade path

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Fresh install pass, upgrade fail | Dữ liệu legacy không đáp ứng constraint | Bổ sung fixture và preflight data |
| Upgrade pass trên schema tự dựng nhưng fail trên release cũ | Fixture thiếu history/index/trigger | Dựng từ artifact hoặc snapshot nguồn |
| Checksum mismatch | Changeset cũ đã bị sửa | Giữ lịch sử, tạo changeset mới |
| Changeset không chạy | Filter hoặc history nguồn không đúng | Kiểm tra contexts/labels/dbms và DATABASECHANGELOG |
| Backfill còn NULL | Mapping thiếu trường hợp | Bổ sung fixture ngoại lệ và quy tắc xử lý |
| Duplicate/unique constraint fail | Dữ liệu cũ có duplicate | Phân loại và xử lý dữ liệu trước constraint |
| Cast datatype thất bại | Giá trị legacy không hợp lệ | Kiểm tra preflight, mapping hoặc giữ kiểu cũ |
| Migration chạy quá lâu | Dataset nhỏ, thiếu index hoặc transaction lớn | Test dữ liệu đại diện và batch |
| Rollback làm mất dữ liệu | Rollback DROP/UPDATE không phục hồi giá trị gốc | Backup, lưu dữ liệu gốc hoặc forward fix |
| Retry báo object exists | Partial DDL sau failure/implicit commit | Reconciliation trước retry |
| Ứng dụng cũ lỗi trong rollout | Thay đổi không tương thích ngược | Expand–migrate–contract |
| Sequence tạo ID trùng | Sequence không được đồng bộ với dữ liệu cũ | Kiểm tra giá trị max và next value |
| Test pass bằng DBA, fail production | Migration user thiếu quyền | Test bằng role tương đương production |
| Staging khác production | Drift hoặc snapshot không đại diện | Phân loại drift và kiểm thử nhiều baseline |
| History có MARK_RAN nhưng schema thiếu | Precondition đánh dấu mà không thực thi | Kiểm tra EXECTYPE và catalog |
| Update nhầm database/schema | Connection config sai | Xác minh endpoint và schema trước ghi |
| Đường nâng cấp nhảy cóc fail | Release trung gian chứa migration bắt buộc | Công bố và test đúng upgrade policy |

## 31. Checklist phê duyệt kiểm thử nâng cấp

- [ ] Đã xác định phiên bản nguồn và phiên bản đích.
- [ ] Đã ghi rõ những đường nâng cấp được hỗ trợ.
- [ ] Artifact changelog nguồn được cố định theo release/tag/commit.
- [ ] Fixture được dựng từ artifact cũ hoặc snapshot có nguồn gốc.
- [ ] DATABASECHANGELOG và schema nguồn được xác minh.
- [ ] Fixture có NULL, chuỗi rỗng, dữ liệu biên và giá trị legacy ngoại lệ.
- [ ] Dữ liệu nhạy cảm được ẩn danh hóa hoặc thay bằng dữ liệu tổng hợp.
- [ ] Có test fresh install và upgrade path riêng.
- [ ] Có test nâng cấp tuần tự/nhảy phiên bản theo chính sách.
- [ ] Chạy validate, status và review update-sql.
- [ ] Kiểm tra identity và checksum của changeset cũ.
- [ ] Có schema assertions sau migration.
- [ ] Có data assertions và kiểm tra invariant nghiệp vụ.
- [ ] Backfill được kiểm tra idempotency, batch và retry nếu cần.
- [ ] Precondition được test với cả điều kiện đạt và không đạt.
- [ ] MARK_RAN được kiểm tra riêng nếu sử dụng.
- [ ] Constraint được thêm sau khi dữ liệu đã đạt yêu cầu.
- [ ] Có kiểm tra sequence/identity nếu thay đổi liên quan.
- [ ] Đánh giá DDL transaction, implicit commit và partial state.
- [ ] Kiểm tra tương thích ứng dụng trong rolling deployment.
- [ ] Rollback được test trên database disposable và đánh giá mất dữ liệu.
- [ ] Hiệu năng/lock được test với dữ liệu đại diện cho bảng lớn.
- [ ] Test dùng DBMS/version/driver gần môi trường đích.
- [ ] CI database được cô lập theo job.
- [ ] Có log, artifact, version, fixture hash và kết quả assertions.
- [ ] Có phương án reconciliation, forward fix hoặc restore khi upgrade thất bại.
- [ ] Không chỉnh sửa DATABASECHANGELOG thủ công để làm test pass.
- [ ] Không dùng production làm nơi thử rollback hoặc failure injection.

## 32. Câu hỏi tự kiểm tra

**1. Vì sao kiểm thử database trống chưa đủ?**

Vì database cũ có dữ liệu và schema đã tích lũy; migration có thể thất bại do NULL, duplicate, datatype, dependency hoặc checksum dù fresh install thành công.

**2. Vì sao nên dựng baseline bằng artifact release cũ?**

Để schema và DATABASECHANGELOG phản ánh đúng changeset đã triển khai, tránh fixture tự viết thiếu lịch sử hoặc đối tượng.

**3. Khi nào cần test nâng cấp nhảy phiên bản?**

Khi sản phẩm tuyên bố hỗ trợ bỏ qua một hoặc nhiều release trung gian. Mỗi đường được hỗ trợ cần có test tương ứng.

**4. Vì sao checksum mismatch có thể chỉ xuất hiện trên upgrade test?**

Database cũ đã lưu checksum của changeset; database trống chưa có checksum cũ để so sánh.

**5. Vì sao phải có dữ liệu NULL và giá trị không nhận diện?**

Để kiểm tra mapping và constraint trên dữ liệu thực tế có thể gặp trong quá trình vận hành, thay vì chỉ test giá trị lý tưởng.

**6. Backfill chạy lại có thể gây lỗi gì?**

Có thể ghi đè dữ liệu mới, nhân đôi tác động hoặc làm sai mapping nếu SQL không idempotent.

**7. MARK_RAN có chứng minh migration đã tạo object không?**

Không. Nó có thể đánh dấu changeset mà không thực thi changes; cần kiểm tra schema và EXECTYPE.

**8. Vì sao cần kiểm thử ứng dụng cũ với schema sau expand?**

Vì rolling deployment có thể còn instance cũ đang chạy trong khi database đã được nâng cấp.

**9. Nếu migration lỗi và history không có changeset, có thể retry ngay không?**

Không. DDL có thể đã partial commit; phải kiểm tra schema/data thật và lập kế hoạch reconciliation.

**10. Rollback DROP COLUMN có khôi phục dữ liệu trong cột không?**

Không. Nếu cần giữ dữ liệu, phải có bản sao hoặc phương án khôi phục/forward fix.

**11. Vì sao cần test bằng migration user giống production?**

Để phát hiện lỗi quyền mà tài khoản DBA trong môi trường test có thể che giấu.

**12. Bằng chứng nào cần lưu cho upgrade test?**

Artifact nguồn/đích, DBMS/version, fixture, history, log migration, schema/data assertions, thời gian và kết luận.

**Kết luận:** Kiểm thử nâng cấp phải bắt đầu từ **schema, lịch sử Liquibase và dữ liệu của một phiên bản nguồn xác định**. Hãy dựng fixture từ artifact release cũ hoặc snapshot có nguồn gốc, kiểm tra cả đường nâng cấp tuần tự và nhảy phiên bản được hỗ trợ, rồi xác minh schema, dữ liệu, history và ứng dụng sau migration. Dữ liệu legacy cần có NULL, duplicate, giá trị biên và ngoại lệ để làm lộ lỗi backfill/constraint; migration lớn cần đo lock và thời gian trên dữ liệu đại diện. Khi fresh install, upgrade path, rollback/recovery và CI đều có tiêu chí kiểm tra rõ ràng, nhóm mới có bằng chứng đáng tin cậy rằng Liquibase có thể đưa database đang vận hành sang phiên bản mới mà vẫn giữ đúng dữ liệu và hợp đồng ứng dụng.

