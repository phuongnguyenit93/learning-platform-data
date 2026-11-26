# Bí danh trường và ánh xạ kết quả SQL++ tùy chỉnh

Trong **Spring Data Couchbase**, câu SQL++ có thể trả về document đầy đủ, một tập trường, object lồng nhau, biểu thức tính toán hoặc giá trị vô hướng. Mỗi cách chọn dữ liệu tạo ra một **hình dạng JSON kết quả** khác nhau. Nếu bí danh trường (field alias) không khớp với kiểu Java được dùng để tiếp nhận kết quả, ứng dụng có thể gặp getter trả `null`, DTO mất trường, document key bị thiếu hoặc lỗi chuyển đổi kiểu.

Bài học thuộc chương **Chiếu và phân trang**, trong phạm vi xây dựng tầng truy cập Couchbase bằng Spring Data với entity mapping, repository, `CouchbaseTemplate` và SQL++. Trọng tâm là hiểu **SQL++ thực sự trả ra những khóa nào**, phân biệt kết quả dành cho entity với kết quả tùy chỉnh cho projection/DTO, rồi kiểm chứng quy tắc ánh xạ trên phiên bản Spring Data Couchbase đang sử dụng.

Sau bài học, bạn có thể:

- Phân biệt `SELECT *`, `SELECT c.*`, `SELECT field AS alias` và `SELECT RAW`.
- Ánh xạ trường Couchbase lưu theo `snake_case` sang thuộc tính Java `camelCase` bằng alias tường minh.
- Lấy document key qua `META()` mà không nhầm với trường `id` trong body.
- Chọn giữa interface projection, DTO/record, kết quả vô hướng và mapper thủ công từ Couchbase Java SDK.
- Xử lý `MISSING`, `NULL`, nested object, mảng, phép tính tổng hợp và alias trùng.
- Kết hợp alias với phân trang, index, CAS và kiểm thử tích hợp.

## 1. Ví dụ xuyên suốt

Giả sử bucket `shop`, scope `crm` và collection `customers` chứa document có key `customer::42`:

~~~json
{
  "full_name": "Trần Minh",
  "email_address": "minh@example.test",
  "active": true,
  "address": {
    "city": "Đà Nẵng",
    "street": "Đường A"
  },
  "orders": [
    { "orderId": "O-1001", "total": 750000 }
  ],
  "_class": "com.example.Customer"
}
~~~

`_class` ở đây minh họa trường phân loại document mà Spring Data có thể sử dụng; giá trị thực tế tùy vào cấu hình của dự án. **Document key `customer::42` là metadata, không tự nằm trong JSON body**.

Entity Spring Data có thể khai báo tên lưu trữ khác tên thuộc tính Java:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Customer {
    @Id
    private String id;

    @Field("full_name")
    private String fullName;

    @Field("email_address")
    private String email;

    private boolean active;
    private Address address;

    // Constructor, accessor phục vụ cơ chế mapping của ứng dụng.
}
~~~

`@Field("full_name")` làm cho thuộc tính Java `fullName` được lưu dưới key JSON `full_name`. Khi viết SQL++ thủ công, ta truy cập **tên trường lưu thực tế** như `c.full_name`, rồi dùng `AS fullName` nếu muốn row có khóa `fullName`.

Giả sử API danh sách cần record:

~~~java
public record CustomerCard(
        String id,
        String fullName,
        String email,
        String city
) {}
~~~

Mục tiêu của câu query sẽ là trả một object như sau:

~~~json
{
  "id": "customer::42",
  "fullName": "Trần Minh",
  "email": "minh@example.test",
  "city": "Đà Nẵng"
}
~~~

## 2. Hai loại bí danh trong SQL++

~~~sql
SELECT c.full_name AS fullName,
       c.email_address AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Có hai vai trò khác nhau:

1. `AS c` trong `FROM` đặt **bí danh nguồn document**, dùng để phân biệt nguồn và truy cập đường dẫn `c.field`, `c.address.city` hoặc `META(c).id`.
2. `AS fullName`, `AS email` trong `SELECT` đặt **tên khóa đầu ra** của mỗi row JSON. Đây là tên mà code Java hoặc converter có thể cần đọc.

