# Sắp xếp, phân trang và projection trong phạm vi hỗ trợ

Query by Example (QBE) xác định **bản ghi nào thỏa điều kiện** từ một đối tượng mẫu và `ExampleMatcher`. Khi hiển thị kết quả trên màn hình hoặc trả về API, ứng dụng còn cần quyết định thứ tự, kích thước trang và dữ liệu được đưa ra ngoài.

Trong Spring Data Commons, các abstraction `Sort`, `Pageable`, `Page` và fluent query giúp diễn đạt những yêu cầu này. Tuy nhiên, việc một phương thức có mặt trong API dùng chung không có nghĩa mọi module Spring Data đều thực thi mọi kiểu projection hoặc mọi tùy chọn truy vấn giống nhau.

## 1. Mục tiêu và mô hình xử lý

Sau bài này, bạn có thể:

- Kết hợp một `Example` với sắp xếp hoặc phân trang.
- Chọn thứ tự ổn định khi nhiều bản ghi có cùng khóa sắp xếp.
- Đọc đúng metadata của `Page` và hiểu chi phí liên quan đến tổng số kết quả.
- Dùng fluent query để yêu cầu projection khi module và phiên bản hỗ trợ.
- Phân biệt projection trong truy vấn với chuyển đổi kết quả bằng `Page.map`.
- Thiết kế phương án thay thế khi kho dữ liệu không hỗ trợ khả năng cần dùng.

Có thể tách yêu cầu tìm kiếm thành bốn câu hỏi:

| Thành phần | Câu hỏi cần trả lời | Abstraction thường dùng |
| --- | --- | --- |
| Điều kiện | Bản ghi nào phù hợp? | Probe, `ExampleMatcher`, `Example<T>` |
| Thứ tự | Bản ghi nào đứng trước? | `Sort` |
| Phân trang | Lấy phần nào của kết quả? | `Pageable`, `PageRequest` |
| Hình dạng kết quả | Mỗi phần tử cung cấp những thuộc tính nào? | Fluent projection hoặc DTO mapping |

Sắp xếp, phân trang và projection không bổ sung khả năng diễn đạt mọi điều kiện lọc. Nếu QBE không biểu diễn được điều kiện khoảng số hay nhóm điều kiện phức tạp mà nghiệp vụ cần, việc đổi hình dạng kết quả không khắc phục giới hạn đó.

## 2. Chuẩn bị repository và mẫu truy vấn

Các ví dụ sử dụng domain `Customer` có các thuộc tính:

| Thuộc tính | Kiểu Java | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất |
| `displayName` | `String` | Tên hiển thị |
| `email` | `String` | Địa chỉ thư điện tử |
| `country` | `String` | Mã quốc gia |

Giả định domain đã có getter, setter và mapping phù hợp với module lưu trữ. Các ví dụ không gắn annotation JPA hay MongoDB để tránh đồng nhất abstraction Commons với một loại kho dữ liệu.

Repository khai báo khả năng truy vấn theo ví dụ:

```java
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends Repository<Customer, Long>,
                QueryByExampleExecutor<Customer> {
}
```

Đây là cách ghép interface về mặt API. Module thực tế phải hỗ trợ QBE và tạo được implementation của repository tương ứng. `Repository` là marker interface; ví dụ không tự bổ sung toàn bộ phương thức CRUD.

Tạo mẫu tìm khách hàng theo quốc gia:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setCountry("VN");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreNullValues();

Example<Customer> example = Example.of(probe, matcher);
```

Ở đây, `id`, `displayName` và `email` đang null nên được bỏ qua. Nếu domain thực tế có thêm field nguyên thủy, field được khởi tạo sẵn hoặc giá trị mặc định khác, cần kiểm soát chúng bằng matcher để tránh thêm điều kiện ngoài ý muốn.

Các đoạn mã tiếp theo giả định đã có `customerRepository` và `example`. Cách so khớp chuỗi cụ thể, mapping và khả năng thực thi vẫn phải phù hợp với module đang sử dụng.

## 3. Sắp xếp với Sort

### 3.1. Áp dụng thứ tự trực tiếp khi lấy kết quả QBE

`QueryByExampleExecutor` cung cấp biến thể nhận `Example` và `Sort`:

```java
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.asc("displayName"),
    Sort.Order.asc("id")
);

