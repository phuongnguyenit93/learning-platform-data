# Tính lũy đẳng, khóa chống trùng và kết quả không xác định

Khi gọi một microservice qua HTTP, **retry** giúp khắc phục một số lỗi tạm thời như kết nối bị reset, instance mới chết hoặc response đến quá chậm. Nhưng với thao tác ghi, retry cũng có thể khiến **cùng một ý định nghiệp vụ được thực hiện hai lần**: tạo hai đơn hàng, giữ chỗ hai lần hoặc trừ tiền hai lần. Sự cố thường xuất hiện khi caller **không biết** server đã hoàn tất request đầu tiên hay chưa.

Bài thuộc chương **Gửi lại yêu cầu** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Trong Spring Cloud LoadBalancer, client chọn một `ServiceInstance` theo service ID từ discovery, health check và chính sách định tuyến; lần retry có thể gửi đến một instance khác. Vì vậy, hiểu **tính lũy đẳng (idempotency)**, **khóa chống trùng (idempotency key)** và **kết quả không xác định (unknown outcome)** là điều kiện quan trọng trước khi cấu hình retry/timeout cho RestClient, WebClient hoặc OpenFeign.

> Thông điệp cốt lõi: **timeout không chứng minh request đã thất bại ở server; retry không tự tạo tính lũy đẳng; và LoadBalancer không bảo đảm một thao tác nghiệp vụ chỉ được thực thi một lần.** Tính an toàn phải được thiết kế ở hợp đồng API và phía xử lý tác dụng phụ.

## 1. Vì sao retry có thể tạo kết quả trùng?

Giả sử `order-service` gọi `reservation-service`:

~~~http
POST /api/reservations HTTP/1.1
Host: reservation-service
Content-Type: application/json

{"sku":"sku-42","quantity":1}
~~~

Trong lần thử đầu, instance A ghi nhận một reservation thành công. Response bị mất trên đường về, làm caller timeout. Caller tiếp tục gửi lại cùng body; LoadBalancer có thể chọn instance B. Nếu server không có cơ chế nhận biết lệnh này đã được thực hiện, B sẽ tạo reservation thứ hai.

~~~mermaid
sequenceDiagram
    autonumber
    participant Caller as order-service
    participant LB as Spring Cloud LoadBalancer
    participant A as reservation-a
    participant B as reservation-b
    participant DB as Database

    Caller->>LB: POST /api/reservations, attempt 1
    LB-->>Caller: Chọn A
    Caller->>A: POST request
    A->>DB: INSERT reservation #101
    DB-->>A: COMMIT thành công
    A--xCaller: Response trễ hoặc bị mất
    Note over Caller: Timeout, chưa biết kết quả
    Caller->>LB: Retry cùng ý định, attempt 2
    LB-->>Caller: Có thể chọn B
    Caller->>B: POST request
    B->>DB: INSERT reservation #102
    DB-->>B: COMMIT thành công
    B-->>Caller: HTTP 201, reservation #102
    Note over Caller,DB: Hai reservation cho một ý định
~~~

Từ phía caller, attempt 1 có thể đã thất bại về **truyền thông**; từ phía server, attempt 1 lại đã thành công về **nghiệp vụ**. Cả hai sự thật cùng tồn tại mà không mâu thuẫn.

Phân biệt ba đại lượng:

- **Business operation**: ý định nghiệp vụ, ví dụ “giữ một sản phẩm cho đơn X”.
- **HTTP attempt**: một lần thực hiện request qua mạng; một operation có thể có nhiều attempts.
- **Business side effect**: thay đổi dữ liệu hoặc hành động ngoại vi thực tế như tạo reservation, trừ tiền, phát sự kiện.

Khi retry, mục tiêu không phải ngăn mọi HTTP attempt bị lặp; mục tiêu là tránh **tác dụng phụ bị lặp ngoài dự kiến**.

## 2. Tính lũy đẳng thực sự là gì?

Một thao tác được gọi là **idempotent** nếu áp dụng cùng thao tác nhiều lần có **hiệu ứng dự kiến trên trạng thái** tương đương áp dụng một lần. Ví dụ thiết lập `status=ACTIVE` hai lần thường vẫn dẫn đến trạng thái ACTIVE.

Viết tượng trưng:

~~~text
f(f(state, command), command) = f(state, command)
~~~

Ở đây dấu bằng nói về **kết quả nghiệp vụ quan trọng**, không nhất thiết tất cả log, timestamp, HTTP status hoặc chi phí xử lý đều giống hệt.

### HTTP method và ngữ nghĩa nghiệp vụ

| HTTP method | Tính chất idempotent theo semantics HTTP | Cảnh báo thực tế |
|---|---|---|
| GET, HEAD | Safe và idempotent theo hợp đồng HTTP | Không nên thay đổi trạng thái nghiệp vụ; log/metric vẫn có thể đổi |
| PUT | Idempotent theo ý nghĩa thay thế trạng thái resource | Implementation sai hoặc tác dụng phụ ngoài DB vẫn có thể gây vấn đề |
| DELETE | Idempotent về hiệu ứng resource | Lần đầu `204`, lần sau `404` vẫn có thể phù hợp với hiệu ứng idempotent |
| POST | Không mặc nhiên idempotent | Thường cần idempotency key cho tạo resource/thao tác |
| PATCH | Không mặc nhiên idempotent | “Set stock=10” khác “increase stock by 10” |

Ví dụ:

~~~text
PUT /items/42 {"stock":10}       -> gọi lại vẫn stock=10
PATCH /items/42 {"stockDelta":+1} -> gọi lại có thể tăng stock nhiều lần
POST /payments {"amount":500}    -> gọi lại có thể tạo giao dịch khác
~~~

