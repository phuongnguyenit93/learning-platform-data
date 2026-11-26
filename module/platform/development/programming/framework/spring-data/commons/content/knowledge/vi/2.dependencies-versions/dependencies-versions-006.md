# Phân biệt tài liệu, API hiện hành và API của phiên bản đang dùng

## 1. Vì sao một ví dụ đúng vẫn có thể không dùng được?

Bạn tìm thấy một ví dụ Spring Data, chép đúng import và chữ ký phương thức, nhưng IDE vẫn báo không tồn tại lớp hoặc phương thức. Trong một tình huống khác, code biên dịch thành công nhưng ứng dụng gặp lỗi khi chạy.

Nguyên nhân có thể nằm ở việc đang đối chiếu những phiên bản khác nhau:

- Tài liệu được viết cho một phiên bản hoặc một dòng phát hành nhất định.
- Trang được gắn nhãn `current` hay `latest` có thể trỏ tới phiên bản khác với dự án.
- Dependency thực tế được chọn khi build có thể khác version ghi ở một nơi trong cấu hình.
- Thư viện xuất hiện khi chạy có thể khác thư viện mà IDE hoặc compiler đã sử dụng.

Với **SPRING_DATA_COMMONS**, sự khác biệt này ảnh hưởng trực tiếp đến repository, CRUD, phân trang, sắp xếp, projection, Query by Example, metadata và auditing. Cùng một tên abstraction không có nghĩa hợp đồng và cách sử dụng của nó bất biến qua mọi dòng phiên bản.

Mục tiêu của bài là hình thành một quy trình đối chiếu: xác định thư viện thực tế, chọn tài liệu tương ứng, kiểm tra hợp đồng API, rồi xác minh khả năng của store module.

## 2. Phân biệt ba đối tượng thường bị gọi chung là “API”

### 2.1. Tài liệu là phần mô tả có phạm vi phiên bản

“Tài liệu Spring Data” có thể chỉ nhiều loại nội dung:

| Loại tài liệu | Câu hỏi nó thường trả lời tốt |
| --- | --- |
| Reference documentation | Tính năng hoạt động theo mô hình nào, cấu hình và giới hạn ra sao? |
| API documentation, thường là Javadoc | Kiểu, phương thức, generic, tham số và hợp đồng cụ thể là gì? |
| Release notes | Phiên bản bổ sung, thay đổi hoặc sửa điều gì? |
| Migration guide | Cần điều chỉnh những gì khi chuyển từ dòng cũ sang dòng mới? |
| Source code và source JAR | Implementation của đúng bản thư viện thực hiện như thế nào? |
| Bài hướng dẫn hoặc ví dụ | Làm một tình huống cụ thể bằng tập dependency mà ví dụ lựa chọn |

Không có loại nào thay thế hoàn toàn các loại còn lại. Một reference guide có thể chủ ý bỏ qua import và chi tiết generic; Javadoc có thể không trình bày toàn bộ cấu hình store; source code của một nhánh phát triển có thể chưa tương ứng với artifact đã phát hành.

Trước khi làm theo một trang, cần biết ít nhất **module** và **version** mà trang đó mô tả.

### 2.2. API hiện hành là một mốc tham chiếu có thể dịch chuyển

Trong hội thoại, “API hiện hành” thường chỉ API của phiên bản đang được công bố hoặc được trang tài liệu mặc định chọn. Nó không tự mang nghĩa “API mà dự án của bạn đang sử dụng”.

Các nhãn `current`, `latest`, `stable` hoặc `snapshot` cần được đọc cùng thông tin phiên bản cụ thể:

- `current` và `latest` là nhãn có thể đổi đích theo thời gian.
- `stable` cho biết trạng thái phát hành theo cách tổ chức của nguồn tài liệu; vẫn cần xem số phiên bản.
- `snapshot` mô tả bản phát triển, có thể thay đổi trước khi phát hành.
- Một số phiên bản cụ thể vẫn có thể là trang cập nhật theo cả dòng bảo trì, thay vì cố định từng bản vá.

Lưu một liên kết có chữ “current” chưa đủ để tái hiện chính xác kiến thức tại thời điểm đã đọc.

Bài này không cần chốt một con số là “mới nhất”. Các mốc phiên bản nêu trong ví dụ là mốc lịch sử để minh họa cách đọc thay đổi API.

