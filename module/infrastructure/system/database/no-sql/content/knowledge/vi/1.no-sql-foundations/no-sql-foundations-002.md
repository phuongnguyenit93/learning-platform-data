# Phân biệt ngôn ngữ SQL, mô hình quan hệ và hệ quản trị dữ liệu cụ thể

Khi mới tìm hiểu NoSQL, chúng ta thường nghe những câu như “SQL là cơ sở dữ liệu quan hệ”, “PostgreSQL là SQL”, hoặc “MongoDB không có quan hệ”. Các cách nói này dễ hiểu trong hội thoại, nhưng trộn lẫn **ba khái niệm ở ba tầng khác nhau**:

1. **Mô hình dữ liệu** quy định cách biểu diễn dữ liệu, quan hệ giữa các phần dữ liệu và các ràng buộc có ý nghĩa.
2. **Ngôn ngữ truy vấn/thao tác** quy định cách người dùng hoặc chương trình diễn đạt yêu cầu đối với dữ liệu.
3. **Hệ quản trị cơ sở dữ liệu (DBMS)** là phần mềm thực sự lưu trữ, truy xuất, bảo vệ và vận hành dữ liệu.

Phân biệt được ba tầng này là nền tảng để hiểu chính xác “NoSQL” khác gì với hệ cơ sở dữ liệu quan hệ, cũng như để chọn công nghệ theo nhu cầu thay vì theo tên gọi.

## 1. Bức tranh tổng quan: ba câu hỏi khác nhau

| Tầng | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Mô hình dữ liệu** (*data model*) | Dữ liệu được tổ chức và ràng buộc về mặt logic như thế nào? | Mô hình quan hệ, mô hình tài liệu, khóa–giá trị, đồ thị |
| **Ngôn ngữ hoặc API truy cập dữ liệu** | Diễn đạt lệnh tạo, đọc, cập nhật, xóa và truy vấn dữ liệu như thế nào? | SQL, MongoDB Query Language (MQL), Cypher, Redis commands, Cassandra Query Language (CQL) |
| **Hệ quản trị dữ liệu** (*database management system*, DBMS) | Phần mềm nào nhận yêu cầu, quản lý lưu trữ, thực thi truy vấn và cung cấp những bảo đảm cần thiết? | PostgreSQL, MySQL, Microsoft SQL Server, MongoDB, Redis, Neo4j, Apache Cassandra |

Có thể hình dung một lần truy vấn theo chuỗi sau:

```text
Ứng dụng cần tìm đơn hàng của khách hàng 1
                │
                ▼
Ngôn ngữ/API: diễn đạt yêu cầu bằng SELECT, find(), ...
                │
                ▼
DBMS: phân tích yêu cầu, lập kế hoạch, truy cập dữ liệu,
      sử dụng chỉ mục, kiểm soát quyền và trả về kết quả
                │
                ▼
Dữ liệu được hiểu theo mô hình đã chọn:
bảng và khóa / tài liệu / đồ thị / khóa–giá trị / ...
```

Đây là sơ đồ giải thích các vai trò, không phải ranh giới cứng: một DBMS có thể hỗ trợ nhiều kiểu dữ liệu, nhiều giao diện truy cập và một phần đặc tính của nhiều mô hình.

**Ví dụ ngắn:** Trong hệ thống dùng PostgreSQL, **mô hình quan hệ** giúp ta thiết kế bảng `customers` và `orders` cùng ràng buộc khóa ngoại; **SQL** cho phép viết câu `SELECT ... JOIN ...`; **PostgreSQL** nhận câu lệnh đó, lập kế hoạch thực thi, đọc dữ liệu và trả kết quả. Ba tên gọi chỉ ba khía cạnh của cùng một hệ thống.

## 2. Mô hình quan hệ là gì?

**Mô hình quan hệ** (*relational model*) là cách mô tả dữ liệu ở cấp logic. Theo cách nhìn lý thuyết, một *quan hệ* (*relation*) là tập các bộ giá trị (*tuples*) có những thuộc tính (*attributes*) xác định. Trong thực hành với RDBMS, ta thường tiếp cận qua **bảng, cột và hàng**.

Giả sử một ứng dụng bán hàng quản lý khách hàng và đơn hàng:

**`customers`**

