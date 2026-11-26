# findById, Optional và kết quả không tồn tại

## Mục tiêu bài học

Khi tìm một đối tượng theo định danh, ứng dụng không thể mặc định rằng đối tượng luôn tồn tại. Một ID đúng kiểu có thể chưa từng được sử dụng, đối tượng có thể đã bị xóa, hoặc thao tác đọc có thể thất bại vì một nguyên nhân hạ tầng.

Spring Data Commons diễn đạt trường hợp có hoặc không có đối tượng bằng hợp đồng `findById` trả về `Optional`. Hiểu đúng hợp đồng này giúp ứng dụng phân biệt một kết quả vắng mặt bình thường với lỗi truy cập dữ liệu, đồng thời chọn cách xử lý phù hợp cho từng nghiệp vụ.

Bài học thuộc chương **Hợp đồng CRUD** của module SPRING_DATA_COMMONS. Sau bài học, bạn có thể:

- Đọc đúng chữ ký và điều kiện đầu vào của `findById`.
- Xử lý `Optional` mà không dựa vào một giá trị `null` hoặc gọi `get()` tùy tiện.
- Chọn giữa giữ kết quả tùy chọn, chuyển đổi dữ liệu, cung cấp giá trị mặc định và ném exception nghiệp vụ.
- Tránh biến lỗi kết nối hoặc lỗi truy vấn thành thông báo “không tìm thấy”.
- Nhận diện những giới hạn về thời điểm đọc, transaction và cơ chế JPA.

## 1. Hợp đồng findById trong Commons

Một phần hợp đồng của `CrudRepository<T, ID>` có dạng:

~~~java
Optional<T> findById(ID id);
~~~

Với repository:

~~~java
public interface BookRepository
        extends CrudRepository<Book, Long> {
}
~~~

method có thể được hiểu ở phía bên gọi là:

~~~java
Optional<Book> findById(Long id);
~~~

Hai tham số kiểu của repository xác định kiểu dữ liệu cần tìm và kiểu định danh được chấp nhận.

Hợp đồng quan trọng gồm:

| Thành phần | Ý nghĩa |
| --- | --- |
| Đầu vào `id` | Định danh của đối tượng, không được là null. |
| Có đối tượng | Trả về một Optional chứa đối tượng tương ứng. |
| Không có đối tượng | Trả về Optional.empty(). |
| Đầu vào null | Vi phạm hợp đồng; method có thể ném IllegalArgumentException theo hợp đồng CRUD. |
| Lỗi khi truy cập hoặc xử lý dữ liệu | Có thể phát sinh exception, không được biểu diễn bằng Optional.empty() một cách mặc định. |

Với implementation tuân thủ hợp đồng, chính đối tượng `Optional` trả về không được là `null`.

`ListCrudRepository` kế thừa hợp đồng tìm theo ID này; chữ “List” không làm `findById` trả về một danh sách. Kết quả vẫn là `Optional<T>`.

`Optional` ở đây là kiểu của Java, được Commons dùng trong hợp đồng repository đồng bộ. Nó không phải một loại entity và không phải một trạng thái được lưu vào kho dữ liệu.

## 2. Ba kết quả cần phân biệt

~~~mermaid
flowchart TD
    A["Gọi findById với ID hợp lệ"] --> B{"Thao tác đọc có hoàn tất bình thường?"}
    B -->|"Không"| C["Exception: xử lý lỗi theo nguyên nhân"]
    B -->|"Có"| D{"Có đối tượng phù hợp?"}
    D -->|"Có"| E["Optional chứa entity"]
    D -->|"Không"| F["Optional.empty"]
~~~

### 2.1. Tìm thấy

~~~java
Optional<Book> result = repository.findById(bookId);
~~~

Nếu có đối tượng, `result.isPresent()` là `true`. Bên gọi có thể lấy hoặc chuyển đổi đối tượng theo mục tiêu sử dụng.

Có entity trong Optional không có nghĩa mọi quan hệ liên quan đã được tải, dữ liệu là bất biến hoặc entity sẽ tiếp tục tồn tại mãi sau thời điểm đọc.

### 2.2. Không tìm thấy

Nếu không có đối tượng tương ứng trong ngữ cảnh đọc, repository trả `Optional.empty()`.

Đây có thể là một kết quả nghiệp vụ bình thường:

- Người dùng mở một đường dẫn tới đối tượng đã bị xóa.
- Một tác vụ đồng bộ tìm một đối tượng chưa tồn tại ở hệ thống đích.
- Một bước xử lý chỉ thực hiện khi dữ liệu đã có sẵn.

Không có đối tượng không tự động là exception ở cấp repository. Bên gọi quyết định sự vắng mặt đó có vi phạm yêu cầu của nghiệp vụ hay không.

### 2.3. Thao tác đọc thất bại

Nếu không kết nối được kho dữ liệu, mapping có vấn đề hoặc truy vấn thất bại, không thể kết luận rằng đối tượng không tồn tại.

Những lỗi này có thể được module biểu diễn qua hệ exception truy cập dữ liệu của Spring hoặc các exception liên quan. Loại exception cụ thể phụ thuộc nguyên nhân, cấu hình và công nghệ lưu trữ.

> Optional.empty() diễn đạt một lần đọc hoàn tất nhưng không tìm thấy đối tượng theo hợp đồng. Nó không phải mã chung cho mọi thất bại trong quá trình đọc.

## 3. Đầu vào hợp lệ chưa bảo đảm có dữ liệu

### 3.1. ID không được null

Không dùng:

~~~java
repository.findById(null);
~~~

để biểu diễn yêu cầu “không có ID”. Đây là đầu vào không hợp lệ, khác với việc truyền một ID không tồn tại.

Tầng service có thể chủ động kiểm tra:

~~~java
private static void requireId(Long id) {
    if (id == null) {
        throw new IllegalArgumentException("ID không được null");
    }
}
~~~

Kiểm tra này làm điều kiện đầu vào rõ ràng tại biên service. Nó không thay thế toàn bộ kiểm tra hoặc ràng buộc của repository.

Không tự áp dụng quy tắc “mọi ID phải lớn hơn 0” cho mọi repository. Kiểu và miền giá trị của ID do domain, mapping và cơ chế lưu trữ quyết định; một module khác có thể sử dụng UUID, chuỗi hoặc kiểu định danh tổng hợp.

### 3.2. Sai định dạng khác với không tồn tại

Với repository nhận `Long`, chuỗi đầu vào chưa chuyển được thành `Long` là lỗi chuyển đổi hoặc kiểm tra đầu vào ở một tầng trước đó.

Ngược lại, một giá trị `Long` đúng kiểu nhưng không có đối tượng tương ứng dẫn tới kết quả không tìm thấy khi thao tác đọc hoàn tất bình thường.

Hai tình huống này cần được phân loại riêng trong ứng dụng. Không chuyển mọi lỗi phân tích ID thành một Optional rỗng rồi coi như đã truy vấn dữ liệu.

### 3.3. Không cần tự tạo một entity để tìm theo ID

Một đối tượng ID là đủ:

~~~java
Optional<Book> result = repository.findById(bookId);
~~~

Không cần tạo một entity rỗng, gán ID rồi gọi `save` để xem dữ liệu có tồn tại hay không. `save` là thao tác ghi và có hành vi khác với thao tác tìm.

## 4. Ví dụ repository và mô hình dữ liệu

Phần thực hành dùng Spring Data JPA để minh họa hợp đồng Commons. Giả định ứng dụng đã có datasource, mapping và cấu hình repository phù hợp. Ví dụ DTO dùng Java có hỗ trợ record.

### 4.1. Domain Book

File `domain/Book.java`:

~~~java
package com.example.library.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "library_book")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private boolean active;

    protected Book() {
    }

    public Book(String title, boolean active) {
        this.title = title;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Các annotation ở đây thuộc JPA, không phải yêu cầu mapping chung của Commons. Thuộc tính `active` được dùng ở ví dụ lọc kết quả bên dưới; nó không tự tạo một cơ chế soft delete.

### 4.2. Repository

File `repository/BookRepository.java`:

~~~java
package com.example.library.repository;

import com.example.library.domain.Book;
import org.springframework.data.repository.CrudRepository;

public interface BookRepository
        extends CrudRepository<Book, Long> {
}
~~~

Không cần khai báo lại `findById` vì repository đã kế thừa method đó.

Trong ứng dụng này, Commons cung cấp hợp đồng, còn Spring Data JPA cung cấp cơ chế thực thi trên JPA. Việc chỉ thêm Commons mà không có module lưu trữ và cấu hình tương ứng chưa đủ để tạo repository truy cập cơ sở dữ liệu.

### 4.3. DTO cho kết quả đọc

File `BookView.java`:

~~~java
package com.example.library;

import com.example.library.domain.Book;

public record BookView(Long id, String title) {

    public static BookView from(Book book) {
        return new BookView(book.getId(), book.getTitle());
    }
}
~~~

DTO chỉ lấy những thuộc tính đơn giản dùng trong ví dụ. Optional có thể chuyển đổi entity sang DTO mà vẫn giữ ý nghĩa có hoặc không có kết quả.

## 5. Ba cách xử lý hợp lý ở tầng service

### 5.1. Giữ kết quả tùy chọn cho bên gọi

Nếu bên gọi có quyền quyết định cách xử lý khi không có sách, service có thể tiếp tục trả Optional.

### 5.2. Yêu cầu phải có đối tượng

Nếu nghiệp vụ chỉ có thể tiếp tục khi sách tồn tại, service có thể chuyển Optional rỗng thành exception có ý nghĩa.

File `BookNotFoundException.java`:

~~~java
package com.example.library;

public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(Long id) {
        super("Không tìm thấy sách: " + id);
    }
}
~~~

Exception này không tự quyết định giao thức trả lời cho HTTP, dòng lệnh hoặc một tác vụ nền. Tầng tiếp nhận exception sẽ ánh xạ theo ngữ cảnh ứng dụng.

### 5.3. Service minh họa

File `BookLookupService.java`:

~~~java
package com.example.library;

import com.example.library.domain.Book;
import com.example.library.repository.BookRepository;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class BookLookupService {

    private final BookRepository repository;

    public BookLookupService(BookRepository repository) {
        this.repository = repository;
    }

    public Optional<BookView> findView(Long id) {
        requireId(id);

        return repository.findById(id)
            .map(BookView::from);
    }

    public BookView requireView(Long id) {
        requireId(id);

        Book book = repository.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));

        return BookView.from(book);
    }

    public Optional<BookView> findActiveView(Long id) {
        requireId(id);

        return repository.findById(id)
            .filter(Book::isActive)
            .map(BookView::from);
    }

    private static void requireId(Long id) {
        if (id == null) {
            throw new IllegalArgumentException(
                "ID không được null"
            );
        }
    }
}
~~~

Ba method thể hiện ba hợp đồng nghiệp vụ khác nhau:

| Method | Khi có sách phù hợp | Khi không có kết quả phù hợp |
| --- | --- | --- |
| `findView` | Trả Optional chứa DTO. | Trả Optional rỗng. |
| `requireView` | Trả DTO trực tiếp. | Ném BookNotFoundException. |
| `findActiveView` | Trả DTO nếu sách đang active. | Trả Optional rỗng nếu không có sách hoặc sách không active. |

Trong cả ba trường hợp, lỗi truy cập dữ liệu không bị service này chuyển thành “không tìm thấy”.

### Optional rỗng có thể do một bước xử lý sau truy vấn

Ở `findActiveView`, Optional rỗng không còn mang duy nhất ý nghĩa “repository không tìm thấy ID”. Nó cũng có thể do `filter` loại một sách tồn tại nhưng không active.

Vì vậy, cần đọc hợp đồng của chính method service, không áp nghĩa của `findById` trực tiếp lên mọi chuỗi xử lý Optional.

Nếu nghiệp vụ cần phân biệt “không tồn tại” với “đã ngừng hoạt động”, hãy đọc đối tượng rồi phân loại rõ hai tình huống. Nếu muốn gộp chúng, việc trả kết quả rỗng phải là quyết định có chủ đích.

## 6. Dùng các thao tác Optional đúng mục đích

### 6.1. map để chuyển đổi kết quả có mặt

~~~java
Optional<BookView> view = repository.findById(bookId)
    .map(BookView::from);
~~~

Nếu có entity, hàm chuyển đổi được gọi. Nếu Optional ban đầu rỗng, kết quả vẫn rỗng và hàm chuyển đổi không được gọi.

Không cần viết một nhánh `if` rồi tự tạo `Optional.of(...)` chỉ để chuyển đổi kiểu kết quả.

