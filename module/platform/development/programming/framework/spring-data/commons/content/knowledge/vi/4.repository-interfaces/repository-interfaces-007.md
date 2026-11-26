# PagingAndSortingRepository và ListPagingAndSortingRepository

## Mục tiêu bài học

Một màn hình danh mục thường cần lấy dữ liệu theo thứ tự, chỉ hiển thị một phần kết quả và cho phép chuyển sang trang tiếp theo. Spring Data Commons cung cấp những hợp đồng chung cho các nhu cầu đó qua `PagingAndSortingRepository`, `ListPagingAndSortingRepository`, `Sort`, `Pageable` và `Page`.

Bài học thuộc chương **Giao diện repository** của module SPRING_DATA_COMMONS. Trọng tâm là chọn đúng interface và hiểu chính xác khả năng mà interface đó đưa vào API repository.

Sau bài học, bạn có thể:

- Phân biệt kiểu trả về của hai sorting repository.
- Kết hợp khả năng CRUD với phân trang, sắp xếp khi ứng dụng cần cả hai.
- Tạo yêu cầu sắp xếp và phân trang bằng các kiểu của Commons.
- Đọc nội dung và metadata của một `Page`.
- Tránh nhầm lẫn giữa `List`, một trang dữ liệu và toàn bộ tập kết quả.
- Nhận diện những giới hạn cần kiểm tra ở module lưu trữ cụ thể.

Bài sử dụng hệ interface từ Spring Data 3.0 trở đi. Từ mốc này, các sorting repository không còn tự kế thừa CRUD repository như ở các dòng cũ; các biến thể trả về `List` cũng được cung cấp để thể hiện rõ kiểu collection mong muốn.

## 1. Hai interface cung cấp những method nào?

### 1.1. PagingAndSortingRepository

Hợp đồng chính có thể mô tả ngắn gọn như sau:

~~~java
interface PagingAndSortingRepository<T, ID>
        extends Repository<T, ID> {

    Iterable<T> findAll(Sort sort);

    Page<T> findAll(Pageable pageable);
}
~~~

Đây là đoạn rút gọn để đọc API, không phải mã nguồn cần khai báo lại trong dự án. Các kiểu thuộc namespace `org.springframework.data.repository` và `org.springframework.data.domain` tương ứng.

Hai method giải quyết hai yêu cầu khác nhau:

- `findAll(Sort)`: lấy tập đối tượng theo thứ tự được yêu cầu, không có giới hạn trang trong hợp đồng này.
- `findAll(Pageable)`: lấy kết quả theo yêu cầu phân trang, trả về một `Page<T>`.

Điểm quan trọng là overload nhận `Sort` trả về `Iterable<T>`, còn overload nhận `Pageable` trả về `Page<T>`.

### 1.2. ListPagingAndSortingRepository

Biến thể này kế thừa `PagingAndSortingRepository` và thu hẹp kiểu trả về của thao tác lấy toàn bộ có sắp xếp:

~~~java
interface ListPagingAndSortingRepository<T, ID>
        extends PagingAndSortingRepository<T, ID> {

    @Override
    List<T> findAll(Sort sort);
}
~~~

Method `findAll(Pageable)` vẫn được kế thừa và vẫn trả về `Page<T>`.

Chữ “List” trong tên interface không biến kết quả phân trang thành `List<T>`. Nó thể hiện kiểu trả về cụ thể hơn của method nhận `Sort`.

### 1.3. Bảng đối chiếu

| Khả năng | PagingAndSortingRepository | ListPagingAndSortingRepository |
| --- | --- | --- |
| `findAll(Sort)` | `Iterable<T>` | `List<T>` |
| `findAll(Pageable)` | `Page<T>` | `Page<T>` |
| Tự cung cấp `findAll()` không tham số | Không, trong hệ interface đang xét. | Không. |
| Tự cung cấp `save`, `findById`, `deleteById` | Không. | Không. |
| Tự tạo giới hạn số phần tử cho method nhận `Sort` | Không. | Không. |

