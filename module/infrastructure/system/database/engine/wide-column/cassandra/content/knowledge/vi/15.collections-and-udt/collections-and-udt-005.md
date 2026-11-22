# Map key/value, phần tử không tồn tại và cập nhật có điều kiện trong Apache Cassandra

> **Chương:** Collection và UDT  
> **Mô-đun:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, cơ sở dữ liệu wide-column phân tán. Bài học gắn thao tác `map<K,V>` với khóa phân vùng, thiết kế bảng theo truy vấn, mức nhất quán, replication, repair/compaction và kết nối Java.

## 1. Tình huống: một khóa cấu hình chưa tồn tại nghĩa là gì?

Giả sử ứng dụng học trực tuyến lưu một số tùy chọn theo người dùng:

```text
user_id = 11111111-1111-4111-8111-111111111111
settings = {
  'language': 'vi',
  'theme':    'dark'
}
```

Ứng dụng có thể cần thêm `timezone`, đổi `theme`, chỉ đổi `language` khi phiên bản dữ liệu chưa thay đổi, hoặc tạo một tùy chọn **nếu khóa đó chưa có**. Những yêu cầu này nhìn giống nhau nhưng có ba khái niệm tồn tại khác nhau:

1. **Hàng có tồn tại?** Có dữ liệu sống cho primary key `user_id` hay chưa?
2. **Cột map có giá trị?** `settings` đang có entry nào hay là `null`/rỗng?
3. **Khóa con có tồn tại?** Trong map hiện tại có entry với key `'timezone'` hay chưa?

Cassandra cung cấp `IF EXISTS` và `IF NOT EXISTS` cho **sự tồn tại của hàng** trong câu lệnh tương ứng. Chúng không đồng nghĩa với “khóa con của map đã/chưa tồn tại”. Nếu bài toán đòi thao tác có điều kiện tại **một khóa map cụ thể**, cần chọn cơ chế phù hợp: kiểm soát phiên bản cả hàng bằng *lightweight transaction* (LWT), hoặc mô hình mỗi khóa là một hàng để có thể `INSERT ... IF NOT EXISTS` trực tiếp trên khóa đó.

## 2. `map<K,V>` là gì và nên dùng khi nào?

`map<K,V>` ánh xạ **khóa duy nhất** kiểu `K` đến **giá trị** kiểu `V`. Một map không giữ thứ tự chèn để ứng dụng sử dụng như một danh sách; các entry được so sánh/sắp theo khóa tùy kiểu. Giá trị có thể lặp ở nhiều khóa, còn mỗi khóa chỉ có một giá trị tại trạng thái quan sát được.

```sql
-- Map từ tên tùy chọn tới giá trị văn bản.
settings map<text, text>
```

| Yêu cầu nghiệp vụ | `map<text,text>` có phù hợp? | Lý do |
| --- | --- | --- |
| Mỗi người dùng có tối đa vài chục thuộc tính linh hoạt | Có thể phù hợp | Đọc cả map theo `user_id`, cập nhật theo khóa con |
| Đổi một thuộc tính đã biết tên | Có | Có cú pháp cập nhật entry |
| Cần giữ thứ tự người dùng nhập các thuộc tính | Không tự đáp ứng | Map không mang thứ tự nghiệp vụ |
| Cần truy vấn tất cả người dùng có `theme = dark` | Cần mô hình đọc/index riêng | Partition key `user_id` không phục vụ truy vấn ngược đó |
| Hàng trăm nghìn khóa, cần phân trang khóa | Không nên | Collection lớn trong một hàng; không phân trang thành hàng độc lập |
| Mỗi khóa có lịch sử, TTL, owner và lifecycle riêng | Cân nhắc bảng riêng | Thuận lợi cho định danh/điều kiện theo từng mục |

Khóa và giá trị của collection không dùng `null` làm một phần tử hợp lệ. Để biểu diễn **không có key**, hãy xóa entry, không cố gán `settings['key'] = null`. Nếu các trường luôn cố định và khác kiểu (`notifications_enabled boolean`, `font_size int`), các cột vô hướng hoặc UDT có thể rõ nghĩa hơn `map<text,text>`.

