# Khi nào dùng DEFAULT, CHECK hoặc FOREIGN KEY thay trigger

Trong **Database SQL**, trigger là cơ chế cho phép cơ sở dữ liệu tự thực hiện một đoạn logic khi xảy ra sự kiện như `INSERT`, `UPDATE` hoặc `DELETE`. Trigger rất hữu ích ở một số bài toán, nhưng **không phải lựa chọn mặc định cho mọi quy tắc dữ liệu**.

Giả sử một hệ thống bán hàng cần:

- Đơn mới có trạng thái `DRAFT` nếu người gọi không truyền trạng thái.
- Số lượng hàng phải lớn hơn 0.
- Đơn hàng phải tham chiếu một khách hàng thực sự tồn tại.
- Mã sản phẩm không được trùng.
- Khi trạng thái đơn chuyển sang `PAID`, phải có thời điểm xác nhận.
- Cần ghi nhận lịch sử **chuyển trạng thái** từ `DRAFT` sang `CONFIRMED`.

Có thể viết trigger cho tất cả việc trên. Nhưng cách thiết kế tốt hơn thường là dùng **`DEFAULT` cho giá trị khởi tạo, `CHECK` cho điều kiện hợp lệ trong một hàng, `FOREIGN KEY` cho quan hệ tham chiếu**, kết hợp `NOT NULL` và `UNIQUE` khi cần. **Trigger chỉ nên đảm nhiệm những công việc không được các cơ chế khai báo đó diễn đạt đầy đủ**, chẳng hạn so sánh giá trị cũ/mới để kiểm soát chuyển trạng thái hoặc ghi audit phức tạp.

Bài học thuộc chương **Trigger**, tập trung vào câu hỏi thiết kế: **khi nào nên thay trigger bằng ràng buộc/giá trị mặc định có sẵn của DBMS, vì sao, và khi nào trigger vẫn cần thiết**. Phần thực hành chính dùng **PostgreSQL**; cuối bài so sánh với MySQL/MariaDB, SQL Server, Oracle và SQLite.

## 1. Nguyên tắc ưu tiên: khai báo quy tắc trước, trigger sau

Một hướng lựa chọn hữu ích:

```text
Bạn muốn bảo đảm điều gì?
             |
             v
   Giá trị khi INSERT bỏ qua cột?
       | Có
       +----> DEFAULT hoặc IDENTITY
             |
             v
   Cột bắt buộc phải có giá trị?
       | Có
       +----> NOT NULL
             |
             v
   Điều kiện chỉ dựa vào các cột cùng hàng?
       | Có
       +----> CHECK
             |
             v
   Giá trị phải duy nhất?
       | Có
       +----> UNIQUE / PRIMARY KEY
             |
             v
   Phải tham chiếu hàng ở bảng khác?
       | Có
       +----> FOREIGN KEY
             |
             v
   Logic phụ thuộc OLD/NEW, nhiều hàng,
   hành động phụ hoặc quy tắc đặc biệt?
       |
       +----> Xem xét trigger/procedure,
              transaction, khóa và ứng dụng
```

Đây không phải danh sách ưu tiên cứng cho mọi trường hợp. Một yêu cầu có thể cần **kết hợp** nhiều cơ chế, ví dụ `DEFAULT 'DRAFT'` + `NOT NULL` + `CHECK (status IN (...))`. Điểm quan trọng là **đừng dùng trigger để mô phỏng một ràng buộc mà DBMS đã hỗ trợ đúng ngữ nghĩa**.

### Bảng quyết định nhanh

| Yêu cầu | Cơ chế nên xét đầu tiên | Vì sao thường không cần trigger? |
| --- | --- | --- |
| Đơn mới mặc định ở trạng thái `DRAFT` | `DEFAULT 'DRAFT'` | DBMS tự điền khi cột được bỏ qua hoặc dùng từ khóa `DEFAULT` |
| Thời điểm tạo mặc định hiện tại | `DEFAULT CURRENT_TIMESTAMP` | Không cần một lệnh UPDATE bổ sung |
| Số lượng phải dương | `CHECK (quantity > 0)` + `NOT NULL` | Quy tắc nằm trong một hàng, khai báo trực tiếp |
| Tiền giảm giá từ 0 đến 100% | `CHECK (discount_pct BETWEEN 0 AND 100)` + `NOT NULL` | Dễ thấy và được áp dụng khi ghi dữ liệu |
| Khách hàng phải tồn tại | `FOREIGN KEY (customer_id) REFERENCES customers(...)` | DBMS bảo vệ quan hệ khi thêm/sửa/xóa |
| SKU không được trùng | `UNIQUE (sku)` | DBMS xử lý cạnh tranh đồng thời thay vì trigger tự `SELECT` kiểm tra |
| ID tự tăng | `IDENTITY` / auto-increment / sequence tùy DBMS | Cơ chế sinh khóa tích hợp |
| Tổng tiền một dòng = số lượng × giá × (1 − giảm giá) | Generated/computed column nếu phù hợp | DBMS tính từ các cột cùng dòng |
| Không được chuyển `PAID` về `DRAFT` | Trigger hoặc procedure kiểm soát chuyển trạng thái | Cần so sánh trạng thái **cũ và mới** |
| Ghi audit giá trị trước/sau một lần UPDATE | Trigger hoặc cơ chế auditing/CDC chuyên dụng | `DEFAULT`/`CHECK`/`FK` không lưu lịch sử sự kiện |
| Số dư tổng từ nhiều giao dịch phải nhất quán | Mô hình transaction/ledger, khóa thích hợp; trigger có thể là một phần | Bài toán nhiều hàng/đồng thời, không giải được bằng CHECK một hàng |
| Gửi email khi có đơn | Outbox + worker ứng dụng, hoặc cơ chế sự kiện thích hợp | Side effect ngoài DB không nên phụ thuộc trực tiếp trigger khó retry |

## 2. Vì sao khai báo ràng buộc thường tốt hơn trigger?

Một ràng buộc như:

```sql
CHECK (quantity > 0)
```

nói rõ **trạng thái dữ liệu được phép tồn tại**, thay vì diễn tả từng bước kiểm tra và phát sinh lỗi.

Về thiết kế, ràng buộc khai báo có những ưu điểm đáng kể:

1. **Dễ đọc từ schema:** người xem định nghĩa bảng nhận ra ngay quy tắc.
2. **Áp dụng cho mọi đường ghi hợp lệ:** nhiều service, công cụ quản trị và batch import cùng chịu ràng buộc, không cần sao chép kiểm tra ở từng nơi.
3. **DBMS quản lý tính nhất quán:** đặc biệt với `UNIQUE` và `FOREIGN KEY` trong tình huống đồng thời.
4. **Ít mã thủ tục:** không cần tự viết trigger function, xử lý biến OLD/NEW, thứ tự trigger và exception cho quy tắc đơn giản.
5. **Có metadata:** công cụ migration, introspection và quản trị có thể tra cứu tên/loại constraint.
6. **Dễ kiểm thử hợp đồng dữ liệu:** thử chèn giá trị sai và mong đợi ràng buộc từ chối.
7. **Cơ hội tối ưu:** một số DBMS/optimizer có thể dùng thông tin về khóa, `NOT NULL` hoặc quan hệ để lập kế hoạch; khả năng cụ thể tùy hệ.

Ngược lại, trigger thường khó tìm thấy nếu chỉ nhìn DDL của một cột, và có thể chứa logic bổ sung mà câu `INSERT` ban đầu không thể hiện. Một thao tác tưởng đơn giản có thể chạm nhiều bảng, tạo độ trễ và khóa ngoài dự kiến.

**Không có nghĩa trigger luôn chậm hoặc constraint luôn miễn phí.** `FOREIGN KEY` cũng tạo công việc kiểm tra, index và khóa; `CHECK` cũng phải đánh giá biểu thức. Nhưng với cùng một quy tắc đã có primitive chuẩn, constraint thường **trực tiếp và dễ bảo trì hơn**.

## 3. DEFAULT: tự điền giá trị khi không được cung cấp

Giả sử khi tạo đơn hàng mới, trạng thái ban đầu mặc định là `DRAFT`.

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'DRAFT'
);
```

Khi:

```sql
INSERT INTO orders (order_id) VALUES (1);
```

DBMS sử dụng `'DRAFT'` cho cột `status`.

Nếu không có `DEFAULT`, một người có thể viết trigger:

```sql
-- Chỉ là ý tưởng; cú pháp trigger thật khác nhau theo DBMS.
IF NEW.status IS NULL THEN
    NEW.status := 'DRAFT';
END IF;
```

Nhưng đây là logic đơn giản mà `DEFAULT` đã được tạo ra để xử lý. Dùng trigger còn dễ làm nhập nhằng giữa “người gọi bỏ qua cột” và “người gọi chủ động truyền NULL”.

### DEFAULT không phải ràng buộc mọi giá trị đều hợp lệ

`DEFAULT 'DRAFT'` chỉ quyết định giá trị mặc định. Nếu người gọi truyền:

```sql
INSERT INTO orders (order_id, status)
VALUES (2, 'UNKNOWN');
```

thì DEFAULT **không từ chối** `UNKNOWN`. Cần thêm:

```sql
CHECK (status IN ('DRAFT', 'CONFIRMED', 'PAID', 'CANCELLED'))
```

hoặc chọn một mô hình danh mục/FK thích hợp.

**Phân biệt rõ:** `DEFAULT` trả lời “không cung cấp thì lấy gì?”, `CHECK` trả lời “cung cấp giá trị nào thì được chấp nhận?”.

## 4. DEFAULT và NULL: lỗi hiểu rất phổ biến

Trong PostgreSQL và nhiều DBMS, hai câu sau **khác nhau**:

```sql
-- Cột status bị bỏ qua, DEFAULT được áp dụng:
INSERT INTO orders (order_id) VALUES (3);

-- Chủ động yêu cầu giá trị mặc định:
INSERT INTO orders (order_id, status)
VALUES (4, DEFAULT);

