# Vì sao đồ thị linh hoạt vẫn cần schema và ràng buộc?

Neo4j thường được mô tả là cơ sở dữ liệu đồ thị linh hoạt hoặc schemaless. Một node có thể có các property khác với node khác cùng label; một relationship có thể mang property riêng; ứng dụng có thể thêm label hoặc loại quan hệ mới mà không phải thay đổi cấu trúc bảng theo cách của cơ sở dữ liệu quan hệ.

Tuy nhiên, **linh hoạt không có nghĩa là không cần quy tắc dữ liệu**. Một hệ thống thực tế vẫn cần xác định node nào đại diện cho loại thực thể nào, property nào là định danh nghiệp vụ, giá trị nào bắt buộc, quan hệ nào cần được giữ nhất quán và truy vấn nào phải chạy hiệu quả khi graph tăng trưởng. Schema, constraint và index giải quyết những nhu cầu khác nhau đó.

Trong Spring Data Neo4j (SDN), entity mapping mô tả cách Java object tương ứng với node và relationship. Cơ sở dữ liệu Neo4j vẫn cần constraint để bảo vệ tính toàn vẹn và index để tìm dữ liệu hiệu quả. SDN hiện đại không tự tạo index hoặc constraint chỉ từ các annotation entity; nhóm schema cần được quản lý bằng Cypher và quy trình migration có kiểm soát.

Sau bài học, bạn có thể:

- Phân biệt schema linh hoạt của property graph với các quy ước miền của ứng dụng.
- Giải thích vai trò riêng của entity mapping, constraint và index.
- Chọn uniqueness, existence, type hoặc key constraint cho từng quy tắc dữ liệu.
- Tạo và kiểm tra index phù hợp với mẫu truy vấn.
- Hiểu vì sao SDN mapping annotation không thay thế schema của Neo4j.
- Quản lý constraint và index bằng migration, kiểm tra dữ liệu hiện có và theo dõi trạng thái index.

## 1. Đồ thị linh hoạt có nghĩa là gì?

Neo4j lưu dữ liệu dưới dạng node, relationship và property:

~~~mermaid
flowchart LR
    P["(:Person)"] -->|"[:PLACED {at, channel}]"| O["(:Order)"]
    O -->|"[:CONTAINS {quantity, unitPrice}]"| I["(:Product)"]
    P --- N["name, email, city"]
    O --- D["orderCode, placedAt"]
    I --- S["sku, title, price"]
~~~

Một số đặc điểm của mô hình property graph:

- Node có thể có một hoặc nhiều label.
- Relationship có kiểu và hướng; nó nối hai node và có thể mang property.
- Property không bắt buộc phải xuất hiện trên mọi node cùng label.
- Hai node cùng label có thể có tập property khác nhau.
- Có thể mở rộng graph bằng label, relationship type hoặc property mới mà không cần khai báo trước một bộ cột cố định.

Ví dụ, hai node `Person` có thể có dữ liệu:

~~~cypher
CREATE
    (:Person {
        personCode: 'P-100',
        name: 'An',
        email: 'an@example.com'
    }),
    (:Person {
        personCode: 'P-200',
        name: 'Binh',
        city: 'Da Nang',
        phone: '0900000000'
    })
~~~

Neo4j cho phép cả hai node cùng label `Person` dù node thứ nhất không có `city`, còn node thứ hai không có `email`. Sự linh hoạt này hữu ích khi dữ liệu đến từ nhiều nguồn hoặc mô hình miền thay đổi theo thời gian.

Nhưng nếu `personCode` là mã định danh nghiệp vụ, hai node `Person` không được phép có cùng mã. Nếu ứng dụng luôn cần email để gửi thông báo, việc thiếu email cũng phải được kiểm soát. Đó là lúc constraint trở nên cần thiết.

## 2. Bốn lớp quy tắc thường bị nhầm lẫn

