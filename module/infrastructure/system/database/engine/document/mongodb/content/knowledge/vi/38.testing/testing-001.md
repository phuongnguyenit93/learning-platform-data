# Phân chia kiểm thử đơn vị, tích hợp và đầu cuối cho ứng dụng MongoDB

## 1. Vì sao một dự án MongoDB cần nhiều tầng kiểm thử?

Giả sử một hệ thống cho thuê nhà dùng **Spring Boot, Spring Data MongoDB và MongoDB replica set**. Người thuê gửi yêu cầu đặt lịch xem nhà; backend tạo một booking, lưu nó vào collection, cho phép chủ nhà xác nhận và trả trạng thái qua REST API.

Một ngày, bản triển khai mới xuất hiện các lỗi:

- Service xác nhận lại một booking đã hủy.
- Java property **tenantId** được đổi thành tên BSON **tenant_id**, nhưng một query cũ vẫn dùng sai tên field.
- Index unique không được tạo trong môi trường staging, cho phép một yêu cầu bị ghi trùng.
- HTTP controller trả **200 OK** thay vì **201 Created**.
- API cho phép người thuê thuộc tenant A đọc booking của tenant B.
- Luồng tạo booking hoạt động trên máy developer nhưng thất bại khi kết nối MongoDB thực vì vấn đề BSON type hoặc transaction.

Không có **một loại test duy nhất** vừa nhanh, vừa cô lập hoàn toàn, vừa chứng minh được tất cả những điều trên.

Ta cần tách trách nhiệm:

~~~text
                 Người dùng / client
                        |
                  HTTP REST API
                        |
                   Controller
                        |
                  BookingService
                        |
                 BookingRepository
                        |
               Spring Data mapping
                        |
                 MongoDB driver
                        |
                     MongoDB

UNIT TEST:
  Business rule trong BookingService, repository giả lập

INTEGRATION TEST:
  Repository + mapper + driver + MongoDB thật

END-TO-END TEST:
  Client gửi HTTP -> Controller -> Service -> Repository
    -> MongoDB thật -> HTTP response
~~~

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **kiểm thử đơn vị (unit)**, **kiểm thử tích hợp (integration)** và **kiểm thử đầu cuối (end-to-end/E2E)** theo **ranh giới hệ thống thật sự chạy**.
2. Quyết định một yêu cầu nên được kiểm tra ở tầng nào để **tránh trùng lặp và chậm không cần thiết**.
3. Dùng **JUnit 5 + Mockito** để kiểm thử service MongoDB mà không cần database.
4. Dùng **@DataMongoTest + Testcontainers** để kiểm chứng Spring Data mapping, repository query và BSON thực.
5. Dùng **@WebMvcTest/MockMvc** đúng phạm vi — không nhầm controller slice test với full E2E.
6. Dùng **@SpringBootTest(webEnvironment = RANDOM_PORT)** và HTTP client để kiểm tra một luồng API có MongoDB thật.
7. Kiểm thử các đặc điểm riêng của MongoDB: **_id, @Field, embedded documents, unique indexes, optimistic locking, transactions, write concern, TTL và Change Streams**.
8. Tạo fixture có thể tái lập, độc lập giữa các tests và không ảnh hưởng dữ liệu production.
9. Thiết kế negative tests về validation, tenant isolation, concurrency và lỗi database.
10. Xây chiến lược CI, chọn số lượng tests ở từng tầng, quản lý flaky tests và ghi nhận bằng chứng phù hợp.

> **Phạm vi:** Bài thuộc **Database Engine Document MongoDB → Kiểm thử**. Ví dụ dùng **Java 17+, Spring Boot 3.4+ tương thích Spring Data MongoDB, JUnit Jupiter, Mockito và Testcontainers**. Một số annotation/versions có thể đổi theo BOM và các phiên bản mới; kiểm tra API tương ứng trước khi sử dụng. Không chạy test hoặc Gradle trong bước viết tài liệu này. Tất cả dữ liệu/collections ví dụ chỉ dành cho **MongoDB test container hoặc database lab riêng**, không dùng production.

## 2. Ba tầng kiểm thử khác nhau ở đâu?

### 2.1. Unit test

**Unit test** kiểm tra một đơn vị logic nhỏ, thường là một class hoặc một nhóm hàm, với dependency bên ngoài được thay bằng test double nếu cần.

Ví dụ:

> “Khi booking đã CANCELLED, lời gọi confirm phải bị từ chối và repository.save không được chạy.”

Không cần MongoDB server để xác minh business rule này.

~~~text
JUnit -> BookingService -> Mockito BookingRepository
                      |
                 Không có MongoDB
~~~

Đặc điểm:

- Chạy nhanh, ít phụ thuộc môi trường.
- Lỗi thường dễ khoanh vùng.
- Phù hợp kiểm tra state transitions, validation, mapping thuần Java, pricing calculation.
- Không chứng minh query MongoDB đúng hay BSON được lưu theo schema dự kiến.

### 2.2. Integration test

**Integration test** kiểm tra sự phối hợp giữa những thành phần thật, chẳng hạn:

> “Khi BookingRepository lưu BookingDocument, tenantId phải được ghi thành tenant_id, guest.fullName thành guest.full_name, và truy vấn findByIdAndTenantId phải trả đúng booking.”

Để chứng minh điều này, cần **Spring Data mapper + MongoDB driver + MongoDB server thật**.

~~~text
JUnit -> MongoRepository -> MappingMongoConverter
       -> MongoDB Java Driver -> Testcontainers MongoDB
~~~

Đặc điểm:

- Chậm hơn unit test, thường cần runtime Docker hoặc database test được quản lý.
- Kiểm chứng BSON, index, query, server constraints và các tình huống data access.
- Không tự chứng minh HTTP routing, JSON serialization hoặc frontend hoạt động.

### 2.3. End-to-end test

**End-to-end** kiểm tra luồng nghiệp vụ đi qua những thành phần cần chứng minh, nhìn từ điểm bắt đầu đến điểm kết thúc đã xác định.

Ví dụ:

> “Client POST /api/bookings được 201 Created, sau đó GET bằng cùng tenant trả booking, còn GET với tenant khác không trả dữ liệu.”

~~~text
HTTP client
     |
     v
Spring Boot HTTP server (real port)
     |
     v
Controller -> Service -> Repository -> MongoDB thật
     |
     v
HTTP status + response JSON + persisted state
~~~

Nếu không dùng real browser, đây có thể là **service-level E2E**. Nó chứng minh đầy đủ luồng của service nhưng **chưa chứng minh UI, ingress, SSO hoặc mọi hệ thống ngoài**. Phải nói rõ **điểm đầu/điểm cuối** khi gọi một test là E2E.

### 2.4. Bảng đối chiếu

| Tiêu chí | Unit | Integration | End-to-end |
| --- | --- | --- | --- |
| Đối tượng | Logic riêng lẻ | Ranh giới giữa các thành phần | Luồng người dùng/nghiệp vụ |
| MongoDB thật | Không cần | Thường có | Có nếu luồng phụ thuộc DB |
| HTTP server thật | Không | Không bắt buộc | Thường có với service E2E |
| Dependency giả | Nhiều khi dùng Mockito | Hạn chế giả ở đúng ranh giới | Hạn chế nhất; vẫn có thể stub hệ ngoài có kiểm soát |
| Tốc độ | Nhanh | Trung bình | Chậm hơn |
| Khả năng khoanh lỗi | Cao | Trung bình | Thấp hơn nếu nhiều thành phần |
| Phát hiện sai BSON @Field | Không đáng tin nếu chỉ mock | Có | Có thể phát hiện gián tiếp |
| Phát hiện sai HTTP status | Không nếu chỉ test service | Không nếu chỉ test repository | Có |
| Phát hiện lỗi business rule | Có | Có thể | Có thể |
| Rủi ro flakiness | Thường thấp | Phụ thuộc môi trường DB | Cao hơn khi nhiều dịch vụ |

**Phân loại theo thành phần đã chạy thật**, không theo tên method như testIntegration() hay tên thư mục.

## 3. Không phải tất cả test thuộc đúng ba nhãn trên

Trong thực tế còn các thuật ngữ:

- **Component test:** kiểm tra một component với một phần dependencies thật và một phần giả.
- **Slice test:** Spring Boot nạp một phần application context, ví dụ **@WebMvcTest** hoặc **@DataMongoTest**.
- **Contract test:** kiểm tra hợp đồng request/response/schema giữa hai dịch vụ.
- **System test:** kiểm tra hệ thống lớn đã tích hợp, có thể gồm nhiều service.
- **Smoke test:** một số hành trình cơ bản sau khi triển khai.
- **Performance/load test:** đo throughput/latency dưới tải.
- **Resilience/failover test:** kiểm tra ứng xử khi lỗi hạ tầng.

Một **@WebMvcTest** dùng MockMvc và mock BookingService là **controller slice/component test**, không phải full E2E, dù có HTTP method và JSON.

Một **@DataMongoTest** chạy MongoDB thật là **persistence integration test**, dù không hề gọi REST controller.

### 3.1. Test pyramid là định hướng, không phải luật phần trăm

~~~text
                   /\
                  /  \
                 / E2E\        Ít, chọn hành trình quan trọng
                /------\
               /  Integ \      Ranh giới dữ liệu và dịch vụ
              /----------\
             /    Unit    \    Nhiều trường hợp logic nhỏ, nhanh
            /______________\
~~~

Ta thường muốn **nhiều unit test nhanh**, **integration tests đúng chỗ** và **ít E2E tests nhưng có giá trị**.

Không có tỷ lệ bắt buộc 70/20/10 cho mọi dự án. Một dịch vụ chủ yếu là persistence mapping có thể cần nhiều integration tests; một business engine ít I/O có thể cần phần lớn unit tests.

### 3.2. Khi nào đặt bài kiểm tra ở tầng thấp hơn?

Quy tắc thực dụng:

> Nếu một lỗi có thể được chứng minh đáng tin cậy ở tầng thấp, không cần lặp lại cùng mười tổ hợp dữ liệu ở E2E.

Ví dụ validation của booking:

- Unit test 12 tình huống title/tenant/request input.
- Integration test 2 tình huống cần MongoDB thật.
- E2E test 1–2 hành trình đại diện để chứng minh wiring và HTTP contract.

Tuy nhiên, đừng đẩy test xuống tầng mock nếu **behavior cần chứng minh thuộc database**.

## 4. Phân chia theo câu hỏi, không theo tên class

Một yêu cầu nghiệp vụ nên được tách thành nhiều điều kiện độc lập.

