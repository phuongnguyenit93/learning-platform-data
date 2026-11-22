# DriverTimeout/AllNodesFailed và đọc lỗi theo từng nút

> **Chương:** Xử lý sự cố  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Ngữ cảnh:** Apache Cassandra là cơ sở dữ liệu wide-column phân tán. Khi chẩn đoán ứng dụng Java, phải kết hợp **partition key, thiết kế bảng theo truy vấn, replication, consistency level, CQL, compaction, repair, sức khỏe replica** và khả năng kết nối của driver.  
> **Trọng tâm:** Phân biệt **DriverTimeoutException**, **AllNodesFailedException** và timeout/failure từ Cassandra server; đọc **nguyên nhân theo từng nút được thử**, xác định hành động sửa an toàn.

## 1. Tình huống mở đầu: hai exception trông giống nhau nhưng chỉ ra vấn đề khác

Một endpoint Spring Boot gọi Cassandra bằng Java Driver 4.x. Trong giờ cao điểm, monitoring xuất hiện hai log:

~~~text
com.datastax.oss.driver.api.core.DriverTimeoutException:
  Query timed out after PT2S

com.datastax.oss.driver.api.core.AllNodesFailedException:
  Could not reach any contact point ...
~~~

Đọc vội có thể dẫn tới kết luận: “Cassandra chết, tăng timeout và retry năm lần”. Kết luận này **không đủ bằng chứng**, thậm chí làm incident nặng hơn.

- **DriverTimeoutException** cho biết thời gian xử lý phía driver vượt ngân sách request đã cấu hình. Đây **không tự chứng minh** query đã được coordinator xử lý, replica đã nhận mutation hay không.
- **AllNodesFailedException** cho biết driver đã không thể hoàn tất thành công hoạt động qua những node/endpoints được thử. Một exception tổng hợp có thể chứa **nhiều nguyên nhân riêng**: connection refused ở A, TLS handshake error ở B, authentication error ở C, v.v.
- **ReadTimeoutException/WriteTimeoutException** do **Cassandra server trả về** mô tả không đủ phản hồi từ replica cho một operation theo CL trong khoảng thời gian quy định. Chúng khác với timeout chỉ do driver quyết định.

Vấn đề không chỉ là bắt đúng tên class. Cần xác định **lỗi ở tầng nào, xảy ra trước hay sau khi có coordinator, những nút nào được thử, và outcome ghi có còn không rõ**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân loại **driver-side timeout**, **server-side timeout/failure**, **AllNodesFailed** và lỗi cấu hình.
2. Dùng **getAllErrors()** để xem những error cause được ghi cho **từng node đã được thử**, thay vì chỉ đọc message rút gọn.
3. Nhận diện DNS/contact points, TLS/auth, local datacenter, network, connection pool và overload từ triệu chứng.
4. Hiểu liên hệ **RF/DC, LOCAL_QUORUM, partition key, hot partition, compaction/repair** với timeout.
5. Viết mã Java xử lý sync/async exception, unwrap đúng và log chẩn đoán không rò rỉ bí mật.
6. Áp dụng **decision tree + runbook** có tiêu chí PAUSE/STOP/ESCALATE.
7. Đánh giá retry theo **idempotency, deadline, backoff và tải cluster**, không retry mù.
8. Kiểm thử các lỗi trong staging và giải thích kết quả chưa đủ bằng chứng.

> **Phiên bản:** Mã hướng tới **Apache Cassandra Java Driver 4.x**, package **com.datastax.oss.driver.api**; hành vi chi tiết, loại exception bên trong và cấu hình có thể khác theo bản driver/Cassandra/JDK. Khi triển khai thực tế, xác minh class signatures và configuration reference của **phiên bản đã pin**. Không cố tình gây fault trên production chỉ để thử bài học.

## 2. Một request Java đi qua những tầng nào?

~~~mermaid
flowchart TD
    A["HTTP/gRPC caller, deadline end-to-end"] --> B["Service Java: admission/queue/retry"]
    B --> C["Java Driver: session, routing, connection pool"]
    C --> D{"Chọn được node và channel sẵn sàng?"}
    D -->|Không| E["Per-node connection/transport failures"]
    E --> F["AllNodesFailed hoặc lỗi driver khác"]
    D -->|Có| G["Coordinator nhận CQL"]
    G --> H["Replica theo partition key + RF/DC"]
    H --> I{"Đủ response theo consistency level?"}
    I -->|Không| J["Server Read/WriteTimeout, Failure, Unavailable"]
    I -->|Có| K["Response CQL về driver"]
    G --> L["Network/queue/driver deadline"]
    K --> L
    L --> M{"Client nhận response đúng hạn?"}
    M -->|Không| N["DriverTimeout hoặc transport/caller timeout"]
    M -->|Có| O["Result/Row trả cho ứng dụng"]
~~~

Sơ đồ là **mô hình suy luận**, không phải cam kết rằng mọi exception chỉ có đúng một đường phát sinh. Driver có thể đã thử nhiều coordinator, retry hoặc speculative execution theo chính sách; một request có thể bị timeout trong khi request trước đó vẫn chạy ở server.

### 2.1. Đường đi chọn coordinator không giống đường đi replica

Cassandra phân vùng dữ liệu theo **partition key**; token map và replication strategy quyết định các replica sở hữu dữ liệu. Driver Java thường có cơ chế **token-aware routing** để ưu tiên node thích hợp khi câu lệnh có routing key hợp lệ, nhưng cần phân biệt:

- **Contact point**: địa chỉ ban đầu giúp driver khám phá cluster, không phải danh sách duy nhất của toàn bộ replica.
- **Coordinator**: node mà client gửi câu CQL tới; node đó liên lạc các replica phù hợp.
- **Replica**: node lưu dữ liệu của partition theo RF/DC/token ownership.
- **Local datacenter**: vùng driver ưu tiên/sử dụng theo policy và cấu hình.
- **Query plan/attempted nodes**: tập node/endpoints mà driver thực sự thử cho một operation; **không nhất thiết là mọi node trong cluster**.

Vì vậy, khi thấy **AllNodesFailed**, phải xem **mỗi node đã thử lỗi gì**, không mặc định “mọi node Cassandra đều chết”.

### 2.2. Cùng trạng thái UP vẫn có request timeout

Một node báo **UN (Up/Normal)** ở nodetool status có thể vẫn gặp:

- Disk latency cao hoặc gần hết dung lượng.
- Compaction/repair/streaming chiếm I/O.
- JVM GC pause, off-heap/native memory pressure.
- Connection pool bị nghẽn, pending requests tăng.
- Hot partition hoặc nhiều tombstones.
- Packet loss/cross-DC latency.
- Quorum không kịp trong deadline dù node vẫn “Up”.

Do đó không coi **nodetool status** là bài kiểm chứng đầy đủ cho mọi lỗi driver.

## 3. Bản đồ exception: tầng nào phát hiện lỗi?

| Nhóm | Class/tín hiệu điển hình | Ý nghĩa chính | Điều không được suy ra |
|---|---|---|---|
| **Driver timeout** | **DriverTimeoutException** | Ngân sách thời gian phía driver bị vượt | Cassandra chưa thực thi mutation |
| **Driver exhausted attempts** | **AllNodesFailedException** | Không có attempt thành công qua các nodes được thử; chi tiết trong **getAllErrors()** | Toàn bộ cluster chắc chắn DOWN |
| **Read timeout server** | **ReadTimeoutException** | Không đủ response đọc trong timeout theo CL | Mọi replica đều không có dữ liệu |
| **Write timeout server** | **WriteTimeoutException** | Không đủ xác nhận ghi trong timeout theo CL | Không replica nào đã ghi |
| **Read/write failure server** | **ReadFailureException**, **WriteFailureException** | Có failure khi thực thi phía server | Chỉ một nguyên nhân mạng ở Java |
| **Unavailable server** | **UnavailableException** | Không đủ replica phù hợp CL tại lúc đánh giá | Giảm CL luôn đúng hoặc an toàn |
| **Server overload** | **OverloadedException** | Node báo áp lực xử lý | Retry ngay giúp hệ thống phục hồi |
| **Session/transport** | Connection closed, refused, TLS/auth/handshake | Đường kết nối chưa sẵn sàng hoặc bị từ chối | Tất cả node có cùng lỗi |
| **Invalid query/schema** | Syntax/invalid query, codec, unknown keyspace/table/column | CQL/schema/driver mapping cần sửa | Có thể chữa bằng retry mù |

**Các class phía server** thường nằm trong **com.datastax.oss.driver.api.core.servererrors**. Một exception liên quan transport có thể là **cause bên trong AllNodesFailed**, không nhất thiết xuất hiện là top-level exception.

### 3.1. DriverTimeoutException không đồng nghĩa ReadTimeoutException

**Driver timeout** là quan sát của **client driver** sau khi request không hoàn thành trong thời gian nó cho phép. Nó có thể liên quan queue tại driver/pool, network, coordinator bận hoặc server thực thi lâu. Driver không thể từ riêng exception đó xác nhận **write outcome**.

**Server ReadTimeout** là kết quả **coordinator** trả về do điều kiện đọc ở replica/CL không đạt trong thời gian server quy định. Nó cung cấp thông tin server-side về loại operation và mức đáp ứng, nhưng không tự chỉ ra vấn đề ở đường client.

**Server WriteTimeout** còn nhạy cảm hơn: một hoặc nhiều replica có thể đã áp dụng mutation trước khi timeout. Retry write có thể gây duplicate side effects nếu operation không idempotent.

### 3.2. Một exception có thể là vỏ bọc

Với các API bất đồng bộ hoặc test Future, log top-level đôi khi chỉ là:

~~~text
java.util.concurrent.CompletionException
  caused by com.datastax.oss.driver.api.core.DriverTimeoutException

java.util.concurrent.ExecutionException
  caused by com.datastax.oss.driver.api.core.AllNodesFailedException
~~~

