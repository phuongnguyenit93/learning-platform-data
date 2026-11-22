# Transaction trong query

GraphQL Query thường dùng để đọc dữ liệu, nhưng một query có thể gọi nhiều resolver, truy cập nhiều repository và lấy dữ liệu từ các service khác nhau. Nếu không xác định rõ transaction boundary, ứng dụng dễ gặp lỗi lazy loading, đọc dữ liệu không nhất quán, mở transaction quá lâu hoặc vô tình thực hiện nhiều truy vấn riêng lẻ.

Trong Spring for GraphQL, GraphQL engine điều phối việc thực thi field. Spring transaction management quản lý transaction tại những method được áp dụng @Transactional. Hai cơ chế này phối hợp với nhau, nhưng GraphQL operation không tự động trở thành một transaction duy nhất.

Với query đọc dữ liệu, cách triển khai thường dùng là đặt transaction read-only tại service method thực hiện truy vấn. Resolver gọi service và trả DTO hoặc projection đã tải đủ dữ liệu cần thiết. Nếu field lồng nhau cần truy vấn riêng, service tương ứng có thể mở transaction read-only riêng. Với DataLoader, batch service thực hiện một truy vấn cho nhiều key trong một transaction thay vì mở một transaction cho từng phần tử.

## Vì sao GraphQL Query cần transaction?

Một GraphQL request có thể yêu cầu dữ liệu từ nhiều nhánh:

~~~graphql
query BookDetails($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
    reviews {
      rating
    }
  }
}
~~~

Để tạo response, ứng dụng có thể:

1. Đọc Book theo ID.
2. Đọc Author theo authorId.
3. Đọc danh sách Review theo bookId.
4. Chuyển các entity thành dữ liệu trả về cho GraphQL.

Transaction giúp nhóm các thao tác truy cập database trong một ranh giới xác định. Nó có thể bảo đảm các quy tắc transaction của database như commit/rollback, isolation và quản lý persistence context.

Các vấn đề thường gặp nếu không thiết kế transaction rõ ràng:

- Entity được trả ra khỏi service rồi field resolver mới truy cập lazy association, dẫn tới LazyInitializationException.
- Các nested resolver có thể mở transaction riêng và đọc dữ liệu ở những thời điểm khác nhau.
- Một resolver gọi repository nhiều lần, khiến transaction bị mở/đóng lặp lại.
- Một GraphQL Query có nhiều field chạy song song, nhưng code lại giả định các field dùng chung một transaction hoặc một EntityManager.
- Method trả CompletableFuture hoặc Publisher nhưng transaction imperative đã kết thúc trước khi phần xử lý bất đồng bộ chạy xong.

Transaction không thay thế batching, pagination hay authorization. Nó xác định phạm vi nhất quán của thao tác database; các vấn đề về N+1 và quyền truy cập vẫn cần được giải quyết riêng.

## GraphQL operation không tự tạo transaction

Spring for GraphQL không tự mở một transaction bao quanh toàn bộ GraphQL operation. Transaction chỉ xuất hiện khi ứng dụng gọi một method có transaction advice, chẳng hạn service method được đánh dấu @Transactional, hoặc khi code chủ động dùng TransactionTemplate/TransactionalOperator.

Ví dụ, một query có hai root field:

~~~graphql
query Dashboard {
  currentUser {
    id
    name
  }
  recentOrders {
    id
    total
  }
}
~~~

GraphQL Query cho phép các root field độc lập được thực thi song song. Nếu currentUser và recentOrders gọi hai service method có @Transactional(readOnly = true), mỗi lần gọi có thể chạy trong transaction riêng. Không có cam kết rằng cả hai cùng đọc một snapshot database.

Mutation có quy tắc thực thi tuần tự đối với các top-level mutation field, nhưng điều đó cũng không tự tạo một transaction database bao trùm toàn bộ operation. Transaction vẫn phải được thiết kế ở tầng ứng dụng.

