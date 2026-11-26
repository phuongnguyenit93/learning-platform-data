# page, slice, scroll và stream theo phiên bản hỗ trợ

Fluent query cho phép giữ cùng một điều kiện tìm kiếm nhưng chọn cách nhận kết quả phù hợp: một trang có tổng số phần tử, một lát cắt chỉ cần biết còn dữ liệu hay không, một cửa sổ tiếp nối bằng vị trí hoặc một luồng cần được đóng sau khi sử dụng.

Bài học thuộc chương **Fluent query** của **SPRING_DATA_COMMONS**. Trọng tâm là cách dùng các abstraction dùng chung này qua repository, đồng thời nhận biết giới hạn theo phiên bản Spring Data và khả năng của từng module lưu trữ.

Không nên chọn kiểu kết quả chỉ vì API có tên quen thuộc. Mỗi lựa chọn kéo theo hợp đồng khác nhau về tổng số phần tử, điều hướng, thứ tự, chi phí truy vấn và vòng đời tài nguyên.

Sau bài học, bạn có thể:

- Phân biệt `Page<T>`, `Slice<T>`, `Window<T>` và `Stream<T>`.
- Dùng các terminal operation tương ứng trong fluent query khi phiên bản hỗ trợ.
- Duyệt scroll đúng vị trí, phân biệt offset với keyset.
- Tiêu thụ và đóng stream trong phạm vi tài nguyên hợp lệ.
- Chọn cách đọc kết quả theo nhu cầu giao diện hoặc xử lý dữ liệu lớn.

## 1. Đặt fluent query trong ngữ cảnh repository

Bài dùng Query by Example làm nguồn điều kiện. Giả sử `Customer` là kiểu miền được store ánh xạ hợp lệ, có các thuộc tính:

| Thuộc tính | Kiểu Java | Vai trò |
|---|---|---|
| `id` | `Long` | Khóa định danh duy nhất |
| `displayName` | `String` | Tên hiển thị |
| `active` | `Boolean` | Bộ lọc trạng thái |
| `createdAt` | `Instant` | Khóa sắp xếp không null trong ví dụ scroll |

Các đoạn mã giả định lớp có getter/setter và constructor không tự thêm các giá trị lọc ngoài ý muốn.

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setActive(Boolean.TRUE);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreNullValues()
    .withIgnorePaths("id", "displayName", "createdAt");

Example<Customer> example = Example.of(probe, matcher);
~~~

Ví dụ chọn khách hàng đang hoạt động. Với ứng dụng dùng Spring Data JPA, repository có thể là:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

`Customer` phải là entity JPA hợp lệ. Với store khác, chọn repository và ánh xạ tương ứng; không chỉ thay tên dependency rồi giả định toàn bộ hành vi giữ nguyên.

Dạng gọi chung là:

~~~java
repository.findBy(example, query -> /* cấu hình rồi lấy kết quả */);
~~~

Đối với API QBE đồng bộ, callback làm việc với `FluentQuery.FetchableFluentQuery`. Nó mô tả cách lấy kết quả cho lần thực thi đó. Đừng trả chính đối tượng fluent query ra ngoài callback để lưu lại và thực thi về sau.

Bài này không dùng API reactive. `Stream<T>` của Java không có cùng hợp đồng với `Flux<T>` và không tự có cơ chế backpressure của Reactive Streams.

## 2. Bốn kiểu kết quả trả lời bốn câu hỏi khác nhau

| Kiểu | Câu hỏi chính | Có tổng số phần tử? | Cách đi tiếp |
|---|---|---|---|
| `Page<T>` | Trang này là gì trong toàn bộ tập kết quả? | Có | `Pageable` của trang kế tiếp hoặc số trang |
| `Slice<T>` | Lấy một phần kết quả; còn phần sau không? | Không yêu cầu tổng số | `nextPageable()` |
| `Window<T>` | Lấy một cửa sổ từ một vị trí tiếp nối | Không | `ScrollPosition` lấy từ phần tử trong cửa sổ |
| `Stream<T>` | Tiêu thụ lần lượt kết quả trong một phạm vi xử lý | Không | Duyệt luồng đến khi kết thúc hoặc dừng |

`Page` kế thừa `Slice`, nhưng việc gán một `Page` vào biến kiểu `Slice` không loại bỏ truy vấn đếm đã được thực hiện.

`Window` là kết quả của scrolling, không phải một số trang được đổi tên. `Stream` là một đối tượng cần quản lý vòng đời, không phải danh sách có thể giữ lại tùy ý.

## 3. Kiểm tra hỗ trợ theo phiên bản ở đúng lớp

