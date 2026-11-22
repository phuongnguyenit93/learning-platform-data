# Thêm cột mới, bổ sung dữ liệu và chuyển đổi cách đọc ghi

## 1. Vì sao cần triển khai theo nhiều giai đoạn?

Một thay đổi schema thường bắt đầu từ yêu cầu tưởng như đơn giản: thêm cột mới, đưa dữ liệu cũ vào cột đó rồi sửa ứng dụng để đọc và ghi theo cấu trúc mới. Nhưng trong production, database vẫn đang được nhiều phiên bản ứng dụng, worker, batch job và báo cáo sử dụng. Các instance cũ có thể tiếp tục ghi trong lúc instance mới đã chạy; dữ liệu có thể được cập nhật đồng thời với backfill; một lần rollback ứng dụng không tự khôi phục schema hoặc dữ liệu.

Ví dụ, bảng <code>orders</code> đang có cột <code>status_text</code> lưu trạng thái dưới dạng văn bản. Nhóm muốn bổ sung <code>status_code</code> theo tập mã chuẩn để truy vấn và tích hợp dễ hơn. Nếu thêm cột mới với NOT NULL ngay lập tức, các instance cũ chưa biết cột này có thể ghi thất bại. Nếu backfill toàn bộ bảng trong một transaction dài, hệ thống có thể chịu lock, log tăng mạnh và replication lag. Nếu chuyển ứng dụng sang chỉ đọc cột mới trước khi dữ liệu cũ được chuyển đầy đủ, người dùng có thể thấy trạng thái rỗng.

Giải pháp là tách thay đổi thành các bước tương thích: **mở rộng schema, chuẩn bị đường ghi, bổ sung dữ liệu, kiểm chứng, chuyển đường đọc/ghi và cuối cùng mới thu hẹp cấu trúc cũ**. Mỗi bước có điều kiện hoàn tất và khả năng dừng riêng.

Bài học thuộc chương **Triển khai an toàn** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng dẫn quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào việc thêm cột mới, chuyển dữ liệu lịch sử và thay đổi cách đọc/ghi mà vẫn giữ ứng dụng hoạt động trong giai đoạn chuyển tiếp.

Sau bài học, người đọc có thể:

1. Thiết kế quy trình expand–migrate–contract cho một thay đổi dữ liệu đang phục vụ.
2. Thêm cột nullable bằng Liquibase theo hướng tương thích với phiên bản ứng dụng cũ.
3. Tổ chức dual-write, dual-read và feature flag có kiểm soát.
4. Backfill theo batch, có thể chạy lại và tiếp tục sau gián đoạn.
5. Xác minh dữ liệu, chuyển đọc sang cột mới và áp ràng buộc sau khi writer đã sẵn sàng.
6. Lập kế hoạch rollback, forward fix và giám sát production theo từng giai đoạn.

## 2. Ví dụ xuyên suốt: chuyển status_text sang status_code

Giả sử bảng hiện tại:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status_text VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Ứng dụng đang lưu các giá trị:

| Giá trị cũ trong status_text | Giá trị chuẩn trong status_code |
|---|---|
| <code>new</code> hoặc <code>NEW</code> | <code>NEW</code> |
| <code>paid</code> hoặc <code>PAID</code> | <code>PAID</code> |
| <code>cancelled</code> hoặc <code>CANCELLED</code> | <code>CANCELLED</code> |

Bảng có thể chứa giá trị legacy khác như <code>pending_review</code>, chuỗi rỗng hoặc NULL do dữ liệu cũ được import từ nhiều nguồn. Không được tự động gán mọi giá trị chưa biết thành <code>NEW</code>; phải thống kê và xác nhận mapping nghiệp vụ trước khi backfill.

Trạng thái mong muốn cuối cùng:

- <code>status_code</code> là nguồn dữ liệu chính.
- Giá trị mới thuộc tập mã đã thống nhất.
- Các truy vấn, API, worker và báo cáo sử dụng cột mới.
- Ứng dụng không còn ghi hoặc đọc <code>status_text</code>.
- Sau khi hết cửa sổ rollback và mọi dependency cũ đã được loại bỏ, có thể xóa cột legacy trong một release riêng.

## 3. Mô hình expand–migrate–contract

Quy trình có ba giai đoạn lớn, thường được chia thành nhiều release:

~~~text
Schema S1 + App V1
  status_text là nguồn chính
          |
          v
EXPAND
  Thêm status_code nullable
  Giữ status_text và hành vi cũ
          |
          v
MIGRATE
  Deploy code tương thích
  Dual-write / đọc fallback
  Backfill dữ liệu lịch sử theo batch
  Đối soát và kiểm chứng
          |
          v
SWITCH
  Shadow-read / so sánh kết quả
  Chuyển read path sang status_code
  Duy trì ghi tương thích trong cửa sổ rollback
          |
          v
CONTRACT
  Ngừng dùng status_text
  Hết mọi consumer/instance cũ
  Xóa cột legacy ở release sau
~~~

**Expand** tạo cấu trúc mới mà phiên bản cũ có thể tiếp tục hoạt động. **Migrate** chuyển ứng dụng và dữ liệu sang cấu trúc mới trong khi vẫn duy trì khả năng tương thích. **Contract** loại bỏ cấu trúc cũ sau khi đã chứng minh không còn phụ thuộc.

Không nên gộp cả ba giai đoạn vào một changeset hoặc một lần phát hành nếu ứng dụng cần rolling deployment hay khả năng rollback. Thời gian giữa các giai đoạn có thể là vài giờ, vài ngày hoặc nhiều release, tùy quy mô dữ liệu và vòng đời consumer.

## 4. Lập kế hoạch tương thích trước khi viết changelog

Trước khi thêm cột, xác định phiên bản ứng dụng nào sẽ cùng tồn tại và chúng đọc/ghi trường nào.

