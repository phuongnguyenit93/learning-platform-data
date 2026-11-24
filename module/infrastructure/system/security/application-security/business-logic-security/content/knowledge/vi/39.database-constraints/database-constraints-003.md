# Foreign key ownership: ràng buộc quan hệ đúng tenant và chủ sở hữu

## 1. Vì sao khóa ngoại vẫn có thể cho phép gắn nhầm dữ liệu?

Một hệ thống đặt hàng cho phép người dùng chọn địa chỉ giao hàng bằng `shipping_address_id`. Backend kiểm tra địa chỉ tồn tại, sau đó lưu đơn hàng. Cơ sở dữ liệu cũng có khóa ngoại từ đơn hàng đến địa chỉ.

Kẻ tấn công thay ID địa chỉ của mình bằng ID địa chỉ của người khác. Nếu khóa ngoại chỉ tham chiếu `addresses(id)`, cơ sở dữ liệu vẫn chấp nhận: địa chỉ đó thực sự tồn tại. Tuy nhiên, đơn hàng đã sử dụng dữ liệu không thuộc khách hàng đang đặt hàng.

Đây là lỗi logic nghiệp vụ: **tính tồn tại của đối tượng không chứng minh quan hệ sở hữu hợp lệ**. ID khó đoán, UUID hay kiểm tra kiểu dữ liệu đầu vào đều không giải quyết được điều kiện này.

Trong bài này, *foreign key ownership* là cách dùng khóa ngoại, thường là khóa ngoại ghép, để buộc các bản ghi liên quan phải chia sẻ đúng phạm vi tenant hoặc đúng đối tượng sở hữu. Đây là lớp bảo vệ tính toàn vẹn cho module bảo mật logic nghiệp vụ, bổ sung cho kiểm tra quyền theo đối tượng tại backend.

Sau bài học, bạn cần có khả năng:

- Chuyển quy tắc “bản ghi con phải thuộc đúng chủ sở hữu” thành invariant có thể kiểm tra trong cơ sở dữ liệu.
- Thiết kế khóa ngoại ghép để ngăn tham chiếu chéo tenant và chéo khách hàng.
- Phân biệt quan hệ sở hữu trong dữ liệu với quyền của người đang gửi yêu cầu.
- Xác định tác động của transaction, thay đổi chủ sở hữu, giá trị `NULL` và thao tác xóa đến invariant.
- Xây dựng các tình huống kiểm thử giả mạo ID, chuyển quyền và cập nhật đồng thời.

## 2. Tách rõ ba câu hỏi bảo mật

Xét một đơn hàng có `tenant_id`, `customer_id` và `shipping_address_id`. Cần trả lời độc lập ba câu hỏi:

| Câu hỏi | Ví dụ điều kiện | Lớp thực thi chính |
|---|---|---|
| Đối tượng có tồn tại không? | Địa chỉ được tham chiếu tồn tại | Khóa ngoại |
| Các đối tượng có quan hệ hợp lệ không? | Địa chỉ thuộc đúng khách hàng trong cùng tenant với đơn hàng | Khóa ngoại ghép và các ràng buộc liên quan |
| Người gọi có được thực hiện hành động không? | Người dùng hiện tại được tạo đơn cho khách hàng này | Xác thực, kiểm tra quyền theo đối tượng, quy tắc nghiệp vụ tại backend |

Khóa ngoại thường không biết danh tính người gọi HTTP. Một câu lệnh SQL dùng tài khoản dịch vụ có thể tạo quan hệ hợp lệ về dữ liệu nhưng vẫn trái quyền của người dùng cuối.

Vì vậy, không được suy luận:

> “Đã có khóa ngoại bảo vệ ownership nên không cần kiểm tra quyền.”

Cách hiểu đúng là:

> Backend xác minh người gọi được thực hiện hành động; cơ sở dữ liệu bảo đảm các bản ghi được lưu không phá vỡ quan hệ sở hữu đã mô hình hóa.

Ngay cả khi áp dụng row-level security, vẫn cần thiết kế và kiểm thử riêng chính sách quyền, tài khoản kết nối, quyền bypass và constraint. Khóa ngoại ghép tự nó không tạo ra chính sách kiểm soát truy cập.

## 3. Viết business invariant trước khi viết DDL

Giả sử hệ thống có mô hình sau:

- Một tenant là một không gian dữ liệu của tổ chức.
- Một thành viên được nhận diện bằng cặp `(tenant_id, user_id)`.
- Mỗi khách hàng thuộc một tenant và có một `owner_user_id` là thành viên của tenant đó.
- Mỗi địa chỉ thuộc đúng một khách hàng trong một tenant.
- Mỗi đơn hàng thuộc một khách hàng và phải dùng địa chỉ của chính khách hàng ấy.

