# Vai trò của khóa, phiên bản dữ liệu và mức cô lập

Khi nhiều giao dịch (transaction) cùng truy cập dữ liệu, hệ quản trị cơ sở dữ liệu (DBMS) phải xử lý hai yêu cầu có thể xung đột: cho phép nhiều công việc diễn ra đồng thời để tăng thông lượng, đồng thời giữ cho kết quả đúng với quy tắc nghiệp vụ. **Khóa (lock)**, **phiên bản dữ liệu (data version/MVCC)** và **mức cô lập (isolation level)** là ba thành phần liên quan chặt chẽ nhưng giữ những vai trò khác nhau:

- **Khóa** điều phối quyền truy cập tài nguyên và kiểm soát những thao tác có thể xung đột.
- **Phiên bản dữ liệu** cho phép giao dịch đọc một trạng thái dữ liệu phù hợp trong khi giao dịch khác đang thay đổi dữ liệu.
- **Mức cô lập** quy định những kết quả và thay đổi đồng thời nào giao dịch được phép quan sát; DBMS dùng khóa, phiên bản, phát hiện xung đột hoặc kết hợp các cơ chế đó để thực thi cam kết này.

Không thể chỉ nhìn vào việc một câu lệnh có sử dụng khóa hay cơ sở dữ liệu có hỗ trợ MVCC để kết luận một nghiệp vụ đã an toàn khi chạy đồng thời. Điều cần xác định trước tiên là **tính đúng đắn mà nghiệp vụ cần bảo vệ**.

## 1. Vì sao giao dịch đồng thời cần được kiểm soát?

Một giao dịch nhóm nhiều thao tác thành một đơn vị có thể `COMMIT` (xác nhận) hoặc `ROLLBACK` (hủy). Trong ACID, thuộc tính **Isolation** liên quan đến cách các giao dịch tương tác khi lịch thực thi của chúng xen kẽ nhau. Ví dụ, hai yêu cầu cùng mua món hàng cuối cùng có thể đọc cùng một số lượng tồn kho, dù từng giao dịch riêng lẻ đều có vẻ hợp lệ.

Giả sử `inventory(id = 1, quantity = 10)` và hai giao dịch cùng muốn xuất một sản phẩm:

| Thời điểm | Giao dịch T1 | Giao dịch T2 |
|---|---|---|
| 1 | Đọc `quantity = 10` | |
| 2 | | Đọc `quantity = 10` |
| 3 | Tính và ghi `quantity = 9` | |
| 4 | | Tính và ghi `quantity = 9` |
| 5 | `COMMIT` | `COMMIT` |

Nếu cả hai thay đổi đều được chấp nhận theo cách này, dữ liệu cuối cùng là `9` thay vì `8`. Đây là ví dụ **lost update**: một lần cập nhật đã vô tình ghi đè tác dụng của lần khác. DBMS có thể chặn hoặc báo lỗi cho một số kiểu xung đột tùy cơ chế và mức cô lập, nhưng ứng dụng không nên mặc định rằng mọi mẫu “đọc trước, tính toán, ghi lại” đều tự an toàn.

Những hiện tượng thường gặp gồm:

| Hiện tượng | Dấu hiệu | Hệ quả có thể gặp |
|---|---|---|
| **Dirty read** (đọc bẩn) | T2 đọc giá trị T1 đã ghi nhưng chưa `COMMIT`; sau đó T1 `ROLLBACK`. | T2 ra quyết định dựa trên dữ liệu chưa từng được xác nhận. |
| **Non-repeatable read** (đọc không lặp lại) | T1 đọc một hàng hai lần; giữa hai lần, T2 sửa hàng và `COMMIT`, làm giá trị T1 nhìn thấy thay đổi. | Một phép kiểm tra trong cùng giao dịch cho hai kết quả khác nhau. |
| **Phantom read** (đọc hàng bóng ma) | T1 chạy lại một truy vấn theo điều kiện; T2 đã thêm/xóa hàng phù hợp và `COMMIT`, nên tập kết quả thay đổi. | Số hàng thỏa điều kiện bị thay đổi trong lúc xử lý. |
| **Lost update** (mất cập nhật) | Hai giao dịch tính giá trị mới từ cùng trạng thái cũ, rồi một thay đổi che mất thay đổi kia. | Sai số lượng, số dư, bộ đếm hoặc trạng thái. |
| **Write skew** (ghi lệch) | T1 và T2 cùng đọc một điều kiện bao quát nhiều hàng, sau đó sửa **những hàng khác nhau** khiến điều kiện chung bị phá vỡ. | Quy tắc “ít nhất một người trực”, giới hạn tổng hoặc ràng buộc nhiều hàng bị vi phạm. |

