# Sắp xếp bằng OrderBy và tham số Sort

Trong **SPRING_DATA_COUCHBASE**, repository không chỉ tìm document thỏa điều kiện mà còn cần trả kết quả theo thứ tự có ý nghĩa: khách hàng mới đăng ký trước, đơn hàng lâu nhất trước, tên tăng dần hoặc nhiều tiêu chí kết hợp. Spring Data cho phép khai báo **thứ tự cố định ngay trong tên phương thức** bằng `OrderBy`, hoặc **truyền thứ tự động** qua đối tượng `Sort` và `Pageable`.

Bài thuộc chương **Truy vấn dẫn xuất**, tập trung vào hai cách sắp xếp này và cách lựa chọn chúng trong ứng dụng. Spring Data Couchbase phân tích tên method dựa trên **property Java**, sử dụng metadata **document mapping** để sinh câu truy vấn **SQL++** trên bucket/scope/collection. Hiệu quả sắp xếp phụ thuộc vào index, số document được lọc, kiểu dữ liệu, thứ tự xử lý `NULL`/`MISSING` và chiến lược phân trang. Các yêu cầu về TTL, CAS, giao dịch và API reactive cũng cần được cân nhắc khi dữ liệu có thể thay đổi giữa các lần truy vấn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Viết `findByStatusOrderByJoinedAtDesc` và giải thích vị trí của `OrderBy`, `Asc`, `Desc`.
2. Khai báo sắp xếp nhiều trường với hướng tăng/giảm khác nhau trong cùng một tên method.
3. Truyền `Sort` vào repository để sắp xếp theo lựa chọn của giao diện mà không tạo nhiều phương thức.
4. Kết hợp `Pageable`, `PageRequest` và `Sort`; phân biệt sắp xếp với phân trang và đếm tổng.
5. Dùng property Java đúng tên kể cả khi JSON được đổi tên bằng `@Field`.
6. Hiểu vì sao phải có **khóa sắp xếp phụ ổn định**, đặc biệt khi phân trang.
7. Thiết kế index hỗ trợ `WHERE` và `ORDER BY`, sử dụng `EXPLAIN` để đánh giá kế hoạch.
8. Xử lý đầu vào sort, `NULL`/`MISSING`, chuỗi Unicode và dữ liệu thay đổi giữa các trang.
9. Quyết định khi nào cần SQL++ tường minh hoặc phân trang dựa trên khóa tiếp nối.

## 2. Tình huống xuyên suốt: danh sách khách hàng

Giả sử CRM lưu document trong bucket `app`, scope `crm`, collection `customers`:

```json
{
  "status": "ACTIVE",
  "customer_code": "C001",
  "display_name": "Lan Anh",
  "city": "HANOI",
  "joined_at": "2026-11-25T09:00:00Z",
  "loyalty_points": 250
}
```

Document có ID riêng, chẳng hạn `customer::C001`. Trong bài này, `customer_code` là trường JSON nghiệp vụ được quản lý để có giá trị duy nhất; nó được sử dụng làm **khóa sắp xếp phụ** khi nhiều document có cùng `joined_at`.

Entity Java ví dụ:

```java
package example.crm;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {

    @Id
    private String id;

    @Field
    private String status;

    @Field("customer_code")
    private String customerCode;

    @Field("display_name")
    private String displayName;

    @Field
    private String city;

    @Field("joined_at")
    private Instant joinedAt;

    @Field("loyalty_points")
    private Integer loyaltyPoints;

    protected Customer() {
        // Dành cho document mapper.
    }

    // Constructors nghiệp vụ và getters/setters được lược bỏ.
}
```

Cần bảo đảm ứng dụng đã cấu hình kết nối đến bucket `app` và entity được mapping đúng collection. Ví dụ dùng `Instant` để nhấn mạnh thời gian UTC; cách Spring Data thực sự serialize/convert `Instant` thành JSON phải được kiểm tra trong ứng dụng. Không nên mặc định mọi converter đều lưu thời gian thành chuỗi ISO 8601 như document mẫu.

## 3. `OrderBy`: sắp xếp cố định từ tên phương thức

### 3.1. Một tiêu chí

