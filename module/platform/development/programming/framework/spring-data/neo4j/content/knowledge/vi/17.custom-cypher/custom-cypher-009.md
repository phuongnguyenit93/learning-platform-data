# Đánh dấu count, exists, delete và chọn kiểu kết quả phù hợp

## Mục tiêu bài học

Khi viết Cypher tùy chỉnh trong repository Spring Data Neo4j (SDN), phương thức không phải lúc nào cũng trả về một danh sách node. Có lúc ứng dụng chỉ cần biết có bao nhiêu node thỏa điều kiện, có tồn tại kết quả hay không, hoặc cần xóa node và relationship phù hợp. Kiểu kết quả của phương thức phải thể hiện đúng mục đích truy vấn để tầng service xử lý rõ ràng.

SDN hỗ trợ các cờ `count`, `exists` và `delete` trên `@Query`. Bài học này giải thích cách dùng chúng, cách chọn `long`, `boolean`, `void`, entity, collection hoặc projection, và cách phân biệt cờ `count` với thuộc tính `countQuery` dùng cho phân trang. Bạn cũng sẽ học cách kiểm soát truy vấn xóa và transaction để tránh tác động nhầm lên graph.

## 1. Chọn kiểu kết quả trước khi viết truy vấn

Trước khi viết Cypher, hãy xác định repository method cần trả lời câu hỏi nào:

| Nhu cầu | Kết quả mong đợi | Kiểu Java thường dùng |
|---|---|---|
| Đọc một entity có thể không tồn tại | Không hoặc một entity | `Optional<Customer>` |
| Đọc nhiều entity | Danh sách có thể rỗng | `List<Customer>` |
| Đếm số entity phù hợp | Một số đếm | `long` hoặc `Long` |
| Kiểm tra có ít nhất một kết quả | Đúng hoặc sai | `boolean` hoặc `Boolean` |
| Xóa dữ liệu, không cần thông tin sau xóa | Không có giá trị trả về | `void` |
| Trả dữ liệu trình bày hoặc báo cáo | Một tập trường được chọn | Projection hoặc DTO |
| Trả danh sách có phân trang và tổng số phần tử | Trang kết quả cùng metadata | `Page<Customer>` |

Không nên dùng `List<Customer>` chỉ để đếm số lượng rồi gọi `size()`. Cách đó buộc ứng dụng tải toàn bộ kết quả về bộ nhớ. Tương tự, không nên tải entity chỉ để kiểm tra tồn tại nếu database có thể trả lời câu hỏi bằng một phép kiểm tra existence.

Ví dụ dưới đây dùng node `Customer` có các property `id`, `email`, `status` và `name`. Repository được khai báo như sau:

```java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {
    // Các phương thức truy vấn được khai báo ở những phần tiếp theo.
}
```

Các ví dụ dùng tham số Cypher có tên như `$status` và liên kết chúng với tham số Java bằng `@Param`. Hãy truyền giá trị đầu vào qua tham số thay vì ghép trực tiếp chuỗi vào câu lệnh.

## 2. Đánh dấu truy vấn đếm bằng count

Khi chỉ cần số lượng node phù hợp, khai báo `@Query` với `count = true` và dùng kiểu số làm kết quả:

```java
@Query(
    value = "MATCH (c:Customer) " +
            "WHERE c.status = $status " +
            "RETURN count(c)",
    count = true
)
long countCustomersByStatus(@Param("status") String status);
```

Truy vấn Cypher trả về một giá trị đếm. Cờ `count = true` đánh dấu phương thức là truy vấn count projection để SDN xử lý kết quả theo mục đích đếm. Kiểu `long` phù hợp cho số lượng có thể lớn; có thể dùng `Long` nếu cần biểu diễn giá trị có thể null theo hợp đồng của ứng dụng.

Nếu một node có thể xuất hiện nhiều lần do truy vấn đi qua nhiều relationship, hãy đếm node duy nhất:

```java
@Query(
    value = "MATCH (c:Customer)-[:MEMBER_OF]->(g:Group) " +
            "WHERE g.name = $groupName " +
            "RETURN count(DISTINCT c)",
    count = true
)
long countDistinctCustomersInGroup(
        @Param("groupName") String groupName);
```

`count(c)` đếm số lần biểu thức `c` xuất hiện trong tập kết quả. Nếu cùng một khách hàng khớp nhiều đường đi, số đếm có thể lớn hơn số khách hàng duy nhất. `count(DISTINCT c)` phù hợp khi nghiệp vụ hỏi số node khách hàng khác nhau.

### Derived count query và custom count query

Nếu điều kiện có thể diễn đạt bằng tên phương thức, derived query thường ngắn gọn hơn:

```java
long countByStatus(String status);
```

Dùng `@Query(count = true)` khi cần tự viết điều kiện Cypher, ví dụ có traversal graph hoặc quy tắc lọc đặc thù. Hai cách có cùng mục tiêu nhưng khác cách mô tả truy vấn.

Không nên tải danh sách rồi tự đếm:

```java
// Không phù hợp nếu chỉ cần số lượng:
long count = customerRepository.findByStatus("ACTIVE").size();
```

Phương thức count để database tính toán và chỉ trả về số đếm, giảm dữ liệu truyền về ứng dụng.

## 3. Đánh dấu truy vấn kiểm tra tồn tại bằng exists

Khi câu hỏi nghiệp vụ chỉ là “có ít nhất một khách hàng với email này không?”, dùng `exists = true` và kiểu trả về boolean:

```java
@Query(
    value = "MATCH (c:Customer {email: $email}) " +
            "RETURN c",
    exists = true
)
boolean existsCustomerByEmail(@Param("email") String email);
```

Cờ `exists = true` yêu cầu SDN xử lý truy vấn như một existence projection. Kết quả thể hiện có hay không có kết quả phù hợp, thay vì hydrate toàn bộ entity khách hàng.

Có thể dùng derived query khi điều kiện đơn giản:

```java
boolean existsByEmail(String email);
```

Dùng custom query khi việc xác định tồn tại cần duyệt graph:

```java
@Query(
    value = "MATCH (c:Customer)-[:MEMBER_OF]->(g:Group) " +
            "WHERE c.id = $customerId AND g.id = $groupId " +
            "RETURN c",
    exists = true
)
boolean isCustomerMemberOfGroup(
        @Param("customerId") String customerId,
        @Param("groupId") String groupId);
```

Một phép kiểm tra tồn tại thường không cần trả về entity. Trả về `boolean` giúp API thể hiện đúng ý nghĩa và tránh tạo object graph không cần thiết.

Không nên viết một phương thức trả về `Optional<Customer>` rồi chỉ gọi `isPresent()` nếu ứng dụng không cần dữ liệu khách hàng. Nếu cần cả kiểm tra và thông tin entity, hãy đọc entity bằng `Optional<Customer>`; nếu chỉ cần câu trả lời đúng/sai, dùng existence query.

## 4. Đánh dấu truy vấn xóa bằng delete

Với custom Cypher dùng để xóa node hoặc relationship, đặt `delete = true` trên `@Query`. Ví dụ xóa một khách hàng theo ID cùng toàn bộ relationship gắn với node đó:

```java
@Query(
    value = "MATCH (c:Customer {id: $customerId}) " +
            "DETACH DELETE c",
    delete = true
)
void deleteCustomerAndRelationships(
        @Param("customerId") String customerId);
```

Câu lệnh Cypher chịu trách nhiệm xác định dữ liệu cần xóa. Cờ `delete = true` đánh dấu phương thức là delete query để SDN xử lý theo loại thao tác này. Nếu không cần dữ liệu trả về sau xóa, `void` là kiểu kết quả rõ ràng.

### DELETE và DETACH DELETE khác nhau

Neo4j không cho xóa node còn relationship gắn với nó bằng `DELETE` thông thường. Có hai tình huống:

- `DELETE r`: xóa một relationship được khớp, giữ nguyên hai node ở hai đầu.
- `DETACH DELETE c`: xóa node `c` cùng tất cả relationship gắn trực tiếp với node đó.

Ví dụ chỉ xóa liên kết theo dõi giữa một khách hàng và một sản phẩm:

```java
@Query(
    value = "MATCH (c:Customer {id: $customerId})" +
            "-[r:FOLLOWS]->(p:Product {id: $productId}) " +
            "DELETE r",
    delete = true
)
void removeFollowRelationship(
        @Param("customerId") String customerId,
        @Param("productId") String productId);
```

Hai node `Customer` và `Product` vẫn tồn tại; chỉ cạnh `FOLLOWS` được xóa.

Ngược lại, xóa node bằng `DETACH DELETE` sẽ xóa mọi relationship gắn với node đó, kể cả relationship không được nêu trong pattern `MATCH`. Các node lân cận không tự động bị xóa. Ví dụ, khi xóa một khách hàng, các node `Order` vẫn tồn tại nếu câu lệnh chỉ xóa khách hàng và các relationship nối đến đơn hàng.

Hãy chọn đúng phạm vi xóa theo quy tắc nghiệp vụ. Nếu một node được nhiều quy trình hoặc aggregate khác tham chiếu, việc xóa detach có thể làm mất những liên kết mà các quy trình đó cần.

### Kiểm soát phạm vi xóa

Trước khi đưa delete query vào repository, hãy kiểm tra pattern và điều kiện:

```cypher
MATCH (c:Customer)
WHERE c.status = $status
RETURN c.id, c.email
```

Chạy truy vấn đọc để xác nhận tập node khớp, rồi mới thay bằng câu lệnh xóa có cùng điều kiện:

```cypher
MATCH (c:Customer)
WHERE c.status = $status
DETACH DELETE c
```

Tránh viết truy vấn xóa thiếu điều kiện khi nghiệp vụ chỉ định xóa một nhóm dữ liệu. Một câu lệnh `MATCH (n) DETACH DELETE n` có thể xóa toàn bộ graph và chỉ phù hợp cho môi trường test hoặc thao tác quản trị được kiểm soát.

Nếu cần số lượng node và relationship đã xóa để ghi audit hoặc trả báo cáo, đừng mặc định rằng `void` hoặc một entity return type sẽ cung cấp số đếm. Hãy thiết kế một custom repository fragment dùng `Neo4jClient` hoặc Neo4j Java Driver để đọc kết quả/counters của transaction và ánh xạ thành một kiểu số cụ thể. Khi dùng Driver trực tiếp, cần quản lý transaction phù hợp; thao tác Driver tự tạo session không tự tham gia Spring transaction.

## 5. Phân biệt count với countQuery

Hai cấu hình này phục vụ hai mục đích khác nhau:

| Cấu hình | Mục đích | Kiểu phương thức thường dùng |
|---|---|---|
| `@Query(count = true)` | Thực thi custom query như một phép đếm độc lập | `long` hoặc `Long` |
| `@Query(countQuery = "...")` | Cung cấp câu Cypher đếm tổng số phần tử cho custom finder trả về `Page<T>` | `Page<T>` |

Ví dụ, một trang khách hàng cần có cả danh sách hiện tại và tổng số khách hàng phù hợp. Custom query phải xử lý phân trang bằng `$skip` và `$limit`, đồng thời cung cấp count query riêng:

```java
@Query(
    value = "MATCH (c:Customer) " +
            "WHERE c.status = $status " +
            "RETURN c " +
            "ORDER BY c.name ASC, c.id ASC " +
            "SKIP $skip LIMIT $limit",
    countQuery = "MATCH (c:Customer) " +
                 "WHERE c.status = $status " +
                 "RETURN count(c)"
)
Page<Customer> findCustomerPageByStatus(
        @Param("status") String status,
        Pageable pageable);
```

