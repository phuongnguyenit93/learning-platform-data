# Điều kiện null, thiếu trường và giới hạn suy diễn từ tên phương thức

Trong **SPRING_DATA_COUCHBASE**, truy vấn dẫn xuất (*derived query*) giúp diễn đạt điều kiện tìm document ngay trong tên phương thức repository. Nhưng khi dữ liệu là JSON, có một khác biệt quyết định kết quả: **một trường tồn tại với giá trị `null`** và **một trường hoàn toàn không tồn tại** là hai trạng thái khác nhau. SQL++ của Couchbase phân biệt **`NULL`** với **`MISSING`**, còn tên phương thức Java không phải lúc nào cũng biểu đạt được toàn bộ quy tắc xử lý hai trạng thái đó.

Bài thuộc chương **Truy vấn dẫn xuất**, tập trung vào **điều kiện null, thiếu trường và giới hạn suy diễn từ tên phương thức**. Các ví dụ kết hợp document mapping, repository và SQL++ trong tầng truy cập Couchbase; đồng thời chỉ ra tác động của bucket/scope/collection, index, TTL, CAS, giao dịch và lựa chọn API reactive đến tính đúng đắn cũng như hiệu năng. Khi điều kiện vượt quá khả năng biểu đạt rõ ràng của derived query, bài hướng dẫn chuyển sang `@Query` hoặc `CouchbaseTemplate`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt giá trị `NULL`, giá trị `MISSING` và giá trị hiện hữu như chuỗi rỗng, `false`, `0` hay mảng rỗng trong JSON.
2. Hiểu vai trò của các biểu thức SQL++ `IS NULL`, `IS MISSING`, `IS NOT MISSING`, `IS VALUED` và `IS NOT VALUED`.
3. Nhận biết ý định của `IsNull` và `IsNotNull` trong tên phương thức repository, đồng thời kiểm chứng khả năng hỗ trợ/ngữ nghĩa thực tế của Spring Data Couchbase.
4. Giải thích vì sao truyền tham số Java `null` vào điều kiện bằng nhau không đủ để định nghĩa chính sách xử lý field vắng mặt.
5. Viết bộ lọc đúng cho object lồng nhau, mảng, dữ liệu không đồng nhất và bộ lọc tùy chọn.
6. Nhận biết giới hạn của parser derived query khi cần dấu ngoặc, `MISSING`, điều kiện động hoặc hàm SQL++ đặc thù.
7. Đánh giá index, kiểu trả về, phân trang và consistency cho truy vấn có trường thiếu.
8. Tạo bộ test bao phủ các trạng thái JSON dễ gây sai kết quả.

## 2. Bối cảnh dữ liệu: một collection có document không đồng nhất

Giả sử hệ thống quản lý khách hàng lưu document ở bucket `app`, scope `crm`, collection `customers`. Mẫu dữ liệu đầu tiên:

```json
{
  "status": "ACTIVE",
  "email": "lan@example.test",
  "primary_phone": null,
  "profile": {
    "city": "HANOI"
  },
  "tags": []
}
```

Các document khác có thể thiếu `primary_phone`, thiếu toàn bộ `profile` hoặc không có `tags`. Điều này xảy ra trong hệ thống NoSQL khi dữ liệu được ghi qua các phiên bản ứng dụng khác nhau, các trường bổ sung theo thời gian, hoặc quy tắc cập nhật chỉ chạm tới một phần nội dung.

Khai báo entity tham khảo:

```java
package example.crm;

import java.util.List;
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
    private String email;

    @Field("primary_phone")
    private String primaryPhone;

    @Field
    private Profile profile;

    @Field
    private List<String> tags;

    protected Customer() {
        // Dành cho document mapper.
    }

    // Constructor nghiệp vụ và getters/setters lược bỏ.
}

class Profile {

    @Field
    private String city;

    protected Profile() {}

    // Getters/setters lược bỏ.
}
```

Ở đây:

- Property Java `primaryPhone` ánh xạ tới trường JSON `primary_phone`.
- Property Java `profile.city` ánh xạ tới JSON `profile.city`.
- `@Id` ánh xạ document ID của Couchbase, không có nghĩa trong JSON luôn tồn tại field `id`.
- Cách Spring Data lưu một property Java bằng `null` (giữ field với JSON null hay bỏ field) còn phụ thuộc mapping, converter và cách ghi của ứng dụng. Phải **xem document JSON thật** trước khi kết luận.

## 3. Năm trường hợp JSON phải tách biệt

Xét năm document cùng collection:

```json
// c01: tồn tại và có giá trị chuỗi
{"status": "ACTIVE", "primary_phone": "0900000001"}
```

```json
// c02: field tồn tại với JSON null
{"status": "ACTIVE", "primary_phone": null}
```

```json
// c03: field không tồn tại
{"status": "ACTIVE"}
```