Repository có thể khai báo:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    List<Customer> findByStatusOrderByJoinedAtDesc(String status);

    List<Customer> findByStatusOrderByJoinedAtAsc(String status);
}
```

Cách đọc `findByStatusOrderByJoinedAtDesc("ACTIVE")`:

- `findBy`: truy vấn các entity thỏa điều kiện.
- `Status`: property `status` của `Customer` bằng tham số `"ACTIVE"`.
- `OrderBy`: bắt đầu phần mô tả thứ tự cố định.
- `JoinedAt`: property Java `joinedAt` là khóa sắp xếp.
- `Desc`: sắp xếp giảm dần, nghĩa là thời điểm mới hơn trước nếu dữ liệu được lưu và so sánh nhất quán.

Câu SQL++ diễn đạt ý định:

```sql
-- Minh họa logic, không phải SQL++ nguyên văn do Spring Data sinh ra.
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC;
```

`Asc` nghĩa là tăng dần; `Desc` nghĩa là giảm dần. Khi không viết rõ `OrderBy` hoặc truyền `Sort`/`Pageable` có sort, kết quả SQL++ **không có cam kết về thứ tự**, ngay cả khi truy vấn đôi khi tình cờ trả theo ID hoặc thứ tự của index.

### 3.2. Sắp xếp nhiều tiêu chí

Để ưu tiên ngày tham gia mới nhất, và khi ngày trùng nhau thì mã khách hàng tăng dần, có thể đặt tên:

```java
List<Customer> findByStatusOrderByJoinedAtDescCustomerCodeAsc(
    String status
);
```

Logic tương ứng:

```sql
WHERE c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC, c.`customer_code` ASC
```

SQL++ so sánh các khóa theo thứ tự trong `ORDER BY`: dùng `joined_at` trước; nếu bằng nhau thì dùng `customer_code`. Đây là **thứ tự từ trái sang phải của tiêu chí**, không phải hai phép sắp xếp độc lập.

Ví dụ dùng property `customerCode` làm khóa phụ vì ứng dụng quản lý tính duy nhất của nó. Nếu property này có thể trùng hoặc `MISSING`, kết quả vẫn có thể không được xác định hoàn toàn; cần bổ sung một khóa khác đủ phân biệt document.

### 3.3. Khi nào dùng `OrderBy`?

`OrderBy` thuận tiện khi một thao tác luôn có cùng thứ tự nghiệp vụ, chẳng hạn “5 khách hàng mới nhất” hoặc “mã chứng từ tăng dần”. Nhưng khi UI cho người dùng thay đổi nhiều cách sắp xếp, việc tạo hàng loạt tên method như `...OrderByJoinedAtDesc`, `...OrderByDisplayNameAsc`, `...OrderByLoyaltyPointsDesc` dễ làm repository phình to. Khi đó nên dùng tham số `Sort`.

## 4. `Sort`: sắp xếp động khi gọi repository

`Sort` là đối tượng của Spring Data Commons diễn đạt danh sách tiêu chí và hướng sắp xếp. Repository có thể nhận nó như một **tham số đặc biệt**:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    List<Customer> findByStatus(String status, Sort sort);
}
```

Ví dụ gọi:

```java
List<Customer> newest = repository.findByStatus(
    "ACTIVE",
    Sort.by(Sort.Direction.DESC, "joinedAt")
);

List<Customer> byName = repository.findByStatus(
    "ACTIVE",
    Sort.by(Sort.Direction.ASC, "displayName")
);
```

Đây vẫn là **cùng một** tên phương thức lọc theo `status`. Thứ tự được chọn tại thời điểm gọi bằng `Sort`.

### 4.1. Nhiều tiêu chí trong `Sort`

```java
Sort newestThenCode = Sort.by(
    Sort.Order.desc("joinedAt"),
    Sort.Order.asc("customerCode")
);

List<Customer> ordered = repository.findByStatus(
    "ACTIVE",
    newestThenCode
);
```

Tương đương ý định với:

```sql
ORDER BY c.`joined_at` DESC,
         c.`customer_code` ASC
```

Các chuỗi `"joinedAt"` và `"customerCode"` là **tên property Java**. Chúng không phải `"joined_at"`, `"customer_code"`, là tên field JSON vật lý. Spring Data Couchbase cần mapping đúng `@Field` để tạo biểu thức SQL++ tương ứng.

### 4.2. Các cách dựng `Sort`

```java
Sort ascending = Sort.by("displayName");
// Mặc định của Sort.by("...") là ASC.

Sort descending = Sort.by(
    Sort.Direction.DESC, "loyaltyPoints"
);

Sort combined = Sort.by(
    Sort.Order.asc("city"),
    Sort.Order.desc("loyaltyPoints"),
    Sort.Order.asc("customerCode")
);

Sort none = Sort.unsorted();
```

`Sort.unsorted()` nghĩa là không yêu cầu sắp xếp. Đây không phải “thứ tự mặc định ổn định”, nên không phù hợp nếu giao diện cần duy trì cùng thứ tự qua nhiều lần gọi hoặc các trang dữ liệu.

### 4.3. `OrderBy` cố định và `Sort` động khác nhau ra sao?