Không kết luận thao tác an toàn chỉ từ tên method: phải kiểm tra **contract, thực thi thật ở server và dependency bên ngoài**. Một PUT có thể bị ứng dụng viết sai theo hướng gửi email mỗi lần, và một POST hoàn toàn có thể trở thành idempotent nếu API thiết kế nhận diện cùng ý định.

**Safe** (không nhằm thay đổi trạng thái nghiệp vụ) và **idempotent** (lặp lại không tăng tác dụng phụ dự kiến) là hai khái niệm khác nhau. Một request idempotent không nhất thiết không tốn CPU hoặc không tạo thêm log.

## 3. “Không xác định kết quả” bắt đầu từ đâu?

Khi caller không nhận được response, có thể có những trạng thái sau:

| Giai đoạn lỗi | Khả năng server đã thực thi? | Caller biết chắc điều gì? |
|---|---|---|
| Chưa có `ServiceInstance` để chọn | Không gửi HTTP đến server đích qua lần chọn này | Không thực thi qua attempt chưa gửi |
| Lỗi kết nối trước khi gửi HTTP request | Thường chưa tới server, nhưng phải xác minh transport | Có lỗi thiết lập kết nối |
| Đứt kết nối khi gửi body | Server có thể nhận một phần hoặc toàn bộ | Không thể suy chắc từ một lỗi I/O |
| Hết read/response timeout | Có thể chưa xử lý, đang xử lý hoặc đã commit | Chưa nhận response đúng hạn |
| Server đã commit, response bị mất | **Đã thực thi** | Caller vẫn có thể chỉ thấy timeout |
| Nhận HTTP 500/503 | Server hoặc gateway đã phản hồi lỗi | Không tự chứng minh tác dụng phụ trước lỗi đã rollback |
| Nhận response thành công và giải mã được | Có bằng chứng theo HTTP/API contract | Vẫn phải hiểu định nghĩa “thành công” của nghiệp vụ |

Trong hệ phân tán, caller không thể tự suy ra một trạng thái giao dịch chắc chắn chỉ từ việc timeout. Vì vậy nên có trạng thái riêng như `UNKNOWN` hoặc `PENDING_VERIFICATION` thay vì đánh đồng với `FAILED`.

~~~mermaid
flowchart TD
    A["Caller gửi operation K"] --> B{"Có response theo contract?"}
    B -->|"Thành công"| C["COMPLETED"]
    B -->|"Lỗi nghiệp vụ xác định"| D["FAILED theo contract"]
    B -->|"Timeout / mất response"| E["UNKNOWN"]
    E --> F["Tra cứu operation theo key K"]
    F --> G{"Trạng thái đọc được?"}
    G -->|"COMPLETED"| C
    G -->|"PENDING"| H["Backoff và tra cứu tiếp"]
    H --> F
    G -->|"Không rõ / query lỗi"| I["Giữ UNKNOWN; đối soát"]
    G -->|"NOT_FOUND"| J["Chưa đủ để khẳng định request đầu chưa tới"]
    J --> K["Chỉ retry với cùng K nếu server hỗ trợ dedup bền vững"]
~~~

Đặc biệt, `NOT_FOUND` có thể xuất hiện do truy vấn quá sớm, đọc từ replica chậm hoặc key chưa được ghi trong khi request đầu còn chạy. Nó **không đủ** để cho phép retry với một key khác.

## 4. Idempotency key: định danh một ý định, không phải một attempt

Một cách phổ biến để làm POST an toàn trước retry là gửi header:

~~~http
POST /api/reservations HTTP/1.1
Host: reservation-service
Idempotency-Key: 0b8d3a2e-...-operation
Content-Type: application/json

{"sku":"sku-42","quantity":1}
~~~

Key đại diện cho **một business operation**. Caller tạo key **trước attempt đầu tiên**, giữ nguyên key qua mọi lần thử hoặc đối soát của cùng operation, và dùng **key mới cho operation nghiệp vụ mới**.

| Việc làm | Đúng hay sai? | Vì sao? |
|---|---|---|
| Retry cùng body, cùng key K | Đúng nếu server hỗ trợ idempotency | Các attempts được nhận diện là một ý định |
| Retry cùng body nhưng tạo key K2 | Nguy hiểm | Server có thể coi là operation thứ hai |
| Dùng lại K cho một payload khác | Sai theo contract thông thường | Không được âm thầm trả kết quả cũ cho lệnh khác |
| Gọi status với K sau timeout | Hữu ích | Giúp xác minh nếu server cung cấp endpoint tương ứng |
| Lưu key riêng trên từng instance | Không đủ với LoadBalancer | Retry có thể sang instance khác |
| Chỉ thêm header K nhưng backend không kiểm tra | Không đủ | Header không tạo bảo đảm chống trùng |

Không có một định dạng key bắt buộc duy nhất cho mọi API. Có thể sử dụng một UUID ngẫu nhiên khó đoán, hoặc định danh nghiệp vụ đã được thống nhất, nhưng phải đảm bảo **tính duy nhất trong phạm vi contract**, tránh lộ bí mật và ngăn caller dùng key của người khác.

### Khóa key nên được scope thế nào?

Thông thường nên dùng kết hợp:

~~~text
(tenant_id hoặc principal, operation_type, idempotency_key)
~~~

Ví dụ cùng chuỗi `request-123` do tenant A và B tạo ra không nên khiến kết quả của A bị lộ cho B. Cũng cần xác định key thuộc endpoint, operation type hay một workflow lớn: không cho cùng key vô tình gom các thao tác khác nhau.

## 5. Cùng key nhưng khác payload: phải phát hiện xung đột

Giả sử request đầu:

~~~json
{"sku":"sku-42","quantity":1}
~~~

Attempt thứ hai có cùng key nhưng body là:

~~~json
{"sku":"sku-42","quantity":4}
~~~

Nếu server chỉ kiểm tra key và trả lại biên nhận cũ, caller có thể tưởng đã giữ bốn sản phẩm dù thực tế chỉ giữ một. Do đó cần lưu **fingerprint của request** cùng key. Fingerprint nên bao gồm các trường có ý nghĩa nghiệp vụ, operation, scope và format canonical ổn định.

Một contract có thể quy định:

| Trạng thái key | Payload | Kết quả được khuyến nghị |
|---|---|---|
| Chưa từng thấy K | Hợp lệ | Nhận xử lý, tạo record PENDING |
| K đã COMPLETED | Payload tương đương | Trả lại kết quả đã ghi |
| K đang PENDING | Payload tương đương | Trả PENDING/202 hoặc chính sách chờ có giới hạn |
| K tồn tại | Payload khác | Trả conflict, ví dụ HTTP `409` theo contract |
| K đã hết hạn theo retention | Có thể không còn record | Phải quy định retry horizon và cách đối soát |

Các mã HTTP ở đây là **gợi ý thiết kế**, không phải quy tắc Spring Cloud LoadBalancer áp dụng sẵn. Phần triển khai server quyết định contract chính xác.

Nếu lưu hash của JSON, không đơn giản hash raw JSON string khi các trường có thể đổi thứ tự, khoảng trắng hoặc định dạng tương đương. Cần canonicalization hoặc lựa chọn các field nghiệp vụ ổn định; tránh hash payload chứa giá trị không liên quan như trace ID.

## 6. Bảo vệ request trùng đến đồng thời: “check rồi insert” là chưa đủ

Một lỗi phổ biến:

~~~java
if (!repository.existsByKey(key)) {
    repository.insertReservation(command);
    repository.saveKey(key);
}
~~~

Khi hai request với cùng key tới hai instance đồng thời:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as reservation-a
    participant B as reservation-b
    participant DB as Shared DB

    A->>DB: exists(K)?
    DB-->>A: false
    B->>DB: exists(K)?
    DB-->>B: false
    A->>DB: INSERT reservation #101
    B->>DB: INSERT reservation #102
    A->>DB: SAVE idempotency key K
    B->>DB: SAVE idempotency key K
    Note over A,B: Race nếu thiếu unique/transaction
~~~

Một kiểm tra `exists` rồi `insert` gồm nhiều bước riêng biệt, nên không ngăn hai request cùng vượt qua kiểm tra. Phải có **điểm quyết định nguyên tử** tại kho dữ liệu chung, ví dụ:

- Unique constraint trên `(tenant_id, operation, idempotency_key)`.
- Transaction thích hợp cho việc claim key, tạo tác dụng phụ và ghi kết quả.
- Một cơ chế sở hữu key hoặc state machine có xử lý concurrency, crash và thời gian sống.
- Nếu side effect nằm ở hệ thống ngoài transaction, cần thêm idempotency ở hệ thống đích hoặc giao thức đối soát/outbox/saga.

Chỉ dùng mutex trong một JVM cũng không bảo vệ request tới **hai replica khác nhau**. Đặc biệt trong Spring Cloud LoadBalancer, retry có thể được gửi tới một `ServiceInstance` mới.

## 7. Mô hình trạng thái bền vững cho request

Một record chống trùng nên lưu tối thiểu:

| Trường | Mục đích |
|---|---|
| `tenant_id` | Giới hạn phạm vi chủ sở hữu |
| `operation_type` | Phân biệt thao tác |
| `request_key` | Nhận diện một business operation |
| `request_hash` | Phát hiện key dùng với payload khác |
| `status` | `PENDING`, `COMPLETED` hoặc `FAILED` theo contract |
| `result_reference` | Định danh reservation/payment đã tạo |
| `response_snapshot` hoặc trường kết quả | Trả lại kết quả nhất quán cho replay |
| `created_at/updated_at` | Vận hành, timeout xử lý và retention |

Ví dụ schema PostgreSQL minh họa:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id VARCHAR(100) NOT NULL,
    operation_type VARCHAR(100) NOT NULL,
    request_key VARCHAR(200) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    result_reference VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, operation_type, request_key)
);

