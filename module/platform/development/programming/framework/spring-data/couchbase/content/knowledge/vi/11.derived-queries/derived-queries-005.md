# Điều kiện cho dữ liệu lồng nhau và tên thuộc tính Java

Trong **SPRING_DATA_COUCHBASE**, truy vấn dẫn xuất (*derived query*) cho phép Spring Data suy ra điều kiện tìm kiếm từ tên phương thức repository. Khi document chứa object lồng nhau, một điều kiện không chỉ tham chiếu tới `status` hay `email` mà còn có thể cần đọc giá trị trong `address.city` hoặc `profile.contact.email`. Cách đặt tên phương thức đúng phải dựa vào **đường dẫn thuộc tính Java**, trong khi truy vấn SQL++ thực thi trên **đường dẫn trường JSON** đã được document mapping ánh xạ.

Bài thuộc chương **Truy vấn dẫn xuất**, tập trung vào **điều kiện cho dữ liệu lồng nhau và tên thuộc tính Java**. Nội dung giải thích quy tắc phân tích đường dẫn, cách xử lý khi tên thuộc tính phẳng trùng với cách ghép tên property lồng nhau, vai trò của `@Field`, và giới hạn khi truy vấn mảng object. Đây là phần quan trọng của tầng truy cập Couchbase bằng Spring Data, nơi repository và `CouchbaseTemplate` phối hợp với SQL++, bucket/scope/collection, index, TTL, CAS, giao dịch và API reactive để giữ dữ liệu chính xác và hệ thống có thể vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **property Java**, **field JSON** và **document ID** trong Spring Data Couchbase.
2. Đọc cấu trúc entity và diễn đạt điều kiện trên object lồng nhau qua đường dẫn property.
3. Giải thích vì sao `findByAddressCity(...)` có thể khác `findByAddress_City(...)`.
4. Dùng `@Field` để ánh xạ tên property Java sang JSON, kể cả tại nhiều tầng lồng nhau.
5. Kết hợp đường dẫn property với `And`, `In`, phép so sánh, `Sort` và `Pageable` khi phiên bản hỗ trợ.
6. Nhận biết `NULL`, `MISSING` và dữ liệu lồng nhau thiếu một tầng ở giữa.
7. Thiết kế index cho đường dẫn JSON, phân biệt object lồng nhau với **mảng object** và biết khi nào dùng SQL++ tường minh.
8. Kiểm tra derived query bằng dữ liệu biên, `EXPLAIN` và các tình huống nhất quán sau khi ghi.

## 2. Ba lớp tên gọi cần phân biệt

Giả sử một document nằm trong bucket `app`, scope `crm`, collection `customers` và có cấu trúc:

```json
{
  "status": "ACTIVE",
  "email": "lan@example.test",
  "address_info": {
    "city_name": "HANOI",
    "district_name": "CAU_GIAY",
    "details": {
      "zone": "NORTH"
    }
  },
  "address_city": "HCM",
  "contacts": [
    {"type": "MOBILE", "value": "0900000001"},
    {"type": "EMAIL", "value": "lan@example.test"}
  ]
}
```

Ví dụ này cố tình chứa **hai nơi lưu thông tin thành phố**:

- `address_info.city_name`: thành phố trong object địa chỉ lồng nhau.
- `address_city`: một trường chuỗi phẳng ở document gốc, có thể đến từ hệ thống cũ.

Document còn có ID, chẳng hạn `customer::1001`, được Couchbase quản lý tách khỏi nội dung JSON.

| Lớp tên | Ví dụ | Vai trò |
| --- | --- | --- |
| **Property Java** | `address`, `city`, `addressCity` | Tên Java để Spring Data phân tích method name. |
| **Field JSON** | `address_info`, `city_name`, `address_city` | Đường dẫn thực trong document và SQL++/index. |
| **Document ID** | `customer::1001` | Khóa key-value, thường được mapping qua `@Id`. |

Lỗi phổ biến là nhìn JSON thấy `address_info.city_name` rồi khai báo phương thức `findByAddressInfoCityName`, dù entity Java thực tế có property `address.city`. Đúng hay sai được quyết định bằng **mô hình entity**, không phải bằng cách nối tên khóa JSON.

