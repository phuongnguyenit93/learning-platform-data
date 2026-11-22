# USING TIMESTAMP, USING TTL và điều kiện được phép kết hợp trong Cassandra

Trong Apache Cassandra, hai tùy chọn `USING TIMESTAMP` và `USING TTL` cùng xuất hiện ở các câu lệnh ghi CQL, nhưng **giải quyết hai bài toán hoàn toàn khác nhau**:

- **`TIMESTAMP`** đặt *write timestamp* dùng để hòa giải những phiên bản dữ liệu cạnh tranh.
- **`TTL`** (*time to live*) đặt thời gian sống của những giá trị được ghi, tính bằng giây.

Điểm dễ sai không chỉ là đơn vị đo. `INSERT`, `UPDATE` và `DELETE` có **vị trí đặt `USING` khác nhau**, không hỗ trợ cùng một tập tùy chọn, và có giới hạn khi kết hợp với điều kiện `IF`/`IF NOT EXISTS` (*lightweight transaction*, LWT). Một câu lệnh có cú pháp hợp lệ chưa chắc có semantics mong muốn khi replica mất kết nối, ghi bị retry hay dữ liệu cũ vẫn còn trong SSTable.

Bài học thuộc chương **Ghi và xóa bằng CQL** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Các ví dụ kết nối cơ chế ghi phân tán, partition key, consistency level, replication, compaction và repair với mã Java Driver.

Sau bài này, bạn sẽ biết cách:

1. Viết `USING TTL` và `USING TIMESTAMP` đúng vị trí cho từng loại statement.
2. Dự đoán trường nào hết hạn và timestamp nào thắng khi hai mutation cạnh tranh.
3. Nhận biết tổ hợp **được phép**, **không được phép** và trường hợp cần LWT.
4. Sử dụng prepared statement Java mà không nhầm giây, mili giây và micro giây.
5. Thiết kế retry, xử lý tombstone và kiểm tra kết quả viết/xóa trong hệ thống nhiều replica.

## 1. Bảng CQL dùng xuyên suốt

Giả sử dịch vụ quản lý thiết lập tài khoản đọc dữ liệu theo `user_id`; keyspace `demo` đã tồn tại trong môi trường thử nghiệm:

```sql
CREATE TABLE demo.user_preferences_by_id (
    user_id          uuid PRIMARY KEY,
    display_name     text,
    preferred_locale text,
    phone            text,
    otp_code         text,
    account_state    text,
    revision         int
);
```

`user_id` là **partition key** và đồng thời là **full primary key** của bảng. Cassandra dùng khóa này để xác định phân vùng và các replica liên quan. Những cột còn lại là regular column, mỗi cột có lịch sử phiên bản và khả năng hết hạn riêng.

Tạo hàng ví dụ:

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, display_name, preferred_locale,
    phone, account_state, revision
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'Linh',
    'vi-VN',
    '0900000001',
    'ACTIVE',
    1
);

SELECT user_id, display_name, preferred_locale,
       phone, otp_code, account_state, revision
FROM demo.user_preferences_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Các ví dụ thực hành giả định không có client khác đang ghi cùng khóa, đồng hồ các node ổn định và bảng không được đặt `default_time_to_live` khác 0, trừ khi có ghi chú riêng. Để thao tác `USING TIMESTAMP` không ảnh hưởng dữ liệu tự sinh timestamp, bài dùng **UUID khác** khi minh họa timestamp tùy chỉnh.

## 2. Ngữ pháp: USING nằm ở đâu?

Không thể đặt `USING` tại một vị trí duy nhất cho cả ba statement. Nhớ ba khuôn dạng sau (chỉ thể hiện các phần liên quan đến bài):

```sql
-- INSERT: IF NOT EXISTS nằm trước USING nếu cùng xuất hiện.
INSERT INTO demo.user_preferences_by_id (user_id, otp_code)
VALUES (33333333-3333-4333-8333-333333333333, '123456')
IF NOT EXISTS
USING TTL 300;

-- UPDATE: USING đứng trước SET; IF nằm ở cuối.
UPDATE demo.user_preferences_by_id
USING TTL 300
SET otp_code = '654321'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- DELETE: USING TIMESTAMP đứng sau tên bảng, trước WHERE.
DELETE otp_code FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000000
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

Lệnh `DELETE` cuối dùng một timestamp **tự chỉ định trong quá khứ** chỉ để minh họa cú pháp; nếu giá trị đang có được ghi với timestamp mới hơn thì dấu xóa đó **không thắng**, nên có thể vẫn đọc được `otp_code`. Đừng dùng timestamp cố định như vậy để xóa dữ liệu production.

### Ma trận hỗ trợ

| Câu lệnh | `USING TTL` | `USING TIMESTAMP` | Hai tùy chọn cùng lúc | Có thể thêm điều kiện `IF`? |
| --- | --- | --- | --- | --- |
| `INSERT` thường | Có | Có | Có, nối bằng `AND` | `IF NOT EXISTS` có thể đi với TTL; không đi với timestamp tùy chỉnh |
| `UPDATE` thường | Có | Có | Có, nối bằng `AND` | `IF EXISTS` hoặc `IF condition` có thể đi với TTL; không đi với timestamp tùy chỉnh |
| `DELETE` | **Không** | Có | **Không**, vì DELETE không có TTL | `IF EXISTS`/`IF condition` khi được hỗ trợ, **không** đi với timestamp tùy chỉnh |
| Ghi trên bảng `counter` | **Không** | **Không** | **Không** | Không dùng LWT điều kiện như regular column |

LWT và counter có các giới hạn riêng ngoài bảng tóm tắt này. **Đừng suy luận rằng có từ khóa `USING` thì mọi tùy chọn đều dùng được với mọi thao tác.**

### Hai tùy chọn trong một statement: dùng AND

```sql
UPDATE demo.user_preferences_by_id
USING TTL 600 AND TIMESTAMP 1700000000000001
SET otp_code = '246810'
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

Trong `UPDATE`, `USING` đứng **trước `SET`**. Có thể viết `USING TIMESTAMP ... AND TTL ...` thay cho `USING TTL ... AND TIMESTAMP ...`; với cả hai, `AND` nối các tham số ghi, không phải điều kiện lọc hàng.

Để không nhầm các loại `AND`, hãy phân biệt:

- `USING TTL ... AND TIMESTAMP ...`: kết hợp **tham số ghi**.
- `WHERE key1 = ... AND key2 = ...`: kết hợp **thành phần khóa/điều kiện định vị**.
- `IF col1 = ... AND col2 = ...`: kết hợp **điều kiện của LWT** nếu câu lệnh và phiên bản CQL hỗ trợ.

## 3. USING TIMESTAMP: thời điểm hòa giải phiên bản, không phải cột thời gian

