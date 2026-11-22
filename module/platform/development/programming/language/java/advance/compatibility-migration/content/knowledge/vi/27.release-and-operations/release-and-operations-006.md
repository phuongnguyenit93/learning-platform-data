# Quay lui JDK hoặc ứng dụng khi dữ liệu và dependency đã thay đổi

## 1. Vì sao rollback sau Java migration không đơn giản là đổi lại image?

Một đợt **Java Advance Compatibility Migration** có thể bao gồm nhiều thay đổi cùng lúc: JDK 17 lên JDK 21, framework và ORM lên major version mới, dependency mới, định dạng thông điệp mới, schema database mới, cách mã hóa dữ liệu mới và cấu hình container mới. Ban đầu mọi thứ hoạt động, nhưng sau khi phát hành một regression xuất hiện: p99 tăng, transaction sai, một thư viện native crash hoặc consumer cũ không đọc được dữ liệu.

Phản ứng tự nhiên là **quay lại JDK hoặc bản ứng dụng trước đó**. Tuy nhiên, việc deployment quay về artifact cũ không đồng nghĩa dữ liệu đã được ghi bởi artifact mới vẫn đọc được, không đồng nghĩa dependency cũ vẫn tồn tại và cũng không bảo đảm hệ thống ngoài (database, broker, cache, search index, object storage) trở lại trạng thái tương thích.

Ví dụ:

~~~text
Trước migration:
  App A + JDK 17 + ORM cũ + Schema S1

Triển khai mới:
  App B + JDK 21 + ORM mới + Schema S2

Trong thời gian App B chạy:
  - Ghi cột mới, bỏ cột cũ
  - Phát event schema v2
  - Ghi session hoặc cache theo format mới
  - Thay đổi sequence/ID và trạng thái transaction

Phát hiện lỗi → triển khai lại App A + JDK 17
  - App A có đọc được Schema S2?
  - App A có đọc được dữ liệu B đã ghi?
  - Consumer cũ có đọc được event v2?
  - Config/dependency cũ còn chạy trên hạ tầng hiện tại?
~~~

Kết luận quan trọng: **rollback thành công là khôi phục khả năng phục vụ đúng hợp đồng nghiệp vụ, không chỉ đưa một process cũ về trạng thái Running**.

Bài học thuộc chương **Phát hành và vận hành**, tập trung vào rollback khi cả Java runtime, application artifacts, dependency và dữ liệu đã thay đổi.

Sau bài học, người đọc có thể:

1. Phân biệt rollback JDK, application, configuration, schema và dữ liệu.
2. Xác định khi nào rollback tại chỗ an toàn và khi nào phải dùng forward fix hoặc khôi phục có kiểm soát.
3. Thiết kế migration database tương thích hai chiều trong một cửa sổ phát hành.
4. Phân tích compatibility với ORM, framework, serialization, message schema, cache/session và security.
5. Xây dựng rollback plan dựa trên RTO, RPO, backup/PITR và tính toàn vẹn nghiệp vụ.
6. Tổ chức canary/blue-green/rolling deployments cùng compatibility gates.
7. Viết runbook và diễn tập trên staging trước khi cho production migration.
8. Đo và chứng minh rollback bằng chức năng, dữ liệu và chỉ số vận hành thực tế.

## 2. Phân biệt năm loại rollback

| Loại | Thay đổi gì? | Điều không tự được khôi phục |
|---|---|---|
| **JDK rollback** | JVM/JDK runtime về bản trước. | Source/binary mới, schema DB, event, dependency và config có thể vẫn mới. |
| **Application rollback** | Container image/JAR/WAR và application config về release trước. | Database và state ngoài process không tự quay về. |
| **Configuration rollback** | JVM flags, feature flags, endpoints, certificates hoặc deployment manifest. | Code và dữ liệu đã ghi có thể vẫn thay đổi. |
| **Schema rollback** | DDL/database schema về hình thái trước. | Dữ liệu đã biến đổi có thể bị mất hoặc không chuyển ngược được. |
| **Data recovery/restore** | Đưa dữ liệu về snapshot/backup hoặc khôi phục theo log. | Giao dịch phát sinh sau điểm khôi phục, side effects và state các hệ khác. |

Một release có thể cần phối hợp nhiều loại. Ví dụ phải rollback container image và application config nhưng **giữ nguyên schema đã mở rộng** để không mất dữ liệu mới. Hoặc có thể giữ image hiện tại và chỉ tắt feature flag gây sự cố. Trong trường hợp phá hủy dữ liệu, phải đánh giá restore, reconciliation hoặc forward fix trước khi thao tác.

### 2.1. Rollback không luôn là lựa chọn tốt nhất

Ba chiến lược chính:

- **Rollback:** chạy lại phiên bản cũ khi nó vẫn tương thích với state mới.
- **Forward fix:** phát hành bản sửa tương thích với state hiện tại, không cố quay dữ liệu về quá khứ.
- **Recovery/restore:** phục hồi dữ liệu từ backup/PITR và xử lý lại các sự kiện cần thiết; đây có thể là thao tác gây gián đoạn và cần kế hoạch riêng.

Nếu bản mới đã thay đổi dữ liệu theo cách không đảo ngược, chạy app cũ có thể gây lỗi nghiêm trọng hơn. Khi đó forward fix hoặc chế độ chỉ đọc để bảo vệ dữ liệu có thể an toàn hơn.

### 2.2. Điều kiện tối thiểu để rollback tại chỗ

Rollback về App A/JDK cũ chỉ nên xem là hợp lệ khi đã xác minh:

1. Artifact A vẫn khởi động được trên runtime/hạ tầng đích.
2. Dependency, agent, native library và TLS/security policy của A còn phù hợp.
3. A đọc được schema và dữ liệu đã được B ghi.
4. A ghi dữ liệu mới mà không phá contract của các thành phần còn chạy B.
5. A đọc/xử lý được message/cache/session hiện còn tồn tại hoặc có cơ chế cách ly.
6. Không có irrecoverable side effect mới khiến A hành xử sai.
7. Runbook có bằng chứng diễn tập và người có quyền quyết định.

Thiếu một điều kiện quan trọng phải chuyển trạng thái sang **ROLLBACK BLOCKED / cần phương án khác**, không “thử trước rồi tính”.

## 3. State là thứ làm rollback khó

Trong service stateless, thay binary có thể tương đối đơn giản. Nhưng ứng dụng doanh nghiệp thường không thực sự stateless dù container có thể bị thay bất cứ lúc nào.

State có thể nằm ở:

~~~text
                       Application release
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
      Database              Message bus          Shared cache
          │                    │                    │
          ▼                    ▼                    ▼
   Schema + rows         Events + offsets       Keys + serialized
   + procedures          + consumers            values + sessions
          │                    │                    │
          ├────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
   Object storage        Search indexes       External systems
   + file formats        + mappings            payment/email/API
~~~

Ngay khi JAR cũ chạy được trên JDK cũ, một phần state có thể đã ở định dạng hoặc semantics của bản mới.

### 3.1. State kỹ thuật và state nghiệp vụ

**State kỹ thuật**: cache entries, sessions, serialization metadata, search index mappings, job checkpoints và broker offsets.

**State nghiệp vụ**: đơn hàng, thanh toán, tồn kho, số dư, lịch sử thay đổi, trạng thái hợp đồng và chứng từ.

Cache có thể được flush có kiểm soát khi chấp nhận mất hiệu quả caching; còn transaction đã được ghi nhận hoặc một payment đã thực hiện bên ngoài không thể bị xóa chỉ vì muốn quay về release cũ.

### 3.2. Rollback binary không rollback giao dịch đã commit

Ví dụ App B tạo đơn hàng #501 và thực hiện charge qua payment gateway. Nếu DB được restore về trước lúc đơn hàng được tạo, cổng thanh toán vẫn có thể đã thu tiền.

~~~text
T0: DB backup
T1: App B tạo Order #501
T2: Payment provider charge thành công
T3: Phát hiện bug, restore DB về T0

DB: không còn Order #501
Payment provider: vẫn có giao dịch tại T2
~~~

Do vậy, khôi phục dữ liệu có thể cần **reconciliation**, bù trừ (compensating transaction), đối chiếu ledger và audit trail, không phải chạy một câu SQL DOWN.

## 4. Compatibility matrix trước khi phát hành

Khi có hai phiên bản App A (cũ), App B (mới) và schema S1/S2, hãy đánh giá các tổ hợp:

| Tổ hợp | Mục tiêu | Câu hỏi cần chứng minh |
|---|---|---|
| A + S1 | Baseline | Release cũ đang phục vụ đúng không? |
| B + S1 | Rolling start | B chạy được trước khi schema migration hoàn tất không? |
| A + S2 | Rollback | A có tiếp tục đọc/ghi đúng trên schema mở rộng không? |
| B + S2 | Target | B chạy tốt sau migration không? |
| A/B cùng chạy trên S2 | Mixed-version window | Hai app có ghi dữ liệu không mâu thuẫn không? |

Trong **expand-contract**, điều kiện A + S2 thường là chìa khóa rollback. Nếu schema S2 xóa cột bắt buộc của A, chiến lược rollback code về A có thể không còn an toàn.

### 4.1. Ma trận cần thêm JDK, dependency và state

Mô hình thực tế gồm nhiều trục:

~~~text
Java runtime:    JDK 17 / JDK 21
Application:     App A / App B
Schema:          S1 / S2
Data format:     V1 / V2
Events:          E1 / E2
Dependencies:    D1 / D2
Environment:     image, OS, agent, config
~~~

Không nhất thiết thử mọi tích Descartes nếu chi phí quá lớn; cần thử những tổ hợp sẽ tồn tại trong rollout và rollback, đặc biệt **A đọc state do B tạo**.

### 4.2. Phân biệt đọc và ghi

Tương thích đọc chưa đủ. Ví dụ App A đọc được cột mới nhưng khi cập nhật một record nó có thể ghi null vào trường không biết, làm mất dữ liệu do B tạo.

Đối với mỗi data type, nên hỏi:

- A có đọc được record B tạo?
- A có cập nhật được mà không xóa metadata mới?
- B có đọc được record A tạo?
- A và B cùng ghi một record có vi phạm invariant?
- Những consumer ngoài ứng dụng xử lý event/schema nào?

Một **write compatibility test** có giá trị hơn chỉ thử SELECT một dòng.

## 5. Vòng đời migration: expand → migrate → contract

Một chiến lược database thường dùng để giữ cửa sổ rollback là **expand-contract**.

~~~text
S1 + App A
   │
   ▼
EXPAND: thêm cấu trúc mới, giữ cấu trúc cũ
   │
   ▼
S2-compatible + App A vẫn chạy
   │
   ▼
App B chuyển dần đọc/ghi theo mô hình mới
   │
   ▼
BACKFILL / VERIFY / CUTOVER
   │
   ▼
Quan sát đủ cửa sổ rollback
   │
   ▼
CONTRACT: chỉ xóa phần cũ khi không còn consumer
~~~

**Expand:** thêm cột/bảng/index/format tương thích, không xóa ngay thứ mà bản cũ đang phụ thuộc.

**Migrate:** backfill dữ liệu, dual-read/dual-write hoặc chuyển writer có kiểm soát; theo dõi trạng thái và correctness.

**Contract:** loại bỏ schema/API/format cũ sau khi toàn bộ consumers đã chuyển và rollback về A không còn trong phạm vi hỗ trợ.

### 5.1. Cửa sổ tương thích

Trong một khoảng thời gian, schema nên phục vụ cả App A và App B:

~~~text
T0   S1 + A
T1   Expand S2
T2   Deploy B canary, A và B cùng tồn tại
T3   B toàn bộ, giữ schema cũ
T4   Hết rollback window / đạt conditions
T5   Contract: drop cột/bảng cũ
~~~

Sau T5, rollback về A có thể không còn được hỗ trợ. Điều này cần được ghi trong release plan thành **rollback boundary**, không chỉ là ghi chú trong pull request.

### 5.2. Không ép tất cả vào một lần deploy

Một release có thể gồm ít nhất ba lần thay đổi độc lập:

1. Database expand migration.
2. Application cutover và backfill.
3. Database contract cleanup.

Việc tách rollout làm tăng cơ hội dừng đúng điểm và rollback app mà không cần restore DB. Nhưng nó cũng đòi hỏi quản lý trạng thái migration và tương thích trong thời gian chuyển tiếp.

## 6. Ví dụ: đổi cột name thành display_name an toàn

Giả sử bản cũ dùng bảng:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
~~~

Mục tiêu bản mới là sử dụng display_name. Một migration nguy hiểm:

~~~sql
ALTER TABLE customer RENAME COLUMN name TO display_name;
~~~

Nếu App A vẫn truy vấn customer.name, nó sẽ lỗi ngay sau migration. Đổi tên cột tại chỗ có thể không phù hợp nếu rolling deployment và rollback cần hỗ trợ A.

### 6.1. Bước expand: thêm cột mới

Ví dụ SQL khái niệm:

~~~sql
ALTER TABLE customer
    ADD COLUMN display_name VARCHAR(120);
~~~

Bản cũ tiếp tục đọc/ghi name. Bản mới có thể được thiết kế để đọc display_name khi có, nếu không thì fallback về name.

Đây là ví dụ mô hình dữ liệu; cú pháp, lock behavior và khả năng thay đổi schema online phụ thuộc database engine/version cụ thể.

### 6.2. Backfill dữ liệu

Với bảng nhỏ trong môi trường thử nghiệm:

~~~sql
UPDATE customer
SET display_name = name
WHERE display_name IS NULL;
~~~

Với bảng production lớn, một UPDATE toàn bảng có thể gây transaction dài, lock contention, replication lag và áp lực transaction log. Nên backfill theo batches, có idempotency, throttle và quan sát progress; câu SQL trên chỉ minh họa logic.

Đồng thời cần xử lý **dữ liệu thay đổi trong lúc backfill**. Nếu App A vẫn ghi name sau khi một record đã được backfill, display_name có thể thành stale. Hãy chọn một cơ chế đồng bộ được thiết kế rõ, không giả định backfill một lần là đủ.

### 6.3. Dual-read

Trong bản B:

~~~java
public final class CustomerNameSelector {
    public static String readName(String displayName, String legacyName) {
        return displayName != null ? displayName : legacyName;
    }
}
~~~

Đoạn này minh họa thứ tự đọc, không phải implementation repository đầy đủ. Cần xác định null/empty string có cùng semantics không, và việc hai cột lệch nhau được giải quyết thế nào.

### 6.4. Dual-write hoặc đồng bộ có chủ đích

Trong rollback window, một phương án là B ghi **cả name và display_name** theo cùng giá trị trong một transaction.

~~~text
Write customer name = "Linh"
        │
        ▼
Transaction:
  name         = "Linh"
  display_name = "Linh"
        │
        ▼
Commit
~~~

Nhưng nếu App A vẫn ghi name còn B đọc display_name ưu tiên, dữ liệu có thể lệch. Phải xử lý **writer cũ** bằng một trong những chiến lược đã đánh giá:

- Giữ name là nguồn sự thật trong thời gian mixed-version.
- Sử dụng DB trigger phù hợp để đồng bộ trong giới hạn được duyệt.
- Hạn chế một version làm writer tại từng thời điểm và cho version khác read-only.
- Sử dụng event-driven replication có idempotency và reconciliation, chấp nhận semantics eventual consistency khi phù hợp.

Không bật dual-write ngây thơ trên nhiều service khi chưa giải quyết transaction boundary, retry, ordering và conflict resolution.

### 6.5. Chỉ contract sau khi rollback window kết thúc

Sau khi mọi consumer dùng display_name và không còn cam kết rollback App A:

1. Xác minh tất cả record đã được backfill.
2. Xác minh không còn writer vào name.
3. Thiết lập constraints cho display_name theo dữ liệu và engine phù hợp.
4. Theo dõi trong thời gian đủ để phát hiện consumer còn dùng name.
5. Chỉ sau đó mới cân nhắc loại bỏ cột name.

Việc DROP cột có thể gây mất dữ liệu không thể đảo bằng thao tác schema đơn giản. Quyết định contract cần là một release milestone riêng.

## 7. Database migration tools và giới hạn của DOWN script

Các công cụ như Flyway hoặc Liquibase giúp version và chạy schema migrations có kiểm soát. Chúng hỗ trợ theo dõi phiên bản schema, nhưng **không tự bảo đảm rollback dữ liệu đúng nghiệp vụ**.

### 7.1. Migration thuận không nhất thiết có migration nghịch

Ví dụ:

~~~sql
-- Migration thuận: hợp nhất hai cột
UPDATE person
SET full_name = first_name || ' ' || last_name;
~~~

Khi xóa first_name và last_name, không chắc có thể tách full_name về đúng hai cột ban đầu. Một người có nhiều thành phần tên khiến phép tách bất định.

Đây là **biến đổi mất thông tin**; một DOWN script chỉ làm schema quay lại tên cột cũ không thể tự khôi phục thông tin ban đầu.

### 7.2. Version history không phải backup

Một bảng migration history ghi “schema hiện ở V42” không lưu đầy đủ:

- Giá trị row trước khi thay đổi.
- Transactions đã commit.
- Side effects ngoài database.
- State các hệ thống phụ thuộc.
- Message đã publish và đã được consumer xử lý.

Vì vậy, **migration history và backup/PITR giải quyết hai vấn đề khác nhau**. Cần cả hai khi rủi ro dữ liệu cao.

### 7.3. DDL có thể không transactional

Khả năng rollback DDL trong transaction thay đổi theo database engine và loại thao tác. Một migration có thể tự commit, giữ lock hoặc không cho phép chạy trong transaction.

Trước khi triển khai cần xác nhận:

- Engine/version có hỗ trợ transactional DDL cho câu lệnh cụ thể không?
- Migration chạy trong một transaction hay nhiều transaction?
- Locks/replication lag ảnh hưởng production thế nào?
- Nếu job bị dừng giữa chừng, schema/data ở trạng thái nào?
- Có idempotent resume/repair plan không?

Không dán nguyên một lệnh DROP/ALTER lên production chỉ vì nó chạy được trong test database nhỏ.

## 8. Rollback khi JPA/ORM provider đã thay đổi

Khi nâng JDK thường đi kèm nâng framework hoặc JPA provider, ví dụ thay đổi thế hệ Hibernate, EclipseLink hoặc tích hợp Jakarta Persistence.

Vấn đề rollback có thể nằm ở:

- Mapping annotations và entity scanning.
- Identifier generation, sequence allocation và identity columns.
- Timestamp, timezone, enum và decimal mapping.
- JSON/UUID/custom SQL types.
- Lazy loading, dirty checking, cascade và orphan removal.
- Schema generation/dialect và SQL semantics.
- Transaction propagation, flush và locking.
- Second-level cache và serialized cache entries.

