# Optional và các wrapper null trong accessor

## 1. Accessor có thể biểu diễn rõ giá trị vắng mặt

Một interface projection có thể đọc các thuộc tính mà dữ liệu cho phép null. Ví dụ, khách hàng đã tồn tại nhưng chưa có email. Nếu getter trả `String`, bên gọi phải tự biết giá trị đó có thể null:

```java
public interface CustomerEmailView {
    String getEmail();
}
```

Với nullable wrapper, hợp đồng đọc thể hiện sự vắng mặt ngay trong kiểu trả về:

```java
import java.util.Optional;

public interface CustomerEmailView {
    Optional<String> getEmail();
}
```

Spring Data Commons hỗ trợ nullable wrapper trên getter của interface projection: backing value khác null được đưa vào biểu diễn có giá trị; backing value null được đưa vào biểu diễn rỗng của wrapper. Xem [Commons — Nullable Wrappers](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.interfaces.nullable-wrappers).

Trong ví dụ này, accessor vẫn đọc property `email`. `Optional` mô tả cách trả giá trị cho bên gọi, không đổi tên property và không yêu cầu thêm một property `optionalEmail`.

## 2. Những wrapper được công bố hỗ trợ

Tài liệu Commons liệt kê các kiểu sau cho accessor projection:

| Kiểu đầy đủ | Hệ thư viện | Biểu diễn vắng mặt thường gặp |
|---|---|---|
| `java.util.Optional<T>` | JDK | `Optional.empty()` |
| `com.google.common.base.Optional<T>` | Guava | `Optional.absent()` |
| `scala.Option<T>` | Scala | `None` |
| `io.vavr.control.Option<T>` | Vavr | `Option.none()` |

Đối với ứng dụng Java đã dùng JDK, `java.util.Optional` là lựa chọn thuận tiện vì không cần thêm thư viện chỉ để có wrapper này. Nếu dự án đã thống nhất dùng Guava, Scala hoặc Vavr, cần giữ cách dùng nhất quán với hệ thư viện đó.

Không nên suy từ tên gọi “optional” rằng mọi kiểu tương tự đều được converter hỗ trợ. Ví dụ, `OptionalInt`, `OptionalLong`, `OptionalDouble` hoặc một lớp `MaybeValue<T>` tự viết không tự thuộc danh sách trên. Cần kiểm tra riêng khả năng của phiên bản đang dùng.

### 2.1. Hai lớp Optional khác package không phải cùng một kiểu

Java có thể gặp xung đột import giữa JDK và Guava. Khi cần minh họa nhiều lựa chọn, dùng tên đầy đủ sẽ rõ hơn:

```java
public interface GuavaEmailView {
    com.google.common.base.Optional<String> getEmail();
}

public interface ScalaEmailView {
    scala.Option<String> getEmail();
}

public interface VavrEmailView {
    io.vavr.control.Option<String> getEmail();
}
```

Đây là các interface thay thế nhau, giả định thư viện tương ứng có trên classpath. Ví dụ không yêu cầu thêm cả ba thư viện vào một dự án.

