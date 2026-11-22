# Hoàn tác theo tag, số lượng changeset hoặc thời điểm trong Liquibase

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với **changelog, changeset, precondition, checksum và lịch sử triển khai**; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Khi một bản phát hành gặp sự cố, đội ngũ vận hành cần trả lời nhanh: **cần quay lại mốc nào, những changeset nào sẽ bị hoàn tác, dữ liệu nào có thể mất và có thể kiểm chứng kết quả ra sao?**

Liquibase cung cấp các cách xác định phạm vi rollback bằng **tag**, **số lượng changeset** hoặc **thời điểm**. Cả ba đều dựa vào lịch sử thực thi của database, nhưng không tương đương nhau và không tự bảo đảm có thể khôi phục dữ liệu. Bài học thuộc phần **Hoàn tác**, hướng dẫn lựa chọn đúng cơ chế, tạo và kiểm tra mốc, preview SQL hoàn tác, đánh giá rủi ro DDL/DML, diễn tập trên database có thể tạo lại và phối hợp an toàn với Spring Boot/CI/CD.

Các lệnh minh họa theo dòng CLI hiện đại của Liquibase, dùng PostgreSQL làm database thử nghiệm. **Tên option, định dạng tham số thời gian và hỗ trợ từng change type có thể khác theo phiên bản Liquibase/DBMS**, nên phải dùng `liquibase --help` cùng tài liệu của phiên bản đang triển khai để xác nhận trước khi áp dụng thực tế.

## 1. Ba cách chọn điểm rollback: khác nhau ở đâu?

| Cơ chế | Lệnh CLI thường dùng | Đối tượng được chọn | Điểm mạnh | Rủi ro chính |
|---|---|---|---|---|
| **Theo tag** | `rollback --tag=release-1` | Những changeset đã thực thi **sau** mốc tag | Diễn đạt mốc phát hành rõ ràng | Tag sai vị trí, tag không tồn tại hoặc bị gắn trên lịch sử không mong muốn |
| **Theo số lượng** | `rollback-count --count=2` | Hai changeset thực thi gần nhất có thể hoàn tác | Hữu ích khi cần bỏ chính xác một số changeset | Đếm nhầm changeset với câu SQL, nhầm thứ tự triển khai |
| **Theo thời điểm** | `rollback-to-date --date="2026-11-19 09:00:00"` | Những changeset được ghi nhận thực thi sau mốc thời gian yêu cầu | Hữu ích khi biết thời điểm database còn ở trạng thái mong muốn | Sai múi giờ, độ chính xác timestamp hoặc nhầm lịch sử từ nhiều lần deploy |

Mỗi cách chọn **tập changeset sẽ hoàn tác**, không trực tiếp chọn “phiên bản mã nguồn Git”, “số bảng” hoặc “số lượng hàng dữ liệu”. Liquibase tính toán dựa trên bảng lịch sử `DATABASECHANGELOG`, thông tin mốc và hành vi thực thi của phiên bản đang dùng.

**Điểm cốt lõi:** rollback là **thực thi những thao tác đảo ngược** chứ không phải quay ngược thời gian database một cách toàn diện. Một changeset có thể có nhiều câu SQL; undo một changeset có thể tác động hàng triệu hàng, hoặc không thể phục hồi dữ liệu đã mất.

## 2. Hiểu `DATABASECHANGELOG` trước khi hoàn tác

Liquibase theo dõi changeset đã chạy trong bảng `DATABASECHANGELOG`, thường chứa các cột:

| Cột | Ý nghĩa trong kiểm tra rollback |
|---|---|
| `ID` | Mã changeset do tác giả đặt |
| `AUTHOR` | Tác giả changeset |
| `FILENAME` | Đường dẫn định danh changelog hoặc đường dẫn logic |
| `DATEEXECUTED` | Thời điểm được ghi nhận khi thực thi |
| `ORDEREXECUTED` | Thông tin thứ tự thực thi trong lịch sử |
| `EXECTYPE` | Trạng thái/kiểu ghi nhận thực thi, ví dụ `EXECUTED` hoặc `MARK_RAN` |
| `MD5SUM` | Checksum được Liquibase lưu cho changeset |
| `TAG` | Giá trị tag nếu lịch sử có mốc gắn tương ứng |

Truy vấn quan sát lịch sử trên PostgreSQL:

```sql
SELECT
    id,
    author,
    filename,
    dateexecuted,
    orderexecuted,
    exectype,
    tag,
    md5sum
FROM databasechangelog
ORDER BY orderexecuted;
```

Trong ví dụ, tên bảng/cột viết thường phù hợp quy tắc tên không đặt dấu nháy của PostgreSQL; trên DBMS khác cần điều chỉnh schema và cách viết tên. Hãy kiểm tra cả `ID`, `AUTHOR`, `FILENAME` vì **`id` đơn lẻ không phải định danh đầy đủ**. Khi di chuyển changelog từ file system sang classpath/JAR, việc đổi đường dẫn định danh có thể làm cùng một changeset bị nhận diện thành thay đổi khác nếu không có `logicalFilePath` nhất quán.

Liquibase sử dụng metadata và thứ tự thực thi để xác định phạm vi rollback. Đừng tự `DELETE` hoặc `UPDATE` bảng `DATABASECHANGELOG` để “đánh dấu hoàn tác”. Sửa lịch sử thủ công có thể làm công cụ mất khả năng phân biệt những thay đổi nào thật sự đã chạy.

