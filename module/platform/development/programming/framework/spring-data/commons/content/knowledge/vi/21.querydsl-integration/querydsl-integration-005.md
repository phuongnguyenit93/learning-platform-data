# QSort và biểu thức sắp xếp Querydsl trong phạm vi hỗ trợ

## 1. QSort dùng để làm gì?

Spring Data Commons thường biểu diễn sắp xếp bằng `Sort` và tên thuộc tính:

~~~java
Sort sort = Sort.by(
        Sort.Order.asc("displayName"),
        Sort.Order.asc("id"));
~~~

Khi đã dùng Querydsl, mô hình Q-type cho phép biểu diễn thứ tự qua các đường dẫn và biểu thức có kiểu:

~~~java
QCustomer customer = QCustomer.customer;

OrderSpecifier<String> byName =
        customer.displayName.asc();
~~~

`QSort` là cầu nối giữa hai cách biểu diễn này. Nó kế thừa `Sort` và giữ các `OrderSpecifier<?>` của Querydsl để một implementation có hỗ trợ có thể áp dụng chúng vào truy vấn.

~~~java
QSort sort = new QSort(
        customer.displayName.asc(),
        customer.id.asc());
~~~

Điểm cần nhớ:

> QSort mang theo biểu thức sắp xếp Querydsl; khả năng thực thi biểu thức đó thuộc về Spring Data module, executor và kho dữ liệu cụ thể.

Nó không biến mọi repository nhận tham số `Sort` thành một Querydsl executor. Nó cũng không tạo join, điều kiện lọc, projection hoặc index.

Sau bài này, bạn có thể:

- Phân biệt `Sort.Order`, `OrderSpecifier` và `QSort`.
- Dùng `QSort` với repository có tích hợp Querydsl phù hợp.
- Kết hợp thứ tự Querydsl với `PageRequest`.
- Chọn thứ tự có tiêu chí phân định khi trùng giá trị.
- Nhận diện giới hạn về biểu thức, alias, giá trị `null` và phạm vi store.

## 2. Ba kiểu biểu diễn không nên nhầm lẫn

| Kiểu | Nguồn | Biểu diễn | Ví dụ |
| --- | --- | --- | --- |
| `Sort.Order` | Spring Data Commons | Hướng và đường dẫn thuộc tính | `Sort.Order.asc("displayName")` |
| `OrderSpecifier<T>` | Querydsl | Hướng và biểu thức Querydsl có kiểu | `customer.displayName.asc()` |
| `QSort` | Spring Data Commons | Một `Sort` giữ các `OrderSpecifier<?>` | `new QSort(customer.id.desc())` |

Các import chính:

~~~java
import com.querydsl.core.types.OrderSpecifier;
import org.springframework.data.domain.Sort;
import org.springframework.data.querydsl.QSort;
~~~

### 2.1. Q-type cung cấp kiểm tra kiểu ở mức mã nguồn

Với Q-type đã được sinh đúng từ mô hình domain:

~~~java
QCustomer customer = QCustomer.customer;

OrderSpecifier<String> byName =
        customer.displayName.asc();

OrderSpecifier<Long> byId =
        customer.id.asc();
~~~

Trình biên dịch có thể phát hiện việc tham chiếu một thuộc tính Q-type không tồn tại. Các thao tác chuỗi, số hoặc thời gian cũng phụ thuộc kiểu biểu thức tương ứng.

Tuy nhiên, kiểm tra kiểu không bảo đảm:

- Biểu thức thuộc đúng root hoặc alias của truy vấn đang chạy.
- Executor hỗ trợ nhận và diễn giải biểu thức đó.
- Một hàm được hỗ trợ bởi provider và kho dữ liệu.
- Truy vấn có hiệu năng phù hợp.
- Thứ tự có cùng ngữ nghĩa collation trên mọi store.

Q-type cần được sinh lại phù hợp khi mô hình thay đổi. Một file sinh tự động cũ không phải bằng chứng schema và entity vẫn đồng bộ.