Cassandra lưu *write timestamp* cho cell để quyết định phiên bản thắng khi có nhiều ghi tại cùng vị trí dữ liệu. Dữ liệu thường được mô tả bằng nguyên tắc **last-write-wins theo timestamp**, chứ không thuần túy theo thứ tự lời gọi Java hoặc thời điểm mutation đến coordinator.

`USING TIMESTAMP` cho phép client **ghi đè timestamp tự động** bằng một giá trị cụ thể:

```sql
-- UUID riêng để minh họa timestamp thủ công.
INSERT INTO demo.user_preferences_by_id (
    user_id, preferred_locale, account_state
)
VALUES (
    22222222-2222-4222-8222-222222222222,
    'vi-VN',
    'ACTIVE'
)
USING TIMESTAMP 1700000000000000;

UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000002
SET preferred_locale = 'en-US'
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

Với cùng cell `preferred_locale`, timestamp `1700000000000002` lớn hơn `1700000000000000` nên phiên bản `'en-US'` thắng trong trường hợp không có mutation khác. Nếu tiếp tục ghi:

```sql
UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000001
SET preferred_locale = 'ja-JP'
WHERE user_id = 22222222-2222-4222-8222-222222222222;

SELECT preferred_locale, WRITETIME(preferred_locale)
FROM demo.user_preferences_by_id
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

thì `'ja-JP'` **không thắng** `'en-US'` vì timestamp `...0001` nhỏ hơn `...0002`, dù câu lệnh chạy sau. Đây là minh họa cơ bản về write timestamp.

### Đơn vị cực kỳ quan trọng

| Khái niệm | Đơn vị | Ví dụ |
| --- | --- | --- |
| `USING TIMESTAMP` | **Microsecond** từ Unix epoch | `1700000000000000` |
| `WRITETIME(column)` | **Microsecond** từ Unix epoch | `1700000000000002` |
| Java `Instant.toEpochMilli()` | **Millisecond** từ Unix epoch | `1700000000000` |
| Java `Instant.getEpochSecond()` | **Second** từ Unix epoch | `1700000000` |
| CQL `timestamp` **type** (giá trị ngày–giờ) | Biểu diễn thời điểm; precision khi lưu là millisecond | `'2026-11-21 10:00:00+0700'` |

Nhầm `Instant.toEpochMilli()` với microsecond của `USING TIMESTAMP` sẽ cho ra timestamp **nhỏ hơn 1.000 lần**, rất xa thời điểm mong đợi; mutation có thể không thắng dữ liệu đang có. Ngược lại, nhân hoặc cộng đơn vị sai tạo timestamp quá xa trong tương lai có thể khiến các lần ghi bình thường về sau không thể thay thế giá trị trong thời gian dài.

Nếu không có yêu cầu xác đáng về đồng bộ timestamp từ hệ thống ngoài, **ưu tiên cơ chế tạo timestamp mặc định của Cassandra/driver** và đừng tự phát minh timestamp thủ công cho mọi lệnh ghi.

### Hai cột của cùng hàng có thể mang write timestamp khác nhau

```sql
UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000003
SET phone = '0911111111'
WHERE user_id = 22222222-2222-4222-8222-222222222222;

SELECT preferred_locale,
       WRITETIME(preferred_locale),
       phone,
       WRITETIME(phone)
FROM demo.user_preferences_by_id
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

Lệnh sửa `phone` không tự làm mới timestamp của `preferred_locale`. Thao tác upsert thường chỉ ghi các cột được nhắc tới. Điều này cũng giải thích vì sao một cột `modified_at timestamp` do ứng dụng tự duy trì **không phải** timestamp hòa giải cell: muốn cập nhật `modified_at`, ứng dụng phải ghi nó như một cột thông thường.

### Xóa với TIMESTAMP và nguy cơ dữ liệu tưởng đã xóa vẫn còn

```sql
-- Timestamp cũ hơn giá trị phone ở trên: dấu xóa không thắng.
DELETE phone FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000002
WHERE user_id = 22222222-2222-4222-8222-222222222222;

-- Timestamp lớn hơn: dấu xóa có thể che phiên bản phone cũ.
DELETE phone FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000004
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

Tombstone cũng mang timestamp để che những phiên bản cũ hơn. Vì vậy, `DELETE` thành công về mặt câu lệnh không phải lúc nào cũng đồng nghĩa “mọi phiên bản được xóa bất kể timestamp”; dùng timestamp thủ công không đúng có thể làm kết quả đọc gây ngạc nhiên.

Trường hợp timestamp bằng nhau có quy tắc hòa giải chi tiết riêng (liên quan dấu xóa và cách so sánh giá trị); **không nên thiết kế nghiệp vụ dựa vào tie-break của timestamp trùng nhau**.

## 4. USING TTL: giá trị được ghi sống trong bao lâu?

`USING TTL n` đặt thời gian sống `n` **giây** cho những giá trị mà mutation ghi, thay vì đặt thời gian sống cho toàn bộ hàng hoặc toàn bộ phân vùng một cách mặc định.

Ví dụ lưu OTP chỉ có hiệu lực 5 phút:

```sql
UPDATE demo.user_preferences_by_id
USING TTL 300
SET otp_code = '835194'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

SELECT otp_code, TTL(otp_code), WRITETIME(otp_code)
FROM demo.user_preferences_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Ngay sau lần ghi thành công, `TTL(otp_code)` thường cho biết số giây còn lại (gần 300 và giảm theo thời gian). Sau khi hết hạn, giá trị không còn được trả về như dữ liệu đang sống: `otp_code` có thể được đọc thành `null`.

### TTL chỉ áp dụng lên các cột vừa được ghi

Hãy xét mutation khác trên cùng hàng:

```sql
UPDATE demo.user_preferences_by_id
USING TTL 120
SET preferred_locale = 'en-US',
    phone = '0900000022'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Trong câu trên, `preferred_locale` và `phone` được ghi cùng TTL 120 giây. `display_name`, `account_state`, `revision` và `otp_code` **không nằm trong `SET`**, nên mutation không đặt TTL mới lên các cột đó.

Nếu `otp_code` đã có TTL 300 giây từ câu trước, đồng hồ TTL của mã OTP **tiếp tục chạy**. Sửa `phone` không tự gia hạn OTP. Tương tự, nếu chỉ một cột trong bảng có TTL, không được suy ra cả hàng sẽ biến mất theo đúng thời điểm cột đó hết hạn.

