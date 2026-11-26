# Tính nguyên tử, nhất quán, cô lập và bền vững trong Neo4j

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích bốn thuộc tính **ACID** của giao dịch (*transaction*) khi thao tác trên **property graph** trong Neo4j.
- Xác định ranh giới giao dịch của một câu lệnh Cypher, nhiều câu lệnh, và các API giao dịch trong Java Driver hoặc Spring Data Neo4j.
- Phân tích việc rollback, áp dụng constraint, đọc/ghi đồng thời, sự cố giữa chừng và tính bền vững sau commit.
- Phân biệt **ACID**, **lũy đẳng** và **nhất quán nhân quả** khi ứng dụng retry hoặc chạy trên cluster.
- Thiết kế và kiểm chứng một thao tác nghiệp vụ cập nhật nhiều node/relationship một cách an toàn.

Chương **Giao dịch** của module **DATABASE_ENGINE_GRAPH_NEO4J** đặt các thao tác tạo node, kết nối relationship và sửa thuộc tính vào cùng một ranh giới tin cậy. Neo4j dùng property graph và Cypher để biểu diễn cũng như truy vấn quan hệ, đường đi; nhưng kết quả đúng của một truy vấn đồ thị không chỉ phụ thuộc vào cú pháp. Khi một nghiệp vụ thay đổi **nhiều phần tử có liên quan**, ta cần bảo đảm các thay đổi được chấp nhận hoặc hủy cùng nhau.

## 1. Transaction là gì và khi nào cần?

**Transaction** là đơn vị công việc được database thực thi và quản lý như một tập thao tác nhất quán. Một transaction có thể chỉ chứa một câu Cypher hoặc nhiều câu Cypher.

Ví dụ, nghiệp vụ đặt hàng cần:

1. Xác định node khách hàng `Customer`.
2. Tạo node đơn hàng `Order`.
3. Tạo relationship `PLACED` từ khách hàng đến đơn.
4. Cập nhật trạng thái đơn hàng.

Nếu bước 3 hoặc 4 thất bại sau khi đơn đã được tạo, không nên để lại đơn mồ côi hoặc đơn ở trạng thái nửa hoàn thành. Đặt các bước trong **cùng transaction** giúp toàn bộ thao tác ghi thành công cùng nhau hoặc bị rollback.

~~~mermaid
flowchart TD
    A["Bắt đầu transaction"] --> B["Tạo/cập nhật node"]
    B --> C["Tạo/cập nhật relationship"]
    C --> D{"Tất cả thao tác hợp lệ?"}
    D -->|Có| E["COMMIT: công bố toàn bộ thay đổi"]
    D -->|Không| F["ROLLBACK: hủy các thay đổi chưa commit"]
~~~

Trong Neo4j, **một câu Cypher thông thường cũng chạy trong transaction**. Khi muốn nhiều câu lệnh cùng thành công hoặc cùng thất bại, ứng dụng phải đặt chúng trong **cùng ranh giới giao dịch**. Nếu gửi từng câu riêng bằng giao dịch ngầm (*implicit/auto-commit*) và câu đầu đã commit, lỗi ở câu sau không thể tự động hủy câu đầu.

> **Lưu ý:** Bài này giải thích nguyên lý và cách dùng trên Neo4j hiện đại (đặc biệt dòng Neo4j 5.x). Tùy phiên bản, API, cú pháp nhập dữ liệu theo lô và hành vi lập kế hoạch truy vấn có thể khác; khi vận hành hãy đối chiếu phiên bản database và driver thực tế.

## 2. ACID nhìn từ property graph

ACID viết tắt của **Atomicity**, **Consistency**, **Isolation**, **Durability**.

| Thuộc tính | Ý nghĩa thực tế trong Neo4j | Nếu thiếu, điều gì có thể xảy ra? |
| --- | --- | --- |
| **A — Atomicity (Nguyên tử)** | Các thay đổi trong một transaction được commit hoặc rollback như một đơn vị | Có node đơn hàng nhưng thiếu relationship bắt buộc |
| **C — Consistency (Nhất quán)** | Transaction phải tuân thủ các quy tắc mà database thực thi, như constraint; quy tắc nghiệp vụ cần được ứng dụng bảo vệ thêm | Hai khách hàng cùng mã dù mã phải duy nhất; tổng tiền sai do logic nghiệp vụ |
| **I — Isolation (Cô lập)** | Các transaction đồng thời không được thấy dữ liệu **chưa commit** của nhau; mức mặc định là *read committed* | Đọc dữ liệu chưa hoàn thành, hoặc hiểu sai về việc hai lần đọc sẽ luôn giống nhau |
| **D — Durability (Bền vững)** | Transaction đã commit được lưu bền vững và có cơ chế phục hồi khi database khởi động lại | Trạng thái đã báo thành công biến mất sau lỗi tiến trình |

