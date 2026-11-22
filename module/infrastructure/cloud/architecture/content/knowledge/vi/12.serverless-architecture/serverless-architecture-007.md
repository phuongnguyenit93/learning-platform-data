# Quản lý kết nối cơ sở dữ liệu trong tải serverless

## 1. Vì sao kết nối database trở thành nút thắt trong serverless?

Serverless cho phép nền tảng tự động khởi tạo và mở rộng execution environment khi có yêu cầu, thay vì đội phát triển phải duy trì nhóm máy chủ ứng dụng luôn chạy. Mô hình này phù hợp với API có lưu lượng không đều, tác vụ theo sự kiện và workload tăng giảm nhanh. Tuy nhiên, **database thường không mở rộng kết nối đồng thời nhanh và rẻ như lớp compute serverless**.

Trong ứng dụng truyền thống, một số lượng instance tương đối ổn định thường giữ pool kết nối trong suốt vòng đời tiến trình. Với function serverless, nhiều execution environment có thể được tạo gần như đồng thời trong một đợt tải. Mỗi environment có thể tạo pool riêng; các lần scale-out, cold start, retry hoặc chạy song song làm số connection tăng đột biến. Khi function scale-in hoặc timeout, việc trả connection về pool hay đóng socket cũng có thể khác kỳ vọng.

Hậu quả thường gặp gồm:

- Database hết giới hạn connection dù CPU và RAM chưa bão hòa.
- Connection bị mở quá sớm, giữ quá lâu hoặc không được đóng đúng cách.
- Function chờ lấy connection, làm tăng latency và timeout dây chuyền.
- Retry sau lỗi database tạo thêm invocation và tiếp tục tăng connection.
- Giao dịch bị giữ mở trong lúc function gọi API bên ngoài hoặc chờ xử lý lâu.
- Proxy/pooler bị quá tải, tạo thành nút thắt mới thay cho database.

Trong module **CLOUD_ARCHITECTURE**, đây là quyết định thiết kế quan trọng giữa compute, dữ liệu, độ tin cậy, hiệu năng, bảo mật, chi phí và vận hành. Bài học tập trung vào cách quản lý vòng đời kết nối khi concurrency serverless thay đổi nhanh, tính giới hạn an toàn, sử dụng pool hoặc database proxy, và kiểm chứng hành vi dưới tải thực tế.

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa invocation concurrency, execution environment, connection pool và giới hạn connection.
- Ước lượng connection khi scale-out và chọn concurrency an toàn.
- Phân biệt pool trong tiến trình, proxy/pooler, kết nối trực tiếp và database API.
- Thiết kế transaction ngắn, retry có backoff, idempotency và timeout nhất quán.
- Quản lý credential, TLS, quyền truy cập và rotation cho function.
- Xây dựng load test, chỉ số quan sát và phương án xử lý khi database hoặc proxy quá tải.

## 2. Mô hình kết nối trong ứng dụng serverless

~~~mermaid
flowchart LR
    Client["Client / Event source"] --> GW["API Gateway / Trigger"]
    GW --> Fn["Function invocation"]
    subgraph Runtime["Execution environments có thể tăng giảm"]
        Fn --> E1["Environment A"]
        Fn --> E2["Environment B"]
        E1 --> P1["Local connection pool"]
        E2 --> P2["Local connection pool"]
    end
    P1 --> Proxy["DB Proxy / Pooler (tùy chọn)"]
    P2 --> Proxy
    Proxy --> DB[("Database")]
~~~

Không phải mọi nền tảng đều dùng đúng sơ đồ này. Function có thể xử lý một invocation mỗi environment, hoặc concurrency cao hơn với runtime riêng; environment có thể được tái sử dụng. Dịch vụ database API-based có thể không mở socket database truyền thống ở phía function. Cần **đọc rõ mô hình concurrency của runtime và semantics kết nối của dịch vụ đang chọn**.

| Khái niệm | Ý nghĩa | Liên hệ với kết nối |
| --- | --- | --- |
| **Invocation** | Một lần thực thi function để xử lý sự kiện/request | Có thể cần 0, 1 hoặc nhiều thao tác DB |
| **Execution environment** | Môi trường chạy được nền tảng tạo và có thể tái sử dụng | Có thể giữ client/pool giữa các invocation |
| **Concurrency** | Số invocation đang xử lý đồng thời theo định nghĩa nền tảng | Quyết định số environment và áp lực lên DB |
| **Connection** | Socket/session được client mở tới DB hoặc proxy | Tiêu thụ giới hạn, memory và tài nguyên DB/proxy |
| **Connection pool** | Tập connection được quản lý để tái sử dụng | Pool riêng ở mỗi environment có thể nhân lên |
| **Proxy / pooler** | Lớp nhận kết nối client và quản lý/ghép nối tới DB backend | Có thể giảm backend connection nhưng tạo thêm hop và giới hạn |
| **Transaction** | Một đơn vị thao tác dữ liệu có commit/rollback | Chiếm connection và có thể giữ lock khi transaction mở |

**Concurrency không đồng nghĩa với số connection.** Một invocation có thể mở 0, 1 hoặc nhiều connection; một environment giữ pool nhiều connection; proxy có thể multiplex nhiều client session lên ít backend connection tùy chế độ và database.

### 2.1. Vì sao cách làm ở server truyền thống có thể thất bại?

Một ứng dụng chạy trên 4 VM, mỗi VM có pool tối đa 10 kết nối, có giới hạn lý thuyết 40 backend connection (chưa tính job, admin và hệ thống khác). Nếu serverless scale thành 200 environment, mỗi environment giữ pool tối đa 10, tổng tiềm năng trở thành 2.000 connection. Database có thể chỉ cho phép một phần nhỏ con số đó.

Đặt pool size cao trong từng function thường không giúp request nhanh hơn. Khi một invocation chỉ chạy một truy vấn, pool nhiều connection ở mỗi environment chỉ làm tăng số session có thể mở mà không đem lại lợi ích tương ứng.