| Phiên bản | Đọc | Ghi | Tương thích với schema mở rộng? |
|---|---|---|---|
| V1 cũ | status_text | status_text | Có nếu cột mới nullable và không có ràng buộc bắt V1 phải điền |
| V2 chuyển tiếp | status_text hoặc fallback | status_text và status_code trong cùng transaction | Có |
| V3 chuyển đọc | status_code, fallback có kiểm soát | Cả hai cột trong cửa sổ rollback | Có |
| V4 sau contract | status_code | status_code | Chỉ tương thích sau khi schema đã contract theo kế hoạch |

Ma trận này là ví dụ; phải lập ma trận thực tế cho API, worker, batch, báo cáo, ETL và client ngoài hệ thống.

### 4.1. Tương thích đọc và tương thích ghi là hai điều kiện riêng

V1 có thể đọc được schema mới vì nó bỏ qua cột chưa biết. Nhưng nếu migration đặt <code>status_code NOT NULL</code>, V1 vẫn có thể ghi thất bại vì không gửi giá trị cho cột mới.

Tương tự, V3 có thể đọc <code>status_code</code> nhưng không có nghĩa mọi hàng đã có dữ liệu ở đó. Nếu backfill chưa xong, V3 phải có fallback hoặc chưa được bật read path mới.

### 4.2. Inventory tất cả writer và reader

Không chỉ kiểm tra web API. Hãy tìm:

- Các service và instance đang ghi bảng.
- Worker xử lý queue hoặc scheduled job.
- Batch import/ETL và script vận hành.
- Stored procedure, trigger và SQL trực tiếp.
- Báo cáo, BI, data warehouse và CDC consumer.
- Phiên bản ứng dụng cũ có thể được rollback hoặc scale lại.

Một job chạy cuối tháng có thể tiếp tục ghi cột cũ sau khi đội đã chuyển toàn bộ web instance. Contract chỉ an toàn khi đã kiểm tra hết các writer/reader theo chu kỳ nghiệp vụ phù hợp.

## 5. Kiểm tra dữ liệu trước khi thêm cột

Trước khi tạo mapping, cần biết dữ liệu thực tế:

~~~sql
SELECT status_text, COUNT(*) AS row_count
FROM orders
GROUP BY status_text
ORDER BY status_text;
~~~

Kiểm tra NULL và chuỗi rỗng:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN status_text IS NULL THEN 1 ELSE 0 END) AS null_rows,
    SUM(CASE WHEN TRIM(status_text) = '' THEN 1 ELSE 0 END) AS blank_rows
FROM orders;
~~~

Các hàm <code>TRIM</code>, cách xử lý chuỗi và biểu thức tổng hợp có thể khác theo DBMS; điều chỉnh cú pháp phù hợp.

Lập bảng mapping được owner nghiệp vụ xác nhận:

| Nhóm giá trị cũ | Cách xử lý | Điều kiện |
|---|---|---|
| new, NEW | NEW | Có thể chuẩn hóa chữ hoa/thường |
| paid, PAID | PAID | Có thể chuẩn hóa chữ hoa/thường |
| cancelled, CANCELLED | CANCELLED | Có thể chuẩn hóa chữ hoa/thường |
| pending_review | PENDING_REVIEW hoặc mapping khác | Cần xác nhận nghĩa nghiệp vụ |
| NULL/chuỗi rỗng | Giữ NULL, suy ra từ nguồn khác hoặc xử lý thủ công | Không tự gán trạng thái mặc định |
| Giá trị không biết | Đưa vào danh sách điều tra | Không âm thầm bỏ qua |

Chỉ bắt đầu backfill khi quy tắc mapping đã được duyệt và có cách xử lý dữ liệu ngoài miền. Nếu chưa thể ánh xạ một nhóm giá trị, giữ nhóm đó trong báo cáo lỗi hoặc bảng xử lý riêng.

## 6. Expand: thêm cột mới ở trạng thái nullable

Trong giai đoạn đầu, cột mới thường nên nullable và chưa có NOT NULL. Điều này cho phép phiên bản V1 tiếp tục ghi cột cũ trong lúc ứng dụng mới đang được rollout.

Ví dụ Liquibase YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 101-add-orders-status-code
      author: orders-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
        - not:
            - columnExists:
                tableName: orders
                columnName: status_code
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: status_code
                  type: varchar(24)
      rollback:
        - dropColumn:
            tableName: orders
            columnName: status_code
~~~

Ví dụ giả định default schema của kết nối đã đúng. Nếu bảng nằm ở schema riêng, chỉ định <code>schemaName</code> trong tableExists, columnExists và addColumn. Kiểu <code>varchar(24)</code> là minh họa; phải chọn độ dài theo miền mã chuẩn.

### 6.1. Vì sao chưa đặt NOT NULL?

Trong rolling deployment, V1 vẫn có thể tạo bản ghi mới mà chỉ điền <code>status_text</code>. Nếu <code>status_code</code> bắt buộc có giá trị ngay từ đầu, các request V1 sẽ lỗi. Nullable tạo cửa sổ tương thích để triển khai code mới và chuyển dữ liệu.

### 6.2. Cẩn trọng với DEFAULT khi thêm cột

Thêm cột có default không phải lúc nào cũng có cùng chi phí trên mọi DBMS/version. Một số engine/version có thể tối ưu default hằng số; trường hợp khác có thể rewrite bảng hoặc giữ khóa đáng kể. Nếu giá trị default không đúng về mặt nghiệp vụ, nó còn làm dữ liệu lịch sử có vẻ đã được chuyển dù thực tế chưa mapping.

Không dùng default <code>'NEW'</code> chỉ để làm số lượng NULL bằng 0. Default chỉ phù hợp khi mọi hàng mới và hàng cũ thực sự có cùng ý nghĩa mặc định đó. Thường nên thêm cột nullable trước, chuyển dữ liệu, rồi quyết định default cho bản ghi mới ở một bước riêng.

### 6.3. Kiểm tra trước và sau changeset

Precondition giúp dừng nếu bảng không tồn tại hoặc cột đã tồn tại theo trạng thái không mong đợi. Tuy nhiên, precondition không thay thế kiểm tra đúng datasource/schema và không ngăn thay đổi đồng thời từ một tiến trình ngoài Liquibase.

Sau changeset, xác minh:

- Cột tồn tại đúng schema.
- Kiểu và độ dài đúng.
- Nullability đang là trạng thái dự kiến.
- Các instance V1 vẫn có thể INSERT/UPDATE như trước.
- Changelog history ghi nhận changeset đúng database.

## 7. Chuẩn bị ứng dụng chuyển tiếp

Sau khi schema đã expand, triển khai một phiên bản ứng dụng có khả năng hiểu cả cấu trúc cũ và mới.

### 7.1. Dual-write trong cùng transaction

Trong giai đoạn chuyển tiếp, V2 có thể ghi cả hai cột. Nếu hai cột nằm trong cùng database và cùng transaction, hoặc cả hai cập nhật thành công hoặc cả hai rollback theo transaction đó.

Ví dụ Java/Spring minh họa:

~~~java
@Transactional
public void changeOrderStatus(long orderId, LegacyStatus status) {
    String legacyValue = status.toLegacyText();
    String newCode = status.toCode();

    Order order = orderRepository.findByIdForUpdate(orderId)
        .orElseThrow();

    order.setStatusText(legacyValue);
    order.setStatusCode(newCode);
    orderRepository.save(order);
}
~~~

Đây là pseudocode minh họa; repository lock, entity mapping và exception handling phải phù hợp dự án. Mấu chốt là hai giá trị được suy ra từ cùng một trạng thái nghiệp vụ và được ghi trong cùng transaction database.

Không thực hiện hai lần ghi độc lập ở hai transaction rồi giả định chúng luôn đồng bộ. Nếu một lần ghi thành công và lần kia thất bại, dữ liệu sẽ lệch. Nếu hai nguồn nằm ở hệ thống khác nhau, cần một cơ chế phối hợp như outbox, retry và reconciliation thay vì dựa vào transaction cục bộ.

### 7.2. Dual-write phải tính đến instance V1 còn chạy

V2 ghi cả hai cột không giúp V1 tự động ghi cột mới. Trong rolling deployment, V1 có thể tiếp tục cập nhật <code>status_text</code> sau khi một hàng đã được backfill, khiến <code>status_code</code> trở nên cũ.

Có ba chiến lược:

1. **Đợi V1 drain trước backfill:** rollout V2 tương thích, xác nhận mọi web instance, worker và job ghi cột cũ đã được nâng cấp hoặc dừng, rồi mới backfill. Đây thường là cách đơn giản nếu thời gian chuyển tiếp cho phép.
2. **Cầu nối ở database:** dùng trigger hoặc cơ chế đồng bộ DBMS để cập nhật cột mới khi writer cũ thay đổi cột cũ. Cần kiểm soát recursion, thứ tự ghi, error handling và quyền; trigger phải được kiểm thử như logic ứng dụng.
3. **Backfill trong khi V1 còn chạy kèm reconciliation:** dùng CDC/change tracking hoặc quét lặp để bắt các thay đổi xảy ra sau batch; chỉ chuyển read path khi đã chứng minh không còn writer cũ và không còn lệch.

Không chọn chiến lược “backfill một lần trong khi V1 vẫn ghi” rồi giả định dữ liệu sẽ luôn nhất quán.

### 7.3. Tương thích với ORM

Nếu dùng JPA/Hibernate, entity mới có thể khai báo cột mới nullable trong giai đoạn đầu:

~~~java
@Column(name = "status_code", length = 24)
private String statusCode;
~~~

Không bật validation NOT NULL ở tầng ORM trước khi mọi hàng và mọi writer đáp ứng điều kiện. Schema validation của ORM khi startup cũng cần phù hợp với trạng thái trung gian. Một entity mới chỉ có field statusCode không tự bảo đảm các câu SQL native, batch hoặc service cũ đã được cập nhật.

## 8. Thiết kế read path chuyển tiếp

Trong giai đoạn backfill, ứng dụng có thể đọc cột mới nếu có giá trị, nếu chưa thì chuyển đổi từ cột cũ theo mapping đã duyệt.

Ví dụ logic:

~~~java
String effectiveStatus(Order order) {
    if (order.getStatusCode() != null) {
        return order.getStatusCode();
    }
    return statusMapper.fromLegacy(order.getStatusText());
}
~~~

Đây là logic minh họa. Hàm mapping cần xử lý rõ giá trị không biết/NULL; không nên tự trả về một trạng thái mặc định có thể làm sai nghiệp vụ.

### 8.1. Đọc mới có fallback

Một read path có thể:

1. Ưu tiên <code>status_code</code> khi giá trị đã được xác nhận hợp lệ.
2. Nếu NULL, chuyển đổi từ <code>status_text</code> theo mapping.
3. Ghi metric cho số lần fallback.
4. Ghi nhận giá trị legacy không thể ánh xạ để điều tra.

Fallback giúp ứng dụng mới phục vụ dữ liệu chưa backfill, nhưng không nên trở thành cơ chế tồn tại vĩnh viễn. Nếu tỷ lệ fallback không giảm về 0, chưa nên contract.

### 8.2. Shadow-read để so sánh

Trước khi chuyển hẳn read path, có thể đọc cả hai nguồn trong một phần traffic hoặc một luồng kiểm tra:

- Kết quả theo logic cũ.
- Kết quả theo cột mới.
- Kết quả sau mapping từ dữ liệu cũ.

So sánh và ghi metric/log có kiểm soát; tránh log thông tin nhạy cảm hoặc toàn bộ payload. Không nhất thiết chạy hai truy vấn nặng trên mọi request; có thể sampling hoặc chạy đối soát offline.

Chỉ bật read path mới khi tỷ lệ khác biệt nằm trong ngưỡng được duyệt và mọi trường hợp ngoại lệ đã được giải thích.

## 9. Backfill dữ liệu theo batch

Không nên chuyển hàng triệu bản ghi bằng một câu UPDATE duy nhất trong changeset nếu nó tạo transaction quá dài. Backfill lớn nên có job riêng hoặc quy trình có khả năng giới hạn kích thước, commit và tiếp tục sau lỗi.

### 9.1. Đặc tính cần có

