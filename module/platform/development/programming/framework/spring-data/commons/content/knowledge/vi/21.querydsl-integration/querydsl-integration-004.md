# Kết hợp Predicate với Sort và Pageable

Khi tìm kiếm bằng Querydsl trong Spring Data, ứng dụng thường phải trả lời ba câu hỏi riêng: bản ghi nào được chọn, kết quả được sắp xếp ra sao và cần lấy đoạn nào của tập kết quả. `Predicate`, `Sort` và `Pageable` đảm nhận ba vai trò đó.

Spring Data Commons cung cấp `QuerydslPredicateExecutor` để công bố các thao tác repository sử dụng predicate Querydsl. Store module cụ thể mới triển khai việc chuyển predicate, thứ tự và phân trang thành truy vấn. Vì vậy, một interface dùng chung không có nghĩa mọi store đều hỗ trợ Querydsl hoặc mọi biểu thức sắp xếp đều thực thi được như nhau.

Bài học tập trung vào cách kết hợp ba thành phần, lựa chọn đúng overload và giữ đúng ý nghĩa của kết quả phân trang. Các ví dụ giả định dự án đã có tích hợp Querydsl phù hợp với store, các Q-type được sinh đúng và repository có thể sử dụng executor tương ứng.

## 1. Phân biệt ba thành phần của yêu cầu tìm kiếm

| Thành phần | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| Querydsl `Predicate` | Bản ghi nào được phép tham gia tập kết quả? | Khách hàng ACTIVE, chi tiêu từ một triệu |
| Spring Data `Sort` | Các bản ghi khớp đứng theo thứ tự nào? | Mới tạo trước, trùng thời gian thì id lớn trước |
| Spring Data `Pageable` | Cần lấy trang nào, kích thước bao nhiêu, theo thứ tự nào? | Trang 0, mỗi trang 20 phần tử |

Một yêu cầu có thể đọc theo thứ tự logic:

```text
Tập dữ liệu
    -> lọc theo Predicate
    -> sắp xếp theo Sort
    -> chọn đoạn theo Pageable
    -> ánh xạ kết quả trả về
```

Predicate không tự chứa số trang. Sort không tự loại bản ghi. Pageable không thay thế điều kiện lọc, nhưng đã mang cấu hình Sort bên trong nó.

Khi cần trang có thứ tự, cách gọi trọng tâm là:

```java
Page<Customer> result = repository.findAll(predicate, pageable);
```

Thứ tự nằm trong `pageable.getSort()`. Không cần một tham số Sort riêng bên cạnh Pageable.

## 2. Mô hình và repository dùng trong ví dụ

Giả sử `Customer` có các thuộc tính miền:

| Thuộc tính | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất |
| `tenantId` | `String` | Phạm vi dữ liệu của khách hàng |
| `fullName` | `String` | Họ tên |
| `email` | `String` | Email |
| `status` | `CustomerStatus` | Trạng thái nghiệp vụ |
| `totalSpent` | `BigDecimal` | Tổng chi tiêu |
| `createdAt` | `Instant` | Thời điểm tạo |

```java
public enum CustomerStatus {
    ACTIVE,
    SUSPENDED,
    CLOSED
}
```

Trong các ví dụ chính, `createdAt` có giá trị và `id` là duy nhất. Nếu mô hình cho phép `createdAt` null, cần quyết định thêm vị trí của null trong thứ tự theo khả năng store.

Giả định Q-type được sinh là `QCustomer`, với biến gốc `QCustomer.customer`. Các thuộc tính như `customer.status` và `customer.totalSpent` có kiểu Querydsl tương ứng. Mapping JPA, mapping tài liệu và cấu hình sinh Q-type phải phù hợp với dự án; bài không định nghĩa một mapping dùng nguyên trạng cho mọi kho dữ liệu.

Repository:

```java
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
```

Cần phân biệt đúng các import:

```java
import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
```

`Predicate` ở đây là `com.querydsl.core.types.Predicate`, không phải `java.util.function.Predicate`. Predicate Querydsl mô tả biểu thức để store dịch thành truy vấn. Predicate của Java kiểm tra một đối tượng trong bộ nhớ; không thể thay thế trực tiếp cho nhau ở repository.

