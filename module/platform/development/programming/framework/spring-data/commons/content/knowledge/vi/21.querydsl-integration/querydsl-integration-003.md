# Tìm một hoặc nhiều kết quả, đếm và kiểm tra tồn tại

Khi tích hợp Querydsl với Spring Data, một `Predicate` diễn đạt điều kiện tìm kiếm, còn phương thức của repository quyết định cách nhận kết quả. Cùng một điều kiện có thể dùng để tìm tối đa một đối tượng, lấy nhiều đối tượng, đếm số lượng hoặc chỉ kiểm tra có dữ liệu hay không.

Trong Spring Data Commons, `QuerydslPredicateExecutor<T>` cung cấp các hợp đồng phổ biến cho những nhu cầu này. Chọn đúng phương thức giúp ứng dụng phát hiện dữ liệu không duy nhất, xử lý trường hợp rỗng rõ ràng và tránh lấy nhiều dữ liệu hơn nghiệp vụ cần.

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể:

- Tạo predicate bằng Q-type và truyền vào repository.
- Phân biệt `findOne`, `findAll`, `count` và `exists`.
- Dự đoán kiểu trả về và hành vi khi có 0, 1 hoặc nhiều kết quả.
- Sắp xếp, phân trang tập kết quả khi module hỗ trợ.
- Giữ được tiêu chí `false` khi tạo predicate từ bộ lọc tùy chọn.
- Nhận biết giới hạn của kiểm tra tồn tại và yêu cầu duy nhất.

Bài tập trung vào API đồng bộ `QuerydslPredicateExecutor` thuộc Commons. Module lưu trữ cụ thể phải hỗ trợ tích hợp Querydsl tương ứng. Không phải cứ thêm interface này vào bất kỳ repository nào cũng có một implementation thực thi được.

Các ví dụ giả định Q-type đã được tạo đúng và dependency đã được cấu hình trong dự án. Bài không hướng dẫn chạy bộ sinh mã hay cấu hình build. Những biểu thức logic được mô tả không khẳng định mọi module đều sinh SQL giống nhau.

## 2. Predicate quyết định điều kiện, executor quyết định hình dạng kết quả

Ví dụ:

```java
Predicate inVietnam = customer.country.eq("VN");
```

Biểu thức trên mô tả điều kiện quốc gia bằng VN. Nó chưa chọn việc trả một khách hàng, danh sách khách hàng, số lượng hay boolean.

Các lời gọi sau có cùng điều kiện nhưng hợp đồng khác nhau:

```java
customerRepository.findOne(inVietnam);
customerRepository.findAll(inVietnam);
customerRepository.count(inVietnam);
customerRepository.exists(inVietnam);
```

Một predicate không tự thực thi truy vấn khi được tạo. Việc gọi repository mới yêu cầu implementation thực hiện thao tác tương ứng.

Cần dùng đúng loại `Predicate`:

```java
import com.querydsl.core.types.Predicate;
```

Đây không phải `java.util.function.Predicate<T>`. Predicate của Java dùng để kiểm tra một đối tượng trong mã Java, còn Predicate của Querydsl là một cấu trúc biểu thức để adapter chuyển thành truy vấn phù hợp.

## 3. Chuẩn bị domain, Q-type và repository

### 3.1. Domain sử dụng trong ví dụ

Giả sử `Customer` có các thuộc tính được mapping đúng với kho dữ liệu:

| Thuộc tính | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất |
| `displayName` | `String` | Tên hiển thị |
| `email` | `String` | Email tra cứu |
| `country` | `String` | Mã quốc gia |
| `active` | `boolean` | Trạng thái kích hoạt |

Domain có getter và các thành phần cần thiết cho module. Q-type tương ứng được giả định là `QCustomer`, với biến mặc định `QCustomer.customer`.

```java
QCustomer customer = QCustomer.customer;
```

Các đường dẫn như `customer.country` và `customer.active` đại diện thuộc tính domain. Nếu đổi tên thuộc tính và tạo lại Q-type, nhiều lỗi tham chiếu có thể được phát hiện khi biên dịch. Điều đó không thay thế việc xác minh mapping hoặc khả năng thực thi của kho dữ liệu.

