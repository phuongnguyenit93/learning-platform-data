# Đối chiếu trạng thái trước/sau với hai phiên cập nhật đồng thời trong Apache Cassandra

Hai người dùng cùng mở hồ sơ, cùng thấy `revision = 1`, rồi mỗi người thay đổi một giá trị: **điều gì xảy ra khi cả hai ghi về Cassandra?** Có phải request gửi sau luôn thắng, có phải `QUORUM` tự ngăn mất cập nhật, và làm sao chứng minh hai phiên thực sự nhìn thấy gì **trước** và **sau** khi ghi?

Trong Apache Cassandra, `INSERT` và `UPDATE` thông thường là **upsert theo primary key**, không tự đọc và khóa hàng cũ trước khi ghi. Các phiên bản của một cell thường được hòa giải theo **write timestamp** (*last-write-wins*), không thuần túy theo thứ tự lời gọi trong ứng dụng. Nếu nghiệp vụ cần kiểm tra “giá trị vẫn như lúc tôi đọc”, phải chuyển sang **lightweight transaction (LWT)** với `IF`, thường dùng cột `revision` hoặc trạng thái mong đợi.

Bài Knowledge này thuộc chương **Ghi và xóa bằng CQL** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, gắn với mục tiêu hiểu kiến trúc Cassandra phân tán, partition key, CQL, replication, consistency level, xử lý lỗi và ứng dụng Java. Trọng tâm là một **thí nghiệm có hai phiên kết nối độc lập**, ghi lại trạng thái trước/sau, quan sát cập nhật cạnh tranh và xây dựng cách xử lý đúng.

Sau bài học, bạn sẽ:

1. Thiết lập **hai phiên `cqlsh` A/B** truy cập cùng cluster và cùng một full primary key.
2. Phân biệt **đọc trước**, **request ghi**, **acknowledgment**, **đọc sau** và **kết quả LWT `[applied]`**.
3. Quan sát timestamp thắng khi hai phiên ghi **cùng một cột**, kể cả khi thứ tự thực thi khác thứ tự timestamp.
4. So sánh cập nhật **hai cột khác nhau** với cách ghi lại toàn bộ object đã đọc cũ gây **lost update**.
5. Dùng `IF revision = expected` để cho phép một CAS thành công và từ chối writer cũ.
6. Phân tích timeout, retry, tính nhất quán đọc/ghi và cách hiện thực trong Java Driver 4.x.

## 1. Quy ước về “đồng thời” và kết quả dự kiến

Hai phiên độc lập không nhất thiết gửi lệnh vào đúng cùng một microsecond. Trong bài lab, chúng ta dùng hai cửa sổ terminal:

- **Phiên A**: client A, mở `cqlsh` riêng.
- **Phiên B**: client B, mở `cqlsh` riêng, kết nối cùng cluster.

Cả hai có thể **đọc trạng thái đầu giống nhau**, rồi lần lượt gửi yêu cầu trong một lịch thực thi được chỉ định. Đây là cách mô phỏng *interleaving* có kiểm soát của hai writer; khi chạy thực sự song song, thứ tự thắng có thể thay đổi. Với phép ghi thông thường, bài sẽ dùng **timestamp tự chọn trên một khóa lab riêng** để kết quả hòa giải có thể kiểm chứng. Với LWT, **không gán timestamp thủ công** và chỉ dự đoán quy tắc “không quá một CAS từ cùng revision có thể thành công” khi không có writer thứ ba.

### Năm mốc phải ghi vào sổ thí nghiệm

| Mốc | Điều cần lưu | Ý nghĩa |
| --- | --- | --- |
| `T0` — Trước cập nhật | `SELECT` ở A và B, `revision` và các cột liên quan | Trạng thái từng client quan sát trước khi quyết định |
| `T1` — A gửi mutation | CQL, khóa, timestamp/điều kiện và phản hồi | Client A yêu cầu điều gì |
| `T2` — B gửi mutation | CQL, khóa, timestamp/điều kiện và phản hồi | Client B yêu cầu điều gì |
| `T3` — Đọc sau | `SELECT` từ hai phiên với consistency đã chọn | Trạng thái từng lần đọc quan sát |
| `T4` — Đối chiếu | `WRITETIME` hoặc `[applied]`, revision, thay đổi thực tế | Giải thích vì sao xuất hiện kết quả đó |

**Quan trọng:** một lệnh `UPDATE` thường hoàn tất **không** có nghĩa hàng vốn tồn tại, và không trả số hàng thực sự thay đổi. Một `SELECT` sau ghi là **request riêng**, không phải snapshot được trả cùng với `UPDATE`. Trong khi A đọc, B có thể đã tiếp tục ghi.

### Ba kết luận không được suy đoán

1. **“A gửi sau B nên A chắc chắn thắng.”** Sai khi timestamp của A nhỏ hơn B.
2. **“Cả A và B đều ghi thành công nên cả hai giá trị mới cùng được giữ.”** Sai nếu hai mutation cạnh tranh trên **cùng cell**; một phiên bản thắng khi hòa giải.
3. **“Đọc trước thấy revision=1, vậy UPDATE thường có thể kiểm tra revision=1.”** Sai; chỉ thêm `IF revision = 1` mới làm điều kiện đó thuộc quyết định của LWT.

## 2. Tạo bảng và hai phiên CQL an toàn

Các lệnh chỉ dùng trên **cluster thử nghiệm**, trong keyspace `demo` đã tồn tại. Không dùng UUID của tài khoản thật; các khóa `1111...`, `2222...`, `3333...` và `4444...` dưới đây là khóa lab riêng cho từng tình huống.

```sql
CREATE TABLE demo.profile_concurrency_lab (
    profile_id     uuid PRIMARY KEY,
    display_name   text,
    contact_email  text,
    account_state  text,
    revision       int,
    modified_by    text
);
```

`profile_id` là **partition key và full primary key**. Mỗi cột còn lại là regular column. Với schema này, cập nhật ở A/B cùng `profile_id` chắc chắn tranh chấp trong **cùng phân vùng logic**. Dùng khóa khác nhau sẽ không chứng minh được CAS cạnh tranh trên cùng tài nguyên.

Mở hai terminal bằng `cqlsh` trỏ **cùng cluster**. Kiểm tra kết nối vào keyspace/bảng giống nhau, không để một phiên ở môi trường staging còn phiên kia ở production.

**Phiên A**

```sql
-- Terminal A / cqlsh A:
DESCRIBE TABLE demo.profile_concurrency_lab;
```

**Phiên B**

```sql
-- Terminal B / cqlsh B:
DESCRIBE TABLE demo.profile_concurrency_lab;
```

Lệnh `DESCRIBE` là tiện ích của `cqlsh`, không phải CQL server-side cho ứng dụng Java. Hai phiên phải hiển thị schema tương đương. Nếu cluster bật authorization, cả hai role cần đủ quyền trong lab; không tự ý nâng quyền ở production.

### Consistency cho lab

Nếu keyspace `demo` có RF=3 và cluster đủ node khỏe, có thể đặt trên **cả A và B**:

```sql
CONSISTENCY QUORUM;
```

Với RF=3, quorum thông thường cần 2 replica xác nhận trong phạm vi tương ứng. Nếu cluster lab có RF=1, `QUORUM` chỉ cần 1 replica và không chứng minh cùng thuộc tính của RF=3; nếu topology nhiều datacenter, lựa chọn `LOCAL_QUORUM`/`QUORUM` phải theo chiến lược replication. Không thay đổi replication factor chỉ để khớp ví dụ.

**`QUORUM` không tự biến `UPDATE` thường thành compare-and-set**. Chọn consistency chỉ để làm rõ mức xác nhận và khả năng đọc quan sát; chính `IF` mới bảo vệ điều kiện revision.

