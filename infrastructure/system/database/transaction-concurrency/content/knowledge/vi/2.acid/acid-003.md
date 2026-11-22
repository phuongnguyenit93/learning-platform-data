# Tính cô lập: quan sát dữ liệu khi giao dịch chạy đồng thời

Trong một hệ thống thực tế, nhiều request có thể cùng đọc và sửa dữ liệu: hai người đặt chiếc vé cuối cùng, một người rút tiền trong khi người khác kiểm tra số dư, hoặc hai nhân viên đồng thời thay đổi lịch trực. Database phải quyết định **mỗi giao dịch được nhìn thấy phiên bản dữ liệu nào** và điều gì xảy ra khi các giao dịch cùng tác động lên dữ liệu đó.

Đây là nội dung của **Isolation (tính cô lập)**, chữ **I** trong ACID. Tính cô lập không có nghĩa database bắt buộc chạy từng giao dịch một. Nó mô tả các bảo đảm quan sát và tương tác giữa những giao dịch được thực thi xen kẽ hoặc song song.

Sau bài học, bạn cần phân biệt được dữ liệu *chưa commit* và *đã commit*, nhận diện những hiện tượng đọc/ghi bất thường, giải thích các mức cô lập phổ biến và chọn cách bảo vệ bất biến nghiệp vụ khi có nhiều giao dịch đồng thời.

## 1. Một giao dịch nhìn thấy điều gì?

Giả sử có bảng hàng tồn kho:

```sql
CREATE TABLE inventory (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);

INSERT INTO inventory (sku, quantity)
VALUES ('BOOK-01', 10);
```

Hai kết nối database độc lập tạo ra hai giao dịch:

- **T1** (người mua A) đang kiểm tra và cập nhật số lượng sách.
- **T2** (người mua B) đang đọc hoặc cập nhật cùng bản ghi.

T1 có thể bắt đầu trước, T2 chạy xen vào, rồi T2 kết thúc trước T1. Việc chạy xen kẽ này gọi là *interleaving*. Kết quả T2 đọc được có thể khác nhau tùy thời điểm truy vấn và mức cô lập.

Một lịch thực thi minh họa:

```text
Thời gian       T1 (kết nối A)                T2 (kết nối B)
    |           BEGIN
    |           UPDATE quantity = 9
    |                                           BEGIN
    |                                           SELECT quantity = ?
    |           COMMIT
    |                                           SELECT quantity = ?
    v                                           COMMIT
```

Câu hỏi ở đây không chỉ là “giá trị cuối cùng bằng bao nhiêu?” mà còn là:

1. T2 có được đọc `9` khi T1 **chưa** commit không?
2. Nếu T2 đã đọc `10` trước khi T1 commit, lần đọc tiếp theo trong **cùng** giao dịch T2 có thể thấy `9` không?
3. Nếu hai giao dịch cùng đọc `10` rồi cùng muốn giảm một đơn vị, làm sao tránh việc một lần mua bị mất dấu?

Thông thường, giao dịch thấy các thay đổi **do chính nó** thực hiện, kể cả trước commit. Việc nó có nhìn thấy thay đổi **của giao dịch khác** hay không là vấn đề cô lập. `COMMIT` công bố thay đổi thành kết quả đã xác nhận; `ROLLBACK` hủy các thay đổi chưa được xác nhận của giao dịch đó.

### Lịch tuần tự và kết quả tương đương tuần tự

Nếu T1 chạy hoàn toàn xong rồi T2 mới chạy, ta có một lịch **tuần tự** (*serial schedule*). Database thường cho chúng chạy đồng thời để tăng thông lượng. Mức cô lập mạnh nhất, **Serializable**, yêu cầu hiệu ứng của các giao dịch đã commit tương đương với một thứ tự chạy tuần tự hợp lệ. Điều này không đồng nghĩa mọi giao dịch đều bị khóa chạy lần lượt; hệ quản trị có thể cho chạy đồng thời rồi chặn, phát hiện xung đột hoặc hủy một giao dịch để giữ tính đúng đắn.

## 2. Những hiện tượng bất thường khi đọc dữ liệu