Ba hiện tượng đầu thường được dùng để giới thiệu các mức cô lập theo chuẩn SQL. **Lost update** và **write skew** đặc biệt quan trọng ở tầng nghiệp vụ; chỉ thuộc lòng ba hiện tượng đầu chưa đủ để đánh giá một quy trình giao dịch.

## 2. Khóa: phối hợp truy cập và xử lý xung đột

Khóa giúp DBMS quản lý việc các giao dịch cùng thao tác trên một tài nguyên, chẳng hạn hàng, trang dữ liệu, bảng, khóa chỉ mục hay một khoảng giá trị trong chỉ mục.

### 2.1. Shared lock và exclusive lock

Trong mô hình khóa đọc/ghi truyền thống, hai loại cơ bản là:

- **Shared lock (S, khóa chia sẻ):** bảo vệ dữ liệu đang đọc; nhiều giao dịch có thể cùng giữ khóa S trên tài nguyên đó.
- **Exclusive lock (X, khóa độc quyền):** bảo vệ thao tác ghi; khóa X xung đột với khóa S và X của giao dịch khác trên cùng tài nguyên.

| Khóa đã giữ | Xin S | Xin X |
|---|---|---|
| **S** | Có thể cùng tồn tại | Xung đột, thường phải chờ |
| **X** | Xung đột, thường phải chờ | Xung đột, thường phải chờ |

Đây là bảng tương thích **khái niệm** cho S/X. Hệ quản trị thực tế còn có khóa ý định (intent lock), khóa cập nhật, khóa trên siêu dữ liệu và các quy tắc riêng. Đặc biệt, trong DBMS dùng MVCC, câu `SELECT` thông thường có thể đọc phiên bản đã xác nhận **mà không giữ khóa S chặn người ghi**. Vì vậy không thể suy từ bảng trên rằng mọi lần đọc đều khóa người cập nhật.

### 2.2. Phạm vi và thời gian giữ khóa

- **Row lock:** điều phối các thay đổi trên hàng cụ thể; thích hợp khi nhiều giao dịch sửa những hàng khác nhau.
- **Page/table lock:** có phạm vi lớn hơn, có thể làm tăng số giao dịch bị chặn.
- **Key-range, gap hoặc predicate protection:** bảo vệ điều kiện truy vấn hoặc khoảng khóa để xử lý nguy cơ thêm hàng mới thỏa điều kiện (phantom). Cách cài đặt khác nhau tùy DBMS và isolation level.
- **Intent lock:** giúp DBMS phối hợp các khóa ở nhiều cấp, ví dụ khóa hàng trong một bảng.

Cùng một câu `WHERE` không bảo đảm luôn khóa đúng một hàng. Dấu vết truy cập, chỉ mục, kế hoạch thực thi và cơ chế của DBMS đều có thể ảnh hưởng đến phạm vi khóa thực tế.

Với họ thuật toán **two-phase locking (2PL)**, giao dịch tuân theo giai đoạn lấy thêm khóa trước khi đi vào giai đoạn nhả khóa. Biến thể **strict 2PL** giữ các khóa ghi đến khi kết thúc giao dịch, giúp tránh việc giao dịch khác dựa vào thay đổi chưa xác nhận. Không phải mọi DBMS hay mọi mức cô lập đều thực thi hoàn toàn bằng 2PL; MVCC và các cơ chế kiểm tra xung đột có thể tham gia.

### 2.3. Khóa tường minh khi đọc rồi quyết định cập nhật

Ví dụ cú pháp trong PostgreSQL/MySQL:

```sql
BEGIN;

-- Đọc đồng thời khóa hàng sản phẩm cần quyết định.
SELECT quantity
FROM inventory
WHERE id = 1
FOR UPDATE;

-- Thực hiện kiểm tra nghiệp vụ dựa trên giá trị vừa đọc.
UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1 AND quantity > 0;

COMMIT;
```