-- Chủ động truyền NULL:
INSERT INTO orders (order_id, status)
VALUES (5, NULL);
```

Với `status TEXT NOT NULL DEFAULT 'DRAFT'`:

- Dòng 3 nhận `DRAFT`.
- Dòng 4 nhận `DRAFT`.
- Dòng 5 bị lỗi `NOT NULL`, **không được ngầm thay bằng DRAFT**.

Vì vậy nếu ứng dụng gửi giá trị `NULL` thay vì bỏ cột, `DEFAULT` không tự cứu dữ liệu. Nếu yêu cầu nghiệp vụ muốn biến `NULL` thành `DRAFT`, cần quyết định liệu:

- Sửa ứng dụng để **bỏ cột** khi không có trạng thái;
- Dùng biểu thức `COALESCE`/logic ở API khi tạo câu `INSERT`;
- Dùng một cơ chế DBMS riêng như **Oracle `DEFAULT ON NULL`** khi phù hợp;
- Hay thật sự cần trigger biến đổi `NULL`, sau khi cân nhắc ngữ nghĩa.

Trước khi thêm trigger, hãy hỏi: **NULL có phải một lỗi dữ liệu cần từ chối hay là một cách viết khác của “không cung cấp”?** Hai quyết định dẫn tới hợp đồng API khác nhau.

## 5. Giá trị mặc định động: ngày giờ và khóa tự sinh

`DEFAULT` không chỉ dành cho chuỗi hằng.

### 5.1. Thời điểm tạo

PostgreSQL:

```sql
created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
```

DBMS tự tạo giá trị khi `INSERT` không truyền cột. Không cần một trigger “trước khi insert, gán thời gian”.

**Chú ý ngữ nghĩa thời gian:** trong PostgreSQL, `CURRENT_TIMESTAMP` phản ánh thời điểm bắt đầu **transaction**; các câu lệnh trong cùng transaction có thể nhận cùng timestamp. Nếu nghiệp vụ yêu cầu thời gian đồng hồ ngay tại từng lần gọi, cần đánh giá `clock_timestamp()` và hệ quả tương ứng. Đừng đổi hàm chỉ vì thấy vài dòng có timestamp bằng nhau.

### 5.2. Khóa chính

PostgreSQL hiện đại:

```sql
order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
```

`IDENTITY` là lựa chọn tích hợp cho giá trị số tăng theo sequence. Không cần trigger “lấy MAX(id)+1” — cách tự tính `MAX+1` còn dễ bị race condition khi nhiều phiên ghi đồng thời.

Tùy hệ, có cơ chế tương ứng như:

- PostgreSQL: `GENERATED ... AS IDENTITY` hoặc sequence.
- MySQL/MariaDB: `AUTO_INCREMENT`.
- SQL Server: `IDENTITY` hoặc sequence.
- Oracle: identity/sequence.
- SQLite: cơ chế `INTEGER PRIMARY KEY`/rowid theo thiết kế.

**Không coi ID tự sinh luôn liên tục không có khoảng trống.** Rollback, cache sequence và xử lý song song có thể tạo gap; khóa định danh không phải số thứ tự chứng từ liên tục theo quy định.

## 6. DEFAULT không có nghĩa “tự cập nhật khi UPDATE”

Một cột:

```sql
updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
```

được gán mặc định lúc **INSERT** nếu bị bỏ qua, nhưng **không tự đổi** mỗi khi một câu `UPDATE` thay đổi hàng, trừ khi có cơ chế riêng của DBMS.

Nếu hệ thống yêu cầu `updated_at` luôn phản ánh lần sửa cuối:

- Có thể để **ứng dụng/procedure** đặt `updated_at = CURRENT_TIMESTAMP` trong mỗi lệnh UPDATE.
- Một số DBMS hỗ trợ cú pháp tự cập nhật timestamp riêng.
- Nếu mọi đường UPDATE không thể được kiểm soát ở ứng dụng, một **trigger BEFORE UPDATE** có thể là giải pháp hợp lý.

Ví dụ PostgreSQL — dùng trigger khi thật sự cần tự động cập nhật:

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;
```

Đoạn trên mới là **trigger function**, chưa gắn vào bảng. Trigger thật còn cần `CREATE TRIGGER ... BEFORE UPDATE ... FOR EACH ROW EXECUTE FUNCTION ...`. Bài học không dùng function này trong lab vì mục tiêu là phân biệt chỗ nào `DEFAULT` chưa đủ.

**Quy tắc:** `created_at` mặc định khi tạo thường là việc của DEFAULT; `updated_at` phản ánh **sự kiện thay đổi** có thể cần application/trigger.

## 7. CHECK: bất biến tính được từ một hàng

`CHECK` diễn đạt một điều kiện mà mỗi hàng phải thỏa khi dữ liệu được ghi/đổi.

Ví dụ:

```sql
CREATE TABLE order_lines (
    line_id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL
        CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL
        CHECK (unit_price >= 0),
    discount_pct NUMERIC(5,2) NOT NULL DEFAULT 0
        CHECK (discount_pct BETWEEN 0 AND 100)
);
```

Quy tắc:

- Số lượng phải là số nguyên dương.
- Đơn giá không âm.
- Giảm giá nằm từ 0 tới 100.
- Nếu không truyền giảm giá, lấy 0.

**Không cần ba trigger riêng** để phát hiện điều này. DBMS có thể kiểm tra từng ràng buộc khi thay đổi dữ liệu.

### CHECK có thể tham chiếu nhiều cột **cùng hàng**

```sql
CREATE TABLE booking_slots (
    slot_id INTEGER PRIMARY KEY,
    starts_at TIMESTAMP NOT NULL,
    ends_at TIMESTAMP NOT NULL,
    CHECK (ends_at > starts_at)
);
```

Điều kiện `ends_at > starts_at` dùng hai cột của **cùng một hàng**, nên phù hợp với CHECK.

Một ví dụ cùng hàng khác:

```sql
CHECK (
    status <> 'PAID'
    OR confirmed_at IS NOT NULL
)
```

Ý nghĩa: nếu đơn ở trạng thái PAID thì phải có `confirmed_at`. Cần thêm `status NOT NULL` và hạn chế miền status nếu không muốn NULL hoặc trạng thái lạ lọt qua.

## 8. CHECK và logic ba giá trị: UNKNOWN không phải FALSE

SQL có logic `TRUE`, `FALSE` và `UNKNOWN` do `NULL`.

Một CHECK trong nhiều DBMS, bao gồm PostgreSQL, từ chối khi biểu thức là **FALSE**; nếu biểu thức là **TRUE hoặc UNKNOWN**, nó không coi đó là vi phạm.

Ví dụ:

```sql
CREATE TABLE samples (
    quantity INTEGER CHECK (quantity > 0)
);
```

Câu:

```sql
INSERT INTO samples (quantity) VALUES (NULL);
```

có thể được chấp nhận vì `NULL > 0` là UNKNOWN, **không phải FALSE**.

Nếu quantity bắt buộc:

```sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
```

Vì vậy quy tắc “lớn hơn 0” và “phải có giá trị” nên được thể hiện bằng **CHECK + NOT NULL**.

### Điều kiện không có ELSE trong CASE cũng có nguy cơ UNKNOWN

Ví dụ:

```sql
CHECK (status IN ('DRAFT', 'PAID'))
```

nếu `status IS NULL`, biểu thức thành UNKNOWN. Cần:

```sql
status TEXT NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT', 'PAID'))
```

Không nên viết trigger kiểm tra trạng thái trước khi hiểu rõ quy tắc NULL của CHECK.

## 9. CHECK không phải công cụ đọc bảng khác

Một yêu cầu nghe gần giống CHECK:

> “Khi tạo dòng đơn hàng, `unit_price` phải bằng giá hiện tại của sản phẩm trong bảng `products`.”

Đây là quy tắc **tham chiếu dữ liệu ở hàng khác/bảng khác**. Trong PostgreSQL, CHECK được thiết kế cho điều kiện trên **hàng đang xét**, không hỗ trợ subquery trực tiếp để truy vấn bảng khác trong biểu thức CHECK.

Dạng sau không phải giải pháp hợp lệ trên PostgreSQL:

```sql
-- Không hợp lệ cho CHECK trong PostgreSQL:
CHECK (
    unit_price = (
        SELECT list_price
        FROM products
        WHERE products.product_id = order_lines.product_id
    )
)
```

Một số người tìm cách giấu truy vấn vào function rồi gọi từ CHECK. Cách đó thường **không an toàn về ngữ nghĩa**: hàng có thể từng hợp lệ nhưng trở nên sai khi giá sản phẩm ở bảng khác thay đổi, trong khi CHECK trên dòng đơn không được đánh giá lại. PostgreSQL kỳ vọng biểu thức CHECK đối với một hàng có tính ổn định phù hợp; dùng hàm phụ thuộc dữ liệu bảng khác còn gây rắc rối khi dump/restore hoặc thay đổi function.

### Giá sản phẩm và giá chốt của đơn là hai ý nghĩa khác nhau

Trong hệ thương mại, đơn giá trong đơn hàng thường cần **lưu lại giá đã chốt tại thời điểm mua**, không buộc bằng giá niêm yết **hiện tại**. Sau khi bảng products đổi giá, đơn đã lập không được tự thay tiền.

Một thiết kế hợp lý:

- `products.list_price`: giá niêm yết hiện tại, có CHECK không âm.
- `order_lines.unit_price`: giá bán đã chốt của dòng đơn, có CHECK không âm.
- `order_lines.product_id`: FK đảm bảo sản phẩm được tham chiếu tồn tại.
- Ứng dụng/procedure chịu trách nhiệm chốt giá tại thời điểm tạo đơn theo quy tắc nghiệp vụ.

Nếu cần tự điền giá qua database, hãy cân nhắc procedure hoặc trigger có khóa/cạnh tranh rõ ràng, **không coi `DEFAULT` là phép đọc động từ bảng sản phẩm**.

## 10. FOREIGN KEY: quan hệ tồn tại giữa các bảng

Một ràng buộc `FOREIGN KEY` nói rằng một giá trị ở bảng con phải tham chiếu tới khóa hợp lệ ở bảng cha, tùy quy tắc NULL.

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
```

Khi thực hiện:

```sql
INSERT INTO orders (order_id, customer_id)
VALUES (1, 9999);
```

mà không có customer 9999, DBMS từ chối vì vi phạm FK.

**Không cần trigger** kiểu:

```text
BEFORE INSERT ON orders:
    SELECT COUNT(*) FROM customers WHERE id = NEW.customer_id;
    IF count = 0 THEN SIGNAL ERROR;
```

Cách trigger kiểm tra tồn tại đơn thuần còn dễ mắc **race condition**: một transaction kiểm tra cha tồn tại, transaction khác xóa cha trước khi bước ghi con hoàn tất. FK do DBMS quản lý đúng cơ chế khóa/kiểm tra tham chiếu cho hệ thống đó.

### FK bảo vệ nhiều chiều

FK không chỉ kiểm tra `INSERT` vào bảng con. Nó còn có thể bảo vệ:

- `UPDATE` khóa tham chiếu của bảng con.
- `UPDATE` khóa phía bảng cha.
- `DELETE` hàng cha đang được tham chiếu.

Tùy hành động `ON DELETE` / `ON UPDATE`, DBMS từ chối hoặc thực hiện hành động khai báo, chứ không nhất thiết cần một trigger tự viết.

## 11. ON DELETE và ON UPDATE: nhiều tình huống không cần trigger

Các lựa chọn FK thường gặp:

| Hành động | Ý nghĩa khái quát | Tình huống |
| --- | --- | --- |
| `NO ACTION` | Từ chối nếu quan hệ bị vi phạm tại thời điểm kiểm tra thích hợp | Đơn không được mất khách hàng tham chiếu |
| `RESTRICT` | Từ chối hành động phá quan hệ; thời điểm khác `NO ACTION` trong DBMS có deferred constraints | Không cho xóa sản phẩm đang được sử dụng |
| `CASCADE` | Thay đổi/xóa bản ghi con liên quan theo tác động trên cha | Xóa dòng chi tiết khi xóa một đơn thử nghiệm |
| `SET NULL` | Đặt khóa con thành NULL khi hàng cha bị xóa/đổi theo action | Quan hệ tùy chọn, cho phép thiếu cha |
| `SET DEFAULT` | Đặt khóa con về giá trị default khi action xảy ra | Chỉ phù hợp nếu default tạo quan hệ hợp lệ theo ràng buộc |

Ví dụ:

```sql
FOREIGN KEY (order_id)
REFERENCES orders(order_id)
ON DELETE CASCADE
```

Không cần trigger `AFTER DELETE ON orders` để tự xóa từng `order_lines` nếu **ý nghĩa nghiệp vụ thật sự là xóa các dòng con theo đơn**.

Nhưng không nên bật CASCADE chỉ để tránh lỗi FK. Với đơn hàng có trách nhiệm lưu chứng từ, **xóa dây chuyền có thể trái yêu cầu audit và retention**. Có thể chọn `RESTRICT`, soft-delete, hoặc quy trình lưu trữ thay thế.

### SET NULL phải tương thích NOT NULL

Nếu cột `customer_id` là `NOT NULL`, `ON DELETE SET NULL` sẽ không phù hợp: khi hành động được thực hiện, hệ có thể bị lỗi NOT NULL. Cần thiết kế trạng thái quan hệ trước khi chọn action.

### SET DEFAULT vẫn phải tham chiếu hợp lệ

Nếu `customer_id DEFAULT 0` mà bảng customers không có khách hàng 0, hành động `SET DEFAULT` vẫn có thể vi phạm FK. Default không phải “miễn kiểm tra khóa ngoại”.

## 12. FOREIGN KEY có thể gồm nhiều cột

Một hệ đa tenant có thể cho phép cùng mã sản phẩm xuất hiện ở nhiều tenant. Chỉ kiểm tra `product_id` có thể không đủ để ngăn tham chiếu chéo tenant.

Ví dụ cấu trúc:

```sql
CREATE TABLE tenant_products (
    tenant_id INTEGER NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, product_code)
);

