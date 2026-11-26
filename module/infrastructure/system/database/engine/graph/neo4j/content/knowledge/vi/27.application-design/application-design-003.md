# Ranh giới giao dịch theo thao tác nghiệp vụ

## 1. Bắt đầu từ thao tác nghiệp vụ, không bắt đầu từ câu Cypher

Neo4j là cơ sở dữ liệu đồ thị theo mô hình **property graph**: node biểu diễn thực thể, relationship biểu diễn liên kết và property lưu dữ liệu của từng đối tượng. Khi một ứng dụng Java sử dụng Neo4j, một yêu cầu nghiệp vụ thường thay đổi **nhiều node, relationship và property**.

Ví dụ, thao tác **“đặt một đơn hàng gồm một sản phẩm”** có thể cần:

1. Xác định khách hàng và sản phẩm.
2. Tạo node `Order`.
3. Tạo node `OrderLine` để giữ số lượng và đơn giá tại thời điểm đặt.
4. Nối `Customer-[:PLACED]->Order`.
5. Nối `Order-[:HAS_LINE]->OrderLine-[:FOR_PRODUCT]->Product`.
6. Ghi sự kiện cần phát để hệ thống khác biết đơn mới được tạo, nếu ứng dụng có yêu cầu tích hợp.

Nếu chỉ tạo được Order mà thiếu OrderLine hoặc relationship nối khách hàng, graph có thể trở thành một trạng thái **nghiệp vụ không hợp lệ**. Ranh giới transaction phải phản ánh điều kiện này.

> **Nguyên tắc chính:** Một transaction nên bao trùm **những thay đổi trong cùng Neo4j database bắt buộc phải thành công hoặc thất bại cùng nhau** để một thao tác nghiệp vụ tạo ra trạng thái hợp lệ.

Không đồng nhất “một transaction = một câu Cypher”, cũng không mặc định “một HTTP request = một transaction duy nhất”. Một thao tác có thể cần nhiều câu lệnh trong cùng transaction; ngược lại, một quy trình lớn gồm nhiều nghiệp vụ và nhiều hệ thống không nên cố giữ một transaction Neo4j mở trong suốt quá trình.

## 2. Ba khái niệm cần phân biệt

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Thao tác nghiệp vụ** | Người dùng/hệ thống đang yêu cầu thực hiện điều gì? | Đặt đơn, chuyển quyền, hủy quan hệ thành viên |
| **Bất biến nghiệp vụ** (*business invariant*) | Điều gì phải luôn đúng sau khi commit? | Mỗi Order có khách hàng và các dòng hàng hợp lệ |
| **Ranh giới transaction** | Những thay đổi nào phải được Neo4j commit hoặc rollback cùng nhau? | Tạo Order, OrderLine và các relationship cần thiết |

Một thao tác nghiệp vụ có thể gồm nhiều bước kỹ thuật; transaction được chọn dựa trên **những bất biến cần bảo toàn**, không phải số câu lệnh.

### 2.1. Tính nguyên tử không đồng nghĩa mọi quy tắc tự đúng

Transaction đảm bảo **atomicity**: các thay đổi của một transaction được commit như một đơn vị hoặc không được commit khi transaction rollback. Nhưng transaction không tự biết rằng số lượng hàng phải lớn hơn 0, một khách hàng chỉ được gia nhập nhóm một lần, hay tài khoản không được âm điểm.

Các quy tắc này còn cần:

- Kiểm tra và chuẩn hóa input.
- Constraint như uniqueness trên khóa nghiệp vụ.
- Cypher biểu diễn đúng điều kiện.
- Cơ chế xử lý cạnh tranh ghi hoặc kiểm soát version khi nhiều request cùng sửa dữ liệu.
- Kiểm thử đồng thời và xử lý lỗi/retry.

**Atomicity** giải quyết “cùng commit hay cùng rollback”; **concurrency correctness** giải quyết “hai transaction cùng chạy có giữ đúng bất biến hay không?”. Hai mục tiêu liên quan nhưng không thay thế nhau.

## 3. Cách xác định ranh giới cho một use case

Trước khi viết repository/service, hãy trả lời năm câu hỏi:

1. **Điểm bắt đầu và kết thúc nghiệp vụ là gì?** Ví dụ “đặt đơn thành công” nghĩa là đơn đã tồn tại cùng các dòng hàng cần thiết, chưa nhất thiết đã gửi email.
2. **Những thực thể nào bị thay đổi?** Node nào, relationship nào, property nào? Có tài nguyên ở ngoài Neo4j không?
3. **Nếu bước giữa thất bại thì được phép giữ phần đã làm không?** Nếu không, các bước ghi phải ở cùng transaction.
4. **Có request/worker khác đồng thời tác động vào cùng thực thể không?** Nếu có, cần bảo vệ điều kiện nghiệp vụ bên cạnh atomicity.
5. **Khi client không nhận được kết quả, làm sao xác định request đã commit chưa?** Cần khóa lũy đẳng, trạng thái truy vết hoặc chính sách retry phù hợp.

Kết quả phân tích nên được ghi thành một **hợp đồng transaction**. Ví dụ:

| Trường hợp | Ranh giới cần cân nhắc | Lý do |
|---|---|---|
| Tạo Order một sản phẩm | Order + OrderLine + relationship cần thiết | Tránh đơn hàng không hoàn chỉnh |
| Đổi tên Product | Cập nhật đúng Product | Một node là đủ nếu không có bất biến khác |
| Chấp nhận lời mời gia nhập nhóm | Đánh dấu lời mời và tạo membership trong một transaction | Không có trạng thái “đã chấp nhận nhưng chưa là thành viên” |
| Xóa membership | Xóa relationship, cập nhật trạng thái liên quan nếu cần | Không xóa nhầm node User/Group |
| Nhập một triệu Customer | Chia thành nhiều lô/transaction, có checkpoint | Một transaction khổng lồ gây chi phí và rủi ro rollback |
| Đặt hàng và gửi email | Transaction Neo4j + outbox, dispatcher bên ngoài | Email không nằm trong transaction Neo4j |
| Thanh toán qua nhà cung cấp ngoài | Giao dịch cục bộ và quy trình phối hợp nhiều bước | Không thể rollback trực tiếp giao dịch ngoài bằng Neo4j |

## 4. Mô hình ví dụ: một đơn hàng gồm một dòng

Giả sử ứng dụng dùng mô hình:

~~~mermaid
flowchart LR
  C["Customer<br/>customerId"]
  O["Order<br/>orderId, status, totalInCents"]
  L["OrderLine<br/>lineId, quantity, unitPriceInCents"]
  P["Product<br/>productId, priceInCents"]
  C -->|PLACED| O
  O -->|HAS_LINE| L
  L -->|FOR_PRODUCT| P
~~~

