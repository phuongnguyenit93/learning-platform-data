# FluentQuery và cách điều khiển truy vấn qua hàm callback

## 1. FluentQuery giải quyết việc gì?

Một bộ lọc có thể được dùng cho nhiều mục đích: lấy danh sách, lấy một bản ghi, phân trang, trả về projection, đếm hoặc kiểm tra tồn tại. Nếu mỗi cách lấy kết quả đều cần một phương thức repository riêng, giao diện repository dễ trở nên dài và lặp lại.

Trong Spring Data Commons, `FluentQuery` mô tả khả năng điều chỉnh cách thực thi và lấy kết quả thông qua một chuỗi phương thức. Một số API repository nhận **hàm callback**, cung cấp đối tượng fluent query cho hàm đó và nhận lại kết quả mà hàm tạo ra.

Mẫu sử dụng điển hình với Query by Example (QBE):

~~~java
List<Customer> customers = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("displayName").ascending())
                .all());
~~~

Đọc biểu thức này theo ba bước:

1. `example` xác định những khách hàng cần tìm.
2. Callback cấu hình sắp xếp trên đối tượng `query`.
3. `all()` thực hiện thao tác lấy kết quả và callback trả về danh sách.

Điểm quan trọng là **điều kiện truy vấn** và **cách lấy kết quả** có vai trò khác nhau. Trong ví dụ QBE, điều kiện nằm trong `Example`; fluent query cho phép điều chỉnh cách đọc tập kết quả đó.

Sau bài này, bạn có thể:

- Giải thích vai trò của `FluentQuery` và `FetchableFluentQuery`.
- Viết callback cho `QueryByExampleExecutor.findBy`.
- Chọn giữa lấy một, lấy đầu tiên, lấy tất cả, phân trang, đếm và kiểm tra tồn tại.
- Hiểu cách projection ảnh hưởng đến kiểu dữ liệu trả về.
- Giữ đối tượng query trong đúng phạm vi callback và sử dụng đúng khả năng của adapter.

## 2. Các abstraction liên quan trong Spring Data Commons

### 2.1. FluentQuery và FetchableFluentQuery

`FluentQuery<T>` nằm trong package:

~~~java
org.springframework.data.repository.query
~~~

Nó mô tả những thao tác cấu hình như sắp xếp, chọn kiểu kết quả và chọn thuộc tính. Trong API đồng bộ, kiểu lồng `FluentQuery.FetchableFluentQuery<T>` bổ sung các thao tác lấy kết quả như `all()`, `one()`, `page(...)`, `count()` và `exists()`.

Có thể phân biệt hai nhóm thao tác:

| Nhóm | Ví dụ | Vai trò |
| --- | --- | --- |
| Cấu hình | `sortBy(...)`, `as(...)`, `project(...)` | Xác định cách đọc hoặc biểu diễn kết quả |
| Kết thúc truy vấn | `all()`, `one()`, `first()`, `page(...)`, `count()`, `exists()` | Thực hiện nhu cầu đọc và tạo kết quả trả về |

“Fluent” nghĩa là kết quả của bước cấu hình cho phép gọi tiếp bước sau. Nó không có nghĩa truy vấn bất đồng bộ, cũng không tự tạo transaction.

Đối với các API reactive, Spring Data có abstraction tương ứng. Không lấy quy tắc về kiểu `List`, `Optional` và transaction đồng bộ trong bài rồi áp dụng nguyên trạng cho reactive repository.

### 2.2. Điểm vào qua QueryByExampleExecutor

Chữ ký tổng quát của phương thức được dùng trong bài:

~~~java
<S extends T, R> R findBy(
        Example<S> example,
        Function<FluentQuery.FetchableFluentQuery<S>, R> queryFunction);
~~~

Các import liên quan:

~~~java
import java.util.function.Function;
import org.springframework.data.domain.Example;
import org.springframework.data.repository.query.FluentQuery;
~~~

Ý nghĩa các kiểu:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `T` | Kiểu domain mà repository quản lý |
| `S extends T` | Kiểu của probe và tập domain đang được truy vấn |
| `FetchableFluentQuery<S>` | Đối tượng truy vấn được cung cấp cho callback |
| `R` | Kiểu kết quả cuối cùng callback trả về |

