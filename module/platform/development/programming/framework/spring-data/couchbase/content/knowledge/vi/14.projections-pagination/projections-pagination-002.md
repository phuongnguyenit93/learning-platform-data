# Projection theo interface và DTO theo khả năng hỗ trợ thực tế

Trong ứng dụng dùng **Spring Data Couchbase**, repository thường trả về entity đại diện cho toàn bộ document. Nhưng API danh sách có thể chỉ cần ID, tên và email; báo cáo cần vài giá trị thống kê; còn màn hình chi tiết mới cần đối tượng đầy đủ. **Projection** là cách mô tả một *góc nhìn dữ liệu* phù hợp với từng chức năng.

Điều cần hiểu chính xác là: **Spring Data Commons mô tả nhiều hình thức projection, còn cách Spring Data Couchbase thực thi truy vấn và ánh xạ kết quả phải được kiểm chứng trên phiên bản đang dùng**. Việc một phương thức repository khai báo kiểu trả về nhỏ hơn không tự chứng minh rằng Couchbase chỉ đọc và gửi về từng ấy trường.

Bài học thuộc chương **Chiếu và phân trang**, trong phạm vi xây dựng tầng truy cập Couchbase bằng Spring Data (document mapping, repository, CouchbaseTemplate và SQL++), tập trung vào ba câu hỏi:

1. Khi nào nên chọn **interface projection** (closed, nested, open, dynamic)?
2. Khi nào nên chọn **DTO/record**, và đâu là các điều kiện cần thử nghiệm trước khi cho repository trả DTO trực tiếp?
3. Làm sao chứng minh truy vấn Couchbase thực sự chỉ lấy các trường cần thiết và việc ánh xạ đúng cả ID, giá trị thiếu và dữ liệu lồng nhau?

## 1. Bắt đầu từ một document cụ thể

Giả sử ứng dụng dùng bucket `shop`, scope `crm`, collection `customers`; document key là `customer::42`:

~~~json
{
  "fullName": "Trần Minh",
  "email": "minh@example.test",
  "active": true,
  "address": {
    "city": "Đà Nẵng",
    "street": "Đường A"
  },
  "preferences": {
    "language": "vi",
    "promotions": false
  },
  "orders": [
    { "code": "O-1001", "total": 750000 }
  ]
}
~~~

Entity được ánh xạ bằng Spring Data Couchbase:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class Customer {
    @Id
    private String id;

    private String fullName;
    private String email;
    private boolean active;
    private Address address;

    // Constructor, getter/setter và các field khác theo nhu cầu.
}

public class Address {
    private String city;
    private String street;

    // Getter/setter.
}
~~~

Ở đây `id` là **document key**, không nhất thiết được lưu trong body JSON; Spring Data quản lý ánh xạ ID qua metadata. Mẫu này bỏ qua cấu hình bucket/scope/collection để tập trung vào projection; dự án cần chỉ định collection tương ứng qua cấu hình hoặc annotation thích hợp.

Yêu cầu nghiệp vụ:

| Điểm sử dụng | Trường cần trả | Kiểu dữ liệu hợp lý |
| --- | --- | --- |
| Danh sách khách hàng | ID, họ tên, email | Closed interface hoặc DTO |
| Lựa chọn thành phố | Tên, thành phố | Nested interface hoặc DTO phẳng |
| API công khai | ID, tên hiển thị | DTO/record định nghĩa hợp đồng rõ ràng |
| Chỉnh sửa đầy đủ | Entity, metadata/CAS theo nghiệp vụ | Entity hoặc thao tác cập nhật có kiểm soát |
| Thống kê `COUNT` | Một số nguyên | Scalar result, không cần entity |

Không nên dùng cùng một kiểu đầy đủ cho mọi mục đích chỉ vì repository mặc định trả `Customer`.

## 2. Phân biệt khả năng Spring Data với hiệu quả ở Couchbase

Có ba tầng cần đánh giá riêng:

- **Hình dạng Java:** consumer nhận proxy interface, DTO/record hay entity.
- **Payload truy vấn:** câu SQL++ có `SELECT` những cột cần dùng hay chọn toàn bộ document.
- **Đường thực thi:** Query Engine có thể đọc bằng secondary index bao phủ (*covering index*) hay phải `Fetch` document; đối với truy cập theo key có thể cân nhắc KV/sub-document.

| Phương án | Lợi ích chính | Không được mặc nhiên suy ra |
| --- | --- | --- |
| Closed interface projection | Getter rõ ràng, giảm trường lộ ra trong code | Repository Couchbase đã tự động sinh `SELECT` tối thiểu |
| Nested interface projection | Truy cập cấu trúc lồng nhau theo interface | Chỉ đúng field con được tải từ Couchbase |
| Open interface projection (SpEL) | Tính trường hiển thị từ đối tượng nguồn | Có thể tối ưu query theo danh sách getter |
| DTO/record trả trực tiếp từ repository | Kiểu dữ liệu độc lập, bất biến nếu dùng record | Mọi đường query đều ánh xạ DTO giống nhau |
| Entity → DTO trong service | Hợp đồng API rõ, dễ kiểm soát mapping | Giảm dữ liệu Couchbase gửi về |
| SQL++ `SELECT` tường minh + mapping kiểm chứng | Kiểm soát chính xác kết quả câu query | Query Engine chắc chắn không đọc body document |

**Nguyên tắc làm việc:** thiết kế projection theo API trước, rồi quan sát SQL++ thực tế, mapping thực tế và kế hoạch `EXPLAIN` trước khi kết luận đã tối ưu hiệu năng.

## 3. Closed interface projection: điểm bắt đầu đơn giản

**Closed projection** chỉ khai báo các getter ánh xạ trực tiếp tới thuộc tính của entity.

~~~java
public interface CustomerListView {
    String getId();
    String getFullName();
    String getEmail();
}
~~~

Một repository có thể khai báo:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    List<CustomerListView> findByActiveTrue();
}
~~~

Khi gọi:

~~~java
List<CustomerListView> views =
        customerRepository.findByActiveTrue();

for (CustomerListView view : views) {
    System.out.println(view.getId() + ": " + view.getFullName());
}
~~~

Theo mô hình chung của Spring Data, framework dựng đối tượng triển khai interface/proxy tại thời gian chạy. Getter phải trùng **tên thuộc tính Java** của entity: `getFullName()` đọc `fullName`, không được tùy ý đổi thành `getName()` rồi kỳ vọng hệ thống hiểu.

### Những gì được và chưa được bảo đảm

- **Được:** chữ ký của `CustomerListView` giới hạn các accessor mà consumer có thể dùng qua kiểu này.
- **Cần xác minh:** câu query repository sinh ra có chọn riêng `id`, `fullName`, `email` hay vẫn lấy nhiều field để ánh xạ.
- **Cần xác minh:** khi `id` là document key, Couchbase mapping có đưa ID vào projection đúng cách không. Một truy vấn SQL++ viết tay có thể phải dùng `META(c).id` và alias thích hợp.
- **Cần xác minh:** projection từ câu query tùy biến hoặc đường KV theo ID có được xử lý giống truy vấn dẫn xuất hay không. Đường truy cập theo document key có thể đi qua KV thay vì SQL++.

Không nên chỉ đổi chữ ký `Customer` sang `CustomerListView` và coi hiệu quả truyền tải dữ liệu là đã được chứng minh.

### Tránh nhầm projection với interface mà entity đã triển khai

Spring Data chỉ coi những kiểu đứng **ngoài hệ phân cấp của entity** là projection chuyên biệt. Nếu `Customer` trực tiếp `implements SomeView` và phương thức repository trả về `SomeView` như một supertype của entity, framework có thể vẫn materialize entity đầy đủ. Dùng interface projection độc lập khi mục tiêu là tạo view riêng.

### Tránh override phương thức gốc để ép projection