Đây là mô hình đơn giản cho ví dụ. Một hệ thống doanh nghiệp có thể dùng nhóm, vai trò hoặc bảng cấp quyền thay cho một `owner_user_id`; khi đó phần kiểm tra quyền cần thay đổi tương ứng.

Với đơn hàng `o`, khách hàng `c` và địa chỉ `a`, các invariant cần lưu giữ là:

```text
I1. Tồn tại c sao cho:
    c.tenant_id = o.tenant_id
    c.id        = o.customer_id

I2. Tồn tại a sao cho:
    a.tenant_id   = o.tenant_id
    a.customer_id = o.customer_id
    a.id          = o.shipping_address_id
```

Trong ví dụ, chính sách tạo đơn còn yêu cầu:

```text
P1. actor có quyền hoạt động trong tenant đã chọn.
P2. c.owner_user_id = actor.user_id.
```

`I1` và `I2` là quan hệ giữa dữ liệu. `P1` và `P2` là điều kiện quyền của hành động. Khóa ngoại có thể bảo vệ hai invariant đầu, nhưng không tự chứng minh hai điều kiện sau.

### Vì sao hai khóa ngoại độc lập chưa đủ?

Thiết kế sau chỉ bảo đảm khách hàng và địa chỉ tồn tại:

```sql
-- Thiết kế minh họa còn thiếu ràng buộc ownership.
FOREIGN KEY (customer_id) REFERENCES customers(id),
FOREIGN KEY (shipping_address_id) REFERENCES customer_addresses(id)
```

Ngay cả khi bổ sung điều kiện cùng tenant, việc kiểm tra độc lập `(tenant_id, customer_id)` và `(tenant_id, shipping_address_id)` vẫn chỉ chứng minh hai đối tượng cùng tenant. Địa chỉ có thể thuộc một khách hàng khác trong cùng tổ chức.

Muốn bảo vệ `I2`, phải ràng buộc **cả tenant, khách hàng và địa chỉ trong cùng một quan hệ tham chiếu**.

## 4. Thiết kế khóa ngoại ghép

DDL dưới đây dùng cú pháp PostgreSQL. Các ID kiểu `uuid` được ứng dụng hoặc hệ thống cấp ID tạo ra; ví dụ không yêu cầu extension sinh UUID. Khi dùng hệ quản trị khác, cần đối chiếu cú pháp và khả năng hỗ trợ constraint của hệ đó.

```sql
CREATE TABLE tenants (
    id uuid PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE tenant_users (
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,

    PRIMARY KEY (tenant_id, user_id),

    CONSTRAINT fk_tenant_users_tenant
        FOREIGN KEY (tenant_id)
        REFERENCES tenants (id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);

CREATE TABLE customers (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    owner_user_id uuid NOT NULL,
    name text NOT NULL,

    PRIMARY KEY (tenant_id, id),

    CONSTRAINT fk_customers_owner
        FOREIGN KEY (tenant_id, owner_user_id)
        REFERENCES tenant_users (tenant_id, user_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);

CREATE TABLE customer_addresses (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    address_text text NOT NULL,

    PRIMARY KEY (tenant_id, id),

    CONSTRAINT uq_addresses_customer_identity
        UNIQUE (tenant_id, customer_id, id),

    CONSTRAINT fk_addresses_customer
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers (tenant_id, id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);

CREATE TABLE orders (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    shipping_address_id uuid NOT NULL,

    PRIMARY KEY (tenant_id, id),

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers (tenant_id, id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CONSTRAINT fk_orders_shipping_address
        FOREIGN KEY (tenant_id, customer_id, shipping_address_id)
        REFERENCES customer_addresses (tenant_id, customer_id, id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);

CREATE INDEX ix_customers_owner
    ON customers (tenant_id, owner_user_id);

CREATE INDEX ix_orders_shipping_address
    ON orders (tenant_id, customer_id, shipping_address_id);
```

### 4.1. Mỗi thành phần đang bảo vệ điều gì?

`PRIMARY KEY (tenant_id, id)` xác định bản ghi trong một tenant. Truy vấn cần dùng cả hai thành phần; riêng `id` không được thiết kế là duy nhất toàn hệ thống trong ví dụ này.

`fk_customers_owner` bảo đảm chủ sở hữu khách hàng là một thành viên có bản ghi trong cùng tenant. Constraint này không kiểm tra thành viên còn hoạt động hay có quyền tạo đơn; đó là chính sách cần kiểm tra riêng.

`fk_addresses_customer` bảo đảm địa chỉ thuộc một khách hàng hợp lệ trong tenant tương ứng.

