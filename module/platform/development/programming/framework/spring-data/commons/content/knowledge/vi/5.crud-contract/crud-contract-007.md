# Null đầu vào, dữ liệu thiếu và exception theo hợp đồng

## Mục tiêu bài học

Ba tình huống thường bị gộp nhầm khi sử dụng repository là: truyền đầu vào không hợp lệ, thao tác hợp lệ nhưng không có dữ liệu và thao tác thất bại vì một nguyên nhân khác. Trong Spring Data Commons, chúng có ý nghĩa khác nhau và cần được xử lý theo hợp đồng của từng method CRUD.

Bài học thuộc chương **Hợp đồng CRUD** của module SPRING_DATA_COMMONS. Trọng tâm là đọc đúng điều kiện đầu vào và kết quả của repository, từ đó xây dựng service không che giấu lỗi hoặc báo sai trạng thái dữ liệu.

Sau bài học, bạn có thể:

- Nhận diện null ở tham số đơn, tập đầu vào và phần tử bên trong tập.
- Phân biệt entity mới có ID null với việc truyền ID null vào một method tìm hoặc xóa.
- Giải thích cách các method CRUD biểu diễn dữ liệu không tồn tại.
- Phân loại lỗi đầu vào, xung đột cập nhật, lỗi ràng buộc và lỗi hạ tầng.
- Đặt kiểm tra đầu vào và ranh giới transaction theo yêu cầu của ứng dụng.

Các hợp đồng chung không thay thế mapping và khả năng của từng module lưu trữ. Ví dụ thực hành dùng Spring Data JPA; các chi tiết về JPA được chỉ rõ ở nơi liên quan.

## 1. Phân loại trước khi chọn cách xử lý

~~~mermaid
flowchart TD
    A["Yêu cầu CRUD"] --> B{"Đầu vào có đáp ứng hợp đồng?"}
    B -->|"Không"| C["Lỗi đầu vào: ví dụ ID hoặc entity null"]
    B -->|"Có"| D{"Thao tác có thực thi thành công?"}
    D -->|"Không"| E["Exception theo nguyên nhân thực thi"]
    D -->|"Có"| F["Kết quả theo method"]
    F --> G["Có dữ liệu hoặc có thay đổi"]
    F --> H["Không có dữ liệu hoặc không có gì cần xóa"]
~~~

Không có dữ liệu chỉ là một kết quả của một số thao tác đã được thực hiện hợp lệ. Nó không phải cách biểu diễn chung cho đầu vào sai hoặc kết nối thất bại.

| Tình huống | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Đầu vào vi phạm hợp đồng | `findById(null)` | Chưa phải một yêu cầu tìm theo ID hợp lệ. |
| Không có dữ liệu | `findById(validId)` trả Optional rỗng | Thao tác đọc hoàn tất nhưng không tìm thấy đối tượng. |
| Không có gì để xóa theo ID | ID hợp lệ nhưng đối tượng không còn tồn tại | Hành vi được quyết định bởi hợp đồng xóa theo ID. |
| Lỗi thực thi | Lỗi kết nối, ràng buộc hoặc xung đột version | Không được suy ra rằng dữ liệu không tồn tại. |

Trước khi viết `try/catch` hoặc giá trị mặc định, hãy xác định yêu cầu thuộc hàng nào.

## 2. Null ở tham số đơn trong CRUD

Những method CRUD thường gặp có các điều kiện đầu vào sau:

| Method | Tham số không được null | Hành vi khi vi phạm theo hợp đồng CRUD |
| --- | --- | --- |
| `save(entity)` | Entity đầu vào. | IllegalArgumentException. |
| `findById(id)` | ID cần tìm. | IllegalArgumentException. |
| `existsById(id)` | ID cần kiểm tra. | IllegalArgumentException. |
| `deleteById(id)` | ID cần xóa. | IllegalArgumentException. |
| `delete(entity)` | Entity cần xóa. | IllegalArgumentException. |

Bảng này nói về null ở **đối tượng tham số**, không nói rằng mọi thuộc tính bên trong một entity đều phải khác null.