### INSERT có TTL

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, otp_code
)
VALUES (
    44444444-4444-4444-8444-444444444444,
    '482731'
)
USING TTL 180;
```

`INSERT` với TTL cũng chỉ ghi các giá trị được liệt kê. Nếu `user_id` đã tồn tại với `display_name` hoặc `phone`, hai cột ấy không bị xóa hoặc tự động có TTL 180 giây do chúng không nằm trong mutation này.

**Primary key không hết hạn như một giá trị trường độc lập.** TTL áp dụng lên các cell/marker được ghi theo mô hình lưu trữ của Cassandra; một hàng chỉ còn dữ liệu có TTL có thể không còn xuất hiện trong kết quả sau khi các giá trị và thông tin liveness liên quan hết hạn.

### Ghi đè cột có TTL

Giả sử một cell `otp_code` đang còn 100 giây. Ứng dụng ghi lại chính cột đó:

```sql
UPDATE demo.user_preferences_by_id
USING TTL 600
SET otp_code = '999888'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Nếu mutation mới thắng theo timestamp, giá trị `'999888'` có thời gian sống theo **lần ghi mới**, thay vì đơn giản thừa hưởng 100 giây còn lại của giá trị cũ. Đây là lý do retry sau timeout cần xét thêm TTL: gửi lại cùng mã OTP nhưng với một timestamp/TTL mới có thể gia hạn thời gian tồn tại.

### USING TTL 0

`USING TTL 0` thường được dùng để **ghi lại giá trị mà không có TTL** và loại bỏ thời hạn hết hạn của phiên bản cũ khi mutation mới thắng:

```sql
UPDATE demo.user_preferences_by_id
USING TTL 0
SET otp_code = 'MA-LUU-LAU'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Với một bảng không có TTL mặc định, `TTL(otp_code)` của giá trị mới thường trả `null`. Trong thực tế, `otp_code` lại là dữ liệu nhạy cảm cần hết hạn, nên lệnh trên **chỉ minh họa cú pháp**; không nên dùng TTL 0 cho mã xác minh production.

**Chú ý cấu hình bảng:** `default_time_to_live` có thể quy định TTL cho những giá trị được ghi khi statement không chỉ định TTL riêng. TTL tường minh và việc xóa thời hạn hết hạn phải được đánh giá theo phiên bản Cassandra cùng cấu hình bảng đang triển khai; tránh giả định “không viết USING TTL” luôn đồng nghĩa lưu vĩnh viễn.

### Đơn vị, giá trị hợp lệ và giới hạn lưu trữ

- TTL được tính bằng **giây**, không phải milli/microsecond.
- TTL phải phù hợp với ràng buộc của Cassandra; `TTL 300` nghĩa là năm phút, không phải 300 mili giây.
- TTL âm không phải một cách hợp lệ để yêu cầu dữ liệu hết hạn ngay.
- Dữ liệu hết hạn được xử lý thông qua cơ chế tombstone và compaction; **không** đồng nghĩa byte cũ bị xóa vật lý ngay đúng giây hết hạn.
- Hệ thống và phiên bản Cassandra có giới hạn thời điểm hết hạn biểu diễn được; TTL quá lớn có thể vướng chính sách xử lý overflow, vì vậy hãy chọn TTL hợp lý và kiểm tra cấu hình khi cần lưu giữ rất lâu.

## 5. Kết hợp TIMESTAMP và TTL trên cùng một mutation

Với `INSERT` hoặc `UPDATE` thông thường trên các cột phù hợp, CQL cho phép chỉ định **cả hai tham số**:

```sql
-- INSERT: USING nằm sau VALUES.
INSERT INTO demo.user_preferences_by_id (
    user_id, otp_code
)
VALUES (
    55555555-5555-4555-8555-555555555555,
    '752901'
)
USING TTL 900 AND TIMESTAMP 1700000000000010;

-- UPDATE: USING nằm trước SET.
UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000011 AND TTL 1200
SET otp_code = '752902'
WHERE user_id = 55555555-5555-4555-8555-555555555555;
```

Hai tùy chọn điều khiển **hai khía cạnh độc lập**:

| Tùy chọn | Trả lời câu hỏi | Đơn vị | Mục đích |
| --- | --- | --- | --- |
| `TIMESTAMP 1700000000000011` | Phiên bản này mới hay cũ khi hòa giải? | Microsecond từ Unix epoch | Thứ tự ưu tiên mutation cạnh tranh |
| `TTL 1200` | Giá trị vừa ghi còn sống bao lâu? | Giây | Hết hạn dữ liệu tạm |

Không tính thời điểm hết hạn một cách máy móc bằng công thức “`USING TIMESTAMP` cộng `TTL`”. **Write timestamp do ứng dụng chọn không phải tham số đặt giờ hết hạn tuyệt đối.** TTL được tính theo cơ chế thời gian sống của mutation khi Cassandra xử lý ghi; hai tham số có vai trò khác nhau.

### Tác động khi ghi cạnh tranh

Giả sử hai mutation vào **cùng `otp_code`**, đều được nhận:

| Mutation | Write timestamp | TTL | Giá trị |
| --- | ---: | ---: | --- |
| A | 100 | 600 giây | `'CODE-A'` |
| B | 200 | 30 giây | `'CODE-B'` |

Khi B thắng theo timestamp, cell `otp_code` mang phiên bản của B cùng thời hạn sống tương ứng. Khi B hết hạn, **không được giả định A tự xuất hiện lại như một phương án dự phòng**. Cassandra sử dụng thông tin hết hạn/tombstone để tránh hồi sinh phiên bản cũ mà B đã thay thế hoặc che khuất.

Một phiên bản mới hơn nhưng có TTL ngắn không phải “lớp phủ tạm thời” cho phép Cassandra tự quay lại phiên bản cũ hơn sau khi hết hạn. Nếu nghiệp vụ muốn phục hồi giá trị trước đó, ứng dụng phải mô hình hóa hoặc ghi lại một giá trị mới theo cách chủ động.

### Dùng timestamp thủ công khi nào?

Chỉ cân nhắc khi có lý do nhất quán rõ ràng, chẳng hạn đồng bộ dữ liệu từ hệ thống bên ngoài với timestamp phiên bản đáng tin cậy. Ngay cả trong trường hợp đó, phải kiểm soát:

- Thống nhất đơn vị microsecond và nguồn thời gian.
- Không sử dụng timestamp quá xa tương lai.
- Không để một ứng dụng tự cấp timestamp thấp hơn hàng loạt timestamp đã ghi.
- Không trộn tùy tiện timestamp từ nhiều nguồn có độ lệch đồng hồ khác nhau.
- Không gán timestamp thủ công cho LWT; đây là tổ hợp bị cấm, không phải một phương án để ép thứ tự giao dịch.

## 6. Điều kiện IF/LWT: kết hợp nào được phép?

`IF NOT EXISTS`, `IF EXISTS` và `IF column = value` làm mutation trở thành một thao tác **có điều kiện** (*lightweight transaction*). Cassandra phải kiểm tra trạng thái hiện có bằng cơ chế đồng thuận, thay vì chỉ gửi một upsert thông thường.

### 6.1. INSERT IF NOT EXISTS cùng TTL: được phép

Ví dụ chỉ tạo một mã tạm khi khóa chưa tồn tại:

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, otp_code
)
VALUES (
    66666666-6666-4666-8666-666666666666,
    '301927'
)
IF NOT EXISTS
USING TTL 300;
```

Ý nghĩa:

