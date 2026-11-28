# Lập kiểm thử hồi quy dữ liệu, giao dịch và hiệu năng trước nâng cấp

Một lần nâng cấp Spring Data Neo4j hoặc Neo4j DBMS có thể làm thay đổi cách ứng dụng ánh xạ entity, thực thi Cypher, quản lý transaction và sử dụng index. Ứng dụng khởi động thành công chưa chứng minh dữ liệu vẫn đúng hoặc các luồng nghiệp vụ vẫn hoạt động như trước. Cần có bộ kiểm thử hồi quy chạy trên bản sao dữ liệu đại diện và đúng tổ hợp phiên bản dự kiến triển khai.

Kiểm thử hồi quy trước nâng cấp có ba mục tiêu:

1. **Bảo toàn dữ liệu:** node, relationship, property, constraint và index vẫn đáp ứng các bất biến nghiệp vụ.
2. **Bảo toàn hành vi transaction:** commit, rollback, cập nhật đồng thời và đọc sau ghi vẫn đúng.
3. **Bảo toàn hiệu năng:** truy vấn và luồng nghiệp vụ quan trọng vẫn đáp ứng ngưỡng thời gian, throughput và tài nguyên đã thống nhất.

Sau bài học, bạn có thể:

- Lập ma trận tương thích giữa Neo4j DBMS, Spring Boot, Spring Data Neo4j, Java Driver và JDK.
- Tạo môi trường diễn tập từ backup hoặc dump của dữ liệu đại diện.
- Xây dựng các kiểm tra bất biến cho node, relationship, property và schema.
- Kiểm tra mapping entity, custom Cypher và dữ liệu relationship properties.
- Kiểm chứng rollback, optimistic locking, retry và tính nhất quán khi đọc/ghi.
- Đo baseline hiệu năng bằng workload, dữ liệu và cấu hình có thể so sánh.
- Phân tích query plan bằng EXPLAIN và PROFILE.
- Xác định tiêu chí chấp nhận, kế hoạch triển khai và phương án khôi phục.

## 1. Kiểm thử hồi quy phải bắt đầu từ ma trận phiên bản

Một ứng dụng Spring Data Neo4j không chỉ phụ thuộc phiên bản Neo4j server. Kết quả còn phụ thuộc phiên bản Spring Boot, Spring Data Neo4j (SDN), Neo4j Java Driver, JDK, plugin và cấu hình triển khai.

Trước khi thay đổi, ghi lại ít nhất các thành phần sau:

| Thành phần | Thông tin cần ghi |
|---|---|
| Neo4j DBMS | Phiên bản đầy đủ, edition, standalone hay cluster |
| Spring Boot | Phiên bản và dependency management đang sử dụng |
| Spring Data Neo4j | Phiên bản SDN và Spring Data release train |
| Neo4j Java Driver | Phiên bản Driver thực tế trong dependency tree |
| JDK | Phiên bản runtime và phiên bản dùng để build |
| Plugin/extension | APOC, Graph Data Science, custom procedure và phiên bản tương ứng |
| Database | Tên database, kích thước, số node/relationship, số lượng label/type chính |
| Schema | Constraint, index, trạng thái index và migration đã áp dụng |
| Runtime | Heap, page cache, CPU, RAM, disk, network và cấu hình connection pool |

Không nâng đồng thời tất cả thành phần rồi chỉ chạy một bài test tổng hợp. Khi kết quả thay đổi, rất khó xác định nguyên nhân nằm ở DBMS, Driver, SDN, Cypher hay JDK. Nếu lộ trình hỗ trợ cho phép, hãy kiểm thử theo từng bước thay đổi và giữ lại kết quả của từng bước.

### Xây dựng ma trận kiểm thử

Một ma trận tối thiểu có thể gồm:

| Neo4j DBMS | Ứng dụng | Mục đích |
|---|---|---|
| Phiên bản hiện tại | Ứng dụng hiện tại | Baseline để so sánh |
| Phiên bản hiện tại | Ứng dụng ứng viên | Tách ảnh hưởng khi nâng SDN, Driver hoặc JDK |
| Phiên bản đích | Ứng dụng ứng viên | Xác minh tổ hợp sẽ triển khai |
| Phiên bản đích | Ứng dụng hiện tại | Chỉ chạy nếu cần bảo đảm tương thích trong rollout hoặc rollback ứng dụng |

Không phải mọi tổ hợp đều được nhà cung cấp hỗ trợ. Chỉ chạy những tổ hợp có ý nghĩa với chiến lược triển khai và được xác nhận tương thích.

Neo4j Java Driver 6.x hiện hỗ trợ kết nối tới Neo4j 4.4.x, 5.x, 2025.x và 2026.x; Driver yêu cầu Java 17 trở lên. Điều đó không có nghĩa mọi phiên bản SDN đều hỗ trợ tất cả tổ hợp server này. Hãy kiểm tra ma trận và dependency được quản lý bởi đúng release của Spring Boot/SDN, rồi xác minh phiên bản Driver thực tế trong ứng dụng.