```json
// c04: field tồn tại nhưng là chuỗi rỗng
{"status": "ACTIVE", "primary_phone": ""}
```

```json
// c05: field tồn tại nhưng có kiểu sai so với entity
{"status": "ACTIVE", "primary_phone": 12345}
```

Các đoạn `// c01`–`// c05` chỉ là chú thích trình bày cho ví dụ, không thuộc JSON hợp lệ nếu chép nguyên vào Couchbase; ID document có thể là `c01` đến `c05` tương ứng.

| Document | Kiểm tra trên JSON | Trạng thái |
| --- | --- | --- |
| `c01` | Field tồn tại, kiểu chuỗi, có nội dung | Giá trị hiện hữu |
| `c02` | Field tồn tại, giá trị JSON null | `NULL` |
| `c03` | Không có khóa `primary_phone` | `MISSING` |
| `c04` | Field tồn tại, giá trị `""` | Giá trị chuỗi rỗng, **không phải null** |
| `c05` | Field tồn tại, giá trị số | Giá trị hiện hữu nhưng **khác kiểu mong đợi** |

Điểm quan trọng: `NULL` không đồng nghĩa `MISSING`; và cả hai không đồng nghĩa chuỗi rỗng, `false`, `0` hay `[]`. Trong Java, một property `String` có thể nhận `null` sau khi ánh xạ từ nhiều tình huống JSON khác nhau, vì vậy chỉ nhìn object Java sau mapping có thể không còn đủ thông tin để phân biệt dữ liệu gốc.

## 4. Các toán tử SQL++ dành cho `NULL` và `MISSING`

SQL++ có các phép kiểm tra rõ ràng cho giá trị null và trường thiếu. Dưới đây là cách viết minh họa trực tiếp trên collection:

```sql
-- Chỉ field có giá trị JSON null.
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`primary_phone` IS NULL;

-- Field hoàn toàn không tồn tại.
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`primary_phone` IS MISSING;

-- Field có tồn tại, kể cả khi giá trị là null.
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`primary_phone` IS NOT MISSING;

-- Field có giá trị, không phải null hoặc missing.
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`primary_phone` IS VALUED;

-- Field không có giá trị hữu dụng theo cặp trạng thái null/missing.
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`primary_phone` IS NOT VALUED;
```

### 4.1. Bảng kết quả cần nhớ

Theo năm document ở mục 3:

| Điều kiện | `c01` chuỗi | `c02` NULL | `c03` MISSING | `c04` `""` | `c05` số |
| --- | :---: | :---: | :---: | :---: | :---: |
| `IS NULL` | ✗ | ✓ | ✗ | ✗ | ✗ |
| `IS MISSING` | ✗ | ✗ | ✓ | ✗ | ✗ |
| `IS NOT MISSING` | ✓ | ✓ | ✗ | ✓ | ✓ |
| `IS VALUED` | ✓ | ✗ | ✗ | ✓ | ✓ |
| `IS NOT VALUED` | ✗ | ✓ | ✓ | ✗ | ✗ |

**`IS VALUED` không có nghĩa là chuỗi không rỗng hoặc có đúng kiểu dữ liệu.** Nó chỉ loại hai trạng thái `NULL` và `MISSING`. Vì vậy `c04` với `""` và `c05` với số `12345` vẫn được xem là có giá trị theo phép kiểm tra này.

Khi nghiệp vụ định nghĩa “đã cung cấp số điện thoại” là một **chuỗi hợp lệ, không rỗng**, cần kiểm tra thêm kiểu/định dạng. Một biểu thức `IS VALUED` đơn lẻ chưa đáp ứng yêu cầu.

### 4.2. Vì sao không viết `= NULL`?

Trong SQL++, việc so sánh với `NULL` không tương đương với phép kiểm tra `IS NULL`. SQL++ xử lý `NULL`/`MISSING` theo logic giá trị đặc biệt; các biểu thức so sánh có thể truyền trạng thái unknown/null/missing vào kết quả và không được xem là `true` trong `WHERE`.

**Nên viết:**

```sql
WHERE c.`primary_phone` IS NULL
```

**Tránh coi câu sau là phép kiểm tra null đúng nghĩa:**

```sql
WHERE c.`primary_phone` = NULL
```

Tương tự, điều kiện `c.primary_phone != "0900000001"` không phải cách bao quát đáng tin cậy cả trường null và thiếu. Nếu cần “khác số này **hoặc** chưa có điện thoại”, phải diễn đạt các nhánh rõ ràng.

### 4.3. `IS NOT NULL` và `IS VALUED` không nên đánh đồng

Muốn tìm **không phải null cũng không thiếu**, dùng phép kiểm tra diễn đạt rõ cả hai trạng thái như `IS VALUED`, hoặc kiểm tra đồng thời trạng thái null và missing theo logic tương đương. Không suy luận chỉ từ chữ `NotNull` trong tên Java rằng nó bắt buộc đồng nghĩa `IS VALUED` trên Couchbase.

