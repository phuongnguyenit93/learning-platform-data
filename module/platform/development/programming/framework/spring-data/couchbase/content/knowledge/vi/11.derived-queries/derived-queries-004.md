# Truy vấn chuỗi và điều kiện không phân biệt hoa thường

Trong **SPRING_DATA_COUCHBASE**, các màn hình tìm kiếm thường lọc document theo tên khách hàng, email, thành phố hoặc mã có dạng chuỗi. Bên cạnh điều kiện bằng nhau, người dùng có thể cần tìm tên **bắt đầu bằng**, **kết thúc bằng** hoặc **chứa** một cụm ký tự, và đôi khi muốn bỏ qua khác biệt chữ hoa/chữ thường. Spring Data Couchbase cho phép biểu diễn nhiều điều kiện như vậy bằng tên phương thức repository (*derived query*).

Bài học thuộc chương **Truy vấn dẫn xuất**, đi sâu vào **truy vấn chuỗi và điều kiện không phân biệt hoa thường**. Nội dung kết nối tên phương thức với document mapping và SQL++; hướng dẫn xử lý wildcard, Unicode tiếng Việt, index, phân trang và nhất quán truy vấn. Đây là một phần của tầng truy cập Couchbase: bucket/scope/collection quyết định nơi đọc dữ liệu, `CouchbaseTemplate` và `@Query` hỗ trợ truy vấn phức tạp hơn, còn TTL, CAS, giao dịch và API reactive ảnh hưởng đến vận hành các luồng sử dụng kết quả.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt so khớp **chính xác**, **tiền tố**, **hậu tố**, **chuỗi con** và **pattern**.
2. Viết và đọc các phương thức `findBy...`, `StartingWith`, `EndingWith`, `Containing` và `Like` theo property Java.
3. Hiểu ý nghĩa của `IgnoreCase`/`AllIgnoreCase` và xác minh khả năng hỗ trợ của phiên bản Spring Data Couchbase trước khi áp dụng.
4. Diễn đạt trường hợp không phân biệt hoa thường bằng `LOWER`/`UPPER` trong SQL++, hoặc dùng trường dữ liệu đã chuẩn hóa.
5. Phân biệt không phân biệt hoa/thường với không phân biệt dấu tiếng Việt, và nhận biết vấn đề Unicode.
6. Xử lý wildcard `%`, `_`, input rỗng, `NULL`/`MISSING` và dữ liệu đặc biệt.
7. Chọn index và cách phân trang, biết khi nào nên chuyển sang Couchbase Full Text Search (FTS).

## 2. Mô hình document và repository

Giả sử ứng dụng CRM dùng bucket `app`, scope `crm`, collection `customers`. Document mẫu:

```json
{
  "display_name": "Lan Anh",
  "email": "lan.anh@example.test",
  "status": "ACTIVE",
  "city": "HANOI"
}
```

ID document, ví dụ `customer::1001`, thuộc metadata khóa của Couchbase và không nhất thiết được lưu thành trường `id` trong JSON.

Khai báo entity:

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

    @Field("display_name")
    private String displayName;

    @Field
    private String email;

    @Field
    private String status;

    @Field
    private String city;

    protected Customer() {
        // Dành cho document mapping.
    }

    // Constructor nghiệp vụ và getters/setters được lược bỏ.
}
```

Một repository có thể mô tả các nhu cầu tra cứu chuỗi phổ biến:

```java
package example.crm;