Một `Page<T>` có nội dung được lấy qua `getContent()` dưới dạng `List<T>` ở cả hai trường hợp. Vì thế, không cần đổi sang `ListPagingAndSortingRepository` chỉ để lấy danh sách phần tử của một trang.

## 2. Quan hệ với các interface CRUD

### 2.1. Sorting và CRUD là hai khả năng riêng

Trong hệ interface hiện hành được bài sử dụng, có thể hình dung:

~~~mermaid
flowchart TD
    R["Repository"] --> C["CrudRepository"]
    C --> LC["ListCrudRepository"]
    R --> P["PagingAndSortingRepository"]
    P --> LP["ListPagingAndSortingRepository"]
~~~

Mũi tên đi từ interface nền đến interface mở rộng. Hai nhánh mô tả hai nhóm khả năng khác nhau.

Nếu repository chỉ khai báo:

~~~java
public interface BookBrowseRepository
        extends PagingAndSortingRepository<Book, Long> {
}
~~~

thì biến có kiểu `BookBrowseRepository` chưa có method `save` hoặc `findById`. Không nên dựa vào một ví dụ cũ rồi cho rằng khả năng CRUD luôn có sẵn.

### 2.2. Kết hợp khi cần cả CRUD và sorting

Nếu muốn các thao tác CRUD và sorting có collection dạng `Iterable`:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface BookRepository
        extends CrudRepository<Book, Long>,
                PagingAndSortingRepository<Book, Long> {
}
~~~

Nếu muốn các thao tác trả nhiều phần tử tương ứng dùng `List`:

~~~java
import org.springframework.data.repository.ListCrudRepository;
import org.springframework.data.repository.ListPagingAndSortingRepository;

public interface BookRepository
        extends ListCrudRepository<Book, Long>,
                ListPagingAndSortingRepository<Book, Long> {
}
~~~

Hai đoạn là hai lựa chọn thay thế cho cùng một repository, không phải hai interface cùng tên để đặt cạnh nhau.

Với lựa chọn thứ hai:

| Lời gọi | Kiểu kết quả |
| --- | --- |
| `findAll()` | `List<Book>` từ nhánh ListCrudRepository. |
| `findAll(sort)` | `List<Book>` từ nhánh ListPagingAndSortingRepository. |
| `findAll(pageable)` | `Page<Book>` từ nhánh phân trang. |
| `findById(id)` | `Optional<Book>` từ nhánh CRUD. |
| `save(book)` | Đối tượng đã lưu theo hợp đồng CRUD. |

Khả năng được công khai phụ thuộc interface bạn chọn kế thừa. Interface trả về `List` không tự thêm hành vi nghiệp vụ hoặc cơ chế tối ưu hóa dữ liệu khác.

Trong ứng dụng JPA, `JpaRepository` là một lựa chọn chuyên biệt xây dựng trên những khả năng chung này. Khi học Commons, cần nhận diện đúng phần abstraction dùng chung trước khi chọn interface gắn với một module.

## 3. Sắp xếp bằng Sort

### 3.1. Sort mô tả thứ tự, không mô tả kích thước trang

Ví dụ:

~~~java
Sort sort = Sort.by("title").ascending()
    .and(Sort.by("id").ascending());
~~~

Yêu cầu này sắp xếp theo `title` tăng dần, rồi dùng `id` tăng dần làm thứ tự phụ.

Các chuỗi thuộc tính thường tham chiếu mô hình domain, không phải tên cột vật lý. Nếu thuộc tính Java tên `title` nhưng được ánh xạ sang một cột khác tên, phía repository vẫn phải dùng đường dẫn thuộc tính theo cơ chế của module.

Không truyền nguyên một đoạn SQL như `"title ASC, id ASC"` để thay thế danh sách thuộc tính. `Sort` không phải nơi viết một mệnh đề SQL tùy ý.

Với một repository trả `List`:

~~~java
List<Book> books = repository.findAll(sort);
~~~

kết quả bao gồm tập dữ liệu phù hợp với thao tác `findAll`, theo thứ tự được yêu cầu. Lời gọi này không tự giới hạn ở 10, 20 hay 100 đối tượng.

### 3.2. Vì sao cần thứ tự phụ?

Nếu nhiều sách có cùng tiêu đề, chỉ sắp theo tiêu đề chưa xác định rõ vị trí tương đối giữa chúng. Thêm ID làm tiêu chí phụ giúp tạo thứ tự có khả năng phân biệt các phần tử.

Điều này đặc biệt quan trọng khi chia trang. Một thứ tự không đủ rõ ràng có thể làm ranh giới giữa các trang khó dự đoán ngay cả khi dữ liệu không thay đổi.

Tuy nhiên, thứ tự phụ không tạo ảnh chụp nhất quán xuyên suốt nhiều lần đọc. Nếu có dữ liệu được chèn, xóa hoặc sửa giữa hai yêu cầu, vị trí các phần tử vẫn có thể thay đổi.

### 3.3. Không yêu cầu sắp xếp

Khi chủ động không cần thứ tự:

~~~java
Iterable<Book> books = repository.findAll(Sort.unsorted());
~~~

Nếu repository là biến thể List, kiểu kết quả của cùng lời gọi sẽ là `List<Book>`.

`Sort.unsorted()` nghĩa là không yêu cầu sắp xếp từ API này. Không được suy ra dữ liệu sẽ luôn theo ID tăng dần, thứ tự tạo hoặc thứ tự quan sát ở lần chạy trước.

Những lựa chọn như bỏ qua hoa thường hoặc gợi ý vị trí của giá trị null còn phụ thuộc khả năng của module và kho dữ liệu. Commons có thể diễn đạt một yêu cầu mà module cụ thể chưa hỗ trợ đầy đủ.

## 4. Phân trang bằng Pageable và PageRequest

`Pageable` mô tả yêu cầu phân trang. `PageRequest` là một cách tạo giá trị đó:

~~~java
Pageable request = PageRequest.of(
    0,
    20,
    Sort.by("title").ascending()
        .and(Sort.by("id").ascending())
);

Page<Book> page = repository.findAll(request);
~~~

Yêu cầu trên có ý nghĩa:

- Trang số 0, tức trang đầu tiên.
- Kích thước trang tối đa 20 phần tử.
- Sắp xếp theo tiêu đề rồi ID.

### 4.1. Chỉ số trang bắt đầu từ 0

| Trang hiển thị theo cách gọi thông thường | page truyền vào PageRequest |
| --- | --- |
| Trang thứ nhất | 0 |
| Trang thứ hai | 1 |
| Trang thứ ba | 2 |

Nếu giao diện dùng cách đánh số từ 1, tầng nhận yêu cầu cần chuyển đổi trước khi tạo `PageRequest`. Không cộng hoặc trừ 1 ở nhiều tầng khác nhau.

`PageRequest` yêu cầu chỉ số trang không âm và kích thước trang lớn hơn 0. Giới hạn kích thước tối đa, chẳng hạn 100 phần tử, là chính sách mà ứng dụng có thể bổ sung, không phải giới hạn mặc định chung của Commons.

### 4.2. Không nhầm số trang với offset

Với mô hình page/size thông thường:

~~~text
offset = page × size
~~~

Chẳng hạn, trang số 2 với kích thước 20 tương ứng yêu cầu bắt đầu sau 40 phần tử đầu, không phải sau 2 phần tử.

Công thức mô tả vị trí theo yêu cầu phân trang. Cách thực thi thực tế và khả năng truy cập đến vị trí đó phụ thuộc module lưu trữ. Một giao diện dùng `Pageable` không bảo đảm việc đi đến trang rất sâu luôn rẻ.

### 4.3. Hai overload không kết hợp bằng hai tham số riêng

Không có method kế thừa sau trong hai interface đang học:

~~~java
findAll(pageable, sort)
~~~

Thứ tự sắp xếp được đưa vào chính `Pageable`, như ví dụ `PageRequest.of(page, size, sort)`. Overload `findAll(Sort)` là một yêu cầu khác, không phân trang.

Nếu một ứng dụng có method nhận cả hai tham số, đó phải là API được thiết kế riêng chứ không phải hợp đồng mặc định của hai interface này.

## 5. Ví dụ repository và service trong ứng dụng JPA

Phần này minh họa cách dùng abstraction Commons trên Spring Data JPA. Giả định ứng dụng đã cấu hình datasource, entity scanning, repository scanning và bộ dependency tương thích.

### 5.1. Domain Book

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
    private boolean available;

    protected Book() {
    }

    public Book(String title, boolean available) {
        this.title = title;
        this.available = available;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public boolean isAvailable() {
        return available;
    }
}
~~~

Mapping và chiến lược sinh ID là phần JPA của ví dụ. Commons không yêu cầu mọi domain của mọi kho dữ liệu phải mang các annotation này.

### 5.2. Repository kết hợp CRUD và List sorting

File `repository/BookRepository.java`:

~~~java
package com.example.library.repository;

import com.example.library.domain.Book;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.ListCrudRepository;
import org.springframework.data.repository.ListPagingAndSortingRepository;

public interface BookRepository
        extends ListCrudRepository<Book, Long>,
                ListPagingAndSortingRepository<Book, Long> {

    Page<Book> findByAvailableTrue(Pageable pageable);
}
~~~

Repository có các method kế thừa để thao tác dữ liệu và có thêm một derived query chỉ lấy sách đang sẵn có.

Method `findAll(Pageable)` không tự áp dụng điều kiện `available = true`. Muốn lọc theo điều kiện đó, bên gọi phải chọn đúng method query đã khai báo.

### 5.3. Service gọi đúng overload

File `BookBrowseService.java`:

~~~java
package com.example.library;

import com.example.library.domain.Book;
import com.example.library.repository.BookRepository;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class BookBrowseService {

    private final BookRepository repository;

    public BookBrowseService(BookRepository repository) {
        this.repository = repository;
    }

    public Page<Book> browse(int page, int size) {
        Pageable request = createRequest(page, size);
        return repository.findAll(request);
    }

    public Page<Book> browseAvailable(int page, int size) {
        Pageable request = createRequest(page, size);
        return repository.findByAvailableTrue(request);
    }

    public List<Book> listAllByTitle() {
        return repository.findAll(titleOrder());
    }

    private Pageable createRequest(int page, int size) {
        if (page < 0) {
            throw new IllegalArgumentException(
                "Chỉ số trang không được âm"
            );
        }

        if (size < 1 || size > 100) {
            throw new IllegalArgumentException(
                "Kích thước trang phải từ 1 đến 100"
            );
        }

        return PageRequest.of(page, size, titleOrder());
    }

    private Sort titleOrder() {
        return Sort.by("title").ascending()
            .and(Sort.by("id").ascending());
    }
}
~~~

Ba method công khai thể hiện ba nhu cầu:

| Method service | Kết quả và phạm vi |
| --- | --- |
| `browse` | Một trang trong toàn bộ sách. |
| `browseAvailable` | Một trang trong tập sách đang sẵn có. |
| `listAllByTitle` | Toàn bộ sách theo thứ tự, không có giới hạn trang. |

Giới hạn 100 trong service là quyết định của ví dụ. Nó không áp dụng cho `listAllByTitle` vì method đó không đi qua một `PageRequest`.

Nếu không muốn công khai CRUD, có thể chỉ kế thừa `ListPagingAndSortingRepository` trong một repository phục vụ tra cứu. Việc kết hợp với `ListCrudRepository` ở ví dụ nhằm thể hiện cách khai báo khi ứng dụng cần cả hai nhóm khả năng.

## 6. Đọc nội dung và metadata của Page