Phương thức như `findById(String id)` đã được định nghĩa trong repository cơ sở và có đường thực thi riêng. Đổi kiểu trả về ở phương thức override, hoặc khai báo một chữ ký trùng cơ sở, không phải cách đáng tin cậy để yêu cầu projection.

Hãy tạo phương thức query riêng như `findByEmail(String email)`, `findByActiveTrue()` hoặc thực hiện custom query có hợp đồng rõ ràng, rồi kiểm thử với Spring Data Couchbase đang dùng.

## 4. Nested projection: tiện ở Java, cần thận trọng với dữ liệu lồng nhau

Spring Data Commons cho phép một getter trả về projection con:

~~~java
public interface CustomerCityView {
    String getFullName();
    AddressCityView getAddress();

    interface AddressCityView {
        String getCity();
    }
}
~~~

Nếu đối tượng nguồn có `address`, lời gọi `getAddress()` có thể tạo tiếp proxy cho `AddressCityView`. Điều này làm API sử dụng thuận tiện và không cho caller thấy `street` qua interface con.

Tuy nhiên, nested projection **không bảo đảm** query tối ưu đến mức chỉ đọc `address.city`. Một số đường ánh xạ có thể phải lấy cả trường `address`, thậm chí materialize document trước khi tạo proxy. Với API lớn, nên kiểm tra payload và thời gian truy vấn, hoặc dùng SQL++ chọn trường lồng nhau rồi ánh xạ sang DTO phẳng:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.address.city AS city
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Phản hồi thích hợp để ánh xạ về kiểu phẳng:

~~~json
{
  "id": "customer::42",
  "fullName": "Trần Minh",
  "city": "Đà Nẵng"
}
~~~

Cách này đặc biệt hữu ích khi client chỉ cần một phần nhỏ của object lồng nhau và không cần giữ cấu trúc entity.

## 5. Getter nullable và hàm mặc định trên interface

Trong model document linh hoạt, một thuộc tính có thể `null` hoặc không có trong JSON (SQL++ gọi là `MISSING`). Spring Data Commons hỗ trợ một số kiểu bao giá trị nullable, trong đó có `java.util.Optional`:

~~~java
import java.util.Optional;

public interface CustomerContactView {
    String getFullName();
    Optional<String> getEmail();
}
~~~

Khi dữ liệu được framework ánh xạ đúng, getter kiểu `Optional` cho phép caller xử lý vắng dữ liệu một cách tường minh.

Nếu cần trường hiển thị được tính **chỉ từ các getter đã khai báo**, có thể dùng `default method`:

~~~java
public interface CustomerBadgeView {
    String getFullName();
    String getEmail();

    default String getLabel() {
        return getFullName() + " <" + getEmail() + ">";
    }
}
~~~

`getLabel()` không phải field lưu trong JSON; đây là logic hiển thị trong Java. Vì nó dùng các getter sẵn có, cách này dễ suy luận hơn biểu thức truy cập toàn bộ entity.

**Cẩn trọng với dữ liệu thiếu:** `Optional` giải quyết một phần bài toán null-safety ở tầng Java, nhưng không xóa khác biệt của `NULL` và `MISSING` trong SQL++. Đối với DTO có constructor hoặc record với trường bắt buộc, cần thử trường thiếu và giá trị không đúng kiểu. Không dùng primitive như `int` hoặc `boolean` cho những giá trị mà nguồn dữ liệu có thể `null` nếu chưa quy định fallback.

## 6. Open projection và giới hạn tối ưu hóa

**Open projection** dùng SpEL (thường qua `@Value`) để tạo giá trị dẫn xuất:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerDisplayView {
    @Value("#{target.fullName + ' (' + target.email + ')'}")
    String getDisplayName();
}
~~~

Biểu thức `target` có thể truy cập nhiều thuộc tính của đối tượng nguồn; Spring Data không thể suy ra chắc chắn tập field tối thiểu chỉ từ một vài getter. Vì thế **không nên hứa hẹn tối ưu truy vấn** cho open projection.

