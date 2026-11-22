# Quan hệ giữa MVC và Hexagonal Architecture

Trong module **MODEL_VIEW_CONTROLLER**, MVC giúp tổ chức phần tương tác của ứng dụng thành Model, View và Controller. Khi ứng dụng lớn hơn, một câu hỏi thường xuất hiện: làm thế nào để phần nghiệp vụ không phụ thuộc chặt vào Spring MVC, template engine, database hoặc dịch vụ bên ngoài? **Hexagonal Architecture** (kiến trúc lục giác, còn gọi là Ports and Adapters) giải quyết mối quan tâm đó bằng cách đặt lõi ứng dụng ở trung tâm và buộc các công nghệ bên ngoài giao tiếp với lõi qua các cổng (port).

MVC và Hexagonal Architecture giải quyết hai trục thiết kế khác nhau và có thể kết hợp. MVC tổ chức cách ứng dụng tiếp nhận tương tác và trình bày kết quả; Hexagonal Architecture tổ chức ranh giới phụ thuộc giữa lõi nghiệp vụ với các tác nhân và hệ thống bên ngoài. Bài học này làm rõ vai trò của từng mô hình, cách ánh xạ Controller và View thành adapter, cách thiết kế port, luồng request trong ứng dụng Spring MVC và cách kiểm thử từng ranh giới.

## 1. Hai mô hình giải quyết hai vấn đề khác nhau

MVC là một mẫu tổ chức giao diện và luồng tương tác. Nó tách trách nhiệm tiếp nhận hành động, quản lý dữ liệu phục vụ giao diện và trình bày kết quả. Hexagonal Architecture là một cách tổ chức kiến trúc ứng dụng nhằm bảo vệ lõi nghiệp vụ khỏi phụ thuộc vào công nghệ bên ngoài.

| Góc nhìn | MVC | Hexagonal Architecture |
|---|---|---|
| Câu hỏi chính | Ai nhận tương tác, điều phối và hiển thị? | Lõi ứng dụng giao tiếp với bên ngoài qua ranh giới nào? |
| Phạm vi | Chủ yếu là luồng giao diện/request | Toàn bộ ứng dụng và các tích hợp |
| Thành phần chính | Model, View, Controller | Core, Port, Adapter |
| Trọng tâm | Phân tách tiếp nhận tương tác và trình bày | Đảo chiều phụ thuộc, cô lập nghiệp vụ |
| Đối tượng bên ngoài | Người dùng qua giao diện | Người dùng, database, message broker, API, filesystem, scheduler |
| Lợi ích nổi bật | Controller và View rõ trách nhiệm | Có thể thay adapter mà ít ảnh hưởng lõi |
| Kiểm thử tiêu biểu | Controller, View và luồng request | Use case qua port, adapter và hợp đồng tích hợp |

Một ứng dụng có thể dùng MVC mà không có Hexagonal Architecture. Ví dụ, Controller gọi trực tiếp service, service gọi repository của Spring Data, entity JPA được truyền thẳng sang template. Cách này có thể đủ cho ứng dụng nhỏ, nhưng phần nghiệp vụ dần phụ thuộc framework và cấu trúc lưu trữ.

Một ứng dụng cũng có thể dùng Hexagonal Architecture mà không dùng MVC. Ví dụ, một worker xử lý message hoặc một ứng dụng dòng lệnh có adapter đầu vào riêng, gọi use case trong lõi và ghi kết quả qua adapter đầu ra.

Khi ứng dụng web cần cả luồng MVC rõ ràng và lõi nghiệp vụ độc lập, hai cách tổ chức có thể bổ trợ cho nhau.

## 2. Hiểu đúng Model trong MVC

Từ Model trong MVC dễ gây nhầm lẫn vì mỗi framework và tài liệu có thể dùng nó theo phạm vi khác nhau. Trong ứng dụng web, Model có thể chỉ dữ liệu mà Controller đưa cho View; trong thiết kế ứng dụng, từ này đôi khi được dùng để nói đến domain model, application model hoặc toàn bộ phần dữ liệu/nghiệp vụ.

Không nên mặc định rằng **MVC Model chính là Hexagonal Core**.

Một ứng dụng có thể có nhiều loại model:

- **Domain Model:** biểu diễn khái niệm, trạng thái và quy tắc nghiệp vụ.
- **Application Model:** biểu diễn ca sử dụng, command, query và kết quả xử lý.
- **Persistence Model:** cấu trúc entity hoặc record phục vụ lưu trữ.
- **Request DTO:** dữ liệu đầu vào được binding từ HTTP.
- **ViewModel:** dữ liệu được chuẩn bị riêng cho một màn hình hoặc template.
- **Response DTO:** hợp đồng dữ liệu trả về qua API.

Các loại này có thể được ánh xạ qua lại. Chúng không nhất thiết là cùng một lớp Java.