CREATE TABLE reservations (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Đây là **schema minh họa**, chưa phải một hệ thống chống trùng production đầy đủ. Cần thiết kế transaction isolation, cơ chế ownership, thời gian xử lý quá hạn, response snapshot, quyền truy cập, lưu trữ và dọn dữ liệu theo nhu cầu thực tế.

### Luồng xử lý transaction

~~~text
1. Validate tenant, key, payload
2. Tính request fingerprint
3. Thử claim key trong shared durable store bằng thao tác atomic
4a. Nếu key đã có, so fingerprint:
    - Khác nhau: conflict
    - COMPLETED: trả kết quả đã lưu
    - PENDING: trả trạng thái đang xử lý/chờ có giới hạn
4b. Nếu claim thành công:
    - Thực hiện nghiệp vụ, ghi domain record
    - Ghi kết quả và trạng thái COMPLETED một cách nhất quán
5. Commit và trả response
~~~

Mô hình có thể dùng transaction gộp bước claim với thay đổi dữ liệu cho nghiệp vụ DB cục bộ, hoặc tách một record PENDING ngắn hạn khi cần xử lý lâu. Nếu tách transaction, phải có cách xử lý **crash sau khi claim nhưng trước khi hoàn tất**, không để key bị PENDING vô thời hạn.

Đừng xóa PENDING rồi chạy lại tùy tiện nếu chưa biết side effect đã xảy ra chưa. Lease/timeout chỉ nói worker sở hữu key có thể đã chết, **không chứng minh thao tác bên ngoài DB chưa hoàn tất**.

## 8. Minh họa atomic claim bằng unique constraint

Với cơ sở dữ liệu hỗ trợ upsert, việc tranh quyền xử lý một key có thể bắt đầu bằng thao tác atomic:

~~~sql
INSERT INTO idempotency_records
    (tenant_id, operation_type, request_key, request_hash, status)
VALUES
    (:tenantId, 'CREATE_RESERVATION', :key, :requestHash, 'PENDING')
ON CONFLICT (tenant_id, operation_type, request_key)
DO NOTHING;
~~~

Sau đó, code ứng dụng phân biệt **insert đã thành công hay có conflict** qua số hàng bị ảnh hưởng. Nếu conflict, đọc record đang có để so fingerprint và trạng thái, thay vì tạo reservation mới.

**Cảnh báo về transaction:** đoạn SQL trên **chỉ minh họa việc claim key**. Không được coi riêng `ON CONFLICT DO NOTHING` là đủ để đảm bảo exactly-once. Phải thiết kế các bước cập nhật reservation và idempotency record đúng transaction hoặc workflow có thể phục hồi; đồng thời xét trường hợp transaction khác chưa commit và deadlock/lock timeout.

Ví dụ một flow cục bộ có thể sử dụng **cùng transaction DB** để chèn reservation rồi cập nhật idempotency record thành COMPLETED, trước khi commit. Nếu gặp lỗi và rollback, cả reservation và kết quả key chưa được commit; attempt sau có thể xử lý lại. Nếu đưa side effect ra Kafka, email hoặc hệ thống thanh toán bên ngoài transaction, cần cơ chế bền vững riêng.

## 9. Ví dụ lab: cùng key không tạo reservation thứ hai trong một JVM

Để thấy rõ hành vi, tạo một Spring Boot server mô phỏng lưu reservation trước khi response chậm. Lab dùng `ConcurrentHashMap.compute` để nguyên tử theo **một key trong một tiến trình**. Nó không chứng minh an toàn trong nhiều replica hoặc khi restart.

Các record:

~~~java
package demo.reservation;

record ReservationRequest(String sku, int quantity) {}

record ReservationReceipt(
    String reservationId,
    String sku,
    int quantity
) {}

record StoredReservation(
    ReservationRequest request,
    ReservationReceipt receipt
) {}
~~~

Controller:

~~~java
package demo.reservation;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/reservations")
class ReservationController {

    private final Map<String, StoredReservation> saved =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(1000);
    private final String instanceId;

    ReservationController(Environment env) {
        this.instanceId = env.getProperty("instance.id", "local");
    }

    @PostMapping
    ResponseEntity<ReservationReceipt> create(
        @RequestHeader("Idempotency-Key") String key,
        @RequestBody ReservationRequest request
    ) throws InterruptedException {

        if (key.isBlank() || request.quantity() <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid key or quantity");
        }

        StoredReservation entry = saved.compute(key, (k, existing) -> {
            if (existing != null) {
                if (!existing.request().equals(request)) {
                    throw new ResponseStatusException(
                        HttpStatus.CONFLICT,
                        "Key reused with a different request");
                }
                return existing;
            }

            String id = instanceId + "-" + sequence.incrementAndGet();
            ReservationReceipt receipt = new ReservationReceipt(
                id, request.sku(), request.quantity());

            return new StoredReservation(request, receipt);
        });

        System.out.println(
            "STORED instance=" + instanceId +
            " key=" + key +
            " reservation=" + entry.receipt().reservationId()
        );

        // Chỉ dùng cho lab: state đã lưu, response cố tình đến trễ.
        Thread.sleep(2500);

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(entry.receipt());
    }

    @GetMapping("/by-key/{key}")
    ResponseEntity<ReservationReceipt> find(@PathVariable String key) {
        StoredReservation entry = saved.get(key);
        if (entry == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(entry.receipt());
    }
}
~~~

Cần có một ứng dụng Spring Boot với `@SpringBootApplication` và dependency `spring-boot-starter-web` để chạy controller. Giả sử đã đóng gói được `reservation-service.jar`.

**Giới hạn cố ý của lab:**

1. Không có authentication, tenant scope, persistence hay transaction thật.
2. `ConcurrentHashMap` chỉ an toàn trong một JVM và không giữ dữ liệu khi restart.
3. `compute` tránh hai thread trong **cùng process** tạo hai receipt cho cùng key, nhưng không tránh hai instance khác nhau tạo hai receipt.
4. `Thread.sleep(2500)` tạo chậm response trong lab; không phù hợp production.
5. Key không được fingerprint bằng hash ở ví dụ, nhưng so trực tiếp các trường của record request; trong hệ thật cần canonicalization và scope rõ ràng.
6. Mọi replay được trả HTTP 201; production có thể chọn trả lại response gốc hoặc status khác theo hợp đồng, nhất là khi request đang PENDING.

## 10. Kiểm chứng timeout rồi retry đúng cùng key

Chạy một instance:

~~~bash
java -jar reservation-service.jar --server.port=18081 --instance.id=reservation-a
~~~

Gửi request với deadline một giây, ngắn hơn delay response 2,5 giây:

~~~bash
curl -v --max-time 1 \
  -X POST "http://localhost:18081/api/reservations" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: reserve-001" \
  -d '{"sku":"sku-42","quantity":1}'
~~~

Caller có thể thấy timeout vì response chưa tới. Nhưng server đã ghi map trước khi sleep. Hỏi trạng thái:

~~~bash
curl -i "http://localhost:18081/api/reservations/by-key/reserve-001"
~~~

Kết quả dự kiến:

~~~json
{
  "reservationId": "reservation-a-1001",
  "sku": "sku-42",
  "quantity": 1
}
~~~

Gửi lại **cùng key, cùng payload**, lần này cho đủ thời gian nhận response:

~~~bash
curl -i --max-time 5 \
  -X POST "http://localhost:18081/api/reservations" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: reserve-001" \
  -d '{"sku":"sku-42","quantity":1}'
~~~

Dự kiến kết quả vẫn có `reservationId=reservation-a-1001`. Gửi lại cùng key nhưng `quantity=2` sẽ nhận HTTP `409` theo code demo; gửi một **key mới** sẽ tạo receipt khác.

### Thử hai request đồng thời

Mở hai terminal và gửi hai POST cùng key trước khi request đầu trả response. Trong **một process**, `ConcurrentHashMap.compute` cung cấp thao tác atomic theo key và hai request cùng dùng một receipt.

Để phân biệt với giải pháp phân tán, mở **instance thứ hai**:

~~~bash
java -jar reservation-service.jar --server.port=18082 --instance.id=reservation-b
~~~

Gửi cùng key trực tiếp tới cổng 18081 và 18082: vì hai map độc lập, bạn có thể nhận hai mã reservation khác nhau, ví dụ `reservation-a-1001` và `reservation-b-1001`. Đây là lý do phải dùng **shared durable idempotency store** khi có nhiều `ServiceInstance`.

## 11. Retry qua Spring Cloud LoadBalancer: cùng ý định, đích có thể khác

Bên caller, có thể dùng `SimpleDiscoveryClient` để khai báo hai instance tĩnh dưới một service ID trong môi trường lab:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            reservation-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Một RestClient được tạo từ builder `@LoadBalanced` có thể gọi:

~~~java
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

record CreateReservationRequest(String sku, int quantity) {}

record ReservationDto(String reservationId, String sku, int quantity) {}

String operationKey = UUID.randomUUID().toString();

ReservationDto receipt = reservationRestClient.post()
    .uri("http://reservation-service/api/reservations")
    .header("Idempotency-Key", operationKey)
    .contentType(MediaType.APPLICATION_JSON)
    .body(new CreateReservationRequest("sku-42", 1))
    .retrieve()
    .body(ReservationDto.class);
~~~

Ở đây `reservationRestClient` phải được tạo từ `@LoadBalanced RestClient.Builder` trong Spring context; đoạn code chỉ tập trung vào request, không phải ứng dụng Java đầy đủ.

Nếu attempt 1 tới instance A và bị timeout, retry có thể tới B theo chính sách LoadBalancer/HTTP client. **Không mặc định retry luôn đổi instance**, nhưng cũng **không được thiết kế server dựa trên giả định tất cả attempts luôn tới A**. Khi dùng idempotency thật, các instance phải phối hợp qua kho dữ liệu chung.

Quan trọng: `UUID.randomUUID()` trong ví dụ được gọi **một lần trước các attempts**. Nếu tạo UUID bên trong hàm dựng lại request ở mỗi lần retry, server sẽ coi đó là các operation khác nhau.

## 12. WebClient retry có giới hạn và giữ nguyên key

Với WebClient reactive, `retryWhen` resubscribe khi publisher phát lỗi phù hợp. Một request HTTP mới có thể đi qua LoadBalancer và chọn instance khác.

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClientRequestException;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

String operationKey = UUID.randomUUID().toString();
CreateReservationRequest command =
    new CreateReservationRequest("sku-42", 1);

Mono<ReservationDto> result = reservationWebClient.post()
    .uri("http://reservation-service/api/reservations")
    .header("Idempotency-Key", operationKey)
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(command)
    .retrieve()
    .bodyToMono(ReservationDto.class)
    .timeout(Duration.ofSeconds(1))
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(1))
            .filter(error ->
                error instanceof WebClientRequestException ||
                error instanceof java.util.concurrent.TimeoutException)
    )
    .timeout(Duration.ofSeconds(4));