Không có một kết luận chung kiểu “Spring Data hỗ trợ phân trang nên mọi fluent query đều có đủ page, slice, scroll và stream”.

Cần phân biệt ba mức:

1. **API đang biên dịch:** `FetchableFluentQuery` của phiên bản dependency có phương thức cần gọi không?
2. **Implementation của module:** module store có triển khai phương thức và tối ưu tương ứng không?
3. **Khả năng thực thi:** loại truy vấn, ánh xạ, driver và store có đáp ứng cách đọc đó không?

Các API `page(Pageable)` và `stream()` có trong các dòng fluent query sớm hơn; `scroll(ScrollPosition)`, khả năng `limit(int)` và terminal operation `slice(Pageable)` cần được kiểm tra riêng ở phiên bản đang dùng. Việc `Slice` hoặc `Window` tồn tại trong dependency không chứng minh callback fluent query của phiên bản đó có terminal operation tương ứng.

Bảng kiểm tra khi áp dụng:

| Muốn dùng | Chữ ký cần xác nhận trong fluent API | Hỗ trợ cần xác nhận thêm |
|---|---|---|
| Page | `page(Pageable)` | Truy vấn dữ liệu, cách tính tổng |
| Slice | `slice(Pageable)` | Cách triển khai có tránh count hay chỉ ủy quyền sang page |
| Scroll | `scroll(ScrollPosition)` | Loại vị trí được hỗ trợ và cách tạo cửa sổ |
| Giới hạn cửa sổ | `limit(int)` | Implementation có áp dụng giới hạn ở store không |
| Stream | `stream()` | Cách đọc, tài nguyên và cấu hình driver |

Khi đối chiếu phiên bản, xem mục `Since` của **đúng artifact đang dùng**, rồi kiểm tra khả năng của module cùng dòng phiên bản. Đừng dùng Javadoc của một dòng mới để khẳng định mã sẽ biên dịch trên một dòng cũ.

Các ví dụ `slice`, `scroll` và `limit` trong bài chỉ áp dụng khi đủ các điều kiện này. Nếu phương thức chưa tồn tại, hãy chọn API repository được phiên bản đó hỗ trợ hoặc nâng cấp đồng bộ các dependency Spring Data. Tránh chép riêng một interface mới vào dự án cũ để “bổ sung” phương thức.

## 4. page: khi cần tổng số phần tử và tổng số trang

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest request = PageRequest.of(
    0,
    20,
    Sort.by("createdAt").ascending()
        .and(Sort.by("id").ascending())
);

Page<Customer> page = repository.findBy(
    example,
    query -> query.page(request)
);
~~~

Trong ví dụ:

- Số trang bắt đầu từ `0`.
- Kích thước trang là `20`.
- `createdAt` xác định thứ tự chính, `id` phân biệt các bản ghi trùng thời điểm.
- Kết quả có nội dung trang và thông tin về toàn bộ tập kết quả.

~~~java
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

### 4.1. Chi phí của tổng số phần tử

Để cung cấp tổng số, implementation có thể phải thực hiện thêm truy vấn đếm. Một số trường hợp có thể suy ra tổng từ nội dung trả về và bỏ qua count. Vì vậy, không khẳng định rằng mọi lời gọi `page` luôn chạy đúng hai câu truy vấn.

Tuy nhiên, nếu giao diện cần hiển thị “1.234 kết quả, 62 trang”, chi phí tính tổng là một phần của yêu cầu. Hãy đánh giá chi phí đó với điều kiện lọc và chỉ mục thực tế.

### 4.2. Trang sâu và dữ liệu đang thay đổi

Phân trang theo offset có thể phải bỏ qua nhiều bản ghi trước khi trả trang ở xa. Chỉ giảm kích thước trang không giải quyết hoàn toàn chi phí offset sâu.

Nếu dữ liệu được thêm hoặc xóa giữa hai lần lấy trang, vị trí các bản ghi có thể thay đổi. Một thứ tự có khóa duy nhất giúp xác định thứ tự trên tập dữ liệu cố định, nhưng không tạo snapshot xuyên suốt nhiều request.

### 4.3. Đặt sort rõ ràng trong Pageable

Khi dùng `page` hoặc `slice`, các ví dụ đặt thứ tự ngay trong `Pageable`. Nếu đồng thời dùng `sortBy(...)`, hãy kiểm tra quy tắc kết hợp hoặc ưu tiên của phiên bản API; không tự giả định hai nguồn sort sẽ được nối theo ý muốn.

## 5. slice: khi chỉ cần biết còn kết quả hay không

Nếu phiên bản và module hỗ trợ terminal operation tương ứng:

~~~java
import org.springframework.data.domain.Slice;