`SELECT ... FOR UPDATE` yêu cầu khóa hàng được chọn để một giao dịch khác muốn cập nhật/khóa xung đột hàng đó phải chờ hoặc nhận lỗi theo chính sách của DBMS. Sau `COMMIT` hoặc `ROLLBACK`, các khóa giao dịch tương ứng được giải phóng. Trong ứng dụng thực tế phải kiểm tra **số hàng được cập nhật**: `0` có thể nghĩa là hết hàng hoặc không tìm thấy sản phẩm.

Nếu không cần đọc để thực hiện một quyết định phức tạp, thao tác nguyên tử sau thường ngắn và rõ hơn:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1 AND quantity > 0;
-- Thành công khi số hàng ảnh hưởng = 1.
```

Phép trừ và điều kiện được đánh giá trong câu lệnh cập nhật của DBMS, thay vì tính từ một bản sao giá trị cũ ở ứng dụng. Khả năng xử lý xung đột, chờ khóa và thử lại vẫn phụ thuộc mức cô lập và DBMS.

### 2.4. Đổi lại: chờ, deadlock và thời gian khóa

Khóa ngăn được nhiều xung đột, nhưng cũng khiến giao dịch khác phải chờ. Ví dụ:

1. T1 khóa hàng A rồi xin khóa hàng B.
2. T2 khóa hàng B rồi xin khóa hàng A.
3. T1 chờ T2, trong khi T2 chờ T1: **deadlock**.

DBMS thường phát hiện deadlock và hủy một giao dịch để giải phóng vòng chờ. Ứng dụng phải xử lý lỗi tương ứng và có thể thử lại **toàn bộ giao dịch** nếu thao tác an toàn để thực hiện lại. Giữ giao dịch ngắn, truy cập các tài nguyên theo thứ tự nhất quán và tạo chỉ mục thích hợp giúp giảm xung đột, dù không loại bỏ hoàn toàn deadlock.

## 3. Phiên bản dữ liệu: cho phép đọc nhất quán khi có ghi đồng thời

**Multi-Version Concurrency Control (MVCC)** duy trì thông tin về nhiều phiên bản logic của một hàng. Thay vì bắt một truy vấn đọc luôn chờ giao dịch đang sửa hàng, DBMS có thể chọn phiên bản phù hợp với **snapshot** (ảnh chụp trạng thái dữ liệu) mà giao dịch được phép thấy.

Giả sử giá trị ban đầu của hàng A là `100`:

```text
Thời điểm       T1 (đọc)                         T2 (ghi)
----------------------------------------------------------------
t0              Bắt đầu snapshot, thấy A = 100
t1                                              UPDATE A = 120
t2                                              COMMIT
t3              Đọc A theo snapshot -> 100
```

Kết quả ở `t3` là `100` nếu T1 đang sử dụng **snapshot cố định của giao dịch**, như trong PostgreSQL `REPEATABLE READ`. Ngược lại, với PostgreSQL `READ COMMITTED`, mỗi câu truy vấn thông thường có snapshot mới; câu đọc tại `t3` có thể thấy `120`. Nói cách khác, **MVCC là cách quản lý phiên bản, còn isolation level quyết định quy tắc nhìn thấy phiên bản**.

Một cách hình dung đơn giản:

```text
Hàng A:
  Phiên bản V1: value = 100  (có hiệu lực ở snapshot cũ)
  Phiên bản V2: value = 120  (được T2 ghi và đã COMMIT)

