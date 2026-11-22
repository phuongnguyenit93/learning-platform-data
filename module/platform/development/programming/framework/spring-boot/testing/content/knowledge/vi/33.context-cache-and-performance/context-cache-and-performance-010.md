# Chọn phạm vi tối ưu mà vẫn giữ tính độc lập và khả năng phát hiện lỗi

Một bộ test Spring Boot có thể chạy chậm vì mỗi class khởi động một `ApplicationContext` mới, nhưng việc ép mọi bài test thành unit test với Mockito lại có thể bỏ lọt lỗi về dependency injection, transaction, serialization, SecurityFilterChain hoặc mapping JPA. Một nhóm khác tối ưu bằng cách chia sẻ cả `ApplicationContext` lẫn dữ liệu mutable của singleton/DB giữa các tests: suite chạy nhanh khi chạy toàn bộ theo một thứ tự, nhưng thất bại ngẫu nhiên nếu chạy riêng, song song hoặc đổi thứ tự. Cả hai giải pháp đều chưa đạt mục tiêu chất lượng.

Bài Knowledge **“Chọn phạm vi tối ưu mà vẫn giữ tính độc lập và khả năng phát hiện lỗi”** thuộc phần **Context cache và hiệu năng** của module **Spring Boot – testing**. Nguyên tắc xuyên suốt là:

> Chọn **phạm vi test nhỏ nhất vẫn có thể thất bại khi lỗi quan trọng mà ta cần phát hiện xuất hiện**, rồi chia sẻ **cấu hình Spring context ổn định**, không chia sẻ **trạng thái nghiệp vụ có thể thay đổi** giữa các test.

Bài sẽ giải thích sự khác nhau giữa **độ rộng test** (unit → slice → full context → real HTTP), **tái sử dụng TestContext cache** và **cô lập dữ liệu/side effects**. Sau đó là một project thực hành **Java 17+, Spring Boot 3.5.16, Spring Framework 6.2, JUnit Jupiter 5, Mockito, MockMvc, Spring Data JPA, H2** minh họa cùng một nghiệp vụ giữ chỗ số lượng sách qua năm tầng test. Phần thực hành cũng chỉ rõ một trường hợp full-context test với `@Transactional` vẫn có thể che lỗi thiếu transaction ở service, và cách test qua real HTTP khép kín khoảng trống đó.

**Phạm vi cam kết:** Mã mẫu đã được rà soát theo API của Spring Boot 3.5/Spring Framework 6.2. Các số thời gian, cache hits, Gradle results hay failure rates nếu xuất hiện trong ví dụ đều được ghi rõ là **minh họa/kỳ vọng**, không phải số liệu đã đo trong repository của người học.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt tốc độ **một test method** với thời gian **toàn suite**, và phân biệt tái sử dụng context với độc lập dữ liệu.
- Chọn giữa JUnit/Mockito thuần, `ApplicationContextRunner`, `@JsonTest`, `@WebMvcTest`, `@RestClientTest`, `@DataJpaTest`, `@SpringBootTest(MOCK)` và `@SpringBootTest(RANDOM_PORT)`.
- Đặt một **bug hypothesis** trước khi chọn test scope, tránh “cái nào nhanh nhất” trở thành tiêu chuẩn duy nhất.
- Hiểu TestContext cache dùng **context configuration key**, **mặc định tối đa 32 contexts**, eviction theo LRU và cache dùng static state trong một JVM process.
- Nhận ra `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, `@MockitoBean` và test configuration có thể phân mảnh cache.
- Biết lúc nào `@DirtiesContext` là đúng và lúc nào nó đang che một bài toán cleanup dễ hơn.
- Viết tests không phụ thuộc thứ tự, tránh dữ liệu/clock/cache/Mockito state rò rỉ.
- Hiểu rollback mặc định trong `@DataJpaTest`, và tại sao `RANDOM_PORT` không được rollback bởi transaction của test thread.
- Biết những gì `@WebMvcTest` **không** nạp, những gì `@DataJpaTest` **không** kiểm và vì sao cần một số full integration cases.
- Kiểm business service bằng mock repository, repository bằng embedded database, controller bằng mock service và end-to-end wiring bằng DB thật trong context.
- Đo số lần load context, cache hit/miss và thời gian test với bằng chứng, thay vì đoán.
- Xác định điểm cân bằng giữa phát hiện lỗi, thời gian feedback, độ tái lập và chi phí CI.
- Trình bày báo cáo nêu rõ mỗi test **phát hiện** và **không phát hiện** loại lỗi nào.

## 2. Ba trục phải tối ưu đồng thời

| Trục | Câu hỏi | Nếu tối ưu sai |
|---|---|---|
| **Phạm vi / fidelity** | Những layers, proxies, filters, serializers, repositories nào là thật? | Mock quá sâu khiến wiring/transaction/security bug không bị phát hiện |
| **Độc lập / isolation** | Mỗi test có thể chạy riêng, đảo thứ tự, song song mà vẫn đúng không? | Suite flaky, dữ liệu còn sót, static/singleton leak |
| **Hiệu năng / feedback** | Tổng thời gian startup contexts, Docker/DB, test execution bao nhiêu? | Chờ CI lâu, feedback chậm, developer bỏ chạy suite |

Không tồn tại một annotation “tối ưu nhất” cho mọi test. Một `@WebMvcTest` nhanh nhưng bỏ quên transaction service **không phải giải pháp** nếu mục tiêu là bảo vệ transaction. Một `@SpringBootTest` đầy đủ nhưng mỗi class có một `@MockBean`/property khác nhau cũng **không tận dụng cache tốt**.

### 2.1. Công thức tư duy về thời gian suite

```text
T_total (xấp xỉ)
  = tổng startup cost của các context keys thực sự phải load
  + tổng thời gian thực thi test methods
  + tổng startup/wait của DB, containers và external dependencies
  + chi phí fork JVM, build/test discovery, instrumentation
  + chi phí contention/retry do chạy song song.

