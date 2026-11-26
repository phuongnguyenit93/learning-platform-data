# Giới hạn số kết quả và lựa chọn kiểu trả về

Trong **SPRING_DATA_COUCHBASE**, việc tìm đúng document chưa đủ: tầng truy cập dữ liệu còn phải quyết định **lấy bao nhiêu kết quả**, **trả về dưới kiểu Java nào** và **có cần tổng số bản ghi hay không**. Một ô tìm kiếm chỉ cần 10 gợi ý đầu tiên khác hẳn báo cáo cần đếm toàn bộ khách hàng hoặc màn hình cần phân trang 20 document một lần. Nếu repository trả danh sách không giới hạn cho mọi trường hợp, ứng dụng dễ mất thời gian truyền dữ liệu, chiếm nhiều bộ nhớ và tạo tải không cần thiết cho Couchbase Query Service.

Bài thuộc chương **Truy vấn dẫn xuất** và tập trung vào **giới hạn số kết quả cùng lựa chọn kiểu trả về** của Spring Data Couchbase. Nội dung trình bày `First`/`Top`, `Optional`, `List`, `Page`, `Slice` (khi phiên bản hỗ trợ), `countBy`, `existsBy` và `Pageable`; đồng thời giải thích quan hệ với SQL++ `LIMIT`/`OFFSET`, `Sort`, index và API reactive. Đây là một phần của kiến trúc truy cập Couchbase bằng document mapping, repository và `CouchbaseTemplate` trên bucket/scope/collection, nơi TTL, CAS, giao dịch và consistency có thể làm tập kết quả thay đổi theo thời gian.

> **Nguyên tắc xuyên suốt:** Giới hạn số document, kiểu trả về và thứ tự sắp xếp là **ba quyết định riêng**. Muốn nói “lấy ba khách hàng mới nhất”, phải có cả điều kiện lọc, **thứ tự xác định** và **giới hạn ba phần tử**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt lấy một document theo ID, một kết quả khớp điều kiện, vài kết quả đầu tiên và một trang dữ liệu.
2. Hiểu các từ khóa `First` và `Top` trong tên phương thức derived query, gồm dạng có số lượng và dạng lấy một kết quả.
3. Chọn `Optional<T>`, `T`, `List<T>`, `Page<T>` hoặc kiểu trả về chỉ đếm/kiểm tra tồn tại dựa trên hợp đồng nghiệp vụ.
4. Kết hợp `Sort` và `Pageable` để giới hạn kết quả có thứ tự và không tải quá nhiều document.
5. Phân biệt số **phần tử trang hiện tại** với **tổng số phần tử khớp điều kiện**.
6. Giải thích vì sao `Page` có thể phát sinh truy vấn count và vì sao `Slice` có đặc điểm khác, khi module hỗ trợ.
7. Thiết kế index để truy vấn `WHERE + ORDER BY + LIMIT` có chi phí hợp lý.
8. Nhận biết giới hạn của cách dùng `Flux.take(n)`, streaming phía Java và việc lọc sau khi đã lấy toàn bộ document.
9. Xử lý trường hợp trùng khóa sắp xếp, tập kết quả rỗng, dữ liệu thay đổi và query consistency.
10. Biết khi nào chuyển sang `@Query` hoặc `CouchbaseTemplate` để kiểm soát truy vấn tường minh.

## 2. Mô hình dữ liệu minh họa

Giả sử ứng dụng CRM dùng bucket `app`, scope `crm`, collection `customers`. Document mẫu:

```json
{
  "customer_code": "C002",
  "email": "binh@example.test",
  "status": "ACTIVE",
  "city": "HANOI",
  "joined_at": "2026-11-24T09:00:00Z",
  "loyalty_points": 150
}
```

Couchbase quản lý **document ID** riêng, ví dụ `customer::C002`. Trường `customer_code` là mã khách hàng nghiệp vụ; ví dụ giả định hệ thống ghi dữ liệu bảo đảm mã này không trùng, để có thể dùng làm khóa sắp xếp phụ.