## 3. Ước lượng connection trước khi triển khai

### 3.1. Giới hạn trên

Với mô hình đơn giản, nếu:

- E: số execution environment hoạt động đồng thời,
- P: số connection tối đa trong pool của mỗi environment,
- D: số connection phụ mỗi environment có thể mở ngoài pool,

thì số client connection tiềm năng xấp xỉ:

$$
C_{client,max} = E \times (P + D)
$$

Nếu mỗi environment xử lý đồng thời nhiều invocation và mỗi invocation tự tạo connection riêng, cần tính theo concurrency thực tế thay vì chỉ dùng E. Công thức trên là mô hình ước lượng; giới hạn thật còn phụ thuộc runtime, driver, pool lifecycle, multiplexing, proxy và cách ứng dụng giữ session.

### 3.2. Chừa ngân sách cho các client khác

Không dành toàn bộ max_connections cho function. Một ngân sách sơ bộ:

$$
C_{function} \leq C_{DB,safe} - C_{other} - C_{reserve}
$$

Trong đó:

- C_DB,safe là ngân sách connection database có thể phục vụ ổn định theo cấu hình và đo tải.
- C_other gồm ứng dụng khác, worker, migration, monitoring, quản trị và công cụ vận hành.
- C_reserve là phần dự phòng cho burst, failover, rollout, maintenance và hoạt động khẩn cấp.

Giới hạn connection trong cấu hình database không nhất thiết bằng số connection có thể duy trì hiệu năng tốt. Mỗi connection tiêu tốn memory, process/thread và tài nguyên nội bộ. Xác nhận bằng load test và hướng dẫn của engine.

### 3.3. Ví dụ tính ngân sách

Giả sử database có giới hạn cấu hình 500 connection. Qua thử tải ban đầu, đội đặt ngân sách vận hành an toàn 350 connection. Client hiện hữu và công cụ vận hành dùng tối đa dự kiến 180; đội dành 50 cho dự phòng. Phần còn lại cho serverless:

$$
C_{function} = 350 - 180 - 50 = 120
$$

Nếu có tối đa 60 execution environment cùng lúc, pool trung bình tối đa theo phép tính sơ bộ là:

$$
P \leq 120 / 60 = 2
$$

Điều này gợi ý mỗi environment chỉ nên giữ tối đa khoảng 2 backend connection trong mô hình trực tiếp. Đây **không phải khuyến nghị mặc định pool size=2**; nếu concurrency lên 150 environment thì ngân sách sẽ vượt. Cần kết hợp giới hạn concurrency, pool size, proxy, timeout và hành vi scale.

### 3.4. Bảng kịch bản tải

| Kịch bản giả định | Environment đồng thời | Pool max mỗi environment | Connection tiềm năng |
| --- | ---: | ---: | ---: |
| Tải thường | 20 | 2 | 40 |
| Cao điểm | 60 | 2 | 120 |
| Burst chưa giới hạn | 150 | 2 | 300 |
| Burst với pool lớn | 150 | 5 | 750 |

Bảng chỉ mô tả tích environment × pool và chưa tính nguồn kết nối khác. Cần xác định concurrency cap phù hợp với database thay vì cho function scale vô hạn rồi hy vọng DB theo kịp.

## 4. Quản lý vòng đời connection trong function

### 4.1. Khởi tạo client ngoài handler khi có thể tái sử dụng

Nhiều nền tảng tái sử dụng execution environment qua nhiều invocation. Có thể khởi tạo DB client hoặc pool ở phạm vi module/global để dùng lại, thay vì mở và đóng pool cho mọi request. Cách này giảm chi phí DNS, TCP/TLS handshake và authentication khi environment được tái sử dụng.

Ví dụ Node.js:

~~~javascript
// db.js - pool nhỏ cho mỗi execution environment.
import pg from "pg";

const { Pool } = pg;
const pool = new Pool({
  host: process.env.DB_HOST,
  port: Number(process.env.DB_PORT ?? 5432),
  database: process.env.DB_NAME,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  max: 1,
  connectionTimeoutMillis: 2000,
  idleTimeoutMillis: 10000,
  statement_timeout: 5000,
  ssl: { rejectUnauthorized: true }
});

export async function query(text, values) {
  return pool.query(text, values);
}
~~~

Handler import hàm query và dùng pool đã tạo trong environment. max=1 là giá trị minh họa cho workload mỗi environment xử lý ít truy vấn đồng thời; cần điều chỉnh theo runtime, driver và cách ứng dụng dùng transaction.

**Không giả định execution environment luôn tồn tại hoặc luôn được tái sử dụng.** Nền tảng có thể đóng băng, kết thúc hoặc thay thế environment. Không dựa vào RAM local để giữ trạng thái nghiệp vụ, và không dựa vào hook shutdown không được bảo đảm để commit giao dịch hoặc trả dữ liệu quan trọng.

### 4.2. Tránh tạo pool mới trên mỗi invocation

~~~javascript
export async function handler(event) {
  // Anti-pattern: mỗi invocation tạo pool riêng.
  const pool = new Pool({
    connectionString: process.env.DB_URL,
    max: 10
  });
  const result = await pool.query("SELECT now()");
  await pool.end();
  return result.rows[0];
}
~~~

Mỗi request tạo pool mới làm mất lợi ích tái sử dụng, tăng handshake và có thể tạo burst connection. Gọi pool.end() cuối mỗi invocation cũng không tốt nếu runtime giữ environment sống cho request tiếp theo.

Đây là anti-pattern với runtime có tái sử dụng pool. Nếu runtime không tái sử dụng môi trường, database API client không có pool hoặc nền tảng khuyến nghị kết nối ngắn hạn, chiến lược khác có thể phù hợp. Dùng hướng dẫn chính thức của runtime/driver và đo trước khi chọn.

### 4.3. Giải phóng connection mượn từ pool

