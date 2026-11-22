# Viết bất biến dữ liệu trước khi chọn cơ chế đồng thời

Khi nhiều giao dịch cùng thay đổi dữ liệu, câu hỏi quan trọng đầu tiên không phải là nên dùng khóa hàng, mức cô lập nào hay optimistic concurrency control (OCC). Câu hỏi đầu tiên là: **trạng thái dữ liệu nào được phép tồn tại sau khi giao dịch hoàn tất?** Quy tắc đó được gọi là **bất biến nghiệp vụ (business invariant)**.

Bất biến mô tả điều kiện phải luôn đúng đối với trạng thái được commit của hệ thống. Ví dụ: mỗi email chỉ thuộc về một tài khoản; số lượng tồn kho không âm; một phòng không được có hai đặt chỗ chồng thời gian; hoặc luôn có ít nhất một bác sĩ trực. Khi viết rõ bất biến, ta mới biết giao dịch cần đọc và thay đổi dữ liệu nào, những thao tác nào có thể xung đột và DBMS cần bảo vệ phạm vi nào.

Nếu chọn cơ chế đồng thời trước khi hiểu bất biến, hệ thống dễ bảo vệ nhầm một hàng trong khi quy tắc thực tế liên quan đến nhiều hàng, nhiều bảng hoặc cả một khoảng giá trị. Một khóa có thể khiến các giao dịch chờ nhau nhưng vẫn không bảo vệ đúng quy tắc; ngược lại, một ràng buộc dữ liệu có thể giải quyết hoàn toàn vấn đề mà không cần khóa ứng dụng phức tạp.

## 1. Bất biến là điều kiện trên trạng thái đã commit

Gọi trạng thái cơ sở dữ liệu tại một thời điểm là `S`. Một bất biến có thể được mô tả bằng vị từ `I(S)`, trong đó:

- `I(S) = true`: trạng thái thỏa mãn quy tắc nghiệp vụ.
- `I(S) = false`: trạng thái vi phạm quy tắc và không được phép commit.

Ví dụ:

| Quy tắc nghiệp vụ | Cách mô tả bất biến |
|---|---|
| Mỗi SKU chỉ có một sản phẩm trong một tenant | Không tồn tại hai hàng `Product` có cùng `(tenant_id, sku)` |
| Tồn kho không âm | Với mọi sản phẩm/kho, `quantity >= 0` |
| Một phòng không có hai booking chồng thời gian | Các khoảng thời gian đặt phòng của cùng phòng không giao nhau |
| Luôn có ít nhất một bác sĩ trực | Tổng số bác sĩ có `on_call = true` luôn lớn hơn hoặc bằng 1 |
| Hạn mức tín dụng không bị vượt | Tổng dư nợ đang tính hạn mức của khách hàng không lớn hơn `credit_limit` |
| Một đơn hàng chỉ được thanh toán một lần | Mỗi `order_id` có tối đa một giao dịch thanh toán thành công theo định danh nghiệp vụ |

Bất biến nói về trạng thái được chấp nhận, không nhất thiết yêu cầu mọi bước trung gian trong transaction đều thỏa điều kiện. Một transaction có thể tạm thời chuyển trạng thái qua các bước trung gian rồi khôi phục điều kiện trước khi commit. Với một số ràng buộc, DBMS hỗ trợ kiểm tra trì hoãn đến cuối transaction; với ràng buộc khác, cần sắp xếp câu lệnh theo cách không vi phạm ở từng bước.

### Bất biến khác với kiểm tra giao diện

Việc ẩn nút “Đặt chỗ” khi phòng đã có lịch không bảo vệ dữ liệu. Hai người dùng có thể mở trang khi phòng còn trống và gửi yêu cầu gần như đồng thời. Kiểm tra ở giao diện chỉ cải thiện trải nghiệm; bất biến phải được bảo vệ ở nơi mọi đường ghi đều đi qua, thường là cơ sở dữ liệu hoặc một dịch vụ ghi duy nhất có cơ chế đồng thời đúng.

Tương tự, đoạn code sau không tự bảo đảm tính duy nhất:

```java
if (!repository.existsByEmail(email)) {
    repository.save(new User(email));
}
```

Hai request có thể cùng nhận `false` từ `existsByEmail` trước khi request nào ghi dữ liệu. Cơ sở dữ liệu vẫn cần unique constraint trên email; ứng dụng có thể chuyển lỗi duplicate key thành phản hồi nghiệp vụ phù hợp.

