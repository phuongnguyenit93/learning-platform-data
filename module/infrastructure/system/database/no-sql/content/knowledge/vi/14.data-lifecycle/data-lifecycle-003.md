# Thời điểm hết hạn logic và thời điểm dữ liệu được thu hồi vật lý trong NoSQL

## 1. Một bản ghi “hết hạn” có thực sự biến mất ngay không?

Giả sử hệ thống đăng nhập tạo một mã xác thực một lần (OTP) với thời hạn **5 phút**. Mã được phát hành lúc 10:00:00 và hết hạn lúc 10:05:00. Người dùng nhập mã lúc 10:05:02. Ứng dụng cần từ chối, ngay cả nếu bản ghi mã vẫn còn trong database.

Điều này dẫn tới hai câu hỏi **khác nhau**:

1. **Khi nào dữ liệu không còn được sử dụng theo nghiệp vụ?** Đây là thời điểm **hết hạn logic** (*logical expiration*).
2. **Khi nào bản ghi, chỉ mục hoặc vùng lưu trữ thật sự được dọn dẹp?** Đây là quá trình **xóa và thu hồi vật lý** (*physical deletion/reclamation*).

Một hệ NoSQL có thể đánh dấu dữ liệu đã hết hạn, ngăn truy vấn nhìn thấy nó, nhưng vẫn giữ các byte trên bộ nhớ hoặc đĩa trong một khoảng thời gian để chờ cơ chế quét nền, xóa bất đồng bộ hoặc compaction.

```text
10:00:00                     10:05:00
   |                            |
   v                            v
Tạo mã OTP                 Hết hạn logic
   |                            |
   +---- được phép sử dụng -----+
                                |
                                +--- không còn hợp lệ theo nghiệp vụ ---+
                                                                        |
                                                         cleanup nền có thể chạy
                                                                        |
                                                                        v
                                                           xóa khỏi cấu trúc lưu
                                                                        |
                                                                        v
                                                          thu hồi dung lượng sau đó
```

**Không được thiết kế tính bảo mật của OTP dựa trên việc job xóa sẽ chạy đúng giây 10:05:00.** Điều kiện xác thực phải kiểm tra thời hạn và trạng thái ngay khi xử lý yêu cầu. Cơ chế TTL của database là lớp quản lý vòng đời/dung lượng, không mặc nhiên là cam kết deadline nghiệp vụ.

Trong NoSQL, sự phân biệt này đặc biệt quan trọng vì nhiều hệ thống dùng lưu trữ phân tán, replica, cache, nhật ký ghi (WAL/commit log), cấu trúc LSM và các đợt dọn nền.

## 2. Mô hình thời gian: nhiều mốc, không chỉ một TTL

Khi mô tả vòng đời một bản ghi, nên phân biệt:

| Ký hiệu | Mốc thời gian | Ý nghĩa |
|---|---|---|
| \(t_w\) | Ghi dữ liệu | Bản ghi được tạo/commit |
| \(t_e\) | Hết hạn logic | Từ thời điểm này bản ghi không còn đủ điều kiện sử dụng |
| \(t_h\) | Ẩn khỏi đường đọc | Ứng dụng hoặc datastore không còn trả bản ghi như dữ liệu hợp lệ |
| \(t_d\) | Xóa khỏi tập dữ liệu hoạt động | Một thao tác delete/expiry cleanup đã áp dụng |
| \(t_r\) | Thu hồi dung lượng | Bộ nhớ, trang đĩa hoặc file lưu có thể được tái sử dụng |
| \(t_b\) | Hết tồn lưu ở các bản sao khác | Backup, snapshot, export hoặc các bản lưu liên quan đã hết hạn/xử lý theo chính sách |

Ví dụ **một** tiến trình có thể có:

```text
tw            te = th             td                  tr               tb
|---------------|-------------------|-------------------|----------------|
 ghi         hết hạn           cleanup/xóa        compaction/GC    backup hết lưu
             + ẩn đọc
```

Đây chỉ là **timeline minh họa**, không phải thứ tự bắt buộc của mọi datastore:

- Một hệ có cơ chế lazy expiration có thể chỉ xóa key khi được truy cập sau \(t_e\).
- Với MongoDB TTL index, document có thể còn xuất hiện trong truy vấn thông thường **sau \(t_e\)** cho đến khi bộ dọn nền thực sự xóa. Khi đó ứng dụng phải tự lọc thời hạn để đạt \(t_h \approx t_e\).
- Một thao tác xóa thủ công hoặc thu hồi quyền có thể làm dữ liệu không hợp lệ **trước TTL dự kiến**.
- Các replica, cache, snapshot và backup có những mốc riêng; không có một \(t_d\) hay \(t_r\) duy nhất đại diện cho toàn hệ.

Nếu thời hạn là \(T\) giây kể từ lúc ghi thì cách diễn đạt đơn giản:

\[
t_e = t_w + T
\]

Ví dụ \(T=300\) giây cho OTP phát lúc 10:00:00 dẫn đến \(t_e=10{:}05{:}00\). Công thức này không nói gì về thời điểm bộ nhớ hay đĩa được thu hồi.

### Điều kiện “còn hợp lệ” nên được viết rõ

Đối với một phiên đăng nhập có `expiresAt` và `status`, quy tắc thường là:

\[
\operatorname{usable}(x,t)
= (\operatorname{status}(x)=\text{ACTIVE})
\land (t < \operatorname{expiresAt}(x))
\land \neg \operatorname{revoked}(x)
\]

Nếu dùng biên thời gian như trên, **tại đúng thời điểm `expiresAt` bản ghi đã không hợp lệ**. Cần thống nhất dấu so sánh `<`/`<=` và cách biểu diễn thời gian ở tất cả service, tránh hai hệ có hành vi khác nhau ở ranh giới.

## 3. Những thuật ngữ dễ bị dùng lẫn

### TTL — Time to Live

**TTL** thường là khoảng thời gian một key, item hoặc giá trị được phép sống, ví dụ 300 giây. Với một số API, TTL được dùng để cấu hình **cơ chế xóa tự động**. Ở API khác, thuộc tính TTL chỉ là dữ liệu để background worker xem xét.

TTL không tự trả lời “khi nào quyền truy cập phải bị chặn” nếu hệ quản trị không cam kết che dữ liệu ngay lúc hết hạn.

### `expiresAt` — Thời điểm hết hạn tuyệt đối

`expiresAt` là một timestamp, chẳng hạn `2026-11-14T10:05:00Z`. Nó giúp ứng dụng so sánh với thời gian hiện tại, dễ đồng bộ giữa nhiều service hơn việc mỗi nơi tự tính TTL kể từ lúc nhận request.

### Retention period — Thời gian lưu giữ

**Retention** là chính sách dữ liệu được giữ trong bao lâu vì mục đích sản phẩm, vận hành hoặc quy định. Một sự kiện có thể không còn được hiển thị sau 30 ngày nhưng log kiểm toán phải giữ 180 ngày. Thời hạn truy cập và thời gian lưu giữ vì vậy có thể khác nhau.

### Tombstone — Dấu xóa

