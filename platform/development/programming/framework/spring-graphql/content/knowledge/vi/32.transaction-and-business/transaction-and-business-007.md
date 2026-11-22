# DataLoader sau commit

Trong Spring for GraphQL, một mutation thường ghi dữ liệu trong transaction rồi trả về object để GraphQL tiếp tục resolve các field lồng nhau. Các field lồng nhau có thể dùng DataLoader để tải dữ liệu liên quan theo batch. Khi transaction của mutation đã commit trước lúc batch loader chạy, loader có thể đọc trạng thái đã lưu bền vững. Tuy nhiên, DataLoader vẫn giữ cache trong suốt request GraphQL, vì vậy một mutation tiếp theo trong cùng request có thể gặp dữ liệu cũ nếu cache không được làm mới.

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao transaction của mutation thường kết thúc trước khi GraphQL resolve các field con.
- Mô tả thời điểm DataLoader gom và dispatch các key trong GraphQL execution.
- Đăng ký batch loader bằng BatchLoaderRegistry.
- Dùng DataLoader trong @SchemaMapping để tải dữ liệu quan hệ.
- Phân biệt transaction của mutation với transaction của batch loader.
- Làm mới cache bằng clear(), clearAll() và prime() sau khi dữ liệu thay đổi.
- Đăng ký cache invalidation chỉ sau khi transaction commit thành công.
- Hiểu ảnh hưởng của nhiều root mutation fields trong cùng một request.
- Dùng @TransactionalEventListener cho side effect cần chạy sau commit.
- Tránh lazy-loading lỗi khi GraphQL resolve field sau khi transaction đã đóng.
- Kiểm thử dữ liệu mới, cache stale, commit và rollback bằng GraphQlTester.

## 1. Vì sao cần quan tâm DataLoader sau commit?

GraphQL cho phép client chọn field theo nhu cầu. Một mutation có thể tạo hoặc cập nhật object rồi trả object đó về để client chọn thêm các field lồng nhau.

Ví dụ:

~~~graphql
mutation {
  adjustBalance(accountId: "42", delta: 10) {
    id
    availableBalance {
      amount
      currency
    }
  }
}
~~~

Root field adjustBalance thay đổi số dư tài khoản. Field availableBalance được resolve sau khi GraphQL nhận object Account từ mutation. Resolver này có thể dùng DataLoader để đọc số dư theo account ID.

Một luồng xử lý điển hình:

1. GraphQL gọi mutation resolver.
2. Spring mở transaction cho method được đánh dấu @Transactional.
3. Ứng dụng cập nhật dữ liệu và trả object kết quả.
4. Transaction interceptor commit transaction khi method hoàn tất.
5. GraphQL tiếp tục resolve các field được client yêu cầu trên object kết quả.
6. Resolver field gọi DataLoader.load(key).
7. GraphQL Java dispatch các key đang chờ tới batch loader.
8. Batch loader đọc dữ liệu đã commit và hoàn tất các future.

DataLoader không phải transaction manager. Nó gom các yêu cầu đọc và cache kết quả trong phạm vi request. Ranh giới transaction được quyết định bởi Spring transaction management và cách ứng dụng thiết kế mutation.

## 2. GraphQL không tự định nghĩa transaction boundary

GraphQL specification mô tả cách operation được thực thi và response được tạo, nhưng không quy định một GraphQL request phải tương ứng với một database transaction.

Ứng dụng cần quyết định:

- Mỗi mutation root field có transaction riêng hay không.
- Nhiều thao tác nghiệp vụ có cần cùng một transaction hay không.
- Field lồng nhau đọc dữ liệu trong transaction riêng hay theo một unit of work lớn hơn.
- Side effect như gửi email, publish message hoặc evict cache chạy ở thời điểm nào.

Spring for GraphQL khuyến nghị cách đơn giản là đặt transaction ở controller method thực hiện mutation hoặc service method được gọi từ mutation. Cách này tạo ranh giới rõ ràng: transaction bắt đầu khi method được gọi và kết thúc khi method trả về.

Ví dụ:

~~~java
@Controller
public class AccountController {

    @MutationMapping
    @Transactional
    public Account adjustBalance(
            @Argument String accountId,
            @Argument BigDecimal delta) {

        // Đọc và cập nhật account trong cùng transaction.
        return accountService.adjustBalance(accountId, delta);
    }
}
~~~

Transaction bao quanh lời gọi adjustBalance. Khi method hoàn tất, Spring commit hoặc rollback trước khi kết quả được trả lại cho GraphQL engine.

Các field lồng nhau được GraphQL resolve sau đó không tự động thuộc transaction của method mutation.

## 3. Transaction của mutation kết thúc trước nested field resolution

Giả sử schema có Account và Balance:

~~~graphql
scalar Decimal

type Mutation {
  adjustBalance(accountId: ID!, delta: Decimal!): Account!
}

type Account {
  id: ID!
  availableBalance: AccountBalance!
}

type AccountBalance {
  amount: Decimal!
  currency: String!
}
~~~

Decimal là custom scalar trong ví dụ này, được ứng dụng cấu hình để ánh xạ với java.math.BigDecimal. GraphQL chỉ có các scalar chuẩn như Int, Float và String; nếu dùng Decimal, server cần đăng ký scalar tương ứng.

Mutation resolver trả về Account. availableBalance là field riêng, có thể được ánh xạ bằng @SchemaMapping và DataLoader.

~~~java
@Controller
public class AccountController {

    private final AccountService accountService;

