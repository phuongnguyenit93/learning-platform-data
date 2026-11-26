# PropertyPath và truy cập thuộc tính lồng nhau

Một phương thức như `findByCustomerAddressZipCode(...)` không chứa câu SQL, nhưng vẫn mô tả một đường đi trong mô hình domain. Spring Data phải xác định tên đó nói tới thuộc tính trực tiếp `customerAddressZipCode`, hay chuỗi thuộc tính `customer.address.zipCode`.

`PropertyPath` là abstraction thuộc Spring Data Commons giúp biểu diễn và phân giải đường dẫn thuộc tính dựa trên kiểu Java. Hiểu cơ chế này giúp viết derived query rõ nghĩa, chẩn đoán lỗi tên phương thức và tránh nhầm lẫn giữa cấu trúc domain với cách dữ liệu được lưu ở từng store.

Sau bài học, bạn cần có khả năng:

- Đọc tên phương thức và xác định đường dẫn thuộc tính mà parser sẽ chọn.
- Giải thích quy tắc ưu tiên thuộc tính trực tiếp và cách tách CamelCase.
- Dùng dấu `_` để chỉ rõ ranh giới thuộc tính lồng nhau.
- Phân biệt tên thuộc tính Java, tên cột/trường lưu trữ và chuỗi đường dẫn.
- Nhận ra giới hạn khi đi qua association, collection hoặc map.
- Kiểm tra lỗi đường dẫn mà không suy diễn rằng mọi store có cùng khả năng thực thi.

## 1. PropertyPath nằm ở đâu trong derived query?

Spring Data Commons cung cấp các thành phần hỗ trợ phân tích tên phương thức repository. Có thể hình dung quá trình suy diễn như sau:

```text
findByCustomerAddressZipCodeAndStatus
             ↓
Tách phần chủ đề và điều kiện của phương thức
             ↓
Các phần điều kiện: CustomerAddressZipCode, Status
             ↓
Phân giải PropertyPath dựa trên kiểu domain
             ↓
customer.address.zipCode, status
             ↓
Module của store tạo và thực thi truy vấn tương ứng
```

`PartTree` và các thành phần liên quan nhận diện cấu trúc tên phương thức, các phần điều kiện, toán tử và thứ tự sắp xếp. `PropertyPath` tập trung vào câu hỏi: **đường dẫn thuộc tính này có thể được phân giải trên kiểu Java nào, qua những đoạn nào?**

Đây là hai việc khác nhau:

- `CustomerAddressZipCode` mô tả đường dẫn thuộc tính.
- Hậu tố như `IsNull`, `Containing`, `GreaterThan` mô tả toán tử của điều kiện, nếu module hỗ trợ.

Không truyền nguyên chuỗi `findByCustomerEmail` vào `PropertyPath.from(...)` rồi kỳ vọng nó tự nhận diện toàn bộ cú pháp derived query. API này nhận phần đường dẫn, chẳng hạn `customerEmail` hoặc `customer.email`.

### 1.1. Đường dẫn dựa trên kiểu, không dựa trên dữ liệu hiện tại

Parser làm việc với kiểu domain và thông tin thuộc tính. Nó không cần đọc một bản ghi để biết `customer` có thuộc tính `address` hay không.

Vì vậy:

- Có một đơn hàng đang mang `customer = null` không làm tên đường dẫn trở nên sai.
- Chưa có dữ liệu trong cơ sở dữ liệu không ngăn parser phát hiện một tên thuộc tính sai.
- Đường dẫn hợp lệ trong Java chưa bảo đảm store hỗ trợ thực thi truy vấn đó.
- Thuộc tính Java tồn tại nhưng không thuộc mapping truy vấn của store vẫn có thể gây lỗi ở giai đoạn sau.

## 2. Mô hình domain dùng trong bài

Các lớp dưới đây mô tả cấu trúc kiểu để học cách phân giải đường dẫn. Getter, constructor, annotation định danh và mapping của từng store được lược bỏ; đây chưa phải một ứng dụng persistence hoàn chỉnh.

```java
import java.util.List;

class PurchaseOrder {
    Long id;
    String status;
    Customer customer;
    List<OrderLine> lines;
}

class Customer {
    String email;
    Address address;
}

class Address {
    String city;
    String zipCode;
}

class OrderLine {
    Product product;
    int quantity;
}

class Product {
    String sku;
}
```

Một số đường dẫn hợp lệ trong mô hình:

| Kiểu gốc | Đường dẫn | Kiểu giá trị ở cuối |
|---|---|---|
| `PurchaseOrder` | `status` | `String` |
| `PurchaseOrder` | `customer.email` | `String` |
| `PurchaseOrder` | `customer.address.city` | `String` |
| `PurchaseOrder` | `customer.address.zipCode` | `String` |
| `PurchaseOrder` | `lines.product.sku` | `String`, sau khi đi qua phần tử collection |

Các đường dẫn sau không có trong mô hình:

- `customer.zipCode`: `Customer` không có thuộc tính `zipCode`.
- `customer.address.postalCode`: thuộc tính thực tế là `zipCode`.
- `customer.address.zip.code`: `zipCode` là một thuộc tính, không phải `zip` chứa `code`.
- `lines.sku`: `OrderLine` không có `sku`; phải đi qua `product`.

### 2.1. Thuộc tính Java không phải tên cột

Giả sử store quan hệ lưu mã bưu chính vào cột `zip_code`, hoặc MongoDB lưu vào một trường có tên tùy chỉnh. Derived query vẫn bắt đầu từ tên thuộc tính domain `zipCode`, sau đó module của store áp dụng mapping.

```text
Tên phương thức: CustomerAddressZipCode
                     ↓
Đường dẫn domain: customer.address.zipCode
                     ↓
Mapping của store
                     ↓
Tên bảng/cột, document field hoặc cấu trúc lưu trữ tương ứng
```

Không đổi thành `findByCustomerAddressZip_code` chỉ vì cột có tên `zip_code`. Dấu `_` trong phân giải đường dẫn có vai trò riêng, không phải cú pháp snake_case của cơ sở dữ liệu.

Trong store hỗ trợ persistence theo getter, field hoặc constructor, cách xác định thuộc tính persistent còn phụ thuộc metadata của module. Không hiểu “thuộc tính” đơn giản là mọi field Java đều chắc chắn truy vấn được.

## 3. Quy tắc phân giải CamelCase

### 3.1. Ưu tiên khớp toàn bộ tên thuộc tính

Với một đoạn như `AddressZipCode`, parser trước hết thử tìm thuộc tính tương ứng với toàn bộ đoạn trên kiểu hiện tại, theo quy tắc tên thuộc tính Java.

Nếu có thuộc tính trực tiếp `addressZipCode`, parser ưu tiên thuộc tính đó. Nó không tự chọn `address.zipCode` vì người viết cảm thấy cách này hợp lý hơn.

Đây là nguyên nhân một tên phương thức vẫn hợp lệ nhưng có thể mang ý nghĩa khác sau khi mô hình domain được bổ sung một thuộc tính mới.

### 3.2. Nếu không khớp, thử tách từ phải sang trái

Giả sử kiểu `Person` chỉ có `address`, và kiểu `Address` có `zipCode`. Với đoạn `AddressZipCode`, có thể hình dung các bước:

```text
1. Thử thuộc tính trực tiếp: addressZipCode
   → không có

2. Tách: AddressZip | Code
   → thử thuộc tính addressZip trên Person
   → không có

3. Tách: Address | ZipCode
   → tìm thấy address trên Person
   → tiếp tục phân giải ZipCode trên kiểu Address
   → tìm thấy zipCode
```

Kết quả là `address.zipCode`.

Nguyên tắc là thử phần đầu dài hơn trước khi lùi điểm tách sang trái. Parser không chỉ tách tên thành từng từ đơn rồi ghép tùy ý. Trong ví dụ, `zipCode` vẫn là một thuộc tính duy nhất.

### 3.3. Lặp lại trên kiểu của thuộc tính vừa tìm được

Với `CustomerAddressZipCode` trên `PurchaseOrder`, việc phân giải tiếp tục trên từng kiểu:

```text
PurchaseOrder
  └─ customer : Customer
       └─ address : Address
            └─ zipCode : String
```

Nếu ở một bước không tìm thấy thuộc tính cần thiết trên kiểu đang xét, đường dẫn không hợp lệ. Một thông báo lỗi có thể nhắc tới `String` thay vì `PurchaseOrder` vì parser đã đi vào một nhánh mà kiểu trung gian là `String`.

Quy tắc này dựa trên cấu trúc kiểu, không suy đoán theo ý nghĩa nghiệp vụ của các từ `Customer`, `Address` hoặc `Code`.

## 4. Hai kiểu mơ hồ thường gặp

### 4.1. Thuộc tính trực tiếp trùng với đường dẫn mong muốn

Xét một kiểu khác:

```java
class DeliveryContact {
    String addressZipCode;
    Address address;
}
```

Cả hai đường dẫn sau đều tồn tại:

- `addressZipCode`: một thuộc tính trực tiếp.
- `address.zipCode`: một thuộc tính lồng nhau.

Tên `findByAddressZipCode(...)` ưu tiên thuộc tính trực tiếp `addressZipCode`. Nếu mục tiêu là `address.zipCode`, phải biểu diễn rõ ranh giới:

```java
findByAddress_ZipCode(...)
```

Điều này còn có ý nghĩa khi refactor. Ban đầu chỉ có `address.zipCode`, nên `findByAddressZipCode` được phân giải theo đường dẫn lồng nhau. Sau đó thêm field `addressZipCode` vào kiểu gốc: cùng tên phương thức có thể được phân giải sang thuộc tính trực tiếp mà không có lỗi cú pháp tên.

Một bài kiểm tra chỉ xác nhận repository khởi tạo được sẽ không phát hiện được thay đổi ý nghĩa này.

### 4.2. Nhánh trung gian dài hơn dẫn tới ngõ cụt

Xét kiểu sau, không có thuộc tính trực tiếp `addressZipCode`:

```java
class Recipient {
    String addressZip;
    Address address;
}
```

Với `AddressZipCode`, parser có thể chọn được phần đầu `addressZip` trước `address`. Sau đó nó tìm `code` trên kiểu `String` của `addressZip`, và không tìm thấy.

```text
Recipient
  ├─ addressZip : String
  │     └─ code ?       ← nhánh được chọn dẫn tới lỗi
  │
  └─ address : Address
        └─ zipCode     ← đường dẫn người viết thực sự muốn
```

Không nên dựa vào giả định parser sẽ thử mọi cách tách, rồi chọn cách cuối cùng có nghĩa nhất với nghiệp vụ. Khi một tiền tố đã phân giải được và phần tiếp theo thất bại, đường dẫn có thể bị từ chối ở nhánh đó.

Giải pháp rõ ràng vẫn là `Address_ZipCode`.

| Mô hình trên kiểu gốc | Tên không có ranh giới | Hệ quả | Cách thể hiện đường dẫn lồng nhau |
|---|---|---|---|
| Chỉ có `address` chứa `zipCode` | `AddressZipCode` | Có thể phân giải thành `address.zipCode` | `Address_ZipCode` |
| Có cả `addressZipCode` và `address` | `AddressZipCode` | Chọn thuộc tính trực tiếp | `Address_ZipCode` |
| Có `addressZip` kiểu `String` và `address` | `AddressZipCode` | Có thể lỗi khi tìm `code` trên `String` | `Address_ZipCode` |

## 5. Dùng dấu gạch dưới để chỉ rõ ranh giới

Trong derived query, dấu `_` có thể đánh dấu vị trí chuyển sang thuộc tính tiếp theo:

```java
findByCustomer_Address_ZipCode(...)
```

Đường dẫn mong muốn là:

```text
customer.address.zipCode
```

Dấu gạch dưới ở đây là chỉ dẫn cho parser, không có nghĩa các lớp phải chứa field tên `customer_address_zipCode`.

### 5.1. Chọn đúng ranh giới

```java
// Với mô hình cơ bản, cả ba có thể cùng trỏ tới đường dẫn mong muốn:
findByCustomerAddressZipCode(...)
findByCustomer_AddressZipCode(...)
findByCustomer_Address_ZipCode(...)
```

Tuy nhiên, mức độ chỉ rõ ranh giới khác nhau:

- Dạng thứ nhất để parser tự phân giải toàn bộ.
- Dạng thứ hai cố định ranh giới sau `customer`, nhưng vẫn tự phân giải `AddressZipCode` trên kiểu `Customer`.
- Dạng thứ ba chỉ rõ cả hai ranh giới quan trọng.

Nếu `Customer` có thêm `addressZipCode` hoặc `addressZip`, chỉ tách sau `Customer` chưa giải quyết được sự mơ hồ bên trong.

Không tách thành `Customer_Address_Zip_Code` nếu mô hình có thuộc tính `zipCode`. Cách viết đó yêu cầu `Address` có thuộc tính `zip`, rồi kiểu của `zip` có thuộc tính `code`.

### 5.2. Dùng có chủ đích

Không bắt buộc thêm `_` vào mọi phương thức. Với đường dẫn ngắn và rõ, CamelCase thường đủ đọc. Dùng ranh giới tường minh khi:

- Có thuộc tính trực tiếp hoặc tiền tố gây mơ hồ.
- Tên ghép dài khiến người đọc khó thấy cấu trúc domain.
- Muốn ghi rõ ý định ở một đường dẫn dễ bị thay đổi ý nghĩa khi thêm thuộc tính.

Một phương thức vẫn dài và khó hiểu sau khi thêm `_` có thể đang mô tả quá nhiều điều kiện. Khi đó nên cân nhắc cơ chế dựng truy vấn hoặc repository fragment thay vì tiếp tục kéo dài tên.

## 6. Quan sát trực tiếp bằng API PropertyPath

API thuộc Spring Data Commons:

```java
import org.springframework.data.mapping.PropertyPath;

PropertyPath path = PropertyPath.from(
    "customerAddressZipCode",
    PurchaseOrder.class
);

System.out.println(path.toDotPath());
// customer.address.zipCode

System.out.println(path.getSegment());
// customer

System.out.println(path.next().getSegment());
// address
```

Một đường dẫn có nhiều đoạn. Đối tượng đầu tiên biểu diễn đoạn `customer`; gọi `next()` chuyển sang đoạn `address`. Khi viết mã duyệt tổng quát, kiểm tra `hasNext()` trước khi gọi `next()`.

Có thể truyền đường dẫn đã chỉ rõ bằng dấu chấm:

```java
PropertyPath explicit = PropertyPath.from(
    "customer.address.zipCode",
    PurchaseOrder.class
);

System.out.println(explicit.toDotPath());
// customer.address.zipCode
```

Hoặc dùng dấu gạch dưới để xác định ranh giới:

```java
PropertyPath explicitBoundary = PropertyPath.from(
    "customer_address_zipCode",
    PurchaseOrder.class
);

System.out.println(explicitBoundary.toDotPath());
// customer.address.zipCode
```