### 2.1. Rollback theo thứ tự ngược

Giả sử một lần nâng cấp đã chạy các changeset `001`, `002`, `003`, `004`. Để quay về trạng thái sau `002`, Liquibase cần đảo ngược **`004` trước, rồi `003`**. Đó là lý do phần rollback của những changeset về sau phải tính đến các phụ thuộc do changeset trước tạo ra.

Ví dụ: `003` tạo index trên một cột được thêm ở `002`. Khi undo `003` trước, index bị xóa; nếu tiếp tục undo `002`, cột mới bị xóa sau. Chọn thứ tự ngược giúp giảm một số xung đột phụ thuộc, nhưng không bảo đảm mọi thao tác đều an toàn: foreign key, dữ liệu mới và các tiến trình ứng dụng có thể làm rollback thất bại.

## 3. Bộ changelog mẫu dùng chung cho ba cách rollback

Ta xây dựng một ví dụ nhỏ trên database thử nghiệm. Mỗi changeset đều khai báo thao tác `rollback` tường minh để dễ quan sát.

File `db/changelog/master.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-demo-product"
      author: "db-team"
      changes:
        - createTable:
            tableName: demo_product
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: sku
                  type: VARCHAR(40)
                  constraints:
                    nullable: false
                    unique: true
      rollback:
        - dropTable:
            tableName: demo_product

  - changeSet:
      id: "002-add-category"
      author: "db-team"
      changes:
        - addColumn:
            tableName: demo_product
            columns:
              - column:
                  name: category
                  type: VARCHAR(60)
      rollback:
        - dropColumn:
            tableName: demo_product
            columnName: category

  - changeSet:
      id: "003-index-category"
      author: "db-team"
      changes:
        - createIndex:
            tableName: demo_product
            indexName: idx_demo_product_category
            columns:
              - column:
                  name: category
      rollback:
        - dropIndex:
            tableName: demo_product
            indexName: idx_demo_product_category

  - changeSet:
      id: "004-add-published"
      author: "db-team"
      changes:
        - addColumn:
            tableName: demo_product
            columns:
              - column:
                  name: published
                  type: BOOLEAN
                  defaultValueBoolean: false
      rollback:
        - dropColumn:
            tableName: demo_product
            columnName: published
```

Mỗi thay đổi có một mục đích:

| Changeset | Forward migration | Rollback khai báo |
|---|---|---|
| `001` | Tạo bảng `demo_product` | Xóa bảng `demo_product` |
| `002` | Thêm cột `category` | Xóa cột `category` |
| `003` | Tạo index cho `category` | Xóa index |
| `004` | Thêm cột `published` với default | Xóa cột `published` |

**Cảnh báo:** ví dụ dùng `dropTable` và `dropColumn` để minh họa. Nếu bảng/cột đã có dữ liệu được tạo sau khi triển khai, rollback sẽ làm mất dữ liệu tương ứng. **Chỉ chạy ví dụ trên database luyện tập có thể tạo lại**, không sao chép nguyên xi vào production.

### 3.1. Tạo mốc sau changeset `002` để diễn tập

Giả sử JDBC driver, thông tin kết nối và `changeLogFile` đã được cấu hình trong `liquibase.properties`. Một cách thiết lập trên **database mới** là áp dụng hai changeset đầu trước:

```bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties update-count --count=2
```

Sau đó tạo tag khi lịch sử kết thúc tại `002`, rồi áp dụng hai changeset còn lại:

```bash
liquibase --defaults-file=liquibase.properties tag --tag=release-1
liquibase --defaults-file=liquibase.properties update
```

Lúc này, lịch sử kỳ vọng có:

```text
001-create-demo-product       EXECUTED
002-add-category              EXECUTED    TAG=release-1
003-index-category            EXECUTED
004-add-published             EXECUTED
```

Đây là **trạng thái minh họa**, không phải output thực tế đã được chạy. Trong phiên bản sử dụng, lệnh `tag` thường gắn mốc với lịch sử hiện có; hãy truy vấn `DATABASECHANGELOG` để xác minh giá trị `TAG` nằm ở bản ghi mong muốn. Nếu CLI/phiên bản không hỗ trợ đúng cú pháp `update-count`/`tag` trong ví dụ, hãy xem `--help` và triển khai thành hai đợt changelog trên database luyện tập thay vì đoán tên option.

## 4. Rollback theo tag: quay về một mốc phát hành

Tag là một **điểm đánh dấu trong lịch sử database**. Có thể dùng tag để biểu diễn ranh giới của một đợt triển khai, chẳng hạn `release-1`, `before-pricing-v2` hoặc `schema-baseline-2026-11`. Tag không đồng nghĩa với một nhánh Git hay một bản sao dữ liệu.

Trong trạng thái ví dụ sau `004`, yêu cầu “quay về `release-1`” thường có nghĩa:

- Hoàn tác `004-add-published`.
- Hoàn tác `003-index-category`.
- Giữ `002-add-category` và `001-create-demo-product`.

### 4.1. Xác minh tag trước khi làm gì khác

Xem lịch sử:

```sql
SELECT id, author, filename, tag, orderexecuted, dateexecuted
FROM databasechangelog
WHERE tag IS NOT NULL
ORDER BY orderexecuted;
```

