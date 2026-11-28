# Loại bỏ dữ liệu không lưu bằng @Transient

Một entity Spring Data Neo4j có thể chứa cả dữ liệu được lưu trong graph và dữ liệu chỉ phục vụ xử lý trong ứng dụng. Ví dụ, một `Product` có mã, tên và giá cần lưu trên node, nhưng cũng có thể có nhãn hiển thị đã ghép, chuỗi tìm kiếm tạm hoặc giá trị cache được tính trong lúc chạy. Annotation `@Transient` cho Spring Data biết một thuộc tính không thuộc dữ liệu cần ánh xạ xuống Neo4j.

Hiểu đúng `@Transient` giúp entity giữ được các tiện ích cần cho Java mà không tạo property thừa trong graph. Đồng thời, ta cần nhận diện những dữ liệu thực sự phải truy vấn, lập chỉ mục hoặc bảo toàn qua các lần khởi động để không vô tình loại chúng khỏi mô hình lưu trữ.

## 1. `@Transient` dùng để làm gì?

`@Transient` là annotation của Spring Data, nằm trong package `org.springframework.data.annotation`. Khi đặt annotation lên một thuộc tính của entity, thuộc tính đó được loại khỏi metadata ánh xạ persistence của Spring Data Neo4j.

Ví dụ, node `Product` cần lưu `productId`, `name` và `priceMinor`. Thuộc tính `displayLabel` chỉ là dữ liệu phụ trợ để hiển thị trong ứng dụng:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    private String productId;

    private String name;
    private long priceMinor;

    @Transient
    private String displayLabel;

    protected Product() {
    }

    public String getDisplayLabel() {
        if (displayLabel == null) {
            displayLabel = name + " - " + priceMinor;
        }
        return displayLabel;
    }

    public void rename(String newName) {
        this.name = newName;
        this.displayLabel = null;
    }
}
```

Trong ví dụ:

- `productId`, `name` và `priceMinor` là dữ liệu được SDN ánh xạ vào node `Product`.
- `displayLabel` là thuộc tính Java được đánh dấu `@Transient`, không được SDN đọc hoặc ghi như một property của node.
- `getDisplayLabel()` tính giá trị khi ứng dụng cần hiển thị. Giá trị cache được đặt lại khi tên sản phẩm thay đổi.

`@Transient` không làm cho cả entity trở thành transient. Entity vẫn được lưu như bình thường; chỉ thuộc tính được đánh dấu bị loại khỏi mapping.

## 2. Import đúng annotation

Với Spring Data Neo4j, dùng annotation:

```java
import org.springframework.data.annotation.Transient;
```

Đây là annotation của Spring Data Commons, được sử dụng trong hệ thống mapping của Spring Data. Đừng nhầm nó với `transient` trong Java. Từ khóa `transient` của Java liên quan đến cơ chế Java Serialization; annotation Spring Data thể hiện rõ ý định loại một thuộc tính khỏi persistence mapping.

Ví dụ dùng trên field:

```java
@Transient
private String calculatedSummary;
```

Hãy giữ import rõ ràng và nhất quán trong entity. Đặc biệt, nếu dự án có nhiều thư viện persistence, kiểm tra package của annotation để chắc chắn đang dùng annotation Spring Data mà SDN nhận diện.

## 3. Khi nào nên đánh dấu thuộc tính là transient?

Một thuộc tính phù hợp với `@Transient` khi giá trị của nó chỉ phục vụ vòng đời xử lý trong ứng dụng và không cần tồn tại như dữ liệu graph.

Các trường hợp thường gặp:

1. **Giá trị tính toán:** chuỗi hiển thị ghép từ tên và giá, tổng tạm tính được tính từ dữ liệu đã nạp.
2. **Cache trong bộ nhớ entity:** kết quả tính toán có chi phí cao và có thể tính lại từ các property đã lưu.
3. **Dữ liệu phục vụ giao diện:** nhãn, trạng thái trình bày hoặc nội dung đã định dạng theo locale hiện tại.
4. **Dữ liệu tạm của một quy trình:** cờ hoặc giá trị trung gian chỉ cần trong thời gian xử lý một request.
5. **Thông tin phụ trợ không thuộc miền lưu trữ:** một giá trị được tạo từ cấu hình ứng dụng hoặc từ service khác sau khi entity được nạp.

Ví dụ, tổng tiền của đơn hàng có thể được tính từ các dòng hàng đã nạp:

```java
@Node("PurchaseOrder")
public class PurchaseOrder {

    @Id
    private String orderId;

    @Relationship(type = "HAS_LINE")
    private List<OrderLine> lines = new ArrayList<>();

    @Transient
    private Long cachedTotalMinor;