## 3. Tạo schema, dữ liệu mẫu và truy vấn map

Các ví dụ dưới đây giả định keyspace `app` đã tồn tại với replication được cấu hình theo môi trường. Dùng `revision` để minh họa cập nhật có điều kiện; nó là **số phiên bản do ứng dụng quản lý**, không phải kiểu `counter` của Cassandra.

```sql
CREATE TABLE app.user_preferences (
    user_id uuid PRIMARY KEY,
    settings map<text, text>,
    revision int
);

INSERT INTO app.user_preferences (user_id, settings, revision)
VALUES (
    11111111-1111-4111-8111-111111111111,
    {'language':'vi', 'theme':'dark'},
    1
);

-- Đọc toàn map và phiên bản đang lưu.
SELECT settings, revision
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Lấy riêng giá trị của khóa theme từ collection.
SELECT settings['theme'] AS theme
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Trong CQL, `{key: value}` là literal của `map`; chú ý dấu `:` giữa key/value. Các truy vấn trên **giới hạn theo primary key**. Chọn một entry trong phần `SELECT` không biến entry đó thành khóa phân vùng và cũng không làm map có khả năng phân trang từng phần tử.

## 4. Đọc một khóa không tồn tại

Trạng thái mẫu chưa có key `'timezone'`:

```sql
SELECT settings['timezone'] AS timezone
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Biểu thức chọn entry chưa có giá trị sẽ cho kết quả **`null` ở trường được chọn** (khi hàng vẫn tồn tại). Tuy nhiên, **đừng suy luận từ một giá trị `null` duy nhất** rằng chắc chắn khóa map đang thiếu:

- Có thể key `'timezone'` chưa từng được ghi hoặc đã bị xóa/hết TTL.
- Có thể toàn bộ cột `settings` không có giá trị.
- Có thể chính hàng `user_id` không tồn tại; khi đó truy vấn `SELECT ... WHERE user_id = ...` trả về **không có hàng**, khác với “có hàng nhưng trường được chọn là null”.

Để phân biệt những trường hợp trên, ứng dụng cần kiểm tra sự tồn tại của `Row`, đọc các cột liên quan (`settings`, `revision`) và định nghĩa rõ ngữ nghĩa “chưa cấu hình”, “dùng mặc định”, “đã xóa”. Không dùng giá trị `null` giả như một giá trị map để lưu thông tin vắng mặt.

Ví dụ trong Java Driver 4.x:

```java
Row row = session.execute(selectStatement.bind(userId)).one();
if (row == null) {
    // Không tìm thấy hàng có primary key tương ứng.
} else {
    Map<String, String> settings = row.getMap(
        "settings", String.class, String.class
    );
    if (settings == null || !settings.containsKey("timezone")) {
        // Hàng có, nhưng timezone chưa được lưu trong map.
    }
}
```

Đoạn code giả định `selectStatement` là prepared statement của `SELECT settings ... WHERE user_id = ?`, và `userId` là `UUID`; việc không có key nên là một nhánh nghiệp vụ bình thường thay vì lỗi được nuốt âm thầm.

## 5. Thêm khóa mới: `UPDATE` là upsert

