# @NonNullApi, @NonNull và @Nullable ở các phiên bản Spring Data 3.x

Một phương thức Java trả `Customer` chưa nói rõ điều gì xảy ra khi truy vấn không có kết quả: trả `null`, phát lỗi hay yêu cầu caller dùng một wrapper khác. Tương tự, tham số `String email` chưa thể hiện email có được phép là `null` hay không. Trong Spring Data 3.x, các annotation nullability của Spring giúp công bố hợp đồng đó để công cụ phân tích và hạ tầng repository hiểu rõ hơn.

Bài học thuộc chương **Null và nullability** của **SPRING_DATA_COMMONS**, tập trung vào `org.springframework.lang.NonNullApi`, `NonNull` và `Nullable` trong hệ phiên bản 3.x. Cần phân biệt hợp đồng Java, kiểm tra của repository proxy, ngữ nghĩa truy vấn của store và ràng buộc dữ liệu; chúng có liên quan nhưng không thay thế nhau.

## 1. Phạm vi phiên bản và package annotation

Ba annotation trong bài được import từ:

```java
import org.springframework.lang.NonNullApi;
import org.springframework.lang.NonNull;
import org.springframework.lang.Nullable;
```

Đây là bộ annotation của Spring được dùng để mô tả nullability trong bối cảnh Spring Data 3.x. Ví dụ không trộn annotation của một hệ nullness khác hoặc giả định hướng dẫn của một major version khác áp dụng nguyên vẹn cho 3.x.

Các annotation này sử dụng metadata dựa trên JSR-305 để nhiều công cụ có thể hiểu ý nghĩa nullability. Điều đó không có nghĩa bản thân Java compiler sẽ tự biến mọi lời gọi truyền `null` thành lỗi biên dịch.

Khi đọc một dự án, cần xác định đầy đủ package import. Hai annotation cùng có tên ngắn `Nullable` chưa chắc được công cụ hoặc hạ tầng đang dùng xử lý theo cùng cách.

## 2. Vai trò của từng annotation

| Annotation | Vị trí sử dụng trong bài | Ý nghĩa chính |
| --- | --- | --- |
| `@NonNullApi` | Package, thường qua `package-info.java` | Đặt mặc định không null cho giá trị trả về và tham số của phương thức thuộc package |
| `@NonNull` | Phương thức hoặc tham số cụ thể | Công bố một vị trí không được null |
| `@Nullable` | Phương thức hoặc tham số cụ thể | Cho phép null tại vị trí được đánh dấu, có thể ghi đè mặc định không null |

Ví dụ đọc một chữ ký:

```java
@Nullable
Customer findCustomer(String email);
```

`@Nullable` đặt trên phương thức mô tả **giá trị trả về**. Nó không tự cho phép `email` là null. Nullability của tham số là một quyết định riêng, dựa vào annotation ở tham số và mặc định của package.

Ngược lại:

```java
Customer findCustomer(@Nullable String email);
```

Chỉ tham số `email` được đánh dấu cho phép null. Giá trị trả về vẫn phải được đọc theo hợp đồng riêng của phương thức và package.

### Phạm vi mặc định không bao gồm mọi thứ trong một object

`@NonNullApi` đặt mặc định cho phương thức và tham số. Nó không tự đặt mặc định cho mọi field của entity. Spring có annotation riêng như `@NonNullFields` cho một mục đích mặc định khác; đó không phải tác dụng đi kèm của `@NonNullApi`.

Một entity trả về không null vẫn có thể chứa một thuộc tính null nếu mapping và hợp đồng thuộc tính cho phép. Kiểm tra null ở giá trị trả về không tự kiểm tra toàn bộ đồ thị entity.

## 3. Đặt mặc định bằng package-info.java

Giả sử repository nằm trong package `com.example.customer.repository`. Có thể công bố mặc định:

```java
@org.springframework.lang.NonNullApi
package com.example.customer.repository;
```

Đây là nội dung của `package-info.java` thuộc chính package đó. Một cấu trúc nguồn minh họa:

```text
com/example/customer/repository/
    package-info.java
    CustomerRepository.java
```

Khi mặc định này có hiệu lực:

- Tham số phương thức không có ngoại lệ `@Nullable` được xem là không null.
- Giá trị trả về không có ngoại lệ `@Nullable` được xem là không null.
- Các wrapper như `Optional` hoặc tập hợp vẫn phải được hiểu theo hợp đồng kết quả riêng của repository.

### Package con không tự kế thừa mặc định

`com.example.customer.repository.internal` là một package Java khác với `com.example.customer.repository`. Đừng giả định `package-info.java` ở package cha tự bao phủ mọi package con theo dạng cây thư mục.

Nếu chuyển repository sang package khác mà quên cấu hình mặc định tương ứng, hợp đồng hiệu lực có thể thay đổi dù chữ ký phương thức gần như giữ nguyên.

Annotation trên package service cũng không tự đặt mặc định cho package repository. Phải kiểm tra đúng package nơi interface repository được khai báo.

## 4. Một repository minh họa đầy đủ các hợp đồng

Giả sử domain `Customer` có các thuộc tính:

| Thuộc tính Java | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh |
| `tenantId` | `String` | Phạm vi tổ chức |
| `email` | `String` | Email khách hàng |
| `nickname` | `String` | Biệt danh có thể chưa được cung cấp |

Ví dụ truy vấn bên dưới sử dụng **Spring Data JPA 3.x**, với entity và hạ tầng đã được ánh xạ/cấu hình phù hợp. Repository ở package đã có `@NonNullApi` như phần trên:

```java
package com.example.customer.repository;

import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;
import org.springframework.lang.NonNull;
import org.springframework.lang.Nullable;

public interface CustomerRepository extends Repository<Customer, Long> {

    Customer getByTenantIdAndEmail(String tenantId, String email);

    @Nullable
    Customer findNullableByTenantIdAndEmail(String tenantId, String email);

    Optional<Customer> findOptionalByTenantIdAndEmail(
            String tenantId, String email);

    List<Customer> findByTenantIdAndNickname(
            String tenantId, @Nullable String nickname);

    @NonNull
    Customer getExplicitByTenantIdAndEmail(
            @NonNull String tenantId, @NonNull String email);
}
```

`Nullable`, `Optional` và `Explicit` trước `By` là những phần mô tả subject trong các tên minh họa; chúng không phải điều kiện lọc. Những phương thức tìm theo email đều dựa trên `tenantId` và `email` nếu được suy diễn theo tên.

Các tên khác nhau giúp so sánh hợp đồng mà không tạo những phương thức trùng chữ ký chỉ khác annotation hoặc kiểu trả về.

### 4.1. Trả entity bắt buộc

```java
Customer getByTenantIdAndEmail(String tenantId, String email);
```

Trong package có mặc định không null, hai tham số không được null và giá trị trả về cũng không được null.

Nếu một query method được proxy kiểm tra nullability hoàn tất với kết quả đơn không có entity, Spring Data 3.x có thể báo `EmptyResultDataAccessException` thay vì trả null cho hợp đồng không null đó.

Chính hợp đồng nullability mới là điểm quan trọng. Từ `get` trong tên không phải một cơ chế phổ quát tự biến mọi phương thức thành “bắt buộc phải có dữ liệu”. Ví dụ đang xét là một derived query riêng, không phải một phương thức JPA cơ sở có ngữ nghĩa khác.

### 4.2. Cho phép giá trị trả về null

```java
@Nullable
Customer findNullableByTenantIdAndEmail(String tenantId, String email);
```

Phương thức này có thể trả null khi không có entity. Nhưng hai tham số vẫn không được null do mặc định package.

Caller phải xử lý kết quả:

```java
Customer customer = repository.findNullableByTenantIdAndEmail(
        tenantId, email);

if (customer == null) {
    // Nhánh không tìm thấy theo hợp đồng ứng dụng.
}
```

Không gọi ngay `customer.getId()` nếu chưa xác định kết quả tồn tại. `@Nullable` làm rõ trách nhiệm xử lý null; nó không tự thực hiện nhánh nghiệp vụ thay caller.

### 4.3. Biểu đạt thiếu dữ liệu bằng Optional

```java
Optional<Customer> findOptionalByTenantIdAndEmail(
        String tenantId, String email);
```

Giá trị trả về là một wrapper không null. Không có entity được biểu đạt bằng `Optional.empty()`, phù hợp với hợp đồng không null của wrapper.