~~~javascript
export async function createOrder(pool, order) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const inserted = await client.query(
      "INSERT INTO orders(id, customer_id, status) VALUES ($1, $2, $3) RETURNING id",
      [order.id, order.customerId, "PENDING"]
    );
    await client.query(
      "UPDATE inventory SET reserved = reserved + 1 WHERE sku = $1",
      [order.sku]
    );
    await client.query("COMMIT");
    return inserted.rows[0].id;
  } catch (error) {
    try {
      await client.query("ROLLBACK");
    } catch (rollbackError) {
      // Ghi log an toàn, giữ nguyên lỗi gốc.
    }
    throw error;
  } finally {
    client.release();
  }
}
~~~

Nếu quên release(), pool sẽ cạn connection dù database vẫn hoạt động. Nếu không rollback khi transaction thất bại, session có thể ở trạng thái transaction mở, giữ lock hoặc làm thao tác sau lỗi. Production cần xử lý trường hợp rollback không thành công và loại bỏ session nếu driver xác định session không còn an toàn để tái sử dụng.

## 5. Connection pooling: đặt pool ở đâu?

### 5.1. Pool trong từng execution environment

Mỗi environment duy trì pool nhỏ, tái sử dụng connection trong các invocation tiếp theo.

**Ưu điểm:** đơn giản, không thêm hop, độ trễ thấp khi connection còn sống.

**Giới hạn:** pool nhân lên theo số environment; mỗi instance có thể scale đồng thời; environment cũ có thể bị đóng băng hoặc đóng; connection stale sau network/database failover cần được phát hiện và tái lập.

Phù hợp khi concurrency có giới hạn, pool rất nhỏ, database đủ connection budget và driver xử lý connection lỗi đúng.

### 5.2. Proxy hoặc pooler ở giữa

Proxy nhận nhiều kết nối client từ function rồi quản lý kết nối backend tới database. Một số proxy chỉ giữ và tái sử dụng backend session; một số pooler hỗ trợ **transaction pooling** hoặc multiplexing để nhiều client session dùng chung ít backend connection hơn.

~~~mermaid
flowchart TB
    F1["Function environment A"] --> C1["Client connection"]
    F2["Function environment B"] --> C2["Client connection"]
    F3["Function environment C"] --> C3["Client connection"]
    C1 --> Proxy["Managed DB Proxy / Pooler"]
    C2 --> Proxy
    C3 --> Proxy
    Proxy --> B1["Backend DB session 1"]
    Proxy --> B2["Backend DB session 2"]
    B1 --> DB[("Database")]
    B2 --> DB
~~~

**Ưu điểm:** giảm backend connection, che bớt churn từ client, tập trung quản lý xác thực và có thể hỗ trợ failover tùy sản phẩm.

**Chi phí:** thêm network hop, thành phần cần capacity và giám sát, phí dịch vụ, giới hạn session/pinning, điểm phụ thuộc và cách xử lý lỗi mới. Proxy cũng có max client, CPU, memory và throughput.

### 5.3. Session pooling và transaction pooling

| Chế độ | Nguyên lý | Khả năng tương thích |
| --- | --- | --- |
| **Session pooling** | Client gắn với backend session trong suốt vòng đời client | Tương thích tốt hơn session state, nhưng giảm mức ghép nối backend |
| **Transaction pooling** | Backend được gán khi transaction bắt đầu và trả về pool khi transaction kết thúc | Tăng multiplexing nhưng hạn chế session state ngoài transaction |
| **Statement pooling** | Backend có thể được dùng cho từng statement | Hạn chế mạnh; không phù hợp nhiều luồng cần transaction nhiều statement |

Transaction pooling có thể không tương thích với session-level SET, temporary table, session advisory lock, prepared statement hoặc state gắn với backend, tùy pooler và cấu hình. Cần kiểm thử driver, ORM và truy vấn thực tế. Không chuyển chế độ pooling trong production khi chưa xác minh tính tương thích.

### 5.4. Proxy không có semantics giống nhau

Tên gọi proxy không bảo đảm mọi sản phẩm hỗ trợ transaction multiplexing. Managed database proxy có thể quản lý connection lifecycle, giữ session backend cho client hoặc có giới hạn pinning. Pooler chuyên dụng như PgBouncer công bố các chế độ pooling riêng. Hãy kiểm tra:

- Proxy có mở backend connection thay mặt client không, và tối đa bao nhiêu?
- Có hỗ trợ transaction pooling hay chỉ session pooling?
- Những thao tác nào làm session bị pin vào backend?
- Hành vi khi database failover, credential rotation hoặc connection timeout?
- Có TLS từ client tới proxy và từ proxy tới database không?
- Quota, throughput, connection limit, idle timeout và chi phí ra sao?

## 6. Chọn mô hình truy cập dữ liệu cho serverless

Không phải ứng dụng serverless nào cũng cần proxy. Lựa chọn phụ thuộc database engine, driver, concurrency, thời gian truy vấn, yêu cầu transaction và khả năng nền tảng.

| Mô hình | Khi phù hợp | Đánh đổi |
| --- | --- | --- |
| Direct connection + pool nhỏ | Concurrency giới hạn, DB chịu được client sessions | Đơn giản và ít hop, nhưng connection nhân theo environment |
| Managed DB proxy | Cần giảm connection churn và quản lý client connection | Thêm chi phí/hop, cần hiểu pinning, quota và failover |
| Dedicated pooler | Có thể vận hành pooler và cần transaction pooling/multiplexing | Tự quản lý HA, sizing, monitoring và compatibility |
| HTTP/Data API | Database cung cấp API phù hợp; workload cần request HTTP | Tránh socket ở client nhưng thay đổi semantics, latency, transaction và API quota |
| Queue + batch/worker | Tác vụ có thể bất đồng bộ và gom nhóm | Tăng độ trễ, eventual consistency và cơ chế retry/dedup |

**Không biến mọi thao tác database thành HTTP API chỉ để tránh connection.** So sánh giao dịch, query pattern, payload, giới hạn request, độ trễ và khả năng bảo đảm tính đúng đắn.