### 3.2. Repository

```java
import org.springframework.data.repository.Repository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends Repository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
```

`Repository` là marker interface. Ví dụ chỉ khai báo khả năng truy vấn Querydsl, không mặc nhiên thêm toàn bộ các phương thức CRUD.

Các đoạn mã tiếp theo giả định có `customerRepository` do ứng dụng cung cấp, cùng biến `customer` và các import Querydsl phù hợp.

### 3.3. Dữ liệu minh họa

| id | displayName | email | country | active |
| --- | --- | --- | --- | --- |
| 101 | An | shared@example.test | VN | true |
| 102 | An | shared@example.test | VN | false |
| 103 | Binh | binh@example.test | TH | true |
| 104 | Chi | chi@example.test | VN | true |
| 105 | Dung | dung@example.test | VN | false |

Quốc gia VN có bốn khách hàng, TH có một khách hàng và JP không có khách hàng. Hai bản ghi cùng email được giữ có chủ đích để minh họa lỗi nhiều kết quả.

## 4. Hợp đồng của bốn phương thức chính

| Phương thức | Kiểu trả về ở interface Commons | Không có kết quả | Một kết quả | Nhiều kết quả |
| --- | --- | --- | --- | --- |
| `findOne(predicate)` | `Optional<T>` | Optional rỗng | Optional chứa đối tượng | Ném `IncorrectResultSizeDataAccessException` |
| `findAll(predicate)` | `Iterable<T>` | Iterable không có phần tử | Một phần tử | Các phần tử phù hợp |
| `count(predicate)` | `long` | `0L` | `1L` | Số lượng phù hợp |
| `exists(predicate)` | `boolean` | `false` | `true` | `true` |

Các phương thức nhận predicate yêu cầu đối số không null. Không dùng null làm quy ước “không lọc” nếu hợp đồng không cho phép.

Đặc biệt, `findOne` không có nghĩa “lấy phần tử đầu tiên”. Nó có nghĩa truy vấn cho phép tối đa một kết quả.

## 5. findOne: tra cứu với hợp đồng tối đa một kết quả

### 5.1. Có đúng một kết quả

```java
import java.util.Optional;

Predicate inThailand = customer.country.eq("TH");

Optional<Customer> result =
    customerRepository.findOne(inThailand);
```

Với dữ liệu minh họa, Optional chứa khách hàng 103.

Một trường hợp nghiệp vụ thường gặp là tra cứu theo mã mà ứng dụng kỳ vọng duy nhất. Kỳ vọng đó cần phù hợp với điều kiện thực tế và cơ chế bảo đảm dữ liệu của kho.

### 5.2. Không có kết quả

```java
Predicate inJapan = customer.country.eq("JP");

Optional<Customer> result =
    customerRepository.findOne(inJapan);
```

Kết quả là `Optional.empty()`, không phải một Customer có các field null.

Nếu nghiệp vụ yêu cầu phải tồn tại, xử lý Optional rõ ràng:

```java
Customer required = customerRepository.findOne(inJapan)
    .orElseThrow(() -> new IllegalStateException(
        "Không tìm thấy khách hàng"
    ));
```

Exception trên chỉ minh họa lỗi ứng dụng. Dự án có thể dùng loại lỗi nghiệp vụ phù hợp và ánh xạ sang phản hồi API ở tầng tương ứng.

### 5.3. Có nhiều kết quả

```java
Predicate inVietnam = customer.country.eq("VN");

Optional<Customer> result =
    customerRepository.findOne(inVietnam);
```

Có bốn khách hàng phù hợp nên lời gọi ném `org.springframework.dao.IncorrectResultSizeDataAccessException`. Nó không trả khách hàng 101 một cách tùy ý.

Tương tự:

```java
Predicate sharedEmail = customer.email.eq(
    "shared@example.test"
);

customerRepository.findOne(sharedEmail);
```

Hai khách hàng cùng email làm hợp đồng tối đa một kết quả bị vi phạm.

Không nên bắt lỗi nhiều kết quả rồi trả Optional rỗng. Cách đó biến dữ liệu trùng thành thông báo không tìm thấy dữ liệu, làm mất thông tin cần xử lý.

