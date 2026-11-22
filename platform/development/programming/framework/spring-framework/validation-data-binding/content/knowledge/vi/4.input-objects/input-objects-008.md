# Giữ dữ liệu đầu vào độc lập với entity và trạng thái nội bộ

## 1. Vì sao cần một ranh giới giữa request và entity?

Một HTTP request là dữ liệu do bên ngoài kiểm soát. Entity lưu trữ và trạng thái nội bộ của ứng dụng lại chứa nhiều thuộc tính **không được phép** do người gọi tùy ý quyết định: khóa chính, chủ sở hữu, vai trò, trạng thái xử lý, người phụ trách, thời điểm tạo, hạn mức, kết quả tính toán, số phiên bản, v.v.

Ví dụ một API tạo yêu cầu hỗ trợ chỉ cần hai trường do khách hàng cung cấp:

~~~json
{
  "title": "Không đăng nhập được",
  "description": "Ứng dụng báo lỗi sau khi nhập mật khẩu"
}
~~~

Nếu controller nhận trực tiếp entity có các setter cho `id`, `status`, `assignedAgentId` và `createdAt`, kẻ gửi request có thể thử thêm:

~~~json
{
  "title": "Không đăng nhập được",
  "description": "Ứng dụng báo lỗi sau khi nhập mật khẩu",
  "id": 9001,
  "status": "RESOLVED",
  "assignedAgentId": 123,
  "createdAt": "2000-01-01T00:00:00Z"
}
~~~

Vấn đề ở đây là **mass assignment**, còn gọi là *over-posting*: quá trình ánh xạ tự động cho phép dữ liệu ngoài ý muốn chảy vào thuộc tính nội bộ. API có thể bị thay đổi trạng thái, phá vỡ tính toàn vẹn hoặc vượt ranh giới phân quyền ngay cả khi request có cú pháp JSON hợp lệ.

Một thiết kế nguy hiểm thường trông như sau:

~~~java
// VÍ DỤ KHÔNG AN TOÀN: chỉ để phân tích; không sử dụng trong ứng dụng.
@PostMapping("/tickets")
TicketEntity create(@RequestBody TicketEntity incoming) {
    return ticketRepository.save(incoming);
}
~~~

Đoạn trên nhận toàn bộ entity từ bên ngoài, rồi chuyển thẳng cho persistence. Nếu entity có thể được deserialization vào những thuộc tính nhạy cảm, client có cơ hội ghi các thuộc tính đó. Việc có annotation `@Valid` hoặc ràng buộc `@NotNull` **không** tự xác định quyền được sửa từng field.

**Nguyên tắc cốt lõi:** request biểu diễn **ý định và các giá trị được phép khai báo**; entity biểu diễn **trạng thái miền nghiệp vụ đang được quản lý**. Ứng dụng phải chủ động chuyển đổi giữa hai mô hình, đồng thời kiểm tra quyền và quy tắc chuyển trạng thái.

## 2. Các loại đối tượng ở ranh giới

| Loại | Do ai quyết định trường nào tồn tại? | Nội dung nên có | Điều không nên làm |
| --- | --- | --- | --- |
| Request DTO / Form object | Hợp đồng API do server định nghĩa; giá trị do client gửi | Chỉ các trường được phép nhập tại thao tác cụ thể | Chứa `isAdmin`, `ownerId`, `status` nếu client không có quyền quyết định |
| Entity / Aggregate | Mô hình nghiệp vụ và persistence | Định danh, trạng thái, quan hệ, bất biến, version, audit | Bind trực tiếp mọi thuộc tính từ request |
| Service / Domain operation | Mã nghiệp vụ phía server | Quyết định tạo/cập nhật, chính sách trạng thái, nguồn giá trị tin cậy | Sao chép toàn bộ thuộc tính DTO sang entity mà không xem xét |
| Response DTO | Hợp đồng dữ liệu công khai mà server muốn trả | Giá trị đủ cho giao diện/client | Tự động trả mọi thuộc tính nội bộ của entity |

Luồng đề xuất:

~~~text
HTTP/form/JSON (không tin cậy)
           |
           v
  Request DTO chỉ chứa input hợp lệ cho thao tác
           |
           v
  Binding / deserialization + type conversion
           |
           v
  Validation cú pháp và ràng buộc dữ liệu
           |
           v
  Service: xác thực quyền, đọc trạng thái hiện tại,
  kiểm tra quy tắc nghiệp vụ, ánh xạ có chủ đích
           |
           v
   Entity/Aggregate + Repository + transaction
           |
           v
   Response DTO (chỉ các trường được công bố)
