# Toán tử so sánh, khoảng giá trị và tập giá trị

Trong **SPRING_DATA_COUCHBASE**, truy vấn dẫn xuất (*derived query*) cho phép thể hiện điều kiện lọc bằng tên phương thức của Spring Data repository. Ngoài so khớp bằng nhau, ứng dụng thường cần tìm document có điểm tích lũy **lớn hơn ngưỡng**, giá trị **nằm trong khoảng**, hoặc thuộc **một tập giá trị**. Các điều kiện này được khai báo bằng những hậu tố như `GreaterThan`, `Between` và `In`.

Bài thuộc chương **Truy vấn dẫn xuất** và tập trung vào **toán tử so sánh, khoảng giá trị và tập giá trị**. Trong Couchbase, Spring Data diễn giải thuộc tính Java, ánh xạ sang trường JSON rồi tạo truy vấn **SQL++**. Để sử dụng đúng các toán tử, phải quan tâm đến kiểu dữ liệu, ranh giới bao gồm/không bao gồm, `NULL`/`MISSING`, index và độ mới của chỉ mục sau khi ghi. Đây là một mắt xích trong việc xây dựng tầng truy cập Couchbase với document mapping, repository, `CouchbaseTemplate`; thiết kế bucket/scope/collection, TTL, CAS, giao dịch và reactive vẫn ảnh hưởng đến hành vi vận hành toàn hệ thống.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Viết và giải thích các phương thức `findBy...GreaterThan`, `GreaterThanEqual`, `LessThan`, `LessThanEqual`, `Between` và `In`.
2. Phân biệt `>` với `>=`, `<` với `<=`, cũng như xác định hai biên của `BETWEEN`.
3. Sử dụng tham số tập giá trị đúng cách, kể cả khi input rỗng hoặc chứa giá trị trùng lặp.
4. Kết hợp các toán tử với `And`/`Or` mà không làm sai thứ tự tham số hoặc nhóm điều kiện.
5. Giải thích những tình huống bất ngờ do kiểu JSON, `NULL`/`MISSING` và query consistency.
6. Thiết kế index tương ứng với truy vấn equality + range, đồng thời kiểm thử các giá trị biên.
7. Biết khi nào nên viết SQL++ tường minh qua `@Query` hoặc `CouchbaseTemplate`.

## 2. Bối cảnh ví dụ: phân nhóm khách hàng

Giả sử hệ thống CRM sử dụng bucket `app`, scope `crm` và collection `customers`. Mỗi document có thông tin trạng thái, thành phố, điểm tích lũy và tổng chi tiêu (đơn vị nhỏ nhất của tiền tệ để tránh lưu số thực làm tiền):

```json
{
  "status": "ACTIVE",
  "city": "HANOI",
  "loyalty_points": 150,
  "total_spent_minor": 2500000
}
```

Một entity Java có thể viết như sau:

```java
package example.crm;

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

    @Field
    private String city;

    @Field("loyalty_points")
    private Integer loyaltyPoints;

    @Field("total_spent_minor")
    private Long totalSpentMinor;

    protected Customer() {
        // Cho Spring Data mapping.
    }

    // Constructor nghiệp vụ, getters/setters được lược bỏ.
}
```

Đặt tên phương thức theo **thuộc tính Java**, không theo tên field lưu trong JSON: `LoyaltyPoints` là phần tên tương ứng với `loyaltyPoints`, còn `loyalty_points` được giải quyết qua `@Field`.

Mẫu repository:

```java
package example.crm;

import java.util.Collection;
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    List<Customer> findByLoyaltyPointsGreaterThan(Integer min);
    List<Customer> findByLoyaltyPointsGreaterThanEqual(Integer min);
    List<Customer> findByLoyaltyPointsLessThan(Integer max);
    List<Customer> findByLoyaltyPointsLessThanEqual(Integer max);

    List<Customer> findByLoyaltyPointsBetween(Integer lower, Integer upper);
    List<Customer> findByLoyaltyPointsIn(Collection<Integer> values);

    List<Customer> findByStatusAndLoyaltyPointsGreaterThan(
        String status, Integer min
    );

    List<Customer> findByStatusAndLoyaltyPointsBetween(
        String status, Integer lower, Integer upper
    );

    List<Customer> findByStatusAndCityIn(
        String status, Collection<String> cities
    );
}
```