Ví dụ:

~~~java
Page<Book> result = repository.findAll(
    PageRequest.of(
        0,
        3,
        Sort.by("title").ascending()
            .and(Sort.by("id").ascending())
    )
);

List<Book> content = result.getContent();

int pageNumber = result.getNumber();
int requestedSize = result.getSize();
int elementsOnThisPage = result.getNumberOfElements();
long totalElements = result.getTotalElements();
int totalPages = result.getTotalPages();
boolean hasNext = result.hasNext();
~~~

Các giá trị không có cùng ý nghĩa:

| API | Ý nghĩa |
| --- | --- |
| `getContent()` | Danh sách phần tử thuộc trang hiện tại. |
| `getNumber()` | Chỉ số trang hiện tại, bắt đầu từ 0. |
| `getSize()` | Kích thước trang theo thông tin yêu cầu/kết quả. |
| `getNumberOfElements()` | Số phần tử thực tế trong trang hiện tại. |
| `getTotalElements()` | Tổng số phần tử của tập kết quả mà truy vấn biểu diễn. |
| `getTotalPages()` | Tổng số trang theo kích thước trang. |
| `hasNext()` | Có trang tiếp theo theo metadata của kết quả hay không. |

Trang cuối có thể có ít phần tử hơn kích thước được yêu cầu. Ví dụ, kích thước trang là 3 nhưng trang cuối chỉ chứa 1 phần tử thì `getSize()` và `getNumberOfElements()` không bằng nhau.

Với query lọc sách sẵn có, `getTotalElements()` phản ánh tổng số sách phù hợp điều kiện query đó, không phải tổng số mọi sách trong kho dữ liệu.

Không chuyển sang chỉ giữ `getContent()` nếu bên gọi còn cần tổng số trang hoặc trạng thái trang tiếp theo. Một `List` riêng không mang các metadata đó.

## 7. Quan sát bằng một tập dữ liệu nhỏ

Giả sử dữ liệu không thay đổi trong thời gian kiểm tra và có thứ tự theo `title ASC, id ASC` như sau. ID trong bảng chỉ dùng để minh họa.

| ID | title |
| --- | --- |
| 10 | Core |
| 11 | Core |
| 12 | Data |
| 13 | JPA |
| 14 | Mongo |
| 15 | Redis |
| 16 | Spring |

Với kích thước trang bằng 3:

| Yêu cầu | Nội dung theo ID | Số phần tử trong trang | Tổng phần tử | Tổng trang |
| --- | --- | --- | --- | --- |
| `PageRequest.of(0, 3, sort)` | 10, 11, 12 | 3 | 7 | 3 |
| `PageRequest.of(1, 3, sort)` | 13, 14, 15 | 3 | 7 | 3 |
| `PageRequest.of(2, 3, sort)` | 16 | 1 | 7 | 3 |

Đối chiếu với:

~~~java
List<Book> all = repository.findAll(sort);
~~~

Kết quả không phân trang sẽ chứa cả 7 đối tượng theo thứ tự, thay vì chỉ một nhóm 3 đối tượng.

Hai sách cùng tiêu đề Core có thứ tự rõ nhờ ID phụ. Nếu bỏ tiêu chí ID, không nên dựa vào việc một lần chạy tình cờ trả ID 10 trước ID 11.

Một trang nằm ngoài phạm vi dữ liệu có thể có nội dung rỗng. Nội dung rỗng của một trang không tự chứng minh toàn bộ tập dữ liệu không có phần tử; cần đọc thêm metadata và kiểm tra chỉ số trang yêu cầu.

### Chuyển trang bằng metadata kết quả

~~~java
Page<Book> current = repository.findAll(
    PageRequest.of(0, 3, sort)
);

if (current.hasNext()) {
    Page<Book> next = repository.findAll(
        current.nextPageable()
    );
}
~~~