import java.util.List;
import java.util.Optional;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);
    List<Customer> findByDisplayName(String displayName);

    List<Customer> findByDisplayNameStartingWith(String prefix);
    List<Customer> findByDisplayNameEndingWith(String suffix);
    List<Customer> findByDisplayNameContaining(String fragment);
    List<Customer> findByDisplayNameLike(String pattern);

    List<Customer> findByStatusAndDisplayNameStartingWith(
        String status, String prefix
    );
}
```

Các ví dụ dùng tên keyword Spring Data phổ biến để diễn đạt ý định. **Cần xác minh từ khóa và cách dịch sang SQL++ được hỗ trợ ở phiên bản Spring Data Couchbase đang sử dụng**: khả năng hỗ trợ có thể khác Spring Data JPA hoặc thay đổi theo phiên bản. Đừng xem một chữ ký Java hợp lệ là bằng chứng rằng query creator của Couchbase sẽ thực thi đúng kỳ vọng.

**Nhớ về mapping:** phương thức viết `DisplayName` tương ứng với property Java `displayName`; `@Field("display_name")` ánh xạ nó thành trường JSON `display_name`. Không dùng tên vật lý `display_name` để ghép trực tiếp tên phương thức.

## 3. Bốn kiểu tra cứu chuỗi

| Cách tìm | Phương thức minh họa | Ý định |
| --- | --- | --- |
| Bằng chính xác | `findByDisplayName("Lan Anh")` | Chuỗi bằng đúng `Lan Anh`. |
| Bắt đầu bằng | `findByDisplayNameStartingWith("Lan")` | Chuỗi có tiền tố `Lan`. |
| Kết thúc bằng | `findByDisplayNameEndingWith("Lan")` | Chuỗi có hậu tố `Lan`. |
| Chứa chuỗi con | `findByDisplayNameContaining("Lan")` | `Lan` xuất hiện ở bất kỳ vị trí nào. |
| Pattern tùy chọn | `findByDisplayNameLike("Lan%")` | Theo cú pháp mẫu `LIKE`. |

Ví dụ trên tập document:

| ID | `display_name` | `status` |
| --- | --- | --- |
| `c01` | Lan Anh | ACTIVE |
| `c02` | LAN PHUONG | ACTIVE |
| `c03` | Thanh Lan | SUSPENDED |
| `c04` | Lân Nguyễn | ACTIVE |
| `c05` | Lan-Anh | ACTIVE |
| `c06` | Bình Minh | ACTIVE |

Khi các phép so khớp **phân biệt hoa thường** và không tự bỏ dấu, ta kỳ vọng:

| Điều kiện | Tập ID |
| --- | --- |
| Bằng `Lan Anh` | `{c01}` |
| Bắt đầu bằng `Lan` | `{c01, c05}` |
| Kết thúc bằng `Lan` | `{c03}` |
| Chứa `Lan` | `{c01, c03, c05}` |
| Bắt đầu bằng `LAN` | `{c02}` |
| Chứa `lan` | `{}` |

Các tập ID không có thứ tự: nếu repository không khai báo `Sort`/`OrderBy`, SQL++ không đảm bảo thứ tự kết quả ổn định. Kết quả trên dựa trên ngữ nghĩa chuỗi phân biệt hoa thường thông thường; khi triển khai cần kiểm thử query được framework sinh ra.

### 3.1. Tại sao `findById` không giống `findByDisplayName`?

`findById("customer::1001")` thường dùng đường **key-value** của Couchbase để lấy document qua khóa. Ngược lại, `findByDisplayName("Lan Anh")` thường được chuyển sang **SQL++** và cần index hỗ trợ trường nội dung. Chúng có thể trông giống API Java thông thường, nhưng khác đường truy cập và đặc điểm consistency.

## 4. `LIKE` và ký tự đại diện

Có thể hình dung các điều kiện chuỗi bằng SQL++:

```sql
-- Chỉ minh họa ngữ nghĩa, không phải SQL++ nguyên văn do Spring Data sinh.
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`display_name` LIKE "Lan%";
```

| Điều kiện SQL++ minh họa | Ý nghĩa |
| --- | --- |
| `display_name = "Lan Anh"` | Bằng chính xác. |
| `display_name LIKE "Lan%"` | Bắt đầu bằng Lan. |
| `display_name LIKE "%Lan"` | Kết thúc bằng Lan. |
| `display_name LIKE "%Lan%"` | Chứa Lan. |
| `display_name LIKE "L_n"` | Chữ `L`, một ký tự bất kỳ, rồi chữ `n`. |

Hai wildcard thường gặp của `LIKE`:

- `%` khớp với chuỗi ký tự bất kỳ, kể cả chuỗi rỗng.
- `_` khớp một ký tự ở một vị trí.

Ví dụ `"Lan%"` có thể khớp `Lan`, `Lan Anh` và `Lan-Anh`, còn `"%Lan%"` khớp cả `Thanh Lan`.

### 4.1. `Like` khác `Containing`

```java
repository.findByDisplayNameLike("Lan%");
repository.findByDisplayNameContaining("Lan");
```

Ở ví dụ đầu, tham số là **pattern**: bên gọi chủ động chỉ định `%`. Ở ví dụ sau, tham số mô tả **chuỗi con**; query creator của thư viện sẽ diễn giải theo keyword `Containing` tương ứng.

Không nên tự thêm `%` vào tham số `Containing` rồi mặc định framework cũng hiểu đó là ý định chính xác. Cần xác minh quy tắc wildcard và escaping trên phiên bản Couchbase thực tế.

### 4.2. Binding tham số không tự escape wildcard

Giả sử người dùng muốn tìm đúng cụm `Mai 100%`. Dấu `%` trong pattern `LIKE` mang ý nghĩa đặc biệt, nên nếu đưa nguyên chuỗi vào pattern tìm kiếm mà không escape, truy vấn có thể khớp các tên không mong muốn.

Quy trình khuyến nghị với **tìm kiếm literal**:

1. Chọn ký tự escape mà biểu thức SQL++ và API đang dùng hỗ trợ.
2. Escape các ký tự đặc biệt trong đầu vào, tối thiểu `%`, `_` và ký tự escape nếu có.
3. Sau đó mới thêm wildcard phục vụ điều kiện tiền tố, hậu tố hoặc chứa.
4. Binding pattern hoàn chỉnh như tham số; không tự nối giá trị đầu vào vào nguyên văn câu SQL++.

**Hai vấn đề riêng biệt:** parameter binding giúp tránh đưa người dùng vào cấu trúc câu SQL++; wildcard escaping giúp người dùng tìm dấu `%` hay `_` như ký tự văn bản. Một cơ chế không tự động thay thế cơ chế kia.

Java và SQL++ có nhiều lớp escaping khác nhau. Không sao chép cú pháp `ESCAPE` từ một SQL dialect khác mà chưa kiểm thử trên Couchbase. Hãy tạo test với `100%`, `A_B` và ký tự escape.

## 5. Điều kiện không phân biệt hoa thường

Người dùng nhập `lan` nhưng muốn thấy cả `Lan Anh` và `LAN PHUONG`. Đó là **case-insensitive search**: bỏ qua khác biệt hoa/thường.

Phân biệt rõ với những mong đợi khác:

- `Lan` và `Lân`: khác dấu tiếng Việt, dù chỉ khác một dấu mũ.
- `Lan Anh` và `LanAnh`: khác khoảng trắng.
- `Lan Anh` và `Lan-Anh`: khác dấu câu.
- `Lan` và `Lancelot`: liên quan tới điều kiện tiền tố/chuỗi con, không phải chuyện hoa/thường.

Không nên tự động coi các cặp này là tương đương nếu chưa có yêu cầu nghiệp vụ.

### 5.1. `IgnoreCase`, `AllIgnoreCase` trong tên phương thức

Trong các module Spring Data, cách đặt tên thường gặp để biểu diễn ý định không phân biệt hoa/thường là:

```java
// Ví dụ ý định: phải xác minh hỗ trợ của Spring Data Couchbase.
List<Customer> findByDisplayNameIgnoreCase(String name);