### 2.1. Vì sao không nên đưa mọi thứ vào một Model?

Nếu một lớp vừa là JPA entity, vừa là request object, vừa chứa logic nghiệp vụ và được đưa thẳng vào View, nó có thể tích lũy nhiều trách nhiệm:

- Annotation của persistence làm lõi phụ thuộc JPA.
- Field được gửi từ client có thể bị binding ngoài ý muốn.
- View phụ thuộc cấu trúc bảng hoặc quan hệ entity.
- Thay đổi template có thể làm thay đổi hợp đồng API.
- Quy tắc nghiệp vụ khó kiểm thử độc lập với database.
- Entity có thể bị serialize đệ quy qua quan hệ hai chiều hoặc lộ field nội bộ.

Hexagonal Architecture khuyến khích phân biệt lõi nghiệp vụ với adapter. Trong MVC, ViewModel và Request DTO giúp phần trình bày có hợp đồng riêng, còn domain model giữ ngữ nghĩa nghiệp vụ.

## 3. Cấu trúc cơ bản của Hexagonal Architecture

Hexagonal Architecture thường được mô tả bằng ba khái niệm:

- **Core:** phần ứng dụng và nghiệp vụ cần được bảo vệ khỏi chi tiết bên ngoài.
- **Port:** giao diện mô tả cách lõi nhận yêu cầu hoặc cần một khả năng từ bên ngoài.
- **Adapter:** thành phần chuyển đổi giao thức/công nghệ cụ thể thành lời gọi port hoặc triển khai port mà lõi cần.

Tên “lục giác” là cách vẽ khái niệm, không yêu cầu hệ thống phải có đúng sáu cạnh hoặc sáu adapter. Một ứng dụng có thể có nhiều adapter đầu vào và đầu ra.

### 3.1. Port đầu vào và port đầu ra

**Inbound port (primary/driving port)** mô tả hành động mà ứng dụng cho phép tác nhân bên ngoài yêu cầu. Ví dụ:

- Đăng ký thành viên.
- Tìm kiếm sách.
- Đặt đơn hàng.
- Hủy lịch hẹn.
- Tạo báo cáo.

**Outbound port (secondary/driven port)** mô tả khả năng mà use case cần từ môi trường bên ngoài. Ví dụ:

- Tìm thành viên trong kho dữ liệu.
- Lưu đơn hàng.
- Gửi email.
- Đọc tỷ giá từ dịch vụ ngoài.
- Phát message lên broker.

| Port | Ai định nghĩa? | Ai gọi/triển khai? | Ví dụ |
|---|---|---|---|
| Inbound port | Lõi ứng dụng | Adapter đầu vào gọi; application service triển khai | RegisterMemberUseCase |
| Outbound port | Lõi ứng dụng | Application service gọi; adapter hạ tầng triển khai | SaveMemberPort |

Điểm quan trọng là interface của port thuộc về phía lõi cần khả năng đó. Adapter phụ thuộc vào hợp đồng này và triển khai chi tiết kỹ thuật.

### 3.2. Dependency direction

Các adapter biết về port và gọi vào lõi. Lõi không import Controller, Spring MVC, Thymeleaf, JPA repository hoặc client của nhà cung cấp dịch vụ bên ngoài.

~~~mermaid
flowchart TB
    subgraph Outside["Tác nhân và công nghệ bên ngoài"]
      Browser["Browser"]
      REST["REST Client"]
      DB["Database"]
      Mail["Email Provider"]
      Broker["Message Broker"]
    end

    subgraph Adapters["Adapters"]
      Web["MVC Controller"]
      Api["REST Adapter"]
      Jpa["JPA Repository Adapter"]
      Email["Email Adapter"]
      Events["Message Adapter"]
    end

    subgraph Core["Application Core"]
      InPort["Inbound Ports / Use Cases"]
      App["Application Services"]
      Domain["Domain Model"]
      OutPort["Outbound Ports"]
      InPort --> App
      App --> Domain
      App --> OutPort
    end

    Browser --> Web
    REST --> Api
    Web --> InPort
    Api --> InPort
    OutPort --> Jpa
    OutPort --> Email
    OutPort --> Events
    Jpa --> DB
    Email --> Mail
    Events --> Broker
~~~

Sơ đồ thể hiện hướng giao tiếp ở mức khái niệm. Trong mã nguồn, interface port được khai báo ở lõi; adapter triển khai interface đó. Mũi tên phụ thuộc mã nguồn hướng từ adapter vào abstraction thuộc lõi, dù lời gọi lúc chạy có thể đi từ service đến adapter thông qua interface.

### 3.3. Dependency Inversion Principle

