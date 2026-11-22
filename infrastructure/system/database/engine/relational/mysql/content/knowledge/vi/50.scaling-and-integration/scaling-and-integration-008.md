# Giao dịch xuyên shard, XA và giới hạn phối hợp phân tán

Khi dữ liệu MySQL được chia thành nhiều shard, một thao tác nghiệp vụ đôi khi phải cập nhật nhiều máy chủ. Ví dụ chuyển tiền giữa hai tài khoản nằm ở hai shard, tạo đơn hàng ở shard đơn hàng rồi giữ tồn kho ở shard kho, hoặc cập nhật dữ liệu khách hàng và sổ cái ở hai phân vùng khác nhau. Mỗi shard có transaction InnoDB riêng; `COMMIT` trên shard thứ nhất không tự động commit hay rollback shard thứ hai.

Để đạt kết quả commit đồng nhất trên nhiều resource manager, hệ thống có thể dùng **XA transaction với two-phase commit (2PC)**. Một transaction coordinator điều phối các nhánh XA trên từng shard: yêu cầu tất cả chuẩn bị commit, ghi quyết định bền vững, rồi yêu cầu các shard commit. Cơ chế này cung cấp atomic outcome khi các thành phần và quy trình recovery hoạt động đúng, nhưng phải trả giá bằng round trip, lock được giữ lâu, trạng thái in-doubt và phụ thuộc vào coordinator.

Không phải mọi nghiệp vụ xuyên shard đều cần XA. Thiết kế shard key để dữ liệu cùng aggregate nằm cùng shard thường đơn giản và nhanh hơn. Với workflow có thể chấp nhận nhất quán cuối cùng, saga kết hợp transactional outbox và thao tác bù trừ thường phù hợp hơn. Bài học này phân tích lựa chọn, cú pháp XA của MySQL, recovery và giới hạn của phối hợp phân tán.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao transaction InnoDB thông thường chỉ bảo đảm nguyên tử trong một MySQL instance.
- Thiết kế shard key để giảm nhu cầu cập nhật nhiều shard.
- Mô tả vai trò coordinator, participant và hai phase của 2PC.
- Đọc và viết các lệnh `XA START`, `XA END`, `XA PREPARE`, `XA COMMIT`, `XA ROLLBACK` và `XA RECOVER`.
- Phân tích lỗi khi coordinator, participant hoặc network gặp sự cố ở từng phase.
- Phục hồi prepared transaction dựa trên quyết định bền vững của coordinator.
- So sánh XA với saga, outbox và eventual consistency.
- Thiết kế kiểm thử lỗi, giám sát và quy trình vận hành cho giao dịch xuyên shard.

## 1. Vì sao transaction xuyên shard khó hơn?

Trong một MySQL instance, InnoDB có thể dùng một transaction để cập nhật nhiều bảng:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 101
  AND balance >= 100.00;

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 202;

COMMIT;
```

Nếu hai tài khoản ở cùng instance và cả hai câu lệnh nằm trong cùng transaction InnoDB, thay đổi được commit hoặc rollback cùng nhau. Nhưng trong hệ thống sharding, tài khoản 101 có thể nằm trên `shard-a`, còn tài khoản 202 nằm trên `shard-b`. Hai máy chủ có transaction log, lock manager và trạng thái commit độc lập.

Nếu ứng dụng chỉ gửi `COMMIT` cho shard A rồi shard B bị lỗi, tiền có thể đã bị trừ ở A nhưng chưa được cộng ở B. Nếu commit B trước rồi A lỗi, kết quả ngược lại cũng sai. Một vòng lặp gọi `commit()` lần lượt không tạo ra một transaction phân tán nguyên tử.

### 1.1. Mục tiêu của distributed commit

Một giao dịch xuyên shard thường muốn bảo đảm:

- **Atomic outcome:** mọi participant commit, hoặc mọi participant rollback theo quyết định toàn cục.
- **Durable decision:** sau khi coordinator quyết định commit/abort, quyết định đó được lưu bền vững để recovery có thể tiếp tục.
- **Consistent recovery:** nếu tiến trình hoặc mạng lỗi, các participant được đưa về cùng một kết quả cuối cùng.

Atomic commit không tự bảo đảm mọi quy tắc nghiệp vụ. XA không tự tạo foreign key xuyên shard, không kiểm tra một invariant nghiệp vụ chưa được mã hóa và không tự cung cấp global serializable isolation cho toàn hệ thống. Mỗi shard vẫn áp dụng isolation và constraint cục bộ của nó.

MySQL cũng có cơ chế **internal XA** để phối hợp transaction của storage engine như InnoDB với binary log trong quá trình commit. Đây là cơ chế nội bộ giúp giữ nhất quán giữa dữ liệu engine và binlog; nó không tự enlist một MySQL server khác vào transaction của ứng dụng. Internal XA và external XA xuyên shard là hai phạm vi khác nhau.

## 2. Thiết kế shard để tránh cross-shard transaction

Trước khi dùng XA, hãy xem có thể đưa dữ liệu thường xuyên thay đổi cùng nhau về một shard hay không. Chọn shard key theo aggregate và ranh giới transaction của nghiệp vụ.

Ví dụ hệ thống thương mại điện tử có thể phân vùng theo `customer_id`:

```text
shard(customer_id)
   |
   +-- customers
   +-- orders
   +-- order_items
   +-- customer_addresses
