# MEMORY, vòng đời dữ liệu và giới hạn vận hành

MySQL có storage engine `MEMORY` để lưu các hàng dữ liệu trực tiếp trong bộ nhớ của máy chủ. Engine này có thể phục vụ tra cứu nhanh đối với tập dữ liệu nhỏ, tạm thời và có thể tạo lại, chẳng hạn bảng tra cứu mã trạng thái hoặc cache ngắn hạn. Đổi lại, dữ liệu trong bảng `MEMORY` không bền vững qua lần khởi động lại máy chủ, engine không hỗ trợ transaction như InnoDB và các thao tác ghi có thể cạnh tranh ở cấp bảng.

Vì vậy, chọn `MEMORY` là quyết định về vòng đời dữ liệu và cách ứng dụng phục hồi, không chỉ là quyết định để tăng tốc truy vấn. Với MySQL, cần hiểu rõ dữ liệu được lưu ở đâu, khi nào biến mất, giới hạn bộ nhớ áp dụng thế nào và cách xử lý khi bảng đầy hoặc server khởi động lại.

## 1. MEMORY storage engine là gì?

`MEMORY` là storage engine lưu nội dung hàng và chỉ mục trong RAM của tiến trình MySQL Server. Tên cũ của engine này là `HEAP`; cú pháp hiện đại nên dùng `ENGINE=MEMORY`.

Một bảng được tạo bằng `ENGINE=MEMORY` vẫn là một bảng MySQL bình thường về mặt tên và quyền truy cập. Các session được cấp quyền trên bảng có thể cùng truy cập bảng đó. Điểm khác biệt nằm ở cách engine lưu dữ liệu và các tính năng mà engine hỗ trợ.

Đặc điểm chính:

- **Dữ liệu nằm trong bộ nhớ:** việc đọc không phải lấy các trang dữ liệu của bảng từ file dữ liệu như một bảng InnoDB thông thường. Chỉ mục của bảng cũng chiếm bộ nhớ.
- **Không bền vững:** khi MySQL Server dừng hoặc khởi động lại, các hàng trong bảng `MEMORY` bị xóa. Định nghĩa của bảng thông thường vẫn tồn tại để ứng dụng có thể nạp dữ liệu lại.
- **Không hỗ trợ transaction:** thao tác thay đổi dữ liệu của `MEMORY` không được rollback theo transaction như InnoDB.
- **Khóa ở cấp bảng:** engine dùng table-level locking, vì vậy một thao tác ghi có thể chặn thao tác khác trên cùng bảng. Engine không cung cấp row-level locking và MVCC như InnoDB.
- **Chỉ mục HASH và BTREE:** HASH phù hợp với tra cứu bằng phép so sánh bằng; BTREE phù hợp hơn với truy vấn phạm vi và thứ tự.
- **Hàng có định dạng độ dài cố định:** thiết kế hàng có thể dùng nhiều RAM hơn dự kiến, đặc biệt với cột chuỗi có độ dài khai báo lớn.
- **Không phù hợp với một số kiểu dữ liệu:** `BLOB` và `TEXT` không được hỗ trợ.

`MEMORY` có thể cho độ trễ thấp khi bảng nhỏ và truy vấn phù hợp với chỉ mục. Tuy nhiên, không có bảo đảm rằng mọi truy vấn trên bảng này đều nhanh: quét bảng lớn, cạnh tranh khóa, cấp phát bộ nhớ và áp lực RAM toàn máy chủ vẫn có thể làm hiệu năng giảm.

## 2. Kiểm tra khả năng hỗ trợ MEMORY

Trước khi tạo bảng, kiểm tra engine có được bật trên server hay không:

```sql
SHOW ENGINES;
```

Trong kết quả, xem cột `Engine` có `MEMORY` và cột `Support` có giá trị cho biết engine được hỗ trợ. Giá trị thường gặp gồm `YES`, `DEFAULT`, `NO` hoặc `DISABLED`, tùy trạng thái cấu hình và phiên bản.

