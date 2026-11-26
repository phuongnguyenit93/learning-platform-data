# Kiểm tra lúc biên dịch, hỗ trợ IDE và kiểm tra runtime

Một phương thức khai báo “không nhận null” hoặc “không trả null” chỉ có ích khi người đọc biết hợp đồng đó được kiểm tra ở đâu. Trong Java và Spring Data, compiler, IDE, repository proxy, Bean Validation và cơ sở dữ liệu là các cơ chế khác nhau.

Một annotation nullability có thể được IDE hiểu nhưng chưa được build kiểm tra. Build có thể phân tích null nhưng lời gọi từ reflection vẫn đưa được null tới runtime. Repository proxy có thể kiểm tra tham số và kết quả của một phương thức, nhưng không tự kiểm tra mọi thuộc tính nằm sâu trong đối tượng.

Trong phạm vi Spring Data Commons, mục tiêu là thiết kế hợp đồng null rõ ràng cho repository, rồi xác định công cụ nào thực thi từng phần của hợp đồng. Khả năng cụ thể còn phụ thuộc phiên bản Spring Data, hệ annotation, ngôn ngữ và module store.

Sau bài học, bạn cần có khả năng:

- Phân biệt lỗi biên dịch Java, chẩn đoán từ nullness checker và cảnh báo IDE.
- Đọc đúng ý nghĩa của nullable/non-null trên tham số, kết quả và phần tử collection.
- Giải thích phạm vi kiểm tra runtime của repository proxy.
- Phân biệt annotation nullability, Bean Validation và ràng buộc database.
- Thiết kế cách xử lý không có kết quả bằng nullable value, `Optional` hoặc collection rỗng.
- Giữ hợp đồng nhất quán giữa Java, Kotlin, IDE và CI.

## 1. Ba lớp kiểm tra trả lời ba câu hỏi

| Lớp | Câu hỏi chính | Khi phát hiện | Giới hạn |
|---|---|---|---|
| Phân tích trong build | Mã nguồn có dùng giá trị có thể null sai hợp đồng không? | Trước khi chạy, nếu đã bật công cụ phù hợp | Phụ thuộc annotation, checker và cấu hình |
| Hỗ trợ IDE | Vị trí nào nên cảnh báo khi lập trình? | Khi soạn mã hoặc chạy inspection | Không tự chứng minh CI sẽ từ chối mã đó |
| Kiểm tra runtime | Lời gọi/kết quả thực tế có vi phạm ràng buộc đang được thực thi không? | Khi chương trình chạy | Chỉ kiểm tra nơi có cơ chế validation/guard |

Ba lớp bổ sung cho nhau. Chúng không tự thay thế nhau và không mặc định có cùng mức nghiêm ngặt.

### 1.1. Java compiler thông thường không có kiểu tham chiếu non-null

Đoạn Java sau có thể biên dịch bằng compiler thông thường:

```java
String email = null;
System.out.println(email.length());
```

Lỗi xuất hiện khi thực thi phép gọi trên null, không phải vì Java đã từ chối phép gán.

Một annotation như `@Nullable` không tự làm compiler Java thay đổi hệ kiểu. Muốn báo lỗi trong build, cần công cụ phân tích hiểu annotation và được tích hợp đúng.

Cần phân biệt:

- “Compiler không biên dịch được vì sai cú pháp/kiểu Java.”
- “Một checker được tích hợp trong build báo lỗi nullness.”
- “IDE hiển thị cảnh báo nhưng build vẫn chấp nhận.”

Các tùy chọn cảnh báo tổng quát như `-Xlint` hoặc chuyển warning thành error không tự tạo ra một hệ phân tích nullness đầy đủ. Công cụ phải phát hiện được loại vấn đề đó trước.

### 1.2. Không thấy cảnh báo chưa phải bằng chứng an toàn

Có thể IDE không nhận ra hệ annotation, một package chưa có default nullness, hoặc phần mã cần phân tích nằm ngoài phạm vi inspection.

Tương tự, build thành công có thể chỉ có nghĩa checker chưa được bật, không phải mọi đường đi null đã được chứng minh an toàn.

## 2. Xác định chính xác phần nào được phép null

Xét hợp đồng:

```java
List<Customer> findByEmail(String email);
```

Nếu không có hệ annotation/default được xác định, chỉ nhìn chữ ký Java này chưa trả lời đầy đủ:

- `email` có được phép null không?
- Bản thân đối tượng `List` có thể null không?
- Một phần tử trong danh sách có thể null không?
- `Customer.email` có thể null không?

Đây là bốn câu hỏi khác nhau.

### 2.1. Kết quả bao ngoài khác dữ liệu nằm bên trong

| Dạng hợp đồng | Câu hỏi được diễn đạt |
|---|---|
| Nullable `Customer` | Có thể không có đối tượng khách hàng |
| Non-null `Optional<Customer>` | Luôn có wrapper; wrapper có thể rỗng |
| Non-null `List<Customer>` | Luôn có container kết quả |
| Non-null list với phần tử nullable | Có list, nhưng từng phần tử có thể null |
| Non-null `Customer` | Có đối tượng; chưa đủ kết luận mọi thuộc tính của nó đều non-null |

