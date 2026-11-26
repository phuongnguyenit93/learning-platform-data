# Nullability của phần tử collection hoặc array

## 1. Một container không null chưa đủ để dùng an toàn mọi phần tử

Một repository trả danh sách không null giúp người gọi có thể duyệt mà không phải kiểm tra container trước. Tuy nhiên, điều đó chưa trả lời các câu hỏi sau:

- Danh sách có được chứa phần tử null không?
- Nếu mỗi phần tử là một entity hoặc DTO, thuộc tính nào bên trong được phép null?
- Nếu kết quả là array, mọi ô đã được điền giá trị chưa?
- Annotation được dùng chỉ mô tả kiểu hay còn có cơ chế kiểm tra runtime tương ứng?

Trong Spring Data Commons, hợp đồng kết quả nhiều phần tử được chia sẻ giữa các mô-đun, nhưng mapping và khả năng thực thi thuộc kho dữ liệu cụ thể. Vì vậy, cần tách hợp đồng container khỏi hợp đồng phần tử và kiểm tra cách query tạo ra các phần tử ấy.

Bài học dùng Java làm ngôn ngữ chính. Các ví dụ JPA được ghi rõ phạm vi; ví dụ JSpecify chỉ áp dụng khi dự án đã dùng thư viện annotation và công cụ phân tích tương thích. Không giả định mọi phiên bản Spring Data đang dùng cùng một cơ chế nullability.

## 2. Ba tầng nullability cần phân biệt

Xét biến `customers` có kiểu danh sách khách hàng:

```text
customers                    -> container
customers.get(0)             -> phần tử
customers.get(0).getPhone()  -> thuộc tính của phần tử
```

Có ít nhất ba hợp đồng độc lập:

| Tầng | Câu hỏi | Ví dụ vi phạm hoặc trạng thái thiếu |
| --- | --- | --- |
| Container | Bản thân list hoặc array có được null không? | `customers == null` |
| Phần tử | Mỗi vị trí có được chứa null không? | `customers.get(0) == null` |
| Thuộc tính | Đối tượng có thể thiếu dữ liệu nào? | Có Customer nhưng `getPhone() == null` |

Ví dụ, một list có một khách hàng chưa có số điện thoại khác với list có một phần tử null:

```text
[ Customer(id=2, phone=null) ]

[ null ]
```

Ở dòng đầu, vẫn có đối tượng khách hàng và định danh để xử lý. Ở dòng sau, không có đối tượng tại vị trí đó để gọi phương thức.

Một hợp đồng “list không null, các Customer không null” vẫn có thể cho phép phone null. Ngược lại, ràng buộc phone không null trong schema không tự chứng minh rằng một array do mã ứng dụng tạo không có ô trống.

### 2.1. Rỗng khác chứa null

```java
List<String> noRows = Collections.emptyList();
List<String> oneNullValue = Collections.singletonList(null);
```

Đoạn mã dùng `java.util.List` và `java.util.Collections`:

- `noRows.size()` bằng 0.
- `oneNullValue.size()` bằng 1.
- `oneNullValue.isEmpty()` là false.
- Gọi phương thức trên `oneNullValue.get(0)` sẽ gặp giá trị null.

Ký hiệu `[null]` trong bài mô tả một container có một phần tử null. Không dùng `List.of(null)` để tạo dữ liệu này, vì factory `List.of` từ chối phần tử null.

## 3. Kiểu Java thông thường chưa mô tả đủ hợp đồng nullability

Chỉ nhìn chữ ký chưa gắn quy tắc nullability:

```java
List<Customer> findCustomers();
Customer[] findCustomerArray();
```

Java thông thường không tự cấm phương thức trả null container hoặc chứa null bên trong. Những bảo đảm bổ sung phải đến từ hợp đồng framework, annotation và công cụ tương thích, hoặc kiểm tra do ứng dụng thực hiện.

Điều tương tự áp dụng cho tham số:

```java
void handleCustomers(List<Customer> customers);
```

Cần biết cả hai điều kiện: `customers` có được null không và `customers` có được chứa phần tử null không. Nếu chỉ kiểm tra `customers != null`, vòng lặp sau vẫn có thể lỗi:

```java
for (Customer customer : customers) {
    processEmail(customer.getEmail());
}
```