### 2.2. QSort không phải một predicate

~~~java
BooleanExpression predicate =
        customer.country.eq("VN")
                .and(customer.active.isTrue());

QSort sort = new QSort(
        customer.displayName.asc(),
        customer.id.asc());
~~~

`predicate` chọn những khách hàng phù hợp. `sort` xác định thứ tự của tập đã được chọn. Hai đối tượng có vai trò khác nhau và được truyền vào API theo các tham số tương ứng.

Các ví dụ dùng `BooleanExpression` từ:

~~~java
import com.querydsl.core.types.dsl.BooleanExpression;
~~~

## 3. Chuẩn bị ví dụ với một adapter cụ thể

Bài dùng **Spring Data JPA** để minh họa một nhánh tích hợp Querydsl. Các kiểu Commons trong bài không tự cung cấp implementation JPA hoặc khả năng truy vấn cho mọi store.

### 3.1. Mô hình domain

~~~java
import java.time.Instant;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;
    private String country;
    private Boolean active;
    private Instant createdAt;

    public Customer() {
    }

    public Long getId() { return id; }
    public String getDisplayName() { return displayName; }
    public String getCountry() { return country; }
    public Boolean getActive() { return active; }
    public Instant getCreatedAt() { return createdAt; }

    public void setDisplayName(String value) { displayName = value; }
    public void setCountry(String value) { country = value; }
    public void setActive(Boolean value) { active = value; }
    public void setCreatedAt(Instant value) { createdAt = value; }
}
~~~

Ví dụ giả định `QCustomer` đã được sinh bằng annotation processor Querydsl tương thích với bộ thư viện JPA/Jakarta đang dùng và được đưa vào quá trình biên dịch. Không tự viết một Q-type giả để che việc thiếu cấu hình sinh mã.

`createdAt` trong entity minh họa là một thuộc tính thời gian thông thường. Nếu cần tự động gán thời điểm tạo bằng auditing, phải cấu hình khả năng đó riêng; `QSort` không tạo hoặc cập nhật metadata auditing.

### 3.2. Repository có QuerydslPredicateExecutor

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
~~~

`QuerydslPredicateExecutor` là abstraction của Commons. Spring Data module có hỗ trợ sẽ cung cấp implementation tương ứng.

Chỉ thêm interface trên không thể bù cho thư viện thiếu, Q-type chưa sinh hoặc adapter không có hỗ trợ Querydsl phù hợp. Khả năng cần được xác định theo đúng module và phiên bản của ứng dụng.

Trong các ví dụ tiếp theo, `repository` là một `CustomerRepository` đã được inject vào service hoặc cung cấp trong repository test. Các đoạn thao tác là những ví dụ độc lập.

### 3.3. Đi qua đúng nhánh thực thi

~~~mermaid
flowchart LR
    Q["QCustomer và biểu thức có kiểu"] --> O["OrderSpecifier"]
    O --> S["QSort"]
    P["Predicate"] --> E["Executor hỗ trợ Querydsl"]
    S --> E
    E --> A["Adapter JPA trong ví dụ"]
    A --> D["Provider và kho dữ liệu"]
~~~

Cấu trúc này có nhiều điểm kiểm tra: API Commons mang được thứ tự; executor phải hiểu Querydsl; adapter và kho dữ liệu phải thực thi được biểu thức.

## 4. Sắp xếp theo thuộc tính domain

### 4.1. Kết hợp nhiều tiêu chí trong một QSort

~~~java
QCustomer customer = QCustomer.customer;

BooleanExpression predicate =
        customer.country.eq("VN")
                .and(customer.active.isTrue());

QSort sort = new QSort(
        customer.displayName.asc(),
        customer.id.asc());

Iterable<Customer> customers =
        repository.findAll(predicate, sort);
~~~

Thứ tự trong constructor có ý nghĩa:

1. So sánh theo `displayName` tăng dần.
2. Khi tên bằng nhau theo quy tắc so sánh của kho dữ liệu, dùng `id` tăng dần để phân định.

