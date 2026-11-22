# Thiết kế bảng tổng hợp hoặc dữ liệu dẫn xuất với cơ chế cập nhật rõ ràng

Trong chương **Mô hình dữ liệu** của module **DATABASE_PERFORMANCE**, bảng tổng hợp và dữ liệu dẫn xuất giúp tổ chức dữ liệu theo cách phù hợp với đường đọc thường xuyên. Một ứng dụng có thể phải join nhiều bảng, tính lại số dư, đếm trạng thái hoặc ghép thông tin khách hàng vào từng đơn hàng mỗi lần hiển thị. Lưu một phần kết quả đã tính có thể giảm số lần đọc, số phép join và chi phí tính toán. Tuy nhiên, dữ liệu dẫn xuất chỉ có ích khi hệ thống biết rõ dữ liệu nào là nguồn sự thật, kết quả được tính theo quy tắc nào và cập nhật ra sao khi nguồn thay đổi.

Thiết kế một bảng dẫn xuất vì thế phải bắt đầu từ hợp đồng cập nhật. Hợp đồng này xác định grain của mỗi dòng, khóa định danh, nguồn dữ liệu, sự kiện làm thay đổi kết quả, cách xử lý insert/update/delete, mức nhất quán, độ trễ cho phép, chống xử lý trùng, phục hồi và đối soát. Nếu thiếu những quy tắc đó, bảng dẫn xuất dễ trở thành một bản sao cũ hoặc sai lệch mà không ai biết.

## 1. Phân biệt dữ liệu nguồn và dữ liệu dẫn xuất

**Dữ liệu nguồn** (*source of truth*) là dữ liệu chuẩn được nghiệp vụ ghi nhận. **Dữ liệu dẫn xuất** (*derived data*) là kết quả được tính từ một hoặc nhiều nguồn để phục vụ một cách đọc cụ thể.

Ví dụ, hệ thống bán hàng có thể có:

| Dữ liệu | Vai trò | Ví dụ |
|---|---|---|
| `orders` | Nguồn chuẩn của đơn hàng | Mã đơn, khách hàng, trạng thái, thời điểm tạo |
| `order_items` | Nguồn chuẩn của dòng hàng | Sản phẩm, số lượng, đơn giá, chiết khấu |
| `payments` | Nguồn chuẩn của thanh toán | Số tiền, phương thức, trạng thái thanh toán |
| `order_read_model` | Dữ liệu dẫn xuất cho màn hình đơn hàng | Tên khách, tổng tiền, trạng thái hiển thị |
| `daily_store_summary` | Dữ liệu tổng hợp cho báo cáo | Doanh thu theo ngày và cửa hàng |
| `search_document` | Dữ liệu dẫn xuất cho tìm kiếm | Văn bản đã chuẩn hóa và các trường lọc |

Khi khách đổi tên, `customers.name` có thể là nguồn chuẩn; tên được sao chép vào `order_read_model` là dữ liệu dẫn xuất. Khi một đơn hàng có thêm dòng hàng, tổng tiền hiển thị trong projection phải được cập nhật theo quy tắc tính tiền. Nếu một khoản thanh toán bị hoàn, số tiền đã thanh toán phải phản ánh sự kiện hoàn tiền.

Không nên để nhiều bảng cùng được xem là nguồn chuẩn cho một thuộc tính. Nếu cả bảng đơn hàng và bảng summary đều được phép sửa trực tiếp tổng tiền, hệ thống sẽ không còn biết giá trị nào có thẩm quyền khi xảy ra sai lệch.

## 2. Khi nào nên tạo bảng tổng hợp hoặc projection?

Dữ liệu dẫn xuất phù hợp khi một đường đọc có tần suất cao, chi phí tính toán lớn hoặc cần hình dạng dữ liệu khác với mô hình ghi. Các trường hợp thường gặp:

- Màn hình danh sách cần hiển thị trạng thái, tên khách hàng, tổng tiền và số dòng hàng trong một lần đọc.
- Dashboard liên tục tổng hợp doanh thu, số giao dịch hoặc số lượng đối tượng theo thời gian.
- Trang chi tiết cần một document đã ghép dữ liệu từ nhiều bảng.
- Bộ lọc tìm kiếm cần trường chuẩn hóa hoặc chỉ mục chuyên dụng.
- Số dư hoặc số lượng tồn cần được đọc nhanh trong khi lịch sử biến động vẫn được lưu riêng.

Trước khi tạo bảng, hãy đo đường đọc hiện tại. Ghi lại số lần gọi, elapsed, CPU, logical reads, số phép join, số dòng trung gian và độ trễ p95/p99. Nếu truy vấn hiện tại đã đủ nhanh hoặc ít được gọi, thêm một projection có thể chỉ làm tăng độ phức tạp.

### 2.1. Các hình thức dữ liệu dẫn xuất

