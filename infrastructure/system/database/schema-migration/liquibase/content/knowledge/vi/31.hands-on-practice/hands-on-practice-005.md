# Triển khai đổi cấu trúc bằng expand-contract

Đổi cấu trúc database trong một hệ thống đang phục vụ người dùng là một quá trình phối hợp giữa schema, dữ liệu và phiên bản ứng dụng. Một thao tác tưởng như đơn giản như đổi tên cột, tách bảng, đổi kiểu dữ liệu hoặc thêm ràng buộc có thể làm hỏng các replica vẫn chạy mã cũ trong lúc rolling deployment chưa hoàn tất.

Chiến lược **expand-contract** chia một thay đổi không tương thích thành nhiều bước nhỏ, mỗi bước vẫn giữ database hoạt động với các phiên bản ứng dụng đang tồn tại. Trước tiên, mở rộng schema để hỗ trợ cả cấu trúc cũ và mới; sau đó triển khai ứng dụng tương thích, chuyển đổi dữ liệu và chuyển dần cách đọc/ghi; cuối cùng mới loại bỏ cấu trúc cũ khi không còn consumer sử dụng.

Với Liquibase, mỗi giai đoạn được ghi thành changeset mới, bất biến sau khi đã triển khai và có thể kiểm tra độc lập. Việc chia giai đoạn giúp giảm rủi ro khi nhiều replica ứng dụng cùng chạy, tạo cơ hội rollback ứng dụng và cho phép xác minh dữ liệu trước thao tác phá hủy.

Bài thuộc chương **Thực hành** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này thực hành đổi tên cột theo expand-contract, từ thiết kế compatibility matrix, tạo changeset, dual-write, backfill theo batch, xác minh invariant đến contract và phục hồi.

## 1. Bài toán thực hành: đổi tên cột đang được nhiều phiên bản sử dụng

Giả sử bảng customer có cột full_name. Nhiều phiên bản ứng dụng đang đọc và ghi cột này. Một release mới muốn dùng display_name vì tên mới phản ánh đúng ý nghĩa nghiệp vụ.

Cách đổi trực tiếp:

~~~sql
ALTER TABLE customer RENAME COLUMN full_name TO display_name;
~~~

có thể làm các replica cũ lỗi ngay lập tức vì chúng vẫn truy vấn full_name. Nếu rolling deployment chỉ thay một vài replica mỗi lần, trong một khoảng thời gian cả mã cũ và mới cùng truy cập database.

Ta sẽ dùng các giai đoạn:

1. Expand: thêm display_name, giữ full_name.
2. Compatibility release: ứng dụng ghi cả hai cột, vẫn đọc full_name.
3. Backfill: sao chép dữ liệu cũ sang display_name.
4. Switch read: ứng dụng đọc display_name, vẫn dual-write.
5. Relax old constraint: bỏ ràng buộc NOT NULL trên full_name nếu phiên bản mới sắp ngừng ghi cột này.
6. New-only release: ứng dụng chỉ ghi/đọc display_name.
7. Contract: xóa full_name sau khi không còn consumer và rollback window đã kết thúc.

Không nhất thiết mọi dự án cần đúng bảy giai đoạn. Số bước phụ thuộc khả năng tương thích ứng dụng, quy mô dữ liệu, DBMS và thời gian cần giữ khả năng rollback.

## 2. Hiểu các trạng thái ứng dụng trong quá trình chuyển đổi

Gọi các phiên bản:

- **V1:** chỉ đọc/ghi full_name.
- **V2:** đọc full_name, ghi cả full_name và display_name.
- **V3:** đọc display_name, ghi cả hai cột.
- **V4:** chỉ đọc/ghi display_name.

Bảng tương thích:

| Schema | V1 | V2 | V3 | V4 |
|---|---|---|---|---|
| Chỉ có full_name | Có | Không | Không | Không |
| Có cả hai, display_name nullable | Có | Có | Có | Có |
| Có cả hai, display_name đã đủ dữ liệu và NOT NULL | Không nếu không có default/trigger tương thích | Có | Có | Có |
| full_name đã cho phép NULL | Có thể | Có | Có | Có |
| Đã xóa full_name | Không | Không | Không | Có |