| customer_id | full_name |
| --- | --- |
| 1 | An |
| 2 | Bình |

**`orders`**

| order_id | customer_id | total_amount |
| --- | --- | --- |
| 101 | 1 | 350000 |
| 102 | 1 | 120000 |

Thiết kế này có những ý nghĩa logic:

- Mỗi bản ghi trong `customers` biểu diễn một khách hàng; `customer_id` xác định duy nhất khách hàng đó.
- Mỗi bản ghi trong `orders` biểu diễn một đơn hàng; `order_id` xác định duy nhất đơn hàng.
- `orders.customer_id` tham chiếu `customers.customer_id`, thể hiện mỗi đơn hàng thuộc về một khách hàng đã tồn tại nếu ràng buộc khóa ngoại được khai báo và thực thi.
- Tổng tiền có thể được ràng buộc không âm. Những quy tắc này phản ánh ý nghĩa nghiệp vụ, không phụ thuộc vào cách câu truy vấn được viết.

Những khái niệm cốt lõi cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Quan hệ (*relation*) | Tập các bộ dữ liệu có chung tập thuộc tính trong mô hình lý thuyết; trong RDBMS thường được biểu diễn bằng bảng. |
| Thuộc tính (*attribute*) | Trường thông tin của quan hệ; thường được thể hiện bằng cột. |
| Bộ (*tuple*) | Một phần tử dữ liệu của quan hệ; thường được thể hiện bằng hàng. |
| Miền giá trị (*domain*) | Tập giá trị hợp lệ của thuộc tính, chẳng hạn số nguyên hoặc giá trị tiền không âm khi có ràng buộc thích hợp. |
| Khóa chính / khóa ứng viên | Cách định danh duy nhất một bộ dữ liệu theo các thuộc tính được chọn. |
| Khóa ngoại | Ràng buộc tham chiếu đến khóa ở một quan hệ khác hoặc cùng quan hệ, nếu thiết kế sử dụng ràng buộc này. |

Trong lý thuyết quan hệ, thao tác trên dữ liệu có nền tảng từ **đại số quan hệ** như chọn (*selection*), chiếu (*projection*), kết (*join*) và hợp (*union*). Mô hình mô tả dữ liệu và phép toán ở cấp logic; nó không yêu cầu tất cả các hệ triển khai phải dùng cùng một cú pháp truy vấn hay cùng một cách lưu trên đĩa.

### Phân biệt “quan hệ” và “liên kết giữa hai bảng”

Từ *relation* trong **mô hình quan hệ** mang nghĩa toán học là quan hệ gồm các bộ giá trị. Trong thiết kế ứng dụng, ta cũng nói “quan hệ một–nhiều giữa khách hàng và đơn hàng”, nghĩa là **mối liên hệ giữa các thực thể**, thường được biểu diễn bằng khóa ngoại. Hai cách dùng từ gần nhau, nhưng không đồng nhất.

Đặc biệt, **không phải cứ có liên kết giữa các đối tượng là dữ liệu thuộc mô hình quan hệ**: cơ sở dữ liệu đồ thị cũng lưu liên kết, và cơ sở dữ liệu tài liệu cũng có thể tham chiếu tài liệu khác. Điểm phân biệt nằm ở mô hình tổ chức, ngữ nghĩa và ràng buộc của dữ liệu.

### Mô hình logic khác cách lưu trữ vật lý

Một bảng logic không nhất thiết được ghi thành một “bảng” liên tục trên đĩa. DBMS có thể sử dụng trang dữ liệu, bộ đệm, cây B-tree, chỉ mục khác hoặc nhiều chiến lược lưu trữ. Đó là **chi tiết triển khai**, không phải định nghĩa của mô hình quan hệ.

Tương tự, việc chuẩn hóa dữ liệu (*normalization*) là một kỹ thuật thiết kế hữu ích trong môi trường quan hệ, nhưng không phải mọi hệ quan hệ đều bắt buộc lưu mọi dữ liệu ở dạng chuẩn hóa tối đa. Từng hệ thống có thể chọn chuẩn hóa hoặc phi chuẩn hóa phù hợp với yêu cầu truy vấn và cập nhật.

## 3. SQL là gì, và SQL không phải là gì?

