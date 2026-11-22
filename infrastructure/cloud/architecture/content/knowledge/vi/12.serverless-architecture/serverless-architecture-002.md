# Thiết kế hàm không lưu trạng thái và quản lý phụ thuộc

Trong kiến trúc serverless, một hàm có thể được khởi chạy để xử lý HTTP request, thông điệp trong queue, sự kiện lưu tệp hoặc lịch định kỳ. Nền tảng có thể tạo nhiều execution environment, tái sử dụng một môi trường cho nhiều lần gọi, tạm dừng hoặc kết thúc nó khi không còn nhu cầu. Vì vậy, thiết kế hàm không nên giả định một tiến trình sẽ sống liên tục, một instance sẽ luôn nhận cùng người dùng hay bộ nhớ cục bộ là nơi lưu dữ liệu lâu dài.

Hai nguyên tắc nền tảng là **stateless execution** và **quản lý phụ thuộc có chủ đích**. Hàm không lưu trạng thái nghiệp vụ giữa các lần gọi; trạng thái cần thiết được đặt trong dịch vụ lưu trữ hoặc hệ thống quản lý phiên phù hợp. Các thư viện, client kết nối, cấu hình, secret và dịch vụ bên ngoài được khởi tạo, tái sử dụng và giới hạn theo vòng đời thực tế của runtime.

Điều đó không có nghĩa hàm không có biến, không được dùng bộ nhớ hoặc phải tạo mọi đối tượng ở mỗi request. Bộ nhớ trong execution environment vẫn hữu ích cho dữ liệu tạm, cache tối ưu và tái sử dụng kết nối khi runtime được giữ ấm. Nhưng dữ liệu này có thể biến mất, bị chia sẻ giữa các lần gọi trên cùng môi trường hoặc không xuất hiện ở môi trường khác. **Không dùng trạng thái cục bộ làm nguồn dữ liệu chuẩn hoặc cơ chế bảo đảm tính đúng đắn.**

Bài học thuộc phần **Kiến trúc serverless** trong học phần thiết kế kiến trúc đám mây. Mục tiêu là hiểu cách thiết kế ứng dụng từ yêu cầu nghiệp vụ đến compute, dữ liệu, mạng và vận hành, với các đánh đổi về độ tin cậy, bảo mật, khả năng mở rộng, chi phí và khả năng kiểm soát theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Giải thích stateless function và phân biệt trạng thái tạm trong runtime với trạng thái nghiệp vụ bền vững.
- Thiết kế hàm có thể chạy nhiều bản sao, nhận sự kiện lặp và phục hồi khi execution environment bị kết thúc.
- Quản lý dependency, SDK client, connection pool, cấu hình và secret theo vòng đời phù hợp.
- Kiểm soát timeout, retry, concurrency, idempotency và giới hạn của dịch vụ downstream.
- Thiết kế truy cập mạng, observability, kiểm thử và triển khai an toàn cho function.
- Đánh giá kiến trúc hàm serverless theo sáu trụ cột Well-Architected.

## 1. Stateless function nghĩa là gì?

Một hàm stateless không dựa vào trạng thái cục bộ của một lần chạy trước để xử lý đúng lần chạy hiện tại. Mỗi invocation nhận đầu vào cần thiết, xác thực và xử lý nghiệp vụ, tương tác với hệ thống lưu trạng thái bên ngoài, rồi trả kết quả hoặc phát sự kiện tiếp theo.

Ví dụ, hàm CreateBooking nhận customerId, slotId và một idempotency key. Hàm xác minh quyền, kiểm tra lịch còn trống, ghi booking vào database và trả mã booking. Trạng thái “khung giờ đã được đặt” được lưu trong database với transaction và constraint phù hợp. Nếu invocation kế tiếp chạy trên một execution environment hoàn toàn khác, kết quả vẫn đúng.

Ngược lại, nếu hàm chỉ lưu lịch đã đặt vào một biến toàn cục hoặc file tạm trên filesystem của execution environment, invocation khác có thể không nhìn thấy dữ liệu đó. Hai invocation chạy đồng thời cũng có thể cùng tin rằng một slot còn trống và ghi đè lẫn nhau.

### Phân biệt các loại trạng thái

| Loại trạng thái | Ví dụ | Nơi phù hợp |
| --- | --- | --- |
| Dữ liệu nghiệp vụ chuẩn | Booking, đơn hàng, quyền sở hữu, số dư | Database hoặc datastore bền vững có mô hình nhất quán phù hợp |
| Session hoặc trạng thái tương tác | Giỏ hàng tạm, bước xác minh, session web | Session store, database, cache có chính sách rõ |
| Trạng thái workflow dài hạn | Chờ phê duyệt, retry sau nhiều giờ, bước xử lý tiếp theo | Workflow orchestration/state machine hoặc datastore bền vững |
| Dữ liệu tạm trong invocation | Biến trung gian, kết quả tính toán, buffer request | Memory của invocation |
| Cache tối ưu trong execution environment | SDK metadata hoặc dữ liệu ít thay đổi | Có thể dùng để giảm chi phí, nhưng phải chấp nhận cache mất hoặc stale |
| File tạm | Nội dung giải nén hoặc tệp trung gian | Filesystem tạm nếu runtime hỗ trợ; không coi là nơi lưu lâu dài |