Ký hiệu “có thể” cần được kiểm tra theo cách ứng dụng truy cập cột. V1 có thể vẫn hoạt động sau khi thêm cột mới và thêm constraint mới nếu cột cũ không đổi. Nhưng khi xóa full_name, V1/V2/V3 có truy cập cột cũ sẽ không còn tương thích.

**Không thực hiện contract khi còn phiên bản ứng dụng hoặc worker phụ thuộc cấu trúc cũ.** Hãy tính cả scheduled job, message consumer, batch ETL, báo cáo, script quản trị và các service khác.

## 3. Quy tắc an toàn trước khi bắt đầu

Trước khi tạo changeset, xác định:

- Tên database, schema và DBMS thực tế.
- Bảng/cột được thay đổi và tất cả consumer.
- Phiên bản ứng dụng đang chạy và các phiên bản có thể rollback.
- Số lượng dòng, kích thước bảng và tốc độ ghi.
- Primary key dùng để chia batch.
- Index hỗ trợ truy vấn backfill.
- Constraint và foreign key liên quan.
- Khả năng transactional DDL của DBMS.
- Thời gian lock/downtime cho phép.
- Cách quan sát và xác minh dữ liệu sau mỗi giai đoạn.

Giữ một artifact changelog bất biến cho mỗi release. Không sửa changeset đã chạy để điều chỉnh migration; hãy thêm changeset mới. Dùng Liquibase history và checksum để truy vết từng bước.

Nếu bảng lớn, không đưa một UPDATE hàng triệu dòng vào một changeset chạy trong một transaction dài mà chưa đánh giá. Backfill có thể là một job riêng có khả năng resume, còn Liquibase quản lý schema và các mốc thay đổi.

## 4. Giai đoạn 1 — Expand schema

Thêm cột mới ở trạng thái nullable. Không xóa hoặc đổi tên cột cũ.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 100-expand-customer-display-name
      author: database-team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: display_name
                  type: VARCHAR(200)
                  constraints:
                    nullable: true
~~~

Changelog master include file này:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/100-expand-customer-display-name.yaml
      relativeToChangelogFile: true
~~~

Tên file chỉ là ví dụ. Cần đặt theo cấu trúc changelog của dự án.

Sau khi chạy migration:

- full_name vẫn tồn tại.
- display_name đã tồn tại và cho phép NULL.
- Replica V1 vẫn truy vấn được cột cũ.
- Chưa có dữ liệu nào bị xóa.
- Rollback ứng dụng về V1 vẫn khả thi.

Không thêm NOT NULL ngay khi tạo cột mới nếu các replica cũ chưa ghi cột đó. Insert từ V1 sẽ không cung cấp display_name và có thể thất bại.

### 4.1. Chọn kiểu dữ liệu và default

Kiểu display_name phải tương thích với dữ liệu cũ và yêu cầu nghiệp vụ. Đừng chọn VARCHAR(100) nếu full_name có thể dài 180 ký tự. Kiểm tra collation, Unicode, index và giới hạn DBMS.

Tránh thêm default nặng trên bảng lớn mà chưa hiểu hành vi DBMS/version. Một số engine có thể tối ưu default hằng số, một số thao tác có thể rewrite bảng hoặc tạo lock đáng kể. Đo trên phiên bản DBMS production.

## 5. Giai đoạn 2 — Triển khai phiên bản tương thích dual-write

V2 tiếp tục đọc full_name nhưng khi tạo/cập nhật customer sẽ ghi cả hai cột:

~~~java
public void updateCustomerName(long id, String name) {
    jdbcTemplate.update(
        """
        UPDATE customer
        SET full_name = ?, display_name = ?
        WHERE id = ?
        """,
        name, name, id
    );
}
~~~

Đây là ví dụ minh họa cho SQL/JDBC. Với JPA, ORM hoặc repository layer, bảo đảm cả hai thuộc tính được ghi trong cùng transaction phù hợp.

Trong rolling deployment có thể đồng thời tồn tại V1 và V2:

- V1 chỉ ghi full_name.
- V2 ghi cả full_name và display_name.
- Cả hai vẫn đọc full_name.