`R` không nhất thiết là entity. Nó có thể là `List<Customer>`, `Optional<Customer>`, `Page<Customer>`, một projection, `Long` hoặc `Boolean`, tùy thao tác kết thúc trong callback.

`Example` và hàm callback phải được cung cấp hợp lệ, không truyền `null` thay cho chúng.

### 2.3. Hợp đồng chung và implementation cụ thể

`QueryByExampleExecutor` và `FluentQuery` thuộc Commons, nhưng truy vấn thực tế do Spring Data module đứng sau repository thực hiện.

Ví dụ trong bài dùng **Spring Data JPA** để có một điểm thực hành cụ thể. Với module khác, cần xác định hỗ trợ QBE, projection, các thao tác fluent và quy tắc ánh xạ tương ứng.

Việc thêm một interface vào khai báo repository không tự tạo implementation truy vấn cho một adapter chưa hỗ trợ. Những API khác cũng có thể cung cấp callback fluent, nhưng phải dùng đúng chữ ký mà chúng công bố.

## 3. Chuẩn bị mô hình và bộ lọc

### 3.1. Entity minh họa

Đặt entity và repository dưới đây trong package mà ứng dụng JPA quét. Các annotation `jakarta.persistence` là phần ánh xạ JPA của ví dụ, không phải yêu cầu của mọi Spring Data module.

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;
    private String email;
    private String country;
    private Boolean active;

    public Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getCountry() {
        return country;
    }

    public void setCountry(String country) {
        this.country = country;
    }

    public Boolean getActive() {
        return active;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
~~~

Dùng kiểu wrapper `Long` và `Boolean` giúp probe biểu diễn giá trị chưa đặt bằng `null`. Nếu dùng primitive, giá trị mặc định như `0` hoặc `false` có thể trở thành điều kiện ngoài ý muốn.

Các trường metadata như ID, thời điểm tạo hoặc người tạo cũng có thể thu hẹp QBE nếu chúng có giá trị và không bị bỏ qua. Vì vậy, nên tạo probe mới dành cho bộ lọc, thay vì sử dụng một entity đã được tải đầy đủ.

### 3.2. Repository

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Trong ví dụ JPA này, khả năng QBE được cung cấp qua hệ thống interface của `JpaRepository`. Không cần tự triển khai một phương thức `findBy` chỉ để chạy những callback bên dưới.

Nếu khai báo repository bằng các interface Commons như `CrudRepository` và `QueryByExampleExecutor`, vẫn cần adapter hỗ trợ tổ hợp đó.

### 3.3. Tạo Example làm điều kiện đầu vào

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setCountry("VN");
probe.setActive(true);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths("id");

Example<Customer> example = Example.of(probe, matcher);
~~~

Điều kiện nghiệp vụ ở đây là:

~~~text
country = "VN" AND active = true
~~~

Các thuộc tính khác đang `null` nên không tham gia. Không tiếp tục sửa probe nếu cần giữ điều kiện ổn định giữa các lần gọi: đối tượng `Example` giữ tham chiếu đến probe, không chụp lại toàn bộ trạng thái của entity thành một bản sao độc lập.

Trong các đoạn tiếp theo, `repository` là một `CustomerRepository` đã được inject vào service hoặc cung cấp trong repository test. `example` là bộ lọc đã tạo ở trên. Các đoạn mã thể hiện những cách gọi độc lập.

## 4. Callback hoạt động như thế nào?

~~~mermaid
sequenceDiagram
    participant S as Service
    participant R as Repository
    participant C as Callback
    participant D as Kho dữ liệu
    S->>R: findBy(example, callback)
    R->>C: Cung cấp FetchableFluentQuery
    C->>C: sortBy / as / cấu hình khác
    C->>D: Thao tác kết thúc qua implementation
    D-->>C: Kết quả
    C-->>R: Trả về R
    R-->>S: Trả về R
~~~

Sơ đồ mô tả luồng logic; chi tiết tạo truy vấn và trao đổi với kho dữ liệu thuộc implementation.

### 4.1. Lambda ngắn

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;

List<Customer> customers = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by(
                        Sort.Order.asc("displayName"),
                        Sort.Order.asc("id")))
                .all());
~~~

`query` là tham số do repository truyền vào callback. Bạn không tự tạo nó bằng `new` và không cần truyền repository vào callback.

### 4.2. Lambda có khối lệnh

