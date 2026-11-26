# Triển khai thay đổi tương thích từng bước giữa ứng dụng và dữ liệu

## 1. Vì sao thay đổi graph và ứng dụng phải được triển khai theo từng bước?

Neo4j lưu property graph bằng node, relationship, label, type và property; ứng dụng Java có thể truy vấn bằng Cypher qua **Neo4j Java Driver** hoặc ánh xạ thành entity qua **Spring Data Neo4j (SDN)**. Khi một tính năng đổi tên property, thêm kiểu relationship, thay constraint hoặc chuyển cấu trúc graph, không phải mọi instance ứng dụng và mọi bản ghi đều được cập nhật tại cùng một thời điểm.

Giả sử API đang đọc `(:Customer {legacyName})`. Nhóm phát triển muốn đổi thành `displayName` rồi xóa `legacyName`. Nếu migration xóa property cũ trước khi toàn bộ Java services được nâng cấp:

- Một ứng dụng cũ đọc `c.legacyName` nhận `null` hoặc không hiển thị tên.
- Các instance mới đọc `c.displayName` cũng chưa thấy những node chưa backfill.
- Một background job cũ vẫn ghi `legacyName` có thể khiến `displayName` **lỗi thời**, ngay cả sau khi backfill một lần.
- Nếu dùng SDN `repository.save(entity)` với entity ánh xạ quan hệ không đầy đủ, thay đổi schema còn có thể kéo theo cập nhật relationship ngoài ý muốn.
- Khi client retry một transaction hoặc một sự kiện import, dữ liệu có thể bị ghi chồng nếu không có khóa nghiệp vụ và tính idempotent.

