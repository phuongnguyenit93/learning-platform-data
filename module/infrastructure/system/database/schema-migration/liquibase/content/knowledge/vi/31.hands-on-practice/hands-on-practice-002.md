# Thiết kế lược đồ đơn hàng qua nhiều phiên bản phát hành

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thực hành này xây dựng một lược đồ đơn hàng qua nhiều phiên bản phát hành, từ mô hình ban đầu đến khi bổ sung trạng thái, tiền tệ, lịch sử thay đổi và ràng buộc duy nhất.

Bài toán được thiết kế theo cách một nhóm phát triển có thể áp dụng vào dự án thật: mỗi release thêm một phần năng lực, changeset đã triển khai được giữ bất biến, dữ liệu cũ được chuyển đổi theo quy tắc có thể kiểm chứng và ứng dụng vẫn tương thích trong giai đoạn chuyển tiếp. Bạn sẽ thấy cách tổ chức changelog, viết YAML changeset, đặt precondition, xem SQL dự kiến, kiểm thử đường nâng cấp và xác nhận trạng thái sau mỗi release.

Ví dụ dùng PostgreSQL để minh họa các truy vấn kiểm tra dữ liệu, nhưng cấu trúc changelog chủ yếu dùng change type của Liquibase. Khi chuyển sang DBMS khác, cần xác minh kiểu dữ liệu, cú pháp SQL, hành vi khóa và khả năng hỗ trợ của phiên bản cụ thể.

## 1. Bài toán và các quyết định thiết kế

Một dịch vụ bán hàng cần quản lý khách hàng, đơn hàng và các dòng hàng trong đơn. Ứng dụng ban đầu đã chạy production. Qua các release, nghiệp vụ phát triển:

- **Release 1:** lưu khách hàng, đơn hàng và dòng hàng; đơn hàng có tổng tiền, thời điểm tạo, thời điểm thanh toán và địa chỉ giao hàng dạng văn bản.
- **Release 2:** cần trạng thái đơn hàng và mã tiền tệ để hỗ trợ quy trình xử lý và báo cáo đa tiền tệ.
- **Release 3:** cần lưu lịch sử chuyển trạng thái để truy vết ai thay đổi đơn hàng và khi nào.
- **Release 4:** yêu cầu mã đơn hàng duy nhất trên toàn bộ bảng, sau khi xử lý dữ liệu trùng từ hệ thống cũ.

Các quyết định quan trọng:

1. Mỗi release bổ sung changeset mới; không sửa changeset đã chạy ở môi trường dùng chung.
2. Mỗi changeset có ID, author và đường dẫn ổn định.
3. Tách thay đổi cấu trúc khỏi backfill dữ liệu dài.
4. Dùng precondition để dừng khi dữ liệu không đáp ứng giả định.
5. Chuyển ứng dụng theo mô hình expand–migrate–contract để hỗ trợ rolling deployment.
6. Kiểm thử cả database mới dựng từ đầu và database đã nâng cấp từ release trước.
7. Kiểm tra DATABASECHANGELOG cùng schema và dữ liệu thực tế.

### Quy ước nghiệp vụ trong bài

- Một khách hàng có thể có nhiều đơn hàng.
- Một đơn hàng có một hoặc nhiều dòng hàng.
- `orders.total_amount` là tổng tiền của đơn, được ứng dụng tính từ dòng hàng theo quy tắc làm tròn đã thống nhất.
- `paid_at` có thể NULL khi đơn chưa thanh toán.
- Trong ví dụ dữ liệu lịch sử, tất cả đơn hàng cũ được xác nhận dùng VND. Nếu hệ thống thực tế có nhiều tiền tệ, không được tự điền VND; phải lấy currency từ nguồn dữ liệu đáng tin cậy.
- Trạng thái ban đầu được suy ra từ `paid_at`: NULL thành PENDING, có thời điểm thanh toán thành PAID. Đây là quy tắc minh họa; nghiệp vụ thực tế có thể cần phân biệt CANCELLED, REFUNDED hoặc các trạng thái khác.

Nếu những giả định trên không đúng với dữ liệu thực tế, phải sửa quy tắc chuyển đổi trước khi chạy migration.

## 2. Lộ trình schema qua các release

| Release | Thay đổi schema | Thay đổi dữ liệu | Tương thích ứng dụng |
|---|---|---|---|
| **1.0** | Tạo customer, orders, order_items và khóa ngoại/index cơ bản | Khởi tạo dữ liệu ban đầu | Ứng dụng chỉ dùng các cột nền |
| **2.0-expand** | Thêm status và currency ở dạng nullable | Chưa bắt buộc backfill ngay trong cùng release | Code cũ vẫn chạy; code mới có thể ghi trường mới |
| **2.1-migrate** | Giữ cấu trúc đã mở rộng | Backfill status/currency, kiểm tra dữ liệu | Code dual-read/dual-write trong thời gian chuyển tiếp |
| **2.2-contract** | Đặt NOT NULL và default sau khi dữ liệu đạt điều kiện | Không còn giá trị thiếu | Code mới coi trường mới là bắt buộc |
| **3.0** | Thêm order_status_history và index | Ghi lịch sử chuyển trạng thái từ thời điểm bật tính năng | Code mới ghi order và history trong cùng transaction |
| **4.0** | Thêm UNIQUE cho order_no | Xử lý duplicate trước migration | Ứng dụng bảo đảm không tạo mã trùng |