Khai báo entity:

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

    @Field("customer_code")
    private String customerCode;

    @Field
    private String email;

    @Field
    private String status;

    @Field
    private String city;

    @Field("joined_at")
    private Instant joinedAt;

    @Field("loyalty_points")
    private Integer loyaltyPoints;

    protected Customer() {
        // Constructor cho document mapper.
    }

    // Constructor nghiệp vụ và getters/setters được lược bỏ.
}
```

Cần cấu hình kết nối đúng bucket `app` và mapping đúng scope/collection. Entity dùng `Instant` để biểu diễn thời điểm; cách converter ghi `Instant` vào JSON có thể khác định dạng chuỗi minh họa, nên cần đối chiếu document thực tế khi thiết kế index và điều kiện sắp xếp.

**Quy tắc đặt tên:** Derived query dùng property Java `joinedAt` và `customerCode`, trong khi SQL++/index dùng tên trường JSON đã mapping là `joined_at` và `customer_code`.

## 3. Cùng một điều kiện nhưng các nhu cầu trả về khác nhau

Xét yêu cầu lọc `status = "ACTIVE"`. Tầng nghiệp vụ có thể đặt nhiều câu hỏi:

| Yêu cầu | Câu hỏi thật sự | Kiểu kết quả phù hợp |
| --- | --- | --- |
| Có bất kỳ khách hàng ACTIVE không? | `true` hoặc `false` | `boolean` với `existsBy...` |
| Có bao nhiêu khách hàng ACTIVE? | Một con số | `long` với `countBy...` |
| Lấy khách hàng ACTIVE mới nhất | Tối đa một document theo thứ tự | `Optional<Customer>` với `First`/`Top` và `OrderBy` |
| Lấy ba khách hàng ACTIVE mới nhất | Tối đa ba document | `List<Customer>` với `Top3` và sort xác định |
| Hiển thị trang đầu, mỗi trang 20 người | Nội dung trang và tổng số nếu cần | `Page<Customer>` và `Pageable` |
| Chỉ muốn biết có trang kế tiếp | Nội dung trang và cờ còn dữ liệu | `Slice<Customer>` nếu phiên bản hỗ trợ, hoặc chiến lược tương đương |
| Duyệt một tập nhỏ đã biết chắc | Danh sách không cần phân trang | `List<Customer>` |

Một repository nên có các phương thức diễn đạt **nhu cầu cụ thể**, không chọn kiểu trả về chỉ vì lập trình viên quen dùng `List`.

## 4. Giới hạn bằng `First` và `Top` trong tên phương thức

Theo ngữ pháp truy vấn dẫn xuất của Spring Data, `First` và `Top` là các từ khóa giới hạn số kết quả. Chúng có thể nhận con số như `Top3` hoặc `First5`. Khi không có con số, ý định thông thường là giới hạn **một** kết quả.

Ví dụ:

```java
package example.crm;

import java.util.List;
import java.util.Optional;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    Optional<Customer> findFirstByStatusOrderByJoinedAtDescCustomerCodeAsc(
        String status
    );

    List<Customer> findTop3ByStatusOrderByJoinedAtDescCustomerCodeAsc(
        String status
    );

    List<Customer> findFirst5ByCityOrderByCustomerCodeAsc(
        String city
    );
}
```

Cách đọc `findTop3ByStatusOrderByJoinedAtDescCustomerCodeAsc("ACTIVE")`:

1. `find`: truy vấn lấy entity.
2. `Top3`: giới hạn **tối đa ba** kết quả.
3. `ByStatus`: chỉ lấy document có `status` bằng tham số.
4. `OrderByJoinedAtDesc`: thời điểm tham gia gần đây trước.
5. `CustomerCodeAsc`: khi thời điểm bằng nhau, dùng mã tăng dần để xác định thứ tự.

SQL++ minh họa:

```sql
-- Logic minh họa; SQL++ Spring Data Couchbase sinh có thể khác.
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC,
         c.`customer_code` ASC
LIMIT 3;
```

**Lưu ý phiên bản:** Ngữ pháp `First`/`Top` là tính năng của Spring Data nói chung. Khả năng Spring Data Couchbase chuyển từng dạng từ khóa này thành `LIMIT`, cũng như tương tác với `Sort`/`Pageable`, cần được xác minh trên phiên bản cụ thể và kiểm thử bằng dữ liệu thật. Không tự suy ra rằng mọi từ khóa Spring Data JPA đều được Couchbase hỗ trợ giống hệt.

### 4.1. Giới hạn không tạo tính duy nhất

Phương thức `findFirstByEmail(...)`, nếu được hỗ trợ, có thể chỉ trả **một** trong nhiều document có email trùng. Nó **không bảo đảm** email là duy nhất, cũng không phát hiện lỗi trùng khi được dùng như một cách che đi kết quả dư thừa.

Nếu email phải duy nhất, đó là **quy tắc ghi dữ liệu** cần được bảo đảm riêng. Secondary index trên email giúp tìm nhanh nhưng không tự trở thành một ràng buộc uniqueness.

Nếu muốn lấy một document theo **document ID** đã biết, dùng `findById(id)`: thao tác này thường sử dụng key-value, khác với truy vấn `First` theo trường nội dung qua SQL++.

### 4.2. Giới hạn một nhưng không có sort

```java
Optional<Customer> findFirstByStatus(String status);
```

Ý định là lấy tối đa một khách hàng theo `status`, nhưng **không xác định khách hàng nào** khi nhiều document khớp. “Đầu tiên” không có ý nghĩa ổn định nếu thiếu `OrderBy`/`Sort`. Cùng dữ liệu có thể trả document khác khi index hoặc kế hoạch thực thi thay đổi.

Nếu nghiệp vụ muốn “người đăng ký sớm nhất”, cần sắp theo `joinedAt ASC`, không chỉ dùng `First`.

## 5. Chọn kiểu trả về đơn trị: `T` và `Optional<T>`

Một phương thức có chữ ký:

```java
Optional<Customer> findByEmail(String email);
```

thể hiện kỳ vọng **0 hoặc 1 document** cho một email. Cách tiêu thụ:

```java
Optional<Customer> result =
    repository.findByEmail("lan@example.test");

