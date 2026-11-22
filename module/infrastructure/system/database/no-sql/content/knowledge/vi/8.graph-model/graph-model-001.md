# Nút, cạnh, thuộc tính và định danh của phần tử đồ thị trong NoSQL

## 1. Vì sao dữ liệu đồ thị cần một cách nhìn khác?

Trong nhiều ứng dụng, câu hỏi quan trọng không chỉ là “một thực thể có những trường nào?” mà còn là **“thực thể đó liên quan đến ai, điều gì và qua những bước nào?”**. Ví dụ:

- Một khách hàng đã đặt những đơn hàng nào?
- Một đơn hàng chứa những sản phẩm nào, mỗi sản phẩm mua bao nhiêu?
- Một người theo dõi những ai; ai đang theo dõi người ấy?
- Một dịch vụ phụ thuộc trực tiếp hoặc gián tiếp vào những dịch vụ nào?
- Một người được cấp quyền truy cập tài nguyên thông qua nhóm hoặc vai trò nào?

Một **graph database** biểu diễn các thực thể và mối quan hệ thành một cấu trúc có thể duyệt theo liên kết. Đây là một họ trong NoSQL, phù hợp đặc biệt với các yêu cầu mà **quan hệ giữa các thực thể là dữ liệu cốt lõi**.

Trong bài này, ta dùng mô hình **labeled property graph** được Neo4j sử dụng để giải thích bốn thành phần nền tảng:

1. **Nút (node/vertex):** phần tử biểu diễn thực thể hoặc một khái niệm.
2. **Cạnh (edge/relationship):** liên kết mang ý nghĩa giữa các nút.
3. **Thuộc tính (property):** dữ liệu mô tả nút hoặc cạnh.
4. **Định danh (identity/identifier):** cách phân biệt một phần tử với những phần tử khác và tìm lại nó ổn định.

Các ví dụ dùng cú pháp **Cypher của Neo4j**. Một graph database khác có thể đặt tên, hỗ trợ kiểu quan hệ hoặc quy định ID khác; không nên xem cú pháp Cypher là cú pháp chuẩn của mọi hệ lưu trữ đồ thị.

## 2. Nhìn tổng thể bằng một đồ thị đơn hàng

Giả sử cửa hàng sách có một khách hàng, một đơn hàng và hai sản phẩm:

```text
  (Customer C001)
        |
        | PLACED
        v
   (Order O1001) -------- CONTAINS {quantity: 2} -------> (Product P10)
        |
        +---------------- CONTAINS {quantity: 1} -------> (Product P20)
```

Các hình elip trong sơ đồ là **nút**. Các mũi tên có nhãn `PLACED`, `CONTAINS` là **cạnh có hướng và có loại**. Phần `{quantity: 2}` là **thuộc tính của cạnh** nối đơn hàng với sản phẩm P10.

Trong toán học, một đồ thị có thể được mô tả khái quát bởi:

\[
G=(V,E)
\]

Trong đó:

- \(V\) là tập các nút (*vertices*).
- \(E\) là tập các cạnh (*edges*), mỗi cạnh nối những đầu mút xác định.

Mô hình **property graph** bổ sung nhãn và thuộc tính:

\[
\text{Node} = (\text{identity},\ \text{labels},\ \text{properties})
\]

\[
\text{Relationship} =
(\text{identity},\ \text{startNode},\ \text{type},\ \text{endNode},\ \text{properties})
\]

Đây là **mô hình khái niệm** giúp đọc hiểu cấu trúc, không phải định nghĩa chính xác của mọi API quản lý ID. Trong graph database cụ thể, nhãn, thuộc tính, ID nội bộ và các ràng buộc duy nhất có quy tắc riêng.

| Thành phần | Ví dụ | Ý nghĩa nghiệp vụ |
|---|---|---|
| Nút | `(:Customer {customerId: "C001"})` | Một khách hàng |
| Nhãn nút | `Customer`, `Order`, `Product` | Phân loại các nút |
| Cạnh | `(Customer)-[:PLACED]->(Order)` | Khách hàng đã đặt đơn |
| Loại cạnh | `PLACED`, `CONTAINS` | Định nghĩa nghĩa của liên kết |
| Thuộc tính nút | `name`, `createdAt`, `status` | Mô tả thực thể |
| Thuộc tính cạnh | `quantity`, `unitPriceAtPurchase` | Mô tả quan hệ hoặc lần tương tác |
| ID nghiệp vụ | `customerId`, `orderId`, `sku` | Tìm đúng thực thể qua API và dữ liệu lâu dài |
| ID nội bộ | ID do hệ quản trị cấp | Hỗ trợ quản lý phần tử bên trong hệ lưu trữ |

## 3. Nút (node): xác định đâu là một thực thể

**Nút** thường biểu diễn một thứ có **danh tính riêng** mà ứng dụng muốn truy vấn, liên kết hoặc quản lý vòng đời độc lập. Ví dụ:

- `Customer` — khách hàng.
- `Order` — đơn hàng.
- `Product` — sản phẩm.
- `User`, `Team`, `Role` — người dùng, nhóm, vai trò.
- `Service`, `Database` — thành phần của hệ thống kỹ thuật.

Một nút có thể có **nhãn (label)** để cho biết nó thuộc loại nào, và **thuộc tính (properties)** mô tả nó.

Ví dụ ở dạng Cypher:

```cypher
CREATE (c:Customer {
  customerId: 'C001',
  name: 'Mai',
  loyaltyTier: 'SILVER'
})
RETURN c;
```

Trong đó:

- `c` là tên biến **tạm thời trong câu truy vấn**. Nó không phải ID của khách.
- `:Customer` là nhãn của nút.
- `customerId`, `name`, `loyaltyTier` là các thuộc tính.
- `C001` là định danh nghiệp vụ do ứng dụng quy định.

### Nhãn nút không phải ID

Một hệ thống có thể có hàng triệu nút đều mang nhãn `Customer`. Nhãn chỉ giúp phân loại, lọc hoặc áp dụng ràng buộc/index; **không dùng để phân biệt riêng một khách hàng**.

Trong Neo4j, một nút cũng có thể mang **nhiều nhãn**, ví dụ:

```cypher
CREATE (p:Person:Customer {
  personId: 'U001',
  customerId: 'C001',
  name: 'Mai'
})
RETURN p;
```

Đây vẫn chỉ là **một nút**, mang cả nhãn `Person` và `Customer`; không phải hai nút được tạo rồi nối với nhau. Nên thêm nhãn khi nó mang ý nghĩa thực sự trong miền dữ liệu hoặc trong cách truy vấn, thay vì nhân nhãn cho mọi trạng thái vụn vặt.

### Khi nào nên tạo một nút mới?

Một dữ liệu thường đáng trở thành nút khi nó:

1. Cần được nhận diện độc lập, chẳng hạn sản phẩm có `sku` riêng.
2. Được nhiều thực thể khác cùng tham chiếu, chẳng hạn một nhóm quyền có nhiều thành viên.
3. Có quan hệ riêng cần duyệt, chẳng hạn một dự án phụ thuộc vào nhiều dịch vụ.
4. Có vòng đời hoặc quy tắc cập nhật độc lập, chẳng hạn một đơn hàng có trạng thái riêng.

Ngược lại, tên hiển thị của khách, màu sắc sản phẩm hoặc số điện thoại giao hàng thường phù hợp làm **thuộc tính** khi không có quan hệ riêng đáng quản lý.

### Phân biệt thực thể với giá trị

Xem hai lựa chọn:

```text
Phương án A:
(Customer {customerId: "C001", city: "Hà Nội"})

Phương án B:
(Customer {customerId: "C001"})-[:LIVES_IN]->(City {code: "HN"})
```

Phương án A đơn giản nếu ứng dụng chỉ cần hiển thị hoặc lọc theo tên thành phố. Phương án B hữu ích nếu thành phố có nhiều thuộc tính riêng và các quan hệ đáng truy vấn, như thuộc tỉnh/vùng nào, kết nối tuyến vận tải nào, hoặc có bao nhiêu khách hàng đang sinh sống.

Không phải mọi chuỗi trong document đều cần đổi thành nút. **Mức độ quan trọng của quan hệ và access pattern** mới là lý do chọn cấu trúc đồ thị.

## 4. Cạnh (relationship/edge): quan hệ là dữ liệu

**Cạnh** kết nối hai nút và diễn đạt một mối liên hệ. Trong labeled property graph của Neo4j, mỗi relationship:

- Có **nút bắt đầu** và **nút kết thúc**.
- Có **đúng một loại (relationship type)**.
- Có thể có **các thuộc tính riêng**.
- Là một phần tử của đồ thị, khác với hai nút mà nó kết nối.

Ví dụ:

```cypher
MATCH (c:Customer {customerId: 'C001'})
MATCH (o:Order {orderId: 'O1001'})
CREATE (c)-[:PLACED]->(o);
```

Đọc thành câu nghiệp vụ: **khách hàng C001 đã đặt đơn O1001**.

### Hướng của cạnh

`(c)-[:PLACED]->(o)` biểu diễn chiều **từ khách hàng đến đơn hàng**. Truy vấn đảo hướng vẫn có thể tìm được cạnh đã lưu:

```cypher
// Từ khách tìm những đơn khách đã đặt.
MATCH (c:Customer {customerId: 'C001'})-[:PLACED]->(o:Order)
RETURN o.orderId;

// Từ đơn tìm khách đã đặt đơn (duyệt ngược cạnh đã lưu).
MATCH (o:Order {orderId: 'O1001'})<-[:PLACED]-(c:Customer)
RETURN c.customerId;
```

Hướng mũi tên là một phần của cấu trúc và ngữ nghĩa; câu truy vấn có thể **duyệt ngược một cạnh đã lưu** bằng cách viết đúng mẫu. Khi muốn tìm cạnh thuộc loại đó bất kể hướng, Cypher hỗ trợ biểu diễn không chỉ rõ hướng:

```cypher
MATCH (a)-[:RELATED_TO]-(b)
RETURN a, b
LIMIT 10;
```

Mẫu không ghi hướng là cách **truy vấn**, không có nghĩa cạnh lưu trong Neo4j trở thành vô hướng hoặc mặc nhiên có thêm một cạnh ngược.

### Quan hệ một chiều không đồng nghĩa quan hệ đối xứng

Trong mạng xã hội:

```text
(User U01)-[:FOLLOWS]->(User U02)
```

Điều đó có nghĩa U01 theo dõi U02, **không suy ra** U02 cũng theo dõi U01. Nếu hai người theo dõi lẫn nhau, có thể tồn tại hai cạnh:

```text
(U01)-[:FOLLOWS]->(U02)
(U02)-[:FOLLOWS]->(U01)
```

Với quan hệ có tính đối xứng về nghiệp vụ, như “hai người là bạn sau khi cả hai đồng ý”, cần thống nhất cách lưu (một cạnh và truy vấn hai đầu, hoặc hai cạnh theo quy ước) để tránh dữ liệu mâu thuẫn.

### Cạnh có thể tự nối và có thể song song