Vì vậy, hãy xem transaction boundary theo công việc nghiệp vụ và lời gọi service, không giả định nó trùng với ranh giới của GraphQL document.

## Dùng @Transactional(readOnly = true) cho truy vấn đọc

Với service chỉ đọc dữ liệu, khai báo readOnly = true:

~~~java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public BookView findBook(String id) {
        BookEntity book = bookRepository.findById(id)
                .orElseThrow(() ->
                        new BookNotFoundException(id));

        return new BookView(
                book.getId(),
                book.getTitle());
    }
}
~~~

readOnly = true thể hiện ý định của method và cho transaction manager/persistence provider cơ hội tối ưu hoạt động đọc. Với Hibernate, Spring có thể áp dụng flush mode phù hợp để giảm dirty checking trong một số cấu hình.

Đây là hint tối ưu và metadata transaction, không phải cơ chế bảo mật. Không dùng readOnly = true để ngăn mọi câu lệnh ghi ở database. Hành vi cụ thể phụ thuộc transaction manager, ORM, driver và database. Nếu nghiệp vụ cần bảo đảm không ghi, hãy thiết kế quyền database và API phù hợp.

## Đặt transaction ở service thay vì giữ trong controller

Resolver nên tập trung vào việc ánh xạ GraphQL argument và gọi use case. Service chịu trách nhiệm về transaction và truy cập dữ liệu:

~~~java
@Controller
public class BookController {

    private final BookQueryService bookQueryService;

    public BookController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public BookView book(@Argument String id) {
        return bookQueryService.findBook(id);
    }
}
~~~

Controller không cần tự mở transaction nếu service đã xác định boundary. Cách này giúp cùng một service được tái sử dụng từ GraphQL, REST, scheduled job hoặc message handler mà không phụ thuộc transport.

Nếu transaction bao trùm nhiều repository call để tạo một kết quả nghiệp vụ, đặt @Transactional trên method service điều phối các thao tác đó:

~~~java
@Service
public class DashboardQueryService {

    private final UserRepository userRepository;
    private final OrderRepository orderRepository;