Có thể lỗi vì `customer` null, hoặc một phương thức xử lý phía sau không chấp nhận email null. Hai nguyên nhân thuộc hai tầng hợp đồng khác nhau.

### 3.1. Khai báo kiểu phần tử không phải kiểm tra runtime tự động

Java generics không tự duyệt list để xác minh mọi giá trị đáp ứng một chính sách nullability. Annotation mô tả phần tử cũng không tự tạo ra một vòng kiểm tra chỉ bằng sự hiện diện của nó.

Không nên suy ra rằng repository proxy sẽ kiểm tra đệ quy mọi phần tử, mọi trường và mọi cấp lồng nhau. Phải xác định cơ chế kiểm tra thực tế của phiên bản, công cụ hoặc adapter đang sử dụng.

## 4. Hai nhóm annotation có phạm vi khác nhau

### 4.1. Annotation ở mức khai báo phương thức hoặc tham số

Các dự án sử dụng cơ chế Spring nullability kiểu khai báo, chẳng hạn `@NonNullApi` cùng các annotation liên quan của thế hệ đó, có thể mô tả mặc định cho tham số và giá trị trả về.

Trong mô hình này, phát biểu “giá trị trả về không null” không tự có nghĩa “mọi phần tử collection, entry trong cấu trúc lồng hoặc ô array đều không null”. Cần xem phạm vi mà chính annotation và phiên bản công cụ hỗ trợ.

Đặc biệt, không thêm một annotation mang tên `Nullable` vào mọi vị trí rồi mặc định cú pháp và ý nghĩa giống nhau giữa các thư viện. Có annotation dành cho declaration, có annotation dành cho type use; vị trí được phép và cách công cụ diễn giải có thể khác.

### 4.2. Annotation type-use biểu đạt phần tử generic

Một cách minh họa tường minh là dùng JSpecify. Ví dụ dưới giả định có dependency JSpecify và công cụ phân tích hiểu `@NullMarked`/`@Nullable`:

```java
import java.util.List;
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
public interface CustomerResultShapes {
    List<Customer> nonNullListWithNonNullElements();

    List<@Nullable Customer> nonNullListWithNullableElements();

    @Nullable List<Customer> nullableListWithNonNullElements();

    @Nullable List<@Nullable Customer> nullableListWithNullableElements();
}
```

Đây là interface minh họa hình dạng kiểu, không phải đề xuất tạo repository query từ các tên phương thức này.

Trong phạm vi null-marked của ví dụ:

| Kiểu | Container | Phần tử |
| --- | --- | --- |
| `List<Customer>` | Không null | Không null |
| `List<@Nullable Customer>` | Không null | Có thể null |
| `@Nullable List<Customer>` | Có thể null | Không null khi container tồn tại |
| `@Nullable List<@Nullable Customer>` | Có thể null | Có thể null |

Các kiểu này không nói gì về nullability của `Customer.phone`; thuộc tính đó có hợp đồng riêng trong lớp Customer.

Ví dụ nhằm giải thích khả năng biểu đạt của type-use annotation. Nó không khẳng định query method của mọi mô-đun có runtime validation tương ứng, cũng không yêu cầu thay bộ annotation đang dùng trong dự án.

### 4.3. Có annotation vẫn cần đường kiểm chứng phù hợp

Cần tách ba cơ chế:

1. Công cụ phân tích tĩnh phát hiện việc dùng một phần tử có thể null mà chưa xử lý.
2. Framework kiểm tra tham số hoặc giá trị trả về ở runtime theo hợp đồng nó hỗ trợ.
3. Ứng dụng hoặc validator được cấu hình kiểm tra nội dung collection tại một ranh giới cụ thể.

Không suy ra cơ chế thứ ba tự tồn tại vì cơ chế thứ nhất đã được khai báo. Cũng không coi việc query chạy thành công là bằng chứng annotation đã được phân tích bởi compiler hoặc IDE.

## 5. Với array, vị trí type-use annotation có ý nghĩa

### 5.1. Phần tử và bản thân array là hai kiểu liên quan

Dưới cùng giả định JSpecify và phạm vi `@NullMarked`, có thể biểu đạt:

```java
import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

@NullMarked
public interface CustomerArrayShapes {
    Customer[] nonNullArrayWithNonNullElements();

    @Nullable Customer[] nonNullArrayWithNullableElements();

    Customer @Nullable [] nullableArrayWithNonNullElements();

    @Nullable Customer @Nullable [] nullableArrayWithNullableElements();
}
```

Bảng đọc cú pháp type-use của ví dụ:

| Kiểu | Array | Phần tử Customer |
| --- | --- | --- |
| `Customer[]` | Không null | Không null |
| `@Nullable Customer[]` | Không null | Có thể null |
| `Customer @Nullable []` | Có thể null | Không null |
| `@Nullable Customer @Nullable []` | Có thể null | Có thể null |

Annotation đặt trước kiểu Customer áp dụng cho kiểu phần tử; annotation đặt ở vị trí trước `[]` áp dụng cho mức array đó.

Không được lấy quy tắc cú pháp này rồi áp dụng máy móc cho một annotation declaration cùng tên từ thư viện khác. Cần kiểm tra đúng import và bộ công cụ. Một annotation xuất hiện trước tên kiểu trả về có thể mang ý nghĩa khác khi nó được thiết kế cho declaration thay vì type use.

Với array nhiều chiều, mỗi cấp array còn là một container riêng. “Array ngoài không null” không tự bảo đảm từng array con hoặc từng phần tử cuối đều có giá trị.

### 5.2. Java khởi tạo array tham chiếu bằng các ô null

```java
Customer[] slots = new Customer[3];
```

Theo ngữ nghĩa Java, array được tạo và có length 3, nhưng cả ba ô ban đầu đều null. Kiểu khai báo thông thường không tự điền Customer vào các ô đó.

Nếu dùng công cụ nullness với hợp đồng phần tử non-null, công cụ có thể phát hiện vấn đề khởi tạo hoặc sử dụng không phù hợp. Annotation không thay đổi cách JVM khởi tạo array.

Cần phân biệt:

```text
null                 : chưa có array
new Customer[0]      : có array rỗng
new Customer[3]      : có array với 3 ô null lúc khởi tạo
array chứa 3 Customer: có array và 3 đối tượng hiện diện
```

Nếu một adapter cấp phát array theo số lượng dự kiến nhưng chỉ điền hai trong ba ô rồi trả toàn bộ array, người gọi có thể nhận một phần tử null dù query chỉ sinh entity hợp lệ.

### 5.3. Array primitive và array wrapper khác nhau

```java
long[] primitiveIds = new long[3];
Long[] boxedIds = new Long[3];
```

- Các phần tử của `primitiveIds` ban đầu là 0; phần tử primitive không thể là null.
- Các phần tử của `boxedIds` ban đầu là null.
- Bản thân mỗi array vẫn là một tham chiếu và có hợp đồng nullability riêng.

Nếu duyệt `Long[]` và tự unbox một ô null thành `long`, chương trình có thể gặp `NullPointerException`. Không nên đổi wrapper thành primitive chỉ để che giá trị thiếu nếu nghiệp vụ cần phân biệt thiếu với giá trị 0.

## 6. Nguồn null trong kết quả repository

### 6.1. Query chọn trường nullable

Giả sử entity JPA `Customer` có `id`, `city`, `phone`; phone được phép thiếu giá trị. Query sau chỉ chọn phone:

```java
@Query("select c.phone from Customer c "
     + "where c.city = :city order by c.id")
List<String> findPhoneValuesByCity(@Param("city") String city);
```

Snippet được đặt trong interface repository phù hợp; dùng `java.util.List`, `org.springframework.data.jpa.repository.Query` và `org.springframework.data.repository.query.Param`. Chữ ký ở đây chưa gắn annotation type-use; nếu dự án có mặc định nullability, phải biểu đạt phần tử nullable cho phù hợp.

Giả sử thành phố có hai khách hàng, một người có phone `"0901000001"`, người còn lại có phone null. Danh sách scalar có thể là:

```text
["0901000001", null]
```

Danh sách có hai phần tử, tương ứng hai hàng phù hợp. Một phần tử null ở đây là dữ liệu được query chọn, không phải dấu hiệu repository không tìm thấy bất kỳ hàng nào.