CREATE TABLE tenant_order_lines (
    line_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    product_code TEXT NOT NULL,
    FOREIGN KEY (tenant_id, product_code)
        REFERENCES tenant_products(tenant_id, product_code)
);
```

FK ghép bảo đảm **cặp** `(tenant_id, product_code)` ở bảng con phải tồn tại trong bảng cha. Không cần trigger tự đối chiếu tenant.

**Thứ tự cột trong danh sách FK có nghĩa:** `FOREIGN KEY (tenant_id, product_code) REFERENCES ... (tenant_id, product_code)` ghép theo vị trí. Nếu đảo thứ tự cột con và có kiểu dữ liệu tương thích, có nguy cơ ánh xạ sai nghiệp vụ dù một số kiểm tra kỹ thuật vẫn có thể chạy.

### FK và NULL trên nhiều cột

Với mặc định `MATCH SIMPLE` trong PostgreSQL, một FK ghép có thể bỏ qua kiểm tra tham chiếu nếu **bất kỳ cột nào** trong cặp là NULL. Nếu bắt buộc tham chiếu đầy đủ, khai báo `NOT NULL` cho tất cả cột liên quan, hoặc cân nhắc `MATCH FULL` khi muốn chính sách tất cả-NULL hoặc tất cả-có-giá-trị và DBMS hỗ trợ.

## 13. FOREIGN KEY yêu cầu khóa phía bảng cha

Một FK không được tham chiếu tùy tiện vào mọi cột không duy nhất của bảng cha. Đối tượng tham chiếu cần là khóa hợp lệ theo quy tắc DBMS, thường là `PRIMARY KEY` hoặc `UNIQUE` thích hợp.

Ví dụ:

```sql
CREATE TABLE product_catalog (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE order_products (
    order_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    FOREIGN KEY (sku) REFERENCES product_catalog(sku)
);
```

Nếu `sku` không duy nhất, không thể xác định “hàng cha nào” một tham chiếu có nghĩa; vì vậy cần khóa phù hợp.

Ngoài ra cần chú ý tương thích kiểu dữ liệu, collation và quy tắc so sánh giữa cột con/cha; DBMS có yêu cầu cụ thể khác nhau.

### Index cho FK không tự đồng nghĩa có index ở bảng con

Bảng cha thường có index nhờ PK/UNIQUE. Tuy nhiên **PostgreSQL không tự tạo index trên các cột tham chiếu ở bảng con chỉ vì bạn khai báo FK**.

Với bảng lớn, nên cân nhắc:

```sql
CREATE INDEX ix_order_lines_order_id
ON order_lines(order_id);
```

nếu workload thường tra đơn, JOIN hoặc xử lý xóa/cập nhật khóa cha. Nhưng index tăng chi phí ghi và dung lượng, nên dựa vào workload thực tế chứ không tự động tạo index cho mọi FK trong mọi hệ.

## 14. UNIQUE và NOT NULL cũng thường thay trigger

Mặc dù tên bài nêu `DEFAULT`, `CHECK` và `FOREIGN KEY`, khi đánh giá trigger cần xét cả:

- `NOT NULL`: cột bắt buộc có giá trị.
- `PRIMARY KEY`: định danh duy nhất, không NULL.
- `UNIQUE`: không cho phép trùng theo tập cột chỉ định, với quy tắc NULL tùy DBMS.
- `EXCLUDE` hoặc ràng buộc chuyên biệt ở DBMS hỗ trợ: một số quan hệ như khoảng thời gian chồng lấn.

Ví dụ nghiệp vụ “mỗi sản phẩm có SKU duy nhất”:

```sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE
);
```

Không viết trigger:

```text
BEFORE INSERT:
    IF EXISTS (SELECT 1 FROM products WHERE sku = NEW.sku)
    THEN error
```

Hai session có thể cùng thấy SKU chưa tồn tại, rồi cùng INSERT. `UNIQUE` là lớp bảo vệ có cơ chế đồng thời do DBMS đảm nhiệm.

### Unique và NULL

Nhiều DBMS mặc định cho phép nhiều dòng `NULL` ở một cột `UNIQUE`, nhưng quy tắc khác nhau theo hệ và phiên bản. Nếu SKU là bắt buộc, kết hợp `NOT NULL UNIQUE`. Đừng dựa vào giả định “UNIQUE tức là NOT NULL”.

### Vùng giá trị dạng enum

Khi danh sách trạng thái nhỏ, cố định:

```sql
CHECK (status IN ('DRAFT', 'CONFIRMED', 'PAID', 'CANCELLED'))
```

thường đơn giản. Khi trạng thái là **dữ liệu danh mục được quản trị**, có mô tả, bật/tắt hoặc thêm mới không muốn sửa DDL, có thể dùng **bảng trạng thái + FOREIGN KEY**. Trigger không tự trở thành lựa chọn tốt hơn chỉ vì danh sách trạng thái dài.

## 15. Generated/computed column: khi giá trị phụ thuộc cùng hàng

Giả sử tổng tiền dòng:

\[
\text{line\_total}
=\text{quantity}\times\text{unit\_price}\times(1-\text{discount\_pct}/100)
\]

Một hướng thường rõ hơn trigger là **generated column**:

```sql
-- PostgreSQL hỗ trợ generated column dạng STORED.
line_total NUMERIC(16,2)
    GENERATED ALWAYS AS (
        quantity * unit_price * (1 - discount_pct / 100)
    ) STORED
```

Ưu điểm:

- Cột tính theo công thức đã khai báo, không phải tự gán ở mọi đường INSERT/UPDATE.
- Tránh tình trạng ứng dụng cập nhật quantity nhưng quên cập nhật line_total.
- Metadata thể hiện quan hệ tính toán giữa các cột.

Giới hạn:

- Quy tắc expression và loại generated column khác nhau theo DBMS/phiên bản.
- Trong PostgreSQL, generated expression có các giới hạn, bao gồm yêu cầu phù hợp về tính bất biến và không dùng subquery tham chiếu bảng khác.
- Định nghĩa **cùng hàng** không tự giải được “tổng tiền toàn bộ đơn = tổng các dòng đơn”, vì đó là phép tổng hợp **nhiều hàng**.

### DEFAULT khác generated column

`DEFAULT` đặt giá trị khi cột không được cung cấp lúc INSERT. Generated column luôn được tính theo expression khi hàng thay đổi theo quy tắc DBMS và thường **không cho phép user tự ghi một giá trị tùy ý vào cột đó**.

Không nên viết một trigger sao chép giá trị tính toán nếu DBMS đã cung cấp generated/computed column phù hợp và không có yêu cầu đặc biệt khác.

## 16. Bài thực hành PostgreSQL: tạo schema không cần trigger

Phần này tạo một mô hình bán hàng nhỏ, trong đó các quy tắc cơ bản đều được bảo vệ **không cần trigger tự viết**.

Môi trường: PostgreSQL hiện đại hỗ trợ identity và stored generated column. Chỉ thực hiện trong database học tập; các lệnh tạo/xóa đối tượng không dành cho dữ liệu sản xuất.

### 16.1. Tạo schema và bảng khách hàng

```sql
CREATE SCHEMA sql357;