Khi cần chọn cấu hình dựa trên đầu vào, có thể dùng lambda có thân:

~~~java
boolean descendingById = true;

List<Customer> customers = repository.findBy(example, query -> {
    Sort sort = descendingById
            ? Sort.by("id").descending()
            : Sort.by("displayName").ascending()
                    .and(Sort.by("id").ascending());

    return query.sortBy(sort).all();
});
~~~

Do callback là một `Function` có kết quả, lambda dạng khối phải trả về giá trị ở các nhánh phù hợp. Không chuyển nó thành một khối chỉ gọi truy vấn rồi bỏ quên `return`.

Biến cục bộ được tham chiếu từ lambda phải là `final` hoặc *effectively final* theo quy tắc Java. Ví dụ trên không thay đổi `descendingById` sau khi gán.

### 4.3. Dùng giá trị trả về của bước cấu hình

Nên viết chuỗi cấu hình và thao tác kết thúc liền nhau:

~~~java
List<Customer> customers = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .all());
~~~

Không giả định đối tượng cấu hình bị thay đổi tại chỗ:

~~~java
// Không nên viết theo giả định sortBy luôn sửa chính query:
List<Customer> customers = repository.findBy(example, query -> {
    query.sortBy(Sort.by("id").ascending());
    return query.all();
});
~~~

Các phương thức cấu hình trả về đối tượng query cần dùng cho bước tiếp theo. Bỏ qua giá trị trả về có thể khiến cấu hình bạn muốn không được áp dụng.

Nguyên tắc này đặc biệt quan trọng với `as(...)` vì kiểu phần tử sau phép chiếu có thể khác kiểu ban đầu.

## 5. Chọn thao tác kết thúc

| Nhu cầu | Thao tác | Kiểu kết quả điển hình |
| --- | --- | --- |
| Lấy toàn bộ kết quả | `all()` | `List<T>` |
| Kỳ vọng tối đa một kết quả | `one()` | `Optional<T>` |
| Lấy kết quả đầu tiên | `first()` | `Optional<T>` |
| Lấy một trang kèm metadata | `page(pageable)` | `Page<T>` |
| Chỉ lấy số lượng | `count()` | `long` |
| Chỉ hỏi có kết quả không | `exists()` | `boolean` |
| Đọc qua stream | `stream()` | `Stream<T>` |

Bảng mô tả nhóm thao tác đồng bộ thường gặp trên `FetchableFluentQuery`. Các khả năng bổ sung như giới hạn hoặc scrolling cần đối chiếu API và hỗ trợ của module đang dùng; không suy ra mọi thao tác đều có cùng mức hỗ trợ trên mọi adapter.

### 5.1. all: toàn bộ kết quả phù hợp

~~~java
List<Customer> customers = repository.findBy(
        example,
        query -> query.sortBy(Sort.by("id").ascending()).all());
~~~

`all()` trả về danh sách rỗng khi không có kết quả. Không có phân trang trong lời gọi này, nên số phần tử có thể lớn.

Nếu không cấu hình thứ tự, không dựa vào thứ tự quan sát được từ một lần chạy. Với màn hình danh sách, sắp xếp ổn định và giới hạn dữ liệu thường cần được thể hiện rõ.

### 5.2. one: tối đa một kết quả

~~~java
import java.util.Optional;

Customer emailProbe = new Customer();
emailProbe.setEmail("an@example.com");

Example<Customer> byEmail = Example.of(
        emailProbe,
        ExampleMatcher.matchingAll()
                .withIgnoreNullValues()
                .withIgnorePaths("id"));

Optional<Customer> customer = repository.findBy(
        byEmail,
        query -> query.one());
~~~

Hành vi:

- Không có kết quả: `Optional.empty()`.
- Có đúng một kết quả: `Optional` chứa kết quả đó.
- Có nhiều hơn một kết quả: phát sinh `IncorrectResultSizeDataAccessException`.

`one()` thể hiện kỳ vọng về số lượng; nó không tự tạo ràng buộc duy nhất trong kho dữ liệu. Khi dùng so khớp không phân biệt hoa thường, kỳ vọng duy nhất cũng phải thống nhất với quy tắc lưu trữ, chuẩn hóa và ràng buộc dữ liệu.

### 5.3. first: lấy phần tử đầu tiên