T1 với snapshot cũ -> V1
T3 bắt đầu sau T2 COMMIT -> V2
```

DBMS thực tế dùng metadata như mã giao dịch hoặc thông tin thứ tự xác nhận để xác định phiên bản hợp lệ; không nhất thiết lưu các bản sao theo đúng cấu trúc minh họa ở trên. Phiên bản cũ được dọn dẹp theo cơ chế riêng, chẳng hạn `VACUUM` trong PostgreSQL hay undo/purge trong InnoDB.

**Lợi ích nổi bật:** trong nhiều tình huống, người đọc không chặn người ghi và người ghi không chặn truy vấn đọc thông thường. Tuy nhiên:

- **Hai thao tác ghi trên cùng hàng vẫn có thể xung đột**, phải chờ hoặc khiến một giao dịch bị hủy.
- `SELECT ... FOR UPDATE` vẫn là một yêu cầu khóa, ngay cả khi DBMS dùng MVCC.
- **Snapshot nhất quán không tự bảo đảm serializable**: hai giao dịch sửa các hàng khác nhau vẫn có thể vi phạm ràng buộc chung (write skew).
- Giao dịch giữ snapshot quá lâu có thể khiến DBMS phải giữ nhiều phiên bản cũ, ảnh hưởng lưu trữ, dọn dẹp và hiệu năng.

Cần phân biệt MVCC nội bộ của DBMS với **optimistic locking bằng cột `version` của ứng dụng**: hai kỹ thuật đều nhắc đến “phiên bản”, nhưng một bên điều khiển tính nhìn thấy của dữ liệu, bên kia phát hiện lần sửa dựa trên giá trị cũ.

## 4. Mức cô lập: định nghĩa những gì giao dịch được phép quan sát

SQL nêu bốn mức cô lập phổ biến. Bảng dưới mô tả **các hiện tượng có thể xảy ra theo khung giới thiệu của chuẩn SQL**, không phải lời khẳng định rằng mọi hệ quản trị đều để chúng xảy ra:

| Isolation level | Dirty read | Non-repeatable read | Phantom read | Ý nghĩa cơ bản |
|---|---|---|---|---|
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể | Mức bảo đảm thấp nhất trong nhóm này. |
| `READ COMMITTED` | Ngăn | Có thể | Có thể | Chỉ đọc dữ liệu đã được xác nhận; hai lần đọc vẫn có thể khác nhau. |
| `REPEATABLE READ` | Ngăn | Ngăn | Có thể theo chuẩn | Duy trì giá trị của các hàng đã đọc trong cùng giao dịch. |
| `SERIALIZABLE` | Ngăn | Ngăn | Ngăn | Kết quả phải tương đương một thứ tự thực thi tuần tự hợp lệ của các giao dịch. |

**Lưu ý khi vận dụng:**

1. Bảng chỉ tập trung ba hiện tượng thường được nêu trong SQL; nó **không mô tả đầy đủ lost update, write skew hay mọi serialization anomaly**.
2. Một DBMS có thể bảo đảm **mạnh hơn** yêu cầu tối thiểu của mức cô lập. Ví dụ, PostgreSQL xử lý `READ UNCOMMITTED` tương đương `READ COMMITTED`, và `REPEATABLE READ` dựa trên snapshot còn ngăn phantom quan sát được trong truy vấn thông thường.
3. Cùng tên `REPEATABLE READ` nhưng cách xử lý giữa PostgreSQL, MySQL InnoDB và các DBMS khác có thể khác nhau. `SNAPSHOT` cũng là tên một chế độ cô lập riêng ở một số hệ thống, không phải mức thứ năm chung của mọi DBMS.
4. `SERIALIZABLE` bảo đảm kết quả tương đương một lịch tuần tự; điều này **không đòi hỏi DBMS bắt từng giao dịch chạy lần lượt từ đầu đến cuối**. Hệ quản trị có thể dùng khóa phạm vi, phát hiện phụ thuộc giữa giao dịch, hoặc hủy giao dịch khi phát hiện xung đột nguy hiểm.

### 4.1. READ COMMITTED: dữ liệu đã commit nhưng hai lần đọc có thể khác nhau

Giả sử ban đầu `inventory(id=1, quantity=10)`. Minh họa trên PostgreSQL với hai phiên kết nối:

**Phiên A, bước 1:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT quantity FROM inventory WHERE id = 1;
-- 10
```

**Phiên B, thực hiện sau lần đọc thứ nhất của A:**

```sql
BEGIN;
UPDATE inventory SET quantity = 8 WHERE id = 1;
COMMIT;
```

**Phiên A, bước 2:**

```sql
SELECT quantity FROM inventory WHERE id = 1;
-- 8

COMMIT;
```

Phiên A không đọc dữ liệu chưa `COMMIT`, nhưng vẫn nhìn thấy thay đổi được `COMMIT` giữa hai câu lệnh. Đây là **non-repeatable read**, hoàn toàn phù hợp với `READ COMMITTED`. Trong PostgreSQL `REPEATABLE READ`, hai câu `SELECT` thông thường của A sẽ nhìn theo cùng snapshot và tiếp tục thấy `10`, nếu snapshot đã được thiết lập ở lần đọc đầu.

### 4.2. REPEATABLE READ / snapshot: nhất quán khi đọc chưa đồng nghĩa đúng mọi quy tắc

Xét bảng `doctor(id, on_call)` có hai bác sĩ A và B đều đang trực. Nghiệp vụ yêu cầu **phải luôn có ít nhất một bác sĩ trực**. Hai giao dịch cùng diễn ra:

| T1 | T2 |
|---|---|
| Đọc: có 2 bác sĩ trực. | |
| | Đọc: có 2 bác sĩ trực. |
| Cho bác sĩ A nghỉ (`on_call = false`). | |
| | Cho bác sĩ B nghỉ (`on_call = false`). |
| `COMMIT` | `COMMIT` |

Trong một mô hình snapshot isolation cho phép lịch này, T1 và T2 sửa **hai hàng khác nhau**, nên không có xung đột ghi cùng hàng. Cả hai có thể `COMMIT`, kết quả là **không còn bác sĩ trực nào**. Đây là **write skew**.

Một snapshot giúp mỗi giao dịch quan sát dữ liệu nhất quán, nhưng không tự đồng bộ quyết định dựa trên **điều kiện tổng hợp nhiều hàng**. Để bảo vệ quy tắc này có thể dùng `SERIALIZABLE` kèm xử lý thử lại khi giao dịch bị hủy, hoặc thiết kế một hàng điều phối/khóa chung thích hợp cho quyết định, đồng thời bổ sung ràng buộc cơ sở dữ liệu nếu có thể diễn đạt quy tắc bằng constraint.

### 4.3. SERIALIZABLE: bảo đảm mạnh hơn, cần xử lý lỗi xung đột

Ở mức `SERIALIZABLE`, kết quả của tập giao dịch đã xác nhận phải giống một cách sắp xếp tuần tự hợp lệ. Với ví dụ bác sĩ trực, hai giao dịch cùng quyết định rời ca dựa trên trạng thái “còn hai người” không thể cùng thành công theo lịch gây vi phạm quy tắc nếu dữ liệu được truy cập và kiểm tra đúng trong các giao dịch serializable.

Tùy DBMS, một giao dịch có thể **chờ khóa** hoặc nhận lỗi serialization và bị hủy để ngăn lịch không hợp lệ. PostgreSQL có thể phát hiện kiểu phụ thuộc như write skew bằng Serializable Snapshot Isolation (SSI). Ứng dụng phải có phương án chạy lại toàn bộ logic giao dịch với dữ liệu mới; chỉ chạy lại câu `COMMIT` hoặc một câu `UPDATE` riêng lẻ thường không đủ.

Mức cô lập cao không thay thế việc định nghĩa bất biến nghiệp vụ: nếu ứng dụng **không kiểm tra** “phải còn người trực” trong cùng giao dịch với thao tác cập nhật, DBMS không tự biết quy tắc đó.

## 5. Khóa, MVCC và isolation level phối hợp ra sao?

Ba khái niệm trả lời ba câu hỏi khác nhau:

| Câu hỏi | Thành phần chính | Ví dụ |
|---|---|---|
| Ai được cập nhật hàng này ngay bây giờ? | **Khóa / phát hiện xung đột ghi** | Hai giao dịch cùng `UPDATE` một hàng có thể phải chờ hoặc một giao dịch thất bại. |
| Khi một giao dịch khác vừa sửa dữ liệu, người đọc thấy giá trị nào? | **Phiên bản dữ liệu + quy tắc snapshot** | Truy vấn `READ COMMITTED` có thể thấy bản mới đã commit ở câu tiếp theo; transaction snapshot có thể tiếp tục thấy bản cũ. |
| Những lịch đồng thời nào được phép cho toàn bộ giao dịch? | **Isolation level** | `SERIALIZABLE` loại các lịch có kết quả không thể giải thích bằng thứ tự tuần tự hợp lệ. |

Ví dụ, ở một DBMS hỗ trợ MVCC, `SELECT` thường có thể đọc phiên bản cũ mà không chờ `UPDATE` của giao dịch khác, trong khi **hai `UPDATE` cùng hàng vẫn phải được phối hợp**. Nếu truy vấn cần quyết định “chỉ tôi được xử lý đơn hàng này”, ứng dụng có thể cần `FOR UPDATE` hoặc thao tác cập nhật có điều kiện. Nếu quyết định dựa trên một **tập hàng**, chỉ khóa một hàng bất kỳ có thể không đủ.

Có thể hình dung dòng xử lý:

```text
Ứng dụng bắt đầu transaction
            |
            v
Chọn isolation level và thực hiện SQL
            |
            +--> Truy vấn đọc: DBMS chọn phiên bản/snapshot hợp lệ
            |
            +--> Truy vấn ghi: DBMS phối hợp khóa và kiểm tra xung đột
            |
            +--> Quy tắc nhiều hàng: cần mức cô lập / khóa phù hợp
            |                       và constraint nghiệp vụ
            v
     COMMIT hoặc ROLLBACK
            |
            +--> Nếu deadlock / serialization failure:
                 xử lý lỗi, có thể thử lại toàn bộ transaction
```

Cần tránh hiểu **“MVCC = không dùng khóa”** hoặc **“thêm `FOR UPDATE` = mọi ràng buộc nghiệp vụ an toàn”**. Cơ chế dùng để đọc, ghi và bảo vệ điều kiện tìm kiếm có thể khác nhau ngay trong cùng một giao dịch.

## 6. Optimistic locking: dùng cột version để phát hiện cập nhật dựa trên dữ liệu cũ

Khi nhiều người cùng chỉnh sửa một bản ghi, ứng dụng thường dùng **optimistic concurrency control** với cột `version`:

```sql
-- Giả sử có bảng inventory(id, quantity, version)
-- Ứng dụng đã đọc: id = 1, quantity = 10, version = 7.

UPDATE inventory
SET quantity = 9,
    version = version + 1
WHERE id = 1 AND version = 7;
```

Nếu một giao dịch khác đã cập nhật và tăng `version` từ `7` lên `8`, câu lệnh trên sẽ ảnh hưởng `0` hàng; ứng dụng phát hiện rằng dữ liệu mình dùng đã cũ. Khi đó phải quyết định: thông báo xung đột cho người dùng, đọc lại rồi thử lại, hay thực hiện một hành động khác phù hợp với nghiệp vụ.

Đặc điểm cần phân biệt:

- **MVCC nội bộ**: DBMS quản lý nhiều phiên bản và xác định phiên bản nào một snapshot được thấy.
- **Cột `version` của ứng dụng**: kiểm tra bằng điều kiện `WHERE version = ...` để từ chối lần ghi xây dựng trên trạng thái cũ.
- **Khóa bi quan (`FOR UPDATE`)**: giữ quyền truy cập xung đột trước khi hoàn tất logic đọc–sửa.
- **Cập nhật nguyên tử có điều kiện**: để DBMS tự kiểm tra và cập nhật trong một câu SQL, chẳng hạn `SET quantity = quantity - 1 WHERE quantity > 0`.

Tăng `version` trên **một hàng** không mặc nhiên ngăn được write skew giữa **nhiều hàng**. Giải pháp cần khớp với phạm vi ràng buộc cần bảo vệ.

## 7. Chọn cơ chế theo tình huống thực tế

| Nhu cầu | Hướng xử lý thường phù hợp | Điểm phải kiểm tra |
|---|---|---|
| Truy vấn xem danh sách, cho phép thấy dữ liệu mới ở mỗi câu | `READ COMMITTED`, kết hợp MVCC nếu DBMS hỗ trợ | Hai lần đọc trong cùng giao dịch có thể khác nhau. |
| Đọc nhiều bảng để tạo một báo cáo nhất quán tại cùng snapshot | Transaction snapshot / `REPEATABLE READ` phù hợp với DBMS | Có thể giữ phiên bản cũ lâu; dữ liệu có thể không phải mới nhất khi kết thúc. |
| Giảm tồn kho của một sản phẩm | `UPDATE ... SET quantity = quantity - 1 WHERE quantity > 0` | Phải kiểm tra số hàng ảnh hưởng và xử lý trường hợp không còn hàng. |
| Đọc trạng thái rồi thay đổi một hàng dựa trên logic nghiệp vụ | `SELECT ... FOR UPDATE` hoặc kiểm tra `version` | Phạm vi khóa, trường hợp thất bại và thời gian giữ giao dịch. |
| Bảo vệ ràng buộc tổng hợp nhiều hàng, như số người trực tối thiểu | `SERIALIZABLE` với retry hoặc cơ chế khóa chung được thiết kế rõ | Phải đọc điều kiện và ghi thay đổi trong **cùng** giao dịch. |
| Chặn dữ liệu trùng hoặc quan hệ không hợp lệ | `UNIQUE`, `CHECK`, `FOREIGN KEY` khi biểu diễn được | Kiểm tra bằng `SELECT` trước khi `INSERT` không thay thế constraint. |

Các lựa chọn trên là hướng suy luận, không phải cấu hình mặc định áp dụng giống nhau cho mọi DBMS. Ví dụ:

- **PostgreSQL:** `READ COMMITTED` dùng snapshot theo câu lệnh; `REPEATABLE READ` dùng snapshot ổn định cho giao dịch; `SERIALIZABLE` bổ sung phát hiện xung đột có thể dẫn đến serialization failure.
- **MySQL InnoDB:** hỗ trợ MVCC cho consistent read và các dạng row/next-key/gap lock tùy câu SQL, chỉ mục và mức cô lập. `SELECT` thường và locking read (`FOR UPDATE`) có hành vi khác nhau.
- **SQL Server:** `READ COMMITTED` có thể dùng khóa đọc truyền thống hoặc row versioning khi bật `READ_COMMITTED_SNAPSHOT`; chế độ `SNAPSHOT` là một lựa chọn riêng.
- **Oracle Database:** dùng cơ chế read consistency dựa trên phiên bản; tập isolation level hỗ trợ và chi tiết xử lý không giống nguyên xi PostgreSQL hay InnoDB.

Vì vậy, khi triển khai thật, cần kiểm tra **DBMS, phiên bản, storage engine, cấu hình isolation mặc định, loại câu SQL và chỉ mục** thay vì chỉ dựa vào tên mức cô lập.

## 8. Nguyên tắc triển khai an toàn

1. **Xác định bất biến nghiệp vụ trước.** “Số lượng không âm”, “không bán vượt tồn” và “luôn có một bác sĩ trực” đòi hỏi cách bảo vệ khác nhau.
2. **Đưa thao tác liên quan vào cùng transaction.** Kiểm tra điều kiện ở giao dịch này rồi cập nhật ở giao dịch khác tạo khoảng trống để dữ liệu thay đổi.
3. **Ưu tiên SQL nguyên tử và constraint khi diễn đạt được.** Chúng làm giảm khoảng thời gian giữa đọc và ghi; constraint còn bảo vệ khỏi các luồng ứng dụng khác.
4. **Chỉ khóa những gì cần khóa, trong thời gian ngắn nhất hợp lý.** Tránh gọi HTTP, chờ tương tác người dùng hoặc làm tác vụ chậm khi đang giữ khóa giao dịch.
5. **Thiết kế đường xử lý lỗi đồng thời.** Deadlock, timeout, conflict của optimistic lock và serialization failure là kết quả có thể xảy ra khi cạnh tranh tài nguyên. Retry có giới hạn cần chạy lại **toàn bộ transaction**, đọc lại dữ liệu và tránh lặp tác dụng bên ngoài (gửi email, trừ tiền ở dịch vụ khác) nếu thao tác chưa có cơ chế idempotency.
6. **Dùng thử nghiệm hai phiên kết nối để xác nhận hành vi.** Chạy đúng isolation level và câu SQL thực tế, quan sát kết quả sau `COMMIT`/`ROLLBACK`; không chỉ dựa vào mô phỏng một luồng.
7. **Theo dõi lock wait, deadlock và giao dịch dài.** Khi độ trễ tăng, nguyên nhân có thể là phạm vi khóa, thứ tự truy cập, thiếu chỉ mục hoặc snapshot tồn tại quá lâu, chứ không nhất thiết do câu truy vấn tính toán chậm.

## 9. Tổng kết kiến thức

**Khóa** bảo vệ tài nguyên trước thao tác xung đột; **MVCC** giúp tạo góc nhìn dữ liệu phù hợp để nhiều hoạt động đọc/ghi có thể cùng tiến hành; **isolation level** quy định mức bảo đảm mà toàn bộ giao dịch phải đạt được. Ba cơ chế bổ sung cho nhau, và mức cô lập được chọn phải xuất phát từ **ràng buộc nghiệp vụ** cùng hành vi của DBMS cụ thể.

Một giao dịch “đọc nhất quán” vẫn có thể đưa ra quyết định sai khi nhiều giao dịch cùng thay đổi các hàng khác nhau. Ngược lại, một câu `UPDATE` nguyên tử có điều kiện đôi khi đủ để bảo vệ một hàng mà không cần mức cô lập cao nhất. Khi thiết kế xử lý đồng thời, hãy hỏi: **đang bảo vệ giá trị của một hàng, một điều kiện trên nhiều hàng, hay tính tương đương tuần tự của cả giao dịch?** Câu trả lời quyết định khi nào dùng khóa, phiên bản, constraint và `SERIALIZABLE`.