Đảm bảo mốc `release-1` tồn tại **trên đúng database** và gắn với changeset mong muốn. Một số phiên bản có lệnh `tag-exists` giúp kiểm tra mốc; nếu dùng, xác nhận cú pháp với `liquibase --help`. Không gắn tag mới ở cuối lịch sử rồi tưởng rằng tag đó tương đương mốc cần quay về ở quá khứ.

### 4.2. Preview SQL rollback theo tag

```bash
liquibase --defaults-file=liquibase.properties rollback-sql --tag=release-1
```

Trong ví dụ, SQL preview dự kiến gồm thao tác xóa cột `published`, rồi xóa index `idx_demo_product_category`. Xem output để xác nhận **không có lệnh xóa bảng `demo_product` hoặc cột `category`**, đồng thời không có DML có thể mất dữ liệu ngoài dự kiến.

### 4.3. Thực thi rollback theo tag

**Chỉ trên database thử nghiệm sau khi đã preview và chấp nhận tác động:**

```bash
liquibase --defaults-file=liquibase.properties rollback --tag=release-1
```

Sau chạy, kiểm tra schema và lịch sử `DATABASECHANGELOG`. Những changeset đã được hoàn tác theo cơ chế bình thường không còn được ghi là đã chạy; nếu changelog vẫn chứa chúng, một lần `update` về sau có thể áp dụng lại.

**Phân biệt các loại tag:** ngoài CLI `tag`, Liquibase còn có change type `tagDatabase` để ghi một mốc ngay trong changelog. Cách một tag marker trong changelog được ghi nhận và xử lý khi rollback có thể khác với tag gắn qua CLI, đặc biệt qua các phiên bản Liquibase. Trước khi chọn chiến lược dùng `tagDatabase`, cần đọc tài liệu của phiên bản thực tế và thử xác minh tập changeset sẽ bị hoàn tác bằng `rollback-sql`. Không suy rằng hai loại tag có hành vi ranh giới hoàn toàn giống nhau trong mọi phiên bản.

## 5. Rollback theo số lượng changeset

Khi biết chắc những thay đổi cuối cùng cần gỡ nhưng không có tag phù hợp, có thể chọn **số lượng changeset**:

```bash
liquibase --defaults-file=liquibase.properties rollback-count-sql --count=2
```

Nếu preview đúng tập cần hoàn tác, trên database thử nghiệm:

```bash
liquibase --defaults-file=liquibase.properties rollback-count --count=2
```

Với lịch sử mẫu còn đủ bốn changeset, `count=2` chọn **hai changeset cuối**: `004` và `003`. Điều này tương đương với quay về tag `release-1` **chỉ trong ví dụ này**, bởi tag tình cờ nằm sau `002`.

### 5.1. `count` đếm changeset, không đếm câu SQL

Ví dụ changeset sau tạo hai cột trong cùng một phần tử:

```yaml
databaseChangeLog:
  - changeSet:
      id: "005-add-contact-fields"
      author: "db-team"
      changes:
        - addColumn:
            tableName: demo_product
            columns:
              - column:
                  name: contact_email
                  type: VARCHAR(255)
              - column:
                  name: contact_phone
                  type: VARCHAR(30)
      rollback:
        - dropColumn:
            tableName: demo_product
            columnName: contact_email
        - dropColumn:
            tableName: demo_product
            columnName: contact_phone
```

Nếu `005` là changeset cuối, `rollback-count --count=1` nhắm đến **cả changeset `005`**, không phải chỉ một trong hai cột. Một changeset chứa nhiều change type hoặc SQL statement vẫn là **một đơn vị đếm**.

### 5.2. Vì sao rollback-count dễ bị dùng sai?

- Trong khi một người đang chuẩn bị rollback, pipeline khác có thể vừa chạy thêm changeset. “Hai changeset cuối” không còn là hai thay đổi mà người vận hành dự định gỡ.
- Một số changeset được ghi bằng `MARK_RAN` hoặc có thuộc tính chạy đặc biệt; cần kiểm tra `EXECTYPE` và preview của đúng phiên bản thay vì suy từ số dòng trong changelog.
- Các changeset thuộc nhiều file `include` hoặc nhiều đợt triển khai cùng góp vào lịch sử: `count=2` không có nghĩa “hai file” hay “hai lần release”.
- Việc rollback một changeset có thể gồm nhiều SQL statement và thời gian chạy đáng kể.

Vì vậy chỉ dùng rollback-count khi đã **đọc lịch sử vừa trước lúc thực thi** và có thể chứng minh chính xác `count` tương ứng tập thay đổi mong muốn. Trong môi trường có nhiều tác nhân triển khai, cần phối hợp để không có migration mới xen vào giữa preview và rollback.

## 6. Rollback theo thời điểm

Rollback theo thời điểm nhắm tới trạng thái lịch sử trước hoặc tại một **mốc datetime**:

```bash
liquibase --defaults-file=liquibase.properties rollback-to-date-sql --date="2026-11-19 09:00:00"
```

Và, chỉ khi preview đạt yêu cầu:

```bash
liquibase --defaults-file=liquibase.properties rollback-to-date --date="2026-11-19 09:00:00"
```

Định dạng date được chấp nhận có thể phụ thuộc phiên bản và cách gọi CLI; ví dụ chỉ mang tính minh họa. **Không sử dụng thời điểm trong ví dụ để chạy trên database thật.** Phải chọn thời điểm dựa trên lịch sử thực tế, múi giờ và ranh giới bản phát hành cần giữ.

