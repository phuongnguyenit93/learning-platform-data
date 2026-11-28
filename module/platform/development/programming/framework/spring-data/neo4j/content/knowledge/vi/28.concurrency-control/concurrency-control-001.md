# Mất cập nhật khi nhiều giao dịch cùng sửa node hoặc relationship

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích hiện tượng lost update khi nhiều transaction cùng đọc rồi ghi một node hoặc relationship.
- Phân biệt khóa ghi tự động của Neo4j với optimistic locking ở tầng Spring Data Neo4j (SDN).
- Dùng `@Version` để phát hiện entity bị cập nhật từ một transaction khác.
- Viết phép cập nhật Cypher nguyên tử cho bộ đếm hoặc thuộc tính cần tăng giảm đồng thời.
- Nhận biết khi nào cần khóa ghi tường minh, xử lý deadlock và retry transaction.
- Chọn cách mô hình hóa phù hợp khi một relationship có trạng thái nghiệp vụ cần được kiểm soát độc lập.

## 1. Lost update là gì?

Lost update (mất cập nhật) xảy ra khi hai transaction cùng đọc một giá trị cũ, tự tính giá trị mới rồi ghi đè lên nhau. Cả hai thao tác ghi có thể hoàn tất, nhưng kết quả cuối cùng chỉ phản ánh một lần thay đổi.

Ví dụ, tồn kho của một sản phẩm đang là 10. Hai đơn hàng đồng thời đặt mỗi đơn một sản phẩm:

| Thời điểm | Transaction A | Transaction B |
| --- | --- | --- |
| 1 | Đọc tồn kho = 10 | |
| 2 | | Đọc tồn kho = 10 |
| 3 | Tính 10 - 1 = 9 | |
| 4 | | Tính 10 - 1 = 9 |
| 5 | Ghi tồn kho = 9 | |
| 6 | | Ghi tồn kho = 9 |
| Kết quả | **Tồn kho = 9** | Đáng lẽ phải là 8 |

Cả hai đơn hàng đều có thể được xử lý thành công, nhưng một lần giảm tồn kho đã bị ghi đè. Đây là lỗi dữ liệu nghiệp vụ, dù từng câu lệnh riêng lẻ không báo lỗi.

Hiện tượng tương tự xảy ra khi nhiều transaction cập nhật:

- Số lượt xem hoặc bộ đếm trên node.
- Điểm số, trạng thái hoặc số lần tham gia trên relationship.
- Số dư, hạn mức, số lượng tồn hoặc số lượng đặt trước.
- Các thuộc tính tổng hợp được tính từ giá trị đọc trước đó.

Điểm chung là giá trị ghi được tính từ một bản đọc đã lỗi thời.

## 2. Vì sao transaction không tự ngăn lost update?

Neo4j cung cấp transaction ACID. Tuy nhiên, mức cô lập mặc định là **read committed**. Một transaction đọc node hoặc relationship không tự giữ khóa ngăn transaction khác ghi lên đối tượng đó trước khi transaction đầu tiên kết thúc.

Neo4j tự động dùng write lock khi thực hiện thay đổi dữ liệu. Khóa này giúp các thao tác ghi đồng thời không sửa cùng một bản ghi tại cùng một thời điểm. Tuy vậy, khóa ghi không tự sửa một giá trị đã được ứng dụng đọc và tính toán từ trước.

Ví dụ luồng đọc và ghi tách thành hai câu truy vấn:

```cypher
// Đọc ở một thời điểm
MATCH (p:Product {id: $id})
RETURN p.stock AS stock
```

Ứng dụng tính `newStock = stock - quantity`, sau đó gửi câu lệnh khác:

```cypher
MATCH (p:Product {id: $id})
SET p.stock = $newStock
```

Khi câu lệnh thứ hai chạy, Neo4j lấy write lock để ghi property. Nhưng `$newStock` đã được tính từ lần đọc cũ. Nếu transaction khác đã cập nhật trước đó, câu lệnh vẫn có thể ghi giá trị cũ lên trên giá trị mới.

Vì thế cần phân biệt:

- **Write lock của Neo4j:** tuần tự hóa việc sửa cùng node hoặc relationship trong lúc ghi.
- **Optimistic locking của SDN:** phát hiện object được lưu dựa trên version đã cũ.
- **Cập nhật nguyên tử trong Cypher:** đọc giá trị hiện tại và tính giá trị mới ngay trong biểu thức ghi có dependency trực tiếp.

`@Transactional` xác định ranh giới commit và rollback. Nó không tự biến mọi lần đọc thành thao tác khóa và không tự bật optimistic locking.

## 3. Lost update có thể xảy ra trên cả node và relationship

Node và relationship đều có property. Neo4j có thể lấy write lock ở cấp node hoặc relationship khi property được thêm, thay đổi hoặc xóa.

Ví dụ cập nhật điểm trên node:

```cypher
MATCH (p:Person {id: $personId})
SET p.score = $newScore
RETURN p.score AS score
```

Ví dụ cập nhật điểm trên relationship:

```cypher
MATCH (p:Person {id: $personId})
      -[r:MEMBER_OF]->
      (d:Department {id: $departmentId})
SET r.score = $newScore
RETURN r.score AS score
```

Nếu `$newScore` được tính từ dữ liệu đã đọc trong một request trước đó, hai transaction vẫn có thể ghi đè giá trị của nhau. Khóa ghi ở cấp relationship chỉ bảo vệ thao tác ghi đang diễn ra; nó không xác nhận rằng dữ liệu đầu vào của ứng dụng vẫn mới nhất.

Trong SDN, relationship có property thường được ánh xạ bằng `@RelationshipProperties`. `@RelationshipId` giúp SDN nhận diện relationship khi lưu object graph. Đây là định danh kỹ thuật của relationship, không phải bộ đếm version để phát hiện mọi cập nhật đồng thời.

## 4. Dùng @Version để phát hiện cập nhật trên entity

SDN hỗ trợ optimistic locking bằng annotation `@Version` trên một field kiểu `Long`. SDN tự tăng version khi cập nhật và kiểm tra version hiện tại trong thao tác lưu. Không tự gán hoặc tăng field này trong code nghiệp vụ.

Ví dụ entity tồn kho:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    private String id;

    @Version
    private Long version;

    private long stock;

    protected Product() {
    }

    public Product(String id, long stock) {
        this.id = id;
        this.stock = stock;
    }

    public long getStock() {
        return stock;
    }

    public void decreaseStock(long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (stock < quantity) {
            throw new IllegalStateException("Insufficient stock");
        }
        stock -= quantity;
    }
}
```

Repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ProductRepository
        extends Neo4jRepository<Product, String> {
}
```