`fk_orders_customer` thể hiện trực tiếp invariant khách hàng của đơn hàng. Trong schema hiện tại, khi địa chỉ bắt buộc và chuỗi constraint đầy đủ, quan hệ này còn có thể suy ra qua địa chỉ. Giữ khóa ngoại riêng giúp quy tắc vẫn được bảo vệ nếu sau này địa chỉ trở thành tùy chọn.

`fk_orders_shipping_address` buộc cả ba giá trị trên đơn hàng phải khớp với **cùng một hàng địa chỉ**. Đây là constraint chặn việc gắn địa chỉ của khách hàng khác.

`UNIQUE (tenant_id, customer_id, id)` cung cấp đích tham chiếu hợp lệ cho khóa ngoại ba cột. Dù khóa chính `(tenant_id, id)` đã làm cho hàng địa chỉ là duy nhất, trong thiết kế PostgreSQL này vẫn khai báo rõ tập cột được tham chiếu bằng constraint `UNIQUE`. Không nên trông chờ hệ quản trị tự suy diễn mọi tập cột mở rộng từ một khóa nhỏ hơn.

Các cột ownership bắt buộc đều có `NOT NULL`. Nếu thiếu điều này, ngữ nghĩa `NULL` của khóa ngoại ghép có thể làm điều kiện tham chiếu không được kiểm tra như mong muốn.

### 4.2. Nếu hệ thống đang dùng ID duy nhất toàn cục

Không bắt buộc phải đổi mọi khóa chính sang dạng ghép. Có thể giữ `PRIMARY KEY (id)`, đồng thời khai báo thêm các khóa duy nhất như `UNIQUE (tenant_id, id)` hoặc `UNIQUE (tenant_id, customer_id, id)` để làm đích tham chiếu.

Điều quan trọng là khóa ngoại phải mang đủ ngữ cảnh sở hữu. UUID duy nhất toàn cục giúp nhận diện bản ghi; UUID không tự chứng minh bản ghi thuộc đúng tenant hoặc đúng khách hàng.

### 4.3. Chỉ mục và thứ tự cột

PostgreSQL tạo chỉ mục phục vụ `PRIMARY KEY` và `UNIQUE`, nhưng không tự tạo chỉ mục trên mọi phía tham chiếu của khóa ngoại. Chỉ mục ở bảng con giúp việc tìm bản ghi liên quan khi cập nhật hoặc xóa bản ghi cha không phải quét toàn bảng.

Trong ví dụ:

- `ix_orders_shipping_address` có tiền tố `(tenant_id, customer_id)`, nên cũng hỗ trợ tìm đơn theo khách hàng.
- Chỉ mục của `uq_addresses_customer_identity` có tiền tố `(tenant_id, customer_id)`, hỗ trợ tìm địa chỉ theo khách hàng.
- `ix_customers_owner` hỗ trợ tìm các khách hàng đang thuộc một thành viên.

Chọn chỉ mục theo truy vấn và tải thực tế. Thiếu chỉ mục phía bảng con không làm khóa ngoại mất hiệu lực, nhưng có thể làm thao tác ghi, xóa và giữ khóa kéo dài, ảnh hưởng khả năng phục vụ của hệ thống.

## 5. Quan sát điều gì bị chặn và điều gì vẫn cần backend

Giả sử tồn tại dữ liệu sau; các ký hiệu trong bảng là nhãn rút gọn cho UUID:

| Tenant | Khách hàng | Chủ sở hữu | Địa chỉ |
|---|---|---|---|
| T1 | C1 | U1 | A1 |
| T1 | C2 | U2 | A2 |
| T2 | C3 | U3 | A3 |

Khi tạo đơn, các tổ hợp có kết quả:

| Dữ liệu của đơn | Kết quả ở tầng constraint | Giải thích |
|---|---|---|
| T1, C1, A1 | Hợp lệ | Địa chỉ thuộc đúng khách hàng trong T1 |
| T1, C1, A2 | Bị từ chối | A2 thuộc C2, không thuộc C1 |
| T1, C1, A3 | Bị từ chối | Không có địa chỉ A3 thuộc C1 trong T1 |
| T1, C3, A3 | Bị từ chối | Không có khách hàng C3 trong T1 theo dữ liệu mẫu |
| T1, C2, A2, nhưng người gọi là U1 | Có thể hợp lệ về constraint | Backend phải từ chối vì U1 không phải chủ C2 theo chính sách ví dụ |

Hàng cuối là điểm dễ bỏ sót: kẻ tấn công có thể thay đồng thời nhiều ID để tạo một bộ quan hệ hoàn toàn hợp lệ nhưng thuộc người khác.

