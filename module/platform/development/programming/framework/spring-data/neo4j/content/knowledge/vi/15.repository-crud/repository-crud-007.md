# Optional, collection rỗng và lỗi kết quả không duy nhất

## Mục tiêu bài học

Một phương thức repository có thể tìm thấy không có bản ghi, đúng một bản ghi hoặc nhiều bản ghi. Kiểu trả về của phương thức cần thể hiện đúng số lượng kết quả mà nghiệp vụ mong đợi. Với Spring Data Neo4j (SDN), `Optional<T>` phù hợp khi truy vấn có thể trả về không hoặc một entity; `List<T>` và các kiểu collection phù hợp khi truy vấn có thể trả về nhiều entity.

Nếu khai báo `Optional<T>` nhưng truy vấn trả về nhiều kết quả, Spring Data báo lỗi kích thước kết quả không hợp lệ thay vì tự chọn một entity. Bài học này giải thích cách chọn kiểu trả về, xử lý trường hợp không tìm thấy dữ liệu, phân biệt collection rỗng với Optional rỗng, nhận diện nguyên nhân trả về nhiều dòng và sửa truy vấn hoặc ràng buộc dữ liệu cho đúng.

## 1. Ba trường hợp về số lượng kết quả

Giả sử ứng dụng quản lý khách hàng và sản phẩm. Khi tìm khách hàng theo email, nghiệp vụ thường kỳ vọng tối đa một khách hàng. Khi tìm khách hàng theo trạng thái, truy vấn có thể trả về nhiều người.

| Số lượng kết quả | Kiểu trả về phù hợp | Ý nghĩa |
|---|---|---|
| 0 hoặc 1 entity | `Optional<Customer>` | Có thể không tìm thấy; nếu có thì có một entity |
| 0 đến nhiều entity | `List<Customer>` hoặc collection phù hợp | Không tìm thấy thì collection rỗng |
| Bắt buộc phải có đúng một entity | `Customer` kèm xử lý trường hợp không tồn tại | Không có kết quả hoặc có nhiều kết quả đều cần được xử lý theo hợp đồng |

Với repository kế thừa `Neo4jRepository`, phương thức `findById(id)` đã trả về `Optional<T>`. Đây là cách biểu diễn chuẩn cho thao tác tìm theo ID: node có thể tồn tại hoặc không tồn tại.

Không nên chọn kiểu trả về chỉ dựa trên việc dữ liệu hiện tại tình cờ có một kết quả. Hãy chọn theo quy tắc nghiệp vụ và bảo đảm dữ liệu được ràng buộc phù hợp.

## 2. Dùng Optional khi truy vấn có tối đa một kết quả

Ví dụ, mỗi khách hàng có email duy nhất. Repository có thể khai báo:

```java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);
}
```

Khi gọi phương thức, Spring Data trả về:

- `Optional.of(customer)` nếu tìm thấy đúng một khách hàng.
- `Optional.empty()` nếu không tìm thấy khách hàng.
- Ném lỗi kích thước kết quả nếu truy vấn trả về nhiều hơn một khách hàng.

Có thể xử lý kết quả bằng các API của `Optional`:

```java
Optional<Customer> result = customerRepository.findByEmail(email);

if (result.isPresent()) {
    Customer customer = result.get();
    // Xử lý khách hàng đã tìm thấy.
}
```

Trong code nghiệp vụ, có thể dùng `orElseThrow` để thể hiện rõ trường hợp bắt buộc phải có dữ liệu:

```java
Customer customer = customerRepository.findByEmail(email)
        .orElseThrow(() -> new CustomerNotFoundException(email));
```

Nếu không tìm thấy khách hàng là tình huống bình thường, hãy giữ kết quả ở dạng `Optional` và xử lý nhánh đó theo nghiệp vụ. Không gọi `get()` khi chưa kiểm tra hoặc chưa xác định được cách xử lý trường hợp rỗng, vì điều đó có thể dẫn đến `NoSuchElementException`.

`Optional` biểu diễn sự có mặt hoặc vắng mặt của một giá trị. Nó không có nghĩa rằng Spring Data sẽ tự chọn một kết quả nếu database trả về nhiều entity.

## 3. Dùng collection khi truy vấn có thể trả về nhiều entity

Một truy vấn tìm khách hàng theo trạng thái có thể trả về không, một hoặc nhiều khách hàng. Khai báo kiểu collection:

```java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    List<Customer> findAllByStatus(String status);
}
```

Nếu không có khách hàng phù hợp, phương thức trả về danh sách rỗng. Nếu có nhiều khách hàng, danh sách chứa các entity tương ứng.