```sql
-- Nếu timezone chưa có, tạo entry mới. Nếu đã có, thay giá trị cũ.
UPDATE app.user_preferences
SET settings['timezone'] = 'Asia/Ho_Chi_Minh'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Gộp nhiều entry vào map hiện có; khóa trùng sẽ được cập nhật.
UPDATE app.user_preferences
SET settings = settings + {'font':'large', 'theme':'light'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Hai lệnh trên là thao tác **thêm hoặc cập nhật (upsert)**, không phải “chỉ thêm khi khóa chưa có”. Trong Cassandra, `UPDATE` thông thường cũng có thể tạo dữ liệu cho **một hàng chưa tồn tại** nếu có đủ primary key. Vì vậy câu lệnh có thể làm xuất hiện hàng mới mà trước đó ứng dụng chưa khởi tạo `revision`.

Nếu yêu cầu là **không được tạo hàng mới**, cân nhắc `UPDATE ... IF EXISTS`; nếu yêu cầu là **không ghi đè key map đang có**, `IF EXISTS` một mình vẫn chưa đủ. Phần sau trình bày CAS theo `revision` và cách chuyển mỗi entry thành một hàng khi điều kiện cần gắn trực tiếp với khóa con.

### Ghi một khóa khác với thay toàn map

```sql
-- Cập nhật một entry: các key khác không bị thay bởi câu lệnh này.
UPDATE app.user_preferences
SET settings['theme'] = 'light'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Thay toàn bộ map: key không có trong literal mới sẽ không còn.
UPDATE app.user_preferences
SET settings = {'theme':'light'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Đây là hai ý định nghiệp vụ khác nhau. Lệnh đầu **patch một thuộc tính**; lệnh thứ hai **đặt trạng thái cuối cùng của toàn bộ map**. Với non-frozen map, Cassandra quản lý các entry theo cell riêng, nên patch key phù hợp hơn khi nhiều client sửa các khóa khác nhau. Thay toàn map có thể tạo thông tin xóa che các entry cũ, làm tăng tombstone, và dễ ghi đè thay đổi của client khác nếu dùng snapshot cũ.

## 6. Xóa một key không tồn tại: nhìn như không đổi nhưng vẫn có chi phí

```sql
-- Xóa entry có key theme.
DELETE settings['theme']
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Xóa key được giả định là chưa tồn tại.
DELETE settings['does_not_exist']
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Xóa cả cột map, khác hoàn toàn với xóa một entry.
DELETE settings
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Trong kết quả đọc của ứng dụng, xóa một key không có sẵn có thể nhìn như **không thay đổi gì**. Nhưng một lệnh xóa không nhất thiết là *no-op* ở mức lưu trữ: Cassandra có thể ghi **tombstone** cho entry nhằm bảo đảm giá trị cũ từ replica/SSTable không xuất hiện lại. Tombstone được xem xét khi đọc và khi compaction; lặp xóa những key không tồn tại ở tần suất cao vẫn có thể tạo tải vận hành.

Đừng thực hiện chiến lược “xóa một key bất kỳ mỗi khi request đến” mà không cần thiết. Nếu cần phân biệt “khóa không có sẵn” và “khóa vừa bị xóa thành công”, phải xây dựng cơ chế trạng thái/điều kiện riêng; `DELETE` thông thường không trả về một cờ xác nhận key đã tồn tại từ trước.

## 7. Cập nhật có điều kiện: điều kiện kiểm tra hàng khác điều kiện kiểm tra key

### 7.1. `INSERT ... IF NOT EXISTS` có phạm vi hàng

```sql
-- Thử tạo hàng có primary key user_id nếu hàng chưa tồn tại.
INSERT INTO app.user_preferences (user_id, settings, revision)
VALUES (
    22222222-2222-4222-8222-222222222222,
    {'theme':'dark'},
    1
)
IF NOT EXISTS;
```

Đây là **lightweight transaction (LWT)**; kết quả có cột `[applied]` báo việc ghi có vượt qua điều kiện hay không. `IF NOT EXISTS` kiểm tra **hàng theo primary key** `user_id`. Nó **không** có nghĩa “thêm key `'theme'` nếu chưa tồn tại trong map của một hàng đã có”. Nếu user đã có hàng dù map chưa chứa key `'theme'`, `INSERT ... IF NOT EXISTS` không thực hiện thay đổi mong muốn.

### 7.2. `UPDATE ... IF EXISTS` cũng kiểm tra hàng

```sql
-- Chỉ cập nhật entry khi hàng theo user_id đã tồn tại.
UPDATE app.user_preferences
SET settings['theme'] = 'dark'
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;
```

Lệnh này chặn trường hợp không có **hàng**. Nhưng nếu hàng đã có và `settings['theme']` đang thiếu, nó **vẫn có thể tạo key `theme`**. Nếu key đã có, nó vẫn có thể ghi đè. Cần tránh diễn giải `IF EXISTS` thành một phép kiểm tra tồn tại của phần tử map.

| Câu lệnh | Điều kiện thực sự | Không tự bảo đảm |
| --- | --- | --- |
| `INSERT ... IF NOT EXISTS` | Hàng có primary key đó chưa tồn tại | Một key con chưa tồn tại trong hàng đã có |
| `UPDATE ... IF EXISTS` | Hàng có primary key đó tồn tại | Key con đã tồn tại hoặc vẫn giữ giá trị cũ |
| `UPDATE ... IF revision = N` | Giá trị cột `revision` trong hàng bằng `N` | Những writer không tuân theo cùng quy trình phiên bản |
| `UPDATE` không `IF` | Không kiểm tra CAS | Ngăn tạo hàng, ngăn ghi đè key |

### 7.3. Cần “chỉ thêm key mới” thì làm thế nào?

Có hai hướng, tùy đặc tính truy vấn:

1. **Giữ map nhỏ trong một hàng:** đọc trạng thái map và `revision`, kiểm tra key chưa có ở tầng ứng dụng, sau đó **CAS trên `revision`**. Khi CAS thất bại, đọc lại và quyết định theo trạng thái mới. Mọi writer sửa map phải tuân thủ cơ chế tăng phiên bản để điều kiện này có ý nghĩa.
2. **Tạo một hàng riêng cho mỗi key:** thiết kế primary key gồm `user_id` và `preference_key`; lúc này `INSERT ... IF NOT EXISTS` kiểm tra đúng sự tồn tại của **entry nghiệp vụ** tương ứng với khóa đó.

Không dùng quy trình đơn thuần **`SELECT` rồi `UPDATE`** để bảo đảm key chưa tồn tại nếu có nhiều client đồng thời: hai client có thể cùng đọc “thiếu key” rồi cùng ghi. Consistency level `QUORUM` không tự biến hai lệnh đó thành giao dịch đọc-sửa-ghi có điều kiện.

## 8. CAS theo phiên bản hàng: giữ map nhưng kiểm soát tranh chấp

Giả sử hàng đang có `revision = 1` và `settings = {'language':'vi','theme':'dark'}`. Client A muốn chuyển `theme` sang `light`, nhưng **chỉ nếu không ai sửa trạng thái hàng kể từ lúc A đọc**.

```sql
-- Tại thời điểm A đọc:
SELECT settings, revision
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- A thử cập nhật entry và tăng revision trong cùng lệnh có điều kiện.
UPDATE app.user_preferences
SET settings['theme'] = 'light', revision = 2
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF revision = 1;
```

Nếu điều kiện đúng, Cassandra thực hiện mutation và trả `[applied] = true`. Nếu một writer khác đã đổi revision, điều kiện không còn đúng và `[applied] = false`; client phải quyết định đọc lại và hiển thị xung đột, thử lại với revision mới, hoặc từ chối thao tác. **Không gửi lặp vô hạn cùng revision cũ** và không bỏ qua cờ `[applied]`.

Để biến “chỉ thêm key khi chưa có” thành nghiệp vụ chắc chắn bằng quy trình này:

1. Client đọc map, xác nhận key mục tiêu chưa có, lấy `revision` hiện tại.
2. Client gửi `UPDATE ... SET settings['new_key'] = ..., revision = revision_moi ... IF revision = revision_cu`.
3. Nếu `[applied] = false`, client đọc lại toàn bộ trạng thái cần thiết. Nếu key đã xuất hiện, trả về kết quả “key đã tồn tại”; nếu chưa có, cân nhắc retry với revision mới.
4. **Mọi code path ghi map phải đồng thời quản lý `revision`**. Một writer cập nhật entry bằng `UPDATE` không điều kiện mà không đổi revision có thể phá vỡ bảo đảm của giao thức.

Không dùng cú pháp `revision = revision + 1` như một phép tăng số bình thường trên cột `int` trong `SET`: Cassandra không hỗ trợ cập nhật kiểu counter cho một cột `int` tùy ý theo cách đó. Ứng dụng tính `revision_moi = revision_cu + 1` rồi gửi giá trị mới; với sản phẩm thực tế, xử lý tràn phiên bản và khởi tạo version một cách rõ ràng.

**Giới hạn cần hiểu:** CAS theo phiên bản này kiểm tra **cả hàng**. Hai client sửa hai khóa map khác nhau vẫn cạnh tranh trên `revision`, dù mỗi entry có thể cập nhật độc lập nếu dùng mutation thường. Sự đánh đổi này có thể chấp nhận được với map nhỏ và tần suất ghi thấp, nhưng dễ trở thành nút thắt ở hàng nhiều writer.

## 9. Thiết kế thay thế: mỗi key/value là một hàng để CAS đúng key

Nếu mỗi key cần **độc lập về điều kiện tồn tại, xóa, TTL, owner hoặc lịch sử**, hãy đưa nó vào primary key của một bảng đọc riêng:

```sql
CREATE TABLE app.preference_by_user_key (
    user_id uuid,
    preference_key text,
    preference_value text,
    PRIMARY KEY ((user_id), preference_key)
);

-- Nếu hàng (user_id, preference_key) chưa tồn tại, thêm một key mới.
INSERT INTO app.preference_by_user_key
    (user_id, preference_key, preference_value)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'theme',
    'dark'
)
IF NOT EXISTS;