Context cache giảm phần startup khi cùng cache key được reuse;
nó không tự làm database sạch hoặc mocks reset đúng như kỳ vọng.
```

Số test methods tăng không có nghĩa số contexts tăng tương ứng. Một trăm methods dùng **cùng một key** có thể reuse một context; mười test classes với mười tập bean overrides khác nhau có thể tạo mười contexts. Tuy nhiên không dùng con số 1 hay 10 này làm cam kết vì môi trường, cache eviction và fork JVM ảnh hưởng.

## 3. “Nhỏ nhất” phải được định nghĩa theo loại lỗi

Thử đưa ra câu hỏi trước khi chọn annotation:

1. Nếu sửa sai **một phép tính**, test có fail không?
2. Nếu xóa `@Transactional` khỏi service, test có fail không?
3. Nếu controller sai path, query parameter, JSON field hoặc HTTP error mapping, test có fail không?
4. Nếu tên cột JPA đổi hoặc query sai, test có fail không?
5. Nếu application thiếu bean, sai profile/property hoặc hai beans cùng type, test có fail không?
6. Nếu SecurityFilterChain sai role, test có chạy real filters không?
7. Nếu request chạy qua TCP và giao dịch nằm ở **server thread**, test có quan sát commit không?
8. Nếu database thật xử lý SQL khác H2, test với H2 có phát hiện không?
9. Nếu background worker/queue ghi ngoài transaction, rollback test thread có dọn side effect không?

Một test ở phạm vi hẹp chỉ tốt nếu **failure mode cần bảo vệ nằm trong phạm vi đó**. Khi bug hypothesis nằm ngoài, hãy nâng cấp đúng một bậc hoặc thêm một test chuyên biệt; không cần nâng toàn bộ suite lên full context.

## 4. Phân loại phạm vi và bug detection

| Loại test | Độ rộng | Chứng minh tốt | Không tự chứng minh |
|---|---|---|---|
| **Pure JUnit / Mockito** | Java object + mocks | Rule, branch, số lần gọi, không side effect giả | Spring proxies, transactions, MVC, DB |
| `ApplicationContextRunner` | Config nhỏ theo từng case | Auto-config class/bean/property conditions | Full app scanning và HTTP |
| `@JsonTest` | JSON serializers/mappers | Format, custom Jackson configuration trong slice | Controller, database, security |
| `@WebMvcTest` | MVC controllers/filter subset | Route, validation, JSON, advice, selected security | Service transaction/real repository |
| `@RestClientTest` | HTTP client bean + mock request factory | Outbound request/headers/status mapping | TCP timeout, real network pool |
| `@DataJpaTest` | JPA entity/repository/embedded DB | Mapping, query, constraints, dirty checking | MVC/Service AOP của app (trừ khi import) |
| `@SpringBootTest + @AutoConfigureMockMvc` | Gần full app, mock servlet transport | Controller→Service→JPA wiring, filter chain, transaction | TCP/server threads/real proxy network |
| `@SpringBootTest(RANDOM_PORT)` | Full app + real embedded HTTP | TCP, committed effects, cookies/filters | Production cluster/cloud nếu vẫn dùng H2/mocks |
| Testcontainers + real DB | App/repo + dependency thực | SQL dialect, migrations, isolation | Toàn bộ production infra |
| Production-like E2E | Multi-service realistic topology | Hành trình thực và hệ thống dependencies | Mọi edge case nhỏ (chi phí cao) |

**Một loại test không tự động “tốt hơn” loại khác.** Cần mix tối ưu: số lượng lớn small tests, đủ slice tests để bắt lỗi Spring integration của từng layer và một tập nhỏ full-flow tests để kiểm giả định giữa các layers.

## 5. Ví dụ về hai lỗi lọt qua slice

**Lỗi A — service thiếu transaction:** `@WebMvcTest` mock `ReservationService` trả JSON 200; không có JPA dirty checking nào được chạy, nên không thể biết `@Transactional` bị xóa.

**Lỗi B — repository query sai:** unit test Mockito luôn trả `Optional.of(book)`, dù repository method `findByTitleIgnoreCase` thực sự sai tên property hoặc không case-insensitive. Chỉ JPA repository test/real DB test mới bắt được.

Ngược lại, để test `quantity=-1` bị service chặn **trước khi gọi repository**, không cần khởi động H2/MVC. Dùng pure JUnit/Mockito chính là phạm vi đúng.

## 6. Ví dụ ngược: full context vẫn có thể cho tín hiệu yếu

Một test:

```java
@SpringBootTest
class WeakTest {
    @Test
    void contextStarts() {
        // Không assert business behavior.
    }
}
```

có thể khởi động cả app nhưng chỉ nói “context hiện tại load được”. Nó **không** bảo vệ 401/403, JSON contract, repository query hoặc rollback. Một test tốt cần có assertion tương ứng bug hypothesis, không chỉ annotation “to”.

Một full context test mà `@MockitoBean` thay chính service chứa `@Transactional` cũng **không kiểm transaction của service đó**. Tương tự, mock payment adapter làm test nhanh nhưng không chứng minh real HTTP client/TLS/retry. Cần ghi rõ nơi mock nằm.

## 7. Context cache: khác biệt lớn giữa test scope và test speed

Spring TestContext Framework cache `ApplicationContext` theo một **context configuration key**. Khi một test khác yêu cầu cùng key trong **cùng JVM test process** và context chưa bị loại bỏ, Spring có thể trả lại cùng object ApplicationContext thay vì load mới. Điều này tiết kiệm phần nặng nhất trong Spring integration tests: bean initialization, Hibernate metamodel, embedded server, filters, auto-config và clients.

**Cache mặc định tối đa 32 contexts**, với chính sách least-recently-used (LRU). Số 32 là **default max**, không phải con số bảo đảm context luôn có 32 entries. Có thể cấu hình:

```text
-Dspring.test.context.cache.maxSize=64
```

Tham số trên là **JVM system property của test JVM** hoặc SpringProperties, không phải một magic annotation để làm suite nhanh ngay. Nếu tăng maxSize nhưng mỗi context tốn rất nhiều memory, CI có thể tăng GC/OutOfMemory. Đầu tiên đo fragmentation và giảm những biến thể không cần thiết, rồi mới cân nhắc chỉnh size.

### 7.1. Điều gì nằm trong cache key?

Theo Spring Framework 6.2 TestContext docs, cache key phụ thuộc nhiều metadata, gồm:

- `locations`, `classes` từ `@ContextConfiguration`.
- `contextInitializerClasses`, `contextLoader`.
- `contextCustomizers` (bao gồm bean overrides như `@MockitoBean`, `@MockitoSpyBean`, `@TestBean`, các `@DynamicPropertySource` methods và customizations từ Spring Boot).
- `contextParent` cho context hierarchy.
- `activeProfiles` từ `@ActiveProfiles`.
- `propertySourceDescriptors`/`propertySourceProperties` từ test properties.
- `resourceBasePath` khi là web context.

**Quan trọng:** Hai classes có code giống nhau nhưng một class khai báo thêm `@MockitoBean` hoặc property khác có thể có **khóa khác**. Hai tests cùng class tự nhiên thường dùng cùng key trừ khi có yếu tố cấu hình động/lifecycle làm đổi behavior.

## 8. Vì sao tên field `@MockitoBean` có thể làm cache phân mảnh?

Trong Spring Framework 6.2, bean override dùng qualifiers để xác định mục tiêu. Nếu thiếu `@Qualifier`, **field name** có thể được dùng làm fallback qualifier. Vì vậy:

```java
// Test A:
@MockitoBean
PaymentGateway paymentGateway;

// Test B (cùng type, tên khác):
@MockitoBean
PaymentGateway gateway;
```

Đây là snippets giả định type `PaymentGateway`, không phải file demo. Nếu field names đóng vai trò qualifier, chúng có thể khiến framework phải tạo những ApplicationContexts riêng; docs chính thức khuyên đặt tên nhất quán khi cùng mock một bean qua nhiều test classes.

**Không sửa tên field một cách mù quáng** nếu một app có nhiều candidates; khi đó cần qualifier đúng để mock đúng bean. Và **không mock thêm beans vô ích chỉ để “chuẩn hóa” annotation**, vì điều đó làm test che nhiều logic thật hơn. Chuẩn hóa các mocks **thực sự cần** giữa những test classes có chung test scope.

### 8.1. `@MockitoBean` có thể tạo bean mới

Mặc định `@MockitoBean` dùng strategy **REPLACE_OR_CREATE**: nếu bean mục tiêu không tồn tại, framework có thể tạo mock mới. Ở `@WebMvcTest`, đây là điều bình thường vì service không thuộc slice. Nhưng nếu một **full integration test** cần bảo đảm bean production thực sự tồn tại, có thể dùng `@MockitoBean(enforceOverride=true)` khi phù hợp để fail nếu bean cần override không có; hoặc tốt hơn **đừng mock bean đang muốn kiểm wiring**.

Đặc biệt, mock thay thế một proxied bean bằng object giả nên không còn các AOP advisors thông thường của bean gốc (transaction/cache/method security). Một test đã mock service **không chứng minh proxy transactional/security thật**.

## 9. Những thay đổi nhỏ phá cache reuse

| Khác biệt giữa test classes | Cache impact có thể có | Có nên chuẩn hóa? |
|---|---|---|
| `@ActiveProfiles("test")` vs `("local")` | Key khác | Có nếu không cần semantics khác |
| `@TestPropertySource(properties="feature=true")` vs false | Key khác | Chỉ thống nhất nếu thật sự cùng scenario |
| `@MockitoBean A` vs `@MockitoBean A,B` | Key khác | Không thêm B nếu B là object cần test |
| Mock field qualifier/name khác | Có thể tạo key khác | Đặt nhất quán nếu cùng target |
| `@DynamicPropertySource` method khác | Có thể tạo key khác | Gom config ổn định khi hợp lý |
| `@Import(TestConfig.class)` khác | Key khác | Shared minimal fixture nếu thích hợp |
| `@SpringBootTest(MOCK)` vs RANDOM_PORT | Key khác | Không đồng nhất vì khác transport |
| `@WebMvcTest` vs full context | Key khác, bản chất khác | Không cố gộp |
| `@DirtiesContext` | Evict + close context | Dùng hiếm, khi thật sự cần |
| Fork JVM riêng | Cache không chia sẻ | Build strategy quyết định |

**Không hy sinh khả năng phát hiện lỗi để tăng cache hits.** Ví dụ, bỏ `feature=false` test chỉ vì key khác sẽ mất negative branch. Số contexts ít **không phải** KPI chất lượng nếu coverage suy giảm.

## 10. Cache không có nghĩa context state là sạch

ApplicationContext thường chứa **singleton beans** và caches/pools trong JVM. Khi context được reuse:

- `AtomicInteger` trong singleton có thể giữ số lần gọi từ test trước.
- `ConcurrentHashMap` caching bean giữ dữ liệu do test khác nạp.
- `Clock` mutable/test clock bị advance và không reset.
- `SecurityContextHolder` custom ThreadLocal có thể còn nếu code cleanup sai.
- `@Scheduled` jobs có thể tiếp tục chạy trên background threads.
- HTTP client pools, retry/circuit breaker state có thể vẫn mở.
- Database in-memory cùng context có thể giữ rows do test đã commit.
- Testcontainers container có thể giữ tables/queues/object data.
- Static fields nằm **ngoài** Spring context và không được reset bởi `@DirtiesContext` mặc định.

Vì thế quy tắc:

**Tái sử dụng object graph khởi tạo đắt tiền; reset/rollback mọi state có thể ảnh hưởng kết quả test.** Nếu không biết một bean có state hay không, hãy điều tra thay vì tự động thêm `@DirtiesContext` để tránh hiểu code.

## 11. `@DirtiesContext`: khi nào nên dùng?

`@DirtiesContext` thông báo context đã bị thay đổi theo cách không thể an toàn reuse. Spring sẽ xóa context khỏi cache và đóng context đó. Những trường hợp hợp lý:

- Test thay đổi **bean definitions**, programmatically register/remove beans.
- Test thay cấu hình hạ tầng không thể hoàn nguyên bằng API được hỗ trợ.
- Test phá trạng thái global trong context mà reset an toàn không thực tế.
- Test đưa container/service có lifecycle khiến context không thể reuse.

Ví dụ **minh họa**, không thuộc runnable project:

```java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MutatesUnresettableBeanGraphTest {
    // Test thay đổi cấu hình context thực sự.
}
```

**Không** dùng `@DirtiesContext` mặc định cho mọi `@SpringBootTest` chỉ vì một repository có dữ liệu còn lại. Khi có thể rollback DB, xóa data có scope, clear in-memory cache hoặc reset clock/mock, hãy làm điều đó để giữ cache reuse. Nếu dùng `@ContextHierarchy`, cần hiểu `hierarchyMode` vì eviction có thể ảnh hưởng nhiều child contexts.

## 12. Test độc lập không có nghĩa mọi test phải load context mới

Một test độc lập thỏa các thuộc tính:

1. **Chạy riêng** từ IDE vẫn pass.
2. **Đảo thứ tự** với test khác vẫn pass.
3. **Repeat** N lần trên cùng environment không tích lũy dữ liệu ảnh hưởng.
4. **Song song** không tranh chấp global fixture nếu suite cho phép parallel.
5. Dữ liệu tạo ra, gửi đi, cache entry, file hay queue message đều có cleanup rõ.
6. Mock interactions không bị giữ từ test trước.
7. Không dựa vào context mới để state tự reset nếu context cache đang được bật.

Nó **không** bắt buộc tạo một ApplicationContext mới cho mỗi method. `@DataJpaTest` thường dùng transaction rollback để độc lập dữ liệu dù nhiều methods reuse cùng JPA context. `@WebMvcTest` có thể reuse controller slice với `@MockitoBean` nhưng Mockito framework reset mocks giữa methods theo lifecycle của test framework.

## 13. DB isolation: transaction rollback có giới hạn

Trong Spring/JUnit:

- `@DataJpaTest` mặc định transactional và **rollback** ở cuối mỗi test method.
- `@SpringBootTest` không tự làm mọi test transactional; thêm `@Transactional` vào test nếu mục tiêu là rollback dữ liệu trong cùng test-managed transaction.
- `@SpringBootTest + @AutoConfigureMockMvc` gọi controller trực tiếp qua mock servlet, thường trong cùng test thread, nên service `@Transactional(REQUIRED)` có thể tham gia test transaction.
- `@SpringBootTest(RANDOM_PORT)` khởi động server thật: test HTTP client và server ở **threads/transactions khác nhau**, rollback của test thread **không rollback server commits**.
- `@Async`/scheduled jobs/new threads và calls tới external broker/file system không nằm trong rollback của transaction test.
- `@Transactional(propagation=REQUIRES_NEW)` hoặc code tự tạo transaction riêng có thể commit độc lập tùy luồng xử lý.

**Đặc biệt quan trọng:** Nếu chỉ chạy full-context MockMvc test với class-level `@Transactional`, nó có thể **che lỗi service bị xóa `@Transactional`**, vì test transaction vẫn bao bọc JPA updates. Vì vậy bài demo thêm real HTTP integration test **không đặt `@Transactional` ở test class**, có assert DB state sau request. Một test từ client tới server khác thread giúp kiểm transaction boundary gần production hơn.

## 14. Isolation với Redis, Kafka, filesystem và Clock

Rollback của JPA **không hoàn nguyên**:

- Kafka messages đã publish.
- Redis keys/cache TTL.
- Multipart temp files/object storage.
- HTTP requests gửi ra ngoài.
- Scheduled jobs đang chạy trên thread khác.
- System property và static singleton mutate.
- In-memory queues/caches không được reset.

Giải pháp đúng boundary: test topic/consumer group riêng, Redis key prefix theo UUID, `@TempDir`, fake SMTP, per-test object prefix, disable/điều khiển scheduler và Clock, cleanup explicit trong `@AfterEach`. Nếu một test tạo event mà consumer xử lý sau khi test kết thúc, cần await bounded completion rồi cleanup hoặc tách environment. Đừng coi `@DirtiesContext` là một giao dịch tổng bao mọi dependencies.

### 14.1. Mutable Clock và static fixtures

Một `Clock.fixed` bean được tái sử dụng ổn vì immutable. Một `MutableClock` trong singleton có thể bị test A advance tới ngày mai, làm test B tưởng token hết hạn. Cách an toàn: tạo domain object với Clock riêng trong pure unit tests; nếu inject mutable Clock vào Spring context, reset nó trong lifecycle của mỗi test và kiểm không có scheduled/background consumer chạy cùng lúc.

## 15. Hướng tối ưu từ bug hypothesis đến annotation

```text
Lỗi mục tiêu nằm ở đâu?
  |
  +-- Pure domain rule?
  |      -> JUnit thuần, mock chỉ port thật cần tách
  |
  +-- Auto-configuration / bean conditional?
  |      -> ApplicationContextRunner
  |
  +-- JSON module / date formatting?
  |      -> @JsonTest
  |
  +-- Controller path / JSON / advice / security filter?
  |      -> @WebMvcTest + MockMvc + đúng SecurityFilterChain
  |
  +-- Repository query / JPA mapping?
  |      -> @DataJpaTest + DB phù hợp (H2 hoặc Testcontainers)
  |
  +-- Outbound HTTP client status/header?
  |      -> @RestClientTest + MockRestServiceServer
  |
  +-- Cross-layer wiring / @Transactional / AOP / DB state?
  |      -> @SpringBootTest + MockMvc, cân nhắc test transaction
  |
  +-- Actual inbound HTTP / server-side commits?
  |      -> @SpringBootTest(RANDOM_PORT)
  |
  +-- Actual DB dialect / distributed IO / infra?
         -> Testcontainers/external integration test