### Những quy tắc tách biệt dữ liệu

| Khóa lab | Mục đích | Cách ghi |
| --- | --- | --- |
| `11111111-1111-4111-8111-111111111111` | Hai writer cùng cell, đối chiếu write timestamp | **Chỉ timestamp thủ công** trong thí nghiệm này |
| `22222222-2222-4222-8222-222222222222` | Hai writer cập nhật hai cell riêng | Timestamp mặc định |
| `33333333-3333-4333-8333-333333333333` | Lost update do ghi lại dữ liệu đã đọc cũ | **Chỉ timestamp thủ công** trong thí nghiệm này |
| `44444444-4444-4444-8444-444444444444` | LWT/CAS cùng `revision` | **Timestamp mặc định, không `USING TIMESTAMP`** |

Trên khóa có timestamp thủ công, **không trộn một lần INSERT tự phát timestamp hiện tại** rồi dùng giá trị ví dụ trong quá khứ: mutation mới với timestamp nhỏ hơn dữ liệu hiện hành sẽ không thắng. Mọi câu ghi trên hai khóa đó được chỉ định timestamp từ đầu để kết quả dễ kiểm chứng.

## 3. Tình huống A: cùng ghi một cột, timestamp nào thắng?

Để tránh phụ thuộc tốc độ gõ lệnh, dùng ba write timestamp **microsecond từ Unix epoch**: `1700000000000100` (khởi tạo), `1700000000000200` (A) và `1700000000000300` (B). Các giá trị này **chỉ dành cho khóa lab mới**, không dùng như timestamp production.

### T0 — Khởi tạo từ A, rồi cả hai đọc

**Phiên A**

```sql
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, contact_email, account_state, revision
) VALUES (
    11111111-1111-4111-8111-111111111111,
    'Original', 'original@example.test', 'ACTIVE', 1
)
USING TIMESTAMP 1700000000000100;

SELECT display_name, contact_email, account_state,
       revision, WRITETIME(display_name)
FROM demo.profile_concurrency_lab
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

**Phiên B**

```sql
SELECT display_name, contact_email, account_state,
       revision, WRITETIME(display_name)
FROM demo.profile_concurrency_lab
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

**Dự đoán T0:** hai phiên thấy `display_name='Original'`, `revision=1`, và `WRITETIME(display_name)=1700000000000100` khi không có writer khác.

### T1 — B ghi phiên bản có timestamp lớn hơn

**Phiên B**

```sql
UPDATE demo.profile_concurrency_lab
USING TIMESTAMP 1700000000000300
SET display_name = 'Name from B'
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

**B gửi trước A** trong lịch lab này. `UPDATE` thường không kiểm tra revision hay tên cũ; nếu mutation được xác nhận, B không nhận một `[applied]` để biết có xung đột.

### T2 — A gửi sau, nhưng timestamp nhỏ hơn

**Phiên A**

```sql
UPDATE demo.profile_concurrency_lab
USING TIMESTAMP 1700000000000200
SET display_name = 'Name from A'
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

### T3 — Cả hai đọc lại để đối chiếu

**Chạy trên cả A và B**

```sql
SELECT display_name, contact_email, revision,
       WRITETIME(display_name)
FROM demo.profile_concurrency_lab
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

| Trạng thái | `display_name` | `revision` | `WRITETIME(display_name)` |
| --- | --- | ---: | ---: |
| Trước ghi | Original | 1 | 1700000000000100 |
| Sau khi B ghi | Name from B | 1 | 1700000000000300 |
| Sau khi A ghi với timestamp nhỏ hơn | **Name from B** | 1 | **1700000000000300** |

**Kết luận:** Cassandra hòa giải phiên bản của cùng cell theo write timestamp, không phải “request gửi cuối thắng” tính theo đồng hồ tường thuật của người học. Cả hai `UPDATE` thường có thể được xác nhận, nhưng giá trị A không trở thành bản đang sống vì timestamp của A thấp hơn.

### Điều được phép và không được phép suy ra

- `WRITETIME(display_name)` trả timestamp của cell đang được đọc, **không phải lịch sử mọi request** từng gửi.
- `revision` vẫn bằng 1 vì cả hai mutation chỉ ghi `display_name`. Cột revision không tự tăng và không tự cung cấp khóa lạc quan.
- `contact_email` không bị ghi lại chỉ vì A/B cập nhật tên.
- Hai timestamp bằng nhau có quy tắc hòa giải bổ sung; không dùng tie-break này làm chiến lược phân xử nghiệp vụ.
- Thí nghiệm có **timestamp tự đặt** để tạo kết quả ổn định; trong production, timestamp có thể do driver/coordinator cấp theo cấu hình, chịu ảnh hưởng lệch đồng hồ, retry và ghi cạnh tranh.

Một người cập nhật tên bị “thua” về phiên bản không nhất thiết biết điều đó chỉ từ acknowledgement của `UPDATE` thường. Muốn ứng dụng phát hiện xung đột trạng thái cũ, phải dùng một điều kiện phù hợp.

## 4. Tình huống B: hai phiên sửa hai cột khác nhau

Cassandra lưu các regular column như những giá trị có timestamp riêng trong một hàng rộng. Vì thế, **hai lệnh cập nhật một phần, mỗi lệnh chỉ sửa một cột khác nhau**, thường không cần tải và ghi lại toàn bộ object.

### T0 — Tạo hàng riêng và đọc trước

**Phiên A**

```sql
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, contact_email, account_state, revision
) VALUES (
    22222222-2222-4222-8222-222222222222,
    'Before', 'before@example.test', 'ACTIVE', 1
);

SELECT display_name, contact_email, revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

**Phiên B**

```sql
SELECT display_name, contact_email, revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

**Dự đoán T0:** hai phiên đều thấy `display_name='Before'`, `contact_email='before@example.test'` và `revision=1`.

### T1 — A chỉ sửa tên

**Phiên A**

```sql
UPDATE demo.profile_concurrency_lab
SET display_name = 'After A'
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

### T2 — B chỉ sửa email

**Phiên B**

```sql
UPDATE demo.profile_concurrency_lab
SET contact_email = 'after-b@example.test'
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

### T3 — Hai phiên đọc cùng khóa

**Chạy trên cả A và B**

```sql
SELECT display_name, contact_email, revision,
       WRITETIME(display_name), WRITETIME(contact_email)
FROM demo.profile_concurrency_lab
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

| Cột | Trước | Sau hai mutation không điều kiện |
| --- | --- | --- |
| `display_name` | Before | **After A** |
| `contact_email` | before@example.test | **after-b@example.test** |
| `revision` | 1 | **1** — không tự thay đổi |

Với hai mutation thắng theo timestamp trên **hai cell khác nhau**, kết quả logic giữ được **cả hai thay đổi**. Đây là lý do pattern **PATCH theo danh sách cột được gửi** thường thích hợp hơn đọc cả hàng rồi ghi lại mọi trường đã đọc.

**Nhưng đừng suy ra từ ví dụ này mọi cập nhật đồng thời đều an toàn.** Nếu hai client thật sự cần duy trì invariant liên quan cả hai cột (ví dụ hai trạng thái không được mâu thuẫn), ghi riêng từng cell không tự bảo vệ invariant đó. Khi đó cần mô hình dữ liệu và điều kiện CAS phù hợp.

### NULL không phải “không gửi”

Nếu B không có ý định sửa tên, đừng bind `display_name = NULL` vào mutation:

```sql
-- Đây là một yêu cầu xóa giá trị tên, KHÔNG phải bỏ qua tên.
UPDATE demo.profile_concurrency_lab
SET display_name = NULL
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

Câu trên **chỉ dùng để minh họa nguy cơ**, không chạy nếu muốn giữ kết quả lab. Cassandra hiểu `NULL` ở regular column là tombstone, còn **không nêu cột** hoặc dùng marker `UNSET` trong driver là không tạo mutation cho cột ấy. Đây là khác biệt quan trọng khi hai phiên gửi JSON PATCH.

## 5. Tình huống C: lost update khi ghi lại dữ liệu đã đọc cũ

Một lỗi phổ biến của ứng dụng Java là thực hiện:

1. `SELECT` toàn bộ hàng.
2. Chuyển thành object `Profile` trong memory.
3. Sửa một field trong object.
4. `UPDATE` lại **mọi field**, kể cả các field người dùng không thay đổi.

Nếu hai client bắt đầu từ cùng một snapshot cũ, request đến sau có thể **ghi đè ngược** thay đổi mới của request trước. Đó là *lost update* do cách xây dựng mutation, không phải vì Cassandra “tự xóa” những field đã bỏ qua.

Để tái hiện ổn định, dùng khóa `3333...` và timestamp thủ công **chỉ trong tình huống C**.

### T0 — Hai phiên đều đọc giá trị cũ

**Phiên A**

```sql
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, contact_email, account_state, revision
) VALUES (
    33333333-3333-4333-8333-333333333333,
    'Initial Name', 'old@example.test', 'ACTIVE', 1
)
USING TIMESTAMP 1700000000001100;

SELECT display_name, contact_email, revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 33333333-3333-4333-8333-333333333333;
```

**Phiên B**

```sql
SELECT display_name, contact_email, revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 33333333-3333-4333-8333-333333333333;
```

Trong bộ nhớ của B, giá trị email được đọc là `'old@example.test'`. B định đổi **tên**, không định đổi **email**. Sau bước này, **B không đọc lại** cho tới sau T2.

### T1 — A sửa email trước

**Phiên A**

```sql
UPDATE demo.profile_concurrency_lab
USING TIMESTAMP 1700000000001200
SET contact_email = 'new-a@example.test'
WHERE profile_id = 33333333-3333-4333-8333-333333333333;
```

Nếu đọc ngay sau T1, `contact_email='new-a@example.test'` đã thay thế giá trị cũ tại cell email.

### T2 — B ghi cả tên mới lẫn email cũ đã giữ trong object

**Phiên B**

```sql
-- Sai ve y dinh nghiep vu: B chi muon sua ten,
-- nhung UPDATE lai mang theo email da doc truoc do.
UPDATE demo.profile_concurrency_lab
USING TIMESTAMP 1700000000001300
SET display_name = 'Name from B',
    contact_email = 'old@example.test'
WHERE profile_id = 33333333-3333-4333-8333-333333333333;
```

B mang timestamp lớn hơn A ở **cell email**, nên giá trị cũ bị ghi trở lại như một phiên bản mới. Đây không phải “Cassandra khôi phục dữ liệu cũ”; **client B chủ động gửi giá trị cũ trong mutation mới**.

### T3 — Đọc lại và lập bảng đối chiếu

**Chạy trên cả A và B**

```sql
SELECT display_name, contact_email, revision,
       WRITETIME(display_name), WRITETIME(contact_email)
FROM demo.profile_concurrency_lab
WHERE profile_id = 33333333-3333-4333-8333-333333333333;
```

| Mốc | Tên | Email | Revision |
| --- | --- | --- | ---: |
| T0 — Cả hai đọc | Initial Name | old@example.test | 1 |
| T1 — A sửa email | Initial Name | **new-a@example.test** | 1 |
| T2 — B ghi object cũ + tên mới | **Name from B** | **old@example.test** | 1 |

`WRITETIME(contact_email)` cuối cùng bằng `1700000000001300`: dấu hiệu bản email mới nhất là mutation của B, **không phải mutation của A**.

### Ba cách giảm nguy cơ lost update

1. **Chỉ ghi các field thực sự thay đổi**. Nếu B chỉ có ý định sửa tên, hãy `SET display_name = 'Name from B'`; trong tình huống không có invariant giữa các cột, A's email được giữ.
2. **Ghi có điều kiện theo revision/giá trị cũ**. Nếu B chỉ được phép cập nhật khi không có ai sửa hồ sơ kể từ lần đọc trước, dùng `IF revision = expected` và tăng revision trong **cùng mutation**.
3. **Định nghĩa hợp đồng API rõ ràng**. `PATCH` khác `PUT` kiểu thay toàn object; chọn cách merge/trả conflict có chủ đích. Tránh map một field vắng mặt thành `NULL`.

Lưu ý: cập nhật chọn lọc field **không tự bảo vệ** quy tắc giữa nhiều field. Nếu trạng thái A và B phải thay đổi cùng nhau theo invariant, lựa chọn đúng có thể vẫn là CAS hoặc một mô hình partition riêng.

## 6. Tình huống D: hai phiên cạnh tranh bằng IF revision

Giờ thay mutation thông thường bằng **LWT**. Hai phiên cùng đọc `revision=1` và đều muốn thay đổi `account_state`. Chỉ một mutation có điều kiện `IF revision = 1` được áp dụng trước khi revision thay đổi thành 2, khi tất cả writer liên quan đều tuân thủ cùng quy ước CAS.

**Không** dùng `USING TIMESTAMP` cùng `IF`. LWT/Paxos quản lý timestamp và phối hợp điều kiện qua các replica. Tình huống D dùng khóa mới, không có timestamp thủ công.

### T0 — Khởi tạo và hai phiên đọc cùng revision

**Phiên A**

```sql
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, contact_email,
    account_state, revision
) VALUES (
    44444444-4444-4444-8444-444444444444,
    'Cas Lab', 'cas@example.test', 'PENDING', 1
);

