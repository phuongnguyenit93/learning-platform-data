# Giới hạn ổn định của định danh nội bộ và lựa chọn ID công khai

Bài học này thuộc chương **Định danh** của module **SPRING_DATA_NEO4J**. Khi xây dựng tầng dữ liệu đồ thị bằng Spring Data Neo4j, ta cần định danh node để ánh xạ entity, lưu và tải dữ liệu qua repository, cũng như liên kết dữ liệu với các hệ thống bên ngoài. Một định danh thuận tiện cho cơ sở dữ liệu chưa chắc là định danh phù hợp để đưa vào API hoặc lưu lâu dài ở hệ thống khác.

Neo4j quản lý định danh nội bộ cho node và relationship. Ứng dụng cũng có thể lưu một thuộc tính ID do mình tạo và kiểm soát. Hai loại định danh phục vụ những mục đích khác nhau. Bài học này giải thích giới hạn ổn định của ID nội bộ, cách Spring Data Neo4j ánh xạ ID và các tiêu chí chọn ID công khai có thể duy trì qua nhiều phiên bản ứng dụng, lần triển khai và hệ thống tích hợp.

## 1. Định danh nội bộ trong Neo4j

Mỗi node và relationship trong Neo4j có một định danh do cơ sở dữ liệu quản lý. Định danh này giúp Neo4j và các công cụ của nó tham chiếu đến phần tử đồ thị. Trong Cypher, các hàm thường gặp là:

```cypher
MATCH (c:Customer {name: 'Lan'})
RETURN id(c), elementId(c);
```

- `id(c)` trả về ID nội bộ dạng số. Hàm `id()` đã bị đánh dấu deprecated trong các phiên bản Neo4j hiện đại; không nên xây dựng API mới phụ thuộc vào nó.
- `elementId(c)` trả về định danh phần tử dạng chuỗi. Đây là cách biểu diễn mới hơn để quan sát hoặc tham chiếu phần tử trong phạm vi mà Neo4j bảo đảm.

Điểm quan trọng là cả hai đều thuộc quyền quản lý của Neo4j. Chúng không phải mã định danh nghiệp vụ do ứng dụng cam kết duy trì. Đặc biệt, `elementId()` không phải một hợp đồng bảo đảm rằng cùng một node sẽ luôn có cùng chuỗi định danh qua mọi transaction hoặc suốt vòng đời của hệ thống. Tài liệu Neo4j giới hạn việc dựa vào định danh phần tử trong phạm vi transaction; ứng dụng không nên lưu nó như khóa tham chiếu lâu dài ở bên ngoài cơ sở dữ liệu.

ID nội bộ cũng có thể được tái sử dụng sau khi node hoặc relationship bị xóa. Vì vậy, một giá trị ID từng trỏ đến một node có thể không còn đại diện cho node đó về sau. Không dùng ID nội bộ làm mã đơn hàng, mã khách hàng, khóa ngoại trong hệ thống khác hoặc định danh được ghi vào URL công khai.

## 2. Phân biệt ID nội bộ và ID do ứng dụng quản lý

Giả sử đồ thị có node khách hàng:

```text
(:Customer {
    name: 'Lan',
    publicId: 'cus_01J8Q7M6K3...'
})
```

Neo4j quản lý ID nội bộ của node. Thuộc tính `publicId` là dữ liệu do ứng dụng ghi vào node và có thể được thiết kế thành định danh bền vững.

| Tiêu chí | ID nội bộ Neo4j | ID do ứng dụng quản lý |
|---|---|---|
| Ai tạo và quản lý? | Neo4j | Ứng dụng hoặc hệ thống định danh được chọn |
| Mục đích chính | Định vị phần tử trong cơ sở dữ liệu | Nhận diện thực thể trong nghiệp vụ và tích hợp |
| Ổn định lâu dài | Không có cam kết phù hợp cho tham chiếu bên ngoài | Có thể được ứng dụng cam kết bất biến |
| Phạm vi sử dụng | Hoạt động nội bộ, chẩn đoán trong phạm vi cho phép | API, URL, thông điệp, log nghiệp vụ và hệ thống khác |
| Ví dụ | `id(node)`, `elementId(node)` | UUID, ULID, mã nghiệp vụ hoặc ID từ nhà cung cấp |

ID công khai không nhất thiết phải được sinh bởi một dịch vụ trung tâm. Điều quan trọng là ứng dụng kiểm soát quy tắc tạo, tính duy nhất, khả năng bất biến và cách duy trì nó qua các thay đổi dữ liệu.

## 3. Ánh xạ ID trong Spring Data Neo4j

Spring Data Neo4j dùng `@Id` để xác định thuộc tính định danh của một node entity. Cách khai báo `@GeneratedValue` ảnh hưởng đến nguồn tạo ID.