Ví dụ:

~~~java
repository.save(null);
~~~

vi phạm điều kiện đầu vào của method. Trong khi đó:

~~~java
Book draft = new Book("Spring Data Commons");
repository.save(draft);
~~~

có thể là thao tác tạo hợp lệ dù `draft.getId()` đang bằng null, nếu mapping và cơ chế nhận diện entity mới của module hỗ trợ cách sử dụng đó.

### 2.1. ID null của entity mới khác với tham số ID null

Với entity JPA dùng ID được sinh tự động:

~~~text
save(entity không-null, entity.id chưa được sinh)
    -> có thể hợp lệ cho entity mới

findById(null)
    -> không có một định danh hợp lệ để tìm
~~~

Không áp dụng một kiểm tra chung kiểu “entity nào ID null cũng không được lưu” nếu mô hình sử dụng ID được sinh khi tạo.

Ngược lại, một module dùng ID do ứng dụng gán có thể yêu cầu ID được chuẩn bị theo mapping của nó. Commons không chọn cơ chế sinh ID thay cho từng công nghệ.

Đối với `delete(entity)`, entity không-null cũng chưa đủ để khẳng định mọi trạng thái ID đều được xử lý giống nhau. Hành vi với một entity mới hoặc chưa có định danh còn phụ thuộc module và trạng thái domain.

### 2.2. IllegalArgumentException không đồng nghĩa NullPointerException

Nếu muốn service từ chối null bằng cùng một loại lỗi đầu vào rõ ràng, có thể viết:

~~~java
private static void requireId(Long id) {
    if (id == null) {
        throw new IllegalArgumentException("ID không được null");
    }
}
~~~

`Objects.requireNonNull(id)` thường ném `NullPointerException` khi id là null. Đó là hành vi của hàm kiểm tra Java, không phải cùng một lựa chọn exception với đoạn trên.

Không phải mọi cách kiểm tra null đều giữ nguyên loại exception mà bạn muốn công khai ở tầng service.

## 3. Null trong tập đầu vào

Các method nhận nhiều đối tượng hoặc nhiều ID có hai mức điều kiện cần phân biệt:

1. Chính tập đầu vào không được null.
2. Các phần tử bên trong tập cũng không được null.

| Method | Tập đầu vào | Phần tử bên trong |
| --- | --- | --- |
| `saveAll(entities)` | Không-null. | Không có entity null. |
| `findAllById(ids)` | Không-null. | Không có ID null. |
| `deleteAllById(ids)` | Không-null. | Không có ID null. |
| `deleteAll(entities)` | Không-null. | Không có entity null. |

Null ở một trong hai mức vi phạm hợp đồng và có thể dẫn đến `IllegalArgumentException` theo method CRUD tương ứng.

### 3.1. Tập null, tập rỗng và tập có phần tử null

Ba giá trị này khác nhau:

~~~java
Iterable<Long> missingInput = null;

Iterable<Long> emptyInput = List.of();

Iterable<Long> invalidElements = Arrays.asList(10L, null, 12L);
~~~

- `missingInput` không có một tập đầu vào hợp lệ.
- `emptyInput` là tập hợp lệ nhưng không có phần tử.
- `invalidElements` là một tập đã có nhưng chứa phần tử vi phạm hợp đồng.

Các method CRUD nhận tập không mặc định yêu cầu ít nhất một phần tử. Trong trường hợp thông thường, tập rỗng dẫn đến kết quả rỗng hoặc không có gì cần xử lý. Nếu ứng dụng muốn từ chối một batch rỗng, đó là quy tắc bổ sung của ứng dụng.

### 3.2. Chú ý nơi exception thật sự xuất hiện

Đoạn sau không phải cách phù hợp để quan sát repository xử lý phần tử null:

~~~java
List<Long> ids = List.of(10L, null);
repository.findAllById(ids);
~~~

`List.of` tự từ chối phần tử null và ném exception ngay khi tạo danh sách. Lời gọi repository chưa diễn ra.