~~~

Đây là **ví dụ cơ chế**, không phải policy production mặc định:

- `operationKey` được tạo một lần ngoài publisher; mọi subscription do retry dùng cùng key.
- `Retry.backoff(2, ...)` cho tối đa **hai lần retry sau attempt đầu**; có thể có tối đa ba HTTP attempts.
- `timeout(1s)` trước `retryWhen` đóng vai trò deadline mỗi attempt trên publisher.
- `timeout(4s)` sau retry là deadline tổng của publisher này; nó bao gồm backoff nhưng không nhất thiết bao quát thời gian trước khi ứng dụng subscribe.
- Predicate chỉ minh họa lỗi I/O và Reactor timeout. Các loại exception khác phụ thuộc connector; cần quan sát cause trước khi mở rộng.
- Retry POST trong ví dụ **chỉ hợp lệ về nghiệp vụ khi server có cơ chế idempotency bền vững**. Server map in-memory của lab **không đáp ứng yêu cầu đó khi có hai instance**.

Không sử dụng `block()` trên WebFlux event-loop. Với reactive controller, trả `Mono<ReservationDto>` hoặc ánh xạ thành response phù hợp.

Một lỗi HTTP `503` có thể được biểu diễn thành `WebClientResponseException` và **không nằm trong filter trên**; nếu muốn retry status 503/429, cần thêm quy tắc rõ ràng, tính đến `Retry-After`, idempotency và ngân sách thời gian.

## 13. RestClient và OpenFeign: retry không tự có semantics chống trùng

Với RestClient, có thể tạo một wrapper resilience quanh lời gọi theo service ID. Với OpenFeign, tích hợp Feign và cấu hình `Retryer`/`ErrorDecoder` quyết định điều kiện thử lại. Spring Cloud OpenFeign có thể dùng `Retryer.NEVER_RETRY` làm mặc định tùy release/config; đừng suy từ Feign core hoặc từ một dependency rằng POST sẽ được retry.

