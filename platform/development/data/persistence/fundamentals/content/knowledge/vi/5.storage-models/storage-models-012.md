# Giới hạn của việc chọn công nghệ chỉ theo nhãn SQL hoặc NoSQL

> **Chương:** Mô hình lưu trữ  
> **Module:** DATA_PERSISTENCE_FUNDAMENTALS  
> **Bối cảnh:** Thiết kế persistence cho ứng dụng Java dựa trên mô hình dữ liệu, truy vấn, chỉ mục, giao dịch, cô lập và kiểm soát đồng thời; đồng thời cân nhắc lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng.

## 1. Tình huống mở đầu: “Cứ chọn NoSQL để mở rộng” có đủ không?

Một nhóm phát triển sàn thương mại điện tử chuẩn bị thiết kế nơi lưu đơn hàng. Có hai ý kiến:

- “Đơn hàng quan trọng nên cứ chọn **SQL**, vì NoSQL không có giao dịch.”
- “Hệ thống sẽ nhiều người dùng nên phải chọn **NoSQL**, vì SQL không mở rộng được.”

Cả hai đều là **kết luận quá sớm**. “SQL” thường gợi tới cơ sở dữ liệu quan hệ và ngôn ngữ truy vấn SQL; “NoSQL” là nhãn rất rộng, có thể chỉ kho tài liệu, khóa–giá trị, wide-column hay đồ thị. Nhưng tính nhất quán, khả năng giao dịch, mức cô lập, mô hình phân phối, giới hạn truy vấn và chi phí vận hành là **đặc tính của sản phẩm, phiên bản, cấu hình và cách triển khai cụ thể** — không thể suy ra đầy đủ từ nhãn.

Ví dụ, hệ thống đơn hàng có thể cần:

1. Tạo đơn và trừ tồn kho trong một đơn vị giao dịch đúng đắn.
2. Đọc lịch sử đơn theo khách, thời gian và trạng thái.
3. Tích hợp tìm kiếm sản phẩm, phân tích doanh thu và hệ thống gợi ý.
4. Tiếp nhận đợt tăng tải mạnh trong chiến dịch bán hàng.
5. Khôi phục khi một nút ngừng hoạt động, mất kết nối hoặc xảy ra xóa nhầm.

Không có một câu trả lời “SQL hay NoSQL?” đủ để giải quyết cả năm yêu cầu. Bài này tập trung vào **phương pháp đặt câu hỏi và chọn công nghệ có kiểm chứng**, thay vì xếp hạng tuyệt đối hai nhóm nhãn.

Sau bài học, người học có thể:

- Giải thích vì sao SQL/NoSQL không phải phân loại đầy đủ về khả năng lưu trữ.
- Nhận diện khác biệt giữa **mô hình dữ liệu**, **ngôn ngữ truy vấn**, **giao dịch**, **mô hình nhất quán**, **cách phân phối** và **cam kết durability**.
- Chuyển một bài toán nghiệp vụ thành tiêu chí lựa chọn và thí nghiệm.
- Thiết kế ranh giới persistence trong Java mà không để phụ thuộc công nghệ che mất bất biến nghiệp vụ.
- Đánh giá rủi ro vận hành, migration, an toàn dữ liệu và chi phí dài hạn trước khi chốt kiến trúc.

## 2. “SQL” và “NoSQL” thực sự nói lên điều gì?

### 2.1. SQL trước hết là một ngôn ngữ

**SQL** (*Structured Query Language*) là ngôn ngữ dùng để khai báo, thao tác và truy vấn dữ liệu, đặc biệt phổ biến trong cơ sở dữ liệu quan hệ. Một hệ quản trị quan hệ thường có bảng, hàng, cột, khóa, ràng buộc và khả năng thực thi SQL.

Tuy nhiên, **có hỗ trợ cú pháp SQL không đồng nghĩa hai hệ thống có cùng ngữ nghĩa giao dịch hoặc kiến trúc lưu trữ**. Một hệ phân tích dạng cột, một cơ sở dữ liệu quan hệ truyền thống và một hệ SQL phân tán có thể đều chấp nhận SQL nhưng khác nhau đáng kể về:

- Độ trễ cho cập nhật từng bản ghi so với quét hàng tỷ bản ghi.
- Cách thực thi join, index, transaction và truy vấn phân tán.
- Cơ chế đồng bộ log, nhân bản, failover và phục hồi.
- Giới hạn đồng thời, loại workload tối ưu và cách tính chi phí.

Trong hội thoại kỹ thuật, “database SQL” thường được dùng như cách gọi tắt **cơ sở dữ liệu quan hệ**, nhưng khi so sánh kiến trúc cần nói rõ lớp đặc tính đang đề cập.

### 2.2. NoSQL là nhãn bao trùm nhiều mô hình

**NoSQL** không phải tên của một giao thức, một kiểu dữ liệu hay một bộ bảo đảm nhất quán duy nhất. Thuật ngữ thường được hiểu là *not only SQL* để nhấn mạnh những cách tổ chức dữ liệu ngoài mô hình quan hệ truyền thống.

| Nhóm mô hình | Tổ chức dữ liệu điển hình | Điểm thường phù hợp | Điều cần kiểm tra riêng |
| --- | --- | --- | --- |
| **Key–value** | Khóa → giá trị | Tra cứu đơn giản theo khóa, phiên, cache, trạng thái ngắn gọn | Tìm theo thuộc tính phụ, atomic operation, durability, TTL |
| **Document** | Document JSON/BSON hoặc tương đương | Đối tượng với cấu trúc lồng nhau, đọc theo aggregate | Index, join/lookup, cập nhật từng phần, transaction đa document |
| **Wide-column / column-family** | Hàng theo partition key và clustering key | Lượng ghi lớn, truy vấn được định hình theo khóa phân vùng | Hot partition, truy vấn ngoài khóa, consistency, tombstone |
| **Graph** | Đỉnh, cạnh, thuộc tính | Quan hệ nhiều bước, tìm đường đi, mạng lưới phụ thuộc | Độ sâu traversal, quy mô phân tán, transaction |
| **Time-series / event store** | Dữ liệu theo thời gian hoặc chuỗi sự kiện | Metrics, cảm biến, nhật ký biến đổi | Retention, cardinality, event ordering, khả năng query |

Bảng là **bản đồ khái niệm**, không phải lời hứa rằng mọi sản phẩm thuộc cùng nhóm có cùng tính năng. Một sản phẩm có thể hỗ trợ nhiều mô hình; một cơ sở dữ liệu quan hệ cũng có thể lưu JSON, làm full-text search hoặc hỗ trợ nhiều dạng index.

