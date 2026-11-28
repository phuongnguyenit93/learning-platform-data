# Thứ tự ổn định và khóa phụ khi nhiều node cùng giá trị sắp xếp

## Mục tiêu bài học

Khi phân trang kết quả từ Neo4j, việc chọn đúng `SKIP` và `LIMIT` chưa đủ để bảo đảm các trang nhất quán. Nếu nhiều node có cùng giá trị sắp xếp, database có thể trả chúng theo thứ tự khác nhau giữa các lần thực thi khi truy vấn không quy định thêm tiêu chí phân biệt. Kết quả là một node có thể xuất hiện ở hai trang hoặc bị bỏ qua khi người dùng chuyển trang.

Với Spring Data Neo4j (SDN), hãy thiết kế thứ tự có tính xác định bằng cách kết hợp tiêu chí nghiệp vụ với một khóa phụ duy nhất. Bài học này giải thích vì sao cần khóa phụ, cách áp dụng với derived query và custom Cypher, cách kiểm thử ranh giới trang, và khi nào nên chuyển từ phân trang theo offset sang phân trang theo cursor (keyset).

## 1. Vì sao ORDER BY một thuộc tính có thể chưa đủ?

Giả sử trang quản trị hiển thị khách hàng theo thời điểm tạo mới nhất. Nhiều khách hàng có thể được tạo trong cùng một giây, nên truy vấn chỉ sắp xếp theo `createdAt`:

```cypher
MATCH (c:Customer)
RETURN c
ORDER BY c.createdAt DESC
SKIP 0
LIMIT 3
```

Nếu nhiều node có cùng `createdAt`, Cypher không có tiêu chí để xác định node nào đứng trước node nào trong nhóm có giá trị bằng nhau. Neo4j không cam kết thứ tự ổn định giữa các node có cùng giá trị sort khi truy vấn không chỉ định thêm tiêu chí.

Ví dụ có năm khách hàng cùng thời điểm tạo:

| Customer | createdAt |
|---|---|
| C-101 | 2026-11-20T09:00:00 |
| C-102 | 2026-11-20T09:00:00 |
| C-103 | 2026-11-20T09:00:00 |
| C-104 | 2026-11-20T09:00:00 |
| C-105 | 2026-11-20T09:00:00 |

Với kích thước trang là ba, truy vấn chỉ sắp xếp theo `createdAt` có thể chọn ba node bất kỳ trong nhóm cùng thời điểm cho trang đầu. Khi chạy lại để lấy trang kế tiếp, thứ tự nội bộ của nhóm có thể khác. Một node đã xuất hiện ở trang đầu có thể bị đẩy sang trang sau, hoặc một node chưa từng xuất hiện bị bỏ qua do vị trí bị thay đổi.

**Thứ tự ổn định cần tạo ra một thứ tự toàn phần (total order)** cho tập kết quả. Khi giá trị của tiêu chí chính bằng nhau, cần thêm tiêu chí phụ để phân biệt các node.

## 2. Thêm khóa phụ duy nhất vào ORDER BY

Một cách phổ biến là sắp xếp theo tiêu chí nghiệp vụ trước, sau đó theo ID duy nhất:

```cypher
MATCH (c:Customer)
RETURN c
ORDER BY c.createdAt DESC, c.id ASC
SKIP 0
LIMIT 3
```

Thứ tự trên có hai tầng:

1. `createdAt DESC`: khách hàng mới hơn đứng trước.
2. `id ASC`: nếu hai khách hàng có cùng thời điểm tạo, ID tăng dần quyết định thứ tự giữa chúng.

Khi `id` duy nhất và không null, mỗi node có vị trí phân biệt trong thứ tự kết quả. Cùng một tập dữ liệu và cùng điều kiện truy vấn sẽ tạo ra thứ tự nhất quán giữa các lần đọc.

Trong mô hình Java, có thể khai báo ID ứng dụng được lưu thành property trên node:

```java
@Node("Customer")
public class Customer {

    @Id
    private String id;

    private String name;

    private String status;

    private LocalDateTime createdAt;

    // Constructor, getter và setter được lược bỏ.
}
```

Ví dụ dùng ID do ứng dụng cung cấp, không dùng `@GeneratedValue` cho trường `id`. Khi đó, ID được lưu như một property của node và có thể dùng làm khóa phụ trong Cypher. Ứng dụng phải cấp ID ổn định, không null và duy nhất.

