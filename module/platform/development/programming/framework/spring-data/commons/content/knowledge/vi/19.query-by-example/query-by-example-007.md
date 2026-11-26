# QueryByExampleExecutor với tìm, đếm và kiểm tra tồn tại

## 1. Mục tiêu và phạm vi

Trong Spring Data Commons, **Query by Example (QBE)** biểu diễn điều kiện tìm kiếm bằng một đối tượng mẫu (*probe*) và quy tắc so khớp (*matcher*). `QueryByExampleExecutor<T>` là abstraction để repository thực thi những điều kiện đó.

Sau bài này, bạn có thể:

- Tạo `Example<T>` dùng chung cho các thao tác tìm, đếm và kiểm tra tồn tại.
- Chọn đúng `findOne`, `findAll`, `count` hoặc `exists` theo nhu cầu.
- Kết hợp QBE với sắp xếp và phân trang.
- Nhận ra các lỗi về điều kiện ngầm, dữ liệu không duy nhất và khác biệt giữa các loại kho dữ liệu.

Phạm vi bài học là API đồng bộ của Spring Data Commons. Phần ví dụ dùng Spring Data JPA làm adapter minh họa. Các annotation ánh xạ, cơ chế thực thi và đặc điểm truy vấn của JPA không phải hợp đồng chung cho mọi Spring Data module.

## 2. Từ đối tượng mẫu đến thao tác repository

Một truy vấn QBE có ba thành phần:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Probe | Mang các giá trị dùng để lọc | `country = "VN"` |
| `ExampleMatcher` | Quy định cách kết hợp, xử lý chuỗi và `null` | Khớp tất cả điều kiện, bỏ qua `null` |
| `Example<T>` | Gói probe và matcher để truyền vào executor | `Example.of(probe, matcher)` |

`Example` mô tả **tập kết quả phù hợp**. Phương thức executor quyết định bạn muốn lấy một bản ghi, lấy nhiều bản ghi, đếm hay chỉ hỏi tập đó có phần tử hay không.

~~~mermaid
flowchart LR
    P["Probe: giá trị bộ lọc"] --> E["Example"]
    M["ExampleMatcher: quy tắc so khớp"] --> E
    E --> O{"Nhu cầu"}
    O --> F["findOne / findAll"]
    O --> C["count"]
    O --> X["exists"]
~~~

QBE khác với một derived query cố định như `findByCountryAndStatus(...)`: bạn thay đổi probe theo bộ lọc đang được cung cấp, thay vì cần một tên phương thức mới cho mỗi tổ hợp điều kiện. Điều này phù hợp với màn hình tìm kiếm có một số trường tùy chọn và logic so khớp đơn giản.

## 3. Chuẩn bị repository và mô hình ví dụ

### 3.1. Repository có khả năng thực thi QBE

Chỉ kế thừa `CrudRepository` không tự bảo đảm repository có API QBE. Có thể thể hiện khả năng cần dùng bằng cách kết hợp hai interface:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                QueryByExampleExecutor<Customer> {
}
~~~

Cách khai báo trên chỉ hoạt động khi Spring Data module đứng sau repository hỗ trợ QBE và tạo implementation tương ứng. Việc thêm interface vào khai báo không tự tạo ra khả năng truy vấn cho một adapter chưa hỗ trợ.

Với JPA, `JpaRepository` đã cung cấp khả năng QBE qua hệ thống interface kế thừa, nên có thể viết:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Hai đoạn trên là **hai lựa chọn khai báo** cho cùng ví dụ; không đặt cả hai interface trùng tên trong một package.

### 3.2. Đối tượng được dùng làm probe

Ví dụ dùng một entity JPA đơn giản. Đặt hai kiểu sau trong các file Java tương ứng của ứng dụng thực hành.

~~~java
public enum CustomerStatus {
    ACTIVE,
    INACTIVE
}
~~~

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
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

    @Enumerated(EnumType.STRING)
    private CustomerStatus status;

    private Boolean archived;

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

    public CustomerStatus getStatus() {
        return status;
    }

    public void setStatus(CustomerStatus status) {
        this.status = status;
    }

    public Boolean getArchived() {
        return archived;
    }

    public void setArchived(Boolean archived) {
        this.archived = archived;
    }
}
~~~