| Câu hỏi cần trả lời | Tầng phù hợp | Lý do |
| --- | --- | --- |
| Có cho confirm booking CANCELLED không? | Unit | State transition thuần Java |
| Có kiểm tra tenantId/ID bắt buộc không? | Unit | Validation service |
| Service có gọi repository.save đúng đối tượng không? | Unit | Interaction với dependency |
| tenantId Java thành tenant_id BSON đúng không? | Integration | Cần MappingMongoConverter |
| Repository query nested field trả dữ liệu đúng không? | Integration | Cần server query semantics |
| MongoDB từ chối duplicate key thật không? | Integration | Constraint do server thực thi |
| Transaction rollback khi lệnh thứ hai thất bại không? | Integration | Cần replica set và transaction |
| REST POST trả 201 và JSON chuẩn không? | Controller slice hoặc E2E | Slice để kiểm tra controller; E2E để xác nhận toàn luồng |
| HTTP request tạo được document đúng trong MongoDB không? | E2E | Kiểm tra xuyên các lớp |
| Người thuộc tenant khác nhận 404/403 theo policy không? | Unit + E2E | Policy riêng và enforcement ở API |
| Tải 500 req/s vẫn đạt p99 không? | Performance | Không phải mục tiêu của unit |
| Secondary stepdown thì driver reconnect được không? | Resilience integration/system | Cần topology thật/mô phỏng hợp lệ |

Nếu chỉ ghi “test BookingRepository” mà chưa có câu hỏi cụ thể, khó biết liệu test nên dùng Mockito hay Testcontainers.

## 5. Mô hình ví dụ xuyên suốt bài

### 5.1. Luồng nghiệp vụ

Ta thiết kế một **Booking API** đơn giản:

1. Người dùng yêu cầu tạo booking cho một listing.
2. Booking được lưu với trạng thái **REQUESTED**.
3. Người có quyền trong tenant gọi confirm, chuyển trạng thái sang **CONFIRMED**.
4. Booking đã **CANCELLED** không được confirm.
5. Mọi thao tác đọc/sửa phải giới hạn theo **tenantId**.

Đây là mô hình nhỏ để làm rõ test boundaries. Hệ thống thật còn cần xác thực, quyền theo actor, listing ownership, availability, idempotency, audit và concurrency controls.

### 5.2. BSON contract

Collection **booking_requests_411**:

~~~javascript
{
  _id: "bk-411-example",
  tenant_id: "tenant-001",
  listing_id: "listing-100",
  guest: {
    full_name: "Lan"
  },
  status: "REQUESTED",
  created_at: ISODate("2026-01-15T09:00:00Z"),
  _class: "com.example.mongo411.domain.BookingDocument"
}
~~~

**_class** có thể được Spring Data mặc định thêm; dạng chính xác phụ thuộc converter/type mapper. Các test không nên phụ thuộc một tên class nếu ứng dụng có chủ đích dùng alias hoặc vô hiệu type metadata.

### 5.3. Ranh giới của bài học

~~~text
HTTP client
   |
BookingController
   |
BookingService
   |             Clock
BookingRepository (Spring Data)
   |
MongoDB
~~~

**Clock** được inject để unit test kiểm soát thời gian. **BookingRepository** được mock ở unit, dùng thật với Testcontainers ở integration và E2E.

### 5.4. Quy ước package

~~~text
src/main/java/com/example/mongo411/
  Mongo411Application.java
  domain/
    BookingStatus.java
    GuestInfo.java
    BookingDocument.java
  repository/
    BookingRepository.java
  service/
    BookingService.java
  web/
    BookingController.java
    CreateBookingRequest.java
    BookingResponse.java
    BookingErrorHandler.java

src/test/java/com/example/mongo411/
  service/BookingServiceUnitTest.java
  repository/BookingRepositoryIntegrationTest.java
  web/BookingControllerSliceTest.java
  BookingHttpE2ETest.java
~~~

Mỗi đoạn Java có tên file riêng; nếu tự tạo project lab, đặt đúng package/import và dependency. Bài viết này không tạo các file Java đó trên máy người dùng.

## 6. Cấu hình tối thiểu cho project lab

### 6.1. Dependencies

Với Maven và dependency management từ Spring Boot phù hợp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-mongodb</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>mongodb</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Artifact names minh họa **Testcontainers 1.x**. Các major versions mới có thể đổi module coordinates; dùng **BOM tương thích** và kiểm tra tài liệu của version đang chọn. Trong Spring Boot 3.4+/Spring Framework 6.2+, ví dụ controller slice phía dưới dùng **@MockitoBean**.

### 6.2. Cần Docker/Testcontainers cho tầng nào?

- **Unit test với Mockito:** không cần Docker/MongoDB.
- **@WebMvcTest controller slice:** không cần MongoDB nếu service được mock.
- **@DataMongoTest với MongoDBContainer:** cần môi trường chạy containers tương thích.
- **@SpringBootTest E2E với MongoDBContainer:** cần database test container và real HTTP server.

Nếu CI không chạy được Docker, đó là vấn đề hạ tầng test; không nên thay mọi integration test bằng mock rồi vẫn tuyên bố đã kiểm chứng MongoDB thật.

### 6.3. Spring Boot application

File **Mongo411Application.java**:

~~~java
package com.example.mongo411;

