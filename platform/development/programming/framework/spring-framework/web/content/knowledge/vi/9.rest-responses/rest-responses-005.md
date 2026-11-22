# Thiết kế DTO phản hồi và tách mô hình HTTP khỏi đối tượng lưu trữ trong Spring MVC

## 1. Mục tiêu bài học

Khi xây dựng API REST bằng Spring MVC, đối tượng Java đọc/ghi trong database thường có nhiều thông tin **không thuộc hợp đồng HTTP**: khóa ngoại, trạng thái nội bộ, metadata quản trị, trường bí mật, lazy relations hoặc tên cột phục vụ tối ưu lưu trữ. Trả thẳng JPA entity từ `@RestController` khiến dữ liệu và cấu trúc API bị phụ thuộc chặt vào schema và hành vi ORM.

Mục tiêu là thiết kế **Response DTO (Data Transfer Object)** như một mô hình biểu diễn công khai, có chủ đích, và giữ xử lý HTTP ở controller thay vì rải `ResponseEntity`, status hoặc Servlet API vào tầng lưu trữ.

Sau bài này, bạn có thể:

- Phân biệt domain model, persistence entity, request DTO, response DTO và HTTP representation.
- Chọn đúng trường, cấu trúc, kiểu dữ liệu, nullability và định dạng cho response mà client thực sự cần.
- Chuyển entity → DTO tại ranh giới service/controller bằng mapper rõ ràng; không lộ field nội bộ hay đồ thị quan hệ JPA.
- Dùng `@RestController`, `@ResponseBody`, `ResponseEntity<T>`, `Location`, status `200`/`201`/`204`/`404` và xử lý lỗi phù hợp.
- Hiểu các hệ quả về transaction, lazy loading, N+1 query, phân trang, security, versioning và kiểm thử.
- Thực hành với **Java 17+, Spring Framework 6.x/Spring Boot 3.x, Spring Data JPA và H2**.

Các ví dụ runnable bên dưới giả định dự án Spring Boot có dependency: **Spring Web**, **Spring Data JPA**, **Validation**, **H2 Database**, **Spring Boot Test**. Nếu ứng dụng đang sử dụng Spring Boot 4/Spring Framework 7, nhiều nguyên tắc vẫn giữ nguyên, nhưng hãy đối chiếu dependency và API test theo phiên bản đang dùng.

## 2. Các mô hình cần tách

Đừng dùng từ “model” cho mọi thứ mà không xác định vai trò:

| Loại | Trách nhiệm | Ví dụ | Có nên trả trực tiếp ra HTTP? |
| --- | --- | --- | --- |
| **Persistence entity** | Ánh xạ database, quan hệ, ID, version, lazy loading | `CustomerEntity` có `internalMemo` | Thông thường **không** |
| **Domain model / business object** | Quy tắc nghiệp vụ, trạng thái và bất biến | `Customer`, `Money`, `Order` | Thường ánh xạ sang DTO |
| **Request DTO** | Hợp đồng dữ liệu client được phép gửi | `CreateCustomerRequest` | Chỉ dùng cho input; phải validate |
| **Response DTO** | Hợp đồng dữ liệu client được phép nhận | `CustomerResponse` | **Có**, là dạng biểu diễn công khai |
| **HTTP envelope** | Status, headers, media type, cache, Location | `ResponseEntity<CustomerResponse>` | Thuộc ranh giới HTTP/controller |
| **Error response** | Cấu trúc lỗi công khai, mã lỗi, message an toàn | `ProblemDetail` hoặc `ApiError` | Có, với chính sách riêng |

Trong demo, một đối tượng lưu trữ có thể bao gồm `id`, `displayName`, `email`, `internalMemo`, `createdAt`. Response DTO chỉ gồm `id`, `displayName`, `email`, `createdAt`; `internalMemo` không phải dữ liệu public.

### Sơ đồ ranh giới

```text
                  HTTP / JSON
                      |
                      v
           CustomerController
         @RequestBody request DTO
      @Valid / status / headers / URI
                      |
                      v
             CustomerService
          nghiệp vụ + transaction
          entity -> response DTO
                      |
                      v
           CustomerRepository
                JPA/Hibernate
                      |
                      v
                   Database

      Response DTO -> HttpMessageConverter/Jackson
                  -> HTTP body
```

Một cách tổ chức thường gặp là mapper riêng (`CustomerMapper`), có thể được gọi trong service hoặc application layer. Điểm cốt lõi là **mapping có chủ đích trước khi object đi qua HTTP serialization**. Controller có thể giữ vai trò mapping nếu ứng dụng nhỏ và dependency hướng đúng; tuy nhiên không nên đưa `HttpServletRequest`, `ResponseEntity` hoặc status HTTP xuống repository.

## 3. Vì sao không trả JPA entity trực tiếp?

### 3.1. Rủi ro lộ dữ liệu

```java
// Ví dụ cần tránh nếu entity chứa trường nội bộ:
@GetMapping("/customers/{id}")
public CustomerEntity find(@PathVariable long id) {
    return repository.findById(id).orElseThrow();
}
```

Jackson có thể serialize các property có getter được nhận diện; thêm getter/field trong entity ở tương lai có thể vô tình xuất hiện trong JSON. Những trường như `passwordHash`, `resetToken`, `secretKey`, `internalMemo`, `riskLevel` hoặc thông tin riêng của tenant tuyệt đối không nên được kiểm soát bằng “hy vọng client không biết chúng tồn tại”.

`@JsonIgnore` trên entity có thể chặn một số field nhưng khiến **schema persistence phải mang trách nhiệm HTTP contract**. Nó cũng không giải quyết toàn bộ vấn đề: một entity có thể cần những view response khác nhau theo endpoint, user role và API version.

**DTO hạn chế bề mặt dữ liệu có thể serialize; nó không thay thế authorization.** Trước khi ánh xạ DTO, service vẫn cần kiểm tra người gọi có quyền đọc resource và từng field nhạy cảm hay không. Nếu endpoint trả email, hãy xác định rõ vai trò nào được phép thấy email.

### 3.2. Lộ chi tiết database và mất ổn định hợp đồng

Entity thường thay đổi theo hiệu năng/schema: rename cột, tách bảng, thêm quan hệ `@OneToMany`, đánh chỉ mục, thêm trường `@Version`. Nếu response = entity, thay đổi lưu trữ có thể phá client. DTO tạo một lớp chống phụ thuộc, cho phép:

- Rename field lưu trữ nhưng giữ JSON `displayName`.
- Tổng hợp dữ liệu từ nhiều bảng thành một response đơn giản.
- Ẩn ID nội bộ hoặc khóa ngoại mà client không cần.
- Thay đổi JPA/Hibernate mà không bắt client thay cấu trúc.
- Giữ phiên bản API cũ bằng mapper cũ khi thay đổi domain.

### 3.3. Lazy loading, vòng lặp JSON và query khó kiểm soát

Ví dụ entity `OrderEntity` có quan hệ `CustomerEntity` và `OrderLineEntity`; trả entity có thể khiến Jackson cố đọc quan hệ lazy sau khi transaction kết thúc và gặp `LazyInitializationException`, hoặc chạy thêm truy vấn không kiểm soát. Quan hệ hai chiều (`Order -> Customer -> Orders -> ...`) có thể dẫn đến vòng lặp serialize, JSON khổng lồ, hoặc cần annotation Jackson gây coupling.

Cách đúng:

1. Xác định chính xác dữ liệu response cần, ví dụ `OrderResponse(id, customerName, List<LineResponse>)`.
2. Fetch dữ liệu bằng query/fetch plan phù hợp **trong transaction** hoặc projection trực tiếp.
3. Map sang DTO, chỉ gồm trường mong muốn.
4. Trả DTO ra khỏi service khi đã hoàn tất truy cập persistence.

Spring Boot có cơ chế **Open Session in View** trong một số cấu hình servlet/JPA, nhưng không nên dựa vào việc session còn mở để Jackson vô tình phát truy vấn database lúc render response. DTO giúp tách thời điểm truy vấn và render, nhưng **không tự sửa N+1**: bạn vẫn phải kiểm tra fetch plan.

### 3.4. Không dùng entity làm request DTO

Input từ client có thể chứa `id`, `role`, `isAdmin`, `ownerId` dù API chỉ định cho phép đổi `displayName`. Nếu bind trực tiếp vào entity và gọi `save`, bạn có nguy cơ **mass assignment/overposting**. Request DTO với trường được phép chỉnh sửa là **allowlist ở hợp đồng đầu vào**; sau đó vẫn cần authorize thao tác và validate.

## 4. Response DTO nên có những trường nào?

Thiết kế từ **nhu cầu của client và cam kết API** trước, sau đó mới quyết định map từ database.

Ví dụ JSON hợp lý cho một customer:

```json
{
  "id": 42,
  "displayName": "Lan",
  "email": "lan@example.com",
  "createdAt": "2026-10-21T04:00:00Z"
}
```

Các lựa chọn cần cân nhắc:

- **Tên field ổn định:** `displayName` nên mang ngữ nghĩa client hiểu, không lệ thuộc tên cột `full_name_v2`.
- **Kiểu dữ liệu đúng:** số là JSON number nếu thực sự là quantity an toàn; identifier dài vượt giới hạn chính xác của JavaScript đôi khi nên là string trong API.
- **Thời gian:** `Instant` thường serialize thành ISO-8601 khi Boot/Jackson Java Time module được cấu hình; nêu rõ UTC và timezone. Trong ví dụ, `"Z"` biểu thị UTC.
- **Tiền tệ:** dùng chuỗi thập phân hoặc object gồm `amount` và `currency` theo hợp đồng; tránh dùng `double` cho số tiền nếu đòi độ chính xác.
- **Null/missing:** JSON `"field":null` và không có key có thể mang ý nghĩa khác; chuẩn hóa API và kiểm thử cấu hình Jackson `NON_NULL`/`NON_EMPTY` nếu dùng.
- **Danh sách:** cân nhắc `[]` thay vì `null` cho collection rỗng nếu hợp đồng quy định; đừng để ORM collection proxy xuất trực tiếp.
- **Trường dẫn xuất:** các URL hay field tổng hợp nên tính ở nơi hiểu ngữ nghĩa/public routing; không bắt entity lưu mọi thứ client thấy.
- **Quyền truy cập:** DTO của admin có thể khác DTO công khai; một DTO có quá nhiều field nullable theo role thường khiến contract khó hiểu.
- **JSON root:** chọn dạng object rõ ràng; định dạng của từng endpoint nên độc lập với chi tiết `ResponseEntity` Java.

Một response DTO là **API schema có vòng đời riêng**, không chỉ “bản copy của entity có ít field hơn”.

## 5. Java record, class và mức bất biến

Java 17 `record` phù hợp cho DTO nhỏ, bất biến về tham chiếu trường:

```java
public record CustomerResponse(
        Long id,
        String displayName,
        String email,
        java.time.Instant createdAt) {}
```

Ưu điểm: cấu trúc ngắn gọn, generated constructor/accessors/`equals`/`hashCode`/`toString`, dễ test; Jackson trong Boot hiện đại hỗ trợ record. Nhưng record không làm đồ thị nested tự động bất biến: nếu chứa `List<MutableItem>` thì vẫn cần copy bất biến hoặc DTO nested tương ứng.

Class DTO phù hợp nếu framework/serializer đặc thù yêu cầu constructor/setter, có nhu cầu tùy biến cao hoặc bạn cần kiểm soát backwards compatibility khác. **Không nên chọn record làm JPA entity tiêu chuẩn**: entity JPA có yêu cầu về constructor và model quản lý vòng đời; record thích hợp với DTO/projection hơn.

Tách input/output:

```java
public record CreateCustomerRequest(
        @jakarta.validation.constraints.NotBlank
        @jakarta.validation.constraints.Size(max = 100)
        String displayName,

        @jakarta.validation.constraints.NotBlank
        @jakarta.validation.constraints.Email
        @jakarta.validation.constraints.Size(max = 254)
        String email) {}
```

Request DTO có constraint vì kiểm soát **dữ liệu được nhập**. Response DTO mô tả **dữ liệu công khai được trả**; các constraint output (nếu áp dụng) có mục đích khác. Đừng đưa field generated `id` hoặc nội bộ `internalMemo` vào `CreateCustomerRequest` nếu client không được đặt chúng.

## 6. Mapper: entity -> response DTO

Mapper đơn giản, rõ ràng:

```java
public final class CustomerMapper {
    private CustomerMapper() {}

    public static CustomerResponse toResponse(CustomerEntity entity) {
        return new CustomerResponse(
                entity.getId(),
                entity.getDisplayName(),
                entity.getEmail(),
                entity.getCreatedAt());
    }
}
```

