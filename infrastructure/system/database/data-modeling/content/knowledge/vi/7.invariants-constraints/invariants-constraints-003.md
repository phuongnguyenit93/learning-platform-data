# Quy tắc trong một bản ghi, trong một nhóm và giữa nhiều nhóm dữ liệu

Một cơ sở dữ liệu có thể chứa các giá trị đúng kiểu nhưng vẫn phản ánh một trạng thái nghiệp vụ sai. Ví dụ, số lượng của từng dòng hàng đều dương nhưng tổng số lượng đặt trước lại vượt tồn kho; từng khoản thanh toán đều hợp lệ nhưng tổng tiền thu lớn hơn số phải trả; từng hợp đồng đều có ngày bắt đầu trước ngày kết thúc nhưng hai hợp đồng lại chiếm dụng cùng một thiết bị trong cùng thời gian.

Trong **data modeling**, các điều kiện mà dữ liệu phải luôn tuân thủ được gọi là bất biến (invariant). Ràng buộc (constraint) là cơ chế giúp thực thi một phần hoặc toàn bộ các điều kiện đó. Khi thiết kế, cần xác định phạm vi của mỗi quy tắc: nó chỉ liên quan đến một bản ghi, một nhóm bản ghi có chung khóa, hay nhiều nhóm dữ liệu ở các bảng hoặc thực thể khác nhau.

Bài học này phân loại các quy tắc theo phạm vi, chỉ ra cơ chế phù hợp trong cơ sở dữ liệu quan hệ và cách bảo vệ chúng khi nhiều giao dịch chạy đồng thời. Ví dụ xuyên suốt là hệ thống bán hàng và quản lý tồn kho, nơi đơn hàng, dòng hàng, thanh toán, sản phẩm và lượng hàng được giữ chỗ phải luôn nhất quán.

## 1. Bất biến là gì và vì sao cần phân loại?

Bất biến là một điều kiện phải đúng trong mọi trạng thái dữ liệu được xem là hợp lệ. Nó có thể đến từ luật nghiệp vụ, hợp đồng, chính sách vận hành hoặc yêu cầu kỹ thuật.

Ví dụ:

- Số lượng của một dòng đơn hàng phải lớn hơn không.
- Mỗi mã đơn hàng chỉ thuộc về một đơn hàng.
- Một đơn hàng phải thuộc về một khách hàng tồn tại.
- Tổng tiền các dòng hàng phải khớp với tổng tiền đơn hàng theo quy tắc tính giá.
- Số lượng hàng đã giữ chỗ không được vượt quá lượng hàng có thể phân bổ.
- Tổng thanh toán đã ghi nhận không được vượt số tiền phải thu, trừ khi nghiệp vụ cho phép tiền trả thừa.
- Một thiết bị không thể được phân bổ cho hai hợp đồng có khoảng thời gian chồng lấn.

Các quy tắc có phạm vi khác nhau:

| Phạm vi | Đối tượng được kiểm tra | Ví dụ | Cơ chế thường dùng |
|---|---|---|---|
| Một bản ghi | Các cột trong cùng một hàng | quantity > 0 | NOT NULL, CHECK |
| Một nhóm bản ghi | Nhiều hàng có cùng khóa hoặc cùng phạm vi | Một đơn hàng không có hai dòng cùng line_no | PRIMARY KEY, UNIQUE, partial unique index |
| Nhiều nhóm dữ liệu | Nhiều bảng, nhóm hoặc thực thể liên quan | Tổng thanh toán không vượt số phải thu | Transaction, khóa, mức cô lập, constraint chuyên biệt |

Phân loại theo phạm vi giúp tránh đặt quy tắc sai chỗ. CHECK rất phù hợp để kiểm tra quantity dương trong một hàng, nhưng không thể tự bảo đảm tổng quantity của tất cả dòng hàng không vượt tồn kho. UNIQUE có thể ngăn trùng mã trong một bảng, nhưng không tự tính tổng công nợ của khách hàng trên nhiều đơn hàng.

Không phải bất biến nào cũng được thực thi bằng một constraint đơn lẻ. Điều cần thiết là xác định rõ điều kiện, nơi bảo vệ nó, mọi đường ghi có tuân thủ cùng cơ chế và cách phát hiện khi dữ liệu sai lệch.

## 2. Xác định bất biến từ nghiệp vụ

### 2.1. Viết quy tắc dưới dạng điều kiện kiểm chứng

Một câu như “đơn hàng phải hợp lệ” quá chung để triển khai. Hãy chuyển thành các điều kiện có thể kiểm tra:

- Mỗi đơn hàng có mã duy nhất.
- Mỗi dòng hàng có số thứ tự dương và thuộc một đơn hàng tồn tại.
- Số lượng dòng hàng lớn hơn không.
- Đơn giá tại thời điểm đặt hàng không âm.
- Đơn hàng đã xác nhận phải có ít nhất một dòng hàng.
- Tổng tiền đã chốt bằng tổng các thành phần theo quy tắc thuế, phí và chiết khấu.
- Chỉ đơn hàng ở trạng thái được phép mới có thể ghi nhận thanh toán.

Quy tắc cần xác định cả thời điểm áp dụng. Ví dụ, đơn hàng nháp có thể chưa có dòng hàng, nhưng đơn hàng được xác nhận phải có ít nhất một dòng. Nếu chỉ đặt điều kiện “đơn hàng luôn có dòng hàng”, hệ thống sẽ khó tạo đơn hàng từng bước.

### 2.2. Phân biệt bất biến với quy tắc giao diện

Một trường bắt buộc trên màn hình không nhất thiết là bất biến dữ liệu. Một trường có thể được nhập ở bước sau hoặc được lấy từ nguồn tích hợp. Ngược lại, một bất biến quan trọng như mã đơn hàng duy nhất không được chỉ kiểm tra bằng JavaScript ở giao diện.