import java.time.Clock;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Mongo411Application {

    public static void main(String[] args) {
        SpringApplication.run(
            Mongo411Application.class, args
        );
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Production dùng thời gian hệ thống, còn unit test có thể inject **Clock.fixed** để kiểm tra chính xác createdAt.

## 7. Domain model và repository thực

### 7.1. BookingStatus

File **domain/BookingStatus.java**:

~~~java
package com.example.mongo411.domain;

public enum BookingStatus {
    REQUESTED,
    CONFIRMED,
    CANCELLED
}
~~~

### 7.2. GuestInfo là embedded document

File **domain/GuestInfo.java**:

~~~java
package com.example.mongo411.domain;

import org.springframework.data.mongodb.core.mapping.Field;

public class GuestInfo {

    @Field("full_name")
    private String fullName;

    protected GuestInfo() {
    }

    public GuestInfo(String fullName) {
        this.fullName = fullName;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Embedded object không tự cần một collection riêng.

### 7.3. BookingDocument

File **domain/BookingDocument.java**:

~~~java
package com.example.mongo411.domain;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "booking_requests_411")
public class BookingDocument {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("listing_id")
    private String listingId;

    @Field("guest")
    private GuestInfo guest;

    @Field("status")
    private BookingStatus status;

    @Field("created_at")
    private Instant createdAt;

    protected BookingDocument() {
    }

    public BookingDocument(
            String id,
            String tenantId,
            String listingId,
            GuestInfo guest,
            Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.listingId = listingId;
        this.guest = guest;
        this.status = BookingStatus.REQUESTED;
        this.createdAt = createdAt;
    }

    public void confirm() {
        if (status == BookingStatus.CANCELLED) {
            throw new IllegalStateException(
                "Booking đã hủy không thể xác nhận"
            );
        }
        status = BookingStatus.CONFIRMED;
    }

    public void cancel() {
        status = BookingStatus.CANCELLED;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getListingId() {
        return listingId;
    }

    public GuestInfo getGuest() {
        return guest;
    }

    public BookingStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

ID dạng **"bk-411..."** trong ví dụ là String không có hình dạng 24 chữ số hexadecimal, nên tránh sự nhập nhằng về conversion **@Id String → BSON ObjectId**. Với IDs trông giống ObjectId, phải kiểm tra cách Spring Data MongoDB chuyển đổi hoặc chọn chiến lược **@MongoId(FieldType.STRING)** phù hợp.

### 7.4. BookingRepository

File **repository/BookingRepository.java**:

~~~java
package com.example.mongo411.repository;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;
import com.example.mongo411.domain.BookingDocument;

public interface BookingRepository
        extends MongoRepository<BookingDocument, String> {

    Optional<BookingDocument> findByIdAndTenantId(
        String id,
        String tenantId
    );
}
~~~

Derived query phải dùng mapping để đọc MongoDB:

~~~javascript
{
  _id: "bk-411-example",
  tenant_id: "tenant-001"
}
~~~

Đây là điều **integration test** nên chứng minh. Mockito không biết MongoDB có field tenant_id hay không.

## 8. BookingService: điểm tập trung business rules

File **service/BookingService.java**:

~~~java
package com.example.mongo411.service;

import java.time.Clock;
import java.time.Instant;
import java.util.NoSuchElementException;
import java.util.UUID;

import org.springframework.stereotype.Service;

import com.example.mongo411.domain.BookingDocument;
import com.example.mongo411.domain.BookingStatus;
import com.example.mongo411.domain.GuestInfo;
import com.example.mongo411.repository.BookingRepository;

@Service
public class BookingService {

    private final BookingRepository repository;
    private final Clock clock;

    public BookingService(
            BookingRepository repository,
            Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public BookingDocument createBooking(
            String tenantId,
            String listingId,
            String guestName) {
        requireText(tenantId, "tenantId");
        requireText(listingId, "listingId");
        requireText(guestName, "guestName");

        BookingDocument booking = new BookingDocument(
            "bk-411-" + UUID.randomUUID(),
            tenantId,
            listingId,
            new GuestInfo(guestName),
            Instant.now(clock)
        );

        return repository.save(booking);
    }

    public BookingDocument getBooking(
            String tenantId,
            String bookingId) {
        requireText(tenantId, "tenantId");
        requireText(bookingId, "bookingId");

        return repository
            .findByIdAndTenantId(bookingId, tenantId)
            .orElseThrow(() -> new NoSuchElementException(
                "Booking không tồn tại trong tenant"
            ));
    }

    public BookingDocument confirmBooking(
            String tenantId,
            String bookingId) {
        BookingDocument booking =
            getBooking(tenantId, bookingId);

        if (booking.getStatus()
                == BookingStatus.CONFIRMED) {
            // Không ghi lại nếu đã ở trạng thái đích.
            return booking;
        }

        booking.confirm();
        return repository.save(booking);
    }

    private static void requireText(
            String value,
            String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                fieldName + " không được để trống"
            );
        }
    }
}
~~~

Service này **cố tình tối giản để học kiểm thử**:

- Không tích hợp authentication thật.
- Không xác nhận listing còn khả dụng.
- Không dùng optimistic locking, nên concurrent updates có thể gây lost update.
- Không có idempotency key cho create.
- Không có audit hoặc multi-document transaction.

Các giới hạn này trở thành những yêu cầu test và thiết kế bổ sung ở các mục sau.

## 9. Unit test với JUnit 5 và Mockito

### 9.1. Tại sao mock repository?

Các quy tắc như **booking đã hủy không thể xác nhận** không phụ thuộc vào disk, network, BSON, index hay replica set. Unit test có thể dùng mock để lập tức trả ra một BookingDocument có trạng thái mong muốn.

Mục tiêu là:

~~~text
Khi: repository trả booking CANCELLED
Thì: confirmBooking ném IllegalStateException
Và: repository.save không được gọi
~~~

### 9.2. Ví dụ unit test

File **service/BookingServiceUnitTest.java**:

~~~java
package com.example.mongo411.service;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.NoSuchElementException;
import java.util.Optional;

import com.example.mongo411.domain.BookingDocument;
import com.example.mongo411.domain.BookingStatus;
import com.example.mongo411.domain.GuestInfo;
import com.example.mongo411.repository.BookingRepository;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class BookingServiceUnitTest {

    private static final Instant FIXED_TIME =
        Instant.parse("2026-01-15T09:00:00Z");

    @Mock
    BookingRepository repository;

    BookingService service;

    @BeforeEach
    void setUp() {
        Clock clock = Clock.fixed(
            FIXED_TIME, ZoneOffset.UTC
        );
        service = new BookingService(
            repository, clock
        );
    }

    @Test
    void createBookingSavesRequestedState() {
        when(repository.save(any(BookingDocument.class)))
            .thenAnswer(call -> call.getArgument(0));

        BookingDocument result = service.createBooking(
            "tenant-001",
            "listing-100",
            "Lan"
        );

        assertNotNull(result.getId());
        assertTrue(result.getId().startsWith("bk-411-"));
        assertEquals(
            BookingStatus.REQUESTED, result.getStatus()
        );
        assertEquals(FIXED_TIME, result.getCreatedAt());
        assertEquals(
            "tenant-001", result.getTenantId()
        );
        assertEquals(
            "Lan", result.getGuest().getFullName()
        );
        verify(repository).save(result);
    }

    @Test
    void rejectsBlankTenantWithoutDatabaseCall() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.createBooking(
                " ", "listing-100", "Lan"
            )
        );

        verifyNoInteractions(repository);
    }

    @Test
    void confirmsRequestedBookingAndPersistsIt() {
        BookingDocument booking = booking("bk-411-1");

        when(repository.findByIdAndTenantId(
            "bk-411-1", "tenant-001"
        )).thenReturn(Optional.of(booking));
        when(repository.save(booking))
            .thenReturn(booking);

        BookingDocument result = service.confirmBooking(
            "tenant-001", "bk-411-1"
        );

        assertEquals(
            BookingStatus.CONFIRMED, result.getStatus()
        );
        verify(repository).save(booking);
    }

    @Test
    void cannotConfirmCancelledBooking() {
        BookingDocument booking = booking("bk-411-2");
        booking.cancel();

        when(repository.findByIdAndTenantId(
            "bk-411-2", "tenant-001"
        )).thenReturn(Optional.of(booking));

        assertThrows(
            IllegalStateException.class,
            () -> service.confirmBooking(
                "tenant-001", "bk-411-2"
            )
        );

        verify(repository, never()).save(any());
    }

    @Test
    void confirmedBookingIsIdempotentForConfirm() {
        BookingDocument booking = booking("bk-411-3");
        booking.confirm();

        when(repository.findByIdAndTenantId(
            "bk-411-3", "tenant-001"
        )).thenReturn(Optional.of(booking));

        BookingDocument result = service.confirmBooking(
            "tenant-001", "bk-411-3"
        );

        assertEquals(
            BookingStatus.CONFIRMED, result.getStatus()
        );
        verify(repository, never()).save(any());
    }

    @Test
    void missingOrOtherTenantBookingIsNotReturned() {
        when(repository.findByIdAndTenantId(
            "bk-411-4", "tenant-002"
        )).thenReturn(Optional.empty());

        assertThrows(
            NoSuchElementException.class,
            () -> service.getBooking(
                "tenant-002", "bk-411-4"
            )
        );

        verify(repository).findByIdAndTenantId(
            "bk-411-4", "tenant-002"
        );
    }

    private BookingDocument booking(String id) {
        return new BookingDocument(
            id,
            "tenant-001",
            "listing-100",
            new GuestInfo("Lan"),
            FIXED_TIME
        );
    }
}
~~~

### 9.3. Unit test thực sự chứng minh điều gì?

Các test trên chứng minh:

- Service validation được thực hiện trước khi gọi repository.
- Trạng thái REQUESTED/CONFIRMED/CANCELLED tuân thủ rules.
- Clock có thể được cố định.
- Service truyền **cả bookingId và tenantId** tới repository.
- Không có save khi rule không cho phép.

Chúng **không chứng minh**:

- Method findByIdAndTenantId chuyển thành query BSON đúng.
- Mongod lưu guest.full_name đúng.
- Index unique có tồn tại.
- API trả status code đúng.
- MongoDB thật có thể kết nối.

### 9.4. Test double trả đúng theo stub, không phải theo database

Ví dụ:

~~~java
when(repository.findByIdAndTenantId(
    "bk-411-1", "tenant-001"
)).thenReturn(Optional.of(booking));
~~~

Mockito trả booking vì ta yêu cầu nó làm vậy; nó **không phân tích MongoDB field names**. Nếu tên derived query sai hoặc tên field đã đổi, unit test vẫn có thể PASS.

### 9.5. Tránh quá phụ thuộc verify

Không phải mọi unit test đều cần verify thứ tự từng lời gọi. Nếu test chỉ thành công vì một method nội bộ được gọi đúng ba lần, refactor implementation có thể làm test lỗi dù behavior không đổi.

Ưu tiên assertion vào **observable behavior**, dùng interaction assertions khi chính việc **không ghi/không gọi dependency** là một phần của yêu cầu.

## 10. Test thuần Java mà không cần Mockito

Một phương thức domain như:

~~~java
public void confirm() {
    if (status == BookingStatus.CANCELLED) {
        throw new IllegalStateException(
            "Booking đã hủy không thể xác nhận"
        );
    }
    status = BookingStatus.CONFIRMED;
}
~~~

có thể được test trực tiếp:

~~~java
@Test
void cancelledBookingCannotBeConfirmed() {
    BookingDocument booking = new BookingDocument(
        "bk-411-domain",
        "tenant-001",
        "listing-100",
        new GuestInfo("Lan"),
        Instant.parse("2026-01-15T09:00:00Z")
    );

    booking.cancel();

    assertThrows(
        IllegalStateException.class,
        booking::confirm
    );
    assertEquals(
        BookingStatus.CANCELLED,
        booking.getStatus()
    );
}
~~~

Đây là unit test **không cần mock**. Không nên thêm Mockito chỉ vì file có hậu tố Test.

## 11. Integration test MongoDB thật với Testcontainers

### 11.1. Vì sao không dùng mocked MongoTemplate?

Mocked MongoTemplate không thực hiện:

- BSON serialization/deserialization.
- Mapping **@Field("tenant_id")**.
- Query execution và nested array semantics.
- MongoDB unique index enforcement.
- Real server transaction semantics.
- Driver/server wire protocol và errors.

Một integration test đúng mục tiêu phải dùng **MongoDB server thực**, dù nó chạy trong container tạm thời.

### 11.2. Testcontainers làm gì?

**Testcontainers** tạo một MongoDB container phù hợp với integration tests, cung cấp URI kết nối và dọn môi trường theo lifecycle test.

Ưu điểm:

- Không phụ thuộc dữ liệu trong máy của developer.
- Cùng image/version trên CI khi cấu hình nhất quán.
- Có thể tái lập lỗi MongoDB thật.
- Phù hợp kiểm tra mapping, repository, indexes và dữ liệu.

Lưu ý:

- Cần container runtime phù hợp.
- Image pull có thể tốn thời gian.
- Tập dữ liệu test nên nhỏ nhưng có đủ edge cases.
- Version image cần gần production, không dùng “latest” không kiểm soát.
- Một container single-node **không chứng minh HA/failover của replica set ba node**.

### 11.3. @DataMongoTest

**@DataMongoTest** là Spring Boot test slice tập trung vào MongoDB persistence components, thường nạp mapping, repositories và MongoTemplate, không nạp tất cả web/services của hệ thống.

Đây là phạm vi tốt cho:

> “Repository method này có thật sự truy vấn đúng field BSON và trả ra Java object mong muốn không?”

### 11.4. Integration test hoàn chỉnh

File **repository/BookingRepositoryIntegrationTest.java**:

~~~java
package com.example.mongo411.repository;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;

import com.example.mongo411.domain.BookingDocument;
import com.example.mongo411.domain.GuestInfo;

import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataMongoTest
@Testcontainers
class BookingRepositoryIntegrationTest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongodbProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
    }

    @Autowired
    BookingRepository repository;

    @Autowired
    MongoTemplate template;

    @BeforeEach
    void resetTestCollection() {
        // CHỈ trên MongoDB test container của class này.
        template
            .getCollection("booking_requests_411")
            .deleteMany(new Document());
    }

    @Test
    void savesMappedBsonFieldNamesAndNestedGuest() {
        BookingDocument booking = sample(
            "bk-411-it-1",
            "tenant-001"
        );
        repository.save(booking);

        Document bson = template
            .getCollection("booking_requests_411")
            .find(new Document("_id", "bk-411-it-1"))
            .first();

        assertNotNull(bson);
        assertEquals(
            "tenant-001", bson.getString("tenant_id")
        );
        assertFalse(bson.containsKey("tenantId"));

        Document guest = bson.get("guest", Document.class);
        assertNotNull(guest);
        assertEquals(
            "Lan", guest.getString("full_name")
        );
        assertEquals(
            "REQUESTED", bson.getString("status")
        );
        assertNotNull(bson.getDate("created_at"));
    }

    @Test
    void derivedQueryRequiresMatchingTenant() {
        repository.save(
            sample("bk-411-it-2", "tenant-001")
        );

        assertTrue(
            repository.findByIdAndTenantId(
                "bk-411-it-2", "tenant-001"
            ).isPresent()
        );
        assertTrue(
            repository.findByIdAndTenantId(
                "bk-411-it-2", "tenant-002"
            ).isEmpty()
        );
    }

    @Test
    void duplicateIdIsRejectedByRealMongoDb() {
        repository.insert(
            sample("bk-411-dup", "tenant-001")
        );

        assertThrows(
            DuplicateKeyException.class,
            () -> repository.insert(
                sample("bk-411-dup", "tenant-002")
            )
        );
    }

    private BookingDocument sample(
            String id,
            String tenantId) {
        return new BookingDocument(
            id,
            tenantId,
            "listing-100",
            new GuestInfo("Lan"),
            Instant.parse("2026-01-15T09:00:00Z")
        );
    }
}
~~~