Dependency Inversion Principle (DIP) khuyến khích module cấp cao và module cấp thấp cùng phụ thuộc vào abstraction; abstraction không phụ thuộc chi tiết triển khai. Hexagonal Architecture áp dụng nguyên tắc này ở ranh giới tích hợp.

Ví dụ, use case cần lưu sách. Nó phụ thuộc vào interface SaveBookPort. Adapter JPA triển khai interface đó bằng Spring Data và EntityManager. Nếu chuyển database hoặc ORM, use case vẫn gọi cùng port khi hợp đồng nghiệp vụ không đổi.

DIP không có nghĩa phải tạo interface cho mọi class. Port nên đại diện cho nhu cầu có ý nghĩa của lõi, không phải bản sao máy móc của mọi method trong framework repository.

## 4. Ánh xạ MVC vào Hexagonal Architecture

Trong một ứng dụng server-rendered MVC, có thể ánh xạ các thành phần như sau:

| Thành phần MVC | Vai trò trong Hexagonal Architecture | Ghi chú |
|---|---|---|
| Browser/form | Driving actor | Tác nhân khởi tạo request |
| Controller | Inbound adapter | Chuyển HTTP/form thành lời gọi use case |
| Inbound port | Application contract | Mô tả ca sử dụng lõi cung cấp |
| Application service | Use case implementation | Điều phối nghiệp vụ và port đầu ra |
| Domain model | Business core | Giữ quy tắc và bất biến nghiệp vụ |
| Outbound port | Required capability | Lõi khai báo nhu cầu lưu trữ/gửi message |
| JPA repository adapter | Outbound adapter | Chuyển port thành thao tác persistence |
| ViewModel + View renderer | Presentation/output adapter | Chuyển kết quả use case thành giao diện |
| Template engine | Công nghệ trình bày | Chi tiết ngoài lõi |

Controller là adapter đầu vào của web. Nó không phải nơi chứa toàn bộ nghiệp vụ. View là một phần của adapter trình bày: nó render dữ liệu được chuẩn bị cho giao diện. Application service không nên biết template đang dùng là Thymeleaf, JSP hay một UI khác.

### 4.1. Controller không đồng nghĩa inbound port

Controller là một adapter cụ thể cho HTTP. Inbound port là hợp đồng ca sử dụng. Một use case có thể được gọi từ nhiều adapter:

- MVC Controller cho form HTML.
- REST Controller cho API.
- Message consumer cho sự kiện.
- CLI adapter cho thao tác quản trị.
- Scheduled job cho tác vụ định kỳ.

Các adapter có thể gọi cùng inbound port mà không phải sao chép logic nghiệp vụ.

### 4.2. View không phải domain core

View nhận dữ liệu để trình bày. Nó có thể dùng ViewModel chứa chuỗi đã định dạng, nhãn, trạng thái hiển thị và các lựa chọn cho form. Những dữ liệu này phục vụ giao diện, không nên trở thành nguồn có thẩm quyền cho nghiệp vụ.

Ví dụ, ViewModel có thể chứa canCancelOrder để quyết định có hiển thị nút hủy. Nhưng khi người dùng gửi request hủy, use case vẫn phải kiểm tra quyền và trạng thái đơn hàng ở server. Việc nút bị ẩn không bảo đảm người dùng không thể gọi endpoint.

### 4.3. MVC có thể là một adapter trong nhiều adapter

Nếu ứng dụng có web HTML và REST API, cả hai đều là adapter đầu vào. Nếu có worker nhận message, worker cũng là adapter đầu vào. Các adapter này có thể dùng chung application service và domain model.

Điều này giúp phần nghiệp vụ không bị khóa vào một giao diện. Một use case tạo đơn hàng có thể được gọi từ trang checkout, API đối tác hoặc quy trình nội bộ với cùng quy tắc cốt lõi.

## 5. Luồng request khi kết hợp MVC và Hexagonal Architecture

Xét chức năng tìm kiếm sách. Người dùng gửi bộ lọc từ trang HTML; Controller binding tham số và gọi inbound port; use case áp dụng quy tắc và gọi outbound port để truy vấn; adapter JPA chuyển truy vấn sang database; kết quả được chuyển thành ViewModel để template render.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Browser
    participant Controller as MVC Controller
    participant InPort as SearchBooksUseCase
    participant Service as SearchBooksService
    participant OutPort as LoadBooksPort
    participant Adapter as JPA Adapter
    participant DB as Database
    participant View as Template View

    User->>Browser: Nhập từ khóa và gửi form
    Browser->>Controller: GET /books?keyword=java
    Controller->>Controller: Binding và validation
    Controller->>InPort: search(query)
    InPort->>Service: Thực thi use case
    Service->>OutPort: load(criteria)
    OutPort->>Adapter: Gọi qua interface
    Adapter->>DB: Truy vấn có tham số
    DB-->>Adapter: Kết quả
    Adapter-->>Service: Book summaries
    Service-->>Controller: Use case result
    Controller->>View: ViewModel
    View-->>Browser: HTML
    Browser-->>User: Hiển thị kết quả
