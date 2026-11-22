# Ranh giới giữa NoSQL, NewSQL, SQL phân tán và hệ đa mô hình

Khi một hệ thống cần lưu lượng dữ liệu lớn, nhiều nhóm phát triển đặt câu hỏi: “Nên dùng NoSQL, NewSQL, distributed SQL hay multi-model database?”. Bốn nhãn này dễ tạo cảm giác như bốn loại cơ sở dữ liệu loại trừ nhau. Thực tế, chúng mô tả **những khía cạnh khác nhau**: mô hình dữ liệu, giao diện truy vấn, kiến trúc phân tán, cách bảo đảm giao dịch và số mô hình được hỗ trợ trong một hệ thống.

Một cơ sở dữ liệu có thể vừa sử dụng SQL, vừa phân tán dữ liệu qua nhiều máy; một hệ NoSQL có thể cung cấp giao dịch ACID; một sản phẩm đa mô hình có thể hỗ trợ document và graph nhưng không nhất thiết có cùng cam kết giao dịch giữa mọi mô hình. Vì thế, chọn công nghệ dựa trên tên gọi thường kém tin cậy hơn việc kiểm tra **hệ thống lưu gì, truy vấn như thế nào và phải bảo đảm kết quả ra sao**.

Bài này đặt bốn khái niệm lên cùng hệ tọa độ, chỉ ra các vùng chồng lấn, giải thích những khác biệt ảnh hưởng đến thiết kế thực tế và thực hành đưa ra quyết định từ một bài toán nghiệp vụ.

## 1. Bốn nhãn không nằm trên cùng một trục phân loại

Trước hết, cần tách các câu hỏi vốn thường bị gộp lại:

| Trục xem xét | Câu hỏi cần trả lời | Ví dụ các lựa chọn |
|---|---|---|
| **Mô hình dữ liệu** | Dữ liệu được biểu diễn và liên kết thế nào? | Bảng quan hệ, document, key-value, wide-column, graph |
| **Ngôn ngữ và API** | Ứng dụng truy vấn, ghi và tổng hợp bằng cách nào? | SQL, API key-value, truy vấn document, CQL, ngôn ngữ graph |
| **Phân bố dữ liệu** | Dữ liệu nằm ở một node hay được chia qua nhiều node? | Một node; replication; sharding; distributed storage |
| **Giao dịch và nhất quán** | Những thao tác nào được bảo đảm nguyên tử, được đọc ở mức nhất quán nào? | Giao dịch một bản ghi/document, giao dịch nhiều bản ghi, snapshot, strong/eventual consistency tùy cơ chế |
| **Số mô hình được hỗ trợ** | Một hệ quản trị có hỗ trợ trực tiếp nhiều cách mô hình hóa và truy vấn không? | Chuyên một mô hình; hỗ trợ document + graph; hỗ trợ nhiều API/mô hình |

Từ đó có thể hiểu:

- **NoSQL** thường chỉ một nhóm cơ sở dữ liệu không lấy mô hình quan hệ và SQL truyền thống làm trung tâm. Nhóm này bao gồm nhiều họ với đặc tính rất khác nhau.
- **NewSQL** là thuật ngữ rộng và không có ranh giới tiêu chuẩn thống nhất, thường dùng cho các hệ thống hướng đến khả năng mở rộng của kiến trúc hiện đại trong khi vẫn duy trì SQL và các bảo đảm giao dịch mạnh cho workload giao dịch.
- **SQL phân tán (distributed SQL)** thường chỉ cơ sở dữ liệu quan hệ cung cấp giao diện SQL và tổ chức lưu trữ, thực thi, sao chép hoặc giao dịch qua nhiều node như một hệ logic thống nhất.
- **Hệ đa mô hình (multi-model database)** nhấn mạnh khả năng phục vụ trực tiếp nhiều mô hình dữ liệu trong cùng hệ quản trị hoặc nền tảng.

Điểm cốt lõi: **NewSQL và SQL phân tán có vùng giao nhau lớn; multi-model là một thuộc tính có thể chồng lên các nhãn khác; NoSQL là một tập hợp nhiều mô hình**, không phải một giao thức hay một mức nhất quán duy nhất.

### Một bản đồ khái niệm

~~~mermaid
flowchart TD
    A["Chọn cơ sở dữ liệu"] --> B["Mô hình dữ liệu và truy vấn"]
    A --> C["Giao dịch, nhất quán"]
    A --> D["Kiến trúc triển khai, phân tán"]
    A --> E["Một hay nhiều mô hình"]
    B --> F["Quan hệ + SQL"]
    B --> G["Document, key-value, wide-column, graph"]
    F --> H["SQL truyền thống / SQL phân tán"]
    G --> I["Các họ NoSQL"]
    C --> J["Phạm vi ACID, mức cô lập, đọc/ghi"]
    D --> K["Partition, replication, đồng thuận, locality"]
    E --> L["Multi-model nếu hỗ trợ nhiều mô hình thực chất"]
    H -. "Một số hệ SQL phân tán được gọi là" .-> M["NewSQL"]
~~~

Sơ đồ không phải cây phân loại độc quyền. Ví dụ một sản phẩm lưu document và graph, đồng thời phân tán qua nhiều node, vẫn có thể thuộc nhóm NoSQL và được mô tả là multi-model. Một sản phẩm SQL phân tán có thể được gọi là NewSQL nhưng không phải mọi sản phẩm dùng nhãn NewSQL đều có cùng kiến trúc.

## 2. “SQL” là ngôn ngữ, “quan hệ” là mô hình

Để hiểu ranh giới, trước tiên cần tách **SQL** ra khỏi **mô hình quan hệ**.

Trong mô hình quan hệ, dữ liệu được biểu diễn bằng các quan hệ (thường được triển khai thành bảng); mỗi hàng biểu diễn một bản ghi và các thuộc tính được quản lý theo schema. Khóa chính, khóa ngoại, ràng buộc duy nhất và giao dịch giúp biểu diễn những bất biến của nghiệp vụ. SQL là ngôn ngữ thường được dùng để khai báo, truy vấn và cập nhật dữ liệu quan hệ.

Ví dụ, một hệ thống bán hàng có thể dùng:

~~~sql
CREATE TABLE customers (
    id          VARCHAR(36) PRIMARY KEY,
    full_name   VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id           VARCHAR(36) PRIMARY KEY,
    customer_id  VARCHAR(36) NOT NULL REFERENCES customers(id),
    status       VARCHAR(20) NOT NULL,
    created_at   TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_id     VARCHAR(36) NOT NULL REFERENCES orders(id),
    line_no      INTEGER NOT NULL,
    sku          VARCHAR(100) NOT NULL,
    quantity     INTEGER NOT NULL,
    unit_price   DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
~~~

Khi lấy đơn và dòng hàng, ứng dụng có thể viết:

~~~sql
SELECT o.id, o.created_at, i.sku, i.quantity, i.unit_price
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.id
WHERE o.customer_id = 'c7'
  AND o.status = 'PAID'
ORDER BY o.created_at DESC, o.id DESC, i.line_no ASC;
~~~

**JOIN** là phép truy vấn qua các quan hệ. Nó không tự biến một cơ sở dữ liệu thành “chậm”, cũng không đồng nghĩa phải dùng một máy. Chi phí phụ thuộc index, cách đặt dữ liệu, cardinality, kế hoạch thực thi và việc các hàng liên quan có nằm gần nhau trong hệ phân tán hay không.

Tương tự, một cơ sở dữ liệu hỗ trợ câu lệnh giống SQL chưa chắc là relational database theo cùng nghĩa. Có hệ NoSQL cung cấp cú pháp SELECT hoặc một ngôn ngữ gần SQL nhưng ràng buộc, JOIN, transaction, index và cách phân vùng khác đáng kể so với PostgreSQL hoặc MySQL. **Cú pháp là bề mặt giao tiếp; mô hình dữ liệu và cam kết thực thi là hợp đồng sâu hơn.**

## 3. NoSQL: một họ kiến trúc, không phải lời tuyên bố “không có SQL”

Thuật ngữ **NoSQL** thường được giải thích theo cách mở là *Not Only SQL*. Điều cần nhớ là NoSQL không phải một engine hoặc tiêu chuẩn chung; nó tập hợp nhiều hướng tiếp cận nhằm tối ưu các kiểu dữ liệu và truy vấn khác nhau.

| Họ NoSQL | Đơn vị mô hình hóa nổi bật | Kiểu truy cập thường hiệu quả | Câu hỏi thiết kế then chốt |
|---|---|---|---|
| **Key-value** | Khóa → giá trị | Tra nhanh theo khóa đã biết, cache, session | Khóa là gì, TTL ra sao, cần truy vấn ngoài khóa hay không? |
| **Document** | Document chứa trường và cấu trúc lồng nhau | Đọc/ghi theo aggregate, lọc theo trường đã index | Nhúng hay tham chiếu; document lớn tới đâu; index nào phục vụ access pattern? |
| **Wide-column** | Row/partition, tập cột theo thiết kế hệ thống | Truy cập theo partition key, đọc dải sắp xếp | Partition key có phân bố tải tốt và bao phủ truy vấn không? |
| **Graph** | Đỉnh, cạnh, thuộc tính và đường đi | Duyệt quan hệ nhiều bước, tìm đường, phân tích kết nối | Truy vấn thực sự cần đi qua những quan hệ nào và sâu đến đâu? |

Những mục trên là các họ điển hình, không phải danh sách đầy đủ. Các hệ hiện đại còn có search engine, time-series, vector database và nhiều kiến trúc lai. Cách phân loại có thể khác nhau giữa tài liệu, sản phẩm và workload cụ thể.

### Ví dụ document: lưu cả snapshot dòng hàng trong đơn

Với một đơn hàng có số mặt hàng được giới hạn hợp lý, document có thể chứa các dòng hàng được đọc cùng nhau:

~~~javascript
{
  _id: "o104",
  customerId: "c7",
  status: "PAID",
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  currency: "VND",
  items: [
    { sku: "BOOK", title: "Sổ", quantity: 2, unitPrice: 50000 },
    { sku: "PEN", title: "Bút", quantity: 1, unitPrice: 20000 }
  ],
  orderTotal: 120000
}
~~~

Một truy vấn MongoDB minh họa:

~~~javascript
db.orders.find(
  { customerId: "c7", status: "PAID" },
  { _id: 1, createdAt: 1, orderTotal: 1, currency: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(10);
~~~

Trong ví dụ này, ứng dụng tập trung vào việc đọc cả đơn như một aggregate. Đưa snapshot giá và tên sản phẩm vào dòng hàng giúp giữ lịch sử giao dịch khi catalog thay đổi. Nhưng nếu một đơn có hàng triệu dòng hoặc thường xuyên cần sửa từng dòng từ nhiều tiến trình độc lập, ranh giới document phải được đánh giá lại.

### NoSQL có thể có ACID

Không nên dùng mệnh đề “NoSQL không hỗ trợ transaction” làm quy tắc. Một số hệ có bảo đảm nguyên tử cho một key/document; một số hỗ trợ giao dịch nhiều document hoặc nhiều item; phạm vi, mức cô lập, giới hạn và chi phí khác nhau tùy sản phẩm và cấu hình.

Ví dụ, MongoDB có tính nguyên tử khi cập nhật một document và có cơ chế transaction cho nhiều document trong các cấu hình được hỗ trợ. DynamoDB có các thao tác điều kiện và transaction API; Redis có các cơ chế nguyên tử và transaction theo ngữ nghĩa riêng. Vì vậy, cần đọc đúng hợp đồng **phạm vi giao dịch, mức cô lập, khả năng retry và kết quả khi lỗi**, thay vì suy ra từ nhãn NoSQL.

NoSQL cũng không đồng nghĩa dữ liệu “phi cấu trúc”. Document thường có schema ứng dụng, trường bắt buộc, quy tắc phiên bản, validator và index. Nếu không xác định những điều này, tính linh hoạt có thể dẫn đến khó kiểm soát dữ liệu về sau.

## 4. NewSQL: giữ ưu thế giao dịch quan hệ trong kiến trúc hiện đại

**NewSQL** là cách gọi xuất hiện để mô tả các hệ thống hướng đến ba mục tiêu:

1. Sử dụng SQL và tư duy dữ liệu quan hệ quen thuộc.
2. Cung cấp các bảo đảm giao dịch cho workload OLTP (online transaction processing).
3. Mở rộng và vận hành trên hạ tầng hiện đại, thường có khả năng phân tán hoặc scale-out.

Tuy nhiên, **NewSQL không phải một chuẩn kỹ thuật định nghĩa chính xác API, isolation level hay cách triển khai**. Tên gọi thiên về một nhóm mục tiêu kiến trúc và có thể được sử dụng khác nhau giữa cộng đồng nghiên cứu và tài liệu sản phẩm.

Điều quan trọng hơn nhãn là những câu hỏi cụ thể:

- Hệ quản trị có hỗ trợ giao dịch ACID qua những khóa, bảng hoặc partition nào?
- Khi ghi qua nhiều node, làm thế nào bảo đảm commit nguyên tử và xử lý lỗi?
- Tính nhất quán đọc/ghi được bảo đảm ra sao ở các vùng địa lý?
- Khi thêm node, phần nào có thể scale-out thực sự: lưu trữ, đọc, ghi hay tất cả?
- Có hạn chế gì trong dialect SQL, khóa ngoại, constraint, index và tính năng truy vấn?
- Ứng dụng có phải quản lý partition thủ công và xác định shard cho mỗi transaction hay không?

Một sản phẩm được gọi là NewSQL không mặc nhiên nhanh hơn mọi hệ SQL truyền thống. Với một ứng dụng nhỏ, mô hình trên một server hoặc cụm primary-replica có thể đơn giản, nhanh và dễ vận hành hơn. Scale-out có giá trị khi workload, yêu cầu phục hồi hoặc vị trí địa lý thực sự cần đến.

## 5. SQL phân tán: SQL nằm trên một hệ dữ liệu được phân bố

**Distributed SQL** theo nghĩa thường dùng cho workload giao dịch là hệ quản trị quan hệ cung cấp giao diện SQL, trong khi dữ liệu và cơ chế xử lý nằm trên nhiều node. Ứng dụng làm việc với một cơ sở dữ liệu logic; bên dưới, hệ thống có thể phân vùng dữ liệu, sao chép, điều phối truy vấn và giao dịch.

Một kiến trúc khái quát:

~~~mermaid
flowchart TD
    A["Ứng dụng: SQL, transaction"] --> B["Điều phối truy vấn / giao dịch"]
    B --> P1["Partition A: customers"]
    B --> P2["Partition B: orders"]
    B --> P3["Partition C: inventory"]
    P1 --- R1["Replica / consensus group A"]
    P2 --- R2["Replica / consensus group B"]
    P3 --- R3["Replica / consensus group C"]
~~~

Sơ đồ chỉ minh họa thành phần, không mô tả tất cả engine. Có hệ phân vùng theo range, có hệ theo hash; có hệ tách compute và storage; có hệ điều phối giao dịch hoặc điều khiển replica theo các cách khác nhau.

### Một câu SQL có thể trở thành công việc liên node

Giả sử hệ thống phải đặt sản phẩm còn đúng một đơn vị tồn kho. Trên cơ sở dữ liệu quan hệ, luồng giao dịch có thể được diễn đạt bằng SQL kiểu PostgreSQL:

~~~sql
BEGIN;

UPDATE inventory
SET available = available - 1
WHERE sku = 'SKU-42'
  AND available > 0
RETURNING available;

-- Chỉ tiếp tục nếu UPDATE ảnh hưởng đúng một hàng.
-- Nếu không, ROLLBACK và báo hết hàng.

INSERT INTO orders (id, customer_id, status, created_at)
VALUES ('order-901', 'c7', 'CREATED', CURRENT_TIMESTAMP);

COMMIT;
~~~

Ví dụ giả định schema **inventory** và **orders** đã được tạo, **id** và khóa yêu cầu idempotency được bảo vệ bởi ràng buộc phù hợp. **RETURNING** là cú pháp kiểu PostgreSQL; dialect và hành vi hỗ trợ có thể khác giữa các SQL database.

Ở một hệ SQL phân tán, hàng **inventory** và **orders** có thể nằm ở các partition khác nhau. Để giữ giao dịch nguyên tử, hệ phải phối hợp ghi, xử lý cạnh tranh và hoàn tất commit theo cơ chế của nó. Các bước liên node, replication và đồng thuận có thể tăng độ trễ so với cập nhật thuần nội bộ một node.

Do đó, **giữ ngữ nghĩa SQL và transaction không có nghĩa chi phí phân tán biến mất**. Một câu lệnh đơn giản ở tầng ứng dụng vẫn có thể tạo nhiều lần trao đổi mạng, đọc hoặc ghi giữa các node.

### SQL phân tán khác gì “có replica” hoặc “tự shard SQL”?

Một cơ sở dữ liệu SQL truyền thống có thể được triển khai với primary-replica, failover hoặc phân mảnh thủ công. Điều đó làm **hệ thống triển khai có tính phân tán**, nhưng chưa tự động đồng nghĩa một database engine sẽ điều phối nhất quán các transaction và JOIN trên nhiều shard như một hệ logic.

| Kiểu triển khai | Việc ứng dụng có thể phải đảm nhiệm |
|---|---|
| SQL một node | Điều khiển transaction, tối ưu index, backup và xử lý bottleneck node |
| SQL với read replica | Chọn nơi đọc; xử lý replication lag và tính mới của dữ liệu |
| SQL shard thủ công | Định tuyến theo shard key; cân nhắc giao dịch/join giữa các shard |
| Distributed SQL có giao dịch liên partition | Ít logic định tuyến ứng dụng hơn ở một số thiết kế; vẫn phải hiểu locality, hotspot, tính nhất quán và chi phí giao dịch |

Có những nền tảng hoặc middleware cung cấp trải nghiệm ở giữa các trường hợp trên. Vì vậy cần kiểm tra khả năng thực tế, thay vì gắn nhãn chỉ dựa vào sơ đồ hạ tầng.

### Distributed SQL không đồng nghĩa mọi công cụ truy vấn SQL phân tán

Các công cụ phân tích có thể chạy SQL trên dữ liệu phân tán, chẳng hạn query engine xử lý tập tin lớn hoặc kho dữ liệu phân tích. Chúng **có thể không cung cấp cùng ngữ nghĩa transaction OLTP, kiểm soát cạnh tranh và constraint** như một cơ sở dữ liệu distributed SQL giao dịch.

Hai hệ đều chạy SELECT trên nhiều máy nhưng phục vụ mục tiêu khác nhau:

- **Distributed SQL OLTP:** ghi/đọc giao dịch trực tuyến, cập nhật tồn kho, chuyển tiền, nhiều request nhỏ đồng thời.
- **Distributed analytical SQL:** quét nhiều bản ghi, tổng hợp, báo cáo và phân tích dữ liệu lớn.

Từ “distributed SQL” trong thảo luận kỹ thuật cần gắn với workload và cam kết giao dịch để tránh hiểu lầm.

## 6. Ranh giới giữa NewSQL và SQL phân tán

Hai khái niệm chồng lấn đáng kể, nhưng khác tiêu điểm:

| Góc nhìn | NewSQL | SQL phân tán |
|---|---|---|
| Trọng tâm của thuật ngữ | Mục tiêu kết hợp SQL, giao dịch quan hệ và khả năng mở rộng hiện đại | Kiến trúc cơ sở dữ liệu SQL hoạt động qua nhiều node |
| Bản chất định nghĩa | Nhãn nhóm sản phẩm/kiến trúc tương đối rộng | Mô tả rõ hơn thuộc tính hệ SQL được phân tán |
| SQL | Thường là đặc trưng cốt lõi | Là giao diện cốt lõi |
| Giao dịch | Thường nhấn mạnh ACID cho OLTP | Phạm vi ACID và mức cô lập phải xem engine/cấu hình |
| Scale-out | Thường là mục tiêu | Thường là khả năng thiết kế quan trọng |
| Quan hệ giữa hai nhãn | Nhiều hệ distributed SQL được xếp vào NewSQL | Không phải mọi thứ mang nhãn NewSQL có một kiến trúc giống nhau |

Ví dụ sản phẩm thường được nhắc đến trong nhóm cơ sở dữ liệu SQL phân tán/NewSQL gồm **CockroachDB, Google Spanner, YugabyteDB, TiDB**. Chúng có kiến trúc, khả năng tương thích SQL, tính năng giao dịch, triển khai và cam kết cụ thể khác nhau. Danh sách chỉ mang tính định hướng khái niệm; không có nghĩa các hệ tương đương hoặc một ứng dụng có thể chuyển đổi chỉ bằng thay JDBC URL.

Không nên lập luận rằng “NewSQL luôn nhất quán mạnh hơn NoSQL” hoặc “SQL phân tán luôn ACID ở mọi thao tác”. Mọi kết luận đều cần chỉ rõ **loại thao tác, cấu hình replication, isolation level, điểm đọc và failure mode**.

## 7. Hệ đa mô hình: nhiều cách nhìn và truy vấn dữ liệu trong một nền tảng

**Multi-model database** cho phép một hệ quản trị hỗ trợ trực tiếp nhiều mô hình hoặc kiểu truy vấn dữ liệu, chẳng hạn document, graph, key-value và các cấu trúc khác. Ý tưởng là những phần khác nhau của nghiệp vụ có thể được mô tả tự nhiên bằng những mô hình khác nhau trong một nền tảng.

Ví dụ trong nền tảng thương mại:

- **Hồ sơ và catalog** có trường linh hoạt, có thể phù hợp với document.
- **Quan hệ theo dõi, giới thiệu, sở thích** có thể được biểu diễn bằng đỉnh và cạnh graph.
- **Tra cứu session theo id** có nhu cầu truy cập gần với key-value.

Nếu một hệ thực sự hỗ trợ document và graph như các mô hình trực tiếp, nó có thể cho phép truy vấn dữ liệu sản phẩm và mối quan hệ người dùng trong cùng một sản phẩm database, thay vì tạo hai kho độc lập rồi tự đồng bộ dữ liệu.

~~~text
                   Một nền tảng đa mô hình
             +----------------------------------+
             | Document: products, profiles      |
             | Graph: users - follows -> users   |
             | Graph: users - likes   -> products |
             | API/truy vấn tùy từng mô hình      |
             +----------------------------------+
                            |
                            v
                Truy vấn nghiệp vụ phối hợp
~~~

Các sản phẩm như **ArangoDB** hoặc **OrientDB** thường được nêu trong thảo luận về cơ sở dữ liệu đa mô hình. Một số nền tảng cloud cung cấp nhiều API hoặc cách truy cập dữ liệu cũng dùng thông điệp “multi-model”. Cần kiểm tra chi tiết liệu các API cùng nhìn vào một tập dữ liệu, chia sẻ transaction/index hay quản lý thành các mô hình hoặc kho dữ liệu độc lập.

### Thế nào mới là hỗ trợ nhiều mô hình một cách có ý nghĩa?

Một sản phẩm có JSON column, key-value API hoặc tính năng tìm kiếm full-text chưa chắc đã trở thành “multi-model” theo cùng nghĩa với cơ sở dữ liệu có đồ thị và khả năng duyệt cạnh trực tiếp. Ranh giới ở đây không có một chuẩn duy nhất. Thay vì tranh luận nhãn, hãy hỏi:

1. **Mô hình dữ liệu có thực chất không?** Có biểu diễn trực tiếp cạnh/đỉnh, document, key-value hay chỉ lưu mọi thứ như blob?
2. **Có ngôn ngữ/toán tử chuyên biệt không?** Truy vấn đường đi graph, truy xuất field document và phép tổng hợp có được hỗ trợ như chức năng chính không?
3. **Index và optimizer hoạt động thế nào?** Mỗi mô hình có index thích hợp hay một mô hình bị “giả lập” với chi phí cao?
4. **Dữ liệu có chung transaction không?** Một cập nhật document và một cạnh graph có commit nguyên tử được không? Phạm vi và mức cô lập là gì?
5. **Vận hành và scale ra sao?** Có thể tối ưu tài nguyên theo mô hình hay một workload gây ảnh hưởng các workload khác?
6. **Dữ liệu có cần sao chép không?** Dùng chung nền tảng có thực sự giảm đồng bộ hay chỉ đặt nhiều API lên các kho riêng?

**Một hệ multi-model không tự động là distributed SQL; một hệ distributed SQL không tự động là multi-model.** Thuộc tính “nhiều mô hình” độc lập với lựa chọn giao thức SQL, kiến trúc phân tán hoặc bảo đảm giao dịch.

## 8. Bảng đối chiếu bốn nhóm theo khả năng phải kiểm chứng

Không thể chấm điểm một nhóm “nhanh”, “dễ scale” hay “nhất quán” tuyệt đối, bởi mỗi nhóm có nhiều sản phẩm và chế độ triển khai. Bảng dưới cho thấy điểm cần tập trung khi đánh giá:

| Tiêu chí | Các hệ NoSQL | NewSQL | SQL phân tán | Multi-model |
|---|---|---|---|---|
| **Mô hình chính** | Key-value, document, wide-column, graph… | Thường là quan hệ | Quan hệ | Nhiều mô hình trong một nền tảng |
| **Giao diện truy vấn** | API và ngôn ngữ tùy họ; có thể có cú pháp giống SQL | SQL, dialect khác nhau | SQL, dialect khác nhau | Một hoặc nhiều API/ngôn ngữ |
| **Schema** | Có thể linh hoạt hoặc chặt, tùy engine | Thường khai báo quan hệ/ràng buộc | Thường khai báo quan hệ/ràng buộc | Theo từng mô hình |
| **JOIN và quan hệ** | Tùy engine; nhiều hệ tối ưu truy cập theo khóa/document | Thường hỗ trợ truy vấn quan hệ | Thường hỗ trợ JOIN quan hệ, chi phí phụ thuộc placement | Theo mô hình: có thể JOIN, duyệt graph hoặc truy vấn document |
| **ACID và isolation** | Tùy engine, thao tác và phạm vi | Thường là mục tiêu quan trọng | Cần xác minh mức cô lập/phạm vi giao dịch | Cần xác minh cả trong và giữa các mô hình |
| **Partition/replication** | Thường quan trọng trong thiết kế; có engine thiên về một node | Tùy kiến trúc | Là thành phần nền tảng | Tùy sản phẩm |
| **Ưu thế khi phù hợp** | Mô hình và access pattern chuyên biệt | Workload OLTP cần SQL và mở rộng | SQL/transaction trên hệ nhiều node | Cần nhiều biểu diễn dữ liệu có liên hệ |
| **Rủi ro khi chọn nhầm** | Thiếu đường truy vấn/ràng buộc cần thiết | Trả giá vận hành/phân tán khi chưa cần | Cross-partition latency, hot key, chi phí hệ phân tán | Một engine không tối ưu mọi mô hình; giới hạn transaction/index giữa mô hình |

Những ví dụ nhận diện thường gặp:

| Tên thường gặp | Vùng thường được nhắc đến | Ghi chú về ranh giới |
|---|---|---|
| PostgreSQL, MySQL | SQL quan hệ | Có nhiều cách triển khai HA/replica; một cấu hình nhiều node không tự thay đổi mô hình dữ liệu |
| MongoDB | NoSQL document | Hỗ trợ truy vấn theo field, index và giao dịch trong phạm vi được cung cấp |
| Redis | Key-value/data-structure store | Có TTL và nhiều kiểu cấu trúc; không nên suy ra cùng semantics với hệ quan hệ |
| Cassandra | NoSQL wide-column | Thiết kế dữ liệu xoay quanh partition và đường truy cập; CQL có cú pháp giống SQL |
| Neo4j | NoSQL graph | Tập trung mô hình đỉnh/cạnh và traversal |
| CockroachDB, YugabyteDB, TiDB, Spanner | Distributed SQL / thường được xếp NewSQL | Không tương đương nhau về dialect, giao dịch, triển khai hay tính năng |
| ArangoDB, OrientDB | Thường được xếp multi-model | Cần xét mô hình và ngữ nghĩa truy vấn/giao dịch thực tế |

Tên sản phẩm là các ví dụ khái niệm, không phải chứng nhận khả năng cụ thể của một phiên bản. Trong một quyết định triển khai, các chi tiết về tính năng cần được kiểm tra theo phiên bản và cấu hình dự kiến.

## 9. CAP, ACID và nhất quán: ba lớp vấn đề khác nhau

Một nguồn nhầm lẫn phổ biến là quy chụp:

> “SQL chọn consistency, NoSQL chọn availability; NewSQL có cả ba.”

Cách nói này không chính xác.

**ACID** mô tả nhóm thuộc tính của transaction: atomicity, consistency theo bất biến được bảo đảm, isolation và durability. Chữ **C** trong ACID liên quan đến việc transaction không phá các ràng buộc được khai báo hoặc quy tắc được ứng dụng giữ đúng; nó không cùng khái niệm với **consistency trong CAP**.

**CAP** nói về giới hạn của hệ phân tán khi xảy ra **network partition**. Với một mức consistency mạnh kiểu tuyến tính hóa (linearizability), nếu các node không thể liên lạc, hệ không thể đồng thời luôn chấp nhận và hoàn thành mọi thao tác ở cả hai phía như thể không có sự cố. Quyết định hệ thống phản hồi lỗi, chờ, cho đọc cũ hay nhận ghi phụ thuộc thiết kế và cấu hình.

**Mức nhất quán đọc/ghi** là hợp đồng cụ thể: một người dùng đọc ngay sau ghi có chắc thấy giá trị mới không? Các vùng có thể đọc bản sao trễ không? Transaction bao phủ một key, một document, một partition hay nhiều partition? Một hệ có thể cung cấp nhiều lựa chọn cho các thao tác khác nhau.

Nên phân tách khi thiết kế:

| Câu hỏi | Thuộc lớp nào? |
|---|---|
| Hai bước trừ tồn kho và tạo đơn phải cùng thành công hoặc cùng thất bại? | Atomicity và transaction |
| Hai giao dịch cùng giữ chỗ có được nhìn trạng thái hợp lệ và tránh oversell? | Isolation, kiểm soát cạnh tranh, bất biến nghiệp vụ |
| Đọc từ replica sau khi ghi vào leader có thể thấy dữ liệu cũ? | Replication và read consistency |
| Khi hai khu vực mất kết nối, hệ cho phép ghi ở cả hai nơi không? | Partition tolerance, availability, conflict handling |
| Khi không có sự cố, truy vấn toàn cầu mất bao lâu? | Latency, locality, mạng, giao thức commit |

Không có câu trả lời đúng cho mọi tính năng. Một lượt xem catalog có thể chấp nhận dữ liệu chậm vài giây; thao tác thu tiền hoặc phân bổ ghế cuối cùng lại cần bảo đảm mạnh hơn. Kết hợp nhiều mức nhất quán theo chức năng là quyết định thiết kế, không phải mâu thuẫn.

## 10. Bài toán đặt hàng: cùng nghiệp vụ, các hướng thiết kế khác nhau

Xét hệ thống có bốn yêu cầu:

1. Khách đặt một sản phẩm, hệ thống không được bán vượt tồn kho.
2. Khách xem đơn đã thanh toán mới nhất và chi tiết từng đơn.
3. Mỗi ngày nhận hàng chục triệu sự kiện xem sản phẩm để phân tích.
4. Sản phẩm hiển thị gợi ý theo quan hệ “người dùng theo dõi người nào, cùng thích những mặt hàng nào”.

### Hướng A — Quan hệ SQL cho lõi giao dịch

Ta chọn các bảng **inventory**, **orders**, **order_items** và **payments**, dùng constraint và transaction để giữ các bất biến quan trọng. Lượt xem đơn theo khách sử dụng index trên customer_id, status và created_at.

Ưu điểm khi phù hợp: mô hình quan hệ và giao dịch làm rõ các bất biến, dễ biểu diễn quan hệ giữa đơn, tồn kho và thanh toán. Cần chú ý contention trên những SKU rất “nóng”, tránh coi transaction là giải pháp tự động cho mọi giới hạn tải.

Nếu lưu lượng và vị trí triển khai còn vừa phải, SQL truyền thống có thể đủ. Khi cần phân tán ghi hoặc tăng khả năng chịu lỗi nhiều node, đánh giá distributed SQL là một phương án có cơ sở; yêu cầu đó cần được chứng minh bằng tải và mục tiêu phục hồi, không phải nhãn “hiện đại”.

### Hướng B — Document NoSQL cho truy vấn theo aggregate

Đơn hàng được lưu thành document chứa snapshot của các dòng sản phẩm. Đây là cách mô hình hóa tự nhiên nếu phần lớn thao tác đọc chi tiết một đơn hoặc danh sách đơn theo customerId.

Nếu **inventory** và **orders** là hai document khác nhau, cập nhật tồn kho rồi ghi đơn **không tự động trở thành một transaction nguyên tử nhiều document**. Ta phải chọn transaction được engine hỗ trợ, mô hình hóa lại aggregate, hoặc một giao thức đặt trước/giữ chỗ có idempotency và đối soát. Phải xác định cùng một SKU được sửa đồng thời ra sao, retry thế nào và khi mất kết nối liệu đơn đã commit hay chưa.

Ví dụ thao tác trừ tồn kho có điều kiện trong MongoDB:

~~~javascript
const result = db.inventory.updateOne(
  { _id: "SKU-42", available: { $gt: 0 } },
  { $inc: { available: -1 } }
);

// result.modifiedCount === 1: đã trừ một đơn vị.
// result.modifiedCount === 0: không có bản ghi phù hợp để trừ.
~~~

Thao tác trên có tính nguyên tử ở **một document inventory**, nhưng chưa tạo đơn tương ứng. Để bảo đảm cả việc tạo đơn, cần một quy trình giao dịch hoặc workflow bổ sung phù hợp. Thêm idempotency key giúp phát hiện request lặp do retry; điều kiện trên một bản ghi tồn kho không tự giải quyết được mọi trường hợp mạng và ghi đơn.

### Hướng C — Wide-column hoặc kho sự kiện cho clickstream

Với hàng chục triệu sự kiện mỗi ngày, workload chính có thể là append và tra cứu sự kiện theo tenant + khoảng thời gian. Mô hình partition theo tenant và time bucket phù hợp hơn với nhiều hệ wide-column hoặc dữ liệu sự kiện được tổ chức theo thời gian.

Ở đây cần phân tích phân bố tải, số partition, retention, TTL và truy vấn thực tế. Không nên dùng tiêu chí “dữ liệu lớn” làm lý do mặc định để chọn NoSQL: một kho phân tích dạng cột hoặc pipeline object storage cũng có thể là lựa chọn thích hợp, tùy độ trễ và mục đích truy vấn.

### Hướng D — Graph cho mối quan hệ nhiều bước

Gợi ý “bạn của bạn thích gì?” có thể cần duyệt nhiều cạnh: **User → FOLLOWS → User → LIKES → Product**. Với đường đi thay đổi độ sâu và nhiều phép duyệt quan hệ, một graph model chuyên dụng có thể diễn đạt trực tiếp hơn.

Mã giả truy vấn dạng graph:

~~~text
MATCH (viewer:User {id: "c7"})-[:FOLLOWS]->(friend:User)
      -[:LIKES]->(product:Product)
RETURN product, count(DISTINCT friend) AS likedByFriends
ORDER BY likedByFriends DESC
LIMIT 10
~~~

Đây là cú pháp minh họa theo phong cách Cypher, không phải truy vấn chạy được trên mọi hệ multi-model hay graph database. Trong ứng dụng thực tế cần lọc quyền riêng tư, giới hạn độ sâu và khối lượng duyệt, ngăn bản sao gợi ý chứa dữ liệu không còn được phép sử dụng.

### Có nên đưa tất cả vào một cơ sở dữ liệu?

Có ba hướng hợp lệ tùy yêu cầu:

- **Một hệ SQL quan hệ**: giữ đơn giản về vận hành, sử dụng bảng/index và extension phù hợp nếu lượng dữ liệu và độ phức tạp cho phép.
- **Một hệ đa mô hình**: tận dụng document + graph trực tiếp nếu tính năng, hiệu năng và giao dịch đáp ứng cả hai access pattern.
- **Polyglot persistence**: SQL/SQL phân tán cho transaction, kho sự kiện cho analytics, graph cho gợi ý. Đổi lại cần đồng bộ, xác định nguồn sự thật và xử lý lỗi khi dữ liệu đi qua nhiều hệ.

Không có phương án nào thắng chỉ từ tên công nghệ. Cần ước lượng tổng chi phí sở hữu, vận hành, kỹ năng đội ngũ và kiểm chứng workflow khi xảy ra lỗi.

## 11. Multi-model khác “polyglot persistence” như thế nào?

Hai cách tiếp cận thường được nhắc đến cùng nhau nhưng khác ranh giới vận hành.

**Multi-model**: nhiều mô hình được hỗ trợ bên trong một hệ quản trị/nền tảng. Tùy sản phẩm, có thể giảm số hệ phải quản trị và số pipeline đồng bộ. Tuy nhiên, chia sẻ nền tảng không bảo đảm mọi mô hình có cùng transaction, scale hoặc hiệu năng.

**Polyglot persistence**: ứng dụng dùng nhiều cơ sở dữ liệu, mỗi hệ tối ưu cho một workload; ví dụ PostgreSQL cho đơn hàng, một kho document cho catalog, graph database cho gợi ý. Kiến trúc này cho phép mỗi mô hình chọn hệ tối ưu nhưng đặt thêm bài toán **sao chép dữ liệu và nhất quán liên hệ thống**.

Ví dụ, đơn hàng được ghi trong SQL và sự kiện **OrderPaid** được gửi sang hệ tổng hợp. Nếu transaction tạo đơn commit thành công nhưng publish event thất bại, dashboard có thể thiếu doanh thu. Một giải pháp phổ biến là **transactional outbox**: ghi thông tin đơn và bản ghi outbox trong cùng transaction, sau đó worker xuất sự kiện. Consumer phải có idempotency để chấp nhận việc có thể nhận sự kiện trùng.

~~~mermaid
flowchart LR
    A["Transaction ở SQL: order + outbox"] --> B["Outbox relay"]
    B --> C["Event stream"]
    C --> D["Analytics / search / graph projection"]
    D --> E["Kiểm tra lag, retry và đối soát"]
~~~

Outbox giải quyết vấn đề “commit nghiệp vụ nhưng không có bản ghi để publish” khi triển khai đúng; nó không mặc nhiên tạo transaction ACID xuyên suốt tất cả database đích. Dữ liệu dẫn xuất có thể trễ và cần cơ chế đối soát, phát lại, versioning, xử lý thứ tự sự kiện.

Một multi-model database có thể giảm nhu cầu đồng bộ nội bộ, nhưng nếu ứng dụng vẫn có kho search, cache, data lake hay dịch vụ bên ngoài, những bài toán trên vẫn xuất hiện.

## 12. Chọn công nghệ theo phép thử nghiệp vụ và chi phí thực thi

Thay vì hỏi “NoSQL hay SQL?”, hãy trả lời sáu nhóm câu hỏi theo thứ tự:

### Bước 1 — Viết các bất biến phải giữ

Ví dụ:

- Một chỗ ngồi không được bán cho hai người.
- Số tiền đã thu phải khớp tổng dòng hàng được xác nhận.
- Người dùng chỉ nhìn thấy đơn thuộc quyền truy cập.
- Sự kiện xem sản phẩm có thể ghi trễ và xử lý lặp, nhưng không được tính hai lần khi tổng hợp.

Hãy ghi rõ **phạm vi transaction**: một document, nhiều hàng, nhiều partition, nhiều vùng hay nhiều hệ thống. Đây là đầu vào quan trọng để đánh giá API giao dịch.

### Bước 2 — Liệt kê access patterns, không chỉ liệt kê thực thể

| Truy vấn | Đầu vào | Đầu ra | Yêu cầu |
|---|---|---|---|
| Đọc đơn | customerId, trạng thái, cursor | 10 đơn mới nhất | Phân trang ổn định, p95 theo mục tiêu đã đo |
| Đặt hàng | sku, userId, requestId | Kết quả thành công/thất bại | Không oversell, retry an toàn |
| Tra cứu sự kiện | tenant, khoảng thời gian | Dòng thời gian sự kiện | Khối lượng lớn, giới hạn retention |
| Gợi ý theo quan hệ | userId, độ sâu duyệt | Danh sách sản phẩm | Truy vấn graph có giới hạn chi phí |

Từ access pattern, thử vẽ đường đọc thực sự: đi qua bao nhiêu partition, bao nhiêu document/hàng, cần JOIN hay traversal, có điều kiện lọc/index thích hợp không?

### Bước 3 — Đo tải và phân bố

Cần số liệu về QPS, read/write ratio, kích thước bản ghi, tốc độ tăng, p95/p99, số tenant, nhóm khóa nóng, lượng dữ liệu cần giữ và đỉnh tải. Quyết định có cần phân tán và shard theo đâu thường phụ thuộc **phân bố** hơn chỉ tổng byte.

Ví dụ 1 TB dữ liệu với toàn bộ request tập trung vào một SKU có bài toán contention khác 1 TB dữ liệu phân bố đều qua một triệu khách. Thêm node không tự giải quyết hot key nếu tất cả thao tác vẫn tranh chấp cùng một tài nguyên logic.

### Bước 4 — Xác định khả năng nhất quán và độ trễ chấp nhận

Một API xem catalog có thể đọc replica trễ trong giới hạn nghiệp vụ. API xác nhận đặt chỗ không được trả thành công khi kết quả commit còn mơ hồ. Nếu triển khai nhiều khu vực, phải nêu ai được ghi, ghi ở khu vực nào, khi mất kết nối có tiếp tục nhận ghi hay không.

Đánh giá contract chi tiết hơn “strong/eventual”, bao gồm:

- Read-your-writes có được bảo đảm ở đường đọc người dùng không?
- Transaction qua các partition có được hỗ trợ và ở isolation level nào?
- Khi client timeout sau COMMIT, làm sao xác định giao dịch đã thành công hay chưa?
- Retry có thể làm phát sinh bản ghi trùng hoặc trừ kho hai lần không?
- Nếu một vùng mất kết nối, ứng dụng sẽ fail, chờ hay chuyển vùng?

### Bước 5 — So sánh chi phí logic và chi phí vận hành

**Chi phí logic** là mức phức tạp của schema, truy vấn, transaction, đồng bộ dữ liệu và xử lý lỗi.

**Chi phí vận hành** gồm hạ tầng, replication, backup/restore, observability, bảo mật, upgrade, index, compaction, dung lượng tăng và năng lực đội ngũ. Sử dụng một hệ nhiều tính năng có thể giảm số sản phẩm phải vận hành, nhưng tăng sự phụ thuộc vào các đặc điểm riêng và làm khó tối ưu từng workload.

### Bước 6 — Chạy phép thử đúng với tình huống thực tế

Một thử nghiệm chọn database nên đo:

1. **Đúng dữ liệu**: transaction và ràng buộc hoạt động như mong đợi dưới truy cập đồng thời.
2. **Đúng đường truy vấn**: query plan sử dụng index và partition theo thiết kế.
3. **Tải đại diện**: có hot key, bản ghi lớn, dữ liệu phân bố lệch, giờ cao điểm và độ tăng trưởng dự kiến.
4. **Lỗi thực tế**: mất node, mất mạng, retry sau timeout, restore từ backup.
5. **Chi phí vận hành**: số thao tác phức tạp, thời gian backup/restore, yêu cầu kỹ năng và giới hạn dịch vụ.

Chỉ khi có kết quả từ workload thực tế mới có cơ sở kết luận hệ nào phù hợp hơn. Benchmark tổng quát của một nhà cung cấp không thể thay cho phép thử trên query, schema, tính nhất quán và cấu hình của ứng dụng.

## 13. Những kết luận sai thường gặp

| Nhận định dễ gặp | Cách hiểu chính xác hơn |
|---|---|
| “NoSQL luôn eventual consistency.” | Phải xem hệ, thao tác, read/write configuration và phạm vi. Có NoSQL cung cấp nhiều mức nhất quán hoặc transaction. |
| “NoSQL không thể JOIN hoặc transaction.” | Một số hệ có truy vấn quan hệ và giao dịch; cần đánh giá tính năng và chi phí thực tế. |
| “NewSQL là NoSQL có cú pháp SQL.” | NewSQL thường hướng đến SQL quan hệ và workload giao dịch; không được định nghĩa chỉ bằng cú pháp. |
| “Distributed SQL làm mọi câu JOIN nhanh hơn.” | JOIN liên partition có chi phí truyền mạng, dữ liệu trung gian và điều phối. |
| “Thêm replica là đã có distributed SQL.” | Replica có thể chỉ phục vụ đọc/HA; không có nghĩa engine cung cấp transaction SQL phân tán thống nhất. |
| “Multi-model luôn thay thế được các database chuyên dụng.” | Cần kiểm tra mức tối ưu của từng mô hình, transaction, index và tính năng phục vụ workload. |
| “Có JSON column là multi-model theo mọi định nghĩa.” | JSON column là một tính năng; khả năng mô hình hóa/truy vấn nhiều mô hình thực sự cần được xem riêng. |
| “ACID loại bỏ mọi vấn đề đồng bộ.” | ACID bảo đảm trong phạm vi transaction; event, cache, search, dịch vụ ngoài vẫn có ranh giới nhất quán khác. |
| “CAP chứng minh luôn phải chọn hai trong ba.” | CAP là giới hạn trong tình huống network partition với các định nghĩa cụ thể; không phải bảng phân hạng đơn giản cho toàn bộ SQL/NoSQL. |
| “Dữ liệu lớn phải dùng NoSQL.” | Workload, access pattern, mức nhất quán, chi phí và cách scale mới quyết định; SQL phân tán hoặc kho phân tích cũng có thể phù hợp. |

## 14. Bài tập vận dụng

**Bài tập 1 — Xác định trục phân loại.** Một sản phẩm hỗ trợ SQL, lưu dữ liệu trên năm node, có replication và transaction qua nhiều partition. Hãy chỉ ra những gì có thể suy ra từ mô tả, những gì chưa thể khẳng định về isolation level, khả năng chạy JOIN và nhãn NewSQL.

**Bài tập 2 — NoSQL với cú pháp SQL.** Một hệ wide-column dùng câu lệnh trông giống SELECT nhưng yêu cầu truy vấn dựa vào partition key và không hỗ trợ JOIN tổng quát như hệ quan hệ. Vì sao chỉ nhìn cú pháp không đủ để xếp nó vào distributed SQL?

**Bài tập 3 — Chọn nơi lưu đơn hàng.** Hệ có 200.000 đơn/ngày; 90% truy vấn đọc chi tiết theo orderId, 9% tra danh sách theo customerId, 1% báo cáo theo tháng. Hãy so sánh schema quan hệ và document, đề xuất index/partition, xác định các bất biến khi thanh toán, và thiết kế một phép thử contention.

**Bài tập 4 — Multi-model hay nhiều hệ?** Một ứng dụng cần document catalog và graph recommendation. Hãy xác định lợi ích và chi phí nếu chọn một engine đa mô hình so với dùng document database + graph database độc lập. Đặc biệt xem xét cách cập nhật cạnh quan hệ khi một tài khoản bị xóa.

**Bài tập 5 — Khi phân tán không miễn phí.** Hai dịch vụ ở hai khu vực địa lý ghi cùng một khóa tồn kho. Hãy mô tả các tình huống mạng bất thường, sự lựa chọn về phản hồi khi lỗi, và vì sao transaction trên nhiều node có thể làm độ trễ lớn hơn.

**Bài tập 6 — Đọc một tuyên bố marketing.** Nhà cung cấp nói sản phẩm “NoSQL, SQL-compatible, ACID, serverless, multi-model, globally distributed”. Hãy lập một danh sách câu hỏi kỹ thuật để kiểm tra mô hình, mức tương thích SQL, ranh giới transaction, consistency, vùng triển khai, quyền dữ liệu và chi phí khi có hot key.

Khi giải bài tập, nên viết theo chuỗi **yêu cầu nghiệp vụ → access patterns → bất biến giao dịch → mô hình dữ liệu → cách phân tán và truy vấn → quan sát khi tải/lỗi**. Chuỗi này có thể đưa đến SQL truyền thống, một hệ NoSQL chuyên biệt, distributed SQL, multi-model hoặc kết hợp nhiều hệ. Giá trị của lựa chọn nằm ở khả năng giữ đúng các yêu cầu đã định và chi phí có thể kiểm soát, chứ không nằm ở việc gắn được nhiều nhãn công nghệ.