**Lưu ý phiên bản:** Bộ từ khóa có thể khác nhau giữa các Spring Data module và các phiên bản Spring Data Couchbase. Các ví dụ dùng cú pháp dẫn xuất phổ biến; trước khi triển khai trên phiên bản cụ thể, xác minh các từ khóa được Couchbase repository hỗ trợ và kiểm tra câu SQL++ được sinh ra. Không suy diễn rằng mọi từ khóa của Spring Data JPA hoạt động giống hệt trên Couchbase.

## 3. Các toán tử so sánh lớn hơn và nhỏ hơn

### 3.1. Bảng đối chiếu chính xác về ranh giới

| Hậu tố phương thức | Ý nghĩa toán học | SQL++ minh họa | Có lấy giá trị đúng bằng ngưỡng? |
| --- | --- | --- | --- |
| `GreaterThan` | `x > p` | `x > $p` | Không |
| `GreaterThanEqual` | `x >= p` | `x >= $p` | Có |
| `LessThan` | `x < p` | `x < $p` | Không |
| `LessThanEqual` | `x <= p` | `x <= $p` | Có |

Giả sử có các mức điểm `99`, `100`, `101`. Khi truyền tham số `100`, kết quả như sau:

| Điều kiện | 99 | 100 | 101 |
| --- | :---: | :---: | :---: |
| `GreaterThan(100)` | ✗ | ✗ | ✓ |
| `GreaterThanEqual(100)` | ✗ | ✓ | ✓ |
| `LessThan(100)` | ✓ | ✗ | ✗ |
| `LessThanEqual(100)` | ✓ | ✓ | ✗ |

Đây là điểm dễ sai nhất trong yêu cầu nghiệp vụ. Câu “hơn 100 điểm” tương ứng với `> 100`; câu “từ 100 điểm trở lên” tương ứng với `>= 100`.

### 3.2. Ví dụ gọi repository

```java
List<Customer> above100 =
    repository.findByLoyaltyPointsGreaterThan(100);

List<Customer> atLeast100 =
    repository.findByLoyaltyPointsGreaterThanEqual(100);

List<Customer> below100 =
    repository.findByLoyaltyPointsLessThan(100);

List<Customer> atMost100 =
    repository.findByLoyaltyPointsLessThanEqual(100);
```

Ví dụ SQL++ biểu đạt logic của `findByLoyaltyPointsGreaterThan(100)`:

```sql
-- Chỉ minh họa điều kiện, không phải SQL++ nguyên văn Spring Data sinh ra.
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`loyalty_points` > $minPoints;
```

Spring Data có thể thêm điều kiện phân biệt loại entity, field metadata của document và các binding tham số khác. Khi tối ưu index, dùng truy vấn thực sự xuất hiện trong log hoặc cấu hình truy vấn của phiên bản đang triển khai.

### 3.3. Kết hợp điều kiện bằng nhau với điều kiện khoảng

```java
List<Customer> activeAbove100 =
    repository.findByStatusAndLoyaltyPointsGreaterThan("ACTIVE", 100);
```

Ý nghĩa:

```sql
WHERE c.`status` = "ACTIVE"
  AND c.`loyalty_points` > 100
```

Chỉ thay `GreaterThan` bằng `GreaterThanEqual` khi thật sự muốn đưa giá trị biên vào tập kết quả. Không chọn hậu tố theo cảm giác: thay đổi này ảnh hưởng trực tiếp đến tập khách hàng được gắn nhãn, tính điểm hoặc cấp quyền.

### 3.4. So sánh số, chuỗi và thời gian

Toán tử quan hệ có thể có ý nghĩa khác nhau theo kiểu JSON:

- Với số, `100 > 99` diễn đạt thứ tự số học.
- Với chuỗi, kết quả sắp xếp/so sánh theo quy tắc của SQL++ và collation tương ứng, không nên giả định giống thứ tự ngôn ngữ tự nhiên.
- Với thời gian, phải thống nhất kiểu lưu trữ và định dạng. Nếu lưu chuỗi ISO 8601, cần chuẩn hóa múi giờ và định dạng; không dựa vào so sánh chuỗi khi dữ liệu thời gian có nhiều kiểu trình bày khác nhau.
- Với tiền, ưu tiên một biểu diễn số nguyên đơn vị nhỏ nhất phù hợp hoặc một quy ước biểu diễn đáng tin cậy; tránh dùng `double` cho logic chính xác về tiền.

Không mặc định rằng property Java kiểu `Instant` có thể so sánh giống nhau trên mọi cách cấu hình converter Couchbase. Kiểm tra **giá trị JSON thực tế** trong collection trước khi xây dựng bộ lọc thời gian.

