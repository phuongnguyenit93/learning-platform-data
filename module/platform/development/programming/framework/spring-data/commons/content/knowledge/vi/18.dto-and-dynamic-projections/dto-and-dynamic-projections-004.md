# Projection động qua tham số Class<T>

## 1. Một điều kiện truy vấn, nhiều góc nhìn kết quả

Một ứng dụng có thể cần đọc cùng tập khách hàng theo nhiều cách:

- Màn hình danh sách chỉ cần họ và tên.
- Một tác vụ liên hệ cần tên và email.
- Một luồng nghiệp vụ khác cần domain object đầy đủ.

Nếu mỗi hình dạng kết quả đều được cố định trong chữ ký riêng, repository có thể xuất hiện nhiều query method gần giống nhau. Dynamic projection cho phép caller chọn kiểu kết quả khi gọi một query method, bằng cách truyền class token tương ứng.

Mẫu khai báo cốt lõi là:

```java
<T> List<T> findByStatus(String status, Class<T> projectionType);
```

Ba phần liên kết với nhau:

1. `<T>` khai báo tham số kiểu của phương thức.
2. `List<T>` nói rằng mỗi phần tử kết quả có kiểu T.
3. `Class<T>` cung cấp kiểu đích cụ thể tại thời điểm gọi.

Ví dụ, truyền `CustomerNameView.class` đi cùng kết quả `List<CustomerNameView>`.

Trong phạm vi **SPRING_DATA_COMMONS**, đây là hợp đồng hỗ trợ lựa chọn projection ở query method. Việc mô-đun kho dữ liệu thực thi query, tạo projection hay DTO và tối ưu dữ liệu đọc vẫn phải được xác nhận theo mô-đun và phiên bản đang dùng.

## 2. Class<T> là class token, không phải dữ liệu khách hàng

`CustomerNameView.class` là một đối tượng Class mô tả kiểu Java. Nó không phải một instance CustomerNameView và không phải một giá trị để so sánh với cột dữ liệu trong ví dụ này.

Với chữ ký dynamic projection đúng hợp đồng, framework sử dụng class token để xác định kiểu kết quả cần tạo. Caller không cần tự tạo proxy cho interface và không cần khởi tạo DTO rỗng rồi đưa vào repository.

Có thể hình dung luồng xử lý:

```text
Caller chọn kiểu đích
    → truyền điều kiện query cùng Class<T>
    → Spring Data nhận diện tham số chọn projection
    → mô-đun thực thi truy vấn phù hợp
    → ánh xạ kết quả sang kiểu đích được hỗ trợ
    → trả List<T>, Optional<T> hoặc wrapper được khai báo
```

Việc chọn kiểu kết quả không tự đổi điều kiện `status`, tenant, giới hạn dữ liệu hoặc quy tắc sắp xếp của query. Nếu hai use case có điều kiện nghiệp vụ khác nhau, chúng vẫn cần hợp đồng truy vấn phản ánh sự khác nhau đó.

## 3. Mô hình dữ liệu và các kiểu kết quả

Giả sử domain type `Customer` đã được mapping với các thuộc tính:

| Thuộc tính | Kiểu minh họa | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh khách hàng |
| `firstName` | `String` | Tên gọi |
| `lastName` | `String` | Họ |
| `email` | `String` | Email liên hệ |
| `status` | `String` | Trạng thái |

Domain type có các accessor tương ứng. Mapping cụ thể do mô-đun kho dữ liệu quyết định.

### 3.1. Interface projection cho danh sách tên

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();
}
```

Các accessor cần khớp với dữ liệu được ánh xạ. Trong đường xử lý interface projection thông thường, Spring Data tạo một proxy thực hiện interface này.

Nếu thêm default method dẫn xuất từ hai getter, chẳng hạn ghép tên hiển thị, phương thức đó vẫn tính bằng Java trên projection. Dynamic projection không tự dịch thân default method thành biểu thức database.

### 3.2. DTO cho tác vụ liên hệ

```java
public final class CustomerContactDto {

    private final String firstName;
    private final String email;