~~~

Ở thời điểm biên dịch, Service chỉ biết outbound port. Adapter JPA được nối vào qua dependency injection ở composition root hoặc cấu hình ứng dụng. Việc thay adapter không buộc sửa logic use case nếu port vẫn mô tả đúng nhu cầu.

## 6. Ví dụ thiết kế port và use case bằng Java

Ví dụ dưới đây dùng tìm kiếm sách để minh họa. Các đoạn mã được chia theo trách nhiệm; một dự án thực tế có thể bổ sung kiểu dữ liệu, xử lý lỗi và validation chi tiết hơn.

### 6.1. Inbound port

Inbound port mô tả chức năng ứng dụng cung cấp:

~~~java
public interface SearchBooksUseCase {
    SearchBooksResult search(SearchBooksQuery query);
}

public record SearchBooksQuery(
    String keyword,
    int page,
    int size
) {}

public record SearchBooksResult(
    List<BookSummary> items,
    int page,
    int size,
    boolean hasNext
) {}

public record BookSummary(
    UUID id,
    String title,
    String authorName
) {}
~~~

Query và result thuộc hợp đồng ứng dụng. Chúng không cần chứa HttpServletRequest, Model của Spring MVC hoặc PageRequest của Spring Data. Nhờ vậy, inbound port có thể được gọi từ adapter khác.

### 6.2. Outbound port

Use case cần một khả năng đọc sách. Lõi định nghĩa port theo nhu cầu đó:

~~~java
public interface LoadBooksPort {
    List<BookSummary> load(BookSearchCriteria criteria);
}

public record BookSearchCriteria(
    String keyword,
    int offset,
    int limit
) {}
~~~

Trong ứng dụng lớn, port có thể trả về Slice hoặc một cấu trúc page nội bộ để truyền metadata. Không nhất thiết phải dùng cùng kiểu Page của Spring Data trong core vì nó có thể kéo dependency framework vào lõi.

### 6.3. Application service triển khai inbound port

~~~java
public class SearchBooksService implements SearchBooksUseCase {
    private final LoadBooksPort loadBooks;

    public SearchBooksService(LoadBooksPort loadBooks) {
        this.loadBooks = loadBooks;
    }

    @Override
    public SearchBooksResult search(SearchBooksQuery query) {
        int page = Math.max(query.page(), 0);
        int size = Math.min(Math.max(query.size(), 1), 100);
        int offset = Math.multiplyExact(page, size);

        var criteria = new BookSearchCriteria(
            normalize(query.keyword()),
            offset,
            size + 1
        );

        var loaded = loadBooks.load(criteria);
        boolean hasNext = loaded.size() > size;

        var items = loaded.stream()
            .limit(size)
            .toList();

        return new SearchBooksResult(items, page, size, hasNext);
    }

    private String normalize(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return null;
        }
        return keyword.trim();
    }
}
~~~

Service chuẩn hóa query, áp dụng giới hạn và xác định hasNext. Trong ví dụ, port yêu cầu thêm một dòng để phát hiện trang tiếp theo. Với offset rất sâu hoặc feed lớn, có thể thay bằng keyset cursor. Trong hệ thống thực tế, cần kiểm tra overflow của offset và xác định cách xử lý tham số ngoài giới hạn theo hợp đồng API.

### 6.4. Outbound adapter dùng Spring Data JPA

Adapter triển khai port bằng công nghệ persistence:

~~~java
@Repository
public class JpaLoadBooksAdapter implements LoadBooksPort {
    private final BookJpaRepository repository;

    public JpaLoadBooksAdapter(BookJpaRepository repository) {
        this.repository = repository;
    }

    @Override
    public List<BookSummary> load(BookSearchCriteria criteria) {
        return repository.searchSummaries(
            criteria.keyword(),
            criteria.offset(),
            criteria.limit()
        );
    }
}
~~~

Adapter gọi custom repository để áp dụng offset và limit trực tiếp. Chi tiết Spring Data, EntityManager hoặc SQL nằm trong adapter, không đi vào application service.

Ví dụ custom repository:

~~~java
@Repository
public class BookSearchJpaRepository {
    @PersistenceContext
    private EntityManager entityManager;

    public List<BookSummary> searchSummaries(
        String keyword,
        int offset,
        int limit
    ) {
        var query = entityManager.createQuery("""
            select new com.example.books.BookSummary(
                b.id, b.title, b.authorName
            )
            from BookJpaEntity b
            where (:keyword is null
                or lower(b.title) like lower(concat('%', :keyword, '%')))
            order by b.title asc, b.id asc
            """, BookSummary.class);

        query.setParameter("keyword", keyword);
        query.setFirstResult(offset);
        query.setMaxResults(limit);
        return query.getResultList();
    }
}
~~~