So sánh:

| Giải pháp | Tính dễ hiểu | Tối ưu trường truy cập |
| --- | --- | --- |
| Closed getter `getFullName()` | Cao | Framework biết thuộc tính cần dùng, nhưng Couchbase vẫn phải xác minh |
| `default getDisplayName()` từ các getter | Cao | Không cần truy cập field ngoài những getter đã khai báo |
| `@Value("#{target...}")` | Linh hoạt | Không thể mặc nhiên suy ra giới hạn field |
| Chọn và tính biểu thức bằng SQL++ | Rõ dữ liệu server trả | Cần kiểm tra cú pháp, index và chi phí thực thi |

SpEL cũng tạo thêm điểm cần bảo trì. Với logic tổng hợp phức tạp, hãy cân nhắc service/mapper hoặc tính toán ở SQL++ khi có lý do rõ ràng.

## 7. Dynamic projection: cùng điều kiện tìm, nhiều kiểu trả về

Spring Data Commons hỗ trợ tham số `Class<T>` để chọn projection lúc gọi:

~~~java
import java.util.List;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    <T> List<T> findByActive(boolean active, Class<T> type);
}
~~~

Ý tưởng sử dụng:

~~~java
List<CustomerListView> compact =
        repository.findByActive(true, CustomerListView.class);

List<Customer> complete =
        repository.findByActive(true, Customer.class);
~~~

Cách này có ích khi điều kiện lọc giống nhau nhưng các use case cần hình dạng dữ liệu khác nhau. Tuy vậy, không nên thay các phương thức rõ ràng bằng dynamic projection chỉ để giảm số chữ trong repository: sự khác biệt về mapping, index, trách nhiệm dữ liệu và performance có thể khó phát hiện hơn.

**Lưu ý tham số:** Spring Data nhận diện `Class<T>` có kiểu generic trùng kiểu trả về là tham số lựa chọn projection; giá trị đó thường **không còn sẵn để bind như một tham số query thông thường**. Nếu thật sự muốn truyền một đối tượng `Class` làm dữ liệu lọc, phải khai báo đúng kiểu query parameter (ví dụ `Class<?>` ở trường hợp phù hợp), tránh nhầm với projection selector.

**Lưu ý phiên bản:** Spring Data Commons mô tả dynamic projection; cần integration test cho chính đường query, kiểu kết quả và phiên bản Spring Data Couchbase của dự án.

## 8. Class-based projection: DTO và Java record

DTO mô tả dữ liệu trả về bằng một **kiểu thực** thay vì proxy interface. Với Java hỗ trợ record:

~~~java
public record CustomerCard(
        String id,
        String fullName,
        String email
) {}
~~~

Điểm mạnh:

- Bất biến ở mức thành phần của record, có constructor rõ ràng.
- Dễ dùng làm hợp đồng service/API và dễ kiểm thử giá trị.
- Không phụ thuộc vào proxy cho các lời gọi getter.
- Tránh để controller trả entity mang quá nhiều dữ liệu.

Cần phân biệt **hai tình huống khác nhau**.

### 8.1. Phương án chắc chắn dễ kiểm soát: ánh xạ projection hoặc entity sang DTO

~~~java
import java.util.List;

public List<CustomerCard> listActiveCards(CustomerRepository repository) {
    return repository.findByActiveTrue()
            .stream()
            .map(view -> new CustomerCard(
                    view.getId(),
                    view.getFullName(),
                    view.getEmail()))
            .toList();
}
~~~

Đây là phép chuyển đổi Java tường minh. Nó cho phép kiểm soát giá trị và đổi tên trường mà không phải dựa vào khả năng constructor mapping của repository.

**Giới hạn:** tốc độ và số byte Couchbase đã đọc vẫn phụ thuộc truy vấn cung cấp `CustomerListView`. Ánh xạ entity đầy đủ sang DTO nhỏ cũng không tự giảm số field được tải.

### 8.2. Repository trả DTO trực tiếp: chỉ dùng khi đã chứng minh hỗ trợ

