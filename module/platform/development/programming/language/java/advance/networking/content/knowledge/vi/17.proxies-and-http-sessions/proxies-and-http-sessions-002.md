# ProxySelector: lựa chọn proxy theo URI và xử lý connectFailed trong Java 17

## 1. Tình huống: cùng một HttpClient nhưng các URI cần tuyến kết nối khác nhau

Một ứng dụng Java gọi nhiều HTTP API: một endpoint nội bộ trong mạng doanh nghiệp, một đối tác bên ngoài phải đi qua proxy, và một endpoint HTTP công khai cần đi qua proxy khác. Nếu chỉ cấu hình **một proxy cố định** hoặc cho mọi request đi trực tiếp, ứng dụng có thể đi sai tuyến, vi phạm chính sách egress hoặc lỗi kết nối.

`java.net.ProxySelector` là **điểm mở rộng chính sách lựa chọn tuyến**. Nó trả lời câu hỏi:

> Với **URI đích** này, danh sách cách kết nối được đề xuất là gì: proxy HTTP, proxy SOCKS (nếu client/protocol hỗ trợ), hay kết nối trực tiếp?

Với một custom `ProxySelector`, có thể xác định:

- URI thuộc domain nội bộ được phép truy cập trực tiếp → `Proxy.NO_PROXY`.
- URI HTTPS đến dịch vụ đối tác → ưu tiên proxy A, có proxy B dự phòng trong danh sách.
- URI HTTP công khai → chỉ dùng proxy B.
- Khi biết một proxy không thể **thiết lập kết nối**, method `connectFailed(URI, SocketAddress, IOException)` nhận thông tin để cập nhật chính sách ở các lần chọn sau.

**Điểm phân biệt cốt lõi:** `select` trả **đề xuất tuyến kết nối**; nó không tự mở socket, không gửi HTTP request, không thực hiện authentication, không tự xác nhận proxy còn sống. `connectFailed` là **thông báo lỗi thiết lập kết nối đến proxy**, không phải callback cho mọi HTTP response lỗi như `404` hoặc `502`.

Bài này nằm trong phần **Proxy và phiên HTTP**, tập trung vào hợp đồng `ProxySelector` trong Java 17, cách chọn theo URI, nghĩa của danh sách proxy, thông báo thất bại và sự khác nhau giữa chính sách lựa chọn với khả năng failover thực tế của HTTP client.

## 2. Phân biệt `Proxy`, `ProxySelector` và `HttpClient`

| Thành phần | Java API | Trách nhiệm |
|---|---|---|
| **Proxy endpoint** | `java.net.Proxy` | Mô tả **một** cách kết nối: HTTP proxy, SOCKS proxy hoặc DIRECT |
| **Proxy address** | `java.net.SocketAddress`, thường `InetSocketAddress` | Host/IP và port **của proxy**, khác host/port của URI đích |
| **Policy / selector** | `java.net.ProxySelector` | Chọn danh sách `Proxy` theo URI; nhận `connectFailed` để biết proxy không kết nối được |
| **HTTP client** | `java.net.http.HttpClient` | Tạo/kết nối HTTP/TLS, gửi request, nhận response; có thể được gắn `ProxySelector` qua builder |
| **HTTP request** | `java.net.http.HttpRequest` | Method, URI, headers, body publisher và timeout request |
| **Proxy authentication** | `java.net.Authenticator` và chính sách HTTP client | Cung cấp thông tin xác thực cho challenge khi proxy yêu cầu; **khác** việc chọn proxy |
| **HTTP response** | `HttpResponse` | Status, headers và body từ HTTP exchange; không có nghĩa cứ status lỗi thì gọi `connectFailed` |

Một giá trị `Proxy` thường mang:

```java
// Đoạn minh họa, các import java.net.* đã có trong ngữ cảnh.
Proxy corpProxy = new Proxy(
        Proxy.Type.HTTP,
        InetSocketAddress.createUnresolved(
                "proxy.corp.example", 8080));

Proxy direct = Proxy.NO_PROXY;
```

`Proxy.NO_PROXY` biểu diễn **kết nối trực tiếp**. Với direct, `type()` trả `Proxy.Type.DIRECT` và `address()` bằng `null`. Không được ép `proxy.address()` sang `InetSocketAddress` trước khi kiểm tra `type()`.

Một proxy có type `HTTP` không phải URI đích; nó là một **đầu mối trung gian** để HTTP client kết nối trước, rồi thực hiện cơ chế HTTP proxy phù hợp. `Proxy.Type.SOCKS` là một loại khác, có semantics ở tầng socket và mức hỗ trợ khác nhau giữa các HTTP client/handler. Không nên giả định mọi `ProxySelector` consumer đều hỗ trợ mọi loại `Proxy.Type`.

### Sơ đồ tuyến kết nối

```text
App Java
  |
  | HttpRequest.uri() = https://api.partner.example/v1
  v
ProxySelector.select(target URI)
  |
  +--> Proxy A (HTTP proxy at proxy-a.example:8080)
  +--> Proxy B (HTTP proxy at proxy-b.example:8081)
             |
             v
   HTTP client chọn và thử kết nối theo khả năng/contract của nó
             |
       Proxy được kết nối
             |
             v
     Origin api.partner.example
             |
             v
     HTTP response / lỗi I/O
```

**Quan trọng:** danh sách A, B biểu thị **thứ tự ưu tiên của selector**; nó **không hứa** mọi triển khai `HttpClient` đều tự thử lần lượt tất cả proxy, chuyển tiếp mọi request hay gọi `connectFailed` trong mọi tình huống. Tính năng retry/failover thực tế phải kiểm chứng theo client và JDK đang dùng.

## 3. Hợp đồng của `ProxySelector.select(URI)`

Hai phương thức abstract phải cài khi tạo subclass:

```java
// Chữ ký API; đây không phải một class độc lập.
public abstract List<Proxy> select(URI uri);

public abstract void connectFailed(
        URI uri, SocketAddress sa, IOException ioe);
```

### `select` nhận gì?

`URI` mô tả **đích** mà ứng dụng muốn truy cập. Java 17 tài liệu hóa các dạng tiêu biểu:

- `http://host[:port]/...` cho kết nối HTTP.
- `https://host[:port]/...` cho kết nối HTTPS.
- `socket://host:port` trong bối cảnh TCP socket dùng selector thích hợp.

Ví dụ:

```text
http://public.example/status
https://api.partner.example/v1/orders
https://reports.corp.example/dashboard
```