| Lớp | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Mô hình miền | Ứng dụng có những loại thực thể và quan hệ nào? | Person, Order, Product, PLACED, CONTAINS |
| Entity mapping của SDN | Java object được ánh xạ thành node/relationship ra sao? | `@Node`, `@Relationship`, `@Property`, `@Id` |
| Constraint của Neo4j | Dữ liệu nào được phép tồn tại? | `Person.personCode` phải duy nhất |
| Index của Neo4j | Cần tìm dữ liệu bằng đường truy cập nào? | Index cho `Person.personCode` hoặc `Product.sku` |

Các lớp này bổ sung cho nhau. `@Node("Person")` cho SDN biết label cần ánh xạ; nó không tự yêu cầu mọi node `Person` phải có `email`. `@Id` xác định định danh persistence của entity; nó không tự tạo uniqueness constraint trên một mã nghiệp vụ như `personCode`.

Một thiết kế thường có:

- Mô hình Java mô tả các property và relationship mà ứng dụng sử dụng.
- Constraint bảo vệ quy tắc quan trọng ngay tại database, kể cả khi dữ liệu được ghi bởi Cypher, import job hoặc ứng dụng khác.
- Index giúp Cypher tìm các ứng viên nhanh hơn khi truy vấn phù hợp.

## 3. Vì sao vẫn cần schema và constraint?

### Bảo vệ định danh và tránh dữ liệu trùng

Giả sử `personCode` là mã duy nhất của một người. Nếu chỉ kiểm tra bằng Java trước khi tạo node, hai request đồng thời vẫn có thể cùng đọc thấy chưa tồn tại rồi cùng tạo một node. Constraint duy nhất được kiểm tra tại database sẽ ngăn hai transaction ghi cùng giá trị.

### Bảo đảm dữ liệu bắt buộc

Một node `Order` cần `orderCode` và `createdAt` để các nghiệp vụ khác có thể tham chiếu. Nếu thiếu property, lỗi có thể chỉ xuất hiện ở một truy vấn hoặc báo cáo chạy sau đó. Existence constraint phát hiện vấn đề ngay khi dữ liệu được ghi.

### Giữ kiểu dữ liệu nhất quán

Property `price` được kỳ vọng là số. Nếu một luồng import vô tình ghi chuỗi "100" trong khi luồng khác ghi số 100, truy vấn so sánh, tính toán và lập kế hoạch có thể cho kết quả khó đoán. Property type constraint có thể giới hạn kiểu dữ liệu được phép.

### Tạo hợp đồng giữa nhiều writer

Một graph có thể được ghi bởi nhiều service, batch import, công cụ quản trị hoặc Cypher trực tiếp. Quy tắc chỉ nằm trong một service không thể bảo vệ dữ liệu trước các writer khác. Constraint được thực thi tại Neo4j và trở thành hợp đồng dùng chung.

### Hỗ trợ hiệu năng khi graph tăng trưởng

Không có index phù hợp, Neo4j có thể phải duyệt nhiều node để tìm điểm bắt đầu cho truy vấn. Khi số node tăng, chi phí lọc có thể tăng theo. Index giúp planner tìm các ứng viên nhanh hơn; constraint uniqueness cũng có index hỗ trợ để kiểm tra trùng lặp hiệu quả.

## 4. Các loại constraint trong Neo4j

Neo4j hỗ trợ constraint cho node theo label và relationship theo type. Các constraint phổ biến:

| Loại constraint | Bảo đảm | Lưu ý |
|---|---|---|
| Property uniqueness | Giá trị property hoặc tổ hợp property không bị trùng | Không bắt buộc property phải tồn tại |
| Property existence | Property phải có mặt | Neo4j Enterprise Edition |
| Property type | Property phải có kiểu được khai báo | Neo4j Enterprise Edition |
| Key | Property phải tồn tại và giá trị phải duy nhất | Neo4j Enterprise Edition |

Constraint áp dụng cho các node có label hoặc relationship có type được chỉ định. Một constraint `Person` không tự áp dụng cho node chỉ có label `Customer`, trừ khi node đó cũng có label `Person`.

### Uniqueness constraint

Ví dụ yêu cầu mọi node `Person` có `personCode` không trùng nhau:

~~~cypher
CREATE CONSTRAINT person_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personCode IS UNIQUE
~~~

Với relationship, có thể bảo đảm một property duy nhất theo relationship type:

~~~cypher
CREATE CONSTRAINT membership_code_unique IF NOT EXISTS
FOR ()-[r:MEMBER_OF]-()
REQUIRE r.membershipCode IS UNIQUE
~~~

Có thể tạo composite uniqueness constraint trên nhiều property:

~~~cypher
CREATE CONSTRAINT person_tenant_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.personCode) IS UNIQUE
~~~

Quy tắc trên chỉ yêu cầu tổ hợp `tenantId` và `personCode` duy nhất trong các node `Person` có đủ các property đó.

**Điểm dễ nhầm:** uniqueness constraint không bắt buộc mọi node phải có property. Node `Person` không có `personCode` không bị vi phạm uniqueness constraint này. Nếu cần property luôn có mặt, hãy dùng existence constraint hoặc key constraint khi edition hỗ trợ.

### Existence constraint

Existence constraint bảo đảm property luôn tồn tại trên node hoặc relationship thuộc label/type được chọn:

~~~cypher
CREATE CONSTRAINT order_code_required IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderCode IS NOT NULL
~~~

Hoặc bắt buộc relationship `CONTAINS` có property `quantity`:

~~~cypher
CREATE CONSTRAINT contains_quantity_required IF NOT EXISTS
FOR ()-[r:CONTAINS]-()
REQUIRE r.quantity IS NOT NULL
~~~

Property existence constraint chỉ khả dụng trên Neo4j Enterprise Edition. Nếu dùng Community Edition, cần kiểm tra và xác thực ở tầng ứng dụng hoặc quy trình ghi dữ liệu.

### Property type constraint

Type constraint giới hạn kiểu property:

~~~cypher
CREATE CONSTRAINT product_price_type IF NOT EXISTS
FOR (p:Product)
REQUIRE p.price IS :: FLOAT
~~~

Ví dụ trên yêu cầu `price` là giá trị kiểu FLOAT. Tùy mô hình, có thể chọn `INTEGER`, `STRING`, `DATE`, `LOCAL DATETIME`, `POINT` và các kiểu Neo4j hỗ trợ khác. Type constraint cũng thuộc Neo4j Enterprise Edition.

Khi dùng tiền tệ, cần quyết định rõ cách biểu diễn. Ví dụ lưu giá theo số nguyên đơn vị nhỏ nhất (như cents) giúp tránh sai số dấu phẩy động; khi đó type constraint có thể là `INTEGER`.

### Key constraint

Key constraint kết hợp hai điều kiện: property phải tồn tại và giá trị phải duy nhất:

~~~cypher
CREATE CONSTRAINT person_code_key IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personCode IS NODE KEY
~~~

Với composite key:

~~~cypher
CREATE CONSTRAINT person_tenant_code_key IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.personCode) IS NODE KEY
~~~

Key constraint phù hợp khi tổ hợp property vừa là định danh nghiệp vụ vừa bắt buộc phải có. Nó chỉ khả dụng trên Neo4j Enterprise Edition.

## 5. Constraint không thay thế index, và index không thay thế constraint

Constraint và index có mục đích khác nhau:

- Constraint xác định dữ liệu nào được phép ghi.
- Index cung cấp đường truy cập để tìm dữ liệu nhanh hơn.
- Uniqueness và key constraint được hỗ trợ bởi range index. Khi xóa constraint, index backing của nó cũng bị xóa.
- Một index thông thường không bảo đảm dữ liệu duy nhất.

Ví dụ, nếu truy vấn thường xuyên tìm sản phẩm theo `sku`, có thể tạo uniqueness constraint:

~~~cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE
~~~

Constraint này vừa bảo đảm `sku` không trùng, vừa có range index backing để hỗ trợ lookup. Không tạo thêm range index giống hệt trên cùng label và property; Neo4j không cho tạo index xung đột với backing index của constraint.

Nếu truy vấn lọc theo `city` nhưng `city` không cần duy nhất, dùng index:

~~~cypher
CREATE INDEX person_city IF NOT EXISTS
FOR (p:Person)
ON (p.city)
~~~

Index này không ngăn hai người cùng sống ở một thành phố; nó chỉ giúp các truy vấn phù hợp tìm node theo `city` hiệu quả hơn.