SELECT account_state, revision, modified_by
FROM demo.profile_concurrency_lab
WHERE profile_id = 44444444-4444-4444-8444-444444444444;
```

**Phiên B**

```sql
SELECT account_state, revision, modified_by
FROM demo.profile_concurrency_lab
WHERE profile_id = 44444444-4444-4444-8444-444444444444;
```

**Dự đoán T0:** cả hai thấy `account_state='PENDING'`, `revision=1` và `modified_by=null`.

### T1 — A gửi compare-and-set

**Phiên A**

```sql
UPDATE demo.profile_concurrency_lab
SET account_state = 'REVIEW',
    revision = 2,
    modified_by = 'A'
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF revision = 1;
```

Nếu không có writer cạnh tranh đã sửa revision trước A, phản hồi có cột `[applied] = true`. A đã yêu cầu một **transition có điều kiện**; revision được đổi thành 2 trong cùng mutation.

### T2 — B gửi mutation với revision cũ

**Phiên B**

```sql
UPDATE demo.profile_concurrency_lab
SET account_state = 'APPROVED',
    revision = 2,
    modified_by = 'B'
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF revision = 1;
```

Trong lịch thực hành A đã thành công trước B, nên phản hồi của B là **`[applied] = false`**. Một số phiên bản/CQL statement có thể trả kèm cột thể hiện giá trị hiện có khi điều kiện không thỏa; không giả định luôn nhận được toàn bộ hàng.

Nếu A và B thật sự gửi **đồng thời**, ai được áp dụng trước phụ thuộc lịch xử lý đồng thuận. Điều chắc chắn trong thí nghiệm không có writer thứ ba và mỗi CAS đều tăng revision: **không thể cả hai cùng áp dụng với cùng expected revision = 1**.

### T3 — Đọc sau cả hai yêu cầu

**Chạy trên cả A và B**

```sql
SELECT account_state, revision, modified_by
FROM demo.profile_concurrency_lab
WHERE profile_id = 44444444-4444-4444-8444-444444444444;
```

| Mốc | `account_state` | `revision` | `modified_by` | Phản hồi |
| --- | --- | ---: | --- | --- |
| T0 | PENDING | 1 | null | SELECT |
| T1 — A CAS | REVIEW | 2 | A | **`[applied] = true`** |
| T2 — B CAS cũ | REVIEW | 2 | A | **`[applied] = false`** |
| T3 — Đọc sau | REVIEW | 2 | A | SELECT |

**Điểm khác biệt cốt lõi với tình huống A/C:** B **không ghi được** thay đổi của mình khi điều kiện đã lỗi thời. Ứng dụng biết điều đó qua `[applied]`, thay vì chỉ nhận acknowledgment của một upsert.

### B phải xử lý false như thế nào?

B **không nên** đổi `IF revision = 1` thành `IF revision = 2` rồi gửi lại mù quáng. B cần:

1. Đọc trạng thái hiện tại để biết A đã chuyển `PENDING → REVIEW`.
2. Quyết định theo nghiệp vụ liệu `REVIEW → APPROVED` có được phép không.
3. Nếu được phép, gửi CAS mới với **expected revision = 2**.
4. Nếu còn xung đột, giới hạn số lần retry và báo conflict cho client.

Ví dụ chỉ khi quy tắc nghiệp vụ cho phép:

```sql
UPDATE demo.profile_concurrency_lab
SET account_state = 'APPROVED',
    revision = 3,
    modified_by = 'B'
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF account_state = 'REVIEW' AND revision = 2;
```

LWT này có thể trả `[applied] = true` và đưa revision lên 3. Đây là **một quyết định mới dựa trên trạng thái vừa đọc**, không phải tự động “retry nguyên request cũ cho tới khi thắng”.

## 7. So sánh IF EXISTS, IF NOT EXISTS và IF giá trị cũ

Không phải cứ thêm một từ khóa `IF` thì mọi xung đột giữa hai phiên đều được ngăn giống nhau. Điều kiện phải khớp với **bất biến nghiệp vụ**.

| Điều kiện | Điều được bảo vệ | Điều **không** tự được bảo vệ |
| --- | --- | --- |
| `INSERT ... IF NOT EXISTS` | Chỉ tạo hàng nếu **full primary key chưa tồn tại** | Unique của cột thường như email trên toàn bảng |
| `UPDATE ... IF EXISTS` | Chỉ sửa khi hàng đang tồn tại | Hai writer sửa cùng cột trong khi hàng vẫn tồn tại |
| `DELETE ... IF EXISTS` | Chỉ xóa khi hàng đang tồn tại | Việc một writer khác tạo lại hàng sau xóa |
| `UPDATE ... IF revision = 1` | Chỉ ghi khi giá trị revision đang khớp | Những đường ghi **không** tuân theo quy ước revision |
| `UPDATE ... IF account_state = 'PENDING'` | Chỉ chuyển trạng thái từ PENDING khi điều kiện đúng | Những invariant của các partition khác |

### Vì sao IF EXISTS không đủ ngăn lost update?

Giả sử hàng `4444...` vẫn tồn tại:

```sql
-- Phiên A có thể gửi:
UPDATE demo.profile_concurrency_lab
SET display_name = 'Edited by A'
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF EXISTS;

-- Phiên B có thể gửi:
UPDATE demo.profile_concurrency_lab
SET display_name = 'Edited by B'
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF EXISTS;
```

Nếu không có delete hay thay đổi làm hàng biến mất, **cả hai điều kiện tồn tại có thể đúng**. `[applied] = true` của mỗi yêu cầu chỉ nói điều kiện tồn tại thỏa; nó **không** chứng minh giá trị trước đó của `display_name` còn giống lúc client đọc. Những câu trên chỉ là ví dụ phân tích, **không chạy sau bài lab CAS nếu muốn giữ trạng thái `revision=2`**.

### Hai phiên cùng đăng ký một khóa

Giả sử cả A và B muốn tạo **cùng `profile_id` mới**:

```sql
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, account_state, revision
) VALUES (
    66666666-6666-4666-8666-666666666666,
    'New Profile', 'PENDING', 1
)
IF NOT EXISTS;
```

Nếu hai phiên đều gửi chính câu này trên **cùng full primary key** lúc hàng chưa có và không có writer thứ ba, một request có thể trả `[applied] = true` và request còn lại trả `false` sau khi khóa đã được tạo. Ai thắng phụ thuộc lịch quyết định LWT. Nhưng **hai khóa UUID khác nhau** sẽ không tranh chấp chỉ vì cột `display_name` trùng nhau.

### Những giới hạn của revision

- `revision` không được Cassandra tự tăng. Ứng dụng phải gửi `SET revision = new` cùng mutation có `IF revision = expected`.
- Nếu client khác ghi `revision` bằng `UPDATE` **không điều kiện**, quy tắc CAS của ứng dụng có thể bị phá vỡ. Tất cả đường ghi của cùng invariant phải thống nhất.
- Dùng revision tăng đơn điệu thay cho cờ boolean để tránh lỗi kiểu **ABA** (giá trị quay lại trạng thái cũ mà client không phát hiện lịch sử thay đổi), nhưng cũng phải kiểm soát overflow và tránh tự đặt lại revision về số cũ.
- LWT không bảo đảm giao dịch xuyên nhiều partition tùy ý. Bảo vệ uniqueness của email cần một mô hình khóa theo email hoặc workflow riêng, không chỉ `IF NOT EXISTS` theo `profile_id`.

## 8. Kết quả trước/sau khác với acknowledgment

Thực hiện đúng thí nghiệm không chỉ nhìn hàng cuối cùng: phải phân biệt **phản hồi của ghi** với **trạng thái quan sát bởi truy vấn đọc**.

### Với UPDATE thường

```text
Client A: UPDATE ... SET display_name = 'A'
Server:   xác nhận mutation theo write consistency level
Client A: không nhận row count, không nhận cờ created/updated

Client B: UPDATE ... SET display_name = 'B'
Server:   cũng có thể xác nhận mutation

Client A/B: SELECT ... -> thấy giá trị thắng sau hòa giải
```

**Hai acknowledgment** không có nghĩa **hai giá trị cùng được giữ** trong một cell, và cũng không tự nói giá trị nào đã thắng. Muốn đối chiếu, cần biết khóa, timestamp và quan sát đọc.

### Với UPDATE IF

```text
Client A: UPDATE ... IF revision = 1
Server:   [applied] = true

Client B: UPDATE ... IF revision = 1
Server:   [applied] = false