Ở đây `uri.getScheme()` cho `http` hoặc `https`, `uri.getHost()` cho hostname; `uri.getPort()` có thể là `-1` khi không khai báo port. Với chính sách theo path, có thể xem `uri.getPath()`, nhưng phải cân nhắc URL normalization, redirects và việc chọn proxy dựa trên **destination host/scheme** thường rõ ràng hơn.

**Không dùng `URI.toString().contains("corp")` làm chính sách bypass.** Chuỗi đó có thể trùng trong path, query hoặc username giả; ví dụ:

```text
https://attacker.example/download?next=corp.example
```

không phải domain doanh nghiệp. Nên lấy thành phần `getHost`, chuẩn hóa hostname theo quy tắc phù hợp và kiểm tra **đúng host hoặc suffix kèm dấu chấm**. Nếu hỗ trợ Unicode domain, IPv6, trailing dot, IDN hoặc hostname dạng đặc biệt, cần normalize và test kỹ hơn demo.

### `select` trả gì?

`select(uri)` trả `List<Proxy>`, mỗi phần tử là một lựa chọn. Nếu chính sách không dùng proxy, theo API trả **danh sách chứa phần tử direct**:

```java
return List.of(Proxy.NO_PROXY);
```

Không trả `null` hay danh sách rỗng để diễn đạt direct. Nếu muốn ưu tiên một proxy rồi một proxy dự phòng:

```java
return List.of(primaryProxy, backupProxy);
```

Nếu chỉ cho phép proxy, **không thêm `Proxy.NO_PROXY` ở cuối** như một “fallback vô hại”: nó có thể tạo đường kết nối trực tiếp và **bỏ qua chính sách egress**. Một danh sách ứng viên không phải là quy tắc an ninh; client có thể thử/bỏ qua các phần tử theo triển khai.

### Kiểm tra URI đầu vào

Tài liệu Java 17 nói `select` ném `IllegalArgumentException` nếu tham số `null` hoặc không xác định được protocol/host. Với custom selector, có thể:

```java
if (uri == null || uri.getScheme() == null
        || uri.getHost() == null) {
    throw new IllegalArgumentException(
            "Absolute URI with scheme and host required");
}
```

Đừng tự đoán hostname từ phần authority chưa parse đúng. `URI.create("/relative/path")` không có host; nó không phải URI HTTP tuyệt đối đủ để chọn proxy. Với scheme không hỗ trợ, nên có chính sách tường minh (từ chối hoặc delegate cho selector phù hợp), tránh tự trả DIRECT cho mọi scheme lạ.

## 4. `Proxy.Type`, `Proxy.NO_PROXY` và thứ tự ưu tiên

`Proxy.Type` có các loại chính:

| Type | Ý nghĩa | `Proxy.address()` |
|---|---|---|
| `HTTP` | Proxy theo cơ chế HTTP | `SocketAddress` chỉ proxy endpoint |
| `SOCKS` | Proxy SOCKS ở tầng socket | `SocketAddress` chỉ proxy endpoint |
| `DIRECT` | Kết nối trực tiếp, không qua proxy | `null` với `Proxy.NO_PROXY` |

Chọn `Proxy.NO_PROXY` có nghĩa client được gợi ý **kết nối trực tiếp tới URI đích**. Nó **không phải** “không có mạng”, cũng không phải “bỏ qua request”. Nếu network policy buộc đi qua proxy, đặt DIRECT nhầm vị trí là một lỗi nghiêm trọng.

### Danh sách ứng viên có ý nghĩa gì?

Giả sử:

```java
return List.of(proxyA, proxyB);
```

Phía selector **đề xuất** proxy A trước, proxy B sau. Theo mô hình `ProxySelector`, khi một proxy kết nối thất bại, phía thực hiện kết nối **nên** thông báo `connectFailed` để selector cập nhật lựa chọn. Nhưng quyền quyết định có thử proxy B ngay hay không, thử bao nhiêu lần và xử lý request replay nằm ở **implementation của consumer**, không nằm ở việc bạn trả List.

**Không tự ghi trong API docs “có List hai proxy ⇒ Java HttpClient chắc chắn failover.”** Hãy integration test với đúng JDK, kiểu request, loại proxy, lỗi mạng và tình huống body có thể gửi lại.

### Thứ tự ưu tiên không phải round-robin

`List.of(A, B)` chỉ trả **A rồi B**; không có phép cân bằng tải tự động theo tỷ lệ, latency hay health. Nếu muốn round-robin, sticky routing, circuit breaker, backoff hoặc region affinity, đó là logic bạn phải **cài rõ** và bảo đảm thread safety.

### Khi nào direct hợp lý?

- Loopback `localhost`/`127.0.0.1` trong môi trường cho phép.
- Một domain nội bộ được **chính sách cho phép bypass**.
- Một thử nghiệm local không cần proxy.

Không dựa vào “host kết thúc bằng .internal” từ input không tin cậy như cơ chế duy nhất chống SSRF hoặc bỏ firewall; việc resolve DNS, private IP, redirects và egress policy vẫn cần bảo vệ độc lập.

## 5. Lựa chọn theo URI: scheme, hostname, port và policy

Một chính sách thường dùng:

```text
URI host thuộc *.corp.example / localhost
    -> DIRECT (chỉ khi công ty cho phép)

URI scheme https và host đối tác
    -> HTTP proxy A, HTTP proxy B dự phòng

URI scheme http thuộc vùng công khai
    -> HTTP proxy B

URI scheme không hỗ trợ hoặc host không xác định
    -> FAIL validation; không lặng lẽ DIRECT
```

Đây là ví dụ sư phạm, **không phải chính sách chuẩn cho mọi doanh nghiệp**. Trong hệ thống thật, host routing có thể phụ thuộc domain allowlist, datacenter, tenant, vùng địa lý, loại dịch vụ và quy định bảo mật.

### Vì sao kiểm tra scheme trước?

`http` và `https` khác nhau về cách client kết nối và bảo vệ nội dung. Một URI HTTPS được gửi qua **HTTP proxy** thường dùng phương thức `CONNECT` để tạo tunnel tới origin, sau đó TLS handshake tới origin qua tunnel. Điều này khác việc gửi HTTP plain request qua proxy. Chính sách có thể buộc HTTPS tới proxy được quản trị tốt hơn.

### Port có tác dụng gì?

`https://api.example:8443` khác `https://api.example` về endpoint. Nếu policy chỉ cho proxy truy cập một số port, cần xét `getPort()` (khi `-1` áp default theo scheme). Tuy nhiên, **đừng lấy port từ path hoặc chuỗi URI không được parse**.