    public CustomerContactDto(String firstName, String email) {
        this.firstName = firstName;
        this.email = email;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getEmail() {
        return email;
    }
}
```

Ví dụ dùng một constructor để làm rõ dữ liệu đầu vào. Với các cơ chế suy ra trường DTO từ tên tham số constructor, metadata tên tham số cần được giữ lại, chẳng hạn bằng tùy chọn compiler `-parameters` theo cấu hình dự án.

Một constructor có đúng số lượng tham số nhưng tên hoặc kiểu không phù hợp chưa đủ để bảo đảm DTO projection hoạt động.

Nếu DTO có nhiều constructor, cần cách chọn constructor mà phiên bản và mô-đun hỗ trợ. `org.springframework.data.annotation.PersistenceCreator` có thể dùng để đánh dấu constructor theo cơ chế tương ứng; annotation đó không tự sửa tên thuộc tính hoặc phép chuyển kiểu sai.

### 3.3. Domain type

Caller cũng có thể chọn `Customer.class` trong một query hỗ trợ trả domain object. Khi đó T là Customer, không phải một interface projection chỉ có vài getter.

Việc trả domain object kéo theo hợp đồng truy cập dữ liệu của mô-đun, bao gồm các vấn đề như entity được quản lý, lazy association hoặc session nếu có. Class token không tự làm domain object thành DTO độc lập.

## 4. Repository với một query method động

```java
import java.util.List;

import org.springframework.data.repository.Repository;

public interface CustomerReads extends Repository<Customer, Long> {

