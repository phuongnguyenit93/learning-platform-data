# Tham chiếu bằng khóa và nhúng dữ liệu

Một đơn hàng cần hiển thị tên sản phẩm và đơn giá tại thời điểm khách đặt mua. Trong khi đó, thông tin sản phẩm ở danh mục có thể thay đổi nhiều lần: đổi tên, thay giá, ngừng bán hoặc xóa khỏi trang mua hàng. Nếu đơn hàng chỉ giữ **productId** rồi đọc toàn bộ thông tin từ danh mục hiện tại, hóa đơn cũ có nguy cơ hiển thị sai. Nếu đơn hàng sao chép cả hồ sơ sản phẩm, hệ thống lại dễ dư thừa dữ liệu và khó đồng bộ. Đây là bài toán điển hình của hai cách tổ chức quan hệ giữa dữ liệu: **tham chiếu bằng khóa (reference)** và **nhúng dữ liệu (embedding)**.

Bài học thuộc chương **Định danh và quan hệ** của **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ thiết kế quan hệ bền vững giữa các thực thể, so sánh mô hình quan hệ và mô hình tài liệu, tổ chức truy cập persistence trong Java, xử lý cập nhật đồng thời, tiến hóa schema, bảo mật và hiệu năng. Trọng tâm là hiểu **ngữ nghĩa và vòng đời dữ liệu** trước khi chọn cấu trúc lưu trữ.

## 1. Hai cách biểu diễn quan hệ

Xét hai thực thể: sản phẩm **P17** và đơn hàng **O101**.

**Tham chiếu bằng khóa:** bản ghi đơn hàng hoặc dòng đơn hàng lưu định danh sản phẩm và truy cập sản phẩm khi cần.

~~~json
{
  "orderId": "O101",
  "lines": [
    {"productId": "P17", "quantity": 2}
  ]
}
~~~

**Nhúng dữ liệu:** đối tượng cha chứa trực tiếp thông tin mà nó cần dùng, thường là một giá trị con hoặc bản chụp của thực thể khác.

~~~json
{
  "orderId": "O101",
  "lines": [
    {
      "productId": "P17",
      "quantity": 2,
      "productSnapshot": {
        "name": "Sổ tay A5",
        "unitPriceMinor": 45000,
        "currency": "VND"
      }
    }
  ]
}
~~~

Trong ví dụ thứ hai, đơn hàng vẫn **tham chiếu** sản phẩm qua **productId**, đồng thời **nhúng bản chụp** tên và giá tại thời điểm đặt hàng. Hai kỹ thuật không loại trừ nhau.

Phân biệt ba câu hỏi:

- **Dữ liệu thuộc về ai?** Sản phẩm trong danh mục có vòng đời riêng; bản chụp giá trong đơn thuộc ngữ cảnh đơn hàng.
- **Ứng dụng cần trạng thái nào?** Thông tin sản phẩm hiện tại hay thông tin đã được xác nhận trong quá khứ?
- **Quan hệ được đảm bảo ở đâu?** Cơ sở dữ liệu có khóa ngoại hay ứng dụng cần tự kiểm tra và đối soát?

Một trường mang tên **productId** không tự tạo ràng buộc toàn vẹn. Ràng buộc thực tế phụ thuộc cơ chế của kho lưu trữ và cách thiết kế chương trình.

## 2. Tham chiếu bằng khóa: giữ định danh để kết nối

Tham chiếu thường là một ID ổn định như **customer_id**, **product_id** hoặc một khóa ghép gồm **tenant_id + entity_id**. Mô hình quan hệ sử dụng khóa ngoại; kho tài liệu có thể lưu một trường ID và thực hiện tra cứu bổ sung.

Ví dụ logic:

~~~text
PRODUCTS
P17 -> name="Sổ tay A5", currentPrice=45000

ORDER_ITEMS
(O101, line 1) -> productId=P17, quantity=2
(O102, line 1) -> productId=P17, quantity=1
~~~

Khi đổi tên sản phẩm ở bản ghi danh mục, mọi nơi **chủ động đọc dữ liệu hiện tại** theo ID sẽ thấy tên mới. Không cần sao chép bản cập nhật vào hàng nghìn dòng đơn hàng.

### Thuận lợi

1. **Một nơi giữ trạng thái hiện tại:** tránh các bản sao bất đồng bộ của dữ liệu thường xuyên thay đổi.
2. **Tái sử dụng thực thể:** nhiều đơn hàng cùng tham chiếu một sản phẩm hoặc nhiều bài viết cùng tham chiếu một tác giả.
3. **Quan hệ nhiều-nhiều rõ ràng:** dùng bảng liên kết hoặc tập định danh, thay vì nhân bản cả thực thể.
4. **Cập nhật hợp lý:** sửa một sản phẩm không bắt buộc ghi lại tất cả đơn hàng chứa nó.
5. **Khả năng bảo vệ toàn vẹn:** cơ sở dữ liệu quan hệ có thể dùng **FOREIGN KEY** ngăn tham chiếu mồ côi.

### Chi phí và giới hạn

- Khi đọc cả cha lẫn thông tin liên quan, có thể cần **JOIN**, nhiều query hoặc nhiều lần gọi dịch vụ.
- **N+1 query** xuất hiện nếu lấy N đơn hàng rồi truy vấn từng sản phẩm riêng lẻ.
- Trong hệ phân tán, tham chiếu sang dịch vụ khác tạo phụ thuộc mạng, độ trễ và nguy cơ lỗi tạm thời.
- Nếu thực thể được tham chiếu bị xóa hoặc không còn quyền truy cập, mã tham chiếu có thể không giải được.
- Tham chiếu tới **dữ liệu hiện tại** không bảo toàn thông tin lịch sử tại thời điểm phát sinh giao dịch.

