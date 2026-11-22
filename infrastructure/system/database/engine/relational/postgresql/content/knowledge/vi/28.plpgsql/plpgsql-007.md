# RAISE, mức thông báo, SQLSTATE và xử lý ngoại lệ trong PL/pgSQL

Khi viết logic bằng **PL/pgSQL** trong PostgreSQL, câu hỏi không chỉ là “làm thế nào để thực thi thành công một phép tính?”. Một hàm hoặc thủ tục còn phải trả lời: **khi dữ liệu không hợp lệ, ràng buộc bị vi phạm hoặc database gặp lỗi, hệ thống sẽ báo điều gì, bằng mức độ nào, ứng dụng nhận biết ra sao và các thay đổi nào được giữ lại?**

Ví dụ, một chức năng đặt hàng muốn trừ tồn kho. Nếu người dùng đặt 15 sản phẩm nhưng kho chỉ còn 8, việc âm thầm trả số 0 hoặc ghi thêm một dòng lỗi mơ hồ sẽ khiến phía Java khó phân biệt “hết hàng” với “database đang gặp sự cố”. Ngược lại, nếu lỗi xảy ra sau khi một số câu `UPDATE` đã chạy, ứng dụng còn phải biết các thay đổi đó có bị rollback hay không.

PostgreSQL cung cấp các công cụ chính:

- **`RAISE`**: phát thông báo ở những mức như `DEBUG`, `LOG`, `INFO`, `NOTICE`, `WARNING` và `EXCEPTION`.
- **SQLSTATE**: mã trạng thái SQL năm ký tự, giúp chương trình nhận biết loại lỗi mà không phụ thuộc câu chữ của thông báo.
- **`EXCEPTION WHEN ... THEN`**: chặn những loại lỗi cụ thể trong một khối PL/pgSQL, xử lý tình huống dự kiến hoặc phát lại lỗi.
- **`GET STACKED DIAGNOSTICS`**: lấy mã lỗi, thông điệp, chi tiết, gợi ý, constraint và ngữ cảnh của lỗi vừa bị chặn.
- **`RAISE;`**: phát lại lỗi gốc từ một exception handler mà không tự tạo lỗi mới mất mã và thông tin gốc.

Ví dụ ngắn:

```sql
DO $do$
BEGIN
    RAISE NOTICE 'Bắt đầu kiểm tra tồn kho';

    RAISE EXCEPTION USING
        ERRCODE = 'PZ001',
        MESSAGE = 'Số lượng đặt vượt tồn kho',
        DETAIL  = 'Yêu cầu 15, hiện có 8',
        HINT    = 'Giảm số lượng hoặc chờ nhập hàng';
END;
$do$;
```

Thông báo `NOTICE` nhằm cung cấp thông tin cho người gọi hoặc phiên làm việc. `EXCEPTION` là lỗi thực sự: nếu không có handler phù hợp, statement thất bại và transaction bị ảnh hưởng theo quy tắc PostgreSQL.

**Quan trọng:** `RAISE WARNING` không tự rollback giao dịch. Một thông báo ở cấp `WARNING` là một thông điệp, không phải lỗi ném ra để bắt bằng `EXCEPTION WHEN`. Để từ chối một thao tác vì vi phạm nghiệp vụ, thông thường dùng `RAISE EXCEPTION` hoặc để constraint của database phát sinh lỗi.

Bài học này thuộc module **Database Engine Relational PostgreSQL**, chương **PL/pgSQL**, tập trung chi tiết vào cách phát thông báo, thiết kế SQLSTATE, nhận và phát lại ngoại lệ, phạm vi rollback, xử lý lỗi trong batch, kết nối Java/JDBC và những mẫu thiết kế an toàn cho ứng dụng.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Viết câu `RAISE` trong `DO` block, function, trigger function và procedure PL/pgSQL.
2. Phân biệt sáu mức `DEBUG`, `LOG`, `INFO`, `NOTICE`, `WARNING` và `EXCEPTION`.
3. Giải thích vai trò của `client_min_messages`, `log_min_messages` và các trường hợp xử lý đặc biệt đối với một số mức thông báo.
4. Dùng placeholders `%`, `%%` trong format literal của `RAISE`.
5. Dùng `RAISE ... USING MESSAGE, DETAIL, HINT, ERRCODE` và các trường thông tin đối tượng liên quan.
6. Hiểu cấu trúc mã **SQLSTATE năm ký tự**, phân biệt mã lớp lỗi và mã điều kiện cụ thể.
7. Nhận diện các mã thông dụng: `23505`, `23503`, `23514`, `23502`, `22012`, `22023`, `40001`, `40P01`, `57014` và `P0001`.
8. Tạo mã nghiệp vụ riêng mà không gây nhầm với lỗi hệ thống.
9. Viết `BEGIN ... EXCEPTION WHEN ... THEN ... END` và nhận biết phạm vi rollback tự động của block.
10. Dùng handler theo tên điều kiện và theo `SQLSTATE`.
11. Hiểu giới hạn của `WHEN OTHERS`, nhất là `query_canceled` và `assert_failure`.
12. Đọc `SQLSTATE`, `SQLERRM` và `GET STACKED DIAGNOSTICS` trong exception handler.
13. Phát lại lỗi gốc bằng `RAISE;`, giữ nguyên SQLSTATE và context.
14. Hiểu vì sao exception handler không phải transaction độc lập và không tự `COMMIT` những ghi chép lỗi.
15. Phân biệt điều kiện nghiệp vụ dự kiến với lỗi hạ tầng phải báo ra ứng dụng.
16. Thiết kế thao tác tồn kho tránh race condition và không sử dụng exception để thay thế mọi điều kiện `WHERE`.
17. Xử lý từng dòng của batch bằng block ngoại lệ con trong những trường hợp phù hợp, đồng thời hiểu chi phí subtransaction.
18. Biết cách xử lý retry cho deadlock/serialization failure ở **ranh giới transaction**.
19. Đọc mã SQLSTATE từ `SQLException.getSQLState()` trong Java, không phân loại lỗi dựa trên văn bản đã dịch.
20. Kiểm thử một cách có hệ thống các đường lỗi: thành công, input NULL, vi phạm constraint, hết dữ liệu, retryable error và lỗi không được nuốt.

**Phạm vi:** PostgreSQL hiện đại với `LANGUAGE plpgsql`. Những ví dụ DDL và DML trong bài chỉ dùng trên database lab được phép thay đổi. Cài đặt hệ thống logging, quyền của role và hành vi driver có thể thay đổi theo phiên bản và cấu hình triển khai.

---

## 2. Ngoại lệ trong PL/pgSQL là gì?

Một **ngoại lệ** (*exception*) là sự kiện báo lỗi làm luồng thực thi thông thường bị gián đoạn.

Ví dụ có thể phát sinh lỗi:

- `INSERT` vi phạm `UNIQUE`.
- `UPDATE` vi phạm `CHECK`.
- `SELECT INTO STRICT` không có hàng hoặc có quá một hàng.
- Chia cho 0.
- Cast dữ liệu sai kiểu.
- Deadlock hoặc serialization failure.
- Lỗi được chủ động phát bằng `RAISE EXCEPTION`.
- Một thao tác SQL trong function/trigger không thành công.

Một block PL/pgSQL có `EXCEPTION` có thể chặn lỗi thích hợp:

```sql
DO $do$
BEGIN
    BEGIN
        RAISE EXCEPTION 'Ví dụ phát lỗi';
    EXCEPTION
        WHEN raise_exception THEN
            RAISE NOTICE 'Đã chặn lỗi được tạo bởi RAISE';
    END;
END;
$do$;
```

Ở đây:

1. `RAISE EXCEPTION` phát lỗi với mã mặc định dành cho RAISE EXCEPTION khi không chỉ định code.
2. Handler `WHEN raise_exception` nhận lỗi tương ứng.
3. Handler phát một `NOTICE` và kết thúc bình thường.
4. Block bên ngoài tiếp tục sau block con.

Điều này không có nghĩa mọi lỗi nên bị chặn. Bắt và bỏ qua một lỗi nghiêm trọng có thể làm ứng dụng nhận “thành công” trong khi nghiệp vụ đã thất bại.

### 2.1. Thông báo khác ngoại lệ

`RAISE NOTICE` hoặc `RAISE WARNING` không buộc luồng xử lý chuyển vào `EXCEPTION WHEN`. Chúng dùng để truyền thông tin/chẩn đoán.

`RAISE EXCEPTION` là cách chủ động tạo lỗi.

### 2.2. SQLSTATE khác thông điệp

Thông điệp `'Số lượng không hợp lệ'` dành cho con người đọc. Mã `PZ002` có thể dành cho chương trình phân nhánh xử lý.

**Không nên viết ứng dụng Java bằng cách so chuỗi thông báo tiếng Việt**, vì người viết có thể sửa câu chữ hoặc bản dịch trong khi bản chất lỗi vẫn giữ nguyên.

### 2.3. Ngoại lệ không phải kết quả trả về thông thường

Một function trả `INTEGER` có thể trả 0 để diễn đạt một kết quả nghiệp vụ được định nghĩa rõ. Nhưng nếu function không thể thực hiện đúng contract vì đầu vào thiếu hoặc constraint hỏng, một ngoại lệ với SQLSTATE phù hợp có thể thể hiện tình huống tốt hơn.

Không có quy tắc “mọi thất bại phải throw”: phải phân biệt **kết quả dự kiến có thể biểu diễn bằng dữ liệu** với **lỗi phá vỡ hợp đồng gọi**.

---

## 3. Cú pháp cơ bản của RAISE

Các dạng thường dùng:

```sql
RAISE [level] 'format' [, expression [, ...]]
    [USING option = expression [, ...]];

RAISE [level] condition_name
    [USING option = expression [, ...]];

RAISE [level] SQLSTATE 'sqlstate'
    [USING option = expression [, ...]];

RAISE [level] USING option = expression [, ...];

RAISE;
```

Trong đó:

- `level` là mức thông báo; nếu không chỉ định thì mặc định **EXCEPTION**.
- `'format'` là chuỗi literal có thể chứa ký hiệu `%` làm placeholder.
- `condition_name` là tên điều kiện lỗi được PostgreSQL nhận diện.
- `SQLSTATE 'xxxxx'` chỉ định mã lỗi.
- `USING` bổ sung message/detail/hint/mã lỗi hoặc metadata.
- `RAISE;` không có tham số là cú pháp **phát lại ngoại lệ đang được xử lý**, chỉ có ý nghĩa trong exception handler phù hợp.

### 3.1. RAISE NOTICE đơn giản

```sql
DO $do$
BEGIN
    RAISE NOTICE 'Đang thực hiện tác vụ...';
END;
$do$;
```

### 3.2. RAISE WARNING

```sql
DO $do$
BEGIN
    RAISE WARNING 'Dữ liệu được nạp thiếu trường tùy chọn';
    RAISE NOTICE 'Tác vụ vẫn tiếp tục';
END;
$do$;
```

`WARNING` báo vấn đề đáng chú ý nhưng bản thân nó không ném ngoại lệ làm dừng block.

### 3.3. RAISE EXCEPTION

```sql
DO $do$
BEGIN
    RAISE EXCEPTION 'Yêu cầu không hợp lệ';
END;
$do$;
```

Câu này thất bại nếu không có handler thích hợp ở phạm vi bao quanh.

### 3.4. Bỏ mức đồng nghĩa với EXCEPTION

```sql
RAISE 'Yêu cầu không hợp lệ';
```

là dạng ngắn của việc phát lỗi ở mức EXCEPTION. Trong code nhóm, viết tường minh `RAISE EXCEPTION` thường dễ đọc hơn.

---

## 4. Sáu mức thông báo

PostgreSQL dùng các mức sau khi gọi `RAISE` trong PL/pgSQL:

| Mức | Vai trò chính | Có tự làm statement thất bại? | Cách sử dụng |
| --- | --- | --- | --- |
| `DEBUG` | Thông tin debug chi tiết | Không | Theo dõi nhánh xử lý khi cần |
| `LOG` | Thông tin hướng về logging | Không | Sự kiện cần log theo chính sách |
| `INFO` | Thông tin vận hành | Không | Trình bày trạng thái một bước |
| `NOTICE` | Ghi chú về hành vi đáng biết | Không | Thông báo quá trình thực thi |
| `WARNING` | Cảnh báo có vấn đề nhưng tiếp tục | Không | Dữ liệu có vấn đề không gây thất bại |
| `EXCEPTION` | Lỗi thực sự | **Có**, trừ khi bắt hợp lệ | Vi phạm contract/điều kiện từ chối |

### 4.1. DEBUG

```sql
DO $do$
DECLARE
    v_attempt INTEGER := 2;
BEGIN
    RAISE DEBUG 'Lần xử lý hiện tại: %', v_attempt;
END;
$do$;
```

Thông điệp DEBUG có thể không xuất hiện ở client do mức lọc cấu hình. Không vì vậy mà kết luận câu `RAISE DEBUG` không được chạy.

### 4.2. LOG

```sql
DO $do$
BEGIN
    RAISE LOG 'Đã bắt đầu công việc tổng hợp theo kỳ';
END;
$do$;
```

`LOG` có cách phân loại đặc biệt khi so mức client/server. Không dựa vào việc một công cụ SQL có hiển thị LOG hay không để kết luận server log đã được cấu hình như mong muốn.

### 4.3. INFO

```sql
DO $do$
BEGIN
    RAISE INFO 'Đã đọc xong dữ liệu đầu vào';
END;
$do$;
```

Đối với thông báo phía client, PostgreSQL xử lý `INFO` theo quy tắc đặc biệt: thông báo INFO được gửi tới client bất kể giá trị `client_min_messages`. Vì vậy INFO không hoàn toàn giống các cấp được lọc theo ngưỡng thông thường.

### 4.4. NOTICE

```sql
DO $do$
BEGIN
    RAISE NOTICE 'Đã bỏ qua bản ghi trùng theo chính sách';
END;
$do$;
```

NOTICE phù hợp để cung cấp thông tin hữu ích cho người thao tác trong psql, migrations hoặc các tác vụ vận hành. Không nên phát hàng triệu NOTICE trong một truy vấn OLTP nóng.

### 4.5. WARNING

```sql
DO $do$
BEGIN
    RAISE WARNING 'Đang sử dụng tham số cấu hình dự phòng';
END;
$do$;
```

Nếu fallback vẫn hợp lệ, WARNING có thể hợp lý. Nếu thiếu cấu hình khiến phép tính không thể đúng, phải cân nhắc EXCEPTION thay vì tiếp tục với giá trị bịa ra.

### 4.6. EXCEPTION

```sql
DO $do$
DECLARE
    v_quantity INTEGER := -2;
BEGIN
    IF v_quantity <= 0 THEN
        RAISE EXCEPTION 'Số lượng phải lớn hơn 0';
    END IF;
END;
$do$;
```

Một EXCEPTION chưa được xử lý có thể khiến transaction đang mở chuyển sang trạng thái thất bại, phải ROLLBACK trước khi tiếp tục các lệnh khác.

---

## 5. client_min_messages và log_min_messages

Không phải mọi `RAISE NOTICE` hay `RAISE DEBUG` đều hiện ở mọi client hoặc trong mọi server log. PostgreSQL có các cơ chế lọc thông điệp.

### 5.1. client_min_messages

Cấu hình này quyết định mức thông điệp gửi đến client với các quy tắc độ ưu tiên tương ứng.

Xem giá trị:

```sql
SHOW client_min_messages;
```

Thử ở mức WARNING trong một transaction lab:

```sql
BEGIN;

SET LOCAL client_min_messages = warning;

DO $do$
BEGIN
    RAISE DEBUG   'DEBUG demo';
    RAISE NOTICE  'NOTICE demo';
    RAISE WARNING 'WARNING demo';
    RAISE INFO    'INFO demo';
END;
$do$;

ROLLBACK;
```

Thông thường NOTICE và DEBUG có thể bị lọc ở mức WARNING; WARNING vẫn đủ mức. INFO có ngoại lệ hiển thị phía client như đã mô tả.

**Lưu ý:** những thông điệp nào được thấy cụ thể còn phụ thuộc driver, cách công cụ SQL hiển thị, cấu hình và phiên bản.