~~~java
Optional<Customer> first = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by(
                        Sort.Order.asc("displayName"),
                        Sort.Order.asc("id")))
                .first());
~~~

`first()` không có nghĩa xác nhận tập kết quả chỉ có một phần tử. Nó dùng khi nghiệp vụ chấp nhận chọn phần tử đầu theo thứ tự.

Đối chiếu:

| Tập kết quả | `one()` | `first()` |
| --- | --- | --- |
| Rỗng | `Optional.empty()` | `Optional.empty()` |
| Một phần tử | Trả phần tử đó | Trả phần tử đó |
| Nhiều phần tử | Lỗi kích thước kết quả | Trả phần tử đầu |

Nếu không chỉ định sắp xếp, “đầu tiên” không có ý nghĩa ổn định về nghiệp vụ. Sắp theo tên và thêm ID giúp phân định khi trùng tên.

Ngoài các biến thể trả `Optional`, API còn có `oneValue()` và `firstValue()` để trả trực tiếp giá trị hoặc `null` khi không có kết quả. Chọn một cách biểu diễn sự vắng mặt nhất quán; không nhầm các biến thể này với cơ chế bảo đảm luôn có dữ liệu.

### 5.4. count và exists: chọn theo câu hỏi cần trả lời

~~~java
long total = repository.findBy(example, query -> query.count());

boolean present = repository.findBy(
        example,
        query -> query.exists());
~~~

`count()` trả về số lượng phù hợp. `exists()` chỉ trả lời có ít nhất một kết quả hay không. Java tự boxing kết quả nguyên thủy khi cần đáp ứng kiểu tổng quát `R` rồi unboxing khi gán lại vào `long` hoặc `boolean`.

Không gọi `all().size()` chỉ để đếm một tập lớn. Không gọi `one().isPresent()` để hỏi có dữ liệu hay không nếu bộ lọc có thể khớp nhiều phần tử.

Hiệu năng cụ thể của `exists` và `count` phụ thuộc implementation và kho dữ liệu. Hợp đồng fluent không bảo đảm một câu SQL cố định hoặc mọi lời gọi `exists` đều có cùng kế hoạch thực thi.

Nếu nhu cầu chỉ đơn giản là đếm hoặc kiểm tra tồn tại từ một `Example`, các phương thức trực tiếp `repository.count(example)` và `repository.exists(example)` cũng diễn đạt rõ ý định. Không bắt buộc bọc mọi thao tác repository vào callback.

## 6. Điều khiển kiểu kết quả bằng as

Một trang chọn khách hàng có thể chỉ cần ID và tên hiển thị, thay vì toàn bộ entity. Có thể khai báo projection:

~~~java
public interface CustomerSummary {
    Long getId();
    String getDisplayName();
}
~~~

Trong ví dụ JPA có hỗ trợ kiểu projection này:

~~~java
List<CustomerSummary> summaries = repository.findBy(
        example,
        query -> query
                .as(CustomerSummary.class)
                .sortBy(Sort.by(
                        Sort.Order.asc("displayName"),
                        Sort.Order.asc("id")))
                .all());
~~~

Đọc kiểu dữ liệu theo chuỗi:

~~~text
FetchableFluentQuery<Customer>
    -> as(CustomerSummary.class)
FetchableFluentQuery<CustomerSummary>
    -> all()
List<CustomerSummary>
~~~

`as(...)` yêu cầu implementation biểu diễn kết quả theo kiểu đích. Nó không phải phép ép kiểu Java từ `Customer` sang `CustomerSummary`.

Các thuộc tính sắp xếp vẫn phải là các đường dẫn hợp lệ theo mô hình domain và khả năng ánh xạ của adapter. Không suy ra rằng sau `as` bạn có thể sắp xếp bằng bất kỳ tên phương thức tùy ý nào của projection.

### 6.1. Không chọn R tùy ý mà bỏ qua khả năng ánh xạ

Tham số tổng quát `R` của callback cho phép nhiều kiểu kết quả, nhưng điều đó không có nghĩa mọi lớp Java đều dùng được với `as(...)`.

Với DTO hoặc projection, phải đáp ứng quy tắc ánh xạ của module: tên thuộc tính, constructor, kiểu dữ liệu và các giới hạn hỗ trợ liên quan. Một lớp không phù hợp có thể gây lỗi ánh xạ dù code generic vẫn biên dịch.