| Đặc điểm | `OrderBy` trong method | Tham số `Sort` |
| --- | --- | --- |
| Định nghĩa thứ tự | Khi khai báo tên phương thức | Khi gọi repository |
| Linh hoạt theo input | Thấp | Cao |
| Đọc nhanh ý định nghiệp vụ | Rõ với một vài tiêu chí cố định | Rõ khi giao diện có nhiều lựa chọn |
| Sắp xếp nhiều cột | Có thể nối nhiều property và `Asc`/`Desc` | Dùng nhiều `Sort.Order` |
| Chọn property | Parser method name | Chuỗi property trong `Sort` |
| Kết hợp phân trang | Cần nhận `Pageable` nếu muốn paging | `Pageable` có thể chứa `Sort` |

**Không nên mặc định cơ chế hợp nhất thứ tự cố định và thứ tự động có cùng hành vi ở mọi data module/phiên bản.** Nếu khai báo một phương thức vừa có `OrderBy...` trong tên vừa nhận `Sort` hoặc `Pageable` có sắp xếp, phải kiểm thử SQL++ được sinh ra và xác định tiêu chí nào được ưu tiên/ghép nối. Khi thứ tự cần hoàn toàn động, chọn phương thức chỉ có điều kiện lọc và truyền `Sort` từ bên gọi để tránh mơ hồ.

## 5. Ví dụ dữ liệu và thứ tự kết quả

Giả sử collection có các document:

| ID | `status` | `customer_code` | `city` | `joined_at` |
| --- | --- | --- | --- | --- |
| `c01` | ACTIVE | C001 | HANOI | 2026-11-25T09:00:00Z |
| `c02` | ACTIVE | C002 | HCM | 2026-11-25T09:00:00Z |
| `c03` | ACTIVE | C003 | HANOI | 2026-11-24T18:00:00Z |
| `c04` | SUSPENDED | C004 | HCM | 2026-11-26T10:00:00Z |
| `c05` | ACTIVE | C005 | HCM | 2026-11-23T12:00:00Z |
| `c06` | ACTIVE | C006 | DANANG | 2026-11-25T09:00:00Z |

Bảng thời gian giả định cùng một chuẩn lưu trữ có thể so sánh được. Kết quả kỳ vọng:

| Cách gọi | Thứ tự ID |
| --- | --- |
| `findByStatusOrderByJoinedAtDesc("ACTIVE")` | Ba ID `c01`, `c02`, `c06` đứng trước `c03` rồi `c05`; thứ tự **trong nhóm ba ID đầu không xác định**. |
| `findByStatusOrderByJoinedAtDescCustomerCodeAsc("ACTIVE")` | `c01 → c02 → c06 → c03 → c05` |
| `findByStatus("ACTIVE", Sort.by("customerCode"))` | `c01 → c02 → c03 → c05 → c06` |
| `findByStatus("ACTIVE", Sort.by(asc("city"), asc("customerCode")))` | `c06 → c01 → c03 → c02 → c05` |

Ở dòng cuối, `asc("city")` là ký hiệu rút gọn để diễn đạt `Sort.Order.asc("city")`; khi viết mã thật, dùng API Spring Data đầy đủ như sau:

```java
Sort byCityThenCode = Sort.by(
    Sort.Order.asc("city"),
    Sort.Order.asc("customerCode")
);

List<Customer> result =
    repository.findByStatus("ACTIVE", byCityThenCode);
```

Thứ tự `c06` trước là do `DANANG` đứng trước `HANOI` và `HCM` trong ví dụ giá trị chữ in hoa không dấu. Với chuỗi có dấu hoặc nhiều ngôn ngữ, thứ tự đối chiếu có thể khác kỳ vọng của người dùng; phải xem quy tắc so sánh chuỗi của SQL++/cấu hình thực tế.

## 6. Phân trang bằng `Pageable` và thứ tự ổn định

`Pageable` gom **chỉ số trang**, **kích thước trang** và **`Sort`** vào một tham số. Repository có thể khai báo:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Customer> findByStatus(String status, Pageable pageable);
```

Lời gọi:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<Customer> page = repository.findByStatus(
    "ACTIVE",
    PageRequest.of(
        0,      // Trang đầu tiên, bắt đầu từ 0.
        20,     // Tối đa 20 document trong một trang.
        Sort.by(
            Sort.Order.desc("joinedAt"),
            Sort.Order.asc("customerCode")
        )
    )
);

List<Customer> rows = page.getContent();
long total = page.getTotalElements();
```

`Page` có thể cần thêm truy vấn đếm để biết tổng số phần tử. Vì vậy chi phí thực tế không chỉ là truy vấn lấy 20 document. Cần kiểm tra với collection lớn, đặc biệt khi query có điều kiện phức tạp.