Theo mô hình property graph, đồ thị có thể có:

- **Self-loop:** cạnh đi từ một nút trở lại chính nó, ví dụ một tài khoản có quy tắc chuyển tiếp về chính nó (nếu nghiệp vụ cho phép).
- **Nhiều cạnh giữa cùng hai nút:** có thể có `FOLLOWS`, `WORKS_WITH` hoặc nhiều quan hệ `PURCHASED` theo các lần giao dịch khác nhau.

Hai cạnh nối cùng cặp nút **không tự động là cùng một cạnh**, kể cả khi cùng loại. Cần định nghĩa nghiệp vụ có cho phép nhiều lần tương tác hay chỉ cho phép một quan hệ logic.

## 5. Thuộc tính: đặt dữ liệu trên nút hay trên cạnh?

Trong property graph, cả nút lẫn cạnh có thể mang cặp **key–value**.

Ví dụ một khách hàng:

```text
(:Customer {
  customerId: "C001",
  name: "Mai",
  loyaltyTier: "SILVER"
})
```

Ví dụ một quan hệ đơn hàng chứa sản phẩm:

```text
(:Order {orderId: "O1001"})
   -[:CONTAINS {quantity: 2, unitPriceAtPurchase: 150000}]->
(:Product {sku: "P10", name: "Sách A"})
```

**`name`** là đặc tính của sản phẩm; **`quantity`** là đặc tính của *lần sản phẩm xuất hiện trong đơn đó*. Nếu P10 xuất hiện trong hai đơn, mỗi cạnh `CONTAINS` có thể có `quantity` khác nhau.

Giá hiện tại và giá tại thời điểm giao dịch cũng khác nhau:

| Dữ liệu | Đặt ở đâu? | Lý do |
|---|---|---|
| `Product.name` | Thuộc tính nút `Product` | Mô tả sản phẩm hiện tại |
| `Product.currentPrice` | Thuộc tính nút `Product` | Giá niêm yết hiện tại |
| `CONTAINS.quantity` | Thuộc tính cạnh `Order → Product` | Gắn với số lượng trong một đơn cụ thể |
| `CONTAINS.unitPriceAtPurchase` | Thuộc tính cạnh `Order → Product` | Giữ giá lịch sử của giao dịch |
| `Order.status` | Thuộc tính nút `Order` | Trạng thái của chính đơn hàng |
| `PLACED.placedAt`, nếu cần | Thuộc tính cạnh `Customer → Order` | Thời điểm quan hệ đặt đơn phát sinh |

Không nên đặt `quantity` lên nút `Product` nếu đó là số lượng của từng đơn: một sản phẩm có thể xuất hiện trong nhiều đơn với số lượng khác nhau.

### Kiểu dữ liệu thuộc tính của Neo4j

Các thuộc tính cơ bản trong Neo4j có thể chứa chuỗi, số, boolean, dữ liệu thời gian, tọa độ và **mảng/list giá trị đơn giản được hỗ trợ**. Không được mặc định rằng một thuộc tính Neo4j có thể chứa object lồng nhau tùy ý giống document JSON.

Ví dụ hợp lý:

```cypher
CREATE (p:Product {
  sku: 'P10',
  name: 'Sách A',
  tags: ['education', 'book'],
  active: true
});
```

Nếu cần lưu nhiều đối tượng con có danh tính hoặc thuộc tính riêng, có thể mô hình hóa chúng thành các nút và cạnh thay vì cố gắng nhét một cấu trúc JSON sâu vào một thuộc tính. Ngoài ra, Neo4j **không lưu thuộc tính có giá trị `null` như một giá trị độc lập**: đặt một property thành `null` thường mang nghĩa xóa property đó. Vì vậy phải phân biệt **không có trường** với một giá trị rỗng theo quy ước ứng dụng.

### Thuộc tính có thể thay đổi theo thời gian

Ví dụ một nhân viên từng thuộc nhóm A rồi chuyển sang nhóm B. Nếu ghi đè một cạnh `MEMBER_OF` hiện tại, ta có thể mất lịch sử. Một cách mô tả là:

```text
(User U01)-[:MEMBER_OF {from: 2025-01-01, until: 2026-05-31}]->(Team A)
(User U01)-[:MEMBER_OF {from: 2026-06-01}]->(Team B)
```

Khi cần lịch sử và truy vấn theo thời điểm, hãy xác định ý nghĩa của `from`, `until`, khoảng thời gian đóng/mở, cách xử lý quan hệ trùng hoặc chồng khoảng. Trường trên cạnh rất hữu ích, nhưng việc giữ các bất biến thời gian vẫn là trách nhiệm thiết kế nghiệp vụ.

## 6. Định danh nút: tên hiển thị khác với danh tính

Hãy xét hai khách hàng:

```text
(Customer {customerId: "C001", name: "Mai"})
(Customer {customerId: "C002", name: "Mai"})
```

Hai nút có cùng tên `Mai` nhưng là **hai khách hàng khác nhau**. Ngược lại, khách C001 đổi tên hiển thị thì vẫn là C001. Vì vậy cần tách bạch:

- **Thuộc tính mô tả** như `name`, `title`, `city`: có thể trùng hoặc thay đổi.
- **Định danh nghiệp vụ** như `customerId`, `orderId`, `sku`: dùng để phân biệt phần tử theo hợp đồng của hệ thống.
- **Định danh nội bộ của database**: do Neo4j quản lý; không nên dựa vào nó để xác định ổn định thực thể trong API lâu dài.

### Chọn ID nghiệp vụ có ý nghĩa ổn định

