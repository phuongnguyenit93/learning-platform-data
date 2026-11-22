# Authorization theo argument

GraphQL field thường nhận dữ liệu do client gửi qua argument. Ví dụ bookById(id: ID!), ordersByCustomer(customerId: ID!) hoặc updateBook(input: UpdateBookInput!). Các argument này giúp resolver biết client muốn truy cập tài nguyên nào, nhưng **không chứng minh client có quyền truy cập tài nguyên đó**.

Nếu server chỉ tải dữ liệu theo ID mà không kiểm tra chủ sở hữu, tenant hoặc quyền cụ thể, API có thể mắc lỗi Broken Object Level Authorization (BOLA), thường được gọi là IDOR. Người dùng thay ID trong query có thể đọc hoặc sửa dữ liệu của người khác.

Trong Spring for GraphQL, authorization theo argument thường kết hợp @Argument hoặc @Arguments để nhận giá trị, Spring Security method security để bảo vệ method và một authorization service để kiểm tra quyền theo principal, resource và tenant. Quy tắc cần được áp dụng ở tầng ứng dụng/domain để mọi entry point dùng chung chính sách.

## 1. Argument không phải danh tính hay quyền truy cập

Xét schema:

~~~graphql
type Query {
    orderById(id: ID!): Order
}
~~~

Client có thể gửi:

~~~graphql
query {
    orderById(id: "order-9001") {
        id
        total
    }
}
~~~

id chỉ là định danh tài nguyên mà client muốn đọc. Server phải lấy principal từ cơ chế authentication đã xác minh, sau đó kiểm tra principal có quyền đọc order đó hay không.

Không nên viết logic như:

~~~java
// Không an toàn: ID do client cung cấp được dùng trực tiếp để trả dữ liệu.
@QueryMapping
public Order orderById(@Argument("id") UUID id) {
    return orderRepository.findById(id).orElse(null);
}
~~~

Nếu ID có thể đoán hoặc lấy từ response khác, người dùng có thể truy cập order không thuộc quyền của họ. ID khó đoán cũng không thay thế authorization.

Một quy tắc an toàn cần kết hợp:

- **Principal:** người gọi đã được xác thực là ai.
- **Action:** người gọi muốn làm gì, ví dụ read, update hoặc cancel.
- **Resource:** đối tượng cụ thể mà argument chỉ định.
- **Context:** tenant, organization, ownership, trạng thái tài nguyên và policy liên quan.

Đây là authorization theo thuộc tính (ABAC): quyết định quyền dựa trên các thuộc tính của subject, action, resource và môi trường thực thi. Role/authority tổng quát vẫn hữu ích, nhưng thường chưa đủ để quyết định quyền trên một object cụ thể.

## 2. Nhận argument trong annotated controller

Spring for GraphQL cung cấp @Argument để bind một argument có tên cụ thể vào tham số Java:

~~~graphql
type Query {
    bookById(id: ID!): Book
}
~~~

~~~java
@QueryMapping
public Book bookById(@Argument("id") UUID bookId) {
    return bookService.findById(bookId);
}
~~~

Với input object:

~~~graphql
input UpdateBookInput {
    bookId: ID!
    title: String
    description: String
}

type Mutation {
    updateBook(input: UpdateBookInput!): Book
}
~~~

~~~java
public record UpdateBookInput(
        UUID bookId,
        String title,
        String description) {
}

@MutationMapping
public Book updateBook(@Argument("input") UpdateBookInput input) {
    return bookService.update(input);
}
~~~

@Arguments có thể bind toàn bộ arguments của field vào một DTO hoặc Map. Dù nhận bằng cách nào, dữ liệu vẫn do client kiểm soát. Binding thành công, kiểu đúng và validation hợp lệ không đồng nghĩa người gọi được phép đọc hoặc thay đổi resource được chỉ định.

GraphQL áp dụng variable coercion, default value và nullability theo schema trước khi resolver xử lý argument. Khi authorization phụ thuộc vào việc một input field bị bỏ qua hay được truyền explicit null, cần giữ được khác biệt đó, ví dụ dùng ArgumentValue<T> trong DTO phù hợp.

## 3. Bật method security

Để dùng @PreAuthorize, ứng dụng phải bật method security:

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {
}
~~~

Với ứng dụng reactive, cấu hình method security reactive tương ứng bằng @EnableReactiveMethodSecurity và bảo đảm security context được truyền trong Reactor Context.