Tên package và projection constructor cần khớp với dự án. Trong thực tế, cần escape wildcard nếu tìm kiếm nguyên văn, áp dụng tenant/authorization scope trong query và xác nhận cú pháp JPQL của phiên bản framework.

### 6.5. MVC Controller gọi inbound port

Controller không cần biết adapter JPA hoặc entity persistence:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final SearchBooksUseCase searchBooks;

    public BookController(SearchBooksUseCase searchBooks) {
        this.searchBooks = searchBooks;
    }

    @GetMapping
    public String list(
        @RequestParam(defaultValue = "") String keyword,
        @RequestParam(defaultValue = "0") int page,
        Model model
    ) {
        var result = searchBooks.search(
            new SearchBooksQuery(keyword, page, 20)
        );

        var viewModel = new BookListViewModel(
            result.items(),
            result.page(),
            result.hasNext(),
            keyword
        );

        model.addAttribute("books", viewModel);
        return "books/list";
    }
}
~~~

Controller là inbound adapter chuyển HTTP sang hợp đồng use case. Nó có thể binding, validation và ánh xạ lỗi HTTP; không tự viết truy vấn hoặc chứa quy tắc nghiệp vụ của tìm kiếm.

### 6.6. ViewModel và View

ViewModel có cấu trúc phục vụ template:

~~~java
public record BookListViewModel(
    List<BookSummary> items,
    int currentPage,
    boolean hasNext,
    String keyword
) {}
~~~

Template render danh sách và liên kết điều hướng:

~~~html
<h1>Danh sách sách</h1>

<form method="get" action="/books">
  <label for="keyword">Từ khóa</label>
  <input id="keyword" name="keyword" value="java" />
  <button type="submit">Tìm kiếm</button>
</form>

<ul>
  <li>Thiết kế hệ thống</li>
  <li>Lập trình Java</li>
</ul>
~~~

Ví dụ HTML chỉ minh họa cấu trúc. Trong template thật, giá trị input và danh sách được bind từ ViewModel; template engine cần escape output phù hợp. View không truy cập repository hoặc gọi trực tiếp domain service.

## 7. Ranh giới giữa DTO, Domain Model và Persistence Model

Kết hợp MVC với Hexagonal Architecture thường cần mapping giữa nhiều kiểu dữ liệu. Đây không phải sự trùng lặp vô ích nếu mỗi kiểu bảo vệ một ranh giới khác nhau.

| Kiểu dữ liệu | Thuộc về | Mục đích | Ví dụ |
|---|---|---|---|
| Request DTO | Web adapter | Binding dữ liệu HTTP | SearchBooksRequest |
| Inbound query/command | Application core | Hợp đồng gọi use case | SearchBooksQuery |
| Domain entity/value object | Domain core | Trạng thái và quy tắc nghiệp vụ | Book, ISBN |
| Outbound result/record | Application port | Kết quả hoặc dữ liệu adapter cung cấp | BookSummary |
| Persistence entity | Persistence adapter | Mapping bảng và quan hệ ORM | BookJpaEntity |
| ViewModel | MVC presentation adapter | Dữ liệu template cần | BookListViewModel |
| Response DTO | REST adapter | Hợp đồng JSON công khai | BookResponse |

Không nhất thiết tạo lớp mới cho mọi trường hợp. Nếu hai ranh giới có cùng ngữ nghĩa và cùng vòng đời, có thể dùng chung kiểu. Nhưng không nên để framework quyết định cấu trúc domain chỉ vì annotation tiện lợi.

### 7.1. Mapping đặt ở đâu?

- Web adapter chuyển Request DTO thành inbound command/query.
- Application service điều phối và gọi domain behavior.
- Persistence adapter chuyển persistence entity thành kiểu mà outbound port công bố.
- Web adapter chuyển kết quả use case thành ViewModel hoặc Response DTO.

Mapping nên được đặt gần ranh giới chuyển đổi. Tránh để domain entity tự biết cách render HTML hoặc để template gọi mapper persistence.

### 7.2. Validation ở các tầng

Validation đầu vào như kiểu dữ liệu, độ dài và format thường nằm ở web adapter hoặc request DTO. Quy tắc nghiệp vụ và bất biến cần được bảo vệ trong application/domain core.

Ví dụ, form có thể kiểm tra ISBN có định dạng hợp lệ; domain object vẫn cần bảo đảm ISBN hợp lệ khi được tạo từ bất kỳ adapter nào. Không để một REST adapter hoặc message consumer bỏ qua quy tắc chỉ vì validation của form đã chạy.

## 8. Transaction và xử lý lỗi trong mô hình kết hợp