Giả sử `DATABASECHANGELOG` trên một database luyện tập ghi:

| Changeset | `DATEEXECUTED` minh họa | Ý nghĩa |
|---|---|---|
| `001` | 2026-11-19 08:40:00 | Tạo bảng |
| `002` | 2026-11-19 08:41:00 | Thêm cột `category` |
| `003` | 2026-11-19 10:10:00 | Tạo index |
| `004` | 2026-11-19 10:11:00 | Thêm cột `published` |

Mốc `09:00:00` nằm giữa `002` và `003`. Khi được Liquibase diễn giải cùng múi giờ và độ chính xác như dự định, rollback-to-date sẽ nhắm đến `004` và `003`, giữ lại `001` và `002`.

### 6.1. Thời điểm triển khai không đồng nghĩa với thời điểm nghiệp vụ

Trường `DATEEXECUTED` là metadata thực thi changeset, không phải ngày tạo commit hay thời điểm một hàng dữ liệu được thêm bằng ứng dụng. Lệnh `rollback-to-date` không khôi phục bảng về toàn bộ dữ liệu đã có lúc 09:00:00; nó chỉ chọn changeset để chạy thao tác rollback.

Các câu hỏi cần xác minh:

1. **Múi giờ:** tham số CLI được diễn giải theo múi giờ nào và `DATEEXECUTED` được driver/DBMS hiển thị trong múi giờ nào?
2. **Độ chính xác:** nhiều changeset có thể có timestamp cùng giây; đặt mốc đúng tại ranh giới có thể khiến tập hoàn tác khó dự đoán nếu không xem preview.
3. **Nhiều đợt deploy:** một mốc quá xa có thể kéo theo changeset của một release khác.
4. **Các DBMS và môi trường khác nhau:** đồng hồ, timezone session và lịch sử có thể không tương đồng; không tái sử dụng một timestamp của staging để rollback production.
5. **Lịch sử đặc biệt:** thay đổi thông tin `DATABASECHANGELOG`, di chuyển changelog hoặc chạy lại changeset có thể ảnh hưởng cách kiểm tra ranh giới.

### 6.2. Ưu tiên một khoảng thời gian rõ ràng

Để chọn thời điểm, truy vấn lịch sử và xác định một khoảng **không chứa changeset đang được thực thi**, sau đó chọn cutoff nằm giữa hai nhóm changeset. Nếu không có khoảng rõ ràng vì nhiều changeset chạy sát nhau, **đừng đoán thêm giây**; cân nhắc dùng tag được xác minh hoặc rollback-count sau khi xác định chính xác số changeset.

Không nhầm `rollback-to-date` với **point-in-time recovery (PITR)** của database. PITR dựa vào backup/WAL/redo log hoặc cơ chế phục hồi của DBMS để khôi phục trạng thái vật lý trong thời gian, thường yêu cầu quy trình riêng. Liquibase rollback chỉ đảo ngược những changeset mà Liquibase quản lý và có khả năng hoàn tác.

## 7. Ma trận so sánh ba lệnh trên cùng một trạng thái

Giả sử database thử nghiệm có bốn changeset `001`→`004`, tag `release-1` được gắn sau `002` và `003`/`004` chạy sau 09:00.

| Lệnh được preview | Các changeset kỳ vọng bị hoàn tác | Các changeset được giữ |
|---|---|---|
| `rollback-sql --tag=release-1` | `004`, `003` | `002`, `001` |
| `rollback-count-sql --count=2` | `004`, `003` | `002`, `001` |
| `rollback-to-date-sql --date="2026-11-19 09:00:00"` | `004`, `003` | `002`, `001` |
| `rollback-count-sql --count=1` | `004` | `003`, `002`, `001` |

Ba dòng đầu **chỉ tình cờ cùng kết quả vì lịch sử được dựng có chủ đích**. Trong production, tag, count và thời điểm có thể chọn các phạm vi khác nhau. Không dùng bảng này làm kết quả dự đoán cho một database khác nếu chưa đọc lịch sử và SQL preview.

**Cách chọn cơ chế:** nếu có tag rõ mốc release và đã kiểm tra tag, thường ưu tiên tag vì người review hiểu phạm vi; nếu cần gỡ một vài changeset cuối với lịch sử ổn định, count dễ xác minh; nếu sự cố được phát hiện theo mốc thời gian và biết chính xác vùng lịch sử, date có thể hữu ích nhưng đòi kiểm tra timezone cẩn thận.

## 8. SQL preview là bước bắt buộc trước khi thực thi

Liquibase cung cấp các lệnh tạo SQL dự kiến tương ứng:

```bash
# Theo tag
liquibase --defaults-file=liquibase.properties rollback-sql --tag=release-1

# Theo số changeset
liquibase --defaults-file=liquibase.properties rollback-count-sql --count=2

# Theo thời điểm
liquibase --defaults-file=liquibase.properties rollback-to-date-sql --date="2026-11-19 09:00:00"
```

Khi đọc SQL preview, cần kiểm tra:

1. **Phạm vi:** những `id`, `author`, `filename` nào thực sự sẽ rollback? Có thay đổi của nhóm khác bị kéo theo không?
2. **Thứ tự:** liệu việc gỡ khóa ngoại, index, cột và bảng có đúng quan hệ phụ thuộc?
3. **Schema:** các lệnh tác động đúng schema, bảng và tên đối tượng hay không?
4. **Dữ liệu:** có `DROP TABLE`, `DROP COLUMN`, `DELETE` hoặc `UPDATE` có thể xóa/ghi đè dữ liệu không?
5. **Điều kiện:** câu SQL rollback có `WHERE` đủ chặt, xử lý giá trị `NULL` và khóa ghép đúng không?
6. **Khả năng DBMS:** câu lệnh có dùng cú pháp riêng, transaction và quyền phù hợp?
7. **Thời gian và khóa:** bảng lớn, index lớn, foreign key hay trigger có thể làm thời gian hoàn tác dài bao nhiêu?
8. **Tài liệu:** có approval, backup, người chịu trách nhiệm và phương án dừng/forward-fix nếu rollback một phần thất bại không?

**Preview không thay thế thử nghiệm.** Một số thao tác rollback có thể được Liquibase dựng SQL dựa trên metadata, trong khi trạng thái database thực tế, dữ liệu phát sinh hoặc hành vi transaction khiến lúc chạy vẫn thất bại. Nếu preview không thể dựng vì một change type không có cách rollback, dừng để thiết kế giải pháp; không nên “thử chạy thật” chỉ để xem điều gì xảy ra.

## 9. Change type nào có thể rollback, và dữ liệu có được bảo toàn?

Hỗ trợ **auto rollback** phụ thuộc change type, DBMS và phiên bản Liquibase. Việc YAML chứa một change type không tự chứng minh rằng rollback được tạo tự động; nhiều thay đổi phá hủy dữ liệu không thể đảo ngược bằng SQL tổng quát.

| Thay đổi khi update | Khả năng rollback | Rủi ro cần đánh giá |
|---|---|---|
| `createTable` | Thường có thể đảo bằng `dropTable` | Mất mọi dữ liệu mới sinh trong bảng |
| `addColumn` | Có thể đảo bằng `dropColumn` khi DBMS hỗ trợ | Mất dữ liệu đã ghi vào cột mới |
| `createIndex` | Có thể đảo bằng `dropIndex` | Tác động hiệu năng, khóa và phụ thuộc |
| `addForeignKeyConstraint` | Có thể đảo bằng `dropForeignKeyConstraint` | Gỡ bảo vệ quan hệ, khác biệt DBMS |
| `dropTable` | Không thể tự dựng lại dữ liệu đã xóa | Cần backup/snapshot hoặc chiến lược phục hồi riêng |
| `dropColumn` | Không thể tự lấy lại giá trị cột đã mất | Cần snapshot hoặc migration bù có nguồn dữ liệu |
| `update` thay đổi hàng hiện có | Cần biết giá trị cũ để khôi phục chính xác | Dữ liệu sau deploy có thể tiếp tục biến động |
| `delete` | Không thể suy ra các hàng đã bị xóa nếu không lưu | Cần snapshot/bảng lưu giá trị cũ |
| `sql` hoặc `sqlFile` | Cần chỉ rõ rollback thích hợp nếu không có suy luận được hỗ trợ | SQL tùy ý có thể không đảo ngược được |

### 9.1. Rollback tường minh trong YAML

Ví dụ thêm một cột và khai báo thao tác đảo ngược:

```yaml
databaseChangeLog:
  - changeSet:
      id: "010-add-internal-note"
      author: "db-team"
      changes:
        - addColumn:
            tableName: demo_product
            columns:
              - column:
                  name: internal_note
                  type: VARCHAR(255)
      rollback:
        - dropColumn:
            tableName: demo_product
            columnName: internal_note
```

Rollback trên **hình thức schema** trông đối xứng, nhưng thông tin được người dùng nhập vào `internal_note` sau khi deploy sẽ mất nếu drop cột. Với production, có thể chọn phương án **forward-fix** hoặc giữ cột cho đến khi toàn bộ ứng dụng không còn dùng nó, thay vì rollback ngay.

### 9.2. SQL DML không thể tự khôi phục giá trị cũ

Giả sử changeset cập nhật phí dịch vụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: "011-adjust-service-fee"
      author: "db-team"
      changes:
        - update:
            tableName: service_plan
            columns:
              - column:
                  name: fee_amount
                  valueNumeric: 125000
            where: "plan_code = 'BASIC'"