| Hình thức | Nội dung | Cách cập nhật thường gặp |
|---|---|---|
| Bảng tổng hợp | Các chỉ số được gộp theo grain xác định | Batch, CDC, sự kiện hoặc transaction đồng bộ |
| Read model/projection | Hình dạng dữ liệu tối ưu cho một màn hình hoặc API | Transaction đồng bộ hoặc consumer bất đồng bộ |
| Materialized view | Kết quả truy vấn được database lưu lại | Refresh toàn bộ hoặc incremental tùy hệ quản trị |
| Counter | Một số đếm hoặc giá trị tích lũy được duy trì | Delta khi nguồn thay đổi, có đối soát |
| Search document | Nội dung đã ghép và chuẩn hóa cho tìm kiếm | Event, CDC hoặc pipeline đồng bộ |
| Cache | Bản sao tạm thời nhằm giảm truy cập nguồn | TTL, invalidation hoặc cập nhật theo sự kiện |

Các hình thức này có thể kết hợp nhưng không có cùng semantics. Cache có thể bị loại bỏ và tạo lại; bảng số dư hoặc read model có thể là thành phần quan trọng của đường phục vụ người dùng và cần quy trình phục hồi chặt chẽ hơn.

## 3. Xác định grain, khóa và quy tắc dữ liệu

Grain mô tả ý nghĩa của một dòng. Hãy viết một câu rõ ràng trước khi tạo schema. Ví dụ:

> Một dòng trong `order_read_model` đại diện cho trạng thái hiển thị mới nhất của đúng một đơn hàng.

Hoặc:

> Một dòng trong `daily_store_summary` đại diện cho doanh thu của một cửa hàng trong một ngày nghiệp vụ và một loại tiền tệ.

Grain quyết định khóa chính, các chiều được giữ lại và cách gộp dữ liệu. Nếu grain không rõ, dữ liệu có thể bị cộng trùng hoặc không thể cập nhật chính xác khi một thuộc tính thay đổi.

### 3.1. Chọn khóa ổn định

- Projection theo đơn hàng thường dùng `order_id` làm khóa.
- Summary theo ngày/cửa hàng/tiền tệ dùng tổ hợp `(business_date, store_id, currency_code)`.
- Counter theo tenant/trạng thái dùng `(tenant_id, status)`.
- Projection theo phiên bản đối tượng có thể lưu thêm `source_version` để phát hiện sự kiện cũ.

Khóa phải đại diện đúng grain và có unique constraint để database bảo vệ tính duy nhất. Không dựa vào kiểm tra `SELECT` trước rồi mới `INSERT` như biện pháp duy nhất, vì hai transaction đồng thời có thể cùng thấy chưa có dòng và cùng chèn.

### 3.2. Định nghĩa chỉ số và thuộc tính dẫn xuất

Với mỗi trường dẫn xuất, ghi rõ:

- Công thức tính và các trường nguồn.
- Quy tắc `NULL`, làm tròn, tiền tệ, múi giờ và trạng thái được tính.
- Có cộng được qua các chiều hay không.
- Khi dữ liệu nguồn sửa hoặc xóa, kết quả được thay thế, trừ delta hay tính lại.
- Giá trị nào được xem là hợp lệ khi nguồn thiếu hoặc sự kiện đến muộn.

Ví dụ, `paid_amount` có thể là tổng các khoản thanh toán đã quyết toán trừ các khoản hoàn đã quyết toán. Nó không nhất thiết bằng `orders.total_amount`, vì đơn hàng có thể chưa thanh toán đủ, thanh toán nhiều lần hoặc được hoàn một phần.

### 3.3. Lưu nguồn gốc và thời điểm cập nhật

Các cột như `source_version`, `refreshed_at`, `last_event_id` hoặc `source_watermark` giúp trả lời projection được cập nhật từ đâu và đến thời điểm nào. Chúng cũng hỗ trợ phát hiện dữ liệu cũ, chạy lại pipeline và đối soát.

Không nên dùng một timestamp duy nhất để thay thế version nếu hệ thống có thể nhận sự kiện không theo thứ tự. Timestamp từ các máy khác nhau có thể lệch đồng hồ; version tăng theo từng aggregate hoặc sequence do nguồn cấp thường đáng tin cậy hơn để xác định thứ tự thay đổi.

## 4. Chọn cơ chế cập nhật phù hợp

Có bốn nhóm cơ chế phổ biến. Lựa chọn dựa trên yêu cầu độ mới, khả năng cập nhật cùng transaction, chi phí ghi và độ phức tạp vận hành.

| Cơ chế | Đặc điểm | Phù hợp khi |
|---|---|---|
| Cập nhật đồng bộ trong transaction | Nguồn và projection commit cùng nhau | Cùng database, logic ngắn, cần nhất quán tức thời |
| Transactional outbox và consumer | Ghi nguồn và sự kiện trong một transaction, projection cập nhật sau | Cần xử lý bất đồng bộ hoặc nhiều hệ thống nhận sự kiện |
| CDC từ transaction log | Đọc thay đổi đã commit từ log của database | Cần đồng bộ nhiều bảng hoặc nhiều hệ thống với ít sửa ứng dụng |
| Batch/recompute định kỳ | Tính lại theo lịch hoặc cửa sổ dữ liệu | Báo cáo chấp nhận độ trễ và có thể xử lý theo lô |