Method security dùng Spring AOP để chặn lời gọi đến bean được bảo vệ. Các method cần được gọi qua Spring proxy; self-invocation bên trong cùng một object có thể bỏ qua interceptor. Vì vậy, đặt quy tắc ở một service bean được inject qua constructor và gọi qua proxy là cách dễ kiểm soát.

## 4. Kiểm tra quyền theo ID bằng @PreAuthorize

Có thể bảo vệ resolver bằng @PreAuthorize và gọi một bean authorization qua SpEL. Ví dụ:

~~~java
@Component("bookAuthorization")
public class BookAuthorization {

    private final BookAccessRepository accessRepository;

    public BookAuthorization(BookAccessRepository accessRepository) {
        this.accessRepository = accessRepository;
    }

    public boolean canRead(Authentication authentication, UUID bookId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        return accessRepository.existsReadableBook(
            bookId, authentication.getName());
    }
}
~~~

Resolver:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("@bookAuthorization.canRead(authentication, #p0)")
    public Book bookById(@Argument("id") UUID bookId) {
        return bookService.findById(bookId);
    }
}
~~~

#p0 tham chiếu tham số đầu tiên của method. Nếu muốn biểu thức dễ đọc hơn, có thể đặt tên tham số method rõ ràng và dùng #bookId; khi đó cần bảo đảm Spring có thể khám phá tên tham số, thường bằng compiler option -parameters. Spring Security cũng hỗ trợ annotation @P để đặt tên tham số dùng trong biểu thức:

~~~java
@QueryMapping
@PreAuthorize("@bookAuthorization.canRead(authentication, #bookId)")
public Book bookById(
        @Argument("id")
        @P("bookId") UUID id) {
    return bookService.findById(id);
}
~~~

@Argument("id") đặt tên GraphQL argument; @P("bookId") đặt tên tham số cho method security. Hai tên này phục vụ hai cơ chế khác nhau.

Authorization component phải kiểm tra quyền thật sự trong dữ liệu tin cậy, chẳng hạn ownership hoặc membership. Không được chỉ so sánh ID với một argument khác do cùng client gửi lên rồi xem đó là bằng chứng quyền.

## 5. Đặt authorization ở application service

Bảo vệ resolver có thể giúp chặn sớm, nhưng quy tắc nghiệp vụ nên nằm ở service/domain boundary để REST controller, message consumer, scheduled job và GraphQL cùng dùng một policy.

Ví dụ:

~~~java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @PreAuthorize("@bookAuthorization.canRead(authentication, #p0)")
    public Book findVisibleById(UUID bookId) {
        return bookRepository.findVisibleById(
                bookId, SecurityContextHolder.getContext()
                    .getAuthentication().getName())
            .orElseThrow(BookNotFoundException::new);
    }
}
~~~

Trong code thực tế, tránh lấy SecurityContext thủ công nếu service đang chạy reactive. Có thể truyền principal/user scope đã xác thực vào service một cách tường minh, hoặc dùng cơ chế method security phù hợp với stack. Mục tiêu là không lấy user identity từ argument của client.

Controller chỉ chuyển dữ liệu đã bind:

~~~java
@QueryMapping
public Book bookById(@Argument("id") UUID bookId) {
    return bookQueryService.findVisibleById(bookId);
}
~~~

Nếu service có thể được gọi từ nhiều nơi, đặt authorization ở service giúp giảm nguy cơ một entry point mới quên kiểm tra quyền. Có thể thêm method security ở resolver như lớp bảo vệ sớm, nhưng không nên để policy quan trọng chỉ tồn tại ở controller.

## 6. Authorization theo tenant argument

Một API đa tenant có thể nhận tenant ID:

~~~graphql
type Query {
    booksByTenant(tenantId: ID!): [Book!]!
}
~~~

Không được tin tenantId do client truyền. Server cần xác định principal hiện tại có membership hoặc role phù hợp với tenant đó:

~~~java
@Component("tenantAuthorization")
public class TenantAuthorization {

    private final TenantMembershipRepository membershipRepository;

    public TenantAuthorization(
            TenantMembershipRepository membershipRepository) {
        this.membershipRepository = membershipRepository;
    }

    public boolean canRead(Authentication authentication, UUID tenantId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }
        return membershipRepository.existsActiveMembership(
            authentication.getName(), tenantId, "BOOK_READ");
    }
}
~~~

~~~java
@QueryMapping
@PreAuthorize("@tenantAuthorization.canRead(authentication, #p0)")
public List<Book> booksByTenant(@Argument("tenantId") UUID tenantId) {
    return bookService.findByTenant(tenantId);
}
~~~