```java
List<Customer> activeCustomers =
        customerRepository.findAllByStatus("ACTIVE");

if (activeCustomers.isEmpty()) {
    // Chưa có khách hàng ACTIVE.
} else {
    activeCustomers.forEach(this::processCustomer);
}
```

Với kiểu trả về collection, không cần bọc thêm bằng `Optional`. Một danh sách rỗng đã thể hiện rằng truy vấn không tìm thấy phần tử nào:

```java
// Nên dùng
List<Customer> findAllByStatus(String status);

// Tránh dùng nếu chỉ để biểu diễn trường hợp không có phần tử
Optional<List<Customer>> findAllByStatus(String status);
```

`Optional<List<T>>` thường không thêm ý nghĩa hữu ích: truy vấn collection không có kết quả đã có thể trả về collection rỗng. Việc bọc thêm Optional tạo hai trạng thái rỗng khác nhau (Optional rỗng và List rỗng) mà tầng gọi phải xử lý, trong khi nghiệp vụ chỉ cần biết danh sách có phần tử hay không.

Nếu truy vấn có thể trả về nhiều kết quả, đừng khai báo `Optional<T>` chỉ vì giao diện hiện tại chỉ hiển thị một phần tử. Hãy dùng collection hoặc thay đổi truy vấn theo quy tắc chọn một kết quả được xác định rõ.

## 4. Khi nào Spring Data báo lỗi kết quả không duy nhất?

Giả sử repository khai báo:

```java
Optional<Customer> findByCity(String city);
```

Nhưng trong dữ liệu có nhiều khách hàng cùng sống ở một thành phố. Truy vấn trả về nhiều entity, trong khi kiểu trả về chỉ cho phép không hoặc một kết quả. Spring Data sẽ ném `IncorrectResultSizeDataAccessException`.

Lỗi này cho biết hợp đồng của phương thức không khớp với số lượng dòng mà truy vấn trả về. Nó không có nghĩa Neo4j không thể tìm dữ liệu, cũng không phải lỗi chuyển đổi thuộc tính.

Ví dụ tình huống:

| Email | City | Customer |
|---|---|---|
| an@example.com | Hà Nội | An |
| binh@example.com | Hà Nội | Bình |
| chi@example.com | Đà Nẵng | Chi |

Với truy vấn theo `city = "Hà Nội"`, kết quả đúng là hai khách hàng. Kiểu trả về phù hợp là `List<Customer>`, không phải `Optional<Customer>`.

Nếu nghiệp vụ thực sự yêu cầu một khách hàng theo email, hãy bảo đảm email duy nhất và dùng phương thức tìm theo email. Không đổi kiểu trả về thành Optional cho một thuộc tính có thể trùng chỉ để làm API ngắn hơn.

## 5. Bảo đảm tính duy nhất ở tầng dữ liệu

Một phương thức repository trả về `Optional<Customer>` theo email chỉ đúng khi dữ liệu có tối đa một khách hàng cho email đó. Có thể tạo uniqueness constraint trong Neo4j:

```cypher
CREATE CONSTRAINT customer_email_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.email IS UNIQUE;
```

Constraint giúp Neo4j từ chối việc tạo hoặc cập nhật node vi phạm tính duy nhất. Đây là lớp bảo vệ dữ liệu ngay cả khi nhiều ứng dụng hoặc request đồng thời ghi vào database.

Trong entity, email có thể được ánh xạ như một property thông thường:

```java
@Node("Customer")
public class Customer {

    @Id
    private String id;

    private String email;

    private String name;

    // Constructor, getter và setter được lược bỏ.
}
```

Cần lưu ý rằng uniqueness constraint áp dụng cho giá trị property theo phạm vi label và property được khai báo. Nếu email có thể vắng mặt, hãy xác định rõ chính sách nghiệp vụ cho giá trị null/rỗng; constraint duy nhất không tự động thay thế kiểm tra dữ liệu đầu vào.

Trước khi thêm constraint vào database đã có dữ liệu, cần kiểm tra và xử lý các giá trị trùng. Nếu dữ liệu hiện tại vi phạm, Neo4j sẽ không tạo được constraint.

## 6. Nhiều dòng có thể đến từ nhiều relationship

Không phải lúc nào nhiều record cũng có nghĩa có nhiều node khác nhau. Một custom Cypher query có thể khớp nhiều relationship hoặc nhiều path dẫn đến cùng node.

Ví dụ, một khách hàng có thể có nhiều relationship tham gia nhóm. Truy vấn:

```cypher
MATCH (c:Customer)-[:MEMBER_OF]->(g:Group)
WHERE g.name = $groupName
RETURN c
```

Nếu cùng một khách hàng có nhiều relationship phù hợp, Cypher có thể trả node `c` ở nhiều dòng. Nếu repository mong đợi một khách hàng duy nhất, cần xác định liệu đó là các node khác nhau hay chỉ là cùng node được tìm thấy qua nhiều đường khớp.