### 2.3. API của phiên bản đang dùng là hợp đồng từ dependency thực tế

Đối với việc biên dịch, API có thể sử dụng được xác định bởi các artifact trên compile classpath hoặc module path của dự án.

Đối với việc thực thi, các kiểu và phương thức được nạp phải tương thích với thư viện trên runtime classpath hoặc module path.

Vì vậy, có hai câu hỏi tách biệt:

1. Compiler nhìn thấy phiên bản nào?
2. Tiến trình chạy ứng dụng thực sự nạp phiên bản nào?

Trong một build được quản lý nhất quán, hai phần này thường tương thích. Nhưng cấu hình đóng gói, môi trường triển khai, dependency exclusion hoặc việc đưa JAR thủ công có thể làm chúng lệch nhau.

Tài liệu không thay đổi bytecode mà ứng dụng đang có. Việc một phương thức xuất hiện trên trang mới không làm nó xuất hiện trong một JAR cũ.

## 3. Xác định đúng phạm vi trước khi tra cứu

### 3.1. Tên hệ sinh thái chưa đủ để định danh API

Một ứng dụng có thể đồng thời sử dụng:

| Thành phần | Ví dụ định danh | Vai trò trong việc đối chiếu |
| --- | --- | --- |
| Spring Boot | Parent hoặc BOM của Boot | Có thể quản lý tập phiên bản dependency |
| Spring Data BOM | `org.springframework.data:spring-data-bom` | Quản lý các phiên bản module Spring Data |
| Spring Data Commons | `org.springframework.data:spring-data-commons` | Hợp đồng và hạ tầng dùng chung |
| Store module | `spring-data-jpa`, `spring-data-mongodb` | API và khả năng thực thi dành cho store |
| Spring Framework | Các artifact `spring-*` tương ứng | Hạ tầng mà các thành phần dựa vào |
| Java | JDK dùng để biên dịch và môi trường chạy | API ngôn ngữ, thư viện chuẩn và yêu cầu nền tảng |

Không suy số phiên bản Commons trực tiếp từ số phiên bản Boot. Cũng không mặc định số phiên bản của BOM chính là số phiên bản mọi artifact được BOM quản lý.

Dependency management giúp phối hợp một tập phiên bản; nó không khiến tất cả thư viện có cùng số version.

### 3.2. Package cho biết nên bắt đầu ở đâu

| Kiểu hoặc API | Nguồn cần xem trước |
| --- | --- |
| `CrudRepository`, `Pageable`, `ExampleMatcher` | Spring Data Commons |
| `JpaRepository`, `JpaSpecificationExecutor` | Spring Data JPA |
| `MongoRepository`, `MongoTemplate` | Spring Data MongoDB |
| `EntityManager`, `@Entity` | API Jakarta Persistence hoặc API tương ứng với dòng đang dùng |
| `@Transactional` của Spring | Spring Framework |
| `Optional`, `UUID`, `BigDecimal` | API Java của JDK tương ứng |

Một phương thức được thấy khi sử dụng `JpaRepository` có thể là phương thức kế thừa từ interface của Commons. Vì vậy, cần xem cả cây kế thừa, không chỉ trang Javadoc của interface cuối cùng.

Ngược lại, một tính năng có trong Spring Data JPA không tự trở thành tính năng của mọi repository Commons hoặc mọi store khác.

### 3.3. Phân biệt version khai báo và version được chọn