CREATE TABLE sql357.customers (
    customer_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    CONSTRAINT uq_sql357_customers_email UNIQUE (email)
);
```

Các nguyên tắc:

- `PRIMARY KEY` cho ID.
- `NOT NULL` cho tên và email.
- `UNIQUE` cho email.

Ví dụ này kiểm tra trùng **chuỗi email đúng theo quy tắc so sánh của database**, chưa tự chuẩn hóa khoảng trắng, Unicode hoặc hoa/thường. Nếu muốn coi `A@example.invalid` và `a@example.invalid` là cùng địa chỉ, cần thiết kế normalization/collation/index phù hợp, không suy rằng `UNIQUE(TEXT)` mặc định đã xử lý.

### 16.2. Tạo bảng sản phẩm

```sql
CREATE TABLE sql357.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    list_price NUMERIC(12,2) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT uq_sql357_products_sku UNIQUE (sku),
    CONSTRAINT ck_sql357_products_price
        CHECK (list_price >= 0)
);
```

Ở đây:

- `active DEFAULT TRUE`: giá trị mặc định cho sản phẩm mới.
- `list_price NOT NULL CHECK >= 0`: giá hiện tại không thể âm và không thể NULL.
- `sku UNIQUE`: ngăn trùng SKU.

Không có trigger để kiểm tra `list_price` hoặc tồn tại SKU.

### 16.3. Tạo bảng đơn hàng

```sql
CREATE TABLE sql357.orders (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    confirmed_at TIMESTAMPTZ,

    CONSTRAINT fk_sql357_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES sql357.customers(customer_id)
        ON DELETE RESTRICT,

    CONSTRAINT ck_sql357_orders_status
        CHECK (status IN (
            'DRAFT', 'CONFIRMED', 'PAID', 'CANCELLED'
        )),

    CONSTRAINT ck_sql357_orders_paid_confirmed
        CHECK (status <> 'PAID' OR confirmed_at IS NOT NULL),

    CONSTRAINT ck_sql357_orders_dates
        CHECK (
            confirmed_at IS NULL
            OR confirmed_at >= created_at
        )
);
```

Ở đây có nhiều loại quy tắc, tất cả đều khai báo được:

| Quy tắc | Thành phần |
| --- | --- |
| Sinh ID nếu không truyền | `GENERATED BY DEFAULT AS IDENTITY` |
| Tạo lúc hiện tại nếu bỏ qua cột | `DEFAULT CURRENT_TIMESTAMP` |
| Trạng thái mặc định DRAFT | `DEFAULT 'DRAFT'` |
| Trạng thái không được NULL | `NOT NULL` |
| Trạng thái thuộc tập hợp cho phép | `CHECK status IN (...)` |
| Đơn PAID bắt buộc có thời điểm xác nhận | `CHECK (status <> 'PAID' OR confirmed_at IS NOT NULL)` |
| Thời điểm xác nhận không trước thời điểm tạo | `CHECK (confirmed_at IS NULL OR confirmed_at >= created_at)` |
| Customer tham chiếu phải tồn tại | `FOREIGN KEY` |
| Không xóa customer đang có đơn | `ON DELETE RESTRICT` |

Điều **chưa** được bảo vệ: trạng thái **đã từng** chuyển qua những bước nào. Một hàng hiện tại có `status = 'PAID'` và `confirmed_at` hợp lệ chưa nói lên trạng thái trước đó là `DRAFT` hay `CONFIRMED`. Phần sau chỉ ra khi nào cần trigger/procedure.

### 16.4. Tạo bảng dòng đơn

```sql
CREATE TABLE sql357.order_lines (
    order_line_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC(12,2) NOT NULL,
    discount_pct NUMERIC(5,2) NOT NULL DEFAULT 0,
    line_total NUMERIC(16,2)
        GENERATED ALWAYS AS (
            quantity * unit_price * (1 - discount_pct / 100)
        ) STORED,

    CONSTRAINT ck_sql357_lines_quantity
        CHECK (quantity > 0),

    CONSTRAINT ck_sql357_lines_price
        CHECK (unit_price >= 0),

    CONSTRAINT ck_sql357_lines_discount
        CHECK (discount_pct BETWEEN 0 AND 100),

    CONSTRAINT fk_sql357_lines_order
        FOREIGN KEY (order_id)
        REFERENCES sql357.orders(order_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_sql357_lines_product
        FOREIGN KEY (product_id)
        REFERENCES sql357.products(product_id)
        ON DELETE RESTRICT
);
```

Hệ thống áp dụng:

- Số lượng mặc định 1, nhưng bắt buộc dương.
- Giảm giá mặc định 0, nhưng không thể âm hoặc vượt 100.
- Đơn giá không âm.
- Tổng dòng được tính từ ba cột cùng hàng.
- Mỗi dòng phải thuộc đơn tồn tại và tham chiếu sản phẩm tồn tại.
- Xóa đơn trong lab làm các dòng đơn bị xóa theo; không tự động xóa sản phẩm.

**Đây là quyết định minh họa**: trong sản phẩm thực, `ON DELETE CASCADE` đối với chứng từ bán hàng có thể không phù hợp vì yêu cầu lưu trữ; cần chọn chính sách xóa theo nghiệp vụ.

### 16.5. Index bảng con cho FK thường xuyên dùng

```sql
CREATE INDEX ix_sql357_orders_customer
ON sql357.orders(customer_id);

CREATE INDEX ix_sql357_lines_order
ON sql357.order_lines(order_id);

CREATE INDEX ix_sql357_lines_product
ON sql357.order_lines(product_id);
```

Index không phải luôn bắt buộc để FK hợp lệ. Chúng có thể giúp JOIN, tra cứu dòng con và kiểm tra khi xóa/cập nhật khóa cha, tùy số lượng và workload. Với bảng lab nhỏ, plan có thể vẫn chọn sequential scan.

## 17. Chèn dữ liệu hợp lệ: quan sát DEFAULT và CHECK

### 17.1. Khách hàng và sản phẩm

```sql
INSERT INTO sql357.customers
    (customer_id, full_name, email)
VALUES
    (1, 'An', 'an@example.invalid'),
    (2, 'Bình', 'binh@example.invalid');

INSERT INTO sql357.products
    (product_id, sku, product_name, list_price)
VALUES
    (101, 'BOOK-SQL', 'Sách SQL', 120000.00),
    (102, 'NOTE-A5', 'Sổ ghi chú', 50000.00);
```

Cột `active` bị bỏ qua nên nhận `TRUE`.

```sql
SELECT product_id, sku, active
FROM sql357.products
ORDER BY product_id;
```

Kết quả mong đợi: hai sản phẩm đều `active = true`.

### 17.2. Tạo đơn không truyền status hay created_at

```sql
INSERT INTO sql357.orders
    (order_id, customer_id)
VALUES
    (5001, 1)
RETURNING order_id, customer_id, created_at, status;
```

Kết quả:

- `order_id = 5001`.
- `customer_id = 1`.
- `created_at` được database đặt.
- `status = 'DRAFT'`.

Bởi dùng `GENERATED BY DEFAULT AS IDENTITY`, lab cho phép truyền ID 5001 tường minh để kiểm tra dễ hơn. Trong ứng dụng thực, thường bỏ cột ID và đọc giá trị do database sinh bằng `RETURNING`, rồi dùng ID đó cho các dòng chi tiết.

### 17.3. Tạo dòng đơn, dùng mặc định giảm giá

```sql
INSERT INTO sql357.order_lines
    (order_line_id, order_id, product_id, quantity, unit_price)
VALUES
    (1, 5001, 101, 2, 120000.00),
    (2, 5001, 102, 1,  50000.00);

SELECT
    order_line_id,
    order_id,
    product_id,
    quantity,
    unit_price,
    discount_pct,
    line_total
FROM sql357.order_lines
ORDER BY order_line_id;
```

Kết quả:

| order_line_id | quantity | unit_price | discount_pct | line_total |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 120000.00 | 0.00 | 240000.00 |
| 2 | 1 | 50000.00 | 0.00 | 50000.00 |

Tổng hai dòng là **290000.00**, chưa tính phí vận chuyển/thuế nếu sản phẩm thực có.

### 17.4. UPDATE cùng hàng: generated column tự cập nhật

```sql
UPDATE sql357.order_lines
SET discount_pct = 10
WHERE order_line_id = 1
RETURNING
    order_line_id,
    quantity,
    unit_price,
    discount_pct,
    line_total;
```

Dòng 1 có `line_total = 216000.00` vì:

\[
2 \times 120000 \times (1 - 10/100) = 216000
\]

Không cần trigger `AFTER UPDATE` sửa `line_total`. Tổng hai dòng lúc này là **266000.00**.

Chú ý: `line_total` là generated column nên không nên cố `INSERT` hoặc `UPDATE` trực tiếp một giá trị tự chọn vào đó. Các DBMS có quy tắc về generated column khác nhau.

## 18. Thử lỗi CHECK: dữ liệu không hợp lệ bị từ chối

Chạy **từng câu riêng biệt** trong PostgreSQL, vì các ví dụ cố ý phát sinh lỗi.

### 18.1. Số lượng âm

```sql
-- Dự kiến lỗi CHECK ck_sql357_lines_quantity.
INSERT INTO sql357.order_lines
    (order_id, product_id, quantity, unit_price)
VALUES
    (5001, 101, -1, 100000.00);
```

DBMS từ chối vì `quantity > 0` là FALSE.

### 18.2. Giảm giá lớn hơn 100

```sql
-- Dự kiến lỗi CHECK ck_sql357_lines_discount.
INSERT INTO sql357.order_lines
    (order_id, product_id, quantity, unit_price, discount_pct)
VALUES
    (5001, 101, 1, 100000.00, 120);
```

Không cần trigger tính lại rồi từ chối khi giảm giá bất hợp lệ; `CHECK` xử lý trực tiếp.

### 18.3. Giá âm

```sql
-- Dự kiến lỗi CHECK ck_sql357_products_price.
INSERT INTO sql357.products
    (product_id, sku, product_name, list_price)
VALUES
    (103, 'INVALID', 'Sản phẩm sai', -5);
```

### 18.4. Trạng thái ngoài danh sách

```sql
-- Dự kiến lỗi CHECK ck_sql357_orders_status.
INSERT INTO sql357.orders
    (order_id, customer_id, status)
VALUES
    (5002, 1, 'UNKNOWN');
```

### 18.5. Đơn PAID nhưng không có confirmed_at

```sql
-- Dự kiến lỗi CHECK ck_sql357_orders_paid_confirmed.
UPDATE sql357.orders
SET status = 'PAID'
WHERE order_id = 5001;
```

Đây là ví dụ ràng buộc **giữa hai cột cùng hàng**. Muốn cho phép:

```sql
UPDATE sql357.orders
SET
    status = 'PAID',
    confirmed_at = CURRENT_TIMESTAMP
WHERE order_id = 5001;
```

Câu UPDATE thứ hai thỏa CHECK nếu thời điểm xác nhận không trước thời điểm tạo.

**Đặc biệt:** CHECK kiểm tra **trạng thái hàng cuối của statement**, không biết quá khứ chuyển từ status nào. Nếu cho phép chỉ `DRAFT -> CONFIRMED -> PAID` theo thứ tự, CHECK trên hàng hiện tại chưa đủ.

## 19. Thử lỗi FOREIGN KEY: không cần trigger kiểm tra tồn tại

### 19.1. Khách hàng không tồn tại

```sql
-- Dự kiến lỗi FOREIGN KEY fk_sql357_orders_customer.
INSERT INTO sql357.orders
    (order_id, customer_id)
VALUES
    (5003, 9999);
```

Không có customer 9999 nên `INSERT` bị từ chối.

### 19.2. Sản phẩm không tồn tại

```sql
-- Dự kiến lỗi FOREIGN KEY fk_sql357_lines_product.
INSERT INTO sql357.order_lines
    (order_id, product_id, quantity, unit_price)
VALUES
    (5001, 9999, 1, 10000.00);
```

### 19.3. Không xóa được customer đang có đơn

```sql
-- Dự kiến lỗi FK vì customer 1 vẫn được orders tham chiếu.
DELETE FROM sql357.customers
WHERE customer_id = 1;
```

### 19.4. CASCADE không cần trigger tự viết

Nếu trong lab thực hiện:

```sql
-- CHỈ khi muốn dọn riêng đơn 5001 trong môi trường thử:
-- DELETE FROM sql357.orders WHERE order_id = 5001;
```

thì do FK `ON DELETE CASCADE`, các `order_lines` của đơn đó được xóa theo. Không cần trigger duyệt từng dòng con. Dòng lệnh được **comment để tránh phá dữ liệu đang dùng cho các bài tập tiếp theo**.

## 20. Thử lỗi UNIQUE và NOT NULL

### 20.1. Email trùng

```sql
-- Dự kiến lỗi UNIQUE uq_sql357_customers_email.
INSERT INTO sql357.customers
    (customer_id, full_name, email)
VALUES
    (3, 'Cường', 'an@example.invalid');
```

### 20.2. Truyền NULL cho cột có DEFAULT + NOT NULL

```sql
-- Dự kiến lỗi NOT NULL: DEFAULT không thay NULL tường minh.
INSERT INTO sql357.orders
    (order_id, customer_id, status)
VALUES
    (5004, 1, NULL);
```

Mặc định `'DRAFT'` chỉ được dùng khi bỏ cột hoặc yêu cầu `DEFAULT`, chứ không tự thay `NULL`.

### 20.3. UPDATE cũng bị constraint bảo vệ

```sql
-- Dự kiến lỗi CHECK, không phải chỉ khi INSERT.
UPDATE sql357.products
SET list_price = -100
WHERE product_id = 101;
```

Các ràng buộc vẫn bảo vệ **UPDATE**, không chỉ lúc tạo dữ liệu.

Trong PostgreSQL, lỗi vi phạm CHECK/FK/UNIQUE/NOT NULL có SQLSTATE tương ứng, giúp application phân loại mà không parse nội dung thông điệp. Khi kiểm thử các câu lỗi trong transaction `BEGIN`, cần `ROLLBACK` nếu transaction bị đánh dấu failed.

## 21. Giao dịch và tính đồng thời: ràng buộc hơn kiểm tra thủ công ở đâu?

Một trigger giả lập FK có thể:

1. `SELECT` bảng cha để xem có tồn tại không.
2. Nếu có, cho phép ghi vào bảng con.

Nhưng ở thời điểm khác, một transaction đang xóa hàng cha. Nếu trigger và ứng dụng không có chiến lược khóa/isolation đúng, kiểm tra trước có thể không ngăn được trạng thái tham chiếu sai trong mọi kịch bản cạnh tranh.

FK của DBMS thực hiện kiểm tra tham chiếu phối hợp với hệ giao dịch theo cơ chế nội bộ. Điều tương tự đúng với unique index: hai phiên cùng chèn một khóa sẽ được hệ xử lý xung đột, không thể cùng “vượt qua” bằng một câu kiểm tra tồn tại đơn giản.

### Ví dụ race condition khi tự kiểm tra SKU

```text
Session A                     Session B
---------                     ---------
SELECT sku='X' -> không thấy
                              SELECT sku='X' -> không thấy
INSERT sku='X'                INSERT sku='X'
             \                 /
              \               /
               UNIQUE constraint
               bảo vệ tính duy nhất
```

Nếu không có UNIQUE, cả hai có thể tự cho rằng “đã kiểm tra” rồi ghi trùng. Dùng trigger kiểm tra `EXISTS` không tự giải quyết race nếu không khóa đúng.

**Không nên bỏ constraint sau khi bổ sung kiểm tra trong application hoặc trigger.** Kiểm tra sớm giúp trả thông báo tốt hơn; constraint là lớp bảo vệ cuối khi nhiều đường ghi và nhiều transaction cùng thao tác.

## 22. CHECK và FK khác nhau về thời điểm kiểm tra

Với PostgreSQL:

- `CHECK` và `NOT NULL` thông thường được kiểm tra theo thao tác ghi và **không phải constraint có thể defer** trong PostgreSQL.
- `FOREIGN KEY` có thể được khai báo `DEFERRABLE` để trì hoãn việc kiểm tra trong một transaction theo quy tắc của DBMS.
- `UNIQUE`/`PRIMARY KEY` có một số biến thể deferrable trong PostgreSQL.
- `RESTRICT` thường không có hành vi trì hoãn giống `NO ACTION` ở trường hợp cần defer.

Ví dụ ý tưởng:

```sql
CREATE TABLE parent_demo (
    id INTEGER PRIMARY KEY
);

CREATE TABLE child_demo (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER,
    CONSTRAINT fk_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES parent_demo(id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Trong một transaction phù hợp, có thể insert con trước, cha sau và khi tới thời điểm kiểm tra FK, quan hệ cuối đã hợp lệ. Đây là ví dụ về **thời điểm kiểm tra ràng buộc**, không phải một lý do để dùng trigger thay FK.

Một số DBMS không hỗ trợ deferred FK theo cùng cú pháp hoặc cùng ngữ nghĩa. Đừng chuyển nguyên câu này sang MySQL/SQL Server rồi giả định chạy được.

## 23. Khi nào trigger thực sự có giá trị?

Ba nhóm bài toán lớn thường được cân nhắc.

### 23.1. Cần biết trạng thái **trước và sau**

Ví dụ:

- Chỉ cho phép `DRAFT -> CONFIRMED -> PAID`.
- Không cho đổi `PAID` thành `DRAFT`.
- Không cho sửa `unit_price` của một dòng đã được chốt.
- Cấm thay khóa nghiệp vụ sau khi đã sử dụng.

CHECK chỉ nhìn **hàng hiện tại**, không có `OLD.status` để so với `NEW.status`. Trigger `BEFORE UPDATE` có thể kiểm tra sự chuyển đổi, hoặc application/procedure có thể quản lý trạng thái.

### 23.2. Cần ghi lịch sử thay đổi

Ví dụ lưu:

| entity_id | old_status | new_status | changed_at |
| --- | --- | --- | --- |
| 5001 | DRAFT | CONFIRMED | ... |
| 5001 | CONFIRMED | PAID | ... |

`DEFAULT` không ghi được sự kiện chuyển trạng thái. Trigger `AFTER UPDATE` hoặc hệ CDC/auditing chuyên dụng có thể phù hợp, với thiết kế transaction và quyền rõ ràng.

### 23.3. Cần phản ứng với nhiều bảng/hàng theo sự kiện

Ví dụ cần cập nhật bảng tổng hợp khi dòng đơn thêm/xóa, hoặc đồng bộ một trạng thái liên quan trong cùng database. Trigger có thể là một lựa chọn **nếu việc này phải gắn chặt với transaction ghi nguồn**.

Nhưng phải cân nhắc:

- Tổng hợp lại bằng view/materialized view có đáp ứng không?
- Dữ liệu tổng hợp có bắt buộc đồng bộ tức thì không?
- Một statement cập nhật 10.000 hàng sẽ làm trigger chạy bao nhiêu lần?
- Có xử lý DELETE, UPDATE, INSERT đủ các nhánh không?
- Có nguy cơ deadlock, recursion, double update hay không?
- Có thể dùng procedure thao tác tập hợp hiệu quả hơn không?

**Không dùng trigger như “cái búa” cho mọi nghiệp vụ phức tạp**, đặc biệt với side effect không rollback được như gửi email hoặc gọi API bên ngoài.

## 24. Ví dụ trigger hợp lý: cấm chuyển trạng thái lùi

Ở PostgreSQL, sau khi có bảng lab, có thể dùng trigger để bảo vệ một quy tắc **chuyển trạng thái** không thể diễn đạt chỉ bằng CHECK trên một hàng.

Ví dụ nghiệp vụ đơn giản:

- `DRAFT -> CONFIRMED` hợp lệ.
- `CONFIRMED -> PAID` hợp lệ.
- Chuyển từ bất kỳ trạng thái nào sang `CANCELLED` chỉ cho phép khi chưa PAID.
- Không cho chỉnh status từ `PAID` hoặc `CANCELLED` về trạng thái trước.
- Không đổi trạng thái thành chính nó là một phép cập nhật không làm thay đổi transition.

Tạo function:

```sql
CREATE OR REPLACE FUNCTION sql357.guard_order_status()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    IF OLD.status = 'DRAFT'
       AND NEW.status IN ('CONFIRMED', 'CANCELLED') THEN
        RETURN NEW;
    END IF;

    IF OLD.status = 'CONFIRMED'
       AND NEW.status IN ('PAID', 'CANCELLED') THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION USING
        ERRCODE = '23514',
        MESSAGE = 'Chuyển trạng thái đơn hàng không hợp lệ',
        DETAIL = format(
            'order_id=%s: %s -> %s',
            OLD.order_id, OLD.status, NEW.status
        );
END;
$$;
```

Gắn trigger:

```sql
CREATE TRIGGER trg_sql357_order_status
BEFORE UPDATE OF status ON sql357.orders
FOR EACH ROW
EXECUTE FUNCTION sql357.guard_order_status();
```

Bây giờ:

```sql
-- Với đơn 5001 còn DRAFT:
UPDATE sql357.orders
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE order_id = 5001;
```

là hợp lệ.

Tiếp theo:

```sql
UPDATE sql357.orders
SET status = 'PAID'
WHERE order_id = 5001;
```

là hợp lệ **nếu** thời điểm `confirmed_at` đã có và không trước `created_at`; các CHECK vẫn áp dụng.

Nhưng:

```sql
-- Dự kiến lỗi do trigger:
UPDATE sql357.orders
SET status = 'DRAFT'
WHERE order_id = 5001;
```

sẽ bị từ chối. CHECK đơn thuần không biết trạng thái cũ là PAID để làm việc này.

### Vì sao vẫn giữ DEFAULT, CHECK và FK?

Trigger trên chỉ xử lý **transition khi UPDATE OF status**. Nó không thay thế:

- `DEFAULT 'DRAFT'` lúc tạo đơn.
- `NOT NULL` và CHECK danh sách trạng thái.
- CHECK yêu cầu thời điểm xác nhận cho PAID.
- FK yêu cầu customer tồn tại.

Ví dụ này minh họa sự **bổ sung**, không cạnh tranh: **constraint bảo vệ trạng thái hợp lệ; trigger bảo vệ quy trình chuyển từ trạng thái cũ sang trạng thái mới.**

### Giới hạn của ví dụ

Trigger chỉ chạy cho `UPDATE OF status`. Một câu `INSERT` có thể truyền thẳng `status='PAID'` và `confirmed_at` hợp lệ vì CHECK cho phép; nếu nghiệp vụ bắt buộc mọi đơn phải bắt đầu từ DRAFT, cần thêm quy tắc tại `INSERT` hoặc buộc mọi thao tác qua API/procedure phù hợp. Không nên tưởng trigger `BEFORE UPDATE OF status` đã bao phủ cả việc tạo mới.

Đây là ví dụ học tập; hệ thực có thể cần nhiều trạng thái, phân quyền người dùng, audit và bảng transition policy riêng.

## 25. Có nên dùng trigger để chép đơn giá từ bảng sản phẩm?

Một yêu cầu khác:

> “Khi chèn `order_lines` mà không truyền `unit_price`, lấy `products.list_price` tại thời điểm đó.”

`DEFAULT` thông thường không thể tham chiếu động tới dòng ở **bảng khác** theo ID được truyền trong cùng hàng. `CHECK` không làm nhiệm vụ điền dữ liệu; `FOREIGN KEY` chỉ xác nhận sản phẩm tồn tại, không chép giá.

Lựa chọn cần đánh giá:

1. **Ứng dụng/procedure** đọc giá, xác thực quyền mua/chiết khấu và ghi snapshot `unit_price` trong **cùng transaction**, với chiến lược đồng thời rõ ràng.
2. **Trigger BEFORE INSERT** lấy giá sản phẩm nếu đây là quy tắc bắt buộc ở tầng database cho mọi đường ghi; cần xử lý product bị xóa/đổi giá, quyền, khóa, kiểm thử.
3. **Không lưu giá snapshot** và luôn JOIN giá hiện tại — thường **không phù hợp** nếu phải giữ nguyên giá lịch sử của đơn.

Nếu có nhiều kênh bán, khuyến mãi, giá theo vùng và thuế, logic tính giá có thể phức tạp; không nên nhét toàn bộ vào trigger chỉ để tránh gọi procedure.

**Kết luận:** đây là ví dụ **không giải được bằng DEFAULT đơn giản**, nhưng trigger cũng **không đương nhiên là lựa chọn tốt nhất**.

## 26. Trường hợp dữ liệu cần kiểm tra nhiều hàng: không dùng CHECK giả lập

Ví dụ quy tắc:

> “Không được có hai lịch đặt phòng trùng thời gian cho cùng một phòng.”

Điều kiện này liên quan **nhiều hàng**, không phải hai cột của cùng một hàng. CHECK như:

```sql
CHECK (ends_at > starts_at)
```

chỉ bảo đảm từng khoảng riêng lẻ hợp lệ, **không chặn hai khoảng chồng nhau**.

Trên PostgreSQL, có thể xem xét **exclusion constraint** với range và toán tử thích hợp, ví dụ khái niệm:

```sql
-- Ý tưởng PostgreSQL: cần kiểu dữ liệu, extension và
-- thiết kế range phù hợp trước khi dùng ở hệ thật.
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
```

Cơ chế này có thể giải quyết một số bất biến giao nhau mà không cần trigger tự kiểm tra `SELECT EXISTS` dễ race. Nó là tính năng chuyên biệt, không có cú pháp hoàn toàn tương đương trên mọi DBMS.

Nếu DBMS không có constraint phù hợp, trigger/procedure có thể cần thiết, nhưng phải kiểm soát **đồng thời và isolation**. Một trigger “SELECT xem có hàng giao nhau không rồi INSERT” **không tự bảo đảm đúng** khi hai transaction cùng chạy.

## 27. Trigger và dữ liệu tổng hợp giữa nhiều hàng

Ví dụ “`orders.total_amount` phải bằng tổng `order_lines.line_total`”.

Một CHECK trên bảng `orders` không thể trực tiếp dùng:

```sql
-- Ý tưởng KHÔNG phù hợp làm CHECK cùng hàng:
CHECK (orders.total_amount = (
    SELECT SUM(line_total)
    FROM order_lines
    WHERE order_id = orders.order_id
))
```

Nếu muốn lưu tổng tiền vật lý, có vài chiến lược:

- **Không lưu tổng:** tính bằng query `SUM(line_total) GROUP BY order_id` khi cần.
- **View:** công bố tổng đã tính mà không tạo dữ liệu sao chép.
- **Materialized view/bảng tổng hợp:** chấp nhận độ trễ và có lịch refresh.
- **Procedure transactional:** mỗi thay đổi chi tiết cập nhật tổng theo chiến lược khóa rõ ràng.
- **Trigger:** duy trì tổng đồng bộ khi dòng được thêm/sửa/xóa, nhưng phải xử lý nhiều dòng, nhiều nhánh và race.

Khi dùng trigger duy trì aggregate, các lỗi thường gặp:

1. Chỉ xử lý `INSERT`, quên `UPDATE quantity` và `DELETE`.
2. Cập nhật tổng bằng số tiền cũ/thay đổi không đúng khi UPDATE.
3. Deadlock do khóa header và lines theo thứ tự khác nhau.
4. Xử lý từng dòng quá tốn kém trên bulk import.
5. Đếm trùng vì application cũng cập nhật tổng.
6. Chưa kiểm tra cuối transaction khi nhiều thao tác liên tiếp.

**Một số quy tắc nhiều hàng thậm chí cần kiểm tra ở cuối transaction**, thay vì bắt buộc đúng ở mọi thời điểm trung gian. Thiết kế constraint/procedure/trigger phải phản ánh đúng thời điểm đó.

## 28. Trigger không nên làm việc ngoài transaction khó rollback

Các side effect như:

- Gửi email xác nhận đơn.
- Gọi HTTP API.
- Gửi thông báo push.
- Ghi file ngoài DB.
- Thực hiện thanh toán qua nhà cung cấp.

thường không nên thực hiện trực tiếp trong trigger nếu thao tác đó không thể rollback cùng transaction database. Có thể xảy ra:

```text
UPDATE orders SET status='PAID'
      |
      v
Trigger gửi email "đã thanh toán"
      |
      v
Transaction DB sau đó ROLLBACK
      |
      v
Email đã gửi nhưng database nói chưa PAID
```

Một thiết kế thường an toàn hơn là **transactional outbox**:

1. Trong cùng transaction, ghi thay đổi nghiệp vụ và bản ghi sự kiện vào **bảng outbox**.
2. Khi commit thành công, một worker bên ngoài đọc sự kiện đã commit.
3. Worker gửi email/API với cơ chế **retry + idempotency**.
4. Ghi nhận trạng thái xử lý, tránh gửi trùng khi worker crash/retry.

Trigger có thể là một cách ghi outbox nếu thực sự cần ghi ở tầng DB, nhưng **không đồng nghĩa trigger nên trực tiếp gọi hệ thống ngoài**.

## 29. Hiệu năng và khả năng quan sát

### 29.1. Chi phí trigger per-row và per-statement

Một số DBMS có trigger theo **mỗi hàng** và trigger theo **mỗi câu lệnh**. Nếu cập nhật 100.000 hàng:

- Trigger per-row có thể thực thi logic 100.000 lần.
- Trigger per-statement có thể xử lý tập hàng theo một lần gọi, tùy cách cung cấp dữ liệu old/new của DBMS.
- Trigger tự query thêm bảng có thể tạo lượng I/O và lock lớn ngoài câu SQL gốc.

Ví dụ PostgreSQL:

```sql
UPDATE sql357.products
SET active = FALSE
WHERE product_id IN (101, 102);
```

Nếu có trigger BEFORE UPDATE FOR EACH ROW, nó có thể chạy một lần cho mỗi hàng bị cập nhật. Nếu quy tắc chỉ là `active` không được NULL, `NOT NULL DEFAULT TRUE` đơn giản hơn và không thêm logic thủ tục.

### 29.2. Các ràng buộc cũng có chi phí

- `CHECK` đánh giá biểu thức ở các thao tác ghi liên quan.
- `UNIQUE` phải duy trì index.
- `FOREIGN KEY` cần kiểm tra tham chiếu và có thể khóa/đọc index.
- `ON DELETE CASCADE` có thể ảnh hưởng rất nhiều hàng.

Vì vậy không thể kết luận “constraint luôn nhanh hơn trigger” bằng một con số tuyệt đối. Nhưng nếu DBMS có primitive đúng bài toán, constraint thường **dễ hiểu, ít sai và dễ tối ưu/quan sát** hơn logic thủ công tương đương.

### 29.3. Metadata và thông báo lỗi

Constraint có tên giúp log và test xác định chính xác vi phạm:

- `ck_sql357_lines_quantity`.
- `fk_sql357_orders_customer`.
- `uq_sql357_products_sku`.

Ở PostgreSQL, error code thường là:

| Vi phạm | SQLSTATE |
| --- | --- |
| `NOT NULL` | `23502` |
| `FOREIGN KEY` | `23503` |
| `UNIQUE` | `23505` |
| `CHECK` | `23514` |

Ứng dụng có thể map lỗi sang thông báo nghiệp vụ ổn định. **Không nên parse nguyên văn message** vì văn bản có thể thay đổi theo phiên bản/ngôn ngữ.

Nếu chỉ cần thông báo người dùng dễ hiểu, **không nhất thiết phải đổi constraint thành trigger**. Tầng ứng dụng có thể tra SQLSTATE và tên constraint để tạo thông điệp phù hợp.

## 30. Thay đổi schema và bổ sung constraint trên dữ liệu cũ

Nếu bảng đã có dữ liệu không hợp lệ, thêm constraint có thể thất bại vì các hàng cũ vi phạm. Không nên bỏ qua việc kiểm tra rồi thay bằng trigger chỉ để “cho triển khai chạy”.

Một quy trình di chuyển an toàn:

1. Xác định quy tắc chính xác và dữ liệu hiện tại.
2. Tìm hàng sai trước khi thêm constraint.
3. Sửa dữ liệu hoặc làm rõ ngoại lệ nghiệp vụ.
4. Thêm constraint theo cơ chế DBMS.
5. Validate dữ liệu cũ.
6. Theo dõi lỗi ghi mới và sửa ứng dụng nếu cần.
7. Chỉ bỏ trigger cũ khi đã xác minh không còn logic phụ nào bị mất.

### PostgreSQL: NOT VALID cho CHECK/FK trong migration

Ví dụ trên bảng thực hành đã tạo:

```sql
-- Minh họa thêm một điều kiện mới:
ALTER TABLE sql357.products
ADD CONSTRAINT ck_sql357_products_price_upper
CHECK (list_price <= 1000000000)
NOT VALID;
```

Trong PostgreSQL, `NOT VALID` cho phép thêm một số constraint như CHECK hoặc FK mà **chưa quét kiểm tra toàn bộ hàng cũ ngay lúc thêm**, nhưng constraint mới vẫn bảo vệ **dữ liệu được thêm hoặc cập nhật** theo quy tắc thích hợp.

Sau khi dọn dữ liệu cũ:

```sql
ALTER TABLE sql357.products
VALIDATE CONSTRAINT ck_sql357_products_price_upper;
```

Không suy rằng `NOT VALID` khiến constraint “không hoạt động”: nó **chưa xác thực dữ liệu lịch sử**, khác với việc tắt kiểm tra ghi mới.

**Chú ý:** `NOT VALID` không áp dụng tùy ý cho mọi loại constraint và syntax mỗi DBMS khác nhau. PostgreSQL hỗ trợ cho CHECK/FK theo điều kiện cụ thể; không sao chép sang `NOT NULL` hoặc `UNIQUE` như một mẫu chung.

## 31. ALTER DEFAULT và ALTER CHECK không đồng nghĩa sửa dữ liệu cũ

Ví dụ:

```sql
ALTER TABLE sql357.products
ALTER COLUMN active SET DEFAULT FALSE;
```

Lệnh thay DEFAULT áp dụng cho **những lần ghi tiếp theo khi cột bị bỏ qua**, không tự sửa toàn bộ hàng đã có `active=TRUE`.

Tương tự, thêm:

```sql
ALTER TABLE sql357.products
ADD CONSTRAINT ck_sql357_products_nonnegative
CHECK (list_price >= 0);
```

nếu thực hiện trên bảng đã có dữ liệu, PostgreSQL thường phải kiểm tra hàng hiện có, trừ khi dùng đường migration cụ thể như `NOT VALID`. Vì lab đã có constraint giá không âm, lệnh thêm điều kiện thứ hai chỉ mang tính minh họa, không cần chạy trong bài thực hành.

Với thay đổi trạng thái nghiệp vụ, việc sửa `DEFAULT`, bổ sung `CHECK` và **migrate các hàng cũ** là ba công việc riêng.

## 32. Kỷ luật đặt tên constraint và cấu trúc rõ ràng

Nên đặt tên constraint tường minh:

```sql
CONSTRAINT ck_order_lines_quantity CHECK (quantity > 0),
CONSTRAINT fk_order_lines_order
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
CONSTRAINT uq_products_sku UNIQUE (sku)
```

Lợi ích:

- Dễ nhận diện nguồn lỗi trong log.
- Migrations có tên đối tượng ổn định để `DROP CONSTRAINT` hoặc thay thế.
- Review dữ liệu biết quy tắc nào đang bảo vệ.
- Unit/integration test có thể khẳng định điều kiện chính xác.
- Dễ phân biệt nhiều FK tới cùng bảng.

Tuy nhiên cần tuân thủ giới hạn độ dài identifier và quy tắc chữ hoa/thường của DBMS. Đừng tạo tên có thông tin nhạy cảm hoặc dựa hoàn toàn vào tên mặc định có thể thay đổi khi sửa schema.

### Tra cứu metadata PostgreSQL

Ví dụ:

```sql
SELECT
    conname,
    contype,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'sql357.orders'::regclass
ORDER BY conname;
```

Trong PostgreSQL, `contype` dùng ký hiệu cho PK/UNIQUE/FK/CHECK và các loại khác. Truy vấn metadata giúp xác minh constraint thật được lưu trong database mà không cần đoán từ mã application.

Có thể kiểm tra cột default/generation bằng các công cụ introspection của DBMS hoặc `information_schema` phù hợp, tùy hệ.

## 33. MySQL/MariaDB: chú ý phiên bản và storage engine

MySQL/MariaDB hỗ trợ DEFAULT, CHECK và FK với những khác biệt lịch sử.

### DEFAULT

```sql
-- Ý tưởng MySQL/MariaDB:
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
);
```

Cột AUTO_INCREMENT đảm nhiệm sinh ID; không cần trigger tự lấy MAX(id)+1.

### CHECK

```sql
-- Cú pháp trên các phiên bản hiện đại hỗ trợ CHECK thực thi:
CREATE TABLE items (
    item_id BIGINT PRIMARY KEY,
    quantity INT NOT NULL,
    CONSTRAINT chk_items_quantity CHECK (quantity > 0)
);
```

**Rất quan trọng:** một số **phiên bản MySQL cũ** từng chấp nhận/parsing CHECK nhưng **không thực thi kiểm tra**; MySQL bắt đầu thực thi CHECK từ phiên bản **8.0.16**. Với MariaDB, cần xác minh hành vi theo phiên bản cụ thể. Không chỉ nhìn DDL có từ khóa CHECK rồi kết luận dữ liệu đang được bảo vệ.

### FOREIGN KEY

Trên MySQL, FK có hiệu lực phụ thuộc storage engine (thông dụng là **InnoDB**) và các yêu cầu về index/kiểu dữ liệu. Cần tránh dựa vào engine không hỗ trợ FK hoặc cấu hình tắt kiểm tra FK.

Các chi tiết `NO ACTION`, `RESTRICT` và deferred checking có thể khác PostgreSQL. Không mặc định MySQL có `DEFERRABLE INITIALLY DEFERRED` như PostgreSQL.

### Trigger có nên thay CHECK vì phiên bản cũ?

Nếu hệ cũ thiếu CHECK thực thi, trigger có thể là workaround. Nhưng đó là **quyết định tương thích có lý do**, cần ghi rõ phiên bản, test và kế hoạch nâng cấp. Không mang workaround legacy sang hệ hiện đại như một tiêu chuẩn mặc định.

## 34. SQL Server: DEFAULT constraint, CHECK, FK và computed column

SQL Server hỗ trợ các cơ chế khai báo tương ứng:

```sql
-- SQL Server minh họa:
CREATE TABLE dbo.Items (
    ItemId BIGINT IDENTITY(1,1) PRIMARY KEY,
    Quantity INT NOT NULL CONSTRAINT DF_Items_Quantity DEFAULT (1),
    UnitPrice DECIMAL(12,2) NOT NULL,
    CONSTRAINT CK_Items_Quantity CHECK (Quantity > 0),
    CONSTRAINT CK_Items_UnitPrice CHECK (UnitPrice >= 0)
);
```

Các điểm riêng:

- SQL Server có **DEFAULT constraints** với tên riêng, thường hữu ích cho migration.
- `IDENTITY` dùng sinh ID.
- **Computed columns** có thể tính biểu thức cùng hàng theo cú pháp riêng, gồm biến thể `PERSISTED` tùy điều kiện.
- `FOREIGN KEY` hỗ trợ các hành động tham chiếu phù hợp.
- `CHECK` có quy tắc xử lý UNKNOWN/NULL cần xem cùng `NOT NULL`.

### Trigger SQL Server thường xử lý tập hàng

SQL Server dùng bảng logic `inserted` và `deleted` cho trigger; một câu `UPDATE` có thể ảnh hưởng **nhiều hàng**. Trigger viết như thể chỉ có đúng một hàng là nguồn bug phổ biến.

Nếu chỉ cần `Quantity > 0`, CHECK vừa ngắn vừa tránh lỗi trigger “chọn một hàng từ inserted” rồi bỏ sót các hàng khác.

Một số cơ chế bật/tắt constraint trong SQL Server có thể làm trạng thái **trusted/untrusted** khác nhau; cần kiểm tra khi migration và tối ưu hóa, không coi một constraint tồn tại trên metadata là chắc đã xác thực mọi dữ liệu cũ.

## 35. Oracle Database: DEFAULT, CHECK, FK và identity

Oracle cũng có:

- `DEFAULT` và một số dạng **`DEFAULT ON NULL`** trong các phiên bản phù hợp.
- `NOT NULL`, `CHECK`, `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`.
- Identity/sequence để sinh khóa.
- Trigger cho tình huống cần xem giá trị trước/sau hoặc thực hiện logic đặc thù.

Một ví dụ ý tưởng Oracle:

```sql
CREATE TABLE items (
    item_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    quantity NUMBER DEFAULT 1 NOT NULL,
    unit_price NUMBER(12,2) NOT NULL,
    CONSTRAINT ck_items_quantity CHECK (quantity > 0),
    CONSTRAINT ck_items_price CHECK (unit_price >= 0)
);
```

**Không đồng nhất `DEFAULT ON NULL` của Oracle với `DEFAULT` thông thường của PostgreSQL.** Đây là ví dụ điển hình vì sao behavior “truyền NULL có được thay bằng default không?” phải kiểm tra theo DBMS/DDL cụ thể.

Oracle còn có quy tắc riêng về chuỗi rỗng và NULL, cũng như constraint deferrable; cần xét nếu trạng thái, mã sản phẩm hoặc ID dùng chuỗi ký tự.

## 36. SQLite: constraint có nhưng FK phải được bật/kiểm tra

SQLite hỗ trợ DEFAULT, CHECK, NOT NULL, UNIQUE và khai báo FOREIGN KEY, nhưng có điểm cấu hình quan trọng.

Ví dụ:

```sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    CHECK (status IN ('DRAFT', 'PAID')),
    FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
```

Để FK được thực thi trên SQLite, thông thường cần bật **theo từng connection**:

```sql
PRAGMA foreign_keys = ON;
```

Điều này phải được thực hiện theo cách phù hợp **trước transaction**; thay đổi `PRAGMA foreign_keys` bên trong một transaction đang mở có thể không có tác dụng như kỳ vọng. Ứng dụng cần bảo đảm mọi kết nối dùng cấu hình mong muốn và không vô tình tắt kiểm tra FK.

SQLite có trigger riêng với cú pháp khác PL/pgSQL. Không vì vậy mà dùng trigger kiểm tra quan hệ cha-con nếu FK đã hỗ trợ đúng — trước hết hãy xác nhận FK đã được bật thật.

SQLite có các giới hạn và khả năng riêng về `ALTER TABLE`, generated columns và biểu thức DEFAULT; cần kiểm tra phiên bản khi thiết kế migration.

## 37. So sánh khái niệm giữa các DBMS

| Năng lực | PostgreSQL | MySQL/MariaDB | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| DEFAULT khi bỏ cột | Có | Có | Có | Có | Có |
| CHECK thực thi | Có | Phụ thuộc phiên bản lịch sử; MySQL 8.0.16+ | Có | Có | Có |
| FK | Có | Có khi engine/cấu hình hỗ trợ, thường InnoDB | Có | Có | Cần bật/kiểm tra PRAGMA per connection |
| Identity/auto-increment | `IDENTITY`/sequence | `AUTO_INCREMENT` | `IDENTITY`/sequence | identity/sequence | `INTEGER PRIMARY KEY`/rowid |
| Generated/computed column | Có, tùy phiên bản và kiểu | Có, tùy phiên bản | Computed column | Các cơ chế tính toán/virtual column | Có trên phiên bản hỗ trợ |
| Deferred FK | Có trong các điều kiện thích hợp | Không như PostgreSQL | Không như PostgreSQL | Có theo khai báo phù hợp | Có deferred FK theo quy tắc riêng |
| Trigger OLD/NEW hoặc tương ứng | PL/pgSQL `OLD/NEW` | `OLD/NEW` theo cú pháp hệ | `inserted/deleted` | `:OLD/:NEW` | `OLD/NEW` trong trigger |

Điểm cần nhớ: **mẫu thiết kế “ưu tiên constraint” áp dụng rộng**, nhưng tính năng, thời điểm kiểm tra, cách báo lỗi và khả năng điều chỉnh constraint phụ thuộc **phiên bản/engine**.

## 38. Khi nào vẫn cần application validation?

Constraint là lớp bảo vệ, nhưng không thay thế toàn bộ kiểm tra ở UI/API.

Ví dụ:

- UI có thể cảnh báo “quantity phải lớn hơn 0” trước khi gửi request.
- API kiểm tra email theo quy tắc sản phẩm trước khi INSERT.
- Application quyết định sản phẩm có thể bán cho người dùng này hay không.
- Service xử lý thông báo lỗi SQLSTATE/constraint name thành lỗi nghiệp vụ dễ hiểu.

Lợi ích của kiểm tra ở nhiều lớp:

```text
UI: thông báo sớm và hữu ích
  |
  v
API: xác thực người dùng, quyền, quy tắc nghiệp vụ
  |
  v
DB: NOT NULL / DEFAULT / CHECK / UNIQUE / FOREIGN KEY
  |
  v
Dữ liệu được bảo vệ trước mọi đường ghi
```

Nhưng **không thay ràng buộc database bằng validation phía client**. Client có thể bị bypass hoặc gặp race condition. Constraint bảo vệ tính hợp lệ theo chính sách tại nguồn dữ liệu, còn validation ứng dụng giúp trải nghiệm và ngữ cảnh nghiệp vụ.

## 39. Checklist thiết kế trước khi viết trigger

Trước khi tạo trigger, hãy tự hỏi:

1. **Đây là quy tắc khởi tạo?** Nếu chỉ cần giá trị khi bỏ cột: dùng `DEFAULT`.
2. **Cột bắt buộc?** Dùng `NOT NULL`.
3. **Điều kiện tính được từ hàng hiện tại?** Dùng `CHECK`.
4. **Đảm bảo duy nhất?** Dùng `UNIQUE` hoặc `PRIMARY KEY`.
5. **Tham chiếu sang bảng khác?** Dùng `FOREIGN KEY`, khai báo đúng action.
6. **Giá trị tính từ cột cùng hàng?** Xem generated/computed column.
7. **Khoảng thời gian không chồng lấn?** Xem specialized constraint (như PostgreSQL EXCLUDE) trước khi tự viết trigger.
8. **Cần giá trị OLD và NEW?** Trigger hoặc procedure chuyển trạng thái có thể phù hợp.
9. **Cần cập nhật bảng khác?** Có thể dùng trigger, nhưng phải kiểm soát nhiều hàng, nhiều đường ghi và khóa.
10. **Cần audit sự kiện?** Cân nhắc trigger, CDC, audit feature, retention.
11. **Có side effect bên ngoài?** Xem transactional outbox, idempotency và worker.
12. **Có nhiều transaction đồng thời?** Không tin một `SELECT EXISTS` thủ công là đủ bảo vệ.
13. **Sẽ thêm constraint trên dữ liệu cũ?** Có kế hoạch migration, validation và xử lý hàng lỗi?
14. **Có cần performance benchmark?** Đọc kế hoạch và đo với workload đại diện.
15. **Đang dùng DBMS/phiên bản nào?** Xác nhận thật sự hỗ trợ CHECK/FK/DEFAULT theo kỳ vọng.
16. **Cần thông báo lỗi tốt hơn?** Tận dụng SQLSTATE + tên constraint, không nhất thiết thêm trigger chỉ để viết message.
17. **Trigger có cần thật sự hoạt động khi ghi bulk/migration/replication?** Xem chính sách và cấu hình của hệ.
18. **Một lỗi sau trigger có rollback toàn transaction đúng mong muốn không?** Kiểm tra transaction owner và side effect.

Một dấu hiệu thiết kế tốt là **mỗi cơ chế có một nhiệm vụ rõ**: default để khởi tạo, constraint để bảo vệ dữ liệu, trigger cho sự kiện/transition mà constraint không thể biểu diễn.

## 40. Bài tập thực hành

Dùng schema `sql357` ở các mục 16–20, trừ khi bài yêu cầu thiết kế lý thuyết. Các câu thử lỗi nên chạy riêng, không gom vào transaction đang mở nếu không xử lý rollback.

### Bài 1 — Chọn công cụ phù hợp

Ghép từng yêu cầu với `DEFAULT`, `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY`, generated column, trigger hoặc application/outbox:

a. Tài khoản mới có `active = TRUE` nếu không truyền.

b. Số lượng bắt buộc và lớn hơn 0.

c. Mã SKU không trùng.

d. `order_lines.product_id` phải tồn tại ở `products`.

e. `line_total` bằng phép tính từ quantity, unit_price, discount_pct cùng hàng.

f. Cấm chuyển trạng thái PAID về DRAFT.

g. Gửi email sau khi giao dịch xác nhận được commit.

### Bài 2 — DEFAULT và NULL

Với cột `status TEXT NOT NULL DEFAULT 'DRAFT'`, dự đoán kết quả khi:

a. Bỏ cột trong INSERT.

b. Truyền `DEFAULT`.

c. Truyền `NULL`.

Vì sao trigger tự đổi NULL thành DRAFT có thể làm thay đổi hợp đồng API?

### Bài 3 — CHECK với NULL

Vì sao `quantity INTEGER CHECK (quantity > 0)` vẫn có thể nhận NULL? Viết lại để bắt buộc số lượng là số nguyên dương.

### Bài 4 — CHECK nhiều cột cùng hàng

Viết ràng buộc cho bảng lịch `starts_at, ends_at` để bảo đảm thời điểm kết thúc sau thời điểm bắt đầu. Cần khai báo gì nếu cả hai cột đều bắt buộc?

### Bài 5 — Ràng buộc trạng thái PAID

Viết CHECK sao cho `status = 'PAID'` đòi `confirmed_at IS NOT NULL`. Liệu CHECK đó có đảm bảo đơn đã từng đi qua CONFIRMED không? Vì sao?

### Bài 6 — FOREIGN KEY thay trigger

Thiết kế `orders.customer_id` tham chiếu `customers.customer_id`, không cho xóa khách còn đơn. Vì sao trigger kiểm tra tồn tại bằng SELECT đơn giản có rủi ro đồng thời?

### Bài 7 — ON DELETE CASCADE

Khi xóa một đơn, các dòng đơn có thể được xóa theo bằng cấu trúc FK nào? Vì sao không phải mọi hệ thống hóa đơn nên dùng CASCADE?

### Bài 8 — Cột tiền tính toán

Với `quantity=2`, `unit_price=120000` và `discount_pct=10`, tính `line_total`. Giải thích generated column có ưu điểm nào so với trigger tự cập nhật cột tổng.

### Bài 9 — FK ghép tenant

Một hệ có mã sản phẩm trùng giữa tenant A và B. Viết ý tưởng PK phía products và FK phía order_lines để chặn tham chiếu sản phẩm khác tenant.

### Bài 10 — CHECK không thể đọc bảng khác

Vì sao không nên dùng hàm truy vấn `products.list_price` trong CHECK của `order_lines.unit_price`? Nếu đơn phải giữ giá tại thời điểm mua, mô hình nào hợp lý?

### Bài 11 — UNIQUE và race

Hai transaction cùng `SELECT` thấy SKU chưa tồn tại rồi cùng INSERT. Constraint nào bảo vệ đúng? Vì sao trigger tự `SELECT` trước INSERT không tự bảo đảm duy nhất?

### Bài 12 — Migration

Một bảng sản phẩm cũ có vài giá âm. Bạn muốn thêm CHECK giá không âm. Trình bày quy trình xử lý dữ liệu cũ, thêm constraint và xác thực. Với PostgreSQL, `NOT VALID` có tác dụng gì?

### Bài 13 — Khi nào cần trigger

Cho yêu cầu cấm `PAID -> DRAFT`. Vì sao `CHECK (status IN (...))` không đủ? Trong trigger PostgreSQL, cần dùng giá trị nào để so sánh?

### Bài 14 — updated_at

Một bảng có `updated_at DEFAULT CURRENT_TIMESTAMP`. Người dùng UPDATE nội dung mà không chạm updated_at. Giá trị có tự thay đổi không trong PostgreSQL? Đề xuất hai cách bảo đảm updated_at phản ánh lần sửa.

### Bài 15 — Trigger gửi email

Giải thích điều gì xảy ra nếu trigger gửi email trước khi transaction chứa UPDATE status được rollback. Đề xuất mô hình outbox thay thế.

### Bài 16 — Kiểm thử PostgreSQL

Với lab, viết câu SQL:

a. Chèn sản phẩm không truyền active rồi đọc active.

b. Chèn dòng đơn với quantity = 0 để quan sát CHECK.

c. Chèn dòng đơn với product_id không tồn tại để quan sát FK.

d. Đổi discount_pct của dòng 1 thành 25 và đọc line_total.

### Bài 17 — DBMS differences

Nêu điểm cần xác nhận khi chuyển cùng thiết kế constraint sang MySQL cũ, SQL Server, Oracle và SQLite. Tại sao không thể chỉ tin rằng có từ khóa CHECK/FK trong DDL là được kiểm tra giống nhau?

### Bài 18 — Tổng tiền đơn

Vì sao `orders.total_amount = SUM(order_lines.line_total)` không phải CHECK cùng hàng? Đưa ra hai cách thiết kế tránh trigger và một trường hợp trigger có thể chấp nhận được.

## 41. Gợi ý đáp án

**Bài 1.** a `DEFAULT TRUE`; b `NOT NULL CHECK(quantity > 0)`; c `UNIQUE(sku)`; d `FOREIGN KEY(product_id)`; e generated/computed column; f trigger hoặc procedure kiểm soát transition; g outbox + worker/sự kiện sau commit.

**Bài 2.** Bỏ cột hoặc truyền `DEFAULT` nhận `DRAFT`. Truyền `NULL` bị `NOT NULL` từ chối. Trigger biến NULL thành mặc định sẽ che trường hợp caller cố ý đưa dữ liệu sai, nên phải được quyết định theo hợp đồng API.

**Bài 3.** `NULL > 0` là UNKNOWN và CHECK không coi UNKNOWN là FALSE. Dùng:

```sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
```

**Bài 4.**

```sql
starts_at TIMESTAMP NOT NULL,
ends_at   TIMESTAMP NOT NULL,
CHECK (ends_at > starts_at)
```

Chỉ có CHECK mà không có NOT NULL vẫn để UNKNOWN đi qua nếu thời gian bị NULL.

**Bài 5.**

```sql
CHECK (status <> 'PAID' OR confirmed_at IS NOT NULL)
```

Nó không biết `OLD.status` hoặc lịch sử trạng thái, nên không bảo đảm đã qua CONFIRMED.

**Bài 6.**

```sql
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id)
ON DELETE RESTRICT
```

FK quản lý tham chiếu khi nhiều transaction cùng ghi/xóa; trigger tự SELECT nếu không có cơ chế đồng thời đúng có thể gặp race.

**Bài 7.** `FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE`. Nhưng đơn hóa đơn/chứng từ có thể cần retention; CASCADE là lựa chọn nghiệp vụ, không phải chỉ để tránh lỗi FK.

**Bài 8.** `2 × 120000 × (1 − 10/100) = 216000`. Generated column giảm nguy cơ quên cập nhật tổng khi một trong các cột đầu vào thay đổi.

**Bài 9.**

```sql
-- Parent:
PRIMARY KEY (tenant_id, product_code)

-- Child:
FOREIGN KEY (tenant_id, product_code)
REFERENCES tenant_products(tenant_id, product_code)
```

Kết hợp `NOT NULL` phù hợp ở các cột khóa con.

**Bài 10.** CHECK một hàng không được thiết kế để đối chiếu trạng thái bảng khác, hàm truy vấn có thể khiến ràng buộc không được kiểm tra lại khi giá cha đổi. Lưu `order_lines.unit_price` là **snapshot giá chốt**, có FK tới product và CHECK giá không âm; procedure/ứng dụng định giá khi lập đơn.

**Bài 11.** `UNIQUE(sku)`. Check trước bằng SELECT không khóa đúng có thể cho hai phiên cùng “được phép” rồi ghi trùng; UNIQUE bảo vệ cuối.

**Bài 12.** Thống kê và sửa hàng âm trước, thêm constraint, validate dữ liệu cũ và cập nhật ứng dụng. Trên PostgreSQL, `ADD CONSTRAINT ... CHECK (...) NOT VALID` cho phép chưa quét xác nhận hàng cũ ngay, nhưng vẫn kiểm soát các ghi mới phù hợp; sau đó `VALIDATE CONSTRAINT`.

**Bài 13.** CHECK chỉ biết trạng thái **sau UPDATE** có nằm trong danh sách hợp lệ; không biết trạng thái trước. Trigger dùng `OLD.status` và `NEW.status` để đánh giá transition.

**Bài 14.** `DEFAULT CURRENT_TIMESTAMP` không tự chạy lại khi UPDATE. Có thể đặt `updated_at` trong mọi câu UPDATE qua API/procedure, hoặc dùng trigger BEFORE UPDATE nếu phải bảo vệ nhiều đường ghi.

**Bài 15.** Email đã gửi có thể không thu hồi được dù database rollback. Dùng outbox ghi cùng transaction, worker chỉ xử lý sự kiện đã commit, có retry/idempotency.

**Bài 16.**

```sql
-- a: product mặc định active=true nếu bỏ cột.
INSERT INTO sql357.products
    (product_id, sku, product_name, list_price)
VALUES
    (104, 'PEN-01', 'Bút', 10000);
SELECT product_id, active
FROM sql357.products
WHERE product_id = 104;

-- b: dự kiến lỗi CHECK.
INSERT INTO sql357.order_lines
    (order_id, product_id, quantity, unit_price)
VALUES
    (5001, 101, 0, 1000);

-- c: dự kiến lỗi FK.
INSERT INTO sql357.order_lines
    (order_id, product_id, quantity, unit_price)
VALUES
    (5001, 9999, 1, 1000);

-- d: generated column tự tính lại.
UPDATE sql357.order_lines
SET discount_pct = 25
WHERE order_line_id = 1
RETURNING quantity, unit_price, discount_pct, line_total;
```

Với quantity 2, unit_price 120000, discount 25%, `line_total = 180000`. Các câu b/c gây lỗi nên chạy riêng hoặc rollback đúng cách.

**Bài 17.** MySQL cũ có thể từng parse CHECK nhưng không enforce; với MySQL/MariaDB cần xem version, storage engine và FK settings. SQL Server có DEFAULT constraints/computed columns và trạng thái constraint trust; Oracle có DEFAULT ON NULL và identity; SQLite cần bật `PRAGMA foreign_keys = ON` theo connection. Cú pháp tồn tại không tự bảo đảm cùng semantics/vận hành.

**Bài 18.** Tổng đơn dùng dữ liệu **nhiều hàng** ở order_lines, vượt phạm vi CHECK trên một hàng của orders. Có thể tính động bằng `SUM` trong query/view hoặc dùng materialized view có refresh. Nếu bắt buộc lưu tổng cập nhật tức thì cùng transaction cho mọi đường ghi, có thể xem xét trigger có xử lý INSERT/UPDATE/DELETE, concurrency và bulk operations đầy đủ.

## 42. Dọn môi trường thực hành

Sau khi đã hoàn thành, chỉ xóa các đối tượng **do chính bài học tạo ra**, trong database thử nghiệm:

```sql
-- PostgreSQL, chỉ chạy khi xác nhận schema thuộc bài thực hành.
DROP SCHEMA sql357 CASCADE;
```

Lệnh trên xóa cả bảng, constraint, index và trigger/function trong schema; `CASCADE` còn có thể tác động tới đối tượng phụ thuộc bên ngoài schema theo quy tắc PostgreSQL. **Không chạy trong database sản xuất hoặc schema dùng chung** nếu chưa kiểm tra dependencies.

## 43. Kết luận

Với một quy tắc dữ liệu, hãy hỏi **“DBMS có thể khai báo trực tiếp điều này trong schema không?”** trước khi viết trigger.

- Dùng **`DEFAULT`** để cấp giá trị khi cột bị bỏ qua lúc tạo hàng; nó **không thay `NULL` tường minh** trong nhiều DBMS và không tự cập nhật lại khi UPDATE.
- Dùng **`NOT NULL` + `CHECK`** cho điều kiện hợp lệ trong một hàng, hiểu rõ logic UNKNOWN khi có NULL.
- Dùng **`FOREIGN KEY`** cho quan hệ tồn tại và chính sách cập nhật/xóa cha-con, thay vì trigger tự `SELECT` kiểm tra tồn tại dễ gặp race.
- Dùng **`PRIMARY KEY`/`UNIQUE`** để bảo vệ tính duy nhất, **generated/computed column** khi giá trị tính từ cột cùng hàng, và các constraint chuyên biệt nếu DBMS hỗ trợ.
- Chỉ dùng **trigger hoặc procedure** khi cần kiểm tra **OLD/NEW**, ghi lịch sử sự kiện, đồng bộ nhiều hàng/bảng hoặc áp dụng quy tắc mà ràng buộc khai báo không biểu diễn được — đồng thời phải thiết kế transaction, concurrency và khả năng quan sát.

**Trigger tốt không phải trigger làm thật nhiều việc, mà là trigger chỉ đảm nhiệm phần logic mà DEFAULT, CHECK, FOREIGN KEY và các ràng buộc tích hợp không thể làm đúng hoặc làm đủ.**