### Path/query có nên tham gia chính sách?

`ProxySelector.select(URI)` nhận URI nên custom policy **có thể** xem path/query. Nhưng routing theo query dễ rò rỉ dữ liệu nhạy cảm và gây lệch giữa proxy/cache với origin. Nhiều hệ thống nên chọn proxy theo **scheme + destination host + port**, còn access control và tính hợp lệ của URL do lớp bảo mật/HTTP API xử lý.

### Bypass theo suffix cần tránh giả mạo

Kiểm tra host kết thúc bằng `".corp.example"` cho domain con, kèm chính xác `"corp.example"` nếu muốn cho domain gốc. Không viết `host.endsWith("corp.example")` để vô tình chấp nhận `evilcorp.example`. Nếu allowlist có IP/CIDR hoặc IPv6, nên dùng parser địa chỉ và kiểm chứng DNS/resolution phù hợp, không chỉ so sánh text.

## 6. `connectFailed` nhận thông tin gì và dùng khi nào?

Chữ ký:

```java
@Override
public void connectFailed(
        URI uri, SocketAddress sa, IOException ioe) {
    // Ghi nhận một proxy không thiết lập được kết nối.
}
```

Ba tham số khác nhau:

| Tham số | Ý nghĩa | Không được nhầm với |
|---|---|---|
| `uri` | **URI của tài nguyên mà client đang muốn truy cập** khi dùng proxy | URI của chính proxy |
| `sa` | **Địa chỉ socket của proxy/SOCKS server** mà kết nối tới đó thất bại | Địa chỉ origin server (trừ trường hợp đặc biệt không nên suy đoán) |
| `ioe` | `IOException` gây thất bại thiết lập kết nối tới proxy | Mã HTTP status hoặc exception nghiệp vụ bất kỳ |

Java 17 mô tả method này được gọi khi **không thiết lập được kết nối đến proxy/SOCKS server**. Một implementation có thể tạm loại proxy hỏng, thay đổi thứ tự proxy hoặc ghi nhận health metric. Không nên giả định callback sẽ xảy ra cho mọi `IOException` ở HTTP application.

### Ví dụ đúng về lỗi cần xét

- Kết nối TCP tới proxy host:port bị từ chối (`ConnectException`).
- Proxy không thể được kết nối do network unreachable/timeout ở bước thiết lập proxy connection, tùy client/provider.
- Một địa chỉ proxy cụ thể không có sẵn, selector muốn giảm ưu tiên nó trong một khoảng cooldown.

### Những lỗi **không đồng nghĩa** `connectFailed`

- Server trả `404 Not Found`: một **HTTP response hợp lệ**.
- Origin trả `500 Internal Server Error`: không có bằng chứng kết nối tới proxy đã thất bại.
- Proxy trả `407 Proxy Authentication Required`: đã có HTTP response từ proxy; đó là **bài toán xác thực proxy**, không mặc định kết nối TCP tới proxy thất bại.
- Proxy trả `502 Bad Gateway`: proxy **đã trả HTTP response**. Nó báo vấn đề upstream/gateway, **không phải cùng một tín hiệu** với không kết nối được tới proxy endpoint.
- JSON parsing hoặc validation lỗi sau khi HTTP response hoàn tất: lỗi application, không phải lỗi thiết lập proxy connection.
- TLS certificate verification thất bại tới origin: cần điều tra TLS trust/host và tunnel; **không thể tự quy mọi SSL exception về proxy down**.

Với `HttpClient` hoặc handler cụ thể, xem tài liệu và quan sát thực tế khi nào `connectFailed` được gọi. Một ứng dụng test gọi `selector.connectFailed(...)` **thủ công** có thể dùng để kiểm tra policy, nhưng **không chứng minh HTTP client tự phát callback trong mọi tình huống**.

## 7. Thiết kế cập nhật health trong `connectFailed`

Nếu chỉ cần demo, một cờ boolean thread-safe có thể ghi nhận proxy A đang lỗi, lần `select` sau bỏ proxy A. Trong production, cần tinh tế hơn:

1. **Nhận diện proxy bằng socket address** thực sự bị lỗi, không đánh dấu toàn bộ danh sách proxy down vì một endpoint khác hỏng.
2. **Không giữ lỗi vĩnh viễn** nếu hệ thống có thể hồi phục: dùng expiry/cooldown, backoff và thử lại có giới hạn.
3. **Tránh race** giữa nhiều thread `select` và `connectFailed`: dùng `AtomicBoolean`, `ConcurrentHashMap` hoặc immutable snapshot; cẩn thận với cập nhật health liên tiếp.
4. **Không chặn lâu** trong callback: đừng gọi HTTP health-check đồng bộ, DNS chậm hoặc database trong `connectFailed`.
5. **Có quan sát**: metric theo proxy endpoint, error class, số lần fail, thời điểm gần nhất, route được chọn, nhưng **không log credentials/token/query nhạy cảm**.
6. **Định nghĩa fail-open hay fail-closed**: nếu mọi proxy bắt buộc đều lỗi, có cho direct không? Trong môi trường buộc egress qua proxy, câu trả lời thường là **không**.
7. **Không nhầm health với authorization**: proxy đang sống chưa có nghĩa yêu cầu đi qua nó được quyền gọi tài nguyên.
8. **Không có rollback tự động**: nếu request đã chuyển byte qua proxy rồi bị lỗi ở giai đoạn sau, quyết định retry phải dựa trên HTTP method/idempotency và body có thể replay, không chỉ một callback.

### Cảnh báo về host failover

Khi hai proxy là hai gateway khác nhau, việc thử B sau A có thể thay đổi tuyến egress, IP nguồn nhìn thấy ở origin, audit policy, latency và phân quyền upstream. Vì vậy “backup proxy” nên thuộc **cùng tập proxy được phê duyệt cho URI đó**, không phải bất kỳ proxy còn hoạt động nào.

### Địa chỉ chưa resolve

`InetSocketAddress.createUnresolved("proxy-a.example", 8080)` tạo endpoint theo hostname/port mà chưa phải thực hiện DNS tại thời điểm tạo object. Nó phù hợp cho deterministic selection test. **Đừng hiểu unresolved là sẽ kết nối thành công**; khi HTTP client thực hiện kết nối, việc resolve/kết nối vẫn có thể thất bại theo môi trường và implementation.

## 8. Tích hợp với `java.net.http.HttpClient`

Cách đặt custom proxy selector **cho riêng một HttpClient**:

```java
// Mã minh họa khi đã có RoutingSelector selector.
HttpClient client = HttpClient.newBuilder()
        .proxy(selector)
        .build();
```

