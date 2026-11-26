# Pageable, Sort và thứ tự ổn định giữa các trang

Trong **Spring Data Couchbase**, phân trang không chỉ là chuyển `page=0` thành `LIMIT 20 OFFSET 0`. Nếu truy vấn thiếu một thứ tự xác định, hai lần đọc liên tiếp có thể trả những hàng khác nhau dù dữ liệu không đổi. Ngay cả khi đã `ORDER BY`, nhiều document trùng giá trị sắp xếp vẫn có thể đổi vị trí giữa các trang nếu không có khóa phân xử. Khi dữ liệu đang được thêm, xóa hoặc sửa, `OFFSET` còn có thể làm một document xuất hiện hai lần hoặc bị bỏ sót.

Bài thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_COUCHBASE**. Trong kiến trúc tầng truy cập bằng Spring Data, repository, `CouchbaseTemplate` và SQL++, ta cần kết hợp ba vấn đề:

1. `Pageable`, `PageRequest` và `Sort` diễn đạt mong muốn phân trang ở phía Java.
2. SQL++ `ORDER BY`, `LIMIT`, `OFFSET` thực thi thứ tự trên tập kết quả Couchbase.
3. Thiết kế khóa sắp xếp duy nhất, cursor và index để dữ liệu qua nhiều trang vừa đúng vừa có hiệu năng chấp nhận được.

Kiến thức này liên hệ với bucket/scope/collection, entity mapping, projection, secondary index, TTL, CAS, giao dịch và cả API reactive. Phân trang **không tự bảo đảm một snapshot nhất quán qua nhiều HTTP request**; cần phân biệt bảo đảm về thứ tự với bảo đảm về tính mới và tính ổn định của dữ liệu.

## 1. Vì sao `LIMIT` và `OFFSET` chưa đủ?

Giả sử collection `shop`.`crm`.`customers` lưu khách hàng. Chức năng danh sách cần lấy 2 khách hàng mỗi trang:

~~~sql
SELECT META(c).id AS id, c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
LIMIT 2 OFFSET 0;
~~~

Và trang sau:

~~~sql
SELECT META(c).id AS id, c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
LIMIT 2 OFFSET 2;
~~~

Không có `ORDER BY`, SQL++ **không cam kết thứ tự bản ghi**. Kế hoạch index, song song hóa, dữ liệu và tài nguyên hệ thống có thể ảnh hưởng thứ tự hàng được trả. Vì vậy không có cơ sở để khẳng định trang đầu và trang thứ hai là hai lát cắt liên tiếp của cùng một thứ tự xác định.

Thêm `ORDER BY c.fullName` là cải thiện, nhưng chưa đủ nếu nhiều khách hàng cùng tên.

| Document key | `fullName` | `active` |
| --- | --- | --- |
| `customer::101` | An | true |
| `customer::102` | An | true |
| `customer::103` | Bình | true |
| `customer::104` | Bình | true |
| `customer::105` | Chi | true |
| `customer::106` | Dũng | true |

Với `ORDER BY c.fullName ASC`, hai hàng có tên `An` hòa nhau về thứ tự. Hệ thống có thể trả `101` trước `102` hoặc ngược lại. Một trang có ranh giới ngay giữa các hàng trùng tên có nguy cơ bị lặp hoặc hụt nếu thứ tự xử lý thay đổi giữa hai lần query.

**Nguyên tắc cốt lõi:** khóa sắp xếp của danh sách phân trang phải tạo một thứ tự **toàn phần** trên tập document đang xét. Thêm một thành phần duy nhất, ổn định như document key để phân xử cuối cùng:

~~~sql
SELECT META(c).id AS id, c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName ASC, META(c).id ASC
LIMIT 2 OFFSET 0;
~~~

Nếu `fullName` trùng nhau, `META(c).id` xác định vị trí giữa chúng. Document key duy nhất **trong một collection**; với query gộp nhiều nguồn hoặc collection cần xem lại tính duy nhất và thứ tự theo ngữ cảnh nguồn.

## 2. Ba mức độ ổn định phải phân biệt

| Mức độ | Cần điều kiện gì? | Có giải quyết insert/delete giữa hai request? |
| --- | --- | --- |
| **Thứ tự rõ ràng** | Có `ORDER BY` và hướng ASC/DESC | Không |
| **Thứ tự toàn phần** | Bộ khóa sắp xếp có thành phần phân xử duy nhất | Không |
| **Duyệt nhiều trang trên dữ liệu biến động** | Chọn offset hoặc cursor, quy tắc consistency và thay đổi dữ liệu | Chỉ giảm được một số hiện tượng, không có snapshot mặc định |

Ví dụ thứ tự toàn phần (`fullName ASC`, `id ASC`), kích thước trang 2:

~~~text
Trước khi có thay đổi:
A(101), B(102), C(103), D(104), E(105)

GET page=0, size=2 -> A, B

Một document X được chèn vào trước B:
A(101), X(099), B(102), C(103), D(104), E(105)

GET page=1, size=2, OFFSET 2 -> B, C
~~~

Hàng B bị lặp dù `ORDER BY` đã có khóa phụ duy nhất. Đây là **offset drift**: vị trí tương đối thay đổi giữa hai request. Thứ tự toàn phần chỉ xác định thứ tự của mỗi truy vấn; nó không đóng băng dữ liệu giữa các truy vấn.

Với cursor lấy từ hàng cuối đã hiển thị, ví dụ B, điều kiện “lớn hơn B” có thể bắt đầu tại C; document X chèn trước B sẽ không xuất hiện trong luồng duyệt này, nhưng B không bị lặp do chỉ số offset dịch chuyển. Cursor cũng không tạo snapshot và vẫn cần chính sách khi giá trị sort của document thay đổi.

## 3. `Pageable` mô tả phạm vi, `Sort` mô tả thứ tự