-- Chỉ đổi giá trị nếu giá trị hiện tại khớp điều kiện.
UPDATE app.preference_by_user_key
SET preference_value = 'light'
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND preference_key = 'theme'
IF preference_value = 'dark';

-- Đọc một key cụ thể, truy cập qua đầy đủ primary key.
SELECT preference_value
FROM app.preference_by_user_key
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND preference_key = 'theme';

-- Hoặc đọc tất cả key của một user (nếu partition được giới hạn kích thước).
SELECT preference_key, preference_value
FROM app.preference_by_user_key
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Ở mô hình này, câu `INSERT ... IF NOT EXISTS` thực sự kiểm tra **khóa nghiệp vụ** `(user_id, preference_key)`, bởi mỗi key là một hàng. `UPDATE ... IF preference_value = 'dark'` cũng kiểm tra trực tiếp giá trị hiện tại của hàng đó. Không cần một `revision` chung chỉ để ngăn hai writer thay cùng entry. Đổi lại, ứng dụng quản lý nhiều hàng và cần cân nhắc kích thước partition nếu một user có cực nhiều tùy chọn.

Nếu cần phân trang hàng, clustering key `preference_key` tạo các hàng có thứ tự theo khóa; thứ tự đó **không phải thứ tự do người dùng kéo thả**. Nếu cần tìm tất cả user có một cặp key/value, bảng trên vẫn **chưa** phục vụ trực tiếp chiều truy vấn đó; cần thêm bảng được phân vùng theo thuộc tính hoặc chiến lược index phù hợp workload.