Nếu không có khách hàng phù hợp, kết quả nhiều phần tử là container rỗng theo hợp đồng được hỗ trợ. Không nên tạo một phần tử null để làm đại diện cho “không có hàng”.

### 6.2. Biểu thức truy vấn hoặc phép join tạo giá trị thiếu

Một biểu thức chọn, aggregate hoặc phía không khớp của outer join có thể tạo ra giá trị null. Ví dụ, aggregate scalar không có giá trị để tổng hợp có thể sinh một hàng chứa null; query theo nhóm lại có thể không tạo hàng nhóm nào.

Khi chọn dữ liệu từ quan hệ tùy chọn, phải xem query đang trả entity gốc, entity ở phía join hay một tuple/DTO. Không khái quát rằng mọi list từ repository đều chứa phần tử null, cũng không khẳng định chúng luôn không thể có null.

### 6.3. Custom implementation hoặc bước chuyển đổi thêm null

Một fragment có thể tự thêm null làm placeholder, một hàm ánh xạ có thể trả null hoặc một array cấp phát dư có thể còn ô trống. Những nguồn này thuộc mã ứng dụng, không phải bảo đảm của query engine.

Khi kết quả yêu cầu phần tử non-null, hãy truy vết cả query, mapping và chuyển đổi container. Chỉ kiểm tra cột DB có `NOT NULL` chưa đủ để loại trừ null được tạo ở các bước sau.

## 7. Chuyển đổi container có thể giữ hoặc tạo phần tử null

### 7.1. Sao chép không có nghĩa làm sạch phần tử

Ví dụ sau tạo một list mới nhưng giữ nguyên null:

```java
List<String> source = Arrays.asList("0901000001", null);
List<String> copy = new ArrayList<>(source);
```

Đoạn mã dùng các kiểu tương ứng trong `java.util`. Hai list có cấu trúc riêng nhưng phần tử thứ hai của cả hai vẫn là null. Đây là sao chép container, không phải validation dữ liệu.

Các thao tác đóng gói hoặc sao chép cũng không tự kiểm tra thuộc tính của entity. Một Customer có phone null vẫn có thể đi qua bước yêu cầu phần tử Customer không null.

### 7.2. ToArray với array quá lớn có ô không thuộc dữ liệu query

```java
List<String> names = Arrays.asList("An", "Binh");

String[] buffer = new String[5];
String[] oversized = names.toArray(buffer);
```

`buffer` đủ lớn nên có thể được dùng làm array kết quả. Với cách khởi tạo trong ví dụ, nội dung là:

```text
["An", "Binh", null, null, null]
```

Collection nguồn chỉ có hai phần tử không null. Array kết quả vẫn có length 5. Theo hợp đồng `toArray(T[])`, khi array đích lớn hơn số phần tử, ô ngay sau phần dữ liệu collection được đặt thành null; các ô còn lại trong ví dụ cũng là null do giá trị khởi tạo của buffer.

Không nên đọc toàn bộ length 5 rồi kết luận repository đã trả năm hàng, trong đó ba hàng bị thiếu. Ba vị trí sau không tương ứng với các bản ghi query.

Nếu muốn một array có kích thước khớp kết quả, có thể dùng:

```java
String[] exact = names.toArray(new String[0]);
```

Trong ví dụ, `exact` có length 2. Tuy nhiên, nếu collection nguồn có phần tử null, phép chuyển đổi này vẫn giữ phần tử null; kích thước chính xác không đồng nghĩa phần tử đã được kiểm tra non-null.

### 7.3. Mở rộng array có thể thêm ô null

```java
String[] original = { "An", "Binh" };
String[] expanded = Arrays.copyOf(original, 4);
```

`expanded` chứa hai giá trị gốc và hai ô null ở cuối. Đây là hành vi cấp phát và sao chép array tham chiếu, không phải thay đổi ngữ nghĩa của hai phần tử nguồn.

Nếu API cần phân biệt buffer capacity và số phần tử hợp lệ, phải truyền thông tin số phần tử rõ ràng hoặc trả một cấu trúc chỉ chứa dữ liệu hợp lệ. Không dùng một array cấp phát dư như thể mọi ô đều là kết quả.

### 7.4. Khả năng chứa null độc lập với khả năng sửa cấu trúc

Các ví dụ tiện ích JDK sau phù hợp với nền tảng Java 17 trở lên của phần minh họa:

| Cách tạo hoặc chuyển đổi | Xử lý phần tử null | Hợp đồng cần nhớ |
| --- | --- | --- |
| `new ArrayList<>(source)` | Giữ null đã có | Tạo container có thể sửa, không làm sạch dữ liệu |
| `Arrays.asList(array)` | Giữ null trong array | List có kích thước cố định, liên hệ với array nguồn |
| `Collections.unmodifiableList(source)` | Không tự loại null đã có | Chặn sửa qua wrapper, không kiểm tra dữ liệu và không tách khỏi source |
| `List.of(...)` | Từ chối phần tử null | Tạo list không cho sửa cấu trúc |
| `List.copyOf(source)` | Từ chối phần tử null | Kết quả không cho sửa cấu trúc, không kiểm tra sâu trường entity |
| `source.toArray(new T[0])` với kiểu cụ thể phù hợp | Giữ null đã có | Hướng tạo array khớp kích thước, không phải validation |
| `Arrays.copyOf(array, largerLength)` trên array tham chiếu | Có thể thêm null ở cuối | Kích thước mới có thể vượt số phần tử dữ liệu ban đầu |

Ký hiệu `T` ở hàng chuyển array mô tả kiểu cụ thể; trong Java không thể trực tiếp viết `new T[0]` với một type parameter thông thường. Ví dụ thực tế phía trên dùng `new String[0]`.

List không sửa được vẫn có thể chứa null nếu cách tạo cho phép. Nó cũng có thể chứa các đối tượng mutable. Đừng đồng nhất tính chỉ đọc của container với non-null hoặc bất biến sâu.

## 8. Dùng DTO để giữ hàng dữ liệu, cho phép thuộc tính nullable

Nếu query scalar có null nhưng người gọi cần biết null thuộc về ai, nên giữ định danh trong kết quả.

Ví dụ DTO dùng Java 17 trở lên:

```java
package com.example.customer;

public record CustomerPhone(Long customerId, String phone) {
}
```

Trong ví dụ này, hợp đồng của `phone` là nullable. Nếu package áp dụng mặc định non-null, cần annotation nullable tương thích ở component đó.

Query JPA có thể khai báo:

```java
@Query("select new com.example.customer.CustomerPhone(c.id, c.phone) "
     + "from Customer c where c.city = :city order by c.id")
List<CustomerPhone> findCustomerPhonesByCity(@Param("city") String city);
```

Kết quả minh họa:

```text
[
  CustomerPhone(customerId=1, phone="0901000001"),
  CustomerPhone(customerId=2, phone=null)
]
```

Hai phần tử DTO hiện diện, mỗi phần tử có định danh. Người gọi có thể xử lý rõ:

```java
for (CustomerPhone row : rows) {
    if (row.phone() == null) {
        showMissingPhone(row.customerId());
    } else {
        showPhone(row.customerId(), row.phone());
    }
}
```

Đoạn duyệt dựa trên hợp đồng phần tử DTO không null; thuộc tính phone có kiểm tra riêng. Nếu một custom implementation trả null thay cho DTO, đó là một vi phạm khác, không phải một cách biểu đạt hợp lệ của phone thiếu giá trị.

Một projection cũng có thể biểu đạt các thuộc tính tùy chọn nếu mô-đun hỗ trợ. Dù chọn DTO hay projection, mục tiêu là giữ đúng đơn vị kết quả và danh tính hàng khi chúng có ý nghĩa với người gọi.

## 9. Không lọc null trước khi xác định hợp đồng

Một cách sửa NPE thường gặp là:

```java
List<Customer> cleaned = results.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

Đoạn mã dùng `java.util.Objects` và `java.util.stream.Collectors`. Nó bỏ các phần tử null. Nó không giải thích vì sao null xuất hiện hoặc chứng minh việc bỏ chúng là đúng.

Cần phân biệt ba tình huống:

1. **Null là dữ liệu hợp lệ của một query scalar.** Lọc bỏ làm giảm số hàng được biểu đạt.
2. **Null là placeholder gắn với một vị trí đầu vào.** Lọc bỏ có thể làm lệch phép ghép theo vị trí.
3. **Null vi phạm hợp đồng phần tử non-null.** Lọc bỏ có thể che lỗi mapping hoặc lỗi custom implementation.

Chỉ nên lọc khi hợp đồng thực sự yêu cầu “chỉ lấy những giá trị có dữ liệu”. Nếu đó là yêu cầu truy vấn, có thể biểu đạt điều kiện thích hợp trong query, chẳng hạn chọn các giá trị phone không null trong JPA.

Nếu cần danh sách khách hàng dù có hay không có phone, hãy giữ DTO với thuộc tính nullable. Không bỏ cả hàng chỉ vì một trường thiếu giá trị.

### 9.1. Số lượng và metadata có thể bị sai

Ví dụ một query trả 20 hàng gồm 2 giá trị scalar null. Lọc sau query chỉ còn 18 giá trị. Kết quả đó không còn có cùng ý nghĩa số lượng với 20 hàng nguồn.

Nếu nội dung trang đã được giới hạn rồi mới lọc, trang có thể thiếu phần tử và tổng đếm không còn cùng đơn vị với nội dung hiển thị. Phải xác định bộ lọc là điều kiện của query, quy tắc trình bày hay bước phát hiện vi phạm hợp đồng.

### 9.2. Không tự gộp null với giá trị mặc định

Đổi mọi phần tử null thành chuỗi rỗng hoặc số 0 giữ nguyên kích thước container nhưng có thể làm mất ngữ nghĩa. Một giá trị 0 hợp lệ khác với một giá trị chưa có dữ liệu.

Nếu API cần trạng thái “thiếu”, có thể dùng DTO hoặc mô hình trạng thái rõ ràng. Không nên chỉ chọn giá trị mặc định vì nó tránh NPE trong một vòng lặp.

## 10. Kiểm tra runtime ở ranh giới cần bảo vệ

Nếu hợp đồng yêu cầu container và mọi phần tử đều không null, ứng dụng có thể kiểm tra tại ranh giới nhận dữ liệu từ một implementation tùy chỉnh hoặc adapter.

Ví dụ helper Java thuần sau không phụ thuộc một bộ annotation nullability:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public final class RequiredElements {
    private RequiredElements() {
    }

    public static <T> List<T> copyOf(Collection<? extends T> source) {
        Objects.requireNonNull(source, "source");

        List<T> copy = new ArrayList<>(source.size());
        int index = 0;
        for (T element : source) {
            if (element == null) {
                throw new IllegalArgumentException(
                        "Phần tử null tại vị trí " + index);
            }
            copy.add(element);
            index++;
        }
        return Collections.unmodifiableList(copy);
    }
}
```

Hàm này:

- Từ chối container null.
- Từ chối phần tử null với thông tin vị trí trong lượt duyệt.
- Chấp nhận collection rỗng.
- Tạo container kết quả không cho sửa cấu trúc qua list trả về.
- Giữ các tham chiếu đối tượng, không kiểm tra hoặc sao chép sâu trường của chúng.

Giả định nguồn không bị sửa đồng thời khi sao chép. Với collection không có thứ tự nghiệp vụ, vị trí trong thông báo chỉ phục vụ chẩn đoán lượt duyệt đó.

Nếu chỉ cần từ chối null và nền tảng đã hỗ trợ, `List.copyOf` có thể đáp ứng nhiều trường hợp mà không cần helper riêng. Helper minh họa việc kiểm tra phần tử là một hành vi cụ thể, tách khỏi việc khai báo annotation.

Không áp dụng bước kiểm tra này vào một query scalar có phần tử null hợp lệ rồi coi đó là lỗi dữ liệu. Trước hết phải chọn đúng hợp đồng. Nếu cần giữ hàng nhưng cấm phần tử null, DTO thường phù hợp hơn scalar nullable.

Đối với array, nguyên tắc tương tự: kiểm tra bản thân tham chiếu và từng ô trong vùng dữ liệu hợp lệ. Nếu array cấp phát dư, cần xác định vùng dữ liệu trước; kiểm tra toàn bộ buffer có thể nhầm capacity chưa dùng với phần tử kết quả.

## 11. Collection đầu vào cũng có hợp đồng phần tử

Nullability của phần tử không chỉ xuất hiện ở giá trị trả về. Một phương thức nhận collection phải xác định liệu collection được phép chứa null hay không.