## 7. Giới hạn concurrency và backpressure

Pool nhỏ giúp giảm connection mỗi environment nhưng không tự giới hạn tổng số environment. Cần quản lý concurrency từ lớp function và event source.

### 7.1. Chọn concurrency cap theo ngân sách DB

Nếu mỗi environment tạo tối đa P backend connection và ngân sách function là C_function, giới hạn environment sơ bộ:

$$
E_{max} \leq \left\lfloor \frac{C_{function}}{P} \right\rfloor
$$

Nếu dùng proxy, phải phân biệt **client connection tới proxy** và **backend connection tới database**. Tổng client connection có thể cao hơn backend pool, nhưng proxy vẫn có max client, CPU, memory và throughput. Cần tính cả hai đầu.

### 7.2. Giảm tốc từ nhiều lớp

- **Function concurrency limit:** đặt mức đồng thời tối đa theo database budget.
- **Event source concurrency:** điều chỉnh số message xử lý cùng lúc; batch size và polling cũng ảnh hưởng tải.
- **Queue buffering:** đưa công việc không cần phản hồi ngay vào hàng đợi để hấp thụ burst.
- **Rate limiting:** giới hạn request từ client/tenant và bảo vệ thao tác đắt.
- **Database admission control:** giới hạn workload, query timeout, transaction duration và pool size.
- **Backpressure:** khi DB/proxy vượt ngưỡng, giảm tốc nhận việc thay vì tiếp tục tạo invocation.

Với queue, tăng consumer quá nhanh có thể biến backlog thành burst connection. Cần đặt concurrency theo capacity DB và tăng dần khi backlog cao, thay vì scale worker theo queue depth mà không có trần.

### 7.3. Ví dụ chiến lược xử lý burst

API nhận đơn hàng có thể xác nhận nhanh việc tiếp nhận và đưa công việc xử lý đơn vào queue. Worker serverless đọc batch nhỏ, concurrency giới hạn, dùng pool/proxy để ghi DB. Khi database tăng latency hoặc backend connection gần ngưỡng, giảm consumer concurrency và để backlog tăng trong giới hạn nghiệp vụ chấp nhận.

Mô hình này chỉ phù hợp nếu nghiệp vụ cho phép phản hồi “đã tiếp nhận” trước khi giao dịch hoàn tất. Nếu người dùng cần biết tồn kho và thanh toán đã xác nhận ngay lập tức, phải thiết kế luồng đồng bộ riêng hoặc quy trình trạng thái rõ ràng.

## 8. Thiết kế transaction ngắn và có thể phục hồi

Transaction chiếm backend connection trong thời gian mở và có thể giữ lock. Trong serverless, thời gian thực thi function có thể kéo dài do cold start, retry, gọi dịch vụ ngoài hoặc chờ queue. Vì vậy, **thời gian giữ transaction phải ngắn và có giới hạn**.

### 8.1. Không giữ transaction trong lúc gọi hệ thống bên ngoài

Mẫu rủi ro:

~~~text
BEGIN
  Đọc tồn kho và khóa hàng
  Gọi payment gateway qua Internet (có thể mất vài giây)
  Chờ callback hoặc retry
  Ghi trạng thái đơn
COMMIT
~~~

Trong khoảng chờ payment, connection và lock vẫn bị giữ. Nếu payment gateway chậm, nhiều invocation có thể đồng thời giữ connection/lock, làm các request khác xếp hàng và tăng nguy cơ deadlock hoặc timeout.

Nên tách quy trình thành các bước có trạng thái:

1. Transaction ngắn tạo đơn ở trạng thái PENDING và giữ/ghi nhận reservation theo cơ chế nguyên tử.
2. Commit transaction, trả connection về pool.
3. Gọi payment gateway ngoài transaction, dùng idempotency key.
4. Transaction ngắn tiếp theo cập nhật trạng thái dựa trên kết quả thanh toán đã xác minh.
5. Nếu không xác định được kết quả vì timeout, giữ trạng thái PENDING/UNKNOWN theo chính sách và đối soát; không tự suy ra giao dịch thất bại.

~~~mermaid
sequenceDiagram
    participant F as Serverless function
    participant DB as Database
    participant Pay as Payment gateway
    F->>DB: BEGIN, create PENDING order
    F->>DB: Reserve inventory, COMMIT
    DB-->>F: Commit OK
    F->>Pay: Charge with idempotency key
    alt Payment accepted
        Pay-->>F: Payment reference
        F->>DB: BEGIN, set PAID, COMMIT
    else Timeout / unknown result
        Pay--xF: No conclusive response
        F->>DB: Record PENDING/UNKNOWN, schedule reconciliation
    end
~~~

Đây là một quy trình nghiệp vụ có nhiều bước, không còn một transaction ACID bao trùm tất cả. Cần thiết kế state machine, reservation expiry, compensation/hoàn tiền, reconciliation và thông báo theo yêu cầu. Đừng giải quyết bằng cách mở transaction lâu hơn.

### 8.2. Giới hạn thời gian

Thiết lập các timeout theo thứ tự phù hợp:

| Timeout | Mục đích | Lưu ý |
| --- | --- | --- |
| Connection acquisition timeout | Giới hạn thời gian chờ lấy connection từ pool/proxy | Quá dài làm invocation chiếm concurrency nhưng chưa xử lý được |
| Connect timeout | Giới hạn thời gian mở socket/TLS tới DB hoặc proxy | Phải tính DNS, network và handshake |
| Statement/query timeout | Ngăn truy vấn chạy vô hạn | Phải phù hợp với SLA của query và engine |
| Transaction timeout/idle-in-transaction | Phát hiện transaction kéo dài hoặc bị bỏ quên | Cần thống nhất với hành vi application và DB |
| Function deadline | Giới hạn tổng thời gian invocation | Phải đủ cho cleanup/rollback có kiểm soát trước deadline nếu runtime hỗ trợ |