Trong ví dụ cuối, `zipCode` vẫn là một đoạn. `customer_address_zip_code` lại có ý nghĩa khác vì tạo thêm ranh giới giữa `zip` và `code`.

Các đoạn mã này minh họa việc phân giải kiểu. Chúng không gửi truy vấn tới cơ sở dữ liệu, không xác nhận index và không kiểm chứng khả năng join của store.

### 6.1. Đừng đưa tên cột vào API rồi coi đó là metadata lưu trữ

`PropertyPath.from("zip_code", Address.class)` không phải yêu cầu “tìm thuộc tính được ánh xạ vào cột zip_code”. Theo quy tắc phân cách, nó sẽ cố diễn giải các đoạn `zip` và `code`.

Muốn biết thuộc tính Java được lưu thành cột/trường nào cần metadata mapping của module tương ứng. `PropertyPath` không thay thế cho toàn bộ persistent metadata của từng store.

## 7. Quy ước tên và những trường hợp đặc biệt

### 7.1. CamelCase là lựa chọn mặc định dễ kiểm soát

Với mã ứng dụng mới, các tên như `customer`, `zipCode`, `orderNumber` giúp derived query dễ đọc. Tránh dùng snake_case làm tên thuộc tính Java chỉ để khớp tên cột. Đặt mapping lưu trữ ở nơi dành cho mapping.

Dấu `_` có ý nghĩa với parser, nên không thể giả định nó luôn được hiểu là ký tự bình thường giữa một tên thuộc tính.

### 7.2. Thuộc tính bắt đầu bằng dấu gạch dưới

Một thuộc tính có thể thực sự mang tên `_name`. Khi cần tham chiếu tới nó, phải giữ dấu `_` thuộc tên.

Với đường dẫn từ `user` tới `_name`, dạng `user__name` thể hiện ranh giới và dấu gạch dưới đầu tên:

```text
user__name
    ↓
user._name
```

Đây là trường hợp đặc biệt cần phân biệt với `user_name`, vốn biểu diễn `user.name`. Nó không phải quy tắc escape tổng quát để đặt tùy ý dấu gạch dưới trong mọi tên thuộc tính.

### 7.3. Thuộc tính toàn chữ hoa

Một thuộc tính thực sự có tên `USER` có thể được tham chiếu bằng chính tên đó. Đường dẫn `USER_name` có thể thể hiện `USER.name` nếu kiểu của `USER` có thuộc tính `name`.

Đừng tùy ý đổi chữ hoa thành chữ thường: `USER` và `user` có thể là hai thuộc tính khác nhau.

### 7.4. Thuộc tính có chữ thứ hai viết hoa

Xét mô hình:

```java
class CodeHolder {
    String qCode;
    CodeValue q;
}

class CodeValue {
    String code;
}
```

Đoạn tên `QCode` có thể phân giải tới thuộc tính trực tiếp `qCode`. Nó không bắt buộc có nghĩa là `q.code`.

Muốn chọn đường dẫn lồng nhau, dùng `Q_Code`.

| Phần tên | Ý định phân giải |
|---|---|
| `QCode` | Thuộc tính trực tiếp `qCode` khi tồn tại |
| `Q_Code` | `q.code` |
| `USER_name` | `USER.name` với thuộc tính gốc tên `USER` |
| `user__name` | `user._name` |
| `user_name` | `user.name` |

Các trường hợp tên đặc biệt cần được xem trên đúng mô hình và phiên bản của dự án. Không áp dụng một phép đổi chữ cơ học thay cho quy tắc phân giải thuộc tính.

## 8. Viết phương thức repository với đường dẫn lồng nhau

Các phương thức dưới đây minh họa tên và thứ tự tham số. Việc tạo repository thực tế cần một module store hỗ trợ những toán tử và đường dẫn được dùng, cùng mapping đầy đủ.

```java
import java.util.List;

import org.springframework.data.repository.Repository;

interface OrderLookupRepository
        extends Repository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByCustomer_Email(String email);

    List<PurchaseOrder> findByCustomer_Address_ZipCodeAndStatus(
        String zipCode,
        String status
    );

    List<PurchaseOrder> findByCustomer_Address_ZipCodeStartingWith(
        String prefix
    );

    boolean existsByCustomer_Email(String email);
}
```

Phân tích từng tên:

| Phương thức | Đường dẫn | Toán tử hoặc vai trò |
|---|---|---|
| `findByCustomer_Email` | `customer.email` | Điều kiện bằng |
| `findByCustomer_Address_ZipCodeAndStatus` | `customer.address.zipCode`, `status` | Hai điều kiện nối bằng `And` |
| `findByCustomer_Address_ZipCodeStartingWith` | `customer.address.zipCode` | Toán tử bắt đầu bằng, nếu store hỗ trợ |
| `existsByCustomer_Email` | `customer.email` | Kiểm tra tồn tại |

Dấu `_` chỉ phân cách thuộc tính; nó không tạo thêm tham số phương thức. Tên `Customer_Address_ZipCode` có ba đoạn nhưng điều kiện bằng vẫn chỉ cần một giá trị mã bưu chính.

