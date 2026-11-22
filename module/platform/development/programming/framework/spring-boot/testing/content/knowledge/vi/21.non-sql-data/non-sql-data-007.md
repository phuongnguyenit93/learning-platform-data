# Dọn collection, key, index hoặc dữ liệu giữa các test

Trong kiểm thử ứng dụng Spring Boot dùng **dữ liệu ngoài SQL**, một bài test có thể xanh khi chạy riêng nhưng đỏ khi chạy cả suite vì dữ liệu của test trước vẫn nằm trong MongoDB, Redis, Elasticsearch hoặc object storage. Một document cũ làm kết quả query tăng thêm một phần tử; một Redis key vẫn còn làm cache trả bản ghi lỗi thời; một MongoDB unique index bị xóa cùng collection khiến test duplicate-key không còn bắt lỗi; hoặc một Elasticsearch index có mapping cũ khiến test chỉ thất bại trên CI. Những lỗi như vậy thường bị hiểu nhầm là lỗi business logic, trong khi nguyên nhân thật là **test không có trạng thái khởi đầu và hậu điều kiện được kiểm soát**.

Bài Knowledge này tập trung vào **dọn collection, key, index hoặc dữ liệu giữa các test**, trong nhóm **Dữ liệu ngoài SQL** của module **Spring Boot – testing**. Mục tiêu không phải gọi một lệnh xóa càng mạnh càng tốt, mà là **tạo ranh giới dữ liệu thử nghiệm an toàn, tái lập được và không phá tài nguyên của test khác hay môi trường production**.

Ví dụ áp dụng cho **Java 17+, Spring Boot 3.5.x, Spring Data MongoDB 4.5.x, Spring Data Redis 3.5.x, JUnit Jupiter 5 và Testcontainers 1.21.x**. Phần runnable có MongoDB và Redis containers riêng biệt, dùng `@DataMongoTest`/`@DataRedisTest`, `@BeforeEach`/`@AfterEach`, `MongoTemplate`, `StringRedisTemplate`, `@DynamicPropertySource`. Elasticsearch/OpenSearch, cache đa tầng và object storage được trình bày bằng patterns và snippets vì API phụ thuộc engine/version.

**Nguyên tắc không được bỏ qua:** Không bao giờ chạy `FLUSHALL`, `DROP DATABASE`, xóa toàn bộ bucket/index hoặc cleanup theo prefix quá rộng trên một hệ thống chưa được xác minh là **môi trường dành riêng cho test**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Nêu lý do dữ liệu NoSQL tồn dư làm kiểm thử **flaky** và cách phát hiện contamination.
- Lập inventory những gì cần dọn: document, collection, index, key, TTL, cache entry, search index, alias và object prefix.
- Chọn giữa **data deletion**, **namespace isolation**, **database/container isolation** và **fresh resource per test**.
- Biết `MongoTemplate.remove(...)` khác `dropCollection(...)` ở chỗ **giữ hay xóa indexes**.
- Recreate đúng **unique index** sau khi drop Mongo collection; không tin vào auto-index creation mặc định.
- Dọn Redis keys theo **danh sách key đã tạo** hoặc namespace dùng riêng; phân biệt `SCAN`, `KEYS`, `DEL`, `UNLINK`, `FLUSHDB` và `FLUSHALL`.
- Thiết kế TTL/expiration test xác định và không dựa vào ngủ vài millisecond.
- Hiểu Elasticsearch index lifecycle, alias, mapping và near-real-time refresh.
- Dùng Testcontainers, dynamic connection properties và test slices mà không phụ thuộc Mongo/Redis cài cố định trên laptop.
- Bảo vệ parallel tests, Spring TestContext cache, retry, test failure và cleanup failure.
- Viết integration tests kiểm **trạng thái trước – hành vi – hậu điều kiện – cleanup** thay vì chỉ assert một giá trị trả về.

## 2. Tại sao dữ liệu ngoài SQL dễ làm bẩn test?

Một quy trình gây flaky thường diễn ra như sau:

```text
Test A
  -> ghi Mongo document id=profile-1
  -> ghi Redis key cache:profile:profile-1
  -> assert PASS
  -> không cleanup

Test B
  -> mong query Mongo chỉ có một document
  -> insert document khác
  -> query ra hai document => FAIL

Test C
  -> mong cache miss
  -> Redis key của Test A vẫn có => FAIL

Chạy Test B/C riêng lẻ có thể PASS.
Chạy suite theo thứ tự A -> B -> C thì FAIL.
```

Nguyên nhân có thể nằm ngoài kết quả return value: DB, Redis, index metadata, cache trong JVM, stream offset, object storage, search alias, thậm chí task bất đồng bộ từ test trước.

Một test lý tưởng không cần test khác “dọn hộ”. Thay đổi thứ tự chạy hay chạy lại một test bất kỳ phải không đổi ý nghĩa. Trong thực tế, ta kết hợp **isolation và cleanup**, chứ không chỉ dựa vào một annotation của JUnit.

## 3. Phân loại tài nguyên và cách dọn

| Store | Đơn vị dữ liệu | Đơn vị metadata | Cách dọn hẹp nhất | Hệ quả cần nhớ |
|---|---|---|---|---|
| MongoDB | Document | Collection, index, TTL index | `remove(Query, Type)` | Giữ indexes, phải dùng query đúng tenant/run |
| MongoDB | Collection | Indexes trong collection | `dropCollection(Type)` | **Mất toàn bộ indexes của collection** |
| Redis | Key/value, hash, set, stream | TTL, consumer group, key namespace | `delete(key)` hoặc tập key sở hữu | Không ảnh hưởng key khác nếu tên key chính xác |
| Redis | Nhiều keys | Keyspace | `SCAN` với prefix riêng rồi `DEL`/`UNLINK` | SCAN không phải snapshot atomic; chú ý concurrent writes |
| Elasticsearch/OpenSearch | Document | Index, mapping, alias, template | Delete document-by-ID hoặc index test riêng | Search gần real-time; xóa index còn xóa mapping/shards |
| Object storage | Object/version | Bucket, version, lifecycle policy | Xóa theo object key/prefix của run | Versioned bucket còn versions/delete markers |
| Cassandra | Rows | Keyspace/table schema | Partition-scoped delete hoặc keyspace riêng | Tombstones/compaction làm cleanup khác SQL |
| Neo4j | Nodes/relationships | Constraints/indexes | Xóa subgraph của run | Có relationships, không xóa cả graph dùng chung |
| In-process cache | Entries | Cache manager/config | Evict key thuộc test | Không dọn Mongo/Redis bên ngoài |
| Message broker | Message/offset | Topic/consumer group | Unique topic/group hoặc purge theo test infra | Offset và events có thể còn sau test |

Cùng từ “**index**” nhưng Mongo index và Elasticsearch index là hai thứ khác nhau: Mongo index là cấu trúc tìm kiếm/constraint của collection; Elasticsearch index là **đơn vị lưu trữ documents và mappings**. Không áp dụng một phương án xóa cho cả hai.

## 4. Thứ tự ưu tiên: cô lập trước, cleanup sau

Một chiến lược hiệu quả thường ưu tiên:

1. **Container hoặc service instance riêng cho suite** bằng Testcontainers.
2. **Database/index/bucket/prefix riêng cho test class hoặc test run**.
3. **Định danh duy nhất cho từng test** nếu cần chạy song song.
4. **Cleanup scoped** sau khi sử dụng, dùng chính các key/document IDs đã tạo.
5. **Kiểm hậu điều kiện** và báo lỗi nếu cleanup không thành công.
6. **Dọn từ đầu** ở những trường hợp có thể còn rác do JVM bị kill ở lượt chạy trước.

