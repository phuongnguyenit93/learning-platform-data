# SecurityContext trong DataLoader

DataLoader giúp Spring for GraphQL gom nhiều lần tải dữ liệu liên quan thành một batch để giảm N+1. Tuy nhiên, một batch loader thường truy cập dữ liệu theo ID và chạy bất đồng bộ. Nếu dữ liệu phụ thuộc vào người dùng đang đăng nhập, tenant hoặc quyền truy cập, loader phải giữ đúng ngữ cảnh bảo mật của GraphQL request.

Ví dụ, một query tải danh sách tài liệu và mỗi tài liệu có field owner, comments hoặc privateNotes. Hai người dùng có thể truy vấn cùng một document ID nhưng chỉ một người được xem ghi chú riêng tư. Batch loader phải lọc dữ liệu theo danh tính và quyền của request hiện tại, đồng thời không để cache trả kết quả đã được tải trong một phạm vi quyền khác.

**SecurityContext trong DataLoader** là cách bảo đảm thông tin xác thực và phạm vi truy cập được truyền tới batch loading function, để mỗi lần tải dữ liệu vẫn áp dụng đúng authorization. Spring for GraphQL hỗ trợ việc này qua Principal trong annotated controller, GraphQLContext và BatchLoaderEnvironment, cùng cơ chế context propagation cho MVC và WebFlux.

## Phân biệt SecurityContext, Authentication, Principal và GraphQLContext

Các khái niệm này liên quan nhưng không thay thế cho nhau:

| Thành phần | Vai trò |
| --- | --- |
| SecurityContext | Chứa thông tin bảo mật của lần thực thi hiện tại, thường gồm Authentication |
| Authentication | Đại diện cho danh tính đã xác thực và các authority được cấp |
| Principal | Giao diện biểu diễn danh tính; trong Spring GraphQL có thể được inject từ Spring Security context |
| GraphQLContext | Context key/value gắn với một GraphQL execution, dùng để truyền metadata tới resolver và batch loader |
| BatchLoaderEnvironment | Context của GraphQL Java được truyền tới BatchLoaderWithContext; cung cấp GraphQLContext chung và local context theo từng key |

Spring for GraphQL cho phép annotated controller nhận java.security.Principal hoặc @AuthenticationPrincipal. Với @BatchMapping, method cũng có thể nhận Principal, GraphQLContext, @ContextValue hoặc BatchLoaderEnvironment.

GraphQLContext không tự động đồng nghĩa với SecurityContext. GraphQLContext là nơi truyền metadata của execution; danh tính và quyền vẫn do Spring Security quản lý. Khi batch loader cần tenant hoặc subject, hãy đưa thông tin cần thiết vào GraphQLContext hoặc key theo cách có kiểm soát, và tiếp tục kiểm tra quyền ở service.

## Vì sao batch loader cần security context?

Giả sử ứng dụng có schema:

~~~graphql
type Query {
  documents: [Document!]!
}

type Document {
  id: ID!
  title: String!
  privateNotes: [Note!]!
}

type Note {
  id: ID!
  content: String!
}
~~~

Một người dùng có thể xem tài liệu nhưng chỉ được xem privateNotes nếu là owner hoặc thành viên có quyền. Resolver tải notes cho nhiều document có thể dùng DataLoader để giảm số truy vấn:

~~~java
public record NoteGroup(List<Note> notes) {
}

@SchemaMapping
public CompletableFuture<List<Note>> privateNotes(
        Document document,
        DataLoader<String, NoteGroup> notesLoader) {
    return notesLoader.load(document.id())
            .thenApply(NoteGroup::notes);
}
~~~

Nếu batch loader chỉ truy vấn theo document ID mà không kiểm tra người dùng, nó có thể trả notes riêng tư cho bất kỳ ai biết ID. Việc dùng DataLoader không tự tạo authorization; nó chỉ gom và cache kết quả tải dữ liệu.

Một nguyên tắc quan trọng: **ủy quyền phải được áp dụng trong chính đường truy vấn dữ liệu**. Không dựa vào việc client không biết ID, không chỉ ẩn field trên giao diện và không giả định resolver cha đã kiểm tra quyền cho mọi field con.

## Lấy Principal trực tiếp trong @BatchMapping

Với trường hợp đơn giản, Spring for GraphQL cho phép nhận Principal trực tiếp trong phương thức @BatchMapping. Đây thường là cách rõ ràng nhất vì method thể hiện rõ danh tính được dùng để lọc batch:

~~~java
import java.security.Principal;
import java.util.List;
import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;

@Controller
public class DocumentBatchController {

    private final NoteService noteService;

    public DocumentBatchController(NoteService noteService) {
        this.noteService = noteService;
    }

    @BatchMapping(typeName = "Document", field = "privateNotes")
    public Map<Document, List<Note>> privateNotes(
            List<Document> documents,
            Principal principal) {

        if (principal == null) {
            throw new AccessDeniedException("Cần đăng nhập để xem ghi chú");
        }

        return noteService.findVisibleNotes(
                documents,
                principal.getName());
    }
}
~~~

Spring lấy Principal từ Spring Security context nếu có. NoteService nhận danh sách document và subject ID để truy vấn những ghi chú người dùng được phép xem. Batch handler trả map từ từng Document sang danh sách Note tương ứng.

Service vẫn phải thực hiện authorization và lọc dữ liệu:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;

@Service
public class NoteService {

    private final NoteRepository noteRepository;
    private final DocumentAccessService accessService;

    public NoteService(
            NoteRepository noteRepository,
            DocumentAccessService accessService) {
        this.noteRepository = noteRepository;
        this.accessService = accessService;
    }

    public Map<Document, List<Note>> findVisibleNotes(
            List<Document> documents,
            String subjectId) {

        Set<String> documentIds = documents.stream()
                .map(Document::id)
                .collect(Collectors.toSet());

        Set<String> allowedIds =
                accessService.findReadableDocumentIds(subjectId, documentIds);

        if (allowedIds.isEmpty()) {
            Map<Document, List<Note>> emptyResult = new HashMap<>();
            documents.forEach(document -> emptyResult.put(document, List.of()));
            return emptyResult;
        }

        Map<String, List<Note>> notesByDocument =
                noteRepository.findVisibleByDocumentIdsAndSubject(
                                allowedIds, subjectId)
                        .stream()
                        .collect(Collectors.groupingBy(Note::documentId));

        Map<Document, List<Note>> result = new HashMap<>();
        for (Document document : documents) {
            result.put(
                    document,
                    allowedIds.contains(document.id())
                            ? notesByDocument.getOrDefault(document.id(), List.of())
                            : List.of());
        }
        return result;
    }
}
~~~

Đoạn code minh họa quy trình: xác định tập document được phép truy cập, truy vấn notes trong một batch theo subject, rồi dựng kết quả cho từng source object. Nếu Document là entity class, hãy bảo đảm equals và hashCode ổn định vì @BatchMapping dùng source object làm key của map. Tùy chính sách API, tài nguyên không được phép có thể trả danh sách rỗng, null hoặc phát lỗi FORBIDDEN. Hãy chọn một semantics nhất quán và tránh tiết lộ tài nguyên có tồn tại hay không nếu đó là thông tin nhạy cảm.

## Khi cần principal có thuộc tính ứng dụng

Nếu ứng dụng có kiểu principal riêng, có thể đặt một đối tượng context đã được xác thực vào GraphQLContext tại ranh giới request, rồi đọc nó bằng @ContextValue trong batch mapping:

~~~java
public record CurrentUser(
        String userId) {
}
~~~

~~~java
@BatchMapping(typeName = "Document", field = "privateNotes")
public Map<Document, List<Note>> privateNotes(
        List<Document> documents,
        @ContextValue("currentUser") CurrentUser currentUser) {

    return noteService.findVisibleNotes(
            documents,
            currentUser.userId());
}
~~~

CurrentUser phải được tạo từ Authentication đã xác thực, không được bind từ argument do client gửi. Một WebGraphQlInterceptor hoặc lớp tích hợp bảo mật có thể đưa subject ID và tenant đã kiểm chứng vào GraphQLContext. Nếu không cần thêm thuộc tính riêng, nhận Principal trực tiếp vẫn đơn giản hơn.

Tránh chuyển toàn bộ Authentication hoặc token thô xuống mọi repository. Hãy trích subject ID, tenant ID và authority cần thiết thành dữ liệu nhỏ, rõ nghĩa.

## Truyền metadata bằng GraphQLContext và @ContextValue

Batch mapping method có thể nhận GraphQLContext hoặc @ContextValue. Đây là lựa chọn phù hợp khi ứng dụng đã chuẩn hóa metadata request như tenant ID, locale hoặc correlation ID trong một WebGraphQlInterceptor.