**Stateless không đồng nghĩa stateless business domain.** Ứng dụng vẫn lưu trạng thái nghiệp vụ; chỉ có execution unit được thiết kế để không sở hữu trạng thái cục bộ cần thiết cho tính đúng đắn.

## 2. Vòng đời execution environment và hệ quả thiết kế

Function runtime thường quản lý môi trường thực thi thay cho đội ứng dụng. Một environment có thể trải qua:

1. **Provisioning:** nền tảng chuẩn bị runtime, mã và cấu hình.
2. **Initialization/cold start:** runtime nạp module, khởi tạo thư viện, client, kết nối hoặc extension.
3. **Invocation:** hàm xử lý một event hoặc request.
4. **Reuse/warm start:** môi trường có thể được giữ lại và dùng cho invocation khác.
5. **Freeze/suspend hoặc termination:** nền tảng có thể ngừng tiến trình, đóng kết nối hay xóa môi trường theo chính sách riêng.

Không có bảo đảm chung rằng một môi trường sẽ tồn tại bao lâu, nhận bao nhiêu invocation hay luôn được tái sử dụng. Chi tiết phụ thuộc runtime và nhà cung cấp.

~~~mermaid
flowchart TD
    A["Event / HTTP request"] --> B{"Có execution environment sẵn sàng?"}
    B -- "Không" --> C["Provision + initialization<br/>Cold start"]
    B -- "Có" --> D["Tái sử dụng runtime<br/>Warm start"]
    C --> E["Invocation"]
    D --> E
    E --> F["Xử lý, gọi dependency,<br/>đọc/ghi state bên ngoài"]
    F --> G["Trả kết quả / ack / phát event"]
    G --> H{"Environment được giữ lại?"}
    H -- "Có thể" --> D
    H -- "Không / hết nhu cầu" --> I["Freeze hoặc terminate"]
~~~

### Những điều không nên giả định

- Invocation tiếp theo sẽ chạy trên đúng instance trước đó.
- Hai invocation của cùng function sẽ chạy tuần tự.
- Biến toàn cục hoặc file tạm được chia sẻ giữa mọi bản sao.
- Code khởi tạo chỉ chạy một lần trong toàn bộ vòng đời ứng dụng.
- Kết nối database sẽ luôn sống sau thời gian idle hoặc sau khi môi trường được resume.
- Nền tảng luôn kết thúc execution environment ngay khi handler trả kết quả.
- Có thể dùng local cache để bảo đảm tính duy nhất hoặc thứ tự xử lý.

Một hàm đúng phải hoạt động khi **được khởi động hoàn toàn mới**, khi **được tái sử dụng**, và khi **nhiều bản sao chạy đồng thời**.

## 3. Tách state ra dịch vụ phù hợp

Stateless function cần một hoặc nhiều dịch vụ bên ngoài để lưu trạng thái. Lựa chọn phụ thuộc vào access pattern, độ bền dữ liệu, yêu cầu nhất quán, latency, retention và chi phí.

| Nhu cầu | Dịch vụ có thể xem xét | Điều cần thiết kế |
| --- | --- | --- |
| Giao dịch nghiệp vụ, ràng buộc quan hệ | Managed relational database | Transaction, constraint, connection management, backup/restore |
| Key-value truy cập nhanh, scale theo khóa | Managed NoSQL database | Partition key, consistency, conditional write, hot key, TTL |
| Session hoặc cache có thể tái tạo | Managed cache/session store | TTL, invalidation, eviction, dữ liệu stale và bảo mật |
| Tệp, ảnh, object lớn | Object storage | Metadata, quyền truy cập, lifecycle, checksum, URL ký |
| Xử lý bất đồng bộ, hấp thụ burst | Queue/event broker | Retry, visibility/ack, dead-letter, idempotency, ordering |
| Quy trình nhiều bước, chờ lâu | Workflow orchestration/state machine | State transition, timeout, compensation, retry, audit |

Ví dụ luồng đặt lịch:

~~~mermaid
flowchart LR
    USER["Client"] --> API["API Gateway / HTTP endpoint"]
    API --> FN["CreateBooking function"]
    FN --> DB[("Booking database<br/>Nguồn dữ liệu chuẩn")]
    FN --> OUTBOX["Outbox / event record"]
    OUTBOX --> Q["Queue / event bus"]
    Q --> NOTIFY["SendNotification function"]
    NOTIFY --> EXT["Email/SMS provider"]
    FN --> OBS["Logs, metrics, traces"]
    NOTIFY --> OBS
~~~

Function chỉ điều phối xử lý trong một invocation. Database giữ booking, còn queue và event record giúp tách tác vụ thông báo. Hàm thông báo có thể chạy nhiều lần mà không làm thay đổi dữ liệu booking theo cách sai lệch.

### Quyết định consistency phải thuộc về datastore

Giả sử hai khách hàng cùng đặt một khung giờ. Việc đọc “slot đang trống” rồi ghi booking bằng hai bước riêng có race condition. Một biến toàn cục, mutex trong process hoặc local cache không giải quyết được vì hai invocation có thể chạy trên hai execution environment.