## 10. LWT, Paxos và các mức nhất quán

Trong Cassandra, các câu lệnh có `IF` kích hoạt **lightweight transaction** để kiểm tra điều kiện và quyết định ghi trên phạm vi dữ liệu liên quan bằng cơ chế đồng thuận kiểu Paxos. Đường đi này có thêm các vòng trao đổi giữa replica so với `UPDATE` thông thường, nên **độ trễ và chi phí điều phối thường lớn hơn**. Đừng dùng LWT cho mọi thao tác chỉ vì muốn “an toàn hơn” khi không có điều kiện nghiệp vụ cần thiết.

Hai loại consistency cần phân biệt:

- **Consistency level thông thường** (`ONE`, `LOCAL_QUORUM`, `QUORUM`, ...): chi phối mức xác nhận đọc/ghi thông thường theo replication và phạm vi datacenter.
- **Serial consistency** (`SERIAL`, `LOCAL_SERIAL`): liên quan pha đồng thuận của thao tác có điều kiện; cần chọn phù hợp với phạm vi datacenter và quy tắc triển khai.

LWT không tự tạo giao dịch nhiều bảng/mọi partition theo mô hình ACID tổng quát. Nếu chương trình muốn cập nhật đồng thời bảng `user_preferences` và bảng truy vấn ngược, cần thiết kế nhất quán giữa các bảng và xử lý lỗi/trạng thái một cách chủ đích. Khi LWT timeout, client cũng phải làm rõ **kết quả có được chấp nhận không**, tránh suy diễn rằng điều kiện chưa từng được xét.