### 6.1. Tại sao phải có khóa sắp xếp phụ?

Nếu ba document `c01`, `c02`, `c06` có cùng `joined_at`, chỉ sắp xếp giảm dần theo thời điểm không cho biết thứ tự giữa ba document này. Khi `LIMIT`/`OFFSET` cắt ngang nhóm đó, cùng một request có thể nhận những document khác nhau ở ranh giới trang do kế hoạch thực thi hoặc dữ liệu thay đổi.

Một thứ tự xác định hơn:

```sql
ORDER BY c.`joined_at` DESC,
         c.`customer_code` ASC
```

Khi `customer_code` **duy nhất**, có mặt và dùng kiểu dữ liệu nhất quán, tổ hợp này cho phép xác định vị trí document rõ ràng. Nếu không có một field JSON nghiệp vụ duy nhất, có thể cân nhắc sử dụng document ID qua biểu thức SQL++/API tương thích, nhưng không được tự giả định `Sort.by("id")` luôn được dịch đúng sang `META(c).id` trong mọi phiên bản Spring Data Couchbase.

**Quan trọng:** Thứ tự xác định tại thời điểm truy vấn không bảo đảm kết quả các trang giữ nguyên khi document bị chèn, xóa hoặc cập nhật giữa các lần gọi. Để đọc ảnh chụp nhất quán qua nhiều trang khi dữ liệu đang đổi, cần chiến lược nghiệp vụ và API phù hợp, không chỉ thêm khóa sort.

### 6.2. Phân trang không có `ORDER BY`

`PageRequest.of(0, 20)` chỉ nêu kích thước và vị trí trang, không bảo đảm lựa chọn 20 document nào theo một thứ tự ổn định. Nếu giao diện gọi trang 0 rồi trang 1 mà không có `Sort`, có thể xuất hiện trùng/thiếu document. Luôn định nghĩa thứ tự rõ ràng cho trường hợp phân trang cần tính liên tục.

### 6.3. Hạn chế của offset lớn

Với SQL++ minh họa:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC, c.`customer_code` ASC
LIMIT 20 OFFSET 100000;
```

Offset cao có thể khiến Query Service xử lý nhiều khóa trước khi trả về 20 document cuối. Index tốt cải thiện hiệu năng nhưng không xóa hoàn toàn chi phí offset. Nếu cần cuộn liên tục qua tập dữ liệu rất lớn, cân nhắc phân trang bằng điều kiện tiếp nối (keyset) thay vì offset tăng không giới hạn.

## 7. Phân trang bằng khóa tiếp nối khi dữ liệu lớn

Giả sử thứ tự cần giữ là:

```sql
ORDER BY c.`joined_at` DESC, c.`customer_code` ASC
```

Trang trước kết thúc tại cặp `($lastJoinedAt, $lastCode)`. Muốn lấy các document **đứng sau** cặp này theo đúng thứ tự, có thể dùng điều kiện:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
  AND (
       c.`joined_at` < $lastJoinedAt
       OR (
           c.`joined_at` = $lastJoinedAt
           AND c.`customer_code` > $lastCode
       )
  )
ORDER BY c.`joined_at` DESC, c.`customer_code` ASC
LIMIT $pageSize;
```

Điều kiện gồm hai nhánh vì hướng sort trái ngược nhau: thời gian `DESC` nên document “sau” có thời gian **nhỏ hơn**; nếu thời gian bằng nhau, mã `ASC` nên document “sau” có mã **lớn hơn**.

Đây là **SQL++ minh họa**, không phải chú thích `@Query` hoàn chỉnh có thể dán vào mọi phiên bản Spring Data Couchbase. Cần chuẩn hóa kiểu và encoding của `joined_at`, binding tham số, điều kiện type discriminator và projection để mapper tạo entity đúng.

Keyset dựa trên cặp khóa không null, nhất quán và có tính thứ tự tổng. Nếu dữ liệu có giá trị `NULL`/`MISSING`, field sort có thể thay đổi hoặc business cần “nhảy tới trang 500”, phải thiết kế API và xử lý riêng. Đối với bộ lọc/sắp xếp nhiều nhánh khó diễn đạt trong tên method, `@Query` hoặc `CouchbaseTemplate` là phương án thích hợp hơn.

## 8. Index cho truy vấn có sắp xếp

Sắp xếp lớn tại Query Service có thể tốn CPU và bộ nhớ. Một index phù hợp với `WHERE` và `ORDER BY` có thể giúp giảm lượng dữ liệu phải xử lý và hạn chế bước sort bổ sung, tùy kế hoạch thực tế.