Đây là thứ tự từ trái sang phải, không phải hai lựa chọn độc lập.

Viết nhiều specifier trong một `QSort` cũng giúp tránh phải trộn một phần thứ tự Querydsl với một phần `Sort` thông thường mà chưa rõ quy tắc hỗ trợ.

### 4.2. Sắp theo thời điểm thực sự cần dùng

~~~java
QSort newestFirst = new QSort(
        customer.createdAt.desc(),
        customer.id.desc());

Iterable<Customer> customers =
        repository.findAll(predicate, newestFirst);
~~~

Nếu nghiệp vụ yêu cầu “mới tạo trước”, hãy dùng thuộc tính thời gian phản ánh việc tạo. ID lớn hơn không mặc nhiên đồng nghĩa được tạo gần đây hơn.

Với dữ liệu có thời điểm tạo bằng nhau, ID đóng vai trò phân định. Nếu thời điểm tạo có thể `null`, phải xác định cách xử lý `null` phù hợp thay vì dựa vào thứ tự mặc định không được công bố.

### 4.3. Khi không cần QSort trung gian

`QuerydslPredicateExecutor` còn có overload nhận trực tiếp các specifier:

~~~java
Iterable<Customer> customers = repository.findAll(
        predicate,
        customer.displayName.asc(),
        customer.id.asc());
~~~

Cách này phù hợp khi chỉ lấy tập kết quả theo thứ tự và API đang dùng hỗ trợ overload đó.

`QSort` đặc biệt hữu ích khi cần đưa các specifier vào một API nhận `Sort`, chẳng hạn phần sắp xếp bên trong `PageRequest`, **và** nhánh thực thi phía sau có hiểu QSort.

Không suy ra một overload nhận `OrderSpecifier` sẽ tồn tại trên mọi loại repository chỉ vì chúng đều thuộc Spring Data.

## 5. Phân trang với QSort

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

QSort sort = new QSort(
        customer.displayName.asc(),
        customer.id.asc());

Pageable pageable = PageRequest.of(0, 20, sort);

Page<Customer> page =
        repository.findAll(predicate, pageable);
~~~

Lời gọi này đi qua nhánh `findAll(Predicate, Pageable)` của Querydsl executor trong ví dụ, thay vì giả định mọi phương thức CRUD có nhận `Sort` đều xử lý cùng một cách.

Các khái niệm cần phân biệt:

| Giá trị | Ý nghĩa |
| --- | --- |
| `PageRequest.of(0, 20, sort)` | Yêu cầu trang đầu, kích thước 20 và thứ tự đã chọn |
| `page.getNumberOfElements()` | Số phần tử thực tế của trang hiện tại |
| `page.getTotalElements()` | Tổng số phần tử phù hợp theo metadata trang |
| `page.getContent()` | Nội dung trang hiện tại |
| `page.hasNext()` | Có trang tiếp theo theo metadata hay không |

Số trang bắt đầu từ `0`. Kích thước trang phải lớn hơn `0`; ứng dụng nên quy định giới hạn tối đa phù hợp.

### 5.1. Vì sao cần tiêu chí phân định?

Nếu chỉ dùng `displayName.asc()` và nhiều khách hàng cùng tên, kho dữ liệu không buộc phải trả họ theo một thứ tự nội bộ cố định. Khi chia trang, điều này có thể khiến ranh giới trang khó dự đoán.

Thêm một khóa duy nhất như `id` giúp xác định rõ thứ tự khi dữ liệu được so sánh trên cùng trạng thái.

Nó không tạo snapshot và không ngăn:

- Bản ghi mới được thêm vào trước vị trí đang đọc.
- Bản ghi bị xóa làm offset thay đổi.
- Thuộc tính sắp xếp được cập nhật giữa các yêu cầu.

Nếu nghiệp vụ cần cơ chế đọc liên tục theo cursor hoặc snapshot, phải chọn API và cơ chế nhất quán phù hợp. `QSort` chỉ biểu diễn thứ tự.

