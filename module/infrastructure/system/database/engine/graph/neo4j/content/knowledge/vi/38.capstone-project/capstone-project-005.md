# Tích hợp Java hoặc Spring Boot với giao dịch và xử lý lỗi

Một ứng dụng Neo4j hoàn chỉnh không chỉ cần query Cypher trả đúng dữ liệu trong Neo4j Browser. Khi người dùng gửi yêu cầu qua HTTP, hệ thống phải **xác thực, kiểm tra quyền, quản lý transaction, tránh ghi một nửa dữ liệu, xử lý hai yêu cầu đồng thời, retry lỗi phù hợp và trả kết quả có thể đối soát**. Đây là điểm kết nối kiến thức mô hình đồ thị với kỹ năng xây ứng dụng Java vận hành được.

Bài thuộc chương **Đồ án thực hành** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module sử dụng Neo4j để mô hình hóa dữ liệu liên kết bằng **property graph**, truy vấn node, relationship và đường đi với Cypher, áp dụng index/constraint, nhập dữ liệu, Java Driver, Spring Data Neo4j và những nguyên tắc vận hành. Đồ án này đưa các thành phần đó vào một ứng dụng **Spring Boot + Neo4j Java Driver** có giao dịch và xử lý lỗi rõ ràng. Cuối bài cũng có phương án thay lớp truy cập dữ liệu bằng Spring Data Neo4j (SDN).

**Đề bài:** xây API đặt chỗ cho sự kiện. Một người tham dự yêu cầu đặt một số ghế; hệ thống phải kiểm tra số ghế còn lại, trừ ghế và tạo dữ liệu đặt chỗ cùng các relationship **trong một transaction Neo4j**. Nếu client gửi lại yêu cầu do timeout, hệ thống không được trừ ghế hai lần. Nếu nhiều người cùng đặt ghế cuối, tổng ghế đã xác nhận không được vượt sức chứa.

Sau khi thực hiện, bạn sẽ có:

1. Property graph và schema Cypher với khóa nghiệp vụ, index/constraint.
2. API `POST /api/v1/bookings` và truy vấn tra cứu kết quả bằng idempotency key.
3. Java service sử dụng `Driver`, `Session`, `executeWrite` và các câu Cypher tham số hóa.
4. Cách khóa/tuần tự hóa cập nhật tồn kho ghế để bảo toàn số ghế khi đồng thời.
5. Chính sách lỗi: dữ liệu sai, không tìm thấy, thiếu ghế, trùng request, lỗi kết nối và outcome chưa xác định.
6. Ma trận kiểm thử, tiêu chí chấp nhận, dashboard cơ bản và kế hoạch triển khai/rollback.

> **Phạm vi:** các đoạn mã minh họa Java 17+ và Spring Boot/Spring Data Neo4j/Neo4j Java Driver tương thích với nhau. Cú pháp cấu hình, driver và test dependency cần kiểm tra theo phiên bản thực tế. Bài chủ yếu trình bày kiến trúc và mã mẫu tự chứa để triển khai đồ án; không tuyên bố một bộ file hoàn chỉnh đã được build hoặc một Neo4j đang chạy.

## 1. Yêu cầu nghiệp vụ và tiêu chí chấp nhận

Giả sử một tổ chức có nhiều sự kiện. Mỗi sự kiện có sức chứa và số ghế còn lại. Người dùng đã đăng nhập có thể đặt từ 1 đến 5 ghế mỗi yêu cầu.

| ID | Yêu cầu | Tiêu chí kiểm chứng |
| --- | --- | --- |
| R01 | Chỉ người đã xác thực được đặt chỗ. | Không có principal hợp lệ thì API từ chối trước khi truy cập dữ liệu. |
| R02 | Không đọc/ghi xuyên tenant. | Tenant được xác minh từ security context; mọi node trong giao dịch cùng tenant. |
| R03 | Ghế còn lại không âm. | Dù request đồng thời, `availableSeats >= 0` sau các transaction thành công. |
| R04 | Không giữ ghế khi đặt chỗ thất bại. | Nếu một bước tạo Booking/relationship lỗi, thay đổi ghế rollback toàn bộ. |
| R05 | Một idempotency key chỉ đại diện một yêu cầu. | Gửi lại cùng key + payload trả cùng booking; key + payload khác bị từ chối. |
| R06 | Khóa nghiệp vụ không trùng. | Constraint ngăn hai Booking cùng key trong tenant. |
| R07 | Lỗi mạng không gây đặt chỗ lặp. | Client dùng lại key; server hòa giải trạng thái đã commit khi cần. |
| R08 | Chỉ sự kiện đang mở được đặt. | Event không `OPEN` thì từ chối và không trừ ghế. |
| R09 | Response không lộ dữ liệu nội bộ. | Không trả stack trace, Cypher, password hoặc property không cần thiết. |
| R10 | Có quan sát và khả năng phục hồi. | Log/metric có request ID, mã lỗi, độ trễ; test backup và restart ở môi trường riêng. |

Đây là yêu cầu tối thiểu. Tính năng hủy chỗ, hoàn ghế, thanh toán và danh sách chờ **không nằm trong luồng ghi chính**; có thể triển khai như phần mở rộng với transaction và chính sách idempotency riêng.

## 2. Chọn mô hình property graph

Một mô hình phù hợp:

~~~text
(:CapAttendee {tenantId, attendeeId, displayName})
             |
             | [:CAP_HAS_BOOKING]
             v
(:CapBooking {
  tenantId, bookingId, requestKey,
  attendeeId, eventId, seats, remainingAfter,
  status, createdAt
})
             |
             | [:CAP_FOR_EVENT]
             v
(:CapEvent {
  tenantId, eventId, title,
  capacity, availableSeats, status, lockVersion
})
~~~

Vì sao chọn **Booking làm node**, thay vì chỉ một relationship từ Attendee đến Event?

- Booking có vòng đời, trạng thái, mã request, số ghế và thời điểm riêng.
- Cần unique constraint theo `(tenantId, requestKey)` để bảo vệ yêu cầu idempotent.
- Một người có thể đặt nhiều lần cho cùng một sự kiện nếu nghiệp vụ cho phép; các booking có identity riêng.
- Dễ bổ sung audit, hủy chỗ, trạng thái thanh toán hoặc outbox về sau.

Quan hệ được sử dụng theo **chiều cố định**: `(Attendee)-[:CAP_HAS_BOOKING]->(Booking)-[:CAP_FOR_EVENT]->(Event)`. Không tạo cạnh ngược rồi dùng traversal không hướng để “bù”.

### 2.1. Bất biến dữ liệu

Đặt các bất biến rõ trước khi viết Java:

| Mã | Bất biến | Phần bảo vệ chính |
| --- | --- | --- |
| I1 | `0 <= availableSeats <= capacity`. | Giao dịch cập nhật cùng event với kiểm số ghế và khóa ghi. |
| I2 | Mỗi Booking có đúng một Attendee và một Event hợp lệ. | Cypher tạo liên kết trong cùng transaction; kiểm thử bất biến. |
| I3 | Booking và hai endpoint cùng `tenantId`. | Query có tenant ở mọi node, security context. |
| I4 | `(tenantId, bookingId)` duy nhất. | Uniqueness constraint Neo4j. |
| I5 | `(tenantId, requestKey)` duy nhất. | Uniqueness constraint Neo4j + kiểm payload khi replay. |
| I6 | Booking `CONFIRMED` chỉ được tạo khi trừ ghế thành công. | Atomic Neo4j transaction. |
| I7 | Client retry cùng key không tạo thêm Booking. | Đọc trước, kiểm lại sau khóa, constraint và hòa giải lỗi. |

**Lưu ý:** uniqueness constraint theo cặp thông thường bảo đảm tính duy nhất **khi có giá trị**; nó không mặc nhiên ràng buộc mọi property tồn tại. API/Java cần validate dữ liệu hoặc dùng key/existence constraint theo edition và phiên bản.

## 3. Kiến trúc ứng dụng và ranh giới transaction

~~~text
Client Web/Mobile
   |
   | POST /api/v1/bookings
   | Idempotency-Key: <request-key>
   v
Spring Security / Authn
   |
   v
BookingController
   |
   +--> TenantScope: tenant từ principal đã xác minh
   |
   +--> BookingService
           |
           | Neo4j Driver executeWrite(...)
           v
       Neo4j transaction
         1. Tra requestKey đã có
         2. Lấy quyền ghi/khóa trên Event
         3. Kiểm tra requestKey lại
         4. Kiểm người tham dự, sự kiện, số ghế
         5. Trừ ghế + tạo Booking + hai relationship
         6. COMMIT hoặc ROLLBACK toàn bộ
           |
           v
      BookingReceipt (DTO)
~~~

Ranh giới là **một Neo4j transaction** cho toàn bộ mutation liên quan tới graph. Không tách `SET availableSeats` và `CREATE Booking` thành hai lần `session.run(...)` autocommit độc lập.

Mô hình triển khai trong đồ án:

| Thành phần | Trách nhiệm | Không được làm |
| --- | --- | --- |
| Spring Security | Xác thực user; cung cấp principal/claim đáng tin. | Không coi header tenant của client là bằng chứng quyền. |
| Controller | Validate JSON/header và chọn response code. | Không tự ghép Cypher từ chuỗi do user nhập. |
| TenantScope | Xác nhận user có quyền thao tác tenant. | Không lấy tenant mặc định khi principal null. |
| BookingService | Điều phối idempotency, transaction và domain error. | Không gửi email/broker message ngay trong callback có thể retry. |
| Neo4j Driver | Quản lý session, transaction, routing và retry phù hợp. | Không tự hiểu bất biến ghế/tenant của nghiệp vụ. |
| Neo4j | Lưu graph, thực thi transaction/constraint và khóa ghi. | Không tự bảo vệ API khỏi user không được phép. |

## 4. Chuẩn bị môi trường và dependency

Môi trường tối thiểu cho đồ án:

- JDK được phiên bản Spring Boot đang chọn hỗ trợ (ví dụ Java 17+ với các dòng phù hợp).
- Một Neo4j instance **thử nghiệm** có quyền tạo schema và dữ liệu `Cap*`.
- Spring Boot với Web, Validation, Security, Spring Data Neo4j starter (cung cấp Driver được autoconfigure).
- Công cụ gửi HTTP request, Neo4j Browser/Cypher Shell và framework kiểm thử JUnit.
- Tùy chọn: Testcontainers Neo4j để kiểm thử tích hợp tự động.

Ví dụ dependency theo **Gradle Kotlin DSL**, giả định dự án đã dùng plugin Spring Boot và dependency management/BOM tương thích:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-data-neo4j")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:neo4j")
}
~~~