Cách này rõ phạm vi: client sử dụng selector đã được builder cung cấp. Không cần sửa `ProxySelector.setDefault` toàn JVM; điều đó tránh làm các thư viện/luồng khác bất ngờ đổi route.

### Ba cấu hình dễ dùng

```java
// 1. Một proxy cố định cho HTTP/HTTPS:
HttpClient fixed = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                InetSocketAddress.createUnresolved(
                        "proxy.example", 8080)))
        .build();

// 2. Cố ý luôn kết nối trực tiếp:
HttpClient direct = HttpClient.newBuilder()
        .proxy(HttpClient.Builder.NO_PROXY)
        .build();

// 3. Chính sách custom theo URI:
// HttpClient custom = HttpClient.newBuilder()
//         .proxy(new RoutingSelector())
//         .build();
```

`ProxySelector.of(address)` là convenience factory sử dụng một proxy cho **HTTP và HTTPS**. Nó không thay được một custom selector có danh sách proxy và rule theo URI. `HttpClient.Builder.NO_PROXY` là selector dùng để chỉ định direct explicitly.

**Mặc định:** trong Java 17, nếu builder không gọi `proxy(...)`, client mới thường sử dụng **default proxy selector**. Default selector có thể xem cấu hình hệ thống và Java networking system properties. Đừng dựa vào việc `HttpClient.proxy()` trả `Optional.empty()` để kết luận client không dùng proxy: API cho biết nó **có thể vẫn dùng default selector không được expose**.

### Client đã build là cấu hình riêng

`HttpClient` được tạo từ builder có trạng thái cấu hình gắn với client; việc đổi `ProxySelector.setDefault(...)` sau khi tạo client **không tự thay đổi default proxy đã lấy** cho client cũ. Nếu muốn thay đổi routing runtime theo policy mới, tùy cách triển khai: cập nhật trạng thái thread-safe của custom selector đã gắn, hoặc tạo client mới với cấu hình mới phù hợp.

**Thận trọng:** selector có mutable state là một phần của client integration; một `HttpClient` được dùng từ nhiều thread có thể gọi selector khi nhiều request diễn ra đồng thời. Phải kiểm soát concurrency và không trả một `ArrayList` mutable đang được thread khác thay đổi.

### Không nhầm `ProxySelector.of(...)` với `URL.openConnection(Proxy)`

Legacy API `URL.openConnection(Proxy)` dùng **một Proxy do caller truyền cho một connection**; không phải cùng hợp đồng với một `ProxySelector` chọn theo URI. Một số protocol handlers có thể không hỗ trợ proxy hoặc xử lý khác. Java `java.net.http.HttpClient` dùng `Builder.proxy(ProxySelector)`, không dùng trực tiếp một `Proxy` trong builder.

## 9. System-wide default, properties và override

Java cung cấp:

```java
ProxySelector current = ProxySelector.getDefault();
// ProxySelector.setDefault(custom) thay đổi global default
// cho những consumer dùng default về sau.
```

**Không tự thay đổi global default** trong một thư viện/SDK dùng chung JVM: các module networking khác có thể dựa vào proxy system khác, và sự thay đổi giữa threads gây hành vi khó đoán. Trong application có quyền kiểm soát startup, cấu hình hệ thống có thể hợp lý nếu được quản trị rõ.

Một số Java networking properties thường gặp:

| Property | Vai trò khái quát |
|---|---|
| `http.proxyHost`, `http.proxyPort` | Proxy HTTP trong cấu hình default |
| `https.proxyHost`, `https.proxyPort` | Proxy HTTPS trong cấu hình default |
| `http.nonProxyHosts` | Các host bypass proxy theo chính sách của default selector/handler |
| `socksProxyHost`, `socksProxyPort` | Cấu hình SOCKS trong các API có hỗ trợ |
| `java.net.useSystemProxies` | Cho phép Java sử dụng system proxy settings trên platform được hỗ trợ, thường xét từ lúc khởi động |

Cấu hình thực tế phụ thuộc runtime/client/platform. Không coi danh sách này là lời cam kết tất cả giá trị đều được tái đọc động sau mỗi request. **`java.net.useSystemProxies` được tài liệu hóa là tham số được xét khi startup.** Nếu muốn routing per-tenant/URI, dùng selector riêng và explicit config thay vì dựa vào việc sửa `System.setProperty(...)` bất kỳ lúc nào.

### Bypass với nonProxyHosts có phải cùng chính sách custom?

`http.nonProxyHosts` có cú pháp host patterns theo default selector/HTTP handler, không phải một danh sách `URI` và không nhất thiết tương đương rule do bạn cài trong `select`. Nếu chọn dùng custom selector, chịu trách nhiệm định nghĩa bypass policy của mình; đừng giả định default nonProxyHosts tự áp dụng bên trong custom code.

### Vấn đề proxy credentials

Credentials không nằm trong `Proxy` endpoint hay `select` return list. Nếu proxy yêu cầu xác thực HTTP, có thể cần `Authenticator`/challenge handling và cấu hình cụ thể của client. **Không nhúng user/password vào URI đích rồi mong selector dùng làm proxy password**, không log `Proxy-Authorization`.

## 10. HTTPS qua HTTP proxy, CONNECT và phiên HTTP

Khi target là `https://origin.example` và policy chọn một **HTTP proxy**, một đường kết nối phổ biến:

```text
Java HttpClient --TCP--> HTTP proxy
                       |
                       | CONNECT origin.example:443 HTTP/1.1
                       v
               Proxy tạo tunnel TCP
                       |
         Java HttpClient --TLS--> origin.example
                       |
                       v
                HTTPS request/response
```

Đây là **mô hình khái quát** của HTTPS tunneling, chi tiết có thể khác theo HTTP version và implementation.

- Proxy có thể thấy đích CONNECT hostname/port, thời điểm và lượng traffic; tunnel **không đồng nghĩa proxy nhìn được plaintext HTTPS** nếu end-to-end TLS được duy trì.
- Java client vẫn phải xác minh TLS certificate/hostname của origin theo trust policy. Routing qua proxy **không vô hiệu hóa TLS verification**.
- Trong môi trường có TLS interception được quản trị, proxy có thể chủ đích chặn/giải mã TLS nếu client tin certificate thích hợp; đây là vấn đề security/trust riêng.
- Với `http://` thông thường, HTTP proxy có thể nhận request HTTP dạng phù hợp cho proxy, không phải TLS end-to-end tới origin.
- `407 Proxy Authentication Required` là một **HTTP status** từ proxy; cần xử lý authentication theo client policy, không nên tự đánh dấu proxy TCP-down.
- `502 Bad Gateway` từ proxy vẫn là một HTTP response; nó có thể báo vấn đề origin/upstream, không tự chứng minh không thiết lập được kết nối **tới proxy**.

