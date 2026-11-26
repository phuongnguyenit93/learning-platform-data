# first, one, all, count và exists

Trong fluent query của Spring Data Commons, cấu hình điều kiện và chọn cách nhận kết quả là hai việc khác nhau. Cùng một điều kiện tìm kiếm có thể được dùng để lấy phần tử đầu tiên, yêu cầu tối đa một phần tử, lấy danh sách, đếm số phần tử hoặc chỉ kiểm tra có kết quả hay không.

Năm thao tác `first()`, `one()`, `all()`, `count()` và `exists()` thể hiện năm ý định đó. Chọn đúng thao tác giúp mã diễn đạt rõ hợp đồng nghiệp vụ, xử lý đúng trường hợp không có dữ liệu và tránh tải dữ liệu không cần thiết.

## 1. Phạm vi và mục tiêu

Bài học tập trung vào fluent query đồng bộ, cụ thể là `FluentQuery.FetchableFluentQuery`, được sử dụng qua callback của `QueryByExampleExecutor.findBy`.

Sau bài này, bạn có thể:

- Phân biệt lấy phần tử đầu tiên với yêu cầu kết quả duy nhất.
- Dự đoán hành vi khi có 0, 1 hoặc nhiều bản ghi phù hợp.
- Chọn đúng kiểu trả về giữa `Optional<T>`, `List<T>`, `long` và `boolean`.
- Dùng `Sort` để xác định phần tử đầu tiên theo nghiệp vụ.
- Hiểu vì sao kiểm tra tồn tại không thay thế ràng buộc duy nhất khi ghi dữ liệu.
- Nhận biết phần hợp đồng thuộc Commons và phần thực thi phụ thuộc module lưu trữ.

Các ví dụ dùng QBE để cung cấp điều kiện. Những interface fluent khác, đặc biệt API reactive, có kiểu trả về và cách thực thi khác; không áp nguyên xi bảng kiểu trả về đồng bộ trong bài cho mọi API.

Các ví dụ không thiết lập giới hạn số kết quả bằng một tùy chọn riêng. Khi đọc tài liệu của phiên bản hoặc API khác có thêm khả năng giới hạn, cần đối chiếu hợp đồng của chính thao tác đang dùng.

## 2. Điều kiện truy vấn và thao tác kết thúc

QBE nhận một probe cùng `ExampleMatcher` để xác định bản ghi phù hợp. Fluent query cho phép bổ sung cấu hình như sắp xếp, rồi chọn thao tác kết thúc:

```java
Optional<Customer> result = customerRepository.findBy(
    example,
    query -> query
        .sortBy(sort)
        .first()
);
```

Có ba phần cần phân biệt:

1. `example` xác định tập bản ghi phù hợp.
2. `sortBy(sort)` xác định thứ tự lấy kết quả.
3. `first()` chọn cách thực thi và hình dạng giá trị trả về.

Callback cần trả về kết quả đã được thực thi như `Optional`, danh sách, số đếm hoặc boolean. Không trả đối tượng fluent query ra ngoài callback để tiếp tục sử dụng sau đó.

Một callback nên thể hiện rõ một nhu cầu đọc. Nhiều lời gọi kết thúc trong cùng callback không mặc nhiên là một truy vấn duy nhất hoặc một snapshot dữ liệu dùng chung.

## 3. Chuẩn bị ví dụ

### 3.1. Domain và repository

Giả sử ứng dụng có domain `Customer` với các thuộc tính sau:

| Thuộc tính | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất |
| `displayName` | `String` | Tên hiển thị |
| `email` | `String` | Email dùng trong ví dụ tra cứu |
| `country` | `String` | Mã quốc gia |

Domain có getter, setter và mapping phù hợp với module đang dùng. Các thuộc tính tham chiếu không được gán sẵn giá trị khi tạo probe mới.

Repository khai báo khả năng QBE:

```java
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends Repository<Customer, Long>,
                QueryByExampleExecutor<Customer> {
}
```

Module lưu trữ cần hỗ trợ QBE và fluent execution tương ứng. Interface `Repository` là marker interface; khai báo trên không tự bổ sung toàn bộ phương thức CRUD.

### 3.2. Tạo điều kiện tìm theo quốc gia

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setCountry("VN");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreNullValues();