Một chi tiết cần nhớ: nếu hàm được truyền vào `map` trả `null`, Optional kết quả sẽ rỗng. Nếu việc chuyển đổi bắt buộc phải thành công khi có entity, tránh để hàm chuyển đổi âm thầm trả null làm mất dấu nguyên nhân.

### 6.2. orElseThrow khi nghiệp vụ yêu cầu tồn tại

~~~java
Book book = repository.findById(bookId)
    .orElseThrow(() -> new BookNotFoundException(bookId));
~~~

Supplier tạo exception được gọi khi Optional rỗng. Dùng exception theo ý nghĩa nghiệp vụ giúp bên gọi hiểu tình huống rõ hơn một lỗi `NoSuchElementException` chung chung.

Việc ném exception ở đây là quyết định của service, không phải bằng chứng rằng repository đã gặp lỗi truy vấn.

### 6.3. orElse và orElseGet có thời điểm tính fallback khác nhau

So sánh:

~~~java
Book value = result.orElse(loadFallbackBook());
~~~

với:

~~~java
Book value = result.orElseGet(() -> loadFallbackBook());
~~~

`result` là Optional đã có, còn `loadFallbackBook` đại diện cho hàm cung cấp giá trị dự phòng trong ứng dụng.

Ở cách thứ nhất, biểu thức đối số được tính trước khi gọi `orElse`, kể cả khi Optional đang có entity. Ở cách thứ hai, supplier chỉ được gọi khi Optional rỗng.

Nếu fallback chỉ là một giá trị đơn giản đã có sẵn, khác biệt thường không đáng kể. Nếu fallback truy vấn dữ liệu, ghi log nghiệp vụ hoặc tạo đối tượng có tác động phụ, sự khác biệt có thể quan sát được.

Không tự dùng fallback để tạo rồi lưu một entity mới nếu nghiệp vụ chỉ yêu cầu đọc. Việc “không tìm thấy thì tạo” là một nghiệp vụ ghi riêng, cần quyết định về định danh, ràng buộc duy nhất và cạnh tranh đồng thời.

### 6.4. ifPresent khi chỉ cần thực hiện nhánh có dữ liệu

~~~java
repository.findById(bookId)
    .ifPresent(book ->
        System.out.println(book.getTitle())
    );
~~~

Cách này phù hợp khi không có dữ liệu thì không cần thực hiện hành động. Nó không phù hợp nếu bên gọi bắt buộc phải nhận được một kết quả hoặc một thông báo vắng mặt rõ ràng.

### 6.5. Tránh get không có chính sách xử lý vắng mặt

~~~java
Book book = repository.findById(bookId).get();
~~~

Nếu không tìm thấy, lời gọi này ném `NoSuchElementException`. Lỗi đó không giải thích rõ yêu cầu nghiệp vụ nào đã bị vi phạm.

Thường có thể dùng `map`, `orElseThrow` hoặc xử lý nhánh rỗng rõ ràng. Không cần gọi `isPresent()` rồi `get()` ở mọi nơi chỉ vì đó là cách làm quen thuộc đầu tiên.

## 7. Những mẫu xử lý làm sai ý nghĩa hợp đồng

### 7.1. Bắt mọi exception rồi trả Optional rỗng

Đây là một mẫu không phù hợp:

~~~java
public Optional<Book> find(Long id) {
    try {
        return repository.findById(id);
    } catch (Exception exception) {
        return Optional.empty();
    }
}
~~~

Mẫu này làm các tình huống khác nhau trở nên không thể phân biệt:

- Không có sách.
- Cơ sở dữ liệu không truy cập được.
- ID null.
- Mapping hoặc cấu hình có vấn đề.

Nếu tầng API dựa vào Optional rỗng để trả thông báo “không tìm thấy”, một lần mất kết nối có thể bị báo sai thành dữ liệu không tồn tại.

Chỉ chuyển đổi exception khi ứng dụng có lý do và quy tắc rõ ràng. Nếu cần đóng gói lỗi hạ tầng thành một exception khác, vẫn phải giữ ý nghĩa lỗi và nguyên nhân liên quan.

### 7.2. Trả null thay cho Optional

Không viết một wrapper trả `null` trong nhánh vắng mặt khi chữ ký đã là `Optional<Book>`. Bên gọi sẽ phải kiểm tra cả null lẫn Optional rỗng, làm mất lợi ích của hợp đồng.

Tương tự, khi tự viết implementation hoặc stub:

- `Optional.of(value)` yêu cầu value không-null.
- `Optional.ofNullable(value)` chuyển một giá trị có thể null sang Optional.
- `Optional.empty()` biểu diễn vắng mặt trực tiếp.

Không cần bọc kết quả `repository.findById(id)` bằng `Optional.ofNullable`. Repository đã trả một Optional; bọc thêm sẽ tạo cấu trúc lồng không cần thiết và có thể che một implementation vi phạm hợp đồng.

### 7.3. Chuyển về null quá sớm

~~~java
Book book = repository.findById(bookId).orElse(null);
~~~

Cách này có thể cần khi tích hợp một API cũ yêu cầu null, nhưng nếu dùng khắp service thì ứng dụng lại phải quản lý các nhánh null mà hợp đồng Optional đã diễn đạt rõ.

Nên giữ ý nghĩa có/không có kết quả đến đúng tầng quyết định hành vi.

### 7.4. So sánh Optional bằng danh tính đối tượng

Không dùng:

~~~java
result == Optional.empty()
~~~

để kiểm tra vắng mặt. Hãy dùng `isEmpty()` hoặc `isPresent()`.

Mục tiêu là kiểm tra trạng thái kết quả, không phải danh tính của một đối tượng Optional cụ thể.

## 8. Có cần gọi existsById trước findById không?

Một mẫu thường gặp:

~~~java
if (!repository.existsById(bookId)) {
    return Optional.empty();
}

return repository.findById(bookId);
~~~

Nếu mục tiêu cuối cùng là lấy entity, `findById` đã biểu diễn được cả hai kết quả có và không có. Kiểm tra tồn tại trước thường tạo thêm một lời gọi repository mà không loại bỏ nhu cầu xử lý Optional.

Hơn nữa, kết quả tồn tại có thể thay đổi giữa hai lời gọi:

~~~text
T1: existsById trả true
T2: một thao tác khác xóa đối tượng
T3: findById trả Optional.empty
~~~

Kiểm tra trước không phải một cơ chế khóa hay một bảo đảm entity vẫn còn tồn tại lúc đọc.

Phân biệt hai nhu cầu:

| Nhu cầu | Hợp đồng trực tiếp |
| --- | --- |
| Chỉ cần biết có tồn tại hay không. | `existsById`. |
| Cần nội dung entity nếu tồn tại. | `findById` và xử lý Optional. |

Cách truy cập dữ liệu và số câu lệnh thực tế phụ thuộc module, cache và transaction. Không cần khẳng định mỗi lời gọi luôn tương ứng đúng một câu SQL để nhận ra mẫu kiểm tra trước có thể thừa.

## 9. findById là method tìm theo định danh, không chỉ là một tên query bất kỳ

Trong Spring Data, các method CRUD được dành sẵn như `findById` hướng tới thuộc tính định danh của domain.

Giả sử một domain JPA có cấu trúc minh họa:

~~~java
@Entity
class Customer {

    @Id
    private Long pk;

    private Long id;
}
~~~

Ở đây:

- `pk` là định danh JPA.
- `id` chỉ là một thuộc tính thông thường có tên id.

Với repository CRUD quản lý `Customer` có ID kiểu `Long`, method kế thừa `findById` hướng tới định danh `pk`, không tự chuyển sang trường thông thường `id` chỉ vì trùng tên.

Nếu muốn derived query tìm theo thuộc tính thông thường tên `id`, có thể dùng một tên có phần mô tả để tránh đụng method dành sẵn, chẳng hạn:

~~~java
Optional<Customer> findCustomerById(Long id);
~~~

Ví dụ này cần domain và module hỗ trợ truy vấn tương ứng. Nếu thuộc tính thông thường không duy nhất nhưng method trả một kết quả tùy chọn duy nhất, nhiều kết quả khớp có thể dẫn đến lỗi kích thước kết quả, không phải Optional rỗng.

Điểm cần nhớ là phải phân biệt **định danh của domain** với **tên thuộc tính trong một derived query**. Điều này giúp tránh đọc nhầm dữ liệu khi domain có cách đặt tên đặc biệt.

## 10. Giới hạn của kết luận “đã tìm thấy” hoặc “không tìm thấy”

### 10.1. Kết quả gắn với ngữ cảnh đọc

Kết quả tìm theo ID phụ thuộc nguồn dữ liệu, transaction và các quy tắc truy cập mà ứng dụng thực sự sử dụng.