Ví dụ schema và resolver:

~~~java
@BatchMapping(typeName = "Document", field = "privateNotes")
public Map<Document, List<Note>> privateNotes(
        List<Document> documents,
        @ContextValue("tenantId") String tenantId,
        Principal principal) {

    return noteService.findVisibleNotes(
            documents,
            principal.getName(),
            tenantId);
}
~~~

Giá trị tenantId phải được thiết lập từ nguồn đáng tin cậy, chẳng hạn tenant gắn với principal đã xác thực hoặc token đã được kiểm tra. Không dùng một argument hay header tùy ý của client làm bằng chứng về tenant mà người dùng được phép truy cập.

Nếu cần đọc nhiều metadata, có thể nhận GraphQLContext:

~~~java
@BatchMapping(typeName = "Document", field = "privateNotes")
public Map<Document, List<Note>> privateNotes(
        List<Document> documents,
        GraphQLContext context,
        Principal principal) {

    String tenantId = context.get("tenantId");
    String locale = context.get("locale");

    return noteService.findVisibleNotes(
            documents,
            principal.getName(),
            tenantId,
            locale);
}
~~~

GraphQLContext của batch mapping là context của BatchLoaderEnvironment và cũng là context được cung cấp cho DataFetchingEnvironment. Hãy thiết lập metadata trước khi resolver chạy và ưu tiên đọc trong batch handler thay vì thay đổi context trong lúc các field đang thực thi.

## BatchLoaderRegistry và BatchLoaderEnvironment

Khi đăng ký DataLoader trực tiếp, Spring for GraphQL khuyến nghị dùng BatchLoaderRegistry thay vì tự tạo DataLoader ở một nơi không được quản lý. Registry đăng ký loader và tạo DataLoader tương ứng cho từng GraphQL request. Batch loading function có thể nhận BatchLoaderEnvironment:

~~~java
import graphql.GraphQLContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;

@Configuration
public class DocumentDataLoaderConfiguration {

    public DocumentDataLoaderConfiguration(
            BatchLoaderRegistry registry,
            NoteService noteService) {

        registry.forTypePair(String.class, NoteGroup.class)
                .registerMappedBatchLoader((documentIds, environment) -> {
                    GraphQLContext context = environment.getContext();
                    String tenantId = context.get("tenantId");

                    return noteService.findGroupsForTenant(
                            documentIds,
                            tenantId);
                });
    }
}
~~~

Ở đây NoteGroup là DTO bao bọc danh sách Note đã khai báo ở ví dụ trước. Phương thức findGroupsForTenant trả về publisher, chẳng hạn Mono<Map<String, NoteGroup>>, theo hợp đồng của registerMappedBatchLoader.

Resolver gọi DataLoader:

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;

@SchemaMapping(typeName = "Document", field = "privateNotes")
public CompletableFuture<List<Note>> privateNotes(
        Document document,
        DataLoader<String, NoteGroup> notesLoader) {

    return notesLoader.load(document.id())
            .thenApply(NoteGroup::notes);
}
~~~

Ví dụ trên minh họa việc lấy tenant từ GraphQLContext. Nếu batch function cần danh tính người dùng, có thể dùng Principal trong @BatchMapping, truyền subject ID qua key hoặc sử dụng SecurityContext đã được propagate vào execution theo web stack. GraphQLContext chỉ chứa SecurityContext nếu ứng dụng chủ động đưa nó vào; không nên giả định nó tự xuất hiện trong context.

BatchLoaderEnvironment cung cấp:

- context: GraphQLContext chung của execution, giống context được nhìn thấy từ DataFetchingEnvironment.
- keyContexts: local context đi kèm từng lần gọi DataLoader.load.

keyContexts hữu ích khi mỗi parent field có metadata riêng. Ví dụ một resolver con truyền local context chứa scope hoặc policy đã tính cho parent. Vì một batch có thể gom nhiều lần load từ các field khác nhau, batch function cần đọc đúng local context tương ứng từng key thay vì lấy một giá trị dùng chung cho toàn batch.

## Truyền SecurityContext qua MVC và WebFlux

GraphQL Java có thể thực thi data fetcher và batch loader bất đồng bộ, trên thread khác với thread nhận HTTP request. Vì vậy, không nên giả định SecurityContextHolder luôn có giá trị chỉ vì controller ban đầu đã có Principal.