```

**Đường nâng cấp tối thiểu:** Nếu bug chỉ liên quan mapping JSON, đừng lập tức thêm Postgres container. Nếu bug xảy ra do transaction boundary, đừng dùng Mockito mock transaction service. Chọn scope theo *điểm lỗi có thể tồn tại*, không theo tên feature chung chung.

## 16. Project runnable: nghiệp vụ giữ số lượng sách

Ứng dụng minh họa lưu bảng `books` với:

- `id`: định danh sách.
- `title`: tên sách để kiểm repository case-insensitive query.
- `priceCents`: giá nguyên theo cent, không cần floating point.
- `stock`: số bản còn có thể giữ.
- `version`: JPA optimistic locking field (không thay thế toàn bộ concurrency test).

HTTP API:

- `GET /api/books/{id}` → `BookView` và stock hiện tại.
- `POST /api/books/{id}/reserve` nhận `{"quantity":2}`.
- Quantity ngoài khoảng 1–10 → HTTP 400.
- ID không tồn tại → HTTP 404.
- Stock không đủ → HTTP 409, **không giảm stock**.
- Hợp lệ → HTTP 200 và `ReservationReceipt` có stock mới.

**Một nghiệp vụ, năm tầng test:**

1. `ReservationServiceTest` — pure JUnit + mock repository.
2. `BookRepositoryTest` — `@DataJpaTest` với embedded H2.
3. `ReservationControllerMvcTest` — `@WebMvcTest` với mocked service.
4. `ReservationFlowMockMvcTest` — full context + MockMvc + H2 + test transaction rollback.
5. `ReservationRealHttpTest` — full context + real HTTP, **không test transaction**, kiểm server commit.

Demo dùng H2 để học ranh giới; không bảo đảm semantics giống Postgres/MySQL khi nâng lên production. Các vấn đề cạnh tranh cập nhật, unique constraints, distributed locks, migration và security cần tests riêng ở đúng hạ tầng.

## 17. Cây thư mục project

```text
test-scope-context-cache/
  settings.gradle
  build.gradle
  src/main/java/com/example/testscope/
    TestScopeApplication.java
    Book.java
    BookRepository.java
    ReserveRequest.java
    BookView.java
    ReservationReceipt.java
    InvalidQuantityException.java
    BookNotFoundException.java
    InsufficientStockException.java
    ReservationService.java
    ReservationController.java
    ReservationAdvice.java
  src/test/resources/
    application.properties
  src/test/java/com/example/testscope/
    ReservationServiceTest.java
    BookRepositoryTest.java
    ReservationControllerMvcTest.java
    ReservationFlowMockMvcTest.java
    ReservationRealHttpTest.java
```

Dự án chỉ cần Java 17+, Gradle 8.x tương thích Spring Boot 3.5.16 và Maven Central cho dependencies. Không cần Docker; datasource H2 embedded chạy trong test JVM. `application.properties` trong `src/test/resources` chỉ áp dụng khi chạy tests, không phải cấu hình production DB.

## 18. Gradle cấu hình tối thiểu

**`settings.gradle`**

```groovy
rootProject.name = 'test-scope-context-cache'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/test/resources/application.properties`**

```properties
spring.jpa.hibernate.ddl-auto=create-drop
spring.datasource.generate-unique-name=true
spring.jpa.open-in-view=false
```

`spring.datasource.generate-unique-name=true` giảm khả năng hai Spring contexts dùng trùng một tên H2 in-memory database ngoài ý muốn. `create-drop` dành cho demo/test, **không dùng cho production với dữ liệu thật**. H2 là runtime dependency của demo để `bootRun` cũng có datasource nếu người học muốn khởi động app; khi phát hành ứng dụng, cấu hình database phù hợp môi trường.

Nếu project chưa có Gradle wrapper, tạo wrapper trước; hai files Gradle ở trên **không tự sinh `gradlew`**. Test runner qua `useJUnitPlatform()` để nhận diện Jupiter tests.

## 19. Spring Boot application

**`src/main/java/com/example/testscope/TestScopeApplication.java`**

```java
package com.example.testscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestScopeApplication {

    public static void main(String[] args) {
        SpringApplication.run(TestScopeApplication.class, args);
    }
}
```

Một `@SpringBootApplication` duy nhất giúp các test slices/full context có application root rõ ràng. `@WebMvcTest` không nạp mọi service/repository dù tìm được `@SpringBootApplication`; nó áp type-exclude filters và auto-config phù hợp MVC. `@DataJpaTest` tương tự chỉ nạp JPA-related components.

## 20. JPA entity và optimistic locking

**`src/main/java/com/example/testscope/Book.java`**

```java
package com.example.testscope;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @Column(length = 100)
    private String id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private long priceCents;

    @Column(nullable = false)
    private int stock;

    @Version
    private Long version;

    protected Book() {
        // JPA constructor
    }

    public Book(
            String id, String title,
            long priceCents, int stock) {

        if (id == null || id.isBlank()
                || title == null || title.isBlank()
                || priceCents < 0 || stock < 0) {
            throw new IllegalArgumentException(
                    "Invalid book fields");
        }

        this.id = id;
        this.title = title;
        this.priceCents = priceCents;
        this.stock = stock;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public long getPriceCents() {
        return priceCents;
    }

    public int getStock() {
        return stock;
    }

    public void reserve(int quantity) {
        if (quantity < 1 || quantity > 10) {
            throw new InvalidQuantityException();
        }
        if (stock < quantity) {
            throw new InsufficientStockException();
        }
        stock -= quantity;
    }
}
```

`@Version` giúp JPA phát hiện nhiều stale writes trên cùng entity version khi flush/commit, nhưng **không tự bảo đảm mọi concurrent reservation thành công**. Nếu production cần an toàn với nhiều concurrent users, test hai transactions thực và quy định cách map/retry optimistic-lock exception. Demo không bao gồm concurrency stress test.

## 21. Repository và DTOs

**`src/main/java/com/example/testscope/BookRepository.java`**

```java
package com.example.testscope;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository
        extends JpaRepository<Book, String> {

    Optional<Book> findByTitleIgnoreCase(String title);
}
```

**`src/main/java/com/example/testscope/ReserveRequest.java`**

```java
package com.example.testscope;