Trong một số hệ lưu trữ phân tán/LSM, thao tác xóa hoặc hết TTL được biểu diễn bằng **tombstone** để ngăn dữ liệu cũ xuất hiện trở lại khi hợp nhất bản ghi. Tombstone không nhất thiết làm dung lượng đĩa giảm ngay.

### Compaction, garbage collection, vacuum

Đây là các cơ chế dọn/cấu trúc lại dữ liệu để loại bỏ giá trị đã chết và/hoặc thu hồi chỗ lưu. **Tên gọi, thời điểm và khả năng thu hồi khác nhau theo datastore**. Không nên coi “DELETE đã thành công” là “tất cả byte trên thiết bị đã bị ghi đè”.

### Eviction khác expiration

**Eviction** là đẩy dữ liệu ra do chính sách quản lý bộ nhớ/dung lượng, có thể xảy ra **trước TTL**. **Expiration** là việc dữ liệu hết hạn theo quy tắc thời gian. Ví dụ một cache có thể xóa một key còn hạn khi thiếu RAM; đây không phải bằng chứng key đã hết hạn nghiệp vụ.

## 4. Phân biệt hai loại TTL: quản lý lưu trữ và thực thi nghiệp vụ

Trong thiết kế, cần tách rõ hai lớp:

**Lớp nghiệp vụ:** kiểm tra bản ghi còn được dùng không. Ví dụ xác thực OTP, cho phép đọc session, áp quyền truy cập, sử dụng token, chấp nhận một đơn giữ chỗ.

**Lớp lưu trữ:** dọn những bản ghi không còn cần cho luồng đọc/ghi thường xuyên, giảm áp lực dung lượng và chỉ mục. Quá trình này có thể bất đồng bộ.

```text
Request đến
     |
     v
Đọc bản ghi
     |
     v
Kiểm tra status, expiresAt, revokedAt, owner
     |
     +-- không hợp lệ --> từ chối ngay, dù record vẫn tồn tại
     |
     +-- hợp lệ ------> thực hiện thao tác có điều kiện

Song song:
TTL monitor / expire cycle / sweeper / compaction
     |
     v
Dọn dữ liệu và thu hồi tài nguyên theo chính sách
```

Một số datastore có thể che key đã quá TTL trực tiếp trong đường đọc, nhưng điều đó không làm mất nhu cầu kiểm tra **các quy tắc bổ sung** như revoked, owner, chỉ dùng một lần, trạng thái đơn hoặc legal hold.

## 5. MongoDB: TTL index xóa nền, không tự bảo đảm ẩn đúng deadline

MongoDB có **TTL index** để tự xóa document dựa trên một trường thời gian. Thông thường, một TTL index trên trường BSON Date cho phép hệ quản trị định kỳ tìm document đã hết hạn rồi xóa.

### 5.1. Lưu thời điểm hết hạn tuyệt đối

Ví dụ tạo collection các phiên xác thực:

```javascript
db.sessions.insertOne({
  _id: "SID-1001",
  userId: "U01",
  status: "ACTIVE",
  createdAt: new Date(),
  expiresAt: new Date(Date.now() + 5 * 60 * 1000),
  version: 1
});
```

Đặt TTL index:

```javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

Ở đây `expireAfterSeconds: 0` có nghĩa field `expiresAt` đã là **timestamp deadline**, thay vì thời điểm tạo cộng một khoảng TTL chung. MongoDB TTL index sử dụng thời điểm ở trường indexed để xác định ứng viên xóa.

**Điều quan trọng:** việc quét và xóa TTL diễn ra bất đồng bộ trong nền. Nó không phải timer đảm bảo xóa đúng mili giây khi `expiresAt` được chạm tới. Nếu server tải cao hoặc đang có nhiều document hết hạn, độ trễ có thể lớn hơn một chu kỳ quét.

### 5.2. Đường xác thực phải tự lọc hết hạn logic

Không nên viết:

```javascript
// KHÔNG đủ để chứng minh session còn hiệu lực.
db.sessions.findOne({ _id: "SID-1001" });
```

Vì document có thể còn trong database sau thời điểm hết hạn. Thay vào đó:

```javascript
const now = new Date();

db.sessions.findOne({
  _id: "SID-1001",
  status: "ACTIVE",
  expiresAt: { $gt: now }
});
```

Truy vấn chỉ trả phiên còn trạng thái ACTIVE và deadline nằm sau thời điểm `now`. Khi sử dụng trong ứng dụng thật, cần lấy `now` từ nguồn thời gian được kiểm soát và bảo đảm service đồng bộ đồng hồ.

**Đọc rồi xử lý riêng vẫn có race:** bản ghi còn hợp lệ tại thời điểm query có thể hết hạn trước lúc commit thao tác tiếp theo. Với quyết định quan trọng, hãy áp điều kiện hạn và trạng thái ngay trong bước ghi nguyên tử hoặc transaction phù hợp.

### 5.3. Ví dụ tiêu thụ token một lần

Giả sử token chỉ dùng được một lần và chứa `consumedAt` nếu đã sử dụng:

```javascript
const now = new Date();