**Lưu ý:** Khi cần lưu quan hệ, không nên mặc định dùng khóa tự nhiên dễ thay đổi (như email hoặc tên sản phẩm). Một ID bất biến thường giúp liên kết ổn định hơn. Nếu dùng khóa ghép, cần bảo vệ đầy đủ các thành phần khóa, đặc biệt ranh giới tenant.

## 3. Nhúng dữ liệu: giữ giá trị cạnh nơi sử dụng

Nhúng là lưu một phần dữ liệu phụ thuộc vào bản ghi cha. Trong document database, nhúng thường thể hiện bằng object hoặc mảng con. Trong RDBMS, dữ liệu con có thể nằm ở cột cùng bảng, ở kiểu **JSON/JSONB**, hoặc trong bảng phụ thuộc được quản lý cùng transaction. Cần phân biệt **khái niệm nhúng theo mô hình** với **cách biểu diễn vật lý** của từng hệ quản trị.

Ví dụ document đơn hàng:

~~~json
{
  "_id": "O101",
  "tenantId": "T42",
  "customerId": "C88",
  "placedAt": "2026-11-20T09:30:00Z",
  "lines": [
    {
      "lineNo": 1,
      "catalogProductId": "P17",
      "productSnapshot": {
        "displayName": "Sổ tay A5",
        "unitPriceMinor": 45000,
        "currency": "VND"
      },
      "quantity": 2
    }
  ]
}
~~~

Tên và đơn giá được **chụp lại khi chốt đơn**. Chúng không còn đóng vai trò là bản sao cần đồng bộ theo danh mục. Nếu tên sản phẩm đổi sau một tuần, hóa đơn vẫn giữ tên đã xác nhận. Đây là **nhúng có chủ đích vì ngữ nghĩa lịch sử**.

### Khi nhúng thường phù hợp

- Dữ liệu con là **value object** có ý nghĩa trong phạm vi thực thể cha, ví dụ địa chỉ giao hàng tại thời điểm đặt đơn.
- Con có **vòng đời phụ thuộc** cha, thường được tạo, chỉnh sửa, xóa cùng cha.
- Con có số lượng **được giới hạn hợp lý**, ví dụ vài dòng thông tin cấu hình hoặc mảng nhỏ.
- Phần lớn lượt đọc cần **toàn bộ nhóm dữ liệu** và backend xử lý thuận lợi việc đọc/cập nhật cùng đơn vị.
- Yêu cầu nhất quán tập trung ở một **đơn vị cập nhật nguyên tử** được backend hỗ trợ.

### Khi nhúng gây vấn đề

- Danh sách con tăng không giới hạn, ví dụ nhúng toàn bộ bình luận vào bài viết có hàng triệu bình luận.
- Nhiều tiến trình cùng sửa các phần khác nhau của tài liệu lớn, làm tăng tranh chấp và chi phí ghi lại.
- Thực thể con cần được truy vấn, phân trang, cấp quyền hoặc quản lý độc lập với cha.
- Một giá trị thay đổi liên tục nhưng bị nhân bản trong quá nhiều cha, như **tồn kho hiện tại** của sản phẩm.
- Giá trị phình to vượt giới hạn kích thước record/document của backend hoặc gây tốn băng thông khi chỉ cần một trường nhỏ.

**Đừng xem nhúng là “cứ sao chép càng nhiều càng nhanh”.** Mỗi bản sao đều có chi phí lưu trữ, cập nhật, bảo mật, migration và khôi phục.

## 4. Thực thể, value object và ranh giới vòng đời

Một tiêu chí thiết kế hữu ích là phân biệt **entity** với **value object**.

- **Entity:** có danh tính và vòng đời riêng. Hai sản phẩm có cùng tên và giá vẫn có thể là hai sản phẩm khác nhau. Chúng thường được tham chiếu bằng ID.
- **Value object:** được xác định bởi các thuộc tính mang giá trị, chẳng hạn cặp **số tiền + loại tiền** hoặc **địa chỉ giao hàng đã xác nhận**. Chúng thường phù hợp để nhúng trong thực thể sở hữu.

Ví dụ, **Product** trong danh mục là một entity. **ProductSnapshot** nằm trong đơn là dữ liệu lịch sử: không cần cập nhật khi Product đổi giá. **OrderLine** có thể được xem là thành phần có danh tính cục bộ trong Order (ví dụ **lineNo**) để xử lý sửa/xóa dòng trước khi chốt.

~~~mermaid
flowchart LR
    P["Product P17<br/>Danh mục hiện tại"] -->|ID tham chiếu| L["OrderLine 1<br/>productId=P17"]
    L -->|chứa| S["ProductSnapshot<br/>Tên và giá lúc mua"]
    O["Order O101"] -->|sở hữu| L
~~~

Ranh giới sở hữu quyết định quy tắc thay đổi: chỉnh **Product** không phải lý do để cập nhật **ProductSnapshot** của đơn đã hoàn tất. Nếu nghiệp vụ yêu cầu sửa đơn, đó là một **nghiệp vụ sửa đơn** với quy tắc và dấu vết riêng.

## 5. So sánh theo truy cập, cập nhật và toàn vẹn