## 3. Khai báo model Java để ánh xạ object lồng nhau

Giả sử kết nối đến bucket `app` đã được cấu hình, và ứng dụng dùng các annotation scope/collection tương thích với phiên bản Spring Data Couchbase đã chọn.

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

    @Field("address_info")
    private Address address;

    @Field("address_city")
    private String addressCity;

    @Field
    private List<Contact> contacts;

    protected Customer() {
        // Dành cho cơ chế mapping.
    }

    // Constructor nghiệp vụ và getters/setters được lược bỏ.
}

class Address {

    @Field("city_name")
    private String city;

    @Field("district_name")
    private String district;

    @Field
    private AddressDetails details;

    protected Address() {}

    // Getters/setters được lược bỏ.
}

class AddressDetails {

    @Field
    private String zone;

    protected AddressDetails() {}

    // Getters/setters được lược bỏ.
}

class Contact {

    @Field
    private String type;

    @Field
    private String value;

    protected Contact() {}

    // Getters/setters được lược bỏ.
}
```

Trong entity này:

- Java `Customer.address` tương ứng với JSON `address_info`.
- Java `Customer.address.city` tương ứng với JSON `address_info.city_name`.
- Java `Customer.address.details.zone` tương ứng với JSON `address_info.details.zone`.
- Java `Customer.addressCity` tương ứng với JSON `address_city`.
- Java `Customer.contacts` là **một danh sách các object**, khác với object đơn `address`.

Các thành phần object được mapping theo quy tắc và converter của Spring Data Couchbase. Nếu dùng converter tùy chỉnh, dữ liệu thực tế có thể không giống cấu trúc ví dụ; cần kiểm tra JSON được lưu và truy vấn do framework sinh ra.

## 4. Derived query dùng tên property Java, không dùng tên field JSON

Một repository tìm thành phố trong object lồng nhau có thể khai báo theo đường dẫn property:

```java
package example.crm;

import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    List<Customer> findByAddress_City(String city);

    List<Customer> findByStatusAndAddress_City(
        String status, String city
    );

    List<Customer> findByAddress_District(String district);

    List<Customer> findByAddress_Details_Zone(String zone);

    List<Customer> findByAddressCity(String flatAddressCity);
}
```

Ký tự `_` trong `Address_City` **không phải** một ký tự nằm trong tên trường JSON. Nó là **điểm tách đường dẫn property một cách tường minh** trong cách Spring Data phân tích tên phương thức: từ property `address` đi tiếp vào property `city`.

Cách diễn giải các phương thức trên:

| Tên phương thức | Property Java | JSON được nhắm tới |
| --- | --- | --- |
| `findByAddress_City` | `address.city` | `address_info.city_name` |
| `findByStatusAndAddress_City` | `status` và `address.city` | `status` và `address_info.city_name` |
| `findByAddress_District` | `address.district` | `address_info.district_name` |
| `findByAddress_Details_Zone` | `address.details.zone` | `address_info.details.zone` |
| `findByAddressCity` | `addressCity` | `address_city` |

Phương thức `findByAddress_City("HANOI")` có thể được hiểu theo SQL++ minh họa:

```sql
-- Biểu đạt logic, không phải nguyên văn SQL++ của mọi phiên bản.
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`address_info`.`city_name` = $city;
```

Spring Data Couchbase có thể thêm metadata document, điều kiện phân biệt kiểu entity và cách binding tham số khác. Khi đánh giá tính chính xác hoặc index, phải xem truy vấn thực sự được thư viện sinh ra.

### 4.1. Vì sao `findByAddressInfoCityName` là sai?

Phương thức này khiến parser tìm các property mang tên `addressInfoCityName`, hoặc thử tách thành những property Java tương ứng. Nhưng entity không có `addressInfo` hay `cityName` ở nơi đó: `address_info` và `city_name` chỉ là tên **JSON** được khai báo qua `@Field`.

Trong ví dụ, cần dùng `findByAddress_City` để diễn đạt `Customer.address.city`. Trên một entity khác có property Java thực sự tên `addressInfo` chứa property `cityName`, cách đặt tên sẽ khác. Không tồn tại một quy tắc “chuyển snake_case JSON thành CamelCase method” mà có thể áp dụng độc lập với model Java.

## 5. Tại sao cần dấu gạch dưới `_` để tách đường dẫn?

Spring Data Commons có bộ phân tích property path: khi gặp tên method dạng `findByAddressCity`, parser cố xác định một property tên `addressCity` ở entity gốc; nếu không tìm được, nó có thể diễn giải theo đường dẫn `address.city` tùy cấu trúc model và quy tắc phân tích.

Điều này dẫn đến **mơ hồ** nếu entity có đồng thời:

```java
@Field("address_info")
private Address address;