Neo4j chuyển sang calendar versioning từ 2025.01. Khi đường nâng cấp đi qua một mốc LTS, cần tuân theo các checkpoint và đường nâng cấp được tài liệu của đúng phiên bản chỉ định. Không suy luận rằng có thể nhảy trực tiếp giữa hai phiên bản chỉ vì Driver kết nối được với cả hai.

## 2. Chuẩn bị môi trường diễn tập từ dữ liệu thật

Test trên graph trống thường không phát hiện được lỗi về cardinality, dữ liệu cũ, property bị thiếu, relationship có hướng sai hoặc truy vấn chậm khi graph lớn. Môi trường diễn tập nên sử dụng bản sao dữ liệu có kích thước và phân bố gần với production.

Quy trình chuẩn bị:

1. Chọn một backup hoặc dump có thời điểm rõ ràng.
2. Khôi phục vào một Neo4j DBMS cô lập với phiên bản nguồn phù hợp.
3. Kiểm tra consistency của database hoặc backup.
4. Chạy ứng dụng và bộ regression hiện tại để xác nhận bản sao phản ánh đúng trạng thái baseline.
5. Tạo thêm một bản sao để thử nâng cấp, migration và kiểm thử ứng viên.
6. Ghi lại thời gian restore, migration, khởi động, kiểm tra dữ liệu và khôi phục.

Không chạy kiểm thử ghi dữ liệu trực tiếp trên database production. Nếu dữ liệu có thông tin nhạy cảm, hãy masking hoặc anonymize theo chính sách trước khi đưa vào môi trường test; việc masking cần giữ được quan hệ và phân bố dữ liệu đủ để kiểm thử.

### Kiểm tra consistency trước khi nâng cấp

Neo4j cung cấp lệnh quản trị:

~~~bash
neo4j-admin database check neo4j
~~~

Lệnh này kiểm tra consistency của database, dump hoặc full backup. Database cần ở trạng thái offline đối với lệnh kiểm tra này; không chạy trên database đang được sử dụng. Có thể dùng các tùy chọn kiểm tra graph, index, counts và property ownership theo yêu cầu kiểm tra.

Sau khi restore, chạy lại consistency check trước khi diễn tập nâng cấp. Nếu database nguồn đã có lỗi cấu trúc, kết quả regression sau nâng cấp sẽ khó phân biệt lỗi cũ với lỗi do phiên bản mới.

### Backup và rollback là một phần của bài test

Neo4j không hỗ trợ downgrade database sau khi nâng cấp. Nếu nâng cấp hoặc migration thất bại, phương án khôi phục DBMS là restore backup được tạo trước thay đổi. Vì vậy, diễn tập cần chứng minh backup có thể restore thành công, không chỉ chứng minh lệnh backup đã tạo ra file.

Ghi lại:

- Thời điểm và phiên bản nguồn của backup.
- Database và schema nằm trong backup.
- Phiên bản Neo4j có thể restore backup theo tài liệu.
- Thời gian restore và kiểm tra sau restore.
- Cách chuyển ứng dụng về endpoint/database đã khôi phục.
- Cách xử lý các ghi dữ liệu phát sinh sau thời điểm backup.

Nếu nâng cấp chỉ ứng dụng, rollback ứng dụng có thể đơn giản hơn. Nếu đã thay đổi store format hoặc thực hiện migration không tương thích ngược, không giả định chỉ cần deploy lại binary cũ là đủ.

## 3. Xác định bất biến dữ liệu cần bảo toàn

Một bộ kiểm thử dữ liệu tốt mô tả điều gì phải đúng với graph sau nâng cấp. Không nên chỉ so sánh tổng số node, vì cùng số lượng node vẫn có thể mất relationship, đổi property hoặc gắn sai label.

Chọn bất biến dựa trên nghiệp vụ:

| Nhóm dữ liệu | Ví dụ bất biến |
|---|---|
| Node | Mọi Order có business key; không có mã đơn trùng |
| Relationship | Mỗi Order phải liên kết với đúng Customer theo quy tắc |
| Relationship property | Số lượng, vai trò hoặc thời điểm trên relationship vẫn giữ nguyên |
| Property | Kiểu dữ liệu, giá trị null, enum và temporal value được ánh xạ đúng |
| Graph topology | Không mất đường đi quan trọng, không sinh relationship trùng |
| Schema | Constraint và index có đúng label/type, property và trạng thái |
| Nghiệp vụ | Tổng tiền, trạng thái, số đơn theo ngày và các aggregate không đổi ngoài delta đã dự kiến |

Nếu migration chủ đích thay đổi dữ liệu, viết rõ phép biến đổi kỳ vọng. Ví dụ property cũ được đổi tên, một relationship được tách thành hai loại hoặc dữ liệu được chuẩn hóa thành node mới. Khi đó, tiêu chí không phải hai snapshot giống hệt nhau mà là kết quả mới tương đương theo quy tắc chuyển đổi.