Kết quả:

~~~json
[
  {
    "fullName": "Trần Minh",
    "email": "minh@example.test"
  }
]
~~~

Alias chỉ áp dụng cho **kết quả câu query**; nó không đổi tên field đã lưu trong Couchbase. Nó cũng không tự thay đổi annotation `@Field` của entity.

### Alias ngầm định và alias tường minh

SQL++ thường lấy thành phần cuối của đường dẫn field làm tên ngầm định:

~~~sql
SELECT c.full_name, c.address.city
FROM `shop`.`crm`.`customers` AS c;
~~~

Hai khóa đầu ra tương ứng là `full_name` và `city`. Nhưng biểu thức tính toán như `UPPER(c.full_name)` hoặc `COUNT(1)` có thể nhận alias tự sinh dạng `$1`. Không nên dựa vào tên tự sinh để ánh xạ DTO.

Hãy dùng alias tường minh khi có đổi tên trường, nested path, biểu thức tính toán, aggregate, metadata hoặc hai trường dễ trùng tên. Với tên alias chứa khoảng trắng, dấu gạch nối hay từ khóa dành riêng, SQL++ cần cú pháp định danh escape phù hợp; trong hợp đồng Java, thường nên chọn alias đơn giản và ổn định như `customerName`.

## 3. Hình dạng kết quả: `SELECT *`, `SELECT c.*`, `SELECT` có alias và `RAW`

Bốn truy vấn dưới đây không tương đương đối với mapper.

### 3.1. `SELECT *`: body được bọc bằng tên nguồn

~~~sql
SELECT *
FROM `shop`.`crm`.`customers` AS c
WHERE META(c).id = "customer::42";
~~~

Result row có dạng:

~~~json
{
  "c": {
    "full_name": "Trần Minh",
    "email_address": "minh@example.test",
    "active": true,
    "address": { "city": "Đà Nẵng", "street": "Đường A" },
    "orders": [],
    "_class": "com.example.Customer"
  }
}
~~~

Giá trị `orders` được rút gọn trong ví dụ. Nếu dùng Java SDK `rowsAsObject()`, phải truy cập `row.getObject("c")` để đọc body; `row.getString("full_name")` tại root sẽ không khớp.

### 3.2. `SELECT c.*`: field body ở root

~~~sql
SELECT c.*
FROM `shop`.`crm`.`customers` AS c
WHERE META(c).id = "customer::42";
~~~

Kết quả:

~~~json
{
  "full_name": "Trần Minh",
  "email_address": "minh@example.test",
  "active": true,
  "address": { "city": "Đà Nẵng", "street": "Đường A" },
  "orders": [],
  "_class": "com.example.Customer"
}
~~~

Các field của body được trải ra root; document key và CAS **không tự xuất hiện** thành field JSON `id`/`cas`. `SELECT c.*` vẫn lấy các trường body, chưa giải quyết yêu cầu chỉ trả một vài trường.

### 3.3. `SELECT expr AS alias`: row object do ứng dụng chủ động thiết kế

~~~sql
SELECT META(c).id AS id,
       c.full_name AS fullName,
       c.email_address AS email,
       c.address.city AS city
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Result:

~~~json
{
  "id": "customer::42",
  "fullName": "Trần Minh",
  "email": "minh@example.test",
  "city": "Đà Nẵng"
}
~~~

Đây là hình dạng phù hợp để tự ánh xạ sang `CustomerCard`; cũng là shape cần kiểm chứng nếu dùng Spring Data interface hoặc DTO projection.

### 3.4. `SELECT RAW`: row là giá trị, không phải object có tên khóa

~~~sql
SELECT RAW c.email_address
FROM `shop`.`crm`.`customers` AS c
WHERE META(c).id = "customer::42";
~~~

Kết quả ở cấp tập rows:

~~~json
[
  "minh@example.test"
]
~~~

`RAW` (các từ khóa tương đương `ELEMENT` và `VALUE`) bỏ lớp object chứa alias và chỉ áp dụng cho **một biểu thức**. Không thể dùng nó với danh sách nhiều biểu thức hoặc `*` theo cách tương tự `SELECT field1, field2`.