### 2.3. Các trục lựa chọn không nằm trên một đường thẳng

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ và workload"] --> B["Mô hình dữ liệu"]
    A --> C["Truy vấn và chỉ mục"]
    A --> D["Giao dịch, nhất quán, cô lập"]
    A --> E["Quy mô, phân phối, độ trễ"]
    A --> F["Độ bền và vận hành"]
    A --> G["Bảo mật, migration, chi phí"]
    B --> H["Đánh giá sản phẩm + cấu hình cụ thể"]
    C --> H
    D --> H
    E --> H
    F --> H
    G --> H
    H --> I["Thử nghiệm bằng dữ liệu đại diện"]
    I --> J["Quyết định và ghi rõ giới hạn"]
~~~

SQL/NoSQL có thể được dùng để **lọc ứng viên ban đầu**, nhưng không thay thế bất kỳ nhánh đánh giá nào trong sơ đồ.

## 3. Những ngộ nhận phổ biến khi chỉ nhìn nhãn

| Nhận định vội vàng | Vì sao không đủ cơ sở? | Câu hỏi đúng hơn |
| --- | --- | --- |
| “SQL không scale ngang.” | Có thể dùng replication, partitioning, sharding hoặc hệ SQL phân tán; mức độ hỗ trợ và chi phí khác nhau | Muốn scale loại thao tác nào, đến bao nhiêu và trong giới hạn độ trễ nào? |
| “NoSQL không có transaction.” | Nhiều sản phẩm có atomicity ở mức key/document và một số có transaction đa bản ghi; ngữ nghĩa khác nhau | Transaction bao phủ bao nhiêu thực thể/partition, mức cô lập và chi phí là gì? |
| “Schema-less nghĩa là không cần schema.” | Ứng dụng vẫn cần hiểu cấu trúc, kiểu và phiên bản dữ liệu; dữ liệu không hợp lệ vẫn có thể gây lỗi | Ai xác thực và triển khai thay đổi schema, dữ liệu cũ được đọc ra sao? |
| “SQL luôn strong consistency.” | Cần xét isolation, đọc từ replica, cấu hình đồng bộ và kiểu giao dịch | Ai được phép đọc dữ liệu cũ, sau commit nhìn thấy giá trị nào? |
| “NoSQL luôn nhanh hơn.” | Độ trễ phụ thuộc mẫu truy cập, index, dữ liệu, mạng, tải và cấu hình | Truy vấn nào nhanh hơn ở p95/p99 với cùng workload? |
| “Dùng document thì không cần join.” | Có thể cần truy vấn xuyên document hoặc chấp nhận trùng lặp dữ liệu | Aggregate nào được đọc/ghi cùng nhau và cập nhật ở bao nhiêu nơi? |
| “Chỉ có SQL mới đảm bảo dữ liệu chính xác.” | Tính đúng đắn phụ thuộc thiết kế, ràng buộc, giao dịch và xử lý lỗi | Bất biến nghiệp vụ nào phải được bảo vệ, bằng cơ chế nào? |
| “NoSQL phù hợp mọi dữ liệu lớn.” | “Lớn” có thể là nhiều byte, nhiều request, nhiều quan hệ hoặc nhiều tổ chức thuê | Tài nguyên/giới hạn thực tế là lưu trữ, CPU, hot key hay mạng? |

Một nhãn có thể gợi ý **triết lý thiết kế ban đầu**; không được biến nó thành bằng chứng về một tính năng chưa kiểm tra.

## 4. Bắt đầu từ mô hình dữ liệu và bất biến nghiệp vụ

Xét hệ thống bán hàng với các thực thể:

~~~text
Customer 1 --- N Order
Order    1 --- N OrderLine
Product  1 --- N OrderLine
Order    1 --- N PaymentAttempt
~~~

**Dữ liệu** có quan hệ nhiều chiều, nhưng cách **người dùng truy cập và cập nhật** mới giúp quyết định nên lưu từng phần như thế nào.

### 4.1. Khi mô hình quan hệ là lựa chọn dễ lý giải

Một thiết kế quan hệ có thể gồm:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_minor BIGINT NOT NULL CHECK (unit_price_minor >= 0)
);
~~~

Ví dụ rút gọn để minh họa khóa ngoại và `CHECK`; hệ thống thật cần thiết kế tiền tệ, khóa sản phẩm, chính sách sửa giá, thời điểm và các ràng buộc khác. Điểm mạnh của mô hình quan hệ thường là các **quan hệ tường minh**, khả năng liên kết qua query và ràng buộc ở tầng database.

Nếu nghiệp vụ thường hỏi:

- Đơn hàng nào của một khách có trạng thái `PAID` trong tháng?
- Có bao nhiêu sản phẩm trong các đơn đã giao?
- Doanh thu theo nhóm khách, nhóm sản phẩm, thời gian?

thì SQL/join/aggregate có thể diễn đạt tự nhiên. Tuy nhiên, chi phí thực thi phải được kiểm tra bằng index và kế hoạch truy vấn; quan hệ rõ không đồng nghĩa truy vấn luôn rẻ.

### 4.2. Khi document có thể khớp aggregate

Nếu một request thường lấy toàn bộ đơn cùng các dòng hàng, có thể lưu thành một document:

~~~json
{
  "id": "ORDER-1001",
  "customerId": "C-42",
  "status": "SUBMITTED",
  "createdAt": "2026-11-20T08:30:00Z",
  "currency": "VND",
  "lines": [
    {"productId": "P-1", "quantity": 2, "unitPriceMinor": 50000},
    {"productId": "P-2", "quantity": 1, "unitPriceMinor": 80000}
  ]
}
~~~

Document đó thể hiện rõ đơn hàng là một **aggregate**: nhiều thuộc tính thường được đọc/ghi cùng nhau. Một số hệ document cung cấp cập nhật nguyên tử trên **một document**, giúp giữ bất biến nội bộ document mà không cần giao dịch đa document trong trường hợp phù hợp.

Đổi lại, cần hỏi:

1. Có nhiều tác nhân cập nhật từng dòng hàng độc lập không?
2. Document có phát triển không giới hạn, vượt giới hạn kích thước hoặc gây chi phí ghi lớn không?
3. Giá sản phẩm và tên sản phẩm có được sao chép vào nhiều đơn không? Nếu có, dữ liệu nào là **snapshot lịch sử** và dữ liệu nào phải đồng bộ?
4. Cần tìm “tất cả đơn chứa sản phẩm P-1, của khách ở một tỉnh, trong tháng” thường xuyên không?
5. Cập nhật trạng thái đơn có cần **nguyên tử với tồn kho và thanh toán ở nguồn khác** không?

Document phù hợp một đường đọc không có nghĩa nó đáp ứng tự động mọi bất biến xuyên hệ thống.

### 4.3. Chọn aggregate theo phạm vi thay đổi nhất quán

Một cách suy nghĩ hữu ích:

> Những dữ liệu nào phải thay đổi cùng nhau để một bất biến nghiệp vụ luôn đúng?