## 3. Chọn đúng overload của QuerydslPredicateExecutor

Các overload thường dùng:

| Lời gọi | Kiểu kết quả | Nhu cầu |
| --- | --- | --- |
| `findAll(predicate)` | `Iterable<T>` | Lấy kết quả khớp, không yêu cầu trang |
| `findAll(predicate, sort)` | `Iterable<T>` | Lấy kết quả khớp có thứ tự |
| `findAll(predicate, pageable)` | `Page<T>` | Lấy một trang có metadata |
| `findAll(predicate, orderSpecifiers...)` | `Iterable<T>` | Sắp xếp bằng Querydsl OrderSpecifier |
| `count(predicate)` | `long` | Đếm bản ghi khớp |
| `exists(predicate)` | `boolean` | Kiểm tra có bản ghi khớp |

Hợp đồng yêu cầu một predicate phù hợp; không truyền `null` để biểu diễn “không lọc”. Nếu ứng dụng thực sự cho phép truy vấn toàn bộ, cần sử dụng cách biểu diễn và API hợp lệ, đồng thời quyết định rõ phạm vi dữ liệu của thao tác đó.

Không có overload chung dạng:

```java
// Không phải chữ ký của QuerydslPredicateExecutor.
repository.findAll(predicate, sort, pageable);
```

Cách kết hợp là đưa Sort vào Pageable:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));

Pageable pageable = PageRequest.of(0, 20, sort);
Page<Customer> result = repository.findAll(predicate, pageable);
```

Việc kiểu trả về là `Iterable<T>` không chứng minh dữ liệu được stream từ kho theo từng phần tử hoặc tự được giới hạn. Không dùng overload nhận Sort nếu yêu cầu thực tế là chỉ lấy một trang hữu hạn.

## 4. Tạo Predicate động với một phạm vi bắt buộc

Giả sử yêu cầu tìm kiếm có các bộ lọc tùy chọn:

- Tên chứa một đoạn văn bản.
- Trạng thái bằng một giá trị đã chọn.
- Tổng chi tiêu lớn hơn hoặc bằng một mức tối thiểu.

Phạm vi tenant đến từ ngữ cảnh ứng dụng đã xác định, không lấy một chuỗi bất kỳ do người gọi gửi để thay cho cơ chế kiểm soát phạm vi.

```java
import java.math.BigDecimal;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;

static Predicate customerPredicate(
        String currentTenantId,
        String fullName,
        CustomerStatus status,
        BigDecimal minimumSpent) {

    if (currentTenantId == null || currentTenantId.isBlank()) {
        throw new IllegalArgumentException("Thiếu phạm vi tenant");
    }
    if (minimumSpent != null && minimumSpent.signum() < 0) {
        throw new IllegalArgumentException(
                "Mức chi tiêu tối thiểu không được âm");
    }

    QCustomer customer = QCustomer.customer;
    BooleanBuilder predicate = new BooleanBuilder(
            customer.tenantId.eq(currentTenantId));

    if (fullName != null && !fullName.isBlank()) {
        predicate.and(customer.fullName.containsIgnoreCase(fullName.trim()));
    }
    if (status != null) {
        predicate.and(customer.status.eq(status));
    }
    if (minimumSpent != null) {
        predicate.and(customer.totalSpent.goe(minimumSpent));
    }

    return predicate;
}
```

`BooleanBuilder` được tạo riêng cho mỗi lần dựng điều kiện vì nó có thể thay đổi khi gọi `and` hoặc `or`. Không giữ một builder dùng chung trong field rồi bổ sung điều kiện của nhiều yêu cầu khác nhau.

Trong ví dụ, khi không truyền các bộ lọc tùy chọn, predicate vẫn giữ điều kiện tenant. Không dùng việc `BooleanBuilder` chưa có điều kiện như một cách che khuất quyết định truy vấn rộng đến đâu. Cũng cần thận trọng nếu lấy `getValue()` từ builder rỗng vì giá trị thu được có thể không phải predicate hợp lệ cho lời gọi tiếp theo.

Tên và mức chi tiêu được đưa vào biểu thức Querydsl có kiểu, không ghép thành văn bản JPQL hoặc SQL thủ công. Khả năng dịch `containsIgnoreCase` và quy tắc so sánh chuỗi vẫn cần được hiểu theo store, collation và chỉ mục.

## 5. Kết hợp Predicate với Sort khi chưa cần phân trang

Ví dụ lấy những khách hàng ACTIVE có chi tiêu từ một triệu, theo thứ tự mới tạo trước:

```java
Predicate predicate = customerPredicate(
        currentTenantId,
        null,
        CustomerStatus.ACTIVE,
        new BigDecimal("1000000"));

Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));

