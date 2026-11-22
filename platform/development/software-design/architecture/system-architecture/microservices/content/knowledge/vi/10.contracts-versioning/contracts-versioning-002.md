# Thiết kế contract-first và code-first theo nhu cầu thực tế

## 1. Bài toán: thiết kế hợp đồng trước hay viết mã trước?

Khi xây dựng API hoặc sự kiện giữa các microservice, nhóm phát triển thường gặp hai cách làm:

- **Contract-first:** xác định và thống nhất hợp đồng giao tiếp trước khi triển khai phần lớn logic xử lý; sau đó dùng hợp đồng để thiết kế, tạo khung mã, giả lập và kiểm thử.
- **Code-first:** triển khai API trong mã nguồn trước, sử dụng annotation, kiểu dữ liệu và công cụ để tạo tài liệu/hợp đồng máy đọc được từ implementation.

Không có cách nào luôn tốt hơn. Contract-first phù hợp khi **nhiều bên cần phối hợp trên một giao diện ổn định trước khi code sẵn sàng**; code-first phù hợp khi **một nhóm làm chủ giao diện, cần thử nghiệm nhanh và có quy trình công bố hợp đồng tự động đáng tin cậy**.

Câu hỏi thực tế không phải “cách nào hiện đại hơn”, mà là:

> **Với mức độ phụ thuộc, số lượng consumer, tần suất thay đổi, yêu cầu ổn định và năng lực kiểm thử hiện tại, đâu là cách giúp giữ hợp đồng đúng, rõ, tương thích và dễ tiến hóa nhất?**

Bài học này tập trung vào thiết kế giao diện trong hệ thống phân tán: API HTTP/gRPC, sự kiện bất đồng bộ, input/output, mã lỗi, tính nhất quán, idempotency và cách kiểm soát phiên bản. Ví dụ kỹ thuật dùng OpenAPI và Java Spring; nguyên tắc vẫn áp dụng cho hệ sinh thái khác.

## 2. “Contract” rộng hơn chữ ký hàm và schema JSON

**Hợp đồng dịch vụ** là những điều producer/provider công bố để consumer sử dụng an toàn. Nó có nhiều lớp:

| Lớp hợp đồng | Ví dụ câu hỏi | Công cụ/mô tả thích hợp |
|---|---|---|
| Định danh và trách nhiệm | Dịch vụ sở hữu năng lực nào, dữ liệu nào? | Service catalog, domain map, ADR |
| Giao diện kỹ thuật | Method/path, field, kiểu dữ liệu, request/response nào? | OpenAPI, Protobuf, AsyncAPI |
| Ngữ nghĩa nghiệp vụ | Khi trả “thành công” thì điều gì đã xảy ra? | Ví dụ, pre/post-condition, state machine |
| Lỗi và xử lý lỗi | Mã nào retry được, mã nào là xung đột? | Error catalog, status policy |
| Bảo đảm phân tán | Retry có gây tạo bản ghi trùng không? Event có thể tới hai lần không? | Idempotency, consistency, delivery contract |
| Bảo mật | Ai gọi được? Scope và tenant isolation ra sao? | Security schemes, authorization policy |
| Tương thích | Client cũ chạy được với server mới không? | Version policy, compatibility tests |
| Vận hành | Deadline, quota, SLO và hành vi quá tải? | API policy, runbook, observability |

Một file OpenAPI đúng cú pháp có thể mô tả request và response rất chi tiết nhưng **không tự bảo đảm** rằng endpoint thực sự đúng nghiệp vụ. Ngược lại, một controller chạy được không tự trở thành một hợp đồng dễ hiểu cho những đội khác.

### 2.1. Ví dụ sự khác biệt giữa hình dạng và ý nghĩa

Giả sử HTTP trả:

~~~json
{
  "reservationId": "rsv_003",
  "status": "ACTIVE"
}
~~~

Schema có thể xác minh hai trường là string. Nhưng consumer vẫn cần biết:

- **ACTIVE** nghĩa là tồn kho đã được giữ trong nguồn sự thật hay chỉ là lệnh đã vào queue?
- Lượt giữ hết hạn vào thời điểm nào?
- Sau timeout có thể retry cùng request không?
- Có thể có hai lượt giữ cho cùng một thao tác đặt hàng không?
- Khi nào một event về lượt giữ được phát, có thể trùng hay đến chậm không?

Vì thế, cả contract-first và code-first đều phải bổ sung **ngữ nghĩa, giới hạn và kiểm thử hành vi**.

## 3. Contract-first là gì?

Contract-first thường đi theo chuỗi:

~~~text
Nhu cầu nghiệp vụ và consumer
       |
       v
Thiết kế API / event contract
       |
       v
Thảo luận + duyệt schema và semantics
       |
       +----> Tạo mock / ví dụ cho consumer
       |
       +----> Sinh model / client / server interface
       |
       v
Triển khai nghiệp vụ
       |
       v
Contract tests + integration tests
       |
       v
Phát hành phiên bản tương thích
~~~

Nhóm đặt hợp đồng — chẳng hạn một tài liệu OpenAPI hoặc file Protobuf — làm **đầu vào thiết kế được quản lý**. Các bên có thể xem các method, field, error và trạng thái trước khi một service có implementation hoàn chỉnh.

### 3.1. Lợi ích chính

- Frontend, backend và consumer khác có thể làm việc song song dựa trên một giao diện đã thống nhất.
- Thay đổi phá vỡ tương thích được phát hiện **trước khi** nhiều người phụ thuộc vào implementation.
- Có thể sinh client, mock và khung server để giảm sai khác về tên/kiểu trường.
- Mọi consumer cùng đọc một hợp đồng máy xử lý được; dễ duyệt trong pull request.
- Phù hợp với API công khai, API đa nhóm, hợp đồng với đối tác và hệ thống có yêu cầu quản trị phiên bản nghiêm ngặt.

### 3.2. Chi phí và rủi ro

- Có thêm bước thiết kế/review trước triển khai; nếu quy trình cứng nhắc, nhóm có thể chậm thử nghiệm.
- Spec có thể trở thành “tài liệu giả” nếu code sinh ra nhưng implementation không tuân theo.
- Schema generator không hiểu mọi bất biến nghiệp vụ; domain rules vẫn cần code và test.
- Đội phải quen cách diễn đạt nullability, lỗi, auth và khả năng tương thích.
- Nếu hợp đồng thiết kế quá sớm khi domain còn chưa hiểu, dễ khóa một API sai.

Contract-first không có nghĩa viết hàng trăm trang tài liệu trước khi thử ý tưởng. Với thay đổi nhỏ, một bản spec tối thiểu, ví dụ request/response và một cuộc review ngắn vẫn có thể là contract-first.

## 4. Code-first là gì?

Code-first thường có luồng:

~~~text
Nhu cầu nghiệp vụ
       |
       v
Thiết kế domain / DTO / controller bằng code
       |
       v
Chạy ứng dụng và kiểm thử hành vi
       |
       v
Sinh OpenAPI / mô tả RPC từ code
       |
       v
Duyệt hợp đồng công khai + chạy diff
       |
       v
Publish spec và client nếu cần
~~~