@Field("address_city")
private String addressCity;
```

Cả hai thông tin đều hợp lệ nhưng mang nghĩa khác nhau. Quy tắc đọc:

```java
findByAddressCity("HANOI")
```

ưu tiên property **phẳng** `addressCity` khi property đó tồn tại. Trong khi:

```java
findByAddress_City("HANOI")
```

buộc parser đi theo đường dẫn **lồng nhau** `address.city`.

### 5.1. Ví dụ dữ liệu cho thấy khác biệt

Giả sử một document lưu:

```json
{
  "address_city": "HCM",
  "address_info": {
    "city_name": "HANOI"
  }
}
```

Hai lời gọi này không tương đương:

```java
repository.findByAddressCity("HANOI");
// So với:
repository.findByAddress_City("HANOI");
```

Bản đầu tìm giá trị `address_city` ở cấp gốc, tức `HCM` nên **không khớp** document. Bản sau tìm `address_info.city_name`, tức `HANOI` nên **khớp**.

Nếu dùng `findByAddressCity` để định nghĩa bộ lọc mới trong khi nghiệp vụ yêu cầu thành phố của địa chỉ lồng nhau, code có thể chạy bình thường nhưng trả kết quả sai. Đây là lỗi khó nhận ra hơn lỗi parser từ chối một tên phương thức không tồn tại property.

### 5.2. Dấu `_` trong method khác dấu `_` trong JSON

- `Address_City`: ký tự `_` là cú pháp tách **property path** trong tên method Spring Data.
- `address_info`, `city_name`: ký tự `_` là một phần tên khóa JSON.
- `AddressCity`: không có ký tự tách, có thể trỏ thẳng tới property Java `addressCity`.

Đừng cố đặt property Java tên `address_city` chỉ để khớp JSON; cách đó làm parser khó diễn giải và phá vỡ quy ước đặt tên Java. Giữ property Java có tên rõ nghĩa, dùng `@Field` cho mapping trường vật lý.

## 6. Kết hợp điều kiện lồng nhau với trường cấp gốc

Ví dụ tìm khách hàng **ACTIVE** trong thành phố **HANOI**:

```java
List<Customer> findByStatusAndAddress_City(
    String status, String city
);
```

Lời gọi:

```java
List<Customer> customers = repository
    .findByStatusAndAddress_City("ACTIVE", "HANOI");
```

Ý định SQL++:

```sql
WHERE c.`status` = "ACTIVE"
  AND c.`address_info`.`city_name` = "HANOI"
```

Tên phương thức thể hiện hai điều kiện, một property cấp gốc (`status`), một property lồng nhau (`address.city`). Thứ tự tham số phải tương ứng với thứ tự property trong tên method.

Tương tự, kết hợp hai property lồng nhau:

```java
List<Customer> findByAddress_CityAndAddress_District(
    String city,
    String district
);
```

Ý định:

```sql
WHERE c.`address_info`.`city_name` = "HANOI"
  AND c.`address_info`.`district_name` = "CAU_GIAY"
```

Nếu trộn nhiều `And` và `Or`, phải kiểm tra cách parser nhóm điều kiện. Đối với nhóm ngoặc nghiệp vụ phức tạp, dùng SQL++ tường minh qua `@Query` thường dễ đọc hơn một tên phương thức dài.

## 7. Đường dẫn sâu hơn hai tầng

Khi model có `Customer.address.details.zone`, tên phương thức có thể diễn đạt ranh giới mỗi tầng:

```java
List<Customer> findByAddress_Details_Zone(String zone);
```

Lời gọi:

```java
List<Customer> northCustomers =
    repository.findByAddress_Details_Zone("NORTH");