Bốn tính chất phối hợp với nhau nhưng giải quyết **những rủi ro khác nhau**. ACID không có nghĩa là mọi quy tắc nghiệp vụ đều tự động được Neo4j hiểu, hay mọi giao dịch đồng thời đều tương đương với xử lý tuần tự.

## 3. Atomicity — tất cả hoặc không gì cả

### 3.1. Một lệnh Cypher cập nhật nhiều phần tử

Giả sử database đã có khách hàng `C-101`. Tạo uniqueness constraint cho mã đơn để ngăn hai đơn hàng trùng định danh:

~~~cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

Sau đó thực hiện thao tác tạo node và relationship:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
CREATE (o:Order {
  orderId: $orderId,
  status: 'CREATED',
  total: $total
})
CREATE (c)-[:PLACED]->(o)
RETURN o.orderId AS orderId;
~~~

Ở một câu Cypher bình thường, việc tạo `Order` và cạnh `PLACED` thuộc **cùng transaction của câu lệnh**. Nếu có lỗi làm transaction thất bại, các thay đổi của câu lệnh đó không được commit một phần.

Tuy vậy, `MATCH` không tìm thấy khách hàng sẽ cho **0 hàng**, không tự động phát sinh lỗi. Trường hợp này câu lệnh không tạo gì; ứng dụng phải kiểm tra số hàng trả về và phát sinh lỗi nghiệp vụ nếu khách hàng bắt buộc tồn tại.

### 3.2. Nhiều câu Cypher phải dùng chung transaction

Nếu ứng dụng tách việc tạo đơn và cập nhật trạng thái thành **hai câu lệnh**, ranh giới phải bao cả hai:

~~~text
BEGIN TRANSACTION
  1. MATCH Customer; CREATE Order; CREATE relationship PLACED
  2. MATCH Order; SET auditState = 'PENDING'
  Nếu có lỗi -> ROLLBACK cả bước 1 và bước 2
  Nếu tất cả đúng -> COMMIT
~~~

Đoạn trên là **mã giả mô tả ranh giới**; `BEGIN TRANSACTION` không phải lệnh Cypher thuần để dán vào mọi client. Cách mở/commit/rollback cụ thể được cung cấp bởi Java Driver, Spring Transaction Manager hoặc client đang dùng.

Khi transaction đã commit, không thể gọi rollback để thu hồi giao dịch cũ. Nếu muốn đảo nghiệp vụ, cần một **giao dịch bù** (*compensating transaction*) phù hợp.

### 3.3. Phân biệt rollback với không tạo ra dữ liệu

Các tình huống có kết quả khác nhau:

| Tình huống | Kết quả |
| --- | --- |
| Lệnh đầu tạo node, lệnh sau lỗi trong **cùng transaction** | Transaction thất bại và rollback các ghi chưa commit |
| Lệnh đầu đã **commit riêng**, lệnh sau lỗi | Dữ liệu lệnh đầu vẫn còn |
| `MATCH` không có hàng, không có lỗi | Câu lệnh có thể hoàn thành bình thường nhưng không ghi gì |
| Xảy ra lỗi constraint, ứng dụng bắt lỗi rồi vẫn muốn commit | Không được giả định có thể tiếp tục transaction đã thất bại; cần rollback và mở transaction mới |
| Driver retry sau lỗi nhất thời | Callback giao dịch có thể được chạy lại; cần tránh tác dụng phụ bên ngoài |

**Ngoại lệ quan trọng với nhập dữ liệu theo lô:** Cypher có cú pháp `CALL { ... } IN TRANSACTIONS` để chia công việc thành nhiều transaction nhỏ. Những lô trước đã commit có thể vẫn còn nếu lô sau lỗi. Vì vậy, không xem cả thao tác import nhiều lô là một transaction nguyên tử duy nhất.

## 4. Consistency — bảo vệ bất biến của đồ thị