Một số ứng dụng có tenant, filter hoặc cơ chế loại trừ dữ liệu đã xóa mềm. Khi những cơ chế đó được áp dụng, một ID có thể không có kết quả trong ngữ cảnh hiện tại dù dữ liệu vật lý vẫn còn ở nơi khác hoặc ở một phạm vi khác.

Commons không tự kích hoạt những cơ chế này. Điều cần tránh là nâng kết quả một lần đọc thành khẳng định tuyệt đối về toàn bộ dữ liệu ở mọi ngữ cảnh.

### 10.2. Tìm thấy rồi không có nghĩa thao tác tiếp theo luôn thành công

Sau khi `findById` trả entity, một tiến trình khác có thể cập nhật hoặc xóa dữ liệu trước thao tác tiếp theo.

Nếu nghiệp vụ cần phát hiện xung đột cập nhật hoặc bảo vệ một chuỗi thao tác, cần đánh giá transaction, optimistic locking hoặc cơ chế khóa phù hợp với module. Optional không mang vai trò khóa dữ liệu.

Chỉ thêm một annotation transaction cũng không tạo cùng một bảo đảm nhất quán cho mọi mức isolation, mọi module và mọi kho dữ liệu.

### 10.3. JPA có thể trả entity từ persistence context

Với JPA, tìm theo ID có thể trả một entity đã được quản lý trong persistence context. Không nên mặc định mọi lời gọi `findById` đều phát sinh một câu SELECT mới.

Nếu đang kiểm chứng tác động từ bên ngoài hoặc hành vi đọc lại, phải hiểu ranh giới persistence context và transaction đang có. Nhìn thấy cùng một giá trị trong hai lần gọi chưa đủ để kết luận đã thực hiện hai vòng đọc độc lập từ cơ sở dữ liệu.

### 10.4. Có entity không có nghĩa mọi quan hệ đã được tải

Optional chứa một entity không làm toàn bộ đồ thị quan hệ của entity trở thành dữ liệu đã khởi tạo.

Trong ví dụ, DTO chỉ dùng ID và tiêu đề đơn giản. Nếu mapping DTO cần truy cập quan hệ lazy trong JPA, cần thiết kế nơi chuyển đổi và chiến lược tải dữ liệu phù hợp. Optional không tự giải quyết vấn đề tải quan hệ ngoài persistence context.

## 11. Phân biệt với getReferenceById và truy vấn nhiều ID

### 11.1. getReferenceById là API chuyên biệt của JPA

`JpaRepository.getReferenceById` có thể trả một reference và trì hoãn việc kiểm tra hay tải dữ liệu đến lúc reference được sử dụng. Chi tiết có thể phụ thuộc provider và ngữ cảnh.

API này không trả Optional và không thay thế `findById` khi mục tiêu là nhận ngay một kết quả có/không có theo hợp đồng đang học. Việc có một reference chưa tự chứng minh entity thực sự tồn tại; lỗi liên quan đến entity không tồn tại có thể xuất hiện khi reference được truy cập.

Đây là khác biệt ở cấp module JPA. Không áp tên hoặc hành vi này lên mọi repository của Commons.

### 11.2. findAllById không trả một Optional cho mỗi ID

Nếu cần đọc nhiều đối tượng, `findAllById` là một hợp đồng khác. Các ID không tìm thấy có thể không tạo phần tử trong tập kết quả; không nên kỳ vọng một danh sách Optional có cùng số lượng và vị trí như đầu vào.

Thứ tự kết quả cũng không được mặc định trùng thứ tự danh sách ID đầu vào. Nếu nghiệp vụ cần chỉ rõ ID nào bị thiếu, phải đối chiếu kết quả theo định danh.

Việc `findById` biểu diễn rõ một kết quả tùy chọn không có nghĩa mọi API tìm kiếm khác đều có cùng hình dạng trả về.

## 12. Chọn chính sách vắng mặt theo nghiệp vụ