```java
Customer customer = repository
        .findOptionalByTenantIdAndEmail(tenantId, email)
        .orElseThrow(() -> new IllegalStateException("Customer not found"));
```

Exception do `orElseThrow` ở đây là chính sách tầng ứng dụng. Nó khác với lỗi vì proxy nhận một kết quả null trái hợp đồng.

### 4.4. Cho phép riêng một tham số null

```java
List<Customer> findByTenantIdAndNickname(
        String tenantId, @Nullable String nickname);
```

`tenantId` vẫn bắt buộc không null. `nickname` được phép null tại ranh giới phương thức. Kết quả danh sách vẫn tuân theo hợp đồng collection của repository: không có entity phù hợp thì nhận danh sách rỗng, không cần một null để biểu đạt thiếu dữ liệu.

### 4.5. @NonNull tường minh trong package đã có mặc định

```java
@NonNull
Customer getExplicitByTenantIdAndEmail(
        @NonNull String tenantId, @NonNull String email);
```

Trong package này, các annotation tường minh lặp lại ý nghĩa mặc định. Chúng có thể giúp diễn đạt ở một ranh giới API cụ thể, nhưng không bắt buộc phải viết trên mọi vị trí nếu cả nhóm đã thống nhất dùng mặc định package.

`@NonNull` có ý nghĩa mô tả hợp đồng ngay cả khi dùng riêng lẻ cho công cụ hỗ trợ. Tuy vậy, không coi một annotation đơn lẻ là cách bật cơ chế kiểm tra runtime cho mọi phương thức tùy ý trong ứng dụng. Với query method Spring Data 3.x, cách cấu hình kiểm tra nhất quán được mô tả ở đây là bật mặc định bằng `@NonNullApi` trong package repository.

## 5. Điều gì được kiểm tra lúc runtime?

Khi hạ tầng repository Spring Data 3.x áp dụng kiểm tra nullability theo cấu hình, có thể hình dung ranh giới như sau:

```text
Caller gọi repository proxy
             |
             v
Kiểm tra tham số theo hợp đồng nullability
             |
             v
Thực hiện phương thức / truy vấn tương ứng
             |
             v
Kiểm tra giá trị trả về theo hợp đồng nullability
             |
             v
Trả kết quả hoặc báo vi phạm
```

Những trường hợp điển hình:

| Trường hợp | Kết quả mong đợi trong phạm vi kiểm tra repository |
| --- | --- |
| Truyền null cho tham số không null | Có thể bị từ chối bằng `IllegalArgumentException` |
| Truy vấn đơn kết quả trả null nhưng hợp đồng không null | Có thể phát `EmptyResultDataAccessException` |
| Truy vấn đơn kết quả có `@Nullable` và không tìm thấy | Cho phép trả null |
| Truy vấn trả `Optional` và không tìm thấy | Trả wrapper rỗng theo hợp đồng query |
| Truy vấn trả danh sách và không tìm thấy | Trả danh sách rỗng theo hợp đồng query |

Các exception ngoài cùng có thể bị bọc bởi tầng gọi khác. Khi chẩn đoán, cần xem nguyên nhân gốc và xác nhận lời gọi có thật sự đi qua repository proxy hay không.

### 5.1. Không phải bộ kiểm tra runtime toàn ứng dụng

Đặt `@NonNull` lên một phương thức Java bất kỳ không tự sinh code kiểm tra null trong method body. Một instance được tạo trực tiếp bằng `new`, một hàm tiện ích thông thường hoặc một service không có cơ chế validation tương ứng sẽ không tự được repository proxy kiểm tra.

Ngay cả khi annotation có thể được quan sát ở runtime, vẫn cần một thành phần chủ động đọc và thực thi hợp đồng. Annotation không tự là một câu lệnh `if`.

### 5.2. Không bật mặc định không đồng nghĩa mọi phương thức đều nhận null

Nhiều phương thức CRUD cơ sở vốn có hợp đồng và kiểm tra riêng, ví dụ id của `findById` không được null. Module, provider hoặc implementation cũng có thể từ chối null độc lập với các annotation trong bài.