Tạo uniqueness constraint để Neo4j bảo vệ quy tắc này:

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.id IS UNIQUE;
```

Constraint cần được tạo sau khi dữ liệu hiện có đã đáp ứng điều kiện duy nhất. Nếu ID được sinh theo cơ chế khác, hãy chọn property nghiệp vụ thực sự được lưu trên node và được bảo đảm duy nhất làm khóa phụ.

Không nên dùng một property có thể trùng như `name`, `city` hoặc `status` làm tiêu chí cuối cùng rồi giả định thứ tự đã ổn định. Khóa phụ cuối cùng cần phân biệt được từng node trong tập kết quả.

## 3. Chọn thứ tự nhiều tiêu chí theo quy tắc nghiệp vụ

Khóa phụ không nhất thiết phải là tiêu chí thứ hai. Có thể có nhiều tiêu chí nghiệp vụ trước khóa duy nhất cuối cùng:

```cypher
MATCH (c:Customer)
WHERE c.status = $status
RETURN c
ORDER BY c.createdAt DESC,
         c.name ASC,
         c.id ASC
```

Thứ tự được áp dụng lần lượt:

- Thời điểm tạo mới nhất trước.
- Nếu cùng thời điểm, tên theo thứ tự tăng dần.
- Nếu cả thời điểm và tên cùng bằng nhau, ID duy nhất quyết định thứ tự cuối cùng.

Các tiêu chí phụ cần phản ánh yêu cầu hiển thị. Nếu người dùng mong đợi nhóm theo trạng thái trước, hãy đặt `status` ở vị trí đầu tiên; nếu cần khách hàng mới nhất trước, đặt `createdAt DESC` đầu tiên. Khóa duy nhất thường nằm cuối danh sách để phá hòa giữa các node còn bằng nhau.

Hướng sắp xếp của từng tiêu chí có thể khác nhau. Ví dụ:

```cypher
ORDER BY c.status ASC, c.createdAt DESC, c.id ASC
```

Hãy ghi rõ `ASC` hoặc `DESC` để người đọc hiểu thứ tự. Mặc dù Cypher có hướng mặc định, viết tường minh giúp tránh hiểu nhầm khi truy vấn có nhiều tiêu chí.

### Giá trị null và tiêu chí sắp xếp

Nếu property sắp xếp có thể là `null`, cần xác định vị trí của các node thiếu giá trị theo quy tắc sắp xếp null của Cypher trong phiên bản Neo4j đang dùng. Hãy kiểm tra tài liệu và kiểm thử dữ liệu thực tế. Nếu nghiệp vụ cần thứ tự rõ ràng, nên yêu cầu property chính có giá trị hoặc chuẩn hóa giá trị trước khi lưu.

Khóa phụ duy nhất chỉ giải quyết trường hợp các tiêu chí trước đó bằng nhau. Nó không thay thế quy tắc nghiệp vụ cho dữ liệu null hoặc sai định dạng.

## 4. Sắp xếp với derived query và Pageable

Với derived query, có thể truyền `Pageable` kèm `Sort`. Spring Data sử dụng tên property trong domain model Java để tạo thứ tự.

Repository:

```java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    Page<Customer> findByStatus(String status, Pageable pageable);
}
```

Tạo yêu cầu trang đầu tiên với hai tiêu chí sắp xếp:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        )
);

Page<Customer> page =
        customerRepository.findByStatus("ACTIVE", pageable);
```

`PageRequest.of` dùng chỉ số trang bắt đầu từ 0. `Sort.Order.desc("createdAt")` đặt thời điểm tạo mới nhất lên trước; `Sort.Order.asc("id")` phá hòa bằng ID.

Tên trong `Sort` là property Java của entity, không phải tên label hoặc relationship type. Nếu property Java được ánh xạ sang tên khác trong Neo4j bằng `@Property`, hãy dùng tên Java trong `Sort`.

Khi người dùng chọn cột sắp xếp trên giao diện, hãy giới hạn các lựa chọn vào danh sách property hợp lệ của API. Không ghép trực tiếp chuỗi sort tùy ý từ request vào Cypher. Với derived query, chuyển lựa chọn hợp lệ thành `Sort`; với custom query, dùng các mẫu truy vấn đã định nghĩa rõ ràng cho từng kiểu sắp xếp.

## 5. Viết thứ tự ổn định trong custom Cypher

