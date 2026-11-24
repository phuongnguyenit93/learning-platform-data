# Thử nghiệm mất mạng, tiếp tục phiên và chống xử lý lặp

Trong dự án này, bạn xây dựng một client và server RSocket Java, chủ động làm đứt đường truyền TCP, khôi phục connection trong khi phiên RSocket vẫn còn hiệu lực, rồi kiểm chứng rằng một command nghiệp vụ không bị thực thi hai lần khi client không nhận được response.

Bài thực hành ghép ba cơ chế có vai trò khác nhau:

1. **RSocket Resume:** tiếp tục một phiên và các interaction đang chạy sau khi transport bị ngắt tạm thời.
2. **Application replay:** mở phiên mới và đọc lại dữ liệu từ cursor bền vững khi phiên cũ đã hết hạn hoặc không thể resume.
3. **Idempotency/Deduplication:** nhận diện command hoặc event đã xử lý để retry không lặp tác dụng phụ.

RSocket Resume không thay thế inbox, transaction hoặc cursor nghiệp vụ. Nó phục hồi luồng frame của một phiên đang được giữ lại; ứng dụng vẫn phải xử lý trường hợp client không biết transaction đã commit hay chưa, server khởi động lại, hoặc client chủ động gửi lại một command trong phiên mới.

## 1. Kết quả cần đạt

Khi hoàn thành lab, bạn có thể:

- Chạy RSocket server trên TCP và client kết nối qua một TCP proxy.
- Bật Resume ở cả client và server.
- Dùng Toxiproxy để ngắt và mở lại đường truyền mà không dừng hai process.
- Theo dõi một request-stream tiếp tục sau khi transport được khôi phục.
- Tạo tình huống server đã commit command nhưng response không đến client.
- Retry cùng command ID và nhận lại kết quả đã lưu.
- Chứng minh một command chỉ tạo một business effect.
- Phân biệt Resume thành công, Resume bị từ chối và application replay bằng cursor.
- Kiểm tra duplicate event, sequence gap và request dùng lại idempotency key với payload khác.

**Mục tiêu kiểm chứng**

Một command có thể được gửi nhiều lần, nhưng trong cùng một hợp đồng idempotency, business effect chỉ được commit một lần và các lần retry nhận cùng kết quả đã lưu.

## 2. Kiến trúc lab

Client kết nối đến TCP proxy. Proxy chuyển tiếp tới RSocket server. Khi proxy bị tắt, socket bị đóng trong khi client và server vẫn còn chạy. Resume policy thử thiết lập lại transport và tiếp tục phiên bằng resume token cùng frame positions.

~~~mermaid
flowchart LR
    C[Java RSocket Client] <-->|TCP localhost:8666| P[Toxiproxy]
    P <-->|TCP host:7000| S[RSocket Server]
    S --> H[Command Handler]
    S --> E[Durable Event Log]
    H --> I[Command Inbox]
    H --> L[Business Ledger / Balance]
    C --> CI[Client Event Inbox]
    CI --> CU[Committed Cursor]
~~~

Các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| RSocket server | Xử lý request-response và request-stream, bật Resume |
| RSocket client | Giữ RSocket session và subscription, bật Resume |
| Toxiproxy | Ngắt/mở đường TCP để tạo network fault có thể lặp lại |
| Command inbox | Lưu idempotency key, request hash và response đã commit |
| Business ledger | Ghi tác dụng phụ nghiệp vụ với unique key |
| Event log | Lưu event theo partition và sequence để replay |
| Client inbox/cursor | Ghi event đã commit và vị trí liên tục cuối cùng đã xử lý |

Trong lab, server và database tiếp tục hoạt động khi proxy bị tắt. Đây là điều kiện để kiểm tra resumption của một phiên còn tồn tại. Khởi động lại server là một bài thử khác vì state Resume trong bộ nhớ của process có thể mất.

## 3. Chuẩn bị project Java

Tạo hai ứng dụng hoặc hai main class:

- rsocket-resume-server: TCP server ở cổng 7000.
- rsocket-resume-client: kết nối qua proxy ở cổng 8666.

Ví dụ Maven dependencies cho phần RSocket Java:

~~~xml
<dependencies>
    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-core</artifactId>
        <version>1.1.5</version>
    </dependency>
    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-transport-netty</artifactId>
        <version>1.1.5</version>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-core</artifactId>
    </dependency>
</dependencies>
~~~

Nếu project dùng Spring Boot, hãy để dependency management quản lý Reactor và Spring versions; giữ rsocket-core và rsocket-transport-netty cùng một phiên bản tương thích. Nếu dùng R2DBC/PostgreSQL cho inbox và event log, bổ sung spring-boot-starter-data-r2dbc cùng driver R2DBC tương ứng.