Các ví dụ dưới đây dùng T1 và T2 trên hai kết nối khác nhau. Chúng mô tả hành vi có thể xảy ra ở những mức cô lập nhất định, **không khẳng định mọi hệ quản trị database đều cho phép từng hiện tượng**.

### 2.1. Dirty read — đọc dữ liệu chưa commit

```text
Giá trị ban đầu: quantity = 10

T1: BEGIN
T1: UPDATE inventory SET quantity = 9 WHERE sku = 'BOOK-01'
T2: BEGIN
T2: SELECT quantity ...       -> 9 (giá trị T1 chưa commit)
T1: ROLLBACK                  -> giá trị trở lại 10
T2: quyết định bán tiếp dựa trên số 9 đã đọc
```

T2 đã quan sát một trạng thái **chưa từng trở thành dữ liệu đã commit**. Nếu ứng dụng thực hiện hành động dựa vào đó, kết quả có thể sai dù T1 đã rollback. Đây là *dirty read*.

Dirty read gắn với mức `READ UNCOMMITTED` theo mô hình SQL truyền thống. Riêng PostgreSQL **không cho phép dirty read**: nó xử lý `READ UNCOMMITTED` tương đương `READ COMMITTED`.

### 2.2. Non-repeatable read — cùng một hàng, hai lần đọc khác nhau

```text
Giá trị ban đầu: quantity = 10

T1: BEGIN
T1: SELECT quantity ...       -> 10
T2: BEGIN
T2: UPDATE quantity = 8
T2: COMMIT
T1: SELECT quantity ...       -> 8
T1: COMMIT
```

Trong cùng T1, cùng câu truy vấn đến cùng một bản ghi trả hai giá trị khác nhau vì T2 đã commit ở giữa. Đây là **non-repeatable read**. Nó khác dirty read: cả `10` và `8` đều là dữ liệu hợp lệ đã commit ở thời điểm tương ứng.

Không phải hệ thống nào cũng xem đây là lỗi. Chẳng hạn, màn hình giám sát muốn có dữ liệu mới nhất ở mỗi truy vấn có thể chấp nhận hành vi đó; một phép tính nghiệp vụ phải dựa trên bộ dữ liệu ổn định thì thường không.

### 2.3. Phantom read — tập hàng thỏa điều kiện thay đổi

```text
Ban đầu có 3 sản phẩm với quantity > 0.

T1: BEGIN
T1: SELECT COUNT(*) FROM inventory WHERE quantity > 0; -> 3
T2: BEGIN
T2: INSERT thêm sản phẩm có quantity = 5
T2: COMMIT
T1: SELECT COUNT(*) FROM inventory WHERE quantity > 0; -> 4
```

Ở đây, T1 không nhất thiết đọc lại một bản ghi cũ bị sửa. **Một hàng mới xuất hiện trong tập kết quả của điều kiện truy vấn**. Đây là *phantom read*. Tương tự, hàng bị xóa hoặc thay đổi điều kiện lọc cũng có thể làm tập kết quả thay đổi.

Phantom quan trọng với các quy tắc như “mỗi phòng chỉ có tối đa N lượt đặt”, “không được trùng khoảng thời gian”, hoặc “tổng số bản ghi thỏa điều kiện không vượt hạn mức”. Chỉ khóa một hàng đã biết chưa chắc bảo vệ được một điều kiện áp dụng cho cả tập hàng, kể cả hàng có thể được chèn về sau.

### 2.4. Read skew — ghép dữ liệu từ hai thời điểm

Giả sử hai tài khoản A và B có tổng số dư luôn bằng 1.000 trong một thao tác chuyển tiền nội bộ:

```text
Ban đầu: A = 500, B = 500

T1: đọc A = 500
T2: chuyển 100 từ A sang B trong một transaction, COMMIT
    -> A = 400, B = 600
T1: đọc B = 600
T1: cộng hai kết quả = 1.100
```

Nếu hai phép đọc của T1 lấy dữ liệu tại hai thời điểm khác nhau, T1 có thể nhìn thấy một **tổ hợp chưa từng tồn tại như một trạng thái đã commit hoàn chỉnh**. Một snapshot nhất quán cho toàn giao dịch giúp tránh dạng đọc lệch này. Nếu đọc A và B trong *cùng một câu lệnh SELECT* dưới cơ chế snapshot theo câu lệnh, hai giá trị thường được lấy từ cùng một snapshot; vấn đề trên phát sinh khi các câu lệnh lấy snapshot khác nhau.