Client A/B: SELECT ... -> quan sát state/revision
```

`[applied] = false` là **kết quả hợp lệ của điều kiện không thỏa**, không phải exception. Một số dạng LWT có thể trả kèm giá trị hiện có trong kết quả false; **không dựa vào đó như ảnh chụp toàn bộ hàng bất biến**, vì danh sách cột phụ thuộc câu lệnh và writer khác có thể tiếp tục ghi sau phản hồi.

### Ma trận đối chiếu bốn tình huống

| Tình huống | Hai phiên đọc T0 | Mutation | Phản hồi ghi | Trạng thái sau dự kiến |
| --- | --- | --- | --- | --- |
| A — Cùng cell, timestamp khác nhau | Cùng tên Original | B ts300; A ts200 | Hai UPDATE thường có thể thành công | **Tên của B** vì timestamp cao hơn |
| B — Hai cell khác nhau | Cùng tên/email ban đầu | A ghi tên; B ghi email | Hai UPDATE thường | **Cả hai cột mới** được giữ |
| C — Ghi cả object cũ | Cùng tên/email ban đầu | A đổi email; B ghi tên + email cũ ở ts cao hơn | Hai UPDATE thường | **Email của A bị mất** |
| D — CAS cùng revision | Cùng revision 1 | A rev1→2; B vẫn IF rev1 | A true; B false theo lịch minh họa | **Mutation A** được áp dụng |

Đối chiếu giá trị sau chỉ có ý nghĩa khi biết trạng thái writer khác, consistency và timestamp. Đừng biến kết quả đọc từ một replica vào một thời điểm thành bằng chứng rằng **mọi replica** đã hội tụ.

## 9. Hai phiên ở các replica: read consistency và write consistency

Cassandra nhân bản partition lên các replica theo replication factor và chiến lược của keyspace. Hai phiên `cqlsh` có thể kết nối tới **coordinator khác nhau** nhưng vẫn định vị **cùng một partition key**. Kết quả quan sát có thể bị ảnh hưởng bởi replica nào đã nhận mutation và consistency level của từng request.

### Ví dụ keyspace RF=3

| Thiết lập | Ý nghĩa cơ bản | Giới hạn cần nhớ |
| --- | --- | --- |
| Write `ONE` | Có thể xác nhận với một replica phù hợp | Replica khác có thể chưa theo kịp |
| Write `QUORUM` | Với RF=3 thường cần 2 xác nhận | Không có nghĩa mọi replica đã nhận ghi |
| Read `ONE` | Có thể đọc từ một replica | Có thể quan sát phiên bản cũ trong điều kiện phù hợp |
| Read `QUORUM` | Với RF=3 thường đọc đủ quorum | Có thể tăng khả năng nhìn ghi đã hoàn thành ở quorum, nhưng phải xét timestamp và ghi đồng thời |
| LWT `SERIAL`/`LOCAL_SERIAL` | Phạm vi đồng thuận khi xử lý điều kiện | Không thể thay `IF` bằng chỉ tăng write consistency |

Với RF=3, đọc quorum và ghi quorum có giao nhau về replica, giúp đạt tính nhất quán mạnh đối với nhiều kịch bản **không có writer cạnh tranh**, đồng hồ timestamp hợp lệ và các giả định khác phù hợp. Tuy nhiên, nếu hai mutation cùng cell có timestamp khác nhau, quy tắc hòa giải timestamp vẫn quyết định giá trị thắng. **`QUORUM` không cấp phép “ai đọc trước thì được ghi trước”**.

### Tại sao hai phiên SELECT có thể khác nhau?

Nếu A đọc ở `ONE` ngay sau một ghi chỉ được xác nhận ở `ONE`, còn B đọc từ replica chưa nhận mutation, kết quả có thể khác. Đó là vấn đề **quan sát replica**, tách biệt với lỗi *lost update* do hai writer ghi đè cùng cell.

Để giải thích lab:

1. Kiểm tra A/B cùng cluster/keyspace.
2. Ghi lại consistency level của từng phiên.
3. Xác định write đã được xác nhận hay timeout.
4. Xem khóa và write timestamp, không chỉ thứ tự gõ lệnh.
5. Đọc lại theo consistency đã thống nhất, tránh sử dụng `ONE` rồi kết luận toàn cụm đã đồng bộ.

### LWT cần serial consistency

Mutation có `IF` sử dụng cơ chế đồng thuận kiểu Paxos. Bên cạnh regular consistency của mutation, còn có **serial consistency** như `SERIAL` hoặc `LOCAL_SERIAL`. Trong hệ thống nhiều datacenter, lựa chọn phải phù hợp topology và nơi các client gửi CAS.

Không nên trộn tùy tiện `SERIAL` và `LOCAL_SERIAL` đối với các CAS cạnh tranh trên cùng dữ liệu nếu chưa có chính sách nhất quán đa vùng. Sơ đồ thí nghiệm một cluster đơn giản không chứng minh mọi giả định trên hệ đa datacenter.

### Không đánh đồng read-before-write với LWT

Hai phiên cùng thực hiện:

```text
SELECT revision -> 1
... client xử lý input ...
UPDATE ... SET revision = 2
```

thì **SELECT và UPDATE là hai request khác nhau**. Không có isolation ngăn client khác thay revision ở giữa. Chỉ:

```sql
UPDATE demo.profile_concurrency_lab
SET revision = 2
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF revision = 1;
```

mới kiểm tra revision khi quyết định mutation; câu trên cũng **không nên chạy độc lập** sau tình huống D nếu đang cần giữ kết quả thực hành. Trong ứng dụng thật, khi cập nhật trạng thái, **thay đổi trạng thái và revision phải cùng mutation** để tránh revision tăng nhưng nghiệp vụ không đổi.

## 10. Retry, timeout và hai phiên sửa xen giữa

Một request có thể được cluster chấp nhận nhưng **response không đến client** vì lỗi mạng hoặc coordinator timeout. Do đó:

- Timeout của `UPDATE` thường **không** chứng minh mutation chưa đến replica.
- Timeout của `UPDATE ... IF` **không** tương đương `[applied] = false`.
- Retry một `UPDATE` thường với timestamp mới có thể ghi đè phiên bản client khác vừa ghi trong khoảng giữa hai lần gửi.
- Retry một CAS sau lần đầu đã thành công có thể nhận `[applied] = false` vì revision đã được tăng. Không được coi false đó chắc chắn là “người khác đã thắng”.

### Ví dụ timeout của A

```text
T0: profile revision=1
A:  UPDATE ... SET state='REVIEW', revision=2 IF revision=1
    -> cluster áp dụng, nhưng response true bị mất
B:  SELECT thấy revision=2
A:  retry nguyên CAS IF revision=1
    -> nhận false
```

Kết quả false của lần retry **không cho biết** lần đầu của A đã thất bại. Muốn xác định tác động của một logical request, có thể lưu **request ID ổn định** cùng mutation và đối chiếu, hoặc thiết kế một workflow idempotency được kiểm chứng.

### Quy tắc xử lý cho API

| Kết quả | Cách hiểu đúng | Hướng xử lý |
| --- | --- | --- |
| UPDATE thường xác nhận | Mutation đạt consistency yêu cầu | Không giả tạo row count hoặc cờ không xung đột |
| LWT `[applied] = true` | Điều kiện thỏa, mutation đã áp dụng | Có thể trả thành công |
| LWT `[applied] = false` | Điều kiện không thỏa trong lần kiểm tra này | Đọc lại trạng thái, xử lý conflict/điều kiện |
| Timeout/không biết kết quả | Một phần hoặc toàn bộ hiệu ứng có thể đã xảy ra | Không suy diễn false; đối chiếu và retry có kiểm soát |
| Validation lỗi trước khi có mutation hợp lệ | Request cần sửa | Không retry nguyên input vô hạn |

Nếu API phải báo `409 Conflict` hoặc `412 Precondition Failed` cho CAS lỗi thời, hãy dựa trên **`[applied] = false`** cùng thông tin hợp đồng, không dùng một exception timeout để giả làm conflict.

## 11. Java Driver 4.x: hai logical writer cùng gửi CAS

Trong ứng dụng Java, hai phiên độc lập có thể là hai API request, hai service instance hoặc hai thread. `CqlSession` của **Apache Cassandra Java Driver 4.x** được thiết kế để dùng chung cho các request; không cần tạo TCP connection mới cho mỗi writer. Điều cần tách là **đầu vào, expected revision và kết quả của từng request**.

### 11.1. Prepared statement của CAS

```java
PreparedStatement cas = session.prepare(
    "UPDATE demo.profile_concurrency_lab " +
    "SET account_state = :next_state, " +
    "    revision = :next_revision, " +
    "    modified_by = :author " +
    "WHERE profile_id = :profile_id " +
    "IF revision = :expected_revision"
);