```

Khi tạo đơn hàng, dữ liệu khách hàng, đơn hàng và dòng hàng có thể được ghi trong cùng một transaction trên một shard. Điều này tránh phối hợp phân tán cho luồng phổ biến.

Tuy nhiên, không phải mọi dữ liệu đều nên phân vùng theo cùng một khóa. Kho hàng có thể phân vùng theo `warehouse_id`; sổ cái có thể phân vùng theo `account_id`; báo cáo toàn hệ thống có thể cần fan-out query hoặc kho dữ liệu riêng. Hãy nhận diện những thao tác xuyên miền nào là thường xuyên, quan trọng và cần atomic commit.

### 2.1. Các vấn đề cần thiết kế trước

- **Cross-shard foreign key:** MySQL không thực thi foreign key giữa hai server độc lập. Ứng dụng phải kiểm tra tham chiếu và xử lý vòng đời dữ liệu.
- **Global unique constraint:** unique index trong một shard chỉ bảo đảm duy nhất trong phạm vi shard. Muốn duy nhất toàn hệ thống cần định tuyến mọi giá trị cùng khóa về một shard, dùng bộ cấp ID toàn cục hoặc có registry/coordination riêng.
- **Global ID:** ID tự tăng cục bộ có thể trùng giữa các shard. Có thể dùng UUID, ID có shard prefix hoặc dịch vụ cấp ID phù hợp.
- **Fan-out query:** truy vấn trên nhiều shard cần hợp nhất kết quả, xử lý phân trang/sắp xếp và nhất quán đọc ở tầng ứng dụng.
- **Hot shard:** phân vùng theo khóa có phân bố lệch có thể khiến một shard quá tải dù tổng cluster còn tài nguyên.
- **Shard movement:** chuyển dữ liệu giữa shard cũng là workflow phân tán, cần dual-write/copy/checkpoint/cutover hoặc công cụ chuyên dụng.

Nếu một thao tác xuyên shard hiếm và không thể tránh, đánh giá XA hoặc saga theo yêu cầu nghiệp vụ. Đừng để XA trở thành cơ chế mặc định cho mọi request.

## 3. XA và two-phase commit

XA là giao thức phối hợp transaction giữa một transaction manager và nhiều resource manager. Trong kiến trúc MySQL sharding:

- **Transaction coordinator/manager:** tạo global transaction ID, ghi log quyết định và điều phối phase.
- **Participant/resource manager:** mỗi MySQL shard thực thi một nhánh (branch) của global transaction.
- **XID:** định danh global transaction và branch trên participant.

Mỗi participant xử lý DML trong một XA branch. Coordinator dùng hai phase để bảo đảm các participant cùng đi tới một kết quả.

### 3.1. Phase 1 — Prepare

1. Coordinator tạo global transaction ID và xác định danh sách participant.
2. Coordinator yêu cầu từng shard bắt đầu XA branch.
3. Ứng dụng thực hiện DML trên từng shard.
4. Coordinator kết thúc nhánh làm việc bằng `XA END`.
5. Coordinator gửi `XA PREPARE` tới từng participant.
6. Mỗi participant trả lời YES nếu đã ghi trạng thái prepared bền vững và có thể commit sau đó; nếu không thể prepare, coordinator phải quyết định abort.

Khi một branch ở trạng thái prepared, nó chưa commit nhưng đã giữ trạng thái cần thiết để hoàn tất về sau. InnoDB có thể tiếp tục giữ lock và tài nguyên liên quan. Các transaction khác có thể bị chặn khi truy cập hàng đang được branch prepared giữ.

### 3.2. Phase 2 — Commit hoặc rollback

- Nếu tất cả participant đã prepare thành công, coordinator ghi quyết định **COMMIT** bền vững vào coordinator log rồi gửi `XA COMMIT` tới từng participant.
- Nếu một participant không prepare được hoặc coordinator quyết định hủy trước commit decision, coordinator ghi quyết định **ROLLBACK** rồi gửi `XA ROLLBACK` tới các branch liên quan.
- Coordinator theo dõi kết quả từng participant. Nếu một lệnh commit/rollback bị mất phản hồi, cần recovery theo XID và durable decision.

Sơ đồ tổng quát:

```text
                Coordinator
                     |
          +----------+----------+
          |                     |
       shard-a                shard-b
          |                     |
       XA START               XA START
       DML                    DML
       XA END                 XA END
          |                     |
       XA PREPARE             XA PREPARE
          |                     |
       vote YES               vote YES
          +----------+----------+
                     |
             Ghi quyết định COMMIT
               bền vững vào log
                     |
          +----------+----------+
          |                     |
       XA COMMIT              XA COMMIT
          |                     |
          +----------+----------+
                     |
              Hoàn tất global tx