~~~

Một kiểu entity có thể được sử dụng ở nhiều thao tác, nhưng request DTO thường nên **riêng cho từng mục đích**: `CreateTicketRequest` không giống `UpdateTicketRequest`, `AssignTicketRequest` hay `CloseTicketRequest`. Tách theo hành động ngăn người gọi tự thêm các trường nghiệp vụ không thuộc quyền của mình.

Ví dụ, đối với một ticket:

- **Client được nhập khi tạo:** `title`, `description`.
- **Server cấp phát/đặt giá trị:** `id`, `createdAt`, `status = OPEN`, `version`.
- **Người có quyền chuyên biệt mới được thao tác:** `assignedAgentId`, chuyển `status` từ `OPEN` sang `RESOLVED`.
- **Dữ liệu trả về:** chỉ các thuộc tính cần thiết; không mặc nhiên trả trường nội bộ hay bí mật.

Cũng cần tách **input DTO** khỏi **response DTO**: API có thể cho xem trạng thái `status` nhưng không đồng nghĩa cho sửa nó.

## 3. Binding trong Spring: hai đường đi khác nhau

### 3.1. `@ModelAttribute`: DataBinder gắn dữ liệu biểu mẫu

Với HTML form hoặc request parameters, Spring MVC dùng cơ chế data binding của `WebDataBinder` để xây dựng hoặc cập nhật model attribute. Cơ chế này có thể bao gồm constructor binding và property binding. Nếu model object là entity nhiều setter, field ngoài ý muốn có thể được gắn vào entity.

Để giảm rủi ro:

1. Ưu tiên form object/DTO chỉ mô tả những trường người dùng được nhập, hoặc immutable object với constructor/record và các tham số được kiểm soát.
2. Nếu phải dùng property binding, khai báo whitelist bằng `WebDataBinder.setAllowedFields(...)`; không dùng blacklist làm biện pháp chính.
3. Kiểm tra `BindingResult` để xử lý lỗi chuyển kiểu, validation và, khi cần, các trường bị chặn qua `getSuppressedFields()`.
4. Không đưa trực tiếp entity đang được JPA quản lý vào binding request; chỉ lấy entity trong service sau khi biết danh tính, quyền truy cập và thao tác được phép.

Ví dụ minh họa cho **form object có setter** (đoạn trích từ controller, không phải một ứng dụng độc lập):

~~~java
@InitBinder("ticketForm")
void configureTicketForm(WebDataBinder binder) {
    binder.setAllowedFields("title", "description");
}

@PostMapping("/tickets/form")
String submit(
        @Valid @ModelAttribute("ticketForm") TicketForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "ticket-form";
    }
    // Gọi service để tự ánh xạ những trường cho phép.
    ticketService.createFromForm(form);
    return "redirect:/tickets";
}
~~~

Trong đoạn trích, `TicketForm` và `createFromForm` được hiểu là các thành phần ứng dụng đã có; phần chạy độc lập ở mục 5 sẽ dùng JSON. `BindingResult` phải nằm **ngay sau** model attribute tương ứng nếu controller muốn xử lý lỗi tại chỗ. `setAllowedFields` giới hạn **property binding**; việc cho phép một tên trường chỉ là lớp bảo vệ bổ sung, không thay thế kiểm tra quyền nghiệp vụ.

### 3.2. `@RequestBody`: JSON được deserialize bởi message converter

Với `@RequestBody` JSON trong Spring MVC, `HttpMessageConverter` (thường là Jackson) đọc body thành đối tượng Java. Đường đi này **không đơn giản là cùng lệnh property binding của `WebDataBinder` áp dụng cho form**. Vì vậy, whitelist trong `@InitBinder` không phải cơ chế để chặn các thuộc tính JSON lạ.

Mẫu nên dùng:

~~~java
@PostMapping("/tickets")
ResponseEntity<TicketResponse> create(
        @Valid @RequestBody CreateTicketRequest request) {
    return ResponseEntity.ok(ticketService.create(request));
}
~~~

Đây là đoạn minh họa trong một controller có sẵn; ví dụ thực thi đầy đủ ở mục 5 còn trả `201 Created`.