Service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final ProductRepository productRepository;

    public InventoryService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional
    public Product reserve(String productId, long quantity) {
        Product product = productRepository.findById(productId)
            .orElseThrow();

        product.decreaseStock(quantity);

        return productRepository.save(product);
    }
}
```

Giả sử hai transaction cùng tải một sản phẩm ở version 4:

1. Transaction A đọc `stock = 10, version = 4`.
2. Transaction B cũng đọc `stock = 10, version = 4`.
3. A giảm tồn kho còn 9 và lưu thành công. SDN tăng version lên 5.
4. B cố lưu object vẫn mang version 4.
5. SDN phát hiện version trong object không còn khớp với dữ liệu hiện tại và ném `OptimisticLockingFailureException`.

Transaction B phải đọc lại dữ liệu mới nhất rồi thực hiện lại quy tắc nghiệp vụ. Với tồn kho, lần đọc mới sẽ thấy 9 trước khi quyết định có thể đặt thêm hàng hay không.

### 4.1. Version được quản lý như thế nào?

- Dùng field kiểu `Long` có `@Version`.
- Giá trị version khởi đầu do SDN quản lý.
- SDN tăng version khi cập nhật entity thành công.
- Không tự sửa version trong setter hoặc service.
- Nếu version cũ không còn khớp, thao tác lưu thất bại bằng `OptimisticLockingFailureException`.
- Khi xử lý xung đột, tải entity mới và áp dụng lại ý định nghiệp vụ lên trạng thái mới.

`@Version` cũng cần thiết khi entity dùng business ID do ứng dụng gán để SDN phân biệt entity mới và entity đã tồn tại.

### 4.2. Version kiểm soát phạm vi nào?

`@Version` bảo vệ thao tác lưu entity có trường version. Không nên xem version của một node là khóa version tự động cho mọi node và relationship có thể truy cập từ node đó.

Nếu một relationship có trạng thái nghiệp vụ được nhiều luồng cập nhật độc lập, hãy xác định rõ phạm vi cần kiểm soát. Có thể dùng Cypher cập nhật nguyên tử trực tiếp trên relationship, hoặc mô hình hóa quan hệ đó thành một node riêng nếu nó cần vòng đời, repository và version độc lập.

## 5. Retry đúng cách sau OptimisticLockingFailureException

Optimistic locking không tự giải quyết xung đột. Nó phát hiện object đã cũ và yêu cầu ứng dụng quyết định cách xử lý.

Một quy trình retry hợp lý:

1. Nhận `OptimisticLockingFailureException`.
2. Kết thúc transaction thất bại.
3. Bắt đầu transaction mới.
4. Đọc lại entity để lấy giá trị và version hiện tại.
5. Kiểm tra lại điều kiện nghiệp vụ.
6. Áp dụng thay đổi trên trạng thái mới.
7. Lưu lại; nếu tiếp tục xung đột thì retry trong giới hạn đã định.

Không retry bằng cách gọi `save()` lặp lại với chính object cũ, vì object vẫn chứa version không hợp lệ. Cũng không nên bắt exception rồi tiếp tục làm việc trong transaction đã bị đánh dấu rollback-only.

Retry nên có số lần thử hữu hạn và backoff ngắn có jitter khi tải đồng thời cao. Chỉ retry lỗi có thể phục hồi như optimistic locking hoặc deadlock; không retry các lỗi dữ liệu sai, vi phạm constraint hay lỗi nghiệp vụ.

Nếu transaction có gửi email, gọi thanh toán hoặc phát message, hãy tránh thực hiện side effect lặp lại trong mỗi lần retry. Có thể dùng outbox hoặc idempotency key để tách việc commit dữ liệu khỏi việc phát sự kiện ra hệ thống ngoài.

## 6. Dùng phép cập nhật nguyên tử trong Cypher

Với bộ đếm hoặc phép cộng trừ đơn giản, có thể để Neo4j đọc giá trị hiện tại và tính giá trị mới trong cùng biểu thức `SET`.

Ví dụ tăng bộ đếm:

```cypher
MATCH (c:Counter {id: $id})
SET c.value = coalesce(c.value, 0) + $delta
RETURN c.value AS value
```

Ví dụ tăng điểm của relationship:

```cypher
MATCH (p:Person {id: $personId})
      -[r:MEMBER_OF]->
      (d:Department {id: $departmentId})