## 3. Bất thường khi ghi: chỉ đọc dữ liệu đã commit vẫn có thể sai

Không có dirty read **không** đồng nghĩa cập nhật đồng thời sẽ đúng. Hai ví dụ sau thể hiện hai kiểu xung đột nghiệp vụ khác nhau.

### 3.1. Lost update — một lần cập nhật bị ghi đè

Giả sử `quantity = 10`, ứng dụng đọc số lượng về bộ nhớ, trừ đi `1` rồi ghi lại:

```text
T1: SELECT quantity -> 10
T2: SELECT quantity -> 10
T1: tính 10 - 1 = 9
T2: tính 10 - 1 = 9
T1: UPDATE inventory SET quantity = 9; COMMIT
T2: UPDATE inventory SET quantity = 9; COMMIT

Kết quả: quantity = 9; đã có hai lượt mua nhưng kho chỉ giảm một.
```

Đó là **lost update** trong mẫu *read → calculate → write* ở phía ứng dụng. Trong PostgreSQL `READ COMMITTED`, ví dụ gán một giá trị đã tính sẵn như trên có thể dẫn đến kết quả này. Hành vi cụ thể của cập nhật cạnh tranh thay đổi theo database, mức cô lập và cách viết SQL; PostgreSQL `REPEATABLE READ` có thể báo lỗi xung đột cập nhật thay vì cho cả hai commit.

Với phép giảm tồn kho đơn giản, hãy để database cập nhật dựa trên giá trị hiện tại một cách nguyên tử:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'BOOK-01' AND quantity > 0
RETURNING quantity;
```

Với PostgreSQL, lệnh này khóa hàng được cập nhật. Khi có giao dịch cạnh tranh, nó có thể phải đợi, rồi đánh giá lại điều kiện trên phiên bản phù hợp trước khi cập nhật. **Không có hàng được trả về** nghĩa là không tìm thấy sản phẩm hoặc tồn kho không đủ, và ứng dụng phải xử lý rõ ràng. Đây là ví dụ về cập nhật nguyên tử, **không phải** giải pháp phổ quát cho mọi bất biến trải trên nhiều hàng.

Một lựa chọn khác là **optimistic locking** bằng cột `version`:

```sql
-- Giả sử bảng đã có cột version và ứng dụng đã đọc expected_version.
UPDATE inventory
SET quantity = quantity - 1,
    version = version + 1
WHERE sku = 'BOOK-01'
  AND version = :expected_version
  AND quantity > 0;
```

Chỉ một giao dịch khớp `version` cũ có thể thành công. Giao dịch còn lại nhận số hàng cập nhật bằng `0` và phải tải lại dữ liệu/giải quyết xung đột, thay vì tự động ghi đè kết quả của giao dịch khác. `:expected_version` là tham số ứng dụng, không phải cú pháp giá trị literal của PostgreSQL.

### 3.2. Write skew — mỗi giao dịch sửa một hàng khác nhau nhưng phá vỡ quy tắc chung

Một bệnh viện yêu cầu **luôn còn ít nhất một bác sĩ trực**. Bảng có hai bác sĩ A và B, ban đầu cả hai đều đang trực:

```sql
CREATE TABLE doctors (
    id TEXT PRIMARY KEY,
    on_call BOOLEAN NOT NULL
);

INSERT INTO doctors (id, on_call)
VALUES ('A', TRUE), ('B', TRUE);
```

T1 và T2 cùng làm việc trên snapshot ban đầu:

```text
                       T1                          T2
                 đọc số người trực = 2       đọc số người trực = 2
                 cho A nghỉ                  cho B nghỉ
                 UPDATE A = false            UPDATE B = false
                 COMMIT                      COMMIT