Khóa ngoại cũng không bảo vệ truy vấn đọc. Lệnh lấy địa chỉ chỉ bằng `id`, hoặc trả mọi đơn trong tenant mà không lọc quyền đối tượng, vẫn có thể làm lộ dữ liệu dù mọi hàng lưu trữ đều hợp lệ.

## 6. Ghép constraint với luồng xử lý có kiểm tra quyền

### 6.1. Phân biệt dữ liệu yêu cầu và ngữ cảnh đã xác minh

Payload tạo đơn có thể chứa `customer_id` và `shipping_address_id` để lựa chọn đối tượng. Những giá trị này luôn là đầu vào cần kiểm tra quyền.

`actor.user_id` phải đến từ quá trình xác thực. Tenant đang thao tác phải được backend xác minh người dùng có quyền truy cập. Nếu client truyền tenant qua URL hoặc header, giá trị đó chỉ là lựa chọn tenant cho đến khi được xác minh.

Không bind tự động toàn bộ JSON vào entity rồi cho phép client ghi `tenant_id`, `owner_user_id`, `customer_id` và các trường kiểm soát khác mà không có quy tắc rõ ràng cho từng trường. Khóa ngoại có thể chặn bộ ID không khớp; nó vẫn chấp nhận một bộ ID khớp nhưng trái quyền người gọi.

### 6.2. Tạo đơn trong transaction

Luồng dưới đây dùng named parameter để minh họa. Với JDBC, cần dùng `PreparedStatement` và bind giá trị; không nối chuỗi SQL từ dữ liệu client.

```sql
BEGIN;

SELECT id
FROM customers
WHERE tenant_id = :verified_tenant_id
  AND id = :requested_customer_id
  AND owner_user_id = :authenticated_user_id
FOR UPDATE;

-- Backend bắt buộc kiểm tra có đúng khách hàng được phép hay không.
-- Nếu không có hàng: ROLLBACK và dừng; không chạy INSERT phía dưới.

INSERT INTO orders (
    tenant_id,
    id,
    customer_id,
    shipping_address_id
) VALUES (
    :verified_tenant_id,
    :server_generated_order_id,
    :requested_customer_id,
    :requested_address_id
);

COMMIT;
```

Phần điều khiển dừng sau `SELECT` thuộc trách nhiệm của ứng dụng; một file SQL chạy tuần tự sẽ không tự dừng chỉ vì `SELECT` trả về không hàng nào.

Luồng này có ba trách nhiệm khác nhau:

1. Lọc khách hàng theo tenant và người dùng để kiểm tra quyền tạo đơn.
2. Khóa hàng khách hàng trong transaction để việc đổi `owner_user_id` trên hàng đó phải chờ.
3. Dùng khóa ngoại để bảo đảm địa chỉ thuộc khách hàng khi ghi đơn.

`FOR UPDATE` chỉ giải quyết phần cạnh tranh liên quan đến hàng được khóa. Nếu quyền còn phụ thuộc vào trạng thái thành viên, bảng cấp quyền hoặc nhóm, cần định nghĩa cách đồng bộ với việc thay đổi những dữ liệu đó. Khóa hàng khách hàng không tự khóa mọi nguồn quyền khác.

Ví dụ cũng chưa xử lý gửi yêu cầu trùng. UUID mới cho mỗi lần retry có thể tạo nhiều đơn hợp lệ. Nếu nghiệp vụ yêu cầu một hành động chỉ tạo một đơn, cần cơ chế idempotency và ràng buộc duy nhất phù hợp ngoài các khóa ngoại này.

### 6.3. Cập nhật địa chỉ của đơn cũng cần kiểm tra quyền

Một endpoint cập nhật không được chỉ chạy `UPDATE orders SET ... WHERE id = ...`. Cần kiểm tra người gọi được sửa chính đơn hàng đó, đồng thời áp dụng điều kiện trạng thái nếu đơn đã qua bước cho phép sửa.

Ví dụ câu lệnh có điều kiện quyền theo mô hình chủ sở hữu hiện tại:

```sql
UPDATE orders AS o
SET shipping_address_id = :requested_address_id
FROM customers AS c
WHERE o.tenant_id = :verified_tenant_id
  AND o.id = :requested_order_id
  AND c.tenant_id = o.tenant_id
  AND c.id = o.customer_id
  AND c.owner_user_id = :authenticated_user_id;
```

Backend phải kiểm tra số hàng bị cập nhật. Không có hàng phù hợp không được trả về thông báo đã sửa thành công. `fk_orders_shipping_address` tiếp tục kiểm tra địa chỉ mới thuộc khách hàng của đơn.

