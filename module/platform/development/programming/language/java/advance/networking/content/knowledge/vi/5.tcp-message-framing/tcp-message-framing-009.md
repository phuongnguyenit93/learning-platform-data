# Mã yêu cầu, phản hồi và phát hiện thông điệp trùng khi thử lại trên TCP

## Mục tiêu bài học

Khi giao tiếp qua TCP, ứng dụng thường gửi một **yêu cầu (request)**, chờ **phản hồi (response)**, rồi có thể **thử lại (retry)** nếu hết thời gian chờ hoặc mất kết nối. Vấn đề là: **không nhận được response không có nghĩa server chưa xử lý request**. Nếu cùng một lệnh như “cộng 10 điểm”, “tạo đơn hàng” hoặc “thanh toán” được xử lý hai lần, hậu quả có thể khác rất xa việc gửi lại một yêu cầu đọc dữ liệu.

Sau bài này, bạn có thể:

1. Gắn **mã yêu cầu `requestId`** vào mỗi thao tác logic; dùng **`responseTo`** trong response để biết phản hồi thuộc request nào, kể cả khi nhiều request đang chờ.
2. Phân biệt **TCP retransmission** của các byte trong một kết nối với **application retry** gửi lại thông điệp logic, có thể qua kết nối mới.
3. Xác định thông điệp trùng bằng **mã yêu cầu + phạm vi người gọi + nội dung thao tác**, đồng thời xử lý an toàn request đang chạy, request đã hoàn tất và trường hợp tái dùng mã cho payload khác.
4. Hiểu giới hạn của bộ nhớ tạm, timeout, retry, cache, transaction và lời hứa “exactly once”; lựa chọn cách bảo vệ **tác dụng nghiệp vụ** theo yêu cầu.
5. Chạy ví dụ Java 17+ minh họa một lệnh bị gửi lại qua TCP nhưng chỉ được áp dụng một lần và ví dụ ghép response với request tương ứng.

Phạm vi bài tập trung vào **thông điệp ứng dụng đi qua TCP socket**. Các cơ chế của HTTP như `Idempotency-Key` có thể xây trên nguyên tắc tương tự, nhưng mọi hợp đồng cụ thể phải do server và client cùng thống nhất.

## 1. Trước hết: TCP không cung cấp “mã yêu cầu” cho nghiệp vụ

TCP đưa tới ứng dụng một **luồng byte có thứ tự**, chứ không cung cấp sẵn đối tượng request/response. Một lần gọi `OutputStream.write(...)` **không** tương ứng chắc chắn với một lần `InputStream.read(...)` ở bên kia. Vì vậy ứng dụng cần hai lớp quy ước:

- **Framing:** biết từ byte nào đến byte nào là **một message**, ví dụ prefix độ dài, delimiter hoặc parser giao thức chuẩn.
- **Message envelope:** sau khi tách message, đọc các trường như `type`, `requestId`, `responseTo`, `operation`, `payload` và `status`.

Ví dụ một protocol tự định nghĩa:

```json
{
  "type": "REQUEST",
  "requestId": "req-7f2a",
  "operation": "ADD_CREDIT",
  "payload": {"amount": 10}
}
```

Response ứng với request đó:

```json
{
  "type": "RESPONSE",
  "responseTo": "req-7f2a",
  "status": "OK",
  "result": {"balance": 110}
}
```

Các JSON này minh họa **hình dạng thông điệp**, không phải chuẩn mà Java `Socket` tự hiểu. Muốn trao đổi nhiều JSON trên TCP phải có framing, chẳng hạn **4 byte độ dài + đúng số byte UTF-8** cho mỗi JSON. Chỉ nối các chuỗi JSON rồi gọi `read()` một lần là không đủ để tách message đáng tin cậy.

`requestId` thường do **client tạo một lần cho một thao tác logic**. Mỗi lần retry của **cùng thao tác đó** phải dùng **lại cùng requestId và cùng nội dung ngữ nghĩa**. Khi người dùng thực sự thực hiện thao tác mới, hãy tạo **requestId mới**.

Một response có thể có thêm `responseId` nếu cần nhận diện độc lập từng message phản hồi, nhưng `responseTo` vẫn là trường quan trọng để trả lời câu hỏi “đây là kết quả của request nào?”. Trong giao thức chỉ có một request chờ ở mỗi connection, thứ tự cũng giúp ghép cặp; tuy nhiên mã tường minh hỗ trợ retry, logging và nhiều request đang chờ tốt hơn.

### Các mã dễ bị nhầm

| Trường | Ý nghĩa | Dùng để chống xử lý trùng? |
|---|---|---|
| `requestId` | Định danh **một ý định/thao tác logic** của client | **Có thể**, khi server có cơ chế lưu trạng thái theo mã |
| `responseTo` / correlation ID | Chỉ ra request mà response trả lời | Dùng để **ghép cặp**, tự nó chưa ngăn side effect trùng |
| `responseId` (nếu có) | Định danh độc lập của response/message | Có thể phát hiện **response lặp**, không thay cho dedup request |
| TCP sequence number | Đánh số byte ở tầng TCP cho chính kết nối | **Không** phải mã request nghiệp vụ, không bền qua kết nối mới |
| Trace ID / span ID | Theo dõi một luồng xử lý trong log/tracing | **Không** mặc nhiên là idempotency key |
| `Idempotency-Key` trong HTTP | Một khóa client cung cấp theo hợp đồng API | Chỉ có tác dụng nếu server **thực hiện** logic idempotency/dedup |

