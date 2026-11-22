# Kiểm thử NULL/UNSET, collection, UDT và kiểu dữ liệu biên

> **Chương:** Kiểm thử tích hợp  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — hiểu kiến trúc phân tán, mô hình wide-column của Apache Cassandra, khóa phân vùng, thiết kế bảng theo truy vấn, consistency, CQL, replication, compaction, repair, xử lý lỗi và kết nối từ Java.

Một API Java nhận bản cập nhật hồ sơ:

~~~json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "note": null,
  "tags": [],
  "address": { "city": "Hà Nội" }
}
~~~

Nhìn sơ qua, team có thể nghĩ rằng `note = null` là “để nguyên”, `tags = []` là “xóa hết” và `address.city` thay đổi mà vẫn giữ các field khác. **Cassandra không tự hiểu ý đồ đó.** Với CQL prepared statements:

- Giá trị **`UNSET`** nghĩa là *không ghi vào cột được bind*.
- Giá trị **`NULL`** ở cột thường là *xóa giá trị*, tạo **tombstone**.
- Collection rỗng và collection thiếu dữ liệu có thể **không phân biệt được sau round-trip**; list/set/map có quy tắc codec, cập nhật và thứ tự khác nhau.
- `frozen<UDT>` được ghi như **một giá trị**, còn UDT không frozen có thể cập nhật **từng field**.
- Kiểu `timestamp`, `date`, `decimal`, `varint`, `blob` và Unicode có những giá trị biên dễ lộ lỗi chuyển đổi kiểu.

Chỉ mock `CqlSession` trong unit test **không thể kiểm chứng** đầy đủ các semantics này. Bài học xây một **bộ integration tests chạy trên Cassandra thật bằng Testcontainers/JUnit**, đồng thời chỉ rõ những trường hợp phải thử thêm trên topology nhiều node.

**Phạm vi phiên bản:** ví dụ chính dùng Apache Cassandra **4.1.x** trong container, **Apache Java Driver 4.19 API**, Java **17**, JUnit Jupiter 5 và Testcontainers **2.0.x**. Có thể chạy ma trận tương thích thêm Cassandra 5.0; test semantics cụ thể phải được xác nhận theo server/driver version đã chốt. Testcontainers **1.x** đặt `CassandraContainer` trong package khác với **2.x**. Không thay dependency version một cách tùy tiện khi sao chép mã.

## 1. Kết quả học tập và triết lý kiểm thử

Học xong bài, bạn có thể:

1. Mô tả rành mạch `ABSENT`, `UNSET`, `NULL`, `EMPTY` và `NON_EMPTY` theo **ngữ cảnh CQL**; không coi chúng là năm trạng thái có thể phân biệt được ở mọi cột.
2. Dùng `PreparedStatement.bind()`, `BoundStatement.unset()`, `setToNull()` và `isSet()` để kiểm tra hiệu ứng ghi lên hàng đã có giá trị.
3. Chứng minh `UNSET` **không xóa** giá trị cũ, còn `NULL` ở cột thường **xóa** và có thể tạo tombstone.
4. Kiểm thử PK không được NULL/UNSET, đồng thời phân biệt hàng không tồn tại với cột không tồn tại trong một hàng đang sống.
5. Round-trip `list/set/map`, tránh phụ thuộc thứ tự của set/map, kiểm tra null elements và collection rỗng đúng semantics.
6. Tạo và đọc `UdtValue`, kiểm thử `frozen<UDT>` và UDT non-frozen, field thiếu/null, schema type evolution và codec.
7. Kiểm tra biên của `tinyint/smallint/int/bigint/varint/decimal`, timestamp trước 1970, leap day, precision và Unicode.
8. Dựng test chạy tự động trên Cassandra thật với isolation, setup/teardown, dependency pinning và CI không phụ thuộc database cá nhân.
9. Tách test **correctness/codec** trên một node khỏi test **RF/CL, repair, failure/retry** đòi hỏi nhiều node.
10. Thiết kế assertion nhạy với schema, timeout, TTL và data modeling thay vì assert theo output `cqlsh` hoặc log text dễ thay đổi.

### 1.1. Test pyramid phù hợp Cassandra

| Lớp | Kiểm tra được | Không chứng minh được |
|---|---|---|
| Unit: codec/utilities/DTO | Normalize Unicode, JSON parsing, validation, mapping local | Server CQL có chấp nhận mutation hay không |
| Integration: **1 Cassandra thật** | NULL/UNSET, CQL type, codec, UDT, collection, PK rule, basic LWT | Quorum nhiều node, split-brain, repair, DC failover |
| Integration: **multi-node** | RF/CL, replica failures, read/write timeouts, topology changes | Toàn bộ tải production và long-term tombstone cost |
| End-to-end: HTTP → service → Cassandra | Contract absent/null/empty, idempotency, serialization, auth | Không thể thay thế test chuyên về schema/driver |
| Load/soak/chaos | Hot partitions, p99, TTL/tombstone/compaction và recovery dài hạn | Không thay thế assertions giá trị chính xác |

**Luật vàng:** Nếu bài toán xảy ra ở wire protocol, CQL parser, server storage engine hoặc codec, phải có **ít nhất một test đi qua chính Cassandra** chứ không chỉ mock repository.

## 2. Định nghĩa NULL, UNSET và trạng thái tồn tại

### 2.1. Những từ giống nhau nhưng ở các tầng khác nhau

| Khái niệm | Xuất hiện ở đâu | Tác động |
|---|---|---|
| **ABSENT JSON field** | HTTP request không chứa key `note` | Application **phải tự quyết định** là UNSET, default hay validation error |
| **JSON `null`** | Request chứa `"note": null` | Application **phải định nghĩa** là xóa hay bỏ qua; không tự suy giống UNSET |
| **UNSET bind variable** | Java Driver native protocol v4+ | CQL bỏ qua assignment cho cột được bind, không sinh tombstone do cột ấy |
| **NULL bind value** | `BoundStatement.setToNull` hoặc bind Java `null` | Với cột thường được phép ghi, xóa giá trị và tạo tombstone theo mutation |
| **CQL empty string** | `''` / Java `""` | Là **chuỗi dài 0**, khác NULL trong text column |
| **Empty collection** | `[]`, `{}`, Java `List.of()`/`Set.of()` | Không tương đương yêu cầu “không động vào cột”; phân biệt với NULL có hạn chế |
| **Row absent** | `SELECT ... WHERE PK=?` trả không có row | Khác với một row còn sống nhưng `note` null |

Tách **trạng thái API** khỏi **trạng thái CQL**. Nếu hệ thống nhận PATCH, nên dùng DTO biểu diễn ba trường hợp **field absent / explicit null / value**, ví dụ JSON presence wrapper; không dùng một nullable property Java đơn thuần để đoán user muốn xóa hay giữ nguyên.

### 2.2. Semantics của UPDATE đã chuẩn bị

Giả sử hàng đã có `note='giữ-lại'` và `score=7`:

~~~text
UPDATE ... SET note=?, score=? WHERE profile_id=?

bind(note=UNSET, score=8) -> note vẫn 'giữ-lại'; score đổi thành 8
bind(note=NULL,  score=UNSET) -> note không còn giá trị; score vẫn 8
bind(note='',    score=UNSET) -> note thành chuỗi rỗng; score vẫn 8
~~~

Nếu hàng vẫn còn dữ liệu sống ở cột khác, `SELECT note,score` cho phép đọc `note=null` và `score=8`. Nhưng truy vấn ở mức CQL **không phải API hỏi “cột này chưa từng được viết hay đã bị xóa?”**: cả hai có thể trả null, phải dùng sequence test và hiểu tombstone/metadata.

### 2.3. Java Driver 4.x: UNSET được hỗ trợ ở protocol v4+

`PreparedStatement.bind()` **không truyền tham số** để lại các bind variables ở trạng thái **UNSET** nếu protocol hỗ trợ; `unset(i)` có thể đưa một biến đã set trở lại UNSET.

~~~java
PreparedStatement ps = session.prepare(
    "UPDATE it_lab.profile_by_id " +
    "SET note = ?, score = ? WHERE profile_id = ?");

BoundStatement base = ps.bind();
assert !base.isSet(0);                  // note: UNSET
assert !base.isSet(1);                  // score: UNSET

BoundStatement withKey = base.setUuid(2, id);
BoundStatement clearNote = withKey.setToNull(0);
BoundStatement keepNote = clearNote.unset(0);

assert clearNote.isSet(0);              // explicit NULL đã set
assert !keepNote.isSet(0);              // UNSET lại
~~~

**Statements Driver 4.x là immutable:** `setUuid()`, `setToNull()` và `unset()` đều trả **object mới**. Không viết `base.unset(0); session.execute(base);` rồi tin biến cũ đã đổi. Đặc biệt, **không gửi UNSET cho primary key hoặc dùng nó như một predicate trong WHERE**; Cassandra sẽ từ chối các vị trí không hợp lệ.

### 2.4. NULL có thể tạo tombstone

Trong Cassandra, xóa cột được biểu diễn bằng **tombstone** để replica khác không làm giá trị cũ “sống lại” khi hợp nhất dữ liệu. Kiểm thử:

~~~sql
UPDATE it_lab.profile_by_id
SET note = null
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
~~~

Để kiểm chứng **ngữ nghĩa**, assert `row.isNull("note")` và cột khác giữ nguyên. **Không** yêu cầu test đọc trực tiếp file SSTable/tombstone để chứng minh CQL NULL — điều đó phụ thuộc flush/compaction và implementation. Với workload cập nhật nhiều cột bằng null, tombstones có thể ảnh hưởng đọc/compaction; đo theo cụm, không suy số lượng tombstone chính xác từ một test đơn.

### 2.5. Khi nào cần phân biệt ABSENT, NULL, EMPTY bằng schema riêng?

Nếu business cần biết **“người dùng chưa từng gửi tags”** khác với **“đã xóa hết tags”**, không dựa vào `getSet("tags") == null` vì Cassandra/codec có thể chuẩn hóa cả hai thành empty collection. Nên thiết kế rõ:

- Cột `tags_state`/`tags_specified` hoặc version/operation marker có chủ đích.
- JSON API contract quy định absent = giữ nguyên, null = xóa, empty = tập rỗng.
- Các cập nhật trên những cột trạng thái liên quan phải nhất quán theo partition và semantics mutation.
- Với workflow đòi compare-and-set, cân nhắc LWT/version, không dựa vào timestamp mặc định để quyết định ai thắng.

## 3. Dựng môi trường test thật bằng Testcontainers

### 3.1. Phiên bản và yêu cầu hạ tầng

Phần thực hành dùng **Testcontainers 2.0.x** và **Java 17**; code đặt `CassandraContainer` tại package **`org.testcontainers.cassandra`**. Testcontainers 1.x cũ dùng `org.testcontainers.containers.CassandraContainer` và artifact `org.testcontainers:cassandra`; **không trộn hai thế hệ**. Cần container runtime/Docker engine hoạt động; Testcontainers sẽ quản lý start/stop thay vì yêu cầu mọi người dùng chung một Cassandra trên máy dev.