## 2. Viết bất biến đủ cụ thể để có thể kiểm chứng

Một câu mô tả như “không được bán quá số lượng hiện có” chưa đủ để thiết kế cơ chế đồng thời. Cần xác định rõ các yếu tố:

1. **Đối tượng:** bất biến áp dụng cho sản phẩm, kho, khách hàng, tài khoản, phòng hay tenant nào?
2. **Phạm vi:** một hàng, một nhóm hàng, một bảng, một khoảng thời gian hay tổng hợp nhiều nguồn?
3. **Thời điểm:** điều kiện phải đúng sau từng câu lệnh, khi commit hay sau một quy trình bất đồng bộ?
4. **Trạng thái được tính:** những trạng thái nào được tính vào tổng? Ví dụ booking `CANCELLED` có chiếm phòng không?
5. **Định lượng:** điều kiện là bằng, lớn hơn, không âm, tối đa một hay không có khoảng giao nhau?
6. **Ngoại lệ:** có vai trò quản trị hoặc quy trình bù trừ nào được phép phá vỡ quy tắc không?
7. **Nguồn sự thật:** dữ liệu nào là canonical khi có cache, bản sao đọc hoặc hệ thống bên ngoài?

Ví dụ, hãy cụ thể hóa quy tắc đặt phòng:

> Với cùng `room_id`, hai booking có trạng thái `PENDING` hoặc `CONFIRMED` không được có khoảng thời gian lưu trú giao nhau. Booking đã `CANCELLED` không chiếm phòng.

Định nghĩa khoảng thời gian là `[check_in, check_out)`, tức bao gồm thời điểm nhận phòng và không bao gồm thời điểm trả phòng. Nhờ vậy, booking A trả phòng lúc 11:00 và booking B nhận phòng lúc 11:00 không bị xem là chồng lấn. Nếu không định nghĩa biên khoảng, các nhóm phát triển có thể triển khai những phép kiểm tra khác nhau.

### Mô tả bằng điều kiện hoặc công thức

Một số bất biến có thể viết thành biểu thức:

```text
UNIQUE(tenant_id, sku)

quantity(warehouse, product) >= 0

COUNT(active_doctors) >= 1

SUM(open_debt(customer)) <= credit_limit(customer)

Không tồn tại hai booking B1, B2:
  B1.room_id = B2.room_id
  AND B1 và B2 đều đang chiếm phòng
  AND B1.check_in < B2.check_out
  AND B2.check_in < B1.check_out
```

Biểu thức giúp nhận ra bất biến đang nói về một giá trị, một tập hàng hay một quan hệ giữa nhiều hàng. Đây là bước quan trọng để quyết định có thể dùng constraint trực tiếp hay phải điều phối giao dịch.

## 3. Phân loại phạm vi bất biến

Phạm vi của bất biến quyết định công cụ nào có thể bảo vệ nó.

| Phạm vi | Ví dụ | Cơ chế thường phù hợp |
|---|---|---|
| Một hàng | `quantity >= 0`, `price >= 0` | `CHECK`, `NOT NULL`, kiểu dữ liệu, atomic UPDATE |
| Một khóa duy nhất | Một email hoặc SKU chỉ xuất hiện một lần | `PRIMARY KEY`, `UNIQUE` |
| Quan hệ giữa hai bảng | Mọi `order.customer_id` phải tham chiếu khách hàng tồn tại | `FOREIGN KEY` |
| Nhiều hàng trong cùng nhóm | Tổng tồn kho, số bác sĩ trực, hạn mức tín dụng | Aggregate/guard row, transaction, isolation, khóa hoặc thiết kế lại mô hình |
| Khoảng giá trị/thời gian | Booking không chồng lấn, không có hai hiệu lực cùng phạm vi | Exclusion/range constraint nếu hỗ trợ, hoặc cơ chế tuần tự hóa phù hợp |
| Nhiều bảng hoặc nhiều hệ thống | Đơn hàng và thanh toán phải đồng bộ | Transaction trong một DB; workflow/outbox/saga khi qua nhiều hệ thống |

