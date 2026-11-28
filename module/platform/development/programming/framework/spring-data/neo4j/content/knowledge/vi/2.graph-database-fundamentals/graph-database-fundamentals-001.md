# Mô hình đồ thị thuộc tính và cách biểu diễn dữ liệu liên kết

Trong Neo4j, dữ liệu được tổ chức thành các **node** (nút) và **relationship** (mối quan hệ). Mỗi node và relationship có thể mang các thuộc tính dạng cặp khóa–giá trị. Cách tổ chức này được gọi là **đồ thị thuộc tính** (*property graph*). Nó phù hợp với những miền nghiệp vụ mà ý nghĩa của dữ liệu nằm nhiều ở cách các thực thể liên kết với nhau, chẳng hạn khách hàng mua sản phẩm, nhân viên làm việc trong phòng ban, hoặc tài khoản chuyển tiền cho tài khoản khác.

Spring Data Neo4j (SDN) ánh xạ mô hình đó vào các lớp Java: lớp được đánh dấu **@Node** đại diện cho node; trường được đánh dấu **@Relationship** biểu diễn liên kết; và lớp **@RelationshipProperties** mô tả những thuộc tính nằm trên chính mối quan hệ. Hiểu đúng mô hình đồ thị trước khi viết entity giúp thiết kế dữ liệu rõ nghĩa, tránh tạo các node dư thừa và giúp truy vấn Cypher đi theo đúng đường liên kết của nghiệp vụ.

Sau bài học, bạn có thể:

- Phân biệt node, label, property, relationship, hướng liên kết và path trong property graph.
- Quyết định dữ liệu nào nên là node, property của node hay property của relationship.
- Đọc một mô hình đồ thị và liên hệ nó với entity, relationship mapping trong Spring Data Neo4j.
- Viết Cypher cơ bản để tạo và duyệt dữ liệu liên kết, đồng thời nhận biết các điểm cần chú ý về định danh và hiệu năng.

## 1. Vì sao cần mô hình dữ liệu dưới dạng đồ thị?

Một hệ thống quản lý bán hàng có thể lưu khách hàng, sản phẩm và đơn hàng. Trong mô hình quan hệ, các bảng thường liên kết với nhau bằng khóa ngoại. Khi cần tìm sản phẩm mà một khách hàng đã mua, truy vấn phải kết hợp các bảng khách hàng, đơn hàng và chi tiết đơn hàng.

Trong mô hình đồ thị, các thực thể được biểu diễn trực tiếp bằng node và mối liên hệ được biểu diễn bằng relationship. Khi truy vấn, ứng dụng bắt đầu từ một node rồi đi theo các relationship phù hợp. Cấu trúc liên kết trở thành một phần của dữ liệu, thay vì chỉ là các giá trị khóa ngoại cần diễn giải qua nhiều phép nối.

Điều này hữu ích khi câu hỏi nghiệp vụ thường xoay quanh các đường đi: khách hàng đã mua sản phẩm nào, người dùng có chung kết nối nào, tài khoản nào có thể liên quan đến một giao dịch, hoặc thiết bị nào thuộc cùng một mạng. Đồ thị không tự động làm mọi truy vấn nhanh hơn; lợi ích xuất hiện khi cấu trúc và kiểu truy vấn thực sự khai thác quan hệ giữa các thực thể.

## 2. Các thành phần của property graph

### Node và label

Node biểu diễn một thực thể có thể nhận diện trong miền nghiệp vụ. Ví dụ: một khách hàng, sản phẩm, nhân viên hoặc thành phố. Node có thể mang một hay nhiều **label** để phân loại nó. Label thường dùng danh từ chỉ loại thực thể, như **Customer**, **Product** hoặc **City**.

Ví dụ:

~~~cypher
(:Customer {customerCode: 'C-100', name: 'An'})
~~~

Biểu thức trên mô tả một node có label **Customer** và hai property là **customerCode** và **name**. Dấu ngoặc tròn biểu diễn node; phần sau label trong dấu ngoặc nhọn là các property.