Không phải mọi test cần container mới cho từng method. Container lifecycle dài hơn kết hợp namespace riêng thường nhanh hơn; nhưng test không được dùng dữ liệu của nhau. Khi dữ liệu/rủi ro cần sự tách biệt tuyệt đối, test class riêng hoặc database riêng có thể đáng chi phí.

### 4.1. Bốn thuật ngữ dễ nhầm

- **Isolation:** không thể tác động lên dữ liệu ngoài phạm vi test của mình.
- **Setup/reset:** đưa môi trường test về trạng thái tiền điều kiện trước test.
- **Teardown/cleanup:** xóa tài nguyên đã tạo sau test.
- **Disposal:** hủy toàn bộ container/database/bucket thuộc suite/run.

Nếu cleanup sau test bị bỏ vì process bị dừng đột ngột, **container disposal hoặc namespace TTL** là lớp bảo vệ bổ sung. Nhưng một container bị crash trong shared staging không được phép dẫn đến dữ liệu mồ côi tồn tại mãi mà không có owner.

## 5. `@BeforeEach` hay `@AfterEach`?

Cả hai có vai trò riêng:

```java
@BeforeEach
void prepare() {
    // Xác minh tiền điều kiện và tạo schema/index bắt buộc.
}

@AfterEach
void cleanup() {
    // Xóa chính tài nguyên test vừa tạo.
}
```

`@BeforeEach` có thể xóa dữ liệu tồn dư **nếu nó chắc chắn nằm trong database/index/namespace riêng của test**. `@AfterEach` giúp giữ môi trường sạch và giúp phát hiện cleanup failure. Một mẫu tốt dùng cả hai, nhưng không thực hiện **xóa rộng** trên database dùng chung.

**Bẫy quan trọng:** Không phải mọi tình huống đều chạy `@AfterEach`. JVM kill, mất Docker daemon, timeout hoặc machine crash có thể ngăn teardown. Vì thế:

- Với container ephemeral, dọn được toàn bộ môi trường khi container bị hủy.
- Với shared test infrastructure, nên có prefix chứa run ID, TTL và garbage collector có phân quyền.
- Với object storage, dọn cả versions/delete markers nếu bucket versioned.
- Với cùng container nhưng nhiều test chạy parallel, per-test namespace giúp một cleanup không xóa dữ liệu test khác.

### 5.1. Test xanh nhưng cleanup lỗi thì sao?

Cleanup là một phần của test contract. Nếu test thực hiện logic đúng mà `@AfterEach` không thể dọn key/document của nó, **test run phải báo lỗi**; không nên `catch(Exception ignored)` để che contamination. Nếu cần preserve state để debug, đó phải là chế độ chẩn đoán rõ, có owner/TTL và không dùng tài nguyên production.

## 6. MongoDB: xóa document khác với drop collection

Hai thao tác:

```java
// Snippet trong test có MongoTemplate mongo.
// Xóa tất cả Profile documents; collection/indexes vẫn còn.
mongo.remove(new Query(), Profile.class);

// Xóa cả collection Profile cùng indexes của collection.
mongo.dropCollection(Profile.class);
```

**Khác biệt lớn nhất:** `remove(...)` giữ collection và unique/TTL/text indexes; `dropCollection(...)` xóa cả indexes. Nếu bạn drop một collection có `UNIQUE(email)` rồi insert lại mà chưa tạo index, duplicate email có thể được chấp nhận. Một test nhận “hai lần insert đều thành công” không nhất thiết là bug của Mongo; có thể chính cleanup đã làm mất constraint.

Spring Data MongoDB từ nhiều phiên bản gần đây **không tự bật auto-index creation theo mặc định**. Ngay cả khi bật, cơ chế auto-index không bảo đảm indexes tự xuất hiện lại sau khi collection bị drop/recreated trong cùng application lifecycle. Vì vậy test cần **ensure indexes một cách tường minh** sau reset, hoặc dùng migration/index initializer thực được kiểm.

### 6.1. Khi nào dùng `remove`?

Dùng khi:

- Collection schema/indexes cố định, không cần test migration.
- Muốn dọn documents trước mỗi method nhưng giữ unique/TTL indexes.
- Test chạy trên **database test tách biệt** và muốn ít chi phí hơn drop/create collection.
- Có thể xóa theo `runId`/`tenantId`, không chạm dữ liệu khác.

Ví dụ scoped:

```java
// Snippet: chỉ khi Profile có field testRunId và dữ liệu là test-only.
mongo.remove(
        Query.query(Criteria.where("testRunId").is(runId)),
        Profile.class);
```

Đừng dùng `new Query()` không điều kiện trên một collection phục vụ nhiều test/tenant trong shared database. “Không có WHERE” trong NoSQL cũng nguy hiểm như SQL `DELETE` không có `WHERE`.

### 6.2. Khi nào dùng `dropCollection`?

Dùng khi:

- Collection chỉ thuộc test class/run và không được chia sẻ.
- Cần reset cả documents và indexes/mapping collection.
- Đang test chính lifecycle **drop → recreate → ensure index**.

Sau drop, nếu contract cần unique index:

```java
mongo.createCollection(Profile.class);
mongo.indexOps(Profile.class)
        .ensureIndex(new Index()
                .on("email", Sort.Direction.ASC)
                .unique());
```

Đây là snippet; `Profile`, `mongo` và imports sẽ có trong project mẫu. Với production migration, index creation phải được quản lý có kiểm soát; test có thể chạy chính migration thay vì một bản copy.

## 7. MongoDB: phải kiểm index, không chỉ data

Nếu database test có indexes, kiểm chúng cũng là hợp đồng.

```java
List<IndexInfo> info =
        mongo.indexOps(Profile.class).getIndexInfo();

assertTrue(info.stream().anyMatch(index ->
        index.isUnique()
        && index.isIndexForFields(List.of("email"))));
```

Dòng trên là snippet với imports. Nó bắt trường hợp unique index bị mất. Nhưng nó chưa đủ để kiểm rằng **duplicate thực sự bị DB từ chối**; nên có test insert hai documents khác `_id` nhưng cùng email và mong `DuplicateKeyException`.

Có những indexes cần thêm test riêng:

- **Unique/compound indexes:** duplicate combination bị chặn.
- **TTL index:** document phải hết hạn theo policy nhưng Mongo TTL monitor chạy bất đồng bộ, không nên assert xóa ngay đúng mili-giây.
- **Text/geospatial indexes:** query/score/sort cần fixtures và index đúng.
- **Partial indexes:** filter expression đúng và không chặn document nằm ngoài scope.
- **Collation:** case/accent sensitivity của unique/search theo contract.
- **Sparse indexes:** sự khác biệt giữa missing/null khi unique constraint là rủi ro thực.

**Không nên drop index production chỉ để tái hiện một test.** Dùng test database và migration/index initializer riêng. Nếu mục tiêu là bảo vệ index lifecycle, hãy cố tình drop/recreate **chỉ index có owner**, rồi assert kết quả.

## 8. Redis: key sống lâu hơn JVM

Redis là external state; việc JUnit tạo lại controller hoặc Spring context không tự xóa key Redis.

Ví dụ:

```text
it:pricing:run-123:quote:BOOK = 216000 (TTL 60s)
it:pricing:run-999:quote:BOOK = 240000 (TTL 60s)
app:session:real-user-42      = sensitive data (KHÔNG ĐƯỢC ĐỤNG)
```

Nếu test cleanup dùng `FLUSHDB`, nó có thể xóa **mọi key** trong selected Redis logical database, bao gồm session/caches không thuộc test. `FLUSHALL` còn rộng hơn: xóa toàn bộ databases trên instance. Trên Redis Cluster, logical DB semantics cũng khác; đừng dựa vào số DB riêng là isolation đủ mạnh.