### 5.2. QSort không làm truy vấn đếm có cùng chi phí với đọc trang

`Page` có thể cần một truy vấn đếm để cung cấp tổng số. Implementation có thể tối ưu và không thực hiện đếm riêng khi suy ra được tổng.

Biểu thức sắp xếp áp dụng cho việc đọc nội dung; không nên cho rằng tổng số được tính bằng cách tải rồi sắp xếp toàn bộ kết quả trong ứng dụng. Cũng không cam kết mọi lần lấy trang đều sinh đúng hai truy vấn.

Nếu đã có tổng cần dùng từ `Page`, thường không cần gọi thêm `count(predicate)` chỉ để hiển thị lại cùng thông tin.

## 6. Sắp xếp bằng biểu thức Querydsl

### 6.1. Ví dụ dùng một biểu thức chuỗi

Trong một nhánh JPA/Querydsl hỗ trợ biểu thức tương ứng, có thể biểu diễn ý định sắp theo tên đã chuyển về chữ thường:

~~~java
QSort sort = new QSort(
        customer.displayName.lower().asc(),
        customer.id.asc());

Iterable<Customer> customers =
        repository.findAll(predicate, sort);
~~~

Điểm khác với `Sort.by("displayName")` là mục tiêu sắp xếp ở đây là một **biểu thức**, không chỉ là đường dẫn thuộc tính.

Để ví dụ hoạt động như mong đợi, cần đồng thời:

1. Nhánh repository sử dụng các `OrderSpecifier` gốc.
2. Querydsl adapter chuyển được biểu thức vào ngôn ngữ truy vấn.
3. Provider và kho dữ liệu hỗ trợ biểu thức đó.
4. Ngữ nghĩa chuyển chữ thường và collation đáp ứng yêu cầu.

Đây là ví dụ mở rộng có điều kiện hỗ trợ, không phải cam kết rằng bất kỳ biểu thức Querydsl nào cũng dùng được qua QSort.

### 6.2. lower không giải quyết mọi quy tắc ngôn ngữ

`lower()` không tự chuẩn hóa dấu, không tự định nghĩa cách xử lý Unicode và không bảo đảm cùng thứ tự cho mọi ngôn ngữ.

Ví dụ, yêu cầu sắp tên tiếng Việt theo một quy tắc nghiệp vụ cụ thể cần được xác định cùng collation hoặc chiến lược chuẩn hóa phù hợp. Chỉ thêm `lower()` không đủ để suy ra kết quả.

Biểu thức tính trên cột cũng có thể ảnh hưởng cách dùng index. Hiệu năng phải được đánh giá theo truy vấn, dữ liệu và cấu hình thực tế của store.

### 6.3. Không chuyển biểu thức thành tên thuộc tính dạng chuỗi

~~~java
// Không dùng chuỗi mô phỏng hàm như một đường dẫn thuộc tính:
// Sort.by("lower(displayName)");
~~~

`Sort` thông thường dùng các đường dẫn thuộc tính theo hợp đồng của API đang nhận nó. Chuỗi trông giống một hàm không tự trở thành biểu thức Querydsl hợp lệ.

Tương tự, không chuyển một danh sách specifier sang vài `Sort.Order` rồi mặc định mọi thông tin biểu thức, null handling và kiểu đều được giữ nguyên.

Nếu cần biểu thức Querydsl, hãy giữ nó dưới dạng `OrderSpecifier` và sử dụng một nhánh thực thi có hỗ trợ.

## 7. Hướng sắp xếp và xử lý null

### 7.1. Yêu cầu null đứng cuối

Querydsl cung cấp khả năng biểu diễn thứ tự đối với giá trị `null` trên specifier:

~~~java
OrderSpecifier<String> byName =
        customer.displayName.asc().nullsLast();

QSort sort = new QSort(
        byName,
        customer.id.asc());
~~~