Cũng có thể kiểm tra từ `INFORMATION_SCHEMA.ENGINES`:

```sql
SELECT ENGINE, SUPPORT, TRANSACTIONS, XA, SAVEPOINTS
FROM INFORMATION_SCHEMA.ENGINES
WHERE ENGINE = 'MEMORY';
```

Các cột `TRANSACTIONS`, `XA` và `SAVEPOINTS` cho biết engine có hỗ trợ những khả năng transaction tương ứng hay không. Không nên suy ra tính năng chỉ từ tên engine hoặc từ việc câu lệnh `CREATE TABLE` thành công.

## 3. Tạo và sử dụng bảng MEMORY

### 3.1. Tạo bảng tra cứu nhỏ

Giả sử ứng dụng thường xuyên tra tên hiển thị của các trạng thái đơn hàng. Danh mục này nhỏ, ít thay đổi và có thể nạp lại từ bảng dữ liệu bền vững:

```sql
CREATE TABLE order_status_cache (
    status_code VARCHAR(20) NOT NULL,
    display_name VARCHAR(80) NOT NULL,
    sort_order INT NOT NULL,
    PRIMARY KEY (status_code),
    KEY idx_sort_order (sort_order) USING BTREE
) ENGINE=MEMORY;
```

Khóa chính được dùng cho tra cứu theo `status_code`. Với `MEMORY`, chỉ mục HASH là loại mặc định cho chỉ mục nếu không chỉ định loại khác; chỉ mục BTREE được khai báo rõ ở `sort_order` để hỗ trợ truy vấn phạm vi hoặc sắp xếp theo cột này.

Nạp một số hàng mẫu:

```sql
INSERT INTO order_status_cache
    (status_code, display_name, sort_order)
VALUES
    ('NEW', 'Mới tạo', 1),
    ('PAID', 'Đã thanh toán', 2),
    ('SHIPPED', 'Đang giao', 3),
    ('CANCELLED', 'Đã hủy', 4);
```

Tra cứu theo khóa:

```sql
SELECT display_name
FROM order_status_cache
WHERE status_code = 'PAID';
```

Tra cứu theo thứ tự:

```sql
SELECT status_code, display_name
FROM order_status_cache
WHERE sort_order >= 2
ORDER BY sort_order;
```

Đối với bảng nhỏ, truy vấn đơn giản có thể không cần nhiều chỉ mục. Mỗi chỉ mục bổ sung chiếm thêm RAM và làm thao tác ghi tốn thêm công việc. Hãy tạo chỉ mục theo mẫu truy vấn thực tế.

### 3.2. Nạp lại dữ liệu từ nguồn bền vững

Một cách sử dụng an toàn hơn là giữ dữ liệu chuẩn trong bảng InnoDB, rồi tạo bản tra cứu trong `MEMORY` khi ứng dụng khởi động hoặc khi danh mục thay đổi:

```sql
CREATE TABLE order_status (
    status_code VARCHAR(20) NOT NULL,
    display_name VARCHAR(80) NOT NULL,
    sort_order INT NOT NULL,
    PRIMARY KEY (status_code)
) ENGINE=InnoDB;

INSERT INTO order_status_cache
    (status_code, display_name, sort_order)
SELECT status_code, display_name, sort_order
FROM order_status;
```

Ví dụ này giả định hai bảng đã được tạo và danh mục nguồn có dữ liệu. Trong quy trình nạp lại, có thể xóa dữ liệu cache cũ trước rồi nạp lại:

```sql
TRUNCATE TABLE order_status_cache;

INSERT INTO order_status_cache
    (status_code, display_name, sort_order)
SELECT status_code, display_name, sort_order
FROM order_status;
```

Vì `MEMORY` không có transaction, `TRUNCATE` và `INSERT` không tạo thành một thao tác nguyên tử có thể rollback. Trong lúc nạp lại, session khác có thể nhìn thấy bảng rỗng hoặc dữ liệu mới chỉ được nạp một phần. Nếu ứng dụng cần cache luôn đầy đủ, hãy cân nhắc nạp vào một bảng cache mới rồi chuyển đổi tên bảng theo một quy trình được kiểm thử, hoặc dùng InnoDB cho cache cần cập nhật nguyên tử.

