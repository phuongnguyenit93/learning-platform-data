# Ràng buộc null của tham số và kiểu trả về

Một lời gọi repository có thể nhận `null`, không tìm thấy bản ghi, trả collection rỗng hoặc trả một đối tượng có property bằng `null`. Đây là những tình huống khác nhau. Nếu gộp chúng thành một khái niệm “không có dữ liệu”, chữ ký method rất dễ trở nên mơ hồ.

Trong chương **Null và nullability** của module `SPRING_DATA_COMMONS`, bài này giải thích cách công bố và sử dụng ràng buộc null ở biên repository: giá trị nào hợp lệ ở đầu vào, kết quả nào hợp lệ ở đầu ra, khi nào dùng `Optional`, và vì sao annotation không tự quyết định ngữ nghĩa query của từng store.

## 1. Nullability là một phần của hợp đồng method

Xét chữ ký Java:

```java
Customer findByEmail(String email);
```

Chỉ nhìn kiểu tham chiếu Java thông thường, chưa thể trả lời chắc chắn:

- Caller có được truyền `null` cho `email` không?
- Nếu không có dữ liệu, method trả `null` hay ném exception?
- Khi có kết quả, bản thân `Customer` có chắc khác `null` không?

Nullability bổ sung những câu trả lời đó. Nó khác với việc query có hợp lệ, dữ liệu có duy nhất hoặc database có cho phép lưu giá trị null hay không.

| Tình huống | Câu hỏi đúng cần đặt |
| --- | --- |
| Đối số `email` bằng `null` | Hợp đồng đầu vào có cho phép không? |
| Query không tìm thấy bản ghi | Hợp đồng đầu ra biểu diễn sự vắng mặt thế nào? |
| Trả `Customer` với `customer.getEmail() == null` | Property email có hợp đồng riêng nào? |
| Query trả `List<Customer>` không có phần tử | Collection rỗng có phải kết quả hợp lệ không? |
| Một phần tử trong collection bằng `null` | Hợp đồng phần tử có cho phép null không? |
| Cột email trong store bằng NULL hoặc bị thiếu | Query và mapping của store diễn giải ra sao? |

Một ràng buộc đặt lên method không tự thay thế tất cả các hợp đồng còn lại.

## 2. Xác định mô hình annotation trước khi đọc ví dụ

Các thế hệ Spring có thể dùng những mô hình annotation null-safety khác nhau. Không nên trộn import chỉ vì annotation đều mang tên `Nullable`.

Bài sử dụng hai phạm vi rõ ràng:

| Phạm vi | Annotation minh họa | Cách dùng trong bài |
| --- | --- | --- |
| Mô hình Spring quen thuộc ở Spring Data 3.x | `org.springframework.lang.NonNullApi`, `Nullable` | Ví dụ repository và runtime validation cụ thể |
| Mô hình JSpecify trong stack có hỗ trợ | `org.jspecify.annotations.NullMarked`, `Nullable` | Phân biệt nullability của reference và phần tử generic |

Những kết luận về runtime validation ở phần ví dụ Spring áp dụng cho cấu hình hỗ trợ mô hình đó. Khi dự án dùng mô hình khác, phải đối chiếu khả năng nhận diện của đúng phiên bản Spring Data, Spring Framework và công cụ phân tích.

Annotation mô tả một hợp đồng; mức độ được kiểm tra còn phụ thuộc công cụ và hạ tầng. Đổi một import từ Spring sang JSpecify không phải bằng chứng rằng mọi hành vi runtime tự động giữ nguyên.

## 3. Đặt mặc định non-null cho package theo mô hình Spring

Với mô hình Spring ở trên, package có thể công bố mặc định non-null bằng nội dung `package-info.java` như sau:

```java
@NonNullApi
package com.example.customer;

import org.springframework.lang.NonNullApi;
```

Đây là đoạn mã minh họa cấu hình, không phải một file bổ sung được tạo cho bài học.

Mặc định này áp dụng cho tham số và giá trị trả về trong phạm vi package mà annotation điều khiển. Một vị trí được đánh dấu `@Nullable` cho phép ngoại lệ tương ứng.

### 3.1. Package con cần được xem riêng

