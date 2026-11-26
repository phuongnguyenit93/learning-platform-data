# Tạo, liệt kê, triển khai và xóa ràng buộc

Trong Neo4j, dữ liệu được tổ chức theo mô hình **property graph**: node mang label và thuộc tính; relationship mang type và thuộc tính, kết nối các node. Ứng dụng thường dùng Cypher để tạo khách hàng, đơn hàng và quan hệ giữa chúng. Khi nhiều tiến trình cùng ghi dữ liệu, kiểm tra tính hợp lệ chỉ ở tầng Java, Spring Data Neo4j hoặc API là chưa đủ. **Constraint (ràng buộc)** cho phép cơ sở dữ liệu trực tiếp từ chối một số trạng thái dữ liệu không hợp lệ.

Bài này thuộc chương **Ràng buộc dữ liệu** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Trọng tâm là toàn bộ vòng đời của constraint: **tạo bằng `CREATE CONSTRAINT`, liệt kê và xác minh bằng `SHOW CONSTRAINTS`, triển khai qua migration, và xóa bằng `DROP CONSTRAINT`**. Ví dụ sử dụng cú pháp Cypher hiện đại của Neo4j 5.x; khi vận hành phiên bản/edition khác, cần kiểm tra tính khả dụng của từng loại constraint và cú pháp tương ứng.

Sau bài học, bạn có thể:

- Tạo constraint có tên rõ ràng, dùng `IF NOT EXISTS` khi triển khai lặp lại.
- Đọc metadata của constraint và phân biệt constraint với index.
- Phát hiện dữ liệu trùng hoặc thiếu thuộc tính trước khi áp dụng ràng buộc.
- Xây dựng quy trình triển khai, kiểm chứng và xóa constraint có kiểm soát.
- Kết hợp ràng buộc với lệnh `MERGE` và các tầng ứng dụng Java.

## 1. Constraint bảo vệ điều gì?

Giả sử có đồ thị:

~~~text
(:Customer {customerId, email, name})
     |
     | [:PLACED {eventId, placedAt}]
     v
(:Order {tenantId, orderNo, createdAt, total})
~~~

Các yêu cầu nghiệp vụ có thể gồm: một `customerId` không thuộc về hai node khách khác nhau; mọi đơn hàng có `createdAt`; không có hai relationship `PLACED` sử dụng cùng `eventId`. Neo4j hỗ trợ nhiều loại constraint để biểu diễn các yêu cầu này.

| Loại | Ý nghĩa | Ví dụ Cypher (phần `REQUIRE`) |
| --- | --- | --- |
| Uniqueness trên node | Các node cùng label không được trùng giá trị thuộc tính được ràng buộc khi thuộc tính đó có mặt. | `c.email IS UNIQUE` |
| Uniqueness ghép | Không trùng **tổ hợp** giá trị thuộc tính. | `(o.tenantId, o.orderNo) IS UNIQUE` |
| Uniqueness trên relationship | Các relationship cùng type không được trùng giá trị thuộc tính được ràng buộc. | `r.eventId IS UNIQUE` |
| Node key | Buộc node có thuộc tính khóa **và** khóa là duy nhất. | `c.customerId IS NODE KEY` |
| Relationship key | Buộc relationship có thuộc tính khóa **và** khóa là duy nhất. | `r.eventId IS RELATIONSHIP KEY` |
| Property existence | Bắt buộc thuộc tính tồn tại trên node/relationship trong phạm vi ràng buộc. | `o.createdAt IS NOT NULL` |
| Property type | Thuộc tính, nếu có, phải thuộc kiểu dữ liệu được khai báo. | `o.total IS :: FLOAT` |

**Chú ý hai điểm khác nhau:**