### 3.3. Bảng thường và bảng TEMPORARY

Hai cách khai báo sau có vòng đời khác nhau:

```sql
CREATE TABLE shared_lookup (
    code VARCHAR(20) PRIMARY KEY
) ENGINE=MEMORY;

CREATE TEMPORARY TABLE session_lookup (
    code VARCHAR(20) PRIMARY KEY
) ENGINE=MEMORY;
```

- `shared_lookup` là bảng thông thường. Các session có quyền có thể cùng nhìn thấy bảng; định nghĩa bảng tồn tại sau khi server khởi động lại, nhưng các hàng bị mất.
- `session_lookup` là bảng tạm gắn với session tạo nó. Session khác không nhìn thấy bảng này; bảng bị xóa khi session kết thúc. Dữ liệu cũng nằm trong RAM và không bền vững.

Không nhầm bảng `TEMPORARY` do ứng dụng tự tạo với bảng tạm nội bộ mà MySQL tự dùng khi thực thi truy vấn. Cơ chế internal temporary table có cấu hình và engine riêng; trong các phiên bản MySQL hiện đại, engine nội bộ mặc định không nhất thiết là `MEMORY`.

## 4. Vòng đời dữ liệu MEMORY

### 4.1. Điều gì xảy ra khi server khởi động lại?

Với bảng `MEMORY` thông thường:

1. Bảng được tạo và ứng dụng ghi các hàng vào RAM.
2. Các session truy vấn hoặc cập nhật bảng trong thời gian server đang chạy.
3. Khi MySQL Server dừng hoặc khởi động lại, dữ liệu hàng trong bảng `MEMORY` bị mất.
4. Sau khi server chạy lại, định nghĩa bảng thông thường vẫn có thể được nhìn thấy, nhưng bảng không có các hàng cũ.
5. Ứng dụng phải nạp lại dữ liệu từ nguồn bền vững hoặc chấp nhận cache trống cho đến khi được làm nóng.

Ví dụ, sau khi khởi động lại:

```sql
SELECT COUNT(*) AS cached_rows
FROM order_status_cache;
```

Kết quả có thể là `0` dù trước khi dừng server bảng có nhiều hàng. Đây là hành vi thiết kế của engine, không phải lỗi phục hồi dữ liệu.

### 4.2. Điều gì xảy ra khi crash hoặc mất điện?

Khi tiến trình MySQL bị crash hoặc máy chủ mất điện, dữ liệu trong RAM cũng không còn. `MEMORY` không cung cấp redo/undo log và cơ chế phục hồi crash để khôi phục các hàng đã ghi. Vì vậy, không dùng nó làm nguồn dữ liệu duy nhất cho đơn hàng, thanh toán, số dư, tồn kho hoặc thông tin mà nghiệp vụ yêu cầu giữ lại sau sự cố.

Định nghĩa bảng thông thường được quản lý bởi MySQL và có thể còn sau khi server khởi động lại. Điều này khác với việc dữ liệu hàng được lưu bền vững: nhìn thấy bảng trong `SHOW TABLES` không có nghĩa là các hàng đã được khôi phục.

### 4.3. Vòng đời của bảng TEMPORARY

Bảng `TEMPORARY` bị xóa khi session tạo nó kết thúc, kể cả khi server không restart. Nếu ứng dụng dùng connection pool, session có thể được giữ lại lâu hơn một request; bảng tạm có thể vẫn tồn tại khi connection được trả về pool. Cần chủ động `DROP TEMPORARY TABLE` hoặc quản lý tên bảng và vòng đời connection để tránh dữ liệu sót giữa các lần mượn kết nối.

Không dùng bảng tạm theo session để truyền trạng thái giữa hai kết nối khác nhau. Mỗi session có namespace và vòng đời riêng.