Một đơn và các dòng hàng có thể thuộc cùng aggregate. Nhưng **tồn kho của sản phẩm** được nhiều đơn cùng tranh chấp; nhét toàn bộ tồn kho vào một document đơn hàng không giải quyết xung đột và không tạo ra nguồn sự thật duy nhất.

Khi chọn mô hình lưu trữ, cần xác định **transaction boundary** và **aggregate boundary**. Tên SQL/NoSQL không thay hai quyết định này.

## 5. Quyết định bằng các mẫu đọc thực tế

Liệt kê những query bắt buộc trước khi chọn công nghệ:

| Use case | Mẫu truy cập | Câu hỏi phải thử |
| --- | --- | --- |
| Xem đơn theo ID | Point lookup | Có tra cứu trực tiếp theo khóa, độ trễ p99 bao nhiêu? |
| Liệt kê 20 đơn gần nhất của khách | Filter + sort + pagination | Index hỗ trợ điều kiện khách/thời gian không? |
| Tìm tất cả đơn chứa sản phẩm | Quan hệ nhiều-nhiều / secondary index | Query cần join, fan-out hay một index riêng? |
| Tổng hợp doanh thu quý | Scan/aggregate | OLTP chịu được không, hay cần hệ phân tích? |
| Tìm kiếm sản phẩm theo từ | Full-text search | Engine/index nào thực sự hỗ trợ yêu cầu tìm kiếm? |
| Xem quan hệ giới thiệu nhiều cấp | Graph traversal | Độ sâu traversal, độ trễ và fan-out ra sao? |
| Lấy vị trí mới nhất từ thiết bị | Latest value theo device | Partition key, thời gian lưu và lịch ghi ra sao? |

**Một yêu cầu “đọc nhiều” chưa đủ.** Đọc theo khóa duy nhất khác đọc theo nhiều điều kiện động; đọc hàng mới nhất khác tổng hợp nhiều năm dữ liệu.

### 5.1. Thiết kế index và query đồng thời

Với quan hệ, ví dụ:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Một index ghép như `(customer_id, created_at DESC, id DESC)` có thể phù hợp; phải kiểm chứng theo hệ quản trị cụ thể, phân bố dữ liệu và tỷ lệ ghi. Trong mô hình document, vẫn cần thiết kế chỉ mục hỗ trợ filter/sort tương đương. Trong wide-column store, thường phải định hình partition/clustering key theo truy vấn dự kiến ngay từ đầu.

**Lỗi thiết kế thường gặp:** chọn database theo nhãn, sau đó phát hiện truy vấn quan trọng cần quét nhiều partition, đọc tràn bộ nhớ hoặc gọi một chuỗi query từ ứng dụng Java để tự join.

### 5.2. Query flexibility cũng có chi phí

Nếu sản phẩm cần hàng trăm bộ lọc và báo cáo chưa biết trước, khả năng truy vấn linh hoạt quan trọng. Tuy nhiên, một query engine mạnh vẫn cần index/thống kê/tài nguyên để thực thi tốt; truy vấn phân tán thường có chi phí mạng và shuffle.

Ngược lại, nếu 95% request là tra cứu theo ID và mô hình không đổi, một hệ key–value có thể đơn giản, hiệu quả. Nhưng nếu tuần sau xuất hiện yêu cầu “lọc theo năm thuộc tính và sắp xếp”, có thể phải thêm **secondary index, search service hoặc dữ liệu dẫn xuất**. Chi phí đổi yêu cầu cần nằm trong quyết định ban đầu.

## 6. Quyết định bằng mẫu ghi và kiểm soát đồng thời

Hãy phân biệt ít nhất bốn loại ghi:

1. **Append-only:** thêm sự kiện hoặc record mới; ít cập nhật tại chỗ.
2. **Update theo khóa:** sửa một bản ghi hoặc document độc lập.
3. **Ghi có điều kiện:** ví dụ trừ tồn kho nếu còn đủ.
4. **Giao dịch đa thực thể:** tạo đơn, giảm tồn, ghi khoản thanh toán hoặc outbox.

Các loại này có yêu cầu khác nhau về tranh chấp, atomicity, rollback, retry và độ trễ.

### 6.1. Atomicity một bản ghi không phải atomicity xuyên nhiều bản ghi

Nếu một hệ bảo đảm cập nhật một document là nguyên tử, điều đó **không mặc nhiên** đồng nghĩa cập nhật đồng thời document đơn và document tồn kho là nguyên tử. Một hệ khác có thể có transaction đa document, nhưng vẫn phải đo chi phí, giới hạn và tình huống lỗi của tính năng đó.

Ở phía SQL, transaction đa bảng là khả năng quen thuộc của nhiều hệ quan hệ, nhưng phải biết:

- Mức cô lập và những hiện tượng mà nó cho phép.
- Khi nào câu lệnh lock, giữ lock bao lâu và có deadlock không.
- Commit được xác nhận khi nào, kết quả có thể không rõ nếu mất mạng không.
- Giao dịch có mở rộng xuyên shard/nút không, và phí giao tiếp là bao nhiêu.

**Cần đặt yêu cầu transaction cụ thể trước** rồi kiểm tra sản phẩm có đáp ứng; không thể đi theo chiều ngược lại từ tên nhãn.

### 6.2. Ví dụ bất biến tồn kho

Một logic sai thường thấy:

~~~text
read available = 1
if available >= 1:
    write available = 0
    confirm order
~~~

Hai request có thể cùng đọc `1` rồi cùng xác nhận đơn. Ở database quan hệ có hỗ trợ thao tác cập nhật có điều kiện, hướng an toàn hơn:

~~~sql
UPDATE inventory
SET available_qty = available_qty - :quantity
WHERE product_id = :productId
  AND available_qty >= :quantity;
~~~

Ứng dụng phải kiểm tra **đúng một hàng được cập nhật**; nếu cập nhật đơn và tồn kho, tổ chức các thay đổi đó trong transaction theo yêu cầu nghiệp vụ. Với một công nghệ khác, cần tìm cơ chế **compare-and-set/conditional write**, transaction hoặc khóa với bảo đảm tương đương. Nếu không có cơ chế phù hợp, phải đổi mô hình xử lý, ví dụ một bộ điều phối ghi hoặc giới hạn số nguồn ghi.

Quan trọng: không được nhìn thấy cụm từ “eventual consistency” hay “ACID” rồi suy ra sẵn liệu thao tác trừ kho sẽ an toàn. Phải chứng minh **điểm kiểm tra và điểm ghi được bảo vệ nguyên tử**.

## 7. Consistency, isolation và durability không phải cùng một thuộc tính

Các thuật ngữ thường bị trộn lẫn:

| Thuộc tính | Ý nghĩa thực tế cần xác định | Ví dụ câu hỏi |
| --- | --- | --- |
| **Consistency** trong ACID | Transaction giữ những ràng buộc/invariant đã được hệ thống mô hình hóa | Có còn dòng hàng mồ côi sau commit không? |
| **Consistency** trong hệ phân tán | Quan hệ thứ tự/khả năng quan sát giữa các lần đọc và ghi | Sau khi ghi xong, client khác thấy giá trị mới khi nào? |
| **Isolation** | Các transaction đồng thời ảnh hưởng nhau ra sao | Có lost update, phantom hoặc write skew không? |
| **Durability** | Thay đổi đã cam kết tồn tại thế nào qua sự cố | Commit đã ghi log bền chưa, replica đã xác nhận chưa? |
| **Availability** | Hệ thống đáp ứng request ở điều kiện đang xét không | Khi mất một vùng mạng, thao tác ghi có tiếp tục không? |
| **Partition tolerance** | Xử lý được việc các nút không liên lạc đáng tin cậy | Khi mạng chia cắt, các nút còn lại hành xử thế nào? |

Một hệ được gọi “ACID” vẫn phải có thiết kế ràng buộc hợp lý. Database **không thể biết** quy tắc nghiệp vụ “không giao hàng trước khi thanh toán” nếu ứng dụng chưa kiểm tra hoặc mô hình hóa nó.

### 7.1. Strong consistency, eventual consistency và read-after-write

Trong hệ phân tán, ứng dụng phải mô tả điều người dùng được phép quan sát:

- **Đọc ngay sau ghi:** khách vừa xác nhận thanh toán cần thấy `PAID` ở trang tiếp theo?
- **Đọc từ vùng khác:** replica có thể chậm vài giây hay không?
- **Đọc trong một phiên:** người dùng có cần luôn thấy kết quả của chính lần ghi trước?
- **Thay đổi đồng thời:** nếu hai người cùng sửa một đối tượng, hệ thống chọn lỗi xung đột, thứ tự thắng hay merge?

Một số luồng chấp nhận dữ liệu cũ (ví dụ danh mục tham khảo), trong khi quyết định trừ tiền hoặc tồn kho thường cần điều kiện đồng thời nghiêm ngặt hơn. Có thể dùng **những mức cam kết khác nhau trên các đường đọc** nếu kiến trúc hỗ trợ.

### 7.2. CAP không phải bảng xếp hạng database

Định lý CAP nói về giới hạn trong hệ thống phân tán khi **xảy ra network partition**: không thể đồng thời bảo đảm cả một dạng nhất quán mạnh (thường diễn giải là linearizability cho thao tác liên quan) và khả năng mọi yêu cầu đến nút còn hoạt động đều nhận phản hồi thành công trong điều kiện phân vùng đó.

Điều CAP **không** nói:

- Rằng mọi hệ thống phải chọn sẵn hai trong ba tính chất theo nhãn cố định.
- Rằng một sản phẩm luôn “AP” hoặc “CP” cho mọi API, mọi cấu hình và mọi topology.
- Rằng hệ thống có độ trễ thấp thì sẽ nhất quán mạnh.
- Rằng chỉ cần CAP là có thể quyết định durability, transaction, vận hành và chi phí.

Cần hỏi chính xác: **khi hai vùng mất liên lạc, thao tác nào sẽ bị từ chối/chờ, thao tác nào được phép tiếp tục, và sau khi kết nối lại giải quyết xung đột ra sao?**

## 8. “Mở rộng” là mở rộng thành phần nào?

“Có nhiều dữ liệu” và “có nhiều request” là hai vấn đề khác nhau. Khi thiết kế, hãy đo:

| Nhu cầu | Ví dụ | Cơ chế có thể cần |
| --- | --- | --- |
| Dung lượng lưu tăng | 5 TB dữ liệu giao dịch | Partitioning, sharding, lưu trữ lạnh, retention |
| Read throughput tăng | 50.000 lượt xem/giây | Index, cache, read replica, phân phối truy vấn |
| Write throughput tăng | 20.000 sự kiện/giây | Batch/append log, partition key phù hợp, ingest pipeline |
| Một khóa bị ghi rất nhiều | Một sản phẩm flash sale | Điều phối/partition nóng, giảm tranh chấp, thay mô hình đếm |
| Truy vấn phân tích lớn | Quét nhiều năm lịch sử | Hệ phân tích cột, dữ liệu tổng hợp, tách OLAP |
| Địa lý trải rộng | Người dùng nhiều khu vực | Đặt dữ liệu gần người dùng, replication, lựa chọn consistency |

**Scale dọc** (máy lớn hơn) và **scale ngang** (thêm nút) đều có giới hạn chi phí và phức tạp. Không phải cứ sharding là mọi truy vấn tăng tuyến tính theo số nút: query xuyên shard, join, transaction phân tán và skew có thể tạo bottleneck mới.

### 8.1. Partition key quan trọng hơn nhãn

Giả sử một hệ thống phân vùng đơn hàng theo `customer_id`. Truy vấn lịch sử của một khách có thể cục bộ trên một partition, nhưng:

- Một khách rất lớn có thể tạo **hot partition**.
- Báo cáo tất cả đơn có `status = 'PAID'` sẽ phải truy cập nhiều partition.
- Nếu transaction cần cập nhật nhiều khách hoặc nhiều product, có thể cần phối hợp xuyên partition.

Với key–value hoặc document store, lựa chọn key kém có thể làm nghẽn hệ thống dù cụm máy có nhiều nút. Với cơ sở dữ liệu quan hệ sharded, vấn đề tương tự cũng xuất hiện. **Topology và phân bố khóa mới quyết định hành vi thực**, không phải tên họ công nghệ.

### 8.2. Capacity planning phải có đỉnh tải và tăng trưởng

Một yêu cầu lưu trữ có ích cần ghi:

~~~text
Read queries/s: trung bình và p95/p99 của độ trễ khi tải đỉnh
Write ops/s:    theo từng loại thao tác và số bản ghi bị tác động
Data volume:    số hàng/document, dung lượng và tốc độ tăng/ngày
Key skew:       top khóa nóng, tỷ lệ tải vào top 1% partition
Concurrency:    transaction đang chạy và thời gian giữ khóa
Recovery:       RPO/RTO, thử nghiệm failover/restore
~~~

Nếu nhóm chỉ nói “sau này có một triệu người dùng” mà không chuyển thành **mẫu đọc, ghi, phân bố và mức dịch vụ**, không thể chứng minh một sản phẩm phù hợp hơn sản phẩm khác.

## 9. Tốc độ của một query không đại diện cho hiệu năng hệ thống

Một benchmark chạy 100.000 lần `GET(key)` trên dữ liệu vừa cache trong RAM không nói nhiều về hệ thống phải:

- Tạo đơn và ghi nhiều bảng/document cùng transaction.
- Quét theo ngày và sắp xếp nhiều triệu record.
- Ghi log bền, đồng bộ replica và phục hồi sau restart.
- Phục vụ nhiều tenant với khóa nóng khác nhau.
- Kiểm tra phân quyền theo hàng hoặc tài liệu.