Đừng tự đoán phiên bản mới nhất hoặc trộn các major version Boot/SDN/Java Driver. Cần pin phiên bản qua BOM/lockfile được nhóm phê duyệt và kiểm tương thích với Neo4j server đang chạy.

### 4.1. Kết nối không hardcode credential

Ví dụ `application.yml`:

~~~yaml
spring:
  neo4j:
    uri: ${NEO4J_URI}
    authentication:
      username: ${NEO4J_USERNAME}
      password: ${NEO4J_PASSWORD}
~~~

Các biến môi trường phải được secret manager/deployment cung cấp; không commit password vào Git hoặc ghi vào log. Dùng `neo4j+s://` hoặc cấu hình Bolt/TLS có certificate verification phù hợp với triển khai thực; không tắt xác minh TLS trong production để giải quyết tạm lỗi kết nối.

Ví dụ Spring Data Neo4j starter tự cấu hình `org.neo4j.driver.Driver` khi môi trường Spring Boot tương thích; code bên dưới **inject Driver đó**, không tự tạo nhiều pool Driver tùy ý.

### 4.2. Cấu trúc project đề xuất

~~~text
src/main/java/.../
  BookingApplication.java
  api/
    BookingController.java
    BookingInput.java
    BookingReceipt.java
    ApiErrorHandler.java
  security/
    TenantScope.java
    SecurityConfiguration.java
  booking/
    BookingService.java
    BookingProblem.java
  monitoring/
    RequestCorrelationFilter.java

src/main/resources/
  application.yml
  migrations/            (quy trình Cypher schema)

src/test/java/.../
  BookingIntegrationTest.java
  BookingConcurrencyTest.java
  BookingSecurityTest.java
~~~

Đây là **sơ đồ tên file cần tự tạo trong project của người học**, không phải những file được tạo ngoài Markdown bài giảng này.

## 5. Schema Neo4j: tạo constraint trước khi mở API

Chạy trong database **học tập**. Tên constraint được đặt riêng để không tác động schema của hệ thống khác:

~~~cypher
CREATE CONSTRAINT cap_attendee_key IF NOT EXISTS
FOR (a:CapAttendee)
REQUIRE (a.tenantId, a.attendeeId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT cap_event_key IF NOT EXISTS
FOR (e:CapEvent)
REQUIRE (e.tenantId, e.eventId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT cap_booking_key IF NOT EXISTS
FOR (b:CapBooking)
REQUIRE (b.tenantId, b.bookingId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT cap_booking_request_key IF NOT EXISTS
FOR (b:CapBooking)
REQUIRE (b.tenantId, b.requestKey) IS UNIQUE;
~~~

Hai constraint trên Booking không trùng vai trò. `bookingId` là định danh kết quả; `requestKey` là định danh **thao tác do client có quyền gửi**, dùng để hòa giải retry.

Kiểm tra:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name STARTS WITH 'cap_'
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

Khi một constraint được tạo trên dữ liệu đã có và có trùng khóa, lệnh có thể thất bại. Không xóa node trùng ngẫu nhiên; phải đối soát dữ liệu và quyết định cách hợp nhất theo nghiệp vụ. Uniqueness constraint thường tạo index hỗ trợ tra cứu; không tự `DROP INDEX` của constraint khi “dọn index”.

### 5.1. Dữ liệu mẫu

~~~cypher
MERGE (a:CapAttendee {
  tenantId: 'tenant-demo',
  attendeeId: 'A01'
})
ON CREATE SET a.displayName = 'Khách mẫu 01';
~~~

~~~cypher
MERGE (e:CapEvent {
  tenantId: 'tenant-demo',
  eventId: 'E01'
})
ON CREATE SET
  e.title = 'Hội thảo Neo4j',
  e.capacity = 3,
  e.availableSeats = 3,
  e.status = 'OPEN',
  e.lockVersion = 0;
~~~

`ON CREATE SET` cố ý chỉ thiết lập tồn kho khi sự kiện được tạo lần đầu. Nếu chạy lại fixture, không tự reset `availableSeats` và ghi đè các booking đang tồn tại.

Tạo thêm một attendee để kiểm tra đồng thời:

~~~cypher
MERGE (a:CapAttendee {
  tenantId: 'tenant-demo',
  attendeeId: 'A02'
})
ON CREATE SET a.displayName = 'Khách mẫu 02';
~~~

**Không dùng fixture production để thực hành** và không đổi capacity/ghế của sự kiện đang bán vé chỉ vì chạy lại câu lệnh seed.

## 6. Hợp đồng HTTP: request, response và lỗi

### 6.1. Tạo booking

~~~http
POST /api/v1/bookings HTTP/1.1
Content-Type: application/json
Authorization: Bearer <valid-token>
Idempotency-Key: req-demo-001

{
  "attendeeId": "A01",
  "eventId": "E01",
  "seats": 2
}
~~~

Response lần đầu minh họa:

~~~json
{
  "bookingId": "b2db6cc2-4f75-45b3-b7bb-1ed9ca2f67b5",
  "status": "CONFIRMED",
  "seats": 2,
  "remainingAfter": 1,
  "replayed": false
}
~~~

Gửi lại cùng `Idempotency-Key` và payload trả **cùng bookingId/seats/remainingAfter**, với `replayed: true`. Số ghế còn lại trong event có thể thay đổi do những booking khác, nhưng `remainingAfter` trên receipt là **snapshot tại lúc booking này commit**, không phải trạng thái ghế hiện hành.

### 6.2. Bảng trạng thái lỗi

| Trường hợp | HTTP gợi ý | Mã lỗi ứng dụng |
| --- | --- | --- |
| JSON/header không hợp lệ, số ghế ngoài 1..5 | 400 | `INVALID_REQUEST` |
| Không có xác thực | 401 | `UNAUTHENTICATED` |
| Người dùng không được phép đặt trong tenant | 403 | `FORBIDDEN` |
| Event/Attendee không tồn tại trong phạm vi hợp lệ | 404 | `ENTITY_NOT_FOUND` |
| Event đã đóng hoặc thiếu ghế | 409 | `EVENT_UNAVAILABLE` / `NO_SEATS` |
| Request key cũ nhưng payload khác | 409 | `IDEMPOTENCY_KEY_REUSED` |
| Driver tạm thời không kết nối được/hết ngân sách retry | 503 | `TEMPORARY_UNAVAILABLE` |
| Không biết transaction đã commit hay chưa | 503 hoặc trạng thái pending tra cứu | `OUTCOME_UNKNOWN` |
| Lỗi triển khai/schema không lường trước | 500 | `INTERNAL_ERROR` |

Không trả toàn bộ message của Neo4j `ClientException`, stack trace hoặc Cypher text cho HTTP client. Những lỗi như constraint collision cần được phân loại **theo ngữ cảnh**, không tự chuyển tất cả lỗi database thành HTTP 409.

## 7. Java DTO và xác thực tenant

Java 17+ với Bean Validation. Hai record sau đặt trong **hai tệp riêng** `BookingInput.java` và `BookingReceipt.java` (cùng package của API), dù được hiển thị gần nhau trong bài:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record BookingInput(
    @NotBlank String attendeeId,
    @NotBlank String eventId,
    @Min(1) @Max(5) int seats
) {}
~~~

~~~java
public record BookingReceipt(
    String bookingId,
    String status,
    int seats,
    int remainingAfter,
    boolean replayed
) {}
~~~

Nếu dự án sử dụng Spring Boot/Validation có namespace khác, cần chuyển import theo phiên bản. Record `BookingInput` chỉ chứa dữ liệu client được phép cung cấp. **Không có tenantId hoặc availableSeats trong request body**.

Hợp đồng giải quyết tenant:

~~~java
import java.security.Principal;

public interface TenantScope {
    // Xác thực principal, kiểm quyền với tenant và trả tenant đáng tin.
    // Nếu không thể xác minh: từ chối, không trả tenant mặc định.
    String requireTenant(Principal principal);
}
~~~

Một quyền **cấp tenant** không tự đồng nghĩa người dùng có thể đặt chỗ thay **mọi attendee** trong tenant. Thêm một hợp đồng authorization theo đối tượng:

~~~java
import java.security.Principal;

public interface BookingAccess {
    // Từ chối nếu principal không có quyền đặt chỗ cho attendee.
    void requireBookPermission(
        Principal principal, String tenantId, String attendeeId);
}
~~~

Trong sản phẩm thật, cần có bean thực thi `TenantScope` và `BookingAccess` từ Spring Security authentication/JWT claims đã **kiểm tra chữ ký, issuer, audience, expiry và quyền**; kiểm tra quan hệ user–attendee nếu mô hình yêu cầu. Một header `X-Tenant-Id` do client tự gửi không đủ để cho phép truy cập tenant đó. API mẫu chỉ hoàn chỉnh về mặt bảo mật sau khi cấu hình authentication/authorization này được triển khai và kiểm thử.

## 8. Domain exception và quy ước outcome

Tách lỗi nghiệp vụ khỏi exception kỹ thuật:

~~~java
import org.springframework.http.HttpStatus;

public final class BookingProblem extends RuntimeException {
    private final HttpStatus status;
    private final String code;

    public BookingProblem(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public HttpStatus status() { return status; }
    public String code() { return code; }
}
~~~

`BookingProblem` biểu diễn những lỗi **đã biết**: sự kiện không tồn tại, thiếu ghế, key sai payload. Những lỗi này không phải là lý do để driver tự retry transaction; chạy lại ngay với dữ liệu y hệt chỉ lặp lỗi.

Ngược lại, lỗi mất kết nối có thể xảy ra **trước, trong hoặc sau COMMIT**. Nếu ứng dụng không nhận được response từ server, nó **không thể suy ra transaction chắc chắn rollback**. Cần dùng request key để tra cứu lại trạng thái.

## 9. Giao dịch ghi có kiểm soát với Neo4j Java Driver

Đây là phần lõi đồ án. Code mẫu sử dụng Neo4j Java Driver `executeWrite` (managed transaction) và **hai truy vấn riêng** để bảo đảm sự kiện được khóa ghi trước khi đọc số ghế để quyết định.

Ý tưởng:

1. Kiểm tra đã có Booking theo `tenantId + requestKey` chưa; nếu có, xác nhận payload trùng và trả kết quả.
2. Lấy write lock của Event bằng một cập nhật property `lockVersion` trên đúng node.
3. **Kiểm tra lại** requestKey sau khi đã giữ lock: yêu cầu khác có thể vừa commit trong lúc request này chờ.
4. Đọc trạng thái Event/Attendee **sau khi giữ write lock**; từ chối khi thiếu ghế.
5. Trong chính transaction đó, trừ ghế, tạo Booking và hai relationship.
6. Nếu xảy ra exception trước commit, rollback tất cả. Nếu commit thành công, trả receipt.

### 9.1. Vì sao cần khóa trước khi đọc số ghế?

Đây là pattern nguy hiểm khi concurrent:

~~~text
Event.availableSeats = 1

Request A đọc availableSeats = 1
Request B đọc availableSeats = 1
A quyết định có thể đặt 1 ghế
B quyết định có thể đặt 1 ghế
A và B cùng ghi trên cùng node theo cách không đồng bộ
=> Có nguy cơ mất cập nhật hoặc chấp nhận quá số ghế
~~~

Chỉ bọc nhiều câu query trong một transaction **không tự đủ** nếu logic đưa ra quyết định từ giá trị cũ trước khi chặn các writer cạnh tranh. Ở mẫu này, trước khi đọc để quyết định, transaction **ghi lên node Event** và Neo4j phải lấy write lock cho node đó. Các transaction tranh chấp cùng Event được tuần tự hóa tại điểm khóa; câu đọc số ghế tiếp theo diễn ra khi transaction đang giữ quyền ghi.

Code không gọi APOC lock procedure và không dựa vào `MERGE` như một cơ chế thay thế transaction. Với mô hình phức tạp khóa **nhiều Event**, phải chọn thứ tự khóa nhất quán để giảm deadlock và kiểm thử thực tế.

### 9.2. Lookup receipt theo request key

~~~java
private static final String FIND_BY_REQUEST = """
    MATCH (b:CapBooking {
      tenantId: $tenantId,
      requestKey: $requestKey
    })
    RETURN b.bookingId AS bookingId,
           b.attendeeId AS attendeeId,
           b.eventId AS eventId,
           b.seats AS seats,
           b.remainingAfter AS remainingAfter,
           b.status AS status
    """;
~~~

Khóa request phải là chuỗi khó đoán/đủ entropy cho client, giới hạn độ dài và không chứa password/PII. Mỗi key chỉ đại diện một **thao tác cụ thể trong một tenant**; không cần đưa header key thô vào log tập trung.

### 9.3. Service mẫu: đặt chỗ và hòa giải

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionContext;
import org.neo4j.driver.exceptions.ClientException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public final class BookingService {
    private static final String DATABASE = "neo4j";

    private static final String FIND_BY_REQUEST = """
        MATCH (b:CapBooking {
          tenantId: $tenantId,
          requestKey: $requestKey
        })
        RETURN b.bookingId AS bookingId,
               b.attendeeId AS attendeeId,
               b.eventId AS eventId,
               b.seats AS seats,
               b.remainingAfter AS remainingAfter,
               b.status AS status
        """;

    private final Driver driver;

    public BookingService(Driver driver) {
        this.driver = driver;
    }

    public BookingReceipt reserve(
            String tenantId, String requestKey, BookingInput input) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new BookingProblem(HttpStatus.FORBIDDEN,
                "FORBIDDEN", "Chưa xác minh tenant");
        }
        if (requestKey == null || requestKey.isBlank()
                || requestKey.length() > 128) {
            throw new BookingProblem(HttpStatus.BAD_REQUEST,
                "INVALID_REQUEST", "Idempotency-Key không hợp lệ");
        }
        if (input == null || input.eventId() == null
                || input.eventId().isBlank()
                || input.attendeeId() == null
                || input.attendeeId().isBlank()
                || input.seats() < 1 || input.seats() > 5) {
            throw new BookingProblem(HttpStatus.BAD_REQUEST,
                "INVALID_REQUEST", "Payload không hợp lệ");
        }

        // Sinh ngoài callback: không gây external side effect khi retry.
        String bookingId = UUID.randomUUID().toString();
        try (Session session = driver.session(
                SessionConfig.forDatabase(DATABASE))) {
            return session.executeWrite(tx ->
                doReserve(tx, tenantId, requestKey, input, bookingId));
        } catch (ClientException ex) {
            // Chỉ hòa giải collision của UNIQUE constraint;
            // không nuốt lỗi Cypher/schema khác.
            if (!"Neo.ClientError.Schema.ConstraintValidationFailed"
                    .equals(ex.code())) {
                throw ex;
            }
            BookingReceipt found = lookupAfterCollision(
                tenantId, requestKey, input);
            if (found != null) return found;
            throw ex;  // Collision khác, không suy diễn thành replay.
        }
    }

    private BookingReceipt doReserve(
            TransactionContext tx, String tenantId, String requestKey,
            BookingInput input, String bookingId) {
        Map<String, Object> ids = Map.of(
            "tenantId", tenantId,
            "requestKey", requestKey,
            "eventId", input.eventId(),
            "attendeeId", input.attendeeId()
        );

        // 1. Fast path: request đã commit từ lần trước?
        List<Record> prior = tx.run(FIND_BY_REQUEST, ids).list();
        if (!prior.isEmpty()) {
            return asReceipt(prior.get(0), input, true);
        }

        // 2. Một câu ghi riêng lấy write lock trên Event.
        List<Record> locked = tx.run("""
            MATCH (e:CapEvent {
              tenantId: $tenantId,
              eventId: $eventId
            })
            SET e.lockVersion = coalesce(e.lockVersion, 0) + 1
            RETURN e.eventId AS eventId
            """, ids).list();
        if (locked.isEmpty()) {
            throw new BookingProblem(HttpStatus.NOT_FOUND,
                "ENTITY_NOT_FOUND", "Không có sự kiện hợp lệ");
        }

        // 3. Sau khi được tuần tự hóa trên Event, đọc lại key.
        prior = tx.run(FIND_BY_REQUEST, ids).list();
        if (!prior.isEmpty()) {
            return asReceipt(prior.get(0), input, true);
        }

        // 4. Đọc ghế và xác minh Attendee sau khi có write lock.
        List<Record> inventory = tx.run("""
            MATCH (e:CapEvent {
              tenantId: $tenantId,
              eventId: $eventId
            })
            MATCH (a:CapAttendee {
              tenantId: $tenantId,
              attendeeId: $attendeeId
            })
            RETURN e.availableSeats AS availableSeats,
                   e.capacity AS capacity,
                   e.status AS eventStatus
            """, ids).list();
        if (inventory.isEmpty()) {
            throw new BookingProblem(HttpStatus.NOT_FOUND,
                "ENTITY_NOT_FOUND", "Không có người tham dự hợp lệ");
        }

        Record state = inventory.get(0);
        if (state.get("eventStatus").isNull() ||
                !"OPEN".equals(state.get("eventStatus").asString())) {
            throw new BookingProblem(HttpStatus.CONFLICT,
                "EVENT_UNAVAILABLE", "Sự kiện chưa mở hoặc đã đóng");
        }
        if (state.get("availableSeats").isNull()
                || state.get("capacity").isNull()) {
            throw new BookingProblem(HttpStatus.CONFLICT,
                "INVALID_INVENTORY", "Số ghế chưa được khởi tạo");
        }
        int available = state.get("availableSeats").asInt();
        int capacity = state.get("capacity").asInt();
        if (available < 0 || capacity < 0 || available > capacity) {
            throw new BookingProblem(HttpStatus.CONFLICT,
                "INVALID_INVENTORY", "Dữ liệu ghế không hợp lệ");
        }
        if (available < input.seats()) {
            throw new BookingProblem(HttpStatus.CONFLICT,
                "NO_SEATS", "Không đủ ghế");
        }
        int remaining = available - input.seats();

        // 5. Tạo node/cạnh và cập nhật ghế trong CÙNG transaction.
        Map<String, Object> params = new HashMap<>(ids);
        params.put("seats", input.seats());
        params.put("bookingId", bookingId);
        params.put("remainingAfter", remaining);

        Record saved = tx.run("""
            MATCH (a:CapAttendee {
              tenantId: $tenantId,
              attendeeId: $attendeeId
            })
            MATCH (e:CapEvent {
              tenantId: $tenantId,
              eventId: $eventId
            })
            SET e.availableSeats = $remainingAfter
            CREATE (b:CapBooking {
              tenantId: $tenantId,
              bookingId: $bookingId,
              requestKey: $requestKey,
              attendeeId: $attendeeId,
              eventId: $eventId,
              seats: $seats,
              remainingAfter: $remainingAfter,
              status: 'CONFIRMED',
              createdAt: datetime()
            })
            CREATE (a)-[:CAP_HAS_BOOKING]->(b)
            CREATE (b)-[:CAP_FOR_EVENT]->(e)
            RETURN b.bookingId AS bookingId,
                   b.status AS status,
                   b.seats AS seats,
                   b.remainingAfter AS remainingAfter
            """, params).single();

        return new BookingReceipt(
            saved.get("bookingId").asString(),
            saved.get("status").asString(),
            saved.get("seats").asInt(),
            saved.get("remainingAfter").asInt(),
            false
        );
    }

    private BookingReceipt lookupAfterCollision(
            String tenantId, String requestKey, BookingInput input) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(DATABASE))) {
            // Đọc qua WRITE routing trên cluster để tránh replica lag
            // ngay sau khi một transaction khác thắng unique constraint.
            // Callback này chỉ đọc, không tạo side effect.
            return session.executeWrite(tx -> {
                List<Record> rows = tx.run(
                    FIND_BY_REQUEST,
                    Map.of("tenantId", tenantId, "requestKey", requestKey)
                ).list();
                return rows.isEmpty() ? null :
                    asReceipt(rows.get(0), input, true);
            });
        }
    }

    private static BookingReceipt asReceipt(
            Record row, BookingInput input, boolean replayed) {
        boolean samePayload =
            row.get("attendeeId").asString().equals(input.attendeeId())
            && row.get("eventId").asString().equals(input.eventId())
            && row.get("seats").asInt() == input.seats();
        if (!samePayload) {
            throw new BookingProblem(HttpStatus.CONFLICT,
                "IDEMPOTENCY_KEY_REUSED",
                "Key đã gắn với một payload khác");
        }
        return new BookingReceipt(
            row.get("bookingId").asString(),
            row.get("status").asString(),
            row.get("seats").asInt(),
            row.get("remainingAfter").asInt(),
            replayed
        );
    }
}
~~~

**Giải thích quan trọng về tính đúng đắn:**