1. Cassandra kiểm tra điều kiện **hàng chưa tồn tại** ở khóa đã định.
2. Nếu điều kiện đúng, mutation được áp dụng với TTL cho dữ liệu được ghi.
3. Nếu điều kiện sai, không có mutation mới từ yêu cầu đó.
4. Kết quả có cột `[applied]`; ứng dụng phải kiểm tra `true`/`false`.

Đây là **kết hợp TTL với LWT**, chứ không phải kết hợp timestamp do người dùng tự đặt với LWT.

**Lưu ý thiết kế:** Nếu bảng có nhiều cột hoặc dữ liệu có TTL hết hạn, “hàng tồn tại” là khái niệm liveness trong Cassandra chứ không chỉ là còn byte trong một SSTable cũ. Không dùng sự tồn tại tạm thời của `otp_code` thay cho quy tắc chống đăng ký tài khoản trùng vĩnh viễn; hai bài toán cần mô hình dữ liệu phù hợp.

### 6.2. UPDATE IF EXISTS cùng TTL: được phép

```sql
UPDATE demo.user_preferences_by_id
USING TTL 180
SET otp_code = '902134'
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;
```

Nếu hàng đã tồn tại khi LWT xét điều kiện, OTP được ghi với TTL 180 giây. Nếu hàng không tồn tại, `[applied] = false` và lệnh không tạo ra hàng thưa như một `UPDATE` không điều kiện.

### 6.3. UPDATE IF điều kiện giá trị cũ cùng TTL: được phép

```sql
UPDATE demo.user_preferences_by_id
USING TTL 120
SET otp_code = '483721'
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF account_state = 'ACTIVE';
```

Ý định là chỉ cấp mã xác minh tạm cho tài khoản còn `ACTIVE`. `IF account_state = 'ACTIVE'` kiểm tra dữ liệu cũ, còn `TTL 120` áp dụng lên `otp_code` được ghi nếu LWT thành công.

Nếu muốn thay đổi đồng thời nhiều cột nhưng **chỉ TTL một cột trong số đó**, một mutation duy nhất có `USING TTL` không phải cách diễn đạt mong muốn: TTL tác động đến những giá trị được ghi trong mutation. Khi cần thời gian sống khác nhau, nên tách các mutation theo cột và thiết kế rõ tính nguyên tử/điều kiện của nghiệp vụ.

### 6.4. INSERT/UPDATE có IF và TIMESTAMP tùy chỉnh: không được phép

Các lệnh sau **cố ý sai** để minh họa những tổ hợp bị từ chối:

```sql
-- SAI: LWT IF NOT EXISTS không nhận USING TIMESTAMP tự chọn.
INSERT INTO demo.user_preferences_by_id (user_id, otp_code)
VALUES (77777777-7777-4777-8777-777777777777, '111222')
IF NOT EXISTS
USING TIMESTAMP 1700000000000100;

-- SAI: UPDATE IF EXISTS không kết hợp với timestamp do client đặt.
UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000101
SET preferred_locale = 'en-US'
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;

-- SAI: có TTL không hợp thức hóa TIMESTAMP + IF.
UPDATE demo.user_preferences_by_id
USING TTL 300 AND TIMESTAMP 1700000000000102
SET otp_code = '555666'
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF account_state = 'ACTIVE';
```

Nguyên tắc: **LWT tự quản lý timestamp/phiên bản phục vụ đồng thuận**; cung cấp một write timestamp thủ công là không tương thích với mutation điều kiện. Nếu bạn cần `IF` và TTL, **chỉ dùng TTL**, không thêm `USING TIMESTAMP`.

### Vì sao SELECT rồi UPDATE thường không thay thế IF?

Hai client cùng hoạt động:

```text
Client A: SELECT revision -> 1
Client B: SELECT revision -> 1
Client A: UPDATE revision = 2, locale = 'en-US'
Client B: UPDATE revision = 2, locale = 'fr-FR'
```

Không có điều kiện `IF`, các mutation tranh chấp theo timestamp và một cập nhật có thể bị che. Nếu cả hai gửi:

```sql
UPDATE demo.user_preferences_by_id
SET preferred_locale = 'en-US', revision = 2
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF revision = 1;
```

thì chỉ những thao tác thỏa điều kiện khi LWT xử lý mới được áp dụng. `USING TTL` có thể được thêm nếu thực sự muốn các cột vừa cập nhật có TTL; nhưng đa số hệ thống **không** muốn `revision` tự hết hạn, vì vậy trong ví dụ compare-and-set trên ta không đặt TTL.

### Kết hợp IF có giới hạn về phạm vi

LWT không biến CQL thành công cụ truy vấn/xóa đa hàng tùy ý. Vẫn phải cung cấp khóa hợp lệ và tuân thủ ràng buộc điều kiện theo loại mutation, cấu trúc bảng, phiên bản Cassandra. Cần đặc biệt thận trọng với collection/counter và những statement tác động nhiều hàng hoặc nhiều partition: không suy ra rằng có `IF` thì mọi kết hợp với `USING` sẽ hợp lệ.

## 7. DELETE: chỉ có TIMESTAMP, không có TTL

`DELETE` có nghĩa ghi **dấu xóa (tombstone)** cho dữ liệu theo phạm vi đã chọn. TTL lại có nghĩa giới hạn **thời gian sống của giá trị vừa được ghi**, nên **DELETE không hỗ trợ `USING TTL`**.

### DELETE có TIMESTAMP: hợp lệ khi không có IF

```sql
DELETE phone FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000200
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

Dấu xóa có write timestamp được chỉ định. Nếu timestamp này thấp hơn timestamp của giá trị `phone` đang sống, dấu xóa không che được giá trị đó. Để thao tác xóa hợp lệ về mặt nghiệp vụ, không nên sử dụng timestamp thủ công tùy tiện.

### DELETE có điều kiện: hợp lệ, nhưng không kèm TIMESTAMP thủ công

```sql
DELETE FROM demo.user_preferences_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;
```

Lệnh này dùng LWT để chỉ xóa khi hàng tồn tại; ứng dụng đọc `[applied]` để quyết định cách trả lời. Không được “tối ưu” thành:

```sql
-- SAI: DELETE với IF không nhận timestamp do client chọn.
DELETE FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000201
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;
```

### Hai ví dụ DELETE sai khác

```sql
-- SAI: DELETE không hỗ trợ USING TTL.
DELETE phone FROM demo.user_preferences_by_id
USING TTL 300
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- SAI: DELETE không hỗ trợ cả TTL và TIMESTAMP theo cách này.
DELETE phone FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000202 AND TTL 300
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

**Nếu muốn giá trị tự biến mất sau 5 phút, hãy ghi giá trị đó với `USING TTL 300`**, không ghi một lệnh DELETE có TTL. Nếu muốn xóa ngay về mặt logic, dùng DELETE không điều kiện hoặc DELETE có LWT theo yêu cầu nghiệp vụ.

### DELETE và TTL tạo ra tombstone theo hai con đường