## 2. Vì sao client phải retry mà vẫn có nguy cơ tạo trùng?

Xét lệnh `ADD_CREDIT(amount=10)` có `requestId=req-001`.

```text
Client                              Server
  │  REQUEST(req-001, ADD 10)          │
  ├───────────────────────────────────►│  Xử lý, số dư +10
  │                                    │  Lưu kết quả req-001 = OK
  │           RESPONSE(req-001, OK)    │
  │   ◄────────────── X ───────────────┤  Client không nhận/thấy response
  │                                    │
  │   Timeout / mất kết nối            │
  │  RETRY(req-001, ADD 10)            │
  ├───────────────────────────────────►│  Thấy req-001 đã xử lý
  │                                    │  Không cộng thêm 10
  │      RESPONSE(req-001, OK)         │
  │ ◄──────────────────────────────────┤  Trả lại kết quả đã lưu
```

Dấu `X` nghĩa là kết quả có thể không tới được hoặc không được ứng dụng client ghi nhận. Có ít nhất ba khả năng sau khi client bị timeout:

- **Request chưa tới server:** thử lại có thể là lần đầu server nhìn thấy request.
- **Request đã tới và còn đang xử lý:** thử lại có thể đến trong lúc request trước **chưa hoàn tất**.
- **Request đã được xử lý thành công nhưng response không tới client:** thử lại có thể yêu cầu **cùng tác dụng nghiệp vụ lần thứ hai**.

Client chỉ thấy “chưa biết kết quả”, không thể suy ra trường hợp nào chỉ từ timeout. Do đó, với thao tác không idempotent như cộng tiền/điểm, **retry tự động an toàn cần hỗ trợ từ server**.

**Phân biệt với TCP retransmission:** TCP có thể truyền lại segment bị mất trong *cùng một kết nối* và tái tạo luồng byte theo thứ tự cho ứng dụng. Việc truyền lại segment ở tầng TCP thường không làm chương trình ứng dụng nhận hai bản sao byte như hai request. Nhưng khi ứng dụng **tự gửi lại nguyên request**, đặc biệt qua kết nối TCP mới, server có thể nhận **hai request hợp lệ và tách biệt**. TCP không gắn hai request ấy thành “cùng một lần xử lý”.

Cũng không thể coi `write()`, `flush()` hoặc TCP ACK là xác nhận **logic nghiệp vụ**. Chúng không chứng minh rằng server đã ghi giao dịch vào cơ sở dữ liệu, đã commit hay đã trả response đúng nghĩa.

## 3. Request ID, response correlation và quy tắc retry

### 3.1. Sinh mã một lần trước vòng retry

Trong Java 17, một cách thông dụng để có mã khó trùng ngẫu nhiên là `UUID.randomUUID()`:

```java
// Đoạn minh họa, đặt trong phương thức thực hiện một thao tác logic.
String requestId = java.util.UUID.randomUUID().toString();
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    // encodeAndSend(requestId, sameOperationAndPayload);
    // Chỉ thử lại theo chính sách của giao thức.
}
```

`maxAttempts` và `encodeAndSend` trong đoạn này là các thành phần giả định của ứng dụng; nó **không phải chương trình độc lập**. Điểm quan trọng là **requestId được tạo BÊN NGOÀI vòng retry**. Sinh ID mới trong mỗi vòng khiến server không nhận ra các lần thử thuộc cùng thao tác.

UUID là một lựa chọn, không phải bắt buộc. Với một protocol khác, có thể dùng ID ngẫu nhiên theo chuẩn nội bộ hoặc bộ đếm được kiểm soát phù hợp. Hãy đặt giới hạn độ dài/định dạng và xử lý va chạm; **ID không phải bí mật hay chứng chỉ quyền truy cập**.

### 3.2. Response phải mang mã để ghép đúng request

Client có thể có bảng request đang chờ:

```text
pending["req-A"] = future/getInventory
pending["req-B"] = future/createOrder

RESPONSE(responseTo="req-B", result=OK)
    -> hoàn thành pending["req-B"]
RESPONSE(responseTo="req-A", result=3 items)
    -> hoàn thành pending["req-A"]
```

Nếu giao thức cho phép xử lý đồng thời, response có thể về **khác thứ tự gửi request**, dù byte trong từng chiều của *một* TCP connection vẫn được chuyển đúng thứ tự. Đây là do server xử lý, enqueue hoặc cách protocol multiplex stream, không phải TCP tự đảo thứ tự byte.