Slice<Customer> slice = repository.findBy(
    example,
    query -> query.slice(request)
);

boolean hasNext = slice.hasNext();
~~~

`Slice` cung cấp nội dung và khả năng điều hướng, nhưng không có hợp đồng cung cấp `getTotalElements()` hoặc `getTotalPages()`.

Nó phù hợp với nút “Tải thêm”, danh sách có “Trang sau”, hoặc luồng giao diện không cần biết toàn bộ có bao nhiêu bản ghi.

### 5.1. Không suy ra tối ưu chỉ từ kiểu trả về

Một implementation chuyên biệt có thể đọc tối đa `pageSize + 1` bản ghi để xác định `hasNext`, rồi chỉ trả tối đa `pageSize` phần tử.

Đó là một chiến lược phổ biến, không phải bằng chứng rằng mọi lời gọi trả `Slice` đều tránh count. Một phương thức mặc định hoặc adapter có thể triển khai slice bằng cách dùng page.

Ví dụ sau vẫn tạo page trước:

~~~java
Slice<Customer> result = repository.findBy(
    example,
    query -> query.page(request)
);
~~~

Kiểu biến `Slice<Customer>` không thay đổi cách truy vấn đã thực thi. Nếu mục tiêu là tránh count, cần dùng terminal operation và implementation phù hợp, rồi xác nhận bằng hành vi truy vấn thực tế.

### 5.2. Lấy lát cắt kế tiếp

~~~java
if (slice.hasNext()) {
    Slice<Customer> next = repository.findBy(
        example,
        query -> query.slice(slice.nextPageable())
    );

    // Dùng next.getContent() cho lượt tải tiếp theo.
}
~~~

Ví dụ giả định `slice` ban đầu không bị gán lại trong phạm vi lambda. Nếu viết vòng lặp cập nhật biến slice, cần tạo biến cục bộ effectively final cho `Pageable` trước mỗi callback.

Slice vẫn có thể sử dụng offset. Vì vậy, nó giải quyết nhu cầu không cần tổng số, nhưng không mặc nhiên loại bỏ mọi hạn chế của offset sâu.

## 6. scroll: đọc theo từng cửa sổ và vị trí tiếp nối

Khi API hỗ trợ, `scroll` trả về `Window<T>`. Mỗi cửa sổ chứa một nhóm kết quả và cho phép lấy vị trí tiếp nối từ phần tử đã đọc.

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.Window;

Sort order = Sort.by("createdAt").ascending()
    .and(Sort.by("id").ascending());

Window<Customer> window = repository.findBy(
    example,
    query -> query
        .sortBy(order)
        .limit(100)
        .scroll(ScrollPosition.offset())
);
~~~

Ở đây `limit(100)` mô tả kích thước tối đa mong muốn cho một cửa sổ trong implementation hỗ trợ cách dùng này. Nó không phải số thứ tự trang và không giới hạn tổng số phần tử của toàn bộ vòng duyệt.

Một implementation có thể đọc thêm dữ liệu để xác định `hasNext`. Không suy ra số hàng store đã đọc chỉ từ `window.size()`.

### 6.1. Vị trí là điểm tiếp tục, không phải số trang

Điểm quan trọng của scrolling là **vị trí được loại trừ**: lần tiếp theo bắt đầu sau vị trí đã cung cấp.

Để bắt đầu từ trước phần tử đầu tiên với offset scrolling, dùng:

~~~java
ScrollPosition initial = ScrollPosition.offset();
~~~

Không thay tùy tiện bằng:

~~~java
ScrollPosition afterOffsetZero = ScrollPosition.offset(0L);
~~~

Hai giá trị không cùng nghĩa. `offset()` là vị trí ban đầu; `offset(0L)` biểu diễn vị trí của phần tử tại offset 0 và lượt đọc tiếp bắt đầu sau vị trí đó. Dùng giá trị thứ hai như điểm khởi đầu có thể bỏ qua phần tử đầu tiên.

### 6.2. Lấy vị trí sau phần tử cuối cùng đã xử lý

~~~java
if (!window.isEmpty() && window.hasNext()) {
    ScrollPosition nextPosition =
        window.positionAt(window.size() - 1);

    Window<Customer> next = repository.findBy(
        example,
        query -> query
            .sortBy(order)
            .limit(100)
            .scroll(nextPosition)
    );
}
~~~

`positionAt(...)` nhận chỉ số phần tử trong cửa sổ. Không gọi `positionAt(window.size())`, vì chỉ số đó nằm ngoài danh sách.

Không tự cộng một kích thước batch vào vị trí nếu API đã cung cấp vị trí từ kết quả. Cách tính đó vừa dễ lệch một phần tử, vừa không phù hợp với keyset.