Gradle Groovy DSL minh họa:

~~~groovy
dependencies {
    testImplementation "org.junit.jupiter:junit-jupiter:5.11.4"
    testImplementation "org.testcontainers:testcontainers-cassandra:2.0.5"
    testImplementation "org.testcontainers:testcontainers-junit-jupiter:2.0.5"

    // Java Driver version dùng cùng BOM/stack của ứng dụng:
    implementation "org.apache.cassandra:java-driver-core:4.19.0"
}

test {
    useJUnitPlatform()
}
~~~

**Version là ví dụ đã pin**, không phải yêu cầu dùng đúng những patch này trong mọi dự án. Nếu dự án Spring Boot quản lý JUnit/driver bằng BOM, ưu tiên BOM đã kiểm tra; đừng ép thêm hai Java Driver implementations khác nhau. Cassandra image trong bài dùng `cassandra:4.1` để dễ thử; **trên CI cần pin patch/digest đã phê duyệt** nhằm tái lập kết quả và kiểm soát thay đổi ảnh.

### 3.2. JUnit 5 container và session lifecycle

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.TestInstance;
import org.testcontainers.cassandra.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CassandraTypesIT {
    @Container
    static final CassandraContainer CASSANDRA =
        new CassandraContainer(DockerImageName.parse("cassandra:4.1"));

    private CqlSession session;

    @BeforeAll
    void init() {
        session = CqlSession.builder()
            .addContactPoint(CASSANDRA.getContactPoint())
            .withLocalDatacenter(CASSANDRA.getLocalDatacenter())
            .build();
        // Tạo schema theo thứ tự: keyspace -> UDT -> table.
        // Đoạn CQL đầy đủ ở mục 4; dùng session.execute từng lệnh.
    }

    @AfterAll
    void close() {
        if (session != null) session.close();
    }
}
~~~

Với cấu hình mặc định, Testcontainers Cassandra là **một node**; không được dùng test này để kết luận `QUORUM/LOCAL_QUORUM` vẫn hoạt động khi một replica Down. JUnit extension thường quản lý static container theo **vòng đời class**. Không enable parallel tests với **chung schema/hàng dữ liệu** nếu chưa có chiến lược isolation; tài liệu Testcontainers JUnit extension chỉ bảo đảm những trường hợp đã kiểm thử.

### 3.3. Spring Boot integration test: chọn đúng entrypoint

Nếu muốn kiểm thử entity converter/repository/Spring Data:

~~~java
// Pattern, không phải file standalone:
//
// @SpringBootTest
// @Testcontainers
// class ProfileRepositoryIT {
//   @Container static final CassandraContainer CASSANDRA = ...;
//
//   @DynamicPropertySource
//   static void cassandraProps(DynamicPropertyRegistry registry) {
//       registry.add("spring.cassandra.contact-points",
//           () -> CASSANDRA.getHost() + ":" + CASSANDRA.getMappedPort(9042));
//       registry.add("spring.cassandra.local-datacenter",
//           CASSANDRA::getLocalDatacenter);
//       registry.add("spring.cassandra.keyspace-name", () -> "it_lab");
//   }
// }
~~~

`@DynamicPropertySource` là một cách đưa endpoint động vào Spring Boot 3.x; với Spring Boot Testcontainers integration đã tương thích, `@ServiceConnection` có thể giúp tạo connection details. **Không bật cả hai mù quáng** khi chúng cấp hai cấu hình khác nhau. Spring context phải được tạo **sau khi endpoint đã biết**; schema/keyspace cần tồn tại trước khi repository khởi tạo sử dụng nó.

### 3.4. Tránh flakiness do Cassandra khởi động và schema agreement

Testcontainers có wait strategy nhưng **container ready không đồng nghĩa mọi schema mutation đã được nhận và đồng thuận** trên topology nhiều node. Nguyên tắc:

1. Chờ cổng native protocol và session kết nối được.
2. Tạo keyspace, sau đó type, sau đó table bằng CQL có kiểm tra kết quả.
3. Với multi-node, đợi **schema agreement** và topology ổn định trước khi prepare statement.
4. Chạy test bằng ID riêng từng case; không tái sử dụng một UUID hard-code làm dữ liệu giữa các tests chạy song song.
5. Nếu container khởi động lỗi, thu log container, native transport/GC và driver startup logs; **không** tăng sleep cố định vô hạn.

## 4. Schema kiểm thử tập trung các loại dữ liệu

### 4.1. Keyspace: RF=1 cho single-node integration test

~~~sql
CREATE KEYSPACE IF NOT EXISTS it_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 1
}
AND durable_writes = true;
~~~

`datacenter1` là tên DC mặc định thường gặp của image Testcontainers Cassandra; **phải kiểm tra `CASSANDRA.getLocalDatacenter()` trong runtime**. Nếu tên khác, thay vào CQL tương ứng. **RF=1 không phải cấu hình production**; nó giúp kiểm thử codec/CQL semantics mà không yêu cầu ba node.

### 4.2. Tạo UDT trước khi tạo bảng

~~~sql
CREATE TYPE IF NOT EXISTS it_lab.address_info (
  street text,
  city text,
  postal_code text
);

CREATE TABLE IF NOT EXISTS it_lab.profile_by_id (
  profile_id uuid PRIMARY KEY,
  note text,
  score int,
  active boolean,
  priority_tiny tinyint,
  short_value smallint,
  long_value bigint,
  huge_value varint,
  amount decimal,
  created_at timestamp,
  event_day date,
  event_time time,
  tags set<text>,
  aliases list<text>,
  quotas map<text, int>,
  home frozen<it_lab.address_info>,
  office it_lab.address_info,
  blob_value blob,
  source_ip inet
);
~~~

Các cột được chọn để thử:

- **`note/score/active`:** NULL vs UNSET và primitive defaults (0/false).
- **`priority_tiny/short_value/long_value/huge_value/amount`:** giá trị biên, overflow và precision.
- **`created_at/event_day/event_time`:** độ chính xác thời gian/UTC/lịch.
- **`tags/aliases/quotas`:** set/list/map, empty, duplicate, element typing.
- **`home`:** frozen UDT, cập nhật **toàn bộ giá trị**.
- **`office`:** non-frozen UDT, có thể cập nhật từng field.
- **`blob_value/source_ip`:** binary buffer và địa chỉ mạng.

Nếu server/version bạn dùng không hỗ trợ một kiểu hay cú pháp, **không bỏ qua lỗi trong test**: ghi rõ feature matrix theo version và kiểm tra tài liệu CQL của release đó. Với Testcontainers 4.1, schema phải được tạo trên instance test mới, không tự suy nó đã tồn tại chỉ vì dùng `IF NOT EXISTS`.

### 4.3. Mẫu trình tự setup trong Java

~~~java
// Bên trong @BeforeAll sau khi CqlSession đã được tạo:
session.execute("CREATE KEYSPACE IF NOT EXISTS it_lab " +
    "WITH replication = {'class': 'NetworkTopologyStrategy', " +
    "'" + CASSANDRA.getLocalDatacenter() + "': 1}");

session.execute("CREATE TYPE IF NOT EXISTS it_lab.address_info (" +
    "street text, city text, postal_code text)");

session.execute("CREATE TABLE IF NOT EXISTS it_lab.profile_by_id (" +
    "profile_id uuid PRIMARY KEY, note text, score int, active boolean, " +
    "priority_tiny tinyint, short_value smallint, long_value bigint, " +
    "huge_value varint, amount decimal, created_at timestamp, " +
    "event_day date, event_time time, tags set<text>, aliases list<text>, " +
    "quotas map<text,int>, home frozen<it_lab.address_info>, " +
    "office it_lab.address_info, blob_value blob, source_ip inet)");
~~~

Trong project thật, **dùng migration SQL/CQL files hoặc schema fixtures được kiểm soát** thay vì chép cùng DDL vào nhiều test classes. Đoạn Java ở trên cho một bài học tự chứa, không đòi đọc thêm tệp repository khác; nó không tự kiểm thử TLS, password auth hoặc rolling migration.

## 5. Test đầu tiên: NULL khác UNSET trên cùng hàng

### 5.1. Chuẩn bị dữ liệu trước mỗi case

Mỗi test tạo UUID riêng để không đụng dữ liệu của test khác:

~~~java
UUID id = UUID.randomUUID();

PreparedStatement seed = session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, note, score) VALUES (?, ?, ?)");
session.execute(seed.bind(id, "preserve-me", 7));
~~~

**Không** dùng `TRUNCATE TABLE` trong mỗi test nếu nhiều tests dùng cùng container; TRUNCATE tạo rào cản/overhead và có thể xóa dữ liệu của test chạy song song. Khi test kết thúc, container được dọn; nếu cần cleanup cụ thể, DELETE theo UUID của test và biết rằng nó sinh tombstones.

### 5.2. UNSET note trong UPDATE vẫn giữ giá trị trước

~~~java
PreparedStatement update = session.prepare(
    "UPDATE it_lab.profile_by_id SET note = ?, score = ? " +
    "WHERE profile_id = ?");

BoundStatement withUnset = update.bind()
    .setInt(1, 8)     // score mới
    .setUuid(2, id);  // note (index 0) để UNSET

org.junit.jupiter.api.Assertions.assertFalse(withUnset.isSet(0));
session.execute(withUnset);

Row afterUnset = session.execute(
    session.prepare(
        "SELECT note, score FROM it_lab.profile_by_id WHERE profile_id = ?")
    .bind(id)).one();

org.junit.jupiter.api.Assertions.assertNotNull(afterUnset);
org.junit.jupiter.api.Assertions.assertEquals(
    "preserve-me", afterUnset.getString("note"));
org.junit.jupiter.api.Assertions.assertEquals(
    8, afterUnset.getInt("score"));
~~~

Vì `note` UNSET, không có mutation cho cột đó; `score` thay thành 8. Test tránh một UPDATE **chỉ toàn UNSET** vì cách server xử lý/no-op có thể khiến ta kiểm thử nhầm một lỗi khác với vấn đề cần học.

### 5.3. NULL note xóa giá trị mà không xóa score

~~~java
BoundStatement withNull = update.bind()
    .setToNull(0)      // note = NULL (delete column)
    .setUuid(2, id);   // score (index 1) vẫn UNSET

org.junit.jupiter.api.Assertions.assertTrue(withNull.isSet(0));
org.junit.jupiter.api.Assertions.assertFalse(withNull.isSet(1));
session.execute(withNull);

Row afterNull = session.execute(
    session.prepare(
        "SELECT note, score FROM it_lab.profile_by_id WHERE profile_id = ?")
    .bind(id)).one();

org.junit.jupiter.api.Assertions.assertNotNull(afterNull);
org.junit.jupiter.api.Assertions.assertTrue(afterNull.isNull("note"));
org.junit.jupiter.api.Assertions.assertEquals(
    8, afterNull.getInt("score"));