Do đó, không thể bỏ `@NonNullApi` rồi kết luận mọi tham số của repository trở thành hợp lệ khi null. Sự thiếu vắng một mặc định annotation không xóa hợp đồng implementation đã có.

## 6. Annotation không quyết định ý nghĩa truy vấn với null

`@Nullable` nói rằng một giá trị null được phép ở vị trí Java đó. Nó không tự định nghĩa null sẽ được biến thành điều kiện gì trong truy vấn.

Ví dụ **Spring Data JPA 3.x**, với một derived query so sánh bằng đơn giản:

```java
List<Customer> findByTenantIdAndNickname(
        String tenantId, @Nullable String nickname);
```

Khi caller truyền `nickname = null`, cơ chế suy diễn JPA có thể tạo điều kiện kiểm tra thuộc tính null, tương ứng về ý nghĩa với:

```text
tenantId = tenantId truyền vào
AND nickname IS NULL
```

Không đọc `@Nullable` thành “bỏ qua điều kiện nickname nếu null”. Một truy vấn tìm khách hàng chưa có biệt danh khác với một truy vấn lấy mọi khách hàng bất kể biệt danh.

Nếu yêu cầu là bộ lọc tùy chọn, cần triển khai rõ ngữ nghĩa đó, chẳng hạn bằng truy vấn khai báo, Query by Example, Specification hoặc API dựng truy vấn mà module hỗ trợ. Không có một cơ chế bỏ qua null tự động và đồng nhất chỉ từ annotation này.

Tương tự, một chuỗi JPQL/SQL khai báo có placeholder null có thể có ngữ nghĩa khác với derived query so sánh bằng. Nullability của chữ ký không viết lại mọi biểu thức truy vấn và không giải quyết các quy tắc null riêng của SQL, tài liệu hay công cụ tìm kiếm.

## 7. Nullability của container khác với nullability bên trong

### 7.1. Optional

Với `Optional<Customer>`, cần phân biệt:

```text
Wrapper không null, có Customer
Wrapper không null, rỗng
Wrapper null
```

Hai trường hợp đầu là cách sử dụng bình thường. Thiết kế repository nên tránh thêm `@Nullable` lên một wrapper chỉ để biểu đạt “không có entity”, vì wrapper đã có cơ chế biểu đạt điều đó.

`Optional` cũng không bảo đảm uniqueness: nếu truy vấn yêu cầu tối đa một kết quả nhưng dữ liệu có nhiều hàng khớp, nó có thể thất bại theo hợp đồng số lượng kết quả của module.

### 7.2. Collection

```java
List<Customer> findByTenantId(String tenantId);
```

Trong hợp đồng collection query của Spring Data, không có entity thì trả một collection rỗng. Mặc định không null của giá trị trả về nói về chính collection.

Nó không tự chứng minh mọi thuộc tính trong mọi `Customer` đều không null. Nó cũng không biến annotation ở method thành một kiểm tra đệ quy trên tất cả phần tử của một collection do code tùy biến tạo ra.

Các annotation `org.springframework.lang.NonNull` và `Nullable` trong phạm vi 3.x của bài không phải một bộ type-use annotation đầy đủ để tùy ý chú thích mọi vị trí generic như phần tử lồng sâu. Cần phân biệt annotation trên một method trả `List<Customer>` với một hợp đồng nullness chi tiết cho mọi type argument.

### 7.3. Reactive publisher

Nếu module reactive hỗ trợ chữ ký:

```java
Mono<Customer> findByTenantIdAndEmail(String tenantId, String email);
```

một `Mono` không null vẫn có thể hoàn tất mà không phát `Customer`. Annotation trên giá trị trả về không tự biến publisher rỗng thành lỗi “không tìm thấy”.

Reactor không phát `onNext(null)` theo hợp đồng của nó; đây là đặc tính của reactive API, không phải tác dụng của `@NonNullApi` lên một phần tử chưa được phát.

Không suy từ kiểu `Mono` sang khả năng reactive của JPA. Ví dụ này chỉ dành cho module reactive hỗ trợ chữ ký tương ứng.

### 7.4. Primitive và giá trị rỗng nghiệp vụ

Một giá trị `long` không thể là null, nhưng có thể bằng `0`. Một `boolean` có thể là false. Một `String` không null vẫn có thể rỗng hoặc chỉ có khoảng trắng.

