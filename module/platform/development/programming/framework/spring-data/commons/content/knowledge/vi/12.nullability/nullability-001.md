# Phân biệt không có kết quả, giá trị null và collection rỗng

## 1. Ba trạng thái trả lời những câu hỏi khác nhau

Khi truy vấn dữ liệu, “không thấy giá trị” có thể mang nhiều ý nghĩa. Không có khách hàng với định danh được yêu cầu khác với có khách hàng nhưng chưa có số điện thoại. Một danh sách khách hàng không có phần tử lại khác với một danh sách số điện thoại chứa một phần tử `null`.

Nếu gom tất cả thành một giá trị mặc định, chương trình có thể hiển thị sai, bỏ qua lỗi hoặc đưa ra quyết định nghiệp vụ không đúng. Nullability cần bắt đầu từ việc xác định rõ truy vấn đang tìm entity, một giá trị scalar hay một tập kết quả.

Trong Spring Data Commons, kiểu kết quả repository giúp diễn đạt hợp đồng chung:

- `Optional<T>` diễn đạt có hoặc không có một giá trị đơn.
- Một kiểu `T` trực tiếp cần được đọc cùng hợp đồng cho phép hoặc không cho phép `null`.
- `List<T>`, `Collection<T>` và các nguồn kết quả nhiều phần tử được hỗ trợ dùng kết quả rỗng để biểu đạt không có phần tử phù hợp.

Hợp đồng container không thay thế ngữ nghĩa dữ liệu bên trong. Một `Optional` có giá trị vẫn có thể chứa một đối tượng mà thuộc tính của nó là `null`. Một `List` không `null` cũng không bảo đảm mọi trường của các phần tử đều có dữ liệu.

Các ví dụ thực thi cụ thể trong bài dùng Spring Data JPA và Jakarta Persistence. Với mô-đun khác, cần đối chiếu hỗ trợ kiểu trả về, mapping, quy tắc giá trị thiếu và cách xử lý tham số của mô-đun đó.

## 2. Tách bốn tầng khi đọc một kết quả

Có thể dùng bốn câu hỏi theo thứ tự:

1. **Truy vấn có thực thi thành công không?** Lỗi kết nối hoặc lỗi cú pháp không phải kết quả rỗng.
2. **Có bản ghi hoặc đối tượng kết quả phù hợp không?** Đây là câu hỏi về sự hiện diện của kết quả.
3. **Thuộc tính được chọn có giá trị không?** Một bản ghi có thể tồn tại trong khi một cột hoặc trường chưa có giá trị.
4. **Kiểu trả về biểu đạt được bao nhiêu trạng thái?** Một kiểu không đủ sức phân biệt các trạng thái cần thiết sẽ làm mất thông tin.

| Trạng thái | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Không có entity phù hợp | Không tồn tại khách hàng id 99 trong phạm vi truy vấn | Không có đối tượng khách hàng để trả |
| Có entity, một thuộc tính `null` | Khách hàng id 2 tồn tại, `phone` chưa có giá trị | Có đối tượng, thiếu một giá trị thuộc tính |
| Collection rỗng | Không có khách hàng ở thành phố được tìm | Có container kết quả nhưng không có phần tử |
| Collection chứa `null` | Query chỉ chọn trường nullable của một bản ghi | Có một hàng kết quả, giá trị scalar của hàng là `null` |
| Giá trị cụ thể | Số lượng phù hợp là 0 | Có kết quả đếm; 0 không phải `null` |
| Lỗi | Không kết nối được kho dữ liệu | Không có kết quả hợp lệ để diễn giải |

“Không có entity” cũng cần gắn với phạm vi truy vấn. Không có kết quả trong một tenant, bộ lọc hoặc phạm vi được phép xem không chứng minh entity không tồn tại ở mọi nơi.

## 3. Mô hình và dữ liệu minh họa

Giả sử ứng dụng quản lý khách hàng với entity sau. Các kiểu trong ví dụ triển khai thuộc package `com.example.customer`, mỗi kiểu `public` đặt trong file riêng.

```java
package com.example.customer;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    private String email;
    private String city;
    private String phone;

    protected Customer() {
    }

    public Customer(Long id, String email, String city, String phone) {
        this.id = id;
        this.email = email;
        this.city = city;
        this.phone = phone;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getCity() {
        return city;
    }

    public String getPhone() {
        return phone;
    }
}
```