Một entity class cũ có thể compile/chạy được nhưng **ghi dữ liệu sai semantics** khi schema/provider đã thay đổi.

### 8.1. Ví dụ thay đổi cách sinh ID

App A dùng một sequence allocation strategy, App B chuyển sang hi/lo hoặc allocation size khác. Nếu hai bản cùng chạy và dùng chung sequence mà cấu hình không tương thích, có thể xảy ra collision hoặc gap bất thường tùy cách cấu hình.

Trước mixed-version rollout:

1. Chốt chiến lược sinh ID/sequence.
2. Kiểm chứng concurrency giữa A và B.
3. Kiểm tra không tạo duplicate primary keys.
4. Quan sát sequence state và rollback behavior.
5. Không reset sequence về giá trị cũ khi đã có IDs mới.

Không gọi một sequence gap là lỗi dữ liệu nếu mô hình ID không bảo đảm liên tục; điều quan trọng là uniqueness và hợp đồng nghiệp vụ.

### 8.2. Jakarta namespace là binary boundary

Khi từ javax.persistence sang jakarta.persistence, hai API có binary names khác nhau. Rollback framework/JPA provider có thể đòi thay **toàn bộ bundle tương thích**, không phải chỉ giảm một JAR version.

Nếu App A dựa trên framework, Servlet container và ORM thế hệ javax, nhưng môi trường deploy đã chuyển toàn bộ sang Jakarta runtime, thay lại app.jar có thể không chạy được dù JDK vẫn tương thích.

Nên duy trì **image/artifact cũ hoàn chỉnh**, bao gồm runtime/container/provider/config được phê duyệt, thay vì chỉ lưu một file JAR.

### 8.3. Cache của ORM

Các entries second-level cache được mã hóa theo provider/config mới có thể không được provider cũ hiểu. Nếu cache không phải nguồn sự thật, có thể đặt namespace/cache version riêng cho mỗi app release hoặc invalidate có kiểm soát.

Không xóa cache mà không xét ảnh hưởng tải đột biến lên database, cache warmup, session semantics và tính nhất quán của write-through/write-behind caches.

## 9. JDK rollback và bytecode compatibility

Quay runtime từ JDK 21 về JDK 17 yêu cầu bytecode của toàn bộ artifact/runtime dependencies phù hợp với Java 17.

Ví dụ class-file major versions:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Nếu App B được biên dịch thành class major 65, nó không thể chạy trên Java 17 bằng cách chỉ đổi base image. JVM Java 17 sẽ không nạp class Java 21.

### 9.1. Ba kiểu rollback JDK

**Kiểu 1 — App B vẫn nhắm Java 17:**

~~~text
Compiler JDK 21 + javac --release 17
                │
                ▼
App B bytecode Java 17
                │
                ├── Runtime JDK 21
                └── Runtime JDK 17 (nếu dependencies/API tương thích)
~~~

Có thể thử rollback JVM trước khi rollback application, **nếu** mọi dependency, agent, native component và API đều hỗ trợ Java 17. --release 17 không hạ bytecode của dependency bên ngoài.

**Kiểu 2 — App B yêu cầu Java 21:**

~~~text
App B bytecode major 65 + dependency Java 21
                │
                ▼
Không thể chỉ thay JDK 21 bằng JDK 17
~~~

Phải rollback **cả application/dependencies** về bundle tương thích Java 17 hoặc phát hành bản B' nhắm Java 17 nếu kỹ thuật và hợp đồng cho phép.

**Kiểu 3 — Bản mới thay đổi định dạng dữ liệu:**

Ngay cả khi rollback cả app về A + JDK 17, A vẫn có thể không đọc được dữ liệu B đã ghi. Lúc này vấn đề nằm ở state, cần compatibility bridge, forward fix hoặc recovery plan.

### 9.2. Dependency trực tiếp và bắc cầu

JDK rollback cần kiểm tra:

- Maven/Gradle resolved runtimeClasspath.
- Bytecode target của mọi JAR được nạp.
- Java SE APIs mà dependency sử dụng.
- JNI/JNA/native libraries theo OS/architecture/libc.
- Java agent/JVMTI và instrumentation bytecode versions.
- TLS/crypto providers và security configuration.
- Servlet/Jakarta EE application server compatibility.
- Startup flags bị thêm mới hoặc bị loại trên JDK cũ.

Một class major 61 không đảm bảo hoàn toàn tương thích runtime cũ nếu code phụ thuộc native library, API reflective hoặc một dependency ở classpath không phù hợp.

### 9.3. Không nhầm Java toolchain với production runtime

Gradle daemon có thể chạy JDK 21, compiler dùng JDK 21 và options.release 17. Nhưng Docker image production có thể dùng JDK 21 còn rollback image dùng JDK 17.

Phải kiểm tra JDK trong **process production**, không kết luận từ JAVA_HOME của developer hoặc ./gradlew --version trên CI.

## 10. Runtime flags và environment cũng có thể chặn rollback

Quay về JDK cũ nhưng giữ startup flags của JDK mới có thể khiến process không khởi động:

~~~text
Unrecognized VM option
Could not create the Java Virtual Machine
~~~

Ví dụ:

- Một flag GC/JFR/module access không tồn tại trong JDK cũ.
- --add-opens/--add-exports hoặc module names khác nhau.
- Java agent mới yêu cầu JVMTI/JDK mới.
- JDK cũ không xử lý cgroups v2 như JDK mới.
- TLS defaults, truststore hoặc crypto providers khác.
- Native library được build theo OS/architecture mới.

Rollback artifact nên đi kèm **runtime profile cũ được version hóa**:

~~~text
Release bundle:
  application image digest
  JDK image/build
  JVM flags and env/config references
  agents and native dependency versions
  compatible schema/data/event versions
  deployment manifest revision
~~~

Không dùng một tập flags chung bất biến cho mọi JDK version mà không có test. Đặc biệt tránh “ignore unrecognized VM options” để lặng lẽ bỏ qua settings quan trọng.

## 11. Serialization và thay đổi định dạng dữ liệu

Một thay đổi serializer có thể khiến rollback application thất bại dù schema database không đổi.

Các khu vực thường gặp:

- Java Object Serialization.
- JSON field names, enum string values, null handling.
- XML/JAXB bindings và schema namespaces.
- Protobuf/Avro schema evolution.
- Kafka/event payloads.
- Cache/session serialization.
- File objects trong S3-compatible object storage.
- Database JSON/JSONB columns.

### 11.1. Java Object Serialization

Java serialization có các yếu tố tương thích như class name, serialVersionUID, serializable fields và class evolution rules. Nếu B đổi serialVersionUID hoặc class hierarchy không tương thích, A có thể không deserialize object do B ghi.

Ngay cả khi A deserialize được object, **semantics** vẫn có thể sai vì B bổ sung trạng thái mới mà A bỏ qua.

Không khuyến nghị lưu Java native serialization làm định dạng trao đổi dài hạn giữa service độc lập khi không có lý do đặc biệt; với migration, cần versioning và compatibility tests nếu hệ thống đang phụ thuộc vào nó.

### 11.2. JSON: tolerant reader chưa đủ

Ví dụ event v1:

~~~json
{
  "eventType": "OrderCreated",
  "orderId": "o-142",
  "amount": "125.50"
}
~~~

Event v2:

~~~json
{
  "eventType": "OrderCreated",
  "orderId": "o-142",
  "amount": {
    "value": "125.50",
    "currency": "VND"
  },
  "schemaVersion": 2
}
~~~

Nếu App A coi amount là string, nó có thể lỗi khi đọc event do B tạo. Thêm schemaVersion không tự khiến A hiểu cấu trúc mới.

Một hướng an toàn:

1. Giữ event v1 trong compatibility window.
2. Thêm field optional có semantics rõ hoặc phát event type/version riêng.
3. Nâng consumer để đọc v1 và v2 **trước** khi producer đổi sang v2.
4. Chỉ bỏ v1 khi consumer cũ không còn và rollback policy đã thay đổi.

### 11.3. Protobuf/Avro và schema evolution

Những serializer có rules evolution riêng không bảo đảm mọi thay đổi backward/forward compatible. Ví dụ trong Protobuf, cần giữ field numbers, tránh tái sử dụng field đã xóa và tuân thủ semantics của field type/presence.

Với Avro/schema registry, cần phân biệt backward/forward/full compatibility mode và cách writer/reader schema được resolve.

Đối với rollback, **old consumer đọc new writer data** là một điều kiện trực tiếp cần test. Chỉ biết “new reader đọc old data” không chứng minh rollback an toàn.

## 12. Messaging: một event đã phát không thể thu hồi đơn giản

Khi B publish event E2, message có thể đã được:

- Ghi vào Kafka/log hoặc queue bền vững.
- Consumer xử lý và commit offset.
- Gửi tiếp sang system khác.
- Kích hoạt email, payment, notification hoặc index update.

Rollback producer về A không xóa các event đó, cũng không phục hồi consumers đã xử lý.

### 12.1. Các trường hợp phải xác minh

