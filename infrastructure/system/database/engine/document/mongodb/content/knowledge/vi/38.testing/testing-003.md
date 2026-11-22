# Thiết kế fixture nhỏ, xác định và độc lập giữa các lần chạy khi kiểm thử MongoDB

Một bài test MongoDB có thể chạy đúng trên máy của lập trình viên nhưng lỗi khi chạy trên CI, khi đổi thứ tự test, hoặc khi chạy lại sau vài phút. Rất nhiều trường hợp không phải MongoDB hoạt động sai, mà do **fixture** của bài test bị phụ thuộc trạng thái bên ngoài: collection còn documents cũ, ID tự sinh mỗi lần, thời gian thay đổi, test A xóa dữ liệu test B, unique index chưa được tạo, hoặc query không có sort nhưng test lại dựa vào thứ tự kết quả.

**Fixture** là trạng thái đầu vào được thiết lập có chủ ý trước khi thực thi một test. Trong MongoDB, fixture có thể bao gồm documents, collections, indexes, validators, BSON types, một mốc thời gian cố định, và khi cần là topology/permissions của test environment.

Bài học thuộc chương **Kiểm thử**, module **Database Engine Document MongoDB**, tập trung vào ba đặc tính cốt lõi:

1. **Nhỏ (minimal):** chỉ dữ liệu và cấu hình cần để chứng minh hành vi được kiểm tra.
2. **Xác định (deterministic):** cùng đầu vào và điều kiện quan trọng sẽ cho cùng kết quả mong đợi.
3. **Độc lập (isolated/repeatable):** chạy riêng, chạy lại, thay thứ tự hoặc chạy song song không ảnh hưởng nhau.

Ví dụ sử dụng mongosh, MongoDB Java Sync Driver, JUnit 5 và một môi trường MongoDB thử nghiệm. **Không chạy seed/cleanup có khả năng xóa dữ liệu trên production.**

## 1. Fixture khác gì seed data, mock và môi trường test?

| Khái niệm | Vai trò |
| --- | --- |
| Fixture | Trạng thái đã biết của hệ thống trước test |
| Seed script | Cách tạo dữ liệu fixture |
| Factory/builder | Hàm tạo Document/POJO fixture |
| Mock | Đối tượng giả thay dependency |
| Stub | Dependency giả trả dữ liệu định trước |
| Test database | Namespace chứa fixture |
| Test environment | MongoDB server, topology, driver, credentials và phụ thuộc |
| Assertion oracle | Giá trị/kết quả được kỳ vọng, độc lập code đang test |

Một test unit có thể dùng mock repository để kiểm tra một hàm thuần. Nhưng nếu muốn kiểm tra **MongoDB query semantics, unique index, $elemMatch, transaction hoặc TTL**, cần integration test tương ứng với server thật.

### 1.1. Chu trình test

~~~text
Arrange:
  Allocate isolated namespace
  Create required collections, indexes and validators
  Seed minimal documents

Act:
  Call repository/service method

Assert:
  Check exact values, order and persisted invariants

Cleanup:
  Remove only owned resources
  Close sessions, cursors and clients
~~~

### 1.2. Fixture là hợp đồng tiền điều kiện

Mỗi test phải biết _id, field types, indexes và state quan trọng ban đầu. Nếu “trên CI chắc đã có order-test” nhưng không biết ai tạo, test không có tiền điều kiện đáng tin cậy.

## 2. Vì sao fixture phải nhỏ?

Giả sử yêu cầu: chỉ trả **orders PAID của tenant-a**.

Chỉ cần ba documents:

| _id | tenantId | status |
| --- | --- | --- |
| o-001 | tenant-a | PAID |
| o-002 | tenant-a | PENDING |
| o-003 | tenant-b | PAID |

Kết quả mong đợi: chỉ **o-001**.

- Nếu code quên status filter, nó trả thêm o-002.
- Nếu code quên tenant filter, nó trả thêm o-003.
- Nếu code đúng, chỉ o-001 được trả.

### 2.1. Mỗi document có mục đích

Trong một fixture tốt, người đọc trả lời được: “Record này giúp phát hiện bug gì?”. Nếu xóa một record không làm mất khả năng phát hiện bug nào, có thể nó là dữ liệu dư.

### 2.2. Có cả positive và negative controls

Một fixture chỉ có một record hợp lệ thường không bắt được filter thiếu điều kiện. Negative controls giúp phân biệt implementation đúng và implementation quá rộng.

### 2.3. Minimal khác với chỉ có happy path

Tùy test, fixture nhỏ vẫn có thể cần:

- Giá trị vừa dưới/trên ngưỡng.
- Missing field và null field.
- Document thuộc tenant khác.
- Hai records cùng timestamp để kiểm tra tie-breaker.
- Một product không đủ tồn kho.
- Một nested array mà các điều kiện có thể match ở hai elements khác nhau.

### 2.4. Không copy cả production collection

Một triệu documents sẽ làm setup chậm, expected result khó hiểu và tăng rủi ro chứa PII. Dữ liệu representative cho performance/load test là artifact khác với fixture nhỏ cho logic.

## 3. Tính xác định: cố định các yếu tố tác động kết quả

Một bài test có tính xác định khi:

~~~text
Fixture version F
+ input I
+ preconditions P
+ behavior under test B
= expected output O
~~~

Nguồn không xác định thường gặp:

- **new Date()** hoặc **Instant.now()** trong fixture.
- **ObjectId()**, UUID hoặc random ID không được kiểm soát.
- **Random()** không seed.
- **find()** không sort nhưng assert result order.
- TTL monitor chạy bất đồng bộ.
- Change Stream/event consumer nhận chậm.
- Secondary reads có replication lag.
- Parallel writes với kết quả phụ thuộc thread scheduling.
- Shared mutable Java Document/List.
- MongoDB server/driver version tự đổi.
- Time zone/locale mặc định của máy CI.

Không nhất thiết phải loại bỏ concurrency hoặc yếu tố thời gian khỏi mọi test. Quan trọng là **assert đúng contract**: có nơi cần kiểm tra exact value, có nơi cần kiểm tra eventual state trong bounded deadline.

## 4. Tính độc lập giữa các lần chạy

Một test nên pass khi:

1. Chạy một mình.
2. Chạy sau một test khác.
3. Chạy trước một test khác.
4. Chạy hai hoặc nhiều lần liên tiếp.
5. Chạy đồng thời với test khác nếu framework cho phép.
6. Chạy trên CI với một MongoDB test environment sạch.

### 4.1. Test order dependence là lỗi

Anti-pattern:

~~~text
Test A: insert order o-001
Test B: assume o-001 exists
Test C: delete o-001
~~~

Nếu B chạy trước A, nó fail; nếu C chạy trước B, nó fail. Một test không được ủy thác setup của mình cho test khác.

### 4.2. Bài test tự sắp đặt tiền điều kiện

~~~text
Test B:
  @BeforeEach -> insert order o-001
  @Test -> perform read/assert
  @AfterEach -> delete/drop own state
~~~

### 4.3. Shared fixture chỉ hợp lý khi immutable

Có thể chia sẻ factory/config không thay đổi. Shared mutable documents hoặc một collection cho nhiều tests ghi/xóa là nguồn gây flaky tests.

## 5. Ba tầng isolation thực dụng

| Chiến lược | Mô tả | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| Per-document | Mỗi test có unique IDs | Ít overhead | Query rộng hoặc cleanup sai có thể va chạm |
| Per-collection | Mỗi test collection riêng | Tách indexes và documents | Cần tạo/xóa collections |
| Per-database | Mỗi test database riêng | Isolation rõ, setup/teardown dễ | Nhiều namespaces, DDL overhead |
| Per-deployment | Container/cluster riêng | Cô lập server/topology | Khởi động và vận hành tốn hơn |