Không đặt mọi timeout bằng nhau. Thời gian lấy connection nên nhỏ hơn tổng deadline; query timeout nên để đủ thời gian cho thao tác hợp lệ nhưng chặn truy vấn treo; function deadline cần đủ khoảng xử lý lỗi và cleanup.

### 8.3. Connection stale và failover

Một pool sống lâu có thể chứa connection bị DB restart, proxy failover, network interruption hoặc hết hạn idle. Driver cần kiểm tra connection lỗi và pool phải bỏ session hỏng thay vì tái sử dụng liên tục. Cân nhắc:

- Validation/health check khi mượn connection, nếu driver và hiệu năng cho phép.
- Maximum lifetime/idle timeout phù hợp với policy của proxy/database.
- Retry kết nối mới cho lỗi tạm thời, nhưng không retry lệnh ghi nếu không biết lệnh trước đã commit hay chưa.
- Dùng idempotency key hoặc transaction marker để xác định kết quả khi response mất sau commit.
- Đo tỷ lệ reconnect, connection reset, authentication failure và thời gian hồi phục.

## 9. Retry, idempotency và tránh khuếch đại tải

Retry giúp vượt qua lỗi tạm thời, nhưng trong serverless retry có thể làm concurrency tăng đúng lúc database đang yếu. Nếu mỗi invocation timeout rồi nền tảng tự gửi lại, function có thể chạy lại nhiều lần trong khi connection cũ hoặc query cũ vẫn chưa kết thúc.

### 9.1. Phân loại lỗi trước khi retry

| Nhóm lỗi | Ví dụ | Hành vi khuyến nghị |
| --- | --- | --- |
| Lỗi cấu hình / vĩnh viễn | Sai password, database không tồn tại, thiếu quyền | Không retry liên tục; cảnh báo và sửa cấu hình |
| Lỗi tạm thời kết nối | Reset, failover, DNS/network interruption | Retry giới hạn với backoff và jitter |
| Quá tải | Too many connections, pool exhausted, throttling | Giảm concurrency/backpressure; không tăng retry ngay lập tức |
| Lỗi câu lệnh | Constraint violation, SQL syntax, schema mismatch | Xử lý theo ngữ nghĩa nghiệp vụ hoặc sửa code; thường không retry nguyên trạng |
| Kết quả không xác định | Client mất kết nối sau khi gửi COMMIT | Tra cứu theo idempotency key/operation ID trước khi quyết định lặp |

### 9.2. Exponential backoff và jitter

Một lịch retry điển hình tăng khoảng chờ theo cấp số nhân, có giới hạn và thêm jitter để các invocation không cùng retry tại một thời điểm:

~~~javascript
function retryDelayMs(attempt, baseMs = 100, capMs = 3000) {
  const ceiling = Math.min(capMs, baseMs * (2 ** attempt));
  return Math.floor(Math.random() * ceiling);
}
~~~

Đây chỉ là hàm tính delay minh họa; chính sách thực tế phải có số lần thử tối đa, deadline tổng, phân loại lỗi và giới hạn concurrency. Không retry ngay trong function nếu thời gian chờ sẽ chiếm invocation lâu hơn giá trị mà queue/scheduler có thể cung cấp tốt hơn.

### 9.3. Idempotency cho thao tác ghi

Ví dụ client gửi yêu cầu tạo đơn với idempotency key. Database có thể lưu khóa duy nhất cùng kết quả thao tác:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id       text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash    text NOT NULL,
    response_body   jsonb,
    status          text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

Use case cần xác định:

- Cùng key và cùng request hash: trả lại kết quả đã lưu hoặc trạng thái đang xử lý.
- Cùng key nhưng payload khác: từ chối vì key bị dùng sai.
- Request đầu tiên đang chạy: request trùng phải chờ, đọc trạng thái hoặc nhận mã xử lý, theo hợp đồng API.
- Key hết hạn: thời gian lưu phải đủ dài hơn cửa sổ retry của client, event source và payment provider.

Idempotency record phải được ghi trong transaction phù hợp với tác dụng phụ quan trọng. Nếu lưu key ở một transaction và ghi đơn ở transaction khác mà không có thiết kế đồng bộ, có thể tồn tại record “đã xử lý” nhưng đơn chưa được tạo, hoặc ngược lại.

## 10. Bảo mật kết nối database

Kết nối DB serverless cần có quyền tối thiểu và vòng đời credential được kiểm soát. Việc function tự động scale không phải lý do cấp một tài khoản DB siêu quyền cho mọi invocation.

### 10.1. Quản lý secret và identity

- Ưu tiên cơ chế xác thực tích hợp workload identity/IAM hoặc token ngắn hạn khi engine, driver và proxy hỗ trợ.
- Nếu dùng username/password, lưu trong secret manager, kiểm soát quyền đọc theo function/role và có kế hoạch rotation.
- Không ghi connection string, password, token hoặc full SQL chứa dữ liệu cá nhân vào log.
- Không nhúng secret vào source code, image, package hoặc biến cấu hình không được bảo vệ.
- Tách identity theo môi trường và workload; tránh dùng chung tài khoản database cho dev, staging và production.
- Đánh giá quyền SELECT/INSERT/UPDATE theo bảng hoặc schema; không mặc định quyền DDL/owner.

### 10.2. TLS và network access

Kết nối từ function tới proxy/database cần mã hóa theo chính sách. Xác minh chứng chỉ máy chủ, CA chain, hostname validation và rotation. Nếu TLS chấm dứt tại proxy, đường proxy→database cũng cần được đánh giá; không mặc định private network là đường truyền đã mã hóa.

Database không nên mở public endpoint cho mọi địa chỉ chỉ để function truy cập dễ hơn. Đặt function trong VPC/VNet hoặc mô hình private networking phù hợp, giới hạn security group/firewall theo nguồn và port cần thiết. Đồng thời tính tới tác động của NAT gateway, subnet routing, DNS và địa chỉ IP egress nếu dịch vụ database/proxy cần allowlist.