- Jackson chỉ có thể đọc các trường mà hợp đồng DTO/deserializer cho phép. Một Java `record` request đơn giản có hai component sẽ không có component `status` để ghi vào entity.
- `@Valid` kích hoạt Bean Validation đối với request DTO khi hạ tầng validator phù hợp được cấu hình. Ràng buộc như `@NotBlank`, `@Size`, `@Email` mô tả **dạng dữ liệu hợp lệ**, chưa đủ để quyết định caller có quyền đổi một resource hay không.
- Trong Spring MVC thông thường, lỗi Bean Validation với `@Valid @RequestBody` dẫn đến `MethodArgumentNotValidException` (HTTP 400 theo xử lý mặc định), hoặc controller có thể xử lý trực tiếp bằng `Errors`/`BindingResult` đặt ngay sau tham số nếu chọn cách đó. Lỗi JSON không parse được, sai kiểu nghiêm trọng hoặc thuộc tính không xác định khi cấu hình Jackson nghiêm ngặt thường qua `HttpMessageNotReadableException`.
- Mặc định nhiều cấu hình Jackson bỏ qua thuộc tính JSON chưa biết; muốn **từ chối** chứ không chỉ **bỏ qua** dữ liệu ngoài hợp đồng, hãy bật `FAIL_ON_UNKNOWN_PROPERTIES` và xem xét các ngoại lệ/cấu hình `@JsonIgnoreProperties` của dự án.
- Không dùng `@JsonIgnore` làm toàn bộ hàng rào bảo vệ. Annotation JSON quyết định hành vi serialize/deserialize, nhưng ranh giới đáng tin cậy hơn là **DTO riêng + ánh xạ tường minh + phân quyền nghiệp vụ**.

### 3.3. Bind được, validate được, vẫn chưa chắc được phép

Cần phân biệt ít nhất ba loại kiểm tra:

| Câu hỏi | Nơi xử lý thường gặp | Ví dụ |
| --- | --- | --- |
| Giá trị chuyển được sang kiểu Java không? | Converter / binder / Jackson | `"abc"` không đổi được thành số |
| Dữ liệu có thỏa ràng buộc DTO không? | Bean Validation / Spring Validator | Tiêu đề không được trống, độ dài tối đa 100 |
| Người gọi có quyền thực hiện hành động và đổi trạng thái không? | Service/domain/security | Người A không được đóng ticket của người B; trạng thái đã đóng không được sửa tùy tiện |

Ngay cả request DTO có `@Valid` không lỗi, service vẫn cần kiểm tra chính sách, trạng thái hiện tại và quan hệ người dùng. Nên lấy `currentUserId` từ **security context đã xác thực**, không dùng `ownerId` do JSON/query param gửi tới rồi tin đó là danh tính hợp lệ.

## 4. Thiết kế DTO trước khi viết controller

Xây dựng hợp đồng input bắt đầu bằng danh sách field client **thực sự được phép** thay đổi.

Ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateTicketRequest(
        @NotBlank @Size(max = 100) String title,
        @NotBlank @Size(max = 1000) String description
) {}
~~~

Đây là định nghĩa record độc lập có thể biên dịch trong một source file cùng tên. Hai field đủ cho thao tác tạo. Không khai báo `id`, `status`, `createdAt` hay `assignedAgentId` vì không thuộc quyền nhập của client.

Sử dụng immutable request DTO/record có ưu điểm: xác định rõ bề mặt dữ liệu, giảm setter có thể bị lạm dụng và khiến việc review API dễ hơn. Tuy nhiên **immutable không thay cho validation hoặc authorization**. Nếu record có component `isAdmin`, Jackson vẫn có thể truyền giá trị `true` vào constructor; do đó chính **thiết kế hợp đồng** mới là yếu tố quyết định.

Đối với input lồng nhau, hãy tiếp tục dùng DTO lồng nhau và validation phù hợp. Tránh nhét entity JPA hoặc object đồ thị tùy ý vào DTO (ví dụ `List<DomainEntity>`) vì nó tái mở khả năng gắn thuộc tính ngoài dự định. Giới hạn kích thước request/list, độ sâu và số phần tử theo nhu cầu thực tế, nhất là khi binding cho collection lớn.

## 5. Ví dụ chạy được: Spring Boot 3 + JPA + H2

Ví dụ sau dùng **Java 17+**, Spring Boot **3.5.8**, Spring MVC, Bean Validation, Spring Data JPA và H2 trong bộ nhớ. Controller **chỉ nhận DTO**; service tạo entity theo factory phương thức `open(...)` và đặt trường nội bộ; API trả một response DTO khác. Ví dụ nhằm minh họa ranh giới dữ liệu trong một ứng dụng nhỏ; production cần bổ sung xác thực, phân quyền, schema migration và database thực.