Các ví dụ dưới đây dùng raw RSocket Java để thấy rõ cấu hình Resume. Trong ứng dụng Spring, có thể giữ nguyên RSocketServer/RSocketConnector ở tầng transport hoặc cấu hình tương đương qua bean/factory của ứng dụng.

## 4. Cấu hình Resume ở hai đầu

RSocket Resume là tính năng tùy chọn. Client phải yêu cầu Resume trong SETUP và server phải bật hỗ trợ Resume. Chỉ cấu hình một phía là chưa đủ.

Với RSocket Java 1.1.x, Resume có thể được cấu hình bằng session duration và retry policy:

~~~java
import io.rsocket.core.Resume;
import reactor.util.retry.Retry;

import java.time.Duration;

public final class ResumePolicies {

    private ResumePolicies() {}

    public static Resume create() {
        return new Resume()
            .sessionDuration(Duration.ofMinutes(2))
            .retry(Retry.fixedDelay(
                Long.MAX_VALUE,
                Duration.ofMillis(500)
            ));
    }
}
~~~

Ý nghĩa:

- sessionDuration: khoảng thời gian server giữ state cần thiết để client có thể resume sau khi transport bị mất.
- retry: chính sách thử kết nối lại trong quá trình resume.
- Khoảng retry ngắn giúp lab phản hồi nhanh; production cần chọn backoff, giới hạn retry và session duration theo mạng, tải và SLO.

Không bật đồng thời resume(...) và reconnect(...) trên cùng một connector. Hai chế độ này có semantics khác nhau và RSocket Java mô tả chúng là loại trừ lẫn nhau; Resume được ưu tiên nếu cả hai cùng được cấu hình.

### Cấu hình server

~~~java
import io.rsocket.SocketAcceptor;
import io.rsocket.Closeable;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;

public final class ResumeServer {

    public static void main(String[] args) {
        SocketAcceptor acceptor =
            SocketAcceptor.with(new CommandAndEventResponder());

        Closeable server = RSocketServer.create(acceptor)
            .resume(ResumePolicies.create())
            .bindNow(TcpServerTransport.create("0.0.0.0", 7000));

        Runtime.getRuntime().addShutdownHook(
            new Thread(server::dispose));
        server.onClose().block();
    }
}
~~~

CommandAndEventResponder là handler của lab, được triển khai ở các phần sau. Trong Spring Boot, hãy khởi động server trong lifecycle bean và giữ handle trả về từ bind(...) để đóng server khi application context shutdown.

### Cấu hình client

~~~java
import io.rsocket.RSocket;
import io.rsocket.core.RSocketConnector;
import io.rsocket.transport.netty.client.TcpClientTransport;

import java.time.Duration;

RSocket socket = RSocketConnector.create()
    .keepAlive(Duration.ofSeconds(1), Duration.ofSeconds(5))
    .resume(ResumePolicies.create())
    .connect(TcpClientTransport.create("localhost", 8666))
    .block(Duration.ofSeconds(10));
~~~

Trong lab, keepalive ngắn giúp phát hiện đường truyền bị ngắt nhanh. keepAlive(interval, maxLifeTime) khai báo nhịp KEEPALIVE và thời gian tối đa chờ peer. Đây là tham số phát hiện peer mất kết nối, không phải thời gian lưu Resume session. sessionDuration và keepalive có mục đích khác nhau.

Giữ socket đang sống trong suốt bài thực hành. Không gọi socket.dispose() để mô phỏng lỗi mạng; thao tác đó đóng RSocket ở phía client một cách chủ động. Ta sẽ cắt transport ở Toxiproxy để cả hai process giữ nguyên state của phiên.

## 5. Tạo TCP fault proxy bằng Toxiproxy

Toxiproxy là TCP proxy có API để bật/tắt proxy và thêm các network toxic. Nó giúp mô phỏng lỗi có thể lặp lại mà không cần thay đổi code RSocket.

Chạy Toxiproxy bằng Docker Desktop:

~~~powershell
docker run --rm -d --name toxiproxy -p 127.0.0.1:8474:8474 -p 127.0.0.1:8666:8666 ghcr.io/shopify/toxiproxy
~~~

Tạo proxy rsocket lắng nghe cổng 8666, chuyển tiếp đến server ở cổng 7000:

~~~powershell
curl.exe -X POST http://127.0.0.1:8474/proxies -H "Content-Type: application/json" --data-raw '{"name":"rsocket","listen":"0.0.0.0:8666","upstream":"host.docker.internal:7000","enabled":true}'
~~~

host.docker.internal cho phép container Docker Desktop truy cập service đang chạy trên máy host. Nếu server chạy trong một container khác, dùng tên service/container trên network Docker thay cho địa chỉ host này.

Kiểm tra proxy:

~~~powershell
curl.exe http://127.0.0.1:8474/proxies/rsocket
~~~

Tắt đường truyền:

~~~powershell
curl.exe -X POST http://127.0.0.1:8474/proxies/rsocket -H "Content-Type: application/json" --data-raw '{"enabled":false}'
~~~

Mở lại đường truyền:

~~~powershell
curl.exe -X POST http://127.0.0.1:8474/proxies/rsocket -H "Content-Type: application/json" --data-raw '{"enabled":true}'
~~~

Toxiproxy admin API không có authentication mặc định. Lab bind cổng quản trị vào loopback 127.0.0.1; không expose cổng 8474 ra mạng không tin cậy.

## 6. Tạo request-stream có sequence

Server phát event theo partition và sequence. Nguồn event nên là event log bền vững hoặc broker có khả năng đọc lại; Flux.interval chỉ thích hợp để thử stream đơn giản, không đủ cho application replay sau khi process restart.

Ví dụ model:

~~~java
public record Event(
    String eventId,
    String partitionKey,
    long sequence,
    String eventType,
    String body
) {}

public record WatchRequest(
    String partitionKey,
    long afterSequence
) {}
~~~

Repository cung cấp luồng event bắt đầu sau một sequence:

~~~java
public interface EventRepository {

    Flux<Event> watchAfter(
        String partitionKey,
        long afterSequence
    );
}
~~~

Responder xử lý request-stream:

~~~java
@Override
public Flux<Payload> requestStream(Payload payload) {
    WatchRequest request = decodeWatchRequest(
        payload.getDataUtf8()
    );

    return eventRepository.watchAfter(
            request.partitionKey(),
            request.afterSequence()
        )
        .map(event ->
            DefaultPayload.create(encodeEvent(event)));
}
~~~

Trong lab, có thể dùng RSocket.requestStream(...) ở client:

~~~java
Flux<Event> events = socket
    .requestStream(DefaultPayload.create(
        encodeWatchRequest(
            new WatchRequest("orders-01", lastCommittedSequence)
        )
    ))
    .map(payload -> decodeEvent(payload.getDataUtf8()));
~~~

Khi Resume thành công, client giữ subscription hiện tại; RSocket Java phục hồi stream đã bị gián đoạn bằng frame resumption. Không tạo subscription mới ngay khi proxy vừa bị tắt, vì điều đó sẽ biến thử nghiệm thành một request mới thay vì kiểm tra stream đang được resume.

## 7. Thử ngắt mạng và tiếp tục stream

Thực hiện theo thứ tự:

1. Khởi động database, RSocket server và Toxiproxy.
2. Khởi động client, kết nối qua localhost:8666.
3. Mở request-stream cho partition orders-01.
4. Chờ client nhận một số event liên tiếp, ví dụ sequence 1 đến 5.
5. Tắt proxy bằng API ở phần 5.
6. Giữ proxy tắt khoảng 8 giây, lâu hơn keepalive detection trong cấu hình lab.
7. Mở lại proxy trong khi session vẫn nằm trong session duration hai phút.
8. Quan sát log client/server và kiểm tra stream tiếp tục nhận event.

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant P as Toxiproxy
    participant S as RSocket Server
    participant E as Event Log
    C->>P: TCP + SETUP (Resume enabled)
    P->>S: SETUP
    C->>P: REQUEST_STREAM afterSequence=0
    P->>S: REQUEST_STREAM
    S->>E: Read event sequence
    E-->>S: Events 1..5
    S-->>P: PAYLOAD 1..5
    P-->>C: PAYLOAD 1..5
    Note over P,S: Disable proxy, transport is interrupted
    C->>P: Resume retry
    Note over C,S: Server session state remains alive
    Note over P,S: Re-enable proxy
    C->>P: RESUME token + last received position
    P->>S: RESUME
    S-->>P: RESUME_OK
    P-->>C: RESUME_OK
    S-->>C: Resume interrupted stream
~~~

Kết quả mong đợi:

- Client phát hiện transport không còn phản hồi.
- Client thử kết nối lại theo Resume retry policy.
- Khi proxy mở lại, client gửi RESUME thay vì bắt đầu SETUP session mới.
- Server chấp nhận session token và trả RESUME_OK nếu session/frame state còn khả dụng.
- Request-stream đang hoạt động tiếp tục.

Ghi log theo connection label ở mức chẩn đoán, partitionKey, sequence, số lần resume attempt, resume success/rejected và thời gian phục hồi. Không dùng RSocket Stream ID làm cursor nghiệp vụ; Stream ID chỉ định danh interaction trong connection/session.

## 8. Phân biệt Resume với reconnect và replay

Ba cơ chế xử lý ba tình huống khác nhau:

| Cơ chế | Điều kiện | Hành vi | State cần có |
|---|---|---|---|
| RSocket Resume | Server còn giữ session và frame store liên tục | Tiếp tục session/stream đang chạy | Resume token, frame positions và frame store |
| Reconnect | Tạo connection RSocket mới | SETUP session mới; interaction cũ không tự tiếp tục | Client tự quyết định request nào cần gửi lại |
| Application replay | Session cũ không resume được hoặc ứng dụng cần khôi phục dữ liệu | Subscribe/đọc lại event sau cursor đã commit | Event log bền vững, event ID, sequence và cursor |

RSocket Resume là cơ chế protocol. Nó không biến một Flux trong bộ nhớ thành event log bền vững. Nếu server process khởi động lại và frame/session store chỉ nằm trong RAM, session cũ có thể không còn để resume.

Trong trường hợp đó, client cần tạo connection mới, gửi SETUP mới và đọc lại event từ cursor nghiệp vụ. Không bật reconnect() cùng resume() trên một connector để thay cho quyết định replay ở application layer.

## 9. Tạo command có idempotency key

Một command phải có ID ổn định được tạo ở client trước lần gửi đầu tiên. Mọi lần retry của cùng một ý định nghiệp vụ phải dùng lại ID đó.

~~~java
public record CreditCommand(
    UUID commandId,
    UUID accountId,
    long amount,
    String currency
) {}

public record CreditResult(
    UUID commandId,
    long newBalance,
    boolean duplicate
) {}
~~~

Ví dụ client tạo command một lần:

~~~java
CreditCommand command = new CreditCommand(
    UUID.randomUUID(),
    accountId,
    5000,
    "VND"
);

String encodedCommand = encodeCommand(command);
~~~

Giữ commandId và nội dung command cho đến khi có kết quả xác định. Không tạo UUID mới trong mỗi lần retry; nếu làm vậy, server sẽ xem đó là hai command độc lập.

Request-response là lựa chọn phù hợp cho command cần kết quả. Fire-and-forget không trả response payload, vì vậy client không thể dựa vào completion của thao tác gửi để biết business transaction đã commit hay chưa.

## 10. Tạo command inbox trong database

Dùng unique constraint ở database để bảo vệ trước retry đồng thời từ nhiều request hoặc nhiều client instance.

~~~sql
CREATE TABLE command_inbox (
    command_id UUID PRIMARY KEY,
    request_hash CHAR(64) NOT NULL,
    state VARCHAR(16) NOT NULL,
    response_json JSONB,
    committed_at TIMESTAMPTZ
);

CREATE TABLE account_balance (
    account_id UUID PRIMARY KEY,
    balance BIGINT NOT NULL
);