Nếu nghiệp vụ thực sự cho phép nhiều kết quả và chỉ muốn chọn một bản ghi theo thứ tự, hãy dùng cơ chế chọn phần tử đầu hoặc phân trang phù hợp với module. Đừng dùng `findOne` để che giấu phần còn lại của tập kết quả.

## 6. findAll: lấy nhiều kết quả

### 6.1. Nhận đúng kiểu Iterable

```java
Predicate inVietnam = customer.country.eq("VN");

Iterable<Customer> customers =
    customerRepository.findAll(inVietnam);

for (Customer result : customers) {
    System.out.println(result.getId());
}
```

Ở cấp interface Commons, kiểu trả về là `Iterable<Customer>`. Không gán trực tiếp kết quả vào `List<Customer>` chỉ vì đã thấy một implementation cụ thể trả về List.

Iterable rỗng biểu diễn không có kết quả. Nó không cần được thay bằng null.

Không gọi `findAll` chỉ để chuyển kết quả thành collection rồi đếm hoặc kiểm tra rỗng, nếu nhu cầu thực sự là `count` hoặc `exists`. Chiến lược lấy và giữ dữ liệu phụ thuộc implementation, nhưng phương thức yêu cầu các đối tượng vẫn diễn đạt nhiều thông tin hơn một số đếm hoặc boolean.

### 6.2. Yêu cầu thứ tự bằng Sort

```java
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.asc("displayName"),
    Sort.Order.asc("id")
);

Iterable<Customer> customers =
    customerRepository.findAll(inVietnam, sort);
```

Tên trong Sort là tên thuộc tính domain. Trong ví dụ, hai khách hàng tên An được phân định bằng ID tăng dần.

Không có thứ tự rõ ràng thì không nên dựa vào thứ tự chèn, thứ tự ID hoặc kết quả quan sát được trong một lần chạy.

### 6.3. Yêu cầu thứ tự bằng biểu thức Querydsl

Khi module hỗ trợ biến thể nhận các `OrderSpecifier`, có thể viết:

```java
Iterable<Customer> customers = customerRepository.findAll(
    inVietnam,
    customer.displayName.asc(),
    customer.id.asc()
);
```

Ưu điểm là tham chiếu đường dẫn qua Q-type thay vì chuỗi tên thuộc tính. Nhưng type safety không bảo đảm mọi phép sắp xếp, cấu trúc lồng nhau hay biểu thức đều được module thực thi.

Các ví dụ trên giả định kho sắp xếp các tên theo thứ tự minh họa. Collation, thứ tự null và hỗ trợ đường dẫn lồng nhau cần được đối chiếu với kho cụ thể.

## 7. Phân trang tập kết quả

Nếu tập dữ liệu có thể lớn, dùng biến thể nhận `Pageable` khi module hỗ trợ:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

Pageable pageable = PageRequest.of(0, 2, sort);

Page<Customer> page =
    customerRepository.findAll(inVietnam, pageable);
```

Ý nghĩa:

- Chỉ số trang bắt đầu từ 0.
- Kích thước trang là 2.
- Thứ tự được đặt trong Pageable.
- Nội dung là các khách hàng phù hợp với predicate.

Với dữ liệu minh họa:

| Chỉ số trang | ID trong trang | Tổng số khách hàng phù hợp |
| --- | --- | --- |
| 0 | 101, 102 | 4 |
| 1 | 104, 105 | 4 |
| 2 | Không có | 4 |

Bảng giả định dữ liệu không thay đổi giữa các lần đọc.

Các giá trị sau có ý nghĩa khác nhau:

```java
int returnedSize = page.getNumberOfElements();
int requestedSize = page.getSize();
long totalElements = page.getTotalElements();
```

Một trang không có nội dung có thể chỉ là trang vượt phạm vi. Nó không nhất thiết chứng minh toàn bộ predicate không phù hợp với bản ghi nào.

Để cung cấp tổng số phần tử, implementation có thể cần thêm truy vấn đếm hoặc suy ra tổng từ tình huống hiện tại. Không khẳng định mọi lần gọi luôn có đúng hai truy vấn.

Thêm khóa duy nhất như ID làm tiêu chí cuối giúp phân định thứ tự cho một tập dữ liệu. Nó không tạo snapshot giữa các lần lấy trang; thay đổi dữ liệu vẫn có thể làm các trang theo offset bị dịch chuyển.

Nếu chỉ cần phần tử đầu tiên, một trang kích thước 1 là một phương án dựa trên API có sẵn, nhưng metadata Page có thể kéo theo công việc đếm. Chọn API phù hợp khác của module khi cần tránh chi phí đó.

## 8. count: đếm số kết quả phù hợp

```java
long total = customerRepository.count(inVietnam);
```

Với dữ liệu minh họa, kết quả là `4L`. Nếu dùng điều kiện quốc gia JP thì kết quả là `0L`.

Đếm một điều kiện kết hợp:

```java
Predicate activeInVietnam = customer.country.eq("VN")
    .and(customer.active.isTrue());