Hãy hỏi:

- Nếu một dịch vụ khác ghi trực tiếp vào cơ sở dữ liệu, quy tắc có còn được giữ không?
- Nếu hai yêu cầu cùng ghi tại một thời điểm, quy tắc có thể bị vi phạm không?
- Nếu một tiến trình bị dừng giữa chừng, dữ liệu có còn ở trạng thái hợp lệ không?
- Nếu import dữ liệu cũ, có thể phát hiện và cách ly các hàng không hợp lệ không?

Những câu hỏi này giúp chọn đúng lớp thực thi. Quy tắc cần được bảo vệ trước mọi đường ghi phải được đặt ở cơ sở dữ liệu hoặc một cơ chế dùng chung có đảm bảo tương đương.

### 2.3. Ghi rõ chủ sở hữu của bất biến

Mỗi bất biến cần có nơi chịu trách nhiệm. Ví dụ, tính duy nhất của mã đơn hàng do bảng orders bảo vệ bằng UNIQUE. Quy tắc giữ chỗ tồn kho có thể do transaction của dịch vụ đặt hàng bảo vệ bằng cập nhật nguyên tử và khóa hàng. Việc tính tổng tiền có thể được thực thi khi chốt đơn hàng và kiểm tra bằng quy trình đối soát.

Nếu cùng một quy tắc được triển khai khác nhau ở nhiều dịch vụ, các cách hiểu có thể lệch nhau. Hãy ghi lại định nghĩa chuẩn, cơ chế bảo vệ và các luồng ghi được phép.

## 3. Quy tắc trong một bản ghi

Quy tắc trong một bản ghi chỉ cần xem các giá trị thuộc cùng một hàng. Đây là phạm vi đơn giản nhất để dùng constraint trực tiếp.

### 3.1. NOT NULL và miền giá trị

NOT NULL yêu cầu cột phải có giá trị. Nó phù hợp với thuộc tính bắt buộc như mã đơn hàng, thời điểm tạo hoặc số lượng.

CHECK kiểm tra một biểu thức trên hàng. Ví dụ:

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    discount_amount NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (discount_amount >= 0),
    CHECK (discount_amount <= quantity * unit_price)
);
~~~

Các điều kiện trên ngăn số lượng bằng không hoặc âm, giá âm và chiết khấu lớn hơn thành tiền trước chiết khấu của dòng hàng.

CHECK thường có ba giá trị logic trong SQL: TRUE, FALSE và UNKNOWN. Một biểu thức CHECK có kết quả UNKNOWN do NULL thường không bị xem là FALSE. Vì vậy, nếu quantity bắt buộc phải có giá trị, cần cả NOT NULL và CHECK (quantity > 0). Chỉ có CHECK không thay thế được NOT NULL.

### 3.2. Quan hệ giữa các cột trong cùng hàng

Một số quy tắc so sánh hai cột:

~~~sql
CREATE TABLE promotions (
    promotion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    discount_percent NUMERIC(5, 2) NOT NULL
        CHECK (discount_percent BETWEEN 0 AND 100),
    CHECK (ends_at > starts_at)
);
~~~

Điều kiện ends_at lớn hơn starts_at chỉ cần dữ liệu của một hàng nên có thể dùng CHECK.

Tương tự, một bảng đo lường có thể kiểm tra minimum_value không lớn hơn maximum_value. Một bảng địa chỉ có thể yêu cầu country_code và postal_code cùng có mặt theo chính sách từng quốc gia, nhưng nếu điều kiện phụ thuộc bảng danh mục quốc gia thì cần cơ chế bổ sung.

### 3.3. DEFAULT không thay thế ràng buộc

DEFAULT cung cấp giá trị khi lệnh INSERT không chỉ định cột. Nó không ngăn ứng dụng ghi một giá trị khác và cũng không bảo đảm giá trị luôn hợp lệ.

Ví dụ, status có DEFAULT 'draft' nhưng vẫn cần CHECK hoặc bảng danh mục để chỉ cho phép trạng thái hợp lệ. Nếu nghiệp vụ quy định trạng thái chỉ được chuyển theo một luồng cụ thể, CHECK chỉ kiểm tra tập giá trị; nó không bảo vệ được lịch sử chuyển trạng thái.

### 3.4. NULL phải có ý nghĩa rõ

NULL có thể biểu thị chưa biết, chưa được cung cấp hoặc chưa phát sinh. Không nên dùng NULL thay cho mọi trạng thái đặc biệt.

Ví dụ:

- returned_at là NULL vì hàng chưa được trả.
- verified_at là NULL vì email chưa được xác minh.
- cancelled_at là NULL vì đơn hàng chưa bị hủy.

Nếu có nhiều ý nghĩa khác nhau, cần trạng thái hoặc thuộc tính riêng. Khi so sánh NULL, dùng IS NULL hoặc IS NOT NULL; biểu thức = NULL không hoạt động như so sánh giá trị thông thường.

## 4. Quy tắc trong một nhóm bản ghi

Một nhóm là tập các hàng có chung phạm vi nghiệp vụ, thường được xác định bằng một khóa như order_id, customer_id, tenant_id hoặc product_id. Quy tắc ở phạm vi này liên quan đến nhiều hàng cùng nhóm.

### 4.1. PRIMARY KEY và UNIQUE

PRIMARY KEY bảo đảm định danh hàng là duy nhất và không NULL. UNIQUE bảo vệ tính duy nhất của một cột hoặc tổ hợp cột.

Ví dụ, mỗi đơn hàng có nhiều dòng nhưng số thứ tự dòng không được trùng trong cùng đơn:

~~~sql
CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Khóa ghép (order_id, line_no) bảo vệ quy tắc line_no duy nhất trong từng đơn hàng. Hai đơn hàng khác nhau có thể cùng có line_no = 1.