## 4. Khoảng giá trị với `Between`

### 4.1. Hai ranh giới của khoảng

Phương thức:

```java
List<Customer> findByLoyaltyPointsBetween(
    Integer lower,
    Integer upper
);
```

Lời gọi:

```java
List<Customer> group =
    repository.findByLoyaltyPointsBetween(100, 150);
```

thể hiện khoảng đóng trong cú pháp SQL++ thông thường:

```sql
WHERE c.`loyalty_points` BETWEEN 100 AND 150
```

Với SQL++ `BETWEEN a AND b`, hai cận được **bao gồm** khi áp dụng đúng ngữ nghĩa khoảng này. Vì vậy giá trị `100`, `125` và `150` đều thỏa; `99` và `151` thì không.

| Điểm | `Between(100, 150)` | Giải thích |
| ---: | :---: | --- |
| 99 | ✗ | Nhỏ hơn cận dưới |
| 100 | ✓ | Đúng cận dưới |
| 125 | ✓ | Bên trong |
| 150 | ✓ | Đúng cận trên |
| 151 | ✗ | Vượt cận trên |

Nếu yêu cầu là **100 ≤ điểm < 150**, `Between(100, 150)` sẽ không diễn đạt đúng vì lấy cả 150. Khi đó cân nhắc kết hợp `GreaterThanEqual` với `LessThan`:

```java
List<Customer>
findByLoyaltyPointsGreaterThanEqualAndLoyaltyPointsLessThan(
    Integer lowerInclusive,
    Integer upperExclusive
);
```

Lời gọi `(100, 150)` nhằm diễn đạt `100 <= loyalty_points AND loyalty_points < 150`. Ví dụ này còn cho thấy cùng một property có thể xuất hiện hai lần trong tên phương thức với hai toán tử khác nhau.

### 4.2. Cận dưới lớn hơn cận trên

Đầu vào `Between(150, 100)` không có ý nghĩa khoảng tăng dần như mong đợi. Không nên trông chờ Spring Data tự đổi thứ tự cận. Xử lý trước khi gọi repository:

```java
public List<Customer> findCustomersByPointRange(
    Integer lower,
    Integer upper,
    CustomerRepository repository
) {
    if (lower == null || upper == null) {
        throw new IllegalArgumentException("Phải nhập đủ hai cận");
    }
    if (lower > upper) {
        throw new IllegalArgumentException(
            "Cận dưới không được lớn hơn cận trên"
        );
    }
    return repository.findByLoyaltyPointsBetween(lower, upper);
}
```

Nếu ứng dụng chấp nhận khoảng một điểm duy nhất, `Between(100, 100)` có thể lấy các document có điểm đúng 100. Nếu nghiệp vụ không cho phép khoảng có hai cận bằng nhau, điều kiện validation phải rõ ràng tại service.

### 4.3. Khoảng ngày giờ: nửa mở thường phù hợp hơn

Một màn hình thống kê yêu cầu đơn hàng trong **ngày 25/11 theo giờ Việt Nam**. Cách diễn đạt khoảng ngày giờ thường dễ an toàn hơn với dạng:

```text
createdAt >= startOfDay
AND
createdAt < startOfNextDay
```

Khoảng `[start, nextStart)` tránh phải tạo “thời điểm cuối ngày” theo độ chính xác mili giây/nano giây. Tuy nhiên, cần:

1. Xác định múi giờ nghiệp vụ và chuyển hai thời điểm cận về biểu diễn được lưu trong Couchbase.
2. Áp dụng converter/kiểu dữ liệu nhất quán giữa document JSON và tham số truy vấn.
3. Kiểm tra cách phiên bản Spring Data Couchbase hỗ trợ derived query trên trường thời gian.

Ví dụ chữ ký thể hiện ý định nếu entity có property `createdAt`:

```java
List<Order> findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
    java.time.Instant fromInclusive,
    java.time.Instant toExclusive
);
```

`Order` chỉ là entity minh họa cho bài toán thời gian; ví dụ không yêu cầu tạo entity hoặc collection ngoài phạm vi tài liệu. Nếu converter và kiểu lưu trữ ngày giờ của ứng dụng khác dự kiến, có thể dùng `@Query` với biểu thức SQL++ tương thích.

## 5. Tập giá trị với `In`

### 5.1. Một property khớp với nhiều giá trị

Giả sử cần tìm khách hàng ở một trong ba thành phố:

```java
List<Customer> findByCityIn(java.util.Collection<String> cities);
```

Gọi:

```java
List<Customer> customers = repository.findByCityIn(
    java.util.List.of("HANOI", "DANANG", "HCM")
);
```

Điều kiện ý tưởng:

```sql
WHERE c.`city` IN ["HANOI", "DANANG", "HCM"]
```

Đây là biểu thức kiểm tra **một trường** thuộc một tập giá trị. Nó khác với `city = "HANOI" AND city = "DANANG"`, điều kiện mà một giá trị đơn thường không thể đồng thời thỏa.

Với tập giá trị cho trước, `In` giúp tránh nối chuỗi tên phương thức `findByCityOrCityOrCity...`. Số lượng phần tử nằm trong tham số của phương thức, không bị cố định bởi tên method.

### 5.2. Kết hợp tập giá trị với điều kiện khác

```java
List<Customer> activeInSelectedCities =
    repository.findByStatusAndCityIn(
        "ACTIVE",
        java.util.List.of("HANOI", "DANANG")
    );
```

Ý nghĩa:

```sql
WHERE c.`status` = "ACTIVE"
  AND c.`city` IN ["HANOI", "DANANG"]
```

Nếu thêm khoảng điểm:

```java
List<Customer> findByStatusAndCityInAndLoyaltyPointsBetween(
    String status,
    java.util.Collection<String> cities,
    Integer lower,
    Integer upper
);
```

thì thứ tự tham số phải là **status → cities → lower → upper**. Không cần làm phức tạp tên phương thức khi chỉ có hai hoặc ba điều kiện rõ ràng; nhưng nếu tập bộ lọc thay đổi động theo request thì dùng API truy vấn tường minh sẽ dễ bảo trì hơn.

### 5.3. Trường hợp tập rỗng, null và trùng lặp

Những trường hợp không nên bỏ qua:

| Đầu vào | Vấn đề | Quy tắc tầng service nên xác định |
| --- | --- | --- |
| `[]` | Không có giá trị nào được chọn. | Có thể trả tập rỗng trước truy vấn nếu đó là ý định nghiệp vụ. |
| `null` | Không có danh sách được cung cấp. | Phân biệt “không áp dụng filter” với “input không hợp lệ”. |
| `["HANOI", "HANOI"]` | Trùng giá trị. | Có thể loại trùng trước khi gọi repository. |
| Danh sách quá dài | Tăng kích thước tham số/truy vấn và chi phí thực thi. | Đặt giới hạn hợp lý; cân nhắc mô hình truy vấn khác nếu cần. |
| Tập chứa `null` | Ngữ nghĩa SQL++ có thể không giống giá trị thường. | Tách xử lý null/missing một cách có chủ đích. |

Đừng dựa vào hành vi ngầm khi truyền collection rỗng hoặc null cho repository, vì có thể phụ thuộc phiên bản. Tầng service nên đưa ra hợp đồng đầu vào rõ ràng.

Ví dụ tách trạng thái rỗng theo quy tắc “không chọn thành phố nào ⇒ không có kết quả”:

```java
public List<Customer> findInCities(
    java.util.Collection<String> cities,
    CustomerRepository repository
) {
    if (cities == null) {
        throw new IllegalArgumentException("cities không được null");
    }
    if (cities.isEmpty()) {
        return java.util.List.of();
    }
    return repository.findByCityIn(cities);
}
```

### 5.4. Phủ định tập giá trị: `NotIn`

Trong Spring Data, `NotIn` thường biểu đạt “giá trị không nằm trong tập”:

```java
// Chỉ dùng khi phiên bản Spring Data Couchbase thực tế hỗ trợ.
List<Customer> findByStatusNotIn(
    java.util.Collection<String> excludedStatuses
);
```

Trong SQL++ cần đặc biệt chú ý đến `NULL`/`MISSING` và ngữ nghĩa ba trị. `NOT IN` không đồng nghĩa “mọi document ngoài tập đều được lấy”, nhất là khi trường bị thiếu hoặc mảng đầu vào chứa null. Hãy kiểm thử các trường hợp này; nếu cần logic loại trừ chính xác, dùng `@Query` và diễn đạt điều kiện tường minh.

## 6. Ví dụ dữ liệu kiểm tra ranh giới

Giả sử `customers` có các bản ghi:

| ID | `status` | `city` | `loyalty_points` |
| --- | --- | --- | ---: |
| `c01` | ACTIVE | HANOI | 99 |
| `c02` | ACTIVE | DANANG | 100 |
| `c03` | ACTIVE | HANOI | 149 |
| `c04` | SUSPENDED | HANOI | 150 |
| `c05` | ACTIVE | HCM | 151 |
| `c06` | ACTIVE | DANANG | 200 |

Đối chiếu **tập ID** cần trả về:

| Gọi repository | Tập ID mong đợi |
| --- | --- |
| `findByLoyaltyPointsGreaterThan(100)` | `{c03, c04, c05, c06}` |
| `findByLoyaltyPointsGreaterThanEqual(100)` | `{c02, c03, c04, c05, c06}` |
| `findByLoyaltyPointsLessThan(100)` | `{c01}` |
| `findByLoyaltyPointsLessThanEqual(100)` | `{c01, c02}` |
| `findByLoyaltyPointsBetween(100, 150)` | `{c02, c03, c04}` |
| `findByLoyaltyPointsIn(List.of(100, 150, 200))` | `{c02, c04, c06}` |
| `findByStatusAndLoyaltyPointsBetween("ACTIVE", 100, 150)` | `{c02, c03}` |
| `findByStatusAndCityIn("ACTIVE", List.of("HANOI", "DANANG"))` | `{c01, c02, c03, c06}` |

Các tập ID được viết không theo thứ tự: nếu không khai báo `Sort`/`OrderBy` thì SQL++ không đảm bảo thứ tự ổn định.

### 6.1. `Between` và `In` không thay thế hoàn toàn cho nhau

- `Between(100, 150)` chấp nhận **mọi điểm trong khoảng**: 100, 101, 102, ..., 150.
- `In([100, 150])` chỉ chấp nhận **hai giá trị cụ thể** là 100 và 150.
- `In([100, 150, 200])` bao gồm 200, dù nằm ngoài khoảng 100–150.

Một lỗi dễ mắc là dùng `In` khi sản phẩm yêu cầu dải liên tục, hoặc dùng `Between` khi chỉ có vài mã/nhãn rời rạc.

### 6.2. Nhiều điều kiện cùng property

Muốn khoảng nửa mở `100 ≤ points < 150`, ý định có thể đặt tên:

```java
List<Customer>
findByLoyaltyPointsGreaterThanEqualAndLoyaltyPointsLessThan(
    Integer minInclusive,
    Integer maxExclusive
);
```

Tập kết quả mẫu sẽ là `{c02, c03}`, không bao gồm `c04` ở đúng cận trên 150.

## 7. `And` và `Or` kết hợp toán tử so sánh

Các toán tử quan hệ áp dụng cho **property ngay trước hậu tố**:

```java
List<Customer> findByStatusAndLoyaltyPointsGreaterThan(
    String status, Integer minPoints
);
```

nghĩa là `status = ? AND loyalty_points > ?`.

Nếu thêm `Or`:

```java
List<Customer> findByStatusAndLoyaltyPointsGreaterThanOrCity(
    String status, Integer minPoints, String city
);
```

cách đọc hợp lý của parser Spring Data là:

```text
(status = ? AND loyalty_points > ?)
OR
(city = ?)
```

Đây **khác** với:

```text
status = ?
AND
(loyalty_points > ? OR city = ?)
```

Trong bài toán lọc phân khúc, hai biểu thức có thể trả về tập khách hàng khác nhau đáng kể. Nếu cần dấu ngoặc tùy ý, điều kiện động hoặc nhóm `OR` lớn, ưu tiên `@Query` có SQL++ tường minh để người đọc xác minh logic dễ dàng.

## 8. Kiểu dữ liệu, `NULL` và `MISSING`

Couchbase lưu dữ liệu dạng JSON nên cùng một field có thể bị thiếu, có `null`, hoặc tồn tại với kiểu khác dự kiến.

Giả sử hai document:

```json
{"status": "ACTIVE", "loyalty_points": null}
```

```json
{"status": "ACTIVE"}
```

Trong SQL++:

- `NULL` là giá trị null được lưu rõ ràng.
- `MISSING` biểu thị field không tồn tại.
- So sánh số học như `loyalty_points > 100` trên `NULL`/`MISSING` không được hiểu là một phép so sánh bình thường trả `true`; các document này thường không vượt qua điều kiện `WHERE`.
- Một field dạng `"loyalty_points": "120"` là **chuỗi**; không nên giả định nó được xử lý như số 120 trong mọi biểu thức so sánh.