### 10.3. Tách quyền và giới hạn dữ liệu

| Kiểm soát | Thiết kế |
| --- | --- |
| Identity của function | Role riêng theo function hoặc nhóm workload có cùng rủi ro |
| DB principal | Tài khoản chỉ có quyền trên schema/table cần thiết |
| Secret access | Chỉ role runtime được đọc secret cần dùng; audit việc truy cập |
| Network | Chỉ cho kết nối từ subnet/security identity cần thiết; không mở DB toàn Internet |
| TLS | Xác minh certificate và mã hóa cả những chặng cần bảo vệ |
| Logging | Che password, token, parameter nhạy cảm và dữ liệu cá nhân |
| Rotation | Luân chuyển secret/token không làm gián đoạn toàn bộ function; kiểm thử pool reconnect |

Rotation credential có thể làm connection hiện hữu mất hiệu lực hoặc khiến pool mới xác thực thất bại. Cần kiểm tra hành vi của proxy, database và driver; triển khai theo giai đoạn và theo dõi lỗi authentication.

## 11. Quan sát connection và database saturation

Chỉ nhìn CPU database là chưa đủ. Database có thể ít CPU nhưng hết connection, nhiều session idle-in-transaction hoặc chờ lock; proxy có thể hết client capacity trong khi backend DB còn khỏe.

### 11.1. Chỉ số nên theo dõi

| Lớp | Metric / tín hiệu | Ý nghĩa |
| --- | --- | --- |
| Function | Concurrent executions, throttles, duration, timeout, cold starts | Ước lượng số client potential và tải phát sinh |
| Driver / pool | Total, idle, active, waiting, acquisition latency, connection errors | Phát hiện pool cạn, leak hoặc reconnect |
| Proxy | Client connections, backend connections, queue depth, pinning, CPU/memory | Phát hiện proxy saturation và multiplexing kém |
| Database | Current/max connections, active/idle sessions, lock waits, deadlocks | Nhìn giới hạn và tắc nghẽn DB |
| Query | p50/p95/p99 latency, slow query, rows scanned, timeout | Xác định query là bottleneck thay vì connection count |
| Transaction | Duration, idle-in-transaction, rollback, commit failures | Phát hiện giữ connection/lock quá lâu |
| Queue/event source | Backlog age, batch size, retry count, consumer concurrency | Phát hiện burst được chuyển xuống database |

Đặt cảnh báo theo ngưỡng và xu hướng. Ví dụ cảnh báo khi backend connection đạt tỷ lệ cao so với ngân sách an toàn, khi acquisition latency tăng hoặc waiting pool kéo dài. Ngưỡng cụ thể phải lấy từ load test và tài nguyên engine.

### 11.2. Correlation ID và truy vết

Gắn operation/request ID xuyên qua API gateway, function, queue, proxy logs và database query logs khi công cụ hỗ trợ. Điều này giúp xác định request nào mở transaction lâu hoặc gửi query lặp. Không đưa credential hoặc payload nhạy cảm vào trace attribute; giới hạn cardinality và retention của telemetry.

### 11.3. Phân biệt pool exhaustion và DB exhaustion

**Pool exhaustion phía client:** pool không còn connection rảnh, invocation chờ acquisition. Database vẫn có thể chưa chạm max_connections; có thể do connection leak, transaction dài hoặc pool quá nhỏ.

**DB connection exhaustion:** database đã đạt giới hạn session; client mới hoặc proxy backend không thể đăng nhập. Tìm nguồn connection khác, session idle và budget của các workload.

**Proxy saturation:** proxy hết client connection, backend pool, CPU/memory hoặc queue capacity. Database có thể vẫn khỏe; tăng max pool ở mọi function có thể làm proxy quá tải hơn.

Điều tra theo từng lớp và so sánh các chỉ số đồng thời trước khi tăng giới hạn.

## 12. Load test và sizing thực tế

Một kế hoạch thử tải có ý nghĩa phải tái hiện đặc tính serverless, không chỉ gửi nhiều request vào một function đã warm sẵn.

### 12.1. Các kịch bản cần đo

1. **Warm steady-state:** traffic đều, execution environment được tái sử dụng; đo baseline pool, query latency và connection.
2. **Cold burst:** tăng request nhanh từ gần 0 lên peak; quan sát số environment mới, connection handshake và proxy/backend growth.
3. **Sustained peak:** duy trì concurrency trong thời gian đủ lâu để phát hiện leak và idle session.
4. **Spike and recovery:** tải tăng nhanh rồi giảm; đo connection đóng/idle timeout và thời gian giải phóng tài nguyên.
5. **Database failover/restart:** quan sát stale connection, reconnect storm, transaction không rõ kết quả và thời gian phục hồi.
6. **Proxy unavailable hoặc quá tải:** xác nhận function timeout/backoff và không tạo retry storm.
7. **Credential rotation:** xác minh pool cũ/mới, authentication và continuity.
8. **Queue backlog:** tăng consumer theo nhiều mức để tìm điểm database bắt đầu bão hòa.

### 12.2. Ma trận thử nghiệm

| Biến số | Giá trị thử nghiệm gợi ý | Quan sát |
| --- | --- | --- |
| Function concurrency cap | 10, 25, 50, 100 (tùy quota lab) | Connection peak, throttle, latency |
| Pool max per environment | 1, 2, 4 | Backend sessions, acquisition wait |
| Proxy | Không proxy / proxy session / transaction pool nếu hỗ trợ | Client/backend ratio, pinning, latency |
| Query duration | Ngắn, trung bình, query giả lập chậm | Transaction time, lock, waiting |
| Retry policy | Không retry, retry cố định, backoff+jitter | Tổng request, connection storm, thời gian recovery |
| Event batch/concurrency | Batch nhỏ/lớn, consumer cap thấp/cao | DB pressure, backlog age, throughput |