Một nguyên tắc thực tiễn: dùng `UPDATE settings['k'] = ...` bình thường khi ghi đè theo nghiệp vụ là chấp nhận được; dùng LWT khi **điều kiện là một phần hợp đồng dữ liệu** (không ghi đè nếu đã có, hoặc chỉ đổi từ giá trị/phiên bản kỳ vọng).

## 11. Concurrency: hai khóa khác nhau và cùng khóa

Giả sử hai client A và B cùng đọc map `{'language':'vi'}`.

### 11.1. Hai key khác nhau: mutation theo entry

```sql
-- Client A:
UPDATE app.user_preferences
SET settings['theme'] = 'dark'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Client B:
UPDATE app.user_preferences
SET settings['timezone'] = 'Asia/Ho_Chi_Minh'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Với non-frozen map, các entry được quản lý ở độ hạt key, nên hai cập nhật khác key có thể cùng xuất hiện khi các replica hòa giải dữ liệu. Điều này không đúng nếu A và B đều ghi lại **toàn map** từ snapshot cũ: một snapshot có thể che mất entry do client kia thêm.

### 11.2. Cùng key: xung đột theo timestamp hoặc điều kiện

```sql
-- Cả hai cùng cập nhật theme, nhưng muốn giá trị khác nhau:
UPDATE app.user_preferences SET settings['theme'] = 'dark'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

UPDATE app.user_preferences SET settings['theme'] = 'light'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Cassandra hòa giải ghi cạnh tranh theo metadata timestamp/tie-breaker của cell; thời điểm client bấm nút **không bảo đảm** là thứ tự thắng. Nếu nghiệp vụ yêu cầu chỉ ghi khi giá trị cũ chưa đổi, hãy dùng điều kiện kiểm tra phiên bản hoặc mô hình hàng riêng. Nếu ứng dụng tự chỉ định `USING TIMESTAMP`, cần hiểu tác động đồng hồ và ghi trễ; không nên tự tạo timestamp lớn bất thường để ép thắng xung đột.

## 12. TTL, tombstone, compaction và repair với map

Mỗi entry của non-frozen map có thể được ghi với TTL trong mutation tương ứng:

```sql
-- Chỉ entry banner mới viết nhận TTL 600 giây từ lệnh này.
UPDATE app.user_preferences USING TTL 600
SET settings['banner'] = 'trial'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Các entry khác của map không tự nhận TTL 600 giây vì lệnh trên. Khi TTL hết hạn hoặc entry bị `DELETE`, Cassandra cần giữ thông tin xóa (*tombstone*) để replica chưa nhận dữ liệu mới không đưa giá trị đã xóa trở lại. Compaction có thể dọn tombstone khi đủ điều kiện an toàn; lịch repair, cấu hình như `gc_grace_seconds` và trạng thái replica là các yếu tố cần cân nhắc.

Nếu map được cập nhật/xóa hàng nghìn key mỗi giây trong một hàng, nhiều entry/tombstone và hoạt động hòa giải SSTable có thể làm tăng latency đọc. Nếu key có lifecycle phức tạp và số lượng tăng liên tục, chuyển sang bảng riêng là một giải pháp mô hình dữ liệu, thay vì chỉ chỉnh compaction để bù cho collection quá lớn.

### `frozen<map<K,V>>` có giúp kiểm soát key không?

`frozen<map<text,text>>` lưu **cả map thành một cell**; không hỗ trợ mutation trực tiếp như `settings['theme'] = 'light'`. Muốn thêm/xóa một key, client phải cung cấp **toàn bộ snapshot mới**. Các lần ghi tranh chấp xảy ra trên toàn giá trị; TTL cũng gắn với cell snapshot. Đây là lựa chọn hợp lý khi map nhỏ, ít sửa và luôn được quản lý như một khối bất biến giữa các phiên bản, nhưng không giải quyết tự động điều kiện “key chưa có”.

## 13. Java Driver 4.x: đọc map, gán entry và kiểm tra `[applied]`

Ví dụ sau sử dụng `CqlSession` đã được cấu hình contact points, local datacenter và authentication phù hợp. Trong ứng dụng thực tế nên **cache/reuse prepared statements**. Code tập trung vào hai thao tác khác nhau: ghi đè entry và CAS dựa trên `revision`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

class PreferenceRepository {
    private final CqlSession session;
    private final PreparedStatement patchKey;
    private final PreparedStatement updateIfVersion;

    PreferenceRepository(CqlSession session) {
        this.session = session;
        this.patchKey = session.prepare(
            "UPDATE app.user_preferences " +
            "SET settings[?] = ? WHERE user_id = ?"
        );
        this.updateIfVersion = session.prepare(
            "UPDATE app.user_preferences " +
            "SET settings[?] = ?, revision = ? " +
            "WHERE user_id = ? IF revision = ?"
        );
    }

    void upsertKey(UUID userId, String key, String value) {
        // Upsert: key vắng mặt được thêm, key có sẵn được ghi đè.
        session.execute(patchKey.bind(key, value, userId));
    }

    boolean updateIfRevision(
        UUID userId, String key, String value,
        int expectedRevision
    ) {
        int nextRevision = Math.addExact(expectedRevision, 1);
        BoundStatement statement = updateIfVersion.bind(
            key, value, nextRevision, userId, expectedRevision
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

        Row result = session.execute(statement).one();
        if (result == null) {
            throw new IllegalStateException("Missing LWT result");
        }
        return result.getBoolean("[applied]");
    }
}
```