- **Idempotent:** chạy lại không ghi đè dữ liệu mới đã đúng.
- **Có checkpoint:** biết batch cuối cùng đã commit.
- **Batch nhỏ:** giới hạn số hàng hoặc thời gian mỗi transaction.
- **Có throttle:** giảm tốc hoặc pause khi database chịu tải cao.
- **Có đối soát:** biết còn bao nhiêu hàng chưa chuyển và vì sao.
- **Có retry:** xử lý lỗi tạm thời mà không nhân đôi hoặc làm sai dữ liệu.
- **Có mapping rõ:** giá trị không biết được đưa vào danh sách xử lý, không bị gán bừa.

### 9.2. Ví dụ batch PostgreSQL theo ID

Đoạn SQL minh họa cho một worker chạy nhiều transaction, mỗi lần xử lý một khoảng ID:

~~~sql
WITH batch AS (
    SELECT id
    FROM orders
    WHERE id > :last_id
      AND id <= :range_end
      AND status_code IS NULL
    ORDER BY id
    LIMIT :batch_size
)
UPDATE orders AS o
SET status_code = CASE UPPER(TRIM(o.status_text))
    WHEN 'NEW' THEN 'NEW'
    WHEN 'PAID' THEN 'PAID'
    WHEN 'CANCELLED' THEN 'CANCELLED'
    ELSE NULL
END
FROM batch
WHERE o.id = batch.id
  AND o.status_code IS NULL
RETURNING o.id;
~~~

Các placeholder <code>:last_id</code>, <code>:range_end</code> và <code>:batch_size</code> được bind parameter bởi job; đây không phải cú pháp chạy trực tiếp trong mọi SQL console. SQL sử dụng cú pháp PostgreSQL cho CTE và UPDATE FROM.

Job cần:

1. Chọn một khoảng ID ổn định.
2. Chạy batch trong transaction.
3. Commit cập nhật.
4. Chỉ sau commit mới ghi checkpoint tương ứng.
5. Tiếp tục tới hết khoảng.
6. Cuối cùng quét lại toàn bộ các hàng còn NULL, kể cả những ID nằm ngoài checkpoint do lỗi hoặc dữ liệu phát sinh.

Điều kiện <code>status_code IS NULL</code> giúp không ghi đè giá trị mới đã được ứng dụng dual-write. Tuy nhiên, nó không giải quyết trường hợp V1 cập nhật status_text sau khi hàng đã được backfill. Vì vậy cần drain V1, trigger hoặc reconciliation như mục 7.2.

Nếu mapping có giá trị ngoài danh sách, câu lệnh để NULL và cần truy vấn riêng để xử lý; không đánh dấu batch là hoàn tất về mặt nghiệp vụ khi còn các hàng không ánh xạ.

### 9.3. Không dùng checkpoint làm bằng chứng dữ liệu hoàn tất

Checkpoint chỉ cho biết job đã xử lý tới vị trí nào theo cách nó được thiết kế. Nó không chứng minh mọi hàng trước đó đã chuyển đúng, đặc biệt khi có lỗi từng hàng, concurrent writer hoặc dữ liệu được import sau checkpoint.

Sau khi chạy hết ID, vẫn cần truy vấn toàn bảng:

~~~sql
SELECT COUNT(*) AS remaining_null
FROM orders
WHERE status_code IS NULL;
~~~

Và thống kê các giá trị legacy chưa có mapping:

~~~sql
SELECT status_text, COUNT(*) AS row_count
FROM orders
WHERE status_code IS NULL
GROUP BY status_text
ORDER BY status_text;
~~~

Đây là các truy vấn minh họa; bảng lớn có thể cần index, sampling hoặc cách đối soát tối ưu hơn. Đánh giá chi phí đọc toàn bảng trước khi chạy trên giờ cao điểm.

### 9.4. Kích thước batch và throttle

Batch 500, 1.000 hay 10.000 hàng không phải con số đúng cho mọi database. Chọn theo:

- Kích thước row và index cần cập nhật.
- TPS ghi hiện tại.
- WAL/redo/binlog và replication capacity.
- Lock wait, deadlock và thời gian transaction.
- Connection pool và tải CPU/I/O.
- SLO của API và job khác.

Bắt đầu nhỏ trên dữ liệu đại diện, đo thời gian và tác động, sau đó điều chỉnh. Job nên có khả năng pause khi p95/p99 latency, replication lag hoặc lock wait vượt ngưỡng đã đặt.

## 10. Xử lý dữ liệu không ánh xạ được

Một backfill hoàn tất về kỹ thuật có thể vẫn chưa hoàn tất về nghiệp vụ. Ví dụ <code>status_text = 'PENDING_REVIEW'</code> không có trong mapping ban đầu. Có các cách xử lý:

- Bổ sung mã mới sau khi owner nghiệp vụ xác nhận.
- Chuyển sang một trạng thái tương đương đã được định nghĩa.
- Giữ bản ghi ở trạng thái chờ xử lý và đưa vào danh sách exception.
- Khôi phục dữ liệu từ nguồn authoritative nếu dữ liệu legacy sai.

Không dùng <code>ELSE 'NEW'</code> chỉ để làm cho số lượng NULL bằng 0. Điều đó che giấu dữ liệu không hợp lệ và có thể làm sai workflow.

Nếu cần lưu exception, ghi lại ID, giá trị gốc, lý do và trạng thái xử lý trong hệ thống có quyền truy cập phù hợp. Không tạo bảng phụ trong production chỉ vì tiện nếu chưa có changeset và owner cho bảng đó.

## 11. Đối soát trước khi chuyển read path

Trước khi chuyển đọc sang cột mới, kiểm tra ít nhất:

### 11.1. Không còn NULL

~~~sql
SELECT COUNT(*) AS null_status_code
FROM orders
WHERE status_code IS NULL;
~~~

Kết quả bằng 0 tại một thời điểm là cần thiết nhưng chưa đủ. Cần bảo đảm writer đang hoạt động không thể tạo NULL trở lại.

### 11.2. Không còn giá trị ngoài tập chuẩn

~~~sql
SELECT status_code, COUNT(*) AS row_count
FROM orders
WHERE status_code NOT IN ('NEW', 'PAID', 'CANCELLED')
GROUP BY status_code;
~~~