| Khía cạnh | Tham chiếu bằng khóa | Nhúng dữ liệu |
|---|---|---|
| Đọc thông tin liên quan | JOIN, lookup hoặc gọi thêm dịch vụ; có thể tối ưu bằng batch | Thường có sẵn khi đọc cha |
| Sửa dữ liệu dùng chung | Một nơi giữ bản hiện tại | Có thể phải cập nhật nhiều bản sao, nếu chúng cần đồng bộ |
| Bảo toàn trạng thái lịch sử | Phải có snapshot/version riêng | Phù hợp để giữ giá trị tại thời điểm phát sinh |
| Quan hệ một-nhiều lớn | Thường dễ phân trang và quản lý riêng | Mảng lớn có thể gây phình và tranh chấp |
| Quan hệ nhiều-nhiều | Dùng bảng liên kết/ID rõ ràng | Dễ nhân bản nhiều phía nếu nhúng cả thực thể |
| Toàn vẹn tham chiếu | FK trong RDBMS; một số kho khác phải kiểm tra bằng ứng dụng | Quan hệ cha-con nội bộ đơn giản; tham chiếu ngoài vẫn cần kiểm tra |
| Transaction | Có thể cần transaction liên bảng/nhiều key | Nếu toàn bộ nằm trong một đơn vị atomic, cập nhật nội bộ có thể thuận lợi |
| Tiến hóa schema | Một bảng hoặc entity có thể đổi độc lập | Mọi snapshot/document đời cũ có thể cần bộ đọc tương thích |
| Bảo mật | Cần ủy quyền cả khi đi theo tham chiếu | Dữ liệu nhạy cảm có thể bị sao chép sang nhiều bản ghi |
| Hiệu năng | Tùy chỉ mục, JOIN, mạng, batching | Tùy kích thước tài liệu, chọn lọc trường, tần suất cập nhật |

Đây là các **xu hướng**, không phải cam kết chung. Một JOIN trên hệ quan hệ có chỉ mục tốt có thể nhanh hơn tải một document rất lớn. Ngược lại, trong hệ phân tán, việc phải gọi 4 dịch vụ để dựng một response có thể chậm hơn nhúng một snapshot nhỏ.

## 6. Quan hệ một-một, một-nhiều và nhiều-nhiều

### Một-một (1:1)

Ví dụ **User** và **UserPreferences**. Nếu preferences nhỏ và luôn đọc/ghi cùng user, nhúng có thể đơn giản. Nếu preferences có quyền truy cập hoặc vòng đời riêng, có thể tách bảng/document và tham chiếu bằng **userId**.

Không nên kết luận “1:1 thì luôn nhúng”: quyền truy cập, sự khác nhau về tần suất cập nhật và cách phân vùng có thể khiến việc tách hợp lý hơn.

### Một-nhiều (1:N)

Ví dụ **Order** có vài **OrderLine**: nhúng nhiều dòng vào một đơn có thể thích hợp, tùy giới hạn kích thước của đơn. **Post** có hàng triệu **Comment**: nên cho comment có ID riêng và truy cập qua khóa ngoại/postId để phân trang, lọc và quản lý tải.

Một ranh giới quan trọng là **tăng trưởng có giới hạn không**. Dữ liệu tăng theo thời gian không nên được nhúng vô hạn chỉ vì API ban đầu cần hiển thị vài phần tử.

### Nhiều-nhiều (N:M)

Ví dụ **Student** và **Course**. Khi cả hai có vòng đời độc lập và một học viên tham gia nhiều khóa học, mô hình liên kết thường rõ ràng hơn:

~~~text
students (student_id)
courses  (course_id)
enrollments (student_id, course_id, enrolled_at, status)
~~~

**Enrollment** có thể là một thực thể quan hệ chứa trạng thái học tập. Nhúng toàn bộ danh sách Course vào mỗi Student và toàn bộ danh sách Student vào mỗi Course sẽ làm dữ liệu lặp lại và phát sinh hai nơi cần đồng bộ.

## 7. Thiết kế kết hợp: tham chiếu dữ liệu hiện tại, nhúng snapshot lịch sử

Với nghiệp vụ đặt hàng, có hai nhu cầu khác nhau:

1. **Tham chiếu để biết sản phẩm nào đã được mua:** lưu **productId** ổn định và kiểm tra rằng sản phẩm thuộc tenant thích hợp.
2. **Nhúng để biết điều gì đã được xác nhận khi mua:** lưu tên hiển thị, đơn giá, đơn vị tiền, thuế/giảm giá và thuộc tính cấu hình có ảnh hưởng đến nghĩa vụ giao hàng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Java Order Service
    participant DB as Database
    C->>A: Place order (productId, quantity)
    A->>DB: Đọc sản phẩm và giá hợp lệ
    DB-->>A: ID, tên, giá, tiền tệ
    A->>A: Xây order line + snapshot
    A->>DB: Ghi Order và OrderLine trong transaction
    DB-->>A: Commit thành công
    A-->>C: orderId
    Note over A,DB: Đổi giá danh mục sau này không đổi snapshot của đơn đã chốt
~~~

**Lưu ý về nghiệp vụ:** giá hiển thị có thể khác giá thực thanh toán do chương trình khuyến mãi, thuế, vận chuyển, làm tròn hoặc thỏa thuận. Snapshot phải chứa **giá được xác nhận thực tế** và đủ dữ liệu để giải thích số tiền, không chỉ đơn giá danh mục. Cần chọn quy tắc làm tròn và kiểu số phù hợp; không sử dụng **double** làm cơ sở tính tiền.

**Về đồng thời:** nếu giá có thể đổi giữa lúc đọc và lúc commit đơn, ứng dụng phải quy định thời điểm khóa giá hoặc cơ chế kiểm tra phiên bản. Ví dụ SQL dưới đây dùng khóa đọc thích hợp cho một luồng tối giản; hệ thống thanh toán thực tế còn cần giải quyết báo giá, tồn kho, thanh toán và idempotency.

## 8. Ví dụ cơ sở dữ liệu quan hệ với khóa ngoại và snapshot

Dưới đây là schema PostgreSQL. Mỗi tenant có sản phẩm và đơn hàng riêng; khóa ghép đảm bảo một dòng đơn không được trỏ tới sản phẩm thuộc tenant khác.