| Nhu cầu | CQL | Khi nào không còn là dữ liệu sống? |
| --- | --- | --- |
| Xóa cột ngay | `DELETE col FROM ... WHERE ...` | Khi tombstone thắng và được đọc thấy |
| Xóa cột ngay với write timestamp cụ thể | `DELETE col FROM ... USING TIMESTAMP ... WHERE ...` | Khi dấu xóa thắng phiên bản cũ |
| Tự hết hạn một giá trị | `UPDATE ... USING TTL 300 SET col = ...` | Sau khi TTL hết hạn (trong điều kiện thời gian hệ thống phù hợp) |
| Chỉ xóa khi hàng tồn tại | `DELETE FROM ... WHERE ... IF EXISTS` | Khi điều kiện LWT thỏa và dấu xóa được áp dụng |

Tombstone có vai trò thiết yếu trong hệ thống phân tán: replica bỏ lỡ phép xóa phải có cách nhận biết dữ liệu cũ không còn hợp lệ khi đồng bộ. `gc_grace_seconds`, repair và compaction quyết định khi nào dấu xóa/dữ liệu cũ có thể được thu gom an toàn; chúng **không** thay đổi cú pháp `USING TTL` hoặc `USING TIMESTAMP`.

## 8. Counter và các thao tác đặc biệt

Counter là kiểu dữ liệu có semantics cộng/trừ chuyên biệt. Ví dụ:

```sql
CREATE TABLE demo.api_call_counts_by_day (
    service_name text,
    call_day date,
    total counter,
    PRIMARY KEY (service_name, call_day)
);

UPDATE demo.api_call_counts_by_day
SET total = total + 1
WHERE service_name = 'auth'
  AND call_day = '2026-11-21';
```

Không thêm `USING TTL` hay `USING TIMESTAMP` cho phép tăng counter, cũng không dùng `IF` như một mutation điều kiện trên regular column. Ví dụ sai:

```sql
-- SAI: counter không hỗ trợ TTL theo cách này.
UPDATE demo.api_call_counts_by_day USING TTL 300
SET total = total + 1
WHERE service_name = 'auth'
  AND call_day = '2026-11-21';

-- SAI: counter không hỗ trợ timestamp thủ công.
UPDATE demo.api_call_counts_by_day USING TIMESTAMP 1700000000000000
SET total = total + 1
WHERE service_name = 'auth'
  AND call_day = '2026-11-21';
```

**Counter không idempotent**: nếu mutation đã tới replica nhưng client nhận timeout, retry có thể cộng thêm lần nữa. Không dùng counter cho ràng buộc “đúng một lần” của giao dịch tài chính hoặc mã OTP.

Các thao tác collection cũng có quy tắc riêng về cập nhật từng phần tử; đừng áp dụng máy móc mọi tùy chọn `USING` vào mọi phép sửa `list`, `map` hoặc `set` mà không kiểm tra hình thức CQL được hỗ trợ bởi phiên bản Cassandra. Đặc biệt, sửa/xóa phần tử `list` theo vị trí/giá trị có thể cần *read-before-write* và có đặc tính tranh chấp khác với upsert một cột scalar.

## 9. Timestamp, TTL và nhiều replica: điều gì xảy ra khi có sự cố?

`USING TIMESTAMP` và `USING TTL` được thực thi trong một hệ thống nhiều replica, không phải trong một bộ nhớ đơn lẻ. Một mutation được coordinator gửi đến các replica phụ trách phân vùng; mức nhất quán `ONE`, `QUORUM` hoặc các mức khác ảnh hưởng số replica phải xác nhận.

### 9.1. Timestamp quyết định phiên bản khi replica hội tụ

Giả sử replication factor là 3:

```text
Replica A: locale = 'en-US', write_ts = T2
Replica B: locale = 'en-US', write_ts = T2
Replica C: locale = 'vi-VN', write_ts = T1
T2 > T1
```

Replica C có thể tạm thời chưa nhận mutation mới. Khi quá trình đọc/đồng bộ/repair xử lý các phiên bản, write timestamp cho biết phiên bản nào thắng. `USING TIMESTAMP` cho phép bạn chọn thứ tự tương đối, nhưng **không buộc cả ba replica nhận mutation ngay**.

### 9.2. TTL không thay thế việc đồng bộ replica

Một cell có TTL sẽ hết hạn theo cơ chế của Cassandra, để không còn được coi là giá trị sống. Dữ liệu hết hạn liên quan đến tombstone và quy trình compaction. Nếu replica không có cùng trạng thái kịp thời, chọn consistency level phù hợp và thực hiện repair vẫn là vấn đề vận hành quan trọng.

**Không tự ý giảm `gc_grace_seconds`** chỉ vì muốn xóa giá trị có TTL nhanh khỏi đĩa. Dấu xóa cần được bảo vệ đủ lâu để replica từng mất kết nối không hồi sinh dữ liệu cũ; thời điểm thu gom vật lý còn phụ thuộc compaction và điều kiện an toàn.

### 9.3. Consistency không thay thế điều kiện

Ghi `QUORUM` với RF=3 thường yêu cầu ít nhất hai replica xác nhận trong phạm vi quorum. Nhưng câu:

```sql
UPDATE demo.user_preferences_by_id
USING TTL 180
SET otp_code = '772211'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

vẫn là **upsert không điều kiện** dù yêu cầu ở `QUORUM`. Nếu chỉ được cấp OTP cho tài khoản `ACTIVE`, phải dùng `IF account_state = 'ACTIVE'` và kiểm tra `[applied]`. Không có mức xác nhận replica thông thường nào tự biến `UPDATE` thành kiểm tra nghiệp vụ.

### 9.4. Retry có thể kéo dài TTL hoặc ghi đè giá trị mới

Một ví dụ điển hình:

1. Client A gửi `USING TTL 300 SET otp_code = 'A'`.
2. Coordinator hoặc mạng bị timeout, dù một phần replica đã nhận mutation.
3. Client B phát mã mới `'B'`.
4. Client A tự động retry với timestamp mới hoặc TTL mới.

Nếu mutation retry của A thắng theo timestamp, nó có thể **che mã B**, và thời gian sống của A có thể được tính lại theo lần ghi mới. Đây là lý do cần đánh giá idempotency theo **hậu quả nghiệp vụ**, không chỉ theo cú pháp “gán cùng một giá trị”.

Nếu mục tiêu là cấp mã OTP có thời hạn, nên:

- Sinh một ID/phiên xác minh ổn định gắn với yêu cầu cấp mã.
- Kiểm soát việc cấp mã mới và vô hiệu mã cũ ở tầng ứng dụng.
- Hạn chế retry mù quáng với mutation liên quan đến tính hợp lệ theo thời gian.
- Xem xét LWT khi cần kiểm tra phiên/trạng thái cũ; tránh timestamp tùy chỉnh với LWT.

## 10. Java Driver: bind TTL, timestamp và xử lý LWT

Các ví dụ sử dụng **Apache Cassandra Java Driver 4.x**, giả định đã có `CqlSession session`, `UUID userId` và các import tương ứng. Prepared statement giúp bind **giá trị** thay vì nối chuỗi CQL từ input của người dùng.

### 10.1. Bind TTL bằng số giây

```java
PreparedStatement updateOtp = session.prepare(
    "UPDATE demo.user_preferences_by_id " +
    "USING TTL :ttl_seconds " +
    "SET otp_code = :otp_code " +
    "WHERE user_id = :user_id"
);