Client phải định nghĩa rõ nếu có response `responseTo` không tồn tại trong `pending`: nó có thể đã bị timeout/xóa, có thể là reply trùng, hoặc ID lạ. Không nên tự đem response ấy áp dụng cho request gần nhất. Mỗi pending request cần deadline và cleanup để tránh rò rỉ bộ nhớ.

### 3.3. Một ý định, nhiều lần thử; ý định mới, mã mới

Hai thao tác có payload giống nhau **không đương nhiên là một thao tác trùng**. Người dùng có thể muốn mua hai món giống nhau hai lần. Không nên dùng **chỉ nội dung payload** làm khóa dedup.

Ngược lại, nếu client retry cùng requestId nhưng đổi amount, target account, method hay nội dung nghiệp vụ, server phải coi đó là **lỗi xung đột**, không coi như request mới. Mã dùng lại phải đại diện một ý định bất biến.

## 4. Server xác định trùng như thế nào?

Một cách thiết kế đơn giản là lưu:

```text
(scope, requestId) -> {
    payloadFingerprint,
    state,
    originalResponse,
    createdAt,
    expiresAt
}
```

`scope` là phạm vi định danh, ví dụ `tenantId + authenticatedPrincipal + operationType`; ý nghĩa chính xác do hợp đồng API quy định. Tránh dùng `requestId` như khóa toàn hệ thống mà bỏ qua tenant/user: ID giống nhau của hai chủ thể độc lập không được gây ảnh hưởng lẫn nhau.

`payloadFingerprint` là dấu vân tay **nội dung ngữ nghĩa cần bất biến**: method/operation, tài nguyên đích, amount, currency, receiver hoặc các trường tạo side effect. Với JSON, hash chuỗi JSON thô có thể xem hai tài liệu tương đương nhưng khác khoảng trắng/thứ tự key là khác nhau; nếu muốn nhận diện theo ngữ nghĩa, cần **canonicalization** rõ ràng và cùng chính sách phía server. Hash không thay thế xác thực hay kiểm tra quyền.

Bảng quyết định:

| Trạng thái trong phạm vi phù hợp | Payload mới | Cách xử lý đúng |
|---|---|---|
| Chưa có `requestId` | Hợp lệ | Đăng ký ID và thực hiện request lần đầu |
| `IN_PROGRESS` | Cùng fingerprint | **Không chạy song song side effect lần hai**; đợi kết quả, trả trạng thái đang xử lý hoặc cho client truy vấn sau |
| `COMPLETED` | Cùng fingerprint | **Trả kết quả đã lưu**, không thực thi nghiệp vụ lần nữa |
| Có cùng `requestId` | Fingerprint khác | Báo `CONFLICT`; không âm thầm sửa hoặc áp dụng như lệnh mới |
| Chưa có ID nhưng payload giống request cũ | Cùng nội dung | Xem là **request mới**, trừ khi nghiệp vụ có quy tắc duy nhất riêng |
| ID hết hạn bị xóa khỏi dedup store | Dù payload giống | Có thể bị xử lý lại; phải công bố cửa sổ retention |

Phân biệt ba loại "trùng":

1. **Duplicate request:** cùng ý định được gửi nhiều lần. Cần dedup **trước side effect** hoặc gắn logic idempotent trong transaction.
2. **Duplicate response:** cùng response được nhìn thấy nhiều lần; client đối chiếu `responseTo` và trạng thái pending/completed, tránh kích hoạt callback hoặc cập nhật UI hai lần.
3. **Hai message cùng nội dung nhưng khác requestId:** có thể là hai ý định hợp lệ. Chỉ business rule như số đơn hàng duy nhất mới quyết định có thực sự trùng về mặt nghiệp vụ.

### Có nên trả nhãn `DUPLICATE`?

Nếu hợp đồng API yêu cầu **retry nhận lại cùng kết quả ban đầu**, server nên lưu và phát lại response gốc (ví dụ `OK, balance=110`). Có thể ghi “replayed=true” vào log/metric hoặc metadata tùy protocol, nhưng không nên đổi một response thành công thành lỗi `DUPLICATE` khiến client hiểu lầm thao tác thất bại. Nếu requestId tái sử dụng với nội dung khác, đó là **xung đột**, nên trả lỗi rõ ràng (trong HTTP có thể dùng `409 Conflict` theo hợp đồng dịch vụ).

## 5. Trạng thái và cuộc đua khi hai bản request tới cùng lúc

Bộ nhớ đệm dạng `if (!map.containsKey(id)) { apply(); map.put(id, result); }` **không an toàn khi nhiều thread**. Hai luồng có thể cùng thấy “chưa có ID” rồi cả hai áp dụng hiệu ứng.

Mô hình trạng thái:

```text
UNKNOWN ── xác nhận quyền + đăng ký duy nhất ──► IN_PROGRESS
                                                   │
                                               xử lý nghiệp vụ
                                                   │
                                     thành công + lưu response
                                                   ▼
                                               COMPLETED
                                               (replay result)

Cùng ID + khác payload ở mọi trạng thái -> CONFLICT
Cùng ID + cùng payload lúc IN_PROGRESS -> WAIT / IN_PROGRESS response
Cùng ID + cùng payload lúc COMPLETED  -> REPLAY original response
```