Tính nhất quán nghĩa là database duy trì những **quy tắc có thể kiểm chứng** của dữ liệu trước và sau transaction đã commit. Trong Neo4j, một phần quy tắc đó được biểu diễn bằng **schema constraint**.

### 4.1. Constraint là tuyến bảo vệ ở database

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

Với constraint duy nhất trên `Order.orderId`, hai node `Order` không thể cùng commit với một giá trị `orderId` giống nhau. Transaction ghi vi phạm constraint sẽ thất bại; các thay đổi chưa commit của transaction đó bị rollback.

**Giới hạn cần nhớ:** uniqueness constraint trên một thuộc tính không tự buộc mọi node thuộc label phải có thuộc tính đó. Nếu mã là bắt buộc, cần kiểm tra input, dùng loại constraint phù hợp với edition/phiên bản đang triển khai, hoặc tổ chức một lớp validation tương ứng.

### 4.2. Constraint không thay cho nghiệp vụ

Giả sử cửa hàng có quy tắc “tổng giá trị đơn phải bằng tổng giá trị các dòng hàng”. Neo4j không tự suy ra công thức này từ graph:

~~~text
Order.total == SUM(OrderLine.quantity * OrderLine.unitPrice)
~~~

Ứng dụng cần tính/kiểm tra trong nghiệp vụ và bảo đảm các node, relationship, thuộc tính liên quan được ghi trong **cùng transaction**. Với cập nhật đồng thời, còn phải có chiến lược cô lập/đồng bộ phù hợp để tránh các transaction cùng đọc trạng thái cũ rồi đưa ra quyết định xung đột.

Tương tự, một constraint trên `Order.orderId` không tự ngăn cùng một đơn xuất hiện hai lần trong hệ thống ngoài Neo4j khi đầu vào sinh ID mới ở mỗi lần retry. **ACID, constraint và idempotency** là ba khái niệm liên quan nhưng không đồng nhất.

## 5. Isolation — điều gì xảy ra khi nhiều transaction chạy cùng lúc?

Neo4j dùng mức cô lập mặc định **read committed**. Điều này có nghĩa:

- Transaction khác **không nhìn thấy thay đổi chưa commit**.
- Một transaction thường **nhìn thấy thay đổi do chính nó ghi** trong các câu truy vấn tiếp theo thuộc cùng transaction.
- Hai lần đọc cùng dữ liệu trong cùng transaction **không được đảm bảo trả cùng kết quả** nếu transaction khác đã commit thay đổi ở giữa. Đây là hiện tượng *non-repeatable read*.
- Các truy vấn theo điều kiện cũng có thể thấy tập kết quả thay đổi khi transaction khác tạo/xóa phần tử thỏa điều kiện, tùy thời điểm đọc; không nên mặc định có *snapshot isolation* cho mọi lần đọc.

### 5.1. Ví dụ đọc có thể thay đổi

~~~text
Thời điểm    Transaction A                      Transaction B
T1           Đọc Customer C-101: status=NEW
T2                                              Đổi status=ACTIVE; COMMIT
T3           Đọc lại C-101: có thể thấy ACTIVE
T4           COMMIT
~~~

Transaction A không thấy trạng thái **chưa commit** của B, nhưng có thể thấy trạng thái **đã commit** của B ở lần đọc sau. Điều này không vi phạm mức read committed.

### 5.2. Khóa ghi, tranh chấp và lost update

Neo4j dùng cơ chế khóa và quản lý xung đột để bảo vệ tính toàn vẹn khi ghi. Hai transaction cùng sửa một node/relationship có thể phải đợi nhau; một transaction có thể bị hủy do deadlock hoặc lỗi transaction nhất thời.

Tuy nhiên, quy tắc như “chỉ trừ tiền nếu số dư đủ” không được bảo vệ chỉ bởi việc đặt `WHERE` trước một lệnh `SET` rồi giả định không có cạnh tranh. Ví dụ nguy hiểm:

~~~text
Transaction A đọc balance = 100
Transaction B đọc balance = 100
Transaction A tính số dư mới = 20
Transaction B tính số dư mới = 30
Cả hai lần ghi cố cập nhật dựa trên giá trị cũ
~~~

Nếu ứng dụng **tính giá trị mới ngoài transaction hoặc đọc trước rồi ghi sau mà không kiểm soát đồng thời**, có nguy cơ cập nhật bị mất (*lost update*) hoặc bất biến số dư bị phá vỡ.