### Kiểm tra số lượng node và relationship

Ví dụ kiểm tra số đơn hàng:

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orderCount
~~~

Kiểm tra số relationship đặt hàng:

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationshipCount
~~~

Chạy cùng truy vấn trước và sau nâng cấp trên cùng snapshot. Nếu có thay đổi dữ liệu theo thiết kế, so sánh với số lượng kỳ vọng được tính từ migration.

### Kiểm tra business key và property bắt buộc

Tìm mã đơn bị thiếu hoặc trùng:

~~~cypher
MATCH (o:Order)
WITH o.orderCode AS code, count(*) AS total
WHERE code IS NULL OR total > 1
RETURN code, total
~~~

Truy vấn phải trả về rỗng nếu mọi Order có orderCode duy nhất. Nếu hệ thống dùng uniqueness constraint, hãy kiểm tra cả constraint metadata và thử ghi dữ liệu trùng trong môi trường test riêng để xác nhận constraint thực sự được thực thi.

### Kiểm tra relationship bị thiếu

Ví dụ mọi Order phải được đặt bởi một Customer:

~~~cypher
MATCH (o:Order)
WHERE NOT EXISTS {
    MATCH (:Customer)-[:PLACED]->(o)
}
RETURN o.orderCode AS orderWithoutCustomer
~~~

Truy vấn này phát hiện Order không có relationship PLACED đi vào. Với nghiệp vụ cho phép đơn hàng chưa gắn Customer, hãy giới hạn predicate theo trạng thái hoặc quy tắc cụ thể thay vì áp dụng bất biến cho toàn bộ dữ liệu.

### So sánh snapshot theo business key

Để so sánh sâu hơn, lấy projection có thứ tự ổn định:

~~~cypher
MATCH (c:Customer)-[r:PLACED]->(o:Order)
RETURN
    c.customerCode AS customerCode,
    type(r) AS relationshipType,
    r.placedAt AS placedAt,
    o.orderCode AS orderCode,
    o.status AS status,
    o.totalAmount AS totalAmount
ORDER BY customerCode, orderCode
~~~

Xuất kết quả trước và sau nâng cấp rồi so sánh theo business key và property nghiệp vụ. Nếu tạo checksum, hãy chuẩn hóa thứ tự, định dạng temporal value, số thập phân và giá trị null trước khi băm. Không dùng internal node ID hoặc internal relationship ID làm khóa so sánh vì chúng không phải định danh nghiệp vụ bền vững qua mọi quy trình migration/restore.

## 4. Kiểm thử schema và mapping của Spring Data Neo4j

Nâng cấp SDN hoặc Neo4j có thể ảnh hưởng mapping metadata, converter, custom query và cách hydrate graph. Regression cần đọc và ghi lại những entity đại diện cho các trường hợp mapping quan trọng.

### Kiểm tra constraint và index

Chụp metadata schema trước nâng cấp:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name
~~~

Và index:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state, owningConstraint
RETURN name, type, entityType, labelsOrTypes, properties, state, owningConstraint
ORDER BY name
~~~

Sau khi migration chạy trên phiên bản đích, so sánh schema với baseline hoặc schema mục tiêu. Index cần ở trạng thái ONLINE trước khi benchmark. Một index đang POPULATING có thể làm kết quả đo và query plan khác đáng kể.

### Kiểm tra mapping entity

Tạo test cho từng dạng property mà ứng dụng sử dụng:

- String, number, boolean và enum.
- Property tùy chọn có giá trị null hoặc không tồn tại.
- Temporal value, spatial value và custom converter.
- Entity có business ID hoặc ID do SDN tạo.
- Relationship một-một, một-nhiều, nhiều-nhiều.
- Relationship properties với annotation @RelationshipProperties.
- Entity có @Version để optimistic locking.

Đối với mỗi entity quan trọng, kiểm thử cả hai chiều: lưu entity rồi đọc lại; và đọc dữ liệu fixture đã có sẵn rồi xác minh entity được hydrate đúng. Chỉ test save có thể bỏ sót lỗi đọc hoặc lỗi mapping graph.

Không giả định relationship collection có thứ tự nếu nghiệp vụ không quy định thứ tự. Nếu thứ tự là yêu cầu, hãy lưu một thuộc tính thứ tự rõ ràng trên relationship hoặc entity liên quan và kiểm tra theo thuộc tính đó.

### Kiểm tra custom Cypher và kết quả mapping

Custom query có thể trả về nhiều record cho cùng một root node khi mở rộng qua relationship. SDN ánh xạ theo record; nếu query tạo một record cho mỗi relationship thì root entity có thể bị lặp hoặc graph không được hydrate đầy đủ.

Ví dụ truy vấn có thể gom các relationship và node liên quan vào một record:

~~~cypher
MATCH (c:Customer {customerCode: $customerCode})-[r:PLACED]->(o:Order)
RETURN c, collect(r) AS relationships, collect(o) AS orders
~~~

Với mỗi custom query, kiểm tra:

- Số root entity trả về.
- Không có root entity trùng ngoài dự kiến.
- Relationship đúng hướng và đúng type.
- Relationship properties có đủ giá trị.
- Entity liên quan được hydrate đầy đủ.
- Projection hoặc DTO giữ nguyên tên và kiểu cột mà code đang đọc.

Spring Data Neo4j có lưu ý riêng về custom query và việc gom relationship/node cho mapping. Khi nâng cấp, chạy lại các query này với dữ liệu có nhiều relationship để phát hiện lỗi Cartesian product hoặc record duplication.

## 5. Kiểm thử migration dữ liệu theo hướng có thể lặp lại

Một migration dữ liệu nên có đầu vào, quy tắc biến đổi và tiêu chí đầu ra rõ ràng. Trong môi trường diễn tập, chạy migration trên bản restore và xác minh kết quả trước khi áp dụng lên production.

Ví dụ migration đổi property:

~~~cypher
MATCH (o:Order)
WHERE o.legacyStatus IS NOT NULL
SET o.status = o.legacyStatus
REMOVE o.legacyStatus
RETURN count(o) AS migratedOrders
~~~

Không chạy ví dụ này nguyên trạng nếu dữ liệu có các quy tắc chuyển đổi khác. Cần xác định:

- Node nào nằm trong phạm vi migration.
- Dữ liệu thiếu hoặc sai kiểu được xử lý thế nào.
- Số bản ghi dự kiến được cập nhật.
- Có thể chạy lại migration an toàn hay không.
- Có checkpoint hoặc batch size nếu graph lớn hay không.
- Cách kiểm tra dữ liệu còn lại chưa được migrate.

Một migration idempotent có thể chạy lại mà không làm sai dữ liệu. Dùng predicate xác định rõ trạng thái trước/sau, business key và constraint để tránh tạo node hoặc relationship trùng. Nếu migration không idempotent, phải ghi lại trạng thái hoàn tất và có cơ chế ngăn chạy lặp.

Sau migration, chạy lại các truy vấn bất biến ở phần trước. Không chỉ kiểm tra số node được cập nhật; hãy kiểm tra cả giá trị mới, property cũ đã xử lý, relationship và aggregate nghiệp vụ.

## 6. Kiểm thử transaction và rollback

Transaction bảo đảm các thay đổi trong một đơn vị công việc được commit cùng nhau hoặc rollback khi thất bại. Regression cần xác minh ranh giới transaction thực tế mà service sử dụng.

Ví dụ service tạo Order và relationship trong cùng transaction:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final Neo4jClient neo4jClient;

    public OrderService(
            OrderRepository orderRepository,
            Neo4jClient neo4jClient) {
        this.orderRepository = orderRepository;
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public void createOrderThenFail(Order order, String customerCode) {
        orderRepository.save(order);

        neo4jClient.query("""
                MATCH (c:Customer {customerCode: $customerCode})
                MATCH (o:Order {orderCode: $orderCode})
                CREATE (c)-[:PLACED]->(o)
                """)
            .bind(customerCode).to("customerCode")
            .bind(order.getOrderCode()).to("orderCode")
            .run();

        throw new IllegalStateException("Simulated failure");
    }
}
~~~

Ví dụ giả định `Order` dùng `orderCode` làm business ID. Với kiểu định danh này, entity cần khai báo trường `@Version Long` như phần optimistic locking bên dưới để SDN quản lý trạng thái mới/cũ và kiểm tra cập nhật đồng thời.

Trong test tích hợp, gọi service trong một test không bọc transaction bên ngoài, xác nhận exception được ném, sau đó đọc bằng transaction mới và kiểm tra cả Order lẫn relationship đều không tồn tại. Điều này chứng minh hai thao tác tham gia cùng transaction Spring.

Ví dụ assertion trong test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Test
@Transactional(propagation = Propagation.NOT_SUPPORTED)
void rollsBackOrderAndRelationshipTogether() {
    Order order = new Order("ORD-ROLLBACK-01", "NEW");

    assertThatThrownBy(() ->
        orderService.createOrderThenFail(order, "CUS-01")
    ).isInstanceOf(IllegalStateException.class);

    assertThat(orderRepository.findById("ORD-ROLLBACK-01")).isEmpty();

    long relationshipCount = neo4jClient.query("""
            MATCH (:Customer {customerCode: $customerCode})
                  -[:PLACED]->
                  (:Order {orderCode: $orderCode})
            RETURN count(*) AS total
            """)
        .bind("CUS-01").to("customerCode")
        .bind("ORD-ROLLBACK-01").to("orderCode")
        .fetchAs(Long.class)
        .mappedBy((typeSystem, record) -> record.get("total").asLong())
        .one()
        .orElseThrow();

    assertThat(relationshipCount).isZero();
}
~~~

Đây là phần thân test; inject `orderService`, `orderRepository` và `neo4jClient` từ Spring test context, đồng thời cung cấp constructor tương ứng cho Order. Dùng business key riêng để test có thể chạy lặp lại.