`Page<Customer>` chứa dữ liệu trang hiện tại và metadata như tổng phần tử, tổng số trang. SDN cần chạy count query để biết tổng số phần tử chính xác. Nếu query duyệt qua relationship có thể làm một node xuất hiện nhiều lần, cả truy vấn lấy dữ liệu và count query phải xử lý trùng theo đúng ý nghĩa nghiệp vụ, chẳng hạn dùng `DISTINCT` hoặc gom relationship phù hợp.

Nếu chỉ cần biết có trang tiếp theo hay không, `Slice<Customer>` thường đủ dùng. Slice không cần biết tổng số phần tử hoặc tổng số trang, vì vậy không cần count query riêng. Với custom query, vẫn phải có thứ tự ổn định và các placeholder `$skip`, `$limit` để SDN áp dụng phân trang:

```java
@Query(
    "MATCH (c:Customer) " +
    "WHERE c.status = $status " +
    "RETURN c " +
    "ORDER BY c.name ASC, c.id ASC " +
    "SKIP $skip LIMIT $limit"
)
Slice<Customer> findCustomerSliceByStatus(
        @Param("status") String status,
        Pageable pageable);
```

Với custom query, mệnh đề `ORDER BY` cần được viết ngay trong Cypher; SDN không lấy thông tin sắp xếp từ `Pageable` để chèn vào câu lệnh này. Hãy truyền một `Pageable` không kèm sort và dùng thứ tự ổn định trong query, chẳng hạn thêm ID làm tiêu chí phụ khi tên có thể trùng. Với derived finder trả về `Page<T>` hoặc `Slice<T>`, Spring Data có thể tạo truy vấn phân trang từ tên phương thức. Yêu cầu tự khai báo `$skip`, `$limit` và `countQuery` ở trên áp dụng cho custom query.

## 6. Chọn kiểu kết quả cho custom Cypher

Không phải custom query nào cũng cần entity. Chọn kiểu trả về theo dữ liệu mà tầng gọi thực sự sử dụng:

### Entity và Optional

Nếu query trả về node được ánh xạ thành entity:

```java
@Query("MATCH (c:Customer {id: $id}) RETURN c")
Optional<Customer> findCustomerGraphById(@Param("id") String id);
```

Dùng `Optional<Customer>` khi node có thể không tồn tại. Nếu nghiệp vụ bảo đảm có đúng một node, có thể dùng kiểu entity trực tiếp theo hợp đồng và cách xử lý lỗi của ứng dụng.

### Collection

Nếu truy vấn trả về nhiều node:

```java
@Query("MATCH (c:Customer) WHERE c.status = $status RETURN c")
List<Customer> findCustomersByStatus(
        @Param("status") String status);
```

Danh sách rỗng thể hiện không có khách hàng phù hợp. Không cần bọc `List<Customer>` trong `Optional` chỉ để biểu diễn trường hợp không có phần tử.

### Projection hoặc DTO

Nếu màn hình chỉ cần một số property, hãy trả về projection thay vì hydrate toàn bộ entity:

```java
public interface CustomerSummary {
    String getName();
    String getEmail();
}
```

```java
@Query("MATCH (c:Customer) " +
       "WHERE c.status = $status " +
       "RETURN c.name AS name, c.email AS email")
List<CustomerSummary> findCustomerSummaries(
        @Param("status") String status);
```

Tên alias trong `RETURN` cần khớp với property/getter mà projection cung cấp. Cách này phù hợp với báo cáo hoặc API đọc chỉ cần một góc nhìn dữ liệu.

### Giá trị vô hướng

Khi Cypher trả một scalar như số, chuỗi hoặc boolean, kiểu Java phải tương thích với giá trị đó. Ví dụ, query `RETURN count(c)` cần kiểu số; query trả `c.email` cần kiểu chuỗi. Không khai báo `Customer` nếu câu lệnh chỉ trả một scalar.