Một số thao tác Cypher cập nhật trực tiếp thuộc tính trên chính node được Neo4j bảo vệ bằng khóa ghi phù hợp, nhưng không nên suy rộng điều đó thành mọi quy tắc nhiều node/đa bước đều đã an toàn. Với nghiệp vụ có cạnh tranh cao, cân nhắc:

1. **Đưa toàn bộ đọc, kiểm tra và ghi liên quan vào một transaction**; tránh dùng kết quả đã đọc ở transaction cũ làm quyết định.
2. **Khóa các thực thể cần bảo vệ trước khi kiểm tra điều kiện**, theo cơ chế và API tương thích phiên bản Neo4j; thống nhất thứ tự khóa để giảm deadlock.
3. **Optimistic locking** bằng trường version hoặc `@Version` trong Spring Data Neo4j; phát hiện xung đột và retry toàn nghiệp vụ có giới hạn.
4. **Constraint** để bảo vệ danh tính, đồng thời kiểm thử hai hoặc nhiều transaction ghi cùng lúc.

Nếu gặp deadlock hoặc transient error, một transaction có thể rollback và được retry theo chính sách ứng dụng. Retry cần có giới hạn, backoff phù hợp và tránh lặp các hành động bên ngoài database.

## 6. Durability — dữ liệu sau COMMIT tồn tại ra sao?

Khi Neo4j xác nhận một transaction đã commit thành công, các thay đổi trở thành **trạng thái đã chấp nhận**. Neo4j sử dụng cơ chế lưu trữ, transaction log và phục hồi sau sự cố để duy trì những thay đổi đã commit khi tiến trình khởi động lại.

Phân biệt các thời điểm sau:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant DB as Neo4j
    App->>DB: Gửi các thao tác ghi trong transaction
    DB-->>App: Thực thi; dữ liệu chưa commit
    App->>DB: Yêu cầu COMMIT
    DB-->>App: Xác nhận commit thành công
    Note over DB: Thay đổi là dữ liệu đã commit
~~~

- **Trước commit:** Dù câu lệnh đã được chạy trong transaction, lỗi/rollback vẫn có thể hủy ghi.
- **Sau commit thành công:** Neo4j có trách nhiệm bảo đảm tính bền vững theo cơ chế lưu trữ và cấu hình triển khai.
- **Mất kết nối đúng thời điểm commit:** Client có thể không biết transaction đã commit hay chưa. Không được suy luận “timeout tức là rollback”; cần truy vấn kiểm chứng, dùng **ID nghiệp vụ ổn định** hoặc cơ chế chống xử lý trùng.
- **Thảm họa mất toàn bộ thiết bị lưu trữ:** Durability không thay thế backup, kiểm tra phục hồi hay thiết kế dự phòng.

Ở **cluster**, đọc từ thành viên khác có thể cần thông tin **bookmark** để bảo đảm các transaction phụ thuộc nhau được quan sát theo đúng thứ tự. Bookmark phục vụ **causal consistency** giữa các session/transaction; nó không tự nâng mức cô lập read committed lên serializable và không phải thay thế cho transaction.

## 7. Ranh giới transaction trong Cypher và Java Driver

### 7.1. Các cách chạy lệnh thường gặp

| Cách chạy | Ranh giới | Khi nên dùng |
| --- | --- | --- |
| Một câu Cypher thông thường | Một transaction cho câu lệnh | Truy vấn/ghi đơn giản, không có bước tiếp theo phải commit cùng |
| Nhiều lệnh `session.run(...)` độc lập | Mỗi lệnh implicit có transaction riêng | Các thao tác không cần nguyên tử với nhau |
| `session.beginTransaction()` | Transaction tường minh, ứng dụng gọi `commit()` | Kiểm soát chính xác thời điểm commit/rollback |
| `session.executeWrite(...)` / `executeRead(...)` | Managed transaction do driver quản lý | Đa số luồng đọc/ghi ứng dụng, có hỗ trợ retry lỗi phù hợp |
| `@Transactional` trong Spring | Transaction theo lời gọi qua Spring proxy và transaction manager | Dịch vụ Spring Data Neo4j phối hợp nhiều truy vấn/repository |

Lưu ý: Với implicit transaction, cần **consume** kết quả hoặc đóng session đúng cách trước khi xem thao tác là hoàn tất. Không được giữ result stream chưa đọc hết rồi suy luận commit đã xảy ra.

