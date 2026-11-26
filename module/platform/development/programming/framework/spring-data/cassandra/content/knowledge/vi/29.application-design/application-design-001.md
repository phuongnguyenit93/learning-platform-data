# Phân chia Controller, Service, Repository và lớp chuyển đổi DTO

Khi phát triển ứng dụng Java với **Spring Data Cassandra**, việc gọi `repository.save(entity)` từ một REST Controller có vẻ ngắn gọn. Nhưng cách viết này nhanh chóng gây khó khăn khi hệ thống phải xác thực tenant, tính partition key, kiểm soát dữ liệu đầu vào, chọn consistency level, xử lý retry hoặc thay đổi hợp đồng API mà không làm hỏng schema Cassandra.

Một cách tổ chức có trách nhiệm rõ ràng là **Controller → Service → Repository**, với **lớp chuyển đổi DTO (Mapper)** nằm ở biên giữa HTTP và mô hình ứng dụng. Controller xử lý giao thức web; Service giữ quy tắc nghiệp vụ và điều phối; Repository truy cập dữ liệu theo khóa và câu truy vấn; Mapper chuyển cấu trúc dữ liệu giữa các lớp. Riêng Cassandra, ranh giới này phải bảo vệ những quyết định về **partition key, clustering key, denormalization, consistency và paging** thay vì che giấu chúng sau các phương thức CRUD chung chung.

Bài thuộc chương **Thiết kế ứng dụng** của module **SPRING_DATA_CASSANDRA**. Chúng ta xây dựng một API lưu và đọc **sự kiện của tenant theo ngày**, sử dụng entity mapping, `CassandraRepository`, DTO, Service, Controller và các thành phần mở rộng như `CassandraTemplate`/`CqlSession` khi cần. Ví dụ định hướng Spring Boot 3.x, Java 17+ và Spring Data Cassandra 4.x; cần đối chiếu phiên bản dependency và hoàn thiện import/boilerplate phù hợp dự án thật.

## 1. Bốn trách nhiệm không nên trộn

| Thành phần | Nên chịu trách nhiệm | Không nên chịu trách nhiệm |
| --- | --- | --- |
| **Controller** | HTTP route, request/response, bean validation, lấy identity đã xác thực, mã trạng thái HTTP | Xây CQL, đoán partition key, lưu entity trực tiếp và tự retry database |
| **Service** | Quy tắc nghiệp vụ, xác định bucket UTC, orchestration, kiểm soát idempotency, chuyển trạng thái và chính sách lỗi | Truy cập trực tiếp `HttpServletRequest` nếu không cần; phụ thuộc chi tiết JSON |
| **Repository / data access** | CQL hợp lệ theo partition key, mapping entity, chuẩn bị truy vấn và truyền lựa chọn đọc/ghi xuống driver | Quyết định user có quyền tenant nào hoặc trả HTTP status |
| **DTO Mapper** | Đổi request DTO thành command, kết quả ứng dụng thành response DTO, định dạng/phiên bản public API | Gọi repository, kiểm tra quyền, phát side effect hoặc đặt random ID không có quy tắc |

Một luồng ghi có thể mô tả:

~~~text
HTTP POST + JWT
       |
       v
EventController -----> EventDtoMapper.toCommand(request)
       |                       |
       |                 CreateEventCommand
       v                       |
EventService <------------------+
       |
       +-- kiểm tra business rule
       +-- tính event_day theo UTC
       +-- tạo EventKey đầy đủ
       v
EventRepository.save(EventEntity)
       |
       v
Cassandra replicas
       |
       v
EventService -> EventView -> DTO Mapper -> HTTP response
~~~

**Nguyên tắc phụ thuộc:** lớp web phụ thuộc vào service/mapper; service phụ thuộc vào repository và mô hình ứng dụng; repository phụ thuộc Cassandra mapping. Lớp dữ liệu không biết gì về HTTP response, cookie hay status code.

## 2. Bắt đầu từ use case và access pattern, không phải từ Controller

Ví dụ API cần hai hành vi:

1. **Ghi một sự kiện** cho tenant đang xác thực; client cung cấp `eventId`, `occurredAt`, `eventType` và `payload`.
2. **Liệt kê sự kiện gần nhất** của tenant trong một ngày, tối đa 50 hàng ở ví dụ cơ bản.

Hợp đồng minh họa:

~~~http
POST /api/v1/events
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "eventId": "550e8400-e29b-41d4-a716-446655440000",
  "occurredAt": "2026-11-25T08:15:00Z",
  "eventType": "ORDER_PAID",
  "payload": "{\"orderRef\":\"O-1001\"}"
}
~~~

Và một GET:

~~~http
GET /api/v1/events?day=2026-11-25
Authorization: Bearer <access-token>
~~~

**Không đưa `tenantId` vào request body để mặc nhiên tin tưởng.** Tenant được suy ra từ danh tính đã xác thực/ủy quyền (hoặc được kiểm tra quyền rõ ràng nếu API cho phép truy cập nhiều tenant). Service chịu trách nhiệm không cho người dùng đọc/ghi dữ liệu ngoài phạm vi tenant được cấp.

Giữ `eventId` ổn định giữa những lần client gửi lại cùng lệnh giúp tránh sinh hàng trùng do ID mới. Tuy nhiên **cùng primary key không tự chứng minh request idempotent hoàn toàn**: một payload khác với cùng ID có thể upsert đè dữ liệu cũ, và tác dụng phụ ngoài Cassandra vẫn cần được bảo vệ riêng.

## 3. Bảng Cassandra phải khớp đúng hai use case

Chọn partition theo **tenant và ngày UTC**, clustering theo thời điểm sự kiện giảm dần:

~~~sql
CREATE KEYSPACE IF NOT EXISTS activity_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS activity_ks.events_by_tenant_day (
    tenant_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (
    occurred_at DESC, event_id DESC
);
~~~

Giải thích:

- **Partition key** là `(tenant_id, event_day)`: hai giá trị phải được bind khi đọc lịch sử một ngày.
- **Clustering columns** là `(occurred_at, event_id)`: xác định hàng và thứ tự bên trong partition; `event_id` xử lý các sự kiện trùng thời điểm.
- `event_type` và `payload` là cột thường. Với danh sách nhiều hàng, có thể chỉ chọn một projection nhỏ thay vì đọc payload dài.
- RF=3, tên datacenter `dc1` chỉ minh họa; production cần thiết kế replication theo topology thật.

GET trên chỉ cần một partition:

~~~sql
SELECT tenant_id, event_day, occurred_at, event_id,
       event_type, payload
FROM activity_ks.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT 50;
~~~

Nếu tương lai cần tìm sự kiện **theo loại trong toàn tenant**, truy vấn `WHERE event_type = ?` không tự trở thành hiệu quả. Phải xem xét **bảng đọc khác** thiết kế theo truy vấn, index phù hợp hoặc hệ thống tìm kiếm riêng. **Service không nên che một truy vấn scan toàn cluster sau tên method `findAllByType()`.**

Lựa chọn ngày làm bucket cũng không mặc định phù hợp mọi tenant: cần đo số row/byte, throughput đỉnh, tombstone và hot partition; nếu một ngày quá lớn thì chia giờ/shard với chi phí truy vấn nhiều bucket.

## 4. Cấu trúc package gọn, vẫn có ranh giới rõ ràng

Một cấu trúc module minh họa:

~~~text
com.example.activity
├── api
│   ├── EventController.java
│   ├── EventDtoMapper.java
│   ├── CreateEventRequest.java
│   ├── EventResponse.java
│   └── ApiExceptionHandler.java
├── application
│   ├── EventService.java
│   ├── CreateEventCommand.java
│   └── EventView.java
├── persistence
│   ├── EventEntity.java
│   ├── EventKey.java
│   └── EventRepository.java
└── security
    └── AppPrincipal.java
~~~

Đây là **mô hình gợi ý**, không yêu cầu tạo các file này trong nhiệm vụ viết bài. Có thể chia tiếp thành `port`/`adapter` ở dự án lớn, nhưng không cần dựng kiến trúc quá nhiều interface cho một API đơn giản.

**Ranh giới quan trọng hơn tên package:** request DTO không đi xuyên repository, persistence entity không xuất hiện trong JSON public API, và controller không trực tiếp gọi `CqlSession`.

## 5. DTO của HTTP: độc lập với @Table và primary key

Request DTO thể hiện contract mà client gửi, với validation ở biên:

~~~java
package com.example.activity.api;

import java.time.Instant;
import java.util.UUID;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateEventRequest(
    @NotNull UUID eventId,
    @NotNull Instant occurredAt,
    @NotBlank String eventType,
    @Size(max = 8192) String payload
) {}
~~~

Response DTO:

~~~java
package com.example.activity.api;

import java.time.Instant;
import java.util.UUID;

public record EventResponse(
    UUID eventId,
    Instant occurredAt,
    String eventType,
    String payload
) {}
~~~

Các record trên **không có `@Table`, `@PrimaryKeyColumn`, `@Column`**. Đổi tên JSON field, ẩn cột nội bộ hay thay version API sẽ không bắt buộc sửa schema Cassandra.

Validation `@NotNull` và `@NotBlank` bắt lỗi hình dạng đầu vào. **Nó chưa kiểm tra hết business rule** như mốc sự kiện nằm trong khoảng cho phép, loại event hợp lệ, giới hạn payload sau mã hóa, hoặc tenant có quyền ghi. Những quy tắc đó thuộc service và cơ chế phân quyền.

Với JSON payload thực tế, có thể chọn `JsonNode` hay một DTO riêng thay vì chuỗi JSON lồng trong chuỗi. Bài dùng `String` để giữ ví dụ mapping CQL `text` đơn giản.

## 6. Command và kết quả ở tầng application

Tránh để `EventService` nhận thẳng `HttpServletRequest` hoặc phụ thuộc vào lớp Spring MVC. Một command/value object thuần Java:

~~~java
package com.example.activity.application;

import java.time.Instant;
import java.util.UUID;

public record CreateEventCommand(
    UUID eventId,
    Instant occurredAt,
    String eventType,
    String payload
) {}

public record EventView(
    UUID eventId,
    Instant occurredAt,
    String eventType,
    String payload
) {}
~~~

Để biên dịch, đặt **mỗi public record vào một file Java riêng**. `CreateEventCommand` là dữ liệu đã được Controller nhận và chuyển thành yêu cầu nghiệp vụ; `EventView` là mô hình kết quả service trả ra. Chúng không cần annotation của Cassandra hay HTTP.

Tại sao tạo thêm kiểu này thay vì truyền request DTO thẳng vào service?

- Service có thể được gọi từ **HTTP, queue consumer, CLI hoặc scheduled job** mà không phụ thuộc JSON contract.
- Thay đổi API v2 không kéo theo thay đổi chữ ký nghiệp vụ.
- Các quy tắc bảo mật/tenant/timezone được áp dụng nhất quán ở service.
- Test service không phải tạo `MockHttpServletRequest` hay giả lập HTTP.

Với ứng dụng nhỏ, có thể giảm bớt lớp trừu tượng khi thật sự không có yêu cầu tái sử dụng; nhưng luôn nên giữ **entity Cassandra tách biệt public DTO**.

## 7. Lớp chuyển đổi DTO không làm nghiệp vụ

`EventDtoMapper` chỉ chuyển cấu trúc giữa hai biên:

~~~java
package com.example.activity.api;

import com.example.activity.application.CreateEventCommand;
import com.example.activity.application.EventView;
import org.springframework.stereotype.Component;

@Component
public class EventDtoMapper {

    public CreateEventCommand toCommand(CreateEventRequest request) {
        return new CreateEventCommand(
            request.eventId(),
            request.occurredAt(),
            request.eventType(),
            request.payload()
        );
    }

    public EventResponse toResponse(EventView view) {
        return new EventResponse(
            view.eventId(),
            view.occurredAt(),
            view.eventType(),
            view.payload()
        );
    }
}
~~~

Điểm tốt của mapper:

1. **Thuần chuyển đổi**; không query Cassandra, không tạo request ID ngẫu nhiên, không truy vấn authorization.
2. Có thể test đơn vị dễ dàng bằng dữ liệu giả.
3. Cho phép response v2 đổi tên/chọn trường mà không động đến entity.
4. Khi logic ánh xạ trở nên phức tạp, có thể dùng MapStruct với cấu hình rõ ràng, nhưng không nên giấu logic nghiệp vụ trong các expression khó theo dõi.

Không nên dùng kiểu `BeanUtils.copyProperties(request, entity)` để chép mù quáng: tên property không đủ diễn đạt partition key, quy tắc UTC, field được phép ghi và giá trị bảo mật nội bộ.

## 8. Entity và khóa tổng hợp của Cassandra

Trong data layer, tách `EventKey` khỏi `EventEntity` để phản ánh primary key của CQL:

~~~java
package com.example.activity.persistence;

import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class EventKey implements Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private UUID eventId;

    // No-arg constructor, constructor đầy đủ,
    // getters/setters và equals/hashCode.
}
~~~

Và entity:

~~~java
package com.example.activity.persistence;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_tenant_day")
public class EventEntity {
    @PrimaryKey
    private EventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    // No-arg constructor, constructor,
    // getters/setters theo Spring Data mapping.
}
~~~

**Cần hoàn thiện các constructor/accessor được ghi chú** nếu muốn biên dịch ví dụ. Chữ ký ví dụ trong phần service giả định có:

~~~java
new EventKey(tenantId, day, occurredAt, eventId);
new EventEntity(key, eventType, payload);

entity.getKey().getEventId();
entity.getKey().getOccurredAt();
entity.getEventType();
entity.getPayload();
~~~

Đối với `EventKey`, triển khai `equals/hashCode` dựa trên **toàn bộ thành phần khóa** và giữ thứ tự/kiểu Cassandra nhất quán. Không dùng `@Id` theo suy đoán từ JPA rồi bỏ qua composite partition key.

**Lưu ý Cassandra-specific:** `event_day` được tính từ `occurred_at` theo UTC ở tầng service, không lấy tùy tiện từ client; `tenant_id` lấy từ quyền đã xác thực, không chép từ body.

## 9. Repository: phương thức phản ánh đường đọc Cassandra

Repository tập trung vào CQL query và entity mapping:

~~~java
package com.example.activity.persistence;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface EventRepository
        extends CassandraRepository<EventEntity, EventKey> {

    @Query("""
        SELECT tenant_id, event_day, occurred_at, event_id,
               event_type, payload
        FROM events_by_tenant_day
        WHERE tenant_id = ?0 AND event_day = ?1
        LIMIT 50
        """)
    List<EventEntity> findRecentByTenantAndDay(
        UUID tenantId, LocalDate day
    );
}
~~~

`CassandraRepository<EventEntity, EventKey>` cung cấp các thao tác cơ bản như `save` và `findById`. Câu `@Query` thể hiện chính xác **điều kiện đọc theo full partition key** và giới hạn số hàng. Để dùng tên bảng không có keyspace prefix, ứng dụng phải được cấu hình keyspace mặc định đúng `activity_ks`.

Tại sao không để Repository chứa `findAnyEventByType(...)` rồi dùng `ALLOW FILTERING`? Vì repository không phải cách vượt qua giới hạn data model. Nếu use case thay đổi, cần **thiết kế bảng đọc/index** theo pattern mới.

**Lưu ý về `LIMIT 50`:** ví dụ chỉ phục vụ trang danh sách nhỏ, chưa phải API pagination hoàn chỉnh. Cassandra không có offset SQL thông thường; khi cần các trang tiếp, sử dụng driver paging state/cursor phù hợp và giới hạn kích thước partition.

## 10. Service: tính bucket, áp quy tắc và điều phối

Service nhận command thuần Java, tự xác định partition key, gọi repository và trả kết quả độc lập HTTP:

~~~java
package com.example.activity.application;

import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import com.example.activity.persistence.EventEntity;
import com.example.activity.persistence.EventKey;
import com.example.activity.persistence.EventRepository;

@Service
public class EventService {
    private final EventRepository repository;

    public EventService(EventRepository repository) {
        this.repository = repository;
    }

    public EventView create(UUID tenantId, CreateEventCommand command) {
        if (tenantId == null) {
            throw new IllegalArgumentException("Tenant là bắt buộc");
        }
        if (command.occurredAt() == null || command.eventId() == null) {
            throw new IllegalArgumentException("Thiếu khóa sự kiện");
        }

        LocalDate day = command.occurredAt()
            .atZone(ZoneOffset.UTC)
            .toLocalDate();

        EventKey key = new EventKey(
            tenantId, day, command.occurredAt(), command.eventId()
        );
        EventEntity entity = new EventEntity(
            key, command.eventType(), command.payload()
        );

        EventEntity saved = repository.save(entity);
        return toView(saved);
    }

    public List<EventView> findRecent(
            UUID tenantId, LocalDate day) {
        if (tenantId == null || day == null) {
            throw new IllegalArgumentException("Thiếu tenant hoặc ngày");
        }
        return repository.findRecentByTenantAndDay(tenantId, day)
            .stream()
            .map(this::toView)
            .toList();
    }

    private EventView toView(EventEntity entity) {
        EventKey key = entity.getKey();
        return new EventView(
            key.getEventId(), key.getOccurredAt(),
            entity.getEventType(), entity.getPayload()
        );
    }
}
~~~

Đoạn code chủ ý minh họa **nghiệp vụ và orchestration cơ bản**; trong dự án cần bổ sung kiểm soát loại sự kiện, độ dài/độ nhạy cảm của payload, time skew, retention, idempotency và các giới hạn per-tenant. Có thể tách phần `toView` thành `EventPersistenceMapper` khi mapping dữ liệu phức tạp; không để controller tự thao tác với `EventEntity`.

**Không đánh đồng việc service chứa hai lệnh repository với transaction SQL.** Cassandra không tự cấp transaction isolation/rollback nhiều bảng chỉ vì method có `@Service` hoặc `@Transactional`. Nếu workflow cần cập nhật nhiều bảng denormalized, phải thiết kế retry, idempotency và reconciliation.

## 11. Controller: chỉ làm giao thức HTTP và ủy quyền biên

Ví dụ Controller với Spring MVC:

~~~java
package com.example.activity.api;

import java.time.LocalDate;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;

import com.example.activity.application.EventService;
import com.example.activity.security.AppPrincipal;

@RestController
@RequestMapping("/api/v1/events")
public class EventController {
    private final EventService service;
    private final EventDtoMapper mapper;

    public EventController(EventService service, EventDtoMapper mapper) {
        this.service = service;
        this.mapper = mapper;
    }

    @PostMapping
    public ResponseEntity<EventResponse> create(
            @AuthenticationPrincipal AppPrincipal principal,
            @Valid @RequestBody CreateEventRequest request) {
        var result = service.create(
            principal.tenantId(),
            mapper.toCommand(request)
        );
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(mapper.toResponse(result));
    }

    @GetMapping
    public List<EventResponse> findRecent(
            @AuthenticationPrincipal AppPrincipal principal,
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate day) {
        return service.findRecent(principal.tenantId(), day)
            .stream()
            .map(mapper::toResponse)
            .toList();
    }
}
~~~

`AppPrincipal` là **kiểu principal do ứng dụng tự định nghĩa**, chứa `tenantId()` đã được xác thực và chỉ có mặt khi Spring Security được cấu hình đúng; nó **không tự được Spring tạo ra**. Ở production, phải bảo vệ endpoint bằng authentication/authorization phù hợp (ví dụ JWT Resource Server), từ chối request chưa xác thực và kiểm tra quyền tenant trước khi gọi service. Không lấy tenant từ chuỗi JWT chưa verify hoặc header do client tự tạo.