    <T> List<T>
    findByStatusOrderByLastNameAscFirstNameAscIdAsc(
            String status,
            Class<T> projectionType);
}
```

Ví dụ giả định mô-đun và phiên bản hỗ trợ derived query, dynamic projection và các kiểu kết quả đang chọn. Những thuộc tính dùng trong tên phương thức phải tồn tại trong domain model.

`status` là điều kiện lọc dữ liệu. `projectionType` là tham số chọn kiểu kết quả khi được nhận diện đúng. Phần `OrderBy...` giữ yêu cầu sắp xếp tại query, với id làm khóa phụ.

Caller sử dụng cùng phương thức theo ba cách:

```java
List<CustomerNameView> names =
        repository.findByStatusOrderByLastNameAscFirstNameAscIdAsc(
                "ACTIVE", CustomerNameView.class);

List<CustomerContactDto> contacts =
        repository.findByStatusOrderByLastNameAscFirstNameAscIdAsc(
                "ACTIVE", CustomerContactDto.class);

List<Customer> customers =
        repository.findByStatusOrderByLastNameAscFirstNameAscIdAsc(
                "ACTIVE", Customer.class);
```

Đây là ba lần gọi query riêng. Framework không tự lấy một tập kết quả dùng chung rồi tạo ba góc nhìn từ cùng một snapshot cho ba lệnh gọi đó.

Nếu dữ liệu thay đổi giữa các lời gọi hoặc chúng chạy trong phạm vi nhất quán khác nhau, số lượng và nội dung kết quả có thể khác. Dynamic projection lựa chọn hình dạng kết quả, không tự cung cấp cơ chế snapshot hay cache dùng chung.

## 5. Liên kết kiểu tại compile time

Trong lời gọi:

```java
Class<CustomerNameView> resultType = CustomerNameView.class;

List<CustomerNameView> names =
        repository.findByStatusOrderByLastNameAscFirstNameAscIdAsc(
                "ACTIVE", resultType);
```

T được xác định là CustomerNameView. Trình biên dịch liên kết kiểu của class token với kiểu phần tử của List.

Cách gán sau không đúng hợp đồng kiểu:

```java
// Không biên dịch theo hợp đồng generic này.
List<CustomerContactDto> contacts =
        repository.findByStatusOrderByLastNameAscFirstNameAscIdAsc(
                "ACTIVE", CustomerNameView.class);
```

Không dùng raw Class, raw List hoặc unchecked cast để vượt qua lỗi này. Những thao tác đó không tạo một phép chuyển CustomerNameView thành CustomerContactDto và làm mất phần kiểm tra kiểu hữu ích của API.

### 5.1. Vì sao phải truyền Class<T>?

Thông tin generic của Java phần lớn bị xóa ở runtime. Framework không thể chỉ nhìn biến bên trái của một phép gán trong mã nguồn để biết caller muốn loại projection nào.

Class token là dữ liệu runtime rõ ràng về kiểu đích. Trong một phương thức generic, không thể tự viết `T.class` để thay cho class token; T không phải tên một class cụ thể có literal như vậy trong Java.

### 5.2. Compile được chưa chắc ánh xạ được

Chữ ký `<T>` không mô tả toàn bộ các ràng buộc mà một projection phải đáp ứng. Một caller có thể truyền một kiểu Java không có mapping phù hợp, và trình biên dịch vẫn suy ra T theo kiểu đó.

Khả năng tạo kết quả còn phụ thuộc accessor của interface, constructor DTO, domain type và query engine. Vì vậy, dùng được một class token trong Java không chứng minh framework có thể tạo projection hợp lệ cho class đó.

Trong thiết kế ứng dụng, nên chọn các kiểu kết quả đã được xác nhận hỗ trợ cho use case cụ thể.

## 6. Phân biệt kiểu chọn projection với tham số bind query

Một chi tiết quan trọng của Spring Data là các tham số Class được kiểm tra xem có phải tham số dynamic projection hay không.

Với mẫu:

```java
<T> List<T> findByStatus(String status, Class<T> projectionType);
```

Class<T> liên kết với kiểu kết quả T. Khi được nhận diện là tham số dynamic projection, nó được dùng làm metadata lựa chọn kiểu, **không còn là một tham số bind thông thường để dùng trong query hoặc SpEL**.

Hệ quả:

- `status` vẫn là giá trị để lọc dữ liệu.
- `projectionType` không tự trở thành điều kiện so sánh trong query.
- Không mặc định có thể tham chiếu class token đó bằng một biến query hoặc biểu thức SpEL như một đối số nghiệp vụ bình thường.
- Đổi tên tham số hoặc thêm annotation đặt tên tham số không tự thay đổi vai trò đặc biệt này.

Tên biến `projectionType` được dùng để người đọc hiểu ý nghĩa. Việc nhận diện không chỉ dựa vào tên biến đó mà dựa trên hợp đồng kiểu của phương thức.

### 6.1. Khi thật sự cần một Class làm đối số query

Nếu một query của mô-đun có nhu cầu nhận một giá trị Class như tham số nghiệp vụ, phải tách nó khỏi tham số chọn projection. Một dạng như `Class<?>` có thể được dùng để tránh sự liên kết generic với T của dynamic projection, theo hợp đồng mà framework hỗ trợ.

| Khai báo tham số | Cách hiểu trong ngữ cảnh tương ứng |
| --- | --- |
| `Class<T>` khớp T của kết quả động | Có thể được nhận diện là tham số chọn projection và loại khỏi nhóm tham số bind |
| `Class<?>` dành cho đối số query thực sự | Không biểu đạt cùng liên kết T; query và mô-đun vẫn phải hỗ trợ cách bind giá trị này |

Không đổi Class<T> thành Class<?> trong một phương thức rồi kỳ vọng nó vẫn lựa chọn projection theo cùng hợp đồng. Cũng không thêm một tham số Class<?> dư vào derived query nếu không có điều kiện hoặc cơ chế query dùng đến nó.

Hai vai trò này cần được thiết kế rõ ràng: một bên là metadata của kết quả, một bên là dữ liệu đầu vào của query.

## 7. Hình dạng phần tử và wrapper kết quả là hai lớp riêng

Dynamic projection chọn T, còn wrapper như List, Optional hoặc Page mô tả số lượng và metadata kết quả.

| Chữ ký minh họa | Ý nghĩa |
| --- | --- |
| `<T> List<T> ...(..., Class<T> type)` | Nhiều phần tử có kiểu T |
| `<T> Optional<T> ...(..., Class<T> type)` | Không có hoặc có một phần tử kiểu T |
| `<T> Page<T> ...(..., Pageable pageable, Class<T> type)` | Trang gồm phần tử kiểu T cùng metadata phân trang |

Mỗi dạng vẫn phải được mô-đun hỗ trợ. Class token không biến một query trả nhiều hàng thành query một hàng và không tự tạo metadata Page từ một List.

### 7.1. Ví dụ tìm một khách hàng theo id

Có thể bổ sung phương thức:

```java
import java.util.Optional;

<T> Optional<T> findProjectedById(Long id, Class<T> projectionType);
```

Sử dụng:

```java
Optional<CustomerNameView> name =
        repository.findProjectedById(42L, CustomerNameView.class);
```

Tên `findProjectedById` là tên query riêng; phần `Id` phải phù hợp thuộc tính domain trong ví dụ. Từ Projected giúp diễn đạt mục đích, không phải một từ khóa đặc biệt tự bật projection.

Dùng tên riêng cũng tránh nhầm với việc khai báo lại base method `findById(ID)` của CRUD. Chỉ đổi return type của phương thức CRUD cơ sở không tự tạo dynamic projection.

Query trả Optional vẫn phải đáp ứng hợp đồng số lượng. Nếu điều kiện có thể khớp nhiều hàng, việc truyền một class token không tự chọn một hàng hoặc âm thầm loại phần dư.

## 8. Kết hợp với phân trang

Khi mô-đun hỗ trợ cả phân trang và dynamic projection, repository có thể có thêm phương thức:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

<T> Page<T> findByStatus(
        String status,
        Pageable pageable,
        Class<T> projectionType);
```

Caller chọn projection và yêu cầu trang:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("lastName"),
                Sort.Order.asc("id")));