List<Customer> findByDisplayNameContainingIgnoreCase(String fragment);

List<Customer> findByStatusAndDisplayNameContainingIgnoreCase(
    String status, String fragment
);
```

`IgnoreCase` thường gắn với điều kiện chuỗi tương ứng; `AllIgnoreCase` có ý nghĩa áp dụng quy tắc đó cho các điều kiện chuỗi liên quan theo ngữ pháp Spring Data nói chung:

```java
// Chỉ dùng khi phiên bản Couchbase thực sự hỗ trợ.
List<Customer> findByStatusAndCityAllIgnoreCase(
    String status, String city
);
```

**Giới hạn quan trọng:** không phải mọi Spring Data module đều hỗ trợ mọi modifier. Cách Spring Data Couchbase xử lý `IgnoreCase` hoặc `AllIgnoreCase` cũng có thể phụ thuộc phiên bản. Vì vậy, cần kiểm tra tài liệu đúng phiên bản, kiểm thử với dữ liệu `Lan`/`LAN`/`lan` và quan sát SQL++ sinh ra. Nếu modifier không hỗ trợ hoặc không đạt kết quả mong muốn, dùng cách chủ động ở phần sau.

### 5.2. Viết ý định bằng SQL++ `LOWER`/`UPPER`

Ví dụ SQL++ so sánh chính xác sau khi chuẩn hóa chữ thường:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE LOWER(c.`display_name`) = LOWER($name);
```

