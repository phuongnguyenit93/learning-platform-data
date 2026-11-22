# Ràng buộc UNIQUE hoặc CHECK để bảo vệ bất biến

## 1. Vấn đề: kiểm tra bằng Java không đủ khi nhiều transaction chạy đồng thời

Trong một ứng dụng Spring, bạn có thể viết:

```java
if (!bookingRepository.existsByEventCodeAndSeatCode(event, seat)) {
    bookingRepository.save(new Booking(event, seat, customer));
}
```

Đây là **đoạn minh họa**, chưa phải class biên dịch độc lập. Nó có vẻ bảo vệ quy tắc “mỗi ghế trong một sự kiện chỉ được bán một lần”. Nhưng khi hai request chạy đồng thời, cả hai có thể thấy ghế còn trống trước khi một request kịp ghi:

```text
Thời điểm    Transaction T1                    Transaction T2
-----------------------------------------------------------------
t1           SELECT ... -> chưa có booking
t2                                             SELECT ... -> chưa có booking
t3           INSERT(event=E, seat=A1)
t4                                             INSERT(event=E, seat=A1)
t5           COMMIT                            COMMIT (nếu DB không có UNIQUE)

Kết quả sai: hai bản ghi cho cùng một ghế.
```

`@Transactional` không tự làm cặp thao tác **SELECT → INSERT** trở thành một kiểm tra độc quyền. Ở isolation `READ_COMMITTED` thông thường, cả hai transaction có thể đọc cùng trạng thái “chưa tồn tại”. Ngay cả việc kiểm tra hai lần ở ứng dụng cũng không giải quyết được cuộc đua thời gian nếu không có cơ chế đồng bộ chính xác.

**Bảo vệ tại database:**

```sql
CONSTRAINT uq_event_seat UNIQUE (event_code, seat_code)
```

Khi đó DB chịu trách nhiệm không cho phép hai row **đã commit** cùng vi phạm khóa duy nhất ấy. Một transaction có thể phải chờ transaction kia; cuối cùng chỉ một kết quả hợp lệ được commit, transaction còn lại nhận lỗi uniqueness hoặc không thể hoàn tất theo cơ chế DB. **Không dựa vào thứ tự thắng/thua của thread.**

Một bất biến khác: “số lượng còn lại không âm và không vượt tổng số lượng” cần:

```sql
CONSTRAINT ck_stock_bounds
CHECK (total_units >= 0
   AND available_units >= 0
   AND available_units <= total_units)
```

`CHECK` ngăn một row chuyển sang trạng thái không hợp lệ **khi DB kiểm tra constraint**. Đối với nhiều transaction cùng trừ tồn kho, nên bổ sung **UPDATE có điều kiện nguyên tử**, không chỉ check bằng Java:

```sql
UPDATE inventory
SET available_units = available_units - :amount
WHERE sku = :sku
  AND available_units >= :amount;
```

Đây là SQL khái niệm dùng named parameters; ví dụ JDBC thực thi đầy đủ sẽ dùng placeholder `?`. Kiểm tra số row được cập nhật: `1` nghĩa là thao tác đã ghi vào transaction, `0` nghĩa là không thỏa điều kiện/không tìm thấy row. Cuối cùng transaction phải commit thành công thì kết quả mới bền vững.

### Kết luận cốt lõi

- **`UNIQUE`:** bảo vệ **tính duy nhất** của khóa nghiệp vụ ở database, kể cả khi hai request tranh chấp.
- **`CHECK`:** bảo vệ **miền giá trị/trạng thái của một row** theo điều kiện có thể biểu diễn ở DB.
- **Guarded/conditional `UPDATE`:** bảo vệ phép cập nhật phụ thuộc vào giá trị hiện tại một cách nguyên tử, ví dụ không bán quá tồn.
- **`@Transactional`:** xác lập boundary commit/rollback, không thay thế constraint hoặc thuật toán cập nhật đúng.
- **Validation ở Java:** vẫn hữu ích để trả thông báo thân thiện và tránh round-trip thừa, nhưng **không phải lớp bảo vệ cuối cùng** của bất biến khi concurrency xuất hiện.

Bài này thuộc **Khóa và đồng thời → Ràng buộc unique hoặc check để bảo vệ bất biến**, tập trung vào giao điểm của database integrity constraints, transaction isolation, Spring JDBC/JPA và race conditions.

## 2. “Bất biến” là gì và đặt ở lớp nào?

**Bất biến (invariant)** là điều kiện phải luôn đúng đối với trạng thái dữ liệu được chấp nhận. Ví dụ:

| Bất biến nghiệp vụ | Đặc điểm | Cơ chế database phù hợp |
| --- | --- | --- |
| Mỗi `(event_code, seat_code)` có tối đa một booking | Cross-row uniqueness | `UNIQUE(event_code, seat_code)` |
| Mỗi request ID trong một tenant chỉ được tạo một lệnh | Cross-row uniqueness | `UNIQUE(tenant_id, request_id)` |
| `available_units >= 0` | Một row | `CHECK` + guarded `UPDATE` khi trừ tồn |
| `available_units <= total_units` | Quan hệ các cột cùng row | `CHECK` |
| `price >= 0` và không NULL | Một row | `NOT NULL` + `CHECK` |
| Đơn hàng phải tham chiếu customer có tồn tại | Tham chiếu khác bảng | `FOREIGN KEY` |
| Tổng số booking ở nhiều row không vượt sức chứa | Aggregate/cross-row | Counter row được cập nhật nguyên tử, locking hoặc isolation phù hợp |
| Không có hai khoảng thời gian booking chồng nhau | Cross-row interval overlap | Exclusion constraint (nếu DB hỗ trợ), locking hoặc thiết kế riêng |

Không mọi invariant đều viết được bằng `UNIQUE`/`CHECK`. Nếu điều kiện phụ thuộc tổng hợp từ nhiều row khác, một `CHECK` đơn giản thường **không** là công cụ đúng. Database như PostgreSQL không hỗ trợ `CHECK` tham chiếu trực tiếp dữ liệu của các row khác để đảm bảo invariant nhất quán; hãy dùng công cụ dành cho cross-row constraints hoặc một transaction protocol tương ứng.

### 2.1. Quy tắc ở application và database bổ trợ nhau

Trong Spring service, validation có thể từ chối ngay `amount <= 0`, trả lỗi HTTP rõ ràng hoặc gợi ý seat đang được giữ. Nhưng sau validation, **database constraint vẫn phải là trọng tài cuối**.