Đây là **đoạn trích minh họa** dùng các lớp `CustomerEntity` và `CustomerResponse` được định nghĩa ở phần ví dụ runnable; không tự chạy riêng.

Ưu điểm của mapper explicit:

- Review dễ thấy chính xác trường nào rời khỏi tầng dữ liệu.
- Thêm trường entity không tự mở rộng JSON.
- Có nơi chuyển enum nội bộ thành chuỗi hợp đồng, chuyển thời gian, đơn vị hay nested DTO.
- Test mapper riêng khi mapping phức tạp, nhất là khi field mới/optional xuất hiện.

Với nhiều DTO, MapStruct có thể sinh mapper tại compile time và phát hiện lỗi mapping sớm. Dù dùng thư viện, vẫn phải xem generated behavior, cấu hình unmapped fields và chính sách fields nhạy cảm. **Không map hai chiều vô điều kiện**: request DTO → entity thường cần logic create/update khác nhau; “đảo ngược” response mapper có thể cho phép client sửa field không hợp lệ.

Khi mapping nested collection:

```java
List<LineResponse> lines = order.getLines().stream()
        .map(line -> new LineResponse(
                line.getProductCode(), line.getQuantity()))
        .toList();
```

Đây là **minh họa trong một method nơi `order` và các kiểu DTO đã tồn tại**. Việc gọi `getLines()` có thể kích hoạt lazy query; fetch dữ liệu có kế hoạch trước rồi mới map, tránh N+1 khi xử lý danh sách orders.

## 7. ResponseEntity<T>: nơi đặt quyết định HTTP

Spring MVC hỗ trợ:

- Trả `CustomerResponse` trực tiếp từ `@RestController`: thông thường framework serialize body và trả `200 OK` khi thành công.
- Trả `ResponseEntity<CustomerResponse>`: điều khiển thêm status/headers, ví dụ `201 Created` với `Location`.
- Trả `ResponseEntity<Void>`: khi không có body, ví dụ `204 No Content` cho DELETE thành công.
- Trả `ResponseEntity.of(Optional<CustomerResponse>)`: `Optional.of(dto)` cho `200` kèm body; `Optional.empty()` cho `404` với body rỗng.

Ví dụ controller quyết định status:

```java
@PostMapping("/customers")
public ResponseEntity<CustomerResponse> create(
        @Valid @RequestBody CreateCustomerRequest request) {
    CustomerResponse response = service.create(request);
    URI location = ServletUriComponentsBuilder.fromCurrentRequestUri()
            .path("/{id}")
            .buildAndExpand(response.id())
            .toUri();
    return ResponseEntity.created(location).body(response);
}
```

Đoạn trên minh họa trong controller có imports, `service` và lớp DTO đã định nghĩa; bản runnable đầy đủ ở phần sau.

**201 Created** phù hợp khi server tạo resource mới. Header `Location` nên trỏ đến URI resource; response có thể kèm body DTO mới. **200 OK** thích hợp cho GET thành công hoặc thao tác trả dữ liệu tùy hợp đồng. **204 No Content** phải không có body response; tránh đặt JSON vào status 204. **404 Not Found** khi resource không tìm thấy (sau kiểm tra quyền theo chính sách). **400 Bad Request** thường cho payload JSON sai, thiếu required input/validation error. **409 Conflict** khi vi phạm trạng thái/điều kiện đồng thời của tài nguyên nếu có hợp đồng tương ứng.

Không nhúng `HttpStatus`/`ResponseEntity` vào JPA entity hay repository. Service thuần nghiệp vụ có thể trả DTO/Result/Optional, hoặc ném exception nghiệp vụ; controller/advice chuyển kết quả thành HTTP semantics.

### Có nhất thiết service phải trả response DTO?

Không bắt buộc. Hai kiến trúc đều có thể hợp lý:

1. Service/application query trả `CustomerResponse` trực tiếp vì use case phục vụ API và có quyền biết projection public. Controller chỉ lo HTTP.
2. Service/domain trả object nghiệp vụ, adapter/controller mapper thành DTO. Hợp lý khi cùng logic dùng cho message consumer, batch job hay transport khác.

Điều quan trọng là **dependency hướng đúng** và dữ liệu persistence không bị serialize trực tiếp. Nếu service trả response DTO, đừng để loại DTO đó mang `ResponseEntity` hay Servlet API; như vậy service vẫn không bị trói vào HTTP transport.

## 8. Ví dụ runnable: Spring Boot 3 + Spring MVC + JPA + H2

Ví dụ minh họa hệ thống customer:

- `CustomerEntity` là mô hình lưu trữ chứa trường nội bộ `internalMemo`.
- `CreateCustomerRequest` chỉ cho phép client gửi `displayName` và `email`.
- `CustomerResponse` chỉ công khai `id`, `displayName`, `email`, `createdAt`.
- `CustomerRepository` lưu/đọc entity bằng Spring Data JPA.
- `CustomerService` thực thi transaction, chuẩn hóa theo quy tắc demo và tạo response DTO.
- `CustomerController` xử lý request và trả `201 + Location` hoặc `200/404`.

Tạo dự án từ Spring Initializr với **Java 17+, Spring Boot 3.x**, Maven, dependencies: `spring-boot-starter-web`, `spring-boot-starter-data-jpa`, `spring-boot-starter-validation`, `h2` (runtime), `spring-boot-starter-test` (test). Không cần cơ sở dữ liệu bên ngoài khi dùng H2 embedded; ví dụ dùng JPA schema auto-ddl chỉ để học, **không bật chế độ auto-ddl tùy tiện trên production**.

### 8.1. Khởi động ứng dụng

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 8.2. Entity lưu trữ (không expose trực tiếp)

Tệp `src/main/java/com/example/demo/CustomerEntity.java`:

```java
package com.example.demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

@Entity
@Table(name = "customers")
public class CustomerEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String displayName;

    @Column(nullable = false, length = 254)
    private String email;

    @Column(nullable = false)
    private String internalMemo;

    @Column(nullable = false)
    private Instant createdAt;

    protected CustomerEntity() {
        // JPA cần no-args constructor.
    }

    public CustomerEntity(
            String displayName, String email, String internalMemo) {
        this.displayName = displayName;
        this.email = email;
        this.internalMemo = internalMemo;
        this.createdAt = Instant.now();
    }

    public Long getId() { return id; }
    public String getDisplayName() { return displayName; }
    public String getEmail() { return email; }
    public String getInternalMemo() { return internalMemo; }
    public Instant getCreatedAt() { return createdAt; }
}
```