`com.example.customer` và `com.example.customer.query` là các package Java khác nhau. Không mặc định annotation trên package cha tự áp dụng đệ quy cho mọi package con.

Khi repository nằm trong package con, cần kiểm tra mặc định tại đúng package đó theo mô hình annotation được sử dụng.

### 3.2. Non-null mặc định không có nghĩa dữ liệu luôn tồn tại

Một kết quả đơn được công bố non-null diễn đạt rằng method không được hoàn tất bình thường bằng cách trả `null`.

Nếu query không có dữ liệu, hạ tầng có thể phải báo vi phạm hợp đồng thay vì trả `null`. Mặc định non-null không tạo thêm bản ghi, không tạo một entity rỗng và không tự chọn một kết quả khác.

## 4. Một repository với bốn hợp đồng khác nhau

Giả sử domain type `Customer` có các property `id`, `email` và `active`. Với các method trả tối đa một entity theo email, giả định dữ liệu và điều kiện bảo đảm số lượng phù hợp; nullability không thay cho tính duy nhất.

Repository nằm trong package đã có `@NonNullApi`:

```java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.Repository;
import org.springframework.lang.Nullable;

interface CustomerRepository extends Repository<Customer, Long> {

    Customer getByEmail(String email);

    @Nullable
    Customer findNullableByEmail(@Nullable String email);

    Optional<Customer> findOptionalByEmail(String email);

    List<Customer> findByActiveTrue();
}
```

Ví dụ giả định module store hỗ trợ các derived query và kiểu kết quả tương ứng. Các từ mô tả `Nullable` và `Optional` trong subject giúp người đọc phân biệt method; chính annotation, kiểu trả về và cấu hình mới công bố hợp đồng nullability, không phải các từ đó tự trở thành keyword null-safety.

### 4.1. getByEmail: đầu vào bắt buộc, kết quả bắt buộc

```java
Customer getByEmail(String email);
```

Với mặc định package đã bật:

- `email` không được bằng `null`.
- Kết quả method không được bằng `null`.

Trong mô hình runtime validation của Spring Data tương ứng, truyền `null` có thể bị từ chối bằng `IllegalArgumentException`; không tìm được kết quả cho một query đơn bắt buộc có thể dẫn đến `EmptyResultDataAccessException`.

Những exception này biểu đạt hai lỗi khác nhau: đối số không hợp lệ và kết quả vắng mặt không đáp ứng hợp đồng. Không nên bắt chung rồi diễn giải tất cả thành “database không có dữ liệu”.

### 4.2. findNullableByEmail: cho phép null ở hai vị trí độc lập

```java
@Nullable
Customer findNullableByEmail(@Nullable String email);
```

Hai annotation có hai ý nghĩa:

| Vị trí | Ý nghĩa |
| --- | --- |
| Trên method | Giá trị trả về có thể là `null` |
| Trên tham số | Caller được phép truyền `null` cho tham số đó theo hợp đồng nullability |

Nếu chỉ muốn kết quả nullable nhưng tham số vẫn bắt buộc, chỉ đánh dấu vị trí trả về. Nếu chỉ muốn tham số nullable nhưng kết quả bắt buộc, không đánh dấu return là nullable.

Cho phép đầu vào `null` không đồng nghĩa query phải bỏ qua điều kiện email. Ngữ nghĩa điều kiện còn được phân tích ở phần sau.

### 4.3. findOptionalByEmail: wrapper không-null cho kết quả có thể vắng

```java
Optional<Customer> findOptionalByEmail(String email);
```

`email` vẫn bắt buộc. Wrapper `Optional` thể hiện một kết quả có thể có hoặc không:

```text
Có kết quả phù hợp       -> Optional chứa Customer
Không có kết quả         -> Optional.empty()
Đối số email bằng null   -> đầu vào không hợp lệ theo hợp đồng này
```

`Optional.empty()` không phải cách hợp thức hóa một đối số không hợp lệ. Một method trả `Optional` vẫn có thể từ chối `null` ở đầu vào.

### 4.4. findByActiveTrue: rỗng khác null

```java
List<Customer> findByActiveTrue();
```

Theo hợp đồng kết quả collection của Spring Data repository, không có phần tử được biểu diễn bằng collection rỗng, thay vì cần trả `null`.