Trong Java Spring, code-first thường xây dựng các controller, request/response records, validation annotations và metadata API. Công cụ tích hợp sau đó sinh OpenAPI. Các ứng dụng Go, C#, TypeScript hoặc Python có cơ chế tương đương theo framework.

**Code-first không đồng nghĩa “không thiết kế”.** Một nhóm code-first tốt vẫn xác định semantics, trường hợp lỗi, tác động tương thích và boundary trước hoặc trong quá trình viết mã. Khác biệt nằm ở đâu được xem là nguồn chính để mô tả giao diện kỹ thuật.

### 4.1. Lợi ích chính

- Vòng lặp thử nghiệm nhanh khi nhóm đang khám phá domain và interface chưa ổn định.
- Ít thao tác sửa song song spec và code nếu generator có thể trích xuất chính xác.
- DTO, validation và controller thường gần với implementation, dễ phát hiện lỗi cú pháp bằng compiler.
- Hữu ích với API nội bộ nhỏ do một nhóm sở hữu và ít consumer.
- Dễ áp dụng từng bước vào codebase đã có endpoint.

### 4.2. Chi phí và rủi ro

- Spec sinh từ code có thể chỉ phản ánh **hiện trạng implementation**, không giải thích vì sao API có hình dạng đó.
- Annotation thiếu hoặc generator cấu hình sai khiến OpenAPI bỏ sót response, lỗi hoặc security.
- Refactor class/DTO có thể vô tình làm thay đổi public contract.
- Consumer chỉ thấy thay đổi sau khi provider đã triển khai xong, khiến phối hợp muộn.
- Dễ để persistence entity hoặc model nội bộ rò rỉ vào giao diện công khai.
- Một API “chạy được” có thể vẫn chưa có versioning, idempotency, deadline hoặc error semantics hợp lý.

Code-first cần pipeline công bố spec và kiểm tra sự tương thích. Nếu thiếu nó, việc sinh tài liệu chỉ làm API dễ nhìn hơn mà chưa làm giao tiếp giữa các nhóm an toàn hơn.

## 5. Ví dụ xuyên suốt: dịch vụ giữ trước tồn kho

Giả sử Checkout cần yêu cầu Inventory Reservation giữ hàng trong một khoảng thời gian. Một yêu cầu có thể bao gồm:

~~~json
{
  "orderId": "ord_731",
  "sku": "SKU-RED-42",
  "quantity": 2
}
~~~

Kết quả thành công giả định:

~~~json
{
  "reservationId": "rsv_91",
  "orderId": "ord_731",
  "sku": "SKU-RED-42",
  "quantity": 2,
  "status": "ACTIVE",
  "expiresAt": "2026-11-11T08:15:00Z"
}
~~~

Trước khi chọn contract-first hay code-first, đội cần làm rõ:

1. Chỉ Inventory Reservation được quyền cấp giữ và giảm lượng tồn có thể phân bổ.
2. **201 Created** có nghĩa lượt giữ đã được commit, không chỉ nhận lệnh.
3. Cùng một thao tác logic được retry với cùng **Idempotency-Key** không tạo thêm lượt giữ.
4. Khi hết hàng, trả lỗi nghiệp vụ rõ ràng thay vì che trong 500.
5. Thời điểm hết hạn được xác định bởi server; client không tự sửa trạng thái.
6. Sau timeout, caller có thể tra cứu kết quả hoặc retry trong phạm vi idempotency đã công bố.

Đây là phần **ngữ nghĩa cốt lõi**. Cả hai cách tiếp cận đều phải bảo vệ nó.

## 6. Contract-first với OpenAPI

Một bản OpenAPI đầu tiên có thể được duyệt trước khi code chạy. Ví dụ rút gọn dùng OpenAPI 3.1:

~~~yaml
openapi: 3.1.0
info:
  title: Inventory Reservation API
  version: 1.0.0
  description: API tạo và truy vấn lượt giữ tồn kho.

servers:
  - url: https://inventory.example.internal

paths:
  /v1/reservations:
    post:
      operationId: createReservation
      summary: Tạo lượt giữ hàng
      description: >
        Khi trả 201, reservation đã được lưu bền vững.
        Retry cùng Idempotency-Key và payload không tạo lượt giữ mới
        trong cửa sổ idempotency đã công bố.
      security:
        - bearerAuth: []
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          description: Khóa định danh thao tác logic khi retry.
          schema:
            type: string
            minLength: 1
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateReservation'
      responses:
        '201':
          description: Lượt giữ đã được tạo
          headers:
            Location:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Reservation'
        '400':
          description: Request không hợp lệ về cú pháp
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '409':
          description: Hết hàng hoặc khóa idempotency xung đột
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '503':
          description: Dịch vụ tạm thời không sẵn sàng

  /v1/reservations/{reservationId}:
    get:
      operationId: getReservation
      summary: Truy vấn lượt giữ
      security:
        - bearerAuth: []
      parameters:
        - name: reservationId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Thông tin lượt giữ
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Reservation'
        '404':
          description: Không tìm thấy hoặc không được phép tiết lộ

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    CreateReservation:
      type: object
      required: [orderId, sku, quantity]
      additionalProperties: false
      properties:
        orderId:
          type: string
          minLength: 1
        sku:
          type: string
          minLength: 1
        quantity:
          type: integer
          minimum: 1
          maximum: 100
    Reservation:
      type: object
      required: [reservationId, orderId, sku, quantity, status, expiresAt]
      properties:
        reservationId:
          type: string
        orderId:
          type: string
        sku:
          type: string
        quantity:
          type: integer
        status:
          type: string
          enum: [ACTIVE, CONFIRMED, RELEASED, EXPIRED]
        expiresAt:
          type: string
          format: date-time
    Error:
      type: object
      required: [code, message, correlationId]
      properties:
        code:
          type: string
        message:
          type: string
        correlationId:
          type: string
        retryable:
          type: boolean
~~~

Địa chỉ server, giới hạn, phiên bản và schema là **ví dụ thiết kế**. Khi dùng thực tế, nhóm cần công bố đầy đủ response, auth scopes, retry, trường optional/nullable và các trường hợp lỗi theo tiêu chuẩn tổ chức.

### 6.1. Review hợp đồng trước khi viết nghiệp vụ

Review cần có ít nhất góc nhìn provider và consumer:

- Consumer có đủ dữ liệu để tạo request và nhận diện response?
- **201** khác **202** thế nào; đã commit hay chỉ nhận command?
- Sau timeout có cơ chế tra cứu kết quả không?
- Mã lỗi có ổn định và dễ xử lý bằng máy không?
- Idempotency key áp dụng trong bao lâu, theo scope nào?
- Trường nào thật sự bắt buộc; liệu sau này có cần thêm không?
- Không có thông tin nào tiết lộ dữ liệu của tenant khác?
- Thay đổi schema có thể ảnh hưởng client nghiêm ngặt không?

Đừng chỉ review xem YAML có parse được. Hợp đồng là đầu ra của quyết định nghiệp vụ.

### 6.2. Sinh mã từ spec có giúp gì?

Có thể sử dụng công cụ tương thích OpenAPI để tạo:

- Interface controller/server stub.
- DTO request/response.
- HTTP client và serializer.
- Tài liệu HTML, ví dụ request hoặc mock server.
- Bộ kiểm tra schema cơ bản.