Page<CustomerNameView> page = repository.findByStatus(
        "ACTIVE", pageable, CustomerNameView.class);
```

Các tham số có vai trò riêng: status lọc, Pageable điều khiển trang và sort, Class<T> chọn kiểu phần tử.

Cần giữ rõ một số giới hạn:

- Sort phải hợp lệ với domain và dạng query theo khả năng mô-đun; tên getter dẫn xuất của projection không tự thành thuộc tính sort tại database.
- Page có thể cần truy vấn đếm để cung cấp tổng số phần tử; đổi T không tự loại bỏ chi phí này.
- Khả năng sử dụng các trường sort không nằm trong hình dạng kết quả cần được kiểm tra với query và mô-đun cụ thể.
- Không đổi generic thành `Page<List<T>>` để diễn đạt trang của T. Khi đó mỗi phần tử của trang lại được khai báo là một List.

Nếu cần Slice hoặc một dạng wrapper khác, phải xác nhận hỗ trợ tương ứng thay vì suy rộng từ ví dụ Page.

## 9. Interface projection và DTO có cơ chế tạo khác nhau

Dynamic projection thống nhất cách chọn kiểu ở lời gọi, nhưng không làm các kiểu đích có cùng cơ chế ánh xạ.

| Kiểu đích | Cơ chế cần hiểu | Điểm cần xác nhận |
| --- | --- | --- |
| Interface projection | Proxy cung cấp các accessor từ nguồn kết quả | Tên thuộc tính, alias và kiểu getter |
| Class DTO | Tạo instance qua cơ chế constructor hoặc mapping được hỗ trợ | Constructor, tên tham số, kiểu dữ liệu |
| Record DTO | Dùng cấu trúc record và constructor tương ứng khi được hỗ trợ | Phiên bản Java, mô-đun và hình dạng kết quả |
| Domain type | Đọc domain object theo hợp đồng kho dữ liệu | Mapping, transaction và dữ liệu phụ thuộc session nếu có |

Ví dụ một lựa chọn record nếu dự án dùng Java hỗ trợ record và mô-đun hỗ trợ DTO tương ứng:

```java
public record CustomerNameRecord(String firstName, String lastName) {
}
```

Khi phù hợp, caller có thể dùng `CustomerNameRecord.class` làm class token. Đây là kiểu đích bổ sung, không phải yêu cầu mọi dự án phải chuyển sang record.

Class DTO không tự có cơ chế projection lồng nhau kiểu proxy interface. Nếu DTO chứa một trường phức tạp, cần biết query hoặc mapping tạo trường đó như thế nào; generic T không tự cung cấp phép ánh xạ đệ quy tùy ý.

## 10. Query viết tường minh cần được đánh giá riêng

Derived query là cách minh họa rõ hợp đồng dynamic projection. Với query được viết bằng annotation hoặc API riêng của mô-đun, hình dạng kết quả có thể đã được xác định trong nội dung query.

Ví dụ, một biểu thức constructor của JPQL nêu đích cụ thể:

```text
select new com.example.CustomerContactDto(c.firstName, c.email)
from Customer c
where c.status = :status
```

Tên class DTO trong biểu thức đã được viết cố định. Không giả định chỉ cần truyền CustomerNameView.class là framework tự thay tên class và toàn bộ danh sách đối số constructor trong mọi tình huống.

Một số mô-đun và phiên bản có cơ chế rewrite hoặc thích nghi kết quả query, nhưng phải kiểm tra đúng khả năng của trường hợp đang dùng. Những điểm cần xem gồm:

- Query trả domain object, tuple, scalar hay instance DTO cụ thể.
- Interface projection có đủ alias hoặc thuộc tính nguồn không.
- Constructor DTO có khớp các giá trị và kiểu được trả về không.
- Class token có thực sự được nhận diện là tham số dynamic projection không.
- Query viết tường minh có cho phép các kiểu đích định dùng cùng tồn tại không.

Với native query, tên cột, alias, kiểu do driver trả về và cơ chế result mapping cũng có thể ảnh hưởng. Class<T> không phải bộ chuyển đổi tổng quát sửa được mọi kết quả SQL.

Annotation Query thuộc mô-đun tương ứng. Không dùng annotation hoặc cú pháp query của một mô-đun rồi coi đó là hợp đồng chung của Commons.

## 11. Giới hạn tối ưu hóa và vòng đời dữ liệu

### 11.1. Đổi class token không phải lời hứa về số cột

Closed interface projection hoặc DTO có thể cho phép hạ tầng biết các đầu vào cần thiết và tối ưu dữ liệu đọc. Tuy nhiên, lượng dữ liệu thực tế phụ thuộc mô-đun, dạng query, mapping, quan hệ và phiên bản.

Một interface chỉ có hai getter không đủ để kết luận truy vấn luôn chỉ đọc hai cột. Một query viết tường minh lấy toàn bộ entity rồi thích nghi kết quả cũng có đặc tính khác query chỉ chọn vài giá trị.

Nếu mục tiêu là hiệu năng, cần quan sát query thực tế và dữ liệu được lấy, cùng với việc kết quả có đúng kiểu hay không.

### 11.2. Projection không tự tách mọi thứ khỏi session

Một DTO chỉ chứa các giá trị đơn giản đã được chuẩn bị đầy đủ thường phù hợp để chuyển qua ranh giới tầng ứng dụng. Nhưng interface projection lồng nhau, entity hoặc giá trị có liên quan đến lazy association vẫn cần được đánh giá theo mô-đun.

Không coi Class<T> là cơ chế kéo dài transaction. Phạm vi truy cập dữ liệu phải đủ cho những accessor được sử dụng thực tế.

### 11.3. Kiểu trả về không thay đổi quy mô dữ liệu

List<T> vẫn có thể chứa rất nhiều phần tử. Projection nhỏ hơn có thể giảm dữ liệu của mỗi phần tử, nhưng không tự giới hạn số hàng hoặc làm toàn bộ xử lý có bộ nhớ hằng số.

Khi dữ liệu lớn, cần kết hợp giới hạn, phân trang, scrolling hoặc streaming được kho dữ liệu hỗ trợ. Những lựa chọn đó có hợp đồng riêng, không được thay thế bằng việc đổi class token.

## 12. Đặt việc lựa chọn kiểu ở ranh giới use case

Repository có generic T giúp tái sử dụng query. Ở tầng ứng dụng, vẫn có thể giữ các phương thức mang kiểu cố định và ý nghĩa nghiệp vụ rõ ràng:

```java
import java.util.List;
import java.util.Objects;