Application service thường là nơi điều phối một ca sử dụng và xác định ranh giới transaction. Nó gọi domain logic và outbound port trong một luồng có ý nghĩa nghiệp vụ.

Ví dụ tạo đơn hàng:

1. Controller nhận request và chuyển thành PlaceOrderCommand.
2. Inbound port nhận command.
3. Application service xác minh ngữ cảnh và bắt đầu use case.
4. Domain kiểm tra bất biến đơn hàng.
5. Outbound port lưu đơn hàng và ghi nhận thao tác cần thiết.
6. Kết quả use case trở lại Controller.
7. Controller chuyển kết quả thành redirect, ViewModel hoặc response DTO.

Không nên đặt transaction trong Controller chỉ vì đó là nơi nhận request. Transaction nên gắn với ranh giới use case. Với Spring, có thể dùng @Transactional trong adapter/service triển khai phù hợp, nhưng cần chú ý annotation framework không làm domain core phụ thuộc Spring nếu mục tiêu là giữ lõi thuần.

### 8.1. Lỗi được ánh xạ ở adapter đầu vào

Core nên biểu diễn lỗi theo ngữ nghĩa ứng dụng, ví dụ BookNotFound, DuplicateEmail hoặc OrderCannotBeCancelled. MVC adapter chuyển chúng thành HTTP status, trang lỗi hoặc lỗi form. REST adapter có thể chuyển cùng lỗi thành Problem Detail JSON.

Không đưa HttpStatus, ModelAndView hoặc thông điệp HTML vào domain model. Điều đó khiến lõi phụ thuộc giao thức trình bày.

### 8.2. Lỗi từ outbound adapter

Database timeout hoặc email provider unavailable là lỗi kỹ thuật của adapter. Adapter có thể chuyển lỗi kỹ thuật thành lỗi hạ tầng có ngữ nghĩa phù hợp với port; application service quyết định có retry, fallback hoặc thất bại use case. MVC Controller không nên bắt SQLException để quyết định logic nghiệp vụ.

Với thao tác có tác dụng phụ như thanh toán hoặc gửi message, cần idempotency, transaction/outbox hoặc cơ chế đảm bảo phù hợp. Việc chỉ bọc lời gọi trong try/catch không bảo đảm thao tác không bị lặp khi response bị mất.

## 9. Cấu trúc package gợi ý

Một cấu trúc có thể tổ chức theo use case và adapter:

~~~text
com.example.library
  domain/
    model/
      Book.java
      ISBN.java
    policy/
      BookPublicationPolicy.java

  application/
    port/
      in/
        SearchBooksUseCase.java
        RegisterBookUseCase.java
      out/
        LoadBooksPort.java
        SaveBookPort.java
    service/
      SearchBooksService.java
      RegisterBookService.java
    model/
      SearchBooksQuery.java
      SearchBooksResult.java

  adapter/
    in/
      web/
        mvc/
          BookController.java
          BookListRequest.java
          BookListViewModel.java
          BookExceptionHandler.java
        rest/
          BookRestController.java
    out/
      persistence/
        BookJpaEntity.java
        BookJpaRepository.java
        JpaLoadBooksAdapter.java
      notification/
        SmtpEmailAdapter.java

  bootstrap/
    LibraryApplication.java
    BeanConfiguration.java
~~~

Tên package là gợi ý, không phải chuẩn bắt buộc. Dự án có thể tổ chức theo feature như books, orders, members rồi đặt domain/application/adapter trong từng feature. Cách đó thường giúp nhóm làm việc trên một nghiệp vụ tìm được các thành phần liên quan dễ hơn.

Điều cần giữ là hướng phụ thuộc: adapter có thể phụ thuộc vào application/domain; application/domain không phụ thuộc ngược vào adapter.

## 10. Composition root và Dependency Injection

Lõi định nghĩa port; adapter cung cấp implementation. Ứng dụng cần một nơi nối chúng lại. Nơi cấu hình object graph này thường được gọi là composition root.

Với Spring, component scanning và dependency injection có thể tự nối implementation:

~~~java
@Service
public class SearchBooksService implements SearchBooksUseCase {
    private final LoadBooksPort loadBooks;

    public SearchBooksService(LoadBooksPort loadBooks) {
        this.loadBooks = loadBooks;
    }
}
~~~

~~~java
@Repository
public class JpaLoadBooksAdapter implements LoadBooksPort {
    // Triển khai bằng Spring Data JPA
}
~~~

Spring tạo bean và inject adapter vào use case. Tuy nhiên, việc dùng annotation Spring không bắt buộc phải lan vào domain model. Có thể đặt cấu hình ở module bootstrap và dùng constructor injection để thể hiện dependency rõ ràng.

### 10.1. Tránh phụ thuộc implementation cụ thể