Nhưng sinh mã **không** sinh hộ:

- Quy tắc transaction chống bán vượt tồn kho.
- Chính sách idempotency và khóa dedup bền vững.
- Quy trình rollback/compensation khi hệ thống phân tán.
- Authorization theo tenant và domain ownership.
- Kiểm thử concurrency, sự cố và khả năng phục hồi.

Vì vậy, nên coi generated code là **bộ khung giao tiếp**, còn domain model và business rules do nhóm phát triển sở hữu.

## 7. Code-first với Java Spring

Một nhóm nhỏ có thể bắt đầu trực tiếp từ request/response DTO và controller, sau đó sinh OpenAPI bằng công cụ tích hợp phù hợp. Ví dụ sử dụng Java records và Jakarta Validation.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.time.Instant;

public record CreateReservationRequest(
    @NotBlank String orderId,
    @NotBlank String sku,
    @Min(1) @Max(100) int quantity
) {}

public record ReservationResponse(
    String reservationId,
    String orderId,
    String sku,
    int quantity,
    String status,
    Instant expiresAt
) {}
~~~

Controller minh họa:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.net.URI;

@RestController
@RequestMapping("/v1/reservations")
public class ReservationController {
    private final ReservationService service;

    public ReservationController(ReservationService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<ReservationResponse> create(
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @Valid @RequestBody CreateReservationRequest request
    ) {
        ReservationResponse result = service.create(
            idempotencyKey, request
        );
        URI location = URI.create(
            "/v1/reservations/" + result.reservationId()
        );
        return ResponseEntity.created(location).body(result);
    }

    @GetMapping("/{reservationId}")
    public ResponseEntity<ReservationResponse> get(
            @PathVariable String reservationId
    ) {
        return ResponseEntity.ok(service.get(reservationId));
    }
}
~~~

Trong ví dụ, **ReservationService** là abstraction nghiệp vụ cần được triển khai; error mapping, security, API metadata và persistence chưa được đưa vào đoạn trích. Code chỉ minh họa vị trí định nghĩa interface/DTO, không tuyên bố sẵn sàng production.

Với cách code-first, nhóm sẽ:

1. Viết controller/DTO và validation.
2. Viết unit/integration tests cho hành vi và lỗi.
3. Dùng công cụ như **springdoc-openapi** để trích xuất schema.
4. Thêm metadata chưa được tự suy ra (security, response errors, descriptions, examples).
5. Xuất spec tại bước build/CI và so sánh với contract của phiên bản đang dùng.
6. Công bố bản spec đã duyệt cùng release của service.

Một annotation đúng không chứng minh idempotency hay consistency đúng. Vẫn cần mô tả behavior và integration tests.

### 7.1. Tránh dùng persistence entity làm API response

Không nên trả thẳng một entity JPA chỉ vì cách đó ít code hơn. Entity có thể chứa field nội bộ, quan hệ lazy-loaded, trạng thái không dành cho người gọi hoặc tên field gắn chặt với database.

Một boundary an toàn hơn:

~~~text
HTTP Request DTO
      |
Validation / Authorization
      |
Application Service
      |
Domain Model / Invariants
      |
Repository / Persistence

Domain Result
      |
Mapping
      |
HTTP Response DTO
~~~

Cách này giúp thay schema nội bộ mà không bắt client đổi theo, đồng thời tạo nơi duy trì hợp đồng rõ ràng.

## 8. Khác nhau về “nguồn sự thật”

Điểm quan trọng nhất không chỉ là thứ tự làm việc mà còn là **nơi quyết định giao diện công khai được duy trì**.

### Contract-first

~~~text
OpenAPI / Protobuf / AsyncAPI (authoritative)
       |
       +--> Generated interfaces / models
       |
       +--> Consumer mock / SDK
       |
       +--> Contract validation
       |
       v
Implementation tuân theo contract
~~~

Nguồn thiết kế là hợp đồng. Không nên sửa generated DTO thủ công rồi quên cập nhật spec gốc.

### Code-first

~~~text
Controller + DTO + annotations (authoritative)
       |
       v
OpenAPI được sinh tự động
       |
       +--> Contract diff / review
       |
       +--> Published docs / SDK
~~~

Nguồn định nghĩa interface là code, nhưng spec được xuất ra vẫn là **sản phẩm phải review và kiểm tra tương thích**. Không nên sửa file OpenAPI được sinh rồi để lần build sau ghi đè mất.

### Hybrid

~~~text
Nhu cầu + ví dụ + review consumer
            |
            v
Thiết kế hình dạng contract sơ bộ
            |
            v
Prototyping / implementation
            |
            v
Xuất hoặc cập nhật contract chuẩn
            |
            v
Review schema diff + contract tests
~~~

Hybrid có thể là lựa chọn phù hợp khi domain còn biến động nhưng vẫn phải phối hợp liên nhóm. Tuy nhiên, cần định nghĩa **nguồn sự thật ở mỗi giai đoạn** và cách đồng bộ; nếu cả spec lẫn code đều tự cho là authoritative, drift sẽ xuất hiện.

## 9. Bảng quyết định theo nhu cầu thực tế

| Tình huống | Contract-first thường phù hợp khi | Code-first thường phù hợp khi |
|---|---|---|
| **API công khai / đối tác** | Có nhiều consumer không kiểm soát lịch phát hành | Chỉ dùng thử rất hạn chế, vẫn có review contract |
| **Microservice liên nhóm** | Nhiều nhóm phải làm song song, dependency quan trọng | Một nhóm sở hữu toàn bộ vòng đời và contract ít thay đổi |
| **API nội bộ nhỏ** | Đã có tiêu chuẩn spec/SDK và cần đồng nhất | Cần thử nghiệm nhanh, consumer ít và gần |
| **Giao diện gRPC** | Protobuf thường là input thiết kế tự nhiên | Framework hỗ trợ sinh schema từ code và quy trình đảm bảo tương thích |
| **Sự kiện bất đồng bộ** | Event schema được nhiều consumer tiêu thụ, cần quản trị version | Event chỉ nội bộ một ứng dụng, nhưng vẫn cần hợp đồng khi mở rộng |
| **Domain chưa rõ** | Có thể bắt đầu bằng contract ví dụ và review nhỏ | Prototype giúp phát hiện mô hình thực tế nhanh hơn |
| **Hệ thống chịu điều tiết** | Cần traceability và phê duyệt thay đổi trước triển khai | Vẫn làm được nếu artifact sinh được review, lưu và kiểm chứng |
| **Nhiều SDK đa ngôn ngữ** | Dễ sinh client từ spec được quản lý | Cần đảm bảo spec sinh ra đầy đủ và ổn định |
| **Legacy API chưa có spec** | Có thể khôi phục spec rồi chọn làm authoritative | Sinh spec từ code hiện có là bước chuẩn hóa khả thi |
| **Tỷ lệ breaking change cao** | Phát hiện điểm xung đột từ khâu thiết kế | Phải có diff gate nghiêm để tránh phá vỡ client |

Bảng này là **gợi ý chọn hướng**, không phải quy định cố định. Một nhóm code-first với contract tests tốt có thể vận hành API đa consumer an toàn; một nhóm contract-first nhưng không kiểm tra implementation vẫn có thể phát hành API sai.

## 10. Quy trình contract-first thực tế, không nặng giấy tờ

### Bước 1: Xác định nghiệp vụ và consumer

Viết một đoạn ngắn mô tả năng lực và phạm vi. Ai cần gọi API? Họ muốn đạt điều gì? Dữ liệu và bất biến thuộc service nào?

Ví dụ:

> Checkout cần yêu cầu giữ một số lượng SKU trước khi xác nhận đơn. Inventory Reservation chịu trách nhiệm quyết định có đủ tồn kho và trả mã lượt giữ có thời hạn. Checkout không được cập nhật bảng tồn kho trực tiếp.

Không định nghĩa API bằng cách bê nguyên mô hình database ra ngoài.

### Bước 2: Vẽ luồng thành công và các lỗi quan trọng

~~~text
Checkout
   |
   | POST /v1/reservations
   v
Inventory Reservation
   |
   +-- 201 Created       -> đã giữ hàng
   +-- 409 No stock      -> không đủ hàng
   +-- 400 Invalid input -> sửa request
   +-- 503 Unavailable   -> có thể retry có kiểm soát
   +-- Timeout           -> kết quả chưa rõ, cần kiểm tra/idempotency
~~~

Phần **timeout chưa rõ kết quả** phải có trong thiết kế, đặc biệt với thao tác tạo side effect.

### Bước 3: Thống nhất schema và semantics

Ghi các field, kiểu, đơn vị, default, nullability, lỗi, security và state transitions. Tạo ít nhất một ví dụ thành công, một ví dụ lỗi nghiệp vụ và một ví dụ timeout/retry.

### Bước 4: Thảo luận với consumer

Consumer có thể phản hồi rằng họ cần **expiresAt**, một mã lỗi ổn định hoặc cơ chế truy vấn theo orderId. Đây là lúc thay đổi rẻ hơn so với sau khi ba nhóm đã triển khai dựa trên giả định khác nhau.

### Bước 5: Chấp thuận bản contract tối thiểu

Lưu spec trong repository/service catalog theo version, có review và changelog. Không phải tất cả cuộc họp đều bắt buộc; review theo pull request với ví dụ cụ thể thường đủ cho nhiều đội.

### Bước 6: Sinh mock và khung code nếu hữu ích

Mock giúp frontend/consumer phát triển song song. Nhưng mock chỉ xác nhận giao diện, không chứng minh invariant hay hiệu năng. Đừng dùng mock success để bỏ kiểm thử server thật.

### Bước 7: Triển khai và chạy contract tests

Provider phải tạo response đúng schema, mã lỗi đúng semantics và bảo vệ bất biến. Consumer kiểm thử những khả năng họ thực sự sử dụng.

### Bước 8: Phát hành có kiểm soát

Publish spec đã dùng cho release, đánh dấu version, chạy compatibility diff, theo dõi adoption và chuẩn bị kế hoạch migrate khi có breaking change.

## 11. Quy trình code-first không làm tài liệu tụt hậu

### Bước 1: Thống nhất ý nghĩa tối thiểu

Dù code-first, vẫn cần một đoạn “service contract intent”: input, output, effect, error, idempotency và owner. Không bắt đầu bằng controller khi chưa biết thành công nghĩa là gì.

### Bước 2: Viết DTO và domain logic tách biệt

Cân nhắc records cho DTO, domain service cho logic và adapter cho persistence. Đừng đưa JPA entity trực tiếp vào API.

### Bước 3: Viết test cho lỗi và ranh giới

Test đầu vào không hợp lệ, duplicate request, conflict, concurrency, authorization và timeout. Nếu code-first nhưng thiếu test này, spec sinh ra sẽ có hình dạng đẹp nhưng không bảo đảm hành vi.

### Bước 4: Sinh OpenAPI theo cách lặp lại được

Dùng plugin hoặc bước build cố định; không phụ thuộc vào việc một developer chạy IDE với cài đặt cá nhân. Lưu hoặc xuất bản spec theo đúng source commit/release.

### Bước 5: Review phần giao diện đã sinh

Những thay đổi nhỏ trong DTO có thể tạo thay đổi lớn trong API. Review generated spec như một artifact công khai, không coi nó là file phụ không cần xem.

### Bước 6: So sánh với phiên bản trước

Kiểm tra field bị xóa, type đổi, required tăng, auth bị siết, response status đổi hoặc enum thay đổi. Phân loại tác động tương thích dựa trên tiêu chuẩn consumer thực tế.

### Bước 7: Công bố cùng ứng dụng

Tài liệu phải phản ánh **đúng phiên bản đang chạy**, đặc biệt nếu có nhiều environment và nhiều phiên bản song song. Gắn spec với release identifier để hỗ trợ điều tra sự cố.

## 12. Contract-first và code-first đều cần ví dụ cụ thể

Một API spec có thể nói **quantity: integer**, nhưng với người tiêu thụ, những câu hỏi sau rất quan trọng:

- Chấp nhận 0 hay số âm không?
- Có giới hạn tối đa không?
- Quantity đại diện cho đơn vị chiếc, kilogram hay gói?
- Có cho phép giữ một phần số lượng yêu cầu không?
- Nếu hết hàng, trả mã lỗi gì?
- Nếu retry cùng Idempotency-Key nhưng payload khác, kết quả ra sao?
- Sau khi trả 201, đọc từ GET có thấy reservation ngay không?

Nên công bố **positive examples, negative examples và edge cases**.

Ví dụ hợp đồng lỗi:

~~~json
{
  "code": "STOCK_NOT_AVAILABLE",
  "message": "Không đủ tồn kho khả dụng",
  "correlationId": "req_55ef",
  "retryable": false
}
~~~

Consumer nên phân nhánh bằng **code ổn định**, không bằng nội dung message có thể đổi theo ngôn ngữ. Phải công bố lỗi nào retry được, dùng backoff và có cần idempotency key khi retry không.

## 13. Phân biệt thay đổi tương thích và breaking changes

Một hợp đồng tồn tại lâu sẽ phát triển. Nếu hai service được triển khai độc lập, cập nhật hợp đồng phải tính tới **client cũ còn đang chạy**.

| Thay đổi | Thường có tác động gì? | Cách giảm rủi ro |
|---|---|---|
| Thêm response field tùy chọn | Có thể tương thích với client bỏ qua unknown fields | Kiểm thử consumer nghiêm ngặt và serializer |
| Thêm optional request field | Có thể tương thích nếu default giữ hành vi cũ | Công bố default, test request cũ |
| Xóa/đổi tên response field | Dễ phá vỡ consumer đang đọc | Deprecate, chạy song song và migrate |
| Đổi string thành number | Thay đổi kiểu có nguy cơ breaking | Version API hoặc migration có kiểm soát |
| Biến optional thành required | Request cũ có thể bị từ chối | Hỗ trợ default hoặc version |
| Siết validation | Request cũ từng hợp lệ có thể thành lỗi | Đo usage và thông báo trước |
| Thêm enum value | Có thể phá vỡ exhaustive switch trong client | Quy ước enum mở/UNKNOWN và test |
| Đổi status 201 thành 202 | Thay đổi ý nghĩa hoàn tất | Thiết kế lại workflow, version hợp đồng |
| Đổi ý nghĩa trường tiền tệ | Lỗi nghiêm trọng dù schema không đổi | Ghi đơn vị; version semantics |
| Đổi error code/retryability | Consumer có thể xử lý sai | Giữ contract lỗi ổn định |
| Bỏ quyền truy cập hoặc đổi scope | Client hợp lệ trước đây có thể bị chặn | Kế hoạch migration quyền |
| Thay đổi event ordering | Consumer có thể xây state sai | Ghi rõ ordering, version hoặc chuyển đổi an toàn |

**Không có quy tắc tuyệt đối rằng “thêm trường luôn non-breaking”.** Một consumer cố định schema có thể từ chối unknown fields; thêm enum value có thể khiến client lỗi. Compatibility cần dựa vào tập consumer và quy ước serializer thực tế.

### 13.1. Hợp đồng bao gồm semantics, không chỉ shape

Giả sử response giữ nguyên:

~~~json
{
  "status": "SUCCESS"
}
~~~

Trước đây SUCCESS nghĩa là Payment đã commit, nay SUCCESS chỉ nghĩa là command đã vào queue. Schema diff sẽ không phát hiện, nhưng đó là **breaking change về ngữ nghĩa**. Cần review điều kiện hậu nghiệm, cập nhật version hoặc sử dụng trạng thái ACCEPTED/PENDING rõ ràng.

### 13.2. Version API có nhiều cách

- Version trên path: **/v1/reservations**, **/v2/reservations**.
- Version qua header/media type khi hợp đồng và tooling hỗ trợ.
- Version schema/event type cho giao tiếp bất đồng bộ.
- SemVer hoặc chính sách version riêng cho artifact spec/SDK.

Mỗi phương án có trade-off. Chọn một chính sách dễ vận hành, có lịch deprecation và dữ liệu adoption. Version path không tự đảm bảo backward compatibility nếu dữ liệu và semantics bên trong vẫn thay đổi ngoài ý muốn.

## 14. Contract testing: cả producer và consumer

Một OpenAPI file hoặc controller annotation mới chỉ là **ý định mô tả**. Hợp đồng cần được xác minh ở runtime hoặc trong pipeline đáng tin cậy.

### 14.1. Provider contract tests

Kiểm tra service thực tế:

- Nhận request hợp lệ và trả đúng status/schema.
- Từ chối request sai format, thiếu field, sai phạm vi.
- Trả mã lỗi ổn định và không lộ dữ liệu nhạy cảm.
- Không tạo hai lượt giữ khi retry cùng idempotency key.
- Đúng behavior khi request cạnh tranh giành một lượng tồn giới hạn.
- Xác thực, phân quyền theo tenant đúng.
- GET và POST tuân theo consistency contract đã công bố.

### 14.2. Consumer-driven contract tests

Consumer định nghĩa những tương tác mình thực sự phụ thuộc, chẳng hạn “Checkout cần 201 với reservationId và expiresAt”. Provider kiểm tra tương tác đó trước khi phát hành. Cách này giúp nhìn thấy hợp đồng từ nhu cầu consumer thay vì chỉ từ provider.

Lưu ý:

- Consumer-driven contract tests không thay thế OpenAPI hoặc schema registry.
- Chúng không thay thế integration tests với broker, database và giao dịch.
- Một consumer không cover tất cả consumer; phải biết ai sử dụng contract.
- Mock tests không chứng minh server thật có cùng bất biến và side effect.

### 14.3. Semantic contract tests

Những điều schema khó kiểm tra cần test riêng:

~~~text
Given: còn đúng 1 đơn vị SKU
When: hai client đồng thời yêu cầu giữ mỗi client 1
Then: tối đa 1 request tạo reservation ACTIVE thành công
And: tồn kho không âm
~~~

Thêm test timeout sau commit, retry cùng key và event duplicate. Những bài test này chứng minh hợp đồng nghiệp vụ, bất kể quy trình sinh spec.

## 15. Đưa compatibility check vào CI/CD

Dù chọn phương pháp nào, một pipeline tốt cần quản lý artifact công khai.

~~~text
Pull Request
    |
    v
Build + unit tests
    |
    v
Validate API schema
    |
    v
Export / load current contract
    |
    v
Compare with last released contract
    |
    +--> Breaking change? Review / migration gate
    |
    v
Provider + consumer contract tests
    |
    v
Integration & semantic tests
    |
    v
Publish spec / SDK / service release
~~~

Ví dụ pseudocode các bước CI:

~~~yaml
steps:
  - name: build-and-test
    run: ./gradlew test

