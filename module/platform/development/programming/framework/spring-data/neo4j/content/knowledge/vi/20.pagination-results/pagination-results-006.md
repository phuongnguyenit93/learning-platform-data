# Slice và xác định còn kết quả phía sau

Khi API cần trả từng nhóm kết quả và chỉ cần biết **có còn dữ liệu để tải tiếp hay không**, `Slice<T>` của Spring Data là lựa chọn phù hợp. Với Spring Data Neo4j (SDN), repository nhận `Pageable` để xác định vị trí và kích thước nhóm; kết quả `Slice` cung cấp `hasNext()` mà không cần biết tổng số node phù hợp.

Điểm khác biệt quan trọng là `Slice` không tính tổng số phần tử hoặc tổng số trang như `Page<T>`. SDN lấy thêm một kết quả so với kích thước trang để nhận biết còn dữ liệu phía sau. Cơ chế này phù hợp với danh sách cuộn vô hạn, lịch sử hoạt động, danh sách đơn hàng hoặc các màn hình chỉ hiển thị nút “Tải thêm”.

## 1. `Slice` giải quyết vấn đề gì?

Giả sử màn hình quản trị cần hiển thị người dùng đang hoạt động theo từng nhóm 20 người. Giao diện cần biết:

- Nhóm hiện tại có những người nào?
- Có thể hiển thị nút “Tiếp theo” hoặc “Tải thêm” không?
- Nếu có, trang tiếp theo bắt đầu từ đâu?

Màn hình không nhất thiết cần biết chính xác toàn bộ hệ thống có bao nhiêu người đang hoạt động. Nếu dùng `Page<T>`, Spring Data có thể phải chạy thêm truy vấn đếm để tính tổng số phần tử và số trang. Với `Slice<T>`, ứng dụng chỉ cần biết liệu có ít nhất một kết quả nằm sau nhóm hiện tại.

`Slice` chứa dữ liệu của một nhóm cùng metadata điều hướng như số trang, kích thước, số phần tử thực tế và trạng thái có trang tiếp theo hay không.

## 2. Phân biệt `Slice`, `Page` và `List`

| Kiểu trả về | Dữ liệu lấy | Thông tin bổ sung | Phù hợp khi |
| --- | --- | --- | --- |
| `List<T>` với `Pageable` | Chỉ phạm vi được yêu cầu | Danh sách kết quả, không có `hasNext()` | Chỉ cần một nhóm dữ liệu và tự quản lý điều hướng |
| `Slice<T>` | Tối đa `pageSize + 1` kết quả để phát hiện phần tiếp theo | `hasNext()`, `isLast()`, số phần tử trong slice và thông tin trang | Chỉ cần biết còn dữ liệu hay không |
| `Page<T>` | Kích thước trang được yêu cầu | Tổng phần tử, tổng số trang và metadata của trang | Giao diện cần hiển thị “trang 2 trên 18” hoặc tổng số kết quả |

Ví dụ, với `pageSize = 20`:

- `List<Person>` lấy tối đa 20 kết quả. Ứng dụng không biết còn kết quả phía sau chỉ từ `List`.
- `Slice<Person>` đọc tối đa 21 kết quả. Nếu có kết quả thứ 21, SDN trả 20 phần tử đầu và đánh dấu `hasNext() = true`.
- `Page<Person>` trả dữ liệu của trang và có thể chạy thêm count query để tính tổng số kết quả.

Việc lấy thêm một phần tử là đủ để xác định có trang kế tiếp mà không cần đếm toàn bộ kết quả phù hợp. Nếu kết quả chỉ có 13 phần tử trong khi kích thước trang là 20, slice chứa 13 phần tử và `hasNext()` là `false`.

## 3. Khai báo repository trả về `Slice`

Giả sử domain có node `Person` với trạng thái tài khoản:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String name;

    private String status;
}
```

Repository chỉ cần khai báo `Slice<Person>` và nhận thêm `Pageable`:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    Slice<Person> findByStatus(String status, Pageable pageable);
}
```

Đây là derived query. SDN tạo Cypher dựa trên tên phương thức, property `status` và metadata phân trang trong `Pageable`. Ứng dụng không cần tự viết `SKIP` hoặc `LIMIT` cho phương thức derived query này.