| Biểu thức SELECT | Một row tiêu biểu | Kiểu mapper hợp lý |
| --- | --- | --- |
| `SELECT * FROM ... AS c` | `{"c": {"full_name": "..."}}` | Đọc object lồng dưới khóa `c` |
| `SELECT c.* FROM ... AS c` | `{"full_name": "..."}` | Đọc object body tại root |
| `SELECT c.full_name AS fullName` | `{"fullName": "..."}` | Mapper object, DTO/projection |
| `SELECT RAW c.full_name` | `"Trần Minh"` | Mapper scalar |
| `SELECT COUNT(1) AS total` | `{"total": 42}` | Mapper object chứa giá trị số |

**Quy tắc:** trước khi chọn API chuyển đổi, hãy xác nhận **một row là object hay scalar** và các khóa trong object đó có tên gì.

## 4. Alias nào khớp với thuộc tính Java?

Giả sử interface projection:

~~~java
public interface CustomerNameView {
    String getFullName();
    String getEmail();
}
~~~

Và record:

~~~java
public record CustomerNameDto(String fullName, String email) {}
~~~

Truy vấn có kết quả phù hợp về tên khóa:

~~~sql
SELECT c.full_name AS fullName,
       c.email_address AS email
FROM `shop`.`crm`.`customers` AS c;
~~~

Ở đây cần phân biệt **bốn tên**:

| Tầng | Ví dụ |
| --- | --- |
| Tên field lưu trong JSON | `full_name` |
| Thuộc tính Java entity | `fullName` |
| Tên getter/record component | `getFullName()` / `fullName` |
| Tên khóa trả bởi SQL++ | `AS fullName` tạo key `fullName` |

Việc đặt `AS fullName` làm kết quả dễ đối chiếu với DTO. Tuy nhiên, **không có nghĩa mọi bản Spring Data Couchbase và mọi dạng repository query đều tự tạo được class/record DTO từ kết quả này**. Cách Spring Data dùng entity metadata, converter, constructor và tên alias cần được kiểm thử trên đúng phiên bản.

### Trùng tên từ nhiều biểu thức

Nếu một document đơn hàng có cả `customer.name` và `seller.name`:

~~~sql
SELECT o.customer.name AS customerName,
       o.seller.name AS sellerName
FROM `shop`.`crm`.`orders` AS o;
~~~

Dùng `AS` độc lập giúp tránh hai giá trị đều rơi vào tên ngầm định `name`. Đối với JOIN hoặc nhiều nguồn, bí danh nguồn như `c`, `o` càng cần rõ ràng. Quy ước tốt là **mỗi biểu thức trong một row có alias duy nhất** và mỗi thuộc tính DTO tương ứng một alias.

## 5. Document key, CAS, TTL và type discriminator

### 5.1. Key nằm trong `META(c).id`

~~~sql
SELECT META(c).id AS id,
       c.full_name AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

`c.id` chỉ đọc **field `id` của body** nếu field đó tồn tại. `META(c).id` là document key. Hai giá trị có thể khác nhau, nên không được thay thế cho nhau bằng suy đoán.

### 5.2. CAS là metadata, không phải field hiển thị thông thường

Couchbase dùng CAS cho cập nhật có kiểm soát đồng thời. SQL++ có thể chọn metadata:

~~~sql
SELECT META(c).id AS id,
       META(c).cas AS cas,
       c.full_name AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Muốn sử dụng CAS cho write path, phải xác minh **kiểu biểu diễn, độ chính xác khi chuyển đổi số và quy tắc truyền lại CAS** trên Server/SDK thực tế. Không lấy một giá trị CAS đã bị làm tròn khi chuyển qua kiểu số trung gian để cập nhật dữ liệu. Khi có document key, KV get/mutation thường là đường API trực tiếp để dùng CAS.

TTL/expiration cũng là metadata riêng, không tự có trong DTO chỉ vì trả ID và tên. Nếu tác vụ quản trị cần TTL, phải đọc theo API/metadata được phiên bản đang chạy hỗ trợ.