~~~sql
CREATE TABLE products (
    tenant_id UUID NOT NULL,
    id UUID NOT NULL,
    name TEXT NOT NULL,
    current_price_minor BIGINT NOT NULL CHECK (current_price_minor >= 0),
    currency VARCHAR(3) NOT NULL
        CHECK (currency ~ '^[A-Z]{3}$'),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE orders (
    tenant_id UUID NOT NULL,
    id UUID NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE order_items (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    product_name_at_order TEXT NOT NULL,
    unit_price_minor_at_order BIGINT NOT NULL
        CHECK (unit_price_minor_at_order >= 0),
    currency_at_order VARCHAR(3) NOT NULL
        CHECK (currency_at_order ~ '^[A-Z]{3}$'),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders (tenant_id, id),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products (tenant_id, id)
);

CREATE INDEX idx_order_items_product
    ON order_items (tenant_id, product_id);
~~~

**Giải thích từng phần:**

- **product_id** là tham chiếu tới entity Product; **product_name_at_order**, **unit_price_minor_at_order** và **currency_at_order** là bản chụp nghiệp vụ được lưu cùng OrderItem.
- Khóa ngoại ghép **(tenant_id, product_id)** kiểm tra phạm vi tenant tại cơ sở dữ liệu. Chỉ thêm trường **tenant_id** mà không ràng buộc FK đúng cặp sẽ chưa đủ.
- PK của **order_items** chứa **line_no** để phân biệt nhiều dòng trong một đơn, kể cả hai dòng có cùng productId nhưng cấu hình khác nhau.
- FK tới Product mặc định không cho xóa Product khi còn được tham chiếu, trừ khi có hành động hoặc thay đổi ràng buộc. Có thể áp dụng **ngừng bán/soft delete** cho danh mục và giữ bản ghi Product để bảo toàn quan hệ lịch sử.
- Chỉ mục phụ trên **(tenant_id, product_id)** giúp các đường truy vấn ngược từ sản phẩm sang các dòng đơn; chỉ mục cần được lựa chọn theo workload thực tế.

Ví dụ truy vấn đọc hóa đơn:

~~~sql
SELECT oi.order_id,
       oi.line_no,
       oi.product_id,
       oi.quantity,
       oi.product_name_at_order,
       oi.unit_price_minor_at_order,
       oi.currency_at_order
FROM order_items AS oi
WHERE oi.tenant_id = $1 AND oi.order_id = $2
ORDER BY oi.line_no;
~~~

Không cần JOIN sang Product để dựng **thông tin đã chốt trên đơn**. Nếu UI cần hiển thị liên kết đến danh mục hiện tại, có thể lấy Product riêng và phân biệt trường nào từ snapshot, trường nào từ bản ghi mới nhất.

Ví dụ truy vấn cần thêm tên hiện tại:

~~~sql
SELECT oi.line_no,
       oi.product_name_at_order,
       p.name AS current_product_name
FROM order_items AS oi
JOIN products AS p
  ON p.tenant_id = oi.tenant_id
 AND p.id = oi.product_id
WHERE oi.tenant_id = $1 AND oi.order_id = $2
ORDER BY oi.line_no;
~~~

PostgreSQL sử dụng cú pháp tham số **$1, $2** ở cấp SQL prepared statement. Trong JDBC **PreparedStatement** thông thường, dùng dấu **?**; không dùng nguyên các ký hiệu **$1, $2** ở câu Java.

### Đọc và cập nhật nhất quán

Câu SELECT riêng lẻ chưa đảm bảo dữ liệu danh mục không thay đổi ngay trước khi ghi snapshot. Nếu sản phẩm phải được chốt giá đúng với bản ghi đã kiểm tra, có thể chọn **SELECT ... FOR SHARE** trong cùng transaction với các INSERT, để giao dịch UPDATE cùng hàng sản phẩm phải chờ. Mức isolation và chính sách locking của cơ sở dữ liệu cần được xác định theo yêu cầu chính xác của ứng dụng.

~~~sql
BEGIN;

SELECT name, current_price_minor, currency
FROM products
WHERE tenant_id = $1 AND id = $2 AND active = TRUE
FOR SHARE;

-- Xây snapshot từ chính dữ liệu vừa đọc trong transaction.
INSERT INTO orders (tenant_id, id) VALUES ($1, $3);

INSERT INTO order_items (
    tenant_id, order_id, line_no, product_id, quantity,
    product_name_at_order, unit_price_minor_at_order, currency_at_order
) VALUES ($1, $3, 1, $2, $4, $5, $6, $7);

COMMIT;
~~~

Giá trị **$5, $6, $7** phải được gán từ kết quả SELECT do server kiểm soát; không lấy giá khách hàng gửi lên làm nguồn tin cậy. Nếu không tìm thấy Product hợp lệ, phải hủy giao dịch. Đây là ví dụ luồng một sản phẩm, chưa gồm logic thuế, chiết khấu, tồn kho và thanh toán. Việc đặt hàng với nhiều product cần thống nhất thứ tự khóa và chiến lược tránh deadlock theo quy mô thật.

## 9. Nhúng trong document database và giới hạn nguyên tử

Một mô hình document có thể giữ Order và OrderLine trong cùng một document, còn Product là document khác. Ví dụ khái niệm:

~~~json
{
  "_id": "order:T42:O101",
  "tenantId": "T42",
  "version": 3,
  "customerId": "C88",
  "lines": [
    {
      "lineNo": 1,
      "productId": "P17",
      "snapshot": {
        "name": "Sổ tay A5",
        "unitPriceMinor": 45000,
        "currency": "VND"
      },
      "quantity": 2
    }
  ]
}
~~~

Nếu backend hỗ trợ cập nhật nguyên tử **một document**, việc thay đổi những field thuộc cùng Order có thể được commit như một đơn vị. Nhưng **Product document** vẫn là đơn vị riêng. Khi cập nhật cả Product và Order, cần kiểm tra backend hỗ trợ transaction nhiều document hay phải giải quyết bằng thiết kế khác.

Đừng suy ra một cách chung rằng mọi hệ NoSQL đều không có transaction; cũng đừng suy ra mọi ghi nhiều document đều nguyên tử. Phải đọc cam kết thực tế về phạm vi atomicity, isolation, replica và acknowledgement của sản phẩm đang dùng.

### Cảnh báo về mảng nhúng tăng không giới hạn

Giả sử document Customer lưu toàn bộ đơn hàng đã mua:

~~~json
{
  "_id": "C88",
  "orders": [
    {"orderId": "O1", "totalMinor": 120000},
    {"orderId": "O2", "totalMinor": 95000}
  ]
}
~~~

Khi khách hàng có hàng chục nghìn đơn, document ngày càng lớn; việc phân trang, ghi thêm đơn và phục hồi trở nên phức tạp. Cách thực dụng hơn là để **Order** có ID riêng và **customerId**, sau đó đánh chỉ mục theo **(tenantId, customerId, placedAt)** cho trang lịch sử mua hàng. Chỉ nhúng **tóm tắt giới hạn số lượng** nếu UI thật sự cần và có chính sách cập nhật rõ ràng.

### Tham chiếu trong document database không đồng nghĩa có FK

Nếu document Order chỉ giữ **productId**, backend có thể không tự kiểm tra Product tồn tại. Ứng dụng có thể kiểm tra trước khi tạo, nhưng Product vẫn có thể bị xóa giữa hai thao tác nếu không có cơ chế đồng bộ phù hợp. Cần chọn chính sách: giữ Product lịch sử, soft delete, tự đối soát, hay áp dụng transaction được hỗ trợ. Không coi “đã GET được Product” là cam kết tồn tại vĩnh viễn.

## 10. Triển khai trong Java: phân biệt identity và snapshot

Một lớp domain có thể biểu diễn ID tham chiếu và giá trị nhúng bằng các kiểu riêng. Java 17 **record** phù hợp cho DTO và value object không cần identity riêng.

~~~java
import java.util.List;
import java.util.UUID;

record ProductId(UUID value) {}

record Money(long minorUnits, String currency) {
    public Money {
        if (minorUnits < 0) throw new IllegalArgumentException("negative amount");
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("invalid currency");
        }
    }
}

record ProductSnapshot(String name, Money unitPrice) {
    public ProductSnapshot {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("missing name");
        }
    }
}