**Pattern an toàn:**

```text
it:<suite>:<runId>:<testId>:<objectType>:<objectId>
```

Ví dụ cụ thể:

```text
it:cleanup:7f2a:user:41
it:cleanup:7f2a:cart:41
```

Với data fixture có thể viết hết key names trước, **theo dõi Set<String> ownedKeys** và cleanup đúng những keys ấy. Nếu key do một background job tạo khó liệt kê, dùng namespace độc quyền của test rồi `SCAN` theo prefix.

### 8.1. `DEL`, `UNLINK`, `EXPIRE` và TTL

- **`DEL`:** xóa key, kết quả trả số keys được xóa.
- **`UNLINK`:** gỡ key khỏi keyspace, reclaim memory bất đồng bộ; hữu ích cho value lớn khi phù hợp.
- **`EXPIRE`/TTL:** đặt thời gian hết hạn, không phải thay thế teardown chắc chắn. Expiration timing không phải đồng hồ chính xác theo milli-giây.
- **`PERSIST`:** xóa TTL để key tồn tại mãi, không phải cleanup; cẩn thận khi test.
- **`FLUSHDB`/`FLUSHALL`:** xóa diện rộng, **chỉ** cân nhắc trong Redis container instance độc quyền và khi thực sự cần reset toàn bộ.

Test dùng TTL có thể xác minh value và TTL dương mà không chờ hết hạn:

```java
redis.opsForValue().set(
        key, "ready", Duration.ofMinutes(5));

Long seconds = redis.getExpire(
        key, TimeUnit.SECONDS);

assertNotNull(seconds);
assertTrue(seconds > 0);
```

Đoạn trên là snippet. Nếu hợp đồng thật sự yêu cầu key biến mất sau TTL, dùng bounded eventual assertion/Awaitility hoặc test hệ thống cho expiry, **không viết `Thread.sleep(500)` và giả định server đã xóa ngay khi dừng ngủ**.

## 9. `SCAN` và `KEYS`: hiểu đúng phạm vi

`StringRedisTemplate.keys(pattern)` gửi lệnh Redis **`KEYS`**; với keyspace lớn nó có thể tốn thời gian và làm nghẽn server. Spring Data Redis khuyến cáo xem `scan(ScanOptions)` cho lượng data lớn.

```java
// Snippet: với StringRedisTemplate redis và namespace được cấp riêng.
ScanOptions options = ScanOptions.scanOptions()
        .match(namespace + "*")
        .count(100)
        .build();

try (Cursor<String> cursor = redis.scan(options)) {
    while (cursor.hasNext()) {
        String key = cursor.next();
        // Chỉ xử lý nếu key thuộc đúng namespace test.
    }
}
```

**Lưu ý quan trọng của Redis SCAN:**

- SCAN duyệt keyspace bằng cursor, không phải một snapshot atomic.
- Khi keyspace thay đổi đồng thời, có thể thấy key lặp hoặc bỏ sót một phần key.
- `COUNT` là hint cho server, không bảo đảm số kết quả chính xác ở mỗi lượt.
- Dùng `try-with-resources` để close cursor.
- Nếu cần cleanup **đảm bảo** trong một môi trường đang bị nhiều writers thay đổi, namespace phải tách biệt hoặc cần chặn writers/đợi job hoàn tất trước teardown.
- Trong Redis Cluster, scan toàn cluster có thể cần xử lý theo node/client API phù hợp; không giả định một SCAN đơn lẻ bao mọi key của cluster.

**Không bao giờ áp `SCAN match("*")` rồi xóa toàn bộ key trên instance chia sẻ.** Nếu không nắm rõ ownership, dừng cleanup và cô lập môi trường trước.

## 10. MongoDB Testcontainers: database dành riêng cho test

Testcontainers khởi động MongoDB trong Docker container, tránh phụ thuộc local MongoDB đã có dữ liệu từ lần chạy trước. Dùng:

```java
@Container
static final MongoDBContainer MONGO =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"));
```

và:

```java
@DynamicPropertySource
static void mongoProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.mongodb.uri",
            () -> MONGO.getReplicaSetUrl(DATABASE));
}
```

Đây là snippets; project runnable có toàn bộ class ở mục 18. `@DynamicPropertySource` inject host/port động vào Spring Environment. `getReplicaSetUrl(DATABASE)` trỏ URI MongoDB vào database test xác định; Testcontainers quản lý cổng và container lifecycle.

Chọn database name theo test run/class giúp giảm va chạm nếu cùng một MongoDB instance được tái sử dụng bởi nhiều lớp:

```java
private static final String DATABASE =
        "it_" + UUID.randomUUID().toString().replace("-", "");
```

Trên **container mới riêng của test class**, UUID là lớp bảo vệ bổ sung. Nếu cho phép Testcontainers reuse hoặc chạy nhiều suites chung container, càng cần namespace/database tách biệt và phải hiểu lifecycle/cache.

### 10.1. Không chỉ dùng random ID cho document

Random document ID tránh trùng primary key nhưng **không ngăn data contamination** nếu test query `findAll()`, count hoặc aggregate toàn collection. Vì vậy random ID cần đi cùng database/collection riêng hoặc query filter theo runId.

## 11. Redis Testcontainers: port động và namespace riêng

Redis container có thể dùng GenericContainer:

```java
@Container
static final GenericContainer<?> REDIS =
        new GenericContainer<>(
                DockerImageName.parse("redis:7.4-alpine"))
                .withExposedPorts(6379);
```

Property cho Spring Boot 3.5:

```java
@DynamicPropertySource
static void redisProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.redis.host", REDIS::getHost);
    registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
}
```

Không hard-code `localhost:6379`. Testcontainers có thể expose Redis trên host/port khác, đặc biệt khi CI/Docker remote. Nếu Redis production có TLS/password/ACL, một plain test Redis không tự kiểm những cấu hình bảo mật đó; thêm transport/security tests theo rủi ro.

**Chọn test data keys:** Trong class test, tạo namespace bằng UUID và lưu key vào `ownedKeys` trước khi ghi. Sau mỗi method, gọi `redis.delete(ownedKeys)`. Cách này không cần lệnh `KEYS` hay `FLUSHDB`.

## 12. Spring Boot test slices và giới hạn

Trong Spring Boot 3.5 có các annotation phù hợp:

| Test | Thành phần chính được nạp | Không chứng minh điều gì? |
|---|---|---|
| `@DataMongoTest` | Mongo mapping/template/repositories và Mongo-related auto-config | Không tự kiểm full business service, Redis, HTTP controller |
| `@DataRedisTest` | Redis connection/template/repositories theo slice | Không tự kiểm Mongo, HTTP, toàn bộ service wiring |
| `@DataElasticsearchTest` | Elasticsearch-related components cho slice | Không tự kiểm gateway/Elastic Cloud network bên ngoài |
| `@SpringBootTest` | Application context đầy đủ theo config test | Không tự biến remote dependencies thành production |
| Test đơn thuần không Spring | Pure cleanup policy/namespace helper | Không chạy real backend |

Trong project runnable, **Mongo test và Redis test là hai class khác nhau**, mỗi class khởi động **một container** tương ứng. Nhờ vậy, một test về unique index của Mongo không cần Redis server, và một test TTL của Redis không cần Mongo.

Nếu cần kiểm use case có **cả Mongo và Redis thật** (chẳng hạn ghi document rồi invalidate cache), dùng `@SpringBootTest` với cả hai containers và kiểm thứ tự side effects. **Hai slice tests xanh không tự chứng minh cross-store consistency**.