## 6. Các loại index và trường hợp sử dụng

Neo4j chia index thành hai nhóm lớn:

- **Performance indexes** được Cypher planner tự động cân nhắc khi truy vấn có predicate phù hợp.
- **Search indexes** được gọi tường minh để tìm và xếp hạng kết quả.

| Index | Công dụng điển hình | Cách dùng |
|---|---|---|
| Range | Equality, range, prefix và nhiều predicate phổ biến; hỗ trợ composite | Planner tự chọn |
| Text | Predicate chuỗi như `CONTAINS`, `ENDS WITH`, `STARTS WITH` | Planner tự chọn khi phù hợp |
| Point | Truy vấn không gian với property kiểu POINT | Planner tự chọn khi phù hợp |
| Token lookup | Tìm theo label của node hoặc relationship type | Thường được tạo sẵn trong database |
| Full-text | Tìm từ khóa qua analyzer, nhiều property hoặc label/type | Gọi search index tường minh |
| Vector | Tìm các vector tương tự về ngữ nghĩa hoặc khoảng cách | Gọi vector index tường minh |

### Range index cho lookup và điều kiện phổ biến

Range index là loại index mặc định nếu không chỉ định loại khi tạo:

~~~cypher
CREATE INDEX person_city_name IF NOT EXISTS
FOR (p:Person)
ON (p.city, p.name)
~~~

Composite range index có thể hữu ích khi truy vấn thường lọc theo cùng tổ hợp property. Thứ tự property trong index và hình dạng predicate ảnh hưởng khả năng planner tận dụng index. Hãy kiểm tra bằng `EXPLAIN` hoặc `PROFILE` thay vì tạo index theo cảm tính.

### Text index cho tìm kiếm chuỗi

Ví dụ:

~~~cypher
CREATE TEXT INDEX person_name_text IF NOT EXISTS
FOR (p:Person)
ON (p.name)
~~~

Text index hỗ trợ predicate chuỗi như `STARTS WITH`, `ENDS WITH` và `CONTAINS`. Nếu đồng thời có range index trên cùng property, planner có thể chọn text index cho các predicate chuỗi phù hợp và range index cho các điều kiện khác.

### Point index cho dữ liệu vị trí

Nếu node `Place` có property `location` kiểu POINT, point index có thể hỗ trợ truy vấn không gian:

~~~cypher
CREATE POINT INDEX place_location IF NOT EXISTS
FOR (p:Place)
ON (p.location)
~~~

Điều này hữu ích với tìm kiếm địa điểm theo khoảng cách hoặc vùng địa lý. Hãy bảo đảm ứng dụng lưu point với hệ tọa độ và đơn vị phù hợp.

### Full-text index cho tìm kiếm từ khóa

Full-text index phù hợp khi cần tìm các từ trong nhiều property văn bản:

~~~cypher
CREATE FULLTEXT INDEX person_text_search IF NOT EXISTS
FOR (p:Person)
ON EACH [p.name, p.bio]
~~~

Full-text index sử dụng analyzer để tách và xử lý từ. Khác với range/text index, nó không tự được planner chọn chỉ vì truy vấn có `WHERE p.bio CONTAINS ...`; ứng dụng cần gọi search index bằng cơ chế tìm kiếm tương ứng.

### Vector index cho tìm kiếm tương đồng

Nếu ứng dụng lưu embedding cho node `Article`, vector index có thể tìm nội dung gần nhau theo vector:

~~~cypher
CREATE VECTOR INDEX article_embedding IF NOT EXISTS
FOR (a:Article)
ON (a.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 1536,
        `vector.similarity_function`: 'cosine'
    }
}
~~~

Kích thước vector phải khớp với embedding model mà ứng dụng sử dụng. Vector index là search index; truy vấn phải gọi index theo API Cypher phù hợp với phiên bản Neo4j. Cú pháp và khả năng vector index thay đổi theo phiên bản, vì vậy cần đối chiếu Cypher Manual của phiên bản triển khai.

## 7. SDN mapping không tự quản lý schema database