1. `IS UNIQUE` **không tự bắt buộc tồn tại thuộc tính**. Nhiều `Customer` thiếu `email` không vi phạm uniqueness của `email`. Nếu cần vừa có giá trị vừa không trùng, dùng key constraint nếu edition hỗ trợ, hoặc kết hợp với existence constraint.
2. `IS :: FLOAT` giới hạn kiểu khi có thuộc tính, **không tự cấm thiếu thuộc tính** và cũng không cấm số âm. Các quy tắc như `total >= 0`, định dạng email, hay quan hệ phải kết nối đúng một khách hàng thuộc về lớp kiểm tra nghiệp vụ/mô hình ứng dụng nếu không có constraint tương ứng.

Không phải mọi edition hoặc phiên bản Neo4j đều hỗ trợ mọi loại. Đặc biệt, **key, existence và property type constraints** cần kiểm tra quyền sử dụng tính năng của Neo4j Enterprise và phiên bản đang vận hành. Cú pháp property type ở đây dành cho các bản Neo4j 5 có hỗ trợ tính năng đó. Không đưa trực tiếp toàn bộ lệnh minh họa vào sản xuất nếu chưa kiểm tra khả năng hỗ trợ.

## 2. Cú pháp chuẩn để tạo constraint

Khuôn mẫu:

~~~cypher
CREATE CONSTRAINT ten_rang_buoc IF NOT EXISTS
FOR (n:Label)
REQUIRE n.thuocTinh IS UNIQUE;
~~~

Trong đó:

- `ten_rang_buoc` là tên để theo dõi, tìm kiếm, di chuyển schema giữa môi trường và xóa chính xác đối tượng.
- `FOR` định nghĩa phạm vi node có label hoặc relationship có type. Ràng buộc áp dụng cho **cùng label/type**, không tự lan sang mọi node hoặc mọi type khác.
- `REQUIRE` mô tả điều kiện được Neo4j kiểm tra khi tạo ràng buộc và khi dữ liệu được ghi/cập nhật sau đó.
- `IF NOT EXISTS` cho phép chạy lại lệnh triển khai khi constraint tương đương đã tồn tại. Nó **không thay thế** bước đối chiếu tên, loại và cấu trúc ràng buộc sau triển khai.

Đặt tên nhất quán giúp việc vận hành dễ kiểm tra, ví dụ `customer_email_unique`, `order_tenant_no_unique` hoặc `order_created_required`. Tránh các tên tự sinh khó nhận diện khi cần rollback.

### 2.1. Ràng buộc duy nhất trên một thuộc tính

~~~cypher
CREATE CONSTRAINT customer_email_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.email IS UNIQUE;
~~~

Lệnh này ngăn hai node có label `Customer` mang **cùng email khác null**. Nếu yêu cầu email luôn có trên mọi khách hàng, cần thêm ràng buộc tồn tại hoặc thiết kế khóa khác. Giá trị email phân biệt chữ hoa/chữ thường theo cách so sánh chuỗi thông thường; muốn `AN@example.com` và `an@example.com` được coi là trùng thì phải chuẩn hóa dữ liệu trước khi ghi và trước khi tạo constraint.

### 2.2. Ràng buộc duy nhất trên tổ hợp thuộc tính

Một hệ thống nhiều tenant có thể cho phép các tenant khác nhau dùng cùng `orderNo`, nhưng không cho phép trùng `orderNo` trong **cùng tenant**:

~~~cypher
CREATE CONSTRAINT order_tenant_no_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE (o.tenantId, o.orderNo) IS UNIQUE;
~~~

Điều kiện này kiểm tra **cặp** `(tenantId, orderNo)`, không buộc `tenantId` hay `orderNo` riêng lẻ là duy nhất. Nếu một phần của cặp bị thiếu, uniqueness không bảo đảm tính hiện diện của từng thuộc tính; cần xem xét key/existence constraints nếu nghiệp vụ yêu cầu.

### 2.3. Ràng buộc duy nhất trên relationship

~~~cypher
CREATE CONSTRAINT placed_event_unique IF NOT EXISTS
FOR ()-[r:PLACED]-()
REQUIRE r.eventId IS UNIQUE;
~~~