Spring for GraphQL hỗ trợ context propagation từ transport tới GraphQL Java và các thành phần được gọi:

- Với Spring MVC, ThreadLocal context có thể được propagate sang thread thực thi data fetcher. Spring for GraphQL cung cấp SecurityContextThreadLocalAccessor, tự đăng ký qua ServiceLoader khi Spring Security có trên classpath.
- Với Spring WebFlux, security context nằm trong Reactor Context. Reactive data fetcher và batch loading function cần đọc nó trong reactive pipeline, không dựa vào ThreadLocal của một thread cố định.

Context propagation chỉ có tác dụng khi các thư viện và accessor tương ứng có mặt trên classpath và pipeline được giữ đúng. Nếu batch loader chuyển sang executor tự quản lý hoặc tự gọi subscribe(), context có thể không còn được gắn với công việc đó. Ưu tiên trả về Mono/CompletableFuture từ batch function và để Spring quản lý quá trình dispatch.

### Spring MVC: SecurityContextHolder

Với ứng dụng MVC, một batch loader đồng bộ có thể đọc Authentication từ SecurityContextHolder khi context propagation được cấu hình và hoạt động:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

registry.forTypePair(String.class, AccountSummary.class)
        .registerMappedBatchLoader((accountIds, environment) -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return CompletableFuture.failedFuture(
                        new AccessDeniedException("Không có danh tính hợp lệ"));
            }

            String subjectId = authentication.getName();
            return CompletableFuture.completedFuture(
                    accountService.findVisibleAccounts(accountIds, subjectId));
        });
~~~

Đây là ví dụ cho imperative batch loader. Nó chỉ an toàn khi SecurityContext được propagate tới execution thread. Nếu batch loader tự chuyển sang executor khác mà không có context propagation, SecurityContextHolder có thể rỗng hoặc mang giá trị không mong muốn. Khi đó hãy truyền subject ID rõ ràng qua key hoặc context thay vì dựa vào ThreadLocal.

### Spring WebFlux: ReactiveSecurityContextHolder

Với WebFlux, đọc SecurityContext từ Reactor Context bên trong publisher:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;

registry.forTypePair(String.class, AccountSummary.class)
        .registerMappedBatchLoader((accountIds, environment) ->
                ReactiveSecurityContextHolder.getContext()
                        .switchIfEmpty(Mono.error(
                                new AccessDeniedException(
                                        "Không có SecurityContext")))
                        .flatMap(securityContext -> {
                            Authentication authentication =
                                    securityContext.getAuthentication();

                            if (authentication == null
                                    || !authentication.isAuthenticated()
                                    || authentication instanceof AnonymousAuthenticationToken) {
                                return Mono.error(new AccessDeniedException(
                                        "Không có danh tính hợp lệ"));
                            }

                            return accountService.findVisibleAccounts(
                                    accountIds,
                                    authentication.getName());
                        }));
~~~

Đoạn code phải chạy trong reactive pipeline được Spring for GraphQL và Spring Security propagate context. Không gọi block() để lấy SecurityContext, không chuyển sang thread tùy ý rồi đọc ReactiveSecurityContextHolder bên ngoài publisher.

Nếu service cần principal trong nhiều nơi, hãy cân nhắc truyền subject ID thành tham số tường minh. Cách này làm dependency bảo mật rõ ràng và dễ kiểm thử hơn việc để mọi tầng tự đọc context ngầm.

## DataLoader key phải phản ánh phạm vi bảo mật

DataLoader cache kết quả theo key trong suốt GraphQL request. Nếu cùng một key luôn có cùng kết quả trong một request, cache có thể tái sử dụng an toàn. Nhưng nếu kết quả còn phụ thuộc tenant, subject, locale hoặc policy, key cần thể hiện những chiều làm thay đổi kết quả.

Ví dụ không đủ phạm vi:

~~~java
DataLoader<String, AccountSummary> accountLoader;
~~~

Nếu account có thể được truy vấn với các tenant khác nhau hoặc theo những quyền khác nhau trong cùng một execution, chỉ dùng accountId có thể làm cache trả lại kết quả không đúng phạm vi.

Dùng composite key bất biến:

~~~java
public record AccountAccessKey(
        String accountId,
        String subjectId,
        String tenantId) {
}
~~~

Resolver tạo key từ principal đã xác thực và tenant đáng tin cậy:

~~~java
@SchemaMapping(typeName = "Document", field = "account")
public CompletableFuture<AccountSummary> account(
        Document document,
        Principal principal,
        @ContextValue("tenantId") String tenantId,
        DataLoader<AccountAccessKey, AccountSummary> accountLoader) {

    AccountAccessKey key = new AccountAccessKey(
            document.accountId(),
            principal.getName(),
            tenantId);

    return accountLoader.load(key);
}
~~~

Batch loader nhận key đã chứa phạm vi:

~~~java
registry.forTypePair(AccountAccessKey.class, AccountSummary.class)
        .registerMappedBatchLoader((keys, environment) ->
                accountService.findVisibleAccounts(keys));
~~~

Composite key phải dùng dữ liệu định danh tối thiểu, bất biến và có equals/hashCode ổn định. Không đưa access token, mật khẩu hoặc toàn bộ Authentication vào key. Key là một phần cache identity, không phải bằng chứng thay thế cho authorization.

Nếu mọi load trong một GraphQL request chắc chắn dùng cùng một principal và tenant, key chỉ cần chứa những chiều có thể thay đổi kết quả trong request đó. Tuy nhiên, service vẫn phải kiểm tra quyền; không được xem composite key là lớp bảo mật duy nhất.

## Cache theo request không phải cache toàn ứng dụng

DataLoader do BatchLoaderRegistry đăng ký được tạo cho từng GraphQL request và có cache theo request. Điều này giúp cùng một key được tải một lần trong operation, nhưng không làm kết quả tự động an toàn cho cache toàn cục.

Phân biệt:

| Loại cache | Phạm vi | Lưu ý bảo mật |
| --- | --- | --- |
| DataLoader cache | Một GraphQL request | Vẫn phải thiết kế key đúng nếu kết quả khác nhau theo context/key |
| Application cache | Nhiều request | Key phải bao gồm tenant/subject/policy khi dữ liệu phụ thuộc quyền; cần TTL và invalidation |
| Database query cache | Phụ thuộc persistence/provider | Không dùng cache như lớp authorization |

Không giữ DataLoader trong singleton service, static field hoặc cache toàn cục. Không đăng ký DataLoader dùng chung giữa người dùng. Spring for GraphQL quản lý registry theo request để tránh chia sẻ cache giữa các GraphQL execution.

Nếu ứng dụng có cache service dùng chung, hãy xác định rõ dữ liệu nào là public, dữ liệu nào phụ thuộc tenant và dữ liệu nào phụ thuộc từng subject. Với dữ liệu nhạy cảm, chỉ cache sau khi đã xác định cache key và invalidation đáp ứng đúng mô hình quyền.

## Không tin tenant hoặc user ID từ client

GraphQL argument là dữ liệu do client gửi. Ví dụ:

~~~graphql
query {
  account(id: "acc-10", tenantId: "tenant-admin") {
    balance
  }
}
~~~

Server không được mặc định tenantId trong argument là tenant mà người dùng có quyền truy cập. Nếu API cần argument tenant để chọn resource, phải so sánh nó với tenant được xác thực hoặc kiểm tra quyền rõ ràng.

Tương tự, không dùng userId do client gửi để quyết định người dùng hiện tại. Danh tính phải đến từ Authentication/Principal đã được Spring Security xác thực. Dữ liệu do client cung cấp chỉ là target resource hoặc filter, không phải credential.

Ở tầng service hoặc repository, nên thực hiện truy vấn có giới hạn tenant và subject ngay trong câu truy vấn nếu có thể:

~~~java
List<Document> findVisibleDocuments(
        String tenantId,
        String subjectId,
        Collection<String> documentIds);
~~~

Điều này giúp tránh tải dữ liệu ngoài quyền rồi mới lọc ở Java. Nếu dùng database row-level security, tenant context cũng phải được thiết lập an toàn trong transaction và được dọn sạch khi transaction kết thúc.

## Authorization ở service và method security

Có thể dùng Spring Method Security để bảo vệ service:

Trong cấu hình bảo mật, bật method security bằng @EnableMethodSecurity nếu ứng dụng chưa bật:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Sau đó áp dụng annotation trên service:

~~~java
@Service
public class AccountService {

    @PreAuthorize("@accountAuthorization.canRead(authentication, #accountId)")
    public AccountSummary findById(String accountId) {
        return accountRepository.findSummaryById(accountId);
    }
}
~~~