Spring Data Commons cung cấp các kiểu chính:

- `Pageable`: số trang, kích thước trang, offset và sort.
- `PageRequest`: một hiện thực phổ biến của `Pageable`.
- `Sort`: danh sách thuộc tính sắp xếp và hướng mỗi thuộc tính.
- `Sort.Order`: một tiêu chí cụ thể, ví dụ `fullName ASC`.
- `Page<T>`: kết quả trang gồm nội dung và tổng số phần tử.
- `Slice<T>`: nội dung trang và có trang tiếp theo hay không, không yêu cầu tổng.

Trang đầu có **chỉ số 0**:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.asc("fullName"),
    Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);
~~~

Một số giá trị:

~~~java
pageable.getPageNumber(); // 0
pageable.getPageSize();   // 20
pageable.getOffset();     // 0 (kiểu long)
pageable.getSort();       // fullName ASC, id ASC
~~~

Khi gọi `PageRequest.of(2, 20, sort)` thì offset bằng `2 × 20 = 40`. Đây là trang thứ ba theo cách đếm bắt đầu từ 0, bỏ qua 40 bản ghi đầu trong **tập kết quả được sắp xếp**.

`Sort.unsorted()` và `Pageable.unpaged()` là các giá trị tường minh khi không yêu cầu sắp xếp hoặc phân trang. Không truyền `null` để diễn đạt ý đó. Với danh sách phân trang thực tế, `Sort.unsorted()` thường không phù hợp nếu sản phẩm cần tái lập thứ tự.

### Nhiều cột và nhiều hướng

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 30, sort);
~~~

Nhu cầu: document mới nhất trước; nếu `createdAt` trùng thì ID tăng dần. Cần nhớ `id` là property `@Id`, có thể được lưu dưới dạng **document key**, nên phải kiểm tra Spring Data Couchbase chuyển `Sort.by("id")` thành SQL++ gì trên phiên bản đang dùng.

Đừng suy từ cú pháp Java rằng chắc chắn sẽ có `ORDER BY META(c).id`. Nếu cần bảo đảm tuyệt đối thứ tự theo document key, hãy kiểm tra query được sinh hoặc viết SQL++ tường minh trong custom repository.

## 4. Repository Spring Data Couchbase với `Pageable`

Một entity tối giản:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    private String fullName;
    private boolean active;
    private Instant createdAt;

    // Constructor và accessor phù hợp với mapping dự án.
}
~~~

Repository có thể cung cấp:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    Page<Customer> findByActiveTrue(Pageable pageable);

    Slice<Customer> findByActive(boolean active, Pageable pageable);

    List<Customer> findByActiveTrue(Sort sort);
}
~~~

Lời gọi:

~~~java
Pageable requested = PageRequest.of(
    0, 20, Sort.by("fullName").ascending()
);

Page<Customer> page = repository.findByActiveTrue(requested);
Slice<Customer> slice = repository.findByActive(true, requested);
~~~

Với `Page`, framework có thể cần truy vấn đếm tổng; `Slice` chỉ cần biết có hàng tiếp theo và thường dùng kỹ thuật lấy dư một hàng. Đó là **quyết định kiểu kết quả**, độc lập với yêu cầu thứ tự toàn phần. Cả hai vẫn cần sort ổn định.

Đối với `Page<T>`, metadata tổng không làm mọi trang trở thành một snapshot thống nhất. Chèn/xóa/TTL có thể làm tổng thay đổi giữa các request.

### Derived method có thứ tự tĩnh

Spring Data Commons cho phép đặt thứ tự trong tên method:

~~~java
List<Customer> findByActiveTrueOrderByCreatedAtDesc();
~~~

Mẫu này phù hợp nếu mọi caller đều cần cùng thứ tự và không phải phân trang theo yêu cầu. Với nhiều cách sắp xếp từ UI, tham số `Pageable` hoặc `Sort` giúp rõ hơn. Tuy vậy, thứ tự tĩnh `createdAt DESC` vẫn cần khóa phụ duy nhất nếu dùng để phân trang; tránh giả định timestamp không thể trùng.

## 5. Sắp xếp theo `@Field` và tên property Java

Giả sử entity có:

~~~java
import org.springframework.data.couchbase.core.mapping.Field;

@Field("display_name")
private String fullName;
~~~

Trong Spring Data, `Sort.by("fullName")` mô tả **property của domain model**. Tuy nhiên, hành vi áp dụng `@Field` và ánh xạ tên property sang đường JSON trong generated SQL++ có thể khác ở các đường truy vấn/phiên bản. Hãy kiểm tra query thực tế.

Khi viết SQL++ trực tiếp, phải dùng **tên lưu trong document**:

~~~sql
SELECT META(c).id AS id,
       c.display_name AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.display_name ASC, META(c).id ASC
LIMIT 20 OFFSET 0;
~~~

`AS fullName` quyết định tên khóa kết quả; `ORDER BY c.display_name` quyết định thứ tự bằng giá trị lưu. Alias không thay đổi field body.

**Đặc biệt:** nếu tạo `Sort` từ chuỗi do HTTP client gửi, không được ghép trực tiếp chuỗi đó thành SQL++. Hãy ánh xạ một **danh sách property được cho phép** sang các biểu thức SQL++ tường minh. Điều này vừa ngăn câu query ngoài ý muốn vừa giúp bảo đảm mọi sort đều có khóa phụ ổn định.

## 6. SQL++ tường minh: chuỗi sắp xếp dễ kiểm soát

Khi cần chắc chắn document key là khóa phân xử, query SQL++ trực tiếp là lựa chọn dễ kiểm tra:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.createdAt AS createdAt
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.createdAt DESC, META(c).id ASC
LIMIT $limit OFFSET $offset;
~~~

Tương ứng trong SDK:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