Iterable<Customer> customers = repository.findAll(predicate, sort);
```

Điều kiện lọc và thứ tự độc lập:

```text
tenantId bằng tenant hiện tại
AND status bằng ACTIVE
AND totalSpent >= 1000000

ORDER BY createdAt DESC, id DESC
```

Tên trong Sort là tên thuộc tính miền. Nếu Java dùng `createdAt` nhưng cột là `created_at`, cấu hình thông thường vẫn dùng `createdAt` theo hợp đồng ánh xạ của repository, không thay bằng tên cột SQL.

Một ưu điểm của Sort là có thể được dựng từ lựa chọn sắp xếp của tầng ứng dụng. Đổi lại, tên thuộc tính ở dạng chuỗi không có khả năng kiểm tra refactor giống đường dẫn Q-type. Đường dẫn sai có thể chỉ bị phát hiện khi thực thi.

Overload này phù hợp khi ứng dụng thực sự cần toàn bộ kết quả khớp và tập dữ liệu được kiểm soát. Nếu chỉ cần vài chục phần tử, nên dùng Pageable hoặc một API giới hạn khác mà store hỗ trợ để tránh lấy toàn bộ rồi cắt trong bộ nhớ.

## 6. Thứ tự có kiểu bằng OrderSpecifier và QSort

Querydsl có kiểu thứ tự riêng là `OrderSpecifier`. Có thể dùng đường dẫn Q-type:

```java
QCustomer customer = QCustomer.customer;

Iterable<Customer> customers = repository.findAll(
        predicate,
        customer.createdAt.desc(),
        customer.id.desc());
```

Tên `createdAt` và `id` được tham chiếu qua Q-type. Khi thuộc tính miền thay đổi và Q-type được sinh lại, mã dùng đường dẫn cũ có thể được phát hiện lỗi ở bước biên dịch.

`OrderSpecifier` khác với Spring Data `Sort`:

| Đặc điểm | Sort | OrderSpecifier |
| --- | --- | --- |
| Nguồn API | Spring Data Commons | Querydsl |
| Mô tả thuộc tính thường gặp | Chuỗi tên đường dẫn | Biểu thức hoặc đường dẫn Querydsl |
| Kiểm tra tên thuộc tính qua compiler | Hạn chế với chuỗi | Có khi dùng Q-type |
| Kết hợp trực tiếp với Pageable | Có | Cần cầu nối phù hợp |

Spring Data có `QSort` để biểu diễn các order specifier dưới dạng Sort. Với implementation Querydsl hỗ trợ cầu nối này:

```java
import org.springframework.data.querydsl.QSort;

QCustomer customer = QCustomer.customer;

QSort typedSort = new QSort(
        customer.createdAt.desc(),
        customer.id.desc());