## 5. Giới hạn bộ nhớ và lỗi bảng đầy

### 5.1. max_heap_table_size

Kích thước tối đa của bảng `MEMORY` do biến hệ thống `max_heap_table_size` kiểm soát. Đây là giới hạn cho từng bảng, không phải ngân sách RAM tổng của toàn bộ MySQL Server.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'max_heap_table_size';
```

Có thể đặt giới hạn session trước khi tạo bảng trong session đó:

```sql
SET SESSION max_heap_table_size = 64 * 1024 * 1024;

CREATE TABLE request_cache (
    request_id BINARY(16) NOT NULL,
    status_code SMALLINT NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (request_id)
) ENGINE=MEMORY;
```

Ví dụ đặt giới hạn 64 MiB cho bảng được tạo trong session này, nếu cấu hình và quyền cho phép. Thay đổi biến không tự động làm tăng dung lượng của mọi bảng `MEMORY` đã tồn tại; muốn áp dụng giới hạn mới cho bảng hiện có, cần thực hiện quy trình thay đổi/rebuild phù hợp và đánh giá tác động.

Quản trị viên cũng có thể đặt giá trị GLOBAL cho các session mới. Không nên tăng giới hạn tùy tiện: nếu có nhiều bảng `MEMORY`, tổng lượng RAM mà chúng tiêu thụ có thể rất lớn dù từng bảng không vượt giới hạn riêng.

### 5.2. Khi bảng đạt giới hạn

Khi một bảng cần thêm bộ nhớ vượt giới hạn cho phép, thao tác ghi có thể thất bại với lỗi:

```text
ERROR 1114 (HY000): The table 'request_cache' is full
```

Đây không nhất thiết có nghĩa toàn bộ RAM vật lý đã hết. Bảng có thể đã chạm `max_heap_table_size` trước khi máy chủ hết RAM. Ngược lại, tăng `max_heap_table_size` khi hệ điều hành đang thiếu bộ nhớ có thể làm tình hình tệ hơn.

Khi gặp lỗi 1114:

1. Xác định bảng nào đầy và kiểm tra engine bằng `SHOW CREATE TABLE`.
2. Đo số hàng, kích thước hàng và chỉ mục; nhớ rằng chỉ mục cũng dùng RAM.
3. Kiểm tra `max_heap_table_size` ở đúng phạm vi session/global.
4. Xác định dữ liệu nào thực sự cần giữ trong cache và thời gian lưu giữ cần thiết.
5. Xóa hoặc làm mới dữ liệu hết hạn theo quy tắc nghiệp vụ, hoặc chuyển tập dữ liệu lớn sang InnoDB.
6. Chỉ tăng giới hạn sau khi tính được ngân sách RAM tổng và theo dõi tác động trên server.

Không giải quyết lỗi bảng đầy bằng cách xóa hàng ngẫu nhiên nếu những hàng đó còn được ứng dụng cần dùng. Cần xác định chính sách eviction, TTL hoặc cách phân trang dữ liệu trước khi triển khai.

### 5.3. Đừng nhầm max_heap_table_size với tmp_table_size

`max_heap_table_size` giới hạn bảng `MEMORY` do người dùng tạo. `tmp_table_size` và các biến liên quan đến internal temporary table điều khiển một phần hành vi bảng tạm nội bộ do MySQL tạo khi thực thi truy vấn. Hai tình huống này khác nhau.

Trong MySQL 8.0, engine nội bộ `TempTable` được dùng cho nhiều internal temporary table trong bộ nhớ theo cấu hình mặc định. Bảng nội bộ có thể được chuyển sang lưu trữ khác khi vượt ngưỡng hoặc theo điều kiện của phiên bản. Không nên suy ra rằng mọi `GROUP BY`, `ORDER BY` hoặc bảng tạm trong kế hoạch thực thi đều đang dùng storage engine `MEMORY`.

## 6. Thiết kế hàng và chỉ mục để không lãng phí RAM

### 6.1. Hàng có độ dài cố định

`MEMORY` dùng định dạng hàng có độ dài cố định. Điều này giúp truy cập hàng đơn giản, nhưng có thể gây lãng phí nếu khai báo cột chuỗi lớn trong khi giá trị thực tế thường ngắn.

Ví dụ, nếu một bảng chỉ cần lưu mã ngắn nhưng khai báo nhiều cột `VARCHAR(1000)`, kích thước hàng có thể bị chi phối bởi độ dài khai báo. Hãy chọn kiểu và độ dài vừa đủ, tránh đưa cột mô tả dài vào bảng `MEMORY`.

Engine không hỗ trợ `BLOB` và `TEXT`. Nếu dữ liệu cần nội dung lớn hoặc độ dài biến thiên đáng kể, dùng InnoDB hoặc storage phù hợp hơn.

### 6.2. Chọn HASH hay BTREE

MEMORY hỗ trợ hai loại chỉ mục phổ biến:

| Loại chỉ mục | Phù hợp với | Hạn chế |
|---|---|---|
| HASH | So sánh bằng trên toàn bộ khóa, ví dụ `WHERE code = 'PAID'` | Không hỗ trợ tìm kiếm theo khoảng và không cung cấp thứ tự khóa cho `ORDER BY` |
| BTREE | So sánh bằng, so sánh phạm vi, tiền tố khóa phù hợp và duyệt theo thứ tự | Có chi phí cấu trúc chỉ mục; cần đo lợi ích với mẫu truy vấn thực tế |

Nếu truy vấn chủ yếu tìm đúng một mã, HASH là lựa chọn tự nhiên. Nếu cần `WHERE expires_at < NOW()` hoặc `ORDER BY created_at`, hãy xem xét BTREE. Có thể khai báo rõ BTREE trong DDL:

```sql
CREATE TABLE short_lived_jobs (
    job_id BIGINT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    state_code SMALLINT NOT NULL,
    PRIMARY KEY (job_id),
    KEY idx_expires_at (expires_at) USING BTREE
) ENGINE=MEMORY;
```

Một chỉ mục HASH không thay thế được BTREE cho truy vấn phạm vi. Ngược lại, tạo nhiều chỉ mục không cần thiết làm tăng lượng RAM tiêu thụ và chi phí cập nhật. Kiểm tra bằng `EXPLAIN` và đo trên dữ liệu có kích thước gần thực tế.

## 7. Giới hạn transaction và đồng thời

### 7.1. MEMORY không có transaction rollback

`MEMORY` không hỗ trợ transaction. Các thay đổi trên bảng không được bảo vệ bởi `COMMIT`/`ROLLBACK` như thay đổi trên InnoDB.

Ví dụ:

```sql
CREATE TABLE memory_flags (
    flag_name VARCHAR(40) PRIMARY KEY,
    flag_value VARCHAR(40) NOT NULL
) ENGINE=MEMORY;