Dữ liệu:

| id | email | city | phone |
| --- | --- | --- | --- |
| 1 | an@example.test | Da Nang | `0901000001` |
| 2 | binh@example.test | Da Nang | `null` |
| 3 | chi@example.test | Hue | Chuỗi rỗng `""` |

Không có khách hàng id 99. Giả định schema cho phép `phone` thiếu giá trị và kho dữ liệu trong ví dụ giữ chuỗi rỗng khác `null`. Cần kiểm chứng giả định này với kiểu cột và hệ quản trị thực tế.

Bảng dùng `null` để ký hiệu giá trị thiếu, không phải chuỗi văn bản gồm bốn ký tự `"null"`. Chuỗi `"null"`, chuỗi rỗng và giá trị `null` là những khái niệm khác nhau trong mô hình Java.

Mô hình minh họa chưa bao gồm mọi validation hoặc ràng buộc nghiệp vụ. Chẳng hạn, sản phẩm có thể không chấp nhận số điện thoại rỗng; đó là quy tắc phải được thiết kế, không phải điều tự suy ra từ kiểu `String`.

## 4. Không có entity: Optional và kết quả đơn

### 4.1. Optional biểu đạt sự hiện diện của kết quả

```java
package com.example.customer;

import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface CustomerRepository extends Repository<Customer, Long> {
    Optional<Customer> findById(Long id);

    List<Customer> findByCityOrderByIdAsc(String city);
}
```

Các lời gọi có ý nghĩa:

```java
Optional<Customer> found = repository.findById(1L);
Optional<Customer> missing = repository.findById(99L);
```

- `found` chứa entity khách hàng id 1.
- `missing` là `Optional.empty()`.
- Bản thân container `Optional` theo hợp đồng này không được trả `null`.

Với id 2, kết quả vẫn là một `Optional` có giá trị vì entity tồn tại. Việc `customer.getPhone()` là `null` không làm toàn bộ khách hàng biến mất.

### 4.2. Không dùng Optional để bỏ qua mọi lỗi

`Optional.empty()` diễn đạt sự vắng mặt của một giá trị, không phải một cách báo lỗi kết nối. Nếu truy vấn thất bại, cần giữ đường xử lý exception thích hợp.

Một query trả kết quả đơn cũng không tự chọn ngẫu nhiên một bản ghi khi có nhiều bản ghi phù hợp. Với hợp đồng đơn yêu cầu tối đa một kết quả, nhiều kết quả là vấn đề về cardinality; các repository Spring Data có thể báo `IncorrectResultSizeDataAccessException` theo cơ chế thực thi tương ứng.

Muốn lấy phần tử đầu, phải có hợp đồng giới hạn và thứ tự rõ ràng được mô-đun hỗ trợ. Muốn bảo đảm duy nhất theo nghiệp vụ, cần có quy tắc dữ liệu phù hợp.

### 4.3. Trả trực tiếp T cần đọc cùng nullability

Một phương thức dạng sau không tự cho biết đầy đủ cách xử lý trường hợp không có dữ liệu:

```java
Customer findByEmail(String email);
```

Nếu hợp đồng cho phép kết quả nullable, không có kết quả đơn có thể được biểu đạt bằng `null`. Nếu hợp đồng yêu cầu non-null và có kiểm tra tương ứng, trường hợp không có kết quả phải được xử lý theo hợp đồng đó; trong cơ chế kiểm tra nullability repository của Spring Data, nó có thể được báo bằng `EmptyResultDataAccessException`.

Không nên dựa vào riêng từ `find` hay `get` trong tên để quyết định kết quả có được `null` hay không. Cần xem kiểu trả về, annotation, cấu hình nullability và tài liệu của phiên bản đang sử dụng.

Bài này không cố định một package annotation nullability cho mọi thế hệ Spring. Dự án phải dùng bộ annotation và cơ chế kiểm tra tương thích với nền tảng của mình. Điều cần giữ là sự nhất quán giữa hợp đồng và hành vi thực tế.

## 5. Collection rỗng: không có phần tử phù hợp

Với phương thức:

```java
List<Customer> findByCityOrderByIdAsc(String city);
```

Kết quả minh họa là:

| Đối số | Kết quả |
| --- | --- |
| `"Da Nang"` | Danh sách có khách hàng id 1 và 2 |
| `"Hue"` | Danh sách có khách hàng id 3 |
| `"Unknown City"` | Danh sách rỗng |