Customer customer = result.orElseThrow(
    () -> new IllegalArgumentException("Không tìm thấy khách hàng")
);
```

`Optional.empty()` diễn đạt trường hợp không có document. Nếu nhiều document cùng email và query **không có giới hạn**, một kiểu trả về đơn trị có thể dẫn đến lỗi vì kết quả không duy nhất. Không dùng `Optional` để tự động lấy phần tử đầu tiên khi dữ liệu có thể có nhiều document.

Một phương thức trả trực tiếp `Customer` cũng diễn đạt kỳ vọng đơn trị, nhưng cách mô tả trạng thái không có kết quả (null/exception) phụ thuộc hợp đồng API Spring Data và annotations; `Optional<Customer>` thường minh bạch hơn tại ranh giới service.

Phân biệt rõ hai ý định:

| Mục đích | Cách biểu diễn |
| --- | --- |
| “Email này được bảo đảm duy nhất; cho tôi kết quả nếu có.” | `Optional<Customer> findByEmail(...)` |
| “Lấy khách hàng mới nhất trong nhóm, tối đa một document.” | `Optional<Customer> findFirstByStatusOrderByJoinedAtDescCustomerCodeAsc(...)` |
| “Lấy document có ID cụ thể.” | `findById(id)` kế thừa repository |

Kiểu trả về không phải cơ chế xác thực quy tắc dữ liệu. Nếu hệ thống cần xác định trùng email là lỗi, cần kiểm thử/kiểm soát từ luồng ghi và giám sát dữ liệu, không sử dụng `Top1` để làm ẩn bản ghi trùng.

## 6. `List<Customer>` và giới hạn dung lượng kết quả

Khai báo:

```java
List<Customer> findByStatus(String status);
```

có nghĩa trả các khách hàng phù hợp và ánh xạ chúng thành `List`. **Nó không tự động đặt giới hạn an toàn**. Nếu 300.000 document có status ACTIVE, ứng dụng có thể phải xử lý một kết quả cực lớn.

Một số trường hợp `List` hợp lý:

- `Top3`/`First5` đã giới hạn tại truy vấn.
- Tập kết quả có kích thước nhỏ theo quy tắc dữ liệu đã được kiểm soát.
- Tầng gọi đã dùng `Pageable` để đặt giới hạn và chỉ muốn nội dung, không cần tổng số.

Ví dụ khi phiên bản Spring Data Couchbase hỗ trợ tham số `Pageable` với kiểu trả về `List`:

```java
List<Customer> findByStatus(String status, Pageable pageable);
```

Lời gọi:

```java
List<Customer> rows = repository.findByStatus(
    "ACTIVE",
    org.springframework.data.domain.PageRequest.of(
        0,
        20,
        org.springframework.data.domain.Sort.by(
            org.springframework.data.domain.Sort.Order.desc("joinedAt"),
            org.springframework.data.domain.Sort.Order.asc("customerCode")
        )
    )
);
```

Đây là lựa chọn khi chỉ cần **dữ liệu trang**, không cần metadata tổng số. Cần kiểm chứng ở phiên bản thực tế rằng query creator áp dụng `LIMIT`/`OFFSET` ở phía Couchbase, không phải lấy toàn bộ rồi mới cắt `List` tại Java.

### 6.1. Không giới hạn sau khi đã tải dữ liệu

Cách làm dưới đây **không** giải quyết được chi phí query lớn:

```java
List<Customer> allActive = repository.findByStatus("ACTIVE");
List<Customer> firstTen = allActive.stream().limit(10).toList();
```

Dù `firstTen` chỉ có 10 phần tử, biến `allActive` đã chứa toàn bộ document khớp điều kiện. Tốn bộ nhớ, băng thông và thời gian truy vấn trước khi Java cắt danh sách. Giới hạn phải được **đẩy xuống query SQL++** khi mục tiêu là giảm tải ở Couchbase.

Tương tự, việc chọn một phần tử `list.get(0)` sau khi tải danh sách không tương đương `LIMIT 1` ở phía server.

## 7. `Page<Customer>`: phân trang và tổng số kết quả

Khi UI cần hiển thị “Trang 1/25” hoặc “Có 483 khách hàng”, `Page<T>` thích hợp vì chứa dữ liệu trang cùng thông tin tổng số.

Repository:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Customer> findByStatus(String status, Pageable pageable);
```

**Chọn một chữ ký cho cùng bộ tham số:** ở mục 6, dạng `List<Customer> findByStatus(String, Pageable)` được giới thiệu như một **phương án thay thế**. Java không cho phép cùng một interface khai báo thêm `Page<Customer> findByStatus(String, Pageable)` chỉ khác **kiểu trả về**. Khi cần hỗ trợ cả hai chiến lược, hãy đổi tên phương thức hoặc thiết kế API riêng, thay vì sao chép cả hai chữ ký vào một repository.

Lời gọi:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<Customer> page = repository.findByStatus(
    "ACTIVE",
    PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.desc("joinedAt"),
            Sort.Order.asc("customerCode")
        )
    )
);