Pageable pageable = PageRequest.of(0, 20, typedSort);
Page<Customer> result = repository.findAll(predicate, pageable);
```

Đây vẫn là overload nhận `Pageable`; `QSort` được đặt bên trong PageRequest vì nó là một dạng Sort. Không chuyển từng OrderSpecifier thành chuỗi tùy ý rồi kỳ vọng mọi biểu thức Querydsl sẽ được giữ nguyên.

Ví dụ chỉ dùng các đường dẫn scalar đơn giản. Khả năng sắp xếp bằng biểu thức phức tạp, hàm hoặc đường dẫn quan hệ cần được kiểm tra theo store và implementation. Việc biểu thức tồn tại trong API Querydsl không tự chứng minh executor của mọi module chấp nhận nó.

## 7. Kết hợp Predicate với Pageable

Một lời gọi phân trang đầy đủ:

```java
Predicate predicate = customerPredicate(
        currentTenantId,
        null,
        CustomerStatus.ACTIVE,
        new BigDecimal("1000000"));

Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));

PageRequest request = PageRequest.of(0, 20, sort);
Page<Customer> page = repository.findAll(predicate, request);
```

Page number của `PageRequest` bắt đầu từ 0:

| Page number | Page size | Offset về mặt logic |
| --- | --- | --- |
| 0 | 20 | 0 |
| 1 | 20 | 20 |
| 2 | 20 | 40 |

Offset được hiểu theo `pageNumber * pageSize`. Store áp dụng cơ chế giới hạn và bỏ qua tương ứng; không nên coi đây là một câu SQL có cú pháp cố định cho mọi kho dữ liệu.

Thông tin thường được lấy từ Page:

```java
List<Customer> content = page.getContent();
int pageNumber = page.getNumber();
int pageSize = page.getSize();
int returnedCount = page.getNumberOfElements();
long totalMatches = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

`getNumberOfElements()` là số phần tử trong trang hiện tại. `getTotalElements()` là tổng số phần tử khớp được xác định cho kết quả phân trang theo điều kiện truy vấn, không phải tổng toàn bộ khách hàng của mọi tenant.

Trang cuối có thể ít hơn page size. Nếu yêu cầu một trang vượt quá vùng có dữ liệu, content có thể rỗng dù tổng số bản ghi khớp vẫn lớn hơn 0. Không dùng content rỗng để tự động kết luận predicate không khớp bản ghi nào.

## 8. Vì sao phân trang cần thứ tự phân định đầy đủ?

Giả sử nhiều khách hàng có cùng `createdAt`. Nếu chỉ sắp xếp theo thời gian, các bản ghi bằng nhau ở khóa đó không có thứ tự được phân định đầy đủ.

```java
// Chưa phân định các bản ghi có cùng thời điểm tạo.
Sort sort = Sort.by("createdAt").descending();
```

Khi chia thành nhiều trang, sự thay đổi thứ tự giữa các bản ghi bằng khóa có thể làm kết quả khó dự đoán. Thêm một khóa duy nhất giúp xác định vị trí trong tập kết quả đang xét:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));
```

### Minh họa bằng dữ liệu

Giả sử có các khách hàng sau; các thời điểm đều dùng cùng múi giờ:

| id | tenantId | status | totalSpent | createdAt |
| --- | --- | --- | --- | --- |
| 101 | A | ACTIVE | 1500000 | 2026-11-20 09:00 |
| 102 | A | ACTIVE | 2000000 | 2026-11-21 10:00 |
| 103 | A | SUSPENDED | 3000000 | 2026-11-22 10:00 |
| 104 | A | ACTIVE | 500000 | 2026-11-23 10:00 |
| 105 | B | ACTIVE | 4000000 | 2026-11-24 10:00 |
| 106 | A | ACTIVE | 2500000 | 2026-11-21 10:00 |

Predicate là tenant A, ACTIVE và chi tiêu từ một triệu. Sort là `createdAt DESC, id DESC`.

Tập khớp sau sắp xếp:

```text
106 -> 102 -> 101
```

Với page size bằng 2:

| Yêu cầu | Content theo id | Number of elements | Total elements | Total pages |
| --- | --- | --- | --- | --- |
| Trang 0 | 106, 102 | 2 | 3 | 2 |
| Trang 1 | 101 | 1 | 3 | 2 |
| Trang 2 | Rỗng | 0 | 3 | 2 |

Id 106 đứng trước 102 vì hai bản ghi có cùng thời điểm tạo và id được sắp xếp giảm. Id 105 không tham gia dù mới hơn và chi tiêu cao hơn vì không thỏa phạm vi tenant.

Một thứ tự đầy đủ không tự tạo snapshot qua nhiều request. Nếu bản ghi mới được thêm trước ranh giới trang hoặc khóa sắp xếp bị sửa giữa hai lần đọc, offset pagination vẫn có thể gặp dịch chuyển vị trí. Yêu cầu duyệt ổn định trong dữ liệu thay đổi cần được đánh giá riêng, có thể sử dụng cơ chế keyset hoặc scrolling mà store hỗ trợ.

## 9. Page và truy vấn đếm

Để tạo metadata tổng số phần tử và số trang, implementation có thể cần thao tác đếm ngoài truy vấn lấy content.

Có thể hình dung:

```text
Truy vấn lấy content:
    Predicate + Sort + offset + page size