### Dùng ID nội bộ do Neo4j sinh

Với cách ánh xạ ID nội bộ mặc định, entity thường được khai báo như sau:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
}
```

`@GeneratedValue` không chỉ định generator sử dụng cơ chế ID nội bộ mặc định của Spring Data Neo4j. Cách này có thể phù hợp khi ID chỉ phục vụ việc ánh xạ entity trong một cơ sở dữ liệu. Không trả `id` này cho client như một ID công khai và không lưu nó vào hệ thống khác để tham chiếu lâu dài.

### Dùng ID do ứng dụng cấp

Nếu muốn một ID có thể xuất hiện trong API và tồn tại qua các lần di chuyển dữ liệu, ứng dụng có thể tạo ID trước khi lưu node. Khi đó, dùng `@Id` mà không dùng `@GeneratedValue`:

```java
import java.util.UUID;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    private String id;

    private String name;

    public Customer() {
    }

    public static Customer create(String name) {
        Customer customer = new Customer();
        customer.id = UUID.randomUUID().toString();
        customer.name = name;
        return customer;
    }
}
```

Khi gọi `Customer.create("Lan")`, ứng dụng sinh UUID và gán vào thuộc tính định danh trước khi lưu:

```java
Customer customer = Customer.create("Lan");
customerRepository.save(customer);
```

Trong trường hợp này, `id` là thuộc tính của node được lưu trong đồ thị. Spring Data Neo4j sử dụng giá trị đó để nhận diện entity. Vì ID được ứng dụng cấp, nó có thể được dùng trong đường dẫn API hoặc thông điệp tích hợp, với điều kiện ứng dụng duy trì tính duy nhất và không thay đổi giá trị sau khi tạo.

Repository phải khai báo kiểu ID khớp với kiểu thuộc tính `@Id`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {
}
```

Với repository này, `findById(id)` nhận giá trị ID ứng dụng đã gán. Nếu entity dùng `Long` làm ID nội bộ, kiểu tham số generic tương ứng phải là `Long`.

## 4. Bảo đảm tính duy nhất của ID công khai

Sinh UUID ở ứng dụng giúp nhiều instance có thể tạo ID mà không cần xin số thứ tự từ một máy chủ trung tâm. Tuy nhiên, lựa chọn thuật toán sinh ID không thay thế ràng buộc dữ liệu. Cơ sở dữ liệu cần bảo vệ tính duy nhất để tránh hai node cùng mang một ID công khai do lỗi ứng dụng, import dữ liệu hoặc thao tác đồng thời.

Với node `Customer`, tạo unique constraint trên thuộc tính ID công khai:

```cypher
CREATE CONSTRAINT customer_public_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.id IS UNIQUE;
```

Unique constraint đảm bảo các giá trị `id` đã có trên các node mang nhãn `Customer` không bị trùng. Ràng buộc này được Neo4j hỗ trợ bằng index tương ứng. Lưu ý, unique constraint không tự bắt buộc mọi node phải có thuộc tính đó; ứng dụng cần bảo đảm thuộc tính ID được gán cho tất cả node trước khi lưu. Khi nâng cấp dữ liệu cũ, hãy kiểm tra và bổ sung các giá trị còn thiếu trước khi tạo ràng buộc.

Nếu mã chỉ duy nhất trong phạm vi một tenant, có thể dùng ràng buộc kết hợp:

```cypher
CREATE CONSTRAINT product_tenant_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE (p.tenantId, p.sku) IS UNIQUE;
```

Trong ví dụ này, cùng một `sku` có thể xuất hiện ở hai tenant khác nhau, nhưng cặp `tenantId` và `sku` phải duy nhất. Cần xác định rõ phạm vi duy nhất của ID trước khi thiết kế constraint và API.

## 5. Chọn loại ID công khai

Không có một định dạng ID phù hợp cho mọi hệ thống. Hãy chọn theo yêu cầu về độ dài, khả năng sinh phân tán, thứ tự, mức độ dễ đoán và khả năng tương thích với hệ thống tích hợp.

### UUID

UUID v4 thường được tạo ngẫu nhiên và có không gian giá trị lớn, phù hợp khi nhiều instance cần tạo ID độc lập. Ví dụ:

```text
550e8400-e29b-41d4-a716-446655440000
```

Ưu điểm là phổ biến, dễ hỗ trợ trong Java và nhiều hệ thống khác, không cần cấp phát tuần tự tập trung. Nhược điểm là chuỗi khá dài và không sắp xếp theo thời điểm tạo. Với UUID ngẫu nhiên, xác suất trùng rất thấp nhưng vẫn nên có unique constraint.

### ULID hoặc ID có thứ tự thời gian