Ví dụ một interface OpenFeign:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "reservation-service")
interface ReservationClient {

    @PostMapping("/api/reservations")
    ReservationDto create(
        @RequestHeader("Idempotency-Key") String operationKey,
        @RequestBody CreateReservationRequest request
    );
}
~~~

Khi logic nghiệp vụ gọi lại `client.create(key, request)`, phải sử dụng **cùng key và cùng request** cho một operation. Nếu muốn áp dụng retry tự động, cần giới hạn và quan sát attempt count, xác minh behavior khi có instance chết/không có instance và không nhân retry giữa các tầng.

### Khác biệt đáng nhớ

| Lựa chọn | Nơi cấu hình retry | Điều không tự được bảo đảm |
|---|---|---|
| RestClient | Resilience wrapper, Spring Retry/Resilience4j hoặc tích hợp LB tương thích | Không tự idempotent cho POST |
| WebClient | Reactor `retryWhen` hoặc tầng resilience/LB phù hợp | Không tự replay cùng key theo semantics nghiệp vụ |
| OpenFeign | Feign `Retryer` và cấu hình Spring Cloud/CB tương ứng | Không bảo đảm mọi phiên bản retry giống nhau |
| Spring Cloud LoadBalancer | Retry integration tùy client/version | Không bảo đảm lần sau luôn đổi instance |
| Gateway/service mesh | Chính sách retry hạ tầng | Không tự biết tác dụng phụ ở backend đã commit |

Hãy để **một nơi** chủ động quyết định retry cho một loại lỗi, hoặc ít nhất tính được tổng số HTTP attempts qua các tầng.

## 14. Bài toán outbox và tác dụng phụ ngoài database

Giả sử `reservation-service` ghi reservation trong database, sau đó phát event `ReservationCreated` hoặc gọi payment gateway. Chỉ lưu idempotency key trong database có thể không đủ để tránh phát event hai lần nếu code xử lý lại sau crash.

~~~mermaid
flowchart TD
    A["POST với key K"] --> B["Transaction DB"]
    B --> C["Ghi idempotency record"]
    B --> D["Ghi reservation"]
    B --> E["Ghi outbox event"]
    B --> F["COMMIT"]
    F --> G["Outbox worker phát event"]
    G --> H["Broker / downstream"]
    H --> I["Consumer idempotent theo event ID"]
~~~

**Transactional outbox** thường lưu domain record và event cần phát trong cùng một transaction DB. Worker phát event sau commit. Nó tránh một số tình huống “DB đã commit nhưng process chết trước khi phát event”. Tuy nhiên outbox worker có thể gửi event **nhiều lần** khi retry; consumer cần deduplication/idempotency theo event ID.

Nếu side effect là **thanh toán bên thứ ba**, nên dùng chính idempotency key hoặc định danh giao dịch được bên thanh toán hỗ trợ, kết hợp đối soát. Nếu bên ngoài không hỗ trợ chống trùng, cần thiết kế quy trình khác; không thể cam kết “exactly once” end-to-end chỉ bằng một unique constraint nội bộ.

## 15. “Exactly once” cần định nghĩa phạm vi

Ba khái niệm dễ nhầm:

| Mục tiêu | Ý nghĩa | Có được bằng cách nào? |
|---|---|---|
| At-most-once **business effect** | Một ý định không tạo tác dụng phụ vượt quá một lần | Dedup key + atomic side effect trong ranh giới được kiểm soát |
| At-least-once **delivery/attempts** | Có thể gửi lại nhiều lần nhằm tăng cơ hội thực thi | Retry với giới hạn và cơ chế tiếp nhận |
| Exactly-once **end-to-end** | Không mất và không lặp mọi tác dụng phụ xuyên toàn hệ thống | Không thể suy ra chỉ từ HTTP retry/key; cần contract và cơ chế cho từng ranh giới |

Ví dụ một hệ thống có thể gửi ba HTTP requests cùng key để đạt **at-least-once attempts**, nhưng backend chỉ tạo một reservation trong transaction DB để đạt **at-most-once side effect** cho reservation. Điều đó không có nghĩa event Kafka hoặc email chỉ phát một lần nếu chúng là các bước độc lập.

Không dùng các nhãn “exactly once” hoặc “idempotent” nếu chưa xác định **đối tượng được bảo vệ**: reservation row, payment authorization, inventory update, email hay toàn workflow.

## 16. Retention của key và xử lý PENDING bị kẹt

Idempotency record không thể lưu vô hạn trong mọi hệ thống, nhưng xóa quá sớm sẽ cho phép cùng key được xử lý lại như yêu cầu mới.

Ví dụ:

~~~text
T0     POST key=K -> tạo reservation
T+5m   caller retry sau một outage
T+1h   batch đối soát lại vì chưa nhận webhook
T+24h  request cuối cùng còn có thể bị replay theo contract
~~~

TTL của key phải dựa trên **retry horizon + thời gian đối soát + yêu cầu nghiệp vụ và pháp lý**, không chỉ dựa vào timeout HTTP 1 giây. Trước khi xóa record, cân nhắc kết quả đã được lưu ở nơi khác, khả năng query operation bằng ID và chính sách chống trùng lâu dài.

Với record PENDING tồn tại quá lâu:

1. Xác định worker đang sở hữu attempt còn hoạt động hay đã chết.
2. Kiểm tra side effect theo operation ID và trạng thái các dependency ngoài DB.
3. Đặt cơ chế lease/recovery phù hợp nếu công việc có thể tiếp tục.
4. Không chạy lại side effect chỉ vì `updated_at` đã cũ.
5. Ghi lại reconciliation outcome trước khi chuyển trạng thái và giải phóng key.