| Cypher trả về | Kiểu Java thường dùng |
|---|---|
| Node `c` | `Customer` hoặc `List<Customer>` |
| Một giá trị đếm | `long` hoặc `Long` |
| Một giá trị đúng/sai | `boolean` hoặc `Boolean` |
| Một chuỗi `c.email` | `String` |
| Các cột được alias | Projection hoặc DTO tương ứng |
| Kết quả không cần đọc lại | `void` cho thao tác xóa |

Nếu query trả nhiều dòng nhưng method khai báo một giá trị đơn, hãy kiểm tra cardinality hoặc thêm quy tắc chọn kết quả rõ ràng. Đừng dựa vào thứ tự ngẫu nhiên của graph để chọn một record.

## 7. Transaction và custom query

Custom query có thể đọc hoặc ghi dữ liệu tùy câu Cypher. SDN không thể luôn suy luận ý định của mọi query tùy chỉnh, đặc biệt khi query gọi procedure hoặc chứa logic động. Vì vậy, custom query thường được xem là có khả năng ghi theo mặc định.

Nếu một phương thức chỉ đọc, có thể đánh dấu ranh giới transaction read-only:

```java
@Transactional(readOnly = true)
public List<CustomerSummary> getActiveCustomerSummaries() {
    return customerRepository.findCustomerSummaries("ACTIVE");
}
```

Với một nghiệp vụ gồm nhiều thao tác cần thành công hoặc rollback cùng nhau, đặt `@Transactional` tại service method bao quanh các lời gọi repository:

```java
@Service
public class CustomerMaintenanceService {

    private final CustomerRepository customerRepository;

    public CustomerMaintenanceService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void removeInactiveCustomer(String customerId) {
        // Kiểm tra quy tắc nghiệp vụ và quyền xóa.
        customerRepository.deleteCustomerAndRelationships(customerId);
        // Các thao tác ghi khác của cùng nghiệp vụ có thể đặt ở đây.
    }
}
```

Không dùng `readOnly = true` cho transaction có thao tác xóa hoặc cập nhật. Nếu service gọi nhiều repository trong cùng nghiệp vụ, transaction ở tầng service giúp những thao tác đó tham gia cùng ranh giới nguyên tử của Spring.

Với thao tác đọc trên Neo4j cluster, read-only transaction còn giúp hệ thống định tuyến truy vấn đọc đến thành phần phù hợp của cluster. Hãy đánh dấu đúng các luồng chỉ đọc và không đánh dấu nhầm thao tác có `MERGE`, `SET`, `CREATE` hoặc `DELETE`.

## 8. Kiểm thử count, exists và delete

Kiểm thử repository nên bao phủ cả kết quả bình thường và trường hợp biên.

| Phương thức | Dữ liệu kiểm thử | Kỳ vọng |
|---|---|---|
| Count theo status | 3 khách hàng ACTIVE | Trả về `3L` |
| Count distinct qua relationship | Một khách hàng khớp nhiều đường đi | Đếm một node nếu dùng `DISTINCT` |
| Exists theo email | Email có node phù hợp | `true` |
| Exists theo email | Email không có node | `false` |
| Delete relationship | Hai node và một cạnh nối chúng | Cạnh bị xóa, hai node còn lại |
| Detach delete node | Một node có nhiều cạnh | Node và các cạnh gắn trực tiếp bị xóa |
| Page custom query | Nhiều node hơn kích thước trang | Đúng nội dung trang và tổng số phần tử |
| Slice custom query | Có trang tiếp theo | Trả về metadata `hasNext` chính xác |

Ví dụ kiểm thử count và exists:

```java
@DataNeo4jTest
class CustomerQueryProjectionTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldCountAndCheckCustomerExistence() {
        // Tạo và lưu một số Customer với status khác nhau.
        // Xác nhận countCustomersByStatus("ACTIVE") trả số mong đợi.
        // Xác nhận existsCustomerByEmail(email) trả true với email có thật.
        // Xác nhận existsCustomerByEmail("missing@example.com") trả false.
    }
}
```