List<Customer> rows = page.getContent();
int number = page.getNumber();       // Chỉ số trang, bắt đầu từ 0.
int size = page.getSize();           // Kích thước trang yêu cầu.
int returned = page.getNumberOfElements();
long total = page.getTotalElements();
int pages = page.getTotalPages();
boolean next = page.hasNext();
```

`PageRequest.of(0, 20, ...)` yêu cầu trang đầu tiên với kích thước tối đa 20. Nếu chỉ có 7 document khớp điều kiện, `getContent().size()` có thể bằng 7; `getSize()` vẫn là kích thước trang yêu cầu.

**Không nhầm:**

- `page.getNumberOfElements()`: số document **trong trang đang nhận**.
- `page.getTotalElements()`: tổng số document **khớp bộ lọc**, theo kết quả đếm mà repository cung cấp.
- `page.getTotalPages()`: số trang tính từ tổng số và kích thước trang.

### 7.1. Vì sao `Page` có thể đắt hơn `List` giới hạn?

Để biết tổng số bản ghi, repository thường phải thực hiện hoặc suy ra kết quả của **truy vấn count** ngoài truy vấn lấy dữ liệu. Truy vấn count cũng có thể cần index và tốn tài nguyên khi tập dữ liệu lớn.

Ví dụ logic của một trang:

```sql
-- Truy vấn lấy nội dung trang.
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC,
         c.`customer_code` ASC
LIMIT 20 OFFSET 0;
```

Và một truy vấn đếm tương ứng:

```sql
SELECT COUNT(1) AS total
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE";
```

Đây là SQL++ minh họa, không phải bản sao truy vấn tự động do Spring Data Couchbase sinh. Framework có thể bổ sung discriminator, metadata, projection hoặc tối ưu tránh count ở một số tình huống. Nếu UI không cần tổng số, không nên mặc định dùng `Page` cho mọi endpoint.

### 7.2. Thứ tự xác định là yêu cầu của phân trang

Một `Pageable` không có `Sort` có thể áp dụng `LIMIT`/`OFFSET` nhưng không đảm bảo thứ tự. SQL++ không cam kết trả document theo thứ tự ID hay thời điểm ghi nếu không có `ORDER BY`.

Ngay cả khi chỉ sắp theo `joinedAt DESC`, nhiều document có cùng thời điểm sẽ tạo nhóm có thứ tự nội bộ chưa xác định. Cần một **tie-breaker** như `customerCode ASC` được đảm bảo duy nhất và không bị thiếu để thứ tự trang ổn định tại thời điểm truy vấn.

Nếu dữ liệu bị chèn, xóa hoặc sửa giữa hai lần lấy trang, ngay cả thứ tự đã xác định vẫn có thể tạo hiện tượng trùng/lệch vị trí do offset. `Sort` không tự tạo snapshot bất biến qua nhiều request.

## 8. `Slice<Customer>`: khi chỉ cần biết có trang tiếp theo

Trong các module Spring Data hỗ trợ `Slice<T>`, loại này có thể trả nội dung một trang và trạng thái còn trang tiếp theo mà **không cần tổng số toàn bộ tập kết quả**. Nhiều implementation có thể dùng kỹ thuật lấy `pageSize + 1` kết quả để xác định `hasNext()` thay vì truy vấn đếm.

Một chữ ký minh họa:

```java
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Pageable;

// Xác minh hỗ trợ kiểu Slice trên phiên bản Spring Data Couchbase.
Slice<Customer> findByCity(String city, Pageable pageable);
```

Ứng dụng có thể đọc:

```java
Slice<Customer> slice = repository.findByCity(
    "HANOI",
    org.springframework.data.domain.PageRequest.of(
        0,
        20,
        org.springframework.data.domain.Sort.by("customerCode")
    )
);

List<Customer> rows = slice.getContent();
boolean hasNext = slice.hasNext();
```

**Caveat quan trọng:** `Slice` là một abstraction của Spring Data; khả năng dùng `Slice` như kiểu trả về của một derived query **cần xác minh theo phiên bản Spring Data Couchbase hiện hành**. Không mặc định repository Couchbase sẽ tự tối ưu lấy thêm một bản ghi giống cách một số Spring Data module khác hoạt động. Nếu không hỗ trợ `Slice`, có thể dùng truy vấn giới hạn `size + 1` thông qua API SQL++ phù hợp và tự dựng phản hồi có `hasNext`.

| Trường hợp | Ưu tiên xem xét |
| --- | --- |
| UI hiển thị tổng số và tổng trang chính xác | `Page<T>` |
| Nút “Xem thêm” chỉ cần biết còn bản ghi không | `Slice<T>` nếu được hỗ trợ |
| Tìm gợi ý, chỉ cần vài kết quả đầu | `TopN`/`FirstN` hoặc SQL++ `LIMIT` |
| API chỉ trả dữ liệu, không cần metadata tổng số | `List<T>` có giới hạn/query paging |

## 9. `countBy` và `existsBy`: đừng tải entity khi chỉ cần thống kê

Hai loại truy vấn chuyên biệt:

```java
long countByStatus(String status);

boolean existsByEmail(String email);
```

Ví dụ:

```java
long activeCount = repository.countByStatus("ACTIVE");

boolean emailPresent =
    repository.existsByEmail("lan@example.test");