Không cam kết rằng mọi projection luôn chỉ đọc đúng số cột hiển thị trên giao diện. Tối ưu truy vấn thực tế phụ thuộc dạng projection và implementation.

### 6.2. Phân biệt as và project

| Thao tác | Ý định |
| --- | --- |
| `as(ResultType.class)` | Chọn kiểu biểu diễn kết quả |
| `project(...)` | Yêu cầu giới hạn các thuộc tính được đưa vào phép chiếu |

`project` không tự đổi kiểu generic thành một DTO và không thay thế quy tắc ánh xạ. Việc đọc một entity chỉ được nạp một phần cũng cần được hiểu theo adapter; không nên coi nó là một entity đầy đủ để sửa rồi lưu một cách tùy tiện.

Ở mức nhập môn, dùng một projection rõ ràng với `as(...)` giúp người đọc hiểu dữ liệu đầu ra. Chỉ kết hợp chọn thuộc tính khi đã xác định mục tiêu và khả năng hỗ trợ.

## 7. Phân trang trong callback

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("displayName"),
                Sort.Order.asc("id")));

Page<CustomerSummary> page = repository.findBy(
        example,
        query -> query
                .as(CustomerSummary.class)
                .page(pageable));
~~~

Callback ở đây trả về `Page<CustomerSummary>`. Không cần lấy toàn bộ danh sách rồi tự cắt một đoạn trong Java.

Các thông tin thường dùng:

~~~java
List<CustomerSummary> content = page.getContent();
int currentPage = page.getNumber();
int numberOfElements = page.getNumberOfElements();
long totalElements = page.getTotalElements();
boolean hasNext = page.hasNext();
~~~

Cần phân biệt:

- `getNumber()` dùng chỉ số trang bắt đầu từ `0`.
- `getNumberOfElements()` là số phần tử trong trang hiện tại.
- `getTotalElements()` là tổng số phần tử phù hợp theo metadata phân trang.
- Trang được yêu cầu có thể rỗng vì vượt phạm vi, dù bộ lọc vẫn có kết quả ở trang trước.

Ví dụ đặt toàn bộ thứ tự trong `PageRequest`, nên không cần gọi thêm `sortBy` trước `page`. Khi kết hợp nhiều nguồn sắp xếp hoặc cấu hình giới hạn, phải xác định quy tắc ưu tiên của API và implementation; tránh viết cấu hình chồng chéo rồi dựa vào suy đoán.

Để lấy tổng số phần tử cho `Page`, implementation có thể cần thêm truy vấn đếm. Một số tình huống cho phép suy ra tổng và bỏ qua bước đếm riêng; không giả định mỗi lời gọi luôn có đúng hai truy vấn.

Nếu trang đã cung cấp tổng số phù hợp, không gọi thêm một callback `count` chỉ để lấy lại cùng thông tin.

Đối với đầu vào phân trang từ người dùng, kiểm tra số trang, kích thước trang và các thuộc tính sắp xếp được phép trước khi thực thi. `PageRequest` yêu cầu số trang không âm và kích thước lớn hơn `0`; mức tối đa do ứng dụng quy định.

## 8. Viết callback thành Function có kiểu rõ ràng

Lambda tại chỗ thường ngắn gọn nhất. Khi cần đặt tên cho một cách lấy kết quả hoặc giải thích kiểu generic, có thể tách callback:

~~~java
import java.util.List;
import java.util.function.Function;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.query.FluentQuery;

Function<
        FluentQuery.FetchableFluentQuery<Customer>,
        List<CustomerSummary>> readSummaries =
        query -> query
                .as(CustomerSummary.class)
                .sortBy(Sort.by(
                        Sort.Order.asc("displayName"),
                        Sort.Order.asc("id")))
                .all();

List<CustomerSummary> summaries =
        repository.findBy(example, readSummaries);
~~~

`readSummaries` lưu **hành vi cấu hình và đọc**. Mỗi lần gọi `findBy`, repository cung cấp một đối tượng query mới phù hợp với lần gọi đó.

Tách callback không có nghĩa lưu lại query từ lần chạy trước. Có thể tái sử dụng hàm không giữ trạng thái; không tái sử dụng một đối tượng query đã thoát khỏi callback.