public record ReserveRequest(int quantity) {
}
```

**`src/main/java/com/example/testscope/BookView.java`**

```java
package com.example.testscope;

public record BookView(
        String id,
        String title,
        long priceCents,
        int available) {
}
```

**`src/main/java/com/example/testscope/ReservationReceipt.java`**

```java
package com.example.testscope;

public record ReservationReceipt(
        String bookId,
        int reserved,
        int remaining) {
}
```

Định nghĩa Java records giúp JSON fields nhất quán. `@WebMvcTest` sẽ kiểm JSON names; `@DataJpaTest` kiểm repository query. Một unit test mocking BookRepository không thể biết `findByTitleIgnoreCase` có chạy đúng với H2 hoặc production database.

## 22. Domain exceptions và service

**`src/main/java/com/example/testscope/InvalidQuantityException.java`**

```java
package com.example.testscope;

public class InvalidQuantityException
        extends RuntimeException {
}
```

**`src/main/java/com/example/testscope/BookNotFoundException.java`**

```java
package com.example.testscope;

public class BookNotFoundException
        extends RuntimeException {
}
```

**`src/main/java/com/example/testscope/InsufficientStockException.java`**

```java
package com.example.testscope;

public class InsufficientStockException
        extends RuntimeException {
}
```

**`src/main/java/com/example/testscope/ReservationService.java`**

```java
package com.example.testscope;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationService {

    private final BookRepository repository;

    public ReservationService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public BookView read(String id) {
        Book book = repository.findById(id)
                .orElseThrow(BookNotFoundException::new);
        return new BookView(
                book.getId(),
                book.getTitle(),
                book.getPriceCents(),
                book.getStock());
    }

    @Transactional
    public ReservationReceipt reserve(
            String id, int quantity) {

        if (quantity < 1 || quantity > 10) {
            throw new InvalidQuantityException();
        }

        Book book = repository.findById(id)
                .orElseThrow(BookNotFoundException::new);

        book.reserve(quantity);

        // No explicit save() needed for a managed entity
        // under JPA dirty checking in the active transaction.
        return new ReservationReceipt(
                book.getId(), quantity, book.getStock());
    }
}
```

**Hành vi cần bảo vệ:**

- Quantity invalid → ném lỗi trước khi chạm repository.
- Unknown ID → BookNotFoundException.
- Stock thiếu → không thay `stock`.
- Hợp lệ → Entity `book` managed trong service transaction, gọi `reserve` rồi JPA dirty checking flush/commit.
- `readOnly=true` chỉ cho đường đọc, không dùng làm bảo vệ quyền truy cập.

**Điểm khiến test scope quan trọng:** Nếu xóa `@Transactional` khỏi `reserve`, một unit test tạo service với mock repository vẫn thấy `book.stock` giảm, và một full-context MockMvc test được bọc bằng **test `@Transactional`** vẫn có thể có active transaction từ bên ngoài. Nhưng real HTTP test không bọc server thread bằng test transaction; khi service thiếu transaction, managed entity lifecycle có thể khác và DB update không commit. Một test qua socket với assert DB sau request phát hiện được loại lỗi này theo behavior của demo.

## 23. HTTP controller và error advice

**`src/main/java/com/example/testscope/ReservationController.java`**

```java
package com.example.testscope;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class ReservationController {

    private final ReservationService service;

    public ReservationController(ReservationService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public BookView read(@PathVariable String id) {
        return service.read(id);
    }

    @PostMapping(
            path = "/{id}/reserve",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ReservationReceipt reserve(
            @PathVariable String id,
            @RequestBody ReserveRequest request) {

        return service.reserve(id, request.quantity());
    }
}
```

**`src/main/java/com/example/testscope/ReservationAdvice.java`**

```java
package com.example.testscope;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ReservationAdvice {

    public record ErrorBody(String code) {
    }

    @ExceptionHandler(InvalidQuantityException.class)
    public ResponseEntity<ErrorBody> invalidQuantity() {
        return ResponseEntity.badRequest()
                .body(new ErrorBody("INVALID_QUANTITY"));
    }

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ErrorBody> missingBook() {
        return ResponseEntity.status(404)
                .body(new ErrorBody("BOOK_NOT_FOUND"));
    }

    @ExceptionHandler(InsufficientStockException.class)
    public ResponseEntity<ErrorBody> insufficientStock() {
        return ResponseEntity.status(409)
                .body(new ErrorBody("INSUFFICIENT_STOCK"));
    }
}
```

Mã HTTP này không có authentication/Spring Security để giữ demo tập trung vào context cache. Với ứng dụng cần authorization, `@WebMvcTest` có filter chain thật được import/scan phù hợp và full-context security test là bắt buộc. Không lấy việc endpoint demo trả 200 làm chứng cứ security policy của một app thực.

## 24. Unit test: nhanh, độc lập, không khởi động Spring

**`src/test/java/com/example/testscope/ReservationServiceTest.java`**

```java
package com.example.testscope;

import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ReservationServiceTest {

    @Mock
    BookRepository repository;

    ReservationService service;

    @BeforeEach
    void setup() {
        service = new ReservationService(repository);
    }

    @Test
    void reserveDecrementsEntityInMemory() {
        Book book = new Book("b1", "Domain", 1500, 5);
        when(repository.findById("b1"))
                .thenReturn(Optional.of(book));

        ReservationReceipt result = service.reserve("b1", 2);

        assertEquals(2, result.reserved());
        assertEquals(3, result.remaining());
        assertEquals(3, book.getStock());
        verify(repository).findById("b1");
    }

    @Test
    void badQuantityFailsBeforeRepositoryCall() {
        assertThrows(InvalidQuantityException.class,
                () -> service.reserve("b1", 0));

        verifyNoInteractions(repository);
    }

    @Test
    void missingBookThrowsDomainError() {
        when(repository.findById("missing"))
                .thenReturn(Optional.empty());

        assertThrows(BookNotFoundException.class,
                () -> service.reserve("missing", 1));
    }

    @Test
    void insufficientStockDoesNotMutateEntity() {
        Book book = new Book("b2", "Domain", 1500, 2);
        when(repository.findById("b2"))
                .thenReturn(Optional.of(book));

        assertThrows(InsufficientStockException.class,
                () -> service.reserve("b2", 3));

        assertEquals(2, book.getStock());
    }

    @Test
    void readMapsDomainObjectWithoutMutation() {
        Book book = new Book("b3", "Testing", 2400, 6);
        when(repository.findById("b3"))
                .thenReturn(Optional.of(book));

        BookView view = service.read("b3");

        assertEquals("Testing", view.title());
        assertEquals(2400, view.priceCents());
        assertEquals(6, view.available());
    }
}
```

Có **5 test methods**. Chúng đủ để phát hiện sai nhánh quantity, mapping DTO hoặc logic giảm stock mà không cần Spring, H2, HTTP. Tuy nhiên, `@Transactional` và JPA dirty checking **không hoạt động** trên `new ReservationService(repository)` — chỉ annotation metadata có mặt, chứ Spring AOP proxy không được tạo. Không được báo test này là bằng chứng DB commit.

## 25. Repository slice: `@DataJpaTest` và rollback

**`src/test/java/com/example/testscope/BookRepositoryTest.java`**

```java
package com.example.testscope;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class BookRepositoryTest {

    @Autowired
    BookRepository repository;

    @Autowired
    EntityManager entityManager;

    @Test
    void derivedIgnoreCaseQueryMatchesTitle() {
        repository.saveAndFlush(
                new Book("jpa-b1", "Spring Boot", 3200, 8));

        assertTrue(repository.findByTitleIgnoreCase(
                "sPrInG bOoT").isPresent());
    }

    @Test
    void managedEntityDirtyCheckingPersistsAfterFlush() {
        Book book = repository.saveAndFlush(
                new Book("jpa-b2", "JPA", 2000, 5));

        book.reserve(2);
        entityManager.flush();
        entityManager.clear();

        Book reloaded = repository.findById("jpa-b2")
                .orElseThrow();

        assertEquals(3, reloaded.getStock());
    }
}
```

Có **2 methods**. `@DataJpaTest` mặc định transactional; mỗi method được rollback, nên chạy cùng context không để lại hai IDs `jpa-b1/jpa-b2` cho test tiếp theo. Test thứ hai `flush/clear` để tránh assertion chỉ nhìn managed entity trong first-level cache mà chưa chứng minh SQL update chạy.

**Giới hạn H2:** Nó giúp kiểm Spring Data derived query và JPA mapping trên H2. Nếu ứng dụng production dùng PostgreSQL-specific SQL/locks/constraints, cần `@DataJpaTest` hoặc full-context integration với **PostgreSQL Testcontainers**, cùng migrations thực và dữ liệu scoped. Không biến “H2 pass” thành “mọi DB pass”.

## 26. Controller slice: `@WebMvcTest` chỉ giữ MVC boundary

**`src/test/java/com/example/testscope/ReservationControllerMvcTest.java`**

```java
package com.example.testscope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReservationController.class)
@Import(ReservationAdvice.class)
class ReservationControllerMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ReservationService reservationService;

    @Test
    void successfulReservationHasCorrectHttpJson()
            throws Exception {

        when(reservationService.reserve("b1", 2))
                .thenReturn(new ReservationReceipt("b1", 2, 3));

        mvc.perform(post("/api/books/b1/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":2}"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.bookId").value("b1"),
                        jsonPath("$.reserved").value(2),
                        jsonPath("$.remaining").value(3));

        verify(reservationService).reserve("b1", 2);
    }

    @Test
    void invalidQuantityMapsTo400() throws Exception {
        when(reservationService.reserve("b1", 0))
                .thenThrow(new InvalidQuantityException());

        mvc.perform(post("/api/books/b1/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":0}"))
                .andExpectAll(
                        status().isBadRequest(),
                        jsonPath("$.code").value("INVALID_QUANTITY"));
    }

    @Test
    void missingBookMapsTo404() throws Exception {
        when(reservationService.read("no-book"))
                .thenThrow(new BookNotFoundException());

        mvc.perform(get("/api/books/no-book"))
                .andExpectAll(
                        status().isNotFound(),
                        jsonPath("$.code").value("BOOK_NOT_FOUND"));
    }

    @Test
    void insufficientStockMapsTo409() throws Exception {
        when(reservationService.reserve("b1", 9))
                .thenThrow(new InsufficientStockException());

        mvc.perform(post("/api/books/b1/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":9}"))
                .andExpectAll(
                        status().isConflict(),
                        jsonPath("$.code").value("INSUFFICIENT_STOCK"));
    }

    @Test
    void getMappingSerializesBookView() throws Exception {
        when(reservationService.read("b1"))
                .thenReturn(new BookView(
                        "b1", "Spring", 3000, 5));

        mvc.perform(get("/api/books/b1"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.title").value("Spring"),
                        jsonPath("$.priceCents").value(3000),
                        jsonPath("$.available").value(5));
    }
}
```

**Có 5 methods**. Chúng phát hiện route/HTTP method, JSON record fields và advice mapping sai. Nhưng `@MockitoBean ReservationService` thay service thật, vì vậy:

- Không chạy `ReservationService.reserve`.
- Không chạy `@Transactional` proxy.
- Không chạy JPA query, flush, optimistic lock.
- Không chứng minh DB rollback.
- Không chứng minh real HTTP socket.

**Một dấu hiệu nguy hiểm:** Nếu ai đó xóa code validate quantity trong service, `invalidQuantityMapsTo400` có thể vẫn pass vì **mock được lập trình để ném exception**. Test `ReservationServiceTest.badQuantityFailsBeforeRepositoryCall` mới bắt nhánh service, còn full flow test giúp phát hiện wiring.

## 27. Full-context MockMvc: controller → service → JPA

**`src/test/java/com/example/testscope/ReservationFlowMockMvcTest.java`**

```java
package com.example.testscope;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class ReservationFlowMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    BookRepository repository;

    @Autowired
    EntityManager entityManager;

    @BeforeEach
    void seedBook() {
        repository.saveAndFlush(
                new Book("mvc-book", "Context", 2500, 5));
    }

    @Test
    void successfulPostUpdatesRealJpaState()
            throws Exception {

        mvc.perform(post("/api/books/mvc-book/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":2}"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.remaining").value(3));

        entityManager.flush();
        entityManager.clear();

        assertEquals(3,
                repository.findById("mvc-book")
                        .orElseThrow().getStock());
    }

    @Test
    void forbiddenByBusinessRuleDoesNotReduceStock()
            throws Exception {

        mvc.perform(post("/api/books/mvc-book/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":7}"))
                .andExpectAll(
                        status().isConflict(),
                        jsonPath("$.code").value("INSUFFICIENT_STOCK"));

        entityManager.flush();
        entityManager.clear();

        assertEquals(5,
                repository.findById("mvc-book")
                        .orElseThrow().getStock());
    }

    @Test
    void getReadsPersistedBookThroughAllLayers()
            throws Exception {

        mvc.perform(get("/api/books/mvc-book"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.title").value("Context"),
                        jsonPath("$.available").value(5));
    }
}
```

**Có 3 methods**. Spring load application context rộng, controller/service/repository **đều thật**, MockMvc không dùng TCP. Test class có `@Transactional`; mỗi method và `@BeforeEach` chạy trong test-managed transaction rồi rollback ở cuối test. Đây là chiến lược **isolation rẻ** cho DB operations trong mock servlet test, cho phép context cache reuse.

**Cảnh báo khả năng phát hiện lỗi:** Nếu xóa service `@Transactional`, test này vẫn có transaction do **test class** cung cấp. Entity có thể vẫn managed và dirty checking vẫn flush; test có thể xanh dù production bị lỗi. Để bảo vệ transaction do service tạo trong server thread, bài có `ReservationRealHttpTest` bên dưới **không có `@Transactional` ở test class**.

### 27.1. Không nhầm test transaction rollback với “service không commit”

Test transaction rollback ở cuối không đồng nghĩa application trả về lỗi. Khi chạy MockMvc cùng thread, nhiều operations cùng transaction và read-your-writes. Nếu production yêu cầu commit trước khi gửi event hoặc trước request thứ hai, cần test ngoài test-managed transaction hoặc real HTTP/integration context phù hợp.

## 28. Real HTTP: bắt khoảng trống transaction thật

**`src/test/java/com/example/testscope/ReservationRealHttpTest.java`**

```java
package com.example.testscope;

import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReservationRealHttpTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    BookRepository repository;

    private String id;

    @BeforeEach
    void createUniqueBook() {
        id = "http-" + UUID.randomUUID();
        repository.saveAndFlush(
                new Book(id, "Real HTTP", 2800, 5));
    }

    @AfterEach
    void deleteOnlyOurBook() {
        if (id != null) {
            repository.deleteById(id);
        }
    }

    @Test
    void httpPostActuallyCommitsStockChange() {
        ResponseEntity<ReservationReceipt> response =
                http.postForEntity(
                        "/api/books/{id}/reserve",
                        new ReserveRequest(2),
                        ReservationReceipt.class,
                        id);

        assertEquals(200, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals(3, response.getBody().remaining());

        // A separate repository call observes committed state.
        assertEquals(3,
                repository.findById(id).orElseThrow()
                        .getStock());
    }

    @Test
    void unknownIdThroughTcpReturns404() {
        ResponseEntity<ReservationAdvice.ErrorBody> response =
                http.getForEntity(
                        "/api/books/{id}",
                        ReservationAdvice.ErrorBody.class,
                        "not-present-" + UUID.randomUUID());

        assertEquals(404, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals(
                "BOOK_NOT_FOUND", response.getBody().code());
    }
}
```

**Có 2 methods**, server lắng nghe random port thật. Test không có `@Transactional` nên `@BeforeEach` seed commit thông qua repository transaction, HTTP request xử lý trong server thread/transaction của service, `@AfterEach` cleanup cụ thể **chỉ ID test tạo**. Một test có thể fail sau request mà `@AfterEach` vẫn chạy trong test lifecycle, giúp tránh dữ liệu sót lại.

**Một giới hạn khác:** `@AfterEach` không được bảo đảm khi process bị kill -9/CI host chết. Với môi trường chia sẻ cần schema/database/container isolated hoặc janitor có ownership. Trong H2 in-memory demo, context/datasource đóng khi JVM test kết thúc. Không xóa toàn database shared để tiết kiệm vài dòng code.

### 28.1. Vì sao transaction boundary giúp phát hiện bug?

Khi service có `@Transactional`, entity lấy bởi repository ở trong service transaction, bị mutate và JPA dirty checking flush khi transaction commit. Nếu annotation bị xóa, transaction của repository.findById (read-only method boundary) thường kết thúc trước khi service mutate entity; entity có thể trở thành detached, nên phép mutate không được commit. Real HTTP test kiểm **DB state sau response**, phát hiện được behavior này trong topology demo.

**Đừng suy rộng** rằng mọi service thiếu `@Transactional` đều fail: một service có thể gọi `save(...)` riêng tạo transaction hoặc có transaction ở caller. Test phải gắn với contract giao dịch cụ thể của ứng dụng.

## 29. Tổng số test và phân bổ mục tiêu

| Test class | Số `@Test` | Scope | Lỗi bắt tốt |
|---|---:|---|---|
| `ReservationServiceTest` | 5 | Pure unit | Business validation, stock math, errors |
| `BookRepositoryTest` | 2 | Data JPA slice | Derived query, entity dirty checking |
| `ReservationControllerMvcTest` | 5 | MVC slice | Routes, JSON, advice, mappings |
| `ReservationFlowMockMvcTest` | 3 | Full context, mock HTTP | Controller–service–JPA wiring và data |
| `ReservationRealHttpTest` | 2 | Full context, TCP | Server-side commit và real HTTP |
| **Tổng** | **17** | Nhiều scopes có chủ đích | Chồng lấp hợp lý, không thay nhau |

Đây **không phải** “17 test = 17 contexts”. Pure JUnit không cần context. JPA/MVC/full-context HTTP là các configuration keys khác nhau. Các methods trong một class có thể share context nhưng rollback/cleanup **dữ liệu** theo chiến lược riêng. Mục tiêu là mỗi scope có **ít nhất một lý do phát hiện lỗi riêng**; không tạo 50 full contexts chỉ để lặp cùng một assertion.

### 29.1. Lệnh chạy

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

Chạy chọn class để debug:

```bash
./gradlew test --tests com.example.testscope.ReservationRealHttpTest
```

Kết quả **dự kiến** khi JDK/Gradle/dependency resolution phù hợp là `BUILD SUCCESSFUL` và report ở `build/reports/tests/test/index.html`. **Đây là kết quả dự kiến từ rà soát mã; tôi chưa chạy Gradle trong repository của người học.** Context startup timings/hit counts không có giá trị stdout cố định; chúng phụ thuộc CI/máy chạy.

## 30. Cách đo TestContext cache thật, không đoán

Spring TestContext hỗ trợ log thống kê cache qua category:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Thêm dòng trên vào `src/test/resources/application.properties` khi muốn debug rồi chạy suite. Logs có thể xuất hiện ở nhiều lifecycle points, phản ánh hitCount/missCount/context size cho **JVM test process**. Không suy “mỗi hit = một test method”; listener và Spring integration có thể access context nhiều lần trong một method.

Các bước điều tra:

1. Chạy baseline cả suite trên CI có hardware cố định, lưu Gradle report và cache DEBUG.
2. Ghi context count/missCount/hitCount, total elapsed, GC, container startup.
3. Chạy lại đủ lần để phân biệt cold cache (JVM mới) và warm reuse **trong cùng JVM**.
4. Group test classes theo configuration keys (profiles, overrides, properties, web environment).
5. Sửa **những khác biệt không có giá trị kiểm thử**, không sửa negative scenarios.
6. Chạy lại với cùng load, JVM/forks và concurrency settings.
7. So sánh **suite time, failures, flaky rate và coverage/bug detection**, không chỉ cache hits.

**Quan trọng:** Nếu build chạy Gradle forks nhiều JVMs hoặc Maven Surefire forked processes, static TestContext cache **không chia sẻ** giữa processes. Tăng cache maxSize trong một fork không giúp test classes ở fork khác reuse context.

## 31. Gradle forks và song song: trade-off thường bị bỏ sót

Các settings như `maxParallelForks` và `forkEvery` trong Gradle kiểm cách test JVM được tạo/reused. Ví dụ **chỉ minh họa, không phải cấu hình đề xuất chung**:

```groovy
tasks.named('test') {
    useJUnitPlatform()
    maxParallelForks = 2
    forkEvery = 0
}
```

`forkEvery=0` có nghĩa Gradle không buộc fork test process mới sau N test classes; điều đó tạo cơ hội reuse TestContext cache trong mỗi fork. `maxParallelForks=2` có thể tăng throughput ở máy nhiều core nhưng tạo **hai caches độc lập**, tăng memory, contention và chi phí contexts lặp trong hai forks. Không tự mặc định “2 forks nhanh gấp đôi”.

Nếu test uses shared DB/port/queue/FS, chạy song song có thể tăng flakiness. Dùng **unique fixture IDs, DB schemas, ephemeral ports, test-owned prefixes**, giới hạn các tests không parallel-safe hoặc thêm JUnit resource locks. Không giải quyết race bằng chạy tất cả trong một thứ tự cố định rồi coi đó là test độc lập.

### 31.1. Context cache và JUnit method-level parallelism

TestContext cache được thiết kế để truy cập thread-safe ở mức framework, nhưng **beans bên trong có thể không thread-safe**. Hai test methods cùng dùng một singleton mutable map qua cùng context có thể race. Nếu bật JUnit parallel execution, phải xác minh state ownership, mock resets, repository fixtures và test container lifecycles. Khi test framework reset mocks giữa methods, song song có thể khiến test A xác minh mock trong lúc test B reset/ghi interactions; thiết kế test riêng fixtures hoặc tắt parallel ở tập shared mock.

## 32. `@DynamicPropertySource` và Testcontainers: cache key không đủ để bảo vệ dữ liệu động

`@DynamicPropertySource` hữu ích để đẩy URL/port/user/password của Testcontainers vào Spring Environment. Nhưng cần phân biệt:

- **Cấu hình key** có thể xét method metadata như một context customizer.
- **Giá trị dynamic được tính khi chạy** có thể liên quan container port/lifecycle cụ thể.
- Hai subclasses thừa kế cùng dynamic property method nhưng dùng các container khác nhau có nguy cơ **reuse context với cấu hình cũ**, nếu không thiết kế container lifecycle ổn định.
- Container database có thể giữ data dù Spring context được tái sử dụng.
- Một cached context chứa HTTP client/pool đã kết nối đến container bị stop/restart sẽ không tự refresh mọi endpoint.

**Hướng làm đúng:** Dùng container với lifecycle phù hợp và một nguồn dynamic properties ổn định cho các test classes được nhóm; hoặc tạo context riêng/`@DirtiesContext` có chủ đích khi container endpoint thật sự khác. Sau đó dùng DB transactions/truncation có scope và test data unique; đừng coi container mới hay cache mới tự bảo đảm isolation.

### 32.1. Ví dụ định nghĩa dynamic property — snippet, không thuộc demo

```java
@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry) {

    registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
```

Ở đây `postgres` là Testcontainers PostgreSQLContainer đã tạo; snippet cần imports và lifecycle phù hợp. Không copy nếu chưa xác định container là per-class hay shared. Đặc biệt nếu dùng reusable containers, đừng cho test run xóa tất cả dữ liệu của user/service khác.

## 33. `@ActiveProfiles` và property permutations: lúc nào cần nhiều contexts?

Một ứng dụng có feature toggle:

```text
feature.tax.enabled=true
feature.tax.enabled=false
```

Nếu behavior trong hai profile/properties **thực sự khác**, cần giữ cả hai tests. Nhưng nếu 50 classes mỗi class tự khai báo một tập properties giống nhau với ordering khác, có thể tạo keys phân mảnh không cần thiết.

Nguyên tắc:

- Định nghĩa số **ít** test configurations có mục đích rõ (ví dụ default, security-enabled, feature-off, real-http).
- Đưa **fixture thường dùng** vào shared minimal test config khi không làm thay semantics.
- Dùng `@Nested`/parameterized pure unit tests khi chỉ thay **input runtime**, không thay Spring bean graph.
- Dùng `ApplicationContextRunner.withPropertyValues(...)` khi mục tiêu là **auto-configuration conditional property** — tạo contexts nhỏ, không khởi động full app cho từng property case.
- Không cố làm một context với feature true rồi mutate Environment thành false trong runtime và giả Spring bean definitions tự được cấu hình lại; conditions thường được evaluate khi startup.

**Một context mới là chi phí xứng đáng nếu nó kiểm một code path cấu hình quan trọng.**

## 34. Mocks, spies, static state và các lỗi isolation khó thấy

| Nguồn state | Triệu chứng | Cách xử lý |
|---|---|---|
| Mockito mock trong context | Test B thấy interactions của A | Dựa vào Spring Mockito reset lifecycle hoặc verify/reset đúng; tránh parallel conflict |
| `@MockitoSpyBean` | Real method side effects chạy khi stubbing | `doReturn/doThrow` trên spy, không `when(spy.realMethod())` |
| Static registry/AtomicInteger | Chạy riêng pass, chạy suite fail | Reset explicit hoặc tránh static mutable |
| In-memory cache singleton | Test phụ thuộc thứ tự warm cache | Clear scoped entries trong lifecycle |
| SecurityContext ThreadLocal | User từ test trước xuất hiện | Spring Security Test cleanup + custom context cleanup |
| Mutable Clock | Test B thấy thời điểm do A advance | Per-test clock hoặc reset |
| HTTP pool/client | Server stub đã stop nhưng client giữ connection | Lifecycle/container isolation đúng |
| DB rows | Duplicate ID/constraint fail ngẫu nhiên | Unique per-test IDs/rollback/cleanup |
| Scheduler/async executor | Event đến sau `@AfterEach` | Disable job hoặc await bounded completion |
| File temp/shared directory | Windows lock/collision | JUnit `@TempDir`, close streams |
| System property | Một class đổi setting ảnh hưởng lớp khác | Save/restore trong `finally` hoặc riêng JVM |
| Kafka/Redis | Messages/keys của test trước còn | Per-test topic/group/prefix + cleanup |

**Tính độc lập quan trọng hơn việc suite chạy nhanh khi may mắn đúng thứ tự.** Cache chỉ là một tối ưu safe nếu test-owned state được quản lý tách biệt.

### 34.1. Không lạm dụng `Mockito.reset(mock)`

Spring Framework/Boot test support thường reset `@MockitoBean` mocks theo test lifecycle. Gọi `Mockito.reset` ở giữa test có thể làm mất interactions mà code under test cần verify và khiến test che bug. Khi manual mocks sống lâu, làm rõ lifecycle; nhiều khi tạo mock mới trong `@BeforeEach` cho pure unit test dễ hiểu hơn.

## 35. `@DirtiesContext` và cache thrashing

Nếu mọi test class có:

```java
@DirtiesContext
@SpringBootTest
class EveryTestReloadsContext {
    // ...
}
```

thì cache hit có thể bị phá, Hibernate/embedded server/clients khởi động liên tục. Hơn nữa, test có thể che state leak thay vì sửa nó. Trước khi dùng, hỏi:

- Đây là **data** cần cleanup hay bean definition thực sự bị thay?
- DB rollback đã đủ chưa?
- Có cache clear API an toàn theo test key không?
- Có thể tạo test fixture mới với UUID?
- Có background thread làm state thay đổi sau cleanup không?
- Một test có thể phá context chung theo cách không hoàn nguyên được không?

Nếu câu cuối “có”, `@DirtiesContext` hợp lý. Nếu chỉ một hàng sách được insert, rollback hoặc delete test-owned ID thường đúng hơn. Lưu ý context hierarchy có cơ chế eviction rộng hơn một class đơn lẻ; xem Spring docs khi dùng parent/child contexts.

## 36. Context failure threshold và thất bại dây chuyền

Từ Spring Framework 6.1, TestContext có **context failure threshold** mặc định **1** cho mỗi cache key. Nếu load context thất bại lần đầu, các tests tiếp theo dùng cùng key có thể nhận `IllegalStateException` ghi rằng framework **bỏ qua việc thử load lại**, thay vì load lỗi lặp lại hàng chục lần.

Điều này **không có nghĩa mỗi test có một bug khác nhau**. Khi suite báo nhiều classes “ApplicationContext failure threshold exceeded”, hãy tìm **root startup failure đầu tiên** cùng context key (configuration error, port collision, missing dependency) rồi sửa nguyên nhân. Có thể cấu hình `spring.test.context.failure.threshold` bằng JVM property khi có lý do điều tra, nhưng đừng tắt cơ chế chỉ để logs dài hơn.

**Đừng đánh giá một refactor cache là thất bại chỉ dựa vào số tests đỏ**: một lỗi config gây ra 40 errors có thể là **một context root cause**.

## 37. Mutation testing / regression test: đo khả năng phát hiện lỗi

Sau khi chọn phạm vi, dùng những thay đổi giả định để kiểm “test có thực sự bảo vệ gì không?”:

| Mutation/bug | Unit | MVC slice | JPA slice | Full MOCK | Real HTTP |
|---|---|---|---|---|---|
| Quantity 0 được phép | Bắt | Có thể **lọt** nếu service mock luôn ném | Không kiểm | Bắt | Bắt |
| JSON field đổi tên | Không | Bắt | Không | Bắt | Bắt nếu assert field |
| Query `findByTitleIgnoreCase` sai | Không nếu repo mock | Không | Bắt | Chỉ khi flow dùng query ấy | Chỉ khi flow dùng query ấy |
| Xóa `@Transactional` của service | **Lọt** | **Lọt** | JPA slice không load service | Có thể lọt do test transaction | Real HTTP DB assertion có thể bắt |
| Bỏ @Version | Unit không thấy concurrency | Không | Chỉ nếu test concurrency | Không nếu single-thread | Không nếu single-thread |
| Route `/reserve` sai | Không | Bắt | Không | Bắt | Bắt |
| Sai production DB dialect | Không | Không | H2 có thể lọt | H2 có thể lọt | H2 có thể lọt |
| Sai security authority | Không nếu không security test | Bắt nếu real filter/test | Không | Bắt nếu filter thật | Bắt nếu auth thật |
| Data leak giữa users | Không nếu không test ownership | Có thể che vì service mock | Không | Bắt nếu test user A/B | Bắt nếu test user A/B |
| Async event publish trùng | Không nếu không assert | Không | Không | Có thể bỏ sót | Cần broker/async integration |

**Điều quan trọng:** Chọn phạm vi không tách rời **assertions**. Real HTTP test chỉ assert status 200 vẫn có thể không phát hiện update DB không commit. Unit test với assertion chi tiết có thể giá trị hơn E2E test có assertion yếu. Ma trận dựa trên code mẫu và type lỗi cụ thể, không phải tuyên bố mọi test kiểu ấy chắc chắn bắt được.

## 38. Quy trình tối ưu test suite dựa trên bằng chứng

1. **Inventory tests:** mỗi class có annotation, mocks, profiles, dynamic properties, containers, side effects gì.
2. **Phân loại bug hypotheses:** business rules, controllers, repository mappings, transactions, HTTP, security, persistence semantics.
3. **Baseline:** đo total suite time, số unique context keys, cache hit/miss, số container starts, CI failures.
4. **Chọn phạm vi nhỏ nhất đủ phát hiện:** chuyển pure rule khỏi full context, dùng slice cho MVC/JPA/client, giữ full-flow tests cho AOP/wiring.
5. **Chuẩn hóa cấu hình thật sự giống nhau:** profiles, shared test configs, mock names/qualifiers; không thêm mocks.
6. **Cô lập dữ liệu:** rollback đúng boundary, unique IDs và cleanup resources ngoài DB.
7. **Kiểm negative scenarios:** thiếu transaction, sai query, sai JSON, invalid authorization, concurrency, failure paths.
8. **Thử suite theo thứ tự khác và chạy selected tests riêng** để bắt hidden dependencies.
9. **Đo lại cùng môi trường:** cache misses, wall-clock, memory, CPU, timeouts và flakiness.
10. **Giữ các tests mở rộng scope khi có giá trị phát hiện lỗi độc đáo.** Đừng xóa real HTTP transaction test chỉ vì nó chậm hơn unit.
11. **Document trade-offs:** H2 vs production DB; mocks vs network, test vs production thread.
12. **Theo dõi theo thời gian:** một refactor có thể giảm test duration hôm nay nhưng thêm nhiều cache keys sau vài tháng.

### 38.1. Một số metric hữu ích

| Metric | Diễn giải | Dễ hiểu sai |
|---|---|---|
| Gradle test task wall-clock | Feedback thực tế người dùng chờ | Không tách startup/test/container |
| TestContext cache hit/miss | Tần suất reuse theo key | Một method có thể có nhiều accesses |
| Số unique contexts | Fragmentation và memory | Ít context không bảo đảm coverage |
| Hibernate/DB startup time | Phần chi phí JPA | H2 và Postgres khác |
| Context failure count | Các cache key startup fail | Có thể chung một root cause |
| CI retry/flaky ratio | Test isolation/capacity issue | Retry xanh không sửa lỗi |
| p95 test execution time | Tính ổn định dưới CI | Không giống service runtime latency |
| Mutation score | Coverage behavior của mutations đã chọn | Không thay threat model/end-to-end test |
| Developer local feedback | Tốc độ lặp cho một class/suite | Không phải test correctness |

## 39. Anti-pattern và cách sửa

| Anti-pattern | Hậu quả | Thay bằng |
|---|---|---|
| `@SpringBootTest` cho mọi pure calculator | Startup nặng, feedback chậm | Plain JUnit |
| `@WebMvcTest` được dùng chứng minh transaction | Service đang mock | Full real service/DB test |
| Chỉ assert `contextLoads` | Coverage hành vi gần như không có | Specific behavior assertions |
| Mỗi class một `@MockBean` khác nhau không cần | Cache keys phân mảnh | Mock boundary tối thiểu, naming nhất quán |
| `@DirtiesContext` ở mọi class | Cache miss/reload liên tục | Rollback/fixture cleanup |
| Hard-code một book ID nhưng không rollback | Flaky khi chạy lại | Unique IDs hoặc test transaction |
| `@Transactional` quanh real HTTP và kỳ vọng rollback | Server thread commit độc lập | Explicit cleanup/DB isolation |
| Full test transaction che lỗi thiếu service transaction | False confidence | Real HTTP/non-test-transaction scenario |
| Dùng H2 để kết luận PostgreSQL locking đúng | SQL dialect/isolation khác | Testcontainers DB thực |
| Cache bean state để “tránh fixture setup” | Phụ thuộc thứ tự | Per-test fixtures |
| Dùng static MutableClock không reset | Test khác thấy thời gian sai | Clock riêng/reset |
| Mock service được kiểm thử | Bypass target logic | Mock downstream port, real service |
| Tắt security filters cho MVC tests security | Endpoint được cho phép giả | Include real SecurityFilterChain |
| Chạy parallel khi shared Mockito mocks | Race verification/reset | Isolate mocks hoặc giới hạn parallel |
| Tăng cache maxSize liên tục | Memory/GC tăng | Giảm key explosion trước |
| Set forkEvery=1 để chữa data contamination | Che leak, mất cache reuse | Sửa cleanup; fork khi thật cần |
| Trùng container port giữa test classes | Collisions và false failures | Random ports/unique environments |
| Đọc log context error cuối cùng | Bỏ sót root cause | Tìm first failed context key |
| Xóa slow full-flow tests vì pass từ slice | Mất coverage AOP/wiring | Giữ số ít high-value full tests |
| Chỉ đo số test methods | Không đo thời gian/chi phí/coverage | Test context/bug-detection metrics |

## 40. Bài tập kiểm tra hiểu biết

### A — Chọn phạm vi

Một method tính phí chuyển hàng theo khối lượng và mã vùng, không dùng Spring beans. Có nên dùng `@SpringBootTest`?

**Đáp án:** Không cần. Pure JUnit với boundary values thường đủ; thêm integration test nếu kết quả phụ thuộc cấu hình/serialization khác mà unit không kiểm.

### B — Tên mock

Hai `@WebMvcTest` cùng mock bean `PaymentGateway` nhưng đặt field names khác nhau. Có chắc reuse context?

**Đáp án:** Không. Field name có thể là fallback qualifier và ảnh hưởng context key. Đặt tên thống nhất nếu cùng bean/qualifier và scope, không làm mất assertions khác.

### C — Dirty context

Test thêm một row trong H2 và có `@Transactional` rollback, nhưng developer thêm `@DirtiesContext` để “làm sạch”. Cần không?

**Đáp án:** Thường không. Transaction rollback đã xử lý DB state trong boundary ấy; @DirtiesContext làm reload context không cần thiết.

### D — Unit pass, prod sai

Service unit test giảm stock từ 5 xuống 3 nhưng HTTP real app không commit. Thiếu loại test nào?

**Đáp án:** Test transaction/service bean thật và server-side persisted state; real HTTP/non-test-managed transaction hữu ích.

### E — GET qua MockMvc

`@SpringBootTest + @AutoConfigureMockMvc` có mở socket tới embedded Tomcat không?

**Đáp án:** Không. MockMvc gọi servlet stack trong memory; cần RANDOM_PORT để kiểm actual TCP/server thread.

### F — Test transaction ở random port

Class real HTTP có `@Transactional`, server POST ghi DB. Sau test, row có chắc rollback không?

**Đáp án:** Không. Client test thread và server thread có transactions khác. Dùng scoped cleanup, DB isolation hoặc container/transactions ở đúng service boundary.

### G — Lỗi query

Repository có `findByTitleIgnoreCase`, unit test mock luôn trả book. Mutation xóa IgnoreCase có bị unit bắt?

**Đáp án:** Không. `@DataJpaTest` chạy derived query với DB mới bắt trường hợp đó.

### H — Cache maxSize

Suite có 100 context keys do 100 properties khác nhau, mỗi context đắt tiền. Tăng maxSize 32→128 luôn là giải pháp tốt?

**Đáp án:** Không. Có thể tăng memory/GC; trước tiên loại khác biệt không có giá trị và đo actual cache evictions, sau đó mới thử maxSize.

### I — Độc lập

Test A set static flag=true, test B mong false. Suite pass khi B chạy trước. Có thể gọi độc lập không?

**Đáp án:** Không. State leak; reset flag/loại static mutable, thêm order/parallel tests để phát hiện chứ không hard-code thứ tự.

### J — @MockitoBean

Full context test đặt @MockitoBean trên chính ReservationService rồi assert HTTP 200. Có kiểm service @Transactional không?

**Đáp án:** Không. Mock thay bean gốc và AOP interceptors; phải giữ service thật.

### K — Testcontainers

Một @DynamicPropertySource method dùng container per subclass, nhưng cache reuse context với cổng container cũ. Cách xử lý?

**Đáp án:** Đồng bộ lifecycle và config key, hoặc tách context/DirtiesContext theo config thực khi endpoint khác. Không coi dynamic supplier là cơ chế tự refresh cached client bean.

### L — Spring cache per JVM

Gradle có hai fork JVM. Chúng có dùng chung static TestContext cache?

**Đáp án:** Không. Mỗi JVM process có cache riêng. Trade-off giữa parallel throughput, memory và reuse.

### M — Context failure threshold

Hàng chục tests báo “failure threshold exceeded” sau một context startup error. Nên sửa bao nhiêu lỗi?

**Đáp án:** Điều tra root failure đầu tiên theo context key; có thể chỉ một lỗi cấu hình làm tất cả fail nhanh.

### N — Tối ưu sai mục tiêu

Sau refactor, CI nhanh hơn 30% nhưng bỏ hết @DataJpaTest và real HTTP, chỉ còn mocked MVC tests. Có thể kết luận chất lượng cải thiện không?

**Đáp án:** Không. Cần kiểm bug detection, DB semantics và integration coverage không bị mất. Tốc độ không thể đứng một mình.

### O — Mutation

Xóa service `@Transactional` mà suite vẫn xanh. Có nên ngay lập tức thêm `@DirtiesContext`?

**Đáp án:** Không. Cần một test không có test-managed transaction bao trọn service, có persist-readback qua server/client boundary; @DirtiesContext không giúp phát hiện transaction đúng.

### P — Concurrency

Một test JPA rollback chạy ổn tuần tự, nhưng khi bật parallel hai tests dùng cùng ID cạnh tranh tạo row. Sửa thế nào?

**Đáp án:** Per-test unique IDs/schema/transaction isolation hoặc tắt parallel cho tests shared state; context mới chưa chắc giải quyết shared DB.

## 41. Checklist nghiệm thu trước khi merge

- [ ] Mỗi nhóm tests có bug hypothesis và phạm vi cần kiểm.
- [ ] Pure Java rules được test không cần Spring khi có thể.
- [ ] Controller mapping/JSON/advice được test bằng MVC slice.
- [ ] Repository mappings/queries được test bằng JPA slice và DB phù hợp.
- [ ] Các integration boundary AOP/@Transactional/security được giữ thực ở ít nhất một số test.
- [ ] Có ít nhất một end-to-end path bảo vệ cross-layer wiring quan trọng.
- [ ] Real HTTP test được phân biệt với MockMvc.
- [ ] Test transaction và server-side commit được phân biệt rõ.
- [ ] Mock không thay chính bean logic mà test muốn chứng minh.
- [ ] Test không coi “context starts” là toàn bộ coverage.
- [ ] Các variants `@ActiveProfiles`/properties có lý do tồn tại.
- [ ] `@MockitoBean` names/qualifiers nhất quán khi có cùng target.
- [ ] Bean override không vô tình tạo bean giả để che missing production wiring.
- [ ] Context cache key được hiểu theo metadata, không theo tên class đơn giản.
- [ ] Đã biết cache mặc định 32 contexts/LRU, các forks không share cache.
- [ ] Có baseline cache hits/misses và suite elapsed trước tối ưu.
- [ ] `@DirtiesContext` chỉ dùng khi context thật sự bị dirty.
- [ ] Database data isolated bằng rollback hoặc cleanup đúng boundary.
- [ ] Tests real HTTP có explicit cleanup cho committed data.
- [ ] Test data unique theo ID/tenant khi có parallel/shared DB.
- [ ] In-memory caches, clocks, scheduled jobs và static state được reset/isolated.
- [ ] Mocks không bị parallel reset/verification races.
- [ ] Testcontainers lifecycle khớp @DynamicPropertySource/context cache.
- [ ] Không test production DB dialect bằng H2 rồi kết luận mọi SQL đều đúng.
- [ ] Có negative tests cho invalid qty, missing data, insufficient stock.
- [ ] Có positive test persisted state sau service operation.
- [ ] Suite có thể chạy từng class riêng, không cần thứ tự cố định.
- [ ] Không dùng sleeps vô hạn; async tests có bounded timeouts.
- [ ] Các external resources (files, Redis keys, queue events) có ownership/cleanup.
- [ ] Có process quản lý test data sau CI crash khi dùng shared environment.
- [ ] Không hy sinh valuable unique full-flow tests để tăng cache hits.
- [ ] Có đo lại performance và flakiness sau thay đổi.
- [ ] Báo cáo QA nêu rõ test source reviewed hay đã được thực thi.

**Kết luận:** Phạm vi test tối ưu không phải là “nhỏ nhất trong mọi tình huống”, cũng không phải “cứ SpringBootTest là chắc chắn đúng”. Nó là **phạm vi nhỏ nhất vẫn đủ bắt lỗi quan trọng**. Context cache cho phép nhiều integration tests dùng lại chi phí startup khi cấu hình giống nhau, nhưng bắt buộc **tách dữ liệu và state mutable theo test**. Dùng unit tests cho domain rules, slice tests cho HTTP/JPA/client conditions và một lượng ít nhưng chiến lược full-context/real HTTP tests cho AOP, transaction và system wiring; đo cache keys/CI time/flakiness trước khi refactor. Nếu một tối ưu làm test xanh nhanh hơn nhưng che transaction, query, security hoặc cross-layer errors, đó không phải tối ưu chất lượng.

### Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Context Caching, cache key, LRU/maxSize=32 và thống kê DEBUG: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — @DirtiesContext và eviction semantics: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework 6.2 — @MockitoBean/@MockitoSpyBean, qualifiers, field names và context reuse: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework 6.2 — Bean overriding / AOP proxies: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html
- Spring Framework 6.2 — Context failure threshold: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html
- Spring Framework 6.2 — Transaction management in tests: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — @DynamicPropertySource: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dynamicpropertysource.html
- Spring Boot 3.5 — Testing Spring Boot Applications: @WebMvcTest/@DataJpaTest/@RestClientTest/@SpringBootTest: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Auto-configured Data JPA tests: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-spring-data-jpa
- JUnit Jupiter — Parallel execution, lifecycle và resource locks: https://junit.org/junit5/docs/current/user-guide/
- Gradle — Test task, maxParallelForks và forkEvery: https://docs.gradle.org/current/userguide/java_testing.html