**Không nên tự gọi `connectFailed` chỉ vì nhận 407/502** rồi chuyển proxy vòng tròn. Tách lỗi network/proxy endpoint với HTTP response status và hệ quả nghiệp vụ.

### Phiên HTTP và connection reuse

Một `HttpClient` có thể tái sử dụng các kết nối theo policy/runtime. Việc custom selector thay đổi danh sách sau lỗi **không nhất thiết làm mọi kết nối đang mở lập tức đổi proxy**. Với kết nối đã thiết lập, request tiếp theo có thể dùng connection pool thay vì gọi lại mọi bước chọn proxy. Muốn kiểm chứng thời điểm selection hoặc fallback, phải test trên JDK, proxy và scenario cụ thể; **không dùng số lần `select` như số lượng HTTP request chắc chắn**.

## 11. Java 17 chạy được: chọn proxy theo URI và cập nhật sau connectFailed

Chương trình minh họa **không mở kết nối mạng tới các host giả**. Nó trực tiếp gọi `select` với ba URI, sau đó **mô phỏng** một lỗi kết nối đến proxy A bằng `connectFailed`, gọi `select` lần nữa và xây một `HttpClient` đã được gắn selector. Cách này giúp kết quả stdout xác định, không phụ thuộc DNS, Internet hay proxy công ty.

**Chính sách minh họa**:

1. Host `localhost`, `127.0.0.1` hoặc subdomain `*.corp.example` → DIRECT.
2. URI HTTP công khai → chỉ proxy B.
3. URI HTTPS công khai → proxy A rồi B; sau khi proxy A bị báo lỗi, chỉ đề xuất B.
4. URI thiếu scheme/host hoặc scheme không phải HTTP(S) → ném `IllegalArgumentException`.
5. `AtomicBoolean` bảo vệ cờ health trong ví dụ; production cần cooldown và state chi tiết hơn.

Tạo file **`ProxySelectorRoutingDemo.java`**:

```java
import java.io.IOException;
import java.net.ConnectException;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.SocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.util.List;
import java.util.Locale;
import java.util.StringJoiner;
import java.util.concurrent.atomic.AtomicBoolean;

public class ProxySelectorRoutingDemo {
    static final class RoutingSelector extends ProxySelector {
        private final Proxy primary = new Proxy(Proxy.Type.HTTP,
                InetSocketAddress.createUnresolved(
                        "proxy-a.example", 8080));
        private final Proxy backup = new Proxy(Proxy.Type.HTTP,
                InetSocketAddress.createUnresolved(
                        "proxy-b.example", 8081));
        private final AtomicBoolean primaryHealthy =
                new AtomicBoolean(true);

        @Override
        public List<Proxy> select(URI uri) {
            if (uri == null || uri.getScheme() == null
                    || uri.getHost() == null) {
                throw new IllegalArgumentException(
                        "Absolute URI with scheme and host required");
            }

            String scheme = uri.getScheme()
                    .toLowerCase(Locale.ROOT);
            if (!scheme.equals("http") && !scheme.equals("https")) {
                throw new IllegalArgumentException(
                        "Unsupported scheme: " + scheme);
            }

            String host = uri.getHost()
                    .toLowerCase(Locale.ROOT);

            if (host.equals("localhost")
                    || host.equals("127.0.0.1")
                    || host.endsWith(".corp.example")) {
                return List.of(Proxy.NO_PROXY);
            }

            if (scheme.equals("http")) {
                return List.of(backup);
            }

            return primaryHealthy.get()
                    ? List.of(primary, backup)
                    : List.of(backup);
        }

        @Override
        public void connectFailed(
                URI uri, SocketAddress address,
                IOException error) {
            if (uri == null || address == null || error == null) {
                throw new IllegalArgumentException(
                        "uri, address and error are required");
            }

            if (primary.address().equals(address)) {
                primaryHealthy.set(false);
            }

            System.out.println("Failed proxy: "
                    + endpoint(address) + " ("
                    + error.getClass().getSimpleName() + ")");
        }

        SocketAddress primaryAddress() {
            return primary.address();
        }
    }

    static String endpoint(SocketAddress address) {
        InetSocketAddress inet = (InetSocketAddress) address;
        return inet.getHostString() + ":" + inet.getPort();
    }

    static String describe(List<Proxy> proxies) {
        StringJoiner result = new StringJoiner(" -> ");
        for (Proxy proxy : proxies) {
            if (proxy.type() == Proxy.Type.DIRECT) {
                result.add("DIRECT");
            } else {
                result.add(proxy.type() + " "
                        + endpoint(proxy.address()));
            }
        }
        return result.toString();
    }

    public static void main(String[] args) {
        RoutingSelector selector = new RoutingSelector();
        URI internal = URI.create(
                "https://reports.corp.example/dashboard");
        URI partner = URI.create(
                "https://api.partner.example/v1");
        URI publicHttp = URI.create(
                "http://public.example/status");

        System.out.println("Internal: "
                + describe(selector.select(internal)));
        System.out.println("Partner before: "
                + describe(selector.select(partner)));
        System.out.println("Public HTTP: "
                + describe(selector.select(publicHttp)));

        // Mo phong thong bao that bai tu caller; KHONG ket noi mang.
        selector.connectFailed(partner,
                selector.primaryAddress(),
                new ConnectException("connection refused"));

        System.out.println("Partner after: "
                + describe(selector.select(partner)));

        HttpClient client = HttpClient.newBuilder()
                .proxy(selector)
                .build();
        System.out.println("HttpClient selector attached: "
                + (client.proxy().orElseThrow() == selector));
    }
}
```

Lệnh biên dịch/chạy **JDK 17 trở lên**:

```bash
javac --release 17 -encoding UTF-8 ProxySelectorRoutingDemo.java
java ProxySelectorRoutingDemo
```

**Stdout chính xác:**

```text
Internal: DIRECT
Partner before: HTTP proxy-a.example:8080 -> HTTP proxy-b.example:8081
Public HTTP: HTTP proxy-b.example:8081
Failed proxy: proxy-a.example:8080 (ConnectException)
Partner after: HTTP proxy-b.example:8081
HttpClient selector attached: true
```

### Diễn giải từng dòng