CREATE TABLE account_ledger (
    command_id UUID PRIMARY KEY
        REFERENCES command_inbox(command_id),
    account_id UUID NOT NULL,
    amount BIGINT NOT NULL,
    currency VARCHAR(8) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Ý nghĩa:

- command_id là idempotency key; primary key ngăn cùng command được tạo hai inbox row.
- request_hash ràng buộc ID với nội dung command cụ thể.
- response_json lưu kết quả để trả lại cho retry.
- account_ledger.command_id là unique business effect key thứ hai.
- state chỉ được commit ở trạng thái COMPLETED; row PROCESSING phải được hoàn tất trong cùng transaction trước commit.

Hash phải được tính trên biểu diễn command đã chuẩn hóa, bao gồm các trường nghiệp vụ quan trọng. Không hash trực tiếp JSON byte nếu serializer có thể thay đổi thứ tự property nhưng giữ nguyên dữ liệu logic.

### Ghi inbox và business effect trong cùng transaction

Trình tự trong một transaction:

1. Thử insert command_id và request_hash.
2. Nếu insert thành công, thực hiện business effect.
3. Ghi ledger và tính kết quả.
4. Lưu response_json, chuyển inbox sang COMPLETED.
5. Commit transaction.
6. Chỉ sau khi transaction hoàn tất, handler mới phát response.

SQL insert có thể dùng:

~~~sql
INSERT INTO command_inbox (
    command_id,
    request_hash,
    state
)
VALUES (
    :commandId,
    :requestHash,
    'PROCESSING'
)
ON CONFLICT (command_id) DO NOTHING
RETURNING command_id;
~~~

Nếu câu lệnh trả về một row, request này sở hữu lần xử lý mới. Nếu không có row trả về, đọc inbox hiện có:

~~~sql
SELECT command_id, request_hash, state, response_json
FROM command_inbox
WHERE command_id = :commandId
FOR UPDATE;
~~~

- Nếu hash trùng và state là COMPLETED, trả lại response đã lưu.
- Nếu hash khác, trả lỗi idempotency conflict vì cùng ID đang được dùng cho nội dung khác.
- Không chạy lại business effect khi đã có kết quả hoàn tất.

Với PostgreSQL, thao tác insert có thể phải chờ transaction đang giữ cùng unique key commit hoặc rollback. Sau khi transaction đầu commit, transaction sau đọc được row hoàn chỉnh. Giữ inbox, ledger, balance update và response trong cùng transaction để tránh row PROCESSING bị commit dở dang.

### Service reactive minh họa

Các method repository trong ví dụ đại diện cho thao tác R2DBC. TransactionalOperator bao toàn bộ luồng để inbox và business update cùng commit hoặc rollback.

~~~java
public Mono<CommandOutcome> executeOnce(CreditCommand command) {
    String requestHash = hashCanonical(command);

    return transactionalOperator.transactional(
        inbox.insertIfAbsent(command.commandId(), requestHash)
            .flatMap(inserted -> {
                if (!inserted) {
                    return inbox.findForUpdate(command.commandId())
                        .flatMap(existing -> {
                            if (!existing.requestHash()
                                    .equals(requestHash)) {
                                return Mono.error(
                                    new IdempotencyConflictException(
                                        command.commandId()));
                            }

                            if (!"COMPLETED".equals(existing.state())) {
                                return Mono.error(
                                    new IllegalStateException(
                                        "Inbox row is not complete"));
                            }

                            return Mono.just(
                                new CommandOutcome(
                                    existing.result(),
                                    false));
                        });
                }

                return ledger.insert(command)
                    .then(balance.credit(
                        command.accountId(),
                        command.amount()))
                    .flatMap(newBalance -> {
                        CreditResult result = new CreditResult(
                            command.commandId(),
                            newBalance,
                            false);

                        return inbox.complete(
                                command.commandId(),
                                result)
                            .thenReturn(
                                new CommandOutcome(result, true));
                    });
            })
    );
}
~~~

Đây là skeleton để triển khai với repository của dự án. Cần bảo đảm insertIfAbsent, findForUpdate, ledger, balance và complete dùng cùng connection/transaction do TransactionalOperator quản lý.

## 11. Tạo tình huống server commit nhưng response bị mất

Đây là tình huống quan trọng nhất để kiểm chứng idempotency:

- Client gửi command C1.
- Server ghi inbox, ghi ledger, cập nhật balance và commit.
- Server cố tình trì hoãn response để tạo khoảng thời gian lỗi.
- Client timeout hoặc proxy bị ngắt trước khi nhận response.
- Client gửi lại đúng command C1 với cùng commandId.
- Server phát hiện inbox đã hoàn tất và trả lại response cũ.

Trong handler, trì hoãn response sau khi service đã hoàn tất transaction:

~~~java
@Override
public Mono<Payload> requestResponse(Payload payload) {
    CreditCommand command =
        decodeCommand(payload.getDataUtf8());

    return commandService.executeOnce(command)
        .delayUntil(outcome ->
            outcome.newlyCommitted()
                ? Mono.delay(Duration.ofSeconds(2))
                : Mono.empty()
        )
        .map(outcome ->
            DefaultPayload.create(
                encodeResult(outcome.result())));
}
~~~

executeOnce hoàn tất transaction trước khi delayUntil bắt đầu chờ. Nếu client timeout trong hai giây này, command có thể đã commit dù response chưa đến client. Lần retry có newlyCommitted=false, vì vậy không cần lặp lại khoảng delay mô phỏng.

Đây là fault injection dành cho lab. Xóa delay khi chạy workload thật.

### Retry cùng command ID

~~~java
Mono<CreditResult> sendCredit(
        RSocket socket,
        CreditCommand command) {

    Payload request = DefaultPayload.create(
        encodeCommand(command));

    return socket.requestResponse(request)
        .map(response ->
            decodeCreditResult(response.getDataUtf8()));
}
~~~

Ví dụ lần đầu với timeout ngắn:

~~~java
Mono<CreditResult> firstAttempt =
    sendCredit(socket, command)
        .timeout(Duration.ofMillis(500));
~~~

Khi nhận TimeoutException, chờ đường truyền hoạt động lại nếu đang dùng Toxiproxy, sau đó gọi sendCredit(socket, command) lần nữa với chính object command đã tạo từ đầu. Ví dụ retry có delay để chờ proxy được mở lại:

~~~java
Mono<CreditResult> retried = firstAttempt.onErrorResume(
    TimeoutException.class,
    error -> Mono.delay(Duration.ofSeconds(3))
        .then(sendCredit(socket, command))
);
~~~

Đoạn này giả định socket hiện tại vẫn resume được. Nếu server từ chối Resume hoặc session đã hết hạn, hãy tạo RSocket connection mới trước rồi gửi lại cùng command ID và nội dung. Không sinh command ID mới cho lần retry.

Kết quả mong đợi:

- Lần đầu có thể timeout ở client.
- Server vẫn có thể đã commit ledger và balance.
- Lần thứ hai đọc inbox đã hoàn tất.
- Response lần hai có cùng command ID và kết quả đã lưu.
- Ledger chỉ có một row cho command ID đó.

Không retry vô hạn mọi lỗi. Chỉ retry lỗi tạm thời/không xác định theo policy; lỗi validation, authorization hoặc idempotency conflict cần trả về cho caller.

## 12. Chống dùng lại idempotency key với payload khác

Một client lỗi có thể gửi lại cùng commandId nhưng thay amount hoặc account. Không được trả response cũ một cách mù quáng.

Thêm test:

1. Gửi commandId = X, amount 5000.
2. Gửi lại commandId = X, amount 9000.
3. Server tính request hash khác.
4. Server trả IdempotencyConflictException.
5. Balance và ledger không thay đổi.

Đây là lỗi hợp đồng của client, không phải duplicate hợp lệ. Ghi metric commands.idempotency_conflict và log command ID đã được hash/tokenize theo policy bảo vệ dữ liệu.

## 13. Lưu cursor và chống xử lý lặp cho event stream

Resume giữ interaction đang chạy, nhưng khi phải mở session mới, client cần biết event nào đã được xử lý bền vững. Lưu cursor theo consumer và partition.

~~~sql
CREATE TABLE event_inbox (
    event_id UUID PRIMARY KEY,
    partition_key VARCHAR(120) NOT NULL,
    sequence_no BIGINT NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (partition_key, sequence_no)
);

CREATE TABLE consumer_cursor (
    consumer_name VARCHAR(120) NOT NULL,
    partition_key VARCHAR(120) NOT NULL,
    last_committed_sequence BIGINT NOT NULL,
    PRIMARY KEY (consumer_name, partition_key)
);
~~~

Khi xử lý một event:

1. Mở transaction.
2. Insert event_id, partition, sequence và payload hash.
3. Nếu event đã tồn tại với cùng hash, coi là duplicate và không chạy side effect.
4. Nếu cùng ID hoặc cùng sequence nhưng hash khác, ghi nhận conflict.
5. Kiểm tra sequence tiếp theo đúng bằng last_committed_sequence + 1.
6. Thực hiện business effect.
7. Cập nhật cursor.
8. Commit inbox, business effect và cursor cùng transaction.

Nếu nhận sequence 12 trong khi cursor là 10, không được cập nhật cursor thành 12 ngay. Phải phát hiện gap 11, buffer hoặc yêu cầu replay event còn thiếu theo policy. Cursor luôn là sequence liên tục cuối cùng đã commit, không phải sequence lớn nhất vừa nhận.

### Vì sao lưu last committed thay vì last received?

Giả sử client nhận event sequence 25, sau đó process crash trước khi commit database. Nếu cursor đã tăng lên 25 ngay lúc nhận, reconnect sẽ bắt đầu từ 26 và bỏ mất event chưa xử lý.

Cursor chỉ được tăng sau khi event và tác dụng phụ nghiệp vụ commit trong cùng transaction. Khi replay, event chưa commit sẽ được gửi lại; inbox loại bỏ duplicate nếu event đã commit trước đó.

## 14. Kết hợp Resume với application replay

Luồng khôi phục nên có hai nhánh:

~~~mermaid
flowchart TD
    A[Transport lost] --> B[Try RSocket RESUME]
    B --> C{RESUME_OK?}
    C -->|Yes| D[Continue existing streams]
    C -->|No / session expired| E[Open new SETUP session]
    E --> F[Load last committed cursor]
    F --> G[Subscribe after cursor]
    G --> H[Inbox dedup + sequence check]
    H --> I[Commit event and cursor]
    I --> G
~~~

Khi Resume thành công, stream cũ tiếp tục. Không tự mở một stream mới từ cursor đồng thời với stream đang được resume, nếu không client có thể xử lý cùng event qua hai subscription.

Khi Resume bị từ chối, session hết hạn hoặc server mất state:

1. Tạo connection mới với SETUP mới.
2. Đọc last_committed_sequence từ database của consumer.
3. Gửi request-stream với afterSequence bằng cursor đã commit.
4. Nhận lại event chưa commit.
5. Inbox xử lý duplicate và sequence gap.
6. Tiếp tục cập nhật cursor sau mỗi transaction thành công.

Ví dụ mở một RSocket session mới sau khi session cũ không thể resume:

~~~java
long cursor = cursorRepository
    .lastCommittedSequence("orders-client", "orders-01")
    .block();

RSocket newSocket = RSocketConnector.create()
    .resume(ResumePolicies.create())
    .connect(TcpClientTransport.create("localhost", 8666))
    .block(Duration.ofSeconds(10));

Flux<Payload> replay = newSocket.requestStream(
    DefaultPayload.create(
        encodeWatchRequest(new WatchRequest("orders-01", cursor))));
~~~

Connector mới bắt đầu bằng SETUP và tạo một session mới có bật Resume cho những lần gián đoạn tiếp theo. Ứng dụng phải tự mở stream từ cursor đã commit; session mới không thể khôi phục interaction state của phiên cũ.

RSocket Resume có thể lưu frame state trong bộ nhớ của process. Muốn resume xuyên qua server restart cần triển khai persistent frame store/session management tương thích và xử lý khôi phục session; đó là phần nâng cao. Lab này dùng in-memory session và kiểm tra application replay khi phiên không còn.

## 15. Thực hiện fault test với Toxiproxy

### Test A — Resume một stream đang chạy

1. Khởi động server và client.
2. Mở stream orders-01.
3. Chờ nhận sequence 1 đến 5.
4. Gọi API tắt proxy.
5. Chờ client ghi nhận transport interruption.
6. Mở lại proxy sau khoảng 8 giây, vẫn trong session duration hai phút.
7. Xác minh stream hiện tại tiếp tục mà không tạo subscription mới.

### Test B — Response bị mất sau commit

1. Tạo command với một commandId.
2. Gửi command tới server.
3. Xác minh server log COMMITTED cho command ID.
4. Trong khoảng delay hai giây trước response, tắt proxy.
5. Client timeout vì không nhận response.
6. Mở lại proxy.
7. Gửi lại cùng command ID và cùng nội dung.
8. Xác minh server trả kết quả inbox đã lưu.

Truy vấn kiểm tra:

~~~sql
SELECT command_id, COUNT(*)
FROM account_ledger
GROUP BY command_id
HAVING COUNT(*) > 1;
~~~

Kết quả mong đợi là không có row nào. Kiểm tra command cụ thể:

~~~sql
SELECT
    i.command_id,
    i.state,
    i.response_json,
    COUNT(l.command_id) AS ledger_rows
FROM command_inbox i
LEFT JOIN account_ledger l
    ON l.command_id = i.command_id
WHERE i.command_id = :commandId
GROUP BY i.command_id, i.state, i.response_json;
~~~

Kết quả mong đợi: state = COMPLETED, response tồn tại và ledger_rows = 1.

### Test C — Resume hết hạn hoặc server restart

1. Tắt proxy lâu hơn sessionDuration, hoặc dừng rồi khởi động lại server.
2. Client thử Resume nhưng server không còn session state tương ứng.
3. Ứng dụng tạo connection mới.
4. Client đọc cursor đã commit.
5. Client mở lại stream từ cursor đó.
6. Xác minh event đã commit không tạo business effect lần thứ hai.

## 16. Ma trận kết quả cần quan sát

| Tình huống | Resume | Application replay | Dedup |
|---|---|---|---|
| Transport mất ngắn, server còn sống | Thành công | Không cần mở stream mới | Bảo vệ retry command nếu có |
| Transport mất lâu hơn session duration | Có thể bị từ chối | Bắt đầu từ committed cursor | Loại event/command trùng |
| Server restart, store trong RAM mất | Thường không khôi phục được session cũ | Bắt buộc nếu cần tiếp tục dữ liệu | Ngăn tác dụng phụ lặp |
| Client timeout sau business commit | Có thể connection vẫn còn hoặc được resume | Không phải lúc nào cũng cần | Retry cùng command ID trả kết quả cũ |
| Client gửi cùng ID với payload khác | Không liên quan | Không liên quan | Từ chối conflict |
| Event sequence bị thiếu | Resume không tự tạo event nghiệp vụ đã mất | Replay sequence còn thiếu | Inbox giữ tính duy nhất |

## 17. Quan sát và log khi thử nghiệm

Ghi structured log với các trường có thể đối chiếu:

~~~json
{
  "event": "rsocket.resume.attempt",
  "session_label": "orders-client",
  "transport": "tcp",
  "result": "resume_ok",
  "resume_attempt": 2,
  "elapsed_ms": 1840
}
~~~

Với command:

~~~json
{
  "event": "command.completed",
  "command_id": "f7c9f40e-5e9a-4d52-8b2f-45b5c22f6e90",
  "request_hash_prefix": "a18f7d2c",
  "outcome": "duplicate_response",
  "ledger_effects": 1
}
~~~

Các metric nên có:

- rsocket.resume.attempts
- rsocket.resume.success
- rsocket.resume.rejected
- rsocket.resume.duration
- rsocket.connection.interruptions
- commands.completed
- commands.duplicate
- commands.idempotency_conflict
- events.duplicate
- events.sequence_gap
- events.replay.count
- consumer.last_committed_sequence

Không dùng command ID, event ID, user ID hoặc stream ID làm metric tag vì cardinality có thể tăng không giới hạn. ID cụ thể phù hợp hơn với log/trace có kiểm soát.

## 18. Những lỗi cần tránh

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ bật Resume ở client | Server từ chối hoặc không thể tiếp tục phiên | Bật ở cả hai đầu |
| Tắt server để giả lập network loss | Làm mất luôn in-memory session state | Tắt proxy, giữ server sống |
| Coi Resume là exactly-once business processing | Retry application vẫn có thể lặp tác dụng phụ | Dùng inbox/idempotency key |
| Tạo UUID mới mỗi lần retry | Server xem retry là command mới | Tạo ID trước lần gửi đầu |
| ACK trước khi database commit | Client nghĩ command thành công nhưng dữ liệu chưa bền vững | Chỉ trả response sau transaction |
| Kiểm tra tồn tại rồi insert không có unique constraint | Race condition cho hai request đồng thời | Dùng primary key/unique constraint |
| Dùng cùng ID cho payload khác | Trả nhầm response cũ | So sánh canonical request hash |
| Lưu cursor ngay khi nhận event | Bỏ mất event chưa commit sau crash | Cập nhật cursor trong transaction |
| Resume thành công nhưng mở thêm subscription mới | Hai stream có thể cùng xử lý event | Tiếp tục subscription hiện tại |
| Resume hết hạn nhưng không replay | Mất phần dữ liệu chưa nhận | Mở session mới từ durable cursor |
| Dùng frame store RAM cho yêu cầu sống qua server restart | Không có state để khôi phục session | Dùng persistent store hoặc application replay |

## 19. Bài tập mở rộng

Sau khi lab cơ bản chạy ổn định, thử các thay đổi sau:

1. **Mất mạng hai chiều:** tạo latency toxic cho cả upstream và downstream, rồi quan sát keepalive detection.
2. **Mất response:** chỉ cắt downstream để server có thể nhận request và commit nhưng client không nhận response.
3. **Mất request:** chỉ cắt upstream để kiểm tra command có đến server hay chưa.
4. **Duplicate đồng thời:** gửi cùng command ID từ hai client song song; xác minh chỉ một transaction tạo ledger effect.
5. **Payload conflict:** dùng cùng command ID nhưng thay amount; xác minh conflict.
6. **Sequence gap:** bỏ một event trong test fixture, phát event sequence kế tiếp và kiểm tra consumer không vượt cursor.
7. **Session expiry:** giữ proxy tắt quá session duration, sau đó kiểm tra application replay.
8. **Server restart:** restart server và xác minh client dùng cursor bền vững để mở stream mới.
9. **Outbox:** thay side effect gọi service ngoài bằng transactional outbox; worker gửi event với event ID ổn định và downstream cũng deduplicate.
10. **Bounded frame storage:** tạo traffic lớn trong lúc transport mất để đánh giá dung lượng frame store, memory và thời điểm Resume không còn khả thi.

## 20. Tiêu chí hoàn thành

- [ ] Client và server cùng bật RSocket Resume.
- [ ] Client kết nối qua Toxiproxy tới TCP server.
- [ ] Request-stream tiếp tục sau một lần ngắt mạng ngắn.
- [ ] Log phân biệt resume attempt, success và rejected.
- [ ] Command có idempotency key ổn định.
- [ ] Inbox có unique key và request hash.
- [ ] Inbox, business effect và response được commit trong cùng transaction.
- [ ] Retry sau timeout trả lại kết quả đã lưu.
- [ ] Một command chỉ tạo một ledger effect.
- [ ] Dùng lại command ID với payload khác bị từ chối.
- [ ] Event inbox và cursor được commit cùng business effect.
- [ ] Resume thất bại dẫn tới session mới và replay từ committed cursor.
- [ ] Không dùng RSocket Stream ID làm cursor nghiệp vụ.
- [ ] Test server restart và session expiry không làm mất event đã commit.

## 21. Tổng kết

Lab này chứng minh ba lớp phục hồi cần phối hợp. RSocket Resume giúp tiếp tục session và stream khi transport mất trong thời gian session state còn được giữ. Application replay khôi phục dữ liệu từ event log khi cần tạo session mới. Inbox và idempotency key bảo vệ business effect khi request được gửi lại hoặc response bị mất sau commit.

Điểm cần giữ xuyên suốt là **transport resume không phải bảo đảm exactly-once cho nghiệp vụ**. Hãy dùng Resume để giữ trải nghiệm stream liên tục, dùng cursor bền vững để phát lại dữ liệu, và dùng transaction cùng unique key để biến retry thành thao tác an toàn.

Tài liệu tham khảo:
- [RSocket Java — RSocketServer Javadoc 1.1.5](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java — RSocketConnector Javadoc 1.1.5](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Protocol — Resume Operation](https://github.com/rsocket/rsocket/blob/master/Protocol.md)
- [RSocket Java — Resume configuration example](https://github.com/rsocket/rsocket-java/issues/1009)
- [Spring Framework — RSocket Reference](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Shopify Toxiproxy — README and HTTP API](https://github.com/Shopify/toxiproxy)