Không có cơ chế nào tốt nhất cho mọi dữ liệu. Có thể cập nhật counter nhỏ đồng bộ trong transaction, đồng thời cập nhật search document bất đồng bộ qua outbox. Bảng summary báo cáo có thể được rebuild theo ngày, trong khi read model đơn hàng cần cập nhật gần thời gian thực.

## 5. Cập nhật đồng bộ trong cùng transaction

Nếu dữ liệu nguồn và projection nằm trong cùng database, và thao tác cập nhật đơn giản, có thể ghi cả hai trong một transaction. Khi transaction commit, cả hai cùng có hiệu lực; khi rollback, cả hai cùng bị hủy.

Ví dụ, bảng nguồn lưu sổ biến động số dư và bảng projection lưu số dư hiện tại:

```sql
CREATE TABLE account_ledger (
    entry_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id       uuid NOT NULL UNIQUE,
    account_id     bigint NOT NULL,
    amount_delta   numeric(20, 2) NOT NULL,
    created_at     timestamptz NOT NULL
);

CREATE TABLE account_balance_projection (
    account_id     bigint PRIMARY KEY,
    balance        numeric(20, 2) NOT NULL,
    updated_at     timestamptz NOT NULL
);
```

Khi ghi một biến động, có thể thêm ledger entry và chỉ cập nhật projection nếu `event_id` là mới:

```sql
BEGIN;

WITH inserted_entry AS (
    INSERT INTO account_ledger (
        event_id, account_id, amount_delta, created_at
    )
    VALUES (
        :event_id, :account_id, :amount_delta, clock_timestamp()
    )
    ON CONFLICT (event_id) DO NOTHING
    RETURNING account_id, amount_delta
)
INSERT INTO account_balance_projection (
    account_id, balance, updated_at
)
SELECT account_id, amount_delta, clock_timestamp()
FROM inserted_entry
ON CONFLICT (account_id)
DO UPDATE SET
    balance = account_balance_projection.balance + EXCLUDED.balance,
    updated_at = EXCLUDED.updated_at;

COMMIT;
```

Ví dụ dùng cú pháp PostgreSQL. Khóa duy nhất trên `event_id` chống cộng cùng một biến động hai lần khi ứng dụng retry. CTE chỉ trả dòng vừa được insert; nếu event đã tồn tại thì projection không được cộng lại. Ledger và projection nằm trong cùng transaction nên không có trạng thái ledger đã commit nhưng projection chưa cập nhật do lỗi giữa hai thao tác.

Đây là ví dụ minh họa cho số dư dẫn xuất; hệ thống tài chính thực tế cần thêm quy tắc tiền tệ, kiểm tra hạn mức, thứ tự hạch toán, khóa tài khoản, đối soát và kiểm soát quyền. Không dùng phép cộng đơn giản nếu nghiệp vụ cần kiểm tra số dư không âm hoặc áp dụng nhiều loại bút toán.

### 5.1. Ưu điểm và giới hạn

Ưu điểm là dữ liệu đọc có thể nhất quán ngay sau commit và logic phục hồi tương đối rõ. Đổi lại, transaction dài hơn, ghi thêm dữ liệu và có thể tạo tranh chấp nếu nhiều giao dịch cập nhật cùng một projection row.

Không nên thực hiện lời gọi mạng, gửi email hoặc publish message tới broker bên ngoài trong transaction database rồi giả định hai hệ thống cùng commit. Database transaction không tự bảo đảm atomicity với dịch vụ bên ngoài. Hãy dùng outbox hoặc một giao thức phân tán được thiết kế riêng.

## 6. Transactional outbox cho cập nhật bất đồng bộ

Khi projection được lưu ở database khác, search engine hoặc cache phân tán, ứng dụng thường cần phát sự kiện sau khi dữ liệu nguồn commit. Nếu ghi nguồn trước rồi publish message sau, tiến trình có thể dừng giữa hai bước: dữ liệu đã commit nhưng message bị mất. Nếu publish trước rồi transaction nguồn rollback, consumer có thể xử lý một thay đổi chưa từng được commit.

Transactional outbox giải quyết khoảng trống này bằng cách ghi thay đổi nguồn và bản ghi outbox trong cùng transaction.

```sql
CREATE TABLE outbox_events (
    event_id          uuid PRIMARY KEY,
    aggregate_type    text NOT NULL,
    aggregate_id      text NOT NULL,
    aggregate_version bigint NOT NULL,
    event_type        text NOT NULL,
    payload           jsonb NOT NULL,
    created_at        timestamptz NOT NULL,
    published_at      timestamptz
);
```

Transaction nghiệp vụ:

```sql
BEGIN;

UPDATE orders
SET status = 'COMPLETED',
    version = version + 1,
    updated_at = clock_timestamp()
WHERE order_id = :order_id;

INSERT INTO outbox_events (
    event_id, aggregate_type, aggregate_id, aggregate_version,
    event_type, payload, created_at
)
VALUES (
    :event_id, 'order', :order_id, :new_version,
    'OrderCompleted', :payload::jsonb, clock_timestamp()
);

COMMIT;
```