Không có khách hàng ở thành phố được tìm không có nghĩa repository nên trả `null` thay cho danh sách. Theo hợp đồng Spring Data cho các kiểu kết quả tập hợp được hỗ trợ, người gọi nhận một kết quả rỗng tương ứng.

```java
List<Customer> customers = repository.findByCityOrderByIdAsc("Unknown City");

if (customers.isEmpty()) {
    showNoCustomers();
}
```

Một fragment tự viết cũng phải tôn trọng hợp đồng đã chọn. Trả `null` ở nhánh không có dữ liệu không trở thành đúng chỉ vì phương thức do ứng dụng triển khai.

### 5.1. Không cần thêm Optional chỉ để diễn đạt danh sách không có phần tử

Nếu câu hỏi chỉ là “những khách hàng nào phù hợp?”, danh sách rỗng đã biểu đạt được trường hợp không có ai. Thêm một tầng `Optional<List<Customer>>` chỉ để báo không tìm thấy thường không bổ sung ý nghĩa hữu ích và còn cần kiểm tra khả năng hỗ trợ kiểu trả về của mô-đun.

Nếu thực sự có một trạng thái riêng như “chưa chạy tìm kiếm”, hãy biểu đạt nó bằng hợp đồng có tên rõ ở tầng ứng dụng. Đừng bắt người gọi đoán sự khác nhau giữa `Optional.empty()` và một list rỗng nếu nghiệp vụ chưa định nghĩa hai trạng thái đó.

### 5.2. Rỗng không có nghĩa không có lỗi ở mọi bước khác

Một query thực thi thành công có thể không tìm thấy phần tử. Ngược lại, nếu mapping thất bại hoặc kho dữ liệu không truy cập được, không được tự chuyển lỗi thành danh sách rỗng rồi hiển thị “không có khách hàng”.

Giữ phân biệt này giúp hệ thống phản hồi đúng và giúp việc theo dõi lỗi không bị che khuất.

## 6. Collection không null vẫn có thể chứa giá trị null

Nếu truy vấn trả entity, mỗi phần tử biểu đạt một entity phù hợp. Nhưng nếu query chỉ chọn một trường nullable, kết quả nhiều phần tử có thể chứa giá trị `null` của trường đó.

Ví dụ JPA:

```java
@Query("select c.phone from Customer c "
     + "where c.city = :city order by c.id")
List<String> findPhoneValuesByCity(@Param("city") String city);
```

Snippet nằm trong một interface repository phù hợp, với import `java.util.List`, `org.springframework.data.jpa.repository.Query` và `org.springframework.data.repository.query.Param`.

Theo dữ liệu minh họa:

| Thành phố | Danh sách giá trị phone |
| --- | --- |
| `Da Nang` | `["0901000001", null]` |
| `Hue` | `[""]` |
| `Unknown City` | `[]` |

Ba kết quả có ý nghĩa khác nhau:

- `[]`: không có hàng phù hợp với query.
- `[null]`: có một hàng phù hợp nhưng giá trị được chọn của hàng đó là `null`.
- `[""]`: có một hàng phù hợp và giá trị là chuỗi rỗng theo giả định kho dữ liệu của ví dụ.

Đừng dùng `list.isEmpty()` để kết luận mọi phần tử đều có dữ liệu. Cũng không nên gọi phương thức trên từng chuỗi mà chưa xem hợp đồng về phần tử nullable.

Nếu người gọi cần biết giá trị thiếu thuộc về khách hàng nào, trả riêng danh sách số điện thoại là hợp đồng thiếu thông tin. Hãy trả DTO hoặc projection có định danh cùng giá trị tương ứng.

Nullability của container và nullability của phần tử là hai tầng độc lập. Annotation nói container không `null` không tự nói mọi phần tử hoặc mọi trường bên trong đều non-null.

## 7. Optional của một scalar có thể làm mất sự khác biệt

### 7.1. Query chỉ chọn một thuộc tính nullable

Thêm phương thức JPA sau vào repository:

```java
@Query("select c.phone from Customer c where c.id = :id")
Optional<String> findPhoneValueById(@Param("id") Long id);
```

Với truy vấn này, có hai đường khác nhau cùng dẫn đến một kết quả `Optional.empty()`:

- Id 99 không có hàng phù hợp.
- Id 2 có hàng phù hợp nhưng giá trị scalar được chọn là `null`.

`Optional<String>` chỉ biểu đạt có hoặc không có một chuỗi. Nó không chứa một trạng thái riêng mang nghĩa “có hàng nhưng chuỗi là null”. Bản thân `Optional` không có trạng thái hợp lệ chứa một giá trị `null` bên trong.

Nếu người gọi chỉ cần biết có số điện thoại hay không, việc gộp hai đường có thể là hợp đồng chấp nhận được. Nếu người gọi phải phân biệt khách hàng không tồn tại với khách hàng chưa có số điện thoại, chữ ký này không đủ thông tin.

### 7.2. Dùng DTO để giữ sự hiện diện của hàng

Có thể trả một đối tượng chứa cả định danh và thuộc tính nullable. Ví dụ dùng record, yêu cầu Java 17 trở lên:

```java
package com.example.customer;

public record CustomerContact(Long id, String phone) {
}
```

Trong hợp đồng này, `phone` được phép `null`. Nếu dự án áp dụng mặc định non-null, cần biểu đạt ngoại lệ nullable bằng bộ annotation tương thích của dự án.

Query JPA:

```java
@Query("select new com.example.customer.CustomerContact(c.id, c.phone) "
     + "from Customer c where c.id = :id")
Optional<CustomerContact> findContactById(@Param("id") Long id);
```

Kết quả giờ giữ được sự khác biệt:

| Đối số | Kết quả |
| --- | --- |
| `1L` | Optional có DTO với id 1, phone `"0901000001"` |
| `2L` | Optional có DTO với id 2, phone `null` |
| `3L` | Optional có DTO với id 3, phone `""` theo giả định của ví dụ |
| `99L` | `Optional.empty()` |

Constructor projection tạo một đối tượng kết quả cho hàng phù hợp ngay cả khi trường `phone` của hàng ấy là `null`. Id giúp giữ rõ sự hiện diện của khách hàng.

Đây là một ví dụ về thiết kế projection theo câu hỏi nghiệp vụ. Không cần nạp toàn bộ entity nếu người gọi chỉ cần hai thuộc tính, nhưng cũng không nên chọn quá ít dữ liệu đến mức mất thông tin cần thiết.

### 7.3. DTO không tự giải thích lý do giá trị thiếu

`phone == null` cho biết chưa có giá trị trong hợp đồng dữ liệu này. Nó không tự nói nguyên nhân là khách hàng chưa cung cấp, hệ thống chưa nhập, dữ liệu bị xóa hay thông tin không được phép hiển thị.

Nếu nghiệp vụ cần phân biệt các nguyên nhân, hãy mô hình hóa trạng thái đó rõ ràng. Không dùng một `null` để ngầm mã hóa nhiều tình huống mà người gọi phải đoán.

## 8. Optional.map cũng có thể gộp hai trạng thái

Ngay cả khi repository trả entity, tầng ứng dụng vẫn có thể vô tình làm mất thông tin:

```java
Optional<String> phone = repository.findById(customerId)
        .map(Customer::getPhone);
```

`Optional.map` trả empty nếu giá trị mà hàm ánh xạ tạo ra là `null`. Vì vậy:

- Không có khách hàng: kết quả empty.
- Có khách hàng nhưng `getPhone()` là `null`: kết quả cũng empty.
- Có khách hàng với phone là chuỗi rỗng: kết quả chứa chuỗi rỗng, không phải empty.

Nếu cần giữ trạng thái hàng, có thể ánh xạ sang một đối tượng luôn được tạo khi có khách hàng:

```java
Optional<CustomerContact> contact = repository.findById(customerId)
        .map(customer -> new CustomerContact(
                customer.getId(), customer.getPhone()));
```

Đây là khác biệt về thông tin được giữ, không phải cách viết ngắn hay dài hơn.

### 8.1. Giá trị mặc định có thể làm mất thêm ý nghĩa

```java
String displayedPhone = repository.findById(customerId)
        .map(Customer::getPhone)
        .orElse("");
```

Đoạn này gộp ít nhất ba trường hợp vào cùng chuỗi rỗng: không có khách hàng, khách hàng có phone `null` và khách hàng có phone vốn là `""`.