    public long totalMinor() {
        if (cachedTotalMinor == null) {
            cachedTotalMinor = lines.stream()
                    .mapToLong(line -> line.getQuantity() * line.getUnitPriceMinor())
                    .sum();
        }
        return cachedTotalMinor;
    }
}
```

Đây là ví dụ rút gọn; cần có import, constructor và accessor phù hợp với entity thực tế. Khi thêm, xóa hoặc thay đổi một dòng hàng, phải vô hiệu hóa `cachedTotalMinor` để tránh dùng tổng cũ. Nếu tổng tiền là dữ liệu chốt theo nghiệp vụ, cần lưu nó như property có chủ đích thay vì coi nó là cache tạm.

## 4. Dữ liệu transient không được lưu và nạp lại

Khi lưu entity, SDN chỉ ánh xạ các thuộc tính persistent. Giá trị của field `displayLabel` trong ví dụ không được ghi thành property trên node. Khi đọc entity từ Neo4j, SDN cũng không lấy một property cùng tên để gán vào field transient.

Ví dụ, sau khi lưu một sản phẩm, node có thể có dạng:

```cypher
(:Product {
    productId: 'PRD-01',
    name: 'Keyboard',
    priceMinor: 850000
})
```

Node không cần property `displayLabel`. Nếu entity được tải lại, `displayLabel` bắt đầu ở trạng thái chưa có giá trị và getter có thể tính lại từ `name` cùng `priceMinor`.

Có thể kiểm tra các property thực sự có trên node bằng Cypher:

```cypher
MATCH (p:Product {productId: 'PRD-01'})
RETURN properties(p) AS storedProperties;
```

Kết quả cho biết dữ liệu đang được lưu trong graph. Việc một field có trong class Java không đồng nghĩa nó sẽ trở thành property; metadata mapping mới quyết định điều đó.

## 5. `@Transient` không phải là cách đổi tên property

`@Transient` loại thuộc tính khỏi persistence mapping. Nếu thuộc tính cần được lưu nhưng tên trong graph khác tên field Java, dùng `@Property` để ánh xạ tên property.

Ví dụ:

```java
import org.springframework.data.neo4j.core.schema.Property;

@Property("db_property_name")
private String displayName;
```

Trong ví dụ này, `displayName` vẫn được lưu, nhưng tên property trong Neo4j là `display_name`. Nếu đánh dấu cùng field bằng `@Transient`, mục tiêu lưu dữ liệu sẽ bị triệt tiêu. Hãy chọn annotation theo ý nghĩa thực tế của dữ liệu:

| Nhu cầu | Cách ánh xạ |
|---|---|
| Không lưu thuộc tính trong graph | `@Transient` |
| Lưu thuộc tính với tên khác | `@Property("db_property_name")` |
| Lưu node entity | `@Node` |
| Ánh xạ relationship có property | `@RelationshipProperties` |

Không dùng `@Transient` chỉ để né một lỗi mapping hoặc để ẩn một field đang chứa dữ liệu nghiệp vụ cần lưu.

## 6. Không dùng transient cho dữ liệu cần truy vấn

Một thuộc tính nên được lưu trong Neo4j nếu nghiệp vụ cần tìm kiếm, lọc, sắp xếp, tạo constraint, lập index hoặc bảo toàn giá trị qua các lần tải entity. Thuộc tính transient không tồn tại như property của node nên Cypher không thể đọc nó như dữ liệu đã lưu.

Ví dụ, nếu `normalizedName` cần được dùng để tìm sản phẩm theo tên không phân biệt dấu hoặc chữ hoa chữ thường, có hai hướng thiết kế:

- Tính giá trị trong ứng dụng khi cần và so sánh trong bộ nhớ nếu tập dữ liệu nhỏ, phạm vi rõ ràng.
- Lưu một property chuẩn hóa trong graph nếu cần truy vấn hiệu quả, lập index hoặc dùng giá trị đó trong nhiều use case.

Nếu chọn lưu, không đánh dấu property đó là `@Transient`. Hãy xác định rõ quy tắc đồng bộ giá trị chuẩn hóa mỗi khi tên gốc thay đổi.

Tương tự, không nên đánh dấu các dữ liệu sau là transient nếu chúng là dữ liệu nghiệp vụ cần tồn tại lâu dài:

- Mã định danh, trạng thái nghiệp vụ hoặc ngày hiệu lực.
- Giá bán đã chốt, số lượng tồn hoặc số dư cần kiểm soát.
- Giá trị cần dùng trong `MATCH`, `WHERE`, `ORDER BY` hoặc constraint.
- Dữ liệu cần được chia sẻ giữa nhiều service hoặc nhiều phiên làm việc.

## 7. `@Transient` và repository query

Repository query chạy trên dữ liệu của Neo4j. Vì field transient không được ánh xạ thành property, không thể dựa vào nó để tạo derived query method hoặc điều kiện Cypher như thể nó tồn tại trên node.

Ví dụ, nếu `displayLabel` được đánh dấu transient, một truy vấn kiểu:

```cypher
MATCH (p:Product)
WHERE p.displayLabel CONTAINS $keyword
RETURN p;
```

sẽ không tìm được dữ liệu dựa trên giá trị do getter Java tính ra, bởi Cypher chỉ nhìn thấy property thực sự có trên node. Hãy lọc theo các property persistent, hoặc tính giá trị ngay trong Cypher nếu biểu thức đó có thể được thực hiện từ dữ liệu lưu trữ.

Nếu một truy vấn cần trả về giá trị tính toán chỉ dành cho màn hình, hãy dùng projection hoặc DTO thay vì cố gán giá trị đó vào field transient của entity:

```java
public interface ProductView {
    String getProductId();
    String getName();
    String getDisplayLabel();
}
```

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends Neo4jRepository<Product, String> {

@Query("""
    MATCH (p:Product {productId: $productId})
    RETURN p.productId AS productId,
           p.name AS name,
           p.name + ' - ' + toString(p.priceMinor) AS displayLabel
    """)
    Optional<ProductView> findProductView(@Param("productId") String productId);
}
```