`nullsLast()` yêu cầu đưa tên `null` ra sau các giá trị khác. Có thể dùng `nullsFirst()` khi muốn chúng đứng trước.

Cần phân biệt:

- Tên `null`.
- Tên là chuỗi rỗng.
- Tên chỉ có khoảng trắng.
- Các tên bằng nhau theo collation.

Một yêu cầu null handling không tự chuẩn hóa những trạng thái dữ liệu này thành cùng một giá trị.

Khả năng biểu diễn trong `OrderSpecifier` không bảo đảm mọi provider và store đều thực thi được theo cùng cách. Cần xác định hỗ trợ thực tế, thay vì để mặc định của database trở thành một bảo đảm ngầm của API.

### 7.2. Tạo lại specifier khi đổi hướng

Nếu cần đổi từ tăng sang giảm, biểu diễn trực tiếp hướng mong muốn:

~~~java
QSort ascending = new QSort(
        customer.displayName.asc(),
        customer.id.asc());

QSort descending = new QSort(
        customer.displayName.desc(),
        customer.id.asc());
~~~

Hai cấu hình này đều giữ ID tăng dần làm tiêu chí phân định; không phải cứ đổi hướng tên là bắt buộc đổi hướng tất cả tiêu chí.

Do `QSort` là một lớp con của `Sort`, đừng suy ra mọi thao tác biến đổi hoặc dựng lại một `Sort` bất kỳ sẽ giữ nguyên các specifier và toàn bộ ngữ nghĩa biểu thức. Khi cần cấu hình Querydsl, dựng rõ các specifier cho cấu hình đó là cách dễ đánh giá.

Không cần dựa vào việc trộn nhiều kiểu sort hoặc một phép biến đổi kế thừa mà chưa xác định hợp đồng của nó.

## 8. Chọn thứ tự động bằng một danh sách có giới hạn

Ứng dụng thường nhận yêu cầu như “tên tăng dần”, “tên giảm dần” hoặc “mới tạo trước”. Có thể biểu diễn các lựa chọn nghiệp vụ bằng enum:

~~~java
public enum CustomerOrder {
    NAME_ASC,
    NAME_DESC,
    CREATED_DESC
}
~~~

Sau đó ánh xạ từng lựa chọn sang specifier đã biết. Cách này giữ logic sắp xếp trong mã nguồn thay vì nhận một chuỗi biểu thức tùy ý rồi đoán cách thực thi.

### 8.1. Service minh họa hoàn chỉnh

Ví dụ dưới đây dùng các kiểu `Customer`, `QCustomer` và `CustomerRepository` ở phần chuẩn bị.

~~~java
import java.util.Locale;
import java.util.Objects;
import com.querydsl.core.types.dsl.BooleanExpression;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.querydsl.QSort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Page<Customer> search(
            String country,
            CustomerOrder order,
            int page,
            int size) {

        if (country == null || country.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "Phải cung cấp mã quốc gia");
        }

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "Trang phải >= 0; kích thước từ 1 đến 100");
        }

        Objects.requireNonNull(order, "order");

        String countryCode =
                country.trim().toUpperCase(Locale.ROOT);

        QCustomer customer = QCustomer.customer;

        BooleanExpression predicate =
                customer.country.eq(countryCode)
                        .and(customer.active.isTrue());

        QSort sort = toSort(customer, order);

        PageRequest pageable =
                PageRequest.of(page, size, sort);

        return repository.findAll(predicate, pageable);
    }

    private static QSort toSort(
            QCustomer customer,
            CustomerOrder order) {

        return switch (order) {
            case NAME_ASC -> new QSort(
                    customer.displayName.asc(),
                    customer.id.asc());

            case NAME_DESC -> new QSort(
                    customer.displayName.desc(),
                    customer.id.asc());

            case CREATED_DESC -> new QSort(
                    customer.createdAt.desc(),
                    customer.id.desc());
        };
    }
}
~~~

Ví dụ dùng cú pháp switch expression phù hợp với Java 17 trở lên. Mỗi kiểu `public` đặt trong file Java tương ứng khi đưa vào ứng dụng.