Method security giúp tái sử dụng chính sách quyền ở nhiều entry point. Với batch method, hãy thiết kế authorization theo tập ID để tránh gọi một lần cho từng phần tử và tái tạo N+1 ở tầng security.

Ví dụ service batch nhận subject ID và tập account ID, sau đó truy vấn danh sách account mà subject được phép xem trong một lần. Nếu dùng @PreAuthorize trên method batch, biểu thức nên bảo vệ cả tập dữ liệu; kiểm tra chi tiết từng ID có thể nằm trong repository query hoặc policy service.

Không dựa vào việc field bị ẩn trong schema hoặc client không chọn field. GraphQL authorization cần được thực thi tại resolver, service hoặc tầng dữ liệu cho mọi đường truy cập có thể gọi tới dữ liệu.

## Xử lý không có quyền và dữ liệu không tồn tại

Một batch có thể chứa:

- Key hợp lệ và người dùng được phép truy cập.
- Key tồn tại nhưng người dùng không có quyền.
- Key không tồn tại.
- Key thuộc tenant khác.

Ứng dụng cần quyết định semantics thống nhất. Với dữ liệu nhạy cảm, trả NOT_FOUND cho cả tài nguyên không tồn tại và tài nguyên không được phép có thể tránh tiết lộ sự tồn tại. Với API nội bộ, FORBIDDEN có thể phù hợp hơn để client biết cần quyền bổ sung.

Không nên để batch loader trả một object khác chỉ để đủ số phần tử. Với MappedBatchLoader, key không có trong map sẽ cho kết quả null; schema nullability quyết định GraphQL xử lý tiếp như thế nào. Với BatchLoader dạng list, vị trí kết quả phải khớp với key đầu vào.

Nếu một key bị từ chối không có nghĩa cả batch đều thất bại, hãy xử lý theo từng key hoặc nhóm key và trả kết quả tương ứng. Nếu toàn bộ operation không thể tiếp tục do policy, phát lỗi có phân loại và không đưa chi tiết nội bộ ra response.

## Kiểm thử SecurityContext và DataLoader

Kiểm thử không chỉ xác nhận loader được gọi một lần. Cần chứng minh dữ liệu không bị rò giữa principal hoặc tenant:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| User A đọc document thuộc quyền A | Batch trả notes mà A được phép xem |
| User B truy vấn cùng document ID | Không nhận notes riêng tư của A |
| Hai tenant dùng cùng kiểu ID | Dữ liệu được giới hạn theo tenant |
| Nhiều key trong một batch | Repository nhận tập key và scope đúng |
| Cùng key được load nhiều lần trong request | Cache chỉ tái sử dụng trong cùng phạm vi quyền |
| Batch loader chạy bất đồng bộ | SecurityContext hoặc Reactor Context vẫn đúng |
| Principal không có quyền | Không trả dữ liệu nhạy cảm |
| Key không tồn tại | Kết quả theo đúng semantics null/NOT_FOUND |
| Client gửi tenantId giả | Service từ chối hoặc bỏ qua giá trị không đáng tin cậy |

Ví dụ kiểm thử service theo subject:

~~~java
@Test
void shouldOnlyLoadNotesVisibleToCurrentSubject() {
    List<Document> documents = List.of(documentA, documentB);

    Map<Document, List<Note>> result =
            noteService.findVisibleNotes(documents, "user-17");

    assertThat(result.get(documentA))
            .extracting(Note::id)
            .containsExactly("note-1");
    assertThat(result.get(documentB)).isEmpty();

    verify(noteRepository).findVisibleByDocumentIdsAndSubject(
            Set.of("doc-a"),
            "user-17");
}
~~~

Ở mức GraphQL integration test, tạo hai request với hai người dùng khác nhau, thực thi cùng một query có field được batch load và xác minh mỗi response chỉ chứa dữ liệu được phép. Có thể dùng Spring Security test support để thiết lập Authentication cho từng request. Chạy song song hai request giúp phát hiện lỗi lưu SecurityContext trong singleton hoặc dùng cache sai phạm vi.