Cần đo **mixed workload** giống production, không chỉ một đường nhanh nhất của sản phẩm:

1. Dataset có số record, kích thước và phân bố khóa đại diện.
2. Tỷ trọng read/write và câu lệnh thật trên mỗi request.
3. Dữ liệu nóng/lạnh, tỷ lệ cache hit, secondary index.
4. p50/p95/p99 latency, throughput, lỗi, CPU, RAM, network và disk.
5. Tình huống compaction, checkpoint, backup, reindex, replica lag hoặc rebalance.
6. Hành vi khi một node mất kết nối, khi client timeout và khi retry.

Kết quả **p95 thấp trong điều kiện bình thường** vẫn chưa chứng minh đạt yêu cầu nếu độ trễ vọt lên khi backup, mất một node hoặc traffic tăng ngắn hạn.

## 10. Khả năng truy vấn còn gắn với lịch sử và nhu cầu phân tích

Một sản phẩm lưu tốt giao dịch hàng ngày (*OLTP*) chưa chắc phù hợp để chạy các báo cáo phải quét hàng tỷ sự kiện (*OLAP*).

Ví dụ một nền tảng giao hàng:

- **OLTP:** tài xế cập nhật trạng thái một kiện; khách đọc trạng thái hiện tại.
- **Phân tích:** thống kê tỷ lệ giao trễ trong 3 năm theo vùng, đơn vị vận chuyển, loại sản phẩm.
- **Tìm kiếm:** nhân viên hỗ trợ tìm theo nội dung ghi chú, số điện thoại hoặc một phần địa chỉ có phân quyền.
- **Lịch sử sự kiện:** kiểm toán mọi lần thay đổi trạng thái.

Bốn đường truy cập này khác nhau về index và độ trễ. Có thể dùng một hệ lưu đủ khả năng cho giai đoạn đầu; khi tải và tính năng tăng, cân nhắc tách hệ tìm kiếm hoặc phân tích.

**Đừng đặt tên SQL/NoSQL lên mọi nhu cầu và coi đó là một lựa chọn duy nhất.** Có khi câu hỏi thực sự là **OLTP hay OLAP**, **dữ liệu hiện tại hay lịch sử sự kiện**, **đọc theo khóa hay tìm kiếm toàn văn**, hoặc **một nguồn sự thật hay bản sao dẫn xuất**.

## 11. Schema cố định và schema linh hoạt đều phải tiến hóa

Một sơ đồ quan hệ tường minh có migration; document có trường linh hoạt hơn. Nhưng cả hai cần trả lời:

1. Phiên bản ứng dụng cũ đọc bản ghi do ứng dụng mới ghi thế nào?
2. Khi bỏ/đổi tên trường, những document/bản ghi lịch sử được xử lý ra sao?
3. Khi đổi kiểu `total` từ số thực sang Money có currency, các bản ghi cũ có đủ thông tin chuyển đổi không?
4. Khi thêm index/constraint, triển khai có gây block write/read không?
5. Khi một phiên bản đang chạy ghi dữ liệu theo quy tắc cũ, có phá dữ liệu mới không?

### 11.1. Ví dụ tiến hóa dữ liệu đơn hàng

Phiên bản đầu:

~~~json
{"orderId": "O-1", "total": 250000}
~~~

Phiên bản sau:

~~~json
{
  "orderId": "O-1",
  "total": {"amountMinor": 250000, "currency": "VND"},
  "schemaVersion": 2
}
~~~

Không phải mọi record cũ đều chắc chắn dùng VND. Nếu hệ thống từng hỗ trợ đa tiền tệ nhưng không lưu mã tiền, việc tự gán `VND` có thể gây hỏng dữ liệu nghiệp vụ. Cần **xác định ý nghĩa lịch sử**, migrate theo nguồn đáng tin, hoặc đánh dấu những record cần đối soát.

### 11.2. “Schema-less” không có nghĩa “validation-less”

Trong Java, DTO, serializer, domain model và consumer vẫn kỳ vọng một cấu trúc nhất định. Nếu thiếu validation phía application/database, hai record cùng collection có thể dùng `quantity` lúc là chuỗi, lúc là số; query tổng hợp và migration trở nên khó dự đoán.

Schema nên được hiểu như **hợp đồng giữa dữ liệu, ứng dụng và các bên tiêu thụ**. Hợp đồng có thể được thực thi ở database, tại API, qua schema registry hoặc phối hợp nhiều nơi. Không nên chọn công nghệ chỉ theo mức nghiêm ngặt biểu diễn schema.

## 12. Java: ranh giới persistence không nên phụ thuộc vào khẩu hiệu công nghệ

Application service nên phát biểu **nghiệp vụ và yêu cầu lưu trữ**, còn adapter chịu trách nhiệm hiện thực bằng sản phẩm được chọn.

Ví dụ Java 17+:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

record OrderLine(UUID productId, int quantity, BigDecimal unitPrice) {}

record Order(UUID id, UUID customerId, String status,
             long version, List<OrderLine> lines) {}

interface OrderRepository {
    Optional<Order> findById(UUID id);

    // Chỉ hoàn tất khi thay đổi được commit theo hợp đồng triển khai.
    // Trả false nếu version/trạng thái đã khác điều kiện mong đợi.
    boolean saveIfVersionMatches(Order proposed, long expectedVersion);
}

final class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    void cancelDraft(UUID orderId, UUID actingCustomerId) {
        Order current = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Khong tim thay don"));

        if (!current.customerId().equals(actingCustomerId)) {
            throw new SecurityException("Khong co quyen huy");
        }
        if (!"DRAFT".equals(current.status())) {
            throw new IllegalStateException("Trang thai khong cho phep");
        }

        Order proposed = new Order(
                current.id(), current.customerId(), "CANCELLED",
                current.version() + 1, current.lines());

        if (!repository.saveIfVersionMatches(proposed, current.version())) {
            throw new java.util.ConcurrentModificationException(
                    "Don da thay doi; can tai lai");
        }
    }
}
~~~

Ví dụ cho thấy **ngữ nghĩa từ phía caller**:

- Phải kiểm tra quyền và trạng thái nguồn.
- Phải tránh ghi đè khi có request khác cập nhật version.
- Chỉ công bố kết quả khi lời hứa `saveIfVersionMatches` của adapter được thỏa.

Khi viết adapter, nhóm phải **chứng minh** câu lệnh ghi của công nghệ được chọn đáp ứng hợp đồng này. Với hệ quan hệ có thể dùng `UPDATE ... WHERE id=? AND version=?` trong transaction; với kho document hoặc key–value có thể cần conditional write/CAS hoặc API transaction tương ứng.