```

`countByStatus` nhằm trả **số lượng** document thỏa điều kiện. `existsByEmail` nhằm trả **có hay không có ít nhất một document** theo email. Cả hai không nên được viết thay bằng `findByStatus(...).size()` hoặc `findByEmail(...).isPresent()` một cách máy móc khi cần tối ưu truy vấn.

Bảng lựa chọn:

| Chỉ cần | API nên cân nhắc | Lý do |
| --- | --- | --- |
| Có ít nhất một document khớp | `existsBy...` | Tránh ánh xạ toàn bộ entity chỉ để kiểm tra sự tồn tại. |
| Tổng số document khớp | `countBy...` | Tránh đưa tập lớn về Java để đếm. |
| Một entity theo ID | `findById(id)` | Truy cập theo key-value, không cần query theo field. |
| Một entity có điều kiện nghiệp vụ duy nhất | `Optional<T> findBy...` | Phản ánh kỳ vọng 0 hoặc 1 kết quả. |
| Một entity được chọn theo thứ tự | `First`/`Top` với `OrderBy` | Thể hiện rõ thứ tự và giới hạn một. |

`existsByEmail` **không** có nghĩa email là duy nhất; nó chỉ trả kết quả tồn tại. Nếu email trùng ở nhiều document, `existsByEmail` vẫn chỉ là true và không báo số lượng bản ghi bị trùng.

## 10. Bộ dữ liệu kiểm thử: `TopN`, `Page` và count

Giả sử collection chứa các document sau:

| ID | `customer_code` | `status` | `joined_at` |
| --- | --- | --- | --- |
| `c01` | C001 | ACTIVE | 2026-11-23T10:00:00Z |
| `c02` | C002 | ACTIVE | 2026-11-24T09:00:00Z |
| `c03` | C003 | ACTIVE | 2026-11-24T09:00:00Z |
| `c04` | C004 | SUSPENDED | 2026-11-25T06:00:00Z |
| `c05` | C005 | ACTIVE | 2026-11-22T18:00:00Z |
| `c06` | C006 | ACTIVE | 2026-11-20T12:00:00Z |

Với bộ lọc `status = "ACTIVE"` và thứ tự `joinedAt DESC, customerCode ASC`:

```text
c02 → c03 → c01 → c05 → c06
```

Mọi kết quả sau đây giả định phương thức tương ứng được phiên bản Spring Data Couchbase hỗ trợ, document có dữ liệu đúng kiểu và index cập nhật xong.

| Yêu cầu | Kết quả |
| --- | --- |
| `findFirstByStatusOrderByJoinedAtDescCustomerCodeAsc("ACTIVE")` | `c02` |
| `findTop3ByStatusOrderByJoinedAtDescCustomerCodeAsc("ACTIVE")` | `c02 → c03 → c01` |
| Trang 0, size 2 với sort tương ứng | `c02 → c03` |
| Trang 1, size 2 với sort tương ứng | `c01 → c05` |
| Trang 2, size 2 với sort tương ứng | `c06` |
| `countByStatus("ACTIVE")` | `5` |
| `countByStatus("SUSPENDED")` | `1` |
| `existsByStatus("ARCHIVED")`, nếu khai báo | `false` |

Không dùng `Top3` mà không có `OrderBy` nếu nghiệp vụ yêu cầu đúng ba document mới nhất. Khi `Top3` trả ít hơn ba kết quả, đó có thể là bình thường vì bộ lọc chỉ khớp ít document hơn giới hạn.

### 10.1. Giá trị biên cần kiểm tra

- **Không có kết quả:** `First` với `Optional` nên diễn đạt không có kết quả bằng `Optional.empty()` theo hợp đồng; danh sách/trang rỗng không đồng nghĩa lỗi.
- **Có ít hơn N:** `Top3` có thể trả 0, 1 hoặc 2 phần tử, không bắt buộc đúng 3.
- **Có đúng N:** query trả N phần tử và không thể suy ra “còn dữ liệu hay không” chỉ từ việc danh sách có kích thước N.
- **Có nhiều hơn N:** `Top3` phải lấy tối đa 3; việc chọn đúng 3 nào phụ thuộc `OrderBy`.
- **Cùng giá trị sort:** phải dùng khóa phụ.
- **Document bị xóa hoặc TTL hết hạn:** tổng số và kết quả có thể khác giữa các lần gọi.

## 11. `LIMIT` và `OFFSET` ở SQL++ cần được hiểu thế nào?

SQL++ có `LIMIT` để giới hạn số dòng kết quả và `OFFSET` để bỏ qua một số dòng. Ví dụ:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC,
         c.`customer_code` ASC
LIMIT 20 OFFSET 40;
```

Ý định là lấy trang có offset 40, tối đa 20 document tiếp theo trong thứ tự đã định. Ứng dụng Spring Data thường diễn đạt yêu cầu này bằng `PageRequest.of(2, 20, sort)`, vì chỉ số trang bắt đầu từ 0.

Phân biệt hai phép toán:

- `LIMIT 20`: tối đa 20 document **được trả về ở truy vấn này**.
- `OFFSET 40`: bỏ qua 40 document trong tập đã lọc/sắp xếp để tới điểm bắt đầu trang; nó **không** làm câu truy vấn “đọc đúng 20 document từ index” theo nghĩa chi phí cố định.

Offset lớn có thể gây tốn tài nguyên vì Query Service vẫn cần xác định/đi qua lượng dữ liệu trước vị trí cần lấy. Để duyệt tập dữ liệu rất lớn, cân nhắc phân trang theo khóa tiếp nối (*keyset pagination*) với các giá trị sort cuối trang trước, nếu nghiệp vụ cho phép.

### 11.1. Keyset khác offset ra sao?

Với `ORDER BY joined_at DESC, customer_code ASC`, trang sau có thể tiếp tục từ cặp cuối trang trước `($lastJoinedAt, $lastCode)` bằng điều kiện minh họa:

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