```text
HTTP / message input
  -> validation: cú pháp, giá trị đầu vào, phản hồi thân thiện
  -> Spring transactional service: phối hợp các bước nghiệp vụ
  -> guarded SQL / locking: cập nhật nguyên tử khi cần
  -> UNIQUE / CHECK / FK: bác bỏ state không hợp lệ
  -> COMMIT: DB quyết định kết quả bền vững
  -> response/event: phản ánh kết quả đã thực sự hoàn tất
```

Tránh coi validation ngoài transaction hoặc một `existsBy...` là “đã khóa” dữ liệu.

## 3. UNIQUE: đúng khóa nghiệp vụ và đúng phạm vi

### 3.1. Single-column, composite unique và primary key

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    CONSTRAINT uq_customer_email UNIQUE (email)
);

CREATE TABLE bookings (
    booking_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_code VARCHAR(40) NOT NULL,
    seat_code VARCHAR(20) NOT NULL,
    customer_code VARCHAR(80) NOT NULL,
    CONSTRAINT uq_event_seat UNIQUE (event_code, seat_code)
);
```

`PRIMARY KEY` định danh row và yêu cầu unique + not null. `UNIQUE` có thể áp dụng cho một hoặc nhiều cột khác. Với `uq_event_seat`, hai sự kiện khác nhau có thể cùng dùng seat code `A1`; chỉ cặp `(event_code, seat_code)` phải duy nhất.

**Sai phạm vi:**

```sql
UNIQUE (seat_code)
```

Nếu nhiều sự kiện cùng có ghế `A1`, constraint trên sẽ ngăn quá mức.

**Phạm vi đúng:**

```sql
UNIQUE (event_code, seat_code)
```

Nếu ứng dụng đa tenant, đôi khi phải thêm `tenant_id` vào khóa, nhưng chỉ khi business invariant thực sự được phân vùng theo tenant. Đừng mù quáng thêm tenant vào constraint nếu đó là một khóa toàn hệ thống.

### 3.2. UNIQUE hoạt động khi hai INSERT đồng thời ra sao?

Một database giao dịch với uniqueness enforcement hợp lệ không được cho hai transaction **cùng commit hai row** vi phạm một unique key. Khi collision, chi tiết tùy engine và isolation:

1. Transaction thứ nhất có thể insert key.
2. Transaction thứ hai cố insert cùng key.
3. DB có thể block transaction hai chờ kết quả commit/rollback của transaction một.
4. Nếu transaction một commit, insert thứ hai sẽ bị từ chối do uniqueness; nếu transaction một rollback, transaction hai có thể tiếp tục.
5. Ở ứng dụng Spring, một lỗi SQL được dịch thành `DataIntegrityViolationException`/`DuplicateKeyException` hoặc một lỗi tương ứng tùy driver/translator, và transaction hiện tại cần được hoàn tất thích hợp.

Không khẳng định lỗi luôn xuất hiện ngay ở `repository.save(...)`, vì với JPA/Hibernate, SQL INSERT có thể bị trì hoãn tới `flush`/commit. Với Spring JDBC, `JdbcTemplate.update(...)` thực thi statement ngay và thường thấy lỗi ở dòng gọi update.

### 3.3. UNIQUE và NULL là bẫy phổ biến

Ở nhiều database, hai row có giá trị `NULL` trong một cột unique **không bị coi là duplicate** theo semantics mặc định. PostgreSQL cho phép tùy chọn `NULLS NOT DISTINCT` với những version có hỗ trợ; H2 mặc định `NULLS DISTINCT` trong chế độ bình thường.

Vì vậy, nếu business key **bắt buộc có giá trị**, đặt `NOT NULL` **cùng với** `UNIQUE`. Không viết:

```sql
email VARCHAR(255),
UNIQUE (email)
```

rồi suy ra “không thể có nhiều customer không có email” trên mọi DB. Nếu email được phép NULL, business requirement phải nêu rõ sự khác biệt giữa “chưa biết email” và “một email duy nhất”.

### 3.4. Chuẩn hóa khóa: case, Unicode, khoảng trắng

`UNIQUE(email)` không có nghĩa DB sẽ coi `"A@EXAMPLE.COM"` và `"a@example.com"` giống nhau ở mọi collation. Tương tự, `"alice"` và `" alice "`, các dạng Unicode canonical khác nhau, hoặc chuỗi dùng normalization khác nhau có thể hành xử khác.

Cần xác định **quy tắc chuẩn hóa** business key trước khi lưu:

- Chuẩn hóa email/user ID theo contract (cẩn thận không phá semantics của domain).
- Dùng generated/normalized key column hoặc functional index được DB hỗ trợ nếu phù hợp.
- Thử thực tế collation, case-sensitivity, Unicode/diacritics.
- Không dùng `toLowerCase()` ở Java làm “unique constraint” thay thế: hai request vẫn có thể race.

### 3.5. Soft delete và unique “chỉ trên row active”

Nếu business muốn nhiều lịch sử nhưng chỉ một phiên bản active, `UNIQUE(customer_id)` có thể quá mạnh. Một DB có hỗ trợ **partial unique index** như PostgreSQL có thể dùng:

```sql
-- PostgreSQL-specific, KHÔNG phải cú pháp H2 chung.
CREATE UNIQUE INDEX uq_active_customer
ON subscriptions (customer_id)
WHERE deleted_at IS NULL;
```

Index này giới hạn uniqueness tới các row thỏa predicate. Cần xem ngữ nghĩa soft delete, cách cập nhật `deleted_at` trong transaction, và việc nhiều transaction đồng thời active/restore cùng một logical key. Không dựa vào application-side `WHERE deleted_at IS NULL` check đơn lẻ.

## 4. CHECK: ngăn một row rơi vào trạng thái sai

### 4.1. CHECK kiểm tra một biểu thức Boolean trên row

```sql
CREATE TABLE inventory (
    sku VARCHAR(40) PRIMARY KEY,
    total_units INT NOT NULL,
    available_units INT NOT NULL,
    CONSTRAINT ck_stock_bounds CHECK (
        total_units >= 0
        AND available_units >= 0
        AND available_units <= total_units
    )
);
```

Các state:

| `total_units` | `available_units` | Constraint |
| ---: | ---: | --- |
| 10 | 10 | Hợp lệ |
| 10 | 0 | Hợp lệ |
| 10 | 6 | Hợp lệ |
| 10 | -1 | Bị từ chối |
| 10 | 11 | Bị từ chối |
| -5 | 0 | Bị từ chối |
| 0 | 0 | Hợp lệ |

SQL `CHECK` được đánh giá ở database khi insert/update theo quy định của engine/constraint. Nó ngăn dữ liệu sai dù source là một API Spring, batch job, migration script, admin SQL, consumer khác hay code của ngôn ngữ khác.

### 4.2. CHECK không mặc nhiên cấm NULL

SQL dùng ba giá trị logic `TRUE`, `FALSE`, `UNKNOWN`. Khi một toán hạng là `NULL`, nhiều điều kiện cho kết quả `UNKNOWN`; `CHECK` nói chung chỉ từ chối khi kết quả **`FALSE`**, không phải `UNKNOWN`.

Ví dụ:

```sql
-- Sai nếu business yêu cầu price luôn tồn tại:
price DECIMAL(12, 2) CHECK (price >= 0)