Đây là lý do cần xem SQL++ thực tế khi framework phát sinh điều kiện; cách đặt tên theo khái niệm “không null” có thể chưa chứa toàn bộ ý định nghiệp vụ “trường có tồn tại và có dữ liệu”.

## 5. Truy vấn dẫn xuất với `IsNull` và `IsNotNull`

Trong hệ sinh thái Spring Data, các tên phương thức thường gặp để biểu đạt null là:

```java
package example.crm;

import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    // Cần kiểm chứng keyword trên phiên bản Spring Data Couchbase dùng thật.
    List<Customer> findByPrimaryPhoneIsNull();

    List<Customer> findByPrimaryPhoneIsNotNull();

    List<Customer> findByStatusAndPrimaryPhoneIsNull(String status);

    List<Customer> findByStatusAndPrimaryPhoneIsNotNull(String status);
}
```

Phân tích cách đặt tên:

| Chữ ký | Ý định thể hiện |
| --- | --- |
| `findByPrimaryPhoneIsNull()` | Tìm entity có `primaryPhone` null theo cách backend hỗ trợ. |
| `findByPrimaryPhoneIsNotNull()` | Tìm entity có `primaryPhone` không null theo cách backend hỗ trợ. |
| `findByStatusAndPrimaryPhoneIsNull(status)` | Kết hợp trạng thái bằng giá trị đầu vào với điều kiện null. |
| `findByStatusAndPrimaryPhoneIsNotNull(status)` | Kết hợp trạng thái với điều kiện không null. |

`IsNull` và `IsNotNull` là những keyword của ngữ pháp derived query nói chung. **Phải xác minh khả năng hỗ trợ, cách dịch SQL++ và trường hợp `MISSING` của Spring Data Couchbase phiên bản thực tế.** Không tự suy ra rằng mọi keyword của JPA có cùng ngữ nghĩa trong Couchbase.

Bài toán: “Tìm khách hàng chưa cung cấp số điện thoại, bao gồm cả document cũ chưa từng có field” có yêu cầu chính xác là **`NULL OR MISSING`**. Chỉ nhìn tên `findByPrimaryPhoneIsNull()` chưa đủ để chứng minh hàm trả đúng cả hai trường hợp.

Một câu SQL++ diễn đạt đúng ý định đó:

```sql
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`primary_phone` IS NOT VALUED;
```

Nếu yêu cầu “chỉ lấy field lưu rõ null, loại document thiếu field”, dùng `IS NULL`. Nếu yêu cầu “chỉ lấy document chưa có khóa”, dùng `IS MISSING`. Đừng thay thế ba nghiệp vụ này bằng cùng một tên phương thức.

## 6. Truyền `null` vào tham số phương thức là chuyện khác

Xét phương thức lấy theo giá trị:

```java
List<Customer> findByPrimaryPhone(String phone);
```

Lời gọi:

```java
repository.findByPrimaryPhone(null);
```

không mang hợp đồng rõ ràng như `findByPrimaryPhoneIsNull()`. Cách xử lý tham số `null` có thể phụ thuộc module Spring Data, phiên bản, khả năng binding và cách query creator sinh predicate.

Không nên giả định `findByPrimaryPhone(null)` chắc chắn được chuyển thành `IS NULL`, cũng không nên dựa vào nó để tìm cả `NULL` và `MISSING`.

Nếu input do người dùng gửi đến có thể null, tầng service cần phân biệt:

- **Không nhập điều kiện:** bỏ bộ lọc `primaryPhone` khỏi câu truy vấn.
- **Yêu cầu tìm giá trị null:** dùng điều kiện `IS NULL` phù hợp.
- **Yêu cầu tìm field vắng mặt:** dùng `IS MISSING`.
- **Yêu cầu tìm chưa có giá trị:** dùng `IS NOT VALUED` nếu nghiệp vụ gộp null và missing.
- **Yêu cầu tìm số cụ thể:** dùng điều kiện bằng giá trị chuỗi đã kiểm tra định dạng.

Những trạng thái này là **năm yêu cầu khác nhau**. Chúng cần API hoặc tham số biểu đạt rõ ý định, thay vì truyền cùng một `null` và để repository đoán.

## 7. Phân biệt `null` trong Java với cách lưu JSON

Với entity ở mục 2, ứng dụng có thể viết:

```java
customer.setPrimaryPhone(null);
repository.save(customer);
```

Nhưng document JSON tạo ra phải được **kiểm tra thực tế**. Converter, chính sách ghi field null, cách cập nhật toàn document hay thao tác chỉnh một field có thể ảnh hưởng trạng thái trên Couchbase:

```json
{
  "primary_phone": null
}
```

và:

```json
{}
```