Trong giai đoạn này display_name có thể chưa đầy đủ vì V1 vẫn tạo/cập nhật dòng mà không ghi cột mới. Điều đó chấp nhận được tạm thời vì chưa chuyển read path sang cột mới.

Sau khi mọi V1 đã được thay thế, xác minh không còn writer cũ. Đừng chỉ kiểm tra số pod của deployment chính; hãy kiểm tra worker, consumer và job nền.

## 6. Xác minh không còn writer cũ

Trước backfill cuối cùng, phải chứng minh mọi tiến trình ghi customer đều hỗ trợ dual-write.

Nguồn bằng chứng có thể gồm:

- Tất cả replica của service đã chạy image V2 trở lên.
- Không còn pod cũ trong terminating hoặc rollout history có thể nhận traffic.
- Worker/batch job đã được nâng cấp.
- Consumer queue đã chuyển sang phiên bản tương thích.
- Không có script hoặc service khác chỉ ghi full_name.
- Log/version telemetry cho thấy không còn writer V1 trong khoảng quan sát đã chọn.

Nếu còn một writer cũ, backfill có thể chạy xong nhưng dữ liệu display_name lại bị thiếu hoặc stale sau đó. Trong trường hợp không thể kiểm soát toàn bộ writer, cần một cơ chế đồng bộ tạm thời khác, ví dụ trigger DBMS đã được review, nhưng không thêm trigger chỉ để né việc xác định ownership.

## 7. Giai đoạn 3 — Backfill dữ liệu cũ sang cột mới

Khi mọi writer đã dual-write, backfill các dòng còn thiếu:

~~~sql
UPDATE customer
SET display_name = full_name
WHERE display_name IS NULL
  AND full_name IS NOT NULL;
~~~

Với bảng nhỏ, câu lệnh trên có thể phù hợp sau khi đo và thử trên database tương đương. Với bảng lớn, hãy chia thành batch theo primary key để giới hạn transaction và lock.

Ví dụ một batch PostgreSQL:

~~~sql
WITH batch AS (
    SELECT id
    FROM customer
    WHERE display_name IS NULL
      AND full_name IS NOT NULL
    ORDER BY id
    LIMIT 5000
)
UPDATE customer c
SET display_name = c.full_name
FROM batch b
WHERE c.id = b.id;
~~~

Đây là một batch, không phải vòng lặp hoàn chỉnh. Worker backfill cần lặp lại theo cách có kiểm soát cho tới khi không còn dòng phù hợp, ghi nhận tiến độ và có thể resume. Cú pháp batch cần điều chỉnh theo DBMS.

### 7.1. Điều kiện an toàn cho backfill

- Chỉ cập nhật dòng chưa có display_name nếu đây là quy tắc đã thống nhất.
- Không ghi đè giá trị display_name mới do ứng dụng đã cập nhật.
- Có primary key ổn định để phân trang.
- Batch size được chọn dựa trên tải, lock và replication lag.
- Có checkpoint hoặc cursor để tiếp tục sau lỗi.
- Có giới hạn thời gian và cơ chế dừng.
- Theo dõi số dòng cập nhật, thời gian mỗi batch và lỗi.
- Xác minh dữ liệu trong lúc và sau khi chạy.

Không dùng OFFSET tăng dần trên bảng thay đổi liên tục nếu nó có thể bỏ qua hoặc lặp dòng. Keyset pagination theo primary key thường dễ kiểm soát hơn.

### 7.2. Cạnh tranh giữa backfill và ghi ứng dụng

V2 dual-write cả hai cột trong cùng transaction. Nếu backfill chỉ cập nhật khi display_name IS NULL, một request đã ghi display_name sẽ không bị backfill ghi đè.

Tuy nhiên, nếu ứng dụng cập nhật hai cột không nguyên tử hoặc có writer ngoài V2, có thể xuất hiện chênh lệch. Hãy xác định nguồn dữ liệu chuẩn trong giai đoạn này và bảo đảm mọi writer tuân thủ cùng quy tắc.

## 8. Giai đoạn 4 — Xác minh dữ liệu trước khi chuyển read path

Không chuyển ứng dụng đọc display_name chỉ vì backfill job báo hoàn tất. Cần kiểm tra invariant:

~~~sql
SELECT COUNT(*) AS missing_new_name
FROM customer
WHERE display_name IS NULL
  AND full_name IS NOT NULL;
~~~

Kiểm tra chênh lệch:

~~~sql
SELECT COUNT(*) AS different_names
FROM customer
WHERE display_name IS DISTINCT FROM full_name;
~~~

Cú pháp IS DISTINCT FROM có hỗ trợ khác nhau giữa DBMS; với engine khác, dùng biểu thức tương đương để xử lý NULL chính xác.

Nếu nghiệp vụ cho phép full_name NULL, cần định nghĩa quy tắc cho các dòng đó. Có thể display_name cũng NULL, hoặc được tạo từ trường khác. Không áp dụng NOT NULL khi chưa giải quyết mọi trường hợp.

Ngoài số lượng, lấy mẫu và đối chiếu các trường hợp:

- Tên có dấu Unicode.
- Chuỗi dài sát giới hạn.
- Chuỗi rỗng hoặc chỉ có khoảng trắng.
- Giá trị NULL.
- Dòng được cập nhật trong lúc backfill.
- Dòng mới được tạo sau khi V2 triển khai.

Lưu kết quả xác minh cùng release và target.

## 9. Dùng precondition để bảo vệ bước chuyển đổi

Trước khi áp dụng constraint hoặc contract, có thể dùng sqlCheck để dừng nếu còn dữ liệu chưa đạt:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 120-require-customer-display-name
      author: database-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer
              WHERE display_name IS NULL
                AND full_name IS NOT NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: display_name
            columnDataType: VARCHAR(200)
~~~

Đây là ví dụ cho quy tắc dữ liệu giả định rằng mọi full_name khác NULL đều phải có display_name. Nếu bảng lớn, COUNT(*) có thể tốn kém; đánh giá execution plan và cân nhắc một kiểm tra EXISTS nếu chỉ cần biết có vi phạm hay không.

Precondition bảo vệ trạng thái tại thời điểm Liquibase đánh giá. Nếu có writer không tuân thủ quy tắc, dữ liệu có thể thay đổi ngay sau kiểm tra. Vì vậy phải phối hợp với ứng dụng và kiểm tra lại sau khi constraint được áp dụng.

Không đổi onFail thành MARK_RAN chỉ để pipeline đi tiếp. Nếu invariant chưa đạt, dừng và sửa dữ liệu.

## 10. Giai đoạn 5 — Chuyển read path sang cột mới

V3 đọc display_name nhưng vẫn dual-write cả hai cột:

~~~java
public CustomerView findCustomer(long id) {
    return jdbcTemplate.queryForObject(
        """
        SELECT id, display_name
        FROM customer
        WHERE id = ?
        """,
        (rs, rowNum) -> new CustomerView(
            rs.getLong("id"),
            rs.getString("display_name")
        ),
        id
    );
}
~~~

Trong giai đoạn rolling V2/V3:

- V2 đọc full_name và ghi cả hai.
- V3 đọc display_name và ghi cả hai.
- Hai phiên bản cùng hoạt động trên schema có cả hai cột.
- Rollback về V2 vẫn có thể hoạt động vì full_name tiếp tục được cập nhật.

Sau khi toàn bộ reader đã chuyển sang display_name và dữ liệu được xác minh, có thể lên kế hoạch ngừng phụ thuộc full_name. Nhưng chưa xóa cột ngay nếu rollback window còn yêu cầu hỗ trợ V2.

## 11. Giai đoạn 6 — Nới ràng buộc trên cột cũ

Nếu full_name đang NOT NULL, V4 chỉ ghi display_name sẽ thất bại khi insert vì full_name không được cung cấp. Trước khi triển khai new-only writer, phải nới ràng buộc cũ hoặc có một default/compatibility mechanism phù hợp.

Ví dụ Liquibase:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 130-relax-old-full-name
      author: database-team
      changes:
        - dropNotNullConstraint:
            tableName: customer
            columnName: full_name
            columnDataType: VARCHAR(200)
~~~

Đây là thay đổi schema thường có thể tương thích với V2/V3 vì các phiên bản đó vẫn ghi full_name. Kiểm tra DBMS và constraint thực tế trước khi chạy.