Ví dụ so khớp tiền tố:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE LOWER(c.`display_name`) LIKE LOWER($prefixPattern);
```

Giả sử `$prefixPattern` đã được binding với pattern `"lan%"` sau khi xử lý escaping phù hợp. Tương tự, tìm chuỗi con có thể dùng `"%lan%"`.

Các truy vấn SQL++ này **mô tả logic**, chưa phải mã `@Query` hoàn chỉnh có thể đưa vào mọi phiên bản Spring Data Couchbase. Cần chú ý projection để ánh xạ entity, metadata, discriminator và cú pháp binding tham số theo framework/cấu hình đang dùng.

Ưu điểm của SQL++ tường minh là thấy rõ vị trí áp dụng `LOWER`. Tuy nhiên, gọi hàm lên trường truy vấn có thể ảnh hưởng cách dùng index nếu index chỉ lưu giá trị nguyên bản.

## 6. Trường tìm kiếm được chuẩn hóa sẵn

Khi tìm không phân biệt hoa thường rất thường xuyên, có thể lưu thêm một field riêng cho tìm kiếm:

```json
{
  "display_name": "Lan Anh",
  "display_name_fold": "lan anh",
  "status": "ACTIVE"
}
```

Ví dụ quy tắc Java đơn giản:

```java
import java.util.Locale;

public static String foldForSearch(String input) {
    return input == null
        ? null
        : input.toLowerCase(Locale.ROOT);
}
```

Entity bổ sung một property:

```java
@Field("display_name_fold")
private String displayNameFold;
```

Repository tìm theo property đó:

```java
List<Customer> findByDisplayNameFoldStartingWith(String prefixFold);
```

Service cũng chuẩn hóa đầu vào trước khi gọi:

```java
String prefixFold = foldForSearch(userPrefix);
List<Customer> results =
    repository.findByDisplayNameFoldStartingWith(prefixFold);