### 5.3. Lọc loại entity trong collection dùng chung

Spring Data có thể lưu thông tin phân loại entity, thường liên quan trường `_class`. Truy vấn repository dành cho một entity cần lọc đúng loại document để tránh nhận dữ liệu của entity khác trong cùng collection.

Nếu viết `@Query` tùy chỉnh với SQL++ tối thiểu, đừng mặc nhiên cho rằng điều kiện type discriminator sẽ được tự gắn vào mọi câu query. Đọc SQL++ thực tế đã gửi và bổ sung filter thích hợp cho model của dự án.

## 6. SQL++ tường minh kết hợp Couchbase Java SDK

Đây là cách dễ kiểm soát khi muốn map **bất kỳ row tùy chỉnh** nào sang DTO/record.

### 6.1. Câu query có alias và tham số

~~~sql
SELECT META(c).id AS id,
       c.full_name AS fullName,
       c.email_address AS email,
       IFMISSINGORNULL(c.address.city, "") AS city
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = $active
ORDER BY c.full_name, META(c).id
LIMIT $limit;
~~~

`IFMISSINGORNULL` chỉ là lựa chọn nghiệp vụ minh họa: biến cả `MISSING` và `NULL` thành chuỗi rỗng. Nếu API cần giữ khác biệt giữa thiếu và null, không dùng fallback như vậy.

### 6.2. Chuyển row sang record bằng `rowsAsObject()`

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import java.util.List;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public record CustomerCard(
        String id, String fullName, String email, String city) {}

// Phương thức minh họa nằm trong lớp truy cập dữ liệu đã có Cluster.
public List<CustomerCard> findActiveCards(Cluster cluster, int limit) {
    String statement = """
        SELECT META(c).id AS id,
               c.full_name AS fullName,
               c.email_address AS email,
               IFMISSINGORNULL(c.address.city, "") AS city
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.active = $active
        ORDER BY c.full_name, META(c).id
        LIMIT $limit
        """;

    JsonObject parameters = JsonObject.create()
            .put("active", true)
            .put("limit", limit);

    QueryResult result = cluster.query(
            statement,
            queryOptions().parameters(parameters));

    return result.rowsAsObject().stream()
            .map(row -> new CustomerCard(
                    row.getString("id"),
                    row.getString("fullName"),
                    row.getString("email"),
                    row.getString("city")))
            .toList();
}
~~~

Đây là các **đoạn khai báo và phương thức minh họa**; hãy đặt record, phương thức, import vào những class/file Java phù hợp trong ứng dụng.

Giải thích:

- `Cluster.query(...)` thực hiện câu SQL++; `QueryResult.rowsAsObject()` trả danh sách `JsonObject` khi row là object.
- `row.getString("fullName")` đọc **alias đầu ra**. Gọi `row.getString("full_name")` sẽ không khớp với truy vấn này.
- `queryOptions().parameters(...)` bind giá trị dữ liệu an toàn; không cần nối chuỗi để đưa `active` và `limit` vào câu SQL++.
- Bucket/scope/collection và tên field là **định danh**, không nên lấy input tùy ý rồi gắn vào SQL++. Chúng phải đến từ cấu hình tin cậy với cú pháp escape phù hợp.
- Nếu có yêu cầu field bắt buộc, kiểm tra sự hiện diện, kiểu và giá trị trước khi tạo record; đừng chỉ dựa vào việc method trả `String`.

Phương án này thích hợp với result row có biểu thức, alias phức tạp hoặc shape mà khả năng DTO projection trực tiếp của Spring Data Couchbase chưa được xác minh.

## 7. Phân biệt `MISSING` và `NULL` trong quá trình ánh xạ

Document có thể:

- Có `email_address` với một chuỗi.
- Có `email_address: null`.
- Không có key `email_address` (SQL++ đánh giá là `MISSING`).

Xét query:

~~~sql
SELECT c.email_address AS email,
       IFMISSINGORNULL(c.email_address, "(chưa có)") AS displayEmail
FROM `shop`.`crm`.`customers` AS c;
~~~