Không xóa cột cũ ở bước này. Chỉ bỏ yêu cầu bắt buộc để phiên bản mới có thể ngừng ghi nó trong giai đoạn tiếp theo.

## 12. Giai đoạn 7 — Triển khai ứng dụng chỉ dùng cột mới

V4 đọc và ghi display_name. Trong rolling deployment có thể cùng tồn tại V3 và V4:

- V3 đọc display_name, ghi cả full_name và display_name.
- V4 đọc/ghi display_name.
- V3 và V4 cùng hoạt động trên schema có cả hai cột, trong đó full_name đã nullable.

Sau khi V4 hoàn tất rollout:

- Xác nhận không còn V1/V2/V3 hoặc worker cũ.
- Kiểm tra telemetry không còn truy vấn full_name.
- Kiểm tra scheduled jobs, reporting, ETL và scripts.
- Xác định rollback window: nếu rollback về V3, V3 vẫn đọc display_name nên có thể hoạt động; nếu rollback về V2 đọc full_name, dữ liệu có thể stale sau khi V4 chỉ ghi cột mới.

Vì vậy, phải ghi rõ phiên bản rollback được hỗ trợ. Nếu bắt buộc rollback về V2, tiếp tục dual-write hoặc duy trì một cơ chế đồng bộ cho tới khi cửa sổ rollback đó kết thúc.

## 13. Giai đoạn 8 — Contract: loại bỏ cột cũ

Chỉ sau khi mọi consumer đã ngừng sử dụng full_name và rollback window đã kết thúc, mới tạo changeset xóa cột:

Một precondition trong database có thể xác nhận cột cũ vẫn tồn tại trước khi drop. Tuy nhiên, catalog chỉ mô tả cấu trúc database; nó không thể chứng minh không còn ứng dụng, worker hoặc script đang đọc cột. Bằng chứng không còn consumer phải được pipeline/deployment gate kiểm tra trước khi chạy contract. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 150-contract-drop-full-name
      author: database-team
      preConditions:
        - onFail: HALT
        - columnExists:
            tableName: customer
            columnName: full_name
      changes:
        - dropColumn:
            tableName: customer
            columnName: full_name
~~~

Precondition columnExists chỉ tránh lỗi nếu cột đã không tồn tại; nó không thay thế approval/gate xác nhận mọi consumer đã chuyển đổi. Không dùng MARK_RAN để che một contract không đúng trạng thái.

## 14. Vì sao không dùng renameColumn trong một bước?

Liquibase có change type renameColumn. Nó phù hợp khi database có thể được chuyển đổi trong một maintenance window, không còn phiên bản ứng dụng cũ truy cập, hoặc có một quy trình cutover được kiểm soát chặt.

Trong rolling deployment, renameColumn trực tiếp có thể khiến app cũ lỗi ngay sau khi DDL hoàn tất. Expand-contract giữ cả hai cột trong thời gian chuyển đổi, cho phép nhiều phiên bản ứng dụng cùng hoạt động.

Không phải lúc nào cũng cần expand-contract. Với bảng nội bộ chưa có consumer, môi trường offline hoặc thay đổi có downtime được phê duyệt, một changeset rename trực tiếp có thể đơn giản và phù hợp hơn. Quyết định dựa trên khả năng tương thích và yêu cầu availability.

## 15. Quản lý changeset và checksum qua các release

Mỗi giai đoạn cần một changeset mới:

| Giai đoạn | Changeset minh họa |
|---|---|
| Expand | 100-expand-customer-display-name |
| Constraint mới | 120-require-customer-display-name |
| Relax constraint cũ | 130-relax-old-full-name |
| Contract | 150-contract-drop-full-name |

Các changeset đã chạy phải được xem là bất biến. Không sửa ID, author, nội dung hoặc path đã phát hành để thay đổi cách migration cũ hoạt động. Nếu cần sửa logic, tạo changeset mới hoặc quy trình repair được review.

DATABASECHANGELOG cho biết changeset nào đã được ghi nhận ở mỗi target. Kiểm tra history trước khi rollout từng release, đặc biệt khi staging và production có thể đang ở các giai đoạn khác nhau.

Checksum mismatch là dấu hiệu cần điều tra. Không xóa history hoặc clear-checksums chỉ để làm pipeline tiếp tục.