Với custom query, viết đầy đủ `ORDER BY` trong câu Cypher. Ví dụ repository trả về một trang khách hàng theo trạng thái:

```java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    @Query(
        value = "MATCH (c:Customer) " +
                "WHERE c.status = $status " +
                "RETURN c " +
                "ORDER BY c.createdAt DESC, c.id ASC " +
                "SKIP $skip LIMIT $limit",
        countQuery = "MATCH (c:Customer) " +
                     "WHERE c.status = $status " +
                     "RETURN count(c)"
    )
    Page<Customer> findCustomerPageByStatus(
            @Param("status") String status,
            Pageable pageable);
}
```

Ở đây:

- `ORDER BY c.createdAt DESC, c.id ASC` tạo thứ tự toàn phần.
- `SKIP $skip` bỏ qua số node thuộc các trang trước.
- `LIMIT $limit` giới hạn số node của trang hiện tại.
- `countQuery` đếm tổng số khách hàng thỏa điều kiện để tạo metadata cho `Page`.

Khi gọi custom query này, hãy truyền `Pageable` không kèm sort vì thứ tự đã được viết tường minh trong Cypher. SDN dùng thông tin trang để cung cấp các giá trị skip và limit; không nên giả định framework sẽ tự chèn sort trong `Pageable` vào câu Cypher tùy chỉnh.

Ví dụ gọi trang đầu:

```java
Pageable pageable = PageRequest.of(0, 20);
Page<Customer> firstPage =
        customerRepository.findCustomerPageByStatus("ACTIVE", pageable);
```

Trang tiếp theo dùng chỉ số trang 1:

```java
Pageable pageable = PageRequest.of(1, 20);
Page<Customer> secondPage =
        customerRepository.findCustomerPageByStatus("ACTIVE", pageable);
```

Cả hai lần gọi đều dùng cùng một thứ tự `createdAt DESC, id ASC`. Nếu điều kiện lọc có traversal relationship làm một node gốc xuất hiện nhiều lần, hãy khử trùng node trong query lấy dữ liệu và bảo đảm `countQuery` đếm cùng tập node duy nhất. Nếu không, tổng số phần tử của `Page` có thể không khớp số entity thực tế.

### Dùng Slice khi không cần tổng số phần tử

Nếu giao diện chỉ cần biết có trang tiếp theo hay không, có thể dùng `Slice<Customer>`:

```java
@Query(
    "MATCH (c:Customer) " +
    "WHERE c.status = $status " +
    "RETURN c " +
    "ORDER BY c.createdAt DESC, c.id ASC " +
    "SKIP $skip LIMIT $limit"
)
Slice<Customer> findCustomerSliceByStatus(
        @Param("status") String status,
        Pageable pageable);
```

Slice không cần truy vấn đếm tổng số phần tử. Thứ tự vẫn phải ổn định; việc dùng Slice không loại bỏ yêu cầu khóa phụ.

## 6. Vì sao khóa phụ quan trọng ở ranh giới trang?

Giả sử kích thước trang là hai và có bốn khách hàng cùng `createdAt`. Nếu chỉ sắp xếp theo thời gian, hai lần truy vấn có thể tạo ra thứ tự khác nhau trong nhóm bằng nhau.

Với thứ tự `createdAt DESC, id ASC`, thứ tự được xác định rõ:

| Vị trí | Customer | createdAt | id |
|---:|---|---|---|
| 1 | An | 09:00 | C-101 |
| 2 | Bình | 09:00 | C-102 |
| 3 | Chi | 09:00 | C-103 |
| 4 | Dũng | 09:00 | C-104 |

Khi `LIMIT 2`:

- Trang 0: C-101, C-102.
- Trang 1 với `SKIP 2 LIMIT 2`: C-103, C-104.

Vì thứ tự trong nhóm cùng thời điểm đã được phá hòa bằng ID, hai trang không phụ thuộc vào thứ tự nội bộ không xác định của database.

Nếu thiếu khóa phụ, một lần chạy có thể trả C-103 và C-101 ở trang đầu, còn lần khác trả C-102 và C-103. Khi ứng dụng kết hợp hai trang được tải ở hai thời điểm, C-103 có thể bị lặp và C-102 bị thiếu.

Khóa phụ tạo thứ tự xác định cho cùng một tập dữ liệu. Tuy nhiên, nó chưa bảo đảm người dùng duyệt qua một snapshot bất biến nếu graph tiếp tục được ghi trong lúc họ chuyển trang.