Thứ tự tham số của phương thức hai điều kiện đi theo các phần điều kiện: `zipCode` trước, `status` sau. Đổi chỗ hai đối số cùng kiểu `String` có thể gây kết quả sai mà không có lỗi biên dịch.

### 8.1. Toán tử và đường dẫn là hai lớp riêng

Với tên:

```java
findByCustomer_Address_ZipCodeIsNull()
```

Phần đường dẫn là `customer.address.zipCode`; `IsNull` là toán tử và không nhận đối số giá trị.

Với:

```java
findByCustomerIsNull()
```

Đường dẫn là `customer`, không phải mã bưu chính. Hai phương thức mô tả hai điều kiện khác nhau dù có thể cùng liên quan tới dữ liệu thiếu.

Tương tự, `IgnoreCase` không phải một đoạn thuộc tính. Khả năng áp dụng toán tử chuỗi và cách thực hiện chúng phụ thuộc module, kiểu dữ liệu và cấu hình của store.

### 8.2. Đường dẫn dài không đồng nghĩa truy vấn rõ hơn

Tên sau có thể trở nên khó bảo trì:

```java
findByCustomer_Address_ZipCodeAndCustomer_EmailAndStatus(...)
```

Nếu điều kiện còn nhiều và thay đổi tùy request, hãy cân nhắc API phù hợp của module, chẳng hạn Specification trong JPA, Criteria/Query của MongoDB hoặc repository fragment.

Query by Example cũng không phải lối thay thế mặc định cho mọi đường dẫn và mọi biểu thức logic; cần xem khả năng của store và cách cấu hình matcher. Việc chọn abstraction nên dựa vào use case, thay vì chỉ dựa vào độ dài tên phương thức.

## 9. Đường dẫn trong sắp xếp

### 9.1. Sắp xếp tĩnh trong tên phương thức

Nếu module hỗ trợ, có thể thêm phần `OrderBy`:

```java
List<PurchaseOrder>
findByStatusOrderByCustomer_Address_ZipCodeAscIdAsc(String status);
```

Ý định:

1. Lọc theo `status`.
2. Sắp xếp tăng dần theo `customer.address.zipCode`.
3. Dùng `id` làm thứ tự phụ.

Phần `OrderBy` không tạo thêm đối số cho mã bưu chính. `Customer_Address_ZipCode` trong vị trí này là đường dẫn dùng để sắp xếp, không phải điều kiện so sánh.

Khóa thứ tự phụ hữu ích khi nhiều đơn hàng có cùng mã bưu chính, nhất là khi phân trang. Nó không giải quyết mọi vấn đề về dữ liệu thay đổi giữa các lần đọc.

### 9.2. Sort động dùng đường dẫn chuỗi

Một hợp đồng khác:

```java
import org.springframework.data.domain.Sort;

List<PurchaseOrder> findByStatus(String status, Sort sort);
```

Trong bối cảnh module hỗ trợ đường dẫn domain bằng dấu chấm, chẳng hạn truy vấn phù hợp trong JPA:

```java
Sort sort = Sort.by("customer.address.zipCode")
    .ascending()
    .and(Sort.by("id").ascending());

repository.findByStatus("PAID", sort);
```

Cần phân biệt:

- Trong tên phương thức Java, không thể viết dấu chấm giữa các phần tên; CamelCase hoặc `_` thể hiện ranh giới.
- Trong tham số chuỗi của API hỗ trợ đường dẫn, dấu chấm thường biểu diễn đường đi.
- Việc tạo được đối tượng `Sort` chưa chứng minh thuộc tính tồn tại hoặc store thực thi được cách sắp xếp đó. Kiểm tra có thể diễn ra khi module xử lý truy vấn.
- Không thay tên thuộc tính domain bằng tên cột tùy ý.
- Sắp xếp qua collection có thể cần quy tắc riêng vì một đối tượng gốc có nhiều giá trị con.

Nếu nhận trường sort từ request, nên ánh xạ lựa chọn công khai như `postalCode` sang đường dẫn nội bộ đã cho phép. Điều này giúp API ổn định khi cấu trúc domain thay đổi.

## 10. Đi qua collection: kiểu phần tử và ngữ nghĩa kết quả

Với mô hình:

```text
PurchaseOrder.lines : List<OrderLine>
OrderLine.product   : Product
Product.sku         : String
```

Đường dẫn:

```text
lines.product.sku
```

đi qua kiểu phần tử `OrderLine`, không tìm `product` trên lớp collection `List`.

Một tên phương thức biểu diễn ý định này:

```java
List<PurchaseOrder> findByLines_Product_Sku(String sku);
```

Tuy nhiên, phải kiểm tra module có hỗ trợ truy vấn đó hay không và nó được chuyển thành cơ chế truy cập nào.

### 10.1. Không có cú pháp chung để chọn phần tử thứ n

Không suy ra rằng `Lines0ProductSku` sẽ lấy phần tử đầu tiên, hay `LinesSize` sẽ luôn truy vấn kích thước collection. Các từ hoặc con số đó cần được parser và module hiểu theo một cơ chế được hỗ trợ; chúng không tự trở thành phép truy cập phần tử Java.