Một row có field `email` là `NULL` sẽ chứa `email: null`. Nếu nguồn là `MISSING`, key `email` có thể vắng khỏi row. Nhưng `displayEmail` sẽ có giá trị fallback trong cả hai tình huống.

Với `JsonObject`, hãy dùng `row.containsKey("email")` để kiểm tra sự hiện diện của khóa, sau đó kiểm tra giá trị khi khóa có mặt. Nếu chỉ dùng `getString("email")` mà không kiểm tra, hai tình huống có thể bị quy về cùng giá trị Java `null`.

Các hàm SQL++ phục vụ fallback khác nhau:

| Hàm | Xử lý `MISSING` | Xử lý `NULL` |
| --- | --- | --- |
| `IFMISSING(expr, fallback)` | Có fallback | Giữ `NULL` |
| `IFNULL(expr, fallback)` | Không thay `MISSING` | Có fallback |
| `IFMISSINGORNULL(expr, fallback)` | Có fallback | Có fallback |

Chọn hàm theo **hợp đồng dữ liệu**, không chỉ theo sự tiện lợi của mapper. Nếu dữ liệu gốc là số, đừng dùng fallback kiểu chuỗi làm DTO nhận sai loại JSON.

## 8. Object lồng nhau và mảng cần kiểu kết quả phù hợp

### DTO phẳng từ nested path

~~~sql
SELECT META(c).id AS id,
       c.full_name AS fullName,
       c.address.city AS city
FROM `shop`.`crm`.`customers` AS c;
~~~

Row:

~~~json
{"id": "customer::42", "fullName": "Trần Minh", "city": "Đà Nẵng"}
~~~

Cấu trúc này phù hợp với `record CustomerCity(String id, String fullName, String city)`.

### DTO lồng nhau

~~~sql
SELECT META(c).id AS id,
       c.full_name AS fullName,
       {"city": c.address.city} AS address
FROM `shop`.`crm`.`customers` AS c;
~~~

Row:

~~~json
{
  "id": "customer::42",
  "fullName": "Trần Minh",
  "address": {"city": "Đà Nẵng"}
}
~~~

Mapper tường minh có thể dùng `row.getObject("address")` rồi đọc `city`. Nếu ứng dụng chọn interface projection lồng nhau, cần kiểm tra framework có tạo đúng proxy con và query có lấy thêm field ngoài yêu cầu hay không.

### Mảng kết quả

~~~sql
SELECT META(c).id AS id,
       ARRAY o.orderId FOR o IN c.orders END AS orderIds
FROM `shop`.`crm`.`customers` AS c;
~~~

Row minh họa:

~~~json
{
  "id": "customer::42",
  "orderIds": ["O-1001"]
}
~~~

Đây là mảng JSON; DTO nên biểu diễn bằng `List<String>` (hoặc kiểu thích hợp khác), không ép thành một chuỗi. Kiểm tra dữ liệu thiếu `orders` và độ lớn mảng để tránh trả payload quá lớn.

## 9. Truy vấn aggregate và giá trị vô hướng

Không phải truy vấn nào cũng phải tạo entity hoặc DTO nhiều trường.

~~~sql
SELECT COUNT(1) AS total
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Kết quả:

~~~json
[
  {"total": 42}
]
~~~

Đọc với SDK khi row là object:

~~~java
QueryResult result = cluster.query("""
    SELECT COUNT(1) AS total
    FROM `shop`.`crm`.`customers` AS c
    WHERE c.active = TRUE
    """);

long total = result.rowsAsObject().get(0).getLong("total");
~~~

Nếu dùng `SELECT RAW COUNT(1)`, row là một số; cần API giải mã scalar thích hợp, ví dụ `result.rowsAs(Long.class)` trong Java SDK tương thích, thay vì `rowsAsObject()`.

Với `SUM`/`AVG`, hãy xem kiểu JSON thực tế, `NULL`, giới hạn số, độ chính xác và yêu cầu nghiệp vụ. Không nên ép số tiền sang kiểu dấu phẩy động rồi giả định chính xác tuyệt đối. Đặt alias rõ ràng như `totalAmount` thay vì phụ thuộc tên ngầm định.