Dùng `Long` và `Boolean` giúp probe biểu diễn trạng thái “chưa đặt điều kiện” bằng `null`. Nếu dùng `long` hoặc `boolean`, các giá trị mặc định `0` và `false` có thể trở thành điều kiện lọc, trừ khi thuộc tính được bỏ qua rõ ràng.

Probe nên là đối tượng mới dành cho một lần xây dựng bộ lọc. Không lấy một entity đã tải đầy đủ từ database làm probe một cách tùy tiện: ID và các trường sẵn có trên entity đó đều có thể thu hẹp kết quả ngoài ý muốn. Các trường auditing như thời điểm tạo, người tạo cũng cần được xem xét khi dùng entity có metadata làm probe.

### 3.3. Tạo một Example để dùng lại

Giả sử cần tìm khách hàng đang hoạt động, ở Việt Nam và chưa lưu trữ:

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setCountry("VN");
probe.setStatus(CustomerStatus.ACTIVE);
probe.setArchived(false);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths("id");

Example<Customer> example = Example.of(probe, matcher);
~~~

Về mặt ý nghĩa, điều kiện là:

~~~text
country = "VN"
AND status = ACTIVE
AND archived = false
~~~

Đây là mô tả logic, không cam kết SQL hoặc cú pháp truy vấn cụ thể. Adapter và kho dữ liệu quyết định cách thực thi.

Các trường `displayName`, `email` đang `null`, nên không tham gia bộ lọc. `withIgnoreNullValues()` làm ý định này rõ ràng; bỏ qua `null` cũng là hành vi mặc định của matcher.

Đừng hiểu `null` trong probe là yêu cầu “cột phải NULL”. Nếu bật `withIncludeNullValues()`, các thuộc tính `null` không bị bỏ qua có thể trở thành điều kiện khớp `null`; tác động này cần được kiểm tra cho toàn bộ probe.

`Example` và `ExampleMatcher` cung cấp các đối tượng cấu hình bất biến, nhưng `Example` vẫn giữ tham chiếu đến probe. Không tiếp tục sửa probe sau khi tạo `Example` nếu bạn cần điều kiện ổn định giữa các lần gọi.

## 4. Chọn phương thức theo kết quả mong muốn

Các phương thức cốt lõi trên `QueryByExampleExecutor<T>` có dạng:

~~~java
<S extends T> Optional<S> findOne(Example<S> example);

<S extends T> Iterable<S> findAll(Example<S> example);

<S extends T> Iterable<S> findAll(
        Example<S> example, Sort sort);

<S extends T> Page<S> findAll(
        Example<S> example, Pageable pageable);

<S extends T> long count(Example<S> example);

<S extends T> boolean exists(Example<S> example);
~~~

Các kiểu nằm trong những package sau:

~~~java
import java.util.Optional;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
~~~

Một interface chuyên biệt của adapter có thể khai báo lại một số phương thức với kiểu trả về cụ thể hơn, chẳng hạn `List<S>`. Khi viết code theo hợp đồng Commons ở trên, hãy coi kết quả nhiều phần tử là `Iterable<S>`, trừ khi kiểu repository đang dùng bảo đảm rõ hơn.

| Nhu cầu | Phương thức | Không có kết quả | Một kết quả | Nhiều kết quả |
| --- | --- | --- | --- | --- |
| Kỳ vọng tối đa một bản ghi | `findOne(example)` | `Optional.empty()` | `Optional` chứa bản ghi | Lỗi kích thước kết quả |
| Lấy các bản ghi phù hợp | `findAll(example)` | Tập rỗng | Một phần tử | Nhiều phần tử |
| Lấy một trang | `findAll(example, pageable)` | Trang không có nội dung | Tùy trang | Tùy trang |
| Đếm toàn bộ bản ghi phù hợp | `count(example)` | `0` | `1` | Số lượng phù hợp |
| Chỉ kiểm tra có bản ghi không | `exists(example)` | `false` | `true` | `true` |

Tham số `Example` phải khác `null`. Với các overload tương ứng, truyền `Sort.unsorted()` hoặc `Pageable.unpaged()` nếu cần biểu thị không sắp xếp hoặc không phân trang, thay vì truyền `null`.