START TRANSACTION;

INSERT INTO memory_flags (flag_name, flag_value)
VALUES ('maintenance_mode', 'on');

ROLLBACK;

SELECT * FROM memory_flags;
```

Hàng vừa chèn vào `memory_flags` vẫn có thể tồn tại sau `ROLLBACK`, vì thao tác ghi của engine không tham gia transaction. Nếu trong cùng transaction còn thay đổi bảng InnoDB, thay đổi InnoDB có thể bị rollback trong khi thay đổi MEMORY vẫn còn. Đây là nguồn gây trạng thái không nhất quán nếu trộn hai engine trong một nghiệp vụ.

Không dùng bảng `MEMORY` làm nơi lưu một phần trạng thái mà bắt buộc phải commit/rollback nguyên tử cùng dữ liệu InnoDB. Nếu cần tính nguyên tử, hãy dùng InnoDB cho tất cả dữ liệu thuộc cùng đơn vị nghiệp vụ.

### 7.2. Khóa cấp bảng

Do dùng table-level locking, một thao tác ghi có thể khiến thao tác khác trên cùng bảng phải chờ. Khi nhiều session cùng ghi vào một bảng `MEMORY`, mức đồng thời có thể thấp hơn kỳ vọng dù dữ liệu nằm trong RAM.

Ví dụ, một bảng cache dùng chung bị cập nhật toàn bộ mỗi vài giây có thể làm các truy vấn đọc phải chờ khóa ghi. Với workload nhiều người dùng và nhiều thao tác cập nhật đồng thời, InnoDB với row-level locking thường phù hợp hơn.

Hãy theo dõi thời gian chờ, tần suất cập nhật và số lượng truy vấn đồng thời. Nếu cần cập nhật cache thường xuyên, cân nhắc batch nhỏ, giảm tần suất refresh, chia dữ liệu hợp lý hoặc dùng engine có khả năng đồng thời phù hợp.

### 7.3. Không hỗ trợ khóa ngoại như InnoDB

Không dùng `MEMORY` để làm nơi bảo đảm quan hệ tham chiếu giữa các bảng. Engine không cung cấp kiểm tra foreign key như InnoDB. Nếu dữ liệu cần bảo đảm cha-con, tính toàn vẹn tham chiếu và transaction, hãy lưu nguồn dữ liệu trong InnoDB rồi chỉ tạo bản tra cứu/cache phù hợp trong MEMORY.

## 8. Ứng dụng phù hợp và trường hợp nên tránh

### 8.1. Trường hợp phù hợp

- **Bảng tra cứu nhỏ:** mã trạng thái, mã loại hoặc cấu hình ít thay đổi có thể nạp lại từ bảng chuẩn.
- **Cache tạm thời:** dữ liệu được tạo lại từ nguồn bền vững và có chính sách hết hạn rõ ràng.
- **Bảng staging nhỏ:** dữ liệu trung gian chỉ cần trong thời gian xử lý và có thể nạp lại nếu server restart.
- **Tập dữ liệu tham chiếu chỉ đọc nhiều:** ít cập nhật, kích thước có thể dự đoán và có nhiều lần tra cứu theo khóa.

Ngay cả với các trường hợp này, cần có fallback khi cache trống hoặc mất dữ liệu. Nguồn chuẩn phải ở nơi bền vững nếu nghiệp vụ cần khôi phục.

### 8.2. Trường hợp nên tránh

- Dữ liệu giao dịch, đơn hàng, thanh toán, số dư hoặc tồn kho cần tồn tại sau restart.
- Dữ liệu cần transaction, rollback, MVCC hoặc khóa ở cấp hàng.
- Bảng lớn hoặc tăng trưởng khó dự đoán, có nguy cơ vượt ngân sách RAM.
- Bảng chứa `BLOB`, `TEXT` hoặc dữ liệu chuỗi dài.
- Tác vụ có nhiều session ghi đồng thời và cần thông lượng ghi cao.
- Dữ liệu cần foreign key hoặc tính toàn vẹn tham chiếu được engine bảo đảm.
- Dữ liệu cache nhạy cảm mà việc lộ trong bộ nhớ, core dump hoặc swap không được chấp nhận.

## 9. Khởi động lại, replication và chiến lược làm nóng cache

### 9.1. Xây dựng lại cache sau restart

Ứng dụng dùng MEMORY cần coi cache là dữ liệu có thể biến mất. Một quy trình khởi động nên có các bước:

1. Kết nối tới MySQL và xác nhận schema/table đã tồn tại.
2. Nạp dữ liệu từ nguồn InnoDB hoặc nguồn bền vững khác.
3. Kiểm tra số hàng, checksum hoặc một số invariant quan trọng.
4. Chỉ đánh dấu cache sẵn sàng sau khi nạp thành công.
5. Nếu nạp thất bại, dùng fallback tới nguồn chuẩn hoặc giữ chức năng phụ thuộc cache ở trạng thái chưa sẵn sàng.

Không để ứng dụng âm thầm coi cache rỗng là dữ liệu nghiệp vụ rỗng. Ví dụ, bảng mã trạng thái trống sau restart không có nghĩa hệ thống không còn trạng thái đơn hàng nào.

### 9.2. Xử lý nhiều server và replication

Replication có thể chuyển các thao tác DML lên bảng MEMORY từ nguồn sang replica, nhưng điều đó không biến dữ liệu trong RAM thành dữ liệu bền vững. Nếu một server khởi động lại, các hàng MEMORY trên server đó bị mất. Khi nguồn và replica restart ở các thời điểm khác nhau, nội dung bảng có thể khác nhau cho đến khi được nạp lại hoặc đồng bộ theo quy trình riêng.

Vì vậy, không dựa vào MEMORY để giữ trạng thái cần nhất quán giữa các node. Nếu dùng bảng này làm cache trên từng node, hãy có cơ chế tái tạo độc lập, xác định rõ node nào là nguồn chuẩn và giám sát cache readiness trên từng node.

### 9.3. Cache miss và dữ liệu hết hạn

Ứng dụng nên xác định hành vi khi không tìm thấy hàng:

- Đọc từ nguồn bền vững rồi có thể nạp lại cache.
- Chấp nhận trả kết quả mặc định nếu nghiệp vụ cho phép.
- Ghi metric cache miss và thời gian làm mới để phát hiện cache bị trống hoặc lỗi.

Nếu dùng cột thời hạn như `expires_at`, cần có quy trình xóa hàng hết hạn. Với chỉ mục BTREE trên cột thời gian, có thể tìm các hàng cần dọn:

```sql
DELETE FROM short_lived_jobs
WHERE expires_at < NOW();
```

Đây là thao tác ghi trên bảng MEMORY và vẫn chịu table-level locking. Chạy dọn dẹp quá thường xuyên hoặc xóa quá nhiều hàng cùng lúc có thể ảnh hưởng truy vấn khác. Hãy đo và chọn batch/tần suất phù hợp.

## 10. Quan sát và quản lý MEMORY trong vận hành

### 10.1. Xem engine, kích thước và số hàng

Kiểm tra định nghĩa:

```sql
SHOW CREATE TABLE order_status_cache;
```

Xem thông tin bảng:

```sql
SHOW TABLE STATUS LIKE 'order_status_cache'\G
```

Hoặc truy vấn metadata:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE
FROM INFORMATION_SCHEMA.TABLES
WHERE ENGINE = 'MEMORY'
ORDER BY DATA_LENGTH + INDEX_LENGTH DESC;
```