ULID có biểu diễn gọn hơn UUID dạng có dấu gạch nối và có thành phần thời gian giúp sắp xếp gần theo thời điểm tạo. Loại ID này có thể hữu ích cho log, phân trang theo thứ tự tạo hoặc quan sát dữ liệu. Đổi lại, nó làm lộ thông tin gần đúng về thời điểm tạo và thứ tự phát sinh. Không nên dùng thứ tự ID như bằng chứng về thứ tự nghiệp vụ nếu hệ thống có xử lý bất đồng bộ hoặc đồng hồ giữa các máy không đồng nhất.

### Mã nghiệp vụ tự nhiên

Một mã như `INV-2026-000123` có thể dễ đọc và thuận tiện khi trao đổi với người dùng. Chỉ dùng mã nghiệp vụ làm định danh chính nếu nó có quy tắc duy nhất rõ ràng, không thay đổi trong suốt vòng đời thực thể và có thể được duy trì qua các hệ thống.

Nhiều thuộc tính nghiệp vụ có vẻ ổn định nhưng thực tế có thể thay đổi: email khách hàng, số điện thoại, tên sản phẩm, mã địa điểm hoặc tên đăng nhập. Khi một thuộc tính có thể đổi, hãy lưu nó như dữ liệu nghiệp vụ và dùng ID riêng làm định danh bền vững. Nếu cần tìm theo email, tạo index hoặc constraint phù hợp cho email mà không biến email thành định danh bất biến.

### ID từ hệ thống bên ngoài

Nếu node đại diện cho dữ liệu từ nhà cung cấp, có thể cần lưu ID của nhà cung cấp. Hãy ghi nhận cả nguồn phát hành ID, ví dụ `provider` và `externalId`, vì hai nhà cung cấp có thể cùng phát hành một chuỗi. Nếu ID chỉ duy nhất trong phạm vi một tài khoản tích hợp, phạm vi tài khoản hoặc tenant cũng phải tham gia khóa kết hợp.

| Lựa chọn | Phù hợp khi | Điểm cần cân nhắc |
|---|---|---|
| UUID | Sinh phân tán, ID ít phụ thuộc nghiệp vụ | Dài, không có thứ tự thời gian |
| ULID | Cần chuỗi gọn và thứ tự gần theo thời điểm tạo | Có thể tiết lộ thời điểm tạo |
| Mã nghiệp vụ | Người dùng cần đọc hoặc trao đổi mã | Có nguy cơ thay đổi theo quy trình nghiệp vụ |
| ID nhà cung cấp | Đồng bộ dữ liệu với hệ thống ngoài | Phải lưu nguồn và phạm vi duy nhất |

## 6. Có nên giữ cả ID nội bộ và ID công khai?

Một số hệ thống đã sử dụng ID nội bộ trong entity và cần bổ sung ID công khai cho API. Khi đó, có thể lưu thêm thuộc tính `publicId` trên node:

```java
@Node("Customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long internalId;

    private String publicId;

    private String name;
}
```

Trong thiết kế này, `internalId` phục vụ ánh xạ persistence theo cơ chế mặc định, còn `publicId` là thuộc tính do ứng dụng quản lý. Tạo unique constraint cho `publicId` và chỉ dùng thuộc tính này ở biên API. Vì `@Id` vẫn là `internalId`, `CustomerRepository<Customer, Long>.findById(...)` sẽ tìm theo ID nội bộ. Nếu cần tìm theo ID công khai, khai báo phương thức truy vấn riêng:

```java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends Neo4jRepository<Customer, Long> {

    @Query("MATCH (c:Customer {publicId: $publicId}) RETURN c")
    Optional<Customer> findByPublicId(@Param("publicId") String publicId);
}
```

Cách này có thể hữu ích khi chuyển đổi một hệ thống đang vận hành. Tuy nhiên, nó tạo ra hai khái niệm định danh trong entity và cần được đặt tên rõ ràng. Với hệ thống mới, nếu ID công khai là định danh chính mà ứng dụng muốn duy trì, thường đơn giản hơn khi dùng trực tiếp ID do ứng dụng cấp làm thuộc tính `@Id`.

## 7. ID công khai không thay thế kiểm soát truy cập

UUID hoặc ULID khó đoán hơn số tăng tuần tự, nhưng không phải thông tin xác thực. Bất kỳ client nào biết một ID cũng không mặc nhiên có quyền đọc hoặc sửa node tương ứng. API vẫn phải kiểm tra người dùng, tenant, vai trò và quyền truy cập trên từng thao tác.