Các tên release trên là mốc học tập, không phải yêu cầu phải tạo nhiều nhánh Git. Một tổ chức có thể phát hành nhiều changeset trong một release ứng dụng hoặc tách thành nhiều release nhỏ. Điều quan trọng là thứ tự triển khai và tương thích schema phải được kiểm soát.

Sơ đồ tiến hóa:

~~~text
R1.0: customer + orders + order_items
                 |
                 v
R2.0: EXPAND status + currency (nullable)
                 |
                 v
R2.1: MIGRATE dữ liệu cũ + kiểm tra
                 |
                 v
R2.2: CONTRACT NOT NULL + default
                 |
                 v
R3.0: order_status_history
                 |
                 v
R4.0: UNIQUE(order_no)
~~~

## 3. Tổ chức changelog

Dùng master changelog với các file theo release giúp reviewer nhìn thấy thứ tự migration:

~~~text
src/main/resources/db/changelog/
  db.changelog-master.yaml
  changes/
    001-create-order-core.yaml
    010-add-order-status-currency.yaml
    011-backfill-order-status-currency.yaml
    012-constrain-order-status-currency.yaml
    020-create-order-status-history.yaml
    030-unique-order-number.yaml
~~~

Master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-order-core.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/010-add-order-status-currency.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/011-backfill-order-status-currency.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/012-constrain-order-status-currency.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/020-create-order-status-history.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/030-unique-order-number.yaml
      relativeToChangelogFile: true
~~~

Dùng include tường minh để thứ tự dễ review. Nếu dùng includeAll, cần hiểu quy tắc sắp xếp file và tránh đặt file tạm trong thư mục được quét.

Đường dẫn file là một phần của định danh changeset. Sau khi migration đã được triển khai, không di chuyển file tùy tiện. Nếu bắt buộc tổ chức lại cấu trúc, cần giữ logicalFilePath phù hợp và kiểm thử với DATABASECHANGELOG hiện có.

## 4. Release 1.0: tạo cấu trúc đơn hàng ban đầu

Mục tiêu release đầu tiên là tạo ba bảng:

- `customer`: thông tin khách hàng tối thiểu.
- `orders`: thông tin tổng quan của đơn.
- `order_items`: các dòng hàng thuộc đơn.

Ví dụ changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-order-core
      author: commerce-team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_code
                  type: VARCHAR(40)
                  constraints:
                    nullable: false
              - column:
                  name: display_name
                  type: VARCHAR(160)
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  constraints:
                    nullable: false

        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: order_no
                  type: VARCHAR(40)
                  constraints:
                    nullable: false
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: total_amount
                  type: DECIMAL(18,2)
                  constraints:
                    nullable: false
              - column:
                  name: shipping_address
                  type: VARCHAR(500)
              - column:
                  name: paid_at
                  type: TIMESTAMP
              - column:
                  name: created_at
                  type: TIMESTAMP
                  constraints:
                    nullable: false

        - createTable:
            tableName: order_items
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: order_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: sku
                  type: VARCHAR(64)
                  constraints:
                    nullable: false
              - column:
                  name: quantity
                  type: INT
                  constraints:
                    nullable: false
              - column:
                  name: unit_price
                  type: DECIMAL(18,2)
                  constraints:
                    nullable: false

        - addForeignKeyConstraint:
            baseTableName: orders
            baseColumnNames: customer_id
            constraintName: fk_orders_customer
            referencedTableName: customer
            referencedColumnNames: id

        - addForeignKeyConstraint:
            baseTableName: order_items
            baseColumnNames: order_id
            constraintName: fk_order_items_order
            referencedTableName: orders
            referencedColumnNames: id

        - createIndex:
            tableName: orders
            indexName: idx_orders_customer_created
            columns:
              - column:
                  name: customer_id
              - column:
                  name: created_at

        - createIndex:
            tableName: order_items
            indexName: idx_order_items_order
            columns:
              - column:
                  name: order_id

      rollback:
        - dropTable:
            tableName: order_items
        - dropTable:
            tableName: orders
        - dropTable:
            tableName: customer
~~~

Ví dụ minh họa kiểu dữ liệu và change type phổ biến. Khi dùng DBMS cụ thể, xác minh kiểu autoIncrement, TIMESTAMP và DECIMAL được Liquibase ánh xạ phù hợp. Rollback drop bảng sẽ xóa dữ liệu, vì vậy chỉ dùng trong môi trường thử nghiệm hoặc khi đã có kế hoạch phục hồi được phê duyệt; không xem rollback tạo schema ban đầu là thao tác vô hại trên production.

### Kiểm tra sau release 1.0

Xác nhận:

- Ba bảng tồn tại đúng schema.
- PK và FK được tạo đúng cột.
- Index theo customer/created_at và order_id tồn tại.
- Không có bảng hoặc constraint ngoài kế hoạch.
- Ứng dụng có thể tạo customer, order và order item.
- `total_amount` nhất quán với tổng dòng hàng theo quy tắc nghiệp vụ.