Kiểm tra `hasNext()` trước khi dùng yêu cầu trang kế tiếp. Khi không có trang tiếp theo, `nextPageable()` có thể trả về giá trị unpaged; không nên gọi tiếp một cách máy móc rồi vô tình thay đổi ý nghĩa truy vấn.

## 8. Những nhầm lẫn về List, Page và Slice

### 8.1. List không phải một trang có metadata

`List<Book>` chỉ thể hiện một collection theo kiểu Java. Kiểu này không cho biết collection là toàn bộ kết quả hay một phần, cũng không cung cấp tổng số phần tử của truy vấn.

Trong `ListPagingAndSortingRepository`, `findAll(Sort)` không có tham số giới hạn và không phải cơ chế bảo vệ trước việc lấy quá nhiều dữ liệu.

Ngược lại, `findAll(Pageable)` trả `Page<Book>` ở cả hai interface. Chính tham số và hợp đồng method quyết định yêu cầu phân trang, không phải chữ “List” trong tên interface.

### 8.2. Iterable không bảo đảm xử lý lười

Việc `PagingAndSortingRepository.findAll(Sort)` trả `Iterable` không cam kết rằng dữ liệu được đọc từng phần từ kho lưu trữ hoặc có thể xử lý một tập rất lớn với bộ nhớ cố định.

Tương tự, chọn biến thể `List` không tự làm truy vấn nhanh hơn hoặc chậm hơn. Cần xem cách thực thi của module và lượng dữ liệu thực tế.

### 8.3. Page có tổng số phần tử, Slice không yêu cầu tổng đó

Một `Page` cung cấp tổng số phần tử và tổng số trang. Để tạo metadata này, module có thể cần thêm truy vấn đếm; trong một số tình huống có thể suy ra tổng mà không chạy một truy vấn đếm riêng.

Nếu giao diện chỉ cần biết còn phần tiếp theo, một query trả `Slice` có thể phù hợp khi module hỗ trợ. Ví dụ một method khác có thể được khai báo:

~~~java
Slice<Book> findSliceByAvailableTrue(Pageable pageable);
~~~

Đây là method query bổ sung, cần import `org.springframework.data.domain.Slice` và được module lưu trữ hỗ trợ.

Không thể đổi chữ ký method kế thừa thành:

~~~java
Slice<Book> findAll(Pageable pageable);
~~~

để thay thế method trả `Page<Book>` trong cùng hệ kế thừa. `Slice` là kiểu rộng hơn `Page`, nên thay đổi đó không phải override kiểu trả về hợp lệ trong Java.

Chọn một method query khác hoặc một hợp đồng repository thích hợp nếu muốn dùng `Slice`. Đổi interface sang biến thể List không thay đổi method phân trang kế thừa thành Slice.

## 9. Đặt điều kiện lọc vào truy vấn trước khi phân trang

Một lỗi thiết kế phổ biến là lấy trang tất cả sách, sau đó mới lọc những sách sẵn có trong Java.

~~~text
Lấy 20 sách bất kỳ theo trang
    -> lọc available trong bộ nhớ
    -> chỉ còn vài sách
~~~

Cách này làm kích thước nội dung sau lọc và metadata tổng không còn mô tả đúng màn hình sách sẵn có. Một sách phù hợp nằm ở trang khác cũng chưa được xem xét.

Trong ví dụ, cách diễn đạt đúng là:

~~~java
Page<Book> availableBooks =
    repository.findByAvailableTrue(request);
~~~

Điều kiện lọc trở thành một phần truy vấn mà module thực thi trước khi hình thành trang kết quả phù hợp.

Cùng nguyên tắc đó áp dụng cho derived queries, Query by Example hoặc các cơ chế truy vấn khác khi module hỗ trợ. Hai interface đang học cung cấp nền tảng phân trang/sắp xếp; chúng không tự thiết kế mọi điều kiện lọc của ứng dụng.

## 10. Ranh giới trách nhiệm và hiệu năng

### 10.1. Commons diễn đạt yêu cầu, module thực thi

Commons cung cấp:

- Hợp đồng `PagingAndSortingRepository` và biến thể List.
- `Sort`, `Pageable` và `PageRequest` để diễn đạt yêu cầu.
- `Page` cùng metadata kết quả.

Module lưu trữ quyết định cách thực hiện yêu cầu dựa trên mô hình, driver và khả năng của kho dữ liệu.

Bởi vậy, cùng một `PageRequest` không bảo đảm mọi module hỗ trợ cùng cách phân trang hoặc có chi phí tương đương. Có interface trên classpath cũng không có nghĩa mọi tổ hợp khả năng đều được mọi module triển khai.

### 10.2. Trang sâu có thể tốn chi phí

Một yêu cầu trang có offset lớn có thể khiến hệ thống phải xử lý hoặc bỏ qua nhiều dữ liệu trước khi trả phần cần thiết. Index phù hợp có thể giúp truy vấn, nhưng không biến mọi kiểu phân trang thành truy cập chi phí cố định.

Nếu ứng dụng cần duyệt sâu hoặc cuộn liên tục trên dữ liệu lớn, có thể phải đánh giá cursor, keyset hoặc scrolling theo khả năng module. Chuyển từ PagingAndSortingRepository sang ListPagingAndSortingRepository không tự kích hoạt những cơ chế đó.

### 10.3. Tổng số phần tử cũng là một yêu cầu dữ liệu

Khi dùng `Page`, hãy xác định giao diện có thật sự cần tổng số kết quả hay không. Truy vấn đếm có thể đáng kể trên một số điều kiện hoặc cấu trúc dữ liệu.

Nếu chọn Slice hoặc phương án khác để không cần tổng, vẫn phải xem chi phí truy cập phần dữ liệu chính. Không có tổng số phần tử không tự làm mọi truy vấn phân trang trở nên rẻ.

### 10.4. Phân trang không tạo tính nhất quán xuyên nhiều lần gọi

Nếu dữ liệu thay đổi giữa lần lấy trang 0 và trang 1, người dùng có thể thấy phần tử dịch chuyển, lặp lại hoặc không còn xuất hiện ở vị trí dự kiến.

Sắp xếp có tiêu chí phân biệt là điều cần thiết để thứ tự rõ ràng, nhưng không thay thế thiết kế transaction, snapshot hoặc chiến lược duyệt dữ liệu của hệ thống.

### 10.5. Unpaged phải được dùng có chủ đích

Có thể diễn đạt một yêu cầu không phân trang bằng:

~~~java
Page<Book> all = repository.findAll(Pageable.unpaged());
~~~

Với module hỗ trợ lời gọi tương ứng, kết quả không còn giới hạn theo kích thước trang như `PageRequest`. Kiểu trả về vẫn là `Page`, nhưng sự có mặt của kiểu Page không tự bảo đảm dữ liệu đã bị giới hạn.

Khi cần lấy toàn bộ có sắp xếp, overload `findAll(Sort)` thể hiện nhu cầu trực tiếp hơn. Trong cả hai trường hợp, lượng dữ liệu vẫn cần phù hợp với mục đích sử dụng.