Nếu mục tiêu là lấy các khách hàng duy nhất, có thể khử trùng node trong Cypher:

```cypher
MATCH (c:Customer)-[:MEMBER_OF]->(g:Group)
WHERE g.name = $groupName
RETURN DISTINCT c
```

Và repository có thể khai báo:

```java
@Query("MATCH (c:Customer)-[:MEMBER_OF]->(g:Group) " +
       "WHERE g.name = $groupName " +
       "RETURN DISTINCT c")
List<Customer> findDistinctCustomersByGroupName(
        @Param("groupName") String groupName);
```

`DISTINCT c` loại bỏ những dòng lặp cùng node khách hàng. Nhưng nếu có nhiều khách hàng khác nhau cùng thỏa điều kiện, kết quả vẫn có nhiều phần tử. Khi đó, nếu dùng `Optional<Customer>`, lỗi kích thước kết quả vẫn đúng và cần được giải quyết bằng quy tắc nghiệp vụ hoặc kiểu trả về phù hợp.

Khi cần giữ thông tin của từng relationship, không nên chỉ trả `DISTINCT c` rồi bỏ mất dữ liệu cạnh. Hãy trả về và gom riêng node, relationship hoặc projection theo mục đích sử dụng.

## 7. Nếu nghiệp vụ chỉ cần một kết quả trong nhiều kết quả

Đôi khi nghiệp vụ có quy tắc chọn một bản ghi trong nhiều bản ghi, ví dụ đơn hàng mới nhất của khách hàng. Khi đó, hãy diễn đạt tiêu chí chọn trong truy vấn thay vì dựa vào thứ tự tình cờ của database.

```cypher
MATCH (c:Customer {id: $customerId})-[:PLACED]->(o:Order)
RETURN o
ORDER BY o.createdAt DESC, o.id DESC
LIMIT 1
```

Repository có thể trả về một `Optional<Order>` vì truy vấn đã giới hạn tối đa một dòng:

```java
@Query("MATCH (c:Customer {id: $customerId})-[:PLACED]->(o:Order) " +
       "RETURN o " +
       "ORDER BY o.createdAt DESC, o.id DESC " +
       "LIMIT 1")
Optional<Order> findLatestOrder(
        @Param("customerId") String customerId);
```

Thứ tự phụ thứ hai giúp kết quả ổn định khi nhiều đơn hàng có cùng thời điểm. Chọn một bản ghi bằng `ORDER BY` và `LIMIT` chỉ phù hợp khi nghiệp vụ thực sự chấp nhận quy tắc đó. Không dùng `LIMIT 1` để che dữ liệu trùng ở trường cần duy nhất như email; trường hợp đó cần ràng buộc dữ liệu và xử lý vi phạm.

## 8. Xử lý kết quả trong service

Service nên giữ rõ ý nghĩa của từng kiểu trả về. Ví dụ:

```java
@Service
public class CustomerService {

    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    public Customer getRequiredCustomer(String email) {
        return customerRepository.findByEmail(email)
                .orElseThrow(() -> new CustomerNotFoundException(email));
    }

    public List<Customer> getCustomersByStatus(String status) {
        return customerRepository.findAllByStatus(status);
    }
}
```

Phương thức đầu tiên thể hiện rằng email được kỳ vọng duy nhất và khách hàng phải tồn tại. Phương thức thứ hai thể hiện rằng truy vấn có thể trả về nhiều khách hàng và danh sách rỗng là kết quả hợp lệ.

Không nên bắt `IncorrectResultSizeDataAccessException` rồi trả về phần tử đầu tiên nếu chưa có quy tắc chọn rõ ràng. Cách đó che giấu lỗi chất lượng dữ liệu hoặc lỗi thiết kế truy vấn. Hãy sửa nguyên nhân ở constraint, query hoặc kiểu trả về.

## 9. Kiểm thử ba trường hợp cardinality

Khi kiểm thử repository, cần tạo dữ liệu bao phủ các trường hợp 0, 1 và nhiều kết quả.

| Trường hợp | Dữ liệu kiểm thử | Kỳ vọng |
|---|---|---|
| Không có kết quả với Optional | Email không tồn tại | `Optional.empty()` |
| Có đúng một kết quả với Optional | Một khách hàng có email đó | `Optional.of(customer)` |
| Có nhiều kết quả với collection | Nhiều khách hàng cùng trạng thái | Danh sách có đủ các khách hàng |
| Không có kết quả với collection | Không có khách hàng ở trạng thái đó | Danh sách rỗng |
| Nhiều kết quả với Optional | Nhiều khách hàng cùng giá trị được truy vấn | `IncorrectResultSizeDataAccessException` |
| Nhiều path đến cùng node | Một khách hàng khớp nhiều relationship | `DISTINCT` trả node duy nhất nếu đó là mục tiêu |