### 11.5. Điều test này chứng minh

- **MongoRepository.save()** thực hiện lệnh ghi qua driver.
- **@Field** lưu đúng **tenant_id**.
- Embedded guest có **full_name**.
- BSON Date được lưu cho created_at.
- Derived query **findByIdAndTenantId** hoạt động với database thật.
- MongoDB thực thi uniqueness của **_id** khi insert hai documents có cùng ID.

### 11.6. Tại sao dùng insert trong test duplicate?

**save** có semantics khác **insert**. Nếu save document với _id đã tồn tại, repository có thể thực hiện replace/upsert phù hợp; đó **không phải** phép thử tốt cho duplicate-key on insert.

Để chứng minh MongoDB không chấp nhận hai inserts cùng _id, dùng **insert** rõ ràng.

### 11.7. Ghi chú về MongoDBContainer

Trong các phiên bản Testcontainers MongoDB module được minh họa, **getReplicaSetUrl()** trả URI phù hợp với container replica set single-node được Testcontainers dựng cho mục đích test.

Không suy ra:

~~~text
MongoDBContainer có replicaSetUrl
  => đã test được election ba nodes,
     network partition và cross-region latency.
~~~

Những kịch bản HA/failover cần topology/chaos test riêng.

### 11.8. Không dùng database production trong @DataMongoTest

Một dòng:

~~~java
template.getCollection(
    "booking_requests_411"
).deleteMany(new Document());
~~~

là hợp lý **chỉ vì đây là MongoDB container cô lập do test tạo**.

Nếu cấu hình URI nhầm production, dòng này có thể xóa dữ liệu thật. Khi tổ chức triển khai:

- Có test profile không chứa production secret.
- CI credentials chỉ được vào test database.
- Network policy ngăn test runner chạm production khi có thể.
- Fail-fast khi URI không thuộc test deployment.
- Không chạy destructive cleanup nếu không xác thực môi trường.

## 12. Kiểm thử unique index và server constraints

### 12.1. Annotation index khác index đã có thật

Nếu model thêm:

~~~java
@Indexed(unique = true)
private String externalRequestId;
~~~

không thể chỉ assert annotation tồn tại rồi kết luận server sẽ từ chối duplicate. Việc auto-create index có cấu hình/điều kiện riêng, và data migration có thể làm index build thất bại.

**Integration test** nên kiểm tra index thực sự được tạo và hiệu lực của nó.

### 12.2. Tạo unique index trên collection test riêng

Ví dụ minh họa trong MongoDB container cô lập:

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

MongoCollection<Document> keys =
    template.getCollection("request_keys_411");

keys.deleteMany(new Document());
keys.createIndex(
    new Document("tenant_id", 1)
        .append("request_key", 1),
    new IndexOptions().unique(true)
);

keys.insertOne(
    new Document("_id", "key-411-a")
        .append("tenant_id", "tenant-001")
        .append("request_key", "req-001")
);

assertThrows(
    MongoWriteException.class,
    () -> keys.insertOne(
        new Document("_id", "key-411-b")
            .append("tenant_id", "tenant-001")
            .append("request_key", "req-001")
    )
);
~~~

Đây là cách kiểm tra **server enforcement của compound unique index**. Tổ hợp cùng request_key nhưng tenant khác có thể được phép tùy index pattern.

### 12.3. Cần cả positive và negative test

- Positive: hai tenants khác nhau có thể dùng cùng request_key nếu hợp đồng cho phép.
- Negative: cùng tenant không thể ghi duplicate request_key.
- Migration: nếu đã có duplicates trước khi tạo index, index creation có thể thất bại.

Không phải tất cả unique indexes đều nên có trong runtime entity; production thường dùng controlled migrations.

## 13. Mapping và BSON type phải có integration coverage

### 13.1. Java String ID và ObjectId

Nếu dùng **@Id String**, Spring Data có thể áp dụng conversion sang ObjectId cho chuỗi có hình dạng phù hợp. Một unit test với mock repository không thấy vấn đề BSON type này.

Integration tests nên có:

- ID dạng String nghiệp vụ có dấu gạch.
- ID dạng hex 24 ký tự nếu hệ dùng nó.
- Query bằng Repository và raw MongoDB Document.
- Kiểm tra **_id** thật là BSON String hay ObjectId.

Nếu chính sách yêu cầu String thuần, cân nhắc **@MongoId(FieldType.STRING)** và kiểm tra readback.

### 13.2. BigDecimal và Decimal128

Với số tiền:

~~~java
@Field(
    value = "amount",
    targetType = FieldType.DECIMAL128
)
private BigDecimal amount;
~~~

Integration test cần khẳng định BSON type thực sự **decimal**, không phải String hoặc Double, và giá trị/scale được khôi phục đúng.

### 13.3. Nested arrays

Đối với:

~~~javascript
{
  rooms: [
    { type: "bedroom", area_sqm: 10 },
    { type: "kitchen", area_sqm: 30 }
  ]
}
~~~

Hai điều kiện:

~~~javascript
{
  "rooms.type": "bedroom",
  "rooms.area_sqm": { $gte: 20 }
}
~~~

có thể match **khác phần tử** trong array. Nếu nghiệp vụ yêu cầu cùng room thỏa cả hai, phải dùng **$elemMatch**.

Unit test chỉ xác minh một chuỗi query được build không đủ chứng minh semantics này. Hãy seed **document phản ví dụ** trong integration test.

### 13.4. Null và missing fields

Documents cũ có thể thiếu trường guest. Integration tests nên kiểm tra:

- guest không tồn tại.
- guest: null.
- guest.full_name: null.
- guest.full_name: "".
- guest.full_name có string hợp lệ.

MongoDB **{ field: null }** có thể match cả null và missing theo query semantics. Business logic cần biết khi nào dùng **$exists, $type** và validation.

### 13.5. Mapping _class

Một test converter có thể assert fields và nested objects nhưng **không cần assert hardcoded full class name** nếu dự án định thay type aliases. Nếu dùng polymorphism, có test tương ứng để chứng minh subclass được đọc đúng cả khi _class/type metadata thay đổi.

## 14. Controller slice test với @WebMvcTest

### 14.1. Khi nào dùng @WebMvcTest?

Nếu chỉ cần kiểm tra:

- Route **POST /api/bookings** có map đúng.
- Request body JSON có deserialize.
- Header được đọc.
- HTTP status là 201.
- Response DTO có fields được mong đợi.
- Controller đổi exceptions thành HTTP status.

thì **@WebMvcTest** có thể nhanh và đủ. Nó không cần chạy MongoDB.

### 14.2. DTO request/response

File **web/CreateBookingRequest.java**:

~~~java
package com.example.mongo411.web;

public record CreateBookingRequest(
    String listingId,
    String guestName
) {}
~~~

File **web/BookingResponse.java**:

~~~java
package com.example.mongo411.web;

import com.example.mongo411.domain.BookingDocument;

public record BookingResponse(
    String id,
    String listingId,
    String status,
    String createdAt
) {

    public static BookingResponse from(
            BookingDocument booking) {
        return new BookingResponse(
            booking.getId(),
            booking.getListingId(),
            booking.getStatus().name(),
            booking.getCreatedAt().toString()
        );
    }
}
~~~

### 14.3. Controller lab

File **web/BookingController.java**:

~~~java
package com.example.mongo411.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import com.example.mongo411.domain.BookingDocument;
import com.example.mongo411.service.BookingService;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {

    private final BookingService service;

    public BookingController(BookingService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<BookingResponse> create(
            @RequestHeader("X-Lab-Tenant") String tenant,
            @RequestBody CreateBookingRequest request) {
        BookingDocument saved = service.createBooking(
            tenant,
            request.listingId(),
            request.guestName()
        );
        return ResponseEntity
            .status(HttpStatus.CREATED)
            .body(BookingResponse.from(saved));
    }

    @GetMapping("/{id}")
    public BookingResponse get(
            @RequestHeader("X-Lab-Tenant") String tenant,
            @PathVariable String id) {
        return BookingResponse.from(
            service.getBooking(tenant, id)
        );
    }

    @PatchMapping("/{id}/confirm")
    public BookingResponse confirm(
            @RequestHeader("X-Lab-Tenant") String tenant,
            @PathVariable String id) {
        return BookingResponse.from(
            service.confirmBooking(tenant, id)
        );
    }
}
~~~

**Cảnh báo bảo mật:** Header **X-Lab-Tenant** chỉ là cơ chế giả lập danh tính để học. Trong production, tenantId phải được lấy từ **principal/session/token đã xác thực và được server kiểm chứng**. Không cho người dùng tự thay header rồi coi họ là tenant khác.

### 14.4. Chuyển exceptions thành status

File **web/BookingErrorHandler.java**:

~~~java
package com.example.mongo411.web;

import java.util.NoSuchElementException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
public class BookingErrorHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> badRequest(
            IllegalArgumentException error) {
        return ResponseEntity
            .badRequest()
            .body(error.getMessage());
    }

    @ExceptionHandler(NoSuchElementException.class)
    ResponseEntity<String> notFound(
            NoSuchElementException error) {
        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .body("Không tìm thấy booking");
    }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<String> conflict(
            IllegalStateException error) {
        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(error.getMessage());
    }
}
~~~

### 14.5. @WebMvcTest và @MockitoBean

File **web/BookingControllerSliceTest.java**:

~~~java
package com.example.mongo411.web;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

import java.time.Instant;

import com.example.mongo411.domain.BookingDocument;
import com.example.mongo411.domain.GuestInfo;
import com.example.mongo411.service.BookingService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(BookingController.class)
class BookingControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    BookingService service;

    @Test
    void postCreatesBookingAndReturns201() throws Exception {
        BookingDocument saved = new BookingDocument(
            "bk-411-mvc",
            "tenant-001",
            "listing-100",
            new GuestInfo("Lan"),
            Instant.parse("2026-01-15T09:00:00Z")
        );

        when(service.createBooking(
            "tenant-001", "listing-100", "Lan"
        )).thenReturn(saved);

        mvc.perform(
            post("/api/bookings")
                .header("X-Lab-Tenant", "tenant-001")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"listingId\":\"listing-100\","
                    + "\"guestName\":\"Lan\"}"
                )
        )
        .andExpect(status().isCreated())
        .andExpect(
            jsonPath("$.id").value("bk-411-mvc")
        )
        .andExpect(
            jsonPath("$.status").value("REQUESTED")
        );
    }
}
~~~