Trong repository hỗ trợ kiểu collection tương ứng, không có kết quả thường được biểu diễn bằng collection rỗng, không phải null container. Hợp đồng đó không tự nói rằng mọi projection hoặc mọi thuộc tính trong phần tử đều có dữ liệu.

`Optional.empty()` cũng khác `null`. Trả null thay cho một `Optional` vi phạm ý định của wrapper. `Optional.of(null)` ném lỗi; `Optional.ofNullable(value)` cho phép chuyển một giá trị có thể null thành wrapper rỗng.

### 2.2. Nullable không có nghĩa là bỏ qua điều kiện truy vấn

Một tham số được phép null chỉ cho biết caller có thể truyền null theo hợp đồng phương thức. Nó không định nghĩa rằng query sẽ bỏ qua bộ lọc đó.

Ví dụ, một phép so sánh suy diễn trong JPA có thể có quy tắc xử lý null thành điều kiện kiểm tra null. Những store, toán tử hoặc truy vấn khai báo khác có thể có hành vi khác.

Nếu nghiệp vụ là “không nhập email thì không lọc theo email”, cần thiết kế logic đó tường minh bằng API truy vấn hoặc các phương thức thích hợp. Annotation nullable không tự tạo logic bộ lọc tùy chọn.

## 3. Tên annotation gần giống không có nghĩa cơ chế giống nhau

Luôn đọc import đầy đủ:

| Hệ/cơ chế | Ví dụ | Vai trò chính |
|---|---|---|
| JSpecify | `org.jspecify.annotations.NullMarked`, `Nullable` | Mô tả nullness của kiểu và phạm vi mặc định để công cụ sử dụng |
| Annotation Spring | `org.springframework.lang.NonNullApi`, `NonNull`, `Nullable` | Hợp đồng nullability theo hệ annotation Spring của những phiên bản dùng cơ chế này |
| Bean Validation | `jakarta.validation.constraints.NotNull` | Ràng buộc được validation engine kiểm tra khi validation được kích hoạt |
| Guard Java | `Objects.requireNonNull(...)` | Kiểm tra trực tiếp khi dòng mã được thực thi |
| Ràng buộc database | `NOT NULL` | Cơ sở dữ liệu từ chối giá trị null tại nơi ràng buộc được áp dụng |

Một project phải chọn hệ annotation phù hợp với phiên bản thư viện và công cụ đang dùng. Không ghép nhiều annotation cùng tên chỉ để làm IDE hết cảnh báo.

Bài học trình bày riêng JSpecify và cơ chế annotation Spring để thấy ranh giới. Không nên mặc định hai hệ kích hoạt cùng một hành vi runtime ở mọi phiên bản.

### 3.1. Annotation là metadata, không phải câu lệnh kiểm tra

Chỉ việc annotation tồn tại trên classpath hoặc được giữ tới runtime chưa làm nó tự ném exception. Phải có compiler/checker, IDE hoặc framework đọc và thực thi metadata đó.

Ví dụ, `@NullMarked` không tự chèn `Objects.requireNonNull` vào mọi phương thức. `@NotNull` cũng không tự chạy một validation engine cho mọi đối tượng được tạo bằng `new`.

## 4. JSpecify: diễn đạt hợp đồng để công cụ phân tích hiểu

Một phạm vi có thể được đánh dấu mặc định non-null bằng `@NullMarked`. Ví dụ một file `package-info.java` trong dự án sử dụng JSpecify:

```java
@org.jspecify.annotations.NullMarked
package example.customer.api;
```

Đoạn này là ví dụ nội dung cấu hình package trong dự án, không phải yêu cầu tạo thêm file cho bài học.

Trong cùng phạm vi được đánh dấu:

```java
package example.customer.api;

import java.util.List;
import java.util.Optional;

import org.jspecify.annotations.Nullable;

public interface CustomerLookup {

    Customer requireByEmail(String email);

    @Nullable
    Customer findByEmail(String email);

    Optional<Customer> findOptionalByEmail(String email);

    List<Customer> findActive();

    List<@Nullable Customer> findPossiblyMissingEntries();
}
```

Ý định hợp đồng:

- `String email` là đầu vào non-null trong phạm vi này.
- `requireByEmail` cam kết một giá trị `Customer` non-null.
- `findByEmail` cho phép kết quả null.
- `findOptionalByEmail` trả wrapper non-null, có thể rỗng.
- `List<Customer>` mô tả list và phần tử non-null theo hợp đồng kiểu trong phạm vi được đánh dấu.
- `List<@Nullable Customer>` cho phép phần tử null, trong khi list vẫn non-null.

Interface này minh họa hợp đồng kiểu; không phải mọi tên phương thức ở đây được kỳ vọng tự tạo query. Repository thực tế cần chữ ký và cơ chế mà module hỗ trợ.

### 4.1. Type-use giúp phân biệt container và phần tử

Với annotation type-use phù hợp:

```java
@Nullable List<Customer> maybeList;
List<@Nullable Customer> listWithNullableElements;
```

Hai khai báo không tương đương:

- Dòng đầu cho phép bản thân list null.
- Dòng sau cho phép phần tử null.