1. `SET e.lockVersion = ...` là một **ghi thật** trên node Event và được thực hiện ở query riêng, trước khi đọc `availableSeats`. Nó giữ write lock đến khi transaction kết thúc. Các booking vào cùng Event không đồng thời quyết định dựa trên cùng một số ghế cũ.
2. Việc đọc lại `requestKey` sau lock xử lý trường hợp request cùng key đã commit trong lúc request hiện tại chờ khóa **cùng Event**.
3. Hai request cùng key nhưng chỉ tới **hai Event khác nhau** không chia sẻ khóa Event. Unique constraint `(tenantId, requestKey)` vẫn ngăn hai booking commit với cùng key; collision được hòa giải bằng lookup sau khi transaction lỗi/rollback.
4. Mọi lỗi phát sinh trong callback trước commit (ví dụ Attendee không tồn tại hoặc `CREATE` vi phạm constraint) làm **rollback cả cập nhật `lockVersion` và số ghế**. `lockVersion` là công cụ tuần tự hóa trong ví dụ, không phải số phiên bản nghiệp vụ để báo cho client.
5. `executeWrite` có thể retry callback khi driver phân loại lỗi transient phù hợp. Vì vậy **không gửi email, HTTP request tới hệ thống khác hoặc publish message bên trong callback**.
6. `bookingId` được sinh ngoài callback để giữ ổn định trong một lần invocation; request key mới là định danh bền vững xuyên những lần gọi HTTP khác nhau.
7. Đoạn mã bắt **một mã legacy Neo4j constraint error cụ thể**. Các dòng driver/server có thêm mã GQLSTATUS hoặc thay đổi phân loại; ở hệ thống thật phải kiểm thử cách nhận diện collision theo version. **Không coi mọi ClientException là replay**.
8. Truy vấn chỉ kiểm payload bằng attendeeId, eventId và seats vì hợp đồng API hiện có đúng ba field. Khi thêm loại vé, giá, mã khuyến mại hoặc loại thanh toán, phải bổ sung so sánh payload/canonical request hash để không cho tái sử dụng key với ý nghĩa khác.
9. Nếu event được xóa, đổi capacity hoặc bị thay trạng thái ngoài service, phải thiết kế **quy tắc cập nhật đồng bộ trên cùng Event**. Một writer bỏ qua protocol khóa và bất biến có thể phá giả định của luồng đặt chỗ.

10. Trong trường hợp race, yêu cầu replay có thể tăng `lockVersion` khi giành khóa rồi đọc thấy Booking đã được tạo. Nó **không trừ thêm ghế**, nhưng vẫn là một lượt ghi kỹ thuật. Nếu traffic replay rất lớn, có thể thiết kế một request-marker riêng làm điểm tuần tự hóa và chứng minh bằng kiểm thử thay vì dùng Event cho mọi trường hợp.
11. Trên Neo4j cluster, một `executeRead` điều phối tới replica có thể trả dữ liệu chưa bắt kịp transaction mới commit nếu không sử dụng bookmark/causal consistency thích hợp. Vì vậy hàm hòa giải collision minh họa dùng `executeWrite` để thực hiện **câu đọc ở write-routing path**. Đó không phải side effect; nếu áp dụng thiết kế đọc replica, phải chứng minh tính nhất quán bằng bookmark hoặc cơ chế khác được hỗ trợ.

### 9.4. Khi có hai Event và một request key

Tình huống tranh chấp:

~~~text
Request A: tenant T, key K, event E1
Request B: tenant T, key K, event E2

Hai transaction có thể giữ lock trên E1 và E2 độc lập.
Constraint (tenantId, requestKey) chỉ cho phép một Booking(K).
Transaction thua collision rollback cả phần trừ ghế.
Service đọc Booking(K):
  - Payload giống => replay thành công
  - Payload khác => 409 IDEMPOTENCY_KEY_REUSED
~~~

Đó là lý do **chỉ khóa Event là chưa đủ cho tính duy nhất theo request key**; cần uniqueness constraint và logic hòa giải.

### 9.5. Tình huống thiếu ghế và rollback

Nếu Event còn một ghế nhưng request đòi hai ghế:

~~~text
Transaction:
  LOCK Event (SET lockVersion = lockVersion + 1)
  READ availableSeats = 1
  CHECK seatsRequested = 2 => NO_SEATS
  THROW BookingProblem
  ROLLBACK (kể cả lockVersion)
~~~

Không có Booking, không có relationship, và `availableSeats` vẫn là 1. Đây là hành vi cần được kiểm thử bằng query readback trên database.

## 10. Controller Spring Boot và mã trạng thái HTTP

~~~java
import java.security.Principal;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/bookings")
public final class BookingController {
    private final BookingService bookingService;
    private final TenantScope tenantScope;
    private final BookingAccess bookingAccess;

    public BookingController(
            BookingService bookingService, TenantScope tenantScope,
            BookingAccess bookingAccess) {
        this.bookingService = bookingService;
        this.tenantScope = tenantScope;
        this.bookingAccess = bookingAccess;
    }

    @PostMapping
    public ResponseEntity<BookingReceipt> create(
            Principal principal,
            @RequestHeader("Idempotency-Key") String requestKey,
            @Valid @RequestBody BookingInput input) {
        String tenantId = tenantScope.requireTenant(principal);
        bookingAccess.requireBookPermission(
            principal, tenantId, input.attendeeId());
        BookingReceipt result = bookingService.reserve(
            tenantId, requestKey, input);
        return ResponseEntity
            .status(result.replayed() ? HttpStatus.OK : HttpStatus.CREATED)
            .body(result);
    }
}
~~~

Hợp đồng response: **201 Created** lần ghi mới, **200 OK** cho replay thành công; hai response cùng bookingId. Có thể bổ sung header `Location` trỏ tới resource nếu đã cung cấp GET endpoint có kiểm quyền.

Controller gọi cả `TenantScope` và `BookingAccess`, không tin `tenantId` từ JSON/header do client kiểm soát. **Không được tự thêm một `TenantScope` implementation trả `"tenant-demo"` cho tất cả user trong sản phẩm thật**; khi demo local không xác thực, phải ghi rõ chỉ dùng trong môi trường cách ly và không công khai endpoint.

## 11. Chuẩn hóa exception thành API error

Trong Spring Boot, dùng handler để không lộ chi tiết driver:

~~~java
import org.neo4j.driver.exceptions.ServiceUnavailableException;
import org.neo4j.driver.exceptions.SessionExpiredException;
import org.neo4j.driver.exceptions.TransientException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

record ApiError(String code, String message) {}

@RestControllerAdvice
public final class ApiErrorHandler {
    @ExceptionHandler(BookingProblem.class)
    public ResponseEntity<ApiError> business(BookingProblem ex) {
        return ResponseEntity.status(ex.status())
            .body(new ApiError(ex.code(), ex.getMessage()));
    }

    @ExceptionHandler({
        ServiceUnavailableException.class,
        SessionExpiredException.class,
        TransientException.class
    })
    public ResponseEntity<ApiError> temporary(RuntimeException ex) {
        // Sau một lỗi mất kết nối, có thể chưa rõ COMMIT đã xảy ra.
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError("OUTCOME_UNKNOWN",
                "Hãy thử lại với cùng Idempotency-Key"));
    }
}
~~~

Đây là **mẫu xử lý một số exception**; cần bổ sung handler xác thực/quyền, validation (Bean Validation, JSON parse), constraint/schema errors, mã lỗi bất ngờ và correlation ID theo framework phiên bản thực tế. Không nên trả `ex.getMessage()` từ Neo4j exception trực tiếp cho client. Trong production, log nguyên nhân kỹ thuật ở nơi hạn chế truy cập với request ID, nhưng không đưa password/PII và query parameters vào log.

**Không gắn nhãn OUTCOME_UNKNOWN cho mọi lỗi transient theo nghĩa transaction chắc chắn đã commit.** Đó là mã phản hồi thận trọng: client **không biết** kết quả, nên phải hòa giải bằng request key. Service có thể biết rõ một lỗi trước commit đã rollback; khi đó mã chi tiết hơn là hợp lý nếu có bằng chứng.

### 11.1. Ma trận retry

| Loại lỗi | Retry tự động ở đâu? | Quy tắc |
| --- | --- | --- |
| Validation sai | Không. | Sửa payload. |
| Không tìm thấy Attendee/Event | Không. | Xác minh quyền và dữ liệu. |
| Không đủ ghế, Event đóng | Không retry tức thì. | Báo 409; client quyết định luồng mới nếu điều kiện thay đổi. |
| Collision idempotency key | Hòa giải bằng lookup. | Payload giống -> trả receipt; payload khác -> 409. |
| Deadlock/lock contention transient | Driver có thể retry `executeWrite`. | Giới hạn thời gian retry, đo contention; callback phải an toàn khi lặp. |
| Mất kết nối/leader change | Driver/ứng dụng retry có điều kiện. | Dùng **cùng request key**, không tạo yêu cầu nghiệp vụ mới. |
| Syntax/permission/schema error | Không retry mù. | Coi là lỗi triển khai/quyền, sửa gốc. |
| Mất response đúng lúc commit | Không kết luận rollback. | Tra cứu requestKey, hoặc lặp request cùng key sau khi kết nối lại. |

Những lỗi tạm thời có thể khiến driver hết ngân sách retry; API nên trả lỗi có thể nhận diện và bảo vệ database bằng rate limiting, giới hạn concurrency và backoff có jitter ở client. Không cho client retry vô hạn khi database quá tải.

## 12. Tra cứu trạng thái và hòa giải UNKNOWN_OUTCOME

Khi response `503 OUTCOME_UNKNOWN`, client có thể:

1. Giữ nguyên `Idempotency-Key` và payload đã gửi.
2. Chờ/backoff theo chính sách.
3. Gửi lại cùng request. Service đọc Booking tồn tại rồi trả receipt, hoặc tiếp tục ghi nếu transaction trước đó đã rollback.
4. Nếu hệ thống cung cấp endpoint tra cứu riêng, gọi endpoint đó để xác nhận không cần tạo một request mới.

Một truy vấn tra cứu kết quả:

~~~cypher
MATCH (b:CapBooking {
  tenantId: $tenantId,
  requestKey: $requestKey
})
RETURN b.bookingId AS bookingId,
       b.attendeeId AS attendeeId,
       b.eventId AS eventId,
       b.seats AS seats,
       b.remainingAfter AS remainingAfter,
       b.status AS status;
~~~

**Quyền:** `$tenantId` phải do server xác minh, và không cho user đoán request key để xem booking người khác. Trong đồ án mẫu, nên kiểm thêm actor có quyền với Attendee/Booking tương ứng; việc cùng tenant **chưa chắc** đủ nếu dữ liệu giữa user cũng cần cô lập.

### 12.1. Endpoint GET gợi ý

~~~http
GET /api/v1/bookings/by-request-key/req-demo-001 HTTP/1.1
Authorization: Bearer <valid-token>
~~~

Việc cho request key vào URL có thể khiến key xuất hiện trong log proxy hoặc lịch sử truy cập. Nếu coi key là token nhạy cảm, có thể chọn một endpoint `POST /api/v1/bookings/lookup` với body phù hợp hoặc chỉ dùng retry POST. Trong mọi trường hợp, **key không được thay thế authorization**.

### 12.2. Không nhầm ID của booking với khóa chống lặp

- `bookingId` do server tạo; là identity của bản ghi đã commit.
- `requestKey` do client tạo/giữ ổn định cho **một ý định đặt chỗ**, dùng được ngay cả trước khi biết `bookingId`.
- Mỗi lần người dùng thực sự muốn đặt thêm ghế, phải dùng request key **mới**; reuse cùng key với số ghế mới phải nhận lỗi 409.