Không phải mọi bất biến đều có thể biểu diễn bằng một `CHECK`. Trong SQL, `CHECK` thông thường kiểm tra biểu thức trên hàng hiện tại; nó không phải công cụ tổng quát để chạy truy vấn `COUNT(*)` hoặc `SUM(...)` trên các hàng khác. Dùng trigger hoặc stored procedure cũng không tự động giải quyết race condition nếu logic bên trong không có khóa hoặc isolation phù hợp.

## 4. Ưu tiên constraint khi DBMS có thể bảo vệ trực tiếp

Constraint là hàng rào do DBMS thực thi cho mọi đường ghi vào bảng, kể cả ứng dụng, batch, script quản trị hoặc dịch vụ khác. Nếu bất biến có thể biểu diễn bằng constraint, đây thường là cơ chế rõ ràng và đáng tin cậy nhất.

### 4.1. CHECK cho điều kiện trên một hàng

Ví dụ số lượng và giá không âm:

```sql
CREATE TABLE ProductStock (
    product_id BIGINT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT ck_stock_nonnegative CHECK (quantity >= 0),
    PRIMARY KEY (product_id, warehouse_id)
);
```

Constraint này ngăn mọi câu lệnh ghi một giá trị âm, bất kể câu lệnh đến từ ứng dụng nào. Tuy nhiên, nó không tự ngăn việc bán vượt tồn kho nếu câu lệnh tính toán sai rồi ghi một số dương không chính xác. Quy tắc “không trừ nhiều hơn số lượng hiện có” cần được bảo vệ ngay tại thao tác cập nhật.

### 4.2. UNIQUE cho tính duy nhất

```sql
CREATE TABLE AppUser (
    user_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(255) NOT NULL,
    CONSTRAINT uq_user_tenant_email UNIQUE (tenant_id, email)
);
```

Nếu hai transaction cùng tạo email cho một tenant, unique constraint quyết định một thao tác thành công và thao tác kia nhận xung đột. Ứng dụng có thể bắt lỗi unique violation và trả về thông báo “email đã được sử dụng”. Không cần tự khóa toàn bảng chỉ để kiểm tra email trùng.

### 4.3. FOREIGN KEY cho quan hệ tham chiếu

```sql
ALTER TABLE Orders
ADD CONSTRAINT fk_order_customer
FOREIGN KEY (customer_id)
REFERENCES Customer(customer_id);
```

Foreign key bảo vệ quan hệ tồn tại giữa hàng con và hàng cha. Nó cũng tham gia vào cơ chế khóa/đồng thời của DBMS khi chèn, xóa hoặc cập nhật khóa tham chiếu. Nếu xóa khách hàng trong khi đơn hàng mới được tạo, DBMS điều phối dựa trên ràng buộc và chính sách `ON DELETE`.

### 4.4. Ràng buộc khoảng và thời gian

Một số DBMS có loại constraint mạnh hơn cho quan hệ giữa các hàng. PostgreSQL hỗ trợ exclusion constraint, thường kết hợp range type và toán tử overlap `&&` để ngăn hai booking đang hoạt động của cùng phòng có khoảng thời gian giao nhau:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_booking (
    booking_id BIGINT PRIMARY KEY,
    room_id BIGINT NOT NULL,
    stay_period TSRANGE NOT NULL,
    status TEXT NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        stay_period WITH &&
    ) WHERE (status IN ('PENDING', 'CONFIRMED'))
);
```

Đây là ví dụ riêng cho PostgreSQL; `btree_gist` cung cấp operator class cần thiết cho phép so sánh equality của `room_id` trong GiST. `TSRANGE` có thể biểu diễn khoảng thời gian với quy tắc biên được chọn. Cú pháp và kiểu dữ liệu này không dùng nguyên trạng trên MySQL hoặc SQL Server.

Khi DBMS không có constraint tương đương, cần xác định cách bảo vệ khoảng: khóa một hàng đại diện cho phòng, dùng isolation `SERIALIZABLE` với predicate phù hợp, hoặc mô hình hóa lịch đặt thành các slot có unique key. Chỉ chạy `SELECT` kiểm tra overlap rồi `INSERT` là không đủ khi hai request có thể cùng kiểm tra trước khi ghi.

## 5. Dùng atomic DML khi bất biến có thể kiểm tra ngay trên hàng

Một số quy tắc không cần đọc trước rồi mới cập nhật. Có thể đưa điều kiện vào chính câu lệnh ghi để DBMS kiểm tra và thay đổi trong một thao tác nguyên tử.

Ví dụ bán một sản phẩm trong kho:

```sql
UPDATE ProductStock
SET quantity = quantity - :requested
WHERE product_id = :productId
  AND warehouse_id = :warehouseId
  AND :requested > 0
  AND quantity >= :requested;