## 16. Rollback theo giai đoạn

Rollback ứng dụng và rollback database là hai thao tác khác nhau.

| Giai đoạn | Rollback ứng dụng | Rollback schema |
|---|---|---|
| Sau expand | Về V1 thường vẫn an toàn | Có thể bỏ cột mới nếu chưa có dữ liệu/consumer phụ thuộc |
| Sau V2 dual-write | Về V1 có thể an toàn nếu full_name vẫn chuẩn | Không nên bỏ cột mới nếu V2 còn chạy |
| Sau backfill | Về V2/V1 có thể được nếu full_name còn đúng | Bỏ cột mới sẽ mất dữ liệu mới nếu không đối chiếu |
| Sau V3 read-new/dual-write | Về V2 có thể được vì cả hai cột vẫn đồng bộ | Giữ cả hai cột trong rollback window |
| Sau V4 new-only | Về V3 có thể được nếu V3 đọc display_name; về V2 có thể không an toàn | Không drop display_name; full_name có thể đã stale |
| Sau contract | Không thể rollback về phiên bản còn truy cập full_name | Cần forward-fix hoặc restore nếu thật sự cần |

Không giả định rollback Liquibase tự khôi phục dữ liệu đồng bộ hai cột. Nếu rollback xóa display_name sau khi V4 đã ghi dữ liệu mới, có thể mất thông tin. Hãy giữ schema expand đủ lâu và định nghĩa rõ phiên bản ứng dụng có thể rollback.

## 17. Kiểm thử expand-contract trên database mới và database cũ

Bộ test cần bao gồm:

**Fresh install:** chạy toàn bộ changelog từ database trống, xác minh schema cuối và history.

**Upgrade:** khởi tạo schema phiên bản trước, nạp dữ liệu legacy, rồi chạy từng giai đoạn mới.

**Mixed-version compatibility:** chạy V1/V2 hoặc V2/V3 cùng lúc trên schema expand, xác minh insert/update không làm mất dữ liệu.

**Backfill:** tạo dữ liệu có NULL, Unicode, chuỗi dài, cập nhật đồng thời và dòng mới.

**Contract gate:** chứng minh pipeline dừng nếu chưa xác nhận consumer cũ đã hết.

**Rollback:** rollback application ở từng giai đoạn; xác minh dữ liệu cần thiết vẫn còn.

Dùng Testcontainers với đúng DBMS production để kiểm tra DDL, transaction, constraint và batch. H2 có thể dùng cho test logic nhanh nhưng không thay thế test tích hợp DBMS thật.

## 18. Quan sát và vận hành từng giai đoạn

Mỗi release cần có:

- Release ID, image version và changelog artifact.
- Database target/schema.
- Changeset đã chạy và changeset pending.
- DATABASECHANGELOGLOCK state.
- Thời gian migration và thời gian backfill.
- Số dòng đã xử lý, còn lại và lỗi.
- Kết quả invariant: missing values, mismatch count.
- Số replica theo phiên bản.
- Consumer/worker còn sử dụng cột cũ.
- Trạng thái rollback window và contract approval.

Không bắt đầu contract chỉ dựa trên số replica web. Một batch job cũ chạy mỗi đêm vẫn có thể truy cập cột đã định xóa.

## 19. Bài thực hành: đổi full_name thành display_name

Thực hiện trên database lab hoặc Testcontainers. Không sử dụng production.

### Bước 1 — Tạo schema phiên bản cũ

Tạo bảng customer có id và full_name NOT NULL. Nạp dữ liệu đại diện gồm Unicode, tên dài và các trường hợp biên.

### Bước 2 — Chạy expand changeset

Thêm display_name nullable. Xác minh full_name vẫn tồn tại và V1 vẫn thực hiện được SELECT/INSERT/UPDATE theo schema cũ.

### Bước 3 — Triển khai V2 dual-write

Cập nhật code để ghi cả hai cột, nhưng vẫn đọc full_name. Chạy test đồng thời V1/V2 và quan sát sự khác biệt dữ liệu.

### Bước 4 — Dừng V1 và backfill

Xác nhận không còn writer V1. Chạy backfill theo batch cho các dòng display_name còn NULL. Ghi checkpoint và số dòng cập nhật.