```

Coordinator phải lưu danh sách participant và XID trước khi điều phối, sau đó ghi rõ quyết định cuối cùng trước khi gửi lệnh phase 2. Không dựa vào bộ nhớ tiến trình hoặc log không bền vững để quyết định recovery sau khi process bị crash.

### 3.3. Vì sao 2PC có thể bị blocking?

Giả sử cả hai shard đã prepare, nhưng coordinator crash trước khi ghi hoặc khôi phục được quyết định cuối cùng. Participant không thể tự suy ra phải commit hay rollback. Chúng giữ trạng thái in-doubt và chờ coordinator recovery.

Nếu coordinator đã ghi COMMIT bền vững rồi crash trước khi gửi lệnh tới shard B, recovery phải tiếp tục commit B. Không được đổi quyết định sang rollback chỉ vì một participant chưa nhận lệnh.

Đây là đặc tính quan trọng của 2PC: nó ưu tiên một quyết định atomic, nhưng trong một số lỗi coordinator/network, participant có thể phải chờ. XA không phải giao thức non-blocking và không loại bỏ ảnh hưởng của network partition.

## 4. Cú pháp XA trong MySQL

MySQL cung cấp các lệnh SQL để quản lý XA branch. Trong ứng dụng production, transaction manager/XA coordinator thường gọi các thao tác tương ứng qua XA resource API của JDBC driver. Các lệnh dưới đây giúp hiểu trạng thái và cơ chế ở phía server.

Một XID có global transaction identifier (gtrid), branch qualifier (bqual) và format ID. Các branch của cùng global transaction dùng chung gtrid nhưng có bqual khác nhau để nhận diện participant.

Một branch đi qua các trạng thái chính:

| Lệnh | Trạng thái sau lệnh | Ý nghĩa |
|---|---|---|
| `XA START` | ACTIVE | Branch đang được session gắn với và có thể thực hiện DML |
| `XA END` | IDLE | Session kết thúc việc tham gia; branch chưa prepare và chưa commit |
| `XA PREPARE` | PREPARED | Participant đã chuẩn bị để có thể commit hoặc rollback sau đó |
| `XA COMMIT` / `XA ROLLBACK` | Hoàn tất | Branch kết thúc theo quyết định toàn cục |

`XA RECOVER` liệt kê branch ở trạng thái PREPARED; nó không phải danh sách mọi branch ACTIVE hoặc IDLE và cũng không phải lịch sử transaction. Khi connection hoặc coordinator lỗi, cần biết lệnh XA cuối cùng đã được xác nhận và đối chiếu XID trong coordinator log; đừng suy luận branch đã rollback chỉ vì client socket đã đóng.

### 4.1. Bắt đầu và kết thúc branch

Trên `shard-a`:

```sql
XA START 'transfer-2026-0001', 'shard-a', 1;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 101
  AND balance >= 100.00;

XA END 'transfer-2026-0001', 'shard-a', 1;
```

Trên `shard-b`:

```sql
XA START 'transfer-2026-0001', 'shard-b', 1;

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 202;

XA END 'transfer-2026-0001', 'shard-b', 1;
```

Ví dụ dùng cùng gtrid `transfer-2026-0001`, nhưng branch qualifier khác nhau. Trong hệ thống thật, XID phải duy nhất theo coordinator và không được tái sử dụng khi transaction cũ còn có thể được recovery.

Ứng dụng phải kiểm tra số hàng bị ảnh hưởng. Nếu câu trừ tiền không cập nhật đúng một tài khoản, nghiệp vụ không hợp lệ; coordinator cần quyết định rollback mọi branch thay vì tiếp tục prepare/commit.

### 4.2. Prepare và commit

Sau khi mọi branch đã `XA END`, coordinator yêu cầu từng participant prepare:

```sql
-- Trên shard-a
XA PREPARE 'transfer-2026-0001', 'shard-a', 1;

-- Trên shard-b
XA PREPARE 'transfer-2026-0001', 'shard-b', 1;
```

Chỉ sau khi nhận được kết quả prepare thành công từ tất cả participant và đã ghi quyết định COMMIT bền vững, coordinator mới gửi:

```sql
-- Trên shard-a
XA COMMIT 'transfer-2026-0001', 'shard-a', 1;