| Tình huống | Câu hỏi rollback |
|---|---|
| A consumer gặp event E2 | Có deserialize/xử lý đúng không? |
| A producer tiếp tục phát E1 | B consumer còn hỗ trợ E1 trong mixed window không? |
| B đã commit offsets | A dùng cùng consumer group có bỏ qua hoặc đọc lại gì không? |
| B đã gửi external side effect | Có thể bù trừ và reconciliation không? |
| B thay partition key | Ordering của business entity có đổi không? |
| B thay idempotency key | Có gây duplicate processing sau retry/rollback không? |

### 12.2. Không reset offsets tùy tiện

Đưa Kafka consumer offset về quá khứ có thể khiến messages được xử lý lại, gây duplicate charges, duplicate email hoặc double writes nếu handler không idempotent.

Một rollback plan cần nêu:

- Offsets/checkpoints do consumer nào sở hữu.
- Cách replay, nếu có.
- Idempotency keys và deduplication window.
- Quarantine/dead-letter policies.
- Reconciliation cho side effects đã thực hiện.

Không tự reset production offsets như một cách “quay lại thời điểm trước release” nếu chưa phân tích semantics nghiệp vụ.

### 12.3. Outbox và transaction boundary

Transactional outbox giúp phối hợp write database với việc phát event theo một số kiến trúc, nhưng rollback vẫn cần đảm bảo schema outbox/payload version và consumer compatibility.

Nếu một release mới thay cấu trúc outbox theo cách A không đọc được, rollback publisher sẽ bị chặn. Nên duy trì payload reader tương thích hoặc tách versioned outbox consumers theo plan.

## 13. Cache và session rollback

Cache/session là dạng state dễ bị xem nhẹ vì có thể mất đi khi restart, nhưng trong hệ phân tán chúng thường nằm ngoài application process.

### 13.1. Cache key và value format

App B có thể chuyển:

~~~text
cache key: customer:42
value: JSON v1
~~~

thành:

~~~text
cache key: customer:v2:42
value: binary schema v2
~~~

Nếu A rollback và đọc customer:42 trong khi B ghi format khác vào cùng key, A có thể deserialize sai. Giải pháp hữu ích là **version namespace** cho cache keys và xác định TTL/invalidation:

- A dùng namespace v1.
- B dùng namespace v2.
- Không ghi đè lẫn nhau.
- Cân nhắc chi phí cache warmup và database load khi rollback.

Không xóa mọi cache trong production mà không tính load spike, consistency semantics và hiệu ứng lên session/authentication.

### 13.2. Session serialization

Với sticky sessions hoặc shared session store, App B có thể thay cấu trúc session object. Khi rollout A/B, user có thể chuyển giữa hai versions và bị logout hoặc gặp lỗi.

Các lựa chọn:

- Dùng session schema backward-compatible trong compatibility window.
- Dùng session affinity tạm thời với giới hạn rõ.
- Version/session namespace; chấp nhận user reauthenticate nếu chính sách cho phép.
- Chuyển session state sang một format ổn định hơn nếu hệ thống yêu cầu rolling upgrade dài hạn.

Với authentication/security state, không thể chỉ flush session tùy tiện nếu ảnh hưởng user obligations hoặc compliance. Phải có chính sách user-facing và security review.

## 14. Database restore, snapshots và Point-in-Time Recovery (PITR)

Nếu dữ liệu đã bị phá hủy hoặc migration không có inverse đúng, nhóm có thể cân nhắc khôi phục từ backup hoặc PITR.

**Snapshot/backup:** bản sao trạng thái tại một thời điểm hoặc theo cơ chế lưu trữ cụ thể.

**PITR:** khả năng khôi phục database tới một điểm thời gian/log position theo cách engine hỗ trợ, thường dựa vào backup cộng với write-ahead logs hoặc cơ chế tương tự.

### 14.1. Hai mục tiêu vận hành

| Khái niệm | Ý nghĩa |
|---|---|
| **RPO — Recovery Point Objective** | Mức mất dữ liệu tối đa chấp nhận được, tính theo thời gian hoặc trạng thái được định nghĩa. |
| **RTO — Recovery Time Objective** | Thời gian tối đa chấp nhận được để khôi phục dịch vụ theo hợp đồng. |

Ví dụ:

~~~text
RPO mục tiêu: 5 phút
RTO mục tiêu: 30 phút
~~~

Không thể kết luận hệ thống đạt các mục tiêu này chỉ vì backup tồn tại. Cần **diễn tập restore thực sự**, đo thời gian và xác nhận dữ liệu/integrity.

### 14.2. PITR không phải phép đảo transaction tùy chọn

Khôi phục database về T0 có thể loại bỏ **mọi giao dịch** xảy ra sau T0, không chỉ những giao dịch bị ảnh hưởng bởi App B. Nó có thể xóa cả giao dịch hợp lệ từ người dùng hoặc service khác.

Do đó, trước khi chọn PITR:

1. Xác định phạm vi database/schema/tenant bị ảnh hưởng.
2. Ước lượng số transactions hợp lệ sẽ bị mất.
3. Xác định side effects đã phát ra ngoài DB.
4. Đánh giá cách replay/reconcile an toàn.
5. Chọn phương án restore sang instance cô lập để so sánh/extract nếu phù hợp.
6. Cần phê duyệt từ data/business owners theo mức rủi ro.

Trong nhiều trường hợp, **restore sang môi trường cô lập rồi sửa dữ liệu có chọn lọc** an toàn hơn việc đưa toàn bộ production DB về quá khứ; lựa chọn phụ thuộc loại hỏng dữ liệu và khả năng đảm bảo consistency.

### 14.3. Backup phải được kiểm chứng

Một backup hợp lệ cần:

- Có thời điểm, retention và phạm vi dữ liệu rõ ràng.
- Có integrity verification.
- Bao gồm hoặc phối hợp đúng schema, transaction logs và encryption keys.
- Có quyền truy cập khi xảy ra sự cố.
- Có kế hoạch restore theo engine/version.
- Được diễn tập trên môi trường phục hồi.
- Có bằng chứng thời gian RTO/RPO thực tế.

**Backup chưa từng thử restore không được coi là phương án rollback chắc chắn.**

## 15. Rollback khi đã thay đổi database engine hoặc driver

Một đợt Java migration có thể nâng JDBC driver hoặc đổi database engine/version.

Rủi ro thường gặp:

- JDBC driver cũ không hỗ trợ database server mới.
- TLS authentication protocol/cipher mặc định khác.
- SQL dialect hoặc reserved keywords thay đổi.
- Timestamp, timezone, JSON/UUID/LOB semantics khác.
- Index/query planner và performance khác.
- Stored procedures, extensions, functions đã thay.
- Database file/storage format không hỗ trợ downgrade engine.

### 15.1. Đừng tự giả định database downgrade

Nếu đã nâng **database server** lên major version mới, quay lại binary database server cũ có thể không được engine hỗ trợ vì storage format hoặc internal catalog changes.

Rollback JDK/app và rollback database server là hai bài toán khác nhau. Có thể cần giữ server mới nhưng chọn driver/app cũ tương thích, hoặc dùng backup/replication strategy được engine hỗ trợ.

### 15.2. Driver và dependency set

Khi rollback application:

1. Xác định JDBC driver của App A.
2. Kiểm tra driver với DB server hiện tại.
3. Kiểm tra Java minimum và TLS/security features.
4. Chạy transaction/query integration tests trên DB representative.
5. Xác nhận pool, failover và timeout behavior.

Không sửa lỗi bằng cách hạ bảo mật TLS hoặc tắt certificate verification.

## 16. Dependency rollback không chỉ là đổi version trong Maven/Gradle

Một dependency upgrade có thể kéo theo breaking changes ở:

- Java minimum runtime và bytecode.
- Public API/binary signatures.
- Jakarta javax/jakarta namespace.
- Native library/OS ABI.
- SQL/serializer defaults.
- Crypto provider/security configuration.
- Framework auto-configuration.
- ServiceLoader/META-INF/services discovery.
- Logging/tracing agent integration.

### 16.1. Lock toàn bộ release bundle

Trong Java build, chỉ giữ pom.xml/build.gradle là chưa đủ nếu dependency versions có thể thay đổi khi resolve.

Một release có thể lưu:

~~~text
Git commit + source revision
Gradle Wrapper/Maven version
Dependency locks hoặc resolved dependency graph
Build JDK, JavaCompile release target
Application artifact checksum
Runtime container image digest
JDK/agent/native dependency builds
Configuration revision
Schema/event compatibility declaration
~~~

Khi rollback, nên triển khai **artifact đã kiểm chứng** thay vì rebuild release cũ với dependency repository hiện tại và hy vọng nhận cùng bytecode.

### 16.2. Nguồn artifact có thể đã biến mất

Một dependency được cung cấp bởi registry nội bộ hoặc vendor cũ có thể không còn truy cập được. Nếu rollback plan dựa vào rebuild “khi có sự cố”, nhóm có thể bị chặn bởi:

- Artifact repository outage.
- Dependency bị unpublish/retire.
- Base image tag đã trỏ sang digest khác.
- Chứng chỉ/credential build đã hết hạn.
- JDK cũ bị rút khỏi hạ tầng vì security policy.

Giải pháp là giữ immutable artifact và runtime images theo retention/security policy, cùng một bản thử triển khai vào môi trường DR/staging.

## 17. Quay lui container image hoặc Java runtime trên Kubernetes

Kubernetes Deployment lưu lịch sử ReplicaSet và hỗ trợ thao tác quản lý rollout. Tuy nhiên, **rollout undo chỉ tác động configuration/deployment history**, không khôi phục state bên ngoài.