SDN sử dụng annotation để ánh xạ Java object:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String personCode;
    private String email;
    private String city;
}
~~~

Trong ví dụ:

- `@Node("Person")` xác định label dùng cho mapping.
- `@Id` đánh dấu property định danh mà SDN dùng để nhận diện entity.
- `@GeneratedValue` yêu cầu SDN dùng cơ chế tạo ID được cấu hình.
- `personCode`, `email` và `city` là property được ánh xạ.

Các annotation này không tự tạo uniqueness, existence hoặc type constraint trên Neo4j. Đặc biệt, ID nội bộ do database/SDN quản lý không nên được dùng thay cho mã nghiệp vụ ổn định. Nếu `personCode` là mã mà các hệ thống khác tham chiếu, hãy tạo constraint trên property đó.

### Các annotation index cũ đã bị loại bỏ

Trong các phiên bản SDN cũ dựa trên Neo4j-OGM từng có `@Index`, `@CompositeIndex` và `@Required` để mô tả index hoặc constraint. Từ SDN 6, các annotation này đã bị loại bỏ và không có annotation thay thế trực tiếp.

Lý do là schema database cần được quản lý riêng với object mapping. Quy trình tạo schema tự động từ entity có thể khó kiểm soát khi nhiều phiên bản ứng dụng chạy đồng thời, khi database có dữ liệu cũ hoặc khi môi trường production cần thay đổi theo từng bước.

Vì vậy, với SDN hiện đại:

- Dùng `@Node`, `@Relationship`, `@Property` và `@Id` để mô tả mapping.
- Dùng Cypher DDL hoặc công cụ migration để tạo constraint và index.
- Lưu migration trong version control và triển khai theo pipeline.
- Kiểm tra schema thực tế trong database thay vì giả định annotation đã tạo nó.

## 8. Ví dụ kết hợp SDN entity, repository và constraint

Entity:

~~~java
@Node("Product")
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;
    private String title;
    private String category;
    private Long priceInCents;
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends Neo4jRepository<Product, Long> {

    Optional<Product> findBySku(String sku);

    List<Product> findByCategory(String category);
}
~~~

Migration Cypher:

~~~cypher
// Mã nghiệp vụ không được trùng.
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE;

// Tìm kiếm theo category thường xuyên.
CREATE INDEX product_category IF NOT EXISTS
FOR (p:Product)
ON (p.category);
~~~

`findBySku()` được hỗ trợ bởi uniqueness constraint và range index backing. `findByCategory()` có thể tận dụng range index nếu predicate và kế hoạch truy vấn phù hợp. Repository method không tự tạo hai schema object này.

Nếu dùng Enterprise Edition và cần mọi sản phẩm có `sku`, `title` và `priceInCents`, có thể thêm existence/type constraint phù hợp. Nếu dùng Community Edition, cần thực hiện validation trong service và kiểm soát mọi đường ghi dữ liệu.

## 9. Quản lý schema bằng migration

Schema cần được triển khai có phiên bản, giống như thay đổi cấu trúc của ứng dụng. Một quy trình an toàn thường gồm các bước:

1. Xác định quy tắc nghiệp vụ và các truy vấn thực tế cần tối ưu.
2. Kiểm tra graph hiện tại để tìm dữ liệu trùng, thiếu hoặc sai kiểu.
3. Làm sạch dữ liệu hiện có.
4. Tạo constraint và index bằng migration có tên rõ ràng.
5. Kiểm tra schema sau migration và xác minh index đã ở trạng thái `ONLINE`.
6. Triển khai code sử dụng quy tắc mới.
7. Theo dõi lỗi constraint và kế hoạch truy vấn sau khi phát hành.

Ví dụ trước khi tạo uniqueness constraint cho `Person.personCode`, tìm giá trị trùng:

~~~cypher
MATCH (p:Person)
WHERE p.personCode IS NOT NULL
WITH p.personCode AS code, collect(p) AS people
WHERE size(people) > 1
RETURN code, size(people) AS occurrences
ORDER BY occurrences DESC
~~~

Tìm node thiếu property:

~~~cypher
MATCH (p:Person)
WHERE p.personCode IS NULL
RETURN p
~~~