Câu lệnh này minh họa việc gắn điều kiện quyền vào thao tác ghi; nó chưa biểu diễn state machine vì schema mẫu không có cột trạng thái. Trong hệ thống thực tế, điều kiện như “chỉ sửa khi đơn còn nháp” cũng phải được kiểm tra nhất quán trong transaction hoặc thao tác ghi có điều kiện.

Nếu chính sách yêu cầu đồng bộ nghiêm ngặt với chuyển chủ sở hữu, cần dùng giao thức khóa hoặc cơ chế kiểm soát đồng thời đã thống nhất, như luồng tạo đơn ở trên. Chỉ thêm điều kiện owner vào một câu lệnh không tự giải quyết mọi cạnh tranh với việc thay đổi quyền ở transaction khác.

## 7. Transaction và thay đổi ownership đồng thời

### 7.1. Lỗi kiểm tra trước rồi ghi sau

Xét một implementation chỉ kiểm tra địa chỉ thuộc khách hàng bằng truy vấn, không có khóa ngoại ghép:

```text
Transaction A: đọc A1 và thấy A1 thuộc C1.
Transaction B: chuyển A1 sang C2 rồi commit.
Transaction A: tạo đơn cho C1 với A1 rồi commit.
```

Kết quả có thể là đơn của C1 tham chiếu địa chỉ hiện thuộc C2. Truy vấn kiểm tra đã đúng ở thời điểm đọc nhưng không còn đủ để bảo vệ thời điểm ghi.

Khi khóa ngoại ghép đã có hiệu lực, cơ sở dữ liệu kiểm tra quan hệ tham chiếu và phối hợp với thao tác đồng thời. Với schema dùng `RESTRICT`, không thể commit thành công cả hai thay đổi nếu trạng thái kết quả vi phạm constraint. Tùy thứ tự và các khóa đang giữ, một thao tác có thể chờ hoặc thất bại.

Không nên mô tả hành vi là “request sai luôn thất bại ngay lập tức”: thời điểm kiểm tra, khóa và thứ tự commit ảnh hưởng kết quả quan sát được. Invariant cần đạt là không lưu được trạng thái quan hệ không hợp lệ.

### 7.2. FK không giữ nguyên mọi dữ kiện quyền

Đổi `customers.owner_user_id` không thay đổi các cột được `orders` tham chiếu là `(tenant_id, id)`. Vì thế, khóa ngoại từ đơn đến khách hàng không tự ngăn việc đổi chủ sở hữu trong lúc một request khác đang kiểm tra quyền.

Cần quyết định rõ:

- Quyền được xác định tại thời điểm nào của hành động?
- Sau khi chuyển chủ sở hữu, chủ cũ có còn được hoàn tất yêu cầu đã bắt đầu không?
- Đơn lịch sử thuộc khách hàng hiện tại hay cần lưu thông tin người tạo, người duyệt và chủ sở hữu tại thời điểm phát sinh?

Nếu quyền theo chủ hiện tại, transaction kiểm tra quyền và transaction chuyển chủ cần phối hợp trên các hàng phù hợp. Nếu cần bằng chứng lịch sử, lưu các trường như `created_by` hoặc bản ghi audit theo chính sách riêng; không suy ra người tạo đơn từ chủ sở hữu hiện tại của khách hàng.

### 7.3. Tại sao không mặc định dùng cascade?

`ON UPDATE CASCADE` có thể làm dữ liệu con tự thay đổi theo khóa được tham chiếu. Với quan hệ ownership, điều này có thể biến việc đổi chủ hoặc chuyển tenant thành một loạt thay đổi dữ liệu ngoài ý muốn nghiệp vụ.

`ON DELETE CASCADE` có thể xóa đơn hàng khi xóa khách hàng hoặc địa chỉ nếu thiết kế chuỗi cascade như vậy. Dữ liệu đặt hàng, thanh toán và phê duyệt thường cần quy trình lưu giữ riêng.

Schema mẫu chọn `RESTRICT` để yêu cầu xử lý tham chiếu trước khi sửa khóa hoặc xóa hàng cha. Đây là lựa chọn cho ví dụ, không phải quy tắc mọi quan hệ đều phải dùng `RESTRICT`. Một bảng con thuần kỹ thuật, không có ý nghĩa lịch sử độc lập, có thể phù hợp với cascade sau khi đánh giá nghiệp vụ.

## 8. Các giới hạn cần thiết kế rõ

### 8.1. Địa chỉ tùy chọn và `NULL`

Trong PostgreSQL, khóa ngoại ghép mặc định dùng `MATCH SIMPLE`: nếu ít nhất một cột tham chiếu là `NULL`, hàng đó không bị yêu cầu khớp với hàng cha theo khóa ngoại ấy.