Nếu cột nullable, SQL NOT IN không trả về hàng NULL; kiểm tra NULL riêng. Nếu tập mã chuẩn có thêm trạng thái, cập nhật danh sách theo data contract thực tế.

### 11.3. Đối chiếu cột cũ và cột mới

~~~sql
SELECT COUNT(*) AS mismatch_count
FROM orders
WHERE status_code IS DISTINCT FROM
    CASE UPPER(TRIM(status_text))
        WHEN 'NEW' THEN 'NEW'
        WHEN 'PAID' THEN 'PAID'
        WHEN 'CANCELLED' THEN 'CANCELLED'
        ELSE NULL
    END;
~~~

<code>IS DISTINCT FROM</code> là cú pháp PostgreSQL so sánh có xử lý NULL; DBMS khác có thể cần biểu thức tương đương. Query phải dùng đúng mapping được duyệt. Nếu dữ liệu legacy không còn được cập nhật hoặc có ý nghĩa đã thay đổi, cần điều chỉnh cách đối soát thay vì so sánh máy móc.

### 11.4. Kiểm tra writer sau backfill

Trong một khoảng quan sát phù hợp:

- Metric số lần fallback về cột cũ phải giảm về 0.
- Không xuất hiện bản ghi mới có status_code NULL.
- Không có mismatch mới giữa hai cột.
- Các API và worker ghi trạng thái không phát sinh lỗi.
- Dữ liệu được tạo bởi các phiên bản ứng dụng đang chạy đều hợp lệ.

Nếu còn writer V1, đối soát có thể đạt rồi lại sai ngay sau đó. Chỉ chuyển read path khi đã kiểm soát nguồn ghi.

## 12. Switch: chuyển cách đọc sang cột mới

Sau khi backfill và kiểm chứng, chuyển read path bằng một thay đổi ứng dụng riêng hoặc feature flag:

1. Đọc <code>status_code</code> làm nguồn chính.
2. Giữ fallback tạm thời để xử lý dữ liệu ngoại lệ nếu chính sách cho phép.
3. Theo dõi tỷ lệ fallback, mismatch, lỗi nghiệp vụ và latency.
4. Duy trì dual-write trong cửa sổ rollback đã định.
5. Tắt fallback chỉ sau khi chứng minh không còn dữ liệu chưa chuyển.

### 12.1. Chuyển bằng feature flag

Một feature flag có thể điều khiển read source:

~~~java
public OrderStatus readStatus(Order order, boolean useNewColumn) {
    if (useNewColumn && order.getStatusCode() != null) {
        return OrderStatus.fromCode(order.getStatusCode());
    }
    return OrderStatus.fromLegacy(order.getStatusText());
}
~~~

Ví dụ minh họa; cần xử lý giá trị không biết và log exception theo chính sách. Feature flag giúp bật theo canary hoặc nhóm người dùng, nhưng không thay thế kiểm chứng dữ liệu. Nếu bật flag cho một phần traffic, các luồng ghi vẫn phải bảo đảm tính nhất quán.

### 12.2. Không để hai nguồn sự thật tồn tại vô thời hạn

Dual-write là cơ chế chuyển tiếp, không phải trạng thái đích mặc định. Nếu duy trì hai cột mãi mãi:

- Có nguy cơ hai giá trị lệch nhau.
- Mọi thay đổi nghiệp vụ phải cập nhật hai field.
- Query và index phức tạp hơn.
- Đội phát triển không rõ cột nào là authoritative.

Hãy xác định rõ thời điểm ngừng ghi cột cũ, thời điểm ngừng đọc cột cũ và thời điểm xóa cột legacy. Ba thời điểm có thể khác nhau.

## 13. Khi nào áp dụng NOT NULL, CHECK và index?

Không áp ràng buộc cuối cùng ngay khi thêm cột. Thứ tự thường là:

1. Cột mới nullable.
2. Ứng dụng mới bắt đầu dual-write.
3. Backfill dữ liệu cũ.
4. Đối soát NULL và giá trị ngoài miền.
5. Xác nhận không còn writer cũ tạo giá trị không hợp lệ.
6. Thêm CHECK/NOT NULL hoặc ràng buộc tương đương.
7. Tạo index theo nhu cầu truy vấn và kỹ thuật online phù hợp.

Ví dụ Liquibase precondition trước khi enforce:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 102-enforce-orders-status-code
      author: orders-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: status_code
        - sqlCheck:
            expectedResult: "0"
            sql: SELECT COUNT(*) FROM orders WHERE status_code IS NULL
      changes:
        - addNotNullConstraint:
            tableName: orders
            columnName: status_code
            columnDataType: varchar(24)
      rollback:
        - dropNotNullConstraint:
            tableName: orders
            columnName: status_code
            columnDataType: varchar(24)
~~~

Đây là ví dụ khái niệm; schemaName có thể cần thêm. Precondition đếm NULL có thể tốn tài nguyên trên bảng lớn và có race nếu writer vẫn tạo NULL sau khi kiểm tra. Điều kiện này không thay thế việc dừng writer cũ hoặc bảo đảm mọi writer đã tuân thủ contract.

### 13.1. Ràng buộc CHECK cho tập mã

Nếu nghiệp vụ có tập mã cố định, có thể thêm CHECK để database bảo vệ miền dữ liệu. Cần xem DBMS hỗ trợ validate theo giai đoạn hay không, cách xử lý NULL và tác động khi thêm constraint trên bảng lớn.

Trước khi áp CHECK:

- Liệt kê toàn bộ giá trị hiện có.
- Xử lý giá trị ngoài tập.
- Đảm bảo code mới chỉ ghi mã hợp lệ.
- Xác minh batch import và SQL trực tiếp cũng tuân thủ.

### 13.2. Index sau khi dữ liệu đã ổn định

Nếu query lọc theo <code>status_code</code>, index có thể cần thiết. Nhưng index không nên được thêm chỉ vì cột mới xuất hiện. Xem query plan và workload; cân nhắc index ghép theo tenant/time nếu đó là pattern thực tế.