Label giúp truy vấn giới hạn loại node cần tìm. Một node có thể mang nhiều label nếu nó đồng thời thuộc nhiều nhóm phân loại. Tuy nhiên, không nên tạo label chỉ để thay thế một thuộc tính thông thường, chẳng hạn không cần tạo label riêng cho từng trạng thái đơn hàng nếu trạng thái chỉ là một giá trị có thể thay đổi.

### Property

Property là dữ liệu mô tả node hoặc relationship. Ví dụ, khách hàng có mã, tên và ngày đăng ký; sản phẩm có mã SKU, tên và giá niêm yết. Neo4j hỗ trợ các kiểu giá trị thuộc tính như chuỗi, số, boolean, ngày giờ và danh sách các giá trị được hỗ trợ.

Hãy đặt property ở nơi thể hiện đúng ý nghĩa của nó. **name** của khách hàng thuộc node **Customer**; **sku** thuộc node **Product**; còn **quantity** của một lần khách hàng mua sản phẩm có thể thuộc relationship giữa khách hàng và sản phẩm nếu mô hình chỉ cần lưu thông tin tổng hợp của liên kết đó.

Property không phải là một node độc lập. Nếu một giá trị cần có định danh riêng, có vòng đời riêng hoặc tham gia nhiều quan hệ khác, hãy cân nhắc mô hình nó thành node.

### Relationship, type và direction

Relationship kết nối hai node và luôn có một **type** mô tả ý nghĩa liên kết, thường dùng động từ hoặc cụm động từ như **PURCHASED**, **WORKS_IN**, **FOLLOWS**. Relationship có hướng từ node bắt đầu đến node đích. Trong Cypher, quan hệ có hướng được viết bằng mũi tên:

~~~cypher
(customer:Customer)-[:PURCHASED]->(product:Product)
~~~

Trong ví dụ này, **Customer** là node bắt đầu, **Product** là node đích và **PURCHASED** là type của relationship. Hướng giúp mô tả ý nghĩa nghiệp vụ nhất quán. Khi truy vấn, mẫu **(a)-[:TYPE]->(b)** chỉ khớp theo hướng từ **a** đến **b**; mẫu **(a)-[:TYPE]-(b)** có thể khớp theo cả hai hướng.

Relationship cũng có thể mang property. Ví dụ **PURCHASED** có thể lưu **quantity** và **purchasedAt**. Các property này mô tả chính lần liên kết giữa khách hàng và sản phẩm, không phải thuộc tính cố định của riêng khách hàng hay sản phẩm.

### Path

Path là một chuỗi node được nối với nhau bằng relationship. Ví dụ, từ khách hàng đi đến đơn hàng rồi đến sản phẩm tạo thành một path. Nhiều truy vấn đồ thị thực chất là tìm các path thỏa điều kiện về label, relationship type, hướng hoặc độ dài.

Mô hình đơn giản dưới đây biểu diễn một khách hàng đã mua một sản phẩm:

~~~mermaid
flowchart LR
    C["Customer<br/>customerCode: C-100<br/>name: An"]
    P["Product<br/>sku: KB-01<br/>name: Bàn phím"]
    C -->|PURCHASED, quantity=2| P
~~~

Node **Customer** và **Product** có thể tham gia nhiều relationship khác nhau. Một sản phẩm không cần được sao chép thành nhiều node chỉ vì nhiều khách hàng cùng mua nó. Mỗi khách hàng có thể kết nối đến cùng node sản phẩm bằng relationship riêng.

## 3. Chọn đúng cấu trúc để biểu diễn dữ liệu liên kết

Khi thiết kế property graph, hãy bắt đầu từ danh từ và động từ trong nghiệp vụ. Danh từ thường gợi ý các thực thể có thể là node; động từ thường gợi ý relationship. Sau đó xem xét vòng đời, định danh và thuộc tính của từng thành phần.