Với các thao tác CRUD của Spring Data như `findAllById` hoặc `saveAll`, hợp đồng không cho phép iterable đầu vào null hoặc chứa phần tử null tương ứng.

Ví dụ vi phạm điều kiện đầu vào:

```java
Iterable<Long> ids = Arrays.asList(1L, null, 3L);
repository.findAllById(ids);
```

Việc biến `ids` không null không làm phần tử null trở thành hợp lệ. Ứng dụng không nên trông chờ repository âm thầm bỏ qua nó.

Tương tự, một entity có phone null khác với một phần tử entity null trong đầu vào `saveAll`:

```text
[ Customer(id=1, phone=null) ] -> phần tử hiện diện; trường có hợp lệ hay không tùy mô hình
[ null ]                     -> thiếu chính entity, vi phạm hợp đồng phần tử
```

### 11.1. Id không tồn tại không tạo placeholder null trong kết quả CRUD

`findAllById` có thể trả ít entity hơn số id yêu cầu khi một số id không tồn tại. Không nên kỳ vọng một ô null tại mỗi vị trí thiếu hoặc thứ tự kết quả luôn trùng đầu vào.

Nếu API ứng dụng cần phản hồi theo từng id, hãy ghép theo định danh rồi biểu đạt riêng trường hợp không tìm thấy. Không thêm null vào kết quả repository rồi quên ghi rõ hợp đồng phần tử nullable ở tầng ứng dụng.

### 11.2. Kiểm tra sớm không thay thế hợp đồng của kho dữ liệu

Validation đầu vào giúp báo lỗi rõ hơn, nhưng không tự chứng minh toàn bộ thao tác ghi là nguyên tử hoặc mọi ràng buộc nghiệp vụ đều thỏa. Transaction, mapping và ràng buộc dữ liệu vẫn có vai trò riêng.

Ngược lại, ràng buộc `NOT NULL` của một cột chỉ nói về giá trị lưu ở cột đó. Nó không xác minh collection Java đầu vào không có phần tử null trước khi mã ứng dụng chạm vào từng phần tử.

## 12. Quy trình thiết kế một kiểu kết quả rõ ràng

Có thể dùng trình tự sau cho mỗi query method hoặc fragment:

1. **Xác định đơn vị kết quả:** entity, giá trị scalar, tuple, DTO hay nhóm tổng hợp.
2. **Chọn ngữ nghĩa khi không có hàng:** dùng container rỗng theo hợp đồng nhiều phần tử; không tự thêm placeholder.
3. **Quy định container nullable hay non-null:** đọc cùng hợp đồng repository và cơ chế annotation của dự án.
4. **Quy định phần tử nullable hay non-null:** tách khỏi nullability của các trường bên trong phần tử.
5. **Kiểm tra nguồn tạo null:** cột nullable, outer join, aggregate, converter, custom implementation hoặc array chưa điền đủ.
6. **Chọn biểu đạt kiểu phù hợp:** dùng type-use khi nền tảng hỗ trợ; không nhầm annotation declaration với annotation phần tử.
7. **Chọn hành vi runtime:** giữ null hợp lệ, trả DTO, từ chối vi phạm hợp đồng hoặc lọc có chủ đích.
8. **Xem lại chuyển đổi container:** sao chép, tạo list không sửa được và chuyển array có thể có chính sách null khác nhau.
9. **Đối chiếu số lượng, thứ tự và phân trang:** việc bỏ phần tử không được làm sai hợp đồng kết quả.
10. **Xác định cách kiểm chứng:** phân tích tĩnh và kiểm chứng runtime phải nhắm đến đúng đặc tính đã cam kết.

Một hợp đồng ngắn có thể được ghi như sau:

> Phương thức trả một list không null. Mỗi phần tử là một DTO không null, có customerId. Thuộc tính phone được phép null. Không có hàng phù hợp thì trả list rỗng. Không thêm phần tử null để đại diện cho khách hàng không có phone.

Mô tả này làm rõ hơn nhiều so với chỉ ghi “phương thức không trả null”.

## 13. Các ca cần kiểm chứng trong dự án thực tế