Đó là lý do chương **Nâng cấp và di trú** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J` cần một quy trình **triển khai thay đổi tương thích từng bước giữa ứng dụng và dữ liệu**. Mục tiêu không phải “chạy một script nhanh nhất”, mà là **giữ được đường nâng cấp và đường quay lui có thể kiểm chứng** khi nhiều phiên bản ứng dụng cùng hoạt động.

**Kết quả học tập:**

1. Phân biệt **nâng cấp Neo4j server/driver**, **di trú schema graph** và **triển khai ứng dụng**.
2. Xây compatibility matrix giữa phiên bản ứng dụng và trạng thái dữ liệu.
3. Triển khai chiến lược **expand → migrate → contract** cho property, index, constraint và relationship.
4. Thiết kế dual-read, dual-write, backfill theo lô, reconciliation và kiểm toán dữ liệu.
5. Viết Cypher và Java/Spring Data Neo4j theo cách idempotent, có ranh giới transaction rõ ràng.
6. Xác định thời điểm chuyển nguồn đọc, thời điểm ngừng ghi cũ và **ranh giới không thể rollback bằng code cũ**.
7. Lập kế hoạch canary, feature flag, quan sát, diễn tập rollback và cleanup có phê duyệt.

> **Phạm vi:** Ví dụ hướng tới Neo4j 5+ và Java 17+/Java Driver/SDN tương thích. Chức năng Cypher, cấu hình constraint, APOC, driver và thứ tự rolling upgrade có thể khác theo phiên bản, edition và topology. Luôn kiểm tra tài liệu đúng release. Tất cả câu lệnh tạo, sửa và xóa dữ liệu dưới đây **chỉ dùng trong database thực hành độc lập**; không dùng làm lệnh triển khai production trực tiếp.

## 2. Ba trục thay đổi khác nhau

| Trục | Ví dụ | Điều kiện tương thích | Rủi ro |
|---|---|---|---|
| **Ứng dụng** | Java service V0/V1/V2, DTO API, SDN entity, query mới | Phiên bản đang chạy phải hiểu dữ liệu có thể gặp | Null, mapper lỗi, caller cũ vẫn ghi |
| **Dữ liệu và schema graph** | Thêm `displayName`, index, constraint; đổi relationship type | Graph phải chấp nhận cả truy vấn cũ và mới trong giai đoạn chuyển tiếp | Mất thuộc tính, dữ liệu phân kỳ, đếm trùng relationship |
| **Nền tảng Neo4j** | Đổi server/cluster, Java Driver, Cypher syntax, APOC | Client, store format, plugin và edition được hỗ trợ | Không khởi động được, lỗi procedure, khó hoặc không thể downgrade store |

**Đừng đổi cả ba trục lớn trong một đợt** nếu có thể tách. Ví dụ đổi tên property cùng ngày với nâng major Neo4j và thay Spring Boot/SDN sẽ làm khó phân định lỗi do query, converter hay server.

Một lộ trình tốt có **điểm chặn (gates)**: sau mỗi bước, đo độ đúng của graph, tình trạng ứng dụng, số lỗi, độ trễ và khả năng rollback trước khi đi tiếp.

## 3. Chiến lược expand → migrate → contract

~~~mermaid
flowchart TD
    A["B0 — Ứng dụng cũ + dữ liệu cũ"] --> B["EXPAND: thêm schema/index/property mới nhưng giữ cũ"]
    B --> C["Triển khai ứng dụng tương thích: đọc cũ ưu tiên, ghi cả hai"]
    C --> D["Loại hết writer chỉ biết định dạng cũ"]
    D --> E["MIGRATE: backfill và đối soát hai phiên bản dữ liệu"]
    E --> F{"Kiểm tra đầy đủ, không divergence?"}
    F -->|Không| G["Giữ source of truth cũ, sửa lỗi và chạy đối soát lại"]
    G --> E
    F -->|Có| H["Canary chuyển sang đọc mới, vẫn dual-write"]
    H --> I["Mở rộng đọc mới, giữ cửa sổ rollback"]
    I --> J["CONTRACT: ngừng phụ thuộc cũ rồi mới bỏ dữ liệu/schema cũ"]
    J --> K["Dọn và đóng runbook sau khi đã kiểm chứng"]
~~~

### EXPAND — mở rộng mà không phá hợp đồng cũ

- Thêm property mới, index mới, label/relationship type mới nếu cần; **không xóa ngay** trường và loại quan hệ cũ.
- Cho phép ứng dụng cũ vẫn hoạt động trong khi ứng dụng mới triển khai dần.
- Cấu hình unique constraint theo khóa nghiệp vụ trước khi chạy backfill lớn.
- Đánh dấu code biết cả hai định dạng, nhưng **chưa lập tức chuyển nguồn đọc**.

### MIGRATE — chuyển dữ liệu và hành vi có kiểm soát

- Chạy bản ứng dụng có khả năng đọc/ghi tương thích với cả hai trường.
- Bảo đảm không còn writer cũ chỉ ghi một định dạng, hoặc có CDC/reconciler theo nguồn sự thật.
- Backfill từng lô, đối soát thiếu/trùng/sai khác, xử lý concurrency và lỗi tạm thời.
- Chạy test trên graph thật, không chỉ mock repository.

### CONTRACT — xóa hợp đồng cũ sau cửa sổ rollback

- Tất cả reader/writer/jobs đã dùng định dạng mới; không còn call đến property/relationship cũ.
- Quy trình backup/restore, scripts quản trị, materialized views và tích hợp bên ngoài đã được cập nhật.
- Đã xác nhận không cần quay về phiên bản chỉ biết dữ liệu cũ.
- Xóa dần index/constraint/property cũ bằng thay đổi riêng có phê duyệt.

**Quy tắc quan trọng:** *Contract thường là bước khó quay lui nhất.* Xóa dữ liệu cũ không giống tắt feature flag: sau khi dữ liệu cũ mất, phiên bản ứng dụng cũ có thể không còn chạy đúng.

## 4. Compatibility matrix: ứng dụng nào đọc được trạng thái dữ liệu nào?

Chọn kịch bản cụ thể:

- **V0:** đọc/ghi `legacyName`.
- **V1 (bridge):** đọc **ưu tiên legacyName**, fallback `displayName`; ghi **cả hai**.
- **V2 (cutover):** đọc **ưu tiên displayName**, fallback `legacyName`; vẫn ghi **cả hai**.
- **V3 (contract):** đọc/ghi **chỉ displayName**.

Các trạng thái dữ liệu:

- **D0:** chỉ `legacyName`.
- **D1:** bản ghi hỗn hợp; một số có cả hai, một số chỉ có cũ.
- **D2:** mọi bản ghi cần thiết có **cả hai giá trị đã đồng bộ**.
- **D3:** chỉ còn `displayName`, property cũ đã xóa hoặc không còn được cập nhật.

| Phiên bản | D0: cũ | D1: hỗn hợp | D2: hai trường đồng bộ | D3: mới |
|---|---|---|---|---|
| **V0: old-only** | Phù hợp | Đọc trường cũ được; **có thể làm hai trường lệch** khi ghi | Đọc được nhưng ghi cũ **làm mất đồng bộ** | **Không tương thích** |
| **V1: old-first, dual-write** | Phù hợp, bổ sung trường mới khi ghi | Phù hợp nếu `legacyName` là nguồn sự thật | Phù hợp | Chỉ fallback được khi chưa gỡ toàn bộ phụ thuộc cũ; **chưa phải mục tiêu cuối** |
| **V2: new-first, dual-write** | Fallback có thể đọc, nhưng chưa đạt gate bao phủ | Chỉ an toàn khi kiểm soát missing/divergence | **Phù hợp** | Có thể vẫn ghi lại property cũ nếu chưa tắt dual-write |
| **V3: new-only** | **Không tương thích** | **Không tương thích** cho bản ghi thiếu mới | Phù hợp | Phù hợp |

Bảng này không phải phép chứng minh tự động cho mọi ứng dụng. Nó **giả định cùng khóa nghiệp vụ, đúng tên property, không có writer ngoài kiểm soát và thao tác cập nhật atomic trong một transaction**.

### 4.1. Bẫy quan trọng: V0 vẫn ghi sau khi V1 đã dual-write

Giả sử C002 đã có:

~~~text
legacyName  = "Bình"
displayName = "Bình"
~~~

Một instance V0 còn chạy ghi:

~~~cypher
MATCH (c:QA008Customer {customerId:'C002'})
SET c.legacyName = 'Bình sửa';
~~~

Kết quả:

~~~text
legacyName  = "Bình sửa"
displayName = "Bình"
~~~

Nếu V2 bắt đầu **đọc mới ưu tiên** ngay lúc này, người dùng sẽ thấy tên **cũ**. Chạy backfill chỉ cho các bản ghi `displayName IS NULL` cũng **không sửa được** vì trường mới đã tồn tại nhưng lệch.

**Cách xử lý:** trong giai đoạn V0/V1 cùng sống, giữ `legacyName` làm nguồn sự thật; loại toàn bộ writer V0 (kể cả cron, batch import và retry worker) rồi **reconcile cả giá trị lệch**, không chỉ bổ sung giá trị thiếu. Nếu không thể loại writer cũ, cần cơ chế version/event/CDC hoặc một tầng ghi tập trung có khả năng bảo đảm sự đồng bộ theo thời điểm.

## 5. Đặt tiêu chí chuyển pha bằng các bất biến dữ liệu

Một “migration chạy xong” chỉ là điều kiện kỹ thuật. Để chuyển sang V2 hoặc V3, phải chứng minh các **bất biến (invariants)**:

| Bất biến | Cách đo | Gate trước khi đọc mới |
|---|---|---|
| Tất cả node có business ID hợp lệ | Đếm ID null/trùng, constraint | **0** bất hợp lệ |
| Tất cả node cần có tên mới | `displayName IS NULL` đối với tập mục tiêu | **0** thiếu |
| Hai trường không lệch trong cửa sổ dual-write | `legacyName <> displayName` | **0** khác biệt |
| Không còn chỉ-writer-cũ | Inventory deploy, metric theo version/caller, audit log | **0** writer V0 |
| Index mới sẵn sàng cho query | `SHOW INDEXES` và plan truy vấn | `ONLINE` khi query phụ thuộc |
| API hai phiên bản tương thích với dữ liệu | Integration/contract tests | PASS |
| Rollback đã được diễn tập | Test tắt flag/đổi app trên staging | PASS |
| Error budget còn cho rollout | Error rate, p95/p99, retries | Trong ngưỡng |

Nên dùng **cửa sổ quan sát** sau khi số liệu về 0, thay vì một lần `COUNT` duy nhất. Đặc biệt, một worker cũ ít chạy có thể chỉ xuất hiện sau khi đợt migration kết thúc.

## 6. Fixture Cypher: dữ liệu cũ có đáp án

Thực hành trên database riêng. Dùng label `QA008Customer`, `QA008Order` và relationship `QA008_PLACED`, tránh động đến mô hình ứng dụng thật.

### 6.1. Dọn fixture cũ (chỉ trong lab độc lập)

~~~cypher
MATCH (n)
WHERE n:QA008Customer OR n:QA008Order
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa008_customer_id_unique IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa008_order_id_unique IF EXISTS;
~~~

~~~cypher
DROP INDEX qa008_customer_display_name IF EXISTS;
~~~

Không chạy trong database thật hoặc database dùng chung các label này. Việc xóa quan hệ qua `DETACH DELETE` là **phá hủy dữ liệu**, nên chỉ dùng trong môi trường đã được chuẩn bị riêng.

### 6.2. Khóa nghiệp vụ và dữ liệu

~~~cypher
CREATE CONSTRAINT qa008_customer_id_unique IF NOT EXISTS
FOR (c:QA008Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa008_order_id_unique IF NOT EXISTS
FOR (o:QA008Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
UNWIND [
  {id:'C001', name:'An'},
  {id:'C002', name:'Bình'},
  {id:'C003', name:'Chi'},
  {id:'C004', name:'Dung'},
  {id:'C005', name:'Em'},
  {id:'C006', name:'Giang'}
] AS row
CREATE (:QA008Customer {
  customerId:row.id,
  legacyName:row.name
});
~~~

~~~cypher
UNWIND [
  {id:'O001', amount:100, customer:'C001'},
  {id:'O002', amount:200, customer:'C002'},
  {id:'O003', amount:300, customer:'C002'}
] AS row
MATCH (c:QA008Customer {customerId:row.customer})
CREATE (o:QA008Order {
  orderId:row.id,
  amount:row.amount
})
CREATE (c)-[:QA008_PLACED]->(o);
~~~

### 6.3. Đáp án baseline D0

~~~cypher
MATCH (c:QA008Customer)
RETURN count(c) AS customers,
       count(c.legacyName) AS oldPresent,
       count(c.displayName) AS newPresent;
~~~

| customers | oldPresent | newPresent |
|---:|---:|---:|
| **6** | **6** | **0** |

~~~cypher
MATCH (o:QA008Order)
RETURN count(o) AS orders, sum(o.amount) AS sumAmount;
~~~

**Đáp án:** `orders=3`, `sumAmount=600`.

~~~cypher
MATCH ()-[r:QA008_PLACED]->()
RETURN count(r) AS relationships;
~~~

**Đáp án:** `relationships=3`; C001 có một order, C002 có hai order, C003–C006 chưa có order. Khi di trú **chỉ đổi property tên**, các số này **phải giữ nguyên**.

## 7. Pha EXPAND: thêm khả năng mà không xóa định dạng cũ

### 7.1. Giữ cả hai property trong thời gian chuyển tiếp

Để Neo4j chấp nhận `displayName`, **không cần lệnh ALTER TABLE** như RDBMS: property graph cho phép node khác nhau có các tập property khác nhau.

Tuy nhiên, nếu truy vấn mới tìm theo `displayName`, có thể cần index:

~~~cypher
CREATE RANGE INDEX qa008_customer_display_name IF NOT EXISTS
FOR (c:QA008Customer) ON (c.displayName);
~~~

Đây là một **index**, không phải constraint bắt buộc mọi node phải có trường mới. Chỉ tạo khi workload cần, đo chi phí bảo trì index đối với ghi và xem trạng thái:

~~~cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties
WHERE name='qa008_customer_display_name'
RETURN name, type, state, labelsOrTypes, properties;
~~~

Chờ `ONLINE` trước khi coi việc tìm kiếm theo property mới đã sẵn sàng. Với fixture 6 node, index không đem lại phép đo hiệu năng có ý nghĩa.

### 7.2. Không đặt constraint bắt buộc trường mới quá sớm

Trước khi backfill, nhiều node D0 không có `displayName`. Nếu triển khai một quy tắc yêu cầu mọi node phải có tên mới, ghi mới hoặc thao tác trên dữ liệu cũ có thể thất bại; một số constraint tồn tại property phụ thuộc **Enterprise Edition** và phiên bản.

Thứ tự an toàn:

1. Tạo index không phá tương thích, nếu cần.
2. Đưa code dual-write vào production.
3. Backfill và sửa divergences.
4. Xác nhận mọi reader/writer dùng định dạng mới.
5. **Sau đó** mới cân nhắc constraint existence/type cho `displayName` phù hợp khả năng edition.

Tương tự, `IF NOT EXISTS` chỉ làm lệnh tạo schema dễ chạy lại; nó **không kiểm chứng** index/constraint đã có cùng loại, properties hoặc options như mong muốn. Kiểm tra `SHOW INDEXES`/`SHOW CONSTRAINTS` thật.

## 8. Pha ứng dụng cầu nối V1: đọc cũ ưu tiên, ghi hai trường

Đọc tương thích khi `legacyName` là nguồn sự thật:

~~~cypher
MATCH (c:QA008Customer {customerId:$id})
RETURN c.customerId AS customerId,
       coalesce(c.legacyName,c.displayName) AS name;
~~~

`coalesce` lấy giá trị khác null đầu tiên. Trong giai đoạn V0 vẫn hoạt động, ưu tiên trường cũ để tránh hiển thị tên mới đã lỗi thời. Nhưng không được xem `coalesce` là bộ kiểm tra đồng bộ: nó có thể che giấu data divergence. Cần metric riêng.

Ghi dual-write **trong cùng một giao dịch**:

~~~cypher
MERGE (c:QA008Customer {customerId:$id})
SET c.legacyName=$name,
    c.displayName=$name
RETURN c.customerId AS customerId;
~~~

Khi cả hai property được cập nhật trong cùng transaction Neo4j, việc commit/rollback bao cả hai giá trị. Không nên cập nhật `legacyName` ở transaction A rồi `displayName` ở transaction B: giữa hai lần commit, reader có thể thấy trạng thái phân kỳ, và lỗi ở bước sau làm dữ liệu lệch.

**Chú ý `MERGE`:** dùng khóa `customerId` có unique constraint; với workload đồng thời, client vẫn cần quản lý retry và lỗi constraint phù hợp. Không dùng `CREATE` tùy ý trong transaction function có thể retry, và không gắn email/payment side effect vào callback ghi.

## 9. Java Driver: ví dụ code tương thích với dữ liệu cũ và mới

Ứng dụng Java dùng `Driver` dài hạn, `Session` ngắn và database tường minh. Ví dụ dùng API đồng bộ Driver 5.x:

~~~java
import java.util.Optional;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class CustomerCompatibility {

    public static Optional<String> readLegacyFirst(
            Driver driver, String database, String id) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> {
                var result = tx.run("""
                    MATCH (c:QA008Customer {customerId:$id})
                    RETURN coalesce(
                        c.legacyName,c.displayName
                    ) AS name
                    """, Values.parameters("id", id));

                if (!result.hasNext()) {
                    return Optional.empty();
                }
                var name = result.next().get("name");
                return name.isNull()
                    ? Optional.empty()
                    : Optional.of(name.asString());
            });
        }
    }

    public static void upsertBoth(
            Driver driver, String database,
            String id, String name) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {
            session.executeWrite(tx -> {
                tx.run("""
                    MERGE (c:QA008Customer {customerId:$id})
                    SET c.legacyName=$name,
                        c.displayName=$name
                    """, Values.parameters(
                        "id", id, "name", name
                    )).consume();
                return null;
            });
        }
    }
}
~~~

**Vì sao code này an toàn hơn ghép Cypher?**

- `$id`/`$name` là tham số, không nối chuỗi từ HTTP input.
- `executeWrite` quản lý transaction/retry; cả hai giá trị được cập nhật trong cùng transaction.
- `Result` được tiêu thụ trong transaction, không trả cursor ra khỏi session.
- Có `SessionConfig.forDatabase`, tránh ghi sang home database sai.
- Hàm đọc trả `Optional<String>` để người gọi phân biệt bản ghi không tìm thấy; trong API thật có thể cần phân biệt thêm **có node nhưng thiếu tên** với không có node.

**Cần bổ sung ở production:** validation ID và tên, phân quyền, timeout, observability, idempotency key nếu API gọi lại, và kiểm thử cùng các version app đang có. Đừng dùng `System.out` chứa PII để debug rollout.

### 9.1. V2 chỉ đổi thứ tự đọc, chưa ngừng dual-write

Sau khi dữ liệu đạt D2 và V0 đã rút hết:

~~~cypher
MATCH (c:QA008Customer {customerId:$id})
RETURN coalesce(c.displayName,c.legacyName) AS name;
~~~

Giữ fallback trong một cửa sổ rollout để phát hiện bản ghi thiếu, nhưng phải **giám sát tỷ lệ fallback**. Nếu fallback tăng, dừng chuyển pha: có thể đang có writer cũ hoặc backfill chưa bao phủ hết.

## 10. Spring Data Neo4j: ánh xạ cả hai property trong giai đoạn chuyển tiếp

Đối với SDN, không nên chỉ đổi tên field Java rồi kỳ vọng database tự đổi property. Nếu tên graph property khác tên Java field, dùng `@Property` rõ ràng.

Ví dụ read/transition entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;

@Node("QA008Customer")
public class Customer {
    @Id
    private String customerId;

    @Property("legacyName")
    private String legacyName;

    @Property("displayName")
    private String displayName;

    protected Customer() {}

    public String nameForLegacyReaders() {
        return legacyName != null
            ? legacyName : displayName;
    }

    public String nameForNewReaders() {
        return displayName != null
            ? displayName : legacyName;
    }
}
~~~

**Những điểm phải test:**

- Repository đọc node D0 có `displayName=null` không gây lỗi ánh xạ.
- Repository đọc node D2 có cả hai giá trị đúng.
- Entity dùng `@Id` theo business key, không vô tình dùng internal/element ID thay thế.
- Nếu entity còn có `@Relationship`, cần kiểm tra custom query có hydrate đầy đủ graph hay không trước khi `save`.
- Spring transaction quản lý repository/`Neo4jClient`; một `Driver.session()` tự mở giao dịch riêng **không tự nhập vào** `@Transactional` của Spring.

Đối với cập nhật có mục tiêu **chỉ hai scalar properties**, một `@Query` hoặc `Neo4jClient` viết Cypher rõ ràng thường dễ kiểm soát hơn `repository.save(entity)` khi entity graph có nhiều relationship.

Ví dụ thao tác ghi qua Neo4jClient:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerNameWriter {
    private final Neo4jClient client;

    public CustomerNameWriter(Neo4jClient client) {
        this.client = client;
    }

    @Transactional
    public void rename(String id, String name) {
        client.query("""
            MERGE (c:QA008Customer {customerId:$id})
            SET c.legacyName=$name,
                c.displayName=$name
            RETURN c.customerId AS id
            """)
            .bind(id).to("id")
            .bind(name).to("name")
            .fetchAs(String.class)
            .mappedBy((typeSystem, record) ->
                record.get("id").asString())
            .one()
            .orElseThrow();
    }
}
~~~

Nếu phương thức dùng cùng `@Transactional` với các thao tác SDN khác, chúng có thể cùng thuộc Spring transaction được cấu hình. Không tự xen một Java Driver transaction riêng rồi nghĩ rằng rollback của Spring sẽ hoàn tác cả hai.

## 11. Pha MIGRATE: backfill theo lô có thể chạy lại

Sau khi đã **loại writer V0**, hoặc có cơ chế đảm bảo nguồn sự thật và giải quyết concurrent writes, mới bắt đầu backfill theo giá trị cũ.

### 11.1. Thử trước với hai khách hàng

~~~cypher
MATCH (c:QA008Customer)
WHERE c.customerId IN ['C001','C002']
SET c.displayName = c.legacyName;
~~~

Kiểm tra:

~~~cypher
MATCH (c:QA008Customer)
RETURN count(c) AS total,
       count(c.legacyName) AS oldPresent,
       count(c.displayName) AS newPresent;
~~~

**Đáp án D1:** `total=6`, `oldPresent=6`, `newPresent=2`.

### 11.2. Query xử lý batch phần còn thiếu hoặc lệch

~~~cypher
MATCH (c:QA008Customer)
WHERE c.legacyName IS NOT NULL
  AND (
    c.displayName IS NULL OR
    c.displayName <> c.legacyName
  )
WITH c
ORDER BY c.customerId
LIMIT $batchSize
SET c.displayName = c.legacyName
RETURN count(c) AS repaired;
~~~

Ứng dụng/job gọi với tham số `batchSize` hợp lý như 100 hoặc 500, commit từng batch rồi lặp lại đến khi `repaired=0`. Mục tiêu là idempotent: khi mọi bản ghi có hai giá trị giống nhau, chạy lại query không sửa thêm.

**Đừng áp dụng vô điều kiện khi đồng thời tồn tại writer thuộc hai hướng nguồn sự thật.** Query này coi `legacyName` là canonical; nếu V2 hoặc V3 đã bắt đầu ghi **chỉ trường mới**, một giá trị mới hơn có thể bị overwrite bởi giá trị cũ. Với ghi concurrent, cần kiểm soát source of truth và dùng hàng đợi sự kiện/version/checkpoint hoặc tạm dừng ghi theo cửa sổ được phê duyệt.

### 11.3. Kết quả mong đợi sau backfill đầy đủ

~~~cypher
MATCH (c:QA008Customer)
RETURN count(c) AS total,
       count(c.legacyName) AS oldPresent,
       count(c.displayName) AS newPresent;
~~~

| total | oldPresent | newPresent |
|---:|---:|---:|
| **6** | **6** | **6** |

Mọi khách hàng có cả hai tên; số order và relationship **vẫn là 3 và 3**. Batch thay property không làm thay đổi số node/relationship.

### 11.4. Vì sao không một transaction cho hàng triệu node?

Transaction quá lớn có thể tăng:

- Bộ nhớ cho transaction state và thời gian giữ lock.
- Áp lực transaction log, checkpoint, CPU/index maintenance.
- Thời gian rollback/retry và mức ảnh hưởng khi một câu lệnh lỗi.
- Số lượng dòng cần ghi và tail latency của API đang hoạt động.

Chia batch, đo `repaired/s`, commit latency, p95/p99 nghiệp vụ, lock waits và lỗi tạm thời. Có thể dùng `CALL { ... } IN TRANSACTIONS` khi phiên bản Cypher hỗ trợ, nhưng cần chú ý **đó là mô hình implicit transaction** và cú pháp scope thay đổi giữa các đời Neo4j 5/Cypher 25; không bọc nó trong `executeWrite` hay Spring transaction bên ngoài.

Một ví dụ cho phiên bản Cypher hỗ trợ **variable-scope CALL**:

~~~cypher
MATCH (c:QA008Customer)
WHERE c.legacyName IS NOT NULL
CALL (c) {
  SET c.displayName = c.legacyName
} IN TRANSACTIONS OF 100 ROWS;
~~~

Đây là minh họa cho **database lab ổn định**. Trên server đời cũ có thể phải dùng cú pháp `CALL { WITH c ... }` tương ứng; chạy `EXPLAIN` và kiểm tra docs đúng version. Ở production phải có chiến lược retry, checkpoint, logging, tránh chạy cả tập dữ liệu lớn chỉ vì lệnh ví dụ ngắn.

## 12. Đối soát dữ liệu: đếm thiếu, lệch và bản ghi không hợp lệ

### 12.1. Đếm chính xác trạng thái migration

~~~cypher
MATCH (c:QA008Customer)
RETURN
  count(c) AS total,
  count(CASE WHEN c.legacyName IS NULL
                AND c.displayName IS NULL THEN 1 END)
    AS missingBoth,
  count(CASE WHEN c.legacyName IS NOT NULL
                AND c.displayName IS NULL THEN 1 END)
    AS missingNew,
  count(CASE WHEN c.legacyName IS NOT NULL
                AND c.displayName IS NOT NULL
                AND c.legacyName <> c.displayName
             THEN 1 END)
    AS divergent;
~~~

Trên D0: `total=6`, `missingBoth=0`, `missingNew=6`, `divergent=0`.

Sau backfill D2: `total=6`, `missingBoth=0`, `missingNew=0`, `divergent=0`.

**Lưu ý:** Một record chỉ có `displayName` nhưng không có `legacyName` không xuất hiện trong `missingNew`/`divergent`. Nếu V1/V2 còn dual-write và trường cũ vẫn là hợp đồng bắt buộc, phải đo thêm trường hợp **missingOld**:

~~~cypher
MATCH (c:QA008Customer)
WHERE c.legacyName IS NULL
  AND c.displayName IS NOT NULL
RETURN count(c) AS missingOld;
~~~

Trong D2 trước contract, kỳ vọng `missingOld=0`. Sau D3, `missingOld` sẽ lớn và **không còn là lỗi** nếu hợp đồng đã chuyển hoàn toàn.

### 12.2. Tìm ID sai và record bất thường

~~~cypher
MATCH (c:QA008Customer)
WHERE c.customerId IS NULL
RETURN count(c) AS missingIds;
~~~

~~~cypher
MATCH (c:QA008Customer)
WITH c.customerId AS id, count(*) AS amount
WHERE id IS NOT NULL AND amount > 1
RETURN id, amount
ORDER BY amount DESC
LIMIT 10;
~~~

Một uniqueness constraint chỉ chặn trùng giá trị **đang tồn tại**; nó không mặc nhiên buộc mọi node phải có `customerId`. Đừng dùng kết quả `SHOW CONSTRAINTS` thay thế kiểm tra property thiếu.

### 12.3. So sánh checksum logic trên tập dữ liệu lớn

`count` bằng nhau không có nghĩa mỗi node đúng. Ngoài đếm:

- Lấy mẫu ngẫu nhiên có seed/quy tắc cố định theo `customerId`.
- So sánh giá trị canonical ở mức record theo ID.
- Đối chiếu tổng hợp nghiệp vụ (số order, total amount, relationship counts).
- Đo số lỗi từ client và record bị retry.
- Nếu cần hash/checksum toàn bộ dữ liệu, dùng một pipeline đáng tin cậy, sắp xếp deterministic, chuẩn hóa null/encoding và giới hạn memory. Không xây một `collect` khổng lồ chỉ để hash toàn graph trong một transaction.

## 13. Minh họa divergence do writer cũ còn sống

Bước này giúp nhận diện lỗi không được sửa bằng backfill chỉ xét null.

Giả sử đang ở D2, rồi **một instance V0 trong lab** chạy:

~~~cypher
MATCH (c:QA008Customer {customerId:'C002'})
SET c.legacyName = 'Bình sửa';
~~~

Kiểm tra:

~~~cypher
MATCH (c:QA008Customer)
WHERE c.legacyName IS NOT NULL
  AND c.displayName IS NOT NULL
  AND c.legacyName <> c.displayName
RETURN c.customerId AS id,
       c.legacyName AS legacy,
       c.displayName AS newer;
~~~

**Đáp án:** một dòng, `id='C002'`; `legacy='Bình sửa'` và `newer='Bình'`. Query chỉ tìm `c.displayName IS NULL` trả 0, dù thực tế có **một divergence**.

Sau khi chắc chắn đã dừng tất cả writer old-only và `legacyName` vẫn là canonical, chạy query sửa theo batch mục 11.2. Đáp án sau xử lý:

~~~cypher
MATCH (c:QA008Customer {customerId:'C002'})
RETURN c.legacyName AS legacy,
       c.displayName AS newer;
~~~

Cả hai phải bằng **"Bình sửa"**. Sau đó `divergent=0`. Không chuyển sang đọc mới cho đến khi đã kiểm tra nhiều đợt, không chỉ một lần đếm ngay sau khi sửa.

## 14. Chuyển nguồn đọc bằng canary và feature flag

Khi các gate đạt:

1. **Đóng băng định nghĩa canonical:** V0 đã rút, V1/V2 vẫn dual-write; không có writer cũ bị quên.
2. **Đối soát:** mọi node cần thiết có `displayName`, `divergent=0`, index mới `ONLINE` nếu cần.
3. **Canary:** cho một tỷ lệ nhỏ request/instance dùng `coalesce(displayName,legacyName)`.
4. **So sánh:** cùng business ID, response fields, error rate, p95/p99, read/write throughput và tỷ lệ fallback.
5. **Mở rộng dần:** 1% → 5% → 25% → 100% (chỉ là ví dụ, phụ thuộc quy trình tổ chức).
6. **Giữ dual-write:** trong cửa sổ rollback về V1, vẫn bảo đảm `legacyName` được cập nhật.
7. **Chốt thời gian quan sát:** chỉ sau nhiều chu kỳ cron/queue/import mới kết luận không còn writer V0.

**Feature flag không tự bảo đảm tính nhất quán.** Nếu một instance bật `readNew` nhưng bản khác chưa backfill hoặc dual-write đúng, API có thể trả khác nhau cho cùng ID. Flag cần được quản lý theo môi trường/workflow, có khả năng tắt nhanh và metric đủ phát hiện lỗi.

### 14.1. Quan sát fallback thay vì im lặng che lỗi

~~~cypher
MATCH (c:QA008Customer)
RETURN
  count(CASE WHEN c.displayName IS NULL
             AND c.legacyName IS NOT NULL
             THEN 1 END) AS needFallback,
  count(CASE WHEN c.displayName IS NOT NULL
             THEN 1 END) AS readyNew;
~~~

Trong fixture D2, `needFallback=0` và `readyNew=6`. Đối với production, số này cần đo trên đúng **tập bản ghi người dùng thực truy cập**, không chỉ tổng graph; một tỷ lệ 0,01% missing có thể vẫn là lỗi nghiêm trọng nếu liên quan khách hàng lớn.

## 15. Relationship migration: dữ liệu có thể bị đếm trùng

Đổi tên property thường ít ảnh hưởng hơn **đổi loại cạnh**, ví dụ từ:

~~~cypher
(c:Customer)-[:PLACED]->(o:Order)
~~~

sang:

~~~cypher
(c:Customer)-[:ORDERED]->(o:Order)
~~~

Nếu triển khai song song cả hai edge types trên cùng một cặp node, query cũ và mới vẫn tìm thấy đơn hàng, nhưng một query tổng hợp dùng:

~~~cypher
MATCH (c)-[:PLACED|ORDERED]->(o)
RETURN count(*) AS edges;
~~~

có thể **đếm gấp đôi** một đơn hàng vì hai quan hệ trùng ý nghĩa. Với dữ liệu có multiple relationship giữa cùng node, không dùng `count(DISTINCT o)` như một “thuốc chữa” nếu business logic thực sự cần phân biệt các giao dịch; phải xác định identity của relationship.

### 15.1. Một migration relationship có kiểm soát trong lab

Fixture đã dùng `QA008_PLACED`. Nếu thêm type mới `QA008_ORDERED`, một phép minh họa idempotent là:

~~~cypher
MATCH (c:QA008Customer)-[:QA008_PLACED]->(o:QA008Order)
MERGE (c)-[:QA008_ORDERED]->(o);
~~~

Với fixture, `QA008_ORDERED` tạo **3 relationship** mới nếu chưa có. `QA008_PLACED` vẫn là 3; tổng hai type là 6, nhưng chỉ có 3 cặp customer/order có ý nghĩa nghiệp vụ.

~~~cypher
MATCH (c:QA008Customer)-[:QA008_PLACED|QA008_ORDERED]->
      (o:QA008Order)
RETURN count(*) AS rawEdges,
       count(DISTINCT o) AS distinctOrders;
~~~

**Đáp án minh họa:** `rawEdges=6`, `distinctOrders=3` trong fixture này vì mỗi order thuộc đúng một customer.

**Thận trọng:** `MERGE (c)-[:REL]->(o)` không đặt unique constraint cho mọi loại relationship và không tự xóa duplicate có từ trước; cần kiểm tra invariant trước/ sau. Nếu relationship có property (`role`, `createdAt`, `amount`), phải copy đúng giá trị theo khóa/định danh nghiệp vụ, không tạo cạnh “trống” khiến thông tin bị mất.

### 15.2. Cách thiết kế chuyển đổi quan hệ an toàn

- Giữ ứng dụng cũ đọc `QA008_PLACED`, ứng dụng mới có thể đọc cả hai với **khử trùng lặp theo business key**.
- Nếu dual-write cả hai relationship types, đặt hai thao tác trong một transaction.
- Khi loại old-only writer, backfill tập cạnh mới bằng batch và kiểm tra completeness.
- Khi mọi reader chuyển sang type mới, tiếp tục giữ cạnh cũ cho cửa sổ rollback.
- Chỉ gỡ relationship cũ khi không còn phụ thuộc và có bản sao/đường forward recovery.

Nếu không chấp nhận tạo trùng cạnh, có thể thiết kế **read bridge bằng Cypher** hoặc một lớp ánh xạ API trong lúc chuyển đổi, thay vì mặc định dual-write relationship.

## 16. Index và constraint: thay đổi “additive” cũng phải chuẩn bị

Một migration có thể đồng thời thay unique key, ví dụ muốn chuyển từ `customerId` sang `externalKey`.

**Nguy cơ:** chưa có `externalKey` ở mọi node; giá trị mới có thể trùng hoặc null; việc tạo unique constraint thất bại, hoặc thành công nhưng vẫn cho những node **thiếu property** vì uniqueness không tự đồng nghĩa existence.

Quy trình:

1. Định nghĩa khóa mới, kiểu dữ liệu, quy tắc normalize và phạm vi uniqueness.
2. Backfill `externalKey` với nguồn dữ liệu chính xác và log record lỗi.
3. Kiểm tra thiếu/trùng **trước** khi tạo constraint mới.
4. Tạo constraint/index mới **với tên riêng**, chờ `ONLINE`.
5. Triển khai reader/writer dùng khóa mới, vẫn giữ khóa cũ trong giai đoạn chuyển tiếp.
6. Test `MERGE`, concurrency, idempotency và Cypher execution plan.
7. Chỉ sau cửa sổ rollback mới cân nhắc drop index/constraint cũ.

Đối với graph truy vấn relationship và đường đi, thay index của **label/node đầu vào** có thể làm kế hoạch truy vấn đổi. Vì vậy, cần `EXPLAIN`/`PROFILE` các query quan trọng **trên cả ứng dụng cũ và mới** khi index tồn tại song song.

### Không xóa index cũ quá sớm

Index cũ vẫn có thể phục vụ truy vấn của instance chưa nâng cấp. Đổi source code ở Git không có nghĩa tất cả background workers hoặc batch scripts đã đổi. Dùng query logs, repository inventory và metrics để xác nhận không còn dependency trước khi drop index.

## 17. Migration không được coi database là toàn bộ hệ thống

Những client có thể dùng mô hình cũ:

| Thành phần | Ví dụ phụ thuộc | Việc kiểm tra |
|---|---|---|
| Java API trực tiếp qua Driver | `RETURN c.legacyName` | Tìm Cypher ở service và job đang chạy |
| Spring Data Neo4j | `@Property("legacyName")`, repository `@Query` | Entity/projection, mapping và `save` |
| Import CSV / batch | Header `legacy_name`, mapping vào property | Pipeline, scheduler, dữ liệu gửi lại |
| Kafka/CDC/outbox | Event schema cũ | Consumer/versioning/offset, replay |
| Báo cáo/BI | Truy vấn Cypher định kỳ | Report engine, dashboard và thời gian chạy |
| Truy vấn thủ công/admin | Procedure APOC, script vận hành | Runbook, permissions và lịch bảo trì |
| Cache/search downstream | Trường tên hiển thị cũ trong index | Rebuild/invalidation và đo sai lệch |
| Backups và DR site | Restore database cũ trong lúc app mới chạy | Kiểm thử restore và migration sau restore |

**Mục tiêu:** không còn đường ghi “ẩn” làm sai invariant. Nên ghi **deployment manifest phiên bản** gồm application releases, background jobs, event schemas, Neo4j DBMS/Driver/SDN versions và thời điểm bật feature flag.

Một migration “thành công” nhưng restore từ backup D0 vào một môi trường chỉ còn V3 vẫn có thể **không khởi động đúng về mặt nghiệp vụ**. Runbook disaster recovery phải biết phục hồi dữ liệu cũ rồi chạy expand/backfill trước khi mở ứng dụng V3, hoặc lưu điểm backup D2/D3 theo chính sách.

## 18. Rolling deployment trên nhiều instance và cluster Neo4j

### 18.1. Rolling ứng dụng trước, contract dữ liệu sau

Trong Kubernetes hoặc nhiều VM, không thể giả định tất cả instances cập nhật tại cùng một thời điểm. Khi deploy V1:

- Một số pod V0 và V1 cùng phục vụ request.
- Có request đang chạy qua transaction cũ, queue consumer hoặc scheduled job.
- Khả năng rollback yêu cầu **dữ liệu vẫn thỏa hợp đồng V0**.

Vì thế, giai đoạn mixed-version ứng dụng phải được thiết kế chủ động; không nhầm “rolling restart ứng dụng” với “migration dữ liệu atomically”.

### 18.2. Rolling Neo4j server khác schema migration

Nâng phiên bản **Neo4j DBMS/cluster** là một bài toán khác. Có những release hỗ trợ rolling upgrades trong phạm vi tương thích được công bố; có những thay đổi cần upgrade/migrate store offline hoặc có giới hạn khi trộn phiên bản các thành viên.

Không khẳng định “chỉ cần nâng từng primary là được” cho mọi cặp version. Trước khi triển khai:

1. Xác định version nguồn, đích, edition, topology và đường nâng cấp được nhà cung cấp hỗ trợ.
2. Kiểm tra Java Driver, Spring Boot/SDN, APOC, GDS/custom procedures, Cypher deprecations, index provider và format store.
3. Backup toàn bộ database cần thiết, gồm metadata hệ thống nếu kế hoạch phục hồi yêu cầu.
4. Diễn tập một đợt upgrade trên bản restore của production dataset hoặc staging tương đương.
5. Có kiểm tra schema/logic và failover/routing từ client sau khi thay đổi.
6. Không kỳ vọng có thể **downgrade store format** chỉ bằng cài lại binary cũ.

**Rollback ứng dụng** và **rollback DBMS** không giống nhau. Khi store đã được nâng cấp không thể đọc bằng phiên bản cũ, đường lui có thể phải là **restore từ backup được kiểm chứng**, với hệ quả RPO/RTO riêng.

### 18.3. Giới hạn khi xử lý đa database

Nếu tách nhiều database/tenant, từng database có thể ở trạng thái migration khác nhau. Một code V2 đọc đồng thời hai database phải dựa vào **compatibility contract** rõ ràng; transaction giữa nhiều database không mặc định là một distributed transaction nguyên tử. Cần thiết kế saga/outbox/reconciliation nếu nghiệp vụ đòi phối hợp xuyên database.

## 19. Quan sát migration bằng metric và log

Nên thu thập đồng thời **độ đúng dữ liệu** và **trải nghiệm ứng dụng**:

| Chỉ số | Ý nghĩa |
|---|---|
| `missingNew`, `missingOld`, `divergent` | Trạng thái và độ nhất quán của bản ghi |
| Số writer V0/V1/V2/V3 còn active | Đo thực tế luồng ghi có tương thích không |
| Backfill batches/s, rows/s, retry rate | Tiến độ migration và ảnh hưởng lên DB |
| Read fallback count/rate | Phát hiện record chưa đủ chuẩn khi chuyển nguồn đọc |
| API p50/p95/p99, error/timeout | Cảnh báo chất lượng phục vụ suy giảm |
| Neo4j transaction/lock waits/commit latency | Có tranh chấp do backfill không |
| CPU, heap/GC, page cache, disk log I/O | Backfill có chiếm tài nguyên quá mức |
| Index population/state | Truy vấn mới có dùng được schema không |
| Bookmark/routing errors ở cluster | Client có đọc đúng dữ liệu sau ghi không |
| Truy vấn query log vẫn nhắc property cũ | Chưa xóa hết phụ thuộc reader/job |

Ví dụ “gate” giả định để quyết định tăng canary:

- 100% instance đọc mới đang dùng đúng cấu hình và database.
- `missingNew=0` và `divergent=0` trong nhiều đợt kiểm tra.
- Không còn writer cũ chạy trong ít nhất một chu kỳ đầy đủ của các scheduled jobs.
- Error rate và p95 không vượt baseline/SLO đã xác định.
- Không có incident constraint/index, lock timeout hoặc retry bùng phát.

Đừng đưa tên khách hàng/email thật vào metric labels hoặc log debug. Với số lượng node lớn, scan toàn graph mỗi giây để đo divergence có thể tốn tài nguyên; dùng scan theo lô, lấy mẫu cộng với kiểm tra toàn phần trong cửa sổ phù hợp.

## 20. Rollback: quay lại app được khi nào, và không được khi nào?

| Thời điểm | Có thể rollback ứng dụng về V1/V0? | Dữ liệu cần giữ | Cảnh báo |
|---|---|---|---|
| Sau EXPAND, trước backfill | Thường **có** nếu chưa phá hợp đồng cũ | `legacyName` | Index mới có thể tạm giữ, không cần drop ngay |
| Đang dual-write V1, V0 đã loại | **V1** được; **V0** chỉ nếu vẫn chấp nhận rủi ro làm lệch mới | Cả hai, canonical cũ | Sau rollback V0 phải reconcile lại trước cutover |
| Đang V2 đọc mới, vẫn dual-write | **V1** thường được; V0 cần đánh giá | Cả hai giá trị đã đồng bộ | Tắt readNew và kiểm tra divergence |
| Đã dừng ghi cũ nhưng chưa xóa field | Về V1/V0 có thể cần backfill ngược | `legacyName` phải còn cập nhật | Tên cũ có thể lỗi thời |
| Đã xóa `legacyName` (D3) | **Không thể** chỉ rollback sang V0/V1 rồi dùng ngay | Cần dữ liệu cũ khôi phục/biến đổi | Ưu tiên forward-fix hoặc restore theo runbook |
| Neo4j store đã upgrade major | Tùy cặp version, có thể **không** downgrade được | Backup tương thích từ trước upgrade | Quay lại binary cũ không đảm bảo đọc store mới |

**Rollback có thể làm mất thay đổi nghiệp vụ** nếu restore từ backup cũ. Do đó, rollback ứng dụng bằng feature flag thường ít rủi ro hơn rollback database, **nhưng chỉ khi dữ liệu vẫn giữ hợp đồng cũ**.

### 20.1. Forward-fix thay vì xóa dữ liệu

Nếu V2 phát hiện một số record chưa có `displayName`, có thể tắt flag readNew, sửa pipeline và backfill/reconcile những record bị ảnh hưởng. Đó là **forward-fix có kiểm soát**.

Đừng chạy `REMOVE c.displayName` trên production để “quay về V0” khi đã có writer mới ghi vào `displayName` như nguồn sự thật; việc đó có thể xóa cập nhật không còn ở `legacyName`.

## 21. Pha CONTRACT: chỉ xóa cũ khi tất cả consumer đã chuyển

Các điều kiện tối thiểu:

1. Inventory xác nhận mọi read/write code, batch, event consumer và script quản trị không cần `legacyName`.
2. V3 đã được triển khai ổn định, `displayName` được ghi đầy đủ và đúng.
3. Không còn mục tiêu rollback về V0/V1, hoặc có phương án restore/forward-transform được duyệt.
4. Backup/DR runbook đã tương thích D3; đã test khôi phục từ bản lưu trước và sau migration.
5. Query dùng index mới ổn định; index cũ có thể ngừng sử dụng và có phương án đánh giá ảnh hưởng khi drop.

### 21.1. Minh họa cleanup có tính phá hủy — chỉ lab

Trên database thực hành, sau khi đã bảo đảm V3 không còn cần `legacyName`:

~~~cypher
MATCH (c:QA008Customer)
WHERE c.legacyName IS NOT NULL
WITH c
ORDER BY c.customerId
LIMIT $batchSize
REMOVE c.legacyName
RETURN count(c) AS removed;
~~~

Chạy theo batch đến khi `removed=0`. **Không chạy query này trên production dựa vào bài học**: nó xóa nguồn dữ liệu cũ và có thể làm mất đường rollback. Cần thay bằng migration job đã review, test, backup và có phê duyệt.

Sau contract D3 với 6 node:

~~~cypher
MATCH (c:QA008Customer)
RETURN count(c) AS customers,
       count(c.legacyName) AS oldPresent,
       count(c.displayName) AS newPresent;
~~~

**Đáp án:** `customers=6`, `oldPresent=0`, `newPresent=6`.

Khi drop constraint/index cũ, đánh giá lại `EXPLAIN`/`PROFILE` của các câu `MATCH/MERGE` theo khóa mới. Không drop unique constraint `qa008_customer_id_unique` của fixture nếu hệ thống vẫn dùng `customerId` để định danh: nó không phải index legacy chỉ vì tên gần với migration.

## 22. Test chiến lược nâng cấp trước khi áp dụng thật

### 22.1. Ma trận integration test tối thiểu

| Trường hợp | Thiết lập | Kết quả phải có |
|---|---|---|
| V0 đọc D0 | Chỉ legacyName | Trả đúng tên |
| V1 đọc D0 | Fallback và dual-write chưa chạy | Trả đúng tên |
| V1 ghi D1 | Sửa C001 | Hai property được cập nhật cùng nhau |
| V0 ghi sau khi D2 | Giả lập old-only writer | Query divergence phát hiện sai lệch |
| Backfill sau khi dừng V0 | C002 bị lệch | Đồng bộ lại C002, count về 0 |
| V2 đọc D2 | New-first | Giá trị mới đúng, fallback=0 |
| V2 rollback về V1 | Hai property còn đồng bộ | Không lỗi hay mất cập nhật |
| V3 đọc D3 | Chỉ displayName | Mọi node đều có tên |
| V0 đọc D3 | Không có legacyName | **Test phải chứng minh không tương thích** |
| Quan hệ cũ/mới cùng tồn tại | Hai type kết nối cùng cặp | Query tổng hợp không được đếm trùng |
| Constraint unique/ID null | Dữ liệu input sai | Lỗi ghi đúng loại; không tạo node trùng |
| Dừng migration giữa chừng | Một số batch đã commit | Resume idempotent, không mất dữ liệu |

Không chỉ unit test một DTO được dựng tay. Dùng Neo4j test container hoặc staging có fixture và chạy thật Java Driver, SDN repositories/custom `@Query`, Schema commands và các transaction.

### 22.2. Test rollback dữ liệu không phải lúc nào cũng nên dùng DROP/DELETE

Để kiểm tra khả năng quay về phiên bản ứng dụng V1, dùng **toggle feature flag**, không cần xóa property mới. Chỉ mô phỏng D3/contract trong một database test độc lập. Không dùng database production để “chứng minh không rollback được” bằng cách xóa dữ liệu.

### 22.3. Hiệu năng và concurrency

Chạy workload trước/sau với cùng dataset, số client và version server. Đo:

- `read fallback`, `p95/p99` và `DB Hits` khi dùng `coalesce`.
- Tải ghi thêm do dual-write và index mới.
- Thời gian backfill, lock wait, transaction log volume, page cache, CPU/GC.
- Retry/timeout của `executeWrite` và Spring transaction.
- Tính đúng qua nhiều bản ghi được cập nhật đồng thời khi backfill.

Với dữ liệu fixture chỉ 6 node, **không lấy thời gian ms làm chuẩn hiệu năng**. Sử dụng dataset đại diện để benchmark, còn fixture để xác nhận logic.

## 23. Runbook triển khai theo nhiều cửa kiểm soát

Một runbook có thể được trình bày như sau:

| Bước | Hành động | Tiêu chí PASS | Nếu FAIL |
|---|---|---|---|
| **0** | Inventory app/job/schema, ghi baseline và backup test được restore | Biết rõ source of truth và đường rollback | Chưa triển khai |
| **1** | Expand index/property/constraint phụ trợ | Code cũ hoạt động, index `ONLINE` | Dừng, không contract |
| **2** | Canary V1 old-first dual-write | API đúng, không lỗi quyền/mapping | Rollback V1, giữ schema additive |
| **3** | Triển khai toàn bộ V1, loại writer V0 | Không còn old-only writer theo deploy+metrics | Chưa backfill chuyển nguồn |
| **4** | Backfill và reconcile batches | MissingNew=0, divergent=0 ổn định | Giảm batch, sửa source/locks |
| **5** | Canary V2 new-first dual-write | Fallback thấp/0, p95 và errors ổn | Tắt flag, quay về old-first |
| **6** | Mở rộng V2, quan sát qua các lịch batch | Không phát sinh divergence | Phân tích writers/event replay |
| **7** | Chuyển V3 new-only | Không còn consumer cũ; backup DR updated | Chưa xóa legacy |
| **8** | Contract: xóa legacy theo lô có phê duyệt | Data/schema tests và DR tests PASS | Dừng cleanup; ưu tiên forward-fix |
| **9** | Đóng migration và cập nhật tài liệu | SLO ổn, alert tốt, restore thử thành công | Không tuyên bố hoàn tất |

Ở mỗi bước, ghi ai phê duyệt, thời điểm UTC, phiên bản đã deploy, số lượng bản ghi và lỗi đo được. Đừng chờ đến bước contract mới viết rollback plan; **đường lui phải được chuẩn bị từ bước 0**.

## 24. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| V2 đôi khi đọc tên cũ | V0 vẫn ghi legacy-only, V2 ưu tiên new | Dừng V0, đo divergence và reconcile |
| `missingNew=0` nhưng dữ liệu vẫn sai | Chỉ backfill null, không xử lý giá trị lệch | So sánh cả hai giá trị, không chỉ sự tồn tại |
| Constraint mới fail | Giá trị trùng/null/không phù hợp type | Kiểm tra và làm sạch trước khi tạo |
| `IF NOT EXISTS` thành công nhưng schema sai | Đã có index/constraint cùng tên khác định nghĩa | Dùng `SHOW INDEXES/CONSTRAINTS` đối chiếu |
| Một số jobs vẫn ghi kiểu cũ | Đã cập nhật HTTP API nhưng quên scheduler/consumer | Inventory mọi writers, log query và version |
| Khi SDN save mất một số quan hệ | Entity được tải thiếu graph hoặc mapping đổi | Test quan hệ và dùng Cypher update scalar có mục tiêu |
| Dual-write nhưng một field mới null | Hai lần ghi nằm ở transaction khác nhau hoặc đường code chưa cập nhật | Atomic dual-write, test rollback |
| Dữ liệu phình gấp đôi sau relationship migration | Hai edge types cùng tồn tại | Đếm theo business key, định nghĩa giai đoạn dual-read/dual-write |
| Rollback app V0 sau khi xóa property cũ lỗi | Đã vượt qua ranh giới contract | Forward-fix hoặc restore theo runbook |
| Migration tạo DB load cao | Batch lớn, khóa/IOPS/index maintenance | Throttle, batch nhỏ, quan sát p95 và lock waits |
| Nâng major Neo4j xong không downgrade được | Store format đổi, quy trình không hỗ trợ downgrade | Restore backup tương thích và theo upgrade guide |
| Backup D0 dùng với app V3 bị lỗi | DR không biết bước migration sau restore | Bổ sung compatibility gate vào runbook restore |

## 25. Bài tập có đáp án

### Bài 1 — Thứ tự triển khai

Một ứng dụng V0 chỉ biết `legacyName`. Nhóm phát triển muốn xóa nó và dùng `displayName`. Nên xóa cũ trước khi deploy ứng dụng mới không?

**Đáp án:** Không. Trước tiên expand/chuẩn bị app V1 tương thích và dual-write, xử lý writers cũ, backfill/validate, chuyển nguồn đọc V2, rồi mới contract khi không còn dependency.

### Bài 2 — Dữ liệu fixture D0

Fixture có sáu customer, ba order, ba relationship. Sau tạo fixture, `count(c.displayName)` bằng bao nhiêu?

**Đáp án:** **0**, vì chỉ có `legacyName`. `count(c.legacyName)=6`; order và relationship đều là 3.

### Bài 3 — Backfill một phần

Chạy backfill cho C001 và C002. Số khách hàng có cả hai trường là bao nhiêu và còn thiếu trường mới bao nhiêu?

**Đáp án:** **2** khách hàng có cả hai, **4** khách hàng còn thiếu `displayName`; tổng vẫn 6.

### Bài 4 — Lỗi old-only writer

Sau D2, V0 sửa `C002.legacyName` từ “Bình” sang “Bình sửa”, không cập nhật `displayName`. Query chỉ đếm `displayName IS NULL` phát hiện lỗi không?

**Đáp án:** Không. `displayName` vẫn tồn tại và là “Bình”; cần đếm `legacyName <> displayName`. Chỉ chuyển đọc mới sau khi loại writer cũ và reconcile.

### Bài 5 — Idempotent backfill

Vì sao câu query batch mục 11.2 có thể chạy lại mà không tạo thêm customer?

**Đáp án:** Nó `MATCH` theo các node đã tồn tại và `SET` property, không `CREATE` node; chỉ sửa record còn thiếu/lệch. Cần vẫn kiểm soát nguồn sự thật và concurrent writes.

### Bài 6 — Java transaction

Tại sao ghi `legacyName` và `displayName` trong **hai transaction riêng** là nguy hiểm?

**Đáp án:** Một transaction có thể commit còn transaction kia lỗi; reader thấy hai giá trị khác nhau. Đặt cả hai trong một transaction và dùng retry idempotent.

### Bài 7 — Relationship migration

Ba cặp customer/order có cả cạnh `QA008_PLACED` và `QA008_ORDERED`. `count(*)` trên pattern hai type và `count(DISTINCT o)` là bao nhiêu?

**Đáp án:** `count(*)=6` cạnh, nhưng `count(DISTINCT o)=3` order duy nhất trong fixture. Tùy nghiệp vụ phải định danh relationship chính xác, không mặc định loại duplicates bằng DISTINCT ở mọi trường hợp.

### Bài 8 — Khi nào bỏ legacy?

Nếu V2 đang đọc mới nhưng vẫn có một batch job hàng tuần chỉ đọc `legacyName`, có được xóa trường cũ sau hai ngày không?

**Đáp án:** Không. Chưa vượt được gate “mọi consumer đã chuyển”. Cần nâng batch job và quan sát ít nhất chu kỳ phù hợp, thử rollback/restore trước contract.

### Bài 9 — Index mới và query cũ

Tại sao không drop index cũ ngay khi tạo index trên `displayName`?

**Đáp án:** Các instance/job cũ vẫn query `legacyName` và có thể dựa vào index cũ. Cần đo `EXPLAIN/PROFILE`, inventory phụ thuộc và chỉ drop khi không còn reader cũ.

### Bài 10 — Nâng phiên bản server

Một cluster vừa nâng major Neo4j. Có thể quay lại binary cũ như rollback ứng dụng Java không?

**Đáp án:** Không mặc định. Store-format/version compatibility có thể không cho downgrade trực tiếp; chỉ dùng lộ trình hỗ trợ hoặc restore backup phù hợp.

### Bài 11 — Rollback sau D3

Tất cả node đã xóa `legacyName`. Nhóm đổi lại app V0 vì lỗi giao diện. Có an toàn không?

**Đáp án:** Không. V0 đọc field đã bị xóa. Cần forward-fix, chuyển app tương thích hoặc khôi phục/biến đổi dữ liệu có kiểm soát; không chỉ đổi image ứng dụng.

### Bài 12 — Mục tiêu test đúng

Một test chỉ assert hai phiên bản ứng dụng trả cùng chuỗi tên nhưng không có expected từ fixture. Có đủ kiểm chứng không?

**Đáp án:** Chưa. Cả hai có thể cùng trả giá trị sai. Cần expected literal theo business ID, dữ liệu graph thực và đối soát null/divergence/relationships.

## 26. Dọn dữ liệu thực hành và tài liệu chính thức

### 26.1. Cleanup — chỉ database thử nghiệm

Sau khi hoàn thành bài, có thể xóa **chính fixture**:

~~~cypher
MATCH (n)
WHERE n:QA008Customer OR n:QA008Order
DETACH DELETE n;
~~~

~~~cypher
DROP INDEX qa008_customer_display_name IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa008_customer_id_unique IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa008_order_id_unique IF EXISTS;
~~~

Kiểm tra:

~~~cypher
MATCH (n)
WHERE n:QA008Customer OR n:QA008Order
RETURN count(n) AS remaining;
~~~

**Đáp án:** `remaining=0`. Nếu chạy thí nghiệm relationship type mới, các cạnh cũng bị xóa do `DETACH DELETE`. Không chạy cleanup ở database dùng chung label test với dữ liệu khác.

### 26.2. Tài liệu chính thức nên tra theo phiên bản

- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/): lộ trình nâng cấp server/store, chuẩn bị backup và các giới hạn tương thích.
- [Neo4j Operations Manual — Upgrade and migration](https://neo4j.com/docs/operations-manual/current/upgrade/): quy trình phiên bản/edition/topology và cách vận hành an toàn.
- [Neo4j Operations Manual — Schema indexes](https://neo4j.com/docs/cypher-manual/current/indexes/): tạo, quan sát và đánh giá index cho truy vấn.
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/): uniqueness, property constraints và giới hạn edition.
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/): xử lý lô, implicit transactions và cú pháp theo version.
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/): managed transactions, retry và idempotency.
- [Neo4j Java Driver Manual — Performance](https://neo4j.com/docs/java-manual/current/performance/): reuse Driver, batching và database selection.
- [Spring Data Neo4j Reference — Object mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/): `@Node`, `@Property`, `@Relationship` và converter.
- [Spring Data Neo4j Reference — Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html): Cypher riêng, graph projection và rủi ro hydrate thiếu quan hệ.
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/): backup và diễn tập phục hồi phù hợp phiên bản/edition.

**Ghi nhớ:** Một thay đổi tương thích không phải chỉ thêm một property hoặc chạy một script. Nó là **hợp đồng giữa nhiều phiên bản ứng dụng, dữ liệu và Neo4j**, được bảo vệ bằng **expand → migrate → contract**, writer inventory, dual-write atomic, backfill idempotent, kiểm tra missing/divergence, canary, metrics và khả năng rollback. **Chỉ xóa định dạng cũ khi không còn ai đọc/ghi nó và kế hoạch phục hồi đã cập nhật.**