Trên PostgreSQL, tạo index concurrent có yêu cầu riêng và không chạy trong transaction block; MySQL có các tùy chọn online DDL tùy phiên bản/engine. Tách changeset index đặc thù DBMS và thử trên dữ liệu đại diện. Không giả định một change type portable có cùng lock behavior trên mọi engine.

## 14. Contract: loại bỏ cột cũ

Contract là bước phá vỡ tương thích và cần được thực hiện sau khi:

- Tất cả instance ứng dụng cũ đã được drain.
- Không còn worker, batch, báo cáo, ETL hoặc integration đọc/ghi cột cũ.
- Read path mới đã ổn định và fallback không còn được sử dụng.
- Dual-write đã dừng theo kế hoạch.
- Backup/retention và nhu cầu audit dữ liệu cũ đã được giải quyết.
- Cửa sổ rollback về phiên bản phụ thuộc cột cũ đã kết thúc.

Changeset xóa cột cũ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 201-drop-legacy-order-status
      author: orders-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - columnExists:
            tableName: orders
            columnName: status_text
      changes:
        - dropColumn:
            tableName: orders
            columnName: status_text
~~~

Ví dụ này chỉ minh họa DDL; precondition kiểm tra cột tồn tại không chứng minh không còn ứng dụng dùng cột đó. Trước khi chạy cần gate ngoài database như inventory dependency, xác nhận version, telemetry và phê duyệt release.

### 14.1. Không gộp contract vào release đầu

Nếu xóa cột cũ ngay trong cùng release thêm cột mới, đội không còn đường rollback ứng dụng cũ. Thêm lại cột bằng rollback DDL cũng không phục hồi giá trị đã mất. Hãy để contract ở release sau, khi hệ thống đã qua thời gian quan sát và mọi dependency cũ đã được loại bỏ.

### 14.2. Xóa cột có thể là thao tác tốn kém hoặc phá hủy

Hành vi DROP COLUMN, thời gian giữ khóa và khả năng thu hồi dung lượng phụ thuộc DBMS/version. Một số engine có thể đánh dấu metadata trước, việc reclaim storage diễn ra sau hoặc cần thao tác khác. Không giả định drop column luôn tức thời và không ảnh hưởng truy vấn.

## 15. Rollback theo từng giai đoạn

Thiết kế an toàn cần trả lời: nếu dừng ở mỗi bước, ứng dụng nào còn chạy được và dữ liệu nào còn giữ?

| Trạng thái | Hướng xử lý thường phù hợp | Điều cần xác minh |
|---|---|---|
| Chỉ expand, chưa có app ghi cột mới | Có thể giữ cột mới và sửa app; drop cột chỉ khi chắc chắn không cần | Không có object/dependency sử dụng cột |
| V2 dual-write đang chạy | Thường rollback app về bản tương thích, giữ schema mở rộng | V1 đọc/ghi đúng dữ liệu đã tạo trong thời gian V2 |
| Backfill đang chạy | Pause job, giữ checkpoint, điều tra exception rồi resume | Batch đã commit, mapping và dữ liệu concurrent |
| Đã backfill, chưa switch read | Có thể tiếp tục đọc cột cũ trong khi giữ dữ liệu mới | Hai cột nhất quán, writer cũ đã dừng hoặc có cầu nối |
| Đã switch read, vẫn dual-write | Có thể tắt feature flag nếu app cũ tương thích | Cột mới không chứa giá trị mà app cũ không hiểu |
| Đã enforce NOT NULL/CHECK | Có thể cần rollback constraint trước khi dùng app cũ | Không còn writer mới phụ thuộc ràng buộc; dữ liệu không mất |
| Đã dừng ghi cột cũ nhưng chưa drop | Có thể bật lại dual-write nếu code và dữ liệu cho phép | Cột cũ còn đủ dữ liệu để khôi phục |
| Đã drop cột cũ | Không thể khôi phục dữ liệu cũ chỉ bằng ADD COLUMN | Backup, audit hoặc forward fix có dữ liệu tái dựng |

### 15.1. Rollback ứng dụng không tự rollback database

Nếu V3 đọc <code>status_code</code> và phát sinh lỗi, có thể rollback về V2 nếu V2 tương thích với schema hiện tại và dữ liệu mới. Không nhất thiết chạy Liquibase rollback để drop cột mới. Giữ cấu trúc mở rộng thường ít rủi ro hơn.

### 15.2. Rollback DDL không hoàn nguyên backfill

Drop <code>status_code</code> sẽ xóa giá trị đã chuyển. Nếu <code>status_text</code> vẫn được dual-write, có thể tiếp tục dùng cột cũ; nhưng nếu đã dừng ghi cột cũ hoặc dữ liệu đã được chuẩn hóa theo nghĩa mới, rollback không còn đơn giản.

Đối với biến đổi dữ liệu mất thông tin, cần lưu nguồn gốc, audit hoặc backup trước khi chuyển. Nếu không thể đảo chính xác, forward fix hoặc restore có kiểm soát thường phù hợp hơn việc chạy rollback SQL giả định.

## 16. Preconditions, checksum và lịch sử changeset

### 16.1. Preconditions bảo vệ điều kiện triển khai

Precondition có thể xác minh bảng/cột tồn tại, DBMS phù hợp hoặc dữ liệu đáp ứng điều kiện trước khi enforce. Chọn <code>HALT</code> khi trạng thái không đạt và cần điều tra. Không dùng <code>MARK_RAN</code> để che việc cột hoặc constraint chưa thực sự được tạo.

Một <code>sqlCheck</code> kiểm tra NULL bằng 0 chỉ phản ánh thời điểm kiểm tra. Nếu writer còn có thể ghi NULL, dữ liệu có thể vi phạm ngay sau đó. Cần phối hợp ứng dụng và ràng buộc để đóng race.

### 16.2. Không sửa changeset đã triển khai

Sau khi changeset đã được áp dụng, không chỉnh nội dung của nó để thay đổi mapping hoặc cách backfill. Liquibase lưu checksum trong DATABASECHANGELOG; sửa changeset lịch sử có thể gây checksum mismatch và làm các môi trường không nhất quán.

Nếu phát hiện mapping sai:

1. Dừng hoặc giới hạn writer có thể tiếp tục tạo dữ liệu sai.
2. Xác định dữ liệu đã được chuyển và phạm vi ảnh hưởng.
3. Tạo changeset/job mới để sửa dữ liệu theo mapping đã xác nhận.
4. Đối soát và lưu bằng chứng.
5. Chỉ tiếp tục switch/contract sau khi đạt điều kiện.

### 16.3. Phân biệt Liquibase history và tiến độ backfill

DATABASECHANGELOG ghi nhận changeset đã chạy, không tự theo dõi từng batch của job dữ liệu bên ngoài. Nếu backfill là job riêng, cần checkpoint và trạng thái riêng có thể kiểm toán. Không đánh dấu changeset enforce hoàn tất chỉ vì changeset tạo cột đã chạy hoặc job đã khởi động.

## 17. Giám sát trong quá trình chuyển đổi

Theo dõi cả database, ứng dụng và tiến độ dữ liệu:

| Nhóm | Chỉ số |
|---|---|
| Backfill | Tổng hàng, hàng đã chuyển, hàng còn NULL, exception, batch throughput |
| Data quality | Mismatch cũ/mới, giá trị ngoài tập, tỷ lệ fallback |
| Database | Lock wait, deadlock, CPU, I/O, WAL/redo/binlog, replication lag |
| Ứng dụng | p95/p99 latency, error rate, timeout, connection pool |
| Rollout | Số instance theo version, worker còn chạy code cũ, feature flag state |
| Liquibase | Changeset đang chạy, history, checksum, DATABASECHANGELOGLOCK |

### 17.1. Ngưỡng dừng cần xác định trước

Ví dụ các điều kiện cần pause:

- API vượt SLO hoặc lỗi ghi tăng rõ rệt.
- Replication lag vượt giới hạn vận hành.
- Lock wait/deadlock tăng khi chạy batch.
- Số mismatch tăng thay vì giảm.
- Backfill liên tục gặp giá trị không ánh xạ.
- Có instance cũ tiếp tục ghi cột legacy sau khi nhóm nghĩ đã drain.

Ngưỡng cụ thể do owner dịch vụ và DBA đặt dựa trên hệ thống. Khi pause, lưu checkpoint sau commit cuối cùng, xác minh transaction đang hoạt động và trạng thái dữ liệu trước khi resume.

### 17.2. Log và dữ liệu nhạy cảm

Log tiến độ theo batch, số hàng và ID checkpoint; tránh ghi toàn bộ dữ liệu cá nhân hoặc payload nhạy cảm. Nếu cần ghi exception row, dùng kênh có quyền truy cập, retention và audit phù hợp.

## 18. Tổ chức triển khai với Spring Boot và CI/CD

Một quy trình release điển hình:

~~~text
Build artifact + changelog
          |
          v
Validate / status / SQL preview
          |
          v
Review mapping + compatibility matrix
          |
          v
Migration job: EXPAND
          |
          v
Deploy app chuyển tiếp (dual-write, fallback)
          |
          v
Drain writer cũ hoặc bật bridge đã kiểm thử
          |
          v
Backfill batch + reconcile
          |
          v
Verify dữ liệu và metrics
          |
          v
Switch read path theo feature flag
          |
          v
Quan sát + duy trì cửa sổ rollback
          |
          v
Release sau: CONTRACT
~~~

### 18.1. Ai chạy Liquibase?

Với migration nhỏ, startup auto-run trong Spring Boot có thể phù hợp. Với DDL kéo dài, backfill hoặc cần approval, nên chạy Liquibase qua job riêng để rollout ứng dụng không phải chờ mỗi replica tự khởi tạo migration.

Không bật đồng thời startup auto-run và migration job mà không có chủ thể điều phối. Cả hai có thể dùng cùng history lock nhưng vẫn gây startup delay và khó kiểm soát thời điểm. Nếu job là chủ thể duy nhất, cấu hình <code>spring.liquibase.enabled=false</code> ở runtime application theo đúng profile; bảo đảm job riêng vẫn được cấu hình chạy changelog.

### 18.2. Cố định artifact và parameters

Preview và update phải dùng cùng:

- Changelog root và include files.
- Commit/image digest.
- Liquibase/JDBC driver version.
- DBMS, schema và datasource.
- Context, labels và changelog parameters.
- Mapping version được phê duyệt.

Không review SQL của một commit rồi chạy migration từ artifact khác. Không lưu secret trong changelog hoặc log pipeline.

### 18.3. Multi-environment

Thử lần lượt trên database local/test, staging có dữ liệu đại diện và production theo rollout có kiểm soát. Không chỉ kiểm tra database trống; vấn đề backfill, NULL, lock và mapping thường chỉ xuất hiện khi dữ liệu cũ đủ đa dạng.

Production có thể dùng batch/canary: một nhóm tenant hoặc partition trước, sau đó mở rộng khi metrics ổn định. Mỗi đích cần checkpoint và kết quả riêng.

## 19. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Thêm cột mới NOT NULL ngay lập tức | Instance cũ không gửi giá trị và ghi thất bại | Expand bằng cột nullable trước |
| Thêm default để loại bỏ NULL | Dữ liệu lịch sử mang giá trị giả | Xác định semantics, backfill theo mapping |
| Backfill toàn bảng trong một transaction | Lock lâu, log lớn, khó rollback | Batch nhỏ, commit, checkpoint và throttle |
| Backfill khi V1 vẫn ghi cột cũ | Cột mới có thể stale sau khi batch đi qua | Drain writer, trigger/CDC hoặc reconciliation |
| V2 dual-write ở hai transaction độc lập | Hai cột lệch khi một lần ghi thất bại | Ghi cùng transaction hoặc cơ chế đồng bộ có kiểm chứng |
| Chuyển read path trước khi backfill xong | Người dùng thấy NULL hoặc trạng thái sai | Fallback/shadow-read và data quality gate |
| Gán giá trị mặc định cho mã legacy chưa biết | Làm sai ý nghĩa nghiệp vụ | Exception workflow và mapping được duyệt |
| Chỉ đếm NULL một lần | Writer có thể tạo NULL ngay sau kiểm tra | Kiểm soát writer và ràng buộc trước switch |
| Contract cùng release expand | Không rollback được app cũ | Tách contract sang release sau |
| Drop cột cũ trước khi kiểm tra batch/report | Luồng định kỳ bị lỗi | Inventory mọi reader/writer |
| Chỉ dựa vào DATABASECHANGELOG để biết backfill xong | History không phản ánh từng batch | Checkpoint và đối soát riêng |
| Sửa changeset đã chạy để sửa mapping | Checksum mismatch giữa môi trường | Tạo changeset/job sửa mới |
| Chạy migration đồng thời ở mọi replica | Startup chờ lock và rollout chậm | Cân nhắc migration job riêng |
| Không đo replication lag và API latency | Backfill làm suy giảm dịch vụ | Metrics và ngưỡng pause |
| Rollback drop cột mới sau khi app đã ghi dữ liệu | Mất dữ liệu đã chuyển | Giữ schema mở rộng hoặc backup/forward fix |