### Bước 5 — Xác minh invariant

Kiểm tra missing count, mismatch count, giá trị NULL hợp lệ và các trường hợp Unicode/độ dài. Chạy precondition trước khi thêm NOT NULL cho display_name nếu nghiệp vụ yêu cầu.

### Bước 6 — Triển khai V3 read-new/dual-write

Chuyển read path sang display_name nhưng vẫn ghi cả hai cột. Rollout từng replica và xác minh V2/V3 cùng hoạt động.

### Bước 7 — Relax cột cũ

Dùng changeset dropNotNullConstraint cho full_name nếu V4 sẽ không ghi cột này. Kiểm tra insert mới từ V4 trên database lab.

### Bước 8 — Triển khai V4 new-only

Chuyển ứng dụng chỉ đọc/ghi display_name. Theo dõi mọi truy vấn còn tham chiếu full_name. Thử rollback về V3 và xác minh hoạt động.

### Bước 9 — Mô phỏng contract gate

Giữ một worker lab vẫn đọc full_name. Xác nhận pipeline contract bị chặn. Sau khi dừng worker và hết rollback window, cho phép contract.

### Bước 10 — Xóa cột cũ

Chạy changeset dropColumn trên database lab. Xác minh schema, dữ liệu display_name và DATABASECHANGELOG. Thử fresh install và upgrade từ release cũ.

### Bước 11 — Ghi báo cáo

Ghi release, changeset, phiên bản ứng dụng, số replica, backfill count, invariant result, rollback test và bằng chứng không còn consumer cũ.

Điều kiện hoàn thành: người học giải thích được từng giai đoạn, chứng minh các phiên bản cùng tồn tại an toàn, backfill không ghi đè dữ liệu mới, rollback application còn khả thi trong cửa sổ đã định và contract chỉ chạy sau khi consumer cũ đã được loại bỏ.

## 20. Checklist trước khi chạy expand-contract

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Đã xác định toàn bộ consumer của cấu trúc cũ? | Danh sách service, worker, batch, report |
| Có compatibility matrix cho từng phiên bản? | Test V1/V2/V3/V4 theo schema |
| Expand có giữ cấu trúc cũ? | Changeset chỉ thêm cấu trúc mới |
| Cột mới có nullable/default phù hợp? | Review DDL theo DBMS |
| Dual-write có nguyên tử? | Transaction và integration test |
| Đã dừng mọi writer cũ trước backfill cuối? | Replica/worker telemetry |
| Backfill có batch và resume? | Checkpoint, batch size, timeout |
| Backfill tránh ghi đè giá trị mới? | Predicate và concurrency test |
| Có invariant để xác minh dữ liệu? | Missing/mismatch/null assertions |
| Precondition có chi phí phù hợp? | Execution plan và benchmark |
| Read path chỉ chuyển sau khi dữ liệu đạt? | Gate và post-check |
| Old constraint đã được nới trước new-only write? | Changeset riêng và test insert |
| Rollback window và version hỗ trợ được ghi rõ? | Release policy |
| Không còn consumer cũ trước contract? | Telemetry, search usage, owner approval |
| Contract là changeset mới, bất biến? | Liquibase history/checksum |
| Rollback/restore/forward-fix đã được thử? | Kết quả lab/backup test |
| Fresh install và upgrade đều đạt? | Testcontainers hoặc DBMS test thật |

**Nguyên tắc cuối cùng:** expand-contract biến một thay đổi phá vỡ tương thích thành chuỗi bước có thể kiểm chứng. Hãy mở rộng schema trước, triển khai ứng dụng dual-write, loại bỏ writer cũ, backfill và xác minh dữ liệu, chuyển read path, nới constraint cũ trước khi ngừng ghi cột cũ, rồi chỉ contract sau khi mọi consumer và rollback window đã kết thúc. Liquibase ghi nhận từng bước bằng changeset mới; pipeline chịu trách nhiệm kiểm tra phiên bản ứng dụng, dữ liệu và consumer trước khi cho phép bước phá hủy. Chỉ xóa cấu trúc cũ khi đã có bằng chứng rõ ràng rằng không còn thành phần nào phụ thuộc vào nó.