Việc gộp có thể phù hợp ở một bước hiển thị cụ thể nếu trạng thái khách hàng đã được xử lý trước đó. Không nên thực hiện sớm rồi để các quyết định nghiệp vụ phía sau dựa vào một giá trị đã mất thông tin.

Tương tự, `orElse(null)` đưa người gọi trở lại hợp đồng nullable; nó không giữ ưu điểm biểu đạt tường minh nếu các tầng sau tiếp tục quên xử lý `null`.

### 8.2. Chọn lỗi nghiệp vụ ở ranh giới phù hợp

Nếu thao tác bắt buộc khách hàng phải tồn tại, service có thể chuyển empty thành lỗi nghiệp vụ:

```java
Customer customer = repository.findById(customerId)
        .orElseThrow(() -> new CustomerNotFoundException(customerId));
```

`CustomerNotFoundException` là kiểu exception do ứng dụng định nghĩa. Chỉ sau khi biết khách hàng tồn tại, service mới xử lý riêng chính sách cho `customer.getPhone()`.

Không nên dùng một exception “không có khách hàng” để báo trường hợp chỉ thiếu số điện thoại. Hai trạng thái có thể cần thông báo, mã lỗi hoặc bước tiếp theo khác nhau.

## 9. Giá trị 0, false và aggregate null

### 9.1. Count và exists trả giá trị có nghĩa

Trong mô-đun hỗ trợ các query method tương ứng:

```java
long countByCity(String city);
boolean existsByCity(String city);
```

Với thành phố không có khách hàng, kết quả là 0 và `false`. Đây là những kết quả hợp lệ của phép đếm và kiểm tra tồn tại, không phải container rỗng hay lỗi nullability.

Không nên chuyển mọi số 0 thành “không có kết quả”. Một tổng tiền bằng 0 hoặc một số lượng bằng 0 có thể là kết quả nghiệp vụ chính xác.

### 9.2. Truy vấn tổng hợp có ngữ nghĩa riêng

Trong truy vấn quan hệ, cần tách số hàng đầu vào khỏi số hàng kết quả của aggregate:

- `COUNT` cho biết số lượng theo biểu thức được đếm; khi không có phần tử phù hợp, giá trị đếm là 0.
- `SUM`, `AVG`, `MIN`, `MAX` có thể trả `null` khi không có giá trị đầu vào phù hợp cho phép tổng hợp.
- Một aggregate không có `GROUP BY` có thể trả một hàng chứa giá trị `null`, dù không có hàng dữ liệu đầu vào thỏa bộ lọc.
- Aggregate theo nhóm có thể không tạo nhóm nào, dẫn đến không có hàng kết quả nhóm.

Đây là khác biệt giữa **không có hàng kết quả** và **có hàng kết quả chứa một giá trị tổng hợp null**. Khi ánh xạ sang `Optional` scalar, hai đường lại có thể được biểu đạt bằng cùng trạng thái empty.

Ví dụ, `COUNT(c)` đếm khách hàng, còn `COUNT(c.phone)` chỉ đếm các giá trị phone không null theo ngữ nghĩa aggregate tương ứng. Với hai khách hàng ở `Da Nang` trong dữ liệu minh họa, các số đếm đó lần lượt là 2 và 1.

Nếu báo cáo cần phân biệt “không có giao dịch” với “có giao dịch nhưng chưa có số tiền”, có thể cần trả cả số hàng, số giá trị có dữ liệu và tổng. Một scalar `Optional<BigDecimal>` không tự phân biệt được mọi trường hợp ấy.

Việc dùng giá trị mặc định như `coalesce` hoặc đổi `null` thành 0 phải là quyết định có chủ đích. Cần biết hợp đồng đã chọn chấp nhận gộp những trạng thái nào.

## 10. Null đầu vào là một câu hỏi khác với null đầu ra

Một phương thức trả `Optional` không có nghĩa mọi tham số đều được phép `null`.

### 10.1. Định danh null không phải định danh không tồn tại

Theo hợp đồng CRUD của Spring Data, `findById` yêu cầu id không null. Với phương thức tương ứng của `CrudRepository`, truyền `null` là đầu vào không hợp lệ và có thể dẫn đến `IllegalArgumentException`, thay vì `Optional.empty()`.

Cần tách:

```java
repository.findById(99L);  // id hợp lệ, có thể không có entity
repository.findById(null); // vi phạm điều kiện đầu vào của hợp đồng CRUD
```