const consumed = db.sessions.findOneAndUpdate(
  {
    _id: "SID-1001",
    status: "ACTIVE",
    expiresAt: { $gt: now },
    consumedAt: { $exists: false }
  },
  {
    $set: {
      status: "USED",
      consumedAt: now
    },
    $inc: { version: 1 }
  },
  { returnDocument: "after" }
);
```

Điều kiện và cập nhật diễn ra trong **một thao tác nguyên tử trên document**. Nếu không còn khớp, token đã hết hạn, bị dùng, bị thu hồi hoặc không tồn tại. Ứng dụng không nên coi kết quả không tìm thấy là bằng chứng duy nhất rằng TTL worker đã xóa.

Lưu ý về thời gian: `now` được chụp lúc tạo lệnh. Trong hệ cần deadline rất nghiêm ngặt, phải xét thời gian từ lúc tạo `now` đến lúc database thực sự xét điều kiện, đồng hồ giữa client/server, và ranh giới commit nghiệp vụ. Có thể dùng cơ chế lấy thời gian phía server hoặc giao thức thời gian phù hợp nếu yêu cầu chính xác hơn.

### 5.4. Những giới hạn khi dùng TTL index

- TTL index trong MongoDB thường dựa trên **một trường thời gian**; không nên giả định có thể kết hợp mọi kiểu compound index để biểu đạt TTL tùy ý.
- Mặc định một document chỉ mang ngày hết hạn **không có nghĩa** quy tắc `status`, `revokedAt`, `legalHold` đều được TTL monitor kiểm tra.
- Nếu cần giữ một record do legal hold, không được để nó vẫn đủ điều kiện xóa bởi TTL index; cần thay đổi thiết kế lưu giữ/thời hạn hoặc tách sang vùng lưu giữ phù hợp.
- Document hết hạn **có thể vẫn hiện trong truy vấn** cho đến khi TTL cleanup chạy. Hãy lọc bằng `expiresAt` ở đường đọc bắt buộc.
- Việc dọn một số lượng rất lớn document có thể tạo thêm tải xóa, ghi nhật ký, replication và chi phí index.
- TTL xóa document khỏi tập dữ liệu hoạt động không đồng nghĩa mọi backup hay bản snapshot chứa document lập tức bị xóa.

## 6. Redis: key hết hạn logic nhưng dọn RAM có thể đến sau

Redis hỗ trợ gắn thời gian sống trực tiếp cho key, ví dụ:

```redis
SET otp:U01:request42 "hashed-value" EX 300 NX
TTL otp:U01:request42
```

Trong ví dụ:

- `EX 300` đặt TTL 300 giây.
- `NX` chỉ đặt key nếu key chưa tồn tại, hữu ích trong một số quy tắc tạo request.
- `TTL` cho số giây còn lại theo quy tắc Redis.

Sau thời hạn, lệnh đọc đến một key đã hết hạn sẽ không trả dữ liệu cũ như một giá trị còn sống; Redis có cơ chế **passive expiration** khi truy cập và **active expiration** để dọn key hết hạn ở nền.

### 6.1. “Không đọc được” khác “đã lấy lại toàn bộ bộ nhớ”

Một key quá hạn nhưng chưa được quét hoặc truy cập có thể còn chiếm tài nguyên trong một khoảng thời gian. Điều này không có nghĩa ứng dụng nên được phép sử dụng key đó. Dùng TTL Redis chủ yếu giúp quản lý vòng đời key ở datastore, nhưng thời điểm dọn toàn bộ bộ nhớ không phải deadline nghiệp vụ có thể đem ra bảo đảm như đồng hồ.

### 6.2. Cách đọc trạng thái TTL

```redis
TTL otp:U01:request42
PTTL otp:U01:request42
EXISTS otp:U01:request42
```

Với Redis:

- `TTL` trả thời gian còn lại tính bằng giây nếu key có expiration.
- Giá trị `-1` nghĩa là key tồn tại nhưng **không có TTL**.
- Giá trị `-2` nghĩa là key **không tồn tại** (hoặc không còn được xem là tồn tại vì đã hết hạn).
- `PTTL` trả độ phân giải mili giây.

**Cảnh báo:** ứng dụng cần phân biệt key không tồn tại vì chưa tạo, đã xóa, hết TTL hoặc bị eviction. Chỉ nhìn `GET`/`EXISTS` thường không đủ biết lịch sử nguyên nhân.

### 6.3. Cập nhật TTL có thể làm thay đổi hạn

```redis
SET session:U01 "state-v1" EX 900
SET session:U01 "state-v2"
TTL session:U01
```

Một lệnh `SET` ghi đè thông thường **có thể xóa TTL đã gắn trước đó**, nếu không sử dụng tùy chọn giữ hạn hoặc đặt lại hạn rõ ràng. Điều này có thể khiến một session đáng lẽ hết hạn vẫn tồn tại lâu hơn dự kiến.

Khi cập nhật cache hoặc session, hãy chọn rõ một trong hai chính sách:

- **Sliding expiration:** hoạt động hợp lệ sẽ gia hạn thời hạn.
- **Absolute expiration:** ngày hết hạn cố định, các lần cập nhật giá trị không được làm nó dịch chuyển.

Không nên vô tình chuyển absolute TTL sang sliding TTL chỉ vì một lệnh cập nhật.

### 6.4. Đọc rồi xóa key không tự chống cạnh tranh

Đối với token chỉ dùng một lần, chuỗi:

```text
GET token
if present:
    do something
    DEL token
```

có race khi hai worker cùng đọc trước lúc xóa. Redis hỗ trợ thao tác như `GETDEL` (ở phiên bản hỗ trợ) để **lấy và xóa key trong một lệnh nguyên tử**. Tuy nhiên, khi hành động “do something” bao gồm hệ thống khác như ghi database hoặc gọi thanh toán, tính nguyên tử của `GETDEL` **không tự tạo transaction xuyên các hệ**. Cần idempotency và cơ chế xử lý lỗi tương ứng.

## 7. DynamoDB: TTL expiration là yêu cầu dọn nền, không phải bộ lọc đọc

Trong Amazon DynamoDB, TTL thường dựa trên **một thuộc tính số chứa thời gian Unix epoch tính bằng giây**. Một item có thể chứa:

```json
{
  "pk": { "S": "SESSION#U01" },
  "sk": { "S": "SID#1001" },
  "expiresAt": { "N": "1794650700" },
  "status": { "S": "ACTIVE" }
}
```

Trong ví dụ, `expiresAt` là một timestamp minh họa theo giây, không phải mili giây. Khi cấu hình TTL trên attribute này, DynamoDB có thể tự xóa item quá hạn qua quá trình nền.

**Khác biệt quan trọng với cách nghĩ “TTL là filter”:** item đã quá hạn **có thể tiếp tục tồn tại và được trả qua truy vấn/đọc** trước khi quá trình xóa nền hoàn tất. Việc xóa thường diễn ra bất đồng bộ, không có cam kết xóa ngay tại mốc Unix timestamp.

Vì thế đường đọc phiên hợp lệ phải kiểm tra:

```text
status == ACTIVE
AND expiresAt > currentEpochSeconds
AND not revoked
```

Ví dụ pseudo-code:

```python
import time

def is_usable_session(item):
    if item is None:
        return False
    return (
        item.get("status") == "ACTIVE"
        and isinstance(item.get("expiresAt"), int)
        and item["expiresAt"] > int(time.time())
        and not item.get("revoked", False)
    )
```

Trong DynamoDB, các thao tác có điều kiện như `ConditionExpression` có thể giúp bảo vệ việc cập nhật session ở nơi ghi. Chỉ dựa vào `FilterExpression` sau query không mặc nhiên giúp tránh đọc tốn tài nguyên, và **không thay thế** kiểm tra nghiệp vụ ở điểm quyết định.

### TTL theo giây, không theo mili giây

Đây là lỗi thường gặp:

```python
import time

expire_in_5_minutes = int(time.time()) + 300  # giây, phù hợp với TTL kiểu epoch seconds
wrong_units = int(time.time() * 1000) + 300000 # mili giây, KHÔNG phải epoch seconds
```

Nếu ghi timestamp mili giây vào field TTL yêu cầu giây, dữ liệu có thể không hết hạn theo kế hoạch. Ngược lại, chuyển nhầm timestamp đang tính bằng giây sang một đơn vị khác cũng có thể dẫn tới xóa sớm.

### Xóa nền và hệ sinh thái

Khi DynamoDB dọn TTL, quá trình và thời gian xử lý khác với một thao tác delete đồng bộ của ứng dụng. Nếu sử dụng DynamoDB Streams hoặc bản sao toàn cầu, cần hiểu cách các sự kiện xóa và replication được biểu diễn trong topology đang dùng. **Không nên mặc định mọi consumer và mọi replica đồng thời ngừng trả item đúng giây TTL**.

## 8. Cassandra và họ LSM: hết TTL, tombstone, compaction

Trong Apache Cassandra, dữ liệu có thể được ghi với TTL. Ví dụ một thông báo trong hộp thư có hạn 24 giờ:

```sql
CREATE TABLE notification_by_user (
    user_id text,
    notification_id timeuuid,
    body text,
    PRIMARY KEY ((user_id), notification_id)
);