-- Rõ ràng hơn:
price DECIMAL(12, 2) NOT NULL
    CHECK (price >= 0)
```

H2 documentation ghi CHECK chấp nhận `TRUE` hoặc `UNKNOWN`. PostgreSQL cũng áp dụng quy tắc tương tự. Vì thế ở schema chạy thử, `total_units` và `available_units` đều có `NOT NULL`.

### 4.3. CHECK thường phù hợp cho invariant nội tại của một row

`CHECK (available_units <= total_units)` biểu diễn được vì cả hai cột thuộc một row. Nhưng các yêu cầu sau không thể giải quyết bằng một row-level CHECK đơn giản:

- Tổng số chỗ đặt của **nhiều row** không vượt capacity.
- Mỗi customer chỉ có tối đa ba đơn đang xử lý trên nhiều row.
- Tổng ledger debits phải bằng tổng credits của nhiều transaction.
- Hai khoảng thời gian đặt phòng ở các row không chồng nhau.

Với những điều kiện này, cần schema khác (ví dụ counter row được cập nhật atomically), `UNIQUE`/`FOREIGN KEY`/exclusion, locking, serializable isolation có retry hoặc quy trình nghiệp vụ phù hợp. Một trigger cũng phải được thiết kế cẩn thận cho concurrency; trigger đơn thuần SELECT rồi insert vẫn có thể race nếu không có locking/isolation đúng.

### 4.4. CHECK không sửa được “lost update”

Hai transaction có thể đọc `available_units = 5`, rồi mỗi bên ghi `available_units = 4`. Row vẫn thỏa CHECK, nhưng DB đã ghi nhận **một lần giảm** thay vì hai lần. Đây là **lost update**, không phải trực tiếp một CHECK violation.

```text
T1 đọc 5  ─── tính 4 ─── UPDATE available=4
T2 đọc 5  ─── tính 4 ─── UPDATE available=4
Kết quả có thể vẫn 4 dù hai lượt giữ hàng đã xảy ra.
```

Sửa bằng atomic arithmetic update hoặc cơ chế locking/optimistic versioning đúng:

```sql
UPDATE inventory
SET available_units = available_units - 1
WHERE sku = 'SKU-1'
  AND available_units >= 1;
```

DB xử lý statement trên row tương ứng với transaction/locking của nó. Khi hai request tranh đơn vị cuối, chỉ một UPDATE có thể thành công; transaction còn lại nhận affected row count `0` hoặc gặp lỗi retryable tùy engine/isolation, chứ không tự ghi -1.

`CHECK` vẫn là tuyến phòng thủ bổ sung nếu có code khác cố ghi `-1` trực tiếp. **Mô hình đúng là combine guarded statement + constraint + transaction boundary**, không chọn một trong ba.

## 5. Spring transaction xử lý constraint violation thế nào?

### 5.1. Spring JDBC và `DataIntegrityViolationException`

Với `JdbcTemplate`, Spring chuyển dịch các JDBC `SQLException` thành hierarchy `DataAccessException`. `DataIntegrityViolationException` là nhóm lỗi vi phạm toàn vẹn dữ liệu; `DuplicateKeyException` là một subclass cụ thể của nó.

```java
@Transactional
public void book(String event, String seat, String customer) {
    jdbc.update(
        "INSERT INTO bookings(event_code, seat_code, customer_code) " +
        "VALUES (?, ?, ?)",
        event, seat, customer);
}
```

Đây là snippet cần field `JdbcTemplate jdbc` và Spring-managed bean. Nếu uniqueness bị vi phạm trong JDBC update, Spring thường ném `DataIntegrityViolationException` hoặc subclass; vì đây là **runtime exception**, rollback rule mặc định của `@Transactional` sẽ yêu cầu rollback.

**Không suy ra mọi lỗi thuộc `DataIntegrityViolationException` đều là duplicate**. Đó có thể là CHECK, NOT NULL, FOREIGN KEY hoặc constraint khác. Ở application boundary, cần phân biệt bằng constraint name/vendor code/SQLState đáng tin và theo chuẩn adapter của dự án, tránh biến lỗi integrity không ngờ thành “ghế đã bán”.

### 5.2. Vị trí đặt `catch` rất quan trọng

Đừng viết:

```java
@Transactional
public void unsafeFlow() {
    try {
        jdbc.update("INSERT INTO bookings (...) VALUES (...)");
    } catch (DataIntegrityViolationException ignored) {
        // Sai nếu coi đây là cách phục hồi transaction sau SQL error.
    }
    // tiếp tục SQL và hi vọng commit ...
}
```

Đây là **pseudo-code**, câu SQL có dấu `...` không hợp lệ. Trên một số DB (ví dụ PostgreSQL), một SQL error có thể làm transaction hiện tại ở trạng thái aborted cho tới khi rollback; trong một số stack ORM, persistence context cũng không còn đáng tin để tiếp tục. Catch ngay trong transaction có thể làm interceptor nhìn thấy return bình thường, rồi commit thất bại/rollback-only xuất hiện muộn.

Nếu mục tiêu là trả kết quả “seat đã có người đặt”, thường để transactional method ném lỗi, để transaction manager hoàn tất rollback, rồi **bắt và ánh xạ exception ở bên ngoài transaction boundary** (controller/facade không còn nằm trong cùng transaction), hoặc dùng database-specific upsert semantics đúng.

```text
Controller / command adapter
   |
   +-- try bookingService.book(...)  // proxy boundary
           -> JDBC INSERT
           -> DB UNIQUE rejects
           -> Spring translates exception
           -> interceptor rolls back
   |
   +-- catch DataIntegrityViolationException
           -> classify known uq_event_seat
           -> return 409 Conflict / domain result