Worker nền đọc outbox và publish tới broker. Nếu worker publish thành công nhưng chết trước khi đánh dấu `published_at`, event có thể được gửi lại. Vì vậy, outbox thường bảo đảm không mất event đã commit khi được vận hành đúng, nhưng phía consumer vẫn phải chấp nhận giao nhận ít nhất một lần và xử lý idempotent.

### 6.1. Consumer chống xử lý trùng

Consumer có thể lưu event id đã xử lý cùng transaction với cập nhật projection:

```sql
CREATE TABLE processed_events (
    event_id     uuid PRIMARY KEY,
    processed_at timestamptz NOT NULL
);
```

Mẫu xử lý khái quát:

1. Bắt đầu transaction ở database projection.
2. Thêm `event_id` vào `processed_events` với unique constraint.
3. Chỉ khi insert mới thành công mới cập nhật projection.
4. Commit cả hai thao tác cùng nhau.
5. Chỉ xác nhận message với broker sau khi transaction commit.

Nếu message được giao lại, unique constraint nhận ra event đã xử lý và consumer không áp dụng thay đổi lần nữa. Nếu transaction rollback, cả dấu đã xử lý và projection cùng rollback để message có thể được thử lại.

### 6.2. Xử lý sự kiện đến sai thứ tự

Chống trùng không giải quyết được sự kiện đến sai thứ tự. Ví dụ `OrderCompleted` version 5 có thể đến trước `OrderCancelled` version 6; nếu version 5 được xử lý sau version 6, projection có thể quay về trạng thái cũ.

Với event chứa toàn bộ trạng thái mới, có thể chỉ áp dụng khi `incoming_version > source_version`:

```sql
UPDATE order_read_model
SET status = :status,
    total_amount = :total_amount,
    source_version = :incoming_version,
    refreshed_at = clock_timestamp()
WHERE order_id = :order_id
  AND source_version < :incoming_version;
```

Nếu event chỉ chứa delta như `+10` hoặc `-5`, không thể bỏ qua mọi version nhỏ hơn version hiện tại mà không kiểm tra khoảng trống, vì có thể mất một delta chưa được áp dụng. Khi đó cần thứ tự tuần tự theo aggregate, kiểm tra version kế tiếp, hoặc lưu và sắp xếp event còn thiếu trước khi áp dụng.

## 7. CDC từ transaction log

Change Data Capture (CDC) đọc các thay đổi đã commit từ transaction log hoặc cơ chế capture của database rồi chuyển chúng tới consumer. CDC hữu ích khi cần đồng bộ nhiều bảng hoặc xây projection mà không phải thêm logic publish ở mọi đường ghi của ứng dụng.

Một pipeline CDC thường có các thành phần:

1. Nguồn database và vị trí log/LSN/binlog/SCN tương ứng.
2. Connector đọc insert, update, delete và metadata giao dịch.
3. Broker hoặc vùng lưu sự kiện trung gian.
4. Consumer ánh xạ thay đổi thành projection.
5. Checkpoint lưu vị trí đã xử lý và cơ chế replay.

CDC có thể phát before-image, after-image hoặc chỉ một phần cột tùy cấu hình và hệ quản trị. Consumer phải biết rõ semantics của payload. Nếu chỉ nhận after-image, việc tính delta cho một tổng tích lũy có thể cần đọc trạng thái cũ trong projection hoặc giữ bản ghi trước đó.

CDC không tự hiểu ý nghĩa nghiệp vụ. Một dòng `orders` đổi trạng thái có thể cần cập nhật counter, search document, tồn kho hoặc bảng tổng hợp theo những quy tắc khác nhau. Cần xây lớp chuyển đổi có kiểm soát, xử lý schema evolution và bảo đảm thứ tự theo transaction/aggregate khi cần.

## 8. Batch và tính lại theo phạm vi

Batch phù hợp khi dữ liệu có thể trễ theo lịch hoặc thay đổi tập trung theo ngày/kỳ. Có thể tính lại toàn bộ summary hoặc chỉ một phạm vi như ngày gần nhất, partition hiện tại hay nhóm tenant được thay đổi.

Ví dụ, bảng `daily_order_summary` được tính lại cho một ngày:

```sql
BEGIN;

DELETE FROM daily_order_summary
WHERE business_date = :business_date;

INSERT INTO daily_order_summary (
    business_date, tenant_id, order_count, net_amount, refreshed_at
)
SELECT created_at::date,
       tenant_id,
       COUNT(*),
       SUM(net_amount),
       clock_timestamp()
FROM orders
WHERE status = 'COMPLETED'
  AND created_at >= :day_start
  AND created_at <  :next_day_start
GROUP BY created_at::date, tenant_id;

COMMIT;
```

Đây là ví dụ PostgreSQL cho phạm vi ngày được tính lại nguyên tử trong một transaction. Với bảng lớn, xóa và nạp trong cùng transaction có thể tạo nhiều WAL, giữ khóa lâu hoặc ảnh hưởng truy vấn đọc. Có thể nạp vào staging rồi publish bằng đổi partition, swap table hoặc cơ chế phù hợp với engine.