    public AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @MutationMapping
    @Transactional
    public Account adjustBalance(
            @Argument String accountId,
            @Argument BigDecimal delta) {

        return accountService.adjustBalance(
                Long.valueOf(accountId), delta);
    }
}
~~~

Khi adjustBalance trả về, transaction interceptor hoàn tất transaction. GraphQL sau đó mới tiếp tục resolve availableBalance theo selection set.

Điều này có một lợi ích quan trọng: batch loader có thể đọc trạng thái đã commit mà không phải giữ transaction ghi mở trong suốt quá trình GraphQL resolve toàn bộ object graph.

Nó cũng có một giới hạn: nếu field con cần đọc dữ liệu nhất quán với toàn bộ thao tác ghi trong cùng một transaction, transaction per mutation method không cung cấp bảo đảm đó. Khi đó cần thiết kế lại unit of work, thường bằng cách thực hiện toàn bộ thao tác cần tính nguyên tử trong một service method và trả về DTO đã được chuẩn bị trong transaction.

## 4. Vì sao không nên giữ transaction mở cho toàn bộ GraphQL request?

GraphQL cho phép client yêu cầu nhiều field và các field được resolve độc lập. Giữ transaction mở từ đầu request đến khi toàn bộ nested fields hoàn tất có thể:

- Giữ connection và database resource lâu hơn cần thiết.
- Kéo dài thời gian giữ lock.
- Tăng nguy cơ deadlock hoặc tranh chấp.
- Làm transaction phụ thuộc vào resolver gọi service ngoài hoặc chờ DataLoader.
- Khó tương thích với execution bất đồng bộ và nhiều thread.

Với transaction đồng bộ dựa trên JDBC/JPA, Spring thường gắn transaction vào ThreadLocal. Nếu GraphQL thực thi DataFetcher bất đồng bộ trên nhiều thread, transaction không tự động lan truyền an toàn qua mọi field.

Spring for GraphQL có thể hỗ trợ transactional instrumentation để bao phủ toàn request, nhưng đây là chiến lược nâng cao. Nó yêu cầu execution strategy phù hợp và việc thực thi DataFetcher tuần tự trên cùng thread đối với transaction đồng bộ dựa trên ThreadLocal. Điều đó có thể làm giảm concurrency và kéo dài transaction.

Trong phần lớn ứng dụng, transaction per mutation method là lựa chọn dễ kiểm soát hơn. Nếu một nghiệp vụ cần cập nhật nhiều aggregate atomically, hãy tạo một mutation nhận đủ input và gọi một service method @Transactional thực hiện toàn bộ unit of work.

## 5. DataLoader trì hoãn batch load như thế nào?

DataLoader cung cấp API load(key) cho resolver. Lời gọi này thường trả về một CompletableFuture và đưa key vào hàng đợi thay vì truy vấn backend ngay lập tức.

Ví dụ:

~~~java
@SchemaMapping(typeName = "Account", field = "availableBalance")
public CompletableFuture<AccountBalance> availableBalance(
        Account account,
        DataLoader<Long, AccountBalance> balanceLoader) {

    return balanceLoader.load(account.id());
}
~~~

Khi GraphQL resolve nhiều Account, mỗi resolver gọi load(account.id()). Các key có thể được gom lại để batch loader đọc một lần.

Ví dụ client yêu cầu 3 account:

~~~graphql
query {
  accounts {
    id
    availableBalance {
      amount
      currency
    }
  }
}
~~~

Nếu có ba account với ID 10, 20 và 30, DataLoader có thể gom ba lần load thành một batch với các key:

~~~text
[10, 20, 30]
~~~

Batch loader trả về kết quả tương ứng với các key. DataLoader hoàn tất từng future và GraphQL dùng giá trị đó để xây dựng response.

Trong Spring for GraphQL, GraphQL Java quản lý dispatch trong quá trình thực thi. Không gọi dispatch() thủ công trong controller hoặc resolver thông thường.

## 6. BatchLoaderRegistry tạo DataLoader theo từng request

Spring for GraphQL cung cấp BatchLoaderRegistry để đăng ký batch loading function. Boot Starter tự cấu hình BatchLoaderRegistry và DefaultExecutionGraphQlService dùng registry này để tạo DataLoader registrations cho từng GraphQL request.

Ví dụ đăng ký loader cho AccountBalance:

~~~java
@Configuration
public class AccountLoaderConfiguration {

    public AccountLoaderConfiguration(
            BatchLoaderRegistry registry,
            AccountBalanceReadService readService) {

        registry.forTypePair(Long.class, AccountBalance.class)
                .registerMappedBatchLoader((accountIds, environment) ->
                        Mono.fromCallable(() ->
                                readService.findBalances(accountIds))
                            .subscribeOn(Schedulers.boundedElastic()));
    }
}
~~~

Ví dụ này giả định AccountBalanceReadService dùng Spring Data JPA hoặc một API blocking. Công việc được chuyển sang boundedElastic để không chạy JDBC blocking trên event-loop của WebFlux.

Read service:

~~~java
@Service
public class AccountBalanceReadService {

    private final AccountBalanceRepository repository;

    public AccountBalanceReadService(
            AccountBalanceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Map<Long, AccountBalance> findBalances(
            Set<Long> accountIds) {

        return repository.findAllByAccountIdIn(accountIds)
                .stream()
                .collect(Collectors.toMap(
                        AccountBalanceEntity::getAccountId,
                        entity -> new AccountBalance(
                                entity.getAmount(),
                                entity.getCurrency())));
    }
}
~~~

Transaction đọc trong findBalances là transaction riêng của batch query. Nó được mở khi read service chạy và kết thúc khi method trả về.

Với reactive repository như R2DBC, batch loader có thể trả trực tiếp Mono<Map<Long, AccountBalance>> mà không cần boundedElastic. Không bọc thao tác reactive vào fromCallable hoặc chuyển nó sang scheduler dành cho blocking work.

## 7. Dùng DataLoader trong @SchemaMapping

Field availableBalance không có property tương ứng trong Account DTO, vì vậy cần resolver riêng:

~~~java
@Controller
public class AccountBalanceController {