Dù entity có `getInternalMemo()`, mapper/response DTO không mang trường này ra JSON. Entity là lớp managed bởi JPA, không mang `@JsonIgnore` hoặc annotation HTTP. Việc đặt internal memo ở đây chỉ để chứng minh sự tách biệt; trong production cần chính sách lưu trữ/quyền truy cập với dữ liệu nhạy cảm.

### 8.3. Repository

Tệp `src/main/java/com/example/demo/CustomerRepository.java`:

```java
package com.example.demo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<CustomerEntity, Long> {
}
```

Repository giải quyết persistence, trả `CustomerEntity`/`Optional<CustomerEntity>`. Nó không biết `ResponseEntity`, `HttpStatus`, `Location`, media type hay status code.

### 8.4. Request DTO và response DTO

Tệp `src/main/java/com/example/demo/CreateCustomerRequest.java`:

```java
package com.example.demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
        @NotBlank @Size(max = 100) String displayName,
        @NotBlank @Email @Size(max = 254) String email) {
}
```

Tệp `src/main/java/com/example/demo/CustomerResponse.java`:

```java
package com.example.demo;

import java.time.Instant;

public record CustomerResponse(
        Long id,
        String displayName,
        String email,
        Instant createdAt) {
}
```

DTO có cấu trúc rõ, không phụ thuộc Hibernate. `@Valid` kiểm tra request khi controller khai báo nó. Constraint này kiểm tra cú pháp cơ bản; email có hợp lệ về nghiệp vụ (ví dụ unique và ownership) hay không là việc khác của service/database.

### 8.5. Service và mapping tại transaction boundary

Tệp `src/main/java/com/example/demo/CustomerService.java`:

```java
package com.example.demo;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Optional;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public CustomerResponse create(CreateCustomerRequest request) {
        // Chính sách normalize này chỉ là ví dụ nghiệp vụ.
        String name = request.displayName().strip();
        String email = request.email().strip();

        CustomerEntity entity =
                new CustomerEntity(name, email, "INTERNAL_ONLY");
        CustomerEntity saved = repository.save(entity);

        return toResponse(saved);
    }

    @Transactional(readOnly = true)
    public Optional<CustomerResponse> findById(long id) {
        return repository.findById(id).map(this::toResponse);
    }

    private CustomerResponse toResponse(CustomerEntity entity) {
        return new CustomerResponse(
                entity.getId(),
                entity.getDisplayName(),
                entity.getEmail(),
                entity.getCreatedAt());
    }
}
```

Giải thích:

- `@Transactional` áp dụng cho use case ghi, `readOnly=true` cho use case đọc. Đây là hint tối ưu và ranh giới transaction, không thay thế phân quyền.
- `repository.save` trả entity có ID đã được tạo theo chiến lược IDENTITY dùng trong demo.
- Mapper `toResponse` diễn ra khi entity còn nằm trong use case/transaction, tránh đưa entity live ra serializer.
- `internalMemo` **không xuất hiện** trong response.
- `Optional<CustomerResponse>` diễn đạt có/không có customer mà không kéo `HttpStatus` vào service.
- Ví dụ `strip()` đầu vào là quyết định normalization của ứng dụng; production phải định nghĩa nó trong API contract. Đừng âm thầm lowercase email local-part nếu chưa có chính sách phù hợp.
- Đoạn demo chưa thực hiện kiểm tra tenant/authorization; trong ứng dụng thực phải thêm logic truy cập vào service/query trước khi trả DTO.

### 8.6. Controller chịu trách nhiệm HTTP

Tệp `src/main/java/com/example/demo/CustomerController.java`:

```java
package com.example.demo;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

import java.net.URI;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {

        CustomerResponse result = service.create(request);
        URI location = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .path("/{id}")
                .buildAndExpand(result.id())
                .toUri();

        return ResponseEntity.created(location).body(result);
    }

    @GetMapping(
        path = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CustomerResponse> find(
            @PathVariable("id") long id) {
        return ResponseEntity.of(service.findById(id));
    }
}
```

Controller không biết entity có field `internalMemo` hay DB dùng H2. Nó chỉ nhận DTO, chuyển cho service, xây `Location` và status. `ResponseEntity.of(Optional)` tự chọn `200` với body hoặc `404` khi `Optional.empty()`; response 404 ở ví dụ không có body tùy biến.

**Lưu ý với reverse proxy:** `ServletUriComponentsBuilder.fromCurrentRequestUri()` dựa trên URI request mà ứng dụng nhìn thấy; khi server đứng sau gateway/proxy, cấu hình forwarded headers chuẩn và tin cậy mới giúp `Location` phản ánh public URL. Không tự tin tưởng header `X-Forwarded-*` từ client không đáng tin. Nếu muốn đường dẫn tương đối, xác định hợp đồng URL và cách phát Location tương ứng.

### 8.7. Cấu hình database demo

Tệp `src/main/resources/application.properties` cho ứng dụng **học tập**:

```properties
spring.datasource.url=jdbc:h2:mem:customers;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

- `create-drop` chỉ phù hợp môi trường test/demo vì xóa/tạo schema theo vòng đời ứng dụng.
- `open-in-view=false` giúp thực hành ranh giới transaction rõ ràng; mapper chuyển object trước khi trả response. Không dựa vào lazy database reads trong giai đoạn render.
- Trong production, dùng migration có quản lý (Flyway/Liquibase) và database thật, không dựa vào embedded H2 hoặc tự động drop schema.

Chạy Maven Wrapper đã tạo sẵn:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Lưu ý các lớp Spring/JPA không thể biên dịch độc lập với `javac` nếu không có dependencies. Tệp/command ở phần này đủ để định hình ứng dụng **khi đã tạo project Boot chứa dependencies và Maven Wrapper nêu trên**.

## 9. HTTP request/response của ví dụ

### 9.1. Tạo customer: status 201 và Location

```bash
curl -i http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"displayName":"Lan","email":"lan@example.com"}'
```

Ví dụ response (ID/timestamp là minh họa, khác nhau mỗi lần chạy):

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/customers/1
Content-Type: application/json

{"id":1,"displayName":"Lan","email":"lan@example.com","createdAt":"2026-10-21T04:00:00Z"}
```