### 8.1. Chọn phạm vi tính lại

- **Toàn bộ bảng:** đơn giản, dễ đối soát, nhưng chi phí cao khi nguồn lớn.
- **Một partition:** phù hợp dữ liệu phân vùng theo thời gian hoặc tenant.
- **Cửa sổ gần đây:** xử lý giao dịch đến muộn trong vài ngày gần nhất.
- **Các khóa bị thay đổi:** tiết kiệm công việc nhưng cần biết chính xác khóa nào bị ảnh hưởng và xử lý cả khóa cũ lẫn mới khi một dòng đổi dimension.

Nếu một đơn hàng chuyển từ ngày 10 sang ngày 11, phải tính lại cả nhóm ngày 10 và ngày 11. Chỉ tính nhóm mới sẽ để lại tổng cũ sai lệch.

### 8.2. Watermark

Watermark biểu thị vị trí hoặc thời điểm nguồn đã được xử lý. Có thể là LSN, sequence, batch id hoặc timestamp. Watermark chỉ được tiến sau khi toàn bộ thay đổi trước vị trí đó đã được áp dụng bền vững.

Timestamp đơn thuần có thể không an toàn nếu nhiều dòng cùng timestamp, đồng hồ lệch hoặc dữ liệu cũ được sửa. Nếu dùng `updated_at`, hãy có tie-breaker ổn định, cửa sổ chồng lấn và cơ chế chống trùng. Với CDC, ưu tiên checkpoint theo vị trí log mà connector cung cấp.

## 9. Xử lý insert, update, delete và thay đổi quan hệ

Một hợp đồng cập nhật đầy đủ phải xác định delta cho từng loại thay đổi.

| Thay đổi nguồn | Tác động lên dữ liệu dẫn xuất | Cách xử lý thường gặp |
|---|---|---|
| Insert | Thêm dòng hoặc tăng chỉ số ở grain tương ứng | Insert projection hoặc cộng delta |
| Update thuộc tính không ảnh hưởng projection | Không cần thay đổi projection | Bỏ qua event hoặc chỉ cập nhật metadata nếu cần |
| Update thuộc tính được sao chép | Thay giá trị cũ bằng giá trị mới | Upsert trạng thái mới theo version |
| Update dimension/grain | Chuyển đóng góp từ khóa cũ sang khóa mới | Trừ khỏi nhóm cũ, cộng vào nhóm mới |
| Delete | Xóa projection hoặc đảo đóng góp | Delete/soft delete hoặc delta âm |
| Hủy/hoàn tiền | Thay đổi trạng thái hoặc số đo | Ghi event điều chỉnh, không cộng lại toàn bộ một cách mù quáng |

Với tổng doanh thu, update từ 100 thành 120 cần delta `+20` nếu biết giá trị cũ. Nếu không có before-image, consumer có thể đọc giá trị cũ từ projection rồi tính chênh lệch, nhưng phải bảo đảm xử lý tuần tự và chống trùng.

Với projection lưu toàn bộ trạng thái mới, cách an toàn hơn thường là ghi đè các trường được dẫn xuất từ snapshot mới cùng version, thay vì áp dụng các phép cộng không có khả năng lặp lại.

## 10. Mức nhất quán và độ trễ dữ liệu

Dữ liệu dẫn xuất có thể được cập nhật đồng bộ hoặc bất đồng bộ. Hãy chọn mức nhất quán theo hành vi mà ứng dụng cần.

| Mức phục vụ | Đặc điểm | Ví dụ phù hợp |
|---|---|---|
| Đồng bộ trong transaction | Projection nhất quán ngay sau commit nguồn trong cùng database | Số dư cần đọc ngay sau ghi, counter ảnh hưởng hạn mức |
| Gần thời gian thực | Event được xử lý sau commit, có độ trễ nhỏ và đo được | Search document, màn hình theo dõi đơn hàng |
| Theo batch | Projection cập nhật theo lịch hoặc cửa sổ | Báo cáo ngày, phân tích lịch sử |
| Ước lượng/cached | Chấp nhận dữ liệu cũ trong TTL hoặc sai số | Dashboard quy mô lớn, số liệu xu hướng |

### 10.1. Công bố độ mới

Projection bất đồng bộ nên lưu `refreshed_at`, `source_version` hoặc watermark. API có thể trả metadata như `data_as_of` để client biết dữ liệu được cập nhật đến thời điểm nào. Không nên gọi dữ liệu là “real-time” nếu pipeline có độ trễ vài phút hoặc có backlog chưa xử lý.

### 10.2. Đọc nguồn và projection trong cùng quy trình

Nếu API đọc thông tin đơn hàng từ nguồn nhưng tổng tiền từ projection, hai phần có thể phản ánh hai phiên bản khác nhau. Cần xác định có chấp nhận trạng thái tạm thời này không. Có thể trả version của nguồn và projection để kiểm tra, chờ projection bắt kịp hoặc đọc lại từ nguồn cho thao tác cần nhất quán cao.