    @SchemaMapping(
            typeName = "Account",
            field = "availableBalance")
    public CompletableFuture<AccountBalance> availableBalance(
            Account account,
            DataLoader<Long, AccountBalance> balanceLoader) {

        return balanceLoader.load(account.id());
    }
}
~~~

DataLoader được Spring for GraphQL cung cấp từ DataLoaderRegistry của request hiện tại. Tên loader mặc định dựa trên kiểu giá trị đích, ở đây là AccountBalance. Có thể tùy chỉnh tên loader khi đăng ký nếu cần.

DataLoader per request giúp:

- Gom nhiều yêu cầu tải dữ liệu cùng loại.
- Tránh đọc lại cùng một key nhiều lần trong một request.
- Giữ cache và future không bị chia sẻ giữa người dùng khác nhau.
- Cho phép batch loader truy cập GraphQLContext qua BatchLoaderRegistry.

Không khai báo DataLoader thành singleton bean dùng chung giữa các request. DataLoader là object có state, queue và cache; việc chia sẻ loader có thể làm lộ dữ liệu hoặc trộn cache giữa người dùng.

## 8. DataLoader dispatch sau commit trong một mutation

Kết hợp các phần trên, luồng thực tế có thể là:

~~~mermaid
sequenceDiagram
    participant Client
    participant GraphQL as GraphQL execution
    participant Mutation as Mutation resolver
    participant DB as Database
    participant Field as Nested field resolver
    participant Loader as DataLoader
    participant Batch as Batch loader

    Client->>GraphQL: adjustBalance
    GraphQL->>Mutation: invoke method
    Mutation->>DB: update balance
    DB-->>Mutation: updated Account
    Mutation-->>GraphQL: method returns
    Note over DB,GraphQL: Spring commits transaction
    GraphQL->>Field: resolve availableBalance
    Field->>Loader: load(accountId)
    Loader->>Batch: dispatch queued keys
    Batch->>DB: read committed balance
    DB-->>Batch: AccountBalance
    Batch-->>Loader: complete future
    Loader-->>Field: balance
    Field-->>GraphQL: field value
    GraphQL-->>Client: mutation response
~~~

Thời điểm commit được đánh dấu sau khi mutation method trả về và trước khi GraphQL tiếp tục resolve nested fields theo transaction-per-controller-method strategy.

Batch loader đọc dữ liệu đã commit nếu nó truy vấn database sau bước này. Nếu batch loader dùng cache ứng dụng riêng, cache đó vẫn cần được invalidation theo chính sách của ứng dụng.

## 9. DataLoader cache tồn tại trong suốt request

DataLoader có cache memoization theo key. Spring for GraphQL đăng ký DataLoader theo từng request, nhưng cache của loader có thể tồn tại trong toàn bộ vòng đời request đó.

Điều này có ý nghĩa khi một GraphQL operation chứa nhiều root mutation fields. GraphQL thực thi các root mutation fields theo thứ tự. Các mutation fields trong cùng request vẫn dùng chung request context và DataLoader registry.

Ví dụ:

~~~graphql
mutation {
  first: adjustBalance(accountId: "42", delta: 10) {
    id
    availableBalance {
      amount
    }
  }

  second: adjustBalance(accountId: "42", delta: 5) {
    id
    availableBalance {
      amount
    }
  }
}
~~~

Giả sử số dư ban đầu là 100:

1. Mutation first cập nhật thành 110.
2. Nested field availableBalance tải và cache giá trị 110 theo key 42.
3. Mutation second cập nhật số dư thành 115.
4. Nếu DataLoader vẫn giữ cache key 42, nested field của second có thể nhận lại giá trị 110.
5. Nếu cache được clear sau khi transaction thứ hai commit, lần load tiếp theo sẽ lấy giá trị 115.

Đây là trường hợp điển hình cần làm mới DataLoader cache sau mutation.

## 10. Clear cache sau khi mutation commit

Java DataLoader cung cấp các thao tác cache:

| Method | Ý nghĩa |
|---|---|
| clear(key) | Xóa cache của một key |
| clearAll() | Xóa toàn bộ cache của loader |
| prime(key, value) | Đưa giá trị vào cache nếu key chưa có |
| clear(key).prime(key, value) | Xóa giá trị cũ rồi đưa giá trị mới vào cache |

Nếu một mutation cập nhật số dư account 42, chỉ cần clear key 42 của loader AccountBalance. Những account khác vẫn giữ cache.

Không nên clearAll() nếu biết chính xác key bị thay đổi và loader có thể đang cache nhiều dữ liệu khác.

clear(key) chỉ xóa cache entry để những lần load tiếp theo có thể gọi batch loader lại. Nó không hủy một future đã được trả về trước đó và không thay đổi kết quả của lần load đang chạy. Nếu cùng key có batch đang pending, cần thiết kế thứ tự thực thi để không nhầm một future cũ với dữ liệu mới.

## 11. Đăng ký invalidation bằng TransactionSynchronization

Nếu chỉ cần clear cache, có thể thực hiện ngay trong mutation method. Tuy nhiên, nếu muốn cache chỉ bị invalidated khi transaction commit thành công, hãy đăng ký callback afterCommit.

Ví dụ:

~~~java
@Controller
public class AccountController {