INSERT INTO notification_by_user (user_id, notification_id, body)
VALUES ('U01', now(), 'Thông báo thử nghiệm')
USING TTL 86400;
```

Sau TTL, các cell đã hết hạn không còn được coi là giá trị “sống” ở đường đọc theo ngữ nghĩa của Cassandra. Nhưng trong hệ lưu trữ kiểu **LSM-tree**, dữ liệu trên đĩa thường nằm trong các file SSTable bất biến. Expiration/xóa không đơn giản là tìm một byte rồi xóa nó tại chỗ.

Quá trình khái niệm:

```text
WRITE với TTL
      |
      v
Memtable / commit log --> SSTables
                              |
                              v
                        TTL hết hạn
                              |
                              v
                     Dữ liệu không còn live
                     / tombstone semantics
                              |
                              v
                  Compaction + điều kiện GC
                              |
                              v
                  File cũ có thể được thay,
                  dung lượng có thể thu hồi
```

### Vì sao tombstone chưa thể xóa ngay?

Trong lưu trữ phân tán, xóa/expiry cần được truyền đạt cho các replica. Nếu một replica tạm thời không nhận thao tác xóa, việc dọn dấu xóa quá sớm có thể làm dữ liệu cũ **xuất hiện trở lại** khi các bản sao đồng bộ. Vì vậy các cơ chế như **grace period**, repair và compaction có liên hệ với nhau.

Các chi tiết như `gc_grace_seconds`, chiến lược compaction, thời điểm dữ liệu được purge và trách nhiệm repair phụ thuộc phiên bản và cấu hình Cassandra. **Không tự giảm grace period để lấy lại đĩa ngay** nếu chưa hiểu ảnh hưởng tới repair và dữ liệu xóa trên replica.

### Tại sao TTL quá dày gây tốn tài nguyên?

Nếu mọi bản ghi được tạo cùng lúc và cùng hết hạn, hệ thống có thể phải xử lý lượng lớn tombstone và công việc compaction. Một truy vấn quét qua nhiều cell đã hết hạn cũng có thể phát sinh chi phí đọc/kiểm tra tombstone. Đây là lý do cần thiết kế partition, TTL, chiến lược compaction và phân bố tải theo nghiệp vụ, chứ không chỉ đặt TTL rồi kỳ vọng dung lượng giảm đều.

## 9. So sánh cách các hệ NoSQL xử lý TTL

| Hệ | Cấu hình hết hạn điển hình | Sau mốc hạn, đọc có thể thấy gì? | Cách dọn thường gặp |
|---|---|---|---|
| **Redis** | TTL trên key (`EX`, `EXPIRE`) | Key quá TTL không còn được coi là sống khi truy cập; cơ chế expiry xử lý | Passive + active expiration |
| **MongoDB** | TTL index trên trường thời gian | Document **có thể còn được trả** cho đến khi bị xóa; app cần filter | TTL monitor/background deletes |
| **DynamoDB** | Attribute Unix epoch seconds, bật TTL | Item quá hạn **có thể còn được đọc** trước khi background delete | Asynchronous TTL deletion |
| **Cassandra** | TTL trên dữ liệu/cell | Giá trị quá TTL không còn live theo semantics đọc; byte có thể vẫn ở SSTable | Tombstone + compaction/purge |
| **Cache phía ứng dụng** | TTL theo memory cache/library | Tùy implementation; có thể expired-on-read hoặc background eviction | Local cleanup/eviction |

Bảng này so sánh **ý tưởng và hành vi quan trọng**, không thay thế tài liệu phiên bản/triển khai. Mỗi hệ còn có lựa chọn replication, backup, snapshot, index và ngữ nghĩa ghi khác nhau.

Kết luận từ bảng: **không nên xây một API bảo mật giả định “đã đặt TTL thì truy vấn nào cũng không thể nhìn thấy record quá hạn”**. Hãy định nghĩa điều kiện hợp lệ ở tầng nghiệp vụ rồi chọn cách hiện thực phù hợp cho từng datastore.

## 10. Thời điểm thu hồi vật lý còn phụ thuộc cách dữ liệu được lưu

### 10.1. Key-value trong RAM

Với một cache in-memory, khi key bị dọn, bộ nhớ có thể được trả về bộ cấp phát để tái sử dụng. Tuy nhiên, mức sử dụng RAM của **process/OS** không nhất thiết giảm đúng bằng kích thước key vừa xóa: allocator, fragmentation và cơ chế quản lý bộ nhớ có thể giữ vùng nhớ để sử dụng sau.

Do đó, “key đã hết hạn” và “RSS giảm ngay” là hai khái niệm khác nhau.

### 10.2. LSM-tree và file bất biến

Nhiều hệ NoSQL sử dụng **write-ahead log/commit log**, memtable và SSTable hoặc các cấu trúc tương tự:

```text
WRITE new value
   |
   v
WAL / commit log
   |
   v
Memtable --> immutable SSTable A
                           |
DELETE / EXPIRE ----> tombstone / newer version
                           |
                           v
                   Compaction later
                           |
                           v
                  SSTable B / old file cleanup