Khả năng phân tích chi tiết phụ thuộc công cụ. Không sao chép cú pháp generic này với một annotation không có target `TYPE_USE`, chẳng hạn chỉ cho phép gắn trên phương thức, tham số hoặc field.

### 4.2. Chẩn đoán từ checker không phải kết quả mặc định của javac

Giả sử caller và các kiểu liên quan đang được phân tích bằng công cụ hiểu hợp đồng:

```java
Customer customer = lookup.findByEmail(email);
customer.getEmail();
```

Vì `findByEmail` có thể trả null, công cụ có thể báo việc dereference không an toàn. Mức cảnh báo hay lỗi phụ thuộc cấu hình công cụ.

Một cách xử lý rõ:

```java
Customer customer = lookup.findByEmail(email);

if (customer == null) {
    return;
}

String foundEmail = customer.getEmail();
```

Việc `customer` đã được kiểm tra không tự chứng minh `foundEmail` non-null. Cần tiếp tục xem hợp đồng của `getEmail()`.

Không suy ra rằng mọi framework sẽ đọc JSpecify để kiểm tra runtime. Cần xác nhận hỗ trợ của phiên bản thực tế nếu định dựa vào framework cho việc đó.

## 5. Cơ chế runtime của repository với annotation Spring

Phần này minh họa hệ annotation `org.springframework.lang` trong các dự án Spring Data hỗ trợ cơ chế kiểm tra runtime tương ứng. Cần đối chiếu phiên bản thực tế trước khi dùng nguyên cấu hình này; không mặc định mọi hệ annotation có cùng tác dụng.

### 5.1. Khai báo default ở đúng package

Ví dụ nội dung `package-info.java`:

```java
@org.springframework.lang.NonNullApi
package example.customer.repository;
```

Trong hệ này, default chủ yếu áp dụng cho tham số và giá trị trả về của phương thức. Nó không tự tuyên bố mọi field của mọi entity non-null, cũng không tương đương annotation type-use cho từng phần tử generic.

Package con là package riêng. Đặt annotation trên `example.customer` không tự làm `example.customer.repository` có cùng default theo cơ chế package annotation của Java.

### 5.2. Repository với các cách biểu diễn vắng dữ liệu

Giả sử `Customer` có thuộc tính `email`, module hỗ trợ các query tương ứng và email được xem là duy nhất theo yêu cầu nghiệp vụ:

```java
package example.customer.repository;

import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.Repository;
import org.springframework.lang.Nullable;

public interface CustomerRepository
        extends Repository<Customer, Long> {

    Customer getByEmail(String email);

    @Nullable
    Customer findCustomerByEmail(String email);

    Optional<Customer> findOptionalByEmail(String email);

    List<Customer> findByActiveTrue();

    List<Customer> findAllByEmail(@Nullable String email);
}
```

Các khai báo dùng cùng domain nhưng hợp đồng khác nhau:

| Phương thức | Đầu vào | Kết quả/hành vi dự kiến trong cấu hình hỗ trợ |
|---|---|---|
| `getByEmail` | Email non-null | Phải có kết quả non-null; không có kết quả vi phạm hợp đồng |
| `findCustomerByEmail` | Email non-null | Cho phép trả null khi không có kết quả |
| `findOptionalByEmail` | Email non-null | Wrapper `Optional` không null; có thể rỗng |
| `findByActiveTrue` | Không có tham số | Collection không null, có thể rỗng |
| `findAllByEmail` | Email được phép null | Việc xử lý null trong query phải xem theo module/toán tử |

Annotation trên kết quả `findCustomerByEmail` không làm tham số email nullable. Annotation trên tham số của `findAllByEmail` cũng không làm danh sách kết quả nullable.

### 5.3. Runtime phát hiện điều gì?

Với repository proxy và cơ chế kiểm tra nullability đang hoạt động:

- Truyền null vào tham số được khai báo non-null có thể bị từ chối bằng `IllegalArgumentException`.
- Một query đơn kết quả không có dữ liệu nhưng phương thức cam kết non-null có thể dẫn tới `EmptyResultDataAccessException`.
- Kết quả đơn được phép nullable có thể trả null.
- Wrapper `Optional` có thể biểu diễn vắng dữ liệu bằng `Optional.empty()`.
- Collection được hỗ trợ có thể biểu diễn không có kết quả bằng collection rỗng.

Những hành vi này không phải do compiler Java tự chèn kiểm tra. Hạ tầng repository đọc hợp đồng và kiểm tra ở ranh giới lời gọi/kết quả.

Không dùng ví dụ này để suy ra mọi phương thức của một service tự viết cũng được Spring kiểm tra giống repository.

### 5.4. Không có kết quả khác nhiều kết quả

`Optional<Customer>` không có nghĩa “lấy đại một khách hàng nếu có nhiều”. Nếu truy vấn đơn kết quả trả quá nhiều bản ghi, có thể phát sinh lỗi cardinality của module, thường thuộc nhóm incorrect result size.

Nullability trả lời câu hỏi có cho phép vắng giá trị không. Nó không thay thế uniqueness, giới hạn kết quả hoặc thiết kế dữ liệu.

### 5.5. Runtime không tự duyệt toàn bộ object graph

Một kiểm tra thấy giá trị trả về khác null chưa chứng minh:

- `customer.getEmail()` khác null.
- Mọi phần tử trong list đều hợp lệ.
- Một projection có đủ trường dữ liệu.
- Association lazy có thể truy cập sau khi transaction đã kết thúc.
- Dữ liệu thỏa định dạng, khoảng giá trị hoặc quyền truy cập.

Cần thiết kế từng ràng buộc và cơ chế kiểm tra tương ứng. Không gán cho `@NonNullApi` vai trò của một validator cho toàn bộ domain.

## 6. Ranh giới proxy quan trọng với kiểm tra runtime

Hợp đồng nullability có thể được công cụ tĩnh đọc ở nhiều nơi, nhưng kiểm tra runtime chỉ xuất hiện tại nơi framework/guard thực sự chạy.

```text
Caller
  → repository proxy có hỗ trợ validation
      → kiểm tra đầu vào theo hợp đồng
      → thực thi query
      → xử lý kiểu kết quả
      → kiểm tra kết quả theo hợp đồng
  → caller nhận giá trị hoặc exception
```

Một đối tượng mock, một implementation được tạo trực tiếp hoặc một phương thức helper không tự có toàn bộ hành vi của repository proxy.

Nếu muốn kiểm chứng runtime của Spring Data, cần gọi repository do hạ tầng tương ứng tạo. Một mock được lập trình trả null chỉ kiểm tra cách caller xử lý null, không chứng minh repository thật có bật validation.

### 6.1. Lỗi runtime không phải lúc nào cũng là NullPointerException

Nên phân biệt:

| Nguồn lỗi | Exception/hành vi tiêu biểu |
|---|---|
| Dereference giá trị null trong Java | `NullPointerException` |
| Guard `Objects.requireNonNull` | `NullPointerException` tại guard |
| Repository từ chối đầu vào non-null bị truyền null | `IllegalArgumentException` trong cấu hình hỗ trợ |
| Query không đáp ứng kết quả non-null | `EmptyResultDataAccessException` trong cơ chế tương ứng |
| Bean Validation phát hiện ràng buộc | Violation hoặc exception do cơ chế validation đang dùng |
| Database từ chối null | Lỗi ràng buộc dữ liệu, có thể được module dịch thành data access exception |

Một exception xảy ra sớm ở ranh giới thường giúp tìm nguyên nhân hơn so với chờ tới một dòng dereference ở xa, nhưng phải biết cơ chế nào đã tạo exception để chẩn đoán đúng.

## 7. Guard tường minh, Bean Validation và database

### 7.1. Guard tường minh kiểm tra ngay khi chạy

```java
import java.util.Objects;

public Customer loadRequired(String email) {
    Objects.requireNonNull(email, "email must not be null");

    return repository.getByEmail(email);
}
```

Guard này hoạt động khi dòng mã được thực thi, không phụ thuộc repository proxy có hiểu một annotation nullability cụ thể hay không.

Nó vẫn không kiểm tra email rỗng, định dạng email, sự tồn tại của bản ghi hoặc mọi trường của kết quả.

Một số công cụ phân tích hiểu `requireNonNull` như thông tin giúp thu hẹp giá trị sau kiểm tra. Đó là khả năng của công cụ, bên cạnh hành vi runtime thật của Java.

### 7.2. Bean Validation cần được kích hoạt

Ví dụ DTO sử dụng namespace Jakarta Validation:

```java
import jakarta.validation.constraints.NotNull;

public record RegisterCustomerRequest(
    @NotNull String email
) {
}
```

Chỉ gọi:

```java
RegisterCustomerRequest request =
    new RegisterCustomerRequest(null);
```

không tự buộc constructor chạy Bean Validation. Record vẫn có thể được tạo nếu không có guard riêng hoặc cơ chế validation khác tại ranh giới.

Với một `Validator` đã được cấu hình và có provider phù hợp:

```java
var violations = validator.validate(request);
```

validation engine mới đánh giá những ràng buộc liên quan.

Framework có thể kích hoạt validation cho request hoặc method invocation khi được cấu hình thích hợp, chẳng hạn qua cơ chế `@Valid`/`@Validated`. Điều này không đồng nghĩa mọi phương thức repository tự động chạy toàn bộ Bean Validation.

`@NotNull` chỉ nói không null. Chuỗi rỗng hoặc chỉ có khoảng trắng cần ràng buộc khác nếu nghiệp vụ không cho phép, chẳng hạn `@NotBlank` với validation engine hỗ trợ.

### 7.3. Database bảo vệ dữ liệu lưu trữ

Ràng buộc `NOT NULL` trong schema có thể từ chối việc lưu null vào cột. Nó không khiến compiler Java từ chối `repository.findByEmail(null)`.

Tương tự, metadata mapping như `@Column(nullable = false)` trong JPA không phải một annotation nullness chung cho IDE. Tác dụng về schema hoặc kiểm tra persistence còn phụ thuộc provider, cấu hình và schema thực tế.

Có thể đến lúc flush hoặc commit mới xuất hiện lỗi dữ liệu. Không xem việc chưa có lỗi tại lời gọi `save` là bằng chứng mọi ràng buộc database đã được kiểm tra xong.

### 7.4. Mỗi lớp bảo vệ một hợp đồng