BoundStatement fromA = cas.boundStatementBuilder()
    .setUuid("profile_id", profileId)
    .setString("next_state", "REVIEW")
    .setInt("next_revision", 2)
    .setString("author", "A")
    .setInt("expected_revision", 1)
    .build();

BoundStatement fromB = cas.boundStatementBuilder()
    .setUuid("profile_id", profileId)
    .setString("next_state", "APPROVED")
    .setInt("next_revision", 2)
    .setString("author", "B")
    .setInt("expected_revision", 1)
    .build();
```

Hai `BoundStatement` **khác nhau về trạng thái mong muốn** nhưng cùng `profile_id` và cùng `expected_revision = 1`. Java Driver bind đúng kiểu dữ liệu, còn LWT xử lý điều kiện ở cluster. Không cần `SELECT` ngay trong Java mỗi lần gửi CAS nếu client đã có revision đáng tin cậy và xử lý conflict đúng cách.

### 11.2. Mô phỏng A/B đồng thời bằng CountDownLatch

Ví dụ dưới đây dùng **một hàng lab chưa tồn tại** và hai tác vụ Java được mở khóa gần như cùng lúc. Phần đồng thuận của Cassandra quyết định ai thắng; `CountDownLatch` chỉ giúp hai client **bắt đầu gửi gần cùng thời điểm**, không ép các request đến node cùng một microsecond.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class CasRaceDemo {
    public static void run(CqlSession session) throws Exception {
        UUID id = UUID.fromString(
            "88888888-8888-4888-8888-888888888888");

        ResultSet created = session.execute(
            SimpleStatement.newInstance(
                "INSERT INTO demo.profile_concurrency_lab " +
                "(profile_id, account_state, revision) " +
                "VALUES (?, ?, ?) IF NOT EXISTS",
                id, "PENDING", 1
            )
        );
        if (!created.wasApplied()) {
            throw new IllegalStateException(
                "Lab ID da ton tai; dung khoa moi cho lan chay nay");
        }

        PreparedStatement cas = session.prepare(
            "UPDATE demo.profile_concurrency_lab " +
            "SET account_state = :next_state, " +
            "revision = 2, modified_by = :author " +
            "WHERE profile_id = :profile_id IF revision = 1"
        );

        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> a = pool.submit(() -> {
                start.await();
                BoundStatement stmt = cas.boundStatementBuilder()
                    .setUuid("profile_id", id)
                    .setString("next_state", "REVIEW")
                    .setString("author", "A")
                    .build();
                return session.execute(stmt).wasApplied();
            });

            Future<Boolean> b = pool.submit(() -> {
                start.await();
                BoundStatement stmt = cas.boundStatementBuilder()
                    .setUuid("profile_id", id)
                    .setString("next_state", "APPROVED")
                    .setString("author", "B")
                    .build();
                return session.execute(stmt).wasApplied();
            });

            start.countDown();
            boolean aApplied = a.get();
            boolean bApplied = b.get();

            System.out.printf(
                "A applied=%s; B applied=%s%n", aApplied, bApplied);

            if (aApplied == bApplied) {
                throw new IllegalStateException(
                    "Ket qua khong khop ky vong 1 true/1 false");
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Với hàng mới, không có writer thứ ba và **hai lời gọi không gặp exception**, kỳ vọng là **một `true` và một `false`**. Không được hardcode “A luôn thắng”: thứ tự hoàn thành thực tế có thể đổi sau mỗi lần chạy.

Nếu `Future.get()` ném exception do timeout hoặc lỗi driver, đoạn mã **không** có đủ hai boolean để kết luận ai thắng. Cần xử lý nhánh kết quả không xác định riêng, kiểm tra trạng thái và request ID; **không bắt exception rồi trả `false`**.

### 11.3. Đọc sau hai CAS

```java
PreparedStatement inspect = session.prepare(
    "SELECT account_state, revision, modified_by " +
    "FROM demo.profile_concurrency_lab WHERE profile_id = ?"
);

Row current = session.execute(inspect.bind(profileId)).one();
if (current != null) {
    String state = current.getString("account_state");
    int revision = current.getInt("revision");
    String writer = current.getString("modified_by");
    // state/author phai phu hop voi writer da duoc ap dung;
    // revision du kien = 2 neu co dung mot CAS thanh cong.
}
```

`Row` thuộc `com.datastax.oss.driver.api.core.cql.Row`. Giá trị `profileId` ở đoạn đọc phải là **chính UUID của hàng vừa được thí nghiệm**, không dùng nhầm khóa `4444...` của cqlsh nếu đang kiểm tra hàng Java `8888...`.

### 11.4. Kiểm soát expected revision từ HTTP API

Một `PATCH /profiles/{id}` có thể nhận một số phiên bản, ví dụ `expectedRevision = 12`. Ứng dụng:

1. Validate người dùng có quyền sửa `profile_id`.
2. Lấy các field thật sự được thay đổi và trạng thái mới hợp lệ.
3. Tính `nextRevision = expectedRevision + 1` có kiểm tra overflow.
4. Gửi `UPDATE ... SET changed_fields, revision = nextRevision ... IF revision = expectedRevision`.
5. Nếu `wasApplied()` true, trả thành công; false thì xử lý `409 Conflict` hoặc `412 Precondition Failed` theo hợp đồng.
6. Nếu timeout, không biến thành false; trả trạng thái lỗi hợp lý và có đường đối chiếu.

Khi sử dụng API nhận optional fields, phân biệt **cột vắng mặt**, **UNSET** và **NULL**:

```java
// Prepared statement co marker :display_name va :contact_email.
// Neu client chi yeu cau doi ten:
BoundStatementBuilder builder = prepared.boundStatementBuilder()
    .setUuid("profile_id", profileId)
    .setString("display_name", "New Name")
    .unset("contact_email");

// Khong dung setToNull("contact_email") de bieu dien field vang mat:
// NULL la mutation xoa gia tri, UNSET la bo qua field do.
```

`BoundStatementBuilder` là kiểu `com.datastax.oss.driver.api.core.cql.BoundStatementBuilder`. Đoạn trên chỉ minh họa semantics marker đã được khai báo trong `prepared`; với CAS thực tế, câu CQL phải có `IF revision = ...` và các marker tương ứng. Không gửi một prepared statement thiếu bind các marker bắt buộc của khóa và revision.

## 12. DELETE và ghi mới cũng có thể cạnh tranh

Chương này nói về cả **ghi và xóa bằng CQL**. Nếu A xóa hàng và B ghi lại hàng cùng full primary key, Cassandra vẫn phải hòa giải **tombstone** và phiên bản mới theo timestamp.

### Minh họa trên khóa riêng với timestamp kiểm soát

```sql
-- Khởi tạo riêng cho tình huống DELETE vs UPDATE.
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, account_state, revision
) VALUES (
    77777777-7777-4777-8777-777777777777,
    'Before Delete', 'ACTIVE', 1
)
USING TIMESTAMP 1700000000002100;

-- A xóa toàn hàng với timestamp mới hơn.
DELETE FROM demo.profile_concurrency_lab
USING TIMESTAMP 1700000000002200
WHERE profile_id = 77777777-7777-4777-8777-777777777777;

-- B ghi lại cùng khóa với timestamp còn mới hơn.
UPDATE demo.profile_concurrency_lab
USING TIMESTAMP 1700000000002300
SET display_name = 'Recreated by B'
WHERE profile_id = 77777777-7777-4777-8777-777777777777;