## 10. Spring Data `@Query`: lúc nào trả entity, lúc nào trả view?

### Truy vấn dùng để tái tạo entity

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} AND active = $1")
    List<Customer> findActiveCustomers(boolean active);
}
~~~

`#{#n1ql.selectEntity}` được Spring Data Couchbase thiết kế để chọn các field/metadata cần thiết cho **entity đầy đủ**, thường gồm document ID và CAS. `#{#n1ql.filter}` thêm điều kiện phân loại entity theo mapping của Spring Data.

Không dùng cấu trúc `selectEntity` rồi khẳng định query chỉ tải vài trường. Ngược lại, không dùng một `SELECT` chỉ lấy ba cột mà yêu cầu framework tạo entity đầy đủ và sau đó lưu ngược, vì dễ gặp field thiếu và ghi đè dữ liệu ngoài ý muốn.

### Truy vấn tùy chỉnh trả interface hoặc DTO

Một result row có alias như:

~~~sql
SELECT META(c).id AS id,
       c.full_name AS fullName,
       c.email_address AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

có thể tương ứng interface:

~~~java
public interface CustomerListView {
    String getId();
    String getFullName();
    String getEmail();
}
~~~

Tuy nhiên, khả năng `@Query` trả trực tiếp interface projection/DTO record **phụ thuộc phiên bản, đường query và converter của Spring Data Couchbase**. Spring Data Commons mô tả các dạng projection chung, nhưng không bảo đảm mọi SQL++ custom row luôn được materialize thành bất kỳ class nào.

Trước khi dùng ở production, cần kiểm tra:

1. `getId()` nhận đúng document key qua `META(c).id AS id`.
2. `getFullName()` đọc được trường nguồn `full_name` đã alias thành `fullName`.
3. Dạng DTO/record được dựng đúng constructor và kiểu tham số.
4. `NULL`, `MISSING`, nested object, mảng và biểu thức tính toán có quy tắc rõ.
5. Custom query có lọc đúng loại document trong collection dùng chung.
6. SQL++ thực sự gửi lên Server có đúng projection mong muốn.
7. Cùng đường truy cập đồng bộ hoặc reactive được dùng trong ứng dụng.

Nếu mapper tự động không hỗ trợ result shape, hãy dùng custom repository/SDK mapper hoặc cơ chế template đã được kiểm chứng bằng test. Khi đó code chuyển đổi rõ hơn và việc chẩn đoán lỗi đơn giản hơn.

## 11. `CouchbaseTemplate` và reactive API không đổi nghĩa alias

`CouchbaseTemplate` quản lý nhiều thao tác truy cập và ánh xạ document qua Spring Data; `ReactiveCouchbaseTemplate` cung cấp biến thể reactive. Chúng hữu ích để dùng converter và cấu hình collection có sẵn, nhưng cần xác minh **API truy vấn nào xử lý entity, API nào cho phép tùy chỉnh row/DTO** ở phiên bản đang dùng.

Reactive repository hoặc SDK reactive không tự làm SQL++ trả ít field hơn. Việc giảm payload xuất phát từ `SELECT`, còn việc không phải đọc body document có thể liên quan đến covering index. Với WebFlux, nên giữ pipeline reactive và tránh chặn thread bằng `block()` không đúng ngữ cảnh.

Các luồng cập nhật dựa trên CAS, TTL hay đọc ngay sau ghi cần chọn API và consistency phù hợp; một projection DTO chỉ phục vụ đọc không tự cung cấp đầy đủ metadata hay cam kết consistency.

## 12. Bí danh và phân trang

Ví dụ API trả 20 khách hàng mỗi trang:

~~~sql
SELECT META(c).id AS id,
       c.full_name AS fullName,
       c.email_address AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.full_name, META(c).id
LIMIT $pageSize OFFSET $offset;
~~~

Các điểm cần chú ý:

- `ORDER BY` dùng biểu thức nguồn `c.full_name`; bí danh `fullName` dùng cho output row.
- `META(c).id` làm tiêu chí phụ khi nhiều khách hàng trùng tên.
- `LIMIT`/`OFFSET` có thể được bind giá trị qua SDK/query API.
- Offset lớn có thể đắt vì Query Engine cần xử lý nhiều hàng trước khi trả trang; danh sách dài có thể dùng keyset pagination theo cặp tên và document key.
- Dữ liệu thêm/xóa trong lúc lật trang có thể làm offset trôi. Alias không tự tạo snapshot nhất quán.
- Tính mới của kết quả sau ghi liên quan đến query scan consistency; cần chọn theo yêu cầu ứng dụng.

## 13. Alias không đồng nghĩa với index cover

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.full_name AS fullName,
       c.email_address AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.full_name, META(c).id
LIMIT 20;
~~~

Query chỉ trả ít trường có thể vẫn phải `Fetch` document từ Data Service. Nếu secondary index chứa dữ liệu đủ cho filter, sort và projection, Query Engine **có thể** dùng covering index và tránh một số bước đọc document. Xem `EXPLAIN`, `covers` và `Fetch` thay vì suy luận từ tên DTO hoặc alias.

Index rộng giúp vài truy vấn nhưng làm tăng lưu trữ và chi phí ghi. Đo số bản ghi quét, response bytes, p95 latency và write overhead trước khi thay đổi index.

| Điều muốn chứng minh | Bằng chứng |
| --- | --- |
| API trả đúng shape | JSON row thực tế và test mapper |
| Payload ít trường | Câu SQL++ `SELECT` thực tế, kích thước response |
| Truy vấn có thể tránh đọc document | Kế hoạch `EXPLAIN`/profiling, `covers`/`Fetch` |
| Truy vấn ổn định qua phân trang | Test dữ liệu trùng khóa sắp xếp và thay đổi đồng thời |
| Đúng dữ liệu ngay sau ghi | Test consistency của query/read path |

## 14. Lỗi thường gặp và hướng khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `row.getString("fullName")` trả null | Query chỉ chọn `full_name` | Thêm `AS fullName`; xem raw JSON row |
| `row.getString("id")` không có giá trị | Chỉ `SELECT c.*`, key không nằm trong body | Chọn `META(c).id AS id` |
| Kết quả có wrapper `{"c": {...}}` | Dùng `SELECT *` với nguồn `AS c` | Chọn `c.*` hoặc danh sách biểu thức |
| `rowsAsObject()` không phù hợp | Dùng `SELECT RAW` tạo scalar | Chọn phương thức đọc scalar |
| Trường `city` không hiện diện | `address.city` là `MISSING` | Quy định fallback hoặc nullable |
| Một trong hai `name` biến mất | Có thể trùng tên ngầm định từ nhiều nguồn | Đặt alias khác nhau |
| DTO mapping lỗi | Kiểu/alias/constructor/converter không tương thích | Kiểm thử trên đúng phiên bản hoặc mapper thủ công |
| Row khớp DTO nhưng query chậm | Không có covering index, sort/filter tốn công | `EXPLAIN` và đo workload |
| Sai loại entity | `@Query` thiếu discriminator filter | Thêm điều kiện lọc loại phù hợp |
| Đọc CAS thành giá trị không an toàn | Ép kiểu làm mất độ chính xác | Dùng metadata/CAS API phù hợp |

### Những suy luận cần tránh

- **“Alias thay đổi dữ liệu lưu”** — alias trong `SELECT` chỉ đặt tên ở result row.
- **“`SELECT *` giống `SELECT c.*`”** — một dạng bọc nguồn, một dạng trải body fields ra root.
- **“DTO Java khớp tên là chắc chắn Spring Data map được”** — tùy phiên bản và cơ chế query, phải test.
- **“Chỉ trả ba field nên không còn truy cập document”** — cần xem index và kế hoạch thực thi.
- **“Projection đủ thông tin để update”** — projection thường thiếu field và metadata; không nên lưu như entity đầy đủ.

## 15. Quy trình áp dụng và kiểm thử