Kiểm tra đầu vào không được gộp vào nhánh “không tìm thấy”. Điều đó giúp người gọi sửa request sai thay vì hiểu nhầm là dữ liệu không tồn tại.

### 10.2. Tham số null không tự có nghĩa bỏ qua bộ lọc

Với Spring Data JPA, một điều kiện bằng trong derived query có thể được chuyển thành kiểm tra `IS NULL` khi tham số là null và hợp đồng cho phép nhận null:

```java
List<Customer> findByPhone(String phone);
```

Vì vậy, không nên gọi `findByPhone(null)` rồi mặc định nó nghĩa là “lấy mọi khách hàng, không lọc theo phone”. Nó có thể là yêu cầu tìm khách hàng có phone null.

Khi chủ đích là tìm giá trị thiếu, một tên tường minh dễ đọc hơn:

```java
List<Customer> findByPhoneIsNull();
```

Hỗ trợ toán tử và cách xử lý tham số cần được đối chiếu với mô-đun thực tế. Nếu hợp đồng tham số không cho phép null, lỗi đầu vào có thể được phát hiện trước khi query chạy.

### 10.3. Query khai báo cần biểu thức đúng

Trong JPQL hoặc SQL, không nên coi điều kiện `c.phone = :phone` khi bind null tự tương đương với `c.phone is null`. So sánh với null có ngữ nghĩa riêng.

Nếu thiết kế tham số null có nghĩa bỏ bộ lọc, query JPA có thể biểu đạt chủ đích bằng một điều kiện như:

```sql
where (:phone is null or c.phone = :phone)
```

Nếu thiết kế null có nghĩa tìm giá trị thiếu, cần dùng điều kiện phù hợp với ý nghĩa đó. Nếu null không được phép, hãy từ chối đầu vào.

| Ý nghĩa muốn có khi tham số không có giá trị | Hợp đồng cần thiết |
| --- | --- |
| Đầu vào sai | Kiểm tra hoặc khai báo non-null phù hợp |
| Bỏ bộ lọc phone | Thiết kế predicate tùy chọn rõ ràng |
| Chỉ tìm phone thiếu giá trị | Điều kiện `IS NULL` hoặc toán tử tương ứng |
| Chưa quyết định có lọc hay không | Mô hình tiêu chí cần biểu đạt thêm trạng thái |

Không có một quy tắc null duy nhất tự động phù hợp cho cả bốn yêu cầu này.

## 11. Nullability ở Java không thay thế ràng buộc dữ liệu

Có thể cần phối hợp nhiều tầng hợp đồng:

| Tầng | Câu hỏi được giải quyết |
| --- | --- |
| Kiểu kết quả repository | Có một hay nhiều kết quả, biểu đạt thiếu kết quả thế nào? |
| Annotation nullability | Tham số, kết quả hoặc phần tử nào được phép null theo công cụ và cơ chế hỗ trợ? |
| Mapping và schema | Trường nào được lưu null, ràng buộc nào thực sự được áp dụng? |
| Validation | Dữ liệu nhận vào có đáp ứng quy tắc định dạng và nghiệp vụ không? |
| Service | Khi không có entity hoặc thiếu thuộc tính, quy trình phải làm gì? |

Một cột `NOT NULL` không bảo đảm truy vấn theo id luôn tìm thấy entity. Ngược lại, kết quả `Optional<Customer>` có giá trị không bảo đảm mọi cột của entity đều `NOT NULL`.

Annotation ở tầng Java cũng không tự sửa dữ liệu cũ hoặc tạo ràng buộc DB đã được triển khai đúng. Các cấu hình sinh schema, migration và trạng thái schema thực tế cần được quản lý riêng.

Tương tự, khai báo kết quả collection không null không có nghĩa runtime sẽ tự kiểm tra đệ quy mọi phần tử và trường con. Mức phân tích tĩnh và kiểm tra runtime phụ thuộc bộ annotation, công cụ và nền tảng được dùng.

Khi thay đổi hợp đồng từ nullable sang non-null, cần xác định nguồn dữ liệu và đường trả kết quả nào phải thay đổi. Chỉ thêm annotation có thể làm một trường hợp trước đây trả null chuyển thành exception mà chưa xử lý được ý nghĩa nghiệp vụ.

## 12. Chuyển ngữ nghĩa sang service và API

### 12.1. Tìm một đối tượng