```

Giá trị cũ và tombstone có thể cùng tồn tại vật lý cho đến khi đủ điều kiện compaction/garbage collection. Việc giảm kích thước **tập dữ liệu logic** có thể diễn ra sớm hơn việc giảm lượng đĩa sử dụng.

### 10.3. Index và dữ liệu dẫn xuất

Xóa một document có thể kéo theo xóa hoặc cập nhật:

- Các index phụ.
- Materialized view/search index.
- Bộ đệm ở nhiều cấp.
- Các hàng tổng hợp nếu nghiệp vụ yêu cầu.

Không thể kết luận tất cả dữ liệu đã được dọn chỉ từ việc query collection chính không trả kết quả. Nếu index bên ngoài được cập nhật từ event, cần theo dõi version, retry, tombstone và độ trễ đồng bộ.

### 10.4. Snapshot, backup và object version

Một bản ghi đã bị xóa khỏi database hoạt động có thể vẫn tồn tại trong:

- Backup định kỳ chưa hết thời hạn lưu.
- Snapshot của storage volume.
- Export phục vụ phân tích.
- Bản sao khôi phục thảm họa.
- Log và dữ liệu dẫn xuất được quản lý độc lập.

Do đó có ít nhất hai mục tiêu khác nhau:

1. **Không còn hiển thị/được truy cập qua đường nghiệp vụ**.
2. **Không còn lưu trữ ở những nơi thuộc phạm vi yêu cầu xóa**.

Mục tiêu thứ hai cần chính sách retention, backup lifecycle, xóa theo lịch và biện pháp bảo vệ dữ liệu khi còn trong backup. Xóa logic hay compaction không tự chứng minh byte đã bị **secure erase** khỏi mọi thiết bị vật lý.

## 11. Hết hạn, xóa chủ động, thu hồi quyền và legal hold

Không phải mọi dữ liệu đều có chính sách “sống đúng T giây rồi xóa”.

| Dữ liệu | Mốc hết giá trị sử dụng | Chính sách thu hồi cần xét |
|---|---|---|
| OTP | Hết sau vài phút hoặc đã được sử dụng | Từ chối ngay; dọn key/token theo TTL |
| Session | Expiry, logout, bị thu hồi | Vô hiệu hóa ngay cả khi TTL chưa tới |
| Giỏ hàng tạm | Sau thời gian không hoạt động | Dọn bất đồng bộ; phục hồi theo nghiệp vụ nếu có |
| Dữ liệu tìm kiếm cache | Đến TTL hoặc khi source đổi | Invalidation và rebuild |
| Log vận hành | Hết retention quy định | Dọn ở storage và bản sao theo policy |
| Hồ sơ có yêu cầu xóa | Khi chính sách/quyền yêu cầu | Xóa/ẩn dữ liệu và kiểm soát hệ liên quan |
| Bản ghi đang legal hold | Theo yêu cầu giữ lại | **Không được TTL xóa** trong khi hold còn hiệu lực |
| Đơn/hóa đơn lịch sử | Hết hiệu lực giao dịch không đồng nghĩa hết nghĩa vụ lưu | Chính sách lưu trữ, bảo vệ và xóa riêng |

### Đừng dùng TTL làm cơ chế pháp lý duy nhất

Một yêu cầu xóa thông tin cá nhân có thể cần chặn truy cập ngay, xóa bản gốc, xử lý projection, cache, log và backup theo chính sách áp dụng. **TTL đến hạn trong vài ngày** có thể không phù hợp với yêu cầu chặn sử dụng dữ liệu ngay.

Ngược lại, có trường hợp pháp lý yêu cầu **giữ** dữ liệu lâu hơn TTL mặc định. Nếu MongoDB TTL index đang đánh vào `expiresAt`, một field `legalHold: true` nằm cạnh nó **không tự ngăn TTL monitor xóa**. Thiết kế phải chủ động đưa bản ghi ra khỏi điều kiện TTL hoặc chuyển sang vùng lưu giữ mà chính sách cho phép, xử lý cả race trong thời điểm bật hold.

## 12. Vòng đời bản ghi nên được mô hình hóa bằng trạng thái

Một thiết kế chỉ có `expiresAt` đôi khi không đủ diễn đạt nghiệp vụ.

Ví dụ trạng thái session:

```text
               +---------+
               | ACTIVE  |
               +----+----+
                    |
          +---------+----------+
          |                    |
      hết hạn              logout/revoke
          |                    |
          v                    v
     +---------+         +----------+
     | EXPIRED |         | REVOKED  |
     +----+----+         +----+-----+
          |                    |
          +---------+----------+
                    |
                    v
             CLEANUP_PENDING
                    |
                    v
              PHYSICALLY
                REMOVED
```

Sơ đồ là **mô hình nghiệp vụ**, không nhất thiết mỗi trạng thái đều được ghi thành document. Một key Redis hết hạn có thể không bao giờ tồn tại với field `status: "EXPIRED"`: trạng thái được suy ra từ thời gian và key có thể bị dọn nền. Nhưng khi cần audit, thông báo, điều phối hoặc xóa có điều kiện, một state machine có thể tránh nhập nhằng.

Một bản ghi có thể bị thu hồi **trước hạn**. Vì vậy điều kiện sử dụng thường không phải chỉ `now < expiresAt` mà còn phải xét `status`, `revokedAt`, `consumedAt`, tenant, quyền truy cập hoặc điều kiện khác.

## 13. Đồng hồ, múi giờ và độ chính xác thời gian

### 13.1. Dùng UTC và thống nhất đơn vị

Đối với thời hạn tuyệt đối, nên lưu timestamp rõ ràng theo UTC hoặc Unix epoch với đơn vị được quy định:

```json
{
  "sessionId": "SID-1001",
  "issuedAt": "2026-11-14T10:00:00Z",
  "expiresAt": "2026-11-14T10:05:00Z"
}
```

Sai lầm phổ biến:

- Client gửi local time không ghi timezone.
- Service A dùng **giây**, service B dùng **mili giây**.
- Thời hạn so với đồng hồ của điện thoại người dùng.
- Đổi giờ mùa hè hoặc múi giờ khi tính “hết ngày”.
- Dùng chuỗi ngày rồi so theo thứ tự từ điển không bảo đảm cùng định dạng.

Quy định ví dụ: thời hạn session là instant UTC, hết hạn khi `now >= expiresAt`. Còn dữ liệu hết hạn “cuối ngày theo giờ địa phương” phải định nghĩa rõ **ngày của vùng nào** rồi chuyển thành instant UTC.

### 13.2. Clock skew giữa các service

Trong hệ phân tán, đồng hồ có thể lệch. Nếu app server thấy 10:05:02 nhưng database server thấy 10:04:58, hai đường kiểm tra có thể khác kết quả.

Các biện pháp:

- Đồng bộ thời gian hệ thống bằng dịch vụ thời gian thích hợp.
- Chọn nguồn thời gian có thẩm quyền cho quyết định nhạy cảm.
- Tránh lấy thời gian từ client không tin cậy để cấp quyền truy cập.
- Định nghĩa rõ biên thời gian và độ trễ chấp nhận.
- Với TTL bảo mật, ưu tiên không chấp nhận token quá hạn thay vì dựa vào cleanup nền.

Không nên tuyên bố mọi hệ có cùng mốc “đúng từng mili giây” chỉ vì chúng đều lưu timestamp UTC.

### 13.3. Thời gian tường (wall-clock) và thời gian đơn điệu (monotonic)

Wall-clock phục vụ deadline tuyệt đối và log có thể bị điều chỉnh bởi đồng bộ đồng hồ. Trong một tiến trình, đo khoảng thời gian/timeout có thể dùng đồng hồ **monotonic** để tránh nhảy giờ làm sai thời lượng. Tuy nhiên, giá trị monotonic của một process không phải timestamp tuyệt đối có thể lưu trực tiếp cho các máy khác cùng hiểu.

## 14. Race khi gia hạn hạn dùng và dọn dữ liệu

Giả sử một giỏ hàng `CART-42` có `expiresAt = 10:00`. Lúc 09:59:59, người dùng thêm sản phẩm, ứng dụng muốn gia hạn đến 10:30. Cùng lúc, một cleanup worker đang xóa giỏ hết hạn.

Nếu worker làm:

```text
1. Đọc cart: expiresAt = 10:00
2. Chờ trong queue
3. DELETE cart theo ID, không kiểm tra thời hạn
```

thì sau khi người dùng đã gia hạn đến 10:30, worker vẫn có thể xóa giỏ hợp lệ.

### Xóa có điều kiện tại thời điểm thực hiện

Với MongoDB, một cleanup worker có thể dùng điều kiện deadline và version:

```javascript
const observedVersion = 7;
const cutoff = new Date();