### 10.2. Nhiều điều kiện trên collection cần quan tâm quan hệ cùng phần tử

Giả sử một đơn hàng có hai dòng:

| Dòng | SKU | Số lượng |
|---|---|---:|
| 1 | `A` | 1 |
| 2 | `B` | 10 |

Yêu cầu: có một dòng mang SKU `A` và số lượng lớn hơn 5.

Đơn hàng trên không đáp ứng yêu cầu, vì dòng có SKU `A` chỉ có số lượng 1.

Trong MongoDB, một bộ lọc gồm hai điều kiện dotted field độc lập trên mảng có thể được thỏa mãn bởi hai phần tử khác nhau:

```javascript
{
  "lines.product.sku": "A",
  "lines.quantity": { "$gt": 5 }
}
```

Để biểu diễn yêu cầu cùng một phần tử, có thể cần cấu trúc như:

```javascript
{
  "lines": {
    "$elemMatch": {
      "product.sku": "A",
      "quantity": { "$gt": 5 }
    }
  }
}
```

Các ví dụ trên mô tả ngữ nghĩa MongoDB, không phải một quy tắc dịch chung của Commons. Với store quan hệ, cần xem alias, join và điều kiện được tạo; với Elasticsearch, cần phân biệt mapping `object` và `nested` cùng loại query tương ứng.

Tên `findByLines_Product_SkuAndLines_QuantityGreaterThan(...)` tự nó không phải cam kết portable rằng mọi store sẽ ràng buộc hai điều kiện vào đúng cùng một phần tử. Nếu use case cần bảo đảm đó, phải kiểm chứng truy vấn thực tế và dùng cơ chế đặc thù khi cần.

### 10.3. Một đối tượng gốc có thể liên quan tới nhiều dòng kết quả

Khi truy vấn store quan hệ đi qua collection, join có thể tạo nhiều dòng cho cùng một đối tượng gốc. Cần xem cách module xử lý kết quả, đếm và phân trang.

Thêm `Distinct` không nên là phản xạ duy nhất. Phải xác định đang muốn loại trùng đối tượng gốc hay giá trị con, và kiểm tra ý nghĩa của distinct/count trong truy vấn thực tế.

## 11. Null ở thuộc tính trung gian

Một đường dẫn hợp lệ như `customer.address.zipCode` không cho biết mọi bản ghi đều có đủ ba mức dữ liệu.

Có thể gặp:

| Trạng thái dữ liệu | Ý nghĩa |
|---|---|
| Không có `customer` | Thiếu đối tượng/association cấp đầu |
| Có `customer`, không có `address` | Thiếu giá trị trung gian |
| Có `address`, `zipCode = null` | Giá trị cuối là null |
| Có địa chỉ và mã bưu chính | Đủ dữ liệu để so sánh giá trị |

Không giải thích truy vấn như một đoạn Java đơn giản gọi liên tiếp getter rồi ném `NullPointerException`. Module chuyển đường dẫn thành truy vấn của store; join, trường thiếu và null có quy tắc riêng.

Cũng không mặc định `findByCustomer_Address_ZipCodeIsNull()` tương đương mọi trường hợp “thiếu customer, thiếu address hoặc thiếu zipCode”. Phải xem mapping và truy vấn thực tế:

- Store quan hệ còn phụ thuộc cấu trúc join và cách biểu diễn giá trị null.
- MongoDB phân biệt trường không tồn tại và trường tồn tại mang giá trị null trong các toán tử liên quan.
- Trường nằm trong reference bên ngoài không nhất thiết có cùng cách truy cập với dữ liệu nhúng.

Nếu nghiệp vụ cần tách các trường hợp này, hãy mô tả điều kiện tường minh và kiểm chứng từng trường hợp.

## 12. Đường dẫn hợp lệ chưa đủ để store thực thi

| Ngữ cảnh | Điều cần kiểm tra ngoài PropertyPath |
|---|---|
| JPA | Thuộc tính persistent, embedded/association, join, kiểu kết quả và fetch plan |
| MongoDB | Dữ liệu nhúng hay reference, tên trường mapping, điều kiện trên mảng |
| JDBC/R2DBC | Mapping aggregate và khả năng truy vấn của module; không suy ra cơ chế join tự động như JPA |
| Cassandra | Cột/UDT và mô hình khóa; đường dẫn Java không tạo ra join quan hệ |
| Neo4j | Mapping node/relationship và khả năng suy diễn đường dẫn |
| Elasticsearch | Mapping document, `object`/`nested`, loại query và cách sort |

### 12.1. Lọc qua association không có nghĩa là fetch toàn bộ association

Trong JPA, điều kiện đi qua `customer.address.zipCode` không đồng nghĩa repository áp dụng `JOIN FETCH` hoặc luôn khởi tạo toàn bộ graph liên quan. Cách tải association còn phụ thuộc mapping, entity graph và truy vấn được dùng.