đều có thể khiến property Java nhận `null` sau khi đọc, nhưng SQL++ `IS NULL` và `IS MISSING` phân biệt chúng.

Vì vậy, một hệ thống cần phân biệt “người dùng chủ động xóa số điện thoại” với “dữ liệu cũ chưa có trường điện thoại” nên lưu quy ước trạng thái có chủ đích, kiểm tra JSON và dùng API cập nhật tương thích. Có thể chọn một field trạng thái riêng nếu nghiệp vụ cần lịch sử và ngữ nghĩa rõ hơn việc suy ra từ null.

Không nên dùng `Optional<String>` trong entity như một cách chắc chắn để bảo tồn sự khác biệt `NULL`/`MISSING` nếu mapping không hỗ trợ. `Optional` trong **kiểu trả về repository** mô tả khả năng có hoặc không có entity kết quả, khác hoàn toàn với trạng thái một field bên trong entity.

## 8. Điều kiện null kết hợp với `And` và `Or`

Ví dụ yêu cầu “khách hàng ACTIVE có field `primary_phone` lưu null”:

```sql
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
  AND c.`primary_phone` IS NULL;
```

Nếu keyword hỗ trợ và sinh đúng ý định, một chữ ký derived query tương ứng có thể là:

```java
List<Customer> findByStatusAndPrimaryPhoneIsNull(String status);
```

Nhưng yêu cầu “khách hàng ACTIVE **và** (phone null **hoặc** missing)” cần nhóm khác:

```sql
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
  AND (
      c.`primary_phone` IS NULL
      OR c.`primary_phone` IS MISSING
  );
```

Có thể viết ngắn hơn với `IS NOT VALUED`:

```sql
WHERE c.`status` = "ACTIVE"
  AND c.`primary_phone` IS NOT VALUED
```

### 8.1. Cẩn trọng với nhóm `Or`

Một tên phương thức dài như:

```java
findByStatusAndPrimaryPhoneIsNullOrEmail(...)
```

có thể dễ bị hiểu là `status = ? AND (phone IS NULL OR email = ?)`, trong khi cách phân tích nhánh `And`/`Or` của Spring Data nói chung tương ứng với `(status = ? AND phone IS NULL) OR email = ?`. Hai biểu thức này khác nhau đáng kể: biểu thức sau có thể chọn document không ACTIVE nếu email khớp.

Khi cần dấu ngoặc phức tạp, logic xử lý `MISSING` hoặc nhiều nhánh tùy chọn, viết SQL++ tường minh qua `@Query` thường dễ kiểm chứng hơn tên phương thức dài.

## 9. Object lồng nhau: thiếu object cha khác thiếu field con

Giả sử cần tìm khách hàng theo `profile.city`. Xét các document:

```json
{"profile": {"city": "HANOI"}}
```

```json
{"profile": {"city": null}}
```

```json
{"profile": {}}
```

```json
{"profile": null}
```

```json
{}
```

Các trạng thái:

1. Có `profile` và `city` với giá trị `HANOI`.
2. Có `profile` và `city` rõ ràng là null.
3. Có `profile`, nhưng thiếu khóa `city`.
4. `profile` tồn tại nhưng null.
5. Không có trường `profile`.

Derived query cho đường dẫn Java có thể dùng dấu `_` để chỉ rõ property path:

```java
// Chỉ dùng nếu query creator của Couchbase hỗ trợ
// đúng tổ hợp nested property và keyword cần thiết.
List<Customer> findByProfile_CityIsNull();
List<Customer> findByProfile_City(String city);
```

Tuy nhiên, `findByProfile_CityIsNull()` không tự nói rõ phải xử lý thế nào nếu **cha `profile` null hoặc missing**. SQL++ thao tác trên biểu thức đường dẫn `c.profile.city`, và tình huống thiếu cha/con có thể cho kết quả khác với trường con tồn tại nhưng null.

Nếu nghiệp vụ là “chưa từng thiết lập hồ sơ”, cần kiểm tra **trường `profile` ở gốc**; còn “đã có hồ sơ nhưng chưa điền thành phố” cần ràng buộc cả trạng thái của cha và con:

```sql
-- Chỉ minh họa ý định đã có profile dạng object,
-- nhưng không có giá trị city.
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`profile` IS OBJECT
  AND c.`profile`.`city` IS NOT VALUED;
```

Trước khi dùng các phép kiểm tra kiểu/đường dẫn, hãy thử câu SQL++ với dữ liệu thật. Với dữ liệu không đồng nhất hoặc converter tùy chỉnh, có thể cần biểu thức chặt chẽ hơn để xác định đúng các trạng thái.

## 10. Mảng rỗng, field thiếu và điều kiện trên phần tử mảng

Giả sử field `tags` có thể là:

```json
{"tags": ["VIP", "ACTIVE"]}
```

```json
{"tags": []}
```

```json
{"tags": null}
```

```json
{}
```

Đây là bốn trạng thái khác nhau:

- `["VIP", "ACTIVE"]`: mảng có phần tử.
- `[]`: mảng tồn tại nhưng **rỗng**, không phải null/missing.
- `null`: field tồn tại nhưng không có giá trị.
- Không có `tags`: `MISSING`.

Câu hỏi “khách hàng chưa có tag” có thể mang nhiều ý nghĩa: chỉ mảng rỗng; null hoặc missing; hay gộp tất cả trạng thái không có tag nào. Đừng suy luận một từ khóa `IsEmpty` hoặc `IsNull` của derived query sẽ bao quát đủ mọi trường hợp ở backend Couchbase.

SQL++ có thể mô tả điều kiện rõ ràng. Ví dụ:

```sql
-- Field tags tồn tại và là mảng rỗng.
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`tags` = [];

-- Field tags là null hoặc missing.
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`tags` IS NOT VALUED;
```

Nếu cần tìm phần tử mảng có giá trị cụ thể, dùng toán tử/biểu thức SQL++ thích hợp với **phần tử mảng**, không nhầm với `IN` khi lọc một field vô hướng theo tập tham số.

Ví dụ ý định “mảng tags có phần tử bằng VIP”:

```sql
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE ANY tag IN c.`tags`
      SATISFIES tag = "VIP"
      END;
```

Với mảng object, các predicate cần được nhóm trên **cùng một phần tử**. Đây là tình huống mà `@Query`/`CouchbaseTemplate` giúp thể hiện rõ hơn so với việc ghép keyword trong tên phương thức.

## 11. Vì sao tên phương thức không thay thế được toàn bộ SQL++?

Spring Data parser có thể suy luận **cấu trúc điều kiện phổ biến** từ tên method, nhưng không phải mọi biểu thức SQL++ đều diễn đạt được. Các giới hạn thực tế gồm:

| Nhu cầu | Vấn đề khi chỉ dùng derived query |
| --- | --- |
| Tách `NULL` và `MISSING` | Keyword `IsNull` không đương nhiên định nghĩa đủ hai trạng thái. |
| Kiểm tra field có mặt và có đúng kiểu | Cần `IS NOT MISSING`, `IS VALUED` và/hoặc kiểm tra kiểu dữ liệu. |
| Nhóm nhiều nhánh `And`/`Or` có ngoặc | Dễ diễn giải sai thứ tự nhóm điều kiện. |
| Bộ lọc tùy chọn theo input runtime | Tên method cố định dẫn tới nhiều tổ hợp overload. |
| Mảng object với nhiều điều kiện trên cùng phần tử | Thường cần `ANY ... SATISFIES` hoặc truy vấn mảng đặc thù. |
| Chuẩn hóa hoặc chuyển kiểu trước so sánh | Cần hàm SQL++ và index tương ứng. |
| `JOIN`, `UNNEST`, `GROUP BY`, aggregate | Vượt khỏi ngữ nghĩa derived query đơn giản. |
| Tùy chỉnh projection, query options và consistency | Có thể cần API truy vấn rõ ràng hơn. |

Ví dụ: một màn hình tìm kiếm cho phép chọn “Tất cả”, “Có điện thoại”, “Chưa có điện thoại”. Thay vì truyền `null` cho cùng một method `findByPrimaryPhone(...)`, hãy định nghĩa rõ ba trạng thái bộ lọc ở service, từ đó chọn truy vấn tương ứng.

## 12. Khi nào dùng `@Query` và khi nào dùng `CouchbaseTemplate`?

### 12.1. `@Query` cho truy vấn có cấu trúc cố định

Nếu nghiệp vụ luôn cần “khách hàng ACTIVE có điện thoại null hoặc missing”, câu SQL++ có thể được diễn đạt minh bạch:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = $status
  AND c.`primary_phone` IS NOT VALUED;