Phải **unwrap CompletionException/ExecutionException** trước khi phân loại. Tuy nhiên, đừng bỏ toàn bộ chuỗi cause và **suppressed exceptions** trong log nội bộ phục vụ incident; lớp cause sâu có thể chứa bằng chứng về TLS, DNS, network hoặc connection pool.

## 4. AllNodesFailedException: đừng dừng ở dòng message đầu

Một thông báo AllNodesFailed thường **rút gọn** lỗi liên quan vài node đầu. Java Driver 4.x cho phép kiểm tra **getAllErrors()** để lấy thông tin chi tiết theo những node mà request đã thử.

Ví dụ **giả định**:

~~~text
AllNodesFailedException: cannot reach a usable node
  node cassandra-a: java.net.ConnectException (connection refused)
  node cassandra-b: javax.net.ssl.SSLHandshakeException
  node cassandra-c: connection initialization timeout
~~~

**Phân tích:**

- **A — Connection refused:** port 9042 không lắng nghe, network policy, NAT/service mapping hoặc process chưa nhận kết nối. Không tự kết luận node DOWN về mặt gossip.
- **B — SSLHandshakeException:** khác biệt truststore/certificate/hostname/protocol, không chữa bằng tăng CQL request timeout.
- **C — initialization timeout:** đường kết nối chậm, auth/TLS handshake/driver init chưa hoàn tất hoặc môi trường quá tải; cần đo ở tầng thiết lập kết nối.

Một “lỗi tổng hợp” có thể có **nhiều nguyên nhân độc lập**, thậm chí một node xuất hiện **nhiều throwable theo những lần thử/channels**. Khi gọi getAllErrors(), không chỉ lấy cause đầu tiên.

### 4.1. Map không phải danh sách toàn bộ node của cluster

Cách hiểu đúng:

- Key của map mô tả node/endpoints mà driver **có ghi nhận error** cho operation.
- Một node không xuất hiện **không chứng minh** node đó khỏe hay đã được thử.
- Có thể có khác biệt khi failure xảy ra ở giai đoạn **session initialization/contact point discovery** so với sau khi metadata đầy đủ.
- Nếu list causes rỗng hoặc metadata node chưa đầy đủ, mã chẩn đoán phải xử lý phòng thủ.
- Thứ tự entry/list là **dữ liệu chẩn đoán**, không phải thứ tự ổn định để xây business logic.

**Không xây retry policy bằng cách tự iterate map rồi đổi coordinator ngẫu nhiên**. Driver đã có load balancing, node health, pool và retry policy. Map phục vụ **điều tra**, không phải API chỉ đạo thao tác routing của ứng dụng.

## 5. Đọc từng cause từ AllNodesFailed trong Java

Đoạn sau minh họa cách lấy map **getAllErrors()** của Java Driver 4.x, in loại nguyên nhân và thông tin node theo hướng không lộ payload. Trong môi trường thật dùng logger có structured fields, chuẩn hóa tên host nội bộ và giới hạn log volume.

~~~java
import java.util.List;
import java.util.Map;

import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;

public final class AllNodesFailureInspector {
    private AllNodesFailureInspector() {}

    public static void inspect(AllNodesFailedException exception) {
        Map<Node, List<Throwable>> perNode =
            exception.getAllErrors();

        if (perNode == null || perNode.isEmpty()) {
            System.err.println(
                "AllNodesFailed: no per-node details available");
            return;
        }

        for (Map.Entry<Node, List<Throwable>> entry
                : perNode.entrySet()) {
            Node node = entry.getKey();
            List<Throwable> causes = entry.getValue();

            String nodeLabel = node == null
                ? "unknown-discovery-node"
                : String.valueOf(node.getEndPoint());

            if (causes == null || causes.isEmpty()) {
                System.err.println(
                    nodeLabel + " -> no nested causes reported");
                continue;
            }

            for (int index = 0; index < causes.size(); index++) {
                Throwable cause = causes.get(index);
                String type = cause == null
                    ? "unknown"
                    : cause.getClass().getName();

                System.err.printf(
                    "attemptedNode=%s causeIndex=%d causeType=%s%n",
                    nodeLabel, index, type);

                // Trong incident: thêm sanitized cause chain,
                // event time, request ID, exception fingerprint.
            }
        }
    }
}
~~~

**Điều quan trọng trong snippet:**

1. **getAllErrors()** mới là nơi cần đọc để thấy nhiều nút/multiple failures, không chỉ top-level message.
2. **Node.getEndPoint()** là một locator kỹ thuật; host/IP có thể là thông tin hạ tầng nhạy cảm. Trong môi trường nhiều tenant, dùng map sang **node alias** được kiểm soát thay vì phơi địa chỉ ra HTTP response.
3. Ghi class của **mọi throwable**, không tự động in toàn bộ exception message nếu message có thể chứa user/keyspace/host/secret.
4. Khi metadata không đầy đủ hoặc một entry không có causes, không để **logging throw NullPointerException** rồi che mất lỗi gốc.
5. Ví dụ dùng **System.err** để dễ đọc trong lab; production nên dùng logging có rate limit, correlation ID và central tracing.
6. Trong một lỗi session init, tập node đã được biết có thể ít hơn toàn cluster; cần kiểm tra thêm contact points/DNS/TLS trong cấu hình.

### 5.1. Đọc cả chuỗi cause thay vì chỉ class ngoài cùng

Một cause ở node có thể có dạng:

~~~text
ConnectionInitException
  caused by SSLHandshakeException
    caused by ValidatorException
      caused by PKIX path building failed
~~~

Nếu logger chỉ ghi **ConnectionInitException**, đội vận hành dễ tưởng đây là pool/timeout trong khi gốc là **truststore không tin cậy chứng chỉ server**.

Ví dụ hàm giới hạn chiều sâu để tránh vòng lặp/log flood:

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class CauseSummary {
    private CauseSummary() {}

    public static String classChain(Throwable root) {
        if (root == null) {
            return "unknown";
        }

        Set<Throwable> seen = Collections.newSetFromMap(
            new IdentityHashMap<>());
        StringBuilder out = new StringBuilder();
        Throwable current = root;
        int depth = 0;

        while (current != null
                && depth < 8
                && seen.add(current)) {
            if (depth > 0) {
                out.append(" <- ");
            }
            out.append(current.getClass().getSimpleName());
            current = current.getCause();
            depth++;
        }

        if (current != null) {
            out.append(" <- ...");
        }
        return out.toString();
    }
}
~~~

Ở đây **chỉ log class chain**, không log raw message/stack trace chứa thông tin nhạy cảm. Khi cần forensic với quyền phù hợp, lưu stack trace đầy đủ ở vùng log nội bộ có kiểm soát. Cần cap số node/causes được xuất ra nếu lưu lượng incident cao, đồng thời giữ được summary/count để không che lỗi hiếm.

## 6. Đọc nguyên nhân từng nút: ma trận điều tra

Sau khi lấy được **getAllErrors()**, phân nhóm cause theo **giai đoạn kết nối và thực thi** thay vì gom tất cả vào “Cassandra unavailable”.

| Per-node cause/tín hiệu | Điểm cần kiểm tra đầu tiên | Không nên làm |
|---|---|---|
| **UnknownHostException / DNS resolution failed** | FQDN, DNS từ chính pod/VM Java, service discovery, split-horizon DNS, TTL DNS | Tăng request timeout rồi kết luận cluster chậm |
| **ConnectException: Connection refused** | IP/port 9042, CQL listener, firewall/network policy, sidecar/service, node process | Chỉ xem nodetool status ở một node khác |
| **Connect timeout / unreachable / no route** | Network route/ACL, DNS, private/public endpoint, NAT, security groups, source IP | Mặc định tất cả replica DOWN |
| **SSLHandshakeException** | Truststore, certificate chain/SAN/expiry, mutual TLS, TLS protocol và hostname verification | Tắt TLS/verify trong production để “chữa nhanh” |
| **AuthenticationException / bad credentials** | Secret rotation, username/password, authenticator, credential source, role state | Retry liên tục với cùng secret sai |
| **Authorization/permission error** | Role có quyền cho keyspace/table/query cụ thể? | Nâng runtime role thành superuser |
| **Connection closed/reset** | Node restart, proxy timeout, keepalive, network reset, idle connection handling | Kết luận server chưa thực thi mutation |
| **Connection initialization failure** | Handshake, protocol/version, TLS/auth, timeouts giai đoạn init | Tăng cql request timeout mà bỏ qua cause sâu |
| **Busy/connection pool saturated** | In-flight/channel, pool sizing, app concurrency, p99, GC, coordinator latency | Mở vô hạn connections hoặc retry storm |
| **Request rejected/overloaded** | Server CPU/disk/GC, pending threads, hot partition, maintenance | Retry tức thì hoặc tăng attempts vô hạn |
| **Invalid query/unknown keyspace** | Schema migration, keyspace-name, RF/DC, mapping và CQL | Đổi contact points ngẫu nhiên |
| **Mixed causes giữa nhiều node** | Kiểm tra từng node và common denominator: DNS/TLS/port/secret | Lấy lỗi đầu làm nguyên nhân duy nhất |

**Những tên exception trong bảng là ví dụ dấu hiệu**, không phải danh sách tất cả class Java Driver 4.x. Một số lỗi nằm sâu trong **Throwable.getCause()**, có thể được bọc bằng exception của driver/Netty/JDK khác nhau. Ghi nhận **class-chain thực tế** và version, không viết quy tắc chẩn đoán chỉ dựa vào so khớp một chuỗi message.

### 6.1. Cùng loại lỗi ở mọi node thường gợi ý cấu hình chung

Nếu tất cả contact points đều báo **SSLHandshakeException**, xem truststore/certificate/protocol ở client hoặc cấu hình TLS đồng nhất. Nếu một số node báo TLS và số khác báo ConnectException, có thể đang có **nhiều lỗi khác nhau** trong rollout certificate/network.

Nếu chỉ một node báo connection closed còn các node khác xử lý tốt, xem node-specific disk/GC/restart/network, đừng lập tức thay toàn cluster configuration.

### 6.2. Khác biệt giữa contact point và discovered node