## 4. Tạo trang đầu và kiểm tra `hasNext()`

`PageRequest` tạo một `Pageable` có số trang bắt đầu từ 0. Ví dụ, trang đầu tiên có chỉ số 0 và kích thước 20:

```java
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.Slice;

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.asc("name"), Sort.Order.asc("personId"))
);

Slice<Person> slice = personRepository.findByStatus("ACTIVE", pageable);

List<Person> people = slice.getContent();
boolean hasMore = slice.hasNext();
```

Trong ví dụ, kết quả được sắp xếp theo tên tăng dần, sau đó theo `personId`. Trường ID đóng vai trò tiêu chí phụ để thứ tự ổn định khi nhiều người có cùng tên.

`hasNext()` trả về `true` nếu SDN phát hiện có ít nhất một kết quả phía sau slice hiện tại. Có thể dùng `isLast()` để kiểm tra slice hiện tại có phải slice cuối cùng hay không; hai cách diễn đạt này bổ sung cho nhau.

## 5. Tải slice tiếp theo

Khi `hasNext()` là `true`, lấy `nextPageable()` để tạo yêu cầu cho nhóm kế tiếp:

```java
if (slice.hasNext()) {
    Pageable nextPageable = slice.nextPageable();

    Slice<Person> nextSlice = personRepository.findByStatus(
        "ACTIVE",
        nextPageable
    );

    List<Person> nextPeople = nextSlice.getContent();
}
```

`nextPageable()` chỉ nên được gọi khi `hasNext()` là `true`. Nếu không còn dữ liệu, không có trang kế tiếp để tải.

Một service có thể đóng gói kết quả cho API:

```java
import java.util.List;

public record PersonSliceResponse(
    List<Person> items,
    boolean hasNext,
    int page,
    int size
) {}
```

```java
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

public PersonSliceResponse findActivePeople(int page, int size) {
    Pageable pageable = PageRequest.of(
        page,
        size,
        Sort.by("name").ascending().and(Sort.by("personId").ascending())
    );

    Slice<Person> slice = personRepository.findByStatus("ACTIVE", pageable);

    return new PersonSliceResponse(
        slice.getContent(),
        slice.hasNext(),
        slice.getNumber(),
        slice.getSize()
    );
}
```

Client có thể dựa vào `hasNext` để hiển thị nút “Tải thêm”. Nếu `hasNext` là `false`, giao diện có thể dừng điều hướng mà không cần biết tổng số kết quả.

## 6. Những method thường dùng trên `Slice`

| Method | Ý nghĩa |
| --- | --- |
| `getContent()` | Danh sách phần tử trong slice hiện tại |
| `getNumber()` | Chỉ số slice hiện tại, bắt đầu từ 0 |
| `getSize()` | Kích thước slice được yêu cầu |
| `getNumberOfElements()` | Số phần tử thực tế trong slice |
| `hasNext()` | Có slice tiếp theo hay không |
| `isLast()` | Slice hiện tại có phải slice cuối hay không |
| `hasPrevious()` | Có slice trước đó hay không |
| `nextPageable()` | Thông tin phân trang cho slice tiếp theo |
| `previousPageable()` | Thông tin phân trang cho slice trước đó |
| `getSort()` | Thông tin sắp xếp của slice |

`Slice` không có `getTotalElements()` hoặc `getTotalPages()` như `Page`, vì nó không duy trì tổng số phần tử và số trang. Nếu giao diện cần các con số đó, hãy cân nhắc `Page<T>` và chấp nhận chi phí count query tương ứng.

## 7. Dùng `Slice` với custom Cypher trong `@Query`

Với derived query, SDN tự tạo truy vấn có phân trang. Với custom query, câu Cypher phải tự thể hiện vị trí và giới hạn kết quả bằng hai tham số đặc biệt `$skip` và `$limit`.