Một ID tốt cần có phạm vi duy nhất rõ ràng và không bị sửa khi tên, mô tả, email hay các thuộc tính khác thay đổi. Ví dụ:

```text
Customer: customerId = "C001"
Order:    orderId    = "O1001"
Product:  sku        = "P10"
```

Nếu `sku` có thể đổi theo nhà cung cấp, nên cân nhắc dùng `productId` bất biến làm khóa chính nghiệp vụ, còn `sku` là thuộc tính có thể thay đổi. Không dùng địa chỉ email làm ID duy nhất nếu sản phẩm cho phép người dùng đổi email.

### ID phải có **phạm vi duy nhất**

Trong một ứng dụng nhiều tổ chức (multi-tenant), hai tenant có thể cùng có `orderId = "O1001"`. Có thể quy định ID là duy nhất toàn hệ thống, hoặc dùng khóa ghép:

```text
(tenantId, orderId)
("T1", "O1001") != ("T2", "O1001")
```

Khi truy vấn phải đi kèm tenant để tránh trộn dữ liệu:

```cypher
MATCH (o:Order {tenantId: 'T1', orderId: 'O1001'})
RETURN o;
```

Ngoài ràng buộc dữ liệu, ứng dụng vẫn phải thực thi phân quyền để người dùng tenant này không xem được tài nguyên của tenant khác.

## 7. ID nội bộ của Neo4j và lý do không nên dùng làm khóa API

Neo4j cấp cho phần tử đồ thị một định danh nội bộ. Cypher có hàm `elementId()` để lấy chuỗi ID phần tử, ví dụ:

```cypher
MATCH (c:Customer {customerId: 'C001'})
RETURN elementId(c) AS internalElementId, c.customerId AS businessId;
```

Hàm này hữu ích khi thao tác trong phạm vi cơ sở dữ liệu và truy vấn phù hợp, nhưng **giá trị ID nội bộ không phải hợp đồng định danh bất biến dài hạn cho ứng dụng**. Việc xóa/tạo lại phần tử, khôi phục/migration dữ liệu, thay đổi phạm vi database hay các quy tắc của phiên bản hệ quản trị có thể khiến giả định về ID nội bộ không còn đúng. Không lưu `elementId(c)` làm `customerId` của API, foreign key của hệ thống khác hoặc ID hiển thị công khai mà không có cơ chế quản lý riêng.

Thay vào đó:

```text
API: GET /customers/C001
                    |
                    v
MATCH (c:Customer {customerId: 'C001'})
RETURN c
```

Định danh nghiệp vụ là thứ hệ thống kiểm soát và có thể chuyển cùng dữ liệu qua môi trường khác. ID nội bộ là chi tiết của lớp lưu trữ. Hai loại ID có thể cùng tồn tại nhưng **phục vụ mục đích khác nhau**.

## 8. Ràng buộc duy nhất để ID nghiệp vụ có hiệu lực

Chỉ đặt thuộc tính `customerId` không tự động làm nó duy nhất. Nếu không có ràng buộc, hai lệnh tạo nút có thể ghi:

```cypher
CREATE (:Customer {customerId: 'C001'});
CREATE (:Customer {customerId: 'C001'});
```

Kết quả là **hai nút Customer khác nhau cùng mang `customerId = "C001"`**. Sau đó truy vấn theo ID có thể trả nhiều kết quả và gây mơ hồ.

Đối với Neo4j, có thể khai báo ràng buộc duy nhất trước khi ghi dữ liệu:

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;

CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE;
```

Trong ví dụ, các ràng buộc này bảo đảm không có hai nút cùng nhãn tương ứng có **cùng giá trị ID được khai báo**. Ràng buộc `IS UNIQUE` không tự bảo đảm mọi nút đều **có** thuộc tính đó; yêu cầu bắt buộc có trường cần được xác thực riêng hoặc dùng ràng buộc tồn tại/khóa phù hợp khi phiên bản và edition hỗ trợ.

Nếu ID chỉ duy nhất **trong tenant**, có thể dùng ràng buộc duy nhất ghép:

```cypher
CREATE CONSTRAINT tenant_order_unique IF NOT EXISTS
FOR (o:TenantOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
```

Đây là ví dụ riêng cho nút mang nhãn `TenantOrder`. Nếu áp dụng mô hình multi-tenant cho chính `:Order` của bài, hãy thay ràng buộc `order_id_unique` bằng ràng buộc ghép tương ứng và cập nhật tất cả truy vấn sử dụng cả `tenantId` lẫn `orderId`. Không nên đồng thời ràng buộc `orderId` duy nhất toàn hệ thống nếu nghiệp vụ cho phép hai tenant trùng mã.

### `CREATE` và `MERGE` có vai trò khác nhau

`CREATE` luôn tạo phần tử mới. `MERGE` tìm mẫu đã có hoặc tạo nếu chưa có:

```cypher
MERGE (c:Customer {customerId: 'C001'})
ON CREATE SET c.name = 'Mai'
RETURN c;
```

Trường `customerId` cần có quy tắc duy nhất rõ ràng. **`MERGE` không thay cho ràng buộc duy nhất** trong mọi tình huống ghi đồng thời: nếu nhiều request đến cùng lúc và không có constraint thích hợp, ứng dụng có nguy cơ tạo dữ liệu trùng. Cũng nên `MERGE` dựa trên ID ổn định, sau đó `SET` hoặc `ON CREATE SET` các thuộc tính có thể thay đổi, thay vì gộp cả tên và mô tả vào mẫu định danh.

## 9. Định danh cạnh: vì sao đây là phần dễ bị bỏ quên?

Trong graph, **cạnh cũng là một phần tử có danh tính riêng**, nhưng nghiệp vụ có thể hoặc không cần một khóa riêng cho nó.

Trường hợp đơn giản:

```text
(Customer C001)-[:PLACED]->(Order O1001)
```

Nếu mỗi đơn chỉ được đặt bởi một khách, quan hệ `PLACED` có thể được xác định theo cặp `(customerId, orderId)` cùng loại `PLACED`; không nhất thiết cần một `placementId` riêng cho API.

Ngược lại, một người có thể **mua nhiều lần cùng một sản phẩm**:

```text
(Customer C001)-[:PURCHASED {at: 2026-11-01, quantity: 1}]->(Product P10)
(Customer C001)-[:PURCHASED {at: 2026-11-12, quantity: 2}]->(Product P10)
```

Hai quan hệ có cùng nút đầu, nút cuối và loại `PURCHASED` nhưng đại diện **hai giao dịch khác nhau**. Nếu muốn hoàn tiền, truy vết hay sửa chính xác từng giao dịch, cần thêm định danh như `purchaseId`, hoặc tốt hơn là mô hình hóa giao dịch bằng một **nút `Order`/`Purchase` độc lập**.

### Cách chọn khóa logic cho quan hệ

Có thể quy ước một quan hệ bằng tổ hợp:

```text
(sourceBusinessId, relationshipType, targetBusinessId, qualifier)
```

Trong đó `qualifier` có thể là `lineId`, `eventId`, thời điểm hợp lệ hoặc một vai trò, nếu nhiều quan hệ cùng loại giữa hai nút được phép tồn tại.

Tuy nhiên, đây là **quy tắc của ứng dụng**, không có nghĩa graph database tự áp dụng tính duy nhất cho bộ giá trị này. Các hệ quản trị/edition/version có khả năng hỗ trợ ràng buộc relationship property khác nhau; cần xác định chính xác nơi thực thi ràng buộc hoặc kiểm soát qua mô hình nút giao dịch.

### Khi cạnh có vòng đời riêng, cân nhắc đổi thành nút

Giả sử một dòng hàng cần:

- `lineId` để sửa/hủy/hoàn tiền chính xác.
- Trạng thái chuẩn bị hàng riêng.
- Các sự kiện giao hàng hoặc hoàn tiền liên kết với **chính dòng hàng**.

Thay vì để mọi thông tin trên cạnh `CONTAINS`, có thể dùng nút `OrderLine`:

```text
(Order O1001)-[:HAS_LINE]->(OrderLine L001)-[:OF_PRODUCT]->(Product P10)
                                  |
                                  +-- quantity = 2
                                  +-- unitPriceAtPurchase = 150000
                                  +-- fulfillmentStatus = "PENDING"
```

Khi đó `lineId = "L001"` là khóa nghiệp vụ của một nút có vòng đời và quan hệ độc lập. Một điểm khởi đầu hợp lý là:

```cypher
CREATE CONSTRAINT order_line_id_unique IF NOT EXISTS
FOR (l:OrderLine)
REQUIRE l.lineId IS UNIQUE;
```

Việc chọn **cạnh có thuộc tính** hay **nút trung gian** dựa trên yêu cầu định danh, lịch sử, vòng đời và truy vấn. Không có lựa chọn cố định cho mọi nghiệp vụ.

## 10. Ví dụ Neo4j: tạo nút và quan hệ có định danh rõ ràng

Các lệnh trong mục này minh họa **một tập dữ liệu giả định trên database thử nghiệm trống**. Nếu thực hành trên database đã có sẵn nhiều nút trùng ID, hãy xử lý dữ liệu trùng trước khi tạo unique constraints. Những câu lệnh `MERGE` dưới đây dựa trên constraints của mục 8.

### 10.1. Tạo ba loại nút

```cypher
MERGE (c:Customer {customerId: 'C001'})
ON CREATE SET
  c.name = 'Mai',
  c.loyaltyTier = 'SILVER';

MERGE (o:Order {orderId: 'O1001'})
ON CREATE SET
  o.status = 'PAID',
  o.createdAt = datetime('2026-11-10T08:30:00Z');

MERGE (p1:Product {sku: 'P10'})
ON CREATE SET p1.name = 'Sách A';

MERGE (p2:Product {sku: 'P20'})
ON CREATE SET p2.name = 'Sách B';
```

Mỗi `MERGE` tìm theo nhãn và ID nghiệp vụ; `ON CREATE SET` chỉ gán thuộc tính khi nút được tạo mới. Nếu nghiệp vụ muốn đồng bộ tên sản phẩm khi nguồn dữ liệu đổi, phải xác định quy tắc cập nhật riêng bằng `SET`.

### 10.2. Tạo cạnh giữa những nút đã có

```cypher
MATCH (c:Customer {customerId: 'C001'})
MATCH (o:Order {orderId: 'O1001'})
MERGE (c)-[:PLACED]->(o);

MATCH (o:Order {orderId: 'O1001'})
MATCH (p:Product {sku: 'P10'})
MERGE (o)-[line:CONTAINS]->(p)
SET line.quantity = 2,
    line.unitPriceAtPurchase = 150000;

MATCH (o:Order {orderId: 'O1001'})
MATCH (p:Product {sku: 'P20'})
MERGE (o)-[line:CONTAINS]->(p)
SET line.quantity = 1,
    line.unitPriceAtPurchase = 220000;
```

Những lệnh này áp dụng quy ước **mỗi đơn có tối đa một cạnh `CONTAINS` cho mỗi sản phẩm**. Nếu một sản phẩm được chia thành nhiều dòng độc lập trong cùng đơn, cần dùng `lineId` hoặc nút `OrderLine` như mục 9.

`MERGE` trên mẫu cạnh nhằm tránh tạo thêm quan hệ cùng mẫu khi chạy nối tiếp thông thường; nó không tự chứng minh tính duy nhất ở tất cả tình huống ghi cạnh đồng thời. Với yêu cầu mạnh, cần ràng buộc/thiết kế giao dịch phù hợp.

### 10.3. Đọc danh sách sản phẩm của một đơn

```cypher
MATCH (o:Order {orderId: 'O1001'})-[line:CONTAINS]->(p:Product)
RETURN
  o.orderId AS orderId,
  p.sku AS sku,
  p.name AS productName,
  line.quantity AS quantity,
  line.unitPriceAtPurchase AS unitPriceAtPurchase,
  line.quantity * line.unitPriceAtPurchase AS lineTotal
ORDER BY sku;
```

Hai cạnh `CONTAINS` được trả theo sản phẩm; giá trị `quantity` nằm **trên từng cạnh**, không phải trên sản phẩm. Từ dữ liệu mẫu:

| orderId | sku | quantity | unitPriceAtPurchase | lineTotal |
|---|---|---:|---:|---:|
| O1001 | P10 | 2 | 150000 | 300000 |
| O1001 | P20 | 1 | 220000 | 220000 |

### 10.4. Duyệt hai loại cạnh từ khách hàng đến sản phẩm

```cypher
MATCH (c:Customer {customerId: 'C001'})
      -[:PLACED]->(o:Order)
      -[line:CONTAINS]->(p:Product)
RETURN
  c.customerId AS customerId,
  o.orderId AS orderId,
  p.sku AS sku,
  line.quantity AS quantity
ORDER BY orderId, sku;
```

Mẫu truy vấn chỉ rõ hai bước duyệt:

1. Từ khách `C001` qua cạnh `PLACED` để tìm đơn.
2. Từ mỗi đơn qua cạnh `CONTAINS` để tìm sản phẩm.

Điểm mạnh của graph model là cấu trúc đường đi thể hiện trực tiếp trong query.

### 10.5. Tổng số tiền của một đơn từ thuộc tính cạnh

```cypher
MATCH (o:Order {orderId: 'O1001'})-[line:CONTAINS]->(:Product)
RETURN o.orderId AS orderId,
       sum(line.quantity * line.unitPriceAtPurchase) AS totalVnd;
```

Kết quả dự kiến là `520000`. Nếu có giảm giá, phí vận chuyển, hoàn tiền hoặc thuế, công thức tổng tiền thực phải đưa thêm các quy tắc đó vào; phép cộng trên chỉ minh họa vai trò của **thuộc tính cạnh**.

## 11. Định danh giúp thao tác cập nhật chính xác

### Cập nhật nút qua ID nghiệp vụ

```cypher
MATCH (c:Customer {customerId: 'C001'})
SET c.name = 'Mai Nguyễn'
RETURN c.customerId, c.name;
```

Tên thay đổi, nhưng `customerId` vẫn là `C001`, nên các cạnh nối khách với đơn hàng **không phải tái tạo vì thay tên**.

### Cập nhật một cạnh qua hai đầu mút

```cypher
MATCH (o:Order {orderId: 'O1001'})
      -[line:CONTAINS]->
      (p:Product {sku: 'P10'})
SET line.quantity = 3
RETURN o.orderId, p.sku, line.quantity;
```

Điều kiện này xác định một quan hệ logic **nếu đúng theo quy ước có một cạnh `CONTAINS` giữa đơn và sản phẩm**. Nếu tồn tại nhiều cạnh cùng cặp đầu mút, `MATCH` có thể khớp nhiều cạnh và `SET` sẽ tác động lên nhiều quan hệ. Trong bài toán nhiều dòng cho cùng sản phẩm, hãy tìm bằng `lineId` hoặc chuyển sang nút `OrderLine`.

### Xóa phần tử có danh tính

Một nút có quan hệ gắn vào thường không thể bị xóa trực tiếp bằng `DELETE` mà không xử lý các quan hệ liên quan. Neo4j hỗ trợ `DETACH DELETE` để xóa nút và các cạnh liên đới; đây là hành động có hậu quả lớn và chỉ nên thực hiện khi nghiệp vụ cho phép xóa toàn bộ liên kết.

Ví dụ với khách hàng thật, xóa nút `Customer` có thể làm mất liên kết đến lịch sử đơn hàng. Nhiều hệ thống chọn vô hiệu hóa/ẩn danh thông tin hoặc chuyển quyền sở hữu theo chính sách, thay vì xóa tất cả liên kết. Cách xử lý phải dựa vào yêu cầu lưu trữ và tuân thủ dữ liệu.

## 12. Phân biệt “cạnh giữa hai nút” với “đường đi”

Một **cạnh** là một liên kết trực tiếp. **Đường đi (path)** là chuỗi nút và cạnh nối tiếp, có thể đi qua một hoặc nhiều bước (*hop*).

```text
Customer C001 --PLACED--> Order O1001 --CONTAINS--> Product P10
        \_____________________ 2 hops ___________________/
```

Ví dụ lấy đường đi dài hai bước:

```cypher
MATCH p = (:Customer {customerId: 'C001'})
          -[:PLACED]->(:Order)
          -[:CONTAINS]->(:Product)
RETURN p
LIMIT 10;
```

Đường đi không nhất thiết có ID nghiệp vụ riêng nếu chỉ là **kết quả tạm của một truy vấn duyệt**. Nó khác một entity như `Order`, vốn có thể được tạo, cập nhật và truy xuất độc lập.

Khi duyệt nhiều bước, số lượng nhánh có thể tăng rất mạnh. Một nút có 1.000 cạnh đi ra có thể tạo ra rất nhiều đường đi ở bước kế tiếp. Vì vậy, cần đặt giới hạn độ sâu, kiểu cạnh, điều kiện bắt đầu và số kết quả phù hợp; **có index tìm nút đầu không bảo đảm duyệt graph nhiều hop luôn rẻ**.

## 13. Labeled property graph và RDF có giống nhau không?

Các sản phẩm gọi chung là **graph database** nhưng có thể sử dụng mô hình khác nhau. Hai nhóm khái niệm hay gặp là:

| Khía cạnh | Labeled property graph (ví dụ Neo4j) | RDF graph |
|---|---|---|
| Thành phần chính | Nút và relationship có type | Bộ ba *subject–predicate–object* |
| Cách biểu diễn quan hệ | Cạnh nối hai nút, có thể mang properties | Predicate liên kết subject và object |
| Mô tả thực thể | Node labels và node properties | Các triple với IRI/literal; lớp/type tùy ontology |
| Thuộc tính trực tiếp trên cạnh | Là một phần tự nhiên của property graph | Thường cần kỹ thuật biểu diễn bổ sung cho metadata của statement |
| Truy vấn tiêu biểu | Cypher | SPARQL |

Ví dụ RDF ở mức khái niệm:

```text
<customer/C001>  <placed>  <order/O1001> .
<order/O1001>    <contains> <product/P10> .
```

Trong RDF, **IRI** là một dạng định danh quan trọng. Trong property graph, thường dùng các thuộc tính ID nghiệp vụ cộng ràng buộc duy nhất. Không nên chuyển trực tiếp mọi tính năng của Neo4j, như properties trên relationship, sang một RDF store mà không hiểu mô hình của nó.

## 14. Các nguyên tắc mô hình hóa nút, cạnh và ID

Khi chuyển yêu cầu từ nghiệp vụ sang đồ thị, hãy trả lời theo thứ tự:

**1. Đâu là các thực thể cần vòng đời riêng?** Chẳng hạn khách hàng, đơn hàng và sản phẩm là ba kiểu nút vì chúng có danh tính và liên kết độc lập.

**2. Mối quan hệ cần thể hiện động từ gì?** `PLACED`, `CONTAINS`, `FOLLOWS`, `MEMBER_OF` nên nói rõ ý nghĩa, tránh loại cạnh quá chung chung như `RELATED` nếu ứng dụng cần phân biệt nhiều nghiệp vụ.

**3. Chiều của quan hệ có ý nghĩa không?** `(User)-[:FOLLOWS]->(User)` có hướng, còn quan hệ bạn bè có thể được mô hình hóa theo quy tắc đối xứng rõ ràng.

**4. Thuộc tính mô tả ai hoặc điều gì?** Đặt tên khách trên nút Customer; đặt số lượng mua của một đơn trên cạnh CONTAINS hoặc OrderLine, không đặt lên Product.

**5. Phần tử được tìm bằng khóa nào?** Chọn ID nghiệp vụ ổn định, có phạm vi duy nhất xác định, đặt ràng buộc và truy vấn bằng ID ấy.

**6. Có nhiều cạnh cùng loại giữa cùng hai nút không?** Nếu có, cần quy tắc định danh mỗi lần tương tác. Khi quan hệ có vòng đời riêng, cân nhắc một nút trung gian.

**7. Truy vấn thực tế bắt đầu ở đâu và đi bao xa?** Nút bắt đầu thường cần được tìm nhanh qua nhãn + thuộc tính ID; giới hạn fan-out và số hop để kiểm soát chi phí.

### Cách đặt tên dễ đọc

| Thành phần | Ví dụ | Gợi ý |
|---|---|---|
| Node label | `Customer`, `Order`, `Product` | Danh từ chỉ thực thể, nhất quán cách viết |
| Relationship type | `PLACED`, `CONTAINS`, `FOLLOWS` | Động từ hoặc cụm từ có nghĩa rõ |
| Business key | `customerId`, `orderId`, `productId` | Tên thể hiện phạm vi và danh tính |
| Property | `name`, `status`, `createdAt` | Thể hiện ý nghĩa và kiểu dữ liệu |
| Relationship property | `quantity`, `since`, `unitPriceAtPurchase` | Mô tả chính tương tác/liên kết |

Với graph multi-tenant, các khóa và truy vấn cần xét cả `tenantId`. Với hệ thống có bản ghi lịch sử, phải xác định rõ ID của **thực thể** khác ID của **phiên bản**, **sự kiện** hoặc **một lần quan hệ**.

## 15. Những lỗi thiết kế dễ gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Dùng `name` làm khóa tìm khách | Hai người trùng tên, đổi tên gây mất liên kết logic | Dùng `customerId` ổn định |
| Xem `:Customer` là định danh nút | Nhiều nút cùng label vẫn phân biệt nhau | Dùng business key và unique constraint |
| Dùng ID nội bộ trong API bên ngoài | Khó duy trì qua migration, xóa/tạo lại, thay đổi môi trường | Expose business ID do ứng dụng quản lý |
| Chỉ viết `MERGE` mà không có ràng buộc duy nhất | Có nguy cơ tạo bản ghi trùng khi ghi đồng thời | Tạo constraint theo ID và thiết kế transaction phù hợp |
| Đặt `quantity` của đơn lên nút Product | Sản phẩm tham gia nhiều đơn khác nhau | Đưa lên cạnh CONTAINS hoặc nút OrderLine |
| Coi `FOLLOWS` là quan hệ hai chiều | Sai ý nghĩa theo dõi | Biểu diễn rõ chiều và quy tắc quan hệ |
| Dùng cặp hai đầu mút để sửa cạnh khi tồn tại nhiều cạnh song song | Có thể sửa/xóa nhầm nhiều lần giao dịch | Thêm định danh quan hệ hoặc nút giao dịch |
| Biến mọi giá trị nhỏ thành nút | Graph rối, truy vấn tốn nhiều hop | Giữ giá trị mô tả thành property |
| Nhồi object lồng nhau tùy ý vào một property | Không phù hợp các kiểu property được hỗ trợ | Dùng property đơn giản hoặc các nút con |
| Duyệt từ nút không có khóa lọc hoặc không giới hạn độ sâu | Chi phí duyệt lớn, kết quả nở nhanh | Bắt đầu bằng ID/index, giới hạn kiểu cạnh và số hop |

## 16. Bài tập ứng dụng

### Bài 1: Phân loại nút, cạnh và thuộc tính

Một hệ thống học tập có **học viên**, **khóa học**, **giảng viên**. Học viên đăng ký khóa với ngày đăng ký và tiến độ; giảng viên phụ trách khóa.

Hãy phân loại:

- `Student`, `Course`, `Instructor`.
- `ENROLLED_IN`, `TEACHES`.
- `studentId`, `courseId`, `instructorId`.
- `enrolledAt`, `progressPercent`.

Gợi ý: ba danh từ là các loại nút; hai động từ là loại cạnh. `studentId`/`courseId`/`instructorId` là ID nghiệp vụ của nút. `enrolledAt` và `progressPercent` gắn với **một lần đăng ký**; nếu mỗi học viên chỉ có một lần đăng ký cho mỗi khóa, chúng có thể nằm trên cạnh `ENROLLED_IN`. Nếu người học có thể đăng ký lại nhiều lần, cần ID của lần đăng ký hoặc nút `Enrollment`.

### Bài 2: Tại sao hai người cùng tên vẫn là hai nút?

Giả sử:

```text
(:Student {studentId: "S01", name: "An"})
(:Student {studentId: "S02", name: "An"})
```

Hãy giải thích vì sao không thể `MERGE` học viên theo `name`. Đề xuất constraint và câu truy vấn tìm đúng S02.

Một cách thực hiện:

```cypher
CREATE CONSTRAINT student_id_unique IF NOT EXISTS
FOR (s:Student)
REQUIRE s.studentId IS UNIQUE;

MATCH (s:Student {studentId: 'S02'})
RETURN s.name, s.studentId;
```

### Bài 3: Nhiều cạnh cùng hai nút

Một học viên đăng ký khóa C01 vào tháng 3, hủy, rồi đăng ký lại vào tháng 7. Nếu lưu hai cạnh `ENROLLED_IN` cùng giữa Student S01 và Course C01, cách nào nhận diện chính xác lần đăng ký để hoàn phí hoặc ghi chứng nhận?

Gợi ý: tạo `enrollmentId` cho từng lần đăng ký, hoặc mô hình hóa:

```text
(Student S01)-[:HAS_ENROLLMENT]->(Enrollment E001)-[:FOR_COURSE]->(Course C01)
(Student S01)-[:HAS_ENROLLMENT]->(Enrollment E002)-[:FOR_COURSE]->(Course C01)
```

Khi mỗi lần đăng ký có vòng đời, trạng thái và các quan hệ riêng, nút `Enrollment` thường giúp thiết kế dễ quản lý hơn.

### Bài 4: Truy vấn hai bước trên đồ thị đơn hàng

Dựa vào dữ liệu phần 10, hãy viết truy vấn lấy tất cả sản phẩm đã mua của `C001` và tổng số lượng theo SKU. Một ví dụ:

```cypher
MATCH (:Customer {customerId: 'C001'})-[:PLACED]->(:Order)
      -[line:CONTAINS]->(p:Product)
RETURN p.sku AS sku, sum(line.quantity) AS totalQuantity
ORDER BY sku;
```

Nếu chính sách báo cáo chỉ tính đơn đã thanh toán, cần bổ sung điều kiện trên nút Order, chẳng hạn `(o:Order)` và `WHERE o.status = 'PAID'`.

## 17. Kết luận

Mô hình đồ thị được xây từ các **nút mang danh tính**, **cạnh diễn đạt quan hệ**, và **thuộc tính mô tả cả thực thể lẫn tương tác**. Nút `Customer` và `Product` có thể có tên/giá trị trùng nhau mà vẫn là các thực thể khác nhau; cạnh `CONTAINS` chứa số lượng mua và giá tại thời điểm giao dịch vì những giá trị ấy thuộc về quan hệ đơn hàng–sản phẩm.

Điểm then chốt khi thiết kế là phân biệt **định danh nghiệp vụ ổn định** với nhãn, tên hiển thị và ID nội bộ của hệ quản trị. Cần xác định phạm vi duy nhất, khai báo ràng buộc khi có thể, xem xét các cạnh song song và dùng nút trung gian cho những quan hệ cần vòng đời hoặc ID riêng.

Khi hiểu rõ bốn thành phần **node – relationship – property – identifier**, ta có thể thiết kế graph phản ánh ngữ nghĩa nghiệp vụ và viết truy vấn duyệt quan hệ chính xác, tránh nhập nhằng giữa một thực thể, một lần tương tác và một đường đi tạm thời.