Các giá trị kích thước và số hàng trong metadata có thể là ước lượng hoặc phản ánh trạng thái engine theo cách triển khai; hãy kết hợp với metric RAM của tiến trình và hệ điều hành. Không cộng một con số metadata rồi xem đó là toàn bộ bộ nhớ MySQL đang dùng.

### 10.2. Theo dõi ngân sách RAM

Một server có thể có nhiều bảng MEMORY do nhiều schema hoặc ứng dụng tạo. Mỗi bảng có giới hạn riêng, nhưng tổng mức tiêu thụ có thể cộng dồn. Ngoài dữ liệu và chỉ mục MEMORY, MySQL còn cần RAM cho buffer pool InnoDB, connection, sort/join buffers, internal temporary tables, Performance Schema và các cấu trúc khác.

Quản trị viên cần:

- Liệt kê các bảng `ENGINE=MEMORY` và chủ sở hữu ứng dụng.
- Ước lượng số hàng tối đa, kích thước hàng và kích thước chỉ mục.
- Đặt `max_heap_table_size` có chủ đích, không chỉ dựa trên RAM đang trống tại một thời điểm.
- Theo dõi RSS của MySQL process, bộ nhớ hệ điều hành, swap và các chỉ số áp lực bộ nhớ.
- Có cảnh báo khi số hàng hoặc mức dùng bộ nhớ tiến gần giới hạn.
- Xóa bảng không còn dùng và định nghĩa TTL/eviction cho cache tăng trưởng.

