# Dùng cache hoặc bản sao truy cập thay cho bản sao lưu

Một ứng dụng Java có PostgreSQL làm nguồn dữ liệu chính, Redis để tăng tốc đọc và hai read replica để chia tải. Khi được hỏi “hệ thống có phương án khôi phục dữ liệu chưa?”, đội phát triển trả lời: **“Có Redis và hai bản sao database nên không cần backup.”** Đây là một **lỗi thiết kế persistence nghiêm trọng**. Các bản sao có thể giúp hệ thống phục vụ nhanh hoặc vượt qua một số lỗi máy chủ, nhưng thường **không bảo vệ được trạng thái dữ liệu của ngày hôm qua khi hôm nay có lệnh xóa nhầm, dữ liệu bị mã độc sửa hoặc lỗi nghiệp vụ đã lan sang tất cả bản sao**.

Trong chương **Lỗi thiết kế** của **DATA_PERSISTENCE_FUNDAMENTALS**, bài học này phân tích ranh giới giữa **cache**, **replica phục vụ truy cập**, **backup độc lập** và **khôi phục tới một thời điểm**. Người học cần nhận diện thiết kế sai, chứng minh tại sao nó thất bại khi có sự cố, hiểu tác động lên Java/JDBC và xây một phương án sao lưu–khôi phục có thể kiểm chứng bằng dữ liệu và số đo.

**Luận điểm chính:** cache tối ưu **đọc nhanh**, replica chủ yếu tăng **khả dụng hoặc năng lực phục vụ**, còn backup tạo **điểm phục hồi được giữ lại độc lập theo thời gian**. Chúng có thể bổ sung cho nhau, nhưng không thể được coi là tương đương chỉ vì mỗi nơi đều đang chứa một số bản sao dữ liệu.

## 1. Phân biệt ba cơ chế theo mục tiêu và vòng đời

| Thành phần | Dữ liệu chứa trong đó | Vai trò chủ đạo | Mất gì khi có sự cố? |
| --- | --- | --- | --- |
| **Cache** (Redis, Caffeine, cache HTTP/CDN) | Giá trị đã tính hoặc bản sao một phần dữ liệu thường truy cập | Giảm độ trễ, giảm lượt đọc DB | Có thể mất bất kỳ lúc nào do TTL, eviction, flush hoặc restart |
| **Read replica** | Bản sao dữ liệu được đồng bộ từ primary, có thể có replication lag | Chia tải đọc, có thể hỗ trợ failover tùy hệ thống | Thay đổi sai/xóa dữ liệu có thể được nhân bản theo; bản sao có thể chậm hoặc lỗi |
| **Backup logic/physical** | Bản lưu có metadata, định dạng và quy trình phục hồi phù hợp | Khôi phục dữ liệu khi nguồn bị mất/sai | Có thể lấy lại một trạng thái lịch sử đã được lưu và giữ đúng cách |
| **WAL/log archive cho PITR** | Chuỗi bản ghi thay đổi phục vụ replay từ một base backup | Khôi phục tới mốc cụ thể khi công cụ hỗ trợ | Có thể khôi phục đến mốc trước sự kiện xóa nhầm nếu chuỗi log đầy đủ |

Một kiến trúc có thể dùng đủ các cơ chế:

```text
              Java API / worker
                  |
        +---------+-----------+
        |                     |
        v                     v
  Redis read cache       PostgreSQL Primary
  TTL / eviction               |
  dữ liệu dẫn xuất             +----> Read replica A
                              |
                              +----> Read replica B
                              |
                              +----> WAL archive liên tục
                              |                 |
                              +----> Base backup|
                                        \       /
                                         v     v
                                    Kho backup độc lập
                                  (giới hạn quyền, giữ phiên bản)
                                              |
                                              v
                                   Restore lab / PITR khi cần
```

**Phân biệt bằng câu hỏi:** nếu một tài khoản có quyền xóa dữ liệu trên primary đã thực hiện `DELETE` hợp lệ về mặt SQL nhưng sai nghiệp vụ, **bản nào còn cho phép khôi phục trạng thái trước câu lệnh đó?** Một replica luôn áp dụng thay đổi mới thường không đáp ứng được; một backup lịch sử có đủ WAL và retention mới có thể.

### “Có nhiều bản sao” không đồng nghĩa “có nhiều mốc thời gian”

Replication tạo thêm bản sao của **trạng thái đang tiến triển**. Backup giữ lại một hoặc nhiều **mốc phục hồi trong quá khứ**. Đó là hai trục khác nhau:

```text
Trục bản sao hiện tại: Primary ──> Replica A ──> Replica B
                      cùng tiến về trạng thái mới hơn

Trục lịch sử backup:  B0 -------- B1 -------- B2 -------- B3
                     các điểm được giữ để phục hồi sau này
```

Số lượng node không thể thay thế số lượng bản backup lịch sử. Một cụm có năm replica mà tất cả đã nhận cùng lệnh `DROP TABLE` vẫn có thể không có bản nào giữ bảng cũ.

## 2. Vì sao cache không phải nguồn dữ liệu phục hồi?

Cache phổ biến hoạt động theo cơ chế **cache-aside**:

1. Java đọc Redis theo khóa `order:42`.
2. Nếu có (*cache hit*), trả kết quả đã lưu; nếu không (*cache miss*), đọc nguồn dữ liệu rồi lưu vào cache trong thời hạn ngắn.
3. Khi DB thay đổi, ứng dụng cố gắng invalidation hoặc chờ TTL hết hạn.