Không cần tạo một lớp callback riêng cho mọi lời gọi đơn giản. Chỉ tách khi nó làm rõ ý định hoặc phục vụ tái sử dụng thực sự.

## 9. Phạm vi sống của query: thực thi bên trong callback

Đối tượng fluent query do repository cung cấp chỉ có giá trị sử dụng trong phạm vi lời gọi `findBy`. Callback cần trả về **kết quả truy vấn**, không trả lại chính đối tượng fluent query.

### 9.1. Trả kết quả đã tạo

~~~java
List<Customer> customers = repository.findBy(
        example,
        query -> query.sortBy(Sort.by("id")).all());
~~~

Ở đây callback kết thúc bằng `all()` và trả về `List<Customer>`, đúng mục đích của API.

### 9.2. Không trả builder ra ngoài

~~~java
// Cách dùng không hợp lệ; không đưa vào luồng thực thi:
FluentQuery.FetchableFluentQuery<Customer> escaped =
        repository.findBy(example, query -> query);
~~~

Generic có thể khiến đoạn này nhìn có vẻ hợp lệ về mặt kiểu, nhưng hợp đồng `findBy` không cho phép trả về đối tượng fluent query. API quy định lỗi `InvalidDataAccessApiUsageException` cho trường hợp callback trả về query thay vì kết quả.

Cấu hình xong rồi trả query cũng không giải quyết vấn đề:

~~~java
// Vẫn không hợp lệ:
repository.findBy(
        example,
        query -> query.sortBy(Sort.by("id")));
~~~

`sortBy` là bước cấu hình, chưa phải kết quả cần trả cho caller.

### 9.3. Không trì hoãn việc dùng query

Không giữ query trong field của service, bộ nhớ đệm hoặc một closure để thực thi sau khi `findBy` đã trả về.

Ví dụ về ý tưởng cần tránh:

~~~java
// Không chuyển query sang công việc chạy sau callback:
// query -> () -> query.all()
//
// Không đẩy query sang một tác vụ bất đồng bộ:
// query -> CompletableFuture.supplyAsync(query::all)
~~~

Những cách này giữ tham chiếu đến query để sử dụng ngoài phạm vi được bảo đảm. Việc Java cho phép tạo lambda hoặc future không mở rộng vòng đời của query.

Nếu ứng dụng cần thực thi truy vấn ở một thời điểm khác, hãy giữ **đầu vào tìm kiếm** hoặc một hàm đọc hợp lệ rồi gọi repository mới ở thời điểm đó. Cơ chế transaction và ngữ cảnh thực thi của công việc đó cần được thiết kế riêng.

## 10. Stream là kết quả có tài nguyên cần quản lý

`stream()` là một thao tác kết thúc được API cung cấp. Việc nhận một `Stream` qua thao tác này khác với việc trả lại đối tượng fluent query để cấu hình và thực thi sau.

Với JPA, nên tiêu thụ stream trong phạm vi transaction đọc phù hợp và đóng nó bằng `try-with-resources`:

~~~java
import java.util.stream.Stream;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerNameStatisticsService {

    private final CustomerRepository repository;

    public CustomerNameStatisticsService(
            CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public long countNamesContaining(String fragment) {
        if (fragment == null || fragment.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "Phải cung cấp đoạn tên cần tìm");
        }

        String needle = fragment.trim();

        Customer probe = new Customer();
        probe.setActive(true);

        Example<Customer> example = Example.of(
                probe,
                ExampleMatcher.matchingAll()
                        .withIgnoreNullValues()
                        .withIgnorePaths("id"));

        try (Stream<Customer> customers =
                repository.findBy(
                        example,
                        query -> query.stream())) {

            return customers
                    .map(Customer::getDisplayName)
                    .filter(name -> name != null)
                    .filter(name -> name.contains(needle))
                    .count();
        }
    }
}
~~~

Đoạn này dùng lại các import `Example` và `ExampleMatcher` từ phần chuẩn bị. Để annotation transaction có hiệu lực trong mô hình proxy thông thường của Spring, phương thức cần được gọi qua service bean được quản lý.

Ví dụ minh họa vòng đời stream và tài nguyên. Nếu điều kiện tên có thể được biểu diễn trực tiếp bằng QBE, nên đưa nó vào matcher và để kho dữ liệu lọc, đếm thay vì tải dữ liệu lên Java.