```text
Static checker:
  mã nguồn có dùng giá trị nullable sai cách không?

Repository runtime:
  lời gọi/kết quả có vi phạm hợp đồng được hỗ trợ không?

Bean Validation:
  đối tượng hoặc tham số có thỏa các constraint được kích hoạt không?

Database:
  dữ liệu được ghi có thỏa schema thực tế không?
```

Dùng các lớp này có chủ đích giúp lỗi được phát hiện tại ranh giới phù hợp, thay vì chờ một lớp khác xử lý thay.

## 8. Hỗ trợ IDE: nhanh, hữu ích nhưng cần thống nhất với build

IDE có thể:

- Hiển thị cảnh báo khi truyền null vào tham số non-null.
- Cảnh báo dereference một kết quả nullable.
- Gợi ý kiểm tra null hoặc dùng `Optional`.
- Theo dõi một số nhánh điều khiển để biết giá trị đã được kiểm tra.
- Đọc annotation từ API của dependency nếu hệ annotation được hỗ trợ.

Nhưng cảnh báo IDE phụ thuộc phiên bản IDE, inspection profile và cách project được import.

### 8.1. Ba cấu hình dễ lệch nhau

| Cấu hình | Kết quả có thể thấy | Điều cần sửa |
|---|---|---|
| IDE hiểu annotation, CI không có checker | Editor cảnh báo nhưng build thành công | Bổ sung hoặc xác định rõ chính sách kiểm tra trong build |
| CI có checker, IDE chưa tích hợp tương ứng | Lỗi chỉ xuất hiện khi build | Cấu hình IDE hiểu cùng hợp đồng để phản hồi sớm |
| Hai nơi hiểu hai hệ annotation khác nhau | Cảnh báo thiếu hoặc mâu thuẫn | Thống nhất hệ annotation và phạm vi được phân tích |

Không nên giải quyết mọi khác biệt bằng cách tắt inspection. Trước hết xem annotation nào đang được đọc và cấu hình build nào thực sự chạy.

### 8.2. Gợi ý tự động của IDE cần được đọc lại

Nếu IDE gợi ý thêm `@Nullable` hoặc `@NotNull`, hãy xem import đầy đủ. Một annotation có thể làm IDE hiểu hợp đồng nhưng framework runtime không đọc nó theo cách mong muốn.

Đừng chỉ nhìn tên ngắn trong source code rồi kết luận hợp đồng của project đã nhất quán.

### 8.3. Unknown nullness không phải non-null

Một API dependency chưa có metadata nullability có thể được công cụ xem như chưa xác định. Tùy checker và mức nghiêm ngặt, mã gọi API đó có thể nhận ít cảnh báo hơn.

Không lấy sự im lặng của công cụ làm một hợp đồng non-null mới. Nếu cần, xác định hợp đồng tại lớp adapter và kiểm tra dữ liệu ở ranh giới, hoặc sử dụng cơ chế bổ sung metadata mà công cụ của dự án hỗ trợ.

## 9. Thiết lập kiểm tra trong build và CI

Mục tiêu là để nhóm biết chính xác loại lỗi nào làm build thất bại.

### 9.1. Xác định bốn quyết định

1. **Hệ annotation:** public API và mã nội bộ dùng hợp đồng nào.
2. **Công cụ:** checker nào hiểu hệ annotation đó, trên phiên bản nào.
3. **Phạm vi:** source, test, generated code và dependency nào được phân tích.
4. **Mức chẩn đoán:** lỗi nullness nào là warning, lỗi nào khiến build thất bại.

Không có một dependency annotation đơn lẻ thay thế được bốn quyết định này.

### 9.2. Đồng bộ default trước khi thêm nhiều annotation cục bộ

Nếu một package đã có default non-null phù hợp, các ngoại lệ nullable nên được khai báo rõ. Nếu package chưa có default, không mặc định kiểu Java không có annotation đã mang cùng nghĩa.

Cần chú ý:

- Package con có cấu hình riêng.
- Một interface công khai có thể được caller ở module khác sử dụng.
- Dependency có thể dùng hệ annotation khác.
- Generated code có thể chưa biểu diễn đúng hợp đồng.
- Suppression hoặc cấu hình loại trừ có thể che một vùng mã đáng lẽ cần kiểm tra.

Chỉ đặt default khi hợp đồng thực sự đúng. Đánh dấu cả package non-null rồi để implementation trả null là mô tả sai, không phải tăng an toàn.

### 9.3. Xác nhận bằng một vi phạm có chủ đích

Trong một dự án cần chứng minh checker đã hoạt động, có thể dùng một fixture nhỏ chứa vi phạm đã biết, chẳng hạn dereference kết quả nullable. Kết quả mong đợi phải được ghi rõ: warning hay build failure.

Không đặt mã cố ý không biên dịch được vào source/test bình thường rồi kỳ vọng test runtime sẽ chạy. Những kiểm tra kiểu này cần cơ chế compile-test hoặc fixture riêng phù hợp.

Đây là kiểm chứng cấu hình công cụ. Nó khác với integration test kiểm tra repository proxy có từ chối một lời gọi thật hay không.

### 9.4. Suppression cần có lý do tại đúng ranh giới