```

Sau câu lệnh, ứng dụng kiểm tra số hàng bị ảnh hưởng:

- `1`: đã trừ tồn kho thành công.
- `0`: không có hàng phù hợp, hoặc số lượng hiện tại không đủ; cần phân biệt theo nghiệp vụ nếu cần.

Vì điều kiện `quantity >= :requested` và phép trừ nằm trong cùng câu UPDATE, hai transaction không thể cùng dựa trên một lần đọc cũ rồi cùng làm tồn kho âm. DBMS điều phối cập nhật cạnh tranh trên hàng đó.

Không nên viết thành hai bước không có bảo vệ:

```sql
SELECT quantity
FROM ProductStock
WHERE product_id = :productId
  AND warehouse_id = :warehouseId;

-- Ứng dụng kiểm tra quantity >= requested rồi mới UPDATE.
```

Giữa SELECT và UPDATE, giao dịch khác có thể trừ tồn kho. Nếu cần hiển thị số lượng hiện tại cho người dùng, vẫn có thể đọc trước để hiển thị; nhưng quyết định cuối cùng phải được kiểm tra lại trong câu lệnh ghi nguyên tử.

### Cập nhật có điều kiện theo version

Nếu bất biến là “chỉ chấp nhận cập nhật khi dữ liệu chưa đổi kể từ lúc người dùng đọc”, có thể dùng version column:

```sql
UPDATE Customer
SET address = :newAddress,
    version = version + 1
WHERE customer_id = :customerId
  AND version = :expectedVersion;
```

Nếu số hàng bị ảnh hưởng bằng 0, ứng dụng biết phiên bản đã thay đổi hoặc bản ghi không còn tồn tại. Đây là optimistic concurrency check. Nó bảo vệ cập nhật cạnh tranh trên hàng được kiểm tra; nó không tự bảo vệ bất biến tổng hợp nhiều hàng như “ít nhất một bác sĩ trực”.

## 6. Khi bất biến phụ thuộc nhiều hàng: xác định điểm điều phối

Bất biến nhiều hàng khó hơn vì mỗi transaction có thể đọc một tập dữ liệu, sau đó ghi các hàng khác nhau. Nếu chỉ khóa những hàng mà mỗi transaction cập nhật, hai transaction vẫn có thể cùng vượt qua kiểm tra trên snapshot cũ.

Ví dụ bất biến: luôn có ít nhất một bác sĩ trực.

| doctor_id | on_call |
|---:|---|
| 1 | TRUE |
| 2 | TRUE |

Hai transaction chạy đồng thời:

1. A đếm được hai bác sĩ trực, rồi tắt `on_call` của bác sĩ 1.
2. B cũng đếm được hai bác sĩ trực, rồi tắt `on_call` của bác sĩ 2.
3. A và B cập nhật hai hàng khác nhau nên khóa hàng trên hai hàng ghi không nhất thiết xung đột.
4. Cả hai commit và bất biến bị phá vỡ.

Đây là một dạng write skew. Để bảo vệ quy tắc, cần điều phối trên phạm vi rộng hơn các hàng ghi riêng lẻ.

### 6.1. Dùng SERIALIZABLE

Mức cô lập `SERIALIZABLE` yêu cầu DBMS bảo đảm kết quả giao dịch tương đương với một thứ tự tuần tự hợp lệ. DBMS có thể khóa predicate/range, phát hiện phụ thuộc hoặc dùng cơ chế khác tùy sản phẩm.

Mã giả:

```text
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE

đếm số bác sĩ đang trực
nếu số lượng sau khi tắt bác sĩ hiện tại sẽ nhỏ hơn 1:
    từ chối thay đổi
cập nhật trạng thái bác sĩ