`Pageable.unpaged()` có thể khiến ứng dụng nhận toàn bộ kết quả; chỉ dùng khi đã cân nhắc kích thước tập dữ liệu.

## 5. Tìm tối đa một bản ghi bằng findOne

Ví dụ tìm theo địa chỉ email:

~~~java
import java.util.Optional;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setEmail("an@example.com");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths("id");

Example<Customer> byEmail = Example.of(probe, matcher);

Optional<Customer> customer = repository.findOne(byEmail);
~~~

Các biến `repository` trong bài là một `CustomerRepository` đã được Spring inject vào service hoặc được cung cấp trong repository test. Các đoạn thao tác là những ví dụ độc lập, không phải nội dung để đặt trực tiếp vào thân interface.

### 5.1. Optional biểu diễn trường hợp không tìm thấy

~~~java
Customer requiredCustomer = repository.findOne(byEmail)
        .orElseThrow(() ->
                new IllegalArgumentException("Không tìm thấy khách hàng"));
~~~

Việc chọn exception và thông báo ở tầng ứng dụng phụ thuộc nghiệp vụ. Khi không tìm thấy là tình huống bình thường, giữ `Optional<Customer>` hoặc ánh xạ sang kết quả phù hợp; không gọi `get()` mà chưa xử lý trường hợp rỗng.

### 5.2. findOne không có nghĩa là lấy bản ghi đầu tiên

Nếu có hai khách hàng khớp `byEmail`, `findOne` không có nghĩa “chọn đại một người”. Hợp đồng của phương thức là trả về tối đa một kết quả và phát sinh `IncorrectResultSizeDataAccessException` khi có nhiều kết quả.

Vì vậy:

- Không dùng `findOne` cho bộ lọc rộng như `country = "VN"`.
- Chỉ kỳ vọng duy nhất khi điều kiện và ràng buộc dữ liệu hỗ trợ kỳ vọng đó.
- Đừng bắt lỗi nhiều kết quả rồi biến thành “không tìm thấy”; việc đó che giấu sai lệch dữ liệu hoặc thiết kế truy vấn.

Nếu nghiệp vụ chỉ cần “một bản ghi theo thứ tự xác định”, dùng truy vấn có sắp xếp và giới hạn phù hợp. Có thể minh họa bằng một trang kích thước `1`:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Optional<Customer> firstCustomer = repository
        .findAll(
                example,
                PageRequest.of(0, 1, Sort.by("id").ascending()))
        .getContent()
        .stream()
        .findFirst();
~~~

Cách này lấy bản ghi đầu tiên theo thứ tự ID và **không kiểm tra tính duy nhất** của tập kết quả. Do trả về `Page`, nó còn có thể kéo theo truy vấn đếm. Các API giới hạn hoặc fluent query khác cần được lựa chọn theo phiên bản và adapter đang dùng.

### 5.3. So khớp email không tự bảo đảm duy nhất

Nếu thêm:

~~~java
ExampleMatcher emailMatcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths("id")
        .withMatcher(
                "email",
                ExampleMatcher.GenericPropertyMatchers
                        .exact()
                        .ignoreCase());
~~~

thì bộ lọc yêu cầu so khớp email không phân biệt hoa thường theo khả năng thực thi của kho dữ liệu. Một ràng buộc duy nhất có phân biệt hoa thường có thể không bảo đảm chỉ có một bản ghi khớp điều kiện này.

Quy tắc chuẩn hóa email, collation và ràng buộc duy nhất phải thống nhất với cách tìm kiếm. `findOne` chỉ thực thi kỳ vọng về số lượng kết quả; nó không tạo ràng buộc dữ liệu.

## 6. Tìm nhiều bản ghi bằng findAll

### 6.1. Không yêu cầu thứ tự

~~~java
Iterable<Customer> customers = repository.findAll(example);

for (Customer customer : customers) {
    System.out.println(customer.getDisplayName());
}
~~~

Nếu không truyền thứ tự, không dựa vào vị trí các phần tử để suy luận khách hàng nào “mới nhất” hoặc “đầu tiên”. Thứ tự quan sát được trong một lần chạy có thể thay đổi ở lần khác.

Không ép kiểu kết quả một cách tùy tiện:

~~~java
// Không an toàn khi chỉ dựa trên hợp đồng QueryByExampleExecutor:
// List<Customer> customers =
//         (List<Customer>) repository.findAll(example);
~~~

Nếu thật sự cần một `List` từ kiểu `Iterable`, có thể tự thu thập:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Customer> customers = new ArrayList<>();
repository.findAll(example).forEach(customers::add);
~~~

Điều này đưa toàn bộ kết quả vào bộ nhớ. Với màn hình tìm kiếm hoặc tập dữ liệu lớn, ưu tiên phân trang.

### 6.2. Thêm sắp xếp ổn định

~~~java
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
        Sort.Order.asc("displayName"),
        Sort.Order.asc("id"));

Iterable<Customer> customers = repository.findAll(example, sort);
~~~

Các chuỗi `"displayName"` và `"id"` là đường dẫn thuộc tính trong mô hình domain, không phải tên cột SQL.

ID đóng vai trò phân định khi nhiều khách hàng có cùng tên. Nó làm thứ tự rõ ràng hơn, đặc biệt khi phân trang. Tuy vậy, một thứ tự xác định không ngăn dữ liệu mới hoặc dữ liệu bị xóa làm các trang thay đổi giữa hai yêu cầu.

Với API nhận tham số sắp xếp từ người dùng, ánh xạ qua danh sách thuộc tính được phép. Cách này giúp tránh lỗi do tên thuộc tính không hợp lệ và kiểm soát chi phí sắp xếp.

## 7. Tìm theo trang

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

Page<Customer> page = repository.findAll(example, pageable);

List<Customer> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

Ở đây `List` là `java.util.List`. Các giá trị có ý nghĩa khác nhau:

| Giá trị | Ý nghĩa |
| --- | --- |
| `page.getNumber()` | Chỉ số trang hiện tại, bắt đầu từ `0` |
| `page.getSize()` | Kích thước trang được yêu cầu |
| `page.getNumberOfElements()` | Số phần tử thực tế trong trang hiện tại |
| `page.getTotalElements()` | Tổng số phần tử khớp bộ lọc trên toàn bộ tập kết quả |
| `page.getTotalPages()` | Tổng số trang theo kích thước đang dùng |
| `page.hasContent()` | Trang hiện tại có phần tử hay không |
| `page.hasNext()` | Có trang tiếp theo hay không theo metadata của `Page` |

Với kích thước trang `20` và tổng `43` kết quả:

- Trang `0` có tối đa `20` phần tử.
- Trang `1` có tối đa `20` phần tử.
- Trang `2` có `3` phần tử trong trạng thái dữ liệu này.
- Trang vượt quá phạm vi có thể không có nội dung dù toàn bộ bộ lọc vẫn có kết quả.

Vì vậy, `page.hasContent()` không thay thế được `repository.exists(example)` trong mọi tình huống. Cái thứ nhất hỏi về **trang được yêu cầu**, cái thứ hai hỏi về **toàn bộ tập phù hợp**.

Để cung cấp metadata tổng số phần tử, việc lấy `Page` có thể cần một truy vấn đếm bên cạnh truy vấn nội dung. Implementation có thể bỏ qua truy vấn đếm khi suy ra được tổng từ kết quả; không nên giả định mọi lần gọi luôn thực hiện đúng hai truy vấn.

Nếu đã dùng `page.getTotalElements()`, thường không cần gọi thêm `repository.count(example)` chỉ để hiển thị cùng một tổng số. Một lần gọi bổ sung vừa tốn tài nguyên, vừa có thể thấy dữ liệu ở thời điểm khác.

Đặt giới hạn kích thước trang ở tầng nhận yêu cầu. `PageRequest.of(...)` yêu cầu số trang không âm và kích thước trang lớn hơn `0`; giới hạn nghiệp vụ như tối đa `100` phần tử do ứng dụng quyết định.

## 8. Đếm bằng count

~~~java
long matchingCustomers = repository.count(example);
~~~

`count(example)` trả về số thực thể phù hợp với điều kiện QBE. Nó không tải toàn bộ thực thể về ứng dụng để bạn đếm.

Không dùng các cách sau chỉ để lấy số lượng:

~~~java
// Tải toàn bộ dữ liệu chỉ để đếm:
long total = 0;
for (Customer ignored : repository.findAll(example)) {
    total++;
}