```

Với transaction đã tồn tại bao quanh controller/facade, “bên ngoài service method” chưa chắc là bên ngoài **physical transaction**. Cần tìm transaction owner cuối và không tiếp tục ghi trong transaction đã lỗi.

### 5.3. JPA có thể ném muộn ở flush/commit

Trong Spring Data JPA, gọi `repository.save(...)` không nhất thiết phát SQL ngay. Hibernate có thể chỉ INSERT/UPDATE ở `flush` hoặc commit. Do đó:

- `save()` return không bảo đảm uniqueness đã được DB xác nhận.
- `saveAndFlush()`/`entityManager.flush()` đẩy SQL sớm hơn, giúp phát hiện một số lỗi trước khi method return, nhưng **không phải commit** và không giải quyết hết mọi lỗi ở commit.
- Một DB hỗ trợ deferred constraints có thể kiểm tra ở commit dù đã flush.
- Các exception có thể được chuyển thành `DataIntegrityViolationException` khi qua Spring persistence exception translation, nhưng không nên hứa chính xác một subclass ở mọi provider/version.
- Sau một Hibernate/JPA persistence failure, không giả định `EntityManager` còn an toàn để dùng tiếp trong cùng transaction.

Bài thực hành dùng **Spring JDBC** để thời điểm statement và lỗi dễ quan sát; phần nguyên lý uniqueness/check áp dụng ở DB bất kể truy cập qua JDBC hay JPA.

### 5.4. Một SQL statement thành công chưa phải commit

`JdbcTemplate.update` trả affected rows trong transaction; application còn cần hoàn tất `@Transactional`. Nếu commit gặp deadlock, timeout, kết nối lỗi, hoặc một trạng thái rollback-only từ nơi khác, caller có thể không nhận kết quả thành công. Với thao tác có side effect quan trọng, hãy dùng business key/idempotency và đối soát trước khi retry.

### 5.5. Constraint name, SQLState và tính portable

Ví dụ với H2:

- Unique violation thường mang error code/SQLState `23505`.
- CHECK violation dùng error code `23513` trong H2.
- NOT NULL violation là `23502`.

Những giá trị này **không phải chuẩn cố định cho mọi database**; ví dụ PostgreSQL CHECK violation dùng SQLSTATE `23514`. Khi cần mapping domain lỗi, cô lập việc đọc `SQLException`/constraint name trong persistence adapter, log an toàn và có integration test cho engine production. Đừng hardcode SQLState của H2 rồi đem dùng nguyên vẹn trên PostgreSQL/MySQL/Oracle.

## 6. Dự án chạy được: UNIQUE, CHECK, race test và atomic UPDATE

Ta tạo project Spring Boot dùng một H2 datasource thật với transaction manager JDBC. Các integration test chứng minh:

1. UNIQUE trên cặp `(event_code, seat_code)`, không phải trên `seat_code` toàn hệ thống.
2. Duplicate booking bị DB từ chối, kể cả khi hai transaction đều precheck thấy ghế trống.
3. CHECK ngăn hàng tồn âm/vượt tổng số lượng; NOT NULL cấm state NULL.
4. Constraint failure trong transaction rollback cả statement hợp lệ đã chạy trước nó.
5. Guarded UPDATE không bán quá số hàng còn trong cùng hoặc nhiều transaction.
6. Kết quả kiểm chứng bằng SQL **sau khi service proxy hoàn tất**, không chỉ bằng exception hoặc log.

### 6.1. Cấu trúc project và môi trường

```text
db-invariants/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/invariants/
    │   │   ├── InvariantsApplication.java
    │   │   ├── BookingService.java
    │   │   └── InventoryService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/invariants/
        └── DatabaseInvariantIntegrationTest.java
```

Sử dụng **Java 17+**, Gradle tương thích và Spring Boot 3.3.5 với Spring JDBC + H2 + JUnit 5. Nếu dùng Spring Initializr, có thể tạo Gradle Wrapper cùng dự án; nếu tạo thủ công, cần Gradle phù hợp để chạy hoặc sinh wrapper. Mã Spring không biên dịch được bằng `javac` trần nếu chưa có classpath dependency.

`settings.gradle`:

```groovy
rootProject.name = 'db-invariants'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot dependency management quản lý version Spring/JUnit/H2 tương thích với Boot version trong ví dụ. Cần đảm bảo Gradle/JDK đáp ứng yêu cầu của plugin.

### 6.2. DataSource và schema

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:invariants;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=10000
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.sql.init.mode=always
```

`LOCK_TIMEOUT=10000` là setting của H2 phục vụ concurrency test, không phải cấu hình isolation portable. Pool size 5 đủ cho hai transaction đồng thời trong fixture. Không dùng H2 result để bảo đảm behavior locking/timing của PostgreSQL hoặc MySQL mà không thử lại.

`src/main/resources/schema.sql`:

```sql
CREATE TABLE bookings (
    booking_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_code VARCHAR(40) NOT NULL,
    seat_code VARCHAR(20) NOT NULL,
    customer_code VARCHAR(80) NOT NULL,
    CONSTRAINT uq_event_seat UNIQUE (event_code, seat_code)
);