## 11. Các lỗi thường gặp và cách phân tích

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách điều chỉnh |
| --- | --- | --- |
| Không gọi được `save` sau khi đổi interface. | Repository chỉ kế thừa sorting repository ở dòng API tách CRUD. | Kế thừa thêm CrudRepository hoặc ListCrudRepository nếu API cần ghi. |
| Không gọi được `findAll()` không tham số. | Không có nhánh CRUD cung cấp method đó. | Chọn đúng hợp đồng hoặc gọi overload có tham số theo nhu cầu. |
| Không gán được kết quả `findAll(sort)` cho List. | Interface hiện tại trả Iterable. | Dùng biến thể List hoặc xử lý theo hợp đồng Iterable. |
| Dùng ListPaging nhưng method pageable vẫn trả Page. | Đây là hợp đồng đúng của interface. | Lấy content bằng `getContent()` hoặc giữ cả Page nếu cần metadata. |
| Trang đầu không như mong đợi. | Nhầm chỉ số bắt đầu từ 0 hoặc chuyển đổi chỉ số ở nhiều tầng. | Chốt quy ước giữa giao diện và service. |
| Kết quả giữa các trang có thứ tự không rõ. | Thiếu Sort hoặc thiếu tiêu chí phân biệt khi giá trị trùng nhau. | Thêm thứ tự phụ thích hợp và xét thay đổi dữ liệu giữa các lần đọc. |
| Một trang có ít phần tử dù còn dữ liệu phù hợp. | Đã lọc trong bộ nhớ sau khi lấy trang. | Đưa điều kiện vào query trước khi phân trang. |
| Tên trường sắp xếp gây lỗi. | Dùng sai thuộc tính domain hoặc dùng tên cột thay cho thuộc tính. | Đối chiếu mapping và đường dẫn thuộc tính mà module hỗ trợ. |
| Tải toàn bộ dữ liệu ngoài dự kiến. | Gọi overload Sort hoặc truyền unpaged. | Kiểm tra chính đối tượng tham số và overload được gọi. |
| Lấy Page chậm. | Query chính, vị trí trang, count hoặc index chưa phù hợp. | Xác định thành phần tốn chi phí trước khi chọn hướng tối ưu. |

Nếu đang nâng cấp từ một dòng Spring Data cũ, nên kiểm tra lại hệ interface mà repository thực sự kế thừa. Bổ sung khả năng CRUD cần thiết ở khai báo repository thay vì thêm các method tùy tiện chỉ để chữa từng lỗi biên dịch.

Không mặc định rằng một method repository không hoạt động là do thiếu interface. Cấu hình module, mapping, dependency tương thích và khả năng của kho dữ liệu vẫn cần được xem xét.

## 12. Bài tập vận dụng

### Bài tập 1: Chọn đúng hệ interface

Một chức năng quản lý cần:

- Lưu và tìm sách theo ID.
- Lấy toàn bộ sách theo thứ tự dưới dạng List.
- Lấy một Page sách theo yêu cầu phân trang.

Một lựa chọn phù hợp là kết hợp `ListCrudRepository<Book, Long>` và `ListPagingAndSortingRepository<Book, Long>` trong module có hỗ trợ tương ứng.

Nếu chức năng chỉ tra cứu có phân trang và sắp xếp, không cần công khai CRUD, có thể chỉ chọn sorting repository phù hợp với kiểu collection mong muốn.

### Bài tập 2: Đọc metadata

Với 7 phần tử và kích thước trang 3, hãy xác định:

1. Chỉ số của trang cuối.
2. Số phần tử thực tế trong trang cuối.
3. Khác biệt giữa `getSize()` và `getNumberOfElements()` ở trang đó.
4. Kết quả của `hasNext()` khi đang ở trang cuối.

Đáp án trong điều kiện tập dữ liệu không đổi: trang cuối có chỉ số 2, chứa 1 phần tử, kích thước yêu cầu là 3 và không có trang tiếp theo.

### Bài tập 3: Phân biệt hai overload

So sánh:

~~~java
repository.findAll(
    Sort.by("title").ascending()
);
~~~

với:

~~~java
repository.findAll(
    PageRequest.of(
        0,
        10,
        Sort.by("title").ascending()
    )
);
~~~

Lời gọi đầu yêu cầu toàn bộ kết quả có sắp xếp, còn lời gọi sau yêu cầu trang đầu tối đa 10 phần tử và trả metadata Page. Với biến thể List, khác biệt đó vẫn giữ nguyên.

Khi thiết kế một repository, hãy quyết định riêng ba điều: có cần CRUD hay không, kết quả lấy toàn bộ cần Iterable hay List, và truy vấn cần toàn bộ dữ liệu hay một trang. Ba quyết định này giúp chọn đúng interface và đúng method mà không gán thêm khả năng cho tên gọi của repository.