### 5.2. log_min_messages

Cấu hình này liên quan đến mức thông điệp được ghi vào server log:

```sql
SHOW log_min_messages;
```

Tùy quyền và cấu hình, không phải người dùng thông thường có thể thay giá trị hệ thống này.

### 5.3. Không hiểu hai cấu hình là một

- `client_min_messages`: mức gửi về session/client.
- `log_min_messages`: mức ghi vào server log.
- `log_min_error_statement` và `log_error_verbosity` còn ảnh hưởng ghi statement/thông tin lỗi theo cấu hình.

Một `NOTICE` có thể thấy trong psql nhưng không thấy trong server log, hoặc ngược lại, tùy thiết lập.

### 5.4. INFO và LOG có xử lý đặc biệt

Thứ tự ưu tiên của INFO/LOG giữa client và server không hoàn toàn đơn giản như một danh sách số từ nhỏ tới lớn; PostgreSQL có các quy tắc riêng. Khi cần chính sách logging chắc chắn, phải kiểm tra tài liệu cấu hình của **phiên bản đang chạy** và thử với công cụ thu log thực tế.

### 5.5. Lọc thông báo không thay tính đúng

Nếu NOTICE bị ẩn, function vẫn phải đúng. Không dùng việc “client có thấy NOTICE” làm điều kiện điều khiển nghiệp vụ.

### 5.6. Không dùng RAISE như hệ thống audit duy nhất

Server log có thể bị rotate, lọc, chuyển vùng hoặc không phải nơi lưu dữ liệu audit theo cam kết nghiệp vụ. Nếu bắt buộc lưu audit có cấu trúc, cần thiết kế bảng/event stream/logging pipeline theo yêu cầu độ bền và giao dịch.

---

## 6. Placeholder trong RAISE

PL/pgSQL dùng dấu `%` trong format literal của `RAISE` để chèn biểu thức.

```sql
DO $do$
DECLARE
    v_sku TEXT := 'SKU-100';
    v_requested INTEGER := 12;
    v_available INTEGER := 8;
BEGIN
    RAISE NOTICE
        'SKU %, yêu cầu %, còn lại %',
        v_sku,
        v_requested,
        v_available;
END;
$do$;
```

Thông điệp có dạng:

```text
NOTICE: SKU SKU-100, yêu cầu 12, còn lại 8
```

### 6.1. Mỗi % cần một biểu thức

```sql
RAISE NOTICE 'Đơn % có trạng thái %', v_order_id, v_status;
```

có hai placeholders và hai biểu thức.

Số lượng placeholders không khớp số biểu thức có thể được PL/pgSQL phát hiện khi compile/validate function.

### 6.2. %% để in dấu phần trăm

```sql
DO $do$
DECLARE
    v_percent INTEGER := 75;
BEGIN
    RAISE NOTICE 'Tiến độ %%%', v_percent;
END;
$do$;
```

Chuỗi `%%%` ở đây gồm một `%` placeholder và một `%%` biểu diễn dấu phần trăm literal; ví dụ có thể hiển thị “75%”.

### 6.3. Format phải là literal trong dạng RAISE format

Không xem cú pháp sau là cách hợp lệ để dùng một format expression động trong vị trí literal của `RAISE`:

```sql
-- Không dùng như cú pháp RAISE format:
-- RAISE NOTICE format('SKU %s', v_sku);
```

Muốn tạo message động, dùng:

```sql
RAISE NOTICE USING
    MESSAGE = format('SKU %s', v_sku);
```

### 6.4. RAISE format và format() khác cách định dạng

- Trong `RAISE '...%', x`, placeholder đơn giản là `%`.
- Trong hàm SQL `format('...%s...', x)` có hệ ký hiệu riêng như `%s`, `%I`, `%L`.

Không trộn cú pháp hai cơ chế rồi kỳ vọng định dạng giống nhau.

### 6.5. Cẩn thận với thông điệp chứa dữ liệu nhạy cảm

Đừng log password, token, API key, thông tin thẻ thanh toán hay dữ liệu cá nhân không cần thiết vào RAISE. Thông điệp có thể xuất hiện ở client, server log hoặc hệ thống giám sát với phạm vi truy cập khác nhau.

---

## 7. USING: MESSAGE, DETAIL và HINT

Cách phát lỗi có cấu trúc:

```sql
DO $do$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = 'PZ001',
        MESSAGE = 'Không thể thực hiện yêu cầu',
        DETAIL  = 'Số lượng đặt vượt số lượng tồn kho',
        HINT    = 'Giảm số lượng hoặc thử lại sau khi nhập hàng';
END;
$do$;
```

Các trường:

| Trường | Vai trò |
| --- | --- |
| `MESSAGE` | Thông điệp lỗi chính, ngắn gọn |
| `DETAIL` | Bối cảnh cụ thể giúp chẩn đoán |
| `HINT` | Hướng dẫn xử lý có thể thực hiện |
| `ERRCODE` | Mã SQLSTATE năm ký tự hoặc tên điều kiện phù hợp |
| `SCHEMA` | Metadata tên schema liên quan khi có |
| `TABLE` | Metadata tên bảng liên quan khi có |
| `COLUMN` | Metadata tên cột liên quan khi có |
| `CONSTRAINT` | Metadata tên constraint liên quan khi có |
| `DATATYPE` | Metadata tên kiểu dữ liệu liên quan khi có |

### 7.1. MESSAGE không phải mã lỗi

Ứng dụng có thể hiển thị một thông điệp thân thiện khác với thông điệp từ database; SQLSTATE là kênh ổn định hơn cho phân loại lỗi.

### 7.2. DETAIL giúp debug, nhưng tránh rò rỉ dữ liệu

Ví dụ:

```sql
DETAIL = format(
    'sku=%s, requested=%s, available=%s',
    v_sku, v_requested, v_available
)
```

hữu ích khi các giá trị không nhạy cảm và người gọi có quyền xem.

Không đưa toàn bộ row, mật khẩu, thông tin xác thực hoặc dữ liệu của tenant khác vào DETAIL chỉ vì “dễ debug”.

### 7.3. HINT có tính hướng dẫn

```sql
HINT = 'Kiểm tra SKU và thử lại'
```

nên giúp người vận hành hoặc ứng dụng biết bước tiếp theo; không dùng HINT để cung cấp thông tin bí mật như tên server nội bộ cho client không tin cậy.

### 7.4. Có thể trộn format và USING

```sql
DO $do$
DECLARE
    v_sku TEXT := 'SKU-100';
BEGIN
    RAISE EXCEPTION 'SKU % không được phép đặt', v_sku
        USING
            ERRCODE = 'PZ002',
            HINT = 'Kiểm tra trạng thái sản phẩm';
END;
$do$;
```

### 7.5. Mã SQLSTATE không cần nằm trong câu MESSAGE

Không viết client parser kiểu “nếu message bắt đầu bằng [PZ002] thì...”. Đọc trường SQLSTATE mà PostgreSQL/driver trả riêng.

---

## 8. SQLSTATE là gì?

**SQLSTATE** là mã trạng thái SQL gồm **năm ký tự** dùng để phân loại điều kiện thành công, cảnh báo và lỗi.

Ví dụ:

```text
23505
  ||---
  ||  condition: unique_violation
  |
  +-- class 23: integrity_constraint_violation
```

Hai ký tự đầu là **class**; ba ký tự còn lại giúp xác định điều kiện cụ thể trong class đó.

### 8.1. Một số mã cần nhận biết

| SQLSTATE | Tên điều kiện PostgreSQL | Khi nào thường gặp |
| --- | --- | --- |
| `00000` | successful_completion | Thành công |
| `22012` | division_by_zero | Chia cho 0 |
| `22023` | invalid_parameter_value | Tham số không hợp lệ |
| `23502` | not_null_violation | Vi phạm NOT NULL |
| `23503` | foreign_key_violation | Vi phạm FOREIGN KEY |
| `23505` | unique_violation | Vi phạm UNIQUE/PRIMARY KEY |
| `23514` | check_violation | Vi phạm CHECK |
| `40001` | serialization_failure | Giao dịch thất bại do serialization |
| `40P01` | deadlock_detected | Phát hiện deadlock |
| `55P03` | lock_not_available | Lock không sẵn có theo cơ chế yêu cầu |
| `57014` | query_canceled | Query bị hủy |
| `P0001` | raise_exception | Lỗi RAISE EXCEPTION mặc định |
| `P0002` | no_data_found | Không có hàng trong ngữ cảnh STRICT phù hợp |
| `P0003` | too_many_rows | Quá nhiều hàng trong ngữ cảnh STRICT phù hợp |
| `P0004` | assert_failure | ASSERT thất bại |

Các mã này hữu ích hơn việc phụ thuộc câu chữ của message, nhất là với ứng dụng đa ngôn ngữ.

### 8.2. SQLSTATE không phải HTTP status

`23505` không phải HTTP 409, `PZ001` không phải HTTP 400. API cần định nghĩa cách ánh xạ lỗi SQLSTATE sang HTTP status/response theo nghiệp vụ.

Ví dụ một mã “hết hàng” có thể được ánh xạ sang HTTP 409 Conflict ở một hệ thống, nhưng không phải quy tắc tự động của PostgreSQL.

### 8.3. Đừng chỉ bắt theo class khi cần chính xác

Class 23 có nhiều lỗi toàn vẹn: NOT NULL, FOREIGN KEY, UNIQUE, CHECK. Nếu chỉ bắt cả class rồi thông báo “SKU đã tồn tại”, bạn có thể che một lỗi FK hoặc CHECK khác.

Nên dùng condition cụ thể hoặc chẩn đoán constraint khi cần quyết định logic.

### 8.4. SQLSTATE có tính ổn định hơn message

Message có thể thay đổi do phiên bản, cấu hình ngôn ngữ hoặc ngữ cảnh. PostgreSQL khuyến khích chương trình dùng SQLSTATE và các trường metadata để xác định loại lỗi thay vì so văn bản lỗi.

---

## 9. Tự định nghĩa SQLSTATE nghiệp vụ

Bạn có thể phát một SQLSTATE riêng:

```sql
RAISE EXCEPTION USING
    ERRCODE = 'PZ001',
    MESSAGE = 'Thiếu SKU';
```

Đây là ví dụ mã tự đặt cho ứng dụng. Khi dùng mã riêng, cần có bảng mã lỗi tài liệu hóa.

### 9.1. Quy tắc chọn mã

- Gồm **đúng 5 ký tự**.
- Dùng ký tự số và chữ cái ASCII in hoa theo quy tắc PostgreSQL cho SQLSTATE.
- Không dùng `00000` (mã thành công) làm lỗi.
- Nên tránh mã tận cùng bằng ba số 0 để tránh nhầm với class code.
- Tránh chiếm các mã chuẩn PostgreSQL cho ý nghĩa không liên quan.
- Có ownership và quy tắc versioning cho mã tự đặt.

Ví dụ mã nội bộ có thể quy ước class `PZ`:

| Mã ví dụ | Ý nghĩa nghiệp vụ |
| --- | --- |
| `PZ001` | SKU không hợp lệ |
| `PZ002` | Số lượng không hợp lệ |
| `PZ003` | Không tìm thấy sản phẩm |
| `PZ004` | Không đủ tồn kho |
| `PZ005` | Không thể áp dụng dòng nhập liệu |
| `PZ006` | Thao tác nghiệp vụ bị từ chối |

Các mã trên là **quy ước của bài học**, không phải mã chuẩn PostgreSQL.

### 9.2. Khi nào dùng mã chuẩn?

Nếu lỗi thực sự là vi phạm constraint tự nhiên, hãy để database trả `23505`, `23503`, `23514` khi thích hợp, thay vì luôn chuyển thành một mã tùy biến khó tra cứu.

### 9.3. Khi nào dùng mã riêng?

Khi nghiệp vụ cần phân biệt một tình huống không có mã chuẩn đủ rõ, chẳng hạn “tồn kho đã hết”, một SQLSTATE riêng cùng MESSAGE/DETAIL/HINT có thể giúp ứng dụng xử lý nhất quán.

### 9.4. Không tạo quá nhiều mã theo message

Nếu mỗi biến thể câu chữ tạo một SQLSTATE mới, hệ thống sẽ có hàng trăm mã khó bảo trì. Mỗi mã nên đại diện **một loại lỗi cần xử lý khác nhau** ở phía consumer.

---

## 10. RAISE EXCEPTION mặc định và P0001

Nếu không khai báo mã bằng condition name/SQLSTATE/ERRCODE, lệnh:

```sql
DO $do$
BEGIN
    RAISE EXCEPTION 'Ví dụ lỗi nghiệp vụ';
END;
$do$;
```

phát lỗi với SQLSTATE **`P0001`** (`raise_exception`).

### 10.1. P0001 không phân biệt nguyên nhân

Nếu mọi function đều viết:

```sql
RAISE EXCEPTION 'Không tìm thấy sản phẩm';
RAISE EXCEPTION 'Không đủ tồn kho';
RAISE EXCEPTION 'SKU trùng';
```

thì tất cả các tình huống chủ động phát trên mặc định cùng SQLSTATE P0001. Ứng dụng khó phân loại mà không parse message.

### 10.2. Cách rõ nghĩa hơn

```sql
RAISE EXCEPTION USING
    ERRCODE = 'PZ004',
    MESSAGE = 'Không đủ tồn kho';
```

Client có thể phân loại dựa vào PZ004.

### 10.3. Không lạm dụng P0001 cho mọi lỗi

Nếu lỗi là `unique_violation` do database thực sự ném, nên cân nhắc giữ nguyên mã 23505 và các trường constraint. Nếu chủ động phát lỗi mang ngữ nghĩa application, dùng mã đã quy ước.

### 10.4. Mã P0001 vẫn có chỗ dùng

Đối với script vận hành hoặc ví dụ ngắn chỉ cần từ chối thao tác không có yêu cầu client phân loại chi tiết, RAISE EXCEPTION mặc định có thể đủ. Nhưng production API thường cần contract rõ hơn.

---

## 11. Phát lỗi theo condition name và SQLSTATE

Có thể sử dụng tên điều kiện được PostgreSQL nhận diện:

```sql
DO $do$
BEGIN
    RAISE division_by_zero
        USING MESSAGE = 'Không thể thực hiện phép chia này';
END;
$do$;
```

Hoặc mã trực tiếp:

```sql
DO $do$
BEGIN
    RAISE SQLSTATE '22012'
        USING MESSAGE = 'Mẫu số không được bằng 0';
END;
$do$;
```

Hai ví dụ chủ động tạo lỗi có mã `22012` nhưng điều đó **không có nghĩa câu SQL đã thật sự thực hiện phép chia**. Khi log và thống kê lỗi, phân biệt lỗi từ engine với lỗi do code chủ động phát.

### 11.1. Phát mã tùy chỉnh qua SQLSTATE

```sql
DO $do$
BEGIN
    RAISE SQLSTATE 'PZ002'
        USING MESSAGE = 'Số lượng yêu cầu không hợp lệ';
END;
$do$;
```

### 11.2. Phát qua ERRCODE

```sql
DO $do$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = 'PZ002',
        MESSAGE = 'Số lượng yêu cầu không hợp lệ';
END;
$do$;
```

Các cú pháp trên là những cách khác nhau để kiểm soát mã lỗi.

### 11.3. Không giả mạo unique_violation theo thói quen

Nếu một kiểm tra thủ công `IF exists(...)` gặp dữ liệu trùng, chủ động phát mã 23505 có thể khiến client nghĩ lỗi đến từ unique constraint cụ thể, trong khi logic có race condition. Hãy dùng unique constraint thật cho invariant dữ liệu và xử lý mã do database phát, hoặc dùng mã nghiệp vụ riêng khi bản chất khác.

---

## 12. Bộ lab: sản phẩm, tồn kho và lịch sử thay đổi

Bài tập chính sẽ sử dụng một bảng sản phẩm và bảng ghi biến động tồn kho. Nhờ đó chúng ta có thể kiểm tra:

- Thông báo không gây rollback.
- Lỗi nghiệp vụ từ function.
- Lỗi UNIQUE, CHECK và FOREIGN KEY từ database.
- Rollback trong block EXCEPTION.
- Chẩn đoán constraint bằng GET STACKED DIAGNOSTICS.
- Xử lý từng dòng của một batch.
- Gọi từ Java theo SQLSTATE.