```text
GET /orders/42
    |
    v
  Cache ---- hit ----> trả giá trị có thể đã cũ
    |
   miss
    |
    v
 PostgreSQL ----> populate cache ----> trả dữ liệu
```

Cache không đại diện đầy đủ cho database vì:

- **Không đầy đủ:** chỉ các khóa từng được truy cập mới có mặt; những hàng ít được đọc, record lịch sử và index/ràng buộc không nằm trong cache.
- **Có thời hạn:** TTL, chính sách LRU/LFU và memory pressure có thể xóa giá trị để nhường RAM.
- **Có thể bị làm rỗng có chủ ý:** `FLUSHDB`, restart hoặc thay cache cluster có thể xóa dữ liệu mà ứng dụng vẫn hoạt động theo thiết kế.
- **Có thể cũ hoặc không nhất quán:** cache cập nhật muộn; một khóa có version 7 trong khi DB đã là version 8, hoặc hai khóa tương quan được lấy ở hai transaction khác nhau.
- **Không giữ metadata phục hồi DB:** schema, foreign key, sequence, role, transaction log, encryption key và lịch sử commit có thể không có.
- **Không có lời hứa lưu giữ một mốc:** nếu cache được thiết kế để tự hết hạn, không thể yêu cầu “cho tôi dữ liệu lúc 10:20 hôm qua”.

Ngay cả Redis được cấu hình **RDB snapshot**, **AOF** hoặc replication thì đó là **cơ chế persistence/replication của Redis theo cấu hình**; nó không tự biến dữ liệu cache thành một backup độc lập, đầy đủ và kiểm chứng được của PostgreSQL. Nếu Redis là nguồn dữ liệu chính của một hệ thống khác, phải thiết kế backup và khôi phục **cho Redis như một database thực sự**, thay vì suy ra tất cả cache đều là DB chính.

### Ví dụ: “Phục hồi” bằng cache sau lệnh xóa nhầm

Giả sử `orders` có 10 triệu hàng. Redis hiện chứa 25.000 khóa do người dùng vừa truy cập. Một migration sai xóa 200.000 đơn cũ khỏi PostgreSQL.

Có thể vẫn có vài trăm đơn trong Redis, nhưng:

1. Không có cách chứng minh 25.000 khóa bao phủ chính xác 200.000 đơn đã xóa.
2. Một phần giá trị đã stale; số tiền, trạng thái hoặc version không nhất thiết là dữ liệu cuối cùng trước sự cố.
3. Quan hệ với `order_items` và `payments` có thể không có trong cache.
4. Cache có thể được làm mới bằng chính dữ liệu **đã xóa** hoặc bị invalidation khi sự cố diễn ra.

Việc lấy cache rồi `INSERT` ngược vào DB không phải một quy trình recovery đáng tin cậy. Nếu muốn tận dụng cache làm **nguồn bằng chứng phụ trợ** khi ứng cứu đặc biệt, phải đối soát có kiểm toán; không được hứa có thể hoàn nguyên dữ liệu đúng và đủ chỉ từ cache.

## 3. Vì sao read replica không thay thế backup?

Ở mô hình primary–replica thông dụng, primary ghi transaction, còn replica nhận và áp dụng log/thay đổi. Replication có thể **bất đồng bộ**, nghĩa là replica chậm hơn primary; hoặc có chế độ xác nhận đồng bộ, nhưng hành vi còn tùy sản phẩm và cấu hình.

Một read replica thường được thiết kế để **theo kịp nguồn**, không phải giữ mãi một trạng thái trước sự cố logic.

```text
10:00 Primary:  100.000 orders
10:01 Primary:  DELETE nhầm 80.000 orders; COMMIT
10:01 Replica:  Nhận và replay DELETE
10:02 Primary:  20.000 orders
10:02 Replica:  20.000 orders

Replica đồng bộ rất tốt -> lỗi logic cũng được nhân bản rất tốt.
```

Những sự cố replica có thể hỗ trợ và không thể tự giải quyết:

| Sự cố | Replica có thể giúp | Tại sao chưa đủ |
| --- | --- | --- |
| Primary gặp lỗi phần cứng | Có thể promote replica và đổi hướng kết nối | Cần failover/fencing, kiểm tra RPO, cập nhật pool và endpoint |
| Primary không đủ sức phục vụ đọc | Chia một phần read workload | Vẫn có thể lag, thiếu dữ liệu mới nhất; không tăng write throughput single-leader |
| Lệnh `DELETE`/`UPDATE` sai đã commit | Thông thường không | Thay đổi sai được áp dụng tiếp ở replica; cần bản lịch sử/PITR |
| Migration sai schema | Thông thường không | DDL có thể được nhân bản hoặc các bản sao cùng chịu lỗi ứng dụng |
| Ransomware hoặc quyền DBA bị lộ | Không bảo đảm | Cùng miền quyền, mạng hoặc điều khiển có thể làm hỏng tất cả các nút |
| Primary mất trước khi log kịp đến replica | Có thể còn dữ liệu cũ để phục vụ | Những giao dịch đã ACK trên primary có thể chưa xuất hiện ở replica async |
| Cần quay về trước lỗi lúc 11:43 | Không phải chức năng chính | Replica theo dòng thay đổi; cần snapshot lịch sử và log archive phù hợp |