Ví dụ unit hoặc integration test với AssertJ:

```java
@Test
void shouldReturnEmptyOptionalWhenEmailDoesNotExist() {
    assertThat(customerRepository.findByEmail("missing@example.com"))
            .isEmpty();
}

@Test
void shouldReturnEmptyListWhenNoCustomerHasStatus() {
    assertThat(customerRepository.findAllByStatus("SUSPENDED"))
            .isEmpty();
}
```

Kiểm thử lỗi nhiều kết quả nên dùng dữ liệu cho phép nhiều node có cùng giá trị được tìm kiếm. Nếu đã bật uniqueness constraint cho email, database sẽ từ chối dữ liệu trùng trước khi repository query được gọi; hãy kiểm tra constraint ở một test riêng và dùng một thuộc tính không duy nhất để kiểm thử lỗi cardinality.

Ví dụ kiểm thử ngoại lệ:

```java
@Test
void shouldFailWhenOptionalQueryReturnsMultipleCustomers() {
    assertThatThrownBy(() -> customerRepository.findByCity("Hà Nội"))
            .isInstanceOf(IncorrectResultSizeDataAccessException.class);
}
```

Kiểm thử này giả định `findByCity` được khai báo trả về `Optional<Customer>` và dữ liệu test có ít nhất hai khách hàng ở Hà Nội. Nếu phương thức được khai báo trả về `List<Customer>`, kết quả nhiều dòng là hợp lệ và không nên kỳ vọng ngoại lệ này.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `Optional<T>` cho truy vấn có thể trả nhiều node | Hợp đồng kết quả chỉ cho phép tối đa một entity | Dùng collection hoặc xác định quy tắc chọn một kết quả |
| Dùng `Optional<List<T>>` cho truy vấn collection | Tạo hai cách biểu diễn không có dữ liệu | Trả `List<T>` và dùng danh sách rỗng |
| Gọi `Optional.get()` khi chưa kiểm tra | Có thể ném `NoSuchElementException` | Dùng `orElseThrow`, `ifPresent` hoặc kiểm tra rỗng |
| Cho rằng Optional tự loại bỏ bản ghi trùng | Optional không khử trùng kết quả query | Dùng `DISTINCT` nếu trùng cùng node hoặc sửa điều kiện truy vấn |
| Dùng Optional cho thuộc tính không duy nhất | Nhiều node khác nhau cùng thỏa điều kiện | Dùng collection hoặc bổ sung uniqueness constraint nếu nghiệp vụ yêu cầu duy nhất |
| Dùng `LIMIT 1` để che lỗi dữ liệu | Kết quả được chọn có thể không ổn định và che vi phạm duy nhất | Chỉ giới hạn khi có tiêu chí chọn rõ ràng |
| Chỉ kiểm thử trường hợp tìm thấy một bản ghi | Không phát hiện hành vi rỗng hoặc nhiều kết quả | Kiểm thử đủ 0, 1 và nhiều kết quả |

## 11. Tự kiểm tra

1. Khi nào nên khai báo phương thức repository trả về `Optional<Customer>`?
2. Nếu truy vấn collection không tìm thấy dữ liệu, Spring Data trả về giá trị nào?
3. Vì sao `Optional<List<Customer>>` thường không cần thiết?
4. `IncorrectResultSizeDataAccessException` xuất hiện trong trường hợp nào?
5. Nếu Cypher trả cùng một node qua nhiều relationship, có thể dùng từ khóa nào để khử trùng node?
6. Vì sao `DISTINCT` không bảo đảm truy vấn Optional chỉ có một kết quả khi nhiều node khác nhau cùng thỏa điều kiện?
7. Khi nào nên dùng `ORDER BY` và `LIMIT 1`?
8. Vì sao uniqueness constraint vẫn cần thiết dù repository đã trả về Optional?

Hãy tạo hai repository method: một phương thức tìm khách hàng theo email trả về `Optional<Customer>`, và một phương thức tìm theo trạng thái trả về `List<Customer>`. Kiểm thử trường hợp không có dữ liệu, có một kết quả và nhiều kết quả. Sau đó thử khai báo một phương thức Optional theo thành phố có nhiều khách hàng để quan sát lỗi kích thước kết quả, rồi sửa bằng collection hoặc quy tắc chọn một kết quả rõ ràng.

## Tài liệu tham khảo

- [Spring Data Commons — Repository query return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html)
- [Spring Data Neo4j — Repository support](https://docs.spring.io/spring-data/neo4j/reference/repositories.html)
- [Neo4j — Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