// getNumberOfElements() chỉ đếm nội dung của một trang:
// long total = repository.findAll(example, pageable)
//         .getNumberOfElements();
~~~

Những điểm cần phân biệt:

- `count(example)` đếm theo bộ lọc; `count()` của repository CRUD đếm toàn bộ dữ liệu thuộc phạm vi mà repository nhìn thấy.
- Kết quả có kiểu `long`. Không ép về `int` nếu không có lý do và kiểm soát giới hạn.
- Không có tham số `Pageable` trong `count(example)`: số đếm không bị giới hạn bởi kích thước trang.
- `count` không phải phép tổng hợp tiền, nhóm theo quốc gia hoặc đếm theo nhiều nhóm. Những nhu cầu đó cần công cụ truy vấn phù hợp khác.

### 8.1. Bộ lọc rỗng có thể trở thành truy vấn rất rộng

~~~java
Example<Customer> emptyExample = Example.of(new Customer());
long total = repository.count(emptyExample);
~~~

Với mô hình trong bài, probe mới có mọi thuộc tính là `null` và matcher mặc định bỏ qua `null`, nên không có điều kiện nghiệp vụ nào thu hẹp truy vấn.

Đừng khái quát rằng mọi probe mới đều rỗng: initializer, constructor, primitive hoặc các trường có giá trị mặc định có thể bổ sung điều kiện. Luôn xem **giá trị thực của probe** cùng **matcher thực đang dùng**.

Nếu màn hình yêu cầu ít nhất một tiêu chí tìm kiếm, kiểm tra yêu cầu đó trước khi gọi repository. Nếu tìm tất cả là hành vi hợp lệ, dùng phân trang và giới hạn phù hợp.

### 8.2. Đếm và đọc riêng không mặc nhiên nhất quán

Giữa hai lệnh:

~~~java
long before = repository.count(example);
Iterable<Customer> customers = repository.findAll(example);
~~~

một tiến trình khác có thể thêm hoặc xóa dữ liệu. Vì thế `before` không mặc nhiên bằng số phần tử bạn đọc sau đó.

Ngay cả việc đặt các lệnh trong một transaction cũng cần được hiểu theo mức cô lập và cơ chế nhất quán của kho dữ liệu. Không suy ra snapshot ổn định chỉ từ việc có annotation transaction.

## 9. Kiểm tra tồn tại bằng exists

~~~java
boolean hasMatchingCustomer = repository.exists(example);

if (hasMatchingCustomer) {
    System.out.println("Có ít nhất một khách hàng phù hợp");
}
~~~

`exists(example)` diễn đạt đúng nhu cầu chỉ cần biết có ít nhất một kết quả. Nó không trả về thực thể và không cho biết có bao nhiêu bản ghi.

### 9.1. Chọn exists khi chỉ cần giá trị boolean

Nếu chỉ cần giá trị `boolean`, các cách sau mang thêm công việc không cần thiết:

~~~java
// Yêu cầu đếm toàn bộ tập phù hợp dù chỉ cần biết có phần tử:
boolean presentByCount = repository.count(example) > 0;

// Sai lựa chọn nếu bộ lọc có thể khớp nhiều bản ghi:
// boolean presentByFindOne = repository.findOne(example).isPresent();
~~~

Tối ưu thực tế của `exists` phụ thuộc adapter, kho dữ liệu, index và kế hoạch truy vấn. Hợp đồng Commons không cam kết nó luôn sinh `SELECT 1`, luôn có `LIMIT 1` hoặc luôn nhanh hơn `count` trong mọi trường hợp.

Lý do đầu tiên để chọn `exists` là **đúng ngữ nghĩa**; hiệu năng cần đánh giá trên implementation thực tế.

### 9.2. Phân biệt exists và existsById

| Phương thức | Điều kiện |
| --- | --- |
| `existsById(id)` | Khóa định danh |
| `exists(example)` | Những thuộc tính và quy tắc có trong `Example` |

Nếu đã có ID và chỉ cần hỏi thực thể có tồn tại hay không, `existsById` là lựa chọn trực tiếp.

Nếu muốn hỏi “có khách hàng đang hoạt động ở Việt Nam và chưa lưu trữ không”, `exists(example)` thể hiện điều kiện phù hợp. `existsById` tự nó không kiểm tra các thuộc tính nghiệp vụ đó.