db.carts.deleteOne({
  _id: "CART-42",
  version: observedVersion,
  expiresAt: { $lte: cutoff },
  legalHold: { $ne: true }
});
```

Nếu người dùng đã gia hạn và tăng version lên 8, `deleteOne` không khớp. Worker phải kiểm tra `deletedCount`, không được cho rằng cứ tìm thấy ID trước đó thì hiện tại vẫn được xóa.

**Giới hạn:** lệnh minh họa bảo vệ **một document** trước race ở tầng ứng dụng. Nếu datastore có cơ chế TTL riêng tự xóa dựa trên field `expiresAt`, nó có quy tắc xóa nền của hệ quản trị; trường `legalHold` trong truy vấn cleanup tùy biến không tự điều khiển TTL monitor. Khi dùng cả hai, phải đảm bảo mọi đường xóa tuân theo chính sách.

### Gia hạn session nên có ngữ nghĩa rõ

- **Absolute TTL:** thời hạn cố định từ lúc phát hành; thao tác sử dụng không được kéo dài.
- **Sliding TTL:** mỗi hoạt động hợp lệ có thể gia hạn thêm khoảng T, nhưng thường cần giới hạn tối đa để một session không sống mãi.
- **Grace period:** khoảng cho phép xử lý tác vụ đã bắt đầu trước deadline, nếu nghiệp vụ cho phép; không phải thời gian dọn vật lý.

Không nên tự hiểu “bản ghi còn trong database” là “có thể gia hạn bất cứ lúc nào”. Với session đã quá hạn, chính sách thường cần tạo một phiên mới thay vì hồi sinh phiên cũ.

## 15. Xóa mềm (soft delete) không phải thu hồi vật lý

Một kỹ thuật thường dùng là đặt:

```json
{
  "id": "DOC-88",
  "status": "DELETED",
  "deletedAt": "2026-11-14T10:05:00Z",
  "purgeAfter": "2026-12-14T10:05:00Z"
}
```

Đường đọc chỉ trả tài liệu có trạng thái còn hiệu lực; một sweeper dọn bản ghi sau `purgeAfter`. Mô hình này có ích khi cần cửa sổ khôi phục, chống xóa nhầm hoặc xử lý các phụ thuộc ngoài hệ nguồn.

Nhưng soft delete không tự:

- Giải phóng byte lưu trữ.
- Xóa nội dung khỏi cache, search index và bản sao.
- Thực thi xóa đúng mốc `purgeAfter`.
- Đáp ứng mọi yêu cầu bảo vệ dữ liệu nếu thông tin nhạy cảm vẫn được truy xuất qua đường khác.

Nếu người dùng không được phép nhìn tài liệu đã xóa, cần áp điều kiện **`status != "DELETED"` hoặc tương đương** vào mọi đường đọc có liên quan. Với API theo ID, không chỉ ẩn khỏi danh sách mà còn phải chặn truy xuất trực tiếp.

### Khi cần lưu dấu xóa để chống hồi sinh dữ liệu

Với event stream, một thông điệp cập nhật v9 có thể đến sau thông điệp xóa v10. Nếu projection đã xóa hoàn toàn ID và quên version, event v9 có thể tạo lại bản ghi.

Một tombstone kiểu:

```json
{
  "id": "DOC-88",
  "version": 10,
  "deleted": true
}
```

cho phép projector từ chối event cũ. Đây là vấn đề **thứ tự và tính đúng đắn của dữ liệu phân tán**, khác với câu hỏi tombstone ở storage engine đã được compaction hay chưa.

## 16. Backup và “xóa vĩnh viễn”: cần phát biểu chính xác

Khi một tài khoản bị xóa khỏi database chính, không nên trả lời người dùng rằng “mọi byte đã biến mất khỏi tất cả hệ thống” nếu không có cơ sở xác nhận.

Một chính sách xóa dữ liệu cần kiểm kê:

```text
Application database
    |
    +--> replicas
    +--> cache / search index
    +--> backups & snapshots
    +--> analytical warehouse / exports
    +--> event log / audit log
    +--> monitoring / error logs
```

Mỗi nhánh có cơ chế và thời gian lưu khác nhau. Một tổ chức có thể thiết kế:

1. Thu hồi quyền đọc và chặn sử dụng dữ liệu ngay theo yêu cầu.
2. Phát lệnh xóa hoặc ẩn danh tại nguồn và bản dẫn xuất.
3. Đưa yêu cầu xóa vào pipeline có kiểm tra trạng thái và retry.
4. Áp dụng chính sách retention cho backup/snapshot; bảo vệ các bản lưu trong thời gian chúng còn tồn tại.
5. Có quy trình nếu phục hồi backup chứa dữ liệu đã bị xóa: **phải phát lại/áp yêu cầu xóa trước khi phục vụ người dùng**.
6. Ghi audit tối thiểu chứng minh quá trình xử lý mà không giữ lại nội dung nhạy cảm không cần thiết.

Một số kiến trúc dùng **mã hóa theo khóa tách biệt** và tiêu hủy khóa (*cryptographic erasure*), nhưng chỉ nên dùng khi đã thiết kế và xác minh quản lý khóa, bản sao khóa, phạm vi dữ liệu và threat model. Không được mặc định “xóa khóa” là tương đương xóa mọi bản plaintext trong cache/log hoặc mọi tình huống backup.

**Thu hồi dung lượng** là mục tiêu vận hành; **xóa không thể truy cập** là mục tiêu truy cập/bảo mật; **xóa an toàn theo chính sách** còn bao gồm các bản sao, retention và kiểm toán. Ba mục tiêu không thể coi như một.

## 17. Cleanup worker: thiết kế cho tính cuối cùng, không phải deadline chính xác

Nếu datastore không có TTL index phù hợp, một dịch vụ **sweeper** có thể tìm dữ liệu quá hạn và xóa theo batch.

Pseudo-code:

```text
loop every configured interval:
    cutoff = trustedNow()

    candidates = queryByExpiryIndex(
        expiresAt <= cutoff,
        status allows purge,
        limit = batchSize
    )

    for candidate in candidates:
        deleteConditionally(
            id = candidate.id,
            version = candidate.version,
            expiresAt <= trustedNow(),
            no legal hold
        )

        record result and checkpoint

    throttle based on datastore latency and error rate
```

Một vài nguyên tắc:

- **Dùng index theo trường thời hạn** khi phù hợp; không quét toàn bộ collection liên tục chỉ để tìm record cũ.
- **Giới hạn batch và tốc độ xóa** nhằm tránh gây đột biến CPU, I/O, compaction hoặc replication lag.
- **Idempotency:** chạy lại job không được xóa nhầm record đã gia hạn.
- **Retry có backoff:** lỗi tạm thời không được làm job mất checkpoint rồi bỏ sót vĩnh viễn.
- **Kiểm tra lại điều kiện khi delete:** xử lý race với người dùng đang gia hạn hoặc chuyển legal hold.
- **Giám sát backlog:** số record quá hạn chưa purge và tuổi của record cũ nhất.
- **Không coi sweeper là công cụ bảo vệ quyền truy cập**: đường đọc vẫn phải lọc logic expiry.

### Phân vùng dữ liệu theo thời gian

Với event log lớn và retention theo ngày/tháng, có thể thiết kế dữ liệu trong **partition/bucket theo thời gian** để dọn dữ liệu theo vùng. Xóa một partition hoặc object lưu trữ theo kỳ có thể hiệu quả hơn hàng triệu delete lẻ, nhưng cách hỗ trợ phụ thuộc hệ quản trị và layout vật lý.

Nếu retention yêu cầu xóa từng người dùng độc lập, phân vùng chỉ theo thời gian có thể khiến xóa chọn lọc trở nên phức tạp. Vì vậy, **khóa phân vùng và retention policy cần được thiết kế cùng nhau**.

## 18. Vùng lưu trữ nóng, lạnh và lưu trữ lưu trữ lâu dài

Một số hệ thống không xóa ngay sau khi hết giá trị truy vấn trực tuyến. Thay vào đó, dữ liệu đi qua nhiều tầng:

```text
HOT: truy vấn trực tuyến
   |
   | sau 7 ngày
   v