### 10.3. Tránh transaction kéo dài

Không giữ transaction nguồn mở để chờ consumer bất đồng bộ. Transaction dài làm tăng thời gian giữ lock, giữ phiên bản MVCC và gây áp lực log. Hãy commit nguồn cùng outbox, sau đó để consumer cập nhật projection độc lập.

## 11. Xử lý đồng thời và điểm nóng

Nhiều transaction có thể cập nhật cùng một dòng counter hoặc summary. Nếu không có cơ chế khóa hoặc cập nhật nguyên tử, các phép đọc-sửa-ghi có thể làm mất cập nhật.

Ví dụ không an toàn về mặt đồng thời:

1. Transaction A đọc counter = 10.
2. Transaction B cũng đọc counter = 10.
3. A ghi 11.
4. B ghi 11.

Kết quả đúng phải là 12 nhưng hệ thống chỉ còn 11. Hãy dùng phép cập nhật nguyên tử như `SET counter = counter + 1`, upsert có khóa, row lock hoặc optimistic concurrency với version.

### 11.1. Khóa và thứ tự cập nhật

Khi một transaction phải cập nhật nhiều summary row, hãy lấy khóa theo thứ tự ổn định để giảm nguy cơ deadlock. Giữ transaction ngắn và tránh thực hiện I/O bên ngoài trong lúc giữ khóa. Có retry có giới hạn cho deadlock hoặc serialization failure, nhưng retry phải an toàn nhờ idempotency.

### 11.2. Hot key

Một tenant hoặc sản phẩm có lượng cập nhật áp đảo có thể làm một dòng counter trở thành hot row. Các hướng xử lý:

- Chia counter thành bucket theo shard hoặc khoảng thời gian rồi cộng khi đọc.
- Gom nhiều event thành một batch update.
- Cập nhật bất đồng bộ nếu nghiệp vụ chấp nhận độ trễ.
- Tách workload ghi và đọc sang projection phù hợp.

Sharding counter làm tăng chi phí đọc và đối soát. Hãy đo lock wait, update latency và throughput trước khi triển khai.

### 11.3. Version và optimistic concurrency

Với projection chứa trạng thái mới nhất, có thể dùng `source_version` để ngăn event cũ ghi đè event mới. Nếu cập nhật thất bại vì version không khớp, consumer cần phân biệt event đã cũ, event bị thiếu trước đó hay xung đột cần retry. Không được âm thầm bỏ qua một version gap nếu event là delta không thể thay thế.

## 12. Rebuild và backfill an toàn

Projection phải có khả năng tái tạo từ nguồn. Rebuild cần tránh khoảng trống giữa dữ liệu snapshot và các thay đổi phát sinh trong lúc copy.

Một quy trình triển khai projection mới có thể gồm:

1. Xác định vị trí bắt đầu CDC hoặc event sequence.
2. Chụp snapshot nguồn nhất quán tại vị trí tương ứng nếu hệ thống hỗ trợ.
3. Nạp snapshot vào bảng projection mới hoặc staging.
4. Phát lại các thay đổi sau vị trí snapshot theo thứ tự cần thiết.
5. Đối soát số dòng, tổng tiền, trạng thái và version theo các nhóm dữ liệu.
6. Chờ consumer bắt kịp watermark và xác nhận backlog bằng 0 hoặc nằm trong giới hạn.
7. Chuyển traffic đọc sang projection mới theo cách có thể rollback.
8. Giữ projection cũ trong thời gian xác nhận và chỉ loại bỏ sau khi đã đủ bằng chứng.

Nếu snapshot và vị trí log không được liên kết đúng, có thể mất hoặc áp dụng trùng thay đổi xảy ra trong lúc backfill. Hãy dùng cơ chế consistent snapshot/CDC được connector hỗ trợ; không tự ghép timestamp gần đúng rồi xem là không có khoảng trống.

### 12.1. Rebuild theo phiên bản

Có thể thêm `projection_version` hoặc tạo bảng mới cho phiên bản schema/logic mới. Nạp và kiểm tra bảng mới trước khi chuyển ứng dụng. Cách này giảm rủi ro sửa trực tiếp projection đang phục vụ người dùng và cho phép quay lại phiên bản trước nếu kết quả không đạt.

### 12.2. Đối soát

Đối soát cần so sánh theo grain và quy tắc nghiệp vụ, không chỉ so tổng toàn hệ thống. Ví dụ, với summary doanh thu theo ngày/cửa hàng, so sánh từng khóa `(business_date, store_id, currency_code)` để tìm nhóm lệch. Với read model đơn hàng, kiểm tra version, trạng thái và các trường quan trọng trên tập mẫu hoặc toàn bộ dữ liệu tùy quy mô.

## 13. Thiết kế chỉ mục và lưu trữ cho projection

Projection được tối ưu cho các truy vấn đọc đã biết. Chọn chỉ mục theo điều kiện lọc, thứ tự sắp xếp và grain:

- Đặt khóa định danh/unique constraint theo grain để chống dòng trùng.
- Tạo index cho các bộ lọc thường dùng; equality thường đứng trước range trong composite index nếu phù hợp với workload.
- Chỉ đưa cột cần thiết vào covering index; tránh index quá rộng.
- Partition theo thời gian khi cần pruning, retention hoặc rebuild theo kỳ.
- Chọn kiểu dữ liệu đủ chính xác và phù hợp với miền giá trị.
- Lưu `source_version`, `refreshed_at` và trạng thái xử lý nếu chúng giúp vận hành.

Không sao chép mọi cột nguồn sang projection theo thói quen. Mỗi cột tăng dung lượng, chi phí ghi và khả năng phát sinh bất đồng bộ. Chỉ lưu trường cần cho đường đọc mục tiêu hoặc cần để xử lý cập nhật.

## 14. Theo dõi hoạt động cập nhật

Một projection nhanh khi đọc nhưng liên tục bị trễ hoặc sai lệch không phải giải pháp tốt. Cần theo dõi cả tốc độ đọc và chất lượng pipeline cập nhật.

| Nhóm | Chỉ số cần theo dõi | Ý nghĩa |
|---|---|---|
| Độ mới | `now - refreshed_at`, source watermark lag | Projection đang trễ bao lâu |
| Backlog | Số event/batch đang chờ và tuổi event cũ nhất | Consumer có theo kịp nguồn không |
| Throughput | Event/second, rows/second, batch duration | Năng lực xử lý thay đổi |
| Lỗi | Retry, dead-letter, schema mismatch, parse failure | Tỷ lệ thay đổi không được áp dụng |
| Idempotency | Event trùng, duplicate key, số lần replay | Cơ chế chống xử lý lặp có hoạt động không |
| Nhất quán | Chênh lệch nguồn-projection, version gap | Dữ liệu dẫn xuất có đúng không |
| Tài nguyên | CPU, I/O, log, lock wait, memory, storage | Chi phí duy trì projection |
| Đọc | p95/p99, logical reads, cache hit, timeout | Projection có cải thiện đường đọc không |

Đặt cảnh báo theo SLO, ví dụ watermark chậm quá giới hạn, backlog tăng liên tục, projection version thấp hơn nguồn quá lâu hoặc đối soát phát hiện chênh lệch. Cần có dashboard riêng cho pipeline và đường truy vấn.

## 15. Ví dụ chọn mô hình cho màn hình đơn hàng

Màn hình danh sách cần hiển thị mã đơn, tên khách hàng, trạng thái thanh toán, tổng tiền và thời điểm cập nhật. Dữ liệu chuẩn nằm ở `orders`, `customers`, `order_items` và `payments`. Nếu mỗi request phải join và aggregate tất cả bảng, chi phí có thể cao khi danh sách được gọi thường xuyên.

Một read model có thể là:

```sql
CREATE TABLE order_read_model (
    order_id          bigint PRIMARY KEY,
    customer_name     text NOT NULL,
    order_status      text NOT NULL,
    payment_status    text NOT NULL,
    item_count        integer NOT NULL,
    order_total       numeric(20, 2) NOT NULL,
    paid_total        numeric(20, 2) NOT NULL,
    source_version    bigint NOT NULL,
    refreshed_at      timestamptz NOT NULL
);

CREATE INDEX ix_order_read_model_status_updated
ON order_read_model (order_status, refreshed_at DESC, order_id DESC);
```

Nếu mọi bảng nguồn cùng database và cần cập nhật ngay, transaction nghiệp vụ có thể cập nhật read model đồng bộ. Nếu dữ liệu được đưa sang search engine hoặc database riêng, có thể ghi outbox cùng transaction nguồn và để consumer xây document.

Khi khách đổi tên, cần quyết định màn hình đơn hàng cũ hiển thị tên hiện tại hay tên tại thời điểm đặt hàng. Hai semantics khác nhau:

- **Tên hiện tại:** event đổi tên khách cần cập nhật mọi order projection liên quan, có thể tạo fan-out lớn.
- **Tên tại thời điểm đặt hàng:** lưu snapshot tên trong nguồn đơn hàng ngay lúc tạo; thay đổi hồ sơ khách không cập nhật đơn cũ.

Đây là quyết định mô hình dữ liệu, không chỉ là quyết định hiệu năng. Nếu cần tên lịch sử, không nên để projection tự lấy tên hiện tại từ bảng khách hàng rồi gọi đó là tên tại thời điểm giao dịch.

Khi một đơn có thêm dòng hàng, `order_total` cần được tính lại hoặc cập nhật delta theo quy tắc thuế/chiết khấu. Khi thanh toán một phần, `paid_total` tăng theo payment đã quyết toán. Khi hoàn tiền, `paid_total` hoặc `refunded_total` thay đổi theo định nghĩa rõ ràng. Consumer cần version và event id để tránh event cũ hoặc trùng làm sai projection.

## 16. Những sai lầm thường gặp