Hãy thực hiện kiểm tra và ghi bằng **transaction hoặc conditional write** ở hệ thống dữ liệu có thể bảo đảm quy tắc nghiệp vụ. Ví dụ:

~~~sql
CREATE TABLE booking (
    booking_id UUID PRIMARY KEY,
    doctor_id UUID NOT NULL,
    slot_start TIMESTAMPTZ NOT NULL,
    customer_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doctor_id, slot_start)
);
~~~

Đây là ví dụ cho khung giờ cố định. Nếu lịch hẹn có thời gian bắt đầu/kết thúc thay đổi và được phép có nhiều quy tắc chồng lấn, constraint đơn giản trên không đủ; cần mô hình dữ liệu và ràng buộc phù hợp với nghiệp vụ.

## 4. Quản lý dependency theo vòng đời

Function thường cần SDK client, database driver, HTTP client, secret provider, logger, metrics exporter hoặc thư viện xử lý dữ liệu. Việc khởi tạo chúng ảnh hưởng cold start, latency, memory và độ ổn định kết nối.

Một nguyên tắc hữu ích:

- **Dependency dùng chung, an toàn để tái sử dụng:** khởi tạo ở phạm vi module/runtime khi việc khởi tạo không phụ thuộc dữ liệu riêng của invocation.
- **Dữ liệu riêng invocation:** tạo trong handler và không để rò rỉ sang lần chạy khác.
- **Kết nối có tuổi thọ giới hạn:** sử dụng pool/client có timeout, keepalive và cơ chế phục hồi khi kết nối bị đóng.
- **Dependency nặng:** đo cold start và memory; cân nhắc lazy initialization khi chỉ một số nhánh cần dùng.
- **Dependency có rủi ro bảo mật:** không giữ credential trong source code hoặc object có vòng đời kéo dài hơn chính sách cho phép.

### Ví dụ Java: khởi tạo client dùng lại

Ví dụ sau minh họa cách tạo client HTTP ở phạm vi class thay vì tạo mới cho mọi request. Việc dùng lại có thể giảm overhead kết nối, nhưng vẫn phải xử lý timeout và response body đúng cách:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class PartnerClient {
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    public String fetchStatus(URI endpoint) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        HttpResponse<String> response = CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IllegalStateException(
                    "Partner returned HTTP " + response.statusCode());
        }
        return response.body();
    }
}
~~~

HttpClient ở ví dụ là dependency dùng chung và được thiết kế để tái sử dụng. Trong triển khai thật, cần phân biệt lỗi kết nối, timeout, status retryable và response không hợp lệ; không log token hoặc payload nhạy cảm. Nếu endpoint được cấu hình động theo tenant, không đặt dữ liệu nhạy cảm của tenant vào biến static dùng chung.

### Không chia sẻ dữ liệu mutable giữa invocation

Một biến static chứa client thread-safe có thể phù hợp; một biến static chứa currentCustomer, danh sách booking hoặc request context lại nguy hiểm. Nếu runtime xử lý invocation đồng thời trong một process, dữ liệu mutable có thể bị ghi đè hoặc rò rỉ giữa người dùng.

Nguyên tắc là:

- Đối tượng dùng chung nên bất biến hoặc thread-safe.
- Không giữ request, token, customer ID hoặc dữ liệu cá nhân trong singleton dùng chung.
- Đưa context qua tham số hàm hoặc context object riêng invocation.
- Không coi việc runtime hiện tại xử lý tuần tự là cam kết lâu dài.

## 5. Kết nối database trong môi trường function

Một lỗi phổ biến là mỗi invocation mở một kết nối database mới và không kiểm soát tổng số kết nối. Khi function scale ngang, số kết nối có thể tăng đột biến dù mỗi invocation chỉ mở một connection.

### Ước lượng connection

Giả sử nền tảng có thể chạy tối đa 80 execution environment đồng thời. Mỗi environment có pool tối đa 4 kết nối:

~~~text
Số connection lý thuyết tối đa = 80 × 4 = 320
~~~

Chưa tính connection của worker khác, tác vụ quản trị, migration, monitoring và replica. Nếu database chỉ còn 250 connection dành cho ứng dụng, cấu hình này có thể làm cạn tài nguyên. Nếu pool lazy-create, số sử dụng thực có thể thấp hơn, nhưng phải đo khi tải đỉnh.

### Các chiến lược thường dùng

1. **Giới hạn concurrency của function:** ngăn số invocation đồng thời vượt năng lực downstream.
2. **Giảm pool mỗi execution environment:** không tạo nhiều connection nhàn rỗi; chọn pool size theo concurrency và thời gian query.
3. **Dùng connection proxy/pooling service:** nếu nền tảng hỗ trợ và semantics phù hợp, gom kết nối từ nhiều execution environment.
4. **Dùng API/data access layer riêng:** bảo vệ database và tập trung logic truy cập trong một dịch vụ có kiểm soát.
5. **Dùng datastore khác với mô hình truy cập phù hợp:** API key-value không nhất thiết cần một connection quan hệ lâu dài.