Giả sử SQL++ do Spring Data sinh ra có điều kiện phân biệt loại entity qua trường `_class`, và các trường JSON được lưu giống ví dụ. Index minh họa:

```sql
CREATE INDEX ix_customers_type_status_joined_code
ON `app`.`crm`.`customers` (
  `_class`,
  `status`,
  `joined_at` DESC,
  `customer_code` ASC
);
```

Một truy vấn có thể sử dụng index này:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`_class` = "example.crm.Customer"
  AND c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC,
         c.`customer_code` ASC;
```

**Các câu trên chỉ là ví dụ định hướng.** Ứng dụng có thể tùy chỉnh type discriminator hoặc không có điều kiện `_class` giống ví dụ; Spring Data cũng có thể chọn projection/metadata khác. Không chép nguyên DDL trước khi đối chiếu SQL++ và JSON thật của ứng dụng.

### 8.1. Vì sao thứ tự trường index quan trọng?

Với truy vấn lọc `status = ?` và sắp theo `joined_at DESC, customer_code ASC`, các key equality đứng trước các key sort là điểm xuất phát hợp lý khi thiết kế composite index. Tuy nhiên:

- Một index `(status, joined_at, customer_code)` không chắc tối ưu khi **chỉ** tìm theo `joined_at` mà không lọc `status`.
- Nếu `ORDER BY` có thứ tự `ASC`/`DESC` khác với thứ tự key index, khả năng tận dụng index để tránh sort có thể thay đổi.
- Sắp xếp theo trường khác, ví dụ `display_name`, có thể cần đường index khác nếu đây là chức năng thường xuyên và tập kết quả lớn.
- Query có thể phải fetch document dù index đã hỗ trợ sort; xem query plan để biết các bước thực tế.
- Index bổ sung tăng chi phí cập nhật dữ liệu, dung lượng lưu trữ và vận hành, nên tránh tạo index cho mọi menu sắp xếp ít dùng.

### 8.2. Dùng `EXPLAIN` để đánh giá

```sql
EXPLAIN
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC,
         c.`customer_code` ASC
LIMIT 20;
```

Hãy bổ sung điều kiện do Spring Data sinh ra khi kiểm tra môi trường thật. Đối chiếu các trường trong index, index scan, số document fetch, bước sort, `LIMIT`/`OFFSET` và độ trễ thực tế.

Trong Couchbase, secondary index có thể không bao gồm mọi document thiếu trường key theo cấu hình và phiên bản. Nếu `joined_at` có thể `MISSING`, phải đánh giá cả tính đúng đắn của tập kết quả chứ không chỉ tối ưu tốc độ. Một index được planner chọn chưa chắc đủ đáp ứng nghiệp vụ nếu ứng dụng cần hiển thị cả document thiếu dữ liệu sort.

## 9. `NULL`, `MISSING` và kiểu dữ liệu làm thay đổi thứ tự

Couchbase lưu JSON nên field `joined_at` hoặc `display_name` có thể:

1. Có giá trị hợp lệ.
2. Tồn tại với JSON `null`.
3. Hoàn toàn không tồn tại (`MISSING`).
4. Tồn tại nhưng có kiểu không đồng nhất, ví dụ chuỗi ở document này và số ở document khác.

Ví dụ:

```json
{"customer_code":"C010","joined_at":"2026-11-25T09:00:00Z"}
```

```json
{"customer_code":"C011","joined_at":null}
```

```json
{"customer_code":"C012"}
```

**Không tự giả định** `NULL` và `MISSING` sẽ được SQL++/Spring Data xử lý giống nhau khi `ORDER BY`. Nếu giao diện cần “không có ngày tham gia thì hiển thị cuối cùng”, phải kiểm tra thứ tự mặc định và cân nhắc biểu thức sắp xếp tường minh trong SQL++ hoặc trường chuẩn hóa dành cho sort.

Các tùy chọn như `Sort.NullHandling.NULLS_LAST` của Spring Data Commons là **gợi ý ở cấp API**, không bảo đảm mọi Spring Data store, trong đó có mọi phiên bản Couchbase, đều hỗ trợ chính xác. Nên xác minh SQL++ sinh ra và dữ liệu thử nghiệm.

### 9.1. Thời gian phải có định dạng thống nhất

Nếu ứng dụng lưu ngày giờ dưới dạng chuỗi ISO 8601, cần chuẩn hóa múi giờ về UTC và định dạng nhất quán nếu muốn thứ tự chuỗi phản ánh thứ tự thời gian. Ví dụ `2026-11-25T09:00:00Z` và cùng thời điểm với offset khác có thể sắp theo chuỗi không như mong muốn dù biểu diễn một thời điểm.

Nếu ứng dụng dùng converter khác lưu `Instant` thành số hoặc cấu trúc khác, index và truy vấn phải dựa trên **giá trị JSON thực tế**, không dựa trên kiểu Java. Không trộn kiểu số và kiểu chuỗi cho cùng một property sort trong tập dữ liệu.

### 9.2. Chuỗi và tiếng Việt

`Sort.by("displayName")` không có nghĩa tên sẽ tự sắp xếp theo quy tắc từ điển tiếng Việt. SQL++ sử dụng quy tắc so sánh và kiểu dữ liệu thực tế, có thể khác kỳ vọng sắp xếp tiếng Việt có dấu, ký tự `Đ/đ` hoặc chữ hoa/thường. Nếu sản phẩm cần thứ tự ngôn ngữ tự nhiên, xem xét một trường khóa sắp xếp đã chuẩn hóa theo quy tắc nghiệp vụ, phương án collation được backend hỗ trợ hoặc xử lý chuyên biệt trên tập có giới hạn.

Tránh sắp xếp tập hàng triệu document trong Java chỉ để thực hiện thứ tự tiếng Việt nếu ứng dụng cần phân trang server-side; phải thiết kế khóa sort và index trước.

## 10. Nhận đầu vào sort từ client một cách có kiểm soát

Cho phép client gửi tùy ý `sort=someProperty` rồi chuyển thẳng thành `Sort.by(...)` có thể gây lỗi nếu property không tồn tại, truy vấn kém hiệu quả hoặc làm lộ một đường truy cập không intended. Cách rõ ràng là đưa ra **danh sách lựa chọn sort đã hỗ trợ** và ánh xạ chúng sang property Java.

Ví dụ:

```java
import org.springframework.data.domain.Sort;