### 5.1. Lựa chọn mặc định hợp lý

Với integration tests CRUD bằng Java, **per-test database** trên một test server được kiểm soát là một lựa chọn dễ hiểu. Với unit tests không cần MongoDB thật, không cần dựng database.

### 5.2. Namespace ngẫu nhiên nhưng kết quả xác định

Tên database có hậu tố UUID ngẫu nhiên chỉ để bảo đảm isolation là hợp lý nếu tên này **không xuất hiện trong expected business output**. Các documents, timestamps và assertions bên trong vẫn cố định.

### 5.3. Parallel execution

Nếu có hai test cùng dùng _id="o-001", chúng vẫn độc lập khi ở hai databases khác nhau. Nếu cùng collection, cả hai có thể gây duplicate key hoặc cleanup nhầm nhau.

## 6. Fixture orders mẫu

Dùng database lab chuyên biệt:

~~~javascript
use mongo_fixture_lab

db.orders.insertMany([
  {
    _id: "o-001",
    tenantId: "tenant-a",
    externalId: "EXT-001",
    status: "PAID",
    totalMinor: NumberLong(150000),
    createdAt: ISODate("2026-01-15T08:00:00Z")
  },
  {
    _id: "o-002",
    tenantId: "tenant-a",
    externalId: "EXT-002",
    status: "PENDING",
    totalMinor: NumberLong(90000),
    createdAt: ISODate("2026-01-15T09:00:00Z")
  },
  {
    _id: "o-003",
    tenantId: "tenant-b",
    externalId: "EXT-001",
    status: "PAID",
    totalMinor: NumberLong(200000),
    createdAt: ISODate("2026-01-15T10:00:00Z")
  }
]);
~~~

**Chỉ dùng trên database lab trống và được phép ghi.** Trong automation, nên tạo riêng database theo test thay vì seed tất cả vào tên chung mongo_fixture_lab.

### 6.1. IDs cố định

Các _id như o-001 giúp expected outputs đọc được mà không phải truy ngược giá trị ngẫu nhiên.

### 6.2. Timestamps cố định

Tất cả dates dùng UTC ISO-8601, không phụ thuộc ngày hệ thống chạy test.

### 6.3. Total lưu kiểu số nhất quán

NumberLong diễn đạt số nguyên 64-bit. Nếu production dùng Decimal128, fixture/test phải dùng đúng Decimal128.

### 6.4. Tenant-b có mục đích

externalId EXT-001 lặp ở tenant-b nhưng thuộc một tenant khác, giúp kiểm tra uniqueness và query tenant scope.

## 7. Tạo index như một phần fixture

Ví dụ unique business identity trong từng tenant:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, externalId: 1 },
  {
    unique: true,
    name: "uq_tenant_external_id"
  }
);
~~~

### 7.1. Index ảnh hưởng correctness

Nếu test kỳ vọng duplicate key bị chặn mà không tạo index, test không mô phỏng đúng schema. Unique index phải nằm trong setup, không dựa vào việc “CI trước đó đã tạo”.

### 7.2. Tạo index trước seed

Thường giúp phát hiện duplicate fixture ngay khi insert, thay vì đợi tới index build sau seed.

### 7.3. Không tạo mọi index production trong mọi test

Tạo những indexes cần cho behavior/constraint. Với test hiệu năng chuyên biệt, xây cấu hình representative đầy đủ hơn.

### 7.4. Index options cũng quan trọng

Một index có thể là unique/partial/sparse/collation/TTL. Không chỉ nhìn tên index khi test yêu cầu behavior cụ thể.

## 8. Query với exact expected IDs

~~~javascript
db.orders.find(
  {
    tenantId: "tenant-a",
    status: "PAID"
  },
  { _id: 1 }
).sort({ _id: 1 });
~~~

Expected: **["o-001"]**.

### 8.1. Không chỉ assert contains

Nếu test chỉ kiểm tra có o-001, query sai trả o-001, o-002 và o-003 vẫn có thể pass. Nên so toàn bộ set/list kết quả.

### 8.2. Expected oracle độc lập implementation

Nếu repository đang dùng một filter sai và test dùng lại y nguyên filter đó để tính expected, cả hai cùng sai vẫn pass. Expected nên suy trực tiếp từ fixture/requirements.

### 8.3. Tách act khỏi oracle

Trong integration tests repository, Act phải gọi **repository method đang kiểm tra**, không tự gọi lệnh query giống implementation rồi coi đã test repository.

## 9. Java fixture factory đơn giản

~~~java
import org.bson.Document;
import java.time.Instant;
import java.util.Date;
import java.util.List;

public final class OrderFixtures {
    private OrderFixtures() {}

    private static Date date(String iso) {
        return Date.from(Instant.parse(iso));
    }

    public static Document paidTenantA() {
        return new Document("_id", "o-001")
            .append("tenantId", "tenant-a")
            .append("externalId", "EXT-001")
            .append("status", "PAID")
            .append("totalMinor", 150000L)
            .append(
                "createdAt",
                date("2026-01-15T08:00:00Z")
            );
    }

    public static Document pendingTenantA() {
        return new Document("_id", "o-002")
            .append("tenantId", "tenant-a")
            .append("externalId", "EXT-002")
            .append("status", "PENDING")
            .append("totalMinor", 90000L)
            .append(
                "createdAt",
                date("2026-01-15T09:00:00Z")
            );
    }

    public static Document paidTenantB() {
        return new Document("_id", "o-003")
            .append("tenantId", "tenant-b")
            .append("externalId", "EXT-001")
            .append("status", "PAID")
            .append("totalMinor", 200000L)
            .append(
                "createdAt",
                date("2026-01-15T10:00:00Z")
            );
    }

    public static List<Document> defaultOrders() {
        return List.of(
            paidTenantA(),
            pendingTenantA(),
            paidTenantB()
        );
    }
}
~~~

### 9.1. Mỗi lần trả object mới

Không dùng một static Document mutable rồi để nhiều test sửa dùng chung. Factory trả new Document, nested objects/dates cũng nên được tạo mới hoặc deep copy đúng.

### 9.2. Date có thể mutable

Date được tạo trong factory mỗi lần; không chia sẻ một Date instance rồi cho test thay đổi.

### 9.3. Java Long và BSON

150000L hướng tới BSON Int64. Nếu schema yêu cầu Decimal128, dùng đúng codec/type, không thay bằng String.

### 9.4. Factory rõ intent

Tên paidTenantA/pendingTenantA giúp người đọc nhận ra ngay lý do tồn tại của document.

## 10. Builder factory với overrides

Khi nhiều tests cần thay trạng thái:

~~~java
public static Document order(
    String id,
    String tenant,
    String externalId,
    String status,
    long totalMinor
) {
    return new Document("_id", id)
        .append("tenantId", tenant)
        .append("externalId", externalId)
        .append("status", status)
        .append("totalMinor", totalMinor)
        .append(
            "createdAt",
            Date.from(
                Instant.parse("2026-01-15T00:00:00Z")
            )
        );
}
~~~

Ví dụ:

~~~java
Document cancelled = order(
    "o-cancelled",
    "tenant-a",
    "EXT-CANCELLED",
    "CANCELLED",
    120000L
);
~~~

### 10.1. Đừng tạo mega factory

Nếu một hàm có 25 optional arguments/booleans, test trở nên khó hiểu. Nên tạo các factory methods theo intent hoặc một builder nhỏ có defaults rõ.

### 10.2. Explicit values cho trường quan trọng

Nếu đang test status transition, nên ghi status ban đầu ngay trong test thay vì dựa vào default bị ẩn trong factory.

### 10.3. Deep copy khi cần

Document có thể chứa List<Document> và nested Document. Shallow copy có thể chia sẻ nested references; test A sửa phần tử mảng và test B bị ảnh hưởng.