record OrderLine(int lineNo, ProductId productId,
                 ProductSnapshot snapshot, int quantity) {
    public OrderLine {
        if (lineNo <= 0 || quantity <= 0 || productId == null ||
            snapshot == null) {
            throw new IllegalArgumentException("invalid order line");
        }
    }
}

record Order(UUID id, UUID tenantId, List<OrderLine> lines) {
    public Order {
        if (id == null || tenantId == null || lines == null ||
            lines.isEmpty()) {
            throw new IllegalArgumentException("invalid order");
        }
        lines = List.copyOf(lines);
    }
}
~~~

Ở đây:

- **ProductId** giữ identity của Product được tham chiếu. Nó không chứa tên hay giá hiện tại.
- **ProductSnapshot** là value object nằm trong OrderLine. Giá trị này được chốt tại thời điểm tạo giao dịch.
- **Order** sở hữu danh sách OrderLine; khi dùng thiết kế bất biến, cập nhật tạo trạng thái Order mới và repository quyết định cách ghi an toàn.
- **Money** sử dụng đơn vị nhỏ nhất dưới dạng **long** để minh họa. Trong hệ thống thực tế, quy tắc số chữ số thập phân của từng loại tiền, làm tròn và giới hạn tràn số phải được xử lý rõ; **BigDecimal** có thể phù hợp hơn cho các phép tính nghiệp vụ.

Không nên cho controller tùy ý lấy **productName** hay **price** từ request để ghi vào snapshot: dịch vụ đặt hàng phải dùng nguồn định giá đã được xác thực và áp dụng các quy tắc khuyến mãi, thuế, thanh toán.

### Ví dụ repository JDBC với transaction

Ví dụ sau minh họa cách một dịch vụ Java đọc Product và lưu **Order + OrderItem** trong cùng transaction; dùng PostgreSQL như ở phần schema trước:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

final class JdbcOrderWriter {
    private final DataSource dataSource;

    JdbcOrderWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    UUID placeOneItemOrder(UUID tenantId, UUID productId, int quantity)
            throws SQLException {
        if (tenantId == null || productId == null || quantity <= 0) {
            throw new IllegalArgumentException("invalid request");
        }

        UUID orderId = UUID.randomUUID();
        try (Connection c = dataSource.getConnection()) {
            boolean originalAutoCommit = c.getAutoCommit();
            try {
                c.setAutoCommit(false);

                String name;
                long price;
                String currency;
                try (PreparedStatement ps = c.prepareStatement("""
                        SELECT name, current_price_minor, currency
                        FROM products
                        WHERE tenant_id = ? AND id = ? AND active = TRUE
                        FOR SHARE
                        """)) {
                    ps.setObject(1, tenantId);
                    ps.setObject(2, productId);
                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) {
                            throw new IllegalArgumentException("product not found");
                        }
                        name = rs.getString("name");
                        price = rs.getLong("current_price_minor");
                        currency = rs.getString("currency");
                    }
                }

                try (PreparedStatement ps = c.prepareStatement("""
                        INSERT INTO orders (tenant_id, id) VALUES (?, ?)
                        """)) {
                    ps.setObject(1, tenantId);
                    ps.setObject(2, orderId);
                    ps.executeUpdate();
                }

                try (PreparedStatement ps = c.prepareStatement("""
                        INSERT INTO order_items (
                          tenant_id, order_id, line_no, product_id, quantity,
                          product_name_at_order, unit_price_minor_at_order,
                          currency_at_order
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """)) {
                    ps.setObject(1, tenantId);
                    ps.setObject(2, orderId);
                    ps.setInt(3, 1);
                    ps.setObject(4, productId);
                    ps.setInt(5, quantity);
                    ps.setString(6, name);
                    ps.setLong(7, price);
                    ps.setString(8, currency);
                    ps.executeUpdate();
                }

                c.commit();
                return orderId;
            } catch (SQLException | RuntimeException ex) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            } finally {
                c.setAutoCommit(originalAutoCommit);
            }
        }
    }
}
~~~