    private final AccountService accountService;

    public AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @MutationMapping
    @Transactional
    public Account adjustBalance(
            @Argument String accountId,
            @Argument BigDecimal delta,
            DataLoader<Long, AccountBalance> balanceLoader) {

        Long id = Long.valueOf(accountId);
        Account updated = accountService.adjustBalance(id, delta);

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        balanceLoader.clear(id);
                    }
                });

        return updated;
    }
}
~~~

Callback afterCommit chỉ được gọi sau khi transaction commit thành công. Nếu transaction rollback, callback không chạy và cache cũ vẫn được giữ.

Lỗi phát sinh trong afterCommit không thể rollback transaction đã commit. Tùy transaction manager và cách exception được truyền lên, GraphQL request vẫn có thể nhận lỗi dù thay đổi dữ liệu đã được lưu. Vì vậy callback này nên ngắn, chỉ làm thao tác trong bộ nhớ như clear(key), và không chứa công việc bên ngoài có thể thất bại hoặc kéo dài.

Đoạn code này giả định:

- Mutation method được gọi qua Spring proxy để @Transactional có hiệu lực.
- Transaction manager là loại đồng bộ, dựa trên thread-bound transaction.
- DataLoader được lấy từ request hiện tại và vẫn còn trong thời gian thực thi GraphQL.
- Callback chỉ làm cache invalidation trong bộ nhớ, không thực hiện ghi database.

TransactionSynchronizationManager.registerSynchronization yêu cầu transaction synchronization đang hoạt động. Không dùng cách này ngoài transaction hoặc trong reactive transaction chỉ dựa vào Reactor Context.

Nếu mutation method có thể được gọi ngoài transaction, hãy kiểm tra trạng thái synchronization và có fallback clear phù hợp. Với một mutation bắt buộc có transaction, nên giữ cấu hình và test bảo đảm transaction luôn hiện diện.

## 12. Clear ngay trong transaction hay clear sau commit?

Hai cách đều có thể đúng, tùy yêu cầu:

| Cách | Thời điểm | Ưu điểm | Lưu ý |
|---|---|---|---|
| clear(key) ngay sau update | Trước commit | Đơn giản, không cần synchronization callback | Cache bị clear cả khi transaction rollback; lần đọc sau sẽ tải lại dữ liệu đã commit |
| clear(key) trong afterCommit | Sau commit thành công | Chỉ invalidation khi ghi thành công | Chỉ phù hợp với transaction synchronization đúng loại và đúng lifecycle |
| clear(key).prime(key, value) | Sau khi có giá trị mới đáng tin cậy | Tránh batch read lại | Chỉ prime khi giá trị đầy đủ và đã commit |

Clear trước commit thường an toàn vì thao tác chỉ xóa cache trong request; nếu rollback, lần đọc sau sẽ lấy lại giá trị cũ từ database. Tuy nhiên, không prime cache bằng giá trị chưa commit vì nếu transaction rollback, DataLoader có thể giữ một giá trị không tồn tại trong database.

Nếu muốn giữ cache khi rollback và chỉ clear khi commit, dùng afterCommit như ví dụ trước.

## 13. Khi nào nên prime cache?

Prime phù hợp khi mutation đã có đầy đủ giá trị mà các resolver tiếp theo cần dùng.

Ví dụ mutation tạo một AccountBalance mới:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                balanceLoader.clear(accountId)
                        .prime(accountId, savedBalance);
            }
        });
~~~

prime() không ghi đè một cache entry đã tồn tại. Vì vậy, cần clear trước nếu key có thể đã được load trước đó trong cùng request.

Chỉ prime khi savedBalance là một projection đầy đủ và phản ánh trạng thái đã commit. Nếu database tự cập nhật cột, trigger, version hoặc giá trị tính toán sau khi save, nên clear và để batch loader đọc lại thay vì prime object có thể chưa đầy đủ.

Không dùng prime để che giấu lỗi consistency. Nếu mutation có side effect ngoài database hoặc một hệ thống khác chưa hoàn tất, giá trị prime cần phản ánh đúng trạng thái mà API cam kết với client.

## 14. Cache invalidation khi nhiều loader phụ thuộc cùng dữ liệu

Một thay đổi nghiệp vụ có thể ảnh hưởng nhiều DataLoader.

Ví dụ đổi customer address có thể ảnh hưởng:

- Customer loader theo customer ID.
- Address loader theo address ID.
- OrderSummary loader chứa địa chỉ giao hàng.
- Search result loader có dữ liệu đã denormalize.

Nếu mutation chỉ clear Customer loader nhưng các loader khác vẫn giữ cache liên quan, response tiếp theo trong cùng request có thể không nhất quán.

Nên xác định dependency graph của dữ liệu:

| Dữ liệu thay đổi | Loader cần xem xét |
|---|---|
| Account balance | AccountBalance loader, AccountSummary loader |
| Customer profile | Customer loader, CustomerProfile loader |
| Order status | Order loader, OrderSummary loader |
| Product price | Product loader, CartTotal loader |
| Address | Address loader, CustomerAddress loader, ShippingQuote loader |

Không nhất thiết clear mọi loader. Chỉ clear các key hoặc cache có thể bị ảnh hưởng. Với loader có nhiều key phức tạp, có thể dùng clearAll() nhưng cần cân nhắc số lần batch read tăng lên.

## 15. DataLoader cache không phải shared application cache

DataLoader cache chủ yếu tối ưu các lần load trùng key trong một GraphQL request. Nó không thay thế Redis, Caffeine hoặc cache dùng chung giữa nhiều request.