Nếu mã sản phẩm chỉ duy nhất trong từng nhà cung cấp, có thể dùng UNIQUE (supplier_id, supplier_product_code). Đưa phạm vi vào khóa giúp tránh áp đặt tính duy nhất toàn cục khi nghiệp vụ không yêu cầu.

### 4.2. Partial unique index

Đôi khi chỉ các hàng đang hoạt động mới cần duy nhất. Ví dụ, một khách hàng có thể có nhiều email trong lịch sử nhưng chỉ có một email chính đang hoạt động:

~~~sql
CREATE UNIQUE INDEX uq_customer_primary_email
ON customer_emails (customer_id)
WHERE is_primary = TRUE AND active = TRUE;
~~~

Đây là cú pháp partial index được hỗ trợ bởi một số hệ quản trị, trong đó có PostgreSQL. Cần kiểm tra khả năng tương đương của hệ quản trị được chọn.

Partial unique index phù hợp với quy tắc duy nhất có điều kiện. Nó không tự bảo đảm mỗi khách hàng phải có ít nhất một email chính; quy tắc tồn tại tối thiểu thường cần xử lý ở transaction hoặc cơ chế khác.

### 4.3. Quy tắc về số lượng hàng trong nhóm

Một đơn hàng đã xác nhận cần có ít nhất một dòng hàng. Đây là quy tắc đếm số hàng trong nhóm order_id.

CHECK trên orders không thể dùng truy vấn con để đếm order_lines theo cách portable. Một cách triển khai phổ biến là kiểm tra khi chuyển trạng thái đơn hàng sang confirmed, trong cùng transaction:

~~~sql
BEGIN;

-- Khóa hàng đơn hàng để tuần tự hóa việc sửa và chốt đơn.
SELECT order_id
FROM orders
WHERE order_id = :order_id
FOR UPDATE;

-- Ứng dụng hoặc thủ tục kiểm tra số dòng.
SELECT COUNT(*)
FROM order_lines
WHERE order_id = :order_id;

-- Chỉ chuyển trạng thái nếu số dòng lớn hơn 0.
UPDATE orders
SET status = 'confirmed',
    confirmed_at = now()
WHERE order_id = :order_id
  AND status = 'draft';

COMMIT;
~~~

Đây là luồng minh họa; triển khai thực tế cần bảo đảm mọi thao tác thêm/xóa dòng hàng cũng khóa hoặc kiểm tra cùng hàng orders theo một giao thức nhất quán. Nếu không, một transaction khác có thể xóa dòng cuối cùng sau khi kiểm tra nhưng trước khi chốt đơn.

### 4.4. Quy tắc tổng hoặc giới hạn trong nhóm

Một nhóm có thể cần tổng số lượng không vượt một giới hạn. Ví dụ, một phiếu phân bổ có giới hạn 100 đơn vị, tổng số lượng các dòng không được vượt 100.

Không thể chỉ dùng CHECK trên từng dòng vì mỗi dòng riêng lẻ có thể hợp lệ trong khi tổng của nhóm vượt giới hạn. Có thể bảo vệ bằng một hàng tổng hợp đại diện cho nhóm:

- Lưu allocated_quantity trên hàng allocation_batch.
- Cập nhật tổng và thêm dòng chi tiết trong cùng transaction.
- Đặt CHECK (allocated_quantity BETWEEN 0 AND capacity) trên hàng tổng hợp.
- Dùng khóa hàng allocation_batch để tuần tự hóa các cập nhật cùng nhóm.

Giá trị tổng hợp là dữ liệu dẫn xuất hoặc được cập nhật đồng thời với chi tiết. Cần có cách đối soát để phát hiện nếu tổng trên hàng cha lệch tổng các dòng con.

### 4.5. Quy tắc khoảng thời gian không chồng lấn

Một nhóm có thể có quy tắc các khoảng thời gian không được giao nhau. Ví dụ, một phòng họp không thể được đặt hai lần trong cùng thời gian. Trong PostgreSQL, exclusion constraint kết hợp range type có thể bảo vệ quy tắc này:

~~~sql
-- Minh họa PostgreSQL; cần extension btree_gist cho phép so sánh room_id.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_bookings (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id BIGINT NOT NULL,
    booking_period TSTZRANGE NOT NULL,
    status VARCHAR(20) NOT NULL,
    CHECK (NOT isempty(booking_period)),
    EXCLUDE USING GIST (
        room_id WITH =,
        booking_period WITH &&
    )
    WHERE (status IN ('confirmed', 'in_progress'))
);
~~~

Toán tử && kiểm tra hai khoảng có giao nhau hay không. Exclusion constraint ngăn các hàng có cùng room_id và khoảng thời gian chồng lấn trong các trạng thái chiếm dụng. Cú pháp và khả năng hỗ trợ phụ thuộc hệ quản trị; không nên coi đây là SQL chuẩn có ở mọi cơ sở dữ liệu.

Nếu không có constraint chuyên biệt, có thể dùng transaction và khóa một hàng đại diện cho tài nguyên (phòng hoặc thiết bị) trước khi kiểm tra lịch. Mọi luồng ghi lịch phải tuân thủ cùng giao thức.

## 5. Quy tắc giữa nhiều nhóm hoặc nhiều bảng

Một bất biến liên bảng thường kết hợp dữ liệu từ nhiều thực thể hoặc nhóm. Ví dụ:

- Tổng các dòng hàng phải bằng tổng tiền đơn hàng.
- Tổng tiền đã thanh toán không vượt số phải thu.
- Tổng lượng hàng đã giữ chỗ không vượt lượng có thể phân bổ.
- Tổng hạn mức tín dụng đang sử dụng của khách hàng không vượt hạn mức.
- Một thiết bị không được vừa được phân bổ cho hợp đồng vừa nằm trong khoảng bảo trì.