Nếu cần kiểm chứng điều kiện null phần tử tại biên repository, phải sử dụng một collection cho phép tạo giá trị đó, chẳng hạn `Arrays.asList` trong ví dụ trước.

Khi phân tích exception, luôn xác định nó đến từ tạo dữ liệu đầu vào, kiểm tra service hay implementation repository.

### 3.3. Vi phạm ở phần tử sau không chứng minh phần tử trước chưa được xử lý

Một method nhận `Iterable` có thể duyệt và xử lý từng phần tử. Không nên chỉ từ hợp đồng “không có phần tử null” mà suy ra implementation chắc chắn kiểm tra toàn bộ tập trước khi làm bất kỳ thao tác nào.

Nếu dữ liệu có phần tử hợp lệ ở đầu và null ở cuối, khả năng có thay đổi trước khi lỗi xuất hiện còn phụ thuộc implementation và ranh giới transaction.

Khi muốn từ chối cả yêu cầu trước khi gọi repository, service có thể duyệt một lượt để kiểm tra và tạo danh sách đầu vào ổn định. Việc kiểm tra trước vẫn không thay thế transaction cho những lỗi có thể xảy ra trong quá trình ghi.

## 4. Dữ liệu không tồn tại được biểu diễn thế nào?

| Method hoặc tình huống | Kết quả vắng mặt theo hợp đồng liên quan |
| --- | --- |
| `findById(id)` với ID hợp lệ không tìm thấy | Optional.empty(), không phải null. |
| `existsById(id)` với ID hợp lệ không tồn tại | false. |
| `findAll()` khi không có đối tượng | Iterable hoặc List rỗng tùy interface, không phải null. |
| `findAllById(ids)` có một số ID không tìm thấy | Những ID thiếu không tạo phần tử tương ứng trong kết quả. |
| `count()` khi không có đối tượng | 0. |
| `deleteById(id)` với đối tượng không tìm thấy | Theo hợp đồng đang xét, bỏ qua trường hợp không tìm thấy. |
| `deleteAllById(ids)` có ID không tìm thấy | Các đối tượng không tìm thấy được bỏ qua theo hợp đồng xóa theo ID. |

### 4.1. Optional rỗng khác với một Optional bằng null

Với implementation tuân thủ hợp đồng:

~~~java
Optional<Book> result = repository.findById(bookId);
~~~

`result` là một đối tượng Optional hợp lệ. Nếu không có sách, `result.isEmpty()` là true.

Nếu một implementation tùy biến hoặc stub trả null cho chữ ký này, đó là một hành vi vi phạm hợp đồng trả về. Không nên bắt bên gọi kiểm tra cả null lẫn Optional rỗng để bù cho lỗi đó.

### 4.2. findAllById không giữ chỗ cho ID thiếu

Giả sử đầu vào gồm các ID 10, 99 và 12, nhưng chỉ 10 và 12 tồn tại.

Kết quả có thể chứa hai entity tìm được. Nó không có một phần tử null ở vị trí của 99 và không phải danh sách Optional có cùng số phần tử với đầu vào.

Thứ tự kết quả cũng không được mặc định giống thứ tự các ID truyền vào. Nếu cần báo cụ thể ID nào bị thiếu, hãy đối chiếu theo định danh.

### 4.3. Xóa theo ID thiếu không phải một lỗi bắt buộc

Với `deleteById`, việc một ID không còn dữ liệu là trường hợp được bỏ qua theo hợp đồng CRUD đang xét. Không dựa vào kỳ vọng “xóa ID thiếu luôn ném exception” để thiết kế nghiệp vụ.

Tuy nhiên, điều đó không có nghĩa thao tác xóa không bao giờ lỗi. Lỗi kết nối, ràng buộc hoặc lỗi thực thi vẫn có thể xảy ra.

Nếu ứng dụng yêu cầu phân biệt “đã tồn tại và bị xóa” với “đã không tồn tại”, riêng method trả void không cung cấp đầy đủ thông tin đó. Kiểm tra trước bằng `existsById` cũng không bảo đảm dữ liệu giữ nguyên giữa hai lần gọi. Khi sự phân biệt này quan trọng, cần một thiết kế thao tác và khả năng kho dữ liệu phù hợp.