long totalActive =
    customerRepository.count(activeInVietnam);
```

Kết quả minh họa là `2L`, ứng với các khách hàng 101 và 104.

Kiểu trả về là `long`. Nếu tầng khác chỉ nhận int, cần kiểm tra giới hạn trước khi chuyển kiểu.

`count` diễn đạt đúng yêu cầu số lượng và cho implementation cơ hội thực hiện phép đếm tại kho. Nó không yêu cầu ứng dụng nhận từng Customer để đếm kích thước một collection.

Không nên suy ra mọi module đều sinh SQL COUNT. Ngay cả phép đếm chuyên biệt cũng có thể tốn kém khi điều kiện rộng, index không phù hợp hoặc kho phải duyệt nhiều dữ liệu.

Trong các ví dụ truy vấn trực tiếp Customer, số đếm là số khách hàng phù hợp. Không tự diễn giải nó thành số email khác nhau hoặc số nhóm. Những nhu cầu như đếm distinct, tổng hợp và group by cần API cùng truy vấn chuyên biệt phù hợp.

## 9. exists: chỉ kiểm tra có dữ liệu hay không

```java
boolean found = customerRepository.exists(inVietnam);
```

Với điều kiện VN, kết quả là true; với JP, kết quả là false.

Nếu nghiệp vụ hỏi “Có khách hàng nào đang kích hoạt ở VN không?”, hãy viết trực tiếp:

```java
Predicate activeInVietnam = customer.country.eq("VN")
    .and(customer.active.isTrue());

boolean found =
    customerRepository.exists(activeInVietnam);
```

So với `count(predicate) > 0`, exists chỉ yêu cầu câu trả lời có hoặc không. Module có thể chọn cách kiểm tra phù hợp mà không phải cung cấp tổng số chính xác.

Tuy nhiên, không hứa rằng mọi implementation đều dùng cùng một lệnh, luôn đọc đúng một bản ghi hay luôn nhanh hơn trong mọi tình huống. Cần quan sát truy vấn và đặc tính kho nếu hiệu năng là yêu cầu chính.

`exists` cũng không thể phân biệt một với nhiều kết quả: cả hai đều trả true. Nếu ứng dụng cần phát hiện trùng dữ liệu, phải dùng hợp đồng phù hợp như `findOne` hoặc một phép kiểm tra số lượng có chủ đích.

## 10. Tạo predicate từ bộ lọc tùy chọn

Querydsl chỉ thêm các điều kiện mà mã xây dựng biểu thức. Khác với QBE đọc giá trị trên probe, việc domain có `boolean active` không tự thêm điều kiện `active = false` vào một predicate chỉ chứa country.

Tuy nhiên, đầu vào tìm kiếm vẫn cần biểu diễn việc người dùng có chọn bộ lọc hay không:

```java
public record CustomerFilter(
    String country,
    Boolean active
) {}
```

Quy ước ví dụ:

- Country null hoặc chỉ chứa khoảng trắng: không lọc quốc gia.
- Active null: không lọc trạng thái.
- Active false: lọc khách hàng chưa kích hoạt.
- Nếu không còn tiêu chí nào: từ chối truy vấn trong thao tác này.

Bộ chuyển đổi dùng `BooleanBuilder`:

```java
import java.util.Objects;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;