Trong dự án dùng Boot, dependency có thể không ghi version trực tiếp:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
```

Đoạn XML này giả định dự án đã có dependency management phù hợp. Nó không cho biết ngay số phiên bản của Commons.

Commons có thể đi vào dự án qua dependency bắc cầu của store module. Version được chọn còn chịu ảnh hưởng của parent, BOM, khai báo trực tiếp, profile và cơ chế giải quyết dependency của công cụ build.

Các nguồn bằng chứng hữu ích:

- Dependency graph đã resolve.
- Effective configuration của build.
- Thông tin artifact mà IDE gắn cho lớp đang mở.
- Dependency và JAR trong gói ứng dụng thực tế.
- Thông tin lớp được nạp khi cần điều tra lệch runtime.

Với một dự án Maven, có thể dùng:

```shell
mvn dependency:tree "-Dincludes=org.springframework.data"
```

Lệnh giúp nhìn thấy các dependency Spring Data trong cây đã giải quyết. Khi nghi có xung đột, xem thêm thông tin dependency bị loại hoặc được thay thế bằng tùy chọn phù hợp của plugin đang dùng; không chỉ đọc một dòng khai báo trong POM.

Effective POM giúp hiểu cấu hình đã hợp nhất, còn dependency tree giúp hiểu artifact được chọn. Hai cách nhìn này bổ sung cho nhau.

Không cần ghi đè version Commons chỉ để làm cho tên trong tài liệu xuất hiện. Trước hết phải biết dự án đang dùng tập dependency nào.

## 4. Chọn đúng tài liệu cho một câu hỏi cụ thể

### 4.1. Dùng reference guide để hiểu hành vi

Ví dụ bạn muốn hiểu khác nhau giữa `Page<T>` và `Slice<T>`. Reference guide của đúng dòng Spring Data giúp giải thích mục đích, cách phân trang và chi phí có thể phát sinh.

Sau đó xem tài liệu store để biết truy vấn đang dùng có hỗ trợ kiểu trả về đó và có giới hạn gì.

Một reference guide của Commons mô tả abstraction chung; phần mô tả đó chưa chứng minh mọi loại truy vấn của mọi store đều hỗ trợ mọi cách kết hợp.

### 4.2. Dùng Javadoc để chốt hợp đồng chính xác

Khi cần viết code, kiểm tra:

1. Fully qualified class name.
2. Interface hoặc superclass mà kiểu đó kế thừa.
3. Chữ ký đầy đủ của phương thức.
4. Kiểu generic và kiểu trả về.
5. Tham số bắt buộc, khả năng nhận null và exception được mô tả.
6. Các ghi chú như `Since`, deprecated hoặc liên kết đến API thay thế.

`Since` giúp nhận diện thời điểm một API được bổ sung, nhưng không phải mọi phần tài liệu đều có ghi chú này. Việc không thấy `Since` không chứng minh API tồn tại từ mọi phiên bản trước đó.

Cũng cần chú ý overload: hai phương thức cùng tên có thể nhận tham số và mang hợp đồng khác nhau. Không chỉ tìm chuỗi tên phương thức rồi dừng lại.

### 4.3. Dùng migration guide khi đổi dòng phiên bản

Một thay đổi có thể không nằm ở việc thêm hoặc xóa method. Nó có thể nằm ở:

- Quan hệ kế thừa giữa các interface.
- Gói annotation hoặc kiểu nền tảng.
- Yêu cầu về Java hay Spring Framework.
- Mặc định cấu hình.
- Cơ chế phát hiện repository.
- Hành vi chuyển đổi, nullability hoặc truy vấn.

Release notes cho biết điều đã thay đổi; migration guide giúp xác định việc cần làm trong dự án. Khi nâng qua nhiều dòng, cần xem các thay đổi liên quan trên toàn bộ chặng nâng cấp, thay vì chỉ so trang đầu và trang cuối.

### 4.4. Dùng source đúng bản phát hành

Source trên nhánh `main` mô tả trạng thái phát triển của nhánh đó. Nó có thể khác JAR đã phát hành và khác dependency của dự án.

Nếu cần xem implementation, ưu tiên source JAR gắn với artifact đang sử dụng hoặc source ở tag/commit tương ứng với bản phát hành. Sau đó mới so sánh với phiên bản khác để hiểu thay đổi.

Implementation là bằng chứng về cách một bản thư viện thực hiện công việc. Những chi tiết nội bộ không được cam kết trong hợp đồng công khai có thể thay đổi; không nên xây logic ứng dụng dựa vào một chi tiết tình cờ quan sát được.

## 5. Ví dụ 1: tài liệu có ListCrudRepository, dự án chưa có

### 5.1. Tình huống

Một ví dụ sử dụng:

```java
import java.util.UUID;

import org.springframework.data.repository.ListCrudRepository;

public interface ProductRepository
        extends ListCrudRepository<Product, UUID> {
}
```

Nhưng dependency thực tế của dự án thuộc dòng Commons 2.7. IDE báo không tìm được `ListCrudRepository`.

Đây là một khác biệt phiên bản có thể giải thích được: `ListCrudRepository` được bổ sung từ dòng 3.0. Một tài liệu mô tả API có interface này không phải bằng chứng rằng JAR 2.7 chứa nó.

Các số 2.7 và 3.0 ở đây phục vụ so sánh một thay đổi lịch sử, không phải khuyến nghị chọn một trong hai làm nền tảng mới.

### 5.2. Nếu mục tiêu là giữ dòng dependency hiện tại

Sử dụng hợp đồng có trong phiên bản đang dùng:

```java
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, UUID> {
}
```

Với `CrudRepository`, `findAll()` trả `Iterable<Product>`. Nếu người gọi cần `List`, có thể chuyển đổi tường minh:

```java
import java.util.ArrayList;
import java.util.List;