Không thử nghiệm phá hủy trên production database. Sử dụng môi trường tương đương, dữ liệu đã làm sạch và giới hạn chi phí. Mỗi thay đổi chỉ nên tác động một nhóm biến số đủ nhỏ để xác định nguyên nhân.

### 12.3. Tiêu chí chấp nhận

Một cấu hình có thể được chấp nhận khi:

- Connection peak thấp hơn ngân sách đã duyệt, kể cả trong burst và failover.
- Acquisition/query latency và tỷ lệ lỗi nằm trong SLO.
- Function không timeout chỉ vì chờ pool; pool waiting không tăng vô hạn.
- Proxy và database có headroom phù hợp, không có session idle-in-transaction kéo dài.
- Retry không làm tăng tải khi database đang quá tải.
- Tác vụ ghi vẫn idempotent sau timeout hoặc mất response.
- Credential rotation và endpoint failover có thể hoàn thành trong mục tiêu phục hồi.
- Tổng chi phí function, proxy, database, NAT và telemetry nằm trong ngân sách.

## 13. Ví dụ kiến trúc: API đặt hàng serverless

Giả sử một API nhận yêu cầu tạo đơn hàng. API Gateway gọi function, function ghi đơn và reservation vào PostgreSQL, sau đó phát thông báo cho xử lý thanh toán. Lưu lượng bình thường thấp nhưng có campaign khiến concurrency tăng đột biến.

### 13.1. Kiến trúc đề xuất

~~~mermaid
flowchart TB
    Client["Web / Mobile"] --> GW["API Gateway"]
    GW --> Fn["CreateOrder function"]
    Fn --> Proxy["Managed DB proxy / pooler"]
    Proxy --> DB[("PostgreSQL")]
    Fn --> Q["Queue: OrderAccepted"]
    Q --> Worker["Payment / order worker functions"]
    Worker --> Proxy
    Proxy --> DB
    DB --> Obs["DB metrics / logs"]
    Proxy --> Obs
    Fn --> Telemetry["Function logs / traces"]
    Worker --> Telemetry
~~~

Trong thiết kế này, API function có pool nhỏ hoặc dùng client ngắn hạn theo khuyến nghị của dịch vụ proxy; worker concurrency bị giới hạn theo ngân sách DB. Không mặc định mỗi function có pool 10 connection. Connection budget tính chung cả API, worker, batch, admin và migration.

### 13.2. Luồng tạo đơn

1. API Gateway xác thực request ở mức phù hợp; function kiểm tra tenant/actor và idempotency key.
2. Function gọi transaction ngắn để ghi order PENDING, reservation và idempotency result theo hợp đồng.
3. Commit xong, connection được trả lại.
4. Hệ thống ghi outbox event cùng transaction hoặc dùng cách bảo đảm phát sự kiện không bị mất đã được thiết kế.
5. Worker nhận message, xử lý payment ngoài transaction DB, dùng idempotency key cho payment gateway.
6. Worker cập nhật trạng thái đơn trong transaction riêng.
7. Nếu payment timeout, trạng thái UNKNOWN được đối soát; không trừ tiền lần nữa chỉ vì message được giao lại.

### 13.3. Quyết định sizing

| Hạng mục | Quy tắc thiết kế mẫu |
| --- | --- |
| Function local pool | Nhỏ, cân theo số query song song trong từng environment |
| Function concurrency | Giới hạn tổng environment theo ngân sách backend connection và proxy capacity |
| DB proxy | Đặt HA và giám sát client/backend session, pinning, queue |
| Database | Chừa connection cho admin, migration, monitoring và workload khác |
| Queue worker | Giới hạn consumer concurrency; backpressure khi DB latency/connection tăng |
| Transaction | Chỉ bao gồm thao tác DB cần atomic; không giữ trong lúc gọi payment API |
| Retry | Có backoff+jitter, số lần tối đa và idempotency |
| Monitoring | Theo dõi đồng thời function, pool, proxy, DB và queue |

Đây là nguyên tắc thiết kế, không phải cấu hình cố định. Số pool, concurrency và proxy instance phải được đo bằng tải và dịch vụ cụ thể.

## 14. Lựa chọn database và mô hình dữ liệu phù hợp

Quản lý connection không thể tách rời lựa chọn database. Một workload serverless có thể dùng relational database, key-value/document database, data API hoặc dịch vụ managed hỗ trợ HTTP.

| Loại backend | Mô hình truy cập | Câu hỏi cần xem xét |
| --- | --- | --- |
| Relational DB qua TCP | Driver và connection pool/proxy | Transaction, concurrent sessions, connection limit, lock và query pattern |
| Key-value/document managed | SDK/API, đôi khi HTTP-based | Partition key, throughput, hot partition, transaction semantics, throttling |
| Database Data API | HTTPS request tới service API | Request quota, payload, transaction duration, latency và feature parity |
| Serverless database engine | Có thể tự scale compute/storage hoặc quản lý connection | Mô hình capacity, minimum spend, cold behavior, connection semantics và failover |

Chọn NoSQL không tự động giải quyết mọi vấn đề connection nếu SDK vẫn tạo client/session hoặc service có giới hạn request và throughput. Tương tự, chọn relational DB không bắt buộc phải dùng proxy nếu concurrency nhỏ và connection budget đủ.

Quyết định phải xuất phát từ truy vấn và yêu cầu nghiệp vụ: nhất quán, quan hệ, transaction, access pattern, latency, dung lượng, retention, backup, portability và kỹ năng vận hành.