Trong một số hệ thống, tenant hiện tại được chọn trong session/token và không cần client gửi tenant ID trên từng field. Nếu API cho phép client chuyển tenant, server vẫn phải kiểm tra membership cho mỗi operation.

Khi truy vấn database, nên scope query theo tenant đã xác thực thay vì tải tất cả rồi lọc trong Java. Ví dụ repository nên nhận cả tenantId và resource ID để câu truy vấn chỉ trả record thuộc tenant được phép. Cách này giảm nguy cơ lộ dữ liệu và tránh tải dữ liệu trái quyền vào memory.

## 7. Authorization với input object của mutation

Mutation thường nhận một input object chứa resource ID và các field cần thay đổi. Server phải kiểm tra quyền trên resource đích trước khi thực hiện side effect:

~~~java
public record UpdateBookInput(
        UUID bookId,
        String title,
        String description) {
}

@Service
public class BookCommandService {

    private final BookRepository bookRepository;

    public BookCommandService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    @PreAuthorize("@bookAuthorization.canEdit(authentication, #p0.bookId())")
    public Book update(UpdateBookInput input) {
        Book book = bookRepository.findEditableById(input.bookId())
            .orElseThrow(BookNotFoundException::new);

        if (input.title() != null) {
            book.rename(input.title());
        }
        if (input.description() != null) {
            book.changeDescription(input.description());
        }
        return bookRepository.save(book);
    }
}
~~~

Trong SpEL, record component có thể được truy cập qua property/accessor. Nếu biểu thức không phân giải được tên component theo cấu hình hiện tại, dùng accessor phù hợp hoặc truyền resource ID riêng vào service method để biểu thức rõ ràng.

Chỉ cho phép thay đổi các field thuộc contract. Không bind trực tiếp toàn bộ entity rồi lưu, vì input có thể chứa field như ownerId, tenantId, role hoặc isPublished mà client không được phép tự gán. Đây là rủi ro mass assignment.

Đối với mutation, authorization phải xảy ra trước side effect. Không dùng @PostAuthorize làm lớp bảo vệ duy nhất cho thao tác ghi, vì annotation đó kiểm tra sau khi method đã chạy và side effect có thể đã commit.

## 8. Authorization theo nhiều argument

Một field có thể nhận nhiều argument cùng ảnh hưởng đến quyết định quyền:

~~~graphql
type Query {
    invoice(
        tenantId: ID!
        invoiceId: ID!
        includeAudit: Boolean = false
    ): Invoice
}
~~~

Policy có thể cần xác minh principal thuộc tenant, invoice thuộc tenant đó và người gọi có quyền đọc audit data nếu includeAudit là true.

~~~java
@QueryMapping
public Invoice invoice(
        @Argument("tenantId") UUID tenantId,
        @Argument("invoiceId") UUID invoiceId,
        @Argument("includeAudit") boolean includeAudit,
        Principal principal) {

    return invoiceQueryService.findVisibleInvoice(
        principal.getName(), tenantId, invoiceId, includeAudit);
}
~~~

Service nên kiểm tra các điều kiện cùng một policy:

~~~java
public Invoice findVisibleInvoice(
        String username,
        UUID tenantId,
        UUID invoiceId,
        boolean includeAudit) {

    authorization.requireTenantMembership(username, tenantId);
    Invoice invoice = repository.findByIdAndTenant(invoiceId, tenantId)
        .orElseThrow(InvoiceNotFoundException::new);
    authorization.requireCanReadInvoice(username, invoice);

    if (includeAudit) {
        authorization.requireAuditAccess(username, tenantId);
    }
    return invoice;
}
~~~

Ví dụ trên truyền principal đã xác thực từ Spring Security vào service. Không thay username bằng một argument userId do client tự gửi. Nếu field có nhiều argument, một DTO nhận bằng @Arguments hoặc input object có thể giúp giữ chữ ký method gọn, nhưng policy vẫn phải kiểm tra từng thuộc tính có ảnh hưởng đến quyền.

## 9. Authorization cho nested field

GraphQL cho phép field lồng nhau có argument riêng:

~~~graphql
type Book {
    id: ID!
    reviews(visibility: ReviewVisibility = PUBLIC): [Review!]!
}
~~~