Kết quả cuối: A = false, B = false, không còn ai trực.
```

Hai giao dịch **không cập nhật cùng một hàng**, nên khóa ghi theo từng hàng có thể không tạo xung đột trực tiếp. Mỗi giao dịch đưa ra quyết định dựa trên dữ liệu mà giao dịch kia cũng đang đọc. Đây là **write skew**.

PostgreSQL `REPEATABLE READ` dùng snapshot cấp giao dịch và vẫn có thể cho hai giao dịch trong ví dụ này commit. `SERIALIZABLE` của PostgreSQL phát hiện chu trình phụ thuộc cần thiết và sẽ hủy ít nhất một giao dịch với lỗi *serialization failure* khi sự xen kẽ đó không thể tương đương với thực thi tuần tự. Ứng dụng cần **retry toàn bộ transaction** đã thất bại.

Quy tắc “luôn còn một người trực” áp dụng cho **nhiều hàng**: một `CHECK (on_call IN (...))` riêng trên từng hàng không thể biểu diễn đúng bất biến này. Có thể bảo vệ nó bằng transaction `SERIALIZABLE`, hoặc mô hình hóa một hàng giám sát/chốt chung được khóa trước khi ra quyết định và cập nhật, cùng với các ràng buộc phù hợp. Cách nào hợp lý phụ thuộc tải, cấu trúc dữ liệu và database.

## 4. Bốn mức cô lập SQL: database cam kết điều gì?

SQL nêu bốn mức cô lập quen thuộc. Bảng sau phản ánh **các bảo đảm tối thiểu trong mô hình phân loại truyền thống**, nghĩa là hiện tượng có thể xảy ra không có nghĩa mọi database chắc chắn sẽ để nó xảy ra:

| Mức cô lập | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ COMMITTED` | Không | Có thể | Có thể |
| `REPEATABLE READ` | Không | Không | Có thể theo phân loại truyền thống |
| `SERIALIZABLE` | Không | Không | Không |

**Đừng suy ra tất cả hành vi đồng thời chỉ từ bảng này.** Lost update, write skew và những chu trình phụ thuộc phức tạp không được bảng ba hiện tượng trên mô tả đầy đủ. Đặc biệt, `REPEATABLE READ` của PostgreSQL ngăn phantom read nhờ snapshot MVCC nhưng **vẫn chưa tương đương Serializable** vì write skew vẫn có thể xảy ra.

### `READ UNCOMMITTED`

Ở mức lý thuyết, giao dịch có thể thấy thay đổi chưa commit của giao dịch khác, nên có nguy cơ ra quyết định theo dữ liệu rồi bị rollback. Đây là bảo đảm yếu nhất. Một số hệ quản trị nâng thực tế mức này lên cao hơn; PostgreSQL xử lý mức này như `READ COMMITTED`.

### `READ COMMITTED`

Một câu lệnh đọc bình thường chỉ quan sát dữ liệu đã commit, nhưng hai câu lệnh đọc trong cùng transaction có thể quan sát hai trạng thái đã commit khác nhau. Đây là mặc định của PostgreSQL. Nó thích hợp với nhiều thao tác CRUD, nhất là khi quyết định nghiệp vụ không yêu cầu toàn bộ transaction có một góc nhìn cố định và các cập nhật cạnh tranh đã được bảo vệ phù hợp.

### `REPEATABLE READ`

Đảm bảo đọc lại một hàng không bị đổi giá trị bởi cập nhật đã commit từ giao dịch khác theo định nghĩa truyền thống. Với PostgreSQL, các truy vấn đọc thông thường trong transaction dùng một snapshot ổn định, nên cả tập kết quả từ truy vấn điều kiện cũng ổn định đối với thay đổi từ transaction khác. Tuy nhiên, những giao dịch cùng dựa trên snapshot cũ để sửa **các hàng khác nhau** vẫn có thể phá vỡ quy tắc chung, như ví dụ lịch trực.

### `SERIALIZABLE`

Mức mạnh nhất: các transaction **được commit thành công** phải có hiệu ứng tương đương một thứ tự chạy tuần tự. Nó phù hợp khi tính đúng đắn phụ thuộc vào quan hệ giữa nhiều hàng, phép kiểm tra điều kiện trước khi ghi hoặc bất biến khó bảo vệ bằng khóa hàng đơn lẻ. Chi phí có thể là chờ khóa, tăng xung đột hoặc các transaction bị hủy và cần thử lại. Không nên mặc định rằng `SERIALIZABLE` đồng nghĩa “câu lệnh nào cũng không bao giờ phải retry”.