    public DashboardQueryService(
            UserRepository userRepository,
            OrderRepository orderRepository) {
        this.userRepository = userRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public DashboardView loadDashboard(String userId) {
        UserSummary user = userRepository.findSummaryById(userId)
                .orElseThrow(() -> new UserNotFoundException(userId));

        List<OrderSummary> orders =
                orderRepository.findRecentSummaries(userId);

        return new DashboardView(user, orders);
    }
}
~~~

Hai truy vấn repository ở trên nằm trong cùng một transaction do method service quản lý. Đây là một boundary rõ ràng vì chúng cùng tạo một DashboardView.

## Transaction propagation mặc định

Spring transaction management mặc định dùng propagation REQUIRED cho @Transactional. Nếu chưa có transaction, method mở transaction mới. Nếu đã có transaction phù hợp, method tham gia transaction hiện tại.

| Propagation | Hành vi | Trường hợp thường gặp |
| --- | --- | --- |
| REQUIRED | Tham gia transaction hiện tại hoặc tạo transaction mới | Lựa chọn mặc định cho service query |
| REQUIRES_NEW | Tạm treo transaction hiện tại và mở transaction mới | Chỉ dùng khi thực sự cần ranh giới độc lập |
| SUPPORTS | Tham gia transaction nếu có, nếu không thì chạy không transaction | Logic đọc có thể chạy trong hoặc ngoài transaction |
| MANDATORY | Yêu cầu caller đã có transaction | Thành phần nội bộ cần transaction từ caller |
| NOT_SUPPORTED | Tạm treo transaction hiện tại và chạy không transaction | Công việc không nên giữ transaction |
| NEVER | Báo lỗi nếu đang có transaction | Hiếm dùng trong luồng query |
| NESTED | Dùng nested transaction/savepoint nếu transaction manager hỗ trợ | Cần kiểm soát rollback một phần |

Với truy vấn thông thường, REQUIRED thường đủ. Không dùng REQUIRES_NEW cho mọi resolver vì có thể tạo nhiều transaction không cần thiết, làm giảm khả năng dùng chung transaction của một service workflow và tăng tải database.

Transaction annotation thường được áp dụng qua Spring proxy. Nếu một method trong cùng class gọi trực tiếp một method khác có @Transactional, lời gọi nội bộ đó không đi qua proxy và không tự tạo transaction boundary mới. Đặt transaction ở public service method được gọi từ bean khác hoặc dùng cách quản lý transaction tường minh khi cần.

## Nested resolver và transaction boundary

Giả sử root resolver trả BookView, sau đó GraphQL gọi field author:

~~~java
@QueryMapping
public BookEntity book(@Argument String id) {
    return bookQueryService.findEntity(id);
}

@SchemaMapping(typeName = "Book", field = "author")
public AuthorView author(BookEntity book) {
    return authorQueryService.findById(book.getAuthorId());
}
~~~

Nếu findEntity() là một method @Transactional(readOnly = true) trả về entity, transaction thường kết thúc khi method trả về. Field author có thể được gọi sau đó, ở một resolver invocation khác. Không nên giả định transaction của root resolver vẫn mở khi GraphQL phân giải field con.

Có hai cách thiết kế thường dùng:

**Cách 1: Tải dữ liệu cần thiết trong một service method và trả DTO.**

~~~java
@Transactional(readOnly = true)
public BookDetailsView findBookDetails(String id) {
    BookEntity book = bookRepository.findDetailsById(id)
            .orElseThrow(() -> new BookNotFoundException(id));

    return new BookDetailsView(
            book.getId(),
            book.getTitle(),
            new AuthorView(
                    book.getAuthor().getId(),
                    book.getAuthor().getName()));
}
~~~

GraphQL nhận DTO đã có dữ liệu cần thiết. Field mapping có thể dùng property access mà không cần mở transaction để truy cập lazy association.

**Cách 2: Nested resolver gọi service riêng.**

~~~java
@Service
public class AuthorQueryService {

    private final AuthorRepository authorRepository;

    public AuthorQueryService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    @Transactional(readOnly = true)
    public AuthorView findById(String id) {
        return authorRepository.findViewById(id)
                .orElseThrow(() -> new AuthorNotFoundException(id));
    }
}
~~~

Resolver author gọi service này khi cần dữ liệu. Service tự mở transaction read-only cho truy vấn của nó. Với danh sách Book lớn, không gọi service một lần cho từng Book; hãy dùng DataLoader hoặc @BatchMapping để gom các ID thành một batch.

## Tránh lazy loading sau khi transaction kết thúc

JPA thường dùng lazy loading để trì hoãn truy vấn association cho tới khi code truy cập. Nếu resolver trả entity ra ngoài transaction rồi GraphQL mới truy cập association, persistence context có thể đã đóng:

~~~java
@Transactional(readOnly = true)
public BookEntity findById(String id) {
    return bookRepository.findById(id)
            .orElseThrow();
}
~~~

Nếu GraphQL sau đó đọc book.getAuthor().getName(), có thể phát sinh LazyInitializationException khi entity không còn gắn với EntityManager.

Không nên dựa vào Open EntityManager in View để giữ persistence context mở cho toàn bộ quá trình render GraphQL response. Cơ chế này có thể khiến truy vấn database phát sinh muộn trong lúc serialize/resolve field, che giấu N+1 và kéo dài thời gian giữ persistence context. Nó cũng không biến toàn bộ GraphQL execution thành một transaction.

Các lựa chọn tốt hơn:

- Dùng DTO hoặc projection để chỉ trả dữ liệu cần thiết.
- Dùng JPQL fetch join hoặc EntityGraph cho association cần tải.
- Dùng batch resolver/DataLoader cho quan hệ một-nhiều hoặc nhiều-một.
- Giữ truy vấn và mapping entity sang DTO bên trong transaction.
- Không trả JPA entity làm contract công khai nếu field GraphQL còn có thể truy cập lazy association.

Ví dụ EntityGraph:

~~~java
public interface BookRepository extends JpaRepository<BookEntity, String> {