## 5. Entity không-null vẫn có thể không hợp lệ

Hợp đồng method, quy tắc domain và ràng buộc lưu trữ là ba lớp khác nhau.

| Lớp | Ví dụ | Nơi thường kiểm tra |
| --- | --- | --- |
| Hợp đồng đầu vào repository | Entity hoặc ID null. | Biên repository và kiểm tra chủ động ở service. |
| Quy tắc domain | Tiêu đề không được trống hoặc chỉ có khoảng trắng. | Constructor, method domain hoặc service theo thiết kế. |
| Mapping và ràng buộc lưu trữ | Cột không-null, giá trị duy nhất, khóa tham chiếu. | Mapping, provider và kho dữ liệu. |

Một entity có `title = null` vẫn là một đối tượng Java không-null. Trường hợp đó không giống `save(null)`.

Nếu mapping không cho phép title null, việc lưu entity có thể thất bại khi provider hoặc cơ sở dữ liệu kiểm tra dữ liệu. Loại lỗi và thời điểm phát hiện còn phụ thuộc module.

Tương tự, nullability annotation hoặc gợi ý của IDE không tự thay thế toàn bộ kiểm tra runtime và ràng buộc lưu trữ. Cần đọc đúng phạm vi mà annotation đang mô tả: tham số, kết quả hay thuộc tính domain.

## 6. Ví dụ service kiểm tra đầu vào trước khi gọi repository

Ví dụ dưới đây dùng JPA cho mapping và `ListCrudRepository` cho hợp đồng CRUD. Giả định ứng dụng đã cấu hình module JPA, datasource và scanning phù hợp.

### 6.1. Domain có ID được sinh và version

File `domain/Book.java`:

~~~java
package com.example.library.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "library_book")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false)
    private String title;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getTitle() {
        return title;
    }
}
~~~

`@Id`, `@GeneratedValue` và `@Version` ở đây thuộc JPA. Version phục vụ cơ chế optimistic locking của ví dụ JPA; không phải mọi module đều triển khai kiểm soát đồng thời giống nhau.

Constructor này giữ ví dụ đơn giản và chưa kiểm tra tiêu đề. Service bên dưới chủ động thực hiện chính sách kiểm tra trước khi lưu.

### 6.2. Repository

File `repository/BookRepository.java`:

~~~java
package com.example.library.repository;

import com.example.library.domain.Book;
import org.springframework.data.repository.ListCrudRepository;

public interface BookRepository
        extends ListCrudRepository<Book, Long> {
}
~~~

Biến thể List cho phép `saveAll` trả về `List` ở ví dụ service. Các điều kiện không-null của hợp đồng CRUD vẫn giữ nguyên.

### 6.3. Exception cho tình huống nghiệp vụ bắt buộc có sách

File `BookNotFoundException.java`:

~~~java
package com.example.library;

public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(Long id) {
        super("Không tìm thấy sách: " + id);
    }
}
~~~

Đây là exception do ứng dụng định nghĩa. Repository không tự ném exception này khi một lần `findById` hợp lệ không có kết quả.

### 6.4. Service

File `BookService.java`:

~~~java
package com.example.library;

import com.example.library.domain.Book;
import com.example.library.repository.BookRepository;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Optional<Book> findOptional(Long id) {
        requireId(id);
        return repository.findById(id);
    }

    public Book requireBook(Long id) {
        requireId(id);

        return repository.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    }

    public Book saveBook(Book candidate) {
        requireBookInput(candidate);
        return repository.save(candidate);
    }

    public List<Book> saveBatch(Iterable<Book> candidates) {
        if (candidates == null) {
            throw new IllegalArgumentException(
                "Danh sách sách không được null"
            );
        }

        List<Book> validated = new ArrayList<>();

        for (Book candidate : candidates) {
            requireBookInput(candidate);
            validated.add(candidate);
        }

        if (validated.isEmpty()) {
            return List.of();
        }

        return repository.saveAll(validated);
    }

    public void deleteIfPresent(Long id) {
        requireId(id);
        repository.deleteById(id);
    }

    private static void requireId(Long id) {
        if (id == null) {
            throw new IllegalArgumentException(
                "ID không được null"
            );
        }
    }

    private static void requireBookInput(Book book) {
        if (book == null) {
            throw new IllegalArgumentException(
                "Sách không được null"
            );
        }

        if (book.getTitle() == null
                || book.getTitle().isBlank()) {
            throw new IllegalArgumentException(
                "Tiêu đề sách không được để trống"
            );
        }
    }
}
~~~