### 12.3. Thời hạn lưu key

Nếu xóa Booking hoặc idempotency metadata quá sớm, một request cũ có thể được xử lý lại như mới. Chọn retention theo cửa sổ retry thực tế, quy định xóa dữ liệu và vòng đời Booking. Nếu cần xóa PII nhưng vẫn giữ bảo vệ key, có thể tách một marker tối thiểu với TTL/chính sách phù hợp và kiểm thử trường hợp xóa dữ liệu. **Không lưu request key mãi mãi mà không có chính sách riêng tư và dung lượng.**

## 13. Chạy cùng luồng nghiệp vụ bằng Java Driver thuần

Spring Boot không bắt buộc khi ứng dụng là một chương trình dòng lệnh hoặc worker. Neo4j Java Driver cũng hỗ trợ trực tiếp:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

public final class BookingCli {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");
        if (uri == null || username == null || password == null) {
            throw new IllegalStateException(
                "Thiếu thông tin kết nối từ môi trường");
        }

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();

            BookingService bookingService = new BookingService(driver);
            BookingReceipt result = bookingService.reserve(
                "tenant-demo",
                "cli-local-request-001",
                new BookingInput("A01", "E01", 1));

            System.out.println("Booking ID: " + result.bookingId());
        }
    }
}
~~~

Đoạn mã dùng `tenant-demo` trực tiếp **chỉ cho CLI thử nghiệm trong môi trường cô lập**; nếu worker thực chạy cho nhiều tổ chức, tenant và quyền phải lấy từ danh tính/tác vụ đã được xác minh. Không in password/URI chứa credential, không đặt secret trong source code và không dùng `verifyConnectivity()` mỗi lần xử lý một request HTTP.

**Vòng đời Driver:** tạo Driver/pool dùng chung cho vòng đời ứng dụng rồi đóng khi dừng; mỗi request/tác vụ dùng **Session riêng**, không chia sẻ một Session giữa nhiều thread. Nếu dùng cluster, chọn URI/routing/encryption đúng mô hình và chỉ định database bằng `SessionConfig.forDatabase(...)` thay vì dựa vào database mặc định không rõ ràng.

### 13.1. Lựa chọn sync hay reactive

Code trên dùng **synchronous/blocking Java Driver** phù hợp Spring MVC và ứng dụng nhỏ/trung bình. Nếu chọn Spring WebFlux/reactive driver thì phải thiết kế từ đầu theo mô hình reactive, ranh giới transaction và backpressure phù hợp; không gọi các phương thức blocking này trên event-loop.

Không nên trộn `CompletableFuture`, session đồng bộ và reactive transaction tùy tiện chỉ vì cần xử lý nhiều request. Trước tiên đảm bảo tính nguyên tử, loại lỗi và khả năng quan sát, sau đó mới thay đổi mô hình thực thi.

## 14. Phương án Spring Data Neo4j và Neo4jClient

Ứng dụng Spring Boot đã dùng starter SDN có thể chọn **Spring-managed transaction** thay vì driver-managed transaction. Khi đó:

- Entity theo mô hình `@Node`, `@Relationship`, `@RelationshipProperties` có thể tiện cho các truy vấn CRUD/aggregate thông thường.
- `Neo4jClient` thuận tiện khi cần Cypher tối ưu hóa theo màn hình hoặc cập nhật property/cạnh có kiểm soát.
- Service `@Transactional` chạy dưới **transaction manager Neo4j đúng cấu hình** có thể bao nhiều lời gọi repository/`Neo4jClient` trong cùng một transaction.
- Phải kiểm tra cách SDN lưu aggregate: save một entity đã tải thiếu relationship có thể có semantics không giống ý định “chỉ cập nhật một property”.

Mẫu service đọc/ghi đơn giản bằng `Neo4jClient`:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class EventAdminService {
    private final Neo4jClient client;

    public EventAdminService(Neo4jClient client) {
        this.client = client;
    }

    @Transactional
    public String renameEvent(String tenantId, String eventId,
                              String title) {
        // Authorization/validation phải chạy trước khi gọi method.
        return client.query("""
                MATCH (e:CapEvent {
                  tenantId: $tenantId,
                  eventId: $eventId
                })
                SET e.title = $title
                RETURN e.eventId AS id
                """)
            .bind(tenantId).to("tenantId")
            .bind(eventId).to("eventId")
            .bind(title).to("title")
            .fetchAs(String.class)
            .mappedBy((typeSystem, row) ->
                row.get("id").asString())
            .one()
            .orElseThrow(() -> new IllegalArgumentException(
                "Event không tồn tại"));
    }
}
~~~

Ví dụ minh họa API/transaction path của SDN, không phải thay thế toàn bộ service đặt chỗ. Với `@Transactional`, cần cấu hình đúng Neo4j transaction manager và kiểm thử rollback trong bản Spring Boot đang dùng. Nếu ứng dụng cũng có RDBMS, phải **chỉ rõ transaction manager** cho mỗi service; một `@Transactional` mặc định không tạo transaction phân tán xuyên Neo4j và RDBMS.

### 14.1. Hai cách quản lý transaction — chọn một cho mỗi use case

| Driver-managed | Spring-managed |
| --- | --- |
| `session.executeWrite(tx -> ...)` | `@Transactional` trên service với Neo4j transaction manager |
| Driver điều phối transaction, callback và retry phù hợp. | Spring mở/commit/rollback transaction quanh phương thức theo cấu hình. |
| Dễ dùng với Java thuần và logic Cypher tường minh. | Dễ phối hợp nhiều repository/Neo4jClient calls trong một service Spring. |
| Không tự nằm trong transaction do `@Transactional` ở service khác quản lý. | Không mặc định lấy `Session` riêng của Java Driver gia nhập transaction Spring. |
| Callback có thể chạy lại, nên không có external side effect. | Spring không tự biến mọi external API call thành atomic với Neo4j. |

**Không đặt `@Transactional` ngoài một `executeWrite` rồi mặc định hai transaction là một.** Nếu dùng SDN cho luồng đặt chỗ, phải chuyển đầy đủ các bước “khóa Event → đọc ghế → tạo Booking/cạnh → trừ ghế” sang **cùng Spring transaction** bằng repository/`Neo4jClient` được Spring quản lý và kiểm thử thực tế.

### 14.2. Vai trò của @Version

SDN có thể hỗ trợ optimistic locking của entity bằng cơ chế phiên bản (ví dụ `@Version`) trong những mô hình phù hợp. Tuy nhiên:

- `@Version` bảo vệ một số tình huống cập nhật **cùng entity** theo semantics framework, không tự thực thi tất cả bất biến xuyên nhiều node/relationship.
- Muốn dùng optimistic concurrency cho số ghế cần kiểm soát retry xung đột, không ghi đè giá trị cũ và xử lý thắng/thua khi hai request cùng thay đổi Event.
- Khi dùng custom Cypher cập nhật thẳng property, không được tự giả định annotation trên entity sẽ được framework áp dụng vào câu query đó.

Đồ án chọn **ghi trước để giữ write lock trên Event** vì dễ minh họa tính tuần tự và ranh giới transaction; đây không phải cách duy nhất. Có thể phát triển biến thể dùng optimistic concurrency hoặc kiểm tra điều kiện cập nhật bằng Cypher và so sánh kết quả ghi, nhưng phải chứng minh bằng kiểm thử đồng thời.

## 15. Câu truy vấn kiểm tra bất biến sau mỗi bài test

### 15.1. Đối chiếu số ghế và tổng Booking đã xác nhận

~~~cypher
MATCH (e:CapEvent {
  tenantId: $tenantId,
  eventId: $eventId
})
OPTIONAL MATCH
  (b:CapBooking {tenantId: $tenantId})
  -[:CAP_FOR_EVENT]->(e)
WITH e,
     sum(
       CASE
         WHEN b.status = 'CONFIRMED' THEN b.seats
         ELSE 0
       END
     ) AS bookedSeats
RETURN e.capacity AS capacity,
       e.availableSeats AS availableSeats,
       bookedSeats,
       e.availableSeats + bookedSeats = e.capacity
         AS capacityInvariant,
       e.availableSeats >= 0 AS nonNegative;
~~~

Với fixture ban đầu có ba ghế:

| Trạng thái | availableSeats | bookedSeats | capacityInvariant |
| --- | ---: | ---: | --- |
| Chưa đặt | 3 | 0 | true |
| A01 đặt 2 ghế | 1 | 2 | true |
| Replay cùng key | 1 | 2 | true |
| A02 đặt thêm 1 ghế | 0 | 3 | true |
| Yêu cầu đặt 1 ghế tiếp theo bị từ chối | 0 | 3 | true |

Query đối soát giả định chưa có luồng hoàn/hủy và `capacity` không bị admin đổi tùy tiện. Khi thêm hủy vé, cần cập nhật quy tắc tính `bookedSeats` và lịch sử giao dịch cho phù hợp. Không dùng count Booking thay cho tổng ghế nếu mỗi Booking có thể chứa nhiều ghế.

### 15.2. Kiểm tra mỗi Booking có đúng một Attendee và Event

~~~cypher
MATCH (b:CapBooking {tenantId: $tenantId})
OPTIONAL MATCH
  (a:CapAttendee)-[:CAP_HAS_BOOKING]->(b)
WITH b, count(a) AS attendeeLinks,
        collect(DISTINCT a.tenantId) AS attendeeTenants
OPTIONAL MATCH
  (b)-[:CAP_FOR_EVENT]->(e:CapEvent)
WITH b, attendeeLinks, attendeeTenants,
     count(e) AS eventLinks,
     collect(DISTINCT e.tenantId) AS eventTenants
WHERE attendeeLinks <> 1
   OR eventLinks <> 1
   OR b.tenantId NOT IN attendeeTenants
   OR b.tenantId NOT IN eventTenants
RETURN b.bookingId AS bookingId,
       attendeeLinks, eventLinks,
       attendeeTenants, eventTenants
LIMIT 100;
~~~

Kết quả mong đợi **0 hàng**. Đây là một kiểm tra cấu trúc. Để bảo vệ tính đúng tuyệt đối, còn phải so `b.attendeeId` với `a.attendeeId` và `b.eventId` với `e.eventId`, cũng như bảo đảm relationship không trùng. Bản thân node/relationship uniqueness của Booking không tự bắt buộc mỗi Booking có đúng hai cạnh.

### 15.3. Kiểm tra booking trùng request key

~~~cypher
MATCH (b:CapBooking {tenantId: $tenantId})
WITH b.requestKey AS requestKey, count(b) AS total
WHERE total > 1
RETURN requestKey, total
ORDER BY total DESC;
~~~

