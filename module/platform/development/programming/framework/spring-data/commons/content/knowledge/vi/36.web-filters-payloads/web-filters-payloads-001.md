# QuerydslPredicateArgumentResolver và @QuerydslPredicate

## 1. Mục tiêu và phạm vi

Trong chương **Bộ lọc và payload web** của module **Spring Data Commons**, Querydsl web support cho phép chuyển các query parameter của HTTP thành một predicate có cấu trúc. Controller có thể nhận predicate rồi chuyển xuống tầng ứng dụng thay vì tự đọc từng chuỗi tham số.

Hai thành phần trung tâm là:

~~~java
org.springframework.data.web.querydsl.QuerydslPredicateArgumentResolver
org.springframework.data.querydsl.binding.QuerydslPredicate
~~~

Resolver tham gia hạ tầng Spring MVC. Annotation giúp xác định domain root và cách binding cho tham số predicate.

Sau bài học, bạn cần làm được:

- Nhận diện đúng predicate của Querydsl và annotation của Spring Data.
- Hiểu quy tắc binding mặc định cho một giá trị, nhiều giá trị và nhiều thuộc tính.
- Khai báo domain root tường minh khi response dùng DTO.
- Giới hạn thuộc tính được lọc bằng QuerydslBindings.
- Kết hợp predicate client với phạm vi truy cập do server quyết định.
- Phân biệt bộ lọc Querydsl với phân trang, sorting và việc bind JSON body.
- Kiểm tra truy vấn thực tế thay vì chỉ quan sát chuỗi biểu thức.

Ví dụ chọn **Spring MVC, Spring Data JPA và Querydsl**, với Java 17 trở lên và một cấu hình JPA dùng namespace Jakarta phù hợp. Phần web binding thuộc Spring Data Commons; khả năng thực thi predicate vẫn phụ thuộc mô-đun lưu trữ.

Không suy ra rằng mọi repository của mọi store đều thực thi được Querydsl chỉ vì interface hoặc annotation có trong dependency.

## 2. Từ request đến truy vấn

Một request tìm sách:

~~~http
GET /books?title=Spring&category=BOOKS&active=true&page=0&size=20
~~~

có thể đi qua luồng sau:

~~~text
Query parameters
        |
        v
QuerydslPredicateArgumentResolver
        |
        +-- Xác định root Book và QBook
        +-- Áp dụng QuerydslBindings
        +-- Chuyển giá trị chuỗi sang kiểu property
        +-- Tạo Querydsl Predicate
        |
        v
Controller nhận Predicate + Pageable
        |
        v
Service ghép phạm vi dữ liệu bắt buộc
        |
        v
Repository thực thi predicate theo hỗ trợ của store
~~~

`page`, `size`, `sort` do cơ chế phân trang/sorting tương ứng xử lý. Chúng không tự biến thành một điều kiện nghiệp vụ trong Querydsl predicate.

Resolver tạo điều kiện. Nó không tự gọi `findAll`, không tự áp quyền người dùng và không tự chọn DTO phản hồi.

## 3. Các điều kiện cần có

### 3.1. Querydsl và Q-type

Domain type cần có đường dẫn Querydsl tương ứng, thường là Q-type được sinh trong quá trình biên dịch:

~~~text
Book -> QBook
~~~

Ví dụ biểu thức type-safe:

~~~java
QBook.book.title.eq("Spring");
QBook.book.price.goe(new BigDecimal("100.00"));
~~~

Q-type giúp tham chiếu tên property và kiểu giá trị bằng Java. Nó không đồng nghĩa mọi biểu thức đều được chấp nhận từ HTTP.

Ứng dụng cần cấu hình annotation processing và các dependency Querydsl tương thích với phiên bản Spring Data, JPA và namespace đang dùng. Với JPA Jakarta, không trộn các thành phần sinh mã dành cho namespace javax vào ví dụ một cách máy móc.

Nếu QBook chưa được sinh hoặc không được đưa vào source set cần thiết, lỗi nằm ở hạ tầng Querydsl trước khi nói đến query parameter.

### 3.2. Spring Data Web support