### 7.2. Java Driver: hai câu lệnh trong một managed transaction

Đây là ví dụ sử dụng **Neo4j Java Driver**, giả sử `Customer` đã tồn tại và database đã có constraint duy nhất trên `Order.orderId`:

~~~java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public class OrderTransactionExample {
    static String placeOrder(
            Driver driver, String customerId, String orderId, long total) {
        try (Session session =
                     driver.session(SessionConfig.forDatabase("neo4j"))) {

            return session.executeWrite(tx -> {
                var params = Map.of(
                        "customerId", customerId,
                        "orderId", orderId,
                        "total", total);

                String createdId = tx.run("""
                        MATCH (c:Customer {customerId: $customerId})
                        CREATE (o:Order {
                            orderId: $orderId,
                            total: $total,
                            status: 'CREATED'
                        })
                        CREATE (c)-[:PLACED]->(o)
                        RETURN o.orderId AS id
                        """, params).single().get("id").asString();

                tx.run("""
                        MATCH (o:Order {orderId: $orderId})
                        SET o.auditState = 'PENDING'
                        """, params).consume();

                return createdId;
            });
        }
    }

    public static void main(String[] args) {
        // URI và thông tin đăng nhập thực tế cần lấy từ cấu hình an toàn.
        try (Driver driver = GraphDatabase.driver(
                "bolt://localhost:7687",
                AuthTokens.basic("neo4j", "password-from-config"))) {
            System.out.println(
                    placeOrder(driver, "C-101", "O-901", 150000L));
        }
    }
}
~~~

Hai lần gọi `tx.run` nằm trong cùng callback `executeWrite`, tức **cùng transaction**. Nếu bước thứ hai lỗi, cả việc tạo `Order` và tạo quan hệ `PLACED` ở bước đầu đều bị rollback. Nếu `MATCH` không có khách hàng, `single()` không tìm được hàng và phát sinh lỗi trong callback; ứng dụng có thể bắt/ánh xạ thành lỗi nghiệp vụ ở bên ngoài transaction.

`executeWrite` có thể **thực thi lại callback** đối với những lỗi transient mà driver coi là có thể retry. Do đó:

- Không gửi email, gọi thanh toán ngoài, xuất bản Kafka message hay sinh ID thay đổi mỗi lần retry **bên trong callback**.
- Tạo `orderId` ổn định trước khi vào transaction; nếu request có thể được gửi lại sau commit thành công, cần thêm **thiết kế idempotent upsert/deduplication**. Constraint đảm bảo không trùng ID nhưng có thể khiến lần gửi lại nhận lỗi trùng, thay vì tự trả thành công.
- Không mặc định driver retry mọi lỗi; vi phạm constraint và lỗi nghiệp vụ thông thường cần ứng dụng quyết định cách xử lý.

### 7.3. Java Driver: transaction tường minh

Khi cần chủ động quyết định lúc commit, sử dụng `beginTransaction()`:

~~~java
try (Session session = driver.session();
     var tx = session.beginTransaction()) {

    tx.run("""
        MATCH (c:Customer {customerId: $customerId})
        SET c.lastOrderId = $orderId
        """, Map.of(
            "customerId", "C-101",
            "orderId", "O-901")).consume();

    // Có thể kiểm tra thêm điều kiện và chạy lệnh khác tại đây.
    tx.commit();
}
~~~

Nếu một exception xảy ra trước `commit()` hoặc transaction đóng mà chưa commit, các thay đổi chưa commit được rollback. Khác với managed transaction, ứng dụng cần tự quản lý retry khi dùng explicit transaction.

### 7.4. Spring Data Neo4j và `@Transactional`

Trong ứng dụng Spring Data Neo4j dùng API đồng bộ, có thể đặt ranh giới trên **service method**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final CustomerRepository customerRepository;

    public OrderService(OrderRepository orderRepository,
                        CustomerRepository customerRepository) {
        this.orderRepository = orderRepository;
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void changeOrderOwner(String orderId, String customerId) {
        var order = orderRepository.findById(orderId).orElseThrow();
        var customer = customerRepository.findById(customerId).orElseThrow();

        // Minh họa: entity Order phải khai báo mapping của quan hệ owner.
        order.setOwner(customer);
        orderRepository.save(order);
    }
}
~~~