## 13. Đừng nhầm context cache với data reset

Spring TestContext cache `ApplicationContext` để giảm thời gian boot. Nó **không tự reset**:

- MongoDB documents/indexes.
- Redis keyspace hoặc TTL còn lại.
- Elasticsearch indices/aliases.
- Object storage objects.
- Singleton local caches/queues không được cleanup.
- Background jobs đang tiếp tục ghi.

`@DirtiesContext` có thể khiến Spring đóng context và dựng lại, nhưng **không đảm bảo xóa data external** và có chi phí lớn. Đừng gắn `@DirtiesContext` cho mọi method chỉ để che data contamination.

Lý tưởng: test có namespace riêng, `@BeforeEach` xác minh tiền điều kiện, `@AfterEach` dọn owned data và chỉ dùng `@DirtiesContext` khi **chính context state** bị thay đổi không thể reset an toàn.

## 14. Lifecycle của index: MongoDB và Elasticsearch khác nhau

### 14.1. MongoDB index nằm trong collection

`dropCollection` làm mất indexes của collection. Nếu test cần kiểm uniqueness, recreate index trước. `remove` không xóa indexes. Một số index options như partial filter, sparse, TTL, collation không thể kiểm chỉ bằng tên index; cần xem metadata và behavior.

### 14.2. Elasticsearch index là resource dữ liệu

Trong Elasticsearch/OpenSearch:

- **Index** chứa documents, mappings và settings; xóa index là xóa cả resource đó.
- **Alias** có thể trỏ đến một hoặc nhiều indexes, nên xóa một index không đồng nghĩa xóa tên alias theo thiết kế ứng dụng.
- **Index templates** có thể áp dụng khi tạo index; test phải nạp template/mapping phù hợp.
- **Refresh** ảnh hưởng khi document xuất hiện trong search; một write acknowledged chưa chắc thấy ngay ở search query.
- **Delete by query** có thể chạy bất đồng bộ, có race với writers và cần xử lý failures/refresh.
- **ILM/lifecycle policy** và rollover có thể tạo tên index mới; cleanup bằng một tên cố định dễ bỏ sót.

**Pattern test:** tạo index có tên duy nhất, ví dụ `it-order-search-<run-id>`, configure mapping, write fixture, refresh/wait theo contract, assert search, rồi xóa **đúng index do run tạo**. Không xóa `orders-*` trên shared cluster.

### 14.3. Không test search bằng Mongo rules

Mongo `IndexOperations.ensureIndex(...)` không tự áp dụng cho Elasticsearch. Search client, index creation/deletion, refresh và mapping semantics khác. Với engine-specific bugs, dùng Testcontainers Elasticsearch/OpenSearch phù hợp hoặc test cluster sandbox riêng; không biến ví dụ thành API calls giả.

## 15. Các nguyên tắc cleanup ngoài Mongo/Redis

### 15.1. Object storage (S3/MinIO/GCS)

Tạo object keys dưới prefix:

```text
it/<suite>/<run-id>/profile/avatar.png
it/<suite>/<run-id>/report/result.json
```

Sau test, xóa đúng objects thuộc prefix đã cấp, kiểm object không còn theo semantics của backend. Với **versioning**, thao tác delete object có thể chỉ tạo delete marker, các versions cũ vẫn tiêu thụ storage; cần lifecycle/cleanup version-aware trong **test bucket riêng**. Không dùng bucket production chỉ vì có prefix.

### 15.2. Cassandra

Không nên truncate keyspace/table dùng chung, nhất là khi có test song song. Dùng keyspace test riêng hoặc partition key chứa run ID, cleanup theo partition trong môi trường test. Tombstones và compaction có nghĩa việc “xóa” khác với thu hồi vật lý ngay lập tức.

### 15.3. Neo4j

Nếu mỗi test tạo subgraph riêng, gắn `testRunId` vào nodes, chỉ xóa nodes/relationships có owner. `MATCH (n) DETACH DELETE n` không điều kiện có thể phá graph khác nếu chạy trên database dùng chung.

### 15.4. In-memory cache và Spring Cache

`@Cacheable` có thể dùng Caffeine/ConcurrentMap, Redis hoặc nhà cung cấp khác. `CacheManager.getCache("x").clear()` chỉ dọn cache tương ứng của context — nếu backend là Redis shared cache, có thể ảnh hưởng keys của các test khác. Dùng key scope/namespace và test-specific CacheManager khi có thể.

### 15.5. Search index name và alias migration

Khi test versioned aliases, tạo alias riêng cho run, đổi alias trỏ index mới, assert old/new documents theo contract, rồi cleanup alias và tất cả indexes run tạo. Không nhầm alias removal với document deletion.

## 16. Project runnable: bộ file và ranh giới

Ta xây project Spring Boot tối thiểu với một document `Profile` và các Redis keys do test quản lý.

```text
nosql-cleanup-demo/
  build.gradle
  settings.gradle
  src/main/java/com/example/nosqlcleanup/
    NoSqlCleanupApplication.java
    Profile.java
  src/test/java/com/example/nosqlcleanup/
    ProfileMongoCleanupTest.java
    RedisKeyCleanupTest.java
```

**Các giả định:**

- Java 17+ và Spring Boot **3.5.x**.
- Docker daemon hoạt động và Testcontainers có quyền pull `mongo:7.0` và `redis:7.4-alpine`.
- Tests dùng containers **riêng**; không cần Mongo/Redis đã cài trên host.
- Maven/Gradle đã truy cập được Central hoặc registry nội bộ phù hợp.
- Không dùng profile hay environment variables trỏ tới database production.

Ví dụ đặt **Spring Boot 3.5.16** trong `build.gradle`. Nếu dự án bị khóa ở một phiên bản 3.5.x khác, giữ cùng API phù hợp với version đã kiểm; không đổi plugin version chỉ vì muốn chạy ví dụ.

## 17. Gradle project và application code

**`settings.gradle`**

```groovy
rootProject.name = 'nosql-cleanup-demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:mongodb'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot BOM quản lý những Testcontainers artifacts thông dụng trong nhánh 3.5. Nếu project đã dùng BOM khác hoặc công ty khóa versions, kiểm dependency resolution trước khi chạy. Không cấu hình Testcontainers reuse trên shared CI mà không có isolation policy.

**`src/main/java/com/example/nosqlcleanup/NoSqlCleanupApplication.java`**

```java
package com.example.nosqlcleanup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NoSqlCleanupApplication {

    public static void main(String[] args) {
        SpringApplication.run(NoSqlCleanupApplication.class, args);
    }
}
```

**`src/main/java/com/example/nosqlcleanup/Profile.java`**

```java
package com.example.nosqlcleanup;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "profiles")
public class Profile {

    @Id
    private String id;
    private String email;
    private String displayName;

    public Profile() {
    }