Vì vậy, không dùng `findByLoyaltyPointsLessThan(100)` như một cách kiểm tra “khách hàng chưa đủ điểm” nếu nghiệp vụ còn xem **chưa có điểm** là trường hợp riêng. Hãy thiết kế quy tắc cụ thể để tách giá trị số, null và thiếu field.

Nếu cần tìm document thiếu trường, cần kiểm tra khả năng hỗ trợ của từ khóa `IsNull` và SQL++ thực tế. SQL++ phân biệt `IS NULL` với `IS MISSING`; một số trường hợp nên dùng `@Query` thay vì hy vọng derived query tự gộp hai khái niệm.

### 8.1. Vì sao kiểu dữ liệu lẫn lộn nguy hiểm?

Với các giá trị `99`, `"100"`, `101`, giả định tất cả đều là số khi chạy `Between(100, 150)` có thể dẫn đến kết quả khác mong đợi. Thực tế, SQL++ thực thi trên JSON của Couchbase **trước khi** ánh xạ kết quả thành entity Java. Mapper không thể sửa ý nghĩa điều kiện phía server khi field được lưu sai kiểu.

Hướng xử lý là chuẩn hóa dữ liệu ngay tại bước ghi, migration dữ liệu không đồng nhất, validation và xây dựng test trên document JSON đại diện.

## 9. Index cho equality, range và `IN`

Truy vấn derived query theo trường nội dung thường dùng SQL++ và cần index phù hợp để thực thi hiệu quả. Phần này không nhằm tạo ra một index cho mọi phương thức, mà giải thích cách ánh xạ **mẫu điều kiện** sang **thứ tự khóa index**.

Giả sử câu SQL++ được Spring Data sinh ra có điều kiện phân biệt loại entity qua field `_class`. Một index minh họa:

```sql
CREATE INDEX ix_customers_type_status_points
ON `app`.`crm`.`customers`(
    `_class`,
    `status`,
    `loyalty_points`
);
```

Index này có thể phục vụ bộ lọc:

```sql
WHERE c.`_class` = "example.crm.Customer"
  AND c.`status` = "ACTIVE"
  AND c.`loyalty_points` BETWEEN 100 AND 150
```

**Các tên, giá trị và discriminator ở đây chỉ minh họa.** Spring Data Couchbase có thể sinh điều kiện type khác hoặc không dùng giả định `_class` như trên. Dùng SQL++ thực tế và tài liệu cấu hình entity của ứng dụng để quyết định index phù hợp.

Một số nguyên tắc thực hành:

1. **Equality trước, range sau:** Với điều kiện `status = ? AND loyalty_points > ?`, index trên các trường bình đẳng rồi trường range thường là điểm khởi đầu hợp lý.
2. **Tiền tố của index:** Nếu index theo `(_class, status, loyalty_points)`, điều kiện chỉ theo `loyalty_points` có thể không tận dụng được index một cách hiệu quả vì thiếu bộ lọc theo các khóa đứng trước.
3. **`IN` cũng có chi phí:** Số giá trị tăng có thể thay đổi số lượng phần index được quét. Không mặc định `IN` với hàng chục nghìn giá trị là lựa chọn tốt.
4. **Sắp xếp và phân trang:** `ORDER BY` có thể làm tăng chi phí nếu index không hỗ trợ. Trước khi thêm khóa sort vào index, kiểm tra kế hoạch thực thi.
5. **Chi phí bảo trì:** Index ảnh hưởng đến ghi, tài nguyên và thời gian xây dựng; nên tái sử dụng index khi phù hợp.

### 9.1. Kiểm tra kế hoạch với `EXPLAIN`

```sql
EXPLAIN
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
  AND c.`loyalty_points` BETWEEN 100 AND 150;
```

Câu trên mô tả mục đích. Khi kiểm tra thật, phải bổ sung các predicate mà framework tự sinh và xem projection/index thực tế; sau đó đánh giá index được chọn, chi phí scan, có bước sort hay fetch hay không. Không chỉ dựa vào việc truy vấn chạy thành công để kết luận index phù hợp.

## 10. Kết quả trả về, giới hạn và nhất quán

### 10.1. Đừng tải toàn bộ tập kết quả không cần thiết

Một điều kiện `GreaterThanEqual(0)` có thể khớp phần lớn collection. Nếu `List<Customer>` chứa hàng trăm nghìn document, bộ nhớ của ứng dụng và thời gian truyền dữ liệu đều bị ảnh hưởng.