Ví dụ ở đây là **khung minh họa dịch vụ**: `OrderRepository`, `CustomerRepository` và entity có phương thức `setOwner` cần được khai báo theo mô hình domain của dự án. Trong triển khai thật, `@Transactional` hoạt động khi lời gọi đi qua cơ chế quản lý transaction của Spring và được cấu hình với **Neo4j transaction manager** thích hợp; gọi nội bộ một phương thức cùng bean có thể bỏ qua transaction proxy. Việc kết hợp Neo4j và một database khác, HTTP hoặc message broker **không tự tạo** một giao dịch phân tán ACID.

## 8. ACID khác lũy đẳng và causal consistency

Ba khái niệm thường xuất hiện cùng nhau trong hệ thống phân tán:

| Khái niệm | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| **ACID transaction** | Một tập thay đổi có commit/rollback đúng và được cô lập ở mức đã cam kết? | Tạo `Order` và `PLACED` cùng thành công |
| **Idempotency** | Cùng request được xử lý lại có gây thêm tác dụng ngoài ý muốn không? | Nhận lại `orderId=O-901` vẫn chỉ có một đơn |
| **Causal consistency** | Một thao tác sau có nhìn thấy những ghi đã được thao tác trước xác nhận trong chuỗi phụ thuộc không? | Đọc đơn vừa tạo ở session khác trong cluster với bookmark |

**Ví dụ:** Một giao dịch có thể hoàn toàn ACID khi tạo đơn `O-901`. Nhưng nếu client mất kết nối ngay sau khi server commit và gửi lại bằng `orderId` mới, hệ thống vẫn có thể tạo **hai đơn nghiệp vụ** trong hai giao dịch ACID riêng biệt. Để ngăn điều đó cần định danh ổn định, constraint hoặc cơ chế xử lý trùng thích hợp.

Ở chiều ngược lại, dùng `MERGE` nhiều lần mà chia các cập nhật quan trọng thành transaction riêng cũng có thể để lại **trạng thái nửa hoàn thành** nếu bước sau lỗi. Lũy đẳng không thay cho nguyên tử.

## 9. Bẫy thường gặp và cách tránh

### Bẫy 1: Chạy nhiều câu lệnh riêng rồi kỳ vọng rollback toàn bộ

~~~text
session.run("CREATE ...")       # implicit transaction số 1
session.run("CREATE ...")       # implicit transaction số 2
~~~

Nếu transaction thứ nhất đã commit, lỗi ở thứ hai không hủy thay đổi thứ nhất. Hãy dùng `executeWrite` hoặc explicit transaction khi hai thao tác là một nghiệp vụ.

### Bẫy 2: Xem kết quả không có hàng là lỗi transaction

`MATCH` không khớp có thể trả về 0 hàng mà không lỗi. Hãy kiểm tra kết quả, và nếu thiếu node là điều kiện thất bại, phát sinh exception **trong cùng transaction** để rollback các ghi liên quan.

### Bẫy 3: Làm công việc bên ngoài Neo4j trong callback có retry

Gửi email hoặc trừ tiền ở cổng thanh toán không rollback theo Neo4j. Dùng mô hình như **transactional outbox** (ghi dấu hiệu cần gửi trong cùng database transaction rồi xử lý bất đồng bộ với deduplication) hoặc saga/compensation khi tích hợp nhiều hệ thống.

### Bẫy 4: Hiểu read committed như serializable

Không có dirty read không có nghĩa là các lần đọc đều cố định hoặc mọi bất biến nghiệp vụ qua nhiều node được tự bảo vệ. Thiết kế locking/version và kiểm thử concurrency khi cần.

### Bẫy 5: Xem `CALL { ... } IN TRANSACTIONS` là một commit chung

Khi nhập dữ liệu theo lô, từng lô có transaction riêng, nên lô đã commit sẽ không tự bị rollback khi lô khác thất bại. Cần nhận diện lô, checkpoint, deduplication và khả năng chạy lại.

### Bẫy 6: Nghĩ commit thành công thay thế sao lưu

Transaction log và cơ chế phục hồi bảo vệ thay đổi đã commit theo phạm vi hệ thống lưu trữ, nhưng sự cố xóa nhầm dữ liệu, mất thiết bị hoặc lỗi vận hành vẫn đòi hỏi **backup, restore và diễn tập khôi phục**.

## 10. Bài thực hành và cách kiểm chứng