Với thao tác đọc một khách hàng theo id, tầng ứng dụng có thể chọn báo không tìm thấy nếu `Optional` empty. Nếu khách hàng tồn tại nhưng phone null, vẫn có đối tượng khách hàng hợp lệ để trả, cùng một thuộc tính chưa có giá trị theo hợp đồng.

Ví dụ dữ liệu API cho khách hàng hiện có:

```json
{
  "id": 2,
  "phone": null
}
```

Không nên biến riêng thuộc tính phone null thành kết luận toàn bộ khách hàng không tồn tại.

### 12.2. Tìm một tập đối tượng

Với thao tác liệt kê, không có phần tử phù hợp có thể được biểu đạt bằng mảng rỗng:

```json
[]
```

Đó là kết quả thành công của truy vấn trong phạm vi đã xác định. Nó khác một phản hồi lỗi vì kho dữ liệu không hoạt động.

### 12.3. Giữ phân biệt đến khi có lý do gộp

Một giao diện có thể muốn hiển thị “Chưa có số điện thoại” thay cho thuộc tính null. Việc đó nên diễn ra ở nơi hiểu ngữ cảnh hiển thị, sau khi sự tồn tại của khách hàng đã được xác định.

Cấu hình serialization cũng có thể bỏ các trường null. Nếu người tiêu thụ cần phân biệt trường bị bỏ với trường có giá trị null, hợp đồng API phải quy định rõ và cấu hình phải phù hợp.

Ở đầu vào cập nhật, “không gửi trường phone” cũng có thể khác “gửi phone bằng null”. Đây là câu hỏi của hợp đồng cập nhật, không thể giải quyết chỉ bằng kiểu trả về của repository.

## 13. Những cách xử lý dễ làm sai ngữ nghĩa

### Bắt mọi lỗi rồi trả rỗng

Không biến lỗi query hoặc mất kết nối thành `Optional.empty()` hoặc `List.of()` chỉ để tránh exception. Người dùng và hệ thống giám sát sẽ không phân biệt được không có dữ liệu với truy vấn thất bại.

### Đổi null thành chuỗi rỗng ở mọi tầng

Cách này có thể làm dữ liệu hiển thị dễ hơn trong một trường hợp, nhưng cũng xóa khác biệt giữa thiếu giá trị và một chuỗi đã được cung cấp. Chính sách chuẩn hóa cần nhất quán với validation, lưu trữ và truy vấn.

### Lọc bỏ phần tử null mà không xem lại số lượng

Nếu query scalar trả hai hàng, trong đó một giá trị null, lọc bỏ null sẽ chỉ còn một phần tử. Kết quả mới đếm các giá trị có dữ liệu, không còn đại diện đầy đủ cho số bản ghi phù hợp.

Nếu báo cáo cần tỷ lệ khách hàng thiếu phone, thao tác lọc sớm này có thể làm sai mẫu số hoặc mất định danh cần xử lý.

### Dùng Optional như một hộp chứa null

`Optional.of(null)` không tạo một Optional “có giá trị null”; nó gây lỗi. `Optional.ofNullable(null)` trả empty và vì vậy cũng không giữ trạng thái “có hàng nhưng giá trị null”.

Muốn giữ sự hiện diện của hàng, cần một đối tượng kết quả như DTO đã minh họa, hoặc một mô hình trạng thái được đặt tên rõ.

### Coi null là một lý do nghiệp vụ duy nhất

Một giá trị thiếu không tự giải thích được nguyên nhân thiếu. Khi quy trình cần biết nguyên nhân, hãy bổ sung trạng thái dữ liệu thay vì để nhiều nhánh nghiệp vụ suy diễn khác nhau từ cùng một null.

## 14. Thiết kế và kiểm chứng hợp đồng

Trước khi viết repository method, có thể đi qua các câu hỏi:

1. Kết quả là entity, scalar, projection hay tập hợp?
2. Số phần tử hợp lệ là không, một hay nhiều?
3. Có cần phân biệt không có hàng với có hàng chứa giá trị null không?
4. Container, phần tử và các thuộc tính được phép null ở tầng nào?
5. Tham số null bị cấm, biểu đạt giá trị thiếu hay có nghĩa bỏ bộ lọc?
6. Các giá trị mặc định như 0 hoặc chuỗi rỗng có làm mất trạng thái cần thiết không?
7. Trường hợp không có dữ liệu là bình thường hay là lỗi nghiệp vụ của thao tác?
8. Lỗi hạ tầng được giữ riêng bằng cách nào?