**Ngoại lệ cần phân biệt:** có hệ thống thiết kế **delayed replica**, tạo độ trễ replay có chủ ý, hoặc backup được **lấy từ standby**. Chúng có thể bổ sung lớp phục hồi nhưng vẫn phải có retention, ranh giới nhất quán, quyền độc lập, phát hiện lỗi kịp thời và **restore drill**. Một delayed replica có “cửa sổ cứu dữ liệu” hữu hạn; nếu sự cố chỉ được phát hiện sau cửa sổ ấy, dữ liệu sai cũng sẽ được replay. Backup tạo từ replica **bằng công cụ backup đúng quy trình** có thể là backup hợp lệ; bản thân replica đang online thì vẫn không phải bản backup lịch sử.

### Replication lag không phải chính sách lưu giữ bản sao cũ

Nếu replica chậm 20 giây, đôi khi có thể đọc dữ liệu trước một lệnh vừa commit. Nhưng **20 giây lag không phải bản snapshot có thể tin cậy**: replay có thể bắt kịp ngay khi CPU/network phục hồi, và từng yêu cầu đến replica có thể quan sát mốc khác. Không dùng sự cố lag ngẫu nhiên để làm chiến lược “hoàn tác xóa nhầm”.

## 4. Ba loại lỗi thường phơi bày thiết kế sai

### 4.1. Lỗi logic được nhân bản hoàn hảo

Ứng dụng có bug cập nhật `wallet.balance = 0` với quá nhiều user, và transaction đã commit. Redis có thể cache kết quả mới; replica sẽ áp dụng log thay đổi. Hệ thống không mất một node nào nhưng đã mất dữ liệu đúng về mặt nghiệp vụ.

**Điểm kiểm thử:** lựa chọn bản backup gần trước lúc bug phát sinh, khôi phục trong môi trường cách ly và đối soát các giao dịch hợp lệ phát sinh sau mốc ấy. Không tự cho rằng replay đến hiện tại là an toàn: WAL chứa cả lệnh lỗi, nên PITR cần **chọn target trước thao tác gây hỏng** khi phù hợp.

### 4.2. Sự cố chung miền lỗi

Cache và replica cùng cluster/cloud account, cùng IAM admin và cùng mạng. Một credential bị lộ hoặc thao tác hạ tầng nhầm có thể xóa cả database, cache và volume replica.

**Điểm kiểm thử:** bản backup có được lưu tại **miền lỗi và quyền quản trị phù hợp để tách biệt**, có retention/immutable protection, encryption key có thể khôi phục, và role chạy ứng dụng có bị chặn xóa backup không?

Không nên chỉ đếm region: một object store cùng tài khoản nhưng có quyền xóa chung có thể vẫn nằm trong cùng miền rủi ro quản trị. Chính sách tách quyền và khả năng chống sửa/xóa backup là phần của recovery.

### 4.3. Bản sao có dữ liệu nhưng không phục hồi ứng dụng

Một replica có thể chứa nhiều bảng giống primary, nhưng sau khi dựng DB mới vẫn thiếu extension, role, connection secret, phiên bản schema, key mã hóa hoặc object storage đính kèm.

**Điểm kiểm thử:** không chỉ chạy `SELECT count(*)`. Phải restore được schema/permission, khởi động Java service với đúng cấu hình, chạy một use case đọc/ghi an toàn và kiểm tra những invariant nghiệp vụ quan trọng.

## 5. Backup đúng nghĩa phải đáp ứng những thuộc tính nào?

Một chiến lược backup không được đánh giá bằng số lượng file, mà bằng **khả năng khôi phục dữ liệu đúng phạm vi và thời gian**.

| Thuộc tính | Câu hỏi đánh giá | Bằng chứng cần có |
| --- | --- | --- |
| **Độc lập** | Nguồn bị xóa/hỏng có làm backup bị xóa/hỏng theo không? | Miền lỗi, quyền và vị trí lưu backup riêng |
| **Nhất quán** | Bản restore có thể đưa DB về trạng thái giao dịch hợp lệ không? | Snapshot logic đồng bộ hoặc protocol physical + WAL |
| **Lịch sử** | Có thể khôi phục về thời điểm trước lỗi logic không? | Retention, bản base backup và WAL/log còn đủ |
| **Đầy đủ phạm vi** | Có mọi schema, data, metadata, dependency cần thiết không? | Manifest DB, global objects, extension, roles, secrets/keys, external storage |
| **Toàn vẹn** | File có bị thiếu/sửa/hỏng khi truyền hoặc lưu không? | Checksum, manifest, xác minh công cụ, thử đọc/restore |
| **Bảo mật** | Ai được xem, giải mã, xóa hoặc thay backup? | Encryption, IAM tối thiểu, audit, immutable/retention policy |
| **Khả dụng khi khẩn cấp** | Người trực có thể lấy backup và key mà không cần hệ thống vừa hỏng không? | Runbook, quyền break-glass có audit, diễn tập |
| **Đã được thử** | Khôi phục thành công trong RTO thực tế chưa? | Restore drill, kiểm tra invariant và API, thời lượng đo được |

Một bản copy trên cùng ổ đĩa của primary là **bản sao bổ sung trong cùng miền lỗi**, không phải cơ chế bảo vệ đủ trước mất ổ đĩa. Một backup trên object storage có versioning nhưng role runtime vẫn có quyền xóa vĩnh viễn cũng cần được xem xét lại theo threat model.