Các thuộc tính `id` và `createdAt` do server tạo; không lấy cứng giá trị minh họa làm test. **Không có `internalMemo`**, dù DB lưu trường đó. `Location` trỏ đến URI resource mới được tạo.

### 9.2. GET một customer

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/customers/1
```

Nếu customer id=1 tồn tại, status `200` và body dùng cùng cấu trúc `CustomerResponse`. Nếu không có record id=9999:

```bash
curl -i http://localhost:8080/api/customers/9999
```

Dự kiến `404 Not Found`, không có JSON DTO; `ResponseEntity.of(Optional.empty())` thường tạo body rỗng. Không đồng nhất “không tìm thấy” với “chưa đăng nhập/không có quyền”: trong sản phẩm thật, chiến lược 403 hay che tồn tại tài nguyên bằng 404 là quyết định security/contract riêng.

### 9.3. Validation input, không tạo record

```bash
curl -i http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  --data '{"displayName":"","email":"invalid"}'
```

Với `spring-boot-starter-validation`, `@Valid` trên request DTO từ chối tên trống/email sai cú pháp. Mặc định thường là `400 Bad Request` (`MethodArgumentNotValidException`). **Không cam kết định dạng body lỗi**; Spring Boot có thể trả JSON lỗi khác nhau tùy cấu hình `ProblemDetail`/ControllerAdvice.

Với `Content-Type: text/plain` gửi vào endpoint chỉ `consumes=application/json`, thường `415 Unsupported Media Type`, xảy ra ở điều kiện media type trước validation. Với `Accept: application/xml` nhưng endpoint chỉ `produces=application/json`, thường `406 Not Acceptable`. Đây là vấn đề giao thức, không phải lỗi entity mapping.

## 10. Kiểm thử tích hợp MockMvc: chứng minh ranh giới

Dùng dependency `spring-boot-starter-test` (JUnit Jupiter, MockMvc). Test tích hợp sau chạy với H2 cấu hình demo và bao phủ **HTTP response contract**. Đặt tại `src/test/java/com/example/demo/CustomerControllerTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