**Giới hạn của abstraction:** Nếu cần tạo đơn + trừ tồn kho + ghi outbox trong **một transaction**, một hàm `save` đơn lẻ là chưa đủ. Interface phải thể hiện ranh giới giao dịch thật, hoặc thiết kế workflow khác. Không che giấu khác biệt nền tảng sau một interface hứa điều mà adapter không làm được.

### 12.1. Tránh ép domain theo kiểu dữ liệu của vendor

Giữa domain và persistence có thể cần mapper:

~~~text
Business command
       |
       v
Java domain model + invariants
       |
       v
Repository port / transaction contract
       |
       +---- JDBC/JPA adapter -> relational database
       |
       +---- Document adapter -> document store
       |
       +---- Conditional-write adapter -> key-value store
~~~

Không phải mọi adapter đều thay thế nhau dễ dàng: điều kiện query, mức isolation, transaction đa entity, index và khả năng tìm kiếm có thể khác. Mục đích của ranh giới kiến trúc là **làm rõ sự phụ thuộc**, không phải hứa rằng đổi database chỉ cần đổi một dependency.

## 13. Lỗi kết nối, retry và “ghi thành công” phải được định nghĩa

Giả sử ứng dụng gửi yêu cầu commit, rồi mất kết nối trước khi nhận phản hồi. Không thể mặc nhiên kết luận transaction **chắc chắn thất bại**. Nó có thể đã commit trên server.

Hệ thống cần:

- **Định danh yêu cầu ổn định** để truy vấn kết quả khi retry.
- **Ràng buộc duy nhất hoặc conditional write** để tránh tạo trùng.
- **Chính sách lỗi có thể retry** được tài liệu hóa cho sản phẩm và driver.
- **Thời điểm xác nhận ghi** rõ ràng: đã nhận vào queue, đã ghi local log, đã đồng bộ replica hay đã commit theo hợp đồng?
- **Quan sát được** độ trễ, timeout, replica lag, số request retry và các lỗi mâu thuẫn.

### 13.1. Ví dụ idempotency

Client gửi:

~~~json
{
  "idempotencyKey": "REQ-903",
  "customerId": "C-42",
  "items": [{"productId": "P-1", "quantity": 1}]
}
~~~

Nếu request đầu đã tạo đơn nhưng response mất trên đường mạng, request thứ hai với cùng khóa cần **tìm lại kết quả hoặc xử lý theo cơ chế idempotency**, không tự tạo đơn khác. Trong hệ quan hệ có thể dùng unique constraint trên khóa; trong hệ key–value/document cần cơ chế ghi có điều kiện với bảo đảm đủ mạnh. Nếu việc ghi khóa và tạo đơn ở hai nơi không nguyên tử, hệ thống phải thiết kế lại ranh giới để tránh tình huống một bên thành công, bên kia thất bại.

Nhãn SQL/NoSQL **không trả lời** đầy đủ câu hỏi này; lời giải phải dựa trên giao dịch và bảo đảm ghi thực tế.

## 14. Backup, restore, HA và bảo mật cũng là yêu cầu chọn công nghệ

Một database chạy nhanh nhưng không đáp ứng yêu cầu phục hồi có thể là lựa chọn sai cho dữ liệu tài chính.

| Tiêu chí | Câu hỏi cần xác minh |
| --- | --- |
| **Durability** | Commit được ghi tới đâu; mất điện/mất nút có thể mất dữ liệu nào? |
| **Backup** | Có backup nhất quán, incremental, PITR hoặc snapshot theo yêu cầu không? |
| **Restore** | Đã thử phục hồi đầy đủ schema, dữ liệu, index và quyền chưa? |
| **RPO** | Tối đa chấp nhận mất bao nhiêu dữ liệu, tính từ thời điểm nào? |
| **RTO** | Mục tiêu khôi phục dịch vụ trong bao lâu? |
| **HA / failover** | Khi primary lỗi, ai được nâng cấp, có split-brain không? |
| **Mã hóa và quyền** | Có TLS, encryption at rest, RBAC, phân tách tenant, audit không? |
| **Tuân thủ và lưu giữ** | Có cơ chế xóa, retention, kiểm soát vùng dữ liệu không? |
| **Quan sát hệ thống** | Có metric query, lock, compaction, replication lag và backup status không? |

**Replication không thay thế backup.** Nếu ứng dụng xóa nhầm một record, thay đổi đó có thể được nhân sang các replica. Một bản sao đồng bộ hỗ trợ sẵn sàng nhưng không tự tạo điểm phục hồi lịch sử.

**Backup không tự chứng minh restore hoạt động.** Cần thực hành khôi phục trên môi trường kiểm thử, kiểm tra thời gian phục hồi và toàn vẹn dữ liệu, không chỉ xem job backup báo thành công.

### 14.1. Tính năng bảo mật không đồng nhất theo nhãn

SQL không tự đảm bảo ứng dụng tránh SQL injection; cần query tham số hóa, phân quyền và quản lý bí mật. NoSQL cũng có thể gặp **injection qua cấu trúc query** hoặc quyền quá rộng nếu ứng dụng đưa input không tin cậy vào biểu thức truy vấn.

Đối với dữ liệu nhiều tenant, xác minh việc tách dữ liệu giữa các tenant trong **mọi** đường đọc, ghi, export, search index và backup. Nếu dùng mã hóa ở tầng ứng dụng, kiểm tra ảnh hưởng đến khả năng index và tìm kiếm.

## 15. Chi phí vận hành, đội ngũ và khả năng rời bỏ công nghệ

Tổng chi phí sở hữu không chỉ là giá máy chủ hoặc dịch vụ mỗi tháng:

~~~text
TCO ≈ compute + storage + network + backup
      + vận hành/giám sát + nhân lực
      + độ phức tạp ứng dụng
      + migration + rủi ro gián đoạn
~~~

Một công nghệ có latency rất thấp cho key lookup nhưng yêu cầu đội ngũ tự xây ba hệ thống index phụ có thể đắt hơn giải pháp hỗ trợ truy vấn cần thiết ngay từ đầu. Ngược lại, dùng một hệ quan hệ lớn để lưu lượng sự kiện append-only khổng lồ với retention ngắn cũng có thể tạo chi phí index/log không cần thiết.

Cần cân nhắc:

- **Độ thành thạo của nhóm:** vận hành replication, upgrade, phân vùng và điều tra sự cố có dễ không?
- **Dịch vụ quản lý:** nhà cung cấp tự xử lý những gì, người dùng vẫn chịu trách nhiệm những gì?
- **Giới hạn dịch vụ:** throughput, kích thước item, transaction, index, thời gian giữ dữ liệu, quota/giá truy vấn.
- **Chi phí egress và di chuyển:** chuyển toàn bộ dữ liệu, thay đổi API và xử lý lịch sử có khó không?
- **Khả năng kiểm thử:** có staging sát production, tài liệu driver và khả năng gây lỗi để thử failover không?
- **Hệ sinh thái Java:** driver, JDBC/JPA support, telemetry, security integration và tooling migration có phù hợp không?