## 7. Offset scrolling và keyset scrolling

### 7.1. Offset scrolling

Offset scrolling tiếp tục theo số phần tử đã đi qua. Nó dễ hiểu nhưng store vẫn có thể phải xử lý phần dữ liệu đứng trước vị trí cần đọc.

~~~java
ScrollPosition position = ScrollPosition.offset();
~~~

Ưu điểm là mô hình vị trí đơn giản. Hạn chế là chi phí có thể tăng khi đi sâu, và việc thêm/xóa dữ liệu trước vị trí hiện tại có thể làm thay đổi phần tử được gặp ở lượt sau.

Một `Window` sử dụng offset không tự có đặc tính hiệu năng của keyset chỉ vì tên API là scroll.

### 7.2. Keyset scrolling

Keyset scrolling tiếp tục dựa trên giá trị các khóa sắp xếp của phần tử trước đó.

~~~java
Window<Customer> firstWindow = repository.findBy(
    example,
    query -> query
        .sortBy(order)
        .limit(100)
        .scroll(ScrollPosition.keyset())
);
~~~

Với thứ tự:

~~~text
createdAt ASC, id ASC
~~~

ý tưởng tiếp tục theo hướng tiến có thể hình dung là:

~~~text
createdAt > lastCreatedAt
OR
(createdAt = lastCreatedAt AND id > lastId)
~~~

Đây là mô tả ý tưởng với hai khóa tăng dần, không phải câu truy vấn được bảo đảm sinh ra. Sort giảm dần, sort hỗn hợp và cách store xử lý từng kiểu dữ liệu cần cách diễn giải tương ứng.

Keyset có thể giúp tránh phải bỏ qua toàn bộ các hàng trước offset, khi store và chỉ mục phù hợp. Nó không phải cam kết rằng mọi truy vấn keyset đều nhanh bất kể điều kiện lọc.

### 7.3. Điều kiện để dùng keyset đáng tin cậy

Cần chú ý:

- **Thứ tự xác định:** có khóa phân biệt các bản ghi trùng giá trị sort chính. Ví dụ dùng `id` sau `createdAt`.
- **Giá trị sort không null:** keyset cần so sánh các giá trị khóa; trường nullable có thể không được hỗ trợ hoặc không cho hành vi mong muốn.
- **Khả năng lấy khóa:** các thuộc tính cần tạo vị trí phải có sẵn trong kết quả theo yêu cầu của implementation.
- **Chỉ mục phù hợp:** đánh giá đồng thời điều kiện lọc và chuỗi khóa sắp xếp.
- **Khóa ít thay đổi:** nếu khóa sort bị sửa trong khi duyệt, bản ghi có thể di chuyển qua ranh giới đã đọc.
- **Store hỗ trợ loại vị trí:** có `scroll` không đồng nghĩa mọi module hỗ trợ cả offset và keyset.

Một số implementation bổ sung định danh vào thứ tự keyset. Dù vậy, khai báo rõ thứ tự nghiệp vụ và khóa phân biệt trong mã giúp hợp đồng dễ hiểu hơn.

Không dùng một trường nullable như `displayName` làm khóa keyset mà chưa có chính sách dữ liệu và hỗ trợ store phù hợp.

## 8. Vòng lặp scroll đúng và dễ kiểm tra

Đoạn mã sau minh họa đọc khách hàng đang hoạt động theo batch. Nó giả định phiên bản và store hỗ trợ `sortBy`, `limit` và keyset scrolling.

~~~java
import java.util.function.Consumer;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.Window;

public void visitCustomers(
        Example<Customer> example,
        Consumer<Customer> consumer) {

    Sort order = Sort.by("createdAt").ascending()
        .and(Sort.by("id").ascending());

    ScrollPosition position = ScrollPosition.keyset();

    while (true) {
        // Lambda cần biến cục bộ không bị gán lại.
        ScrollPosition currentPosition = position;

        Window<Customer> window = repository.findBy(
            example,
            query -> query
                .sortBy(order)
                .limit(100)
                .scroll(currentPosition)
        );

        if (window.isEmpty()) {
            break;
        }

        for (Customer customer : window) {
            consumer.accept(customer);
        }

        if (!window.hasNext()) {
            break;
        }

        position = window.positionAt(window.size() - 1);
    }
}
~~~

Có bốn quyết định quan trọng trong vòng lặp:

1. Mọi lượt dùng cùng bộ lọc và cùng thứ tự.
2. Xử lý cửa sổ trước khi chuyển vị trí.
3. Không lấy vị trí từ cửa sổ rỗng.
4. Chỉ cập nhật vị trí khi còn lượt tiếp theo.