1. **Internal DIRECT:** `select` đọc `uri.getHost()`, nhận diện `reports.corp.example` là subdomain theo policy demo và trả `List.of(Proxy.NO_PROXY)`.
2. **Partner before:** với HTTPS công khai, `select` trả **danh sách có thứ tự** gồm HTTP proxy A và B. Đây là kết quả policy, **chưa có connection nào tới chúng**.
3. **Public HTTP:** rule demo cho URI scheme HTTP dùng B, không đưa A vào danh sách.
4. **Failed proxy:** chính chương trình gọi `selector.connectFailed` với `SocketAddress` của A và `ConnectException` được tạo để **mô phỏng** một lỗi. Đây **không phải** log do `HttpClient` phát khi kết nối thất bại.
5. **Partner after:** `AtomicBoolean` chuyển sang false, nên lần `select` kế tiếp chỉ trả proxy B. **Không** chứng minh consumer đã tự fallback hoặc retry request.
6. **HttpClient selector attached:** `HttpClient.newBuilder().proxy(selector)` nhận chính instance đó; `client.proxy().orElseThrow()==selector` là `true`. Chương trình không gọi `client.send` tới các host giả.

### Những giới hạn phải hiểu

- `InetSocketAddress.createUnresolved` **không resolve DNS**, cho phép demo không cần Internet; khi dùng để kết nối thật vẫn có thể lỗi DNS/network.
- `connectFailed` trong demo được gọi **thủ công**, không kiểm tra được callback invocation của runtime HTTP client.
- Dùng `AtomicBoolean` là đơn giản hóa: sau một lỗi proxy A bị bỏ vĩnh viễn trong vòng đời selector demo. Production cần cooldown/retry probe/per-proxy health và metrics.
- Bỏ proxy A khỏi `select` chỉ ảnh hưởng các lần chọn mới; không bảo đảm yêu cầu đã gửi hoặc kết nối đang mở chuyển proxy ngay.
- URI `*.corp.example`, `*.partner.example` ở đây là địa chỉ giả minh họa; không cần kết nối hay cấu hình proxy thật để chương trình chạy.

## 12. Một số thiết kế production và sự đánh đổi

### 12.1. Một danh sách cho nhiều URI hay một policy per-tenant?

Một proxy chung dễ quản trị, nhưng mọi lưu lượng đi qua một tuyến có thể ảnh hưởng latency và bảo mật. Routing theo tenant/service cần ánh xạ được kiểm soát, tránh một user input tự ý chọn proxy nội bộ để truy cập mạng riêng.

Không lưu credentials trong lựa chọn proxy trả về. Nếu nhiều tenant có danh tính/egress khác nhau, quản lý client/selector/auth riêng theo policy, tránh trộn quyền ở connection pool chung khi không phù hợp với thiết kế.

### 12.2. Circuit breaker với cooldown

Khi A lỗi:

```text
A HEALTHY --> (connect failure) --> A COOLDOWN
     ^                               |
     |                               v
     +---- (probe thành công) ---- A PROBING
                         (probe thất bại) -> A COOLDOWN
```

Đây là mô hình thiết kế **đề xuất**, không phải tính năng sẵn có của `ProxySelector`. Có thể lưu `nextRetryNanos` theo proxy và dùng `System.nanoTime()` để tính cooldown; không block `select` chờ proxy hồi phục. Probe phải có rate limit, và việc thăm dò có thể cần giao thức/endpoint chuyên dụng.

### 12.3. Healthy proxy không đồng nghĩa request chắc chắn thành công

Kết nối TCP tới proxy được thiết lập mới chỉ vượt qua một bước. Proxy còn có thể yêu cầu authentication, từ chối đích, gặp lỗi upstream, mất mạng tới origin, hoặc trả lỗi HTTP. `connectFailed` không thể thay thế HTTP error handling, retry status, circuit breaker origin hoặc business observability.

### 12.4. Hạn chế cấp phát và độ trễ trong selector

Nếu `select` bị gọi thường xuyên, đừng mỗi lần gọi lại tải config từ database hoặc đánh DNS cho mọi proxy. Có thể giữ danh sách proxy bất biến theo cấu hình, đọc state health thread-safe, trả `List.of(...)` để tránh consumer vô tình sửa list. Cần cơ chế reload policy an toàn, test không có race và định nghĩa điểm áp dụng cho các connection mới.

### 12.5. Tránh fail-open trái policy

Đưa DIRECT vào cuối danh sách proxy là một kiểu “nếu không có proxy thì thử đi thẳng”. Trong mạng doanh nghiệp có chính sách bắt buộc inspection/egress, điều đó có thể vi phạm compliance. Nếu mọi proxy không sẵn sàng, policy **fail-closed** thường nên để request thất bại có kiểm soát, chứ không lén bypass.

Tuy nhiên, chỉ trả danh sách proxy không đủ để thực thi mạng an toàn. Cần kiểm tra egress firewall, DNS/redirect policies, allowlist, TLS và auditing theo phạm vi.

## 13. Kiểm thử `ProxySelector` theo hai tầng

### 13.1. Unit test không cần mạng

Các assertion của chính selector có thể kiểm tra:

| Input | Kỳ vọng theo policy demo |
|---|---|
| `https://reports.corp.example/dashboard` | `[DIRECT]` |
| `https://api.partner.example/v1` khi healthy | `[proxyA,proxyB]` |
| `http://public.example/status` | `[proxyB]` |
| `https://api.partner.example/v1` sau báo lỗi A | `[proxyB]` |
| `null` | `IllegalArgumentException` |
| `/relative/path` | `IllegalArgumentException` |
| `file:///tmp/a` | `IllegalArgumentException` trong policy demo |
| `https://evilcorp.example` | **Không** bypass nếu rule đúng `.corp.example` |
| `http://localhost/status` | DIRECT |

Test `connectFailed` với `SocketAddress` của B không được làm A unhealthy nếu code chỉ đánh dấu A khi A lỗi. Nếu selector có state health theo địa chỉ, test trùng hostname với port khác để tránh nhận diện sai endpoint.

### 13.2. Integration test với proxy giả

Muốn kiểm tra **HttpClient thực sự dùng proxy nào**, cần thiết lập test proxy server loopback (hoặc framework test proxy), nhận connection/HTTP request/tunnel, tạo các tình huống:

1. Proxy A sẵn sàng, trả response/forward hợp lệ.
2. Proxy A từ chối TCP connection; quan sát có gọi `connectFailed` không, thử B hay trả lỗi.
3. Proxy trả `407`/`502`: so với lỗi connect khác thế nào.
4. HTTPS CONNECT tunnel và TLS handshake thành công/thất bại.
5. Redirect từ origin A tới origin B: selector có chọn lại theo URI mới không.
6. Reuse connection: request thứ hai có thực hiện selection lại không.
7. BodyPublisher stream một lần: nếu client định retry/failover, body có replay được không.
8. Connection timeout vs request timeout, concurrency/health race và shutdown.