BoundStatement writeOtp = updateOtp.boundStatementBuilder()
    .setUuid("user_id", userId)
    .setString("otp_code", "538291")
    .setInt("ttl_seconds", 300)  // 300 giay = 5 phut
    .build();

session.execute(writeOtp);
```

Đối số `300` là **giây**. Không truyền `Duration.ofMinutes(5).toMillis()` (300.000) vào marker này, vì sẽ chuyển 5 phút thành nhiều ngày. Nên validate khoảng TTL cho phép của API, tránh mã tạm bị lưu quá lâu.

### 10.2. Bind TIMESTAMP bằng microsecond

```java
PreparedStatement updateLocale = session.prepare(
    "UPDATE demo.user_preferences_by_id " +
    "USING TIMESTAMP :write_ts " +
    "SET preferred_locale = :locale " +
    "WHERE user_id = :user_id"
);

// Chi minh hoa phep doi don vi; production nen dung timestamp
// mac dinh cua driver/Cassandra tru khi co ly do nghiep vu ro rang.
java.time.Instant instant = java.time.Instant.now();
long micros = Math.addExact(
    Math.multiplyExact(instant.getEpochSecond(), 1_000_000L),
    instant.getNano() / 1_000L
);

BoundStatement writeLocale = updateLocale.boundStatementBuilder()
    .setUuid("user_id", userId)
    .setString("locale", "en-US")
    .setLong("write_ts", micros)
    .build();

session.execute(writeLocale);
```

Công thức trên chuyển `Instant` thành microsecond bằng cách giữ phần giây và nano giây; nó chỉ minh họa **đơn vị**. Việc tự phát timestamp từ nhiều máy có đồng hồ lệch vẫn có thể gây thứ tự ghi không như mong muốn. Trong ứng dụng bình thường, thường nên bỏ hẳn `USING TIMESTAMP`.

### 10.3. Bind cả TTL và TIMESTAMP trong UPDATE không điều kiện

```java
PreparedStatement updateWithBoth = session.prepare(
    "UPDATE demo.user_preferences_by_id " +
    "USING TTL :ttl_seconds AND TIMESTAMP :write_ts " +
    "SET otp_code = :otp_code " +
    "WHERE user_id = :user_id"
);

BoundStatement command = updateWithBoth.boundStatementBuilder()
    .setUuid("user_id", userId)
    .setInt("ttl_seconds", 600)
    .setLong("write_ts", micros)
    .setString("otp_code", "712408")
    .build();

session.execute(command);
```

Ví dụ chỉ thể hiện **cú pháp bind hợp lệ** với mutation thường. Không dùng lệnh này trên tài khoản đã có timestamp được tự phát trong tương lai hoặc trong một luồng LWT; phải thống nhất chính sách timestamp của cả hệ thống nếu muốn sử dụng tùy chọn này.

### 10.4. LWT đi với TTL, không đi với TIMESTAMP thủ công

```java
PreparedStatement conditionalOtp = session.prepare(
    "UPDATE demo.user_preferences_by_id " +
    "USING TTL :ttl_seconds " +
    "SET otp_code = :code " +
    "WHERE user_id = :user_id " +
    "IF account_state = :expected_state"
);

ResultSet result = session.execute(
    conditionalOtp.boundStatementBuilder()
        .setUuid("user_id", userId)
        .setInt("ttl_seconds", 120)
        .setString("code", "812306")
        .setString("expected_state", "ACTIVE")
        .build()
);

if (result.wasApplied()) {
    // Dieu kien duoc thoa; OTP da duoc ghi voi TTL.
} else {
    // Tai khoan khong o trang thai mong doi.
}
```

`ResultSet.wasApplied()` là cách driver cho biết điều kiện LWT có được áp dụng không. Không được chỉ kiểm tra “`session.execute` không ném exception” để kết luận `IF` thành công.

### 10.5. Đọc TTL và write timestamp từ CQL

```java
PreparedStatement inspect = session.prepare(
    "SELECT otp_code, TTL(otp_code) AS seconds_left, " +
    "WRITETIME(otp_code) AS write_ts " +
    "FROM demo.user_preferences_by_id WHERE user_id = ?"
);

Row row = session.execute(inspect.bind(userId)).one();
if (row != null) {
    String code = row.getString("otp_code");
    Integer remaining = row.isNull("seconds_left")
        ? null : row.getInt("seconds_left");
    Long timestampMicros = row.isNull("write_ts")
        ? null : row.getLong("write_ts");
    // Khong log ma OTP that; chi su dung thong tin can thiet.
}
```

`TTL(...)` có thể trả `null` khi cell không có TTL hoặc không còn giá trị sống. `WRITETIME(...)` trả write timestamp của cell đang được quan sát; nó không phải nhật ký đầy đủ các phiên bản cũ hoặc tombstone.

### 10.6. Idempotency và retry policy

Driver có metadata về tính idempotent của statement, nhưng đánh dấu một lệnh là `idempotent` **không tạo ra điều kiện LWT** và không bảo vệ trước mọi tranh chấp:

- Đặt một cột thành giá trị cố định thường dễ retry hơn phép cộng counter hoặc append list.
- Với TTL, một lần ghi lại có thể gia hạn thời hạn tồn tại.
- Với timestamp tự động được cấp lại, retry có thể thắng ghi cạnh tranh.
- Với LWT, kết quả `[applied]` và timeout phải được xử lý theo trạng thái nghiệp vụ.

Đừng tự động retry mọi lỗi mạng chỉ vì có `USING TTL` hoặc consistency level cao. Với OTP thật, ưu tiên quy trình cấp mã và idempotency key được thiết kế riêng.

## 11. Bài thực hành: tự kiểm tra TTL, TIMESTAMP và IF

Chỉ thực hiện trong môi trường thử nghiệm với bảng `demo.user_preferences_by_id` đã tạo ở phần 1. Dùng các UUID riêng để kết quả không phụ thuộc dữ liệu ở những ví dụ trước. Các lệnh sai cú pháp trong phần 6–8 chỉ dùng để nhận diện lỗi, **không** cần chạy.

### Bước 1 — Tạo dữ liệu không TTL và đặt TTL cho đúng một cột

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, display_name, account_state
)
VALUES (
    88888888-8888-4888-8888-888888888888,
    'TTL Lab',
    'ACTIVE'
);

UPDATE demo.user_preferences_by_id
USING TTL 90
SET otp_code = 'TEMP-001'
WHERE user_id = 88888888-8888-4888-8888-888888888888;

SELECT display_name, account_state, otp_code,
       TTL(otp_code), TTL(display_name)
FROM demo.user_preferences_by_id
WHERE user_id = 88888888-8888-4888-8888-888888888888;
```