1. **Định nghĩa hợp đồng đầu ra:** các tên key, kiểu dữ liệu, field bắt buộc/tùy chọn và metadata cần thiết.
2. **Đối chiếu mapping entity:** `@Field`, `@Id`, discriminator và tên trường lưu trong document.
3. **Thiết kế SQL++:** alias tường minh, kết quả object hay scalar, quy tắc `NULL`/`MISSING`, query parameters.
4. **Chạy query trực tiếp:** quan sát raw JSON row và xác minh ID, nested path, alias, kiểu số.
5. **Chọn đường mapping:** entity converter cho entity đầy đủ; projection/DTO có integration test; SDK/custom mapper cho row tùy chỉnh cần kiểm soát chính xác.
6. **Kiểm tra dữ liệu biên:** field thiếu, `null`, sai kiểu, hai field trùng tên, ID body khác document key và mảng lớn.
7. **Kiểm tra pagination:** sort ổn định với khóa phụ, giới hạn số hàng và consistency phù hợp.
8. **Kiểm tra quyền:** query có thể truy cập đúng scope/collection, DTO công khai không có dữ liệu nhạy cảm.
9. **Đánh giá index:** `EXPLAIN` và số đo từ workload thật trước khi tạo index mới.
10. **Đóng gói test:** dùng phiên bản Server, Couchbase SDK và Spring Data Couchbase tương ứng môi trường sản xuất.

### Bài tập thực hành

Xây API `GET /customers/active` trả dữ liệu:

~~~json
{
  "id": "customer::42",
  "fullName": "Trần Minh",
  "email": "minh@example.test",
  "city": "Đà Nẵng"
}
~~~

Yêu cầu:

- Document lưu `full_name`, `email_address` và `address.city`, còn key ở metadata.
- Viết SQL++ có `META(c).id` và alias tường minh cho từng trường.
- Tạo trường hợp document đầy đủ, thiếu `address`, và `email_address: null`.
- Quy định rõ trường nào cần fallback; viết mapper từ `rowsAsObject()` sang `CustomerCard`.
- Thử cùng dữ liệu với `SELECT *`, `SELECT c.*` và `SELECT RAW c.email_address` để quan sát khác biệt shape.
- Sắp xếp tên rồi ID, giới hạn 20 hàng; xem `EXPLAIN` để biết có `Fetch` hay không.
- Nếu thử repository trả DTO trực tiếp, ghi nhận kết quả integration test và phiên bản dependency cụ thể.

Câu hỏi tự kiểm tra:

1. `AS c` ở `FROM` và `AS fullName` ở `SELECT` có vai trò nào?
2. Vì sao `c.id` không phải lúc nào cũng bằng document key?
3. Khi dùng `SELECT RAW COUNT(1)`, result có còn khóa `total` không?
4. Nếu `@Field("full_name")`, SQL++ tự viết nên chọn `c.fullName` hay `c.full_name`?
5. Vì sao DTO mapping tự động cần integration test riêng cho Spring Data Couchbase?
6. Tại sao `SELECT` ít trường chưa chứng minh được Query Engine không đọc document?

## 16. Tài liệu tham khảo chính thức

- [Couchbase SQL++ — SELECT Clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/selectclause.html): alias, `SELECT *`, `SELECT RAW` và tên trường kết quả.
- [Couchbase SQL++ — Conditional Functions for Unknowns](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/condfununknown.html): `IFMISSING`, `IFNULL`, `IFMISSINGORNULL`.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): `QueryResult`, `rowsAsObject()` và parameter binding.
- [Spring Data Couchbase — Couchbase Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): `@Query`, `#n1ql.selectEntity`, `#n1ql.filter`.
- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Id`, `@Field`, entity converter.
- [Spring Data — Projections](https://docs.spring.io/spring-data/couchbase/reference/repositories/projections.html): cơ chế projection chung; cần đối chiếu với module và phiên bản dùng thực tế.

> **Ghi nhớ:** Alias là **hợp đồng tên khóa của row SQL++**. `SELECT` quyết định shape và payload; `META()` cung cấp document key/metadata; converter hoặc mapper quyết định cách dựng đối tượng Java. Kiểm chứng ba tầng đó trước khi tối ưu hoặc dùng kết quả cho tác vụ nghiệp vụ quan trọng.