Cấu trúc tệp:

~~~text
boundary-demo/
├── pom.xml
└── src/main/
    ├── java/demo/boundary/
    │   ├── BoundaryDemoApplication.java
    │   ├── domain/
    │   │   ├── TicketEntity.java
    │   │   └── TicketRepository.java
    │   ├── service/
    │   │   └── TicketService.java
    │   └── web/
    │       ├── CreateTicketRequest.java
    │       ├── TicketResponse.java
    │       └── TicketController.java
    └── resources/application.yml
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>boundary-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. `src/main/java/demo/boundary/BoundaryDemoApplication.java`

~~~java
package demo.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryDemoApplication.class, args);
    }
}
~~~

### 5.3. `src/main/java/demo/boundary/web/CreateTicketRequest.java`

~~~java
package demo.boundary.web;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateTicketRequest(
        @NotBlank @Size(max = 100) String title,
        @NotBlank @Size(max = 1000) String description
) {}
~~~

Record này là hợp đồng của thao tác **tạo ticket**. Client được nhập đúng hai trường, không mang entity identity hoặc workflow state. Mã kiểm tra Bean Validation chạy trước service khi controller dùng `@Valid`.

### 5.4. `src/main/java/demo/boundary/domain/TicketEntity.java`

~~~java
package demo.boundary.domain;