| Ngữ cảnh | Cách xử lý có thể phù hợp |
| --- | --- |
| Tra cứu tùy chọn trong một bước xử lý. | Giữ Optional để bên gọi quyết định. |
| Mở một tài nguyên bắt buộc tồn tại theo ID. | Service dùng exception rõ nghĩa; tầng HTTP có thể ánh xạ thành 404 nếu đó là hợp đồng API. |
| Chỉ thực hiện hành động khi có dữ liệu. | Dùng ifPresent hoặc nhánh xử lý tương đương. |
| Hiển thị một giá trị đơn giản khi thiếu dữ liệu. | map rồi cung cấp fallback có ý nghĩa. |
| Phân biệt không tồn tại với không đủ điều kiện nghiệp vụ. | Đọc và phân loại rõ, tránh gộp bằng filter nếu cần hai trạng thái riêng. |
| Lỗi kết nối hoặc mapping. | Giữ và phân loại lỗi hệ thống theo nguyên nhân; không chuyển thành vắng mặt. |

Commons không tự trả mã HTTP, tạo thông báo giao diện hoặc quyết định tiếp tục hay dừng một tác vụ nền. Những quyết định đó thuộc hợp đồng ứng dụng xây dựng trên kết quả repository.

Nếu chọn hành vi mặc định khi thiếu dữ liệu, hãy xác định đó là một giá trị trình bày hay một hành động tạo dữ liệu mới. Hai việc có tác động rất khác nhau.

## 13. Các tình huống tự kiểm chứng

Khi thực hành trong một ứng dụng đã cấu hình, có thể đối chiếu các trường hợp sau:

| Tình huống | Điều cần quan sát |
| --- | --- |
| ID của một sách đã lưu và đang tồn tại. | Repository trả Optional chứa đúng định danh. |
| ID hợp lệ nhưng không có sách trong ngữ cảnh đọc. | Repository trả Optional rỗng, không phải null. |
| ID null. | Bị từ chối do vi phạm điều kiện đầu vào, không được xem như “không có sách”. |
| requireView nhận ID không tồn tại. | Service ném BookNotFoundException do chính sách nghiệp vụ. |
| findActiveView nhận ID của sách không active. | Optional rỗng do filter dù repository có thể đã tìm thấy entity. |
| Kho dữ liệu không truy cập được. | Lỗi được giữ lại hoặc chuyển đổi thành lỗi hệ thống có ý nghĩa, không thành Optional rỗng. |
| Optional đã có giá trị nhưng dùng orElse với một hàm fallback. | Biểu thức fallback vẫn được tính trước lời gọi. |
| Optional đã có giá trị và dùng orElseGet. | Supplier fallback không được gọi. |
| Một đối tượng bị xóa giữa existsById và findById. | Lần kiểm tra trước không bảo đảm lần đọc sau còn kết quả. |

Bảng này mô tả những hành vi cần kiểm chứng, không thay thế việc xác định module, transaction và dữ liệu đầu vào của một lần thực hành cụ thể.

## 14. Bài tập vận dụng

### Bài tập 1: Thiết kế hai hợp đồng service

Với cùng một `BookRepository`, viết:

- Một method trả `Optional<BookView>` để bên gọi tự quyết định khi thiếu sách.
- Một method trả `BookView` và ném exception nghiệp vụ khi thiếu sách.

Giải thích vì sao hai method có thể dùng cùng một `findById` nhưng mang chính sách vắng mặt khác nhau.

### Bài tập 2: Phân loại lỗi

Một ứng dụng đang trả thông báo “không tìm thấy sách” trong cả ba trường hợp: ID không tồn tại, ID null và kho dữ liệu mất kết nối.

Hãy chỉ ra tầng đang gộp sai các trạng thái, rồi thiết kế cách phân biệt lỗi đầu vào, kết quả vắng mặt và lỗi hệ thống. Không sửa bằng cách chỉ đổi nội dung một exception chung.

### Bài tập 3: Đọc đúng định danh

Một entity có `@Id Long pk` và một thuộc tính khác tên `id`. Giải thích sự khác nhau giữa method CRUD `findById` và derived query `findCustomerById`.

Xác định thêm điều kiện cần có nếu derived query trả Optional: dữ liệu phù hợp phải có tối đa một kết quả theo hợp đồng query đó.

Một cách sử dụng findById đúng luôn làm rõ ba điều: ID có hợp lệ không, lần đọc có hoàn tất bình thường không và sự vắng mặt có ý nghĩa gì trong nghiệp vụ. Optional giúp biểu diễn câu hỏi cuối, còn việc giữ đúng ranh giới giữa đầu vào, kết quả và lỗi là trách nhiệm của mã ứng dụng.