Controller không biết bảng Cassandra được bucket theo ngày hay danh sách được đọc bằng `@Query`. Nó nhận DTO, gọi Service và chuyển `EventView` thành response; vì thế đổi HTTP route không bắt buộc sửa entity/repository.

## 12. Đọc toàn bộ luồng từ HTTP đến Cassandra

Khi client gọi `POST /api/v1/events`, các bước xảy ra:

~~~text
1. Spring Security
   - Xác minh access token/chứng thực
   - Tạo principal có tenant được phép truy cập

2. Spring MVC / Controller
   - Deserialize JSON -> CreateEventRequest
   - Chạy bean validation
   - Lấy tenantId từ principal
   - Mapper -> CreateEventCommand

3. EventService
   - Kiểm tra business rule
   - Tính eventDay = occurredAt theo UTC
   - Tạo EventKey(tenantId, eventDay, occurredAt, eventId)
   - Gửi entity sang Repository

4. EventRepository / Java Driver
   - Mapped write -> INSERT/UPDATE theo schema Cassandra
   - Định tuyến dựa trên partition key
   - Thực thi theo consistency level và timeout được cấu hình

5. Kết quả
   - Service -> EventView
   - Mapper -> EventResponse
   - Controller -> HTTP 201 và JSON
~~~

**Một ranh giới cần bảo vệ:** khi Service tính `eventDay`, hãy dùng **đúng quy tắc UTC** ở mọi đường ghi/đọc. Nếu một consumer bất đồng bộ tính ngày theo timezone JVM còn REST Service dùng UTC, dữ liệu sẽ nằm ở partition khác, và tăng consistency level không sửa được lỗi.

Đối với GET, Service nhận `tenantId` và `day`, Repository bind **đúng partition key**, sau đó trả entity; Service tạo `EventView` và Mapper chuyển thành response. Không nên để Controller tự điền `WHERE tenant_id = ...` hoặc gắn `ALLOW FILTERING`.

## 13. Ba lớp kiểm tra dữ liệu: cú pháp, nghiệp vụ, phân quyền

Không nên dồn mọi validation vào một nơi.

| Kiểm tra | Ví dụ | Nơi phù hợp |
| --- | --- | --- |
| **Hình dạng request** | `eventId` bắt buộc, `occurredAt` đúng định dạng, `eventType` không rỗng | DTO + Bean Validation/Controller |
| **Quy tắc nghiệp vụ** | Event time không ở tương lai quá xa; event type thuộc tập được hỗ trợ; giới hạn số ngày backfill | Service |
| **Phân quyền** | Principal có quyền ghi/đọc dữ liệu tenant A, nhưng không phải tenant B | Security layer và policy kiểm tra ở application |
| **Tính hợp lệ của CQL** | Bind đầy đủ partition key, kiểu `timestamp`/`uuid` phù hợp | Repository/data access |
| **Ràng buộc vận hành** | Page size tối đa, payload size, rate limit, request deadline | Controller/service/gateway tùy trách nhiệm |

Một lỗi phổ biến là kiểm tra tenant **chỉ ở Controller** rồi cho queue consumer gọi thẳng service với tenant tùy ý. Nếu nhiều entry point cùng dùng business use case, Service nên nhận một **actor/authorization context đáng tin cậy** hoặc một abstraction chính sách quyền để không lặp logic bảo mật không nhất quán.

Đừng cho client ghi toàn bộ entity dưới dạng JSON chỉ vì entity có các field giống request. Điều đó dễ dẫn tới **mass assignment**: người dùng tự đưa `tenantId`, `eventDay` hoặc metadata nội bộ nhằm ghi sang partition không được phép.

### Chống sửa đổi dữ liệu từ client

Client có thể tự thay `eventId` giữa các retry hoặc thay `occurredAt` để gây ra hàng khác. Với endpoint cần idempotency nghiêm ngặt, nên dùng `Idempotency-Key`/request ID đã được chuẩn hóa, ánh xạ vào một command ổn định, và xác minh cùng khóa không được dùng với payload khác. Mỗi request vẫn phải xác thực quyền và kiểm tra kích thước dữ liệu.

## 14. Xử lý lỗi ở ranh giới Controller, không rò CQL

Không trả nguyên message của Java Driver hoặc stack trace ra REST response. Một mẫu ánh xạ:

| Tình huống | HTTP thường phù hợp | Lưu ý |
| --- | --- | --- |
| JSON sai kiểu, thiếu trường, validation thất bại | `400 Bad Request` | Chỉ ra field sai, không phản chiếu dữ liệu nhạy cảm |
| Chưa xác thực | `401 Unauthorized` | Security filter xử lý trước Controller |
| Đã xác thực nhưng không có quyền tenant | `403 Forbidden` hoặc `404` theo chính sách | Không để lộ sự tồn tại tài nguyên |
| Không tìm thấy entity theo full key | `404 Not Found` | Chỉ thực hiện query theo key hợp lệ |
| Conflict idempotency key/payload hoặc LWT không áp dụng | `409 Conflict` | Trả mã lỗi nghiệp vụ, không đoán kết quả ghi trước đó |
| Cassandra không sẵn sàng, thiếu replica | `503 Service Unavailable` | Circuit breaker/rate limit/retry có kiểm soát |
| Timeout giao tiếp Cassandra | `503` hoặc `504` tùy hợp đồng | **Ghi có thể đã xảy ra**; cần idempotency/reconciliation |

Với Spring MVC, `@RestControllerAdvice` có thể chuyển exception của Service thành body lỗi thống nhất. Ví dụ xử lý một ngoại lệ nghiệp vụ **do ứng dụng định nghĩa**:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(InvalidEventException.class)
    public ResponseEntity<ProblemDetail> invalidEvent(
            InvalidEventException exception) {
        ProblemDetail detail = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            exception.getMessage()
        );
        detail.setTitle("Invalid event");
        return ResponseEntity.badRequest().body(detail);
    }
}
~~~

Đoạn code cần import từ `org.springframework.http`, `org.springframework.web.bind.annotation`; `InvalidEventException` là class ứng dụng phải tự định nghĩa. Với lỗi hạ tầng, tránh gọi `exception.getMessage()` từ driver để đưa thẳng ra client vì có thể chứa chi tiết nội bộ; log theo request/correlation ID và trả thông báo an toàn.

**Cẩn thận với timeout ghi:** một HTTP 503/504 không bảo đảm Cassandra chưa áp dụng mutation. Gắn request ID ổn định và cung cấp đường kiểm tra trạng thái hoặc cơ chế reconciliation khi hiệu ứng nghiệp vụ quan trọng.