```

Đây là ví dụ phần update; **không có rollback tường minh**. Nếu `fee_amount` trước đó khác nhau giữa các hàng hoặc đã được ứng dụng cập nhật hợp lệ sau thời điểm deploy, Liquibase không thể suy ra giá trị gốc chỉ từ câu cập nhật trên. Không tự viết rollback `fee_amount = 100000` nếu không có bằng chứng giá trị trước đó đúng cho tất cả hàng.

Muốn hoàn tác có kiểm chứng, phải có snapshot phù hợp, hoặc thiết kế changeset bù theo quy tắc nghiệp vụ sau khi xem xét trạng thái mới nhất. **Bảo toàn dữ liệu quan trọng hơn việc làm một lệnh rollback báo “thành công”.**

## 10. Rollback không giống undo giao dịch và cũng không giống restore backup

Ba cơ chế này giải quyết các phạm vi khác nhau:

| Cơ chế | Đối tượng tác động | Ví dụ |
|---|---|---|
| **Transaction rollback của DBMS** | Hủy những thay đổi chưa commit trong một transaction khi DBMS hỗ trợ | Câu SQL trong transaction lỗi và database trả về trạng thái trước transaction |
| **Liquibase rollback** | Chạy SQL/chức năng hoàn tác của các changeset **đã triển khai** | Gỡ index và cột từ release vừa chạy |
| **Restore backup/PITR** | Khôi phục database từ snapshot/transaction log ở mức cơ sở dữ liệu | Khôi phục dữ liệu đã bị `DROP TABLE` hoặc `DELETE` không có snapshot trong changelog |

Không phải mọi DDL đều transactional trên mọi DBMS. Một lệnh Liquibase rollback gồm nhiều changeset có thể gặp lỗi ở giữa; tùy DBMS và cấu hình transaction, một số thao tác trước đó có thể đã được commit. Nếu điều này xảy ra, phải xem trạng thái schema, dữ liệu và `DATABASECHANGELOG` trước khi chạy lại, chứ không đoán rằng toàn bộ rollback đã tự được hủy.

### 10.1. Quy trình chuẩn bị dữ liệu an toàn

Trước một rollback có nguy cơ mất dữ liệu:

- Xác định có bảng/cột nào chứa dữ liệu mới cần giữ không.
- Chụp backup/snapshot theo chính sách công ty và thử khả năng phục hồi.
- Kiểm tra foreign key, trigger, materialized view, index và ứng dụng phụ thuộc.
- Kiểm tra bản ứng dụng sẽ chạy sau rollback có tương thích schema đã rollback không.
- Xác nhận cửa sổ thay đổi, quyền, thời gian khóa và người phê duyệt.
- Có kế hoạch forward-fix nếu rollback không thể thực hiện an toàn.

Không đưa bản sao dữ liệu nhạy cảm sang môi trường thử nghiệm mà chưa qua cơ chế bảo vệ/phân quyền. Khi thực hành, ưu tiên dữ liệu giả hoặc bản sao đã được ẩn danh.

## 11. Context, label, precondition và lịch sử khi rollback

Trong hệ thống dùng một changelog cho nhiều môi trường, các changeset có thể gắn `contextFilter`, `labels` hoặc `dbms`. Bộ lọc của lần `update` quyết định những changeset nào được chọn chạy; vì thế mỗi database sẽ có **lịch sử thực thi thực tế khác nhau**.

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: "020-load-demo-product"
      author: "db-team"
      contextFilter: "@demo-data"
      changes:
        - insert:
            tableName: demo_product
            columns:
              - column:
                  name: id
                  valueNumeric: 900020
              - column:
                  name: sku
                  value: "DEMO-020"
      rollback:
        - delete:
            tableName: demo_product
            where: "id = 900020 AND sku = 'DEMO-020'"
```

Nếu `020` không được chọn khi cập nhật production, nó sẽ không có trong lịch sử execution ở production. Không thể xác định số changeset cần rollback bằng cách **đếm phần tử trong YAML**, bởi danh sách thực thi còn phụ thuộc context, label, DBMS, precondition và những changeset đã chạy trước đó.

Khi chuẩn bị rollback:

1. Xem chính xác `DATABASECHANGELOG` của database mục tiêu.
2. Xem output của lệnh preview với đúng cấu hình phiên bản, context/label và database.
3. Kiểm tra có changeset nào được ghi `MARK_RAN` hoặc có hành vi `runAlways`/`runOnChange` cần đánh giá riêng.
4. Chú ý việc đổi context không tự hoàn tác những thay đổi đã triển khai.
5. Không xem tên context như `prod` là bằng chứng URL/JDBC thực sự trỏ tới production.

Precondition có vai trò kiểm tra điều kiện trước khi thực thi một số changeset, nhưng **không phải bảo đảm rollback sẽ đảo ngược mọi thay đổi trong ứng dụng**. Khi cần điều kiện riêng cho rollback, xem hỗ trợ phù hợp trong phiên bản Liquibase và thiết kế test để xác nhận hành vi; đừng mặc định precondition khi update luôn đủ để bảo vệ thao tác hoàn tác.

## 12. Rollback trong Spring Boot và CI/CD

Một ứng dụng Spring Boot có thể chạy migration lúc khởi động:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/master.yaml
```

Khi cần rollback production, một cách quản lý phổ biến là dùng **job điều phối Liquibase CLI riêng** với đúng artifact và kết nối database đích, đồng thời kiểm soát quá trình khởi động ứng dụng.

Vì sao? Sau khi rollback `003` và `004`, nếu ứng dụng tiếp theo vẫn chạy với changelog chứa `003`/`004` và tự động gọi `update` lúc startup, Liquibase có thể **áp dụng lại những changeset vừa rollback**. Điều đó khiến rollback không đạt mục tiêu dù lệnh ban đầu thành công.

Một quy trình CI/CD tham khảo:

```text
Sự cố phát hành hoặc yêu cầu quay về mốc
              |
              v
Xác nhận DB đích, artifact và lịch sử DATABASECHANGELOG
              |
              v
Chọn tag / count / date theo phạm vi mong muốn
              |
              v
Preview rollback SQL, review tác động dữ liệu/khóa
              |
              v
Backup, approval, chọn phiên bản ứng dụng tương thích
              |
              v
Chặn migration cạnh tranh, chạy rollback có giám sát
              |
              v