Stream không tự bảo đảm bộ nhớ luôn thấp: adapter, driver, persistence context và cách xử lý phần tử đều ảnh hưởng. Không trả stream ra ngoài một service đã kết thúc transaction rồi mặc định rằng caller có thể tiếp tục đọc an toàn.

## 11. Một service hoàn chỉnh dùng callback

Ví dụ sau cung cấp hai nhu cầu đọc: trang projection cho màn hình tìm kiếm và phần tử đầu theo tên. Các kiểu `Customer`, `CustomerSummary` và `CustomerRepository` đã được định nghĩa ở trên.

~~~java
import java.util.Optional;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class CustomerLookupService {

    private final CustomerRepository repository;

    public CustomerLookupService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Page<CustomerSummary> search(
            String country,
            int page,
            int size) {

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "Trang phải >= 0; kích thước phải từ 1 đến 100");
        }

        Sort sort = Sort.by(
                Sort.Order.asc("displayName"),
                Sort.Order.asc("id"));

        PageRequest pageable = PageRequest.of(page, size, sort);

        return repository.findBy(
                activeInCountry(country),
                query -> query
                        .as(CustomerSummary.class)
                        .page(pageable));
    }

    public Optional<CustomerSummary> firstByName(
            String country) {

        return repository.findBy(
                activeInCountry(country),
                query -> query
                        .as(CustomerSummary.class)
                        .sortBy(Sort.by(
                                Sort.Order.asc("displayName"),
                                Sort.Order.asc("id")))
                        .first());
    }

    private static Example<Customer> activeInCountry(
            String country) {

        if (country == null || country.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "Phải cung cấp mã quốc gia");
        }

        Customer probe = new Customer();
        probe.setCountry(country.trim());
        probe.setActive(true);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnoreNullValues()
                .withIgnorePaths("id");

        return Example.of(probe, matcher);
    }
}
~~~

Service có ba điểm đáng chú ý:

1. `activeInCountry` tập trung định nghĩa điều kiện, tạo probe mới cho mỗi lần gọi.
2. Callback chỉ cấu hình cách lấy dữ liệu và trả về kết quả ngay trong `findBy`.
3. Kiểu trả về của service thể hiện nhu cầu của caller: trang projection hoặc một projection tùy chọn.

Transaction đọc trong ví dụ là lựa chọn cho service JPA; callback không tự tạo nó và `readOnly` không mặc nhiên cung cấp một snapshot cố định cho mọi lần đọc.

Không cần định nghĩa một derived query mới cho từng cách hiển thị cùng bộ lọc. Ngược lại, không bắt buộc dùng fluent query nếu một phương thức repository đơn giản đã thể hiện đầy đủ nhu cầu.

## 12. Quan sát hành vi trên dữ liệu cụ thể

Giả sử dữ liệu ổn định trong lúc thực hiện các lời gọi:

| id | displayName | country | active |
| --- | --- | --- | --- |
| 1 | An Nguyen | VN | true |
| 2 | Binh Tran | VN | true |
| 3 | Chi Le | VN | false |
| 4 | David | US | true |

Với `example` là `country = "VN" AND active = true`:

| Callback | Kết quả mong đợi |
| --- | --- |
| `q -> q.sortBy(Sort.by("id")).all()` | Danh sách ID `1` và `2` |
| `q -> q.count()` | `2L` |
| `q -> q.exists()` | `true` |
| `q -> q.one()` | Lỗi vì có nhiều hơn một kết quả |
| `q -> q.sortBy(Sort.by("id")).first()` | Khách hàng ID `1` trong `Optional` |
| `q -> q.as(CustomerSummary.class).all()` | Hai projection, không mặc định bảo đảm thứ tự |
| `q -> q.page(PageRequest.of(0, 1, Sort.by("id")))` | Trang chứa ID `1` và metadata tổng số `2` |

Nếu đổi điều kiện quốc gia sang một giá trị không có trong dữ liệu:

- `all()` trả về danh sách rỗng.
- `one()` và `first()` trả về `Optional.empty()`.
- `count()` bằng `0` và `exists()` bằng `false`.
- `page(...)` trả về một trang không có nội dung.

Mỗi callback là một yêu cầu đọc riêng. Khi dữ liệu thay đổi đồng thời, không dùng các kết quả từ nhiều lần gọi để suy ra rằng tất cả đều nhìn thấy cùng một trạng thái dữ liệu.