## 15. DTO Mapper khác CassandraCustomConversions

Hai loại “mapping” rất dễ bị đánh đồng:

| Mapper | Chuyển đổi gì? | Ví dụ |
| --- | --- | --- |
| **EventDtoMapper** | Public HTTP DTO ↔ application command/view | `CreateEventRequest → CreateEventCommand` |
| **Persistence mapper** (tùy ứng dụng) | Application model ↔ persistence entity | `EventView ← EventEntity` |
| **Spring Data custom conversions** | Java property ↔ kiểu/giá trị CQL | Enum, value object hoặc representation phù hợp Cassandra |
| **Jackson** | JSON ↔ DTO Java | ISO-8601 string ↔ `Instant` trong HTTP |

Mapper API **không phải** nơi ép kiểu `String` thành `LocalDate` cho Cassandra hoặc thực thi `USING TIMESTAMP`. Những việc đó thuộc converter/data-access, với quy tắc schema và phiên bản rõ ràng.

Nếu cần mở rộng:

~~~text
HTTP JSON
  -> Jackson
  -> CreateEventRequest
  -> EventDtoMapper
  -> CreateEventCommand
  -> EventService
  -> EventPersistenceMapper (tùy chọn)
  -> EventEntity
  -> Spring Data Cassandra Mapping / Conversions
  -> CQL bind values
~~~

Không đổi converter của một trường khóa mà bỏ qua dữ liệu cũ: nếu writer và reader ánh xạ khác nhau, cùng tenant/event có thể thành các giá trị CQL khác hoặc query không tìm thấy đúng hàng.

## 16. Khi nào Repository chưa đủ: CassandraTemplate và CqlSession

`CassandraRepository` phù hợp cho CRUD cơ bản và query theo key có thể diễn đạt rõ. Không nên ép mọi yêu cầu vào tên method derived query dài khó kiểm chứng.

| Nhu cầu | Cách truy cập thường phù hợp |
| --- | --- |
| Lưu/đọc entity theo primary key | `CassandraRepository` |
| Câu SELECT tường minh theo tenant/day | Repository `@Query` |
| Tạo điều kiện CQL từ nhiều lựa chọn hợp lệ và dùng mapping entity | `CassandraTemplate` |
| Chỉ chọn một số cột và ánh xạ kết quả nhỏ | Projection, `CassandraTemplate` hoặc `CqlTemplate` |
| Cần điều khiển driver paging state, CL, timeout, prepared/bound statement | `CqlSession`/Java Driver hoặc API Spring Data phù hợp |
| Ghi nhiều mutation có liên quan | `CassandraTemplate.batchOps()`, với giới hạn batch Cassandra |

Ví dụ tầng data-access bổ sung có thể chọn `CassandraTemplate` cho một lookup theo key:

~~~java
@Repository
public class EventLookup {
    private final CassandraTemplate template;

    public EventLookup(CassandraTemplate template) {
        this.template = template;
    }

    public EventEntity findExact(EventKey key) {
        return template.selectOneById(key, EventEntity.class);
    }
}
~~~

Đây là ví dụ API đồng bộ; cần import `CassandraTemplate` và `@Repository` phù hợp Spring Data/Spring Framework version. Phương thức lookup có thể trả `null` khi không tìm thấy; Service cần chuyển thành `EventNotFound` hoặc một kết quả miền nghiệp vụ có nghĩa.

**Không đưa `CassandraTemplate` và `CqlSession` vào Controller**. Khi Repository cần sức mạnh thấp tầng, có thể tạo thêm một **data-access adapter** thực thi query, vẫn để Service làm lớp điều phối.

## 17. Cursor pagination: ranh giới HTTP và trạng thái driver

Ví dụ `findRecentByTenantAndDay` trả tối đa 50 hàng. Nếu UI cần hàng nghìn sự kiện, không nên tăng `LIMIT` lên hàng trăm nghìn hoặc dùng offset SQL giả.

Một API thực tế:

~~~http
GET /api/v1/events?day=2026-11-25&limit=25
GET /api/v1/events?cursor=<opaque-cursor>
~~~

Các trách nhiệm nên chia:

- **Controller:** validate `limit`, nhận cursor dạng chuỗi opaque, trả `nextCursor`.
- **Service:** giữ hợp đồng lọc/tenant/sort bất biến qua các trang; điều phối nhiều bucket nếu cần.
- **Data access:** tạo bound statement và dùng paging state của Java Driver cho **cùng CQL và tham số**.
- **Cursor encoder/decoder:** ký HMAC hoặc mã hóa xác thực, gắn tenant/subject, query ID, filter fingerprint, page size và expiry.
- **Security:** kiểm tra lại quyền tenant trên **mỗi request**, không tin chữ ký cursor là đủ quyền.

Paging state của driver không phải số trang tùy ý và **không phải snapshot giao dịch**. Nếu dữ liệu bị ghi/xóa hoặc TTL hết hạn giữa các request, các trang có thể khác nhau. Với API cần xuất dữ liệu bất biến tại một mốc, phải thiết kế snapshot/export riêng.

### Nhiều ngày nghĩa là nhiều partition

Ở bảng ví dụ, truy vấn ba ngày cần đọc các partition:

~~~text
(tenant A, 2026-11-23)
(tenant A, 2026-11-24)
(tenant A, 2026-11-25)
~~~

Không lấy paging state của ngày 25 rồi bind ngày 24. Service phải quản lý **bucket hiện tại** và trạng thái đọc của từng partition trong cursor cấp ứng dụng, cùng giới hạn fan-out/latency.

Nếu API tìm theo nhiều tenant hoặc khoảng thời gian rộng, Controller không nên đưa một tham số “unlimited” xuống Repository; Service cần đặt ngưỡng và hợp đồng truy vấn đúng data model.

## 18. Consistency, timeout và retry thuộc chính sách nào?

RF được khai báo ở keyspace; CL có thể được cấu hình ở Java Driver/execution profile hoặc mỗi statement. Ví dụ RF=3 trong dc1:

~~~text
Write LOCAL_QUORUM: cần 2/3 replica cục bộ phản hồi.
Read  LOCAL_ONE:   cần 1 replica cục bộ phản hồi.
Read  LOCAL_QUORUM: cần 2/3 replica cục bộ phản hồi.
~~~

Một cấu hình Spring Boot minh họa:

~~~yaml
spring:
  cassandra:
    contact-points: cassandra-dc1.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: activity_ks
    schema-action: none
~~~