Ví dụ này hữu ích khi sự kiện tạo đơn hàng có mã định danh riêng. Một relationship type khác không chịu ràng buộc của `:PLACED`. Tùy edition/phiên bản, hãy xác nhận rằng loại uniqueness trên relationship được hỗ trợ.

### 2.4. Node key và relationship key

Nếu mọi khách hàng **bắt buộc có `customerId` và duy nhất**, node key thể hiện cả hai quy tắc:

~~~cypher
CREATE CONSTRAINT customer_id_key IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS NODE KEY;
~~~

Một khóa ghép cũng có thể được định nghĩa:

~~~cypher
CREATE CONSTRAINT order_business_key IF NOT EXISTS
FOR (o:Order)
REQUIRE (o.tenantId, o.orderNo) IS NODE KEY;
~~~

Với relationship, nếu `eventId` phải có và không trùng:

~~~cypher
CREATE CONSTRAINT placed_event_key IF NOT EXISTS
FOR ()-[r:PLACED]-()
REQUIRE r.eventId IS RELATIONSHIP KEY;
~~~

Các lệnh key phía trên minh họa khả năng của phiên bản/edition có hỗ trợ. Không triển khai đồng thời uniqueness và key trên cùng một schema một cách máy móc: quyết định một cấu trúc đủ đáp ứng nghiệp vụ, kiểm tra các ràng buộc đã có và lên kế hoạch thay đổi nếu cần.

### 2.5. Property existence và property type

Buộc mọi node `Order` có `createdAt`:

~~~cypher
CREATE CONSTRAINT order_created_required IF NOT EXISTS
FOR (o:Order)
REQUIRE o.createdAt IS NOT NULL;
~~~

Buộc `total` nếu tồn tại phải là số thực `FLOAT`:

~~~cypher
CREATE CONSTRAINT order_total_float IF NOT EXISTS
FOR (o:Order)
REQUIRE o.total IS :: FLOAT;
~~~

Trước khi tạo type constraint, phải xem kiểu giá trị thực tế trong database: một số `total` đang lưu dưới dạng `INTEGER` hoặc `STRING` sẽ không tự động được chuyển sang `FLOAT`. Chọn kiểu theo miền nghiệp vụ và cách ứng dụng ghi dữ liệu; Neo4j không tự coi mọi số nguyên là giá trị `FLOAT` khi kiểm tra constraint kiểu `FLOAT`.

Với dữ liệu cần kiểm tra cả sự tồn tại lẫn kiểu, phải thiết kế đủ hai điều kiện tương ứng (hoặc dùng loại key thích hợp cho khóa). Không nên hiểu một constraint là hệ thống kiểm tra toàn bộ hợp lệ của bản ghi.

## 3. Liệt kê và kiểm tra ràng buộc đang có

Lệnh tổng quát:

~~~cypher
SHOW CONSTRAINTS;
~~~

Để hiển thị đúng các cột hữu ích cho việc vận hành:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

Ý nghĩa của những cột thường dùng:

| Cột | Cách dùng |
| --- | --- |
| `name` | Nhận diện constraint để kiểm tra và gọi `DROP CONSTRAINT`. |
| `type` | Phân biệt uniqueness, key, existence, property type, ...; giá trị cụ thể phụ thuộc phiên bản. |
| `entityType` | Cho biết phạm vi là node hay relationship. |
| `labelsOrTypes` | Label node hoặc type relationship đang được ràng buộc. |
| `properties` | Danh sách thuộc tính tham gia constraint; có thể có nhiều thuộc tính. |

Có thể lọc theo quy ước tên:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name STARTS WITH 'customer_'
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

Một số constraint về uniqueness và key có **index phục vụ kiểm tra tính duy nhất** do Neo4j quản lý. Có thể kiểm tra thêm qua:

~~~cypher
SHOW INDEXES;
~~~