Caller có thể xử lý danh sách như một collection thông thường mà không thêm một nhánh chỉ để phân biệt “không có danh sách” với “danh sách không có phần tử”. Điều này không tự bảo đảm mọi property của từng entity đều khác `null`.

## 5. Ma trận hành vi ở biên repository

Bảng sau áp dụng cho repository ví dụ với mô hình Spring đã bật runtime validation; giả định query chạy bình thường và không có lỗi số lượng kết quả:

| Lời gọi/tình huống | Hành vi cần mong đợi |
| --- | --- |
| `getByEmail(null)` | Từ chối đối số null theo hợp đồng non-null |
| `getByEmail(email)` nhưng không có bản ghi | Báo kết quả vắng mặt vi phạm hợp đồng non-null |
| `findNullableByEmail(null)` | Qua được ràng buộc null của tham số; query quyết định ngữ nghĩa |
| `findNullableByEmail(email)` nhưng không có bản ghi | Có thể trả `null` |
| `findOptionalByEmail(null)` | Đối số vẫn bị từ chối |
| `findOptionalByEmail(email)` nhưng không có bản ghi | `Optional.empty()` |
| `findByActiveTrue()` nhưng không có bản ghi | Collection rỗng |

Nếu query trả nhiều dòng cho một method chỉ chấp nhận một kết quả, đó là vấn đề cardinality riêng. `@Nullable` và `Optional` không yêu cầu framework tự chọn dòng đầu.

Nếu chưa bật hoặc không được hỗ trợ runtime validation, không suy rằng chỉ có annotation là mọi lời gọi chắc chắn bị chặn tại proxy. Các precondition do implementation tự kiểm tra vẫn là một lớp hợp đồng khác cần giữ nguyên.

## 6. Cho phép null ở tham số không quyết định ý nghĩa truy vấn

Annotation nullable nói rằng giá trị `null` được chấp nhận tại vị trí đó. Nó không tự chọn một trong các ý nghĩa sau:

```text
Tìm bản ghi có email null
Bỏ qua hoàn toàn điều kiện email
Không tìm bản ghi nào
Dùng một giá trị mặc định
```

Cần thiết kế ngữ nghĩa query riêng và công bố rõ cho caller.

### 6.1. Derived query JPA với điều kiện bằng

Ví dụ riêng cho Spring Data JPA, vẫn dùng mô hình annotation Spring:

```java
List<Customer> findByEmail(@Nullable String email);
```

Với một derived query so sánh bằng đơn giản của JPA, truyền `null` có thể được diễn giải thành điều kiện tìm property email là null, thay vì bind như một phép so sánh bằng giá trị thông thường.

Vì vậy, nếu có ba khách hàng chưa có email, query có thể trả ba kết quả. Dùng collection ở ví dụ giúp biểu đạt số lượng đó; đổi thành một kết quả đơn nullable không làm dữ liệu tự trở nên duy nhất.

Đây là quy tắc query của module JPA trong tình huống đã nêu, không phải hệ quả phổ quát của annotation `@Nullable` cho mọi store và mọi toán tử.

### 6.2. Query khai báo bằng dấu bằng không tự đổi thành IS NULL

Ví dụ JPA:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.lang.Nullable;

@Query("select c from Customer c where c.email = :email")
List<Customer> findDeclaredByEmail(
    @Param("email") @Nullable String email
);
```

Method này nằm trong một repository JPA của `Customer`. Với ngữ nghĩa JPQL/SQL thông thường, bind null vào vế so sánh `=` không tương đương điều kiện `IS NULL` để tìm mọi dòng có email null.

Đừng lấy hành vi của derived query làm bằng chứng rằng một query khai báo với `= :email` cũng được viết lại như vậy.

### 6.3. Nếu null nghĩa là bỏ qua bộ lọc, thể hiện điều đó trong query

Một cách biểu đạt tường minh trong JPQL:

```java
@Query("""
    select c from Customer c
    where (:email is null or c.email = :email)
    """)