Service có những quyết định rõ ràng:

- Null ở ID, entity hoặc batch bị từ chối.
- Mọi phần tử batch được kiểm tra trước khi gọi `saveAll`.
- Batch rỗng được chấp nhận và trả danh sách rỗng.
- Entity mới không bị từ chối chỉ vì ID chưa được sinh.
- Một lần tra cứu tùy chọn giữ Optional; một lần yêu cầu bắt buộc có dữ liệu dùng exception nghiệp vụ.
- Xóa theo ID thiếu được chấp nhận, nhưng lỗi thực thi không bị nuốt.

Danh sách `validated` chốt tập tham chiếu đầu vào sau một lượt duyệt, tránh phải giả định mọi Iterable đều có thể duyệt lặp lại tùy ý. Nó không tạo một bản sao sâu của các entity hoặc một cơ chế transaction.

Code này cũng không khẳng định việc kiểm tra title ở service là nơi duy nhất để giữ quy tắc domain. Một thiết kế khác có thể đặt điều kiện đó ngay trong constructor hoặc hành vi domain.

## 7. Exception theo nguyên nhân, không chỉ theo tên method

### 7.1. IllegalArgumentException: đầu vào hoặc cách dùng không hợp lệ

Null ở tham số bị cấm là một nguyên nhân rõ ràng. Một số cách dùng không hợp lệ khác cũng có thể phát sinh exception loại này ở tầng ứng dụng hoặc hạ tầng.

Không kết luận rằng mọi IllegalArgumentException đều do người dùng nhập sai ID. Cần xác định nơi nó được ném; null có thể đến từ lỗi lập trình bên trong ứng dụng.

Trong service ví dụ, các thông báo kiểm tra đầu vào giúp định vị điều kiện vi phạm cụ thể.

### 7.2. OptimisticLockingFailureException: xung đột trạng thái

Các đường lưu và một số đường xóa có thể phát sinh `OptimisticLockingFailureException` khi entity có trạng thái version không còn phù hợp với dữ liệu lưu trữ.

Hợp đồng cũng đề cập tình huống entity được coi là phải tồn tại nhưng không còn tìm thấy trong quá trình thực hiện thao tác. Không nên từ đó suy ra mọi implementation đều báo cùng một lỗi cho mọi entity thiếu; cơ chế nhận diện trạng thái và kiểm tra version phụ thuộc module.

Ví dụ JPA với hai persistence context độc lập:

~~~text
Ban đầu: dữ liệu lưu trữ có version 4
Luồng A đọc entity với version 4
Luồng B đọc entity với version 4
Luồng A cập nhật thành công, version lưu trữ chuyển sang 5
Luồng B ghi lại entity cũ với version 4
    -> có thể phát hiện xung đột optimistic locking
~~~

Đây không phải lỗi null và cũng không phải kết quả tìm kiếm rỗng. Ứng dụng cần chính sách xử lý xung đột, chẳng hạn thông báo dữ liệu đã thay đổi hoặc thực hiện lại nghiệp vụ khi phù hợp.

Không tự xóa hoặc ghi đè version chỉ để ép một lần lưu đi qua. Version là một phần thông tin mà cơ chế kiểm soát đồng thời sử dụng.

### 7.3. DataIntegrityViolationException: dữ liệu vi phạm ràng buộc

Những ràng buộc như duy nhất, không-null hoặc quan hệ tham chiếu có thể làm thao tác ghi thất bại. Khi được tích hợp và dịch lỗi tương ứng, Spring có thể biểu diễn qua `DataIntegrityViolationException` hoặc lớp liên quan.