Example<Customer> example = Example.of(probe, matcher);
```

Các thuộc tính còn lại đang null nên được bỏ qua. Nếu domain thực tế có field nguyên thủy hoặc giá trị khởi tạo sẵn, phải kiểm soát chúng để tránh thêm điều kiện ngoài ý muốn.

Trong các đoạn mã tiếp theo:

- `customerRepository` là repository được ứng dụng cấu hình.
- `example` là điều kiện tìm quốc gia VN.
- Cách so khớp mã quốc gia được giả định phù hợp với mapping và matcher của module.
- Các đoạn mã là những cách sử dụng thay thế nhau, không bắt buộc phải gọi liên tiếp tất cả.

### 3.3. Dữ liệu minh họa

| id | displayName | email | country |
| --- | --- | --- | --- |
| 101 | An | shared@example.test | VN |
| 102 | An | shared@example.test | VN |
| 103 | Binh | binh@example.test | TH |
| 104 | Chi | chi@example.test | VN |

Có ba khách hàng ở VN, một khách hàng ở TH và không có khách hàng ở JP. Email trùng ở hai bản ghi được giữ có chủ đích để minh họa hành vi khi dữ liệu không duy nhất.

## 4. Bảng hợp đồng của năm thao tác

Trong fluent query đồng bộ đang xét:

| Thao tác | Kiểu trả về | Không có kết quả | Có một kết quả | Có nhiều kết quả |
| --- | --- | --- | --- | --- |
| `first()` | `Optional<T>` | `Optional.empty()` | Phần tử đó | Phần tử đầu theo thứ tự truy vấn |
| `one()` | `Optional<T>` | `Optional.empty()` | Phần tử đó | Ném `IncorrectResultSizeDataAccessException` |
| `all()` | `List<T>` | Danh sách rỗng | Danh sách một phần tử | Danh sách toàn bộ kết quả phù hợp |
| `count()` | `long` | `0L` | `1L` | Số phần tử phù hợp |
| `exists()` | `boolean` | `false` | `true` | `true` |

Điểm dễ nhầm nhất là `one()` không yêu cầu bắt buộc phải có một kết quả. Nó yêu cầu **không có nhiều hơn một kết quả**. Trường hợp không có dữ liệu vẫn được biểu diễn bằng `Optional.empty()`.

Nếu nghiệp vụ yêu cầu đúng một phần tử, cần kết hợp `one()` với xử lý trường hợp Optional rỗng.

## 5. first(): lấy phần tử đầu tiên

### 5.1. Chỉ rõ ý nghĩa của “đầu tiên”

```java
import java.util.Optional;

import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.asc("displayName"),
    Sort.Order.asc("id")
);

Optional<Customer> firstCustomer =
    customerRepository.findBy(
        example,
        query -> query
            .sortBy(sort)
            .first()
    );
```

Với bộ dữ liệu minh họa, kết quả là khách hàng 101:

- Chỉ các bản ghi quốc gia VN tham gia.
- Tên An đứng trước tên Chi theo giả định thứ tự trong ví dụ.
- Hai bản ghi tên An được phân định bằng ID tăng dần.

Tên trong `Sort` là tên thuộc tính domain như `displayName`, không phải tên cột lưu trữ hoặc tên getter.

### 5.2. Không có sort thì không có lựa chọn nghiệp vụ ổn định

```java
Optional<Customer> anyFirst =
    customerRepository.findBy(example, query -> query.first());
```

Đoạn mã diễn đạt lấy phần tử đầu tiên theo cách kho dữ liệu trả kết quả, nhưng không xác định đó là khách hàng nhỏ tuổi nhất, mới nhất hay có ID nhỏ nhất.

Không suy ra thứ tự từ kết quả của một lần chạy. Nếu nghiệp vụ nói “bản ghi mới nhất”, domain cần một thuộc tính thời gian phù hợp và truy vấn cần sắp xếp giảm dần theo thuộc tính đó, thêm khóa phân định khi cần.

Thêm khóa duy nhất vào cuối thứ tự giúp phân định các bản ghi có cùng giá trị sắp xếp. Nó không khóa dữ liệu và không bảo đảm kết quả giữ nguyên nếu dữ liệu thay đổi giữa các lần gọi.

### 5.3. first không xác nhận dữ liệu duy nhất

Với hai bản ghi cùng email, `first()` vẫn trả một bản ghi. Đây là hành vi đúng khi nghiệp vụ chủ động chọn một kết quả đại diện.

Nhưng nếu email phải duy nhất, dùng `first()` có thể che khuất tình trạng dữ liệu trùng. Muốn phát hiện nhiều kết quả, cần hợp đồng của `one()` và ràng buộc dữ liệu phù hợp.

## 6. one(): yêu cầu tối đa một kết quả

### 6.1. Trường hợp hợp lệ

Giả sử probe lọc quốc gia TH:

```java
Customer thailandProbe = new Customer();
thailandProbe.setCountry("TH");