Dùng Neo4jClient do SDN cấu hình khi cần tham gia transaction Spring. Một Driver session tự tạo ngoài transaction manager không tự động tham gia transaction mà service đang quản lý.

Nếu ứng dụng bắt lỗi bên trong service rồi tiếp tục trả về bình thường, transaction có thể commit tùy loại exception và cấu hình rollback. Kiểm tra rõ exception nào phải rollback; với checked exception, có thể cần khai báo rollbackFor theo quy tắc Spring.

## 7. Kiểm thử cập nhật đồng thời và optimistic locking

Khi hai request đọc cùng một entity rồi cập nhật độc lập, request thứ hai có nguy cơ ghi đè thay đổi mới hơn. SDN hỗ trợ optimistic locking qua @Version trên thuộc tính kiểu Long. Version được tăng tự động khi update; không tự gán giá trị version trong code nghiệp vụ.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Order")
public class Order {

    @Id
    private String orderCode;

    @Version
    private Long version;

    private String status;
}
~~~

Khi dùng business ID, @Version cũng cần thiết để SDN phân biệt entity mới và entity đã được lưu.

Test stale update:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Test
@Transactional(propagation = Propagation.NOT_SUPPORTED)
void rejectsUpdateBasedOnOldVersion() {
    Order first = orderRepository.findById("ORD-100").orElseThrow();
    Order stale = orderRepository.findById("ORD-100").orElseThrow();

    first.setStatus("PAID");
    orderRepository.save(first);

    stale.setStatus("CANCELLED");

    assertThatThrownBy(() -> orderRepository.save(stale))
        .isInstanceOf(OptimisticLockingFailureException.class);
}
~~~

Test dùng các thao tác repository trong transaction riêng để lần save đầu commit trước khi save stale. Trong test suite thực tế, bảo đảm dữ liệu ORD-100 được tạo trước test và cleanup theo fixture. Có thể mở rộng thành hai thread hoặc hai request độc lập để mô phỏng cạnh tranh gần production hơn.

Sau khi bắt OptimisticLockingFailureException, nghiệp vụ cần đọc lại entity với version mới, kiểm tra trạng thái và quyết định retry hay trả conflict. Không tự retry bằng entity cũ vì version của nó đã lỗi thời.

## 8. Kiểm thử retry, idempotency và tính nhất quán cluster

Neo4j Java Driver có thể retry managed transaction khi gặp lỗi được phân loại là transient. Vì callback có thể được chạy lại, code bên trong callback phải an toàn khi thực thi nhiều lần.

Các điểm cần kiểm thử:

- Một yêu cầu tạo Order không tạo hai Order khi transaction được retry.
- Một relationship không bị nhân đôi sau lần retry.
- Business key và uniqueness constraint ngăn ghi trùng.
- Tác động bên ngoài như gửi email hoặc publish message không bị lặp do callback được chạy lại.
- Nếu có outbox hoặc event sau commit, chỉ phát sự kiện khi transaction đã commit thành công.

Trong cluster, một transaction có thể commit ở một member và truy vấn đọc tiếp theo cần nhìn thấy thay đổi đó. Neo4j Driver quản lý causal consistency trong cùng session; với nhiều session hoặc transaction song song, cần kiểm thử bookmark nếu nghiệp vụ yêu cầu đọc sau ghi trên một session khác.

Không bật bookmark cho mọi tình huống mà không đo tác động. Bookmark có thể khiến transaction chờ dữ liệu được replicate tới trạng thái cần thiết và làm tăng latency. Hãy kiểm tra đúng mô hình session mà ứng dụng dùng.

## 9. Kiểm thử imperative và reactive riêng biệt

SDN cung cấp transaction manager imperative và reactive:

- Neo4jTransactionManager cho luồng imperative.
- ReactiveNeo4jTransactionManager cho luồng reactive.

Không dùng kết quả test imperative để kết luận reactive pipeline vẫn hoạt động đúng. Với reactive code, thao tác chỉ chạy khi publisher được subscribe. Test phải subscribe và chờ hoàn tất, ví dụ bằng StepVerifier.

Kiểm thử các trường hợp:

- Transaction reactive commit khi publisher hoàn tất thành công.
- Transaction reactive rollback khi publisher phát lỗi.
- Không thực thi query trước khi subscribe.
- Không subscribe cùng một publisher nhiều lần ngoài ý định.
- Không trộn blocking repository/Driver call vào reactive pipeline.
- Transaction manager reactive và cấu hình Driver tương ứng được khởi tạo trong application context.

Nếu ứng dụng không dùng reactive access, không cần thêm test reactive chỉ vì classpath có Reactor. Hãy tập trung vào mô hình truy cập thực tế.

## 10. Thiết lập baseline hiệu năng có thể so sánh

Hiệu năng sau nâng cấp chỉ có ý nghĩa khi điều kiện đo đủ giống baseline. Ghi lại cấu hình và dữ liệu cùng với kết quả, nếu không một thay đổi về page cache, kích thước graph hoặc phần cứng có thể bị hiểu nhầm là regression do code.