Index và constraint có mục đích khác nhau: index chủ yếu hỗ trợ tìm/truy cập dữ liệu, còn constraint xác định tính hợp lệ dữ liệu. Không tự xóa index do constraint sở hữu để “gỡ ràng buộc”; cần xóa constraint đúng cách bằng tên. Existence/type constraints không đồng nghĩa sẽ có một index phục vụ truy vấn.

**Kiểm tra sau khi tạo:** đừng chỉ kết luận thành công vì lệnh `CREATE ... IF NOT EXISTS` không báo lỗi. Hãy đối chiếu cả `name`, `type`, `labelsOrTypes` và `properties` với schema mong muốn. Tên trùng nhưng định nghĩa không như kỳ vọng là vấn đề cần xử lý qua migration cụ thể.

## 4. Kiểm tra dữ liệu trước khi triển khai

Neo4j kiểm tra **dữ liệu đã tồn tại** khi tạo constraint. Nếu có vi phạm, thao tác tạo thất bại; dữ liệu không được âm thầm sửa, xóa hoặc bỏ qua. Do đó, cần thực hiện kiểm tra dữ liệu và chọn cách sửa phù hợp trước khi chạy DDL ở môi trường thực.

### 4.1. Tìm email trùng trước khi tạo uniqueness

~~~cypher
MATCH (c:Customer)
WHERE c.email IS NOT NULL
WITH c.email AS email, count(*) AS soKhach
WHERE soKhach > 1
RETURN email, soKhach
ORDER BY soKhach DESC, email ASC
LIMIT 20;
~~~

Nếu truy vấn có kết quả, cần xử lý trùng theo nghiệp vụ: hợp nhất khách hàng, đổi khóa email hoặc xác định record chính. Không tự động xóa node trùng vì có thể còn relationship, đơn hàng và lịch sử liên quan.

### 4.2. Tìm thuộc tính bắt buộc đang thiếu

~~~cypher
MATCH (o:Order)
WHERE o.createdAt IS NULL
RETURN count(o) AS soDonThieuNgayTao;
~~~

Trong Cypher, truy cập thuộc tính không tồn tại trả về `null`. Cần phân biệt “thiếu ngày tạo” với ngày tạo lỗi do ứng dụng nhập sai kiểu dữ liệu. Nếu chuẩn bị áp dụng node key trên `customerId`, kiểm tra riêng các khách hàng thiếu khóa:

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IS NULL
RETURN count(c) AS soKhachThieuMa;
~~~

### 4.3. Tìm tổ hợp khóa đơn hàng bị trùng

~~~cypher
MATCH (o:Order)
WHERE o.tenantId IS NOT NULL AND o.orderNo IS NOT NULL
WITH o.tenantId AS tenantId, o.orderNo AS orderNo, count(*) AS soDon
WHERE soDon > 1
RETURN tenantId, orderNo, soDon
ORDER BY soDon DESC, tenantId ASC, orderNo ASC
LIMIT 20;
~~~

Nếu sử dụng **node key ghép**, cũng phải kiểm tra những node thiếu `tenantId` hoặc `orderNo`, vì key yêu cầu tất cả thành phần đều tồn tại. Với uniqueness ghép, truy vấn tìm trùng trên các hàng có đủ cặp thuộc tính là bước preflight phù hợp.

### 4.4. Kiểm tra dữ liệu thực tế và edition

Trước khi áp dụng type constraint, thống kê các kiểu đang lưu trong dữ liệu bằng công cụ truy vấn/kiểm tra tương thích với bản Neo4j của hệ thống. Việc chuyển chuỗi thành số, chuyển số nguyên thành số thực hoặc đổi biểu diễn ngày giờ cần có quy tắc dữ liệu rõ ràng và migration riêng. Ngoài ra, xác nhận edition có hỗ trợ loại constraint mục tiêu và tài khoản triển khai có quyền quản trị schema trên đúng database.