> **Cảnh báo:** Câu `DROP SCHEMA ... CASCADE` sau đây xóa toàn bộ đối tượng trong schema thực hành cùng tên. Chỉ chạy trong database lab có thể reset. Không chạy trên production.

### 12.1. Tạo schema

```sql
DROP SCHEMA IF EXISTS plpgsql_errors_lab CASCADE;

CREATE SCHEMA plpgsql_errors_lab;
```

### 12.2. Bảng sản phẩm

```sql
CREATE TABLE plpgsql_errors_lab.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0
        CONSTRAINT products_stock_nonnegative CHECK (stock >= 0),
    price NUMERIC(12,2) NOT NULL
        CONSTRAINT products_price_nonnegative CHECK (price >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

Chúng ta đặt tên tường minh cho hai CHECK constraints để dễ đọc chẩn đoán. UNIQUE trên `sku` được PostgreSQL đặt tên ràng buộc theo quy tắc mặc định nếu không chỉ định tên riêng.

### 12.3. Bảng lịch sử tồn kho

```sql
CREATE TABLE plpgsql_errors_lab.stock_movements (
    movement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES plpgsql_errors_lab.products(product_id),
    delta INTEGER NOT NULL
        CONSTRAINT stock_movements_delta_nonzero
        CHECK (delta <> 0),
    reason TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

Ý nghĩa:

- `delta > 0`: tăng tồn kho.
- `delta < 0`: giảm tồn kho.
- `reason`: lý do của nghiệp vụ.
- Foreign key bảo đảm bản ghi biến động gắn với sản phẩm có thật.

### 12.4. Dữ liệu đầu vào

```sql
INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES
    ('SKU-100', 'Bàn phím',  8,  450000.00),
    ('SKU-200', 'Chuột',    20,  180000.00),
    ('SKU-300', 'Màn hình',  3, 2500000.00);
```

Kiểm tra:

```sql
SELECT product_id, sku, stock, price
FROM plpgsql_errors_lab.products
ORDER BY product_id;
```

### 12.5. Lab chủ ý có constraints thực

Trong một hệ thống thật, kiểm tra input trong PL/pgSQL rất hữu ích để báo message thân thiện. Nhưng **constraint ở bảng** mới là tuyến bảo vệ cuối cùng khi người gọi bỏ qua function và ghi trực tiếp.

---

## 13. Hàm kiểm tra input bằng RAISE EXCEPTION

Viết hàm xác thực SKU và quantity.

```sql
CREATE FUNCTION plpgsql_errors_lab.validate_reservation(
    p_sku TEXT,
    p_quantity INTEGER
)
RETURNS VOID
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF p_sku IS NULL OR BTRIM(p_sku) = '' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'PZ001',
            MESSAGE = 'SKU không được để trống',
            HINT = 'Truyền mã SKU đã được xác nhận';
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = 'PZ002',
            MESSAGE = 'Số lượng phải lớn hơn 0',
            DETAIL = format(
                'quantity=%s',
                COALESCE(p_quantity::TEXT, '<NULL>')
            ),
            HINT = 'Chọn một số nguyên dương';
    END IF;
END;
$fn$;
```

### 13.1. Gọi hợp lệ

```sql
SELECT plpgsql_errors_lab.validate_reservation(
    'SKU-100', 2
);
```

Function trả `VOID`, không có giá trị nghiệp vụ cần sử dụng.

### 13.2. Gọi thiếu SKU

```sql
SELECT plpgsql_errors_lab.validate_reservation(
    NULL::TEXT, 2
);
```

Kết quả là lỗi SQLSTATE `PZ001`.

### 13.3. Gọi quantity không hợp lệ

```sql
SELECT plpgsql_errors_lab.validate_reservation(
    'SKU-100', 0
);
```

Kết quả là lỗi SQLSTATE `PZ002`.

### 13.4. Tại sao không chỉ dùng RAISE WARNING?

Số lượng bằng 0 là không hợp lệ theo hợp đồng đặt hàng. Nếu chỉ WARNING rồi function vẫn tiếp tục, có nguy cơ tạo một giao dịch vô nghĩa hoặc ghi dữ liệu sai.

### 13.5. CHECK constraint vẫn cần

Nếu một API khác thực hiện trực tiếp:

```sql
UPDATE plpgsql_errors_lab.products
SET stock = -5
WHERE sku = 'SKU-100';
```

CHECK trên bảng sẽ từ chối. Function validation **không thể thay CHECK** khi dữ liệu có nhiều đường ghi.

---

## 14. Hàm đặt hàng: trừ tồn kho nguyên tử và phát lỗi có mã

Một mẫu đơn giản nhưng đúng về cạnh tranh khi giảm tồn kho là dùng một `UPDATE` điều kiện:

```sql
UPDATE products
SET stock = stock - requested
WHERE sku = requested_sku
  AND stock >= requested
RETURNING product_id;
```

Không dùng mô hình dễ race:

```text
SELECT stock
IF stock >= quantity
    UPDATE stock = old_stock - quantity
```

nếu không có khóa/transaction discipline phù hợp, vì hai session có thể cùng đọc một tồn kho cũ.

### 14.1. Hàm reserve_stock

```sql
CREATE FUNCTION plpgsql_errors_lab.reserve_stock(
    p_sku TEXT,
    p_quantity INTEGER
)
RETURNS BIGINT
LANGUAGE plpgsql
VOLATILE
AS $fn$
DECLARE
    v_product_id BIGINT;
    v_available INTEGER;
    v_movement_id BIGINT;
BEGIN
    PERFORM plpgsql_errors_lab.validate_reservation(
        p_sku, p_quantity
    );

    UPDATE plpgsql_errors_lab.products AS p
    SET
        stock = p.stock - p_quantity,
        updated_at = clock_timestamp()
    WHERE p.sku = p_sku
      AND p.stock >= p_quantity
    RETURNING p.product_id
      INTO v_product_id;

    IF NOT FOUND THEN
        SELECT p.stock
          INTO v_available
        FROM plpgsql_errors_lab.products AS p
        WHERE p.sku = p_sku;

        IF NOT FOUND THEN
            RAISE EXCEPTION USING
                ERRCODE = 'PZ003',
                MESSAGE = 'Không tìm thấy SKU',
                DETAIL = format('sku=%s', p_sku),
                HINT = 'Kiểm tra mã sản phẩm';
        END IF;

        RAISE EXCEPTION USING
            ERRCODE = 'PZ004',
            MESSAGE = 'Không đủ tồn kho để đặt',
            DETAIL = format(
                'sku=%s, requested=%s, available_at_check=%s',
                p_sku, p_quantity, v_available
            ),
            HINT = 'Giảm số lượng hoặc chờ nhập thêm';
    END IF;

    INSERT INTO plpgsql_errors_lab.stock_movements (
        product_id, delta, reason
    )
    VALUES (
        v_product_id,
        -p_quantity,
        'RESERVATION'
    )
    RETURNING movement_id INTO v_movement_id;

    RETURN v_movement_id;
END;
$fn$;
```

### 14.2. Tại sao VOLATILE?

Function thực hiện `UPDATE` và `INSERT`, có side effects. Nó không thể được khai báo trung thực là STABLE hoặc IMMUTABLE.

### 14.3. Tại sao UPDATE có điều kiện?

PostgreSQL kiểm tra điều kiện cập nhật khi thao tác thực thi theo quy tắc concurrency của mức cô lập đang dùng. Với mẫu trừ tồn kho bằng một UPDATE và điều kiện `stock >= p_quantity`, hai request đồng thời không thể đơn giản cùng dùng cùng tồn kho cũ để trừ vượt điều kiện mà không có cơ chế khóa xử lý.

Cần vẫn kiểm thử ở isolation level và workload thực tế; mẫu này không tự giải quyết mọi vấn đề của một hệ thống quản lý kho phân tán.

### 14.4. Tại sao SELECT bổ sung sau khi UPDATE thất bại?

Dùng để phân biệt:

- Không tồn tại SKU → `PZ003`.
- Có SKU nhưng không đủ hàng tại lúc kiểm tra → `PZ004`.

**Giới hạn:** trong concurrency, dữ liệu có thể thay đổi giữa UPDATE thất bại và SELECT chẩn đoán. Vì vậy `available_at_check` là thông tin tại lần đọc chẩn đoán, **không phải snapshot bảo đảm tại thời điểm UPDATE**. Tình huống cạnh tranh nên được caller xử lý bằng retry thích hợp nếu business contract cho phép.

### 14.5. Vì sao log biến động trong cùng transaction?

Khi giảm stock và ghi stock_movements đều nằm trong một function được gọi bởi cùng transaction, nếu INSERT movement bị lỗi không được chặn, toàn statement/transaction chịu rollback theo quy tắc PostgreSQL. Không nên giảm tồn kho thành công rồi bỏ qua lỗi ghi lịch sử.

### 14.6. Function không tự commit

Function chạy trong transaction của caller. Dù nó `RETURN movement_id`, ứng dụng phải xem transaction đã COMMIT thành công trước khi thông báo đặt hàng hoàn tất.

---

## 15. Thử đường thành công và đường lỗi

### 15.1. Đặt hai sản phẩm trong transaction rồi rollback để giữ lab

```sql
BEGIN;

SELECT plpgsql_errors_lab.reserve_stock(
    'SKU-100', 2
) AS movement_id;

SELECT sku, stock
FROM plpgsql_errors_lab.products
WHERE sku = 'SKU-100';

SELECT *
FROM plpgsql_errors_lab.stock_movements
ORDER BY movement_id DESC
LIMIT 5;

ROLLBACK;
```

Trong transaction, stock của SKU-100 sẽ từ 8 còn 6. Sau `ROLLBACK`, thay đổi đó không được commit.

### 15.2. Đặt quá số lượng

Chạy riêng:

```sql
SELECT plpgsql_errors_lab.reserve_stock(
    'SKU-100', 999
);
```

Kết quả là lỗi nghiệp vụ `PZ004`, với DETAIL chứa số lượng theo lần kiểm tra.

### 15.3. SKU không tồn tại

```sql
SELECT plpgsql_errors_lab.reserve_stock(
    'SKU-NOT-FOUND', 1
);
```

Dự kiến mã `PZ003`.

### 15.4. Đầu vào không hợp lệ

```sql
SELECT plpgsql_errors_lab.reserve_stock(
    'SKU-100', -1
);
```

Dự kiến mã `PZ002`.

### 15.5. Lỗi được phát ở đâu?

- `PZ001` và `PZ002` đến từ validation.
- `PZ003` và `PZ004` đến từ nhánh xử lý nghiệp vụ sau UPDATE.
- `23505`, `23514` và `23503` có thể đến trực tiếp từ constraints, không cần function tự giả lập.

---

## 16. EXCEPTION WHEN: cú pháp bắt ngoại lệ

Một block PL/pgSQL có thể có phần ngoại lệ:

```sql
BEGIN
    -- Các câu lệnh có thể phát lỗi.
EXCEPTION
    WHEN condition_name THEN
        -- Xử lý lỗi được nhận diện.
    WHEN SQLSTATE 'xxxxx' THEN
        -- Xử lý theo mã lỗi.
    WHEN OTHERS THEN
        -- Xử lý các lỗi còn lại trong phạm vi mà OTHERS bắt.
END;
```

Ví dụ:

```sql
DO $do$
BEGIN
    BEGIN
        PERFORM plpgsql_errors_lab.reserve_stock(
            'SKU-100', 999
        );

        RAISE NOTICE 'Đặt hàng thành công';
    EXCEPTION
        WHEN SQLSTATE 'PZ004' THEN
            RAISE NOTICE 'Không đủ tồn kho; có thể mời chọn lại';
    END;
END;
$do$;
```

Vì `PZ004` là mã tùy chỉnh, dùng `WHEN SQLSTATE 'PZ004'`.

### 16.1. Handler bắt lỗi trong block nào?

Handler bắt các lỗi nảy sinh trong **phần lệnh trước EXCEPTION của chính block đó**, hoặc lỗi được truyền từ các function được gọi trong phần đó.

### 16.2. Handler đầu tiên phù hợp được chạy

Nếu nhiều nhánh có thể bao trùm cùng một lỗi, cần đặt nhánh xử lý cụ thể trước nhánh chung.

### 16.3. Không bắt mọi lỗi chỉ để tiếp tục

Một lỗi `23505` có thể do SKU trùng, nhưng cũng có thể do một unique constraint không liên quan. Chỉ khi biết chính xác loại lỗi và cách khôi phục an toàn mới nên bắt để tiếp tục.

### 16.4. Lỗi trong handler không do cùng handler bắt lại

Nếu code bên trong một nhánh `WHEN ... THEN` phát lỗi mới, phần `EXCEPTION` của chính block không tự chạy lần nữa để bắt lỗi đó. Cần block ngoài hoặc để lỗi truyền tới caller.

---

## 17. Bắt lỗi theo tên điều kiện

PostgreSQL có nhiều condition names dễ đọc:

```sql
DO $do$
BEGIN
    BEGIN
        INSERT INTO plpgsql_errors_lab.products (
            sku, display_name, stock, price
        )
        VALUES ('SKU-100', 'Trùng SKU', 1, 1000);
    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'Sản phẩm có SKU đã tồn tại';
    END;
END;
$do$;
```

### 17.1. Các tên phổ biến

| Condition name | SQLSTATE | Nghĩa |
| --- | --- | --- |
| `unique_violation` | 23505 | Trùng khóa unique/PK |
| `foreign_key_violation` | 23503 | Vi phạm khóa ngoại |
| `not_null_violation` | 23502 | Trường NOT NULL bị NULL |
| `check_violation` | 23514 | CHECK trả FALSE |
| `division_by_zero` | 22012 | Chia cho 0 |
| `invalid_parameter_value` | 22023 | Tham số không hợp lệ |
| `serialization_failure` | 40001 | Transaction không thể serialize |
| `deadlock_detected` | 40P01 | Deadlock |
| `raise_exception` | P0001 | RAISE EXCEPTION mặc định |
| `no_data_found` | P0002 | Không có hàng ở ngữ cảnh STRICT |
| `too_many_rows` | P0003 | Nhiều hàng ở ngữ cảnh STRICT |

### 17.2. Tên điều kiện tăng khả năng đọc code

```sql
WHEN unique_violation THEN ...
```

thường rõ nghĩa hơn:

```sql
WHEN SQLSTATE '23505' THEN ...
```

nhưng mã SQLSTATE vẫn hữu ích cho custom codes và giao diện giữa database với driver.

### 17.3. Có thể bắt theo lớp

Một tên điều kiện của class (ví dụ nhóm lỗi toàn vẹn dữ liệu) có thể bao phủ nhiều lỗi con. Không nên bắt cả class nếu ứng dụng phải phân biệt UNIQUE với FK hoặc NOT NULL.

---

## 18. Lỗi UNIQUE, CHECK và FOREIGN KEY

Ràng buộc bảng là nguồn phát lỗi rất quan trọng.

### 18.1. UNIQUE — 23505

```sql
INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES ('SKU-100', 'Một SKU trùng', 1, 1000);
```

Vì `sku` có UNIQUE constraint, statement có thể thất bại với `23505`.

### 18.2. CHECK — 23514

```sql
INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES ('SKU-NEG-STOCK', 'Kho âm', -1, 1000);
```

Vi phạm `products_stock_nonnegative`, mã `23514`.

### 18.3. FOREIGN KEY — 23503

```sql
INSERT INTO plpgsql_errors_lab.stock_movements (
    product_id, delta, reason
)
VALUES (999999999, -1, 'UNKNOWN_PRODUCT');
```

Nếu không có product_id tương ứng, mã `23503`.

### 18.4. NOT NULL — 23502

```sql
INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES (NULL, 'Thiếu mã', 2, 1000);
```

Mã `23502`.

### 18.5. Trường constraint giúp phân loại chính xác

Cùng mã `23505` có thể đến từ unique trên `sku` hoặc một unique key khác. `GET STACKED DIAGNOSTICS ... CONSTRAINT_NAME` có thể giúp handler biết constraint nào thực sự vi phạm.

Không dựa chỉ vào thông điệp kiểu `duplicate key value violates unique constraint ...` rồi parse tên trong câu text.

---

## 19. GET STACKED DIAGNOSTICS: lấy chi tiết lỗi vừa bắt

Trong exception handler, PostgreSQL cung cấp:

```sql
GET STACKED DIAGNOSTICS
    variable_1 = diagnostic_item_1,
    variable_2 = diagnostic_item_2,
    ...;
```

Các mục thông dụng:

| Diagnostic item | Ý nghĩa |
| --- | --- |
| `RETURNED_SQLSTATE` | Mã SQLSTATE của lỗi |
| `MESSAGE_TEXT` | Thông điệp lỗi chính |
| `PG_EXCEPTION_DETAIL` | DETAIL của lỗi |
| `PG_EXCEPTION_HINT` | HINT của lỗi |
| `PG_EXCEPTION_CONTEXT` | Ngữ cảnh thực thi nơi lỗi phát sinh |
| `SCHEMA_NAME` | Schema liên quan nếu có |
| `TABLE_NAME` | Bảng liên quan nếu có |
| `COLUMN_NAME` | Cột liên quan nếu có |
| `CONSTRAINT_NAME` | Constraint liên quan nếu có |
| `PG_DATATYPE_NAME` | Kiểu dữ liệu liên quan nếu có |

### 19.1. Ví dụ lấy SQLSTATE và constraint

```sql
DO $do$
DECLARE
    v_state TEXT;
    v_message TEXT;
    v_constraint TEXT;
BEGIN
    BEGIN
        INSERT INTO plpgsql_errors_lab.products (
            sku, display_name, stock, price
        )
        VALUES ('SKU-100', 'Trùng SKU demo', 1, 1000);
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_constraint = CONSTRAINT_NAME;

        RAISE NOTICE
            'state=%, constraint=%, message=%',
            v_state, v_constraint, v_message;
    END;
END;
$do$;
```

### 19.2. Metadata có thể không hiện diện

Không phải mọi lỗi đều có TABLE_NAME/COLUMN_NAME/CONSTRAINT_NAME. Không giả định mỗi error có đầy đủ mọi trường và không dùng metadata vắng mặt như một bằng chứng SQLSTATE sai.

### 19.3. GET STACKED DIAGNOSTICS chỉ dùng với lỗi đã được bắt

Nó dựa trên thông tin ngoại lệ hiện tại trong handler. Không dùng như lệnh truy vấn “lỗi cuối của session” ở bất kỳ vị trí nào ngoài phạm vi xử lý ngoại lệ.

### 19.4. Lấy tất cả khi cần chẩn đoán, không nhất thiết trả tất cả cho client

`PG_EXCEPTION_CONTEXT` có thể chứa tên function, vị trí và ngữ cảnh thực thi. Hữu ích trong log vận hành được kiểm soát, nhưng đôi khi không nên trả nguyên văn trong HTTP response công khai.

---

## 20. SQLSTATE và SQLERRM trong exception handler

Trong phần handler, PL/pgSQL có sẵn hai biến đặc biệt:

- `SQLSTATE`: mã lỗi.
- `SQLERRM`: thông điệp lỗi.

Ví dụ:

```sql
DO $do$
BEGIN
    BEGIN
        PERFORM 10 / 0;
    EXCEPTION
        WHEN division_by_zero THEN
            RAISE NOTICE
                'Bắt được state=% và message=%',
                SQLSTATE, SQLERRM;
    END;
END;
$do$;
```

### 20.1. Khi nào đủ dùng?

Nếu handler chỉ cần phân loại và log ngắn:

```sql
RAISE NOTICE 'SQLSTATE=%', SQLSTATE;
```

có thể đủ.

### 20.2. Khi nào cần GET STACKED DIAGNOSTICS?

Khi cần constraint, DETAIL, HINT hoặc context gốc, dùng `GET STACKED DIAGNOSTICS`.

### 20.3. SQLERRM không thay SQLSTATE

Câu chữ có thể thay đổi; driver và application nên dựa trên mã. Đừng viết:

```text
IF SQLERRM contains 'duplicate key' THEN ...
```

để phân loại ràng buộc unique.

### 20.4. Biến SQLSTATE không phải biến SQL toàn cục

`SQLSTATE`/`SQLERRM` ở đây là các biến PL/pgSQL có ý nghĩa trong exception handler. Không giả định mọi session SQL bên ngoài function luôn có một biến `SQLSTATE` đọc được bằng `SELECT SQLSTATE`.

---

## 21. RAISE; phát lại lỗi gốc

Một handler có thể cần ghi log/thu thập context rồi **không tự quyết định cách phục hồi**. Khi đó nên phát lại lỗi:

```sql
DO $do$
DECLARE
    v_state TEXT;
    v_message TEXT;
BEGIN
    BEGIN
        PERFORM 1 / 0;
    EXCEPTION
        WHEN division_by_zero THEN
            GET STACKED DIAGNOSTICS
                v_state = RETURNED_SQLSTATE,
                v_message = MESSAGE_TEXT;

            RAISE WARNING
                'Phép tính thất bại: state=%, message=%',
                v_state, v_message;

            RAISE;
    END;
END;
$do$;
```

`RAISE;` phát lại lỗi được bắt, giúp caller nhận đúng SQLSTATE và thông tin lỗi gốc.

### 21.1. Không thay bằng RAISE EXCEPTION SQLERRM

Mẫu sau thường **làm mất mã gốc**:

```sql
-- Không phải cách rethrow bảo toàn thông tin:
-- RAISE EXCEPTION '%', SQLERRM;
```

Vì câu RAISE EXCEPTION mới có thể mặc định `P0001` và tạo context khác, nó không còn là cùng lỗi gốc.

### 21.2. Khi nào chuyển đổi lỗi có chủ đích?

Nếu database là một boundary và bạn muốn chuyển một lỗi nội bộ thành mã nghiệp vụ an toàn, có thể tạo lỗi mới **có chủ đích**:

```sql
RAISE EXCEPTION USING
    ERRCODE = 'PZ006',
    MESSAGE = 'Yêu cầu không thể hoàn thành',
    HINT = 'Vui lòng kiểm tra dữ liệu đầu vào';
```

Nhưng nên giữ lỗi gốc trong log/chẩn đoán bảo mật phù hợp và tránh che mất lỗi hạ tầng cần retry.

### 21.3. RAISE; chỉ có ý nghĩa trong handler

Không gọi `RAISE;` ở một phần PL/pgSQL bất kỳ để tạo lỗi mặc định. Nó cần một ngoại lệ đang được xử lý trong ngữ cảnh handler.

---

## 22. EXCEPTION block là một subtransaction

Đây là phần quan trọng nhất về tính nhất quán dữ liệu.

Khi một block PL/pgSQL có `EXCEPTION` bắt lỗi, PostgreSQL xử lý các thay đổi database trong phần thân block theo cơ chế **subtransaction**. Nếu lỗi xảy ra và được bắt, những thay đổi **persistent database state bên trong phần thân block đó** được rollback đến điểm bắt đầu block.

Nhưng:

- Các biến PL/pgSQL vẫn giữ giá trị tại thời điểm xảy ra lỗi.
- Những thay đổi database trước khi vào block con vẫn giữ trong transaction ngoài.
- Các thay đổi được thực hiện **trong handler** sau rollback block con có thể được giữ nếu transaction ngoài cuối cùng COMMIT.
- Nếu transaction ngoài ROLLBACK, các thay đổi handler vào bảng logged thông thường cũng rollback.
- Thông điệp đã gửi ra client/server log không được “rút lại” theo rollback dữ liệu.
- Sequence values, side effects ngoài database hoặc tác động hệ thống khác có thể có semantics không transaction như DML; không dùng exception rollback để giả định mọi tác động đều đảo ngược.

### 22.1. Ví dụ có thể chạy

```sql
BEGIN;

INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES (
    'SKU-OUTER',
    'Tạo ở transaction ngoài',
    1,
    1000
);

DO $do$
DECLARE
    v_stage TEXT := 'chưa xử lý';
BEGIN
    BEGIN
        INSERT INTO plpgsql_errors_lab.products (
            sku, display_name, stock, price
        )
        VALUES (
            'SKU-INNER',
            'Tạo trong block con',
            1,
            1000
        );

        v_stage := 'đã INSERT SKU-INNER';

        RAISE EXCEPTION 'Giả lập lỗi ở block con';

    EXCEPTION
        WHEN raise_exception THEN
            RAISE NOTICE
                'Handler thấy v_stage=%', v_stage;
    END;
END;
$do$;

SELECT sku
FROM plpgsql_errors_lab.products
WHERE sku IN ('SKU-OUTER','SKU-INNER')
ORDER BY sku;

ROLLBACK;
```

### 22.2. Dự đoán trạng thái trong transaction

Trước lệnh ROLLBACK cuối cùng:

- `SKU-OUTER` tồn tại trong transaction vì được INSERT **trước block con**.
- `SKU-INNER` **không còn**, vì INSERT trong block con đã rollback khi ngoại lệ phát sinh.
- `v_stage` ở handler vẫn là `'đã INSERT SKU-INNER'`, vì biến PL/pgSQL không tự phục hồi như table data.

Sau ROLLBACK, cả thay đổi thêm ở transaction ngoài cũng không được commit.

### 22.3. Vì sao biến và bảng khác nhau?

PL/pgSQL variables thuộc bộ nhớ thực thi function/block. Các thay đổi bảng nằm dưới transaction/subtransaction engine. Khi lỗi được bắt, cơ chế rollback database state không đồng nghĩa restore mọi biến của chương trình về giá trị cũ.

### 22.4. Không “nuốt lỗi” rồi tin UPDATE trước đó đã được giữ

Nếu UPDATE nằm **trong cùng block có EXCEPTION** và block đó ném lỗi, UPDATE sẽ rollback, dù biến đếm đã tăng. Khi viết batch processing, phải đặt phép tăng số thành công **sau** những thao tác có thể lỗi hoặc điều chỉnh biến thích hợp.

---

## 23. Phạm vi block quyết định dữ liệu rollback

So sánh hai cấu trúc.

### 23.1. Block EXCEPTION bao quanh toàn bộ công việc

```sql
BEGIN
    UPDATE ...;  -- A
    INSERT ...;  -- B có thể lỗi
EXCEPTION WHEN OTHERS THEN
    -- A và B trong phần thân block cùng bị rollback
END;
```

Nếu B lỗi, thay đổi A trong block cũng rollback.

### 23.2. Chỉ bọc một bước có thể thất bại

```sql
BEGIN
    UPDATE ...;  -- A trong block ngoài

    BEGIN
        INSERT ...;  -- B trong block con
    EXCEPTION WHEN unique_violation THEN
        -- Chỉ database changes trong block con bị rollback.
    END;
END;
```

Nếu B lỗi và được bắt trong block con, A trong phần thân block ngoài có thể còn được giữ, tùy transaction ngoài.

### 23.3. Quy tắc thiết kế

Đặt ranh giới exception block theo **đơn vị công việc được phép rollback**. Đừng bọc toàn bộ function vào OTHERS chỉ vì muốn ghi log, nếu điều đó làm mất khả năng phân biệt lỗi và phạm vi subtransaction.

### 23.4. Không có COMMIT độc lập trong handler

Một handler không thể tự biến INSERT error_log thành một transaction đã commit độc lập với caller. Nếu caller rollback sau đó, error_log bình thường cũng rollback.

Nếu yêu cầu audit lỗi **dù transaction nghiệp vụ rollback**, cần cơ chế logging ngoài transaction hoặc kiến trúc phù hợp, không chỉ một bảng INSERT trong handler.

---

## 24. Nested EXCEPTION: lỗi trong handler sẽ đi đâu?

Xét:

```sql
DO $do$
BEGIN
    BEGIN
        BEGIN
            RAISE EXCEPTION USING
                ERRCODE = 'PZ001',
                MESSAGE = 'Lỗi ban đầu';
        EXCEPTION WHEN SQLSTATE 'PZ001' THEN
            RAISE EXCEPTION USING
                ERRCODE = 'PZ002',
                MESSAGE = 'Lỗi mới từ handler';
        END;

    EXCEPTION WHEN SQLSTATE 'PZ002' THEN
        RAISE NOTICE 'Block ngoài nhận PZ002';
    END;
END;
$do$;
```

Handler của block bên trong không tự bắt lại lỗi PZ002 mà chính nó phát. Lỗi được chuyển tới block bao quanh, nơi có handler PZ002.

### 24.1. Khi nào dùng nested handler?

- Một đơn vị công việc nhỏ có lỗi có thể bỏ qua.
- Handler bên trong muốn chuyển loại lỗi một cách có chủ đích.
- Block ngoài xử lý chính sách retry/abort khác.
- Một batch xử lý nhiều hàng nhưng toàn batch vẫn có thể bị lỗi hệ thống.

### 24.2. Đừng tạo quá nhiều tầng

Nhiều tầng handler lồng nhau khiến rollback scope và đường lỗi khó hiểu. Khi cần nhiều bước rõ ràng, cân nhắc tách function, đổi mô hình kết quả hoặc đưa retry lên tầng transaction của ứng dụng.

---

## 25. WHEN OTHERS: có ích nhưng nguy hiểm

Một handler:

```sql
EXCEPTION WHEN OTHERS THEN
    ...
```

bắt nhiều loại lỗi mà các nhánh cụ thể chưa xử lý.

### 25.1. OTHERS không bao gồm mọi lỗi tuyệt đối

Trong PostgreSQL, `OTHERS` **không bắt** `query_canceled` và `assert_failure` theo cơ chế thông thường; muốn xử lý hai loại này, phải chỉ định bằng tên điều kiện thích hợp.

Đừng viết tài liệu “WHEN OTHERS bắt mọi lỗi không ngoại lệ”.

### 25.2. Mẫu nguy hiểm: nuốt lỗi

```sql
-- Phản ví dụ: KHÔNG DÙNG CHO NGHIỆP VỤ QUAN TRỌNG.
--
-- EXCEPTION WHEN OTHERS THEN
--     RAISE NOTICE 'Có lỗi nhưng tiếp tục';
--     RETURN TRUE;
```

Nếu INSERT vi phạm unique, deadlock hoặc SQL sai, function có thể báo TRUE dù không hoàn tất công việc.

### 25.3. Mẫu log rồi phát lại

```sql
DO $do$
DECLARE
    v_state TEXT;
    v_message TEXT;
BEGIN
    BEGIN
        PERFORM 1 / 0;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT;

        RAISE WARNING
            'Unhandled error state=%, message=%',
            v_state, v_message;

        RAISE;
    END;
END;
$do$;
```

Đây là mẫu an toàn hơn trong những tình huống cần thêm context nhưng không có chính sách hồi phục hợp lệ.

### 25.4. Khi nào có thể nuốt lỗi?

Chỉ khi đó là **một chính sách nghiệp vụ được xác định rõ**, ví dụ một dòng import sai độc lập có thể bị bỏ qua và được ghi vào danh sách rejected rows, trong khi các dòng hợp lệ vẫn xử lý.

Cần ghi rõ:

- Những mã lỗi được phép bỏ qua.
- Những thay đổi nào rollback.
- Logging có bền hay không.
- Cách báo số dòng thất bại.
- Trường hợp nào phải dừng toàn batch.

### 25.5. Không bắt deadlock/serialization rồi trả thành công

Các mã `40P01`/`40001` thường cần retry transaction với dữ liệu/logic nhất quán tại boundary phù hợp. Nếu chỉ bắt rồi trả 0, application có thể xem giao dịch chưa thực hiện là đã hoàn tất.

---

## 26. Bắt UNIQUE phải xác định đúng constraint

Một function có thể thực hiện nhiều INSERT/UPDATE với nhiều unique constraints. Handler:

```sql
EXCEPTION WHEN unique_violation THEN
    -- "SKU trùng" ?
```

chưa đủ chứng minh lỗi do `products.sku`.

### 26.1. Dùng CONSTRAINT_NAME

```sql
DO $do$
DECLARE
    v_constraint TEXT;
BEGIN
    BEGIN
        INSERT INTO plpgsql_errors_lab.products (
            sku, display_name, stock, price
        )
        VALUES ('SKU-100', 'Trùng SKU', 1, 1000);

    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_constraint = CONSTRAINT_NAME;

        IF v_constraint = 'products_sku_key' THEN
            RAISE NOTICE 'SKU đã tồn tại';
        ELSE
            RAISE;
        END IF;
    END;
END;
$do$;
```

Với schema lab đã tạo, UNIQUE constraint trên sku thường có tên mặc định `products_sku_key`. Nếu DDL đặt tên khác hoặc schema thay đổi, cần sử dụng tên ràng buộc đúng đã kiểm tra.

### 26.2. Mặc định nên đặt tên constraint rõ ràng

Ở production, tên tường minh ổn định giúp chẩn đoán và mapping. Không phụ thuộc vào việc PostgreSQL tự đặt tên theo một quy ước rồi quên ghi vào contract/migration.

### 26.3. Đừng xem mọi UNIQUE là lỗi cần retry

Unique trên idempotency key có thể nghĩa là request đã xử lý trước đó; unique trên SKU có thể nghĩa dữ liệu nhập trùng; unique trên transaction ID có thể báo một lỗi logic khác. SQLSTATE chỉ xác định loại constraint, còn policy tùy nghiệp vụ.

### 26.4. ON CONFLICT có thể tốt hơn exception

Với insert-if-absent là tình huống bình thường, cân nhắc:

```sql
INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES ('SKU-100', 'Bàn phím', 8, 450000)
ON CONFLICT (sku) DO NOTHING;
```

Ví dụ này sẽ không ghi đè sản phẩm đang có. Khi mục tiêu là hành vi idempotent và không cần báo lỗi, `ON CONFLICT` thường rõ và ít overhead hơn sử dụng unique_violation handler cho từng hàng.

---

## 27. SELECT INTO STRICT và hai ngoại lệ P0002/P0003

PL/pgSQL cho phép:

```sql
SELECT ...
INTO STRICT variable
FROM ...
WHERE ...;
```

`STRICT` đòi truy vấn trả **đúng một hàng**.

### 27.1. Không có hàng: no_data_found

```sql
DO $do$
DECLARE
    v_product_id BIGINT;
BEGIN
    BEGIN
        SELECT product_id
          INTO STRICT v_product_id
        FROM plpgsql_errors_lab.products
        WHERE sku = 'SKU-UNKNOWN';

    EXCEPTION WHEN no_data_found THEN
        RAISE NOTICE 'Không tìm thấy sản phẩm';
    END;
END;
$do$;
```

Lỗi có mã `P0002`.

### 27.2. Nhiều hàng: too_many_rows

```sql
DO $do$
DECLARE
    v_product_id BIGINT;
BEGIN
    BEGIN
        SELECT product_id
          INTO STRICT v_product_id
        FROM plpgsql_errors_lab.products
        WHERE stock >= 0;

    EXCEPTION WHEN too_many_rows THEN
        RAISE NOTICE 'Truy vấn trả nhiều hơn một sản phẩm';
    END;
END;
$do$;
```

Lab có nhiều sản phẩm nên lỗi mã `P0003`.

### 27.3. Không dùng STRICT khi 0 hàng là kết quả bình thường

Nếu thiếu row là một nhánh nghiệp vụ dự kiến, có thể dùng `SELECT INTO` không STRICT và `FOUND`.

```sql
DO $do$
DECLARE
    v_product_id BIGINT;
BEGIN
    SELECT product_id
      INTO v_product_id
    FROM plpgsql_errors_lab.products
    WHERE sku = 'SKU-UNKNOWN';

    IF NOT FOUND THEN
        RAISE NOTICE 'Không có SKU này';
    END IF;
END;
$do$;
```

### 27.4. Không STRICT có thể lấy một hàng tùy ý

Nếu SELECT trả nhiều hàng mà không có STRICT, PL/pgSQL có thể chọn hàng đầu theo cách truy vấn được thực thi. Không xem đó là “bản ghi đầu tiên” đáng tin cậy nếu không xác định ORDER BY và LIMIT phù hợp.

---

## 28. FOUND và ROW_COUNT không phải cơ chế bắt lỗi

Có nhiều tình huống **không có hàng phù hợp** nhưng không cần EXCEPTION.

### 28.1. FOUND

Sau một số SQL statements trong PL/pgSQL, biến đặc biệt `FOUND` cho biết thao tác có tìm/ảnh hưởng hàng theo quy tắc tương ứng.

Ví dụ:

```sql
DO $do$
BEGIN
    UPDATE plpgsql_errors_lab.products
    SET updated_at = updated_at
    WHERE sku = 'SKU-UNKNOWN';

    IF NOT FOUND THEN
        RAISE NOTICE 'Không có hàng để cập nhật';
    END IF;
END;
$do$;
```

### 28.2. GET DIAGNOSTICS ROW_COUNT

```sql
DO $do$
DECLARE
    v_affected BIGINT;
BEGIN
    UPDATE plpgsql_errors_lab.products
    SET updated_at = updated_at
    WHERE sku IN ('SKU-100','SKU-200');

    GET DIAGNOSTICS v_affected = ROW_COUNT;

    RAISE NOTICE 'Số hàng bị ảnh hưởng: %', v_affected;
END;
$do$;
```

`ROW_COUNT` ở đây là số hàng do câu SQL gần nhất ảnh hưởng theo cách PostgreSQL định nghĩa.

### 28.3. GET DIAGNOSTICS khác GET STACKED DIAGNOSTICS

- `GET DIAGNOSTICS ... ROW_COUNT`: thông tin về thao tác trong luồng thực thi bình thường.
- `GET STACKED DIAGNOSTICS ... RETURNED_SQLSTATE`: thông tin của lỗi đang được xử lý trong exception handler.

Không hoán đổi hai câu lệnh.

### 28.4. Đừng dùng exception cho mọi “0 rows updated”

Một UPDATE với điều kiện không khớp không mặc định là lỗi PostgreSQL. Nếu nghiệp vụ yêu cầu phải cập nhật một hàng, kiểm tra `FOUND` hoặc `ROW_COUNT` rồi chủ động RAISE với mã nghiệp vụ phù hợp.

---

## 29. Exception block có overhead

PostgreSQL documentation lưu ý rằng **đi vào và thoát một block PL/pgSQL có EXCEPTION tốn tài nguyên hơn block không có handler**, bởi cơ chế subtransaction.

Điều này đặc biệt đáng chú ý trong vòng lặp xử lý hàng triệu bản ghi.

### 29.1. Mẫu nhiều ngoại lệ nhỏ

```sql
FOR r IN SELECT ... LOOP
    BEGIN
        INSERT INTO ...;
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;
END LOOP;
```

Nếu phần lớn hàng trùng, rất nhiều lần vào exception path có thể khiến batch tốn CPU và WAL/transaction metadata.

### 29.2. Thay bằng SQL set-based khi phù hợp

```sql
INSERT INTO target_table (...)
SELECT ...
FROM staging_table
ON CONFLICT (unique_key)
DO NOTHING;
```

Một statement set-based và `ON CONFLICT` có thể phù hợp hơn cho trường hợp trùng được dự kiến.

### 29.3. Khi exception per row hợp lý

- Dữ liệu import độc lập từng dòng.
- Chỉ một số rất ít dòng lỗi.
- Mỗi lỗi cần được ghi riêng có cấu trúc.
- Các dòng tốt được phép tiếp tục.
- Tác động của từng dòng có thể rollback độc lập trong cùng transaction ngoài.

### 29.4. Không có benchmark chung

Chi phí phụ thuộc số hàng, tỷ lệ lỗi, index, constraints, disk, phiên bản PostgreSQL và transaction length. Không khẳng định handler per row luôn chậm hơn một tỷ lệ cố định.

---

## 30. Xử lý batch: chuẩn bị bảng yêu cầu và bảng lỗi

Ta tạo một batch nhỏ để minh họa cách mỗi dòng được xử lý độc lập, trong khi caller vẫn kiểm soát transaction ngoài.

### 30.1. Bảng request

```sql
CREATE TABLE plpgsql_errors_lab.stock_requests (
    request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    sku TEXT,
    quantity INTEGER,
    processed BOOLEAN NOT NULL DEFAULT FALSE
);
```

### 30.2. Bảng rejection

```sql
CREATE TABLE plpgsql_errors_lab.rejected_requests (
    rejection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    request_id BIGINT NOT NULL,
    error_state TEXT NOT NULL,
    error_message TEXT NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

Đây là bảng log nghiệp vụ **trong transaction database**. Nếu caller rollback transaction ngoài, các rows trong rejected_requests cũng rollback.

### 30.3. Dữ liệu mẫu

```sql
INSERT INTO plpgsql_errors_lab.stock_requests (
    batch_id, sku, quantity
)
VALUES
    (1, 'SKU-100', 1),
    (1, 'SKU-200', 3),
    (1, 'SKU-300', 999),
    (1, 'SKU-UNKNOWN', 1),
    (1, 'SKU-200', 0);
```

Trong batch:

- Hai request đầu hợp lệ.
- Một request thiếu tồn kho.
- Một request SKU không tồn tại.
- Một request quantity bằng 0.

### 30.4. Yêu cầu nghiệp vụ

- Cố xử lý từng request.
- Nếu request thành công: đánh dấu processed.
- Nếu lỗi nghiệp vụ PZ001–PZ004: rollback thay đổi của request lỗi, ghi rejection và tiếp tục.
- Nếu lỗi hệ thống khác: không tự nuốt; phát lại cho caller.
- Kết quả trả số thành công và thất bại.
- Caller quyết định COMMIT hoặc ROLLBACK cả batch.

---

## 31. Hàm xử lý batch với exception per item

```sql
CREATE FUNCTION plpgsql_errors_lab.process_stock_batch(
    p_batch_id INTEGER
)
RETURNS TABLE (
    processed_count INTEGER,
    rejected_count INTEGER
)
LANGUAGE plpgsql
VOLATILE
AS $fn$
DECLARE
    v_request RECORD;
    v_processed INTEGER := 0;
    v_rejected INTEGER := 0;
    v_state TEXT;
    v_message TEXT;
BEGIN
    FOR v_request IN
        SELECT
            r.request_id,
            r.sku,
            r.quantity
        FROM plpgsql_errors_lab.stock_requests AS r
        WHERE r.batch_id = p_batch_id
          AND NOT r.processed
        ORDER BY r.request_id
    LOOP
        BEGIN
            PERFORM plpgsql_errors_lab.reserve_stock(
                v_request.sku,
                v_request.quantity
            );

            UPDATE plpgsql_errors_lab.stock_requests
            SET processed = TRUE
            WHERE request_id = v_request.request_id;

            v_processed := v_processed + 1;

        EXCEPTION
            WHEN SQLSTATE 'PZ001'
              OR SQLSTATE 'PZ002'
              OR SQLSTATE 'PZ003'
              OR SQLSTATE 'PZ004'
            THEN
                GET STACKED DIAGNOSTICS
                    v_state = RETURNED_SQLSTATE,
                    v_message = MESSAGE_TEXT;

                INSERT INTO plpgsql_errors_lab.rejected_requests (
                    batch_id, request_id, error_state, error_message
                )
                VALUES (
                    p_batch_id,
                    v_request.request_id,
                    v_state,
                    v_message
                );

                v_rejected := v_rejected + 1;
        END;
    END LOOP;

    RETURN QUERY
    SELECT v_processed, v_rejected;
END;
$fn$;
```

### 31.1. Vì sao chỉ bắt những mã nghiệp vụ đã biết?

Nếu lỗi do deadlock, constraint hỏng hoặc database gặp vấn đề nghiêm trọng, không nên chuyển nó thành “một request bị từ chối” rồi tiếp tục mù quáng. Hàm chỉ bắt những trường hợp được thiết kế để xử lý và để lỗi khác truyền ra caller.

### 31.2. Vì sao UPDATE processed nằm trong block con?

Nếu `reserve_stock` và việc đánh dấu `processed` nằm trong cùng block, một lỗi được bắt sẽ rollback mọi thay đổi persistent được làm trong phần thân block đó. Nhờ vậy không có chuyện giảm kho nhưng request không được đánh dấu thành công vì một lỗi sau đó bị nuốt.

### 31.3. Vì sao ghi rejection trong handler?

Khi vào handler, thay đổi persistent của phần thân block con đã bị rollback. Việc INSERT rejection ở handler nằm ngoài phần đã rollback, và có thể được commit cùng transaction ngoài.

### 31.4. Chú ý biến đếm

Các biến PL/pgSQL không tự rollback với subtransaction, vì thế chỉ tăng `v_processed` sau các thao tác có thể thất bại. Nếu tăng sớm rồi câu sau RAISE, biến vẫn giữ giá trị tăng trong handler.

### 31.5. Chạy thử không commit

```sql
BEGIN;

SELECT *
FROM plpgsql_errors_lab.process_stock_batch(1);

SELECT
    request_id, sku, quantity, processed
FROM plpgsql_errors_lab.stock_requests
WHERE batch_id = 1
ORDER BY request_id;

SELECT
    request_id, error_state, error_message
FROM plpgsql_errors_lab.rejected_requests
WHERE batch_id = 1
ORDER BY rejection_id;

SELECT sku, stock
FROM plpgsql_errors_lab.products
ORDER BY sku;

ROLLBACK;
```

Khi lab ở trạng thái ban đầu, dự kiến:

- `processed_count = 2`.
- `rejected_count = 3`.
- Hai hàng request hợp lệ được đánh dấu processed trong transaction.
- Ba lỗi được ghi với `PZ004`, `PZ003` và `PZ002` theo thứ tự mẫu.
- Sau ROLLBACK, trạng thái quay về trước lời gọi.

### 31.6. Giới hạn về idempotency

Đây là lab mô tả exception. Một batch production cần thiết kế thêm:

- Request idempotency key.
- Quy tắc retry toàn batch/single item.
- Unique constraint cho bản ghi rejection nếu muốn tránh ghi lặp.
- Khóa cạnh tranh khi hai worker xử lý cùng batch.
- Trạng thái failed/processed bền vững và cách chọn lại hàng.
- Sự đồng bộ của stock và hệ thống bên ngoài.
- Cách xử lý crash và transaction restart.

Một cột `processed BOOLEAN` một mình không giải quyết hết các rủi ro đó.

---

## 32. Điểm tinh tế: log lỗi và rollback ngoài cùng

Giả sử batch function bắt một lỗi hàng và ghi bảng `rejected_requests`. Nếu caller chạy:

```sql
BEGIN;

SELECT *
FROM plpgsql_errors_lab.process_stock_batch(1);

ROLLBACK;
```

thì cả kết quả tồn kho và các bản ghi rejection được ghi trong transaction đều rollback.

### 32.1. Khi nào log được giữ?

Khi caller commit một transaction thành công:

```sql
BEGIN;
SELECT * FROM plpgsql_errors_lab.process_stock_batch(1);
COMMIT;
```

### 32.2. Không tồn tại “autonomous transaction” đơn giản trong function PL/pgSQL

Một exception handler trong function không thể tự COMMIT log lỗi, tách khỏi transaction ngoài, theo kiểu autonomous transaction có ở một số hệ quản trị khác.

### 32.3. RAISE LOG/NOTICE là kênh khác

Một thông điệp đã được gửi tới client hoặc server log không phải row DML trong transaction nên không có cùng semantics rollback. Tuy nhiên, kênh log đó lại có độ bền, retention và bảo mật riêng; không xem nó tự đáp ứng yêu cầu audit pháp lý.

### 32.4. Nếu audit thất bại phải tồn tại dù transaction nghiệp vụ rollback

Cần thiết kế một thành phần theo dõi ngoài ranh giới transaction hoặc một kiến trúc thích hợp. Ví dụ ứng dụng ghi sự kiện lỗi sau khi nhận SQLSTATE vào hệ thống logging/audit riêng, với chính sách an toàn và idempotency; nhưng vẫn cần cân nhắc sai lệch khi network failure.

---

## 33. RAISE trong trigger function

PL/pgSQL thường dùng trigger function để kiểm tra và từ chối một số thao tác dữ liệu.

Ví dụ minh họa chặn tên sản phẩm trống:

```sql
CREATE FUNCTION plpgsql_errors_lab.reject_blank_name()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW.display_name IS NULL
       OR BTRIM(NEW.display_name) = ''
    THEN
        RAISE EXCEPTION USING
            ERRCODE = 'PZ006',
            MESSAGE = 'Tên sản phẩm không được trống',
            HINT = 'Nhập display_name có ký tự hợp lệ';
    END IF;

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_reject_blank_product_name
BEFORE INSERT OR UPDATE OF display_name
ON plpgsql_errors_lab.products
FOR EACH ROW
EXECUTE FUNCTION plpgsql_errors_lab.reject_blank_name();
```

### 33.1. RAISE EXCEPTION trong trigger làm gì?

Nếu trigger phát EXCEPTION không được bắt, thao tác DML gọi trigger thất bại theo quy tắc transaction; row không được ghi thành công.

### 33.2. Vì sao dùng trigger thay CHECK?

Với một điều kiện đơn giản như:

```sql
CHECK (BTRIM(display_name) <> '')
```

CHECK constraint thường rõ và rẻ hơn trigger tùy biến. Trigger có ích hơn khi logic cần context phức tạp mà constraint không biểu đạt được phù hợp. Đừng tạo trigger cho mọi ràng buộc có thể viết bằng CHECK/UNIQUE/FK.

### 33.3. Không dùng trigger để log rồi nuốt lỗi

Nếu trigger function trả NEW dù phát hiện lỗi nghiêm trọng mà chỉ WARNING, dữ liệu vẫn có thể được ghi. Từ chối dữ liệu không hợp lệ phải được enforce bằng constraint hoặc EXCEPTION phù hợp.

### 33.4. Trigger cũng chạy trong transaction

Trigger không tự COMMIT. Mọi tác động database của trigger chịu giao dịch của DML đã kích hoạt nó.

### 33.5. Quyền và thông điệp

Thông báo trigger có thể được người dùng cuối nhận qua API khi INSERT/UPDATE thất bại. Không lộ thông tin nhạy cảm của bản ghi khác trong DETAIL/HINT.

---

## 34. Constraint deferrable và thời điểm lỗi xuất hiện

Không phải mọi lỗi constraint xảy ra ngay ở statement tạo dữ liệu.

PostgreSQL hỗ trợ một số constraint **DEFERRABLE**; việc kiểm tra có thể được hoãn tới cuối transaction theo thiết kế.

### 34.1. Vì sao quan trọng?

Giả sử một function thực hiện DML và trả thành công, nhưng constraint hoãn được kiểm tra khi `COMMIT`. Lỗi có thể xuất hiện **sau khi function đã hoàn thành**.

Handler bên trong function không thể chặn một lỗi chỉ xảy ra ở COMMIT ngoài function như thể nó đã được phát trong block.

### 34.2. Kiểu constraint nào?

Một số constraint như FOREIGN KEY, UNIQUE, PRIMARY KEY hoặc EXCLUDE có thể có khả năng DEFERRABLE theo điều kiện và cú pháp hỗ trợ. CHECK/NOT NULL không có cùng cơ chế hoãn tùy ý trong PostgreSQL thông thường.

### 34.3. SET CONSTRAINTS ... IMMEDIATE

Trong các hoàn cảnh phù hợp, transaction có thể yêu cầu kiểm tra deferred constraints sớm bằng `SET CONSTRAINTS ... IMMEDIATE`. Khi đó lỗi có thể xuất hiện tại statement kiểm tra, nhưng không dùng kỹ thuật này một cách mù quáng vì nó tác động transaction hiện tại.

### 34.4. Hợp đồng ứng dụng phải dựa vào COMMIT

Ngay cả khi function trả movement ID, không nên báo business transaction thành công cho đến khi COMMIT hoàn tất.

---

## 35. Deadlock và serialization_failure cần retry đúng tầng

Một số lỗi xảy ra do điều kiện đồng thời:

- `40001` — `serialization_failure`.
- `40P01` — `deadlock_detected`.

Trong nhiều hệ thống, chính sách hợp lý là **retry toàn transaction** nếu thao tác idempotent hoặc được bảo vệ bằng idempotency key.

### 35.1. Vì sao không tiếp tục phần còn lại của transaction cũ?

Sau lỗi transaction nghiêm trọng, trạng thái snapshot và các quyết định đã đọc trước đó có thể không còn hợp lệ. PostgreSQL khuyến nghị logic retry serialization failure phải bao gồm **toàn bộ transaction**, kể cả quyết định dựa trên dữ liệu đã đọc.

### 35.2. Pseudocode ở tầng ứng dụng

```text
for attempt in 1..maxAttempts:
    BEGIN TRANSACTION
    try:
        perform entire business transaction
        COMMIT
        return success
    catch SQLSTATE 40001 or 40P01:
        ROLLBACK
        if attempt < maxAttempts:
            sleep with bounded backoff/jitter
            retry whole transaction
        else:
            report retry exhausted
    catch any other error:
        ROLLBACK
        propagate/map error
```

### 35.3. Tránh retry vô hạn

Giới hạn số lần, timeout, backoff, metrics và phân biệt lỗi vĩnh viễn với lỗi tạm thời. Không retry lỗi `23505` hoặc `PZ002` một cách mù quáng.

### 35.4. Idempotency rất quan trọng

Nếu transaction có gọi cổng thanh toán hoặc gửi email ngoài database, việc retry toàn bộ cần tránh nhân đôi tác động. Transaction của PostgreSQL không tự rollback một HTTP request đã gửi.

### 35.5. Deadlock khác insufficient stock

Không đủ tồn kho là một trạng thái nghiệp vụ có thể giải thích cho người dùng. Deadlock là lỗi đồng thời/hạ tầng cần logic retry. Không ánh xạ cả hai sang cùng một SQLSTATE “có lỗi”.

---

## 36. Query canceled và assert failure

Hai trường hợp cần chú ý khi dùng `WHEN OTHERS`:

### 36.1. query_canceled — 57014

Một query có thể bị hủy do người dùng, timeout/cancel request hoặc cơ chế vận hành phù hợp. PostgreSQL có condition `query_canceled` và SQLSTATE `57014`.

`WHEN OTHERS` không bắt nó theo mặc định.

Nếu ứng dụng đã yêu cầu hủy công việc, việc code cố tình bỏ qua cancel có thể gây hành vi trái mong đợi. Không bắt query_canceled và tiếp tục tính toán khi không có nhu cầu rõ ràng, có kiểm soát.

### 36.2. assert_failure — P0004

PL/pgSQL có câu `ASSERT` để kiểm tra giả định nội bộ khi cấu hình cho phép.

```sql
DO $do$
DECLARE
    v_count INTEGER := 2;
BEGIN
    ASSERT v_count >= 0, 'Giả định count không âm';
END;
$do$;
```

Nếu assertion thất bại và việc kiểm tra assertion đang được bật, SQLSTATE thường là `P0004`.

### 36.3. ASSERT không thay RAISE EXCEPTION nghiệp vụ

`ASSERT` dùng để phát hiện lỗi lập trình/giả định nội bộ, không dành để báo input người dùng không hợp lệ. Một số cấu hình có thể tắt việc đánh giá assertions, vì thế không dùng ASSERT để enforce invariant nghiệp vụ quan trọng.

### 36.4. WHEN OTHERS không bắt hai lỗi này

Không tự giả định:

```sql
EXCEPTION WHEN OTHERS THEN
    RETURN TRUE;
```

sẽ nuốt được cancel/assertion. Quan trọng hơn, ngay cả khi một lỗi có thể bắt, thường cũng **không nên nuốt** hai loại lỗi này.

---

## 37. Thông báo có cấu trúc và khả năng quan sát

Một handler có thể ghi log chẩn đoán:

```sql
DO $do$
DECLARE
    v_state TEXT;
    v_message TEXT;
    v_detail TEXT;
    v_hint TEXT;
    v_context TEXT;
BEGIN
    BEGIN
        PERFORM 1 / 0;

    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_detail = PG_EXCEPTION_DETAIL,
            v_hint = PG_EXCEPTION_HINT,
            v_context = PG_EXCEPTION_CONTEXT;

        RAISE WARNING
            'Error state=% message=% detail=% hint=%',
            v_state,
            v_message,
            v_detail,
            v_hint;

        -- Gửi context vào log kiểm soát nếu thực sự cần;
        -- không công bố nguyên văn cho client không tin cậy.
        RAISE;
    END;
END;
$do$;
```

### 37.1. Nên log những trường nào?

- SQLSTATE.
- Tên function/mục đích thao tác.
- Request/correlation ID không nhạy cảm.
- Constraint name nếu phù hợp.
- Số lần retry/attempt.
- Kết quả transaction (commit/rollback).
- Metadata thời gian và tenant ID đã được bảo vệ theo chính sách.

### 37.2. Không lạm dụng MESSAGE làm nơi nhét JSON tùy ý

Nếu hệ thống muốn structured logs, ứng dụng hoặc logging pipeline nên có schema rõ: fields, data types, masking và retention. Một câu MESSAGE dài không tự tạo cấu trúc dễ truy vấn.

### 37.3. Tránh log cùng lỗi nhiều tầng

Một lỗi có thể được log ở database handler, JDBC layer, service layer và HTTP middleware. Nếu mỗi tầng đều ghi ERROR cùng stack, metrics có thể bị nhân lên. Quyết định tầng nào chịu trách nhiệm log chính, tầng nào chỉ gắn context rồi rethrow.

### 37.4. RAISE NOTICE không phải bảng metrics

Không có cơ chế mặc định tự tổng hợp số lỗi PZ004 theo SKU khi bạn chỉ phát NOTICE. Cần pipeline/SQL monitoring phù hợp nếu muốn dashboard.

---

## 38. GET STACKED DIAGNOSTICS và PG_EXCEPTION_CONTEXT

Hai loại ngữ cảnh dễ nhầm:

- `PG_EXCEPTION_CONTEXT`: nơi và call stack liên quan **lỗi đã xảy ra**.
- `PG_CONTEXT` dùng với `GET DIAGNOSTICS`: ngữ cảnh của **điểm thực thi hiện tại**.

### 38.1. Minh họa phân biệt

```sql
DO $do$
DECLARE
    v_error_context TEXT;
    v_current_context TEXT;
BEGIN
    BEGIN
        PERFORM 1 / 0;

    EXCEPTION WHEN division_by_zero THEN
        GET STACKED DIAGNOSTICS
            v_error_context = PG_EXCEPTION_CONTEXT;

        GET DIAGNOSTICS
            v_current_context = PG_CONTEXT;

        RAISE NOTICE 'Error context: %', v_error_context;
        RAISE NOTICE 'Handler context: %', v_current_context;
    END;
END;
$do$;
```

### 38.2. Tại sao phân biệt?

Khi handler nằm sâu trong một chuỗi function, stack của lỗi gốc có thể khác stack hiện tại của handler. Nếu chỉ log vị trí handler, bạn có thể bỏ lỡ nơi thực sự phát lỗi.

### 38.3. Không dựa vào text stack như API ổn định

Context phục vụ chẩn đoán; function names, line numbers hoặc format có thể thay đổi sau migration/phiên bản. SQLSTATE/constraint metadata mới là cơ chế phân loại có cấu trúc hơn.

---

## 39. RAISE trong vòng lặp: chọn mức thông báo và giảm nhiễu

Một batch lớn có thể có hàng trăm nghìn hàng. Nếu mỗi row đều:

```sql
RAISE NOTICE 'Đang xử lý request %', v_request_id;
```

thì số lượng thông điệp rất lớn, gây:

- Tốn chi phí format/gửi message.
- Nhiễu log.
- Tăng network traffic giữa server và client.
- Dễ che các lỗi quan trọng.
- Có thể làm chậm job đáng kể.

### 39.1. Mẫu theo cột mốc

Trong batch, ghi NOTICE mỗi 1.000 hàng hoặc khi kết thúc:

```sql
IF v_processed > 0
   AND v_processed % 1000 = 0 THEN
    RAISE NOTICE 'Đã xử lý % hàng', v_processed;
END IF;
```

### 39.2. DEBUG cho chẩn đoán chi tiết

Những thông tin phục vụ kiểm tra tạm thời có thể dùng DEBUG và được lọc theo session config, nhưng vẫn cần cân nhắc chi phí tạo message và bảo mật.

### 39.3. WARNING không thay bảng rejected rows

Nếu cần truy cứu mỗi dòng lỗi nhập liệu, ghi dữ liệu có cấu trúc trong transaction nghiệp vụ tương ứng. WARNING chỉ là kênh thông báo và không cung cấp một bảng dữ liệu được chuẩn hóa.

### 39.4. EXCEPTION cho lỗi làm công việc không thể tiếp tục

Đừng đổi một error cần rollback thành WARNING để “job không bị đỏ” nếu việc tiếp tục làm sai dữ liệu. Trạng thái fail là một kết quả vận hành quan trọng.

---

## 40. Giao diện Java/JDBC: đọc SQLSTATE thay vì parse message

Ở Java, PostgreSQL JDBC driver thông thường cung cấp lỗi qua `SQLException` hoặc các subclass thích hợp.

Ví dụ:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class InventoryRepository {

    public long reserve(
            Connection connection,
            String sku,
            int quantity
    ) throws SQLException {

        String sql = """
            SELECT plpgsql_errors_lab.reserve_stock(?, ?)
            """;

        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {

            ps.setString(1, sku);
            ps.setInt(2, quantity);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "Function did not return a movement id"
                    );
                }
                return rs.getLong(1);
            }
        }
    }
}
```

### 40.1. Phân loại theo SQLSTATE

```java
try {
    long movementId = repository.reserve(conn, sku, quantity);
    // Chỉ công bố thành công sau khi transaction đã COMMIT.

} catch (SQLException e) {
    String state = e.getSQLState();

    if ("PZ001".equals(state) || "PZ002".equals(state)) {
        // Validation error: dữ liệu đầu vào không hợp lệ.
    } else if ("PZ003".equals(state)) {
        // SKU không tồn tại.
    } else if ("PZ004".equals(state)) {
        // Không đủ tồn kho.
    } else if ("23505".equals(state)) {
        // Vi phạm UNIQUE: cần xem ngữ nghĩa constraint.
    } else if ("40001".equals(state)
            || "40P01".equals(state)) {
        // Có thể cần retry toàn transaction với giới hạn.
    } else {
        // Lỗi không được định nghĩa: propagate/alert.
        throw e;
    }
}
```

Đoạn trên minh họa phân loại lỗi, **không phải một hàm transaction manager hoàn chỉnh**.

### 40.2. Phải rollback giao dịch khi có lỗi

Trong JDBC với `autoCommit=false`, khi statement gặp lỗi chưa được handle ở server, connection có thể nằm trong transaction bị đánh dấu thất bại. Ứng dụng phải rollback theo chính sách rồi mới sử dụng transaction mới.

### 40.3. Không phân loại bằng getMessage()

`e.getMessage()` có thể chứa detail, hint, câu chữ/phiên bản khác nhau. Dùng `getSQLState()` để phân loại ổn định hơn.

### 40.4. JDBC driver có thể cung cấp metadata thêm

Với driver PostgreSQL, các API chuyên biệt có thể cho biết server error fields như DETAIL, HINT, constraint. Nếu sử dụng, hãy giữ logic phụ thuộc đúng driver/version và tránh đưa chi tiết nhạy cảm vào HTTP response.

### 40.5. Mapping sang HTTP status là trách nhiệm API

Một phương án:

| Loại SQLSTATE | Cách xử lý API minh họa |
| --- | --- |
| `PZ001/PZ002` | Trả lỗi input rõ ràng, ví dụ HTTP 400 |
| `PZ003` | Không tìm thấy sản phẩm, ví dụ HTTP 404 |
| `PZ004` | Xung đột trạng thái tồn kho, ví dụ HTTP 409 |
| `23505` | Conflict khi uniqueness thực sự bị vi phạm |
| `40001/40P01` | Retry toàn transaction; báo thất bại tạm thời nếu hết lượt |
| Lỗi SQLSTATE chưa biết | Không lộ thông tin nội bộ; log/alert và trả 5xx phù hợp |

Đây là **lựa chọn thiết kế ứng dụng**, không phải mapping bắt buộc của PostgreSQL.

---

## 41. Java transaction retry: không chỉ bắt rồi lặp một SELECT

Với `40001` hoặc `40P01`, retry nên bắt đầu transaction mới.

Pseudocode Java:

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection conn = dataSource.getConnection()) {
        conn.setAutoCommit(false);

        try {
            // Toàn bộ logic nghiệp vụ phải là một transaction.
            // Không gọi hệ thống ngoài theo cách tạo side effect
            // không idempotent trước khi chắc chắn commit.
            performBusinessWork(conn);

            conn.commit();
            return;

        } catch (SQLException e) {
            try {
                conn.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }

            String state = e.getSQLState();
            boolean retryable =
                    "40001".equals(state)
                 || "40P01".equals(state);

            if (!retryable || attempt == maxAttempts) {
                throw e;
            }

            // Ứng dụng thực tế thêm backoff/jitter có giới hạn.
        }
    }
}
```

### 41.1. Retry toàn bộ quyết định nghiệp vụ

Nếu transaction đọc tồn kho, chọn nhà kho, tạo reservation và ghi log, phải xem các quyết định đó là một phần của lần retry. Không chỉ chạy lại statement cuối cùng với dữ liệu cũ.

### 41.2. Timeout và cancellation

Nếu request đã bị hủy, không tự retry đến vô hạn chỉ vì truy vấn thất bại. Cancel có semantics khác deadlock/serialization.

### 41.3. Đảm bảo khả năng retry an toàn

Idempotency keys, unique constraints, outbox pattern hoặc cơ chế tương đương giúp hạn chế việc tạo đơn hoặc gửi thông điệp hai lần khi client không biết chính xác transaction trước đã commit hay chưa.

### 41.4. Đừng retry lỗi input

`PZ002` không trở thành hợp lệ sau vài lần retry nếu client vẫn truyền quantity âm. Hãy trả lỗi rõ ràng cho người gọi.

---

## 42. Error boundary giữa database và application

Một thiết kế phân tầng hữu ích:

```text
Request / Java / API
        |
        | bind parameters, authenticate tenant
        v