    @EntityGraph(attributePaths = "author")
    Optional<BookEntity> findWithAuthorById(String id);
}
~~~

Service tải association và chuyển thành DTO trước khi transaction kết thúc:

~~~java
@Transactional(readOnly = true)
public BookDetailsView findBookDetails(String id) {
    BookEntity book = bookRepository.findWithAuthorById(id)
            .orElseThrow(() -> new BookNotFoundException(id));

    return new BookDetailsView(
            book.getId(),
            book.getTitle(),
            book.getAuthor().getName());
}
~~~

EntityGraph chỉ tải association đã chỉ định. Nếu response còn cần reviews, hãy xác định cách tải reviews riêng thay vì thêm tùy tiện nhiều collection vào một fetch join gây nhân bản dòng hoặc xung đột với pagination.

## Transaction và DataLoader

DataLoader gom nhiều lần yêu cầu dữ liệu thành một batch. Transaction nên được mở tại batch service để toàn bộ truy vấn của batch chạy trong cùng một boundary.

Ví dụ:

~~~java
@Service
public class ReviewQueryService {

    private final ReviewRepository reviewRepository;

    public ReviewQueryService(ReviewRepository reviewRepository) {
        this.reviewRepository = reviewRepository;
    }

    @Transactional(readOnly = true)
    public Map<String, List<ReviewView>> findByBookIds(
            Set<String> bookIds) {

        return reviewRepository.findByBookIdIn(bookIds).stream()
                .map(ReviewView::from)
                .collect(Collectors.groupingBy(ReviewView::bookId));
    }
}
~~~

Batch mapping:

~~~java
@Controller
public class BookReviewController {

    private final ReviewQueryService reviewQueryService;

    public BookReviewController(ReviewQueryService reviewQueryService) {
        this.reviewQueryService = reviewQueryService;
    }