Ứng dụng phải đăng ký tích hợp Spring Data Web và có các thành phần Querydsl cần thiết trên classpath. Trong cấu hình phù hợp, Spring Data Web có thể bổ sung resolver tương ứng.

Một ứng dụng cấu hình thủ công có thể dùng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration(proxyBeanMethods = false)
@EnableSpringDataWebSupport
class DataWebConfiguration {
}
~~~

Với Spring Boot đang auto-configure hạ tầng này, cần hiểu cấu hình hiện có trước khi thêm annotation thủ công. Mục tiêu là xác nhận resolver thật sự có trong MVC, không phải chồng nhiều cơ chế cấu hình.

Ví dụ của bài dùng MVC. Không mặc định rằng đăng ký một resolver MVC sẽ giải quyết tham số trong WebFlux.

### 3.3. Repository thực thi Querydsl

Trong ví dụ JPA:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface BookRepository
        extends JpaRepository<Book, Long>,
                QuerydslPredicateExecutor<Book> {
}
~~~

`QuerydslPredicateExecutor` cung cấp hợp đồng truy vấn bằng predicate. Store và repository factory tương ứng phải có implementation hỗ trợ.

`QuerydslPredicateArgumentResolver` không tạo implementation executor cho một store vốn không hỗ trợ nó.

## 4. Chữ ký controller và import cần dùng đúng

~~~java
import com.querydsl.core.types.Predicate;

import org.springframework.data.domain.Pageable;
import org.springframework.data.querydsl.binding.QuerydslPredicate;
import org.springframework.data.web.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookSearchController {

    private final BookSearchService service;

    public BookSearchController(BookSearchService service) {
        this.service = service;
    }

    @GetMapping("/books")
    public PagedModel<BookView> search(
            @QuerydslPredicate(root = Book.class) Predicate predicate,
            Pageable pageable) {

        return new PagedModel<>(
                service.search(predicate, pageable));
    }
}
~~~

`PagedModel` trong snippet là DTO trang của Spring Data Web, không phải PagedModel của Spring HATEOAS. Ví dụ cần dòng Spring Data có hỗ trợ lớp này; dự án có hợp đồng response khác có thể thay lớp biểu diễn mà không đổi ý nghĩa predicate.

Ba import dễ nhầm:

| Tên | Import đúng trong ví dụ | Không thay thế bằng |
| --- | --- | --- |
| Predicate | `com.querydsl.core.types.Predicate` | `java.util.function.Predicate` |
| QuerydslPredicate | `org.springframework.data.querydsl.binding.QuerydslPredicate` | Một annotation JPA hoặc annotation validation |
| Pageable | `org.springframework.data.domain.Pageable` | DTO query tự đặt cùng tên |

Predicate Querydsl là một biểu thức truy vấn, không phải một hàm Java nhận object rồi trả boolean.

### 4.1. Vì sao khai báo root = Book.class?

Predicate phải được tạo trên domain có các đường dẫn dùng cho truy vấn.

Controller ở trên trả `PagedModel<BookView>`. Nếu dựa vào việc suy ra kiểu từ chữ ký response, root có thể không phải domain cần truy vấn hoặc không suy ra được theo thiết kế mong muốn.

Khai báo:

~~~java
@QuerydslPredicate(root = Book.class)
~~~

nói rõ các tham số lọc được diễn giải theo `Book`, không phải theo DTO BookView.

Root không phải tên bảng SQL và không phải biểu thức tùy ý từ client.

## 5. Quy tắc binding mặc định cần hiểu trước khi tùy chỉnh

Với binding mặc định và những property được cho phép:

| Property và đầu vào | Ý nghĩa điển hình |
| --- | --- |
| Property scalar, một giá trị | So sánh bằng |
| Property scalar, nhiều giá trị | Thành viên trong tập giá trị, tương đương in |
| Property collection, một giá trị | Điều kiện collection chứa giá trị |
| Nhiều property khác nhau | Kết hợp các điều kiện bằng AND |

Ví dụ:

~~~http
GET /books?category=BOOKS&active=true
~~~

có ý nghĩa gần với:

~~~text
category = 'BOOKS' AND active = true
~~~

Còn:

~~~http
GET /books?category=BOOKS&category=COURSE
~~~

với scalar `category` và binding mặc định có ý nghĩa gần với:

~~~text
category IN ('BOOKS', 'COURSE')
~~~

Điều đó không có nghĩa mọi property lặp đều tạo cùng một phép toán. Binding được tùy chỉnh có thể thay đổi quy tắc.

### 5.1. Chuỗi mặc định không tự là containsIgnoreCase

Nếu chưa có custom binding, không nên mặc định:

~~~http
GET /books?title=Spring
~~~

sẽ tìm được mọi title có chứa từ Spring, không phân biệt hoa thường.

Binding mặc định cho một scalar thường là equality. Muốn contains, prefix hoặc quy tắc khác, cần khai báo rõ.

### 5.2. Không có ngôn ngữ điều kiện tùy ý chỉ từ annotation

Request:

~~~http
GET /books?price.goe=100
~~~

không tự trở thành một hợp đồng “price lớn hơn hoặc bằng 100” chỉ vì Querydsl có phương thức `goe`.

Tên property, alias và cách diễn giải giá trị phải được bindings hỗ trợ. Annotation không cung cấp một ngôn ngữ query tổng quát với OR, ngoặc, toán tử và biểu thức lồng tùy ý.

Khi cần tìm kiếm phức tạp, một DTO bộ lọc hoặc một hợp đồng truy vấn riêng có thể dễ kiểm soát hơn.

## 6. Model minh họa cho ví dụ JPA

Các field cần thiết:

~~~java
import java.math.BigDecimal;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Book {

    @Id
    @GeneratedValue
    private Long id;

    private Long tenantId;
    private String title;
    private String category;
    private boolean active;
    private BigDecimal price;

    protected Book() {
    }

    public Book(
            Long tenantId,
            String title,
            String category,
            boolean active,
            BigDecimal price) {

        this.tenantId = tenantId;
        this.title = title;
        this.category = category;
        this.active = active;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getCategory() {
        return category;
    }

    public boolean isActive() {
        return active;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

QBook được sinh từ model tương ứng. Ví dụ không trình bày migration hoặc chính sách ràng buộc schema của một database cụ thể.

DTO công khai:

~~~java
import java.math.BigDecimal;

public record BookView(
        Long id,
        String title,
        String category,
        boolean active,
        BigDecimal price) {
}
~~~

DTO không cần công bố tenantId chỉ vì entity có property đó.

Mỗi kiểu public ở ví dụ cần một file Java riêng khi triển khai thật. Các snippet là nội dung học tập trong bài, không phải yêu cầu tạo thêm file tại bước viết Markdown này.

## 7. Giới hạn thuộc tính và tùy chỉnh binding tại repository

Một repository có thể cung cấp customizer:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public interface BookRepository
        extends JpaRepository<Book, Long>,
                QuerydslPredicateExecutor<Book>,
                QuerydslBinderCustomizer<QBook> {

    @Override
    default void customize(
            QuerydslBindings bindings, QBook root) {

        bindings.excludeUnlistedProperties(true);
        bindings.including(
                root.title,
                root.category,
                root.active,
                root.price);

        bindings.bind(root.title)
                .first((path, value) ->
                        path.containsIgnoreCase(value));
    }
}
~~~

Đây là khai báo repository đầy đủ thay cho phiên bản đơn giản ở phần trước.

### 7.1. Allowlist làm gì?

Chỉ bốn property được đưa vào hợp đồng lọc:

~~~text
title
category
active
price
~~~

`tenantId` và `id` không nằm trong danh sách được cho phép để tạo predicate từ query parameter trong ví dụ.

Allowlist giúp endpoint không tự công khai mọi property có thể truy cập từ model. Khi entity được bổ sung một field mới, field đó không tự trở thành một bộ lọc công khai theo chính sách này.

Tuy nhiên, allowlist không tự tạo HTTP 400 cho mọi tham số không được bind. Những tham số không được nhận diện hoặc bị loại khỏi binding có thể không đóng góp điều kiện vào predicate.

Do đó:

~~~http
GET /books?tenantId=999
~~~

không được coi là một cơ chế yêu cầu dữ liệu tenant 999. Nhưng việc loại nó khỏi binding cũng chưa đủ để bảo đảm dữ liệu được giới hạn vào tenant của người dùng. Service vẫn cần phạm vi bắt buộc riêng.

### 7.2. Binding title đã thay đổi ý nghĩa request

Sau customizer:

~~~http
GET /books?title=spring
~~~

có ý nghĩa tìm title chứa chuỗi theo quy tắc containsIgnoreCase của Querydsl và khả năng thực thi tương ứng của store.

Không đồng nhất điều đó với một chính sách tìm kiếm ngôn ngữ tự nhiên hoặc bỏ dấu tiếng Việt. Collation và khả năng so sánh chuỗi của database vẫn liên quan đến kết quả thực tế.

### 7.3. first không phải validation “chỉ được gửi một lần”

Đoạn:

~~~java
bindings.bind(root.title).first(...);
~~~

chỉ định binding sử dụng giá trị đầu tiên cho đường dẫn đó.

Nếu client gửi title nhiều lần, không suy ra hệ thống sẽ tự trả HTTP 400:

~~~http
GET /books?title=Spring&title=Kotlin
~~~

Nếu hợp đồng cần từ chối title lặp, phải kiểm tra số lượng giá trị ở biên request bằng một cơ chế thích hợp. Không dùng tên `first` để ngầm cam kết “mọi giá trị đều được kết hợp”.

Ngược lại, `category` chưa có custom binding nên scalar nhiều giá trị vẫn có thể theo quy tắc in mặc định.

### 7.4. Binding một giá trị và binding nhiều giá trị

`first` thuận tiện khi chính sách chỉ dùng một giá trị.

`all` cho phép xử lý tập giá trị và trả về một predicate tùy chỉnh, thường qua `Optional<Predicate>`. Đây là điểm mở rộng khi cần một hợp đồng đa giá trị rõ ràng.

Không viết một binding khoảng giá rồi mặc định hai giá trị bất kỳ luôn là min và max hợp lệ. Cần quyết định số lượng được phép, thứ tự, trường hợp thiếu đầu mút và điều kiện min không lớn hơn max.

Với API có nhiều quy tắc như vậy, một DTO bộ lọc tường minh có thể giúp kiểm tra dễ hơn việc dồn mọi logic vào bindings.

## 8. Chỉ định customizer riêng tại endpoint

Nếu nhiều endpoint truy vấn cùng domain nhưng có hợp đồng lọc khác nhau, có thể chỉ định loại customizer qua annotation:

~~~java
@QuerydslPredicate(
        root = Book.class,
        bindings = PublicBookBindings.class)
Predicate predicate
~~~

Ví dụ một policy chỉ cho title và category:

~~~java
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public class PublicBookBindings
        implements QuerydslBinderCustomizer<QBook> {

    @Override
    public void customize(
            QuerydslBindings bindings, QBook root) {

        bindings.excludeUnlistedProperties(true);
        bindings.including(root.title, root.category);

        bindings.bind(root.title)
                .first((path, value) ->
                        path.containsIgnoreCase(value));
    }
}
~~~

Ứng dụng cần để hạ tầng binding tạo hoặc lấy được customizer theo cơ chế cấu hình đang dùng. Class ví dụ không có dependency và có constructor mặc định.

Chọn rõ nơi định nghĩa chính sách. Khi chỉ định customizer tường minh, không mặc định mọi customizer repository và endpoint sẽ tự được hợp nhất theo đúng mong muốn.

Nếu muốn tái sử dụng một policy nền, hãy tổ chức việc tái sử dụng trong code và kiểm tra kết quả binding thay vì dựa vào một thứ tự cấu hình chưa được xác nhận.

## 9. Predicate của client phải được ghép với điều kiện bắt buộc của server

Giả sử người dùng chỉ được xem dữ liệu tenant hiện tại.

Một abstraction lấy tenant từ ngữ cảnh đã xác thực:

~~~java
public interface CurrentTenant {
    long requiredTenantId();
}
~~~

Implementation phải lấy phạm vi từ cơ chế xác thực/ủy quyền của ứng dụng, không coi một query parameter tenantId là bằng chứng quyền truy cập.

Service:

~~~java
import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookSearchService {

    private final BookRepository books;
    private final CurrentTenant currentTenant;

    public BookSearchService(
            BookRepository books,
            CurrentTenant currentTenant) {

        this.books = books;
        this.currentTenant = currentTenant;
    }

    @Transactional(readOnly = true)
    public Page<BookView> search(
            Predicate clientPredicate,
            Pageable pageable) {

        long tenantId = currentTenant.requiredTenantId();

        BooleanBuilder scoped = new BooleanBuilder(
                QBook.book.tenantId.eq(tenantId));

        if (clientPredicate != null) {
            scoped.and(clientPredicate);
        }

        return books.findAll(scoped, pageable)
                .map(book -> new BookView(
                        book.getId(),
                        book.getTitle(),
                        book.getCategory(),
                        book.isActive(),
                        book.getPrice()));
    }
}
~~~

Ý nghĩa cuối cùng là:

~~~text
tenantId = tenant hiện tại
AND
các bộ lọc client được cho phép
~~~

Không dùng OR để ghép điều kiện tenant với predicate client:

~~~text
tenantId = tenant hiện tại OR title chứa 'Spring'
~~~

Biểu thức đó có thể lấy sách ngoài tenant chỉ vì title khớp.

Ví dụ service tập trung vào việc ghép phạm vi và ánh xạ DTO. Ứng dụng vẫn cần chính sách Pageable/Sort phù hợp trước khi gọi truy vấn.

### 9.1. Request không có bộ lọc

Một request không có điều kiện được bind có thể tạo predicate rỗng. Tùy đường gọi, code cũng có thể nhận giá trị không có điều kiện hữu hiệu.

Không dùng “predicate rỗng” để suy ra người dùng đã bị từ chối truy cập. Nếu truyền một predicate rỗng trực tiếp cho truy vấn không có điều kiện bắt buộc, nó có thể tương đương việc không lọc tập dữ liệu.

Service ví dụ luôn bắt đầu từ điều kiện tenant. Khi không có bộ lọc client, phạm vi vẫn còn:

~~~text
tenantId = tenant hiện tại
~~~

### 9.2. Allowlist lọc không giới hạn Sort

Các property được đưa vào QuerydslBindings kiểm soát predicate. Chúng không đồng thời tạo allowlist cho:

~~~http
GET /books?sort=tenantId,asc
~~~

Sort đi qua cơ chế khác. Nếu chỉ cho sắp xếp theo title, price và id, cần kiểm tra Sort theo policy đó trước khi truy vấn.

Tương tự, cần giới hạn page size, cân nhắc độ sâu offset và có một thứ tự ổn định phù hợp. Annotation QuerydslPredicate không tự thực hiện các chính sách này.

## 10. Chuyển kiểu, đầu vào sai và tham số không được bind

### 10.1. Chuyển kiểu dựa trên property

Với property active kiểu boolean và price kiểu BigDecimal:

~~~http
GET /books?active=true&price=120.00
~~~

resolver và hạ tầng chuyển đổi tương ứng tạo giá trị theo kiểu property trước khi binding.

Không phải mọi giá trị chuỗi đều hợp lệ:

~~~http
GET /books?price=not-a-number
~~~

Ứng dụng cần có chính sách chuyển lỗi chuyển đổi thành phản hồi client phù hợp, thường là HTTP 400 với định dạng ổn định.

Không mặc định một `@RestControllerAdvice` chỉ bắt một loại lỗi phổ biến của `@RequestParam` sẽ bắt đúng mọi lỗi xuất phát từ Querydsl binding. Cần kiểm tra loại exception thực tế ở đường resolver và cấu hình đang dùng.

Không catch toàn bộ Exception rồi trả một danh sách rỗng; cách đó che cả lỗi query, lỗi kết nối và lỗi lập trình thành “không có kết quả”.

### 10.2. Rỗng không tự có nghĩa là IS NULL

~~~http
GET /books?title=
~~~

không tự công bố một hợp đồng tìm title NULL.

Tương tự, việc không gửi title thường biểu đạt “không áp dụng bộ lọc title”, không phải “title phải bằng NULL”.

Nếu API cần lọc NULL, blank hoặc missing theo những nghĩa khác nhau, hãy thiết kế tham số và binding rõ ràng rồi kiểm tra từng trường hợp.

### 10.3. Validation nghiệp vụ không tự xuất hiện

Chuyển price thành BigDecimal không tự kiểm tra price không âm. QuerydslPredicate cũng không tự bảo đảm một category thuộc danh mục được ứng dụng cho phép.

Cần phân biệt:

| Loại kiểm tra | Ví dụ |
| --- | --- |
| Cú pháp/chuyển kiểu | price có chuyển thành BigDecimal được không |
| Miền đầu vào | price có âm không |
| Hợp đồng query | title có được lặp không |
| Phạm vi dữ liệu | người dùng được xem tenant nào |
| Năng lực store | predicate có được mô-đun thực thi không |

Nếu hợp đồng trở nên phức tạp, controller nhận một DTO tìm kiếm rồi service chủ động xây predicate có thể phù hợp hơn.

### 10.4. Tham số lạ có thể làm request rộng hơn client nghĩ

Ví dụ client gõ sai:

~~~http
GET /books?catgory=BOOKS
~~~

Nếu tên này không được bind và không có cơ chế từ chối tham số lạ, query có thể chạy mà không có bộ lọc category.

Allowlist bảo vệ những property được phép sử dụng, nhưng không phải bộ xác thực toàn bộ query string.

Nếu API cần strict contract, hãy kiểm tra tên query parameter được phép, đồng thời giữ page/size/sort và các tham số nghiệp vụ hợp lệ trong danh sách tương ứng.

## 11. Ví dụ kết quả để kiểm tra ngữ nghĩa

Giả sử dữ liệu kiểm tra:

| Id | Tenant | Title | Category | Active | Price |
| --- | --- | --- | --- | --- | --- |
| 1 | A | Spring Data căn bản | BOOKS | true | 120.00 |
| 2 | A | Spring MVC thực hành | BOOKS | true | 90.00 |
| 3 | A | Spring Data nâng cao | COURSE | false | 120.00 |
| 4 | B | Spring Data căn bản | BOOKS | true | 120.00 |

Người dùng hiện tại thuộc tenant A, bindings title dùng containsIgnoreCase như ví dụ.

| Query | Kết quả kỳ vọng theo bộ lọc và phạm vi |
| --- | --- |
| Không có bộ lọc | Id 1, 2, 3 |
| `title=Spring&category=BOOKS&active=true` | Id 1, 2 |
| `title=Spring&category=BOOKS&active=true&price=120.00` | Id 1 |
| `category=BOOKS&category=COURSE` | Id 1, 2, 3 |
| `active=false` | Id 3 |
| `title=không-tồn-tại` | Không có kết quả |
| `tenantId=B` | Không được mở phạm vi sang tenant B |

Ở dòng cuối, tenantId bị loại khỏi binding trong policy ví dụ. Không khẳng định request tự trả 400; nếu chưa có strict parameter validation, phạm vi truy vấn vẫn phải được server giữ tại tenant A.

Thứ tự các id trong bảng là tập kết quả kỳ vọng, không phải cam kết thứ tự query. Muốn assert một danh sách theo thứ tự, cần Sort xác định.

## 12. Kiểm tra theo từng lớp

### 12.1. Kiểm tra binding

Cần xác minh:

- Root được chọn là Book.
- Title dùng containsIgnoreCase.
- Category lặp đi theo quy tắc nhiều giá trị đã công bố.
- TenantId không được client bind.
- Endpoint có customizer riêng chỉ công khai đúng property của nó.
- Giá trị đầu vào sai không bị âm thầm biến thành một truy vấn rộng ngoài hợp đồng.

Không dùng riêng `predicate.toString()` làm bằng chứng đầy đủ về query thực thi. Chuỗi biểu thức không kiểm tra được mapping, collation hay khả năng của store.

### 12.2. Kiểm tra MVC

Một request minh họa:

~~~java
mockMvc.perform(get("/books")
        .param("title", "Spring")
        .param("category", "BOOKS")
        .param("active", "true")
        .param("page", "0")
        .param("size", "20"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.content").isArray());
~~~

Snippet giả định MockMvc, service và các import kiểm tra đã được cấu hình. Chỉ assert mảng content chưa đủ chứng minh predicate đúng.

Cần cấu hình MVC thực sự có Querydsl resolver và binding factory. Một test standalone thiếu resolver không đại diện cho đường request trong ứng dụng.

Với mock service, có thể kiểm tra predicate và Pageable được truyền xuống. Tuy nhiên, mock không chứng minh repository thực thi predicate đúng trên database.

### 12.3. Kiểm tra tích hợp store

Dùng fixture như bảng trên và thực hiện request hoặc gọi đường truy vấn phù hợp để xác minh tập id:

- Người dùng A không nhận id 4 trong mọi biến thể bộ lọc.
- Không có bộ lọc vẫn giữ tenant A.
- Nhiều property được kết hợp bằng AND.
- Nhiều category hoạt động đúng hợp đồng.
- Tổng số và nội dung Page đều phù hợp với predicate đã scope.
- DTO không công bố field ngoài hợp đồng.

Kiểm tra thêm cú pháp sai, tham số lặp và tham số bị bỏ qua theo policy của API. Không coi một HTTP 200 là bằng chứng mọi tham số đều đã được áp dụng.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Predicate không được phân giải | Thiếu tích hợp web hoặc Querydsl | Kiểm tra resolver trong cấu hình MVC |
| Không tìm thấy QBook | Q-type chưa được sinh/đưa vào build | Sửa cấu hình sinh mã của dự án |
| Không suy ra root mong muốn | Chữ ký response dùng DTO hoặc kiểu bọc | Khai báo root tường minh |
| Predicate không có kiểu đúng | Import java.util.function.Predicate | Dùng Predicate của Querydsl |
| Title chỉ khớp đúng toàn chuỗi | Đang dùng binding equality mặc định | Khai báo contains/prefix theo hợp đồng |
| Title lặp không tạo OR | Customizer dùng first | Công bố hoặc thay quy tắc đa giá trị |
| Query có nhiều trường ngoài dự kiến | Property chưa được giới hạn | Dùng allowlist |
| Gõ sai query nhưng vẫn 200 | Tham số không được bind bị bỏ qua | Thêm strict parameter validation nếu cần |
| Sort vẫn dùng property ngoài allowlist | Nhầm QuerydslBindings với Sort policy | Kiểm tra Sort độc lập |
| Không lọc thấy toàn bộ dữ liệu | Predicate rỗng được dùng không có scope | Ghép điều kiện bắt buộc tại server |
| Client đổi được phạm vi tenant | Dùng query parameter như quyền truy cập | Lấy scope từ ngữ cảnh đã xác thực |
| Mô-đun không thực thi được predicate | Suy năng lực store từ API Commons | Chọn executor/template được store hỗ trợ |

## 14. Bài thực hành

1. Tạo domain sách và bảo đảm Q-type được sinh trong cấu hình dự án tương thích.
2. Khai báo repository Querydsl cho một mô-đun có hỗ trợ thực thi.
3. Tạo endpoint nhận `@QuerydslPredicate(root = Book.class) Predicate` cùng Pageable.
4. Chỉ cho phép lọc title, category, active và price.
5. Đổi title thành containsIgnoreCase và mô tả rõ cách xử lý title lặp.
6. Ghép điều kiện tenant tại service bằng AND trước khi truy vấn.
7. Kiểm tra request không có filter, filter nhiều thuộc tính và category nhiều giá trị.
8. Phân biệt tham số không được bind, lỗi chuyển kiểu và lỗi nghiệp vụ.
9. Giới hạn Sort và page size bằng chính sách riêng.
10. Giải thích khi nào nên chuyển sang DTO bộ lọc do ứng dụng chủ động xử lý.

Bài thực hành đạt yêu cầu khi bạn chứng minh được **request tạo predicate theo binding đã công bố**, **client chỉ dùng các property được cho phép**, và **mọi truy vấn vẫn giữ phạm vi dữ liệu do server quyết định**.