**Không suy ra contract của một consumer chỉ từ unit test `select`.** Chương trình trong bài kiểm tra logic selector và builder wiring; integration test mới kiểm tra hành vi mạng cụ thể.

### 13.3. Kiểm thử lớp bảo mật

Với URI do user cung cấp, test cả:

- Domain nhìn giống internal như `evilcorp.example`.
- Encoded URL, userinfo, fragment, query chứa tên host internal, Unicode/IDN.
- Redirect tới `127.0.0.1`, private IP, link-local, metadata service khi policy không cho phép.
- DNS trả kết quả không khớp allowlist hoặc thay đổi theo thời gian.
- Proxy credentials không đi nhầm origin hoặc sang proxy không đáng tin.
- Proxy bị lỗi: có bị fallback DIRECT trái chính sách không.

Đây là lớp kiểm soát **SSRF/egress**, không tự được giải quyết chỉ vì code có `ProxySelector`.

## 14. Sai lầm thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| Nghĩ `select` thực hiện kết nối | Bỏ lỡ xử lý lỗi thực tế | `select` chỉ trả danh sách proxy/direct |
| Trả `null` khi không có proxy | Vi phạm contract và gây lỗi client | Trả `List.of(Proxy.NO_PROXY)` khi direct được phép |
| Trả `List.of()` để chỉ direct | Không phải direct entry hợp lệ | Dùng `Proxy.NO_PROXY` |
| Dùng `Proxy.NO_PROXY.address()` như proxy host | `null`/cast error | Kiểm tra `type()==DIRECT` |
| Cho rằng `List.of(A,B)` bảo đảm HttpClient tự failover A→B | Lỗi kỳ vọng retry/khả năng tương thích | Test consumer/JDK thực, không tự hứa fallback |
| Cho rằng `connectFailed` gọi trên mọi HTTP `5xx` | Đánh nhầm proxy healthy thành down | Chỉ theo lỗi kết nối đến proxy theo contract |
| Coi `407` là proxy TCP connect failure | Retry vô hạn, mất thông tin auth | Xử lý proxy authentication |
| Coi `502` luôn là proxy không kết nối được | Nhầm upstream/gateway failure | Phân loại status và network failure |
| Bỏ proxy A vĩnh viễn sau một lỗi thoáng qua | Lưu lượng lệch, không tự hồi phục | Cooldown/circuit breaker/probe phù hợp |
| Cho mọi URI lỗi proxy fallback DIRECT | Bypass egress/security policy | Fail-closed theo yêu cầu |
| Dùng `URI.toString().contains("corp")` | Query/path giả mạo bypass | Kiểm tra host/scheme chuẩn hóa |
| `host.endsWith("corp.example")` không có dấu chấm | Chấp nhận `evilcorp.example` | Dùng suffix `.corp.example` + domain gốc rõ |
| Đồng bộ kém khi cập nhật danh sách proxy | Race/corrupt state | Immutable lists và thread-safe health state |
| Block DNS/HTTP health-check trong `select`/`connectFailed` | Tăng latency hoặc deadlock tiềm năng | Callback nhẹ; probe riêng có giới hạn |
| Gọi `setDefault` trong thư viện dùng chung | Đổi routing toàn JVM ngoài ý muốn | Dùng `HttpClient.Builder.proxy(...)` per client |
| Nghĩ `HttpClient.proxy()==Optional.empty` là direct | Client có thể dùng default proxy ẩn | Xem builder/default policy thực |
| Nghĩ `http.nonProxyHosts` tự áp dụng trong custom selector | URI bypass/route không theo policy | Cài và test rule riêng |
| Đưa thông tin proxy password trong URI/log | Rò rỉ credentials | Dùng authentication API, redaction |
| Coi HTTPS qua HTTP proxy là plaintext toàn bộ | Hiểu sai CONNECT + TLS | Phân biệt tunnel và TLS end-to-end |
| Coi proxy đang hoạt động là request thành công | Origin có thể lỗi/timeout | Quan sát HTTP status + nghiệp vụ |
| Thay selector health mà nghĩ pool connection đã đổi ngay | Request vẫn dùng kết nối cũ | Test connection reuse/lifecycle |
| Tự retry POST upload/payment sau network failure | Side effect trùng hoặc body không replay | Idempotency, deadline, replay-safe policy |
| Dùng unresolved address như bằng chứng DNS OK | Kết nối thật có thể resolve fail | Hiểu `createUnresolved` chỉ hoãn DNS |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `ProxySelector.select(URI)` có tự kết nối tới proxy không?

**Đáp án:** Không. Nó trả một danh sách các `Proxy` hoặc `Proxy.NO_PROXY`. Consumer như HTTP client thực hiện connection theo khả năng và chính sách riêng.

**Câu 2.** Nếu không muốn dùng proxy cho URI nội bộ, trả gì?

**Đáp án:** `List.of(Proxy.NO_PROXY)`. Không trả `null` hoặc danh sách rỗng để biểu diễn direct.

**Câu 3.** `URI` truyền vào `select` là URI của proxy hay của resource cần truy cập?

**Đáp án:** Của **resource đích**. Địa chỉ proxy nằm trong `Proxy.address()` và trong `SocketAddress sa` của `connectFailed` khi proxy không kết nối được.

**Câu 4.** `connectFailed(uri, sa, ioe)` cho biết điều gì?

**Đáp án:** Kết nối tới proxy/SOCKS server tại `sa` đã thất bại khi phục vụ URI `uri`, với lỗi `IOException ioe`. Nó hỗ trợ cập nhật thứ tự/health của proxy.

**Câu 5.** Một server trả `404`, có nên tự gọi `connectFailed` không?

**Đáp án:** Không. `404` là HTTP status từ một HTTP exchange hợp lệ, không có bằng chứng TCP connection tới proxy endpoint thất bại.

**Câu 6.** Proxy trả `407 Proxy Authentication Required` có phải A down không?

**Đáp án:** Không mặc định. Proxy đã phản hồi HTTP; cần xử lý proxy authentication/challenge và policy, không đánh dấu connect failure chỉ vì status 407.

**Câu 7.** Danh sách `[A, B]` có bảo đảm JDK 17 HttpClient thử B nếu A lỗi?