## 5. Thử quan sát trên hai kết nối PostgreSQL

Các câu lệnh tiếp theo dùng **PostgreSQL** để hành vi có ý nghĩa cụ thể, thay vì giả định mọi database triển khai bốn mức cô lập giống hệt nhau. Chạy phần tạo bảng ở mục 1 trước; sau đó mở hai cửa sổ SQL độc lập, **A** và **B**, mỗi cửa sổ dùng một kết nối. Đặt `quantity = 10` và commit trước mỗi kịch bản; kết thúc cả hai transaction rồi mới đặt lại dữ liệu.

### Thí nghiệm A: `READ COMMITTED` đọc hai lần ra hai giá trị

**Kết nối A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT quantity FROM inventory WHERE sku = 'BOOK-01';
-- 10
```

Giữ A đang mở transaction. **Kết nối B:**

```sql
BEGIN;

UPDATE inventory
SET quantity = 8
WHERE sku = 'BOOK-01';

COMMIT;
```

Quay về **kết nối A:**

```sql
SELECT quantity FROM inventory WHERE sku = 'BOOK-01';
-- 8

COMMIT;
```

T1/A không thấy thay đổi chưa commit của B; lần đọc thứ hai thấy `8` vì B đã commit. Hai câu `SELECT` có thể dùng hai snapshot khác nhau. Đây là non-repeatable read.

### Thí nghiệm B: `REPEATABLE READ` giữ góc nhìn ổn định

Đặt `quantity` trở lại `10`, rồi tại **kết nối A**:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT quantity FROM inventory WHERE sku = 'BOOK-01';
-- 10
```

Tại **kết nối B**:

```sql
BEGIN;

UPDATE inventory
SET quantity = 8
WHERE sku = 'BOOK-01';

COMMIT;
```

Quay về **kết nối A**:

```sql
SELECT quantity FROM inventory WHERE sku = 'BOOK-01';
-- Vẫn 10 trong snapshot của A

COMMIT;
```

Nếu một transaction mới bắt đầu sau đó, nó có thể đọc `8`. Việc A nhìn thấy `10` không có nghĩa B chưa commit; A đang đọc theo snapshot đã được chốt trước khi B commit. Trong PostgreSQL `REPEATABLE READ`, snapshot thông thường được xác lập khi câu lệnh truy vấn hoặc sửa dữ liệu đầu tiên của transaction thực thi, **không phải cứ vừa gửi `BEGIN` là mọi dữ liệu được chụp ngay**.

### Thí nghiệm C: phantom với `READ COMMITTED`

Tại **A**:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) FROM inventory WHERE quantity > 0;
-- Giả sử kết quả là 1
```

Tại **B**:

```sql
BEGIN;
INSERT INTO inventory (sku, quantity) VALUES ('PEN-01', 5);
COMMIT;
```

Tại **A**:

```sql
SELECT COUNT(*) FROM inventory WHERE quantity > 0;
-- Bây giờ có thể là 2

COMMIT;
```

Hàng `PEN-01` là một *phantom* đối với truy vấn điều kiện của A. Nếu chuyển A sang PostgreSQL `REPEATABLE READ` và thực hiện câu `COUNT` đầu tiên trước khi B commit, lần `COUNT` tiếp theo của A vẫn thấy tập hàng theo snapshot cũ. Hãy dùng SKU khác hoặc xóa `PEN-01` giữa các lần thử để tránh lỗi khóa chính trùng.

## 6. Database thực thi cô lập bằng cơ chế nào?

### MVCC — Multi-Version Concurrency Control

Nhiều database, trong đó có PostgreSQL, giữ nhiều phiên bản logic của hàng để transaction đọc bản phù hợp với **snapshot** của mình. Một cập nhật mới có thể tạo phiên bản mới; transaction cũ vẫn đọc phiên bản đủ điều kiện đối với snapshot cũ.

```text
Hàng BOOK-01:

  phiên bản V1: quantity = 10     (đã commit trước)
                        |
                        +-- T1 chốt snapshot thấy V1
                        |
  phiên bản V2: quantity = 8      (T2 cập nhật rồi commit)
                        |
                        +-- T3, bắt đầu sau đó, có thể thấy V2