SELECT display_name, account_state, revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 77777777-7777-4777-8777-777777777777;
```

Với dữ liệu lab mới và không có writer khác, sau DELETE các giá trị cũ bị tombstone che. Khi B ghi cell `display_name` có timestamp **mới hơn row tombstone**, giá trị mới có thể xuất hiện; `account_state` và `revision` cũ **không tự trở lại** chỉ vì B tái ghi một cell.

**DELETE không tạo quy tắc “khóa này bị cấm sử dụng mãi mãi”.** Nếu nghiệp vụ cần cấm tạo lại tài nguyên đã hủy, phải dùng trạng thái/tombstone nghiệp vụ hoặc cơ chế kiểm soát tạo mới riêng, không chỉ dựa vào một lệnh xóa dữ liệu.

### Khi nào DELETE IF EXISTS không đủ?

`DELETE ... IF EXISTS` kiểm tra hàng có tồn tại trước khi xóa. Nó không đảm bảo một writer khác không thể upsert hàng sau đó. Nếu mục tiêu là chuyển trạng thái `ACTIVE → DELETED` và ngăn tái tạo, một mô hình **soft delete có revision/điều kiện** hoặc khóa claim/retention riêng thường phù hợp hơn xóa vật lý đơn giản. Cần xác định chính sách GDPR/retention/backup tùy nghiệp vụ thay vì coi soft delete là thay thế bắt buộc cho xóa thật.

## 13. Thực hành tổng hợp: đối chiếu hai phiên theo một bảng kết quả

Để tự đánh giá, hãy chạy lại các tình huống A–D **từng tình huống một** trên cluster lab. Sau mỗi mutation, ghi **kết quả từ chính terminal gửi lệnh** và sau đó mới ghi **kết quả SELECT**. Không bỏ qua bước đọc trước từ cả A và B.

### Bước 1 — Xác định đúng hai phiên

Kiểm tra A/B cùng schema `demo.profile_concurrency_lab`. Ghi consistency level của mỗi phiên. Không dùng bảng production hoặc các khóa đang được chương trình khác sử dụng.

### Bước 2 — Chụp trạng thái ban đầu

Với từng UUID lab, cả A và B chạy:

```sql
SELECT display_name, contact_email, account_state,
       revision, modified_by
FROM demo.profile_concurrency_lab
WHERE profile_id = 44444444-4444-4444-8444-444444444444;
```

Đây là truy vấn của tình huống D; thay UUID theo tình huống đang thử. Ghi giá trị **trước khi một phiên gửi UPDATE**. Nếu A/B thấy khác nhau ngay T0, chưa thể kết luận về xung đột writer; cần kiểm tra consistency, dữ liệu seed và trạng thái replica.

### Bước 3 — Chạy lịch A hoặc B được chỉ định

- **Tình huống A:** B ghi cùng cột với timestamp 0300, A ghi sau với 0200.
- **Tình huống B:** A chỉ ghi `display_name`, B chỉ ghi `contact_email`.
- **Tình huống C:** A ghi email mới ts1200; B ghi tên mới **và email cũ** ts1300.
- **Tình huống D:** A gửi `IF revision=1` trước, sau khi true mới cho B gửi `IF revision=1`.

Không thay thứ tự T1/T2 nếu bạn muốn đối chiếu đúng bảng kết quả dự kiến. Khi chủ động cho A/B chạy song song hoàn toàn, thứ tự thắng là biến quan sát, **không phải dữ kiện cố định**.

### Bước 4 — Ghi response thay vì đoán

Với `UPDATE` thường, ghi **thành công/timeout/lỗi** mà terminal thấy; không tự điền một cột `rowsAffected`. Với LWT, ghi chính xác `[applied]`:

| Lệnh | Ghi gì vào sổ lab? |
| --- | --- |
| UPDATE thường của A | Thành công hay exception, timestamp sử dụng |
| UPDATE thường của B | Thành công hay exception, timestamp sử dụng |
| CAS của A | `[applied] = true/false` hoặc timeout |
| CAS của B | `[applied] = true/false` hoặc timeout |
| SELECT sau | Giá trị đọc và consistency level |

Nếu một request timeout, **không hoàn thiện bảng dự kiến như thể request thành công**. Đánh dấu kết quả chưa biết và chuyển sang phần xử lý timeout ở mục 10.

### Bước 5 — Đọc lại từ cả hai phiên

Ví dụ với bài timestamp:

```sql
SELECT display_name,
       WRITETIME(display_name),
       contact_email,
       WRITETIME(contact_email),
       revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

`WRITETIME` đo write timestamp của **cell đang được quan sát** với đơn vị microsecond từ Unix epoch. Nó không chứng minh thứ tự phát request nếu timestamp được tự chọn, và cũng không cho biết ai là người ghi nếu bạn không lưu metadata nghiệp vụ riêng.

### Bước 6 — Đối chiếu trước/sau

| Phép thử | Kỳ vọng chính | Cần giải thích |
| --- | --- | --- |
| A | Sau A ghi trễ hơn, tên B vẫn thắng | Timestamp B cao hơn; không theo thứ tự gõ |
| B | Tên mới của A + email mới của B cùng tồn tại | Hai mutation tác động hai cell khác nhau |
| C | Email quay về giá trị cũ | B đã gửi email cũ với write timestamp mới hơn |
| D | A true, B false trong lịch A trước B | LWT chỉ áp dụng mutation có revision còn khớp |

### Bước 7 — Cố tình thay một biến trong lab

Thử một trong các biến sau **trên khóa lab mới**:

1. Đổi thứ tự gửi A/B nhưng giữ **write timestamp** của tình huống A: phiên bản có timestamp cao hơn vẫn thắng khi mọi mutation được nhìn thấy.
2. Bỏ cột `contact_email` khỏi `SET` của B ở tình huống C: email mới của A không còn bị B ghi ngược.
3. Thay `IF revision = 1` bằng `IF EXISTS` ở hai cập nhật tên: điều kiện tồn tại không tự ngăn hai client ghi nối tiếp vào cùng cell.
4. Thực hiện hai CAS thật sự đồng thời: **ai thắng có thể thay đổi**, nhưng khi cả hai nhận kết quả rõ ràng thì không quá một mutation từ cùng revision được áp dụng.

Không chạy lại timestamp thủ công trên **chính hàng CAS**. Không dùng `USING TIMESTAMP` cùng `IF`: CQL không cho phép kết hợp đó.

### Bước 8 — Viết kết luận từ bằng chứng

Một báo cáo lab đủ tốt phải chỉ ra:

- **Full primary key** nào bị tác động, hai phiên có thật sự dùng cùng khóa không?
- Dữ liệu nào được mỗi phiên đọc ở T0?
- Mỗi phiên chỉ ghi một field hay ghi lại cả object?
- Có write timestamp tự chọn hay không?
- Mutation thường hay LWT?
- Response là acknowledgment, `[applied]` hay timeout?
- Kết quả `SELECT` từ A và B giống nhau không, dưới consistency nào?
- Kết luận về **lost update**, **merge cell** hoặc **CAS conflict** dựa trên bằng chứng nào?

Không chỉ ghi “A thắng” hoặc “B thua” mà không nêu timestamp/điều kiện/khóa; mô tả đó không giải thích được tính đúng đắn khi thay đổi topology hoặc cách gửi request.

## 14. Những lỗi rất dễ gặp khi hai client cập nhật đồng thời