-- Trên shard-b
XA COMMIT 'transfer-2026-0001', 'shard-b', 1;
```

Nếu cần abort theo quyết định coordinator:

```sql
XA ROLLBACK 'transfer-2026-0001', 'shard-a', 1;
XA ROLLBACK 'transfer-2026-0001', 'shard-b', 1;
```

Các câu lệnh trên là trình tự minh họa trên từng shard, không phải script có thể chạy tuần tự tùy ý trên một kết nối. Trong ứng dụng thật, coordinator phải quản lý session/resource, lỗi ở từng bước, timeout, durable log và recovery. Không tự viết vòng lặp `XA COMMIT` mà không có coordinator log.

### 4.3. XA RECOVER

Trên mỗi MySQL participant, người vận hành có thể xem các XA branch đang ở trạng thái prepared:

```sql
XA RECOVER;
```

Kết quả thường có các trường `formatID`, `gtrid_length`, `bqual_length` và `data` chứa phần định danh XID. `XA RECOVER` là công cụ kiểm kê prepared branch; nó không cho biết coordinator đã quyết định COMMIT hay ROLLBACK.

Nếu một XID xuất hiện trong `XA RECOVER`, cần đối chiếu với coordinator log và danh sách participant. Không commit hoặc rollback thủ công chỉ dựa trên tuổi transaction hay tên XID.

## 5. Ví dụ nghiệp vụ chuyển tiền xuyên shard

Giả sử tài khoản nguồn ở shard A và tài khoản đích ở shard B. Yêu cầu nghiệp vụ:

- Tài khoản nguồn tồn tại và có đủ số dư.
- Tài khoản đích tồn tại.
- Tổng tiền được bảo toàn trong phạm vi transfer.
- Một `transfer_id` chỉ được xử lý một lần.

Schema cục bộ trên mỗi shard nên có khóa định danh giao dịch để hỗ trợ idempotency:

```sql
CREATE TABLE account_transfers (
  transfer_id VARCHAR(64) NOT NULL,
  account_id BIGINT UNSIGNED NOT NULL,
  direction ENUM('DEBIT', 'CREDIT') NOT NULL,
  amount DECIMAL(18, 2) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (transfer_id, direction)
) ENGINE = InnoDB;
```

Mỗi shard ghi dấu vết branch của transfer trong cùng XA transaction với thay đổi số dư. Khóa duy nhất giúp phát hiện việc coordinator gửi lại cùng branch sau timeout; cách xử lý duplicate phải được tích hợp vào transaction manager và quy tắc recovery.

Trình tự khái quát:

1. Coordinator nhận `transfer_id` và xác thực request.
2. Xác định shard nguồn và shard đích từ routing metadata.
3. Tạo XID duy nhất cho global transaction, gtrid đại diện transfer và bqual cho từng shard.
4. Mở XA branch trên cả hai shard.
5. Trừ tiền có điều kiện ở shard A và xác minh đúng một hàng được cập nhật; ghi debit record.
6. Cộng tiền ở shard B và xác minh đúng một hàng được cập nhật; ghi credit record.
7. Kết thúc và prepare cả hai branch.
8. Nếu mọi branch prepare thành công, ghi COMMIT decision bền vững rồi commit từng branch.
9. Nếu không thể prepare, ghi ROLLBACK decision rồi rollback các branch đã tham gia.
10. Ghi trạng thái hoàn tất và trả kết quả cho caller.

Nếu mất kết nối sau bước 8, caller có thể chưa nhận response dù transfer đã commit. Caller phải gửi lại cùng `transfer_id` để tra cứu kết quả, không tạo transfer mới với ID khác.

## 6. Coordinator log và recovery

Coordinator log là phần cốt lõi của recovery. Nó cần lưu ít nhất:

- Global transaction ID/gtrid và từng branch XID.
- Danh sách shard/resource manager tham gia.
- Trạng thái từng branch: started, ended, prepared, commit sent, committed hoặc rollback.
- Quyết định toàn cục COMMIT hoặc ROLLBACK đã được ghi bền vững.
- Thời điểm và thông tin cần thiết để retry/reconcile sau crash.

Log cần được ghi bền vững trước khi gửi phase 2. Nếu coordinator dùng database riêng để lưu log, bản thân thao tác ghi quyết định phải có durability phù hợp. Không lưu decision chỉ trong memory, log file tạm hoặc cache có thể mất khi restart.

### 6.1. Các tình huống phục hồi

| Sự cố | Trạng thái có thể gặp | Hướng recovery |
|---|---|---|
| Coordinator lỗi trước khi participant prepare | Branch có thể đang ACTIVE hoặc IDLE tùy lệnh XA cuối cùng; `XA RECOVER` không liệt kê các trạng thái này | Đọc coordinator log, đối chiếu XID và trạng thái session/participant; không suy luận đã rollback chỉ từ việc client mất kết nối |
| Một participant prepare thất bại | Một số branch có thể đã prepared | Ghi quyết định ROLLBACK bền vững rồi rollback mọi branch đã prepare |
| Coordinator crash sau khi tất cả prepare, trước khi lưu decision | Participant ở trạng thái in-doubt | Khôi phục coordinator log; nếu log xác nhận chưa ghi COMMIT decision, recovery có thể ghi quyết định ROLLBACK rồi hoàn tất các branch; nếu log không thể xác minh, không tự đoán tại participant |
| Coordinator đã ghi COMMIT nhưng chưa gửi tới mọi shard | Một số branch prepared, một số có thể đã commit | Recovery phải tiếp tục COMMIT tất cả branch theo durable decision |
| Phản hồi XA COMMIT bị mất | Branch có thể đã commit dù coordinator chưa nhận ACK | Đối chiếu durable decision, XA RECOVER và trạng thái nghiệp vụ; không đổi sang rollback |
| Participant restart khi branch prepared | Branch có thể xuất hiện lại trong `XA RECOVER` | Coordinator khôi phục decision và hoàn tất branch |
| Mất coordinator log | Không xác định được quyết định cuối cùng | Khôi phục log từ bản lưu bền vững; không tự ý quyết định commit/rollback |

### 6.2. Quy trình xử lý in-doubt branch

1. Xác định đúng MySQL shard và kiểm tra `XA RECOVER`.
2. Thu thập XID, thời điểm, trạng thái server, error log và replication state.
3. Tìm global transaction tương ứng trong coordinator log.
4. Xác định quyết định COMMIT/ROLLBACK đã được ghi bền vững hay chưa.
5. Nếu có COMMIT decision, hoàn tất commit cho các branch còn prepared.
6. Nếu có ROLLBACK decision, rollback các branch còn prepared.
7. Nếu chưa thể khôi phục decision, giữ nguyên trạng thái in-doubt và chuyển cho quy trình recovery của coordinator; không giải phóng lock bằng cách tự ý rollback.
8. Sau khi hoàn tất, xác minh dữ liệu và đánh dấu branch đã xử lý trong coordinator log.

Một prepared transaction có thể giữ lock và làm query khác chờ. Tuy nhiên, rollback thủ công một branch mà coordinator đã ghi COMMIT sẽ phá vỡ atomic outcome. Quyết định toàn cục phải là nguồn sự thật.

### 6.3. Participant commit response bị mất

Nếu coordinator đã ghi COMMIT và gửi `XA COMMIT`, nhưng socket đứt trước khi nhận phản hồi, không thể kết luận branch chưa commit. Khi recovery, kiểm tra:

- Durable coordinator decision.
- Branch còn xuất hiện trong `XA RECOVER` hay không.
- Participant đang ở primary nào sau failover.
- Transaction marker hoặc business record tương ứng với XID/transfer ID.
- Trạng thái của các participant còn lại.

Nếu branch không còn trong `XA RECOVER` trong khi coordinator có COMMIT decision, branch có thể đã hoàn tất commit; cần đối chiếu log và dữ liệu để xác nhận. `XA RECOVER` chỉ liệt kê branch còn prepared, không phải lịch sử commit/rollback.

## 7. XA qua JDBC và Spring

Trong ứng dụng Java, XA thường được tích hợp qua JDBC `XADataSource`/`XAResource` và một JTA transaction manager. Driver cung cấp resource adapter; transaction manager điều phối prepare/commit/rollback giữa các resource.

Điểm cần nhớ:

- Một `DataSource` JDBC thông thường cùng với `@Transactional` kiểu local không tự tạo distributed transaction.
- Spring `@Transactional` chỉ sử dụng transaction manager đang được cấu hình. Nếu đó là local `DataSourceTransactionManager`, transaction chỉ bao phủ resource tương ứng.
- Muốn phối hợp nhiều MySQL datasource, cần cấu hình JTA/XA transaction manager và XA-capable datasource cho từng shard.
- Tất cả participant phải được enlist vào cùng global transaction; mở một connection thông thường ngoài transaction manager sẽ không tự tham gia XA.
- Kiểm tra khả năng XA của đúng phiên bản MySQL Connector/J, pool, transaction manager và MySQL server.

Một số transaction manager phổ biến có cơ chế recovery riêng. Cần cấu hình transaction log path bền vững, unique node identifier và thông tin kết nối recovery cho mọi participant. Không xóa transaction log khi còn transaction in-doubt.

### 7.1. Ranh giới transaction trong code

Với JTA, service có thể dùng transaction boundary do JTA manager điều khiển. Ví dụ khái niệm:

```java
@Transactional
public TransferResult transfer(TransferCommand command) {
    // accountRepository dùng XA datasource của shard nguồn.
    // ledgerRepository dùng XA datasource của shard đích.
    // Cả hai resource phải được enlist trong cùng JTA transaction.
    debitSource(command);
    creditDestination(command);
    return TransferResult.accepted(command.transferId());
}
```

Đoạn code chỉ có ý nghĩa phân tán khi transaction manager thực sự là JTA/XA và cả hai datasource được cấu hình enlist. Nếu dùng transaction manager local, annotation không biến hai commit riêng lẻ thành 2PC.

Không tự gọi `XA PREPARE` hoặc `XA COMMIT` bằng một JDBC connection thông thường bên trong method đang có transaction manager khác điều khiển. Trộn hai cơ chế có thể khiến coordinator không biết trạng thái branch.

### 7.2. Pool và XA recovery

Connection pool phải tương thích với XA resource và transaction manager. Khi global transaction kết thúc, resource phải được delist và trả về pool đúng trạng thái. Prepared branch không được xem như một connection idle thông thường; nó có thể tiếp tục giữ transaction state trên server sau khi ứng dụng đã mất session.

Recovery manager cần có khả năng kết nối lại participant và enumerate prepared XID. Đảm bảo account recovery có quyền phù hợp, endpoint luôn trỏ đúng shard và thông tin xác thực được quản lý an toàn.

## 8. Giới hạn của XA và 2PC

XA giúp điều phối atomic commit, nhưng không loại bỏ chi phí và failure mode của hệ phân tán.

### 8.1. Độ trễ và throughput

Một giao dịch cần ít nhất phase prepare và phase commit/rollback qua network tới mọi participant. Độ trễ phụ thuộc participant chậm nhất và coordinator. Nếu một request chạm nhiều shard, số round trip, connection và tài nguyên giữ đồng thời tăng.

Batching nhiều thao tác trong cùng một shard branch có thể giảm số lần gọi coordinator, nhưng transaction càng lớn càng giữ lock lâu. Cần giới hạn số participant và thời gian thực thi.

### 8.2. Lock và in-doubt transaction

Prepared branch có thể giữ row lock và tài nguyên cho đến khi coordinator gửi quyết định cuối cùng. Nếu coordinator hoặc network bị gián đoạn lâu, các transaction khác có thể bị block và hàng đợi lock tăng.

Đặt timeout ở tầng request, coordinator và database; nhưng timeout không tự giải quyết branch đã prepared. Recovery phải tiếp tục theo durable decision. Theo dõi tuổi của prepared XID, số lượng branch in-doubt và lock wait.

### 8.3. Distributed deadlock

InnoDB phát hiện deadlock trong phạm vi một MySQL instance. Một vòng chờ khóa đi qua nhiều shard có thể không được local deadlock detector nhìn thấy như một chu trình toàn cục. Ví dụ transaction A giữ row trên shard 1 rồi chờ shard 2, trong khi transaction B giữ row trên shard 2 rồi chờ shard 1.

Giảm nguy cơ bằng cách:

- Truy cập participant theo thứ tự shard ổn định trong mọi luồng nghiệp vụ.
- Giữ transaction ngắn và cập nhật số hàng tối thiểu.
- Đặt deadline toàn cục và timeout chờ có giới hạn.
- Có cơ chế phát hiện transaction tiến triển chậm và hủy theo quyết định coordinator.
- Retry toàn bộ nghiệp vụ bằng idempotency key sau khi xác định kết quả cũ.

Timeout cục bộ có thể giải phóng một branch đang chờ nhưng không thay thế distributed deadlock detection và recovery.

### 8.4. Availability khi network partition

Nếu coordinator không thể liên lạc với một participant, nó không thể tự ý coi participant đó đã commit hoặc rollback. Khi đã có prepared branch, 2PC có thể phải chờ để giữ atomic decision. Vì vậy XA đánh đổi khả năng tiếp tục hoàn tất giao dịch trong một số phân vùng mạng để duy trì quyết định nhất quán.

Không có cấu hình timeout nào biến 2PC thành một giao thức luôn tiếp tục được khi coordinator hoặc participant không thể liên lạc. Cần chấp nhận trade-off này ở cấp nghiệp vụ và SLO.

### 8.5. XA không tạo global constraint hoặc global isolation tự động

XA phối hợp kết quả commit của các resource manager. Nó không cung cấp:

- Foreign key vật lý giữa hai MySQL server.
- Unique index toàn cluster nếu dữ liệu được phân tán tùy ý.
- Một global lock manager cho mọi row ở mọi shard.
- Global serializable isolation mặc định cho mọi transaction xuyên shard.
- Atomicity với hệ thống ngoài XA như HTTP service, email hoặc message broker không được enlist.

Nếu nghiệp vụ cần invariant toàn cục, phải thiết kế rõ nơi kiểm tra, cơ chế khóa/định danh và cách phục hồi. XA không thay thế thiết kế dữ liệu phân tán.

## 9. XA so với saga và transactional outbox

Không phải thao tác xuyên shard nào cũng cần atomic commit. Chọn cơ chế dựa trên hậu quả nghiệp vụ nếu một bước hoàn tất còn bước khác thất bại.

| Tiêu chí | XA / 2PC | Saga | Transactional outbox |
|---|---|---|---|
| Mục tiêu | Atomic outcome giữa các XA participant | Chuỗi local transaction và hành động bù trừ | Ghi business data và event trong cùng local transaction |
| Rollback | Coordinator quyết định commit/rollback các branch | Dùng compensating action; không xóa lịch sử đã commit | Không tự rollback consumer; bảo đảm event được phát sau commit |
| Nhất quán | Atomic commit khi participant và recovery đáp ứng | Eventual consistency theo workflow | Event được phát bền vững; consumer xử lý eventual |
| Tài nguyên | Giữ prepared state/lock qua phase | Không giữ transaction DB xuyên suốt workflow | Mỗi bước có transaction cục bộ ngắn |
| Khi phù hợp | Cần all-or-nothing và các resource hỗ trợ XA | Workflow dài, có bước bù trừ nghiệp vụ | Cần phát event đáng tin cậy sau khi commit database |
| Giới hạn | Blocking, latency, coordinator và recovery phức tạp | Compensation không luôn đảo ngược được tác động | Cần xử lý duplicate, retry và thứ tự event |

### 9.1. Saga cho chuyển trạng thái nhiều bước

Ví dụ đặt hàng có thể gồm:

1. Tạo order ở shard đơn hàng.
2. Giữ tồn kho ở shard kho.
3. Yêu cầu thanh toán ở service thanh toán.
4. Xác nhận order.

Nếu thanh toán thất bại sau khi giữ kho, saga chạy hành động bù trừ để giải phóng tồn kho và chuyển order sang trạng thái thất bại. Hành động bù trừ là một giao dịch nghiệp vụ mới, không phải rollback vật lý transaction cũ.

Saga phù hợp khi hệ thống có thể biểu diễn trạng thái trung gian như `PENDING`, `RESERVED`, `PAYMENT_FAILED` và chấp nhận eventual consistency. Mỗi bước cần idempotent và có retry/dead-letter/reconciliation.

### 9.2. Outbox để phát sự kiện

Khi một service cập nhật MySQL rồi cần publish message, ghi business row và outbox row trong cùng local transaction:

```sql
START TRANSACTION;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 9001;