Phân biệt:

| Loại cache | Phạm vi | Khi nào invalidation |
|---|---|---|
| DataLoader memoization cache | Một GraphQL request | Clear khi mutation trong request làm dữ liệu cũ |
| Local application cache | Một instance ứng dụng | Evict sau commit hoặc theo TTL |
| Distributed cache | Nhiều instance | Publish invalidation hoặc cập nhật theo version |
| Database cache/buffer | Tầng database | Quản lý theo cơ chế của database |

Clear DataLoader không tự xóa Redis hoặc cache ở instance khác. Ngược lại, evict Redis cũng không xóa một DataLoader đã cache giá trị trong request đang chạy.

Với dữ liệu cần consistency mạnh, cần phối hợp cache invalidation ở mọi tầng có liên quan.

## 16. @TransactionalEventListener cho side effect sau commit

Một số công việc cần chạy sau khi transaction thành công:

- Gửi thông báo.
- Publish event sang message broker.
- Evict cache dùng chung.
- Cập nhật search index.
- Kích hoạt workflow khác.

Có thể publish Spring application event trong transaction và lắng nghe bằng @TransactionalEventListener:

~~~java
public record AccountBalanceChangedEvent(
        Long accountId,
        BigDecimal newBalance) {
}
~~~

Mutation service:

~~~java
@Service
public class AccountService {

    private final AccountRepository repository;
    private final ApplicationEventPublisher eventPublisher;

    public AccountService(
            AccountRepository repository,
            ApplicationEventPublisher eventPublisher) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Account adjustBalance(
            Long accountId,
            BigDecimal delta) {

        AccountEntity entity = repository.findById(accountId)
                .orElseThrow(AccountNotFoundException::new);

        entity.setBalance(entity.getBalance().add(delta));

        eventPublisher.publishEvent(
                new AccountBalanceChangedEvent(
                        accountId, entity.getBalance()));

        return new Account(entity.getId(), entity.getName());
    }
}
~~~

Listener:

~~~java
@Component
public class AccountBalanceChangedListener {

    private final AccountCache accountCache;

    public AccountBalanceChangedListener(
            AccountCache accountCache) {
        this.accountCache = accountCache;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onBalanceChanged(
            AccountBalanceChangedEvent event) {

        accountCache.evict(event.accountId());
    }
}
~~~

Nếu transaction rollback, listener AFTER_COMMIT không chạy. Nếu không có transaction đang hoạt động, transactional event listener mặc định không được gọi, trừ khi bật fallbackExecution.

Không nhầm listener AFTER_COMMIT với DataLoader dispatch. DataLoader được GraphQL execution dispatch khi các resolver gọi load(); transactional event listener chạy theo transaction lifecycle.

## 17. Cẩn thận khi ghi database trong AFTER_COMMIT listener

Khi listener chạy ở AFTER_COMMIT, transaction ban đầu đã commit. Transactional resources có thể vẫn còn được bind và truy cập được trong quá trình completion, nhưng mọi thay đổi database được thực hiện lúc này không được commit vào transaction cũ.

Nếu listener cần ghi database, hãy tạo transaction mới bằng propagation REQUIRES_NEW hoặc gọi một service method có transaction riêng.

Ví dụ:

~~~java
@Component
public class AccountAuditListener {

    private final AccountAuditService auditService;

    public AccountAuditListener(AccountAuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onBalanceChanged(
            AccountBalanceChangedEvent event) {

        auditService.record(event);
    }
}
~~~

Service:

~~~java
@Service
public class AccountAuditService {

    private final AccountAuditRepository repository;