### 10.3. Quy trình khi server restart

Sau restart, cần xác minh các bảng MEMORY đã được nạp lại trước khi mở lưu lượng nghiệp vụ. Có thể kiểm tra nhanh:

```sql
SELECT COUNT(*) FROM order_status_cache;
SELECT COUNT(*) FROM short_lived_jobs;
```

Không chỉ kiểm tra bảng tồn tại. Hãy kiểm tra dữ liệu có đủ, phiên bản cache có khớp nguồn chuẩn và ứng dụng có thể phục vụ request an toàn hay chưa.

## 11. So sánh MEMORY với InnoDB

| Tiêu chí | MEMORY | InnoDB |
|---|---|---|
| Nơi lưu dữ liệu hàng | RAM | Trang dữ liệu trên storage, cache nóng trong buffer pool |
| Bền vững qua restart | Không; hàng bị mất | Có, thông qua cơ chế redo/undo và phục hồi |
| Transaction/rollback | Không hỗ trợ | Có |
| Khóa | Table-level locking | Chủ yếu row-level locking cùng cơ chế khóa khác |
| MVCC | Không | Có |
| Foreign key | Không hỗ trợ như InnoDB | Có |
| Chỉ mục | HASH mặc định; hỗ trợ BTREE | BTREE cho các chỉ mục thông dụng và nhiều tính năng khác |
| Kiểu dữ liệu lớn | Không hỗ trợ BLOB/TEXT | Hỗ trợ |
| Phù hợp | Cache/bảng tham chiếu nhỏ, có thể tạo lại | Dữ liệu nghiệp vụ và workload cần tính bền vững, transaction |