Iterable<Customer> customers =
    customerRepository.findAll(example, sort);
```

Ý nghĩa yêu cầu:

1. Lọc theo `example`.
2. Sắp xếp theo `displayName` tăng dần.
3. Khi tên bằng nhau, sắp xếp tiếp theo `id` tăng dần.

Ở cấp interface Commons, biến thể này trả về `Iterable<S>`. Không nên gán trực tiếp vào `List<Customer>` chỉ vì một implementation cụ thể có thể trả về một loại collection hẹp hơn.

Tên trong `Sort` là đường dẫn thuộc tính của domain, chẳng hạn `displayName`, không phải tên cột như `display_name` hay tên getter như `getDisplayName`. Đường dẫn lồng nhau chỉ dùng được khi mapping và module hỗ trợ.

### 3.2. Không có Sort thì không có thứ tự hiển thị được bảo đảm

`Sort.unsorted()` biểu diễn việc không yêu cầu thứ tự. Không nên suy ra kết quả sẽ theo thứ tự chèn, thứ tự ID hay thứ tự quan sát được trong một lần chạy.

Một thứ tự ổn định đặc biệt quan trọng khi phân trang. Nếu chỉ sắp xếp theo tên và nhiều khách hàng cùng tên, thứ tự tương đối giữa họ có thể không xác định. Thêm khóa duy nhất như `id` làm tiêu chí cuối giúp xác định thứ tự cho một tập dữ liệu tại thời điểm truy vấn.

Khóa duy nhất không tạo ra snapshot giữa các lần đọc. Nếu dữ liệu thay đổi giữa hai yêu cầu trang, phân trang theo offset vẫn có thể lặp hoặc bỏ sót bản ghi.

### 3.3. Tùy chọn về chữ hoa, chữ thường và null cần được đối chiếu

Các yêu cầu như bỏ qua khác biệt hoa thường khi sắp xếp, đặt null trước hoặc đặt null sau không có hành vi thực thi giống nhau ở mọi kho dữ liệu.

Tương tự, collation của kho có thể ảnh hưởng thứ tự chữ có dấu. Nếu giao diện cần một quy tắc ngôn ngữ cụ thể, phải xác minh trên module và kho dữ liệu mục tiêu; không chỉ kiểm tra đối tượng `Sort` trong Java.

## 4. Phân trang với Pageable và PageRequest

### 4.1. Truy vấn một trang có thứ tự

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

Pageable pageable = PageRequest.of(0, 20, sort);

Page<Customer> page =
    customerRepository.findAll(example, pageable);
```

Các đối số của `PageRequest.of` lần lượt là:

- Chỉ số trang, bắt đầu từ `0`.
- Số phần tử tối đa trong một trang.
- Thứ tự áp dụng cho tập kết quả.

`PageRequest.of(0, 20, sort)` yêu cầu trang đầu. `PageRequest.of(1, 20, sort)` yêu cầu trang thứ hai, tương ứng offset 20 đối với mô hình phân trang theo offset.

Số trang phải không âm và kích thước trang phải lớn hơn 0. Ở biên API, nên giới hạn kích thước tối đa để một request không vô tình yêu cầu tải lượng dữ liệu quá lớn.

Đối với lời gọi `findAll(example, pageable)`, đặt thứ tự vào chính `Pageable`. Không cần lấy kết quả trước rồi sắp xếp từng trang trong bộ nhớ: sắp xếp sau khi đã cắt trang không tạo ra thứ tự đúng trên toàn bộ tập kết quả.

### 4.2. Đọc nội dung và metadata

```java
List<Customer> content = page.getContent();

int pageIndex = page.getNumber();
int requestedSize = page.getSize();
int returnedSize = page.getNumberOfElements();

long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();

boolean nextPageExists = page.hasNext();
boolean firstPage = page.isFirst();
```

Đoạn mã cần import `java.util.List`.

Phải phân biệt ba con số:

| Giá trị | Ý nghĩa |
| --- | --- |
| `getSize()` | Kích thước trang được yêu cầu |
| `getNumberOfElements()` | Số phần tử thực tế trong trang hiện tại |
| `getTotalElements()` | Tổng số phần tử thỏa điều kiện theo kết quả phân trang được trả về |