Một **CqlSession.builder().build()** lỗi khi contact points đều không kết nối được có thể tạo AllNodesFailed **trước khi driver khám phá đầy đủ topology**. Không thể dùng map đó để suy rằng tất cả replica đã được thử.

Ngược lại, sau khi session khởi tạo thành công, driver có metadata nhiều node; query plan tùy DC/load balancing/token awareness. Tập attempted nodes vẫn có thể chỉ là **một phần** cluster. Nếu cần biết nodes nào được chọn, kết hợp:

- Driver logs/metrics của execution, query plan khi công cụ hỗ trợ.
- Metadata topology từ session và node health.
- Application request ID/query shape/partition key classification.
- Coordinator logs cùng mốc thời gian và server metrics.
- Cấu hình local-datacenter, contact points và pool.

## 7. Phân biệt các tầng timeout và deadline

Không nên tăng một timeout bất kỳ vì cùng xuất hiện chữ “timed out”.

| Tầng | Khái niệm | Triệu chứng | Cần đo |
|---|---|---|---|
| **Caller** | HTTP/gRPC/request deadline | Client ngắt dù Java service vẫn đang làm | Deadline từ lúc nhận request, queue wait |
| **Application admission** | Queue/semaphore wait | Chưa gửi CQL mà đã hết ngân sách | Active permits, rejected, wait |
| **Driver request** | Thời hạn hoàn tất execution theo driver | **DriverTimeoutException** hoặc lỗi driver-side | Time spent, retries/speculation, pool |
| **Connection establishment** | DNS/TCP/TLS/auth handshake | Connection-init/transport cause; có thể trong AllNodesFailed | Per-node connection attempts, handshake |
| **Server read/write** | Replica/coordinator đáp ứng trong thời gian server | **ReadTimeout/WriteTimeout** | CL, required/received acknowledgements, node latency |
| **Async paging** | Trang đầu vs toàn bộ nhiều trang | First page OK nhưng page N fail hoặc vượt deadline | Page count, full-result duration |
| **Downstream** | Persist/message broker/cache sau query | DB OK nhưng API vẫn timeout | Sink latency và queue |

Cấu hình Java Driver 4.x minh họa:

~~~hocon
datastax-java-driver {
  basic {
    request {
      timeout = 2 seconds
      consistency = LOCAL_QUORUM
    }
  }
}
~~~

**Đây là ví dụ**, không phải default bắt buộc của driver. Timeout kết nối, TLS, initialization và request có các option/chính sách riêng tùy phiên bản. Phải đối chiếu **effective config** đang chạy, không chỉ file local application.conf, vì execution profile/overrides có thể khác.

### 7.1. Minh họa deadline end-to-end

~~~text
HTTP caller deadline:                     2.000 ms
Đợi admission tại Java:                    300 ms
Chọn node/đợi connection pool:             250 ms
Execution Cassandra tới khi lỗi:         1.100 ms
Thời gian đã dùng:                        1.650 ms
Còn trước deadline:                        350 ms

Backoff dự kiến:                           250 ms
Ngân sách còn cho attempt + phản hồi:     100 ms
~~~

Trong trường hợp này, **thử lại với request timeout 1 giây** không đáp ứng được deadline 2 giây của caller. Một retry dù technically idempotent vẫn có thể là quyết định sai vì tạo thêm tải khi người dùng không còn nhận được kết quả.

### 7.2. DriverTimeout không biết mutation đã áp dụng chưa

Với **INSERT**, **UPDATE**, **DELETE**, **LWT** hoặc counter, khi driver timeout:

- Request có thể chưa tới coordinator, đang chờ pool, hoặc đã tới server và được xử lý.
- Coordinator có thể đã gửi tới một số replica.
- Phản hồi có thể mất trên đường về.
- Caller có thể đã hủy nhưng mutation tiếp tục ở server.

**Outcome ghi có thể UNKNOWN.** Không dùng “driver timeout” làm điều kiện tự động tạo request ID mới hay cộng counter lần nữa.

### 7.3. First-page timeout khác full-result timeout

Một **executeAsync** trả **AsyncResultSet** cho trang đầu. Với query phân trang, các trang sau được lấy bằng **fetchNextPage()**. Thời gian đọc 10 trang là **tổng quá trình**, không chỉ 2 giây cấu hình cho một request tới trang đầu.

Bài toán điều tra cần hỏi:

- Timeout xảy ra ở **trang đầu** hay trang thứ N?
- Có page nào trả dữ liệu trước lỗi?
- Kết quả đã gửi downstream có side effect chưa?
- Pipeline có tổng deadline, pagination state và giới hạn demand không?
- Service có trả **partial results** mà lại báo complete không?

Không retry toàn query nhiều trang từ đầu nếu các trang trước đã phát event/ghi sink mà chưa có idempotency/checkpoint.

## 8. RF/DC, consistency và data model ảnh hưởng lỗi thế nào?

### 8.1. Cùng RF = 3, lỗi trả về phụ thuộc CL

Giả sử keyspace dùng **NetworkTopologyStrategy** và **RF = 3** ở dc1:

| Điều kiện | LOCAL_ONE | LOCAL_QUORUM |
|---|---|---|
| Ba replica khỏe, đủ nhanh | Thường nhận sớm sau một phản hồi | Cần đủ quorum local (thường 2/3) |
| Một replica chậm | Có thể ít ảnh hưởng nếu replica khác nhanh | Vẫn có thể thành công nếu hai replica đủ nhanh |
| Hai replica chậm/unreachable | Có thể có lúc thành công nếu một replica còn phục vụ | Có thể timeout/Unavailable tùy điều kiện |
| Node UP nhưng disk/GC nghẽn | Có thể timeout | Có thể timeout dù RF vẫn đủ trên giấy |

Đây là **mô hình đơn giản hóa**; chi tiết read/write, speculative retry và node failures cần được đối chiếu telemetry thực. CL dùng trong API là **hợp đồng nhất quán**, không phải nút chỉnh performance tùy tiện khi incident.

### 8.2. Query không bind đủ partition key sẽ gây hậu quả khác

Giả sử bảng:

~~~sql
-- Chỉ thực hiện trên lab có đủ ba replica trong dc1.
CREATE KEYSPACE IF NOT EXISTS diag_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS diag_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);
~~~

Một query hợp lệ theo access pattern:

~~~sql
SELECT happened_at, event_id, payload
FROM diag_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT ?;
~~~

**Đừng thêm ALLOW FILTERING** để query thiếu partition key “chạy được” rồi sửa bằng tăng timeout. Cần bảng theo truy vấn, index thích hợp (sau review version/cardinality) hoặc mô hình bucket/shard. Một query scan lớn, partition có tombstone hoặc collection lớn có thể làm coordinator/replica chậm rồi dẫn tới DriverTimeout/ReadTimeout.

### 8.3. Hot partition có thể khiến chỉ một nhóm node lỗi

Nếu phần lớn traffic dồn vào **một tenant_id + event_day**, các replica của token range đó chịu tải lớn dù phần còn lại cluster rất rảnh. AllNodesFailed chỉ hiện một vài coordinator/attempt errors hoặc DriverTimeout tăng theo query shape; cần đo:

- Request rate theo **loại truy vấn / nhóm hot keys**.
- Partition size/row count/tombstones, page size và số SSTables.
- Node/token ownership, disk/GC/pending compaction.
- CL và coordinator routes.
- Retry amplification khi query nóng đã chậm.

Giải pháp có thể là **bucketing, sharding hoặc thay query design**, không phải tự tăng pool/timeout vô hạn.

### 8.4. Repair, compaction, bootstrap và backup gây nhiễu

Các công việc nền có thể tranh **disk read/write, network, CPU và memory** với CQL:

- **Repair** đọc/đối soát SSTables và có thể stream dữ liệu giữa replica.
- **Compaction** đọc/ghi SSTable và xử lý tombstones.
- **Bootstrap/streaming** di chuyển SSTables khi topology thay đổi.
- **Backup copy** đọc nhiều SSTables, nén/mã hóa và upload ngoài cluster.

Nếu timeout tăng đúng thời điểm maintenance, xem metric timeline để kiểm chứng thay vì khẳng định ngay quan hệ nhân quả. **Không chạy repair để “chữa DriverTimeout”**; repair bản thân có thể tạo thêm I/O và không khắc phục DNS/TLS/connection pool.

## 9. Runbook phân loại trong 5 phút đầu

~~~mermaid
flowchart TD
    A["Java operation thất bại"] --> B{"DriverTimeout hay AllNodesFailed?"}
    B -->|DriverTimeout| C["Đo deadline, admission/pool, coordinator latency"]
    B -->|AllNodesFailed| D["getAllErrors(): per-node causes"]
    B -->|Server timeout/failure| E["CL, RF/DC, required/received, replica health"]
    D --> F{"Các nút có cùng cause?"}
    F -->|DNS/TLS/Auth/Port| G["Sửa cấu hình/secret/network có kiểm soát"]
    F -->|Khác nhau/transport| H["Điều tra per-node network, pool, disk, JVM"]
    C --> I["So caller/driver/server timeouts và retries"]
    E --> J["So coordinator/replica, partition key, load"]
    G --> K["Verify trên staging/canary"]
    H --> K
    I --> K
    J --> K
    K --> L{"Correctness + SLO đã đạt?"}
    L -->|Chưa| M["PAUSE/ESCALATE; không retry mù"]
    L -->|Rồi| N["Mở traffic dần, theo dõi"]
~~~

### 9.1. Trước tiên: xác định phạm vi

1. **Khi nào** bắt đầu, sau deploy/cert rotation/maintenance hay tăng traffic?
2. Bao nhiêu **logical requests** thất bại, bao nhiêu retries/physical attempts?
3. Chỉ **một service/pod/region/DC** hay mọi client?
4. Thất bại lúc **CqlSession khởi tạo** hay lúc execute CQL?
5. Lỗi chỉ ở **một query shape/tenant** hay mọi truy vấn?
6. Lỗi sync/async nào đang bị **CompletionException** bọc?
7. Server logs/metrics có ReadTimeout, WriteTimeout, Overloaded hoặc replica issue tương ứng không?
8. Có dữ liệu ghi **unknown outcome** cần đối soát và bảo vệ không?