Trong schema ban đầu, các cột đều `NOT NULL`, nên không có lối bỏ qua này. Nếu nghiệp vụ cho phép đơn nháp chưa chọn địa chỉ, có thể cho riêng `shipping_address_id` nhận `NULL`, còn `tenant_id` và `customer_id` vẫn bắt buộc.

Khi đó:

- Khóa ngoại khách hàng riêng vẫn buộc đơn thuộc một khách hàng hợp lệ.
- Nếu địa chỉ khác `NULL`, khóa ngoại ba cột vẫn buộc địa chỉ thuộc đúng khách hàng.
- Quy tắc “đơn đã xác nhận phải có địa chỉ” cần một ràng buộc bổ sung gắn với trạng thái hoặc loại giao nhận.

Không áp dụng máy móc `MATCH FULL` cho khóa `(tenant_id, customer_id, shipping_address_id)` trong thiết kế này. `MATCH FULL` yêu cầu các cột cùng `NULL` hoặc cùng không `NULL`; một đơn có tenant và khách hàng nhưng chưa có địa chỉ sẽ bị từ chối.

### 8.2. Soft delete, khóa tài khoản và hết hạn quyền

Một địa chỉ có `deleted_at` vẫn tồn tại về mặt vật lý, nên khóa ngoại vẫn có thể tham chiếu nó. Tương tự, sự tồn tại của hàng `tenant_users` không chứng minh thành viên còn hoạt động.

Backend cần kiểm tra điều kiện “được phép dùng ở thời điểm tạo hoặc sửa”. Nếu yêu cầu chỉ lưu tham chiếu đến tài nguyên đang hoạt động là một invariant bắt buộc, cần mô hình hóa thêm hoặc có cơ chế transaction phù hợp; khóa ngoại tồn tại đơn thuần không biểu diễn điều kiện lọc tùy ý theo `deleted_at`.

Cũng cần phân biệt: đơn lịch sử được phép tiếp tục tham chiếu địa chỉ đã ngừng sử dụng có thể là hành vi đúng, trong khi tạo đơn mới với địa chỉ đó là sai.

### 8.3. Dữ liệu lịch sử và địa chỉ giao hàng

Khóa ngoại bảo vệ quan hệ, không giữ nguyên nội dung địa chỉ. Nếu sửa `address_text`, đơn cũ có thể hiển thị thông tin mới khi truy vấn join.

Nếu cần giữ địa chỉ tại thời điểm đặt hàng, lưu snapshot hoặc tham chiếu đến phiên bản địa chỉ bất biến. Quyết định này độc lập với việc địa chỉ có thuộc đúng khách hàng hay không.

### 8.4. Chuyển tenant hoặc chuyển đối tượng sở hữu

Việc cập nhật đồng thời `tenant_id`, `customer_id` và `shipping_address_id` có thể tạo ra một bộ tham chiếu hợp lệ ở đích mới. Khóa ngoại sẽ chấp nhận nếu tất cả điều kiện tham chiếu đều được đáp ứng.

Vì vậy, khóa ngoại không ngăn một người có quyền ghi SQL rộng chuyển dữ liệu sang tenant khác. Các cột định danh phạm vi thường cần được coi là bất biến trong API thông thường; việc di chuyển phải qua luồng chuyên biệt có kiểm tra quyền và audit.

Tương tự, khóa ngoại không cấm một đơn đang nháp bị biến thành đơn đã duyệt nếu giá trị trạng thái vẫn hợp lệ. Invariant chuyển trạng thái và quyền phê duyệt phải được bảo vệ riêng.

### 8.5. Quan hệ sở hữu đa hình và dữ liệu ngoài database

Thiết kế `owner_type` cộng `owner_id`, trong đó ID có thể trỏ đến nhiều bảng khác nhau, không được bảo vệ đầy đủ bằng một khóa ngoại thông thường. Có thể cân nhắc một bảng đối tượng sở hữu chung, hoặc các bảng quan hệ tách riêng cho từng loại.

Nếu đối tượng được sở hữu nằm ở dịch vụ hay database khác, khóa ngoại cục bộ không thể tự kiểm tra trạng thái hiện tại của nó. Cần xác định ranh giới nhất quán, dữ liệu bản sao và quy trình xử lý khi quyền hoặc quan hệ bên ngoài thay đổi. Không mô tả một lần gọi API kiểm tra trước khi ghi như tương đương với constraint nội bộ.

## 9. Xử lý lỗi và đưa constraint vào hệ thống đang chạy