Quy trình server thực tế nên có **khóa duy nhất** hoặc một cơ chế tạo entry nguyên tử theo `(scope, requestId)` trước khi chạy nghiệp vụ. Không chỉ dựa vào check-then-act.

Một database transaction có thể lưu "đã xử lý requestId" **cùng transaction với side effect** nếu chúng nằm trong **cùng hệ quản trị CSDL và ranh giới giao dịch**. Ví dụ ý tưởng:

```text
BEGIN TRANSACTION
  kiểm tra/đăng ký (scope, requestId) với UNIQUE constraint
  nếu ID đã tồn tại:
      khóa/đọc bản ghi, so fingerprint, trả kết quả đã commit
  nếu là ID mới:
      cập nhật số dư trong cùng transaction
      lưu kết quả phản hồi và trạng thái COMPLETED
COMMIT
```

Đây là **pseudocode về thứ tự và ranh giới nguyên tử**, không phải đoạn SQL có thể copy chạy nguyên văn. Với cạnh tranh thực tế, phải có quy tắc khóa, isolation, wait/retry khi unique constraint va chạm và cách tránh tự trả kết quả chưa commit. Không được thực hiện side effect rồi **mới** ghi ID vào cache trong transaction khác: có thể crash giữa hai bước và retry sẽ cộng lần thứ hai.

Nếu side effect nằm **ngoài** database đó (gọi dịch vụ thanh toán khác, gửi email, publish message...), transaction local không tự làm remote side effect trở thành exactly-once. Cần hợp đồng idempotency của downstream, transactional outbox/inbox, khóa nghiệp vụ, reconciliation hoặc thiết kế bù trừ phù hợp.

### Crash window và khả năng bảo đảm

| Mốc lỗi | Server có thể đã làm gì? | Hệ quả nếu chỉ lưu trong RAM |
|---|---|---|
| Trước khi nhận đủ message | Chưa xử lý | Client có thể retry |
| Đang xử lý, chưa commit | Có thể rollback hoặc chưa rõ phụ thuộc | Không thể đoán từ timeout client |
| Đã commit business effect, chưa gửi response | Side effect đã xảy ra | Restart mất cache → retry có thể thực hiện lại |
| Đã gửi response, client không ghi nhận | Side effect đã xảy ra | Client vẫn retry; server cần phát lại response |
| Đã lưu cùng transaction cả effect và dedup record | Có kết quả bền vững hoặc rollback cùng nhau | Retry cùng ID có thể an toàn **trong phạm vi và thời hạn bảo đảm** |

Không nên hứa "exactly once delivery" cho một hệ thống phân tán chỉ nhờ requestId. Điều có thể thiết kế là **không lặp lại tác dụng nghiệp vụ** cho một khóa đã đăng ký, trong một cửa sổ thời gian và với các side effect có cơ chế nguyên tử/idempotent phù hợp. Việc **message đến** và **business effect chạy** là hai khái niệm cần phân biệt.

## 6. Java 17+: ví dụ TCP retry và dedup chạy được

Ví dụ này dùng **hai đầu socket TCP trên loopback**. Một server xử lý bốn request trên **bốn kết nối khác nhau**, giữ bảng dedup trong `HashMap` để tập trung vào khái niệm. Phép toán giả định là `ADD amount` vào số dư ban đầu 0:

- Request thứ nhất `req-001, ADD 10`: server thực hiện, nhưng client **cố ý bỏ qua kết quả đã nhận** để mô phỏng ứng dụng không ghi nhận reply.
- Retry **cùng `requestId` và cùng payload**: server phát lại response đã lưu, **không cộng thêm 10**.
- Cùng mã nhưng đổi amount thành 20: nhận `CONFLICT`.
- Request mới `req-002, ADD 5`: được áp dụng như một thao tác mới.

**Lưu ý cách mô phỏng:** ví dụ cố ý **không hiển thị** response đầu tiên ở tầng ứng dụng; nó không tạo packet loss thật trên mạng. Kết quả minh họa đúng tình huống “client không biết phản hồi trước”, còn cơ chế server lưu cache là điểm cần quan sát.

Để có ranh giới message rõ ràng, hai phía dùng `DataOutputStream.writeUTF(...)`/`DataInputStream.readUTF(...)` cho hai trường text, tiếp theo `writeInt(...)`/`readInt(...)` cho số tiền. `writeUTF` dùng **modified UTF-8 với tiền tố độ dài 2 byte** riêng của Java, không phải UTF-8 chuẩn không kèm header; chỉ dùng khi hai phía thống nhất đúng protocol này.