```

Đường JSON dự kiến là `address_info.details.zone`. Khi dùng property lồng nhau nhiều tầng, cần kiểm tra:

1. Mỗi đoạn của đường dẫn có đúng property Java không: `address` → `details` → `zone`.
2. Kiểu Java tại mỗi tầng có được document mapper nhận diện như object phù hợp không.
3. Tên JSON có bị đổi bởi `@Field` hoặc converter tùy chỉnh không.
4. SQL++ sinh ra có tham chiếu đúng đường JSON đã lưu không.
5. Có index hỗ trợ đường dẫn và predicate thực tế không.

**Giới hạn theo phiên bản:** Bộ phân tích property path thuộc Spring Data Commons, nhưng khả năng tạo SQL++ hợp lệ cho một cấu trúc lồng nhau cụ thể phụ thuộc Spring Data Couchbase và mapping. Vì vậy, trước khi phụ thuộc vào một tên phương thức nhiều tầng, hãy kiểm thử với phiên bản ứng dụng thực tế. Nếu truy vấn dẫn xuất không hỗ trợ đúng đường dẫn mong muốn, dùng `@Query` hoặc `CouchbaseTemplate` để diễn đạt rõ điều kiện.

## 8. Kết hợp đường dẫn với `In`, phép so sánh và sắp xếp

Những hậu tố quen thuộc của Spring Data có thể biểu diễn điều kiện trên property lồng nhau, miễn phiên bản Couchbase repository hỗ trợ tổ hợp cần dùng.

Ví dụ tìm khách hàng ở một trong nhiều thành phố:

```java
List<Customer> findByAddress_CityIn(
    java.util.Collection<String> cities
);
```

Diễn giải:

```sql
WHERE c.`address_info`.`city_name` IN ["HANOI", "DANANG"]
```

Hoặc tìm theo mã bưu điện nếu model lưu kiểu chuỗi:

```java
List<Customer> findByAddress_PostalCode(String postalCode);
```

Để phương thức cuối hợp lệ, phải **bổ sung property `postalCode` vào class `Address`**, chẳng hạn `@Field("postal_code") private String postalCode;`. Ở model hiện tại, `Address` chưa có property đó; khai báo method mà không sửa entity sẽ gây lỗi parse property. Đây là minh họa về việc tên method phải xuất phát từ model, không thể tự chọn một property chỉ vì JSON chứa khóa tương tự.

### 8.1. Phân trang và sắp xếp

Có thể khai báo phương thức có phân trang:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Customer> findByStatusAndAddress_City(
    String status,
    String city,
    Pageable pageable
);
```

Nếu cần sắp xếp theo thành phố lồng nhau, đường property như `address.city` có thể được truyền qua API `Sort` **khi module/phiên bản hỗ trợ việc chuyển đường dẫn thành trường JSON**:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

var page = repository.findByStatusAndAddress_City(
    "ACTIVE",
    "HANOI",
    PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "address.city")
    )
);
```

Cần quan sát SQL++ tạo ra để chắc chắn `Sort` đã dùng `address_info.city_name` và index phù hợp. Không mặc định mọi cấu trúc nested sort hoặc keyword `OrderByAddress_City` được hỗ trợ đồng nhất ở mọi phiên bản Couchbase. Với tập dữ liệu có giá trị sort trùng nhau, cần khóa phụ để phân trang ổn định.

`Page` có thể phát sinh truy vấn đếm ngoài truy vấn lấy dữ liệu. Nếu chỉ cần trang tiếp theo và không cần tổng số, cân nhắc kiểu phân trang khác được phiên bản hỗ trợ để tránh chi phí đếm lớn.

## 9. Object lồng nhau và mảng object là hai bài toán khác nhau

Với một object đơn:

```json
{
  "address_info": {
    "city_name": "HANOI"
  }
}
```

đường truy cập `address_info.city_name` diễn đạt rõ **một** giá trị.

Nhưng với mảng object:

```json
{
  "contacts": [
    {"type": "MOBILE", "value": "0900000001"},
    {"type": "EMAIL", "value": "lan@example.test"}
  ]
}
```

yêu cầu “tìm document có **một phần tử contact** với `type = MOBILE` và `value = 0900000001`” đòi hỏi xét **cùng một phần tử** của mảng. Không nên tự suy diễn một tên như `findByContacts_TypeAndContacts_Value` sẽ tạo ra cùng ý nghĩa. Parser có thể không hỗ trợ traversal qua collection theo cách mong đợi, và hai điều kiện cũng có thể vô tình trỏ tới các phần tử khác nhau nếu biểu thức không được nhóm đúng.

SQL++ cho một phần tử cùng thỏa hai điều kiện có thể được viết rõ:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE ANY contact IN c.`contacts`
      SATISFIES contact.`type` = "MOBILE"
            AND contact.`value` = "0900000001"
      END;
```

