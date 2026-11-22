# Khóa được cập nhật nhiều, bộ đếm dùng chung và giới hạn thông lượng ghi

Một hệ thống có thể đọc hàng triệu bản ghi mỗi phút nhưng vẫn bị giới hạn bởi một hàng duy nhất được cập nhật liên tục. Ví dụ thường gặp là bộ đếm lượt xem, số thứ tự dùng chung, số lượng tồn kho của một SKU, trạng thái một tác vụ, số dư tài khoản hoặc một hàng tổng hợp lưu số sự kiện. Khi nhiều transaction cùng ghi vào một khóa, chúng phải phối hợp để bảo đảm tính đúng đắn. Các transaction có thể xếp hàng chờ khóa, chờ latch trên cấu trúc lưu trữ hoặc tranh chấp ở trang chỉ mục và transaction log.

Một hàng hoặc một vùng chỉ mục nhận lượng ghi tập trung thường được gọi là **hot spot**. Hot spot có thể làm thông lượng ghi chững lại dù CPU tổng thể chưa đạt tối đa. Tăng số kết nối hoặc số worker đôi khi chỉ làm hàng đợi dài hơn, tăng thời gian chờ và p95/p99 mà không tăng số giao dịch hoàn tất.

Trong module **DATABASE_PERFORMANCE**, cần nhận diện khóa được cập nhật nhiều, phân biệt lock contention với latch/page contention, hiểu vì sao bộ đếm dùng chung tạo giới hạn tuần tự, và chọn cách phân phối hoặc gom thao tác ghi phù hợp. Mục tiêu là giữ đúng quy tắc nghiệp vụ trong khi giảm thời gian tranh chấp và tăng thông lượng ghi đo được.

## 1. Hot row và giới hạn tuần tự

Giả sử mọi yêu cầu tăng một bộ đếm tổng hợp trong cùng một hàng:

```sql
UPDATE system_counter
SET counter_value = counter_value + 1
WHERE counter_name = 'page_views';
```

Phép cập nhật phải bảo đảm hai transaction không ghi đè kết quả của nhau. Cơ sở dữ liệu thường khóa hàng hoặc khóa tương ứng trong quá trình cập nhật và giữ khóa đến thời điểm thích hợp theo transaction. Nếu nhiều phiên cùng cập nhật đúng hàng này, chúng phải chờ nhau theo một thứ tự được kiểm soát.

Một hàng có thể trở thành điểm tuần tự hóa (*serialization point*): dù các transaction khác nhau về người dùng hoặc máy chủ ứng dụng, chúng vẫn phải lần lượt cập nhật cùng một tài nguyên. Thêm worker có thể tăng số transaction đang chờ, nhưng không làm hàng đó xử lý song song vô hạn.

### Ví dụ hàng tồn kho nóng

Một sản phẩm bán chạy có một hàng tồn kho:

```sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id
  AND available_quantity >= :quantity;
```

Điều kiện kiểm tra và cập nhật trong cùng câu lệnh giúp tránh lỗi đọc số lượng rồi ghi lại bằng một giá trị cũ. Tuy nhiên, tất cả yêu cầu mua cùng `product_id` vẫn tranh chấp trên hàng tồn kho đó. Đây có thể là giới hạn cần thiết để không bán vượt số lượng hiện có.

### Dấu hiệu của hot row

- Nhiều transaction chờ cùng một khóa hoặc cùng một hàng.
- Một câu `UPDATE` rất ngắn nhưng thời gian chờ trước khi hoàn tất cao.
- Throughput không tăng khi tăng số worker; độ trễ và số phiên chờ lại tăng.
- Một số khóa, tenant, tài khoản, SKU hoặc bộ đếm nhận phần lớn thao tác ghi.
- CPU chưa bão hòa nhưng transaction duration, lock wait hoặc wait event tăng.
- Hệ thống có nhiều retry, deadlock hoặc timeout tập trung quanh một đối tượng.

Không phải mọi transaction chậm đều do hot row. I/O chậm, log flush, trigger, foreign key, index maintenance, mạng hoặc transaction giữ khóa quá lâu cũng có thể tạo hàng đợi. Cần quan sát đúng tài nguyên đang bị tranh chấp.

## 2. Phân biệt lock contention, latch contention và index page contention

Ba dạng tranh chấp có liên quan nhưng không giống nhau.