String statement = """
    SELECT META(c).id AS id,
           c.fullName AS fullName,
           c.createdAt AS createdAt
    FROM `shop`.`crm`.`customers` AS c
    WHERE c.active = TRUE
    ORDER BY c.createdAt DESC, META(c).id ASC
    LIMIT $limit OFFSET $offset
    """;

JsonObject params = JsonObject.create()
    .put("limit", 20)
    .put("offset", 40);

QueryResult result = cluster.query(
    statement,
    queryOptions().parameters(params)
);
~~~

Đây là đoạn minh họa bên trong một service có `Cluster` được cấu hình. `limit` và `offset` là **giá trị** nên được bind bằng query parameter. Tên bucket/scope/collection và biểu thức sort là **định danh/cú pháp**, không thể được bảo đảm an toàn bằng cách dùng một parameter thay cho chuỗi `ORDER BY`; hãy lấy chúng từ cấu hình đáng tin cậy và tập lựa chọn cố định.

### `@Query` kết hợp `Pageable`: chỉ một nơi tạo ORDER BY/LIMIT/OFFSET

Spring Data Couchbase có thể **tự thêm clause** sắp xếp và phân trang khi repository method có `Pageable` hoặc `Sort`. Ví dụ:

~~~java
import org.springframework.data.couchbase.repository.Query;

@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} AND active = $1")
Page<Customer> findActiveByQuery(boolean active, Pageable pageable);
~~~

Khi dùng kiểu method này, **không** đồng thời viết `ORDER BY`, `LIMIT` hoặc `OFFSET` trong chuỗi `@Query` rồi lại đưa `Pageable` vào. Tài liệu Spring Data Couchbase cảnh báo SQL++ có thể sai do framework thêm các clause trùng lặp.

Nếu cần sort bằng biểu thức đặc biệt như `META(c).id` mà đường `Sort` domain không tạo được, cân nhắc custom repository/SDK hoặc cơ chế query phù hợp đã được thử nghiệm, nơi **chính bạn** kiểm soát trọn chuỗi `ORDER BY` và `LIMIT/OFFSET`. Không khẳng định một property name bất kỳ trong `Sort` sẽ tự chuyển thành biểu thức SQL++ tùy ý.

## 7. Thứ tự toàn phần: trường hợp tên trùng và timestamp trùng

### Sắp theo tên

~~~sql
ORDER BY c.fullName ASC, META(c).id ASC
~~~

Ngay cả khi 50 người đều tên “An”, mỗi document có key khác nhau, nên thứ tự cặp (`fullName`, `id`) là xác định.

### Sắp theo thời điểm tạo

~~~sql
ORDER BY c.createdAt DESC, META(c).id ASC
~~~

`createdAt` thường không duy nhất do nhiều record có thể được tạo cùng mili-giây, import theo lô hoặc dùng thời gian mặc định. Đừng bỏ khóa ID chỉ vì thời gian có độ chính xác cao.

### Sắp theo giá trị nghiệp vụ có thể thay đổi

~~~sql
ORDER BY c.balance DESC, META(c).id ASC
~~~

Thứ tự trong **một truy vấn** xác định nếu `balance` có kiểu nhất quán và ID là khóa phụ. Nhưng `balance` có thể thay đổi giữa hai trang, làm document dịch chuyển. Vì thế khóa phân xử duy nhất giải quyết vấn đề **tie**, còn cursor và chính sách nhất quán xử lý một phần vấn đề **dữ liệu biến động**.

### Vì sao khóa phụ cần thật sự duy nhất?

`ORDER BY c.fullName, c.city` chưa chắc là thứ tự toàn phần nếu nhiều khách hàng trùng tên và cùng thành phố. Chỉ khi tổ hợp khóa là duy nhất **trong tập kết quả đang xét** mới tránh hoàn toàn tie.

Khi query có `JOIN` hoặc `UNNEST` tạo **nhiều row cho cùng document**, `META(c).id` cũng có thể trùng giữa các row. Lúc đó cần thêm khóa phân biệt từng row kết quả, chẳng hạn ID phần tử mảng/đối tượng liên quan, hoặc thiết kế lại query.

## 8. `NULL`, `MISSING` và kiểu dữ liệu ảnh hưởng thứ tự

Document database có schema linh hoạt: một số document có thể thiếu `createdAt`, có `createdAt: null` hoặc lưu nhầm kiểu string/number.

Couchbase SQL++ hỗ trợ tùy chọn sắp xếp null:

~~~sql
SELECT META(c).id AS id, c.createdAt AS createdAt
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.createdAt DESC NULLS LAST,
         META(c).id ASC
LIMIT 20;
~~~

Trong Couchbase SQL++ hiện hành, khi bỏ `NULLS FIRST/LAST`, mặc định `ASC` đưa `MISSING`/`NULL` lên trước và `DESC` đưa chúng về sau. `NULLS FIRST/LAST` giúp hợp đồng sort rõ ràng, nhưng **không biến `MISSING` thành `NULL`**; hai trạng thái vẫn có khác biệt.

Khi dùng keyset cursor cần đặc biệt cẩn thận:

- Điều kiện `c.createdAt > $lastCreatedAt` có thể không bao gồm document `MISSING` hoặc `NULL` như cách `ORDER BY` xử lý.
- Nếu field có nhiều kiểu JSON, thứ tự so sánh không đơn giản như so hai chuỗi.
- Dữ liệu kiểu timestamp lưu dạng chuỗi phải có **format chuẩn hóa** để thứ tự lexicographic tương ứng thứ tự thời gian, ví dụ ISO-8601 UTC có độ dài/cấu trúc thống nhất.
- Nếu UI yêu cầu không phân biệt hoa thường hoặc dấu, `Sort.Order.ignoreCase()` ở tầng Java không tự bảo đảm SQL++ sẽ dùng collation phù hợp ở mọi module. Cần định nghĩa rõ biểu thức như `LOWER(...)`, chuẩn hóa dữ liệu và kiểm tra index.

