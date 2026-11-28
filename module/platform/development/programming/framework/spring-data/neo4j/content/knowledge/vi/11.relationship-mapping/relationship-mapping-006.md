# Quan hệ tự tham chiếu và chu trình trong mô hình Java

Trong graph, một node có thể liên kết với node khác cùng label và cùng kiểu entity. Ví dụ, một danh mục có danh mục con, một nhân viên có người quản lý cũng là nhân viên, hoặc một dịch vụ phụ thuộc vào dịch vụ khác. Đây là quan hệ tự tham chiếu (self-referencing relationship). Khi các liên kết nối vòng lại điểm xuất phát, graph hình thành chu trình (cycle).

Spring Data Neo4j (SDN) có thể ánh xạ quan hệ tự tham chiếu bằng cách khai báo thuộc tính quan hệ ngay trong entity của chính kiểu đó. Tuy nhiên, cần phân biệt cấu trúc graph với object graph trong Java: một chu trình trong Neo4j có thể là dữ liệu hợp lệ, còn các tham chiếu vòng trong object Java có thể gây đệ quy vô hạn khi in log, so sánh object hoặc chuyển thành JSON. Bài học này trình bày cách mô hình hóa, định hướng quan hệ, phát hiện chu trình và kiểm soát việc tải, cập nhật cũng như tuần tự hóa graph.

## Quan hệ tự tham chiếu trong Neo4j

Quan hệ tự tham chiếu xảy ra khi hai đầu của relationship cùng là node thuộc một kiểu hoặc label. Ví dụ, cây danh mục có thể dùng một label **Category** cho cả danh mục cha và danh mục con:

~~~cypher
CREATE (books:Category {id: "CAT-BOOKS", name: "Books"})
CREATE (fiction:Category {id: "CAT-FICTION", name: "Fiction"})
CREATE (history:Category {id: "CAT-HISTORY", name: "History"})
CREATE (books)-[:PARENT_OF]->(fiction)
CREATE (books)-[:PARENT_OF]->(history);
~~~

Cả ba node đều mang label **Category**. Relationship **PARENT_OF** cho biết hướng từ danh mục cha tới danh mục con. Graph không cần tạo label riêng như **ParentCategory** và **ChildCategory**, bởi vai trò cha/con được xác định bởi hướng relationship trong từng kết nối.

Quan hệ tự tham chiếu thường xuất hiện trong các mô hình:

- Danh mục cha và danh mục con.
- Nhân viên và người quản lý.
- Người dùng theo dõi hoặc giới thiệu người dùng khác.
- Thành phần phần mềm phụ thuộc vào thành phần khác.
- Trang hoặc tài liệu liên kết tới trang hoặc tài liệu liên quan.
- Các bước trong quy trình có quan hệ trước/sau.

Một node có thể có nhiều quan hệ cùng kiểu. Ví dụ một danh mục có nhiều con; một danh mục con có thể có một cha trong cây phân cấp hoặc nhiều cha trong đồ thị phân loại dạng DAG. Cần xác định quy tắc nghiệp vụ trước khi chọn kiểu thuộc tính Java là một đối tượng hay một collection.

## Ánh xạ self-reference bằng Spring Data Neo4j

Giả sử ứng dụng quản lý cây danh mục và mỗi danh mục có thể có nhiều danh mục con. Có thể biểu diễn bằng entity **Category** với thuộc tính **children** tham chiếu lại chính kiểu **Category**:

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Direction;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.UUIDStringGenerator;

@Node("Category")
public class Category {

    @Id
    @GeneratedValue(UUIDStringGenerator.class)
    private String id;

    private String name;

    @Relationship(type = "PARENT_OF", direction = Direction.OUTGOING)
    private Set<Category> children = new LinkedHashSet<>();

    protected Category() {
    }