Ý nghĩa của `ANY ... SATISFIES ... END` là tồn tại **ít nhất một** phần tử trong mảng `contacts` thỏa đồng thời hai predicate. Đây là tình huống thích hợp để dùng SQL++ tường minh qua `@Query` hoặc API query linh hoạt như `CouchbaseTemplate`, đồng thời xây dựng index mảng phù hợp nếu truy vấn thường xuyên và dữ liệu lớn.

**Điểm phân biệt:** `In` trong `findByAddress_CityIn(cities)` là kiểm tra **một field đơn** thuộc một tập giá trị truyền vào. Nó không tự biến việc truy cập mảng object `contacts` thành điều kiện tồn tại trên một phần tử. Hai mục tiêu cần các biểu thức khác nhau.

## 10. `NULL`, `MISSING` và thiếu object cha

JSON có thể tồn tại ở những trạng thái sau:

```json
{"address_info": {"city_name": "HANOI"}}
```

```json
{"address_info": {"city_name": null}}
```

```json
{"address_info": {}}
```

```json
{"address_info": null}
```

```json
{}
```

Đối với câu truy vấn tìm `address_info.city_name = "HANOI"`, chỉ document đầu tiên có chuỗi `HANOI` được mong đợi khớp. Các trường hợp sau khác nhau:

- Có `address_info` nhưng `city_name` là `NULL`.
- Có object `address_info` nhưng thiếu `city_name` → đường dẫn có thể dẫn đến `MISSING`.
- `address_info` bằng `NULL` hoặc hoàn toàn `MISSING` → đường dẫn lồng nhau không có giá trị chuỗi để so sánh.

Không đồng nhất `NULL` và `MISSING` trong Couchbase. Cú pháp SQL++ có `IS NULL` và `IS MISSING` để làm rõ ý định:

```sql
-- Chỉ lấy trường city_name được lưu dưới dạng null.
WHERE c.`address_info`.`city_name` IS NULL

-- Xét biểu thức đường dẫn bị thiếu.
WHERE c.`address_info`.`city_name` IS MISSING
```

Khi object cha không có hoặc không đúng kiểu, cần kiểm tra giá trị biểu thức và quy tắc mong muốn, đặc biệt nếu nghiệp vụ cần phân biệt **cha bị thiếu** với **con bị thiếu**. Khi đó có thể tách điều kiện kiểm tra từng cấp trong SQL++ thay vì dựa vào một tên phương thức `IsNull`.

Nếu query creator cung cấp keyword `IsNull` cho property lồng nhau, không được mặc định rằng nó tìm cả `MISSING`. Muốn xử lý riêng các trạng thái, hãy viết `@Query` và kiểm tra trên document thật.

## 11. Index cho JSON path lồng nhau

Derived query lọc trường nội dung thường chạy qua Query Service và index SQL++. Index cần tham chiếu **đường dẫn JSON vật lý**, không phải property Java.

Giả sử Spring Data Couchbase trong ứng dụng sinh predicate phân biệt loại entity qua trường `_class`, một index minh họa là:

```sql
CREATE INDEX ix_customer_type_status_address_city
ON `app`.`crm`.`customers`(
  `_class`,
  `status`,
  `address_info`.`city_name`
);
```