Ví dụ, tìm người có đơn hàng thuộc một trạng thái nhất định:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person)-[:PLACED]->(o:Order)
        WHERE o.status = $orderStatus
        WITH DISTINCT p
        RETURN p
        ORDER BY p.name ASC, p.personId ASC
        SKIP $skip LIMIT $limit
        """)
    Slice<Person> findPeopleByOrderStatus(
        @Param("orderStatus") String orderStatus,
        Pageable pageable
    );
}
```

Trong custom query này:

- `$skip` nhận offset tính từ `Pageable`.
- `$limit` nhận giới hạn kết quả mà cơ chế `Slice` cần để phát hiện phần tiếp theo.
- `ORDER BY` được khai báo trực tiếp trong Cypher.
- `WITH DISTINCT p` loại các dòng trùng người trước khi áp dụng thứ tự và phân trang, vì một người có thể có nhiều đơn hàng cùng trạng thái.

Khi dùng custom query kiểu này, hãy truyền `Pageable` không có sort, vì SDN không áp dụng thông tin sắp xếp từ `Pageable` vào câu Cypher tùy chỉnh. Ví dụ:

```java
Pageable pageable = PageRequest.of(0, 20, Sort.unsorted());
Slice<Person> slice = repository.findPeopleByOrderStatus("PAID", pageable);
```

Tự khai báo một thứ tự ổn định trong Cypher, tốt nhất có thêm khóa duy nhất làm tiêu chí phụ. Nếu bỏ `ORDER BY`, các node có thể xuất hiện ở thứ tự khác nhau giữa các lần gọi, làm việc chia trang dễ bị lặp hoặc bỏ sót phần tử.

Custom query trả `Slice` không cần `countQuery`, vì slice chỉ cần xác định có dữ liệu phía sau. Với custom query trả `Page`, cần cung cấp `countQuery` phù hợp để tính tổng số kết quả. Tài liệu SDN cũng yêu cầu custom Cypher cho `Slice` phải có cả `$skip` và `$limit`; nếu thiếu, SDN phát cảnh báo và kết quả có thể không như mong đợi.

## 8. Vì sao thứ tự sắp xếp ổn định rất quan trọng?

Phân trang dựa trên offset chia một tập kết quả thành các đoạn. Nếu thứ tự không xác định, cùng một node có thể chuyển vị trí giữa các lần truy vấn.

Ví dụ, chỉ sắp xếp theo `name` có thể chưa đủ nếu nhiều người cùng tên. Hãy thêm ID làm tiêu chí phụ:

```cypher
MATCH (p:Person)
WHERE p.status = $status
RETURN p
ORDER BY p.name ASC, p.personId ASC
SKIP $skip LIMIT $limit
```

Thứ tự này tạo ra một trình tự nhất quán hơn vì `personId` phân biệt các node có cùng tên. Với derived query, có thể truyền `Sort` vào `Pageable` theo cùng nguyên tắc.

## 9. Chú ý khi truy vấn đi qua relationship

Một truy vấn đồ thị có thể tạo nhiều dòng cho cùng một node gốc. Ví dụ, một người có nhiều đơn hàng thỏa điều kiện sẽ xuất hiện nhiều lần sau `MATCH`:

```cypher
MATCH (p:Person)-[:PLACED]->(o:Order)
WHERE o.status = $status
RETURN p
```

Nếu phân trang trực tiếp trên các dòng này, cùng một người có thể chiếm nhiều vị trí trong slice. Điều đó khiến số người duy nhất trong một slice ít hơn kích thước yêu cầu và có thể gây cảm giác kết quả bị lặp.

Khi mục tiêu là phân trang theo node `Person`, hãy loại trùng trước khi `ORDER BY`, `SKIP` và `LIMIT`:

```cypher
MATCH (p:Person)-[:PLACED]->(o:Order)
WHERE o.status = $status
WITH DISTINCT p
RETURN p
ORDER BY p.name ASC, p.personId ASC
SKIP $skip LIMIT $limit
```

Thứ tự các bước rất quan trọng: `DISTINCT` phải diễn ra trước khi chia trang để mỗi node gốc chỉ chiếm một vị trí. Nếu cần trả cả thông tin tổng hợp từ relationship, hãy tính hoặc `collect` dữ liệu theo từng node gốc trước khi áp dụng pagination.

## 10. Offset lớn và dữ liệu thay đổi giữa các lần tải

`Pageable` thông thường dùng offset. Trang đầu có offset 0; trang tiếp theo có offset bằng số phần tử đã đi qua. Với những trang rất sâu, database vẫn phải duyệt hoặc bỏ qua một lượng lớn kết quả trước khi trả phần dữ liệu cần thiết. Vì vậy, offset pagination có thể kém hiệu quả khi offset tăng cao.

Ngoài ra, nếu dữ liệu được thêm hoặc xóa giữa hai lần tải, vị trí offset có thể dịch chuyển. Một node đã xuất hiện ở trang trước có thể xuất hiện lại hoặc một node khác bị bỏ qua. Thứ tự ổn định giúp giảm vấn đề do các giá trị sắp xếp trùng nhau, nhưng không tạo snapshot xuyên suốt nhiều request độc lập.

Với danh sách rất lớn hoặc cập nhật liên tục, hãy cân nhắc cursor/keyset pagination dựa trên giá trị cuối cùng đã đọc, chẳng hạn cặp `(name, personId)`. Khi đó truy vấn tiếp theo lọc các node đứng sau khóa cuối cùng thay vì bỏ qua một offset lớn. Đây là một chiến lược truy vấn riêng; `Slice` với `PageRequest` mặc định vẫn là offset-based.

## 11. Chọn `Slice` hay `Page` trong API?

| Yêu cầu giao diện | Lựa chọn |
| --- | --- |
| Chỉ có nút “Tải thêm” | `Slice<T>` |
| Cuộn vô hạn, chỉ cần biết còn dữ liệu | `Slice<T>` |
| Hiển thị “đang xem 20 kết quả” nhưng không cần tổng | `Slice<T>` |
| Hiển thị “trang 2 / 12” | `Page<T>` |
| Cần tổng số kết quả để hiển thị bộ đếm | `Page<T>` hoặc count query riêng |
| Chỉ lấy một đoạn dữ liệu và không cần điều hướng tự động | `List<T>` với `Pageable` |

Không nên dùng `Page<T>` chỉ vì giao diện có nút tiếp theo. Nếu chỉ cần `hasNext()`, `Slice<T>` tránh yêu cầu tổng số kết quả và có thể tiết kiệm một count query đáng kể trên graph lớn.

## 12. Checklist kiểm tra `Slice`

Trước khi đưa phân trang vào API, hãy xác minh:

1. Repository method trả `Slice<T>` và nhận một `Pageable` không null.
2. `PageRequest` dùng chỉ số trang bắt đầu từ 0 và kích thước hợp lý.
3. Derived query có thứ tự sắp xếp ổn định; custom query khai báo `ORDER BY` rõ ràng.
4. Custom `@Query` có cả `$skip` và `$limit`.
5. Custom query truyền `Pageable` unsorted nếu thứ tự đã được viết trực tiếp trong Cypher.
6. Nếu query đi qua nhiều relationship, loại dòng trùng của node gốc trước khi phân trang.
7. Code chỉ gọi `nextPageable()` khi `hasNext()` là `true`.
8. Integration test kiểm tra trang đầu, trang giữa, trang cuối, tập rỗng và dữ liệu trùng do relationship.
9. Với offset sâu, đo hiệu năng và cân nhắc cursor/keyset pagination.

## Kết luận

`Slice<T>` là abstraction phù hợp khi ứng dụng chỉ cần biết còn kết quả phía sau hay không. SDN lấy tối đa `pageSize + 1` kết quả để xác định `hasNext()` mà không cần count query như `Page<T>`. Với derived query, chỉ cần truyền `Pageable`; với custom Cypher, phải có `$skip` và `$limit`, đồng thời khai báo thứ tự ổn định và truyền `Pageable` unsorted nếu đã tự sắp xếp trong query. Khi truy vấn đi qua relationship, hãy loại node gốc trùng trước khi phân trang. Với offset sâu hoặc dữ liệu thay đổi liên tục, cân nhắc cursor/keyset pagination.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2.0 — Paging, Iterating Large Results, Sorting & Limiting](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Spring Data Neo4j 7.0.2 — Custom queries returning Page or Slice](https://docs.spring.io/spring-data/neo4j/docs/7.0.2/reference/html/)