    public AccountAuditService(AccountAuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(AccountBalanceChangedEvent event) {
        repository.save(new AccountAudit(
                event.accountId(),
                event.newBalance()));
    }
}
~~~

Listener gọi qua bean service khác để Spring transaction proxy áp dụng REQUIRES_NEW. Tránh self-invocation trong cùng bean vì lời gọi nội bộ có thể không đi qua proxy.

## 18. Khi cần publish message đáng tin cậy, cân nhắc Transactional Outbox

@TransactionalEventListener bảo đảm listener chỉ chạy sau commit trong process hiện tại. Nó không tự bảo đảm message sẽ được gửi thành công nếu ứng dụng crash ngay sau khi database commit nhưng trước khi publish tới broker.

Nếu cần bảo đảm sự kiện không bị mất, dùng Transactional Outbox:

1. Trong cùng transaction với thay đổi nghiệp vụ, ghi một bản ghi outbox.
2. Commit dữ liệu nghiệp vụ và outbox cùng nhau.
3. Một publisher riêng đọc outbox và gửi message.
4. Đánh dấu message đã publish hoặc dùng cơ chế retry.
5. Consumer xử lý idempotent để chịu được message trùng.

Ví dụ:

~~~java
@Transactional
public Account adjustBalance(
        Long accountId,
        BigDecimal delta) {

    AccountEntity account = accountRepository.findById(accountId)
            .orElseThrow(AccountNotFoundException::new);

    account.setBalance(account.getBalance().add(delta));

    outboxRepository.save(
            OutboxEvent.accountBalanceChanged(
                    accountId, account.getBalance()));

    return new Account(account.getId(), account.getName());
}
~~~

DataLoader không cần tham gia vào outbox. DataLoader giải quyết batching và request cache; outbox giải quyết độ tin cậy của việc phát sự kiện sau khi transaction commit.

## 19. Lazy loading và entity detached sau commit

Một vấn đề thường gặp với JPA là mutation trả về entity có quan hệ lazy. Khi transaction kết thúc, GraphQL tiếp tục resolve field lồng nhau. Nếu default property fetcher truy cập lazy association, ứng dụng có thể gặp LazyInitializationException.

Ví dụ:

~~~java
@Entity
public class AccountEntity {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;
}
~~~

Nếu mutation trả AccountEntity và field GraphQL customer được resolve bằng cách gọi getCustomer() sau commit, persistence context có thể đã đóng.

Cách xử lý:

- Trả DTO hoặc record chứa các ID cần thiết cho nested resolver.
- Dùng DataLoader để tải customer theo customer ID sau commit.
- Dùng projection hoặc query phù hợp trong transaction.
- Không giữ transaction mở chỉ để tránh lazy loading.
- Không serialize trực tiếp entity graph chưa được kiểm soát.

Ví dụ DTO:

~~~java
public record Account(
        Long id,
        String name,
        Long customerId) {
}
~~~

Nested resolver:

~~~java
@SchemaMapping(typeName = "Account", field = "customer")
public CompletableFuture<Customer> customer(
        Account account,
        DataLoader<Long, Customer> customerLoader) {

    return customerLoader.load(account.customerId());
}
~~~

DTO giữ đủ thông tin để DataLoader đọc dữ liệu cần thiết sau khi transaction mutation đã kết thúc.

## 20. Nhiều mutation trong cùng request và atomicity

GraphQL cho phép một operation Mutation có nhiều root fields. Các root mutation fields được thực thi tuần tự, nhưng điều đó không có nghĩa tất cả tự động nằm trong cùng một transaction.

Nếu mỗi controller method có @Transactional, mỗi root mutation method có thể có transaction riêng:

~~~graphql
mutation {
  first: reserveInventory(input: { productId: "p-1", quantity: 1 }) {
    id
  }

  second: chargePayment(input: { orderId: "o-1" }) {
    id
  }
}
~~~

Nếu reserveInventory commit thành công nhưng chargePayment thất bại, transaction đầu tiên không tự rollback chỉ vì mutation thứ hai thất bại.

Nếu hai bước cần atomicity, hãy thiết kế một mutation command:

~~~graphql
type Mutation {
  placeOrder(input: PlaceOrderInput!): Order!
}
~~~

Resolver gọi một service method @Transactional:

~~~java
@Service
public class OrderApplicationService {

    @Transactional
    public Order placeOrder(PlaceOrderInput input) {
        InventoryReservation reservation =
                inventoryService.reserve(input);

        Payment payment =
                paymentService.authorize(input);

        return orderService.create(input, reservation, payment);
    }
}
~~~

Các service được gọi tham gia transaction hiện tại theo propagation mặc định REQUIRED nếu cùng transaction manager và cùng thread-bound transaction.

Nếu cần giao dịch qua nhiều hệ thống như database, payment provider và message broker, database transaction đơn lẻ không tạo atomicity phân tán. Cần thiết kế saga, compensation hoặc outbox tùy nghiệp vụ.

## 21. Reactive transaction và DataLoader

Với Spring WebFlux và R2DBC, transaction có thể được quản lý bởi ReactiveTransactionManager. Transaction context nằm trong Reactor Context thay vì ThreadLocal thông thường.

Ví dụ service reactive:

~~~java
@Service
public class ReactiveAccountService {

    private final ReactiveAccountRepository repository;

    public ReactiveAccountService(
            ReactiveAccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Account> adjustBalance(
            Long accountId,
            BigDecimal delta) {

        return repository.findById(accountId)
                .switchIfEmpty(Mono.error(
                        new AccountNotFoundException(accountId)))
                .flatMap(account -> {
                    account.setBalance(
                            account.getBalance().add(delta));
                    return repository.save(account);
                })
                .map(account -> new Account(
                        account.getId(), account.getName()));
    }
}
~~~

Với reactive @Transactional, transaction được duy trì trong vòng đời publisher và hoàn tất khi publisher kết thúc. GraphQL adapter chờ publisher của mutation hoàn tất trước khi tiếp tục xử lý kết quả field.

Nếu cần invalidation sau reactive commit, hãy dùng reactive transaction synchronization hoặc sắp xếp thao tác clear sau khi publisher được TransactionalOperator hoàn tất. Ví dụ dưới đây minh họa ranh giới với TransactionalOperator:

~~~java
public Mono<Account> adjustBalance(
        Long accountId,
        BigDecimal delta,
        DataLoader<Long, AccountBalance> balanceLoader) {

    return transactionalOperator.transactional(
                    accountService.adjustBalanceInTransaction(
                            accountId, delta))
            .flatMap(updated ->
                    Mono.fromRunnable(() -> balanceLoader.clear(accountId))
                            .thenReturn(updated));
}
~~~

Trong ví dụ này, adjustBalanceInTransaction không tự mở một transaction khác; TransactionalOperator sở hữu transaction cho publisher. Publisher phía sau chỉ chạy sau khi transaction operator hoàn tất thành công. Nếu transaction lỗi hoặc rollback, bước clear không chạy.

Batch loader reactive có thể trả Mono<Map<K,V>>. Nó chạy trong transaction riêng nếu service đọc được đánh dấu @Transactional và dùng reactive transaction manager.

Không dùng TransactionSynchronizationManager dạng thread-bound để quản lý reactive transaction. Với transactional events trong Spring Framework 6.1 trở lên, reactive transaction context cần được truyền qua TransactionalEventPublisher theo hướng dẫn của Spring.

Không trộn JDBC/JPA blocking transaction với R2DBC reactive transaction rồi kỳ vọng chúng tự tham gia cùng một unit of work. Chọn một transaction model cho từng luồng xử lý hoặc thiết kế ranh giới rõ ràng giữa chúng.

## 22. Context của DataLoader và bảo mật theo request

Batch loader đôi khi cần thông tin về người dùng hiện tại, tenant hoặc quyền truy cập để lọc dữ liệu.

Spring for GraphQL khuyến nghị đăng ký loader qua BatchLoaderRegistry vì registry hỗ trợ chia sẻ GraphQLContext và context propagation tới batch loading functions.

Ví dụ:

~~~java
registry.forTypePair(Long.class, Customer.class)
        .registerMappedBatchLoader((customerIds, environment) -> {
            String tenantId =
                    environment.getGraphQlContext().get("tenantId");

            return customerService.findVisibleCustomers(
                    tenantId, customerIds);
        });
~~~

Batch loader cần bảo đảm mỗi key chỉ được truy cập trong phạm vi tenant hoặc principal hợp lệ. Không dựa vào việc DataLoader cache theo key ID là đủ để bảo mật.

Nếu loader key chỉ là customer ID nhưng kết quả còn phụ thuộc tenant, loader phải được tạo riêng theo request và query service phải áp dụng tenant filter. Không chia sẻ DataLoader giữa các request có principal khác nhau.

## 23. Kiểm thử DataLoader đọc dữ liệu sau commit

Một integration test có thể xác nhận nested field nhìn thấy giá trị đã commit.

Ví dụ mutation có hai root fields cập nhật cùng một account:

~~~graphql
mutation {
  first: adjustBalance(accountId: "42", delta: 10) {
    id
    availableBalance {
      amount
    }
  }

  second: adjustBalance(accountId: "42", delta: 5) {
    id
    availableBalance {
      amount
    }
  }
}
~~~

Giả sử số dư ban đầu là 100. Kết quả mong đợi:

| Field | Giá trị mong đợi |
|---|---:|
| first.availableBalance.amount | 110 |
| second.availableBalance.amount | 115 |

Test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class AccountMutationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Autowired
    AccountRepository accountRepository;