| Dạng tranh chấp | Bảo vệ điều gì? | Dấu hiệu thường gặp | Hướng điều tra |
|---|---|---|---|
| Lock contention | Dữ liệu logic và quy tắc đồng thời giữa transaction | Transaction chờ row/key/page/table lock, blocking chain | Xác định blocker, câu lệnh, thời gian giữ khóa và khóa nóng |
| Latch contention | Cấu trúc bộ nhớ nội bộ cần được cập nhật an toàn trong thời gian ngắn | Wait trên latch hoặc buffer/page structure | Xác định trang/cấu trúc nóng, mẫu ghi và cách phân phối truy cập |
| Index/page contention | Các thao tác ghi tập trung vào cùng trang hoặc vùng chỉ mục; có thể biểu hiện thành latch wait hoặc lock wait tùy engine | Trang cuối của index tăng tuần tự, page split hoặc insert hotspot | Kiểm tra khóa chỉ mục, thứ tự ghi, phân vùng và wait cụ thể |

**Lock** thường gắn với transaction và được giữ trong một khoảng thời gian để bảo vệ tính nhất quán logic. **Latch** thường là cơ chế đồng bộ ngắn hạn để bảo vệ cấu trúc bộ nhớ như page trong buffer pool. Latch không thay thế transaction lock và thường không được người dùng quản lý trực tiếp bằng câu SQL.

Một hot row có thể gây lock contention. Một khóa tăng tuần tự có thể khiến nhiều thao tác chèn tập trung vào trang cuối của B-tree, tạo page/latch contention ngay cả khi các hàng mới khác nhau. Hai tình huống cần biện pháp khác nhau: phân phối khóa hàng có thể giảm row lock hotspot; thay đổi cách sinh hoặc tổ chức index có thể giảm tranh chấp trang.

### Vì sao transaction ngắn vẫn có thể chờ lâu?

Một câu cập nhật chỉ mất vài mili giây khi chạy một mình nhưng có thể chờ hàng trăm mili giây khi nhiều phiên cùng cập nhật một hàng. Thời gian thực thi quan sát được gồm thời gian chờ lấy quyền truy cập, thời gian xử lý và thời gian commit. Nếu chỉ nhìn CPU của câu SQL, nguyên nhân có thể bị bỏ sót.

## 3. Bộ đếm dùng chung và phép cập nhật nguyên tử

### Tránh mẫu đọc rồi ghi bằng giá trị cũ

Mẫu sau dễ gây mất cập nhật nếu không có khóa hoặc cơ chế đồng thời phù hợp:

```sql
SELECT counter_value
FROM system_counter
WHERE counter_name = 'page_views';

-- Ứng dụng cộng thêm 1 rồi gửi giá trị mới.
UPDATE system_counter
SET counter_value = :old_value_plus_one
WHERE counter_name = 'page_views';
```

Hai phiên có thể cùng đọc `100`, rồi cả hai cùng ghi `101`; một lần tăng bị mất. Đây là lỗi lost update nếu transaction và isolation không ngăn được tình huống đó.

Với bộ đếm, dùng phép cập nhật nguyên tử tại database:

```sql
UPDATE system_counter
SET counter_value = counter_value + 1
WHERE counter_name = 'page_views';
```

Một số hệ quản trị hỗ trợ trả lại giá trị mới bằng `RETURNING`, `OUTPUT` hoặc cơ chế tương đương. Phép cập nhật nguyên tử loại bỏ khoảng trống giữa đọc và ghi ở ứng dụng, nhưng không loại bỏ tranh chấp: các transaction vẫn phải cập nhật cùng một hàng.

### Cập nhật nhiều đơn vị trong một lần

Nếu ứng dụng đã gom được số sự kiện, có thể tăng bộ đếm theo batch:

```sql
UPDATE system_counter
SET counter_value = counter_value + :delta
WHERE counter_name = 'page_views';
```

Thay vì gửi 100 lần cập nhật tăng một đơn vị, ứng dụng gửi một lần tăng 100 đơn vị. Cách này giảm số round trip, số lần commit và số lần giành khóa. Nó phù hợp với số liệu tổng hợp có thể chấp nhận độ trễ cập nhật hoặc có một tầng gom sự kiện đáng tin cậy.

Nếu mỗi lần tăng phải được xác nhận ngay và có ý nghĩa nghiệp vụ riêng, gom batch có thể thay đổi ngữ nghĩa hoặc làm mất dữ liệu khi worker gặp sự cố. Cần thiết kế buffer bền vững, retry idempotent và đối soát.

### Dùng UPSERT có kiểm soát