Trong dự án thực tế, các ca kiểm chứng nên phản ánh những câu trả lời đó:

| Ca | Điều cần quan sát |
| --- | --- |
| Id 99 không tồn tại | Entity query trả empty theo hợp đồng |
| Id 2 tồn tại, phone null | Entity hoặc DTO vẫn hiện diện |
| Scalar phone của id 2 | Optional scalar có thể empty; không suy ra thiếu entity |
| Thành phố không có khách hàng | List rỗng, không phải container null |
| Scalar nhiều hàng có trường null | Giữ đúng số hàng và ngữ nghĩa phần tử |
| Phone là chuỗi rỗng | Không tự đồng nhất với null nếu hợp đồng chưa chọn vậy |
| Query đơn có nhiều kết quả | Không âm thầm chọn một dòng ngoài hợp đồng |
| Tham số id null | Bị xử lý như đầu vào không hợp lệ theo hợp đồng CRUD |
| Tham số filter null | Hành vi đúng chính sách đã chọn |
| Count không có dữ liệu | Giá trị 0 có nghĩa, không bị báo thiếu kết quả |
| Aggregate thiếu giá trị | Không bị nhầm với 0 khi cần giữ khác biệt |
| Kho dữ liệu lỗi | Không bị chuyển thành kết quả rỗng |

Mock trả một `Optional` hoặc danh sách định sẵn có thể kiểm chứng logic service. Nó không chứng minh JPA mapping, query aggregate, tham số null hoặc nullability runtime đang hoạt động đúng. Những đặc tính đó cần mức kiểm chứng tích hợp phù hợp với mô-đun và kho dữ liệu.

## 15. Tình huống tự đánh giá

### A. Không có số điện thoại hay không có khách hàng?

Repository dùng `Optional<String>` để lấy phone theo id. Cả id không tồn tại lẫn id có phone null đều cho empty. Service trả cùng một lỗi “khách hàng không tồn tại”.

Xác định thông tin đã bị mất và thiết kế lại kết quả để service phân biệt hai trường hợp. Giải thích vai trò của định danh trong DTO hoặc projection.

### B. List rỗng và list chứa null

Một query scalar trả `[null]`, nhưng người viết cho rằng nó tương đương `[]` vì “không có số điện thoại”. Báo cáo cần đếm số khách hàng phù hợp và tỷ lệ thiếu phone.

Giải thích khác biệt về số hàng và lý do việc thay `[null]` bằng `[]` có thể làm sai báo cáo. Nêu hợp đồng dữ liệu phù hợp hơn nếu cần biết khách hàng nào thiếu giá trị.

### C. Optional.map làm mất trạng thái

Service lấy `findById(id).map(Customer::getPhone).orElse("")` rồi dựa vào chuỗi rỗng để quyết định có tạo khách hàng mới hay không.

Liệt kê các trạng thái đã bị gộp và chỉ ra vì sao quyết định tạo mới không nên dựa trên kết quả ấy.

### D. Null nghĩa là gì trong filter?

Một endpoint nhận `phone = null`. Thành viên thứ nhất hiểu là bỏ lọc, người thứ hai hiểu là chỉ tìm dữ liệu thiếu phone, còn người thứ ba cho rằng đầu vào sai.

Thiết kế hợp đồng tiêu chí đủ rõ cho yêu cầu đã chọn. Phân biệt derived equality, điều kiện `IS NULL` và predicate tùy chọn trong query khai báo.

### E. Tổng bằng 0 và chưa có giá trị để tổng hợp

Một báo cáo đổi mọi kết quả tổng hợp null thành 0. Sau đó người dùng không còn phân biệt được chưa có giao dịch với tổng giao dịch bằng 0.

Xác định thông tin cần trả thêm và nơi hợp lý để quyết định có hiển thị giá trị mặc định hay không.

### F. Thêm non-null để sửa lỗi

Nhóm thêm một hợp đồng non-null vào phương thức trả entity nhưng chưa xử lý trường hợp không có hàng. Lỗi null ở phía gọi được thay bằng exception ở ranh giới repository.

Giải thích điều đã thay đổi và điều chưa được giải quyết. Đề xuất cách lựa chọn giữa Optional, kết quả nullable và lỗi nghiệp vụ phù hợp với thao tác.