`schema-action: none` giúp tránh ứng dụng tự thay đổi schema khi khởi động; keyspace/table phải được quản lý trước. Endpoint và DC ở đây chỉ là giá trị ví dụ; production cần TLS, authentication và cấu hình cluster phù hợp.

Khi một workflow cần CL riêng, có thể cấu hình tại data-access layer:

~~~java
BoundStatement statement = preparedSelect
    .bind(tenantId, day)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(25);

AsyncResultSet page = session.executeAsync(statement)
    .toCompletableFuture()
    .join(); // Chỉ minh họa; không block trên event loop.
~~~

Đoạn trên minh họa driver 4.x và yêu cầu import/cấu hình `CqlSession`, `PreparedStatement`, `BoundStatement`, `AsyncResultSet`. **Không dùng `join()` trong luồng reactive hay request thread nếu mục tiêu là non-blocking**; code production có thể trả `CompletionStage` và tiếp tục bất đồng bộ hoặc chọn API đồng bộ phù hợp.

**Không đặt retry ở ba tầng một cách độc lập** (gateway → Service → driver), vì một thao tác có thể bị thực thi nhiều lần. Service quyết định khi nào lệnh có thể retry về mặt nghiệp vụ; data access áp dụng timeout/idempotency metadata tương ứng; cả hệ thống có backoff, deadline và reconciliation.

## 19. Upsert không đồng nghĩa tạo mới duy nhất

Ví dụ Service dùng `repository.save(entity)`. Trong Cassandra, thao tác ghi thường có **upsert semantics**: nếu primary key đã tồn tại, có thể ghi đè cell với write timestamp phù hợp.

Điều này tác động trực tiếp tới API:

~~~text
Request A: eventId=E1, occurredAt=T1, payload="A"
Request B: eventId=E1, occurredAt=T1, payload="B"

Cùng tenant và event_day => cùng full primary key.
Không thể coi cả hai là hai sự kiện riêng;
giá trị cell có thể được phân giải theo write timestamp.
~~~

Vì vậy **HTTP 201** trong ví dụ minh họa có ý nghĩa “server chấp nhận lưu theo command”, nhưng **chưa bảo đảm bản ghi trước đó chưa tồn tại**. Nếu API cam kết “chỉ tạo một lần”, cần thiết kế điều kiện:

~~~sql
INSERT INTO activity_ks.events_by_tenant_day (
    tenant_id, event_day, occurred_at, event_id,
    event_type, payload
) VALUES (?, ?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

`IF NOT EXISTS` sử dụng LWT với chi phí riêng; kết quả phải được kiểm tra `[applied]`. Nếu request trước thành công nhưng response mất, lần retry có thể nhận `applied=false`. Service cần kiểm tra **eventId/request ID và fingerprint payload** để phân biệt retry hợp lệ với conflict thực sự.

Không tự suy rằng `save()`, `@Transactional` hoặc một batch thông thường đủ để tạo exactly-once effect cho nhiều bảng và hệ thống ngoài Cassandra.

## 20. Khi một nghiệp vụ ghi nhiều bảng đọc (denormalization)

Vì Cassandra thường thiết kế **mỗi bảng theo truy vấn**, cùng một sự kiện có thể được ghi vào:

~~~text
events_by_tenant_day
  -> lịch sử theo tenant/ngày

events_by_type_day
  -> lịch sử theo event_type/ngày

events_by_order
  -> tìm mọi event của một order
~~~

Nhiều bảng đọc có thể giúp API nhanh hơn, nhưng thay đổi cách tổ chức Service:

1. Service xác định **command ID ổn định**, các partition keys và dữ liệu cần ghi cho từng access pattern.
2. Các repository/data-access adapter xử lý CQL của mỗi bảng, **không trả HTTP status**.
3. Nếu cần gom một số mutation có liên quan, đánh giá `CassandraTemplate.batchOps()` hoặc CQL batch đúng phạm vi; **logged batch không cung cấp isolation kiểu SQL xuyên nhiều partition**.
4. Timeout có thể khiến kết quả chưa chắc chắn; cần **idempotency, metrics và reconciliation**.
5. Read model phải biết mức trễ/đồng bộ chấp nhận được, đặc biệt khi dữ liệu bị cập nhật hoặc xóa.

Tránh “service method có ba lệnh `save()` nên chắc chắn cả ba cùng commit”. Spring không biến các thao tác Cassandra thành transaction ACID đa bảng chỉ vì code nằm trong cùng một hàm.

## 21. Đồng bộ và reactive: chọn một mô hình xuyên các lớp

Ví dụ từ đầu bài dùng **Spring MVC + CassandraRepository/CassandraTemplate đồng bộ**. Với throughput cao và nhu cầu backpressure, có thể chọn **Spring WebFlux + ReactiveCassandraRepository/ReactiveCassandraTemplate**.

| Tầng | Đồng bộ | Reactive |
| --- | --- | --- |
| Controller | Trả `ResponseEntity<T>`/`List<T>` | Trả `Mono<T>`/`Flux<T>` |
| Service | Gọi repository và trả giá trị trực tiếp | Composing operators trên Publisher |
| Repository | `CassandraRepository` | `ReactiveCassandraRepository` |
| Template | `CassandraTemplate` | `ReactiveCassandraTemplate` |
| Quy tắc schema/CL/TTL | Theo CQL Cassandra | **Cùng quy tắc** |

Không đưa một repository blocking vào WebFlux event loop rồi cho rằng API tự trở thành non-blocking. Tương tự, không gọi `block()` trong giữa service reactive hoặc tự động dùng `subscribe()` để “kích hoạt ghi” rồi trả HTTP 201 trước khi có kết quả.

**Kiến trúc phân tầng vẫn giữ nguyên** khi chuyển sang reactive; chỉ kiểu giá trị và mô hình thực thi thay đổi. Hãy test cancellation, backpressure, timeout, retry và phạm vi bảo mật trên chuỗi reactive.

## 22. Kiểm thử từng lớp mà không cần khởi động cả cluster

Một lợi ích thực tế của phân tầng là dễ kiểm thử **logic và boundary riêng**:

| Mức test | Đối tượng | Điều cần xác minh |
| --- | --- | --- |
| Mapper unit test | `EventDtoMapper` | Field mapping, null contract, không tự tạo tenant/id |
| Service unit test | `EventService` với repository mock | Tính bucket UTC, tạo full primary key, gọi repository đúng dữ liệu |
| Controller web test | MVC + security test principal | HTTP validation, auth tenant, mã lỗi, response JSON |
| Repository integration test | Cassandra thật trong test environment | CQL hợp lệ, mapping composite key, thứ tự clustering |
| End-to-end | HTTP + Spring + Cassandra | Retry/CL/timeout, partition bucket, response, metrics |

Ví dụ test service với JUnit 5 và Mockito:

~~~java
@ExtendWith(MockitoExtension.class)
class EventServiceTest {

    @Mock
    EventRepository repository;

    @InjectMocks
    EventService service;

    @Test
    void createUsesUtcDayAndAuthenticatedTenant() {
        UUID tenant = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();
        Instant occurredAt = Instant.parse("2026-11-25T00:15:00Z");

        when(repository.save(any(EventEntity.class)))
            .thenAnswer(call -> call.getArgument(0));

        service.create(
            tenant,
            new CreateEventCommand(
                eventId, occurredAt, "ORDER_PAID", "ok"
            )
        );

        ArgumentCaptor<EventEntity> captor =
            ArgumentCaptor.forClass(EventEntity.class);
        verify(repository).save(captor.capture());

        EventKey key = captor.getValue().getKey();
        assertEquals(tenant, key.getTenantId());
        assertEquals(LocalDate.of(2026, 11, 25), key.getEventDay());
        assertEquals(eventId, key.getEventId());
    }
}
~~~

Import cần thiết: `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.extension.ExtendWith`, `org.mockito.*`, `org.mockito.junit.jupiter.MockitoExtension`, `java.time.*`, `java.util.UUID` cùng các class ứng dụng; dùng static import cho `when`, `any`, `verify` và `assertEquals`. Snippet này là ví dụ test rút gọn, **không chạy trong STEP 4**.

Một unit test **không đủ** để chứng minh Cassandra hiểu mapping, CQL `WHERE` hoặc secondary index. Cần integration test trên một cluster thử nghiệm/fixture phù hợp phiên bản, xác minh mapping thực bằng đọc lại theo full key và các edge cases phân vùng ngày.

### Các test edge case quan trọng

- Event lúc **23:59:59 UTC** và **00:00:01 UTC** được ghi ở hai partition ngày khác nhau.
- Hai tenant dùng cùng `eventId` không được đọc chéo dữ liệu.
- Bỏ `occurredAt` hoặc `eventId` bị từ chối trước khi ghi.
- Request có payload vượt giới hạn bị từ chối với HTTP 400.
- Cùng request ID với payload khác được xử lý theo chính sách conflict, không im lặng ghi đè.
- Query theo tenant/ngày không dùng `ALLOW FILTERING` hoặc scan toàn cluster.
- Timeout ghi không bị giả định là rollback, có phương án kiểm tra và retry.
- API cursor không được dùng để đổi tenant/filter hoặc tái sử dụng paging state sai query.

## 23. Observability và vận hành nên đặt ở đâu?

| Quan sát | Tầng nên triển khai | Tránh |
| --- | --- | --- |
| Correlation/request ID | Gateway/Controller, propagate tới service | Ghi access token nguyên văn |
| Business command ID và outcome | Service | Log payload nhạy cảm |
| Query latency, timeout, unavailable | Data access/driver metrics | Chỉ log stack trace, không có metric |
| Retry count và reconciliation | Service/worker | Retry vô hạn không kiểm soát |
| HTTP 4xx/5xx và latency | Controller/MVC observability | Gộp hết thành HTTP 500 |
| Partition size, tombstone, compaction | Cassandra vận hành | Dùng `LIMIT` như giải pháp duy nhất cho partition lớn |

Các nhãn metric nên có **cardinality thấp**; không dùng `tenantId`, `eventId` hoặc payload làm label cho mọi request. Khi cần debug một request cụ thể, dùng trace/correlation ID được bảo vệ và tuân thủ chính sách lưu giữ.

Sự phân tầng giúp trả lời: lỗi xuất phát từ **input**, **business rule**, **mapping**, **CQL**, **replica/CL** hay **hệ thống ngoài**? Nếu tất cả nằm trong Controller, sẽ rất khó tách và đo từng nguyên nhân.

## 24. Anti-pattern và hướng cải thiện

| Anti-pattern | Vì sao có vấn đề | Hướng sửa |
| --- | --- | --- |
| Controller gọi thẳng `CassandraRepository.save()` | HTTP biết entity, key và business rule | Controller gọi Service, Service điều phối |
| Trả `EventEntity` trực tiếp thành JSON | Rò field lưu trữ, coupling schema và API | Dùng `EventResponse` và DTO Mapper |
| Nhận `tenant_id` từ body mà không kiểm quyền | Nguy cơ ghi/đọc chéo tenant | Tenant từ principal/authorization context đáng tin |
| Mapper gọi DB để lấy tenant hoặc tạo business ID | Side effect và logic ẩn trong mapping | Mapping thuần; quyết định ở Service |
| Service tạo `HttpStatus` và `ResponseEntity` | Domain logic dính Spring MVC | Trả command result, Controller chọn HTTP status |
| Repository có `findAllByEventType()` thiếu key | Truy vấn Cassandra không phù hợp schema | Thiết kế bảng đọc/query-driven |
| Đọc về hàng triệu entity rồi tự cắt list | Heap/network lớn; bỏ qua paging state | CQL paging/cursor và giới hạn query |
| `@Transactional` bọc nhiều save và giả định rollback | Cassandra không giống SQL transaction | Idempotency, LWT/batch đúng chỗ, reconciliation |
| `save(entity)` để cập nhật một cột | Có thể ghi đè giá trị từ snapshot cũ | Partial update bằng CQL/Template |
| Tự retry mọi timeout | Ghi cũ có thể đã áp dụng | Command ID ổn định, retry theo idempotency |
| Nhét `CqlSession` vào Controller | Business, HTTP, CQL trộn vào nhau | Data-access adapter riêng |
| Đưa blocking calls vào WebFlux event loop | Chặn luồng xử lý | Dùng reactive access đồng nhất |
| Cùng converter Java nhưng writer/read khác cách lưu | Không tìm đúng partition, lỗi dữ liệu | Test mapping thực và thống nhất CQL representation |

## 25. Checklist thiết kế ứng dụng Spring Data Cassandra

- [ ] Schema được thiết kế từ **API query patterns**, không suy ra từ entity Java giống bảng quan hệ.
- [ ] Controller chỉ xử lý HTTP, validation cơ bản, security context và DTO mapping.
- [ ] Service giữ business rules, tenant scope, partition bucket, idempotency, timeout/retry policy.
- [ ] Repository/data-access giữ CQL, bind đúng partition/clustering key, mapping entity và execution options.
- [ ] Public API dùng DTO riêng, không serialize trực tiếp `@Table` entity.
- [ ] Mapper thuần chuyển đổi; không gọi database hoặc phát side effect.
- [ ] Có quy tắc UTC/timezone cố định khi tính `event_day`.
- [ ] Có cơ chế authorization tenant ở mọi entry point, không chỉ một Controller.
- [ ] Đường đọc có partition key đầy đủ; không che full scan bằng repository method.
- [ ] Dữ liệu cần nhiều access pattern được denormalize có chủ đích, có kế hoạch đồng bộ/reconcile.
- [ ] Pagination dùng cursor/paging state phù hợp và token có bảo vệ nếu public.
- [ ] CL, timeout, retry và idempotency phù hợp RF và workflow; không đánh đồng timeout với rollback.
- [ ] Có test Mapper/Service/Controller và integration test trên Cassandra.
- [ ] Log/metrics đủ để quan sát lỗi CQL/replica mà không lộ dữ liệu nhạy cảm.
- [ ] Khi cần reactive, toàn bộ Controller–Service–Repository theo cùng non-blocking model.

## 26. Bài tập thực hành

**Bài 1 — Phân vai đúng lớp.** Cho các thao tác: parse ngày từ query string, kiểm tra tenant có quyền ghi, tính `event_day`, chạy `SELECT ... WHERE tenant_id=?`, đổi entity thành JSON và kiểm tra payload dài quá 8 KiB. Hãy phân chúng vào Controller/Service/Repository/Mapper và giải thích vì sao.

**Gợi ý:** parsing/bean validation ở HTTP; quyền và bucket ở policy/service; CQL ở data access; entity → response DTO ở mapper. Kích thước payload có thể kiểm tra sơ bộ ở API và giới hạn nghiệp vụ ở service.

**Bài 2 — Viết test ranh giới UTC.** Tạo hai command với mốc `2026-11-25T23:59:59Z` và `2026-11-26T00:00:01Z`; dùng Mockito capture `EventEntity` để xác nhận chúng thuộc hai `event_day` khác nhau, trong khi tenant được giữ nguyên.

**Bài 3 — API mới theo loại sự kiện.** Product yêu cầu `GET /events?type=ORDER_PAID&day=...` trên nhiều tenant. Hãy giải thích vì sao thêm derived repository method chưa đủ; phác thảo partition key/bảng đọc `events_by_type_day`, authorization và cơ chế đồng bộ dữ liệu.

**Bài 4 — Retry ghi sự kiện.** Client gửi lại cùng `eventId` nhưng payload khác. Hãy thiết kế chính sách idempotency key, cách phát hiện conflict và cách map sang HTTP 409. Phân biệt upsert thông thường với `INSERT ... IF NOT EXISTS` và kết quả `[applied]`.

**Bài 5 — Cursor nhiều ngày.** API hiển thị lịch sử 7 ngày. Hãy xác định lớp nào quản lý list ngày và giới hạn fan-out, lớp nào quản lý raw paging state và lớp nào ký token cho client. Giải thích vì sao một paging state không dùng được cho nhiều partition với bind ngày khác nhau.

## 27. Tự kiểm tra

**Câu 1.** Controller có nên gửi trực tiếp `EventEntity` qua JSON không?

**Đáp án:** Không nên. Entity phụ thuộc schema Cassandra và có thể chứa metadata nội bộ; trả `EventResponse` qua mapper để bảo vệ public contract.

**Câu 2.** Ai tính `event_day` từ `occurredAt` và vì sao?

**Đáp án:** Service với quy tắc timezone thống nhất (ví dụ UTC), vì đây là quyết định phân vùng theo nghiệp vụ/data model. Mapper/Controller không nên tự đưa nhiều quy tắc tính bucket khác nhau.

**Câu 3.** Ai quyết định tenant ID thật sự được ghi vào partition?

**Đáp án:** Một security/application context đã xác thực và ủy quyền, rồi Service sử dụng giá trị đó. Không tin tenant ID do client tự điền.

**Câu 4.** Có thể dùng `@Transactional` để biến hai lần `repository.save()` trên hai bảng Cassandra thành transaction SQL có rollback đầy đủ không?

**Đáp án:** Không. Cần hiểu semantics CQL, phân vùng, batch/LWT khi phù hợp và cơ chế retry/reconciliation.

**Câu 5.** `EventDtoMapper` có nên gọi `repository.findById()` để bổ sung dữ liệu?

**Đáp án:** Không nên. Mapper nên thuần chuyển đổi; Service/data access thực hiện truy vấn và quyết định dữ liệu được trả.

**Câu 6.** Vì sao `GET /events?day=...` có thể đọc hiệu quả với schema ví dụ nhưng `GET /events?type=...` không tự nhiên hiệu quả?

**Đáp án:** Bảng dùng partition key `(tenant_id, event_day)`; truy vấn theo loại thiếu đường truy cập tương ứng. Cần thiết kế bảng/index/query phù hợp.

**Câu 7.** Gọi `repository.save()` hai lần cùng primary key có đảm bảo tạo một sự kiện bất biến duy nhất không?

**Đáp án:** Không. Ghi Cassandra thường upsert và có thể ghi đè cell theo timestamp; muốn create-only/idempotency cần điều kiện và xử lý conflict.

**Câu 8.** Khi một write timeout, Controller có thể khẳng định chắc Cassandra chưa ghi không?

**Đáp án:** Không. Kết quả có thể chưa chắc chắn; phải có request ID ổn định, policy retry và cách kiểm tra/reconcile.

**Câu 9.** Nếu ứng dụng chuyển từ MVC sang WebFlux, có nên giữ repository blocking nhưng gọi `block()`/`subscribe()` trong handler?

**Đáp án:** Không nên. Chọn mô hình reactive xuyên tầng và để Publisher hoàn tất theo request lifecycle, không tự block event loop hoặc trả thành công trước khi mutation hoàn tất.

**Câu 10.** Điều gì phải được kiểm tra ngoài unit test Service?

**Đáp án:** Integration test trên Cassandra thực tế để xác minh composite key mapping, CQL hợp lệ, clustering, paging/consistency và hành vi ghi/đọc khi có replica/timeout.

---

**Ghi nhớ:** thiết kế ứng dụng tốt với **Spring Data Cassandra** bắt đầu từ **bảng theo truy vấn và partition key đúng**, sau đó tách **Controller (HTTP/security boundary)**, **Service (nghiệp vụ/orchestration)**, **Repository/data access (CQL/mapping/driver)** và **DTO Mapper (chuyển đổi dữ liệu thuần)**. Không để entity Cassandra thành public JSON, không giấu quét toàn cluster sau tên method, không nhầm `save()` hay `@Transactional` với transaction SQL, và phải coi **consistency, paging, retry, idempotency, tenant authorization** là một phần của thiết kế xuyên các lớp.