## 5. Quy trình triển khai constraint theo migration

Triển khai schema là thay đổi có trạng thái trên database, cần tính **lặp lại được, xác minh được và có kế hoạch hoàn nguyên**. Một quy trình thực tế gồm sáu bước:

1. **Chốt đặc tả:** xác định label/type, thuộc tính, kiểu constraint, cách đặt tên, edition và phiên bản Cypher.
2. **Khảo sát dữ liệu:** kiểm tra duplicate, missing value và kiểu dữ liệu theo phần 4; hoàn thành migration làm sạch nếu phát hiện vi phạm.
3. **Thử nghiệm trên môi trường tương đương:** chạy lệnh, quan sát thời gian và thay đổi ghi dữ liệu; kiểm tra các luồng tạo/cập nhật node/relationship của ứng dụng.
4. **Chuẩn bị vận hành:** lưu script schema có phiên bản trong hệ thống migration của dự án; sao lưu/thiết lập điểm phục hồi theo quy trình tổ chức, chọn thời điểm triển khai phù hợp với khối lượng dữ liệu.
5. **Áp dụng và xác minh:** dùng tài khoản đủ quyền trên **đúng database**, kiểm tra `SHOW CONSTRAINTS` rồi kiểm tra chức năng ghi dữ liệu.
6. **Ghi nhận kết quả:** lưu phiên bản migration đã chạy, đối chiếu với môi trường đích; tài liệu hóa cách xử lý lỗi và rollback.

Ví dụ một migration SQL-like được lưu dưới dạng các câu Cypher, trong đó sử dụng loại constraint đã được xác nhận là khả dụng:

~~~cypher
// Ví dụ migration: 001_customer_order_constraints.cypher
CREATE CONSTRAINT customer_email_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.email IS UNIQUE;

CREATE CONSTRAINT order_tenant_no_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE (o.tenantId, o.orderNo) IS UNIQUE;
~~~

Khi triển khai qua dòng lệnh, `cypher-shell` có thể chạy script vào database chỉ định:

~~~bash
cypher-shell -a neo4j://localhost:7687 -u neo4j -d neo4j -f 001_customer_order_constraints.cypher
~~~

Đường dẫn, địa chỉ, tên user và database là **ví dụ**; công cụ có thể hỏi mật khẩu an toàn khi chạy. Với môi trường production, sử dụng địa chỉ bảo mật, tài khoản triển khai theo chính sách phân quyền và cách quản lý bí mật được tổ chức chấp nhận.

**Vì sao cần chạy theo migration có phiên bản?** Giả sử môi trường A có constraint `customer_email_unique`, môi trường B không có, môi trường C lại có constraint khác dùng cùng tên. Một script chỉ dựa vào `IF NOT EXISTS` chưa đủ để khẳng định cả ba đã đồng nhất schema. Quy trình migration phải kiểm tra cấu trúc thực tế và báo sai khác khi cần.

### 5.1. Triển khai bằng Neo4j Java Driver

Một hệ thống Java có thể gọi lệnh schema thông qua Neo4j Java Driver, chẳng hạn trong một migration runner hoặc công cụ quản trị riêng:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class SchemaMigration {
    public static void apply(Driver driver) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.run("""
                CREATE CONSTRAINT customer_email_unique IF NOT EXISTS
                FOR (c:Customer)
                REQUIRE c.email IS UNIQUE
                """).consume();
        }
    }
}
~~~

`Driver` được cấu hình và quản lý vòng đời ở tầng ứng dụng; ví dụ giả định đã có một `Driver` hợp lệ. `consume()` giúp đợi kết quả thực thi và nhận lỗi nếu database từ chối thao tác. Lệnh chạy trên database `neo4j` theo cấu hình ví dụ, phải thay bằng tên database triển khai thực tế.