Một lựa chọn thực tế cho màn hình chỉ hỗ trợ khách hàng có tên hợp lệ:

~~~sql
WHERE c.active = TRUE
  AND c.fullName IS NOT MISSING
  AND c.fullName IS NOT NULL
~~~

Điều này giới hạn tập dữ liệu thay vì phải xử lý cursor qua cả hai trạng thái thiếu/null. Nếu tất cả bản ghi phải được hiển thị, hãy thiết kế **khóa sắp xếp chuẩn hóa** có fallback minh bạch và dùng **cùng biểu thức** trong `SELECT`, `ORDER BY`, điều kiện keyset và index.

### Sắp xếp chữ tiếng Việt có luôn theo bảng chữ cái người dùng mong muốn?

Không chắc. SQL++ so sánh chuỗi theo quy tắc collation của hệ thống, có thể khác sắp xếp ngôn ngữ tự nhiên của tiếng Việt, đặc biệt với ký tự có dấu, chữ hoa/thường và Unicode normalization. Nếu nghiệp vụ yêu cầu thứ tự theo ngôn ngữ, có thể tạo khóa tìm kiếm/sắp xếp đã chuẩn hóa theo chính sách ứng dụng và index khóa đó; hãy ghi rõ tiêu chuẩn để UI và backend không hiểu khác nhau.

## 9. Kiểm soát `Sort` từ HTTP: allowlist và khóa phụ

Giả sử API nhận `GET /customers?sort=name,asc&page=0&size=20`. Không nên cho người dùng truyền bất kỳ tên field hoặc biểu thức SQL++ nào; hãy chuyển lựa chọn công khai sang sort được cho phép.

~~~java
import org.springframework.data.domain.Sort;

public Sort toCustomerSort(String publicField, boolean descending) {
    String property = switch (publicField) {
        case "name" -> "fullName";
        case "created" -> "createdAt";
        default -> throw new IllegalArgumentException(
            "Unsupported sort field");
    };

    Sort.Direction direction = descending
            ? Sort.Direction.DESC
            : Sort.Direction.ASC;

    return Sort.by(new Sort.Order(direction, property))
            .and(Sort.by(Sort.Order.asc("id")));
}
~~~

Đây là mapper từ **field API công khai** sang property của entity. Dùng nó trong repository **sau khi đã kiểm chứng cách map `id` trong `Sort`**. Nếu đường repository không hỗ trợ sort document key đúng như mong muốn, hãy dùng custom SQL++ có danh sách biểu thức sắp xếp cố định, tránh tự động thêm `id` nhưng không thực thi được.

Nên giới hạn thêm:

- `page >= 0`; `size` có min/max hợp lý, ví dụ từ 1 đến 100.
- Kiểu sort cho từng field phải được định nghĩa; tránh `sort=orders[0].amount` tùy ý.
- Nếu có nhiều tenant/collection, predicate lọc quyền luôn được áp dụng.
- Giao diện cần biết thứ tự để hiển thị ổn định khi người dùng quay lại trang.

## 10. `OFFSET`: dễ dùng nhưng có chi phí trang sâu

Offset pagination dễ hiểu:

~~~sql
SELECT META(c).id AS id, c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName ASC, META(c).id ASC
LIMIT 20 OFFSET 200000;
~~~

Truy vấn này cần tìm một vị trí ở sâu trong thứ tự kết quả. Tùy index và optimizer, Query Engine/Index Service có thể phải xét một lượng lớn entries trước khi bỏ qua 200.000 hàng.

`LIMIT 20` chỉ hạn chế số hàng cuối cùng trả về, không luôn giới hạn số hàng hệ thống phải **quét, sắp xếp hoặc bỏ qua**.

Couchbase có thể **đẩy `LIMIT/OFFSET` xuống Index Service** khi điều kiện và `ORDER BY` phù hợp index. Pushdown không phải cam kết cho mọi query, nhất là khi có `JOIN`, `IntersectScan`, sort theo biểu thức không tương ứng index hoặc filter không thể đẩy xuống.

### Đếm tổng và phân trang là hai chi phí riêng

Trả `Page<T>` có thể khiến ứng dụng cần một query `COUNT` ngoài query dữ liệu; trả `Slice<T>` thường lấy thêm một hàng để biết `hasNext` mà không tính total. Tuy vậy, cả `Page` và `Slice` với offset lớn vẫn chịu cùng rủi ro truy vấn trang sâu.

Với UX “Tải thêm”, nên cân nhắc cursor/keyset; với UX cần nhảy thẳng đến trang số 500, offset có thể phù hợp hơn nhưng cần hạn mức và đo hiệu năng.

## 11. Keyset pagination: khóa trang theo giá trị đã thấy

**Keyset pagination** (seek pagination) không yêu cầu “bỏ qua N hàng”. Thay vào đó, nó tìm các row đứng **sau row cuối mà client đã hiển thị** theo cùng thứ tự sort.

### 11.1. Trang đầu với thứ tự tăng dần

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.fullName IS NOT MISSING
  AND c.fullName IS NOT NULL
ORDER BY c.fullName ASC, META(c).id ASC
LIMIT 21;
~~~

Ví dụ ứng dụng hiển thị 20 hàng và lấy dư 1 hàng để quyết định có trang tiếp theo. Cursor được tạo từ **hàng thứ 20 đã hiển thị**, không phải hàng thứ 21 nhìn trước. Giả sử:

~~~json
{
  "afterFullName": "Trần Minh",
  "afterId": "customer::42"
}
~~~