Với hướng DESC của thời gian, những document đứng sau có `joined_at` nhỏ hơn; nếu thời gian bằng nhau, mã ASC lớn hơn mới đứng sau. Ví dụ này đòi hỏi hai khóa có kiểu nhất quán, không null/missing và mã duy nhất theo nghiệp vụ.

Derived query có tên ngắn thường không diễn đạt thuận tiện điều kiện keyset phức tạp. Có thể dùng `@Query`/`CouchbaseTemplate` với binding tham số và projection metadata phù hợp phiên bản, hoặc các API scrolling mà Spring Data Couchbase thực sự hỗ trợ sau khi xác minh.

## 12. Index cho lọc, sắp xếp và giới hạn

`LIMIT 10` không bảo đảm truy vấn nhẹ nếu backend phải quét và sắp xếp hàng trăm nghìn document để xác định 10 document cần lấy. Index phải được thiết kế theo **điều kiện lọc và thứ tự**.

Giả sử câu SQL++ của Spring Data có điều kiện type discriminator `_class`. Một index minh họa:

```sql
CREATE INDEX ix_customers_type_status_joined_code
ON `app`.`crm`.`customers` (
    `_class`,
    `status`,
    `joined_at` DESC,
    `customer_code` ASC
);
```

Index này có thể hỗ trợ truy vấn:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`_class` = "example.crm.Customer"
  AND c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC, c.`customer_code` ASC
LIMIT 10;
```

**Lưu ý:** Đây là minh họa. Spring Data Couchbase có thể cấu hình discriminator khác, thay đổi projection, hoặc không sinh `_class` đúng như ví dụ. Phải so sánh với SQL++ thực tế, document JSON thật và index đang có trước khi tạo/chọn index.

Các nguyên tắc thực hành:

1. Trường lọc equality thường phù hợp đứng trước khóa sort trong một composite index, nhưng thứ tự tối ưu cần dựa trên workload.
2. Chiều `ASC`/`DESC` trong index có thể ảnh hưởng khả năng tránh sort ở Query Service.
3. Một index theo `status, joined_at` không mặc định tối ưu cho tìm tất cả document chỉ sắp theo `joined_at`.
4. Một số index có thể bỏ document thiếu trường key theo cấu hình/phiên bản; phải kiểm tra tính đúng đắn khi `joined_at` là `MISSING`.
5. Index mới tăng chi phí ghi, lưu trữ và vận hành. Không tạo một index riêng cho mọi giới hạn `Top1`, `Top3`, `Top10` nếu chúng dùng cùng đường truy cập.

### 12.1. `EXPLAIN` và cách kiểm tra

```sql
EXPLAIN
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC,
         c.`customer_code` ASC
LIMIT 10;
```

Khi đánh giá thật, cần đưa vào các predicate/discriminator mà Spring Data sinh ra. Xem index nào được dùng, có bước sort/fetch không, lượng phần tử quét và chi phí `OFFSET`. Đối chiếu cả độ trễ thực thi thực tế ở dữ liệu đại diện.

Không chỉ kiểm tra “query có trả đúng 10 document không”; một truy vấn đúng số kết quả nhưng cần quét hàng triệu document vẫn có thể không đáp ứng tải sản xuất.

## 13. Trả về reactive: `Mono`, `Flux` và bẫy giới hạn phía client

Với Spring Data Couchbase reactive repository:

```java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Mono<Customer> findById(String id);

    // Kiểm chứng hỗ trợ của First/Top trên phiên bản reactive cụ thể.
    Mono<Customer> findFirstByStatusOrderByJoinedAtDescCustomerCodeAsc(
        String status
    );

    Flux<Customer> findTop3ByStatusOrderByJoinedAtDescCustomerCodeAsc(
        String status
    );

    Flux<Customer> findByStatus(String status);
}
```

`Mono<Customer>` biểu diễn tối đa một entity, còn `Flux<Customer>` biểu diễn một luồng có thể có nhiều entity. **Kiểu reactive không mặc định giới hạn số document ở phía Couchbase.**

Xét:

```java
Flux<Customer> firstThree =
    reactiveRepository.findByStatus("ACTIVE").take(3);
```

`take(3)` là một toán tử Reactor trên publisher. Nó có thể dừng yêu cầu thêm/huỷ subscription tùy pipeline, nhưng **không được xem là bằng chứng SQL++ đã có `LIMIT 3`**. Query Service có thể đã lập kế hoạch hoặc bắt đầu tạo luồng kết quả lớn. Khi mục tiêu chính là tối ưu truy vấn, ưu tiên một API đặt giới hạn **ở query**, sau đó mới tiêu thụ `Flux`.

Tương tự, `Mono<Customer>` trên một phương thức truy vấn trường không có giới hạn/duy nhất không tự thay thế quy tắc dữ liệu 0..1. Cần dùng `findById` khi biết khóa hoặc dùng truy vấn có giới hạn/sắp xếp rõ ràng.

Không gọi `block()` trong luồng web reactive nếu không có thiết kế cô lập blocking phù hợp.

## 14. Projection và streaming: giảm dữ liệu không chỉ bằng số dòng

Ngoài giới hạn **số document**, một API còn có thể giảm lượng dữ liệu truyền bằng cách chỉ lấy **những trường cần dùng**. Ví dụ màn hình gợi ý có thể chỉ cần mã, tên, thành phố chứ không cần toàn bộ document.

Trong Spring Data, một số dạng projection/interface DTO được hỗ trợ tùy module và phiên bản. Tuy nhiên, việc khai báo một kiểu trả về không phải entity **không tự bảo đảm Couchbase chỉ fetch các trường đó**. Cần kiểm tra projection, metadata mapping và SQL++ thực tế.

Một truy vấn SQL++ minh họa:

```sql
SELECT c.`customer_code` AS customerCode,
       c.`display_name` AS displayName,
       c.`city` AS city
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
ORDER BY c.`joined_at` DESC,
         c.`customer_code` ASC