## 7. Giới hạn của offset pagination khi dữ liệu thay đổi

Phân trang theo offset dùng vị trí trong danh sách đã sắp xếp:

```cypher
ORDER BY c.createdAt DESC, c.id ASC
SKIP 20
LIMIT 20
```

Giả sử người dùng vừa xem trang đầu, sau đó một khách hàng mới được thêm vào đầu danh sách trước khi họ yêu cầu trang thứ hai. Các vị trí phía sau bị dịch chuyển một đơn vị. Trang thứ hai có thể lặp lại node cuối trang đầu hoặc bỏ sót một node.

Khóa phụ duy nhất giải quyết sự không xác định khi các giá trị sắp xếp bằng nhau, nhưng không ngăn các vị trí thay đổi khi node được thêm, xóa hoặc cập nhật giữa hai request.

Offset pagination vẫn phù hợp khi:

- Tập dữ liệu ít thay đổi trong khoảng thời gian người dùng duyệt.
- Người dùng cần nhảy đến một trang bất kỳ.
- API cần tổng số phần tử và số trang.
- Dataset vừa phải và chi phí bỏ qua nhiều dòng chấp nhận được.

Nếu dữ liệu thay đổi liên tục hoặc số trang rất sâu, hãy cân nhắc keyset pagination.

## 8. Keyset pagination dùng khóa sắp xếp làm cursor

Keyset pagination không yêu cầu database bỏ qua toàn bộ các node của trang trước. Thay vào đó, ứng dụng gửi giá trị của node cuối cùng ở trang hiện tại làm cursor. Truy vấn kế tiếp tìm các node đứng sau cursor theo cùng quy tắc sắp xếp.

Với thứ tự:

```cypher
ORDER BY c.createdAt DESC, c.id ASC
```

Node đứng sau cursor có điều kiện:

- `createdAt` nhỏ hơn thời điểm của node cuối trang trước; hoặc
- `createdAt` bằng thời điểm đó và `id` lớn hơn ID cuối trang trước.

Cypher cho trang kế tiếp:

```cypher
MATCH (c:Customer)
WHERE c.status = $status
  AND (
      c.createdAt < $lastCreatedAt
      OR (
          c.createdAt = $lastCreatedAt
          AND c.id > $lastId
      )
  )
RETURN c
ORDER BY c.createdAt DESC, c.id ASC
LIMIT $limit
```

Repository có thể khai báo:

```java
@Query(
    "MATCH (c:Customer) " +
    "WHERE c.status = $status " +
    "AND (c.createdAt < $lastCreatedAt " +
    "OR (c.createdAt = $lastCreatedAt AND c.id > $lastId)) " +
    "RETURN c " +
    "ORDER BY c.createdAt DESC, c.id ASC " +
    "LIMIT $limit"
)
List<Customer> findCustomersAfter(
        @Param("status") String status,
        @Param("lastCreatedAt") LocalDateTime lastCreatedAt,
        @Param("lastId") String lastId,
        @Param("limit") int limit);
```

Trang đầu dùng truy vấn riêng không có điều kiện cursor. Sau khi đọc một trang, lấy `createdAt` và `id` của node cuối cùng để làm cursor cho lần gọi tiếp theo. Nếu cần xác định có trang tiếp theo, có thể yêu cầu thêm một phần tử so với kích thước hiển thị, rồi dùng phần tử dư để tính `hasNext`.

Các giá trị cursor phải đến từ bản ghi cuối cùng của trang trước, không lấy trực tiếp một biểu thức tùy ý từ request. Cần kiểm tra `limit` là số dương và bảo đảm cursor có đủ cả hai thành phần.

Keyset pagination cần các tiêu chí sắp xếp ổn định, có thể so sánh và không null trong phạm vi truy vấn. Nếu thay đổi thứ tự hoặc hướng sort, điều kiện so sánh cursor cũng phải đổi tương ứng. Ví dụ trên đúng cho `createdAt DESC, id ASC`; không thể sao chép nguyên điều kiện đó cho `createdAt ASC, id DESC`.