Kiểm tra schema, dữ liệu, lịch sử; giữ ứng dụng ở phiên bản phù hợp
```

Các bảo vệ nên có trong pipeline:

- Job rollback phải là bước **được kích hoạt và phê duyệt có chủ đích**, không tự động thử rollback ngay sau một lỗi không xác định.
- Cấu hình phải chỉ rõ JDBC URL, default schema, credential, changelog, version Liquibase/extension và tham số tag/count/date.
- Dùng cùng cấu hình/artifact để preview và thực thi, không preview staging rồi chạy production với changeset khác.
- Phải kiểm tra database hiện có và khóa triển khai; tránh một job `update` chạy xen giữa preview và rollback.
- Lưu SQL preview, thông tin người phê duyệt, log và trạng thái sau rollback, nhưng không lộ secret.
- Kiểm tra ứng dụng sau rollback có tương thích schema mới và dữ liệu còn lại.

Một chiến lược an toàn hơn khi không thể khôi phục dữ liệu là **roll forward**: phát hành changeset mới và bản ứng dụng sửa lỗi thay vì gỡ hàng loạt schema. Quyết định cần dựa vào nguyên nhân sự cố và rủi ro thực tế, không mặc định rollback luôn tốt hơn forward-fix.

## 13. Kiểm tra kết quả sau rollback

Sau khi chạy, đừng chỉ nhìn thông báo CLI “success”. Cần xác minh:

1. **Schema**: những cột/index đã chọn có thực sự bị gỡ không; các bảng/cột cần giữ vẫn còn không?
2. **Dữ liệu**: có mất dữ liệu hợp lệ, mất ràng buộc tham chiếu hoặc xuất hiện dữ liệu không nhất quán không?
3. **Lịch sử**: `DATABASECHANGELOG` không còn ghi những changeset đã hoàn tác theo cơ chế bình thường; những changeset cần giữ vẫn còn.
4. **Ứng dụng**: phiên bản ứng dụng hiện tại có thể đọc/ghi trên schema sau rollback không?
5. **Pipeline**: các job tự chạy migration đã được kiểm soát để không cập nhật lại ngoài dự kiến chưa?
6. **Quan sát hệ thống**: lỗi kết nối, lỗi SQL, transaction, replication và độ trễ ứng dụng có ổn định không?

Ví dụ truy vấn lịch sử:

```sql
SELECT id, author, filename, tag, exectype, orderexecuted, dateexecuted
FROM databasechangelog
ORDER BY orderexecuted;
```

Ví dụ kiểm tra các cột còn lại trong PostgreSQL với schema `public`:

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'demo_product'
ORDER BY ordinal_position;
```