Truy vấn xác định tổng:
    Cùng ý nghĩa Predicate, không đếm riêng đoạn trang hiện tại
```

Không khẳng định mọi lời gọi Page luôn tạo đúng hai câu lệnh. Implementation có thể suy ra tổng trong một số trường hợp hoặc tối ưu cách đếm. Ngược lại, một truy vấn có quan hệ phức tạp có thể cần xử lý nhiều hơn mô hình đơn giản này.

Điểm cần kiểm tra là content và tổng số phản ánh cùng điều kiện nghiệp vụ. Nếu ứng dụng tự mở rộng repository, không được bỏ điều kiện tenant hoặc một bộ lọc tùy chọn khỏi truy vấn đếm rồi trả tổng không khớp dữ liệu.

### Đổi kiểu biến sang Slice không loại bỏ thao tác đếm

`Page` cũng cung cấp các khả năng của một slice. Nhưng việc nhận kết quả bằng biến kiểu `Slice` không đổi lời gọi executor đã chọn:

```java
// Vẫn đang gọi phương thức có hợp đồng trả Page.
Slice<Customer> slice = repository.findAll(predicate, pageable);
```

Không coi phép đổi kiểu tham chiếu này là cách bảo đảm tránh truy vấn đếm. Nếu chỉ cần biết còn dữ liệu tiếp hay không, cần chọn một API slice hoặc truy vấn tùy chỉnh được store hỗ trợ thay vì suy luận từ kiểu biến ở bên gọi. Khi dùng đoạn mã trên cần import `org.springframework.data.domain.Slice`.

Tương tự, `Pageable.unpaged()` không phải một giới hạn nhỏ mặc định. Nó biểu diễn không phân trang; nếu sử dụng trong luồng có nhiều dữ liệu, cần hiểu lượng kết quả mà implementation sẽ lấy.

## 10. Kiểm soát Pageable và lựa chọn sắp xếp từ đầu vào

Tầng ứng dụng nên có quy ước rõ ràng về page number, page size tối đa và các kiểu sắp xếp được cung cấp cho giao diện.

Ví dụ ánh xạ hai khóa giao diện sang thuộc tính miền:

```java
static Pageable customerPageable(
        int pageNumber,
        int pageSize,
        String sortKey,
        boolean descending) {

    if (pageNumber < 0) {
        throw new IllegalArgumentException("Số trang không được âm");
    }
    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException(
                "Kích thước trang phải nằm trong khoảng 1 đến 100");
    }

    String property;
    if ("created".equals(sortKey)) {
        property = "createdAt";
    } else if ("name".equals(sortKey)) {
        property = "fullName";
    } else {
        throw new IllegalArgumentException("Kiểu sắp xếp không được hỗ trợ");
    }

    Sort primary = descending
            ? Sort.by(property).descending()
            : Sort.by(property).ascending();

    Sort complete = primary.and(Sort.by("id").descending());
    return PageRequest.of(pageNumber, pageSize, complete);
}
```

Ở đây `id DESC` là quy tắc phân định được ứng dụng lựa chọn cho các trường hợp bằng khóa chính. Nếu sản phẩm yêu cầu quy tắc khác, cần thay đổi một cách có chủ đích.

Kết hợp với predicate:

```java
Predicate predicate = customerPredicate(
        currentTenantId,
        requestedName,
        requestedStatus,
        requestedMinimumSpent);