~~~

Ở đây hàng vẫn tồn tại do `score` còn giá trị; nếu chỉ có PK và xóa mọi cell, sự tồn tại của row marker/row result có thể có ngữ nghĩa riêng. **Không assert rằng hàng biến mất chỉ vì một non-key column được set NULL**.

### 5.4. Chuỗi rỗng không phải NULL

~~~java
BoundStatement empty = update.bind()
    .setString(0, "")
    .setUuid(2, id);
session.execute(empty);

Row r = session.execute(
    session.prepare("SELECT note FROM it_lab.profile_by_id " +
                    "WHERE profile_id=?").bind(id)).one();
org.junit.jupiter.api.Assertions.assertNotNull(r);
org.junit.jupiter.api.Assertions.assertFalse(r.isNull("note"));
org.junit.jupiter.api.Assertions.assertEquals("", r.getString("note"));
~~~

Đây là một regression test quan trọng cho REST/API clients gửi `""`, `null` hoặc bỏ field. Nếu ứng dụng normalize empty thành null trước khi bind, test tích hợp phải phản ánh **đúng contract** đó.

## 6. Những trường hợp NULL/UNSET không hợp lệ

### 6.1. Primary key phải có giá trị

Một hàng Cassandra được xác định bằng **đầy đủ primary key**. Không thể insert/update hàng có partition key `null`/UNSET; điều kiện WHERE trên khóa không thể dùng một giá trị chưa được bind.

~~~java
PreparedStatement insert = session.prepare(
    "INSERT INTO it_lab.profile_by_id (profile_id, note) " +
    "VALUES (?, ?)");

// profile_id không được bind, nghĩa là UNSET.
BoundStatement missingPk = insert.bind()
    .setString(1, "bad-key");

// profile_id được bind tường minh thành NULL.
BoundStatement nullPk = insert.bind()
    .setToNull(0)
    .setString(1, "bad-key");

// Với driver/server tương thích, các request này phải bị từ chối.
// Kiểm tra loại lỗi/cause đúng release; không so nguyên thông báo.
org.junit.jupiter.api.Assertions.assertThrows(
    com.datastax.oss.driver.api.core.servererrors.InvalidQueryException.class,
    () -> session.execute(missingPk));
org.junit.jupiter.api.Assertions.assertThrows(
    com.datastax.oss.driver.api.core.servererrors.InvalidQueryException.class,
    () -> session.execute(nullPk));
~~~

Nếu một driver/framework **chặn request trước khi gửi tới server**, class exception có thể khác; lúc đó test cần assert nguyên tắc “không thể gửi mutation hợp lệ với PK thiếu” và phân loại tại tầng đã từ chối, không ép class lỗi mù quáng. Cũng cần kiểm tra **clustering key** nếu bảng có khóa ghép; nó không được dùng NULL/UNSET khi CQL yêu cầu khóa đầy đủ cho mutation.

### 6.2. UNSET không phải wildcard trong WHERE

Sai:

~~~sql
-- WHERE profile_id = ? với bind UNSET KHÔNG phải tìm mọi profile.
SELECT note FROM it_lab.profile_by_id WHERE profile_id = ?;
~~~

Tương tự, `UNSET` không phải toán tử “IS NULL” cho tập dữ liệu. Cassandra không phải relational SQL engine có scan tùy ý theo NULL. Nếu app cần truy vấn “mọi profile chưa có note”, phải **thiết kế bảng/index theo truy vấn** hoặc pipeline offline; không bỏ bind marker `profile_id` rồi mong server lọc cho mình.

### 6.3. Row không tồn tại khác cột null

~~~java
UUID unknown = UUID.randomUUID();
Row missing = session.execute(
    session.prepare(
        "SELECT note, score FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(unknown)).one();

org.junit.jupiter.api.Assertions.assertNull(missing);
~~~

Với một hàng đang sống nhưng `note` đã bị xóa, có thể nhận `Row != null` và `row.isNull("note") == true`. Không viết:

~~~java
// SAI: row có thể là null do khóa không tồn tại.
// String note = result.one().getString("note");
~~~

Khi đọc primitive `int/boolean`, driver có thể dùng default 0/false cho CQL NULL; phải gọi `Row.isNull("score")` trước nếu nghiệp vụ cần phân biệt **không có giá trị** với **giá trị 0**.

### 6.4. Null trong tên cột và CQL identifier

Bind marker `?` dùng cho **giá trị**, không dùng để tham số hóa identifier (tên bảng, tên cột, tên keyspace). Một request chứa field name null hoặc tự do trong JSON không được phép ghép trực tiếp vào CQL string. Nếu ứng dụng cho phép patch nhiều field, dùng **allowlist thuộc tính và CQL fragments tĩnh**, sau đó bind giá trị bằng prepared statement.

## 7. Collection: list, set, map và phép thử round-trip

### 7.1. Ba collection khác nhau về ý nghĩa

| Kiểu | Java Driver getter | Ngữ nghĩa cần kiểm thử |
|---|---|---|
| `list<text>` | `row.getList("aliases", String.class)` | Có thứ tự; duplicate **được giữ** |
| `set<text>` | `row.getSet("tags", String.class)` | Không có duplicate; không phụ thuộc thứ tự iteration |
| `map<text,int>` | `row.getMap("quotas", String.class, Integer.class)` | Key duy nhất; so key-value, không phụ thuộc thứ tự iteration |

Collection phù hợp với **một tập nhỏ, có giới hạn**. Chúng không phải lựa chọn tốt để lưu mọi event của hàng triệu lần truy cập: collection thường được đọc như một đơn vị lớn, không hỗ trợ paging bên trong từng collection, có giới hạn kích thước và tombstone/latency riêng.

### 7.2. Ghi ba collection và đọc theo kiểu

~~~java
UUID id = UUID.randomUUID();

PreparedStatement ps = session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, tags, aliases, quotas) " +
    "VALUES (?, ?, ?, ?)");

Set<String> tags = Set.of("new", "priority");
List<String> aliases = List.of("Lan", "Lan", "LAN");
Map<String, Integer> quotas = Map.of("daily", 0, "monthly", 100);

BoundStatement bs = ps.bind()
    .setUuid(0, id)
    .setSet(1, tags, String.class)
    .setList(2, aliases, String.class)
    .setMap(3, quotas, String.class, Integer.class);
session.execute(bs);

Row r = session.execute(
    session.prepare(
        "SELECT tags, aliases, quotas FROM it_lab.profile_by_id " +
        "WHERE profile_id=?")
    .bind(id)).one();

org.junit.jupiter.api.Assertions.assertNotNull(r);
org.junit.jupiter.api.Assertions.assertEquals(
    tags, r.getSet("tags", String.class));
org.junit.jupiter.api.Assertions.assertEquals(
    aliases, r.getList("aliases", String.class));
org.junit.jupiter.api.Assertions.assertEquals(
    quotas, r.getMap("quotas", String.class, Integer.class));
~~~

**Vì sao kiểm tra theo equals:** Set và Map không hứa iteration order giống input; JUnit `assertIterableEquals` dựa vào thứ tự không phù hợp. List **có thứ tự** và duplicate hợp lệ, nên assert chính xác danh sách.

### 7.3. Null hoặc empty collection có thể cho cùng kết quả đọc

Cassandra và Java Driver **không bảo đảm có một trạng thái “collection empty” phân biệt rõ với “collection chưa có” trên mọi phiên bản/codec**. Driver built-in codecs thường giải mã collection không có giá trị thành **empty Java collection**; vậy:

~~~java
// Phải kiểm tra contract theo driver/version.
List<String> aliases = row.getList("aliases", String.class);
Set<String> tags = row.getSet("tags", String.class);

// Với built-in codecs, cả hai có thể là empty dù CQL column
// là empty hoặc không có giá trị. KHÔNG mặc nhiên assert null.
org.junit.jupiter.api.Assertions.assertTrue(aliases.isEmpty());
org.junit.jupiter.api.Assertions.assertTrue(tags.isEmpty());
~~~

**Quan trọng:** đoạn trên chỉ đúng khi test đã ghi cột theo tình huống **được kỳ vọng rỗng** (ví dụ row mới với collection rỗng); không dùng nó với dataset ngẫu nhiên. `row.isNull("tags")` có thể phản ánh trạng thái wire-level khác tùy represention và frozen/multi-cell, nhưng **không tạo ra một business-level distinction ổn định** giữa “chưa gửi” và “đã gửi empty”.

Để kiểm thử phân biệt ý định của HTTP PATCH:

1. Ghi một tập tags đang có (ví dụ `{"a","b"}`).
2. Gửi request **field absent** → service bind UNSET → tags phải giữ nguyên.
3. Gửi request **explicit empty** → service dùng mutation thích hợp để làm trống collection → đọc ra empty.
4. Gửi **explicit null** → service xóa cột theo contract → đọc ra có thể cũng empty; so với state marker nếu cần phân biệt.

Không assert “CQL empty” và “CQL null” luôn có hai giá trị Java khác nhau sau round-trip.

### 7.4. CQL collection không nhận null elements

Một collection CQL **không có phần tử null hợp lệ**. Đừng nhầm **cả cột = NULL** với **một phần tử trong list/map = NULL**:

~~~text
tags = NULL       -> tác động ở mức cột, có thể xóa dữ liệu
tags = {'a','b'}  -> set hợp lệ
tags = {'a',NULL} -> không phải set CQL hợp lệ
aliases = [NULL]  -> không phải list CQL hợp lệ
quotas = {'x':NULL} -> không phải map có giá trị hợp lệ
~~~

Test âm cần dùng một `List`/`Map` Java **có chứa null thực**, nhưng class exception có thể phát sinh ở codec trước khi gửi network hoặc từ server. Assertion nên xác nhận mutation bị từ chối và **row cũ không thay đổi**, không so thông báo lỗi từng ký tự.

### 7.5. Set duplicate, map duplicate key, list duplicate

| Input | Kỳ vọng kiểm thử | Giải thích |
|---|---|---|
| `Set.of("a","a")` | Java ném exception trước khi bind | Java immutable factory không nhận duplicate |
| `new HashSet<>(List.of("a","a"))` | Kết quả một phần tử | Set loại duplicate |
| `List.of("a","a")` | Hai phần tử | List giữ duplicate |
| Map put cùng key hai lần | Chỉ có giá trị sau cùng trong Java Map | Map không có duplicate key |

**Không** dùng input Java bị constructor ném exception rồi báo đó là “Cassandra đã từ chối duplicate”. Phải phân biệt lỗi tạo collection ở Java, lỗi codec và lỗi từ server.

## 8. Collection mutations, frozen và idempotency

### 8.1. Thêm/xóa phần tử thay vì ghi lại toàn bộ

Với non-frozen collection:

~~~sql
UPDATE it_lab.profile_by_id
SET tags = tags + {'verified'}
WHERE profile_id = 11111111-1111-4111-8111-111111111111;