CREATE TABLE inventory (
    sku VARCHAR(40) PRIMARY KEY,
    total_units INT NOT NULL,
    available_units INT NOT NULL,
    CONSTRAINT ck_stock_bounds CHECK (
        total_units >= 0
        AND available_units >= 0
        AND available_units <= total_units
    )
);
```

Schema tạo **hai bất biến** có thể được enforced tại DB:

- `uq_event_seat`: không được có hai booking cùng event+seat.
- `ck_stock_bounds`: tổng số unit không âm, available trong khoảng từ 0 đến total (với NOT NULL trên các cột liên quan).

Đặt tên constraint giúp giải thích lỗi, migrate schema và ánh xạ domain error nhất quán hơn so với phụ thuộc một tên auto-generated.

### 6.3. Spring Boot application và transaction manager

`src/main/java/com/example/invariants/InvariantsApplication.java`:

```java
package com.example.invariants;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class InvariantsApplication {
    public static void main(String[] args) {
        SpringApplication.run(InvariantsApplication.class, args);
    }

    @Bean("transactionManager")
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Chỉ có **một** local JDBC transaction manager bean để mọi service dùng cùng datasource. `DataSourceTransactionManager` và `JdbcTemplate` phối hợp Spring transaction-bound JDBC connection. H2 database được khởi tạo qua `schema.sql` trước khi tests chạy.

### 6.4. BookingService: một method bình thường và một race precheck có chủ ý

`src/main/java/com/example/invariants/BookingService.java`:

```java
package com.example.invariants;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookingService {
    private final JdbcTemplate jdbc;

    public BookingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void book(String event, String seat, String customer) {
        jdbc.update(
            "INSERT INTO bookings(event_code, seat_code, customer_code) " +
            "VALUES (?, ?, ?)",
            event, seat, customer);
    }

    @Transactional
    public void bookAfterBothSawEmpty(
            String event,
            String seat,
            String customer,
            CountDownLatch ready,
            CountDownLatch release) {

        Integer existing = jdbc.queryForObject(
            "SELECT COUNT(*) FROM bookings " +
            "WHERE event_code = ? AND seat_code = ?",
            Integer.class, event, seat);

        if (existing == null || existing != 0) {
            throw new IllegalStateException(
                "Test precondition: seat already booked");
        }

        // Để thử race có chủ ý: mỗi transaction đã SELECT thấy trống
        // trước khi bất kỳ transaction nào được phép INSERT.
        ready.countDown();
        try {
            if (!release.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Barrier timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }

        jdbc.update(
            "INSERT INTO bookings(event_code, seat_code, customer_code) " +
            "VALUES (?, ?, ?)",
            event, seat, customer);
    }

    @Transactional
    public void bookThenBreakStockCheck() {
        jdbc.update(
            "INSERT INTO bookings(event_code, seat_code, customer_code) " +
            "VALUES (?, ?, ?)",
            "FAILED_TX", "Z9", "alice");

        jdbc.update(
            "UPDATE inventory SET available_units = -1 WHERE sku = ?",
            "SKU-1");
    }
}
```

`bookAfterBothSawEmpty` được thiết kế **cố ý sai nếu bỏ UNIQUE**: cả hai thread SELECT `COUNT=0`, rồi barrier mở cho cả hai INSERT cạnh tranh. Nó không phải flow nghiệp vụ nên đưa vào production; trong production, hãy attempt INSERT atomically rồi handle constraint violation.

`bookThenBreakStockCheck` cho thấy constraint failure phát sinh sau một INSERT hợp lệ **trong cùng transaction**, và vì runtime exception thoát qua transactional proxy, Spring rollback cả transaction. Trong demo H2, CHECK vi phạm ngay ở `JdbcTemplate.update`, không chờ commit.

### 6.5. InventoryService: guarded UPDATE cùng CHECK

`src/main/java/com/example/invariants/InventoryService.java`:

```java
package com.example.invariants;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final JdbcTemplate jdbc;

    public InventoryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean reserve(String sku, int units) {
        if (units <= 0) {
            throw new IllegalArgumentException("units must be positive");
        }

        int changed = jdbc.update(
            "UPDATE inventory " +
            "SET available_units = available_units - ? " +
            "WHERE sku = ? AND available_units >= ?",
            units, sku, units);

        // 1: update đã thực hiện trong transaction này.
        // 0: SKU không có hoặc available không đủ.
        // Caller nhận boolean sau khi transaction advice hoàn tất.
        return changed == 1;
    }
}
```

Vì `sku` là primary key, một UPDATE chỉ nhắm tới tối đa một row. `changed==1` không nên được diễn giải như “đã durable commit” khi code ở **trong** transactional method. Với lời gọi **bên ngoài qua proxy**, transaction advice sẽ thực hiện completion trước khi trả kết quả thành công cho caller. Nếu caller đã có một outer transaction `REQUIRED`, việc commit physical vẫn chờ outer transaction owner.

Điều kiện `available_units >= units` được đánh giá trong chính UPDATE. Transaction đồng thời cập nhật cùng row phải phối hợp khóa/visibility của engine, khiến kết quả khác với precheck bằng SELECT ở application. `CHECK` vẫn bảo vệ nếu code khác viết thẳng giá trị sai, và `units > 0` ngăn request âm/0 gây sai semantics.

### 6.6. Integration test: chín kịch bản

`src/test/java/com/example/invariants/DatabaseInvariantIntegrationTest.java`:

```java
package com.example.invariants;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class DatabaseInvariantIntegrationTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private BookingService booking;

    @Autowired
    private InventoryService inventory;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM bookings");
        jdbc.update("DELETE FROM inventory");
        jdbc.update(
            "INSERT INTO inventory(sku, total_units, available_units) " +
            "VALUES (?, ?, ?)",
            "SKU-1", 2, 2);
    }

    private long bookingCount() {
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM bookings", Long.class);
        return count;
    }

    private int available() {
        Integer count = jdbc.queryForObject(
            "SELECT available_units FROM inventory WHERE sku = ?",
            Integer.class, "SKU-1");
        return count;
    }

    @Test
    void uniqueIsScopedToEventAndSeat() {
        booking.book("E1", "A1", "alice");
        booking.book("E2", "A1", "bob");

        assertEquals(2L, bookingCount());
    }

    @Test
    void duplicateSeatIsRejectedByUnique() {
        booking.book("E1", "A1", "alice");

        assertThrows(DataIntegrityViolationException.class,
            () -> booking.book("E1", "A1", "bob"));

        assertEquals(1L, bookingCount());
    }

    @Test
    void checkRejectsNegativeAvailableUnits() {
        assertThrows(DataIntegrityViolationException.class,
            () -> jdbc.update(
                "UPDATE inventory SET available_units = -1 " +
                "WHERE sku = ?", "SKU-1"));

        assertEquals(2, available());
    }

    @Test
    void checkRejectsAvailableGreaterThanTotal() {
        assertThrows(DataIntegrityViolationException.class,
            () -> jdbc.update(
                "UPDATE inventory SET available_units = 3 " +
                "WHERE sku = ?", "SKU-1"));

        assertEquals(2, available());
    }

    @Test
    void notNullClosesTheCheckUnknownGap() {
        assertThrows(DataIntegrityViolationException.class,
            () -> jdbc.update(
                "UPDATE inventory SET available_units = NULL " +
                "WHERE sku = ?", "SKU-1"));

        assertEquals(2, available());
    }

    @Test
    void constraintViolationRollsBackEarlierBookingInsert() {
        assertThrows(DataIntegrityViolationException.class,
            booking::bookThenBreakStockCheck);

        assertEquals(0L, bookingCount());
        assertEquals(2, available());
    }

    @Test
    void guardedUpdatePreventsSequentialOverselling() {
        assertTrue(inventory.reserve("SKU-1", 2));
        assertFalse(inventory.reserve("SKU-1", 1));

        assertEquals(0, available());
    }

    @Test
    void twoThreadsCannotReserveLastUnitTwice() throws Exception {
        jdbc.update(
            "UPDATE inventory SET available_units = 1 WHERE sku = ?",
            "SKU-1");

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            Future<Boolean> first = pool.submit(() -> {
                start.await();
                return inventory.reserve("SKU-1", 1);
            });
            Future<Boolean> second = pool.submit(() -> {
                start.await();
                return inventory.reserve("SKU-1", 1);
            });

            start.countDown();

            List<Boolean> results = List.of(
                first.get(15, TimeUnit.SECONDS),
                second.get(15, TimeUnit.SECONDS));

            assertEquals(1L, results.stream()
                .filter(Boolean::booleanValue).count());
            assertEquals(0, available());
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }

    private String tryBookAfterPrecheck(
            String customer,
            CountDownLatch ready,
            CountDownLatch release) {
        try {
            booking.bookAfterBothSawEmpty(
                "CONCERT", "A1", customer, ready, release);
            return "COMMITTED";
        } catch (DataIntegrityViolationException expected) {
            return "REJECTED";
        }
    }

    @Test
    void simultaneousPrechecksCannotBypassUnique() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> first = pool.submit(() ->
                tryBookAfterPrecheck("alice", ready, release));
            Future<String> second = pool.submit(() ->
                tryBookAfterPrecheck("bob", ready, release));

            // Cả hai transaction đã SELECT thấy seat chưa có booking.
            assertTrue(ready.await(10, TimeUnit.SECONDS));
            release.countDown();

            List<String> outcomes = List.of(
                first.get(15, TimeUnit.SECONDS),
                second.get(15, TimeUnit.SECONDS));

            assertEquals(1L, outcomes.stream()
                .filter("COMMITTED"::equals).count());
            assertEquals(1L, outcomes.stream()
                .filter("REJECTED"::equals).count());
            assertEquals(1L, bookingCount());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Các test được viết để không phụ thuộc **thread nào thắng**. Bài test race dùng hai transaction riêng trong hai thread; chúng đều đã precheck trước khi được phép INSERT. `UNIQUE` vẫn giữ invariant.

**Vì sao không đặt `@Transactional` lên test class?** Nếu test sở hữu transaction, các service `REQUIRED` có thể chỉ tham gia transaction của test; khi đó việc query số hàng ngay trong test **không** chứng minh service đã commit. Ở fixture này, test không có transaction annotation; service proxy hoàn tất transaction trước khi caller kiểm tra DB.

**Chú ý concurrency fixture:** test chạy mặc định tuần tự giữa các method; hai worker threads chỉ tồn tại trong từng test. `LOCK_TIMEOUT` và pool size được đặt để giảm flaky do tài nguyên. Scheduler không đảm bảo thứ tự winner. Các database engines có chính sách lock timeout/deadlock/serialization khác H2; nếu kết quả test trên production DB khác, cần xem SQLState, isolation, pool, indexes và retry policy. Test concurrency cần timeout hữu hạn và giải phóng executor trong `finally`.

### 6.7. Cách chạy

Trong thư mục `db-invariants`, với Gradle Wrapper:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu dự án chưa có Gradle Wrapper, tạo wrapper bằng Gradle tương thích hoặc chạy `gradle test` với phiên bản được Spring Boot plugin hỗ trợ. Trình biên dịch và JUnit dependencies do Gradle xử lý; không cần tự cấu hình `javac` classpath.

**Kết quả kỳ vọng:** 9 integration tests pass trong fixture Java17/Boot3.3.5/H2 theo code trên, sau khi tải dependencies. JUnit không cam kết thứ tự các test và không có stdout cố định. Báo cáo HTML nằm tại `build/reports/tests/test/index.html`. Đây là **dự đoán từ cấu hình và code**, không phải lời khẳng định bộ test đã được thực thi ở môi trường người đọc.

| Kiểm chứng | Kết quả kỳ vọng |
| --- | --- |
| Ghế `A1` ở hai event khác nhau | Cả hai booking được giữ, count = 2 |
| Hai booking trùng `E1/A1` | Booking thứ hai bị từ chối, count = 1 |
| `available_units=-1` | CHECK từ chối, giá trị vẫn = 2 |
| `available_units=3 > total_units=2` | CHECK từ chối, giá trị vẫn = 2 |
| `available_units=NULL` | NOT NULL từ chối, giá trị vẫn = 2 |
| Insert booking rồi CHECK thất bại trong cùng transaction | Toàn transaction rollback, booking count = 0 |
| Reserve 2 rồi reserve thêm 1 | Lần đầu true, lần sau false, available = 0 |
| Hai thread cùng reserve đơn vị cuối | Một true, một false, available = 0 |
| Hai thread precheck cùng thấy ghế trống | Một commit, một bị unique reject, booking count = 1 |

**Phân biệt kiểm thử:** xác nhận exception **và** trạng thái DB sau boundary. `assertThrows(DataIntegrityViolationException.class, ...)` một mình không đủ để chứng minh mọi statement trước lỗi đã rollback; đó là lý do test thứ sáu còn kiểm tra booking count bằng 0.

## 7. Một quy trình xử lý race trong production

### 7.1. Booking: attempt INSERT là nguồn sự thật

Một flow thông thường:

1. Nhận `event_code`/`seat_code` từ request và validate format.
2. Nếu cần UX “seat đã được giữ”, có thể query trạng thái để hiển thị, nhưng hiểu rằng kết quả đó **có thể stale**.
3. Trong transaction, attempt INSERT booking với unique key đúng.
4. Nếu insert/commit thành công, trả booking đã tạo.
5. Nếu DB báo conflict unique, **sau khi transaction thất bại được kết thúc**, ánh xạ lỗi sang domain result như `SEAT_ALREADY_BOOKED`, có thể HTTP 409.
6. Nếu lỗi khác (CHECK/FK/DB unavailable/deadlock), không tự ánh xạ tất cả thành “ghế đã bán”. Ghi log có correlation ID và phân loại an toàn.
7. Khi retry, dùng request idempotency key và kiểm tra tài nguyên đã tạo trước đó.

Giả sử request trùng đã được xử lý thành công nhưng response bị mất: một lần retry có thể gặp unique constraint. Nếu unique key là **business resource** (seat) và request thuộc một customer khác, đây là conflict. Nếu unique key là **idempotency key**, cần đọc kết quả của request trước và xác minh payload/fingerprint để biết có nên trả lại kết quả cũ hay phản hồi conflict. Không trả success mù khi gặp duplicate.

### 7.2. Inventory: UPDATE có điều kiện đi cùng giao dịch đặt hàng

Giả sử bạn vừa ghi booking vừa giảm kho trong một service:

```java
@Transactional
public void bookAndReserve(String event, String seat, String customer) {
    bookingService.book(event, seat, customer);
    if (!inventoryService.reserve("SKU-1", 1)) {
        throw new IllegalStateException("Not enough inventory");
    }
}
```

Snippet **minh họa cấu trúc**, yêu cầu bean/các biến `bookingService` và `inventoryService`, và method được gọi qua Spring proxy. Nếu cả hai services dùng `REQUIRED` trên **cùng transaction manager/DataSource**, việc insert booking và giảm inventory có thể cùng commit hoặc cùng rollback; ngoại lệ runtime `IllegalStateException` được ném ra khỏi outer method sẽ yêu cầu rollback.

Nhưng nếu booking và stock ở hai databases khác nhau hoặc một service dùng `REQUIRES_NEW`, atomicity ở trên **không tự được bảo đảm**. Không khẳng định một `@Transactional` bảo vệ distributed resources/email/Kafka một cách tự động.

### 7.3. Khi cần invariant trên nhiều row

Ví dụ “chỉ được tối đa 100 booking chưa hủy trên event” mà booking là nhiều row. Nếu dùng:

```sql
SELECT COUNT(*) FROM bookings WHERE event_code = 'E';
-- nếu count < 100 thì INSERT ...
```

hai transaction cùng đọc `99` có thể đều insert, đạt `101`. `UNIQUE(event,seat)` không giúp nếu hai booking chọn **hai seat khác nhau**; `CHECK` trên từng booking row không biết count toàn event.

Các cách đúng tùy mô hình:

- Một row `event_capacity` duy trì `remaining` và cập nhật với guarded UPDATE, cùng transaction với insert booking.
- Dùng row-level pessimistic lock trên một row đại diện event trước khi count+insert, với quy tắc tất cả writer tuân thủ.
- Dùng `SERIALIZABLE` isolation có xử lý **serialization failure/retry** được thiết kế idempotent.
- Dùng các dạng constraint mạnh hơn (exclusion/trigger với locking) nếu DB hỗ trợ và phù hợp.

Một chiến lược khác nhau có chi phí contention, deadlock, throughput và độ phức tạp khác nhau. Không chọn isolation level tùy tiện rồi kết luận an toàn từ một test không có cạnh tranh.

## 8. Giới hạn và tác dụng phụ khi triển khai schema

### 8.1. Thêm UNIQUE vào dữ liệu cũ

Trước khi thêm constraint lên bảng production, kiểm tra duplicates:

```sql
SELECT event_code, seat_code, COUNT(*) AS n
FROM bookings
GROUP BY event_code, seat_code
HAVING COUNT(*) > 1;
```

Đây là SQL truy vấn dữ liệu dùng được trên nhiều RDBMS. Nếu đã có duplicates, việc thêm `UNIQUE` có thể thất bại; cần migration plan làm sạch dữ liệu, xử lý nhiều writer đang hoạt động, tạo index/constraint theo cơ chế online DDL của database và kiểm thử deploy/rollback. “Đã tạo unique index” không đồng nghĩa mọi nhánh code cũ dùng đúng key business hoặc normalization.

### 8.2. Thêm CHECK vào dữ liệu cũ

Kiểm tra dữ liệu không hợp lệ:

```sql
SELECT sku, total_units, available_units
FROM inventory
WHERE total_units < 0
   OR available_units < 0
   OR available_units > total_units
   OR total_units IS NULL
   OR available_units IS NULL;
```

Với schema mẫu các cột đã NOT NULL, hai điều kiện NULL là defensive check khi dùng với hệ dữ liệu cũ có schema khác. Trước migration, thống nhất cách xử lý những row đang vi phạm: sửa dữ liệu theo business invariant, không chỉ xóa “cho thêm constraint chạy qua”.

### 8.3. Chi phí index, contention và locking

Một unique constraint thường được DB thực thi bằng unique index. Điều này có chi phí ghi/index maintenance, có thể gây contention trên hot keys. Nhưng bỏ unique index để “tăng tốc” rồi tự khóa ở application không phải giải pháp mặc định: nó làm mất lớp phòng vệ giữa các process, jobs và writer không đi qua cùng distributed lock.

Cũng cần tránh tạo nhiều index trùng lặp. Với PostgreSQL, một unique constraint đã tạo unique index phù hợp; kiểm tra index plan trước khi tạo thêm index bằng tay.

### 8.4. Vi phạm constraint không luôn là “dữ liệu đầu vào sai”

Một duplicate có thể là:

- Hai người cùng đặt seat, business conflict bình thường.
- Retry cùng request idempotent.
- Một bug tạo cùng key nhiều lần.
- Job/backfill import trùng dữ liệu.
- Một bản ghi “active” khác đã tồn tại do soft delete semantics.
- Khác biệt casefold/normalization/collation.
- Chạy không đúng tenant scope.

Vì vậy một exception chung không đủ để quyết định HTTP status, retry hay thông báo. Tầng persistence cần cung cấp ngữ cảnh constraint; tầng domain cần biết invariant nào bị vi phạm, tầng API mới quyết định response.

## 9. So sánh các kỹ thuật bảo vệ concurrency

| Kỹ thuật | Bảo vệ tốt nhất | Không tự giải quyết |
| --- | --- | --- |
| `UNIQUE` | Không cho duplicate key commit | Aggregate count, mất update, trùng semantic nếu key normalization sai |
| `CHECK` | State của row hợp lệ | Điều kiện dựa trên row khác, lost update |
| `NOT NULL` | Không thiếu required fields | Concurrency uniqueness |
| `FOREIGN KEY` | Referential integrity | Multi-row business quotas |
| Guarded `UPDATE` | Trừ số lượng không âm ngay trong statement | Bất biến nằm ở những bảng độc lập |
| `SELECT ... FOR UPDATE` | Phối hợp các writer lock row đang tồn tại | Kiểm tra sự **vắng mặt** của row không có sẵn để lock trong mọi DB/isolation |
| Optimistic locking `@Version` | Phát hiện update conflict của cùng entity | Không ngăn insert duplicate nếu thiếu unique |
| `SERIALIZABLE` + retry | Nhiều dạng anomaly giữa transactions | Không tự thay thế mọi constraint/schema rule |
| `@Transactional` | Boundary atomic commit/rollback của resource tham gia | Không khóa đúng business key nếu logic vẫn có TOCTOU race |
| Application prevalidation | UX, fast rejection | Không phải final arbiter concurrency |

**TOCTOU** (time-of-check to time-of-use) là khoảng cách giữa lúc kiểm tra và lúc sử dụng. Trong booking, `existsBy...` là check và `insert` là use. `UNIQUE` chuyển quyết định cuối cùng về cùng atomic DB write path.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Hai request cùng `SELECT COUNT(*)=0` rồi `INSERT` một booking có cặp event/seat giống nhau. `@Transactional` có tự chống trùng ở `READ_COMMITTED` không?

**Trả lời:** Không. Cần `UNIQUE(event_code, seat_code)` (hoặc cơ chế ràng buộc tương đương) để DB bác bỏ state duplicate, kể cả khi cả hai đã precheck thành công.

**Câu 2.** Có `CHECK(available_units >= 0)`. Hai request đọc `available=1` rồi cùng ghi `available=0`. Có thể đã bán hai lần nhưng DB vẫn hợp lệ không?

**Trả lời:** Có, vì có thể lost update hoặc quota invariant chưa được cập nhật đúng. Dùng atomic guarded decrement trên cùng row hoặc locking/isolation strategy phù hợp, cộng CHECK làm tuyến bảo vệ.

**Câu 3.** Vì sao `CHECK(price >= 0)` không thay thế `NOT NULL`?

**Trả lời:** Khi price NULL, điều kiện thường là UNKNOWN; CHECK không nhất thiết từ chối. Cần NOT NULL nếu giá trị là bắt buộc.

**Câu 4.** `UNIQUE(seat_code)` có đúng với hệ nhiều sự kiện cùng seat A1 không?

**Trả lời:** Không. Business scope là event+seat; cần composite unique key.

**Câu 5.** Nếu `DataIntegrityViolationException` xảy ra, luôn trả “booking trùng” được không?

**Trả lời:** Không. Exception còn có thể do CHECK/NOT NULL/FK. Phải phân loại constraint hoặc use-case đúng cách.

**Câu 6.** Vì sao không nên catch duplicate ngay trong một `@Transactional` method rồi tiếp tục nhiều SQL?

**Trả lời:** DB hoặc ORM transaction có thể đã ở trạng thái aborted/rollback-only. Catch có thể che lỗi gốc và dời lỗi ra commit; bắt tại boundary an toàn sau rollback hoặc dùng upsert chuyên biệt có semantics rõ.

**Câu 7.** `JpaRepository.save` thành công nghĩa unique chắc chắn đã được DB xác nhận chưa?

**Trả lời:** Không. JPA có thể defer SQL tới flush/commit; thậm chí flush không phải durable commit.

**Câu 8.** Hai transaction cùng cần giảm đơn vị hàng cuối, câu SQL nào an toàn hơn đọc rồi ghi?

**Trả lời:** Một `UPDATE inventory SET available=available-1 WHERE sku=? AND available>=1`, kiểm tra affected row count và transaction completion. CHECK ngăn âm khi code khác ghi sai.

**Câu 9.** Một ràng buộc “tổng booking active trên event <= 100” có thể đảm bảo bằng CHECK trên từng booking row không?

**Trả lời:** Không theo row-level CHECK thông thường. Cần thiết kế counter row atomic/locking/serializable hoặc công cụ database dành cho invariant cross-row.

**Câu 10.** Tại sao test không nên chỉ `assertThrows`?

**Trả lời:** Exception xác nhận một đường lỗi, nhưng invariant cuối phải được đo sau transaction boundary bằng truy vấn DB; đồng thời cần kiểm tra các statement trước lỗi đã rollback.

**Câu 11.** Constraint có bảo vệ khi job ngoài Spring trực tiếp ghi SQL không?

**Trả lời:** Có, nếu mọi writer thật sự dùng database/schema/table/constraint ấy và DB thực thi constraint. Đó là lợi thế quan trọng so với prevalidation chỉ nằm trong Spring service.

**Câu 12.** Nếu cần idempotency, bắt duplicate và trả success luôn có đủ không?

**Trả lời:** Không. Cần phân biệt duplicate business conflict với cùng idempotency key từ cùng request; đọc kết quả trước và xác minh payload/hash để trả lại đúng kết quả.

## 11. Checklist triển khai vào hệ thống thật

1. Viết rõ invariant bằng ngôn ngữ nghiệp vụ, gồm tenant, trạng thái active, soft delete và normalization.
2. Chọn đúng DB primitive: `UNIQUE`, `CHECK`, `NOT NULL`, `FOREIGN KEY`, guarded update hoặc cơ chế cross-row.
3. Đặt tên constraint rõ, ví dụ `uq_event_seat`, `ck_stock_bounds`.
4. Kiểm tra dữ liệu production hiện có trước migration.
5. Thiết kế migration có tính đến concurrent writes, lock duration và online DDL của engine.
6. Đảm bảo mọi đường ghi (HTTP, batch, import, admin jobs) đều phải qua cùng DB invariant.
7. Giữ Java validation để UX tốt, nhưng không coi check-before-write là lock.
8. Kiểm tra `@Transactional` thật sự đi qua Spring proxy và dùng đúng transaction manager.
9. Catch/mapping errors ở boundary sau khi transaction đã kết thúc; phân loại constraint, không nuốt mọi `DataIntegrityViolationException`.
10. Với JPA, kiểm tra flush/commit timing thay vì chỉ `save` return.
11. Với inventory, dùng conditional SQL update và kiểm tra affected rows; áp dụng retry hợp lệ khi DB báo deadlock/serialization conflict.
12. Viết race test có barrier và timeout, test DB thật hoặc DB gần production; không dựa vào một lần chạy ngẫu nhiên.
13. Đọc DB sau transaction boundary để kiểm tra invariant, không chỉ exception/log/first-level cache.
14. Đảm bảo response gửi tới client phản ánh outcome đã commit, và retry idempotent khi kết quả chưa xác định.
15. Theo dõi unique/check violations bằng metrics có phân loại, không log secrets hay dữ liệu nhạy cảm.

## 12. Nguồn tham khảo

- [PostgreSQL Documentation — Constraints: CHECK, NOT NULL, UNIQUE, PRIMARY KEY](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [H2 Database — SQL Grammar: CHECK/UNIQUE/NULLS DISTINCT](https://h2database.github.io/html/grammar.html)
- [H2 Database — ErrorCode: duplicate key và CHECK violation](https://h2database.github.io/javadoc/org/h2/api/ErrorCode.html)
- [Spring Framework — DataIntegrityViolationException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html)
- [Spring Framework — DuplicateKeyException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/dao/DuplicateKeyException.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Rollback Rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — JDBC Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring Framework — Transactional Test Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