## 11. Không tin thứ tự tự nhiên của find

Một test sai:

~~~java
List<Document> actual = orders.find(
    Filters.eq("tenantId", "tenant-a")
).into(new ArrayList<>());

assertEquals(
    "o-001",
    actual.get(0).getString("_id")
);
~~~

MongoDB không cam kết natural result order như business contract. Hãy sort tường minh:

~~~java
List<Document> actual = orders.find(
    Filters.eq("tenantId", "tenant-a")
).sort(
    Sorts.ascending("_id")
).into(
    new ArrayList<>()
);
~~~

### 11.1. Khi thứ tự không quan trọng

Có thể so sets các IDs, nhưng vẫn kiểm tra số lượng/duplicates nếu yêu cầu.

### 11.2. Khi pagination quan trọng

Nên sort createdAt và thêm _id tie-breaker để thứ tự không mơ hồ khi nhiều timestamps trùng.

### 11.3. Đừng dựa vào index order

Query planner và indexes có thể thay đổi, không biến index scan order thành API guarantee nếu query không sort.

## 12. Cố định thời gian bằng java.time.Clock

Không viết test expected dựa vào Instant.now() trong nhiều nơi:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

Service có thể nhận Clock qua constructor:

~~~java
public final class OrderService {
    private final Clock clock;

    public OrderService(Clock clock) {
        this.clock = clock;
    }

    public Instant currentTime() {
        return clock.instant();
    }
}
~~~

### 12.1. Tại sao injection tốt?

Test assert exact timestamp; production truyền Clock.systemUTC() hoặc dependency phù hợp.

### 12.2. Server-side time khác app time

Clock.fixed **không** điều khiển MongoDB server clock, $currentDate, TTL monitor hoặc timestamps server khác.

### 12.3. Test $currentDate

Nếu behavior phải dùng server time, có thể assert timestamp nằm trong khoảng có kiểm soát và giải thích tolerance, thay vì so với Clock.fixed.

### 12.4. Timezone và locale

Dùng Instant/UTC để biểu diễn thời điểm. Nếu ứng dụng hiển thị theo timezone người dùng, kiểm thử format riêng; không phụ thuộc system default timezone của CI.

## 13. Kiểm soát random và IDs tự sinh

Nếu bắt buộc sinh dữ liệu ngẫu nhiên:

~~~java
import java.util.Random;

Random random = new Random(20260115L);
int quantity = random.nextInt(5) + 1;
~~~

### 13.1. Seed là dữ liệu đầu vào

Lưu seed khi test fail để tái hiện. Với property-based testing, lưu cả case đã được shrink về ví dụ nhỏ nhất.

### 13.2. Random không cần thiết cho mọi fixture

Nếu cần test quantity=3, khai báo 3 trực tiếp giúp expected output rõ hơn random.

### 13.3. UUID cho namespace

Có thể dùng UUID.randomUUID() để tránh va chạm tên database, vì tên này không được đem so như business output.

### 13.4. ObjectId

Nếu test cần so _id chính xác, dùng một ObjectId cố định:

~~~java
import org.bson.types.ObjectId;

ObjectId id = new ObjectId(
    "65a000000000000000000001"
);
~~~

Nếu test kiểm tra cơ chế tạo ID, có thể assert not-null/unique, không nhất thiết hard-code generated value.

### 13.5. Kiểu ObjectId khác String

Một filter bằng string "65a..." không tương đương filter bằng ObjectId với cùng dạng hex.

## 14. Per-test database isolation

Mỗi test có thể dùng namespace duy nhất:

~~~text
Test 1: it_orders_0fe8... / orders
Test 2: it_orders_6dc2... / orders
Test 3: it_orders_a2d1... / orders
~~~

Bên trong từng database, có thể dùng các IDs giống nhau mà không đụng dữ liệu.

### 14.1. Cần tạo đủ indexes/schema

Một database mới mặc định trống. Setup không nên dựa vào migration đã chạy ở một test khác.

### 14.2. Teardown chỉ xóa database sở hữu

Nếu test lưu databaseName=it_orders_0fe8..., chỉ database đó được drop sau test.

### 14.3. Database name ngẫu nhiên và determinism

Fixture business vẫn exact; random namespace dùng cho isolation không làm thay đổi kết quả.

### 14.4. Lớp bảo vệ production

Mặc dù tên database có prefix it_, URI test vẫn có thể bị cấu hình sai. An toàn thực sự đến từ test deployment, restricted credentials và kiểm tra cluster identity.

## 15. JUnit 5 lifecycle

Các annotations:

- **@BeforeAll:** setup resource dùng chung cho class/suite.
- **@BeforeEach:** setup fixture riêng trước từng test.
- **@Test:** chạy hành vi, assertions.
- **@AfterEach:** cleanup sau từng test.
- **@AfterAll:** giải phóng resource dùng chung.

Gợi ý:

~~~text
@BeforeEach
  verify test environment
  create unique DB
  create indexes
  insert fixed documents

@Test
  call repository
  assert exact results

@AfterEach
  stop owned workers
  drop owned DB
  close owned cursors/client
~~~

### 15.1. Không biến @BeforeAll thành shared mutable database mặc định

Nếu tests ghi vào cùng database của @BeforeAll, chạy parallel/reorder có thể ảnh hưởng. Chỉ chia sẻ immutable config hoặc container/server, còn state nên riêng.

### 15.2. Cleanup vẫn phải chạy khi test fail

JUnit @AfterEach được dùng để cleanup ngay cả khi assertion không pass. Nếu beforeEach fail nửa chừng, teardown cần kiểm tra resource nào đã được tạo.

### 15.3. Test không phụ thuộc @Order

Nếu một workflow có nhiều bước phụ thuộc nhau, có thể đặt tất cả trong một test rõ Arrange/Act/Assert thay vì ép test methods thành chuỗi thao tác.

## 16. JUnit 5 + Java Sync Driver: fixture độc lập

Đây là ví dụ integration test dùng MongoDB test deployment qua biến **MONGODB_TEST_URI**. Hãy cấu hình credentials/test network riêng; không dùng production connection string.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.Sorts;

import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.Date;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderRepositoryIT {
    private MongoClient client;
    private MongoDatabase database;
    private MongoCollection<Document> orders;
    private String databaseName;

    @BeforeEach
    void setUp() {
        String uri = System.getenv(
            "MONGODB_TEST_URI"
        );

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "MONGODB_TEST_URI must point to a test DB"
            );
        }

        // Test infrastructure must additionally ensure
        // deployment identity and restricted credentials.
        databaseName = "it_orders_" +
            UUID.randomUUID().toString()
                .replace("-", "");

        client = MongoClients.create(uri);
        database = client.getDatabase(databaseName);
        orders = database.getCollection("orders");

        orders.createIndex(
            Indexes.compoundIndex(
                Indexes.ascending("tenantId"),
                Indexes.ascending("externalId")
            ),
            new IndexOptions().unique(true)
        );

        orders.insertMany(List.of(
            order("o-001", "tenant-a", "EXT-001",
                  "PAID", 150000L,
                  "2026-01-15T08:00:00Z"),
            order("o-002", "tenant-a", "EXT-002",
                  "PENDING", 90000L,
                  "2026-01-15T09:00:00Z"),
            order("o-003", "tenant-b", "EXT-001",
                  "PAID", 200000L,
                  "2026-01-15T10:00:00Z")
        ));
    }

    static Document order(
        String id,
        String tenant,
        String externalId,
        String status,
        long totalMinor,
        String createdAt
    ) {
        return new Document("_id", id)
            .append("tenantId", tenant)
            .append("externalId", externalId)
            .append("status", status)
            .append("totalMinor", totalMinor)
            .append(
                "createdAt",
                Date.from(
                    Instant.parse(createdAt)
                )
            );
    }

    @Test
    void returnsOnlyPaidOrdersFromTenantA() {
        List<Document> actual = orders.find(
            Filters.and(
                Filters.eq("tenantId", "tenant-a"),
                Filters.eq("status", "PAID")
            )
        ).sort(
            Sorts.ascending("_id")
        ).into(
            new ArrayList<>()
        );

        List<String> actualIds = actual.stream()
            .map(doc -> doc.getString("_id"))
            .toList();

        assertEquals(
            List.of("o-001"),
            actualIds
        );
    }

    @AfterEach
    void tearDown() {
        try {
            if (database != null) {
                // Drop only the database this test owns.
                database.drop();
            }
        } finally {
            if (client != null) {
                client.close();
            }
        }
    }
}
~~~