**Các giới hạn của ví dụ:** đây là luồng ghi đơn một sản phẩm để thấy **ràng buộc tham chiếu** và **snapshot**. Hệ thống thực tế cần transaction boundary do framework hoặc lớp ứng dụng quản lý; kiểm tra quyền của tenant theo danh tính đã xác thực; xử lý timeout/unknown commit, idempotency, giới hạn số lượng, tồn kho, báo giá, thuế, discount, thanh toán và các lỗi constraint. Nếu kết nối lỗi ở giai đoạn commit, **client có thể không biết transaction đã commit hay chưa**, nên retry cùng yêu cầu cần có idempotency key, không đơn giản tạo orderId mới và thực hiện lại.

### Tránh N+1 khi đọc tham chiếu

Giả sử API trả 100 đơn hàng, mỗi đơn có 5 dòng. Nếu đọc từng **productId** riêng lẻ, tầng repository có thể tạo hàng trăm query. Có các cách thay thế:

- Dùng JOIN nếu thông tin cần lấy nằm trong cùng RDBMS và chỉ mục phù hợp.
- Lấy danh sách **productId** duy nhất rồi đọc theo batch, ghép kết quả bằng Map, vẫn kiểm soát tenant.
- Chỉ đọc snapshot cho màn hình hóa đơn; không tải Product khi không cần thông tin hiện tại.
- Với ORM, chọn fetch plan rõ ràng để tránh N+1 và tránh tải dư dữ liệu qua nhiều quan hệ.

Không bật eager loading cho mọi quan hệ một cách máy móc. Cần đo SQL thực tế, số lượt truy vấn, kích thước dữ liệu và độ trễ p95/p99 theo các kịch bản sử dụng.

## 11. Cập nhật, xóa và đồng thời

Tham chiếu và nhúng tạo những loại lỗi khác nhau:

**Lỗi khi tham chiếu:** Product P17 đã bị xóa, OrderLine vẫn chứa productId P17. Nếu DB không có FK hoặc không thực thi cùng phạm vi, tham chiếu có thể mồ côi. Nếu có FK, việc xóa có thể bị từ chối; thiết kế phải quy định xóa cứng, ngừng bán hay lưu lịch sử.

**Lỗi khi nhúng:** Product được đổi tên, nhưng 10.000 tài liệu nhúng bản sao có mục đích hiển thị **tên hiện tại** vẫn là tên cũ. Khi đó bản sao là dữ liệu đồng bộ, cần kế hoạch cập nhật, event, version và đối soát. Nếu các snapshot phản ánh **tên tại thời điểm mua**, việc không đổi tên trong đơn lại là hành vi đúng.

**Lost update trên tài liệu nhúng:**

~~~text
t1  A đọc Order version=8, quantity=1
t2  B đọc Order version=8, quantity=1
t3  A tăng quantity lên 2, ghi cả document
t4  B sửa địa chỉ giao hàng, ghi cả document từ version=8
    -> có thể làm quantity quay về 1
~~~

Cách xử lý thường là **compare-and-set theo version** hoặc cập nhật nguyên tử đúng trường khi backend hỗ trợ. Nếu ghi có điều kiện thất bại, ứng dụng đọc lại và giải quyết conflict theo luật nghiệp vụ. **Version nằm trong JSON chưa đủ**, kiểm tra điều kiện và ghi phải diễn ra nguyên tử.

### Khi nào cần transaction nhiều bản ghi?

- Tạo Order và nhiều OrderItem trong schema quan hệ.
- Chuyển một đối tượng từ cha A sang cha B kèm cập nhật chỉ mục phụ.
- Ghi trạng thái và phát event trong cùng nghiệp vụ, cần cơ chế nhất quán như **transactional outbox** nếu dùng message broker.
- Cập nhật cả bản gốc lẫn bản sao vật chất hóa mà người dùng bắt buộc thấy ngay nhất quán.

Không phải mọi quan hệ phân tán đều có transaction bao trùm. Khi dùng eventual consistency, mô tả rõ thời gian trễ chấp nhận được, trạng thái tạm thời, cách retry, cơ chế idempotent và quy trình sửa sai.

## 12. Tiến hóa schema và di chuyển giữa hai cách lưu

Theo thời gian, bạn có thể cần chuyển từ nhúng toàn bộ thông tin liên hệ của khách hàng trong từng đơn sang **customerId** tham chiếu, hoặc chuyển từ tra cứu giá hiện tại sang snapshot giá chốt đơn. Migration phải bảo vệ dữ liệu cũ và nghĩa của chúng.

### Từ nhúng sang tham chiếu