```

Khi tích hợp vào `@Query` của **Spring Data Couchbase**, phải dùng đúng cú pháp binding, projection và metadata/discriminator do phiên bản thư viện cung cấp. Không nên chép nguyên ví dụ SQL++ trên vào annotation rồi giả định entity sẽ tự ánh xạ đúng trên mọi phiên bản.

Ưu điểm của truy vấn tường minh là người đọc thấy ngay `IS NOT VALUED` thay vì phải suy đoán `IsNull` bao gồm những trạng thái nào.

### 12.2. `CouchbaseTemplate` cho bộ lọc động

Ví dụ request có thể chứa các bộ lọc:

```json
{
  "status": "ACTIVE",
  "phoneFilter": "UNSET",
  "city": null
}
```

Trong đó `phoneFilter` là một enum nghiệp vụ:

| Giá trị | Ý nghĩa truy vấn |
| --- | --- |
| `ANY` | Không áp dụng điều kiện cho phone. |
| `PRESENT` | Phone có giá trị (`IS VALUED`), có thể thêm kiểm tra kiểu/chuỗi rỗng theo quy tắc. |
| `EXPLICIT_NULL` | Chỉ field có `NULL`. |
| `MISSING` | Chỉ document không có field. |
| `UNSET` | Gộp `NULL` và `MISSING`. |

Tầng service nên kiểm tra enum và dựng truy vấn phù hợp bằng API query động (`CouchbaseTemplate` hoặc cơ chế xây query khác được phiên bản hỗ trợ). Cần binding tham số cho giá trị người dùng và áp dụng chính sách truy cập dữ liệu ở cùng một nơi.

Nếu số trường tùy chọn tăng, một phương thức derived query riêng cho mỗi tổ hợp sẽ khó bảo trì hơn một bộ xây dựng điều kiện có cấu trúc. Tuy vậy, với truy vấn cố định đơn giản như `findByStatus("ACTIVE")`, derived query vẫn là lựa chọn gọn và dễ đọc.

## 13. Index và `EXPLAIN` khi field có thể bị thiếu

Truy vấn theo trường JSON thường chạy qua SQL++ và **secondary index**. Nhưng khi các document thiếu một trường, cách index chứa hoặc bỏ qua chúng có thể ảnh hưởng khả năng lập kế hoạch và tập kết quả.

Giả sử hệ thống thường tìm khách hàng ACTIVE có điện thoại được cung cấp. Một index minh họa dành cho bộ lọc theo trạng thái và số điện thoại:

```sql
-- Ví dụ định hướng, không phải index tối ưu phổ quát.
CREATE INDEX ix_customers_status_phone
ON `app`.`crm`.`customers`(
    `status`,
    `primary_phone`
);
```

**Cảnh báo thiết kế:** nếu một index có field ở vị trí đầu và nhiều document thiếu field đó, chúng có thể không xuất hiện trong index theo cấu trúc và quy tắc của phiên bản Couchbase. Truy vấn cần tìm `IS MISSING` có thể phải dùng chiến lược index khác với truy vấn giá trị cụ thể. Một số phiên bản Couchbase có tùy chọn xử lý `MISSING` trong index; phải đối chiếu tài liệu phiên bản server thực tế và kiểm tra kế hoạch, không tự giả định tất cả index lưu trường thiếu như giá trị null.

### 13.1. `EXPLAIN` cho hai truy vấn có mục tiêu khác nhau

```sql
EXPLAIN
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
  AND c.`primary_phone` IS VALUED;
```

```sql
EXPLAIN
SELECT META(c).id AS docId
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
  AND c.`primary_phone` IS MISSING;
```

Hai truy vấn nhìn giống nhau về filter status, nhưng yêu cầu truy cập index khác: một truy vấn tìm field có giá trị, truy vấn kia tìm field không tồn tại.

Quy trình kiểm tra:

1. Lấy SQL++ thực tế do Spring Data sinh ra, gồm điều kiện type discriminator nếu có.
2. Chạy `EXPLAIN` và so sánh index được chọn cho `IS VALUED`, `IS NULL` và `IS MISSING`.
3. Đối chiếu với tập document thử nghiệm có trường vắng mặt; không chỉ đo thời gian chạy.
4. Kiểm tra số phần tử scan, fetch, sort, chi phí count khi phân trang.
5. Thiết kế index hỗ trợ đường truy cập **thật sự thường gặp**, cân bằng với chi phí ghi và tài nguyên vận hành.

`PRIMARY INDEX` có thể giúp chạy một số truy vấn tổng quát trong môi trường thử nghiệm nhưng không thay thế kế hoạch secondary index được thiết kế theo workload. Không tạo index cho mọi phương thức một cách máy móc.

## 14. Count, exists, phân trang và kiểu trả về

Với nghiệp vụ kiểm kê dữ liệu thiếu, đôi khi chỉ cần số lượng thay vì toàn bộ document:

```java
// Các keyword cần được kiểm tra trên phiên bản Couchbase thực tế.
long countByStatusAndPrimaryPhoneIsNull(String status);