**OrderLine** được biểu diễn thành node vì nó có khóa `lineId`, số lượng và giá lịch sử. Nếu Product đổi giá ngày hôm sau, đơn cũ vẫn phải lưu đúng giá lúc đặt; không tính tiền lại từ `Product.priceInCents` khi đọc lịch sử.

### 4.1. Bất biến của thao tác đặt đơn

Với ví dụ đơn một dòng, khi transaction thành công:

- Có đúng một `Order` theo `orderId` được nhận diện bởi ứng dụng.
- Có một `OrderLine` mới với `lineId` ổn định.
- Order thuộc về một Customer được xác định.
- OrderLine được nối với đúng Order và Product.
- `quantity > 0` và `unitPriceInCents` là giá dùng để lập đơn.
- `totalInCents = quantity × unitPriceInCents` cho ví dụ một dòng.

Không mặc định Neo4j hiểu “một Order phải có chính xác một Customer” chỉ vì tồn tại relationship `PLACED`. Bất biến bội số relationship là một quy tắc mô hình/ứng dụng cần thiết kế và kiểm thử. Unique constraint trên `Order.orderId` không tự hạn chế số relationship từ các Customer khác nhau trỏ tới Order.

### 4.2. Ranh giới transaction đề xuất

~~~text
API placeOrder
    |
    +-- validate request trước transaction
    |
    +-- BEGIN transaction Neo4j
           |
           +-- MATCH Customer, Product
           +-- CREATE Order + OrderLine
           +-- CREATE các relationship
           +-- RETURN orderId, totalInCents
           |
           +-- COMMIT hoặc ROLLBACK toàn bộ
    |
    +-- trả kết quả / xử lý xung đột / phát tác vụ sau commit
~~~

Các bước **xác thực/validate thuần** có thể chạy trước khi mở transaction. Những điều kiện phụ thuộc dữ liệu graph đang thay đổi cần được thiết kế sao cho không dùng kết quả đọc cũ một cách thiếu an toàn.

## 5. Định danh và constraint trước khi mở traffic ghi

Sử dụng khóa nghiệp vụ ổn định thay vì ID nội bộ của Neo4j để định danh qua các lần retry và qua các service.

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT product_id_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.productId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT order_line_id_unique IF NOT EXISTS
FOR (l:OrderLine)
REQUIRE l.lineId IS UNIQUE;
~~~

Constraint cần được triển khai qua migration trước khi nhiều worker đồng thời ghi. Nếu database đã có node trùng, tạo uniqueness constraint tương ứng có thể thất bại. Uniqueness trên một property không tự khiến property đó bắt buộc tồn tại, vì vậy ứng dụng phải kiểm tra các khóa đầu vào.

**Không chạy câu tạo constraint trong mỗi request đặt đơn.** Schema là phần chuẩn bị môi trường, không phải một bước nghiệp vụ thông thường.

## 6. Ví dụ Cypher: tạo cả graph của một đơn trong một transaction

Một câu Cypher có thể bao trùm mọi thay đổi cần thiết cho use case đơn một dòng:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (p:Product {productId: $productId})
WHERE p.priceInCents IS NOT NULL

CREATE (o:Order {
  orderId: $orderId,
  status: 'CREATED',
  createdAt: datetime(),
  totalInCents: p.priceInCents * $quantity
})
CREATE (l:OrderLine {
  lineId: $lineId,
  quantity: $quantity,
  unitPriceInCents: p.priceInCents
})
CREATE (c)-[:PLACED]->(o)
CREATE (o)-[:HAS_LINE]->(l)
CREATE (l)-[:FOR_PRODUCT]->(p)

RETURN o.orderId AS orderId,
       o.totalInCents AS totalInCents;
~~~

**Điều kiện áp dụng:** request đã được validate: `orderId`, `lineId`, `customerId`, `productId` hợp lệ; `quantity` là số nguyên dương; `priceInCents` là giá hợp lệ do hệ thống quản lý. Câu lệnh không thực hiện giữ hàng hay thanh toán; đó là các bất biến nghiệp vụ khác phải được thiết kế riêng.

Ở Neo4j, một câu truy vấn ghi chạy trong phạm vi transaction. Nếu caller dùng managed transaction, nó có thể là một phần của transaction đó. Nếu truy vấn không tìm thấy Customer hoặc Product, `MATCH` cho ra **0 hàng** và các lệnh CREATE phía sau không chạy. Ứng dụng phải **kiểm tra không có kết quả** và trả lỗi phù hợp; không được coi “truy vấn không ném exception” là đơn được tạo.

Nếu CREATE OrderLine thành công về mặt thực thi trung gian nhưng thao tác ghi tiếp theo gây lỗi dẫn đến transaction rollback, không có phần OrderLine hoặc relationship của transaction được commit.

### 6.1. Vì sao không chia thành các auto-commit riêng?

Phản ví dụ:

~~~cypher
// Lần gọi 1: tạo Order trong một transaction riêng.
CREATE (:Order {
  orderId: $orderId,
  status: 'CREATED'
});
~~~

~~~cypher
// Lần gọi 2: tạo dòng hàng trong transaction khác.
CREATE (:OrderLine {
  lineId: $lineId,
  quantity: $quantity
});
~~~

~~~cypher
// Lần gọi 3: nối Order và OrderLine.
MATCH (o:Order {orderId: $orderId})
MATCH (l:OrderLine {lineId: $lineId})
CREATE (o)-[:HAS_LINE]->(l);
~~~

Nếu lần gọi 1 commit nhưng lần gọi 2 hoặc 3 thất bại, database có thể lưu một đơn thiếu dữ liệu. Việc chạy các câu trong **cùng một HTTP request** không làm chúng tự động cùng transaction.

Có thể tách nhiều câu Cypher vì mục đích rõ ràng/kiểm tra lỗi, **miễn là chúng nằm trong cùng transaction** khi tính nguyên tử là bắt buộc.

### 6.2. Quan hệ cũng là một phần của bất biến

Node có mặt đầy đủ nhưng relationship sai vẫn tạo graph nghiệp vụ sai. Ví dụ một OrderLine được nối tới Product khác với hàng đã chọn có thể dẫn tới sai báo cáo. Vì vậy, khi thiết kế transaction, đừng chỉ liệt kê những node phải tạo; cần liệt kê **tất cả relationship và property** cần đúng tại thời điểm commit.

## 7. Java Driver: managed transaction theo use case