WARM: truy vấn chậm hơn, ít index
   |
   | sau 90 ngày
   v
COLD / ARCHIVE: lưu vì audit/quy định
   |
   | sau retention hợp lệ
   v
PURGE theo chính sách
```

Các mốc 7/90 ngày chỉ là ví dụ. **Hết hạn ở tầng hot** không có nghĩa dữ liệu phải bị xóa khỏi mọi tầng. Cần xác định:

- Khi nào bản ghi không còn được phục vụ qua API thông thường?
- Khi nào chuyển sang archive, ai được xem?
- Bản hot có được xóa sau khi archive thành công không?
- Khi nào dữ liệu phải được xóa khỏi archive và backup?
- Nếu phải giữ lâu hơn vì legal hold, hệ thống thay đổi vòng đời thế nào?

Trong NoSQL, dữ liệu có thể được tổ chức tối ưu theo access pattern; retention theo thời gian là một trong những access pattern quan trọng của thiết kế lưu trữ.

## 19. Đo lường: biết key “đã hết hạn” chưa đủ

Monitoring nên phân biệt **độ trễ hiển thị**, **độ trễ xóa**, và **hiệu quả thu hồi tài nguyên**.

| Metric gợi ý | Ý nghĩa |
|---|---|
| `expired_but_readable_total` | Bản đã quá deadline nhưng vẫn lọt đường đọc nghiệp vụ — phải bằng 0 với quy tắc nghiêm ngặt |
| `expiry_visibility_violation_total` | Yêu cầu sử dụng token/session quá hạn được chấp nhận sai |
| `expired_pending_cleanup_count` | Số record hết hạn còn chờ dọn |
| `oldest_expired_age_seconds` | Tuổi bản ghi hết hạn cũ nhất chưa dọn |
| `ttl_delete_rate` | Tốc độ xóa từ worker TTL/sweeper |
| `cleanup_failure_rate` | Lỗi thao tác dọn dữ liệu |
| `compaction_backlog_bytes` | Dữ liệu/việc compaction còn chờ theo engine |
| `storage_live_bytes_estimate` | Dung lượng dữ liệu đang sống ước tính |
| `disk_used_bytes` | Dung lượng đĩa thực dùng, có thể chậm giảm |
| `replication_lag_seconds` | Chậm đồng bộ delete/expiry qua replica |
| `cache_stale_entry_count` | Bản cache lẽ ra không được phục vụ |
| `backup_retention_overdue_count` | Bản lưu vượt chính sách, nếu hệ có khả năng đo |

Định nghĩa hai độ trễ:

\[
L_{\text{cleanup}} = t_d - t_e
\]

\[
L_{\text{reclaim}} = t_r - t_e
\]

Hai đại lượng này khác nhau và có thể không quan sát trực tiếp từng record, đặc biệt ở storage engine có compaction và backup. Khi đo, cần nêu rõ \(t_d\) là **đã xóa khỏi tập dữ liệu hoạt động nào**, còn \(t_r\) là **dung lượng trên tầng lưu trữ nào**.

### Không gắn ID bản ghi vào nhãn metric

Ví dụ không tạo một time series riêng cho từng `sessionId` hay `userId` trong hệ metric, vì cardinality và rủi ro lộ dữ liệu. Có thể lưu thống kê theo loại dữ liệu, shard, tenant nhóm hoặc mức độ trễ; chi tiết bản ghi dùng hệ audit có quyền truy cập phù hợp.

### Mục tiêu dịch vụ minh họa

Một hệ thống có thể đặt:

- **Tính hợp lệ nghiệp vụ:** 100% OTP quá hạn bị từ chối theo clock/điều kiện quy định.
- **Cleanup:** 99% key/bản ghi đủ điều kiện dọn được xóa khỏi tập dữ liệu hoạt động trong vài phút.
- **Thu hồi đĩa:** dung lượng sau compaction có xu hướng giảm trong khung vận hành chấp nhận được.
- **Backup:** bản lưu bị dọn theo chính sách retention riêng, có quy trình xử lý xóa khi restore.

Đây là mục tiêu ví dụ, **không phải bảo đảm mặc định của Redis, MongoDB, DynamoDB hoặc Cassandra**. Mục tiêu phải gắn với topology, workload, quy định và chi phí thực tế.

## 20. Kiểm thử vòng đời bằng đồng hồ giả và tình huống hỏng

Không nên chỉ viết test kiểu “`sleep(301 seconds)` rồi xem record còn không”. Cách này chậm, dễ flake và kiểm tra lẫn lộn logic nghiệp vụ với cleanup engine.

### 20.1. Unit test cho logic expiry

Tách hàm kiểm tra thời hạn và cho phép truyền clock:

```java
import java.time.Clock;
import java.time.Instant;