**Cần chú ý khi triển khai:**

- Các marker `?` truyền vào **key/value** của map là tham số bind, không phải tên cột; key map `null` không phải đầu vào hợp lệ. Việc hỗ trợ bind ở vị trí subscript phụ thuộc phiên bản CQL/driver: nếu bản đang vận hành không chấp nhận `settings[?]`, có thể dùng statement cố định cho một key hoặc mutation `settings = settings + ?` với một map tham số như `Map.of(key, value)`.
- `LOCAL_QUORUM`/`LOCAL_SERIAL` là **ví dụ** phù hợp với một số cụm có replication đa replica trong cùng datacenter; lựa chọn thực tế phải căn cứ cấu hình datacenter và yêu cầu nhất quán.
- Chỉ coi thao tác thành công khi `[applied] = true`. Khi false, đọc lại trạng thái; nếu kết quả bị timeout, không tự mặc định điều kiện đã thất bại.
- Tất cả writer tham gia kiểm soát phiên bản phải thay `revision` theo cùng quy trình. Nếu một code path ghi map trực tiếp mà bỏ revision, CAS không còn bảo vệ toàn bộ thay đổi nghiệp vụ.
- Hàm `upsertKey` có ý nghĩa **ghi đè được phép**; nó không thay thế quy trình “chỉ thêm key khi key chưa tồn tại”.

## 14. Bài tập tình huống và câu trả lời gợi ý

**Tình huống A — key chưa có.** Hàng của user đã tồn tại với `settings={'language':'vi'}`. Ứng dụng gọi `UPDATE ... SET settings['theme']='dark' IF EXISTS`. Lệnh có bị từ chối do `theme` chưa có?  
**Gợi ý:** Không. `IF EXISTS` kiểm tra **hàng**, không kiểm tra key. Nếu hàng tồn tại, key mới có thể được thêm.

**Tình huống B — chỉ thêm khi chưa có.** Hai client đồng thời muốn tạo `theme` lần đầu. Chúng đều `SELECT`, thấy chưa có key rồi gửi `UPDATE` bình thường. Có thể bảo đảm chỉ một client thắng không?  
**Gợi ý:** Không. Dùng CAS dựa trên revision mà mọi writer cùng tuân thủ, hoặc chuyển mỗi key thành một hàng để `INSERT ... IF NOT EXISTS` kiểm tra trực tiếp khóa nghiệp vụ.