### 16.1. An toàn là điều kiện tiên quyết

**MONGODB_TEST_URI** phải trỏ tới test deployment được bảo vệ bằng network/credentials thích hợp. Random database prefix không phải biện pháp đủ để bảo vệ production.

### 16.2. Tại sao có UUID?

Mỗi method execution có database riêng để chạy đồng thời hoặc chạy lại không va chạm. Các IDs/dates bên trong vẫn cố định.

### 16.3. Vì sao tạo index trước insert?

Unique index là precondition của ứng dụng. Nếu dữ liệu seed vi phạm uniqueness, insert fail rõ ràng.

### 16.4. Java version

Stream.toList() yêu cầu Java version hỗ trợ, ví dụ JDK 17. Với Java cũ, có thể dùng Collectors.toList().

### 16.5. Test thực tế phải gọi repository

Ví dụ trên minh họa MongoDB operation. Khi kiểm thử repository method, thay phần actual bằng lời gọi **repository.findPaidByTenant("tenant-a")**, giữ expectedIds independent.

## 17. Ví dụ một test âm tính

Trong cùng class, test này có setup riêng nhờ @BeforeEach:

~~~java
@Test
void cannotSeePaidOrderOfAnotherTenant() {
    List<String> ids = orders.find(
        Filters.and(
            Filters.eq("tenantId", "tenant-a"),
            Filters.eq("status", "PAID")
        )
    ).sort(
        Sorts.ascending("_id")
    ).map(
        d -> d.getString("_id")
    ).into(new ArrayList<>());

    assertEquals(
        List.of("o-001"),
        ids
    );
}
~~~

### 17.1. Phải có negative control

Nếu bỏ o-003 thuộc tenant-b khỏi fixture, một query thiếu tenant filter có thể pass.

### 17.2. Assert toàn bộ result

Không chỉ assert contains o-001; một query trả thêm o-003 cũng là lỗi bảo mật.

### 17.3. Không lặp implementation làm expected

Expected là IDs đã biết từ fixture. Khi test repository thật, phần Act không nên tự tái tạo query cần kiểm tra.

## 18. Testcontainers tạo MongoDB disposable

Testcontainers có thể cung cấp MongoDB process riêng cho suite hoặc class. Đoạn sau là định hướng; module, Java class name và API chính xác cần đối chiếu với version Testcontainers của project.

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.containers.MongoDBContainer;

@Testcontainers
class MongoContainerIT {
    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(
            "mongo:PIN_A_SUPPORTED_TEST_VERSION"
        );

    @Test
    void usesDisposableMongo() {
        String uri = mongo.getReplicaSetUrl();

        // Open MongoClient for the test server,
        // create an isolated database, seed and test.
    }
}
~~~

### 18.1. Không dùng "latest" khi cần reproducibility

Ghim MongoDB server image tag và Java driver/Testcontainers module versions.

### 18.2. Khả năng mô phỏng

MongoDB container phù hợp nhiều integration tests; không tự mô phỏng toàn bộ Atlas, sharded cluster, region failover hoặc production network.

### 18.3. Container shared, state isolated

Có thể reuse MongoDB container trong phạm vi suite để giảm startup cost; vẫn tạo database riêng cho mỗi mutating test.

### 18.4. Readiness

Để container/framework đợi server thực sự sẵn sàng, không chỉ sleep một số giây cố định.

## 19. Pin versions và topology

Một test environment reproducible cần ghi:

~~~text
JDK: pinned compatible release
MongoDB Java Sync Driver: pinned release
MongoDB server/image: pinned release
Testcontainers module: pinned release
Topology: standalone or replica set
Feature Compatibility Version: recorded if relevant
Deployment settings: recorded if relevant
~~~

### 19.1. Transactions không chạy trên mọi topology

Multi-document transactions cần replica set/sharded cluster được hỗ trợ; standalone server có thể không đáp ứng.

### 19.2. Change Streams có yêu cầu topology

Một Change Stream integration test không nên được chạy trên standalone deployment nếu server/topology không hỗ trợ.

### 19.3. Matrix tests

Có thể chạy suite trên current và target server versions, nhưng mỗi run phải biết version đã dùng để không nhầm khác biệt behavior với fixture bug.

## 20. Schema validation thuộc fixture

Nếu production sử dụng MongoDB JSON Schema validator, một integration test cần xem xét tạo validator tương ứng.

Ví dụ lab:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "externalId",
        "status"
      ],
      properties: {
        tenantId: {
          bsonType: "string"
        },
        externalId: {
          bsonType: "string"
        },
        status: {
          enum: ["PENDING", "PAID", "CANCELLED"]
        }
      }
    }
  }
});
~~~

### 20.1. Valid fixture và invalid test case

Không nhét invalid documents vào baseline chung nếu việc seed sẽ fail. Trong test “reject missing tenant”, hãy thử insert invalid document trong Act và assert validation error.

### 20.2. Không tắt validator để test pass

Nếu hệ thống dựa vào validator, tắt nó trong integration tests sẽ bỏ sót bug.

### 20.3. Collection options

Collation, TTL, time-series/capped options hoặc view definitions cũng có thể là tiền điều kiện của behavior đang test.

## 21. Null, missing và BSON types

MongoDB phân biệt:

~~~javascript
{ _id: "null", discount: null }
{ _id: "missing" }
{ _id: "zero", discount: 0 }
{ _id: "string", discount: "0" }
~~~

### 21.1. eq(null)

MongoDB equality với null có thể match cả field null và missing. Fixture cần có cả hai để biết code hiểu đúng semantics.

### 21.2. exists(false)

Thường dùng để chọn field missing, không giống exact null.

### 21.3. Numeric types

Integer, Long, Double và Decimal128 có serialization/precision semantics riêng. Đừng seed giá bằng String nếu production lưu BSON numeric.

### 21.4. BSON Date

Một chuỗi "2026-01-15T10:00:00Z" không giống BSON Date của cùng thời điểm. Test filter date cần dùng Date/Instant mapping đúng.

### 21.5. Unicode

Nếu nghiệp vụ có text tiếng Việt, có thể thêm một vài fixtures có dấu để test collation/normalization; không cần corpus lớn nếu chỉ kiểm tra CRUD bình thường.

## 22. Nested arrays và $elemMatch

Fixture hai phần tử:

~~~javascript
{
  _id: "order-array-001",
  items: [
    { sku: "BOOK-001", qty: 1 },
    { sku: "BOOK-002", qty: 3 }
  ]
}
~~~

Query yêu cầu cùng phần tử có sku BOOK-001 và qty>=2:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "BOOK-001",
      qty: { $gte: 2 }
    }
  }
}
~~~

**Không match**, vì BOOK-001 chỉ có qty=1.

### 22.1. Fixture bắt một lỗi phổ biến

Hai điều kiện dot path riêng có thể match ở các phần tử khác nhau. Hai items là đủ để phân biệt query sai và $elemMatch đúng.

### 22.2. Không cần mảng dài

Nếu bài test chỉ kiểm tra same-element semantics, mảng 100 items làm test khó đọc mà không tăng coverage cần thiết.