## 13. Các giới hạn cần hiểu đúng

### 13.1. FluentQuery không thay thế ngôn ngữ điều kiện truy vấn

Chuỗi:

~~~java
query.as(CustomerSummary.class)
        .sortBy(Sort.by("id"))
        .all()
~~~

không bổ sung điều kiện `country`, `active` hoặc khoảng thời gian. Với điểm vào QBE, những điều kiện được biểu diễn qua `Example` và khả năng của matcher.

Nếu cần khoảng ngày, so sánh lớn hơn/nhỏ hơn, nhóm `AND`/`OR` lồng nhau, join hoặc aggregation phức tạp, hãy chọn công cụ truy vấn phù hợp của module. Ví dụ JPA có thể dùng Specifications hoặc truy vấn tùy chỉnh.

Fluent query điều khiển cách thực thi trên điều kiện đầu vào được hỗ trợ; nó không biến QBE thành một ngôn ngữ truy vấn tổng quát.

### 13.2. Callback không tự áp dụng cho mọi phương thức repository

Không thêm một tham số `Function` tùy ý vào một derived query rồi mặc định Spring sẽ cung cấp `FetchableFluentQuery`:

~~~java
// Không suy ra cách khai báo này được tự hỗ trợ:
// <R> R findByCountry(
//         String country,
//         Function<FetchableFluentQuery<Customer>, R> callback);
~~~

Phải dùng điểm vào callback mà API hoặc implementation cụ thể công bố, như `QueryByExampleExecutor.findBy(example, queryFunction)` đang học.

### 13.3. Không gán thêm bảo đảm mà callback không cung cấp

Một callback không mặc nhiên:

- Gộp nhiều thao tác kết thúc thành một truy vấn duy nhất.
- Tạo transaction hoặc nâng mức cô lập.
- Cố định dữ liệu trong kho giữa các lần gọi.
- Bảo đảm projection luôn ánh xạ thành công.
- Bảo đảm mọi module đều hỗ trợ toàn bộ thao tác fluent.
- Tự làm một truy vấn không giới hạn trở nên ít tốn tài nguyên.

Bạn có thể viết nhiều thao tác kết thúc trong một lambda, nhưng chúng vẫn có thể là các truy vấn riêng. Thông thường nên chọn một kết quả đúng nhu cầu; dùng `Page` khi cần trang và metadata thay vì tự gọi `all` rồi `count`.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Callback không trả về dữ liệu cần dùng | Kết thúc ở `sortBy` hoặc trả chính `query` | Kết thúc bằng `all`, `page`, `one` hoặc thao tác phù hợp |
| Sắp xếp không được áp dụng như dự định | Bỏ qua đối tượng trả về từ bước cấu hình | Dùng chuỗi phương thức hoặc gán lại query đã cấu hình |
| `one` phát sinh lỗi khi có nhiều kết quả | Nhầm “tối đa một” với “lấy đầu tiên” | Chọn `first` với thứ tự rõ ràng nếu nghiệp vụ cho phép |
| Kết quả đầu tiên thay đổi giữa các lần chạy | Thiếu thứ tự xác định | Sắp theo tiêu chí nghiệp vụ và tiêu chí phân định |
| Projection gây lỗi ánh xạ | Kiểu đích không phù hợp với module hoặc dữ liệu | Kiểm tra thuộc tính, constructor và hỗ trợ projection |
| Stream lỗi khi caller đọc tiếp | Tài nguyên hoặc transaction đã kết thúc | Tiêu thụ, đóng stream trong phạm vi thích hợp |
| Danh sách và bộ đếm không khớp | Khác bộ lọc hoặc khác thời điểm đọc | Dùng chung logic bộ lọc và hiểu mức nhất quán |
| Repository không hỗ trợ cách gọi mong muốn | Suy rộng khả năng của một adapter sang mọi module | Dùng đúng interface, phiên bản và implementation hỗ trợ |

Khi đọc một lời gọi fluent, hãy xác định lần lượt: **điều kiện đầu vào**, **cấu hình cách đọc**, **thao tác kết thúc** và **kiểu kết quả trả về**. Khi bốn phần này rõ ràng, callback thường ngắn, dễ kiểm tra và thể hiện đúng nhu cầu của service.