    public Profile(
            String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Đây là entity đơn giản cho MongoDB. `@Id` ánh xạ đến `_id`; tên collection là `profiles`. Email được dùng để minh họa **unique index**, không phải thiết kế dữ liệu người dùng thực. Dùng địa chỉ `.test` trong fixture, không đưa email thật/PII vào CI logs.

## 18. MongoDB integration tests: drop, recreate, ensure index

**`src/test/java/com/example/nosqlcleanup/ProfileMongoCleanupTest.java`**

```java
package com.example.nosqlcleanup;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexInfo;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataMongoTest
class ProfileMongoCleanupTest {

    private static final String DATABASE = "it_"
            + UUID.randomUUID().toString().replace("-", "");

    @Container
    static final MongoDBContainer MONGO =
            new MongoDBContainer(
                    DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri",
                () -> MONGO.getReplicaSetUrl(DATABASE));
    }

    @Autowired
    MongoTemplate mongo;

    @BeforeEach
    void resetCollectionAndRequiredIndex() {
        // Chỉ collection trong database Testcontainer của class.
        mongo.dropCollection(Profile.class);
        mongo.createCollection(Profile.class);

        mongo.indexOps(Profile.class).ensureIndex(
                new Index()
                        .on("email", Sort.Direction.ASC)
                        .unique());

        assertEquals(0L, mongo.count(new Query(), Profile.class));
    }

    @AfterEach
    void dropOnlyOwnedCollection() {
        mongo.dropCollection(Profile.class);
        assertFalse(mongo.collectionExists(Profile.class));
    }

    @Test
    void startsWithNoStaleDocuments() {
        assertEquals(0L, mongo.count(new Query(), Profile.class));

        mongo.insert(new Profile(
                "p-1", "one@example.test", "An"));

        assertEquals(1L, mongo.count(new Query(), Profile.class));
        assertEquals("An",
                mongo.findById("p-1", Profile.class)
                        .getDisplayName());
    }

    @Test
    void uniqueIndexIsPresentAfterEveryReset() {
        List<IndexInfo> indexes =
                mongo.indexOps(Profile.class).getIndexInfo();

        assertTrue(indexes.stream().anyMatch(index ->
                index.isUnique()
                && index.isIndexForFields(List.of("email"))));

        mongo.insert(new Profile(
                "p-2", "same@example.test", "Mai"));

        assertThrows(DuplicateKeyException.class, () ->
                mongo.insert(new Profile(
                        "p-3", "same@example.test", "Minh")));
    }

    @Test
    void deletingDocumentsKeepsIndexMetadata() {
        mongo.insert(new Profile(
                "p-4", "four@example.test", "Lan"));

        mongo.remove(new Query(), Profile.class);

        assertEquals(0L, mongo.count(new Query(), Profile.class));

        List<IndexInfo> indexes =
                mongo.indexOps(Profile.class).getIndexInfo();

        assertTrue(indexes.stream().anyMatch(index ->
                index.isUnique()
                && index.isIndexForFields(List.of("email"))));
    }
}
```

### 18.1. Vì sao test này đáng tin hơn “save rồi findAll”?

- Test luôn vào `@BeforeEach` với collection được reset trong **database test class sở hữu**.
- Unique index được **ensure sau reset**, nên test vẫn bảo vệ constraint.
- Test kiểm document count, email uniqueness và sự khác nhau giữa `remove`/`dropCollection`.
- `@AfterEach` xóa collection và assert nó biến mất; cleanup lỗi làm test fail.
- Database name chứa UUID nên hai test runs có rủi ro thấp hơn khi cùng dùng container/backend.
- Không dựa vào thứ tự chạy của ba `@Test`, không gắn `@TestMethodOrder` để che contamination.

### 18.2. Những giới hạn của Mongo demo

- Test không dùng Mongo transaction hoặc session, nên không chứng minh multi-document transaction.
- Không dùng TTL index/partial index, chỉ unique index.
- Không chạy trên Mongo Atlas service thật, sharded cluster hay môi trường có auth/TLS.
- Container là external MongoDB instance nhỏ do Testcontainers quản lý; không có hạ tầng production.
- `@DataMongoTest` không kiểm full Spring Boot business service/HTTP mapping.
- Trong cùng class, nếu dự án bật JUnit **parallel methods** và cùng database/collection, một method có thể drop collection của method khác. Ví dụ được thiết kế cho **method execution tuần tự**. Để chạy parallel, dùng database/collection namespace **theo method**, hoặc tắt song song cho nhóm test này.

## 19. Redis integration tests: namespace + owned keys + TTL

**`src/test/java/com/example/nosqlcleanup/RedisKeyCleanupTest.java`**

```java
package com.example.nosqlcleanup;

import java.time.Duration;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.redis.DataRedisTest;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataRedisTest
class RedisKeyCleanupTest {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(REDIS_PORT);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
                () -> REDIS.getMappedPort(REDIS_PORT));
    }

    @Autowired
    StringRedisTemplate redis;

    // JUnit Jupiter mặc định tạo một instance test class mỗi method.
    private final String namespace =
            "it:cleanup:" + UUID.randomUUID() + ":";

    private final Set<String> ownedKeys = new HashSet<>();

    private String ownedKey(String suffix) {
        String key = namespace + suffix;
        ownedKeys.add(key);
        return key;
    }

    @AfterEach
    void deleteOnlyKeysCreatedByThisTest() {
        if (!ownedKeys.isEmpty()) {
            redis.delete(ownedKeys);
        }
        for (String key : ownedKeys) {
            assertFalse(Boolean.TRUE.equals(redis.hasKey(key)));
        }
    }

    @Test
    void stringKeyIsReadableAndOwnedByTest() {
        String key = ownedKey("profile:p-1");

        redis.opsForValue().set(key, "An");

        assertEquals("An", redis.opsForValue().get(key));
        assertTrue(Boolean.TRUE.equals(redis.hasKey(key)));
    }

    @Test
    void hashKeyIsAlsoCleanedUpBySameOwnershipList() {
        String key = ownedKey("profile:p-2");

        redis.opsForHash().put(key, "name", "Mai");
        redis.opsForHash().put(key, "role", "reader");

        assertEquals("Mai",
                redis.opsForHash().get(key, "name"));
        assertEquals("reader",
                redis.opsForHash().get(key, "role"));
    }

    @Test
    void ttlIsCheckedWithoutSleeping() {
        String key = ownedKey("session:p-3");

        redis.opsForValue().set(
                key, "active", Duration.ofMinutes(5));

        Long ttlSeconds = redis.getExpire(
                key, TimeUnit.SECONDS);

        assertNotNull(ttlSeconds);
        assertTrue(ttlSeconds > 0L);
        assertEquals("active", redis.opsForValue().get(key));
    }

    @Test
    void scanCanFindOnlyCurrentTestNamespace() {
        String keyA = ownedKey("product:BOOK");
        String keyB = ownedKey("product:PEN");

        redis.opsForValue().set(keyA, "available");
        redis.opsForValue().set(keyB, "available");

        ScanOptions options = ScanOptions.scanOptions()
                .match(namespace + "*")
                .count(100)
                .build();

        Set<String> seen = new HashSet<>();
        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext()) {
                seen.add(cursor.next());
            }
        }

        assertTrue(seen.contains(keyA));
        assertTrue(seen.contains(keyB));
        assertTrue(seen.stream()
                .allMatch(key -> key.startsWith(namespace)));
    }
}
```

### 19.1. Vì sao cleanup dùng `ownedKeys`?

- Test biết chính xác keys do nó tạo.
- Một Hash và một String đều nằm dưới **cùng key namespace**, `redis.delete(key)` dọn được cả hai.
- Không phải duyệt toàn Redis keyspace.
- Không cần `FLUSHDB` hay `FLUSHALL`, tránh xóa session/cache của test khác.
- Key được đăng ký **trước khi write**, nên nếu lệnh ghi xảy ra rồi test ném exception, `@AfterEach` vẫn biết key phải xóa.
- Sau cleanup, test kiểm lại `hasKey(...)`. Điều này cũng giúp phát hiện Redis connection bị lỗi lúc teardown.

### 19.2. Trường hợp không thể theo dõi từng key

Nếu một background job tạo keys mới theo namespace, chỉ dùng danh sách `ownedKeys` là chưa đủ. Trong **container/dedicated Redis test instance**, có thể scan `it:cleanup:<runId>:*` và xóa những keys phát hiện được. Cần dừng job/writers trước cleanup và hiểu SCAN không đảm bảo snapshot. Không sử dụng thuật toán ấy trên namespace shared mà team khác cũng dùng.

### 19.3. Test Redis chưa bảo vệ điều gì?

- TTL **thực sự hết hạn sau chính xác năm phút**; test chỉ bảo vệ TTL được đặt.
- Redis Cluster, Sentinel, replication, failover, eviction policy hoặc memory pressure.
- Spring Cache annotation/proxy key generator của business service.
- Redis transactions/Lua scripting hoặc concurrency giữa nhiều clients.
- Real authentication/TLS/ACL production.

Khi các yếu tố này là rủi ro quan trọng, phải có adapter/configuration tests chuyên biệt và môi trường kiểm soát được.

## 20. Chạy bộ ví dụ và giải thích kết quả

Với Docker chạy được và Gradle wrapper có trong project:

```bash
./gradlew test --tests com.example.nosqlcleanup.ProfileMongoCleanupTest --tests com.example.nosqlcleanup.RedisKeyCleanupTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.nosqlcleanup.ProfileMongoCleanupTest --tests com.example.nosqlcleanup.RedisKeyCleanupTest
```

Nếu bạn mới tạo project chưa có Gradle wrapper, sinh wrapper bằng Gradle của môi trường development hoặc IDE rồi commit wrapper theo chính sách dự án. Trong multi-module build, dùng đúng task `:your-module:test`.

**Số test methods dự kiến:**

| Lớp | Test count | Điều quan sát |
|---|---:|---|
| `ProfileMongoCleanupTest` | 3 | Clean collection, unique index, remove vs drop |
| `RedisKeyCleanupTest` | 4 | String key, Hash key, TTL, prefix SCAN |
| **Tổng** | **7** | Mongo và Redis test slices độc lập |

Nếu Docker, images, network permissions, dependencies và source đúng ví dụ, các test dự kiến pass và Gradle báo `BUILD SUCCESSFUL`. **Đây là kết quả dự kiến qua rà soát mã và API**, không phải tuyên bố đã chạy Docker/Gradle trong repository hiện tại.

Không có stdout nghiệp vụ cố định. Mongo/Redis container IDs, host ports và startup logs có thể thay đổi mỗi run. Report JUnit thông thường ở `build/reports/tests/test/index.html` và XML ở `build/test-results/test/`.

### 20.1. Vì sao không dùng `@Transactional` rollback như JDBC?

MongoDB và Redis không tự tham gia chung một Spring JDBC transaction. Mongo có transaction riêng khi replica set/session và transaction manager được cấu hình; Redis có MULTI/EXEC semantics và nhiều API không tự enlist vào transaction Spring như JDBC. **Không gắn `@Transactional` trên test rồi giả định Mongo document và Redis key đều rollback cùng nhau.**

Ở ví dụ này, cleanup **tường minh** là hợp đồng. Với một use case ghi cả Mongo và Redis, phải thiết kế consistency/failure recovery và test từng boundary.

## 21. Cleanup theo key vs cleanup theo pattern

So sánh:

| Lựa chọn | Độ an toàn | Khi nào hợp lý |
|---|---|---|
| `redis.delete("it:run:test:key")` | Cao nếu key thuộc test | Một key cụ thể |
| `redis.delete(ownedKeys)` | Cao nếu tracked đầy đủ | Một test tạo nhiều key |
| `SCAN match("it:run:*")` rồi xóa | Tương đối khi namespace độc quyền | Backend job tạo keys khó dự đoán |
| `KEYS "it:run:*"` rồi xóa | Có thể blocking theo keyspace | Chỉ dành cho Redis nhỏ, isolated; không ưu tiên |
| `FLUSHDB` | Rất nguy hiểm với shared DB | Chỉ Redis instance độc quyền |
| `FLUSHALL` | Rất nguy hiểm với shared instance | Hầu như không cần cho method tests |

Một namespace phải **không va chạm**. Prefix `test:*` không an toàn nếu nhiều builds dùng chung Redis. Prefix gồm `runId`/`testId` và được sinh trước test giúp tránh trường hợp build A xóa keys của build B.

Nếu cleanup theo prefix có thể match các ký tự pattern Redis đặc biệt (như `*`, `?`), không tạo namespace trực tiếp từ input chưa sanitize; dùng ký tự ASCII alphanumeric/hyphen/UUID an toàn.

## 22. Cleanup và parallel test execution

JUnit 5 có thể chạy test parallel khi được bật. Khi đó:

- Hai Mongo methods dùng chung database/collection và cùng `dropCollection` có race.
- Hai Redis methods dùng keys riêng có thể chạy đồng thời an toàn hơn, nhưng test class instance lifecycle và client thread-safety phải đúng.
- Một Elasticsearch index alias được test A cập nhật có thể đổi kết quả test B.
- Spring context cache dùng cùng singleton Mongo/Redis client không tạo isolation data.
- Tạo container per class không tự tách **các methods trong class** nếu chúng dùng chung collection.

**Bốn cách xử lý:**

1. Tắt parallel cho test class dùng cùng collection.
2. Tạo **per-method collection name** và dùng `MongoTemplate` theo collection name có owner.
3. Tạo **per-method database** hoặc container khi chi phí chấp nhận được.
4. Đặt parallel tests vào resource lock trên tài nguyên có shared state.

Với JUnit Jupiter có thể dùng:

```java
// Snippet minh họa: gắn trên class dùng chung một collection.
@Execution(ExecutionMode.SAME_THREAD)
class SequentialMongoTests {
    // ...
}
```

Cần imports `org.junit.jupiter.api.parallel.Execution` và `ExecutionMode`. Đây không phải file trong ví dụ runnable; khi repo bật parallel class/method, hãy áp policy/test isolation rõ ràng. **Không dựa vào thứ tự chạy để che lỗi.**

## 23. MongoDB index tự động: bẫy sau drop/recreate

Nếu domain model có:

```java
// Snippet bên trong @Document class.
@Indexed(unique = true)
private String email;
```

không được suy luận rằng sau `mongo.dropCollection(Profile.class)`, unique index sẽ lập tức được tạo lại. Index creation có lifecycle và việc auto-index-create có thể bị tắt theo mặc định. Khi test cần index:

- Chạy **index migration/setup thật** của ứng dụng, hoặc
- `ensureIndex(...)` tường minh sau reset.
- Assert index metadata và duplicate insert behavior.
- Giữ mọi thao tác trong database test.

**Một lỗi thường gặp:** test bắt `DuplicateKeyException` ở lần chạy đầu (index có từ bootstrap), rồi sau khi một test khác drop collection, test duplicate chạy lại và không ném exception vì index đã biến mất. Nếu fix bằng cách “bỏ assertion” thì bạn đã xóa lớp bảo vệ integrity. Fix đúng là **tái tạo index một cách xác định** hoặc thay chiến lược cleanup từ drop sang remove.

## 24. Elasticsearch search: eventual visibility và index cleanup

Search engines gần real-time không giống Mongo CRUD.

Một test làm:

```text
PUT document -> HTTP acknowledged
GET/search ngay -> có thể chưa thấy document trong search
DELETE document -> search ngay -> có thể vẫn thấy
```

có thể flaky vì refresh cycle. Phương án:

- Dùng **refresh policy thích hợp cho test**, hoặc gọi refresh API trên **test index** sau write/delete khi contract yêu cầu query ngay.
- Nếu hệ thống real-world có eventual consistency, dùng eventual assertion có timeout rõ ràng thay vì ép strong consistency giả.
- Mỗi test/run dùng index name riêng; cleanup alias và index **đúng owner**.
- Không dùng `Thread.sleep(1000)` làm giải pháp mặc định; thời gian refresh có thể thay theo tải và CI.
- Nếu API test gọi asynchronous indexing pipeline, phải chờ job hoàn thành theo điều kiện trước cleanup; nếu job còn chạy, nó có thể tạo lại dữ liệu sau khi test đã xóa.

**Index metadata cũng là fixture.** Nếu expected search cần analyzer/custom mapping, chỉ xóa documents mà giữ mapping cũ có thể làm test không đại diện migration mới. Nếu test schema migration, tạo index mới với mapping từ version cần kiểm.

## 25. TTL, cache expiration và thời gian ảo

Redis `EXPIRE` và Mongo TTL index không có semantics “xóa chính xác vào thời điểm đồng hồ của JUnit”.

- Redis có active/passive expiration; key có thể biến mất khi truy cập hoặc do background expiration cycle.
- Mongo TTL monitor hoạt động theo chu kỳ, nên tài liệu không hứa document bị xóa ngay sau khi timestamp hết hạn.
- Caffeine/local cache dùng clock và eviction policies riêng.
- Elasticsearch ILM có lifecycle delays.

**Để test TTL đúng:**

1. Test rằng TTL/expires-at **được cấu hình** đúng ngay sau write.
2. Nếu cần test actual expiry, dùng timeout có biên và observe đến khi key/document biến mất, không đòi đúng mili-giây.
3. Nếu logic domain dựa vào clock, inject `Clock.fixed` và unit test không cần chờ thời gian thật.
4. Không đồng nhất **logic expire** của token trong domain với cleanup vật lý của backend: có thể token hết hạn về nghiệp vụ trước khi key được xóa.

Giải pháp tốt nhất thường là **unit tests cho thời gian logic**, **ít integration tests cho TTL thực** và cleanup tường minh ở cuối để không phụ thuộc expiration.

## 26. Điều gì xảy ra khi cleanup thất bại giữa chừng?

Giả sử một test tạo ba tài nguyên:

```text
Mongo profile document
Redis cache key
Elasticsearch search document
```

Nếu teardown xóa Mongo trước và Mongo connection lỗi, code không nên dừng ngay rồi bỏ Redis/Elasticsearch mà không báo. Có thể dùng separate cleanup actions, gom lỗi bằng JUnit extensions/finally và **propagate failure** sau khi đã thử dọn các tài nguyên còn lại.

Pseudo-code ở mức ý tưởng:

```text
cleanupFailures = []

try deleteMongoOwnedData
catch error: collect error

try deleteRedisOwnedKeys
catch error: collect error

try deleteSearchOwnedIndex
catch error: collect error

if cleanupFailures not empty:
    fail test run with all cleanup errors
```

**Đây là pseudo-code**, không phải Java/Gradle runnable. Khi viết implementation, dùng exception aggregation đúng, không ném mất lỗi đầu tiên; không xóa rộng vì không biết tài nguyên thuộc ai.

Nếu test fails và cleanup cũng fails, báo cả **test failure** và **teardown failure**. Xóa những dữ liệu cần debug chỉ nên thực hiện theo policy bảo mật và thời hạn lưu giữ, không vì thuận tiện mà để tài nguyên chứa PII tồn tại vô hạn.

## 27. Quản lý dữ liệu theo test run và CI

Trên CI, có thể tạo run ID:

```text
build-20261108-17823
```

Nó phải tránh collision giữa branches/reruns. Nếu lấy CI job identifier từ environment, kiểm input và sanitize để phù hợp quy tắc đặt tên database/index/bucket/key. Không đưa secrets vào tên resource.

Một inventory đơn giản:

| Field | Ví dụ |
|---|---|
| Owner | CI job hoặc local developer test profile |
| Run ID | `it-17823-a42b` |
| Backend | Mongo/Redis/Elasticsearch |
| Resource | database, collection, key prefix, index alias |
| Created at | timestamp cho vận hành cleanup |
| TTL | thời hạn tồn tại nếu job chết |
| Cleanup strategy | afterEach/afterAll/container disposal/janitor |
| Safety guard | xác nhận host/test environment, whitelist prefix |

Đối với ephemeral Testcontainers, runtime/container lifecycle đã là lớp bảo vệ mạnh. Với staging shared, cần cơ chế janitor riêng chỉ có quyền xóa test resources; không cấp quyền delete toàn bộ production.

## 28. Test fixture data phải đáng tin

Một lỗi không liên quan trực tiếp cleanup nhưng dễ bị quy kết cho nó: fixture được tạo từ dữ liệu thật không ổn định.

**Nên:**

- Dùng ID/email giả, không trùng giữa runs.
- Khởi tạo fixtures trong setup từ một factory/builder rõ ràng.
- Assert count và IDs theo scope của test, không assert toàn database luôn chỉ có một document khi có test khác.
- Chỉ query data của test bằng run ID/tenant ID khi backend dùng chung.
- Dùng index/mapping/schema thực sự cần thiết để test query.
- Tách fixture “normal”, “duplicate”, “expired”, “invalid” có tên rõ.
- Giữ seed data deterministic khi test không kiểm randomness.

**Tránh:**

- Hard-code document ID mà tất cả parallel tests cùng dùng.
- Viết test theo thứ tự `testCreate` rồi `testUpdate` rồi `testDelete`.
- Dùng TTL để trông chờ dữ liệu trước test tự hết hạn.
- So count toàn collection không được cô lập.
- Reset indexes không có kế hoạch recreate.
- Auto-update fixture bằng dữ liệu hiện tại mỗi lần test chạy.

## 29. Bộ lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
|---|---|---|
| Local pass, CI fail theo thứ tự | Data còn lại từ test khác | Isolate namespace, setup/teardown |
| Mongo duplicate không bị từ chối | Index bị drop hoặc chưa ensure | Recreate unique index và assert metadata |
| Mongo query trả thêm document | Collection có fixture cũ | Per-test DB/collection hoặc scoped delete |
| Redis test cache hit ngoài dự kiến | Key name tái sử dụng, TTL còn | Run-specific key, tracked cleanup |
| Redis test không dọn được key | Connection fail hoặc ownedKeys thiếu | Báo teardown error, track key trước write |
| Redis `KEYS` làm suite chậm | Quét toàn keyspace | Dùng targeted keys hoặc SCAN |
| `FLUSHDB` phá dữ liệu môi trường khác | Shared Redis logical DB | Chỉ dedicated instance, tránh broad commands |
| Search không thấy record vừa ghi | Refresh chưa xảy ra | Test refresh policy/eventual assertion |
| Elasticsearch mapping sai sau test khác | Shared index và mappings cũ | Unique index + recreate mapping |
| Object storage “đã xóa” nhưng còn versions | Versioning/delete markers | Version-aware cleanup/test bucket |
| Test chưa hết hạn TTL mà vẫn PASS | Chỉ assert TTL được set, không kiểm expiry | Bổ sung riêng eventual expiry test nếu contract cần |
| Context cache mới nhưng data còn | External DB/cache không phụ thuộc Spring context | Cleanup external state, không lạm dụng `@DirtiesContext` |
| Test xóa data của test đang chạy | Shared collection/prefix, parallel tests | Namespace per method/resource locks |
| Docker không sẵn, Testcontainers fail | CI không có daemon/socket/image access | Cấu hình runtime Docker và quyền pull images |
| Cleanup chạy nhầm cluster | Property/environment override sai | Dynamic properties + test-only credentials + guards |
| Mongo `dropCollection` chạy nhưng index chưa có | Auto-index không tự tái tạo | `ensureIndex` sau mỗi reset |
| Test error che cleanup error | Teardown chỉ log rồi ignore | Aggregate/propagate cleanup failures |

## 30. Bài tập thực hành

### Bài A — Mongo collection và unique index

Test A gọi `dropCollection(Profile.class)`, sau đó insert hai users cùng email nhưng ID khác nhau đều thành công. Trước đó duplicate từng ném `DuplicateKeyException`. Cần sửa nơi nào? Phân biệt `remove(new Query())` và `dropCollection`.

**Đáp án:** Drop collection đã xóa unique index. Nếu chỉ cần dọn documents, dùng remove; nếu cần drop, `createCollection` và `ensureIndex(unique)` trước khi insert.

### Bài B — Redis cache từ test trước

Test B mong cache miss trên `user:41`, nhưng test A vẫn để key ấy trong Redis. Có nên thay cache assertion để chấp nhận hit?

**Đáp án:** Không. Dùng test-specific namespace/key, cleanup sau test và assert tiền điều kiện. Chỉ cho phép hit nếu đó là scenario đang kiểm.

### Bài C — `FLUSHDB` có an toàn không?

Hai CI jobs chia sẻ cùng Redis instance/logical DB. Một test chạy `FLUSHDB` trong `@AfterEach`. Điều gì xảy ra và giải pháp?

**Đáp án:** Nó có thể xóa keys của job kia. Dùng Redis instance riêng hoặc per-job prefix + tracked keys, không flush database dùng chung.

### Bài D — TTL test flaky

Một test đặt TTL một giây, `Thread.sleep(1000)`, rồi assert Redis key không tồn tại. Vì sao flaky?

**Đáp án:** Scheduling, network latency, timer resolution, server expiration processing khác nhau. Dùng bounded eventual assertion và kiểm TTL semantics, không dựa thời gian ngủ cứng.

### Bài E — Elasticsearch index vs Mongo index

Test X xóa Elasticsearch index `it-orders-123`. Test Y xóa Mongo unique index của collection `profiles`. Hai thao tác có cùng hậu quả không?

**Đáp án:** Không. Elasticsearch index chứa documents và mappings; Mongo index là cấu trúc truy vấn/constraint của collection. Phải có kế hoạch recreate và test khác nhau.

### Bài F — Spring context và external data

Team gắn `@DirtiesContext` cho test và nói “mọi Redis key đã được xóa vì Spring context khởi động lại”. Kết luận này đúng không?

**Đáp án:** Không. Context cache/lifecycle không tự dọn external Redis. Phải xóa key/tách namespace/container.

### Bài G — Parallel Mongo tests

Hai JUnit methods cùng database `it_shared` và collection `profiles`; cả hai có `@BeforeEach dropCollection`. Test nào có thể fail?

**Đáp án:** Bất kỳ test nào đang query/insert khi method kia drop. Dùng per-method collection/database hoặc resource lock/SAME_THREAD.

### Bài H — Index fixture là gì?

Unique index `email` phải tồn tại để API từ chối duplicate. Có thể chỉ assert Mongo count trước test bằng 0 và coi tiền điều kiện đủ không?

**Đáp án:** Không. Count 0 không chứng minh index tồn tại. Cần ensure index và kiểm metadata/duplicate behavior.

### Bài I — Cleanup fail nhưng test logic pass

Test insert Mongo và Redis thành công, nhưng `@AfterEach` không kết nối được Redis. Có nên chỉ log warning và báo PASS?

**Đáp án:** Không. Cleanup failure là failure độc lập cần được ghi nhận để tránh làm bẩn lần chạy sau. Cần fail run, có cơ chế janitor/TTL hoặc container disposal.

### Bài J — Chọn cấp test

Bạn muốn kiểm cache invalidation khi Mongo profile đổi. Hai slice tests riêng đã đủ chưa?

**Đáp án:** Chưa. Cần một `@SpringBootTest` hoặc targeted integration test nạp service thật, Mongo/Redis clients thật trong môi trường test và assert update + cache invalidation qua đúng workflow; vẫn giữ slice tests để debug boundary riêng.

## 31. Checklist hoàn thành

- [ ] Backend đang dùng là **test-only**, không phải database/index/bucket production.
- [ ] Có owner/run ID rõ cho mọi resource được tạo.
- [ ] Tôi biết cleanup xóa document hay cả collection/index/mapping.
- [ ] MongoDB `dropCollection` xóa indexes và test recreate indexes cần thiết.
- [ ] Unique/TTL/partial indexes được kiểm bằng metadata và behavior đúng contract.
- [ ] Redis keys dùng namespace tránh collision với test khác.
- [ ] Tôi ưu tiên xóa danh sách key đã tạo, không dùng `FLUSHALL`/`FLUSHDB` bừa bãi.
- [ ] Khi dùng SCAN, tôi hiểu tính không atomic và close cursor.
- [ ] Redis TTL/expiration test không dựa vào sleep tùy tiện.
- [ ] Elasticsearch index, alias, template, refresh được xem là test resources.
- [ ] Object storage versioning và cleanup prefix được xử lý nếu dùng.
- [ ] Testcontainers và `@DynamicPropertySource` cấp đúng host/port động.
- [ ] `@DataMongoTest` và `@DataRedisTest` được dùng khi chỉ cần data slices.
- [ ] Business workflow dùng Mongo + Redis có integration test riêng nếu cần.
- [ ] Mỗi test có tiền điều kiện rõ và cleanup scoped.
- [ ] Cleanup failure làm test run báo lỗi; không nuốt exception.
- [ ] `@DirtiesContext` không được coi là thay thế xóa dữ liệu external.
- [ ] Khi bật parallel tests, database/collection/index/key prefix tách biệt hoặc khóa tài nguyên.
- [ ] Dữ liệu fixture giả, không chứa credentials/PII thực.
- [ ] Test không phụ thuộc thứ tự chạy hay key/index cũ từ CI.
- [ ] Không kết luận H2/JPA transaction rules áp dụng tương tự cho Mongo/Redis.
- [ ] Phần chưa kiểm (TLS, cluster, failover, production mapping) được nêu trung thực.

**Kết luận:** Dọn dữ liệu giữa các test không chỉ là xóa thật nhanh. Với **MongoDB**, cần phân biệt document cleanup với collection/index lifecycle. Với **Redis**, key ownership và namespace quyết định độ an toàn; TTL không thay cleanup, `SCAN` không thay isolation. Với **Elasticsearch/object storage**, index/alias/mapping và object versioning tạo thêm metadata và consistency semantics phải quản lý. Test đáng tin bắt đầu từ tài nguyên riêng, xây fixture/index xác định, kiểm hành vi trên backend phù hợp rồi cleanup đúng owner — và **thất bại rõ ràng khi cleanup không thành công**.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Testing Testcontainers, `@Container`, `@DynamicPropertySource`: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — Test slices (`@DataMongoTest`, `@DataRedisTest`): https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html
- Spring Data MongoDB — Collection and Index Management: https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-collection-management.html
- Spring Data MongoDB — Index Creation Lifecycle: https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html
- Spring Data Redis — `RedisTemplate.scan(ScanOptions)` / `keys(...)`: https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/RedisTemplate.html
- Testcontainers — MongoDB module: https://java.testcontainers.org/modules/databases/mongodb/
- Redis — SCAN semantics: https://redis.io/docs/latest/commands/scan/
- Redis — Key expiration: https://redis.io/docs/latest/commands/expire/
- Elasticsearch — Index management: https://www.elastic.co/guide/en/elasticsearch/reference/current/indices.html
- JUnit Jupiter — Test Instance Lifecycle and Before/After callbacks: https://junit.org/junit5/docs/current/user-guide/