Với **Spring Data Neo4j**, vẫn nên quản lý constraint như một phần của migration/schema deployment có kiểm soát. Việc ánh xạ entity, annotation và repository không phải bằng chứng rằng tất cả constraint mong muốn đã có đúng kiểu trong database đang chạy. Dù chạy bằng Java Driver, CLI hay công cụ migration, quy trình preflight và kiểm tra metadata vẫn như nhau.

### 5.2. Ảnh hưởng vận hành và concurrency

Tạo uniqueness/key constraint có thể đòi hỏi quét dữ liệu đang có và xây dựng index phục vụ kiểm tra khóa. Với đồ thị lớn, thời gian xây dựng và tác động lên tài nguyên có thể đáng kể; phải đo trên dữ liệu đại diện. Nếu các tiến trình khác đang ghi dữ liệu trong lúc triển khai, sự cạnh tranh tài nguyên hoặc dữ liệu mới không hợp lệ có thể khiến thao tác chờ hoặc thất bại. Chuẩn bị kế hoạch triển khai, giám sát và xử lý lỗi phù hợp với hệ thống.

Sau khi tạo thành công, constraint kiểm soát những lần ghi tiếp theo. Nó không tự kiểm tra tất cả quy tắc phức tạp như số tiền dương, chiều của relationship hay một khách chỉ có một đơn ở một trạng thái.

## 6. Xóa ràng buộc và rollback

Khi cần ngừng áp dụng uniqueness của email:

~~~cypher
DROP CONSTRAINT customer_email_unique IF EXISTS;
~~~

Lệnh `DROP CONSTRAINT` sử dụng **tên constraint**, không dùng mô tả label/thuộc tính. `IF EXISTS` giúp tránh lỗi khi tên không tồn tại, nhưng vẫn cần kiểm tra trạng thái sau khi chạy:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name = 'customer_email_unique'
RETURN name, type, labelsOrTypes, properties;
~~~

Nếu không có dòng nào, constraint đó không còn trong danh sách. Việc xóa constraint **không xóa các node, relationship hay giá trị thuộc tính hiện có**, nhưng những bản ghi mới có thể vi phạm quy tắc trước đây. Với constraint có index do Neo4j sở hữu, việc xóa constraint cũng loại bỏ index liên quan của constraint; điều này có thể ảnh hưởng kế hoạch truy vấn.

Trước khi drop, xác minh constraint có còn được ứng dụng, quá trình nhập dữ liệu hoặc quy trình đồng bộ dựa vào hay không. Nếu bỏ constraint để thực hiện migration, tránh khoảng thời gian ghi không được bảo vệ. Khi tạo lại constraint, Neo4j phải kiểm tra dữ liệu hiện có lần nữa; những giá trị trùng xuất hiện trong khoảng thời gian đó có thể làm lệnh tạo lại thất bại.

**Đổi loại ràng buộc không chỉ là đổi tên.** Ví dụ chuyển `customer_email_unique` sang `customer_id_key` có thể thay đổi cả trường khóa nghiệp vụ lẫn quy tắc bắt buộc tồn tại. Quy trình cần kiểm tra dữ liệu trước, tạo ràng buộc mới khi phù hợp, cập nhật ứng dụng và chỉ xóa ràng buộc cũ sau khi các đường ghi đã chuyển đổi. Nếu có xung đột cấu trúc khiến không thể tạo mới trước, lập kế hoạch chuyển đổi riêng và giảm tối đa thời gian thiếu bảo vệ.

## 7. Kết hợp constraint với MERGE khi ghi dữ liệu

Trong ứng dụng, `MERGE` thường được dùng để tìm hoặc tạo node theo khóa nghiệp vụ:

~~~cypher
MERGE (c:Customer {customerId: $customerId})
ON CREATE SET c.createdAt = datetime()
SET c.name = $name, c.email = $email
RETURN c;
~~~

Khi đã có constraint duy nhất (hoặc node key) trên `Customer.customerId`, database có cơ sở ngăn chặn hai bản ghi cùng mã, kể cả khi nhiều request chạy đồng thời. Tuy nhiên:

- `MERGE` không thay thế toàn bộ constraint. Trước khi cấu hình khóa đúng, các request đồng thời vẫn có nguy cơ tạo dữ liệu trùng.
- `MERGE` có thể báo lỗi khi giá trị xung đột constraint; ứng dụng cần xử lý ngoại lệ và có chính sách retry phù hợp.
- Tránh `MERGE` đồng thời trên nhiều thuộc tính mutable, ví dụ cả mã khách lẫn email, khi mỗi thuộc tính chịu constraint khác nhau. Nên xác định một khóa ổn định rồi cập nhật các thuộc tính còn lại bằng `SET`.
- Khi muốn email không trùng, phải giữ riêng constraint `customer_email_unique` nếu khóa `customerId` không bảo vệ được email.

Ví dụ về sự khác biệt: ràng buộc `customer_id_key` ngăn hai node có cùng `customerId`; nó **không** ngăn hai khách có `email` giống nhau. Thiết kế constraint phải xuất phát từ các bất biến nghiệp vụ, không chỉ từ câu `MERGE` đang được sử dụng.

## 8. Lỗi thường gặp khi quản lý constraint

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tạo uniqueness thất bại vì trùng giá trị | Đã có hai node/relationship trong cùng label/type với khóa trùng. | Chạy truy vấn tìm duplicate, xử lý theo nghiệp vụ, rồi tạo lại. |
| Tạo node key/existence thất bại | Có node/relationship thiếu thuộc tính bắt buộc. | Đếm bản ghi thiếu, bổ sung hoặc sửa dữ liệu trước migration. |
| Tạo type constraint thất bại | Dữ liệu có kiểu khác kiểu khai báo, hoặc phiên bản/edition không hỗ trợ. | Khảo sát kiểu thực tế và khả năng hỗ trợ, sửa hoặc chuyển đổi có kiểm soát. |
| Truy vấn tạo constraint không được phép | Tài khoản không có quyền quản lý schema trên database đích. | Kiểm tra cấu hình quyền và database, dùng tài khoản migration phù hợp. |
| `IF NOT EXISTS` chạy được nhưng schema không như kỳ vọng | Constraint đã tồn tại dưới tên/cấu trúc khác, hoặc không được tạo như dự kiến. | So sánh `SHOW CONSTRAINTS` với đặc tả migration, xử lý sai khác rõ ràng. |
| Drop constraint rồi các request tạo dữ liệu trùng | Quy tắc duy nhất không còn được database áp dụng. | Thiết kế lịch chuyển đổi, giới hạn ghi hoặc áp dụng bảo vệ thay thế trong migration. |
| Truy vấn chậm hơn sau khi drop | Index gắn với constraint đã bị xóa; kế hoạch truy vấn thay đổi. | Kiểm tra `PROFILE` và nhu cầu index độc lập, tránh tạo index theo phỏng đoán. |
| Dùng cú pháp `ASSERT` trong hệ thống mới | Script được viết cho phiên bản Neo4j cũ. | Chuẩn hóa migration theo cú pháp `FOR ... REQUIRE ...` phù hợp phiên bản đích. |

**Lưu ý tương thích:** các tài liệu cũ của Neo4j có thể dùng `CREATE CONSTRAINT ... ASSERT ...`. Ví dụ trong bài sử dụng cú pháp `FOR ... REQUIRE ...` của dòng Neo4j 5. Khi nâng cấp từ hệ thống cũ, cần đối chiếu cú pháp, tên constraint và loại constraint thay vì sao chép hai kiểu DDL vào cùng migration.

## 9. Kịch bản kiểm chứng trên database thử nghiệm

Chỉ thực hiện các lệnh ghi và xóa dữ liệu trong phần này ở **database thử nghiệm**, sau khi xác nhận các dữ liệu/mã ví dụ không ảnh hưởng dữ liệu đang dùng.