## 20. Bài thực hành

### Bài A — Thêm cột và giữ ứng dụng cũ hoạt động

1. Tạo bảng orders có status_text.
2. Viết changeset thêm status_code nullable.
3. Chạy Liquibase update và xác minh cột mới.
4. Chạy phiên bản ứng dụng cũ để INSERT/UPDATE status_text.
5. Xác nhận cột mới không làm thay đổi hành vi cũ.

Mục tiêu: chứng minh giai đoạn expand không phá compatibility.

### Bài B — Dual-write và backfill

1. Cập nhật ứng dụng để ghi hai cột trong cùng transaction.
2. Tạo tập dữ liệu gồm giá trị chuẩn, NULL và mã legacy chưa biết.
3. Chạy backfill theo batch, ghi checkpoint sau commit.
4. Ngắt job giữa chừng và chạy lại.
5. Xác nhận giá trị đã chuyển không bị ghi đè và exception được thống kê.
6. Mô phỏng một writer cũ cập nhật status_text để thấy vì sao cần drain/bridge/reconciliation.

Mục tiêu: hiểu idempotence và race với concurrent writer.

### Bài C — Chuyển read path

1. Thêm fallback đọc status_code rồi status_text.
2. Bật shadow-read cho một phần traffic.
3. Đối chiếu kết quả và đo tỷ lệ fallback/mismatch.
4. Sau khi đạt gate, bật đọc cột mới.
5. Giữ dual-write trong cửa sổ rollback.

Mục tiêu: tách việc chuyển đọc khỏi việc dừng ghi cột cũ.

### Bài D — Enforce và contract

1. Xác nhận không còn NULL hoặc giá trị ngoài tập.
2. Xác nhận mọi writer đã tuân thủ.
3. Thêm CHECK/NOT NULL trong changeset riêng.
4. Deploy phiên bản chỉ dùng status_code.
5. Xác minh không còn dependency cũ.
6. Ở release sau, drop status_text và kiểm tra rollback/backup plan.

Mục tiêu: hiểu contract là bước phá tương thích cần phê duyệt riêng.

## 21. Checklist trước khi chuyển đổi production

- [ ] Đã xác định nguồn dữ liệu chuẩn và mapping cho mọi giá trị legacy.
- [ ] Đã thống kê NULL, chuỗi rỗng, giá trị lạ và phân bố dữ liệu.
- [ ] Đã inventory mọi writer/reader, bao gồm batch, ETL, báo cáo và consumer.
- [ ] Cột mới được expand theo hướng tương thích; kiểu/độ dài đã được xác nhận.
- [ ] Changeset có precondition phù hợp và rollback được hiểu rõ giới hạn dữ liệu.
- [ ] V1 và V2 đã được thử trên schema trung gian.
- [ ] Dual-write dùng cùng transaction hoặc có cơ chế đồng bộ được kiểm chứng.
- [ ] Có kế hoạch drain writer cũ hoặc bridge/CDC/reconciliation.
- [ ] Backfill có batch, checkpoint, retry, idempotence và throttle.
- [ ] Có bước quét lại dữ liệu sau checkpoint và xử lý exception.
- [ ] Có đối soát NULL, mapping, mismatch và concurrent writes.
- [ ] Read path mới có fallback/shadow-read và metrics.
- [ ] Feature flag có thể dừng hoặc chuyển lại theo ma trận tương thích.
- [ ] NOT NULL/CHECK/index được áp sau khi writer và dữ liệu sẵn sàng.
- [ ] Contract được tách khỏi release expand và có xác nhận hết dependency.
- [ ] Rollback ứng dụng, rollback DDL và phục hồi dữ liệu được phân biệt.
- [ ] CI/CD cố định artifact, parameters, datasource và lưu bằng chứng từng giai đoạn.
- [ ] Có ngưỡng pause, owner vận hành và kế hoạch forward fix/restore.

## 22. Kết luận

Thêm cột mới và chuyển cách đọc/ghi là một quá trình thay đổi hợp đồng dữ liệu giữa database và tất cả phiên bản ứng dụng đang hoạt động. Cách triển khai an toàn là **expand bằng cột tương thích → chuẩn bị ứng dụng dual-write/fallback → kiểm soát writer cũ → backfill theo batch → đối soát → chuyển read path → enforce → contract ở release sau**.

Liquibase quản lý các thay đổi cấu trúc và lịch sử changeset; job backfill có thể cần cơ chế checkpoint, retry và throttle riêng. Preconditions giúp bảo vệ điều kiện nhưng không thay thế kiểm soát concurrent writer. Checksum bảo vệ tính nhất quán của changelog nhưng không chứng minh dữ liệu đã được chuyển đúng. Khi gặp sự cố, giữ schema mở rộng và rollback ứng dụng thường an toàn hơn việc drop cột; nếu dữ liệu đã mất thông tin, cần forward fix hoặc restore có kiểm soát. Kết hợp changelog, changeset, precondition, checksum, kiểm chứng dữ liệu và pipeline Spring Boot/CI/CD giúp quá trình chuyển đổi có thể quan sát, dừng và tiếp tục theo từng giai đoạn.