Không nên để Controller inject JpaBookRepository nếu Controller chỉ cần chức năng tìm kiếm sách. Controller nên phụ thuộc inbound port. Không nên để application service gọi trực tiếp EntityManager hoặc RestTemplate; nó nên phụ thuộc outbound port.

Nếu một port chỉ có một adapter, interface vẫn có thể hữu ích khi nó thể hiện ranh giới ổn định của lõi. Nhưng đừng tạo interface cho mọi class chỉ để tăng số lượng abstraction.

## 11. Kiểm thử khi kết hợp MVC và Hexagonal Architecture

Ranh giới rõ ràng giúp chọn loại test phù hợp.

| Phạm vi | Test nên tập trung | Phụ thuộc cần giả lập |
|---|---|---|
| Domain | Bất biến, quy tắc và chuyển trạng thái | Thường không cần framework |
| Application use case | Điều phối, quyết định và gọi port | Fake/mock outbound port |
| Outbound adapter | Mapping và hành vi tích hợp với database/API | Test database hoặc server giả |
| MVC Controller | Binding, validation, điều hướng, status và ViewModel | Mock inbound port |
| View/template | Render dữ liệu, escaping, accessibility | Model mẫu |
| End-to-end | Luồng người dùng xuyên các adapter | Hệ thống tích hợp theo môi trường test |

### 11.1. Unit test use case không cần Spring context

Ví dụ dùng fake outbound port:

~~~java
class SearchBooksServiceTest {
    @Test
    void requestsOneExtraItemToDetectNextPage() {
        LoadBooksPort fakePort = criteria ->
            List.of(
                new BookSummary(UUID.randomUUID(), "A", "Author"),
                new BookSummary(UUID.randomUUID(), "B", "Author"),
                new BookSummary(UUID.randomUUID(), "C", "Author")
            );

        var service = new SearchBooksService(fakePort);
        var result = service.search(new SearchBooksQuery(" java ", 0, 2));

        assertEquals(2, result.items().size());
        assertTrue(result.hasNext());
    }
}
~~~

Test xác nhận use case chuẩn hóa và xử lý kết quả mà không khởi động Spring, database hoặc template engine. Test thực tế cần kiểm tra cả criteria được truyền cho port, page/size biên và lỗi phù hợp.

### 11.2. Controller test chỉ kiểm tra adapter web

Mock inbound port để xác nhận Controller chuyển request đúng và trả view phù hợp. Không cần mock repository JPA nếu Controller không phụ thuộc trực tiếp repository.

Các tình huống:

- Query parameter được binding đúng.
- Giá trị sai trả form hoặc lỗi theo hợp đồng.
- Controller gọi đúng inbound port.
- ViewModel có dữ liệu cần thiết.
- Lỗi use case được ánh xạ sang status/view phù hợp.
- Không có field nội bộ bị đưa vào ViewModel ngoài ý muốn.

### 11.3. Adapter contract test

Kiểm tra adapter triển khai port đúng hợp đồng. Ví dụ JPA adapter cần:

- Lọc đúng điều kiện.
- Áp dụng sort ổn định.
- Phân trang đúng.
- Ánh xạ null và kiểu dữ liệu phù hợp.
- Xử lý lỗi database theo chính sách.
- Không trả dữ liệu ngoài tenant scope.

Nếu có nhiều adapter triển khai cùng một port, có thể chạy cùng bộ contract test cho từng implementation.

## 12. Khi nào nên kết hợp MVC và Hexagonal Architecture?

Không phải ứng dụng nào cũng cần đầy đủ lớp port/adapter. Quyết định phụ thuộc vào độ phức tạp nghiệp vụ, số lượng tích hợp, tuổi thọ hệ thống và khả năng thay đổi công nghệ.

| Bối cảnh | Cách tiếp cận phù hợp |
|---|---|
| CRUD nhỏ, một database, ít quy tắc | MVC với service/repository đơn giản |
| Nhiều quy tắc nghiệp vụ và trạng thái | MVC ở adapter web, application/domain core rõ ràng |
| Có HTML, REST, message consumer cùng gọi use case | Hexagonal giúp dùng chung inbound port |
| Tích hợp nhiều nhà cung cấp bên ngoài | Outbound port cô lập API và SDK |
| Cần test nghiệp vụ không khởi động framework | Core thuần với port dễ fake |
| Hệ thống có nhiều module và nhóm phát triển | Ranh giới adapter/port giúp kiểm soát phụ thuộc |
| Prototype ngắn hạn | Có thể bắt đầu đơn giản, tách port khi có nhu cầu thật |

### 12.1. Dấu hiệu nên tách port

- Application service phụ thuộc trực tiếp nhiều SDK hoặc framework.
- Cùng một nghiệp vụ được gọi từ web, API và message.
- Test use case phải khởi động database hoặc Spring context dù chỉ kiểm tra quy tắc.
- Thay database hoặc nhà cung cấp tích hợp làm sửa nhiều lớp nghiệp vụ.
- Controller truy cập repository và chứa logic truy vấn/điều phối phức tạp.
- Entity persistence bị dùng xuyên suốt đến template hoặc API.