INSERT INTO outbox_events (event_id, aggregate_id, event_type, payload)
VALUES ('evt-9001', '9001', 'OrderConfirmed', '{"orderId":9001}');

COMMIT;
```

Worker đọc outbox và publish event; sau đó đánh dấu đã gửi. Worker có thể gửi lại nếu mất ACK, nên consumer phải deduplicate theo `event_id`. Outbox không tạo atomic transaction giữa MySQL và broker, nhưng tránh khoảng trống giữa commit database và việc lưu ý định publish.

## 10. Durability, replication và failover

2PC chỉ có thể recovery đúng nếu quyết định và trạng thái prepared còn tồn tại sau crash. Cần cấu hình durability của MySQL và transaction manager phù hợp với yêu cầu dữ liệu.

Đánh giá tối thiểu:

- InnoDB redo log flush policy, đặc biệt `innodb_flush_log_at_trx_commit`.
- Binary log durability, đặc biệt `sync_binlog` nếu binary log tham gia replication/recovery.
- Coordinator log có được ghi bền vững trước phase 2 hay không.
- Backup/restore của coordinator log và cấu hình transaction manager.
- Replication topology của từng shard, GTID, failover policy và RPO.
- Khả năng tìm lại prepared branch sau restart hoặc chuyển primary.

Với asynchronous replication, một transaction có thể đã commit trên primary nhưng chưa được replicate khi primary failover. Nếu shard mới không có transaction đó, trạng thái global có thể không còn như coordinator dự kiến. Không giả định XA tự làm cho replication giữa các shard trở thành đồng bộ hoặc loại bỏ RPO.

Diễn tập failover trong lúc có XA transaction ở các trạng thái active, prepared và commit-sent. Sau failover, đối chiếu coordinator decision, `XA RECOVER`, GTID và business record trên primary mới trước khi cho phép retry.

## 11. Quan sát và vận hành

Coordinator và mỗi participant cần có log liên kết bằng global transaction ID. Tránh log riêng từng shard mà không có ID chung.

Các chỉ số nên theo dõi:

- Số global transaction đang active, preparing, prepared, committing, rolling back và in-doubt.
- Số prepared XA branch và tuổi của branch lâu nhất trên từng shard.
- Thời gian phase prepare và phase commit p95/p99.
- Tỷ lệ prepare failure, commit/rollback timeout và recovery retry.
- Số transaction coordinator chưa hoàn tất và độ trễ recovery.
- Lock wait, deadlock, transaction age, connection pool usage và replica lag trên từng shard.
- Tỷ lệ saga compensation, outbox backlog và consumer duplicate nếu dùng eventual consistency.

### 11.1. Kiểm tra prepared transaction

Trên từng shard:

```sql
XA RECOVER;