Khi bộ đếm được tạo theo khóa, có thể dùng cơ chế upsert để tạo hàng nếu chưa có hoặc tăng giá trị nếu đã có. Cú pháp khác nhau giữa PostgreSQL (`ON CONFLICT`), MySQL (`ON DUPLICATE KEY UPDATE`), SQL Server (`UPDATE`/`INSERT` với transaction hoặc mẫu an toàn phù hợp) và Oracle (`MERGE` hoặc thao tác tương đương). Dù cú pháp nào, nhiều phiên cùng cập nhật một khóa vẫn có thể tranh chấp.

Không dùng `SELECT MAX(id) + 1` để sinh số thứ tự trong workload đồng thời. Nhiều transaction có thể đọc cùng một giá trị lớn nhất và sinh cùng ID. Hãy dùng identity, sequence hoặc cơ chế cấp phát khóa phù hợp của hệ quản trị.

## 4. Phân mảnh bộ đếm (striped hoặc sharded counter)

Nếu một bộ đếm duy nhất trở thành điểm nóng, có thể chia nó thành nhiều bucket. Mỗi worker hoặc một hàm phân phối chọn một bucket để cập nhật. Khi cần tổng số, hệ thống cộng các bucket lại.

Ví dụ cấu trúc:

```sql
CREATE TABLE counter_bucket (
    counter_name VARCHAR(100) NOT NULL,
    bucket_id    INTEGER NOT NULL,
    counter_value BIGINT NOT NULL,
    PRIMARY KEY (counter_name, bucket_id)
);
```

Một lần ghi chọn một bucket:

```sql
UPDATE counter_bucket
SET counter_value = counter_value + :delta
WHERE counter_name = :counter_name
  AND bucket_id = :bucket_id;
```

Đọc tổng:

```sql
SELECT SUM(counter_value) AS total_value
FROM counter_bucket
WHERE counter_name = :counter_name;
```

Nếu có 64 bucket và thao tác ghi được phân phối tương đối đều, các cập nhật có thể diễn ra trên nhiều hàng độc lập thay vì cùng một hàng. Mức cải thiện phụ thuộc phân bố tải, số bucket, chỉ mục, engine và cách đọc tổng.

### Chọn bucket như thế nào?

- **Theo worker/shard:** mỗi worker có bucket ổn định; dễ phân phối nhưng cần quản lý vòng đời worker và bucket.
- **Theo tenant hoặc nhóm nghiệp vụ:** phù hợp khi tải tự nhiên phân bố theo tenant; tenant quá lớn vẫn có thể trở thành hot bucket.
- **Theo hash của event/key:** phân phối đều nếu khóa đủ đa dạng; cần bảo đảm mọi lần retry của cùng một thao tác cập nhật đúng bucket mong muốn.
- **Theo thời gian:** bucket theo cửa sổ thời gian có thể giúp truy vấn và lưu trữ, nhưng thời điểm hiện tại thường trở thành bucket nóng nếu mọi ghi cùng đổ vào một bucket.

Không nên chọn bucket ngẫu nhiên nếu cần xử lý idempotency hoặc chống ghi trùng mà không có mã sự kiện riêng. Một sự kiện retry vào bucket khác có thể bị cộng hai lần. Hãy gắn event ID hoặc khóa idempotency và xác định quy tắc phân phối ổn định.

### Đánh đổi khi phân mảnh

| Lợi ích | Chi phí và giới hạn |
|---|---|
| Giảm số transaction cùng ghi một hàng | Tăng số hàng và logic quản lý bucket |
| Có thể tăng throughput ghi | Đọc tổng cần aggregate nhiều bucket |
| Giảm hot row nếu phân phối đều | Bucket lệch tải vẫn có thể nóng |
| Cho phép gom và cập nhật theo nhóm | Cần xử lý retry, rollover và đối soát |
| Có thể mở rộng theo tenant/worker | Tăng độ phức tạp vận hành và quan sát |

Striped counter phù hợp với lượt xem, số sự kiện, metric hoặc bộ đếm tổng hợp. Nó không tự động phù hợp với số dư tài khoản, tồn kho chính xác hoặc giới hạn quota cần kiểm tra nguyên tử trên một giá trị duy nhất. Với dữ liệu có ràng buộc không được vượt ngưỡng, phân mảnh phải đi kèm mô hình phân bổ hạn mức có chứng minh tính đúng.

## 5. Chọn mô hình cho dữ liệu cần tính đúng tuyệt đối