### 9.3. Kiểm tra trước khi ghi không tạo ràng buộc duy nhất

Luồng sau có thể hỗ trợ phản hồi sớm cho người dùng, nhưng không bảo đảm email duy nhất:

~~~java
if (!repository.exists(byEmail)) {
    Customer customer = new Customer();
    customer.setEmail("an@example.com");
    customer.setStatus(CustomerStatus.ACTIVE);
    customer.setArchived(false);

    repository.save(customer);
}
~~~

Hai yêu cầu đồng thời có thể cùng quan sát `false` rồi cùng ghi. Tính duy nhất phải được thực thi bằng ràng buộc hoặc cơ chế ghi nguyên tử tương ứng của kho dữ liệu; ứng dụng xử lý xung đột khi thao tác ghi thực sự được thực thi.

Quy tắc chuẩn hóa và so khớp email ở bước kiểm tra cũng phải thống nhất với ràng buộc đó. Ví dụ trên minh họa giới hạn của `exists`, không phải một triển khai hoàn chỉnh cho nghiệp vụ đăng ký khách hàng.

## 10. Dùng chung bộ lọc giữa tìm, đếm và tồn tại

Một lỗi thường gặp là màn hình tìm theo `country + status + archived` nhưng phần đếm chỉ lọc theo `country + status`. Danh sách và tổng số lúc đó không cùng ý nghĩa.

Đưa logic dựng `Example` vào một chỗ giúp các thao tác dùng chung định nghĩa điều kiện.

### 10.1. Factory tạo Example

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

public final class CustomerExamples {

    private CustomerExamples() {
    }

    public static Example<Customer> search(
            String name,
            String country,
            CustomerStatus status) {

        Customer probe = new Customer();
        probe.setDisplayName(trimToNull(name));
        probe.setCountry(trimToNull(country));
        probe.setStatus(status);
        probe.setArchived(false);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnoreNullValues()
                .withIgnorePaths("id")
                .withMatcher(
                        "displayName",
                        ExampleMatcher.GenericPropertyMatchers
                                .contains()
                                .ignoreCase());

        return Example.of(probe, matcher);
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }

        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
~~~

Quy ước của factory:

- Tên khách hàng là điều kiện “chứa”, không phân biệt hoa thường theo hỗ trợ của adapter.
- Quốc gia và trạng thái dùng điều kiện khớp giá trị tương ứng.
- Giá trị chuỗi trống sau khi trim được xem là không cung cấp bộ lọc.
- `archived = false` luôn tham gia vì màn hình chỉ tìm khách hàng chưa lưu trữ.
- Mọi điều kiện được kết hợp bằng `matchingAll()`.

`trimToNull` là quy ước ở tầng ứng dụng; QBE không tự biến chuỗi rỗng thành `null`. Mã quốc gia trong ví dụ cần được đầu vào và dữ liệu lưu trữ thống nhất, chẳng hạn đều dùng `VN`.

Nếu đổi sang `matchingAny()`, `archived = false` cũng nằm trong phép OR. Khi đó một khách hàng chưa lưu trữ có thể khớp dù tên hoặc quốc gia không đúng. Không dùng việc thay `matchingAll` bằng `matchingAny` để biểu diễn tùy tiện điều kiện kiểu `archived = false AND (name ... OR country ...)`; QBE không cung cấp cấu trúc nhóm điều kiện tổng quát này.

### 10.2. Service thực hiện ba nhu cầu

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class CustomerLookupService {

    private final CustomerRepository repository;

    public CustomerLookupService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Page<Customer> search(
            String name,
            String country,
            CustomerStatus status,
            int page,
            int size) {

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "Trang phải >= 0; kích thước phải từ 1 đến 100");
        }

        Sort sort = Sort.by(
                Sort.Order.asc("displayName"),
                Sort.Order.asc("id"));

        return repository.findAll(
                CustomerExamples.search(name, country, status),
                PageRequest.of(page, size, sort));
    }

    public long count(
            String name,
            String country,
            CustomerStatus status) {

        return repository.count(
                CustomerExamples.search(name, country, status));
    }

    public boolean exists(
            String name,
            String country,
            CustomerStatus status) {

        return repository.exists(
                CustomerExamples.search(name, country, status));
    }
}
~~~