### 22.3. Nested Java objects phải độc lập

Một static List<Document> được chia sẻ giữa fixtures có thể bị sửa trong test A, khiến test B nhận state khác. Trả một List/Document mới hoặc deep copy.

## 23. Pagination fixture với tie-breaker

~~~javascript
[
  {
    _id: "o-101",
    tenantId: "tenant-a",
    createdAt: ISODate("2026-01-15T10:00:00Z")
  },
  {
    _id: "o-102",
    tenantId: "tenant-a",
    createdAt: ISODate("2026-01-15T10:00:00Z")
  },
  {
    _id: "o-103",
    tenantId: "tenant-a",
    createdAt: ISODate("2026-01-14T10:00:00Z")
  }
]
~~~

Nếu sort createdAt descending rồi _id descending, kết quả mong đợi: **o-102, o-101, o-103**.

### 23.1. Vì sao trùng createdAt?

Nếu không có tie, test sẽ không phát hiện code thiếu _id tie-breaker.

### 23.2. Keyset pagination

Page size 2: trang đầu o-102/o-101; cursor ở o-101, trang tiếp theo o-103.

### 23.3. Concurrent updates là test khác

Fixture pagination static kiểm tra thuật toán. Muốn test inserts trong lúc đọc nhiều trang, tạo một case riêng với yêu cầu concurrency rõ.

## 24. Fixed time không phải phép màu cho TTL

MongoDB TTL monitor hoạt động bất đồng bộ và dùng thời gian server.

### 24.1. TTL có thể xóa dữ liệu trong fixture

Nếu một document có expiresAt trong quá khứ và TTL index đang hoạt động, record có thể biến mất giữa Arrange và Assert.

### 24.2. Không test TTL bằng sleep(1000)

MongoDB không cam kết xóa đúng thời điểm một giây. Dùng bounded polling tới khi condition đúng hoặc timeout.

### 24.3. Test TTL riêng

Đừng seed expired data vào fixture chung của mọi repository tests. Dùng collection/database riêng dành cho TTL.

### 24.4. Clock.fixed không đóng băng server clock

Inject fixed Clock trong Java kiểm soát app time, không thay giờ mà mongod dùng cho TTL.

## 25. Eventual consistency và bounded polling

Một hệ thống có Change Streams, background consumer hoặc search index cập nhật bất đồng bộ cần test có deadline.

~~~text
deadline = now + timeout
repeat:
  observe condition
  if expected: PASS
  if deadline elapsed: FAIL with diagnostic
  wait a bounded interval
~~~

### 25.1. Không sleep cố định quá lâu

Sleep 10 giây cho mọi test làm suite chậm, còn sleep 200 ms có thể gây flakiness trên CI. Poll condition thực tế.

### 25.2. Timeout rõ ràng

Không chờ vô hạn; khi fail, log expected/observed state và elapsed duration.

### 25.3. Consistency contract

Nếu behavior eventual, không assert một kết quả phải xuất hiện ngay tức thì; nếu behavior synchronous, cũng không nên dùng polling để che bug.

## 26. Change Stream fixture

Ví dụ contract:

~~~text
Given:
  Test collection is empty
  Consumer has subscribed and is ready
  Event identity is known

When:
  Update one known document

Then:
  A corresponding change event is observed
  Event identifies the expected document
  No unrelated tenant data is exposed
~~~

### 26.1. Resume token không portable tùy tiện

Không hard-code resume token từ cluster khác rồi kỳ vọng hoạt động. Token gắn với stream/history/topology theo MongoDB semantics.

### 26.2. Assert business invariant

Nếu event processing có at-least-once semantics, test có thể cần assert final state và idempotency thay vì đòi callback luôn đúng một lần.

### 26.3. Không dựa vào thứ tự giữa các consumers

Nếu nhiều workers/partitions, thứ tự tổng có thể không phải contract. Assert theo event ID và quan hệ nhân quả thực sự.

## 27. Concurrency fixture cực nhỏ

Test atomic $inc có thể chỉ cần một counter:

~~~javascript
{
  _id: "counter-001",
  value: 0
}
~~~

Sau N successful atomic increments, expected value=N.

### 27.1. Start đồng thời có kiểm soát

Dùng CountDownLatch/CyclicBarrier để nhiều workers cùng bắt đầu, thay vì gọi tuần tự.

### 27.2. Assert final state, không assert thread order

Không thể đảm bảo Thread 1 hoàn thành trước Thread 2. Điều cần kiểm tra là tất cả increments được ghi và final value đúng.

### 27.3. Worker cleanup

Đợi futures hoàn tất hoặc cancel/shutdown executor trước khi drop test database.

### 27.4. Một lần pass không chứng minh mọi interleaving

Có thể chạy nhiều seeds/stress suites, nhưng fixture data và invariant vẫn nên nhỏ và rõ.

## 28. Java concurrency test sketch

Hàm này giả định một MongoCollection thuộc test database riêng, chưa có counter-001.

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

public static void verifyAtomicCounter(
    MongoCollection<Document> collection
) throws Exception {
    collection.insertOne(
        new Document("_id", "counter-001")
            .append("value", 0)
    );

    int workers = 8;
    ExecutorService pool =
        Executors.newFixedThreadPool(workers);

    CountDownLatch ready =
        new CountDownLatch(workers);

    CountDownLatch start =
        new CountDownLatch(1);

    List<Future<?>> futures =
        new ArrayList<>();

    try {
        for (int i = 0; i < workers; i++) {
            futures.add(pool.submit(() -> {
                ready.countDown();
                if (!start.await(
                    5, TimeUnit.SECONDS
                )) {
                    throw new IllegalStateException(
                        "Start timed out"
                    );
                }

                collection.updateOne(
                    Filters.eq("_id", "counter-001"),
                    Updates.inc("value", 1)
                );
                return null;
            }));
        }

        if (!ready.await(
            5, TimeUnit.SECONDS
        )) {
            throw new IllegalStateException(
                "Workers not ready"
            );
        }

        start.countDown();

        for (Future<?> future : futures) {
            future.get(10, TimeUnit.SECONDS);
        }

        Document doc = collection.find(
            Filters.eq("_id", "counter-001")
        ).first();

        assertEquals(
            workers,
            doc.getInteger("value")
        );
    } finally {
        start.countDown();
        pool.shutdownNow();
    }
}
~~~

### 28.1. Client dùng chung giữa threads

MongoClient/MongoCollection trong Java Sync Driver được thiết kế để tái sử dụng; không cần tạo client riêng cho mỗi worker.

### 28.2. Test có timeout

ready latch, futures và executor đều có cơ chế giới hạn/cleanup. Không để CI chờ vô hạn.

### 28.3. Fixture per-test

Nếu hai tests cùng dùng counter-001 nhưng ở hai databases riêng, không va chạm.

## 29. Optimistic locking với version

Một document là đủ:

~~~javascript
{
  _id: "product-001",
  tenantId: "tenant-a",
  version: 5,
  stock: 10
}
~~~

Hai updates cùng filter version=5:

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "product-001"),
    Filters.eq("tenantId", "tenant-a"),
    Filters.eq("version", 5)
);

Bson update = Updates.combine(
    Updates.set("stock", 9),
    Updates.inc("version", 1)
);
~~~

### 29.1. Expected state

Nếu gọi tuần tự hai lần:

- Lần đầu matchedCount=1.
- Lần sau matchedCount=0.
- version cuối là 6.
- stock cuối là 9.

### 29.2. Không dùng data từ test trước

Nếu version đã là 6 vì test khác, case không còn kiểm tra expectedVersion=5 như đã định.

### 29.3. Assert persistency

Không chỉ assert API trả conflict; đọc lại document và kiểm tra version/stock không bị cập nhật thêm.

## 30. Transaction fixture và topology