Nhãn SQL hoặc NoSQL không cho biết **đội ngũ có vận hành hệ thống tin cậy được hay không**.

## 16. Một hệ thống có thể dùng nhiều mô hình — nhưng phải có nguồn sự thật

Một kiến trúc có thể sử dụng:

- Cơ sở dữ liệu giao dịch giữ **đơn hàng và thanh toán chính thức**.
- Search index phục vụ **tìm kiếm văn bản và lọc sản phẩm**.
- Cache phục vụ **dữ liệu đọc nhiều, có thể tái tạo**.
- Kho phân tích phục vụ **báo cáo lịch sử**.
- Object storage giữ **hóa đơn hoặc tệp đính kèm**.

~~~mermaid
flowchart TD
    A["Java application"] --> B[("Kho giao dịch - nguồn sự thật")]
    A --> C[("Cache - bản sao có thể dựng lại")]
    B --> D["Outbox / sự kiện thay đổi"]
    D --> E["Consumer đồng bộ có kiểm soát"]
    E --> F[("Search index")]
    E --> G[("Kho phân tích")]
    A --> H[("Object storage cho tệp")]
~~~

Mô hình này gọi chung là **polyglot persistence**. Nó có thể giúp mỗi loại truy vấn dùng công cụ phù hợp, nhưng mang theo:

1. Chi phí đồng bộ dữ liệu và xử lý sự kiện lặp/đến muộn.
2. Quy tắc read-after-write khi search index chưa cập nhật.
3. Quyền truy cập và xóa dữ liệu phải được thực thi ở mọi bản sao.
4. Khả năng khôi phục search index và báo cáo từ nguồn chính khi cần.
5. Giới hạn về giao dịch: cập nhật ở nhiều hệ không tự nguyên tử với nhau.

**Không nên tạo nhiều công nghệ chỉ để “đúng xu hướng”.** Khi workload còn đơn giản và một hệ có thể đáp ứng rõ ràng, kiến trúc ít thành phần thường dễ vận hành, bảo mật và phục hồi hơn.

## 17. Ma trận quyết định: mô tả nhu cầu trước khi chấm điểm ứng viên

Giả sử nhóm phát triển ứng dụng quản lý đơn có ba ứng viên:

- **R:** cơ sở dữ liệu quan hệ giao dịch.
- **D:** kho document.
- **K:** kho key–value/wide-column.

Không gán điểm theo nhãn. Thay vào đó, định nghĩa tiêu chí, mức bắt buộc và cách kiểm chứng:

| Tiêu chí | Mức yêu cầu của bài toán | Cách kiểm chứng |
| --- | --- | --- |
| Đơn và tồn kho nhất quán | **Bắt buộc**: không oversell theo quy tắc đã định | Test cạnh tranh và rollback theo transaction boundary |
| Lịch sử đơn theo khách | **Bắt buộc**: 20 bản ghi mới nhất, có phân trang | Truy vấn với dữ liệu đại diện, p95/p99 và index |
| Thông báo thanh toán lặp | **Bắt buộc**: không ghi nhận hai lần | Idempotency test và lỗi mạng khi commit |
| Tăng đỉnh tải | Ví dụ 1.000 tạo đơn/giây | Mixed-load test với phân bố khóa thật |
| Báo cáo doanh thu tháng | Có thể chạy nền | Đo query hoặc pipeline phân tích |
| Backup/restore | RPO ≤ 5 phút; RTO ≤ 1 giờ (*giả định*) | Diễn tập recovery và xác nhận dữ liệu |
| Migration | Hỗ trợ hai phiên bản ứng dụng khi rollout | Test đọc/ghi song song trong giai đoạn chuyển tiếp |
| TCO và kỹ năng đội | Không vượt ngân sách/vận hành thực tế | Ước lượng nguồn lực, giá và runbook |

Các số về tải và thời gian khôi phục trong bảng chỉ là **giả định minh họa**. Một nhóm phải thay bằng mục tiêu được chủ sở hữu nghiệp vụ chấp thuận.

### 17.1. Phân biệt “không đạt điều kiện bắt buộc” với “điểm hiệu năng thấp”

Nếu một ứng viên không đáp ứng bất biến giao dịch mà không có thiết kế thay thế được chấp thuận, **không nên cộng điểm tốc độ để bù lại**. Những yêu cầu như bảo mật, độ bền, tính đúng đắn nghiệp vụ và tính tuân thủ có thể là **điều kiện loại**.

Chỉ sau khi ứng viên vượt qua các điều kiện bắt buộc mới so sánh chi phí, độ trễ, công sức vận hành và khả năng mở rộng.

### 17.2. Quy trình thử nghiệm có thể tái hiện

1. Chọn 5–10 luồng nghiệp vụ quan trọng nhất.
2. Ghi request/s, transaction/s, tần suất ghi nóng, query, kích thước dữ liệu và phân bố khóa.
3. Mô hình hóa bất biến, quyền thao tác và mức consistency cần có.
4. Thiết kế schema/document/key cho từng ứng viên **theo cách phù hợp với chính ứng viên**, không ép mọi hệ thành cùng một cấu trúc.
5. Viết thử một luồng end-to-end với Java adapter, bao gồm commit, timeout và retry.
6. Đo mixed workload, index, p95/p99 và việc thay đổi theo kích thước dữ liệu.
7. Gây lỗi có kiểm soát: mất kết nối, kill node, replica lag, restore và xung đột ghi.
8. Ghi rõ điều ứng viên **không** đáp ứng, các giả định và chi phí để khắc phục.
9. Chốt **quyết định có lý do** và điều kiện cần đánh giá lại khi workload thay đổi.

Không nên chỉ đo một lệnh `INSERT` hoặc `GET` rồi công bố giải pháp “nhanh hơn X lần” cho toàn hệ thống.

## 18. Tình huống thực hành: ba quyết định lưu trữ

### Tình huống A — Nền tảng đặt vé

Yêu cầu:

- Một ghế chỉ được bán cho một khách theo quy tắc giữ chỗ/thanh toán.
- Người mua có thể đổi hoặc hủy vé trước một hạn định.
- Có báo cáo doanh số và log phục vụ kiểm toán.
- Ứng dụng Java cần trả kết quả đáng tin khi có nhiều request cạnh tranh.

**Gợi ý phân tích:** Bất biến ghế duy nhất và chuyển trạng thái cần cơ chế giao dịch hoặc conditional update đủ mạnh. Mô hình quan hệ với ràng buộc duy nhất/cập nhật có điều kiện có thể là ứng viên ban đầu dễ triển khai và chứng minh; một hệ khác cũng có thể đáp ứng nếu cung cấp cùng mức bảo đảm với thiết kế thích hợp.