Quy ước dữ liệu của service là mã quốc gia được lưu dưới dạng chữ hoa như `VN`. Chuẩn hóa đầu vào không tự sửa dữ liệu đã lưu khác quy ước.

Ví dụ cũng giả định nghiệp vụ đã quy định dữ liệu và thứ tự cho các trường có thể `null`. Nếu đây là yêu cầu quan trọng, bổ sung null handling đã được xác nhận là phù hợp với provider và store, hoặc đặt ràng buộc dữ liệu tương ứng.

### 8.2. Vì sao không nhận trực tiếp tên biểu thức?

Một lựa chọn nghiệp vụ như `CREATED_DESC` có thể được ánh xạ sang đúng hai tiêu chí `createdAt DESC, id DESC`. Caller không cần biết tên thuộc tính nội bộ hoặc cú pháp Querydsl.

Điều này giúp:

- Chỉ cung cấp những thứ tự ứng dụng thực sự hỗ trợ.
- Kiểm soát các biểu thức có chi phí cao.
- Xử lý đầu vào không hợp lệ một cách rõ ràng.
- Thay đổi cấu trúc domain mà không biến tên field nội bộ thành hợp đồng bên ngoài.

Nếu đầu vào đến từ tham số web dạng `sort=...`, không suy ra nó đã trở thành `OrderSpecifier` hợp lệ. Cần có bước ánh xạ chủ động theo những lựa chọn được công bố.

## 9. Hiểu đúng phạm vi hỗ trợ

### 9.1. Nhận Sort không đồng nghĩa hiểu QSort

Một phương thức có tham số `Sort` có thể chỉ diễn giải các thuộc tính như `"displayName"`. Một nhánh khác có tích hợp Querydsl có thể nhận ra `QSort` và sử dụng các `OrderSpecifier` gốc.

Vì vậy, hai điểm sau không đủ để kết luận một biểu thức được hỗ trợ:

- `QSort` có thể truyền vào tham số `Sort` về mặt kiểu Java.
- Đoạn code đã biên dịch thành công.

Cần dùng đúng nhánh thực thi của module. Bài minh họa qua `QuerydslPredicateExecutor.findAll(predicate, sort)` và `findAll(predicate, pageable)` trong tích hợp JPA.

Không lấy ví dụ này để cam kết hành vi giống hệt cho một lời gọi `findAll(sort)` bất kỳ hoặc cho một repository của module khác.

### 9.2. QSort không tạo root và join theo nhu cầu

Biểu thức trong sort phải thuộc ngữ cảnh truy vấn mà executor tạo ra.

~~~java
QCustomer customer = QCustomer.customer;
QSort sort = new QSort(customer.displayName.asc());
~~~

Trong ví dụ, root được lấy theo Q-type thông thường của domain. Không tự tạo một alias khác rồi giả định executor biết alias đó:

~~~java
// Không coi alias tự chọn này là mặc nhiên tương thích:
// QCustomer another = new QCustomer("anotherCustomer");
// QSort sort = new QSort(another.displayName.asc());
~~~

Nếu truy vấn gốc không có alias tương ứng, một biểu thức đúng kiểu vẫn có thể không hợp lệ trong truy vấn.

Tương tự, sắp theo dữ liệu của một quan hệ không tự yêu cầu QSort tạo join đúng ngữ nghĩa. Những truy vấn cần kiểm soát join, fetch join, grouping hoặc số hàng nên được thực hiện bằng API thích hợp của module, thường qua repository fragment hay truy vấn tùy chỉnh.

Không dùng QSort để thay thế một thiết kế truy vấn vốn cần kiểm soát nhiều thành phần hơn thứ tự.

### 9.3. Quan hệ nhiều phần tử làm vấn đề phức tạp hơn

Yêu cầu “sắp khách hàng theo giá trị đơn hàng” còn thiếu ý nghĩa khi mỗi khách hàng có nhiều đơn:

- Theo đơn mới nhất?
- Theo tổng giá trị?
- Theo đơn có giá trị lớn nhất?
- Hay sắp các hàng sau join thay vì sắp khách hàng?

Chỉ tham chiếu một đường dẫn trong Q-type không trả lời được những câu hỏi đó. Cần xác định phép tổng hợp hoặc cách chọn dữ liệu quan hệ trước, rồi chọn công cụ truy vấn phù hợp.

Trong trường hợp này, lỗi không nằm ở việc chưa bọc biểu thức bằng QSort. Yêu cầu truy vấn cần được diễn đạt đầy đủ hơn.

### 9.4. Mỗi store có phạm vi riêng

| Lớp khả năng | Câu hỏi cần trả lời |
| --- | --- |
| Module | Module và phiên bản có tích hợp Querydsl phù hợp không? |
| Repository/executor | Phương thức đang gọi có sử dụng QSort và specifier gốc không? |
| Model | Q-type, root và đường dẫn có thuộc đúng domain không? |
| Biểu thức | Adapter chuyển được phép toán hoặc hàm này không? |
| Provider/store | Ngôn ngữ truy vấn, null handling và collation có phù hợp không? |
| Hiệu năng | Index và kế hoạch truy vấn có đáp ứng kích thước dữ liệu không? |

Đây là các tầng giới hạn của một abstraction dùng chung, không phải một danh sách tính năng mặc định của mọi Spring Data module.

Với reactive repository hoặc một công cụ truy vấn đặc thù khác, dùng hợp đồng tương ứng đã được module hỗ trợ. Không ép các API đồng bộ trong bài thành một API khác chỉ bằng cách đổi kiểu trả về.

## 10. Minh họa thứ tự và phân trang

Giả sử các khách hàng dưới đây đều thuộc quốc gia `VN` và có `active = true`. Dữ liệu giữ nguyên trong lúc minh họa.

| id | displayName | createdAt |
| --- | --- | --- |
| 11 | An | 2026-01-01T08:00:00Z |
| 12 | Binh | 2026-01-03T08:00:00Z |
| 13 | An | 2026-01-02T08:00:00Z |
| 14 | Chi | 2026-01-03T08:00:00Z |

Với tên ASCII trong dữ liệu minh họa và quy tắc so sánh phù hợp:

| Cấu hình | Dãy ID mong đợi |
| --- | --- |
| `displayName ASC, id ASC` | `11, 13, 12, 14` |
| `displayName DESC, id ASC` | `14, 12, 11, 13` |
| `createdAt DESC, id DESC` | `14, 12, 13, 11` |

Khi dùng `displayName ASC, id ASC` với kích thước trang `2`:

- Trang `0` chứa ID `11` và `13`.
- Trang `1` chứa ID `12` và `14`.
- Trang vượt phạm vi có thể rỗng dù bộ lọc vẫn có kết quả ở các trang trước.

Hai người cùng tên `An` được phân định theo ID. Hai người có cùng `createdAt` trong cấu hình mới nhất trước được phân định theo ID giảm dần.

Nếu thêm dữ liệu có tên `null`, kết quả phụ thuộc chính sách null đã chọn và hỗ trợ thực tế. Không tự chèn giá trị đó vào một thứ tự kỳ vọng dựa trên thói quen của một database khác.

Bảng trên mô tả hành vi mong muốn của ví dụ, không phải kết quả kiểm thử đã chạy trên một provider cụ thể.

## 11. Chi phí truy vấn và giới hạn thực tế

### 11.1. Sắp xếp có thể cần xử lý nhiều dữ liệu

Trang chỉ trả về `20` phần tử không có nghĩa store chỉ phải xét `20` phần tử. Điều kiện lọc, thứ tự, index và vị trí trang quyết định công việc thực tế.

Ví dụ, một thứ tự tính từ `lower(displayName)` có thể không dùng được index giống một thứ tự trực tiếp theo `displayName`. Cần xem cấu hình index hoặc phương án lưu giá trị chuẩn hóa khi hiệu năng thực sự đòi hỏi.