COMMIT
```

Nếu hai transaction tạo ra write skew, DBMS có thể chặn một transaction hoặc hủy một transaction bằng lỗi serialization. Ứng dụng phải xử lý lỗi đó và có thể retry toàn bộ transaction sau khi đọc lại trạng thái mới.

Tên và cách triển khai mức `SERIALIZABLE` có thể khác nhau. PostgreSQL dùng Serializable Snapshot Isolation (SSI) để theo dõi các phụ thuộc nguy hiểm và có thể trả lỗi `serialization_failure`; SQL Server có locking/range-lock behavior ở isolation này. Không nên suy luận rằng mọi DBMS đều xử lý bằng cách khóa mọi hàng đọc.

### 6.2. Dùng guard row hoặc hàng tổng hợp

Một cách khác là tạo một hàng đại diện cho phạm vi nghiệp vụ cần điều phối. Ví dụ bảng `DutyRosterGuard` có một hàng cho mỗi khoa. Mọi transaction thay đổi trạng thái trực đều khóa hàng guard trước khi đếm và cập nhật:

```sql
BEGIN TRANSACTION;

SELECT roster_id
FROM DutyRosterGuard
WHERE roster_id = :rosterId
FOR UPDATE;

SELECT COUNT(*)
FROM DoctorDuty
WHERE roster_id = :rosterId
  AND on_call = TRUE;

-- Kiểm tra số bác sĩ còn trực sau thay đổi.
-- Chỉ UPDATE khi bất biến vẫn được giữ.

COMMIT;
```

`FOR UPDATE` là cú pháp phổ biến ở PostgreSQL và MySQL; cú pháp khóa hàng tương đương của SQL Server khác. Ví dụ chỉ minh họa mẫu thiết kế. Guard row phải tồn tại và mọi đường ghi có thể ảnh hưởng bất biến phải lấy cùng khóa trước khi đọc/ghi.

Guard row biến một quy tắc nhiều hàng thành một điểm điều phối chung. Nó dễ hiểu nhưng có thể trở thành điểm nóng nếu mọi thay đổi đều phải chờ cùng một hàng. Có thể chia guard theo khoa, phòng hoặc phạm vi nghiệp vụ nếu các nhóm độc lập.

### 6.3. Dùng advisory lock theo khóa nghiệp vụ

Nếu phạm vi điều phối là một tài nguyên logic không có hàng đại diện, có thể dùng advisory lock như `roster:department-7`. Mọi transaction thay đổi lịch trực của khoa đó lấy cùng khóa trước khi kiểm tra và cập nhật.

Advisory lock chỉ bảo vệ các luồng tuân thủ giao thức. Constraint hoặc cơ chế kiểm tra khác vẫn cần thiết nếu có đường ghi ngoài giao thức. Với công việc nằm trong một transaction, ưu tiên khóa transaction-scoped nếu DBMS hỗ trợ để commit/rollback tự giải phóng.

### 6.4. Dùng mô hình dữ liệu để làm bất biến dễ bảo vệ hơn

Đôi khi thay đổi mô hình dữ liệu tốt hơn thêm khóa. Ví dụ, thay vì tính tổng từ hàng nghìn giao dịch mỗi lần cấp tín dụng, hệ thống duy trì một hàng `CustomerCredit` có `used_amount` và `credit_limit`, rồi cập nhật có điều kiện:

```sql
UPDATE CustomerCredit
SET used_amount = used_amount + :newDebt
WHERE customer_id = :customerId
  AND used_amount + :newDebt <= credit_limit;