Tránh đưa thông tin nhạy cảm vào ID, chẳng hạn email, số điện thoại, mã định danh cá nhân hoặc dữ liệu có thể suy ra từ cấu trúc ID. ID xuất hiện trong URL, log, lịch sử trình duyệt và thông điệp tích hợp; hãy xem nó là dữ liệu có thể bị lộ.

Không tái sử dụng ID công khai của một thực thể đã xóa cho một thực thể mới. Việc tái sử dụng có thể khiến một URL cũ hoặc thông điệp được gửi trễ trỏ nhầm sang dữ liệu khác. Nếu cần lưu vết lịch sử, hãy giữ tombstone hoặc bản ghi vòng đời theo quy tắc nghiệp vụ, đồng thời bảo đảm ID đã phát hành không được cấp lại.

## 8. Định danh relationship và trường version

Relationship cũng có ID nội bộ. Trong Spring Data Neo4j, `@RelationshipId` có thể được dùng trong lớp `@RelationshipProperties` để ánh xạ định danh relationship phục vụ persistence. ID này có cùng giới hạn: không dùng làm mã giao dịch, mã liên kết công khai hoặc định danh bền vững ở hệ thống ngoài.

Nếu một relationship đại diện cho thực thể nghiệp vụ độc lập, chẳng hạn hợp đồng, lần giao hàng hoặc thành viên đăng ký, hãy cân nhắc mô hình hóa nó thành một node có ID ứng dụng riêng. Khi đó, vòng đời, thuộc tính, quyền truy cập và liên kết của thực thể được quản lý rõ ràng.

Trường `@Version` trong Spring Data Neo4j giải quyết một vấn đề khác. Nó hỗ trợ kiểm soát phiên bản và phát hiện cập nhật đồng thời theo cơ chế optimistic locking. Version thay đổi khi entity được cập nhật; nó không phải ID và không nên dùng để nhận diện thực thể.

## 9. Quy trình đưa ID công khai vào hệ thống đang có

Khi bổ sung ID công khai cho dữ liệu đã tồn tại, cần triển khai theo thứ tự để tránh tạo ID trùng hoặc làm hỏng tham chiếu:

1. **Xác định phạm vi duy nhất.** Quyết định ID duy nhất toàn bộ loại node, theo tenant hay theo nguồn dữ liệu.
2. **Kiểm tra dữ liệu hiện tại.** Tìm node thiếu ID, giá trị trùng và các trường hợp dữ liệu không hợp lệ.
3. **Sinh và ghi bù ID.** Gán một ID duy nhất cho từng node còn thiếu; không suy ra ID từ thuộc tính có thể thay đổi.
4. **Tạo unique constraint.** Chỉ tạo sau khi dữ liệu đã được làm sạch để constraint không thất bại vì giá trị trùng.
5. **Cập nhật tầng ứng dụng.** Dùng ID công khai trong URL và thông điệp; chuyển các truy vấn tìm kiếm sang thuộc tính này.
6. **Kiểm tra tham chiếu và vận hành.** Xác minh dữ liệu cũ, log, job nền và consumer thông điệp đều hiểu cùng một định dạng ID.

Trong giai đoạn chuyển đổi, nếu phải hỗ trợ cả client cũ và mới, hãy quy định rõ thời điểm ngừng sử dụng ID cũ. Không âm thầm diễn giải một chuỗi ID công khai như ID nội bộ hoặc ngược lại.

## 10. Nguyên tắc lựa chọn

- Dùng ID nội bộ Neo4j cho mục đích persistence nội bộ khi chấp nhận được giới hạn ổn định của nó.
- Dùng ID do ứng dụng quản lý khi cần tham chiếu bền vững qua API, log nghiệp vụ, sự kiện hoặc hệ thống khác.
- Giữ ID công khai bất biến, không chứa dữ liệu nhạy cảm và không tái sử dụng sau khi xóa.
- Đặt unique constraint phù hợp với phạm vi duy nhất và kiểm tra ID được gán cho mọi node.
- Chọn UUID, ULID, mã nghiệp vụ hoặc ID nhà cung cấp theo nhu cầu thực tế; không chọn chỉ vì định dạng đang phổ biến.
- Luôn kiểm tra quyền truy cập độc lập với việc client có biết ID hay không.

Khi thiết kế định danh cho Spring Data Neo4j, hãy bắt đầu từ câu hỏi: “Giá trị này cần tồn tại ổn định trong phạm vi nào và ai chịu trách nhiệm duy trì nó?”. Nếu câu trả lời là Neo4j trong phạm vi lưu trữ nội bộ, ID nội bộ có thể đáp ứng. Nếu câu trả lời bao gồm API, hệ thống tích hợp hoặc vòng đời nghiệp vụ, hãy cấp một ID do ứng dụng quản lý và bảo vệ tính duy nhất của nó bằng ràng buộc dữ liệu.