import com.jayway.jsonpath.JsonPath;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class CustomerControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void createsResourceWithLocationAndPublicDtoOnly() throws Exception {
        MvcResult created = mvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(
                    "{\"displayName\":\"Lan\",\"email\":\"lan@example.com\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.email").value("lan@example.com"))
            .andExpect(jsonPath("$.internalMemo").doesNotExist())
            .andReturn();

        Number id = JsonPath.read(
                created.getResponse().getContentAsString(), "$.id");

        mvc.perform(get("/api/customers/{id}", id.longValue())
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(id.intValue()))
            .andExpect(jsonPath("$.internalMemo").doesNotExist());
    }

    @Test
    void missingCustomerReturns404() throws Exception {
        mvc.perform(get("/api/customers/{id}", Long.MAX_VALUE))
            .andExpect(status().isNotFound());
    }

    @Test
    void invalidInputReturns400() throws Exception {
        mvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"\",\"email\":\"bad\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void wrongRequestMediaTypeReturns415() throws Exception {
        mvc.perform(post("/api/customers")
                .contentType(MediaType.TEXT_PLAIN)
                .content("Lan"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Chạy:

```bash
./mvnw test
```

Windows:

```powershell
.\mvnw.cmd test
```

Đây là **mẫu code kiểm thử**, không phải khẳng định đã thực thi trong project hiện tại. Nếu dự án đã bật Spring Security, CSRF, tenant filter, Jackson serialization hoặc DB constraint riêng, phải cấu hình test và assertions đúng với môi trường đó. Trong test trên, `@Transactional` giúp các thay đổi DB trên thread test/MockMvc thường được rollback sau test; HTTP server thật dùng transaction khác nên không suy từ test này rằng mọi end-to-end request đều tự rollback.

### Test thêm khi hợp đồng phức tạp

- Kiểm tra JSON **không có field nội bộ** bằng `jsonPath("$.internalMemo").doesNotExist()`. Đây là test regression quan trọng khi entity về sau thêm getters.
- Kiểm tra `Location` thực sự trỏ tới URI có thể GET, không chỉ header tồn tại.
- Kiểm tra status/response shape khi data không tồn tại, input validation lỗi, requester không đủ quyền.
- Kiểm tra ngày `createdAt` có thể parse theo ISO-8601, thay vì so sánh timestamp bằng chuỗi cố định.
- Nếu có nested DTO, test không serialize quan hệ ngoài danh sách công khai.
- Với list endpoint, test query count/pagination để tránh N+1 khi dữ liệu tăng.

## 11. Mapping DTO khi có quan hệ: tránh vòng lặp và N+1

Giả sử entity `OrderEntity` chứa `@ManyToOne(fetch=LAZY) CustomerEntity customer` và `@OneToMany List<OrderLineEntity> lines`. Một response hợp đồng có thể là:

```java
public record OrderResponse(
        Long id,
        CustomerSummary customer,
        java.util.List<LineResponse> lines) {}

public record CustomerSummary(Long id, String displayName) {}

public record LineResponse(
        String productCode, int quantity) {}
```

Những record này **là đoạn thiết kế DTO minh họa**, không phải tệp độc lập có package/import hoàn chỉnh. Mapper quyết định chỉ đưa `customer.id`, `customer.displayName` và vài field của line ra ngoài; không serialize `customer.orders`, `orderLine.order` hay field quản trị.

Cẩn thận:

- Đọc `order.getCustomer().getDisplayName()` hoặc `order.getLines()` có thể kích hoạt lazy query. Cần fetch plan phù hợp theo use case.
- Với list 100 orders, mỗi order lại truy vấn customer/lines có thể thành N+1 dù response DTO rất nhỏ.
- Dùng **fetch join**, `@EntityGraph`, projection hoặc truy vấn riêng theo batch tùy cardinality và pagination. Fetch join collection cùng pageable có thể tạo duplicate/khó phân trang; đừng tự thêm `JOIN FETCH` mọi nơi.
- Map trong transaction nơi quan hệ có thể được truy cập an toàn, rồi trả DTO. `open-in-view=false` giúp phát hiện phụ thuộc lazy khi vượt ranh giới.
- Không đưa `HibernateProxy`/`PersistentCollection` ra JSON như đối tượng DTO.

Đặt JSON nested ở mức độ vừa đủ; client có thể gọi endpoint tài nguyên liên quan nếu dữ liệu quá lớn hoặc quyền đọc khác nhau.

## 12. DTO projection giúp tối ưu việc truy vấn

Mapping entity đầy đủ → DTO là giải pháp rõ ràng, nhưng có thể tốn RAM/query khi chỉ cần vài cột. Spring Data JPA hỗ trợ **class-based DTO projections**, có thể dùng Java record nếu constructor phù hợp.

Ví dụ JPQL constructor expression:

```java
public interface CustomerQueryRepository
        extends org.springframework.data.repository.Repository<CustomerEntity, Long> {

    @org.springframework.data.jpa.repository.Query(
        "select new com.example.demo.CustomerResponse(" +
        "c.id, c.displayName, c.email, c.createdAt) " +
        "from CustomerEntity c where c.id = :id")
    java.util.Optional<CustomerResponse> findPublicById(
            @org.springframework.data.repository.query.Param("id") Long id);
}
```

Đây là **tệp minh họa** cần đặt đúng package, có `CustomerEntity`/`CustomerResponse` đã khai báo; có thể thêm thành repository riêng nếu muốn thử. Ý tưởng là query lấy trực tiếp các cột DTO cần, thay vì nạp entity đầy đủ rồi map. JPQL `new` cần **tên class đầy đủ**, constructor phù hợp đúng thứ tự và kiểu; không phải mọi native query tự map vào record được.

Lựa chọn:

| Cách đọc | Khi phù hợp | Điều cần theo dõi |
| --- | --- | --- |
| Entity → manual mapper | Domain logic cần entity, response nhỏ | Lazy loading, N+1, field nội bộ |
| Entity → MapStruct mapper | Mapping nhiều field, DTO lặp lại | Cấu hình unmapped fields và nested mapping |
| Spring Data interface projection | Chỉ cần một vài property/query | Nested projection có thể join sâu tùy cấu trúc |
| Class/record DTO projection | Query đọc thuần, chỉ vài cột | Constructor mapping, JPQL/native query |
| Truy vấn SQL tối ưu + mapping thủ công | Read-heavy endpoint rất phức tạp | SQL/database coupling và test |

**Projection không thay authorization**: nếu truy vấn projection chứa email, dữ liệu vẫn đã được lấy từ DB, dù DTO khác entity. Áp điều kiện tenant/user ở query hoặc service theo chính sách; ưu tiên giới hạn dữ liệu sớm nhất có thể.

## 13. List response và phân trang

Trả nguyên `List<CustomerEntity>` cho hàng chục nghìn bản ghi khiến response nặng và lộ schema. Khi API trả danh sách, dùng dạng payload đã thiết kế:

```json
{
  "items": [
    {"id":1,"displayName":"Lan","email":"lan@example.com",
     "createdAt":"2026-10-21T04:00:00Z"}
  ],
  "page": 0,
  "size": 20,
  "totalItems": 1
}
```

Một DTO riêng:

```java
public record PageResponse<T>(
        java.util.List<T> items,
        int page,
        int size,
        long totalItems) {}
```

Đoạn này là **thiết kế DTO độc lập có thể đặt trong một tệp Java**, nhưng chưa phải controller runnable. Dùng `Pageable`/`Page<Entity>` ở repository, map mỗi entity thành response DTO rồi đóng gói các thông số paging. Tài liệu API phải nói `page` bắt đầu từ 0 hay 1, thứ tự sort ổn định và maximum `size`. Tránh expose trực tiếp cấu trúc `PageImpl` hoặc Hibernate internals chỉ vì chúng có thể serialize.

Khi phân trang:

- Đảm bảo sort có tie-breaker ổn định nếu muốn tránh mất/trùng bản ghi do nhiều hàng có cùng timestamp.
- Dùng kích thước trang tối đa, limit dữ liệu trả về và projection nếu phù hợp.
- Với dữ liệu lớn/thay đổi nhanh, cân nhắc cursor pagination; không bắt buộc nếu nhu cầu đơn giản.
- Xem log/query metrics; DTO không tự giảm số row query hoặc query N+1.

## 14. Nullability, Optional, định dạng và thay đổi hợp đồng

### 14.1. Null và dữ liệu chưa có

Ví dụ customer có `phoneNumber` tùy chọn. API có thể trả:

```json
{"phoneNumber":null}
```

hoặc bỏ hẳn `phoneNumber` tùy hợp đồng. Jackson có thể được cấu hình `@JsonInclude(Include.NON_NULL)` để bỏ field null; tuy nhiên đừng thay đổi chính sách chỉ để response “đẹp hơn”, vì client có thể phân biệt missing và explicit null.

- Thiết kế DTO nói rõ field nào required, field nào optional.
- Tránh để `Optional<T>` làm field DTO chỉ để biểu thị nullable; với nhiều serializer/config, behavior không rõ bằng trường nullable và schema tường minh.
- `record` không cấm thành phần có `null`. Nếu client không được phép nhận null, kiểm tra bất biến ở mapper/service hoặc bằng contract test.
- Dùng `Instant` cho thời điểm UTC; `LocalDate` cho ngày không có timezone; không trả epoch string khó hiểu khi API yêu cầu ISO-8601.
- Không đưa `BigDecimal` qua `double` rồi đánh mất độ chính xác; mô tả precision/scale cho giá tiền.

### 14.2. CREATE/PUT/PATCH cần DTO riêng

Request và response DTO thường **không đối xứng**:

- `CreateCustomerRequest` không có `id`, `createdAt` vì server sinh chúng.
- `UpdateCustomerRequest` có thể yêu cầu toàn bộ field người dùng sửa được.
- `PatchCustomerRequest` thường cần phân biệt field **vắng mặt**, explicit `null` và giá trị mới. Plain nullable Java field trong DTO có thể gộp missing/null sau Jackson deserialization.
- `CustomerResponse` chứa metadata để client biết kết quả, nhưng không buộc client gửi lại mọi field.

Ví dụ PATCH:

| Input JSON | Ý nghĩa ví dụ |
| --- | --- |
| `{}` | Không thay đổi email |
| `{"email":null}` | Xóa email nếu policy cho phép |
| `{"email":""}` | Đặt chuỗi rỗng hoặc validation error |
| `{"email":"new@example.com"}` | Thay email |

Không dùng quy tắc `if (request.email() != null) update` nếu hợp đồng yêu cầu explicit null để xóa: cách đó đã mất phân biệt missing/null. Có thể dùng `JsonNode`/presence tracking/JSON Merge Patch theo hợp đồng. Trong JSON Merge Patch (RFC 7396), null trong patch có semantics xóa member. Đây là thiết kế **input**, không nên làm thay đổi response DTO ngẫu nhiên.

### 14.3. DTO là hợp đồng cần versioning

Thay đổi tương đối an toàn có thể là **thêm field tùy chọn** nếu client chịu được unknown fields; thay đổi tên/kiểu field hoặc ý nghĩa giá trị có thể phá client. Một số client deserialize nghiêm ngặt nên ngay cả thêm field cũng cần đánh giá. Các thay đổi có ý nghĩa lớn cần chiến lược tương thích: endpoint version, media type version hoặc ra DTO mới theo contract.

Không dùng tên field dựa trên entity như `customerV3TableId` nếu client không cần biết. Khi refactor database, ưu tiên giữ nguyên JSON contract; mapping layer chịu trách nhiệm bắc cầu.

## 15. Nơi xử lý lỗi HTTP: service kết quả nghiệp vụ, controller/advice response

Trong ví dụ, `service.findById` trả `Optional<CustomerResponse>` và controller trả `ResponseEntity.of(...)`: đây là thiết kế đơn giản cho 404.

Ứng dụng lớn có thể dùng exception nghiệp vụ như `CustomerNotFound`, `CustomerConflict`, rồi ánh xạ tại `@RestControllerAdvice` thành status/body lỗi chuẩn. Lúc đó:

- Service nêu vấn đề **nghiệp vụ**, không rải `new ResponseStatusException(HttpStatus.NOT_FOUND, ...)` ở sâu trong repository nếu muốn giữ khả năng tái sử dụng nhiều transport.
- Controller/advice quyết định `404`, `409`, `400`, headers, `ProblemDetail` và định dạng thông báo an toàn.
- Validation của `@Valid @RequestBody` thường gây `MethodArgumentNotValidException` và 400 trước khi vào service; không phải mọi lỗi nghiệp vụ đều là validation annotation.
- JSON sai cú pháp gây lỗi đọc body (thường 400) trước khi tạo request DTO; `consumes` không khớp thường 415.
- Ngoại lệ hạ tầng/database không nên bị bắt bằng `catch (Exception) { return 400; }`, vì lỗi nội bộ 500 sẽ bị báo nhầm là lỗi client.

Spring Framework hỗ trợ `ProblemDetail` (RFC 9457) và `ResponseEntityExceptionHandler` để tùy chỉnh lỗi có cấu trúc. Khi tạo body lỗi, hạn chế `detail` chứa thông tin nhạy cảm hay tên bảng/query. Mã lỗi public và correlation ID giúp client debug mà không để lộ internals.

## 16. Bảo mật DTO: chỉ chọn field chưa đủ

Bảo vệ dữ liệu có hai bước độc lập nhưng liên quan:

1. **Authorization trước hoặc trong truy vấn:** user hiện tại có quyền đọc customer này không? Có áp tenant ID và phạm vi hàng dữ liệu đúng không?
2. **Field-level visibility:** sau khi có quyền đọc resource, user có được nhận email, địa chỉ, giá mua nội bộ hoặc trạng thái gian lận không?

DTO đảm bảo không serializing những trường **không được khai báo trong DTO đó**. Nếu mapping lấy thêm email cho user không có quyền xem, DTO vẫn lộ email. Với nhiều nhóm quyền, dùng response schema khác nhau hoặc mapper phân quyền rõ ràng; đừng serialize một “admin response” rồi dựa hoàn toàn vào client ẩn field.

Các rủi ro thực tế:

- **Mass assignment** khi bind entity từ JSON đầu vào.
- **Broken Object Level Authorization (BOLA)** khi client đổi `/customers/42` thành ID người khác.
- **Sensitive Data Exposure** khi API trả raw entity hoặc log body.
- **Inconsistent projection** khi GET dùng DTO an toàn nhưng endpoint list/export trả thẳng entity.
- **Caching dữ liệu cá nhân:** `Cache-Control` và private/public cache phải phù hợp; DTO không tự giải quyết cache leak.
- **Lỗi debug:** `toString()` của DTO hoặc entity có thể in email/token vào log; cân nhắc masking.

Test nên bao phủ các endpoint của cùng resource (create/get/list/export), không chỉ một GET happy-path.

## 17. Hiệu năng và transaction boundary

DTO và entity separation thường cải thiện tính kiểm soát nhưng không tự động làm API nhanh hơn. Để đo:

- **Số query SQL:** N+1 có thể xuất hiện ở bước mapping quan hệ.
- **Kích thước dữ liệu lấy từ DB:** nếu chỉ cần vài cột, projection có thể giảm I/O.
- **Kích thước JSON:** không đưa quan hệ/metadata thừa vào response.
- **Độ sâu nested data:** mô hình cây quá lớn làm serialization tốn CPU/RAM.
- **Transaction duration:** tránh giữ transaction mở khi response được serialize/chờ mạng; map DTO trong transaction rồi đóng.
- **Pagination:** giới hạn số bản ghi và kết hợp sort ổn định.
- **Cache:** DTO public ổn định thuận lợi cho conditional requests (`ETag`/`Last-Modified`) nếu có chiến lược nhất quán.

Ví dụ status HTTP `304 Not Modified` liên quan cache validator của representation, khác chuyện object lưu trữ có thay đổi hay không. Không gắn raw `@Version` của JPA làm HTTP `ETag` mà chưa xem xét quyền riêng tư, biến thể response và semantics (ETag mạnh/yếu). ETag nên đại diện cho representation mà client nhận theo hợp đồng.

## 18. Anti-pattern và cách thay thế

| Anti-pattern | Vấn đề | Giải pháp |
| --- | --- | --- |
| `@GetMapping` trả `CustomerEntity` | Có thể lộ field, lazy proxy, vòng lặp quan hệ | Map sang `CustomerResponse` |
| `CreateCustomerRequest` dùng nguyên entity | Overposting, lẫn ID/server fields | Input DTO chỉ có field client được phép sửa |
| Repository trả `ResponseEntity<?>` | Persistence phụ thuộc HTTP | Repository trả entity/projection; controller quyết định status |
| Service trả `HttpServletResponse` | Trói business logic vào Servlet | Service trả kết quả/DTO; controller/advice lo HTTP |
| Mapping `BeanUtils.copyProperties` vô điều kiện | Dễ copy field ngoài chủ đích, mất kiểm soát | Mapper explicit/MapStruct với rule rõ |
| Một DTO “God Object” cho mọi endpoint | Quá nhiều field null/khó phân quyền | DTO chuyên biệt theo use case/public role |
| DTO nested chứa JPA entity | Vẫn lộ lazy/proxy/field nội bộ | Nested DTO cũng phải public-only |
| Tạo DTO sau khi transaction đóng rồi đọc lazy field | LazyInitializationException | Fetch/mapping trong transaction |
| Bật Open Session in View chỉ để fix serialize | Che phụ thuộc truy vấn khi render | Tối ưu fetch và mapping explicit |
| Trả toàn `Page<Entity>` | Lộ implementation shape và entity | Page response DTO có contract ổn định |
| Đổi tên field JSON theo mỗi schema migration | Phá client | Giữ contract và đổi mapper |
| Bỏ qua tenant check vì DTO đã bỏ field bí mật | Vẫn có thể lộ data của người khác | Authorization + field visibility |
| Trả `204` với body DTO | Vi phạm semantics response no-content | Dùng `200/201` nếu có body, hoặc `204` body rỗng |
| Trả `500` như lỗi validation cho mọi request | Client khó xử lý và che lỗi thật | Phân loại lỗi request/business/server đúng tầng |

## 19. Checklist review thiết kế response API

### Hợp đồng dữ liệu

1. JSON có đúng field mà client cần và không có field nội bộ không?
2. Tên field, kiểu số, timestamp, enum, null và collection có được định nghĩa ổn định không?
3. Request DTO chỉ chứa những giá trị client được phép gửi? Response DTO chỉ chứa dữ liệu client được phép nhận?
4. DTO nested có mức sâu/hạn mức phù hợp không? Có field nào lặp, quá rộng hoặc đòi quan hệ lazy vô ý?
5. Thay đổi schema DB có thể diễn ra mà không đổi JSON response không?

### Luồng ứng dụng và HTTP

6. Controller chịu trách nhiệm `ResponseEntity`, `Location`, HTTP status/headers không?
7. Service/repository có tránh phụ thuộc trực tiếp `HttpServletRequest`, `ResponseEntity`, `HttpStatus` khi không cần không?
8. `201` kèm `Location` chính xác khi tạo resource? GET thành công 200? Missing resource 404? 204 không body?
9. Validation, lỗi JSON, business conflict và server failure có response semantics riêng?
10. Có kiểm thử response schema và loại trừ các field riêng tư không?

### Data và security

11. Fetch plan/projection đã được đo để tránh N+1?
12. DTO được tạo trước khi trả ra khỏi transaction nếu cần đọc lazy data?
13. Authorization theo resource/tenant và field-level đã được áp?
14. Endpoint list/export cũng tuân theo DTO policy giống endpoint detail?
15. Log/cache/header có thể rò rỉ dữ liệu công khai chưa được phép không?

## 20. Câu hỏi tự kiểm tra

**1.** Vì sao không nên trả JPA entity trực tiếp từ `@RestController`?

**Đáp án:** Entity có thể lộ field nội bộ, ràng buộc API vào schema persistence, kích hoạt lazy query/vòng lặp JSON, gây khó khăn khi versioning. Response DTO xác định rõ contract công khai.

**2.** Input DTO và response DTO khác nhau thế nào?

**Đáp án:** Input DTO chỉ chứa field client được phép gửi và cần validate; response DTO chứa field server cam kết trả. Các giá trị `id`/`createdAt` do server sinh thường chỉ xuất hiện trong response.

**3.** Service có nhất thiết phải trả `ResponseEntity<CustomerResponse>`?

**Đáp án:** Không. Nó có thể trả `CustomerResponse`, `Optional<CustomerResponse>` hoặc kết quả nghiệp vụ. HTTP status/headers nên được xử lý tại controller/advice.

**4.** Làm sao trả 201 và Location sau POST create?

**Đáp án:** Tạo DTO chứa ID resource, xây URI, dùng `ResponseEntity.created(location).body(dto)`.

**5.** Có DTO rồi thì lazy loading/N+1 tự hết không?

**Đáp án:** Không. Mapper vẫn có thể đọc lazy relations và gây truy vấn thêm. Cần transaction boundary và fetch/query phù hợp.

**6.** Chỉ cần DTO không có field `internalMemo` là đủ bảo mật không?

**Đáp án:** Không. DTO chặn field đó khỏi serialization, nhưng phải kiểm tra người gọi có quyền đọc resource và những field DTO chứa (như email).

**7.** Khi truy vấn chỉ cần ID và tên, có nhất thiết fetch cả entity?

**Đáp án:** Không. Có thể dùng Spring Data JPA DTO projections/JPQL constructor expressions khi phù hợp, đồng thời đảm bảo query áp đúng authorization.

**8.** Nếu không tìm thấy record, service trả `Optional.empty()`, controller `ResponseEntity.of(...)` làm gì?

**Đáp án:** Trả HTTP 404; nếu có DTO thì trả 200 và body DTO.

**9.** Vì sao không dùng cùng một nullable DTO cho CREATE và PATCH khi explicit null có nghĩa “xóa”?

**Đáp án:** JSON field missing và explicit null có thể thành cùng Java null khi deserialize, làm mất ý định. PATCH cần cơ chế presence tracking hoặc chuẩn patch rõ ràng.

**10.** Mapper dùng cách copy tự động có thay thế review bảo mật không?

**Đáp án:** Không. Cần giới hạn field rõ ràng, policy theo role, test response công khai và đánh giá từng trường khi thêm mới.

## 21. Tài liệu tham khảo

- Spring Framework — `@ResponseBody` và serializing response: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html
- Spring Framework — `ResponseEntity`, status/headers/body: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html
- Spring Framework — `@RequestBody` và validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — MVC Controller Return Types: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — Error Responses / ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Data JPA — Projections: https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html
- Spring Data JPA — Transactionality: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Jakarta Persistence specification: https://jakarta.ee/specifications/persistence/
- RFC 9110 — HTTP Semantics (200, 201, 204, 404, Location, caching): https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- OWASP — API Security Top 10: https://owasp.org/API-Security/editions/2023/en/0x11-t10/