public final class CustomerPredicates {

    private CustomerPredicates() {}

    public static Predicate from(CustomerFilter filter) {
        Objects.requireNonNull(filter, "filter");

        QCustomer customer = QCustomer.customer;
        BooleanBuilder builder = new BooleanBuilder();

        if (filter.country() != null
                && !filter.country().isBlank()) {
            builder.and(customer.country.eq(
                filter.country().trim()
            ));
        }

        if (filter.active() != null) {
            builder.and(customer.active.eq(
                filter.active()
            ));
        }

        if (!builder.hasValue()) {
            throw new IllegalArgumentException(
                "Cần ít nhất một tiêu chí tìm kiếm"
            );
        }

        return builder;
    }
}
```

Ví dụ dùng cú pháp record của Java 17 trở lên. Có thể thay bằng DTO class thông thường.

```java
Predicate inactiveInVietnam = CustomerPredicates.from(
    new CustomerFilter("VN", false)
);

Iterable<Customer> customers =
    customerRepository.findAll(inactiveInVietnam, sort);

long total =
    customerRepository.count(inactiveInVietnam);

boolean found =
    customerRepository.exists(inactiveInVietnam);
```

Trên dữ liệu minh họa, tập kết quả có ID 102 và 105, số đếm là 2, kiểm tra tồn tại trả true.

Điều kiện `filter.active() != null` giữ được cả true và false. Nếu chỉ thêm điều kiện khi `Boolean.TRUE.equals(filter.active())`, yêu cầu tìm false sẽ bị mất.

Builder được tạo mới trong mỗi lần chuyển đổi. Không dùng chung một BooleanBuilder có thể thay đổi giữa nhiều request.

## 11. Ba ý nghĩa khác nhau liên quan đến null

| Trường hợp | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Đối số predicate của repository là null | Không đáp ứng hợp đồng yêu cầu predicate | Tạo điều kiện hợp lệ hoặc chọn API phù hợp |
| Giá trị trong DTO tìm kiếm là null | Có thể là người dùng không chọn tiêu chí | Bộ chuyển đổi quyết định không thêm điều kiện |
| Muốn tìm bản ghi có email null | Một điều kiện nghiệp vụ thực sự | Dùng biểu thức `customer.email.isNull()` nếu mapping hỗ trợ |

Ví dụ điều kiện tìm email null:

```java
Predicate missingEmail = customer.email.isNull();

Iterable<Customer> customers =
    customerRepository.findAll(missingEmail);
```

Không dùng `customer.email.eq(null)` thay cho `isNull()`; API Querydsl yêu cầu biểu diễn phép kiểm tra null bằng toán tử phù hợp.

Một BooleanBuilder chưa có điều kiện cũng khác với một biến Predicate có giá trị null. Bộ chuyển đổi ở phần trước chủ động từ chối builder rỗng theo quy tắc của thao tác tìm kiếm ví dụ. Đó không phải quy tắc bắt buộc cho mọi màn hình hay mọi API của Commons.

Nếu ứng dụng cho phép tìm kiếm không có tiêu chí, cần thiết kế rõ cách truy vấn, phân trang và phạm vi dữ liệu. Không dựa vào một quy ước null không được phương thức hỗ trợ.

## 12. Tính duy nhất cần được bảo đảm ở cơ chế lưu trữ

Giả sử ứng dụng kiểm tra email trước khi tạo khách hàng:

```text
1. exists(email) trả false
2. Ghi khách hàng mới với email đó
```

Hai request có thể đồng thời quan sát false trước khi bất kỳ request nào hoàn tất bước ghi. Cả hai sau đó cùng cố tạo khách hàng với một email.

Do đó:

- Exists hữu ích để phản hồi sớm hoặc cung cấp thông tin cho giao diện.
- Nó không tự tạo khóa và không bảo đảm dữ liệu giữ nguyên sau lần kiểm tra.
- Nếu email phải duy nhất, kho dữ liệu cần cơ chế tương ứng, chẳng hạn unique constraint hoặc unique index với đúng phạm vi và quy tắc so sánh.
- Luồng ghi vẫn phải xử lý trường hợp cơ chế duy nhất từ chối thao tác.

`findOne` cũng chỉ kiểm tra cardinality của kết quả đọc. Nó không ngăn một request khác tạo bản ghi trùng ở thời điểm sau.

Quy tắc so khớp phải nhất quán với quy tắc duy nhất. Nếu nghiệp vụ coi email không phân biệt hoa thường, cần thiết kế chuẩn hóa, truy vấn và ràng buộc lưu trữ tương ứng; chỉ thay một biểu thức tìm kiếm không tự thay đổi cách kho bảo đảm duy nhất.

## 13. Các lần đọc riêng không mặc nhiên có cùng snapshot

Cùng một predicate không có nghĩa cùng thời điểm quan sát:

```java
boolean found =
    customerRepository.exists(inVietnam);