    @BatchMapping(typeName = "Book", field = "reviews")
    public Map<BookView, List<ReviewView>> reviews(List<BookView> books) {
        Set<String> bookIds = books.stream()
                .map(BookView::id)
                .collect(Collectors.toSet());

        Map<String, List<ReviewView>> byBook =
                reviewQueryService.findByBookIds(bookIds);

        Map<BookView, List<ReviewView>> result = new HashMap<>();
        for (BookView book : books) {
            result.put(
                    book,
                    byBook.getOrDefault(book.id(), List.of()));
        }
        return result;
    }
}
~~~

Transaction nằm trong findByBookIds(). Một lần batch có thể truy vấn nhiều book ID trong một câu lệnh, map kết quả và trả DTO. Không đặt @Transactional trên một method chỉ nhận từng Book rồi gọi repository riêng cho mỗi phần tử; như vậy vẫn giữ N+1 và tạo transaction lặp lại.

Nếu batch loader tùy chỉnh dùng BatchLoaderRegistry, hãy để batch service sở hữu transaction. DataLoader cache theo GraphQL request không phải transaction và không cung cấp isolation database.

## Query có nhiều root field và tính nhất quán dữ liệu

Một query có thể có nhiều root field độc lập:

~~~graphql
query AccountOverview($accountId: ID!) {
  account(id: $accountId) {
    id
    balance
  }
  recentTransactions(accountId: $accountId) {
    id
    amount
  }
}
~~~

Nếu hai resolver gọi hai service method khác nhau, mỗi method có thể chạy trong transaction riêng. Một transaction có thể đọc balance trước khi giao dịch mới được ghi, còn transaction kia đọc recentTransactions sau khi giao dịch đã commit.

Điều này không nhất thiết là lỗi. Nó phụ thuộc yêu cầu nhất quán của màn hình và chính sách isolation database. Nếu response cần một snapshot nhất quán, hãy thiết kế một service use case duy nhất đọc dữ liệu liên quan trong cùng transaction rồi trả DTO tổng hợp:

~~~java
@Transactional(
        readOnly = true,
        isolation = Isolation.REPEATABLE_READ)
public AccountOverviewView loadOverview(String accountId) {
    AccountView account = accountRepository.findViewById(accountId)
            .orElseThrow();

    List<TransactionView> transactions =
            transactionRepository.findRecentViews(accountId);

    return new AccountOverviewView(account, transactions);
}
~~~

Isolation REPEATABLE_READ có ý nghĩa khác nhau tùy database và có thể ảnh hưởng concurrency. Một số database dùng snapshot isolation; database khác có semantics riêng. Isolation chỉ được áp dụng khi transaction mới được tạo; nếu method tham gia transaction có sẵn, thuộc tính isolation khai báo ở method con thường không thay đổi isolation của transaction hiện tại.

Không tăng isolation lên SERIALIZABLE cho mọi query. Hãy chọn mức cần thiết theo invariant nghiệp vụ, thời gian transaction và khả năng chịu contention của database.

## readOnly không đồng nghĩa với isolation

Hai thuộc tính này giải quyết hai mục tiêu khác nhau:

| Thuộc tính | Mục tiêu |
| --- | --- |
| readOnly = true | Thể hiện transaction chỉ đọc và cho provider cơ hội tối ưu |
| isolation | Xác định mức độ cô lập giữa các transaction đồng thời |
| timeout | Giới hạn thời gian transaction theo transaction manager hỗ trợ |
| propagation | Quy định cách method tham gia hoặc tạo transaction |

Một transaction read-only vẫn có thể đọc dữ liệu bị thay đổi bởi transaction khác, tùy isolation level. Ngược lại, transaction REPEATABLE_READ không tự động trở thành read-only.

Nếu query chỉ cần đọc dữ liệu, dùng readOnly = true là hợp lý. Nếu cần snapshot nhất quán, đánh giá isolation riêng và xác nhận database hỗ trợ đúng semantics mong muốn.

## Transaction với CompletableFuture và asynchronous resolver

Spring transaction imperative thường gắn với thread hiện tại. Khi method trả về, transaction interceptor hoàn tất transaction theo vòng đời method. Không nên giả định transaction tiếp tục tồn tại trong callback chạy sau đó trên một thread khác.

Ví dụ dễ gây hiểu nhầm:

~~~java
@Transactional(readOnly = true)
public CompletableFuture<BookView> findBookAsync(String id) {
    return CompletableFuture.supplyAsync(() ->
            bookRepository.findById(id)
                    .map(BookView::from)
                    .orElseThrow());
}
~~~

Trong ví dụ này, phần repository call chạy bên trong supplier có thể được thực thi sau khi method đã trả CompletableFuture và transaction imperative đã kết thúc. Thread của ForkJoinPool cũng không tự kế thừa transaction hoặc EntityManager của caller.

Với JPA, cách đơn giản là thực hiện database work đồng bộ trong transaction rồi trả kết quả đã materialize:

~~~java
@Transactional(readOnly = true)
public BookView findBook(String id) {
    return bookRepository.findById(id)
            .map(BookView::from)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Nếu cần asynchronous execution, hãy tạo transaction trong chính worker/service method thực hiện database work, hoặc dùng một reactive persistence stack với reactive transaction manager. Không truyền JPA entity chưa tải đầy đủ sang thread khác.

## Transaction reactive với WebFlux và R2DBC

Với WebFlux và R2DBC, transaction được quản lý theo reactive context thay vì chỉ dựa trên ThreadLocal. Spring hỗ trợ ReactiveTransactionManager và @Transactional cho method trả về Publisher như Mono hoặc Flux.

Ví dụ service:

~~~java
@Service
public class ProductQueryService {

    private final ProductRepository productRepository;

    public ProductQueryService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional(readOnly = true)
    public Mono<ProductView> findById(String id) {
        return productRepository.findById(id)
                .map(ProductView::from);
    }
}
~~~

Controller:

~~~java
@Controller
public class ProductController {

    private final ProductQueryService productQueryService;

    public ProductController(ProductQueryService productQueryService) {
        this.productQueryService = productQueryService;
    }

    @QueryMapping
    public Mono<ProductView> product(@Argument String id) {
        return productQueryService.findById(id);
    }
}
~~~

Reactive transaction được giữ trong reactive pipeline của method. Publisher cần được subscribe bởi framework; không tự gọi subscribe() hoặc block() bên trong service. Các thao tác database phải được ghép trong cùng pipeline để chúng tham gia transaction.

Để annotation trên method trả Mono/Flux tạo reactive transaction, ứng dụng phải có ReactiveTransactionManager phù hợp, chẳng hạn R2dbcTransactionManager. Nếu chỉ có PlatformTransactionManager của JPA/JDBC, không giả định transaction đó sẽ quản lý các thao tác R2DBC.

Với transaction phức tạp hơn, có thể dùng TransactionalOperator:

~~~java
public Mono<ProductView> findProduct(String id) {
    return productRepository.findById(id)
            .map(ProductView::from)
            .as(transactionalOperator::transactional);
}
~~~

TransactionalOperator phải được tạo từ ReactiveTransactionManager. Đây là lựa chọn hữu ích khi cần bao một reactive sequence cụ thể thay vì đặt annotation trên method.

Không dùng JPA/Jdbc blocking repository bên trong reactive transaction và mong nó tự tham gia R2DBC transaction. Hai transaction manager và hai resource khác nhau. Nếu ứng dụng dùng JPA trong Spring MVC, dùng transaction manager imperative; nếu dùng R2DBC trong WebFlux, dùng reactive transaction manager tương ứng.

## Không block hoặc tự subscribe trong reactive transaction

Những cách sau làm mất ý nghĩa của reactive transaction:

~~~java
@Transactional(readOnly = true)
public Mono<ProductView> findById(String id) {
    Product product = productRepository.findById(id).block();
    return Mono.just(ProductView.from(product));
}
~~~

~~~java
@Transactional(readOnly = true)
public Mono<Void> refreshCache(String id) {
    productRepository.findById(id)
            .doOnNext(this::updateCache)
            .subscribe();
    return Mono.empty();
}
~~~

block() làm nghẽn thread và có thể chạy ngoài reactive flow mong muốn. subscribe() tự tạo một subscription tách khỏi publisher mà Spring transaction interceptor đang quản lý; method có thể kết thúc và transaction đóng trước khi database work hoàn tất.

Hãy trả publisher cho framework và ghép các bước bằng map, flatMap, then hoặc các operator phù hợp. Khi cần chạy nhiều truy vấn trong một transaction, ghép chúng vào cùng sequence.

## Transaction và lỗi GraphQL

GraphQL có thể trả partial data cùng errors. Một resolver thất bại không nhất thiết làm toàn bộ GraphQL operation thất bại.

Ví dụ:

~~~json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Không thể tải tác giả",
      "path": ["book", "author"]
    }
  ]
}
~~~