public final class CustomerSorts {

    private CustomerSorts() {}

    public static Sort fromUiChoice(String choice) {
        if (choice == null) {
            return newest();
        }

        return switch (choice) {
            case "newest" -> newest();
            case "oldest" -> Sort.by(
                Sort.Order.asc("joinedAt"),
                Sort.Order.asc("customerCode")
            );
            case "name" -> Sort.by(
                Sort.Order.asc("displayName"),
                Sort.Order.asc("customerCode")
            );
            case "points" -> Sort.by(
                Sort.Order.desc("loyaltyPoints"),
                Sort.Order.asc("customerCode")
            );
            default -> throw new IllegalArgumentException(
                "Cách sắp xếp không được hỗ trợ"
            );
        };
    }

    private static Sort newest() {
        return Sort.by(
            Sort.Order.desc("joinedAt"),
            Sort.Order.asc("customerCode")
        );
    }
}
```

Nhờ đó client chỉ có thể yêu cầu các khóa được ứng dụng xác định trước. Khi thêm một lựa chọn mới, cần kiểm tra đường index tương ứng và thứ tự với giá trị null/missing.

### 10.1. Giới hạn chỉ số và kích thước trang

```java
import org.springframework.data.domain.PageRequest;

public static PageRequest pageRequest(
    int page,
    int size,
    String sortChoice
) {
    if (page < 0) {
        throw new IllegalArgumentException("Trang phải >= 0");
    }
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException(
            "Kích thước trang phải từ 1 đến 100"
        );
    }

    return PageRequest.of(
        page,
        size,
        CustomerSorts.fromUiChoice(sortChoice)
    );
}
```

`100` chỉ là giới hạn ví dụ. Tùy lưu lượng và kích thước document, ứng dụng có thể đặt giới hạn thấp hơn. Cần đánh giá rủi ro offset rất cao khi client có thể cung cấp chỉ số trang bất kỳ.

## 11. Khi nào không nên suy diễn thứ tự bằng tên method?

Derived query thích hợp cho lọc đơn giản với thứ tự cố định hoặc một tham số `Sort`. Chuyển sang SQL++ tường minh qua `@Query` hay `CouchbaseTemplate` khi cần:

- Sắp xếp theo **biểu thức**, ví dụ `LOWER(display_name)`, `COALESCE` hoặc `CASE` để xử lý null/missing.
- Quy tắc ưu tiên nghiệp vụ như “ACTIVE trước, PENDING sau, SUSPENDED cuối” không trùng thứ tự chữ cái.
- Keyset pagination có nhiều khóa và điều kiện tiếp nối phức tạp.
- `JOIN`, `UNNEST`, tổng hợp hay projection đặc thù.
- Kết hợp nhiều bộ lọc tùy chọn và sắp xếp động theo lựa chọn của người dùng.
- Cần kiểm soát rõ index, hints hoặc query options.

Một ví dụ sắp xếp trạng thái theo ưu tiên nghiệp vụ:

```sql
-- Minh họa thứ tự theo yêu cầu sản phẩm.
SELECT c.*
FROM `app`.`crm`.`customers` AS c
ORDER BY CASE c.`status`
           WHEN "ACTIVE" THEN 1
           WHEN "PENDING" THEN 2
           WHEN "SUSPENDED" THEN 3
           ELSE 4
         END ASC,
         c.`customer_code` ASC;