Example<Customer> thailandExample = Example.of(
    thailandProbe,
    ExampleMatcher.matchingAll().withIgnoreNullValues()
);

Optional<Customer> uniqueCustomer =
    customerRepository.findBy(
        thailandExample,
        query -> query.one()
    );
```

Với dữ liệu minh họa, Optional chứa khách hàng 103. Nếu đổi quốc gia thành JP, kết quả là Optional rỗng.

### 6.2. Nhiều kết quả là lỗi cardinality

Với `example` quốc gia VN:

```java
Optional<Customer> uniqueCustomer =
    customerRepository.findBy(example, query -> query.one());
```

Có ba bản ghi phù hợp nên truy vấn không trả một phần tử tùy ý. Nó ném `org.springframework.dao.IncorrectResultSizeDataAccessException`.

Sắp xếp không làm các bản ghi trùng biến thành duy nhất:

```java
customerRepository.findBy(
    example,
    query -> query
        .sortBy(Sort.by("id"))
        .one()
);
```

Nếu điều kiện vẫn phù hợp với nhiều bản ghi, hợp đồng `one()` vẫn bị vi phạm. Muốn chọn phần tử đứng đầu, hãy dùng `first()`; muốn kiểm tra tính duy nhất của kết quả, hãy giữ `one()`.

### 6.3. Phân biệt vắng dữ liệu và lỗi dữ liệu trùng

Nếu nghiệp vụ yêu cầu phải tìm thấy một khách hàng, có thể chuyển Optional rỗng thành lỗi ứng dụng:

```java
Customer customer = customerRepository.findBy(
    thailandExample,
    query -> query.one()
).orElseThrow(
    () -> new IllegalStateException("Không tìm thấy khách hàng")
);
```

Hai tình huống khác nhau vẫn được giữ:

- Không có kết quả: xử lý bởi `orElseThrow`.
- Có nhiều kết quả: lỗi cardinality phát sinh khi thực thi `one()`.

Không nên bắt lỗi nhiều kết quả rồi chuyển thành `Optional.empty()`, vì như vậy dữ liệu trùng bị báo thành không tìm thấy dữ liệu.

Việc chọn exception nghiệp vụ và ánh xạ sang phản hồi API thuộc thiết kế ứng dụng; ví dụ chỉ minh họa cách tách hai trường hợp.

## 7. all(): lấy danh sách kết quả phù hợp

```java
import java.util.List;

List<Customer> customers =
    customerRepository.findBy(
        example,
        query -> query
            .sortBy(sort)
            .all()
    );