Ví dụ, yêu cầu kích thước 20 nhưng trang cuối chỉ có 7 phần tử thì `getSize()` vẫn là 20, còn `getNumberOfElements()` là 7.

Một trang không có nội dung chưa đủ để kết luận toàn bộ truy vấn không có kết quả. Người dùng có thể đã yêu cầu trang vượt ra ngoài tập kết quả.

### 4.3. Page có thể cần thêm công việc để tính tổng

Để cung cấp `totalElements` và `totalPages`, implementation có thể phải thực hiện truy vấn đếm ngoài truy vấn lấy nội dung. Một số trường hợp có thể suy ra tổng hoặc tối ưu việc đếm; không nên khẳng định mọi lần gọi luôn phát ra đúng hai truy vấn.

Ngay cả khi trang chỉ chứa ít phần tử, việc đếm trên một tập dữ liệu lớn vẫn có thể tốn kém. Cần quan sát truy vấn thực tế và đặc tính của kho dữ liệu.

`Page` mở rộng `Slice`, nhưng gán kết quả sang biến `Slice` không thay đổi cách repository đã thực thi:

```java
Slice<Customer> slice =
    customerRepository.findAll(example, pageable);
```

Đoạn mã cần import `org.springframework.data.domain.Slice`. Lời gọi gốc vẫn là phương thức trả về `Page`; việc đổi kiểu biến nhận không tự loại bỏ công việc tính tổng.

Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, hãy chọn một API thực sự hỗ trợ `Slice`, giới hạn kết quả hoặc cuộn dữ liệu trong module và phiên bản mục tiêu. Không mặc định rằng mọi biến thể QBE đều có sẵn những phương thức đó.

## 5. Minh họa trên một tập dữ liệu

Giả sử dữ liệu như sau:

| id | displayName | country |
| --- | --- | --- |
| 101 | An | VN |
| 102 | An | VN |
| 103 | Binh | VN |
| 104 | Chi | TH |
| 105 | Dung | VN |

Với điều kiện quốc gia VN, thứ tự tên tăng dần rồi ID tăng dần, và kích thước trang 2:

| Chỉ số trang | ID trong trang | Tổng phần tử | Tổng trang |
| --- | --- | --- | --- |
| 0 | 101, 102 | 4 | 2 |
| 1 | 103, 105 | 4 | 2 |
| 2 | Không có | 4 | 2 |

Bảng giả định dữ liệu không thay đổi giữa các lần đọc và kho sắp xếp các tên trong ví dụ theo thứ tự đã nêu.

Hai bản ghi tên An được phân định bằng ID. Bản ghi 104 bị loại bởi điều kiện QBE trước khi phân trang; nó không được tính vào tổng kết quả phù hợp.

## 6. Projection qua fluent query

### 6.1. Projection mô tả hình dạng phần tử trả về

Giả sử màn hình danh sách chỉ cần ID, tên và email:

```java
public interface CustomerSummary {
    Long getId();
    String getDisplayName();
    String getEmail();
}
```

Đây là ví dụ projection interface đóng: các accessor tương ứng với thuộc tính của domain. Nó khác với yêu cầu tìm kiếm; projection không làm thay đổi điều kiện quốc gia trong `example`.

Với phiên bản Commons và module hỗ trợ fluent QBE projection, có thể yêu cầu kiểu kết quả bằng `as(...)`:

```java
List<CustomerSummary> summaries =
    customerRepository.findBy(
        example,
        query -> query
            .as(CustomerSummary.class)
            .sortBy(sort)
            .all()
    );
```

Đoạn mã cần import `java.util.List`. Các bước có ý nghĩa:

1. `example` cung cấp điều kiện lọc.
2. `as(CustomerSummary.class)` yêu cầu biểu diễn phần tử theo projection.
3. `sortBy(sort)` cung cấp thứ tự.
4. `all()` thực thi để lấy toàn bộ kết quả phù hợp dưới dạng danh sách.

`all()` ở đây không tự áp dụng phân trang. Nếu số bản ghi phù hợp lớn, cần dùng biến thể có giới hạn phù hợp thay vì tải hết chỉ vì mỗi phần tử có ít thuộc tính.

### 6.2. Projection kết hợp phân trang

Có thể yêu cầu trang projection trong cùng callback nếu implementation hỗ trợ:

```java
Pageable pageable = PageRequest.of(0, 20, sort);

Page<CustomerSummary> summaryPage =
    customerRepository.findBy(
        example,
        query -> query
            .as(CustomerSummary.class)
            .page(pageable)
    );
```

Đặt thứ tự trong `Pageable` giúp yêu cầu phân trang được trình bày đầy đủ tại một chỗ. Tránh đồng thời truyền các thứ tự khác nhau qua `sortBy` và `Pageable` nếu chưa xác định quy tắc kết hợp của API và implementation đang dùng.

Metadata trang vẫn nói về tập kết quả thỏa `example`. Việc đổi từ `Customer` sang `CustomerSummary` không có nghĩa tổng số phần tử được tính theo số thuộc tính projection.

Fluent query phải được sử dụng và kết thúc trong callback. Hãy trả về kết quả như danh sách hoặc trang; không giữ hay trả lại đối tượng `query` để tiếp tục thực thi sau callback.

### 6.3. as và project có vai trò khác nhau

Trong fluent API, hai thao tác thường dễ bị nhầm:

| Thao tác | Vai trò |
| --- | --- |
| `as(ResultType.class)` | Yêu cầu kiểu biểu diễn kết quả |
| `project("propertyA", "propertyB")` | Yêu cầu tập thuộc tính cần đưa vào quá trình truy vấn kết quả |

Ví dụ minh họa khi module hỗ trợ cả hai:

```java
List<CustomerSummary> summaries =
    customerRepository.findBy(
        example,
        query -> query
            .as(CustomerSummary.class)
            .project("id", "displayName", "email")
            .sortBy(sort)
            .all()
    );
```

Các chuỗi trong `project` là tên thuộc tính domain. Chúng không phải alias tùy ý do client gửi vào. Trong ví dụ, các thuộc tính getter của projection và các khóa sắp xếp đều nằm trong tập thuộc tính được yêu cầu.

`project(...)` không tự tạo một DTO Java mới và không tự đổi kiểu trả về. Ngược lại, chỉ dùng `as(...)` cũng chưa đủ để khẳng định kho dữ liệu chỉ đọc đúng ba cột hoặc ba field. Cách chọn dữ liệu, tạo proxy, dựng DTO và tối ưu truy vấn thuộc implementation.

Nếu bỏ qua một thuộc tính mà projection cần, kết quả có thể không như mong đợi. Không dựa vào giả định rằng mọi module sẽ tự bổ sung mọi thuộc tính còn thiếu.

### 6.4. Các loại projection không có mức hỗ trợ đồng nhất

Projection interface đóng, projection mở có biểu thức, DTO theo constructor và projection lồng nhau có thể được hỗ trợ khác nhau.

Ví dụ `CustomerSummary` là một yêu cầu cụ thể cần xác minh, không phải bảo đảm rằng mọi kiểu đích đều dùng được chỉ bằng cách thay đối số của `as`. Một số module hoặc phiên bản có thể từ chối một dạng projection bằng lỗi không hỗ trợ.

Projection cũng không mặc nhiên loại bỏ việc tải entity, không tự giải quyết mọi vấn đề tải quan hệ và không chứng minh dữ liệu nhạy cảm chưa từng được đọc từ kho. Muốn khẳng định hiệu quả truy vấn, phải quan sát dữ liệu và truy vấn thực tế của module.

## 7. Phương án thay thế: lấy Page rồi chuyển sang DTO

Nếu repository hỗ trợ QBE phân trang nhưng không hỗ trợ kiểu projection mong muốn, có thể lấy entity rồi chuyển nội dung trang sang DTO:

```java
public record CustomerSummaryDto(
    Long id,
    String displayName,
    String email
) {}
```

Ví dụ dùng Java 17 trở lên; DTO class thông thường cũng có thể thay thế record.

```java
Page<Customer> entityPage =
    customerRepository.findAll(example, pageable);

Page<CustomerSummaryDto> responsePage =
    entityPage.map(customer -> new CustomerSummaryDto(
        customer.getId(),
        customer.getDisplayName(),
        customer.getEmail()
    ));
```

`Page.map` chuyển từng phần tử trong trang và giữ metadata phân trang tương ứng. Nó không chạy lại truy vấn QBE và không tự thực hiện projection tại kho dữ liệu.