Nếu mỗi vòng lại dùng `ScrollPosition.keyset()`, truy vấn sẽ bắt đầu lại thay vì tiếp tục, có thể tạo vòng lặp đọc lặp dữ liệu.

Nếu cần offset scrolling, điểm bắt đầu có thể đổi thành `ScrollPosition.offset()` khi implementation hỗ trợ; phần tiếp tục vẫn nên dùng vị trí lấy từ cửa sổ.

### 8.1. Scroll không tự cung cấp snapshot

Giữ cùng thứ tự không đóng băng tập dữ liệu. Trong lúc duyệt, dữ liệu có thể được tạo, xóa hoặc sửa.

Ví dụ, nếu `createdAt` thực tế được cho phép sửa, một bản ghi có thể di chuyển sang phía trước hoặc phía sau vị trí đã đọc. Offset cũng chịu tác động khi số phần tử phía trước thay đổi.

Với tác vụ yêu cầu một tập dữ liệu xác định, cần thiết kế thêm chính sách nhất quán: mốc chặn thời gian, tập định danh cố định, snapshot hoặc giao dịch phù hợp với store và quy mô tác vụ. Một mốc thời gian đơn lẻ cũng không giải quyết mọi trường hợp sửa dữ liệu; nó phải phù hợp với cách dữ liệu được cập nhật.

### 8.2. Checkpoint phải đi cùng kết quả xử lý

Nếu dùng scroll cho xử lý nền và lưu checkpoint:

- Lưu sau khi đã xử lý thành công phần dữ liệu tương ứng.
- Khi khởi động lại, dùng cùng bộ lọc và cùng thứ tự.
- Thiết kế xử lý lặp an toàn nếu có thể xảy ra lỗi giữa việc xử lý và ghi checkpoint.

Scroll chỉ cung cấp cơ chế điều hướng. Nó không tạo cam kết “mỗi bản ghi được xử lý đúng một lần” cho các tác động bên ngoài.

### 8.3. Vị trí nội bộ không phải hợp đồng token công khai sẵn có

Không coi `ScrollPosition.toString()` là định dạng token API ổn định.

Nếu giao diện cần truyền continuation token giữa nhiều request, ứng dụng phải xác định cách mã hóa vị trí, hướng duyệt, bộ lọc, thứ tự và phiên bản token. Khi người dùng thay bộ lọc hoặc thứ tự, vị trí cũ có thể không còn ý nghĩa.

## 9. Projection và khóa sắp xếp khi scroll

Fluent query có thể chọn kiểu kết quả bằng `as(...)` nếu module hỗ trợ projection tương ứng.

Ví dụ projection có đủ các trường cần thiết:

~~~java
import java.time.Instant;

public interface CustomerRow {
    Long getId();
    String getDisplayName();
    Instant getCreatedAt();
}
~~~

~~~java
Window<CustomerRow> rows = repository.findBy(
    example,
    query -> query
        .sortBy(order)
        .limit(100)
        .as(CustomerRow.class)
        .scroll(ScrollPosition.keyset())
);
~~~

Ví dụ giả định implementation hỗ trợ kết hợp interface projection với keyset scroll và ánh xạ được các thuộc tính trên.

Nếu bỏ `createdAt` hoặc `id` khỏi kết quả, module có thể không tạo được vị trí tiếp nối tùy cách triển khai. Vì vậy, tối ưu projection phải đi cùng yêu cầu tạo keyset; không chỉ giữ các trường nhìn thấy trên giao diện.

Projection cũng không tự chứng minh rằng store chỉ đọc đúng những cột hoặc trường được khai báo. Hãy kiểm tra cách module ánh xạ và thực thi.

## 10. stream: tiêu thụ trong phạm vi tài nguyên hợp lệ

Khi terminal operation được hỗ trợ:

~~~java
import java.util.stream.Stream;

try (Stream<Customer> rows = repository.findBy(
        example,
        query -> query.sortBy(order).stream())) {

    rows.forEachOrdered(this::handleCustomer);
}
~~~

`Stream` có thể được gắn với tài nguyên store như cursor hoặc kết quả truy vấn đang mở. Vì vậy, dùng try-with-resources là cách thể hiện rõ trách nhiệm đóng luồng, kể cả khi có ngoại lệ.

Các ví dụ giả định `handleCustomer` là hàm xử lý của ứng dụng. Không giữ tham chiếu tới stream để dùng sau khi khối try đã kết thúc.

### 10.1. Giao dịch phải bao trùm lúc tiêu thụ, khi store yêu cầu