### Quy tắc 3-2-1 là gợi ý, không phải phép chứng minh

Một khuyến nghị vận hành thường gặp là **3 bản sao dữ liệu trên 2 loại phương tiện, ít nhất 1 bản ở vị trí khác**. Có thể bổ sung bản bất biến/offline và thử restore. Tuy nhiên, không có con số nào tự động đáp ứng mọi RPO/RTO hay quy định bảo mật; điều quan trọng là các bản sao **không cùng bị phá bởi một lỗi và vẫn có thể phục hồi đúng dữ liệu**.

## 6. PostgreSQL: backup logic, physical, WAL và PITR

Với PostgreSQL, những cơ chế chính được dùng để **lưu một trạng thái có thể phục hồi**, khác với việc để một replica online:

### 6.1. Backup logic nhất quán bằng `pg_dump`

```bash
# Chỉ minh họa tại môi trường được phê duyệt.
# Credential được cấp an toàn, không đặt password vào command line.
pg_dump \
  --host=db-primary.internal.example \
  --username=backup_reader \
  --dbname=orders_db \
  --format=custom \
  --file=/secure/backups/orders_001.dump
```

`pg_dump` sử dụng snapshot phù hợp cho một PostgreSQL database và có thể xuất schema/data khi hệ thống vẫn ghi. File custom dump là **backup logic ở một mốc**, không tự mang theo toàn bộ WAL cho PITR. Nếu có nhiều database, global roles, tablespaces hoặc những thành phần ngoài DB, phải lên kế hoạch sao lưu riêng; một file dump không tự bảo đảm toàn hệ thống đã được lưu.

### 6.2. Physical base backup với WAL phù hợp

```bash
# Backup vật lý tới thư mục đích mới trên hệ thống backup.
# Điều kiện quyền, dung lượng và tính nhất quán phải được kiểm tra.
pg_basebackup \
  --host=db-primary.internal.example \
  --username=backup_operator \
  --pgdata=/secure/backups/base_001 \
  --format=plain \
  --wal-method=stream \
  --progress

# Kiểm tra manifest và file theo khả năng phiên bản công cụ.
pg_verifybackup /secure/backups/base_001
```

`pg_basebackup` phối hợp dữ liệu và WAL cần thiết để tạo một base backup có thể recovery. Nếu muốn **PITR đến thời điểm về sau**, cần lưu/archiving **chuỗi WAL liên tục**, có chính sách retention đủ bao phủ từ base backup tới recovery target. Một lần backup vật lý **không tự bao gồm vô hạn WAL tương lai**.

`pg_verifybackup` giúp xác minh các thành phần theo manifest nhưng **không thay thế khôi phục thử**: DB có thể mở được mà ứng dụng vẫn không chạy vì schema/role/extension/secret hoặc phụ thuộc ngoài DB chưa đúng.

### 6.3. PITR để tránh replay lỗi logic

```text
10:00  Base backup hợp lệ (B0)
10:01  WAL archive nhận log liên tục
10:10  Giao dịch hợp lệ #A commit
10:20  Giao dịch hợp lệ #B commit
10:21  Lệnh DELETE sai commit
10:25  Phát hiện sự cố
          |
          v
   Restore B0 trong môi trường cô lập
   + replay WAL tới mốc NGAY TRƯỚC DELETE sai
          |
          v
   Kiểm tra dữ liệu và quyết định đối soát
   các giao dịch hợp lệ xảy ra SAU target
```

Một target trước lệnh sai sẽ **không gồm** cả những commit hợp lệ sau target. Vì vậy recovery không kết thúc ở thao tác replay: phải liệt kê những request/operation ID đã được xác nhận trong khoảng giữa target và thời điểm sự cố, đối soát với hệ thống ngoài và quyết định làm lại/bù trừ theo nghiệp vụ.

**Phân biệt thời điểm với ranh giới commit:** chọn target bằng timestamp có thể chịu ảnh hưởng đồng hồ và giao dịch cùng thời điểm; nếu cần chính xác, phải dùng quy trình xác định transaction ID/LSN hoặc khả năng target của engine theo điều kiện hỗ trợ. Không chọn target bằng suy đoán rồi mở traffic ngay.

### 6.4. Backup từ replica có thể hợp lệ, nhưng cần công cụ đúng

Có thể xây backup từ standby bằng cơ chế PostgreSQL hỗ trợ ở phiên bản/cấu hình cụ thể, nếu bảo đảm WAL cần thiết, quyền, độ trễ và điều kiện consistency. Khi đó **sản phẩm được lưu độc lập từ backup job** là backup; **standby đang phục vụ đọc** vẫn không tự biến thành một điểm phục hồi bất biến. Cần thử restore theo đúng topology đã chọn.

## 7. Ví dụ Java: cache chỉ là read optimization

Một mẫu Java 17+ sau cho thấy cách tổ chức ranh giới persistence: **PostgreSQL là nguồn sự thật**, cache chỉ chứa kết quả đọc có TTL. Khi cache trống, service đọc DB để điền lại; việc mất cache không được làm mất record nghiệp vụ.

Giả sử bảng:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
           CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Mã đọc minh họa qua JDBC:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Duration;
import java.util.Optional;

public final class OrderReadService {
    public record OrderView(long orderId, String status, long version) {}

    public interface Cache {
        Optional<OrderView> get(long orderId);
        void put(long orderId, OrderView value, Duration ttl);
        void evict(long orderId);
    }