**Dự đoán:** `otp_code` có TTL còn lại gần 90 giây, còn `display_name` không có TTL trong schema mặc định của ví dụ. Không phải mọi cột của hàng đều biến thành dữ liệu tạm chỉ vì một cột có TTL.

### Bước 2 — Ghi cột khác không gia hạn mã

```sql
UPDATE demo.user_preferences_by_id
SET preferred_locale = 'en-US'
WHERE user_id = 88888888-8888-4888-8888-888888888888;

SELECT preferred_locale, otp_code, TTL(otp_code)
FROM demo.user_preferences_by_id
WHERE user_id = 88888888-8888-4888-8888-888888888888;
```

**Dự đoán:** `preferred_locale = 'en-US'`. TTL của OTP **không trở lại 90 giây** chỉ vì mutation mới sửa `preferred_locale`.

### Bước 3 — Ghi lại OTP với TTL mới

```sql
UPDATE demo.user_preferences_by_id
USING TTL 180
SET otp_code = 'TEMP-002'
WHERE user_id = 88888888-8888-4888-8888-888888888888;

SELECT otp_code, TTL(otp_code)
FROM demo.user_preferences_by_id
WHERE user_id = 88888888-8888-4888-8888-888888888888;
```

**Dự đoán:** OTP mới có TTL gần 180 giây sau khi ghi. Đây là một **phiên bản mới**, không chỉ đổi tên một bộ đếm TTL.

### Bước 4 — Quan sát TTL 0

```sql
UPDATE demo.user_preferences_by_id
USING TTL 0
SET otp_code = 'NO-EXPIRY-LAB'
WHERE user_id = 88888888-8888-4888-8888-888888888888;

SELECT otp_code, TTL(otp_code)
FROM demo.user_preferences_by_id
WHERE user_id = 88888888-8888-4888-8888-888888888888;
```

**Dự đoán:** với bảng không có TTL mặc định, giá trị mới không còn TTL, `TTL(otp_code)` thường trả `null`. Chỉ dùng mã minh họa này trong lab: OTP thật không nên được thiết kế lưu vô thời hạn.

### Bước 5 — So sánh hai write timestamp tùy chỉnh

Tạo một khóa **mới hoàn toàn**, và chỉ dùng timestamp thủ công trên khóa này:

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, preferred_locale
)
VALUES (
    99999999-9999-4999-8999-999999999999,
    'vi-VN'
)
USING TIMESTAMP 1700000000000001;

UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000003
SET preferred_locale = 'en-US'
WHERE user_id = 99999999-9999-4999-8999-999999999999;

-- Gửi sau nhưng timestamp nhỏ hơn: không thắng.
UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000002
SET preferred_locale = 'ja-JP'
WHERE user_id = 99999999-9999-4999-8999-999999999999;

SELECT preferred_locale, WRITETIME(preferred_locale)
FROM demo.user_preferences_by_id
WHERE user_id = 99999999-9999-4999-8999-999999999999;
```

**Dự đoán:** giá trị là `'en-US'` với write timestamp `1700000000000003`. Thứ tự chạy câu lệnh không thay thế quy tắc hòa giải timestamp.

### Bước 6 — DELETE với timestamp cũ và mới

Trên cùng khóa lab `9999...`, thử hai dấu xóa:

```sql
-- Tombstone có timestamp thấp hơn giá trị đang sống:
DELETE preferred_locale FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000002
WHERE user_id = 99999999-9999-4999-8999-999999999999;

SELECT preferred_locale
FROM demo.user_preferences_by_id
WHERE user_id = 99999999-9999-4999-8999-999999999999;

-- Tombstone mới hơn:
DELETE preferred_locale FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000004
WHERE user_id = 99999999-9999-4999-8999-999999999999;

SELECT preferred_locale
FROM demo.user_preferences_by_id
WHERE user_id = 99999999-9999-4999-8999-999999999999;
```

**Dự đoán:** dấu xóa `...0002` không che được phiên bản `...0003`, nhưng dấu xóa `...0004` che được nó. Truy vấn cuối có thể không còn trả hàng (nếu không có giá trị sống/row marker phù hợp) hoặc trả `null` ở cột đã xóa; **điểm cần kiểm chứng là `preferred_locale` không còn giá trị sống `'en-US'`**.

### Bước 7 — Kết hợp TTL và TIMESTAMP trong INSERT thường

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, otp_code
)
VALUES (
    cccccccc-cccc-4ccc-8ccc-cccccccccccc,
    'COMBINED'
)
USING TIMESTAMP 1700000000000010 AND TTL 120;

SELECT otp_code, WRITETIME(otp_code), TTL(otp_code)
FROM demo.user_preferences_by_id
WHERE user_id = cccccccc-cccc-4ccc-8ccc-cccccccccccc;
```

**Dự đoán:** `WRITETIME(otp_code)` là timestamp microsecond được chỉ định; `TTL(otp_code)` giảm từ gần 120 giây. Hai số phục vụ **hai mục đích độc lập**.

### Bước 8 — TTL với LWT có điều kiện

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, display_name, account_state
)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    'Conditional Lab',
    'ACTIVE'
);

UPDATE demo.user_preferences_by_id
USING TTL 60
SET otp_code = 'IF-ACTIVE'
WHERE user_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
IF account_state = 'ACTIVE';
```

**Dự đoán:** khi điều kiện đúng, `[applied] = true` và OTP nhận TTL 60 giây. Thử sửa trạng thái rồi gọi lại:

```sql
UPDATE demo.user_preferences_by_id
SET account_state = 'LOCKED'
WHERE user_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