### 11.2. Trang tiếp theo

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.fullName IS NOT MISSING
  AND c.fullName IS NOT NULL
  AND (
      c.fullName > $afterFullName
      OR (
          c.fullName = $afterFullName
          AND META(c).id > $afterId
      )
  )
ORDER BY c.fullName ASC, META(c).id ASC
LIMIT 21;
~~~

Điều kiện được diễn giải theo thứ tự từ trái sang phải:

1. Mọi hàng có `fullName` lớn hơn `afterFullName` đều ở phía sau cursor.
2. Khi tên bằng nhau, chỉ lấy hàng có document key lớn hơn `afterId`.
3. Bộ khóa so sánh phải tương ứng chính xác với `ORDER BY`.
4. Cursor nên ràng buộc với **tenant, filter và sort đang sử dụng**; client thay điều kiện phải khởi tạo lại trang đầu.

`LIMIT 21` dành cho kích thước trang 20; nếu nhận 21 hàng thì `hasNext=true`, còn phần tử thứ 21 không được đưa vào nội dung hiển thị. Cursor trang sau lấy từ phần tử cuối trong **20 hàng thực tế trả cho client**.

### 11.3. Thứ tự giảm dần hoặc trộn hướng

Nếu `ORDER BY c.createdAt DESC, META(c).id DESC`, biểu thức sau cursor dùng **dấu `<`** cho cả hai khóa:

~~~sql
AND (
    c.createdAt < $afterCreatedAt
    OR (
        c.createdAt = $afterCreatedAt
        AND META(c).id < $afterId
    )
)
~~~

Nếu `ORDER BY c.fullName ASC, META(c).id DESC`, dấu phải khác nhau:

~~~sql
AND (
    c.fullName > $afterFullName
    OR (
        c.fullName = $afterFullName
        AND META(c).id < $afterId
    )
)
~~~

**Sai dấu ở khóa phân xử** có thể làm bỏ sót hoặc lặp những document cùng giá trị sort.

### 11.4. Khi nào keyset không tiện?

- UI yêu cầu nhảy trực tiếp đến một số trang bất kỳ.
- Sort theo biểu thức không có khóa ổn định hoặc không có index phù hợp.
- Filter/phân quyền thay đổi giữa các request.
- Nghiệp vụ cần duyệt một **snapshot bất biến**; keyset đơn thuần không tạo được snapshot đó.
- Trường sort có nhiều kiểu dữ liệu, `NULL`/`MISSING` và chưa quy định thứ tự chuẩn.

Keyset thường phù hợp cho feed, “Tải thêm”, duyệt nhiều bản ghi theo trình tự; cần đo trên workload thật trước khi khẳng định nó nhanh hơn offset ở mọi tình huống.

## 12. Ví dụ custom repository với cursor và SDK

Khi cần kiểm soát tuyệt đối `META(c).id`, một custom repository có thể thực hiện SQL++ và tự ánh xạ từng row sang DTO.

~~~java
public record CustomerCard(String id, String fullName, String email) {}

public record CustomerCursor(String lastName, String lastId) {}

public record CustomerSlice(
    java.util.List<CustomerCard> items,
    boolean hasNext,
    CustomerCursor nextCursor
) {}
~~~

Phần xử lý minh họa:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import java.util.List;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

// Phương thức trong lớp repository adapter có Cluster được cấu hình.
public CustomerSlice loadActive(
        Cluster cluster,
        int pageSize,
        CustomerCursor after) {

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("pageSize must be 1..100");
    }

    boolean nextPage = after != null;
    if (nextPage && (after.lastName() == null || after.lastId() == null)) {
        throw new IllegalArgumentException("Invalid cursor");
    }

    String predicate = nextPage ? """
        AND (
            c.fullName > $lastName
            OR (
                c.fullName = $lastName
                AND META(c).id > $lastId
            )
        )
        """ : "";

    String statement = """
        SELECT META(c).id AS id,
               c.fullName AS fullName,
               c.email AS email
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.active = TRUE
          AND c.fullName IS NOT MISSING
          AND c.fullName IS NOT NULL
        """ + predicate + """
        ORDER BY c.fullName ASC, META(c).id ASC
        LIMIT $limit
        """;

    JsonObject parameters = JsonObject.create()
        .put("limit", pageSize + 1);

    if (nextPage) {
        parameters.put("lastName", after.lastName());
        parameters.put("lastId", after.lastId());
    }

    QueryResult queryResult = cluster.query(
        statement, queryOptions().parameters(parameters));

    List<CustomerCard> fetched = queryResult.rowsAsObject()
        .stream()
        .map(row -> new CustomerCard(
            row.getString("id"),
            row.getString("fullName"),
            row.getString("email")))
        .toList();

    boolean hasNext = fetched.size() > pageSize;
    List<CustomerCard> visible = hasNext
        ? fetched.subList(0, pageSize)
        : fetched;

    CustomerCursor cursor = hasNext && !visible.isEmpty()
        ? new CustomerCursor(
            visible.get(visible.size() - 1).fullName(),
            visible.get(visible.size() - 1).id())
        : null;

    return new CustomerSlice(visible, hasNext, cursor);
}
~~~

Cú pháp SQL++ được ghép từ **hai nhánh cố định của ứng dụng**, không từ input người dùng. Mọi giá trị cursor đều được bind bằng named parameters. Các định danh keyspace/field trong query là cấu hình tin cậy.

Ví dụ cố ý dùng query với thứ tự tăng dần và loại các row có tên `MISSING`/`NULL` để điều kiện keyset dễ kiểm chứng. Trong production, cần bổ sung:

- Tenant và điều kiện quyền truy cập vào `WHERE`; cursor phải gắn với cùng filter.
- Token cursor có định dạng ổn định, xác thực và giới hạn kích thước; có thể encode, ký để ngăn sửa đổi không hợp lệ nếu cần.
- Chính sách xử lý trường tên sai kiểu hoặc trùng/đổi tên.
- Timeout, scan consistency, chỉ mục và error handling.
- Integration test chứng minh kết quả không trùng hoặc mất row do logic dấu so sánh khi dữ liệu đứng yên.