```

Với dữ liệu minh họa, danh sách chứa các ID 101, 102 và 104 theo thứ tự đã chọn.

Nếu không có bản ghi phù hợp, `all()` trả danh sách rỗng. Vì vậy, xử lý trường hợp không có dữ liệu bằng `isEmpty()`, không cần dựa vào null:

```java
if (customers.isEmpty()) {
    // Xử lý trường hợp không có khách hàng phù hợp.
}
```

Trong ví dụ không đặt giới hạn này, `all()` lấy toàn bộ tập kết quả phù hợp và tạo một danh sách. Không dùng thao tác này cho tập dữ liệu có thể lớn chỉ để lấy một phần tử, kiểm tra tồn tại hoặc đếm.

Đặc biệt, cách sau có hai vấn đề:

```java
Customer first = customerRepository.findBy(
    example,
    query -> query.all()
).get(0);
```

- Có thể tải toàn bộ danh sách trong khi chỉ cần một phần tử.
- Ném lỗi truy cập chỉ số nếu danh sách rỗng.

`first()` diễn đạt đúng nhu cầu hơn và trả Optional để biểu diễn trường hợp không có dữ liệu.

Khi giao diện cần từng trang, hãy dùng thao tác phân trang được module hỗ trợ thay vì gọi `all()` rồi cắt danh sách trong bộ nhớ.

## 8. count(): lấy số lượng, không lấy danh sách

```java
long total = customerRepository.findBy(
    example,
    query -> query.count()
);
```

Với điều kiện quốc gia VN trong bộ dữ liệu minh họa, `total` bằng `3L`.

Kiểu trả về là `long`. Nếu tầng API hoặc cấu trúc dữ liệu khác chỉ nhận `int`, cần xử lý khả năng vượt giới hạn trước khi chuyển kiểu.

So sánh với cách đếm qua danh sách:

```java
int totalAfterLoading = customerRepository.findBy(
    example,
    query -> query.all()
).size();
```

Cách thứ hai yêu cầu lấy và biểu diễn các phần tử trước khi đếm kích thước danh sách. Nếu nhu cầu chỉ là số lượng, hãy dùng `count()` để implementation có cơ hội thực thi theo cách đếm phù hợp với kho dữ liệu.

Không khẳng định mọi module đều phát ra SQL `COUNT(*)`: module có thể dùng SQL, lệnh đếm của kho tài liệu hoặc cơ chế khác. Ngay cả một truy vấn đếm chuyên biệt cũng có thể tốn kém trên tập dữ liệu lớn.

Thứ tự không phải thông tin cần thiết để trả lời có bao nhiêu bản ghi. Ví dụ đếm không gọi `sortBy`; đừng dựa vào sắp xếp để thay đổi ý nghĩa phép đếm.

## 9. exists(): chỉ trả lời có hay không

```java
boolean found = customerRepository.findBy(
    example,
    query -> query.exists()
);
```

Kết quả:

- Có ít nhất một bản ghi phù hợp: `true`.
- Không có bản ghi phù hợp: `false`.

Nếu câu hỏi nghiệp vụ chỉ là “Có khách hàng ở VN không?”, `exists()` thể hiện đúng yêu cầu hơn hai cách sau:

```java
boolean foundByCounting = customerRepository.findBy(
    example,
    query -> query.count()
) > 0;