LIMIT 10;
```

Ví dụ trên trả một tập dữ liệu nhỏ hơn về **số trường** và **số dòng**. Muốn mapping ra DTO/projection qua `@Query` hoặc `CouchbaseTemplate`, phải dùng quy ước projection/binding của Spring Data Couchbase phiên bản cụ thể.

Một số Spring Data module cho phép kiểu trả về `Stream<T>` để tiêu thụ dữ liệu tuần tự. Không tự áp dụng cơ chế đó cho Couchbase khi chưa xác minh hỗ trợ và cách giải phóng tài nguyên. Ngay cả khi hỗ trợ stream, **streaming không đồng nghĩa SQL++ có LIMIT**: hai khái niệm cần được thiết kế riêng.

## 15. `NULL`, `MISSING`, TTL và consistency ảnh hưởng tập kết quả

### 15.1. Document có field sort thiếu hoặc sai kiểu

Nếu document không có `joined_at`, hoặc có `joined_at = null`, thì thứ tự thực thi `ORDER BY joined_at DESC` có thể khác kỳ vọng về “mới nhất”. Nếu field lưu trộn kiểu chuỗi ISO 8601 và số timestamp, kết quả sort cũng có thể không phù hợp thứ tự thời gian.

Cần chuẩn hóa dữ liệu hoặc dùng biểu thức SQL++ rõ ràng, đồng thời kiểm tra index. Trong môi trường production, một `Top3` sắp xếp sai kiểu có thể chọn “ba bản ghi mới nhất” không đúng, dù số lượng trả về chính xác.

### 15.2. TTL làm tổng số thay đổi

Document có TTL sẽ hết hạn theo thời gian. Giả sử `countByStatus("ACTIVE")` trả 5, một document hết hạn trước khi UI gọi trang tiếp theo: tổng số và danh sách có thể giảm. Đây không nhất thiết là lỗi của repository hay phân trang, mà là đặc tính dữ liệu thay đổi.

Nếu ứng dụng cần một báo cáo bất biến, phải thiết kế snapshot hoặc một nguồn dữ liệu lịch sử phù hợp; `Page` và `Top` tự chúng không giữ một ảnh chụp dữ liệu.

### 15.3. Query index consistency

```text
save(customer)             -> ghi key-value thành công
findById(customer.id)      -> đọc theo document ID
findTop3ByStatus...()      -> truy vấn SQL++ qua index
```

Query Service và index có thể cập nhật chậm hơn đường key-value. Ngay sau khi ghi một khách hàng mới có `joined_at` lớn nhất, kết quả `Top3` theo trường có thể **chưa bao gồm document mới** ở mức query consistency thông thường.

Nếu yêu cầu đọc ngay kết quả ghi vừa xong, cần xem xét query scan consistency thích hợp, chẳng hạn mức tương đương `REQUEST_PLUS` nếu API phiên bản hỗ trợ, hoặc thiết kế truy cập theo ID. Consistency mạnh hơn có thể tăng thời gian chờ. Không đồng nhất “đúng thứ tự” với “đã đọc thấy mọi ghi mới nhất”.

### 15.4. CAS và giao dịch

- **CAS/optimistic locking:** Nếu cập nhật `joinedAt`, `status` hoặc `customerCode` đồng thời, cần phát hiện xung đột ghi theo cơ chế phù hợp. Kết quả `findTop3...` không khóa những document đã trả về.
- **Giao dịch:** Các lần lấy `Page`, `countBy` và `Top` riêng lẻ không tự tham gia một giao dịch hay snapshot chung. Đừng giả định `totalElements` và từng trang luôn phản ánh một trạng thái toàn cục bất biến, nhất là khi có cập nhật liên tục.
- **Scope/collection:** Nếu repository và index trỏ tới namespace khác nhau, truy vấn có thể rỗng/chậm hoặc không đúng dữ liệu. Phải xác minh mapping bucket/scope/collection trước khi tối ưu giới hạn.

## 16. Thực hành: chọn đúng API cho yêu cầu

Dùng bộ dữ liệu `c01`–`c06` ở mục 10. Với khách hàng ACTIVE, thứ tự `joinedAt DESC, customerCode ASC` là:

```text
c02 → c03 → c01 → c05 → c06
```

**Bài A — Chỉ cần một khách hàng ACTIVE mới nhất.**

```java
Optional<Customer> findFirstByStatusOrderByJoinedAtDescCustomerCodeAsc(
    String status
);
```

Gọi với `"ACTIVE"` → dự kiến `c02`. Vì `c02` và `c03` có cùng ngày, mã `C002` đứng trước `C003`.

**Bài B — Lấy ba người mới nhất để làm widget.**

```java
List<Customer> findTop3ByStatusOrderByJoinedAtDescCustomerCodeAsc(
    String status
);
```

Kết quả `c02 → c03 → c01`, không cần tải toàn bộ năm người ACTIVE rồi cắt trên Java.

**Bài C — Hiển thị trang 2, mỗi trang hai người.**

```java
PageRequest.of(
    1,
    2,
    Sort.by(
        Sort.Order.desc("joinedAt"),
        Sort.Order.asc("customerCode")
    )
);
```

Vì trang đếm từ 0, đây là trang thứ hai. Kết quả dự kiến `c01 → c05`. Nếu truy vấn trả `Page` và tập dữ liệu ổn định, `totalElements` là 5, `totalPages` là 3.

**Bài D — Kiểm tra sự tồn tại.** Nếu chỉ cần biết có khách hàng status ARCHIVED hay không, chọn `existsByStatus("ARCHIVED")` (cần khai báo chữ ký tương ứng), không lấy danh sách rồi kiểm tra `isEmpty()`.

**Bài E — Thống kê.** Nếu giao diện chỉ cần tổng khách hàng ACTIVE, chọn `countByStatus("ACTIVE")`, không dùng `findByStatus(...).size()` để đếm dữ liệu lớn.

**Bài F — Tiếp tục tải sau trang đầu.** Nếu UI chỉ có nút “Xem thêm”, hãy đánh giá `Slice` trên đúng phiên bản Couchbase hoặc một truy vấn `LIMIT size+1` tự quản lý cờ `hasNext`. Không phải lúc nào cũng cần `Page` cùng một truy vấn count đắt tiền.

**Bài G — Phân trang khi dữ liệu thay đổi.** Giả sử người dùng mở trang đầu, rồi một document mới được thêm vào đầu danh sách trước khi mở trang hai. Hãy giải thích vì sao offset có thể trả trùng hoặc bỏ sót document, dù `Sort` có khóa phụ. Đề xuất dùng keyset cursor nếu sản phẩm chấp nhận truy cập tuần tự, đồng thời quy định consistency và thời điểm chốt dữ liệu nếu cần snapshot.

### Bảng kiểm trước khi đưa chức năng vào ứng dụng

| Câu hỏi | Hệ quả nếu bỏ qua |
| --- | --- |
| Nghiệp vụ cần tối đa một, tối đa N hay một trang? | Có thể tải nhiều document không cần thiết. |
| Thứ tự `OrderBy`/`Sort` có xác định rõ không? | `First`/`Top` có thể chọn bản ghi tùy ý. |
| Có khóa phụ duy nhất và không thiếu không? | Trang có thể không ổn định khi nhiều document cùng ngày. |
| `Optional` có phản ánh kỳ vọng duy nhất không? | Có thể che giấu lỗi dữ liệu hoặc lỗi nhiều kết quả. |
| `Page` có cần tổng số thật không? | Count query có thể tăng tải đáng kể. |
| `Slice`/`Top` có được phiên bản Couchbase hỗ trợ không? | Query creator có thể không sinh `LIMIT` như kỳ vọng. |
| Có đặt giới hạn ở SQL++ hay chỉ cắt tại Java/`Flux`? | Giới hạn phía client không nhất thiết tiết kiệm tài nguyên Query Service. |
| Kích thước trang, offset và sort có được giới hạn? | Người dùng có thể gây truy vấn quá tốn tài nguyên. |
| Index hỗ trợ `WHERE + ORDER BY + LIMIT` chưa? | Trả 10 dòng vẫn có thể cần quét/sort tập rất lớn. |
| `NULL`/`MISSING`/kiểu thời gian có nhất quán không? | Sai “mới nhất” và sai ranh giới trang. |
| Có chấp nhận index chưa kịp cập nhật sau `save` không? | TopN/trang có thể thiếu document mới trong thời gian ngắn. |
| Dữ liệu có TTL hoặc cập nhật giữa các trang không? | Số lượng và vị trí kết quả có thể thay đổi. |

## 17. Ghi nhớ

**`First`/`Top`** mô tả giới hạn kết quả ở mức tên phương thức, **`Optional`** mô tả kỳ vọng đơn trị, **`List`** trả tập entity, **`Page`** phục vụ phân trang cần tổng số, còn **`countBy`** và **`existsBy`** trả đúng thông tin thống kê cần dùng. `Slice` hữu ích về mặt khái niệm khi không cần tổng số, nhưng cần xác minh hỗ trợ trong phiên bản Spring Data Couchbase cụ thể. Với reactive, `Mono`/`Flux` không tự có ý nghĩa SQL++ `LIMIT`.

Một truy vấn giới hạn đúng phải có **điều kiện lọc**, **thứ tự xác định**, **giới hạn được đẩy xuống Couchbase** và **index phù hợp**. Tránh cắt `List` sau khi tải, tránh `Top1` để che giấu dữ liệu trùng, và không mặc định một `Page` là snapshot nhất quán của tập dữ liệu đang thay đổi. Khi cần keyset, projection, count tối ưu hoặc truy vấn phức tạp, dùng `@Query`/`CouchbaseTemplate` và đánh giá SQL++ thực tế bằng `EXPLAIN`.