public class CustomerReadService {

    private final CustomerReads repository;

    public CustomerReadService(CustomerReads repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public List<CustomerNameView> activeNames() {
        return repository.findByStatusOrderByLastNameAscFirstNameAscIdAsc(
                "ACTIVE", CustomerNameView.class);
    }

    public List<CustomerContactDto> activeContacts() {
        return repository.findByStatusOrderByLastNameAscFirstNameAscIdAsc(
                "ACTIVE", CustomerContactDto.class);
    }
}
```

Trong ví dụ, service lựa chọn những kiểu đã biết. Caller của service không phải hiểu tên class Java hoặc cơ chế projection để dùng chức năng đọc tên khách hàng.

Các quy tắc như phạm vi tenant, bộ lọc dữ liệu và quyền sử dụng từng chức năng vẫn thuộc hợp đồng của ứng dụng. Truyền một class token không tự cung cấp các điều kiện đó.

Nếu một endpoint cần lựa chọn hình dạng response, có thể ánh xạ lựa chọn sản phẩm sang những use case hoặc DTO được hỗ trợ. Không cần để hợp đồng công khai phụ thuộc trực tiếp vào tên class nội bộ.

## 13. Những sai lầm thường gặp

### 13.1. Chỉ đổi return type của phương thức cơ sở

Khai báo lại `findById(ID)` của CRUD với return type projection không tự tạo query projection. Dynamic projection cần một chữ ký và đường thực thi query phù hợp, không chỉ một generic mới trên giấy.

### 13.2. Đổi Class<T> thành Class<?> để hết lỗi generic

Việc này làm mất liên kết kiểu được dùng trong mẫu dynamic projection. Cần sửa hợp đồng kiểu hoặc class token, thay vì bỏ liên kết giữa input và output.

### 13.3. Cố bind tham số chọn projection vào query

Khi Class<T> đã được framework nhận diện là tham số chọn projection, nó không còn là tham số query thông thường. Không dựa vào nó như một biến lọc dữ liệu hoặc biến SpEL nghiệp vụ.

### 13.4. Coi mọi class đều là projection hợp lệ

Generic T chỉ bảo đảm mối liên hệ kiểu ở lời gọi. Nó không bảo đảm một class bất kỳ có constructor, getter hoặc mapping phù hợp với domain.

### 13.5. Nghĩ rằng Class<T> quyết định điều kiện lọc

Class token quyết định hình dạng phần tử trong hợp đồng này. Query vẫn phải biểu đạt điều kiện cần đọc. Chọn một DTO ít trường không tự thay các điều kiện nghiệp vụ khác.

### 13.6. Kiểm tra mỗi số lượng kết quả

Một List có đúng kích thước chưa chứng minh các phần tử ánh xạ đúng. Cần sử dụng accessor của interface hoặc DTO và đối chiếu giá trị, null cùng kiểu dữ liệu.

## 14. Cách kiểm chứng khi tích hợp vào dự án

Nên có dữ liệu đủ để phân biệt các kiểu đích: tên có dấu, email khác nhau, nhiều khách hàng cùng họ và ít nhất một bản ghi không khớp trạng thái.

| Ca | Điều cần xác nhận |
| --- | --- |
| Truyền CustomerNameView.class | Nhận được phần tử dùng đúng accessor của interface |
| Truyền CustomerContactDto.class | DTO có đúng tên và email theo dữ liệu nguồn |
| Truyền Customer.class | Nhận domain object theo hợp đồng mô-đun |
| Không có bản ghi phù hợp | List hoặc Optional rỗng theo chữ ký |
| Có giá trị nullable | Interface hoặc DTO xử lý đúng hợp đồng dữ liệu |
| Query có nhiều kết quả với Optional | Không âm thầm che vi phạm cardinality |
| Dùng Pageable | Nội dung, sort và metadata phù hợp |
| DTO có nhiều constructor | Constructor được chọn đúng theo cấu hình hỗ trợ |
| Query viết tường minh | Alias và constructor phù hợp từng kiểu đích cần dùng |
| Thay đổi một kiểu projection | Không làm hỏng các kiểu khác đang sử dụng cùng query |

Có thể kiểm tra công thức Java hoặc constructor DTO trong bộ nhớ. Nhưng để xác nhận dynamic projection, cần lời gọi repository thật với các class token thực tế trên mô-đun và cấu hình dự án.

Khi mục tiêu có tối ưu query, cần thêm quan sát lượng dữ liệu hoặc câu query, không chỉ so sánh JSON cuối cùng. Những lời gọi chọn các kiểu khác nhau nên được kiểm tra với điều kiện dữ liệu được kiểm soát, thay vì giả định các truy vấn ở thời điểm khác nhau luôn trả cùng một snapshot.

## 15. Bảng chẩn đoán nhanh

| Hiện tượng | Khả năng cần xem xét | Hướng kiểm tra |
| --- | --- | --- |
| Không gán được kết quả vào biến mong muốn | Class token không khớp T của biến | So kiểu của Class<T> và kiểu phần tử kết quả |
| Query đòi bind một tham số không tồn tại | Nhầm vai trò tham số chọn projection | Kiểm tra generic và nhóm tham số query thực sự |
| DTO không khởi tạo được | Constructor, tên tham số hoặc kiểu dữ liệu không phù hợp | Kiểm tra metadata constructor và kết quả nguồn |
| Interface getter trả giá trị sai hoặc thiếu | Tên thuộc tính hoặc alias không khớp | Đối chiếu getter với query và mapping |
| Một kiểu hoạt động, kiểu khác thất bại | Query chỉ phù hợp một hình dạng kết quả | Kiểm tra riêng cơ chế tạo từng kiểu đích |
| Query vẫn lấy nhiều dữ liệu | Dạng query hoặc mapping không được tối ưu như kỳ vọng | Quan sát truy vấn thực tế của mô-đun |
| Lỗi khi đọc association sau service | Tài nguyên hoặc session đã hết phạm vi | Kiểm tra dữ liệu projection và transaction |
| Generic đã bị bỏ qua bằng raw type | Kiểm tra kiểu bị che, chưa có phép chuyển đổi | Khôi phục chữ ký generic và dùng token phù hợp |
| Class<?> không còn chọn đúng kiểu kết quả | Mất hợp đồng liên kết T | Phân biệt tham số chọn projection với đối số query |

## 16. Tình huống tự đánh giá

### A. Cùng điều kiện, hai màn hình

Màn hình A cần firstName và lastName; màn hình B cần firstName và email. Cả hai đọc khách hàng ACTIVE theo cùng thứ tự.

Thiết kế một query method dynamic projection, hai kiểu kết quả và hai lời gọi có kiểu compile-time phù hợp. Nêu điều kiện để DTO của màn hình B được tạo đúng.

### B. Muốn dùng type trong SpEL

Một query có Class<T> được nhận diện là tham số chọn projection, nhưng biểu thức query lại cố đọc tham số đó như dữ liệu nghiệp vụ.

Giải thích vì sao giả định này không đúng. Phân biệt trường hợp chọn projection với trường hợp một query thật sự cần đối số Class và cách dùng generic tương ứng.

### C. DTO có thêm trường

CustomerContactDto được thêm một tham số constructor không có thuộc tính nguồn hoặc alias tương ứng.

Giải thích vì sao lời gọi Java vẫn có thể biên dịch nhưng query mapping thất bại. Xác định phần hợp đồng cần cập nhật hoặc thiết kế lại.

### D. Query constructor cố định

Một query JPQL viết sẵn `select new ...CustomerContactDto(...)`, trong khi caller muốn truyền CustomerNameView.class.

Nêu lý do không thể mặc định class token sẽ tự thay biểu thức constructor. Chỉ ra khả năng query và cơ chế rewrite cần được kiểm tra theo mô-đun, phiên bản.

### E. Chọn entity thay vì projection

Một service truyền Customer.class rồi trả kết quả ra ngoài transaction; caller sau đó truy cập một association lazy.

Giải thích điều gì thuộc trách nhiệm của class token và điều gì thuộc vòng đời dữ liệu. Đề xuất hình dạng kết quả phù hợp nếu cần dữ liệu độc lập cho tầng ngoài.

### F. Biên dịch được với class không phù hợp

Một caller truyền một class Java bất kỳ không có cấu trúc tương ứng với Customer và cho rằng generic T chứng minh query sẽ hoạt động.

Phân biệt bảo đảm của trình biên dịch với yêu cầu mapping runtime. Đề xuất cách giữ các kiểu kết quả được hỗ trợ rõ ràng tại ranh giới use case.

## 17. Quy trình áp dụng

1. Xác định những hình dạng kết quả thực sự cần cho cùng một điều kiện query.
2. Thiết kế interface accessor hoặc DTO constructor phù hợp domain và khả năng mô-đun.
3. Khai báo phương thức generic với liên kết giữa T của kết quả và Class<T>.
4. Phân biệt class token đặc biệt với các tham số bind query thông thường.
5. Chọn class token rõ ràng tại mỗi use case và giữ kiểu compile-time tương ứng.
6. Kiểm tra từng kiểu đích, wrapper kết quả và dữ liệu nullable.
7. Đánh giá truy vấn thực tế, metadata phân trang và vòng đời dữ liệu khi có yêu cầu liên quan.

Dynamic projection giúp tái sử dụng một hợp đồng truy vấn cho nhiều góc nhìn đọc. Giá trị của nó đến từ liên kết rõ ràng giữa class token và kiểu kết quả, cùng khả năng mapping đã được xác nhận của mô-đun kho dữ liệu đang dùng.