Ví dụ kiểm tra cấu trúc bằng information_schema trên PostgreSQL:

~~~sql
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('customer', 'orders', 'order_items')
ORDER BY table_name, ordinal_position;
~~~

## 5. Release 2.0-expand: thêm status và currency nullable

Yêu cầu mới cần mỗi đơn hàng có trạng thái và mã tiền tệ. Không thêm NOT NULL ngay lập tức vì dữ liệu cũ chưa có hai trường này và ứng dụng cũ có thể vẫn ghi đơn hàng theo cấu trúc trước.

Thay đổi đầu tiên chỉ mở rộng schema:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-add-order-status-currency
      author: commerce-team
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
              - column:
                  name: currency
                  type: CHAR(3)
~~~

Hai cột được thêm ở trạng thái nullable. Ở giai đoạn này:

- Code cũ chưa gửi status/currency vẫn có thể ghi đơn hàng.
- Code mới có thể bắt đầu đọc trường mới nếu xử lý NULL.
- Chưa bật ràng buộc bắt buộc.
- Chưa xóa `paid_at` hoặc thay đổi cấu trúc cũ.
- Chưa coi mọi dữ liệu đã hoàn tất chuyển đổi.

### Triển khai ứng dụng tương thích

Trong giai đoạn chuyển tiếp, ứng dụng có thể:

1. Đọc status nếu có; nếu NULL, tạm suy ra từ paid_at.
2. Ghi status mới cùng với paid_at theo quy tắc chuyển đổi.
3. Ghi currency cho đơn hàng mới.
4. Không giả định tất cả đơn cũ đã có status/currency.
5. Có metric đếm số bản ghi thiếu trường để theo dõi backfill.

Đây là cách tránh triển khai code đòi hỏi schema mới trước khi migration mở rộng đã hoàn tất.

## 6. Release 2.1-migrate: backfill dữ liệu cũ

Sau khi cột mới tồn tại, cần chuyển dữ liệu cũ. Quy tắc trong ví dụ:

- `paid_at IS NULL` → status = PENDING.
- `paid_at IS NOT NULL` → status = PAID.
- currency = VND chỉ khi đã xác nhận toàn bộ dữ liệu lịch sử đang dùng VND.

Với database nhỏ, có thể dùng changeset SQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 011-backfill-order-status-currency
      author: commerce-team
      changes:
        - sql:
            sql: |
              UPDATE orders
              SET status = CASE
                  WHEN paid_at IS NULL THEN 'PENDING'
                  ELSE 'PAID'
              END
              WHERE status IS NULL;

        - sql:
            sql: |
              UPDATE orders
              SET currency = 'VND'
              WHERE currency IS NULL;
~~~

Không chạy phần backfill currency nếu dữ liệu có nhiều tiền tệ hoặc không có bằng chứng rằng mọi đơn hàng đều là VND. Khi đó cần ánh xạ từ nguồn dữ liệu đáng tin cậy và dừng nếu không tìm được currency hợp lệ.

### Vì sao điều kiện WHERE quan trọng?

`WHERE status IS NULL` khiến thao tác có thể chạy lại mà không ghi đè status đã được ứng dụng hoặc người vận hành xác định. Đây là một dạng idempotency hữu ích cho backfill đơn giản.

Tuy nhiên, một changeset đã được Liquibase ghi nhận sẽ không tự chạy lại chỉ vì câu SQL idempotent. Nếu job bị gián đoạn trước khi changeset ghi lịch sử, cần xác minh trạng thái thực tế trước retry. Không chỉnh DATABASECHANGELOG để ép chạy lại.

### Với bảng lớn, không backfill toàn bộ trong một transaction dài

Một UPDATE hàng triệu bản ghi có thể tạo transaction lớn, tăng WAL/redo, lock và replication lag. Với bảng lớn, nên tách thành job batch có:

- Phạm vi theo ID hoặc partition.
- Batch size có thể điều chỉnh.
- Checkpoint cho batch đã hoàn tất.
- Điều kiện idempotent.
- Retry có backoff.
- Metric số hàng còn thiếu và tốc độ xử lý.
- Cơ chế dừng/tiếp tục an toàn.

Liquibase quản lý các thay đổi schema và có thể ghi nhận phiên bản của quy trình dữ liệu; job backfill kéo dài có thể cần một cơ chế điều phối riêng. Phải ghi nhận rõ job version, release, phạm vi và hậu điều kiện trước khi cho phép bước contract.

## 7. Gate dữ liệu trước khi đặt NOT NULL

Trước khi bắt buộc hai cột, chạy assertion:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status IS NULL) AS missing_status,
    COUNT(*) FILTER (WHERE currency IS NULL) AS missing_currency
FROM orders;
~~~

Với PostgreSQL, FILTER là cú pháp hợp lệ; DBMS khác có thể dùng SUM(CASE WHEN ... THEN 1 ELSE 0 END).

Kỳ vọng:

- `missing_status = 0`.
- `missing_currency = 0).
- Giá trị status thuộc tập trạng thái được hỗ trợ.
- Currency là mã hợp lệ theo quy ước nghiệp vụ.
- Ứng dụng mới không còn ghi NULL trong thời gian xác minh.

Nếu có NULL, không tiếp tục. Xác định nhóm bản ghi thiếu, kiểm tra nguồn dữ liệu và chạy lại backfill có kiểm soát.

### Kiểm tra miền giá trị

Có thể kiểm tra status ngoài tập cho phép:

~~~sql
SELECT COUNT(*) AS invalid_status_count
FROM orders
WHERE status NOT IN (
    'PENDING',
    'PAID',
    'CANCELLED',
    'REFUNDED'
);
~~~

Lưu ý truy vấn trên không đếm NULL vì phép so sánh với NULL cho kết quả UNKNOWN; do đó cần assertion NULL riêng. Nếu nghiệp vụ có trạng thái khác, cập nhật tập giá trị theo state machine thực tế.

## 8. Release 2.2-contract: đặt NOT NULL và default

Khi mọi dữ liệu đã được backfill và code không còn ghi NULL, mới đặt ràng buộc. Precondition giúp Liquibase dừng nếu dữ liệu chưa đạt.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 012-constrain-order-status-currency
      author: commerce-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM orders
              WHERE status IS NULL
                 OR currency IS NULL
      changes:
        - addNotNullConstraint:
            tableName: orders
            columnName: status
            columnDataType: VARCHAR(20)
        - addNotNullConstraint:
            tableName: orders
            columnName: currency
            columnDataType: CHAR(3)
~~~

Sau đó đặt default cho các lệnh INSERT không truyền giá trị, nếu đó là quy tắc nghiệp vụ mong muốn:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 013-default-order-status-currency
      author: commerce-team
      changes:
        - addDefaultValue:
            tableName: orders
            columnName: status
            columnDataType: VARCHAR(20)
            defaultValue: PENDING
        - addDefaultValue:
            tableName: orders
            columnName: currency
            columnDataType: CHAR(3)
            defaultValue: VND
~~~

Default currency VND chỉ đúng trong mô hình đơn tiền tệ. Hệ thống đa tiền tệ nên yêu cầu ứng dụng cung cấp currency rõ ràng hoặc có default theo tenant/merchant được xác định ở tầng nghiệp vụ.

Tách thay đổi constraint và default thành changeset riêng giúp dễ xác định bước nào đã chạy và xử lý lỗi. Nếu một changeset chứa nhiều DDL, khả năng rollback phụ thuộc DBMS và transaction semantics; không giả định mọi DDL đều nguyên tử.

### Precondition không thay thế kiểm tra liên tục

Precondition được đánh giá khi Liquibase chạy changeset. Sau khi changeset thành công, một ứng dụng lỗi vẫn có thể ghi dữ liệu sai nếu quyền hoặc logic không được kiểm soát. Cần có constraint ở database và validation ở ứng dụng để bảo vệ trạng thái lâu dài.

## 9. Release 3.0: thêm lịch sử trạng thái đơn hàng

Nghiệp vụ cần biết đơn hàng đã chuyển từ trạng thái nào sang trạng thái nào, ai thực hiện và thời điểm nào. Thêm bảng `order_status_history`:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-create-order-status-history
      author: commerce-team
      changes:
        - createTable:
            tableName: order_status_history
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: order_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: previous_status
                  type: VARCHAR(20)
              - column:
                  name: new_status
                  type: VARCHAR(20)
                  constraints:
                    nullable: false
              - column:
                  name: changed_at
                  type: TIMESTAMP
                  constraints:
                    nullable: false
              - column:
                  name: changed_by
                  type: VARCHAR(100)
                  constraints:
                    nullable: false
              - column:
                  name: change_source
                  type: VARCHAR(30)
                  constraints:
                    nullable: false

        - addForeignKeyConstraint:
            baseTableName: order_status_history
            baseColumnNames: order_id
            constraintName: fk_order_status_history_order
            referencedTableName: orders
            referencedColumnNames: id

        - createIndex:
            tableName: order_status_history
            indexName: idx_order_status_history_order_time
            columns:
              - column:
                  name: order_id
              - column:
                  name: changed_at
~~~

Bảng này ghi nhận các chuyển trạng thái sau khi tính năng được bật. Không tự tạo lịch sử giả cho quá khứ nếu hệ thống cũ không có event log đáng tin cậy. Nếu cần một bản ghi baseline, ghi rõ `change_source = 'BASELINE'` và thời điểm ghi nhận baseline; không gán thời điểm đó thành thời điểm chuyển trạng thái thực tế trong quá khứ.

### Ghi order và history trong cùng transaction ứng dụng

Khi đơn hàng chuyển từ PENDING sang PAID, ứng dụng cần:

1. Đọc trạng thái hiện tại và xác định transition có hợp lệ không.
2. Cập nhật `orders.status`.
3. Thêm một dòng `order_status_history`.
4. Commit cả hai trong cùng transaction.

Nếu cập nhật orders thành công nhưng ghi history thất bại, transaction phải rollback để không tạo trạng thái thiếu audit. Có thể dùng optimistic locking hoặc điều kiện cập nhật theo trạng thái cũ để tránh hai request cùng chuyển trạng thái cạnh tranh.

Ví dụ logic SQL khái niệm:

~~~sql
BEGIN;

UPDATE orders
SET status = 'PAID'
WHERE id = :order_id
  AND status = 'PENDING';

-- Chỉ thêm history nếu đúng một order được cập nhật.
INSERT INTO order_status_history (
    order_id,
    previous_status,
    new_status,
    changed_at,
    changed_by,
    change_source
) VALUES (
    :order_id,
    'PENDING',
    'PAID',
    CURRENT_TIMESTAMP,
    :actor,
    'API'
);

COMMIT;
~~~

Đây là minh họa luồng; ứng dụng phải kiểm tra số hàng UPDATE trước khi INSERT và xử lý trường hợp không có transition hợp lệ. Không chạy nguyên đoạn SQL này như migration Liquibase vì đây là thao tác nghiệp vụ theo từng request.

## 10. Release 4.0: thêm UNIQUE cho order_no

Ban đầu `order_no` chỉ NOT NULL nhưng chưa có unique constraint. Khi yêu cầu mã đơn không trùng được phê duyệt, phải kiểm tra dữ liệu cũ trước:

~~~sql
SELECT order_no, COUNT(*) AS occurrences
FROM orders
GROUP BY order_no
HAVING COUNT(*) > 1;
~~~

Nếu có kết quả, cần xác định bản ghi trùng là duplicate thật, dữ liệu import hay mã đơn được tái sử dụng theo tenant/merchant. Không tự xóa hoặc đổi mã khi chưa có quy tắc nghiệp vụ và kế hoạch tham chiếu.

Khi đã xử lý dữ liệu trùng, changeset thêm unique constraint:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 030-unique-order-number
      author: commerce-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM (
                  SELECT order_no
                  FROM orders
                  GROUP BY order_no
                  HAVING COUNT(*) > 1
              ) AS duplicate_order_numbers
      changes:
        - addUniqueConstraint:
            tableName: orders
            columnNames: order_no
            constraintName: uk_orders_order_no
~~~

Precondition giúp chặn migration nếu vẫn còn duplicate tại thời điểm chạy. Tuy nhiên, giữa lúc kiểm tra và tạo constraint, ứng dụng vẫn có thể tạo mã trùng nếu không có cơ chế phối hợp. Trước release, cần triển khai logic sinh mã duy nhất và kiểm soát writer; constraint database là lớp bảo vệ cuối cùng.

Với bảng lớn, tạo unique constraint có thể cần index build và lock tùy DBMS. Hãy đánh giá chiến lược online riêng theo hệ quản trị, kích thước bảng và SLA. Không giả định addUniqueConstraint luôn chạy không gián đoạn.

## 11. Quản lý thứ tự changeset và dependency

Thứ tự include phản ánh dependency:

~~~text
001-create-order-core
        |
        v
010-add-order-status-currency
        |
        v
011-backfill-order-status-currency
        |
        v
012-constrain-order-status-currency
        |
        v
013-default-order-status-currency
        |
        v
020-create-order-status-history
        |
        v
030-unique-order-number
~~~

Ví dụ:

- 011 cần cột được tạo bởi 010.
- 012 cần backfill của 011 đã hoàn tất.
- 020 cần bảng orders và cột status.
- 030 cần dữ liệu order_no đã được làm sạch.

Không chỉ dựa vào số ID để suy ra dependency. Liquibase thực thi theo thứ tự changelog được nạp, bao gồm include và các filter. Hãy review master changelog sau khi thêm file mới.

Tránh để cùng một file được include hai lần qua cả include tường minh và includeAll. Kiểm tra contexts/labels/dbms để bảo đảm changeset bắt buộc được chọn trong đúng môi trường.

## 12. Quy tắc bất biến của changeset và checksum

Sau khi changeset đã được chạy ở một database dùng chung, không sửa nội dung của nó để phản ánh thiết kế mới. Ví dụ không sửa `001-create-order-core` để thêm cột status sau khi production đã chạy 001.

Nếu sửa changeset cũ:

- Checksum có thể không còn khớp với DATABASECHANGELOG.
- Môi trường đã chạy và môi trường mới có thể xử lý cùng changelog khác nhau.
- Khó tái dựng schema của release cũ.
- Rollback và audit trở nên khó giải thích.

Cách đúng là tạo changeset mới với ID mới. Changelog đã phát hành là lịch sử migration; thay đổi tiếp theo phải được biểu diễn bằng một bước mới.

Định danh changeset gồm ID, author và đường dẫn changelog (có thể chịu ảnh hưởng của logicalFilePath). Khi backport cùng migration sang nhánh khác, giữ nguyên identity và nội dung nếu muốn Liquibase nhận diện đó là cùng một thay đổi.

Không dùng clear-checksums hoặc sửa MD5SUM trực tiếp để che sai khác chưa hiểu. Checksum mismatch cần được điều tra từ file, path, version và lịch sử triển khai.

## 13. Kiểm thử hai đường đi: database mới và database đã tồn tại

Một thiết kế migration qua nhiều release phải kiểm tra ít nhất hai đường:

### Đường A: database mới hoàn toàn

Dựng database rỗng, chạy toàn bộ master changelog đến release mới nhất. Xác nhận:

- Tất cả bảng và constraint được tạo.
- Các changeset được ghi nhận theo thứ tự.
- Schema cuối đúng thiết kế.
- Ứng dụng khởi động và thực hiện luồng đơn hàng được.

### Đường B: nâng cấp từ release cũ

Dựng database bằng changelog đến release 1.0, nạp dữ liệu đại diện, sau đó chạy các release 2.0, 2.1, 2.2, 3.0 và 4.0. Xác nhận:

- Backfill status/currency đúng quy tắc.
- Không mất dữ liệu cũ.
- Constraint chỉ được thêm khi precondition đạt.
- History table hoạt động cho transition mới.
- Duplicate order_no được phát hiện trước unique constraint.
- Ứng dụng tương thích trong giai đoạn chuyển tiếp.

Chỉ test database rỗng sẽ bỏ sót nhiều lỗi dữ liệu lịch sử. Chỉ test nâng cấp một snapshot production cũng không chứng minh đường cài mới hoạt động.

## 14. Quy trình kiểm tra bằng Liquibase CLI

Với master changelog đã cấu hình, quy trình cơ bản:

~~~shell
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate
liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

Sau khi review SQL và xác nhận target:

~~~shell
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
~~~

Cú pháp có thể thay đổi theo cách cài đặt CLI, file properties và phiên bản Liquibase. Mỗi môi trường phải sử dụng đúng URL/schema/credentials và contexts/labels đã phê duyệt.

Sau update, đối chiếu DATABASECHANGELOG, schema metadata và data assertions. `validate` kiểm tra cấu trúc changelog; `status` cho biết changeset pending; `update-sql` giúp review SQL dự kiến. Không lệnh nào thay thế việc kiểm tra dữ liệu và hành vi ứng dụng.

## 15. Kiểm tra DATABASECHANGELOG theo release

Ví dụ trên PostgreSQL nếu metadata nằm trong public:

~~~sql
SELECT
    id,
    author,
    filename,
    exectype,
    md5sum,
    dateexecuted,
    orderexecuted
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Mỗi release cần có danh sách changeset dự kiến. Ví dụ sau release 2.2, cần xác nhận các changeset 001, 010, 011, 012 và 013 đã được ghi nhận; changeset 020/030 có thể vẫn pending nếu chưa phát hành.

Không chỉ đếm số dòng. Kiểm tra đúng ID/author/path/checksum và loại thực thi. Một changeset bị MARK_RAN không đồng nghĩa DDL đã chạy; phải xem precondition và trạng thái schema thực tế.

Nếu cùng module triển khai cho nhiều database hoặc tenant, thực hiện kiểm tra trên từng đơn vị. Không dùng một DATABASECHANGELOG chung để suy ra mọi tenant đã đạt release.

## 16. Kiểm tra dữ liệu cuối cùng của lược đồ đơn hàng

Sau release 4.0, các assertion quan trọng:

### Không thiếu status/currency

~~~sql
SELECT COUNT(*) AS invalid_order_metadata
FROM orders
WHERE status IS NULL
   OR currency IS NULL;
~~~

Kỳ vọng bằng 0.

### Status thuộc tập cho phép

~~~sql
SELECT status, COUNT(*)
FROM orders
GROUP BY status
ORDER BY status;
~~~

Đối chiếu các giá trị với state machine nghiệp vụ. Nếu xuất hiện trạng thái ngoài danh sách, cần xác định đó là trạng thái hợp lệ mới hay dữ liệu sai.

### Không có mã đơn trùng

~~~sql
SELECT order_no, COUNT(*)
FROM orders
GROUP BY order_no
HAVING COUNT(*) > 1;
~~~

Kỳ vọng không có dòng kết quả sau khi unique constraint được tạo.

### Không có order item mồ côi

~~~sql
SELECT COUNT(*) AS orphan_items
FROM order_items oi
LEFT JOIN orders o ON o.id = oi.order_id
WHERE o.id IS NULL;
~~~

Kỳ vọng bằng 0.

### Tổng tiền nhất quán

Một assertion có thể so sánh total_amount với tổng quantity × unit_price của order_items. Cần thống nhất cách làm tròn, currency và các khoản thuế/phí trước khi dùng truy vấn làm tiêu chí. Không so sánh số thập phân bằng quy tắc làm tròn tùy tiện.

Các assertion phải được chạy trong phạm vi schema/tenant đúng và có kế hoạch tránh tạo tải quá lớn trên production.

## 17. Tương thích ứng dụng trong các giai đoạn phát hành

Một lược đồ có thể ở trạng thái chuyển tiếp trong lúc rolling deployment. Ví dụ:

| Giai đoạn | Schema | Ứng dụng cũ | Ứng dụng mới |
|---|---|---|---|
| Trước 2.0 | Chưa có status/currency | Hoạt động | Chưa triển khai |
| Sau 2.0-expand | Hai cột nullable | Vẫn hoạt động | Có thể đọc NULL và bắt đầu dual-write |
| Trong 2.1 | Backfill đang chạy | Phải tránh ghi dữ liệu không tương thích | Dual-read/dual-write |
| Sau 2.2-contract | Hai cột NOT NULL | Chỉ hoạt động nếu luôn cung cấp giá trị hoặc có default phù hợp | Hoạt động theo schema mới |
| Sau 3.0 | Có history table | Có thể chưa ghi history nếu tính năng chưa bật | Ghi status và history đồng bộ |

Không đặt NOT NULL khi còn instance cũ có thể ghi NULL, trừ khi default và semantics được chứng minh phù hợp. Với thay đổi phá hủy, dùng expand–migrate–contract và đợi mọi consumer cũ được loại bỏ trước khi contract.

Feature flag có thể giúp chuyển traffic, nhưng không thay thế kiểm tra schema và data. Một feature được bật khi tenant chưa có migration sẽ gây lỗi runtime.

## 18. Rollback và forward-fix cho lược đồ nhiều release

Rollback phải được xem xét theo từng changeset và dữ liệu đã phát sinh.

| Thay đổi | Khả năng đảo ngược | Rủi ro |
|---|---|---|
| Tạo bảng mới | Có thể drop bảng | Mất dữ liệu phát sinh sau release |
| Thêm cột nullable | Có thể drop cột | Mất giá trị ứng dụng đã ghi |
| Backfill status/currency | Có thể khó đảo | Giá trị cũ không còn nếu không lưu lại |
| Đặt NOT NULL | Có thể drop constraint | Không giải quyết dữ liệu sai |
| Tạo history table | Có thể drop bảng | Mất audit history |
| Thêm unique constraint | Có thể drop constraint | Có thể cho phép duplicate mới |

Nếu ứng dụng mới đã ghi dữ liệu vào cột mới, rollback drop cột có thể mất dữ liệu. Nếu history đã được dùng cho audit, không nên drop bảng chỉ vì code rollback. Forward-fix thường an toàn hơn: tạo changeset mới để sửa schema hoặc dữ liệu trong khi giữ lại thông tin đã phát sinh.

Không sửa changeset cũ để “đảo” một release. Tạo changeset mới cho hành động tiếp theo, trừ khi đang thử nghiệm trên database cô lập chưa được phát hành.

## 19. Tích hợp Spring Boot và pipeline phát hành

Trong Spring Boot, có thể để Liquibase chạy khi ứng dụng khởi động hoặc chạy qua job riêng của CI/CD. Với production và nhiều replica, nên xác định một migration owner rõ ràng.

Nếu pipeline chạy migration riêng, cấu hình minh họa:

~~~yaml
spring:
  liquibase:
    enabled: false
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Ứng dụng không tự chạy migration trong profile này; pipeline sở hữu việc update. `ddl-auto: validate` chỉ kiểm tra mapping theo cấu hình Hibernate, không thay thế Liquibase validation hoặc postflight SQL.

Một pipeline release có thể:

~~~text
Build changelog artifact
        |
        v
Validate + test từ database rỗng
        |
        v
Test upgrade từ release cũ có dữ liệu
        |
        v
Review update-sql + approval
        |
        v
Preflight target / backup / data
        |
        v
Liquibase update
        |
        v
Postflight history + schema + data
        |
        v
Deploy/enable application
        |
        v
Smoke test + observation
        |
        v
Record release evidence
~~~

Với database-per-tenant hoặc schema-per-tenant, registry phải theo dõi trạng thái từng đơn vị. Không đánh dấu toàn bộ release thành công khi mới có một tenant canary đạt.

## 20. Bài tập thực hành theo từng release

Có thể thực hiện bài tập trên database PostgreSQL dùng riêng cho học tập. Không chạy các lệnh phá hủy trên production.

### Bài tập A — Release 1.0

1. Tạo master changelog và changeset 001.
2. Chạy update trên database rỗng.
3. Kiểm tra ba bảng, PK, FK và index.
4. Tạo customer, order và hai order item.
5. Xác minh total_amount theo dữ liệu dòng hàng.

Kết quả mong đợi: schema nền tạo được từ đầu và dữ liệu quan hệ hợp lệ.

### Bài tập B — Release 2.0/2.1

1. Thêm status/currency nullable.
2. Deploy code có khả năng đọc NULL và dual-write.
3. Tạo dữ liệu cũ với paid_at NULL và non-NULL.
4. Chạy backfill.
5. Kiểm tra status được ánh xạ đúng.
6. Chạy assertion cho NULL và currency.

Kết quả mong đợi: mọi đơn hàng cũ có giá trị phù hợp theo quy tắc chuyển đổi đã thống nhất.

### Bài tập C — Release 2.2

1. Cố tình để một order status NULL trên database test.
2. Chạy changeset có sqlCheck.
3. Xác nhận Liquibase HALT và changeset chưa được ghi nhận thành công.
4. Sửa dữ liệu test.
5. Chạy lại sau khi xác minh trạng thái.
6. Kiểm tra NOT NULL và default.

Kết quả mong đợi: precondition ngăn constraint khi dữ liệu chưa đạt.

### Bài tập D — Release 3.0

1. Tạo history table.
2. Viết logic ứng dụng cập nhật order và history trong cùng transaction.
3. Thử chuyển PENDING → PAID.
4. Cố tình làm insert history lỗi trên database test.
5. Xác nhận update orders cũng rollback.
6. Kiểm tra thứ tự và nội dung history.

Kết quả mong đợi: không có trạng thái order thay đổi mà thiếu history event tương ứng.

### Bài tập E — Release 4.0

1. Tạo hai đơn có order_no trùng trên database test trước khi thêm constraint.
2. Chạy changeset có precondition.
3. Xác nhận migration dừng.
4. Xử lý duplicate theo quy tắc nghiệp vụ.
5. Chạy lại và xác minh unique constraint.
6. Thử INSERT trùng và xác nhận database từ chối.

Kết quả mong đợi: unique constraint chỉ được tạo sau khi dữ liệu đáp ứng điều kiện.

## 21. Tiêu chí nghiệm thu bài thực hành

Bài thực hành được xem là đạt khi:

**Changelog**

- Master changelog include đúng thứ tự.
- Mỗi changeset có ID/author ổn định.
- Changeset cũ không bị sửa sau khi đã triển khai.
- Precondition dừng đúng khi dữ liệu không đạt.
- SQL đặc thù DBMS được giới hạn và kiểm thử phù hợp.

**Schema**

- customer, orders, order_items và history table đúng định nghĩa.
- PK/FK/index/unique constraint đúng.
- status/currency đạt nullability/default theo release cuối.
- Không có object ngoài phạm vi do include/filter sai.

**Dữ liệu**

- Backfill status theo paid_at đúng quy tắc.
- Currency được điền từ nguồn đáng tin cậy.
- Không còn NULL hoặc duplicate ngoài mong đợi.
- Không có order item mồ côi.
- Tổng tiền nhất quán theo quy tắc làm tròn.

**Vận hành**

- Update từ database rỗng thành công.
- Upgrade từ release cũ có dữ liệu thành công.
- DATABASECHANGELOG/checksum khớp.
- Rollback/forward-fix được đánh giá theo tác động dữ liệu.
- Ứng dụng tương thích qua các giai đoạn expand/migrate/contract.
- Evidence và kết quả test được lưu cùng release.

## 22. Những lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Thêm NOT NULL thất bại | Còn dữ liệu NULL hoặc writer vẫn ghi NULL | Dừng, backfill và kiểm soát writer trước |
| Currency cũ bị điền sai | Giả định mọi đơn đều VND không đúng | Lấy nguồn currency chuẩn, không ghi đè dữ liệu |
| Backfill chạy quá lâu | Cập nhật toàn bảng trong transaction lớn | Chuyển sang batch có checkpoint |
| History không khớp trạng thái order | Hai thao tác không cùng transaction | Ghi order và event nguyên tử trong ứng dụng |
| Unique constraint thất bại | Có order_no trùng | Phân loại và xử lý duplicate trước |
| Checksum mismatch | Sửa changeset đã chạy hoặc đổi path | Khôi phục nội dung/identity và tạo changeset mới |
| Changeset không chạy | Master changelog thiếu include hoặc filter loại bỏ | Kiểm tra root changelog, context/label/dbms |
| Rollback mất dữ liệu | Drop cột/bảng đã có dữ liệu mới | Ưu tiên forward-fix hoặc restore có kế hoạch |
| Một môi trường khác schema | Migration không được chạy hoặc hotfix chưa backport | Đối chiếu DATABASECHANGELOG và schema từng môi trường |
| App lỗi khi rolling deploy | Contract trước khi loại bỏ code cũ | Triển khai expand, chuyển consumer rồi mới contract |

## 23. Checklist phát hành lược đồ đơn hàng

- [ ] Mô hình customer/orders/order_items được review.
- [ ] Quy tắc tổng tiền, trạng thái và tiền tệ được xác định.
- [ ] Master changelog include đúng thứ tự và không nạp trùng.
- [ ] Changeset đã triển khai được giữ bất biến.
- [ ] Release 2.0 thêm cột nullable trước khi backfill.
- [ ] Backfill status/currency có nguồn dữ liệu và điều kiện rõ.
- [ ] Bảng lớn dùng batch/checkpoint thay vì transaction dài.
- [ ] Precondition kiểm tra NULL trước NOT NULL.
- [ ] Ứng dụng tương thích trong giai đoạn chuyển tiếp.
- [ ] History table không giả mạo lịch sử quá khứ.
- [ ] Update order và insert history nằm trong cùng transaction ứng dụng.
- [ ] Duplicate order_no được xử lý trước unique constraint.
- [ ] Đã test từ database rỗng và từ release cũ có dữ liệu.
- [ ] Đã review update-sql và target identity.
- [ ] DATABASECHANGELOG/checksum được xác minh sau update.
- [ ] Schema/data postflight đạt.
- [ ] Rollback/forward-fix và backup/PITR được đánh giá.
- [ ] Release evidence và trạng thái từng môi trường được lưu.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, thiết kế lược đồ đơn hàng qua nhiều release là bài tập kết hợp mô hình dữ liệu, changelog bất biến, precondition, backfill, checksum, lịch sử và vận hành. Mỗi release cần tạo một bước tiến nhỏ có thể kiểm tra; ứng dụng phải tương thích với schema trong giai đoạn chuyển tiếp; dữ liệu cũ phải được chuyển đổi từ nguồn đáng tin cậy; và constraint chỉ được áp dụng khi hậu điều kiện đạt. Khi kiểm thử cả đường dựng mới lẫn đường nâng cấp từ dữ liệu cũ, nhóm có thể phát hành lược đồ đơn hàng có thể truy vết và duy trì an toàn qua nhiều phiên bản ứng dụng.