**Giới hạn:** mã minh họa không hứa giữ nguyên tập kết quả khi có document thay đổi vị trí sort, bị xóa hoặc chèn mới giữa các trang.

## 13. Thay đổi đồng thời, CAS, TTL và consistency

### Thứ tự xác định không đồng nghĩa snapshot

Giả sử `page 0` sắp theo `fullName` và `page 1` được tải sau một phút. Trong thời gian đó:

- Một customer mới có tên xếp trước cursor có thể **không xuất hiện** trong phần còn lại của keyset scan.
- Một customer đã đọc có tên bị đổi sang vị trí **sau cursor** có thể lại xuất hiện; nếu đổi sang trước cursor, nó có thể bị bỏ qua.
- Document hết hạn TTL hoặc bị xóa sẽ không còn xuất hiện.
- Query có mức scan consistency khác nhau có thể nhìn tập index entries khác nhau.

Điều này áp dụng ngay cả khi mỗi request có `ORDER BY c.fullName, META(c).id` hoàn toàn xác định.

### Có nên giữ CAS trong cursor?

Thường **không**. CAS là token dùng kiểm tra phiên bản của **một document** khi mutation, không phải khóa thứ tự và không phải snapshot token của cả tập kết quả. Cursor phân trang nên giữ giá trị sort (và khóa phân xử) tương ứng; không dùng CAS để so “hàng nào đứng sau”.

Nếu màn hình cho phép chỉnh sửa trực tiếp một hàng, có thể giữ CAS riêng cho **luồng cập nhật**, nhưng không nhầm nó với cursor thứ tự.

### Query consistency giải quyết gì?

Couchbase Query Service có những chính sách scan consistency, ví dụ `NOT_BOUNDED` và `REQUEST_PLUS` tùy API/phiên bản. `REQUEST_PLUS` có thể yêu cầu query chờ index phản ánh những mutation đã hoàn tất tới thời điểm request, giúp giảm tình trạng vừa ghi xong mà query chưa thấy dữ liệu.

Tuy nhiên, cấu hình này **không tạo snapshot chung** cho nhiều request phân trang cách nhau nhiều giây hoặc nhiều phút. Khi nghiệp vụ cần xử lý nhất quán một tập cố định, cân nhắc thiết kế export, snapshot vật hóa, dấu mốc dữ liệu, hoặc cơ chế transaction phù hợp thay vì mặc nhiên dựa trên nhiều lần query offset.

## 14. Index, sort và pagination pushdown

SQL++ phải có kế hoạch thực thi phù hợp với bộ lọc và thứ tự:

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName ASC, META(c).id ASC
LIMIT 20 OFFSET 1000;
~~~

Một index ứng viên cho điều kiện và sort theo tên:

~~~sql
CREATE INDEX ix_customer_active_name
ON `shop`.`crm`.`customers` (active, fullName);
~~~

Đây là **index ứng viên để thử**, chưa phải bảo đảm query được cover hoặc toàn bộ `ORDER BY` sẽ được index pushdown. Đặc biệt phải kiểm tra phần khóa phân xử `META(c).id` và field `email` nằm ở đâu trong kế hoạch.

Khi đọc `EXPLAIN`/query profile, hãy xem:

1. `IndexScan` hoặc scan nào được chọn? Có quét nhiều index entries không?
2. Có bước `Order` (sort tại Query Service) hay index đã cung cấp thứ tự cần thiết?
3. Có `Fetch` body không? `SELECT` ít field nhưng vẫn có thể cần fetch nếu index không cover.
4. `LIMIT/OFFSET` có được push down xuống Index Service hay phải xử lý sau scan/sort?
5. Predicate theo tenant, status, type discriminator đã được push down và có chọn lọc không?
6. Độ trễ thực tế ở trang 0, 100, 10.000 và trang sâu nhất mà UX cho phép là bao nhiêu?

Với sort theo `createdAt DESC`, index theo hướng ASC có thể không đáp ứng tối ưu việc order. Index tăng chiều rộng hoặc có biểu thức có thể cải thiện một số truy vấn nhưng tăng lưu trữ và chi phí cập nhật. Hãy thiết kế theo **tần suất sort thật sự** của sản phẩm, không tạo một index cho mọi tổ hợp sort tùy ý.

### Sort theo expression và index

Nếu muốn sắp xếp `LOWER(c.fullName)` hoặc trường đã chuẩn hóa, phải đo xem index có hỗ trợ đúng biểu thức sort và điều kiện lọc. Một index trên `fullName` nguyên bản không mặc nhiên khiến `ORDER BY LOWER(c.fullName)` trở thành index order.

## 15. Projection và `Page`/`Slice`: phân trang ít dữ liệu hơn

Để giảm payload, có thể trả các trường cần dùng thay vì entity đầy đủ:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName ASC, META(c).id ASC
LIMIT 20;
~~~

Ở đây:

- `SELECT` ít field giảm kích thước row.
- `ORDER BY` có khóa duy nhất làm thứ tự toàn phần.
- `LIMIT` giới hạn số hàng mỗi query.
- `Slice` có thể dùng look-ahead bằng `pageSize + 1` để biết còn hàng kế tiếp.
- `Page` có thể cần thêm query đếm tổng theo cùng điều kiện lọc.
- Index phù hợp quyết định khả năng tối ưu scan, sort và tránh `Fetch`.

Interface projection hoặc DTO của Spring Data có lợi về hợp đồng Java, nhưng **không tự bảo đảm SQL++ đã chọn ít field**. Hãy kiểm tra generated query và mapping, đặc biệt với `META(c).id`, alias, field `@Field` và nested properties.