**Dùng node cho thực thể có danh tính riêng.** Khách hàng và sản phẩm có thể được tham chiếu từ nhiều nơi, có thuộc tính thay đổi độc lập và thường có mã định danh riêng. Vì vậy chúng phù hợp làm node.

**Dùng property cho giá trị mô tả một thực thể.** Tên sản phẩm, email khách hàng hoặc trạng thái hiện tại thường là property nếu chúng không cần được truy vấn như một thực thể độc lập.

**Dùng relationship cho liên kết có ý nghĩa nghiệp vụ.** **PURCHASED** thể hiện quan hệ khách hàng mua sản phẩm; **WORKS_IN** thể hiện nhân viên làm việc trong phòng ban. Một relationship nên có type rõ ràng, dễ đọc từ cả truy vấn lẫn sơ đồ dữ liệu.

**Dùng property của relationship cho thông tin thuộc về liên kết.** Số lượng mua, điểm đánh giá của một người dành cho một bộ phim, hoặc thời điểm một người bắt đầu theo dõi người khác là ví dụ về dữ liệu gắn với mối quan hệ. Đặt chúng lên node nguồn hoặc node đích sẽ làm sai ý nghĩa nếu giá trị thay đổi theo từng liên kết.

**Tạo node riêng khi sự kiện hoặc liên kết có vòng đời độc lập.** Ví dụ **PURCHASED** kèm **quantity** có thể phù hợp nếu hệ thống chỉ cần biểu diễn một quan hệ tổng hợp giữa khách hàng và sản phẩm. Nhưng nếu mỗi lần mua là một đơn hàng riêng, có mã đơn, thời điểm đặt, thanh toán, giao hàng và nhiều sản phẩm, nên mô hình **Order** thành node:

~~~cypher
(customer:Customer)-[:PLACED]->(order:Order)
(order)-[:CONTAINS {quantity: 2}]->(product:Product)
~~~

Như vậy mỗi đơn hàng có danh tính riêng, có thể mang trạng thái và liên kết với nhiều sản phẩm. Mô hình hóa theo sự kiện giúp tránh gộp nhiều lần mua khác nhau thành một relationship duy nhất.

**Chọn hướng liên kết theo ý nghĩa nghiệp vụ.** Hướng của relationship không nhất thiết phản ánh một chiều duy nhất mà người dùng được phép điều hướng. Nó là cách lưu và diễn giải quan hệ. Cypher có thể truy vấn ngược hướng khi cần, nhưng entity mapping trong SDN nên khai báo hướng rõ ràng để người đọc hiểu quan hệ bắt đầu từ đâu.

Cuối cùng, xác định định danh ổn định cho từng loại node. Nếu mã khách hàng là duy nhất và không đổi, có thể dùng nó làm định danh. Nếu không có khóa nghiệp vụ phù hợp, dùng định danh được sinh trong tầng dữ liệu. Với dữ liệu nghiệp vụ quan trọng, nên thiết lập uniqueness constraint để cơ sở dữ liệu ngăn các node trùng mã.

## 4. Ánh xạ property graph với Spring Data Neo4j

Spring Data Neo4j cung cấp annotation để mô tả cách lớp Java tương ứng với cấu trúc đồ thị. Một lớp entity thường đại diện cho node; các trường trong lớp chứa property hoặc các relationship được ánh xạ.

### Ánh xạ node bằng @Node

Ví dụ, **Customer** là node có label **Customer**. Mã khách hàng được dùng làm định danh:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.ArrayList;
import java.util.List;

@Node("Customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String customerCode;
    private String name;

    @Relationship(
        type = "PURCHASED",
        direction = Relationship.Direction.OUTGOING
    )
    private List<Purchase> purchases = new ArrayList<>();

    // Constructor và getter/setter được lược bớt.
}
~~~