boolean foundByLoading = !customerRepository.findBy(
    example,
    query -> query.all()
).isEmpty();
```

Cách đếm yêu cầu một kết quả số lượng chính xác. Cách lấy danh sách yêu cầu tải các phần tử. Cả hai đều cung cấp nhiều thông tin hơn điều kiện có/không cần dùng.

`exists()` cho implementation cơ hội chọn chiến lược kiểm tra tồn tại phù hợp. Nó không bảo đảm mọi module sẽ thực hiện cùng một lệnh, luôn dừng sau đúng một bản ghi hay luôn nhanh hơn trong mọi tình huống. Hiệu quả cụ thể phụ thuộc implementation, điều kiện, index và kho dữ liệu.

## 10. Áp dụng one và exists cho tra cứu email

### 10.1. Tra cứu email với hợp đồng duy nhất

Ví dụ một phương thức trong service đã được cung cấp `customerRepository`:

```java
public Optional<Customer> findUniqueByEmail(String email) {
    if (email == null || email.isBlank()) {
        throw new IllegalArgumentException(
            "Email tìm kiếm không được để trống"
        );
    }

    Customer probe = new Customer();
    probe.setEmail(email);

    ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withMatcher(
            "email",
            ExampleMatcher.GenericPropertyMatchers.exact()
        );

    Example<Customer> example = Example.of(probe, matcher);

    return customerRepository.findBy(
        example,
        query -> query.one()
    );
}
```

Đoạn mã dùng `String.isBlank()` của Java 11 trở lên, cùng các import `Optional`, `Example` và `ExampleMatcher` đã giới thiệu.

Cần xác định trước quy tắc email của ứng dụng, bao gồm chuẩn hóa, phân biệt hoa thường và collation của kho. Quy tắc so khớp trong truy vấn và quy tắc duy nhất trong lưu trữ phải nhất quán.

Với dữ liệu minh họa, tìm `shared@example.test` theo quy tắc so khớp đã nêu sẽ gặp hai kết quả và `one()` báo lỗi cardinality. Tìm `chi@example.test` trả khách hàng 104.

Kiểm tra email đầu vào giúp tránh việc giá trị null bị matcher bỏ qua, biến một truy vấn tra cứu cụ thể thành truy vấn rộng ngoài ý muốn.

### 10.2. Kiểm tra email tồn tại không bảo đảm việc tạo mới sẽ hợp lệ

Giả sử luồng xử lý là:

```text
1. exists(email) trả false
2. Tạo khách hàng với email đó
```

Hai request đồng thời có thể đều thực hiện bước 1 trước khi bất kỳ request nào hoàn tất bước 2. Cả hai cùng quan sát không tồn tại, rồi cùng cố ghi.

Vì vậy:

- `exists()` hữu ích cho phản hồi sớm hoặc thông báo trên giao diện.
- Nó không tự tạo ràng buộc duy nhất và không tự khóa khoảng thời gian giữa kiểm tra và ghi.
- Nếu nghiệp vụ yêu cầu duy nhất, cần cơ chế bảo đảm phù hợp với kho dữ liệu, chẳng hạn unique constraint hoặc unique index với phạm vi và quy tắc so sánh đúng.
- Luồng ghi vẫn cần xử lý việc kho dữ liệu từ chối do xung đột duy nhất.

Tương tự, `one()` kiểm tra cardinality của kết quả đọc tại lần thực thi. Nó không thay thế cơ chế ngăn dữ liệu trùng trong tương lai.

## 11. Chọn thao tác theo câu hỏi nghiệp vụ

| Câu hỏi | Thao tác phù hợp | Lý do |
| --- | --- | --- |
| Khách hàng đứng đầu theo một thứ tự là ai? | `sortBy(...).first()` | Chủ động chọn một phần tử, cho phép có nhiều phần tử phù hợp |
| Tối đa một khách hàng được phép khớp mã tra cứu này là ai? | `one()` | Phát hiện trường hợp có nhiều kết quả |
| Phải có đúng một khách hàng phù hợp | `one()` và xử lý Optional rỗng | Tách yêu cầu không trùng và yêu cầu phải tồn tại |
| Toàn bộ khách hàng trong tập kết quả nhỏ là những ai? | `all()` | Cần danh sách các phần tử |
| Có bao nhiêu khách hàng phù hợp? | `count()` | Chỉ cần số lượng |
| Có khách hàng phù hợp hay không? | `exists()` | Chỉ cần boolean |

Không chọn `one()` chỉ vì màn hình có chỗ hiển thị một khách hàng. Cần hỏi rõ dữ liệu được phép có nhiều kết quả và giao diện chọn một phần tử, hay nhiều kết quả là vi phạm nghiệp vụ.

## 12. Cùng một Example không tạo cùng một thời điểm quan sát

Các lời gọi dưới đây là những lần thực thi riêng:

```java
boolean found = customerRepository.findBy(
    example,
    query -> query.exists()
);

long total = customerRepository.findBy(
    example,
    query -> query.count()
);
```

Không thể suy ra `found == true` thì `total` trong lần gọi sau chắc chắn lớn hơn 0, nếu dữ liệu có thể bị xóa giữa hai lần đọc.

Tương tự, sau khi `count()` trả một giá trị, `all()` gọi sau đó có thể trả danh sách với kích thước khác nếu dữ liệu thay đổi.

Nếu nghiệp vụ cần các kết quả nhất quán theo cùng snapshot, phải xem xét transaction, isolation và khả năng của kho dữ liệu. Chỉ đặt hai thao tác trong cùng callback hoặc cùng một phương thức Java không tự cung cấp tính nhất quán đó; ngay cả transaction cũng cần mức cô lập phù hợp.

Không nên gọi `exists()` trước mọi lần gọi `first()` để tránh Optional rỗng. `first()` đã biểu diễn trực tiếp trường hợp không có kết quả, còn bước kiểm tra trước thêm một lần đọc và vẫn có khoảng thời gian dữ liệu thay đổi.

## 13. Projection và giới hạn hỗ trợ của từng module

Năm thao tác này thuộc hợp đồng fluent query, nhưng implementation do module Spring Data cụ thể cung cấp.

Nếu module hỗ trợ projection, có thể đổi kiểu phần tử trước thao tác lấy dữ liệu:

```java
public interface CustomerSummary {
    Long getId();
    String getDisplayName();
}
```

```java
Optional<CustomerSummary> summary =
    customerRepository.findBy(
        example,
        query -> query
            .as(CustomerSummary.class)
            .sortBy(sort)
            .first()
    );