SET r.score = coalesce(r.score, 0) + $delta
RETURN r.score AS score
```

Trong các biểu thức này, vế phải của `SET` đọc trực tiếp property đang được cập nhật. Neo4j tự lấy write lock trước khi đọc giá trị đó, nhờ vậy các lần tăng đồng thời được tuần tự hóa và không bị mất như cách đọc ở request trước rồi ghi một hằng số mới.

Đây là lựa chọn phù hợp cho phép cập nhật có tính cộng dồn, chẳng hạn tăng lượt xem, cộng điểm hoặc điều chỉnh bộ đếm. `coalesce()` xử lý trường hợp property chưa có giá trị.

Không nên tách biểu thức thành một bước `WITH c.value AS current` rồi mới tính và ghi lại nếu cần bảo đảm phép cập nhật nguyên tử. Khi giá trị được đọc ở một statement trước hoặc không còn dependency trực tiếp trong biểu thức `SET`, Neo4j có thể không lấy write lock trước lúc đọc giá trị cũ.

### 6.1. Cập nhật có điều kiện nghiệp vụ

Các phép cập nhật phức tạp như đặt chỗ, trừ tồn kho có điều kiện hoặc chuyển trạng thái cần kiểm tra cả điều kiện và thay đổi dữ liệu trong cùng một quy trình được bảo vệ.

Không nên chỉ kiểm tra điều kiện ở một truy vấn, rồi để ứng dụng tính giá trị mới và gửi một truy vấn ghi khác. Một transaction khác có thể thay đổi dữ liệu giữa hai bước.

Với entity được quản lý bằng SDN, `@Version` là lựa chọn rõ ràng để phát hiện trạng thái đã thay đổi. Với custom Cypher, cần thiết kế điều kiện, biểu thức ghi và khóa sao cho việc kiểm tra không dựa trên một giá trị đã lỗi thời. Hãy kiểm thử tình huống hai transaction cùng vượt qua điều kiện ở thời điểm gần nhau, không chỉ kiểm thử từng request riêng lẻ.

## 7. Khi cần khóa ghi tường minh

Có trường hợp phép tính phụ thuộc vào nhiều bước hoặc nhiều property, khiến Cypher không thể dùng dependency trực tiếp trong biểu thức `SET`. Khi đó, Neo4j có thể không tự lấy write lock trước thời điểm đọc property cần thiết.

Tài liệu Neo4j mô tả một workaround để lấy write lock tường minh: ghi rồi xóa ngay một property tạm trên node hoặc relationship. Khóa ghi vẫn được giữ đến khi transaction kết thúc.

Ví dụ trên node:

```cypher
MATCH (n:Counter {id: $id})
SET n.__writeLock = true
REMOVE n.__writeLock
WITH n, n.value AS currentValue
// Tính toán các giá trị phụ thuộc currentValue tại đây.
SET n.value = currentValue + $delta
RETURN n.value AS value
```

Ví dụ trên relationship có thể áp dụng cùng ý tưởng bằng cách đặt và xóa property tạm trên biến relationship.

Cách này cần được dùng thận trọng:

- Thực hiện trong cùng một transaction.
- Đảm bảo property tạm không bị ứng dụng khác sử dụng.
- Giữ thời gian transaction ngắn để giảm lock contention.
- Chỉ dùng khi phép cập nhật không thể viết thành biểu thức nguyên tử đơn giản.
- Kiểm tra kỹ mọi nhánh truy vấn để property tạm được xóa trước commit.

Đây là workaround về khóa, không phải cú pháp khóa chuyên biệt của Cypher. Nếu có thể biểu diễn phép cập nhật bằng dependency trực tiếp trong `SET`, hãy ưu tiên cách đó.

## 8. Kiểm soát cập nhật relationship

Neo4j lấy write lock trên relationship khi property của relationship được thêm, thay đổi hoặc xóa. Điều này bảo vệ thao tác ghi ở cấp relationship, nhưng ứng dụng vẫn cần tránh gửi giá trị đã tính từ một lần đọc cũ.

Ví dụ `Membership` là relationship có property `score`:

```cypher
MATCH (p:Person {id: $personId})
      -[membership:MEMBER_OF]->
      (d:Department {id: $departmentId})
SET membership.score =
    coalesce(membership.score, 0) + $delta
RETURN membership.score AS score
```

Vì biểu thức cập nhật phụ thuộc trực tiếp vào `membership.score`, Neo4j có thể lấy write lock trước khi đọc property để tính giá trị mới.

Trong mô hình SDN, relationship có property có thể được ánh xạ bằng:

```java
@RelationshipProperties
public class Membership {

    @RelationshipId
    private Long relationshipId;

    private long score;