Vì vậy, tên phương thức lọc không phải bằng chứng rằng vấn đề N+1 đã được giải quyết.

### 12.2. Reference không tự trở thành join portable

Một document giữ tham chiếu tới document khách hàng không giống việc nhúng toàn bộ khách hàng. Không suy từ đường dẫn Java `customer.address.zipCode` rằng module tự tải document được tham chiếu để lọc như một join SQL.

Tương tự, một lớp Java chứa đối tượng khác không tự bảo đảm có cấu trúc lưu trữ tương ứng hoặc có index thích hợp.

### 12.3. Map không phải không gian tên khóa động dùng chung

Với `Map<String, String> attributes`, không có hợp đồng chung rằng tên `findByAttributesPriority(...)` sẽ hiểu `Priority` là khóa map `"priority"`.

Khóa map tùy dữ liệu khác với thuộc tính được khai báo trên một kiểu Java. Nếu cần truy vấn khóa động, hãy chọn API và cú pháp mà store hỗ trợ, cùng chính sách giới hạn trường được phép truy vấn.

## 13. Chẩn đoán PropertyReferenceException

Khi không phân giải được một đoạn, có thể gặp `PropertyReferenceException` hoặc lỗi tạo truy vấn/repository bọc lấy lỗi này.

Thông tin quan trọng thường gồm:

- Tên thuộc tính chưa tìm được.
- Kiểu Java mà parser đang tìm thuộc tính trên đó.
- Phần đường dẫn đã phân giải trước khi lỗi.
- Phương thức repository liên quan, ở lớp lỗi bao ngoài.

Với ví dụ `Recipient.addressZip` kiểu `String`, thông tin chẩn đoán có thể cho thấy:

```text
Thuộc tính chưa tìm được: code
Kiểu đang được xét: String
Đường dẫn đã đi qua: Recipient.addressZip
```

Không kết luận ngay rằng database thiếu cột `code`. Đây trước hết là lỗi phân giải thuộc tính Java. Cần xem tại sao parser đi vào `addressZip`, rồi thử chỉ rõ ranh giới `Address_ZipCode`.

### 13.1. Trình tự kiểm tra

1. Xác định kiểu domain gốc của repository, kể cả khi interface kế thừa qua generic.
2. Tách phần đường dẫn khỏi `findBy`, toán tử, `And`/`Or` và `OrderBy`.
3. Kiểm tra thuộc tính trực tiếp có trùng với toàn bộ đoạn tên hay không.
4. Kiểm tra các tiền tố dài hơn mà parser có thể chọn.
5. Đi lần lượt qua kiểu của từng thuộc tính; với collection, xét kiểu phần tử.
6. Thử biểu diễn ranh giới bằng `_` hoặc quan sát `PropertyPath.from(...).toDotPath()`.
7. Sau khi đường dẫn đúng, tiếp tục xem mapping và khả năng thực thi của module.

Không sửa tên cột hoặc dữ liệu lưu trữ chỉ để xử lý một lỗi đặt sai tên thuộc tính domain.

### 13.2. Phân biệt các lớp lỗi

| Hiện tượng | Lớp cần xem trước | Ví dụ |
|---|---|---|
| Không tìm được thuộc tính trên một kiểu Java | Phân giải đường dẫn | `postalCode` trong khi lớp chỉ có `zipCode` |
| Tìm `code` trên `String` | Nhánh parser đã chọn | Đi vào `addressZip` thay vì `address` |
| Đường dẫn đúng nhưng module không tạo được query | Mapping và khả năng store | Đi xuyên reference không được hỗ trợ |
| Query chạy nhưng nhiều bản ghi gốc lặp lại | Ngữ nghĩa collection/join | Một đơn hàng có nhiều dòng con khớp |
| Query chạy nhưng thiếu dữ liệu | Mapping và điều kiện | Trường thiếu, null, hoặc kiểu giá trị không khớp |
| Có kết quả nhưng tải quá nhiều truy vấn | Fetch plan và cách sử dụng dữ liệu | Lọc qua association không giải quyết N+1 |

Tùy module và chế độ khởi tạo repository, lỗi có thể xuất hiện lúc bootstrap hoặc khi phương thức được sử dụng. Không lấy thời điểm xuất hiện lỗi làm căn cứ duy nhất để phân loại nguyên nhân.

## 14. Refactor domain mà giữ rõ ý nghĩa truy vấn

Derived query là một hợp đồng gắn với tên và cấu trúc domain. Thay đổi mô hình cần xem lại:

- Phương thức suy diễn đang tham chiếu tới thuộc tính đổi tên.
- Chuỗi đường dẫn trong `Sort`, matcher hoặc các API truy vấn.
- Các tên ghép có thể trở nên mơ hồ khi thêm một thuộc tính mới.
- Mapping và khả năng store sau khi chuyển một giá trị thành embedded object, association hoặc reference.
- Projection và kiểu kết quả có phụ thuộc cấu trúc cũ không.

Ví dụ, đổi `Address.zipCode` thành `Address.postalCode` không tự cập nhật phương thức `findByCustomer_Address_ZipCode`. IDE có thể hỗ trợ một phần, nhưng không nên mặc định mọi chuỗi đường dẫn và mọi tên phương thức đều đã được refactor đúng.