```

Trong trường hợp này, Optional chứa `CustomerSummary` thay vì `Customer`. Hợp đồng chọn phần tử đầu tiên vẫn là ý định của `first()`.

Đổi hình dạng kết quả không đồng nghĩa kiểm tra tính duy nhất của một giá trị hiển thị. Nếu nhiều khách hàng cùng tên, projection chỉ chứa tên không tự biến tập khách hàng đó thành một khách hàng duy nhất. Không dùng `one()` như một phép đếm số giá trị tên khác nhau.

Trước khi áp dụng:

- Đối chiếu phiên bản Commons mà dự án đang dùng có API tương ứng.
- Xác định repository và module có hỗ trợ fluent QBE hay không.
- Xác minh kiểu projection, đường dẫn sắp xếp và cách so khớp được hỗ trợ.
- Quan sát cách thực thi nếu cần khẳng định hiệu quả của `first`, `count` hoặc `exists`.

Không mặc định một module dùng SQL hoặc cho rằng một dạng projection dùng được với mọi kho dữ liệu. Số truy vấn, cách giới hạn, cách đếm và chiến lược kiểm tra tồn tại là chi tiết implementation.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `first()` để xác nhận duy nhất | Dữ liệu trùng có thể bị che khuất | Dùng `one()` cho hợp đồng tối đa một kết quả |
| Dùng `one()` để chọn bất kỳ một bản ghi | Lỗi khi có nhiều kết quả | Dùng `first()` với thứ tự phù hợp |
| Cho rằng `one()` bắt buộc có dữ liệu | Xử lý thiếu trường hợp Optional rỗng | Thêm quy tắc vắng dữ liệu ở tầng ứng dụng |
| Gọi `all().get(0)` | Tải thừa và lỗi khi danh sách rỗng | Dùng `first()` |
| Gọi `all().size()` chỉ để đếm | Tải các phần tử không cần thiết | Dùng `count()` |
| Gọi `count() > 0` chỉ để kiểm tra có dữ liệu | Yêu cầu số lượng khi chỉ cần boolean | Dùng `exists()` |
| Gọi `first()` không có thứ tự nhưng mong bản ghi mới nhất | Kết quả không được xác định theo nghiệp vụ | Thêm Sort trên thuộc tính phù hợp |
| Bắt lỗi nhiều kết quả và trả Optional rỗng | Lẫn dữ liệu trùng với không tìm thấy | Giữ hoặc ánh xạ lỗi cardinality rõ ràng |
| Kiểm tra `exists` rồi xem đó là bảo đảm duy nhất khi ghi | Có thể xảy ra tranh chấp đồng thời | Bảo đảm duy nhất tại cơ chế lưu trữ phù hợp |

## 15. Bài tập tự kiểm tra

Dùng bộ dữ liệu minh họa và thứ tự `displayName ASC, id ASC`:

1. Với quốc gia VN, `first()` trả bản ghi nào?
2. Với quốc gia VN, `one()` trả gì?
3. Với quốc gia TH, kết quả của cả năm thao tác khác nhau thế nào?
4. Với quốc gia JP, `one()` có ném lỗi vì không có dữ liệu không?
5. Nếu hai khách hàng cùng email nhưng ứng dụng dùng `first()`, điều gì bị bỏ qua?
6. Nếu chỉ cần biết có khách hàng nào ở VN, vì sao nên chọn `exists()`?
7. Nếu `exists(email)` trả false, có thể bảo đảm một request khác chưa tạo email đó trước bước ghi tiếp theo không?

Gợi ý đáp án:

1. Optional chứa khách hàng 101.
2. Ném `IncorrectResultSizeDataAccessException` vì có ba khách hàng phù hợp.
3. `first` và `one` trả Optional chứa khách hàng 103; `all` trả danh sách một phần tử; `count` trả `1L`; `exists` trả `true`.
4. Không. Nó trả `Optional.empty()`.
5. Tình trạng nhiều kết quả không bị phát hiện qua hợp đồng của `first()`.
6. Nó diễn đạt đúng nhu cầu có/không và không yêu cầu danh sách hoặc tổng số.
7. Không. Cần cơ chế bảo đảm duy nhất và xử lý đồng thời phù hợp với kho dữ liệu.

Chọn thao tác kết thúc theo thông tin nghiệp vụ thực sự cần: một phần tử theo thứ tự, tối đa một phần tử, danh sách, số lượng hoặc sự tồn tại. Sau đó xử lý rõ trường hợp rỗng, nhiều kết quả và dữ liệu thay đổi giữa các lần đọc.