Ví dụ lệnh quan sát:

~~~bash
kubectl rollout history deployment/customer-service -n staging
kubectl rollout status deployment/customer-service -n staging
~~~

Ví dụ rollback Deployment có thể dùng trong staging nếu đã xác minh tương thích:

~~~bash
kubectl rollout undo deployment/customer-service -n staging
kubectl rollout status deployment/customer-service -n staging
~~~

Các lệnh trên **không được chạy trong khi soạn bài** và chỉ là ví dụ thao tác trong môi trường được phép. Trước production rollback, cần quyết định đúng revision/image digest, cấu hình, schema và state, không dựa vào revision gần nhất theo cảm tính.

### 17.1. Cạm bẫy của rollout undo

- Revision cũ có thể giữ image tag thay vì immutable digest.
- ConfigMap/Secret có thể đã thay nội dung dù Deployment về revision cũ.
- Database đã chạy migrations mới.
- Queue/cache vẫn chứa state mới.
- Helm/GitOps controller có thể tự reconcile lại desired state hiện tại.
- ReplicaSet history có thể không còn đủ để quay về phiên bản muốn dùng.

Vì vậy, trước khi rollback cần khóa/điều phối nguồn cấu hình GitOps/Helm và chỉ rõ target revision. Không coi kubectl rollout undo là runbook đầy đủ.

### 17.2. Blue-green và canary

Blue-green giữ hai bộ application/runtime để chuyển traffic nhanh khi phù hợp. Canary triển khai dần một phần traffic.

Ưu điểm:

- Có thể giảm blast radius.
- Phát hiện regression sớm.
- Cho phép quay traffic về A nhanh hơn so với rebuild.

Nhưng **blue-green không nhân đôi database state** mặc định. Nếu B đã ghi format mới vào DB chung, chuyển traffic về A vẫn đụng vấn đề compatibility. Cả hai chiến lược chỉ làm rollback binary/traffic dễ hơn khi data contract được thiết kế phù hợp.

### 17.3. Rolling deployment có thời gian A/B cùng tồn tại

Kubernetes có thể để old và new pods phục vụ đồng thời trong rollout. Vì vậy **forward và backward compatibility giữa A/B** không chỉ phục vụ sự cố rollback mà còn là điều kiện của ngay chính rollout bình thường.

Test nên bao gồm:

- A và B cùng đọc/ghi chung database.
- B tạo event mà A consumer có thể thấy.
- Session chuyển giữa pods.
- Phần mềm đọc cache của version khác.
- Backfill đang chạy giữa lúc A/B cập nhật record.

Nếu không bảo đảm mixed-version behavior, cần chiến lược cutover hoặc maintenance window riêng với điều kiện tạm dừng writes rõ ràng.

## 18. Quay lui trên VM/systemd hoặc application server

Với VM/systemd, rollback có thể gồm đổi symlink artifact, đổi JDK executable và sửa unit/drop-in rồi restart service. Nhưng những thao tác này cần được version hóa và kiểm chứng:

~~~text
Release A:
  /opt/apps/customer/releases/A/app.jar
  JDK 17 installation / image
  Config profile A

Release B:
  /opt/apps/customer/releases/B/app.jar
  JDK 21 installation / image
  Config profile B
~~~

Trong ví dụ, một cách triển khai là đặt đường dẫn current về release được chọn bằng cơ chế atomic, rồi restart service có kiểm soát. Không tự đổi JDK với các flags của B còn nguyên nếu JDK A không hỗ trợ chúng.

### 18.1. systemd rollback cần xử lý nhiều thứ

- ExecStart và Java executable thực tế.
- EnvironmentFile, JVM flags và agent paths.
- WorkingDirectory, User/Group, filesystem permissions.
- systemd cgroup CPU/MemoryMax.
- logging/heap dump/truststore.
- service dependency ordering.
- restart policy và graceful shutdown.

Sau khi thay unit/drop-in, cần daemon-reload và restart theo quy trình vận hành; nhưng **restart service không rollback database**.

### 18.2. Application server và WAR

Với Java EE/Jakarta EE, rollback WAR có thể bị chặn bởi:

- Container/server đã nâng sang Jakarta namespace.
- DataSource/JNDI names thay đổi.
- JPA/Validation implementation do server cung cấp.
- Servlet filter/REST providers không tương thích.
- Session replication state/version.

Nếu version A dùng javax.servlet nhưng server đã chuyển sang jakarta.servlet, chỉ deploy lại WAR A có thể không chạy. Cần rollback cả server/runtime bundle hoặc có một target deployment tương thích.

## 19. Quản lý rollback boundary rõ ràng

Một **rollback boundary** là mốc sau đó việc quay về release trước không còn được bảo đảm theo cách thông thường.

Ví dụ:

~~~text
Phase 1: Expand schema
  Rollback App A: SAFE nếu tests chứng minh

Phase 2: Deploy App B, dual-read/write
  Rollback App A: SAFE WITH CONDITIONS

Phase 3: B writes new-only event/data
  Rollback App A: BLOCKED nếu A không đọc được

Phase 4: Contract/drop legacy column
  Rollback App A: NOT SUPPORTED
~~~

Mỗi boundary cần chỉ rõ:

- Change/release nào tạo boundary.
- Mốc thời gian, flag hoặc migration ID.
- Tại sao rollback trở nên nguy hiểm.
- Ai được phê duyệt vượt boundary.
- Có forward fix/recovery plan nào thay thế.
- Backup/PITR/checkpoint còn khả dụng đến lúc nào.

Không đưa một destructive migration vào cùng pipeline release mà không ghi nhận nó làm đóng cửa sổ rollback.

### 19.1. Nguyên tắc “stop the world” khi nguy hiểm

Nếu vừa phát hiện dữ liệu bị ghi sai format, tiếp tục để App B phục vụ writes có thể làm tăng lượng dữ liệu cần sửa. Một incident runbook có thể yêu cầu:

1. Tạm ngừng feature hoặc write path gây hại.
2. Đưa API vào read-only/maintenance mode nếu được thiết kế và phù hợp nghiệp vụ.
3. Giữ bằng chứng và state hiện tại để phân tích.
4. Đánh giá rollback A có thể đọc state hay không.
5. Chọn rollback, forward fix hoặc recovery theo quyết định đã duyệt.

Chế độ read-only cần được kiểm thử từ trước; nếu một số background workers vẫn ghi DB, việc tắt HTTP write endpoints chưa chắc đã ngừng dữ liệu thay đổi.

## 20. Feature flags để tách code deploy và thay đổi dữ liệu

Feature flags có thể cho phép deploy code hỗ trợ cả mô hình cũ và mới, sau đó kích hoạt hành vi mới riêng.

Một ví dụ:

~~~text
Phase A:
  new_reader_enabled = true
  new_writer_enabled = false

Phase B:
  new_reader_enabled = true
  new_writer_enabled = true
  legacy_writer_enabled = true

Phase C:
  all consumers upgraded
  legacy_writer_enabled = false

Phase D:
  compatibility window ended
  remove old schema
~~~

Tên flags là mô hình minh họa, không có sẵn trong framework nào. Thứ tự phải được điều chỉnh theo đặc tính dữ liệu, tránh bật writer mới trước khi old readers có thể đọc.

### 20.1. Kill switch khác rollback binary

Khi B gặp lỗi ở một feature mới, tắt feature flag có thể là cách giảm sự cố nhanh mà không rollback JDK/framework. Tuy nhiên, flag chỉ làm dừng hành vi tương lai, **không tự đảo dữ liệu đã ghi**.

Runbook cần ghi:

- Flag nào vô hiệu hóa writer mới.
- Flag update có được apply ngay hay cần restart.
- Các background jobs và consumers có tôn trọng flag không.
- Dữ liệu đã tạo có cần reconciliation không.
- Có thể rollback B binary sau khi tắt flag không.

### 20.2. Flag không miễn phép kiểm tra concurrency

Khi nhiều phiên bản cùng chạy, propagation của flag không tức thời. Có thể tồn tại khoảng thời gian pod A/B áp dụng flags khác nhau. Nếu yêu cầu atomic cutover, phải thiết kế cơ chế đồng bộ/leader election/write gating phù hợp.

## 21. Diễn tập rollback trước production

Một rollback plan chưa được thử là giả định. Diễn tập nên chứng minh **tổ hợp code cũ + state mới** vận hành theo hợp đồng.

### 21.1. Kịch bản kiểm thử staging

~~~text
1. Khởi tạo dữ liệu baseline trên App A + Schema S1.
2. Chạy expand schema migration.
3. Deploy App B + JDK mục tiêu.
4. Tạo/đổi dữ liệu và phát events bằng B.
5. Chạy backfill/dual-write theo đúng quy trình.
6. Dừng/giảm traffic B theo runbook.
7. Deploy lại App A + JDK cũ + config cũ.
8. Cho A đọc và cập nhật những record do B tạo.
9. Chạy business invariants và consumer tests.
10. Xác nhận không mất dữ liệu, không duplicate side effects.
~~~

Đây là bài diễn tập rollback thực sự hơn là chỉ khởi động App A trên một database trắng chưa có dữ liệu mới.

### 21.2. Các bài test bắt buộc