T1 ở REPEATABLE READ tiếp tục thấy V1 trong snapshot của mình.
```

MVCC cho phép nhiều thao tác đọc diễn ra mà không luôn phải khóa chặn mọi lần ghi. Nhưng **MVCC không đồng nghĩa không có khóa**: các transaction vẫn có thể chờ nhau khi cập nhật cùng hàng, khóa tường minh, thực thi ràng buộc và những tình huống khác. Snapshot ổn định cũng không tự loại trừ write skew giữa các hàng.

Phạm vi snapshot thay đổi theo mức cô lập và hệ quản trị:

| Cách nhìn | Ý nghĩa thực tế |
|---|---|
| Snapshot theo câu lệnh | Hai câu `SELECT` trong cùng transaction có thể thấy những commit khác nhau. Ví dụ: đọc thông thường ở PostgreSQL `READ COMMITTED`. |
| Snapshot theo transaction | Nhiều câu `SELECT` nhìn một ảnh chụp nhất quán đã xác lập. Ví dụ: PostgreSQL `REPEATABLE READ`. |
| Serializable | Ngoài tính nhất quán của kết quả đọc, phải bảo đảm những transaction thành công không tạo lịch thực thi phi tuần tự hóa. PostgreSQL dùng cơ chế phát hiện phụ thuộc và có thể báo lỗi serialization. |

Trong cùng một transaction, các thay đổi do **chính transaction đó** thực hiện vẫn có thể được quan sát dù chúng xảy ra sau khi snapshot đọc được xác lập. Vì vậy “snapshot cố định” cần hiểu là góc nhìn đối với dữ liệu của **các transaction khác**, không phải cấm nhìn thấy các lệnh ghi của bản thân.

### Khóa bi quan — chặn các sửa đổi cạnh tranh khi cần

Khi nghiệp vụ phải đọc trạng thái rồi quyết định cập nhật một hàng, có thể khóa hàng đó trước khi ra quyết định:

```sql
BEGIN;

SELECT quantity
FROM inventory
WHERE sku = 'BOOK-01'
FOR UPDATE;

-- Kiểm tra số lượng và thực hiện cập nhật trong cùng transaction.
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'BOOK-01' AND quantity > 0;