**Tình huống C — tưởng là no-op.** Ứng dụng xóa key `never_seen` nhiều lần mỗi giây mặc dù key chưa từng tồn tại. Có thể bỏ qua chi phí không?  
**Gợi ý:** Không nên. Xóa có thể tạo tombstone cho entry, tăng công việc đọc/compaction; cần kiểm tra workload và loại bỏ thao tác xóa không cần thiết.

**Tình huống D — hai key khác nhau.** Client A đổi `theme`, B đổi `language`. Tại sao patch từng key thường ít nguy cơ lost update hơn thay toàn map từ snapshot cũ?  
**Gợi ý:** Non-frozen map quản lý entry theo key; hai mutation khác key có thể cùng tồn tại. Thay cả snapshot có thể che thay đổi của client còn lại.

**Tình huống E — key nhiều và TTL khác nhau.** Một người dùng có vài trăm nghìn khóa, mỗi khóa cần TTL riêng, tìm kiếm và phân trang. Dùng `frozen<map<text,text>>` có phù hợp không?  
**Gợi ý:** Không. Dùng hàng riêng với khóa truy vấn thích hợp và bucket khi cần. `frozen` làm cập nhật từng key khó hơn và không cấp phân trang theo hàng cho các phần tử.

**Tình huống F — CAS thất bại.** Client đọc `revision=7`, thử ghi với `IF revision=7`, nhận `[applied]=false`. Nên ép ghi không điều kiện ngay để tránh làm phiền người dùng?  
**Gợi ý:** Không. Phải đọc lại, xác định ai đã sửa dữ liệu và áp dụng chính sách xung đột/retry có giới hạn; ép ghi có thể làm mất thay đổi hợp lệ.

## 15. Checklist thiết kế trước khi đưa vào production

1. **Đường đọc là gì?** Truy cập `settings` qua `user_id`, hay cần tra ngược theo key/value? Thiết kế schema dựa trên truy vấn thực.
2. **Số key tối đa?** Collection có giới hạn nhỏ không? Nếu không, cân nhắc bảng riêng và bucket.
3. **Key chưa có nghĩa là gì?** Dùng mặc định, chưa khởi tạo, bị xóa hay cần báo lỗi? Phân biệt hàng không có với entry không có.
4. **Ghi đè có được phép?** Nếu có, mutation theo entry có thể đủ. Nếu không, cần điều kiện theo version/giá trị và kiểm tra `[applied]`.
5. **Điều kiện nằm ở đâu?** `IF EXISTS`/`IF NOT EXISTS` mặc định xét **hàng**; cần ngữ nghĩa theo key thì thiết kế primary key hoặc protocol CAS phù hợp.
6. **Ai ghi đồng thời?** Mọi writer có dùng chung revision? Có retry tự động? Có phụ thuộc timestamp, TTL hoặc clock skew không?
7. **Vận hành ra sao?** Theo dõi tombstone, repair, compaction, p95/p99 latency và ảnh hưởng LWT lên replica trước khi tăng tần suất ghi.

## 16. Ghi nhớ

- `map<K,V>` dùng **khóa duy nhất** để định danh entry; cập nhật `settings['key']` thông thường là **upsert**.
- Key thiếu có thể đọc thành `null`, nhưng phải phân biệt **key thiếu**, **cột null** và **hàng không tồn tại**.
- `IF EXISTS`/`IF NOT EXISTS` kiểm tra **hàng theo primary key**, không phải tự động kiểm tra sự tồn tại của một key con trong map.
- Muốn “chỉ thêm nếu key chưa có”, dùng **CAS theo phiên bản cả hàng** và quản lý mọi writer, hoặc mô hình **mỗi key là một hàng** rồi dùng `INSERT ... IF NOT EXISTS`.
- LWT có chi phí Paxos/serial consistency và cần xử lý `[applied]`, timeout, conflict; consistency `QUORUM` thông thường không thay thế CAS.
- Xóa entry dù đang thiếu vẫn có thể tạo **tombstone**; compaction và repair là phần quan trọng của vận hành Cassandra phân tán.
- Collection nên **nhỏ và có giới hạn**. Khi cần truy vấn ngược, TTL/điều kiện độc lập, phân trang hoặc số key tăng mãi, hãy thiết kế bảng theo truy vấn với partition/clustering key phù hợp.