Có thể thêm phân trang:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Customer> findByStatusAndLoyaltyPointsBetween(
    String status,
    Integer lower,
    Integer upper,
    Pageable pageable
);
```

Phương thức trên có cùng tên lõi với bản trả về `List` nhưng thêm `Pageable`, vì vậy cần chú ý vị trí tham số (ở cuối) và khả năng overload của Java.

Ví dụ gọi:

```java
var page = repository.findByStatusAndLoyaltyPointsBetween(
    "ACTIVE",
    100,
    150,
    org.springframework.data.domain.PageRequest.of(0, 20)
);
```

`Page` có thể dẫn đến thêm truy vấn đếm để tính tổng số; phải kiểm tra hiệu năng, đặc biệt với trang sâu. Nếu giao diện chỉ cần biết có trang tiếp theo, cân nhắc kiểu trả về có ngữ nghĩa phù hợp hơn khi phiên bản hỗ trợ.

### 10.2. Vừa ghi xong nhưng tìm theo khoảng không thấy

Giữa thao tác ghi bằng key-value và hệ thống index/truy vấn có thể có độ trễ cập nhật:

```text
save(customer)                         -> ghi document thành công
findById(customer.id)                  -> đọc theo ID có thể thấy ngay
findByLoyaltyPointsBetween(100, 150)   -> SQL++ có thể chưa thấy ngay
```

Nếu nghiệp vụ bắt buộc thấy document vừa ghi khi truy vấn theo khoảng, xem xét query scan consistency thích hợp, ví dụ mức như `REQUEST_PLUS` khi thư viện đang dùng hỗ trợ, hoặc thiết kế chuỗi xử lý đọc lại bằng ID. Tính nhất quán mạnh hơn có thể tăng độ trễ, nên chỉ áp dụng khi yêu cầu nghiệp vụ thực sự cần.

### 10.3. TTL, CAS và transaction

- **TTL:** Document hết hạn sẽ không còn tồn tại để đáp ứng truy vấn khoảng/tập; tập kết quả có thể thay đổi theo thời gian.
- **CAS/optimistic locking:** Truy vấn lọc chỉ tìm document. Nếu sau đó cập nhật điểm hoặc trạng thái, cần xử lý xung đột ghi theo cơ chế concurrency phù hợp, không giả định lần đọc giúp khóa document.
- **Giao dịch:** Chuỗi `findBy...` rồi `save(...)` không tự là một giao dịch nguyên tử. Khi nghiệp vụ đòi hỏi tính nguyên tử qua nhiều thao tác, sử dụng giải pháp transaction phù hợp với phiên bản SDK/Spring Data Couchbase.

## 11. Repository reactive vẫn dùng cùng điều kiện

Khi ứng dụng sử dụng API reactive, cùng tên phương thức có thể trả về `Flux`:

```java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Flux<Customer> findByLoyaltyPointsBetween(
        Integer lower, Integer upper
    );

    Flux<Customer> findByStatusAndCityIn(
        String status, java.util.Collection<String> cities
    );
}
```

Reactive thay đổi **cách tiêu thụ kết quả**, không thay đổi ý nghĩa `Between`/`In`, cấu trúc index hay cơ chế cập nhật chỉ mục. Nếu luồng web đã sử dụng reactive end-to-end, tránh gọi `block()` trong đường xử lý yêu cầu vì có thể làm mất lợi ích không chặn.

## 12. Khi nào cần SQL++ tường minh?

Tên phương thức rất tốt với một vài điều kiện xác định. Nên cân nhắc `@Query` hoặc `CouchbaseTemplate` khi:

- Khoảng giá trị có cận tùy chọn: chỉ min, chỉ max, cả hai, hoặc không cận nào.
- Cần nhóm logic như `status = "ACTIVE" AND (points BETWEEN 100 AND 150 OR city IN [...])`.
- Cần xử lý riêng `NULL`, `MISSING`, phép chuyển kiểu, biểu thức số học hoặc điều kiện trên mảng JSON.
- Truy vấn dùng `JOIN`/`UNNEST`/`GROUP BY`, projection đặc thù hoặc cần kiểm soát SQL++ và query options chi tiết.
- Muốn điều kiện lọc, sort và pagination thay đổi theo nhiều tổ hợp runtime.

Ví dụ SQL++ diễn đạt rõ điều kiện:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = $status
  AND (
    c.`loyalty_points` BETWEEN $minPoints AND $maxPoints
    OR c.`city` IN $cities
  );
```