Spring Data Commons mô tả class-based projection/record dựa vào constructor. Mẫu biểu diễn ý định thường gặp:

~~~java
// Mẫu cần xác minh bằng integration test trên phiên bản Couchbase sử dụng.
public interface CustomerCardRepository
        extends CouchbaseRepository<Customer, String> {

    List<CustomerCard> findByActiveTrue();
}
~~~

**Không coi mẫu trên là cam kết mọi cấu hình Couchbase đều hỗ trợ trực tiếp.** Hành vi phụ thuộc vào đường query, cơ chế ánh xạ, converter, metadata và phiên bản Spring Data Couchbase. Tài liệu Couchbase minh họa rõ interface projection; tài liệu Spring Data Commons mô tả DTO projection ở mức framework chung. Với kết quả SQL++ tùy biến, ánh xạ constructor/record có thể khác với truy vấn dẫn xuất.

Nếu chọn DTO trực tiếp, phải xác nhận:

1. Repository khởi tạo thành công; phương thức thực thi không ném lỗi conversion/mapping.
2. Giá trị `id`, `fullName`, `email` được dựng đúng từ document hoặc result row.
3. Constructor nhận đúng tên/kiểu dữ liệu, kể cả alias khác tên field lưu.
4. Các trường `NULL`, `MISSING` và nested structure được xử lý đúng.
5. Truy vấn thực tế không vô tình tải cả document.
6. Cùng một hành vi hoạt động với cách truy cập sẽ dùng ở sản xuất: derived query, `@Query`, reactive hay template.

**Chú ý:** class-based projection không áp dụng nested projection động theo cơ chế proxy interface. Nếu cần nested DTO, hãy khai báo các DTO con và tự kiểm soát ánh xạ, hoặc flatten kết quả query.

### Constructor mapping với DTO thông thường

Spring Data Commons xác định input của class projection từ **tên tham số constructor**. Với class có nhiều constructor, Spring Data có thể cần `@PersistenceCreator` để chỉ rõ constructor dùng cho persistence:

~~~java
import org.springframework.data.annotation.PersistenceCreator;

public final class CustomerCardDto {
    private final String fullName;
    private final String email;

    public CustomerCardDto() {
        this(null, null);
    }

    @PersistenceCreator
    public CustomerCardDto(String fullName, String email) {
        this.fullName = fullName;
        this.email = email;
    }

    public String getFullName() { return fullName; }
    public String getEmail() { return email; }
}
~~~

Đây là ví dụ về **hợp đồng constructor** trong Spring Data Commons, không phải lời bảo đảm DTO này hoạt động trong tất cả câu SQL++ của Couchbase. Thông thường nên ưu tiên record/constructor duy nhất nếu được phiên bản thực tế hỗ trợ; không thêm constructor rỗng nếu không có nhu cầu tương thích cụ thể.

## 9. SQL++ tường minh và ánh xạ DTO: đường đi dự đoán được

Nếu yêu cầu quan trọng nhất là **server chỉ trả ID, tên và email**, viết SQL++ chọn field tường minh:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 20;
~~~

Kết quả là các object có đúng những alias đã chọn. `META(c).id` đưa document key vào result row; `AS fullName`/`AS email` giữ tên khớp DTO.

Nếu dùng Couchbase Java SDK trực tiếp, có thể tự chuyển result row thành record, tránh phụ thuộc vào việc repository có hỗ trợ constructor mapping cho kiểu query đó hay không:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public List<CustomerCard> fetchActiveCards(Cluster cluster) {
    String statement = """
        SELECT META(c).id AS id,
               c.fullName AS fullName,
               c.email AS email
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.active = $active
        ORDER BY c.fullName, META(c).id
        LIMIT 20
        """;

    QueryResult result = cluster.query(
            statement,
            queryOptions().parameters(JsonObject.create().put("active", true))
    );

    return result.rowsAsObject()
            .stream()
            .map(row -> new CustomerCard(
                    row.getString("id"),
                    row.getString("fullName"),
                    row.getString("email")))
            .toList();
}
~~~