### Cố định điều kiện benchmark

Giữ nhất quán:

- Cùng snapshot dữ liệu hoặc cùng quy tắc tạo dữ liệu.
- Cùng số node, relationship, label/type và phân bố property.
- Cùng constraint và index; đợi index ONLINE.
- Cùng loại máy, CPU, RAM, disk, network và container limits.
- Cùng heap, page cache, connection pool và cấu hình Neo4j.
- Cùng JDK, workload và tham số truy vấn.
- Cùng trạng thái cache khi so sánh: warm với warm hoặc cold với cold.

Nếu môi trường không thể giống hoàn toàn, ghi rõ khác biệt và tránh kết luận dựa trên một con số latency đơn lẻ.

### Chọn workload đại diện

Chọn các luồng có ảnh hưởng tới người dùng hoặc vận hành:

| Nhóm workload | Ví dụ |
|---|---|
| Point lookup | Tìm Order theo orderCode |
| Filter và range | Tìm đơn theo status, createdAt |
| Traversal | Lấy Customer cùng các Order và Product liên quan |
| Aggregation | Đếm đơn theo trạng thái hoặc doanh thu theo tháng |
| Write | Tạo Order và relationship, cập nhật trạng thái |
| Batch | Nạp hoặc cập nhật nhiều node/relationship |
| Concurrency | Nhiều request cập nhật cùng loại entity |

Dùng tham số đại diện cho cả trường hợp phổ biến và trường hợp dữ liệu lớn. Một query chỉ chạy nhanh với một customer có ít relationship chưa chứng minh nó hoạt động tốt với customer có degree rất cao.

### Chỉ số nên ghi lại

Ở tầng ứng dụng:

- Throughput (request hoặc transaction mỗi giây).
- Latency p50, p95 và p99.
- Tỷ lệ lỗi, timeout và retry.
- CPU, heap, garbage collection và connection pool saturation.

Ở tầng Neo4j:

- Thời gian thực thi query.
- Số row và DB hits.
- Bộ nhớ query và operator có chi phí cao.
- Index được sử dụng.
- Page cache hits/misses nếu edition và công cụ đo hỗ trợ; cột page cache trong PROFILE chỉ có trên Enterprise Edition.
- Transaction timeout, lock wait và deadlock nếu workload có ghi đồng thời.

Đo cả thời gian end-to-end và thời gian query riêng. End-to-end bao gồm network, connection pool, mapping entity và serialization; query-only giúp xác định phần chi phí nằm trong DBMS.

Không dùng một ngưỡng phần trăm cố định cho mọi ứng dụng. Hãy định nghĩa budget theo SLO của từng luồng, ví dụ p95 phải thấp hơn giới hạn nghiệp vụ, throughput phải đáp ứng tải đỉnh và tỷ lệ lỗi không vượt mức chấp nhận.

Ghi kết quả vào một bảng so sánh cố định để tránh chọn số liệu thuận lợi từ từng lần chạy:

| Kịch bản | Baseline p95 | Ứng viên p95 | Baseline throughput | Ứng viên throughput | Ngưỡng | Kết quả |
|---|---:|---:|---:|---:|---|---|
| Tìm Order theo business key |  |  |  |  | Theo SLO |  |
| Lấy Customer cùng graph liên quan |  |  |  |  | Theo SLO |  |
| Tạo Order và relationship |  |  |  |  | Theo SLO |  |
| Truy vấn aggregate |  |  |  |  | Theo SLO |  |

Đính kèm số lần chạy, kích thước graph, trạng thái cache, cấu hình máy và tỷ lệ lỗi. Dùng median hoặc percentile của nhiều lần chạy thay vì lấy một lần chạy đơn lẻ.

## 11. So sánh query plan bằng EXPLAIN và PROFILE

EXPLAIN tạo kế hoạch thực thi dự kiến nhưng không chạy truy vấn. PROFILE thực thi truy vấn và trả số liệu thực tế như rows, DB hits, memory và thông tin page cache trong các trường hợp được hỗ trợ.

Ví dụ truy vấn tìm đơn theo trạng thái và thời điểm:

~~~cypher
EXPLAIN
MATCH (o:Order)
WHERE o.status = $status
  AND o.createdAt >= $from
RETURN o
ORDER BY o.createdAt
~~~

Sau đó, trên database test có dữ liệu đại diện, dùng PROFILE:

~~~cypher
PROFILE
MATCH (o:Order)
WHERE o.status = $status
  AND o.createdAt >= $from
RETURN o
ORDER BY o.createdAt
~~~

PROFILE thực thi câu lệnh. Nếu dùng với truy vấn ghi, dữ liệu có thể bị thay đổi; chỉ chạy trên bản sao test hoặc truy vấn đã được bảo đảm an toàn.

Khi so sánh plan, chú ý:

- Truy vấn có dùng index seek/scan phù hợp hay chuyển sang label scan.
- Estimated Rows có sai lệch lớn so với Rows thực tế không.
- DB hits có tăng bất thường không.
- Có operator expand hoặc sort tạo lượng row trung gian lớn không.
- Memory allocation hoặc page cache misses có tăng không.
- Kết quả cuối có cùng cardinality và giá trị với baseline không.

Không khóa test vào tên operator hoặc plan tree chính xác. Planner có thể thay đổi theo phiên bản, thống kê, index và phân bố dữ liệu. Hãy so sánh xu hướng chi phí, kết quả và ngưỡng hiệu năng. DB hits là đơn vị công việc trừu tượng của storage engine, không phải thời gian millisecond.

Không so sánh kết quả page cache giữa lần chạy cold-cache và warm-cache. Lần đầu có thể đọc nhiều dữ liệu từ disk; các lần sau có thể dùng cache nên latency và page cache misses khác nhau.

## 12. Phân tích nguyên nhân khi có regression

Khi test thất bại, phân loại trước khi sửa:

| Dấu hiệu | Khu vực cần kiểm tra |
|---|---|
| Số node hoặc relationship thay đổi | Migration dữ liệu, import, constraint và query ghi |
| Business key trùng hoặc thiếu | Logic migration, dữ liệu cũ và uniqueness constraint |
| Entity đọc thiếu relationship | Mapping metadata, hướng relationship, custom query và record aggregation |
| Save tạo node mới thay vì update | ID mapping, business ID và @Version |
| Rollback không xóa mọi thay đổi | Transaction boundary, client/Driver không tham gia transaction Spring |
| Optimistic lock tăng bất thường | Luồng cập nhật đồng thời hoặc entity stale |
| Query plan chuyển sang scan | Index thiếu/không ONLINE, predicate thay đổi hoặc statistics |
| DB hits tăng nhưng latency chưa tăng | Graph lớn hơn, plan khác hoặc cache đang ấm |
| Latency tăng nhưng DB hits tương tự | Network, JVM, mapping, pool, disk hoặc contention |
| Chỉ cluster test lỗi đọc sau ghi | Session boundary, bookmark và causal consistency |

Giữ lại log, query plan, cấu hình và snapshot dùng để tái hiện. Một regression chỉ được xem là xử lý xong khi test ban đầu chạy lại thành công và các bất biến liên quan vẫn đạt.

## 13. Quy trình diễn tập nâng cấp đầu-cuối

Một đợt rehearsal có thể triển khai theo trình tự:

1. **Chốt baseline:** ghi phiên bản, cấu hình, schema, data invariants và performance metrics.
2. **Khôi phục dữ liệu:** tạo bản sao từ backup/dump và kiểm tra consistency.
3. **Chạy baseline test:** xác nhận bộ regression hiện tại xanh trên phiên bản nguồn.
4. **Nâng ứng dụng:** thử phiên bản Boot/SDN/Driver/JDK ứng viên với DBMS nguồn nếu tổ hợp được hỗ trợ.
5. **Nâng DBMS:** áp dụng đúng đường nâng cấp, checkpoint LTS và migration cần thiết.
6. **Kiểm tra schema:** xác minh constraint, index, plugin và trạng thái ONLINE.
7. **Chạy regression dữ liệu:** so sánh counts, business keys, relationship, properties và graph snapshot.
8. **Chạy regression transaction:** rollback, concurrency, optimistic locking, retry và read-after-write.
9. **Chạy performance suite:** warm-up, workload chuẩn, p50/p95/p99, throughput, errors và query plan.
10. **Diễn tập rollback:** restore backup trước nâng cấp, kiểm tra consistency và xác nhận ứng dụng cũ kết nối lại.

Neo4j khuyến nghị diễn tập quy trình nâng cấp và kiểm tra tương thích với hệ thống khác trong môi trường test trước khi thay đổi production. Với cluster, cần diễn tập theo topology và thực hiện checklist trên từng thành viên.

### Tiêu chí cho phép triển khai

Chỉ thông qua khi:

- Mọi đường nâng cấp đều được hỗ trợ và đã diễn tập.
- Backup có thể restore và consistency check đạt.
- Data invariants đạt hoặc delta đúng với migration đã phê duyệt.
- Repository, custom Cypher và entity mapping trả dữ liệu đúng.
- Transaction commit/rollback và concurrency đạt.
- Index/constraint đúng schema và index cần thiết đã ONLINE.
- Workload quan trọng nằm trong performance budget.
- Plugin/extension tương thích với phiên bản DBMS đích.
- Có kế hoạch giám sát, rollback và người chịu trách nhiệm khi rollout.

Nếu chỉ tiêu hiệu năng không đạt, không nên lấy việc mọi test chức năng đều xanh làm lý do bỏ qua. Cần phân tích plan, số liệu và workload, sau đó quyết định tối ưu hoặc điều chỉnh năng lực triển khai trước khi phát hành.

## 14. Những lỗi thường gặp