Đây là SQL++ minh họa, không phải câu `@Query` đầy đủ có thể chép nguyên vào mọi phiên bản Spring Data Couchbase: binding tham số, projection để ánh xạ entity và discriminator phải theo quy ước của thư viện/cấu hình thực tế.

## 13. Bài tập ứng dụng và đáp án

Dùng dữ liệu `c01`–`c06` trong mục 6.

**Bài A.** Tìm khách hàng có **ít nhất 150 điểm**.

```java
List<Customer> findByLoyaltyPointsGreaterThanEqual(Integer min);
```

Gọi `findByLoyaltyPointsGreaterThanEqual(150)` → mong đợi `{c04, c05, c06}`.

**Bài B.** Chọn khách hàng ACTIVE có điểm **từ 100 đến 150**, bao gồm hai cận.

```java
List<Customer> findByStatusAndLoyaltyPointsBetween(
    String status,
    Integer lower,
    Integer upper
);
```

Gọi `findByStatusAndLoyaltyPointsBetween("ACTIVE", 100, 150)` → mong đợi `{c02, c03}`.

**Bài C.** Chọn khách hàng ACTIVE ở HANOI hoặc DANANG.

```java
List<Customer> findByStatusAndCityIn(
    String status,
    java.util.Collection<String> cities
);
```

Gọi `findByStatusAndCityIn("ACTIVE", List.of("HANOI", "DANANG"))` → mong đợi `{c01, c02, c03, c06}`.

**Bài D.** Yêu cầu điểm `100 ≤ points < 150`. Có thể dùng `Between(100, 150)` không? **Không**, vì sẽ lấy cả giá trị 150. Hãy dùng hai điều kiện cận tương ứng như ở mục 4.1; với dữ liệu mẫu mong đợi `{c02, c03}`.

**Bài E.** Bổ sung document `c07` với `status = "ACTIVE"` và `loyalty_points = null`, `c08` có status nhưng không có trường `loyalty_points`. Giải thích vì sao chúng không nên được coi là thỏa điều kiện số học `loyalty_points BETWEEN 100 AND 150`. Sau đó kiểm tra riêng biểu thức SQL++ cho `NULL` và `MISSING` theo yêu cầu nghiệp vụ.

### Bảng kiểm trước khi triển khai

| Câu hỏi kiểm tra | Vì sao quan trọng |
| --- | --- |
| Điều kiện có bao gồm đúng giá trị biên không? | Phân biệt `>` với `>=`, `BETWEEN` với khoảng nửa mở. |
| Hai cận đã được sắp đúng thứ tự chưa? | Cận đảo có thể trả kết quả rỗng hoặc bất ngờ. |
| `In` biểu diễn tập rời rạc hay một dải liên tục? | Đây là hai loại bộ lọc khác nhau. |
| Danh sách giá trị có rỗng, null hoặc quá dài không? | Cần hợp đồng đầu vào và giới hạn tài nguyên. |
| Dữ liệu JSON thật có đúng kiểu số/chuỗi/thời gian không? | Query Service lọc trên JSON trước khi mapping thành Java. |
| Có document `NULL` hoặc `MISSING` không? | Không được đồng nhất với giá trị 0 hay chuỗi rỗng. |
| Index đã phù hợp equality + range chưa? | Thứ tự khóa index và selectivity ảnh hưởng hiệu năng. |
| Có cần phân trang và scan consistency không? | Hạn chế tải lớn; đáp ứng yêu cầu dữ liệu vừa ghi. |

## 14. Ghi nhớ

**`GreaterThan`, `GreaterThanEqual`, `LessThan` và `LessThanEqual`** xác định phép so sánh và ranh giới có được lấy hay không. **`Between`** biểu diễn khoảng có hai cận và trong ngữ nghĩa SQL++ thông thường bao gồm cả hai biên; **`In`** biểu diễn một tập giá trị rời rạc. Khi kết hợp với `And`/`Or`, cần giữ đúng thứ tự tham số và nhóm điều kiện.

Trong Spring Data Couchbase, một derived query đúng về tên vẫn cần **mapping đúng**, **kiểu JSON nhất quán**, **index phù hợp**, **kiểu trả về có giới hạn hợp lý** và **query consistency** đáp ứng nghiệp vụ. Với điều kiện động, xử lý `NULL`/`MISSING` đặc biệt hoặc biểu thức phức tạp, dùng `@Query`/`CouchbaseTemplate` để viết SQL++ rõ ràng và có thể kiểm chứng.