    @TargetNode
    private Department department;
}
```

`@RelationshipId` giúp SDN nhận diện relationship trong object graph. Nó không phải optimistic version. Nếu nhiều transaction sửa độc lập cùng một relationship, cần quyết định rõ chiến lược:

- Dùng custom Cypher với biểu thức cập nhật nguyên tử nếu thay đổi là phép cộng dồn.
- Giữ transaction ngắn và giới hạn phạm vi relationship được cập nhật.
- Nếu relationship có trạng thái phức tạp, nhiều thuộc tính cần kiểm soát đồng thời và vòng đời riêng, cân nhắc mô hình hóa nó thành node `Membership` với `@Id` và `@Version`.
- Nếu cần khóa cho phép tính nhiều bước, dùng cơ chế khóa tường minh đã được kiểm tra trong môi trường Neo4j mục tiêu.

Khi chuyển relationship thành node, membership trở thành một entity độc lập. Ứng dụng có thể tải, kiểm tra version, cập nhật và lưu nó như một aggregate riêng.

## 9. Lock contention và deadlock

Khóa ghi giúp dữ liệu nhất quán nhưng cũng khiến transaction phải chờ nếu transaction khác đang giữ khóa trên cùng node hoặc relationship. Đây là lock contention.

Deadlock xảy ra khi hai transaction giữ những khóa khác nhau và chờ khóa mà transaction còn lại đang giữ. Ví dụ:

- Transaction A khóa node `A`, sau đó chờ node `B`.
- Transaction B khóa node `B`, sau đó chờ node `A`.

Neo4j phát hiện deadlock và hủy một transaction với lỗi transient, thường có mã `Neo.TransientError.Transaction.DeadlockDetected`. Ứng dụng có thể retry toàn bộ công việc trong transaction mới.

Một số cách giảm nguy cơ deadlock:

- Cập nhật nhiều node hoặc relationship theo cùng một thứ tự ổn định, chẳng hạn sắp xếp theo ID.
- Giữ transaction ngắn và tránh gọi API bên ngoài khi đang giữ lock.
- Tránh để nhiều luồng cùng ghi vào một node nóng nếu có thể phân vùng hoặc gom cập nhật.
- Giảm số node và relationship bị sửa trong cùng transaction.
- Retry deadlock có giới hạn, có backoff và bắt đầu transaction mới.

Không nên tăng số lần retry vô hạn. Deadlock thường là dấu hiệu các transaction đang cập nhật tài nguyên giao nhau theo thứ tự không nhất quán; cần sửa thiết kế truy cập dữ liệu nếu lỗi xảy ra thường xuyên.

## 10. Chọn chiến lược theo loại cập nhật

| Tình huống | Chiến lược phù hợp |
| --- | --- |
| Cập nhật nhiều field của một node entity qua repository | Dùng `@Version` để phát hiện object cũ |
| Cộng hoặc trừ bộ đếm trên node | Dùng `SET n.value = n.value + $delta` |
| Cộng hoặc trừ property trên relationship | Dùng `SET r.value = r.value + $delta` |
| Cập nhật có điều kiện dựa trên nhiều bước đọc/tính | Thiết kế transaction và khóa ghi tường minh hoặc dùng optimistic version phù hợp |
| Relationship có trạng thái và vòng đời riêng | Cân nhắc chuyển thành node entity có `@Version` |
| Hai transaction sửa nhiều node theo thứ tự khác nhau | Chuẩn hóa thứ tự khóa và cập nhật |
| Gặp optimistic locking hoặc deadlock | Đọc lại dữ liệu và retry toàn bộ transaction mới trong giới hạn |

Không có một cơ chế duy nhất phù hợp với mọi loại cập nhật. `@Version` phù hợp với entity có trạng thái được đọc, sửa và lưu như một đơn vị. Biểu thức Cypher nguyên tử phù hợp với phép cập nhật cộng dồn. Khóa ghi tường minh dành cho các trường hợp cần đọc nhiều bước dưới sự bảo vệ của cùng một khóa.

## 11. Quy trình xử lý khi nghi ngờ mất cập nhật

Khi phát hiện số liệu hoặc relationship property không khớp với số request thành công, hãy kiểm tra theo trình tự:

1. Xác định các transaction nào cùng sửa một node hoặc relationship.
2. Kiểm tra ứng dụng có đọc giá trị rồi tính giá trị mới ngoài Cypher hay không.
3. Kiểm tra các câu `SET` có dependency trực tiếp vào property đang cập nhật hay không.
4. Nếu dùng SDN `save()`, xác định entity đã có `@Version` và mọi luồng ghi có dùng cùng cơ chế version hay không.
5. Kiểm tra custom Cypher có bỏ qua version hoặc ghi đè property do một luồng khác quản lý hay không.
6. Đọc log để phân biệt `OptimisticLockingFailureException`, lock wait và deadlock.
7. Kiểm tra transaction có được retry bằng dữ liệu mới và transaction mới hay không.
8. Tạo test đồng thời với hai hoặc nhiều transaction cùng cập nhật một giá trị, sau đó xác nhận kết quả cuối cùng.

Test concurrency cần tạo được tình huống các transaction đọc gần như cùng thời điểm. Test tuần tự từng request không chứng minh hệ thống đã xử lý đúng lost update.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đọc property, tính trong Java rồi ghi giá trị cố định | Ghi đè cập nhật của transaction khác | Dùng `@Version` hoặc biểu thức Cypher nguyên tử |
| Nghĩ `@Transactional` tự ngăn lost update | Transaction vẫn có thể đọc dữ liệu cũ theo read committed | Chọn optimistic locking hoặc atomic update |
| Tự tăng field `@Version` | Làm sai cơ chế version do SDN quản lý | Để SDN tự tăng version |
| Retry cùng object cũ sau optimistic lock failure | Version vẫn lỗi thời, xung đột tiếp tục | Tải lại entity trong transaction mới rồi áp dụng lại nghiệp vụ |
| Nghĩ `@RelationshipId` là version | Không phát hiện được cập nhật relationship cũ | Phân biệt relationship identity với version |
| Dùng node version như khóa cho toàn bộ graph | Không bảo vệ mọi relationship độc lập | Xác định aggregate và phạm vi version |
| Dùng phép tính nhiều bước sau khi đọc property mà không khóa | Có thể mất cập nhật | Dùng atomic expression hoặc khóa ghi tường minh |
| Giữ transaction lâu khi đang có write lock | Tăng lock contention và nguy cơ deadlock | Rút ngắn transaction |
| Retry mọi loại lỗi | Lặp lại lỗi dữ liệu hoặc nghiệp vụ không thể phục hồi | Chỉ retry lỗi transient phù hợp và giới hạn số lần |
| Cập nhật nhiều node theo thứ tự ngẫu nhiên | Tăng nguy cơ deadlock | Sắp xếp thứ tự cập nhật nhất quán |

## 13. Câu hỏi tự kiểm tra

1. Lost update xảy ra như thế nào khi hai transaction cùng giảm tồn kho?
2. Vì sao write lock của Neo4j không tự sửa một giá trị đã được ứng dụng đọc và tính từ trước?
3. Mức cô lập mặc định của Neo4j là gì?
4. `@Version` giúp SDN phát hiện tình huống nào?
5. Khi gặp `OptimisticLockingFailureException`, vì sao phải tải lại entity?
6. Vì sao không nên tự tăng field version trong service?
7. Điều gì làm cho `SET n.counter = n.counter + 1` an toàn hơn cách đọc rồi ghi giá trị tính ở Java?
8. Neo4j lấy write lock ở đâu khi cập nhật property của relationship?
9. `@RelationshipId` khác `@Version` như thế nào?
10. Khi nào nên chuyển một relationship có trạng thái phức tạp thành node entity?
11. Deadlock xảy ra khi nào và vì sao retry phải bắt đầu transaction mới?
12. Vì sao test concurrency cần chạy các transaction thực sự đồng thời?

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1 – Optimistic locking với @Version](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html#mapping-annotations.optimistic-locking)
- [Neo4j Operations Manual – Concurrent data access và lost updates](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Neo4j Operations Manual – Transaction management](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/)

## Kết luận

Lost update thường xuất hiện khi nhiều transaction cùng đọc một trạng thái cũ rồi ghi lại giá trị được tính từ trạng thái đó. Neo4j có write lock để bảo vệ thao tác sửa node và relationship, nhưng mức cô lập read committed không tự ngăn mọi tình huống ghi đè từ dữ liệu đã đọc trước đó.

Trong Spring Data Neo4j, dùng `@Version` để phát hiện entity được lưu bằng version cũ và đọc lại trước khi retry. Với phép cộng dồn đơn giản, dùng biểu thức Cypher có dependency trực tiếp như `SET n.value = n.value + $delta` để Neo4j khóa trước khi đọc giá trị cần cập nhật. Với relationship, áp dụng cùng nguyên tắc trên property của relationship; nếu cần kiểm soát trạng thái độc lập và phức tạp, cân nhắc mô hình hóa relationship thành node entity.

Giữ transaction ngắn, cập nhật nhiều tài nguyên theo thứ tự nhất quán và retry có giới hạn trong transaction mới. Kết hợp đúng optimistic locking, atomic update và quản lý write lock sẽ giúp ứng dụng tránh mất cập nhật khi nhiều request cùng thay đổi dữ liệu đồ thị.