  - name: produce-openapi
    run: ./scripts/export-openapi.sh

  - name: validate-spec
    run: ./scripts/validate-api-schema.sh build/openapi.yaml

  - name: check-compatibility
    run: >
      ./scripts/compare-api.sh
      contracts/last-released.yaml
      build/openapi.yaml

  - name: run-contract-tests
    run: ./gradlew contractTest
~~~

Đây là mô tả pipeline **giả định**: các script cần được cung cấp và kiểm tra theo công cụ của tổ chức; không phải tên lệnh có sẵn trong mọi dự án.

### 15.1. Ngăn spec drift

**Spec drift** xảy ra khi tài liệu và implementation khác nhau. Hai hướng đều có nguy cơ:

- Contract-first: spec đã sửa nhưng code chưa triển khai hoặc triển khai sai.
- Code-first: code đã thay đổi nhưng spec chưa được sinh/công bố đúng.
- Hybrid: cả spec và code được sửa độc lập, không có bước đồng bộ.

Cách giảm drift:

1. Xác định artifact authoritative.
2. Sinh các artifact còn lại từ nguồn đó khi phù hợp.
3. Kiểm tra provider thực thi đúng theo schema và semantics.
4. So sánh spec với phiên bản đã phát hành.
5. Công bố version/commit của contract kèm version của service.
6. Nếu generated artifact được commit, kiểm tra nó có thay đổi khi chạy generator không; không để thay đổi chưa commit.
7. Không chỉnh tay generated code rồi coi đó là thiết kế chính thức.

## 16. Contract-first trong sự kiện bất đồng bộ

Với HTTP có OpenAPI; với event/message có thể dùng **AsyncAPI**, Protobuf, Avro, JSON Schema hoặc schema registry theo stack đã chọn.

Ví dụ event OrderPaid:

~~~json
{
  "eventId": "evt_91",
  "eventType": "order.paid.v1",
  "aggregateId": "ord_731",
  "aggregateVersion": 4,
  "occurredAt": "2026-11-11T09:20:00Z",
  "payload": {
    "orderId": "ord_731",
    "currency": "VND",
    "paidAmount": 240000
  }
}
~~~

Nhóm phải thống nhất trước khi viết producer/consumer:

- Event mô tả **điều gì đã xảy ra**, khác command yêu cầu làm việc.
- Schema và phiên bản dùng để consumer giải mã.
- eventId và khóa dedup.
- Partition key và giới hạn ordering.
- Event có thể giao nhiều lần không?
- Consumer xử lý event đến chậm, out-of-order hoặc replay thế nào?
- Producer chỉ phát event sau thời điểm commit nào?
- PII, retention, quyền xóa và khả năng tái dựng projection?

### 16.1. Code-first event có rủi ro riêng

Nếu producer serialize trực tiếp một Java domain object, consumer có thể vô tình phụ thuộc vào tên class, chi tiết nội bộ và thay đổi ngẫu nhiên của serializer. Việc refactor nội bộ sẽ biến thành phá vỡ event contract.

Dù code-first, hãy giữ **public event DTO** và schema version độc lập với persistence/domain internals. Consumer không nên cần cùng Java classpath hay bản jar nội bộ của producer để hiểu sự kiện.

### 16.2. Contract của delivery không tự sinh ra từ schema

AsyncAPI/schema registry có thể mô tả hình dạng event và kênh giao tiếp; delivery semantics, retention, idempotency, cách retry và dead-letter vẫn phải được xác định theo broker và implementation thực tế.

Ví dụ, **at-least-once** có thể khiến cùng event đến nhiều lần. Chỉ vì schema có eventId không có nghĩa consumer đã chống trùng. Cần kiểm thử idempotency và logic replay.

## 17. Khi nào nên dùng contract-first cho microservices?

Những trường hợp mang lại giá trị rõ:

**Nhiều nhóm phát triển song song.** Checkout và Inventory có thể thống nhất contract rồi triển khai độc lập. Consumer dùng mock trong khi provider hoàn thiện invariant, giảm thời gian chờ nhau.

**API có consumer bên ngoài tổ chức.** Thay đổi sai làm đứt tích hợp mà bạn không thể cập nhật client ngay. Review và compatibility gate trước implementation mang lại lợi ích cao.

**Sự kiện có nhiều subscriber.** Một event schema do nhiều nhóm sử dụng có vòng đời dài; contract-first giúp tránh việc producer vô tình đổi event theo internal model.

**Yêu cầu truy vết và phê duyệt.** Hợp đồng được version, review và lưu bằng chứng; dễ truy nguồn quyết định.

**SDK đa ngôn ngữ.** Từ một spec có thể tạo hoặc kiểm tra SDK cho Java, TypeScript, Go,... nhưng vẫn cần test những phần generator không hỗ trợ hoàn toàn.

**Các interface đã ổn định về nghiệp vụ.** Khi hiểu rõ bounded context và semantics, thiết kế trước thường giảm vòng sửa đổi về sau.

Tuy nhiên, contract-first không phù hợp nếu nhóm mất hàng tuần duyệt API trong khi chưa biết yêu cầu thực tế. Có thể dựng một prototype nội bộ, xác định dữ liệu thật rồi mới “đóng băng” hợp đồng cho consumer bên ngoài.

## 18. Khi nào code-first thực tế hơn?

**Prototype nội bộ của một nhóm.** Domain thay đổi theo feedback hằng ngày; việc chỉnh DTO/controller rồi sinh spec giúp khám phá nhanh.

**Legacy cần chuẩn hóa.** Hệ thống đã có nhiều endpoint; sinh OpenAPI từ code hiện có có thể là bước đầu xây contract catalog. Sau đó mới bổ sung các phần semantics chưa biểu diễn.

**API chỉ có một consumer do cùng nhóm sở hữu.** Lợi ích của phối hợp theo spec trước có thể thấp hơn chi phí quy trình; vẫn cần tests và compatibility policy tối thiểu.

**Framework/type system đã quản lý API khá tốt.** Nếu có generator tin cậy, DTO riêng và CI diff, code-first có thể giảm thao tác và vẫn kiểm soát contract.

**Nhu cầu thử nhiều phương án nhỏ.** Khi design space chưa rõ, code-first giúp dựng mẫu, đo latency, kiểm tra mô hình dữ liệu rồi mới cam kết interface dài hạn.

Dù vậy, khi API có thêm consumer độc lập, đặc biệt ở bên ngoài nhóm, cần nâng mức review contract. Không phải cứ bắt đầu code-first là phải mãi code-first.

## 19. Cách kết hợp theo vòng đời sản phẩm

Một hệ thống có thể thay đổi phương pháp khi trưởng thành:

~~~text
Giai đoạn 1: Khám phá
  Code-first prototype hoặc hợp đồng giả lập tối thiểu
        |
        v
Giai đoạn 2: Có consumer thực
  Review ví dụ, schema và semantics xuyên nhóm
        |
        v
Giai đoạn 3: Hợp đồng ổn định
  Lưu contract có version, diff, provider/consumer tests
        |
        v
Giai đoạn 4: Nhiều consumer / public API
  Contract-first cho thay đổi lớn, migration policy nghiêm
~~~

Đây không phải lộ trình bắt buộc. Cách thực tế là lựa chọn theo **rủi ro thay đổi**:

- Thay đổi nhỏ, nội bộ, có rollback nhanh: code-first có thể đủ.
- Thay đổi ảnh hưởng nhiều nhóm hoặc phá vỡ tương thích: yêu cầu review hợp đồng trước triển khai.
- Một API đã phát hành lâu dài: mọi thay đổi cần diff, communication và tests, bất kể nguồn spec xuất phát từ code hay YAML.

## 20. Hợp đồng, ranh giới dữ liệu và microservice ownership

Một service contract tốt phải giúp che giấu chi tiết nội bộ, chứ không chỉ biến lời gọi trong tiến trình thành HTTP.

Các câu hỏi kiến trúc quan trọng:

1. Dịch vụ nào sở hữu quyết định và dữ liệu nguồn sự thật?
2. Consumer có đang đọc trực tiếp bảng dữ liệu của provider không?
3. API mô tả một năng lực nghiệp vụ hay chỉ expose CRUD của entity nội bộ?
4. Khi đổi schema database, có bắt buộc đổi API không?
5. Một thay đổi nghiệp vụ phổ biến có phải chỉnh nhiều hợp đồng cùng lúc không?
6. Có thể triển khai/rollback hai service mà không cần khóa phiên bản không?
7. Lời gọi đồng bộ có cần giao dịch xuyên service hay có thể chuyển thành workflow rõ ràng?
8. Khi provider lỗi, consumer có xử lý được status, retry và timeout đã công bố không?

Contract-first **không tự sửa ranh giới sai**. Một OpenAPI đẹp bao bọc shared database và distributed transaction vẫn có thể là một distributed monolith.

Code-first **không nhất thiết tạo coupling cao** nếu DTO riêng, ownership dữ liệu và compatibility được bảo vệ. Ranh giới nghiệp vụ quan trọng hơn hình thức soạn hợp đồng.

## 21. Thiết kế lỗi, retry và idempotency

Hai quy trình đều cần đặc tả lỗi với ý nghĩa có thể lập trình được:

| HTTP status | Error code ví dụ | Ý nghĩa | Gợi ý consumer |
|---|---|---|---|
| 400 | MALFORMED_REQUEST | Cú pháp hoặc format sai | Sửa request |
| 401 | UNAUTHENTICATED | Không có thông tin xác thực hợp lệ | Xin token phù hợp |
| 403 | FORBIDDEN | Không đủ quyền | Không retry y nguyên |
| 404 | RESERVATION_NOT_FOUND | Không tìm thấy / không cho tiết lộ | Kiểm tra quyền và ID |
| 409 | STOCK_NOT_AVAILABLE | Không đủ tồn kho | Điều chỉnh số lượng hoặc thông báo |
| 409 | IDEMPOTENCY_KEY_REUSED | Cùng key nhưng payload khác | Không đổi payload khi retry cùng key |
| 422 | INVALID_QUANTITY | Vi phạm ràng buộc nghiệp vụ | Sửa trường đầu vào |
| 429 | RATE_LIMITED | Quá giới hạn | Backoff; theo Retry-After nếu có |
| 503 | SERVICE_UNAVAILABLE | Tạm thời không xử lý | Retry giới hạn theo policy |

Mã lỗi là ví dụ, cần thống nhất theo tiêu chuẩn tổ chức. Một contract tốt chỉ rõ:

- Trường hợp nào tạo side effect, dù response bị mất.
- Cách client dùng idempotency key cho cùng thao tác logic.
- Cửa sổ hiệu lực của key và hành vi sau khi key hết hạn.
- Cách tra cứu kết quả chưa biết sau timeout.
- Những lỗi nào phải dừng, những lỗi nào có thể retry có kiểm soát.
- Có giới hạn deadline, retry budget, backoff và quota không.

Chỉ công bố “POST trả 201” nhưng không nói gì về retry là chưa đủ với thao tác có hiệu ứng phụ.

## 22. Bảo mật là một phần của contract

Dù bắt đầu từ YAML hay controller, hãy ghi:

- Phương thức xác thực: OAuth2, bearer token, mTLS hoặc mô hình phù hợp.
- Authorization theo scope/role **và theo thực thể nghiệp vụ**.
- Tenant isolation: cùng ID ở tenant khác phải không bị đọc/sửa trái phép.
- Không trả lỗi làm lộ tài nguyên thuộc tenant khác.
- Những trường chứa PII, dữ liệu tài chính hoặc bí mật phải được hạn chế.
- Quy tắc log, trace, audit và dữ liệu nào không được xuất hiện trong example.
- Header do người dùng cung cấp có thể bị giả mạo; không tin mặc định vào X-Tenant-Id hoặc X-User-Id nếu chưa có ranh giới tin cậy.
- Chính sách rate limit và payload size để tránh bị lạm dụng.

Code-first có thể đưa security vào framework annotations; contract-first có thể ghi security schemes trong OpenAPI. Cả hai đều cần test quyền ở runtime.

## 23. Migrate breaking change mà không deploy lockstep

Giả sử API v1 có:

~~~json
{
  "amount": 240000
}
~~~

Nhưng khách hàng quốc tế cần currency. Việc âm thầm đổi đơn vị hoặc cách tính amount sẽ phá vỡ consumer cũ. Một chiến lược an toàn:

### Bước 1: Expand

- Giữ field cũ và ngữ nghĩa cũ trong thời gian chuyển đổi.
- Bổ sung API/field/version mới, ví dụ amountMinorUnits + currency.
- Provider chấp nhận cả request cũ và mới nếu an toàn.
- Thêm metric để biết consumer nào dùng phiên bản nào.

### Bước 2: Migrate

- Công bố hướng dẫn chuyển đổi có ví dụ cụ thể.
- Chạy consumer-driven contract tests cho cả hai phiên bản.
- Chuyển từng consumer một, không buộc tất cả deploy cùng lúc.
- Theo dõi latency, error rate, số request v1 và các lỗi chuyển đổi.
- Xử lý dữ liệu lịch sử theo semantics đã lưu, không tự đổi ý nghĩa.

### Bước 3: Contract

- Chỉ loại bỏ field/version cũ sau khi điều kiện deprecation được đáp ứng và consumer đã chuyển.
- Có đường rollback hoặc biện pháp tương ứng khi không thể rollback dữ liệu.
- Ghi ngày ngừng hỗ trợ, nhóm chịu trách nhiệm và bằng chứng adoption.

Nguyên tắc **expand → migrate → contract** phù hợp với nhiều thay đổi API và schema, nhưng không thay thế kế hoạch riêng cho transaction, dữ liệu nhạy cảm hoặc event history.

## 24. Chọn phương pháp bằng tiêu chí có thể đo

Đừng chỉ chọn theo cảm nhận của team. Có thể thiết lập baseline và một thử nghiệm nhỏ.

### 24.1. Các chỉ số quan sát

| Metric | Muốn hiểu điều gì? |
|---|---|
| Số breaking change bị phát hiện trước merge | Khả năng phát hiện sớm |
| Số incident do API contract mismatch | Độ tin cậy tích hợp |
| Thời gian từ đề xuất interface đến consumer dùng được | Tốc độ phối hợp |
| Số PR phải sửa nhiều repository để đổi một contract | Change coupling |
| Tỷ lệ release phải deploy đồng bộ | Khả năng độc lập triển khai |
| Số consumer được xác nhận tương thích trước release | Phạm vi kiểm soát |
| Số API thiếu error/auth semantics | Mức độ đầy đủ |
| Thời gian cập nhật tài liệu sau khi code thay đổi | Nguy cơ spec drift |
| Tỷ lệ test hành vi quan trọng được tự động hóa | Bằng chứng thực thi đúng contract |

Ví dụ, thử code-first có CI export OpenAPI cho API nội bộ nhỏ; thử contract-first cho API đối tác đang chờ tích hợp. So sánh chi phí phối hợp, lỗi tương thích và thời gian phản hồi thay đổi. Không tối ưu “số dòng YAML” hoặc “số annotation” nếu hai cách cho kết quả vận hành khác nhau.

### 24.2. Guardrails

Khi đẩy nhanh tốc độ phát triển, vẫn cần giữ:

- Không phát hành breaking change ngoài quy trình đã thống nhất.
- Không giảm kiểm soát authorization, tenant isolation và bảo vệ dữ liệu.
- Không bỏ idempotency/consistency tests cho lệnh có side effect.
- Không xuất bản spec không khớp implementation.
- Không tạo dependency khiến nhiều nhóm bắt buộc deploy lockstep.

Một quy trình nhanh hơn nhưng tăng incident không hẳn là lựa chọn tốt.

## 25. Các lỗi thường gặp

### 25.1. “Contract-first nghĩa là tài liệu trước, còn code không quan trọng”

Sai. Spec chỉ có giá trị khi implementation và tests chứng minh nó đúng. Review phải bao gồm nghiệp vụ, không chỉ YAML.

### 25.2. “Code-first nên không cần thiết kế hợp đồng”

Sai. Implementation có thể chạy nhưng thiếu error semantics, version policy, idempotency, authorization hoặc trạng thái sau timeout.

### 25.3. “Generated client là bằng chứng tương thích”

Chưa đủ. Generated client có thể deserialize thành công nhưng dùng sai semantics; runtime behavior, lỗi và authorization cần test riêng.

### 25.4. “Thêm field chắc chắn tương thích”

Không tuyệt đối. Strict JSON schema/enum handling có thể khiến consumer cũ lỗi. Cần kiểm tra consumer thực tế.

### 25.5. “Cho phép cả YAML và annotation cùng được sửa độc lập”

Dễ dẫn tới hai nguồn sự thật. Hãy quy định artifact nào authoritative, artifact nào generated, và CI phải phát hiện drift.

### 25.6. “Mỗi API change phải tăng major version”

Không nhất thiết. Thêm optional field với default an toàn có thể tương thích. Nhưng thay semantics hoặc tăng yêu cầu auth có thể là breaking dù schema không đổi.

### 25.7. “Schema là đủ cho event”

Không. Event còn delivery, ordering, dedup, replay, retention và side effect. Một schema hợp lệ không đảm bảo consumer xử lý đúng khi message trùng.

### 25.8. “Consumer phải dùng chung domain model jar”

Chia sẻ model nội bộ qua thư viện chung có thể làm các service phụ thuộc phiên bản classpath và refactor của nhau. Nên chia sẻ hợp đồng được quản lý, không đưa internals thành API.

### 25.9. “Mock pass thì provider sẽ pass”

Mock thường trả kết quả dựa trên ví dụ tĩnh, không thực thi DB/invariant. Vẫn cần provider contract tests và integration tests.

### 25.10. “OpenAPI đã được sinh là hoàn tất”

Một file spec được sinh chưa chứng minh auth, lỗi, consistency hay compatibility được mô tả đầy đủ. Phải có review công khai và kiểm thử hành vi.

## 26. Mẫu ADR quyết định cách thiết kế hợp đồng

~~~markdown
# ADR: Chọn contract-first hay code-first cho <service>

Bối cảnh:
- Service và bounded context:
- Producer/provider owner:
- Consumer hiện tại và dự kiến:
- Độ ổn định của domain:
- Mức độ thay đổi interface:
- Rủi ro về dữ liệu, bảo mật và side effect:

Phương án:
1. Contract-first với OpenAPI/Protobuf/AsyncAPI
2. Code-first + sinh contract tự động
3. Hybrid có nguồn sự thật rõ ràng

Quyết định:
- Phương án được chọn:
- Artifact authoritative:
- Vì sao phù hợp:
- Điều kiện xem lại:

Quy trình thay đổi:
- Ai review và phê duyệt:
- Cách sinh code/schema hoặc cập nhật spec:
- Cách kiểm tra compatibility:
- Cách chạy provider/consumer tests:
- Cách publish spec và version:
- Chính sách breaking change và deprecation:

Rủi ro và trade-off:
- Tốc độ phát triển:
- Spec drift:
- Consumer coordination:
- Versioning/migration:
- Sự cố tương thích và rollback:

Metrics đánh giá sau vài release:
- Contract mismatch incidents:
- Release coordination rate:
- Lead time for API changes:
- Consumer adoption:
~~~

Một ADR tốt ghi **quyết định theo điều kiện hiện tại**, không biến contract-first/code-first thành khẩu hiệu bắt buộc mọi service của tổ chức phải giống nhau.

## 27. Bài tập: thiết kế API hoàn tiền

Bạn tham gia đội xây dựng **Refund Service**. Frontend và Payment Service của hai nhóm khác nhau cần tích hợp. API sẽ được dùng bởi một đối tác trong vài tháng tới. Yêu cầu ban đầu:

- Tạo yêu cầu hoàn tiền cho một giao dịch đã được thanh toán.
- Cho phép hoàn một phần nếu tổng tiền hoàn không vượt số tiền đã thanh toán.
- Trả trạng thái PENDING khi nhà cung cấp chưa xác nhận.
- Đảm bảo retry không tạo hai yêu cầu hoàn tiền.
- Có thể truy vấn trạng thái để xử lý timeout chưa rõ kết quả.

**Yêu cầu thực hành:**

1. Liệt kê các consumer và rủi ro thay đổi hợp đồng.
2. Chọn contract-first, code-first hay hybrid; giải thích lý do theo tiêu chí cụ thể.
3. Thiết kế POST /v1/refunds với input paymentId, amountMinorUnits, currency, reason và Idempotency-Key. Quy định required/optional, phạm vi giá trị và authorization.
4. Thiết kế response cho **đã nhận**, **hoàn tiền thành công**, **bị từ chối**. Phân biệt 201 và 202 theo nghĩa nghiệp vụ.
5. Thiết kế GET /v1/refunds/{refundId} để client kiểm tra sau timeout.
6. Đề xuất mã lỗi và quy tắc retry cho PAYMENT_NOT_FOUND, REFUND_LIMIT_EXCEEDED, IDEMPOTENCY_KEY_REUSED, RATE_LIMITED và PROVIDER_UNAVAILABLE.
7. Cho một breaking change giả định: đổi cách biểu diễn tiền từ number sang object. Lập kế hoạch expand/migrate/contract.
8. Viết hai provider contract tests, một consumer-driven test, một concurrency test chống hoàn quá số tiền và một test timeout sau khi provider đã commit.
9. Vẽ pipeline để phát hiện breaking changes trước production.
10. Nêu điều kiện khiến nhóm cần chuyển từ code-first sang contract-first khi số consumer tăng.

**Gợi ý:** Với nhiều nhóm và đối tác tương lai, có lý do rõ để review hợp đồng trước implementation. Tuy nhiên, một prototype code-first vẫn có thể giúp khám phá semantics PENDING/COMPLETED/REJECTED trước khi chốt version được công bố. Không chọn chỉ vì tên phương pháp.

## 28. Checklist trước khi áp dụng

- [ ] Đã xác định bounded context, owner và consumer chính.
- [ ] Biết đâu là nguồn sự thật của hợp đồng.
- [ ] Input, output, error và auth được mô tả có thể kiểm thử.
- [ ] Có ví dụ request/response thành công và thất bại.
- [ ] Có mô tả business invariants, idempotency và consistency.
- [ ] Hợp đồng có version/changelog và chính sách deprecation.
- [ ] Có CI validate spec, sinh artifact nhất quán và diff.
- [ ] Có provider/consumer contract tests theo nhu cầu.
- [ ] Có integration tests cho transaction, concurrency, retry và side effect.
- [ ] Không đưa persistence entity/domain internals thành public API ngoài ý muốn.
- [ ] Có kế hoạch phối hợp khi breaking change.
- [ ] Consumer cũ có thời gian chuyển đổi, không bắt buộc deploy lockstep vô cớ.
- [ ] Event contract nêu rõ ordering, duplication, replay và schema evolution khi dùng async.
- [ ] Tài liệu công bố đúng phiên bản đang chạy.
- [ ] Có metrics đánh giá lỗi tương thích, thời gian phối hợp và mức độ độc lập triển khai.

## 29. Ghi nhớ

**Contract-first** đặt hợp đồng được thống nhất trước khi implementation chi tiết, rất hữu ích khi nhiều consumer cần phối hợp và độ ổn định giao diện có giá trị cao. **Code-first** phát triển implementation trước rồi sinh hợp đồng, phù hợp với khám phá nhanh hoặc API nội bộ ít phụ thuộc nếu có kiểm soát chất lượng và compatibility tốt. **Hybrid** giúp chuyển từ thử nghiệm sang hợp đồng ổn định nhưng cần xác định nguồn sự thật rõ ràng.

Không phương pháp nào tự bảo đảm đúng nghiệp vụ. Trong microservices, điều quan trọng nhất là **hợp đồng có ý nghĩa rõ, tuân thủ ranh giới sở hữu, được version, được kiểm thử và cho phép các nhóm triển khai độc lập mà không gây lỗi cho consumer**.