UPDATE it_lab.profile_by_id
SET tags = tags - {'obsolete'}
WHERE profile_id = 11111111-1111-4111-8111-111111111111;

UPDATE it_lab.profile_by_id
SET quotas['daily'] = 42
WHERE profile_id = 11111111-1111-4111-8111-111111111111;

UPDATE it_lab.profile_by_id
SET aliases = aliases + ['new-alias']
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
~~~

Những mutation này yêu cầu một hàng/partition hợp lệ; nếu chưa có row, Cassandra có thể upsert tùy câu lệnh. Thêm một giá trị vào set có semantics khác **append list**:

- Thêm cùng một phần tử vào set thường không làm có hai bản giống nhau.
- Append list cùng một giá trị hai lần **có thể lưu hai phần tử**, nên retry sau timeout có thể tạo duplicate.
- Thêm phần tử map theo key sẽ cập nhật key đó; write timestamp/concurrency quyết định giá trị thắng.
- Một số thao tác list cần read-before-write, có tác động latency đáng kể.

### 8.2. Bài test idempotency nhỏ

~~~java
UUID id = UUID.randomUUID();
session.execute(session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, tags, aliases) VALUES (?, ?, ?)")
    .bind(id, Set.of("a"), List.of("a")));

PreparedStatement addToSet = session.prepare(
    "UPDATE it_lab.profile_by_id SET tags = tags + ? " +
    "WHERE profile_id = ?");
PreparedStatement appendList = session.prepare(
    "UPDATE it_lab.profile_by_id SET aliases = aliases + ? " +
    "WHERE profile_id = ?");

// Chạy hai lần có chủ đích để quan sát khác biệt.
session.execute(addToSet.bind(Set.of("b"), id));
session.execute(addToSet.bind(Set.of("b"), id));
session.execute(appendList.bind(List.of("b"), id));
session.execute(appendList.bind(List.of("b"), id));

Row r = session.execute(session.prepare(
    "SELECT tags, aliases FROM it_lab.profile_by_id " +
    "WHERE profile_id=?").bind(id)).one();

org.junit.jupiter.api.Assertions.assertEquals(
    Set.of("a","b"), r.getSet("tags", String.class));
org.junit.jupiter.api.Assertions.assertEquals(
    List.of("a","b","b"), r.getList("aliases", String.class));
~~~

Các lần ghi có thể xảy ra với timestamps khác nhau khi chạy tuần tự. Nếu test có clock/timestamp override, phải hiểu conflict resolution. **Không** lấy việc set chống trùng làm lý do bật retry vô hạn: có thể còn TTL, side effects và multiple-replica failure modes.

### 8.3. Frozen collection khác non-frozen

Với:

~~~sql
CREATE TABLE it_lab.frozen_collection_by_id (
  id uuid PRIMARY KEY,
  tags frozen<set<text>>
);
~~~

`frozen<set<text>>` lưu collection như **một giá trị**. Update “thêm đúng một phần tử” cần read/modify/write toàn bộ collection hoặc schema khác; không thể dựa vào cùng operator partial mutation như non-frozen collection. Nếu có concurrent writers, whole-value replacement có thể làm lost update. Test frozen/non-frozen phải tạo hai bảng/cột khác nhau và không so latency chỉ với một row.

### 8.4. Nested collection, UDT và GenericType

Khi có nested generics, Java Driver không thể mô tả bằng `String.class` đơn thuần:

~~~java
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

GenericType<Set<List<String>>> nested =
    new GenericType<Set<List<String>>>() {};

// Với schema CQL nested phù hợp và được frozen theo yêu cầu:
// Set<List<String>> value = row.get("nested_column", nested);
~~~

Lập test riêng cho:

- Type không khớp: Java `Map<String, Long>` không tự thành `map<text,int>`.
- Nested element codec, frozen inner types và key/value của map.
- Collection rất lớn: test **giới hạn đầu vào/validation** thay vì nạp hàng trăm MB vào một row.
- Biến đổi collection theo TTL; TTL cho từng cell/element trong non-frozen collection không nên bị diễn giải như một deadline duy nhất của whole collection.

## 9. UDT: tạo, ghi, đọc và NULL fields

### 9.1. UDT có schema, không phải map tùy ý

`it_lab.address_info` có đúng ba trường theo thứ tự schema:

~~~sql
CREATE TYPE it_lab.address_info (
  street text,
  city text,
  postal_code text
);
~~~

`UdtValue` được tạo từ metadata của Cassandra/Driver, **không tự xây UserDefinedType bằng fields tùy ý** vì schema UDT bao gồm tên và thứ tự các trường. Nếu dùng object của một CqlSession khác hoặc đã đổi schema, phải xác minh type attachment/metadata/codec.

### 9.2. Tạo UdtValue từ schema metadata

~~~java
import com.datastax.oss.driver.api.core.data.UdtValue;
import com.datastax.oss.driver.api.core.type.UserDefinedType;

UserDefinedType addressType = session.getMetadata()
    .getKeyspace("it_lab")
    .flatMap(ks -> ks.getUserDefinedType("address_info"))
    .orElseThrow(() -> new IllegalStateException("UDT not loaded"));

UdtValue home = addressType.newValue()
    .setString("street", "12 Lê Lợi")
    .setString("city", "Đà Nẵng")
    .setString("postal_code", "550000");

PreparedStatement write = session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, home) VALUES (?, ?)");

UUID id = UUID.randomUUID();
session.execute(write.bind().setUuid(0, id).setUdtValue(1, home));