| Nhầm lẫn | Vì sao sai | Cách xử lý đúng |
| --- | --- | --- |
| “UPDATE gửi cuối luôn thắng” | Cassandra hòa giải theo write timestamp của cell | So sánh `WRITETIME` và nguồn timestamp |
| “Cả hai thành công nghĩa cả hai tên được giữ” | Hai giá trị cạnh tranh cùng một cell | Xác định phiên bản đang sống; dùng CAS nếu cần phát hiện xung đột |
| “Revision tự tăng mỗi lần UPDATE” | `revision` là regular column ứng dụng tự ghi | Tăng trong cùng CAS với điều kiện revision cũ |
| “SELECT trước rồi UPDATE thường là nguyên tử” | Client khác có thể ghi giữa hai request | `UPDATE ... IF revision = old` |
| “IF EXISTS là CAS theo tên cũ” | Chỉ kiểm tra sự tồn tại, không kiểm tra giá trị cũ | Dùng `IF revision = old` hoặc `IF col = expected` |
| “Hai field khác nhau luôn cần LWT” | Nếu mutation độc lập, hai cell có thể cùng được ghi | Chỉ dùng LWT khi cần invariant giữa field/hàng |
| “Ghi full object giống PATCH một field” | Gửi lại field cũ có thể che giá trị vừa được writer khác cập nhật | Chỉ viết những field thực sự thay đổi |
| “Bỏ field khỏi JSON tương đương NULL” | `NULL` xóa giá trị qua tombstone | Dùng bỏ cột/UNSET cho no-op |
| “QUORUM bảo đảm không mất cập nhật” | Quorum xác nhận replica, không kiểm tra revision | Dùng điều kiện nghiệp vụ với LWT |
| “applied=false là lỗi mạng” | Điều kiện không thỏa là kết quả bình thường của LWT | Tách conflict khỏi exception |
| “Timeout chứng minh mutation thất bại” | Cluster có thể đã áp dụng nhưng mất phản hồi | Đối chiếu request ID/trạng thái, retry có kiểm soát |
| “Retry CAS false chứng minh writer khác thắng” | Lần CAS trước của chính client có thể đã thành công | Định danh logical request và kiểm tra hiện trạng |
| “USING TIMESTAMP bảo vệ được CAS” | Timestamp tùy chỉnh không được dùng với LWT | Để LWT quản lý timestamp |
| “Hai cqlsh ở hai node là hai partition” | Partition do **partition key**, không do node client kết nối | Xác định full primary key và token mapping |
| “Ghi thành công nghĩa mọi replica đồng bộ” | Consistency level chỉ yêu cầu một tập xác nhận | Theo dõi replica/repair và đọc ở CL phù hợp |
| “DELETE cấm ghi lại khóa vĩnh viễn” | Ghi mới với timestamp thắng tombstone có thể xuất hiện | Dùng trạng thái/điều kiện nghiệp vụ để cấm tái tạo |
| “BATCH nhiều mutation thay CAS” | Logged batch không cho isolation read-modify-write kiểu SQL tổng quát | LWT cho điều kiện trên partition hỗ trợ; workflow khác cho nhiều partition |

## 15. Câu hỏi tự kiểm tra và checklist ứng dụng

### Câu hỏi

1. **Vì sao B thắng trong tình huống A dù A gửi sau?** Vì write timestamp của B lớn hơn timestamp của A trên cùng cell.
2. **`WRITETIME(display_name)` đo gì?** Write timestamp của cell `display_name` đang đọc, theo microsecond Unix epoch; không phải lịch sử toàn bộ request.
3. **Hai phiên sửa hai cột khác nhau có nhất thiết mất cập nhật không?** Không. Nếu mỗi mutation chỉ ghi cột tương ứng và thắng tại cell, cả hai thay đổi có thể cùng tồn tại.
4. **Vì sao B làm mất email mới của A trong tình huống C?** Vì B gửi lại email cũ trong mutation mới với timestamp cao hơn.
5. **`UPDATE` thường có kiểm tra row tồn tại và revision không?** Không, trừ khi dùng điều kiện `IF` tương ứng.
6. **`IF EXISTS` có ngăn hai người cùng đổi tên trên hàng đang tồn tại không?** Không; cả hai điều kiện tồn tại có thể đúng.
7. **`IF revision = 1` giải quyết điều gì?** Chỉ áp dụng mutation nếu revision hiện tại còn là 1 khi LWT xử lý; nếu đã đổi thì trả false.
8. **Tại sao phải tăng revision trong cùng mutation?** Nếu chỉ kiểm tra mà không tăng, writer sau vẫn có thể thỏa cùng điều kiện.
9. **Nếu A/B chạy CAS thực sự song song, có thể khẳng định A luôn thắng không?** Không. Kết quả phụ thuộc lịch đồng thuận; với hai request cạnh tranh cùng expected revision và cùng tăng revision, không quá một được áp dụng.
10. **`[applied] = false` có phải row count bằng 0 không?** Không. Nó cho biết điều kiện LWT không thỏa, không phải số hàng bị thay đổi.
11. **Đọc QUORUM và ghi QUORUM có tự tạo giao dịch SQL không?** Không; consistency của replica khác với điều kiện/transaction nghiệp vụ.
12. **Timeout sau CAS có nghĩa `[applied] = false` không?** Không. Có thể mutation đã áp dụng nhưng phản hồi thất lạc.
13. **Sau khi DELETE hàng, client khác còn được ghi cùng khóa không?** Có thể, nếu mutation mới thắng dấu xóa theo timestamp.
14. **Vì sao cần cả A và B đọc T0?** Để xác nhận hai writer thực sự bắt đầu từ cùng trạng thái và diễn giải đúng tranh chấp.
15. **Để kiểm tra xung đột trong Java dùng API nào?** `ResultSet.wasApplied()` đối với statement có `IF`; ngoại lệ/timeout phải xử lý riêng.

### Checklist trước khi đưa vào production

1. **Khóa và phạm vi:** mọi writer có dùng cùng full primary key cho cùng thực thể không?
2. **Ý nghĩa request:** upsert thông thường, PATCH từng field, thay toàn object, hay CAS theo revision?
3. **Đọc trước:** nếu cần so sánh trạng thái cũ, có đưa điều kiện vào chính mutation bằng `IF` không?
4. **Revision:** đã tăng cùng mutation, có bảo vệ toàn bộ đường ghi liên quan và xử lý overflow không?
5. **Timestamp:** có nguồn cấp thống nhất, tránh timestamp thủ công cũ/tương lai và lệch đồng hồ không?
6. **Replica consistency:** write/read CL, RF và topology phù hợp với điều cần quan sát không?
7. **LWT consistency:** đã chọn serial consistency phù hợp, không trộn CAS xuyên vùng tùy tiện không?
8. **Retry:** khi timeout có nhận diện logical request và trạng thái chưa xác định không?
9. **Kết quả:** ứng dụng có phân biệt ghi thường thành công, `[applied]` false và exception không?
10. **Payload:** cột vắng mặt có bị map nhầm thành `NULL` hay ghi lại dữ liệu cũ không?
11. **Test thực tế:** đã thử hai phiên cùng đọc T0, ghi T1/T2, đối chiếu T3 và lỗi mạng trong lab chưa?
12. **Observability:** có log an toàn về key logic, revision, request ID, latency và loại conflict mà không làm lộ dữ liệu riêng tư không?

**Ghi nhớ:** Muốn hiểu hai phiên cập nhật đồng thời trong Cassandra, hãy **ghi trạng thái trước**, xác định **full primary key và mutation từng phiên gửi**, phân biệt **write timestamp** với thời điểm gửi request, rồi **đọc trạng thái sau** dưới consistency đã biết. Cập nhật hai cell riêng có thể cùng tồn tại; ghi lại cả object cũ có thể gây mất cập nhật; hai mutation cùng cell cạnh tranh theo timestamp. Khi phải ngăn writer cũ ghi đè trạng thái mới, dùng **`IF revision = expected` và tăng revision trong cùng LWT**, kiểm tra `[applied]`, đồng thời xử lý timeout/idempotency riêng. Đó là nền tảng để ứng dụng Java dùng Cassandra phân tán đúng tính nhất quán và đúng nghiệp vụ.