Ngược lại, thêm `PurchaseOrder.customerAddressZipCode` có thể khiến phương thức `findByCustomerAddressZipCode` vẫn hợp lệ nhưng chuyển ý nghĩa. Tên đã chỉ rõ `findByCustomer_Address_ZipCode` giúp giữ ranh giới mong muốn.

Khi kiểm chứng trong một dự án thực tế, cần phân biệt:

- **Kiểm tra phân giải:** đường dẫn được hiểu thành chuỗi thuộc tính nào.
- **Kiểm tra hành vi với store:** dữ liệu nào được chọn, association/collection/null được xử lý ra sao.
- **Kiểm tra yêu cầu truy cập:** thứ tự, phân trang, index và lượng dữ liệu cần tải.

Không cần suy ra cấu trúc truy vấn thực tế chỉ bằng cách nhìn một chuỗi `toDotPath()`.

## 15. Bài tập vận dụng

### Bài tập 1: Xác định đúng các đoạn thuộc tính

Với mô hình cơ bản của bài, hãy phân giải:

```java
findByCustomerAddressZipCode(...)
findByCustomer_Address_ZipCode(...)
findByCustomer_Address_Zip_Code(...)
```

**Gợi ý lời giải:**

- Hai tên đầu có thể phân giải thành `customer.address.zipCode` trong mô hình hiện tại.
- Tên thứ ba yêu cầu `Address.zip.code`, nên không đúng mô hình.
- Dấu gạch dưới không đơn thuần làm tên dễ đọc; nó thay đổi ranh giới parser sử dụng.

### Bài tập 2: Tìm nguyên nhân lỗi trên kiểu String

Cho:

```java
class Recipient {
    String addressZip;
    Address address;
}
```

Tên `findByAddressZipCode(...)` gây lỗi liên quan tới thuộc tính `code` trên `String`. Vì sao và sửa thế nào?

**Gợi ý lời giải:** Parser có thể chọn tiền tố `addressZip` trước `address`, rồi tìm `code` trên kiểu của tiền tố đã chọn. Dùng `findByAddress_ZipCode(...)` để thể hiện rõ `address.zipCode`; không sửa bằng cách thêm một cột `code` vào database.

### Bài tập 3: Refactor không gây lỗi nhưng làm đổi ý nghĩa

Ban đầu `PurchaseOrder` chỉ có `customer.address.zipCode`. Sau đó thêm:

```java
String customerAddressZipCode;
```

Phương thức `findByCustomerAddressZipCode(...)` có chắc tiếp tục lọc trên địa chỉ của khách hàng không?

**Gợi ý lời giải:** Không. Thuộc tính trực tiếp mới có thể được ưu tiên. Nếu ý định là đường dẫn qua khách hàng, dùng `findByCustomer_Address_ZipCode(...)` và kiểm chứng kết quả với dữ liệu mà hai giá trị khác nhau.

### Bài tập 4: Tên cột và tên thuộc tính

Giả sử `Address.zipCode` được ánh xạ tới cột `zip_code`. Nên viết `ZipCode` hay `Zip_Code` trong đường dẫn tên phương thức?

**Gợi ý lời giải:** Dùng `ZipCode` cho thuộc tính Java `zipCode`. `Zip_Code` chỉ đúng khi domain thực sự có `zip` chứa `code`. Mapping lưu trữ xử lý việc chuyển tên thuộc tính thành tên cột.

### Bài tập 5: Xác định điều mà PropertyPath không bảo đảm

Đường dẫn `lines.product.sku` đã phân giải thành công. Có thể kết luận truy vấn sẽ không có dòng trùng, đã dùng index, và mọi store đều hỗ trợ không?

**Gợi ý lời giải:** Không. Phân giải chỉ xác nhận đường đi theo kiểu. Khả năng thực thi, ngữ nghĩa collection, index, distinct và phân trang thuộc module cùng mô hình lưu trữ thực tế.

## 16. Những điều cần ghi nhớ

- `PropertyPath` phân giải đường dẫn thuộc tính dựa trên kiểu domain; nó không phân giải tên cột.
- Parser ưu tiên thuộc tính trực tiếp, rồi thử tách CamelCase từ phải sang trái.
- Tiền tố dài hơn có thể dẫn tới một nhánh sai; không dựa vào giả định parser sẽ thử mọi khả năng.
- Dấu `_` chỉ rõ ranh giới, chẳng hạn `Customer_Address_ZipCode`; không tách `ZipCode` thành `Zip_Code` nếu domain không có cấu trúc đó.
- Collection được xét qua kiểu phần tử, nhưng ngữ nghĩa “cùng phần tử” và loại trùng phải xem theo store.
- Đường dẫn hợp lệ không bảo đảm khả năng join, fetch graph, index hoặc xử lý null giống nhau giữa các module.
- Khi domain thay đổi, hãy xem lại cả tên phương thức và chuỗi đường dẫn để giữ đúng ý định truy vấn.