    private final DataSource primary;
    private final Cache cache;

    public OrderReadService(DataSource primary, Cache cache) {
        this.primary = primary;
        this.cache = cache;
    }

    // Chỉ phù hợp use case cho phép dữ liệu có thể hơi cũ.
    public Optional<OrderView> findForDisplay(long orderId)
            throws SQLException {
        Optional<OrderView> cached = cache.get(orderId);
        if (cached.isPresent()) return cached;

        Optional<OrderView> fromDb = findFromPrimary(orderId);
        fromDb.ifPresent(row ->
                cache.put(orderId, row, Duration.ofSeconds(30)));
        return fromDb;
    }

    // Bỏ qua cache khi cần kiểm tra trạng thái mới nhất từ primary.
    public Optional<OrderView> findFromPrimary(long orderId)
            throws SQLException {
        String sql = """
            SELECT order_id, status, version
            FROM orders WHERE order_id = ?
            """;
        try (Connection c = primary.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            ps.setQueryTimeout(5);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) return Optional.empty();
                return Optional.of(new OrderView(
                        rs.getLong("order_id"),
                        rs.getString("status"),
                        rs.getLong("version")));
            }
        }
    }
}
```

**Đọc đúng hợp đồng của ví dụ:**

- Đây là **read cache**; giá trị cache có thể stale trong thời gian TTL/invalidation. Không dùng `findForDisplay()` để quyết định thanh toán, giữ chỗ hoặc cập nhật bất biến.
- Khi PostgreSQL không còn hoặc dữ liệu bị xóa, cache **không phải** nơi lấy lại toàn bộ bảng hay lịch sử transaction. Method `findFromPrimary()` phải cho phép lỗi DB hiện ra để hệ thống xử lý phù hợp, không âm thầm trả cache cũ như dữ liệu xác thực.
- Interface `Cache` đại diện cho Redis/Caffeine; cần bổ sung timeout, fallback policy, metric và fail-open/fail-closed theo use case. Nếu cache lỗi, nhiều API đọc có thể bỏ qua cache để đọc DB, nhưng cần giới hạn tải để tránh **cache stampede** làm DB quá tải.
- `try-with-resources` bảo đảm connection được trả về pool. `setQueryTimeout()` không thay thế pool-acquire/network timeout.
- Khi có cập nhật DB, cần thiết kế invalidation hoặc version-aware cache **sau commit**, đồng thời có TTL/CDC/outbox hoặc chiến lược để phục hồi khi invalidation bị mất. Không giữ DB transaction mở trong khi chờ Redis.

Điều quan trọng: ngay cả một cache được duy trì chính xác 100% trong điều kiện bình thường **vẫn không phải backup** nếu nó không có version lịch sử, retention, cơ chế restore và miền lỗi độc lập.

## 8. Khi primary lỗi, có nên “ghi vào cache rồi đồng bộ sau”?

Đây là một biến thể nguy hiểm của nhầm lẫn cache và nguồn sự thật. Một API đặt hàng được thiết kế để ghi PostgreSQL, nhưng khi DB lỗi thì chuyển sang:

```text
DB unavailable
  -> write order to Redis cache
  -> return "ORDER_CONFIRMED" to customer
  -> hope to flush to DB later
```

Nếu Redis thực sự chỉ là cache, dữ liệu có thể bị eviction, restart hoặc không được ghi bền vững; API đã **xác nhận một giao dịch mà không có bằng chứng commit ở nguồn nghiệp vụ**. Nếu Redis trở thành hệ thống ghi chính tạm thời, đó là **một kiến trúc mới** cần giao thức durability, idempotency, ordering, conflict resolution, quota và backup riêng; không thể thêm một nhánh `catch(SQLException) { cache.put(...); }` rồi coi là an toàn.

Các lựa chọn có thể phù hợp hơn:

1. **Fail closed** cho command cần commit bền vững: trả lỗi có thể retry, không xác nhận thành công giả.
2. **Queue bền vững** được thiết kế làm nguồn nhận lệnh trong một số use case, có ranh giới acknowledgment và phục hồi rõ ràng; phải bảo đảm semantics, quyền, retention và đối soát.
3. **Degraded read-only mode** cho endpoint cho phép stale data: chỉ trả dữ liệu từ cache kèm chính sách freshness rõ, không xử lý command thay đổi trạng thái.
4. **Failover tới primary mới** nếu kiến trúc đã triển khai HA, có fencing, RPO và xử lý commit-result-unknown.

Không đánh đồng “còn trả được trang web” với “còn có thể ghi nghiệp vụ an toàn”.

## 9. RPO/RTO: số replica và cache hit ratio không trả lời được

| Chỉ số | Câu hỏi cần trả lời | Không thể suy ra từ |
| --- | --- | --- |
| **RPO** (*Recovery Point Objective*) | Tối đa mất bao nhiêu dữ liệu đã được xác nhận commit trong loại sự cố được xét? | Số node replica, cache hit rate hoặc số file backup |
| **RTO** (*Recovery Time Objective*) | Mất bao lâu tới khi **dịch vụ nghiệp vụ thiết yếu** hoạt động lại? | Chỉ việc DB lên TCP hoặc Redis ping thành công |
| **Backup retention** | Có những mốc lịch sử nào và giữ trong bao lâu? | Replication lag ngắn hoặc TTL cache |
| **Restore confidence** | Đã giải mã, dựng DB, replay WAL, kiểm tra schema/role và chạy API được chưa? | Backup job báo “success”, file tồn tại hoặc replica đang online |

Ví dụ giả định:

- Replica làm giảm thời gian chuyển khỏi một primary hỏng, nhưng vẫn có thể mất một số commit nếu replication bất đồng bộ.
- Backup lúc 00:00 với không có WAL archiving có thể không đáp ứng yêu cầu RPO 5 phút khi lỗi xảy ra lúc 23:50.
- Backup có PITR nhưng restore mất 8 giờ có thể không đạt RTO 30 phút dù dữ liệu đúng.
- Cache rất nhanh nhưng nếu primary và backup hỏng, cache có thể chỉ phục vụ một số trang cũ cho đến khi TTL hết; nó **không** tạo ra khả năng rebuild database đầy đủ.

Mục tiêu RPO/RTO phải được **đặt theo use case và loại sự cố**, rồi kiểm chứng bằng diễn tập chứ không áp một thông số chung cho mọi hệ thống.

## 10. Đối soát và khôi phục không dừng ở một database

Ứng dụng có thể đã gửi event tới broker, ghi dữ liệu thanh toán vào dịch vụ khác hoặc đưa file vào object storage. Nếu PostgreSQL restore về T0 nhưng broker/ledger vẫn ở T1, các thành phần **không có cùng mốc thời gian**:

```text
Source DB A (order + outbox) --- restore về T0
             |
             v
           Broker             --- đã giao event E trước T1
             |
             v