public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isUsable(Instant expiresAt, boolean revoked) {
        return !revoked
                && expiresAt != null
                && clock.instant().isBefore(expiresAt);
    }
}
```

Một số case cần kiểm tra:

```text
now = 10:04:59, expiresAt = 10:05:00, revoked=false  -> true
now = 10:05:00, expiresAt = 10:05:00, revoked=false  -> false
now = 10:05:01, expiresAt = 10:05:00, revoked=false  -> false
now = 10:04:00, expiresAt = 10:05:00, revoked=true   -> false
expiresAt missing/null                                 -> false theo policy này
```

Trong unit test, dùng `Clock.fixed(...)` để kiểm tra ranh giới thời gian chính xác mà không phải chờ thực.

### 20.2. Integration test cho datastore

Với MongoDB, kiểm tra hai hành vi **riêng**:

1. API đọc theo `expiresAt` phải từ chối ngay sau deadline dù document còn tồn tại.
2. TTL index thực sự được cấu hình và cleanup nền cuối cùng xóa document, nhưng **không dùng timeout quá ngắn để kết luận sai về tính năng TTL**.

Với Redis, kiểm tra TTL còn hiệu lực sau các thao tác cập nhật key, tránh vô tình xóa TTL. Với Cassandra, đo tác động của tombstone/compaction; với DynamoDB, không mong background delete xảy ra tức thời trong integration test.

### 20.3. Failure scenarios

Hệ thống nên được thử với:

- Gia hạn TTL đồng thời với cleanup.
- Reader và writer có clock skew.
- Dữ liệu bị revoke trước expiresAt.
- TTL expired event đến chậm hoặc lặp.
- Service xử lý key không tồn tại do eviction, không chỉ do expiry.
- Replica hoặc cache vẫn mang bản cũ.
- Restore backup chứa dữ liệu đã bị xóa và chạy quy trình tái áp dụng delete.
- Retention đổi trong lúc có backfill/migration.
- Đột biến hàng triệu record cùng hết hạn một thời điểm.

## 21. Những sai lầm dễ gặp và cách tránh

| Sai lầm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Coi deadline TTL là lịch xóa chính xác từng giây | Đọc nhầm record quá hạn trên MongoDB/DynamoDB | Lọc `expiresAt` và trạng thái ở đường nghiệp vụ |
| Coi xóa logic là đã giải phóng đĩa | Dung lượng không giảm, dự báo sai | Theo dõi compaction/GC và disk metrics |
| Không kiểm tra revoke/logout vì key còn TTL | Session đã thu hồi vẫn sử dụng được | Điều kiện `revoked`/`status` độc lập |
| Dùng mili giây cho thuộc tính DynamoDB TTL yêu cầu giây | Item sống quá lâu | Chuẩn hóa đơn vị và test timestamp |
| Ghi `SET` vào Redis mà quên giữ/đặt lại TTL | Key mất thời hạn | Quy định sliding/absolute expiration |
| Dùng MongoDB TTL index để bảo vệ legal hold | Bản ghi có hold vẫn có thể bị xóa | Thay đổi mô hình lưu/điều kiện TTL trước khi hold |
| Xóa cứng từ snapshot đọc cũ | Xóa record đã được gia hạn | Delete có điều kiện deadline + version |
| Bỏ tombstone quá sớm trong hệ phân tán | Bản cũ có thể xuất hiện lại | Cấu hình grace/repair/compaction phù hợp |
| Chỉ xóa ở primary mà quên search/cache/backup | Dữ liệu còn truy cập qua nhánh khác | Quy trình lan truyền và kiểm tra xóa xuyên hệ |
| Dùng một TTL chung cho mọi loại dữ liệu | Vi phạm retention hoặc lãng phí lưu trữ | Chính sách theo loại dữ liệu và nghiệp vụ |
| Đột ngột xóa hàng triệu bản cùng lúc | Tăng I/O, độ trễ, tombstone/backlog | Batch, throttle, partition theo thời gian |
| Chỉ kiểm tra `GET` không thấy key rồi khẳng định secure erase | Không có bằng chứng byte/bản lưu đã biến mất | Tách mục tiêu truy cập, thu hồi dung lượng và xử lý bản sao |

## 22. Bài tập thực hành

### Bài 1 — Phân biệt các mốc

Một token được tạo lúc 09:00, TTL 10 phút. Người dùng gọi API lúc 09:11. Job dọn chạy 09:15 và compaction hoàn thành 10:00.

Hãy xác định:

- Thời điểm token hết hạn logic.
- Token có được phép dùng lúc 09:11 không?
- Job dọn đã thực hiện lúc nào?
- Có được kết luận tất cả backup đã xóa token lúc 10:00 không?

*Gợi ý:* Token hết hạn 09:10; 09:11 phải bị từ chối; cleanup và compaction xảy ra sau; trạng thái backup cần chính sách riêng.

### Bài 2 — Truy vấn session trong MongoDB

Cho collection:

```javascript
{
  _id: "SID-2",
  status: "ACTIVE",
  expiresAt: ISODate("2026-11-14T10:05:00Z")
}
```

Viết truy vấn chỉ trả session còn hạn. Giải thích vì sao `findOne({_id:"SID-2"})` chưa đủ và vai trò của TTL index `{expireAfterSeconds: 0}`.

### Bài 3 — Redis TTL mất sau cập nhật

Một session được ghi bằng `SET session:U01 ... EX 600`. Sau hai phút, code cập nhật bằng `SET session:U01 ...` không đặt TTL. Hãy nêu rủi ro và cách định nghĩa chính sách giữ nguyên thời hạn hay gia hạn có chủ ý.

### Bài 4 — DynamoDB TTL sai đơn vị

Một service dùng `Date.now()` trong JavaScript để tạo `expiresAt` cho DynamoDB. Vì sao kết quả có thể sai khi đem dùng làm Unix epoch seconds? Viết công thức chuyển sang giây và cộng thời hạn 5 phút.

*Gợi ý:* `Math.floor(Date.now() / 1000) + 300`.

### Bài 5 — Cassandra và tombstone

Một bảng thông báo đặt TTL 24 giờ. Đúng 24 giờ sau, API không còn thấy thông báo, nhưng dung lượng đĩa chưa giảm. Giải thích vai trò của SSTable, tombstone, grace period và compaction. Tại sao không nên tự giảm grace period nếu chưa xem chiến lược repair?

### Bài 6 — Gia hạn đúng lúc dọn

Giỏ hàng `CART-42` ở version 7 hết hạn lúc 10:00. Worker lấy ứng viên xóa lúc 10:01; người dùng đã gia hạn thành version 8 đến 10:30. Viết điều kiện `deleteOne` để worker không xóa nhầm giỏ đã gia hạn.

### Bài 7 — Xóa dữ liệu người dùng

Một tài khoản bị xóa khỏi database chính nhưng còn dữ liệu trong search index và backup tháng trước. Hãy phân biệt “không còn phục vụ trên API”, “đã thu hồi dung lượng ở database chính”, “đã hết dữ liệu ở backup”. Đề xuất cách quản lý yêu cầu xóa khi khôi phục backup.

### Bài 8 — Thiết kế retention

Hệ thống chứa OTP (5 phút), giỏ hàng (7 ngày), log truy cập (90 ngày) và hóa đơn cần lưu lâu hơn theo chính sách. Hãy đề xuất cho mỗi loại:

- Deadline logic nếu có.
- Cơ chế dọn phù hợp (TTL, sweeper, partition retention).
- Yêu cầu đối với snapshot/backup.
- Có cần thu hồi tức thời khi bị revoke không?

## 23. Kết luận

Trong vòng đời dữ liệu NoSQL, **thời điểm hết hạn logic** và **thời điểm dữ liệu được thu hồi vật lý** là hai khái niệm riêng:

- **Logical expiry** quyết định dữ liệu còn được sử dụng theo nghiệp vụ hay không. Nó phải được thực thi ở đường truy vấn/ghi phù hợp, dựa trên deadline, trạng thái và quyền truy cập.
- **TTL cleanup** là cơ chế dọn dữ liệu có thể chạy nền. MongoDB và DynamoDB có thể còn trả bản ghi đã quá hạn trước khi xóa; Redis có cơ chế expiry ở đường truy cập và nền; Cassandra có tombstone và compaction.
- **Physical reclamation** phụ thuộc storage engine, bộ cấp phát, compaction, replica, index và backup. Dữ liệu không còn nhìn thấy **không chứng minh** mọi byte đã bị xóa an toàn.
- **Retention, legal hold, thu hồi quyền và xóa dữ liệu cá nhân** cần chính sách độc lập, có quy trình bảo vệ và đối soát xuyên các bản lưu.

Thiết kế tốt bắt đầu bằng ba câu hỏi: **“Từ lúc nào bản ghi không được dùng?”, “Khi nào và bằng cơ chế nào hệ thống dọn nó?”, “Những bản sao và byte lưu trữ còn tồn tại đến bao giờ?”** Trả lời riêng từng câu hỏi giúp hệ NoSQL vừa đúng nghiệp vụ, vừa kiểm soát dung lượng và rủi ro dữ liệu lâu dài.