```

Lợi ích là index có thể đặt trực tiếp trên `display_name_fold`. Đổi lại, cần:

1. Cập nhật field chuẩn hóa **mỗi khi tên hiển thị thay đổi**.
2. Backfill các document đã tồn tại.
3. Giữ nguyên `display_name` để hiển thị tên gốc chính xác.
4. Định nghĩa rõ chuẩn Unicode, xử lý khoảng trắng và dấu theo nghiệp vụ.
5. Kiểm thử sự tương đương giữa quy tắc chuẩn hóa ở nơi ghi và nơi truy vấn.

`toLowerCase(Locale.ROOT)` là ví dụ lowercase phổ biến, không phải giải pháp Unicode case folding hoàn hảo cho mọi ngôn ngữ. Không giả định nó luôn tương đương với hàm `LOWER` phía SQL++ trên mọi ký tự Unicode.

### 6.1. Email không phân biệt hoa thường

Email thường được tìm kiếm bằng cách không phân biệt hoa/thường theo chính sách tài khoản, nhưng phải phân biệt quy tắc ứng dụng với chuẩn địa chỉ email. Phần domain không phân biệt chữ hoa/thường; phần local-part có thể có trường hợp phân biệt theo tiêu chuẩn, dù nhiều dịch vụ email thực tế không phân biệt.

Nếu chọn normalize toàn bộ email để đăng nhập/tra cứu, ứng dụng phải áp dụng nhất quán ở tạo tài khoản, xác minh, kiểm tra trùng và truy vấn. **Secondary index không tự bảo đảm uniqueness**; `findByEmailIgnoreCase` hay field normalized không thay thế một cơ chế bảo đảm duy nhất trong quy trình ghi.

## 7. Chữ hoa/thường và dấu tiếng Việt

| Chuỗi gốc | Lowercase thông thường |
| --- | --- |
| `Lan` | `lan` |
| `LAN` | `lan` |
| `Lân` | `lân` |
| `LẮM` | `lắm` |
| `Đức` | `đức` |

`Lan` và `Lân` khác nhau sau khi đưa về chữ thường. Nếu UI cần người dùng gõ `lan` nhưng nhận cả `Lân`, đó là yêu cầu **accent-insensitive**, khác với case-insensitive.

Để tìm không dấu, có thể chuẩn hóa một field tìm kiếm bổ sung với quy tắc rõ ràng; tránh biến đổi tên gốc. Cần chú ý:

- Unicode có thể lưu cùng hình thức hiển thị dưới các dạng tổ hợp khác nhau (`NFC` và `NFD`).
- Loại bỏ combining marks theo cách chung có thể làm các từ khác nghĩa trở nên trùng nhau.
- Chữ `đ`/`Đ` không tự chuyển thành `d`/`D` chỉ bằng việc bỏ combining marks.
- Analyzer của FTS có thể có quy tắc tokenization, lowercase và xử lý dấu riêng; phải cấu hình và kiểm thử với tiếng Việt thật.

Bỏ dấu để hỗ trợ tìm kiếm không đồng nghĩa có thể dùng tên đã bỏ dấu để định danh người, đối soát hay xuất giấy tờ. Giữ nguyên dữ liệu gốc và xác định từng trường phục vụ đúng mục đích.

## 8. Phối hợp điều kiện chuỗi với các trường khác

Yêu cầu: “Tìm khách hàng ACTIVE có tên bắt đầu bằng Lan”.

```java
List<Customer> findByStatusAndDisplayNameStartingWith(
    String status, String prefix
);
```

```java
List<Customer> results =
    repository.findByStatusAndDisplayNameStartingWith("ACTIVE", "Lan");
```

Logic minh họa:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
  AND c.`display_name` LIKE "Lan%";
```

Với bảng mục 3 và so khớp phân biệt hoa thường, kết quả là `{c01, c05}`. `c02` có chữ `LAN` viết hoa; `c03` có `Lan` ở cuối nhưng trạng thái SUSPENDED.

Nếu cả điều kiện status và tên đều muốn bỏ qua hoa/thường, cần phân biệt việc áp dụng case-insensitive cho **một field** hay **cả hai field**. Không mặc định `IgnoreCase` áp dụng cho mọi điều kiện trong tên phương thức. Khi tên method chứa nhiều `And`/`Or` hoặc cần ngoặc logic phức tạp, dùng SQL++ tường minh hay `CouchbaseTemplate` thường giúp tránh sai nhóm điều kiện.

## 9. Index: sự khác biệt giữa tiền tố và chuỗi con

Các phương thức lọc theo chuỗi document thường đi qua **SQL++** và index. Khả năng dùng index phụ thuộc mẫu điều kiện:

| Mẫu truy vấn | Hướng tối ưu |
| --- | --- |
| `display_name = ?` | Secondary index theo trường tìm kiếm. |
| `display_name LIKE "Lan%"` | Prefix có thể dùng range scan phù hợp nếu index hỗ trợ, xác minh bằng `EXPLAIN`. |
| `display_name LIKE "%Lan"` | Wildcard đầu chuỗi thường làm kém hiệu quả truy cập theo thứ tự index. |
| `display_name LIKE "%Lan%"` | Tìm substring thường khó thu hẹp bằng index B-tree thông thường. |
| `LOWER(display_name) = ?` | Có thể cần expression index hoặc field đã chuẩn hóa. |
| Nhiều từ, tìm gần đúng, ranking | Cân nhắc Couchbase FTS. |

Giả sử truy vấn entity do Spring Data sinh có discriminator `_class` và sử dụng tên JSON `display_name`. Một số index **minh họa**:

```sql
-- Bộ lọc status kết hợp tiền tố tên.
CREATE INDEX ix_customers_type_status_name
ON `app`.`crm`.`customers`(
    `_class`,
    `status`,
    `display_name`
);

-- Nếu câu truy vấn thực tế lọc theo LOWER(display_name).
CREATE INDEX ix_customers_type_lower_name
ON `app`.`crm`.`customers`(
    `_class`,
    LOWER(`display_name`)
);

-- Nếu ứng dụng đã lưu field chuẩn hóa.
CREATE INDEX ix_customers_type_name_fold
ON `app`.`crm`.`customers`(
    `_class`,
    `display_name_fold`
);
```

Đây không phải danh sách index bắt buộc. Ứng dụng có thể tùy chỉnh discriminator hoặc query creator sinh cấu trúc khác. Index có chi phí lưu trữ, cập nhật và tài nguyên; cần kiểm tra SQL++ thực tế, mẫu truy cập, kế hoạch thực thi trước khi quyết định.

### 9.1. Chạy `EXPLAIN`

```sql
EXPLAIN
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
  AND c.`display_name` LIKE "Lan%";
```

Khi kiểm tra, bổ sung điều kiện Spring Data tự sinh, đối chiếu index được chọn, số phần tử scan và chi phí sort/fetch trên dữ liệu đại diện. So sánh prefix `"Lan%"` với substring `"%Lan%"`; đừng mặc định hai kiểu có chi phí tương tự vì cùng dùng `LIKE`.

### 9.2. Khi nào chuyển sang Full Text Search?

`LIKE "%...%"` phù hợp cho một số tìm kiếm đơn giản, nhưng khi sản phẩm cần tách từ, tìm gần đúng, nhiều trường, kết quả theo mức liên quan hoặc gợi ý, Couchbase **Full Text Search (FTS)** thường là công cụ phù hợp hơn.

FTS có index/analyzer và API riêng; nó không phải kết quả tự động của một phương thức `findByDisplayNameContaining` chạy qua SQL++. Nếu dùng FTS, phải xem xét quy tắc tokenize, lowercase, diacritics, tính nhất quán của index và đặc điểm tiếng Việt. Không tự xem FTS và `LIKE` là tương đương về tập kết quả.

## 10. Xử lý `NULL`, `MISSING` và input bất thường

Ba document dưới đây khác nhau:

```json
{"display_name": null}
```

```json
{}
```

```json
{"display_name": ""}
```

`NULL` là field tồn tại với null; `MISSING` là field không tồn tại; `""` là chuỗi rỗng. Điều kiện `display_name LIKE "Lan%"` không nên được xem là khớp bất kỳ trường hợp nào trên.

Nếu nghiệp vụ cần tìm “chưa có tên”, phải quy định có tính cả chuỗi rỗng và chuỗi chỉ có khoảng trắng không; sau đó dùng SQL++ phù hợp. `IS NULL` không đồng nghĩa `IS MISSING`.

### 10.1. Input rỗng có thể trở thành pattern toàn tập

Nếu ứng dụng chuyển prefix rỗng thành `"%"`, truy vấn có thể khớp nhiều document có trường chuỗi hợp lệ. Vì vậy service nên quy định:

1. Input `null` có bị từ chối hay mang nghĩa không áp dụng bộ lọc?
2. Có trim khoảng trắng đầu/cuối không?
3. Độ dài tối thiểu để bắt đầu tìm là bao nhiêu?
4. Độ dài tối đa và kích thước trang tối đa được phép?
5. Ký tự `%` và `_` là literal hay wildcard do người dùng chủ đích nhập?

Ví dụ validation:

```java
public static String validatedPrefix(String input) {
    if (input == null) {
        throw new IllegalArgumentException("Thiếu tiền tố");
    }

    String prefix = input.strip();

    if (prefix.length() < 2) {
        throw new IllegalArgumentException("Tiền tố quá ngắn");
    }

    if (prefix.length() > 100) {
        throw new IllegalArgumentException("Tiền tố quá dài");
    }

    return prefix;
}
```

Mức 2 và 100 ký tự chỉ là ví dụ; sản phẩm cần quy định theo UX, dữ liệu Unicode và mức tải thật.

## 11. Phân trang, sắp xếp và kiểu trả về

Một tìm kiếm `Containing` có thể khớp hàng chục nghìn document, nên không nên mặc định trả `List<Customer>` không giới hạn cho UI tìm kiếm.