Consumer DB B / payment ledger --- giữ trạng thái ở T1
```

Những yêu cầu cần thiết:

- Đối soát **operation ID, request ID, event ID** và version, không chỉ so `COUNT(*)`.
- Nếu outbox sau restore quay lại `PENDING`, publisher có thể phát lại event đã được gửi; consumer cần **idempotency marker** và xử lý trùng đúng transaction.
- Nếu cả inbox marker trong DB consumer bị restore về trước khi xử lý, một side effect bên ngoài như gửi email/thu tiền có thể đã diễn ra dù marker đã mất; cần idempotency tại provider và quy trình điều chỉnh có audit.
- Không khôi phục một bản sao lab rồi cho worker tự gửi email, thanh toán hoặc message tới **production**. Phải cô lập external dependencies trước restore.
- Nếu backup trước lỗi logic làm mất các giao dịch hợp lệ sau target, không lấy từ cache/replica để chèn bừa dữ liệu; cần quy trình replay hoặc bù trừ dựa trên những bằng chứng bền vững.

Một backup giao dịch **đúng trong một database** không tự là snapshot nhất quán của **nhiều dịch vụ**. Runbook recovery phải nêu ranh giới và thứ tự mở lại các luồng xử lý.

## 11. Diễn tập phân biệt cache, replica và backup

### Kịch bản A: xóa toàn bộ cache

1. Trên **môi trường test cách ly**, seed PostgreSQL và làm nóng cache một số khóa.
2. Xóa cache hoặc restart cache test theo quy trình được phép.
3. Gọi API đọc; kiểm tra cache miss đọc từ DB, sau đó điền cache lại.
4. Đối chiếu trạng thái DB trước/sau không thay đổi; đo DB load khi cache lạnh và giới hạn stampede.

**Kỳ vọng:** ứng dụng có thể chậm hơn nhưng dữ liệu nghiệp vụ vẫn tồn tại. Nếu mất Redis làm mất đơn hàng, kiến trúc đã đối xử với dữ liệu quan trọng như cache hoặc đã có nguồn sự thật khác chưa được mô tả.

### Kịch bản B: primary hỏng nhưng replica còn

1. Ghi marker/operation ID vào primary DB test; lưu **commit ACK** độc lập bên ngoài.
2. Kiểm tra replication lag và cách định tuyến read endpoint.
3. Gây lỗi primary trong cụm test; thực hiện failover có fencing tới replica hợp lệ.
4. Tạo connection mới từ Java và đối chiếu tập marker đã ACK, tính mất mát theo RPO.
5. Kiểm tra read-your-writes, transaction lỗi và khả năng ghi mới lên leader.

**Kỳ vọng:** replica có thể giúp tiếp tục phục vụ, nhưng có thể chưa có mọi commit nếu async; đây là bài đo HA/durability, **không chứng minh khả năng quay về trước một `DELETE` sai**.

### Kịch bản C: lỗi logic đã được nhân bản

1. Tạo dữ liệu test có quan hệ `orders`/`order_items` và ghi một mốc backup hợp lệ.
2. Ghi thêm transaction hợp lệ, rồi thực hiện một thao tác xóa nhầm **chỉ trên dữ liệu test**.
3. Xem lỗi được phản ánh ở primary và read replica; cache có thể stale hoặc đã bị làm mới.
4. Dựng DB **lab khác** từ backup và WAL, chọn recovery target trước lệnh sai nếu được hỗ trợ.
5. Kiểm tra constraint/invariant, liệt kê operation ID hợp lệ sau recovery target cần đối soát.

**Kỳ vọng:** cache/replica không được coi là cứu cánh; bản backup đúng và quy trình PITR/đối soát mới chứng minh được khả năng phục hồi.

### Kịch bản D: backup có file nhưng ứng dụng không chạy

1. Restore bản backup vào môi trường không kết nối hệ thống ngoài thật.
2. Kiểm tra role, extension, encryption key, secret JDBC, migration version, sequence, index và quyền truy cập.
3. Chạy smoke test Java đọc dữ liệu và một giao dịch ghi **trên bảng probe dành cho lab**.
4. Đo RTO đến lúc API thiết yếu thực sự đáp ứng; phân loại blocker và điều chỉnh runbook.

**Kỳ vọng:** backup không chỉ là file có checksum đúng; nó phải cho phép khởi động ứng dụng với dữ liệu và quyền hợp lệ.

## 12. Runbook phục hồi mẫu

| Pha | Hành động | Điều kiện qua pha |
| --- | --- | --- |
| **1. Phát hiện** | Định danh lỗi máy chủ, lỗi logic, leak credential hoặc mất backup; ghi mốc và phiên bản | Xác định đúng loại sự cố và người điều phối |
| **2. Ngăn lan truyền** | Dừng writer/worker khi phù hợp; thu hồi quyền bị lộ, chặn xóa nhầm tiếp diễn | Không làm tình trạng dữ liệu xấu thêm |
| **3. Chọn nguồn phục hồi** | Xác minh backup + WAL, tính độc lập, retention, khóa giải mã, khả năng dùng | Có manifest và recovery target rõ |
| **4. Khôi phục cô lập** | Dựng DB mới, replay log tới target phù hợp; chưa mở external side effect | DB phục hồi transaction-consistent |
| **5. Kiểm tra dữ liệu** | Schema/role/constraint, totals, order ID, receipt/outbox, dữ liệu ngoài DB | Bất biến được xác minh, sai lệch được phân loại |
| **6. Kiểm tra ứng dụng** | Java DataSource, connection pool, TLS, migrations, read/write lab | API và transaction thiết yếu thực thi đúng |
| **7. Đối soát** | Khớp operation/event ID với provider và broker, quyết định replay/bù trừ | Không double charge, không bỏ sót sự kiện không được phép |
| **8. Mở lại và theo dõi** | Chuyển traffic, bật worker có kiểm soát, xem error/RPO/RTO/outbox lag | Dịch vụ hoạt động ổn định trong ngưỡng |
| **9. Hậu kiểm** | Báo cáo dữ liệu được/phải mất, thời gian phục hồi, nguyên nhân và action items | Có bằng chứng, owner và lần diễn tập lại |

Đừng ngắt kênh backup/WAL archiving một cách tùy tiện khi xử lý sự cố; việc bảo vệ log phục hồi và xác định chính xác target là bước ưu tiên. Các thao tác phá hủy hoặc promote trên production phải theo quyền và runbook được phê duyệt.

## 13. Những dấu hiệu hệ thống đang nhầm cache/replica với backup

| Dấu hiệu | Tại sao đáng ngại | Câu hỏi nên đặt |
| --- | --- | --- |
| “Redis đã bật AOF nên không cần backup database” | Redis chỉ giữ dữ liệu cache theo workload/eviction và không có schema/transaction của DB nguồn | Có thể restore *toàn bộ* DB về hôm qua không? |
| “Có ba replica là đủ” | Thao tác sai đã commit có thể nhân bản tới mọi node | Có điểm lịch sử độc lập trước lỗi logic không? |
| “Replica chậm sẽ cứu được DELETE nhầm” | Lag không có retention hoặc mốc ổn định | Nếu phát hiện sau 4 giờ thì sao? |
| “File backup có trên ổ primary” | Cùng miền lỗi phần cứng, ransomware, quyền xóa | Mất máy hoặc tài khoản quản trị thì file có còn không? |
| “Backup mỗi đêm nên RPO chỉ 5 phút” | Không phù hợp nếu không có WAL/PITR hoặc backup tăng tần suất | Mốc commit gần nhất có thể phục hồi thực tế là gì? |
| “Backup job báo success” | File tốt không đồng nghĩa restore đúng | Lần restore thử hoàn chỉnh cuối cùng khi nào? |
| “Health check trả 200 là khôi phục xong” | Có thể thiếu quyền, dữ liệu hoặc invariant | API đọc/ghi thiết yếu và đối soát có pass không? |
| “Chúng ta có thể dùng cache để điền lại DB” | Cache thiếu khóa, thiếu lịch sử và có thể stale | Có chứng minh tập đủ, mốc nhất quán và kiểm toán không? |

## 14. Bài tập thực hành

### Bài tập 1: replica áp dụng lỗi logic

Primary có 1 triệu đơn. Một lệnh `DELETE FROM orders` sai phạm vi đã commit và được các replica nhận đầy đủ. Hệ thống có ba replica và cache chứa 10.000 đơn gần đây. Các thành phần ấy có thể bảo đảm lấy lại 1 triệu đơn không?

**Đáp án:** không. Replica đã nhận lệnh xóa; cache không đầy đủ, có TTL và không giữ ràng buộc hay lịch sử. Cần backup độc lập phù hợp, nếu có PITR thì phục hồi tới trước lệnh sai, sau đó đối soát các transaction hợp lệ nằm ngoài target.

### Bài tập 2: “Redis có persistence”

Một cache Redis bật AOF và có replica. Team đề nghị bỏ backup PostgreSQL vì “Redis cũng lưu ra đĩa”. Có lý do nào bác bỏ?

**Đáp án:** AOF/replication của Redis bảo vệ dữ liệu **mà Redis thực sự đang giữ** theo cấu hình; nó không bảo đảm có toàn bộ bảng, quan hệ, constraint, các commit lịch sử và metadata của PostgreSQL. Nếu Redis chỉ là cache dẫn xuất, nó không được phép thay thế backup nguồn.

### Bài tập 3: read-only khi nguồn mất

DB chính không truy cập được, cache còn `order.status='PENDING'` từ 10 phút trước. Người dùng bấm thanh toán, API trả `PAID` chỉ vì đã ghi vào cache. Thiết kế sai ở đâu?

**Đáp án:** command chưa được commit ở nguồn nghiệp vụ. Việc ghi cache không tạo độ bền/atomicity cho thanh toán; có thể gây xác nhận giả hoặc xử lý lặp. Chọn fail closed, một hàng đợi bền vững có giao thức rõ nếu nghiệp vụ cho phép, hoặc failover tới leader hợp lệ với idempotency và đối soát.

### Bài tập 4: backup đúng mốc nhưng không đủ phục hồi

File `pg_dump` hợp lệ, nhưng khi restore vào môi trường mới thì ứng dụng Java lỗi vì thiếu DB role, extension và khóa giải mã. Có thể tuyên bố backup strategy đạt yêu cầu không?

**Đáp án:** chưa. Cần phục hồi cả những dependency và quyền cần thiết, kiểm tra schema, secret/TLS, khả năng chạy use case thật; diễn tập restore end-to-end mới chứng minh phục hồi vận hành.

### Bài tập 5: RPO từ backup hằng đêm

DB làm backup logic mỗi ngày 00:00, không có lưu WAL để PITR. Lúc 23:55 dữ liệu bị xóa nhầm, trong khi yêu cầu RPO chỉ 10 phút. Có đáp ứng không?

**Đáp án:** không. Bản backup gần nhất có thể thiếu gần một ngày giao dịch. Cần thiết kế WAL/PITR hoặc giải pháp bổ sung đúng RPO, retention và kiểm thử khôi phục; số replica không giải quyết lỗi xóa logic đã lan truyền.

### Bài tập 6: bản sao được giữ trễ

Team cố giữ một delayed replica trễ replay 2 giờ và gọi nó là “backup”. Lệnh xóa nhầm được phát hiện 5 giờ sau khi xảy ra. Điều gì có thể đã xảy ra?

**Đáp án:** delayed replica có thể đã replay lệnh sai; cửa sổ 2 giờ không đủ cho phát hiện sau 5 giờ. Ngay cả khi còn dữ liệu, cần quy trình đóng băng/khôi phục hợp lệ; nên có backup lịch sử độc lập, retention và PITR theo yêu cầu.

### Bài tập 7: khôi phục hai hệ thống lệch mốc

DB đơn hàng restore về T0, nhưng dịch vụ thanh toán giữ dữ liệu tới T1. Một số payment operation đã xảy ra ngoài DB đơn hàng. Có thể chỉ lấy record từ Redis để làm hai bên giống nhau không?

**Đáp án:** không. Cần đối soát theo operation/payment ID, đối chiếu provider và ledger, rồi replay/bù trừ có audit. Cache không mang snapshot nghiệp vụ nhất quán và có thể thiếu dữ liệu.

### Checklist tránh lỗi thiết kế

- **Nguồn sự thật** của mỗi loại dữ liệu đã được xác định và phân biệt với cache/read replica chưa?
- Cache có TTL/eviction, stale data và khả năng bị xóa mà không làm mất dữ liệu nghiệp vụ đúng không?
- Read replica được coi là năng lực HA/đọc; không bị dùng làm điểm lịch sử không có retention và restore plan chứ?
- Backup có được lưu **độc lập**, có version/retention, quyền xóa riêng, mã hóa và khả năng lấy khóa khôi phục không?
- Với PostgreSQL, logical/physical backup đã được tạo bằng cơ chế nhất quán, có WAL đầy đủ cho PITR yêu cầu chưa?
- RPO/RTO cho lỗi phần cứng, xóa nhầm, ransomware và failover đã được mô tả và đo riêng chưa?
- Java có ranh giới read cache/transaction, không xác nhận command chỉ nhờ ghi cache và không dùng dữ liệu stale để bảo vệ invariant chưa?
- Có restore drill ở lab: schema, roles, constraint, index, connection, secret, API đọc/ghi và dữ liệu ngoài DB không?
- Sau phục hồi, outbox, inbox, broker, ledger và tác động ngoài DB có quy trình đối soát bằng ID không?
- Có giám sát backup freshness, WAL archive health, thời gian restore thử, khả năng lấy key và cảnh báo backup lỗi không?

**Kết luận:** **Cache và read replica không phải bản sao lưu** vì chúng được thiết kế để hỗ trợ trạng thái hiện tại và khả năng phục vụ, chứ không để duy trì những điểm khôi phục lịch sử độc lập. Một lỗi logic, lệnh xóa nhầm hoặc sự cố chung miền quyền có thể làm hỏng mọi bản sao truy cập. Thiết kế persistence đáng tin cần **backup nhất quán, retention thích hợp, WAL/PITR khi cần, bảo vệ độc lập, diễn tập restore và đối soát nghiệp vụ**. Chỉ khi chứng minh có thể dựng lại database và Java service đúng dữ liệu trong RPO/RTO mong muốn, mới có cơ sở khẳng định hệ thống thực sự phục hồi được.