COMMIT;
```

`SELECT ... FOR UPDATE` của PostgreSQL đặt khóa trên hàng được chọn. Giao dịch cạnh tranh muốn khóa/sửa hàng đó có thể phải chờ cho đến khi transaction hiện tại commit hoặc rollback. Khóa giúp bảo vệ chuỗi thao tác phụ thuộc cùng hàng, nhưng có chi phí chờ và có nguy cơ deadlock nếu các transaction lấy nhiều khóa theo thứ tự khác nhau.

Với điều kiện liên quan cả tập hàng (ví dụ có người trực, số booking trong khoảng thời gian), việc chỉ khóa vài hàng đang có **có thể chưa đủ** để ngăn hàng mới hoặc các cập nhật trên hàng khác phá vỡ điều kiện. Khi đó cần thiết kế ràng buộc dữ liệu, một hàng dùng chung làm điểm đồng bộ, khóa phù hợp với mô hình hoặc `SERIALIZABLE`.

### Optimistic locking — phát hiện thay đổi rồi thử lại

Thay vì giữ khóa trong suốt giai đoạn xử lý, ứng dụng đọc dữ liệu kèm `version`, tính toán, rồi chỉ ghi khi `version` chưa đổi. Nếu lệnh `UPDATE ... WHERE version = ...` ảnh hưởng `0` hàng, ứng dụng nhận biết một giao dịch khác đã sửa trước và xử lý xung đột. Cách này thường phù hợp khi xung đột hiếm; khi một hàng bị tranh chấp mạnh, nhiều lượt thử lại có thể làm tăng tải.

## 7. Chọn mức cô lập theo bất biến nghiệp vụ

Không có một mức cô lập tối ưu cho mọi thao tác. Đầu tiên cần viết rõ **điều gì bắt buộc đúng sau mỗi giao dịch commit**; sau đó xem giao dịch đọc và sửa những hàng nào, có thể xung đột ra sao.

| Tình huống | Nguy cơ chính | Hướng bảo vệ có thể dùng |
|---|---|---|
| Hiển thị danh sách tin tức mới nhất | Mỗi truy vấn thấy dữ liệu mới hơn | `READ COMMITTED` thường đủ nếu không yêu cầu ảnh chụp xuyên suốt nhiều câu lệnh. |
| Giảm tồn kho một SKU | Lost update, bán quá số lượng | Cập nhật nguyên tử có điều kiện; kiểm tra số hàng cập nhật. Có thể thêm khóa hoặc `version`. |
| Kiểm tra rồi tạo username duy nhất | Hai transaction đều thấy “chưa tồn tại” | `UNIQUE` constraint là tuyến bảo vệ cuối cùng; xử lý lỗi trùng khóa. |
| Đọc nhiều bảng để tạo một báo cáo nhất quán | Read skew, non-repeatable read | Snapshot nhất quán cấp transaction, ví dụ PostgreSQL `REPEATABLE READ`, khi phù hợp. |
| Duy trì điều kiện trải qua nhiều hàng | Write skew, phantom, serialization anomaly | `SERIALIZABLE`, ràng buộc mạnh trong schema hoặc một giao thức khóa chung được thiết kế cẩn thận. |
| Chuyển tiền giữa hai tài khoản | Cập nhật thiếu một bên, tranh chấp số dư | Thao tác debit/credit trong cùng transaction, kiểm tra điều kiện số dư và kiểm soát ghi đồng thời; rollback nếu bất kỳ bước nào thất bại. |

Một số quy tắc phòng vệ quan trọng:

1. **Ưu tiên ràng buộc ngay tại database** cho điều kiện database biểu diễn được: `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK`, cùng các cơ chế ràng buộc phù hợp của hệ quản trị. Hai request cùng kiểm tra trước khi `INSERT` không thay thế được `UNIQUE`.
2. **Giữ transaction ngắn**. Đừng mở transaction rồi chờ người dùng hoặc một API bên ngoài lâu không kiểm soát; nó kéo dài vòng đời snapshot/khóa và tăng xung đột.
3. **Đặt kiểm tra và cập nhật liên quan trong cùng transaction**. Nếu kiểm tra số dư bằng một transaction rồi trừ tiền ở transaction khác, mức cô lập của từng transaction riêng lẻ không tự bảo vệ khoảng trống ở giữa.
4. **Chuẩn bị retry có kiểm soát** cho lỗi có thể thử lại, đặc biệt `SQLSTATE 40001` (serialization failure) và tùy trường hợp `40P01` (deadlock detected) của PostgreSQL. Sau khi transaction thất bại, rollback rồi chạy lại **toàn bộ logic đọc → quyết định → ghi** với dữ liệu mới. Không chỉ lặp lại lệnh SQL cuối.
5. **Thiết kế idempotency cho tác động bên ngoài**. Nếu transaction gửi email, gọi cổng thanh toán hoặc phát sự kiện trước khi commit, retry có thể tạo tác động trùng. Nên tổ chức phát sự kiện sau commit hoặc dùng *transactional outbox*/idempotency key khi phù hợp.
6. **Đo tranh chấp thực tế**. Quan sát thời gian chờ khóa, deadlock, số lần retry và transaction kéo dài để quyết định có cần thay đổi mức cô lập, thứ tự khóa hoặc mô hình dữ liệu.

### Trong ứng dụng Java/Spring

Spring có thể khai báo mức cô lập trên transaction do framework quản lý:

```java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void updateOnCallSchedule(...) {
    // Đọc trạng thái hiện tại, kiểm tra quy tắc và cập nhật trong transaction.
}
```

Điều này yêu cầu transaction manager và database hỗ trợ mức đã chọn. Các giá trị như `Isolation.DEFAULT` dựa vào cấu hình mặc định của database. Annotation chỉ đặt ranh giới và mức cô lập cho transaction được Spring quản lý; **nó không tự tạo cơ chế retry hay thay thế ràng buộc dữ liệu**. Nếu triển khai retry, cần bảo đảm mỗi lần thử thật sự tạo một transaction mới (chẳng hạn orchestration retry ở bên ngoài phương thức transactional), và không phát sinh tác động ngoài database bị lặp ngoài ý muốn.

## 8. Cách suy luận khi gặp một bài toán concurrency

Khi xem một luồng nghiệp vụ có nhiều request đồng thời, hãy đi theo trình tự:

1. **Xác định bất biến:** Sau mọi `COMMIT`, điều gì phải luôn đúng? Ví dụ `quantity >= 0` và mỗi đơn hàng thành công phải giảm kho đúng một lần.
2. **Vẽ lịch xen kẽ:** T1 đọc gì? T2 đọc gì? Giao dịch nào ghi hàng nào? Khi nào mỗi giao dịch commit/rollback?
3. **Hỏi về góc nhìn:** T1 có được nhìn thay đổi chưa commit không? Hai câu đọc có cùng snapshot không? Việc đọc theo snapshot có che mất cập nhật của T2 đang cạnh tranh không?
4. **Tìm xung đột:** Hai giao dịch ghi cùng hàng hay ghi hai hàng khác nhau nhưng đọc trạng thái chung? Có hàng mới lọt vào một điều kiện truy vấn không?
5. **Chọn cơ chế bảo vệ:** Ràng buộc DB, cập nhật nguyên tử, khóa, `version` hay mức `SERIALIZABLE`. Kiểm tra cách database cụ thể triển khai và các lỗi cần xử lý.
6. **Tính đến transaction thất bại:** Một giao dịch bị rollback hoặc bị hủy do xung đột phải trả kết quả rõ ràng hay được thử lại toàn bộ mà không tạo hành động trùng.

### Bài tập tự suy luận

**Bài 1.** Hai tab của cùng người dùng đều đọc `quantity = 1`, cùng hiển thị “còn hàng”, rồi cùng đặt mua. Vì sao kiểm tra ở bước `SELECT` chưa đủ? Viết một câu `UPDATE` nguyên tử chỉ giảm kho khi còn hàng và nêu cách biết đơn nào thất bại.

**Bài 2.** T1 đọc tổng tiền từ hai bảng bằng hai câu `SELECT`; T2 cập nhật cả hai bảng và commit giữa hai lần đọc. T1 không đọc dữ liệu chưa commit nhưng tổng tiền vẫn sai. Hiện tượng này liên quan đến góc nhìn dữ liệu như thế nào? Snapshot cấp transaction giúp gì?

**Bài 3.** Trong ví dụ hai bác sĩ trực, tại sao mỗi transaction đều thấy “còn hai người” mà kết quả sau hai lần commit lại vi phạm quy tắc? Vì sao nâng từ `READ COMMITTED` lên PostgreSQL `REPEATABLE READ` vẫn chưa phải cách giải quyết chắc chắn? `SERIALIZABLE` đòi hỏi ứng dụng xử lý thêm điều gì?

**Bài 4.** Một API thử lại transaction `SERIALIZABLE` sau `SQLSTATE 40001`, nhưng bên trong transaction đã gọi cổng thanh toán thành công. Hãy giải thích nguy cơ và đề xuất cơ chế tránh tính phí hai lần.

## Kết luận

Isolation trả lời câu hỏi **giao dịch có thể quan sát dữ liệu nào khi các giao dịch khác đang chạy** và những kết quả kết hợp nào được phép commit. `READ COMMITTED` ngăn đọc dữ liệu chưa commit nhưng cho phép một transaction nhìn thấy các commit khác nhau giữa các câu lệnh. Snapshot cấp transaction giúp giữ góc nhìn ổn định nhưng chưa tự loại bỏ mọi bất thường ghi, đặc biệt write skew. `SERIALIZABLE` cung cấp bảo đảm tương đương thực thi tuần tự cho những transaction thành công, đồng thời đòi hỏi xử lý xung đột và retry.

Thiết kế transaction đúng luôn bắt đầu từ bất biến nghiệp vụ, rồi mới chọn mức cô lập và cơ chế cụ thể của database. Hiểu rõ **đang đọc phiên bản nào**, **đang khóa điều gì**, và **sẽ làm gì khi một transaction thất bại** là nền tảng để xây dựng hệ thống có thể hoạt động đúng dưới tải đồng thời.