Chỉ tạo constraint sau khi dữ liệu vi phạm đã được xử lý. Neo4j cần kiểm tra dữ liệu hiện có khi tạo constraint; thao tác có thể thất bại nếu graph đã vi phạm quy tắc.

### IF NOT EXISTS không thay thế kiểm tra migration

`IF NOT EXISTS` giúp lệnh có thể chạy lại mà không báo lỗi khi cùng constraint hoặc index đã tồn tại. Tuy nhiên, nó không tự sửa constraint sai, không làm sạch dữ liệu trùng và không giải quyết xung đột với index hoặc constraint khác. Migration vẫn cần được theo dõi và xác minh kết quả.

### Kiểm tra constraint và index

Liệt kê constraint:

~~~cypher
SHOW CONSTRAINTS
~~~

Liệt kê index:

~~~cypher
SHOW INDEXES
~~~

`SHOW INDEXES` cung cấp `state` và `populationPercent`. Index mới tạo có thể ở trạng thái `POPULATING` trong khi database xây dựng dữ liệu index. Index chỉ dùng được khi trạng thái là `ONLINE`.

## 10. Chọn index theo truy vấn, không theo từng property một cách máy móc

Index có chi phí lưu trữ và cập nhật. Mỗi index bổ sung làm database phải duy trì thêm dữ liệu khi node hoặc relationship thay đổi. Tạo quá nhiều index có thể làm tăng chi phí ghi và quản trị.

Quy trình chọn index:

1. Liệt kê các truy vấn quan trọng theo tần suất và độ trễ.
2. Xác định label/relationship type và predicate thường dùng để tìm điểm bắt đầu.
3. Xem các property được lọc, sắp xếp hoặc kết hợp.
4. Tạo index phù hợp với mẫu truy vấn.
5. Dùng `EXPLAIN` để xem kế hoạch mà không thực thi truy vấn.
6. Dùng `PROFILE` trên dữ liệu đại diện để đo operator, số row và database hits.
7. Xác nhận index được planner sử dụng và truy vấn thực sự cải thiện.

Index giúp tìm điểm bắt đầu; nó không làm mọi traversal trở nên miễn phí. Nếu truy vấn bắt đầu từ một node có độ chọn lọc thấp rồi mở rộng ra hàng triệu relationship, cần xem lại mô hình, độ sâu traversal, filter và số kết quả trả về.

## 11. Schema không chỉ là danh sách property

Một schema hữu ích còn thể hiện quy tắc quan hệ và cách ứng dụng sử dụng graph:

- Label xác định nhóm node có cùng ý nghĩa nghiệp vụ.
- Relationship type mô tả loại liên kết và hướng của nó.
- Relationship property lưu dữ liệu thuộc về chính liên kết, chẳng hạn `quantity`, `role` hoặc `since`.
- Constraint bảo vệ các property quan trọng của node và relationship.
- Index hỗ trợ truy vấn theo label/type và property.
- Quy ước đặt tên giúp các team hiểu graph và viết Cypher nhất quán.

Các constraint truyền thống của Neo4j tập trung vào property. Chúng không tự mô tả toàn bộ cấu trúc topology như cardinality hoặc mọi kiểu node được phép ở hai đầu một relationship. Những quy tắc đó có thể cần được kiểm tra ở tầng nghiệp vụ hoặc qua các tính năng schema nâng cao tùy phiên bản và edition.

### Graph types trong các phiên bản Neo4j mới

Từ Neo4j 2026.02, Cypher 25 trên Enterprise Edition có tính năng graph types để khai báo cấu trúc node, relationship, property và một số constraint trong một mô tả schema tổng thể. Đây là hướng tiếp cận rộng hơn các lệnh constraint riêng lẻ. Khả năng này phụ thuộc phiên bản và edition; các dự án dùng phiên bản cũ vẫn có thể quản lý schema bằng `CREATE CONSTRAINT` và `CREATE INDEX` như các ví dụ trong bài.

## 12. Những lỗi thường gặp

**Cho rằng schemaless nghĩa là không cần quy tắc.** Graph linh hoạt nhưng vẫn cần định danh, dữ liệu bắt buộc, kiểu dữ liệu và quy tắc nghiệp vụ nhất quán.