Projection biểu diễn dữ liệu kết quả của use case đọc. Nó không làm cho `displayLabel` trở thành property được lưu trên node.

## 8. Nếu graph đã có property cũ cùng tên

Thêm `@Transient` vào entity chỉ thay đổi cách Spring Data ánh xạ thuộc tính. Annotation không phải một lệnh migration để chủ động xóa property cũ đã được ghi trước đó bằng Cypher hoặc bởi phiên bản ứng dụng trước.

Nếu cần dọn dữ liệu cũ, hãy thực hiện migration có kiểm soát. Ví dụ, sau khi xác nhận `displayLabel` không còn được ứng dụng nào sử dụng:

```cypher
MATCH (p:Product)
REMOVE p.displayLabel;
```

Lệnh trên xóa property khỏi các node `Product` đã khớp. Trước khi chạy trên môi trường có dữ liệu thật, cần xác định phạm vi node, sao lưu hoặc có phương án khôi phục phù hợp và kiểm tra các phiên bản ứng dụng còn đang đọc property đó.

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `@Transient` cho thuộc tính cần lưu | Giá trị không được SDN ghi vào node | Bỏ annotation hoặc chuyển sang property persistent |
| Mong field transient được khôi phục khi tải entity | Giá trị runtime không được nạp từ graph | Tính lại sau khi tải hoặc dùng projection phù hợp |
| Dùng field transient trong Cypher `WHERE` | Cypher không thấy giá trị do Java getter tạo ra | Lọc bằng property đã lưu hoặc tính biểu thức trong truy vấn |
| Quên xóa cache transient khi dữ liệu nguồn thay đổi | Getter có thể trả về giá trị cũ | Vô hiệu hóa cache trong các phương thức cập nhật hoặc tính trực tiếp |
| Nhầm `@Transient` với `@Property` | Thuộc tính bị loại khỏi mapping thay vì đổi tên | Dùng `@Property` nếu cần lưu dưới tên khác |
| Nghĩ rằng annotation tự xóa property cũ trong graph | Dữ liệu legacy có thể vẫn còn | Viết migration Cypher riêng sau khi đánh giá ảnh hưởng |
| Dùng transient cho trạng thái nghiệp vụ | Trạng thái mất sau khi entity được tải lại | Lưu trạng thái thành property persistent |

## 10. Quy trình quyết định một field có nên transient

Trước khi thêm `@Transient`, hãy trả lời các câu hỏi sau:

1. Giá trị có cần tồn tại sau khi ứng dụng khởi động lại hoặc entity được tải lại không?
2. Có use case nào cần tìm, lọc, sắp xếp hoặc lập index theo giá trị này trong Neo4j không?
3. Giá trị có thể được tính lại đầy đủ từ các property persistent không?
4. Nếu lưu cache trong entity, có thể xác định và vô hiệu hóa cache mỗi khi dữ liệu nguồn đổi không?
5. Có dữ liệu cũ cùng tên trong graph cần migration không?

Nếu giá trị chỉ phục vụ tính toán hoặc hiển thị trong bộ nhớ và có thể tạo lại từ dữ liệu persistent, `@Transient` là lựa chọn phù hợp. Nếu giá trị là một phần của trạng thái nghiệp vụ hoặc cần truy vấn trong graph, hãy mô hình hóa nó thành property persistent.

## Kết luận

`@Transient` của Spring Data (`org.springframework.data.annotation.Transient`) đánh dấu một thuộc tính Java không tham gia ánh xạ persistence của Spring Data Neo4j. Annotation phù hợp với cache, giá trị dẫn xuất và dữ liệu phụ trợ chỉ tồn tại trong lúc ứng dụng chạy. Những thuộc tính cần truy vấn, lập index hoặc bảo toàn qua các lần tải entity phải tiếp tục được lưu thành property của node. Hãy phân biệt rõ dữ liệu runtime với dữ liệu miền nghiệp vụ để entity vừa tiện cho Java vừa phản ánh chính xác graph được lưu trữ.