Index này có thể hữu ích cho bộ lọc:

```sql
WHERE c.`_class` = "example.crm.Customer"
  AND c.`status` = "ACTIVE"
  AND c.`address_info`.`city_name` = "HANOI"
```

**Chỉ mang tính minh họa:** tên/giá trị discriminator và query thật do framework sinh ra phụ thuộc cấu hình mapping. Nếu ứng dụng không dùng `_class` như giả định, cần thiết kế index khác. Không chép nguyên index mà chưa xem SQL++ thực tế.

Các nguyên tắc:

1. Đối chiếu property `address.city` với JSON `address_info.city_name`, kể cả alias được `@Field` khai báo ở mỗi cấp.
2. Với điều kiện kết hợp, xem thứ tự trường equality và range trong index; không mặc định index cho `address_city` cấp gốc dùng được cho `address_info.city_name`.
3. Index kết hợp như `(_class, status, address_info.city_name)` có thể phù hợp với truy vấn lọc type và status trước, nhưng không nhất thiết tối ưu khi chỉ tìm city.
4. Trường lồng nhau có thể `MISSING` ở nhiều document; cách index lưu/xử lý giá trị thiếu cần được kiểm tra trong kế hoạch thực thi và mục tiêu truy vấn.
5. Không tạo một index mới cho mọi phương thức repository; cân nhắc độ chọn lọc, chi phí ghi và tài nguyên.

### 11.1. Kiểm tra với `EXPLAIN`

```sql
EXPLAIN
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
  AND c.`address_info`.`city_name` = "HANOI";
```

Câu SQL++ chỉ mô tả logic. Trước khi kết luận index phù hợp, hãy dùng SQL++ đúng với câu do Spring Data thực thi, bổ sung discriminator/projection nếu có, rồi kiểm tra index được chọn, lượng quét, bước fetch và sort trên dữ liệu đại diện.

Đối với mảng `contacts`, có thể cần **array index** và dạng predicate `ANY` tương ứng; index trường object đơn không tự tối ưu mọi truy vấn trên array.

## 12. Kiểu trả về và truy vấn khi thiếu dữ liệu

Một số chữ ký thường gặp:

```java
List<Customer> findByAddress_City(String city);

long countByAddress_City(String city);

boolean existsByStatusAndAddress_City(
    String status, String city
);
```

Ý nghĩa:

| Kiểu trả về | Dùng khi | Lưu ý |
| --- | --- | --- |
| `List<Customer>` | Cần nhiều document. | Có thể tải tập lớn, nên giới hạn/paginate. |
| `Page<Customer>` | Cần phân trang và tổng số. | Có thể thêm query count. |
| `long` với `countBy...` | Chỉ cần biết số lượng. | Giảm nhu cầu tải entity. |
| `boolean` với `existsBy...` | Chỉ cần kiểm tra có ít nhất một document. | Không bảo đảm uniqueness. |
| `Optional<Customer>` | Nghiệp vụ bảo đảm 0 hoặc 1 document. | Nhiều kết quả có thể gây lỗi. |

**Đặc biệt với dữ liệu thiếu:** Nếu nhiều document không có `address_info` hoặc `city_name`, chúng không trở thành một kết quả “thành phố rỗng” trừ khi SQL++ được thiết kế để xử lý như vậy. Nếu màn hình yêu cầu tìm “khách hàng chưa cập nhật địa chỉ”, nên viết bộ lọc dành riêng cho trạng thái thiếu địa chỉ, thay vì truyền chuỗi rỗng vào `findByAddress_City("")` và hy vọng nó khớp.

## 13. Consistency, TTL, CAS, giao dịch và reactive

### 13.1. Vì sao vừa cập nhật địa chỉ mà `findByAddress_City` chưa thấy?

Trong Couchbase, đường key-value và SQL++ index có thể cập nhật theo nhịp khác nhau:

```text
save(customer)                   -> ghi document thành công
findById(customer.id)            -> truy cập theo ID bằng key-value
findByAddress_City("HANOI")      -> truy vấn SQL++ qua index
```