Có thể khai báo:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Customer> findByStatusAndDisplayNameStartingWith(
    String status,
    String prefix,
    Pageable pageable
);
```

Cách gọi:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

var page = repository.findByStatusAndDisplayNameStartingWith(
    "ACTIVE",
    "Lan",
    PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "displayName")
    )
);
```

`PageRequest` bắt đầu từ trang 0; `Sort` nhận property Java `displayName`, SQL++ và index tham chiếu trường JSON `display_name`. Nếu nhiều document có cùng tên, nên có tiêu chí sắp xếp phụ để trang ổn định. Truy vấn `Page` có thể cần thêm truy vấn đếm; cân nhắc chi phí với tập kết quả lớn.

| Kiểu trả về | Dùng khi |
| --- | --- |
| `Optional<Customer>` | Kỳ vọng tối đa một document, có ràng buộc nghiệp vụ đảm bảo. |
| `List<Customer>` | Tập kết quả nhỏ/được kiểm soát. |
| `Page<Customer>` | Muốn phân trang và biết tổng số phần tử. |
| `long countByStatus(...)` | Chỉ cần số lượng, không tải entity. |
| `boolean existsByEmail(...)` | Chỉ cần biết có document khớp, không thay cơ chế uniqueness. |

## 12. Consistency, TTL, CAS, giao dịch và reactive

### 12.1. Vừa đổi tên nhưng tìm theo tên mới chưa thấy

```text
save(customer)                     -> ghi thành công qua key-value
findById(customer.id)              -> truy cập theo khóa ID
findByDisplayNameStartingWith(...) -> SQL++ tra cứu qua index
```

Index truy vấn có thể phản ánh thao tác ghi muộn hơn đường key-value. Nếu nghiệp vụ cần tìm ngay bản ghi vừa ghi, phải xem xét query scan consistency phù hợp (ví dụ mức tương đương `REQUEST_PLUS` khi API hỗ trợ) hoặc đọc theo ID. Mức nhất quán cao hơn có thể làm tăng độ trễ.

### 12.2. TTL, CAS và transaction

- **TTL:** Document hết hạn có thể không còn xuất hiện ở lần tìm tiếp theo dù chuỗi tìm kiếm không đổi.
- **CAS/optimistic locking:** Kết quả đọc không khóa document cho lần ghi sau. Khi cập nhật `display_name` và `display_name_fold`, cần xử lý xung đột và duy trì đồng bộ giữa hai field.
- **Giao dịch:** Chuỗi `findBy...` rồi `save(...)` không mặc nhiên là giao dịch nguyên tử. Với nghiệp vụ nhiều bước cần tính nguyên tử, phải dùng giải pháp transaction tương ứng của SDK/Spring Data Couchbase.

### 12.3. Cùng bộ lọc trong repository reactive

```java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByDisplayNameStartingWith(String prefix);

    Flux<Customer> findByStatusAndDisplayNameContaining(
        String status, String fragment
    );
}
```

`Mono<Customer>` diễn tả tối đa một kết quả; `Flux<Customer>` diễn tả nhiều kết quả. Reactive không thay đổi cách phân tích keyword, nhu cầu index hay tính mới của SQL++ index. Không gọi `block()` trong luồng web reactive nếu không có kiến trúc cô lập blocking phù hợp.

## 13. Bài tập áp dụng: ô tìm tên khách hàng

**Yêu cầu:** Người dùng nhập một phần tên, chỉ tìm khách hàng ACTIVE, không phân biệt hoa/thường, chưa cần bỏ dấu tiếng Việt. Kết quả sắp tên tăng dần, mỗi trang tối đa 20 document.

**Bước 1 — Chọn ngữ nghĩa.** Nhập `"lan"` phải tìm `Lan Anh`, `LAN PHUONG` và `Lan-Anh`. `Thanh Lan` không được lấy vì status SUSPENDED; `Lân Nguyễn` không được tự xem là tương đương `lan` nếu chưa có yêu cầu bỏ dấu.

**Bước 2 — Chọn API.** Nếu phiên bản Spring Data Couchbase hỗ trợ và kiểm thử thành công modifier kết hợp, có thể khai báo theo ý định:

```java
Page<Customer> findByStatusAndDisplayNameContainingIgnoreCase(
    String status,
    String fragment,
    org.springframework.data.domain.Pageable pageable
);
```

Nếu keyword chưa được hỗ trợ hoặc kết quả khác mong đợi, dùng SQL++ `LOWER(display_name) LIKE ...` với pattern được binding/escape rõ ràng, hoặc dùng field `display_name_fold` đã chuẩn hóa khi ghi.

**Bước 3 — Lập index và xem kế hoạch.** Kiểm tra `EXPLAIN` trên SQL++ thực, đặc biệt khi substring có wildcard đầu chuỗi. Nếu UI cần fuzzy search, ranking hay nhiều token, đánh giá FTS.

**Bước 4 — Giới hạn kết quả.** Dùng `Pageable`, đặt giới hạn kích thước trang ở service/controller, xác định thứ tự khi trùng tên; đánh giá chi phí count query.

**Bước 5 — Kiểm thử các trường hợp biên.**

| Dữ liệu hoặc đầu vào | Kỳ vọng cần xác minh |
| --- | --- |
| `lan`, `Lan`, `LAN` | Kết quả giống nhau khi thực sự bật case-insensitive. |
| `Lan` và `Lân` | Khác nhau nếu chỉ bỏ hoa/thường. |
| `Lan Anh` và `Lan-Anh` | Không tự bỏ dấu câu. |
| `Mai 100%` | Dấu `%` không trở thành wildcard nếu người dùng tìm literal. |
| `A_B` | Dấu `_` không được hiểu nhầm. |
| Input rỗng hoặc toàn khoảng trắng | Không vô tình quét toàn bộ collection. |
| `display_name = null` hoặc thiếu field | Tuân thủ hợp đồng xử lý `NULL`/`MISSING`. |
| Nhiều người trùng tên | Kiểu trả về và phân trang vẫn chính xác. |
| Vừa lưu tên mới rồi tìm | Query consistency đáp ứng nhu cầu đọc ngay. |

### Câu hỏi tự kiểm tra

1. **`StartingWith("Lan")` khác `Containing("Lan")` thế nào?** — Tiền tố chỉ khớp từ đầu chuỗi; contains khớp ở vị trí bất kỳ.
2. **Vì sao `IgnoreCase` không tự bỏ dấu tiếng Việt?** — Chuyển hoa/thường không xóa dấu thanh hay dấu chữ.
3. **Vì sao `LIKE "%lan%"` thường khó tối ưu hơn `LIKE "lan%"`?** — Wildcard đầu chuỗi làm giảm khả năng dùng thứ tự khóa index để giới hạn phạm vi.
4. **Binding tham số có đủ để tìm literal `100%` không?** — Chưa đủ; phải xử lý ngữ nghĩa wildcard của pattern.
5. **Nếu `ContainingIgnoreCase` không được phiên bản Couchbase hỗ trợ thì làm sao?** — Dùng SQL++ tường minh với `LOWER` và index tương ứng hoặc trường tìm kiếm đã chuẩn hóa.

## 14. Ghi nhớ

Các tên phương thức `findBy...`, `StartingWith`, `EndingWith`, `Containing` và `Like` thể hiện những kiểu so khớp chuỗi khác nhau. Điều kiện không phân biệt hoa/thường có thể được diễn đạt bằng `IgnoreCase`/`AllIgnoreCase` **khi phiên bản Spring Data Couchbase hỗ trợ**, hoặc bằng SQL++ `LOWER`/`UPPER` và trường dữ liệu chuẩn hóa. **Case-insensitive không đồng nghĩa accent-insensitive** và không tự xử lý dấu câu, khoảng trắng hay tìm kiếm gần đúng.

Một triển khai đáng tin cậy phải thống nhất **property Java và tên JSON**, quy tắc Unicode và wildcard, **index**, kiểu trả về, phân trang và consistency. Với tìm kiếm nhiều từ, sai chính tả hay ranking trên lượng lớn document, cần cân nhắc FTS thay vì cố mở rộng derived query hoặc lạm dụng `LIKE` có wildcard đầu chuỗi.