Ngoài response, nên xác minh batch service được gọi theo nhóm thay vì một lần cho từng parent. Authorization và batching phải cùng hoạt động; không tối ưu truy vấn bằng cách bỏ qua kiểm tra quyền.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Principal có trong controller nhưng null trong batch loader | Context không được propagate tới thread thực thi | Dùng BatchLoaderRegistry, kiểm tra context propagation hoặc truyền subject rõ ràng |
| WebFlux đọc SecurityContextHolder nhưng không có dữ liệu | Reactive security context nằm trong Reactor Context | Dùng ReactiveSecurityContextHolder trong publisher |
| Batch trả dữ liệu của tenant khác | Tenant lấy từ client hoặc không được đưa vào truy vấn | Dùng tenant đã xác thực và lọc ở service/repository |
| Cùng ID trả kết quả không đúng scope | DataLoader key thiếu tenant/subject/filter ảnh hưởng kết quả | Dùng composite key bất biến |
| Cache hoạt động giữa nhiều request | Tự giữ DataLoader trong singleton/static field | Dùng BatchLoaderRegistry để đăng ký loader theo request |
| @BatchMapping không nhận Principal | Không có Spring Security context hoặc request chưa xác thực | Kiểm tra security chain và cấu hình authentication |
| Loader không đọc được metadata | Không có key trong GraphQLContext hoặc interceptor chạy sai thứ tự | Thiết lập metadata trước execution và kiểm tra tên key |
| Batch query tải quá nhiều dữ liệu | Lọc quyền sau khi tải toàn bộ bản ghi | Đưa tenant/subject condition vào query batch |
| Dùng Authentication làm cache key | Key chứa object không cần thiết hoặc mutable | Dùng subject ID và tenant ID bất biến |
| SecurityContext bị giữ sau request | Tự quản lý ThreadLocal không reset đúng | Dùng cơ chế context propagation của Spring và không lưu state vào singleton |

## Nguyên tắc thiết kế SecurityContext trong DataLoader

Khi sử dụng DataLoader với Spring for GraphQL, hãy áp dụng:

1. **Dùng Principal trực tiếp khi có thể.** @BatchMapping hỗ trợ Principal; với metadata principal tùy biến, dùng @ContextValue sau khi context đã được thiết lập từ danh tính đã xác thực.
2. **Dùng BatchLoaderRegistry cho loader tùy chỉnh.** Registry tạo DataLoader theo request và hỗ trợ GraphQLContext cùng context propagation.
3. **Phân biệt GraphQLContext với SecurityContext.** GraphQLContext chỉ có dữ liệu được đưa vào; không giả định nó tự chứa Authentication.
4. **Đọc context đúng web stack.** MVC dùng SecurityContextHolder khi propagation được thiết lập; WebFlux dùng ReactiveSecurityContextHolder trong reactive pipeline.
5. **Đưa scope cần thiết vào key.** Dùng subject ID, tenant ID hoặc filter bất biến nếu chúng làm thay đổi kết quả.
6. **Ủy quyền ở service hoặc query dữ liệu.** DataLoader chỉ batching và caching, không tự kiểm tra quyền.
7. **Giữ cache theo request.** Không dùng DataLoader singleton hoặc cache dùng chung giữa các người dùng.
8. **Không tin dữ liệu nhận dạng từ client.** Principal và tenant phải đến từ nguồn đã xác thực.
9. **Xử lý missing và forbidden nhất quán.** Tránh tiết lộ sự tồn tại của tài nguyên nhạy cảm.
10. **Kiểm thử isolation.** Chạy nhiều principal và tenant để chứng minh không có dữ liệu rò giữa request.

SecurityContext trong DataLoader bảo đảm batch loading thực thi dưới đúng danh tính và phạm vi quyền của GraphQL request. Với trường hợp thông thường, @BatchMapping có thể nhận Principal trực tiếp. Với loader tùy chỉnh, BatchLoaderRegistry cung cấp BatchLoaderEnvironment và GraphQLContext, đồng thời hỗ trợ context propagation. Hãy chọn đúng cách đọc SecurityContext cho MVC hoặc WebFlux, thiết kế key/cache theo tenant và subject khi kết quả phụ thuộc quyền, và luôn kiểm tra authorization ở service hoặc tầng dữ liệu. DataLoader có thể giảm N+1 mà vẫn bảo vệ được dữ liệu khi batching, caching và security được thiết kế như một cơ chế thống nhất.

## Tài liệu tham khảo

- [Spring for GraphQL - Annotated Controllers: Principal và BatchMapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - Request Execution: BatchLoaderRegistry và Context Propagation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL - SecurityContextThreadLocalAccessor API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/execution/SecurityContextThreadLocalAccessor.html)
- [Spring Security - SecurityContextHolderThreadLocalAccessor](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/SecurityContextHolderThreadLocalAccessor.html)
- [Spring Security - ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