Mã ví dụ giả định method nằm trong một service và `Cluster` đã được cấu hình. Trong ứng dụng Spring Data Couchbase, một custom repository adapter có thể đóng gói đường truy vấn này. Có thể dùng `CouchbaseTemplate`/`ReactiveCouchbaseTemplate` theo cơ chế của phiên bản hiện tại, nhưng phải xác nhận API query và converter; đừng suy diễn rằng phương thức template trả DTO có cùng quy tắc với SDK raw rows.

### Nếu viết `@Query` trong repository

Các biểu thức `#{#n1ql.selectEntity}` và `#{#n1ql.filter}` trong tài liệu Couchbase hữu ích cho **truy vấn entity** và điều kiện loại tài liệu. Tuy nhiên `selectEntity` được thiết kế để lấy các trường cần tái tạo **entity đầy đủ** (kể cả metadata). Vì vậy nó không thay thế một `SELECT` ít field khi mục tiêu là payload tối thiểu.

Một query viết tay chỉ chiếu field có thể mô tả bằng:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = $1;
~~~

Trước khi gắn nó vào `@Query` trả interface hay DTO trực tiếp, cần kiểm thử **đúng cách ánh xạ result row** và cách bind tham số của phiên bản đang sử dụng. Với collection lưu nhiều loại entity, cần điều kiện phân biệt kiểu tài liệu tương ứng thay cho việc mặc nhiên cho rằng query tùy biến đã áp dụng filter của framework.

### Tránh lỗi metadata và alias

- Document key là `META(c).id` trong SQL++, không mặc định là field body `c.id`.
- Tên alias phải phù hợp kiểu đích hoặc mapper do ứng dụng kiểm soát.
- CAS, TTL/expiration không tự xuất hiện khi chỉ chọn vài field. Những tác vụ đọc để sau đó cập nhật có CAS cần lấy và bảo toàn metadata riêng.
- `SELECT c.*` và `SELECT #{#n1ql.fields}` phục vụ mục tiêu khác nhau so với một projection gọn; cần xem SQL++ cuối cùng.
- `MISSING` có thể làm một thuộc tính không hiện diện trong row; `null` có thể hiện diện nhưng không có giá trị. Khi dùng `getString` hoặc constructor, phải thử cả hai trường hợp.

## 10. Chọn projection không thay thế index và phép đo

Một truy vấn trả ít cột có thể vẫn phải đọc nguyên document để lấy dữ liệu. Nếu có covering index phù hợp, Query Engine *có thể* đáp ứng từ index; nếu không có, kế hoạch có thể có bước `Fetch`.

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 20;
~~~

Hãy xem index được chọn, thông tin `covers` và sự xuất hiện của `Fetch`. Đừng tạo index rộng chỉ để chứng minh một projection: secondary index làm tăng chi phí ghi, dung lượng và vận hành.

Cũng cần phân biệt **tính đúng đắn** với **tính mới của dữ liệu**: query theo secondary index có cấu hình scan consistency; nếu vừa cập nhật rồi query mà cần đọc thấy thay đổi ngay, phải chọn mức nhất quán phù hợp nghiệp vụ. Interface hay DTO không tự giải quyết chuyện này.

## 11. Bảng hỗ trợ thực tế theo loại phương thức