Dưới đây là ví dụ Java Driver gọi câu Cypher ở mục 6 trong `Session.executeWrite(...)`. Hệ thống thực tế cần cấu hình `Driver`, authentication, URI và database tương ứng.

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class OrderApplicationService {
    public record CreatedOrder(String orderId, long totalInCents) {}

    private final Driver driver;

    public OrderApplicationService(Driver driver) {
        this.driver = driver;
    }

    public CreatedOrder placeSingleItemOrder(
            String orderId,
            String lineId,
            String customerId,
            String productId,
            long quantity) {

        if (orderId == null || orderId.isBlank()
                || lineId == null || lineId.isBlank()
                || customerId == null || customerId.isBlank()
                || productId == null || productId.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order input");
        }

        String cypher = """
            MATCH (c:Customer {customerId: $customerId})
            MATCH (p:Product {productId: $productId})
            WHERE p.priceInCents IS NOT NULL
            CREATE (o:Order {
                orderId: $orderId,
                status: 'CREATED',
                createdAt: datetime(),
                totalInCents: p.priceInCents * $quantity
            })
            CREATE (l:OrderLine {
                lineId: $lineId,
                quantity: $quantity,
                unitPriceInCents: p.priceInCents
            })
            CREATE (c)-[:PLACED]->(o)
            CREATE (o)-[:HAS_LINE]->(l)
            CREATE (l)-[:FOR_PRODUCT]->(p)
            RETURN o.orderId AS orderId,
                   o.totalInCents AS totalInCents
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> {
                Result result = tx.run(cypher, Values.parameters(
                    "orderId", orderId,
                    "lineId", lineId,
                    "customerId", customerId,
                    "productId", productId,
                    "quantity", quantity
                ));
                if (!result.hasNext()) {
                    throw new IllegalStateException(
                        "Customer or Product not found or invalid price"
                    );
                }
                var record = result.single();
                return new CreatedOrder(
                    record.get("orderId").asString(),
                    record.get("totalInCents").asLong()
                );
            });
        }
    }
}
~~~

Ví dụ đặt Order và OrderLine với ID **đã được chọn ở ranh giới nhận request**, không phát sinh ID mới mỗi khi callback chạy lại. `executeWrite` có thể retry transaction khi gặp lỗi transient phù hợp, nên callback không được gửi email hoặc gọi dịch vụ khác có tác dụng phụ ngoài Neo4j.

Cần xét trường hợp **commit đã thành công nhưng client không nhận được phản hồi**. Khi caller thử lại cùng `orderId`, CREATE có thể gặp uniqueness violation. Lúc đó service nên tra Order đã có và kiểm tra đầu vào tương ứng trước khi trả kết quả “đã xử lý”, thay vì tạo `orderId` mới hoặc coi mọi lỗi uniqueness là thành công.

### 7.1. Phương thức executeWrite có thể gồm nhiều câu Cypher

Một transaction không bắt buộc có một câu duy nhất:

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (o:Order {orderId: $orderId})
        SET o.internalNote = $note
        """, Values.parameters(
            "orderId", orderId,
            "note", note
        )).consume();

    tx.run("""
        MATCH (o:Order {orderId: $orderId})
        SET o.lastReviewedAt = datetime()
        """, Values.parameters("orderId", orderId)).consume();

    return null;
});
~~~

Hai câu ghi trên chạy **trong cùng managed transaction** nếu cùng dùng biến `tx` được cung cấp. Trong ví dụ này cả hai cập nhật có thể được gom thành một SET; nó minh họa ranh giới transaction chứ không khuyến khích tách câu khi không cần.

Nếu một câu Cypher tìm **0 hàng**, transaction vẫn có thể commit mà không có thay đổi tương ứng. Hãy dùng `RETURN` hoặc kiểm tra số hàng/thông tin kết quả khi nghiệp vụ yêu cầu đối tượng phải tồn tại. Chỉ dựa vào “không exception” là chưa đủ.

### 7.2. Phạm vi vòng đời Driver, Session và Transaction

| Đối tượng | Vòng đời tham khảo | Trách nhiệm |
|---|---|---|
| `Driver` | Tái sử dụng theo vòng đời ứng dụng | Kết nối, cấu hình, routing/pool |
| `Session` | Ngắn, thường theo một đơn vị gọi ứng dụng | Bối cảnh thực hiện truy vấn |
| Managed transaction callback | Một thao tác nghiệp vụ có thể được retry | Ghi/đọc những dữ liệu phải cùng commit |
| `Result` / `Record` | Tiêu thụ trong phạm vi phù hợp | Ánh xạ dữ liệu trả về DTO |

Đừng dùng một Session chia sẻ tùy tiện giữa nhiều thread, hoặc truyền Result chưa tiêu thụ ra ngoài callback rồi mong nó còn hoạt động sau khi transaction đóng.

## 8. Lựa chọn transaction đọc và ghi

Dùng `executeRead` cho truy vấn chỉ đọc:

~~~java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    var orders = session.executeRead(tx ->
        tx.run("""
            MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
            RETURN o.orderId AS orderId,
                   o.status AS status
            ORDER BY o.createdAt DESC, o.orderId DESC
            LIMIT $limit
            """, Values.parameters(
                "customerId", customerId,
                "limit", 20
            )).list(row -> new OrderSummary(
                row.get("orderId").asString(),
                row.get("status").asString()
            ))
    );
}
~~~

Ví dụ giả định `OrderSummary` là DTO/record đã được định nghĩa trong ứng dụng, còn `customerId` là biến đầu vào hợp lệ. Đặt điều kiện lọc, phân trang và projection vào Cypher để không truyền node/relationship thừa.

**Không dùng executeRead chỉ vì truy vấn có phần MATCH**: nếu transaction thực hiện CREATE/SET/DELETE, nó là thao tác ghi và nên dùng `executeWrite`.

### 8.1. Nhiều lần đọc có cần cùng transaction không?

Nếu ứng dụng phải tính một kết quả dựa trên nhiều truy vấn đọc liên quan, đặt chúng trong một read transaction có thể bảo đảm chúng cùng chịu quản lý thành một đơn vị giao dịch. Tuy nhiên, mức cô lập mặc định của Neo4j thường được mô tả là **read committed**; không được ngầm hiểu nhiều lần đọc trong một transaction luôn thấy cùng một snapshot bất biến của toàn database.

Nếu báo cáo yêu cầu snapshot chặt chẽ qua nhiều truy vấn, cần thiết kế quy trình nhất quán phù hợp với phiên bản Neo4j, workload và nguồn dữ liệu, thay vì cho rằng một transaction đọc tự tạo serializable isolation.

### 8.2. Không bao mọi truy vấn đọc của một màn hình bằng transaction ghi

Một trang dashboard có thể gọi nhiều endpoint độc lập: danh sách đơn, số đơn theo trạng thái và sản phẩm bán chạy. Không mặc định phải gom tất cả vào một write transaction. Nếu nghiệp vụ chấp nhận các chỉ số được cập nhật theo nhịp khác nhau, có thể đọc độc lập và dùng projection/materialized summary phù hợp.

Chỉ yêu cầu nhất quán mạnh hơn khi hợp đồng màn hình thật sự cần, ví dụ một chứng từ đối soát tài chính.