Row r = session.execute(session.prepare(
    "SELECT home FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id)).one();

org.junit.jupiter.api.Assertions.assertNotNull(r);
UdtValue actual = r.getUdtValue("home");
org.junit.jupiter.api.Assertions.assertNotNull(actual);
org.junit.jupiter.api.Assertions.assertEquals(
    "Đà Nẵng", actual.getString("city"));
org.junit.jupiter.api.Assertions.assertEquals(
    "550000", actual.getString("postal_code"));
~~~

`home` trong schema là `frozen<address_info>`; lúc ghi, toàn bộ object được coi là một giá trị. `UdtValue` mặc định ở Driver 4.x là **mutable**, trong khi `BoundStatement` immutable. Đừng dùng chung một mutable UdtValue giữa các luồng đang ghi khác nhau mà không sao chép.

### 9.3. UDT thiếu field sẽ đọc null

~~~java
UdtValue partial = addressType.newValue()
    .setString("city", "Huế");
// Không set street và postal_code.

UUID id2 = UUID.randomUUID();
session.execute(write.bind().setUuid(0, id2).setUdtValue(1, partial));

UdtValue readBack = session.execute(session.prepare(
    "SELECT home FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id2)).one().getUdtValue("home");

org.junit.jupiter.api.Assertions.assertEquals(
    "Huế", readBack.getString("city"));
org.junit.jupiter.api.Assertions.assertTrue(readBack.isNull("street"));
org.junit.jupiter.api.Assertions.assertTrue(readBack.isNull("postal_code"));
~~~

Một UDT literal CQL có thể bỏ field; phần không được cung cấp có giá trị NULL. **Đừng xem việc thiếu field bên trong frozen UDT như “UNSET cột ngoài”**: ghi cả UDT mới sẽ thay thế whole value và có thể làm mất fields cũ. Vì thế test update partial DTO → frozen UDT cần xác định “replace” hay “merge” ở tầng nghiệp vụ.

## 10. Frozen UDT so với non-frozen UDT

### 10.1. Khác nhau ngay ở đơn vị mutation

| Thuộc tính | `home frozen<address_info>` | `office address_info` |
|---|---|---|
| Lưu trữ | Một giá trị được coi là toàn bộ UDT | Các fields có thể là cells riêng |
| Update `column.city = ?` | **Không** hỗ trợ partial field update | Hỗ trợ field update theo CQL |
| Ghi toàn bộ object | Replace whole UDT, có thể làm mất field không được gửi | Có thể tác động các fields được set theo statement |
| TTL/tombstone | Whole-value semantics | Có thể áp vào field/cell phù hợp |
| Concurrency | Whole-value replacement dễ lost update nếu client dùng DTO cũ | Field-specific write giúp giảm xung đột ngoài ý muốn, không thành ACID transaction cross-partition |

### 10.2. Cập nhật một field của non-frozen UDT

~~~java
UUID id = UUID.randomUUID();
UserDefinedType addressType = session.getMetadata()
    .getKeyspace("it_lab")
    .flatMap(ks -> ks.getUserDefinedType("address_info"))
    .orElseThrow();

UdtValue office = addressType.newValue()
    .setString("street", "1 Main St")
    .setString("city", "Hà Nội")
    .setString("postal_code", "100000");

session.execute(session.prepare(
    "INSERT INTO it_lab.profile_by_id (profile_id, office) " +
    "VALUES (?, ?)").bind(id, office));

PreparedStatement changeCity = session.prepare(
    "UPDATE it_lab.profile_by_id SET office.city = ? " +
    "WHERE profile_id = ?");
session.execute(changeCity.bind("Hải Phòng", id));

UdtValue after = session.execute(session.prepare(
    "SELECT office FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id)).one().getUdtValue("office");

org.junit.jupiter.api.Assertions.assertEquals(
    "Hải Phòng", after.getString("city"));
org.junit.jupiter.api.Assertions.assertEquals(
    "1 Main St", after.getString("street"));
org.junit.jupiter.api.Assertions.assertEquals(
    "100000", after.getString("postal_code"));
~~~

Với **frozen UDT**, query tương tự `SET home.city = ?` phải bị từ chối. Hãy viết test âm tách biệt và chỉ assert lỗi semantic, không phụ thuộc message:

~~~java
org.junit.jupiter.api.Assertions.assertThrows(
    com.datastax.oss.driver.api.core.servererrors.InvalidQueryException.class,
    () -> session.execute(
        "UPDATE it_lab.profile_by_id SET home.city = 'Huế' " +
        "WHERE profile_id = 11111111-1111-4111-8111-111111111111"));
~~~

Test âm có thể nhận lỗi ở bước prepare hoặc execute tùy cách API gọi, vì vậy đặt **toàn bộ lời gọi** vào lambda assertion.

### 10.3. UDT evolution và mapping compatibility

Nếu thay UDT bằng:

~~~sql
ALTER TYPE it_lab.address_info ADD country text;
~~~

test phải xác minh:

1. Driver **schema metadata** được cập nhật trước khi bind/đọc object với field mới.
2. Data cũ không có `country` được đọc theo semantics tương thích/null.
3. Code mới biết field `country` nhưng code cũ vẫn hoạt động khi rollback/chạy hỗn hợp version, theo protocol/schema hỗ trợ.
4. UDT thứ tự field/name không được tự giả định hoặc tự xây bản detached không tương thích với schema.
5. Có quy trình migration/version pin; tránh `ALTER TYPE` trên shared schema giữa nhiều test classes chạy song song.

**Không thực hiện ALTER TYPE trong test cơ bản dùng chung `profile_by_id`**, vì nó có thể làm prepared statement và các tests đang chạy phụ thuộc schema trước đó bị ảnh hưởng. Dùng **keyspace hoặc container riêng** cho schema-evolution tests.

## 11. Các giá trị biên của số nguyên, decimal và boolean

### 11.1. CQL type và Java type phải tương ứng chính xác

| CQL type | Java Driver type/API | Test biên |
|---|---|---|
| `tinyint` | `byte` / `setByte` / `getByte` | -128, 0, 127; 128 **ngoài phạm vi** |
| `smallint` | `short` / `setShort` / `getShort` | -32768, 32767; 32768 **ngoài phạm vi** |
| `int` | `int` / `setInt` / `getInt` | `Integer.MIN_VALUE/MAX_VALUE` |
| `bigint` | `long` / `setLong` / `getLong` | `Long.MIN_VALUE/MAX_VALUE` |
| `varint` | `BigInteger` / `setBigInteger` / `getBigInteger` | Số lớn hơn `Long.MAX_VALUE` |
| `decimal` | `BigDecimal` / `setBigDecimal` / `getBigDecimal` | Scale, âm, 0, phần thập phân dài |
| `boolean` | `boolean` / `setBoolean` / `getBoolean` | `true/false` và phân biệt NULL bằng `isNull` |

**Không dùng `int` Java để nhận một CQL `varint`**. Việc conversion thủ công bằng `longValue()` có thể truncate khi vượt miền giá trị. Đừng so decimal bằng `double` nếu nghiệp vụ cần tính chính xác tiền hoặc định lượng.

### 11.2. Round-trip nhiều kiểu biên trong một hàng

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.UUID;

UUID id = UUID.randomUUID();
BigInteger huge = new BigInteger("18446744073709551617000");
BigDecimal amount = new BigDecimal("-1234567890.000100");

PreparedStatement write = session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, priority_tiny, short_value, score, " +
    "long_value, huge_value, amount, active) " +
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)");

BoundStatement bs = write.bind()
    .setUuid(0, id)
    .setByte(1, Byte.MIN_VALUE)
    .setShort(2, Short.MAX_VALUE)
    .setInt(3, Integer.MIN_VALUE)
    .setLong(4, Long.MAX_VALUE)
    .setBigInteger(5, huge)
    .setBigDecimal(6, amount)
    .setBoolean(7, false);
session.execute(bs);

Row r = session.execute(session.prepare(
    "SELECT priority_tiny, short_value, score, long_value, " +
    "huge_value, amount, active FROM it_lab.profile_by_id " +
    "WHERE profile_id=?").bind(id)).one();

org.junit.jupiter.api.Assertions.assertNotNull(r);
org.junit.jupiter.api.Assertions.assertEquals(
    Byte.MIN_VALUE, r.getByte("priority_tiny"));
org.junit.jupiter.api.Assertions.assertEquals(
    Short.MAX_VALUE, r.getShort("short_value"));
org.junit.jupiter.api.Assertions.assertEquals(
    Integer.MIN_VALUE, r.getInt("score"));
org.junit.jupiter.api.Assertions.assertEquals(
    Long.MAX_VALUE, r.getLong("long_value"));
org.junit.jupiter.api.Assertions.assertEquals(
    huge, r.getBigInteger("huge_value"));
org.junit.jupiter.api.Assertions.assertEquals(
    0, amount.compareTo(r.getBigDecimal("amount")));
org.junit.jupiter.api.Assertions.assertFalse(r.getBoolean("active"));
org.junit.jupiter.api.Assertions.assertFalse(r.isNull("active"));
~~~

`BigDecimal.compareTo` so giá trị số; `BigDecimal.equals` còn xét **scale**. Nếu business contract yêu cầu scale cố định, thêm assertion `actual.scale()` sau khi xác minh Cassandra/codec giữ scale đúng, không chỉ dùng compareTo. Khi hiển thị JSON, serialization của BigDecimal có thể tạo ký pháp khác; cần test cả HTTP mapping.

### 11.3. NULL cho số hoặc boolean không phải 0/false

~~~java
// Giả sử score và active chưa được ghi:
Row r = session.execute(session.prepare(
    "SELECT score, active FROM it_lab.profile_by_id " +
    "WHERE profile_id=?").bind(id)).one();

// Chỉ khi id thật sự có một hàng đang sống, r mới khác null.
if (r != null) {
    Integer score = r.isNull("score") ? null : r.getInt("score");
    Boolean active = r.isNull("active") ? null : r.getBoolean("active");
}
~~~

Với Java primitive getter, một số CQL NULL có thể chuyển thành giá trị mặc định (0/false); **phải kiểm tra `Row.isNull`** khi business phân biệt “không rõ” với false/0. Không viết assertion `getInt()==0` để chứng minh cột lưu số 0 nếu chưa kiểm tra `isNull`.

### 11.4. Test overflow và type mismatch phải đo ở đúng tầng

Ví dụ CQL literal `priority_tiny = 128` nằm ngoài miền `tinyint`; hệ thống nên từ chối ở parser/validation. Nếu Java lập biểu thức `(byte) 128`, nó **đã biến thành -128 trước khi tới driver** — một integration test nhận -128 không chứng minh Cassandra chấp nhận 128.

Thử:

~~~java
// Java cast đã overflow trước khi bind; KHÔNG dùng để test server range.
byte wrapped = (byte) 128; // -128

// Test server-side CQL literal, dùng UUID hợp lệ và một bảng lab:
// INSERT INTO it_lab.profile_by_id
//   (profile_id, priority_tiny)
// VALUES (11111111-1111-4111-8111-111111111111, 128);
// Kỳ vọng bị từ chối do giá trị không fit tinyint.
~~~

Tương tự, Java BigInteger rất lớn **vẫn hợp lệ với CQL varint** nếu nằm trong giới hạn thực của codec/storage, nhưng không thể map sang `long` bằng cách ép kiểu. Test cần tách **server acceptance**, **driver codec** và **DTO serialization**.

## 12. Kiểu thời gian, Unicode, blob và inet

### 12.1. Timestamp: hiểu đơn vị và precision

CQL `timestamp` được biểu diễn theo **milli-giây** kể từ Unix epoch, trong khi Java `Instant` có thể có **nano-giây**. Một Instant có precision cao hơn có thể bị làm tròn/cắt về milli-giây khi ghi qua codec.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;

UUID id = UUID.randomUUID();
Instant withNanos = Instant.parse(
    "1969-12-31T23:59:59.123456789Z");
Instant expectedStored =
    Instant.ofEpochMilli(withNanos.toEpochMilli());

LocalDate leapDay = LocalDate.of(2000, 2, 29);
LocalTime lastNano = LocalTime.of(23, 59, 59, 999_999_999);

PreparedStatement ps = session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, created_at, event_day, event_time) " +
    "VALUES (?, ?, ?, ?)");
session.execute(ps.bind()
    .setUuid(0, id)
    .setInstant(1, withNanos)
    .setLocalDate(2, leapDay)
    .setLocalTime(3, lastNano));

Row r = session.execute(session.prepare(
    "SELECT created_at, event_day, event_time " +
    "FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id)).one();

org.junit.jupiter.api.Assertions.assertEquals(
    expectedStored, r.getInstant("created_at"));
org.junit.jupiter.api.Assertions.assertEquals(
    leapDay, r.getLocalDate("event_day"));
org.junit.jupiter.api.Assertions.assertEquals(
    lastNano, r.getLocalTime("event_time"));
~~~

**Đặc biệt trước 1970:** dùng `toEpochMilli()` thay vì `Instant.getEpochSecond() * 1000 + getNano()/1_000_000` viết thủ công không cẩn thận với số âm. `timestamp` lưu một instant tuyệt đối, **không có timezone ID**: timezone là vấn đề ở parsing/hiển thị phía ứng dụng.

### 12.2. Phân biệt date, time và timestamp

| CQL type | Java type | Điều cần test |
|---|---|---|
| `date` | `LocalDate` | Leap day, pre-1970, ngày không có timezone |
| `time` | `LocalTime` | 00:00:00, 23:59:59.999999999, nanoseconds |
| `timestamp` | `Instant` | Before/after epoch, millisecond precision, UTC display |
| `duration` | `CqlDuration` | **Months/days/nanos**, không mặc nhiên đổi thành một Duration giây cố định |
| `timeuuid` | UUID phiên bản 1 | Không lấy `UUID.randomUUID()` v4 rồi bind như một timeuuid |

Với `duration`, một tháng không luôn bằng 30 ngày. Nếu API Java dùng `java.time.Duration` để biểu diễn nghiệp vụ “1 tháng”, phải thiết kế converter rõ, không coi tất cả durations là mili-giây cố định. Với `timeuuid`, kiểm thử version/ordering tương thích timeuuid chứ không so lexical UUID string.

### 12.3. Unicode và chuỗi rỗng

~~~java
import java.text.Normalizer;

String composed = "Café 🚀";
String decomposed = "Cafe\u0301 🚀";

org.junit.jupiter.api.Assertions.assertNotEquals(
    composed, decomposed);  // Khác chuỗi Unicode code points.

String normalized =
    Normalizer.normalize(decomposed, Normalizer.Form.NFC);
org.junit.jupiter.api.Assertions.assertEquals(composed, normalized);
~~~

Khi round-trip `text/varchar`:

- Kiểm tra tiếng Việt có dấu, emoji (surrogate pairs trong Java), ký tự kết hợp, độ dài 0 và chuỗi nhiều byte UTF-8.
- Không giả định Cassandra/codec **tự normalize Unicode** theo NFC/NFD hay thực hiện so sánh case-insensitive.
- Nếu business yêu cầu username không phân biệt dấu/case, normalize/case-folding và thiết kế key riêng **trước khi bind**; giữ một policy nhất quán cho toàn hệ thống.
- Tránh so `String.length()` với số Unicode code points hoặc byte UTF-8: ba đơn vị khác nhau.

### 12.4. Blob: ByteBuffer có position và limit

~~~java
import java.nio.ByteBuffer;
import java.util.Arrays;

byte[] payload = new byte[] {0, 1, 0, (byte) 0xFF};
ByteBuffer original = ByteBuffer.wrap(payload);
UUID id = UUID.randomUUID();

session.execute(session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, blob_value) VALUES (?, ?)")
    .bind(id, original));

Row r = session.execute(session.prepare(
    "SELECT blob_value FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id)).one();

ByteBuffer buffer = r.getByteBuffer("blob_value");
org.junit.jupiter.api.Assertions.assertNotNull(buffer);
ByteBuffer copy = buffer.duplicate();
byte[] actual = new byte[copy.remaining()];
copy.get(actual);

org.junit.jupiter.api.Assertions.assertArrayEquals(payload, actual);
~~~

`ByteBuffer.get(...)` thay đổi **position** của buffer; dùng `duplicate()` hoặc `asReadOnlyBuffer()` khi nhiều code cùng kiểm tra. Không ép binary thành UTF-8 text rồi so string nếu payload chứa zero bytes hoặc byte không hợp lệ.

### 12.5. inet và DNS

~~~java
import java.net.InetAddress;

InetAddress localhostIPv4 = InetAddress.getByAddress(
    new byte[] {127, 0, 0, 1});

UUID id = UUID.randomUUID();
session.execute(session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, source_ip) VALUES (?, ?)")
    .bind(id, localhostIPv4));

Row r = session.execute(session.prepare(
    "SELECT source_ip FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id)).one();
org.junit.jupiter.api.Assertions.assertEquals(
    localhostIPv4, r.getInetAddress("source_ip"));
~~~

Dùng `InetAddress.getByAddress` để test không phụ thuộc DNS. Nếu kiểm tra IPv6, dùng 16 byte chuẩn. Không assert string render IP luôn giống input (IPv6 có nhiều biểu diễn hợp lệ). Nếu API nhận hostname, việc DNS resolve là logic riêng phải có test/deterministic stub.

## 13. Spring Data, Mapper và hợp đồng null ở tầng ứng dụng

### 13.1. Hai đường mapping phải test riêng

**Java Driver trực tiếp:** test nhìn thấy rõ `bind()`/`setToNull()`/`unset()` và `Row`. **Spring Data Cassandra / Java Driver Mapper:** có tầng converter/DAO có thể chọn chiến lược null-saving khác. Một test pass ở raw driver **không chứng minh** entity mapping sẽ xử lý `null` như API PATCH mong muốn.

Ví dụ Apache Java Driver Mapper 4.19 có `NullSavingStrategy`:

| Mapper strategy | Khi entity property null | Tác dụng |
|---|---|---|
| `DO_NOT_SET` (default của Mapper annotations nếu chưa override) | Không gọi setter cho bind variable | Cột được UNSET; không xóa giá trị cũ |
| `SET_TO_NULL` | Gọi setter với null | CQL NULL; có thể tạo tombstone và xóa giá trị cũ |

~~~java
// Chỉ minh họa annotation của Java Driver Mapper 4.x:
//
// @Dao
// interface ProfileDao {
//     @Update(nullSavingStrategy = NullSavingStrategy.SET_TO_NULL)
//     void updateAllowNullDelete(ProfileEntity entity);
// }
~~~

**Đừng đánh đồng với Spring Data Cassandra:** Spring Data `CassandraTemplate` có converter/write options/version-specific behavior riêng. Hãy kiểm thử **đúng code path** mà service sử dụng, ví dụ:

1. Seed cột `note="old"` bằng raw CQL.
2. Gọi repository/`CassandraOperations.update(entity)` với `note=null`.
3. Đọc lại bằng raw CQL để thấy note giữ nguyên hay bị xóa.
4. Đổi policy/option nếu có yêu cầu contract; ghi rõ tên config/version trong test.
5. Đọc lại TTL/WRITETIME khi cần chứng minh không cập nhật nhầm cột.

### 13.2. PATCH JSON phải giữ được ba trạng thái

Nếu DTO dùng một `String note` đơn:

~~~json
{}
~~~

và:

~~~json
{ "note": null }
~~~

có thể đều tạo `note=null` trong Java object sau deserialize; **mất thông tin presence**. Để hỗ trợ PATCH:

- Dùng wrapper/tri-state field presence, JsonNode hoặc cấu trúc định nghĩa “được cung cấp”.
- Absent → **UNSET** trong prepared UPDATE.
- Explicit null → **setToNull** khi business muốn clear.
- String có giá trị (kể cả empty) → **setString**.
- Viết HTTP → CQL integration test cho cả ba case; không chỉ test DTO parsing.

### 13.3. Optional không phải toàn bộ giải pháp

`Optional.empty()` không tự phân biệt field absent và explicit null khi serializer/framework biến cả hai thành empty. Nếu business có ba trạng thái, dùng **hai thông tin**: presence flag và value, hoặc một algebraic type rõ ràng:

~~~text
PatchField =
  Absent
  | Clear
  | Set(value)

mapping:
  Absent -> BoundStatement.unset(...)
  Clear  -> BoundStatement.setToNull(...)
  Set(x) -> BoundStatement.setXxx(...)
~~~

Trong môi trường reactive/async, `BoundStatement` immutable và an toàn khi truyền giữa luồng theo semantics driver; nhưng **builder** và một số `UdtValue` mặc định mutable, không dùng chung để chỉnh sửa đồng thời.

### 13.4. Không test tombstone bằng cách đếm trực tiếp file

Nếu muốn kiểm tra tác động null-saving tới hiệu năng, dùng thêm **soak/integration benchmark riêng**:

- Tạo nhiều updates có explicit NULL so với UNSET.
- Đo tombstones scanned/compaction theo công cụ phù hợp release.
- So SSTable footprint và read p95/p99 sau thời gian đủ dài.
- Giữ replication/repair/TTL/GC grace và dataset cố định.

Không dùng một test JUnit với 2 hàng rồi khẳng định “NULL tạo chính xác một tombstone nhìn thấy ngay trong SSTable”; storage engine và compaction không cung cấp sự đơn giản đó.

## 14. Assertions đúng tầng: codec, CQL, server và business

### 14.1. Ma trận lỗi kiểm thử

| Tình huống | Có thể bị từ chối ở đâu? | Assertion nên đặt |
|---|---|---|
| `UUID.randomUUID()` bind vào `timeuuid` | Driver codec/serialization hoặc server | Error type và row không bị ghi |
| Java `byte` cast từ 128 | **Java** đã overflow | Test validation ở HTTP/DTO trước khi cast |
| NULL trong collection element | Driver codec hoặc server | Reject input và không sửa row cũ |
| UDT field name không tồn tại | Driver setter hoặc server | Reject và schema compatibility check |
| `home.city` trên frozen UDT | Server CQL validation | `InvalidQueryException`/semantic rejection |
| PK NULL hoặc UNSET | Driver/server | Không chấp nhận mutation hợp lệ |
| Query thiếu partition key | Server query validation | Không bật ALLOW FILTERING để “cho qua” |
| Giá trị bigint lưu vào int cột | Codec/type mismatch hoặc server | Không truncate dữ liệu âm thầm |
| Timeout/mất ACK khi ghi | Driver/server/network | **UNKNOWN outcome**, không giả định rollback |
| LWT IF không thỏa | CQL trả `[applied]=false` | **Không phải exception**; check `wasApplied()` |

**Lỗi “mang tính nghiệp vụ” và “lỗi hạ tầng” phải khác nhau:** LWT false là conflict có điều kiện; timeout có thể xảy ra sau khi ghi đã áp dụng. Nếu test injection timeout trên UPDATE collection không idempotent, phải reconcile và kiểm tra duplicates, không tự retry vô hạn.

### 14.2. Kiểm tra kết quả sau lỗi

Mẫu test âm:

~~~text
given: row note='stable', score=7
when: send invalid mutation (NULL PK / invalid collection element)
then: request rejected
and: SELECT by valid PK still returns note='stable', score=7
and: no partial business side effects are claimed
~~~

Không assert chỉ exception rồi bỏ qua tính đúng dữ liệu. Với multi-partition batch/ETL, một lỗi có thể để lại những thành phần đã áp dụng theo semantics khác; cần test transaction scope riêng.

### 14.3. Không “snapshot” output cqlsh để test

`cqlsh` hiển thị `null`, collection ordering, timestamp và số thập phân theo formatting; output có thể thay đổi giữa phiên bản. Tốt hơn:

- Dùng typed getters `getInt/getBigDecimal/getList/getUdtValue/getInstant`.
- Dùng `isNull` cho scalar primitive.
- Với binary, so byte arrays không so render hex string trừ khi contract đòi.
- Với map/set, so equality theo phần tử, không theo thứ tự.
- Với BigDecimal, tách equality số học và scale business.
- Với time, so đúng precision và timezone semantics.

### 14.4. Kiểm soát race, TTL và timestamp

Một test kiểu:

~~~text
UPDATE note='A'
UPDATE note=NULL
SELECT note expected NULL
~~~

chỉ đáng tin nếu cả hai mutations được thực thi và quan sát theo thứ tự có kiểm soát, cùng clock/timestamp semantics. Cassandra dùng timestamps để giải quyết xung đột; nếu tự đặt cùng timestamp cho hai mutations, kết quả có thể không phản ánh thứ tự câu lệnh. Không cấu hình write timestamp thủ công tùy tiện trong bộ test NULL/UNSET.

Với TTL, test nên dùng fake clock/service-level abstraction khi có thể; **không ngủ chính xác một giây rồi khẳng định TTL hết** vì scheduling, network và reconciliation làm test flaky. Nếu cần test TTL thực, dùng timeout window có biên và kiểm tra eventually với deadline có giới hạn.

## 15. Bảng testcase đầy đủ và quản lý dữ liệu

| Nhóm | Input | Kết quả kỳ vọng | Điều kiện để assert |
|---|---|---|---|
| NULL vs UNSET | note UNSET, score=8 | note giữ nguyên, score=8 | Seed note trước |
| NULL vs UNSET | note NULL, score UNSET | note null, score không đổi | Row còn sống |
| Scalar empty | note = `""` | note không null, length 0 | Không normalize ở service |
| PK absent | profile_id UNSET/NULL | Request bị từ chối | Driver/server có validation |
| Collection set | `{"a","b"}` | Không duplicate, không quan tâm thứ tự | Built-in codec |
| Collection list | `["a","a"]` | Giữ hai phần tử và thứ tự | Chỉ mutation bình thường |
| Collection map | `{"a":0,"b":-1}` | So đúng keys/values | CQL map<text,int> |
| Collection empty | `[]`/`{}` | Getter có thể trả empty, không chắc phân biệt null | Ghi rõ codec/version |
| Collection invalid | Element null | Reject và row cũ giữ nguyên | Check lỗi phù hợp |
| Collection retry | Append list hai lần | Duplicate là khả năng có thật | Không có concurrent writers |
| Frozen UDT | Ghi một UdtValue đầy đủ | Round-trip field names/types | Metadata type đúng |
| Frozen UDT | SET home.city | Reject | Frozen field mutation không hỗ trợ |
| Non-frozen UDT | SET office.city | Chỉ city đổi, fields khác giữ | Seed đủ fields |
| UDT partial | Không set street/postal_code | Read null cho fields thiếu | Whole UDT được ghi |
| Tinyint/smallint | Min/max | Typed round-trip chính xác | Không cast trước khi test |
| Varint/decimal | > Long.MAX, scale lớn | BigInteger/BigDecimal chính xác | Không chuyển qua double |
| Timestamp | Pre-epoch + nanoseconds | Chính xác đến milliseconds | Codec release tương ứng |
| Date/time | Leap day, cuối ngày nano | LocalDate/LocalTime đúng | Test không dùng timezone |
| Unicode | NFC/NFD, tiếng Việt, emoji | Giữ text được bind, không auto normalize | So code points khi cần |
| Blob | Chứa 0x00/0xFF | Byte arrays bằng nhau | ByteBuffer duplicate |
| Inet | IPv4/IPv6 bytes | Address bằng nhau | Không phụ thuộc DNS |

### 15.1. Test isolation và cleanup

- Mỗi test dùng một `UUID.randomUUID()` riêng; nếu cần test order/retry với cùng PK, chỉ dùng nó **bên trong một test**.
- Không dùng cùng UUID hard-coded ở các test classes chạy song song.
- Nên tạo schema một lần cho container và dùng fixtures riêng; tránh tạo/drop type liên tục giữa nhiều concurrent tests.
- Có thể giữ container theo class để giảm startup time; không bật reuse container giữa CI runs khi không có quản lý state.
- Cleanup cuối test thường có thể để container lifecycle đảm nhiệm; DELETE mỗi row tạo tombstones và có thể làm méo benchmark.
- Không chia sẻ prepared statement builder hay mutable UdtValue khi nhiều thread cùng tạo mutation.
- Ghi tên image, version Cassandra, driver, Testcontainers, OS/architecture, native protocol và test seed trong báo cáo lỗi.

## 16. Một bài JUnit tích hợp hoàn chỉnh về NULL/UNSET

Các đoạn trước được viết theo từng thí nghiệm. Dưới đây là **một phương thức test độc lập** có thể đặt bên trong class `CassandraTypesIT` của mục 3 (sau khi `@BeforeAll` đã tạo keyspace, type, table ở mục 4):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

// Bên trong CassandraTypesIT, đã có field "session":
@Test
void unsetPreservesValueButNullDeletesIt() {
    UUID id = UUID.randomUUID();

    PreparedStatement seed = session.prepare(
        "INSERT INTO it_lab.profile_by_id " +
        "(profile_id, note, score) VALUES (?, ?, ?)");
    session.execute(seed.bind(id, "initial", 5));

    PreparedStatement patch = session.prepare(
        "UPDATE it_lab.profile_by_id " +
        "SET note = ?, score = ? WHERE profile_id = ?");
    PreparedStatement read = session.prepare(
        "SELECT note, score FROM it_lab.profile_by_id " +
        "WHERE profile_id = ?");

    // Patch 1: không đặt note -> UNSET; chỉ tăng score.
    BoundStatement preserve = patch.bind()
        .setInt(1, 6)
        .setUuid(2, id);
    assertFalse(preserve.isSet(0));
    session.execute(preserve);

    Row first = session.execute(read.bind(id)).one();
    assertNotNull(first);
    assertEquals("initial", first.getString("note"));
    assertEquals(6, first.getInt("score"));

    // Patch 2: xóa note tường minh, để score UNSET.
    BoundStatement clear = patch.bind()
        .setToNull(0)
        .setUuid(2, id);
    assertTrue(clear.isSet(0));
    assertFalse(clear.isSet(1));
    session.execute(clear);

    Row second = session.execute(read.bind(id)).one();
    assertNotNull(second);
    assertTrue(second.isNull("note"));
    assertEquals(6, second.getInt("score"));

    // Patch 3: chuỗi rỗng là giá trị, không phải NULL.
    session.execute(patch.bind()
        .setString(0, "")
        .setUuid(2, id));
    Row third = session.execute(read.bind(id)).one();
    assertNotNull(third);
    assertFalse(third.isNull("note"));
    assertEquals("", third.getString("note"));
    assertEquals(6, third.getInt("score"));
}
~~~

**Tại sao test này tương đối ổn định:** nó dùng một UUID mới, thực thi mutation tuần tự và đọc lại bằng prepared SELECT cùng session, không phụ thuộc vào cách `cqlsh` in dấu `null` hay số. Nó không yêu cầu một cluster nhiều node để chứng minh semantics NULL/UNSET.

**Giới hạn:** class scaffold chỉ đưa phần cấu hình chính; để chạy nguyên suite còn cần project Gradle/Maven, JUnit Jupiter, Testcontainers, Java Driver, Docker runtime và schema setup được tạo đúng thứ tự. Các bài test network failure/repair/CL phải có fixture **multi-node** riêng.

### 16.1. Chuẩn hóa setup và test data factory

Trong dự án lớn, nên tách helper:

~~~java
// Ví dụ chữ ký helper, không bắt buộc tạo file riêng trong bài học:
// UUID newProfileWithNote(String note);
// Row readProfile(UUID profileId);
// PreparedStatement patchProfileStatement();
// UdtValue address(String street, String city, String zip);
// void assertNoUnexpectedMutation(UUID id, ExpectedState expected);
~~~

Nên tạo prepared statements một lần sau khi schema sẵn sàng rồi tái sử dụng; tránh chạy schema DDL trong từng test case hoặc đổi UDT type trong lúc suite đang chạy. Helpers **không** được swallow exceptions hoặc tự retry lỗi bind/codec, vì điều đó che bug mà test cần phát hiện.

### 16.2. Parameterized test cho từng lớp giá trị

JUnit 5 có `@ParameterizedTest` và `@MethodSource`. Một data provider có thể sinh:

~~~java
import java.util.stream.Stream;
import org.junit.jupiter.params.provider.Arguments;

static Stream<Arguments> scoreCases() {
    return Stream.of(
        Arguments.of(Integer.MIN_VALUE),
        Arguments.of(-1),
        Arguments.of(0),
        Arguments.of(1),
        Arguments.of(Integer.MAX_VALUE)
    );
}
~~~

Test mỗi giá trị bằng **một UUID mới**, thực hiện `setInt/getInt` đúng cột và assert `!row.isNull("score")` trước khi so. Nếu dùng property-based testing (jqwik/QuickTheories), pin random seed khi fail và in **chỉ dữ liệu fixture không nhạy cảm**, tránh log rows của người dùng.

### 16.3. Test framework với external resources

Một test Java/Maven có thể xuất hiện nhiều lỗi không thuộc Cassandra:

- Docker socket/runtime không chạy hoặc CI không được phép khởi động containers.
- Không kéo được Docker image vì network/registry rate limit.
- Quá ít RAM/CPU khiến Cassandra startup lâu hoặc bị OOM-kill.
- Node advertised address không kết nối được từ test process (Docker-in-Docker/remote daemon).
- Native port bị chặn hoặc truststore/auth chưa cấu hình.
- Module Testcontainers 1.x và 2.x lẫn package/artifact gây `ClassNotFoundException`.

Trong báo cáo, phân loại **ENVIRONMENT_SETUP_FAILURE** tách khỏi **CQL_SEMANTIC_FAILURE**; không biến lỗi môi trường thành “cột NULL sai” hoặc bỏ test hàng loạt mà không ghi lý do.

## 17. Ma trận CI theo phiên bản và topology

### 17.1. Một node đủ cho kiểu dữ liệu, chưa đủ cho replication

| Test class | Cassandra 4.1, 1 node | Cassandra 5.0, 1 node | Multi-node |
|---|---|---|---|
| NULL vs UNSET protocol V4+ | **Bắt buộc** | Bắt buộc nếu hỗ trợ release | Thường không cần để chứng minh semantics |
| CQL PK null/unset validation | Bắt buộc | Bắt buộc | Không cần |
| Collection list/set/map | Bắt buộc | Bắt buộc | Có thể thêm lỗi replica |
| Frozen/non-frozen UDT | Bắt buộc | Bắt buộc | Có thể thêm schema agreement |
| Scalar boundary, date/time/blob | Bắt buộc | Bắt buộc | Không cần |
| Spring Data converter/mapper | Bắt buộc với stack sử dụng | Bắt buộc nếu nâng cấp | Không cần cho mapping cơ bản |
| LOCAL_QUORUM availability | **Không phù hợp** với RF1 | Không phù hợp với RF1 | **Bắt buộc** |
| Node outage/repair/hinted handoff | Không thể kết luận | Không thể kết luận | **Bắt buộc** |
| LWT contention/serial consistency đa DC | Không đủ | Không đủ | **Bắt buộc** |

Khi nâng cấp Cassandra/Driver:

1. Pin cùng schema/fixtures và so assertions giữa các version.
2. Đọc release notes CQL/protocol/codec thay vì đoán mọi behavior giống nhau.
3. Kiểm tra schema metadata sau `ALTER TYPE` và các prepared statements cũ.
4. Test serialization của DTO qua HTTP/Kafka/snapshot nếu có.
5. Ghi lại mọi expected change cần migration hoặc feature flag.

### 17.2. Testcontainers và thời gian chạy CI

Với Cassandra, container startup không nhanh như một in-memory database:

- Chia nhóm fast unit tests và integration tests có container.
- Cho phép cache Docker images hợp lệ và pin digest theo policy bảo mật.
- Có CPU/RAM đủ để Cassandra không bị OOM/GC thô bạo.
- Chạy Testcontainers extension tuần tự nếu chia sẻ static container và schema.
- Không bật retry CI toàn suite ba lần để che flaky test; phân biệt transient infrastructure failure với bug correctness.
- Thu logs, thread dumps/cqlsh status và driver exception **sau lỗi**, không để thông tin xác thực xuất hiện trong log.

Trên môi trường build không có Docker, test có thể dùng một Cassandra cluster ephemeral được cấp riêng trong CI, nhưng phải đảm bảo **không có dữ liệu production**, isolation, cleanup, RF/CL và quyền tạo schema. Mock driver chỉ là phương án cho unit tests, không phải giải pháp thay integration test cho kiểu dữ liệu.

### 17.3. Kiểm thử topology nhiều node

Một cụm có RF=3 tại `dc1` (ít nhất ba node) cho phép:

- Ghi/đọc ở `LOCAL_QUORUM` khi đủ local replicas.
- Thử một node Down trong điều kiện được phép và quan sát `Unavailable`/timeout theo CL.
- Thử schema agreement sau thêm/đổi UDT field.
- Kiểm tra TTL/tombstone reconciliation theo repair/compaction trong một lab riêng.
- Đo hot partition/skew và request coordinator placement.

**Đừng** sử dụng test NULL/UNSET một node để khẳng định dữ liệu “đã được replicate tới toàn cluster” hoặc “có thể khôi phục sau node loss”. Nhiệm vụ của nó là xác minh **semantics CQL và Java codec**.

## 18. Chẩn đoán khi test thất bại

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| `NullPointerException` khi đọc `Row` | SELECT không có row theo PK | Assert row khác null trước getter |
| `getInt` trả 0 nhưng expected null | Primitive getter che nullable semantics | `row.isNull("score")` |
| NULL lại giữ nguyên cột cũ | Mapper đang dùng DO_NOT_SET, không phải SET_TO_NULL | Inspect generated statement/mapper config |
| UNSET xóa cột | Bind nhầm index/name, setter bị gọi với null hoặc test đã có mutation trước | Assert `BoundStatement.isSet` và CQL bind order |
| Collection empty trả List.of() thay vì null | Driver codec mặc định map empty/missing sang empty | Đổi assertion, dùng marker nếu business cần |
| Set order khác test | Set không đảm bảo ordering như List | So equality theo Set |
| List bị duplicate sau retry | Append list không idempotent | Dedup/event ID, dừng retry mù |
| UDT `getString("city")` null bất ngờ | UDT partial, thiếu field hoặc metadata version khác | Inspect type fields và payload bind |
| SET frozen UDT field bị reject | Không hỗ trợ field-specific mutation | Replace toàn bộ UDT hoặc non-frozen schema |
| UDT codec mismatch | Sử dụng UdtValue từ session/schema khác | Lấy UserDefinedType từ metadata của session hiện tại |
| Tinyint 128 trở thành -128 | Java cast byte overflow trước khi gửi | Validate số trước cast, test CQL literal đúng |
| Timestamp lệch precision | Instant nanos → CQL millis | So sau khi về milliseconds |
| Decimal equality fail dù số bằng | Scale khác nhau | Dùng compareTo và assert scale riêng khi cần |
| Blob test fail sau khi đọc một lần | ByteBuffer position thay đổi | Duplicate buffer và so bytes |
| `InvalidQueryException` trên PK UNSET | Expected validation | Không biến thành retryable network failure |
| Timeout trên UPDATE | Có thể đã ghi nhưng mất ACK | UNKNOWN outcome, reconcile trước retry |
| Testcontainers không start | Docker/RAM/image/port/wait strategy | Thu logs và environment diagnostics |
| Test pass local, fail CI | Version khác, clock/locale, parallel state, resource limits | Pin version, seed, timezone, isolate tests |

### 18.1. Kiểm thử ba kiểu lỗi dễ bị nhầm

**Lỗi bind/codec:** Java object không thể chuyển thành CQL type tương ứng. Ví dụ map nhận `Integer` trong schema nhưng service truyền `Long`. Thường cần sửa input/converter, không retry.

**Lỗi validation CQL:** server từ chối PK null, frozen field update, query không đúng partition restriction. Thường cần sửa CQL/schema hoặc validation, không retry.

**Lỗi hạ tầng/timeout:** request có thể đã được xử lý hoặc chưa; với mutation, phải đánh giá unknown outcome. Không đổi một timeout thành “thao tác chưa thực hiện” chỉ để test dễ pass.

### 18.2. Test nào không nên cố chạy trong mọi pull request?

Những bài có hiệu ứng lớn — flush SSTables liên tục, đổi RF trên multi-node, repair/decommission, chaos network kéo dài, benchmark tombstones hàng triệu cells — nên ở **nightly/soak/chaos pipeline** hoặc staging lab, không cần ép chạy trên mọi PR nhỏ. Core correctness test NULL/UNSET, collections, UDT và scalar boundaries vẫn nên nằm trong CI phù hợp.

## 19. Bài tập tình huống

### Bài 1 — PATCH absent và explicit null

Ứng dụng nhận hai request: `{}` và `{"note":null}`. Cả hai DTO Java đều có `note == null`. Vì sao đây là bug tiềm ẩn?

**Đáp án:** đã mất thông tin **field presence**. Nếu PATCH contract định nghĩa absent = giữ nguyên, explicit null = xóa, DTO phải lưu presence để bind UNSET và NULL khác nhau.

### Bài 2 — UNSET khi row có dữ liệu cũ

Hàng có `note="x"`, `score=10`. CQL `UPDATE SET note=?, score=?` được bind `note=UNSET`, `score=11`. Kết quả?

**Đáp án:** note vẫn `"x"`, score thành 11. UNSET bỏ qua assignment, không tạo tombstone cho note.

### Bài 3 — NULL trong non-key

Hàng có `note="x"` và `score=10`. Bind `note=NULL`, `score=UNSET`. Có mất cả hàng không?

**Đáp án:** không. Cột note bị xóa, score vẫn là 10; hàng vẫn được đọc nhờ cell sống khác. NULL thường tạo tombstone, cần monitor nếu lặp nhiều.

### Bài 4 — Collection empty vs null

Code thấy `row.getList("aliases", String.class).isEmpty()`. Có chứng minh khách hàng đã gửi `[]` và không phải chưa từng gửi aliases?

**Đáp án:** không. Cassandra/built-in codecs có thể không phân biệt được hai trạng thái đó khi đọc. Muốn giữ ý nghĩa nghiệp vụ, cần marker/trạng thái riêng.

### Bài 5 — Set khác List

Hai request cùng thêm tag `"vip"` và cùng append alias `"vip"`. Kết quả nào có thể chứa duplicate?

**Đáp án:** list giữ duplicate, set không. List append có thể không idempotent khi retry sau timeout.

### Bài 6 — Frozen UDT bị cập nhật field

Schema có `home frozen<address_info>` và `office address_info`. Vì sao `SET home.city='Huế'` lỗi còn `SET office.city='Huế'` hợp lệ?

**Đáp án:** frozen lưu whole UDT như một giá trị, không hỗ trợ partial field mutation; non-frozen có thể ghi từng field.

### Bài 7 — UdtValue thiếu trường

Client tạo UdtValue chỉ đặt `city`, không đặt `street/postal_code`, rồi ghi vào cột frozen `home` đang có đầy đủ thông tin. Có giữ các trường cũ không?

**Đáp án:** không nên giả định. Whole-value replacement với frozen UDT có thể làm các fields không được đặt thành NULL. Muốn merge cần read/modify/write toàn bộ có kiểm soát concurrency hoặc đổi data model.

### Bài 8 — Decimal với BigDecimal.equals

Một giá trị CQL đọc về là `1.00`, expected là `1.0`. Test `BigDecimal.equals` fail dù hai số bằng nhau. Làm gì?

**Đáp án:** dùng `compareTo() == 0` nếu contract là numeric equality; nếu scale là bất biến nghiệp vụ, assert scale riêng với codec/schema được xác minh.

### Bài 9 — Timestamp trước Unix epoch

App ghi `1969-12-31T23:59:59.123456789Z`. Vì sao round-trip có thể không giữ nano-giây?

**Đáp án:** CQL timestamp có precision milli-giây. Test so với `Instant.ofEpochMilli(input.toEpochMilli())` và tránh công thức chia epoch thủ công sai với số âm.

### Bài 10 — Một node RF1 cho QUORUM?

Integration test dùng Testcontainers một node và RF1, tất cả ghi/đọc thành công. Có thể kết luận cluster RF3 vẫn thỏa LOCAL_QUORUM khi một DC node Down?

**Đáp án:** không. Test một node chỉ chứng minh codec/CQL; availability/repair/CL phải thử trên topology nhiều node và failure injection riêng.

### Bài 11 — Invalid PK UNSET

BoundStatement để `profile_id` UNSET nhưng bind `note` đầy đủ. Server lỗi. Có nên tự gắn `idempotent=true` để Driver retry?

**Đáp án:** không. Đây là lỗi validation CQL/bind data, retry không thay được một PK thiếu. Sửa input/schema mapping.

### Bài 12 — Test pass nhưng service vẫn sai

Raw Driver test UNSET pass; Spring repository PATCH vẫn xóa cột khi field absent. Phân tích?

**Đáp án:** converter/DTO mapping có thể biến absent thành explicit null hoặc null-saving policy khác. Cần integration test qua **đúng API HTTP → entity/repository → Cassandra**, không chỉ qua low-level driver.

### Checklist hoàn thành bài

- [ ] Dùng Cassandra thật bằng Testcontainers/JUnit cho các semantics không thể mock.
- [ ] Phân biệt ABSENT (API), UNSET (bind), NULL (delete), empty string/collection.
- [ ] Kiểm tra `BoundStatement.isSet()` và gán lại instance sau `unset/setToNull`.
- [ ] Không truyền NULL/UNSET cho primary key hoặc predicate WHERE không phù hợp.
- [ ] Kiểm tra row tồn tại trước khi dùng getter; kiểm tra scalar NULL trước getter primitive.
- [ ] Biết list giữ thứ tự/duplicate; set/map so theo equality phần tử, không iteration order.
- [ ] Không assert collection rỗng và collection null luôn phân biệt được sau round-trip.
- [ ] Không đưa null elements vào collection; có negative test đúng tầng.
- [ ] Biết mutation partial collection và retry list append có thể không idempotent.
- [ ] Tạo UdtValue từ metadata session; phân biệt frozen và non-frozen field updates.
- [ ] Có test partial UDT và schema-evolution isolated.
- [ ] Test tinyint/smallint/int/bigint/varint/decimal boundaries và overflow trước codec.
- [ ] Test timestamp millisecond precision, pre-epoch, leap day và LocalTime nanos.
- [ ] Test Unicode normalization, blob ByteBuffer, IPv4/IPv6 không phụ thuộc DNS.
- [ ] Kiểm thử null-saving ở tầng Spring Data/Mapper thực tế khi có sử dụng.
- [ ] Phân biệt lỗi codec, CQL validation, CAS false và timeout UNKNOWN.
- [ ] Có test isolation, image/version pin, CI resource budget và ma trận multi-node riêng.

## 20. Tài liệu tham khảo

1. Apache Cassandra — [CQL Data Types](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html): primitive types, collection, UDT, null elements và frozen semantics.
2. Apache Cassandra — [CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): INSERT/UPDATE/DELETE, conditional statements, TTL và collection mutations.
3. Apache Cassandra — [Collections](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/collections/collection-create.html): list/set/map, kích thước và giới hạn truy vấn.
4. Apache Cassandra — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): xóa logic, repair và compaction.
5. Apache Cassandra Java Driver 4.19 — [Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): bind, UNSET, immutable BoundStatement.
6. Apache Cassandra Java Driver 4.19 — [Bindable API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/Bindable.html): `isSet()` và `unset()`.
7. Apache Cassandra Java Driver 4.19 — [Core Data Types](https://apache.github.io/cassandra-java-driver/4.19.0/core/): scalar/collection Java types, primitive NULL và GenericType.
8. Apache Cassandra Java Driver 4.19 — [User-Defined Types](https://apache.github.io/cassandra-java-driver/4.19.0/core/udts/): UdtValue, UserDefinedType và metadata.
9. Apache Cassandra Java Driver 4.19 — [Mapper Null Saving](https://apache.github.io/cassandra-java-driver/4.19.0/mapper/daos/null_saving/): DO_NOT_SET và SET_TO_NULL.
10. Testcontainers for Java — [Cassandra Module](https://java.testcontainers.org/modules/databases/cassandra/): CassandraContainer, CqlSession và cấu hình TLS.
11. Testcontainers for Java — [JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): @Testcontainers, @Container, lifecycle và giới hạn parallel execution.
12. Testcontainers — [2.0 Release Notes](https://github.com/testcontainers/testcontainers-java/releases): thay đổi artifact prefixes và package của container modules.
13. Spring Data Cassandra — [Reference](https://docs.spring.io/spring-data/cassandra/reference/): CassandraTemplate, entity conversion và repository integration.
14. JUnit 5 — [User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions, lifecycle, parameterized tests và reporting.