Ví dụ kiểm thử xóa cần đọc lại graph bằng query độc lập sau khi gọi phương thức delete. Không chỉ xác nhận method không ném exception; cần kiểm tra node hoặc relationship thực sự đã bị xóa và các node lân cận còn lại đúng như thiết kế.

Với delete query, hãy có test cho trường hợp ID không tồn tại và trường hợp node có nhiều loại relationship. Những test này giúp phát hiện truy vấn xóa rộng hơn dự kiến.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `List<Customer>` chỉ để đếm | Tải toàn bộ entity về ứng dụng | Dùng count query trả kiểu số |
| Dùng entity để kiểm tra tồn tại | Nạp dữ liệu không cần thiết | Dùng `exists = true` hoặc derived `existsBy...` |
| Đánh dấu `count = true` nhưng return type là entity | Hợp đồng kiểu kết quả không khớp mục tiêu count | Dùng kiểu số và Cypher trả giá trị đếm |
| Dùng `count(c)` khi node có thể lặp qua nhiều relationship | Đếm record thay vì node duy nhất | Dùng `count(DISTINCT c)` |
| Nhầm `countQuery` với `count = true` | Dùng truy vấn đếm độc lập như projection method | Dùng `countQuery` cho tổng số phần tử của Page |
| Dùng `DELETE c` khi node còn relationship | Neo4j từ chối xóa node có cạnh gắn vào | Dùng `DETACH DELETE` nếu nghiệp vụ muốn xóa các cạnh đó |
| Dùng `DETACH DELETE` chỉ để bỏ một cạnh | Xóa cả các relationship khác của node | Match cạnh và `DELETE r` |
| Xóa node mà không giới hạn pattern | Tác động đến nhiều dữ liệu hơn dự kiến | Xác định điều kiện và kiểm tra tập khớp trước |
| Dùng Page cho custom query nhưng thiếu skip/limit/countQuery | Trang hoặc tổng số trang không chính xác | Khai báo `$skip`, `$limit` và countQuery |
| Đánh dấu transaction đọc cho query có ghi | Giao dịch không phù hợp với thao tác thực tế | Dùng transaction ghi hoặc để Spring quản lý theo service |

## 10. Tự kiểm tra

1. Khi nào nên dùng `@Query(count = true)` thay vì tải danh sách rồi gọi `size()`?
2. Cờ `exists = true` phù hợp với kiểu trả về nào?
3. Khác biệt giữa `count = true` và `countQuery` là gì?
4. Vì sao `count(DISTINCT c)` có thể đúng hơn `count(c)` khi truy vấn đi qua relationship?
5. Khi nào nên dùng `DELETE r` và khi nào nên dùng `DETACH DELETE c`?
6. Vì sao delete query thường dùng `void` nếu ứng dụng không cần kết quả sau xóa?
7. Custom query trả về `Page<T>` cần chuẩn bị những phần nào trong Cypher?
8. Vì sao một custom query chỉ đọc nên được đánh dấu read-only khi phù hợp?
9. Cần kiểm tra điều gì sau khi chạy một delete query để bảo đảm phạm vi xóa đúng?

Hãy tạo ba phương thức repository: một phương thức đếm khách hàng theo trạng thái, một phương thức kiểm tra khách hàng có tồn tại theo email và một phương thức xóa relationship theo hai ID. Dùng `@Query` với các cờ tương ứng, chọn kiểu trả về phù hợp và viết integration test cho cả trường hợp có dữ liệu lẫn không có dữ liệu. Sau đó mở rộng truy vấn danh sách thành `Page<Customer>`, bổ sung `$skip`, `$limit` và `countQuery`, rồi so sánh với `Slice<Customer>`.

## Tài liệu tham khảo

- [Spring Data Neo4j — Query annotation API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/query/Query.html)
- [Spring Data Neo4j — Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j — FAQ: Pages, slices and transactions](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Commons — Repository query keywords](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-keywords-reference.html)