## 15. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Mỗi invocation tạo pool mới | Connection churn, tăng handshake và backend session | Tái sử dụng client/pool khi runtime hỗ trợ hoặc dùng mô hình connection phù hợp |
| Pool lớn trong mọi environment | Số connection nhân theo scale-out | Pool nhỏ, concurrency cap và ngân sách connection tổng |
| Cho function scale không giới hạn | Database bị overwhelm trước compute | Admission control, concurrency và queue backpressure |
| Giữ transaction khi gọi API ngoài | Giữ connection/lock, tăng deadlock và timeout | Tách quy trình thành các transaction ngắn và trạng thái rõ |
| Retry vô hạn hoặc retry lỗi cấu hình | Connection storm và chi phí tăng | Phân loại lỗi, backoff+jitter, deadline và giới hạn lần thử |
| Retry lệnh ghi không idempotent | Tạo đơn hoặc charge trùng | Idempotency key, operation ID và reconciliation |
| Nghĩ proxy luôn multiplex mọi session | Session pinning làm backend connection vẫn cao | Đọc semantics pooler và test query/session state thật |
| Không release client sau transaction | Pool cạn dù DB còn khỏe | finally/release, rollback và kiểm tra leak |
| Coi CPU DB là chỉ số duy nhất | Bỏ sót connection exhaustion, lock và proxy queue | Quan sát cả pool/proxy/database/transaction |
| Rotation password không kiểm thử | Pool mới không xác thực; pool cũ bị ngắt | Secret rotation có giai đoạn, reconnect và rollback |
| Public DB để function kết nối dễ hơn | Tăng bề mặt tấn công và phụ thuộc IP | Private networking, TLS, IAM và firewall tối thiểu |
| Tách mọi tác vụ thành async | Eventual consistency và retry phức tạp không cần thiết | Chỉ bất đồng bộ khi nghiệp vụ cho phép |

## 16. Bài thực hành: giữ database ổn định trong campaign

Một nền tảng thương mại điện tử sử dụng function serverless để xử lý checkout. Trong ngày thường có khoảng 15 environment hoạt động, nhưng campaign có thể tăng nhanh lên 180. Mỗi environment hiện đang tạo pool PostgreSQL tối đa 5 connection. Database có giới hạn cấu hình 600 connection; hệ thống báo cáo và quản trị có thể sử dụng tối đa 160. Sau campaign thử nghiệm, database báo too many connections và function timeout tăng mạnh.

**Yêu cầu bài làm:**

1. Tính số client connection tiềm năng ở ngày thường và campaign theo giả định pool đang được tạo đầy đủ.
2. Đề xuất ngân sách connection cho checkout sau khi chừa phần vận hành và headroom; ghi rõ các giả định chưa có dữ liệu.
3. So sánh ba phương án: giảm pool size + concurrency cap; bổ sung managed proxy/pooler; chuyển một phần xử lý sang queue/worker.
4. Thiết kế lại transaction tạo đơn để không giữ connection trong lúc gọi payment gateway; mô tả state khi payment timeout.
5. Xác định idempotency key, nơi lưu kết quả và cách xử lý khi client retry sau khi response bị mất.
6. Đề xuất timeout, retry/backoff và concurrency cho worker khi queue backlog tăng.
7. Liệt kê metric và dashboard cần có để phân biệt pool exhaustion, proxy saturation và database exhaustion.
8. Viết kịch bản load test gồm warm traffic, cold burst, sustained peak, failover và credential rotation.
9. Viết ADR ghi lựa chọn kiến trúc, chi phí, rủi ro và điều kiện xem lại.

### Gợi ý đánh giá

Với giả định mọi environment mở đủ pool:

$$
C_{normal} = 15 \times 5 = 75
$$

$$
C_{campaign} = 180 \times 5 = 900
$$

Mức 900 vượt giới hạn cấu hình 600 trước cả khi tính 160 connection từ báo cáo/quản trị. Một phương án đạt yêu cầu không chỉ giảm pool; nó phải **giới hạn tổng concurrency, chừa ngân sách, quản lý transaction và kiểm soát retry**. Nếu đưa proxy vào, cần tính riêng client connection và backend connection, đồng thời kiểm tra pinning và quota.

## 17. Checklist trước khi đưa function truy cập database vào production

- [ ] Đã mô hình hóa concurrency của runtime và số execution environment tối đa.
- [ ] Đã xác định mỗi environment/invocation có thể tạo bao nhiêu connection.
- [ ] Connection budget bao gồm các ứng dụng khác, worker, migration, admin và phần dự phòng.
- [ ] Pool được tái sử dụng đúng lifecycle hoặc dùng chiến lược kết nối được provider khuyến nghị.
- [ ] Connection được release; transaction luôn commit/rollback và có thời hạn phù hợp.
- [ ] Không giữ transaction trong lúc chờ API ngoài, queue hoặc tác vụ không liên quan.
- [ ] Pool/proxy/DB có timeout, idle policy, connection lifetime và xử lý stale session rõ ràng.
- [ ] Function concurrency, event source concurrency và queue consumer có giới hạn.
- [ ] Retry phân loại lỗi, backoff+jitter và có giới hạn; thao tác ghi có idempotency.
- [ ] Payment hoặc thao tác ngoài có trạng thái không xác định và quy trình reconciliation.
- [ ] Database credentials được quản lý bằng secret manager/IAM phù hợp; có rotation đã thử.
- [ ] TLS, hostname validation, private networking, firewall và least privilege được cấu hình.
- [ ] Có metric pool waiting, proxy client/backend, DB connections, transaction duration và query latency.
- [ ] Đã load test cold burst, sustained peak, failover, proxy pressure và credential rotation.
- [ ] Có alert, runbook, giới hạn chi phí và kế hoạch giảm tải khi DB quá tải.

**Ghi nhớ:** Serverless mở rộng compute nhanh nhưng database vẫn có giới hạn session, memory, lock và throughput. Thiết kế bền vững bắt đầu bằng **ngân sách connection có headroom**, pool nhỏ theo execution environment, concurrency cap và transaction ngắn. Proxy/pooler, queue hay Data API chỉ giải quyết được một phần bài toán; cần kiểm chứng semantics, bảo mật và hành vi lỗi dưới tải thực tế để giữ độ tin cậy, hiệu năng, chi phí và vận hành trong giới hạn chấp nhận được.