SELECT
  trx_id,
  trx_state,
  trx_started,
  trx_mysql_thread_id,
  trx_rows_locked,
  trx_rows_modified
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Prepared XA branch không nhất thiết hiển thị như một transaction session đang hoạt động thông thường trong mọi góc nhìn; dùng `XA RECOVER` để liệt kê branch prepared. Kết hợp process list, InnoDB transaction view và coordinator log để điều tra.

### 11.2. Quy tắc vận hành

- Không xóa coordinator log khi còn global transaction chưa hoàn tất.
- Không khởi động một coordinator mới với cùng identity nếu transaction manager cũ vẫn có thể recovery, trừ khi cơ chế HA đã bảo đảm fencing.
- Không để hai coordinator cùng quyết định cho cùng một global transaction.
- Không tự commit/rollback XID chỉ để giải phóng lock.
- Không tái sử dụng XID cũ cho request mới.
- Lưu thông tin participant, shard identity và routing version để recovery không gửi quyết định nhầm server.
- Định kỳ diễn tập crash coordinator, mất network, restart participant và failover primary.

## 12. Bài thực hành

Một ứng dụng ngân hàng chia dữ liệu tài khoản theo `account_id`. Tài khoản nguồn `101` nằm trên shard A; tài khoản đích `202` nằm trên shard B. Mỗi shard dùng MySQL 8.0 và InnoDB. Ứng dụng cần chuyển 100 đơn vị tiền và bảo đảm không mất hoặc tạo tiền hai lần.