List<Customer> searchWithOptionalEmail(
    @Param("email") @Nullable String email
);
```

Ở đây, chính biểu thức `:email is null or ...` định nghĩa rằng null làm điều kiện email không còn hạn chế kết quả. Annotation cho phép caller truyền giá trị đó; nó không sinh biểu thức thay caller.

Đây là ví dụ về ngữ nghĩa, không khẳng định một query có nhiều điều kiện tùy chọn bằng `OR` là lựa chọn hiệu năng phù hợp cho mọi dữ liệu. Các API điều kiện động hoặc custom repository fragment có thể phù hợp hơn tùy store và độ phức tạp.

### 6.4. Mỗi loại kho dữ liệu có quy tắc riêng

Một document store có thể phân biệt trường bị thiếu với trường có giá trị null theo những cách khác với cột SQL. Query by Example cũng có quy tắc matcher và xử lý property null riêng trong phạm vi hỗ trợ.

Không suy rằng đánh dấu một tham số nullable sẽ làm mọi store đồng nhất “không có trường”, “trường null” và “bỏ qua tiêu chí”. Những khái niệm đó thuộc hợp đồng query/mapping cần được xác định riêng.

## 7. Precondition của CRUD và tham số điều khiển vẫn phải được giữ

Nullability annotation không xóa những điều kiện đã được API công bố.

### 7.1. findById nhận định danh hợp lệ, không dùng null để biểu diễn vắng mặt

Với `CrudRepository<Customer, Long>`:

```java
repository.findById(101L);  // định danh hợp lệ, có thể không có entity
repository.findById(null); // vi phạm precondition của hợp đồng CRUD
```

`findById` trả `Optional` để biểu diễn không tìm được entity cho một định danh hợp lệ. Nó không nhận null như một cách yêu cầu `Optional.empty()`.

Phương thức CRUD chuẩn công bố định danh không được null và implementation có thể tự kiểm tra điều đó. Không đánh dấu một method khai báo lại là `@Nullable` ở tham số rồi mặc định đã làm `findById(null)` trở thành thao tác hợp lệ.

### 7.2. Một container đầu vào và các phần tử của nó có hợp đồng riêng

Các API như `findAllById` yêu cầu iterable đầu vào không-null và không chứa định danh null. Phân biệt:

```text
Iterable bằng null
Iterable rỗng
Iterable có phần tử null
Iterable chỉ gồm các định danh hợp lệ
```

Đây là bốn trạng thái khác nhau. Một annotation non-null đặt lên tham số container không tự chứng minh mọi phần tử bên trong đều đã được kiểm tra, nhưng precondition cụ thể của API vẫn phải được tuân thủ.

Với một method tự định nghĩa nhận collection, hãy công bố cả việc có chấp nhận tập rỗng và phần tử null hay không. Đừng để caller phải suy luận từ một annotation đặt trên reference của collection.

### 7.3. Dùng giá trị điều khiển thay thế đã được API cung cấp

Đối với các API repository yêu cầu `Pageable` hoặc `Sort` không-null, dùng giá trị thích hợp khi không có yêu cầu phân trang/sắp xếp:

```java
Pageable.unpaged();
Sort.unsorted();
```

Những giá trị này biểu đạt ý định trong hợp đồng Commons. Truyền null không phải cách thay thế chung cho “không phân trang” hoặc “không sắp xếp”, dù một đoạn implementation cụ thể có thể tình cờ chưa chặn nó ngay.

## 8. Null của kết quả, property và scalar cần được tách riêng

### 8.1. Entity không-null vẫn có thể chứa property nullable

Một method trả `Customer` non-null chỉ bảo đảm reference của kết quả theo hợp đồng method. Nó không có nghĩa mọi getter của entity đều trả giá trị không-null.

Ví dụ:

```java
Customer customer = repository.getByEmail("an@example.test");
```

Kết quả `customer` và từng giá trị như `customer.getDisplayName()` cần được xem theo các hợp đồng khác nhau, nếu mô hình có property `displayName`.

Không dùng mặc định non-null của package chứa repository để suy ra nullability của mọi property trong package entity khác.

### 8.2. Projection công bố hợp đồng accessor riêng

Một projection có thể biểu đạt property được phép thiếu:

```java
interface CustomerEmailView {
    Long getId();