Một process bị chết sau khi gửi lệnh tới payment gateway nhưng trước khi nhận response là tình huống đặc biệt nguy hiểm: cần hỏi trạng thái giao dịch phía gateway, không tạo một payment hoàn toàn mới.

## 17. Quan sát để phân biệt operation với HTTP attempt

Nếu chỉ đếm HTTP status theo instance, một operation bị retry ba lần sẽ trông giống ba yêu cầu độc lập. Cần liên kết các attempts với **business operation ID**.

| Trường hoặc metric | Mục đích |
|---|---|
| `operationId` / key đã che bớt | Nối các attempts của cùng ý định |
| `attemptNumber` | Biết đây là lần gửi thứ mấy |
| `serviceId` | Xác định downstream logic |
| `selectedInstance` | Biết LoadBalancer chọn replica nào |
| `timeoutKind` / exception cause | Phân biệt connect, read, response và tổng deadline |
| `httpStatus` | Biết đã nhận HTTP response hay chưa |
| `idempotencyOutcome` | NEW, REPLAY, CONFLICT, PENDING, COMPLETED |
| `businessResultId` | Đối chiếu reservation/payment đã tạo |
| `retryDelay` / remaining deadline | Phát hiện retry quá dày hoặc vượt ngân sách |
| `dedupConflictCount` | Phát hiện caller dùng cùng key với payload khác |
| `inflightOperations` | Theo dõi các key PENDING và queue |
| `reconciliationLag` | Biết UNKNOWN tồn tại bao lâu |

Ví dụ log **minh họa**, không phải format mặc định của Spring Cloud:

~~~text
caller op=op-71 attempt=1 key_hash=*** service=reservation-service instance=A
server-A op=op-71 idem=NEW reservation=reservation-101 committed=true
caller op=op-71 attempt=1 result=READ_TIMEOUT
caller op=op-71 attempt=2 key_hash=*** instance=B
server-B op=op-71 idem=REPLAY reservation=reservation-101
caller op=op-71 result=COMPLETED reservation=reservation-101
~~~

Không ghi full token, header Authorization, payload nhạy cảm hoặc key thật vào log công khai. Với metrics, tránh đưa operation ID hoặc idempotency key vào tag vì cardinality không giới hạn; hãy ghi giá trị chi tiết có kiểm soát trong traces/logs.

Nếu clock giữa caller và server lệch nhau, không suy diễn thứ tự sự kiện chỉ bằng cách trừ timestamp từ hai máy. Dùng trace context, server transaction log và correlation ID để xây bằng chứng.

## 18. Retry budget: tránh khuếch đại tải khi hệ thống đã lỗi

Giả sử service nhận 200 business operations/giây, mỗi operation được thử tối đa **ba attempts**:

~~~text
Không retry:      200 HTTP attempts/giây
Khi hầu hết lỗi:  tối đa khoảng 600 HTTP attempts/giây
Hệ số tải:        tối đa khoảng 3 lần
~~~

Nếu gateway cũng retry ba lần mỗi HTTP attempt của caller, tổng số attempt phía dưới có thể tăng mạnh hơn, tùy điều kiện retry thực tế. Tải tăng đúng lúc dependency đang chậm có thể tạo vòng lặp timeout → retry → quá tải → timeout.

Một retry policy cần có:

- **Số attempts tổng** và số retries rõ nghĩa; nhiều API tính “maxRetries” không gồm attempt đầu.
- **Backoff có giới hạn**, thường kèm jitter để giảm đồng loạt.
- **Deadline tổng** theo SLO và thời gian còn lại trước lần thử tiếp.
- **Danh sách lỗi có thể phục hồi**; không retry lỗi validation, authentication hoặc payload conflict.
- **Idempotency precondition** cho bất kỳ thao tác có tác dụng phụ.
- **Circuit breaker, bulkhead/concurrency limit và load shedding** khi dependency quá tải.
- **Metric riêng** cho retry attempts, timeout và operation success/failure/unknown.

Nếu response `429`/`503` có `Retry-After`, xem xét nó cùng deadline của caller; không chờ vô hạn chỉ vì server gợi ý thời gian dài. Nếu operation đang UNKNOWN, ưu tiên query theo key/operation ID hoặc retry có tính idempotent thay vì gửi key mới.

## 19. Ma trận quyết định retry theo phương thức và kết quả

| Request/tình huống | Cách xử lý gợi ý | Điều kiện an toàn |
|---|---|---|
| GET bị lỗi mạng tạm thời | Có thể retry giới hạn | GET không gây side effect nghiệp vụ |
| GET trả 404 hợp lệ | Không retry máy móc | Contract khẳng định resource không có |
| PUT đặt trạng thái tuyệt đối | Cân nhắc retry | Implementation thật sự idempotent |
| PATCH cộng dồn số lượng | Không retry mù | Cần key/dedup hoặc operation token |
| POST tạo reservation, connect timeout | Retry cùng key nếu cần | Server hỗ trợ key/shared store |
| POST tạo reservation, read timeout | UNKNOWN; query status hoặc retry cùng key | Không đổi key; dedup atomic |
| POST trả 409 do key khác payload | Không retry y nguyên như lỗi tạm | Sửa payload/key usage theo contract |
| HTTP 429/503 | Retry có điều kiện | Deadline, backoff, Retry-After, không quá tải |
| Không có ServiceInstance | Phân biệt lỗi discovery/health | Không chắc thêm retries sẽ có instance |
| Server trả 500 sau side effect | UNKNOWN nếu contract không xác định | Query/replay cùng key, không tạo operation mới |
| Status API tạm lỗi | Giữ UNKNOWN, đối soát | Không được biến lỗi query thành FAILED |