Nếu trả entity đọc một phần rồi gọi `save`, có thể ghi thiếu dữ liệu. Projection dùng cho màn hình danh sách nên là read model; thao tác cập nhật cần đường riêng và CAS khi nghiệp vụ yêu cầu optimistic locking.

## 16. Reactive repository và phân trang

Reactive pipeline không thay đổi ý nghĩa `ORDER BY`, `LIMIT/OFFSET` hoặc cursor. Các quy tắc khóa phụ, nullability và scan consistency vẫn áp dụng.

Trong WebFlux:

- Dùng reactive query/repository/template mà phiên bản Spring Data Couchbase hỗ trợ.
- Không chuyển sang blocking query bằng `block()` trên event loop.
- Nếu UI dùng “Tải thêm”, trả `hasNext` và cursor hoặc dùng một cơ chế reactive slice được hỗ trợ; đừng giả định mọi phiên bản đều có cùng kiểu trả về `Mono<Page<T>>`/`Mono<Slice<T>>`.
- Áp dụng backpressure và giới hạn page size; reactive không cho phép trả hàng triệu rows mà không tính đến bộ nhớ và thời gian xử lý.
- Việc nhiều query chạy bất đồng bộ **không** bảo đảm thứ tự trả kết quả nếu ứng dụng gộp chúng sai thứ tự; thứ tự các row trong từng SQL++ query vẫn do `ORDER BY` quyết định.

Nếu dùng reactive SDK để thực hiện keyset pagination, hãy giữ cùng biểu thức sort và cursor giữa các request; kiểm tra cùng các ca biên như đường đồng bộ.

## 17. Các lỗi dễ mắc

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| Cùng dữ liệu nhưng mỗi lần trang trả thứ tự khác | Không có `ORDER BY` | Đặt thứ tự tường minh |
| Hàng trùng giữa hai trang dù không có ghi mới | Sort có nhiều giá trị trùng, thiếu khóa phụ | Thêm document key/khóa duy nhất cuối `ORDER BY` |
| Hàng trùng sau khi thêm record mới | Offset bị dịch giữa hai request | Xem xét keyset, quy định consistency |
| Keyset bỏ sót hàng trùng tên | Cursor chỉ giữ tên, thiếu document key | Giữ toàn bộ cặp khóa sort |
| Keyset sai khi sort DESC | Điều kiện sau cursor vẫn dùng `>` | Đổi dấu theo từng hướng sort |
| Sort `id` trên repository không như mong đợi | `@Id` là metadata, mapping Sort tùy đường query | Xem generated SQL++; dùng `META(c).id` tường minh |
| Field đặt `@Field("display_name")` sort sai | Dùng tên Java trong raw SQL++ | Dùng tên JSON lưu thực tế |
| Null/missing làm cursor sai | Predicate không tương thích `ORDER BY` | Chuẩn hóa kiểu/null, test dữ liệu biên |
| Page sâu chậm dù LIMIT nhỏ | Offset scan/sort nhiều hàng, index không phù hợp | `EXPLAIN`, keyset hoặc giới hạn page sâu |
| Lỗi query khi kết hợp `@Query` và `Pageable` | Tự đặt ORDER BY/LIMIT/OFFSET rồi framework thêm lần nữa | Chỉ một cơ chế tạo các clause |
| Kết quả vừa ghi chưa xuất hiện | Index scan consistency | Chọn consistency theo nghiệp vụ |
| Danh sách thay đổi qua nhiều trang | Insert/delete/update/TTL giữa các request | Thống nhất yêu cầu snapshot và chiến lược đọc |
| Thứ tự tên tiếng Việt khác mong muốn | Collation mặc định khác sắp xếp theo ngôn ngữ | Thiết kế normalized sort key |
| Người dùng yêu cầu sort field lạ | API nhận property/biểu thức tùy ý | Allowlist và validate sort |

## 18. Checklist thiết kế, kiểm thử và vận hành

1. **Định nghĩa bộ lọc:** tenant, quyền, type discriminator, active status và mọi điều kiện nghiệp vụ phải được giữ nguyên giữa các trang.
2. **Chọn khóa sort:** thứ tự nghiệp vụ + thành phần duy nhất, ưu tiên document key trong collection đơn nguồn.
3. **Quy định hướng:** ASC/DESC cho từng trường; với keyset, dấu so sánh phải tương ứng đúng.
4. **Xử lý dữ liệu thiếu:** `NULL`, `MISSING`, nhiều kiểu JSON, timestamp và Unicode phải có quy tắc rõ ràng.
5. **Giới hạn request:** page âm, page size không hợp lệ, offset quá sâu, sort ngoài allowlist.
6. **Xác minh Spring Data query:** đặc biệt `@Id` trong `Sort`, `@Field`, `@Query` ghép `Pageable` và filter loại document.
7. **Kiểm tra dữ liệu test trùng khóa:** ít nhất ba bản ghi có cùng `fullName` và nhiều bản ghi có cùng `createdAt`.
8. **Kiểm tra ranh giới trang:** dữ liệu 0, `size−1`, `size`, `size+1`, trang đầu/giữa/cuối và cursor cuối.
9. **Thử thay đổi đồng thời:** chèn trước cursor, xóa trước offset, đổi sort key, document TTL hết hạn.
10. **Thử consistency:** query ngay sau ghi, trong khi index chưa bắt kịp, kiểm tra chính sách mong muốn.
11. **Đo hiệu năng:** `EXPLAIN` và query profile cho trang đầu, offset sâu, cursor; xem `Order`, `Fetch`, index pushdown, độ trễ p95.
12. **Ổn định hợp đồng API:** ghi rõ sort/cursor, next-page token, cách reset pagination khi đổi bộ lọc và lỗi cursor không hợp lệ.