### 12.2. Tránh overengineering

Tạo nhiều interface, mapper và package không tự động làm kiến trúc tốt hơn. Một port không có ranh giới có ý nghĩa sẽ trở thành lớp chuyển tiếp hình thức. Nếu một service chỉ gọi một repository với cùng tham số và không có quy tắc use case, thêm nhiều abstraction có thể làm code khó đọc hơn.

Hãy bắt đầu từ một ranh giới có lý do: một use case có nhiều adapter, một dependency bên ngoài dễ thay đổi hoặc một quy tắc nghiệp vụ cần kiểm thử độc lập. Mở rộng cấu trúc khi sự phức tạp thực sự xuất hiện.

## 13. Những lỗi thiết kế thường gặp

| Dấu hiệu | Hệ quả | Cách cải thiện |
|---|---|---|
| Đồng nhất MVC Model với toàn bộ Hexagonal Core | Trộn dữ liệu ViewModel, persistence và domain | Phân biệt loại model theo trách nhiệm |
| Controller gọi trực tiếp JPA repository | Adapter web phụ thuộc hạ tầng và có thể chứa nghiệp vụ | Controller gọi inbound port |
| Application service import Spring Data hoặc SDK | Lõi bị khóa vào công nghệ | Khai báo outbound port trong core |
| Port được định nghĩa trong adapter rồi core phụ thuộc ngược | Dependency direction bị đảo sai | Đặt abstraction ở phía lõi cần khả năng |
| Domain entity mang annotation View hoặc HTTP | Domain phụ thuộc trình bày/giao thức | Mapping ở adapter |
| Đưa JPA entity thẳng vào template | View phụ thuộc persistence và có thể tải lazy ngoài ý muốn | Dùng ViewModel hoặc projection |
| Một interface cho mọi class | Tăng abstraction không có giá trị | Chỉ tạo port tại ranh giới có ý nghĩa |
| Controller và REST adapter lặp use case | Logic nghiệp vụ bị nhân đôi | Dùng chung inbound port |
| Adapter tự quyết định quy tắc nghiệp vụ | Quy tắc phân tán theo công nghệ | Đưa quyết định vào application/domain core |
| Mock mọi thứ và không test adapter thật | Không phát hiện lỗi mapping hoặc tích hợp | Thêm adapter contract và integration test |
| Gắn transaction vào Controller | Ranh giới transaction phụ thuộc giao thức | Đặt transaction theo use case |
| Nghĩ Hexagonal Architecture bắt buộc microservices | Tăng vận hành và phân tán không cần thiết | Có thể dùng trong một modular monolith |

## 14. Checklist kết hợp MVC và Hexagonal Architecture

- [ ] Controller là adapter HTTP, tập trung binding, validation giao thức và điều hướng.
- [ ] Inbound port mô tả hành động ứng dụng cung cấp.
- [ ] Application service triển khai use case và điều phối nghiệp vụ.
- [ ] Domain model giữ bất biến và quy tắc cốt lõi.
- [ ] Outbound port mô tả nhu cầu của lõi đối với database hoặc dịch vụ ngoài.
- [ ] Adapter hạ tầng triển khai port bằng công nghệ cụ thể.
- [ ] View dùng ViewModel hoặc dữ liệu trình bày phù hợp.
- [ ] Request DTO, domain model và persistence entity không bị đồng nhất vô điều kiện.
- [ ] Dependency từ adapter hướng vào abstraction thuộc lõi.
- [ ] Lõi không import Spring MVC, template engine, JPA hoặc SDK tích hợp.
- [ ] Transaction và lỗi được xử lý theo ranh giới use case và adapter.
- [ ] Use case có thể kiểm thử độc lập với framework.
- [ ] Controller, View và adapter có test ở đúng phạm vi.
- [ ] Port chỉ được tạo khi thể hiện một ranh giới có ý nghĩa, tránh abstraction hình thức.

MVC và Hexagonal Architecture không phải hai lựa chọn loại trừ nhau. MVC tổ chức phần giao diện và luồng tương tác; Hexagonal Architecture bảo vệ lõi nghiệp vụ bằng các port và adapter. Khi kết hợp, Controller trở thành adapter đầu vào, View là phần trình bày đầu ra, application service thực hiện use case, domain giữ quy tắc và các adapter hạ tầng triển khai những khả năng mà lõi yêu cầu. Ranh giới này giúp ứng dụng có thể thay đổi giao diện hoặc công nghệ tích hợp mà không phải viết lại logic nghiệp vụ, đồng thời giữ được khả năng kiểm thử từng phần một cách độc lập.