```

Hàng tổng hợp tạo ra một điểm kiểm tra nguyên tử cho hạn mức. Tuy nhiên, mọi khoản tăng/giảm dư nợ phải cập nhật hàng tổng hợp đúng transaction với ledger gốc. Nếu một đường ghi quên cập nhật `used_amount`, dữ liệu tổng hợp sẽ lệch. Có thể cần reconciliation định kỳ để phát hiện sai lệch.

## 7. Chọn cơ chế dựa trên loại bất biến

Sau khi mô tả bất biến, có thể chọn cơ chế theo bảng định hướng:

| Loại bất biến | Cơ chế đầu tiên nên xem xét | Khi nào cần cơ chế đồng thời bổ sung? |
|---|---|---|
| Giá trị hợp lệ trên một hàng | `CHECK`, `NOT NULL`, kiểu dữ liệu | Khi phép tính cập nhật dựa trên giá trị cũ; dùng atomic UPDATE |
| Tính duy nhất | `PRIMARY KEY`, `UNIQUE` | Khi cần hành vi insert-or-update; dùng UPSERT phù hợp |
| Tham chiếu tồn tại | `FOREIGN KEY` | Khi có quy tắc cascade hoặc thay đổi nhiều bảng cần transaction |
| Không vượt tồn kho | UPDATE có điều kiện và CHECK | Khi tồn kho phân tán nhiều hàng/kho hoặc có reservation phức tạp |
| Không vượt tổng hạn mức | Hàng tổng hợp/ledger + atomic update | Khi invariant được tính từ nhiều loại giao dịch hoặc nhiều nguồn |
| Không chồng lấn thời gian | Exclusion/range constraint nếu DBMS hỗ trợ | Nếu không có constraint tương đương, cần SERIALIZABLE hoặc guard/lock theo phạm vi |
| Ít nhất một thành viên còn hoạt động | SERIALIZABLE, guard row hoặc advisory lock | Khi nhiều transaction có thể thay đổi các hàng khác nhau |
| Một công việc logic chỉ có một owner | Unique key, lease hoặc advisory lock | Khi công việc kéo dài, cần timeout, heartbeat và phục hồi owner |
| Quy trình qua nhiều hệ thống | Outbox/saga/idempotency | Transaction DB không thể bao trùm commit của dịch vụ ngoài |

Thứ tự ưu tiên thực tế thường là:

1. Constraint trực tiếp nếu DBMS biểu diễn được bất biến.
2. Atomic DML nếu điều kiện có thể kiểm tra ngay tại hàng được cập nhật.
3. Transaction với khóa/guard khi cần điều phối một phạm vi xác định.
4. Isolation `SERIALIZABLE` hoặc cơ chế phát hiện xung đột khi phụ thuộc phức tạp và DBMS hỗ trợ phù hợp.
5. Thiết kế lại mô hình dữ liệu hoặc workflow nếu bất biến trải qua nhiều hệ thống hoặc công việc dài.

Đây là trình tự xem xét, không phải quy tắc cứng. Một hệ thống có thể kết hợp constraint với serializable hoặc guard row. Mục tiêu là bảo vệ đúng bất biến với chi phí và độ phức tạp phù hợp.

## 8. Đừng nhầm invariant với cơ chế triển khai

Một câu mô tả “dùng khóa hàng để tránh bán âm tồn kho” là lựa chọn triển khai, chưa phải bất biến. Bất biến phải độc lập với công cụ:

> Với mọi cặp `(product_id, warehouse_id)`, số lượng khả dụng sau mỗi transaction commit không âm.

Sau đó mới chọn cách triển khai: `CHECK (quantity >= 0)` và atomic UPDATE có điều kiện. Nếu sau này chuyển DBMS, bất biến vẫn giữ nguyên dù cú pháp hoặc cơ chế khóa thay đổi.

Tương tự:

- “Dùng SERIALIZABLE để bảo vệ lịch trực” là cơ chế.
- “Mỗi khoa luôn có ít nhất một bác sĩ được phân công trực trong mỗi khoảng thời gian vận hành” mới là bất biến.
- “Dùng advisory lock theo customer ID” là cơ chế.
- “Không có hai worker cùng tạo hóa đơn cho cùng khách hàng và kỳ kế toán” là quy tắc nghiệp vụ, có thể còn cần unique constraint để bảo vệ dữ liệu.

Tách hai lớp giúp tài liệu kiến trúc mô tả được lý do của quyết định kỹ thuật và giúp nhóm phát triển đánh giá lại khi tải hoặc DBMS thay đổi.

## 9. Transaction boundary phải bao phủ toàn bộ thay đổi liên quan

Một bất biến có thể bị phá vỡ nếu các bước cập nhật được commit ở những transaction độc lập. Ví dụ chuyển tiền giữa hai tài khoản:

```text
Trạng thái đầu:
  Account A = 1.000
  Account B = 500

Chuyển 200:
  trừ A 200
  cộng B 200

Trạng thái cuối mong muốn:
  Account A = 800
  Account B = 700
  tổng tiền không đổi
```

Hai cập nhật phải thuộc cùng một transaction:

```sql
BEGIN;

UPDATE Account
SET balance = balance - 200
WHERE account_id = 1
  AND balance >= 200;

-- Ứng dụng kiểm tra đúng một hàng được cập nhật.

UPDATE Account
SET balance = balance + 200
WHERE account_id = 2;