Với một ứng dụng JPA có truy vấn stream dựa trên tài nguyên persistence, cách đặt phạm vi thường là:

~~~java
import java.util.function.Consumer;
import java.util.stream.Stream;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.Sort;
import org.springframework.transaction.annotation.Transactional;

@Transactional(readOnly = true)
public void processActiveCustomers(Consumer<Customer> sink) {
    Customer probe = new Customer();
    probe.setActive(Boolean.TRUE);

    Example<Customer> example = Example.of(
        probe,
        ExampleMatcher.matchingAll()
            .withIgnoreNullValues()
            .withIgnorePaths("id", "displayName", "createdAt")
    );

    Sort order = Sort.by("createdAt").ascending()
        .and(Sort.by("id").ascending());

    try (Stream<Customer> rows = repository.findBy(
            example,
            query -> query.sortBy(order).stream())) {

        rows.forEachOrdered(sink);
    }
}
~~~

Đoạn mã nằm trong một Spring bean và cần được gọi theo cơ chế áp dụng giao dịch của ứng dụng, thường qua Spring proxy. Chỉ thêm annotation rồi tự gọi nội bộ không phải lúc nào cũng mở được giao dịch mới.

Phạm vi giao dịch trong ví dụ bao trùm cả việc tạo stream và tiêu thụ nó. Nếu hàm chỉ trả stream ra ngoài rồi kết thúc giao dịch, caller có thể duyệt khi tài nguyên cần thiết đã đóng.

Yêu cầu cụ thể khác nhau theo module. Với store khác JPA, cần xác định cách mở/đóng cursor và phạm vi đọc tương ứng thay vì sao chép mọi cấu hình giao dịch.

### 10.2. Trả Stream ra ngoài cần một hợp đồng vòng đời rõ ràng

Một phương thức trả `Stream<Customer>` có thể là thiết kế hợp lệ nếu caller biết rõ:

- Ai giữ phạm vi tài nguyên hoặc giao dịch cần thiết?
- Ai tiêu thụ dữ liệu?
- Ai đóng stream khi hoàn tất, dừng sớm hoặc gặp lỗi?

Nếu các câu trả lời không rõ, xử lý bên trong service thường dễ kiểm soát hơn.

Không trả stream vào response JSON và kỳ vọng framework tự duy trì cursor, giao dịch và xử lý lỗi theo đúng ý ứng dụng.

### 10.3. Stream không đồng nghĩa bộ nhớ hằng số

API Java trả stream không tự bảo đảm store hoặc driver gửi dữ liệu từng phần nhỏ.

Hành vi phụ thuộc:

- Driver và cấu hình fetch size.
- Implementation của module.
- Cách store cung cấp kết quả.
- Việc entity có được giữ trong persistence context không.
- Các thao tác tiếp theo trên stream.

Ví dụ:

~~~java
List<Customer> allRows = rows.collect(Collectors.toList());
~~~

lại tập hợp toàn bộ dữ liệu vào bộ nhớ ứng dụng. Một số thao tác như `sorted()` trên Java Stream cũng có thể cần giữ nhiều phần tử trước khi trả kết quả.

Nếu mục tiêu là giảm bộ nhớ, hãy chọn đúng adapter, projection và cách tiêu thụ. Với entity được quản lý trong JPA, cần đánh giá cả persistence context; đóng stream không biến toàn bộ quá trình thành đọc thuần không giữ trạng thái.

### 10.4. Giới hạn ở query khác giới hạn ở Java Stream

Hai biểu thức sau không có cùng cam kết thực thi:

~~~java
query.limit(100).stream()
~~~

~~~java
query.stream().limit(100)
~~~

Biểu thức thứ nhất yêu cầu giới hạn ở fluent query, khi API và implementation hỗ trợ. Biểu thức thứ hai giới hạn số phần tử được Java Stream chuyển tới bước sau; nó không chứng minh truy vấn gốc đã mang giới hạn tại store.

Dù dừng sớm bằng `limit`, `findFirst` hoặc một thao tác khác, stream vẫn cần được đóng. Terminal operation không tự thay thế trách nhiệm gọi `close()` trên stream tài nguyên.

### 10.5. Không tự biến stream store thành xử lý song song

Gọi `parallel()` không biến driver hoặc persistence context thành tài nguyên an toàn cho nhiều luồng.

Nếu cần xử lý song song, hãy thiết kế ranh giới tách dữ liệu và tác vụ rõ ràng, chẳng hạn đọc từng batch thành dữ liệu độc lập rồi giao cho cơ chế xử lý phù hợp. Đừng chia sẻ một stream gắn với phiên truy cập store và các entity đang được quản lý giữa các luồng một cách mặc định.