long total =
    customerRepository.count(inVietnam);

Iterable<Customer> customers =
    customerRepository.findAll(inVietnam);
```

Nếu dữ liệu thay đổi giữa các lời gọi, kết quả có thể khác điều suy ra từ lần đọc trước. Ví dụ, exists có thể trả true rồi count trả 0 nếu các bản ghi bị xóa ở khoảng giữa.

Tương tự, không nên đếm trước để quyết định có được gọi findOne hay không. Bước đếm thêm một lần đọc, còn dữ liệu vẫn có thể thay đổi trước bước lấy kết quả. FindOne đã có hợp đồng xử lý 0, 1 và nhiều kết quả.

Nếu nghiệp vụ cần quan sát nhất quán, cần xem xét transaction, mức cô lập và khả năng của kho. Cùng nằm trong một phương thức Java hoặc cùng tái sử dụng một predicate không tự tạo snapshot. Ngay cả khi có transaction, mức cô lập và implementation vẫn quyết định các bảo đảm thực tế.

## 14. Ranh giới giữa Commons, Querydsl và module lưu trữ

Ba lớp có vai trò khác nhau:

| Lớp | Cung cấp điều gì? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| Querydsl | Kiểu biểu thức, Q-type, phép kết hợp điều kiện | Mọi biểu thức đều chạy được trên mọi kho |
| Spring Data Commons | Hợp đồng executor, Optional, Iterable, Sort, Pageable | Một implementation Querydsl cho mọi module |
| Module và kho dữ liệu | Mapping, dịch truy vấn, đếm, kiểm tra tồn tại, phân trang | Cùng câu lệnh và cùng chi phí với kho khác |

Q-type không phải đối tượng domain đã tải từ kho. Nó là mô hình đường dẫn và biểu thức phục vụ xây truy vấn.

`QuerydslPredicateExecutor` cũng không phải toàn bộ query API của Querydsl. Những nhu cầu như chọn biểu thức tổng hợp, trả tuple, group by, join tùy chỉnh hoặc điều khiển truy vấn chuyên sâu có thể cần repository fragment hay API truy vấn riêng của module.

Với quan hệ, join hoặc cách mapping phức tạp, phải xác minh đơn vị kết quả, cách xử lý trùng và phép đếm của truy vấn thực tế. Không suy ra số bản ghi lưu trữ ở mức thấp luôn bằng số đối tượng domain quan sát được chỉ từ tên phương thức.

Khi hiệu năng quan trọng, hãy đánh giá điều kiện thực tế, index và truy vấn do module thực thi. Các kết luận như “exists luôn chỉ đọc một dòng”, “count luôn rẻ” hoặc “mọi findAll đều có cùng chiến lược tải” vượt quá hợp đồng dùng chung.

## 15. Chọn phương thức theo nhu cầu

| Nhu cầu nghiệp vụ | Lựa chọn |
| --- | --- |
| Tra cứu một đối tượng, dữ liệu không được phép có nhiều kết quả | `findOne(predicate)` |
| Tra cứu đúng một đối tượng và phải báo lỗi khi vắng | `findOne(predicate)` cùng xử lý Optional rỗng |
| Lấy các đối tượng phù hợp trong tập nhỏ | `findAll(predicate)` |
| Hiển thị kết quả có thứ tự | `findAll(predicate, sort)` hoặc OrderSpecifier được hỗ trợ |
| Hiển thị từng trang với metadata | `findAll(predicate, pageable)` |
| Chỉ cần số lượng | `count(predicate)` |
| Chỉ cần biết có dữ liệu | `exists(predicate)` |
| Chọn một phần tử đầu dù có thể có nhiều phần tử | API chọn đầu hoặc giới hạn phù hợp; không coi findOne là phép chọn đầu |

Trước khi viết lời gọi repository, hãy diễn đạt câu hỏi thành một trong các nhu cầu trên. Kích thước vùng hiển thị trên màn hình không quyết định tính duy nhất của dữ liệu.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `java.util.function.Predicate` | Không tương thích với executor Querydsl | Import Predicate từ Querydsl |
| Dùng findOne để lấy bất kỳ một bản ghi | Lỗi khi có nhiều kết quả | Chọn cơ chế lấy đầu hoặc giới hạn phù hợp |
| Gọi Optional.get mà không xử lý vắng dữ liệu | Có thể lỗi khi không tìm thấy | Dùng map, orElse hoặc orElseThrow theo nghiệp vụ |
| Chuyển lỗi nhiều kết quả thành Optional rỗng | Che giấu dữ liệu trùng | Giữ hoặc ánh xạ lỗi cardinality rõ ràng |
| Gán findAll trực tiếp vào List | Không khớp kiểu trả về ở interface | Dùng Iterable hoặc chuyển đổi có chủ đích |
| Lấy toàn bộ đối tượng chỉ để đếm | Tải dữ liệu không cần thiết | Dùng count |
| Đếm mọi kết quả chỉ để hỏi có dữ liệu | Yêu cầu thông tin dư so với nhu cầu | Dùng exists |
| Chỉ thêm active khi giá trị là true | Mất tiêu chí false | Kiểm tra có giá trị bằng điều kiện khác null |
| Truyền null với ý nghĩa không lọc | Vi phạm hợp đồng đối số | Thiết kế trường hợp không có tiêu chí rõ ràng |
| Cho rằng kiểm tra tồn tại bảo đảm không trùng khi ghi | Có thể xảy ra tranh chấp đồng thời | Bảo đảm duy nhất bằng cơ chế lưu trữ phù hợp |

## 17. Bài tập tự kiểm tra

Dùng bộ dữ liệu minh họa:

1. Predicate quốc gia VN tạo kết quả gì với findOne, count và exists?
2. Với quốc gia JP, findOne trả null hay Optional rỗng?
3. Khi lấy khách hàng tên An, có thể dùng findOne để tùy ý chọn một người không?
4. Với `CustomerFilter("VN", false)`, những ID nào phù hợp?
5. Vì sao kiểu trả về của findAll cần được đọc từ interface thay vì suy từ implementation?
6. Khi exists trả false, có thể khẳng định request khác chưa tạo dữ liệu trước lần ghi tiếp theo không?
7. Muốn tìm email null thì bỏ qua bộ lọc email hay dùng isNull?

Gợi ý đáp án:

1. FindOne báo lỗi nhiều kết quả; count trả 4L; exists trả true.
2. Optional rỗng.
3. Không. Hai bản ghi cùng tên làm vi phạm hợp đồng tối đa một kết quả.
4. ID 102 và 105.
5. Vì hợp đồng Commons là Iterable; một loại trả về cụ thể hơn không phải giả định chung cho mọi repository.
6. Không. Có khoảng thời gian dữ liệu có thể thay đổi giữa kiểm tra và ghi.
7. Dùng isNull để diễn đạt điều kiện tìm null. Bỏ qua bộ lọc là không yêu cầu điều kiện đó.

Nguyên tắc áp dụng là tách điều kiện Querydsl khỏi cách nhận kết quả, chọn phương thức theo thông tin thật sự cần và giữ rõ ba trường hợp không có, có một, có nhiều kết quả. Những bảo đảm về mapping, hiệu năng và tính nhất quán phải được đối chiếu với module lưu trữ đang sử dụng.