    @Nullable
    String getEmail();
}
```

Nếu store và cơ chế projection hỗ trợ wrapper tương ứng, một lựa chọn khác là accessor trả `Optional<String>`.

Điều cần nhớ là: một projection có mặt và một giá trị bên trong projection vắng mặt là hai trạng thái khác nhau. Annotation trên accessor cũng không phải lời bảo đảm rằng hạ tầng runtime sẽ tự quét và kiểm tra sâu tất cả property của mọi đối tượng được trả về.

### 8.3. Scalar nullable không giống count bằng không

Một query count có thể trả số `0` khi không có dữ liệu. Một query aggregate như SUM hoặc MAX có thể trả null khi không có giá trị đầu vào phù hợp, tùy ngữ nghĩa query của store.

Vì vậy, primitive như `long` phù hợp khi query bảo đảm trả một giá trị số hợp lệ; nó không biểu diễn được kết quả null. Với scalar có thể thiếu, cần chọn boxed type, `Optional` hoặc giá trị mặc định được định nghĩa rõ trong nghiệp vụ và query.

Một kết quả `Optional<String>` lấy một property nullable có thể không phân biệt được “không có dòng” với “có dòng nhưng property null”. Nếu cần phân biệt, hãy trả cấu trúc giữ thêm thông tin về dòng, chẳng hạn một DTO chứa định danh cùng property đó.

### 8.4. Đừng trả null thay cho Optional hoặc collection rỗng

Trong code ứng dụng tự viết quanh repository, giữ nguyên hợp đồng đã chọn:

```java
Optional<Customer> lookup(String email) {
    return repository.findOptionalByEmail(email);
}
```

Không thay trường hợp vắng mặt bằng `return null` trong một method công bố trả `Optional`. Tương tự, một adapter hoặc custom fragment cần giữ hợp đồng collection nhất quán thay vì buộc caller xử lý thêm một trạng thái null không được công bố.

Runtime có thể có cơ chế bọc hoặc chuyển đổi kết quả, nhưng đó không phải lý do viết implementation cố ý vi phạm hợp đồng public rồi trông chờ được sửa tự động.

## 9. Nullability của generic và giới hạn kiểm tra sâu

Các annotation Spring theo mô hình khai báo truyền thống cần được phân biệt với annotation type-use của JSpecify. Một ràng buộc trên reference không tự diễn đạt toàn bộ ràng buộc bên trong một kiểu generic.

Trong một phạm vi JSpecify đã đánh dấu `@NullMarked`, có thể phân biệt:

| Kiểu minh họa | Ý nghĩa hợp đồng kiểu |
| --- | --- |
| `List<String>` | List không-null với phần tử String không-null |
| `@Nullable List<String>` | Reference list có thể null; phần tử nếu có vẫn non-null |
| `List<@Nullable String>` | List không-null; phần tử có thể null |

Bảng này minh họa ý nghĩa type-use trong một API Java. Nó không khuyến khích khai báo query repository trả list nullable, vì hợp đồng collection của repository thường dùng collection rỗng.

Ví dụ phạm vi package JSpecify:

```java
@org.jspecify.annotations.NullMarked
package com.example.customer;
```

Nếu dùng `@Nullable` trong ví dụ generic của phần này, import tương ứng là `org.jspecify.annotations.Nullable`, khác với import Spring dùng ở các phần trước.

Các kiểu trong bảng giúp checker hiểu ý định. Chúng không tự sinh một vòng lặp runtime kiểm tra từng phần tử. Runtime validation ở biên method có thể chỉ kiểm tra reference tham số và reference kết quả; mức kiểm tra sâu phải được xác định theo công cụ và implementation thực tế.

Khi chuyển mô hình annotation, cần rà cả mặc định package, import, generic type-use và khả năng hỗ trợ runtime. Không thay annotation theo tên mà bỏ qua thay đổi ý nghĩa.

## 10. Phân biệt các tầng thực thi ràng buộc

| Tầng | Trách nhiệm | Điều không tự bảo đảm |
| --- | --- | --- |
| Công cụ static analysis/IDE | Phát hiện đường đi có thể đưa null vào vị trí không-null | Chặn mọi dữ liệu null xuất hiện ở runtime |
| Runtime validation của repository | Kiểm tra những hợp đồng nullability hạ tầng nhận diện | Kiểm tra sâu mọi property và phần tử |
| Implementation API | Kiểm tra precondition cụ thể, như ID không-null | Tự sinh mọi kiểm tra chỉ từ chữ ký Java |
| Method validation với Bean Validation | Kiểm tra constraint khi được cấu hình và gọi đúng cơ chế | Tự hoạt động ở mọi lời gọi chỉ vì có `@NotNull` |
| Mapping và constraint store thực tế | Bảo vệ tính hợp lệ của dữ liệu được lưu | Kiểm tra mọi tham số tìm kiếm ở biên repository |

`jakarta.validation.constraints.NotNull` và các annotation null-safety như Spring `@Nullable` phục vụ những cơ chế khác nhau. Method validation cần hạ tầng, cấu hình và đường gọi phù hợp; không coi `@NotNull` là một cách viết khác của mặc định package Spring Data.

Tương tự, một metadata mapping như `@Column(nullable = false)` không tự chứng minh database hiện tại đã có đúng constraint, và cũng không thay việc công bố hợp đồng null của tham số repository.

Một API rõ ràng phối hợp các tầng cần thiết, đồng thời không gán cho một annotation trách nhiệm của tất cả các tầng.

## 11. Hợp đồng kế thừa và đường gọi runtime

### 11.1. Khai báo lại method không tự viết lại hợp đồng cơ sở

Khi kế thừa repository hoặc một interface nghiệp vụ, cần giữ nullability tương thích với hợp đồng đã công bố.

Về nguyên tắc thay thế:

- Một implementation không nên bắt caller tuân theo đầu vào chặt hơn hợp đồng cơ sở mà caller được phép dựa vào.
- Một kết quả đã được hứa non-null không nên bị implementation âm thầm nới thành nullable.

Công cụ null-safety có thể cảnh báo những khai báo không tương thích. Mặc định package của interface con không phải giấy phép thay đổi precondition của CRUD hoặc của một interface đã công bố.

Với `findById`, precondition ID không-null vẫn cần được giữ. Với một query tự định nghĩa cho phép email null, hãy giữ ý nghĩa đó nhất quán nếu đưa nó qua nhiều interface và adapter.

### 11.2. Annotation và việc đi qua đúng hạ tầng là hai điều khác nhau

Runtime validation của repository gắn với cách hạ tầng repository xử lý lời gọi. Gọi qua repository proxy được quản lý và gọi trực tiếp một đối tượng implementation tự tạo không phải hai tình huống tương đương.

Tương tự, method validation bằng một cơ chế proxy khác có đường áp dụng riêng. Nếu một kiểm tra được kỳ vọng không chạy, cần kiểm tra cấu hình, đối tượng được gọi và đường gọi, thay vì chỉ nhìn annotation trên source.

### 11.3. Đừng biến lỗi hợp đồng thành một kết quả vắng mặt bình thường

Không nên bắt mọi `IllegalArgumentException` rồi trả `Optional.empty()` cho caller. Cách đó có thể làm một đầu vào không hợp lệ trông giống một truy vấn hợp lệ nhưng không có dữ liệu.

Cũng không nên bắt mọi lỗi query rồi trả collection rỗng. Timeout, lỗi mapping và vi phạm cardinality không phải những cách biểu diễn thay thế của “không có kết quả”.

Hợp đồng null rõ ràng giúp giữ được sự khác nhau giữa các tình huống, thay vì làm tất cả hội tụ về một giá trị rỗng.

## 12. Thiết kế biên service nhất quán với repository

Service thường quyết định việc không có kết quả là một tình huống bình thường hay một lỗi nghiệp vụ.

Ví dụ một đoạn method service:

```java
Customer requireCustomerByEmail(String email) {
    if (email == null) {
        throw new IllegalArgumentException("email phải có giá trị");
    }

    return repository.findOptionalByEmail(email)
        .orElseThrow(() -> new java.util.NoSuchElementException(
            "Không tìm thấy khách hàng theo email"
        ));
}
```

Đoạn này giả định `repository` là dependency của service và có method đã khai báo ở phần trước. Service tách hai quyết định:

```text
Đầu vào null     -> từ chối đầu vào
Đầu vào hợp lệ nhưng không có dữ liệu -> xử lý vắng mặt theo nghiệp vụ
```

Ứng dụng có thể dùng exception nghiệp vụ riêng thay cho `NoSuchElementException`. Điều quan trọng là nơi quyết định và ý nghĩa kết quả phải rõ ràng, không để việc chọn một kiểu trả về ngẫu nhiên quyết định hành vi.

### 12.1. Khi sự vắng mặt là bình thường, giữ wrapper phù hợp

Một chức năng tra cứu có thể công bố trả `Optional<Customer>` hoặc chuyển sang một kết quả ứng dụng khác biểu đạt được không tìm thấy.

Một chức năng danh sách thường dùng collection rỗng. Không thêm `Optional<List<Customer>>` chỉ để biểu diễn lại cùng trạng thái danh sách không có phần tử, nếu nghiệp vụ không có thêm một trạng thái riêng cần phân biệt.

### 12.2. Non-null không đồng nghĩa dữ liệu hợp lệ về nghiệp vụ

Chuỗi `""` và `"   "` khác `null`. Một annotation non-null không tự kiểm tra email đúng định dạng, chuỗi không rỗng hoặc độ dài nằm trong giới hạn.

Nếu yêu cầu đó tồn tại, hãy dùng validation hoặc logic nghiệp vụ thích hợp. Nullability chỉ là một phần của hợp đồng đầu vào, không thay thế tất cả các constraint khác.

Tương tự, một ID không-null chưa chứng minh entity tồn tại; một collection không-null chưa chứng minh nó có phần tử.

## 13. Kotlin và reactive: cách biểu diễn khác, câu hỏi hợp đồng vẫn giữ nguyên

### 13.1. Kotlin thể hiện nullability trong hệ thống kiểu

Ví dụ ý nghĩa kiểu Kotlin:

```kotlin
fun findByEmail(email: String): Customer?
```

Tham số không-null và kết quả nullable là hai lựa chọn độc lập. Đổi tham số thành `String?` mới cho phép null theo hợp đồng Kotlin của vị trí đó.

Compiler Kotlin giúp phát hiện nhiều lỗi ở phía caller Kotlin, nhưng tương tác với Java và nhận diện metadata ở runtime còn phụ thuộc annotation, dependency và phiên bản stack. Ở các cấu hình Spring Data dùng Kotlin reflection để kiểm tra nullability, cần có hỗ trợ reflection tương ứng; không coi hệ thống kiểu của source là bằng chứng rằng mọi đường gọi Java đã được runtime kiểm tra.

### 13.2. Reactive biểu diễn vắng mặt bằng tín hiệu hoàn tất không có phần tử

Trong API dùng Reactor, một query đơn có thể trả `Mono<Customer>`. Không tìm thấy dữ liệu thường được biểu diễn bằng `Mono.empty()` theo hợp đồng query, không phải trả một reference `Mono` bằng null hoặc phát một giá trị null.

Một luồng nhiều phần tử có thể hoàn tất mà không phát phần tử nào. Điều đó khác với tham số repository bằng null và khác với một đối tượng được phát ra có property nullable.

Các wrapper reactive phải được module hỗ trợ; không suy từ ví dụ `Optional` đồng bộ rằng mọi validation và thời điểm phát sinh lỗi đều diễn ra ở cùng một thời điểm trong pipeline reactive.

## 14. Kịch bản thực hành kiểm chứng hợp đồng

Với mô hình Spring của các phần đầu, hãy bố trí repository trong đúng package được đánh dấu và có dữ liệu phân biệt các tình huống:

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Gọi method có tham số non-null bằng null | Bị từ chối theo cơ chế đang được bật |
| Query đơn trả non-null nhưng không có bản ghi | Báo vi phạm kết quả bắt buộc, không tự tạo entity rỗng |
| Query đơn trả nullable nhưng không có bản ghi | Trả null theo hợp đồng |
| Query trả Optional nhưng không có bản ghi | Wrapper rỗng, không phải reference wrapper null |
| Query collection không có bản ghi | Collection rỗng |
| Nullable parameter nhận null trong derived query JPA bằng | Tìm theo ngữ nghĩa null được JPA query creation hỗ trợ |
| Nullable parameter nhận null trong query `= :email` | Không mặc định có hành vi giống derived query |
| Nullable parameter nhận null trong query tùy chọn có `OR` | Hành vi bỏ lọc đến từ biểu thức query đã viết |
| Query đơn gặp nhiều dòng | Lỗi số lượng không bị che bởi `@Nullable` hoặc `Optional` |
| `findById(null)` | Vẫn vi phạm precondition CRUD |
| Kết quả entity non-null có property nullable | Phân biệt ràng buộc reference kết quả với property |

Đây là các kịch bản thiết kế thực hành, không phải kết quả của một bộ test đã được chạy trong bài. Khi hiện thực, cần xác định module, phiên bản annotation, dữ liệu, cơ chế proxy và cấu hình validation tương ứng.

Một kiểm tra chỉ gọi method với dữ liệu tìm thấy chưa đủ kiểm chứng nullability. Cần đi qua cả đầu vào null, kết quả vắng mặt và trường hợp vi phạm số lượng, vì ba loại này đi qua các nhánh hợp đồng khác nhau.

Đối với phần tử generic, đừng mặc định runtime sẽ kiểm tra sâu chỉ vì checker có thể mô tả `List<@Nullable String>` hoặc `List<String>`. Nếu có yêu cầu kiểm tra nội dung, cần xác định cơ chế thực hiện cụ thể.

## 15. Chẩn đoán khi hành vi khác kỳ vọng

| Dấu hiệu | Điểm cần kiểm tra |
| --- | --- |
| Truyền null nhưng không bị chặn như mong đợi | Phiên bản hỗ trợ annotation, mặc định đúng package và đường gọi qua proxy |
| Query không có dữ liệu nhưng nhận exception thay vì null | Return có được công bố non-null và runtime validation có đang bật không |
| Method trả Optional vẫn từ chối null đầu vào | Hợp đồng tham số độc lập với hợp đồng vắng mặt của kết quả |
| Đánh dấu Nullable nhưng query không bỏ qua bộ lọc | Annotation không định nghĩa ngữ nghĩa điều kiện |
| Collection có mặt nhưng getter trên phần tử trả null | Hợp đồng phần tử/property khác hợp đồng container |
| ID null vẫn lỗi dù method khai báo lại cho nullable | Precondition CRUD không được thay bằng annotation tùy ý |
| Annotation giống tên nhưng hành vi khác | Kiểm tra đúng import và mô hình annotation |
| Chuyển package làm mất mặc định | Mỗi package cần được xem theo phạm vi annotation của nó |

Khi đọc exception, xác định lỗi xuất hiện ở bước kiểm tra tham số, thực thi query, kiểm tra kết quả hay mapping. Không chỉ dựa vào việc có chữ “null” trong thông báo để kết luận tất cả là một loại lỗi.

Nếu dùng mô hình annotation mới hoặc di chuyển từ mô hình cũ, cần xác nhận cả nhận diện của công cụ static và hỗ trợ runtime. Hai cơ chế bổ sung cho nhau nhưng không đồng nhất.

## 16. Tự kiểm tra mức độ hiểu

1. Một method trả `Optional<Customer>` có tự cho phép tham số null không?
2. `@Nullable` trên tham số khác `@Nullable` trên return ở điểm nào?
3. Vì sao collection rỗng khác với reference collection bằng null?
4. Trong ví dụ JPA, vì sao derived query bằng và query khai báo `= :email` có thể xử lý null khác nhau?
5. Vì sao `findById(null)` không phải một cách tìm kiếm bình thường không có kết quả?
6. Một `Customer` non-null có bảo đảm mọi property đều non-null không?
7. `@Nullable List<String>` khác `List<@Nullable String>` thế nào trong phạm vi JSpecify tương ứng?
8. Annotation null-safety, Bean Validation và constraint store thực tế kiểm tra các tầng nào?

Với mỗi method repository, hãy công bố riêng **giá trị đầu vào hợp lệ**, **cách biểu diễn kết quả vắng mặt** và **ngữ nghĩa query khi chấp nhận null**. Sau đó chọn annotation và cơ chế kiểm tra mà stack thực sự hỗ trợ, để caller dựa được vào một hợp đồng nhất quán khi dùng repository trên từng loại kho dữ liệu.