Pageable pageable = customerPageable(
        requestedPage,
        requestedSize,
        requestedSortKey,
        requestedDescending);

Page<Customer> page = repository.findAll(predicate, pageable);
```

Việc giới hạn các lựa chọn sắp xếp còn giúp tránh đường dẫn không có trong mô hình hoặc các phép duyệt quan hệ tốn chi phí mà màn hình không cần. Nếu giao diện đánh số trang từ 1, cần chuyển đổi ở ranh giới đầu vào theo một quy ước thống nhất, không thay đổi hợp đồng zero-based của PageRequest.

## 11. Quan hệ, collection và giới hạn của executor

Predicate Querydsl có thể diễn đạt nhiều biểu thức hơn một đối tượng mẫu QBE. Tuy nhiên, `QuerydslPredicateExecutor` không phải API tùy ý xây dựng toàn bộ truy vấn với mọi join, fetch plan, group, projection và count query riêng.

Các trường hợp cần xem xét kỹ:

| Tình huống | Vấn đề cần giải quyết |
| --- | --- |
| Sắp xếp qua quan hệ đơn trị | Khả năng duyệt đường dẫn, join và bản ghi không có quan hệ |
| Sắp xếp qua quan hệ collection | Một bản ghi gốc có thể tương ứng nhiều giá trị sắp xếp |
| Join một-nhiều để lọc | Có thể nhân dòng ở tầng truy vấn, ảnh hưởng content và tổng |
| Fetch collection cùng phân trang | Phụ thuộc store/provider; cần kiểm tra giới hạn và chi phí |
| Group hoặc aggregate | Định nghĩa phần tử kết quả và tổng số không còn như truy vấn entity đơn giản |
| Predicate hoặc order dùng hàm đặc thù | Khả năng dịch và tối ưu phụ thuộc store |

Ví dụ, yêu cầu “sắp xếp khách hàng theo thời điểm đơn hàng gần nhất” cần xác định một giá trị đại diện cho mỗi khách hàng. Không chỉ đưa một đường dẫn collection vào Sort rồi mặc định hệ thống đã chọn phép MAX và giữ đúng phân trang.

Khi cần điều khiển join, EXISTS, aggregate hoặc truy vấn đếm riêng, nên mở rộng repository bằng một implementation truy vấn phù hợp với module. Có thể dùng Querydsl ở tầng đó, nhưng đây là thiết kế truy vấn đầy đủ hơn các overload có sẵn của executor.

Q-type giúp kiểm tra kiểu biểu thức. Nó không tự bảo đảm chỉ mục phù hợp, loại join đúng ý nghĩa, không nhân bản dòng hoặc hiệu năng tốt trên mọi dữ liệu.

## 12. Ánh xạ Page sang dữ liệu đầu ra mà giữ metadata

Nếu cần trả DTO, có thể ánh xạ từng phần tử bằng `Page.map`:

```java
public record CustomerRow(Long id, String fullName, String email) {
    public static CustomerRow from(Customer customer) {
        return new CustomerRow(
                customer.getId(),
                customer.getFullName(),
                customer.getEmail());
    }
}
```

```java
Page<CustomerRow> response = repository
        .findAll(predicate, pageable)
        .map(CustomerRow::from);