Truy vấn theo field lồng nhau có thể chưa thấy ngay thay đổi nếu index chưa phản ánh lần ghi. Nếu ứng dụng bắt buộc đọc lại ngay theo `address.city`, cần xem xét mức query scan consistency phù hợp (ví dụ tương đương `REQUEST_PLUS` khi API/phiên bản hỗ trợ) hoặc dùng document ID. Mức nhất quán cao hơn có thể tăng độ trễ truy vấn.

### 13.2. TTL, CAS và transaction

- **TTL:** Document hết hạn có thể biến mất khỏi mọi truy vấn, dù đường dẫn property và giá trị thành phố không thay đổi.
- **CAS/optimistic locking:** Đọc document từ `findByAddress_City` không khóa dữ liệu trước một lần `save` tiếp theo; khi nhiều tiến trình sửa địa chỉ, cần xử lý xung đột ghi theo cơ chế phù hợp.
- **Giao dịch:** `findBy...` rồi `save(...)` không tự tạo một giao dịch nguyên tử. Nếu nghiệp vụ yêu cầu đổi đồng bộ địa chỉ ở nhiều document, cần đánh giá transaction và giới hạn hỗ trợ của SDK/Spring Data Couchbase.

### 13.3. Dùng repository reactive

Cùng đường dẫn property có thể diễn đạt trong repository reactive, còn cách tiêu thụ kết quả đổi sang Reactor:

```java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Flux<Customer> findByAddress_City(String city);

    Flux<Customer> findByStatusAndAddress_City(
        String status, String city
    );

    Mono<Customer> findById(String id);
}
```

`Flux<Customer>` cho nhiều kết quả; `Mono<Customer>` cho tối đa một. API reactive không làm mất nhu cầu index, không tự sửa mapping hay vấn đề `NULL`/`MISSING`. Khi dùng reactive end-to-end, tránh gọi `block()` trên luồng xử lý web để lấy kết quả đồng bộ nếu không có thiết kế phù hợp.

## 14. Bài tập thực hành với tập dữ liệu nhỏ

Xét sáu document:

| ID | `status` | `address_info.city_name` | `address_city` | `address_info.district_name` |
| --- | --- | --- | --- | --- |
| `c01` | ACTIVE | HANOI | HCM | CAU_GIAY |
| `c02` | ACTIVE | HCM | HANOI | DISTRICT_1 |
| `c03` | SUSPENDED | HANOI | HANOI | BA_DINH |
| `c04` | ACTIVE | `NULL` | DANANG | — |
| `c05` | ACTIVE | `MISSING` | HANOI | — |
| `c06` | ACTIVE | Hanoi | HCM | LONG_BIEN |

Ở `c04`, `address_info.city_name` có thể tồn tại nhưng được lưu `null`; ở `c05`, field đó không có hoặc object cha bị thiếu. Ký hiệu “—” trong bảng nghĩa là không cung cấp giá trị cho ví dụ, không suy ra cách JSON đã được ghi.

**Bài A — Tìm theo thành phố trong object địa chỉ.**

```java
List<Customer> findByAddress_City(String city);
```

Gọi `findByAddress_City("HANOI")` → tập ID dự kiến `{c01, c03}`.

**Bài B — Tìm theo thành phố cấp gốc.**

```java
List<Customer> findByAddressCity(String city);
```

Gọi `findByAddressCity("HANOI")` → tập ID dự kiến `{c02, c03, c05}`. Hai tập kết quả khác nhau dù tên property nhìn gần giống.

**Bài C — Kết hợp status và thuộc tính lồng nhau.**

```java
List<Customer> findByStatusAndAddress_City(
    String status, String city
);
```

Gọi `findByStatusAndAddress_City("ACTIVE", "HANOI")` → chỉ có `{c01}`.

**Bài D — Tra cứu một nhóm thành phố.**

```java
List<Customer> findByAddress_CityIn(
    java.util.Collection<String> cities
);
```

Gọi `findByAddress_CityIn(List.of("HANOI", "HCM"))` → tập ID `{c01, c02, c03}`. Nếu muốn bao gồm `Hanoi` với chữ thường khác, phải xác định thêm quy tắc tìm kiếm không phân biệt hoa thường; không mặc định `In` sẽ làm vậy.