Các giá trị đó không vi phạm hợp đồng “không null” chỉ vì nghiệp vụ không chấp nhận chúng. Cần validation riêng cho quy tắc “lớn hơn 0”, “email hợp lệ” hoặc “chuỗi không trắng”.

## 8. Phân biệt với Bean Validation và ràng buộc cơ sở dữ liệu

| Cơ chế | Đối tượng được mô tả/kiểm tra | Không tự thay thế được |
| --- | --- | --- |
| `org.springframework.lang.NonNullApi` / `NonNull` / `Nullable` | Hợp đồng nullability của API Java và metadata cho công cụ/hạ tầng hiểu nó | Validation toàn bộ object, ràng buộc store |
| Bean Validation, ví dụ `jakarta.validation.constraints.NotNull` | Constraint khi có cơ chế validation phù hợp được kích hoạt | Mặc định nullability cho mọi repository method |
| Ràng buộc `NOT NULL` ở cơ sở dữ liệu | Dữ liệu được phép lưu ở tầng cơ sở dữ liệu | Hợp đồng giá trị trả về khi truy vấn không có hàng |
| Mapping như `@Column(nullable = false)` trong JPA | Metadata mapping và khả năng tham gia sinh schema theo cấu hình | Bảo đảm schema đang triển khai đã có constraint hoặc mọi lời gọi Java đã được validate |

`@NonNullApi` không tạo migration thêm `NOT NULL`. Nó cũng không biến một truy vấn không có kết quả thành một entity giả để thỏa ràng buộc.

Ngược lại, một cột `email NOT NULL` không bảo đảm phương thức tìm theo email luôn có hàng để trả về. Null ở giá trị cột và null do không có entity là hai vấn đề khác nhau.

Nếu DTO đầu vào cần `@NotBlank`, validation vẫn phải được kích hoạt đúng ở ranh giới ứng dụng. Không dùng `@NonNull` làm một thay thế mặc định cho mọi constraint nghiệp vụ.

## 9. Tác dụng với công cụ Java và Kotlin

### 9.1. Công cụ phân tích Java

IDE hoặc bộ phân tích nullness hiểu metadata JSR-305 có thể cảnh báo khi truyền một giá trị có thể null vào tham số không null, hoặc khi dereference một kết quả `@Nullable` chưa được kiểm tra.

Mức nghiêm khắc phụ thuộc công cụ và cấu hình build. Không nên viết trong hướng dẫn dự án rằng “Java sẽ không cho compile” nếu dự án mới chỉ có annotation nhưng chưa cấu hình một cơ chế phân tích tương ứng.

Runtime checking của repository và static analysis bổ sung cho nhau:

- Static analysis giúp phát hiện lời gọi có vấn đề trước khi chạy.
- Repository checking giúp phát hiện vi phạm ở ranh giới được hạ tầng quản lý.
- Cả hai không chứng minh mọi giá trị sâu trong entity đều hợp lệ nghiệp vụ.

### 9.2. Kotlin gọi API Java

Kotlin có thể dùng metadata nullability của các annotation Spring để hiểu chữ ký Java rõ hơn thay vì chỉ xem chúng như platform types không chắc chắn.

Trong hệ annotation JSR-305 đang xét, tùy chọn compiler như `-Xjsr305=strict` ảnh hưởng cách Kotlin đối xử với các khai báo đó. Cần thống nhất cấu hình theo bộ Kotlin/Spring Data 3.x của dự án, không coi annotation luôn có cùng mức lỗi/cảnh báo trên mọi build.

Kotlin cũng có nullability và metadata riêng cho repository viết bằng Kotlin. Đó là một nguồn hợp đồng bổ sung; không nên suy toàn bộ hành vi Kotlin chỉ từ vị trí annotation Java trong ví dụ này.

Khi nâng major version của hệ Spring hoặc đổi hệ annotation, cần đánh giá lại import, công cụ phân tích và cấu hình compiler theo phiên bản đích. Bài này giữ phạm vi 3.x, không coi việc thay import là một nâng cấp hành vi tự động.

## 10. Kế thừa và mở rộng repository cần giữ hợp đồng