**SQL (*Structured Query Language*) là ngôn ngữ dùng để định nghĩa và làm việc với dữ liệu**, được tiêu chuẩn hóa và được nhiều DBMS hỗ trợ. Lệnh SQL thường diễn đạt **cần kết quả gì**; DBMS lựa chọn cách thực hiện bằng bộ tối ưu hóa và cơ chế thực thi của mình.

Một số nhóm thao tác thông dụng:

| Nhóm thao tác | Ví dụ SQL | Mục đích |
| --- | --- | --- |
| Định nghĩa cấu trúc | `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` | Tạo hoặc thay đổi đối tượng dữ liệu. |
| Đọc và thao tác dữ liệu | `SELECT`, `INSERT`, `UPDATE`, `DELETE` | Truy vấn hoặc thay đổi bản ghi. |
| Kiểm soát giao dịch | `BEGIN`, `COMMIT`, `ROLLBACK` | Nhóm thao tác thành giao dịch và quyết định xác nhận/hủy bỏ. |
| Phân quyền | `GRANT`, `REVOKE` | Quản lý quyền sử dụng các đối tượng trong DBMS hỗ trợ cú pháp tương ứng. |

Ví dụ một câu SQL:

```sql
SELECT c.full_name, o.order_id, o.total_amount
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.customer_id
WHERE c.customer_id = 1;
```

Người viết yêu cầu lấy tên khách hàng và các đơn hàng của khách hàng mang mã `1`. **SQL diễn đạt yêu cầu**; bản thân đoạn văn bản SQL không lưu dữ liệu, không cấp phát bộ nhớ, không quản lý tệp và không quyết định một cách cố định phải dùng chỉ mục nào.

### SQL và mô hình quan hệ có liên hệ, nhưng không đồng nhất

SQL phát triển mạnh cùng các hệ cơ sở dữ liệu quan hệ và có nhiều phép toán tương ứng đại số quan hệ. Tuy nhiên, SQL trong thực tế **không phải bản sao chính xác của mô hình quan hệ thuần túy**:

- Quan hệ trong mô hình toán học là **tập** các bộ giá trị, trong khi kết quả SQL thông thường có thể chứa **hàng trùng lặp**; `DISTINCT` giúp loại trùng khi cần.
- SQL thường có **`NULL`** cho dữ liệu không có giá trị/không biết, kéo theo logic điều kiện ba giá trị trong nhiều biểu thức; đây là khác biệt với cách trình bày quan hệ toán học cơ bản.
- SQL bao gồm nhiều đặc tính thực dụng như thủ tục, JSON, kiểu dữ liệu mở rộng và các hàm riêng của DBMS. Các đặc tính này không đồng nghĩa với yêu cầu cốt lõi của mô hình quan hệ.

Do đó, nói “SQL = mô hình quan hệ” là thiếu chính xác. Một hệ có thể dùng mô hình quan hệ và cung cấp một ngôn ngữ truy vấn khác SQL; ngược lại, một hệ không thuần quan hệ vẫn có thể cung cấp giao diện SQL hoặc cú pháp tương tự SQL.

### Chuẩn SQL và phương ngữ SQL

SQL có tiêu chuẩn chung, nhưng từng DBMS triển khai những phần khác nhau và bổ sung **phương ngữ** (*dialect*) riêng. Ví dụ PostgreSQL có `ON CONFLICT` để xử lý xung đột khi chèn, trong khi MySQL có cú pháp `ON DUPLICATE KEY UPDATE` cho bài toán gần tương tự.

Vì vậy, “hai hệ cùng hỗ trợ SQL” **không có nghĩa** mọi câu SQL sẽ chạy y hệt trên cả hai. Khác biệt còn xuất hiện ở kiểu dữ liệu, hàm, cách xử lý giao dịch, tối ưu hóa và những tính năng đặc thù. Khi đánh giá tính di động của ứng dụng, phải xét cả SQL cụ thể đang sử dụng và các hành vi DBMS mà ứng dụng phụ thuộc.

## 4. DBMS là gì? RDBMS là một loại DBMS

**DBMS (*Database Management System*) là phần mềm quản lý cơ sở dữ liệu.** Phần mềm này cung cấp những năng lực như nhận lệnh và API, quản lý dữ liệu trên bộ nhớ hoặc đĩa, thực thi truy vấn, điều khiển truy cập, phục hồi sau lỗi, đồng thời cung cấp mức độ giao dịch, sao lưu hoặc phân tán tùy sản phẩm.