| Dữ liệu hoặc thao tác | Điều cần bảo vệ |
| --- | --- |
| Container null | Chấp nhận hoặc từ chối đúng hợp đồng container |
| List rỗng | Không bị hiểu là lỗi hoặc một hàng null |
| List có một phần tử null | Không bị nhầm với list rỗng |
| List có DTO nhưng phone null | Giữ định danh và xử lý thuộc tính thiếu riêng |
| Array rỗng | Length 0, không có phần tử để kiểm tra |
| `new Customer[2]` | Nhận diện hai ô null, không coi là hai Customer |
| Chuyển list sang array đích lớn hơn | Không tính các ô dư thành hàng query |
| `Arrays.copyOf` tăng độ dài | Nhận diện null được thêm do mở rộng buffer |
| `List.copyOf` gặp phần tử null | Hiểu vì sao thất bại; không nhầm với lỗi DB |
| Collection đầu vào có id null | Phát hiện vi phạm hợp đồng phần tử |
| Id hợp lệ nhưng không tồn tại | Không suy ra kết quả có placeholder hoặc cùng thứ tự đầu vào |
| Lọc null sau phân trang | Không giữ metadata tổng sai ngữ nghĩa |

Nếu dự án dùng nullness checker, cần có kiểm chứng phù hợp rằng cấu hình thật sự phân tích annotation đã chọn. Việc source có import annotation chưa đủ chứng minh công cụ đang kiểm tra phần tử generic hoặc array.

Nếu cần bảo vệ mapping query, hãy kiểm chứng qua mô-đun kho dữ liệu thật phù hợp. Một mock luôn trả `List.of(customer)` không thể chứng minh query scalar nullable, outer join hoặc custom converter không tạo null.

Bài kiểm chứng nên tập trung vào hợp đồng quan sát được: container rỗng, phần tử hiện diện, giá trị thuộc tính, kích thước và hành vi khi vi phạm. Không cần phụ thuộc vào lớp collection runtime mà một phiên chạy tình cờ trả về.

## 14. Tình huống tự đánh giá

### A. Đã có non-null ở phương thức nhưng vẫn NPE

Một query chọn phone trả list không null. Người gọi duyệt và gọi `phone.trim()` cho từng phần tử, sau đó gặp NPE khi một khách hàng chưa có phone.

Hãy chỉ ra tầng hợp đồng nào chưa được biểu đạt. Đề xuất cách dùng kiểu phần tử nullable hoặc DTO có định danh và quy tắc xử lý tương ứng.

### B. Array có ô null dù DB không có null

Adapter lấy hai Customer hợp lệ, chuyển vào một array mới có length 5 rồi trả toàn bộ array. Người gọi gặp ba phần tử null.

Giải thích nguồn null, phân biệt số phần tử dữ liệu với capacity và nêu cách trả một array có kích thước phù hợp.

### C. List không sửa được vẫn có phần tử null

Một nhóm bọc kết quả bằng `Collections.unmodifiableList` và cho rằng từ đó có thể bỏ mọi kiểm tra phần tử null.

Phân biệt tính chỉ đọc của container, nullability phần tử và nullability trường của đối tượng. Nêu thao tác nào sẽ từ chối null nếu hợp đồng thực sự cấm chúng.

### D. Đổi vị trí annotation trên array

Trong phạm vi JSpecify null-marked, hai chữ ký dùng `@Nullable Customer[]` và `Customer @Nullable []`.

Giải thích khác biệt giữa phần tử nullable và array nullable. Nêu lý do không được sao chép kết luận này sang annotation cùng tên từ một thư viện có target khác.

### E. Lọc null làm sai báo cáo

Query scalar trả 20 hàng, có 2 giá trị null. Tầng service lọc chúng đi nhưng vẫn hiển thị tổng và số dòng như trước.

Xác định đơn vị kết quả đã thay đổi, ảnh hưởng đến metadata và cách thiết kế query hoặc DTO nếu cần giữ đủ hàng.

### F. Null trong danh sách id

Đầu vào `findAllById` có một phần tử null. Người viết cho rằng vì kết quả là iterable nên framework phải bỏ qua các phần tử không hợp lệ.

Phân biệt kiểu container với điều kiện phần tử của hợp đồng CRUD. Đề xuất vị trí kiểm tra và cách xử lý riêng id không tồn tại mà không dùng null placeholder ngầm định.