**Tệp `RetryDedupTcpDemo.java`:**

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class RetryDedupTcpDemo {
    private static final int REQUEST_COUNT = 4;

    private record Cached(String fingerprint, String response) {}
    private record Stats(int applied, int balance) {}

    private static String send(InetAddress host, int port,
                               String id, String operation, int amount)
            throws IOException {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 3000);
            socket.setSoTimeout(3000);
            DataOutputStream output = new DataOutputStream(socket.getOutputStream());
            DataInputStream input = new DataInputStream(socket.getInputStream());
            output.writeUTF(id);
            output.writeUTF(operation);
            output.writeInt(amount);
            output.flush();
            return input.readUTF();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            listener.setSoTimeout(3000);
            int port = listener.getLocalPort();

            Future<Stats> serverResult = executor.submit(() -> {
                Map<String, Cached> completed = new HashMap<>();
                int applied = 0;
                int balance = 0;

                for (int i = 0; i < REQUEST_COUNT; i++) {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(3000);
                        DataInputStream input =
                                new DataInputStream(peer.getInputStream());
                        DataOutputStream output =
                                new DataOutputStream(peer.getOutputStream());

                        String id = input.readUTF();
                        String operation = input.readUTF();
                        int amount = input.readInt();
                        String fingerprint = operation + ":" + amount;
                        Cached prior = completed.get(id);
                        String response;

                        if (id.isBlank() || id.length() > 80) {
                            response = id + "|INVALID_ID";
                        } else if (prior != null) {
                            response = prior.fingerprint().equals(fingerprint)
                                    ? prior.response() : id + "|CONFLICT";
                        } else if (!operation.equals("ADD")
                                || amount < 1 || amount > 1000) {
                            response = id + "|INVALID";
                        } else {
                            balance += amount;
                            applied++;
                            response = id + "|OK|" + balance;
                            completed.put(id, new Cached(fingerprint, response));
                        }
                        output.writeUTF(response);
                        output.flush();
                    }
                }
                return new Stats(applied, balance);
            });

            send(loopback, port, "req-001", "ADD", 10); // Ignore reply on purpose.
            System.out.println("Initial reply: hidden by simulation");
            System.out.println("Retry reply: "
                    + send(loopback, port, "req-001", "ADD", 10));
            System.out.println("Mismatched payload: "
                    + send(loopback, port, "req-001", "ADD", 20));
            System.out.println("New request: "
                    + send(loopback, port, "req-002", "ADD", 5));

            Stats stats = serverResult.get(5, TimeUnit.SECONDS);
            System.out.println("Applied requests: " + stats.applied());
            System.out.println("Final balance: " + stats.balance());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 RetryDedupTcpDemo.java
java RetryDedupTcpDemo
```

**Stdout đã xác minh khi chạy chương trình:**

```text
Initial reply: hidden by simulation
Retry reply: req-001|OK|10
Mismatched payload: req-001|CONFLICT
New request: req-002|OK|15
Applied requests: 2
Final balance: 15
```

Giải thích:

1. `listener.bind(..., 0)` yêu cầu hệ điều hành cấp **port tạm thời**; server và client chạy cùng chương trình nên không cần nhập port. `InetAddress.getLoopbackAddress()` giới hạn lưu lượng vào máy hiện tại.
2. Mỗi lời gọi `send(...)` tạo **một TCP connection mới**, encode một request theo quy tắc cố định rồi đọc một response bằng `readUTF()`.
3. Server nhận các kết nối **tuần tự trên một thread**. Điều này giúp demo dễ hiểu nhưng **chưa xử lý race giữa nhiều thread**; trong production cần đăng ký key nguyên tử và lưu trạng thái bền.
4. `fingerprint = operation + ":" + amount` chỉ là biểu diễn giản lược cho một protocol có đúng hai trường đơn giản. Không dùng phép nối chuỗi này làm canonical fingerprint của JSON/business payload phức tạp hoặc của nhiều tenant.
5. Lần đầu `req-001` được xử lý: `balance=10`, `applied=1` và cache lưu response `req-001|OK|10`.
6. Lần retry giữ nguyên ID/payload, server lấy **đúng response cũ** từ cache. Số dư không thay đổi.
7. Lần dùng lại `req-001` với `ADD 20` bị từ chối bằng `CONFLICT`. Đây là **sai hợp đồng mã yêu cầu**, không phải một thao tác mới.
8. `req-002` là ý định mới, số dư lên 15. Hai tác dụng nghiệp vụ đã xảy ra, dù server đã nhận bốn message.

**Giới hạn cố ý của ví dụ:** bảng `HashMap` chỉ sống trong JVM, chỉ dùng một thread, không có xác thực, không có lưu trữ ổn định, không có deadline/retention thực, không có transaction và không có retry policy tự động. Restart sẽ mất cache; một client khác có thể giả mạo ID nếu protocol không xác thực. Mã này **không nên dùng nguyên vẹn cho giao dịch tiền thật**. Nó chứng minh nguyên lý: server phải hiểu **mã yêu cầu của ứng dụng** thay vì chỉ nhìn địa chỉ TCP hoặc chuỗi byte.

## 7. Java 17+: ghép phản hồi theo `responseTo` và phát hiện response lặp

Server có thể trả các response khác thứ tự xử lý request nếu giao thức/ứng dụng cho phép nhiều request đang chờ. Bảng `pending` ánh xạ mã yêu cầu tới công việc tương ứng; khi response tới, lookup bằng `responseTo`.

Ví dụ sau mô phỏng ba response đi tới ứng dụng theo thứ tự B, A, B; response B thứ hai là message lặp. **Đây là ví dụ quản lý trạng thái client trong bộ nhớ, không mở socket**; framing và I/O TCP được minh họa ở ví dụ trước.

**Tệp `ResponseCorrelationDemo.java`:**

```java
import java.util.HashMap;
import java.util.Map;