Fixture cho test tạo order/trừ stock:

~~~text
products:
  product-001 available=2

orders:
  empty

On success:
  decrement available by 1
  insert order-001
  commit
  -> available=1, order exists

On failure:
  abort
  -> available=2, order absent
~~~

### 30.1. Topology phải hỗ trợ transaction

Multi-document transactions yêu cầu deployment/topology phù hợp, không mặc định một standalone mongod hỗ trợ như replica set.

### 30.2. Không bọc mọi test vào transaction như phương án cleanup chung

DDL, index builds, background consumers hoặc service code mở session riêng có thể không nằm trong transaction test. Per-test namespace dễ hiểu hơn trong nhiều integration tests.

### 30.3. External side effects

MongoDB transaction không tự rollback email/payment. Test cần sandbox hoặc fake integrations và kiểm tra idempotency/outbox.

### 30.4. Abort case riêng

Một test abort cần fixture mới có product available=2. Không chạy nó sau success case rồi mong stock vẫn bằng 2.

## 31. Upsert và unique index fixture

Fixture:

~~~text
products:
  p-001 tenant-a sku=BOOK-001

Unique index:
  (tenantId, sku)

Test A:
  upsert tenant-a/BOOK-001
  -> existing p-001 updated

Test B:
  upsert tenant-a/BOOK-002
  -> new document inserted

Test C:
  insert duplicate tenant-a/BOOK-001
  -> duplicate key rejected

Test D:
  insert tenant-b/BOOK-001
  -> allowed
~~~

### 31.1. Test insert và update của upsert

Chỉ kiểm tra upsertedId không đủ cho branch matched existing. Kiểm tra count/state và createdAt semantics.

### 31.2. Race conditions

Khi nhiều writers upsert cùng key, unique index bảo vệ uniqueness; application cần xử lý duplicate key errors theo semantics.

### 31.3. Seed không nên tự upsert mọi document

Dùng upsert khi đó là behavior được test. Trong setup clean DB, insert fixed documents thường khiến lỗi fixture bị lộ rõ hơn.

## 32. Soft-delete fixture

~~~javascript
[
  {
    _id: "p-live",
    tenantId: "tenant-a",
    name: "Live"
  },
  {
    _id: "p-deleted",
    tenantId: "tenant-a",
    name: "Deleted",
    deletedAt: ISODate("2026-01-01T00:00:00Z")
  },
  {
    _id: "p-other",
    tenantId: "tenant-b",
    name: "Other"
  }
]
~~~

### 32.1. Expected

Query visible products của tenant-a chỉ trả p-live.

### 32.2. Quy ước missing/null

Nếu active record có deletedAt missing, fixture phản ánh missing. Nếu thiết kế là deletedAt:null, thay test theo schema đó.

### 32.3. Không bật TTL ngoài ý muốn

Một test soft-delete visibility không cần TTL xóa documents theo đồng hồ thực; TTL phải được kiểm tra riêng.

## 33. Fixtures cho joins và $lookup

Khi repository dùng aggregation lookup:

~~~text
customers:
  c-001 tenant-a name=Alice
  c-002 tenant-a name=Bob

orders:
  o-001 tenant-a customerId=c-001
  o-002 tenant-a customerId=c-002
  o-003 tenant-a customerId=c-missing
~~~

### 33.1. Cố tình có orphan

Document o-003 giúp kiểm tra behavior khi reference không tìm thấy.

### 33.2. Chỉ giữ fields cần thiết

Nếu pipeline chỉ cần customerId và name, không đưa cả customer profile dài vào fixture.

### 33.3. Tenant-aware joins

Nếu hệ thống dùng business keys có thể trùng giữa tenants, nên thêm một record tenant-b làm negative control để phát hiện lookup sai scope.

## 34. Fixture cho business invariants

Ví dụ reserve stock:

~~~text
Given:
  Product available=2

When:
  Request quantity=3

Then:
  Reservation rejected
  Product available remains 2
  No confirmed order inserted
~~~

Success case:

~~~text
Given:
  Product available=2

When:
  Request quantity=2

Then:
  Reservation accepted
  Available becomes 0
  One expected order inserted
~~~

### 34.1. Assert database sau action

Một service có thể throw đúng exception nhưng vẫn ghi một phần. Cần xác minh persisted state.

### 34.2. Mỗi case có setup riêng

Không dùng remaining stock=0 từ test success làm tiền điều kiện cho test failure.

### 34.3. Multiple documents

Nếu một business operation cập nhật nhiều documents, assertion phải kiểm tra tất cả invariants và transaction/compensation semantics.

## 35. Fixture cho idempotency

~~~text
Before:
  operationId = reserve-001
  available = 5
  no reservation

Act:
  Call reserve(operationId, qty=2) twice

Expected:
  One logical reservation
  available = 3
  Both responses satisfy idempotency contract
~~~

### 35.1. Cùng operation ID cho retry

Nếu mỗi lần gọi dùng operation ID mới thì không kiểm thử duplicate suppression.

### 35.2. Có thể test concurrently

Gửi hai requests cùng operationId và kiểm tra final state/invariant, không phụ thuộc request nào thắng.

### 35.3. Outbox và external effects

Nếu reservation tạo outbox event, fixture/assertions phải kiểm tra không có duplicate logical side effects theo contract.

## 36. File fixtures: JSON, Extended JSON và Java code

Có thể tổ chức:

~~~text
src/test/resources/fixtures/
  orders-basic.json
  orders-null-missing.json
  products-stock.json
  aggregation-join.json
~~~

### 36.1. Java code

Tốt cho fixtures nhỏ với reusable factories, fixed Clock và BSON types rõ.

### 36.2. JSON

Tốt cho nội dung có nhiều records/fields và người đọc muốn kiểm tra riêng.

### 36.3. Extended JSON

Plain JSON không giữ đủ BSON type semantics cho ObjectId, Date, Decimal128, Binary. Dùng Extended JSON/codec khi cần fidelity.

### 36.4. Đừng có một mega fixture

Một file chung rất lớn làm mọi test phụ thuộc dữ liệu không liên quan và khiến việc sửa schema khó.

### 36.5. Version fixture cùng code

Fixtures là test artifacts cần được review cùng repository/schema migration. Không tự lấy dữ liệu live tại runtime rồi coi là stable fixture.

## 37. Tại sao không dùng production data trực tiếp?

- Có PII, secrets hoặc dữ liệu kinh doanh nhạy cảm.
- Có thể vi phạm retention và access policy.
- Dữ liệu biến đổi, không xác định expected output.
- CI logs/artifacts có nguy cơ rò dữ liệu.
- Test trở nên chậm và khó tối giản khi lỗi.

### 37.1. Synthetic fixtures

Ưu tiên tên/IDs/email/tổng tiền giả và có chủ đích.

### 37.2. Nếu cần dữ liệu production-like

Dùng quy trình trích xuất/khử định danh được phê duyệt, kiểm soát access và data lifecycle. Không copy raw backup vào test repository.

### 37.3. Dữ liệu nhỏ vẫn có thể nhạy cảm

Một document duy nhất chứa email/token thật vẫn là rủi ro.

## 38. Cleanup có ownership rõ ràng

~~~text
Test owns:
  Database it_orders_<unique>
  Its collections, indexes and docs

Test teardown:
  Stop test-owned background workers
  Close cursors and sessions
  Drop only it_orders_<unique>
  Close owned client
~~~

### 38.1. Setup thất bại một phần

Nếu MongoClient đã được tạo nhưng database chưa tạo xong, teardown vẫn phải đóng client, không cố drop một database không xác định.

### 38.2. Cleanup failure cũng là lỗi

Không nuốt mọi exception trong teardown. Nếu không xóa được namespace, ghi rõ và để CI/retention process xử lý.