**Chú ý:** Trong Java, static imports của MockMvcRequestBuilders/MockMvcResultMatchers phải đặt trên **một dòng Java hợp lệ** (ở snippet chúng được xuống dòng sau dấu chấm để dễ đọc; trình biên dịch Java cho phép whitespace đó). Tùy cấu hình component scanning, cần bảo đảm **BookingErrorHandler** được đưa vào MVC slice khi muốn kiểm tra error mappings.

### 14.6. Chứng minh phạm vi thật

Test trên:

- Dùng Spring MVC mapping/JSON infrastructure.
- Controller được chạy thật.
- BookingService là Mockito mock.
- MongoDB **không được gọi**.
- Không chứng minh repository và persistence wiring.

Đây là một **slice test**, không nên ghi báo cáo “đã E2E booking workflow” chỉ từ bài này.

### 14.7. @AutoConfigureMockMvc với @SpringBootTest

Một ứng dụng có thể dùng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApiIntegrationTest {
    @Autowired MockMvc mvc;
}
~~~

Khi context đầy đủ và MongoDB thật, test có thể đi qua controller/service/repository nhưng **MockMvc không mở real TCP HTTP server**. Đó là **full-context HTTP-layer integration test**, không đồng nghĩa với real-port E2E. Chọn tên và mục tiêu cho rõ.

## 15. Service-level E2E với HTTP thật và MongoDB thật

### 15.1. Mục tiêu

Một E2E scenario nên chứng minh hành vi từ đầu đến cuối:

~~~text
POST /api/bookings
   |
   v
201 + booking ID
   |
   v
GET /api/bookings/{id}
   |
   v
200 + REQUESTED
   |
   v
PATCH /api/bookings/{id}/confirm
   |
   v
200 + CONFIRMED
   |
   v
MongoDB lưu status CONFIRMED
~~~

Kèm một negative path:

~~~text
GET với tenant khác
   |
   v
404 (không tiết lộ booking)
~~~

Đây là **service-level E2E với giả lập tenant header**, chưa phải bài security E2E với authentication thật.

### 15.2. @SpringBootTest RANDOM_PORT

Chọn:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
~~~

Spring Boot chạy embedded HTTP server trên port ngẫu nhiên. **TestRestTemplate** gửi request qua HTTP client tới server thật, không chỉ gọi controller như method Java.

### 15.3. E2E test hoàn chỉnh

File **BookingHttpE2ETest.java**:

~~~java
package com.example.mongo411;

import static org.junit.jupiter.api.Assertions.*;

import com.example.mongo411.web.BookingResponse;
import com.example.mongo411.web.CreateBookingRequest;

import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.http.*;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Testcontainers
class BookingHttpE2ETest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongodbProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
    }

    @Autowired
    TestRestTemplate http;

    @Autowired
    MongoTemplate template;

    @BeforeEach
    void clean() {
        template
            .getCollection("booking_requests_411")
            .deleteMany(new Document());
    }

    @Test
    void createReadConfirmAndIsolateTenant() {
        HttpHeaders ownerHeaders = new HttpHeaders();
        ownerHeaders.set("X-Lab-Tenant", "tenant-001");

        HttpEntity<CreateBookingRequest> createRequest =
            new HttpEntity<>(
                new CreateBookingRequest(
                    "listing-100", "Lan"
                ),
                ownerHeaders
            );

        ResponseEntity<BookingResponse> created =
            http.exchange(
                "/api/bookings",
                HttpMethod.POST,
                createRequest,
                BookingResponse.class
            );

        assertEquals(
            HttpStatus.CREATED,
            created.getStatusCode()
        );
        assertNotNull(created.getBody());
        assertEquals(
            "REQUESTED",
            created.getBody().status()
        );

        String bookingId = created.getBody().id();
        assertNotNull(bookingId);

        ResponseEntity<BookingResponse> fetched =
            http.exchange(
                "/api/bookings/" + bookingId,
                HttpMethod.GET,
                new HttpEntity<>(null, ownerHeaders),
                BookingResponse.class
            );

        assertEquals(
            HttpStatus.OK,
            fetched.getStatusCode()
        );
        assertEquals(
            bookingId, fetched.getBody().id()
        );

        ResponseEntity<BookingResponse> confirmed =
            http.exchange(
                "/api/bookings/" + bookingId + "/confirm",
                HttpMethod.PATCH,
                new HttpEntity<>(null, ownerHeaders),
                BookingResponse.class
            );

        assertEquals(
            HttpStatus.OK,
            confirmed.getStatusCode()
        );
        assertEquals(
            "CONFIRMED",
            confirmed.getBody().status()
        );

        Document saved = template
            .getCollection("booking_requests_411")
            .find(new Document("_id", bookingId))
            .first();

        assertNotNull(saved);
        assertEquals(
            "CONFIRMED", saved.getString("status")
        );
        assertEquals(
            "tenant-001", saved.getString("tenant_id")
        );

        HttpHeaders otherTenant = new HttpHeaders();
        otherTenant.set("X-Lab-Tenant", "tenant-002");

        ResponseEntity<String> denied =
            http.exchange(
                "/api/bookings/" + bookingId,
                HttpMethod.GET,
                new HttpEntity<>(null, otherTenant),
                String.class
            );

        assertEquals(
            HttpStatus.NOT_FOUND,
            denied.getStatusCode()
        );
    }
}
~~~

### 15.4. Tại sao E2E có thể bắt lỗi mà unit không bắt?

Một lỗi như:

~~~java
@GetMapping("/api/booking/{id}")
~~~

thay vì:

~~~java
@GetMapping("/api/bookings/{id}")
~~~

có thể làm E2E trả **404**, dù BookingService unit tests đều PASS.

Một lỗi cấu hình URI, bean wiring hoặc response serializer cũng có thể chỉ xuất hiện khi chạy application thật.

### 15.5. Giới hạn của E2E trong ví dụ

Đây **không phải production-wide E2E** vì:

- Tenant header chưa được JWT/SSO xác minh.
- Không có ingress/load balancer/API gateway.
- Chỉ có một MongoDB test container, không đủ để thử failover ba nodes.
- Không có email, payment, message broker hay search index bên ngoài.
- Không kiểm tra UI browser.
- Chưa kiểm tra concurrent requests thực tế.

Khi báo cáo phải ghi đúng: **“service-level HTTP-to-MongoDB E2E”**.

## 16. Phân biệt E2E, contract, UI và smoke test

### 16.1. E2E ở cấp service

HTTP thật → Spring Boot → MongoDB thật. Ví dụ ở mục 15.

### 16.2. E2E ở cấp sản phẩm

Một hành trình người dùng đầy đủ:

~~~text
Browser
  -> Login/Identity Provider
  -> Frontend
  -> API Gateway
  -> Booking Service
  -> MongoDB
  -> Notification Service
  -> Email/SMS sandbox
  -> User nhận xác nhận
~~~

Test này tốn nhiều thời gian và dễ flake hơn; chỉ nên chọn một số critical journeys và dùng test accounts/sandbox.

### 16.3. Contract test

Ví dụ Booking API cam kết trả:

~~~json
{
  "id": "bk-411-example",
  "listingId": "listing-100",
  "status": "REQUESTED",
  "createdAt": "2026-01-15T09:00:00Z"
}
~~~

Contract test có thể kiểm tra tên fields, schema, HTTP status, error shape và backward compatibility. Nó không tự chứng minh MongoDB đã lưu đúng state, trừ khi test được thiết kế có thật persistence flow.

### 16.4. Smoke test sau deploy

Một vài thao tác read-only hoặc dữ liệu sandbox riêng:

- Health/readiness endpoint hoạt động.
- Kết nối database sẵn sàng.
- Một query an toàn trả dữ liệu dự kiến.
- Nếu được cho phép, một create/read/delete trên test tenant có cleanup đáng tin.

Không lấy bộ dữ liệu thật của khách hàng để chạy destructive smoke test.

## 17. Kiểm thử transaction MongoDB

### 17.1. Unit test có thể chứng minh gì?

Giả sử service chuyển trạng thái booking và ghi audit event trong cùng transaction. Unit test có thể chứng minh **khi repository phụ ném exception, service không tiếp tục các bước nghiệp vụ** theo logic mock.

Nhưng unit test **không thể chứng minh server rollback hai writes** như một MongoDB transaction thật.

### 17.2. Integration test cho commit/rollback

Một integration test transaction cần:

- MongoDB deployment hỗ trợ transactions, thường replica set hoặc sharded cluster.
- Spring transaction manager được cấu hình.
- Các operations thực sự chạy trong cùng session/transaction.
- Assertions xác minh không còn partial writes sau lỗi.
- Write concern/read concern và session semantics được biết.

Kịch bản:

~~~text
BEGIN TRANSACTION
  update booking -> CONFIRMED
  insert audit event
  force exception trước commit
ROLLBACK

Assert sau transaction:
  booking vẫn REQUESTED
  audit event chưa tồn tại
~~~

### 17.3. @Transactional không phải phép thử

Chỉ nhìn:

~~~java
@Transactional
public void confirmAndAudit(...) {
    // ...
}
~~~

không chứng minh transaction đang hoạt động đúng. Nếu không có MongoTransactionManager hoặc self-invocation/proxy setup sai, behavior có thể khác kỳ vọng.

Test transaction phải chạy **database thật** và xác minh persisted state sau success/failure.

### 17.4. Testcontainers single-node replica set

Container MongoDB được Testcontainers module cấu hình theo cách hỗ trợ replica-set connection cho test trong các versions phù hợp, giúp kiểm tra một số transaction semantics.

**Không** coi một test commit/rollback trên single-node replica set là bằng chứng ứng dụng xử lý được:

- Primary stepdown.
- Network partition.
- Multi-shard distributed transaction.
- Majority timeout.
- Replica-set recovery nhiều thành viên.

Những tình huống đó thuộc integration/system resilience test riêng.

## 18. Kiểm thử concurrency và optimistic locking

### 18.1. Vì sao test một thread chưa đủ?

Hai request đồng thời:

~~~text
Request A đọc booking REQUESTED
Request B đọc booking REQUESTED
A chuyển CONFIRMED, save
B chuyển CANCELLED, save
~~~

Nếu service dùng **read-modify-save** toàn document không có version check, có thể có **lost update**.

### 18.2. @Version

Spring Data MongoDB hỗ trợ optimistic locking:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

Với mapping/operations được hỗ trợ, version field có thể giúp phát hiện update trên một entity đã bị thay đổi kể từ lần đọc.