| Nhóm | Điều kiện nghiệm thu |
|---|---|
| Startup | App A/JDK cũ khởi động với schema hiện tại và runtime profile cũ. |
| Read | A đọc record do B tạo và backfill record không lỗi. |
| Write | A update record do B tạo mà không phá dữ liệu mới cần bảo tồn. |
| Transactions | Commit/rollback, idempotency và constraints giữ đúng. |
| Events | A đọc events đã được B publish hoặc cơ chế quarantine hợp lệ. |
| Sessions/cache | Không crash/deserialize sai; có chiến lược invalidation. |
| External effects | Không double-charge/double-notify khi retry hoặc replay. |
| Security | Authentication, authorization và TLS vẫn đúng. |
| Operational | Liveness/readiness, GC, memory và shutdown PASS. |
| Recovery | Restore/PITR drill đạt RTO/RPO khi cần. |

### 21.3. Dữ liệu thử nghiệm phải mang đặc tính migration

Đừng chỉ dùng 3 record đơn giản. Nên có:

- Null/legacy fields, unicode, timezone, decimal precision.
- Bản ghi cũ/chưa backfill và bản ghi mới.
- Concurrent updates và retry.
- Transaction thất bại giữa chừng.
- Entity có associations/cascade phức tạp.
- Event schemas nhiều phiên bản.
- Người dùng có session được tạo bởi A và B.
- Record đã có external side effects.

Phải bảo vệ dữ liệu nhạy cảm; dùng dữ liệu tổng hợp hoặc đã được ẩn danh theo chính sách.

## 22. Thiết kế quality gates trước và sau rollback

Một migration có thể áp dụng các gates:

~~~text
PRE-RELEASE:
  Compatibility matrix tests
  Schema expand/backfill dry run
  Restore/PITR drill
  JDK + dependency runtime test

ROLLOUT:
  Canary and business metrics
  Data integrity reconciliation
  Read/write compatibility checks

ROLLBACK DECISION:
  Boundary check
  Stop harmful writes
  Select safe target bundle
  Evaluate external side effects

POST-ROLLBACK:
  Functional invariants
  Data correctness
  Error rate/latency/GC
  Events and reconciliation
~~~

### 22.1. Hard blockers

Ví dụ điều kiện chặn quay lui:

- A không thể đọc dữ liệu đã được B ghi.
- B đã chạy destructive schema migration mà A còn phụ thuộc.
- Event schema mới không có old-reader compatibility.
- A thiếu critical security fix trong môi trường hiện tại.
- A/JDK cũ không khởi động được với OS/container/native dependencies mới.
- Backup/restore plan chưa được kiểm chứng trong sự cố mất dữ liệu.
- Đang có irreversible external side effects chưa được xử lý.

Những blocker không nên được bỏ qua chỉ vì rollback image nhanh.

### 22.2. Khi nào chỉ cần cấu hình rollback?

Nếu regression do -XX flag mới, số GC threads, container CPU limit hoặc sai feature flag mà code/data vẫn tương thích, có thể rollback **configuration** mà không rollback application. Nhưng phải test rằng thay đổi config khắc phục sự cố và không gây tác động phụ.

Đặc biệt, đừng downgrade JDK chỉ để sửa một JVM flag lỗi khi có thể sửa flags an toàn ngay trên JDK mục tiêu.

## 23. Quy trình quyết định khi production xảy ra sự cố

Một decision tree:

~~~text
Phát hiện regression sau Java migration
                │
                ▼
Có ảnh hưởng dữ liệu hoặc security không?
         │                 │
        Có               Chưa rõ/Không
         │                 │
         ▼                 ▼
Ngừng write path nguy hiểm    Thu thập runtime metrics,
và đánh giá integrity         xác định lỗi
         │                 │
         └────────┬────────┘
                  ▼
          Có thể rollback config/flag?
             │             │
            Có            Không
             │             │
             ▼             ▼
       Thực hiện có     App A có tương thích
       kiểm chứng        với state mới không?
                           │             │
                          Có            Không
                           │             │
                           ▼             ▼
                     Rollback bundle   Forward fix hoặc
                     đã được thử       recovery/reconciliation
                           │             │
                           └──────┬──────┘
                                  ▼
                      Kiểm chứng data + SLO
                      rồi mới đóng incident
~~~

Quy trình này mang tính định hướng. Trong incident thật, runbook phải có quyền hạn, trách nhiệm, escalation, security/data owners, communication và các bước phù hợp hạ tầng.

### 23.1. Đừng phá bằng chứng trước khi chẩn đoán

Nếu tiến trình crash hoặc dữ liệu bị corrupt:

- Lưu application/JVM logs, traces và metrics theo retention policy.
- Ghi image digest, JDK version, flags và schema migration IDs.
- Giữ stack traces/core/heap dumps theo chính sách an toàn thông tin.
- Lưu snapshot/checkpoint nếu phù hợp và được phê duyệt.
- Tránh xóa queue/DLQ hoặc clear DB tables tùy tiện.

Các dữ liệu chẩn đoán có thể chứa PII/secrets; chỉ chia sẻ trong kênh nội bộ được phép, không gửi công khai.

## 24. Runbook mẫu cho rollback App B → App A

Runbook nên viết trước deployment, được review và diễn tập. Mẫu:

~~~text
RUNBOOK: rollback customer-service B -> A

1. Trigger:
   - Error/latency/data-integrity thresholds breached
   - Incident owner authorizes rollback assessment

2. Preconditions:
   - Schema at expected compatible version
   - App A can read B-produced data/events
   - App A runtime image/JDK available and approved
   - No unresolved irreversible data change

3. Containment:
   - Pause harmful write paths/background jobs
   - Preserve current metrics/logs and state snapshot
   - Announce incident/change window

4. Choose action:
   - Config/feature flag rollback
   - Binary/runtime rollback
   - Forward fix
   - Recovery/PITR with data owner approval

5. Execution:
   - Select immutable release bundle A
   - Coordinate GitOps/Helm/systemd desired state
   - Shift traffic / deploy and monitor rollout
   - Do not run destructive schema down migrations
     without a separately approved data plan

6. Validation:
   - Functional critical paths
   - Reads/writes to migrated records
   - Event processing, sessions/cache
   - Data reconciliation and external effects
   - Operational SLOs, GC, OOM and restarts

7. Completion:
   - Incident owner records outcome
   - Backfill/replay and monitoring follow-ups
   - Re-enable traffic/writers when safe
   - Document residual risks and next release plan
~~~

Runbook trên là **template hướng dẫn**, không phải lệnh tự động để chạy trực tiếp. Phải thay bằng thông tin service, dashboard, owner, artifact digests và điều kiện thực tế.

### 24.1. “Ai quyết định?” quan trọng như “Chạy lệnh nào?”

Với sự cố ảnh hưởng dữ liệu hoặc giao dịch tài chính, quyết định restore/PITR có thể cần:

- Incident commander/on-call.
- Application owner.
- DBA/data platform owner.
- Security/compliance nếu liên quan.
- Product/business owner đối với RPO hoặc transaction reconciliation.

Khi quyền phê duyệt không rõ, đội vận hành có thể lãng phí thời gian trong incident hoặc thực hiện thao tác mất dữ liệu không được chấp thuận.

## 25. Các tình huống phức tạp thường gặp

### 25.1. B đã thêm NOT NULL constraint mới

Nếu App A không cung cấp giá trị trường mới, rollback có thể làm INSERT thất bại. Có thể tránh bằng cách chỉ áp constraint sau khi tất cả writers tương thích, hoặc dùng default/backfill có semantics rõ trong compatibility window.

Không bỏ constraint quan trọng tùy tiện để App A chạy lại nếu điều đó có nguy cơ làm mất invariants.

### 25.2. B đã đổi Enum values

App B lưu trạng thái ORDER_PENDING_REVIEW, nhưng enum của App A không có giá trị này. Khi A đọc record, ORM/JSON mapping có thể ném exception.

Giải pháp có thể gồm:

- Nâng A để tolerant-read unknown values trước khi B ghi giá trị mới.
- Feature gate để không tạo value mới trong rollback window.
- Adapter/translation có ý nghĩa nghiệp vụ được duyệt.

Không tự map mọi trạng thái mới sang một trạng thái cũ ngẫu nhiên, đặc biệt trong xử lý payment/order.

### 25.3. B đã ghi JSON format mới vào cùng DB column

Dù schema database không đổi, content JSON có thể không tương thích với old parser. Điều này minh họa **schema-level compatibility không đồng nghĩa data-level compatibility**.

Nên version payload và có old-reader tests hoặc dùng new column/new namespace khi format thay đổi không tương thích.

### 25.4. B đã bật Java serialization mới cho session

Nếu App A không deserialize được session mới, có thể cần logout/recreate sessions hoặc tách session namespace. Quyết định có thể ảnh hưởng user experience và bảo mật, cần kiểm soát và thông báo tùy sản phẩm.

### 25.5. B đã cập nhật JDBC driver vì database bật TLS policy mới

Quay về App A với driver cũ có thể không kết nối được do TLS/authentication change. Cần giữ một driver release vừa tương thích App A vừa đáp ứng security policy, hoặc forward-fix A branch đã kiểm chứng.

Không hạ TLS/security settings chỉ để khôi phục kết nối nếu vi phạm policy.

### 25.6. B đã phát event mà external consumer không thể xử lý

Rollback producer về A không sửa event E2 đã nằm trong broker. Cần phân loại, quarantine/replay, schema translation hoặc cập nhật consumer có kiểm soát; side effects đã phát phải được reconciliation.

### 25.7. B đã tăng tốc nhưng gây sai số tính toán