Ba phương thức phục vụ những yêu cầu riêng:

- Trang danh sách gọi `search` và dùng metadata của `Page` khi cần tổng số.
- Một báo cáo chỉ cần số lượng có thể gọi `count`.
- Một kiểm tra chỉ cần biết có dữ liệu hay không gọi `exists`.

Không cần gọi cả ba cho cùng một màn hình nếu kết quả đã lấy đáp ứng đủ nhu cầu.

Factory tạo một probe mới mỗi lần, nên các yêu cầu không chia sẻ một đối tượng probe có thể bị sửa đồng thời. Điều này giúp quản lý trạng thái bộ lọc rõ ràng; nó không bảo đảm dữ liệu trong kho giữ nguyên giữa các truy vấn.

## 11. Minh họa kết quả trên một tập dữ liệu

Giả sử dữ liệu không thay đổi trong lúc minh họa:

| id | displayName | country | status | archived |
| --- | --- | --- | --- | --- |
| 1 | An Nguyen | VN | ACTIVE | false |
| 2 | Binh Tran | VN | ACTIVE | false |
| 3 | An Le | VN | INACTIVE | false |
| 4 | Anh Pham | VN | ACTIVE | true |
| 5 | Carol | US | ACTIVE | false |

Tạo điều kiện:

~~~java
Example<Customer> example =
        CustomerExamples.search(null, "VN", CustomerStatus.ACTIVE);
~~~

Kết quả mong đợi:

| Thao tác | Kết quả |
| --- | --- |
| `findAll(example, Sort.by("id"))` | Khách hàng có ID `1` và `2` |
| `count(example)` | `2L` |
| `exists(example)` | `true` |
| `findOne(example)` | Lỗi do nhiều hơn một kết quả |
| `findAll(example, PageRequest.of(0, 1, Sort.by("id")))` | Trang chứa ID `1`; tổng số phần tử là `2` |
| `findAll(example, PageRequest.of(1, 1, Sort.by("id")))` | Trang chứa ID `2` |
| `findAll(example, PageRequest.of(2, 1, Sort.by("id")))` | Trang không có nội dung |

Nếu thêm tên `"An"`:

~~~java
Example<Customer> narrowed =
        CustomerExamples.search("An", "VN", CustomerStatus.ACTIVE);
~~~

Lưu ý `"An"` cũng xuất hiện trong `"Binh Tran"` nếu so khớp chuỗi không phân biệt hoa thường. Điều kiện “chứa” không có nghĩa tìm một từ độc lập hoặc chỉ tìm phần tên đầu.

Để minh họa một kết quả rõ ràng hơn, dùng `"An Nguyen"`:

~~~java
Example<Customer> single =
        CustomerExamples.search(
                "An Nguyen", "VN", CustomerStatus.ACTIVE);
~~~

Trên đúng tập dữ liệu trên:

- `findOne(single)` trả về khách hàng ID `1`.
- `count(single)` bằng `1`.
- `exists(single)` bằng `true`.

Với tên `"KhongTonTai"`, các phương thức tương ứng trả về `Optional.empty()`, `0`, `false` hoặc tập/trang không có nội dung. Những kết quả này là hành vi bình thường, không phải lỗi truy vấn.

## 12. Khả năng của Commons và giới hạn theo kho dữ liệu

### 12.1. Hợp đồng chung không đồng nghĩa mọi module đều hỗ trợ giống nhau

`Example`, `ExampleMatcher` và `QueryByExampleExecutor` thuộc lớp abstraction dùng chung. Khi áp dụng vào một module cụ thể, cần xác định:

1. Repository factory của module có hỗ trợ QBE hay không.
2. Những dạng so khớp chuỗi nào được hỗ trợ và được ánh xạ thế nào.
3. Kiểu thuộc tính, đường dẫn lồng nhau và quy tắc xử lý `null` phù hợp.
4. Cách triển khai phân trang, đếm, kiểm tra tồn tại và sắp xếp.
5. Ảnh hưởng của collation, index và quy tắc so khớp hoa thường.