```

Ví dụ record giả định Java 17 trở lên. Mỗi entity được chuyển thành đúng một `CustomerRow`, nên metadata phân trang vẫn có ý nghĩa trên cùng tập bản ghi.

Không dùng một bước lọc Java sau khi lấy Page rồi giữ nguyên tổng số:

```text
Lấy 20 khách hàng bằng repository
-> lọc tiếp theo điều kiện nghiệp vụ trong bộ nhớ
-> còn 7 khách hàng
-> vẫn trả totalElements ban đầu
```

Lúc đó kích thước trang và tổng không còn phản ánh điều kiện cuối cùng. Những bản ghi hợp lệ khác có thể đang nằm ở trang sau, nhưng ứng dụng đã trả một trang thiếu. Điều kiện quyết định bản ghi nào được chọn cần được đưa vào predicate hoặc một cơ chế truy vấn phù hợp trước khi phân trang.

`Page.map` cũng không thay thế projection ở tầng truy vấn. Nếu executor lấy entity đầy đủ rồi mới ánh xạ DTO, lượng dữ liệu đã đọc phụ thuộc truy vấn ban đầu. Nếu mục tiêu là chỉ đọc một số cột hoặc field, cần chọn API projection được store hỗ trợ và kiểm tra truy vấn thực tế.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách điều chỉnh |
| --- | --- | --- |
| Không tìm thấy overload ba tham số | Truyền Predicate, Sort và Pageable riêng | Đưa Sort vào PageRequest |
| Predicate không đúng kiểu | Import java.util.function.Predicate | Dùng com.querydsl.core.types.Predicate |
| Trang đầu bị bỏ qua | Truyền 1 vì nghĩ PageRequest bắt đầu từ 1 | Chuyển quy ước giao diện sang chỉ số bắt đầu từ 0 |
| Kết quả trùng khóa sắp xếp có vị trí không ổn định | Sort chưa có khóa phân định | Thêm id hoặc thuộc tính duy nhất phù hợp |
| Đường dẫn sắp xếp lỗi lúc chạy | Dùng tên cột hoặc tên field không tồn tại | Dùng thuộc tính miền hoặc QSort được hỗ trợ |
| Lấy quá nhiều dữ liệu | Dùng findAll với Sort thay vì Pageable | Chọn overload phân trang khi chỉ cần một đoạn |
| Đổi biến sang Slice nhưng vẫn có chi phí đếm | Lời gọi vẫn là phương thức trả Page | Dùng API slice thực sự nếu store cung cấp |
| Tổng số không khớp content | Truy vấn đếm khác điều kiện hoặc có nhân dòng | Kiểm tra predicate, join và ngữ nghĩa count |
| Các yêu cầu tìm kiếm ảnh hưởng nhau | Tái sử dụng BooleanBuilder mutable | Tạo builder mới cho từng yêu cầu |
| Sắp xếp qua collection cho kết quả khó hiểu | Chưa định nghĩa giá trị đại diện trên mỗi bản ghi gốc | Thiết kế truy vấn aggregate hoặc truy vấn tùy chỉnh |
| Sau khi lọc Java, page bị thiếu nhưng total vẫn lớn | Điều kiện áp dụng sau phân trang | Đưa điều kiện vào truy vấn trước khi lấy trang |

## 14. Tự diễn giải một lời gọi repository

Với lời gọi:

```java
Page<Customer> page = repository.findAll(
        customerPredicate(
                currentTenantId,
                requestedName,
                CustomerStatus.ACTIVE,
                new BigDecimal("1000000")),
        PageRequest.of(
                0,
                20,
                Sort.by("createdAt").descending()
                        .and(Sort.by("id").descending())));
```

Cần đọc được ý nghĩa đầy đủ:

1. Chỉ khách hàng thuộc tenant hiện tại được xét.
2. Nếu có tên tìm kiếm, áp dụng điều kiện tên cùng các bộ lọc ACTIVE và mức chi tiêu.
3. Tập khớp được sắp theo thời điểm tạo giảm, sau đó id giảm.
4. Lấy trang đầu theo hợp đồng zero-based, tối đa 20 phần tử trong content.
5. Metadata tổng số cần phản ánh cùng điều kiện lọc, theo cách implementation xác định tổng.
6. Khả năng thực thi và chi phí vẫn cần được đánh giá trên đúng store, mapping và dữ liệu.

Giữ rõ ba vai trò giúp mở rộng repository có kiểm soát: Predicate xác định tập kết quả, Sort xác định thứ tự, Pageable xác định đoạn cần lấy cùng thứ tự của đoạn đó. Khi yêu cầu vượt các overload sẵn có, việc mở rộng truy vấn cần giữ nhất quán cả content, count và ý nghĩa nghiệp vụ của từng phần tử.