**Đáp án:** Không thể hứa chung cho mọi consumer/tình huống; selector đưa ra **thứ tự đề xuất**, còn logic fallback/retry thực tế cần kiểm chứng ở client và runtime cụ thể.

**Câu 8.** Tại sao không đặt `Proxy.NO_PROXY` cuối danh sách cho Internet nếu doanh nghiệp yêu cầu dùng proxy?

**Đáp án:** Vì DIRECT cho phép kết nối thẳng tới origin, có thể bỏ qua bắt buộc egress/inspection; khi proxy không khả dụng nên fail-closed theo policy.

**Câu 9.** `Proxy.Type.HTTP` và `Proxy.Type.SOCKS` có đồng nghĩa?

**Đáp án:** Không. Chúng là các cơ chế proxy khác nhau. Mức hỗ trợ SOCKS tùy client/protocol; không suy ra `HttpClient` nào cũng hỗ trợ.

**Câu 10.** `Proxy.NO_PROXY.address()` trả gì?

**Đáp án:** `null`; phải kiểm tra `type` trước khi lấy/cast địa chỉ.

**Câu 11.** `ProxySelector.of(address)` khác custom selector ở đâu?

**Đáp án:** Factory `of` trả selector dùng một địa chỉ proxy cho HTTP/HTTPS, thuận tiện khi policy cố định. Custom subclass xử lý URI và health/fallback theo logic riêng.

**Câu 12.** Nếu `HttpClient.proxy()` trả `Optional.empty()`, có chắc không có proxy không?

**Đáp án:** Không. Java 17 API cho biết client có thể dùng default proxy selector không được expose qua Optional này.

**Câu 13.** Một URL chứa query `?next=corp.example` có nên được chọn DIRECT theo `contains("corp.example")`?

**Đáp án:** Không. Phải xác minh `URI.getHost()` của request, không nhầm query/path với authority.

**Câu 14.** Sau một lần `connectFailed`, có nên permanently disable proxy A?

**Đáp án:** Demo làm như vậy để dễ quan sát, production nên có health model, cooldown và phép thăm dò trở lại theo policy.

**Câu 15.** Khi thay proxy route, những connection HTTP đang mở có chắc đổi ngay không?

**Đáp án:** Không. Connection reuse/pool và thời điểm chọn route do client runtime quyết định; cần integration test.

**Câu 16.** Tại sao `HttpClient.newBuilder().proxy(selector)` thường an toàn hơn thay `ProxySelector.setDefault` trong SDK?

**Đáp án:** Vì gắn policy vào một client cụ thể, không làm bất ngờ các thư viện/HTTP clients khác cùng JVM.

**Câu 17.** Với HTTPS qua HTTP proxy, thường client và origin làm gì sau CONNECT?

**Đáp án:** Tạo TLS session tới origin qua tunnel, kiểm tra certificate/hostname. Proxy vẫn thấy thông tin đích CONNECT và metadata kết nối; CONNECT không tự vô hiệu hóa TLS.

**Câu 18.** Khi mất response sau POST thanh toán qua proxy, có nên retry ngay khi proxy B còn hoạt động?

**Đáp án:** Không. Server có thể đã commit trước khi response bị mất. Phải dựa trên idempotency, trạng thái nghiệp vụ, deadline và replay policy; chuyển proxy không tự bảo đảm exactly-once.

## 16. Checklist áp dụng trong Java networking

Trước khi dùng `ProxySelector` trong ứng dụng thực:

1. **Chốt routing policy**: domain/scheme/port nào DIRECT, domain nào bắt buộc đi proxy và nhóm dự phòng nào được phê duyệt.
2. **Parse URI đúng**: kiểm tra `getScheme`, `getHost`, port/IDN/IPv6 khi cần; không substring/suffix mơ hồ trên toàn URI.
3. **Trả danh sách hợp lệ** từ `select`: không `null`, không rỗng, dùng `Proxy.NO_PROXY` chỉ khi được phép.
4. **Phân biệt Proxy endpoint với origin**: `Proxy.address` và `connectFailed.sa` là địa chỉ proxy.
5. **Đặt custom selector trên đúng HttpClient** qua `HttpClient.newBuilder().proxy(selector)` để tránh global surprises.
6. **Không hứa failover** khi chưa integration test hành vi thật của client/JDK, loại proxy và request.
7. **Định nghĩa rõ callback failure**: `connectFailed` là thiết lập connection tới proxy thất bại, không phải HTTP status lỗi.
8. **Quản lý concurrency/health**: immutable lists, atomic state, cooldown, observability và callback nhẹ.
9. **Fail-closed khi bắt buộc egress**: không thêm DIRECT fallback không được cấp phép.
10. **Kiểm soát proxy authentication** riêng, không hardcode credentials hoặc log secret.
11. **HTTPS cần TLS verify**: CONNECT là tunnel, không thay thế trust/hostname checking.
12. **Test redirects/connection reuse** vì route có thể được áp dụng ở các thời điểm khác nhau.
13. **Có timeout và retry policy** phù hợp với HTTP method, idempotency và BodyPublisher khả năng replay.
14. **Bảo vệ SSRF và DNS** bằng kiểm soát mạng độc lập, không dựa độc nhất vào host matching của selector.
15. **Theo dõi lỗi đúng tầng**: DNS/network, proxy connect, proxy HTTP 407/502, origin status, TLS và business outcome.

**Ghi nhớ:** `ProxySelector.select(uri)` quyết định **proxy/direct candidate theo URI đích**. `connectFailed(uri, sa, ioe)` là phản hồi về **thất bại kết nối tới proxy endpoint**, để policy cập nhật thứ tự hoặc health. `HttpClient.Builder.proxy(selector)` là cách gắn chính sách vào client trong Java 17. Cần phân biệt **lựa chọn tuyến**, **kết nối thực sự**, **HTTP response** và **kết quả nghiệp vụ**; không tự suy ra failover, retry, hoặc bảo mật chỉ từ một danh sách `Proxy`.

### Tài liệu chính thức (Java SE 17)

- [java.net.ProxySelector — select, connectFailed, of, default](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html)
- [java.net.Proxy — HTTP/SOCKS/DIRECT và Proxy.NO_PROXY](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Proxy.html)
- [java.net.InetSocketAddress — createUnresolved](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html)
- [java.net.http.HttpClient.Builder — proxy, NO_PROXY](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [java.net.http.HttpClient — default selector và proxy()](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 Networking Properties — proxies](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html)
- [RFC 9110 — HTTP Semantics, CONNECT và status](https://www.rfc-editor.org/rfc/rfc9110)