Không suy ra một ví dụ JPA sẽ chạy nguyên trạng trên document store hoặc các module khác. Đối với API reactive, dùng abstraction tương ứng như `ReactiveQueryByExampleExecutor` khi module hỗ trợ; không thay kiểu trả về `Optional`/`Iterable` của API đồng bộ bằng cách ép kiểu.

### 12.2. QBE phù hợp với bộ lọc theo giá trị và chuỗi đơn giản

Probe không biểu diễn tự nhiên mọi loại điều kiện. Chuyển sang công cụ phù hợp của module khi cần:

- Khoảng ngày hoặc điều kiện lớn hơn, nhỏ hơn.
- `IN` với một danh sách giá trị tùy ý.
- Các nhóm `AND`/`OR` lồng nhau.
- Truy vấn trên collection với ngữ nghĩa phức tạp.
- Join, aggregation, thống kê theo nhóm hoặc truy vấn đặc thù của kho dữ liệu.

Ví dụ, với JPA có thể cân nhắc Specifications hoặc một truy vấn tùy chỉnh. Quyết định đó phụ thuộc yêu cầu và module, không phải chỉ cần thêm dữ liệu vào probe là đủ.

### 12.3. Tối ưu theo thao tác thực sự cần

| Nhu cầu | Lựa chọn khởi đầu |
| --- | --- |
| Cần tối đa một kết quả và muốn phát hiện dữ liệu trùng | `findOne` |
| Cần hiển thị một trang và tổng số | `findAll` với `Pageable` |
| Cần toàn bộ tập nhỏ, có giới hạn rõ trong nghiệp vụ | `findAll`, thêm `Sort` khi cần |
| Cần một số đếm | `count` |
| Cần một câu trả lời có/không | `exists` |

So khớp chứa và bỏ qua hoa thường có thể ảnh hưởng cách dùng index. Không khẳng định mọi QBE đều nhanh hoặc chậm; kiểm tra kế hoạch truy vấn trên adapter và dữ liệu thực tế khi cần tối ưu.

## 13. Những lỗi cần nhận diện khi sử dụng

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Bộ lọc tưởng đúng nhưng không tìm thấy | Probe có ID, primitive mặc định hoặc trường metadata không mong muốn | Tạo probe mới, đặt rõ trường cần lọc và bỏ qua trường không dùng |
| Nhiều bản ghi nhưng `findOne` phát sinh lỗi | Nhầm “một kết quả đầu tiên” với “tối đa một kết quả” | Kiểm tra tính duy nhất hoặc chuyển sang truy vấn có thứ tự và giới hạn |
| Truy vấn vô tình áp dụng điều kiện chuỗi rỗng | Input chưa được chuẩn hóa | Quy định rõ chuỗi rỗng là giá trị hay là thiếu bộ lọc |
| Tổng số khác độ dài danh sách đang hiển thị | So sánh toàn bộ tập với một trang | Dùng đúng `getNumberOfElements()` và `getTotalElements()` |
| Danh sách và bộ đếm có điều kiện khác nhau | Xây probe/matcher lặp lại ở nhiều nơi | Dùng chung factory dựng `Example` |
| Kết quả thay đổi giữa các lần gọi | Dữ liệu đồng thời thay đổi hoặc probe bị sửa | Tách trạng thái probe; chọn cơ chế nhất quán theo nhu cầu |
| `exists` trả về `false` nhưng khi ghi vẫn bị trùng | Khoảng đua giữa kiểm tra và ghi | Dựa vào ràng buộc/cơ chế ghi của kho dữ liệu |
| Code biên dịch nhưng repository không khởi tạo được | Adapter không hỗ trợ interface/khả năng đã khai báo | Kiểm tra hỗ trợ QBE của đúng module và phiên bản |
| Đếm hoặc kiểm tra tồn tại dùng nhiều bộ nhớ | Lấy toàn bộ thực thể rồi xử lý trong Java | Dùng `count` hoặc `exists` trực tiếp |

Khi thực hành, bắt đầu bằng một `Example` có điều kiện rõ ràng, sau đó chọn thao tác theo kết quả cần nhận. `findOne` thể hiện kỳ vọng về số lượng, `findAll` lấy dữ liệu, `count` lấy số lượng và `exists` trả lời về sự tồn tại. Tách bốn mục đích này giúp code repository rõ ý nghĩa và tránh truy vấn vượt nhu cầu.