Guava dùng `absent()` và có API khác JDK; không thể chỉ đổi import rồi giữ nguyên mọi lời gọi `orElse`, `flatMap`. Xem [Guava Optional](https://guava.dev/releases/33.4.8-jre/api/docs/com/google/common/base/Optional.html). Scala và Vavr cũng có hợp đồng riêng, lần lượt được mô tả tại [Scala Option](https://www.scala-lang.org/api/2.13.16/scala/Option.html) và [Vavr Option](https://docs.vavr.io/#_option).

Sự hỗ trợ ở accessor có nghĩa framework biết tạo wrapper tương ứng từ backing value. Nó không làm cho toàn bộ API của các thư viện trở nên giống nhau.

## 3. Không có bản ghi khác với thuộc tính null

Có hai vị trí đặt wrapper thường bị nhầm:

```java
Optional<CustomerContactView> findContactById(Long id);
```

và:

```java
Optional<String> getEmail();
```

Wrapper ngoài phương thức repository biểu diễn việc có tìm được một kết quả hay không. Wrapper trong getter biểu diễn việc một thuộc tính của kết quả có giá trị hay không.

### 3.1. Ví dụ projection và repository

Giả sử `Customer` là domain type đã được ánh xạ cho store đang dùng, có các thuộc tính:

| Property | Kiểu domain | Ý nghĩa |
|---|---|---|
| `id` | `Long` | Định danh khác null của bản ghi tồn tại |
| `segment` | `String` | Nhóm khách hàng dùng làm điều kiện truy vấn |
| `email` | `String` | Có thể null |
| `emailVerified` | `Boolean` | Có thể null, true hoặc false |
| `creditLimit` | `BigDecimal` | Có thể chưa xác định |

Projection khai báo:

```java
import java.math.BigDecimal;
import java.util.Optional;

public interface CustomerContactView {

    Long getId();

    Optional<String> getEmail();

    Optional<Boolean> getEmailVerified();

    Optional<BigDecimal> getCreditLimit();
}
```

Repository khai báo query riêng:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.Repository;

public interface CustomerRepository extends Repository<Customer, Long> {

    Optional<CustomerContactView> findContactById(Long id);

    List<CustomerContactView> findBySegmentOrderByIdAsc(String segment);
}
```

Ví dụ giả định module store và phiên bản hỗ trợ interface projection với đường query này. Domain type của repository vẫn là `Customer`; projection là hình dạng dữ liệu đọc.

### 3.2. Bảng trạng thái

| Dữ liệu truy vấn | Wrapper ngoài repository | Getter `getEmail()` |
|---|---|---|
| Không tìm thấy khách hàng | Rỗng | Không có projection để gọi getter |
| Có khách hàng, `email = null` | Có projection | Rỗng |
| Có khách hàng, `email = ""` | Có projection | Có giá trị là chuỗi rỗng |
| Có khách hàng, email bình thường | Có projection | Có giá trị email |

Khai báo `id` trong projection giúp ví dụ thể hiện rõ bản ghi tồn tại dù email null. Không lấy kết quả của một truy vấn chỉ chọn scalar nullable rồi mặc định suy ra đầy đủ các trạng thái như truy vấn projection này.

Repository trả `Optional<T>` vẫn có hợp đồng tối đa một kết quả. Nếu truy vấn trả nhiều kết quả khi chỉ được phép một, `Optional` không có nghĩa “tự chọn phần tử đầu tiên”; tài liệu nêu lỗi `IncorrectResultSizeDataAccessException`. Xem [Repository Query Return Types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html).

Đối với truy vấn danh sách, không có hàng nào được biểu diễn bằng danh sách rỗng theo hợp đồng repository. Còn trong một danh sách có phần tử, từng projection có thể có accessor wrapper rỗng. Xem [Null Handling of Repository Methods](https://docs.spring.io/spring-data/commons/reference/repositories/null-handling.html).

## 4. Null khác chuỗi rỗng, false và số không

Nullable wrapper không tự gán ý nghĩa nghiệp vụ cho giá trị. Nó biểu diễn sự có mặt của backing value.

Giả sử có các khách hàng thuộc nhóm `RETAIL`:

| id | email | emailVerified | creditLimit |
|---|---|---|---|
| 21 | `an@example.test` | false | 0 |
| 22 | null | null | null |
| 23 | `""` | true | 500000 |
| 24 | `"   "` | false | null |

Kết quả đọc mong đợi:

| Getter | Giá trị domain | Trạng thái wrapper |
|---|---|---|
| `getEmail()` | null | Rỗng |
| `getEmail()` | `""` | Có giá trị |
| `getEmail()` | `"   "` | Có giá trị |
| `getEmailVerified()` | false | Có giá trị false |
| `getEmailVerified()` | null | Rỗng |
| `getCreditLimit()` | 0 | Có giá trị số không |
| `getCreditLimit()` | null | Rỗng |

Do đó:

- `Optional.empty()` của email không đồng nghĩa với mọi email không dùng được.
- `Optional.of(false)` khác trạng thái chưa có thông tin xác minh.
- Hạn mức bằng 0 khác hạn mức chưa xác định.

Nếu nghiệp vụ cần phân biệt “không được thu thập”, “người dùng đã xóa”, “đã ẩn do quyền truy cập” hoặc “chưa tải”, một wrapper rỗng đơn thuần không giữ đủ lý do. Khi đó cần một mô hình kết quả có trạng thái rõ ràng hơn.

### 4.1. Không gộp trạng thái quá sớm

Đoạn sau có thể phù hợp cho một chính sách cụ thể:

```java
boolean verified =
        contact.getEmailVerified().orElse(false);
```

Nhưng nó đã gộp hai trường hợp: có thông tin là false và không có thông tin. Nếu màn hình cần phân biệt, hãy giữ cả ba trạng thái:

```java
String verificationLabel = contact.getEmailVerified()
        .map(value -> value ? "Đã xác minh" : "Chưa xác minh")
        .orElse("Chưa có thông tin xác minh");
```

Tương tự, chỉ dùng `creditLimit.orElse(BigDecimal.ZERO)` khi quy tắc nghiệp vụ cho phép coi chưa có hạn mức là số không. Việc chọn mặc định là quyết định của ứng dụng, không phải kết luận do wrapper áp đặt.

## 5. Đọc Optional theo mục đích sử dụng

### 5.1. Tách lỗi không có khách hàng khỏi email vắng mặt

```java
CustomerContactView contact = repository.findContactById(id)
        .orElseThrow(() ->
                new IllegalArgumentException(
                        "Customer not found: " + id));

String emailLabel = contact.getEmail()
        .orElse("Chưa có email");
```

Luồng này xử lý hai tình huống ở hai bước: không có khách hàng được báo lỗi; khách hàng tồn tại nhưng email null được biểu diễn bằng nhãn.

Lựa chọn loại lỗi và cách phản hồi ở API thuộc về ứng dụng. Ví dụ chỉ minh họa việc giữ hai ý nghĩa riêng.

### 5.2. Chuẩn hóa hiển thị là một bước riêng

Nếu màn hình muốn coi chuỗi rỗng và toàn khoảng trắng như chưa có email, có thể áp dụng chính sách đó sau khi đọc:

```java
String emailLabel = contact.getEmail()
        .map(String::trim)
        .filter(value -> !value.isEmpty())
        .orElse("Chưa có email");
```

Ở đây, `map` và `filter` của mã ứng dụng mới làm chuỗi rỗng trở thành trạng thái rỗng trong chuỗi xử lý. Getter projection ban đầu không tự trim và không tự loại chuỗi rỗng.

Thao tác này cũng không cập nhật email lưu trữ. Nếu dữ liệu cần chuẩn hóa lâu dài, hãy thực hiện qua luồng ghi và quy tắc validation thích hợp.

### 5.3. Khi chủ đích là lấy email nếu có

Có thể nối hai wrapper bằng `flatMap`:

```java
Optional<String> email =
        repository.findContactById(id)
                .flatMap(CustomerContactView::getEmail);
```

Biểu thức này trả rỗng trong cả hai trường hợp: không có khách hàng hoặc có khách hàng nhưng email null. Điều đó phù hợp nếu bên gọi chỉ cần “email có sẵn”.

Nếu cần phân biệt hai trường hợp, hãy giữ wrapper ngoài hoặc xử lý khách hàng trước như phần 5.1. Việc làm phẳng đã chủ động bỏ một phần thông tin.

Ngược lại, dùng `map(CustomerContactView::getEmail)` trên wrapper ngoài sẽ tạo hai tầng `Optional` khi khách hàng tồn tại. Hai cách viết có ý nghĩa khác nhau.

### 5.4. Tránh gọi get khi chưa xác định giá trị tồn tại

```java
// Có thể lỗi nếu backing value là null.
String email = contact.getEmail().get();
```

Hãy chọn hành vi theo nhu cầu: `orElse` cho giá trị mặc định, `ifPresent` cho hành động chỉ khi có giá trị, hoặc `orElseThrow` cho điều kiện bắt buộc.

Nếu giá trị dự phòng cần tính toán, `orElseGet` cho phép chỉ gọi supplier khi wrapper rỗng. Chi tiết hợp đồng `map`, `flatMap`, `get` và các phương thức xử lý được mô tả tại [Java Optional API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).

## 6. Optional trong projection không buộc entity dùng Optional

Với property domain:

```java
private String email;

public String getEmail() {
    return email;
}
```

projection vẫn có thể khai báo:

```java
Optional<String> getEmail();
```

Tầng projection chịu trách nhiệm biểu diễn giá trị trả về bằng wrapper được hỗ trợ. Không cần đổi field entity thành `Optional<String>` chỉ để đạt mục tiêu này.

Cần giữ riêng các hợp đồng:

| Hợp đồng | Câu hỏi cần trả lời |
|---|---|
| Schema và mapping | Dữ liệu lưu trữ có cho phép null không? |
| Domain | Null có ý nghĩa gì trong nghiệp vụ? |
| Accessor projection | Bên gọi nhận giá trị nullable hay một wrapper? |
| Repository | Truy vấn có thể không có bản ghi hoặc có nhiều bản ghi không? |
| API đầu ra | Giá trị vắng mặt được biểu diễn thế nào cho client? |

Một getter wrapper không tạo ràng buộc `NOT NULL`, không sửa schema và không làm giá trị email trở thành hợp lệ. Ngược lại, một ràng buộc dữ liệu cũng không bảo đảm rằng mọi query tùy biến đều trả đúng alias và giá trị cho getter.

Nullability annotation của dự án giúp mô tả hợp đồng kiểu, nhưng không thay thế quy tắc chuyển backing value thành nullable wrapper. Cần dùng annotation phù hợp với phiên bản và cấu hình của ứng dụng.

### 6.1. Getter vẫn phải khớp property

Khai báo đúng:

```java
Optional<String> getEmail();
```

Khai báo sai tên khi domain không có property tương ứng:

```java
Optional<String> getEmai();
```

Một getter sai tên không tự trở thành một trường tùy chọn mới. Tùy store và đường query, lỗi có thể xuất hiện khi xây dựng truy vấn, xử lý kết quả hoặc đọc accessor.

Đặc biệt với query khai báo, một alias bị thiếu có thể khiến giá trị đầu vào của projection không đúng mong đợi. Không thấy giá trị trong wrapper chưa đủ để kết luận cột trong database đang null; trước hết phải kiểm tra mapping và query.

### 6.2. Nullable wrapper không tự đổi sang open projection

Nếu accessor tiếp tục đọc đúng property `email`, việc đổi `String` thành `Optional<String>` không thêm một biểu thức tính toán tùy ý. Không cần viết SpEL chỉ để bọc null.

Khả năng giới hạn dữ liệu đọc vẫn phụ thuộc hình dạng projection, loại query và module store. Wrapper hỗ trợ null là một phần của hợp đồng kết quả, không phải cam kết độc lập về số cột hoặc số truy vấn.

## 7. Biên chuyển đổi và những trường hợp cần kiểm tra riêng

### 7.1. Interface proxy và DTO constructor là hai cơ chế khác nhau

Bài này nói về getter của interface projection. Không suy rằng mọi constructor DTO có tham số `Optional<String>` đều tự nhận được một cột nullable theo cùng cơ chế.

Nếu chọn class projection hoặc record DTO, cần kiểm tra mapping constructor và khả năng của store. Khi cần, ứng dụng có thể nhận kiểu dữ liệu thích hợp rồi tự ánh xạ sang DTO đầu ra.

### 7.2. Không trả null thay cho một wrapper

Nếu tự viết một implementation projection hoặc một adapter thủ công, phải giữ hợp đồng:

```java
Optional<String> email = Optional.ofNullable(rawEmail);
```

Không viết:

```java
Optional<String> email = null;
```

Trong trường hợp nullable, `Optional.ofNullable` phù hợp; `Optional.of(null)` sẽ ném ngoại lệ. Việc framework xử lý getter chuẩn không sửa được một implementation tự viết đang trả null.

Một wrapper rỗng là đối tượng hợp lệ có thể gọi `isPresent()`; một tham chiếu wrapper null vẫn gây lỗi khi gọi phương thức.

### 7.3. Chuyển sang dữ liệu đầu ra một cách chủ động

Một ứng dụng có thể chọn DTO cho giao tiếp bên ngoài:

```java
import java.math.BigDecimal;

public record CustomerContactResponse(
        Long id,
        String email,
        Boolean emailVerified,
        BigDecimal creditLimit) {
}
```

Ví dụ ánh xạ tại biên API:

```java
CustomerContactResponse response =
        new CustomerContactResponse(
                contact.getId(),
                contact.getEmail().orElse(null),
                contact.getEmailVerified().orElse(null),
                contact.getCreditLimit().orElse(null));
```

DTO này chủ động dùng các giá trị nullable. Nếu hợp đồng API yêu cầu bỏ field vắng mặt hoặc thêm trạng thái lý do, cần thiết kế DTO và cấu hình serialization tương ứng.

Không mặc định rằng mọi serializer sẽ biến các loại Optional thành cùng một JSON. Hình dạng truyền ra phải được xác nhận trong ứng dụng; kiểu wrapper dùng nội bộ không thay thế thiết kế hợp đồng API.

## 8. Những tình huống thực hành cần quan sát

Có thể dùng các hàng dữ liệu ở phần 4 làm tập ví dụ nhỏ. Các kết quả dưới đây là kỳ vọng để kiểm chứng trong dự án đích, không phải kết quả chạy trên một store chưa được chỉ định.

| Tình huống | Kỳ vọng |
|---|---|
| ID không tồn tại | Wrapper ngoài repository rỗng |
| Khách hàng tồn tại, email null | Có projection, getter email rỗng |
| Email là chuỗi rỗng | Getter có giá trị chuỗi rỗng |
| Email là toàn khoảng trắng | Getter vẫn có giá trị trước bước chuẩn hóa của ứng dụng |
| `emailVerified = false` | Wrapper có giá trị false |
| `emailVerified = null` | Wrapper rỗng |
| `creditLimit = 0` | Wrapper có giá trị số không |
| Getter sai tên hoặc alias thiếu | Điều tra mapping, không tự diễn giải là dữ liệu nghiệp vụ vắng mặt |
| Truy vấn danh sách không có hàng | Danh sách rỗng |
| Truy vấn đơn trả nhiều hàng | Không dùng Optional để che lỗi số lượng kết quả |
| Dùng Guava, Scala hoặc Vavr | Có dependency phù hợp và đúng kiểu wrapper thực tế |
| Ánh xạ sang response | Hình dạng đầu ra đúng hợp đồng API đã chọn |

Khi xác minh, cần quan sát cả sự có mặt của wrapper và giá trị bên trong. Chỉ kiểm tra “không có NullPointerException” chưa đủ để bảo đảm ứng dụng còn phân biệt được false, zero và unknown.

## 9. Lựa chọn hợp đồng accessor trong thực tế

Nên dùng `Optional<T>` trên accessor khi sự vắng mặt của thuộc tính là một phần có ý nghĩa trong mô hình đọc và bên gọi cần xử lý rõ ràng. Các wrapper được công bố hỗ trợ giúp diễn đạt điều đó mà vẫn giữ tên property domain.

Lựa chọn mặc định, chuẩn hóa chuỗi và gộp trạng thái thuộc về nghiệp vụ. Một màn hình có thể hiện “Chưa có email”, trong khi một luồng gửi thông báo có thể yêu cầu email tồn tại và báo lỗi nếu thiếu. Cùng một projection có thể phục vụ hai cách xử lý mà không tự áp đặt một mặc định.

Hợp đồng tốt giữ rõ ba câu hỏi: có bản ghi hay không, thuộc tính có giá trị hay không, và giá trị hiện có có đáp ứng yêu cầu nghiệp vụ hay không. Nullable wrapper giải quyết câu hỏi thứ hai; repository và logic ứng dụng hoàn thiện hai phần còn lại.