**Chỉ kiểm thử ứng dụng khởi động.** Kết nối thành công không chứng minh mapping, transaction hoặc query đúng. Chạy regression trên graph có dữ liệu đại diện.

**Chỉ so sánh tổng số node.** Số lượng có thể giống nhưng relationship hoặc property đã thay đổi. So sánh theo business key, relationship và aggregate nghiệp vụ.

**Dùng internal ID làm khóa snapshot.** Internal ID không phải business identifier. So sánh bằng mã nghiệp vụ ổn định.

**Nâng DBMS và SDN cùng lúc mà không có baseline trung gian.** Khi lỗi xảy ra khó tìm nguyên nhân. Kiểm thử theo ma trận phiên bản và từng bước thay đổi được hỗ trợ.

**Bỏ qua plugin và extension.** APOC hoặc procedure riêng có thể không tương thích với DBMS đích. Kiểm tra version và chạy lại truy vấn phụ thuộc extension.

**Không diễn tập restore.** Có file backup không đồng nghĩa có thể khôi phục đúng thời gian và đúng phiên bản. Hãy thực hiện restore rehearsal.

**Cho rằng có thể downgrade Neo4j sau nâng cấp.** Neo4j không hỗ trợ downgrade database. Chuẩn bị backup/restore trước thay đổi.

**Kiểm tra rollback trong transaction test bên ngoài.** Transaction ngoài có thể che khuất ranh giới transaction của service. Dùng transaction độc lập để xác minh dữ liệu đã commit hay rollback.

**Không kiểm thử stale entity.** Hai request có thể ghi đè nhau. Kiểm thử @Version và xử lý OptimisticLockingFailureException.

**Callback retry gây side effect lặp.** Transaction function có thể chạy lại khi gặp lỗi transient. Giữ callback idempotent và chỉ phát tác động ngoài sau commit.

**Đo performance với cache không giống nhau.** So sánh cold với warm tạo kết luận sai. Chuẩn hóa cache state và ghi lại cấu hình.

**Dùng PROFILE trên dữ liệu production.** PROFILE thực thi truy vấn và có thể ghi dữ liệu. Dùng database test hoặc truy vấn chỉ đọc an toàn.

**Khẳng định query plan phải giống hệt.** Planner có thể thay đổi. So sánh chi phí thực tế, kết quả và performance budget.

## 15. Tự kiểm tra

1. Vì sao cần ma trận phiên bản thay vì chỉ kiểm tra Neo4j DBMS?
2. Driver 6.x hỗ trợ những nhóm phiên bản Neo4j server nào và vì sao điều đó chưa đủ để kết luận một bản SDN tương thích?
3. Vì sao phải restore dữ liệu đại diện vào môi trường cô lập trước khi diễn tập?
4. Lệnh neo4j-admin nào kiểm tra consistency và tại sao cần chạy khi database offline?
5. Vì sao không nên so sánh internal node ID trước và sau migration?
6. Những bất biến nào cần kiểm tra ngoài số lượng node?
7. Vì sao custom query của SDN cần chú ý số record cho mỗi root node?
8. Làm thế nào để kiểm chứng rollback khi service ghi qua repository và Neo4jClient?
9. @Version phát hiện stale update như thế nào?
10. Vì sao transaction callback cần idempotent khi Driver retry?
11. EXPLAIN khác PROFILE ở điểm nào?
12. Vì sao không so sánh page cache metrics giữa hai lần chạy có cache state khác nhau?
13. Nếu Neo4j upgrade thất bại, vì sao phương án rollback phải dựa trên restore backup?

**Bài tập thực hành:** Tạo một bản sao database có dữ liệu Customer, Order, Product và các relationship PLACED, CONTAINS. Ghi baseline gồm số node/relationship, business key trùng, Order không có Customer, schema metadata và kết quả projection theo business key. Chạy bộ test repository để kiểm tra mapping, custom Cypher và relationship properties. Viết test rollback cho service tạo Order, test optimistic locking bằng hai bản entity cùng version và test đọc sau ghi. Sau đó chạy cùng workload trên phiên bản DBMS/SDN hiện tại và phiên bản ứng viên; ghi p50, p95, throughput, error rate, DB hits, rows và query plan. Cuối cùng, diễn tập restore backup trước nâng cấp và lập bảng kết quả PASS/FAIL cùng các regression cần xử lý.

## Tài liệu tham khảo

- [Neo4j Upgrade and Migration Guide — Introduction and preparation](https://neo4j.com/docs/upgrade-migration-guide/current/)
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual — Check database consistency](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/)
- [Neo4j Java Driver Manual — Installation and server compatibility](https://neo4j.com/docs/java-manual/current/install/)
- [Neo4j Java Driver Manual — Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Coordinate parallel transactions with bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Cypher Manual — Understanding query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Spring Data Neo4j — Supported versions and release documentation](https://docs.spring.io/spring-data/neo4j/reference/)
- [Spring Data Neo4j — Optimistic locking with @Version](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j — Custom queries and relationship mapping](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j — Neo4jClient and transaction integration](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