**Bối cảnh:** Khi tạo một đơn hàng, ứng dụng phải tạo đúng node `Order`, tạo cạnh từ `Customer` và ghi trạng thái xử lý. Hãy thực hiện các kịch bản sau trong môi trường thực hành:

1. Chuẩn bị `Customer`, đặt constraint duy nhất trên `Order.orderId` và chạy quy trình `executeWrite` ở phần 7. Xác nhận đơn và quan hệ được tạo đầy đủ.
2. Thử làm bước thứ hai ném exception **trước commit**. Kiểm tra `Order` và `PLACED` vừa tạo không tồn tại sau rollback; nên dùng một `orderId` mới cho mỗi phép thử.
3. Thử gửi lại cùng `orderId` sau một lần commit thành công. Quan sát lỗi constraint hoặc hành vi ứng dụng; thảo luận vì sao ACID không đồng nghĩa idempotency.
4. Mở hai transaction để đọc cùng một thuộc tính, rồi cho transaction khác commit cập nhật ở giữa hai lần đọc. Quan sát khả năng thấy giá trị thay đổi của read committed.
5. Đưa một lệnh nhập dữ liệu vào nhiều batch transaction rồi cố ý gây lỗi ở batch sau. Xác nhận các batch đã commit trước đó có thể còn dữ liệu.

Truy vấn kiểm tra đơn và quan hệ:

~~~cypher
MATCH (c:Customer {customerId: 'C-101'})
OPTIONAL MATCH (c)-[r:PLACED]->(o:Order {orderId: 'O-901'})
RETURN
  c.customerId AS customerId,
  count(r) AS placedRelationships,
  count(o) AS matchedOrders;
~~~

Nếu cần phân biệt đơn **không tồn tại** với đơn **tồn tại nhưng thiếu cạnh**, thực hiện thêm truy vấn độc lập:

~~~cypher
MATCH (o:Order {orderId: 'O-901'})
RETURN count(o) AS orderCount;
~~~

| Phép kiểm thử | Kết quả mong đợi |
| --- | --- |
| Một transaction ghi đầy đủ | Node, relationship và thuộc tính cùng xuất hiện |
| Có lỗi trước commit | Không có thay đổi một phần từ transaction thất bại |
| Lệnh vi phạm constraint | Transaction ghi thất bại, không commit dữ liệu sai |
| Đọc dữ liệu chưa commit từ transaction khác | Không nhìn thấy dirty data |
| Đọc lại sau khi transaction khác commit | Có thể thấy dữ liệu mới ở mức read committed |
| Client timeout gần thời điểm commit | Phải xác minh trạng thái trước khi retry, không đoán rollback |
| Nhập dữ liệu bằng nhiều batch transaction | Những batch đã commit có thể còn nguyên khi batch sau lỗi |

## 11. Checklist thiết kế transaction Neo4j

- Xác định **đơn vị nghiệp vụ cần commit cùng nhau**, gồm cả node, relationship và thuộc tính.
- Chọn rõ **managed** hay **explicit transaction**; không dựa vào nhiều implicit transaction nếu cần nguyên tử.
- Kiểm tra kết quả `MATCH`, validate input và tạo constraint phù hợp để bảo vệ dữ liệu ở cấp database.
- Phân tích **read committed**, cạnh tranh ghi, lost update và deadlock cho các bất biến liên quan nhiều phần tử.
- Thiết kế **ID ổn định và xử lý retry** cho request có thể đến nhiều lần; tránh side effect ngoài DB trong callback có retry.
- Dùng **bookmark** khi cần duy trì quan hệ nhân quả giữa các transaction/session trong cluster.
- Phân biệt batch transaction với giao dịch nguyên tử chung; chuẩn bị khả năng chạy lại khi nhập dữ liệu lớn.
- Kiểm tra rollback, concurrency, commit không rõ kết quả và backup/restore trên môi trường thử nghiệm.

**Kết luận:** ACID là nền tảng để Neo4j cập nhật property graph một cách tin cậy. **Atomicity** bảo vệ ranh giới commit/rollback; **Consistency** thực thi các ràng buộc đã khai báo; **Isolation** quy định cách các transaction tương tác khi chạy đồng thời; và **Durability** bảo vệ dữ liệu sau commit. Kết quả nghiệp vụ đúng còn đòi hỏi thiết kế khóa, invariant, retry và tích hợp hệ thống phù hợp với ranh giới transaction thực tế.