Ví dụ một sách có entity không-null nhưng title null có thể thất bại ở provider hoặc kho dữ liệu nếu không bị chặn sớm. Không mặc định mọi module đều ném đúng một lớp exception cho mọi loại vi phạm.

Các kiểm tra ở service giúp phản hồi sớm, nhưng không loại bỏ nhu cầu ràng buộc dữ liệu. Chẳng hạn, hai yêu cầu đồng thời vẫn có thể vượt qua một lần kiểm tra giá trị duy nhất ở ứng dụng trước khi cạnh tranh tại kho lưu trữ.

### 7.4. Lỗi hạ tầng và lỗi cấu hình

Lỗi kết nối, tài nguyên không sẵn có, mapping hoặc cấu hình truy cập dữ liệu có thể phát sinh trong lúc thao tác repository.

Hệ `DataAccessException` của Spring có các nhóm lỗi phù hợp cho nhiều trường hợp truy cập dữ liệu. Tuy nhiên, không phải mọi lỗi cấu hình hoặc lỗi lập trình đều nhất thiết xuất hiện dưới đúng lớp cha đó.

Phân loại theo nguyên nhân gốc, không biến mọi exception xuất hiện gần repository thành một thông báo “dữ liệu không tồn tại”.

## 8. Vì sao không nên catch mọi lỗi rồi trả giá trị rỗng?

Một mẫu gây mất thông tin:

~~~java
public Optional<Book> find(Long id) {
    try {
        return repository.findById(id);
    } catch (Exception exception) {
        return Optional.empty();
    }
}
~~~

Mẫu này làm null đầu vào, mất kết nối và không có sách trở nên giống nhau ở phía bên gọi.

Một mẫu tương tự ở batch:

~~~java
try {
    return repository.saveAll(books);
} catch (Exception exception) {
    return List.of();
}
~~~

Danh sách rỗng khi đó không cho biết batch đầu vào rỗng, toàn bộ thao tác thất bại hay có một phần dữ liệu đã bị ảnh hưởng trong một ngữ cảnh transaction nào đó.

Với `saveAll`, kết quả trả về bình thường có số phần tử tương ứng với đầu vào theo hợp đồng. Tự thay một lỗi bằng danh sách rỗng cho batch không rỗng đã tạo ra một hợp đồng khác nhưng không báo cho bên gọi.

Khi cần chuyển đổi lỗi:

- Giữ sự phân biệt giữa lỗi đầu vào, dữ liệu thiếu, xung đột và lỗi hệ thống.
- Nếu bọc bằng exception ứng dụng, giữ nguyên nhân để có thể điều tra.
- Xác định transaction sẽ được hoàn tất hay rollback theo cơ chế thực tế.
- Không dùng giá trị rỗng để che một lần ghi thất bại.

## 9. Exception có thể xuất hiện vào lúc nào?

### 9.1. Đọc và ghi có cơ chế khác nhau

Một lỗi đầu vào thường được phát hiện khi method được gọi hoặc lúc service kiểm tra tham số.

Với thao tác ghi, thời điểm lỗi không phải lúc nào cũng nằm ngay tại dòng `repository.save(...)`. Trong JPA, thay đổi có thể được kiểm tra hoặc đồng bộ khi flush hoặc khi transaction chuẩn bị commit.

~~~text
Service bắt đầu transaction
    -> save được gọi
    -> tiếp tục thực hiện nghiệp vụ
    -> flush hoặc commit
    -> phát hiện lỗi ràng buộc hoặc xung đột
~~~

Nếu commit diễn ra sau khi method service trả về qua một transaction interceptor, khối try/catch chỉ bao quanh dòng save bên trong method có thể không bắt được lỗi ở thời điểm commit.

### 9.2. Flush không phải commit

Flush đồng bộ thay đổi đang chờ xuống cơ sở dữ liệu theo cơ chế JPA. Nó không tự bảo đảm transaction đã hoàn tất thành công.