Hãy thiết kế giải pháp và trả lời:

1. Vì sao transaction InnoDB thông thường trên shard A không thể rollback một transaction đã commit trên shard B?
2. Có thể đổi shard key hoặc thiết kế aggregate thế nào để giảm số lần chuyển tiền cần XA?
3. Mô tả coordinator, participant, gtrid và bqual trong global transaction.
4. Viết trình tự `XA START`, DML, `XA END`, `XA PREPARE` và `XA COMMIT` cho hai shard.
5. Nếu cập nhật số dư nguồn ảnh hưởng 0 hàng, coordinator phải xử lý thế nào?
6. Vì sao phải ghi COMMIT decision bền vững trước khi gửi `XA COMMIT` tới participant?
7. Nếu shard A đã commit nhưng phản hồi bị mất, làm sao recovery xác định trạng thái?
8. Nếu coordinator crash khi cả hai shard đã prepared nhưng chưa có durable decision, tại sao participant không thể tự quyết định?
9. Dùng `XA RECOVER` như thế nào để tìm branch in-doubt và đối chiếu coordinator log?
10. Vì sao không thể dùng `XA RECOVER` để biết một branch đã commit hay rollback trong quá khứ?
11. Những lock, latency và availability trade-off nào xuất hiện khi network partition?
12. Nếu workflow đặt hàng có thể dùng compensation, hãy thiết kế saga và transactional outbox thay cho XA.
13. Sau primary failover trên một shard dùng asynchronous replication, cần kiểm tra GTID, prepared branch và RPO ra sao?
14. Viết ma trận fault injection cho lỗi trước prepare, trong prepare, sau durable commit decision và trong lúc gửi commit.