    @Test
    void shouldReloadBalanceAfterEachMutationCommit() {
        accountRepository.save(
                new AccountEntity(42L, "Main", new BigDecimal("100")));

        graphQlTester.document("""
                mutation {
                  first: adjustBalance(
                    accountId: "42",
                    delta: 10
                  ) {
                    id
                    availableBalance {
                      amount
                    }
                  }
                  second: adjustBalance(
                    accountId: "42",
                    delta: 5
                  ) {
                    id
                    availableBalance {
                      amount
                    }
                  }
                }
                """)
                .execute()
                .path("first.availableBalance.amount")
                .entity(BigDecimal.class)
                .isEqualTo(new BigDecimal("110"))
                .path("second.availableBalance.amount")
                .entity(BigDecimal.class)
                .isEqualTo(new BigDecimal("115"));
    }
}
~~~

Test giả định:

- Database test ban đầu có account ID 42 với số dư 100.
- Mỗi mutation commit trong transaction riêng.
- Callback afterCommit clear key 42 của DataLoader.
- Batch loader đọc số dư từ database sau commit.
- Test method không chạy trong transaction bao ngoài làm thay đổi lifecycle cần kiểm tra.

Nếu bỏ clear cache, mutation thứ hai có thể đọc lại giá trị đã cache từ mutation thứ nhất. Test này giúp phát hiện lỗi đó.

## 24. Kiểm thử rollback không làm prime dữ liệu chưa commit

Một test khác cần xác nhận mutation rollback không đưa dữ liệu chưa commit vào DataLoader cache.

Ví dụ service cập nhật dữ liệu rồi phát sinh exception:

~~~java
@Transactional
public Account adjustBalanceAndFail(
        Long accountId,
        BigDecimal delta) {

    AccountEntity account = repository.findById(accountId)
            .orElseThrow();

    account.setBalance(account.getBalance().add(delta));
    repository.save(account);
    repository.flush();

    throw new IllegalStateException("Simulated failure");
}
~~~

Ví dụ flush giả định repository là JpaRepository hoặc có phương thức tương đương. Việc flush buộc SQL chạy trong transaction trước khi exception phát sinh, giúp test xác nhận rollback của thay đổi đã được gửi tới database.

Nếu mutation thất bại:

- Transaction phải rollback.
- Callback afterCommit không chạy.
- Không prime giá trị chưa commit vào DataLoader.
- Database giữ số dư ban đầu.
- GraphQL response chứa error ở mutation field.

Test:

~~~java
@Test
void shouldRollbackAndKeepCommittedBalance() {
    graphQlTester.document("""
            mutation {
              adjustBalanceAndFail(
                accountId: "42",
                delta: 50
              ) {
                id
              }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors ->
                    assertThat(errors).isNotEmpty());

    AccountEntity account = accountRepository.findById(42L)
            .orElseThrow();

    assertThat(account.getBalance())
            .isEqualByComparingTo("100");
}
~~~

Không chạy test trong transaction bao ngoài nếu mục tiêu là xác nhận commit/rollback của request. Một test transaction bao ngoài có thể làm thay đổi cách transaction bên trong tham gia hoặc rollback.

## 25. Kiểm thử cache invalidation độc lập

Có thể kiểm tra trực tiếp DataLoader cache trong unit test:

~~~java
@Test
void shouldClearAndPrimeChangedValue() {
    DataLoader<Long, AccountBalance> loader =
            createAccountBalanceLoader();

    loader.prime(42L, new AccountBalance(
            new BigDecimal("100"), "VND"));

    loader.clear(42L).prime(
            42L,
            new AccountBalance(
                    new BigDecimal("115"), "VND"));

    AccountBalance value = loader.load(42L).join();

    assertThat(value.amount())
            .isEqualByComparingTo("115");
}
~~~

Ví dụ minh họa API cache của DataLoader. Trong GraphQL integration test, không tự tạo loader mới nếu muốn kiểm tra cache của request thật; hãy gọi nhiều mutation fields trong cùng một GraphQL operation và xác nhận kết quả.

Cũng nên kiểm tra:

- Cùng một key được load hai lần trong request chỉ gọi batch loader theo cache behavior mong muốn.
- clear(key) khiến lần load sau đọc lại dữ liệu.
- clearAll() làm mới toàn bộ key.
- prime() không ghi đè cache entry đã tồn tại.
- clear(key).prime(key, value) thay thế cache entry cũ.
- Request tiếp theo tạo DataLoader mới và không dùng cache của request trước.

## 26. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Nested field đọc dữ liệu cũ | DataLoader cache vẫn giữ key từ lần load trước | Clear key sau commit |
| Mutation commit nhưng DataLoader không thấy dữ liệu | Batch loader dùng cache ứng dụng hoặc replica có độ trễ | Invalidate cache, xem consistency và read routing |
| LazyInitializationException | GraphQL resolve lazy relation sau khi transaction đóng | Trả DTO/ID và dùng DataLoader |
| Cache bị xóa dù transaction rollback | Clear được gọi trước commit | Dùng afterCommit nếu chỉ muốn invalidate khi commit thành công |
| Cache chứa giá trị không tồn tại | Prime bằng entity chưa commit | Chỉ prime sau commit và khi giá trị đầy đủ |
| Mutation thứ hai nhận dữ liệu cũ | DataLoader cache dùng chung trong request | Invalidate giữa các mutation root fields |
| Transaction kéo dài | Transaction bao cả GraphQL request | Ưu tiên transaction per mutation method |
| Batch loader không có transaction | Loader chạy ngoài transaction mutation | Đặt read transaction riêng trong batch service nếu cần |
| JPA blocking trên event-loop | Batch loader gọi repository blocking trực tiếp trong WebFlux | Chuyển blocking work sang boundedElastic hoặc dùng R2DBC |
| DataLoader bị chia sẻ giữa người dùng | Loader được giữ thành singleton hoặc cache toàn cục | Dùng BatchLoaderRegistry per request |
| AFTER_COMMIT listener không chạy | Event được publish ngoài transaction hoặc transaction rollback | Kiểm tra transaction và fallbackExecution |
| Ghi DB trong AFTER_COMMIT không được lưu | Thay đổi tham gia resource đã commit nhưng không có transaction mới | Dùng REQUIRES_NEW |
| Message bị mất khi ứng dụng crash | Listener in-process không phải durable messaging | Dùng Transactional Outbox |

## 27. Checklist triển khai DataLoader sau commit

Trước khi đưa mutation và DataLoader vào production:

- [ ] Xác định rõ transaction boundary của mutation.
- [ ] Dùng transaction per controller/service method cho mutation thông thường.
- [ ] Không giả định nested field tự tham gia transaction của mutation.
- [ ] Đăng ký DataLoader qua BatchLoaderRegistry.
- [ ] Để GraphQL Java quản lý dispatch, không gọi dispatch() thủ công.
- [ ] Giữ DataLoader trong phạm vi từng GraphQL request.
- [ ] Dùng DTO hoặc ID để nested resolver không phụ thuộc lazy entity sau commit.
- [ ] Xác định loader key nào bị ảnh hưởng bởi mutation.
- [ ] Clear đúng key sau commit khi dữ liệu đã thay đổi.
- [ ] Chỉ prime giá trị đầy đủ và đã commit.
- [ ] Xem xét nhiều root mutation fields trong cùng request.
- [ ] Tách transaction đọc của batch loader khỏi transaction ghi của mutation khi cần.
- [ ] Không chạy JDBC/JPA blocking trên event-loop.
- [ ] Bảo đảm batch loader áp dụng tenant và authorization filter.
- [ ] Dùng @TransactionalEventListener cho side effect phụ thuộc commit.
- [ ] Dùng REQUIRES_NEW nếu AFTER_COMMIT listener cần ghi database.
- [ ] Dùng outbox nếu cần publish message đáng tin cậy.
- [ ] Có integration test cho commit, rollback và stale cache.

## Kết luận

DataLoader và transaction giải quyết hai vấn đề khác nhau. Transaction bảo đảm tính nguyên tử và nhất quán của thao tác ghi; DataLoader gom các lần đọc và cache kết quả trong phạm vi GraphQL request.

Với transaction per mutation method, Spring hoàn tất commit khi mutation method trả về. GraphQL sau đó tiếp tục resolve nested fields và dispatch DataLoader batch. Điều này giúp batch loader đọc trạng thái đã commit mà không phải giữ transaction ghi mở xuyên suốt quá trình resolve toàn bộ object graph.

Tuy nhiên, DataLoader cache vẫn tồn tại trong cùng request. Khi nhiều mutation root fields thay đổi cùng key, cần clear cache sau commit để nested field tiếp theo tải dữ liệu mới. Chỉ prime cache bằng giá trị đầy đủ và đã commit. Với side effect cần chạy sau commit, dùng @TransactionalEventListener; với message cần bảo đảm không mất, cân nhắc Transactional Outbox.

## Tài liệu tham khảo

- [Spring for GraphQL — Data Integration and Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [GraphQL Java — java-dataloader](https://github.com/graphql-java/java-dataloader)