### 9.2. Nếu lỗi ở CqlSession startup

Tập trung vào:

- Contact points, DNS, CQL port 9042, service/network policy.
- **local datacenter** chính xác; phiên bản driver yêu cầu DC phù hợp.
- TLS truststore/certificate chain, hostname verification, mTLS.
- Authentication secrets/role/password và cách được inject vào app.
- Protocol version/driver compatibility, yêu cầu proxy/cloud bundle.
- Connection initialization và node logs.

**Đừng sửa CQL query hoặc tăng page size** khi session còn chưa kết nối được cluster.

### 9.3. Nếu lỗi sau khi session đã chạy

Tập trung vào:

- Query shape, partition key và routing key.
- Driver pool/in-flight, số instances/connection concurrency.
- Coordinator/replica health, RF/CL, DC routing.
- Compaction, repair, backup, disk, GC, network.
- Request timeout/HTTP deadline và retry policy.
- Khả năng một node bị lỗi riêng trong getAllErrors.

### 9.4. Tách các nhánh xử lý

| Quan sát chính | Hướng hành động |
|---|---|
| Tất cả node causes là **TLS certificate expired** | Xử lý chứng chỉ/truststore, kiểm tra rollout; không giảm bảo mật |
| Một node bị refused, node khác reachable | Kiểm tra listener/network/node đó; giữ traffic qua node khỏe theo policy |
| Hầu hết errors là pool saturation | Giảm incoming concurrency, đo latency và pool/connection; tránh retry storm |
| Server ReadTimeout tăng ở vài hot partitions | Chẩn đoán SSTable/tombstone/partition/data model và CL |
| Server Unavailable sau node DOWN | Khôi phục quorum/topology, không hạ CL ngoài hợp đồng |
| DriverTimeout trong khi server metrics bình thường | Kiểm tra client queue/CPU/GC/network/connection/timeout layers |
| Vừa xảy ra schema/driver upgrade | Kiểm tra version matrix, schema agreement, contact points, protocol/codec |
| WriteTimeout với tiền hoặc đơn hàng | Ghi UNKNOWN, đối soát theo business request ID, không tạo ghi mới tùy tiện |

## 10. Java Driver 4.x: phân loại lỗi đồng bộ và bất đồng bộ

Một lớp chẩn đoán tốt cần: **unwrap** CompletionException/ExecutionException, phân loại DriverTimeout/AllNodesFailed/server errors, đọc **getAllErrors()** khi có AllNodesFailed, giữ outcome ghi chưa rõ và log **query shape/correlation ID** thay vì dữ liệu bind nhạy cảm.

### 10.1. Bộ phân loại nguyên nhân

~~~java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;
import com.datastax.oss.driver.api.core.servererrors.ReadFailureException;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteFailureException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

public final class CassandraFailureClassifier {
    private CassandraFailureClassifier() {}

    public enum Kind {
        ALL_NODES_FAILED, DRIVER_TIMEOUT,
        SERVER_READ_TIMEOUT, SERVER_WRITE_TIMEOUT,
        SERVER_READ_FAILURE, SERVER_WRITE_FAILURE,
        SERVER_UNAVAILABLE, SERVER_OVERLOADED, OTHER
    }

    public static Throwable unwrap(Throwable t) {
        while ((t instanceof CompletionException
                || t instanceof ExecutionException)
                && t.getCause() != null) {
            t = t.getCause();
        }
        return t;
    }

    public static Kind classify(Throwable error) {
        Throwable cause = unwrap(error);
        if (cause instanceof AllNodesFailedException) {
            return Kind.ALL_NODES_FAILED;
        }
        if (cause instanceof DriverTimeoutException) {
            return Kind.DRIVER_TIMEOUT;
        }
        if (cause instanceof ReadTimeoutException) {
            return Kind.SERVER_READ_TIMEOUT;
        }
        if (cause instanceof WriteTimeoutException) {
            return Kind.SERVER_WRITE_TIMEOUT;
        }
        if (cause instanceof ReadFailureException) {
            return Kind.SERVER_READ_FAILURE;
        }
        if (cause instanceof WriteFailureException) {
            return Kind.SERVER_WRITE_FAILURE;
        }
        if (cause instanceof UnavailableException) {
            return Kind.SERVER_UNAVAILABLE;
        }
        if (cause instanceof OverloadedException) {
            return Kind.SERVER_OVERLOADED;
        }
        return Kind.OTHER;
    }

    public static void diagnose(Throwable error) {
        Throwable root = unwrap(error);
        System.err.println("failureKind=" + classify(root));
        if (root instanceof AllNodesFailedException) {
            AllNodesFailureInspector.inspect(
                (AllNodesFailedException) root);
        }
        System.err.println(
            "causeClasses=" + CauseSummary.classChain(root));
    }
}
~~~

Đoạn này dùng các class Java Driver 4.x thường gặp. Khi pin thư viện cụ thể, cần **compile** và đối chiếu package/class với dependency thật. Những lỗi khác (authentication, invalid query, codec, connection, cancellation) thuộc nhánh OTHER; service thực tế nên mở rộng taxonomy bằng class và cause chain cụ thể. Không tạo một chính sách retry chỉ dựa vào enum phân loại trên.

### 10.2. Đồng bộ: phân loại mà không nuốt exception

~~~java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class ReadDiagnostics {
    private final CqlSession session;
    private final PreparedStatement select;

    public ReadDiagnostics(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT happened_at, event_id, payload " +
            "FROM diag_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? LIMIT ?");
    }

    public ResultSet read(UUID tenantId, LocalDate day) {
        BoundStatement statement = select
            .bind(tenantId, day, 20)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        try {
            return session.execute(statement);
        } catch (RuntimeException error) {
            CassandraFailureClassifier.diagnose(error);
            throw error;
        }
    }
}
~~~

**Session và prepared statements** nên được tái sử dụng theo lifecycle của service, không tạo một CqlSession mới cho mỗi HTTP request. Mã ví dụ giả định session đã được cấu hình TLS/auth/contact points/local DC đúng; không log tenantId và payload thật.

### 10.3. Async: không chuyển timeout thành empty result

~~~java
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class AsyncReadDiagnostics {
    private final CqlSession session;
    private final PreparedStatement select;

    public AsyncReadDiagnostics(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT event_id, payload " +
            "FROM diag_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? LIMIT ?");
    }

    public CompletionStage<AsyncResultSet> read(
            UUID tenantId, LocalDate day) {
        BoundStatement query = select
            .bind(tenantId, day, 50)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        return session.executeAsync(query)
            .whenComplete((page, error) -> {
                if (error != null) {
                    CassandraFailureClassifier.diagnose(error);
                }
            });
    }
}
~~~

**whenComplete** chỉ quan sát; lỗi vẫn truyền qua stage. Tránh:

~~~java
// SAI: null bị caller hiểu là không có dữ liệu.
return session.executeAsync(query)
    .exceptionally(error -> null);
~~~

Nếu query nhiều trang, executeAsync trả **trang đầu**; lỗi khi gọi **fetchNextPage()** cần được ghi nhận với page index và toàn pipeline. Không chỉ đo first-page latency mà kết luận mọi dữ liệu đã được đọc.

### 10.4. Thời hạn cho từng lớp workload

- Interactive point read: deadline từ HTTP caller, bao gồm admission, driver và chuyển kết quả.
- Query paging: tổng deadline và kiểm soát demand/chặng downstream; không đặt timer mới cho mỗi trang rồi hứa sẽ kết thúc đúng hạn.
- LWT: tính thêm serial consensus và CAS contention; ghi regular/serial CL.
- DML write: xử lý **UNKNOWN** sau timeout trước khi retry.
- Background job: chia thành đơn vị có checkpoint, không giữ HTTP future hàng giờ.
- Migration/bootstrap/backup: có runbook và monitoring riêng, không sửa bằng tăng timeout của API.

## 11. Metric và lệnh quan sát xác minh nguyên nhân

### 11.1. Lệnh chỉ đọc

Trên node được cấp quyền, đối chiếu cú pháp của phiên bản Cassandra đang chạy:

~~~bash
# Trạng thái node và DC/rack/token.
nodetool status

# Thông tin node và bộ nhớ.
nodetool info

# Pending/dropped messages, thread pools.
nodetool tpstats

# Compaction và backlog SSTable.
nodetool compactionstats

# Streaming/network tasks khi version hỗ trợ.
nodetool netstats

# Thống kê bảng liên quan workload.
nodetool tablestats diag_lab.events_by_tenant_day

# Partition size/row histogram theo phiên bản.
nodetool tablehistograms diag_lab events_by_tenant_day
~~~

Những lệnh này không thay thế metric của **driver, client CPU/GC, OS disk latency/network và server JMX/Prometheus**. Không chạy **repair, cleanup, rebuild, decommission hoặc thay RF** như phản xạ chữa timeout; những thao tác đó thay tải/topology, cần runbook và approval.

### 11.2. Metadata driver có giới hạn

**session.getMetadata()** cho thông tin cluster mà session đã khám phá, nhưng metadata có thể chưa cập nhật ngay sau topology change, một node được biết không có nghĩa connection pool tới node đó luôn usable. Khi CqlSession còn **chưa build được**, không có metadata session đáng dùng; phải bắt đầu với contact points, DNS/TLS/auth và AllNodesFailed causes của startup.

### 11.3. Gắn metric theo tầng

| Tầng | Tín hiệu | Câu hỏi |
|---|---|---|
| **HTTP/gRPC** | Offered/completed RPS, p95/p99, 5xx, deadline exceeded | Caller thấy gì? |
| **Application** | Active permits, admission queue, rejection, retries | Có gửi request tới driver chưa? |
| **Driver** | Pool usage, in-flight, timeouts, retries/speculation, coordinator | Đang chờ connection hay server? |
| **Server coordinator** | Read/write latency, timeouts, overload | Request có tới coordinator không? |
| **Replica** | Local latency, pending/dropped, RF/CL, GC/disk | Replica nào không phản hồi kịp? |
| **Storage/JVM** | Disk await, SSTables, compaction, repair, heap/native, GC | Có resource pressure/tombstone? |
| **Correctness** | Missing/duplicate event, request ID/version | Retry hoặc timeout có làm sai dữ liệu? |