boolean existsByStatusAndPrimaryPhoneIsNull(String status);
```

Tuy nhiên, nếu nghiệp vụ muốn tính cả `NULL` và `MISSING`, việc chỉ dùng `IsNull` có thể đếm thiếu. Phải kiểm tra SQL++ hoặc dùng truy vấn `IS NOT VALUED` tường minh.

| Kiểu trả về | Sử dụng | Lưu ý |
| --- | --- | --- |
| `List<Customer>` | Muốn xử lý tập khách hàng. | Có thể tải rất nhiều document thiếu field. |
| `Page<Customer>` | Cần hiển thị theo trang và tổng số. | Có thể phát sinh query count. |
| `long` với `countBy...` | Chỉ cần số lượng. | Phải đảm bảo điều kiện đếm đúng trạng thái null/missing. |
| `boolean` với `existsBy...` | Chỉ cần biết có kết quả. | Không tự chứng minh mọi document đều đáp ứng quy ước dữ liệu. |
| `Optional<Customer>` | Khi bộ lọc đảm bảo tối đa một document. | Không nên dùng để lấy một document bất kỳ trong tập nhiều bản ghi thiếu dữ liệu. |

Khi truy vấn có thể trả hàng trăm nghìn document, dùng phân trang hoặc luồng dữ liệu phù hợp; đừng lấy hết vào bộ nhớ chỉ để hiển thị trang đầu. Việc sắp xếp dựa trên trường có nhiều `NULL`/`MISSING` cũng cần kiểm thử thứ tự thực tế trong SQL++, và bổ sung khóa phụ xác định nếu muốn trang ổn định.

## 15. Consistency, TTL, CAS, giao dịch và reactive

### 15.1. Vừa cập nhật field nhưng truy vấn chưa thấy

Couchbase có đường key-value và cơ chế index/truy vấn SQL++ riêng. Sau khi cập nhật `primary_phone`:

```text
save(customer)                      -> ghi document thành công
findById(customer.id)               -> truy cập bằng khóa ID
findByPrimaryPhoneIsNull()          -> SQL++ và index, nếu keyword được hỗ trợ
```

Truy vấn derived query có thể chưa phản ánh ngay thay đổi khi index chưa kịp cập nhật ở mức nhất quán không đợi chỉ mục. Nếu quy trình nghiệp vụ yêu cầu tìm ngay document vừa sửa, cần xem xét query scan consistency thích hợp (ví dụ mức tương đương `REQUEST_PLUS` nếu phiên bản SDK/Spring Data cho phép) hoặc đọc theo ID.

Đừng nhầm **sai khác do index chưa cập nhật** với **sai khác do `NULL`/`MISSING`**. Khi debug, hãy so sánh bản JSON đọc theo ID, SQL++ thực thi và mức consistency đang cấu hình.

### 15.2. TTL, CAS và transaction

- **TTL:** Document đã hết hạn có thể không còn được chọn bởi bất kỳ điều kiện null/missing nào; tình trạng thiếu kết quả không nhất thiết do tên method.
- **CAS/optimistic locking:** Tìm thấy một khách hàng có phone missing rồi cập nhật phone không đảm bảo tránh xung đột với người khác đang sửa document. Cần cơ chế kiểm soát cập nhật đồng thời và xử lý retry theo nghiệp vụ.
- **Giao dịch:** Một chuỗi `findBy...` rồi `save(...)` không tự có tính nguyên tử. Nếu quy trình chuẩn hóa dữ liệu thiếu liên quan nhiều document, phải đánh giá API transaction và giới hạn hỗ trợ của Couchbase/Spring Data.
- **Collection:** Derived query lấy đích từ mapping/cấu hình bucket/scope/collection; tìm trong nhầm collection có thể làm bạn tưởng mọi field đều missing vì không có document đúng đối tượng.

### 15.3. API reactive không thay đổi ngữ nghĩa null/missing

Với repository reactive, phương thức vẫn thể hiện cùng điều kiện nhưng trả các kiểu Reactor:

```java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    // Xác minh hỗ trợ keyword trên phiên bản đang dùng.
    Flux<Customer> findByPrimaryPhoneIsNull();

    Flux<Customer> findByStatusAndPrimaryPhoneIsNotNull(
        String status
    );
}
```

`Flux<Customer>` cho phép tiêu thụ nhiều kết quả theo cách reactive. Nó không tự thay đổi SQL++ sinh ra, không làm `MISSING` thành `NULL` và không thay thế index. Với ứng dụng reactive end-to-end, tránh gọi `block()` trên đường xử lý yêu cầu nếu không có thiết kế phù hợp.

## 16. Bài tập: chọn đúng điều kiện trước khi viết repository

Giả sử một collection có dữ liệu:

| ID | `status` | `primary_phone` | `profile` |
| --- | --- | --- | --- |
| `c01` | ACTIVE | `"0900000001"` | `{"city":"HANOI"}` |
| `c02` | ACTIVE | `null` | `{"city":"HANOI"}` |
| `c03` | ACTIVE | `MISSING` | `{"city":null}` |
| `c04` | SUSPENDED | `""` | `{}` |
| `c05` | ACTIVE | `""` | `MISSING` |
| `c06` | ACTIVE | `12345` | `null` |
| `c07` | SUSPENDED | `MISSING` | `{"city":"DANANG"}` |

Các dấu `MISSING` trong bảng mang nghĩa **không có khóa** trong JSON, không phải chuỗi literal `"MISSING"`.

### Bài A — Tìm điện thoại được lưu rõ null

SQL++:

```sql
WHERE c.`primary_phone` IS NULL
```

Tập ID kỳ vọng: `{c02}`.

### Bài B — Tìm document thiếu hẳn field điện thoại

SQL++:

```sql
WHERE c.`primary_phone` IS MISSING
```

Tập ID kỳ vọng: `{c03, c07}`.

### Bài C — Tìm khách hàng ACTIVE chưa có giá trị điện thoại

Quy tắc nghiệp vụ: null **hoặc** missing, nhưng không xem chuỗi rỗng là chưa có giá trị trong bài này.

```sql
WHERE c.`status` = "ACTIVE"
  AND c.`primary_phone` IS NOT VALUED