public class ResponseCorrelationDemo {
    private record Response(String responseTo, String result) {}

    public static void main(String[] args) {
        Map<String, String> pending = new HashMap<>();
        pending.put("req-A", "Inventory lookup");
        pending.put("req-B", "Create order");

        Response[] incoming = {
                new Response("req-B", "OK"),
                new Response("req-A", "3 items"),
                new Response("req-B", "OK")
        };

        for (Response response : incoming) {
            String operation = pending.remove(response.responseTo());
            if (operation == null) {
                System.out.println("Unmatched/duplicate: "
                        + response.responseTo());
            } else {
                System.out.println(operation + " <- " + response.result());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 ResponseCorrelationDemo.java
java ResponseCorrelationDemo
```

**Stdout đã xác minh:**

```text
Create order <- OK
Inventory lookup <- 3 items
Unmatched/duplicate: req-B
```

Điều chương trình chứng minh:

- Response mang `responseTo=req-B` có thể hoàn tất công việc B trước khi A hoàn tất.
- Khi đã xóa `req-B` khỏi `pending`, phản hồi khác mang cùng mã **không được tự chuyển sang request A hoặc gây hiệu ứng UI lần hai**.
- Mã không biết chắc response thứ hai là bản trùng hay một thông điệp không hợp lệ, nên log dùng `Unmatched/duplicate`. Trong hệ thống thực, phân biệt trường hợp này bằng lưu một tập ID đã hoàn tất có TTL, kiểm tra người gửi, trạng thái request và hợp đồng protocol.
- Đây là **dedup response tại client**, không thay thế dedup **request tại server**. Bỏ qua phản hồi lặp không ngăn server cộng tiền hai lần nếu request bị thực thi trùng.

## 8. Thiết kế retry an toàn và thời hạn ghi nhớ ID

### 8.1. Chính sách retry phía client

Một chính sách thực tế thường gồm:

1. **Cố định** requestId và payload của *cùng một ý định* trước lần gửi đầu tiên.
2. Chỉ retry các lỗi **có khả năng tạm thời** theo hợp đồng dịch vụ (timeout, mất kết nối, lỗi giới hạn tạm thời hoặc mã phản hồi cho phép retry).
3. Đặt **connect timeout**, **read/request deadline**, **tổng deadline** và số lần thử tối đa; sau deadline phải có trạng thái “chưa biết kết quả” nếu request có thể đã xử lý.
4. Dùng **exponential backoff có jitter** để tránh các client retry đồng loạt. Cân nhắc `Retry-After` khi dịch vụ cung cấp.
5. Khi thấy **response thành công cho cùng requestId**, ngừng retry và trả đúng kết quả. Nếu response báo `IN_PROGRESS`, nên đợi hoặc query trạng thái thay vì tạo requestId khác.
6. Với thao tác không idempotent, chỉ retry tự động khi server có **hợp đồng dedup** đủ mạnh. Nếu không, hãy xác minh trạng thái nghiệp vụ trước khi quyết định thử lại.

Ví dụ lịch backoff **minh họa**, không phải cấu hình bắt buộc: 200 ms, khoảng 400 ms, khoảng 800 ms, cộng jitter nhỏ và giới hạn tổng thời gian. Không nên đặt retry vô hạn vì có thể nhân tải trên server đang gặp sự cố.

Không phải mọi `IOException` hoặc HTTP status đều nên retry. Lỗi validation, credential sai, requestId/payload conflict và thao tác bị từ chối vĩnh viễn thường cần sửa đầu vào. Đôi khi một request đã hoàn tất nhưng client mất kết quả; response bị mất là một **trạng thái không xác định**, không phải bằng chứng thất bại.

### 8.2. TTL và khả năng phát hiện trùng

Dedup record phải được giữ đủ lâu so với **thời gian retry tối đa**, độ trễ hàng đợi, khả năng offline của client và quy tắc nghiệp vụ. Nếu server xóa bản ghi `req-001` sau 10 phút nhưng client gửi lại sau 1 giờ, server có thể coi đó là request **mới** và gây side effect lần hai.

Không có TTL “đúng cho mọi nghiệp vụ”:

- Hành động nhỏ, ít rủi ro có thể dùng retention ngắn và chấp nhận cửa sổ dedup hữu hạn.
- Thanh toán, chuyển tiền hoặc đặt hàng thường cần **business transaction ID duy nhất**/sổ cái, điều tra trạng thái và quy tắc lưu lâu dài hơn cache tạm.
- Hệ thống cần chiến lược dọn dẹp record có giới hạn bộ nhớ/dung lượng, bảo vệ khỏi client sinh ID vô hạn và metric cho trạng thái pending lâu bất thường.

**Không dùng địa chỉ IP + port của client để nhận diện một request trùng:** mỗi lần retry có thể mở connection mới với ephemeral port khác, qua NAT/proxy khác. Một connection cũng có thể mang nhiều request khác nhau. Khóa logic phải nằm ở **tầng ứng dụng**.

### 8.3. Bảo mật và phạm vi sử dụng mã

RequestId do client cung cấp là **dữ liệu không đáng tin cậy**. Server phải:

- Xác thực/ủy quyền mỗi request như bình thường; ID trùng **không được bỏ qua auth**.
- Scope key theo tenant/principal/operation phù hợp để tránh người dùng này truy cập response/khóa của người dùng khác.
- Giới hạn độ dài/định dạng, số lượng request pending và retention để tránh tấn công tiêu tốn tài nguyên.
- So fingerprint của lệnh có side effect; xung đột phải trả lỗi rõ ràng. Không “lấy cache của người khác” khi hai client ngẫu nhiên/chủ ý dùng cùng ID.
- Không ghi bí mật trong ID hoặc trả response cũ có dữ liệu nhạy cảm cho caller chưa được kiểm tra quyền.

Trên TCP thuần, requestId **không** bảo vệ tính toàn vẹn, riêng tư hay danh tính peer. Với truyền thông qua mạng không tin cậy, dùng cơ chế bảo mật phù hợp (TLS và xác thực ở tầng ứng dụng).

## 9. Khi nào cần idempotency tự nhiên, dedup và khóa nghiệp vụ?

**Idempotency** nghĩa là lặp cùng thao tác vẫn cho **tác dụng mong muốn** như một lần thực hiện, theo hợp đồng được xác định. Không phải thao tác nào cũng tự idempotent:

| Thao tác | Thử lại trực tiếp có an toàn? | Cách xử lý cần cân nhắc |
|---|---|---|
| Đọc trạng thái đơn hàng | Thường không gây side effect nghiệp vụ | Vẫn cần deadline và consistency phù hợp |
| “Đặt giá trị cấu hình X = 5” | Có thể idempotent ở hiệu ứng cuối | Cạnh tranh cập nhật/versioning vẫn cần xử lý |
| “Tăng số dư thêm 10” | **Không**; làm hai lần cho +20 | Stable requestId + effect atomically recorded |
| “Tạo order mới” | Thường không; dễ sinh hai order | Client business key hoặc requestId được lưu bền |
| “Gửi email” | Gửi lặp có thể tạo hai email | Outbox/idempotent provider, dedup theo hợp đồng |
| “Thanh toán” | Không được tùy tiện retry | Provider idempotency key, transaction ID và đối soát |

RequestId giúp *nhận diện thao tác*, nhưng khả năng idempotent thật sự còn phụ thuộc **cơ chế lưu khóa và side effect**. Một thao tác `PUT` hoặc gán trạng thái có vẻ idempotent ở kết quả cuối vẫn có thể tạo nhiều bản ghi audit/webhook nếu không thiết kế kỹ.

## 10. Debug và log theo mã yêu cầu

Khi nhận phản ánh “click một lần nhưng có hai đơn hàng”, các log tối thiểu hữu ích:

```text
time | scope/tenant | requestId | operation | payloadFingerprint
     | state | duplicateDecision | responseStatus | businessRecordId
```

Nên có metric: số request mới, số retry có cùng ID, số replay từ cache, số ID conflict, số request `IN_PROGRESS` quá lâu, tỷ lệ timeout, độ trễ hoàn tất và tỷ lệ dedup record hết hạn. Log tránh chứa payload bí mật, credential hay dữ liệu nhạy cảm không cần thiết; dùng correlation/trace ID để nối sự kiện giữa dịch vụ.

Các hiện tượng dễ bị hiểu sai:

| Hiện tượng | Cách đọc đúng |
|---|---|
| Server log hai TCP connections từ hai ephemeral ports | Không biết có phải hai request trùng; kiểm tra `requestId` |
| Client log timeout nhưng server đã có business record | Có thể request hoàn tất và response mất; query theo business/request ID |
| Hai request cùng ID, cùng fingerprint, một đang chạy | Không cho hai worker cùng áp dụng side effect |
| Retry được response gốc `OK` | Server có thể đã xử lý lần đầu; đây là hành vi replay mong muốn |
| Cùng ID nhưng payload khác | Protocol conflict, không tự coi đây là cập nhật request |
| Hai request khác ID, payload giống nhau | Không đủ chứng cứ là duplicate; xem ý định và unique business key |
| Server restart rồi cùng ID tạo thêm record | Dedup chỉ lưu RAM hoặc cửa sổ retention không đủ |
| Client thấy response hai lần | Client phải correlate bằng `responseTo`, không kích hoạt hiệu ứng hai lần |

### Checklist cho một protocol request-response trên TCP

1. **Framing:** header/delimiter/length chuẩn, giới hạn kích thước, xử lý đọc thiếu và EOF.
2. **Identity:** requestId duy nhất trong scope đã định, giữ nguyên cho retry, responseTo khớp request.
3. **Validation:** auth, schema, fingerprint, trường hợp ID trùng nhưng nội dung khác.
4. **Server lifecycle:** atomic registration, xử lý cạnh tranh IN_PROGRESS, lưu kết quả/side effect bền nếu cần.
5. **Client lifecycle:** pending table, timeout/deadline, bounded retry với backoff/jitter, cleanup late response.
6. **Retention/observability:** thời hạn dedup, log requestId, metrics và cách truy vấn trạng thái sau timeout.

## 11. Bài tập suy luận

**Tình huống A:** Client gửi `req-21, ADD 10`, hết thời gian đọc response; client gửi lại **`req-22, ADD 10`**. Server đã thực hiện lệnh thứ nhất. Có thể cộng 20 không?

**Đáp án:** Có, vì hai ID khác nhau được xem là hai ý định. Nếu đây là retry của cùng ý định, phải giữ `req-21`; server cần kiểm tra/lưu ID và side effect theo hợp đồng.

**Tình huống B:** Server nhận hai bản `req-21, ADD 10` gần như đồng thời trên hai kết nối. Chỉ dùng `HashMap.containsKey` rồi `put` có đủ không?

**Đáp án:** Không trong server đa luồng. Cần đăng ký duy nhất nguyên tử hoặc khóa/transaction; nếu không, cả hai worker có thể thấy ID chưa tồn tại và cùng cộng.

**Tình huống C:** Client nhận `responseTo=req-B` trước `responseTo=req-A`, mặc dù gửi A trước B. Có vi phạm thứ tự TCP không?

**Đáp án:** Chưa chắc. Server/protocol có thể gửi response B trước A; TCP vẫn giữ đúng **thứ tự byte thực sự được gửi**. Client phải ghép response theo ID.

**Tình huống D:** Client retry cùng requestId nhưng đổi amount từ 10 thành 20. Server nên phát lại response cũ, cập nhật thành 20, hay báo conflict?

**Đáp án:** Báo **conflict** vì cùng ID được gắn với hai nội dung khác nhau; yêu cầu mới phải có ID mới và được xác nhận như một ý định riêng.

**Tình huống E:** Dedup cache chỉ ở RAM. Server đã commit tăng số dư nhưng crash trước khi gửi response. Sau restart client retry. Có thể tăng hai lần không?

**Đáp án:** Có. RAM mất record dedup. Muốn bảo vệ qua restart, cần lưu ID và effect bền, tốt nhất nguyên tử trong transaction phù hợp hoặc dùng downstream idempotency.

**Tình huống F:** Server dedup và trả lại response gốc đúng, nhưng client nhận response hai lần. Server-side dedup có tự ngăn UI gọi callback hai lần không?

**Đáp án:** Không. Client cần đối chiếu `responseTo`, trạng thái pending/completed và chính sách xử lý late/duplicate response.

**Tình huống G:** Hai khách hàng độc lập tình cờ gửi `req-1`. Dùng chung một cache key toàn cầu có an toàn không?

**Đáp án:** Không. Phải scope key theo tenant/principal/operation phù hợp và xác thực mỗi request. ID không phải khóa ủy quyền.

**Tình huống H:** RequestId trùng bị xóa khỏi cache sau 5 phút nhưng client retry sau 2 giờ. Có thể xem server còn bảo đảm “không trùng” không?

**Đáp án:** Không. Lời hứa dedup chỉ hợp lệ trong **cửa sổ retention** và các ràng buộc được công bố, trừ khi business ID bền vững tiếp tục bảo vệ tác dụng.

## 12. Ghi nhớ

- TCP tự truyền byte có thứ tự; **application protocol mới có request, response và message ID**. TCP retransmission không đồng nghĩa application retry.
- Một thao tác logic có **requestId ổn định** qua mọi retry; response phải mang **responseTo** để ghép đúng tác vụ. Ý định mới phải dùng ID mới.
- Server xử lý request mới, đang chạy, đã hoàn tất và trùng ID khác payload **theo các nhánh khác nhau**. Cùng ID + cùng payload sau `COMPLETED` nên phát lại kết quả gốc mà không áp dụng side effect lần nữa.
- Muốn chống nhân đôi tác dụng qua concurrency/crash, dedup và business effect phải được bảo vệ bằng **đăng ký nguyên tử, trạng thái bền và transaction/idempotency phù hợp**. Cache RAM là minh họa, không phải giải pháp đảm bảo đầy đủ.
- Timeout đồng nghĩa **chưa biết kết quả**, không đồng nghĩa server thất bại. Retry có deadline/backoff và phải tôn trọng hợp đồng idempotency.
- Cả phía server (dedup request) và phía client (correlate response) đều có trách nhiệm riêng.

### Tài liệu Java 17

- [`Socket` — TCP socket và các luồng I/O](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [`ServerSocket` — lắng nghe kết nối](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
- [`DataInputStream` — `readUTF`, `readInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html)
- [`DataOutputStream` — `writeUTF`, `writeInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html)
- [`UUID` — tạo requestId ngẫu nhiên](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html)