## 11. Chọn phương án theo nhu cầu

| Nhu cầu | Lựa chọn thường phù hợp | Điều cần xác nhận |
|---|---|---|
| Bảng quản trị hiển thị tổng số và số trang | `page` | Chi phí count, thứ tự và offset sâu |
| Nút “Tải thêm”, không cần tổng số | `slice` | Terminal operation có trong phiên bản, implementation tránh count nếu đó là mục tiêu |
| Xử lý nhiều batch và cần tiếp tục từ vị trí | `scroll` | Hỗ trợ loại vị trí, khóa sort, checkpoint và dữ liệu thay đổi |
| Đọc tuần tự trong một phạm vi xử lý | `stream` | Cursor, giao dịch, đóng tài nguyên, driver và bộ nhớ |
| Chỉ cần một số lượng nhỏ tối đa | `limit` kết hợp terminal phù hợp | API và implementation hỗ trợ giới hạn tại store |
| Cần tiêu thụ bất đồng bộ có backpressure | API reactive phù hợp | Module reactive và hợp đồng đọc tương ứng |

Những cặp lựa chọn dễ nhầm:

- **Slice và keyset scroll:** cùng không cần tổng số, nhưng slice có thể vẫn dùng offset; keyset dùng giá trị khóa để tiếp tục.
- **Scroll và stream:** scroll thường trả từng cửa sổ có vị trí; stream cung cấp luồng tiêu thụ với vòng đời tài nguyên cần kiểm soát.
- **Page và slice:** page có thêm tổng số; đổi kiểu biến không làm mất chi phí tính tổng.
- **Stream và danh sách:** stream có thể lười và giữ tài nguyên; danh sách thường đã có toàn bộ nội dung trong bộ nhớ.

## 12. Khi phiên bản chưa hỗ trợ một terminal operation

### 12.1. Chưa có slice trong callback fluent query

Có thể chọn API repository khác mà phiên bản và module hỗ trợ trả `Slice`, nếu nó diễn đạt đúng điều kiện cần tìm.

Dùng `page` rồi xem nó như `Slice` chỉ là một cách dùng kiểu kết quả. Không coi đó là cách đảm bảo bỏ count.

Nếu tự thiết kế truy vấn đọc thêm một phần tử, phải xử lý đúng giới hạn, offset, thứ tự và `hasNext`. Đây là một truy vấn riêng cần được duy trì, không phải thao tác đổi kiểu đơn giản.

### 12.2. Chưa có scroll hoặc không hỗ trợ keyset

Có thể dùng phân trang hoặc batch theo API được module hỗ trợ. Nhưng cần chấp nhận và đo đặc tính của cách đọc đó, đặc biệt ở offset sâu.

Nếu yêu cầu là keyset, phải triển khai hoặc sử dụng truy vấn có điều kiện tiếp nối theo khóa. Không truyền số trang vào một token rồi gọi đó là keyset.

### 12.3. Có Stream nhưng implementation không đọc dần như mong muốn

Nếu driver hoặc adapter vẫn tải lượng dữ liệu quá lớn, cân nhắc:

- Cấu hình đọc phù hợp với driver.
- Giảm kích thước dữ liệu qua projection được hỗ trợ.
- Đọc theo các cửa sổ hoặc batch có giới hạn rõ.
- Đổi cơ chế truy vấn nếu API hiện tại không cung cấp cách tiêu thụ cần thiết.

Không khẳng định giải pháp đúng chỉ từ việc kiểu trả về là `Stream`.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
|---|---|---|
| Không biên dịch được `slice(...)` | Phiên bản fluent API chưa có phương thức | Kiểm tra artifact và chọn API tương thích |
| Có phương thức nhưng thực thi báo không hỗ trợ | Module hoặc loại truy vấn chưa triển khai khả năng đó | Xác nhận hỗ trợ ở store, chọn cơ chế khác |
| Dùng slice nhưng vẫn thấy count | Implementation ủy quyền sang page hoặc đang gọi page | Kiểm tra terminal operation và truy vấn thực tế |
| Scroll bỏ qua phần tử đầu | Dùng `offset(0)` như vị trí ban đầu | Dùng `ScrollPosition.offset()` để bắt đầu |
| Scroll đọc lặp batch đầu | Khởi tạo lại vị trí mỗi vòng | Lấy vị trí từ cửa sổ vừa xử lý |
| Lỗi chỉ số khi lấy vị trí | Dùng `positionAt(size())` hoặc cửa sổ rỗng | Kiểm tra rỗng và dùng chỉ số hợp lệ |
| Keyset không tiếp tục được | Thiếu khóa sort trong kết quả hoặc khóa null | Rà soát dữ liệu, projection và hỗ trợ module |
| Kết quả giữa các lượt bị lặp hoặc thiếu | Sort không xác định hoặc dữ liệu thay đổi | Thêm khóa phân biệt, thiết kế chính sách nhất quán |
| Stream báo tài nguyên đã đóng | Tiêu thụ ngoài phạm vi phiên/giao dịch cần thiết | Bao trùm lúc tiêu thụ bằng phạm vi phù hợp |
| Dùng stream nhưng vẫn nhiều bộ nhớ | Driver tải nhiều, context giữ entity hoặc collect toàn bộ | Kiểm tra toàn bộ đường đọc và cách tiêu thụ |
| Dừng đọc sớm nhưng tài nguyên còn giữ | Chưa đóng stream | Dùng try-with-resources |
| Export chậm dù mỗi batch nhỏ | Count, offset sâu, thiếu chỉ mục hoặc xử lý từng bản ghi tốn kém | Đo truy vấn và phần xử lý riêng |