    public Category(String name) {
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Set<Category> getChildren() {
        return children;
    }

    public void addChild(Category child) {
        if (child == null) {
            throw new IllegalArgumentException("Child category is required");
        }
        if (this == child || (id != null && id.equals(child.id))) {
            throw new IllegalArgumentException("A category cannot be its own child");
        }
        children.add(child);
    }
}
~~~

Các thành phần quan trọng:

- **@Node("Category")** ánh xạ mọi danh mục vào label **Category**.
- **@Id** đánh dấu thuộc tính định danh của entity.
- **@GeneratedValue(UUIDStringGenerator.class)** sinh ID dạng chuỗi cho node mới.
- **Set<Category>** cho biết một danh mục có thể liên kết với nhiều danh mục con.
- **@Relationship(type = "PARENT_OF")** xác định kiểu relationship trong graph.
- **Direction.OUTGOING** xác định relationship đi từ node hiện tại tới các phần tử trong **children**.

Với mapping này, thuộc tính **children** mô tả các cạnh đi ra từ danh mục hiện tại. Ví dụ **books.getChildren()** biểu diễn các node được nối bởi **(:Category)-[:PARENT_OF]->(:Category)**. Hướng mặc định của **@Relationship** là outgoing, nhưng ghi rõ **Direction.OUTGOING** giúp người đọc nhận biết quy ước graph ngay tại entity.

### Ánh xạ chiều ngược

Nếu use case chính là truy cập danh mục cha từ một danh mục con, có thể ánh xạ quan hệ incoming:

~~~java
@Relationship(type = "PARENT_OF", direction = Direction.INCOMING)
private Category parent;
~~~

Trong khai báo này, **parent** là node ở đầu relationship trỏ vào node hiện tại. Quan hệ trong graph vẫn có hướng **parent -[:PARENT_OF]-> child**; **Direction.INCOMING** chỉ cách SDN đọc mối liên kết từ góc nhìn của entity con.

Nếu một danh mục có thể có nhiều cha, dùng collection:

~~~java
@Relationship(type = "PARENT_OF", direction = Direction.INCOMING)
private Set<Category> parents = new LinkedHashSet<>();
~~~

Hãy chọn cách ánh xạ theo hướng truy cập chính của ứng dụng. Không cần khai báo cả **children** và **parent** chỉ để có thể đi hai chiều; có thể truy vấn chiều còn lại bằng Cypher hoặc một repository method chuyên biệt. Nếu cố ý ánh xạ cả hai phía trong cùng mô hình, cần xác minh hành vi đọc/ghi bằng integration test và không cập nhật hai collection một cách thiếu nhất quán.

## Phân biệt chu trình trong graph và vòng tham chiếu trong Java

Hai khái niệm này liên quan nhưng không giống nhau.

**Chu trình trong graph** là một đường đi bắt đầu và kết thúc ở cùng một node. Ví dụ:

~~~cypher
CREATE (a:Service {name: "Catalog"})
CREATE (b:Service {name: "Pricing"})
CREATE (c:Service {name: "Inventory"})
CREATE (a)-[:DEPENDS_ON]->(b)
CREATE (b)-[:DEPENDS_ON]->(c)
CREATE (c)-[:DEPENDS_ON]->(a);
~~~

Graph trên có chu trình **Catalog -> Pricing -> Inventory -> Catalog**. Chu trình có thể hợp lệ trong một số miền nghiệp vụ, chẳng hạn mạng quan hệ xã hội hoặc liên kết giữa các tài liệu. Nhưng nếu mô hình biểu diễn cây phân cấp, chu trình thường vi phạm quy tắc: một danh mục không thể là tổ tiên của chính nó.

**Vòng tham chiếu trong Java object graph** xuất hiện khi các object giữ tham chiếu qua lại. Ví dụ, **parent.children** chứa **child**, đồng thời **child.parent** lại trỏ về **parent**. Khi tuần tự hóa object đầy đủ, bộ tuần tự hóa có thể đi từ cha sang con rồi quay lại cha, lặp vô hạn nếu không có cơ chế xử lý identity hoặc giới hạn độ sâu.

Vì vậy, không thể kết luận graph sai chỉ vì Java object graph có tham chiếu vòng. Cần xác định chu trình có được domain cho phép hay không, và xử lý tuần tự hóa object riêng biệt.

## Khi nào chu trình được phép?

Quy tắc phụ thuộc loại graph:

| Mô hình | Chu trình có hợp lệ? | Quy tắc thường dùng |
|---|---|---|
| Cây danh mục | Không | Mỗi node con có tối đa một cha; không node nào là tổ tiên của chính nó |
| Cây tổ chức | Thường không | Quan hệ quản lý không tạo đường quay lại cấp trên |
| Mạng xã hội | Có thể có | Người dùng có thể theo dõi lẫn nhau |
| Đồ thị phụ thuộc | Thường không nếu cần thứ tự build | Chu trình khiến không thể sắp xếp thứ tự thực thi topo |
| Đồ thị liên kết tài liệu | Có thể có | Tài liệu có thể tham chiếu lẫn nhau |
| Quy trình trạng thái | Tùy thiết kế | Chỉ cho phép chu trình nếu nghiệp vụ có vòng lặp được kiểm soát |

Với cây danh mục, quan hệ **PARENT_OF** cần tạo thành cấu trúc không chu trình. Với mạng xã hội, **FOLLOWS** có thể tạo vòng hai chiều hoặc chu trình dài và điều đó không nhất thiết là lỗi. Không nên áp dụng một quy tắc cấm chu trình chung cho mọi graph.

## Phát hiện thao tác có thể tạo chu trình

Giả sử graph hiện tại có các cạnh:

~~~cypher
CREATE (a:Category {id: "A", name: "Root"})
CREATE (b:Category {id: "B", name: "Books"})
CREATE (c:Category {id: "C", name: "Fiction"})
CREATE (a)-[:PARENT_OF]->(b)
CREATE (b)-[:PARENT_OF]->(c);
~~~

Nếu muốn thêm quan hệ **C -[:PARENT_OF]-> A**, graph sẽ tạo chu trình **A -> B -> C -> A**. Trước khi thêm cạnh từ **parent** tới **child**, cần kiểm tra xem đã tồn tại đường đi từ **child** quay lại **parent** hay chưa.

Truy vấn sau trả về **true** nếu thao tác thêm cạnh có thể tạo chu trình:

~~~cypher
MATCH (child:Category {id: $childId})
MATCH (parent:Category {id: $parentId})
RETURN EXISTS {
    MATCH (child)-[:PARENT_OF*1..]->(parent)
} AS wouldCreateCycle;
~~~

Giải thích:

1. Tìm node sẽ trở thành con và node sẽ trở thành cha.
2. Tìm đường đi theo hướng **PARENT_OF** từ node con hiện tại tới node cha dự kiến.
3. Nếu đường đi tồn tại, thêm cạnh **parent -> child** sẽ khép kín một chu trình.
4. Nếu không có đường đi, thao tác không tạo chu trình theo trạng thái graph vừa kiểm tra.

Ngoài kiểm tra đường đi, cần từ chối trường hợp **parentId** và **childId** giống nhau. Truy vấn chỉ tìm đường có độ dài từ một relationship trở lên, vì vậy trường hợp một node nối chính nó nên được kiểm tra riêng.

Có thể đưa truy vấn vào repository:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CategoryRepository extends Neo4jRepository<Category, String> {

    @Query("""
        MATCH (child:Category {id: $childId})
        MATCH (parent:Category {id: $parentId})
        RETURN EXISTS {
            MATCH (child)-[:PARENT_OF*1..]->(parent)
        } AS wouldCreateCycle
        """)
    boolean wouldCreateCycle(
        @Param("parentId") String parentId,
        @Param("childId") String childId
    );
}
~~~

Đoạn query dùng cú pháp text block của Java và existential subquery của Cypher. Hãy bảo đảm phiên bản Java và Neo4j trong dự án hỗ trợ các cú pháp này. Với phiên bản cũ hơn, có thể viết query thành chuỗi nối hoặc dùng **OPTIONAL MATCH** cùng phép đếm đường đi.

### Kiểm tra trong service trước khi ghi relationship

Quy tắc nghiệp vụ nên nằm ở service để mọi endpoint cùng dùng một cách kiểm tra:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CategoryService {

    private final CategoryRepository categories;

    public CategoryService(CategoryRepository categories) {
        this.categories = categories;
    }

    @Transactional
    public void addChild(String parentId, String childId) {
        if (parentId.equals(childId)) {
            throw new IllegalArgumentException("A category cannot be its own child");
        }

        Category parent = categories.findById(parentId)
            .orElseThrow(() -> new IllegalArgumentException("Parent category not found"));

        Category child = categories.findById(childId)
            .orElseThrow(() -> new IllegalArgumentException("Child category not found"));

        if (categories.wouldCreateCycle(parentId, childId)) {
            throw new IllegalArgumentException("The relationship would create a cycle");
        }

        parent.addChild(child);
        categories.save(parent);
    }
}
~~~

Thứ tự xử lý rất quan trọng: kiểm tra ID tự tham chiếu, xác nhận cả hai node tồn tại, kiểm tra đường đi có thể tạo chu trình rồi mới cập nhật graph. Ví dụ giả định **Category** chỉ quản lý cạnh đi ra qua **children**.

**@Transactional** giúp nhóm thao tác đọc và ghi trong một transaction, nhưng không tự tạo constraint tổng quát để bảo đảm graph luôn không chu trình. Nếu nhiều request đồng thời có thể thay đổi cùng một cây hoặc cùng một vùng graph, hai request có thể cùng kiểm tra trạng thái cũ rồi ghi các cạnh tạo thành chu trình. Với hệ thống có cập nhật đồng thời, cần tuần tự hóa các thao tác thay đổi cấu trúc trên cùng phạm vi hoặc dùng cơ chế khóa/đồng bộ phù hợp, đồng thời kiểm tra lại trước khi ghi.

## Giới hạn traversal và tải object graph

Một self-reference có thể dẫn tới graph rất sâu hoặc có nhiều nhánh. Nếu tải toàn bộ cấu trúc mỗi lần gọi repository, lượng dữ liệu và số object được tạo có thể lớn. Với graph có chu trình, traversal không giới hạn còn có nguy cơ sinh ra rất nhiều đường đi khác nhau.

Hãy xác định rõ use case đọc:

- Màn hình danh mục chỉ cần danh mục gốc và các con trực tiếp: chỉ lấy một cấp.
- Trang chi tiết cần cây con tới độ sâu cố định: dùng traversal có giới hạn.
- Báo cáo cần tất cả hậu duệ: dùng truy vấn chuyên biệt và phân trang hoặc giới hạn kết quả phù hợp.
- API chỉ cần hiển thị danh sách ID liên quan: trả DTO hoặc projection thay vì toàn bộ entity graph.

Ví dụ lấy các node trong cây con tối đa ba cấp:

~~~cypher
MATCH path = (root:Category {id: $rootId})-[:PARENT_OF*0..3]->(node:Category)
RETURN node.id AS id,
       node.name AS name,
       length(path) AS depth
ORDER BY depth, name;
~~~

Đây là kết quả phẳng gồm ID, tên và độ sâu. Có thể ánh xạ thành DTO rồi nhóm theo quan hệ cha/con ở tầng ứng dụng nếu giao diện cần cây lồng nhau. Cách này giúp giới hạn số cấp dữ liệu trả về và tránh buộc API phải serialize toàn bộ object graph.

Đối với mạng có chu trình, hãy cân nhắc truy vấn theo tập node đã thăm hoặc giới hạn độ dài đường đi. Một truy vấn tìm đường trong graph có chu trình có thể trả nhiều path; nếu chỉ cần biết có kết nối hay không, dùng **EXISTS** để dừng ngay khi tìm được đường phù hợp.

## Tránh đệ quy vô hạn khi dùng object trong Java

### Không đưa relationship vào equals, hashCode và toString một cách tự động

Nếu dùng Lombok **@Data** cho entity có quan hệ tự tham chiếu, Lombok có thể sinh **equals**, **hashCode** và **toString** dựa trên các trường. Khi một object chứa object khác rồi object kia lại tham chiếu về object ban đầu, các phương thức này có thể gọi lặp vô hạn hoặc gây **StackOverflowError**.

Với entity dùng Lombok **@Data** (hoặc **@ToString** và **@EqualsAndHashCode**), nên loại trừ trường quan hệ khỏi các phương thức do Lombok sinh:

~~~java
import lombok.EqualsAndHashCode;
import lombok.ToString;

@ToString.Exclude
@EqualsAndHashCode.Exclude
@Relationship(type = "PARENT_OF", direction = Direction.OUTGOING)
private Set<Category> children = new LinkedHashSet<>();
~~~

Không đưa collection relationship vào **equals** hoặc **hashCode** của entity. Nếu dùng **Set**, quy tắc so sánh phần tử cần ổn định; các trường quan hệ có thể thay đổi trong lúc object đang nằm trong hash-based collection.

### Không serialize trực tiếp entity graph thành JSON

Một entity có **children** và một entity con có **parent** có thể tạo vòng tham chiếu khi Jackson chuyển object thành JSON. Cách an toàn hơn là tạo DTO với dữ liệu cần thiết:

~~~java
import java.util.List;

public record CategoryResponse(
    String id,
    String name,
    List<String> childIds
) {
}
~~~

Chuyển entity thành DTO bằng cách chỉ lấy ID các node con:

~~~java
CategoryResponse toResponse(Category category) {
    List<String> childIds = category.getChildren().stream()
        .map(Category::getId)
        .toList();

    return new CategoryResponse(
        category.getId(),
        category.getName(),
        childIds
    );
}
~~~

DTO không giữ tham chiếu ngược về entity cha, do đó không tạo chu trình object khi serialize. Nếu API cần cây lồng nhau, hãy giới hạn độ sâu hoặc dùng một tập ID đã thăm để tránh thêm lại node đã xuất hiện. Có thể dùng cơ chế identity của Jackson trong những trường hợp phù hợp, nhưng DTO thường giúp hợp đồng API rõ ràng và không phụ thuộc cấu trúc persistence.

## Kiểm tra chu trình và tính nhất quán của dữ liệu

Ngoài kiểm tra trước khi ghi, có thể chạy truy vấn kiểm toán để phát hiện chu trình đã tồn tại. Ví dụ tìm các đường quay về node xuất phát:

~~~cypher
MATCH path = (start:Category)-[:PARENT_OF*1..]->(start)
RETURN path
LIMIT 20;
~~~

Truy vấn này có thể tốn tài nguyên nếu graph lớn hoặc có nhiều chu trình. Chỉ chạy trên phạm vi cần kiểm tra, cân nhắc lọc theo node gốc và giới hạn kết quả. Không nên chạy một truy vấn liệt kê tất cả đường đi trong graph dày đặc như một bước kiểm tra thường xuyên.

Với mô hình cây, cần kiểm tra thêm các quy tắc:

- Node không được tự làm cha của chính nó.
- Một node con chỉ có tối đa một node cha nếu domain yêu cầu cấu trúc cây.
- Không tồn tại đường đi từ node con quay về node cha trước khi thêm cạnh cha-con.
- Xóa hoặc di chuyển một node phải giữ các quy tắc về cha, con và node gốc.
- Nếu cho phép nhiều cha, cần xác định rõ mô hình là DAG hay graph tổng quát và chính sách xử lý chu trình.

Neo4j có thể bảo vệ uniqueness của property và một số kiểu/ràng buộc tồn tại tùy phiên bản, nhưng không có uniqueness constraint tổng quát để bảo đảm một node chỉ có một relationship incoming hoặc để cấm mọi chu trình trong graph. Những quy tắc cấu trúc này cần được kiểm tra trong logic nghiệp vụ và các quy trình ghi dữ liệu.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không khai báo đúng **Direction** | Truy vấn hoặc mapping nhìn sai chiều relationship | Chọn rõ **OUTGOING** hoặc **INCOMING** theo hướng cạnh trong graph |
| Dùng một object thay cho collection dù node có nhiều node liên quan | Chỉ biểu diễn được một liên kết trong mô hình Java | Dùng **Set** hoặc **List** theo cardinality |
| Coi mọi chu trình là dữ liệu sai | Loại bỏ các quan hệ hợp lệ như theo dõi lẫn nhau | Xác định quy tắc chu trình theo từng domain |
| Cho phép cây danh mục tạo cạnh tùy ý | Có thể hình thành chu trình và làm sai cấu trúc phân cấp | Kiểm tra đường đi trước khi thêm cạnh |
| Duy trì hai chiều object reference mà không đồng bộ | Java object graph và graph trong Neo4j không còn nhất quán | Chọn một phía ánh xạ hoặc cập nhật hai phía qua helper/service |
| Để Lombok sinh **toString**, **equals**, **hashCode** trên relationship | Đệ quy vô hạn hoặc so sánh object không ổn định | Loại trừ trường quan hệ và dùng identity ổn định |
| Trả entity graph trực tiếp qua REST | JSON tuần tự hóa lặp, payload quá lớn hoặc lộ dữ liệu persistence | Dùng DTO/projection có giới hạn |
| Tải toàn bộ graph tự tham chiếu cho một màn hình nhỏ | Tốn bộ nhớ và thời gian truy vấn | Dùng Cypher có giới hạn độ sâu và projection |
| Chỉ kiểm tra chu trình ở controller | Đường ghi khác có thể bỏ qua quy tắc | Đặt kiểm tra ở service/domain và áp dụng cho batch/import |

## Bài tập thực hành

Xây dựng mô hình cây danh mục với label **Category** và relationship **PARENT_OF**:

1. Tạo entity **Category** có ID dạng String, tên và collection **children** tự tham chiếu.
2. Ánh xạ **children** bằng **@Relationship** với hướng outgoing.
3. Tạo repository hỗ trợ tìm danh mục và kiểm tra đường đi từ node con tới node cha dự kiến.
4. Viết service thêm danh mục con; từ chối khi hai ID giống nhau hoặc khi thao tác tạo chu trình.
5. Tạo dữ liệu **Books -> Fiction -> Mystery**, sau đó thử thêm **Mystery -> Books** và xác nhận service từ chối.
6. Tạo DTO chỉ chứa ID, tên và danh sách ID con; xác nhận API không tuần tự hóa vòng tham chiếu entity.
7. Thử mô hình mạng xã hội với quan hệ **FOLLOWS** và giải thích vì sao chu trình có thể được phép trong miền này.

Khi thiết kế quan hệ tự tham chiếu trong Spring Data Neo4j, hãy xác định rõ chiều relationship, cardinality và quy tắc chu trình của domain. Ánh xạ một phía khi có thể, kiểm soát traversal và dùng DTO để bảo vệ tầng API khỏi vòng tham chiếu trong Java object graph.