**Bài E — Kiểm tra `NULL` và `MISSING`.**

Thử hai câu SQL++ riêng để biết document nào có giá trị null và đường dẫn nào bị thiếu. Nếu cần phân biệt **object cha thiếu** với **field con thiếu**, bổ sung điều kiện kiểm tra riêng từng cấp.

### 14.1. Bảng kiểm trước khi sử dụng trong sản phẩm

| Câu hỏi | Vì sao cần kiểm tra |
| --- | --- |
| Tên trong method có phải property Java không? | Spring Data parser đọc property, không trực tiếp đọc tên field JSON. |
| Đường dẫn nào đang được chọn: `addressCity` hay `address.city`? | Property phẳng và nested có thể mang dữ liệu khác nhau. |
| Có cần `_` để tách property tường minh không? | Tránh parser ưu tiên property khác do trùng tên. |
| `@Field` ở mỗi tầng đã trỏ đúng JSON chưa? | Alias JSON quyết định SQL++/index cần dùng. |
| Trường đích là object hay array? | Array cần ngữ nghĩa phần tử và có thể cần `ANY`. |
| Object cha/con có thể `NULL` hoặc `MISSING` không? | Bộ lọc equality không đồng nghĩa “chưa có địa chỉ”. |
| Index có trên đúng JSON path không? | Index cho field phẳng không tự phục vụ nested field. |
| Có yêu cầu phân trang và sắp xếp ổn định không? | Tránh tải tập quá lớn hoặc kết quả không xác định thứ tự. |
| Có cần nhìn thấy bản ghi ngay sau `save` không? | SQL++ phụ thuộc độ mới của index theo scan consistency. |

## 15. Khi nào nên dùng `@Query` hoặc `CouchbaseTemplate`?

Derived query đủ rõ khi điều kiện chỉ đi qua một vài property đơn hoặc nested đã được mapping. Nhưng nên chuyển sang SQL++ tường minh nếu:

- Cần điều kiện trên **cùng một phần tử trong mảng object** (ví dụ `ANY ... SATISFIES`).
- Cần kiểm tra riêng `NULL`/`MISSING` của object cha và field con.
- Có nhiều tổ hợp `And`/`Or`, ngoặc logic hoặc filter tùy chọn.
- Cần hàm SQL++, projection đặc biệt, phân tích index, `JOIN`, `UNNEST` hoặc aggregate.
- Phiên bản Spring Data Couchbase không hỗ trợ nested path/keyword mong muốn một cách rõ ràng.
- Cấu trúc JSON rất sâu hoặc biến đổi động khiến tên phương thức trở nên khó bảo trì.

`@Query` thích hợp khi câu SQL++ cố định nhưng cần toàn quyền diễn đạt điều kiện. `CouchbaseTemplate` hữu ích khi tầng service phải dựng bộ lọc theo nhiều tùy chọn runtime. Với cả hai, phải dùng binding tham số và cấu trúc projection đúng quy ước của Spring Data Couchbase. Không sao chép nguyên JPQL của JPA sang truy vấn Couchbase.

## 16. Ghi nhớ

**Tên phương thức derived query dựa trên property Java; SQL++ và index dựa trên đường dẫn JSON thực tế.** `@Field` là cầu nối hai phía. Khi entity vừa có `addressCity` vừa có `address.city`, dùng `Address_City` để chỉ rõ đường dẫn lồng nhau và tránh lỗi parser trỏ tới property phẳng.

Object lồng nhau và mảng object yêu cầu cách truy vấn khác nhau; `NULL`/`MISSING` cũng cần được xử lý theo nghiệp vụ. Một implementation đáng tin cậy kết hợp **document mapping**, **repository**, **SQL++**, **index**, **phân trang** và **consistency**, đồng thời kiểm thử bằng các document có giá trị phẳng/lồng nhau khác nhau. Khi logic vượt khỏi phạm vi một vài property path rõ ràng, dùng `@Query` hoặc `CouchbaseTemplate` để giữ truy vấn minh bạch, dễ tối ưu và dễ vận hành.