Application service / transaction boundary
        |
        | gọi PL/pgSQL function
        v
PostgreSQL function
        |
        +-- xác thực input -> PZ001/PZ002
        +-- thao tác dữ liệu -> constraints, 23xxx
        +-- trạng thái nghiệp vụ -> PZ003/PZ004
        +-- deadlock/serialization -> 40xxx
        |
        v
SQLException / SQLSTATE / structured error fields
        |
        +-- lỗi input  -> hướng dẫn người dùng
        +-- hết hàng   -> xử lý conflict
        +-- transient  -> retry transaction có giới hạn
        +-- unexpected -> rollback + alert
```

### 42.1. Database chịu trách nhiệm gì?

- Bảo vệ invariants bằng PK/UNIQUE/CHECK/FK.
- Kiểm tra điều kiện nghiệp vụ gần dữ liệu khi có thiết kế phù hợp.
- Phát SQLSTATE có ý nghĩa.
- Bảo toàn transaction consistency.

### 42.2. Application chịu trách nhiệm gì?

- Authentication/authorization.
- Kiểm tra input sớm khi cần UX tốt.
- Quản lý transaction và retry.
- Ánh xạ lỗi ra HTTP/UI.
- Logging, tracing, monitoring và redaction.
- Idempotency đối với hệ thống ngoài.

### 42.3. Không làm mất SQLSTATE khi qua nhiều tầng

Nếu repository bắt mọi `SQLException` rồi ném một `RuntimeException("Database error")` không có cause/mã gốc, service khó biết lỗi nào cần retry.

Nếu phải wrap exception, giữ cause và cung cấp mã phân loại phù hợp.

### 42.4. Không phát lỗi nghiệp vụ với message khác nhau nhưng cùng mã vô tội vạ

Một mã PZ004 nên có hợp đồng rõ “insufficient stock” hoặc một nhóm lỗi có cùng cách xử lý. Không dùng lại PZ004 cho “đăng nhập sai” hay “hết hạn token”.

---

## 43. Bảo mật của thông báo lỗi

Thông báo chi tiết giúp debug, nhưng cũng là bề mặt rò rỉ dữ liệu.

### 43.1. Không tiết lộ row dữ liệu của tenant khác

Một handler có thể trả:

```sql
DETAIL = format(
    'User % owns account %, balance %',
    v_user, v_account, v_balance
)
```

Nếu caller chưa được phép xem các thông tin đó, chính lỗi đã tiết lộ dữ liệu nhạy cảm. Không dựa vào việc transaction rollback để che thông báo đã phát.

### 43.2. Phân tách message công khai và log nội bộ

Một API có thể trả:

```text
errorCode: INVENTORY_UNAVAILABLE
message: Sản phẩm hiện không đủ hàng
```

trong khi log nội bộ giữ SQLSTATE, request ID và ngữ cảnh không nhạy cảm theo chính sách. Không nhất thiết trả nguyên `PG_EXCEPTION_CONTEXT` cho client.

### 43.3. SECURITY DEFINER function

Nếu function dùng quyền owner cao hơn người gọi, cần đặc biệt cẩn thận với các query/DETAIL/HINT. Function không chỉ cần kiểm tra quyền dữ liệu trả về, mà cả **thông tin rò qua error text**.

### 43.4. search_path và hàm được gọi

Trong SECURITY DEFINER code, nên schema-qualify đối tượng quan trọng và cấu hình search_path an toàn theo tài liệu PostgreSQL. Một đối tượng bị resolve sai có thể tạo lỗi hoặc chạy logic không mong muốn.

### 43.5. Lọc dữ liệu đầu vào

RAISE không thay input validation và prepared statements. Nếu kết hợp message từ input người dùng, không chèn nguyên nội dung nguy hiểm/nhạy cảm vào log theo thói quen.

---

## 44. Khi nào dùng RAISE NOTICE thay cho kết quả SELECT?

Giả sử một function xử lý batch và muốn trả số lượng:

```text
Đã xử lý 2 dòng
Bỏ qua 3 dòng
```

Có hai kênh:

1. **Result data** — `RETURNS TABLE(processed_count,rejected_count)`.
2. **Notification** — `RAISE NOTICE 'Đã xử lý ...'`.

### 44.1. Dữ liệu chính nên là kết quả có cấu trúc

Nếu application phải quyết định tiếp theo dựa trên processed_count, return value/table output thường đáng tin và dễ lập trình hơn việc parse NOTICE.

### 44.2. NOTICE phù hợp cho người vận hành

Trong migration, psql script hoặc tác vụ bảo trì, NOTICE có thể giúp quan sát tiến độ.

### 44.3. NOTICE có thể bị lọc hoặc không được thư viện đọc

Các client, driver và cấu hình message filtering có cách hiển thị khác nhau. Không xây business protocol dựa vào một chuỗi NOTICE phải luôn đến UI.

### 44.4. WARNING là dấu hiệu, không phải contract lỗi

Nếu dữ liệu nhập có 10 dòng bị từ chối nhưng batch vẫn hoàn tất theo policy, số rejected_count và bảng rejected rows mới là dữ liệu contract; WARNING là thông tin bổ sung.

---

## 45. Quan sát và kiểm thử PL/pgSQL error handling

Một bài lab nên kiểm tra ít nhất những tình huống sau.

| Tình huống | Cách kích hoạt | Kết quả mong đợi |
| --- | --- | --- |
| Thành công | reserve SKU-100, quantity=1 | Movement ID, kho giảm trong transaction |
| SKU NULL | reserve(NULL,1) | PZ001 |
| Quantity=0 | reserve(SKU-100,0) | PZ002 |
| SKU không tồn tại | reserve(SKU-UNKNOWN,1) | PZ003 |
| Không đủ hàng | reserve(SKU-300,99) | PZ004 |
| Trùng SKU | INSERT SKU-100 | 23505 |
| Stock âm | INSERT product stock=-1 | 23514 |
| FK sai | INSERT movement product_id không tồn tại | 23503 |
| Không có SELECT STRICT | SELECT INTO STRICT SKU không tồn tại | P0002 |
| Nhiều hàng SELECT STRICT | SELECT INTO STRICT không lọc unique | P0003 |
| Chia 0 | PERFORM 1/0 | 22012 |
| RAISE EXCEPTION mặc định | RAISE EXCEPTION '...' | P0001 |
| RAISE NOTICE | RAISE NOTICE '...' | Không tự thất bại |
| RAISE WARNING | RAISE WARNING '...' | Không tự thất bại |
| RAISE; | Handler bắt lỗi rồi RAISE; | Mã gốc không đổi |
| Block rollback | INSERT rồi RAISE trong block con | INSERT trong block bị rollback |
| Biến giữ giá trị | Biến tăng trước RAISE | Biến vẫn giữ giá trị tại lỗi |
| Logging handler | INSERT rejection trong handler | Có nếu transaction ngoài commit |
| Rollback ngoài | ROLLBACK sau batch | Mọi DML thường trong transaction rollback |
| Query cancel | Cancel một query | Không bị OTHERS nuốt theo mặc định |
| Assert failure | ASSERT false khi enabled | P0004; không bị OTHERS bắt mặc định |

### 45.1. Dùng transaction thử nghiệm

Với những thao tác DML muốn xem kết quả tạm thời:

```sql
BEGIN;
-- Thực thi phép thử.
ROLLBACK;
```

Với câu làm transaction bị lỗi và không có handler, PostgreSQL có thể yêu cầu ROLLBACK trước khi tiếp tục statement kế tiếp. Không gom tất cả test lỗi vào một transaction rồi giả định chúng độc lập.

### 45.2. Test bằng psql và JDBC

Một câu lỗi có thể hiển thị màu sắc/message khác nhau ở psql, UI database, JDBC. Xác nhận **SQLSTATE và ngữ nghĩa transaction** không bị phụ thuộc cách hiển thị.

### 45.3. Thử ở các isolation levels cần dùng

Với function thay đổi tồn kho trong môi trường concurrent, test ít nhất concurrency đang chạy thực tế (READ COMMITTED/REPEATABLE READ/SERIALIZABLE theo thiết kế). Không dùng kết quả một session tuần tự để chứng minh không có race.

---

## 46. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Dùng WARNING thay EXCEPTION cho dữ liệu không hợp lệ | Statement vẫn có thể thành công | RAISE EXCEPTION hoặc constraint |
| Mọi lỗi đều P0001 | Client không phân biệt được | SQLSTATE riêng hoặc mã chuẩn |
| Parse SQLERRM để nhận diện UNIQUE | Dễ vỡ do thay đổi text/localization | SQLSTATE 23505 + CONSTRAINT_NAME |
| Gắn mã 23505 cho mọi lỗi input | Gây hiểu nhầm constraint | Custom SQLSTATE phù hợp |
| Custom SQLSTATE không có registry | Trùng nghĩa, đổi mã tùy tiện | Quản lý bảng mã lỗi |
| Dùng mã 00000 cho EXCEPTION | Mã thành công, không phù hợp | Chọn 5 ký tự hợp lệ khác |
| Dùng mã tự đặt kết thúc 000 | Có thể nhầm mã class | Tránh hậu tố 000 |
| RAISE format động sai cú pháp | Function compile lỗi | USING MESSAGE=format(...) |
| Quên biểu thức cho placeholder % | Format không hợp lệ | Khớp placeholders |
| Nhét token/PII vào DETAIL | Lộ thông tin qua lỗi/log | Redact/minimize |
| Dùng NOTICE để trả business data | Client có thể bỏ qua/lọc | RETURN/RETURNS TABLE |
| Tin rằng NOTICE bị ẩn nghĩa function chưa chạy | Nhầm cấu hình logging | Xem client_min_messages |
| Dùng INFO như NOTICE và mong lọc giống nhau | INFO có quy tắc đặc biệt | Hiểu mức client |
| Coi LOG luôn gửi client | Cấu hình/mức khác nhau | Kiểm tra logging |
| Bắt OTHERS rồi RETURN TRUE | Nuốt lỗi dữ liệu/hạ tầng | Bắt cụ thể hoặc RAISE; |
| Tin OTHERS bắt query_canceled/assert_failure | Không đúng | Xử lý theo quy tắc riêng |
| Bắt 23505 rồi luôn nói “SKU trùng” | Có thể unique khác | Kiểm tra CONSTRAINT_NAME |
| Nuốt 40001/40P01 như lỗi nghiệp vụ | Không retry transaction | Retry toàn transaction |
| Retry lỗi input không giới hạn | Lãng phí, vẫn thất bại | Phân loại retryable |
| RAISE EXCEPTION SQLERRM thay cho RAISE; | Mất SQLSTATE/context gốc | RAISE; |
| Ghi log ở mọi tầng | Nhiều sự kiện trùng | Quy định owner logging |
| Hiểu EXCEPTION block rollback toàn transaction luôn | Không phân biệt subtransaction | Xác định phạm vi block |
| Tin variables tự rollback | Bộ đếm báo sai | Tăng sau phần có thể lỗi |
| Tin INSERT error_log trong handler tự commit | Caller ROLLBACK sẽ xóa log | Thiết kế audit phù hợp |
| Dùng exception per row trong mọi batch lớn | Subtransaction overhead | Set-based/ON CONFLICT |
| Thực hiện SELECT stock rồi UPDATE không khóa | Race condition | Conditional UPDATE/locking |
| Tin SELECT chẩn đoán luôn cùng snapshot UPDATE | Concurrency có thể đổi dữ liệu | Nêu available_at_check |
| Bỏ constraints vì function đã validate | Các đường ghi khác vẫn có thể sai | CHECK/UNIQUE/FK |
| Dùng SELECT INTO không STRICT rồi tin 1 hàng | Có thể chọn một hàng tùy ý | STRICT hoặc unique/ORDER BY |
| Dùng STRICT khi 0 hàng bình thường | Exception không cần thiết | FOUND |
| Nhầm GET DIAGNOSTICS với GET STACKED DIAGNOSTICS | Đọc sai context | Chọn đúng lệnh |
| Lỗi trong handler được chính handler bắt lại | Không đúng phạm vi | Block ngoài nếu cần |
| Tưởng function tự COMMIT | Báo thành công trước COMMIT | Transaction boundary ở caller |
| Bắt lỗi COMMIT trong handler function | Lỗi deferred có thể xảy ra sau function | Xử lý COMMIT ở ứng dụng |
| Lạm dụng ASSERT cho input validation | Có thể bị tắt, sai mục đích | RAISE/constraints |
| Security definer tiết lộ dữ liệu trong DETAIL | Rò thông tin qua lỗi | Kiểm soát quyền và message |
| Dùng RAISE LOG để thay audit bền | Không chắc đáp ứng retention | Audit pipeline/bảng chuyên dụng |
| Coi HTTP status = SQLSTATE | Hai hệ mã khác | Mapping rõ |
| Dùng getMessage thay getSQLState | Dễ vỡ | API trường SQLSTATE |
| Không ROLLBACK sau lỗi JDBC | Transaction vẫn ở trạng thái lỗi | Quản lý transaction đúng |
| Test chỉ một session | Bỏ sót concurrency | Test đồng thời |
| Không thử lỗi khi COMMIT | Bỏ sót deferred constraints | Test cả transaction lifecycle |
| Không có upper bound retry | Có thể retry vô hạn | Max attempts/backoff |
| Không có idempotency | Retry có thể nhân tác động | Idempotency/outbox |

---

## 47. Bài tập thực hành

### Bài 1 — RAISE NOTICE

Viết `DO` block phát NOTICE gồm mã sản phẩm và số lượng, dùng placeholders `%`. Vì sao NOTICE không tự làm câu lệnh thất bại?

### Bài 2 — RAISE WARNING

Phát WARNING khi giá trị tùy chọn không có và vẫn cho phép block tiếp tục. Nêu khác biệt với EXCEPTION.

### Bài 3 — Sáu mức thông báo

Viết một DO block phát lần lượt DEBUG, LOG, INFO, NOTICE và WARNING. Thử thay `client_min_messages` bằng SET LOCAL trong transaction. Quan sát mức nào hiện ở client.

### Bài 4 — INFO đặc biệt

Giải thích vì sao INFO không có behavior lọc phía client giống mọi mức khác. Không coi nó là lỗi EXCEPTION.

### Bài 5 — Định dạng % và %%

Phát thông điệp “Tiến độ 75%” bằng format literal của RAISE và giá trị biến 75.

### Bài 6 — Dynamic MESSAGE

Dùng `RAISE NOTICE USING MESSAGE = format(...)` để tạo message có SKU và quantity. Vì sao không viết RAISE NOTICE format(...)?

### Bài 7 — DETAIL và HINT

Tạo một lỗi giả lập “không đủ hàng” với MESSAGE, DETAIL, HINT và ERRCODE.

### Bài 8 — Mã P0001 mặc định

Phát `RAISE EXCEPTION 'demo'` mà không chỉ định SQLSTATE, bắt bằng `WHEN raise_exception` và đọc mã. Vì sao P0001 không đủ để phân loại mọi lỗi nghiệp vụ?

### Bài 9 — SQLSTATE tùy chỉnh

Đặt `PZ010` cho một loại lỗi nội bộ mới. Viết RAISE EXCEPTION USING ERRCODE và một handler WHEN SQLSTATE 'PZ010'.

### Bài 10 — Các nhóm SQLSTATE

Giải thích hai ký tự đầu và ba ký tự cuối của `23505`. Nêu hai lỗi khác cũng thuộc class 23.

### Bài 11 — UNIQUE

Thử INSERT SKU-100 lần hai trong block có EXCEPTION, bắt `unique_violation` và lấy `CONSTRAINT_NAME`.

### Bài 12 — CHECK

Thử thêm sản phẩm stock=-1. Ghi SQLSTATE và constraint name, không parse thông điệp.

### Bài 13 — FOREIGN KEY

Thử INSERT movement với product_id không tồn tại. Bắt lỗi phù hợp và giải thích lý do transaction không nên vẫn ghi movement.

### Bài 14 — NOT NULL

Thử INSERT sản phẩm có sku=NULL. Cần phân biệt SQLSTATE với lỗi CHECK như thế nào?

### Bài 15 — SELECT INTO STRICT: không có hàng

SELECT INTO STRICT theo SKU không tồn tại, bắt no_data_found. So sánh với SELECT INTO không STRICT và FOUND.

### Bài 16 — SELECT INTO STRICT: nhiều hàng

SELECT INTO STRICT product_id từ tất cả sản phẩm, bắt too_many_rows. Làm thế nào sửa query để contract “đúng một sản phẩm” hợp lệ?

### Bài 17 — FOUND và ROW_COUNT

Chạy UPDATE cho SKU không tồn tại, dùng FOUND và GET DIAGNOSTICS ROW_COUNT. Vì sao không phải lúc nào 0 rows cũng là lỗi SQL?

### Bài 18 — GET STACKED DIAGNOSTICS

Từ một lỗi CHECK, lấy RETURNED_SQLSTATE, MESSAGE_TEXT, PG_EXCEPTION_DETAIL, PG_EXCEPTION_HINT và CONSTRAINT_NAME.

### Bài 19 — PG_EXCEPTION_CONTEXT

Trong handler, so PG_EXCEPTION_CONTEXT với GET DIAGNOSTICS PG_CONTEXT. Cái nào mô tả nơi lỗi thực sự phát ra?

### Bài 20 — RAISE; rethrow

Bắt division_by_zero, phát NOTICE về SQLSTATE, rồi RAISE; để lỗi truyền ra caller. Vì sao không nên thay bằng RAISE EXCEPTION '%', SQLERRM?

### Bài 21 — Lỗi trong handler

Tạo handler bắt PZ001 rồi phát PZ002. Chỉ dùng block ngoài để bắt PZ002. Giải thích đường đi.

### Bài 22 — WHEN OTHERS

Viết handler OTHERS log rồi RAISE; và nêu hai điều kiện không được OTHERS bắt mặc định.

### Bài 23 — Rollback block con

Trong transaction lab, INSERT một row ở bên ngoài exception block, INSERT row thứ hai trong block con rồi phát EXCEPTION. Chứng minh row thứ hai bị rollback, row đầu còn thấy trước khi ROLLBACK ngoài.

### Bài 24 — Biến không rollback

Tăng một biến PL/pgSQL trong block con trước khi phát lỗi, rồi in biến ở handler. Giải thích vì sao biến vẫn có giá trị tăng.

### Bài 25 — Log lỗi trong handler

Trong exception handler, INSERT rejected_requests. Kiểm tra dữ liệu trước và sau ROLLBACK của transaction ngoài. Có phải handler tự commit không?

### Bài 26 — reserve_stock thành công

Chạy reserve_stock('SKU-100',2) trong transaction, xem stock và movements rồi ROLLBACK. Vì sao nên chỉ báo thành công sau COMMIT?

### Bài 27 — Không đủ tồn kho

Gọi reserve_stock với quantity=999. Đọc mã PZ004 và DETAIL. Vì sao số available_at_check chỉ là số chẩn đoán trong concurrency?

### Bài 28 — SKU không tồn tại

Gọi reserve_stock cho SKU-UNKNOWN. Vì sao PZ003 hợp hơn “23505 duplicate key”?

### Bài 29 — Input NULL

Gọi validate_reservation(NULL,1) và validate_reservation('SKU-100',NULL). Dự đoán SQLSTATE từng trường hợp.

### Bài 30 — Kiểm tra race condition

Mô tả hai session cùng muốn đặt 7 sản phẩm khi chỉ có 8. Vì sao một câu UPDATE có điều kiện stock>=quantity tốt hơn SELECT rồi UPDATE dùng giá trị cũ?

### Bài 31 — Batch per-row exceptions

Chạy process_stock_batch(1) trong transaction rồi ROLLBACK. Dự đoán processed_count và rejected_count khi dữ liệu gốc chưa thay đổi.

### Bài 32 — Không nuốt lỗi hệ thống

Sửa function batch để có handler OTHERS chỉ log rồi RAISE; thay vì coi mọi lỗi là rejected request. Vì sao mã 40001 không nên bị nuốt?

### Bài 33 — ON CONFLICT

Thay một đoạn INSERT sản phẩm dùng EXCEPTION unique_violation bằng INSERT ... ON CONFLICT(sku) DO NOTHING. Trường hợp nghiệp vụ nào phù hợp?

### Bài 34 — Exception overhead

Mô tả benchmark 1 triệu rows với tỷ lệ lỗi 0%, 1% và 50%, so handler per-row với cách set-based. Những chỉ số nào cần đo?

### Bài 35 — Trigger

Tạo trigger chặn display_name rỗng theo ví dụ. So với CHECK(BTRIM(display_name)<>'') về đơn giản, hiệu năng và trường hợp áp dụng.

### Bài 36 — Deferred constraints

Một transaction dùng deferred foreign key có thể thất bại ở COMMIT. Vì sao function đã RETURN không thể tự bắt lỗi chưa xảy ra tại thời điểm đó?

### Bài 37 — Deadlock và serialization failure

Thiết kế retry policy cho 40P01 và 40001. Vì sao phải retry toàn transaction, không chỉ statement cuối?

### Bài 38 — Query cancellation

Giải thích query_canceled (57014) và tại sao WHEN OTHERS không bắt nó mặc định. Có nên bỏ qua cancel request của client không?

### Bài 39 — ASSERT

Dùng ASSERT để kiểm tra một invariant nội bộ. Giải thích vì sao không nên dùng ASSERT thay CHECK constraint hoặc RAISE EXCEPTION cho input nghiệp vụ.

### Bài 40 — JDBC getSQLState

Viết Java PreparedStatement gọi reserve_stock, bắt SQLException và phân biệt PZ002, PZ004, 23505, 40001, 40P01 bằng getSQLState().

### Bài 41 — HTTP error mapping

Thiết kế mapping từ PZ001/PZ002/PZ003/PZ004 sang HTTP 400/404/409 theo API contract. Vì sao không thể suy ra HTTP code chỉ từ SQLSTATE một cách phổ quát?

### Bài 42 — Thông điệp an toàn

Đề xuất MESSAGE, DETAIL và HINT cho lỗi “không có quyền truy cập tài khoản” mà không tiết lộ tài khoản có tồn tại hay số dư của người khác.

### Bài 43 — Audit bền vững

Một hệ thống phải giữ log thất bại ngay cả khi giao dịch rollback. Vì sao INSERT bảng log trong handler chưa đáp ứng? Đề xuất hướng logging/audit ngoài transaction thích hợp.

### Bài 44 — Mã lỗi riêng có phiên bản

Tạo bảng quy ước các mã PZ001–PZ006, giải thích ai sở hữu, điều kiện nào retryable, thông điệp public và metadata được phép log.

### Bài 45 — RAISE LOG/NOTICE trong job lớn

Một job xử lý 500.000 hàng. Thiết kế chính sách thông báo ở mỗi cột mốc, severity và các metrics để không tạo 500.000 NOTICE.

### Bài 46 — Full workflow

Thiết kế một luồng đặt hàng production: validate input, trừ tồn kho nguyên tử, ghi movement, ghi idempotency key, COMMIT, xử lý SQLSTATE ở Java, retry giao dịch khi thích hợp và phát alert khi gặp lỗi bất thường. Chỉ rõ thao tác nào thuộc database transaction và thao tác nào thuộc hệ thống ngoài.

---

## 48. Checklist xử lý ngoại lệ trong PL/pgSQL

| Câu hỏi | Cách đánh giá |
| --- | --- |
| Có phân biệt thông báo và lỗi thực sự? | NOTICE/WARNING vs EXCEPTION |
| Mức thông báo có đúng? | DEBUG/LOG/INFO/NOTICE/WARNING/EXCEPTION |
| Client có chắc thấy thông báo? | client_min_messages/driver |
| Server log có ghi thông báo? | log_min_messages/log configuration |
| Có phụ thuộc việc NOTICE được hiển thị? | Không dùng thông báo làm control flow |
| RAISE format đúng cú pháp? | Placeholder %/%% và số arguments |
| Message có cấu trúc? | MESSAGE/DETAIL/HINT |
| Có ERRCODE khi cần phân loại? | SQLSTATE chuẩn hoặc custom |
| SQLSTATE đủ năm ký tự? | Mã hợp lệ, không dùng 00000 |
| Mã tự đặt có registry? | Không collision, có ý nghĩa ổn định |
| Có parse message để phân loại không? | Dùng SQLSTATE thay vì text |
| Có nêu constraint metadata? | CONSTRAINT_NAME khi phù hợp |
| Handler theo mã cụ thể? | unique_violation/check_violation/... |
| Có WHEN OTHERS không? | Vì sao cần, có rethrow không? |
| Có nhớ OTHERS không bắt cancel/assert? | query_canceled/assert_failure |
| Có RAISE; để giữ lỗi gốc? | Không thay vô tình thành P0001 |
| Có sử dụng SQLSTATE/SQLERRM trong handler? | Scope đúng |
| Có dùng GET STACKED DIAGNOSTICS? | RETURNED_SQLSTATE/DETAIL/HINT/CONTEXT |
| Có hiểu GET DIAGNOSTICS ROW_COUNT? | Khác stacked diagnostics |
| Có hiểu FOUND? | 0 rows không nhất thiết là exception |
| Có dùng SELECT INTO STRICT đúng lúc? | P0002/P0003 |
| Phạm vi rollback block rõ? | Subtransaction chỉ block có EXCEPTION |
| Có biến thay đổi trước lỗi? | Biến không rollback |
| Có ghi log lỗi trong handler? | Commit phụ thuộc transaction ngoài |
| Có side effect ngoài database? | Rollback không tự đảo ngược |
| Có lỗi deferred constraint khi COMMIT? | Bắt ở transaction boundary |
| Có commit trước khi báo thành công? | Không nhầm function return với commit |
| Có constraint bảng nền? | PK/UNIQUE/CHECK/FK bảo vệ mọi đường ghi |
| Có concurrency check đủ mạnh? | Conditional UPDATE/locking |
| Có phân biệt lỗi nghiệp vụ và hạ tầng? | PZxxx vs 40xxx/23xxx |
| Có retry toàn transaction? | 40001/40P01 |
| Có giới hạn retry/backoff? | Không vô hạn |
| Có idempotency? | Tránh nhân đôi tác động |
| Có handler per row? | Chỉ khi cần và được benchmark |
| Có thể dùng ON CONFLICT không? | Expected duplicates |
| Có bảo vệ quyền tenant? | Auth/RLS/permissions |
| Có tránh lộ PII/secrets trong lỗi? | Redaction và public message |
| Có test bằng role thật? | Không chỉ superuser |
| Có JDBC getSQLState? | Không parse getMessage |
| Có xử lý rollback khi JDBC lỗi? | Transaction state sạch |
| Có mapping HTTP riêng? | SQLSTATE khác HTTP code |
| Có ghi event/metrics không? | Phân loại lỗi có quan sát |
| Có test cancel/assert? | Không nuốt tín hiệu vận hành |
| Có test dữ liệu NULL/âm/trùng? | Negative paths |
| Có test concurrent requests? | Race/deadlock/serialization |
| Có kiểm tra thông điệp trong log? | Client/server visibility |
| Có tài liệu hóa SQLSTATE contract? | Ownership/versioning |
| Có theo dõi thay đổi sau migration? | Constraints và handlers |
| Có chiến lược rollback/deploy? | Transaction và versioning |

## Kết luận

**`RAISE`, các mức thông báo, `SQLSTATE` và `EXCEPTION`** giúp PL/pgSQL giao tiếp rõ ràng với người dùng, ứng dụng và hệ thống vận hành. Nhưng các tính năng này không chỉ nhằm “in ra lỗi đẹp hơn”: chúng là một phần của hợp đồng dữ liệu, quyền truy cập và tính nhất quán giao dịch.

Những nguyên tắc cốt lõi:

1. **RAISE có nhiều mức, nhưng chỉ EXCEPTION thực sự tạo lỗi cần xử lý.** `NOTICE`/`WARNING` không tự rollback dữ liệu.
2. **SQLSTATE là cơ chế phân loại lỗi cho chương trình.** Đừng phân nhánh bằng cách parse message có thể thay đổi.
3. **Dùng MESSAGE, DETAIL, HINT đúng chức năng.** Thông điệp hữu ích nhưng không được tiết lộ secrets hoặc thông tin người gọi không có quyền xem.
4. **Khai báo mã lỗi riêng có chủ đích.** Giữ các mã chuẩn cho lỗi PostgreSQL và quy ước rõ những mã nghiệp vụ như PZ001–PZ006.
5. **Handler phải bắt đúng phạm vi.** Bắt lỗi cụ thể khi có cách phục hồi hợp lệ; `WHEN OTHERS` không phải lý do để trả thành công giả.
6. **`RAISE;` giữ nguyên lỗi gốc.** Khi chỉ thêm chẩn đoán rồi muốn báo caller, phát lại thay vì tạo một P0001 mới.
7. **Khối EXCEPTION có semantics subtransaction.** DML trong phần thân block bị rollback khi lỗi được bắt; biến PL/pgSQL không tự rollback, còn transaction ngoài vẫn quyết định COMMIT/ROLLBACK.
8. **GET STACKED DIAGNOSTICS cho thông tin có cấu trúc.** Dùng RETURNED_SQLSTATE và CONSTRAINT_NAME thay vì đoán từ câu chữ.
9. **Không dùng exception cho mọi trường hợp dự kiến.** `FOUND`, `ROW_COUNT`, `ON CONFLICT` và conditional UPDATE đôi khi rõ ràng và hiệu quả hơn.
10. **Đưa retry ra đúng tầng.** Với `40001` và `40P01`, thường phải retry toàn transaction, có giới hạn và idempotency.
11. **Đừng báo thành công trước COMMIT.** Deferred constraints và lỗi transaction có thể xuất hiện sau khi một function đã RETURN.
12. **Thiết kế cả luồng database–application.** PostgreSQL phát mã, Java đọc `getSQLState()`, service rollback/retry/map lỗi, còn hệ thống logging/audit bảo vệ thông tin và độ bền cần thiết.

Một hệ thống PostgreSQL đáng tin cậy không phải hệ thống “không bao giờ có lỗi”, mà là hệ thống **phát hiện đúng lỗi, dùng mã ổn định, rollback đúng phạm vi, không che giấu hỏng dữ liệu và giúp ứng dụng quyết định hành động tiếp theo một cách an toàn**.