1. Xác định thuộc tính nào thực sự đại diện cho cùng một entity, không gộp nhầm hai người chỉ vì trùng tên.
2. Xây một bảng/document thực thể đích, cấp ID ổn định và quy tắc UNIQUE phù hợp.
3. Backfill ID trong các cha bằng quy trình có thể chạy lại; kiểm tra giá trị thiếu, mơ hồ và xung đột.
4. Trong giai đoạn chuyển tiếp, dùng bộ đọc hỗ trợ cả định dạng cũ và mới; có cơ chế đồng bộ khi cần.
5. Thêm FK/chỉ mục hoặc quy tắc kiểm tra tham chiếu; đối soát số lượng hàng mồ côi.
6. Chỉ bỏ field nhúng cũ khi đã xác minh không có hệ thống nào cần giá trị cũ để giải thích lịch sử.

### Từ tham chiếu sang snapshot nhúng

1. Xác định **thời điểm lịch sử** cần lưu: lúc tạo đơn, xác nhận giá hay lúc thanh toán.
2. Xem nguồn dữ liệu có giữ **lịch sử phiên bản** hay không. Không thể suy ra chính xác giá mua trong quá khứ chỉ từ giá hiện tại.
3. Backfill các snapshot có thể xác minh từ bảng lịch sử/giao dịch; với phần thiếu, đánh dấu chất lượng dữ liệu và xử lý theo nghiệp vụ.
4. Cập nhật luồng tạo mới để chụp snapshot trong transaction/quy trình nhất quán.
5. Hỗ trợ đọc các schema version cũ, kiểm tra dung lượng record/document và lập kế hoạch dọn dữ liệu không còn dùng.

**Không được lặng lẽ ghi giá hiện tại vào trường “giá lúc mua” của đơn hàng cũ.** Đó là thay đổi sự thật nghiệp vụ, dù câu lệnh backfill chạy thành công.

### Version của dữ liệu nhúng

Có thể lưu **schemaVersion** của document để bộ đọc nhận diện định dạng cũ. Ví dụ tên trường đổi từ **unitPrice** sang **unitPriceMinor** cần migration và quy tắc chuyển đổi rõ (loại tiền, số chữ số thập phân, làm tròn). Nếu trường bổ sung có default, phải xác định default có đúng với bản ghi lịch sử không; tránh tự gán một giá trị sai nhưng hợp lệ về mặt kỹ thuật.

## 13. Bảo mật, sao lưu và quan sát

Các bản sao nhúng làm tăng số vị trí chứa dữ liệu. Nếu nhúng **email**, **địa chỉ giao hàng**, **số điện thoại** hoặc dữ liệu nhạy cảm trong nhiều đơn, việc kiểm soát truy cập, mã hóa, logging, lưu giữ và yêu cầu xóa theo quy định trở nên phức tạp hơn.

Một số nguyên tắc:

- **Tenant isolation:** tham chiếu phải mang đủ phạm vi tenant hoặc được DB đảm bảo bằng FK ghép; khi đọc document cũng phải lọc theo tenant lấy từ ngữ cảnh xác thực, không tin tenantId tự khai từ client.
- **Least privilege:** chỉ nhúng thuộc tính mà use case thực sự cần; không lưu toàn bộ Product/Customer chứa trường nhạy cảm nếu đơn chỉ cần tên hiển thị.
- **Tách dữ liệu lịch sử hợp pháp:** snapshot có thể cần giữ để chứng minh giao dịch, trong khi các trường thông tin cá nhân khác phải được ẩn, xóa hoặc xử lý theo chính sách lưu trữ. Quyết định cần căn cứ yêu cầu nghiệp vụ và pháp lý.
- **Khôi phục nhất quán:** khi backup/restore, xác minh các quan hệ FK, tài liệu tham chiếu, chỉ mục phụ và snapshot không bị mất một phía do khôi phục lệch thời điểm.
- **Quan sát tính toàn vẹn:** đo tỷ lệ tham chiếu mồ côi, bản sao hiện tại bị trễ, lỗi decode schema, xung đột phiên bản, timeout, query N+1 và dung lượng tài liệu.
- **Thông tin trong log:** log correlation ID, orderId và mã lỗi thích hợp, hạn chế log toàn bộ snapshot có PII.

Với hệ thống nhiều nguồn, có thể dùng event để cập nhật các **read model** nhúng dữ liệu tổng hợp. Event là thông báo thay đổi, không tự bảo đảm đã cập nhật tất cả bản sao. Cần idempotency, version/ordering, retry, dead-letter, giám sát lag và kế hoạch rebuild.

## 14. Đánh giá hiệu năng theo đường truy cập

Không thể chọn tham chiếu hay nhúng chỉ bằng số lượng bảng hoặc số lần JOIN. Cần đo chính xác **truy vấn nghiệp vụ**:

| Tình huống | Cần đo | Hướng cân nhắc |
|---|---|---|
| Hiển thị chi tiết đơn hàng | Số query, p95 thời gian, byte đọc, hiệu quả index | Snapshot trong đơn tránh phải JOIN danh mục hiện tại |
| Danh sách 100 đơn | N+1 query, batch size, số dòng scan | JOIN/batch theo ID, phân trang |
| Cập nhật tên sản phẩm | Số bản sao cần đổi, write amplification, lag | Tham chiếu cho trạng thái hiện tại |
| Một customer có hàng triệu đơn | Kích thước tài liệu, chi phí phân trang | Đơn có ID riêng và chỉ mục theo customer |
| Nhiều người sửa một document | Xung đột version, retry, độ trễ ghi | Chia aggregate hoặc cập nhật theo trường/atomic operation |
| Đọc liên vùng/dịch vụ | Số round trip, timeout, độ trễ mạng | Read model/snapshot có kiểm soát |

Các giá trị p50, p95 và p99 nên được đo trong tải đại diện, cùng kích thước dữ liệu và mô hình đọc/ghi thực tế. **Ít truy vấn hơn** không đồng nghĩa **độ trễ luôn thấp hơn** nếu mỗi truy vấn phải đọc khối dữ liệu lớn. Ngược lại, mô hình tham chiếu tốt cũng có thể hoạt động hiệu quả nhờ chỉ mục, JOIN có kế hoạch tốt và connection pool đúng kích thước.