**DriverTimeout** có thể xảy ra khi server ReadTimeout counters không tăng nếu request chưa tới coordinator. Ngược lại, server ReadTimeout tăng cùng disk await replica có thể là bằng chứng read path chậm. Cần **timeline và request correlation** để phân biệt.

### 11.4. Log có cấu trúc và hạn chế lộ dữ liệu

~~~json
{
  "event": "cassandra_operation_failed",
  "request_id": "req-lab-084",
  "operation": "events_by_tenant_day.read",
  "failure_kind": "ALL_NODES_FAILED",
  "attempted_nodes_count": 3,
  "per_node_cause_classes": {
    "node-alias-a": ["ConnectException"],
    "node-alias-b": ["SSLHandshakeException"],
    "node-alias-c": ["ConnectionInitException", "TimeoutException"]
  },
  "local_dc": "dc1",
  "consistency": "LOCAL_QUORUM",
  "driver_timeout_ms": 2000,
  "logical_attempt": 1,
  "deadline_remaining_ms": 300,
  "reconciliation_required": false
}
~~~

Đây là mẫu do service định nghĩa, **không phải output mặc định** của Java Driver. Không ghi raw bind values, user ID, credential, certificate private key, token hoặc message chứa secret. Giới hạn số node/causes và log volume trong incident; song vẫn cần tổng hợp được nhóm lỗi hiếm.

## 12. Cấu hình khiến AllNodesFailed dù cluster khỏe

### 12.1. Contact points, DNS và port

**Triệu chứng:** Java app trong Kubernetes báo AllNodesFailed, trong khi đội DBA kết nối thành công từ VM khác.

Kiểm tra:

1. Contact points đã trỏ tới đúng cluster/environment chưa?
2. Pod Java có resolve FQDN đúng không? Có split-horizon DNS hoặc service mesh?
3. Địa chỉ resolve có route được từ namespace/VPC của pod không?
4. CQL native transport port (thường **9042**) có lắng nghe và được network policy cho phép?
5. Có proxy/LB/NAT trả endpoint không phù hợp với driver discovery?
6. Node có thật sự nhận kết nối CQL dù nodetool status vẫn UP?
7. Lỗi ở mọi pods hay chỉ một AZ/region?

**Ping host thành công không chứng minh TCP/TLS/auth CQL thành công.** Kiểm tra từ **vị trí client Java** và đúng đường mạng thực tế.

### 12.2. Local datacenter sai

Driver dùng **local-datacenter** để chọn node theo load balancing policy. Giá trị sai có thể khiến request không tìm thấy node phù hợp dù contact points reachable.

Đối chiếu tên DC thực từ cluster với cấu hình **withLocalDatacenter** hoặc property hiệu lực. Kiểm tra overrides theo environment, contact points, metadata và phiên bản driver.

**Không tự chuyển request sang remote DC** chỉ để “có node” khi ứng dụng có yêu cầu local data residency, LOCAL_QUORUM hoặc độ trễ được cam kết.

### 12.3. TLS và certificate rotation

**Triệu chứng:** Nhiều cause chains có SSLHandshakeException/PKIX.

- Certificate server còn hạn và đúng hostname/SAN không?
- Truststore của JDK/pod có được mount và nạp không?
- mTLS client cert/key có đúng và còn hạn không?
- Protocol/cipher suite có tương thích theo driver/JDK/server?
- Có node chưa nhận certificate mới giữa rolling rotation?

**Không tắt TLS hoặc hostname verification trong production.** Sửa trust/certificate, kiểm tra canary trước khi rollout.

### 12.4. Authentication khác authorization

**Sai secret/credential** có thể gây authentication failure khi mở connection. **Thiếu SELECT/MODIFY** trên table có thể gây authorization failure khi chạy câu CQL.

Không retry vô hạn với cùng secret sai và không nâng role runtime thành superuser để vượt lỗi. Phân tích **authenticator, secret rotation và role grants** theo nguyên tắc least privilege.

### 12.5. Driver/server version hoặc protocol mismatch

Sau upgrade Cassandra/driver/JDK, kiểm tra compatibility matrix, native protocol, TLS/codec, schema migration và tình trạng mixed-version. Không ép protocol ngẫu nhiên hay vô hiệu hóa bảo mật để che lỗi. Nếu dùng một driver khác để kiểm chứng, phải dùng **cùng endpoint/security model** mới so sánh hợp lý.

## 13. Ba tình huống chẩn đoán theo per-node errors

### 13.1. Ca A — AllNodesFailed sau certificate rotation

**Bối cảnh giả định:** một nửa Spring Boot pods mới khởi động fail sau rotation; pod cũ vẫn hoạt động.

~~~text
AllNodesFailedException
  node-a: ConnectionInitException <- SSLHandshakeException <- PKIX...
  node-b: ConnectionInitException <- SSLHandshakeException <- PKIX...
  node-c: ConnectionInitException <- SSLHandshakeException <- PKIX...
~~~

**Hướng điều tra:**

1. So pod cũ/mới về truststore/secret image/volume mount và effective TLS config.
2. Kiểm tra certificate chain/SAN/tình trạng rollout của CQL nodes.
3. Thử cấu hình sửa trên canary, xác minh session build và SELECT chỉ đọc.
4. Giám sát sau rollout; không restart Cassandra toàn cụm khi chưa có bằng chứng.

**Kết luận:** Cause sâu cho thấy lỗi có khả năng ở **trust/TLS của client**, không chứng minh toàn bộ Cassandra nodes DOWN.

### 13.2. Ca B — DriverTimeout tăng đúng lúc repair

**Bối cảnh giả định:** interactive read API đặt driver timeout 2 giây. Repair/compaction trùng thời điểm p99 tăng.

~~~text
Read p99: từ 180 ms lên 2.400 ms
DriverTimeoutException: tăng theo read query
Replica disk await: tăng rõ
Compaction pending: tăng
nodetool status: các node vẫn UN
~~~

**Hướng điều tra:**

1. Gắn timeline errors/p99 với repair phases, disk I/O, GC.
2. Kiểm tra partition keys, tombstones, SSTables, page size/hot tenant.
3. Đo driver pool/in-flight, retries và attempted nodes.
4. Nếu vượt stop gates, điều tiết maintenance theo runbook; không kill node tùy tiện.
5. Đo recovery sau repair và xác minh dữ liệu.

**Kết luận:** Driver timeout là **triệu chứng**. Resource contention/hot partition là **giả thuyết cần chứng cứ**; tăng timeout có thể khiến queue tăng, không cải thiện năng lực server.

### 13.3. Ca C — AllNodesFailed chỉ ở một vùng ứng dụng

**Bối cảnh giả định:** Java service vùng A hoạt động, vùng B mới deploy không tạo được session.

~~~text
region-A: CqlSession connected; SELECT OK
region-B: AllNodesFailed; per-node ConnectTimeout
Cassandra nodes: UN trong DC
~~~

**Hướng điều tra:**

1. So subnet, route table, firewall/security groups giữa A và B.
2. Kiểm tra DNS/contact point resolution từ pod B.
3. Kiểm tra local-datacenter, proxy/address translation, TLS.
4. Không thay RF/CL hoặc chạy repair: những thao tác đó không sửa đường network client.
5. Mở traffic B chỉ khi path đã được sửa và canary CQL thành công.

**Kết luận:** Có bằng chứng về **sự cố đường kết nối từ một vùng**, chưa đủ để gọi cluster-wide outage.

## 14. Retry, idempotency và kết quả ghi chưa xác định

### 14.1. Retry chỉ khi đủ điều kiện

Một request thất bại không có nghĩa **phải retry**. Cần đồng thời:

1. **Thao tác có thể thực thi lại an toàn:** primary key, payload, write timestamp, TTL, LWT và downstream side effects đã được đánh giá.
2. **Lỗi có khả năng tạm thời:** không phải DNS/TLS/auth sai bền vững, syntax error hay schema mismatch.
3. **Còn deadline và retry budget:** trừ backoff và tính cả attempts ở driver, ứng dụng, gateway.
4. **Cluster còn headroom:** không đang Overloaded, queue growth hoặc circuit breaker mở.

~~~mermaid
flowchart TD
    A["Gặp exception"] --> B{"Lỗi cấu hình hoặc không tạm thời?"}
    B -->|Có| X["Không retry; sửa nguyên nhân"]
    B -->|Không| C{"Mutation được chứng minh idempotent?"}
    C -->|Không/chưa rõ| U["UNKNOWN/đối soát, không retry mù"]
    C -->|Có| D{"Còn deadline và retry budget?"}
    D -->|Không| F["Fail fast"]
    D -->|Có| E{"Server quá tải?"}
    E -->|Có| G["Shed load; đợi phục hồi"]
    E -->|Không| H["Backoff + jitter, retry có giới hạn"]
~~~

Đọc SELECT theo partition key **thường có thể retry** trong budget, nhưng kết quả có thể khác do ghi đồng thời/TTL. Ghi INSERT/UPDATE/DELETE, counter, list append và LWT cần đánh giá ngữ nghĩa chặt chẽ hơn.

### 14.2. DriverTimeout sau INSERT có thể gây duplicate event

~~~text
Attempt đầu:
  INSERT event_id = X
  Cassandra có thể đã áp dụng
  Java nhận DriverTimeout

Sai:
  Sinh event_id = Y rồi INSERT lần nữa
  => Có thể tạo hai logical events

Tốt hơn:
  Giữ event_id = X và các bind values ổn định
  Đọc/đối soát theo primary key
  Retry chỉ khi idempotent và còn budget
~~~