Một thao tác đã flush vẫn có thể bị rollback trước khi commit. Không dùng việc “save không ném lỗi ngay” hoặc “đã nhìn thấy SQL” làm bằng chứng duy nhất về kết quả cuối cùng của nghiệp vụ.

### 9.3. Bắt lỗi không tự khôi phục transaction

Nếu một lỗi khiến transaction bị đánh dấu rollback-only, bắt exception rồi tiếp tục thao tác trong cùng transaction không bảo đảm có thể commit các phần còn lại.

Chính sách chuyển đổi lỗi, thử lại hoặc chia transaction phải phù hợp với module và ranh giới nghiệp vụ. Một câu lệnh catch không tạo một transaction mới và không tự xóa trạng thái lỗi của transaction cũ.

## 10. saveAll và deleteAll không tự bảo đảm mọi điều bạn cần

Tên method có chữ “All” cho biết phạm vi đầu vào, không tự cam kết:

- Thực hiện đúng một câu lệnh vật lý.
- Sử dụng batching của driver.
- Có hiệu năng giống nhau trên mọi kho dữ liệu.
- Có một giao dịch nguyên tử chung cho mọi module.
- Kiểm tra hết toàn bộ đầu vào trước khi bắt đầu xử lý.

Với Spring Data JPA được cấu hình thông thường, các method ghi kế thừa có transaction tương ứng. Nếu có transaction bao ngoài, chúng có thể tham gia transaction đó. Nhưng không nên chuyển chi tiết này thành một bảo đảm toàn cục của Commons cho mọi công nghệ.

Khi nghiệp vụ yêu cầu “toàn bộ thành công hoặc không thay đổi gì”, cần xác định transaction manager, ranh giới transaction, hỗ trợ của kho dữ liệu và quy tắc rollback.

Kiểm tra trước toàn bộ batch như service mẫu giúp từ chối phần tử null trước khi gọi repository. Nó không ngăn được lỗi ràng buộc hoặc xung đột xảy ra sau đó.

Cũng phân biệt `deleteAll(entities)` với `deleteAll()` không tham số: method thứ nhất nhận tập cần xóa, còn method thứ hai yêu cầu xóa toàn bộ đối tượng theo phạm vi repository. Tập đầu vào null không phải một cách viết tắt cho “xóa tất cả”.

## 11. Chọn phản ứng ở tầng ứng dụng

| Nguyên nhân | Cách phản ứng có thể phù hợp |
| --- | --- |
| Tham số bắt buộc bị null | Từ chối yêu cầu ở biên phù hợp và chỉ rõ trường cần có. |
| ID hợp lệ nhưng không có đối tượng khi tra cứu tùy chọn | Giữ Optional rỗng cho bên gọi xử lý. |
| Nghiệp vụ yêu cầu đối tượng phải tồn tại | Chuyển vắng mặt thành exception hoặc kết quả nghiệp vụ rõ nghĩa. |
| Xóa theo ID đã thiếu và nghiệp vụ cho phép | Chấp nhận trạng thái không còn dữ liệu theo hợp đồng. |
| Xung đột version | Báo xung đột hoặc thực hiện lại nghiệp vụ theo một chính sách đã xác định. |
| Vi phạm ràng buộc dữ liệu | Phân loại ràng buộc và phản hồi theo hợp đồng ứng dụng. |
| Lỗi hạ tầng | Giữ ý nghĩa lỗi hệ thống và xử lý ở tầng thích hợp. |

Commons không tự quyết định mã HTTP, thông báo giao diện hoặc trạng thái tác vụ nền. Một API có thể ánh xạ tài nguyên không tồn tại thành 404, nhưng đó là hợp đồng API xây dựng bên trên kết quả repository.

Không ánh xạ một lớp exception quá rộng sang một trạng thái duy nhất mà không xét nguồn phát sinh. Ví dụ, IllegalArgumentException do lỗi nội bộ không tự trở thành bằng chứng rằng người dùng đã gửi sai dữ liệu.

## 12. Bảng tình huống thực hành

Khi tự kiểm chứng trong một ứng dụng đã cấu hình, hãy tách các trường hợp:

| Đầu vào hoặc điều kiện | Kết quả cần phân biệt |
| --- | --- |
| `findById(null)` | Vi phạm đầu vào, khác với Optional rỗng. |
| `findById(validMissingId)` | Optional rỗng nếu thao tác đọc hoàn tất bình thường. |
| `existsById(validMissingId)` | false. |
| `save(null)` | Entity đầu vào không hợp lệ. |
| Entity mới có ID null với mapping sinh ID phù hợp | Có thể là thao tác tạo hợp lệ. |
| Entity không-null nhưng title null | Kiểm tra domain hoặc ràng buộc lưu trữ, không đồng nhất với save(null). |
| `saveAll(null)` | Tập đầu vào không hợp lệ. |
| `saveAll` với một phần tử null | Vi phạm điều kiện phần tử; cần xét transaction khi phân tích tác động. |
| `findAllById` với ID tồn tại lẫn ID thiếu | Chỉ có đối tượng tìm được, không có chỗ giữ bằng null. |
| `deleteById` với ID thiếu | Không dùng exception thiếu dữ liệu làm kết quả bắt buộc. |
| Cập nhật entity có version cũ | Có thể phát hiện lỗi optimistic locking. |
| Lỗi kết nối trong lúc đọc | Không được chuyển thành “không có dữ liệu”. |
| Lỗi ràng buộc phát hiện khi commit | Cần quan sát đúng ranh giới transaction, không chỉ dòng save. |

Nếu tạo đầu vào chứa null, hãy chắc rằng exception quan sát được đến từ tầng bạn muốn kiểm tra. Một NPE từ `List.of` không kiểm chứng hợp đồng của `saveAll` hoặc `findAllById`.

## 13. Bài tập vận dụng

### Bài tập 1: Phân loại sáu yêu cầu

Phân loại các tình huống sau thành lỗi đầu vào, vắng mặt hợp lệ, lỗi domain hoặc lỗi thực thi:

1. Tìm một sách bằng ID null.
2. Tìm một sách bằng ID hợp lệ chưa có dữ liệu.
3. Lưu một entity null.
4. Lưu entity không-null nhưng tiêu đề chỉ có khoảng trắng.
5. Lưu bản cập nhật mang version đã cũ.
6. Xóa theo ID hợp lệ của một sách đã bị xóa trước đó.

Với tình huống 4, xác định rõ ứng dụng kiểm tra ở constructor, service hay để ràng buộc lưu trữ phát hiện. Cùng một dữ liệu đầu vào có thể bị chặn ở những tầng khác nhau, nhưng không vì thế mà ba tầng hợp đồng trở thành một.

### Bài tập 2: Sửa một service báo sai dữ liệu thiếu

Một service đang catch mọi Exception từ repository rồi trả Optional rỗng hoặc danh sách rỗng.

Hãy thiết kế lại để dữ liệu thiếu giữ đúng ý nghĩa, null đầu vào bị từ chối rõ ràng và lỗi hạ tầng không bị che. Nếu cần exception nghiệp vụ, chỉ ra chính xác trường hợp nào tạo ra exception đó.

### Bài tập 3: Thiết kế batch có kiểm soát

Với một batch gồm nhiều entity hợp lệ và một entity null ở cuối:

- Xác định cách kiểm tra toàn bộ trước khi gọi repository.
- Xác định nghiệp vụ có yêu cầu atomicity hay không.
- Chỉ ra vì sao bước kiểm tra null trước chưa đủ để bảo đảm không có lỗi khi ghi.
- Xác định nơi cần quan sát exception nếu module có thể trì hoãn ghi đến flush hoặc commit.

Sử dụng CRUD đúng hợp đồng bắt đầu từ việc gọi đúng tên cho từng trạng thái: null vi phạm đầu vào, dữ liệu thiếu là một kết quả được quy định theo method, còn exception thực thi phải được giữ và phân loại theo nguyên nhân. Khi ba phần này rõ ràng, service có thể phản hồi đúng mà không gán trách nhiệm của domain hoặc kho dữ liệu cho Commons.