Ví dụ kiểm tra index:

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'demo_product';
```

Nếu vừa rollback hai changeset `004` và `003`, bảng `demo_product` vẫn tồn tại và cột `category` còn đó; cột `published` và index `idx_demo_product_category` không còn. Đây là kết quả **mong đợi trên bài tập**, chỉ khẳng định kết quả thực tế sau khi truy vấn và đối chiếu database.

## 14. Sự cố thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy tag | Chưa tag database này, sai tên tag hoặc tag nằm ở nơi khác | Kiểm tra `TAG` trong `DATABASECHANGELOG` và URL/schema đích |
| Rollback-count gỡ nhiều/ít hơn dự kiến | Đếm file/SQL thay vì changeset; có migration mới xen vào | Xem lịch sử và preview, xác nhận chính xác các changeset cuối |
| Rollback-to-date chọn sai mốc | Sai timezone, precision hoặc lấy thời điểm từ hệ thống khác | So sánh `DATEEXECUTED` và SQL preview với cùng database |
| Preview không tạo được SQL rollback | Change type thiếu khả năng đảo ngược hoặc cần rollback tường minh | Thiết kế phương án bù/restore an toàn, thử trên bản sao |
| Rollback lỗi do foreign key/index | Quan hệ phụ thuộc hoặc thứ tự DDL không phù hợp | Kiểm tra metadata DBMS và kế hoạch tháo phụ thuộc |
| Một phần thay đổi đã rollback rồi lệnh lỗi | DDL không transactional hoặc trạng thái transaction đã thay đổi | Dừng, kiểm tra schema/dữ liệu/lịch sử, không chạy lại mù quáng |
| Mất dữ liệu sau `dropTable`/`dropColumn` | Rollback chỉ khôi phục hình dạng schema, không có snapshot dữ liệu | Phục hồi từ backup hoặc thực hiện forward-fix có kiểm soát |
| Changeset tự chạy lại sau rollback | `update` hoặc Spring Boot chạy với changelog cũ | Kiểm soát job/application version và kế hoạch phát hành |
| Checksum lỗi khi chuẩn bị rollback | Changeset đã chạy bị chỉnh nội dung hoặc đường dẫn thay đổi | Đối chiếu bản đã release, `MD5SUM` và `FILENAME` |
| Rollback trên staging ổn nhưng production lỗi | Khác dữ liệu, DBMS, quyền hoặc cấu hình | Thử trên bản sao production và kiểm soát quyền/DBMS |
| Lệnh SQL preview không khớp SQL thực tế | Khác version/config, DB state thay đổi giữa preview và chạy | Dùng cùng artifact và trạng thái; đóng băng migration cạnh tranh |
| Tag mới gắn ở cuối lịch sử nên rollback “không làm gì” | Mốc đánh dấu sai vị trí | Kiểm tra mốc tag, không nhầm tag hiện tại với release trước |

## 15. Bài thực hành: đối chiếu tag, count và thời điểm

Thực hiện trên database riêng có thể xóa và tạo lại, với changelog bốn changeset ở mục 3.

### Vòng A — Theo tag

1. Chạy `validate` rồi `update-count --count=2` để tạo bảng và cột `category`.
2. Gắn tag `release-1` và truy vấn `DATABASECHANGELOG` để chắc chắn tag thuộc mốc sau `002`.
3. Chạy `update` để áp dụng `003` và `004`.
4. Ghi lại danh sách changeset cùng schema thực tế.
5. Chạy `rollback-sql --tag=release-1`; xác nhận SQL chỉ gỡ `004` và `003`.
6. Chạy `rollback --tag=release-1`; xác nhận `published` và index biến mất, `category` và bảng còn nguyên.

### Vòng B — Theo số lượng

1. **Tạo lại** database luyện tập rồi áp dụng đủ bốn changeset.
2. Chạy `rollback-count-sql --count=1`; nhận diện chính xác `004`.
3. Chạy `rollback-count-sql --count=2`; nhận diện `004` và `003`.
4. Chỉ khi đã hiểu phạm vi, chạy `rollback-count --count=2`.
5. Kiểm tra `DATABASECHANGELOG` và schema, so sánh với kết quả vòng A.

### Vòng C — Theo thời điểm

1. Tạo lại database luyện tập, áp dụng `001` và `002`.
2. Ghi nhận `DATEEXECUTED` của hai changeset đầu.
3. Đảm bảo có một khoảng thời gian đủ rõ trước khi áp dụng `003` và `004`; ghi lại các timestamp thực tế của chúng.
4. Chọn cutoff **nằm giữa** hai nhóm timestamp, không dùng lại mốc minh họa trong bài.
5. Chạy `rollback-to-date-sql` với cutoff đó, đối chiếu tập `003`/`004`.
6. Thực hiện `rollback-to-date` chỉ trên database thực hành, kiểm tra kết quả và lý giải khác biệt nếu timestamp sát nhau.

### Vòng D — Kiểm chứng rủi ro dữ liệu

1. Sau khi có `004`, chèn một hàng giả vào `demo_product` với giá trị `published`.
2. Preview rollback `004` và nhận ra `dropColumn(published)` sẽ làm mất trường vừa nhập.
3. Trình bày phương án an toàn hơn: backup/snapshot hoặc forward-fix tùy mục tiêu, thay vì giả định rollback giữ nguyên dữ liệu.
4. Thử lệnh rollback trên database có thể tạo lại, rồi kiểm chứng phần dữ liệu thực sự còn lại.
5. Mô tả điều gì xảy ra nếu ứng dụng Spring Boot tự `update` trở lại ngay sau khi rollback.

## 16. Checklist quyết định rollback trước production

- [ ] Đã xác minh **đúng database, schema, tài khoản, changelog và phiên bản Liquibase**.
- [ ] Đã đọc `DATABASECHANGELOG` để biết changeset nào thật sự đã chạy.
- [ ] Mục tiêu rollback được phát biểu rõ: **tag**, **count** hay **date**, không nhầm sang commit Git hoặc bản backup.
- [ ] Với tag: mốc tồn tại và được gắn ở đúng ranh giới release.
- [ ] Với count: đã đếm changeset thực tế, không phải câu SQL, file hoặc số lần deploy.
- [ ] Với date: cutoff được đối chiếu `DATEEXECUTED`, timezone và độ chính xác timestamp.
- [ ] Đã chạy lệnh `*-sql` tương ứng và review đầy đủ SQL đảo ngược.
- [ ] Đã xác nhận khả năng rollback của từng change type và đánh giá các bước mất dữ liệu.
- [ ] Đã kiểm tra foreign key, index, transaction/DDL, quyền và thời gian khóa dự kiến.
- [ ] Backup, snapshot hoặc phương án forward-fix đã sẵn sàng và được diễn tập phù hợp.
- [ ] Đã thử rollback trên database có dữ liệu và lịch sử gần production.
- [ ] Đã kiểm soát job update và tự migration của Spring Boot để tránh tái áp dụng thay đổi.
- [ ] Kế hoạch version ứng dụng tương thích schema sau rollback đã được xác nhận.
- [ ] Có approval, người chịu trách nhiệm, log và tiêu chí kiểm tra hậu triển khai.
- [ ] Không sửa thủ công `DATABASECHANGELOG`/checksum để che lỗi hoặc ép chạy lại.

**Kết luận:** hoàn tác theo **tag** phù hợp với mốc phát hành, theo **count** phù hợp khi muốn gỡ một số changeset cuối đã xác định chính xác, còn theo **date** phù hợp khi có ranh giới thời gian rõ và đã kiểm tra múi giờ. Dù chọn cách nào, Liquibase rollback vẫn là **một migration ngược có tác động thật**: cần preview, đánh giá mất dữ liệu, bảo toàn lịch sử `DATABASECHANGELOG` và kiểm chứng trên database tương đương. Phối hợp chặt chẽ với changelog, checksum, precondition, Spring Boot và CI/CD là cách sử dụng rollback có trách nhiệm trong `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`.