### 18.3. Phân chia test

- **Unit:** khi repository trả OptimisticLockingFailureException, service phản ứng/retry theo policy đúng.
- **Integration:** hai copies có cùng version được đọc, copy A save thành công, copy B save phải bị từ chối bằng optimistic locking.
- **E2E:** hai HTTP requests đồng thời không dẫn tới trạng thái sai, nếu đây là yêu cầu hệ thống.

Không kết luận “service an toàn với concurrency” chỉ vì có @Version trong source code.

### 18.4. Không lạm dụng sleep

Concurrency test:

~~~java
Thread.sleep(1000);
~~~

không bảo đảm hai operations chạm đúng thời điểm race. Dùng **CountDownLatch, CyclicBarrier hoặc CompletableFuture coordination** để kiểm soát thời điểm bắt đầu; kiểm tra kết quả có deadline và dữ liệu cuối cùng.

### 18.5. Nếu retry thì phải kiểm tra idempotency

Một timeout không luôn có nghĩa MongoDB chưa ghi. Client có thể nhận timeout sau khi write đã commit. Nếu API tự retry create booking bằng ID mới, có nguy cơ nhân đôi booking.

Thử bằng integration/E2E:

- Cùng **idempotency key** gửi hai lần.
- Server dùng unique constraint và reconciliation.
- Chỉ một booking được tạo.
- Response lần retry có semantics đã quy định.

Unit test có thể kiểm tra logic xử lý duplicate-key exception, nhưng server unique enforcement vẫn cần integration.

## 19. MongoDB-specific behaviors cần chọn đúng tầng

### 19.1. TTL index

MongoDB TTL cleanup là hoạt động **bất đồng bộ**, không xảy ra đúng tại mili giây document hết hạn.

Một test có:

~~~java
Thread.sleep(200);
assertFalse(repository.existsById(id));
~~~

có thể flake hoặc giả định sai. Nên:

- Test unit riêng để kiểm tra logic xác định expiry timestamp.
- Test integration index definition thực sự có **expireAfterSeconds** đúng.
- Nếu cần kiểm tra TTL deletion, dùng **eventually/polling với timeout đủ**, không đòi delete ngay lập tức.
- Không dùng TTL test như đo chính xác thời điểm xóa từng document.

### 19.2. Change Streams

Change Streams cần MongoDB deployment phù hợp, thường replica set hoặc sharded cluster.

Phân chia:

- Unit: xử lý event type và idempotency của consumer.
- Integration: mở change stream thật, ghi insert/update, đọc event, kiểm tra resume token.
- E2E: event từ MongoDB đi qua consumer và làm một business side effect có thể quan sát.

Không mock mọi event rồi tuyên bố đã kiểm tra tính đúng đắn của resumeAfter, oplog retention hoặc permissions.

### 19.3. Unique indexes

Unit: ứng dụng phản ứng đúng với duplicate-key exception.

Integration: server thực sự có unique index và từ chối duplicate data.

E2E: API trả **409 Conflict** hoặc response contract đã thống nhất khi gửi duplicate request.

### 19.4. JSON Schema validation

Unit: kiểm tra DTO/Bean Validation.

Integration: tạo MongoDB collection validator trong test database và cố ghi BSON sai; xác minh server từ chối.

E2E: API trả lỗi đầu vào phù hợp và không để lại document sai.

**Bean Validation** và **MongoDB server schema validation** là hai lớp khác nhau.

### 19.5. Read/write concerns

Unit test có thể xác nhận service chọn policy/cấu hình phù hợp khi được truyền qua abstraction.

Integration test cần database thật để kiểm tra behavior/timeout cơ bản.

Resilience/system test mới thích hợp để đánh giá majority write, lag, read preference và election/failover dưới topology đại diện.

### 19.6. Aggregation

Unit test thích hợp cho business transformation sau khi lấy kết quả.

Integration test cần kiểm tra:

- $match/$group/$lookup semantics.
- Empty result và null/missing fields.
- Numeric BSON types.
- Array pipelines.
- Collation, sort và pagination.

Nếu aggregation output đổ vào collection khác bằng $merge/$out, test phải ghi nhận side effects và cleanup.

### 19.7. Index và query performance

Integration test có thể kiểm tra index có tồn tại và explain plan trong môi trường phù hợp. Nhưng một test với 50 documents không chứng minh index tối ưu ở production với 50 triệu documents.

Latency p95/p99, throughput và saturation cần **load/performance tests** trên dataset/topology đủ đại diện.

## 20. Test fixtures: dữ liệu nhỏ nhưng có chủ đích

### 20.1. Fixture đơn giản

~~~java
static BookingDocument booking(
        String id,
        String tenantId) {
    return new BookingDocument(
        id,
        tenantId,
        "listing-100",
        new GuestInfo("Lan"),
        Instant.parse("2026-01-15T09:00:00Z")
    );
}
~~~

Một fixture tốt:

- Có giá trị mặc định hợp lệ.
- Cho phép override những field test cần biến đổi.
- Không dùng dữ liệu production thật.
- Đọc tên là hiểu tình huống.
- Không tạo tác động ngoài phạm vi test.

### 20.2. Đặt dữ liệu phản ví dụ

Để test tenant isolation, cần ít nhất:

~~~text
booking-A: tenant-001
booking-B: tenant-002
~~~

Nếu test chỉ có document tenant-001, một query thiếu tenant filter vẫn có thể PASS mà không phát hiện nguy cơ.

Để test array $elemMatch, cần document có hai phần tử **mỗi phần tử thỏa một điều kiện khác nhau**, để phát hiện query match sai khác phần tử.

### 20.3. Cố định thời gian

Tránh:

~~~java
assertEquals(
    Instant.now(),
    booking.getCreatedAt()
);
~~~

Hai lần gọi now có thể lệch mili giây/nanosecond. Dùng **Clock.fixed** ở unit test, hoặc assert khoảng thời gian hợp lý khi kiểm tra integration thật.

### 20.4. Random IDs có giới hạn

Random UUID tiện tránh trùng dữ liệu, nhưng một test muốn assert ID cụ thể nên:

- Inject ID generator, hoặc
- Chỉ assert shape/prefix, hoặc
- Cung cấp deterministic ID qua fixture.

Không phụ thuộc thứ tự ngẫu nhiên hoặc timestamp tường để quyết định PASS/FAIL.

### 20.5. Không tái sử dụng một dataset mutable giữa mọi tests

Nếu Test A tạo booking và Test B ngầm dựa vào booking đó, kết quả phụ thuộc thứ tự chạy. Khi chạy parallel hoặc thay test order sẽ flake.

Mỗi test nên tự tạo dữ liệu cần thiết trong môi trường cô lập, hoặc có fixture/reset contract rõ ràng.

## 21. Quản lý vòng đời MongoDB test database

### 21.1. Testcontainers lifecycle

~~~text
Start container
      |
Create MongoDB test connection
      |
Prepare fixture per test
      |
Run assertions
      |
Cleanup test data / container stops
~~~

Để giảm runtime có thể share container giữa tests theo chiến lược phù hợp, nhưng sharing tăng yêu cầu tránh data leakage và test interference.

### 21.2. @BeforeEach cleanup

Trên container **hoàn toàn cô lập**, xóa dữ liệu của collection test trước mỗi case là cách đơn giản:

~~~java
@BeforeEach
void clean() {
    template.getCollection(
        "booking_requests_411"
    ).deleteMany(new Document());
}
~~~

Đây **không phải** một pattern an toàn khi test kết nối production hoặc staging có dữ liệu chung. Phải có guardrails xác định URI thật sự trỏ tới test environment.

### 21.3. Database name theo test run

Với CI song song, có thể dùng database riêng cho mỗi job/run:

~~~text
mongo_test_411_run_123
mongo_test_411_run_124
~~~

Hoặc container riêng với filesystem data độc lập. Lựa chọn theo chi phí và khả năng bảo đảm isolation.

### 21.4. Tác dụng của @DirtiesContext

**@DirtiesContext** yêu cầu Spring test framework tạo context mới theo điều kiện, có thể rất tốn thời gian. Không dùng nó như một lệnh cleanup database mặc định. Nếu context/beans không thay đổi, reset dữ liệu test đúng scope thường hiệu quả hơn.

### 21.5. Parallel execution

Hai tests có chung database và cùng gọi:

~~~java
deleteMany(new Document());
~~~

có thể xóa dữ liệu của nhau nếu chạy song song. Chọn một trong:

- Separate containers/databases/collections per test.
- Controlled test serialization.
- Unique fixture keys và không global cleanup.

Không chỉ tăng số worker CI mà quên data isolation.

## 22. Negative tests quan trọng hơn chỉ happy path

Một test suite tốt không chỉ hỏi “tạo booking thành công không?”.

### 22.1. Validation

- Missing tenantId.
- Blank listingId.
- Blank guestName.
- Invalid JSON.
- Oversized fields.
- Unknown enum status.

### 22.2. Authorization

- Tenant A đọc booking của tenant B.
- Tenant A confirm booking của tenant B.
- User không xác thực.
- User chỉ có quyền đọc cố gắng ghi.

Trong mô hình lab, header tenant chỉ minh họa; với ứng dụng thật phải test authentication/authorization ở layer bảo mật chính thức.

### 22.3. Data integrity

- Duplicate idempotency key.
- Duplicate _id.
- Invalid BSON type.
- Missing required fields nếu có validator.
- Currency/Decimal128 conversion.
- Timestamp timezone/precision.

### 22.4. State transitions

- REQUESTED → CONFIRMED.
- CONFIRMED → CONFIRMED (idempotent hoặc conflict theo contract).
- CANCELLED → CONFIRMED bị từ chối.
- Không có booking → 404.
- Conflicting concurrent updates.

### 22.5. Reliability

- MongoDB temporarily unavailable.
- Driver server selection timeout.
- Connection pool exhaustion.
- Retryable write error.
- Transaction conflict.
- Primary stepdown (chỉ trên topology test phù hợp).

Đừng dùng một mock ném RuntimeException bất kỳ rồi xem như đã kiểm tra được chính xác MongoDB error labels/retry semantics.

## 23. Failure injection: chọn tầng phù hợp

### 23.1. Ở unit test

Mock repository ném:

~~~java
when(repository.save(any()))
    .thenThrow(
        new IllegalStateException("Simulated persistence failure")
    );
~~~

Test này giúp kiểm tra service/logging/exception translation theo chính sách. Nó **không tái tạo chính xác một MongoDB driver exception** nếu loại exception giả không phù hợp.

### 23.2. Ở integration test