**Nhầm @Id với uniqueness constraint cho mã nghiệp vụ.** `@Id` là metadata định danh của SDN. Nếu hệ thống cần `personCode` hoặc `sku` duy nhất, hãy tạo constraint trên property nghiệp vụ đó.

**Dùng uniqueness constraint để bắt buộc property.** Uniqueness chỉ kiểm tra giá trị của các entity có property. Dùng existence hoặc key constraint nếu property phải luôn có mặt.

**Cho rằng index bảo đảm dữ liệu duy nhất.** Index thường chỉ tăng tốc lookup. Muốn bảo đảm duy nhất, cần uniqueness hoặc key constraint.

**Cho rằng SDN tự tạo index từ @Index.** Các annotation `@Index`, `@CompositeIndex`, `@Required` thuộc thế hệ cũ và đã bị loại bỏ trong SDN 6+. Quản lý schema bằng migration Cypher.

**Tạo constraint khi dữ liệu cũ còn vi phạm.** Constraint có thể không tạo được nếu graph chứa giá trị trùng hoặc property bắt buộc đang thiếu. Hãy audit và làm sạch trước.

**Tạo index mà không kiểm tra query plan.** Index có thể không phù hợp predicate hoặc không được planner chọn. Dùng `EXPLAIN`, `PROFILE` và dữ liệu gần với production.

**Tạo quá nhiều index.** Index tăng tốc đọc nhưng có chi phí ghi và lưu trữ. Ưu tiên các truy vấn quan trọng thay vì index mọi property.

**Cho rằng full-text và vector index tự được planner chọn.** Đây là search index cần được gọi tường minh bằng cơ chế tìm kiếm tương ứng.

## 13. Tự kiểm tra

1. Vì sao property graph linh hoạt vẫn cần schema và quy tắc dữ liệu?
2. `@Node` và `@Relationship` của SDN khác constraint database như thế nào?
3. `@Id` có tự tạo uniqueness constraint trên mã nghiệp vụ không?
4. Uniqueness constraint khác key constraint ở điều kiện property tồn tại như thế nào?
5. Khi nào nên dùng existence constraint hoặc type constraint?
6. Index khác constraint ở mục đích nào?
7. Range, text, point, full-text và vector index phục vụ những mẫu tìm kiếm nào?
8. Vì sao SDN hiện đại quản lý schema bằng migration thay vì annotation `@Index`?
9. Vì sao phải làm sạch dữ liệu trước khi tạo constraint?
10. `SHOW INDEXES`, `EXPLAIN` và `PROFILE` giúp kiểm tra điều gì?

**Bài tập thực hành:** Thiết kế graph cho ứng dụng bán hàng với `Person`, `Product`, `Order` và relationship `PLACED`, `CONTAINS`. Xác định `personCode`, `sku` và `orderCode` là business key. Viết migration tạo uniqueness constraint cho ba mã, index cho `Product.category` và composite range index cho truy vấn lọc đơn theo `status` và `placedAt`. Kiểm tra dữ liệu trùng và thiếu property trước khi tạo constraint. Sau đó dùng `SHOW CONSTRAINTS`, `SHOW INDEXES`, `EXPLAIN` và `PROFILE` để xác minh schema và kế hoạch truy vấn. Cuối cùng, ghi rõ quy tắc nào được database bảo vệ và quy tắc topology nào vẫn cần validation trong service.

Ví dụ composite index cho truy vấn đơn hàng:

~~~cypher
CREATE INDEX order_status_placed_at IF NOT EXISTS
FOR (o:Order)
ON (o.status, o.placedAt)
~~~

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Cypher Manual — Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher Manual — Indexes](https://neo4j.com/docs/cypher-manual/current/indexes/)
- [Neo4j Cypher Manual — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Cypher Manual — Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Cypher Manual — Graph types](https://neo4j.com/docs/cypher-manual/current/schema/graph-types/set-graph-types/)
- [Spring Data Neo4j — Automatic creation of constraints and indexes](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j — Object mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/sdc-object-mapping.html)