import java.time.Instant;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "tickets")
public class TicketEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String title;

    @Column(nullable = false, length = 1000)
    private String description;

    @Column(nullable = false, length = 16)
    private String status;

    @Column(nullable = false)
    private Instant createdAt;

    private Long assignedAgentId;

    @Version
    private Long version;

    protected TicketEntity() {
        // JPA cần constructor không tham số.
    }

    public static TicketEntity open(
            String title, String description, Instant now) {

        if (title == null || title.isBlank()
                || description == null || description.isBlank()) {
            throw new IllegalArgumentException("Required ticket fields");
        }

        TicketEntity entity = new TicketEntity();
        entity.title = title;
        entity.description = description;
        entity.status = "OPEN";
        entity.createdAt = now;
        entity.assignedAgentId = null;
        return entity;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

`id`, `status`, `createdAt`, `assignedAgentId` và `version` là thuộc tính nội bộ. Factory `open(...)` đặt trạng thái `OPEN` ở server; entity không cung cấp setter công khai cho các trường nội bộ. Annotation `@Version` hỗ trợ optimistic locking khi về sau có thao tác cập nhật đồng thời; bản thân nó **không tự phân quyền** hay tự đổi lỗi concurrency thành mã HTTP mong muốn.

Lưu ý: khóa chính `id` được JPA/H2 cấp, không dựa trên một giá trị gửi lên. Phần kiểm tra `title`/`description` trong factory là lớp bảo vệ quy tắc của domain khi service được gọi ngoài HTTP, bổ sung cho `@NotBlank` ở DTO.

### 5.5. `src/main/java/demo/boundary/domain/TicketRepository.java`

~~~java
package demo.boundary.domain;

import org.springframework.data.jpa.repository.JpaRepository;

public interface TicketRepository
        extends JpaRepository<TicketEntity, Long> {
}
~~~

### 5.6. `src/main/java/demo/boundary/web/TicketResponse.java`

~~~java
package demo.boundary.web;

import java.time.Instant;

public record TicketResponse(
        Long id,
        String title,
        String status,
        Instant createdAt
) {}
~~~

Response cho phép UI xem `status` nhưng không hề cung cấp quyền **sửa** `status`. Chúng ta chủ động không đưa `assignedAgentId`, `version` hoặc toàn bộ entity ra API công khai.

### 5.7. `src/main/java/demo/boundary/service/TicketService.java`

~~~java
package demo.boundary.service;

import java.time.Instant;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import demo.boundary.domain.TicketEntity;
import demo.boundary.domain.TicketRepository;
import demo.boundary.web.CreateTicketRequest;
import demo.boundary.web.TicketResponse;

@Service
public class TicketService {

    private final TicketRepository repository;

    public TicketService(TicketRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public TicketResponse create(CreateTicketRequest input) {
        TicketEntity entity = TicketEntity.open(
                input.title().strip(),
                input.description().strip(),
                Instant.now()
        );

        TicketEntity saved = repository.save(entity);
        return toResponse(saved);
    }

    @Transactional(readOnly = true)
    public TicketResponse get(long id) {
        TicketEntity entity = repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Ticket not found"));
        return toResponse(entity);
    }

    private static TicketResponse toResponse(TicketEntity entity) {
        return new TicketResponse(
                entity.getId(),
                entity.getTitle(),
                entity.getStatus(),
                entity.getCreatedAt()
        );
    }
}
~~~

Đây là đoạn quan trọng nhất để hiểu **ranh giới tin cậy**:

- `input.title()` và `input.description()` là dữ liệu đã được parse/validate và được phép dùng cho thao tác tạo; service chủ động lấy đúng hai giá trị.
- `Instant.now()` đến từ đồng hồ **của server**, `status = OPEN` đến từ chính sách **của domain**, `id` từ **database**.
- `toResponse(...)` quyết định những gì công khai; vì thế API không tự phụ thuộc vào tất cả thuộc tính, lazy relation hoặc annotation của entity.
- `@Transactional` đặt một biên giao dịch cho thao tác persistence. Giao dịch không thể thay thế kiểm tra quyền ở các thao tác cần chủ thể xác thực.

### 5.8. `src/main/java/demo/boundary/web/TicketController.java`

~~~java
package demo.boundary.web;

import java.net.URI;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import demo.boundary.service.TicketService;

@RestController
@RequestMapping("/tickets")
public class TicketController {

    private final TicketService service;

    public TicketController(TicketService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<TicketResponse> create(
            @Valid @RequestBody CreateTicketRequest request) {

        TicketResponse created = service.create(request);
        return ResponseEntity
                .created(URI.create("/tickets/" + created.id()))
                .body(created);
    }

    @GetMapping("/{id}")
    public TicketResponse get(@PathVariable long id) {
        return service.get(id);
    }
}
~~~

Controller nhận DTO, không sử dụng entity làm tham số request. URL của resource được xây từ ID mà JPA vừa sinh. Endpoint GET trả đúng response DTO mà service xây dựng.

### 5.9. `src/main/resources/application.yml`

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
~~~

H2 được Spring Boot tự cấu hình cho ví dụ nhờ dependency có sẵn. `create-drop` chỉ phù hợp với dữ liệu thử nghiệm: bảng bị tạo/xóa theo vòng đời ứng dụng, dữ liệu không bền vững. Dự án thật nên dùng schema migration và chiến lược persistence phù hợp.

`fail-on-unknown-properties: true` yêu cầu Jackson từ chối JSON có thuộc tính không nằm trong DTO (trừ khi kiểu hoặc cấu hình deserialization có quy định bỏ qua khác). Đó là hành vi **fail-closed cho hợp đồng input**, giúp phát hiện request thừa trường sớm. Nó vẫn không thay thế authorization khi người gọi truy cập một tài nguyên không thuộc quyền mình.

### 5.10. Chạy ứng dụng và kiểm tra HTTP

Trong thư mục `boundary-demo`, cần JDK 17+ và Maven; lần chạy đầu tải dependencies qua internet:

~~~bash
mvn spring-boot:run
~~~

Gửi request hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/tickets \
  -H 'Content-Type: application/json' \
  -d '{"title":"Không đăng nhập được","description":"Lỗi sau khi nhập mật khẩu"}'
~~~

Kỳ vọng: HTTP **201 Created**; header `Location` trỏ đến `/tickets/{id}`; JSON response có `id` do database cấp, `title`, `status` bằng `OPEN` và `createdAt` là timestamp server. **ID và timestamp phụ thuộc lần chạy**, nên không gán một output cố định. Dùng URL từ `Location` để gọi GET và xem lại ticket. Ví dụ trên dùng cú pháp dòng lệnh POSIX; trong PowerShell, dùng `curl.exe` hoặc công cụ HTTP tương đương.

Thử thêm trạng thái nội bộ:

~~~bash
curl -i -X POST http://localhost:8080/tickets \
  -H 'Content-Type: application/json' \
  -d '{"title":"Yêu cầu mới","description":"Mô tả hợp lệ","status":"RESOLVED"}'
~~~

Kỳ vọng: HTTP **400 Bad Request** do `status` là thuộc tính JSON **không thuộc** `CreateTicketRequest` và cấu hình Jackson đang từ chối unknown properties. Body thông báo lỗi cụ thể tùy cấu hình xử lý lỗi của ứng dụng.

Thử thiếu trường bắt buộc:

~~~bash
curl -i -X POST http://localhost:8080/tickets \
  -H 'Content-Type: application/json' \
  -d '{"title":"  ","description":"Mô tả hợp lệ"}'
~~~

Kỳ vọng: HTTP **400 Bad Request** do `@NotBlank` trên `title`. Service không được gọi với request hợp lệ về cấu trúc nhưng vi phạm validation, và không tạo bản ghi mới.

Với request tạo hợp lệ, hai điều được bảo đảm bởi **thiết kế ví dụ**: client không thể truyền trực tiếp giá trị `status` hoặc `assignedAgentId` qua request DTO này, và mọi ticket được tạo từ service mang `status = OPEN`. Việc bảo vệ thao tác **đọc/cập nhật theo người dùng** là một trách nhiệm khác; ứng dụng mẫu chưa có cơ chế đăng nhập và không nên dùng như API production.

## 6. Cập nhật entity phải đi qua thao tác nghiệp vụ

Tạo mới thường dễ phân định: chỉ hai input và nhiều giá trị server-managed. Khi cập nhật, tránh cách ngắn gọn sau:

~~~java
// VÍ DỤ KHÔNG AN TOÀN: không dùng cho bản cập nhật thực tế.
BeanUtils.copyProperties(request, entity);
repository.save(entity);
~~~

Ngay cả khi hôm nay DTO chỉ có vài thuộc tính, người khác có thể bổ sung một field sau này và vô tình cho phép nó ghi vào entity. Mapper tự động dùng theo quy ước tên field cần được cấu hình whitelist rõ ràng; không nên phụ thuộc việc tên giống nhau là đủ để cho phép cập nhật.

Thay bằng thao tác nghiệp vụ rõ ý định:

~~~java
// Minh họa thiết kế service/domain; cần các lớp và method
// tương ứng trong ứng dụng thực tế, không thuộc demo chạy ở mục 5.
@Transactional
public TicketResponse changeTitle(
        long ticketId, ChangeTitleRequest request, AuthenticatedUser actor) {

    TicketEntity ticket = ticketRepository.findById(ticketId)
            .orElseThrow(TicketNotFoundException::new);

    if (!accessPolicy.canEdit(actor, ticket)) {
        throw new AccessDeniedException("Not allowed");
    }

    ticket.rename(request.title());  // Entity tự giữ invariants.
    return mapToResponse(ticket);
}
~~~

Đoạn này là **mã minh họa**, không độc lập để biên dịch vì `ChangeTitleRequest`, `AuthenticatedUser`, `TicketNotFoundException`, `accessPolicy`, `rename` và `mapToResponse` thuộc thiết kế của ứng dụng. Điều cần học là thứ tự: **tải entity đang tồn tại → kiểm tra quyền → gọi thao tác được phép → giữ bất biến trạng thái → trả DTO**. Không nhận `ownerId` từ request rồi coi đó là bằng chứng sở hữu; danh tính caller phải đến từ cơ chế xác thực đáng tin cậy.

Với workflow, phương thức như `ticket.assignTo(agentId, actor)` hay `ticket.resolve(actor)` có thể buộc kiểm tra trạng thái hợp lệ: chẳng hạn chỉ `OPEN` mới được chuyển `IN_PROGRESS`, chỉ agent có quyền mới được giải quyết. Không mở setter `setStatus(String)` cho code bên ngoài để thao tác tùy tiện.

## 7. Một số bẫy khi thiết kế API tạo/cập nhật

### 7.1. Create DTO, Update DTO và Patch DTO khác nhau

Một `CreateTicketRequest` có thể bắt buộc `title` và `description`. Khi sửa tiêu đề, DTO tương ứng chỉ cần `title`; khi đóng ticket, endpoint nghiệp vụ có thể không cần body, vì trạng thái cần đổi đã được thể hiện bằng hành động `POST /tickets/{id}/resolve` và được kiểm tra ở server.

Với PATCH cập nhật từng phần, phân biệt ba trạng thái:

1. **Không xuất hiện field**: giữ nguyên giá trị hiện có.
2. **Field xuất hiện với `null`**: có thể là yêu cầu xóa giá trị, hoặc lỗi nếu field không cho phép null.
3. **Field xuất hiện với giá trị**: validate rồi cập nhật.

Java record thông thường với các component nullable không tự phân biệt *absent* và *explicit null* của JSON. Có thể dùng một DTO PATCH với cơ chế biểu diễn field presence (ví dụ wrapper có trạng thái absent/present hoặc truy cập `JsonNode` được validate và ánh xạ chặt chẽ). Đừng diễn giải mọi `null` là lệnh xóa hay thay toàn bộ entity theo mặc định.

### 7.2. Không đặt thông tin tin cậy vào request DTO

- `currentUserId`, `tenantId`, quyền quản trị: lấy từ authentication/security context và scope đã kiểm tra; client có thể đưa resource ID làm mục tiêu nhưng server phải xác minh quyền truy cập.
- `createdAt`, `updatedAt`: tính/đặt ở server hoặc lifecycle auditing, không tin timestamp do client khai báo khi nghiệp vụ không cho phép.
- `status`, `approvedBy`, `accountBalance`, `effectivePrice`: tính từ quy tắc nghiệp vụ hoặc hành động có phân quyền, không gắn hàng loạt.
- `version`: có thể được lộ trong ETag/If-Match hoặc cơ chế concurrency có chủ đích, nhưng không nên gắn trực tiếp vào managed entity như một thuộc tính bình thường.

Ngay cả khi **không bind** một field được bảo vệ, API vẫn cần ngăn caller lợi dụng đường dẫn ID, tham số tìm kiếm hoặc thao tác khác để truy cập tài nguyên người khác (IDOR/BOLA).

### 7.3. Validation và các quy tắc trong cơ sở dữ liệu

DTO validation như `@NotBlank`, `@Size` cải thiện trải nghiệm và trả lỗi sớm. Entity/domain vẫn cần duy trì invariants khi thao tác không đi qua HTTP (batch, scheduler, messaging, tests). Ràng buộc CSDL như `NOT NULL`, `UNIQUE`, foreign key và transaction giúp đảm bảo tính toàn vẹn dưới truy cập đồng thời.

Đặc biệt, quy tắc “email là duy nhất” không thể được bảo đảm chỉ bằng bước `repository.existsByEmail(...)` rồi mới insert: giữa hai thao tác có thể xảy ra race condition. Cần unique constraint ở database và ánh xạ lỗi xung đột phù hợp.

### 7.4. Optimistic locking và quyền sửa là hai lớp khác nhau

`@Version` trong JPA/Hibernate giúp phát hiện hai luồng cập nhật dựa trên phiên bản cũ khi thực hiện thao tác SQL tương ứng. Nó không thay thế kiểm tra quyền. Khi có conflict, ứng dụng cần quyết định cách phản hồi (ví dụ HTTP 409, hoặc 412 với điều kiện If-Match) thông qua cơ chế xử lý lỗi đã triển khai; **không mặc định** mọi `@Version` tự sinh đúng HTTP status.

### 7.5. Những trường hợp không nên trả entity

Trả nguyên entity có thể vô tình lộ thuộc tính nội bộ, token/hash, mối quan hệ không mong muốn hoặc phát sinh lazy loading và vòng lặp serialize. `Response DTO` thể hiện rõ cấu trúc API công khai, tách version và cấu trúc persistence khỏi client. Các field cho phép **đọc** và field cho phép **ghi** là hai chính sách độc lập.

## 8. Cách kiểm tra ranh giới input trong một API thực tế

Các tình huống sau giúp tìm lỗi từ sớm:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| JSON hợp lệ, chỉ có field được khai báo | Tạo/cập nhật thành công theo policy; thuộc tính server-managed được server quyết định |
| Client gửi thêm `isAdmin`, `status`, `ownerId` | Field không bao giờ làm thay đổi giá trị nội bộ; nếu bật chế độ strict unknown JSON thì trả lỗi 400 |
| Bỏ trống field `@NotBlank`, vượt giới hạn `@Size` | HTTP 400 và không ghi entity |
| Sửa ID thuộc tài khoản khác | Server kiểm tra quyền đối với entity đang tải và từ chối, thường 403 hoặc 404 theo chính sách API |
| Chuyển trạng thái trái workflow | Service/domain từ chối thao tác bất hợp lệ, không chỉ phụ thuộc validation DTO |
| Hai tác vụ cập nhật đồng thời | Không âm thầm mất dữ liệu; kiểm soát cạnh tranh dựa trên version/transaction khi có nhu cầu |
| PATCH field vắng mặt so với `null` | Hai trường hợp có ngữ nghĩa rõ ràng, không vô tình xóa dữ liệu |
| Mở rộng DTO trong tương lai | Review hợp đồng API và mapping; field mới không tự được sao chép sang entity |

Trong kiểm thử tự động, nên có ít nhất trường hợp **over-posting** và trường hợp **authorization** cho API thật. Một test “status không bị ghi đè” cần kiểm tra trạng thái entity đọc lại từ repository, thay vì chỉ xem response 200/201. Một test quyền truy cập cần chạy với hai danh tính khác nhau và hai tài nguyên khác chủ sở hữu.

Đối với ứng dụng Spring MVC, tùy lớp kiểm thử có thể dùng `MockMvc` hoặc tích hợp HTTP, kết hợp kiểm tra repository. Khi xác thực, đừng đặt danh tính thử nghiệm trong một header tự chọn rồi xem header đó là principal tin cậy nếu production không có middleware xác thực rõ ràng.

## 9. Những cách hiểu sai thường gặp

1. **“DTO chỉ là thêm một class, không cần thiết.”** DTO là ranh giới hợp đồng có thể review và version độc lập với persistence; nó cắt đường gắn dữ liệu tự động vào field nội bộ.
2. **“Dùng record là an toàn tuyệt đối.”** Record chỉ bất biến về field, nhưng vẫn có thể chứa các component nhạy cảm nếu hợp đồng được thiết kế sai.
3. **“Có `@Valid` là đủ.”** Validation kiểm tra định dạng và constraint; authorization và state transition phải kiểm tra ở service/domain.
4. **“`@InitBinder.setAllowedFields` bảo vệ mọi `@RequestBody` JSON.”** `@ModelAttribute` property binding và JSON `HttpMessageConverter` là hai đường đi khác nhau; với JSON hãy dùng DTO, Jackson configuration và explicit mapping.
5. **“Ẩn field khi serialize là đã chặn được ghi.”** Cần đánh giá cả chiều deserialization, các mapper khác và các con đường cập nhật entity.
6. **“Đổi tên vài field trong DTO là đủ.”** Ngay cả field tên khác cũng có thể bị mapper custom gắn sai; đường đi từ request sang entity cần rõ ràng.
7. **“Entity có private field nên client không sửa được.”** ORM, reflection, Jackson setter/field visibility, constructor binding và mapping library có thể tiếp cận dữ liệu theo cấu hình; không dựa vào modifier đơn lẻ để định nghĩa quyền.
8. **“Trả nguyên entity sẽ tiết kiệm mã.”** Dễ làm lộ thuộc tính không dự định và khiến API thay đổi theo schema database.
9. **“Server bỏ qua extra field nên đã an toàn.”** Bỏ qua có thể bảo vệ một field trước over-posting, nhưng nếu cần giao thức chặt chẽ và phát hiện client gửi sai thì cấu hình từ chối unknown fields là một lựa chọn rõ ràng hơn.
10. **“Chỉ cần phân quyền tại controller.”** Kiểm tra quyền phải áp dụng đúng resource và trạng thái trong transaction/service khi thực hiện thay đổi; controller chỉ là một lối vào.

## 10. Câu hỏi tự kiểm tra

- Khi endpoint nhận `@RequestBody TicketEntity` thay vì `CreateTicketRequest`, những thuộc tính nào có khả năng bị bind trái ý định?
- Vì sao `@Valid` trên DTO không thể cho biết người gọi có quyền chuyển ticket sang `RESOLVED` hay không?
- Với `@ModelAttribute`, `setAllowedFields` bảo vệ loại binding nào? Với JSON body, lớp nào deserialize dữ liệu?
- Vì sao nên tách DTO tạo mới, DTO cập nhật và DTO phản hồi ngay cả khi tất cả liên quan một entity?
- Khi PATCH, vì sao “không gửi field” và “gửi field = null” cần được phân biệt?
- Làm thế nào chứng minh một field client tự thêm vào JSON không thể thay đổi trạng thái đã lưu?

Nếu trả lời được các câu hỏi trên và truy vết được đúng luồng **request DTO → validation → service/domain → entity → response DTO**, bạn đã nắm được cách giữ dữ liệu đầu vào độc lập với persistence entity và trạng thái nội bộ.

## Tài liệu tham khảo

- Spring Framework, Data Binding (Model Design): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework, `@ModelAttribute`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework, `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework, Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework, Core Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Boot 3.5.8 release: https://spring.io/blog/2025/11/20/spring-boot-3-5-8-available-now