Một **RDBMS (*Relational Database Management System*)** là DBMS có nền tảng quản lý dữ liệu theo mô hình quan hệ. Các ví dụ quen thuộc gồm PostgreSQL, MySQL, MariaDB, Microsoft SQL Server, Oracle Database và SQLite. Các sản phẩm này có nhiều điểm chung ở khả năng truy vấn SQL, nhưng không phải cùng một phần mềm hay cùng một bộ tính năng.

Ví dụ về điều **DBMS** quyết định hoặc triển khai, bên cạnh mô hình dữ liệu và cú pháp truy vấn:

- Cách tổ chức tệp, trang dữ liệu, bộ đệm và chỉ mục.
- Cách lập kế hoạch để thực thi `JOIN`, lọc dữ liệu hoặc sắp xếp.
- Cơ chế đồng thời, giao dịch, khôi phục dữ liệu và xử lý sự cố.
- Hệ thống phân quyền, sao lưu, nhân bản và khả năng mở rộng theo cấu hình hoặc kiến trúc sản phẩm.
- Các kiểu dữ liệu, hàm, tiện ích quản trị và giới hạn riêng.

**PostgreSQL là tên DBMS**, **SQL là ngôn ngữ mà PostgreSQL hỗ trợ**, còn **mô hình quan hệ là một mô hình dùng để thiết kế dữ liệu mà PostgreSQL quản lý**. PostgreSQL cũng hỗ trợ kiểu dữ liệu `jsonb`, cho thấy một DBMS quan hệ hiện đại có thể phục vụ cả tình huống lưu cấu trúc tài liệu mà không vì thế đổi tên thành “NoSQL DBMS”.

Một điểm dễ nhầm khác: **Microsoft SQL Server** có chữ “SQL” trong tên sản phẩm, nhưng cả cụm đó chỉ một hệ quản trị cụ thể; nó không đồng nghĩa với bản thân ngôn ngữ SQL.

## 5. Ví dụ trọn vẹn: cùng bài toán, ba tầng vai trò

Giả sử yêu cầu nghiệp vụ là: “Lưu khách hàng và đơn hàng; tra cứu toàn bộ đơn hàng của khách hàng có mã `1`.”

### 5.1. Thiết kế theo mô hình quan hệ

Ta chọn biểu diễn khách hàng và đơn hàng thành hai quan hệ logic, xác định khóa chính và khóa ngoại. Trong một DBMS như PostgreSQL, có thể tạo dữ liệu bằng SQL:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    total_amount DECIMAL(12, 2) NOT NULL CHECK (total_amount >= 0)
);

INSERT INTO customers (customer_id, full_name)
VALUES (1, 'An'), (2, 'Bình');

INSERT INTO orders (order_id, customer_id, total_amount)
VALUES (101, 1, 350000), (102, 1, 120000);
```

Trong đoạn này:

- **Mô hình quan hệ** định hướng cách chia dữ liệu thành `customers` và `orders`, mỗi bảng mang một loại thông tin và liên kết bằng `customer_id`.
- **SQL** cung cấp các câu `CREATE TABLE` và `INSERT` để thể hiện cấu trúc, ràng buộc và dữ liệu cần ghi.
- **PostgreSQL** (nếu được chọn để chạy ví dụ) thực thi câu lệnh, lưu bản ghi và kiểm tra khóa chính, khóa ngoại, `NOT NULL`, `CHECK`.

Để truy xuất:

```sql
SELECT c.full_name, o.order_id, o.total_amount
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.customer_id
WHERE c.customer_id = 1
ORDER BY o.order_id;
```

Kết quả mong đợi từ dữ liệu ví dụ:

| full_name | order_id | total_amount |
| --- | --- | --- |
| An | 101 | 350000.00 |
| An | 102 | 120000.00 |

`JOIN` được viết bằng SQL để kết hợp thông tin của hai bảng theo điều kiện, còn DBMS chọn chiến lược thực thi cụ thể. Việc khóa ngoại có được thực thi và câu truy vấn chạy được phụ thuộc vào khả năng cùng cấu hình DBMS, không phải chỉ vào cách đặt tên bảng.

### 5.2. Thiết kế theo mô hình tài liệu trong MongoDB

Cùng nghiệp vụ, một phương án trong MongoDB là lưu mỗi đơn hàng dưới dạng **tài liệu**, kèm phần thông tin khách hàng cần cho màn hình đọc đơn hàng:

```javascript
db.orders.insertMany([
  {
    _id: 101,
    customer: { id: 1, fullName: "An" },
    totalAmount: 350000
  },
  {
    _id: 102,
    customer: { id: 1, fullName: "An" },
    totalAmount: 120000
  }
]);