Keyset giảm chi phí offset sâu và hạn chế việc dịch chuyển vị trí do bản ghi mới nằm trước cursor. Tuy nhiên, nó không tạo snapshot tuyệt đối: nếu một node hiện có thay đổi `createdAt` và đi qua cursor, node đó vẫn có thể xuất hiện lặp hoặc bị bỏ qua. Vì vậy, ưu tiên khóa sắp xếp bất biến như thời điểm tạo không đổi và ID ổn định.

## 9. Chọn chiến lược phân trang

| Tiêu chí | Offset với Page | Offset với Slice | Keyset/Cursor |
|---|---|---|---|
| Thứ tự ổn định | Cần ORDER BY và khóa phụ | Cần ORDER BY và khóa phụ | Cần thứ tự và cursor tương ứng |
| Tổng số phần tử | Có | Không | Thường không |
| Nhảy đến trang bất kỳ | Có | Có | Không thuận tiện |
| Trang rất sâu | Có thể tốn chi phí do SKIP | Có thể tốn chi phí do SKIP | Thường hiệu quả hơn |
| Dữ liệu mới được thêm trước vị trí đang xem | Có thể làm lệch offset | Có thể làm lệch offset | Ít ảnh hưởng đến cursor đã đi qua |
| Dữ liệu sắp xếp bị sửa | Có thể lặp hoặc bỏ sót | Có thể lặp hoặc bỏ sót | Có thể lặp hoặc bỏ sót nếu đi qua cursor |
| Phù hợp | Bảng quản trị, tìm kiếm có tổng số trang | Feed đơn giản cần biết còn dữ liệu | Feed lớn, cuộn liên tục, dữ liệu thường xuyên thêm mới |

Chọn chiến lược theo trải nghiệm người dùng và cách dữ liệu thay đổi. Nếu cần hiển thị “trang 4 trên 12”, Page thuận tiện. Nếu giao diện chỉ có nút “Xem thêm”, Slice hoặc cursor có thể phù hợp hơn. Nếu cần hiệu quả ở tập dữ liệu lớn và duyệt tuần tự, keyset đáng cân nhắc.

Dù chọn chiến lược nào, hãy định nghĩa thứ tự ở tầng truy vấn và kiểm tra nó trên dữ liệu có nhiều giá trị trùng.

## 10. Kiểm thử thứ tự và phân trang

Một test chỉ tạo dữ liệu với các giá trị sort khác nhau chưa đủ để phát hiện lỗi thiếu khóa phụ. Hãy tạo fixture có nhiều node cùng giá trị ở tiêu chí chính, đặc biệt tại ranh giới giữa hai trang.

Ví dụ, với page size là hai, tạo ít nhất năm khách hàng có cùng `createdAt` nhưng ID khác nhau. Sau đó đọc liên tiếp các trang và xác nhận:

1. Mỗi trang không vượt quá kích thước yêu cầu.
2. Thứ tự trong từng trang đúng theo `createdAt DESC, id ASC`.
3. Trang sau bắt đầu sau node cuối của trang trước theo thứ tự đã chọn.
4. Khi dữ liệu không đổi, hợp nhất các trang không có ID trùng.
5. Không có node phù hợp nào bị bỏ sót.
6. `Page.getTotalElements()` khớp số node duy nhất thỏa điều kiện.

Ví dụ khung integration test:

```java
@DataNeo4jTest
class CustomerPaginationTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldKeepStableOrderWhenCreatedAtValuesAreEqual() {
        // Tạo năm Customer có cùng createdAt và ID khác nhau.
        // Lưu dữ liệu qua repository.
        // Đọc Page 0 và Page 1 với Sort:
        // createdAt DESC, id ASC.
        // Xác nhận thứ tự ID đúng và không có ID trùng giữa hai trang.
    }
}
```

Đối với keyset pagination, kiểm tra cursor được tạo từ node cuối trang và query tiếp theo trả về những node đứng sau node đó. Bổ sung test khi hai hoặc nhiều node có cùng `createdAt`, vì đây là trường hợp điều kiện cursor cần dùng đến khóa phụ.

Cũng nên có test riêng mô phỏng một node mới được chèn trước cursor hoặc một node bị thay đổi sort key giữa hai lần đọc. Test này giúp xác nhận hành vi nhất quán mà API cam kết, đồng thời cho thấy giới hạn của phân trang khi dữ liệu thay đổi.

## 11. Tối ưu truy vấn mà vẫn giữ đúng thứ tự

Thứ tự ổn định là yêu cầu đúng đắn của kết quả; index là công cụ tối ưu hiệu năng. Không nên bỏ `ORDER BY` chỉ vì truy vấn hiện tại có vẻ trả về theo thứ tự mong muốn từ index.