List<Product> result = new ArrayList<>();
products.findAll().forEach(result::add);
```

Đoạn code giả định `products` là repository bean được cấu hình cho một store. Không ép kiểu `Iterable` thành `List` vì implementation có thể không trả về một `List`.

Phép chuyển đổi này tải toàn bộ kết quả vào danh sách. Nó không thay thế phân trang khi tập dữ liệu lớn.

### 5.3. Nếu mục tiêu là dùng API mới

Đánh giá nâng cấp cả tập dependency và nền tảng có liên quan:

- Dòng Spring Boot, nếu dự án dùng Boot.
- Spring Data BOM và store module.
- Spring Framework.
- Java, persistence API, driver hoặc provider tương ứng.
- Những thay đổi được migration guide yêu cầu.

Không coi việc thêm một version Commons mới trực tiếp vào POM là toàn bộ quá trình nâng cấp. Nó có thể giải quyết lỗi “không tìm thấy interface” nhưng tạo ra tập thư viện không tương thích.

Quyết định cần dựa trên nhu cầu dự án: giữ hợp đồng cũ có thể đủ; dùng tính năng mới có thể cần một lần nâng cấp có phạm vi rõ ràng.

## 6. Ví dụ 2: cùng tên interface, quan hệ kế thừa thay đổi

### 6.1. Giả định ngầm trong code cũ

Một repository chỉ khai báo:

```java
import java.util.UUID;

import org.springframework.data.repository.PagingAndSortingRepository;

public interface ProductRepository
        extends PagingAndSortingRepository<Product, UUID> {
}
```

Trong dòng 2.7, `PagingAndSortingRepository` kế thừa `CrudRepository`. Người gọi vì vậy có thể sử dụng cả nhóm CRUD qua hợp đồng này.

Từ dòng 3.0, các interface sắp xếp tương ứng không còn tự kế thừa nhóm CRUD theo cách đó. Nếu chỉ nhìn tên interface, bạn có thể tưởng code vẫn có toàn bộ phương thức cũ.

Ví dụ, lời gọi:

```java
products.findById(productId);
```

có thể không còn biên dịch với khai báo repository chỉ mở rộng interface sắp xếp trong dòng API mới.

### 6.2. Khai báo rõ các năng lực cần dùng

Nếu repository cần cả CRUD và phân trang/sắp xếp:

```java
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface ProductRepository
        extends CrudRepository<Product, UUID>,
                PagingAndSortingRepository<Product, UUID> {
}
```

Cách đọc hợp đồng trở nên rõ ràng:

- `CrudRepository` cung cấp nhóm thao tác CRUD.
- `PagingAndSortingRepository` cung cấp các thao tác phân trang và sắp xếp tương ứng.

Trong dòng có các biến thể trả về danh sách, có thể cân nhắc `ListCrudRepository` và `ListPagingAndSortingRepository` khi đúng nhu cầu và được phiên bản hỗ trợ. Cần xem chữ ký của từng phương thức, không chỉ thay tên interface hàng loạt.

### 6.3. Bài học về đọc Javadoc

Một phương thức không nằm trong danh sách method khai báo trực tiếp có thể xuất hiện qua kế thừa. Ngược lại, khi quan hệ kế thừa thay đổi, method từng có qua interface cha có thể không còn thuộc hợp đồng hiện tại.

Do đó, khi kiểm tra một lời gọi, hãy lần theo:

```text
Kiểu khai báo của biến repository
        |
        v
Interface repository của ứng dụng
        |
        v
Các interface cha trong đúng phiên bản
        |
        v