Với **counter +1**, **list append** hoặc payment/email, cờ **setIdempotent(true)** không làm thao tác an toàn khi lặp. Cờ false chỉ tác động tới các cơ chế thực thi tự động của driver theo policy; application vẫn phải tránh tự gửi lại không kiểm soát.

### 14.3. LWT false sau retry chưa chứng minh một client khác thắng

Nếu **INSERT ... IF NOT EXISTS** đã được áp dụng ở server nhưng response bị mất, lần retry cùng business key có thể nhận **[applied] = false**. Không coi đó là conflict ngay. Phải đọc lại row và so **request_id, owner/fingerprint và workflow state**. Nếu không thể đọc vì quorum/network vẫn lỗi, giữ **UNKNOWN**.

Regular consistency và serial consistency (**SERIAL / LOCAL_SERIAL**) là hai lựa chọn khác nhau. Không hạ serial policy tùy tiện khi invariant nghiệp vụ yêu cầu phạm vi rộng nhiều DC.

### 14.4. Cờ driver khác retry policy

**setIdempotent(true)** chỉ là metadata chứng nhận thao tác có thể thực thi lại theo đánh giá của application. Nó không tự cấu hình maxAttempts và không đổi bản chất CQL.

~~~text
Một logical HTTP request
  -> HTTP client/gateway retry (nếu có)
    -> Spring service retry (nếu có)
      -> Java Driver retry/speculative execution (nếu có)
        -> Cassandra physical CQL attempts
~~~

Application retry count bằng 0 **không có nghĩa** driver/gateway chưa retry. Đo logical requests, physical attempts, p99, retries và speculative executions. Dùng backoff/jitter và admission; không Thread.sleep trong driver callback/reactive event loop.

### 14.5. Domain outcome phải phân biệt

| Nhóm kết quả | Điều kiện | Xử lý |
|---|---|---|
| **SUCCESS** | Phản hồi hợp lệ, business invariant đạt | Hoàn tất |
| **BUSINESS_FALSE/CONFLICT** | LWT false hoặc quy tắc nghiệp vụ không thỏa có bằng chứng | Trả conflict hoặc xử lý duplicate |
| **UNKNOWN/ERROR** | DriverTimeout/WriteTimeout/reset và trạng thái chưa xác minh | Đối soát, checkpoint hoặc trả lỗi đúng contract |

Không đổi UNKNOWN thành false hoặc “không tìm thấy dữ liệu” chỉ để code ngắn hơn. Với đơn hàng/thanh toán, cần idempotency key và reconciliation trước khi tạo mutation mới.

## 15. Kiểm thử chẩn đoán trên staging

### 15.1. Ma trận thử lỗi có kiểm soát

| Case | Tình huống trong lab | Điều phải quan sát | Không được suy ra |
|---|---|---|---|
| **T0 — baseline** | Session khỏe, SELECT theo khóa | CQL thành công, p95/p99, node health | Production luôn tương tự |
| **T1 — DNS sai** | Contact point test không resolve | DNS/initialization cause theo driver/version | Cluster Cassandra DOWN |
| **T2 — port sai** | CQL endpoint thử dùng port không mở | Refused/connection timeout theo network | Mutation đã tới coordinator |
| **T3 — sai truststore** | Client không tin certificate lab | TLS/PKIX nested cause | Tăng request timeout sẽ chữa |
| **T4 — sai credential** | Secret lab cố ý sai | Authentication failure và đường init | Retry vô hạn là phù hợp |
| **T5 — local DC mismatch** | Cấu hình DC không có/không phù hợp | No eligible node/config issue | Hạ RF/CL để sửa |
| **T6 — pool saturation** | Bounded load cao hơn baseline | Pool/in-flight/queue, driver timeout | Server chắc chắn hỏng |
| **T7 — replica chậm** | Network/disk shaping ở lab RF3 | Client vs server timeout, CL | Node UP thì phải phản hồi nhanh |
| **T8 — hot partition** | Nhiều query cùng bucket/partition | Replica skew, p99, tombstones | Tăng timeout chữa data model |
| **T9 — lost response** | Test adapter che ACK sau write | UNKNOWN, reconciliation cùng ID | Timeout = không ghi |
| **T10 — LWT contention** | N writers cùng IF NOT EXISTS | true, false, unknown khác nhau | false là exception |

**Không cam kết mỗi fault đều tạo đúng một top-level class.** Driver/server có thể trả Authentication, connection-init, AllNodesFailed hoặc timeout tùy thời điểm và phiên bản. Ghi lại **class chain, stage init/execute, node causes và version**.

### 15.2. Ba cổng trước khi thử fault

1. **Isolation:** cluster lab/staging, dữ liệu tổng hợp, khôi phục được, không dùng production.
2. **Safety:** RF/CL phù hợp, capacity, quyền network shaping và change owner, stop gate.
3. **Observability:** Java structured logs, coordinator/replica metrics, disk/GC/network và mốc inject/restore fault.

Nếu fault injection không hoạt động như dự kiến hoặc thiếu telemetry, đánh dấu **INCONCLUSIVE**, không ép test PASS.

### 15.3. JUnit kiểm tra unwrap không mất nguyên nhân

Đây là unit test cho helper ở mục 10; nó không thay thế integration test với Cassandra thật:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

import org.junit.jupiter.api.Test;

public class CassandraFailureClassifierTest {
    @Test
    void keepsRootCauseFromCompletionException() {
        IllegalStateException root =
            new IllegalStateException("simulated");
        CompletionException wrapper =
            new CompletionException(root);

        assertSame(
            root, CassandraFailureClassifier.unwrap(wrapper));
        assertEquals(
            CassandraFailureClassifier.Kind.OTHER,
            CassandraFailureClassifier.classify(wrapper));
    }

    @Test
    void unwrapsNestedFutureExceptions() {
        IllegalArgumentException root =
            new IllegalArgumentException("simulated");
        Throwable wrapped = new ExecutionException(
            new CompletionException(root));

        assertSame(
            root, CassandraFailureClassifier.unwrap(wrapped));
    }
}
~~~

Test xác minh wrapper Java Future không che root cause. Nó **không** sinh DriverTimeoutException thật hoặc xác minh getAllErrors() của driver trên cluster. Để thử những điều đó cần fault lab và kiểm tra per-node errors ghi nhận thực tế.

### 15.4. Simulated lost response khác server WriteTimeout

~~~text
Lost-response test double:
  Cassandra áp dụng write thành công
  Adapter test cố ý không chuyển ACK
  Service nhận UNKNOWN và đối soát bằng request ID

Server WriteTimeout ở lab:
  Coordinator không nhận đủ replica ACK theo CL
  Một số replica có thể đã ghi
  Cần kiểm tra node logs/metrics và dữ liệu sau fault
~~~

Hai case chứng minh các nhánh khác nhau. Không đổi request ID khi retry logical operation chỉ vì attempt trước không có response.

## 16. Giới hạn của AllNodesFailed.getAllErrors()

### 16.1. Khi CqlSession còn chưa được khởi tạo

- Contact points có thể là toàn bộ endpoints driver biết.
- Node metadata có thể thiếu hoặc chưa hoàn chỉnh.
- Không thể dùng session.getMetadata() nếu session build thất bại.
- DNS/TLS/auth errors có thể nằm dưới nhiều lớp wrapper.
- Một số dữ liệu chi tiết chỉ xuất hiện trong driver logs với mức verbosity phù hợp.

### 16.2. Khi session đã hoạt động

- Query plan được tạo theo token awareness, load balancing và local DC.
- Driver có thể thử một phần cluster, không nhất thiết mọi node.
- Một **attempted coordinator** không đồng nhất với **replica** sở hữu partition.
- Retry/speculative execution có thể làm số attempts và thứ tự errors phức tạp.
- Node addresses là metadata hạ tầng, phải hạn chế lộ cho user-facing API.

### 16.3. Giá trị chứng cứ của từng tín hiệu

| Bằng chứng | Cho biết | Không cho biết |
|---|---|---|
| ConnectException trên node A | Attempt không thiết lập TCP tới endpoint A | Tất cả hoạt động ở A đều lỗi |
| SSLHandshakeException trên node B | TLS handshake của attempt lỗi | Cassandra replication bị sai |
| AllNodesFailed có 3 entries | Có errors được ghi cho 3 keys/attempted nodes | Cluster chỉ có 3 node hoặc mọi node DOWN |
| DriverTimeout | Request không hoàn tất đúng hạn ở driver | Server chưa ghi |
| Server WriteTimeout | Không đủ xác nhận theo CL trước timeout | Không replica nào ghi |
| nodetool status UN | Node liveness bình thường theo gossip | CQL p99 luôn đạt SLO |
| Một SELECT thành công | Query đó đọc được tại thời điểm đó | Tất cả tables/DC đều khỏe |

**Không thể lấy getAllErrors() thay thế distributed tracing, server-side logs và application metrics.** Tập lỗi có ý nghĩa trong bối cảnh query plan và trạng thái cluster ở đúng thời điểm.

### 16.4. Bảo vệ dữ liệu khi log

Exception message/stack trace có thể chứa endpoint, CQL string, schema/table hoặc thông tin auth. Telemetry phổ biến nên dùng **cause classes, node aliases, operation IDs**; log forensic đầy đủ phải có quyền truy cập, retention và rate limit phù hợp.

## 17. Mẫu báo cáo incident có thể hành động

~~~yaml
incident:
  id: "cassandra-java-failure-lab-2026-11-21"
  first_seen_at_utc: "<timestamp>"
  environment: "staging-isolated"
  affected_service: "event-api"
  affected_operation: "events_by_tenant_day.read"
versions:
  cassandra: "<exact-version>"
  java_driver: "<exact-version>"
  jdk: "<exact-version>"
topology:
  local_dc: "dc1"
  replication_strategy: "NetworkTopologyStrategy"
  replication_factor_dc1: 3
client:
  contact_point_group: "internal-cql"
  request_timeout_ms: 2000
  regular_consistency: "LOCAL_QUORUM"
  logical_error_rate_percent: "<measured>"
  physical_attempts: "<measured>"