Repository thường kế thừa CRUD, thêm query method hoặc dùng fragment tùy biến. Các đường mở rộng này không làm annotation trở thành một cơ chế thay đổi ngữ nghĩa tùy ý.

### 10.1. Không nới annotation để phủ nhận implementation cơ sở

Ví dụ một phương thức cơ sở yêu cầu id không null. Khai báo lại với `@Nullable` không làm implementation tự hỗ trợ một id null nếu nó vốn từ chối giá trị đó.

Cần đọc hợp đồng phương thức kế thừa cùng implementation/module, thay vì coi annotation ở interface con luôn ghi đè mọi hành vi runtime.

### 10.2. Không vô tình tăng yêu cầu với caller của interface cha

Nếu một API cha cho phép null ở tham số, implementation hoặc interface con không nên âm thầm yêu cầu non-null mà vẫn quảng bá như cùng một hợp đồng sử dụng. Caller tuân theo API cha có thể bị phá vỡ.

Tương tự, nếu API cha hứa trả một giá trị không null, implementation trả null sẽ phá lời hứa đó. Các quy tắc này là trách nhiệm thiết kế API, không chỉ là làm cho một cảnh báo IDE biến mất.

### 10.3. Đừng giả định mọi annotation method được kế thừa tự động

Việc công cụ hoặc framework kết hợp annotation trên interface, override và package cần được xem theo cơ chế thực tế. Khi thay package, override method hoặc thêm fragment, nên giữ hợp đồng rõ ràng và kiểm chứng đường gọi qua proxy thay vì dựa trên suy luận rằng mọi annotation luôn tự được sao chép.

## 11. Những lỗi dễ gặp

| Biểu hiện | Nguyên nhân có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Truyền null nhưng Java vẫn compile | Annotation không tự kích hoạt một lỗi compiler Java chuẩn | Xem công cụ phân tích và cấu hình build |
| Repository trả null dù dự định bắt buộc có kết quả | Thiếu mặc định đúng package hoặc không đi qua cơ chế kiểm tra mong đợi | Kiểm tra `package-info.java`, import và đường gọi |
| Package con có hành vi khác package cha | Mặc định package không tự bao phủ package con | Cấu hình đúng package chứa repository |
| Đánh dấu return `@Nullable` nhưng null argument vẫn lỗi | Return và parameter là hai vị trí riêng | Xem annotation của từng tham số và mặc định package |
| Tham số null bị hiểu thành “bỏ qua lọc” | Nhầm nullability với ngữ nghĩa predicate | Kiểm tra derived query hoặc chuỗi truy vấn của store |
| Một entity không null vẫn có field null | Chỉ kiểm tra container/entity ở biên phương thức | Xem mapping, hợp đồng thuộc tính và dữ liệu |
| Mono không null nhưng không phát entity | Nhầm publisher với giá trị bên trong | Xử lý tín hiệu rỗng theo hợp đồng reactive |
| `@NonNull` không kiểm tra chuỗi trắng | Hợp đồng chỉ nói về null | Dùng validation nghiệp vụ phù hợp |
| Database có `NOT NULL` nhưng query vẫn không có entity | Ràng buộc cột không tạo ra hàng phù hợp | Xử lý thiếu kết quả bằng hợp đồng return rõ ràng |

## 12. Kiểm chứng các hợp đồng khi tích hợp

Không cần một bài test cho từng annotation một cách máy móc. Các kiểm tra có giá trị là những kiểm tra phân biệt hành vi mà caller dựa vào.

Với repository ví dụ ở package có `@NonNullApi`, có thể chuẩn bị:

| Trường hợp | Hành vi cần xác nhận |
| --- | --- |
| Có đúng một khách hàng theo tenant/email | Cả ba dạng đơn kết quả trả đúng khách hàng |
| Không có khách hàng, return bắt buộc không null | Đường gọi qua proxy phát lỗi thiếu kết quả theo hợp đồng |
| Không có khách hàng, return `@Nullable` | Nhận null |
| Không có khách hàng, return `Optional` | Nhận `Optional.empty()` |
| Truyền null vào tenant hoặc email không null | Bị từ chối theo cơ chế kiểm tra repository |
| Truyền null vào nickname có `@Nullable` | Qua được kiểm tra tham số; truy vấn có đúng ngữ nghĩa store đã chọn |
| Không có kết quả collection | Nhận collection rỗng |
| Repository ở package con | Mặc định được cấu hình đúng tại package đó nếu cần |