## 9. Read–check–write và giới hạn của atomicity trước ghi đồng thời

Giả sử cần trừ 3 sản phẩm tồn kho nhưng chỉ khi kho còn ít nhất 3. Một thiết kế đơn giản có thể là:

~~~text
T1: đọc stock = 4
T2: đọc stock = 4
T1: quyết định cho đặt 3
T2: quyết định cho đặt 3
T1/T2: ghi cập nhật tồn kho
~~~

Nếu một transaction đọc stock rồi tách sang transaction khác để trừ, kiểm tra cũ không còn đáng tin. Tuy nhiên, **chỉ đưa cả MATCH/WHERE/SET vào một transaction cũng chưa tự chứng minh** điều kiện được đánh giá sau khi có khóa ghi cần thiết trong mọi cách viết/query plan.

### 9.1. Lost update khi tính giá trị trước

Ví dụ có nguy cơ lost update:

~~~cypher
MATCH (p:Product {productId: $productId})
WITH p, p.stock AS oldStock
SET p.stock = oldStock - $quantity
RETURN p.stock AS stock;
~~~

Hai transaction có thể cùng tính `oldStock` trước khi khóa ghi được cấp cho thao tác SET, rồi ghi lại một giá trị từ dữ liệu cũ.

Với phép tăng/giảm số đơn giản, trực tiếp biểu diễn giá trị mới phụ thuộc property cũ trong SET cho phép Neo4j dùng cơ chế khóa phù hợp:

~~~cypher
MATCH (p:Product {productId: $productId})
SET p.stock = p.stock - $quantity
RETURN p.stock AS stock;
~~~

Nhưng ví dụ thứ hai **chưa bảo vệ bất biến stock không âm**. Để triển khai nghiệp vụ giữ tồn kho, cần một quy trình kiểm tra điều kiện an toàn dưới concurrency: phối hợp khóa ghi, đọc lại trạng thái sau khi giữ khóa, hoặc cơ chế điều khiển phiên bản được xác minh theo phiên bản Neo4j đang chạy. Nếu không bảo vệ đúng thời điểm kiểm tra, hai đơn song song vẫn có thể bán quá số lượng.

### 9.2. Ghi nhiều node dễ gặp deadlock

Một thao tác chuyển điểm từ ví A sang ví B có thể phải ghi hai node. Hai transaction chuyển A→B và B→A theo thứ tự lấy khóa đối nghịch có nguy cơ deadlock. Neo4j có thể phát hiện và rollback một transaction; ứng dụng cần xử lý lỗi transient/retry phù hợp.

Cân nhắc quy ước **thứ tự khóa nhất quán** theo ID ở những quy trình ghi nhiều thực thể. Việc này giúp giảm một số kiểu deadlock nhưng không bảo đảm loại bỏ toàn bộ, vì Neo4j còn có thể lấy khóa liên quan đến cấu trúc relationship và các toán tử khác.

Không kéo dài transaction trong lúc gọi HTTP bên ngoài chỉ để chờ nghiệp vụ hoàn tất; khóa đang giữ có thể chặn nhiều request khác.

## 10. Tính lũy đẳng cho request nghiệp vụ bị gửi lại

Một API có thể gặp tình huống:

~~~text
Client                   API / Neo4j
   |--- placeOrder ------->|
   |                       |--- transaction commit thành công
   |                       |
   X--- mất response ------|
   |
   |--- placeOrder lại --->|   (cùng thao tác logic)
~~~

Khi client không nhận phản hồi, **không thể chắc chắn** database chưa commit. Cần khóa lũy đẳng như `orderId` hoặc `commandId` ổn định qua các lần thử.

Trong ví dụ đặt đơn:

- `orderId` và `lineId` được chọn từ đầu, **không tạo UUID mới trong mỗi retry**.
- Uniqueness constraint ngăn tạo hai Order cùng `orderId`.
- Nếu lần thử sau gặp uniqueness violation, service tra Order đã tồn tại và đối chiếu Customer/Product/quantity/price hoặc request hash theo hợp đồng.
- Nếu dữ liệu khớp: coi là yêu cầu đã xử lý; nếu khác: trả xung đột, không im lặng ghi đè.

**Không xem mọi lỗi uniqueness là duplicate an toàn**: có thể trùng khóa khác hoặc dữ liệu đã bị tạo bởi một yêu cầu khác.

### 10.1. MERGE node chưa đủ cho mọi thao tác

~~~cypher
MERGE (a:Account {accountId: $accountId})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + 100;
~~~

MERGE bảo vệ cách tìm/tạo Account theo khóa, **không biết lệnh “cộng 100 điểm” đã được áp dụng chưa**. Nếu request chạy lại và commit lần hai, points tăng 200.

Với thao tác cộng dồn, cần một `commandId`/`eventId` ổn định và receipt/ledger được ghi cùng transaction với thay đổi nghiệp vụ, có uniqueness constraint trên định danh lệnh. Đây là một **bất biến khác** so với tính duy nhất của node Account.

### 10.2. Ranh giới transaction phải bao gồm receipt khi cần

~~~cypher
MATCH (a:Account {accountId: $accountId})
CREATE (cmd:AppliedCommand {
    commandId: $commandId,
    accountId: $accountId,
    delta: $delta,
    appliedAt: datetime()
})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta
SET cmd.resultPoints = a.rewardPoints
CREATE (cmd)-[:APPLIED_TO]->(a)
RETURN cmd.resultPoints AS resultPoints;
~~~

Cần constraint:

~~~cypher
CREATE CONSTRAINT applied_command_unique IF NOT EXISTS
FOR (cmd:AppliedCommand)
REQUIRE cmd.commandId IS UNIQUE;
~~~

Nếu commandId đã tồn tại, câu CREATE có thể vi phạm constraint và transaction thất bại; bản cập nhật cộng dồn trong transaction đó cũng không commit. Sau lỗi, ứng dụng đọc receipt và so nội dung request trước khi xác nhận đã xử lý.

**Đây là hai phạm vi cần tách rõ:**

1. **Business transaction:** thay đổi Account và receipt cùng commit.
2. **API retry policy:** khi gặp kết quả không rõ, tra receipt và quyết định có cần thử lại.

## 11. Khi thao tác cần gọi hệ thống ngoài Neo4j

Một use case thường vượt khỏi một database:

- Đặt đơn và gọi cổng thanh toán.
- Đặt đơn và gửi email xác nhận.
- Thêm bạn bè và publish message sang hệ thống thông báo.
- Duyệt đơn và gửi yêu cầu giao hàng tới dịch vụ kho ngoài.

Neo4j transaction chỉ bảo đảm atomicity của những thay đổi **trong phạm vi Neo4j database**. Email, Kafka, REST API, SQL server khác hay hệ thống thanh toán **không tự tham gia cùng transaction**.