### 38.3. Stop workers trước cleanup

Nếu executor còn chạy sau database.drop(), các workers có thể tạo documents trở lại hoặc lỗi bất thường.

### 38.4. Job bị kill trước teardown

Một CI job bị hủy có thể không chạy @AfterEach. Disposable containers, namespace TTL và cleanup theo ownership giúp xử lý leftovers.

## 39. Ngăn test ghi nhầm production

Tối thiểu:

1. Biến riêng **MONGODB_TEST_URI**, không fallback sang MONGODB_URI.
2. Test deployment thuộc network/project riêng.
3. Test credentials không có quyền ở production.
4. Verify deployment identity/control plane.
5. Test database names có prefix rõ.
6. Chỉ drop namespaces test tạo.
7. Có explicit approval cho lệnh destructive.
8. Không chạy test seeds qua production CI secrets.
9. Có observability/audit cho các thao tác dữ liệu lớn.

### 39.1. Localhost chưa chắc an toàn

Một port-forward/tunnel có thể trỏ tới production. Không dựa vào hostname để suy đoán môi trường.

### 39.2. Prefix không đủ

Dù database có tên it_test, nếu URI trỏ production và credentials quá rộng, dropDatabase vẫn nguy hiểm.

### 39.3. Không xóa để thử đoán lỗi

Nếu không xác định được target, dừng và xác minh kết nối thay vì thử drop collection/database.

## 40. CI workflow

~~~text
Checkout + build
     |
     v
Start pinned MongoDB test deployment
     |
     v
Wait for readiness, not fixed sleep
     |
     v
Run tests with isolated fixtures
     |
     v
Collect sanitized diagnostics
     |
     v
Cleanup owned resources
~~~

### 40.1. Pin dependency versions

Server/driver/Testcontainers version khác nhau có thể đổi behavior. Ghi lại versions của mỗi CI run.

### 40.2. Parallel jobs

Dùng namespace riêng cho mỗi test/job. Không chia sẻ một collection và xóa lẫn nhau.

### 40.3. Re-run và reorder

Một suite đáng tin phải pass khi chạy từng test, chạy lại và đổi thứ tự thực thi.

### 40.4. Thất bại ngẫu nhiên cần điều tra

Một flaky test đôi khi là data race hoặc thiếu isolation. Retry xanh lần hai không chứng minh root cause đã biến mất.

## 41. Fixture correctness khác performance dataset

| Mục đích | Kích thước | Yêu cầu chính |
| --- | --- | --- |
| Unit | Không cần MongoDB thật | Pure logic |
| Integration CRUD | Vài documents | Exact assertions |
| Unique index | 2-4 documents | Constraint correctness |
| Array matching | 1-2 documents | Semantics |
| Concurrency | 1-3 documents + nhiều writes | Invariant |
| Transaction | Ít documents nhiều collections | Atomicity |
| TTL/Change Stream | Ít documents và async events | Eventual behavior |
| Load/performance | Data representative lớn | P95/throughput |
| DR/failover | Topology, backups | Recovery behavior |

### 41.1. Không suy từ dữ liệu nhỏ rằng query nhanh khi production lớn

Với ba documents, server có thể dùng COLLSCAN rất hợp lý. Index performance phải được đo riêng trên dataset đủ đại diện.

### 41.2. Không đưa performance volume vào mọi correctness test

Sẽ khiến suite chậm, tốn CI resources và khó debug.

## 42. Quy trình thiết kế fixture từ requirement

Requirement: “Người dùng chỉ xem được orders PAID của tenant mình, sắp theo createdAt mới nhất”.

### Bước 1 — Diễn đạt behavior

~~~text
Given orders from two tenants and multiple statuses
When finding paid orders for tenant-a
Then return only tenant-a paid orders
And order by createdAt descending, _id descending
~~~

### Bước 2 — Chọn records tối thiểu

~~~text
o-001 tenant-a PAID    10:00
o-002 tenant-a PAID    10:00
o-003 tenant-a PENDING 11:00
o-004 tenant-b PAID    12:00
~~~

### Bước 3 — Cố định loại dữ liệu

String IDs, BSON Date theo UTC, status strings hợp lệ.

### Bước 4 — Dự đoán kết quả

Theo createdAt desc, _id desc: **o-002, o-001**.

### Bước 5 — Setup độc lập

Tạo database riêng, indexes, seed bốn documents.

### Bước 6 — Gọi method đang test

Gọi repository.findPaidByTenant("tenant-a") hoặc service public API tương ứng.

### Bước 7 — Assert toàn bộ kết quả

So exact ordered IDs và fields quan trọng.

### Bước 8 — Cleanup

Drop đúng own database, close resources.

## 43. Detect state leakage

Các cách chủ động tìm lỗi fixture:

- Chạy test đơn lẻ.
- Chạy test hai lần liên tiếp.
- Đổi thứ tự test methods/classes.
- Chạy parallel.
- Chạy trên test environment trống.
- Cố ý để test trước fail giữa chừng, kiểm tra test sau vẫn độc lập.
- Theo dõi số databases/containers còn lại.
- So outputs ở nhiều CI runs cùng version/seed.

### 43.1. Reproducibility report

Ghi test name, code revision, fixture version, seed, fixed Clock, driver/server version, namespace và sanitized failure details.

### 43.2. Không thêm sleep để che race

Sleep làm test chậm và có thể chỉ dời điểm lỗi. Cần setup isolation hoặc bounded waiting theo behavior.

### 43.3. Test failures nên thu nhỏ fixture

Nếu bug chỉ xuất hiện với 100 random documents, thử tìm minimal counterexample để chuyển thành regression fixture xác định.

## 44. Mẫu log khi test fail

~~~text
test: OrderRepositoryIT.returnsPaidTenantOrders
fixture: orders-basic-v1
serverVersion: pinned-test-release
driverVersion: pinned-driver-release
namespace: it_orders_<run-id>
clockUtc: 2026-01-15T10:00:00Z
seed: none
expectedIds: [o-001]
actualIds: [o-001, o-003]
result: FAIL
~~~

### 44.1. Log đủ để tái hiện

Expected/actual IDs và environment context giúp phân biệt bug query, mismatch server version hoặc state leakage.

### 44.2. Không log credentials/PII

Dùng synthetic IDs và bỏ password/token/raw customer details khỏi test artifacts.

### 44.3. Diagnostic order

Sắp xếp IDs/fields trong báo cáo khi thứ tự không có ý nghĩa để tránh noise giữa runs.

## 45. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Fixture có hàng ngàn documents không dùng | Chậm, khó hiểu | Minimal counterexamples |
| Chỉ có happy path | Query sai vẫn pass | Negative controls |
| new Date() trong expected | Time flakiness | Fixed Clock |
| Random không seed | Không tái hiện | Seed cố định/log seed |
| ObjectId tự sinh rồi so hard-coded | Mismatch | Fixed ID/assert property |
| Không sort find | Order-dependent | Explicit sort |
| Fixture dùng String thay BSON Date | Range sai | Correct BSON types |
| Static mutable Document | Cross-test mutation | Fresh factories |
| Test B dựa Test A | Order-dependent | Per-test Arrange |
| Database chung | Parallel collision | Unique namespace |
| Cleanup toàn shared DB | Xóa test khác | Drop owned DB only |
| Unique index chưa setup | False pass | Index in fixture |
| Validator không setup | Invalid writes lọt | Relevant schema setup |
| Dùng JSON để biểu diễn ObjectId như string | Type mismatch | Extended JSON/codec |
| Expected query tính bằng implementation | Shared bug | Independent oracle |
| Test TTL bằng sleep cố định | Flaky | Bounded polling |
| Test Change Stream trên topology sai | Unsupported | Supported replica set |
| Assert thread order | Flaky | Final invariants |
| Không join workers trước cleanup | Background races | Join/cancel first |
| Transactions trên standalone | Feature error | Correct topology |
| Container tag latest | Version drift | Pin version |
| Raw production fixture | Privacy risk | Synthetic/anonymized |
| URI test fallback production | Data loss risk | Restricted test deployment |
| Setup fail, teardown không cleanup | Leaked resources | Defensive teardown |
| CI kill để lại DB | Resource leak | Disposable infra/TTL |
| Tiny fixture dùng kết luận performance | Sai bằng chứng | Separate load suite |