Nếu kiểm tra một query có thể khớp nhiều entity, cần một trường hợp riêng cho cardinality. `@Nullable` không có nghĩa “được trả nhiều entity rồi chọn một”; `Optional` cũng không giải quyết dữ liệu trùng.

Nếu dùng mock repository để kiểm tra một service, mock có thể phục vụ chính sách service nhưng không chứng minh nullability interceptor hoặc ngữ nghĩa truy vấn của store. Muốn kiểm chứng những cơ chế đó, cần đi qua hạ tầng tương ứng trong kiểm tra tích hợp.

## 13. Bài tập phân tích

### Bài 1: Đọc annotation theo vị trí

Trong package có `@NonNullApi`, phương thức sau có cho phép truyền null email không?

```java
@Nullable
Customer findNullableByTenantIdAndEmail(String tenantId, String email);
```

**Phân tích:** không. Annotation trên phương thức cho phép return null; hai tham số vẫn theo mặc định không null. Nếu thật sự muốn một tham số nhận null, phải công bố ngoại lệ ở chính tham số và xác định ngữ nghĩa truy vấn phù hợp.

### Bài 2: Vì sao Optional.empty không vi phạm NonNullApi?

Một method trả `Optional<Customer>` không tìm thấy entity.

**Phân tích:** wrapper `Optional` vẫn tồn tại và không null. Thiếu entity nằm trong trạng thái rỗng của wrapper, không phải một giá trị wrapper null.

### Bài 3: Đổi package làm hợp đồng thay đổi

Repository được chuyển từ `com.example.customer.repository` sang `com.example.customer.repository.internal`, nhưng `package-info.java` chỉ còn ở package cũ.

**Phân tích:** package con là một package riêng, không tự kế thừa mặc định. Cần cấu hình và kiểm chứng hợp đồng tại package mới. Không dùng sự giống nhau của đường dẫn thư mục để suy ra phạm vi annotation Java.

### Bài 4: Null nickname có nghĩa là gì?

Với derived query JPA so sánh bằng trong bài, caller truyền null cho tham số nickname đã được đánh dấu `@Nullable`, rồi mong nhận mọi khách hàng của tenant.

**Phân tích:** annotation chỉ cho phép giá trị null ở biên Java. Trong trường hợp so sánh bằng JPA đã mô tả, điều kiện có thể trở thành `nickname IS NULL`, nên kết quả là khách hàng chưa có nickname. Nếu muốn bỏ qua lọc, cần triển khai ngữ nghĩa bộ lọc tùy chọn riêng.

### Bài 5: Annotation có thay migration không?

Một nhóm thêm `@NonNullApi` vào package repository rồi cho rằng dữ liệu hiện có trong cột email không thể null nữa.

**Phân tích:** annotation không sửa schema hay dữ liệu cũ, và không đặt mặc định field cho entity. Cần xem mapping, migration, constraint và quá trình xử lý dữ liệu theo yêu cầu thực tế.

## 14. Các điểm cần nhớ

- Trong phạm vi Spring Data 3.x của bài, dùng đúng `org.springframework.lang.NonNullApi`, `NonNull` và `Nullable`.
- `@NonNullApi` đặt mặc định ở package cho return và parameter; `@Nullable` tạo ngoại lệ tại vị trí cụ thể, còn `@NonNull` công bố yêu cầu tường minh.
- Package con không tự kế thừa mặc định, và annotation return không tự áp dụng sang tham số hoặc toàn bộ field/generic bên trong kết quả.
- Kiểm tra repository proxy, công cụ phân tích, validation nghiệp vụ và constraint cơ sở dữ liệu là các lớp khác nhau.
- Optional rỗng, collection rỗng, publisher rỗng và entity null có các hợp đồng khác nhau; không dùng một nhãn “nullable” để đánh đồng chúng.
- Cho phép null ở tham số không có nghĩa bỏ qua predicate; ngữ nghĩa truy vấn vẫn phụ thuộc module và loại truy vấn đang dùng.