Nếu constraint `cap_booking_request_key` còn hiệu lực và dữ liệu luôn có khóa hợp lệ, kỳ vọng 0 hàng. Nếu một số Booking có property `requestKey` null hoặc thiếu, uniqueness thông thường chưa chắc bảo vệ trường hợp đó; validation và test dữ liệu thiếu vẫn cần thiết.

## 16. Kiểm thử tích hợp với Neo4j thật

**Không thể xác minh transaction/locking chính xác chỉ bằng cách mock `Driver`.** Unit test hữu ích cho validation và mapping error, nhưng race condition, unique constraint, rollback và driver retry phải chạy trên **Neo4j thật ở môi trường cô lập**.

Có thể dùng Testcontainers để tạo một Neo4j test instance. Cấu trúc minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class BookingIntegrationTest {
    @Container
    static final Neo4jContainer<?> neo4j =
        new Neo4jContainer<>("neo4j:5.26")
            .withAdminPassword("test-only-password");

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username",
            () -> "neo4j");
        registry.add("spring.neo4j.authentication.password",
            () -> "test-only-password");
    }

    @Test
    void smokePlaceholder() {
        // Bổ sung migration/fixture và assertion thật ở các test bên dưới.
        // Không đánh dấu PASS nếu chỉ chạy được container.
    }
}
~~~

Tag image và constructor Testcontainers ở trên là ví dụ; chọn image Neo4j và dependency **phù hợp với sản phẩm thật**. Cần Docker/container runtime hoặc môi trường CI được phép chạy container. Nếu không dùng Testcontainers, có thể trỏ các test tới một database integration-test riêng và bảo đảm cleanup không tác động dữ liệu khác.

Trong test, tạo schema trước khi nạp fixture; chờ constraint/index sẵn sàng khi cần. Với test đồng thời, phải đảm bảo mỗi test có fixture độc lập hoặc cleanup theo thứ tự **không xóa dữ liệu của test đang chạy**.

`@SpringBootTest` sẽ dựng application context; scaffold này cần các bean `TenantScope`, `BookingAccess`, Security config và migration/fixture tương ứng trước khi chạy như một integration test thật. Không coi method `smokePlaceholder()` không có assertion là bằng chứng nghiệp vụ đã PASS.

### 16.1. Test idempotency bằng service thật

Pseudocode JUnit (giả định `service` và fixture đã khởi tạo):

~~~java
@Test
void sameRequestKeyDoesNotConsumeSeatsTwice() {
    BookingInput input = new BookingInput("A01", "E01", 2);

    BookingReceipt first = service.reserve(
        "tenant-demo", "same-request-key", input);
    BookingReceipt second = service.reserve(
        "tenant-demo", "same-request-key", input);

    assertEquals(first.bookingId(), second.bookingId());
    assertFalse(first.replayed());
    assertTrue(second.replayed());
    assertEquals(1, readAvailableSeats("tenant-demo", "E01"));
    assertEquals(1, countBookingsByRequestKey(
        "tenant-demo", "same-request-key"));
}
~~~

`readAvailableSeats(...)` và `countBookingsByRequestKey(...)` là helper test cần tự triển khai bằng Cypher. Không dùng mock để giả kết quả những truy vấn này. Test phải bắt đầu với Event còn 3 ghế và chưa có Booking cho key đó.

### 16.2. Test rollback bằng lỗi được chèn sau cập nhật

Test riêng ở database test:

~~~java
@Test
void transactionRollsBackWhenCallbackThrows() {
    assertThrows(IllegalStateException.class, () -> {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWrite(tx -> {
                tx.run("""
                    MATCH (e:CapEvent {
                      tenantId: 'tenant-demo',
                      eventId: 'E01'
                    })
                    SET e.availableSeats = e.availableSeats - 1
                    RETURN e.eventId
                    """).consume();

                // Lỗi có chủ ý, transaction chưa commit.
                throw new IllegalStateException("INJECTED_FAILURE");
            });
        }
    });
    assertEquals(3, readAvailableSeats("tenant-demo", "E01"));
}
~~~

Đoạn trên chứng minh thay đổi cùng transaction rollback khi callback ném lỗi. **Nó không phải endpoint production** và không nên bật fault injection trong dịch vụ thật. Với service hoàn chỉnh, có thể thêm một seam dành riêng cho test để chèn lỗi giữa hai thao tác và xác minh **không còn Booking hay relationship nửa vời**.

### 16.3. Test concurrent booking

Tạo Event còn ba ghế, sau đó chạy **tám request khác key**, mỗi request đặt một ghế. Kỳ vọng ba transaction thành công; năm request còn lại bị từ chối vì hết ghế, không có `availableSeats < 0`.

Một khung test:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(8);
CountDownLatch start = new CountDownLatch(1);
List<Future<BookingReceipt>> futures = new ArrayList<>();
try {
    for (int i = 0; i < 8; i++) {
        final int n = i;
        futures.add(pool.submit(() -> {
            start.await();
            return service.reserve(
                "tenant-demo",
                "parallel-" + n,
                new BookingInput("A01", "E01", 1));
        }));
    }
    start.countDown();

    int success = 0;
    int noSeats = 0;
    for (Future<BookingReceipt> future : futures) {
        try {
            if ("CONFIRMED".equals(future.get().status())) success++;
        } catch (ExecutionException ex) {
            if (ex.getCause() instanceof BookingProblem problem
                    && "NO_SEATS".equals(problem.code())) {
                noSeats++;
            } else {
                throw ex;
            }
        }
    }
    assertEquals(3, success);
    assertEquals(5, noSeats);
    assertEquals(0, readAvailableSeats("tenant-demo", "E01"));
} finally {
    pool.shutdownNow();
}
~~~

Các import JUnit/Java concurrency được lược bớt để tập trung vào kịch bản. Nếu hệ thống có nhiều concurrent writers hoặc cấu hình retry quá ngắn, test có thể gặp timeout/lock contention. Khi đó cần phân tích **loại lỗi** và ngân sách retry, không tự thay expected thành “năm lỗi bất kỳ”. Bất biến quan trọng hơn cả là **không quá số ghế và không có bản ghi nửa vời**.

### 16.4. Test unknown commit outcome

Khó tái hiện chính xác mất kết nối **ngay sau commit nhưng trước response** bằng unit test. Trong integration/chaos test, có thể dùng proxy kiểm soát mạng như Toxiproxy hoặc một kịch bản fault injection có hỗ trợ để ngắt phản hồi tại những thời điểm khác nhau.

Thứ tự cần kiểm tra:

1. Gửi request K với payload P.
2. Cắt một kết nối ở cửa sổ có thể gây **outcome unknown**; không biết nó đã commit hay chưa.
3. Khôi phục kết nối và gửi lại **cùng K và P**.
4. Đọc graph và xác nhận **tối đa một Booking(K)**, ghế chỉ bị trừ đúng một lần nếu đặt chỗ đã thành công.
5. Gửi K với payload Q khác và xác nhận 409, không ghi thêm.

Không cố tình ngắt mạng Neo4j production để thực hiện bài test. Trường hợp outcome không thể xác định ngay có thể trả `OUTCOME_UNKNOWN` và yêu cầu client kiểm tra/trả lại cùng key theo chính sách.

## 17. Ma trận kiểm thử chấp nhận đồ án

| ID | Tình huống | Kết quả bắt buộc |
| --- | --- | --- |
| C01 | Event còn 3 ghế, đặt 2 ghế. | HTTP 201, một Booking CONFIRMED, available=1, hai cạnh đúng chiều. |
| C02 | Gửi lại cùng key/payload C01. | HTTP 200, cùng bookingId, không trừ ghế lần hai. |
| C03 | Cùng key, số ghế khác. | HTTP 409 IDEMPOTENCY_KEY_REUSED, dữ liệu không đổi. |
| C04 | Cùng key, Event khác. | 409; không có hai Booking trùng key. |
| C05 | Event còn 1 ghế, request đòi 2. | 409 NO_SEATS, ghế không đổi. |
| C06 | Event status CLOSED. | 409, không tạo Booking. |
| C07 | Không có Event trong tenant. | 404, không tạo Booking. |
| C08 | Không có Attendee trong tenant. | 404 và rollback update lockVersion. |
| C09 | seats = 0, -1, 6 hoặc JSON sai. | 400 trước khi ghi Neo4j. |
| C10 | Thiếu Idempotency-Key. | 400 và không có side effect. |
| C11 | Không có principal hợp lệ. | 401, không chạy mutation. |
| C12 | Principal không có quyền với attendee. | 403, không chạy mutation. |
| C13 | Event của tenant khác có cùng eventId. | Không đọc/ghi tenant khác. |
| C14 | 8 request tranh 3 ghế. | Tối đa 3 xác nhận, available không âm, tổng khớp capacity. |
| C15 | Hai request cùng key, cùng Event. | Có một Booking; request còn lại là replay hoặc được hòa giải đúng. |
| C16 | Hai request cùng key, khác Event. | Constraint bảo đảm một key; payload thua bị từ chối và rollback. |
| C17 | Exception sau thay đổi ghế trước commit. | ROLLBACK, không còn Booking/cạnh dở dang. |
| C18 | Driver gặp transient error có thể retry. | Không gửi external side effect trong callback; kết quả cuối đúng. |
| C19 | Mất response lúc commit. | Gửi lại cùng key hòa giải, không trừ ghế hai lần. |
| C20 | Thiếu constraint request key. | Migration gate không cho mở tính năng vì mất bảo vệ idempotency. |
| C21 | Neo4j thiếu index/constraint sẵn sàng. | Phát hiện trong startup/rollout, không lặng lẽ chạy sai. |
| C22 | Transaction commit rồi server restart. | Dữ liệu đã commit còn nguyên sau recovery. |
| C23 | User đoán bookingId/requestKey người khác. | Read API kiểm quyền đối tượng, không lộ dữ liệu. |
| C24 | Lỗi Cypher/schema nội bộ. | HTTP 500 ổn định; không lộ query/PII trong response. |
| C25 | Collector/metrics mất dữ liệu. | Cảnh báo telemetry missing, không coi lỗi bằng 0. |
| C26 | Capacity bị sửa sai bởi admin/job khác. | Phát hiện invariant và ngăn tiếp tục booking sai. |

**Mục tiêu test:** chứng minh bất biến sau mỗi trường hợp, không chỉ kiểm HTTP status. Ví dụ một request 409 nhưng đã trừ ghế trước khi lỗi là **FAIL**.

## 18. Giới hạn của giao dịch Neo4j khi có hệ thống bên ngoài

Một Booking CONFIRMED có thể kích hoạt email, push notification hoặc sự kiện broker. Nhưng transaction Neo4j **không tự commit nguyên tử** cùng dịch vụ email hoặc message broker:

~~~text
Neo4j COMMIT thành công
           |
           +--> Publish broker thất bại
           |
           '-- Email gửi thành công nhưng HTTP response mất
~~~

Nếu gửi email **trong** callback `executeWrite`, driver có thể retry callback khiến email được gửi nhiều lần dù chỉ có một Booking commit. Vì vậy:

- Không gọi external service trong callback transaction.
- Có thể sử dụng **outbox**: tạo một `CapOutboxEvent` trong cùng Neo4j transaction với Booking, rồi worker xuất bản sau commit.
- Worker dùng `eventId` duy nhất, cơ chế claim/ack/idempotency và retry có kiểm soát.
- Subscriber phải chấp nhận event **at-least-once** và deduplicate bằng event ID nếu hạ tầng không hỗ trợ exactly-once end-to-end.

### 18.1. Outbox mẫu

Một phần mở rộng của Cypher tạo Booking:

~~~cypher
CREATE (evt:CapOutboxEvent {
  tenantId: $tenantId,
  eventId: $outboxEventId,
  eventType: 'BOOKING_CONFIRMED',
  bookingId: $bookingId,
  status: 'PENDING',
  createdAt: datetime()
})
~~~

Đoạn này chỉ được chèn **vào cùng transaction đã tạo Booking** nếu tính năng outbox được triển khai. Cần thêm uniqueness constraint cho `(tenantId, eventId)`, chính sách nhận/gửi lại, claim event đồng thời và retention sau khi phát thành công. Không dùng `CREATE CapOutboxEvent` từ một request HTTP riêng sau khi Booking đã commit rồi coi là atomic.

**Lưu ý privacy:** event không nên chứa toàn bộ thông tin attendee. Dùng bookingId/eventId để service có quyền đọc dữ liệu cần thiết. Không cho worker log request body/credential thô.

## 19. Theo dõi lỗi và hiệu năng thực tế

Một ứng dụng có transaction đúng vẫn có thể không đáp ứng SLO khi hàng nghìn request cùng tranh một Event nóng. Hãy theo dõi **cả kết quả nghiệp vụ lẫn nguồn lực**:

| Metric | Ý nghĩa |
| --- | --- |
| `booking_requests_total` theo outcome/code | Tỷ lệ thành công, NO_SEATS, invalid, unknown, 5xx. |
| `booking_replayed_total` | Mức request lặp và hiệu quả idempotency. |
| `booking_transaction_duration` p50/p95/p99 | Tải và thời gian chờ lock/commit. |
| Lỗi transient/timeout/leader change | Sự cố Neo4j hay routing/driver. |
| Số booking mỗi Event theo thời gian | Phát hiện hot Event/supernode và contention. |
| Số ghế còn lại và invariant | Bảo đảm không âm, tổng booked + available khớp capacity. |
| Neo4j active transactions, lock wait | Nút thắt concurrency theo khả năng metric của phiên bản. |
| CPU, page cache, disk I/O, transaction log | Phân biệt lỗi tải với lỗi code/Cypher. |
| Connection pool và retry count | Phát hiện queue dài hoặc pool thiếu capacity. |
| Backup age và restore drill | Bảo đảm có phương án phục hồi nếu schema/upgrade lỗi. |

Các tên metric ở bảng là **tên minh họa do ứng dụng có thể tự đặt**, không phải tên Prometheus/Neo4j chắc chắn có sẵn. Gắn tag theo mã lỗi và tên operation, nhưng tránh cardinality cao như raw userId, email, bookingId hoặc requestKey trong metric labels.

### 19.1. Correlation ID

Mỗi HTTP request có thể mang một trace/correlation ID do gateway tin cậy cấp hoặc server xác minh. Các log nên cho biết:

~~~text
timestamp | requestId | operation=book | tenantRef=<redacted>
result=CONFIRMED | durationMs | replayed=false
~~~

Không ghi email, thông tin người dùng nhạy cảm, query parameter thô hoặc token. Nếu cần điều tra booking cụ thể, lưu tham chiếu vào kho audit được bảo vệ thay vì đưa toàn bộ danh tính lên dashboard chung.

### 19.2. Khó khăn với Event rất nóng

Protocol khóa trên cùng Event **chủ ý tuần tự hóa** các cập nhật `availableSeats`. Nó đảm bảo invariant nhưng có thể khiến throughput giảm nếu hàng nghìn request/giây cùng tranh ghế một sự kiện.

Có thể cân nhắc:

- Xếp hàng request theo Event ở tầng ứng dụng, có giới hạn và fairness phù hợp.
- Dùng cơ chế đặt vé theo slot/seat cụ thể với unique constraint riêng, hoặc phân vùng tồn kho khi yêu cầu nghiệp vụ cho phép.
- Giới hạn tốc độ API, concurrency và timeout để tránh quá tải.
- Thiết kế booking bất đồng bộ với trạng thái PENDING và cơ chế trả kết quả, **không giả báo CONFIRMED trước commit**.
- Giảm transaction work và index writes không cần thiết.

Những phương án này **đổi bài toán giao dịch**, phải kiểm lại invariant và fairness. Không dùng một cache của ghế còn lại như nguồn quyết định cuối cùng nếu nó không đồng bộ atomically với Neo4j.

## 20. Tối ưu Cypher mà không đánh đổi tính đúng

### 20.1. Dùng index từ khóa nghiệp vụ

Một thao tác đặt chỗ bắt đầu bằng:

~~~cypher
EXPLAIN
MATCH (e:CapEvent {
  tenantId: $tenantId,
  eventId: $eventId
})
RETURN e.availableSeats AS availableSeats;
~~~

Với uniqueness constraint `cap_event_key`, Neo4j có index hỗ trợ tra cứu cặp khóa. Tuy nhiên, trên fixture rất nhỏ planner có thể chọn kế hoạch khác vì rẻ hơn. **Không đánh giá hiệu năng từ tên index có tồn tại**; dùng `EXPLAIN`/`PROFILE` với dữ liệu đại diện và xem `Rows`, `DB Hits` cùng p95.

### 20.2. Không dùng PROFILE tùy tiện với mutation

`PROFILE` thực thi query. Do đó:

~~~cypher
PROFILE
MATCH (e:CapEvent {tenantId: $tenantId, eventId: $eventId})
RETURN e.availableSeats;
~~~

là một phép đọc để khảo sát plan; còn `PROFILE` với `SET e.availableSeats = ...` sẽ **ghi dữ liệu** nếu chạy. Không thử mutation trên production chỉ vì muốn thấy DB Hits.

### 20.3. Đừng tách transaction để giảm latency

Sai về tính nguyên tử:

~~~text
session.run("SET e.availableSeats = ...");  // autocommit
session.run("CREATE Booking ...");           // autocommit khác
~~~

Nếu thao tác thứ hai thất bại, số ghế đã giảm nhưng không có Booking. Đừng đổi tính đúng để lấy vài mili giây. Muốn giảm latency, đo:

- Số query round-trip trong transaction.
- Mức tranh chấp Event, thời gian chờ lock và thời gian commit.
- Chỉ mục tra cứu Event, Attendee và Booking theo key.
- Page cache, disk I/O và transaction log flush.
- Dữ liệu thừa/relationship không cần thiết trong cùng transaction.

Sau khi tối ưu, chạy lại toàn bộ test concurrency/idempotency. Một cải thiện p50 không có giá trị nếu p99 tệ hơn nghiêm trọng hoặc có thể bán quá ghế.

## 21. Bảo mật và ranh giới multi-tenant

Mọi đường truy cập đều phải thống nhất các quy tắc:

1. **Principal:** xác thực user qua Spring Security và không tin claim chưa được xác minh.
2. **Tenant:** lấy từ identity/authorization; nếu user được phép nhiều tenant thì phải kiểm quyền với tenant cụ thể do user chọn.
3. **Attendee:** kiểm người dùng hiện tại có quyền đặt thay attendee này hay không, kể cả khi cùng tenant.
4. **Event:** query bắt đầu bằng cả `tenantId + eventId`, không dùng mã event đơn lẻ khi mã có thể trùng giữa tenant.
5. **Booking:** tra bằng `tenantId + requestKey/bookingId` và kiểm quyền đối tượng trước khi trả.
6. **Schema:** uniqueness theo tenant; không cho client tự đặt `tenantId` hay `remainingAfter`.
7. **Secrets:** credential Neo4j, JWT signing key và TLS certificate do hệ thống bảo mật quản lý.
8. **Network:** chỉ ứng dụng và các tác vụ được phê duyệt kết nối trực tiếp Neo4j; không mở Bolt công khai không cần thiết.
9. **Logs:** không ghi token, password, request key thô hoặc PII trong tracing.
10. **Least privilege:** tài khoản ứng dụng không cần quyền quản trị role, database, backup hoặc thay schema.

**Phân quyền ở ứng dụng không thay thế an toàn ở database nếu tồn tại đường kết nối trực tiếp khác.** Cân nhắc fine-grained access control khi edition/phiên bản hỗ trợ, hoặc dùng database/tài khoản và network boundary tách biệt theo yêu cầu cách ly.

### 21.1. Kiểm thử không lộ tenant khác

Tạo một event cùng `eventId = E01` ở tenant khác trong fixture:

~~~cypher
MERGE (e:CapEvent {
  tenantId: 'tenant-other',
  eventId: 'E01'
})
ON CREATE SET
  e.title = 'Sự kiện tenant khác',
  e.capacity = 1,
  e.availableSeats = 1,
  e.status = 'OPEN',
  e.lockVersion = 0;
~~~

Thực hiện request của `tenant-demo` tới `E01`; chỉ Event thuộc `tenant-demo` bị cập nhật. Một request do người của `tenant-other` thực hiện cũng không được đọc Booking/Attendee của `tenant-demo`.

Không dùng một query tổng quát `MATCH (e:CapEvent {eventId:$id})` trong service mutation vì nó có thể gặp nhiều node trùng mã trên các tenant.

## 22. Triển khai an toàn và kế hoạch khôi phục

Một sản phẩm chưa sẵn sàng production chỉ vì test JUnit PASS. Trước khi mở API:

| Bước | Nội dung | Gate |
| --- | --- | --- |
| P1 | Kiểm version Neo4j, Spring Boot, Driver, plugin, edition. | Tương thích đã xác minh. |
| P2 | Backup và restore drill trên dữ liệu đại diện. | Có đường phục hồi đạt RPO/RTO. |
| P3 | Áp dụng schema migration khi có quyền. | Bốn constraint tồn tại và sẵn sàng. |
| P4 | Kiểm security, TLS, network, secret và quyền attendee. | Không có đường truy cập trái phép. |
| P5 | Seed/test dữ liệu trong môi trường staging. | Invariant đủ, không có request key trùng. |
| P6 | Thử load test concurrent và retry. | Không oversell, p95/p99 trong SLO. |
| P7 | Bật canary và observability. | Có metric lỗi, tracing và rollback ứng dụng. |
| P8 | Mở traffic theo từng nhóm. | Không tăng lỗi constraint/UNKNOWN_OUTCOME bất thường. |
| P9 | Theo dõi sau triển khai và backup thường kỳ. | Có owner/on-call và lịch xử lý sự cố. |