Một suppression có thể cần khi checker không biểu diễn được một bất biến đã được kiểm tra. Nó không nên thay thế hợp đồng thiếu hoặc guard chưa có.

Trước khi bỏ cảnh báo, hãy tự hỏi:

- Giá trị được bảo đảm non-null bởi đoạn mã nào?
- Bảo đảm đó còn đúng khi API được gọi từ module khác không?
- Có thể diễn đạt lại bằng kiểm tra tường minh hoặc hợp đồng rõ hơn không?
- Việc refactor có dễ làm giả định này sai không?

Không dùng suppression toàn project để làm một lần build xanh mà không hiểu cảnh báo.

## 10. Kotlin: kiểu nullable giúp compiler kiểm tra mạnh hơn

Kotlin có thể biểu diễn nullable ngay trong kiểu:

```kotlin
interface KotlinCustomerRepository : Repository<Customer, Long> {
    fun findByEmail(email: String): Customer?

    fun getByEmail(email: String): Customer
}
```

Ví dụ giả định domain, repository scanning và module hỗ trợ các phương thức này.

Ý nghĩa:

- Cả hai tham số `email: String` không cho phép null theo kiểu Kotlin.
- `findByEmail` cho phép không có khách hàng.
- `getByEmail` cam kết có khách hàng theo hợp đồng kết quả.

Caller phải xử lý kết quả nullable:

```kotlin
val customer: Customer? = repository.findByEmail(email)
val id = customer?.id
```

Gọi trực tiếp `customer.id` trên biến nullable có thể bị compiler từ chối nếu chưa có bằng chứng non-null phù hợp.

### 10.1. Java interop vẫn có vùng chưa xác định

Khi gọi API Java thiếu nullability metadata được compiler hiểu, Kotlin có thể nhìn thấy platform type. Ký hiệu như `Customer!` là cách mô tả platform type trong thông tin công cụ, không phải cú pháp để tự khai báo trong source Kotlin.

Mức xử lý annotation Java có thể phụ thuộc hệ annotation, phiên bản compiler và chế độ cấu hình. Không mặc định mọi annotation có tên `Nullable` đều tạo ra cùng một kiểu Kotlin.

Toán tử `!!` chuyển giả định non-null thành một assertion có thể thất bại ở runtime. Nó không làm dữ liệu nullable thực sự trở nên an toàn.

### 10.2. Runtime cần framework đọc được hợp đồng Kotlin

Compiler Kotlin bảo vệ những lời gọi được nó phân tích, nhưng framework còn phải đọc được metadata Kotlin để kiểm tra hợp đồng tại runtime theo khả năng của phiên bản sử dụng.

Các cấu hình Spring Data dựa vào Kotlin reflection cần dependency `kotlin-reflect` phù hợp. Cần xem yêu cầu của phiên bản dự án, không suy từ việc Kotlin source đã biên dịch rằng runtime validation của repository chắc chắn hoạt động.

Lời gọi từ Java, reflection hoặc framework có thể đi qua những ranh giới mà kiểm tra source Kotlin không bao phủ hoàn toàn.

## 11. Kiểm chứng từng lớp bằng tình huống riêng

| Tình huống | Lớp được kiểm chứng | Kết quả cần quan sát |
|---|---|---|
| Source dereference kết quả được khai báo nullable | Checker/IDE | Chẩn đoán đúng theo mức đã cấu hình |
| Truyền null tới tham số repository non-null qua ranh giới động | Runtime repository | Lời gọi bị từ chối nếu cơ chế tương ứng được bật |
| Không có bản ghi cho kết quả bắt buộc non-null | Runtime và hợp đồng kết quả | Exception theo cơ chế nullability/cardinality của module |
| Không có bản ghi cho kết quả nullable | Repository | Giá trị null được phép |
| Không có bản ghi cho `Optional` | Repository | Wrapper rỗng theo kiểu được hỗ trợ |
| Không có phần tử cho query collection | Repository | Collection rỗng, không phải null container |
| DTO vi phạm `@NotNull` được đưa qua validator | Bean Validation | Có violation theo constraint |
| Ghi null vào cột có ràng buộc thực tế | Database/persistence | Thất bại tại thời điểm áp dụng ràng buộc |

Một bài test chỉ kiểm tra `Optional.empty()` không xác nhận IDE đã hiểu annotation. Một bài compile-test thành công cũng không xác nhận database có cột `NOT NULL`.

### 11.1. Dữ liệu biên phải đúng với hợp đồng đang kiểm tra

Nên phân biệt:

- Không có bản ghi.
- Có bản ghi nhưng một thuộc tính là null.
- Có nhiều bản ghi trong một query đơn kết quả.
- Collection kết quả rỗng.
- Container hoặc phần tử vi phạm hợp đồng.
- Giá trị null được phép ở đầu vào nhưng có ngữ nghĩa truy vấn đặc thù.

Những trường hợp này dễ bị gộp thành “test null”, trong khi chúng đi qua các cơ chế khác nhau.

### 11.2. Không suy ra kiểm tra runtime từ một mock

Nếu mock được cấu hình trả `null` cho phương thức non-null, kết quả đó chỉ phản ánh hành vi mock. Nó không chứng minh repository thật sẽ trả null theo cùng cách.