## 15. Quy trình lựa chọn mô hình

Trước khi thiết kế quan hệ, trả lời lần lượt:

1. **Đơn vị định danh là gì?** Con có ID và vòng đời riêng không, hay chỉ là giá trị thuộc cha?
2. **Đường đọc phổ biến nhất?** Đọc cả cha-con hay truy vấn con độc lập, lọc/sắp xếp/phân trang theo thuộc tính nào?
3. **Quy mô tăng trưởng?** Số con nhỏ, có giới hạn hay tăng vô tận?
4. **Tần suất cập nhật và người ghi?** Mỗi phía có thể thay đổi độc lập, có nhiều người sửa đồng thời không?
5. **Cần dữ liệu hiện tại hay lịch sử?** Tên/giá hiện tại và tên/giá lúc giao dịch có cùng ý nghĩa không?
6. **Ranh giới nhất quán?** Những field nào bắt buộc thay đổi cùng nhau; backend có transaction hoặc atomic operation ở phạm vi đó không?
7. **Toàn vẹn tham chiếu và cô lập tenant?** FK, khóa ghép, kiểm tra ứng dụng hoặc đối soát vận hành nào phải có?
8. **Bảo mật và lưu giữ?** Nhúng bản sao có làm lan rộng dữ liệu cá nhân hoặc gây khó khăn cho xóa dữ liệu không?
9. **Đo và kiểm chứng:** đã có bằng chứng về chi phí JOIN, số query, write amplification và kích thước tài liệu dưới tải đại diện chưa?

Một chiến lược thường hiệu quả là **tham chiếu thực thể có danh tính, vòng đời độc lập**, **nhúng value object thuộc về cha**, và **giữ snapshot khi lịch sử không được phép đổi theo bản ghi hiện tại**. Đây là định hướng để đặt câu hỏi, không phải quy tắc áp dụng máy móc.

## 16. Bài thực hành: mô hình hóa đơn hàng và danh mục

Dịch vụ Java bán hàng phục vụ nhiều tenant. Danh mục gồm sản phẩm có **productId**, tên, giá bán và tồn kho; một đơn hàng có từ một đến vài chục dòng. Khách hàng có thể xem hóa đơn sau nhiều năm; sản phẩm có thể đổi giá, đổi tên hoặc ngừng bán. API cần liệt kê đơn theo khách hàng, truy cập chi tiết đơn theo **orderId** và đôi khi tìm các đơn có chứa một sản phẩm.

**Yêu cầu:**

1. Chọn trường nào trong OrderLine nên là **tham chiếu**, trường nào là **snapshot nhúng**; giải thích ý nghĩa khi giá sản phẩm thay đổi.
2. Đề xuất schema SQL với PK, FK, constraint tenant và chỉ mục phù hợp cho các đường truy vấn.
3. Phác thảo document Order có mảng line giới hạn và đề xuất thời điểm cần tách dòng đơn thành entity riêng.
4. Nêu cách tạo Order và các line trong một transaction; xác định xử lý khi Product bị xóa hoặc hết hàng giữa lúc đặt đơn.
5. Phân tích lỗi **N+1** khi hiển thị 100 đơn cùng danh mục; đưa ra hai cách giảm query.
6. Mô tả race condition khi hai tác vụ cùng sửa document đơn và cách dùng version/CAS.
7. Lập kế hoạch migration nếu schema cũ chỉ lưu productId và không lưu giá tại thời điểm mua.
8. Đề xuất các chỉ số quan sát cho chất lượng dữ liệu, p95 truy vấn, lag cập nhật và lỗi giải mã.

**Gợi ý hướng giải:** OrderLine tham chiếu Product qua khóa **(tenantId, productId)** nhưng giữ **productNameAtOrder**, **unitPriceAtOrder**, **currency** và thông tin cấu thành giá thực đã xác nhận như snapshot. Order được truy vấn theo khóa tenant/orderId; danh sách đơn theo khách hàng dùng chỉ mục **(tenantId, customerId, placedAt)** nếu schema có customerId. Product có vòng đời độc lập; việc ngừng bán không làm mất tham chiếu lịch sử. Transaction ghi Order/OrderItem và cơ chế đồng bộ tồn kho phải phản ánh đúng quy tắc nghiệp vụ. Giá lịch sử không thể tái dựng chính xác chỉ từ giá hiện tại; dữ liệu cũ cần lịch sử giá hoặc dấu hiệu rằng giá trị chưa xác định.

### Câu hỏi tự kiểm tra

- Vì sao lưu **productId** trong OrderLine không tự bảo đảm sản phẩm tồn tại nếu backend không hỗ trợ FK?
- Tại sao cùng một OrderLine có thể vừa chứa **productId** vừa chứa **productSnapshot**?
- Trường hợp nào nên tách danh sách con thành bảng/document riêng dù ban đầu chỉ có một mảng nhỏ?
- Vì sao một lần cập nhật document nguyên tử vẫn chưa chắc tránh được lost update của hai lần đọc rồi ghi?
- Khác nhau giữa bản sao cần đồng bộ với **snapshot lịch sử** là gì?
- Làm thế nào chuyển từ mô hình chỉ tham chiếu sang snapshot mà không tạo sai lệch dữ liệu lịch sử?

Sau bài học, người học cần giải thích được sự khác nhau giữa tham chiếu bằng khóa và nhúng dữ liệu, quyết định dựa trên vòng đời và đường truy cập của thực thể, xây ranh giới persistence Java phù hợp, đồng thời bảo vệ tính toàn vẹn, tính nhất quán và giá trị lịch sử của dữ liệu.