### 22.1. Rollback ứng dụng không có nghĩa rollback dữ liệu

Nếu deploy một phiên bản mới rồi phát sinh Booking, việc chuyển lại image ứng dụng cũ **không xóa được Booking** và cũng không nên làm vậy. Một data migration/index change có thể không tương thích với code cũ. Trước deployment, phải kiểm:

- Có thể chạy phiên bản ứng dụng trước với schema mới không?
- Schema migration có tính mở rộng tương thích ngược (*expand/migrate/contract*) không?
- Nếu rollback cần restore backup, những booking phát sinh sau điểm cắt sẽ được xử lý thế nào?
- Những event outbox đã publish cần đối soát ra sao?

Không tự phục hồi backup trước triển khai và làm mất những giao dịch đã commit mà không có quyết định nghiệp vụ và kế hoạch replay.

### 22.2. Runbook sự cố thiếu ghế hoặc dữ liệu lệch

Nếu phát hiện `availableSeats < 0` hoặc `bookedSeats + availableSeats != capacity`:

1. Hạn chế mutation liên quan Event bị ảnh hưởng theo quy trình đã duyệt.
2. Ghi lại Event, thời điểm, transaction/request IDs đã được bảo vệ và backup gần nhất.
3. Kiểm quyền, các đường ghi khác, rollback/commit outcomes và uniqueness constraints.
4. Đối soát danh sách Booking CONFIRMED với tồn kho, không chỉ sửa `availableSeats` bằng cảm tính.
5. Chọn biện pháp sửa theo nguồn dữ liệu đúng và phê duyệt của nghiệp vụ.
6. Chạy regression test concurrency/idempotency và giám sát sau khi mở lại.

Không xóa relationship/Booking để “đưa count về đúng” khi chưa xác minh chúng đại diện cho giao dịch đã được xác nhận với người dùng.

## 23. Hồ sơ bàn giao đồ án

Một đồ án được đánh giá theo **khả năng chứng minh**, không chỉ số dòng Java. Bộ bàn giao khuyến nghị:

| Artifact | Nội dung tối thiểu |
| --- | --- |
| Tài liệu kiến trúc | Sơ đồ node/relationship, ranh giới tenant, lý do dùng Booking node. |
| Schema migration | Bốn constraint, kiểm trạng thái và hướng dẫn rollback schema. |
| API contract | Request/response, idempotency key, HTTP statuses và error codes. |
| Java implementation | Controller, domain service, transaction, lookup/reconciliation, DTO, auth contracts. |
| Configuration | Biến môi trường cho Neo4j/TLS, config Security, profile test/prod. |
| Tests | Validation, atomic rollback, concurrent booking, retry, unknown outcome, tenant isolation. |
| Evidence | Kết quả chạy test, dữ liệu/query bất biến, plan, p95/p99, ảnh chụp metric có nguồn rõ. |
| Operations | Backup/restore, deploy gate, cảnh báo, runbook lỗi Neo4j và lỗi tồn kho. |
| Known limits | Không có thanh toán, không có hủy chỗ, hot Event throughput và giới hạn version. |

Phần bài học này không tự tạo các file kể trên; người học xây chúng trong repository đồ án riêng theo hướng dẫn và chính sách nhóm.

## 24. Thang đánh giá đồ án

| Nhóm tiêu chí | Trọng số minh họa | Yêu cầu đạt |
| --- | ---: | --- |
| Graph modeling và constraint | 15% | Node/cạnh đúng chiều, khóa không trùng và phân tách tenant. |
| Cypher và transaction | 25% | Ghế + Booking + relationship atomic; không oversell khi đồng thời. |
| Idempotency và lỗi | 20% | Replay đúng, mismatch 409, unknown outcome có đường hòa giải. |
| Spring Boot/Java design | 15% | Phân lớp rõ, tham số hóa, Driver/session lifecycle đúng. |
| Kiểm thử và bằng chứng | 15% | Test database thật, concurrency/rollback/security và báo cáo invariant. |
| Vận hành và bảo mật | 10% | Secrets/TLS/auth, log/metric, deploy gate và backup/restore. |

Đây là rubric **gợi ý**, không phải quy định điểm số mặc định của khóa học.

Một số lỗi là **điều kiện không đạt bắt buộc** dù tổng điểm khác cao: có thể bán quá ghế, transaction commit một phần, lộ dữ liệu tenant khác, bỏ qua authentication/authorization hoặc retry tạo Booking trùng.

## 25. Bài tập mở rộng

**Bài 1 — Bổ sung GET an toàn.** Xây endpoint đọc Booking theo `bookingId`, bắt buộc tenant và quyền với Attendee, chỉ trả field cần thiết. Kiểm tra không tiết lộ Booking của user khác cùng tenant.

**Bài 2 — Hủy booking.** Thiết kế `POST /bookings/{id}/cancel` với idempotency key riêng. Cần khóa Event và Booking theo thứ tự ổn định, chỉ hoàn ghế **một lần** khi chuyển `CONFIRMED → CANCELLED`. Viết test hai request hủy đồng thời.

**Bài 3 — Reservation TTL.** Thay CONFIRMED tức thời bằng trạng thái `HELD` có hạn giữ ghế. Thiết kế job hết hạn, race với thanh toán, timezone và idempotency sao cho không giữ ghế mãi hoặc hoàn ghế hai lần.

**Bài 4 — Outbox.** Thêm `CapOutboxEvent` cùng transaction, worker phát thông điệp `BOOKING_CONFIRMED` và deduplicate ở subscriber. Tạo lỗi “broker mất kết nối” sau khi booking commit; chứng minh event vẫn được gửi lại mà không đặt thêm ghế.

**Bài 5 — Optimistic concurrency.** So sánh phiên bản dùng write lock hiện tại với phiên bản dùng version/check-and-set. Đo throughput/lock wait trong trường hợp Event nóng; giữ cùng ma trận bất biến.

**Bài 6 — SDN transaction.** Viết lại service bằng `Neo4jClient` và `@Transactional`; phân biệt transaction manager với Driver `executeWrite`, và chứng minh rollback khi tạo relationship lỗi.

**Bài 7 — Chịu lỗi commit không xác định.** Dùng network proxy trong test để tái hiện ngắt kết nối ở nhiều giai đoạn. Báo cáo trường hợp chắc chắn rollback, chắc chắn commit, và chưa biết outcome. Kiểm tra retry cùng key không làm tăng tổng ghế được đặt.

**Bài 8 — Multi-tenant khó hơn.** Một người dùng có quyền với hai tenant nhưng không có quyền với mọi Attendee. Thiết kế authorization ở API lẫn Cypher để ngăn đặt hộ người khác, đồng thời ngăn rò rỉ số lượng booking nhạy cảm.

**Bài 9 — Hot Event và giới hạn tải.** Mô phỏng 100 request cùng tranh 10 ghế. Đo p50/p95/p99, lỗi transient và lock wait. Đề xuất cách queue, rate limit hoặc tối ưu transaction mà không đánh đổi invariant.

**Bài 10 — Dữ liệu lịch sử.** Thêm trạng thái REFUNDED và cập nhật logic đối soát `capacity = available + ghế đang giữ/đã xác nhận`. Chứng minh báo cáo cũ không còn đúng nếu chỉ đếm tất cả Booking bất kể trạng thái.

**Bài 11 — Upgrade và khôi phục.** Sao lưu database test, nâng cấp sang phiên bản Neo4j hỗ trợ, restore sang môi trường cô lập và kiểm graph/constraint/transaction trước khi cho API xử lý ghi.

**Bài 12 — Dấu vết kiểm toán.** Ghi actorRef, requestId, action và outcome trong nơi lưu phù hợp mà không để lộ PII hoặc secret. Phân biệt audit thành công đã commit với attempt bị từ chối và timeout chưa rõ outcome.

## 26. Checklist kết thúc đồ án

1. **Mô hình:** Attendee → Booking → Event đúng chiều, có tenant và khóa nghiệp vụ.
2. **Schema:** bốn constraint tạo được, sẵn sàng và không bị xóa tùy tiện khi tối ưu index.
3. **An ninh:** xác thực principal, xác minh tenant và quyền đặt chỗ cho Attendee; không tin header client.
4. **Transaction:** tất cả cập nhật ghế, node Booking và hai relationship trong cùng một transaction.
5. **Concurrency:** đọc ghế sau khi giữ write lock Event; kiểm thử nhiều writer và dữ liệu lệch.
6. **Idempotency:** request key duy nhất trong tenant, replay cùng payload trả kết quả cũ, payload khác bị từ chối.
7. **Unknown outcome:** mất response commit không bị xem là rollback; client dùng lại key/lookup có quyền.
8. **Retry:** hiểu `executeWrite` có thể chạy callback nhiều lần; không gọi external side effect trong callback.
9. **Error contract:** lỗi domain 400/404/409, lỗi kết nối 503, lỗi bất ngờ 500, không lộ stack trace/Cypher.
10. **Đúng framework:** Java Driver managed transaction hoặc Spring-managed transaction, không mặc định hai cơ chế tự hợp nhất.
11. **Test thật:** integration test Neo4j, rollback, race, constraint collision, tenant, stale/missing data và restart.
12. **Đối soát:** ghế còn lại không âm; ghế đã xác nhận + còn lại bằng capacity theo mô hình nghiệp vụ.
13. **Quan sát:** có request/correlation ID, lỗi theo loại, latency p95/p99, lock contention và cảnh báo mất telemetry.
14. **Tài nguyên:** có kế hoạch xử lý Event nóng, quá tải, connection pool, index và transaction log.
15. **Phục hồi:** backup được diễn tập restore, migration/rollout có điểm dừng và đường rollback được đánh giá.
16. **Bàn giao:** tài liệu, mã, cấu hình không chứa secret, test report, giới hạn đã biết và owner vận hành.

**Kết luận:** một đồ án Java/Spring Boot với Neo4j đạt yêu cầu khi **bất biến nghiệp vụ vẫn đúng dưới lỗi và cạnh tranh**, không chỉ khi một HTTP request thành công. Hãy bắt đầu bằng graph schema và uniqueness constraint, xây mutation với write lock và transaction rõ ràng, sử dụng idempotency key để xử lý retry/unknown commit, kiểm quyền theo tenant và đối tượng, rồi đo lại bằng integration test và Cypher đối soát. Khi các điều kiện đó được chứng minh, API trên property graph mới có cơ sở để vận hành tin cậy.