Các quy tắc này khó hơn vì nhiều transaction có thể cùng tác động đến các hàng khác nhau.

### 5.1. Khóa ngoại bảo vệ quan hệ tham chiếu

Foreign key bảo đảm giá trị tham chiếu tồn tại ở bảng được tham chiếu. Ví dụ, mỗi order_line phải trỏ đến một order tồn tại và một product tồn tại.

~~~sql
CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    order_number VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE order_lines (
    order_line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Foreign key bảo vệ sự tồn tại của hàng được tham chiếu, nhưng không tự bảo đảm một order có ít nhất một line, tổng tiền đúng hoặc sản phẩm đang còn hàng.

Chính sách ON DELETE cũng là một phần của mô hình. CASCADE có thể phù hợp với dữ liệu phụ thuộc hoàn toàn như một số bảng nháp, nhưng có thể phá hủy lịch sử nếu áp dụng cho đơn hàng đã thanh toán. RESTRICT hoặc soft delete thường phù hợp hơn với dữ liệu giao dịch cần kiểm toán.

### 5.2. Tổng tiền đơn hàng và các dòng hàng

Giả sử orders lưu grand_total, còn order_lines lưu quantity, unit_price và discount. Bất biến là:

**grand_total = tổng thành tiền các dòng + thuế + phí - giảm giá cấp đơn**

Có hai cách chính:

1. Không lưu grand_total và tính từ các dòng mỗi lần đọc.
2. Lưu grand_total để truy vấn nhanh hoặc chụp giá trị đã chốt, đồng thời cập nhật trong cùng transaction và có cơ chế đối soát.

Nếu lưu tổng, không nên để mỗi dịch vụ tự tính theo một công thức riêng. Hãy xác định quy tắc làm tròn, thời điểm chốt, cách xử lý thuế và chiết khấu. Khi đơn hàng đã xác nhận, có thể khóa sửa dòng hoặc tạo điều chỉnh mới thay vì âm thầm thay đổi số tiền lịch sử.

Một cách kiểm tra khi chốt đơn:

~~~sql
BEGIN;

SELECT order_id
FROM orders
WHERE order_id = :order_id
FOR UPDATE;

-- Tính tổng từ các dòng và các khoản phụ phí/thuế.
SELECT SUM(quantity * unit_price - discount_amount)
FROM order_lines
WHERE order_id = :order_id;

-- Thủ tục hoặc ứng dụng áp dụng cùng quy tắc làm tròn,
-- ghi grand_total và chuyển trạng thái trong transaction.

COMMIT;
~~~

Truy vấn SUM ở trên chỉ tính thành tiền các dòng sau chiết khấu dòng; thuế, phí và giảm giá cấp đơn phải được cộng hoặc trừ theo quy tắc riêng. Đoạn SQL minh họa điểm tuần tự hóa. Trong triển khai thực tế, cần xử lý đơn không có dòng và bảo đảm các thao tác sửa dòng cùng khóa hàng cha.

### 5.3. Tổng thanh toán không vượt số phải thu

Giả sử một đơn hàng có số tiền phải thu là 1.000.000 VND và có nhiều lần thanh toán. Bất biến có thể là tổng các payment đã capture không vượt amount_due. Nếu chấp nhận trả thừa hoặc đặt cọc, quy tắc cần được diễn đạt khác.

Ví dụ dưới đây giả định bảng orders có các cột amount_due và amount_paid; amount_paid là tổng hợp được cập nhật trong cùng transaction với từng payment.

Một cách triển khai là khóa hàng orders trước khi ghi payment:

~~~sql
BEGIN;

SELECT amount_due, amount_paid
FROM orders
WHERE order_id = :order_id
FOR UPDATE;

-- Kiểm tra amount_paid + :new_payment <= amount_due.
-- Nếu hợp lệ, thêm payment và cập nhật amount_paid.

COMMIT;
~~~

Khóa hàng orders giúp các lần ghi thanh toán cho cùng đơn được tuần tự hóa, miễn là mọi đường ghi đều tuân thủ giao thức này. Có thể dùng một cột amount_paid tổng hợp để kiểm tra nhanh, nhưng cần cập nhật cùng transaction với payment và đối soát với tổng các payment hợp lệ.

### 5.4. Tồn kho và lượng giữ chỗ

Tồn kho là ví dụ điển hình của bất biến giữa nhiều nhóm. Giả sử:

- on_hand là số lượng đang có.
- reserved là số lượng đã giữ chỗ.
- available = on_hand - reserved.

Các điều kiện:

- on_hand >= 0.
- reserved >= 0.
- reserved <= on_hand.

Nếu lưu on_hand và reserved trên cùng một hàng inventory_balance, CHECK có thể bảo vệ các quan hệ này trong một bản ghi:

~~~sql
CREATE TABLE inventory_balances (
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    warehouse_id BIGINT NOT NULL REFERENCES warehouses(warehouse_id),
    on_hand INTEGER NOT NULL CHECK (on_hand >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    PRIMARY KEY (product_id, warehouse_id),
    CHECK (reserved <= on_hand)
);
~~~

Tuy nhiên, chi tiết các reservation nằm ở nhiều hàng khác. Bất biến cần bảo vệ là tổng reservation đang hoạt động của sản phẩm tại kho phải bằng reserved trên hàng tổng hợp. Mỗi lần tạo, hủy hoặc hoàn tất reservation cần cập nhật chi tiết và hàng tổng hợp trong cùng transaction.

Một thao tác giữ chỗ an toàn có thể dùng cập nhật có điều kiện:

~~~sql
BEGIN;

UPDATE inventory_balances
SET reserved = reserved + :requested_quantity
WHERE product_id = :product_id
  AND warehouse_id = :warehouse_id
  AND on_hand - reserved >= :requested_quantity;

-- Chỉ khi đúng một hàng được cập nhật mới thêm reservation detail.
-- Nếu không đủ hàng hoặc không có balance, rollback.

COMMIT;
~~~

Điều kiện kiểm tra và tăng reserved diễn ra trong một câu lệnh cập nhật nguyên tử. Hai yêu cầu đồng thời không thể cùng tiêu thụ một lượng available đã được nhìn thấy ở một thời điểm cũ, miễn là tất cả luồng giữ chỗ dùng cùng cơ chế.

### 5.5. Hạn mức tín dụng của khách hàng

Một khách hàng có hạn mức tín dụng 50 triệu đồng. Tổng công nợ chưa thanh toán của nhiều đơn hàng không được vượt hạn mức đó.

Đây là bất biến giữa nhiều đơn hàng và các khoản thanh toán. Nếu hai yêu cầu tạo đơn đồng thời, mỗi yêu cầu có thể đọc thấy công nợ còn trong hạn mức rồi cùng ghi thêm, khiến tổng vượt giới hạn.

Các cách bảo vệ:

- Khóa hàng customer_credit_limit trước khi tính và cập nhật công nợ.
- Dùng hàng tổng hợp current_exposure và cập nhật nguyên tử trong cùng transaction với đơn hàng.
- Dùng mức cô lập SERIALIZABLE và xử lý retry khi có serialization failure.
- Dùng ledger làm nguồn sự thật và đối soát với số dư tổng hợp.

Một cột tổng hợp chỉ có tác dụng nếu mọi đường ghi đều cập nhật nó đúng cách. Nếu một tiến trình import bỏ qua cột đó, hạn mức có thể bị vượt dù các giao dịch trực tuyến đều tuân thủ.

## 6. Vì sao kiểm tra trước khi ghi chưa đủ?

Một lỗi thường gặp là đọc dữ liệu, kiểm tra điều kiện trong ứng dụng, sau đó mới ghi. Khoảng thời gian giữa kiểm tra và ghi tạo ra race condition.

Ví dụ, tồn kho còn một sản phẩm. Hai transaction cùng chạy:

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant B as Transaction B
    participant DB as Database
    A->>DB: Đọc available = 1
    B->>DB: Đọc available = 1
    A->>DB: Ghi giữ chỗ 1
    B->>DB: Ghi giữ chỗ 1
    Note over A,B: Nếu không có khóa hoặc cập nhật nguyên tử
    DB-->>A: Thành công
    DB-->>B: Thành công
    Note over DB: Có thể giữ chỗ tổng cộng 2 khi chỉ có 1
~~~

Ứng dụng đã kiểm tra điều kiện nhưng kết quả không còn đúng tại thời điểm ghi. Đây là lỗi TOCTOU (time of check to time of use).

Giải pháp không chỉ là kiểm tra lại ở giao diện. Cần cơ chế đồng bộ tại nơi cập nhật:

- Atomic conditional update.
- SELECT ... FOR UPDATE hoặc khóa tương đương.
- Unique/exclusion constraint chuyên biệt.
- Isolation level phù hợp.
- Optimistic concurrency với version và điều kiện cập nhật.

### 6.1. Pessimistic locking

Pessimistic locking khóa hàng trước khi đọc và sửa. Transaction khác muốn sửa cùng hàng phải chờ hoặc thất bại theo chính sách timeout.

Phù hợp khi xung đột có thể xảy ra thường xuyên và thao tác cần tuần tự hóa. Tuy nhiên, khóa lâu làm giảm thông lượng, có thể gây deadlock và cần quy tắc lấy khóa nhất quán.

### 6.2. Optimistic concurrency

Optimistic concurrency dùng version hoặc giá trị cũ để chỉ cập nhật nếu dữ liệu chưa bị thay đổi:

Giả sử inventory_balances có thêm cột version BIGINT NOT NULL DEFAULT 0.

~~~sql
UPDATE inventory_balances
SET reserved = :new_reserved,
    version = version + 1
WHERE product_id = :product_id
  AND warehouse_id = :warehouse_id
  AND version = :expected_version;
~~~

Nếu số hàng cập nhật bằng không, dữ liệu đã thay đổi hoặc bản ghi không còn phù hợp; ứng dụng phải đọc lại và xử lý lại thao tác. Cơ chế này phù hợp khi xung đột ít và có thể retry.

### 6.3. Isolation level và serialization failure

Isolation level quyết định các transaction đồng thời nhìn thấy và tác động lên dữ liệu như thế nào. READ COMMITTED, REPEATABLE READ và SERIALIZABLE có hành vi khác nhau giữa các hệ quản trị.

SERIALIZABLE hướng tới kết quả tương đương một thứ tự chạy tuần tự, nhưng hệ quản trị có thể hủy một transaction khi phát hiện xung đột cần retry. Ứng dụng phải xử lý lỗi serialization và chạy lại toàn bộ transaction một cách an toàn.

Không nên chọn isolation level chỉ dựa trên tên. Hãy đọc tài liệu của hệ quản trị, hiểu các anomaly có thể xảy ra và kiểm thử với đúng workload.

### 6.4. Thứ tự lấy khóa và deadlock

Nếu một transaction khóa sản phẩm A rồi B, trong khi transaction khác khóa B rồi A, hai transaction có thể chờ nhau và tạo deadlock. Hãy thống nhất thứ tự lấy khóa, ví dụ sắp xếp theo product_id trước khi khóa nhiều hàng.

Deadlock không nhất thiết có nghĩa dữ liệu sai; cơ sở dữ liệu thường hủy một transaction để giải phóng tình trạng chờ. Ứng dụng cần xử lý lỗi có thể retry, giới hạn số lần và bảo đảm thao tác có tính idempotent.

## 7. Chọn cơ chế theo phạm vi bất biến

Không có một cơ chế duy nhất phù hợp với mọi quy tắc. Có thể dùng bảng quyết định sau:

| Loại quy tắc | Ví dụ | Cơ chế ưu tiên | Điều cần kiểm tra |
|---|---|---|---|
| Một cột | quantity > 0 | NOT NULL, CHECK | NULL và kiểu dữ liệu |
| Nhiều cột cùng hàng | ends_at > starts_at | CHECK | Quy tắc NULL và timezone |
| Duy nhất trong nhóm | line_no duy nhất trong order | PRIMARY KEY, UNIQUE | Phạm vi khóa ghép |
| Duy nhất có điều kiện | Một email chính đang hoạt động | Partial unique index hoặc cơ chế tương đương | Hỗ trợ của hệ quản trị |
| Tham chiếu | order_line phải có order | FOREIGN KEY | Chính sách ON DELETE/UPDATE |
| Tổng trong nhóm | Tổng phân bổ không vượt capacity | Hàng tổng hợp + transaction/lock | Mọi đường ghi cập nhật cùng cơ chế |
| Khoảng không chồng lấn | Lịch phòng hoặc thiết bị | Exclusion constraint hoặc khóa tài nguyên | Ngữ nghĩa khoảng và đồng thời |
| Liên bảng | Payment không vượt amount_due | Transaction, lock hoặc SERIALIZABLE | Race condition và retry |
| Quy trình trạng thái | Chỉ đơn đã xác nhận mới được giao | State transition + transaction | Lịch sử và quyền chuyển trạng thái |

### 7.1. Ưu tiên constraint khai báo khi có thể

Constraint khai báo trong schema có một lợi thế quan trọng: mọi đường ghi qua cơ sở dữ liệu đều phải tuân thủ. Nó cũng giúp người đọc schema nhìn thấy một phần hợp đồng dữ liệu.

Hãy dùng PRIMARY KEY, UNIQUE, FOREIGN KEY, NOT NULL và CHECK cho các quy tắc mà chúng biểu diễn chính xác. Với ràng buộc đặc thù như exclusion, hãy đánh giá tính portable và khả năng hỗ trợ của hệ quản trị.

### 7.2. Dùng transaction cho một thay đổi nghiệp vụ gồm nhiều bước

Một nghiệp vụ như giữ chỗ hàng thường cần:

1. Kiểm tra và tăng reserved.
2. Tạo reservation.
3. Ghi nhận thời hạn giữ chỗ.
4. Ghi lịch sử hoặc outbox event nếu cần.

Các bước phải cùng commit hoặc cùng rollback. Nếu chỉ tăng reserved nhưng không tạo reservation, số tổng hợp sẽ bị lệch. Nếu tạo reservation nhưng không tăng reserved, hai khách hàng có thể cùng được xác nhận.

### 7.3. Trigger không phải giải pháp mặc định

Trigger có thể bảo vệ quy tắc ở cấp cơ sở dữ liệu khi cần phản ứng với INSERT/UPDATE/DELETE. Nhưng trigger làm hành vi ghi dữ liệu ít hiển thị hơn trong mã ứng dụng và có thể gây khó khăn khi debug, migration hoặc kiểm soát hiệu năng.

Chỉ dùng trigger khi lợi ích thực thi tập trung rõ ràng và nhóm có thể kiểm thử, giám sát, tài liệu hóa nó. Trigger cũng phải được thiết kế để xử lý transaction và cạnh tranh đồng thời; việc đặt logic trong trigger không tự động làm quy tắc an toàn.

### 7.4. Materialized aggregate cần đối soát

Một số hệ thống lưu số dư, tổng tiền hoặc tổng lượng giữ chỗ để đọc nhanh. Đây là dữ liệu tổng hợp có thể được tái tạo từ các bản ghi chi tiết.

Nếu lưu tổng hợp:

- Xác định dữ liệu chi tiết nào là nguồn sự thật.
- Cập nhật chi tiết và tổng hợp trong cùng transaction hoặc cơ chế đồng bộ đáng tin cậy.
- Có job đối soát định kỳ.
- Có cách sửa sai có kiểm soát.
- Không cho phép nhiều dịch vụ tự cập nhật tổng theo công thức riêng.

Một tổng hợp nhanh nhưng không có cách kiểm chứng sẽ trở thành nguồn sai lệch khó tìm.

## 8. Bất biến và state machine

Một giá trị status có thể thuộc tập hợp hợp lệ nhưng luồng chuyển trạng thái vẫn sai. Ví dụ, các trạng thái đơn hàng gồm draft, confirmed, paid, fulfilled, cancelled. CHECK có thể ngăn status = 'unknown', nhưng không tự ngăn chuyển từ cancelled sang fulfilled.

Hãy mô tả các chuyển trạng thái hợp lệ:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Confirmed
    Draft --> Cancelled
    Confirmed --> Paid
    Confirmed --> Cancelled
    Paid --> Fulfilled
    Paid --> Refunded
    Fulfilled --> [*]
    Cancelled --> [*]
    Refunded --> [*]
~~~

Khi chuyển trạng thái:

- Kiểm tra trạng thái hiện tại.
- Kiểm tra điều kiện nghiệp vụ cần thiết.
- Cập nhật trạng thái và các dữ liệu liên quan trong transaction.
- Ghi lịch sử chuyển trạng thái nếu cần.
- Chặn các chuyển đổi không hợp lệ.

Ví dụ, khi chuyển đơn hàng từ confirmed sang paid, cần kiểm tra số tiền thanh toán hợp lệ và trạng thái đơn hàng chưa bị hủy. Nếu ghi payment và đổi status là hai thao tác tách rời, lỗi giữa chừng có thể tạo trạng thái không nhất quán.

## 9. Idempotency và xử lý gửi lặp

Một yêu cầu thanh toán hoặc đặt hàng có thể được gửi lại do timeout, mạng chập chờn hoặc người dùng nhấn nút nhiều lần. Nếu mỗi lần gửi đều tạo bản ghi mới, một giao dịch có thể bị xử lý hai lần.

Idempotency key giúp nhận diện các lần gửi thuộc cùng một thao tác logic:

~~~sql
CREATE TABLE payment_requests (
    payment_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Khi nhận yêu cầu:

1. Tìm hoặc tạo bản ghi theo idempotency_key.
2. Nếu key đã tồn tại với cùng request_hash, trả lại kết quả đã ghi nhận hoặc trạng thái đang xử lý.
3. Nếu key đã tồn tại nhưng nội dung yêu cầu khác, từ chối vì cùng một key không được đại diện cho hai thao tác khác nhau.
4. Ghi kết quả và cập nhật trạng thái trong transaction phù hợp.

Unique constraint bảo đảm chỉ một yêu cầu logic được tạo cho mỗi key. Nhưng xử lý idempotency vẫn cần thiết kế trạng thái, kết quả, thời hạn lưu key và tương tác với hệ thống thanh toán bên ngoài.

## 10. Phát hiện và xử lý dữ liệu vi phạm

Constraint giúp chặn dữ liệu sai mới, nhưng dữ liệu cũ có thể đã vi phạm trước khi constraint được thêm. Trước khi triển khai ràng buộc:

1. Truy vấn tìm các hàng vi phạm.
2. Phân loại nguyên nhân: dữ liệu thiếu, dữ liệu trùng, lỗi logic hay khác biệt định nghĩa.
3. Xác định cách sửa có căn cứ nghiệp vụ.
4. Lưu lại dữ liệu gốc và quyết định sửa nếu cần audit.
5. Làm sạch hoặc cách ly dữ liệu.
6. Thêm constraint và xác minh.

Ví dụ, trước khi thêm UNIQUE cho email đã chuẩn hóa, cần tìm các giá trị trùng. Không nên tự động xóa một tài khoản vì hai khách hàng có thể dùng chung email.

Với bất biến tổng hợp, có thể chạy truy vấn đối soát:

~~~sql
SELECT
    b.product_id,
    b.warehouse_id,
    b.reserved AS stored_reserved,
    COALESCE(SUM(r.quantity), 0) AS calculated_reserved
FROM inventory_balances b
LEFT JOIN reservations r
    ON r.product_id = b.product_id
   AND r.warehouse_id = b.warehouse_id
   AND r.status = 'active'
GROUP BY
    b.product_id,
    b.warehouse_id,
    b.reserved
HAVING b.reserved <> COALESCE(SUM(r.quantity), 0);
~~~

Truy vấn này tìm các hàng tổng hợp không khớp với chi tiết reservation đang hoạt động. Schema thực tế có thể cần nhóm theo batch, owner hoặc thời hạn giữ chỗ; điều kiện phải khớp định nghĩa nghiệp vụ.

### 10.1. Cách sửa dữ liệu vi phạm

Không phải mọi lỗi đều nên được sửa tự động. Có thể:

- Tự sửa khi có nguồn sự thật rõ và phép biến đổi không mơ hồ.
- Đưa vào hàng đợi xử lý thủ công khi cần quyết định nghiệp vụ.
- Cách ly bản ghi import sai để không ảnh hưởng dữ liệu đang hoạt động.
- Tạo điều chỉnh bù trừ thay vì sửa trực tiếp giao dịch đã chốt.

Sau khi sửa, chạy lại truy vấn đối soát và lưu số lượng bản ghi đã xử lý, số còn tồn đọng cùng lý do.

## 11. Kiểm thử bất biến

### 11.1. Kiểm thử dữ liệu hợp lệ và không hợp lệ

Với mỗi constraint, cần ít nhất một trường hợp hợp lệ và một trường hợp bị từ chối:

| Quy tắc | Dữ liệu hợp lệ | Dữ liệu không hợp lệ |
|---|---|---|
| quantity > 0 | quantity = 2 | quantity = 0 |
| ends_at > starts_at | kết thúc sau bắt đầu | kết thúc trước bắt đầu |
| Mã đơn duy nhất | hai mã khác nhau | chèn mã đã tồn tại |
| Foreign key | customer_id tồn tại | customer_id không tồn tại |
| Một email chính | một hàng primary đang hoạt động | hai hàng primary cùng khách hàng |
| Tồn kho | reserved <= on_hand | reserved > on_hand |

### 11.2. Kiểm thử đồng thời

Các bất biến về tổng và tài nguyên phải được kiểm thử với nhiều transaction thực sự chạy đồng thời. Một test tuần tự có thể luôn pass dù hệ thống vẫn có race condition.

Ví dụ:

- Tồn kho chỉ còn một đơn vị, gửi hai yêu cầu giữ chỗ cùng lúc.
- Hạn mức tín dụng chỉ còn đủ cho một đơn, tạo hai đơn đồng thời.
- Hai người cùng xác nhận một lịch phòng.
- Hai webhook thanh toán gửi cùng một sự kiện.

Kiểm tra kết quả cuối cùng: chỉ số thao tác được phép thành công, tổng không vượt giới hạn, không có bản ghi mồ côi và transaction thất bại không để lại thay đổi một phần.

### 11.3. Kiểm thử rollback và retry

Giả lập lỗi sau khi cập nhật hàng tổng hợp nhưng trước khi thêm chi tiết. Transaction phải rollback cả hai thay đổi. Giả lập deadlock hoặc serialization failure để xác nhận ứng dụng retry đúng cách.

Nếu transaction gọi hệ thống bên ngoài, không nên giữ khóa cơ sở dữ liệu trong lúc chờ mạng lâu. Có thể dùng outbox, trạng thái trung gian và xử lý bất đồng bộ, nhưng cần định nghĩa bất biến cho từng trạng thái và cách phục hồi khi gửi lại.

## 12. Tiến hóa ràng buộc và schema

Bất biến có thể thay đổi khi nghiệp vụ phát triển. Ví dụ, trước đây đơn hàng không cho phép thanh toán một phần; sau này cho phép nhiều lần thanh toán. Hoặc tồn kho bắt đầu hỗ trợ backorder nên on_hand - reserved có thể âm theo một mô hình mới.

Khi thay đổi:

- Xác nhận định nghĩa mới và thời điểm có hiệu lực.
- Tìm dữ liệu cũ vi phạm quy tắc mới.
- Quyết định backfill, chuyển đổi hoặc giữ trạng thái lịch sử.
- Thêm constraint theo giai đoạn nếu bảng lớn.
- Triển khai ứng dụng tương thích với schema trong thời gian chuyển tiếp.
- Theo dõi lỗi constraint và số liệu đối soát sau phát hành.

Với một constraint mới trên bảng lớn, có thể cần kiểm tra dữ liệu trước, thêm constraint theo chế độ ít chặn hơn nếu hệ quản trị hỗ trợ, xác minh và sau đó chuyển sang trạng thái được xác thực đầy đủ. Cú pháp và tác động khóa phụ thuộc sản phẩm cơ sở dữ liệu.

Không nên xóa constraint chỉ vì một luồng ghi đang bị lỗi. Trước hết cần xác định lỗi do dữ liệu sai, quy tắc mới chưa được cập nhật ở ứng dụng hay constraint mô tả sai nghiệp vụ.

## 13. Quy trình thiết kế và bảo vệ bất biến

Khi thiết kế một thực thể hoặc quy trình dữ liệu:

1. **Liệt kê bất biến:** viết điều kiện phải luôn đúng và thời điểm áp dụng.
2. **Xác định phạm vi:** một hàng, một nhóm, nhiều bảng hay toàn hệ thống.
3. **Chọn nguồn sự thật:** xác định bảng hoặc ledger nào là căn cứ chính.
4. **Chọn cơ chế:** CHECK, UNIQUE, FOREIGN KEY, exclusion constraint, transaction, lock hoặc isolation level.
5. **Xác định mọi đường ghi:** API, job, import, webhook, admin tool và migration.
6. **Phân tích đồng thời:** tìm race condition, deadlock và thứ tự lấy khóa.
7. **Thiết kế phục hồi:** rollback, retry, idempotency, outbox hoặc quy trình bù trừ.
8. **Kiểm thử:** trường hợp hợp lệ, không hợp lệ, đồng thời và lỗi giữa chừng.
9. **Đối soát:** tạo truy vấn phát hiện sai lệch cho dữ liệu tổng hợp hoặc quy tắc liên bảng.
10. **Theo dõi sau triển khai:** giám sát lỗi constraint, retry, deadlock và các chỉ số bất biến.

Mỗi bất biến nên có tài liệu ngắn gồm định nghĩa, phạm vi, nơi thực thi, chủ sở hữu và cách kiểm chứng. Điều này đặc biệt quan trọng khi một quy tắc được bảo vệ bởi nhiều cơ chế phối hợp.

## 14. Checklist đánh giá thiết kế

- [ ] Các bất biến được viết thành điều kiện cụ thể và có thời điểm áp dụng.
- [ ] Mỗi quy tắc được phân loại theo phạm vi một hàng, một nhóm hoặc nhiều nhóm.
- [ ] NOT NULL và CHECK bảo vệ các điều kiện trong cùng hàng.
- [ ] PRIMARY KEY và UNIQUE phản ánh đúng phạm vi định danh.
- [ ] Foreign key bảo vệ các quan hệ tham chiếu.
- [ ] Quy tắc tổng hợp có cơ chế cập nhật và đối soát.
- [ ] Quy tắc liên bảng được bảo vệ bằng transaction và cơ chế đồng thời phù hợp.
- [ ] Các luồng ghi trực tuyến, import, job và webhook dùng cùng quy tắc.
- [ ] Có xử lý rollback, deadlock, serialization failure và retry.
- [ ] Yêu cầu gửi lặp có idempotency khi cần.
- [ ] State transition được kiểm tra chứ không chỉ kiểm tra tập giá trị status.
- [ ] Dữ liệu cũ được kiểm tra trước khi thêm constraint mới.
- [ ] Có truy vấn hoặc chỉ số phát hiện bất biến bị vi phạm.
- [ ] Có người chịu trách nhiệm và tài liệu cho mỗi bất biến quan trọng.

## Kết luận

Bất biến cần được phân loại theo phạm vi trước khi chọn cách thực thi. Quy tắc trong một hàng thường phù hợp với NOT NULL và CHECK. Quy tắc trong một nhóm thường cần khóa chính, unique constraint, partial index hoặc cơ chế kiểm tra tổng hợp. Quy tắc giữa nhiều nhóm và nhiều bảng thường cần transaction, khóa, isolation level hoặc constraint chuyên biệt, cùng quy trình đối soát.

Kiểm tra trước khi ghi trong ứng dụng không đủ để bảo vệ dữ liệu khi nhiều giao dịch chạy đồng thời. Hãy đặt constraint khai báo ở nơi có thể, dùng transaction cho thay đổi nhiều bước, xử lý retry và idempotency, đồng thời kiểm thử các tình huống cạnh tranh. Khi bất biến được mô tả rõ, thực thi nhất quán và kiểm chứng thường xuyên, mô hình dữ liệu sẽ giữ được trạng thái đáng tin cậy ngay cả khi hệ thống có nhiều luồng ghi và quy trình thay đổi.