Muốn kiểm chứng guard/proxy của framework, phải dùng hạ tầng tương ứng. Muốn kiểm chứng phản ứng của service khi nhận dữ liệu bất thường, mock lại có thể hữu ích. Hai mục tiêu cần được đặt tên rõ.

## 12. Chẩn đoán khi các lớp kiểm tra không khớp nhau

| Hiện tượng | Nguyên nhân cần xem | Hướng xử lý |
|---|---|---|
| Có annotation nhưng javac vẫn chấp nhận mã nguy hiểm | Chỉ thêm metadata, chưa có checker | Xác định công cụ phân tích và cấu hình build |
| IDE cảnh báo nhưng CI xanh | Inspection không tương đương build | Đồng bộ chính sách hoặc ghi rõ giới hạn |
| CI báo lỗi mà IDE không báo | IDE không hiểu cùng hệ/configuration | Cập nhật cấu hình import project và inspection |
| Package đã non-null nhưng repository vẫn chưa như kỳ vọng | Annotation đặt nhầm package hoặc sai hệ | Kiểm tra package khai báo thật, import và hỗ trợ phiên bản |
| `@Nullable` trên kết quả nhưng null input bị từ chối | Kết quả và tham số là hai vị trí khác nhau | Khai báo đúng ngoại lệ cho từng vị trí |
| List non-null nhưng đọc phần tử bị lỗi | Hợp đồng container không kiểm tra object graph | Xem phần tử, projection và thuộc tính bên trong |
| Không có bản ghi gây exception | Phương thức cam kết kết quả non-null | Chọn nullable hoặc `Optional` nếu vắng dữ liệu là hợp lệ |
| Đã có `@NotNull` nhưng đối tượng vẫn chứa null | Validation chưa được kích hoạt | Kiểm tra ranh giới validator hoặc guard |
| Database lỗi sau lời gọi save | Constraint có thể được áp dụng lúc flush/commit | Xem thời điểm persistence thực sự ghi dữ liệu |
| Kotlin vẫn gặp null ở runtime | Java interop, assertion hoặc metadata không được hiểu đầy đủ | Xác định ranh giới và cơ chế runtime |

### 12.1. Đọc vị trí lỗi trước khi thêm annotation

Nếu lỗi xảy ra ở `customer.getEmail().trim()`, cần xác định đối tượng nào null:

- `customer` null vì không có bản ghi.
- `getEmail()` trả null dù khách hàng tồn tại.
- Một lớp adapter đã chuyển kết quả sang null.
- Hợp đồng không được thực thi tại ranh giới đang sử dụng.

Thêm annotation non-null vào `getEmail()` khi dữ liệu thực tế vẫn có null chỉ làm metadata sai. Cần xử lý dữ liệu hoặc thay đổi hợp đồng và implementation.

### 12.2. Không dùng cùng một chính sách cho mọi sự vắng dữ liệu

Một query tìm kiếm không có kết quả thường là tình huống bình thường. Một query phục vụ bất biến “bản ghi bắt buộc phải tồn tại” có thể xem sự vắng dữ liệu là lỗi.

Hai phương thức có thể truy vấn cùng bảng nhưng cần kiểu kết quả khác nhau. Chọn hợp đồng theo use case giúp caller xử lý đúng, thay vì phụ thuộc một `NullPointerException` phát sinh ngẫu nhiên.

## 13. Thiết kế một luồng đọc có hợp đồng rõ

Giả sử API tìm khách hàng theo email. Cần quyết định từng ranh giới:

| Ranh giới | Quyết định cần làm rõ |
|---|---|
| Request | Email bắt buộc, tùy chọn hay có thể là chuỗi trống? |
| Service | Null input bị từ chối bằng guard/validation hay được phép theo nghiệp vụ? |
| Repository | Không có khách hàng được biểu diễn bằng null, `Optional.empty()` hay exception? |
| Domain | Khách hàng tồn tại có chắc email và các thuộc tính cần dùng đều có giá trị không? |
| DTO | Trường nào có thể null trong kết quả công khai? |
| Caller | Phải xử lý trường hợp vắng dữ liệu ở đâu? |

Một lựa chọn thường rõ nghĩa là dùng `Optional<Customer>` cho việc tìm một khách hàng có thể không tồn tại, rồi để service quyết định trường hợp vắng dữ liệu.

Tuy nhiên, lựa chọn này chưa tự giải quyết:

- Input null.
- Hai khách hàng cùng khớp email.
- Một khách hàng có thuộc tính email null.
- Việc checker hiểu hệ annotation hay không.
- Những ràng buộc nghiệp vụ khác.

Nếu service nhận `Optional.empty()`, có thể chuyển thành một phản hồi “không tìm thấy” theo hợp đồng ứng dụng. Nếu có khách hàng nhưng thiếu một trường mà DTO bắt buộc, đó là vấn đề khác với “không có khách hàng”.

Không chuyển mọi trường hợp thành null để đơn giản hóa chữ ký. Việc đó làm mất thông tin cần thiết để caller phân biệt các trạng thái.

### 13.1. Khi chuyển đổi hệ annotation

Một dự án có thể cần chuyển từ hệ annotation cũ sang hệ phù hợp với phiên bản thư viện mới. Không chỉ đổi import bằng tìm-thay thế.