COMMIT;
```

Ví dụ rút gọn này cần kiểm tra số hàng bị ảnh hưởng của cả hai UPDATE và rollback nếu tài khoản không tồn tại hoặc bước nào thất bại. Có thể thêm `CHECK (balance >= 0)` để bảo vệ số dư không âm. Nếu có nhiều loại phí hoặc hạn mức, cần đưa chúng vào mô hình tính toán và transaction tương ứng.

Nếu cập nhật A commit trước rồi cập nhật B commit sau, lỗi giữa hai bước có thể làm tiền bị mất. Nếu hệ thống còn gọi ngân hàng hoặc payment provider bên ngoài, transaction DB không thể rollback giao dịch của provider; cần idempotency key, outbox hoặc saga/compensation để điều phối.

## 10. Kiểm tra bất biến dưới tải đồng thời

Một kiểm thử chạy tuần tự không đủ để chứng minh cơ chế đồng thời bảo vệ bất biến. Cần tạo các lịch thực thi có xen kẽ giữa các transaction.

Ví dụ với tồn kho ban đầu bằng 1 và hai yêu cầu cùng bán một sản phẩm:

```text
T1: Transaction A đọc quantity = 1
T2: Transaction B đọc quantity = 1
T3: A yêu cầu trừ 1
T4: B yêu cầu trừ 1
T5: A commit
T6: B tiếp tục hoặc bị từ chối

Kết quả hợp lệ:
  Chỉ một giao dịch bán thành công.
  quantity cuối = 0.
  Không có quantity âm.