Nếu B đổi thuật toán floating point/BigDecimal rounding hoặc locale, dữ liệu đã ghi có thể khác trước. Rollback A không tự sửa historical rows. Cần xác định phạm vi affected transactions, luật làm tròn chuẩn, audit trail và kế hoạch correction có phê duyệt.

### 25.8. Native agent chỉ hỗ trợ JDK mới

Một instrumentation agent hoặc JNI library chỉ có binary cho JDK/OS mới có thể ngăn rollback runtime. Release bundle A phải có agent/native dependency tương ứng hoặc có policy vận hành an toàn khi agent không thể load.

Không tự tắt agent bảo mật bắt buộc mà không có cơ chế kiểm soát thay thế.

### 25.9. Search index đã đổi mapping

App B tạo index format mới, A query theo mapping cũ có thể lỗi hoặc trả kết quả khác. Cần hỗ trợ index alias/version, khả năng dual-index hoặc rebuild có thể giám sát; rolling app rollback không tự biến index về dạng cũ.

### 25.10. Mã hóa dữ liệu hoặc key rotation

Nếu B bắt đầu mã hóa bằng format/key mới, A có thể không decrypt. Một cách an toàn thường là **new reader supports old keys trước**, duy trì key lifecycle theo security policy và không xóa key cũ trước khi có kế hoạch decryption/re-encryption hoàn chỉnh.

Không lưu plaintext hoặc đưa key ra logs để “chữa cháy”. Key revocation/retention cần được phối hợp với security/compliance.

## 26. Reconciliation sau khi rollback

Sau khi dịch vụ phục hồi, cần kiểm tra rằng kết quả nghiệp vụ vẫn đúng; chỉ một dashboard HTTP 200 chưa đủ.

Một reconciliation report có thể gồm:

| Invariant | Kiểm chứng |
|---|---|
| Không mất giao dịch đã xác nhận | So sánh business ledger, external provider receipts và database rows. |
| Không nhân đôi payment/message | Đối chiếu idempotency key và transaction IDs. |
| Balance/tồn kho nhất quán | Kiểm tra tổng và reconciliation rules theo nghiệp vụ. |
| Số record chuyển đổi | So count, checksums hoặc sample validation phù hợp. |
| Session/cache không lỗi | Monitor deserialization failures và auth metrics. |
| Event processing tiến triển | Consumer lag, DLQ, retry failures và ordering. |
| Database constraints | Kiểm tra violations và dữ liệu chưa backfill. |
| Không còn writes theo schema mới sai | Audit theo writer version/feature flag. |

### 26.1. Reconciliation không phải chỉ so COUNT(*)

Hai bảng có cùng row count vẫn có thể khác giá trị tiền, state, foreign key hoặc timestamp. Với dữ liệu quan trọng, cần invariants, row-level checksums, IDs/versions hoặc business ledger comparison tùy domain.

Nếu có sai lệch, phải phân loại:

- Dữ liệu mất.
- Dữ liệu trùng.
- Dữ liệu không chuyển đổi đầy đủ.
- Dữ liệu tương thích cú pháp nhưng sai nghiệp vụ.
- Event đã xử lý ngoài DB nhưng không có bản ghi trong DB.

Hành động sửa phải có audit trail và idempotency để không làm vấn đề tệ hơn.

## 27. Quan sát và chỉ số khi rollout/rollback

Các signals thường hữu ích:

- Error rate theo endpoint, HTTP/gRPC status và exception classes.
- p95/p99 latency theo request type, throughput và queue depth.
- JVM crashes, OutOfMemoryError, OOMKilled, GC và native memory.
- DB connection pool, deadlocks, constraint violations, slow queries.
- Schema migration/backfill progress, replication lag.
- Cache misses, session invalidation, deserialization errors.
- Message lag, DLQ, retries và duplicate rates.
- Payment/email/webhook side-effect reconciliation.
- Readiness, liveness, restart loops và canary health.

### 27.1. Thresholds cần gắn với rollback decision

Ví dụ policy minh họa:

~~~text
Canary 5% traffic for a defined observation window
Abort if:
  critical data invariant violation > 0
  unauthorized access violation > 0
  OOMKilled/unexpected crash in canary
  p99 latency exceeds approved regression budget
  event deserialization failure appears

Before rollback:
  verify A can read B-generated data
  verify schema rollback boundary not crossed
~~~

Con số 5% chỉ là ví dụ; observation window và traffic volume phải đủ để phát hiện lỗi. Không tự rollback mù nếu boundary đã bị vượt: thay vào đó cần containment/forward fix/recovery.

### 27.2. Metrics mất cũng là sự cố

Nếu monitoring mất dữ liệu trong canary, không mặc định “không có lỗi” vì dashboard trắng. Một rollout gate có thể yêu cầu đủ samples, health telemetry và data-integrity checks trước khi tiếp tục.

## 28. Mẫu metadata release bundle

Một release record hữu ích:

~~~yaml
releaseId: "customer-service-2026-11-B"
application:
  artifactDigest: "sha256:example-placeholder"
  sourceRevision: "example-commit"
runtime:
  javaMajor: 21
  jvmVendor: "vendor-placeholder"
  imageDigest: "sha256:runtime-placeholder"
  jvmProfile: "jvm-21-profile-v2"
dependencies:
  lockRevision: "example-lock-revision"
database:
  expandedSchemaVersion: "S2"
  destructiveContractApplied: false
  backfillState: "complete"
dataContracts:
  reads: ["customer-v1", "customer-v2"]
  writes: ["customer-v1", "customer-v2"]
events:
  reads: ["order-event-v1", "order-event-v2"]
  writes: ["order-event-v1"]
rollback:
  targetRelease: "customer-service-A"
  targetRuntimeJava: 17
  allowedUntilContractPhase: true
  rehearsalEvidence: "staging-run-placeholder"
~~~

File là **schema minh họa**, không phải file hiện có hay một công cụ tự động có thể chạy. Trong hệ thống thật nên version/validate fields bằng một policy đã được đội sở hữu thống nhất.

Điều đáng lưu ý: một release record chứa cả **data compatibility** và **rollback window**, chứ không chỉ tên image.

## 29. Ma trận QA/CI cho khả năng rollback

CI/Pre-release có thể thiết kế các jobs:

| Job | Chạy gì? | Tiêu chí |
|---|---|---|
| Compile/runtime matrix | A/JDK cũ, B/JDK mới theo support contract. | Không có class-version, missing API/agent errors. |
| Expand migration | Chạy schema expand trên dữ liệu giống production. | App A vẫn đọc/ghi như trước. |
| New data fixture | B tạo row/event mới. | A đọc được hoặc có boundary rõ, không âm thầm sai. |
| Mixed-version write | A/B cùng cập nhật fixture. | Không mất dữ liệu/vi phạm invariant. |
| Persistence integration | ORM A/B với DB schema tương ứng. | Transaction, IDs, queries đúng. |
| Serialization | A deserialize format do B ghi. | Theo compatibility contract. |
| Cache/session | Trộn A/B hoặc chuyển traffic. | Không crash; auth/session policy đúng. |
| Backup/PITR rehearsal | Restore ở môi trường cô lập. | Đạt RTO/RPO đã duyệt, integrity PASS. |
| Rollback smoke | Deploy lại A trên state do B tạo. | Functional + operational tests PASS. |
| Security regression | TLS, authorization, critical audit. | Không regression blocker. |

### 29.1. Không yêu cầu tất cả jobs chạy mọi pull request

Một số test có thể tốn thời gian, nhất là restore/PITR hoặc long-running backfill. Phân tầng:

- PR: unit, contract, schema compatibility, simulated mixed-version.
- Pre-release: full database integration và runtime/JDK matrix.
- Release candidate: restore rehearsal, rollback drill và operational gates.
- Staging/canary: kiểm tra với hạ tầng và traffic gần thực tế.

Những jobs bắt buộc cho quyết định phát hành phải được định nghĩa trước; không được bỏ vì chúng chạy lâu sau khi các jobs nhẹ đã xanh.

### 29.2. “Test cũ có PASS” là chưa đủ

Một ứng dụng A khởi động trên S1 không chứng minh A hoạt động trên S2. Test rollback phải **lấy trạng thái sau khi B chạy**, không chỉ chạy smoke test của A trên fixtures đã cũ.

## 30. RPO, RTO và lựa chọn chiến lược

| Tình huống | Phương án thường cân nhắc | Điều kiện quyết định |
|---|---|---|
| Config/JVM flag gây lỗi, dữ liệu không đổi | Rollback config, restart/rollout có kiểm soát. | JDK và app còn an toàn, flag cũ hỗ trợ. |
| B code lỗi, schema vẫn backward compatible | Rollback app/runtime bundle A. | A đọc/ghi B-created data và events. |
| B đã ghi format mới A không hiểu | Forward fix/compatibility patch hoặc writer containment. | Không có data loss và có cách đọc state mới. |
| Schema đã drop cột A cần | Forward fix hoặc recovery có kế hoạch. | Rollback A bị block nếu thiếu data/schema. |
| Có data corruption giới hạn phạm vi | Targeted repair/reconciliation từ audit/backup. | Có xác định affected records và invariants. |
| Data corruption rộng, không thể sửa chọn lọc | PITR/restore và replay/bù trừ. | RPO/RTO, side effects, phê duyệt business/data. |
| DB engine đã nâng không hỗ trợ downgrade | Giữ DB server mới, app/driver tương thích hoặc restore. | Engine support matrix/backup evidence. |
| JDK cũ thiếu bản vá bảo mật bắt buộc | Forward fix hoặc hotfix nhánh an toàn. | Security policy không cho downgrade. |