Nếu author resolver gọi một service method có transaction riêng và method đó ném exception, transaction của method đó được xử lý theo quy tắc rollback của Spring. GraphQL error handler sau đó chuyển exception thành GraphQL error. Các field khác có thể tiếp tục trả dữ liệu nếu GraphQL nullability cho phép.

Với query read-only, rollback thường không có thay đổi dữ liệu để hoàn tác. Tuy nhiên, nếu query method thực hiện side effect ngoài ý muốn, không dựa vào việc GraphQL trả partial data để suy luận transaction đã rollback toàn bộ operation.

Spring transaction mặc định rollback với RuntimeException và Error; checked exception không tự động rollback nếu không cấu hình rollbackFor. Khi cần quy tắc riêng, khai báo rollbackFor/noRollbackFor rõ ràng trên service method. Không đặt logic rollback ở GraphQL error handler vì lúc đó transaction của resolver có thể đã kết thúc.

## Transaction và bảo mật dữ liệu đọc

readOnly = true không có nghĩa người dùng được phép đọc mọi dữ liệu. Authorization phải được kiểm tra riêng trong service hoặc query repository.

Ví dụ query giới hạn theo tenant:

~~~java
@Transactional(readOnly = true)
public List<OrderView> findOrders(
        String tenantId,
        String subjectId) {

    return orderRepository.findVisibleOrders(tenantId, subjectId)
            .stream()
            .map(OrderView::from)
            .toList();
}
~~~