### 9.1. Trả lỗi đủ dùng, không làm lộ dữ liệu

Khi một bộ ID không khớp ownership, PostgreSQL có thể trả lỗi vi phạm khóa ngoại với SQLSTATE `23503`. Ứng dụng cần phân loại lỗi tại tầng truy cập dữ liệu, rollback transaction lỗi và chuyển thành phản hồi nghiệp vụ phù hợp.

Không trả nguyên thông báo SQL, tên bảng, tên constraint hoặc chi tiết cho biết địa chỉ của tenant khác có tồn tại. Có thể dùng thông báo như:

```json
{
  "code": "INVALID_ORDER_REFERENCE",
  "message": "Không thể sử dụng khách hàng hoặc địa chỉ đã chọn."
}
```

Mã HTTP và việc dùng chung phản hồi cho đối tượng không tồn tại hoặc không được phép cần theo quy ước của hệ thống. Kiểm tra quyền trước khi ghi vẫn cần thiết; không dùng lỗi constraint làm cơ chế xác thực người gọi.

Trong PostgreSQL, sau lỗi câu lệnh trong transaction, phải rollback transaction hoặc rollback về savepoint phù hợp trước khi tiếp tục. Không nuốt exception rồi tiếp tục lưu các thay đổi còn lại như thể đơn hàng đã được tạo.

Log nội bộ nên có mã lỗi, thao tác, correlation ID và định danh cần thiết theo chính sách dữ liệu. Hạn chế ghi thông tin cá nhân như nội dung địa chỉ; theo dõi cả lỗi vô tình lẫn chuỗi thử ID đáng ngờ.

### 9.2. Kiểm tra dữ liệu cũ trước khi áp dụng

Thêm constraint không tự sửa các hàng đã sai. Có thể tìm đơn hàng không khớp địa chỉ bằng truy vấn đọc sau:

```sql
SELECT
    o.tenant_id,
    o.id AS order_id,
    o.customer_id,
    o.shipping_address_id
FROM orders AS o
LEFT JOIN customer_addresses AS a
    ON a.tenant_id = o.tenant_id
   AND a.customer_id = o.customer_id
   AND a.id = o.shipping_address_id
WHERE o.shipping_address_id IS NOT NULL
  AND a.id IS NULL;
```

Đồng thời kiểm tra các quan hệ khác và cột bắt buộc. Truy vấn trên chỉ kiểm tra quan hệ địa chỉ; nó không thay thế việc tìm tenant, khách hàng hoặc owner không hợp lệ.

Với dữ liệu lỗi, cần xác định nguồn dữ liệu đúng, cách sửa và ảnh hưởng lịch sử. Không tự gán mọi hàng sai sang khách hàng đầu tiên tìm thấy để migration chạy qua.

PostgreSQL hỗ trợ một lộ trình thêm khóa ngoại với `NOT VALID`, sau đó chạy `VALIDATE CONSTRAINT`. Cách này tách việc kiểm tra dữ liệu lịch sử khỏi lúc thêm constraint: các thao tác ghi liên quan vẫn chịu ràng buộc, nhưng dữ liệu cũ chưa được xác nhận đầy đủ cho đến khi validate thành công.

Không xem `NOT VALID` là trạng thái bảo vệ hoàn tất. Việc chuẩn bị khóa duy nhất ở bảng cha, tạo chỉ mục, khóa DDL và thời gian validate vẫn cần kế hoạch triển khai phù hợp. Schema mẫu ở bài này là schema tạo mới với constraint được kiểm tra thông thường.

## 10. Kiểm thử theo tình huống tấn công logic

Cần kiểm thử cả API lẫn database. Test API chứng minh việc kiểm tra quyền của actor; test ghi trực tiếp bằng tài khoản ứng dụng có quyền DML chứng minh quan hệ sai không thể được lưu qua một đường ghi khác.

### 10.1. Ma trận kiểm thử tối thiểu

| Tình huống | Kỳ vọng |
|---|---|
| U1 tạo đơn C1 với A1 trong T1 | Thành công nếu các điều kiện nghiệp vụ khác đều thỏa |
| U1 thay riêng A1 bằng A2 của C2 trong T1 | API từ chối; ghi trực tiếp cũng bị constraint chặn |
| U1 dùng địa chỉ A3 của T2 | Không tạo được quan hệ chéo tenant |
| U1 thay cả C1/A1 bằng C2/A2 | API từ chối do thiếu quyền, dù bộ tham chiếu hợp lệ |
| Client giả `owner_user_id` hoặc tenant chưa được xác minh | Không được dùng làm căn cứ cấp quyền |
| Cùng giá trị ID tồn tại trong hai tenant | Truy vấn và ghi vẫn phân biệt bằng tenant |
| Sửa địa chỉ của đơn sang địa chỉ của khách hàng khác | Constraint tiếp tục chặn đường cập nhật |
| Đổi khách hàng của đơn nhưng giữ địa chỉ cũ | Bị chặn nếu không còn khớp bộ tham chiếu |
| Gán `NULL` vào cột bắt buộc trong schema mẫu | Bị `NOT NULL` chặn |
| Xóa địa chỉ đã được đơn tham chiếu | Bị `RESTRICT` chặn trong schema mẫu |
| Tạo đơn với địa chỉ đã soft delete | API từ chối theo chính sách; không trông chờ FK tự chặn |
| Gửi lại cùng hành động tạo đơn | Hành vi tuân theo thiết kế idempotency riêng |