## 46. Bài tập về fixture tối thiểu

### Bài 1 — Tenant filter

Thiết kế ba orders để phát hiện cả hai lỗi: thiếu tenantId filter và thiếu status filter. Viết exact expected result.

### Bài 2 — Range boundary

Filter price>=100 và price<200. Chọn tối thiểu các prices để phân biệt gt/gte và lt/lte.

### Bài 3 — Unique business key

Thiết kế fixture chứng minh unique(tenantId,externalId) chặn duplicate cùng tenant nhưng cho phép trùng giữa tenants.

### Bài 4 — Null/missing

Tạo bốn documents có field discount: null, missing, 0, "0". Dự đoán eq(null) và exists(false).

### Bài 5 — Array

Tạo một items array khiến hai dot predicates match nhưng $elemMatch không match.

### Bài 6 — Pagination

Hai orders cùng createdAt; thiết kế expected order với sort createdAt desc,_id desc.

## 47. Bài tập về determinism

### Bài 7 — Fixed clock

Thay Instant.now() trong service bằng injectable Clock và test timestamp cố định.

### Bài 8 — Random seed

Một generator Random() không seed bị fail trên CI. Ghi seed, tái tạo case, giảm fixture về ví dụ nhỏ.

### Bài 9 — ObjectId

Khi nào cần ObjectId cố định, khi nào chỉ assert ID không null/unique?

### Bài 10 — BSON types

Giải thích vì sao ISO string và BSON Date không thay thế cho nhau trong range query test.

### Bài 11 — Sort

Một test assert phần tử đầu từ find không sort. Sửa thành kết quả ổn định.

### Bài 12 — Mutable fixture

Hai tests dùng chung static Document có nested List. Chỉ ra bug và sửa factory.

## 48. Bài tập về isolation và CI

### Bài 13 — Test order

Test A tạo o-001, Test B đọc o-001. Viết lại để B chạy riêng được.

### Bài 14 — Parallel

Hai tests đều dùng _id=o-001. Thiết kế per-test database names và cleanup.

### Bài 15 — Setup failure

@BeforeEach đã tạo MongoClient nhưng lỗi createIndex. @AfterEach phải xử lý thế nào?

### Bài 16 — Production safety

MONGODB_TEST_URI vô tình trỏ production. Những lớp bảo vệ nào ngoài tên it_ giúp ngăn destructive test?

### Bài 17 — Testcontainers

Thiết kế CI job pin MongoDB image, chờ readiness, seed, test và cleanup.

### Bài 18 — Leaked DB

Một CI job bị kill và không chạy teardown. Làm cách nào phát hiện và cleanup an toàn theo ownership?

## 49. Bài tập về concurrency và asynchronous behavior

### Bài 19 — TTL

Thiết kế TTL test với bounded polling thay sleep cố định.

### Bài 20 — Change Streams

Một change event có thể đến muộn. Assert bằng event ID và deadline thế nào?

### Bài 21 — Atomic $inc

Một counter=0, 100 concurrent increments. Expected state và cách dùng latch/futures?

### Bài 22 — Optimistic locking

Hai updates với filter version=5. Trạng thái cuối, matchedCount và version expected?

### Bài 23 — Transaction

Dùng một product và một order, thiết kế commit case và abort case độc lập.

### Bài 24 — Idempotency

Gọi reserve cùng operationId hai lần, kiểm tra stock, reservation và outbox không double count.

### Bài 25 — Performance

Tại sao fixture ba documents không đủ chứng minh index phù hợp với 1 triệu orders? Cần test suite nào?

## 50. Checklist thiết kế fixture MongoDB

### Nhỏ gọn

1. Mỗi record đều phục vụ một assertion hoặc negative control.
2. Không giữ fields không liên quan.
3. Có edge case/boundary đủ để phân biệt bug.
4. Tách từng scenario thành fixture nhỏ.
5. Expected result độc lập implementation.

### Xác định

6. Fixed IDs cho values cần so chính xác.
7. Fixed UTC timestamps và injected Clock khi thích hợp.
8. Random có seed hoặc được loại bỏ.
9. Không phụ thuộc natural order của MongoDB.
10. Explicit sort và tie-breaker khi cần.
11. BSON types được kiểm soát.
12. Server/driver/container versions được ghi rõ.
13. TTL/Change Stream có eventual assertions với timeout.
14. Concurrency assert invariant, không thread order.

### Độc lập

15. Mỗi test tự setup tiền điều kiện.
16. Không phụ thuộc thứ tự tests.
17. Mutating tests có namespace riêng.
18. Factory trả object mới, không shared mutable state.
19. Indexes/validators là một phần setup.
20. Cleanup chỉ resources test sở hữu.
21. Teardown xử lý cả setup failure.
22. Join/stop workers trước cleanup.
23. CI xử lý leaked resources khi job bị hủy.
24. Tests chạy lại/parallel vẫn pass.

### An toàn và vận hành

25. URI/credentials riêng cho test deployment.
26. Không fallback test URI sang production.
27. Không copy raw production PII vào fixture.
28. Không dùng dropDatabase ngoài namespace được phép.
29. Failure logs có seed, version, expected/actual.
30. Performance/load testing có datasets và suite riêng.

## 51. Runbook áp dụng cho mỗi integration test

~~~text
INPUT:
  Behavior under test
  Small document set
  Required indexes/validators
  Fixed IDs/Clock/seed
  Expected exact result/invariant

SETUP:
  Verify dedicated test environment
  Allocate unique namespace
  Create collection/index/schema
  Insert minimal fixture

ACT:
  Call real repository/service method

ASSERT:
  Exact IDs/values and order
  Negative controls excluded
  Persisted business invariants
  Expected error type/code if failure case

CLEANUP:
  Stop background tasks
  Close sessions/cursors
  Drop owned namespace only
  Release resources

REPORT:
  Test ID and fixture version
  Server/driver version
  Seed/Clock
  Expected vs actual
  Sanitized diagnostics
~~~

## 52. Kết luận

Một fixture MongoDB tốt không chỉ là “một ít dữ liệu để test chạy”. Nó là **hợp đồng tiền điều kiện rõ ràng**, giúp mỗi assertion có ý nghĩa.

- **Nhỏ:** có đủ positive, negative và boundary examples nhưng không chứa dữ liệu thừa.
- **Xác định:** ID, thời gian, random seed, BSON types và thứ tự kết quả được kiểm soát.
- **Độc lập:** mỗi test tự tạo trạng thái và cleanup resources của chính mình, không phụ thuộc tests khác hay dữ liệu từ lần chạy trước.
- **MongoDB-specific:** unique indexes, validators, array semantics, transactions, TTL, Change Streams và topology cần xuất hiện trong setup khi behavior yêu cầu.
- **An toàn:** test deployment riêng, credentials hạn chế và không dùng lệnh xóa lên production.

Khi thực hiện nhất quán, fixture nhỏ, xác định và độc lập giúp giảm flaky tests, rút ngắn thời gian điều tra và làm các thay đổi repository/schema đáng tin hơn. Một test fail lúc đó chỉ ra vấn đề thực sự trong logic hoặc tiền điều kiện được kiểm chứng, thay vì một chuỗi hiệu ứng phụ không thể tái hiện từ test khác.

## Tài liệu tham khảo

- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [MongoDB Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/)