Tenant ID và subject ID phải đến từ danh tính đã xác thực hoặc context đáng tin cậy. Không dùng tenantId do client gửi làm bằng chứng quyền truy cập. Transaction bảo vệ tính nhất quán của thao tác database, còn authorization quyết định bản ghi nào được phép đọc.

Nếu repository dùng database row-level security, tenant context cần được thiết lập trong đúng transaction và dọn sạch khi transaction kết thúc. Với connection pool, không để session variable của tenant rò sang request kế tiếp.

## Kiểm thử transaction trong GraphQL Query

Nên kiểm thử cả kết quả GraphQL lẫn transaction behavior ở service:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Query thành công | Service trả dữ liệu đúng trong read-only transaction |
| Không tìm thấy entity | Service phát exception và GraphQL error có path phù hợp |
| Nested resolver | Không truy cập lazy association sau khi transaction đã đóng |
| Batch mapping | Một batch query xử lý nhiều parent ID trong transaction |
| Nhiều root field | Không giả định các field song song dùng chung transaction |
| CompletableFuture | Database work không chạy sau khi transaction imperative kết thúc |
| R2DBC Publisher | Các thao tác trong cùng reactive pipeline dùng đúng reactive transaction |
| Authorization | Query chỉ đọc dữ liệu thuộc tenant/subject được phép |
| Isolation | Mức nhất quán đáp ứng yêu cầu nghiệp vụ dưới concurrent update |

Ví dụ test service:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class BookQueryServiceTests {

    @Autowired
    private BookRepository bookRepository;

    @Autowired
    private BookQueryService bookQueryService;

    @Test
    void shouldReturnBookView() {
        BookEntity saved = bookRepository.save(
                new BookEntity("book-42", "Spring GraphQL"));

        BookView result = bookQueryService.findBook(saved.getId());

        assertThat(result.id()).isEqualTo("book-42");
        assertThat(result.title()).isEqualTo("Spring GraphQL");
    }
}
~~~

Test trên minh họa integration test gọi service bean do Spring quản lý, để lời gọi đi qua transaction proxy. Nếu muốn kiểm tra read-only flag hoặc transaction active, có thể dùng TransactionSynchronizationManager bên trong service test hook hoặc instrument transaction manager trong test. Không tự new service vì khi đó @Transactional không được áp dụng qua Spring proxy.