### 11.1. Vì sao không gọi API ngoài trong executeWrite?

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (o:Order {orderId: $orderId})
        SET o.status = 'CONFIRMED'
        """, Values.parameters("orderId", orderId)).consume();

    mailer.sendOrderConfirmation(orderId);
    return null;
});
~~~

Nếu callback được driver retry, email có thể được gửi nhiều lần. Nếu transaction rollback, email gửi trước đó không được hoàn tác.

Việc gọi API ngoài khi đang giữ transaction còn tăng thời gian khóa, độ trễ và khả năng xung đột với các worker khác.

**Nguyên tắc:** callback managed transaction nên tập trung vào thao tác Neo4j có thể chạy lại một cách an toàn; không thực hiện tác dụng phụ bên ngoài nếu chưa có cơ chế idempotency phù hợp.

## 12. Transactional outbox: ghi “ý định phát” cùng dữ liệu

Một cách kết hợp giao dịch cục bộ với message broker là **transactional outbox**.

~~~mermaid
flowchart TD
    A["API: Xác nhận Order"] --> B["Neo4j transaction"]
    B --> C["SET Order.status = CONFIRMED"]
    B --> D["CREATE OutboxEvent PENDING"]
    C --> E["COMMIT"]
    D --> E
    E --> F["Dispatcher đọc OutboxEvent"]
    F --> G["Publish broker / gọi dịch vụ ngoài"]
    G --> H["Đánh dấu tiến độ"]
~~~

Lợi ích: nếu Neo4j commit, cả **trạng thái Order** và **bằng chứng cần phát sự kiện** đều có mặt; nếu rollback, cả hai cùng không commit.

Tạo constraint trên khóa event:

~~~cypher
CREATE CONSTRAINT outbox_event_key_unique IF NOT EXISTS
FOR (e:OutboxEvent)
REQUIRE e.eventKey IS UNIQUE;
~~~

Ví dụ trong một transaction:

~~~cypher
MATCH (o:Order {orderId: $orderId})
SET o.status = 'CONFIRMED',
    o.confirmedAt = datetime()
CREATE (e:OutboxEvent {
    eventKey: $eventKey,
    eventType: 'OrderConfirmed',
    orderId: $orderId,
    status: 'PENDING',
    createdAt: datetime()
})
CREATE (o)-[:EMITS]->(e)
RETURN o.orderId AS orderId, e.eventKey AS eventKey;
~~~

`eventKey` cần ổn định qua retry của cùng hành động xác nhận. Nếu confirmation có thể được gọi lặp, còn cần đảm bảo **không tạo lặp ý nghĩa xác nhận** hoặc các property có điều kiện trước khi phát event. Constraint outbox giúp chặn hai event cùng khóa; nó không tự bảo đảm quy tắc chuyển trạng thái Order hợp lệ khi nhiều loại lệnh khác nhau cùng chạy.

**Outbox không đồng nghĩa gửi chính xác một lần.** Nếu dispatcher publish thành công rồi crash trước khi cập nhật trạng thái SENT, nó có thể publish lại cùng eventKey. Bên nhận cần xử lý trùng hoặc API đích cần cung cấp idempotency key.

### 12.1. Không coi truy vấn đọc PENDING là claim độc quyền

~~~cypher
MATCH (e:OutboxEvent {status: 'PENDING'})
RETURN e.eventKey AS eventKey
LIMIT 10;
~~~

Đây là truy vấn **đọc**, không chiếm độc quyền mười event. Hai dispatcher có thể cùng đọc một tập kết quả. Trong vận hành cần cơ chế claim/lease/timeout, điều phối worker và chính sách retry riêng.

### 12.2. Bản tin outbox nên chứa dữ liệu ổn định

Không để dispatcher tự đọc lại Order ở thời điểm muộn rồi suy ra đó là “trạng thái ngay khi event phát sinh” nếu Order đã tiếp tục thay đổi. Có thể lưu snapshot dữ liệu/phiên bản cần thiết vào OutboxEvent cùng transaction để tái tạo thông điệp ổn định.

## 13. Workflow nhiều hệ thống: transaction cục bộ và saga

Giả sử đặt hàng qua Neo4j rồi thanh toán qua hệ thống ngoài:

~~~text
B1. Neo4j: tạo Order = PENDING_PAYMENT
B2. Payment API: xác nhận giao dịch
B3. Neo4j: đổi Order = PAID
B4. Dịch vụ giao hàng: tạo yêu cầu vận chuyển
~~~

Không nên giữ **một transaction Neo4j mở** xuyên suốt B1–B4, vì:

- Payment API có thể mất hàng giây hoặc nhiều phút.
- Neo4j không rollback được thanh toán đã thực hiện.
- Giao dịch dài giữ khóa, tăng chi phí và gây timeout.
- Bất kỳ lỗi nào ở bước sau cũng cần quyết định xử lý nghiệp vụ chứ không chỉ database rollback.

Một cách tiếp cận là **saga**: nhiều transaction cục bộ theo từng bước, có event, trạng thái trung gian và **compensating action** khi bước sau thất bại.

Ví dụ nếu đã thanh toán nhưng không thể giao hàng, hệ thống có thể cần **hoàn tiền** theo quy tắc nghiệp vụ, không phải rollback transaction Neo4j đã commit từ trước. Compensating action là một **thao tác nghiệp vụ mới**, không phải chức năng hoàn tác tự động của Neo4j.

### 13.1. Phân biệt tính nhất quán mạnh và nhất quán cuối cùng

| Nhu cầu | Lựa chọn khả thi |
|---|---|
| Order và OrderLine phải cùng tồn tại | Một Neo4j transaction |
| Ghi receipt và cộng điểm phải cùng commit | Một Neo4j transaction với constraint |
| Order đã commit thì cuối cùng phải có event phát đi | Neo4j transaction + outbox + dispatcher |
| Thanh toán ngoài phải được điều phối với Order | Workflow/saga và idempotency ở API thanh toán |
| Dashboard đọc dữ liệu tổng hợp giữa nhiều service | Thường chấp nhận eventual consistency nếu hợp đồng cho phép |

Đừng gán nhãn “eventual consistency” để biện minh cho trạng thái sai trong **một transaction nội bộ**. Ngược lại, đừng ép một quy trình liên hệ nhiều hệ thống thành transaction database duy nhất chỉ vì yêu cầu “mọi thứ phải đúng”.

## 14. Thiết kế transaction cho cập nhật relationship

Một số thao tác nghiệp vụ tập trung vào **mối quan hệ**, không phải node.

Ví dụ “khách hàng theo dõi một tác giả”:

~~~cypher
MATCH (u:User {userId: $userId})
MATCH (a:Author {authorId: $authorId})
MERGE (u)-[r:FOLLOWS]->(a)
ON CREATE SET r.followedAt = datetime()
RETURN u.userId AS userId, a.authorId AS authorId;
~~~

Nếu toàn bộ nghiệp vụ chỉ là “bảo đảm có quan hệ theo dõi”, một transaction cho mẫu này có thể đủ. Nhưng nếu đồng thời phải ghi nhận thay đổi trạng thái lời mời, loại bỏ yêu cầu đang chờ và tạo relationship, **những thay đổi bắt buộc cùng đúng** cần được gom cùng transaction.

**Cảnh báo concurrency:** MERGE relationship giữa hai node đã định danh giúp thể hiện ý định tìm hoặc tạo, nhưng uniqueness constraint trên ID của User và Author **không tự chứng minh duy nhất relationship cho cùng cặp** trong mọi lịch ghi đồng thời. Nếu nghiệp vụ cấm mọi quan hệ FOLLOWS trùng, cần thiết kế kiểm soát đồng thời/định danh relationship phù hợp với phiên bản Neo4j và kiểm thử.

### 14.1. Đừng xóa node chỉ để hủy một quan hệ

~~~cypher
MATCH (u:User {userId: $userId})-[r:FOLLOWS]->
      (a:Author {authorId: $authorId})
DELETE r;
~~~

Hủy theo dõi nghĩa là xóa relationship `FOLLOWS`, không phải `DETACH DELETE u` hoặc xóa Author. Phạm vi transaction cần khớp **tác động nghiệp vụ mong muốn**, tránh ảnh hưởng những thực thể không liên quan.

## 15. Chia nhỏ batch mà không phá vỡ một bất biến

Đối với nhập CSV hoặc xử lý hàng triệu event, không nên giữ một transaction duy nhất cho toàn bộ tập. Giao dịch lớn có thể giữ nhiều khóa lâu, tiêu thụ bộ nhớ và khiến rollback rất tốn kém.

Một thiết kế hợp lý:

1. Xác định **đơn vị bất biến nhỏ nhất**: một Customer, một Order đầy đủ, một event đã áp dụng cùng receipt.
2. Không chia một đơn vị phải cùng commit sang hai transaction khác nhau.
3. Gom nhiều đơn vị độc lập thành batch có kích thước phù hợp.
4. Dùng khóa ổn định, checkpoint và quy tắc replay/duplicate để tiếp tục sau lỗi.
5. Giới hạn mức song song khi nhiều batch cùng cập nhật node nóng.

Ví dụ nếu một Order có ba dòng hàng, không tách “CREATE Order” vào batch hôm nay rồi “CREATE OrderLine” vào batch ngày mai **nếu nghiệp vụ công bố Order là hoàn chỉnh ngay khi commit**. Có thể dùng trạng thái nhập tạm `IMPORTING` và quy trình công bố `READY` sau khi tất cả dữ liệu đã được xác minh, nhưng đó là **một hợp đồng nghiệp vụ khác** và cần được thể hiện rõ.

Neo4j hỗ trợ các cơ chế batch phù hợp từng phiên bản, ví dụ quản lý transaction trong Java Driver hoặc các mẫu Cypher chia transaction. Cú pháp và giới hạn của `CALL ... IN TRANSACTIONS` cần đối chiếu bản Neo4j đang dùng; không trộn nó vào một managed transaction khác nếu cách gọi không cho phép.

## 16. Vận hành: giữ transaction ngắn nhưng không cắt sai ranh giới

Nguyên tắc giảm thời gian giao dịch:

- Kiểm tra format, kiểu, quyền thao tác ở tầng ứng dụng trước khi bắt đầu khi không phụ thuộc dữ liệu đang thay đổi.
- Dùng khóa nghiệp vụ và index/constraint phù hợp để tìm node nhanh.
- Chỉ MATCH những node/relationship cần thay đổi.
- Không trả graph/path khổng lồ nếu API chỉ cần ID và vài property.
- Không thực hiện I/O bên ngoài Neo4j bên trong transaction callback.
- Giới hạn số bản ghi xử lý trong một transaction; đo lại theo workload.
- Tránh giữ transaction trong lúc đợi người dùng, gọi HTTP hoặc sleep/backoff.
- Retry **toàn bộ transaction** khi loại lỗi phù hợp, không tiếp tục từ giữa một transaction đã rollback.

Nhưng **không cắt một transaction đúng thành nhiều transaction nhỏ** chỉ để giảm thời gian khóa mà làm mất tính nguyên tử nghiệp vụ.

### 16.1. Quan sát query plan và transaction

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})
MATCH (p:Product {productId: $productId})
RETURN c.customerId AS customerId,
       p.productId AS productId;
~~~

`EXPLAIN` hiển thị kế hoạch mà không chạy truy vấn; dùng để xem tra cứu node, index và độ lớn dự kiến. Với truy vấn ghi, `PROFILE` **thực thi thao tác ghi**, nên không dùng trên dữ liệu thật chỉ để xem kế hoạch.

Theo quyền và phiên bản Neo4j, có thể xem transaction đang chạy bằng:

~~~cypher
SHOW TRANSACTIONS;
~~~

Theo dõi transaction lâu, khóa chờ, deadlock, timeout, kích thước lô và retry ở ứng dụng. Thời gian truy vấn trung bình thấp không chứng minh rằng không có request kéo dài vì tranh chấp khóa.

## 17. Bản thiết kế service cho ứng dụng nhiều lớp

Một kiến trúc thường gặp:

~~~mermaid
flowchart TD
    A["HTTP Controller"] --> B["Application Service / Use Case"]
    B --> C["Neo4j transaction / Repository"]
    C --> D["Node + Relationship + Property"]
    C --> E["OutboxEvent nếu cần"]
    E --> F["Dispatcher"]
    F --> G["Broker / dịch vụ ngoài"]
~~~

### 17.1. Application service quyết định ranh giới

Controller nhận input và gọi `placeOrder`; application service xác định bất biến, thực hiện transaction và phân loại lỗi; repository hoặc Neo4jClient chịu trách nhiệm câu Cypher cụ thể.

Không nên để controller gọi lần lượt bốn repository ghi bằng bốn transaction mặc định rồi coi các thao tác là nguyên tử chỉ vì nằm trong một request.

### 17.2. Spring Data Neo4j và @Transactional

Với Spring Data Neo4j, một service có thể khai báo:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWorkflowService {
    private final OrderWorkflowRepository repository;

    public OrderWorkflowService(OrderWorkflowRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void attachExistingLine(
            String orderId, String lineId, String productId) {
        repository.assertOrderAndProductExist(orderId, productId);
        repository.createLineAndRelationships(orderId, lineId, productId);
    }
}
~~~

Đây là **ví dụ tổ chức lớp**, giả định `OrderWorkflowRepository` cung cấp các phương thức phù hợp; không phải đoạn code có thể compile độc lập nếu chưa triển khai repository. Khi Spring transaction manager được cấu hình đúng cho Neo4j, các thao tác repository được gọi trong phạm vi transaction của service theo quy tắc quản lý transaction tương ứng.

Các lưu ý:

- Một `@Transactional` của Spring không mặc nhiên commit nguyên tử xuyên Neo4j, SQL và Kafka.
- Retry ở tầng Spring nếu có phải được thiết kế riêng; không coi `@Transactional` là tương đương chính sách retry của `executeWrite`.
- Self-invocation và cách cấu hình proxy có thể ảnh hưởng việc áp dụng annotation; kiểm tra hành vi transaction trên service thực tế.
- Khi exception bị bắt rồi nuốt trước khi ra khỏi service, việc rollback có thể không diễn ra như dự định nếu không đánh dấu rollback phù hợp.
- Không kết hợp tùy tiện managed transaction Java Driver với transaction Spring đang hoạt động mà chưa hiểu cách chúng quản lý session và phạm vi commit.

**Quy tắc thiết kế:** ranh giới transaction nên được khai báo tại **use-case/application service**, nơi biết những bước nào phải cùng đúng, thay vì rải rác ở từng thao tác repository mà không có hợp đồng chung.

## 18. Xử lý lỗi theo ranh giới nghiệp vụ

| Kết quả/lỗi | Tác động tới transaction | Phản ứng của ứng dụng |
|---|---|---|
| Commit thành công | Tất cả thay đổi trong transaction đã commit | Trả kết quả nghiệp vụ |
| Một câu Cypher ném lỗi và transaction rollback | Các thay đổi chưa commit trong transaction bị hủy | Trả lỗi hoặc retry theo nhóm lỗi |
| MATCH không tìm thấy node nhưng không ném lỗi | Có thể không có thay đổi | Kiểm tra kết quả và báo thiếu dữ liệu |
| Vi phạm uniqueness | Transaction ghi có thể thất bại | Phân biệt duplicate lũy đẳng với xung đột |
| Deadlock/transient error | Một transaction có thể bị rollback | Retry toàn bộ use case có giới hạn |
| Mất kết nối sau commit | Kết quả phía client có thể không rõ | Đọc lại bằng khóa ổn định/receipt |
| Email API thất bại sau commit Neo4j | Neo4j không rollback theo email | Outbox/retry/compensation |
| Payment API thành công nhưng cập nhật Order thất bại | Trạng thái hai hệ thống lệch | Sửa trạng thái qua saga/reconciliation |
| Vượt giới hạn tài nguyên vì batch lớn | Transaction có thể thất bại hoặc kéo dài | Giảm batch, thêm checkpoint, quan sát |

### 18.1. Không đánh đồng lỗi kỹ thuật và lỗi nghiệp vụ

Nếu Customer không tồn tại, có thể trả lỗi `NOT_FOUND` thay vì retry. Nếu cùng `orderId` đã tạo nhưng payload khác, trả `CONFLICT`. Nếu lỗi tạm thời do cluster/khóa, retry có giới hạn có thể hợp lý.

Nếu retry, lặp lại **toàn bộ callback hoặc transaction**, không chạy tiếp từ “bước thứ ba” như thể những bước trước đã commit. Với transaction đã rollback, tất cả thao tác Neo4j thuộc transaction đó phải được xem như chưa hoàn thành.

### 18.2. Idempotency là một phần hợp đồng API

Tài liệu endpoint đặt đơn nên nói rõ:

- Khóa dùng để nhận diện một request logic: `orderId` hay `requestId`.
- Cùng khóa/cùng payload được xử lý thế nào.
- Cùng khóa/khác payload có trả conflict không.
- Khi timeout, client nên gửi lại cùng khóa hay tra cứu trạng thái.
- Những trạng thái trung gian nào được phép hiển thị.

Không thể xây dựng retry an toàn nếu client luôn tạo một khóa mới cho cùng một thao tác.

## 19. Kiểm thử ranh giới transaction

### 19.1. Kiểm thử atomicity

Trong database thử nghiệm, tạo Customer và Product hợp lệ, sau đó gọi đặt đơn với `orderId` mới.

**Kỳ vọng thành công:**

- Có một Order và một OrderLine mới.
- Có đủ `PLACED`, `HAS_LINE`, `FOR_PRODUCT`.
- Order lưu đúng giá tại thời điểm đặt.

**Kỳ vọng lỗi giữa chừng:** cố tình gây lỗi constraint cho `lineId`, kiểm tra không có Order mới cùng các relationship của lần thử thất bại được commit.

Ví dụ kiểm tra trên khóa của một Order:

~~~cypher
MATCH (o:Order {orderId: $orderId})
OPTIONAL MATCH (c:Customer)-[placed:PLACED]->(o)
OPTIONAL MATCH (o)-[hasLine:HAS_LINE]->(l:OrderLine)
OPTIONAL MATCH (l)-[forProduct:FOR_PRODUCT]->(p:Product)
RETURN o.orderId AS orderId,
       count(DISTINCT c) AS customers,
       count(DISTINCT l) AS lines,
       count(DISTINCT p) AS products;
~~~

Truy vấn kiểm tra trên **một Order** và giả định mô hình một dòng. Các OPTIONAL MATCH có thể nhân hàng nếu dữ liệu có relationship trùng; `DISTINCT` giúp đếm node phân biệt, nhưng nếu cần phát hiện trùng relationship thì phải đếm từng relationship riêng.

### 19.2. Kiểm thử retry và idempotency

| Tình huống | Kết quả mong đợi |
|---|---|
| Một request tạo Order mới | Có một Order hoàn chỉnh |
| Cùng `orderId` và payload gửi lại | Không có Order/OrderLine lặp |
| Cùng `orderId` nhưng payload khác | Trả xung đột, không ghi đè |
| Hai thread cùng đặt một `orderId` | Constraint ngăn hai Order trùng đã commit |
| Gây lỗi giữa các câu ghi trong cùng transaction | Không có cập nhật một phần được commit |
| Gây transient error trước commit | Callback có thể retry; không có tác dụng phụ ngoài DB bị lặp |
| Mất response sau commit | Client dùng cùng khóa để truy trạng thái |
| Outbox dispatcher crash sau publish | Có thể publish lại, downstream xử lý trùng |
| Đặt đơn đồng thời với thay đổi tồn kho | Kiểm tra bất biến stock bằng concurrency test |

### 19.3. Kiểm thử nhiều transaction và hệ thống ngoài

Đừng chỉ kiểm tra hàm service bằng mock repository rồi kết luận ranh giới giao dịch đúng. Cần integration test với Neo4j chạy thật, có constraint và nhiều thread, đặc biệt cho:

- Cùng một khóa nghiệp vụ được ghi đồng thời.
- Thao tác thay đổi nhiều relationship.
- Lỗi sau câu ghi thứ nhất nhưng trước câu ghi thứ hai.
- Retry sau timeout và kết quả commit không rõ.
- Dispatcher outbox phát lại.
- Quy trình saga cần compensation.

Trong môi trường test, không dùng dữ liệu thật hoặc gửi email/thanh toán thật để gây lỗi mô phỏng.

## 20. Các sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Một repository call là một transaction riêng, dù thuộc cùng nghiệp vụ | Graph có thể ở trạng thái dở dang | Đặt ranh giới tại use-case service |
| Cho rằng một HTTP request tự có atomicity | Các lần gọi DB có thể commit riêng | Dùng transaction tường minh/managed |
| Bao cả lời gọi HTTP ngoài vào transaction | Khóa giữ lâu, side effect không rollback | Outbox và workflow riêng |
| Tạo ID mới bên trong callback retry | Cùng request sinh nhiều Order | ID ổn định trước callback |
| Chỉ MERGE Account trước khi cộng điểm | Retry cộng lại lần nữa | Receipt/commandId trong cùng transaction |
| Chỉ kiểm tra “không exception” sau MATCH | Có thể không tạo dữ liệu vì 0 hàng | Kiểm tra RETURN/row count |
| Tin rằng transaction tự chống mọi lost update | Đọc giá trị cũ rồi ghi đè | Thiết kế concurrency và kiểm chứng |
| Giả định constraint node ngăn mọi relationship trùng | Cạnh trùng vẫn có thể vi phạm nghiệp vụ | Mô hình relationship và điều phối ghi |
| Một transaction cho toàn bộ import nhiều triệu hàng | Giữ khóa lâu, rollback tốn kém | Chia lô theo đơn vị bất biến |
| Chia một đơn hàng đang “hoàn chỉnh” thành hai transaction | Trạng thái thiếu line/relationship | Gom các thay đổi cần cùng đúng |
| Dùng PROFILE để thử câu ghi trên production | Thao tác ghi được thực thi thật | EXPLAIN hoặc test DB |
| Bỏ qua ambiguous commit | Request bị áp dụng lặp | Truy theo ID/receipt và retry an toàn |

## 21. Bài tập ứng dụng

### Bài 1 — Xác định transaction cho Order

Yêu cầu tạo Order cùng hai OrderLine và đầy đủ relationship. Nếu một dòng hàng lỗi, đơn không được phép xuất hiện.

**Câu hỏi:** Nên tạo Order và từng OrderLine trong ba auto-commit hay một transaction?

**Đáp án:** Một transaction bao trùm các node, relationship và property bắt buộc của Order. Nếu có lỗi, rollback tất cả phần của nghiệp vụ.

### Bài 2 — Đổi tên Product

Yêu cầu duy nhất là cập nhật `Product.name`, không có thay đổi quan hệ hay hệ thống ngoài.

**Câu hỏi:** Có nên mở transaction chờ dịch vụ email gửi xong không?

**Đáp án:** Không. Giới hạn transaction ở cập nhật Product; nếu cần gửi thông báo, dùng quy trình sau commit/outbox phù hợp.

### Bài 3 — Cộng điểm

API nhận lệnh cộng 100 điểm. Nếu client retry sau timeout, lệnh không được cộng thêm lần nữa.

**Câu hỏi:** `MERGE (Account)` đã đủ không?

**Đáp án:** Chưa. Cần định danh command ổn định, receipt/constraint và cập nhật điểm trong cùng transaction; kiểm tra receipt khi kết quả commit không rõ.

### Bài 4 — Tồn kho

Hai người dùng đồng thời đặt ba sản phẩm khi kho có bốn.

**Câu hỏi:** Chỉ bao phép kiểm tra “stock >= 3” và trừ tồn kho vào một transaction là chắc chắn an toàn chưa?

**Đáp án:** Chưa thể khẳng định nếu chưa hiểu thời điểm đọc/khóa và cách biểu diễn điều kiện. Cần thiết kế thao tác giữ kho có bảo vệ concurrency, rồi kiểm thử đồng thời với Neo4j.

### Bài 5 — Thanh toán bên ngoài

Transaction Neo4j đã tạo Order thành công, API thanh toán thành công, nhưng dịch vụ giao hàng thất bại.

**Câu hỏi:** Có thể rollback Neo4j để tự hoàn tác thanh toán không?

**Đáp án:** Không. Cần điều phối saga/compensating action theo nghiệp vụ, ví dụ hoàn tiền hoặc chuyển trạng thái xử lý lỗi.

### Bài 6 — Sự kiện outbox

Dispatcher gửi message thành công nhưng crash trước khi đánh dấu SENT.

**Câu hỏi:** Outbox có bảo đảm consumer nhận message đúng một lần không?

**Đáp án:** Không. Dispatcher có thể gửi lại. Dùng eventKey ổn định và lũy đẳng phía consumer.

### Bài 7 — Đọc nhiều truy vấn

Service mở một read transaction, đọc `Order.status` rồi đọc `Order.totalInCents` sau đó.

**Câu hỏi:** Có thể khẳng định hai lần đọc thấy snapshot bất biến không?

**Đáp án:** Không chỉ dựa vào việc chúng cùng transaction. Cần hiểu isolation và mức nhất quán mà nghiệp vụ yêu cầu.

### Bài 8 — Transaction bị nuốt exception

Một service Spring bắt exception từ repository rồi trả thành công mà không ném lại hoặc đánh dấu rollback.

**Câu hỏi:** Có nguy cơ gì?

**Đáp án:** Transaction có thể commit những thay đổi đã thực hiện trước lỗi nếu không được đánh dấu rollback đúng cách. Cần quy tắc xử lý exception nhất quán với ý nghĩa use case.

## 22. Ghi nhớ

**Ranh giới giao dịch trong Neo4j phải được thiết kế theo thao tác nghiệp vụ và các bất biến cần cùng đúng**, không theo số câu Cypher, số repository hay số request HTTP. Một Order hoàn chỉnh cần node, relationship và property liên quan cùng commit; một phép đổi tên đơn giản không cần transaction kéo dài qua thao tác không liên quan.

Trong Java Driver, dùng `executeWrite` cho các bước ghi phải nguyên tử, xử lý trường hợp MATCH không có hàng, chuẩn bị khóa nghiệp vụ ổn định và thiết kế callback an toàn khi retry. **Atomicity không tự giải quyết cạnh tranh ghi**, nên những điều kiện như tồn kho, phiên bản và tính duy nhất relationship cần được bảo vệ/kiểm thử riêng. Khi quy trình liên quan broker, email hoặc thanh toán, dùng **transaction cục bộ, outbox và saga** theo nhu cầu, thay vì giả định Neo4j có thể rollback hệ thống khác. Một ranh giới đúng vừa bảo vệ dữ liệu graph vừa giữ transaction đủ ngắn để ứng dụng vận hành ổn định.