## 14. Bài thực hành

### 14.1. Chuẩn bị dữ liệu có ranh giới rõ

Tạo 7 khách hàng có `id` duy nhất và `createdAt` không null. Trong đó có 5 khách hàng đang hoạt động. Đặt ít nhất hai người có cùng `createdAt` để kiểm tra vai trò của khóa `id`.

Dùng cùng một `Example` chọn `active = true` và cùng thứ tự:

~~~text
createdAt ASC, id ASC
~~~

Kích thước mỗi lần đọc là `2`.

### 14.2. Kiểm tra page

- Đọc trang đầu và xác nhận tối đa 2 phần tử.
- Xác nhận tổng số phần tử là 5 trên tập dữ liệu cố định.
- Xác nhận số trang là 3.
- Quan sát truy vấn dữ liệu và việc count có thực sự được gọi không.

Không viết kỳ vọng “luôn có hai câu truy vấn” nếu implementation có tối ưu bỏ count trong một số trường hợp.

### 14.3. Kiểm tra slice khi được hỗ trợ

- Đọc lần lượt các lát cắt với kích thước 2.
- Kỳ vọng nội dung có số phần tử lần lượt là 2, 2 và 1.
- Kỳ vọng `hasNext` lần lượt là true, true và false.
- Quan sát implementation có thực hiện count hay không.

### 14.4. Kiểm tra offset và keyset scroll

- Với offset, bắt đầu bằng `ScrollPosition.offset()`.
- Với keyset, bắt đầu bằng `ScrollPosition.keyset()`, nếu store hỗ trợ.
- Tiếp tục bằng vị trí phần tử cuối cửa sổ vừa xử lý.
- Trên tập dữ liệu không thay đổi, xác nhận cả 5 định danh được gặp, không lặp và không thiếu.
- Chạy một tình huống sai có chủ đích với `offset(0)` để quan sát khác biệt so với vị trí ban đầu.
- Nếu dùng projection, thử kiểm tra yêu cầu về các khóa tạo vị trí.

### 14.5. Kiểm tra stream

- Tiêu thụ 5 kết quả trong khối try-with-resources.
- Thử dừng sớm sau 2 phần tử và xác nhận tài nguyên vẫn được đóng.
- Thử một lỗi từ hàm xử lý để kiểm tra luồng đóng tài nguyên.
- Với store yêu cầu phạm vi giao dịch khi đọc, xác nhận phạm vi đó bao trùm cả lúc tiêu thụ.

### 14.6. Ghi lại khả năng của môi trường đang dùng

| Khả năng | Phiên bản API có phương thức? | Module thực thi được? | Hành vi quan sát |
|---|---|---|---|
| `page` | Có/Không | Có/Không | Nội dung, tổng số, count |
| `slice` | Có/Không | Có/Không | `hasNext`, có/không count |
| Offset scroll | Có/Không | Có/Không | Vị trí đầu và vị trí tiếp theo |
| Keyset scroll | Có/Không | Có/Không | Khóa sort và truy vấn tiếp nối |
| `stream` | Có/Không | Có/Không | Phạm vi đọc, đóng tài nguyên, bộ nhớ |

Lựa chọn đúng bắt đầu từ câu hỏi mà ứng dụng cần trả lời: cần tổng số thì dùng page; chỉ cần biết còn phần sau thì cân nhắc slice; cần các batch có vị trí tiếp nối thì đánh giá scroll; cần tiêu thụ trong một phạm vi tài nguyên thì xem xét stream. Sau đó mới đối chiếu phiên bản, implementation và store để bảo đảm cách đọc thực tế đáp ứng yêu cầu.