Cần xem lại:

- Default được đặt ở package, type hay phạm vi nào.
- Annotation áp dụng trên declaration hay type-use.
- Generic element nullness có thay đổi ý nghĩa không.
- Checker và IDE nhận diện hợp đồng mới thế nào.
- Runtime framework còn kiểm tra cùng những ràng buộc không.
- Các module Java/Kotlin nhìn thấy hợp đồng public API ra sao.

Mục tiêu là giữ đúng ý nghĩa của API. Việc mã vẫn biên dịch chưa chứng minh runtime validation và cảnh báo công cụ vẫn như cũ.

## 14. Bài tập vận dụng

### Bài tập 1: Có annotation nhưng build vẫn thành công

Một phương thức được đánh dấu nullable. Caller dereference kết quả ngay. IDE cảnh báo, nhưng build Java vẫn thành công. Có mâu thuẫn không?

**Gợi ý lời giải:** Không. IDE có thể chạy inspection riêng trong khi build chưa tích hợp checker hoặc chỉ xem chẩn đoán là warning. Annotation không tự buộc javac thực thi hệ kiểu non-null.

### Bài tập 2: Chọn cách biểu diễn không có kết quả

Trong cấu hình repository hỗ trợ runtime nullability của hệ Spring, so sánh:

```java
Customer getByEmail(String email);

@Nullable
Customer findCustomerByEmail(String email);

Optional<Customer> findOptionalByEmail(String email);
```

Giả sử default non-null được khai báo đúng package. Điều gì khác nhau khi không có bản ghi?

**Gợi ý lời giải:** Phương thức đầu không đáp ứng hợp đồng kết quả bắt buộc và có thể dẫn tới `EmptyResultDataAccessException`. Phương thức thứ hai được phép trả null. Phương thức thứ ba dùng wrapper rỗng theo hợp đồng được hỗ trợ. Cả ba vẫn cần xử lý trường hợp query trả quá nhiều bản ghi.

### Bài tập 3: List và phần tử

Trong phạm vi JSpecify đã đánh dấu non-null, hai kiểu sau khác gì?

```java
@Nullable List<Customer> first;
List<@Nullable Customer> second;
```

**Gợi ý lời giải:** `first` cho phép container null. `second` giữ container non-null nhưng cho phép phần tử null. Công cụ phải hiểu type-use và default tương ứng; không suy rằng runtime sẽ tự duyệt list để kiểm tra.

### Bài tập 4: Constraint trên record

Một record có component `@NotNull String email`. Gọi constructor trực tiếp với null có chắc ném lỗi validation không?

**Gợi ý lời giải:** Không. Bean Validation cần một validation engine được kích hoạt tại ranh giới hoặc được gọi tường minh. Constructor chỉ tự từ chối nếu có kiểm tra khác thực sự chạy, chẳng hạn guard trong constructor.

### Bài tập 5: Package con

Annotation default đặt trên `example.customer`. Repository nằm ở `example.customer.repository`. Có nên mặc định repository đã nhận cùng default không?

**Gợi ý lời giải:** Không. Package con là package riêng. Cần đặt hoặc xác định default đúng phạm vi mà hệ annotation và framework sử dụng, rồi kiểm chứng cấu hình.

### Bài tập 6: Nullable parameter và bộ lọc tùy chọn

Một phương thức nhận email nullable. Caller truyền null và mong query bỏ qua điều kiện email. Hợp đồng nullable có bảo đảm điều đó không?

**Gợi ý lời giải:** Không. Nó chỉ cho phép đầu vào null. Ngữ nghĩa query còn phụ thuộc module và toán tử; nếu cần bộ lọc tùy chọn, phải thiết kế điều kiện đó tường minh.

### Bài tập 7: Kotlin và runtime

Compiler Kotlin đã từ chối lời gọi với null trong source Kotlin. Có thể bỏ mọi kiểm tra runtime tại ranh giới public API không?

**Gợi ý lời giải:** Không nên suy như vậy. Java interop, reflection, framework hoặc dữ liệu ngoài vẫn có thể vượt khỏi phần mã đã được kiểm tra. Cần xác định ranh giới nào thực sự cần runtime validation và hạ tầng có đọc được hợp đồng Kotlin không.

## 15. Những điều cần ghi nhớ

- Java compiler thông thường, nullness checker và IDE inspection là các cơ chế khác nhau.
- Annotation mô tả hợp đồng; phải có công cụ hoặc framework đọc nó để tạo chẩn đoán hay kiểm tra.
- JSpecify, annotation Spring và Bean Validation không thể đổi chỗ chỉ dựa vào tên ngắn.
- Runtime repository chỉ thực thi những ràng buộc mà phiên bản, hệ annotation và proxy tương ứng hỗ trợ.
- Container non-null khác phần tử non-null; đối tượng non-null khác mọi thuộc tính đều có dữ liệu.
- `Optional.empty()`, collection rỗng, kết quả nullable và kết quả bắt buộc là những hợp đồng khác nhau.
- Null input được phép không tự có nghĩa là query bỏ qua điều kiện.
- Kiểm chứng riêng build, IDE, repository runtime, validation và database để biết mỗi lớp đang bảo vệ điều gì.