So sánh hai cách:

| Tiêu chí | Fluent projection được module hỗ trợ | Lấy entity rồi dùng Page.map |
| --- | --- | --- |
| Kiểu kết quả mong muốn | Được yêu cầu trong fluent query | Được tạo từ phần tử đã trả về |
| Phụ thuộc hỗ trợ projection của module | Có | Không cần hỗ trợ projection trong truy vấn |
| Khả năng giảm thuộc tính đọc từ kho | Có thể có, phải xác minh | Không phát sinh chỉ nhờ map |
| Metadata trang | Do truy vấn phân trang cung cấp | Được giữ khi chuyển phần tử |
| Công việc chuyển đổi | Implementation xử lý kiểu projection | Mã ứng dụng tạo DTO |

Phương án `Page.map` tạo được hợp đồng phản hồi rõ ràng, nhưng không phải bằng chứng rằng truy vấn đã nhẹ hơn. Nếu việc giảm dữ liệu đọc là yêu cầu chính, cần xem xét truy vấn chuyên biệt hoặc cơ chế projection phù hợp của module.

## 8. Xác định đúng phạm vi hỗ trợ

Trước khi dùng một khả năng trong mã sản phẩm, cần phân biệt ba lớp:

1. **Hợp đồng Commons:** tên phương thức, kiểu đầu vào và kiểu trả về mà phiên bản dự án cung cấp.
2. **Implementation của module:** khả năng module thực thi QBE, sắp xếp, phân trang và từng loại projection.
3. **Đặc tính kho dữ liệu:** collation, index, chi phí đếm, giới hạn sắp xếp và hành vi khi dữ liệu thay đổi.

Bảng dưới đây dùng để chọn hướng triển khai, không thay thế tài liệu của module:

| Nhu cầu | Điểm bắt đầu ở Commons | Điều cần xác minh ở module |
| --- | --- | --- |
| Lấy kết quả QBE có thứ tự | `findAll(example, sort)` | Đường dẫn sắp xếp và quy tắc so sánh được hỗ trợ |
| Lấy trang có metadata tổng | `findAll(example, pageable)` | Thực thi phân trang, đếm và chi phí thực tế |
| Lấy projection có thứ tự | `findBy` với `as`, `sortBy`, `all` | Kiểu projection được hỗ trợ |
| Lấy trang projection | `findBy` với `as`, `page` | Kết hợp projection và phân trang có thực thi được không |
| Hạn chế tập thuộc tính | Fluent `project` | Thuộc tính có thực sự được giới hạn trong truy vấn hay không |
| Chỉ cần biết còn dữ liệu | API Slice, giới hạn hoặc cuộn phù hợp | Có biến thể phù hợp trong phiên bản và module hay không |

Các ví dụ fluent sử dụng những phương thức phải có trong phiên bản Spring Data mà dự án đang dùng. Không nên thêm một lời gọi chỉ vì một tài liệu của phiên bản khác có phương thức đó.

Nếu một khả năng không được hỗ trợ:

- Chọn `Page.map` nếu nhu cầu chính là hình dạng dữ liệu phản hồi.
- Dùng repository fragment hoặc truy vấn chuyên biệt của module khi cần kiểm soát rõ truy vấn và tập thuộc tính được đọc.
- Chọn cơ chế phân trang hoặc cuộn thích hợp nếu offset lớn hay truy vấn đếm không đáp ứng yêu cầu.

Không bắt mọi lỗi truy vấn rồi âm thầm bỏ projection hoặc phân trang. Lỗi mapping, lỗi kết nối và lỗi cú pháp không đồng nghĩa với thiếu hỗ trợ; phương án thay thế cần được chọn rõ ràng.

## 9. Từ yêu cầu giao diện đến một truy vấn nhất quán

Một API danh sách khách hàng có thể nhận:

```text
country=VN
page=0
size=20
sort=name,asc
```

Tên sắp xếp công khai `name` không bắt buộc trùng tên thuộc tính Java. Ứng dụng nên ánh xạ qua danh sách được cho phép:

```text
name  -> displayName
email -> email
```

Sau đó, tạo thứ tự có khóa duy nhất ở cuối và xây dựng truy vấn:

```java
Sort sort = Sort.by(
    Sort.Order.asc("displayName"),
    Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);

Page<Customer> entityPage =
    customerRepository.findAll(example, pageable);
```

Trong ứng dụng thực tế:

- Chuẩn hóa và xác thực dữ liệu đầu vào trước khi tạo probe.
- Chỉ cho phép các thuộc tính sắp xếp và thuộc tính phản hồi mà API chủ động hỗ trợ.
- Dùng cùng điều kiện và cùng quy tắc sắp xếp cho các lần yêu cầu trang liên tiếp.
- Xem xét index dựa trên mẫu lọc, sắp xếp và kho dữ liệu cụ thể.
- Áp dụng các điều kiện quyền truy cập và phạm vi dữ liệu bắt buộc ở cơ chế thích hợp; projection không thay thế các điều kiện này.

Nếu client muốn trang hiển thị bắt đầu từ 1, hãy chuyển đổi rõ ràng tại biên API sang chỉ số bắt đầu từ 0 của `PageRequest`. Không trộn hai quy ước trong cùng hợp đồng.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đặt page và size, bỏ Sort | Thứ tự giữa các trang có thể không ổn định | Đặt thứ tự rõ ràng, thêm khóa duy nhất |
| Sắp xếp danh sách sau khi lấy một trang | Chỉ thứ tự trong trang được sửa | Đưa Sort vào yêu cầu truy vấn |
| Dùng tên cột lưu trữ trong Sort | Có thể không phân giải được thuộc tính | Dùng tên thuộc tính domain |
| Gán Page sang Slice để tránh đếm | Cách thực thi không thay đổi | Chọn API thực sự phù hợp |
| Gọi fluent all rồi tự cắt trang | Tải toàn bộ tập kết quả trước khi cắt | Dùng truy vấn phân trang được hỗ trợ |
| Cho rằng as luôn giảm số cột đọc | Đánh giá sai chi phí truy vấn | Xác minh implementation và truy vấn thực tế |
| Cho rằng Page.map thực hiện projection tại kho | Entity đã được truy vấn trước khi map | Phân biệt chuyển đổi ứng dụng với projection trong truy vấn |
| Đổi kiểu projection tùy ý giữa các module | Có thể lỗi lúc chạy | Chốt loại projection được module hỗ trợ |
| Cho rằng Sort theo ID tạo snapshot | Vẫn có thể dịch trang khi dữ liệu đổi | Chọn cơ chế nhất quán hoặc cuộn phù hợp với nghiệp vụ |

## 11. Bài tập tự kiểm tra

1. Vì sao `Sort.by("displayName")` chưa đủ để phân định thứ tự giữa hai khách hàng cùng tên?
2. Với kích thước trang 20, `PageRequest.of(1, 20, sort)` chỉ trang nào và tương ứng offset bao nhiêu?
3. Kết quả có `getSize() == 20` nhưng `getNumberOfElements() == 7` có mâu thuẫn không?
4. Nếu `findAll(example, pageable)` trả về `Page`, đổi biến nhận sang `Slice` có bảo đảm không đếm tổng không?
5. Khi dùng `as(CustomerSummary.class)`, có thể kết luận kho dữ liệu chỉ đọc ba thuộc tính không?
6. Khi module không hỗ trợ projection DTO trong QBE nhưng hỗ trợ phân trang entity, có thể trả về trang DTO bằng cách nào?

Gợi ý đáp án:

1. Hai bản ghi có cùng khóa sắp xếp; cần thêm tiêu chí phân định, chẳng hạn ID duy nhất.
2. Trang thứ hai, với offset 20 trong mô hình offset.
3. Không. Một giá trị là kích thước yêu cầu, giá trị còn lại là số phần tử thực tế.
4. Không. Kiểu biến không thay đổi phương thức đã được gọi.
5. Không. Cần xác minh khả năng chọn thuộc tính và cách thực thi của module.
6. Truy vấn `Page<Customer>` rồi dùng `Page.map` để tạo DTO, đồng thời hiểu rằng đây là chuyển đổi sau khi đọc.

Khi áp dụng QBE, hãy diễn đạt tách bạch điều kiện, thứ tự, trang và hình dạng kết quả. Sau đó chọn đúng phần API mà module lưu trữ hỗ trợ, đồng thời đánh giá chi phí bằng hành vi truy vấn thực tế.