error:
  top_level_kind: "ALL_NODES_FAILED"
  at_stage: "execute"
  attempted_node_causes:
    node_a: ["ConnectException"]
    node_b: ["SSLHandshakeException"]
    node_c: ["ConnectionInitException", "TimeoutException"]
server:
  node_health: "<observed>"
  disk_gc_compaction: "<observed>"
  read_write_timeouts: "<observed>"
assessment:
  hypothesis: "mixed network and TLS failures"
  outcome_ambiguous: false
  confidence: "requires staging validation"
  decision: "PAUSE rollout"
evidence:
  driver_logs: "<controlled-log-reference>"
  node_metrics: "<dashboard-reference>"
  change_record: "<change-id>"
~~~

Đây là **report template**, không phải config Cassandra. Nếu không có metric, ghi NOT_MEASURED chứ không điền số giả. Không xuất secrets, raw bind values, endpoint nhạy cảm hoặc dữ liệu người dùng vào bản báo cáo chia sẻ rộng.

### 17.1. Cần gì trước khi khẳng định root cause?

- Có thời điểm chính xác, phân biệt **session init hay query execute**?
- Có cause chain theo **từng attempted node** trong AllNodesFailed?
- Đã đối chiếu local DC, DNS/contact points, TLS/auth?
- Đã đo client pool, in-flight, retries và deadline?
- Có telemetry RF/CL, replica, disk/GC, compaction/repair?
- Có biết query shape và partition key?
- Write outcome có thể UNKNOWN không? Có idempotency/reconciliation?
- Đã xác minh remediation bằng canary và SLO/correctness chưa?

Một dòng message AllNodesFailed hay DriverTimeout **không đủ để tuyên bố root cause**.

## 18. Runbook theo giai đoạn incident

### 18.1. Phút 0–5: phân loại, khoanh vùng, bảo vệ dữ liệu

1. **Xác nhận symptom:** ứng dụng khởi tạo session fail, query fail, hay HTTP caller timeout?
2. **Thu phiên bản và cấu hình hiệu lực:** Cassandra, driver, JDK, local DC, CL, timeout, retry profiles.
3. **Phân loại top-level exception** và unwrap Future wrappers.
4. Với AllNodesFailed, **dump per-node cause classes + nested cause chains**, kiểm tra có cùng nguyên nhân không.
5. Ghi **mốc thời gian** của deploy, TLS rotation, network change, bootstrap/repair/backup.
6. **Đo phạm vi:** một pod/region/DC hay toàn bộ; một query/partition hay mọi API.
7. Với ghi bị timeout, đánh dấu **UNKNOWN**, tránh sinh request ID mới hoặc retry counter/list append.
8. Nếu có sai dữ liệu/mất quorum hoặc lộ secret, kích hoạt **incident/STOP** theo chính sách.

Không restart cả cluster hoặc tự hạ CL chỉ vì một log thông báo không tìm được node.

### 18.2. Phút 5–15: so cause giữa client và server

| Nếu top-level là | Bước kiểm tra tiếp | Tác vụ không nên làm ngay |
|---|---|---|
| **AllNodesFailed khi startup** | Contact point, DNS, CQL port, local DC, TLS/auth/version | Chạy repair, đổi query CQL |
| **AllNodesFailed khi execute** | getAllErrors, pool/health/route của attempted nodes, retry policy | Kết luận mọi replica DOWN |
| **DriverTimeout** | Client queue/pool, timeout layers, coordinator/replica p99, retry attempts | Chỉ tăng timeout từ 2s lên 20s |
| **Server ReadTimeout** | CL/RF/replica speed, tombstones, partition size, disk/GC | Dùng ALLOW FILTERING để “thử” scan |
| **Server WriteTimeout** | Replica ACKs, type of write, idempotency, data outcome | Tạo mutation mới với ID khác |
| **Unavailable** | Node UP/DOWN, RF/DC, CL, topology/streaming | Hạ CL ngoài hợp đồng |
| **Overloaded** | In-flight/queue, disk, GC, hot partition, traffic burst | Retry tức thì và tăng max attempts |
| **Unknown CQL column** | Schema migration/agreement, code/driver version | Restart hàng loạt nodes |

### 18.3. Phút 15–30: thử giả thuyết có kiểm soát

1. Chỉ thay **một biến** khi có thể: DNS mapping, truststore, rate limit, pool/circuit hoặc data model.
2. Test trên staging hoặc một canary có quyền, không đồng thời sửa nhiều tầng.
3. Đặt **GO/PAUSE/STOP gates** cho error rate, p95/p99, quorum, disk headroom và data correctness.
4. Quan sát **thời gian phục hồi**, không chỉ lỗi biến mất trong một phút.
5. Nếu nguyên nhân là maintenance, phối hợp owner repair/streaming/backup; không tự kill process.
6. Nếu app deploy gây lỗi, đánh giá rollback **ứng dụng** so với schema/data đã thay đổi; không coi rollback code là undo mutation.
7. Lưu raw evidence có kiểm soát, viết timeline và cập nhật giả thuyết khi dữ liệu mới phản bác kết luận đầu tiên.

### 18.4. Sau incident

- **Root cause vs contributing factors:** ví dụ truststore sai là nguyên nhân, retry storm do gateway là yếu tố khuếch đại.
- **Detection gap:** log chỉ top-level message mà không có getAllErrors per-node?
- **Safety gap:** timeout bị đổi thành false hoặc write được retry với ID mới?
- **Capacity gap:** disk/GC/hot partition, pool saturation và p99 đầu tiên đã cảnh báo sớm chưa?
- **Prevention:** integration tests trong staging, certificate rotation rehearsal, retries/limits, schema/version checks.
- **Recovery evidence:** dữ liệu đối soát được, quorum/CL ổn định, p99/throughput đạt SLO.

## 19. Phân biệt lỗi cấu hình, lỗi node riêng và lỗi query

### 19.1. Một bảng phân loại nhanh

~~~text
AllNodesFailed + cùng SSLHandshakeException trên nhiều nodes
    => Ưu tiên kiểm tra client trust/TLS rollout.

AllNodesFailed + cùng ConnectTimeout từ một region
    => Ưu tiên route/firewall/endpoint từ region đó.

AllNodesFailed + một node refused, node khác timeout
    => Kiểm tra từng node; không gộp thành "Cassandra down".

DriverTimeout + app queue cao + server latency bình thường
    => Ưu tiên admission/pool/client CPU/GC/network.

DriverTimeout + server read p99 cao + disk await cao
    => Điều tra read path, hot partition, compaction/repair.

WriteTimeout + RF/CL chưa đủ ACK
    => UNKNOWN outcome, đối soát bằng request ID.

Unavailable + thiếu replica theo CL
    => Topology/quorum; không hạ CL tùy tiện.

InvalidQuery hoặc unknown column
    => Schema/mapping/version; retry thông thường không giúp.
~~~

Đây là **quy tắc định hướng điều tra**, không phải kết luận chắc chắn chỉ bằng tên exception. Cần xem cause chain, thời điểm, cấu hình và metrics.

### 19.2. Khi nào cần hỏi Cassandra owner?

- Node health/token placement/RF/DC không phù hợp.
- Server Read/WriteTimeout, Unavailable hoặc Overloaded tăng.
- Disk/GC/compaction/repair/streaming gây ảnh hưởng tới SLO.
- Nghi dữ liệu mất/sai hoặc query thấy inconsistent results.
- Cần thay topology, RF, repair, compaction, auth hoặc TLS server.

### 19.3. Khi nào cần hỏi Java/platform owner?

- Session build fail do contact point, DNS, TLS/truststore, local DC.
- Driver request timeout tăng nhưng server metrics không cùng chiều.
- Pool/connection setup, circuit breaker, admission, in-flight/queue.
- HTTP client/gateway chồng retries/speculation.
- Async callbacks nuốt exception, deadline propagation sai.
- Spring Boot config/profile hoặc secret rotation không có hiệu lực.

**Hai nhóm phải phối hợp**: driver error có thể bắt nguồn từ server, server error có thể bị client retry làm nặng thêm. Không “đẩy ticket” chỉ dựa vào class name.

## 20. Bài tập tình huống và đáp án gợi ý

### Bài 1 — AllNodesFailed có phải mọi node DOWN?

Ứng dụng báo AllNodesFailed, getAllErrors() cho thấy ba entries; nodetool status cho thấy năm node UP.

**Hỏi:** Có thể khẳng định năm node đều hỏng không?

**Đáp án gợi ý:** Không. Map chứa lỗi của attempted nodes, không phải danh sách tất cả node cluster. Xem query plan, local DC, per-node causes và tình trạng client connections.

### Bài 2 — Nhiều TLS causes giống nhau

Ba causes cùng có SSLHandshakeException và nested PKIX path building failed sau deploy pod mới.

**Hỏi:** Điều tra gì đầu tiên?

**Đáp án:** Truststore/certificate chain/SAN/hostname/JDK TLS của pod mới và tình trạng cert rotation. Không tăng CQL timeout hay tắt xác minh TLS production.

### Bài 3 — DriverTimeout và server ReadTimeout

Driver báo DriverTimeoutException sau 2 giây, nhưng metrics Cassandra không thấy tăng server ReadTimeout, còn app queue wait tăng mạnh.

**Hỏi:** Nguyên nhân có thể ở đâu?

**Đáp án:** Có thể ở admission, pool, driver/client CPU/GC hoặc network trước coordinator. Đối chiếu timeline và attempted node metrics, không suy toàn bộ replica quá chậm.

### Bài 4 — Server WriteTimeout và retry ID mới

Một INSERT event gặp WriteTimeout. Service tạo event_id mới rồi gửi lại.

**Hỏi:** Nguy cơ là gì?

**Đáp án:** Mutation đầu có thể đã áp dụng trên một số replica; ID mới có thể tạo hai event nghiệp vụ. Cần ID ổn định, idempotency contract và đối soát.

### Bài 5 — One node refused

AllNodesFailed chứa ConnectException ở node A, SSLHandshakeException ở B và timeout init ở C.