Một phương án tốt phải có XID duy nhất, coordinator log bền vững, recovery không suy đoán, idempotency key ở API và tiêu chí xác minh số dư sau mỗi fault injection. Hãy chạy trên hai MySQL test instance cô lập, không thử nghiệm với tài khoản hoặc dữ liệu thật.

## 13. Những nhầm lẫn thường gặp

- **Gọi `commit()` trên từng shard là distributed transaction:** commit tuần tự có thể để lại trạng thái một shard đã commit, shard kia chưa commit.
- **Cho rằng `@Transactional` mặc định điều phối XA:** annotation chỉ dùng transaction manager được cấu hình; local transaction manager không phối hợp nhiều datasource.
- **Cho rằng XA không thể bị block:** prepared branch có thể chờ coordinator trong trạng thái in-doubt.
- **Rollback branch khi coordinator mất kết nối:** có thể mâu thuẫn với COMMIT decision đã ghi bền vững.
- **Dùng `XA RECOVER` như lịch sử transaction:** lệnh chỉ liệt kê branch đang prepared.
- **Cho rằng XA tạo foreign key xuyên shard:** constraint vật lý chỉ có hiệu lực trong phạm vi MySQL instance.
- **Cho rằng XA cung cấp global serializable isolation:** mỗi participant vẫn có isolation và constraint cục bộ.
- **Retry với global transaction ID mới sau timeout:** có thể thực hiện cùng nghiệp vụ hai lần; cần idempotency key ổn định.
- **Dùng XA cho workflow dài nhiều dịch vụ:** lock và prepared state kéo dài có thể gây nghẽn; saga thường phù hợp hơn nếu có compensation.
- **Cho rằng XA loại bỏ rủi ro replication failover:** mỗi shard vẫn có RPO và durability riêng.

## Kết luận

Giao dịch xuyên shard cần một cơ chế phối hợp vì commit cục bộ trên từng MySQL server không tạo ra atomicity toàn cục. XA/2PC dùng coordinator, participant và durable decision để chuẩn bị rồi commit hoặc rollback các branch, nhưng có thể giữ lock ở trạng thái in-doubt khi coordinator hoặc network gặp sự cố. Hãy giảm cross-shard write bằng shard key phù hợp; dùng XA cho thao tác thực sự cần atomic outcome và có hạ tầng recovery; dùng saga/outbox cho workflow chấp nhận trạng thái trung gian và compensation. Dù chọn cách nào, cần global transaction ID, idempotency, observability, diễn tập failover và quy trình recovery dựa trên bằng chứng bền vững.