Có thể mô phỏng server constraints thật bằng:

- Duplicate unique key.
- BSON type khác.
- Schema validator.
- Document size limit trong test có kiểm soát.
- Transaction rollback.
- Query maxTimeMS trên workload test phù hợp.

Không ép server test vào tình trạng nghẽn/khóa vô thời hạn nếu không có timeout và cleanup.

### 23.3. Ở resilience/system test

Các kịch bản như:

- Primary stepdown.
- Mất một replica member.
- Network delay/partition.
- Disk pressure.
- Sharded migration/failover.

cần hạ tầng/phép thử chuyên biệt và guardrails. Không làm trên production chỉ để tăng coverage.

### 23.4. Tại sao retry logic cần end-to-end viewpoint?

Một request có thể:

~~~text
Client gửi create
MongoDB commit
Network timeout trước response
Client retry
~~~

Nếu create không có idempotency, hệ thống có thể tạo hai booking. Unit test kiểm tra retry policy, integration test xác minh unique key/transaction, E2E test xác minh hai HTTP requests cùng idempotency key có observable outcome đúng.

## 24. Test data chứa PII và security

### 24.1. Không copy dữ liệu thật vào CI tùy tiện

Production MongoDB có thể lưu tên, số điện thoại, thông tin tài chính và địa chỉ. Dump nguyên bộ data vào CI để “giống production” có rủi ro:

- Lộ PII/secrets.
- Đội phát triển không có quyền xem dữ liệu đó.
- Retention/backups của test database không được quản lý.
- Logs chứa document thật.

Ưu tiên synthetic fixtures hoặc dữ liệu đã xử lý theo policy và được phê duyệt.

### 24.2. Test credentials

Database test user nên có quyền giới hạn ở test deployment. Không dùng production root URI trong:

~~~text
application-test.yml
GitHub Actions secrets
developer laptops
CI debug logs
~~~

Nếu có secret manager, quản lý test credentials theo scope riêng và rotation policy.

### 24.3. Không log toàn BSON nhạy cảm

Khi assertion lỗi, nên log những fields cần debug và che PII. Không in raw MongoDB URI có password hay dump toàn bộ booking document vào public CI artifacts.

## 25. CI pipeline: test nào chạy khi nào?

### 25.1. Một pipeline mẫu

~~~text
Developer push / pull request
          |
          v
     Compile + static checks
          |
          v
        Unit tests
          |
          v
  Persistence integration tests
    (Testcontainers MongoDB)
          |
          v
   Controller/API contract tests
          |
          v
     Service-level E2E
          |
          v
      Build/deploy review
          |
          v
   Staging smoke/system E2E
~~~

Thứ tự có thể khác theo thời gian chạy và chi phí. Mục tiêu là:

- Fail nhanh khi lỗi thuần logic.
- Có evidence về MongoDB thật trước deploy.
- Chạy E2E quan trọng ở mức phù hợp.
- Không biến mỗi PR thành một test suite kéo dài hàng giờ không cần thiết.

### 25.2. Tại pull request

Thông thường:

- Toàn bộ unit tests.
- Integration tests quan trọng.
- Controller slices/contract tests.
- Một số service-level E2E tests.

Nếu quá chậm, tối ưu isolation, parallelism, fixture scope và chia pipelines hợp lý; không xóa mọi integration test để rút thời gian một cách mù quáng.

### 25.3. Nightly hoặc trước release

Có thể mở rộng:

- Nhiều MongoDB versions được hỗ trợ.
- Migration fixtures từ schema cũ.
- Dữ liệu lớn hơn.
- Full E2E journeys.
- Replica-set failover tests.
- Load/performance smoke.
- Security scanning.

### 25.4. Sau deploy

Smoke tests phải dùng:

- Health/readiness.
- Test tenant riêng nếu cần write.
- Tài khoản được phép.
- Deadline và cleanup.
- Alerts nếu production behavior sai.

Không tạo booking thật cho khách hàng bằng smoke test.

## 26. Test matrix theo môi trường

| Loại test | Local developer | Pull request CI | Nightly/staging | Production |
| --- | --- | --- | --- | --- |
| Unit | Luôn | Luôn | Có | Không cần chạy trên production |
| @WebMvcTest | Thường xuyên | Thường xuyên | Có | Không |
| @DataMongoTest + container | Có Docker | Nên có | Có | Không |
| HTTP + MongoDB container E2E | Có Docker | Critical paths | Full paths | Không |
| Schema migration rehearsal | Có thể | Nếu thay schema | Nên có | Chỉ migration được phê duyệt |
| Failover/resilience | Lab chuyên biệt | Tùy hạ tầng | Nên có khi phù hợp | Không tự gây sự cố |
| Load/performance | Quy mô nhỏ | Smoke | Staging đại diện | Chỉ có kế hoạch được phê duyệt |
| Smoke after deploy | Không cần | Không | Có | Read-only/test-tenant an toàn |

Mục tiêu không phải càng nhiều E2E càng tốt, mà là **bao phủ đúng rủi ro ở tầng có thể chứng minh**.

## 27. Đánh giá chất lượng test suite

### 27.1. Code coverage không đồng nghĩa confidence

Một service có 95% line coverage nhưng mọi repository đều mock có thể vẫn sai tên BSON field trong toàn bộ queries.

Ngược lại, một integration test nhỏ xác minh mapping và unique index có thể bắt được lỗi deployment nghiêm trọng mà nhiều mock tests bỏ sót.

### 27.2. Mutation testing

Nếu có thể, dùng mutation testing ở unit layer để kiểm tra tests có phát hiện khi điều kiện đổi:

~~~text
if (status == CANCELLED)
~~~

thành:

~~~text
if (status == CONFIRMED)
~~~

Nếu test vẫn PASS, rule coverage có thể yếu. Mutation testing là kỹ thuật bổ sung, không thay integration tests.

### 27.3. Flaky tests

Các nguồn thường gặp:

- Test phụ thuộc thứ tự.
- Shared mutable fixture.
- Sleep dựa trên timing.
- TTL/background jobs không deterministic.
- MongoDB container chưa sẵn sàng.
- Random ports, network và external services.
- CI resource contention.
- Test dùng Instant.now và so bằng equality.

Sửa flakiness bằng root cause, isolation, explicit readiness và bounded eventual assertions. Không tự retry test 10 lần rồi báo PASS mà che giấu lỗi.

### 27.4. Test ownership

Mỗi failed test nên gợi ý được:

- Lỗi thuộc business logic, mapping, database hoặc HTTP?
- Log/test evidence nằm ở đâu?
- Ai chịu trách nhiệm sửa?
- Có dữ liệu test nào bị rò sang case khác?

Một suite lớn nhưng fail không chẩn đoán được có thể làm chậm nhóm hơn một suite nhỏ thiết kế tốt.

## 28. Mẫu kế hoạch kiểm thử cho một tính năng mới

### 28.1. Requirement

> “Booking có thể được xác nhận nếu còn REQUESTED. Booking đã CANCELLED phải bị từ chối. Không tenant nào truy cập được booking của tenant khác.”

### 28.2. Unit cases

1. REQUESTED → CONFIRMED.
2. CANCELLED → IllegalStateException.
3. CONFIRMED → idempotent (không save lại).
4. Missing booking → NoSuchElementException.
5. Tenant/ID blank → IllegalArgumentException.
6. Không gọi repository.save khi validation/state fail.

### 28.3. Integration cases

1. Lưu đúng tenant_id/listing_id/guest.full_name.
2. findByIdAndTenantId trả đúng tenant, không trả tenant khác.
3. Duplicate _id bị server từ chối.
4. Index/JSON schema quan trọng được verify nếu deployment sử dụng.
5. Transaction/optimistic locking behavior nếu feature yêu cầu.

### 28.4. Controller slice cases

1. POST trả 201 + JSON DTO.
2. Missing required header trả 400.
3. Invalid body trả error đúng contract.
4. Service báo missing → 404.
5. Service báo conflict → 409.

### 28.5. E2E cases

1. Create → Get → Confirm → Get, kiểm persisted state.
2. Cross-tenant GET không trả dữ liệu.
3. Một negative business flow quan trọng, ví dụ confirm đã hủy trả 409.

### 28.6. Ngoài ba tầng

1. Load test nếu cần SLO concurrency/throughput.
2. Failover test nếu yêu cầu HA.
3. Restore drill nếu cần bảo đảm RTO/RPO.
4. Security test cho principal/roles thật.

## 29. Những sai lầm thường gặp

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Mock MongoRepository rồi gọi đó là integration test | Không thực sự kiểm tra database | @DataMongoTest + real MongoDB |
| Dùng @WebMvcTest rồi gọi full E2E | Service/DB đều giả | Phân loại là controller slice |
| Chỉ có E2E cho mọi nhánh logic | Chậm, khó khoanh lỗi | Tách nhiều unit cases |
| Chỉ có unit tests | Không thấy mapping/index/server errors | Thêm persistence integration |
| Integration trỏ localhost developer tùy ý | Khó tái lập, phụ thuộc dữ liệu | Container cô lập |
| Test tự kết nối URI production | Nguy cơ mất dữ liệu | Fail-fast + network/secret separation |
| Xóa toàn bộ collection trước mỗi test trên shared DB | Xóa dữ liệu test khác | Separate database/container |
| Test phụ thuộc thứ tự execution | Flaky khi parallel | Fixture mỗi test độc lập |
| Dùng Thread.sleep cố định cho TTL | TTL bất đồng bộ | Eventual assertion có timeout |
| So Instant.now bằng exact equality | Nondeterministic | Clock.fixed |
| Dùng save để test duplicate _id | Save có thể replace | Dùng insert |
| Assert annotation @Indexed là đủ | Server có thể chưa tạo index | Kiểm tra index thật |
| Không seed tenant B | Không phát hiện thiếu tenant filter | Negative fixture cross-tenant |
| Chỉ test one-item array | Không thấy $elemMatch issue | Seed các elements phản ví dụ |
| Test field Java nhưng không inspect raw BSON | Bỏ qua @Field alias/type | Raw Document assertions |
| Không kiểm lỗi/timeouts trong E2E | Happy path che failure paths | Negative/resilience tests |
| Test transaction với standalone không hỗ trợ | Kết luận sai | Replica set test environment |
| Test single-node RS rồi tuyên bố đã test failover | Không có election đa thành viên | Multi-node resilience test |
| Assert p99 trong 10 requests | Không có độ tin cậy | Dedicated load test |
| Dùng production PII làm fixture | Vi phạm privacy/security | Synthetic/anonymized data |
| Hardcode MongoDB root secret vào test | Lộ quyền cao | Least-privilege test credentials |
| Retry failed tests vô hạn | Che flakiness | Sửa root cause |
| Chỉ nhìn line coverage | Coverage không nói integration quality | Mapping/constraints tests |
| Dùng @DirtiesContext để cleanup DB mọi case | Suite chậm và vẫn có thể để dữ liệu | Reset đúng scope |
| Không ghi version MongoDB/image | Test khác production không được nhận ra | Pin version/BOM |
| Không gắn tên test với behavior | Fail khó chẩn đoán | Given–When–Then và clear names |