Không thêm một biểu thức chỉ vì nó biên dịch được rồi mặc định chi phí ngang với sắp theo khóa.

### 11.2. Thứ tự không khắc phục dữ liệu hoặc điều kiện sai

Nếu predicate bỏ sót điều kiện `active`, QSort vẫn sắp xếp một tập dữ liệu sai so với nghiệp vụ. Nếu metadata thời gian chưa được gán đúng, thứ tự `createdAt` cũng không thể đại diện chính xác cho việc tạo mới.

Nên đọc một lời gọi truy vấn theo các phần riêng:

1. Domain và root nào đang được dùng?
2. Predicate chọn tập kết quả nào?
3. Specifier xác định thứ tự gì?
4. Phân trang hoặc giới hạn nào được áp dụng?
5. Adapter thực thi có hỗ trợ toàn bộ những phần đó không?

### 11.3. Không coi transaction là bảo đảm cho mọi yêu cầu đọc

Annotation transaction trong service minh họa thuộc phạm vi JPA của ứng dụng. QSort không tự tạo transaction, không chọn mức cô lập và không tạo tính nhất quán xuyên nhiều store.

Nếu yêu cầu cần so sánh nhiều trang trong một trạng thái dữ liệu cố định, cần một thiết kế nhất quán riêng. Một thứ tự rõ ràng chỉ giải quyết phần thứ tự.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy `QCustomer` lúc biên dịch | Chưa sinh Q-type hoặc chưa đưa generated sources vào biên dịch | Cấu hình annotation processing tương thích |
| Biểu thức đúng kiểu nhưng truy vấn lỗi | Sai root/alias hoặc thiếu hỗ trợ từ adapter/provider | Dùng đúng ngữ cảnh truy vấn và xác định khả năng thực thi |
| Chuỗi như `lower(displayName)` bị coi là đường dẫn sai | Dùng `Sort` theo thuộc tính để biểu diễn hàm | Dùng biểu thức Querydsl qua nhánh hỗ trợ hoặc API tùy chỉnh phù hợp |
| Hai trang có thứ tự không ổn định khi trùng tên | Thiếu tiêu chí phân định | Thêm khóa phân định như ID |
| Kết quả giữa các lần đọc thay đổi | Dữ liệu bị thêm, xóa hoặc cập nhật | Xác định cơ chế nhất quán và cách phân trang theo nhu cầu |
| Null đứng khác vị trí mong muốn | Dựa vào mặc định của store | Quy định null handling và xác định hỗ trợ thực tế |
| Sắp xếp tên có dấu không đúng yêu cầu | Ngữ nghĩa collation/chuẩn hóa chưa được định nghĩa | Chọn quy tắc ngôn ngữ phù hợp và xác nhận trên dữ liệu liên quan |
| Đổi nhánh repository thì biểu thức không còn dùng được | Nhánh mới chỉ hiểu Sort theo thuộc tính | Dùng executor có hỗ trợ Querydsl cho yêu cầu đó |
| Sắp theo quan hệ nhiều phần tử cho kết quả khó hiểu | Thiếu định nghĩa chọn hay tổng hợp dữ liệu quan hệ | Làm rõ truy vấn rồi dùng công cụ phù hợp của module |
| Trang nhỏ nhưng truy vấn chậm | Thứ tự, hàm hoặc offset khiến store xử lý nhiều dữ liệu | Đánh giá kế hoạch truy vấn và index theo trường hợp thực tế |

`QSort` hữu ích khi cần giữ các biểu thức thứ tự Querydsl trong một hợp đồng dùng `Sort`. Cách sử dụng rõ ràng là tạo specifier đúng domain, thêm tiêu chí phân định khi cần và đưa chúng qua executor thực sự có hỗ trợ. Những bảo đảm về hàm, join, null, collation và hiệu năng vẫn thuộc phạm vi adapter và kho dữ liệu.