**Hỏi:** Có thể sửa bằng một tham số request.timeout không?

**Đáp án:** Không có căn cứ. Ba nguyên nhân khác nhau cần kiểm tra listener/network, truststore/cert và init/pool/network tương ứng. Có thể cùng một rollout config gây nhiều triệu chứng nhưng phải chứng minh.

### Bài 6 — Một local DC bị viết sai

Cluster có DC tên DC-EAST-1 nhưng Java cấu hình local DC = east. App báo không có node phù hợp.

**Hỏi:** Sửa gì?

**Đáp án:** Xác minh tên DC thực và effective configuration; sửa cấu hình local-datacenter và canary. Không tự đổi sang remote DC ngoài hợp đồng.

### Bài 7 — Nút UP nhưng p99 xấu

nodetool status UN ở mọi node, nhưng read p99 tăng sau khi bắt đầu repair; disk await và compaction pending cao.

**Hỏi:** Có thể kết luận Cassandra khỏe hoàn toàn?

**Đáp án:** Không. Liveness khác latency/capacity. Phải so repair timeline, disk/GC, partition distribution, CL và throttle/stop gates theo runbook.

### Bài 8 — Retry một counter

Driver timeout sau counter increment. Dev đặt setIdempotent(true) và retry ba lần.

**Hỏi:** Có được phép không?

**Đáp án:** Cờ không biến counter thành idempotent; có thể tăng nhiều lần. Không retry mù, cần mô hình business event/deduplication hoặc đối soát phù hợp.

### Bài 9 — LWT false sau retry

Lần đầu INSERT IF NOT EXISTS có thể được áp dụng nhưng mất response. Lần hai trả [applied]=false.

**Hỏi:** Đây có chắc là conflict với client khác?

**Đáp án:** Không. Có thể chính attempt đầu đã tạo row. Đọc row bằng khóa, so request ID/fingerprint và state; nếu không đọc được giữ UNKNOWN.

### Bài 10 — Top-level CompletionException

Java Future hoàn thành lỗi với CompletionException bọc AllNodesFailedException.

**Hỏi:** Logger nên làm gì?

**Đáp án:** Unwrap Future wrapper, nhận dạng AllNodesFailed, duyệt getAllErrors theo node/cause; giữ root cause và correlation ID. Không log mỗi CompletionException rồi ngừng.

### Bài 11 — Không có nodes trong map

Một log có AllNodesFailed nhưng map per-node rỗng hoặc metadata hạn chế trong startup.

**Hỏi:** Có chứng minh Cassandra không có node nào?

**Đáp án:** Không. Có thể driver chưa khám phá topology; kiểm tra contact points, DNS, TLS/auth và giai đoạn init. Logger phải hỗ trợ map rỗng.

### Bài 12 — Pool saturation vì retry storm

Client có max in-flight thấp, server chậm, gateway và driver đều retry. AllNodesFailed hoặc DriverTimeout tăng.

**Hỏi:** Có nên tăng connections tối đa vô hạn?

**Đáp án:** Không. Đo logical/physical attempts, in-flight/queue, giảm retry và shed load, kiểm tra server/disk/GC. Nới pool phải dựa trên capacity và thử tải.

### Bài 13 — Đổi CL để giảm lỗi

Một endpoint cam kết LOCAL_QUORUM, nhưng incident runbook tự retry ở LOCAL_ONE.

**Hỏi:** Vấn đề gì?

**Đáp án:** Đổi điều kiện xác nhận nhất quán, có thể vi phạm hợp đồng. Phải giữ CL đã duyệt, sửa replica/topology hoặc chấp thuận degradation rõ ràng.

### Bài 14 — Lỗi chỉ ở một query shape

Point reads của bảng A vẫn ổn, nhưng query lịch sử thiếu partition key và scan lớn thường DriverTimeout.

**Hỏi:** Có phải lỗi contact points?

**Đáp án:** Chưa có bằng chứng. Khả năng truy vấn/data model chưa phù hợp, gây read amplification, tombstones/hot partition. Cần thiết kế bảng theo truy vấn, không dùng ALLOW FILTERING và tăng timeout làm giải pháp mặc định.

### Bài 15 — Một SELECT thành công

Một pod mới thực hiện SELECT test thành công qua node A, rồi đội kết luận mọi node, mọi CL và write đều khỏe.

**Hỏi:** Kết luận có đủ không?

**Đáp án:** Không. Một query tại một thời điểm chỉ kiểm chứng đường đó. Cần các test theo RF/DC, CL, write paths, node/error distribution và SLO.

### Bài 16 — Phân trang đọc được 5/10 trang

Java đã nhận năm trang rồi fetchNextPage trang sáu timeout; API vẫn trả HTTP 200 với toàn bộ danh sách đã có.

**Hỏi:** Sai ở đâu?

**Đáp án:** Đánh dấu kết quả thiếu là complete. Cần trạng thái partial/incomplete, tổng deadline, checkpoint/continuation phù hợp và sink idempotent nếu các trang trước có side effects.

## 21. Checklist xử lý DriverTimeout/AllNodesFailed

### 21.1. Nhận diện lỗi và thu bằng chứng

- [ ] Đã phân biệt **DriverTimeoutException**, **AllNodesFailedException** và server Read/WriteTimeout/Failure/Unavailable/Overloaded.
- [ ] Đã unwrap **CompletionException/ExecutionException** trước khi phân loại.
- [ ] Với AllNodesFailed, đã xem **getAllErrors()** theo từng attempted node và **mọi cause** liên quan.
- [ ] Đã đọc nested cause chain đến DNS, TLS, auth, transport hoặc pool thay vì chỉ top-level message.
- [ ] Không kết luận “mọi node DOWN” dựa vào số entries trong AllNodesFailed map.
- [ ] Có timestamp/correlation ID, driver/server/JDK version và query shape.
- [ ] Có phân biệt **CqlSession startup** với **CQL execute**.
- [ ] Không log secrets, raw bind values, định danh khách hàng hoặc endpoint nhạy cảm trong response.

### 21.2. Kiểm tra client/network và cluster

- [ ] Contact points, DNS, CQL port, route, network policy và proxy đã được kiểm tra từ **đúng môi trường Java client**.
- [ ] **local-datacenter** khớp topology/driver configuration hiệu lực.
- [ ] TLS truststore/cert/SAN/hostname, auth/role permissions được kiểm chứng.
- [ ] Connection pool/in-flight/admission/retries/speculative executions được đo.
- [ ] Driver request timeout, connection init, caller deadline và server timeout được phân biệt.
- [ ] Node health, RF/DC, regular CL và serial CL (nếu LWT) được xác minh.
- [ ] Server read/write latency, pending/dropped threads, disk I/O, GC và network được so theo timeline.
- [ ] Đã xem compaction, repair, streaming, backup và các thay đổi deployment cùng thời điểm.
- [ ] Partition key, hot partition, tombstones, page size và CQL query shape đã được đánh giá.
- [ ] Không tự chạy repair/cleanup/rebuild hoặc hạ consistency để che triệu chứng.

### 21.3. Quyết định xử lý và xác nhận phục hồi

- [ ] Write timeout/transport error không bị hiểu thành **chắc chắn chưa ghi**.
- [ ] Request ID, idempotency key, payload/timestamp/version được giữ ổn định qua attempts.
- [ ] Counter/list append/LWT và side effects được review trước khi cho phép retry.
- [ ] Có retry budget, backoff/jitter, deadline end-to-end và load shedding khi Overloaded.
- [ ] Không có retries chồng lớp không kiểm soát ở driver/service/gateway.
- [ ] Có cơ chế đối soát/UNKNOWN khi write outcome không rõ.
- [ ] Đã thử trên staging/canary đúng lỗi bằng evidence, không thử phá production.
- [ ] Có điều kiện PAUSE/STOP/ESCALATE cho data correctness, quorum, p99 và error budget.
- [ ] Sau khi sửa, đã xác minh session startup, CQL read/write được phép, p95/p99 và error rate.
- [ ] Có recovery window, không chỉ một lần SELECT thành công rồi tuyên bố hết incident.
- [ ] Incident report có nguyên nhân, yếu tố khuếch đại, phạm vi tác động và biện pháp ngăn tái diễn.

## 22. Tổng kết

**DriverTimeoutException** là dấu hiệu driver không hoàn tất request trong ngân sách thời gian của nó; **AllNodesFailedException** là lỗi tổng hợp khi driver không thực hiện thành công operation qua các node/endpoints đã được thử. Hai exception này **không tương đương** với **ReadTimeoutException/WriteTimeoutException** mà coordinator Cassandra trả về khi các replica không đáp ứng điều kiện của consistency level.

Với **AllNodesFailed**, giá trị chẩn đoán quan trọng nằm ở **getAllErrors()**: xem **node nào được thử, cause gì xuất hiện, chuỗi nguyên nhân sâu dẫn tới DNS/TCP/TLS/auth/pool hay overload**, và nhớ rằng danh sách này **không phải toàn bộ node cluster**. Với **DriverTimeout**, phải đối chiếu caller deadline, driver queue/pool, network, coordinator/replica p99, RF/CL, hot partition và các tác vụ compaction/repair/streaming. Một node UP không chứng minh query nhanh; một exception timeout không chứng minh mutation chưa được áp dụng.

Cách xử lý bền vững là **phân loại lỗi theo tầng → đọc per-node causes → đối chiếu telemetry client/server → kiểm tra ngữ nghĩa CQL và dữ liệu → quyết định retry/giảm tải/sửa cấu hình có kiểm soát → xác minh lại trên staging/canary**. Chỉ retry khi operation idempotent, còn deadline/budget và cluster đủ năng lực; bảo vệ **UNKNOWN write outcome** bằng request identity và reconciliation.

Như vậy, việc hiểu kiến trúc phân tán, partition key, bảng theo truy vấn, replication/consistency, CQL và Java Driver sẽ giúp xử lý sự cố Cassandra bằng **bằng chứng theo từng nút và từng tầng**, thay vì tăng timeout hoặc restart cả cluster theo cảm tính.