Resolver Book.reviews phải kiểm tra quyền dựa trên source object Book và argument visibility. Người dùng không thể yêu cầu visibility INTERNAL chỉ vì schema cho phép giá trị enum đó:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
@PreAuthorize("@reviewAuthorization.canRead(authentication, #p0.id(), #p1)")
public List<Review> reviews(
        Book book,
        @Argument("visibility") ReviewVisibility visibility) {

    return reviewService.findVisibleReviews(book.id(), visibility);
}
~~~

Trong biểu thức method security, #p0 là source object đầu tiên và #p1 là argument thứ hai theo thứ tự tham số Java. Có thể đặt tên rõ bằng @P nếu cần tránh phụ thuộc vào parameter metadata. Source object do server phân giải, nhưng vẫn cần kiểm tra quyền vì dữ liệu parent có thể được truy cập qua nhiều đường khác nhau.

Một nested field có thể được gọi nhiều lần trong cùng operation với argument khác nhau. Mỗi lần resolve phải được authorization theo đúng source object và argument tương ứng.

## 10. Alias và cùng field với nhiều argument

GraphQL cho phép gọi cùng field nhiều lần bằng alias:

~~~graphql
query {
    ownBook: bookById(id: "book-01") {
        id
        title
    }
    anotherBook: bookById(id: "book-02") {
        id
        title
    }
}
~~~

Hai alias tạo hai response key và có thể kích hoạt hai lần resolve với argument khác nhau. Không nên kiểm tra quyền một lần cho toàn operation rồi mặc định mọi lần gọi cùng field đều được phép. Authorization phải gắn với resource ID thực tế ở mỗi lần gọi.

Tương tự, không cache kết quả authorization chỉ bằng tên field hoặc role nếu quyết định còn phụ thuộc resource ID, tenant hoặc argument khác. Nếu có cache policy, key phải bao gồm đủ thuộc tính ảnh hưởng đến quyết định và thời gian hiệu lực phải phù hợp với thay đổi quyền.

## 11. Kết hợp role-based và attribute-based authorization

Role/authority có thể kiểm tra quyền tổng quát:

~~~java
@PreAuthorize("hasAuthority('books:read')")
~~~

Nhưng quyền đọc sách có thể còn phụ thuộc ownership, tenant hoặc trạng thái:

~~~java
@PreAuthorize("""
    hasAuthority('books:read')
    and @bookAuthorization.canRead(authentication, #p0)
    """)
~~~

Điều này kết hợp RBAC và ABAC:

- RBAC kiểm tra principal có authority chung hay không.
- ABAC kiểm tra resource cụ thể có nằm trong phạm vi của principal hay không.

Không nên nhét toàn bộ logic phức tạp vào một biểu thức SpEL dài. Đặt policy trong component chuyên trách để dễ kiểm thử, theo dõi và tái sử dụng. SpEL nên đóng vai trò gọi policy, không phải nơi chứa hàng chục điều kiện truy vấn dữ liệu.

## 12. DataLoader và authorization theo key

DataLoader gom các key để giảm N+1. Tuy nhiên, batch loader không được bỏ qua authorization chỉ vì nó nhận nhiều ID trong một lần gọi.

Ví dụ, một field Book.author dùng DataLoader để tải tác giả theo ID. Batch query phải chỉ trả tác giả mà principal hiện tại được phép xem. Nếu dữ liệu phụ thuộc tenant, batch loader phải nhận tenant scope đáng tin cậy từ security/GraphQL context và áp dụng điều kiện đó cho toàn bộ truy vấn.

Không dùng tenantId do client truyền trực tiếp làm scope của cache hoặc batch query. Hãy suy ra tenant từ principal đã xác thực hoặc xác minh membership trước khi sử dụng.

DataLoader cache thường có phạm vi một GraphQL execution/request. Tuy nhiên, key chỉ là author ID có thể không đủ nếu kết quả phụ thuộc tenant hoặc policy. Trong trường hợp đó, cần bảo đảm một execution chỉ có một security scope nhất quán hoặc dùng key chứa đủ thuộc tính ảnh hưởng đến kết quả. Không chia sẻ DataLoader instance/cache giữa các principal.

Authorization theo field cũng cần áp dụng với nested fields được tải qua DataLoader. Có thể lọc dữ liệu ngay trong batch query hoặc kiểm tra quyền trước khi trả value. Tránh tải dữ liệu nhạy cảm trái quyền vào resolver rồi hy vọng client không chọn field đó.

## 13. Async và reactive authorization

Resolver có thể trả CompletableFuture, Mono hoặc Flux. Khi method security được dùng, cần cấu hình đúng cho imperative hay reactive stack:

- Với Spring MVC/imperative, method security thường dựa trên SecurityContext hiện tại.
- Với WebFlux/reactive, SecurityContext được truyền qua Reactor Context.
- Khi chuyển sang executor hoặc CompletableFuture thủ công, không giả định ThreadLocal tự động theo sang thread khác.

Ví dụ reactive service:

~~~java
@PreAuthorize("hasAuthority('books:read')")
public Mono<Book> findVisibleBook(UUID bookId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
            bookRepository.findVisibleById(
                bookId, authentication.getName()));
}
~~~

Đây là minh họa cho việc lấy security context trong reactive chain. Nếu method được bảo vệ bằng reactive method security, hãy để framework áp dụng authorization và giữ mọi thao tác trong publisher; không gọi block() để lấy principal hoặc kết quả quyền.

Với CompletableFuture, có thể truyền user scope đã xác thực vào tác vụ async một cách tường minh hoặc cấu hình context propagation phù hợp. Không lưu Authentication vào biến static hoặc singleton mutable field để callback async đọc sau.

## 14. Authorization cho subscription argument

Subscription cũng nhận argument, ví dụ orderUpdated(orderId: ID!). Trước khi mở stream, server phải xác minh principal được phép theo dõi order đó:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderUpdated(
        @Argument("orderId") UUID orderId,
        Principal principal) {

    String username = principal.getName();
    return orderAuthorization.assertCanReadOrder(username, orderId)
        .thenMany(orderEventService.eventsForOrder(orderId));
}
~~~

Với stream nhạy cảm hoặc quyền có thể thay đổi, kiểm tra lúc subscribe chưa đủ. Cần lọc theo từng event hoặc kết hợp tín hiệu thu hồi quyền để kết thúc stream. Không dùng orderId hoặc tenant ID từ client để đăng ký topic nếu chưa xác minh quyền.

## 15. Forbidden hay Not Found?

Khi resource tồn tại nhưng người gọi không có quyền, API có thể trả FORBIDDEN. Tuy nhiên, trong một số hệ thống, việc phân biệt resource không tồn tại với resource tồn tại nhưng bị cấm có thể làm lộ thông tin.

Hai policy thường gặp:

| Policy | Hành vi | Khi phù hợp |
| --- | --- | --- |
| Phân biệt NOT_FOUND và FORBIDDEN | Client biết resource không tồn tại hay không có quyền | Resource không nhạy cảm và sản phẩm cần phân biệt |
| Che sự tồn tại | Trả NOT_FOUND hoặc thông báo chung cho cả hai trường hợp | Resource nhạy cảm, cần chống enumeration |

Chọn một policy nhất quán và ánh xạ bằng GraphQL error code ổn định. Không để message hoặc timing vô tình tiết lộ thông tin mà policy muốn che.

## 16. @PostAuthorize và giới hạn của nó

@PostAuthorize kiểm tra kết quả sau khi method thực thi. Nó có thể hữu ích cho một số query khi quyền phụ thuộc vào object được trả về:

~~~java
@PostAuthorize("@bookAuthorization.canRead(authentication, returnObject)")
public Book loadBook(UUID bookId) {
    return repository.findById(bookId).orElseThrow();
}
~~~

Tuy nhiên, method đã tải object trước khi kiểm tra. Điều này có thể không phù hợp nếu việc tải đã kích hoạt side effect, ghi audit, truy cập hệ thống nhạy cảm hoặc làm lộ dữ liệu qua log/cache. Với mutation, @PostAuthorize không thể hoàn tác side effect đã thực hiện.

Ưu tiên @PreAuthorize khi có thể kiểm tra quyền từ ID/argument trước khi gọi service. Nếu phải tải resource để biết thuộc tính cần kiểm tra, hãy thực hiện kiểm tra trong service/domain trước khi trả object hoặc thay đổi dữ liệu, đồng thời bảo đảm truy vấn chỉ đọc trong phạm vi phù hợp.

## 17. Kiểm thử authorization theo argument

Kiểm thử cần bao phủ cả trường hợp được phép và bị từ chối. Chỉ test user không đăng nhập là chưa đủ; lỗi BOLA thường xảy ra khi người dùng đã đăng nhập nhưng thay ID hoặc tenant trong argument.

Với GraphQlTester, gửi operation và xác nhận dữ liệu cho principal phù hợp:

~~~java
graphQlTester.document("""
        query($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-01")
    .execute()
    .path("bookById.id")
    .entity(String.class)
    .isEqualTo("book-01");
~~~

Test cần được cấu hình với principal đã xác thực. Với integration test qua HTTP, dùng security test support của stack đang chạy, chẳng hạn MockMvc/Spring Security Test cho servlet hoặc WebTestClient/security test support cho reactive. GraphQlTester chạy trực tiếp trên GraphQL service có thể không đi qua toàn bộ HTTP security filter chain; hãy chọn tester phù hợp với lớp bảo vệ cần kiểm chứng.

Các trường hợp nên kiểm thử:

1. User A đọc resource thuộc A thành công.
2. User A đổi argument ID sang resource của User B thì bị từ chối.
3. User thuộc tenant A không đọc resource của tenant B.
4. Authority tổng quát có nhưng không sở hữu resource vẫn bị từ chối.
5. Mutation không thực hiện side effect khi authorization thất bại.
6. Input không thể tự đổi ownerId, tenantId hoặc role trái quyền.
7. Nested field có argument nhạy cảm được kiểm tra theo source object và argument.
8. Cùng field gọi bằng nhiều alias với ID khác nhau được kiểm tra riêng.
9. DataLoader/batch query không trả dữ liệu chéo tenant.
10. Subscription không mở topic trái quyền và dừng khi quyền bị thu hồi theo policy.
11. Forbidden/Not Found tuân thủ policy chống enumeration.
12. Async/reactive resolver vẫn dùng đúng security context.

Ngoài response, kiểm tra repository/service không được gọi hoặc không có thay đổi dữ liệu khi request bị từ chối. Với mutation, assert số bản ghi và trạng thái trước/sau để chứng minh side effect không xảy ra.

## 18. Lỗi thường gặp

| Cách làm sai | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Tin id do client gửi | Người dùng đọc/sửa resource của người khác | Kiểm tra ownership/tenant theo principal |
| Dùng userId/tenantId trong input làm danh tính | Client giả mạo scope | Lấy identity từ SecurityContext đã xác thực |
| Chỉ kiểm tra role tổng quát | Bỏ sót quyền trên object cụ thể | Kết hợp RBAC với ABAC/object-level check |
| Chỉ bảo vệ root query | Nested field vẫn có thể lộ dữ liệu | Bảo vệ từng field nhạy cảm và service tương ứng |
| Dùng @PostAuthorize cho mutation | Side effect đã xảy ra trước khi từ chối | Kiểm tra trước side effect bằng @PreAuthorize/service policy |
| Bind toàn bộ entity từ input | Mass assignment thay đổi field nhạy cảm | Dùng input DTO allowlist và mapping tường minh |
| Cache quyết định chỉ theo field name | Kết quả quyền của resource khác bị tái sử dụng | Cache theo principal, action, resource và scope nếu thật sự cần |
| Batch loader bỏ qua tenant filter | Rò dữ liệu qua DataLoader | Áp dụng scope/authorization trong batch query |
| SecurityContext mất trong async | Resolver chạy với context thiếu hoặc sai | Dùng Reactor Context hoặc context propagation phù hợp |
| Chỉ test anonymous user | Không phát hiện BOLA giữa hai user hợp lệ | Test đổi ID và truy cập chéo tenant |
| Trả lỗi khác nhau làm lộ resource | Resource enumeration | Áp dụng NOT_FOUND/FORBIDDEN policy thống nhất |

## 19. Nguyên tắc thiết kế

Xem mọi GraphQL argument là dữ liệu do client kiểm soát. Dùng @Argument hoặc @Arguments để bind dữ liệu, nhưng quyết định quyền dựa trên principal đã xác thực, action, resource và tenant từ nguồn tin cậy. Kết hợp authority tổng quát với policy object-level; đặt quy tắc quan trọng ở application service/domain để mọi entry point cùng tuân thủ.

Kiểm tra quyền trước side effect, giới hạn query theo tenant/resource và chỉ cho phép input DTO chứa các field client thực sự được phép thay đổi. Bảo vệ nested field, xử lý từng alias/argument độc lập và giữ authorization trong DataLoader/async/reactive flow. Dùng GraphQlTester để kiểm thử cả truy cập hợp lệ, IDOR/BOLA, cross-tenant, mutation side effects và error disclosure.

Trong Spring for GraphQL, argument cho biết client muốn làm gì và muốn truy cập tài nguyên nào. Chỉ authorization service dựa trên danh tính và policy của server mới có thể quyết định request đó có được phép hay không.