db.orders.find(
  { "customer.id": 1 },
  { _id: 1, "customer.fullName": 1, totalAmount: 1 }
);
```

Đây là ví dụ dùng **MongoDB Query API/MQL**, không phải SQL. Tại ba tầng:

- **Mô hình tài liệu** cho phép mỗi đơn hàng chứa đối tượng `customer` lồng bên trong tài liệu đơn hàng; các tài liệu thuộc collection `orders`.
- **API truy vấn MongoDB** dùng `insertMany()` và `find()` để ghi và đọc tài liệu, với cú pháp phù hợp mô hình này.
- **MongoDB** là phần mềm DBMS thực hiện lưu trữ, tìm kiếm, lập chỉ mục và các chức năng quản trị tương ứng.

Đặt cạnh mô hình quan hệ, ví dụ tài liệu này **lặp lại tên khách hàng** ở nhiều đơn hàng. Đổi tên khách hàng có thể cần cập nhật nhiều tài liệu nếu ứng dụng muốn các bản sao luôn mới. Đây là **đánh đổi của phương án nhúng thông tin**, không phải đặc điểm bắt buộc của mọi mô hình NoSQL: MongoDB cũng cho phép lưu tham chiếu đến tài liệu khác và hỗ trợ các thao tác tổng hợp như `$lookup`.

Hai đoạn code minh họa **hai cách thiết kế dữ liệu và hai giao diện truy cập** cho cùng mục tiêu nghiệp vụ. Chúng không chứng minh cách nào mặc định nhanh hơn, tốt hơn hay dễ mở rộng hơn; để đánh giá phải xét lượng dữ liệu, mẫu truy vấn, mô hình cập nhật, chỉ mục, yêu cầu nhất quán và cấu hình hệ thống thực tế.

## 6. Đặt NoSQL đúng tầng khái niệm

**NoSQL** là tên gọi chung cho nhiều nhóm hệ quản trị và mô hình dữ liệu **không lấy mô hình bảng quan hệ truyền thống làm cách tổ chức trung tâm**. Trong cách diễn giải phổ biến, NoSQL có thể hiểu là *Not Only SQL*: việc truy cập dữ liệu không bị giới hạn ở SQL. Nó không phải tên một ngôn ngữ truy vấn thống nhất, cũng không chỉ một sản phẩm cụ thể.

Một số nhóm thường gặp:

| Nhóm mô hình/DBMS | Ví dụ DBMS | Cách biểu diễn và truy cập nổi bật |
| --- | --- | --- |
| **Tài liệu (document)** | MongoDB | Tài liệu BSON/JSON-like, có thể lồng đối tượng và mảng; truy vấn bằng API/MQL, aggregation pipeline. |
| **Khóa–giá trị (key–value)** | Redis | Truy cập theo khóa, lưu nhiều kiểu cấu trúc dữ liệu; dùng lệnh/API của Redis. |
| **Wide-column** | Apache Cassandra | Bảng theo thiết kế phục vụ truy vấn với partition key và clustering columns; dùng **CQL** có cú pháp giống SQL ở nhiều chỗ nhưng khác ngữ nghĩa và khả năng truy vấn. |
| **Đồ thị (graph)** | Neo4j | Node, relationship và property; thường truy vấn bằng Cypher để duyệt mẫu liên kết. |

Điểm cần chú ý là **cách gọi tên của từng tầng vẫn giữ nguyên**. “MongoDB” là tên DBMS; “document” là mô hình dữ liệu chủ đạo; “MQL” là cách truy vấn. “Cassandra” là tên DBMS; “wide-column” mô tả họ mô hình; “CQL” là ngôn ngữ truy cập có cú pháp gần SQL. Có câu `SELECT` trong CQL không khiến Cassandra trở thành RDBMS với ngữ nghĩa `JOIN` và ràng buộc như PostgreSQL.

Ngược lại, một DBMS quan hệ như PostgreSQL có thể lưu và truy vấn JSON. Vì thế, chỉ nhìn thấy JSON chưa đủ để kết luận đó là “NoSQL”, và chỉ nhìn thấy cú pháp `SELECT` chưa đủ để kết luận dữ liệu đang tuân theo mô hình quan hệ.

### Không đánh đồng NoSQL với những đặc tính khác

Các nhận định sau thường quá tuyệt đối:

- **“NoSQL là không có schema.”** Nhiều hệ tài liệu cho phép cấu trúc linh hoạt, nhưng ứng dụng vẫn cần quy ước và kiểm tra schema; một số DBMS còn hỗ trợ xác thực cấu trúc. “Linh hoạt schema” không đồng nghĩa với “không có quy tắc dữ liệu”.
- **“NoSQL không hỗ trợ giao dịch.”** Hỗ trợ giao dịch và phạm vi bảo đảm phụ thuộc DBMS, phiên bản, loại thao tác và cấu hình. Một số hệ NoSQL cung cấp giao dịch ACID trong phạm vi nhất định, thậm chí trên nhiều tài liệu.
- **“NoSQL không có liên kết hoặc không thể join.”** Dữ liệu có thể chứa tham chiếu, liên kết đồ thị hoặc phép kết hợp; tính năng và chi phí của việc kết hợp phụ thuộc hệ thống. Chẳng hạn MongoDB có `$lookup`, nhưng thiết kế và đặc tính khác một phép `JOIN` trên RDBMS.
- **“RDBMS không mở rộng ngang còn NoSQL luôn mở rộng ngang.”** Khả năng phân vùng, nhân bản, phân tán và mở rộng phụ thuộc kiến trúc sản phẩm cùng cách triển khai; không thể kết luận chỉ từ nhãn SQL/NoSQL.
- **“NoSQL nhanh hơn SQL.”** Tốc độ phụ thuộc truy vấn, dữ liệu, chỉ mục, mô hình thiết kế, phần cứng, mức độ phân tán và yêu cầu nhất quán. SQL là ngôn ngữ nên bản thân nó không phải đối tượng so hiệu năng trực tiếp với một DBMS.

Khi so sánh công nghệ, hãy chọn **cùng một tầng so sánh**: PostgreSQL với MongoDB là so hai DBMS; mô hình quan hệ với mô hình tài liệu là so hai mô hình; SQL với MQL là so cách diễn đạt và khả năng truy vấn.

## 7. Cách nhận diện một phát biểu đang nói đến tầng nào

| Phát biểu | Đang nói chủ yếu về | Giải thích |
| --- | --- | --- |
| “Dùng `SELECT`, `WHERE`, `JOIN` để lấy dữ liệu.” | **Ngôn ngữ** | Đây là cấu trúc câu SQL hoặc cú pháp tương ứng. |
| “Mỗi đơn hàng có khóa ngoại tham chiếu khách hàng.” | **Mô hình và thiết kế logic** | Đây là cách tổ chức dữ liệu cùng ràng buộc tham chiếu. |
| “Chúng ta chạy PostgreSQL 16 trên máy chủ.” | **DBMS và triển khai** | Nêu sản phẩm/phần mềm và phiên bản. |
| “Cần chỉ mục để cải thiện truy vấn tìm theo mã khách hàng.” | **Thiết kế truy cập và triển khai** | Chỉ mục là cơ chế được DBMS hiện thực để hỗ trợ truy cập nhanh; nhiều mô hình đều có thể dùng. |
| “Tài liệu đơn hàng chứa mảng sản phẩm.” | **Mô hình tài liệu** | Mô tả cấu trúc dữ liệu, chưa nói phần mềm nào lưu nó. |
| “Dùng `db.orders.find()`.” | **API truy vấn** | Cú pháp quen thuộc của MongoDB để truy vấn collection. |
| “Ứng dụng dùng SQL Server.” | **DBMS** | SQL Server là tên một hệ quản trị cụ thể, dù chứa từ “SQL”. |

Một số cách viết chính xác hơn trong tài liệu kỹ thuật:

- Thay “**SQL lưu dữ liệu**” bằng “**DBMS lưu dữ liệu; ứng dụng dùng SQL để thao tác với dữ liệu**”.
- Thay “**SQL có quan hệ một–nhiều**” bằng “**mô hình dữ liệu quan hệ biểu diễn mối liên hệ một–nhiều; khóa ngoại là một cách thực thi ràng buộc đó trong RDBMS**”.
- Thay “**MongoDB là ngôn ngữ NoSQL**” bằng “**MongoDB là DBMS thiên về tài liệu, cung cấp ngôn ngữ/API truy vấn cho tài liệu**”.
- Thay “**SQL hay NoSQL nhanh hơn?**” bằng “**PostgreSQL hay MongoDB phù hợp hơn với mẫu dữ liệu, truy vấn và yêu cầu vận hành cụ thể này?**”.

## 8. Ứng dụng cách phân biệt khi thiết kế hệ thống

Khi bắt đầu một bài toán lưu trữ, có thể lần lượt xem xét ba tầng để tránh chọn công nghệ trước khi hiểu nhu cầu:

**Bước 1 — Xác định cấu trúc logic và bất biến nghiệp vụ.** Dữ liệu có những thực thể nào? Quan hệ và ràng buộc nào phải được bảo vệ? Dữ liệu thường được đọc theo bản ghi đơn lẻ, theo tài liệu tổng hợp, theo đường liên kết nhiều bước hay theo partition? Cần cập nhật đồng thời những phần nào?

**Bước 2 — Xem khả năng truy vấn và cách dùng từ ứng dụng.** Cần lọc, kết nối, tổng hợp, sắp xếp, truy vấn ad hoc hay truy xuất theo khóa? Nhóm phát triển đã có kiến thức SQL/CQL/Cypher/MQL nào? Mức độ ổn định của API và tính di động của câu truy vấn quan trọng đến đâu?

**Bước 3 — Chọn và đánh giá DBMS cụ thể.** So sánh tính năng, bảo đảm giao dịch, cơ chế nhất quán, chỉ mục, khả năng phân tán, sao lưu, độ trưởng thành công cụ, chi phí và khả năng vận hành. Sau đó kiểm thử trên khối lượng dữ liệu và mẫu truy vấn gần với thực tế.

Ví dụ, hệ thống đơn hàng cần khóa ngoại và thao tác nhất quán xuyên nhiều bảng có thể bắt đầu khảo sát RDBMS như PostgreSQL. Một hệ thống quản lý hồ sơ có cấu trúc linh hoạt, thường đọc/ghi nguyên tài liệu có thể xem xét document DBMS như MongoDB. Hệ thống truy vết những chuỗi liên kết phức tạp có thể khảo sát graph DBMS như Neo4j. Đây là **định hướng lựa chọn**, không phải quy tắc rằng mỗi loại bài toán chỉ dùng được một mô hình.

## 9. Ghi nhớ bằng ba phép hỏi

Khi gặp một thuật ngữ mới, hãy thử đặt nó vào đúng câu hỏi:

1. **“Dữ liệu được hiểu và liên kết như thế nào?”** → Câu trả lời thuộc **mô hình dữ liệu** (quan hệ, tài liệu, đồ thị, khóa–giá trị...).
2. **“Tôi diễn đạt thao tác với dữ liệu bằng cách nào?”** → Câu trả lời thuộc **ngôn ngữ hoặc API** (SQL, MQL, CQL, Cypher...).
3. **“Phần mềm nào thực sự chạy và quản lý dữ liệu?”** → Câu trả lời thuộc **DBMS** (PostgreSQL, MongoDB, Redis, Neo4j...).

Trong ngữ cảnh tư duy NoSQL, phân biệt ba khái niệm này giúp tránh so sánh lệch tầng. **SQL là một ngôn ngữ; mô hình quan hệ là một cách tổ chức dữ liệu; PostgreSQL, MongoDB và các sản phẩm tương tự là các hệ quản trị cụ thể.** Quyết định kiến trúc đúng đắn bắt đầu từ dữ liệu, thao tác và ràng buộc của bài toán rồi mới đến lựa chọn DBMS phù hợp.