Không nên chọn chỉ theo “ứng dụng lớn nên NoSQL” hay “vì có tiền nên SQL”. Đặc tả chính xác **lúc ghế được giữ**, **bao lâu**, **khi nào thu tiền**, **khi nào giải phóng** mới quyết định mô hình transaction.

### Tình huống B — Thu thập telemetry từ thiết bị

Yêu cầu:

- Mỗi thiết bị gửi nhiều mẫu đo có timestamp.
- Ghi thường xuyên, ít cập nhật tại chỗ, phần lớn query là “giá trị gần đây của thiết bị X”.
- Dữ liệu thô chỉ giữ 30 ngày; báo cáo dài hạn dùng dữ liệu tổng hợp.
- Có thể chấp nhận độ trễ nhỏ khi một dashboard đọc dữ liệu mới nhất, nhưng không được nhầm đơn vị đo.

**Gợi ý phân tích:** Một kho tối ưu time-series, wide-column hoặc hệ quan hệ có partitioning phù hợp đều có thể là ứng viên; phải thử mô hình partition key, retention, batch ingest và query theo thời gian. Cần chuẩn hóa đơn vị, theo dõi dữ liệu đến trễ, duplicate event và lưu aggregate dài hạn.

Hệ này không nhất thiết cần cùng cơ chế transaction đa bảng như đặt vé. Nhưng vẫn cần độ bền phù hợp, chính sách chống trùng, bảo mật và khả năng restore.

### Tình huống C — Bổ sung tìm kiếm sản phẩm

Hệ thống hiện đã có database giao dịch và cần tìm theo từ khóa có xếp hạng, gợi ý, bộ lọc nhiều thuộc tính.

**Gợi ý phân tích:** Trước khi chuyển toàn bộ dữ liệu sang hệ khác, đánh giá khả năng full-text/index của hệ hiện có và khối lượng thực tế. Nếu chọn search service riêng, phải định nghĩa nguồn sự thật, cơ chế đồng bộ, độ trễ cho phép và cách rebuild index.

## 19. Câu hỏi kiểm tra hiểu đúng

**Câu 1.** Một kho document hỗ trợ cập nhật nguyên tử một document. Có thể kết luận việc cập nhật đồng thời hai document “đơn hàng” và “tồn kho” luôn nguyên tử không?

**Trả lời:** Không. Cần cơ chế transaction đa document hoặc thiết kế workflow/conditional write chứng minh được bất biến nghiệp vụ; atomicity một document không tự mở rộng.

**Câu 2.** Một hệ quan hệ hỗ trợ SQL và transaction. Có thể bỏ qua thiết kế idempotency khi xử lý timeout gần lúc commit không?

**Trả lời:** Không. Client có thể không biết kết quả commit; cần định danh ổn định, ràng buộc duy nhất và cách tra cứu khi retry.

**Câu 3.** Dùng NoSQL “không có schema” thì có thể đổi trường `total` từ number sang object bất kỳ lúc nào không?

**Trả lời:** Không nên. Reader/consumer cũ có thể lỗi và dữ liệu lịch sử có thể mất ngữ nghĩa; cần chiến lược versioning và migration.

**Câu 4.** Một ứng viên cho tốc độ đọc theo khóa rất cao. Điều đó đã đủ để chọn cho hệ báo cáo quan hệ nhiều chiều chưa?

**Trả lời:** Chưa. Phải đo query/filter/aggregate thực tế, chi phí các index hoặc pipeline dẫn xuất và khả năng vận hành.

**Câu 5.** Đã bật replication thì có thể bỏ backup không?

**Trả lời:** Không. Xóa nhầm và lỗi logic có thể lan qua bản sao; cần cơ chế phục hồi lịch sử và thử restore.

**Câu 6.** Nếu một workload bắt buộc giao dịch nhiều thực thể và ứng viên không hỗ trợ trực tiếp, nhóm có thể vẫn chọn nó không?

**Trả lời:** Có thể, **chỉ nếu** một thiết kế thay thế (ví dụ tái cấu trúc aggregate hoặc workflow có bù trừ) chứng minh thỏa bất biến và được nghiệp vụ chấp thuận. Không được ngụy trang việc giảm cam kết nhất quán dưới tên gọi “tối ưu kiến trúc”.

## 20. Checklist trước khi quyết định công nghệ lưu trữ

- [ ] Đã ghi rõ **dữ liệu và bất biến nghiệp vụ** thay vì chỉ chọn nhãn SQL/NoSQL.
- [ ] Đã liệt kê query, index, bộ lọc, thứ tự, phân trang và báo cáo bắt buộc.
- [ ] Đã đo hoặc ước lượng tải đọc/ghi, đỉnh, tăng trưởng, hot key và phân bố tenant.
- [ ] Đã xác định transaction boundary, isolation, conditional write và cơ chế idempotency.
- [ ] Đã nêu rõ consistency của từng đường đọc, bao gồm read-after-write và replica lag.
- [ ] Đã kiểm chứng lời hứa durability, failover, backup/restore, RPO/RTO cho cấu hình sẽ triển khai.
- [ ] Đã xem xét quyền truy cập, encryption, audit và yêu cầu giữ/xóa dữ liệu.
- [ ] Đã có chiến lược schema/versioning/migration và kiểm thử tương thích reader/writer.
- [ ] Đã đánh giá driver, adapter, transaction mapping và observability trong Java.
- [ ] Đã thử **mixed workload** trên dữ liệu đại diện, không chỉ microbenchmark.
- [ ] Đã tính chi phí hạ tầng, vận hành, đào tạo, di chuyển và bản sao dẫn xuất.
- [ ] Đã ghi tài liệu quyết định với **lý do, giả định, giới hạn và thời điểm cần đánh giá lại**.

## 21. Tổng kết

**SQL và NoSQL là những nhãn định hướng, không phải hợp đồng kỹ thuật đầy đủ.** Chúng không tự chứng minh hệ thống sẽ có giao dịch đúng, truy vấn nhanh, mở rộng dễ, lưu bền an toàn hay vận hành rẻ.

Với ứng dụng Java, hãy đi từ **ngữ nghĩa và vòng đời dữ liệu → mẫu đọc/ghi → ràng buộc và giao dịch → yêu cầu nhất quán, độ bền và phục hồi → kiểm thử tải → chi phí vận hành**. Sau đó mới chọn **sản phẩm, phiên bản, cấu hình và mô hình triển khai** phù hợp. Khi cần nhiều hệ lưu trữ, hãy chỉ rõ nguồn sự thật và cách đồng bộ; khi chưa cần, giữ kiến trúc đơn giản sẽ giúp giảm rủi ro.

Lựa chọn có trách nhiệm không phải “SQL thắng NoSQL” hay ngược lại, mà là **chứng minh giải pháp đáp ứng các bất biến và hành vi thực tế của hệ thống**, kể cả khi dữ liệu tăng trưởng, có cạnh tranh đồng thời, nâng cấp schema hoặc gặp sự cố.