```

Với bất biến nhiều hàng, cần tạo đúng tình huống write skew. Ví dụ hai transaction cùng đọc hai bác sĩ đang trực rồi mỗi transaction tắt một người. Kiểm thử phải xác nhận chỉ một transaction được commit hoặc có cơ chế điều phối khiến transaction thứ hai đọc lại trạng thái sau khi transaction đầu hoàn tất.

### Những điều nên quan sát

- Trạng thái dữ liệu cuối có thỏa biểu thức invariant không?
- Có transaction nào bị lỗi constraint, deadlock hoặc serialization failure không?
- Số lần retry và tỷ lệ retry thành công là bao nhiêu?
- Thời gian chờ khóa và độ trễ p95/p99 thay đổi ra sao?
- Có đường ghi nào không đi qua cơ chế bảo vệ không?
- Khi worker bị kill giữa chừng, transaction rollback và quyền sở hữu khóa có được giải phóng không?
- Khi request được gửi lặp sau timeout, kết quả có bị cộng/trừ hai lần không?

Nên kiểm thử cả trường hợp cùng khóa và khóa khác nhau. Một giải pháp bảo vệ đúng nhưng khóa toàn bộ tenant cho mọi thao tác có thể tạo bottleneck lớn không cần thiết.

## 11. Xử lý lỗi và retry theo bất biến

Các cơ chế đồng thời có thể từ chối một transaction vì nhiều lý do khác nhau:

| Lỗi | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Unique violation | Một hàng khác đã chiếm khóa duy nhất | Trả lỗi trùng, hoặc đọc hàng hiện có nếu nghiệp vụ cho phép |
| Check/FK violation | Dữ liệu vi phạm constraint | Thường là lỗi nghiệp vụ/dữ liệu; không retry vô điều kiện |
| Deadlock victim | Transaction bị hủy để phá chu trình chờ | Có thể retry toàn bộ transaction với giới hạn nếu thao tác an toàn |
| Serialization failure | DBMS từ chối lịch có nguy cơ không tuần tự hóa được | Rollback và retry toàn bộ transaction từ đầu |
| Optimistic version mismatch | Dữ liệu đã đổi so với phiên bản được đọc | Tải lại, hợp nhất thay đổi hoặc trả conflict cho người dùng |
| Lock timeout | Không lấy được tài nguyên trong thời hạn | Chờ lại có giới hạn, đưa job vào hàng đợi hoặc trả lỗi |

Không gom tất cả lỗi vào một nhánh retry. Constraint violation thường chỉ ra đầu vào không hợp lệ hoặc một quy tắc nghiệp vụ đã bị chiếm; retry ngay với cùng dữ liệu có thể lặp lại lỗi. Deadlock và serialization failure có thể là lỗi cạnh tranh tạm thời, nhưng retry vẫn cần giới hạn và phải chạy lại toàn bộ đơn vị nghiệp vụ.

Nếu transaction có tác động ngoài DB, phải đảm bảo retry không gửi email, thanh toán hoặc thông điệp nhiều lần. Transactional outbox và idempotency key giúp tách commit dữ liệu khỏi việc phát tác động bên ngoài.

## 12. Các câu hỏi cần trả lời trước khi chọn khóa

Trước khi viết `SELECT ... FOR UPDATE`, thêm advisory lock hoặc chuyển isolation level, hãy trả lời:

1. Trạng thái nào bị cấm? Viết thành biểu thức có thể kiểm tra.
2. Bất biến áp dụng trên một hàng, một khóa duy nhất, một tập hàng, một khoảng hay nhiều hệ thống?
3. DBMS có constraint trực tiếp cho quy tắc đó không?
4. Có thể gộp điều kiện kiểm tra và thay đổi thành một câu DML nguyên tử không?
5. Nếu nhiều hàng liên quan, phạm vi nào cần được điều phối: guard row, range/predicate hay toàn bộ transaction?
6. Mọi đường ghi có đi qua cùng giao thức không?
7. Transaction kéo dài bao lâu và giữ tài nguyên nào?
8. Nếu DBMS hủy transaction, ứng dụng xử lý lỗi và retry ra sao?
9. Nếu request được gửi lặp hoặc worker chết, trạng thái có phục hồi đúng không?
10. Có thể đo được cả tính đúng đắn lẫn chi phí đồng thời không?

## 13. Ví dụ tổng hợp: bảo vệ hạn mức tín dụng

Giả sử mỗi khách hàng có hạn mức tín dụng 10.000.000 đồng. Tổng các khoản nợ đang mở không được vượt hạn mức:

```text
SUM(open_debt for customer) <= credit_limit(customer)
```

Nếu ứng dụng chỉ đọc tổng nợ rồi kiểm tra trước khi INSERT khoản nợ mới, hai giao dịch có thể cùng thấy còn đủ hạn mức và cùng tạo khoản nợ, khiến tổng vượt giới hạn.

Có một số cách thiết kế:

**Cách A — Duy trì hàng tổng hợp và cập nhật có điều kiện.** Bảng `CustomerCredit` lưu `used_amount` và `credit_limit`. Một câu UPDATE tăng `used_amount` chỉ khi tổng mới không vượt giới hạn. INSERT ledger và UPDATE tổng hợp nằm trong cùng transaction. Cách này tạo điểm kiểm soát nguyên tử, nhưng phải bảo đảm mọi khoản nợ và hoàn trả đều cập nhật tổng hợp đúng cách.

**Cách B — Dùng SERIALIZABLE.** Transaction đọc tổng nợ, kiểm tra hạn mức và thêm khoản nợ. DBMS bảo đảm lịch tuần tự hợp lệ bằng khóa hoặc phát hiện xung đột. Ứng dụng phải xử lý serialization failure/deadlock và retry toàn bộ transaction.

**Cách C — Dùng guard row.** Mỗi khách hàng có một hàng đại diện. Transaction khóa hàng khách hàng trước khi tính tổng và ghi khoản nợ. Các giao dịch cùng khách hàng được tuần tự hóa; khách hàng khác vẫn có thể xử lý song song.

Lựa chọn phụ thuộc số lượng khoản nợ, tần suất cập nhật, độ trễ yêu cầu và khả năng duy trì dữ liệu tổng hợp. Dù chọn cách nào, bất biến không đổi: tổng nợ được tính theo đúng định nghĩa nghiệp vụ không được lớn hơn hạn mức đã được phê duyệt.

## 14. Kết luận thiết kế

Viết bất biến trước khi chọn cơ chế đồng thời giúp chuyển một yêu cầu nghiệp vụ thành điều kiện kỹ thuật có thể kiểm chứng. Khi biết chính xác phạm vi và thời điểm của điều kiện, ta có thể chọn constraint cho quy tắc dữ liệu trực tiếp, atomic DML cho cập nhật có điều kiện trên hàng, hoặc transaction/locking/serializable cho phụ thuộc nhiều hàng. Với workflow qua nhiều hệ thống, cần thêm idempotency, outbox hoặc cơ chế bù trừ.

Điều quan trọng là giữ bất biến làm tiêu chí đánh giá xuyên suốt: sau mọi lịch thực thi đồng thời được chấp nhận, trạng thái commit vẫn phải hợp lệ. Khóa, isolation level và OCC chỉ là những công cụ khác nhau để đạt điều kiện đó; chúng cần được lựa chọn sau khi quy tắc dữ liệu đã được mô tả rõ ràng.