**Bước 1 — Tạo uniqueness cho một label thử nghiệm riêng:**

~~~cypher
CREATE CONSTRAINT demo_customer_code_unique IF NOT EXISTS
FOR (c:DemoCustomer)
REQUIRE c.code IS UNIQUE;
~~~

**Bước 2 — Tạo node có khóa:**

~~~cypher
CREATE (:DemoCustomer {code: 'DEMO-001', name: 'An'});
~~~

**Bước 3 — Thử tạo bản ghi trùng để quan sát lỗi mong đợi:**

~~~cypher
CREATE (:DemoCustomer {code: 'DEMO-001', name: 'Binh'});
~~~

Lệnh thứ ba phải bị từ chối nếu constraint ở bước 1 đã tạo thành công. Khi thao tác thất bại, không nên dựa vào lỗi đó để khẳng định mọi loại constraint khác cũng hoạt động; kiểm tra đúng loại và đối tượng mục tiêu.

**Bước 4 — Kiểm tra trạng thái, xóa đối tượng thử nghiệm và constraint:**

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name = 'demo_customer_code_unique'
RETURN name, type, labelsOrTypes, properties;
~~~

~~~cypher
MATCH (c:DemoCustomer {code: 'DEMO-001'})
DELETE c;
~~~

~~~cypher
DROP CONSTRAINT demo_customer_code_unique IF EXISTS;
~~~

Trong kịch bản này `DemoCustomer` được tạo để không có relationship, nên `DELETE` node là đủ. Nếu node có relationship, phải xem xét hậu quả trước khi sử dụng `DETACH DELETE` vì nó sẽ xóa cả các relationship kết nối. Không dùng `MATCH (n) DETACH DELETE n` để dọn bài tập trên database chứa dữ liệu khác.

## 10. Bài tập áp dụng

1. Hệ thống có `(:User {tenantId, username})`. Mỗi tenant được phép có username trùng với tenant khác, nhưng không trùng trong cùng tenant. Hãy viết constraint và truy vấn tìm những cặp đang vi phạm trước khi tạo.
2. Mọi `:Order` phải có `orderNo` và mã này duy nhất **trong một tenant**. So sánh giải pháp dùng uniqueness ghép với node key ghép. Trong edition không hỗ trợ node key, cần bổ sung những kiểm tra nào?
3. Một migration vừa chạy `CREATE CONSTRAINT IF NOT EXISTS` rồi in “OK”. Hãy giải thích vì sao cần `SHOW CONSTRAINTS` và những metadata cần đối chiếu.
4. Đội vận hành muốn bỏ constraint email. Hãy mô tả những điều có thể thay đổi đối với dữ liệu và hiệu năng truy vấn, cũng như cách kiểm tra hậu triển khai.

Gợi ý cho bài 1:

~~~cypher
MATCH (u:User)
WHERE u.tenantId IS NOT NULL AND u.username IS NOT NULL
WITH u.tenantId AS tenantId, u.username AS username, count(*) AS soLuong
WHERE soLuong > 1
RETURN tenantId, username, soLuong
ORDER BY soLuong DESC, tenantId ASC, username ASC;
~~~

~~~cypher
CREATE CONSTRAINT user_tenant_username_unique IF NOT EXISTS
FOR (u:User)
REQUIRE (u.tenantId, u.username) IS UNIQUE;
~~~

Khi quản lý ràng buộc Neo4j, nên luôn trả lời đủ bốn câu hỏi: **ràng buộc bảo vệ bất biến dữ liệu nào, dữ liệu hiện tại đã đáp ứng chưa, phiên bản/edition đang chạy có hỗ trợ không, và sau triển khai sẽ xác minh/hoàn nguyên như thế nào?** Quy trình đó giúp constraint trở thành một phần có thể kiểm soát của schema property graph, cùng với index, truy vấn Cypher, Java Driver và Spring Data Neo4j.