**@Node("Customer")** khai báo label chính của node. **@Id** đánh dấu property định danh mà SDN dùng để nhận diện entity; **@GeneratedValue** yêu cầu SDN sinh giá trị cho trường **id**. **customerCode** vẫn được lưu như mã nghiệp vụ để tìm kiếm và trao đổi với hệ thống khác, đồng thời có thể được bảo vệ bằng uniqueness constraint.

Định danh nội bộ được sinh cho mục đích mapping không nên được xem là mã nghiệp vụ ổn định để trao đổi với hệ thống bên ngoài. Nếu chọn mã nghiệp vụ làm ID được gán từ ứng dụng, cần cấu hình version/optimistic locking phù hợp với phiên bản SDN đang dùng.

Các property đơn giản như **name** được ánh xạ thành property của node. Trường **purchases** biểu diễn các relationship **PURCHASED** đi ra từ node khách hàng. Khai báo hướng tường minh giúp tránh hiểu nhầm khi đọc mô hình.

### Ánh xạ node đích

Sản phẩm cũng là một node độc lập:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;
    private String name;

    // Constructor và getter/setter được lược bớt.
}
~~~

Một node **Product** có thể được kết nối với nhiều khách hàng. Mỗi relationship thể hiện một liên kết cụ thể, còn thông tin chung của sản phẩm chỉ lưu một lần trên node sản phẩm.

### Ánh xạ thuộc tính của relationship

Khi relationship có property, SDN cho phép mô tả nó bằng một lớp riêng được đánh dấu **@RelationshipProperties**:

~~~java
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.TargetNode;

import java.time.LocalDate;

@RelationshipProperties
public class Purchase {

    @RelationshipId
    private Long id;

    @TargetNode
    private Product product;

    private int quantity;

    private LocalDate purchasedAt;

    // Constructor và getter/setter được lược bớt.
}
~~~

**Purchase** không phải node. Đây là lớp mô tả relationship **PURCHASED**. **@RelationshipId** giữ định danh nội bộ để SDN nhận diện relationship hiện có khi cập nhật; **@TargetNode** chỉ ra node đích của relationship; **quantity** và **purchasedAt** là property nằm trên relationship. Trong **Customer**, collection **List<Purchase>** vì thế chứa các đối tượng quan hệ, mỗi đối tượng trỏ đến một **Product**.

Nếu relationship không có property riêng, trường quan hệ có thể tham chiếu trực tiếp đến entity đích, chẳng hạn **List<Product>**. Khi cần thêm dữ liệu lên liên kết, dùng lớp **@RelationshipProperties** sẽ thể hiện mô hình chính xác hơn.

SDN ánh xạ cấu trúc đồ thị thành object graph để ứng dụng làm việc bằng Java. Object graph có thể có vòng lặp vì node có thể kết nối qua lại theo nhiều đường. Do đó, chỉ khai báo các hướng quan hệ mà ứng dụng thực sự cần, tránh mô hình hai chiều không cần thiết khiến việc đọc, cập nhật hoặc tuần tự hóa object graph trở nên khó kiểm soát.

## 5. Biểu diễn và truy vấn dữ liệu bằng Cypher

Cypher là ngôn ngữ truy vấn khai báo của Neo4j. Cú pháp của nó thể hiện trực quan node bằng dấu ngoặc tròn, relationship bằng dấu ngoặc vuông và hướng bằng mũi tên.

Có thể tạo hoặc cập nhật ví dụ khách hàng và sản phẩm bằng **MERGE**:

~~~cypher
MERGE (c:Customer {customerCode: 'C-100'})
SET c.name = 'An'

MERGE (p:Product {sku: 'KB-01'})
SET p.name = 'Bàn phím'

MERGE (c)-[r:PURCHASED]->(p)
SET r.quantity = 2,
    r.purchasedAt = date('2026-11-01')
~~~