- **Không xác định nguồn chuẩn:** nhiều bảng cùng được sửa và không rõ bảng nào có thẩm quyền.
- **Không mô tả grain:** dữ liệu bị cộng trùng hoặc không biết khóa duy nhất là gì.
- **Chỉ xử lý insert:** update, delete, hủy, hoàn tiền và thay đổi dimension bị bỏ sót.
- **Publish message sau commit mà không có outbox:** tiến trình có thể dừng sau khi nguồn commit nhưng trước khi phát event.
- **Cho rằng broker giao message đúng một lần:** consumer vẫn phải xử lý retry và giao nhận lặp.
- **Chống trùng nhưng không xử lý sai thứ tự:** event cũ có thể ghi đè trạng thái mới.
- **Dùng timestamp làm version:** đồng hồ lệch hoặc timestamp trùng có thể làm sai thứ tự.
- **Cộng delta không idempotent:** retry có thể cộng nhiều lần.
- **Cập nhật counter bằng đọc-sửa-ghi không khóa:** transaction đồng thời có thể làm mất cập nhật.
- **Không có rebuild/backfill:** projection sai không thể tái tạo đáng tin cậy.
- **Chuyển traffic trước khi consumer bắt kịp:** người dùng có thể đọc projection thiếu dữ liệu.
- **Chỉ đo tốc độ đọc:** bỏ qua backlog, độ mới, chi phí ghi và đối soát.
- **Sao chép quá nhiều cột:** projection trở nên rộng, đắt và khó đồng bộ.

## 17. Quy trình thiết kế và triển khai

1. **Đo đường đọc hiện tại:** xác định truy vấn tốn kém, tần suất, số dòng, join, CPU, I/O và mục tiêu độ trễ.
2. **Chọn đường đọc cần phục vụ:** danh sách, chi tiết, tìm kiếm, counter hay báo cáo.
3. **Xác định nguồn chuẩn:** liệt kê bảng/stream có thẩm quyền và quyền cập nhật.
4. **Định nghĩa grain và khóa:** mô tả một dòng đại diện cho điều gì và cách bảo đảm unique.
5. **Định nghĩa trường dẫn xuất:** công thức, `NULL`, tiền tệ, múi giờ, trạng thái và quy tắc lịch sử.
6. **Chọn cơ chế cập nhật:** đồng bộ, outbox, CDC, batch hoặc kết hợp.
7. **Thiết kế idempotency và thứ tự:** event id, version, checkpoint, retry và xử lý dead-letter.
8. **Xử lý mọi loại thay đổi:** insert, update, delete, chuyển grain và dữ liệu đến muộn.
9. **Thiết kế rebuild/backfill:** snapshot, vị trí CDC, staging, replay, đối soát và cutover.
10. **Tạo constraint và index:** bảo vệ grain và hỗ trợ truy vấn đọc.
11. **Benchmark tải hỗn hợp:** đo đọc, ghi, backlog, độ mới, CPU, I/O, lock và dung lượng.
12. **Triển khai có kiểm soát:** chạy song song, so sánh kết quả, chuyển traffic theo bước và giữ khả năng rollback.
13. **Vận hành liên tục:** cảnh báo độ trễ, lỗi, version gap, sai lệch và khả năng rebuild.

## 18. Checklist hợp đồng cập nhật dữ liệu dẫn xuất

- [ ] Đã xác định rõ nguồn chuẩn và chủ sở hữu dữ liệu.
- [ ] Đã mô tả grain, khóa chính và unique constraint.
- [ ] Đã định nghĩa công thức và semantics của từng trường dẫn xuất.
- [ ] Đã quyết định dữ liệu cập nhật đồng bộ hay bất đồng bộ và độ trễ cho phép.
- [ ] Đã chọn transaction, outbox, CDC hoặc batch phù hợp.
- [ ] Đã có event id/batch id để chống xử lý trùng.
- [ ] Đã có version hoặc cơ chế bảo đảm thứ tự khi event đến sai thứ tự.
- [ ] Đã xử lý insert, update, delete, chuyển nhóm và dữ liệu đến muộn.
- [ ] Đã bảo đảm cập nhật counter/projection không mất dữ liệu khi có ghi đồng thời.
- [ ] Đã có checkpoint, retry, dead-letter và quy trình replay.
- [ ] Đã có snapshot/backfill/rebuild và đối soát với nguồn.
- [ ] Đã xác định cách publish dữ liệu và mức nhất quán mà API công bố.
- [ ] Đã đo read latency, write throughput, pipeline lag, backlog và chi phí tài nguyên.
- [ ] Đã có kế hoạch rollback hoặc chuyển về nguồn đọc cũ khi projection sai.

Bảng tổng hợp và dữ liệu dẫn xuất giúp giảm công việc trên đường đọc bằng cách lưu kết quả theo grain phù hợp. Lợi ích chỉ bền vững khi hệ thống xác định rõ nguồn chuẩn, quy tắc tính, cơ chế cập nhật, tính idempotent, thứ tự sự kiện, khả năng rebuild và đối soát. Hãy coi hợp đồng cập nhật là một phần của mô hình dữ liệu ngay từ đầu; khi đó projection vừa có thể phục vụ truy vấn nhanh, vừa duy trì được tính đúng đắn trong suốt vòng đời dữ liệu.