Một số nguyên tắc:

- Lọc theo các property có tính chọn lọc cao trước khi sắp xếp tập kết quả.
- Tạo index phù hợp cho các điều kiện lọc thường xuyên, rồi dùng `PROFILE` để xem kế hoạch thực thi.
- Chỉ trả về node hoặc projection mà màn hình cần.
- Với offset sâu, đánh giá keyset pagination thay vì tăng `SKIP` không giới hạn.
- Giữ khóa phụ có kích thước và kiểu dữ liệu phù hợp, có giá trị duy nhất.
- Tránh thay đổi tiêu chí sort giữa các trang của cùng một luồng duyệt.

Index có thể giúp Neo4j tìm hoặc sắp xếp dữ liệu hiệu quả hơn trong một số kế hoạch, nhưng không tự định nghĩa hợp đồng thứ tự của kết quả. Hợp đồng đó vẫn nằm trong `ORDER BY` của Cypher hoặc `Sort` hợp lệ của derived query.

## 12. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ sắp xếp theo `createdAt` có nhiều giá trị bằng nhau | Thứ tự giữa các node bằng nhau không được xác định | Thêm khóa phụ duy nhất như `id` |
| Dùng `name` làm khóa phụ dù tên có thể trùng | Một số node vẫn không có thứ tự phân biệt | Thêm ID duy nhất làm tiêu chí cuối |
| Thứ tự sort ở trang đầu và trang sau khác nhau | Node bị lặp hoặc bị bỏ sót | Dùng cùng thứ tự trên mọi lần gọi |
| Nghĩ `Pageable` tự thêm sort vào custom Cypher | Query có thể vẫn chạy theo thứ tự đã viết hoặc không như giao diện yêu cầu | Viết `ORDER BY` rõ ràng trong custom query |
| Dùng khóa phụ là property có thể thay đổi | Node có thể đổi vị trí giữa các lần đọc | Ưu tiên ID ổn định và sort key bất biến |
| Dùng `SKIP` lớn cho feed dữ liệu liên tục | Chi phí tăng và offset dễ lệch khi dữ liệu thay đổi | Cân nhắc keyset pagination |
| Chuyển sang keyset nhưng giữ nguyên predicate cũ khi đổi chiều sort | Có thể bỏ sót hoặc trả sai thứ tự | Suy ra predicate cursor từ đúng thứ tự sort |
| Không tạo constraint cho khóa phụ | ID trùng làm mất tính toàn phần của thứ tự | Tạo uniqueness constraint và kiểm tra dữ liệu |
| Nghĩ khóa phụ giải quyết mọi thay đổi đồng thời | Insert, delete hoặc update vẫn có thể làm thay đổi tập kết quả | Xác định chính sách nhất quán và dùng snapshot/cursor phù hợp |

## 13. Tự kiểm tra

1. Vì sao `ORDER BY c.createdAt DESC` chưa đủ khi nhiều node có cùng thời điểm?
2. Khóa phụ nên có đặc điểm gì để tạo thứ tự toàn phần?
3. Trong `ORDER BY c.createdAt DESC, c.id ASC`, tiêu chí nào được xét trước?
4. Vì sao phải dùng cùng thứ tự sắp xếp cho tất cả các trang?
5. Khóa phụ duy nhất có ngăn được hiện tượng dịch chuyển offset khi thêm node mới không?
6. Keyset pagination xác định trang tiếp theo dựa trên thông tin nào?
7. Với thứ tự `createdAt DESC, id ASC`, điều kiện cursor “sau node cuối” được viết ra sao?
8. Khi nào nên chọn Page, Slice hoặc keyset pagination?
9. Vì sao cần test dữ liệu có nhiều giá trị sort trùng nhau?

Hãy tạo năm khách hàng có cùng `createdAt` và ID khác nhau. Truy vấn bằng `ORDER BY createdAt DESC` rồi phân trang để quan sát kết quả. Sau đó thêm `id ASC`, đọc lại tất cả các trang và kiểm tra không lặp hoặc thiếu ID khi dữ liệu không thay đổi. Cuối cùng thêm một node mới ở đầu danh sách giữa hai request, so sánh offset pagination với keyset pagination và ghi lại giới hạn của từng cách.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/)
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Data Neo4j — Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