**MERGE** tìm một mẫu đã tồn tại hoặc tạo mẫu đó nếu chưa có. Trong ví dụ, nó giúp tránh tạo lại node có cùng mã và relationship cùng loại giữa đúng hai node. Tuy nhiên, mẫu **MERGE** relationship này phù hợp với quan hệ tổng hợp một khách hàng–một sản phẩm. Nếu một khách hàng có thể mua cùng sản phẩm trong nhiều đơn hàng khác nhau, hãy mô hình từng đơn hàng thành node riêng như phần trước; nếu không, nhiều sự kiện có thể bị gộp vào cùng một relationship.

Để tìm các sản phẩm khách hàng đã mua:

~~~cypher
MATCH (c:Customer {customerCode: $customerCode})
      -[r:PURCHASED]->(p:Product)
RETURN p.sku AS sku,
       p.name AS productName,
       r.quantity AS quantity,
       r.purchasedAt AS purchasedAt
~~~

**$customerCode** là tham số truy vấn. Dùng tham số giúp tái sử dụng câu lệnh và tránh ghép trực tiếp dữ liệu đầu vào vào chuỗi Cypher. **MATCH** mô tả mẫu đồ thị cần tìm; **RETURN** chọn dữ liệu trả về.

Trong repository, SDN hỗ trợ cả phương thức truy vấn dẫn xuất từ tên method và truy vấn Cypher tự viết bằng **@Query**. Khi trả về projection, các alias trong **RETURN** cần khớp với tên property hoặc getter của projection:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface PurchaseSummary {
    String getSku();
    String getProductName();
    Integer getQuantity();
}

public interface CustomerRepository
        extends Neo4jRepository<Customer, Long> {

    @Query("""
        MATCH (c:Customer {customerCode: $customerCode})
              -[r:PURCHASED]->(p:Product)
        RETURN p.sku AS sku,
               p.name AS productName,
               r.quantity AS quantity
        """)
    List<PurchaseSummary> findPurchaseSummary(
        @Param("customerCode") String customerCode
    );
}
~~~

Ví dụ trên minh họa truy vấn trả về dữ liệu đọc gọn qua projection. Khi truy vấn trả về entity thay vì projection, cần thiết kế phần **RETURN** phù hợp với quy tắc mapping của SDN và bảo đảm kết quả chứa các node, relationship cần thiết để dựng entity graph. Không nên giả định rằng chỉ trả về một node trong Cypher thì mọi quan hệ của node đó đều tự động được tải.

## 6. Ràng buộc dữ liệu và hiệu năng truy vấn

Property graph linh hoạt về cấu trúc, nhưng ứng dụng vẫn cần quy tắc dữ liệu rõ ràng. Với mã khách hàng duy nhất, có thể tạo uniqueness constraint:

~~~cypher
CREATE CONSTRAINT customer_code_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerCode IS UNIQUE
~~~

Tương tự, có thể tạo constraint cho **Product.sku**. Constraint giúp cơ sở dữ liệu bảo vệ tính duy nhất ngay cả khi nhiều luồng hoặc nhiều ứng dụng cùng ghi dữ liệu. Index trên property thường dùng để tìm kiếm cũng có thể giúp Neo4j định vị node hiệu quả hơn; hãy chọn index theo điều kiện truy vấn thực tế và phiên bản Neo4j đang sử dụng.

Một số nguyên tắc khi viết truy vấn:

- Bắt đầu từ label và property có điều kiện chọn lọc tốt, đặc biệt khi tìm node theo mã định danh.
- Khai báo rõ relationship type và hướng nếu nghiệp vụ yêu cầu một hướng cụ thể.
- Giới hạn độ dài đường đi và số lượng kết quả khi duyệt các mạng liên kết lớn.
- Chỉ trả về các node hoặc property mà ứng dụng cần, thay vì trả toàn bộ đồ thị.
- Dùng tham số cho dữ liệu đầu vào; dùng **EXPLAIN** để xem kế hoạch dự kiến và **PROFILE** để đo các bước thực thi khi tối ưu truy vấn.