## 30. Checklist thực hành

### 30.1. Trước khi viết test

- Xác định behavior cần chứng minh.
- Chọn tầng thấp nhất **có khả năng chứng minh behavior thật**.
- Tách database business rules khỏi persistence adapters khi hợp lý.
- Định nghĩa BSON/API contract.
- Xác định dữ liệu positive/negative/edge cases.

### 30.2. Unit

- Không cần Spring context nếu không cần.
- Mock các I/O dependencies.
- Clock/ID generator deterministic khi cần.
- Assert behavior và side effects/không side effects.
- Không phụ thuộc implementation details không cần thiết.

### 30.3. Integration

- MongoDB server thật, version gần production.
- Test database cô lập.
- Assert raw BSON field names/types.
- Test index/unique/schema/query semantics.
- Test null/missing/nested arrays.
- Transaction/concurrency tests trên deployment hỗ trợ.
- Cleanup và parallel execution an toàn.

### 30.4. E2E

- Ghi rõ điểm bắt đầu/kết thúc.
- Real HTTP server nếu mục tiêu là network-level HTTP.
- Kiểm response status/body và persisted state.
- Có negative authorization path.
- Stub external dependencies đúng mục tiêu, không giả mọi thứ.
- Test data/credentials riêng.
- Không sử dụng E2E để đo p99 capacity nếu không có load harness.

### 30.5. CI

- Unit chạy thường xuyên và nhanh.
- Integration không bị tắt âm thầm.
- E2E critical paths chạy trước release.
- Artifacts ghi test environment/version.
- Flakiness có owner và xử lý root cause.
- Test credentials không xuất hiện trong logs.

## 31. Bài tập thực hành

### Bài 1 — Nhận diện tầng

Một test gọi BookingService.confirmBooking với Mockito repository. Đây là unit, integration hay E2E? Điều gì nó chưa kiểm tra?

### Bài 2 — Persistence thật

Một test khởi động MongoDB Testcontainer, gọi repository.save rồi đọc raw BSON Document. Hãy phân loại và nêu vì sao.

### Bài 3 — Controller slice

@WebMvcTest + MockMvc + @MockitoBean BookingService thuộc loại nào? Tại sao không gọi nó là full E2E?

### Bài 4 — HTTP thật

Một test dùng @SpringBootTest(RANDOM_PORT), TestRestTemplate và MongoDB thật. Nó kiểm chứng những boundaries nào?

### Bài 5 — Test pyramid

Một tính năng có 20 business validation rules, một repository query và hai user journeys. Bạn sẽ phân phối các tests thế nào để vừa nhanh vừa đáng tin?

### Bài 6 — Business rule

Viết unit test đảm bảo CANCELLED không chuyển sang CONFIRMED và repository.save không được gọi.

### Bài 7 — Fixed time

Thay Instant.now() trực tiếp trong service bằng Clock injection. Viết assertion createdAt ở một thời điểm cố định.

### Bài 8 — Validation negative

Kiểm thử tenantId rỗng trong BookingService. Vì sao verifyNoInteractions(repository) là một assertion có giá trị?

### Bài 9 — Mockito không đủ

Mock repository trả kết quả đúng cho findByIdAndTenantId. Vì sao test này không phát hiện việc MongoDB thực lưu tên field tenant_id?

### Bài 10 — BSON mapping

Viết integration test lưu BookingDocument rồi assert raw Document có tenant_id, listing_id và guest.full_name.

### Bài 11 — Duplicate _id

Tại sao cần dùng repository.insert hai lần thay vì save hai lần khi kiểm MongoDB duplicate _id?

### Bài 12 — Compound unique index

Thiết kế index unique theo tenant_id và request_key. Viết negative test trùng cả hai và positive test khác tenant_id.

### Bài 13 — ObjectId conversion

Giải thích rủi ro khi Java @Id String có giá trị trông giống ObjectId. Integration test nên assert điều gì ở BSON thật?

### Bài 14 — Decimal128

Một domain dùng BigDecimal tiền thuê. Viết kế hoạch test Java → BSON Decimal128 → Java, với giá trị có phần thập phân.

### Bài 15 — Array semantics

Seed một document có bedroom 10 m² và kitchen 30 m². Chứng minh query dotted có thể match cả hai điều kiện ở hai elements, rồi sửa bằng $elemMatch.

### Bài 16 — Null/missing

Viết cases cho guest field missing, null và guest.full_name empty. Vì sao không được coi cả ba là cùng business state?

### Bài 17 — API contract

POST /api/bookings phải trả 201, id, status và createdAt. Viết controller slice test với MockMvc.

### Bài 18 — 404/409

Thiết kế test cho booking không tồn tại và booking bị hủy. Chỉ rõ exception mapping và HTTP status.

### Bài 19 — E2E flow

Mô tả/viết test Create → Get → Confirm → Get và xác minh MongoDB status cuối là CONFIRMED.

### Bài 20 — Tenant isolation

Tạo một booking tenant-001; truy cập bằng tenant-002 phải bị từ chối hoặc không trả dữ liệu. Nêu tầng nào test policy và tầng nào test full HTTP enforcement.

### Bài 21 — Authentication thật

Vì sao header X-Lab-Tenant trong ví dụ không thể dùng làm cơ chế bảo mật production? Thiết kế test với security principal đã được server xác thực.

### Bài 22 — Transaction rollback

Một transaction cập nhật booking và insert audit, sau đó phát sinh exception. Bạn cần loại test/deployment nào để khẳng định không có partial writes?

### Bài 23 — @Version

Hai copies cùng version được đọc; A save trước, B save sau. Thiết kế integration test optimistic locking và expected exception.

### Bài 24 — TTL

Vì sao test TTL bằng sleep 100 ms thường flake? Nêu phương án test index definition và asynchronous cleanup.

### Bài 25 — Change Stream

Phân chia test cho event handler, real change-stream cursor và luồng consumer → business side effect.

### Bài 26 — Testcontainers

Phân tích lợi ích của pin MongoDB image version, tự tạo replica-set URI và không dựa vào MongoDB local trên laptop.

### Bài 27 — Test data isolation

Hai tests chạy parallel cùng xóa toàn collection. Hãy đề xuất cách cô lập database/collections hoặc điều phối test.

### Bài 28 — @DirtiesContext

Vì sao không dùng @DirtiesContext như giải pháp mặc định để reset MongoDB giữa mọi tests?

### Bài 29 — Production protection

Một integration test có deleteMany({}) trên collection của lab nhưng URI vô tình trỏ production. Thiết kế guardrails ở CI/secret/network/test runtime.

### Bài 30 — Unknown fields

Spring Data đọc một document cũ có field chưa có trong Java class rồi save lại. Loại integration test nào có thể phát hiện nguy cơ mất field đó?

### Bài 31 — Retry và idempotency

Client timeout sau khi MongoDB đã commit create. Thiết kế unit/integration/E2E tests chứng minh retry không tạo duplicate booking.

### Bài 32 — Performance không phải unit

Vì sao không kết luận MongoDB đáp ứng 500 RPS p99 200 ms từ 10 unit tests và một @DataMongoTest trên 20 documents?

### Bài 33 — Resilience

Bạn cần chứng minh driver phục hồi sau primary stepdown. Single-node MongoDBContainer có đủ không? Cần topology và test controls nào?

### Bài 34 — Test quality

Line coverage đạt 95% nhưng production lỗi do index unique không tồn tại. Bạn bổ sung gì vào test suite và release pipeline?

### Bài 35 — CI

Đề xuất pipeline gồm compile, unit, integration, controller slice/contract, service E2E, staging smoke và nightly resilience. Mỗi tầng có mục tiêu gì?

### Bài 36 — End-to-end plan

Cho hệ thống booking của 20 tenants, 5 triệu documents, có yêu cầu optimistic locking, idempotency key và audit trail: lập test matrix đầy đủ **unit/integration/E2E** và ngoài ba tầng cho hiệu năng/khôi phục.

## 32. Tài liệu tham khảo

- Spring Boot Reference — [Testing](https://docs.spring.io/spring-boot/reference/testing/index.html).
- Spring Boot Reference — [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html).
- Spring Boot Reference — [Test Slices](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-tests).
- Spring Data MongoDB — [Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html).
- Spring Data MongoDB — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html).
- Spring Data MongoDB — [Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html).
- Spring Data MongoDB — [Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking).
- JUnit Jupiter — [User Guide](https://junit.org/junit5/docs/current/user-guide/).
- Mockito — [Official site](https://site.mockito.org/).
- Testcontainers Java — [MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/).
- Testcontainers Java — [JUnit 5 Integration](https://java.testcontainers.org/test_framework_integration/junit_5/).
- MongoDB Manual — [Documents](https://www.mongodb.com/docs/manual/core/document/).
- MongoDB Manual — [Indexes](https://www.mongodb.com/docs/manual/indexes/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- MongoDB Manual — [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/).
- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/).
- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).

**Kết luận:** Với ứng dụng MongoDB, phân chia test theo **ranh giới thực sự cần chứng minh**: **unit tests** xác minh business rules nhanh và cô lập bằng JUnit/Mockito; **integration tests** dùng MongoDB thật để kiểm tra Spring Data mapping, BSON, queries, indexes, unique constraints và transactions; **end-to-end tests** kiểm tra một hành trình từ HTTP client qua Spring Boot tới MongoDB và trạng thái trả về. **@WebMvcTest** là controller slice, không phải full E2E; **mock repository** không chứng minh database behavior; **Testcontainers single-node replica set** không chứng minh HA/failover nhiều node. Một test suite đáng tin cần **fixtures độc lập, clock deterministic, negative scenarios, tenant isolation, schema evolution checks, bảo vệ môi trường test và CI hợp lý**. Mục tiêu không phải viết càng nhiều E2E càng tốt, mà là **phát hiện lỗi ở tầng phù hợp với chi phí nhỏ nhất, đồng thời có đủ bằng chứng rằng MongoDB và toàn bộ luồng người dùng hoạt động đúng**.