### 10.2. Kiểm thử đồng thời

Sử dụng hai kết nối database và các điểm đồng bộ rõ ràng, thay vì chỉ đặt thời gian ngủ rồi mong tái hiện được cuộc đua.

**Kịch bản A: tạo đơn và chuyển địa chỉ sang khách hàng khác.** Cho hai transaction thao tác trên cùng địa chỉ, thử cả hai thứ tự commit. Với constraint đã có hiệu lực, không được có kết quả commit cuối cùng chứa đơn tham chiếu địa chỉ sai khách hàng. Chấp nhận kết quả một transaction chờ hoặc thất bại theo lịch thực thi.

**Kịch bản B: tạo đơn và chuyển chủ khách hàng.** Kiểm tra chính sách thời điểm quyền đã chọn. Nếu luồng tạo đơn đã khóa hàng khách hàng để xác minh owner, thao tác đổi owner trên hàng đó phải phối hợp với khóa; sau khi chuyển chủ hoàn tất, request mới của chủ cũ phải bị từ chối.

**Kịch bản C: transaction có lỗi khóa ngoại.** Xác minh không còn đơn, chi tiết hay audit “thành công” bị lưu dở sau rollback. Nếu có gửi sự kiện, cần kiểm tra cơ chế phối hợp transaction, chẳng hạn outbox, để không phát sự kiện thành công trước khi commit.

### 10.3. Tiêu chí quan sát

Không chỉ kiểm tra mã HTTP. Sau mỗi tình huống, cần quan sát trạng thái dữ liệu:

- Không xuất hiện đơn gắn sai tenant, khách hàng hoặc địa chỉ.
- Yêu cầu bị từ chối không tạo tác dụng phụ nghiệp vụ.
- Lỗi không tiết lộ sự tồn tại của tài nguyên ngoài quyền.
- Các đường batch, import, tác vụ nền và endpoint quản trị vẫn chịu constraint nếu dùng quyền DML thông thường.

Tài khoản đặc quyền có thể sửa schema hoặc vô hiệu hóa cơ chế kiểm tra theo khả năng hệ quản trị. Vì vậy, việc hạn chế quyền database của ứng dụng và quản lý migration vẫn là một phần của mô hình bảo vệ.

## 11. Áp dụng sang các nghiệp vụ khác

| Nghiệp vụ | Quan hệ cần giữ | Hướng khóa ngoại |
|---|---|---|
| Dòng đơn và đơn hàng | Dòng đơn thuộc đúng tenant và đơn | `(tenant_id, order_id)` đến đơn |
| Yêu cầu hoàn tiền | Tham chiếu đúng giao dịch của đơn đang xử lý | Bộ cột định danh tenant, đơn và giao dịch |
| Tệp đính kèm chứng từ | Tệp thuộc đúng hồ sơ hoặc chứng từ | Bộ cột phạm vi và định danh chủ sở hữu |
| Bước phê duyệt | Tham chiếu đúng quy trình | `(tenant_id, workflow_id)` đến quy trình |

Mỗi dòng chỉ bảo vệ quan hệ dữ liệu đã nêu. Hoàn tiền còn cần giới hạn tổng tiền; phê duyệt còn cần đúng người, đúng thứ tự bước và trạng thái hợp lệ; dòng đơn còn cần quy tắc giá. Không suy ra các invariant đó chỉ từ việc khóa ngoại đã hợp lệ.

Khi thiết kế một quan hệ nhạy cảm, hãy hỏi: “Các ID này chỉ cùng tồn tại, hay bắt buộc phải thuộc cùng một đối tượng nghiệp vụ?” Nếu thuộc cùng đối tượng, hãy biểu diễn ngữ cảnh đó trong khóa tham chiếu. Sau đó kiểm tra riêng ai được thực hiện hành động, lúc nào được thực hiện và transaction phải giữ những điều kiện nào đến khi commit.