Không nên chọn MEMORY chỉ vì dữ liệu được lưu trong RAM. InnoDB cũng giữ dữ liệu nóng trong buffer pool và cung cấp transaction, crash recovery cùng khả năng đồng thời tốt hơn cho phần lớn workload nghiệp vụ. Nếu một truy vấn InnoDB chậm, trước tiên hãy kiểm tra chỉ mục, kế hoạch thực thi, kích thước dữ liệu đọc và cấu hình buffer pool thay vì chuyển bảng sang MEMORY ngay lập tức.

## 12. Checklist trước khi chọn MEMORY

- Dữ liệu có thể mất hoàn toàn sau restart hoặc crash mà không gây mất mát nghiệp vụ không?
- Có nguồn bền vững để nạp lại dữ liệu không?
- Ứng dụng có xử lý cache miss và thời gian cache chưa sẵn sàng không?
- Kích thước hàng, số hàng và chỉ mục có thể dự đoán được không?
- Tổng RAM của tất cả bảng MEMORY có nằm trong ngân sách server không?
- Mẫu truy vấn cần HASH hay BTREE? Có cần truy vấn phạm vi hoặc sắp xếp không?
- Tải ghi có đủ thấp để chấp nhận table-level locking không?
- Nghiệp vụ có cần transaction, rollback, MVCC hoặc foreign key không?
- Có cần đồng bộ cache trên nhiều node và xử lý replication/restart không?
- Có metric, cảnh báo và quy trình làm nóng lại cache sau restart không?

## Kết luận

`MEMORY` phù hợp với tập dữ liệu nhỏ, tạm thời và có thể tái tạo. Các hàng và chỉ mục nằm trong RAM, nhưng bị mất khi MySQL Server restart hoặc crash; bảng thông thường vẫn giữ định nghĩa để nạp lại. Giới hạn `max_heap_table_size`, hàng có độ dài cố định, chỉ mục HASH/BTREE và table-level locking quyết định cách thiết kế cũng như khả năng vận hành. Hãy giữ dữ liệu chuẩn trong engine bền vững như InnoDB, xây dựng quy trình làm nóng cache, theo dõi ngân sách bộ nhớ và chỉ chọn MEMORY khi ứng dụng đã xử lý rõ vòng đời dữ liệu cùng các giới hạn của engine.