Connection proxy có thể giảm số kết nối backend, nhưng thêm một lớp mạng, quota, chi phí và giới hạn transaction/session. Một số kiểu transaction hoặc session-level setting có thể không tương thích với pooling mode cụ thể. Cần kiểm tra theo engine và proxy thực tế.

### Quản lý kết nối stale

Execution environment có thể bị tạm dừng hoặc kết nối đi qua NAT/firewall/database bị idle timeout. Khi tái sử dụng, client có thể giữ một socket đã bị đóng ở phía server. Hãy cấu hình:

- Connection validation hoặc kiểm tra kết nối khi borrow, theo driver/pool.
- Idle timeout ngắn hơn timeout ở các lớp trung gian khi phù hợp.
- Connect/read/query timeout.
- Retry có giới hạn cho lỗi kết nối có thể phục hồi.
- Đóng tài nguyên đúng cách khi invocation kết thúc nếu client/pool thuộc invocation.

Không retry vô hạn hoặc tự động lặp transaction ghi mà không biết giao dịch trước đã commit hay chưa. Dùng idempotency key hoặc cơ chế xác minh kết quả trước khi thử lại.

## 6. Dependency ngoài: timeout, retry và circuit breaker

Function thường gọi API của email, thanh toán, bản đồ, xác thực hoặc một dịch vụ nội bộ khác. Khi dependency chậm, function có thể giữ concurrency lâu hơn, tăng chi phí và làm cạn quota.

### Timeout theo ngân sách thời gian

Nếu function có timeout tối đa 10 giây, không nên để một HTTP call downstream chờ 10 giây rồi mới trả về, vì còn thời gian parse, validate, ghi dữ liệu và phản hồi. Hãy chia ngân sách:

~~~text
T_function
  >= T_validate
   + T_database
   + T_dependency
   + T_persist_result
   + T_response_margin
~~~

Đây là cách phân bổ tư duy, không phải cam kết runtime chính xác. Mỗi lời gọi cần timeout nhỏ hơn thời gian còn lại của invocation; các lời gọi song song cần tính theo đường thực thi và thời gian hoàn tất dài nhất.

### Retry có điều kiện

Retry phù hợp khi lỗi có thể phục hồi và thao tác có tính idempotent hoặc đã có cơ chế chống lặp. Ví dụ 429 hoặc 503 có thể thử lại sau Retry-After hoặc backoff; lỗi validate 400 thường không nên retry.

Khuyến nghị:

- Dùng exponential backoff với jitter.
- Đặt số lần retry và deadline tổng thể.
- Phân loại lỗi retryable và permanent.
- Không retry đồng thời ở quá nhiều tầng.
- Kiểm tra giới hạn retry, visibility timeout và redrive của queue.
- Chuyển thông điệp lỗi kéo dài sang dead-letter queue để điều tra.

### Circuit breaker và load shedding

Khi downstream liên tục lỗi, circuit breaker có thể tạm ngăn các request mới gọi dependency, cho phép hệ thống phục hồi và tránh làm cạn concurrency. Đối với serverless, trạng thái breaker trong memory của một execution environment không phải trạng thái toàn cục. Nếu cần phối hợp giữa nhiều instance, phải dùng cơ chế được chia sẻ hoặc dựa vào gateway/service mesh/platform policy phù hợp.

Không biến circuit breaker thành nguồn trạng thái khó đồng bộ. Cấu hình có thể đặt tại tầng gateway hoặc dependency client nếu semantics và phạm vi áp dụng rõ ràng.

## 7. Idempotency và xử lý sự kiện lặp

Nền tảng event-driven thường có thể giao lại sự kiện khi timeout, lỗi xử lý hoặc không nhận được acknowledgement. Một invocation cũng có thể ghi database thành công rồi mất kết nối trước khi trả kết quả. Client hoặc queue sẽ thử lại, dẫn tới cùng một sự kiện được xử lý nhiều lần.

**Idempotency** nghĩa là xử lý cùng một yêu cầu/sự kiện nhiều lần không tạo thêm tác dụng phụ ngoài kết quả dự kiến.

### Mẫu idempotency bằng khóa

Với API tạo booking:

1. Client tạo idempotency key duy nhất cho ý định đặt lịch.
2. Function nhận key và kiểm tra bản ghi idempotency.
3. Nếu đã xử lý, trả lại kết quả đã lưu.
4. Nếu chưa, thực hiện transaction ghi booking và kết quả idempotency cùng nhau.
5. Nếu request đến đồng thời, unique constraint hoặc conditional write quyết định chỉ một giao dịch được tạo.

Ví dụ bảng:

~~~sql
CREATE TABLE idempotency_record (
    idempotency_key VARCHAR(128) PRIMARY KEY,
    request_hash VARCHAR(128) NOT NULL,
    response_json JSONB,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Đây chỉ là mô hình khái niệm. Thiết kế thật cần định nghĩa transaction, trạng thái đang xử lý, timeout, request hash, retention, xử lý key dùng lại với payload khác và cách phục hồi khi invocation chết giữa chừng.

### Không đồng nhất idempotency với exactly-once

Một queue có thể giao thông điệp ít nhất một lần (at-least-once); consumer cần chịu duplicate. Một số dịch vụ có tính năng deduplication hoặc ordering trong phạm vi giới hạn, nhưng không tự bảo đảm toàn bộ side effect bên ngoài chỉ xảy ra một lần.

Gửi email cho khách hàng là ví dụ: function gọi nhà cung cấp thành công rồi bị timeout trước khi ghi nhận kết quả. Khi retry, email có thể gửi lần nữa. Cần idempotency ở provider nếu hỗ trợ, lưu operation ID, hoặc thiết kế quy tắc nghiệp vụ chấp nhận/gộp thông báo trùng.

## 8. Cấu hình và secrets

Function cần cấu hình môi trường, endpoint, feature flag, thông tin kết nối và credentials. Phải phân biệt **configuration không nhạy cảm** với **secret**.

| Dữ liệu | Nơi quản lý phù hợp | Lưu ý |
| --- | --- | --- |
| Feature flag, tên queue, timeout | Environment/config service | Kiểm soát version và thay đổi |
| Database password/API token | Secret manager | Phân quyền theo function, rotation, audit |
| Khóa mã hóa | KMS hoặc hệ thống quản lý khóa tương ứng | Không đưa plaintext key vào source/config log |
| Certificate | Certificate/secret management | Gia hạn, rotation và quyền đọc |
| Tenant-specific credentials | Secret store theo danh tính/tenant hoặc token exchange | Không giữ trong cache dùng chung không kiểm soát |

### Least privilege

Mỗi function nên có execution role/service identity riêng hoặc nhóm quyền theo chức năng. CreateBooking chỉ cần quyền ghi booking và phát event; SendNotification cần quyền đọc thông điệp và gọi dịch vụ gửi, không cần quyền sửa toàn bộ database.

Không nhúng access key dài hạn vào code, image hay environment variable được quản lý thủ công. Environment variable có thể dùng để truyền tham chiếu secret hoặc cấu hình, nhưng secret cần được cấp qua cơ chế bảo vệ và quyền tối thiểu. Cần xác định:

- Ai được lấy secret và trong thời gian nào?
- Rotation có làm hỏng execution environment đang giữ kết nối cũ không?
- Secret bị lộ thì revoke và điều tra thế nào?
- Có log hoặc trace vô tình in token/payload không?
- Secret store có quota/latency ảnh hưởng cold start không?

### Cache secret có điều kiện

Đọc secret ở mỗi invocation có thể tăng latency và chi phí. Có thể cache secret trong execution environment với TTL ngắn nếu chính sách cho phép. Tuy nhiên, rotation sẽ không có hiệu lực với môi trường đang giữ bản cũ cho tới khi cache hết hạn hoặc được làm mới. Hãy ghi rõ thời gian hiệu lực tối đa và quy trình revoke.

## 9. Dependency management trong build và deploy

Ngoài dịch vụ runtime, dependency còn gồm thư viện mã nguồn, runtime version, native library, extension và artifact được đóng gói.

- Pin version hoặc dùng lock/dependency constraints để build có thể tái tạo.
- Dùng dependency tối thiểu để giảm kích thước package và cold start.
- Kiểm tra CVE, license và nguồn artifact.
- Build theo runtime/architecture tương thích với function target.
- Tách dependency chỉ dùng trong build khỏi dependency cần ở runtime khi công cụ hỗ trợ.
- Kiểm tra package shading, native library, classpath và giới hạn kích thước deployment.

Với Java, cần kiểm tra phiên bản JDK, API tương thích, framework startup, reflection/AOT nếu áp dụng, timezone/locale và memory profile. Một artifact chạy trên máy dev chưa chắc chạy trong runtime serverless với filesystem, CPU architecture hoặc quyền khác.

Mỗi release nên gắn mã version hoặc digest, không tải dependency tùy ý trong lúc xử lý request. Build pipeline cần scan, test, ký hoặc xác minh artifact theo chính sách tổ chức. Khi rollback, đội ngũ phải biết artifact và cấu hình nào đã được triển khai.

### Dependency graph và cold start

Thư viện lớn, static initialization nặng, class scanning và kết nối đồng bộ lúc startup có thể tăng cold start. Chỉ khởi tạo những gì invocation cần. Lazy initialization có thể giảm startup cho nhánh ít dùng, nhưng đổi lại invocation đầu tiên vào nhánh đó có thêm latency.

Đo cold start riêng với warm invocation; không lấy trung bình chung để che p99.

## 10. Concurrency, memory và giới hạn function

Serverless có thể tự tạo thêm execution environment khi tải tăng. Điều này tiện cho scale nhưng có thể khuếch đại tải đến database hoặc API ngoài.

Các giới hạn cần xác định:

- **Max concurrency:** số invocation đồng thời toàn function hoặc theo event source.
- **Reserved/provisioned concurrency:** capacity được dành trước hoặc giữ warm theo semantics nhà cung cấp.
- **Memory/CPU:** cấu hình memory thường ảnh hưởng cả CPU/network performance hoặc giá theo dịch vụ.
- **Timeout:** thời gian tối đa một invocation.
- **Payload/event size:** giới hạn kích thước request/message.
- **Retries and age:** số lần thử lại hoặc tuổi event tối đa.
- **Account/region quota:** tổng concurrency và số resource của account.

Ví dụ, nếu function có thể mở tối đa 100 invocation đồng thời và mỗi invocation mở 3 database connections, tải tiềm năng là 300 kết nối. Việc đặt concurrency limit cần phối hợp với connection pool, quota và năng lực database.

### Tránh scale storm

Một sự kiện bất thường có thể tạo lượng invocation lớn. Khi downstream lỗi, queue retry hoặc event redelivery có thể tạo thêm tải. Thiết kế cần:

1. Giới hạn concurrency ở mức downstream có thể phục vụ.
2. Đặt queue buffer và quy định tốc độ consumer.
3. Dùng retry/backoff với jitter, không lặp vô hạn.
4. Theo dõi backlog và age, không chỉ số invocation.
5. Có phương án xử lý DLQ và replay an toàn.
6. Đặt budget/quota và cảnh báo tăng chi phí.

## 11. Network và kết nối đến dependency

Function thường cần truy cập database private, object storage, queue hoặc API bên ngoài. Cách kết nối ảnh hưởng security, latency, chi phí và khả năng mở rộng.

Nếu function đặt trong VPC/VNet hoặc mạng riêng, cần xác định:

- Subnet và IP address đủ cho concurrency, ENI hoặc network interface theo cách nền tảng cấp phát.
- Route đến database/private endpoint.
- Đường egress đến Internet/API bên ngoài qua NAT hoặc network gateway khi cần.
- DNS resolver và private DNS zone.
- Security group/firewall chỉ mở port và destination cần thiết.
- Phí NAT, private endpoint và data transfer.

Không phải function nào cũng cần gắn vào private network. Nếu chỉ gọi dịch vụ managed qua endpoint được bảo vệ bằng identity/service policy, việc đưa function vào VPC có thể thêm độ phức tạp và chi phí. Ngược lại, dữ liệu private cần network path và policy rõ ràng.

Khi concurrency tăng, số socket, ephemeral port, NAT connection tracking và IP cần dùng có thể tăng. Đừng chỉ tính request/giây. Thử burst concurrency, số destination, thời gian sống socket và số connection pool.

Client có thể cache DNS hoặc giữ connection lâu. Khi endpoint đổi, kết nối cũ vẫn có thể lỗi. Cần timeout hợp lý, connection refresh, retry có kiểm soát và endpoint discovery phù hợp.

## 12. Observability cho function stateless

Execution environment có thể ngắn hạn và nhiều bản sao, nên log và metric cần tập trung. Không thể đăng nhập vào một instance cố định rồi xem trạng thái của toàn workload.

Mỗi invocation nên ghi các trường phù hợp:

- Function name/version, environment, invocation/request ID.
- Event/correlation ID và trace ID.
- Operation name, dependency name, trạng thái kết quả.
- Duration, timeout, retry count và loại lỗi.
- Tenant/customer identifier đã giả danh hoặc làm sạch nếu có yêu cầu.

Không log access token, secret, dữ liệu thanh toán hay toàn bộ payload nhạy cảm. Thực hiện redaction ở nguồn trước khi gửi đến hệ thống log trung tâm.

| Nhóm | Metric |
| --- | --- |
| Invocation | invocation count, success/error, throttles, duration p50/p95/p99 |
| Runtime | cold start, init duration, memory used, timeout, OOM |
| Concurrency | concurrent executions, reserved/provisioned utilization |
| Dependency | connect/query/API latency, timeout, error, retry |
| Event processing | queue depth, oldest message age, DLQ count, delivery failures |
| Business | booking created, duplicate prevented, notification delivered |
| Cost | invocation, duration, memory allocation, network, logs và downstream |

Một function có tỷ lệ success 99,99% nhưng thông báo nằm trong queue nhiều giờ vẫn có thể không đáp ứng nghiệp vụ. Kết hợp telemetry kỹ thuật với metric nghiệp vụ và SLO đầu-cuối.

## 13. Kiểm thử và triển khai

Các lớp kiểm thử cần cân nhắc:

1. **Unit test:** logic thuần, validate, mapping và xử lý lỗi.
2. **Contract test:** schema event, HTTP contract, database access và API đối tác.
3. **Integration test:** chạy với datastore/queue thật hoặc emulator phù hợp, kiểm tra auth và network.
4. **Concurrency test:** nhiều invocation tạo cùng tài nguyên, gửi event lặp hoặc cập nhật đồng thời.
5. **Failure test:** dependency chậm, timeout, connection reset, DLQ, secret rotation, database failover.
6. **Performance test:** cold start, warm duration, p95/p99, concurrency và downstream saturation.
7. **Security test:** IAM least privilege, payload validation, secret exposure, SSRF và truy cập mạng.

### Kiểm thử cả cold và warm

Một bài benchmark chỉ chạy invocation liên tục trên cùng một môi trường có thể không phản ánh cold start hoặc scale-out. Cần thử:

- Invocation đầu tiên sau deploy hoặc khi không có environment warm.
- Tải tăng đột biến khiến nền tảng tạo nhiều môi trường mới.
- Invocation dài và các dependency bị chậm.
- Retry/redelivery sau khi function chết ở các điểm khác nhau của workflow.
- Memory gần giới hạn và xử lý payload lớn.

### Triển khai an toàn

Function có thể triển khai qua version/alias, traffic shifting, canary hoặc cơ chế tương ứng của nền tảng. Quy trình nên:

- Build artifact bất biến và kiểm tra bảo mật.
- Triển khai version mới mà chưa chuyển toàn bộ traffic.
- Quan sát error rate, duration, throttling, business metrics.
- Tăng traffic từng bước nếu đạt ngưỡng.
- Rollback alias/version nếu lỗi vượt mức.
- Quản lý schema database tương thích với phiên bản cũ và mới trong thời gian chuyển tiếp.

Rollback code không tự rollback dữ liệu đã ghi. Migration cần chiến lược tương thích ngược hoặc bước khôi phục riêng.

## 14. Những sai lầm thường gặp

**Lưu trạng thái nghiệp vụ trong biến global.** Một execution environment khác không nhìn thấy; dữ liệu có thể mất khi bị terminate.

**Cho rằng một function chạy tuần tự.** Concurrency có thể tạo nhiều invocation song song; cần transaction, conditional write và idempotency.

**Mở database connection mới ở mọi invocation mà không giới hạn.** Scale-out tạo nhiều connection, có thể làm database quá tải.

**Giữ connection vô hạn trong environment.** Runtime có thể bị freeze; NAT, firewall hoặc database có thể đóng socket idle.

**Retry mọi lỗi.** Lỗi validate không thể tự khỏi; retry thao tác ghi có thể tạo duplicate hoặc khuếch đại quá tải.

**Đặt toàn bộ workflow dài trong một function.** Timeout và memory giới hạn có thể không phù hợp; dùng queue/workflow orchestration cho tác vụ dài, chờ hoặc nhiều bước.

**Coi cache cục bộ là dữ liệu chuẩn.** Cache có thể stale, mất hoặc khác nhau giữa môi trường; chỉ dùng cho tối ưu với cơ chế invalidation.

**Để secret trong source code hoặc log.** Secret có thể bị lộ qua artifact, trace hoặc debugging; dùng secret manager và redaction.

**Không tính quota và cost khi scale.** Tăng concurrency có thể kéo theo database, NAT, logging và API provider cost.

**Chỉ thử warm invocation.** Bỏ qua cold start, scale-out, runtime initialization và hành vi sau freeze/thaw.

## 15. Bài thực hành: thiết kế hàm đặt lịch stateless

**Bối cảnh giả định:** Một ứng dụng đặt lịch chạy trên nền tảng function. API nhận yêu cầu đặt lịch, lưu dữ liệu vào database và gửi sự kiện thông báo vào queue. Function gửi email/SMS chạy riêng. Hệ thống có thể nhận 200 request/giây vào giờ cao điểm; cùng một event có thể được giao lại; database chỉ dành 120 connection cho ứng dụng. SLO giao dịch đặt lịch hợp lệ là 99,9% trong 30 ngày, p95 API dưới 400 ms. Đây là số liệu luyện tập, cần được xác nhận và đo trong dự án thực tế.

### Nhiệm vụ

1. **Thiết kế ranh giới state:** xác định dữ liệu nào ở memory invocation, cache, database, queue và workflow store. Nêu nguồn dữ liệu chuẩn cho booking.
2. **Thiết kế dependency:** quyết định client nào khởi tạo ở module/runtime, client nào theo invocation; xác định thread safety, connection lifetime và secret access.
3. **Tính connection:** với concurrency tối đa 60 và pool tối đa 2 connection/environment, tính tổng kết nối tiềm năng. Đối chiếu với ngân sách 120 connection và dành chỗ cho worker/monitoring.
4. **Thiết kế idempotency:** xử lý hai event cùng key, cùng key nhưng payload khác và trường hợp ghi database thành công nhưng invocation timeout trước khi phản hồi.
5. **Thiết kế timeout/retry:** đặt ngân sách thời gian cho database, queue và email provider; xác định lỗi retryable, backoff, DLQ và concurrency cap.
6. **Thiết kế bảo mật:** execution role riêng, secret manager, network access và redaction log. Nêu quyền mà function không cần.
7. **Thiết kế quan sát:** chọn metric kỹ thuật và nghiệp vụ để phát hiện cold start, throttling, duplicate, backlog và lỗi downstream.
8. **Lập kế hoạch test:** unit, integration, concurrency, cold/warm, scale-out và failure test.

### Gợi ý hướng giải

Booking được lưu trong database bằng transaction/constraint, không lưu trong static map của function. Invocation nhận idempotency key và ghi kết quả chống lặp cùng transaction. Queue/event được phát qua transactional outbox hoặc cơ chế bảo đảm tương đương để tránh trường hợp booking đã commit nhưng event bị mất.

Client HTTP và SDK thread-safe có thể khởi tạo ngoài handler và tái sử dụng; request context, tenant data và transaction object là dữ liệu riêng invocation. Database pool được giới hạn; với 60 environment × 2 connection, mức tối đa lý thuyết là 120, chưa có headroom cho worker và tác vụ khác. Vì vậy nhóm cần giảm pool, giới hạn concurrency hoặc sử dụng proxy/tầng truy cập phù hợp sau khi đo.

Function thông báo idempotent theo notification ID. Nếu provider hỗ trợ idempotency, truyền operation key; nếu không, lưu trạng thái gửi và chấp nhận/kiểm soát khả năng gửi lặp. Queue có retry giới hạn, visibility timeout phù hợp và DLQ để xử lý poison message.

Đây là hướng giải, không phải cấu hình production hoàn chỉnh. Phải kiểm tra semantics của dịch vụ function, database, queue, connection proxy và email provider thực tế.

### Tiêu chí nghiệm thu

| Mục tiêu | Bằng chứng |
| --- | --- |
| Không đặt trùng lịch | Concurrent test chứng minh chỉ một booking cho slot duy nhất |
| Không phụ thuộc environment cũ | Khởi chạy environment mới vẫn đọc và xử lý đúng booking |
| Chịu event lặp | Gửi lại cùng event không tạo side effect nghiệp vụ ngoài ý muốn |
| Bảo vệ database | Connection count không vượt ngân sách khi concurrency đạt trần |
| Phục hồi khi dependency lỗi | Retry hữu hạn, DLQ có cảnh báo, replay an toàn |
| Bảo vệ secret | Không có credential trong code/log; quyền function được giới hạn |
| Đạt SLO | Load test và telemetry cho thấy p95/error rate đáp ứng mục tiêu trong tải thử |

## 16. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho stateless function và dependency |
| --- | --- |
| **Operational Excellence** | Build có tái tạo được, version có rollback, dependency và runtime có inventory, log có correlation ID không? |
| **Security** | Function có execution identity riêng, least privilege, secret rotation, input validation và network boundary đúng không? |
| **Reliability** | Event duplicate, timeout, retry, DLQ, downstream failure và environment termination đã được xử lý chưa? |
| **Performance Efficiency** | Cold start, dependency initialization, connection pool, memory, concurrency và p95/p99 có được đo không? |
| **Cost Optimization** | Concurrency có giới hạn, retry storm có được ngăn, log retention và network egress có được theo dõi không? |
| **Sustainability** | Function có tránh polling/lặp không cần thiết, dependency thừa và tài nguyên chạy nền không cần thiết không? |

Một thiết kế tốt cần chứng minh **đúng đắn không phụ thuộc execution environment**, concurrency không làm hỏng dữ liệu hoặc downstream, và nhóm có đủ tín hiệu để biết function đang hoạt động thế nào. Stateless giúp mở rộng và thay thế execution environment dễ hơn; quản lý dependency đúng giúp lợi ích đó không bị mất bởi cold start, kết nối cạn, secret lỗi thời hoặc retry không kiểm soát.

## 17. Checklist trước khi đưa function vào production

- [ ] Dữ liệu nghiệp vụ và session cần thiết nằm trong datastore/workflow phù hợp, không chỉ ở memory cục bộ.
- [ ] Handler đúng khi chạy trên environment mới, environment warm và nhiều invocation đồng thời.
- [ ] Biến dùng chung chỉ chứa dependency bất biến/thread-safe; không chứa request context hoặc dữ liệu tenant mutable.
- [ ] SDK/client initialization và lazy loading được đo về cold start, memory và latency.
- [ ] Connection pool, idle timeout, validation, retry và max concurrency phù hợp với quota downstream.
- [ ] Timeout tổng và timeout từng dependency được phân bổ rõ; không retry vô hạn.
- [ ] Thao tác ghi có idempotency key hoặc cơ chế chống lặp tương đương.
- [ ] Queue có retry policy, visibility/ack phù hợp, DLQ, cảnh báo và quy trình replay.
- [ ] Secrets nằm trong hệ thống quản lý phù hợp, được cấp theo least privilege và có rotation.
- [ ] Build artifact pin version, kiểm tra vulnerability, runtime và kiến trúc tương thích.
- [ ] Network route, subnet, DNS, egress, NAT/IP và endpoint private đã được kiểm tra theo concurrency.
- [ ] Logs/metrics/traces có correlation, redaction và chỉ số nghiệp vụ.
- [ ] Có cold/warm, concurrency, failure, load, security và rollback tests.
- [ ] Quota, cost, retry storm và điều kiện scale-out có giới hạn, cảnh báo và owner.
- [ ] Quyết định kiến trúc, ngoại lệ và điều kiện review được ghi lại.

Thiết kế hàm không lưu trạng thái không chỉ là bỏ biến toàn cục. Đó là cách đặt **nguồn dữ liệu chuẩn ở nơi bền vững**, làm cho mỗi invocation có thể chạy độc lập, quản lý dependency theo vòng đời, bảo vệ downstream trước concurrency và xử lý lỗi lặp một cách an toàn. Khi các ranh giới này rõ ràng và được thử nghiệm, serverless mới có thể mở rộng linh hoạt mà vẫn giữ được tính đúng đắn, bảo mật, hiệu năng và chi phí có thể kiểm soát.