| Tình huống | Hướng chọn | Điều bắt buộc xác minh |
| --- | --- | --- |
| Derived query trả closed interface | Phù hợp làm điểm bắt đầu | Getter, ID, câu `SELECT` sinh ra |
| Derived query trả nested interface | Hợp lý cho view lồng nhau | Độ sâu mapping, toàn bộ field cha có bị tải không |
| Derived query trả open interface | Dùng khi thực sự cần SpEL | Không kỳ vọng tối ưu select-fields |
| Dynamic projection với `Class<T>` | Hữu ích nếu nhiều kiểu trả cùng điều kiện | Tương thích từng projection, tham số query |
| Derived query trả DTO/record | Có mô hình trong Spring Data Commons | Integration test dành riêng cho Couchbase và constructor |
| `@Query` tùy biến trả DTO | Chỉ chọn sau khi thử | Alias, result shape, type filter, ID/CAS |
| SQL++ + SDK raw rows → DTO | Hợp đồng mapping do ứng dụng nắm | Trường thiếu, alias, kiểu dữ liệu, lỗi query |
| Entity → DTO trong service | Giải pháp đáng tin để tách hợp đồng API | Không mặc nhiên giảm IO |
| `findById` trả projection qua override | Tránh ép chữ ký phương thức cơ sở | Xây phương thức riêng, chọn query/KV đúng nhu cầu |

Bảng này là hướng quyết định khi viết ứng dụng. **Không phải ma trận bảo đảm tính năng cho mọi phiên bản Spring Data Couchbase.** Dùng dependency lockfile/project thực tế và integration test để xác định kết luận cuối cùng.

## 12. Kiểm thử theo đường truy vấn, không chỉ kiểm thử kiểu Java

Giả sử bài toán trả về 20 khách hàng đang hoạt động. Bộ ca kiểm tra tối thiểu gồm:

1. **Đúng hình dạng:** caller chỉ nhận ID, tên, email như hợp đồng.
2. **Đúng metadata:** `getId()` hoặc DTO `id` phải bằng Couchbase document key, không phải field body giả định.
3. **Trường thiếu:** document không có `email` và document có `email: null` đều được xử lý theo đặc tả API.
4. **Trường lồng nhau:** `address.city` có giá trị, không có `address` và `address` là `null`.
5. **Đúng kiểu dữ liệu:** nếu `active` hoặc `email` lưu sai kiểu, mapper phản hồi thế nào?
6. **Đúng cơ chế query:** chạy cả derived method, `@Query`/SDK/custom repository thật sự được sử dụng, thay vì chỉ unit test mapper.
7. **Đúng payload:** thu thập SQL++ được gửi, xác minh `SELECT` và kích thước phản hồi; dùng `EXPLAIN` cho truy vấn trọng yếu.
8. **Đúng truy cập:** kiểm tra quyền dữ liệu; projection không thay thế authorization.
9. **Đúng tính mới:** nếu kịch bản yêu cầu read-after-write, kiểm tra scan consistency.
10. **Đúng phân trang:** sắp xếp ổn định (ưu tiên có khóa phân xử như document key), dữ liệu không trùng/lọt ngoài dự kiến khi lật trang.

Ví dụ một kiểm tra chức năng cần có với projection interface:

~~~java
// Pseudocode kiểm thử tích hợp: sử dụng Couchbase test instance đã cấu hình.
// 1. Seed document key "customer::42" với fullName/email/active.
// 2. Gọi repository.findByActiveTrue().
// 3. Tìm phần tử có getId() == "customer::42".
// 4. Assert getFullName() == "Trần Minh", getEmail() == "minh@example.test".
// 5. Quan sát query thực tế và result mapping trên cùng phiên bản dùng production.
~~~

Kiểm tra thành công của getter **chưa đủ** để kết luận đã giảm network IO. Phải đo thêm câu query sinh ra, số byte trả, index scan và độ trễ.

## 13. Lỗi thường gặp và cách tự chẩn đoán

### Getter trả null dù document có field

Kiểm tra tên thuộc tính Java, `@Field` nếu dùng custom stored-name, tên alias SQL++, đường nested và metadata ID. Đừng chỉ nhìn JSON rồi đoán tên getter.

### DTO không dựng được từ repository

Kiểm tra constructor/record components, sự hiện diện của tham số, converter, đường query trả về entity hay raw row và phiên bản Spring Data. Nếu không thể bảo đảm class-based mapping, chuyển sang interface projection đã xác minh hoặc ánh xạ thủ công từ result row.

### Query không tìm thấy document sau khi ghi