```

Đây không phải thứ tự đơn giản theo property để diễn đạt bằng `Sort.by("status")`. Truy vấn dùng biểu thức có thể đòi hỏi chiến lược index khác; xem `EXPLAIN` và dữ liệu thực. Khi đưa vào `@Query`, cần dùng cú pháp binding và projection phù hợp Spring Data Couchbase, không sao chép JPQL của Spring Data JPA.

## 12. Sắp xếp trong repository reactive

Repository reactive có thể dùng ý tưởng tương tự:

```java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Flux;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Flux<Customer> findByStatusOrderByJoinedAtDesc(String status);

    // Kiểm tra trên phiên bản Spring Data Couchbase đang dùng
    // khả năng xử lý tham số Sort trong query reactive.
    Flux<Customer> findByStatus(String status, Sort sort);
}
```

`Flux<Customer>` cho phép tiêu thụ nhiều kết quả theo mô hình reactive, nhưng **thứ tự vẫn phải được xác lập ở phía truy vấn**. Không nên lấy một `Flux` không sắp xếp rồi kỳ vọng thứ tự phát ra luôn trùng thứ tự mong muốn.

Reactive không làm thay đổi quy tắc SQL++ `ORDER BY`, index hay chi phí sort; không tự giải quyết hiện tượng document thay đổi giữa các lần phân trang. Tránh gọi `block()` trong đường xử lý web reactive nếu không có thiết kế xử lý blocking phù hợp.

## 13. Consistency, TTL, CAS và giao dịch ảnh hưởng thứ tự ra sao?

### 13.1. Index chưa phản ánh document mới

```text
save(customer)                         -> key-value write thành công
findById(customer.id)                  -> có thể đọc document theo ID
findByStatusOrderByJoinedAtDesc(...)   -> SQL++ qua index
```

Truy vấn có `ORDER BY` vẫn dựa trên Query Service và index; ở mức consistency thông thường, document mới có thể chưa xuất hiện ngay dù `save` đã thành công. Khi nghiệp vụ cần read-your-own-write, xem xét query scan consistency thích hợp (chẳng hạn mức tương đương `REQUEST_PLUS` khi API/phiên bản hỗ trợ) hoặc đọc lại document theo ID. Consistency mạnh hơn có thể tăng độ trễ và không thay thế nhu cầu có khóa sắp xếp phụ.

### 13.2. TTL

Document có TTL có thể hết hạn giữa lúc người dùng mở trang 1 và trang 2. Điều này làm số lượng và ranh giới trang thay đổi ngay cả khi cùng một `Sort`. Nếu cần kết quả lịch sử bất biến, phải có chiến lược snapshot hoặc lưu dữ liệu thích hợp; không thể đạt được chỉ bằng `ORDER BY`.

### 13.3. CAS và giao dịch

Nếu hai tác vụ đồng thời cập nhật `joinedAt`, `customerCode` hoặc các trường ảnh hưởng thứ tự, cần bảo đảm thao tác ghi đúng thông qua CAS/optimistic locking khi phù hợp. Một lần `findByStatus(...)` không tự khóa document. Nhiều request phân trang cũng không mặc nhiên nằm trong cùng giao dịch nguyên tử; giao dịch (khi được hỗ trợ) xử lý một phạm vi khác với việc cố định snapshot qua hàng loạt request web.

### 13.4. Bucket, scope và collection

Tên method quyết định điều kiện và thứ tự, nhưng collection đích đến từ mapping/cấu hình. Nếu repository đọc nhầm scope hoặc collection, kết quả có thể rỗng hoặc không đúng cấu trúc index. Hãy xác minh entity mapping và index cùng trỏ tới đúng namespace.

## 14. Bài tập thực hành

Dùng bảng `c01`–`c06` ở mục 5 và các property của `Customer`.

**Bài A — Sắp xếp cố định.** Khách hàng ACTIVE theo ngày tham gia mới nhất, rồi mã tăng dần.

```java
List<Customer> findByStatusOrderByJoinedAtDescCustomerCodeAsc(
    String status
);
```

Gọi với `"ACTIVE"` → `c01 → c02 → c06 → c03 → c05`. Vì `c04` không ACTIVE nên bị loại dù có ngày tham gia mới hơn.

**Bài B — Sắp xếp động.** Khách hàng ACTIVE theo số điểm giảm dần, mã tăng dần. Chọn đúng `Sort`:

```java
Sort.by(
    Sort.Order.desc("loyaltyPoints"),
    Sort.Order.asc("customerCode")
);
```

Để biết thứ tự ID chính xác, thêm giá trị `loyalty_points` vào bộ dữ liệu thử nghiệm; không suy luận thứ tự chỉ từ tên khách hàng hoặc ngày tham gia.

**Bài C — Thứ tự ổn định.** Vì sao `findByStatusOrderByJoinedAtDesc` chưa đủ cho phân trang? — Vì nhiều document có cùng `joinedAt` và thứ tự trong nhóm đó chưa được xác định. Bổ sung `customerCode` làm khóa phụ có tính duy nhất.

**Bài D — Property Java và JSON.** Với `@Field("joined_at") private Instant joinedAt;`, client nên ánh xạ lựa chọn sort tới `"joinedAt"` hay `"joined_at"`? — Trong `Sort` và tên derived query dùng **`joinedAt`**; SQL++/index dùng **`joined_at`**.

**Bài E — Offset so với keyset.** Với `ORDER BY joined_at DESC, customer_code ASC`, cặp cuối trang trước là `("2026-11-25T09:00:00Z", "C002")`. Trang tiếp theo lấy `joined_at` nhỏ hơn cận hoặc cùng thời gian nhưng `customer_code` lớn hơn `"C002"`. Trên bảng mẫu, cặp tiếp theo là `c06` (cùng thời gian, mã C006) trước khi chuyển sang `c03` rồi `c05`.

**Bài F — Dữ liệu thiếu.** Thêm `c07` ACTIVE nhưng không có `joined_at` và `c08` ACTIVE có `joined_at = null`. Yêu cầu sắp “document chưa có ngày tham gia ở cuối” có được `Sort.by(desc("joinedAt"))` bảo đảm không? — Không được kết luận khi chưa kiểm tra thứ tự SQL++ và query creator; cần quy tắc SQL++ tường minh hoặc field sort chuẩn hóa nếu nghiệp vụ đòi hỏi.

### Checklist trước khi đưa chức năng sort vào sản phẩm

| Kiểm tra | Câu hỏi cần trả lời |
| --- | --- |
| Property | Tên trong `OrderBy`/`Sort` có đúng property Java, bao gồm alias `@Field`? |
| Hướng sort | `Asc`/`Desc` đúng quy tắc thời gian và nghiệp vụ chưa? |
| Khóa phụ | Có thứ tự xác định khi nhiều document cùng giá trị chính? |
| Dữ liệu | Field sort có `NULL`/`MISSING` hoặc trộn kiểu JSON không? |
| Time zone | Dữ liệu ngày giờ có cùng chuẩn và converter không? |
| Tính ổn định | Có yêu cầu snapshot hay chấp nhận dữ liệu đổi giữa các trang? |
| Client | Sort có được ánh xạ từ whitelist, size và page được giới hạn? |
| Index | `EXPLAIN` có dùng index thích hợp, tránh sort/scan quá đắt không? |
| Mở rộng | Offset lớn có cần chuyển sang phân trang theo khóa tiếp nối? |
| Nhất quán | Query scan consistency đáp ứng nhu cầu đọc dữ liệu vừa ghi? |

## 15. Ghi nhớ

**`OrderBy` trong tên phương thức** phù hợp khi thứ tự cố định theo nghiệp vụ; **`Sort` và `Pageable`** phù hợp khi người gọi cần lựa chọn thứ tự hoặc phân trang. Cả hai đều sử dụng **property Java** để Spring Data Couchbase ánh xạ tới **field JSON** trong `ORDER BY` SQL++. Không có sort thì không có cam kết thứ tự; sort theo một field có giá trị trùng cũng chưa tạo thứ tự ổn định.

Một chức năng sắp xếp đáng tin cậy cần **khóa phụ đủ phân biệt**, **kiểu dữ liệu thống nhất**, **xử lý `NULL`/`MISSING` rõ ràng**, **index hỗ trợ `WHERE` và `ORDER BY`**, cùng giới hạn tải và chiến lược phân trang phù hợp. Với sort theo biểu thức, ưu tiên nghiệp vụ hoặc keyset phức tạp, sử dụng `@Query`/`CouchbaseTemplate` để định nghĩa SQL++ minh bạch, kiểm chứng bằng `EXPLAIN` và kiểm thử trên dữ liệu thực tế.