```

Tập ID kỳ vọng: `{c02, c03}`.

Nếu nghiệp vụ muốn **chuỗi rỗng cũng là chưa cung cấp**, phải thêm điều kiện `primary_phone = ""`, và tập ID thành `{c02, c03, c05}`. Không dùng cùng một bộ lọc cho hai chính sách mà không ghi rõ.

### Bài D — Tìm khách hàng có field điện thoại hiện hữu

```sql
WHERE c.`primary_phone` IS VALUED
```

Tập ID kỳ vọng: `{c01, c04, c05, c06}`. Kết quả này có cả chuỗi rỗng và số `12345`; do đó `IS VALUED` chưa phải ràng buộc “số điện thoại hợp lệ”.

### Bài E — Khác biệt của field lồng nhau

Yêu cầu: chỉ lấy document có `profile` là object và `profile.city` bằng null **hoặc** missing.

```sql
WHERE c.`profile` IS OBJECT
  AND c.`profile`.`city` IS NOT VALUED
```

Tập ID kỳ vọng: `{c03, c04}`. `c05` có profile missing, `c06` có profile null nên không khớp điều kiện “profile là object”.

### Bài F — Tự thiết kế API tìm dữ liệu thiếu

Thiết kế một lựa chọn lọc điện thoại cho UI gồm: Tất cả, Có giá trị, Null rõ ràng, Thiếu field, Chưa có giá trị (null hoặc thiếu), Chuỗi rỗng. Với mỗi lựa chọn:

1. Viết một điều kiện SQL++ phản ánh đúng ý định.
2. Xác định có thể dùng derived query an toàn hay cần `@Query`/`CouchbaseTemplate`.
3. Kiểm thử trên bảng `c01`–`c07` và trên dữ liệu vừa được cập nhật.
4. Dùng `EXPLAIN` để kiểm tra liệu index dự kiến có hỗ trợ truy vấn missing hay không.

### Bảng kiểm trước khi triển khai

| Câu hỏi | Vì sao quan trọng |
| --- | --- |
| Field null hay hoàn toàn missing? | `IS NULL` và `IS MISSING` là hai điều kiện khác nhau. |
| Chuỗi rỗng, `false`, `0`, `[]` có ý nghĩa gì? | Chúng là giá trị hiện hữu, không mặc nhiên là null. |
| Query dùng `IsNull` có thực sự sinh đúng SQL++? | Khả năng hỗ trợ và ngữ nghĩa phụ thuộc phiên bản. |
| Có đang truyền tham số Java `null` để “bỏ filter” không? | Null input không biểu diễn rõ ý định nghiệp vụ. |
| Có object cha bị null/missing không? | Điều kiện nested field cần xử lý từng cấp nếu cần. |
| Có mảng hoặc nhiều kiểu dữ liệu trong cùng field? | `IsNull` một mình không diễn đạt đủ nghiệp vụ. |
| Index có bao phủ các document thiếu field không? | Một số cấu trúc index không lưu giá trị missing của khóa. |
| Có cần count/page hoặc query consistency không? | Đảm bảo tải lớn và đọc ngay sau ghi đúng yêu cầu. |

## 17. Ghi nhớ

Trong Couchbase, **`NULL` là giá trị được lưu rõ ràng**, còn **`MISSING` nghĩa là không tồn tại field**. `IS NULL`, `IS MISSING`, `IS VALUED` và `IS NOT VALUED` cho phép diễn đạt những điều kiện riêng biệt trong SQL++; chuỗi rỗng, số 0, `false` và mảng rỗng vẫn là các giá trị hiện hữu.

Derived query rất hiệu quả cho điều kiện đơn giản, nhưng tên phương thức `IsNull`/`IsNotNull` **không tự chứng minh** rằng truy vấn bao quát đúng null, missing và các trạng thái nghiệp vụ. Cần kiểm chứng trên **phiên bản Spring Data Couchbase**, đối chiếu JSON thực, SQL++ sinh ra và index. Khi logic yêu cầu xử lý field thiếu, object lồng nhau, mảng, kiểu dữ liệu hoặc nhiều bộ lọc tùy chọn, dùng `@Query` hoặc `CouchbaseTemplate` để biểu đạt chính xác hơn. Thiết kế đúng còn phải tính đến collection đích, phân trang, TTL, CAS, transaction, reactive và độ mới của index sau khi ghi.