Xem scan consistency, index đã sẵn sàng hay chưa và điều kiện filter kiểu entity/collection. Đây không nhất thiết là lỗi projection.

### Truy vấn vẫn chậm dù API trả ba field

Xem `EXPLAIN`: có thể query vẫn đọc document, thiếu covering index, sort tốn tài nguyên, lọc không chọn lọc hoặc trả quá nhiều hàng. DTO nhỏ ở tầng Java không xử lý trực tiếp các vấn đề này.

### Kết quả lộ dữ liệu nhạy cảm

Controller vô tình trả entity hoặc JSON serializer dùng kiểu runtime khác kiểu view. Chọn DTO phản hồi rõ ràng, test JSON cuối cùng và thực thi phân quyền; projection chỉ là một phần của ranh giới dữ liệu.

### Thử dùng projection để cập nhật

Không nên `save` một projection hoặc DTO thiếu trường như thể nó là entity đầy đủ. Với Couchbase, cập nhật cần chú ý cấu trúc document, CAS và lựa chọn thao tác mutation phù hợp để không ghi đè dữ liệu ngoài ý muốn.

## 14. Bài tập áp dụng

Thiết kế tính năng **“Danh sách khách hàng đang hoạt động”** với hai cách:

- **Cách A:** repository trả `CustomerListView` có `getId()`, `getFullName()` và `getEmail()`; service chuyển sang `CustomerCard`.
- **Cách B:** SQL++ chọn ba trường tường minh; custom repository map result row sang `CustomerCard`.

Tạo dữ liệu kiểm thử gồm: một document đầy đủ, một document thiếu email, một document có email `null` và một document có tên trùng với document khác. Đo SQL++ phát sinh, response size, kết quả `EXPLAIN` và mức ổn định khi sắp xếp. Nếu repository DTO trực tiếp hoạt động trên phiên bản đang dùng, có thể thử **Cách C** để so sánh; ghi rõ những giới hạn đã quan sát, không giả định kết quả từ Spring Data Commons tự động đúng với mọi cơ chế Couchbase.

Câu hỏi tự kiểm tra:

1. Vì sao `getFullName()` ở closed projection thuận lợi hơn SpEL đọc `target` khi muốn tối ưu?
2. Vì sao interface projection trả đúng ba getter vẫn có thể phát sinh query đọc toàn bộ document?
3. Khác nhau giữa DTO được tự map trong service và DTO do repository trực tiếp tạo là gì?
4. Tại sao `META(c).id AS id` có thể cần trong câu SQL++ thủ công?
5. Làm sao biết truy vấn chỉ trả ít field nhưng vẫn có bước `Fetch`?

## 15. Tài liệu chính thức và cách đối chiếu

- [Spring Data Couchbase — Projections](https://docs.spring.io/spring-data/couchbase/reference/repositories/projections.html): interface projection, nested projection, closed/open projection, nullable wrapper, class-based DTO và dynamic projection ở tầng Spring Data.
- [Spring Data Couchbase — Couchbase repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): truy vấn dẫn xuất, `@Query`, các biểu thức `#n1ql`, cơ chế query theo điều kiện, index và ví dụ projection được mô tả riêng cho Couchbase.

Khi triển khai, hãy mở đúng tài liệu theo **phiên bản Spring Data Couchbase đã khóa trong ứng dụng**, vì tài liệu Spring Data Commons trình bày cơ chế chung còn hành vi truy vấn, kiểu ánh xạ và khả năng tối ưu có thể khác nhau giữa từng module hoặc phiên bản.

> **Ghi nhớ:** Interface projection phù hợp để khai báo view linh hoạt; DTO/record phù hợp để đóng gói hợp đồng dữ liệu rõ ràng. **Chứng minh tính đúng đắn bằng integration test và chứng minh hiệu năng bằng SQL++ thực tế + `EXPLAIN`**. Khi chưa xác minh khả năng Couchbase ánh xạ DTO trực tiếp, sử dụng mapper tường minh sẽ dễ dự đoán và vận hành hơn.