UPDATE demo.user_preferences_by_id
USING TTL 60
SET otp_code = 'SHOULD-NOT-APPLY'
WHERE user_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
IF account_state = 'ACTIVE';
```

**Dự đoán:** lệnh cuối có `[applied] = false`; không ghi mã mới vì trạng thái hiện không còn là `ACTIVE`. Tổ hợp **TTL + IF** hợp lệ, còn **TIMESTAMP tùy chỉnh + IF** thì không.

### Bảng tổng kết phép thử

| Phép thử | Điều cần quan sát |
| --- | --- |
| Ghi OTP với TTL 90 | Chỉ cột được ghi nhận TTL |
| Ghi `preferred_locale` trong khi OTP còn TTL | Không gia hạn OTP |
| Ghi lại OTP với TTL 180 | TTL của phiên bản mới thay đổi |
| `USING TTL 0` | Loại bỏ thời hạn hết hạn ở cell được ghi mới trong bảng lab |
| Ghi timestamp `...0003` rồi `...0002` | Phiên bản timestamp cao hơn thắng |
| Xóa với tombstone `...0002` rồi `...0004` | Timestamp của tombstone quyết định khả năng che dữ liệu cũ |
| INSERT với TTL và TIMESTAMP | Cả hai tham số được áp dụng, với hai đơn vị khác nhau |
| UPDATE TTL có `IF account_state` | Phải kiểm tra `[applied]` của LWT |

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `UPDATE ... SET ... USING TTL 300 WHERE ...` | `USING` của UPDATE đứng **trước `SET`** | `UPDATE table USING TTL 300 SET ... WHERE ...` |
| `INSERT ... VALUES (...) USING TTL ... IF NOT EXISTS` | Với INSERT, `IF NOT EXISTS` nằm **trước `USING`** | `INSERT ... VALUES (...) IF NOT EXISTS USING TTL ...` |
| `DELETE ... USING TTL 300 WHERE ...` | DELETE không hỗ trợ TTL | Ghi giá trị với TTL nếu muốn tự hết hạn, hoặc DELETE để xóa |
| `UPDATE ... USING TIMESTAMP ... IF EXISTS` | LWT không nhận timestamp tùy chỉnh | Bỏ `USING TIMESTAMP`, để LWT quản lý timestamp |
| `INSERT ... IF NOT EXISTS USING TTL ... AND TIMESTAMP ...` | Có timestamp thủ công trong mutation điều kiện | Chỉ giữ TTL hoặc bỏ điều kiện theo yêu cầu thực tế |
| Truyền Java `toEpochMilli()` vào `USING TIMESTAMP` | Millisecond khác microsecond | Chuyển đúng đơn vị hoặc không tự cấp timestamp |
| Truyền `300000` khi muốn TTL 5 phút | TTL tính bằng giây | Truyền `300` |
| Tin rằng TTL một cột là TTL toàn hàng | TTL tác động vào giá trị được ghi | Chỉ định đúng các cột hoặc thiết kế retention |
| Tin rằng ghi lại cùng OTP sau timeout không có hiệu ứng | TTL/timestamp có thể được tính lại | Thiết kế idempotency và xử lý timeout |
| Dùng timestamp quá xa tương lai | Mutation sau có timestamp thấp hơn, không thắng | Không tự tạo timestamp vô căn cứ; kiểm soát nguồn giờ |
| Trộn counter với TTL/TIMESTAMP/LWT | Counter có semantics riêng | Dùng bảng counter và cập nhật cộng/trừ đúng quy tắc |
| Nghĩ `QUORUM` làm `IF` tự xuất hiện | Consistency không phải điều kiện nghiệp vụ | Viết `IF` và kiểm tra `[applied]` |

### Câu hỏi tự kiểm tra

1. **`USING TIMESTAMP` và `USING TTL` có cùng đơn vị không?** Không. TIMESTAMP dùng microsecond từ Unix epoch, TTL dùng giây.
2. **Có thể viết `UPDATE ... USING TTL 120 AND TIMESTAMP ...` không?** Có với mutation thường được hỗ trợ, không có `IF`.
3. **Có thể viết `UPDATE ... USING TTL 120 ... IF EXISTS` không?** Có. Đây là mutation LWT có TTL.
4. **Có thể thêm `TIMESTAMP` vào câu ở câu 3 không?** Không; timestamp tự chọn không tương thích LWT.
5. **Vì sao DELETE không có `USING TTL`?** DELETE tạo dấu xóa; TTL đặt thời gian sống cho giá trị được ghi.
6. **Ghi `phone` với TTL có làm cột `display_name` hết hạn không?** Không, nếu tên không được ghi trong mutation và không chịu chính sách TTL khác.
7. **Vì sao một UPDATE chạy sau vẫn có thể thua?** Write timestamp nhỏ hơn phiên bản tại cell.
8. **Giá trị có TTL ngắn hơn, timestamp lớn hơn hết hạn thì phiên bản cũ tự trở lại không?** Không được giả định như vậy; cơ chế hết hạn/tombstone ngăn hồi sinh dữ liệu cũ.
9. **`IF NOT EXISTS` có tự ghi đè hàng đang tồn tại không?** Không; nếu không thỏa, kết quả `[applied] = false`.
10. **Khi retry OTP sau timeout cần chú ý gì?** Khả năng mutation trước đã áp dụng, timestamp mới và TTL bị làm mới hoặc cạnh tranh với mã vừa cấp.

## 13. Checklist thiết kế và điểm ghi nhớ

Trước khi đưa câu lệnh CQL có `USING` vào ứng dụng Java, hãy xác định:

1. **Đây là INSERT, UPDATE hay DELETE?** Đặt `USING` đúng vị trí của từng statement.
2. **Dữ liệu cần có thời gian sống hay thứ tự phiên bản riêng?** TTL dùng cho hết hạn; TIMESTAMP dùng cho hòa giải; không đánh đồng.
3. **Đơn vị đã đúng chưa?** TTL theo giây, write timestamp theo microsecond; đừng dùng milli giây Java trực tiếp.
4. **Có `IF` không?** Với mutation điều kiện, dùng TTL khi phù hợp và **không** đặt timestamp tùy chỉnh.
5. **Cột nào thực sự được ghi?** TTL chỉ gắn với giá trị trong mutation; cột bị bỏ qua/UNSET không được gia hạn hoặc xóa.
6. **Có dữ liệu cần xóa?** DELETE tạo tombstone; không dùng `USING TTL` trên DELETE.
7. **Có dùng counter/list đặc biệt?** Kiểm tra giới hạn cú pháp, khả năng read-before-write và tính idempotent riêng.
8. **Có nguy cơ đồng hồ lệch, retry hoặc ghi đồng thời?** Thiết kế idempotency key và LWT khi cần bảo vệ trạng thái, không dựa vào timestamp tùy chọn để giả lập giao dịch.
9. **Consistency level, repair và compaction đã được vận hành hợp lý chưa?** Timestamp/TTL không thay thế việc hội tụ các replica hoặc xử lý tombstone an toàn.
10. **Đã thử với khóa riêng trên môi trường lab chưa?** Quan sát `TTL(col)`, `WRITETIME(col)` và `[applied]` trước khi áp dụng vào production.

**Ghi nhớ:** `USING TIMESTAMP` trả lời **“phiên bản nào thắng?”**, `USING TTL` trả lời **“giá trị vừa ghi sống bao lâu?”**. `INSERT` và `UPDATE` thông thường có thể kết hợp cả hai bằng `AND`; `DELETE` chỉ nhận timestamp, không có TTL; mutation có `IF` có thể dùng TTL nhưng **không** dùng write timestamp thủ công; counter có giới hạn riêng. Nắm rõ ma trận này giúp viết CQL đúng cú pháp và duy trì tính đúng đắn khi Cassandra hoạt động qua nhiều replica, lỗi mạng và ứng dụng Java.