Đây không phải bảng tự động chọn lệnh; mọi phương án phải dựa vào mức thiệt hại nghiệp vụ, security, dữ liệu và khả năng thực thi.

### 30.1. Khi rollback JDK có thể bị cấm vì bảo mật

Một JDK version cũ có thể không còn được vá hoặc đã bị loại khỏi policy hạ tầng. Dù chạy được App A, đưa JVM cũ trở lại production có thể tạo rủi ro security/compliance không chấp nhận được.

Một hướng thay thế là hotfix trên JDK mục tiêu hoặc rebuild một nhánh cũ bằng runtime đã được vá/tương thích, nếu sản phẩm và dependency cho phép.

Quyết định phải được đưa vào risk acceptance có người phê duyệt; không coi “runtime này từng chạy ổn” là đủ.

## 31. Những sai lầm phổ biến

| Sai lầm | Rủi ro | Nguyên tắc khắc phục |
|---|---|---|
| Rollback image nghĩa là rollback hệ thống. | DB, events và external effects vẫn mới. | Xác minh toàn bộ state. |
| Có DOWN migration thì dữ liệu sẽ phục hồi. | Biến đổi có thể mất thông tin. | Expand-contract, backup và reconciliation. |
| Chạy DROP column cùng release B. | Khóa ngay đường rollback A. | Contract sau rollback window. |
| A đọc được S2 nghĩa là A ghi an toàn. | A có thể overwrite dữ liệu mới. | Kiểm thử read **và write**. |
| Dual-write tự đảm bảo đồng bộ. | Race, retry, transaction split, divergence. | Rõ source of truth và reconciliation. |
| Thử rollback trên DB trống. | Không bắt được format do B ghi. | B-created data fixtures. |
| JDK 21 → 17 chỉ đổi JAVA_HOME. | Bytecode/dependency mới có thể không chạy. | Runtime/bytecode/API matrix. |
| Dùng lại JVM flags của JDK mới. | Startup lỗi hoặc semantics khác. | Versioned runtime profiles. |
| Trộn javax/jakarta providers. | Binary API/classloading mismatch. | Rollback nguyên stack tương thích. |
| Downgrade database server dễ như app. | Storage/catalog format có thể không hỗ trợ. | Theo engine docs và restore rehearsal. |
| Reset Kafka offsets để “undo”. | Replay/duplicate side effects. | Idempotency và event recovery plan. |
| Xóa cache/session không tính hậu quả. | Tải DB tăng hoặc user bị logout. | Cache namespace và rollout policy. |
| Restore DB không xem side effects. | Payment/email/API vẫn đã xảy ra. | Ledger reconciliation/compensation. |
| Có backup là đạt RTO/RPO. | Backup có thể restore quá chậm hoặc không hợp lệ. | Diễn tập restore. |
| Canary 5% thì rollback luôn an toàn. | Canary vẫn ghi vào DB chung. | Data compatibility gates. |
| Rollout undo tự xử lý GitOps/ConfigMap. | Desired state và secrets vẫn mới. | Bundle/manifest coordination. |
| Thấy service Running là rollback thành công. | Có thể sai business data hoặc messages. | End-to-end invariants và monitoring. |
| Forward fix bị coi là thất bại. | Có thể rollback sai và phá dữ liệu. | Chọn phương án giảm rủi ro tốt nhất. |
| Dùng lại JDK hết hỗ trợ để chữa cháy. | Security/compliance regression. | Security approval hoặc hotfix an toàn. |

## 32. Quy trình đầy đủ trước một Java migration rủi ro cao

**Bước 1 — Kiểm kê release hiện tại.** Ghi source, JDK/vendor/update, JVM flags, framework, ORM, JDBC driver, agents, OS/container, database schema, event formats, cache/session và external integrations.

**Bước 2 — Xác định thay đổi dữ liệu.** Phân loại additive, compatible, destructive, lossy, format change và external side effect. Đánh dấu những thay đổi tạo rollback boundary.

**Bước 3 — Thiết kế compatibility matrix.** Xác nhận A/S1, A/S2, B/S1, B/S2 cùng các phiên bản data/event cần thiết. Thử đọc **và ghi**.

**Bước 4 — Tách expand-contract.** Áp migration additive trước, giữ cột/format cũ trong compatibility window, triển khai B và backfill, chỉ contract sau khi điều kiện thoát được đáp ứng.

**Bước 5 — Khóa artifact/runtime bundles.** Lưu image digests, JDK cũ/mới, dependency locks, agents và deployment config; đảm bảo artifacts có thể triển khai lại.

**Bước 6 — Định nghĩa feature flags.** Tách rollout code và writer mới, hỗ trợ kill switch, xác định flag propagation và rollback implications.

**Bước 7 — Chuẩn bị backup/PITR và RTO/RPO.** Kiểm tra restore credentials, encryption keys, transaction logs và khả năng reconciliation.

**Bước 8 — Diễn tập rollback có B-generated state.** Trên staging, cho B ghi dữ liệu thật kiểu mới, quay về A và chạy contract tests, event/session tests cùng data integrity checks.

**Bước 9 — Thiết lập gates/canary.** Chọn thresholds cho data integrity, errors, latency, OOM, message processing và rollback boundary.

**Bước 10 — Rollout từng giai đoạn.** Theo dõi mixed-version window, backfill progress, old consumer count và các side effects.

**Bước 11 — Khi có sự cố, containment trước.** Dừng write path nguy hiểm, giữ bằng chứng, xác định có thể rollback config, app/JDK, hay cần forward fix/recovery.

**Bước 12 — Kiểm chứng sau rollback.** Đo business invariants, reconcile DB/events/external effects, xác minh security và operational SLOs.

**Bước 13 — Đóng rollback window có chủ đích.** Chỉ chạy destructive contract migrations khi không còn old writers/readers, không còn rollback target phụ thuộc schema cũ và đã có phê duyệt.

**Bước 14 — Postmortem.** Ghi root cause, dữ liệu bị ảnh hưởng, hiệu quả runbook, thời gian RTO/RPO thật và cải tiến CI/rollback tests.

## 33. Checklist trước khi phê duyệt phát hành

- [ ] Có danh sách thay đổi JDK, app, dependencies, schema và data formats.
- [ ] Có immutable artifact/runtime bundle A và B, đủ để deploy lại.
- [ ] Xác định Java bytecode target và runtime dependencies của A/B.
- [ ] Kiểm tra minimum Java, native agents, JPA/Servlet stack và startup flags.
- [ ] Có compatibility matrix old/new app với old/new schema/data/events.
- [ ] A có thể đọc và **ghi** dữ liệu do B tạo theo contract.
- [ ] Đã đánh dấu rõ destructive/lossy migrations và rollback boundaries.
- [ ] Backfill có batches, idempotency, progress metrics và resume plan.
- [ ] Dual-read/dual-write có source-of-truth/conflict resolution rõ.
- [ ] Event consumers/offsets, cache/session và external side effects đã được xem xét.
- [ ] Database backup/PITR đã được kiểm chứng bằng restore drill.
- [ ] RTO/RPO có giá trị, owner và bằng chứng khả thi.
- [ ] Có feature kill switch/containment để dừng writes nguy hiểm.
- [ ] Canary/rolling/blue-green strategy không giả định DB rollback tự động.
- [ ] Runbook chỉ rõ rollback, forward fix và recovery decision branches.
- [ ] Có escalation, approvals và communication plan.
- [ ] Có functional, data-integrity và operational gates sau rollback.
- [ ] Không downgrade về một JDK/dependency vi phạm security policy.
- [ ] Contract cleanup chỉ diễn ra sau khi rollback window được đóng.

Checklist là hướng dẫn lập kế hoạch; mỗi mục được đánh dấu hoàn thành cần có bằng chứng thực tế từ test, release policy hoặc diễn tập.

## 34. Kết luận

**Quay lui JDK hoặc ứng dụng khi dữ liệu và dependency đã thay đổi là bài toán tương thích của toàn bộ hệ thống, không chỉ của Java executable hay container image.** JVM cũ có thể không chạy bytecode/dependency mới; application cũ có thể không đọc schema/event/session mới; còn database restore có thể làm mất những giao dịch hợp lệ đã xảy ra sau mốc phục hồi và không đảo được side effects bên ngoài.

Chiến lược an toàn là thiết kế rollback ngay từ đầu: giữ release bundles có thể triển khai lại, dùng **expand → migrate → contract**, xác định rõ **rollback boundary**, kiểm tra cả old-reader lẫn old-writer với dữ liệu do bản mới tạo và duy trì event/cache/session compatibility trong cửa sổ hỗ trợ. Song song, cần backup/PITR có diễn tập, RTO/RPO rõ ràng, business reconciliation, kill switches và decision tree phân biệt rollback với forward fix hoặc recovery.

Trong **Java Advance Compatibility Migration**, thành công của rollback không được đo bằng việc lệnh deploy trước đó chạy xong hay Pod trở lại màu xanh. Nó được chứng minh khi **ứng dụng tiếp tục phục vụ đúng, dữ liệu và giao dịch vẫn nhất quán, external side effects được xử lý và hệ thống đáp ứng tiêu chí vận hành/bảo mật đã cam kết**.
