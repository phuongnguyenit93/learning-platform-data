# Phân trang theo khóa bằng Cypher tùy chỉnh cho dữ liệu lớn

Khi một truy vấn Neo4j trả về hàng chục nghìn hoặc hàng triệu node, phân trang bằng `SKIP` và `LIMIT` có thể trở nên tốn kém ở những trang sâu. Neo4j vẫn phải tìm và bỏ qua các dòng trước vị trí yêu cầu. Với dữ liệu lớn, một lựa chọn phù hợp là keyset pagination, còn gọi là seek pagination: thay vì gửi số dòng cần bỏ qua, client gửi giá trị của bản ghi cuối cùng ở trang trước để truy vấn tiếp tục từ vị trí đó.

Trong Spring Data Neo4j (SDN), có thể triển khai cách này bằng Cypher tùy chỉnh qua `@Query`, trả về projection gọn, rồi đóng gói khóa cuối trang thành cursor cho lần gọi kế tiếp. Cách làm này đặc biệt hữu ích cho feed, danh sách sự kiện, lịch sử giao dịch hoặc màn hình cuộn vô hạn.

## 1. Vì sao keyset pagination phù hợp với dữ liệu lớn?

Phân trang offset thường có dạng:

~~~cypher
MATCH (person:Person {status: $status})
RETURN person
ORDER BY person.createdAt, person.id
SKIP $offset
LIMIT $limit
~~~

`SKIP` yêu cầu truy vấn bỏ qua một số dòng đầu tiên. Khi offset tăng lớn, database vẫn cần xử lý phần dữ liệu đứng trước trang được yêu cầu. Ngoài chi phí đó, dữ liệu được thêm hoặc xóa giữa hai lần gọi có thể làm vị trí của các dòng dịch chuyển: người dùng có thể thấy bản ghi lặp hoặc bỏ sót khi chuyển trang.

Keyset pagination dùng giá trị sắp xếp của bản ghi cuối cùng đã nhận:

~~~cypher
MATCH (person:Person {status: $status})
WHERE person.createdAt > $afterCreatedAt
   OR (person.createdAt = $afterCreatedAt AND person.id > $afterId)
RETURN person
ORDER BY person.createdAt ASC, person.id ASC
LIMIT $limit
~~~

Điều kiện `WHERE` yêu cầu database chỉ tìm các bản ghi đứng sau cursor. Truy vấn không cần đếm hoặc bỏ qua toàn bộ các dòng trước đó. Với index phù hợp và kế hoạch thực thi tốt, cách này thường duy trì hiệu năng ổn định hơn khi người dùng đi sâu qua nhiều trang.

## 2. Chọn khóa sắp xếp ổn định

Keyset pagination chỉ đúng khi thứ tự kết quả là xác định. Nếu chỉ sắp xếp theo `createdAt`, nhiều node có thể cùng thời điểm tạo. Khi đó, cursor không thể xác định chính xác vị trí giữa các node có cùng giá trị.

Hãy thêm một khóa duy nhất làm tiêu chí phụ, ví dụ ID nghiệp vụ:

~~~cypher
ORDER BY person.createdAt ASC, person.id ASC
~~~

Thứ tự của mỗi dòng là bộ khóa `(createdAt, id)`. Điều kiện trang tiếp theo phải so sánh theo thứ tự từ trái sang phải:

~~~cypher
person.createdAt > $afterCreatedAt
OR (person.createdAt = $afterCreatedAt AND person.id > $afterId)
~~~

Đây là phép so sánh từ điển (lexicographic): bản ghi đứng sau nếu thời điểm tạo lớn hơn, hoặc thời điểm bằng nhau và ID lớn hơn. ID cần duy nhất trong tập kết quả và hai khóa phải có giá trị ổn định.

Các nguyên tắc khi chọn cursor key:

- Khóa sắp xếp phải có giá trị trên mọi node trong tập kết quả; tránh `null` hoặc quy tắc null phức tạp.
- Khóa cuối cùng nên duy nhất, chẳng hạn ID đã có uniqueness constraint.
- Ưu tiên trường bất biến trong suốt quá trình phân trang, như thời điểm tạo và ID.
- Dùng cùng biểu thức `ORDER BY` và điều kiện cursor ở mọi trang.
- Nếu sắp xếp theo nhiều trường, xây dựng điều kiện so sánh theo từng tiền tố bằng nhau rồi mới so sánh trường tiếp theo.

Nếu người dùng chọn sắp xếp giảm dần, đổi cả thứ tự và phép so sánh. Ví dụ:

~~~cypher
WHERE person.createdAt < $afterCreatedAt
   OR (person.createdAt = $afterCreatedAt AND person.id < $afterId)
RETURN person.id AS id, person.name AS name, person.createdAt AS createdAt
ORDER BY person.createdAt DESC, person.id DESC
LIMIT $limit
~~~

Không được đổi `ORDER BY` mà vẫn giữ dấu `>` của truy vấn tăng dần; nếu làm vậy, cursor sẽ đi sai chiều hoặc lặp kết quả.

## 3. Chuẩn bị dữ liệu và index

Ví dụ sử dụng node `Person` có các property `id`, `status`, `name` và `createdAt`. Thời điểm `createdAt` được lưu dưới dạng Neo4j `LOCAL DATETIME`, tương ứng với `java.time.LocalDateTime` trong ví dụ Java.

Có thể tạo dữ liệu mẫu với `localdatetime()` để bảo đảm kiểu thời gian phù hợp:

~~~cypher
CREATE (person:Person {
    id: $personId,
    status: $status,
    name: $name,
    createdAt: localdatetime()
})
~~~

Trong ứng dụng thực tế, hãy đặt `createdAt` một lần khi tạo node và không sửa nó trong các lần cập nhật thông thường.

Định danh nên được bảo vệ bằng uniqueness constraint:

~~~cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (person:Person)
REQUIRE person.id IS UNIQUE
~~~

Có thể tạo composite index cho điều kiện lọc và trường sắp xếp chính:

~~~cypher
CREATE INDEX person_status_created_at IF NOT EXISTS
FOR (person:Person)
ON (person.status, person.createdAt)
~~~

Index giúp Neo4j tìm tập node theo `status` và điều kiện trên `createdAt` hiệu quả hơn trong nhiều trường hợp. Việc index có thể đáp ứng toàn bộ thứ tự `createdAt, id` hay không còn phụ thuộc phiên bản Neo4j, cấu trúc index và kế hoạch thực thi. Hãy kiểm tra bằng `EXPLAIN` và `PROFILE` trên dữ liệu có quy mô gần thực tế; không mặc định rằng chỉ cần tạo index là truy vấn chắc chắn tối ưu.

Các node thiếu `createdAt` không tham gia truy vấn mẫu. Nếu đó là dữ liệu hợp lệ trong domain, hãy xác định quy tắc sắp xếp rõ ràng hoặc bổ sung giá trị trước khi đưa chúng vào tập phân trang.

## 4. Tạo projection cho một dòng kết quả

Không nhất thiết phải tải toàn bộ entity graph nếu danh sách chỉ cần vài trường. Khai báo projection cho một dòng:

~~~java
import java.time.LocalDateTime;

public interface PersonCursorRow {
    String getId();
    String getName();
    LocalDateTime getCreatedAt();
}
~~~

Projection có `createdAt` và `id` vì service cần hai giá trị này để tạo cursor. Người dùng có thể chỉ nhìn thấy `name`, nhưng cursor phải giữ toàn bộ khóa sắp xếp.

## 5. Viết truy vấn cho trang đầu và trang tiếp theo

Trang đầu không có cursor. Tách truy vấn đầu tiên khỏi truy vấn tiếp theo giúp tránh điều kiện `OR $cursor IS NULL` trên mọi lần gọi và làm rõ logic seek.

Repository có thể khai báo hai method:

~~~java
import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (person:Person {status: $status})
        WHERE person.createdAt IS NOT NULL
          AND person.id IS NOT NULL
        RETURN person.id AS id,
               person.name AS name,
               person.createdAt AS createdAt
        ORDER BY person.createdAt ASC, person.id ASC
        LIMIT $limit
        """)
    List<PersonCursorRow> findFirstPage(
        @Param("status") String status,
        @Param("limit") int limit
    );

    @Query("""
        MATCH (person:Person {status: $status})
        WHERE person.createdAt IS NOT NULL
          AND person.id IS NOT NULL
          AND (person.createdAt > $afterCreatedAt
               OR (person.createdAt = $afterCreatedAt AND person.id > $afterId))
        RETURN person.id AS id,
               person.name AS name,
               person.createdAt AS createdAt
        ORDER BY person.createdAt ASC, person.id ASC
        LIMIT $limit
        """)
    List<PersonCursorRow> findNextPage(
        @Param("status") String status,
        @Param("afterCreatedAt") LocalDateTime afterCreatedAt,
        @Param("afterId") String afterId,
        @Param("limit") int limit
    );
}
~~~

Cả hai truy vấn đều trả các alias `id`, `name`, `createdAt` khớp với getter của `PersonCursorRow`. Trang đầu sắp xếp theo hai khóa; trang tiếp theo dùng chính hai khóa đó để xác định vị trí bắt đầu.

Giữ phần `WHERE` và `ORDER BY` nhất quán là điều bắt buộc. Nếu trang đầu dùng một bộ lọc nhưng trang tiếp theo dùng bộ lọc khác, hoặc nếu cursor được tạo theo thứ tự khác, kết quả phân trang sẽ không còn liên tục.

## 6. Lấy dư một dòng để biết còn trang sau

Keyset pagination thường không cần truy vấn `COUNT(*)` chỉ để biết có trang kế tiếp hay không. Hãy yêu cầu `pageSize + 1` dòng:

- Nếu số dòng trả về không vượt `pageSize`, đây là trang cuối.
- Nếu trả về `pageSize + 1`, có ít nhất một dòng tiếp theo.
- Chỉ trả `pageSize` dòng đầu cho client.
- Cursor tiếp theo phải lấy từ dòng cuối cùng được trả cho client, không lấy từ dòng dư.

Ví dụ service:

~~~java
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public record PersonCursor(LocalDateTime createdAt, String id) {}

public interface PersonCursorCodec {
    String encode(LocalDateTime createdAt, String id, String status);
    PersonCursor decode(String token, String expectedStatus);
}

PersonCursor cursor = cursorToken == null
    ? null
    : cursorCodec.decode(cursorToken, status);
int pageSize = validatePageSize(requestedPageSize);
int fetchSize = pageSize + 1;

List<PersonCursorRow> fetched = cursor == null
    ? personRepository.findFirstPage(status, fetchSize)
    : personRepository.findNextPage(
        status, cursor.createdAt(), cursor.id(), fetchSize
    );

boolean hasNext = fetched.size() > pageSize;
List<PersonCursorRow> items = hasNext
    ? new ArrayList<>(fetched.subList(0, pageSize))
    : fetched;

String nextCursor = null;
if (hasNext && !items.isEmpty()) {
    PersonCursorRow lastItem = items.get(items.size() - 1);
    nextCursor = cursorCodec.encode(lastItem.getCreatedAt(), lastItem.getId(), status);
}
~~~

Đây là luồng xử lý minh họa trong service; `PersonCursorCodec` và `validatePageSize` là thành phần ứng dụng tự định nghĩa, không phải API có sẵn của SDN. Codec cần kiểm tra cursor thuộc đúng bộ lọc `status` trước khi trả về khóa seek. `validatePageSize` cần từ chối số âm/0 và giới hạn kích thước tối đa theo chính sách API.

Nếu dùng dòng dư làm cursor, dòng đó sẽ bị bỏ qua ở trang tiếp theo vì truy vấn mới tìm strictly after cursor. Vì vậy, cursor phải được tạo từ dòng cuối thực sự được gửi đi.

## 7. Thiết kế cursor cho API

Một cursor cần chứa đủ khóa để tiếp tục truy vấn. Với ví dụ này, payload logic có thể gồm:

~~~json
{
  "createdAt": "2026-11-26T09:30:00",
  "id": "person-204"
}
~~~

API thường mã hóa payload thành chuỗi opaque, ví dụ Base64 URL-safe. Base64 chỉ là encoding, không bảo vệ tính toàn vẹn hoặc che giấu dữ liệu. Nếu client không được phép sửa khóa cursor, hãy ký payload bằng MAC hoặc dùng cơ chế token có xác thực phù hợp.

Cursor nên được ràng buộc với điều kiện lọc và thứ tự sắp xếp. Ví dụ, cursor được tạo cho `status = ACTIVE` không nên được tái sử dụng với `status = INACTIVE`. Có thể đưa filter, sort version và page size vào payload hoặc kiểm tra chúng cùng cursor ở server.

Khi giải mã cursor, cần xác thực cấu trúc, kiểu dữ liệu, giới hạn độ dài và phiên bản định dạng. Không dùng cursor như bằng chứng phân quyền; mọi request vẫn phải được xác thực và kiểm tra quyền truy cập dữ liệu.

Response có thể dùng một DTO tổng quát:

~~~java
import java.util.List;

public record CursorPage<T>(
    List<T> items,
    String nextCursor,
    boolean hasNext
) {}
~~~

Trang cuối trả `hasNext = false` và `nextCursor = null`. API keyset thường không cung cấp tổng số trang hoặc tổng số bản ghi vì việc đếm có thể tốn kém và không cần thiết cho trải nghiệm cuộn tiếp.

## 8. Xử lý dữ liệu thay đổi giữa các lần gọi

Keyset pagination tránh việc các dòng trước cursor bị dịch chuyển do insert/delete như offset pagination, nhưng không tự tạo snapshot nhất quán qua nhiều request.

Ví dụ:

- Một node mới được thêm với khóa sắp xếp lớn hơn cursor hiện tại có thể xuất hiện ở trang sau.
- Một node đã hiển thị bị xóa trước lần gọi tiếp theo sẽ không xuất hiện nữa.
- Nếu `createdAt` hoặc một khóa sắp xếp bị sửa, node có thể chuyển từ trước cursor sang sau cursor hoặc ngược lại, gây lặp hoặc bỏ sót.

Để giảm vấn đề, ưu tiên dùng khóa sắp xếp bất biến. Với feed cần giới hạn dữ liệu tại thời điểm bắt đầu, có thể chụp một watermark ở trang đầu, chẳng hạn thời điểm bắt đầu hoặc giá trị ID tối đa, rồi áp dụng cùng điều kiện watermark cho mọi trang. Watermark giới hạn các bản ghi mới hơn mốc đó nhưng không tạo snapshot tuyệt đối nếu dữ liệu cũ có thể được chèn trễ hoặc các property lọc/sắp xếp bị cập nhật.

Nếu yêu cầu nghiệp vụ cần snapshot nhất quán tuyệt đối qua nhiều trang, phải thiết kế cơ chế snapshot/version riêng; không nên cho rằng nhiều HTTP request sẽ tự chia sẻ cùng một transaction Neo4j.

## 9. Bộ lọc và thứ tự động

Các giá trị lọc như `status`, thời điểm cursor và ID nên được truyền bằng tham số Cypher. Không nối chuỗi trực tiếp từ dữ liệu client vào câu query.

Tên property và hướng sắp xếp không thể thay thế an toàn bằng một parameter value thông thường trong `ORDER BY`. Nếu API hỗ trợ nhiều kiểu sort, hãy whitelist các lựa chọn hợp lệ và dùng query/method tương ứng cho từng thứ tự, bảo đảm mỗi kiểu có predicate cursor đúng với chiều sắp xếp.

Với thứ tự nhiều trường, ví dụ `createdAt ASC, priority DESC, id ASC`, predicate phải mô tả đúng phép so sánh từ điển hỗn hợp: trường đầu lớn hơn, hoặc trường đầu bằng và trường thứ hai nhỏ hơn, hoặc hai trường đầu bằng và ID lớn hơn. Không dùng một dấu so sánh chung cho tất cả trường.

## 10. Tối ưu và xác minh truy vấn

Để keyset pagination hoạt động tốt ở dữ liệu lớn:

1. Bắt đầu từ nhãn node và điều kiện equality có chọn lọc.
2. Tạo index phù hợp với các property lọc và khóa sắp xếp chính.
3. Giữ cursor ngắn, gồm các giá trị scalar cần thiết.
4. Chỉ trả các cột mà màn hình và cursor cần.
5. Giới hạn page size để tránh tải quá nhiều node cùng lúc.
6. Dùng `EXPLAIN` để xem kế hoạch và `PROFILE` để đo DB hits, số dòng cùng các operator thực tế.
7. Đo cả trang đầu lẫn trang sâu với phân bố dữ liệu gần production.

Nếu một node có nhiều relationship và truy vấn cần lọc qua chúng, hãy kiểm tra cardinality của từng nhánh. Tránh tạo nhiều dòng trung gian rồi mới `DISTINCT` nếu có thể lọc sớm hoặc dùng `EXISTS`/subquery phù hợp. Keyset chỉ tối ưu cách định vị trang; nó không làm một pattern graph đắt đỏ trở nên rẻ tự động.

## 11. Keyset và offset: chọn theo nhu cầu

| Tiêu chí | Offset (`SKIP`/`LIMIT`) | Keyset (cursor) |
| --- | --- | --- |
| Đi đến trang số bất kỳ | Thuận tiện | Cần cursor của vị trí trước đó |
| Trang sâu trên tập lớn | Chi phí bỏ qua có thể tăng | Tìm từ khóa cursor, thường ổn định hơn với index phù hợp |
| Dữ liệu thay đổi giữa các lần gọi | Dễ dịch vị trí dòng | Ít bị ảnh hưởng bởi thay đổi trước cursor, nhưng không phải snapshot |
| Hiển thị tổng số trang | Thường kết hợp count query | Thường không cần count |
| Điều hướng ngược | Dễ tính offset | Cần cursor và thứ tự truy vấn ngược riêng |

Offset phù hợp với bảng nhỏ hoặc giao diện cần nhảy trực tiếp đến trang cụ thể. Keyset phù hợp với dữ liệu lớn, truy cập tuần tự và cuộn vô hạn. Có thể kết hợp hai chiến lược ở các màn hình khác nhau trong cùng ứng dụng.

## 12. Bài tập tự kiểm tra

1. Vì sao `SKIP` lớn có thể làm truy vấn tốn kém trên tập dữ liệu lớn?
2. Vì sao chỉ sắp xếp theo `createdAt` chưa đủ để tạo cursor ổn định?
3. Với thứ tự `createdAt ASC, id ASC`, hãy viết điều kiện `WHERE` cho trang tiếp theo.
4. Vì sao service nên lấy `pageSize + 1` dòng và tạo cursor từ dòng cuối đã trả cho client?
5. Cursor cần chứa và xác thực những thông tin nào ngoài khóa sắp xếp?
6. Keyset pagination có bảo đảm snapshot tuyệt đối khi node bị cập nhật giữa các lần gọi không?
7. Cần dùng `EXPLAIN` và `PROFILE` để xác minh điều gì sau khi tạo index?

Khi hoàn thành bài học, bạn cần thiết kế được cursor ổn định từ nhiều khóa sắp xếp, viết truy vấn Cypher trang đầu và trang tiếp theo, tích hợp chúng với repository/service SDN và hiểu các giới hạn khi graph thay đổi giữa những lần gọi. Đây là nền tảng để phân trang hiệu quả trên các tập dữ liệu Neo4j lớn.