Trong ứng dụng Spring, thao tác ghi nhiều node và relationship có liên quan cần được đặt trong ranh giới transaction phù hợp, thường ở tầng service. Transaction bảo đảm các thay đổi thuộc cùng một nghiệp vụ được commit hoặc rollback nhất quán; việc chọn đúng node và relationship vẫn là trách nhiệm của thiết kế mô hình.

## 7. Những lỗi mô hình hóa thường gặp

**Tạo node cho mọi thuộc tính.** Nếu mỗi tên, màu sắc hoặc trạng thái đều thành node, đồ thị sẽ có nhiều thành phần không mang danh tính riêng. Chỉ tạo node khi dữ liệu cần được tham chiếu, quản lý hoặc kết nối độc lập.

**Đặt thuộc tính của liên kết lên node.** Nếu **quantity** được lưu trên **Product**, hệ thống không thể biểu diễn số lượng khác nhau theo từng khách hàng hoặc từng đơn hàng. Hãy xác định property thuộc về thực thể hay relationship trước khi ánh xạ.

**Dùng một relationship để đại diện nhiều sự kiện.** Một cặp khách hàng–sản phẩm có thể có nhiều lần mua. Nếu từng lần mua cần được lưu, truy vấn hoặc cập nhật riêng, hãy tạo node **Order** hoặc node sự kiện tương ứng.

**Không thống nhất type và direction.** Các tên như **PURCHASED**, **BOUGHT** và **HAS_PURCHASE** có thể cùng diễn tả một ý nghĩa nhưng làm mô hình khó đọc và truy vấn thiếu nhất quán. Chọn một quy ước đặt tên và duy trì trong toàn bộ module.

**Dựa vào ID nội bộ như mã nghiệp vụ.** ID nội bộ phục vụ lưu trữ và mapping. Với tích hợp giữa các hệ thống, nên dùng mã nghiệp vụ ổn định và ràng buộc tính duy nhất cho mã đó.

**Khai báo quan hệ hai chiều chỉ vì object có thể tham chiếu ngược.** Relationship trong Neo4j đã có thể được duyệt theo cả hai chiều trong Cypher. Chỉ khai báo hai phía trong entity model khi ứng dụng cần truy cập object theo cả hai hướng và đã kiểm soát được phạm vi tải dữ liệu.

## 8. Tự kiểm tra

1. Trong biểu thức **(:Customer)-[:PURCHASED {quantity: 2}]->(:Product)**, thành phần nào là node, type và property của relationship?
2. Nếu một khách hàng có thể mua cùng sản phẩm trong nhiều đơn hàng và mỗi đơn có trạng thái thanh toán riêng, vì sao nên cân nhắc tạo node **Order**?
3. Trong SDN, annotation nào đánh dấu node entity, annotation nào mô tả relationship có property, và annotation nào chỉ node đích của relationship?
4. Vì sao nên dùng uniqueness constraint cho **customerCode** thay vì chỉ kiểm tra trùng mã trong Java?

**Bài tập thực hành:** Thiết kế đồ thị cho hệ thống học trực tuyến gồm **Student**, **Course** và việc đăng ký học. Xác định node, label, property và relationship type. Nếu mỗi lần đăng ký có ngày đăng ký, trạng thái và điểm cuối kỳ, hãy giải thích nên đặt các dữ liệu đó trên relationship hay tạo node **Enrollment**. Sau đó viết một mẫu Cypher để tìm các khóa học mà một học viên đã đăng ký và phác thảo các entity tương ứng bằng **@Node** và **@Relationship**.

Khi hoàn thành mô hình, hãy đọc sơ đồ theo hai chiều: từ mỗi node, các relationship đi ra thể hiện nó liên kết với loại thực thể nào; từ mỗi relationship, type, hướng và property cho biết chính xác nghiệp vụ nào đang được biểu diễn. Nếu một người mới đọc sơ đồ có thể hiểu các liên kết mà không cần suy đoán, mô hình đã có nền tảng tốt để triển khai bằng Spring Data Neo4j.