Không phải mọi hot row đều có thể phân mảnh. Một số quy tắc nghiệp vụ cần một điểm quyết định nguyên tử.

### Số dư tài khoản

Hai giao dịch đồng thời cùng rút tiền từ một tài khoản cần bảo đảm số dư không âm và không mất cập nhật. Một cách là cập nhật có điều kiện:

```sql
UPDATE account_balance
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng. Nếu một hàng được cập nhật, khoản rút được chấp nhận; nếu không, số dư không đủ hoặc tài khoản không tồn tại. Cần xác định thêm trạng thái tài khoản, tiền tệ, giới hạn và ghi ledger trong cùng transaction.

Đây vẫn là hàng nóng khi một tài khoản nhận nhiều giao dịch. Các lựa chọn như hàng đợi theo tài khoản, xử lý tuần tự theo key, giới hạn concurrency hoặc mô hình ledger append-only có thể phù hợp hơn việc cố chia một số dư thành nhiều hàng độc lập.

### Tồn kho và quota

Với tồn kho, có thể phân bổ số lượng theo kho, vùng hoặc reservation pool nếu nghiệp vụ cho phép. Ví dụ, thay vì một hàng tồn kho toàn cục cho mọi yêu cầu, có thể phân chia lượng hàng có thể bán theo fulfillment center. Nhưng phải có quy trình chuyển lượng tồn giữa các pool và bảo đảm tổng phân bổ không vượt tồn kho thực.

Với quota, có thể cấp trước một phần hạn mức cho từng worker hoặc partition. Mỗi worker tiêu thụ hạn mức cục bộ, định kỳ xin cấp thêm. Cách này giảm cập nhật bộ đếm toàn cục nhưng có thể giữ lại quota chưa dùng ở một worker. Cần xác định giới hạn sai lệch, hành vi khi worker chết và cơ chế thu hồi.

### Ledger hoặc event log

Nếu cần lịch sử đầy đủ, lưu các sự kiện tăng/giảm theo dạng append-only rồi tổng hợp số dư hoặc số liệu đọc có thể là một lựa chọn. Ghi append thường phân tán tốt hơn cập nhật một hàng tổng hợp, nhưng việc đọc số dư tức thời cần projection hoặc snapshot và có thể có độ trễ. Với nghiệp vụ tài chính, ledger phải có quy tắc bất biến, khóa idempotency, thứ tự xử lý và đối soát chặt chẽ.

## 6. Hot spot trên chỉ mục và khóa tăng tuần tự

Tranh chấp ghi không chỉ xuất phát từ một hàng logic. Một B-tree index có khóa tăng tuần tự như identity hoặc timestamp có thể khiến nhiều thao tác insert cùng ghi vào trang lá cuối cùng. Các hàng khác nhau vẫn có thể tranh chấp trên cùng trang vật lý.

Ví dụ:

```sql
CREATE TABLE event_log (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

Nếu tốc độ insert rất cao, trang cuối của primary key index có thể nhận lượng ghi tập trung. Một số engine có cơ chế tối ưu cho insert tuần tự; trong trường hợp khác, wait trên latch/page có thể xuất hiện.

### Các hướng giảm tranh chấp trang

- Đánh giá index nào thật sự cần thiết; mỗi index phụ tạo thêm thao tác ghi.
- Phân vùng hoặc phân phối khóa theo tenant/shard nếu mô hình dữ liệu cho phép.
- Xem xét thiết kế index và fill factor/page split theo hệ quản trị, sau khi đo.
- Với workload append-only, cân nhắc phân vùng theo thời gian để giới hạn phạm vi bảo trì và truy vấn.
- Dùng batch insert hoặc bulk load khi phù hợp để giảm overhead mỗi hàng.
- Kiểm tra sequence/identity cache và cơ chế cấp phát ID thay vì tự tạo ID bằng truy vấn.

Không nên thay khóa tuần tự bằng UUID ngẫu nhiên một cách máy móc. Khóa ngẫu nhiên có thể giảm tập trung ở trang cuối nhưng làm tăng phân mảnh, page split, kích thước index và I/O ngẫu nhiên. Có thể cân nhắc ID có thứ tự theo thời gian hoặc phân phối theo shard nếu phù hợp với yêu cầu toàn cục và hệ quản trị.

### Sequence không phải bộ đếm nghiệp vụ

Sequence/identity phù hợp để cấp ID duy nhất, nhưng thường không bảo đảm dãy số liên tục không có khoảng trống. Rollback, cache, lỗi tiến trình hoặc cơ chế cấp phát có thể làm mất một số giá trị đã cấp. Nếu nghiệp vụ yêu cầu số hóa đơn liên tục theo quy định, cần thiết kế cơ chế riêng với khóa và kiểm soát transaction; không nên giả định sequence tự đáp ứng yêu cầu gapless.

## 7. Giảm thời gian giữ khóa

Ngay cả khi phải cập nhật một hàng nóng, có thể giảm thời gian mỗi transaction giữ tài nguyên bằng cách rút ngắn critical section.

- Không gọi API bên ngoài, gửi email hoặc chờ người dùng trong transaction đang giữ khóa.
- Thực hiện tính toán không phụ thuộc database trước khi mở transaction.
- Chỉ đọc và cập nhật các hàng cần thiết; tránh truy vấn rộng trước khi ghi.
- Commit sớm sau khi các thay đổi nguyên tử hoàn tất.
- Không dùng transaction dài để xử lý hàng loạt nếu có thể chia thành batch an toàn.
- Giữ thứ tự lấy khóa nhất quán giữa các luồng để giảm nguy cơ deadlock.
- Đặt timeout hợp lý và xử lý lỗi chờ khóa ở ứng dụng.

Ví dụ không tốt:

```text
BEGIN TRANSACTION
  khóa hàng tồn kho
  gọi dịch vụ thanh toán qua mạng
  chờ phản hồi vài giây
  cập nhật đơn hàng
COMMIT
```

Trong thời gian gọi mạng, khóa có thể vẫn bị giữ. Một thiết kế tốt hơn tách bước xử lý bên ngoài transaction, sau đó dùng transaction ngắn để xác nhận thay đổi database; nếu cần điều phối nhiều hệ thống, dùng state machine, outbox hoặc saga với trạng thái rõ ràng.

Tuy nhiên, không được tách transaction theo cách làm mất tính nguyên tử mà nghiệp vụ cần. Với cập nhật số dư hoặc tồn kho, phần kiểm tra và ghi quyết định phải nằm trong cùng một đơn vị đồng thời phù hợp.

## 8. Batching, gom sự kiện và cập nhật bất đồng bộ

### Batch update

Gom nhiều thay đổi thành một câu lệnh có thể giảm round trip, parse/execute overhead và số lần commit. Ví dụ:

```sql
UPDATE counter_bucket
SET counter_value = counter_value + :delta
WHERE counter_name = :name
  AND bucket_id = :bucket;
```

Một batch lớn hơn giảm số lần lấy khóa nhưng có thể giữ khóa lâu hơn, tạo log lớn và làm các transaction khác chờ lâu. Cần thử nhiều kích thước batch và đo throughput, latency, log bytes, lock duration và replication lag.

### Gom sự kiện trong bộ nhớ

Ứng dụng có thể gom nhiều lượt tăng trong một khoảng ngắn rồi ghi `delta` một lần. Nếu dữ liệu chỉ phục vụ thống kê và chấp nhận eventual consistency, cách này giảm tải database. Nhưng buffer trong bộ nhớ có thể mất khi tiến trình chết.

Đối với sự kiện không được phép mất, dùng hàng đợi bền vững, log sự kiện hoặc outbox. Worker đọc theo batch, ghi idempotent và xác nhận thông điệp sau khi transaction thành công. Cần có cơ chế retry, dead-letter, replay và đối soát số sự kiện.

### Projection bất đồng bộ

Một hệ thống có thể lưu sự kiện nguồn bất biến, sau đó cập nhật bảng tổng hợp theo luồng. Bảng tổng hợp phục vụ truy vấn nhanh nhưng có độ trễ so với dữ liệu nguồn. Cần xác định SLA freshness, cách xử lý sự kiện đến muộn, thứ tự sự kiện và khả năng rebuild projection.

Không nên dùng eventual consistency cho quyết định cần chính xác tức thời như chấp nhận giao dịch vượt hạn mức, trừ khi có cơ chế phân bổ hoặc reservation bảo đảm giới hạn.

## 9. Cơ chế theo hệ quản trị

Tên wait và cách triển khai khác nhau, nhưng các nguyên tắc nhận diện hot row, giảm thời gian giữ khóa và phân phối tải vẫn áp dụng.

### PostgreSQL

PostgreSQL dùng row-level locks cho nhiều thao tác cập nhật và MVCC để các reader không nhất thiết chặn writer theo cùng cách như một số engine khác. Nhiều transaction cập nhật cùng một hàng vẫn phải tuần tự hóa; phiên sau có thể chờ transaction trước hoàn tất. Có thể điều tra bằng `pg_stat_activity`, `pg_locks`, wait events và truy vấn đang chặn.

Ví dụ tăng bộ đếm và trả giá trị mới:

```sql
UPDATE system_counter
SET counter_value = counter_value + 1
WHERE counter_name = 'page_views'
RETURNING counter_value;
```

Sequence trong PostgreSQL có thể dùng cache để giảm đồng bộ khi cấp giá trị. Sequence không bảo đảm gapless và giá trị đã cấp không được hoàn lại khi transaction rollback. Với hot update, cần xem dead tuples, vacuum, HOT update eligibility, fillfactor và index có phụ thuộc cột đang thay đổi hay không. Nếu cập nhật cột xuất hiện trong index, cơ hội HOT update có thể giảm.

### SQL Server

SQL Server có lock manager cho khóa transaction và latch cho cấu trúc bộ nhớ. Một số wait thường được xem xét gồm `LCK_M_*` cho lock, `PAGELATCH_*` cho latch trên page trong bộ nhớ và `PAGEIOLATCH_*` cho chờ I/O page; cần đọc đúng loại wait và tài nguyên liên quan. `PAGELATCH_EX` trên trang cuối index có thể gợi ý insert page contention, nhưng phải xác định object/index/page cụ thể.

Có thể dùng Query Store, actual execution plan, `sys.dm_exec_requests`, `sys.dm_tran_locks` và các DMV liên quan để xác định blocker, wait và câu lệnh. Không bật trace hoặc thu thập dữ liệu nặng kéo dài mà chưa đánh giá overhead.

Sequence hỗ trợ `CACHE` và các tùy chọn cấp phát; cache có thể giảm chi phí lấy số nhưng không tạo dãy liên tục. Với bảng insert tuần tự, xem xét wait latch, page split, thiết kế index và các tùy chọn phù hợp phiên bản thay vì đổi sang khóa ngẫu nhiên ngay.

### MySQL/InnoDB

InnoDB dùng record locks, gap/next-key locks và cơ chế latch nội bộ. Tranh chấp có thể đến từ cập nhật cùng record, range locking ở isolation level cao hơn hoặc insert tập trung vào vùng index. Có thể xem `performance_schema`, `sys` schema và `SHOW ENGINE INNODB STATUS` để tìm transaction chờ, deadlock và lock wait.

InnoDB có các chế độ xử lý `AUTO_INCREMENT` khác nhau theo phiên bản và cấu hình. Với insert đồng thời, cần kiểm tra `innodb_autoinc_lock_mode` và đặc điểm câu lệnh insert. Thay đổi chế độ có ảnh hưởng đến concurrency và khả năng tái lập thứ tự cấp ID trong một số dạng insert; hãy xem tài liệu đúng phiên bản và replication mode.

### Oracle Database

Oracle dùng khóa hàng và cơ chế đồng bộ nội bộ. Nhiều session cập nhật cùng một hàng có thể chờ TX enqueue; tranh chấp cấu trúc block có thể xuất hiện dưới các wait như `buffer busy waits` hoặc các sự kiện liên quan tùy phiên bản và loại workload. Có thể dùng AWR/ASH nếu được cấp phép, `V$SESSION`, `V$LOCK`, `V$SQL` và `DBMS_XPLAN` để xác định session chờ và đối tượng liên quan.

Sequence với `CACHE` thường giảm chi phí cấp số khi có nhiều session. `NOCACHE` có thể tăng chi phí đồng bộ và không nên được dùng chỉ để cố đạt dãy không có khoảng trống; sequence vẫn không phải cơ chế gapless. Với hot block, cần xác định đó là hàng dữ liệu, index leaf block, segment header hay cấu trúc khác trước khi thay đổi.

## 10. Chẩn đoán hot spot theo quy trình

Một quy trình điều tra hiệu quả cần nối wait với câu SQL, khóa và đối tượng cụ thể.

1. **Xác định triệu chứng:** throughput ghi có chững lại không, p95/p99 tăng ở thao tác nào, lỗi timeout/deadlock có tăng không?
2. **Tìm wait chính:** lock wait, latch wait, I/O, log flush, CPU hay network? Tỷ lệ thời gian chờ so với thời gian chạy là bao nhiêu?
3. **Tìm blocker hoặc tài nguyên nóng:** transaction nào giữ khóa lâu, hàng/index/page nào nhận nhiều lần ghi?
4. **Gắn với query fingerprint:** câu lệnh nào cập nhật đối tượng, với tần suất và tham số nào?
5. **Đo phân bố khóa:** một khóa duy nhất chiếm bao nhiêu phần trăm thao tác, hay tải phân bố đều?
6. **Kiểm tra transaction:** có gọi mạng, xử lý lâu hoặc cập nhật nhiều bảng trước commit không?
7. **Kiểm tra index:** có nhiều index phải cập nhật, index tuần tự có trang cuối nóng, page split hoặc lock range không?
8. **Đặt giả thuyết:** rút ngắn transaction, batch, striped counter, sequence cache, index change hay queue theo khóa?
9. **Thử có kiểm soát:** giữ nguyên dữ liệu và tải, thay đổi một yếu tố mỗi lần.
10. **Đo lại và kiểm tra tính đúng:** throughput, latency, wait, retry, lost update, duplicate và invariant nghiệp vụ.

### Chỉ số nên theo dõi

| Chỉ số | Cách diễn giải |
|---|---|
| Transactions/second | Số giao dịch hoàn tất thực tế, không phải số request được gửi |
| Lock wait time và blocked sessions | Mức độ chờ khóa và số phiên bị ảnh hưởng |
| Latch/page wait | Tranh chấp cấu trúc lưu trữ hoặc buffer page |
| p50/p95/p99 | Phân bố độ trễ, đặc biệt ở đuôi khi hàng đợi dài |
| Deadlock/timeout/retry rate | Chi phí phối hợp và lỗi dưới tải đồng thời |
| Log bytes/flush latency | Giới hạn ghi log và commit durability |
| CPU, IOPS, storage latency | Phân biệt nghẽn tài nguyên với điểm tuần tự hóa |
| Hot-key distribution | Tỷ trọng thao tác tập trung vào một số khóa |

Đo throughput theo số giao dịch commit thành công. Một hệ thống có thể nhận 10.000 request/giây nhưng chỉ commit 2.000 transaction/giây; phần còn lại đang chờ hoặc retry không phải năng lực xử lý hoàn tất.

## 11. Thiết kế kiểm thử tải cho hot row

Kiểm thử chỉ với một client không thể bộc lộ tranh chấp. Cần tăng dần số worker và kiểm tra đường cong throughput/latency.

Một kịch bản thử nghiệm nên có:

- Một nhóm worker cập nhật cùng một khóa để tạo hot row có chủ đích.
- Một nhóm worker cập nhật các khóa phân tán để làm đối chứng.
- Các mức concurrency tăng dần, ví dụ 1, 4, 8, 16, 32, 64 worker tùy năng lực môi trường.
- Cùng số lượng thao tác và cùng mức durability để so sánh công bằng.
- Đo thời gian transaction, wait, throughput commit, p95/p99 và lỗi.
- Chạy cả warm-up và giai đoạn đo ổn định; tách ảnh hưởng cache lạnh.
- Kiểm tra tổng giá trị cuối để phát hiện mất cập nhật hoặc cộng trùng.

Nếu throughput tăng đến một điểm rồi gần như phẳng trong khi p99 và lock wait tiếp tục tăng, đó là dấu hiệu một tài nguyên tuần tự đang giới hạn hệ thống. Nếu throughput phẳng cùng CPU 100%, nguyên nhân có thể là CPU thay vì hot row. Nếu log flush chiếm phần lớn thời gian, thêm bucket có thể không giải quyết được giới hạn commit log.

## 12. Chọn biện pháp theo loại dữ liệu

| Loại dữ liệu | Vấn đề thường gặp | Biện pháp nên đánh giá |
|---|---|---|
| Bộ đếm thống kê | Nhiều lần tăng cùng một hàng | Striped counter, batch delta, event log và projection bất đồng bộ |
| Lượt xem hoặc metric | Ghi rất nhiều, chấp nhận độ trễ nhỏ | Buffer bền vững, batch flush, bucket theo worker/thời gian |
| Tồn kho | Nhiều yêu cầu mua cùng SKU | Atomic conditional update, reservation, phân bổ theo kho/pool nếu đúng nghiệp vụ |
| Số dư tài khoản | Cần bảo đảm số dư và thứ tự giao dịch | Transaction ngắn, xử lý tuần tự theo account, ledger và kiểm soát idempotency |
| Số ID | Nhiều session xin số | Identity/sequence cache, cấp dải ID; không dùng MAX+1 |
| Trạng thái tác vụ | Nhiều worker cùng cập nhật một trạng thái | Claim theo batch, khóa có thời hạn, optimistic version và queue partition theo key |
| Index insert tuần tự | Nhiều insert vào trang cuối | Phân tích latch/page, index design, partition hoặc khóa phân phối phù hợp |

Không chọn biện pháp chỉ dựa vào tốc độ. Cần giữ các invariant như không bán vượt tồn kho, không ghi sổ hai lần, không mất sự kiện và không cấp ID trùng.

## 13. Những sai lầm thường gặp

1. **Tăng số connection để chữa nghẽn:** có thể chỉ làm hàng đợi khóa dài hơn.
2. **Đọc rồi ghi bộ đếm ở ứng dụng:** có nguy cơ lost update nếu không có cơ chế đồng thời phù hợp.
3. **Cho rằng UPDATE nguyên tử loại bỏ contention:** nó bảo đảm phép cộng đúng nhưng nhiều phiên vẫn phải tuần tự cập nhật cùng hàng.
4. **Phân mảnh bộ đếm nhưng đọc tổng liên tục:** chi phí aggregate có thể chuyển bottleneck sang đường đọc.
5. **Chọn bucket ngẫu nhiên không có idempotency:** retry có thể cộng một sự kiện nhiều lần ở các bucket khác nhau.
6. **Phân mảnh dữ liệu cần invariant toàn cục mà không có cơ chế phân bổ:** có thể tạo oversell hoặc vượt quota.
7. **Dùng UUID ngẫu nhiên để tránh trang cuối mà không đo:** có thể tăng page split và I/O ngẫu nhiên.
8. **Giữ transaction mở trong lúc gọi dịch vụ bên ngoài:** kéo dài thời gian giữ khóa.
9. **Batch quá lớn:** giảm round trip nhưng tăng lock duration, log và thời gian rollback.
10. **Dùng sequence với kỳ vọng gapless:** sequence/identity thường không bảo đảm không có khoảng trống.
11. **Chỉ xem CPU:** lock/latch wait hoặc log flush có thể là giới hạn khi CPU còn thấp.
12. **Không kiểm tra tính đúng sau tối ưu:** throughput tăng nhưng mất cập nhật, cộng trùng hoặc sai invariant là thất bại.

## 14. Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định hot row, hot key hoặc hot index/page bằng số liệu quan sát.
- [ ] Đã phân biệt lock wait với latch/page wait, I/O và log flush.
- [ ] Đã xác minh câu SQL, transaction và nhóm khóa gây tranh chấp.
- [ ] Đã kiểm tra mẫu đọc-sửa-ghi có nguy cơ lost update.
- [ ] Đã rút ngắn transaction và loại bỏ thời gian chờ bên ngoài khỏi critical section.
- [ ] Đã chọn atomic update, batching, striped counter, queue hoặc sequence theo đúng invariant.
- [ ] Đã có idempotency và retry an toàn khi gom hoặc phân phối sự kiện.
- [ ] Đã đánh giá index maintenance, page split, cache và chi phí ghi bổ sung.
- [ ] Đã kiểm thử nhiều mức concurrency với nhóm hot-key và nhóm khóa phân tán.
- [ ] Đã đo throughput commit, p95/p99, wait, log, CPU và I/O trước/sau.
- [ ] Đã kiểm tra tổng giá trị, không mất/cộng trùng dữ liệu và mọi invariant nghiệp vụ.
- [ ] Đã có phương án rollback hoặc giảm tải nếu contention tăng sau triển khai.

Khóa được cập nhật nhiều và bộ đếm dùng chung có thể trở thành điểm tuần tự hóa, giới hạn thông lượng ghi ngay cả khi phần còn lại của database chưa bão hòa. Hãy xác định đúng loại tranh chấp, rút ngắn thời gian giữ khóa và chọn cách phân phối thao tác phù hợp: batch hoặc striped counter cho số liệu tổng hợp, atomic update và reservation cho tồn kho, xử lý theo khóa hoặc ledger cho dữ liệu cần invariant chặt chẽ, và sequence/cache cho cấp ID. Mọi thay đổi phải được kiểm thử dưới tải đồng thời, đo số transaction commit và độ trễ đuôi, đồng thời xác minh không mất cập nhật, không cộng trùng và không vi phạm quy tắc nghiệp vụ.