Chữ ký phương thức thực sự khả dụng
```

Đừng kết luận rằng Commons “xóa CRUD” chỉ vì một interface sắp xếp không còn chứa CRUD qua quan hệ kế thừa cũ.

## 7. Ví dụ 3: khác kiểu trả về do đọc nhầm hợp đồng

Giả sử repository của ứng dụng mở rộng `CrudRepository<Product, UUID>`, nhưng người viết đã xem ví dụ của một interface trả về danh sách:

```java
List<Product> all = products.findAll();
```

Lỗi có thể xuất hiện vì kiểu trả về của `CrudRepository.findAll()` là `Iterable<Product>`, không phải `List<Product>`.

Cần kiểm tra:

1. `products` được khai báo với kiểu nào?
2. `findAll()` được kế thừa từ interface nào trong phiên bản đó?
3. Interface ứng dụng có khai báo lại phương thức với kiểu trả về hợp lệ hay không?
4. Ví dụ đang đọc dùng Commons trực tiếp hay dùng một interface của store có hợp đồng khác?

Hai đoạn code cùng gọi `findAll()` chưa chắc có cùng kiểu trả về ở cấp biên dịch.

Không sửa lỗi này bằng một phép cast chưa được bảo đảm. Hãy chọn đúng kiểu nhận kết quả, chuyển đổi tường minh hoặc chọn hợp đồng repository phù hợp với phiên bản và store.

## 8. Tồn tại trong Commons chưa đồng nghĩa store hỗ trợ mọi cách dùng

Sau khi xác minh class và method có trong JAR, vẫn còn một tầng đối chiếu.

### 8.1. Ba mức kiểm tra

| Mức | Câu hỏi | Ví dụ |
| --- | --- | --- |
| API | Kiểu và phương thức có tồn tại không? | Có `ExampleMatcher`, `Pageable`, projection interface |
| Tích hợp | Store hỗ trợ cách dùng cụ thể không? | Loại truy vấn đó có dùng QBE hoặc kiểu projection này được không? |
| Hành vi | Kết quả và chi phí thực tế có đúng yêu cầu không? | Có truy vấn đếm, tải thêm dữ liệu, phụ thuộc callback auditing không? |

Ví dụ:

- `Pageable` biểu đạt yêu cầu phân trang; nó không tự bảo đảm mọi loại truy vấn đều thực hiện phân trang theo cùng cách.
- Hạ tầng projection không bảo đảm mọi store đều chỉ đọc đúng những trường xuất hiện trong interface projection.
- `ExampleMatcher` không làm mọi phép lọc phức tạp trở thành Query by Example.
- `@CreatedDate` cần cơ chế auditing theo store được kích hoạt và áp dụng trên đường ghi thực tế.
- Metadata chung không thay thế toàn bộ mapping và quy tắc chuyển đổi của store.

### 8.2. Ví dụ với Query by Example

Bạn tìm được cách tạo matcher trong tài liệu Commons của đúng phiên bản. Code tạo `Example<Product>` biên dịch thành công.

Trước khi kết luận tính năng đã sử dụng đúng, cần tiếp tục kiểm tra:

- Store module có hỗ trợ Query by Example hay không.
- Kiểu thuộc tính và kiểu so khớp được hỗ trợ.
- Repository có ghép hợp đồng thực thi tương ứng.
- Probe có vô tình mang giá trị mặc định làm điều kiện lọc hay không.
- Hành vi chuỗi có phụ thuộc khả năng và cấu hình kho dữ liệu hay không.

Tài liệu đúng phiên bản giải quyết được câu hỏi về hợp đồng. Nó vẫn phải được đọc cùng tài liệu store và dữ liệu thực tế để đánh giá hành vi.

## 9. Phân biệt tương thích nguồn, tương thích nhị phân và hành vi

### 9.1. Tương thích nguồn

Code nguồn có tiếp tục biên dịch với tập thư viện mới không?

Ví dụ quan hệ kế thừa của `PagingAndSortingRepository` cho thấy thay đổi API có thể khiến lời gọi từng hợp lệ không còn nằm trong hợp đồng mà biến repository đang sử dụng.

Các thay đổi về generic, overload hoặc kiểu trả về cũng có thể làm compiler chọn cách hiểu khác hoặc từ chối code.

### 9.2. Tương thích nhị phân

Bytecode đã biên dịch có liên kết được với các class và method ở runtime không?

Một ứng dụng có thể đã biên dịch với method của thư viện mới nhưng được triển khai cùng một JAR không chứa chữ ký đó. Khi JVM thực hiện liên kết, lỗi như `NoSuchMethodError` có thể xuất hiện.

`NoClassDefFoundError` có thể liên quan tới class không có ở runtime; nó cũng có nguyên nhân khác, chẳng hạn lỗi khởi tạo class trước đó. Phải đọc nguyên nhân gốc thay vì mặc định mọi lỗi kiểu này đều do version Commons.

`AbstractMethodError` cũng có thể là dấu hiệu các thành phần không còn khớp hợp đồng nhị phân. Tên lỗi gợi hướng điều tra, không thay thế việc kiểm tra dependency và stack trace.

### 9.3. Tương thích hành vi

Code biên dịch và chạy được có tiếp tục đáp ứng nghiệp vụ không?

Những thay đổi cần quan sát có thể gồm:

- Cách xác định đối tượng mới.
- Cách xử lý null hoặc dữ liệu không hợp lệ.
- Cơ chế truy vấn, chuyển đổi và mapping.
- Cách áp dụng auditing.
- Chi phí truy vấn hoặc việc tải dữ liệu liên quan.

Không khẳng định tất cả mục trên thay đổi trong mọi lần nâng cấp. Chúng là các điểm cần kiểm tra khi release notes, migration guide hoặc hành vi ứng dụng chỉ ra có liên quan.

Ba mức tương thích là ba loại bằng chứng khác nhau. Build thành công là cần thiết, nhưng chưa chứng minh toàn bộ hành vi và runtime đều đúng.

## 10. Quy trình đối chiếu khi tài liệu và dự án không khớp

### Bước 1: mô tả chính xác điều đang thất bại

Ghi rõ:

- Tên kiểu đầy đủ hoặc import.
- Chữ ký phương thức muốn dùng.
- Kiểu khai báo của biến nhận lời gọi.
- Lỗi xảy ra ở IDE, lúc biên dịch, khi khởi tạo context hay khi chạy truy vấn.
- Ví dụ được lấy từ module và phiên bản tài liệu nào.

“Repository không chạy” chưa đủ để phân biệt thiếu dependency, thiếu bean, sai tên thuộc tính hoặc lỗi liên kết API.

### Bước 2: xác định dependency đã resolve

Đối chiếu ít nhất Commons và store module. Nếu có Boot hoặc BOM, xác định chúng đang quản lý tập phiên bản nào.

Khi nghi ngờ runtime, kiểm tra cả gói ứng dụng được triển khai và môi trường nạp thư viện. Một dependency tree ở máy phát triển không tự chứng minh môi trường chạy đang dùng đúng JAR đó.

Chưa thay version ở bước này. Mục đích là biết trạng thái hiện tại để mọi thay đổi sau đó có cơ sở.

### Bước 3: mở tài liệu đúng module và dòng phiên bản

Chuyển version selector hoặc tìm bộ tài liệu phát hành phù hợp. Kiểm tra số phiên bản hiển thị trên chính trang đang đọc, thay vì chỉ dựa vào tiêu đề tab hoặc kết quả tìm kiếm.

Nếu nguồn chỉ có tài liệu theo dòng minor hoặc dòng bảo trì, ghi nhận phạm vi đó. Khi lỗi có thể liên quan đến bản vá, xem release notes và source của artifact cụ thể.

Nếu trang đã chuyển hướng, kiểm tra đích cuối cùng. Một liên kết cũ có thể đưa tới tài liệu khác với điều người chia sẻ ban đầu muốn chỉ.

### Bước 4: kiểm tra API và quan hệ kế thừa

Xác minh class, method, tham số, kiểu trả về và interface cha.

Đối chiếu API của Commons với API của store nếu phương thức được kế thừa. Chú ý đúng overload, tránh lấy chữ ký của ví dụ khác chỉ vì tên method giống nhau.

Nếu Javadoc chưa rõ, xem source JAR hoặc class mà IDE đang gắn với artifact đã resolve.

### Bước 5: kiểm tra hỗ trợ của store và cấu hình

Nếu API tồn tại nhưng thao tác thất bại, xem:

- Khả năng truy vấn và kiểu trả về của store.
- Mapping của domain.
- Đăng ký repository và phạm vi quét.
- Cấu hình auditing, transaction hoặc callback có liên quan.
- Những điều kiện nền tảng được tài liệu yêu cầu.

Lỗi thuộc bước này không nhất thiết được giải quyết bằng cách nâng Commons.

### Bước 6: chọn một hướng xử lý có mục tiêu

Có ba hướng thường gặp:

| Hướng | Khi nào phù hợp | Việc phải làm rõ |
| --- | --- | --- |
| Điều chỉnh code theo API đang có | Chức năng hiện tại đáp ứng đủ nhu cầu | Dùng đúng hợp đồng, không dựa vào API chưa có |
| Dùng cách khác được store hỗ trợ | API chung không bao phủ nhu cầu cụ thể | Đặt implementation đúng tầng, chấp nhận phụ thuộc store |
| Nâng cấp tập dependency | Cần tính năng mới hoặc có lý do bảo trì cụ thể | Phối hợp phiên bản, đọc migration guide, kiểm tra thay đổi |

Không đồng thời đổi Commons, store, driver và code truy vấn mà không biết mục tiêu của từng thay đổi. Khi có một lần nâng cấp toàn bộ nền tảng đã được lựa chọn, ghi rõ đó là một thay đổi có phạm vi tương ứng.

### Bước 7: xác minh ở mức cần thiết

Sau khi điều chỉnh:

1. Biên dịch bằng cấu hình build thực tế.
2. Khởi tạo context với repository cần dùng.
3. Thực hiện thao tác liên quan trên dữ liệu kiểm soát được.
4. Kiểm tra tập dependency đóng gói nếu lỗi từng xuất hiện ở runtime.
5. Quan sát hành vi và chi phí truy vấn nếu thay đổi có thể ảnh hưởng chúng.

Không cần kiểm tra lại mọi tính năng chỉ vì sửa một cách nhận `Iterable`. Phạm vi xác minh phải phù hợp với thay đổi và dấu hiệu lỗi đang điều tra.

## 11. Bảng triệu chứng và bằng chứng cần tìm

| Triệu chứng | Các khả năng cần phân biệt | Bằng chứng nên lấy |
| --- | --- | --- |
| IDE không tìm thấy class | Thiếu dependency, sai import hoặc API chưa có ở version hiện tại | Artifact đã resolve và Javadoc đúng version |
| Compiler không tìm thấy method | Sai kiểu biến, sai overload hoặc quan hệ kế thừa khác | Chữ ký và cây interface của đúng bản |
| Không gán được `Iterable` cho `List` | Đọc nhầm hợp đồng trả về | Interface thực sự cung cấp method |
| `NoSuchMethodError` khi chạy | Compile và runtime không tương thích | JAR nạp ở runtime so với JAR dùng khi build |
| Repository không được tạo | Cấu hình, quét repository, binding store hoặc lỗi truy vấn khi khởi tạo | Nguyên nhân gốc trong log và cấu hình liên quan |
| Derived query báo sai thuộc tính | Tên method không khớp domain hoặc mapping được hiểu sai | Thuộc tính Java và đường dẫn mà parser nhận diện |
| Có annotation auditing nhưng trường vẫn rỗng | Chưa bật auditing hoặc đường ghi bỏ qua cơ chế tương ứng | Cấu hình store và thao tác ghi thực tế |
| Chỉ lỗi trên môi trường triển khai | Khác artifact, runtime hoặc cấu hình | Gói ứng dụng thực tế và thông tin môi trường |

Bảng này giúp tách lỗi API phiên bản khỏi lỗi cấu hình và dữ liệu. Một triệu chứng có thể có nhiều nguyên nhân; luôn theo nguyên nhân gốc thay vì gán mọi vấn đề cho “tài liệu cũ”.

## 12. Đọc deprecated và API thay thế

Một API được đánh dấu deprecated vẫn có thể tồn tại và hoạt động trong phiên bản đang dùng. Dấu này thể hiện định hướng sử dụng mà tác giả thư viện muốn truyền đạt, không tự chứng minh phương thức đã bị xóa.

Khi gặp deprecated:

1. Đọc lý do và liên kết thay thế.
2. Xem API thay thế có tồn tại trong phiên bản hiện tại không.
3. Đối chiếu khác biệt về tham số, kết quả và hành vi.
4. Xem migration guide nếu thay đổi gắn với một lần nâng dòng.
5. Chuyển đổi và kiểm tra đúng phạm vi bị ảnh hưởng.

Nếu có thông tin như `forRemoval = true`, nó thể hiện ý định loại bỏ nhưng không tự cam kết API chắc chắn mất ở ngay bản phát hành kế tiếp.

Không thay một API deprecated bằng một đoạn ví dụ mới chỉ vì tên có vẻ tương đương. API thay thế có thể yêu cầu xử lý trạng thái, dữ liệu hoặc cấu hình khác.

## 13. Ghi nhận phiên bản để người khác tái hiện được

Khi chia sẻ một ví dụ hoặc kết luận kỹ thuật, ghi lại những thông tin có liên quan:

| Mục | Nội dung cần ghi |
| --- | --- |
| Công việc đang xét | CRUD, phân trang, projection, QBE, auditing hoặc fragment |
| Nền tảng quản lý dependency | Dòng và version Boot/BOM nếu có |
| Dependency thực tế | Version Commons và store module đã resolve |
| Java | JDK biên dịch và Java runtime khi có khác biệt |
| Tài liệu | Tên module, version hiển thị và trang cụ thể |
| API | Tên đầy đủ của kiểu, chữ ký method, interface cha cần thiết |
| Kết quả | Biên dịch, khởi tạo repository và hành vi đã quan sát |
| Phạm vi kết luận | Điều đã xác minh và giới hạn chưa được kiểm chứng |

Có thể viết một ghi nhận ngắn như:

> Ví dụ dùng repository mở rộng CrudRepository và PagingAndSortingRepository. Kết quả đã được đối chiếu với Javadoc của Commons đúng dòng dependency đã resolve, sau đó thực hiện truy vấn phân trang qua store đang dùng.

Trong một ghi nhận thực tế, điền số phiên bản cụ thể thay vì chỉ ghi “Spring Data mới” hoặc “tài liệu hiện tại”.

Nếu sử dụng tài liệu của phiên bản khác để so sánh, ghi rõ phiên bản đang dùng và phiên bản được đối chiếu. Điều đó giúp người đọc phân biệt mô tả hiện trạng với đề xuất nâng cấp.

## 14. Bài tập tự đối chiếu

### Tình huống A: không có ListCrudRepository

Dự án resolve Commons 2.7. Một bài hướng dẫn dùng `ListCrudRepository`.

**Cần kết luận:** ví dụ yêu cầu một API được bổ sung từ 3.0, trong khi JAR hiện tại chưa có. Chọn `CrudRepository` và xử lý kiểu trả về phù hợp, hoặc đánh giá nâng cấp tập dependency. Không sửa bằng import một class có tên gần giống ở thư viện khác.

### Tình huống B: không gọi được findById sau khi đổi dòng

Repository chỉ mở rộng `PagingAndSortingRepository`. Sau khi chuyển sang dòng API từ 3.0, code gọi `findById` không biên dịch.

**Cần kết luận:** kiểm tra thay đổi quan hệ kế thừa. Nếu cần cả hai nhóm chức năng, khai báo thêm hợp đồng CRUD phù hợp. Không coi đây là bằng chứng mọi repository của Spring Data đều mất khả năng đọc theo ID.

### Tình huống C: build thành công, runtime báo NoSuchMethodError

Máy phát triển biên dịch được, nhưng gói triển khai dùng một JAR khác với bản compiler đã thấy.

**Cần kết luận:** kiểm tra chữ ký method và nguồn JAR thực sự được nạp. Giải quyết sự lệch dependency hoặc đóng gói trước khi thay đổi logic nghiệp vụ.

### Tình huống D: API có nhưng truy vấn không được hỗ trợ

Commons có kiểu biểu đạt yêu cầu mà code sử dụng, nhưng store không hỗ trợ cách kết hợp đó.

**Cần kết luận:** tài liệu API đúng chưa đủ. Phải xem khả năng của store và chọn hợp đồng hoặc implementation phù hợp. Không mặc định chuyển sang Javadoc mới hơn sẽ làm kho dữ liệu có thêm khả năng.

## 15. Thói quen cần giữ khi học các bài tiếp theo

Trước một ví dụ về repository, phân trang, projection, Query by Example, metadata hoặc auditing, hãy xác định ba mốc: **tài liệu của phiên bản nào, dependency thực tế là phiên bản nào, store nào thực hiện thao tác**.

Dùng reference guide để hiểu mô hình, Javadoc để chốt hợp đồng, migration guide để xử lý thay đổi và dependency graph để xác định thư viện thực tế. Khi cần điều tra implementation, xem source tương ứng với đúng artifact.

Cách đọc đó giúp bạn học được API hiện hành, áp dụng được kiến thức vào phiên bản dự án đang dùng và biết rõ phần nào cần thay đổi trước khi nâng cấp.