Với GraphQL integration test, dùng GraphQlTester hoặc HttpGraphQlTester để gửi query và xác minh response. Nếu cần kiểm tra transaction boundary, spy/mock service hoặc instrument transaction manager ở test để xác nhận mỗi service invocation chạy đúng boundary. Tránh chỉ kiểm tra HTTP 200 vì response vẫn có thể chứa GraphQL errors.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| LazyInitializationException ở nested field | Entity được trả ra sau khi service transaction kết thúc | Trả DTO/projection hoặc tải association trong service |
| Resolver con không tham gia transaction của resolver cha | Mỗi resolver là invocation riêng; transaction method cha đã kết thúc | Đặt transaction ở service thực hiện truy vấn của field con hoặc gom dữ liệu trong use case |
| N+1 dù đã có @Transactional | Transaction không gom các câu SQL thành một query | Dùng DataLoader, @BatchMapping, projection hoặc fetch plan |
| CompletableFuture không có transaction | Imperative transaction kết thúc khi method trả future | Thực hiện DB work bên trong worker method có transaction hoặc dùng reactive stack phù hợp |
| R2DBC transaction không bao trùm query | Publisher bị block/subscribe tách khỏi pipeline | Trả và compose Mono/Flux, dùng ReactiveTransactionManager |
| Transaction không rollback với checked exception | Quy tắc mặc định rollback RuntimeException/Error | Cấu hình rollbackFor cho checked exception khi cần |
| Query trả dữ liệu không cùng snapshot | Nhiều root resolver dùng transaction riêng hoặc isolation thấp | Gom dữ liệu vào một service transaction hoặc chọn isolation phù hợp |
| Read-only vẫn có thể ghi | readOnly là hint, không phải cơ chế chặn ghi tuyệt đối | Dùng database privilege và tách API/query command rõ ràng |
| Transaction kéo dài khi GraphQL response lớn | Service giữ transaction trong lúc làm thêm công việc hoặc stream lâu | Materialize DTO, giới hạn transaction ở database work và tránh giữ transaction khi gọi network |
| Dữ liệu tenant rò qua request | Tenant context/session state không được giới hạn theo transaction | Thiết lập và dọn tenant context trong transaction, kiểm thử với connection pool |

## Nguyên tắc thiết kế transaction cho GraphQL Query

Khi triển khai query, hãy áp dụng:

1. **Không giả định GraphQL operation có một transaction chung.** Transaction xuất hiện tại method được quản lý bởi Spring transaction manager.
2. **Đặt read-only transaction ở service.** Service xác định rõ nhóm truy vấn cần cùng một boundary.
3. **Trả DTO hoặc projection.** Không để GraphQL field resolver vô tình truy cập lazy association sau khi transaction đã kết thúc.
4. **Xử lý nested field có chủ đích.** Tải trước dữ liệu cần thiết hoặc dùng service riêng cho resolver con.
5. **Batch trước khi tối ưu transaction.** @BatchMapping/DataLoader giảm N+1; transaction chỉ quản lý boundary của batch query.
6. **Tôn trọng concurrency của GraphQL Query.** Các root field có thể chạy song song và dùng transaction riêng.
7. **Phân biệt imperative và reactive.** JPA/JDBC dùng transaction gắn với thread; R2DBC dùng reactive transaction context.
8. **Không block hoặc subscribe thủ công.** Giữ mọi thao tác reactive trong cùng publisher pipeline.
9. **Chọn isolation theo invariant nghiệp vụ.** readOnly không thay thế isolation và không bảo đảm snapshot nhất quán.
10. **Tách authorization khỏi transaction.** readOnly không cấp quyền đọc dữ liệu.
11. **Giữ transaction ngắn.** Không giữ transaction database trong lúc gọi network chậm hoặc stream dữ liệu vô hạn.
12. **Kiểm thử boundary thực tế.** Xác minh service bean, nested resolver, batch loader và reactive flow trong môi trường phù hợp.

Transaction trong GraphQL Query là ranh giới quản lý truy cập database của service và resolver, không phải một transaction tự động bao trùm toàn bộ GraphQL document. Với JPA/JDBC, dùng @Transactional(readOnly = true) ở service method và chuyển entity thành DTO trước khi trả về GraphQL. Với nested field, tránh lazy loading sau khi transaction đóng; với danh sách, dùng DataLoader hoặc @BatchMapping để batch truy vấn. Trong WebFlux/R2DBC, dùng reactive transaction manager và giữ database work trong cùng Mono/Flux pipeline. Cuối cùng, lựa chọn isolation theo yêu cầu nhất quán, tách authorization khỏi read-only hint và giữ transaction ngắn để GraphQL Query hoạt động ổn định dưới tải đồng thời.

## Tài liệu tham khảo

- [Spring Framework - Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework - Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework - Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring for GraphQL - Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - Request Execution and DataLoader](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Data JPA - Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