Ma trận chỉ là khung đánh giá. Trong production, xác nhận semantics từng endpoint và ý nghĩa trạng thái nghiệp vụ, không áp dụng cứng chỉ theo HTTP method/status.

## 20. Bộ test cần có trước khi bật retry cho thao tác ghi

Một cơ chế idempotency đáng tin cậy phải được kiểm thử trong các **failure windows**:

| Tình huống | Bằng chứng cần thu |
|---|---|
| Hai POST cùng key/payload chạy đồng thời | Chỉ một domain side effect |
| POST cùng key nhưng payload khác | Conflict, không ghi lần hai |
| Server commit rồi mất response | Caller UNKNOWN, tra cứu thấy kết quả |
| Retry cùng key tới instance khác | Dùng chung result, không tạo reservation khác |
| Caller timeout khi server đang PENDING | Chỉ một processor được làm việc |
| Process crash sau claim key | Record được recovery, không kẹt vô hạn |
| Crash sau DB commit, trước khi gửi event | Outbox/event vẫn được phát đúng contract |
| Outbox phát event trùng | Consumer dedup/handle idempotent |
| Payment gateway đã xử lý nhưng local chưa nhận response | Đối soát cùng provider key |
| Key hết hạn trong thời gian retry hợp lệ | Hệ thống không tạo operation trùng ngoài contract |
| Chạy retry ở cả client và gateway | Tổng attempt không vượt ngân sách |
| Không còn ServiceInstance nào healthy | Caller phân loại failure trước HTTP |
| Trả 409/400/401/403 | Không retry như lỗi tạm thời |
| Thao tác đã COMPLETED nhưng status query lỗi | Không đổi key hoặc tạo operation mới |
| Restart service với shared DB | Key/result vẫn tồn tại |

Với lab in-memory ở phần 9, các test **trên một process** có thể chạy được ngay để chứng minh cơ chế chống trùng cục bộ. Các bài test **nhiều instance/restart** phải sử dụng triển khai shared storage; nếu chỉ chạy lại lab thì kết quả trùng là **điều được dự báo**, không phải bằng chứng triển khai production đã đúng.

## 21. Checklist triển khai và những hiểu lầm cần tránh

Trước khi bật retry trong module Spring Cloud LoadBalancer, hãy kiểm tra:

1. **Operation cần bảo vệ là gì?** Phân biệt request HTTP với ý định nghiệp vụ.
2. **Request có thực sự idempotent không?** Đừng chỉ dựa vào tên phương thức.
3. **Idempotency key được sinh ở đâu?** Nó phải ổn định qua các attempts của cùng operation.
4. **Key có gắn tenant/owner và operation scope không?** Tránh rò dữ liệu giữa các caller.
5. **Có đối chiếu payload/fingerprint không?** Cùng key khác command phải conflict.
6. **Có atomic claim và unique constraint không?** Tránh hai replica cùng xử lý.
7. **Key/result có ở shared durable store không?** LoadBalancer có thể chọn replica khác.
8. **Có PENDING/COMPLETED/FAILED rõ ràng không?** Không biến mọi timeout thành FAILED.
9. **Có status API hoặc operation ID để đối soát không?** Nhất là khi response đã bị mất.
10. **Retention có đủ dài không?** Key không được hết hạn giữa retry/reconciliation hợp lệ.
11. **Có side effect ngoài DB không?** Cân nhắc outbox, idempotent consumer và provider key.
12. **Retry được bật ở những tầng nào?** Tính tổng attempts, backoff và deadline.
13. **HTTP client có phân loại lỗi trước response và status có response không?**
14. **Health/discovery có thể đổi instance sau retry không?** Cần test hai replica.
15. **Logs/traces có operation ID, attempt và idempotency outcome không?**
16. **Có kịch bản concurrency, crash, timeout và replay để kiểm chứng không?**

Những nhận định phải tránh:

- “Client timeout nghĩa là server chưa chạy.”
- “Dùng POST thì không bao giờ được retry.”
- “Chỉ cần đặt header `Idempotency-Key` là xong.”
- “Dùng lock trong JVM đủ an toàn vì LoadBalancer chọn một instance.”
- “Có unique key nghĩa là mọi side effect toàn hệ thống exactly-once.”
- “Retry qua LoadBalancer chắc chắn đổi sang instance khác.”
- “Đã có response `500` nên DB chắc chắn rollback.”
- “Status query `404` chứng minh request đầu chưa được xử lý.”
- “Đặt TTL key bằng HTTP read timeout là đủ.”

## 22. Kết luận

**Tính lũy đẳng** là thuộc tính của **hành vi nghiệp vụ** khi thực hiện cùng một operation nhiều lần. **Idempotency key** là công cụ để server nhận diện các attempts cùng ý định; muốn hoạt động đúng cần kiểm tra payload, unique/atomic claim, lưu trạng thái và kết quả bền vững, chia sẻ giữa các instance và có quy trình xử lý side effect bên ngoài. **Unknown outcome** xuất hiện khi caller không có bằng chứng request đã hoặc chưa hoàn tất ở backend; cách xử lý đúng là giữ nguyên operation key, tra cứu/đối soát và retry có kiểm soát theo contract.

Trong **Spring Cloud LoadBalancer**, mỗi HTTP attempt qua RestClient, WebClient hoặc OpenFeign có thể đi qua discovery, health check, thuật toán chọn `ServiceInstance` và timeout riêng. Các thành phần đó hỗ trợ định tuyến và phục hồi giao tiếp, **không tự tạo bảo đảm chống thực thi lặp**. Trước khi tăng số retries để cải thiện availability, hãy bảo vệ tác dụng phụ bằng **idempotency bền vững**, đặt **deadline và backoff có ngân sách**, và quan sát rõ sự khác nhau giữa **số HTTP attempts** với **số business operations được hoàn tất**.