### Các ca kiểm tra cụ thể

Với page size 2 và tập có thứ tự (`fullName ASC`, `META().id ASC`):

~~~text
An/101
An/102
An/103
Bình/104
Chi/105
~~~

Kỳ vọng khi dữ liệu không đổi:

| Request | Nội dung | Trang tiếp theo |
| --- | --- | --- |
| Page 0, OFFSET 0 | An/101, An/102 | Có |
| Page 1, OFFSET 2 | An/103, Bình/104 | Có |
| Page 2, OFFSET 4 | Chi/105 | Không |
| Keyset sau An/102 | An/103, Bình/104 | Có |
| Keyset sau Bình/104 | Chi/105 | Không |

Các bài test bổ sung phải sửa dữ liệu **giữa hai request** và ghi nhận rằng một câu query riêng lẻ có thứ tự toàn phần vẫn không làm offset giữ vị trí cũ.

## 19. Bài tập thực hành

Xây dựng API `GET /customers` hỗ trợ hai chế độ:

- **Chế độ trang số:** `page=0&size=20&sort=name,asc`, dùng repository `Pageable`/`Sort` và trả kết quả được sắp xếp ổn định.
- **Chế độ “Tải thêm”:** `limit=20&after=<cursor>`, dùng SQL++ keyset với cặp `fullName` và `META(c).id`.

Yêu cầu triển khai:

1. Tạo ít nhất 30 document, có tên trùng và thời điểm tạo trùng.
2. Với đường repository, bật log truy vấn hoặc quan sát SQL++ thực tế để kiểm tra `Sort.by("id")` được ánh xạ ra document key đúng cách.
3. Viết custom SQL++ có `ORDER BY c.fullName ASC, META(c).id ASC`, `LIMIT` và `OFFSET` cho trang số.
4. Viết query keyset “sau tên + ID”, dùng `pageSize+1` để tính `hasNext`.
5. Cho phép sort theo `name` hoặc `created` từ API; chuyển qua allowlist, luôn thêm khóa phụ.
6. Tạo document thiếu tên, tên `null`, tên khác chữ hoa/chữ thường và Unicode có dấu; lựa chọn chính sách sort rõ ràng.
7. Chèn document trước ranh giới trang trong lúc duyệt; quan sát offset drift và so sánh keyset.
8. Đổi `fullName` của một document đã đọc để thấy keyset không phải snapshot.
9. Dùng `EXPLAIN`/profiling đánh giá index và chi phí sort/offset ở trang sâu.
10. Đặt câu hỏi sản phẩm: liệu người dùng cần nhảy đến trang bất kỳ hay chỉ cần “Tải thêm”?

### Câu hỏi tự kiểm tra

1. Vì sao `LIMIT/OFFSET` không kèm `ORDER BY` không phải phân trang ổn định?
2. Vì sao `ORDER BY fullName` vẫn chưa đủ nếu nhiều document trùng tên?
3. `Sort.by("id")` trong repository có luôn tương đương `ORDER BY META(c).id` không?
4. Thứ tự toàn phần có ngăn được offset drift khi document được chèn/xóa không?
5. Tại sao cursor của keyset phải giữ **cả** tên và ID?
6. Khi `ORDER BY createdAt DESC, id ASC`, dấu so sánh ở điều kiện cursor sau cùng là gì?
7. `NULLS LAST` giải quyết điều gì và chưa giải quyết điều gì với `MISSING`/`NULL`?
8. Vì sao `LIMIT 20 OFFSET 200000` vẫn có thể tốn chi phí?
9. `REQUEST_PLUS` có khiến nhiều trang cách nhau một phút thành một snapshot không?
10. Khi nào cần dùng keyset, khi nào vẫn nên dùng offset?

## 20. Tài liệu chính thức

- [Spring Data Couchbase — Couchbase repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): `PagingAndSortingRepository`, `Page`/`Slice` và lưu ý `@Query` có `Pageable`.
- [Spring Data — Defining query methods](https://docs.spring.io/spring-data/couchbase/reference/repositories/query-methods-details.html): `Pageable`, `Sort`, `Page`/`Slice` và các hạn chế tham số.
- [Couchbase SQL++ — ORDER BY clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/orderby.html): thứ tự, `ASC`/`DESC`, `NULLS FIRST/LAST` và các kiểu JSON.
- [Couchbase SQL++ — LIMIT clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/limit.html): giới hạn số hàng.
- [Couchbase SQL++ — OFFSET clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/offset.html): cơ chế bỏ qua hàng.
- [Couchbase Server — Index pushdowns](https://docs.couchbase.com/server/current/indexes/index_pushdowns.html): index ordering và điều kiện pushdown pagination.
- [Couchbase Server — Early filters, order, and pagination](https://docs.couchbase.com/server/current/indexes/early-filters-and-pagination.html): các phương án tối ưu query/index khi pushdown trực tiếp không áp dụng.

Cần đối chiếu chức năng `@Query`, `Sort`, mapping `@Id` và query/index optimization với **phiên bản Spring Data Couchbase, Couchbase Java SDK và Couchbase Server thực tế** của ứng dụng. Hành vi tối ưu là kết quả của query plan, không thể kết luận chỉ từ kiểu `Pageable`.

> **Ghi nhớ:** `Pageable` xác định **muốn lấy trang nào**; `Sort` xác định **muốn xếp theo gì**; `ORDER BY` có khóa phân xử duy nhất tạo **thứ tự toàn phần trong mỗi truy vấn**. Khi duyệt nhiều trang trên dữ liệu biến động, offset vẫn có thể trôi; keyset thường giảm rủi ro theo vị trí, nhưng không tự tạo snapshot. Kiểm chứng query thực tế, khóa sort và index trước khi cam kết kết quả ổn định.
